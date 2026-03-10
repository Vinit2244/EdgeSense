# ============================================================
# Imports
# ============================================================
import numpy as np
import pandas as pd
import config as cfg
from pathlib import Path
from utils import read_tif
from scipy.ndimage import label


# ============================================================
# Helper Functions
# ============================================================
def compute_all_perimeters_vectorized(labeled: np.ndarray, n_patches: int) -> np.ndarray:
    """
    Vectorized perimeter computation for ALL patches in a single pass.

    A pixel belongs to a patch's perimeter if it has at least one 4-connected
    neighbour with a different label (including background = 0).  We detect
    those boundary pixels with four shifted comparisons, OR the results, then
    use bincount to tally counts per patch — no per-patch loop required.

    Returns
    -------
    perimeter_counts : np.ndarray, shape (n_patches + 1,)
        Index 0 is background (ignored downstream); index i is the perimeter
        pixel count for patch i.
    """
    rows, cols = labeled.shape

    # Shift comparisons — True where neighbour label differs
    # right neighbour
    diff_r = np.empty((rows, cols), dtype=bool)
    diff_r[:, :-1] = labeled[:, :-1] != labeled[:, 1:]
    diff_r[:, -1]  = labeled[:, -1] != 0          # edge of array → boundary

    # left neighbour
    diff_l = np.empty((rows, cols), dtype=bool)
    diff_l[:, 1:]  = labeled[:, 1:] != labeled[:, :-1]
    diff_l[:, 0]   = labeled[:, 0]  != 0

    # bottom neighbour
    diff_d = np.empty((rows, cols), dtype=bool)
    diff_d[:-1, :] = labeled[:-1, :] != labeled[1:, :]
    diff_d[-1, :]  = labeled[-1, :]  != 0

    # top neighbour
    diff_u = np.empty((rows, cols), dtype=bool)
    diff_u[1:, :]  = labeled[1:, :] != labeled[:-1, :]
    diff_u[0, :]   = labeled[0, :]  != 0

    is_boundary = diff_r | diff_l | diff_d | diff_u

    # Count boundary pixels per patch label
    boundary_labels = labeled[is_boundary]  # 1-D array of patch IDs at boundary pixels
    perimeter_counts = np.bincount(boundary_labels, minlength=n_patches + 1)
    return perimeter_counts


