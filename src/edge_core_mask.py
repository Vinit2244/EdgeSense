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
def compute_edge_core_mask_plugin(mask):
    disk = make_circular_kernel(cfg.edge_pixels)

    forest    = (mask == 1)
    nonforest = (mask == 0)
    nodata    = (mask == 255)

    # STRICTLY dilate only the valid non-forest pixels. 
    # This prevents the district boundary (nodata) from being treated as an edge.
    nonforest_dilated = binary_dilation(nonforest, structure=disk)

    edge = forest & nonforest_dilated
    core = forest & ~edge

    # 1. Initialize EVERYTHING as 255 (Transparent NoData)
    result = np.full((3, mask.shape[0], mask.shape[1]), 255, dtype=np.uint8)

    # 2. Paint Edge pixels Red
    result[0, edge] = 254
    result[1, edge] = 0
    result[2, edge] = 0

    # 3. Paint Core pixels Green
    result[0, core] = 0
    result[1, core] = 254
    result[2, core] = 0

    # 4. Paint valid Non-forest pixels Blue
    result[0, nonforest] = 0
    result[1, nonforest] = 0
    result[2, nonforest] = 254

    return result


# ============================================================
# Main
# ============================================================
def compute_edge_core_mask(year, mask_path):
    if not mask_path.exists():
        print(f"Mask not found for {year}, skipping.")
        return

    disk = make_circular_kernel(cfg.edge_pixels)

    mask_image, meta = read_tif(mask_path)
    mask = mask_image[0]                        

    forest     = (mask == 1)
    non_forest = (mask == 0)
    nodata     = (mask == 255)

    # Only dilate valid non-forest pixels
    non_forest_dilated = binary_dilation(non_forest, structure=disk)
    
    edge = forest & non_forest_dilated
    core = forest & ~edge

    # Initialize EVERYTHING as 255 (Transparent NoData)
    result = np.full((3, mask.shape[0], mask.shape[1]), 255, dtype=np.uint8)

    # Paint Edge pixels Red
    result[0, edge] = 254
    result[1, edge] = 0
    result[2, edge] = 0

    # Paint Core pixels Green
    result[0, core] = 0
    result[1, core] = 254
    result[2, core] = 0

    # Paint Non-forest pixels Blue
    result[0, non_forest] = 0
    result[1, non_forest] = 0
    result[2, non_forest] = 254

    out_meta = meta.copy()
    out_meta.update({
        "count": 3,
        "nodata": 255
    })

    out_path = cfg.edge_core_mask_dir / f"EdgeCoreMask_{cfg.aoi_slug}_{year}.tif"
    save_tif(result, out_path, meta=out_meta, nodata=255)
    print(f"  Saved EdgeCore : {out_path.name}")

    vis_out = cfg.visualisations_dir / f"EdgeCoreMask_{cfg.aoi_slug}_{year}.png"
    
    visualise_bands(
        result,
        out_path=vis_out,
        band_indices=[0, 1, 2],        
        nodata=255,
        percentile_stretch=(0, 100)
    )
    print(f"  Saved visual   : {vis_out.name}")

    n_core = int(np.sum(core))
    n_edge = int(np.sum(edge))
    ratio  = (n_edge / n_core) if n_core > 0 else float('inf')
    print(f"  {year} → Core: {n_core:,} px | Edge: {n_edge:,} px | Edge:Core ratio = {ratio:.3f}")


if __name__ == "__main__":
    cfg.edge_core_mask_dir.mkdir(parents=True, exist_ok=True)
    cfg.visualisations_dir.mkdir(parents=True, exist_ok=True)

    for year in cfg.years:
        mask_path = cfg.forest_mask_dir / f"ForestMask_{cfg.aoi_slug}_{year}.tif"
        compute_edge_core_mask(year, mask_path)

    print("\nEdge/Core separation complete.")
