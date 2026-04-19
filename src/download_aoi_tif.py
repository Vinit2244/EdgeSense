# ============================================================
# Imports
# ============================================================
import os
import ee
import sys
import math
import shutil
import requests
import rasterio
import numpy as np
import geopandas as gpd
from pathlib import Path
from shapely.geometry import box
from shapely.ops import unary_union
from rasterio.mask import mask as rio_mask
from omnicloudmask import predict_from_array
from rasterio.merge import merge as rio_merge

sys.path.append(str(Path(__file__).resolve().parents[1]))
import config as cfg
from src.utils import visualise_bands


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


def find_aoi(gdf, aoi_name):
    """Exact case-insensitive match across all text columns."""
    name = aoi_name.lower().strip()
    text_columns = gdf.select_dtypes(include=['object', 'string']).columns
    for col in text_columns:
        values = gdf[col].astype(str).str.lower().str.strip()
        match = gdf[values == name]
        if not match.empty:
            return match
    return None


def load_aoi_geodataframe():
    """Loads the correct shapefile based on cfg.aoi_level."""
    level = cfg.aoi_level.lower().strip()

    if level == "village":
        shapefile_path = cfg.villages_shapefile
        print(f"AOI level: village — loading village shapefile: {shapefile_path}")
    elif level in cfg.india_boundary_shapefiles:
        shapefile_path = cfg.india_boundary_shapefiles[level]
        print(f"AOI level: {level} — loading India boundary shapefile.")
    else:
        raise ValueError(
            f"Unknown aoi_level '{cfg.aoi_level}'. "
            f"Must be one of: village, district, subdistrict, state."
        )

    if not Path(shapefile_path).exists():
        raise FileNotFoundError(f"Shapefile not found: {shapefile_path}")

    return gpd.read_file(shapefile_path)


def compute_tile_grid(n_tiles):
    # Calculate the square root and round up to get the grid side
    grid_side = max(1, math.ceil(math.sqrt(n_tiles)))

    # Calculate the actual total tiles generated
    actual_tiles = grid_side ** 2

    print(f"Splitting into {grid_side}×{grid_side} = {actual_tiles} tiles.")

    return grid_side


def make_tile_boxes(bounds, grid_side):
    """Returns a list of (col, row, shapely box) for each cell in the grid."""
    minx, miny, maxx, maxy = bounds
    dx = (maxx - minx) / grid_side
    dy = (maxy - miny) / grid_side

    tiles = []
    for row in range(grid_side):
        for col in range(grid_side):
            tile_minx = minx + col * dx
            tile_miny = miny + row * dy
            tile_maxx = tile_minx + dx
            tile_maxy = tile_miny + dy
            tiles.append((col, row, box(tile_minx, tile_miny, tile_maxx, tile_maxy)))
    return tiles


def download_tile(median_image, tile_geom, tile_path, scale, epsg_code):
    """Downloads a single tile as GeoTIFF. Returns True on success."""
    ee_tile = shapely_to_ee_geometry(tile_geom)
    try:
        url = median_image.getDownloadURL({
            'scale':  scale,
            'crs':    f'EPSG:{epsg_code}',
            'region': ee_tile,
            'format': 'GEO_TIFF',
        })
        response = requests.get(url, timeout=300)
        if response.status_code != 200:
            print(f"HTTP {response.status_code}")
            return False

        tile_path.write_bytes(response.content)
        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def mosaic_tiles(tile_paths, output_path):
    """Merges a list of GeoTIFF tiles into a single mosaicked output file."""
    datasets = [rasterio.open(p) for p in tile_paths]
    mosaic, transform = rio_merge(datasets)

    meta = datasets[0].meta.copy()
    meta.update({
        "driver":    "GTiff",
        "height":    mosaic.shape[1],
        "width":     mosaic.shape[2],
        "transform": transform,
        "compress":  "lzw",
    })

    with rasterio.open(output_path, "w", **meta) as dest:
        dest.write(mosaic)

    for ds in datasets:
        ds.close()