# ============================================================
# Main
# ============================================================
def main():
    Path(cfg.metrics_dir).mkdir(parents=True, exist_ok=True)

    all_years_summary = []

    for year in cfg.years:
        mask_path = Path(cfg.forest_mask_dir)    / f"ForestMask_{cfg.aoi_slug}_{year}.tif"
        edge_path = Path(cfg.edge_core_mask_dir) / f"EdgeCoreMask_{cfg.aoi_slug}_{year}.tif"

        if not mask_path.exists() or not edge_path.exists():
            print(f"Files missing for {year}, skipping.")
            continue

        # Read inputs
        forest_image, forest_meta = read_tif(mask_path)
        forest_mask = forest_image[0]

        edge_image, _ = read_tif(edge_path)
        edge_mask_channel = edge_image[0]   # Channel 0: Edge mask
        core_mask_channel = edge_image[1]   # Channel 1: Core mask

        # NoData handling
        nodata_val   = forest_meta.get('nodata', 255)
        forest_binary = (forest_mask == 1) & (forest_mask != nodata_val)

        # Label connected patches
        labeled, n_patches = label(forest_binary)
        print(f"\n{year} → {n_patches} forest patches found.")

        if n_patches == 0:
            print(f"  No patches found for {year}.")
            all_years_summary.append({"year": year, "n_patches": 0})
            continue

        all_areas_px = np.bincount(labeled.ravel(), minlength=n_patches + 1)

        core_counts  = np.bincount(
            labeled[core_mask_channel == 1].ravel(), minlength=n_patches + 1
        )
        edge_counts  = np.bincount(
            labeled[edge_mask_channel == 1].ravel(), minlength=n_patches + 1
        )

        # Perimeter count
        perimeter_counts = compute_all_perimeters_vectorized(labeled, n_patches)

        # Slice to patch indices (1 to n_patches); index 0 is background and ignored downstream
        idx          = np.arange(1, n_patches + 1)
        area_px      = all_areas_px[idx].astype(np.float64)
        perim_px     = perimeter_counts[idx].astype(np.float64)
        core_px      = core_counts[idx].astype(np.float64)
        edge_px      = edge_counts[idx].astype(np.float64)

        # Derived metrics
        scale         = cfg.scale
        area_ha       = area_px * (scale ** 2) / 10_000
        perimeter_m   = perim_px * scale

        # Shape index: 1 = circle, higher = more irregular
        shape_index   = perimeter_m / (2.0 * np.sqrt(np.pi * area_px * scale ** 2))

        # Log-transform (NaN where shape_index ≤ 0)
        with np.errstate(divide='ignore', invalid='ignore'):
            log_shape_index = np.where(shape_index > 0, np.log(shape_index), np.nan)

        core_area_ha  = core_px * (scale ** 2) / 10_000
        edge_area_ha  = edge_px * (scale ** 2) / 10_000

        # Fraction of patch that is interior (sheltered) habitat
        core_area_fraction = np.where(area_px > 0, core_px / area_px, np.nan)

        # Primary hypothesis variable
        edge_core_ratio = np.divide(
            edge_px,
            core_px,
            out=np.full_like(edge_px, np.nan, dtype=float),
            where=core_px > 0
        )

        # Spatial cohesion
        patch_cohesion = np.where(
            area_px > 0,
            1.0 - (perim_px / (area_px * scale)),
            np.nan,
        )

        # Composite stress signal
        stress_pressure_index = np.where(
            ~np.isnan(edge_core_ratio),
            edge_core_ratio * shape_index,
            np.nan,
        )

        # Area filter
        valid = area_ha >= 0.5

        print(f"  {valid.sum()} patches ≥ 0.5 ha (of {n_patches} total).")

        # Build yearly dataframe
        df_year = pd.DataFrame({
            "year":                  year,
            "patch_id":              idx[valid],
            "area_ha":               np.round(area_ha[valid],             3),
            "perimeter_m":           np.round(perimeter_m[valid],         1),
            "shape_index":           np.round(shape_index[valid],         4),
            "log_shape_index":       np.round(log_shape_index[valid],     4),
            "core_area_ha":          np.round(core_area_ha[valid],        3),
            "edge_area_ha":          np.round(edge_area_ha[valid],        3),
            "core_area_fraction":    np.round(core_area_fraction[valid],  4),
            "edge_core_ratio":       np.round(edge_core_ratio[valid],     4),
            "patch_cohesion":        np.round(patch_cohesion[valid],      4),
            "stress_pressure_index": np.round(stress_pressure_index[valid], 4),
        })

        csv_out = Path(cfg.metrics_dir) / f"FragMetrics_{cfg.aoi_slug}_{year}.csv"
        df_year.to_csv(csv_out, index=False)

        if len(df_year) == 0:
            print(f"  No patches ≥ 0.5 ha found for {year}.")
            continue

        # Calculate landscape-level edge-to-core ratio for the valid patches
        total_edge_area = df_year["edge_area_ha"].sum()
        total_core_area = df_year["core_area_ha"].sum()
        
        # Prevent division by zero if there's absolutely no core habitat
        if total_core_area > 0:
            total_ec_ratio = round(total_edge_area / total_core_area, 4)
        else:
            total_ec_ratio = np.nan

        summary = {
            "year":                       year,
            "n_patches":                  len(df_year),
            "total_forest_ha":            round(df_year["area_ha"].sum(),                   2),
            "mean_patch_ha":              round(df_year["area_ha"].mean(),                  3),
            "largest_patch_ha":           round(df_year["area_ha"].max(),                   3),
            "mean_shape_index":           round(df_year["shape_index"].mean(),              4),
            "mean_core_area_fraction":    round(df_year["core_area_fraction"].mean(),       4),
            "total_edge_core_ratio":      total_ec_ratio,
            "mean_patch_cohesion":        round(df_year["patch_cohesion"].mean(),           4),
            "mean_stress_pressure_index": round(df_year["stress_pressure_index"].mean(),    4),
        }
        all_years_summary.append(summary)
        print(
            f"  Patches (≥ 0.5 ha): {len(df_year)} | "
            f"Total forest: {summary['total_forest_ha']} ha | "
            f"Edge:Core: {summary['total_edge_core_ratio']} | "
            f"Mean Stress Index: {summary['mean_stress_pressure_index']}"
        )

    # Save multi-year summary
    if all_years_summary:
        df_summary = pd.DataFrame(all_years_summary)
        df_summary.to_csv(
            Path(cfg.metrics_dir) / f"FragMetrics_{cfg.aoi_slug}_AllYears_Summary.csv",
            index=False,
        )
        print("\nFragmentation metrics saved.")
        print(df_summary.to_string(index=False))
    else:
        print("\nNo fragmentation metrics to save across all years.")


if __name__ == "__main__":
    main()
