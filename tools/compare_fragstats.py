# ============================================================
# compute_fragstats_comparison.py
#
# Outputs (all written to cfg.metrics_dir / "fragstats_comparison/"):
#   FragStats_Patches_{aoi}_{year}.csv        — pylandstats patch metrics
#   FragStats_Summary_{aoi}_{year}.csv        — pylandstats landscape summary
#   Custom_Patches_{aoi}_{year}.csv           — your patch metrics
#   Custom_Summary_{aoi}_{year}.csv           — your landscape summary
#   LandscapeComparison_{aoi}_{year}.csv      — side-by-side landscape summary
#   MultiYear_Landscape_{aoi}.csv             — all years combined landscape
# ============================================================

from __future__ import annotations

import sys
import warnings
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from scipy.ndimage import label, binary_dilation

warnings.filterwarnings("ignore")

sys.path.append(str(Path(__file__).resolve().parents[1]))
import config as cfg
from src.utils import read_tif

try:
    import pylandstats as pls
except ImportError as e:
    raise ImportError(
        "pylandstats is required: pip install pylandstats"
    ) from e


# ============================================================
# Shared helpers
# ============================================================

def make_circular_kernel(radius: int) -> np.ndarray:
    """Boolean 2-D disk of the given radius (diameter = 2r+1)."""
    size = radius * 2 + 1
    cy, cx = radius, radius
    y, x = np.ogrid[:size, :size]
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def reproject_to_metric(src_path: Path, dst_epsg: int = 32644) -> tuple[Path, bool]:
    """
    Reproject raster to a metric CRS if needed.
    Returns (path, needs_cleanup) — caller must unlink if needs_cleanup=True.
    """
    with rasterio.open(src_path) as src:
        if src.crs is None:
            raise ValueError(f"{src_path} has no CRS.")
        if src.crs.to_epsg() == dst_epsg:
            return src_path, False

        dst_crs = f"EPSG:{dst_epsg}"
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )
        meta = src.meta.copy()
        meta.update({"crs": dst_crs, "transform": transform,
                     "width": width, "height": height})

        tmp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()

        with rasterio.open(tmp_path, "w", **meta) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest,
                )
        return tmp_path, True


def write_labeled_tif(labeled_arr: np.ndarray, meta: dict) -> tuple[Path, bool]:
    """
    Write the scipy-labeled patch array to a temp GeoTIFF.
    Background (0) = nodata so pylandstats sees each patch as its own class.
    Returns (path, needs_cleanup=True).
    """
    out_meta = meta.copy()
    out_meta.update({"count": 1, "dtype": "int32", "nodata": 0})

    # Reproject to metric if needed before handing to pylandstats
    tmp_raw = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
    tmp_raw_path = Path(tmp_raw.name)
    tmp_raw.close()

    with rasterio.open(tmp_raw_path, "w", **out_meta) as dst:
        dst.write(labeled_arr.astype(np.int32), 1)

    metric_path, needs_reproj_cleanup = reproject_to_metric(tmp_raw_path)

    if metric_path != tmp_raw_path:
        tmp_raw_path.unlink(missing_ok=True)
        return metric_path, True

    return tmp_raw_path, True


# ============================================================
# Perimeter helper
# ============================================================

def compute_all_perimeters_vectorized(labeled_arr: np.ndarray,
                                      n_patches: int) -> np.ndarray:
    rows, cols = labeled_arr.shape

    diff_r = np.empty((rows, cols), dtype=bool)
    diff_r[:, :-1] = labeled_arr[:, :-1] != labeled_arr[:, 1:]
    diff_r[:, -1]  = labeled_arr[:, -1] != 0

    diff_l = np.empty((rows, cols), dtype=bool)
    diff_l[:, 1:]  = labeled_arr[:, 1:] != labeled_arr[:, :-1]
    diff_l[:, 0]   = labeled_arr[:, 0] != 0

    diff_d = np.empty((rows, cols), dtype=bool)
    diff_d[:-1, :] = labeled_arr[:-1, :] != labeled_arr[1:, :]
    diff_d[-1, :]  = labeled_arr[-1, :] != 0

    diff_u = np.empty((rows, cols), dtype=bool)
    diff_u[1:, :]  = labeled_arr[1:, :] != labeled_arr[:-1, :]
    diff_u[0, :]   = labeled_arr[0, :] != 0

    is_boundary = diff_r | diff_l | diff_d | diff_u
    boundary_labels = labeled_arr[is_boundary]
    return np.bincount(boundary_labels, minlength=n_patches + 1)


