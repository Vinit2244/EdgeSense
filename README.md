# EdgeSense
### Forest Edge Pressure & Fragmentation Analysis

> *Do increasing edge-to-core ratios amplify ecological stress signals within forest patches?*

---

## Team WFH

| Name | Roll Number |
|---|---|
| Medha Prasad | 2022101034 |
| Pearl Shah | 2022102073 |
| Vinit Mehta | 2022111001 |
| Naveen Kumar G | 2023702016 |

---

## Overview

Forest ecosystems are increasingly fragmented by anthropogenic pressures. As patches shrink and break apart, the **edge-to-core ratio** rises — exposing larger portions of forest to external stressors:

- Deforestation and logging
- Urban and agricultural encroachment
- Climate variability and microclimate disruption

EdgeSense quantifies this fragmentation over time using multi-year Sentinel-2 satellite imagery, computing NDVI-based forest masks, edge/core classifications, and patch-level fragmentation metrics for any village-level AOI in India.

---

## Hypothesis

Forest edges experience higher ecological stress than interior (core) areas due to increased exposure and human interference. Specifically:

- Higher edge-to-core ratios correlate with stronger ecological stress signals.
- Smaller, fragmented patches exhibit disproportionately greater edge effects than large continuous ones.

---

## Setup

### 1. Create and activate a virtual environment

```bash
python3 -m venv edgesense
source ./edgesense/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Data Download

### 1. Get the village boundary shapefile

Download the village boundary `.zip` for your state from the [Survey of India portal](https://surveyofindia.gov.in/pages/village-boundary-data-base-of-entire-india) and State/District/Sub-district boundaries from [Download link State_District_Sub-district_Boundary_of_entire_India](https://surveyofindia.gov.in/documents/State_District_Sub-district_Boundary_of_entire_India.zip), unzip it, and place the folder inside `input/` folder.

### 2. Configure your AOI

Open `src/config.py` and update the state name, village name, and any other relevant parameters.

### 3. Authenticate Earth Engine

```bash
export SSL_CERT_FILE=$(python -m certifi)
earthengine authenticate
```

### 4. Download Sentinel-2 imagery

> Run from inside the `src/` directory.

```bash
python download_aoi_tif.py
```

This fetches a 13-band Sentinel-2 median composite for each configured year and saves:
- **13-band GeoTIFF** → `input/tiffs/`
- **RGB visualisation PNG** → `output/visualisations/`

---

## Running the Pipeline

> Run from inside the `src/` directory.

```bash
chmod +x run_pipeline.sh
./run_pipeline.sh
```

The pipeline runs the following stages in sequence:

| Step | Script | Output |
|---|---|---|
| 1 | `compute_ndvi.py` | Per-year NDVI GeoTIFFs + FCC visualisations |
| 2 | `create_forest_mask.py` | Binary forest masks (NDVI ≥ threshold) |
| 3 | `edge_core_separation.py` | Edge/Core encoded rasters |
| 4 | `fragmentation_metrics.py` | Per-year CSVs + multi-year summary |
| 5 | `change_analysis.py` | Plots visualisations for fragmentation metrics |

---

## License

[MIT License](./LICENSE)
