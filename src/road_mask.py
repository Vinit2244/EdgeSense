# ============================================================
# Imports
# ============================================================
import sys
import numpy as np
from pathlib import Path

import requests
import rasterio
from rasterio.features import rasterize
from rasterio.warp import transform_bounds, transform_geom
from shapely.geometry import LineString, shape, mapping

sys.path.append(str(Path(__file__).resolve().parents[1]))
import config as cfg
from src.utils import read_tif, save_tif, visualise_bands


# ============================================================
# Overpass helpers
# ============================================================

# Public Overpass endpoints — tried in order, first success wins.
_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

_ROAD_TAGS = [
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified", "residential",
    "service", "track", "path",
    "footway", "cycleway",
]


def _build_overpass_query(south84, west84, north84, east84):
    """
    Build an Overpass QL query that fetches every highway way inside the bbox
    in a single request, returning JSON with full geometry.
    """
    bbox_str = f"{south84:.6f},{west84:.6f},{north84:.6f},{east84:.6f}"
    tag_union = "\n  ".join(
        f'way["highway"="{tag}"]({bbox_str});' for tag in _ROAD_TAGS
    )
    return f"""
[out:json][timeout:180];
(
  {tag_union}
);
out geom;
""".strip()


def _fetch_overpass(query):
    """
    POST the Overpass query to the first available public endpoint.
    Returns the parsed JSON dict or raises RuntimeError.
    """
    for url in _OVERPASS_ENDPOINTS:
        try:
            resp = requests.post(
                url,
                data={"data": query},
                timeout=240,
                headers={"Accept-Encoding": "gzip"},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            print(f"  [{url.split('/')[2]}] failed: {exc} — trying next endpoint.")

    raise RuntimeError("All Overpass endpoints failed. Check your internet connection.")


def _utm_epsg_from_bbox(south84, west84, north84, east84):
    """
    Derive the UTM zone EPSG code from the centroid of a WGS-84 bbox.
    Pure arithmetic — no pyproj needed.

    UTM zones are 6° wide, numbered 1-60 starting at 180°W.
    Northern hemisphere -> 326xx, southern -> 327xx.
    """
    lon_centre = (west84 + east84) / 2.0
    lat_centre = (south84 + north84) / 2.0
    zone   = int((lon_centre + 180) / 6) + 1        # 1 – 60
    prefix = 32600 if lat_centre >= 0 else 32700     # N / S hemisphere
    return f"EPSG:{prefix + zone}"


def _parse_ways_to_lines(overpass_json):
    """
    Convert Overpass JSON 'way' elements (with inline geometry) into a plain
    list of Shapely LineStrings in WGS-84 (EPSG:4326).

    Returns a list — deliberately not a GeoDataFrame so that no geopandas
    CRS machinery (which requires pyproj) is ever invoked.
    """
    lines = []
    for element in overpass_json.get("elements", []):
        if element.get("type") != "way":
            continue
        coords = [(n["lon"], n["lat"]) for n in element.get("geometry", [])]
        if len(coords) >= 2:
            lines.append(LineString(coords))
    return lines


def _buffer_and_reproject_roads(lines, metric_crs, raster_crs, buffer_m):
    """
    Buffer WGS-84 road LineStrings in a metric UTM CRS, then reproject the
    resulting polygons to raster_crs ready for rasterization.

    Uses rasterio.warp.transform_geom for every CRS conversion.
    This calls GDAL/PROJ directly — it does NOT import pyproj as a Python
    package, so it works correctly inside QGIS's bundled environment.

    Parameters
    ----------
    lines      : list[LineString]  Road centrelines in WGS-84.
    metric_crs : str               UTM EPSG string, e.g. "EPSG:32644".
    raster_crs : str               Raster CRS string, e.g. "EPSG:32644".
    buffer_m   : float             Buffer radius in metres.

    Returns
    -------
    list[Polygon]  Buffered road polygons in raster_crs.
    """
    buffered = []
    for line in lines:
        if line is None or line.is_empty:
            continue
        # Step 1: WGS-84 -> metric UTM (enables accurate metre buffering)
        geom_metric   = shape(transform_geom("EPSG:4326", metric_crs, mapping(line)))
        # Step 2: Buffer in metres
        geom_buffered = geom_metric.buffer(buffer_m)
        # Step 3: metric UTM -> raster CRS (aligns with the raster affine transform)
        geom_raster   = shape(transform_geom(metric_crs, raster_crs, mapping(geom_buffered)))
        buffered.append(geom_raster)
    return buffered


# ============================================================
# Plugin Function
# ============================================================
def compute_road_mask_plugin(forest_mask, meta, road_buffer_m):
    height     = meta["height"]
    width      = meta["width"]
    transform  = meta["transform"]
    raster_crs = str(meta["crs"])
    nodata_val = meta.get("nodata", 255)

    # ── Derive WGS-84 bbox for Overpass query ─────────────────────────
    west, south, east, north = rasterio.transform.array_bounds(
        height, width, transform
    )
    west84, south84, east84, north84 = transform_bounds(
        raster_crs, "EPSG:4326", west, south, east, north
    )

    print(f"  Querying Overpass API for bbox "
          f"(N={north84:.4f}, S={south84:.4f}, "
          f"E={east84:.4f}, W={west84:.4f}) ...")

    # ── Fetch roads from Overpass ─────────────────────────────────────
    query = _build_overpass_query(south84, west84, north84, east84)
    try:
        overpass_data = _fetch_overpass(query)
    except RuntimeError as exc:
        print(f"  ERROR: {exc}\n  Returning empty road mask.")
        road_mask = np.zeros((height, width), dtype=np.uint8)
        road_mask[forest_mask == nodata_val] = 255
        return road_mask

    # ── Parse Overpass response -> list of LineStrings ─────────────────
    lines = _parse_ways_to_lines(overpass_data)

    if not lines:
        print("  No roads found in OSM bbox — returning empty road mask.")
        road_mask = np.zeros((height, width), dtype=np.uint8)
        road_mask[forest_mask == nodata_val] = 255
        return road_mask

    print(f"  {len(lines):,} road segments fetched from OSM.")

    # ── Buffer in UTM, reproject to raster CRS, rasterize ────────────
    metric_crs = _utm_epsg_from_bbox(south84, west84, north84, east84)
    buffered = _buffer_and_reproject_roads(lines, metric_crs, raster_crs, road_buffer_m)

    road_mask = rasterize(
        shapes=((geom, 1) for geom in buffered if geom is not None and not geom.is_empty),
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype=np.uint8,
        all_touched=True,
    )

    # ── Clip to valid AOI pixels ──────────────────────────────────────
    valid_pixels = (forest_mask != nodata_val)
    road_mask[~valid_pixels] = 255

    n_road_px = int(np.sum(road_mask == 1))
    n_valid   = int(np.sum(valid_pixels))
    pct       = (n_road_px / n_valid * 100) if n_valid > 0 else 0
    print(f"  Road pixels: {n_road_px:,}  ({pct:.2f}% of district area)")

    return road_mask


# ============================================================
# Main (pipeline script entry point)
# ============================================================
def compute_road_mask(year, forest_mask_path):
    out_path = cfg.road_mask_dir / f"RoadMask_{cfg.aoi_slug}_{year}.tif"

    if out_path.exists():
        print(f"  Road mask already exists, re-using: {out_path.name}")
        return

    if not forest_mask_path.exists():
        print(f"  Forest mask not found for {year} — skipping road mask.")
        return

    # ── Read reference grid ───────────────────────────────────────────
    mask_image, meta = read_tif(forest_mask_path)
    forest_mask = mask_image[0]

    height     = meta["height"]
    width      = meta["width"]
    transform  = meta["transform"]
    raster_crs = str(meta["crs"])

    # ── WGS-84 bbox for Overpass ──────────────────────────────────────
    west, south, east, north = rasterio.transform.array_bounds(
        height, width, transform
    )
    west84, south84, east84, north84 = transform_bounds(
        raster_crs, "EPSG:4326", west, south, east, north
    )

    print(f"  Querying Overpass API for bbox "
          f"(N={north84:.4f}, S={south84:.4f}, "
          f"E={east84:.4f}, W={west84:.4f}) ...")

    query = _build_overpass_query(south84, west84, north84, east84)

    try:
        overpass_data = _fetch_overpass(query)
    except RuntimeError as exc:
        print(f"  ERROR: {exc}\n  Saving empty road mask for {year}.")
        road_mask = np.zeros((height, width), dtype=np.uint8)
        _save_road_mask(road_mask, forest_mask, meta, out_path)
        return

    # ── Parse -> LineStrings ───────────────────────────────────────────
    lines = _parse_ways_to_lines(overpass_data)

    if not lines:
        print(f"  No roads found in OSM bbox — saving empty mask.")
        road_mask = np.zeros((height, width), dtype=np.uint8)
        _save_road_mask(road_mask, forest_mask, meta, out_path)
        return

    print(f"  {len(lines):,} road segments fetched from OSM.")

    # ── Buffer in UTM, reproject to raster CRS, rasterize ────────────
    metric_crs = _utm_epsg_from_bbox(south84, west84, north84, east84)
    buffered   = _buffer_and_reproject_roads(lines, metric_crs, raster_crs, cfg.road_buffer_m)

    road_mask = rasterize(
        shapes=((geom, 1) for geom in buffered if geom is not None and not geom.is_empty),
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype=np.uint8,
        all_touched=True,
    )

    # ── Clip to valid AOI pixels ──────────────────────────────────────
    nodata_val   = meta.get("nodata", 255)
    valid_pixels = (forest_mask != nodata_val)
    road_mask[~valid_pixels] = 255

    _save_road_mask(road_mask, forest_mask, meta, out_path)


# ============================================================
# Private helpers
# ============================================================
def _save_road_mask(road_mask, forest_mask, meta, out_path):
    road_meta = meta.copy()
    road_meta.update({"count": 1, "dtype": "uint8", "nodata": 255})

    save_tif(road_mask[np.newaxis, ...], out_path, meta=road_meta, nodata=255)
    print(f"  Saved road mask : {out_path.name}")

    year_tag = out_path.stem.split("_")[-1]
    vis_out  = cfg.visualisations_dir / f"RoadMask_{cfg.aoi_slug}_{year_tag}.png"
    visualise_bands(
        road_mask[np.newaxis, ...],
        out_path=vis_out,
        band_indices=[0],
        nodata=255,
        percentile_stretch=(0, 100),
    )
    print(f"  Saved visual    : {vis_out.name}")

    n_road_px    = int(np.sum(road_mask == 1))
    valid_pixels = (forest_mask != road_meta["nodata"])
    n_valid      = int(np.sum(valid_pixels))
    pct          = (n_road_px / n_valid * 100) if n_valid > 0 else 0
    print(f"  Road pixels: {n_road_px:,}  ({pct:.2f}% of district area)")


if __name__ == "__main__":
    cfg.road_mask_dir.mkdir(parents=True, exist_ok=True)
    cfg.visualisations_dir.mkdir(parents=True, exist_ok=True)

    for year in cfg.years:
        forest_mask_path = cfg.forest_mask_dir / f"ForestMask_{cfg.aoi_slug}_{year}.tif"
        print(f"\nProcessing {year}...")
        compute_road_mask(year, forest_mask_path)

    print("\nRoad masks saved.")