# ============================================================
# Build forest_binary
# ============================================================

def build_forest_binary(forest_mask: np.ndarray, meta: dict,
                         road_mask: np.ndarray | None) -> np.ndarray:
    nodata_val = meta.get("nodata", 255)
    forest_binary = (forest_mask == 1) & (forest_mask != nodata_val)

    if road_mask is not None:
        road_pixels   = (road_mask == 1)
        n_removed     = int(np.sum(forest_binary & road_pixels))
        forest_binary = forest_binary & ~road_pixels
        print(f"  Road mask applied  : {n_removed:,} forest pixels excluded.")
    else:
        print("  No road mask — proceeding without road subtraction.")

    return forest_binary


# ============================================================
# Our custom metrics
# ============================================================

def compute_custom_metrics(
    labeled_arr: np.ndarray,
    n_patches: int,
    edge_core_mask: np.ndarray,   # shape (3, H, W): R=edge, G=core, B=non-forest
    scale: float,
    year: int,
) -> tuple[pd.DataFrame, dict]:
    """
    Computes your existing custom fragmentation metrics on the labeled array.
    Returns (patch_df, landscape_summary_dict).
    """
    edge_mask_channel = edge_core_mask[0]   # value 254 = edge pixel
    core_mask_channel = edge_core_mask[1]   # value 254 = core pixel

    all_areas_px = np.bincount(labeled_arr.ravel(), minlength=n_patches + 1)
    core_counts  = np.bincount(
        labeled_arr[core_mask_channel == 254].ravel(), minlength=n_patches + 1
    )
    edge_counts  = np.bincount(
        labeled_arr[edge_mask_channel == 254].ravel(), minlength=n_patches + 1
    )
    perimeter_counts = compute_all_perimeters_vectorized(labeled_arr, n_patches)

    idx      = np.arange(1, n_patches + 1)
    area_px  = all_areas_px[idx].astype(np.float64)
    perim_px = perimeter_counts[idx].astype(np.float64)
    core_px  = core_counts[idx].astype(np.float64)
    edge_px  = edge_counts[idx].astype(np.float64)

    area_ha     = area_px * (scale ** 2) / 10_000
    perimeter_m = perim_px * scale

    # Shape index: deviation from a perfect circle
    shape_index = perimeter_m / (2.0 * np.sqrt(np.pi * area_px * scale ** 2))

    with np.errstate(divide="ignore", invalid="ignore"):
        log_shape_index = np.where(shape_index > 0, np.log(shape_index), np.nan)

    core_area_ha = core_px * (scale ** 2) / 10_000
    edge_area_ha = edge_px * (scale ** 2) / 10_000

    core_area_fraction = np.where(area_px > 0, core_px / area_px, np.nan)

    edge_core_ratio = np.divide(
        edge_px, core_px,
        out=np.full_like(edge_px, np.nan, dtype=float),
        where=core_px > 0,
    )

    patch_cohesion = np.where(
        area_px > 0,
        1.0 - (perim_px / (area_px * scale)),
        np.nan,
    )

    stress_pressure_index = np.where(
        ~np.isnan(edge_core_ratio),
        edge_core_ratio * shape_index,
        np.nan,
    )

    valid = area_ha >= 0.5

    df = pd.DataFrame({
        "year":                  year,
        "patch_id":              idx[valid],          # == scipy label integer
        "area_ha":               np.round(area_ha[valid],               3),
        "perimeter_m":           np.round(perimeter_m[valid],           1),
        "shape_index":           np.round(shape_index[valid],           4),
        "log_shape_index":       np.round(log_shape_index[valid],       4),
        "core_area_ha":          np.round(core_area_ha[valid],          3),
        "edge_area_ha":          np.round(edge_area_ha[valid],          3),
        "core_area_fraction":    np.round(core_area_fraction[valid],    4),
        "edge_core_ratio":       np.round(edge_core_ratio[valid],       4),
        "patch_cohesion":        np.round(patch_cohesion[valid],        4),
        "stress_pressure_index": np.round(stress_pressure_index[valid], 4),
    })

    if len(df) == 0:
        return df, {}

    total_edge = df["edge_area_ha"].sum()
    total_core = df["core_area_ha"].sum()
    total_ec   = round(total_edge / total_core, 4) if total_core > 0 else np.nan

    summary = {
        "year":                       year,
        "n_patches":                  len(df),
        "total_forest_ha":            round(df["area_ha"].sum(),                2),
        "mean_patch_ha":              round(df["area_ha"].mean(),               3),
        "largest_patch_ha":           round(df["area_ha"].max(),                3),
        "mean_shape_index":           round(df["shape_index"].mean(),           4),
        "mean_core_area_fraction":    round(df["core_area_fraction"].mean(),    4),
        "total_edge_core_ratio":      total_ec,
        "mean_patch_cohesion":        round(df["patch_cohesion"].mean(),        4),
        "mean_stress_pressure_index": round(df["stress_pressure_index"].mean(), 4),
    }

    print(
        f"  [Custom] {len(df)} patches ≥ 0.5 ha | "
        f"Forest: {summary['total_forest_ha']} ha | "
        f"E:C ratio: {summary['total_edge_core_ratio']} | "
        f"Stress: {summary['mean_stress_pressure_index']}"
    )

    return df, summary


