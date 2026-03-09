# ============================================================
# Imports
# ============================================================
import os
import ee
import requests
import config as cfg
import geopandas as gpd
from pathlib import Path
from shapely.ops import unary_union
from utils import read_tif, visualise_bands


# Initialize Earth Engine
try:
    ee.Initialize(project=cfg.ee_project)
except Exception as e:
    print("Earth Engine not initialized. Run `earthengine authenticate` in your terminal first.")
    exit()


# ============================================================
# Helper Functions
# ============================================================
def shapely_to_ee_geometry(geom):
    """Robustly converts a Shapely geometry to an Earth Engine geometry."""
    if not geom.is_valid:
        geom = geom.buffer(0)

    if geom.geom_type == 'GeometryCollection':
        polys = [g for g in geom.geoms if g.geom_type in ('Polygon', 'MultiPolygon')]
        geom = unary_union(polys)

    def strip_z(coords):
        return [[c[0], c[1]] for c in coords]

    def clean_polygon(poly):
        exterior = strip_z(poly.exterior.coords)
        interiors = [strip_z(ring.coords) for ring in poly.interiors]
        return [exterior] + interiors

    if geom.geom_type == 'Polygon':
        return ee.Geometry.Polygon(clean_polygon(geom))
    elif geom.geom_type == 'MultiPolygon':
        return ee.Geometry.MultiPolygon([clean_polygon(p) for p in geom.geoms])
    else:
        raise ValueError(f"Unsupported geometry type: {geom.geom_type}")


def find_village(gdf, village_name):
    name = village_name.lower().strip()
    text_columns = gdf.select_dtypes(include=['object', 'string']).columns

    for col in text_columns:
        values = gdf[col].astype(str).str.lower().str.strip()
        match = gdf[values == name]
        if not match.empty:
            return match

    return None


# ============================================================
# Main
# ============================================================
def main():
    print(f"Loading village shapefile...")
    try:
        state_villages = gpd.read_file(cfg.state_shapefile)
    except Exception as e:
        print(f"Error loading shapefile:\n{e}")
        return

    print(f"Searching for: '{cfg.village}'...")
    village_match = find_village(state_villages, cfg.village)

    if village_match is None:
        print(f"{cfg.village} not found in the dataset.")
        return

    village_match = village_match.to_crs(epsg=cfg.epsg_code)
    merged_geom = village_match.geometry.union_all()

    if merged_geom.is_empty:
        print(f"{cfg.village} has an empty or invalid geometry in the shapefile.")
        return

    ee_geom = shapely_to_ee_geometry(merged_geom)
    print(f"Geometry type: {merged_geom.geom_type} — converted successfully.")

    os.makedirs(cfg.tiffs_dir, exist_ok=True)
    os.makedirs(cfg.visualisations_dir, exist_ok=True)

    print(f"\nFetching representative composite for {cfg.village} ({cfg.years[0]}-{cfg.years[-1]})...")

    for year in cfg.years:
        print(f"--- Processing Year: {year} ---")

        collection = (ee.ImageCollection(cfg.image_collection)
                      .filterBounds(ee_geom)
                      .filterDate(f'{year}-01-01', f'{year}-12-31')
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cfg.max_cloud_cover)))

        img_count = collection.size().getInfo()
        if img_count == 0:
            print(f"No images found for {year} with <{cfg.max_cloud_cover}% cloud cover. Skipping.")
            continue

        print(f"Found {img_count} images. Calculating median and downloading...")

        median_image = collection.median().clip(ee_geom).select('B.*')

        # Download the 13-band median composite as GeoTIFF
        output_tiff = Path(cfg.tiffs_dir) / f"{cfg.village_slug}_{year}.tif"

        try:
            url_tiff = median_image.getDownloadURL({
                'scale':  cfg.scale,
                'crs':    f'EPSG:{cfg.epsg_code}',
                'region': ee_geom,
                'format': 'GEO_TIFF',
            })

            response_tiff = requests.get(url_tiff)

            if response_tiff.status_code != 200:
                print(f"Failed to download TIFF for {year}. HTTP {response_tiff.status_code}")
                continue

            # Write the raw bytes from GEE to disk first
            output_tiff.write_bytes(response_tiff.content)
            print(f"Saved 13-band TIFF → {output_tiff}")

            # Visualise RGB composite from the downloaded TIFF
            image, meta = read_tif(output_tiff)

            output_png = Path(cfg.visualisations_dir) / f"RGB_{cfg.village_slug}_{year}.png"
            visualise_bands(
                image,
                band_indices=[cfg.red_band_index, cfg.green_band_index, cfg.blue_band_index],
                out_path=output_png,
                nodata=meta.get('nodata'),
            )

        except Exception as e:
            print(f"Error processing {year}:\n{e}")


if __name__ == "__main__":
    main()
