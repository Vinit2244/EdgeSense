# ============================================================
# Imports
# ============================================================
import numpy as np
import config as cfg
from pathlib import Path
from utils import visualise_bands
from utils import read_tif, save_tif


# ============================================================
# Main
# ============================================================
def main():
    Path(cfg.forest_mask_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.visualisations_dir).mkdir(parents=True, exist_ok=True)

    for year in cfg.years:
        ndvi_path = Path(cfg.ndvi_dir) / f"NDVI_{cfg.aoi_slug}_{year}.tif"

        if not ndvi_path.exists():
            print(f"NDVI file not found for {year}, skipping.")
            continue

        # Read NDVI GeoTIFF
        ndvi_image, meta = read_tif(ndvi_path)
        ndvi = ndvi_image[0].astype(np.float32)   # (H, W) — single band

        # 1. Identify valid pixels (ignoring our -9999 NoData value from the NDVI step)
        nodata_val = meta.get('nodata', -9999)
        valid_pixels = (ndvi != nodata_val) & (~np.isnan(ndvi))

        # 2. Compute Binary Forest Mask (0 = Non-forest, 1 = Forest, 255 = NoData)
        # We start by filling the entire array with 255 (our new NoData value)
        forest_mask = np.full(ndvi.shape, 255, dtype=np.uint8)
        
        # Apply logic ONLY to valid pixels inside the district boundary
        forest_mask[valid_pixels & (ndvi >= cfg.ndvi_threshold)] = 1
        forest_mask[valid_pixels & (ndvi < cfg.ndvi_threshold)] = 0

        # 3. Save the TIFF
        mask_out = Path(cfg.forest_mask_dir) / f"ForestMask_{cfg.aoi_slug}_{year}.tif"
        
        # Update metadata for an 8-bit integer mask
        mask_meta = meta.copy()
        mask_meta.update({
            "dtype": "uint8",
            "nodata": 255
        })
        
        # save_tif usually expects a shape of (bands, H, W)
        save_tif(forest_mask[np.newaxis, ...], mask_out, meta=mask_meta, nodata=255)
        print(f"  Saved mask : {mask_out.name}")

        # 4. Save a transparent, colored PNG for visualization
        vis_out = Path(cfg.visualisations_dir) / f"ForestMask_{cfg.aoi_slug}_{year}.png"
        
        visualise_bands(
            forest_mask[np.newaxis, ...],  # Add band dimension: (1, H, W)
            out_path=vis_out,
            band_indices=[0],              # 1 index triggers Grayscale mode ("LA")
            nodata=255,                    # Tell the function to mask 255
            percentile_stretch=(0, 100)    # Prevents clipping 0s and 1s
        )
        print(f"  Saved visual : {vis_out.name}")

        # 5. Print Accurate Stats (excluding out-of-bounds pixels)
        n_forest = int(np.sum(forest_mask == 1))
        n_valid  = int(np.sum(valid_pixels)) # ONLY counting pixels inside the district
        pct      = (n_forest / n_valid * 100) if n_valid > 0 else 0
        print(f"  {year} → Forest pixels: {n_forest:,}  ({pct:.1f}% of district area)")

    print("\nForest masks saved.")


if __name__ == "__main__":
    main()