# ============================================================
# PyLandStats metrics
# ============================================================

def compute_fragstats_metrics(
    labeled_arr: np.ndarray,
    n_patches: int,
    meta: dict,
    edge_depth_cells: int,
    year: int,
) -> tuple[pd.DataFrame, dict]:
    """
    Feeds the already-labeled array to pylandstats.
    Each unique integer in labeled_arr becomes its own 'class', so
    pylandstats sees separate patches — not one blob.
    """
    tmp_path, needs_cleanup = write_labeled_tif(labeled_arr, meta)

    try:
        # 4-neighborhood matches scipy default (rook adjacency)
        ls = pls.Landscape(str(tmp_path), nodata=0, neighborhood_rule="4")

        PATCH_METRICS = [
            "area",
            "perimeter",
            "shape_index",
            "fractal_dimension",
            "core_area",
            "core_area_index",
        ]

        metrics_kwargs = {
            "area":            {"hectares": False},
            "core_area":       {"hectares": False, "edge_depth": edge_depth_cells},
            "core_area_index": {"edge_depth": edge_depth_cells, "percent": True},
        }

        patch_df = ls.compute_patch_metrics_df(
            metrics=PATCH_METRICS,
            metrics_kwargs=metrics_kwargs,
        )

        # Drop background (class_val == 0 is nodata)
        patch_df = patch_df[patch_df["class_val"] != 0].reset_index(drop=True)

        patch_df = patch_df.rename(columns={
            "area":              "fs_area_m2",
            "perimeter":         "fs_perimeter_m",
            "shape_index":       "fs_shape_index",
            "fractal_dimension": "fs_fractal_dimension",
            "core_area":         "fs_core_area_m2",
            "core_area_index":   "fs_core_area_fraction_pct",
        })

        patch_df["year"]                    = year
        patch_df["patch_id"]                = patch_df["class_val"].astype(int)   # == scipy label
        patch_df["fs_area_ha"]              = patch_df["fs_area_m2"] / 10_000.0
        patch_df["fs_core_area_ha"]         = patch_df["fs_core_area_m2"] / 10_000.0
        patch_df["fs_core_area_fraction"]   = patch_df["fs_core_area_fraction_pct"] / 100.0
        patch_df["fs_edge_area_ha"]         = patch_df["fs_area_ha"] - patch_df["fs_core_area_ha"]
        patch_df["fs_edge_core_ratio"]      = np.where(
            patch_df["fs_core_area_ha"] > 0,
            patch_df["fs_edge_area_ha"] / patch_df["fs_core_area_ha"],
            np.nan,
        )

        # Keep columns in logical order, drop raw m2 cols
        keep_cols = [
            "year", "patch_id",
            "fs_area_ha", "fs_perimeter_m", "fs_shape_index",
            "fs_fractal_dimension", "fs_core_area_ha", "fs_edge_area_ha",
            "fs_core_area_fraction", "fs_edge_core_ratio",
        ]
        # Round
        for c in keep_cols[2:]:
            if c in patch_df.columns:
                patch_df[c] = patch_df[c].round(4)

        patch_df = patch_df[keep_cols]

        # Filter ≥ 0.5 ha to match your threshold
        patch_df = patch_df[patch_df["fs_area_ha"] >= 0.5].copy()

        total_forest = patch_df["fs_area_ha"].sum()
        total_core   = patch_df["fs_core_area_ha"].sum()
        total_edge   = patch_df["fs_edge_area_ha"].sum()

        landscape = {
            "year":                       year,
            "n_patches":                  int(len(patch_df)),
            "total_forest_ha":            round(float(total_forest), 2),
            "mean_patch_ha":              round(float(patch_df["fs_area_ha"].mean()), 3),
            "largest_patch_ha":           round(float(patch_df["fs_area_ha"].max()), 3),
            "mean_shape_index":           round(float(patch_df["fs_shape_index"].mean()), 4),
            "mean_fractal_dimension":     round(float(patch_df["fs_fractal_dimension"].mean()), 4),
            "mean_core_area_fraction":    round(float(patch_df["fs_core_area_fraction"].mean()), 4),
            "total_edge_core_ratio":      round(float(total_edge / total_core), 4) if total_core > 0 else np.nan,
        }

        print(
            f"  [FragStats] {len(patch_df)} patches ≥ 0.5 ha | "
            f"Forest: {landscape['total_forest_ha']} ha | "
            f"E:C ratio: {landscape['total_edge_core_ratio']}"
        )

        return patch_df, landscape

    finally:
        if needs_cleanup:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


