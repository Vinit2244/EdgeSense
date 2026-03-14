# ============================================================
# Imports
# ============================================================
import sys
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
import config as cfg
from src.utils import read_tif, save_tif, visualise_bands


# ============================================================
# Helper Functions
# ============================================================
def compute_ndvi(image, red_idx, nir_idx, nodata_val):
    red = image[red_idx].astype(np.float32) / 10000.0
    nir = image[nir_idx].astype(np.float32) / 10000.0

    # Strictly mask based on the raster's official NoData value
    nodata_mask = (image[red_idx] == nodata_val) | (image[nir_idx] == nodata_val)

    ndvi = (nir - red) / (nir + red + 1e-10)
    ndvi = np.clip(ndvi, -1, 1)
    
    # Apply NaN to pixels outside the district
    ndvi[nodata_mask] = np.nan

    return ndvi


def compute_ndmi(image, narrow_nir_idx, swir_idx, nodata_val):
    narrow_nir = image[narrow_nir_idx].astype(np.float32) / 10000.0
    swir = image[swir_idx].astype(np.float32) / 10000.0

    # Strictly mask based on the raster's official NoData value
    nodata_mask = (image[narrow_nir_idx] == nodata_val) | (image[swir_idx] == nodata_val)

    ndmi = (narrow_nir - swir) / (narrow_nir + swir + 1e-10)
    ndmi = np.clip(ndmi, -1, 1)
    
    # Apply NaN to pixels outside the district
    ndmi[nodata_mask] = np.nan

    return ndmi


# ============================================================
# Plugin Functions
# ============================================================
def compute_spectral_indices_plugin(image):
    red = image[cfg.red_band_index].astype(np.float32) / 10000
    nir = image[cfg.nir_band_index].astype(np.float32) / 10000
    swir = image[cfg.swir_band_index].astype(np.float32) / 10000
    narrow_nir = image[cfg.narrow_nir_band_index].astype(np.float32) / 10000

    ndvi = (nir - red) / (nir + red + 1e-10)
    ndmi = (narrow_nir - swir) / (narrow_nir + swir + 1e-10)

    return ndvi, ndmi


# ============================================================
# Main
# ============================================================
def compute_spectral_indices(year, tif_files):
    print(f"\nProcessing {year}...")
    
    if not tif_files:
        print(f"  No TIF found for {year} — check filename.")
        return
    
    # Read input tif
    image, meta = read_tif(tif_files[0])
    red_idx        = cfg.red_band_index
    nir_idx        = cfg.nir_band_index
    narrow_nir_idx = cfg.narrow_nir_band_index
    swir_idx       = cfg.swir_band_index

    # Safely extract the NoData value (fallback to 0 if missing)
    nodata_val = meta.get('nodata', 0)


    # Compute and Save NDVI
    ndvi = compute_ndvi(image, red_idx, nir_idx, nodata_val)
    ndvi_out  = cfg.ndvi_dir / f"NDVI_{cfg.aoi_slug}_{year}.tif"
    ndvi_save = np.where(np.isnan(ndvi), -9999, ndvi).astype(np.float32)
    save_tif(ndvi_save, ndvi_out, meta=meta, nodata=-9999)
    print(f"  Saved NDVI : {ndvi_out.name}")

    valid_ndvi = ndvi[~np.isnan(ndvi)]
    print(f"  NDVI Stats -> Min: {valid_ndvi.min():.3f} | Mean: {valid_ndvi.mean():.3f} | Max: {valid_ndvi.max():.3f}")


    # Compute and Save NDMI
    ndmi = compute_ndmi(image, narrow_nir_idx, swir_idx, nodata_val)
    ndmi_out  = cfg.ndmi_dir / f"NDMI_{cfg.aoi_slug}_{year}.tif"
    ndmi_save = np.where(np.isnan(ndmi), -9999, ndmi).astype(np.float32)
    save_tif(ndmi_save, ndmi_out, meta=meta, nodata=-9999)
    print(f"  Saved NDMI : {ndmi_out.name}")

    valid_ndmi = ndmi[~np.isnan(ndmi)]
    print(f"  NDMI Stats -> Min: {valid_ndmi.min():.3f} | Mean: {valid_ndmi.mean():.3f} | Max: {valid_ndmi.max():.3f}")


    # Visualise NDVI - green
    ndvi_vis_out = cfg.visualisations_dir / f"NDVI_{cfg.aoi_slug}_{year}.png"

    ndvi_rgb = np.zeros((3, ndvi_save.shape[0], ndvi_save.shape[1]), dtype=np.float32)
    ndvi_rgb[1] = ndvi_save  # G channel

    visualise_bands(
        ndvi_rgb,
        out_path=ndvi_vis_out,
        band_indices=[0,1,2],
        nodata=-9999,
        percentile_stretch=(2, 98)
    )


    # Visualise NDMI - blue
    ndmi_vis_out = cfg.visualisations_dir / f"NDMI_{cfg.aoi_slug}_{year}.png"

    ndmi_rgb = np.zeros((3, ndmi_save.shape[0], ndmi_save.shape[1]), dtype=np.float32)
    ndmi_rgb[2] = ndmi_save  # B channel

    visualise_bands(
        ndmi_rgb,
        out_path=ndmi_vis_out,
        band_indices=[0,1,2],
        nodata=-9999,
        percentile_stretch=(2, 98)
    )


    # Visualise FCC - NIR (R), Red (G), SWIR (B)
    fcc_out = cfg.visualisations_dir / f"FCC_{cfg.aoi_slug}_{year}.png"

    visualise_bands(
        image,
        out_path=fcc_out,
        band_indices=[nir_idx, red_idx, swir_idx],
        nodata=nodata_val
    )
    print(f"  Saved Visualisations to {cfg.visualisations_dir.name}/")


if __name__ == "__main__":
    cfg.ndvi_dir.mkdir(parents=True, exist_ok=True)
    cfg.ndmi_dir.mkdir(parents=True, exist_ok=True)
    cfg.visualisations_dir.mkdir(parents=True, exist_ok=True)

    for year in cfg.years:
        tif_files = list(cfg.tiffs_dir.glob(f"{cfg.aoi_slug}_{year}*.tif"))
        compute_spectral_indices(year, tif_files)

    print("\nIndices computation complete.")
