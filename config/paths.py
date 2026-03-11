from pathlib import Path
from .constants import state

project_root = Path(__file__).resolve().parents[1]
input_dir    = project_root / 'input'

# Village-level: state-specific shapefile
villages_shapefile = input_dir / state / f"{state}.shp"

# District / Sub-district / State-level: India-wide boundary folder
india_boundaries_dir = input_dir / 'State_District_Sub-district_Boundary_of_entire_India'

# Maps aoi_level -> shapefile path within india_boundaries_dir
INDIA_BOUNDARY_SHAPEFILES = {
    "district":    india_boundaries_dir / "District Boundary.shp",
    "subdistrict": india_boundaries_dir / "Sub-district Boundary.shp",
    "state":       india_boundaries_dir / "State Boundary.shp",
}

tiffs_dir          = input_dir / 'tiffs'
output_dir         = project_root / 'output'
ndvi_dir           = output_dir / 'ndvi'
ndmi_dir           = output_dir / 'ndmi'
rgb_dir            = output_dir / 'rgb'
plots_dir          = output_dir / 'plots'
visualisations_dir = output_dir / 'visualisations'
forest_mask_dir    = output_dir / 'forest_mask'
edge_core_mask_dir = output_dir / 'edge_core'
metrics_dir        = output_dir / 'fragmentation_metrics'