# ============================================================
# Comparison tables
# ============================================================

def compare_landscape(custom_sum: dict, fs_sum: dict, year: int) -> pd.DataFrame:
    """Side-by-side landscape-level comparison."""
    metrics = [
        ("n_patches",                  "# Patches"),
        ("total_forest_ha",            "Total Forest (ha)"),
        ("mean_patch_ha",              "Mean Patch Size (ha)"),
        ("largest_patch_ha",           "Largest Patch (ha)"),
        ("mean_shape_index",           "Mean Shape Index  [formula differs — see notes]"),
        ("mean_core_area_fraction",    "Mean Core Area Fraction"),
        ("total_edge_core_ratio",      "Total Edge:Core Ratio"),
        ("mean_patch_cohesion",        "Mean Patch Cohesion  [custom only]"),
        ("mean_stress_pressure_index", "Mean Stress Pressure Index  [custom only]"),
        ("mean_fractal_dimension",     "Mean Fractal Dimension  [FragStats only]"),
    ]

    rows = []
    for key, label_str in metrics:
        c_val = custom_sum.get(key, np.nan)
        f_val = fs_sum.get(key, np.nan)

        try:
            pct = round((float(c_val) - float(f_val)) / float(f_val) * 100, 2)
        except Exception:
            pct = "—"

        def fmt(v):
            if isinstance(v, float) and np.isnan(v):
                return "—"
            return v

        rows.append({
            "Metric":                label_str,
            "Custom (yours)":        fmt(c_val),
            "FragStats (pylandstats)": fmt(f_val),
            "Delta_%":               pct,
        })

    df = pd.DataFrame(rows).set_index("Metric")
    df.name = f"Landscape comparison — {year}"
    return df

# ============================================================
# Main per-year pipeline
# ============================================================

