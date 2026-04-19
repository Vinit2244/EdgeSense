# ============================================================
# Imports
# ============================================================
import ee
import sys
import requests
import rasterio
import numpy as np
import geopandas as gpd
from pathlib import Path
import matplotlib.pyplot as plt
from scipy.stats import pearsonr
from shapely.ops import unary_union
from prettytable import PrettyTable

sys.path.append(str(Path(__file__).resolve().parents[1]))
import config as cfg

# Initialize Earth Engine
try:
    ee.Initialize(project=cfg.ee_project)
except Exception as e:
    print("Earth Engine not initialized. Run `earthengine authenticate`.")
    exit()


# ============================================================
# Helper Functions
# ============================================================
def shapely_to_ee_geometry(geom):
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


def load_and_prep_aoi():
    print(f"Loading shapefile for level='{cfg.aoi_level}'...")
    level = cfg.aoi_level.lower().strip()
    
    if level == "village":
        shapefile_path = cfg.villages_shapefile
    elif level in cfg.india_boundary_shapefiles:
        shapefile_path = cfg.india_boundary_shapefiles[level]
    else:
        raise ValueError("Unknown aoi_level in config.")

    gdf = gpd.read_file(shapefile_path)
    name = cfg.aoi_name.lower().strip()
    
    match = None
    for col in gdf.select_dtypes(include=['object', 'string']).columns:
        values = gdf[col].astype(str).str.lower().str.strip()
        filtered = gdf[values == name]
        if not filtered.empty:
            match = filtered
            break

    if match is None:
        raise ValueError(f"'{cfg.aoi_name}' not found.")

    merged_geom = match.to_crs(epsg=cfg.epsg_code).geometry.union_all()
    return shapely_to_ee_geometry(merged_geom)


def download_indices_composite(sensor, start_date, end_date, ee_geom, output_path):
    if sensor == 'S2':
        collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(ee_geom)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 5)))
        
        median_img = collection.median()
        ndvi = median_img.normalizedDifference(['B8', 'B4']).rename('NDVI')
        ndmi = median_img.normalizedDifference(['B8', 'B11']).rename('NDMI')

    elif sensor == 'L8':
        def apply_scale_factors(image):
            optical_bands = image.select('SR_B.').multiply(0.0000275).add(-0.2)
            return image.addBands(optical_bands, None, True)

        collection = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
            .filterBounds(ee_geom)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt('CLOUD_COVER', 20))
            .map(apply_scale_factors)) 
        
        median_img = collection.median()
        ndvi = median_img.normalizedDifference(['SR_B5', 'SR_B4']).rename('NDVI')
        ndmi = median_img.normalizedDifference(['SR_B5', 'SR_B6']).rename('NDMI')

    # Stack bands: Band 1 = NDVI, Band 2 = NDMI
    combined = ee.Image.cat([ndvi, ndmi])
    url = combined.getDownloadURL({
        'scale': 30.0,
        'crs': f'EPSG:{cfg.epsg_code}',
        'region': ee_geom,
        'format': 'GEO_TIFF',
    })

    response = requests.get(url, timeout=300)
    if response.status_code == 200:
        output_path.write_bytes(response.content)
        return True
    return False


def compute_forest_mask_plugin(ndvi, ndmi, ndvi_threshold, ndmi_threshold):
    forest = (ndvi >= ndvi_threshold) & (ndmi >= ndmi_threshold)
    mask = np.zeros_like(ndvi, dtype=np.uint8)
    mask[forest] = 1
    return mask


def visualise(s2_ndvi, s2_ndmi, l8_ndvi, l8_ndmi, valid_mask, output_png):
    # Apply valid mask (set invalid pixels to NaN for clean plotting)
    for arr in [s2_ndvi, s2_ndmi, l8_ndvi, l8_ndmi]:
        arr = arr.astype(np.float32)
        arr[~valid_mask] = np.nan

    # Updated to 2x2 grid
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    plt.subplots_adjust(wspace=0.1, hspace=0.2)

    # Helper function for plotting
    def plot_ax(ax, data, title, cmap, vmin, vmax, cbar_label=""):
        im = ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_title(title, fontsize=12)
        ax.axis('off')
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        if cbar_label:
            cbar.set_label(cbar_label)

    # --- Row 1: Sentinel-2 ---
    plot_ax(axes[0, 0], s2_ndvi, "Sentinel-2 NDVI", "RdYlGn", -0.2, 0.8)
    plot_ax(axes[0, 1], s2_ndmi, "Sentinel-2 NDMI", "RdYlBu", -0.2, 0.6)

    # --- Row 2: Landsat 8 ---
    plot_ax(axes[1, 0], l8_ndvi, "Landsat 8 NDVI", "RdYlGn", -0.2, 0.8)
    plot_ax(axes[1, 1], l8_ndmi, "Landsat 8 NDMI", "RdYlBu", -0.2, 0.6)

    plt.suptitle("Module 10: Sensor NDVI & NDMI Comparison", fontsize=16, y=0.98)
    plt.tight_layout()
    plt.savefig(output_png, dpi=300, bbox_inches='tight')
    plt.close()


