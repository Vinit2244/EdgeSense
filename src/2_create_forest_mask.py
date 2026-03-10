# ============================================================
# Imports
# ============================================================
import numpy as np
import config as cfg
from pathlib import Path
import scipy.ndimage as ndimage
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
        
        # We need the raw TIFF to compute NDMI (B8A and B11)
        raw_tiff_path = Path(cfg.tiffs_dir) / f"{cfg.aoi_slug}_{year}.tif"

        if not ndvi_path.exists():
            print(f"NDVI file not found for {year}, skipping.")
            continue
            
        if not raw_tiff_path.exists():
            print(f"Raw TIFF not found for {year} at {raw_tiff_path}. Cannot compute NDMI, skipping.")
            continue

        # 1. Read NDVI GeoTIFF
        ndvi_image, meta = read_tif(ndvi_path)
        ndvi = ndvi_image[0].astype(np.float32)   

        # 2. Read Raw GeoTIFF and compute NDMI
        raw_image, _ = read_tif(raw_tiff_path)
        
        b8a = raw_image[cfg.narrow_nir_band_index].astype(np.float32)
        b11 = raw_image[cfg.swir_band_index].astype(np.float32)

        denom = b8a + b11
        ndmi = np.zeros_like(b8a, dtype=np.float32)
        
        valid_ndmi_pixels = denom != 0
        ndmi[valid_ndmi_pixels] = (b8a[valid_ndmi_pixels] - b11[valid_ndmi_pixels]) / denom[valid_ndmi_pixels]

        # 3. Identify valid pixels
        nodata_val = meta.get('nodata', -9999)
        valid_pixels = (ndvi != nodata_val) & (~np.isnan(ndvi))

        # 4. Compute Binary Forest Mask
        forest_mask = np.full(ndvi.shape, 255, dtype=np.uint8)
        
        is_forest = valid_pixels & (ndvi >= cfg.ndvi_threshold) & (ndmi >= cfg.ndmi_threshold)
        
        # Apply Base Logic
        forest_mask[valid_pixels] = 0
        forest_mask[is_forest] = 1

        if cfg.mask_type == "smooth_boundary":
            # Create a boolean array of just the forest pixels
            binary_forest = (forest_mask == 1)
            
            # Define a 3x3 structural element (adjust size for more/less aggressive smoothing)
            struct = np.ones((3, 3), dtype=bool)
            
            # Step A: Opening removes thin protrusions and isolated pixels
            smoothed_forest = ndimage.binary_opening(binary_forest, structure=struct)
            
            # Step B: Closing fills small holes and smooths inward boundaries
            smoothed_forest = ndimage.binary_closing(smoothed_forest, structure=struct)
            
            # Re-apply the smoothed mask, being careful to preserve 255 (NoData)
            forest_mask[valid_pixels] = 0
            forest_mask[valid_pixels & smoothed_forest] = 1

        # 5. Save the TIFF
        # Modify the filename so you can tell which method was used
        mask_out = Path(cfg.forest_mask_dir) / f"ForestMask_{cfg.aoi_slug}_{year}.tif"
        
        mask_meta = meta.copy()
        mask_meta.update({
            "dtype": "uint8",
            "nodata": 255
        })
        
        save_tif(forest_mask[np.newaxis, ...], mask_out, meta=mask_meta, nodata=255)
        print(f"  Saved mask : {mask_out.name}")

        # 6. Save Visualization
        vis_out = Path(cfg.visualisations_dir) / f"ForestMask_{cfg.aoi_slug}_{year}.png"
        
        visualise_bands(
            forest_mask[np.newaxis, ...],  
            out_path=vis_out,
            band_indices=[0],              
            nodata=255,                    
            percentile_stretch=(0, 100)    
        )
        print(f"  Saved visual : {vis_out.name}")

        # 7. Print Accurate Stats
        n_forest = int(np.sum(forest_mask == 1))
        n_valid  = int(np.sum(valid_pixels)) 
        pct      = (n_forest / n_valid * 100) if n_valid > 0 else 0
        print(f"  {year} → Forest pixels: {n_forest:,}  ({pct:.1f}% of district area)")

    print("\nForest masks saved.")

if __name__ == "__main__":
    main()
