# ============================================================
# Imports
# ============================================================
import numpy as np
import pandas as pd
import config as cfg
from pathlib import Path
from scipy.ndimage import label, find_objects
from utils import read_tif


# ============================================================
# Helper Functions
# ============================================================
def compute_perimeter_pixels(patch_binary):
    """Count edge pixels of a binary patch (4-connectivity)."""
    from scipy.ndimage import binary_erosion
    interior = binary_erosion(patch_binary)
    return np.sum(patch_binary & ~interior)


# ============================================================
# Main
# ============================================================
def main():
    Path(cfg.metrics_dir).mkdir(parents=True, exist_ok=True)

    all_years_summary = []

    for year in cfg.years:
        mask_path = Path(cfg.forest_mask_dir)    / f"ForestMask_{cfg.village_slug}_{year}.tif"
        edge_path = Path(cfg.edge_core_mask_dir) / f"EdgeCoreMask_{cfg.village_slug}_{year}.tif"

        if not mask_path.exists() or not edge_path.exists():
            print(f"Files missing for {year}, skipping.")
            continue

        # Read inputs
        forest_image, _ = read_tif(mask_path)
        forest_mask     = forest_image[0]          # (H, W)

        edge_image, _   = read_tif(edge_path)
        edge_mask_channel = edge_image[0]          # Channel 0: Edge mask
        core_mask_channel = edge_image[1]          # Channel 1: Core mask

        # Label connected forest patches
        forest_binary      = (forest_mask == 1)
        labeled, n_patches = label(forest_binary)
        print(f"\n{year} → {n_patches} forest patches found. Optimising calculation...")

        all_areas_px = np.bincount(labeled.ravel())
        
        # Count pixels where the specific channel mask is equal to 1
        core_counts  = np.bincount(labeled[core_mask_channel == 1].ravel(), minlength=n_patches + 1)
        edge_counts  = np.bincount(labeled[edge_mask_channel == 1].ravel(), minlength=n_patches + 1)

        slices = find_objects(labeled)

        # Per-patch metrics
        patch_records = []
        print(f"Processing metrics for {n_patches} patches...")

        for i, sl in enumerate(slices):
            patch_id = i + 1
            area_px  = all_areas_px[patch_id]
            area_ha  = area_px * (cfg.scale ** 2) / 10_000

            if area_ha < 0.5:
                continue

            patch_crop   = (labeled[sl] == patch_id)
            perimeter_px = compute_perimeter_pixels(patch_crop)
            perimeter_m  = perimeter_px * cfg.scale
            
            # Use standard Python float operations; no need for LaTeX rendering here
            shape_index  = perimeter_m / (2 * np.sqrt(np.pi * area_px * cfg.scale ** 2))

            core_px      = core_counts[patch_id]
            edge_px      = edge_counts[patch_id]
            core_area_ha = core_px * (cfg.scale ** 2) / 10_000
            edge_area_ha = edge_px * (cfg.scale ** 2) / 10_000
            edge_core_ratio = (edge_px / core_px) if core_px > 0 else None

            patch_records.append({
                "year":            year,
                "patch_id":        patch_id,
                "area_ha":         round(area_ha, 3),
                "perimeter_m":     round(perimeter_m, 1),
                "shape_index":     round(shape_index, 4),
                "core_area_ha":    round(core_area_ha, 3),
                "edge_area_ha":    round(edge_area_ha, 3),
                "edge_core_ratio": round(edge_core_ratio, 4) if edge_core_ratio else None,
            })

        # Save per-patch csv
        df_year = pd.DataFrame(patch_records)
        csv_out = Path(cfg.metrics_dir) / f"FragMetrics_{cfg.village_slug}_{year}.csv"
        df_year.to_csv(csv_out, index=False)

        # Handle edge cases where there are no patches >= 0.5ha
        if len(df_year) == 0:
            print(f"  No patches ≥0.5ha found for {year}.")
            continue

        summary = {
            "year":                 year,
            "n_patches":            len(df_year),
            "total_forest_ha":      round(df_year["area_ha"].sum(), 2),
            "mean_patch_ha":        round(df_year["area_ha"].mean(), 3),
            "largest_patch_ha":     round(df_year["area_ha"].max(), 3),
            "mean_shape_index":     round(df_year["shape_index"].mean(), 4),
            "mean_edge_core_ratio": round(df_year["edge_core_ratio"].mean(), 4),
        }
        all_years_summary.append(summary)
        print(
            f"  Patches (≥0.5ha): {len(df_year)} | "
            f"Total forest: {summary['total_forest_ha']} ha | "
            f"Mean Edge:Core: {summary['mean_edge_core_ratio']}"
        )

    # Save summary across all years
    if all_years_summary:
        df_summary = pd.DataFrame(all_years_summary)
        df_summary.to_csv(Path(cfg.metrics_dir) / f"FragMetrics_{cfg.village_slug}_AllYears_Summary.csv", index=False)
        print("\nFragmentation metrics saved.")
        print(df_summary.to_string(index=False))
    else:
        print("\nNo fragmentation metrics to save across all years.")


if __name__ == "__main__":
    main()
