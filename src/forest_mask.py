# ============================================================
# Imports
# ============================================================
import numpy as np
import config as cfg
import scipy.ndimage as ndimage
from src.utils import visualise_bands, read_tif, save_tif


# ============================================================
# Main
# ============================================================
def compute_forest_mask(year, ndvi_path, ndmi_path):
    if not ndvi_path.exists() or not ndmi_path.exists():
        print(f"Files missing for {year}, skipping.")
        return

    # Read NDVI GeoTIFF
    ndvi_image, meta_ndvi = read_tif(ndvi_path)
    ndvi = ndvi_image[0].astype(np.float32)

    # Read NDMI GeoTIFF
    ndmi_image, _ = read_tif(ndmi_path)
    ndmi = ndmi_image[0].astype(np.float32)

    # Identify valid pixels
    nodata_val = meta_ndvi.get('nodata', -9999)
    valid_pixels = (ndvi != nodata_val) & (~np.isnan(ndvi))

    # Compute Binary Forest Mask
    forest_mask = np.full(ndvi.shape, 255, dtype=np.uint8)
    
    is_forest = valid_pixels & (ndvi >= cfg.ndvi_threshold) & (ndmi >= cfg.ndmi_threshold)
    
    # Apply Base Logic
    forest_mask[valid_pixels] = 0
    forest_mask[is_forest] = 1

    if cfg.mask_type == "smooth_boundary":
        # Create a boolean array of just the forest pixels
        binary_forest = (forest_mask == 1)

        # Define a structural element (adjust size for more/less aggressive smoothing)
        struct = np.ones((cfg.smooth_kernel_size, cfg.smooth_kernel_size), dtype=bool)
        
        # Step A: Opening removes thin protrusions and isolated pixels
        smoothed_forest = ndimage.binary_opening(binary_forest, structure=struct)
        
        # Step B: Closing fills small holes and smooths inward boundaries
        smoothed_forest = ndimage.binary_closing(smoothed_forest, structure=struct)
        
        # Re-apply the smoothed mask, being careful to preserve 255 (NoData)
        forest_mask[valid_pixels] = 0
        forest_mask[valid_pixels & smoothed_forest] = 1

    # Save the TIFF
    mask_meta = meta_ndvi.copy()
    mask_meta.update({
        "dtype": "uint8",
        "nodata": 255
    })
    
    mask_out = cfg.forest_mask_dir / f"ForestMask_{cfg.aoi_slug}_{year}.tif"
    save_tif(forest_mask[np.newaxis, ...], mask_out, meta=mask_meta, nodata=255)
    print(f"  Saved mask : {mask_out.name}")

    # Save Visualization
    vis_out = cfg.visualisations_dir / f"ForestMask_{cfg.aoi_slug}_{year}.png"
    
    visualise_bands(
        forest_mask[np.newaxis, ...],  
        out_path=vis_out,
        band_indices=[0],              
        nodata=255,                    
        percentile_stretch=(0, 100)    
    )
    print(f"  Saved visual : {vis_out.name}")

    # Print Stats
    n_forest = int(np.sum(forest_mask == 1))
    n_valid  = int(np.sum(valid_pixels)) 
    pct      = (n_forest / n_valid * 100) if n_valid > 0 else 0
    print(f"  {year} → Forest pixels: {n_forest:,}  ({pct:.1f}% of district area)")


if __name__ == "__main__":
    cfg.forest_mask_dir.mkdir(parents=True, exist_ok=True)
    cfg.visualisations_dir.mkdir(parents=True, exist_ok=True)

    for year in cfg.years:
        ndvi_path = cfg.ndvi_dir / f"NDVI_{cfg.aoi_slug}_{year}.tif"
        ndmi_path = cfg.ndmi_dir / f"NDMI_{cfg.aoi_slug}_{year}.tif"
        compute_forest_mask(year, ndvi_path, ndmi_path)

    print("\nForest masks saved.")
