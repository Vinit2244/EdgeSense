"""
EcoLand-OS | Step 1: NDVI Computation from Sentinel-2
Study Area: Rampachodavaram Mandal, Andhra Pradesh
GEE Export: S2_SR_HARMONIZED, bands B4/B8/B11, EPSG:32644, scale=10
"""

import os
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from pathlib import Path

INPUT_DIR = "../input"   # folder with your .tif files
OUTPUT_DIR = "../output/ndvi"           # where NDVI outputs will be saved
RGB_DIR    = "../output/rgb"
YEARS = [2024]
DISTRICT = "Mayurbhanj"


# ─────────────────────────────────────────────
# NOTE: Forest-range pixels (NDVI ≥ 0.4) this threshold can be changed (its just printed in this file, used in 2_forestMaskCreation.py)

# NOTE: I saved "var S2_BANDS = ['B4','B8','B11'];". If your band order is different, adjust the RED_BAND_INDEX, NIR_BAND_INDEX, and SWIR_BAND_INDEX below.
# ─────────────────────────────────────────────
# Sentinel-2 band indices (1-based, inside a multi-band TIF)
RED_BAND_INDEX = 1   # B4
NIR_BAND_INDEX = 2   # B8
SWIR_BAND_INDEX = 3   # B11  ← not used in NDVI but can be useful for QA/QC

# ─────────────────────────────────────────────
# FUNCTION: Inspect band count (run once to verify)
# ─────────────────────────────────────────────
def inspect_tif(tif_path):
    with rasterio.open(tif_path) as src:
        print(f"  File     : {Path(tif_path).name}")
        print(f"  CRS      : {src.crs}")
        print(f"  Bands    : {src.count}")
        print(f"  Shape    : {src.height} x {src.width} pixels")
        print(f"  Res      : {src.res[0]}m x {src.res[1]}m")
        for i in range(1, src.count + 1):
            band = src.read(i).astype(np.float32)
            valid = band[band > 0]
            if len(valid) > 0:
                print(f"  Band {i}    : min={valid.min():.0f}  mean={valid.mean():.0f}  max={valid.max():.0f}")

# ─────────────────────────────────────────────
# FUNCTION: Compute NDVI
# ─────────────────────────────────────────────
def compute_ndvi(tif_path, red_idx, nir_idx):
    with rasterio.open(tif_path) as src:
        red     = src.read(red_idx).astype(np.float32)
        nir     = src.read(nir_idx).astype(np.float32)
        profile = src.profile.copy()

    nodata_mask = (red == 0) | (nir == 0)
    red  = red  / 10000.0
    nir  = nir  / 10000.0
    ndvi = (nir - red) / (nir + red + 1e-10)
    ndvi = np.clip(ndvi, -1, 1)
    ndvi[nodata_mask] = np.nan

    return ndvi, profile

# ─────────────────────────────────────────────
# FUNCTION: Save NDVI raster
# ─────────────────────────────────────────────
def save_ndvi(ndvi_array, profile, output_path):
    profile.update(dtype=rasterio.float32, count=1, nodata=-9999)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    out = np.where(np.isnan(ndvi_array), -9999, ndvi_array).astype(np.float32)
    with rasterio.open(output_path, 'w', **profile) as dst:
        dst.write(out, 1)
    print(f"  Saved NDVI : {Path(output_path).name}")

# ─────────────────────────────────────────────
# FUNCTION: Save RGB bands as uint8 GeoTIFF    ← NEW
#
# Composite: R=B8(NIR), G=B4(Red), B=B11(SWIR)
# This is a standard false-color used to highlight
# vegetation (bright red) and bare soil/urban (cyan).
#
# Pass r_idx/g_idx/b_idx to remap any band order.
# ─────────────────────────────────────────────
def save_rgb(tif_path, output_path,
             r_idx=NIR_BAND_INDEX,
             g_idx=RED_BAND_INDEX,
             b_idx=SWIR_BAND_INDEX,
             percentile_clip=(2, 98)):
    """
    Reads three bands from tif_path, applies percentile contrast stretch,
    scales to uint8 (0-255), and writes a 3-band RGB GeoTIFF.
    """
    with rasterio.open(tif_path) as src:
        r_raw = src.read(r_idx).astype(np.float32)
        g_raw = src.read(g_idx).astype(np.float32)
        b_raw = src.read(b_idx).astype(np.float32)
        profile = src.profile.copy()

    # Nodata mask (GEE border pixels = 0 across all bands)
    nodata_mask = (r_raw == 0) & (g_raw == 0) & (b_raw == 0)

    def stretch_to_uint8(band, mask, p_low, p_high):
        """Percentile-clip then scale to 0-255 uint8."""
        valid_pixels = band[~mask & (band > 0)]
        if len(valid_pixels) == 0:
            return np.zeros_like(band, dtype=np.uint8)
        lo = np.percentile(valid_pixels, p_low)
        hi = np.percentile(valid_pixels, p_high)
        stretched = np.clip(band, lo, hi)
        # Normalise to 0-255
        stretched = (stretched - lo) / (hi - lo + 1e-10) * 255.0
        stretched = np.clip(stretched, 0, 255).astype(np.uint8)
        stretched[mask] = 0   # set nodata pixels to 0
        return stretched

    p_low, p_high = percentile_clip
    r_u8 = stretch_to_uint8(r_raw, nodata_mask, p_low, p_high)
    g_u8 = stretch_to_uint8(g_raw, nodata_mask, p_low, p_high)
    b_u8 = stretch_to_uint8(b_raw, nodata_mask, p_low, p_high)

    # Update profile for a 3-band uint8 output
    profile.update(
        dtype  = rasterio.uint8,
        count  = 3,
        nodata = 0,
        compress = 'lzw',      # lossless compression keeps file size small
        photometric = 'RGB'    # tells GIS tools this is an RGB image
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with rasterio.open(output_path, 'w', **profile) as dst:
        dst.write(r_u8, 1)
        dst.write(g_u8, 2)
        dst.write(b_u8, 3)

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"  Saved RGB  : {Path(output_path).name}  ({size_mb:.1f} MB)")
    print(f"  Composite  : R=B8(NIR)  G=B4(Red)  B=B11(SWIR)")

# ─────────────────────────────────────────────
# MAIN: Process each year
# ─────────────────────────────────────────────
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(RGB_DIR, exist_ok=True)      # ← NEW

for year in YEARS:
    print(f"\nProcessing {year}...")

    tif_files = list(Path(INPUT_DIR).glob(f"{DISTRICT}_sentinel_{year}*.tif"))
    if not tif_files:
        print(f"  ⚠ No TIF found for {year} — check filename")
        continue

    tif_path = str(tif_files[0])

    # ── NDVI ──────────────────────────────────
    ndvi, profile = compute_ndvi(tif_path, RED_BAND_INDEX, NIR_BAND_INDEX)
    ndvi_out = os.path.join(OUTPUT_DIR, f"NDVI_{year}_postmonsoon.tif")
    save_ndvi(ndvi, profile, ndvi_out)

    valid = ndvi[~np.isnan(ndvi)]
    print(f"  Stats → Min: {valid.min():.3f} | Mean: {valid.mean():.3f} | Max: {valid.max():.3f}")
    print(f"  Forest-range pixels (NDVI ≥ 0.4): {np.sum(valid >= 0.4):,} / {len(valid):,}")

    # ── RGB ───────────────────────────────────  
    # rgb_out = os.path.join(RGB_DIR, f"RGB_{year}_postmonsoon.tif")
    # save_rgb(tif_path, rgb_out)

print("\nDone. Check ../output/ndvi/ and ../output/rgb/")