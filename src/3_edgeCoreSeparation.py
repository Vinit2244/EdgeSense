"""
EcoLand-OS | Module 3 | Step 3: Edge vs Core Forest
Uses morphological erosion to separate forest edge from core.
Edge width = 3 pixels = 30m at Sentinel-2 10m resolution
"""

import os
import numpy as np
import rasterio
from scipy.ndimage import binary_erosion, label
from pathlib import Path

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
MASK_DIR    = "../output/forest_mask"
EDGE_DIR    = "../output/edge_core"
YEARS       = [2024]

# Edge depth in pixels. At 10m resolution:
# 3 pixels = 30m edge,  5 pixels = 50m edge (common ecological standard)
EDGE_PIXELS = 3

os.makedirs(EDGE_DIR, exist_ok=True)

# Structuring element for erosion (square kernel)
struct = np.ones((EDGE_PIXELS * 2 + 1, EDGE_PIXELS * 2 + 1), dtype=bool)

for year in YEARS:
    mask_path = os.path.join(MASK_DIR, f"ForestMask_{year}.tif")

    if not os.path.exists(mask_path):
        print(f"⚠ Mask not found for {year}, skipping.")
        continue

    with rasterio.open(mask_path) as src:
        mask   = src.read(1)
        profile = src.profile.copy()

    forest = (mask == 1)  # boolean array

    # ── Core forest: erode the forest mask inward ──────────────────────
    core   = binary_erosion(forest, structure=struct)

    # ── Edge forest: forest pixels that are NOT core ────────────────────
    edge   = forest & ~core

    # ── Encode: 0=NonForest, 1=Core, 2=Edge, 255=NoData ────────────────
    result = np.zeros(mask.shape, dtype=np.uint8)
    result[forest]           = 2   # default: all forest = edge
    result[core]             = 1   # overwrite core pixels
    result[mask == 255]      = 255 # nodata

    profile.update(dtype=rasterio.uint8, nodata=255)

    out_path = os.path.join(EDGE_DIR, f"EdgeCore_{year}.tif")
    with rasterio.open(out_path, 'w', **profile) as dst:
        dst.write(result, 1)

    n_core = np.sum(result == 1)
    n_edge = np.sum(result == 2)
    ratio  = (n_edge / n_core) if n_core > 0 else float('inf')

    print(f"{year} → Core: {n_core:,} px | Edge: {n_edge:,} px | Edge:Core ratio = {ratio:.3f}")

print("\nEdge/Core separation complete.")