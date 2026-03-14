# ============================================================
# Imports
# ============================================================
import sys
import numpy as np
from pathlib import Path
from scipy.ndimage import binary_dilation

sys.path.append(str(Path(__file__).resolve().parents[1]))
import config as cfg
from src.utils import visualise_bands, read_tif, save_tif


# ============================================================
# Helper Functions
# ============================================================
def make_circular_kernel(radius: int) -> np.ndarray:
    """Return a boolean 2-D disk of the given radius (diameter = 2r+1)."""
    size = radius * 2 + 1
    cy, cx = radius, radius                         # centre of the kernel
    y, x = np.ogrid[:size, :size]
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


# ============================================================
# Plugin Functions
# ============================================================
def compute_edge_core_mask_plugin(forest_mask, road_mask=None, edge_pixels=3):
    disk = make_circular_kernel(edge_pixels)

    # Subtract roads from forest mask
    if road_mask is not None:
        road_pixels    = (road_mask == 1)
        forest_on_road = (forest_mask == 1) & road_pixels
        n_reclassified = int(np.sum(forest_on_road))

        adjusted_mask = forest_mask.copy()
        adjusted_mask[forest_on_road] = 0

        print(f"  Road mask applied  : {n_reclassified:,} forest pixels "
              f"reclassified as non-forest due to roads.")
    else:
        print("  Road mask not provided — proceeding without road subtraction.")
        adjusted_mask = forest_mask.copy()

    forest     = (adjusted_mask == 1)
    non_forest = (adjusted_mask == 0)

    # Only dilate valid non-forest pixels so the district boundary is not
    # mistaken for an edge-generating feature.
    non_forest_dilated = binary_dilation(non_forest, structure=disk)

    edge = forest & non_forest_dilated
    core = forest & ~edge

    result = np.full((3, adjusted_mask.shape[0], adjusted_mask.shape[1]),
                     255, dtype=np.uint8)

    result[0, edge] = 254;  result[1, edge] = 0;   result[2, edge] = 0    # Red
    result[0, core] = 0;    result[1, core] = 254;  result[2, core] = 0    # Green
    result[0, non_forest] = 0; result[1, non_forest] = 0; result[2, non_forest] = 254  # Blue

    return result


# ============================================================
# Main
# ============================================================
def compute_edge_core_mask(year, mask_path, road_mask_path):
    if not mask_path.exists():
        print(f"  Forest mask not found for {year}, skipping.")
        return

    disk = make_circular_kernel(round(cfg.edge_width / cfg.scale))

    # Load forest mask
    mask_image, meta = read_tif(mask_path)
    forest_mask = mask_image[0]          # uint8: 0=non-forest, 1=forest, 255=nodata

    # Load road mask and subtract roads from forest
    if road_mask_path.exists():
        road_image, _ = read_tif(road_mask_path)
        road_mask = road_image[0]        # uint8: 0=no road, 1=road, 255=nodata

        road_pixels = (road_mask == 1)

        # Count how many forest pixels are reclassified
        forest_on_road = (forest_mask == 1) & road_pixels
        n_reclassified = int(np.sum(forest_on_road))

        # Reclassify: forest pixels that sit on a road → non-forest (0)
        adjusted_mask = forest_mask.copy()
        adjusted_mask[forest_on_road] = 0

        print(f"  Road mask applied  : {n_reclassified:,} forest pixels "
              f"reclassified as non-forest due to roads.")
    else:
        print(f"  Road mask not found for {year} — proceeding without road subtraction.")
        adjusted_mask = forest_mask.copy()

    # Derive edge / core from the road-adjusted forest mask
    forest     = (adjusted_mask == 1)
    non_forest = (adjusted_mask == 0)

    non_forest_dilated = binary_dilation(non_forest, structure=disk)

    edge = forest & non_forest_dilated
    core = forest & ~edge

    result = np.full((3, adjusted_mask.shape[0], adjusted_mask.shape[1]),
                     255, dtype=np.uint8)

    # Edge — Red
    result[0, edge] = 254
    result[1, edge] = 0
    result[2, edge] = 0

    # Core — Green
    result[0, core] = 0
    result[1, core] = 254
    result[2, core] = 0

    # Non-forest (includes reclassified road pixels) — Blue
    result[0, non_forest] = 0
    result[1, non_forest] = 0
    result[2, non_forest] = 254

    # Save GeoTIFF
    out_meta = meta.copy()
    out_meta.update({"count": 3, "nodata": 255})

    out_path = cfg.edge_core_mask_dir / f"EdgeCoreMask_{cfg.aoi_slug}_{year}.tif"
    save_tif(result, out_path, meta=out_meta, nodata=255)
    print(f"  Saved EdgeCore     : {out_path.name}")

    # Save Visualisation
    vis_out = cfg.visualisations_dir / f"EdgeCoreMask_{cfg.aoi_slug}_{year}.png"
    visualise_bands(
        result,
        out_path=vis_out,
        band_indices=[0, 1, 2],
        nodata=255,
        percentile_stretch=(0, 100),
    )
    print(f"  Saved visual       : {vis_out.name}")

    # Print stats
    n_core = int(np.sum(core))
    n_edge = int(np.sum(edge))
    ratio  = (n_edge / n_core) if n_core > 0 else float("inf")
    print(f"  {year} → Core: {n_core:,} px | Edge: {n_edge:,} px | "
          f"Edge:Core ratio = {ratio:.3f}")


if __name__ == "__main__":
    cfg.edge_core_mask_dir.mkdir(parents=True, exist_ok=True)
    cfg.visualisations_dir.mkdir(parents=True, exist_ok=True)

    for year in cfg.years:
        print(f"\nProcessing {year}...")
        mask_path      = cfg.forest_mask_dir / f"ForestMask_{cfg.aoi_slug}_{year}.tif"
        road_mask_path = cfg.road_mask_dir   / f"RoadMask_{cfg.aoi_slug}_{year}.tif"
        compute_edge_core_mask(year, mask_path, road_mask_path)

    print("\nEdge/Core separation complete.")
