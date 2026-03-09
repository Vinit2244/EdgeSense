# ============================================================
# Imports
# ============================================================
import numpy as np
import config as cfg
from pathlib import Path
from utils import read_tif, save_tif, visualise_bands


# ============================================================
# Main
# ============================================================
def main():
    Path(cfg.forest_mask_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.visualisations_dir).mkdir(parents=True, exist_ok=True)

    for year in cfg.years:
        ndvi_path = Path(cfg.ndvi_dir) / f"NDVI_{cfg.village_slug}_{year}.tif"

        if not ndvi_path.exists():
            print(f"NDVI file not found for {year}, skipping.")
            continue

        # Read NDVI GeoTIFF
        ndvi_image, meta = read_tif(ndvi_path)
        ndvi = ndvi_image[0].astype(np.float32)   # (H, W) — single band

        # Compute Binary Forest Mask: 1 for forest-range pixels, 0 for non-forest
        forest_mask = np.where(ndvi >= cfg.ndvi_threshold, 1, 0).astype(np.uint8)

        mask_out = Path(cfg.forest_mask_dir) / f"ForestMask_{cfg.village_slug}_{year}.tif"
        save_tif(forest_mask, mask_out, meta=meta, nodata=None)
        print(f"  Saved mask : {mask_out.name}")

        # Visualise the forest mask
        vis_out = Path(cfg.visualisations_dir) / f"ForestMask_{cfg.village_slug}_{year}.png"
        visualise_bands(
            forest_mask[np.newaxis, ...],
            band_indices=[0],
            out_path=vis_out,
        )

        # Print stats
        n_forest = int(np.sum(forest_mask == 1))
        n_total  = forest_mask.size
        pct      = (n_forest / n_total * 100) if n_total > 0 else 0
        print(f"  {year} → Forest pixels: {n_forest:,}  ({pct:.1f}% of total image)")

    print("\nForest masks saved.")


if __name__ == "__main__":
    main()
