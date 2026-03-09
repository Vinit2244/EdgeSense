"""
EcoLand-OS | Module 3 | Step 4: Forest Patch Fragmentation Metrics
Per-patch: area, perimeter, shape index, core area, edge ratio
Outputs: CSV summary + labeled patch raster
"""

import os
import numpy as np
import rasterio
import pandas as pd
from scipy.ndimage import label, find_objects
from pathlib import Path

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
MASK_DIR    = "../output/forest_mask"
EDGE_DIR    = "../output/edge_core"
METRICS_DIR = "../output/fragmentation_metrics"
YEARS       = [2024]

PIXEL_SIZE_M = 10.0  # Sentinel-2 resolution in metres

os.makedirs(METRICS_DIR, exist_ok=True)

def compute_perimeter_pixels(patch_binary):
    """Count edge pixels of a binary patch (4-connectivity)."""
    from scipy.ndimage import binary_erosion
    interior = binary_erosion(patch_binary)
    return np.sum(patch_binary & ~interior)

all_years_summary = []

for year in YEARS:
    mask_path = os.path.join(MASK_DIR, f"ForestMask_{year}.tif")
    edge_path = os.path.join(EDGE_DIR, f"EdgeCore_{year}.tif")

    if not os.path.exists(mask_path) or not os.path.exists(edge_path):
        print(f"⚠ Files missing for {year}, skipping.")
        continue

    with rasterio.open(mask_path) as src:
        forest_mask = src.read(1)
        profile     = src.profile.copy()

    with rasterio.open(edge_path) as src:
        edge_core = src.read(1)

    forest_binary = (forest_mask == 1)
    labeled, n_patches = label(forest_binary)
    print(f"\n{year} → {n_patches} forest patches found. Optimizing calculation...")

    # ── STEP 1: Global Stats (Fast) ──────────────────────────────────
    # Calculate areas and core/edge counts for ALL patches at once
    flat_labeled = labeled.ravel()
    all_areas_px = np.bincount(flat_labeled)

    # Mask labeled array by core/edge types to get per-patch counts
    core_counts = np.bincount(labeled[edge_core == 1].ravel(), minlength=n_patches+1)
    edge_counts = np.bincount(labeled[edge_core == 2].ravel(), minlength=n_patches+1)

    # ── STEP 2: Bounding Boxes (Fast) ───────────────────────────────
    # This finds the coordinates for every patch so we don't scan the whole map
    slices = find_objects(labeled)

    patch_records = []

    print(f"Processing metrics for {n_patches} patches...")
    for i, sl in enumerate(slices):
        patch_id = i + 1
        area_px = all_areas_px[patch_id]
        area_ha = area_px * (PIXEL_SIZE_M ** 2) / 10000

        if area_ha < 0.5:
            continue

        # Extract only the small "cutout" of the patch
        patch_crop = (labeled[sl] == patch_id)

        # Perimeter calculation only on the cutout
        perimeter_px = compute_perimeter_pixels(patch_crop)
        perimeter_m  = perimeter_px * PIXEL_SIZE_M

        shape_index = perimeter_m / (2 * np.sqrt(np.pi * area_px * PIXEL_SIZE_M**2))

        core_px = core_counts[patch_id]
        edge_px = edge_counts[patch_id]

        core_area_ha = core_px * (PIXEL_SIZE_M ** 2) / 10000
        edge_area_ha = edge_px * (PIXEL_SIZE_M ** 2) / 10000
        edge_core_ratio = (edge_px / core_px) if core_px > 0 else None

        patch_records.append({
            "year": year, "patch_id": patch_id, "area_ha": round(area_ha, 3),
            "perimeter_m": round(perimeter_m, 1), "shape_index": round(shape_index, 4),
            "core_area_ha": round(core_area_ha, 3), "edge_area_ha": round(edge_area_ha, 3),
            "edge_core_ratio": round(edge_core_ratio, 4) if edge_core_ratio else None
        })

    df_year = pd.DataFrame(patch_records)
    csv_out = os.path.join(METRICS_DIR, f"FragMetrics_{year}.csv")
    df_year.to_csv(csv_out, index=False)

    # ── Year summary stats ───────────────────────────────────────────────
    summary = {
        "year":                year,
        "n_patches":           len(df_year),
        "total_forest_ha":     round(df_year["area_ha"].sum(), 2),
        "mean_patch_ha":       round(df_year["area_ha"].mean(), 3),
        "largest_patch_ha":    round(df_year["area_ha"].max(), 3),
        "mean_shape_index":    round(df_year["shape_index"].mean(), 4),
        "mean_edge_core_ratio":round(df_year["edge_core_ratio"].mean(), 4),
    }
    all_years_summary.append(summary)
    print(f"  Patches (≥0.5ha): {len(df_year)} | Total forest: {summary['total_forest_ha']} ha | Mean Edge:Core: {summary['mean_edge_core_ratio']}")

# ── Save multi-year summary ──────────────────────────────────────────────
df_summary = pd.DataFrame(all_years_summary)
df_summary.to_csv(os.path.join(METRICS_DIR, "FragMetrics_AllYears_Summary.csv"), index=False)
print("\nFragmentation metrics saved.")
print(df_summary.to_string(index=False))