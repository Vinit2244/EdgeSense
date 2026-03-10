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


# ============================================================
# Main
# ============================================================
def main():
    Path(cfg.ndvi_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.visualisations_dir).mkdir(parents=True, exist_ok=True)

    for year in cfg.years:
        print(f"\nProcessing {year}...")

        tif_files = list(Path(cfg.tiffs_dir).glob(f"{cfg.aoi_slug}_{year}*.tif"))
        if not tif_files:
            print(f"  No TIF found for {year} — check filename.")
            continue

        # Read input tif
        image, meta = read_tif(tif_files[0])
        red_idx  = cfg.red_band_index
        nir_idx  = cfg.nir_band_index
        swir_idx = cfg.swir_band_index

        # NEW: Safely extract the NoData value (fallback to 0 if missing)
        nodata_val = meta.get('nodata', 0)

        # Compute and save NDVI
        ndvi = compute_ndvi(image, red_idx, nir_idx, nodata_val)

        # Replace NaN with -9999 sentinel for the saved file
        ndvi_out  = Path(cfg.ndvi_dir) / f"NDVI_{cfg.aoi_slug}_{year}.tif"
        ndvi_save = np.where(np.isnan(ndvi), -9999, ndvi).astype(np.float32)
        save_tif(ndvi_save, ndvi_out, meta=meta, nodata=-9999)
        print(f"  Saved NDVI : {ndvi_out.name}")

        valid = ndvi[~np.isnan(ndvi)]
        print(f"  Stats → Min: {valid.min():.3f} | Mean: {valid.mean():.3f} | Max: {valid.max():.3f}")
        print(f"  Forest-range pixels (NDVI ≥ {cfg.ndvi_threshold}): {np.sum(valid >= cfg.ndvi_threshold):,} / {len(valid):,}")

        # FCC visualisation (NIR, Red, SWIR)
        fcc_out = Path(cfg.visualisations_dir) / f"FCC_{cfg.aoi_slug}_{year}.png"
        visualise_bands(
            image,
            out_path=fcc_out,
            band_indices=[nir_idx, red_idx, swir_idx],
            nodata=nodata_val
        )

    print("\nNDVI computation complete.")


if __name__ == "__main__":
    main()
