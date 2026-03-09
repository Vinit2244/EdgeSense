"""
EcoLand-OS | Module 3 | Step 2: Forest Binary Mask
Creates forest / non-forest raster for each year using NDVI threshold
"""

import os
import numpy as np
import rasterio
from pathlib import Path

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
NDVI_DIR   = "../output/ndvi"          # output from Step 1
MASK_DIR   = "../output/forest_mask"   # where binary masks will be saved
YEARS      = [2024]

# NOTE: we can make this better in 2 ways (using morphology and the road plan thing you mentioned). For now, this is a simple threshold-based mask that will be refined in future steps.

# NDVI threshold: pixels >= this value are classified as "forest"
# 0.4 is standard for dense tropical/mixed forest (Rampachodavaram area)
# Adjust after visual check in QGIS if needed
FOREST_NDVI_THRESHOLD = 0.4

os.makedirs(MASK_DIR, exist_ok=True)

for year in YEARS:
    ndvi_path = os.path.join(NDVI_DIR, f"NDVI_{year}_postmonsoon.tif")

    if not os.path.exists(ndvi_path):
        print(f"⚠ NDVI file not found for {year}, skipping.")
        continue

    with rasterio.open(ndvi_path) as src:
        ndvi = src.read(1).astype(np.float32)
        profile = src.profile.copy()

    # Binary mask: 1 = Forest, 0 = Non-forest, 255 = NoData
    forest_mask = np.where(np.isnan(ndvi), 255,
                  np.where(ndvi >= FOREST_NDVI_THRESHOLD, 1, 0)).astype(np.uint8)

    profile.update(dtype=rasterio.uint8, count=1, nodata=255)

    out_path = os.path.join(MASK_DIR, f"ForestMask_{year}.tif")
    with rasterio.open(out_path, 'w', **profile) as dst:
        dst.write(forest_mask, 1)

    n_forest = np.sum(forest_mask == 1)
    n_total  = np.sum(forest_mask != 255)
    pct      = (n_forest / n_total * 100) if n_total > 0 else 0
    print(f"{year} → Forest pixels: {n_forest:,}  ({pct:.1f}% of AOI)")

print("\nForest masks saved.")

# """
# EcoLand-OS | Debug: Check actual NDVI value distribution
# Run this BEFORE forest mask to find the right threshold
# """

# import numpy as np
# import rasterio
# import os

# NDVI_DIR = "../output/ndvi"
# YEARS    = [2022]

# for year in YEARS:
#     ndvi_path = os.path.join(NDVI_DIR, f"NDVI_{year}_postmonsoon.tif")
#     if not os.path.exists(ndvi_path):
#         continue

#     with rasterio.open(ndvi_path) as src:
#         ndvi   = src.read(1).astype(np.float32)
#         nodata = src.nodata

#     if nodata is not None:
#         ndvi[ndvi == nodata] = np.nan

#     valid = ndvi[~np.isnan(ndvi)]

#     print(f"\n{year} NDVI distribution:")
#     print(f"  Min   : {valid.min():.4f}")
#     print(f"  Max   : {valid.max():.4f}")
#     print(f"  Mean  : {valid.mean():.4f}")
#     print(f"  Median: {np.median(valid):.4f}")
#     print(f"  --- Pixel counts by threshold ---")
#     for t in [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6]:
#         count = int(np.sum(valid >= t))
#         pct   = count / len(valid) * 100
#         print(f"  ≥ {t:.2f} → {count:>10,} px  ({pct:.1f}%)")