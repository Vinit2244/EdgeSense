# ============================================================
# Imports
# ============================================================
import numpy as np
import config as cfg
from pathlib import Path
from utils import read_tif, save_tif, visualise_bands


# ============================================================
# Helper Functions
# ============================================================
def inspect_tif(tif_path):
    image, meta = read_tif(tif_path)
    print(f"  File     : {Path(tif_path).name}")
    print(f"  CRS      : {meta['crs']}")
    print(f"  Bands    : {meta['count']}")
    print(f"  Shape    : {meta['height']} x {meta['width']} pixels")
    print(f"  Res      : {meta['transform'].a:.1f}m x {abs(meta['transform'].e):.1f}m")
    for i, band in enumerate(image, start=1):
        band_f = band.astype(np.float32)
        valid = band_f[band_f > 0]
        if len(valid) > 0:
            print(f"  Band {i:<4}: min={valid.min():.0f}  mean={valid.mean():.0f}  max={valid.max():.0f}")


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
# Main
# ============================================================
def main():
    # Ensure all output directories exist
    Path(cfg.ndvi_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.ndmi_dir).mkdir(parents=True, exist_ok=True)  # <-- Make sure to add ndmi_dir to config.py
    Path(cfg.visualisations_dir).mkdir(parents=True, exist_ok=True)

    for year in cfg.years:
        print(f"\nProcessing {year}...")

        tif_files = list(Path(cfg.tiffs_dir).glob(f"{cfg.aoi_slug}_{year}*.tif"))
        if not tif_files:
            print(f"  No TIF found for {year} — check filename.")
            continue

        # Read input tif
        image, meta = read_tif(tif_files[0])
        red_idx        = cfg.red_band_index
        nir_idx        = cfg.nir_band_index
        narrow_nir_idx = cfg.narrow_nir_band_index
        swir_idx       = cfg.swir_band_index

        # Safely extract the NoData value (fallback to 0 if missing)
        nodata_val = meta.get('nodata', 0)

        # --------------------------------------------------------
        # Compute and Save NDVI
        # --------------------------------------------------------
        ndvi = compute_ndvi(image, red_idx, nir_idx, nodata_val)
        ndvi_out  = Path(cfg.ndvi_dir) / f"NDVI_{cfg.aoi_slug}_{year}.tif"
        ndvi_save = np.where(np.isnan(ndvi), -9999, ndvi).astype(np.float32)
        save_tif(ndvi_save, ndvi_out, meta=meta, nodata=-9999)
        print(f"  Saved NDVI : {ndvi_out.name}")

        valid_ndvi = ndvi[~np.isnan(ndvi)]
        print(f"  NDVI Stats → Min: {valid_ndvi.min():.3f} | Mean: {valid_ndvi.mean():.3f} | Max: {valid_ndvi.max():.3f}")

        # --------------------------------------------------------
        # Compute and Save NDMI
        # --------------------------------------------------------
        ndmi = compute_ndmi(image, narrow_nir_idx, swir_idx, nodata_val)
        ndmi_out  = Path(cfg.ndmi_dir) / f"NDMI_{cfg.aoi_slug}_{year}.tif"
        ndmi_save = np.where(np.isnan(ndmi), -9999, ndmi).astype(np.float32)
        save_tif(ndmi_save, ndmi_out, meta=meta, nodata=-9999)
        print(f"  Saved NDMI : {ndmi_out.name}")

        valid_ndmi = ndmi[~np.isnan(ndmi)]
        print(f"  NDMI Stats → Min: {valid_ndmi.min():.3f} | Mean: {valid_ndmi.mean():.3f} | Max: {valid_ndmi.max():.3f}")

        # --------------------------------------------------------
        # Visualisations
        # --------------------------------------------------------
        # NDVI - green
        ndvi_vis_out = Path(cfg.visualisations_dir) / f"NDVI_{cfg.aoi_slug}_{year}.png"

        ndvi_rgb = np.zeros((3, ndvi_save.shape[0], ndvi_save.shape[1]), dtype=np.float32)
        ndvi_rgb[1] = ndvi_save  # G channel

        visualise_bands(
            ndvi_rgb,
            out_path=ndvi_vis_out,
            band_indices=[0,1,2],
            nodata=-9999,
            percentile_stretch=(2, 98)
        )

        # NDMI - blue
        ndmi_vis_out = Path(cfg.visualisations_dir) / f"NDMI_{cfg.aoi_slug}_{year}.png"

        ndmi_rgb = np.zeros((3, ndmi_save.shape[0], ndmi_save.shape[1]), dtype=np.float32)
        ndmi_rgb[2] = ndmi_save  # B channel

        visualise_bands(
            ndmi_rgb,
            out_path=ndmi_vis_out,
            band_indices=[0,1,2],
            nodata=-9999,
            percentile_stretch=(2, 98)
        )

        # FCC Visualization
        fcc_out = Path(cfg.visualisations_dir) / f"FCC_{cfg.aoi_slug}_{year}.png"

        visualise_bands(
            image,
            out_path=fcc_out,
            band_indices=[nir_idx, red_idx, swir_idx],
            nodata=nodata_val
        )
        print(f"  Saved Visualisations to {cfg.visualisations_dir.name}/")

    print("\nIndices computation complete.")


if __name__ == "__main__":
    main()
