# ============================================================
# Imports
# ============================================================
import ee
import sys
import requests
import rasterio
import numpy as np
import seaborn as sns
import geopandas as gpd
from pathlib import Path
from scipy import ndimage
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
# Global Thresholds for Forest Masking
# ============================================================
# Adjust these values based on your specific requirements
S2_NDVI_THRESHOLD = 0.6
S2_NDMI_THRESHOLD = 0.25

L8_NDVI_THRESHOLD = 0.5
L8_NDMI_THRESHOLD = 0.32


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


def compute_forest_mask_plugin(ndvi, ndmi, ndvi_threshold, ndmi_threshold, valid_mask):
    """
    Computes a binary forest mask based on thresholds and applies 5x5 morphological smoothing.
    """
    # Create initial boolean array of just the forest pixels
    binary_forest = (ndvi >= ndvi_threshold) & (ndmi >= ndmi_threshold)
    
    # Ensure we are only smoothing valid pixels to prevent edge artifacts
    binary_forest = binary_forest & valid_mask

    # Define a 5x5 structural element
    struct = np.ones((5, 5), dtype=bool)
    
    # Step A: Opening removes thin protrusions and isolated pixels
    smoothed_forest = ndimage.binary_opening(binary_forest, structure=struct)
    
    # Step B: Closing fills small holes and smooths inward boundaries
    smoothed_forest = ndimage.binary_closing(smoothed_forest, structure=struct)
    
    # Initialize mask and re-apply the smoothed forest (preserving valid pixels only)
    mask = np.zeros_like(ndvi, dtype=np.uint8)
    mask[valid_mask & smoothed_forest] = 1
    
    return mask


def visualise(s2_ndvi, s2_ndmi, s2_forest, l8_ndvi, l8_ndmi, l8_forest, valid_mask, output_png):
    # Apply valid mask (set invalid pixels to NaN for clean plotting)
    s2_ndvi_plot = np.where(valid_mask, s2_ndvi, np.nan)
    s2_ndmi_plot = np.where(valid_mask, s2_ndmi, np.nan)
    s2_forest_plot = np.where(valid_mask, s2_forest, np.nan)
    
    l8_ndvi_plot = np.where(valid_mask, l8_ndvi, np.nan)
    l8_ndmi_plot = np.where(valid_mask, l8_ndmi, np.nan)
    l8_forest_plot = np.where(valid_mask, l8_forest, np.nan)

    # Updated to 2x3 grid (increased width to 15)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
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
    plot_ax(axes[0, 0], s2_ndvi_plot, "Sentinel-2 NDVI", "RdYlGn", -0.2, 0.8)
    plot_ax(axes[0, 1], s2_ndmi_plot, "Sentinel-2 NDMI", "RdYlBu", -0.2, 0.6)
    plot_ax(axes[0, 2], s2_forest_plot, "Sentinel-2 Forest Mask", "gray", 0, 1)

    # --- Row 2: Landsat 8 ---
    plot_ax(axes[1, 0], l8_ndvi_plot, "Landsat 8 NDVI", "RdYlGn", -0.2, 0.8)
    plot_ax(axes[1, 1], l8_ndmi_plot, "Landsat 8 NDMI", "RdYlBu", -0.2, 0.6)
    plot_ax(axes[1, 2], l8_forest_plot, "Landsat 8 Forest Mask", "gray", 0, 1)

    plt.suptitle("Module 10: Sensor NDVI, NDMI & Forest Mask Comparison", fontsize=16, y=0.98)
    plt.tight_layout()
    plt.savefig(output_png, dpi=300, bbox_inches='tight')
    plt.close()


