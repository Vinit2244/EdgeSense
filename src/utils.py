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

    # Stretch selected bands to uint8 with percentile clipping
    def stretch_to_uint8(band: np.ndarray) -> np.ndarray:
        band = band.astype(np.float32)

        mask = (band == nodata) if nodata is not None else np.zeros(band.shape, dtype=bool)
        mask |= ~np.isfinite(band)

        valid = band[~mask]
        if valid.size == 0:
            return np.zeros(band.shape, dtype=np.uint8)

        lo, hi = np.percentile(valid, percentile_stretch)

        if hi == lo:
            stretched = np.zeros_like(band)
        else:
            stretched = np.clip((band - lo) / (hi - lo), 0, 1)

        out = (stretched * 255).astype(np.uint8)
        out[mask] = 0
        return out

    # Visualise
    if mode == "L":
        canvas = stretch_to_uint8(image[selected[0]])           # (H, W)
    else:
        canvas = np.stack(
            [stretch_to_uint8(image[i]) for i in selected],
            axis=-1,                                            # (H, W, 3)
        )

    PILImage.fromarray(canvas, mode=mode).save(out_path, format="PNG")
    return out_path