def process_year(year: int, out_dir: Path, scale: float,
                 edge_depth_cells: int, dst_epsg: int = 32644):

    forest_mask_path = cfg.forest_mask_dir    / f"ForestMask_{cfg.aoi_slug}_{year}.tif"
    edge_path        = cfg.edge_core_mask_dir / f"EdgeCoreMask_{cfg.aoi_slug}_{year}.tif"
    road_mask_path   = cfg.road_mask_dir      / f"RoadMask_{cfg.aoi_slug}_{year}.tif"

    if not forest_mask_path.exists():
        print(f"  Forest mask missing for {year}, skipping.")
        return None, None

    if not edge_path.exists():
        print(f"  EdgeCore mask missing for {year}, skipping.")
        return None, None

    # ------------------------------------------------------------------
    # Load inputs
    # ------------------------------------------------------------------
    forest_image, forest_meta = read_tif(forest_mask_path)
    forest_mask = forest_image[0]

    edge_image, _ = read_tif(edge_path)  # shape (3, H, W)

    road_mask = None
    if road_mask_path.exists():
        road_image, _ = read_tif(road_mask_path)
        road_mask = road_image[0]
    else:
        print(f"  Road mask not found for {year}.")

    # ------------------------------------------------------------------
    # Build binary forest
    # ------------------------------------------------------------------
    forest_binary = build_forest_binary(forest_mask, forest_meta, road_mask)

    # ------------------------------------------------------------------
    # Label connected patches (scipy)
    # ------------------------------------------------------------------
    labeled_arr, n_patches = label(forest_binary)
    print(f"  {n_patches:,} connected forest patches found.")

    if n_patches == 0:
        print(f"  No patches for {year}.")
        return None, None

    # ------------------------------------------------------------------
    # A — 0ur custom metrics
    # ------------------------------------------------------------------
    custom_df, custom_sum = compute_custom_metrics(
        labeled_arr, n_patches, edge_image, scale, year
    )

    # ------------------------------------------------------------------
    # B — PyLandStats metrics
    # ------------------------------------------------------------------
    fs_df, fs_sum = compute_fragstats_metrics(
        labeled_arr, n_patches, forest_meta, edge_depth_cells, year
    )

    # ------------------------------------------------------------------
    # Standalone outputs for this year
    # ------------------------------------------------------------------
    # Custom
    if len(custom_df) > 0:
        custom_df.to_csv(out_dir / f"Custom_Patches_{cfg.aoi_slug}_{year}.csv",   index=False)
        pd.DataFrame([custom_sum]).to_csv(
            out_dir / f"Custom_Summary_{cfg.aoi_slug}_{year}.csv", index=False)

    # FragStats
    if len(fs_df) > 0:
        fs_df.to_csv(out_dir / f"FragStats_Patches_{cfg.aoi_slug}_{year}.csv",   index=False)
        pd.DataFrame([fs_sum]).to_csv(
            out_dir / f"FragStats_Summary_{cfg.aoi_slug}_{year}.csv", index=False)

    # ------------------------------------------------------------------
    # Comparison table for this year
    # ------------------------------------------------------------------
    if len(custom_df) > 0 and len(fs_df) > 0:

        # 2. Landscape summary side-by-side
        land_cmp = compare_landscape(custom_sum, fs_sum, year)
        land_cmp.to_csv(out_dir / f"LandscapeComparison_{cfg.aoi_slug}_{year}.csv")

        # Print landscape comparison to console
        print(f"\n  [Landscape comparison — {year}]")
        print(land_cmp.to_string())

    print(f"\n  Outputs written to {out_dir}/")

    return custom_sum, fs_sum

if __name__ == "__main__":
    out_dir          = cfg.metrics_dir / "fragstats_comparison"
    scale            = cfg.scale
    edge_depth_cells = round(cfg.edge_width / cfg.scale)
    dst_epsg         = getattr(cfg, "metric_epsg", 32644)

    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  Fragmentation Metrics: Custom vs FragStats (pylandstats)")
    print(f"  Scale       : {scale} m/px")
    print(f"  Edge width  : {cfg.edge_width} m  →  {edge_depth_cells} cells")
    print(f"  Target EPSG : {dst_epsg}")
    print("=" * 70)

    all_custom_rows = []
    all_fs_rows     = []

    for year in cfg.years:
        print(f"\n{'─' * 70}")
        print(f"  YEAR : {year}")
        print(f"{'─' * 70}")

        custom_sum, fs_sum = process_year(
            year, out_dir, scale, edge_depth_cells, dst_epsg
        )

        if custom_sum:
            all_custom_rows.append(custom_sum)
        if fs_sum:
            all_fs_rows.append(fs_sum)

    # ------------------------------------------------------------------
    # Multi-year combined landscape CSV
    # ------------------------------------------------------------------
    if all_custom_rows or all_fs_rows:
        combined = []
        for c, f in zip(all_custom_rows, all_fs_rows):
            row = {"year": c.get("year")}
            row.update({f"custom_{k}": v for k, v in c.items() if k != "year"})
            row.update({f"fs_{k}": v for k, v in f.items() if k != "year"})
            combined.append(row)

        pd.DataFrame(combined).to_csv(
            out_dir / f"MultiYear_Landscape_{cfg.aoi_slug}.csv", index=False
        )
        print(f"\nMulti-year landscape summary → {out_dir}/MultiYear_Landscape_{cfg.aoi_slug}.csv")

    print("Done.")