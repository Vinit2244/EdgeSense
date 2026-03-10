import rasterio
import numpy as np
from pathlib import Path


_UNSET = object()


def read_tif(tif_path):
    tif_path = Path(tif_path)
    if not tif_path.exists():
        raise FileNotFoundError(f"TIF file not found: {tif_path}")

    with rasterio.open(tif_path) as src:
        image = src.read()           # (bands, height, width) — always 3D
        meta  = src.meta.copy()      # CRS, transform, dtype, nodata, count, etc.

    return image, meta


def save_tif(image, out_path, meta, *, crs=None, transform=None, nodata=None) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Normalise to 3-D: (bands, H, W)
    if image.ndim == 2:
        image = image[np.newaxis, ...]          # (1, H, W)
    elif image.ndim != 3:
        raise ValueError(f"image must be 2-D or 3-D, got shape {image.shape}")

    bands, height, width = image.shape

    # Metadata
    base_meta = {
        "driver": "GTiff",
        "dtype":  image.dtype.name,
        "width":  width,
        "height": height,
        "count":  bands,
    }

    if meta is not None:
        # Merge: caller's meta wins over base defaults
        base_meta.update(meta)

    # Keyword overrides (explicit args beat everything)
    base_meta["dtype"]  = image.dtype.name   # always match the actual array dtype
    base_meta["count"]  = bands              # always match the actual band count
    base_meta["width"]  = width
    base_meta["height"] = height

    if crs is not None:
        base_meta["crs"] = crs
    if transform is not None:
        base_meta["transform"] = transform
    if nodata is not _UNSET:           # ← triggers for both None and a real value
        base_meta["nodata"] = nodata

    # Write
    with rasterio.open(out_path, "w", **base_meta) as dst:
        dst.write(image)

    return out_path


def visualise_bands(image, out_path, band_indices=None, *, percentile_stretch=(2, 98), nodata=None):
    from PIL import Image as PILImage

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if image.ndim != 3:
        raise ValueError(f"image must be 3-D (bands, H, W), got shape {image.shape}")

    n_bands = image.shape[0]

    if n_bands == 1:
        selected = [0]
        mode = "L"
    elif n_bands == 3 and band_indices is None:
        selected = [0, 1, 2]
        mode = "RGB"
    else:
        if band_indices is None:
            raise ValueError(
                f"Image has {n_bands} bands — band_indices is required. "
                "Pass 1 index for greyscale or 3 indices for RGB."
            )

        n_sel = len(band_indices)
        if n_sel not in (1, 3):
            raise ValueError(f"band_indices must have 1 (greyscale) or 3 (RGB) elements, got {n_sel}.")

        max_idx = n_bands - 1
        for idx in band_indices:
            if not (0 <= idx <= max_idx):
                raise ValueError(f"Band index {idx} out of range for image with {n_bands} bands.")

        selected = list(band_indices)
        mode = "L" if n_sel == 1 else "RGB"

    # ==========================================================
    # 1. Build a Universal NoData Mask for Selected Bands
    # ==========================================================
    _, H, W = image.shape
    global_mask = np.zeros((H, W), dtype=bool)
    
    for idx in selected:
        band = image[idx].astype(np.float32)
        
        # Handle both specific nodata values and NaN
        if nodata is not None:
            if np.isnan(nodata):
                band_mask = np.isnan(band)
            else:
                band_mask = (band == nodata)
        else:
            band_mask = np.zeros((H, W), dtype=bool)
            
        # Also flag infinite/NaN values automatically
        band_mask |= ~np.isfinite(band)
        
        # Combine with the global mask
        global_mask |= band_mask

    # ==========================================================
    # 2. Stretch Function (now uses the global mask)
    # ==========================================================
    def stretch_to_uint8(band: np.ndarray) -> np.ndarray:
        band = band.astype(np.float32)

        # Only calculate stretch percentiles on valid pixels
        valid = band[~global_mask]
        if valid.size == 0:
            return np.zeros(band.shape, dtype=np.uint8)

        lo, hi = np.percentile(valid, percentile_stretch)

        if hi == lo:
            stretched = np.zeros_like(band)
        else:
            stretched = np.clip((band - lo) / (hi - lo), 0, 1)

        out = (stretched * 255).astype(np.uint8)
        
        # Black out the RGB/L channels where NoData exists 
        # (Alpha channel will handle the actual transparency)
        out[global_mask] = 0 
        return out

    # ==========================================================
    # 3. Create Alpha Channel and Stack
    # ==========================================================
    # 0 = Transparent (NoData), 255 = Opaque (Valid Data)
    alpha = np.where(global_mask, 0, 255).astype(np.uint8)

    if mode == "L":
        canvas_l = stretch_to_uint8(image[selected[0]])           
        canvas = np.stack([canvas_l, alpha], axis=-1)               # (H, W, 2)
        out_mode = "LA"                                             # Luma + Alpha
    else:
        canvas_r = stretch_to_uint8(image[selected[0]])
        canvas_g = stretch_to_uint8(image[selected[1]])
        canvas_b = stretch_to_uint8(image[selected[2]])
        canvas = np.stack([canvas_r, canvas_g, canvas_b, alpha], axis=-1) # (H, W, 4)
        out_mode = "RGBA"                                           # Red Green Blue + Alpha

    PILImage.fromarray(canvas, mode=out_mode).save(out_path, format="PNG")
    return out_path