def compute_cloud_mask(arr):
    """
    arr: (bands, H, W) float32 array normalised to [0, 1].
    Returns:
        cloud_mask     : (H, W) uint8 — 1 = clear, 0 = cloud / shadow
        cloud_pct      : % of pixels that are cloud or shadow
        haze_pct       : % of pixels that are thin cloud / haze (label 2)
    """
    # predict_from_array expects (3, H, W): Red, Green, NIR
    raw_mask = predict_from_array(arr[[cfg.red_band_index, cfg.green_band_index, cfg.nir_band_index], :, :])

    haze_pct = float((raw_mask == 2).mean()) * 100

    # Collapse thin cloud + shadow into the same "bad" class
    raw_mask[raw_mask > 1] = 1

    # Invert: 1 = clear, 0 = cloud / shadow
    cloud_mask = (1 - raw_mask).astype(np.uint8)
    cloud_mask = np.squeeze(cloud_mask)

    cloud_pct = float(1.0 - cloud_mask.mean()) * 100

    return cloud_mask, cloud_pct, haze_pct


def apply_cloud_mask(tiff_path):
    with rasterio.open(tiff_path) as src:
        data   = src.read().astype(np.float32)   # (bands, H, W)
        meta   = src.meta.copy()
        nodata = src.nodata if src.nodata is not None else 0

    arr = data / 10_000.0

    cloud_mask, cloud_pct, haze_pct = compute_cloud_mask(arr)
    print(f"✓  ({cloud_pct:.1f}% cloud/shadow, {haze_pct:.1f}% haze)")

    if cloud_mask.min() == 0:
        bad = (cloud_mask == 0)
        data[:, bad] = nodata
        meta.update({"nodata": nodata, "dtype": "float32"})

        with rasterio.open(tiff_path, "w", **meta) as dst:
            dst.write(data)
        print(f"    Saved cloud-masked TIFF -> {tiff_path.name}")
    else:
        print("    No cloud/shadow pixels detected — TIFF unchanged.")

    return cloud_pct, haze_pct, cloud_mask

