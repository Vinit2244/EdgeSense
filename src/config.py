# ============================================================
# Imports
# ============================================================
from pathlib import Path


# ============================================================
# Common Configurations
# ============================================================
state        = "ANDHRA_PRADESH"                  # Must match the folder name for shapefiles in input/
# aoi_level    = "subdistrict"                     # Administrative level: "village" | "subdistrict" | "district" | "state"
# aoi_name     = "Rampa Chodavaram"                # Name as it appears in the shapefile's attribute table
aoi_level    = "village"
aoi_name     = "Rampachodavaram (CT)"
aoi_slug     = aoi_name.replace(' ', '_')        # Used for naming outputs
ee_project   = 'ee-vinitmehta'                   # GEE project name
epsg_code    = 4326                              # WGS84 Lat/Lon (Earth Engine standard)
years        = list(range(2018, 2025))           # Years to analyze (2018-2022 inclusive)
scale        = 10.0                              # Sentinel-2's native resolution (10m per pixel)
image_collection = 'COPERNICUS/S2_SR_HARMONIZED' # Sentinel-2


# ============================================================
# Paths
# ============================================================
project_root       = Path(__file__).resolve().parents[1]
input_dir          = project_root / 'input'

# Village-level: state-specific shapefile
state_shapefile    = input_dir / state / f"{state}.shp"

# District / Sub-district / State-level: India-wide boundary folder
india_boundaries_dir = input_dir / 'State_District_Sub-district_Boundary_of_entire_India'

# Maps aoi_level → shapefile path within india_boundaries_dir
INDIA_BOUNDARY_SHAPEFILES = {
    "district":    india_boundaries_dir / "District Boundary.shp",
    "subdistrict": india_boundaries_dir / "Sub-district Boundary.shp",
    "state":       india_boundaries_dir / "State Boundary.shp",
}

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
max_cloud_cover   = 1  # 1% cloud cover limit
n_tiles           = 16 # Total tiles to split into (e.g., 9, 16, 25, 36)
bands_to_download = ['B4', 'B8', 'B11']
rgb_bands         = ['B4', 'B3', 'B2']


# ============================================================
# NDVI Configurations
# ============================================================
# NOTE: 0-based band indices, but rasterio (and Earth Engine) use 1-based indexing for band selection.
# download_aoi_tiff.py saves 5 bands in this order: B2, B3, B4, B8, B11
red_band_index   = 0  # B4
nir_band_index   = 1  # B8
swir_band_index  = 2  # B11  ← not used in NDVI; used for NDVI FCC visualisation

# Threshold for forest-range pixels (NDVI ≥ this value means "forest")
ndvi_threshold  = 0.6


# ============================================================
# Edge-Core Configurations
# ============================================================
edge_pixels = 3