def plot_histograms(s2_ndvi, s2_ndmi, l8_ndvi, l8_ndmi, valid_mask, output_hist_png):
    """Generates aesthetic overlay histograms of NDVI and NDMI using seaborn."""
    
    # Filter arrays down to 1D valid pixels
    s2_ndvi_v = s2_ndvi[valid_mask]
    l8_ndvi_v = l8_ndvi[valid_mask]
    s2_ndmi_v = s2_ndmi[valid_mask]
    l8_ndmi_v = l8_ndmi[valid_mask]

    # Set Seaborn theme
    sns.set_theme(style="whitegrid", palette="muted")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # --- NDVI Histogram ---
    sns.histplot(s2_ndvi_v, bins=100, kde=True, color="mediumseagreen", stat="density", 
                 label="Sentinel-2", alpha=0.5, ax=axes[0])
    sns.histplot(l8_ndvi_v, bins=100, kde=True, color="coral", stat="density", 
                 label="Landsat 8", alpha=0.5, ax=axes[0])
    axes[0].set_title("NDVI Distribution", fontsize=14, pad=10)
    axes[0].set_xlabel("NDVI Value", fontsize=12)
    axes[0].set_ylabel("Density", fontsize=12)
    axes[0].legend(loc='upper right')

    # --- NDMI Histogram ---
    sns.histplot(s2_ndmi_v, bins=100, kde=True, color="royalblue", stat="density", 
                 label="Sentinel-2", alpha=0.5, ax=axes[1])
    sns.histplot(l8_ndmi_v, bins=100, kde=True, color="indianred", stat="density", 
                 label="Landsat 8", alpha=0.5, ax=axes[1])
    axes[1].set_title("NDMI Distribution", fontsize=14, pad=10)
    axes[1].set_xlabel("NDMI Value", fontsize=12)
    axes[1].set_ylabel("Density", fontsize=12)
    axes[1].legend(loc='upper right')

    plt.suptitle("Sensor Value Distributions (Sentinel-2 vs Landsat 8)", fontsize=16, y=1.02)
    sns.despine(left=True)
    plt.tight_layout()
    plt.savefig(output_hist_png, dpi=300, bbox_inches='tight')
    plt.close()


def process_and_compare(s2_path, l8_path, output_map_png, output_hist_png):
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

    # Compute Smoothed Forest Masks using individual thresholds
    s2_forest = compute_forest_mask_plugin(s2_ndvi, s2_ndmi, S2_NDVI_THRESHOLD, S2_NDMI_THRESHOLD, valid_mask)
    l8_forest = compute_forest_mask_plugin(l8_ndvi, l8_ndmi, L8_NDVI_THRESHOLD, L8_NDMI_THRESHOLD, valid_mask)

    # Calculate Pearson Correlation for valid pixels
    r_ndvi, _ = pearsonr(s2_ndvi[valid_mask], l8_ndvi[valid_mask])
    r_ndmi, _ = pearsonr(s2_ndmi[valid_mask], l8_ndmi[valid_mask])
    
    # Calculate Smoothed Forest Agreement %
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

    # Generate the 2x3 Map Plot
    visualise(
        s2_ndvi, s2_ndmi, s2_forest,
        l8_ndvi, l8_ndmi, l8_forest,
        valid_mask, output_map_png
    )

    # Generate the Seaborn Distribution Plots
    plot_histograms(
        s2_ndvi, s2_ndmi, 
        l8_ndvi, l8_ndmi, 
        valid_mask, output_hist_png
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
        
        plot_path = cfg.val_dir / f"Comparison_{cfg.aoi_slug}_{season_name[:3]}.png"
        hist_path = cfg.val_dir / f"Histograms_{cfg.aoi_slug}_{season_name[:3]}.png"

        print("  -> Downloading Sentinel-2 30m composite...")
        download_indices_composite('S2', start_date, end_date, ee_geom, s2_path)

        print("  -> Downloading Landsat 8 30m composite...")
        download_indices_composite('L8', start_date, end_date, ee_geom, l8_path)

        process_and_compare(s2_path, l8_path, plot_path, hist_path)
        
    print("\nValidation Complete.")


if __name__ == "__main__":
    main()
