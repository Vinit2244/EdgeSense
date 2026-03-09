# ============================================================
# Imports
# ============================================================
import numpy as np
import config as cfg
from pathlib import Path
from scipy.ndimage import binary_erosion
from utils import read_tif, save_tif, visualise_bands


# ============================================================
# Main
# ============================================================
def main():
    Path(cfg.edge_core_mask_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.visualisations_dir).mkdir(parents=True, exist_ok=True)

    # Structuring element for erosion (square kernel)
    struct = np.ones((cfg.edge_pixels * 2 + 1, cfg.edge_pixels * 2 + 1), dtype=bool)

    for year in cfg.years:
        mask_path = Path(cfg.forest_mask_dir) / f"ForestMask_{cfg.village_slug}_{year}.tif"

        if not mask_path.exists():
            print(f"Mask not found for {year}, skipping.")
            continue

        # Read forest mask
        mask_image, meta = read_tif(mask_path)
        mask = mask_image[0]                        # (H, W) uint8

        forest = (mask == 1)                        # boolean array
        non_forest = (mask == 0)                    # boolean array

        # Compute core & edge (using erosion)
        core = binary_erosion(forest, structure=struct)
        edge = forest & ~core

        # Encode as 3-channel mask: (3, H, W)
        # Channel 0 (Red): Edge | Channel 1 (Green): Core | Channel 2 (Blue): Non-Forest
        result = np.zeros((3, mask.shape[0], mask.shape[1]), dtype=np.uint8)
        
        result[0, edge]       = 1
        result[1, core]       = 1
        result[2, non_forest] = 1

        # Preserve NoData (255) across all three channels
        nodata_mask = (mask == 255)
        result[0, nodata_mask] = 255
        result[1, nodata_mask] = 255
        result[2, nodata_mask] = 255

        # Save Edge/Core GeoTIFF
        out_path = cfg.edge_core_mask_dir / f"EdgeCoreMask_{cfg.village_slug}_{year}.tif"
        save_tif(result, out_path, meta=meta, nodata=255)
        print(f"  Saved EdgeCore : {out_path.name}")

        # Visualise Edge/Core map
        # Now automatically maps to RGB:
        #   Red   = Edge
        #   Green = Core
        #   Blue  = Non-Forest
        vis_out = Path(cfg.visualisations_dir) / f"EdgeCoreMask_{cfg.village_slug}_{year}.png"
        visualise_bands(
            result,                             # Already (3, H, W)
            vis_out,
            band_indices=[0, 1, 2],             # Explicitly call RGB mapping
            nodata=255,
            percentile_stretch=(0, 100),        # No clipping — keep discrete levels
        )

        # Print stats
        n_core = int(np.sum(core))
        n_edge = int(np.sum(edge))
        ratio  = (n_edge / n_core) if n_core > 0 else float('inf')
        print(f"  {year} → Core: {n_core:,} px | Edge: {n_edge:,} px | Edge:Core ratio = {ratio:.3f}")

    print("\nEdge/Core separation complete.")


if __name__ == "__main__":
    main()
