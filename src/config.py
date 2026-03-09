# ============================================================
# Imports
# ============================================================
from pathlib import Path


# ============================================================
# Common Configurations
# ============================================================
state        = "ANDHRA_PRADESH"                  # Make sure it matches the folder name for shapefiles in input/
village      = "Rampachodavaram (CT)"            # Name of the village (as it appears in the shapefile's attribute table)
village_slug = village.replace(' ', '_')         # used for naming outputs
ee_project   = 'ee-vinitmehta'                   # GEE project name (must be set up in your GEE account and have appropriate permissions)
epsg_code    = 4326                              # WGS84 Lat/Lon (Earth Engine standard)
years        = list(range(2018, 2023))           # Years to analyze (2018-2022 inclusive)
scale        = 10.0                              # Sentinel-2's native resolution (10m per pixel)
image_collection = 'COPERNICUS/S2_SR_HARMONIZED' # Sentinel-2


# ============================================================
# Paths
# ============================================================
project_root       = Path(__file__).resolve().parents[1]
input_dir          = project_root / 'input'
state_shapefile    = input_dir / state / f"{state}.shp"
tiffs_dir          = input_dir / 'tiffs'
output_dir         = project_root / 'output'
ndvi_dir           = output_dir / 'ndvi'
rgb_dir            = output_dir / 'rgb'
plots_dir          = output_dir / 'plots'
visualisations_dir = output_dir / 'visualisations'
forest_mask_dir    = output_dir / 'forest_mask'
edge_core_mask_dir = output_dir / 'edge_core'
metrics_dir        = output_dir / 'fragmentation_metrics'


# ============================================================
# Tiff Download Configurations
# ============================================================
max_cloud_cover = 1  # 1% cloud cover limit


# ============================================================
# NDVI Configurations
# ============================================================
# NOTE: 0-based band indices, but rasterio (and Earth Engine) use 1-based indexing for band selection.
# download_aoi_tiff.py saves 13 bands in this order: B1, B2, B3, B4, B5, B6, B7, B8, B8A, B9, B10, B11, B12
blue_band_index  = 1  # B2
green_band_index = 2  # B3
red_band_index   = 3  # B4
nir_band_index   = 7  # B8
swir_band_index  = 11 # B11  ← not used in NDVI instead used for NDVI FCC visualisation

# Threshold for forest-range pixels (NDVI ≥ this value means "forest")
# 0.4 is standard for dense tropical/mixed forest (Rampachodavaram area)
# Adjust after visual check in QGIS if needed
ndvi_threshold  = 0.4


# ============================================================
# Edge-Core Configurations
# ============================================================
# Edge depth in pixels. At 10m resolution:
# 3 pixels = 30m edge,  5 pixels = 50m edge (common ecological standard)
edge_pixels = 3
