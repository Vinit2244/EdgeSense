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

## Results

All outputs and results can be found on this [google drive link](https://drive.google.com/drive/folders/1RSsDQbVAdNWlzGFQHG2kKv7PG377L_Nn?usp=sharing).

---

## Setup Environment

1. Install uv: [uv intallation guide](https://docs.astral.sh/uv/getting-started/installation/)
2. Setup env: `uv sync`
3. Activate env: `source .venv/bin/activate`

---

## Data Download

### 1. Get the village boundary shapefile

Download the village boundary `.zip` for your state from the [Survey of India portal](https://surveyofindia.gov.in/pages/village-boundary-data-base-of-entire-india) and State/District/Sub-district boundaries from [Download link State_District_Sub-district_Boundary_of_entire_India](https://surveyofindia.gov.in/documents/State_District_Sub-district_Boundary_of_entire_India.zip), unzip it, and place the folder inside `input/` folder.

### 2. Configure your AOI

Open `config/constants.py` and update the state name, village name, and any other relevant parameters.

### 3. Authenticate Earth Engine

```bash
export SSL_CERT_FILE=$(python -m certifi)
earthengine authenticate
```

### 4. Download Sentinel-2 imagery

```bash
uv run python tools/download_aoi_tif.py
```

This fetches a multi-band Sentinel-2 median composite for each configured year and saves:

- **Multiband-band GeoTIFF** -> `input/tiffs/`
- **RGB visualisation PNG** -> `output/visualisations/`

---

## Plugin

### Plugin Setup (Linux & MacOS)

1. Clone this repository `git clone https://github.com/Vinit2244/EdgeSense.git`
2. Open your QGIS -> Go to `Settings` -> `User Profiles` -> `Open active profile folder` -> Copy the path to this directory and update the variable `active_profile_folder_path` in `config/paths.py` file and modify the `TARGET_DIR` variable in `scripts/copy_files.sh`.
3. Run: `chmod +x scripts/copy_files.sh`
4. Then run the script to copy the necessary files into your plugins folder `./scripts/copy_files.sh`.

### Plugin Usage

<span style="color:red">Plese NOTE that the current version of this plugin only works with the data downloaded using the given tools/download_aoi_tif.py file as we have hardcoded the channels to download and their index in config/config.py file.</span>

1. Start QGIS
2. Go to `Plugins` -> `Manage and Install Plugins...` -> `All` -> Search for `EdgeSense` -> Make sure it is enabled (ticked)
3. Drag and drop your original multi-band .tif file into the QGIS -> Press on the EdgeSense icon: <img src="./logo.png" height=20>.
4. Set the values of the configurations and click on `Run Pipeline`.
5. To download any layer, select that layer and click on `Save active layer` option.

## Normal Pipeline Usage

### Setup

### Run the complete pipeline

```bash
chmod +x srcipts/run_pipeline.sh
./scripts/run_pipeline.sh
```

### Visualising Trends

```bash
uv run python tools/plot_fragmentation_trends.py
```

---

## License

[MIT License](./LICENSE)

## Caveats

* We are getting road masks but we don't have access to road masks for all years so we are just taking the current road mask and applying it to all the years throughout.
* Computation of fragmentation metrics requires edge-core mask, forest mask and road mask so if using the plugin make sure to download and save those before running the fragmentation metrics calculation code.



## Downloading a TIF from Google Earth Engine using EdgeSense Plugin

## Before you start
- EdgeSense plugin loaded in QGIS
- Your `.shp` shapefile ready
- Internet connection

---

## Step 1 — Load your shapefile
**Drag and drop** your `.shp` file onto the QGIS map canvas. The boundary polygons will appear on the map.

---

## Step 2 — Find the exact feature name
1. In the **Layers panel**, right-click your shapefile → **Open Attribute Table**
2. Find the column with place names (e.g. `DISTRICT`, `SUB_DIST`)
3. Note the **exact spelling** of your target area

---

## Step 3 — Select your area
1. Click **Edit → Select → Select Features by Expression**
2. Type your expression:
```
"COLUMN_NAME" = 'Exact Value'
```
Examples:
```
"DISTRICT" = 'Visakhapatnam'
"SUB_DIST" = 'RAMPA CHODAVARAM'
```
3. Click **Select Features** then close the dialog

You should see `1 matching feature(s) selected` at the bottom of QGIS and the polygon highlighted in yellow.

> If you see `0 matching features` — recheck spelling and column name in the attribute table.

---

## Step 4 — Set output directory
In the EdgeSense panel, click **Browse** next to Output Directory and choose a folder.

> The Download button stays greyed out until this is done.

---

## Step 5 — Connect the shapefile
In the **AOI & DOWNLOAD** section of the panel:
- If your shapefile name already appears in the dropdown → skip to Step 6
- If it's empty → click the **↺ refresh button**

---

## Step 6 — Download the TIF
1. Set the **Analysis Year** at the top of the panel
2. Click **⬇ Download TIF from GEE**
3. Watch the footer for progress — download takes **1–5 minutes**

When complete, the TIF auto-loads into QGIS as a new layer.

---

## Step 7 — Run the Pipeline
With the downloaded TIF as the active layer, click **Run Pipeline**.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Download button greyed out | Set output directory, then click ↺ refresh |
| 0 matching features | Copy value exactly from attribute table |
| GEE error | Check **Python error** tab in Log Messages panel |
| Missing module on startup | Run `pip_main(['install', 'earthengine-api', 'geopandas', 'shapely'])` in QGIS Python Console |
