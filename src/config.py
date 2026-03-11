# ============================================================
# Imports
# ============================================================
from pathlib import Path


# ============================================================
# Common Configurations
# ============================================================
state        = "ANDHRA_PRADESH"                  # Must match the folder name for shapefiles in input/
aoi_level    = "subdistrict"                     # Administrative level: "village" | "subdistrict" | "district" | "state"
aoi_name     = "Rampa Chodavaram"                # Name as it appears in the shapefile's attribute table
# aoi_level    = "village"
# aoi_name     = "Rampachodavaram (CT)"
aoi_slug     = aoi_name.replace(' ', '_')        # Used for naming outputs
ee_project   = 'ee-vinitmehta'                   # GEE project name
epsg_code    = 4326                              # WGS84 Lat/Lon (Earth Engine standard)
years        = list(range(2018, 2025))           # Years to analyze (2018-2024 inclusive)
scale        = 10.0                              # Sentinel-2's native resolution (10m per pixel)
image_collection = 'COPERNICUS/S2_SR_HARMONIZED' # Sentinel-2


# ============================================================
# Paths
# ============================================================
project_root       = project_root = Path.home() / "Desktop" / "IIITH" / "Sem8" / "ORS" / "Project" / "EdgeSense"
# project_root       = Path(__file__).resolve().parents[1]
input_dir          = project_root / 'input'

# Village-level: state-specific shapefile
villages_shapefile = input_dir / state / f"{state}.shp"

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
ndmi_dir           = output_dir / 'ndmi'
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
bands_to_download = ['B3', 'B4', 'B8', 'B8A', 'B11']
rgb_bands         = ['B4', 'B3', 'B2']


# ============================================================
# NDVI-NDMI Configurations
# ============================================================
# NOTE: 0-based band indices, but rasterio (and Earth Engine) use 1-based indexing for band selection.
# download_aoi_tiff.py saves 5 bands in this order: B2, B3, B4, B8, B11
green_band_index      = 0  # B3
red_band_index        = 1  # B4
nir_band_index        = 2  # B8
narrow_nir_band_index = 3  # B8A
swir_band_index       = 4  # B11  ← used for FCC visualisation
mask_gen_bands        = [1, 0, 2]

# Threshold for forest-range pixels (NDVI ≥ this value means "forest")
ndvi_threshold = 0.4
ndmi_threshold = 0.1


# ============================================================
# Forest Cover Configurations
# ============================================================
mask_type = "smooth_boundary"  # "raw" or "smooth_boundary"
smooth_kernel_size = 3         # Size of the smoothing kernel (must be odd, e.g., 3, 5, 7)


# ============================================================
# Edge-Core Configurations
# ============================================================
edge_pixels = 10