def download_for_geom(
    shapely_geom,
    out_dir: str,
    year: int,
    progress_cb=None,
) -> Path:
    """
    Downloads a Sentinel-2 median composite for a given Shapely geometry and year.

    Parameters
    ----------
    shapely_geom : shapely.geometry.*
        The area of interest (in EPSG:4326 or any CRS — will be reprojected via EE).
    out_dir : str
        Directory where the output GeoTIFF will be saved.
    year : int
        The year to process (post-monsoon Oct–Dec window).
    progress_cb : callable, optional
        A function(msg: str) called with status strings during processing.

    Returns
    -------
    Path
        Absolute path to the saved (and cloud-masked) GeoTIFF.

    Raises
    ------
    RuntimeError
        If Earth Engine is not initialised, no imagery is found, or no tiles
        download successfully.
    """

    def _log(msg: str):
        if progress_cb:
            progress_cb(msg)

    # ── 1. Initialise Earth Engine ────────────────────────────────────────────
    try:
        ee.Initialize(project=cfg.ee_project)
    except Exception as e:
        raise RuntimeError(f"Earth Engine initialisation failed: {e}") from e

    # ── 2. Validate / fix geometry ────────────────────────────────────────────
    if not shapely_geom.is_valid:
        shapely_geom = shapely_geom.buffer(0)

    if shapely_geom.is_empty:
        raise ValueError("The supplied geometry is empty.")

    if shapely_geom.geom_type == "GeometryCollection":
        polys = [g for g in shapely_geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        shapely_geom = unary_union(polys)

    ee_geom = shapely_to_ee_geometry(shapely_geom)

    # ── 3. Find imagery (post-monsoon Oct–Dec, escalating cloud thresholds) ───
    cloud_thresholds = cfg.cloud_cover_fallback_thresholds

    collection    = None
    img_count     = 0
    used_threshold = None

    for threshold in cloud_thresholds:
        candidate = (
            ee.ImageCollection(cfg.image_collection)
            .filterBounds(ee_geom)
            .filterDate(f"{year}-10-01", f"{year}-12-31")
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", threshold))
        )
        count = candidate.size().getInfo()

        if count > 0:
            collection     = candidate
            img_count      = count
            used_threshold = threshold
            _log(f"Found {img_count} image(s) at <{threshold}% cloud cover (Oct–Dec {year})")
            break
        else:
            is_last = threshold == cloud_thresholds[-1]
            _log(
                f"No images at <{threshold}% (Oct–Dec {year}). "
                f"{'Trying next threshold…' if not is_last else 'All thresholds exhausted.'}"
            )

    if img_count == 0:
        raise RuntimeError(
            f"No Sentinel-2 imagery found for the AOI in Oct–Dec {year} "
            f"at any configured cloud threshold."
        )

    # ── 4. Build median composite ─────────────────────────────────────────────
    _log(f"Building median composite (<{used_threshold}% cloud)…")
    median_image = (
        collection.median()
        .clip(ee_geom)
        .select(cfg.bands_to_download)
    )

    # ── 5. Tile grid ──────────────────────────────────────────────────────────
    bounds    = shapely_geom.bounds                          # (minx, miny, maxx, maxy)
    grid_side = max(1, math.ceil(math.sqrt(cfg.n_tiles)))
    tiles     = make_tile_boxes(bounds, grid_side)
    _log(f"Downloading {grid_side}×{grid_side} tile(s)…")

    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    # Derive a slug from the geometry centroid so filenames are unique
    cx, cy    = shapely_geom.centroid.x, shapely_geom.centroid.y
    geom_slug = f"aoi_{cx:.4f}_{cy:.4f}".replace("-", "m").replace(".", "p")
    tiles_tmp = out_dir_path / f"_tiles_{geom_slug}_{year}"
    tiles_tmp.mkdir(exist_ok=True)

    tile_paths   = []
    failed_tiles = []

    for idx, (col, row, tile_geom) in enumerate(tiles):
        tile_path = tiles_tmp / f"tile_{col}_{row}.tif"
        _log(f"Tile ({col},{row}) [{idx + 1}/{len(tiles)}]…")

        ok = download_tile(median_image, tile_geom, tile_path, cfg.scale, cfg.epsg_code)

        if ok and tile_path.stat().st_size >= 1024:
            tile_paths.append(tile_path)
        else:
            tile_path.unlink(missing_ok=True)
            failed_tiles.append((col, row))

    if not tile_paths:
        shutil.rmtree(tiles_tmp, ignore_errors=True)
        raise RuntimeError(f"All {len(tiles)} tile(s) failed to download for {year}.")

    if failed_tiles:
        _log(f"Warning: {len(failed_tiles)} tile(s) failed — mosaic may have gaps.")

    # ── 6. Mosaic tiles ───────────────────────────────────────────────────────
    output_tiff = out_dir_path / f"{geom_slug}_{year}.tif"

    try:
        if len(tile_paths) == 1:
            shutil.move(str(tile_paths[0]), str(output_tiff))
            _log("Single tile — moved directly.")
        else:
            _log(f"Mosaicking {len(tile_paths)} tiles…")
            mosaic_tiles(tile_paths, output_tiff)

        # ── 7. Clip to AOI polygon exactly ────────────────────────────────────
        _log("Clipping to AOI boundary…")
        with rasterio.open(output_tiff) as src:
            clipped_img, clipped_transform = rio_mask(src, [shapely_geom], crop=True, nodata=0)
            clipped_meta = src.meta.copy()

        clipped_meta.update({
            "height":    clipped_img.shape[1],
            "width":     clipped_img.shape[2],
            "transform": clipped_transform,
            "nodata":    0,
        })

        with rasterio.open(output_tiff, "w", **clipped_meta) as dst:
            dst.write(clipped_img)

        # ── 8. Cloud masking ──────────────────────────────────────────────────
        _log("Running OmniCloudMask…")
        try:
            cloud_pct, haze_pct, _ = apply_cloud_mask(output_tiff)
            _log(f"Cloud masking done — {cloud_pct:.1f}% masked ({haze_pct:.1f}% haze).")
        except Exception as e:
            _log(f"Cloud masking failed (non-fatal): {e}")

    finally:
        shutil.rmtree(tiles_tmp, ignore_errors=True)

    _log(f"Saved → {output_tiff.name}")
    return output_tiff.resolve()

# ============================================================
# Main Execution Blocks
# ============================================================
def main():
    print(f"Loading shapefile for level='{cfg.aoi_level}'...")
    try:
        gdf = load_aoi_geodataframe()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}")
        return

    print(f"Searching for: '{cfg.aoi_name}'...")
    aoi_match = find_aoi(gdf, cfg.aoi_name)

    if aoi_match is None:
        print(f"'{cfg.aoi_name}' not found in the dataset.")
        print("Tip: check the attribute table in QGIS to confirm the exact name spelling.")
        return

    aoi_match   = aoi_match.to_crs(epsg=cfg.epsg_code)
    merged_geom = aoi_match.geometry.union_all()

    if merged_geom.is_empty:
        print(f"'{cfg.aoi_name}' has an empty or invalid geometry in the shapefile.")
        return

    ee_geom = shapely_to_ee_geometry(merged_geom)
    print(f"Geometry type: {merged_geom.geom_type} — converted successfully.")

    os.makedirs(cfg.tiffs_dir, exist_ok=True)
    os.makedirs(cfg.visualisations_dir, exist_ok=True)

    # Pre-compute tile grid once (same bounding box for every year)
    bounds    = merged_geom.bounds  # (minx, miny, maxx, maxy)
    grid_side = compute_tile_grid(n_tiles=cfg.n_tiles)
    tiles     = make_tile_boxes(bounds, grid_side)

    print(f"\nFetching representative composite for '{cfg.aoi_name}' ({cfg.years[0]}-{cfg.years[-1]})...")

    # Build the ordered list of thresholds to try: primary first, then fallbacks
    cloud_thresholds = cfg.cloud_cover_fallback_thresholds

    for year in cfg.years:
        print(f"\n--- Processing Year: {year} ---")

        # -------------------------------------------------------
        # Try post-monsoon (Oct–Dec) at increasing cloud thresholds
        # -------------------------------------------------------
        collection = None
        img_count  = 0
        used_threshold = None

        for threshold in cloud_thresholds:
            candidate = (ee.ImageCollection(cfg.image_collection)
                         .filterBounds(ee_geom)
                         .filterDate(f'{year}-10-01', f'{year}-12-31')
                         .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', threshold)))

            count = candidate.size().getInfo()

            if count > 0:
                collection     = candidate
                img_count      = count
                used_threshold = threshold
                print(f"  Found {img_count} post-monsoon image(s) (Oct-Dec {year}) "
                      f"at <{threshold}% cloud cover. Using post-monsoon composite.")
                break
            else:
                is_last = (threshold == cloud_thresholds[-1])
                print(f"  No images at <{threshold}% cloud cover (Oct-Dec {year}). "
                      f"{'Trying next threshold...' if not is_last else 'All thresholds exhausted — skipping year.'}")

        if img_count == 0:
            continue

        print(f"  Building median composite (threshold used: <{used_threshold}% cloud cover)...")
        median_image = collection.median().clip(ee_geom).select(cfg.bands_to_download)

        # Temporary folder to hold this year's tiles before mosaicking
        tiles_tmp = Path(cfg.tiffs_dir) / f"_tiles_{cfg.aoi_slug}_{year}"
        tiles_tmp.mkdir(exist_ok=True)

        tile_paths   = []
        failed_tiles = []

        for idx, (col, row, tile_geom) in enumerate(tiles):

            tile_path = tiles_tmp / f"tile_{col}_{row}.tif"
            print(f"  Tile ({col},{row}) [{idx+1}/{len(tiles)}]... ", end="", flush=True)

            ok = download_tile(median_image, tile_geom, tile_path, cfg.scale, cfg.epsg_code)

            if ok and tile_path.stat().st_size >= 1024:
                tile_paths.append(tile_path)
                print("✓")
            else:
                # GEE occasionally returns a valid 200 with a tiny error payload
                print("skipped (empty or error response)")
                tile_path.unlink(missing_ok=True)
                failed_tiles.append((col, row))

        if not tile_paths:
            print(f"  No tiles downloaded successfully for {year}. Skipping.")
            shutil.rmtree(tiles_tmp, ignore_errors=True)
            continue

        if failed_tiles:
            print(f"  Warning: {len(failed_tiles)} tile(s) failed — mosaic may have gaps.")

        output_tiff = Path(cfg.tiffs_dir) / f"{cfg.aoi_slug}_{year}.tif"

        try:
            # 1. Handle Mosaicking / Moving
            if len(tile_paths) == 1:
                shutil.move(str(tile_paths[0]), str(output_tiff))
                print(f"  Single tile — moved directly to {output_tiff.name}")
            else:
                print(f"  Mosaicking {len(tile_paths)} tiles...", end=" ", flush=True)
                mosaic_tiles(tile_paths, output_tiff)
                print("✓")

            # ==========================================================
            # Strictly Mask the TIFF to the Shapely Polygon
            # ==========================================================
            print("  Applying strict polygon mask to TIFF...", end=" ", flush=True)
            with rasterio.open(output_tiff) as src:
                # crop=True shrinks the bbox, nodata=0 forces outside pixels to 0
                clipped_img, clipped_transform = rio_mask(src, [merged_geom], crop=True, nodata=0)
                clipped_meta = src.meta.copy()

            clipped_meta.update({
                "height":    clipped_img.shape[1],
                "width":     clipped_img.shape[2],
                "transform": clipped_transform,
                "nodata":    0
            })

            # Overwrite the TIFF with the perfectly clipped version
            with rasterio.open(output_tiff, "w", **clipped_meta) as dest:
                dest.write(clipped_img)
            print("✓")
            print(f"  Saved masked {len(cfg.bands_to_download)}-band TIFF -> {output_tiff}")

            # ==========================================================
            # OmniCloudMask — detect and null-out cloud/shadow pixels
            # ==========================================================
            print("  Running OmniCloudMask...", end=" ", flush=True)
            cloud_mask = None
            try:
                cloud_pct, haze_pct, cloud_mask = apply_cloud_mask(output_tiff)
                print(f"  Cloud masking complete — {cloud_pct:.1f}% masked "
                      f"({haze_pct:.1f}% was thin cloud/haze).")
            except Exception as e:
                print(f"  Warning: cloud masking failed for {year}: {e}")

            # ==========================================================
            # Visualisations — cloud mask + RGB from cloud-masked TIFF
            # ==========================================================

            # 1. Binary cloud mask PNG (1 = clear, 0 = cloud/shadow)
            if cloud_mask is not None:
                cloud_vis_path = Path(cfg.visualisations_dir) / f"CloudMask_{cfg.aoi_slug}_{year}.png"
                try:
                    mask_as_band = cloud_mask[np.newaxis, :, :]  # (1, H, W)
                    visualise_bands(mask_as_band, cloud_vis_path)
                    print(f"  Saved cloud mask visualisation -> {cloud_vis_path.name}")
                except Exception as e:
                    print(f"  Warning: cloud mask visualisation failed for {year}: {e}")

            # 2. RGB visualisation
            output_png = Path(cfg.visualisations_dir) / f"RGB_{cfg.aoi_slug}_{year}.png"
            try:
                print(f"  Downloading RGB visualisation from GEE...", end=" ", flush=True)

                rgb_image = collection.median().clip(ee_geom).select(cfg.rgb_bands)
                thumb_url = rgb_image.getThumbURL({
                    'region':     ee_geom,
                    'dimensions': 1024,
                    'format':     'png',
                    'min':        0,
                    'max':        3000,
                    'gamma':      1.4,
                })

                response = requests.get(thumb_url, timeout=120)
                if response.status_code == 200:
                    output_png.write_bytes(response.content)
                    print(f"✓\n  Saved transparent RGB visualisation → {output_png}")
                else:
                    print(f"failed (HTTP {response.status_code})")

            except Exception as e:
                print(f"  Warning: RGB visualisation failed for {year}:\n  {e}")

        except Exception as e:
            print(f"  Error during mosaic/visualisation for {year}:\n  {e}")
        finally:
            # Always clean up temp tiles
            shutil.rmtree(tiles_tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
