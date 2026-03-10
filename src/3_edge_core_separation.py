# ============================================================
# Imports
# ============================================================
import numpy as np
import config as cfg
from pathlib import Path
from utils import visualise_bands
from utils import read_tif, save_tif
from scipy.ndimage import binary_dilation


# ============================================================
# Helpers
# ============================================================
def make_circular_kernel(radius: int) -> np.ndarray:
    """Return a boolean 2-D disk of the given radius (diameter = 2r+1)."""
    size = radius * 2 + 1
    cy, cx = radius, radius                         # centre of the kernel
    y, x = np.ogrid[:size, :size]
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


# ============================================================
# Main
# ============================================================
def main():
    Path(cfg.edge_core_mask_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.visualisations_dir).mkdir(parents=True, exist_ok=True)

    # Circular structuring element — radius = cfg.edge_pixels
    disk = make_circular_kernel(cfg.edge_pixels)

    for year in cfg.years:
        mask_path = Path(cfg.forest_mask_dir) / f"ForestMask_{cfg.aoi_slug}_{year}.tif"

        if not mask_path.exists():
            print(f"Mask not found for {year}, skipping.")
            continue

        # Read forest mask
        mask_image, meta = read_tif(mask_path)
        mask = mask_image[0]                        # (H, W) uint8

        forest     = (mask == 1)                    # boolean array
        non_forest = (mask == 0)                    # boolean array
        nodata     = (mask == 255)                  # Our explicit NoData background

        # Any forest pixel within `edge_pixels` of a non-forest pixel is "edge".
        # Dilate the non-forest region by the disk, then restrict to forest.
        # Note: Because `nodata` is excluded from `non_forest`, the district 
        # boundary itself won't falsely trigger an "edge" effect.
        non_forest_dilated = binary_dilation(non_forest, structure=disk)
        edge = forest & non_forest_dilated
        core = forest & ~edge

        # Encode as 3-channel mask: (3, H, W)
        # Channel 0 (Red): Edge | Channel 1 (Green): Core | Channel 2 (Blue): Non-Forest
        result = np.zeros((3, mask.shape[0], mask.shape[1]), dtype=np.uint8)

        result[0, edge]       = 1
        result[1, core]       = 1
        result[2, non_forest] = 1

        # Preserve NoData (255) across all three channels
        result[0, nodata] = 255
        result[1, nodata] = 255
        result[2, nodata] = 255

        # Update metadata to explicitly state this is a 3-band TIFF now
        out_meta = meta.copy()
        out_meta.update({
            "count": 3,
            "nodata": 255
        })

        # Save Edge/Core GeoTIFF
        out_path = cfg.edge_core_mask_dir / f"EdgeCoreMask_{cfg.aoi_slug}_{year}.tif"
        save_tif(result, out_path, meta=out_meta, nodata=255)
        print(f"  Saved EdgeCore : {out_path.name}")

        # ==========================================================
        # Custom RGBA PNG Visualization
        # ==========================================================
        vis_out = Path(cfg.visualisations_dir) / f"EdgeCoreMask_{cfg.aoi_slug}_{year}.png"
        
        visualise_bands(
            result,
            out_path=vis_out,
            band_indices=[0, 1, 2],        # 3 indices trigger RGB mode ("RGBA")
            nodata=255,
            percentile_stretch=(0, 100)
        )
        print(f"  Saved visual   : {vis_out.name}")

        # Print stats
        n_core = int(np.sum(core))
        n_edge = int(np.sum(edge))
        ratio  = (n_edge / n_core) if n_core > 0 else float('inf')
        print(f"  {year} → Core: {n_core:,} px | Edge: {n_edge:,} px | Edge:Core ratio = {ratio:.3f}")

    print("\nEdge/Core separation complete.")


if __name__ == "__main__":
    main()