def process_and_compare(s2_path, l8_path, output_png):
    with rasterio.open(s2_path) as s2_src, rasterio.open(l8_path) as l8_src:
        s2_data = s2_src.read() # Shape: (2, H, W)
        l8_data = l8_src.read() # Shape: (2, H, W)

    # Ensure spatial dimensions match exactly
    min_h = min(s2_data.shape[1], l8_data.shape[1])
    min_w = min(s2_data.shape[2], l8_data.shape[2])
    
    s2_ndvi, s2_ndmi = s2_data[0, :min_h, :min_w], s2_data[1, :min_h, :min_w]
    l8_ndvi, l8_ndmi = l8_data[0, :min_h, :min_w], l8_data[1, :min_h, :min_w]

    # Mask valid data (ignore 0s or extreme values from edge artifacts)
    valid_mask = (
        (s2_ndvi != 0) & (s2_ndvi > -1) & (s2_ndvi <= 1) &
        (l8_ndvi != 0) & (l8_ndvi > -1) & (l8_ndvi <= 1)
    )

    # Compute Forest Masks using your plugin to calculate agreement rate
    s2_forest = compute_forest_mask_plugin(s2_ndvi, s2_ndmi, cfg.ndvi_threshold, cfg.ndmi_threshold)
    l8_forest = compute_forest_mask_plugin(l8_ndvi, l8_ndmi, cfg.ndvi_threshold, cfg.ndmi_threshold)

    # Calculate Pearson Correlation for valid pixels
    r_ndvi, _ = pearsonr(s2_ndvi[valid_mask], l8_ndvi[valid_mask])
    r_ndmi, _ = pearsonr(s2_ndmi[valid_mask], l8_ndmi[valid_mask])
    
    # Calculate Forest Agreement %
    agree_pixels = np.sum(s2_forest[valid_mask] == l8_forest[valid_mask])
    total_valid = np.sum(valid_mask)
    forest_agreement = (agree_pixels / total_valid) * 100 if total_valid > 0 else 0

    # Initialize and populate PrettyTable
    table = PrettyTable()
    table.field_names = ["Metric", "Value"]
    table.align["Metric"] = "l"
    table.align["Value"] = "r"
    table.add_row(["NDVI Correlation (r)", f"{r_ndvi:.4f}"])
    table.add_row(["NDMI Correlation (r)", f"{r_ndmi:.4f}"])
    table.add_row(["Forest Mask Agreement", f"{forest_agreement:.2f}%"])

    print("\nComparison Statistics:")
    print(table)

    # Generate the 2x2 Plot (Forest masks and differences removed)
    visualise(
        s2_ndvi, s2_ndmi, 
        l8_ndvi, l8_ndmi, 
        valid_mask, output_png
    )


# ============================================================
# Main Validation Pipeline
# ============================================================
def main():
    ee_geom = load_and_prep_aoi()
    cfg.val_dir.mkdir(parents=True, exist_ok=True)
    
    year = cfg.years[0]
    seasons = {
        "Post-Monsoon": (f'{year}-10-01', f'{year}-12-31'),
        # "Pre-Monsoon": (f'{year}-03-01', f'{year}-05-31')
    }

    for season_name, (start_date, end_date) in seasons.items():
        print(f"\nEvaluating: {season_name} ({start_date} to {end_date})")
        
        s2_path = cfg.val_dir / f"S2_Indices_{cfg.aoi_slug}_{season_name[:3]}.tif"
        l8_path = cfg.val_dir / f"L8_Indices_{cfg.aoi_slug}_{season_name[:3]}.tif"
        plot_path = cfg.val_dir / f"Comparison_2x2_{cfg.aoi_slug}_{season_name[:3]}.png"

        print("  -> Downloading Sentinel-2 30m composite...")
        download_indices_composite('S2', start_date, end_date, ee_geom, s2_path)

        print("  -> Downloading Landsat 8 30m composite...")
        download_indices_composite('L8', start_date, end_date, ee_geom, l8_path)

        process_and_compare(s2_path, l8_path, plot_path)
        
    print("\nValidation Complete.")


if __name__ == "__main__":
    main()
