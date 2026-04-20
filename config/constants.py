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
image_collection = 'COPERNICUS/S2_SR_HARMONIZED' # Sentinel-2 or Landsat-8 surface reflectance collection
start_date = '{year}-10-01'
end_date   = '{year}-12-31'


# ============================================================
# Tiff Download Configurations
# ============================================================
cloud_cover_fallback_thresholds = range(1, 50, 5)
n_tiles           = 1  # Total tiles to split into (e.g., 9, 16, 25, 36)
bands_to_download = ['B3', 'B4', 'B8', 'B8A', 'B11'] # Green, Red, NIR, Narrow NIR, SWIR
rgb_bands         = ['B4', 'B3', 'B2'] # Red, Green, Blue


# ============================================================
# NDVI-NDMI Configurations
# ============================================================
# NOTE: 0-based band indices, but rasterio (and Earth Engine) use 1-based indexing for band selection.
# download_aoi_tiff.py saves 5 bands in this order: B2, B3, B4, B8, B11
green_band_index      = 0  # B3
red_band_index        = 1  # B4
nir_band_index        = 2  # B8
narrow_nir_band_index = 3  # B8A
swir_band_index       = 4  # B11  <- used for FCC visualisation
mask_gen_bands        = [1, 0, 2]

# Threshold for forest-range pixels (NDVI >= this value means "forest")
if image_collection == 'COPERNICUS/S2_SR_HARMONIZED':
    ndvi_threshold = 0.65
    ndmi_threshold = 0.3
elif image_collection == 'LANDSAT/LC08/C02/T1_L2':
    ndvi_threshold = 0.5
    ndmi_threshold = 0.3


# ============================================================
# Forest Cover Configurations
# ============================================================
mask_type = "smooth_boundary"  # "raw" or "smooth_boundary"
smooth_kernel_size = 5         # Size of the smoothing kernel (must be odd, e.g., 3, 5, 7)


# ============================================================
# Road-Mask Configurations
# ============================================================
road_buffer_m = 10 # In meters


# ============================================================
# Edge-Core Configurations
# ============================================================
edge_width = 100 # In meters; this is the width of the "edge" zone around non-forest areas. Adjust as needed based on ecological definitions and scale of analysis.
