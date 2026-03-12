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
python -m tools.download_aoi_tif
```

This fetches a multi-band Sentinel-2 median composite for each configured year and saves:

- **Multiband-band GeoTIFF** -> `input/tiffs/`
- **RGB visualisation PNG** -> `output/visualisations/`

---

## Plugin

### Plugin Setup (Linux & MacOS)

1. Clone this repository `git clone https://github.com/Vinit2244/EdgeSense.git`
2. Open your QGIS -> Go to `Settings` -> `User Profiles` -> `Open active profile folder` -> Copy the path to this directory and update the variable `active_profile_folder_path` in `config/constant.py` file and `TARGET_DIR` variable in `scripts/copy_files.sh` file.
3. Run: `chmod +x scripts/copy_files.sh`
4. Then run the script to copy the necessary files into your plugins folder `./scripts/copy_files.sh`.

### Plugin Usage

<span style="color:red">Plese NOTE that the current version of this plugin only works with the data downloaded using the given tools/download_aoi_tif.py file as we have hardcoded the channels to download and their index in config/config.py file.</span>

<span style="color:green">In future we will update the code to take settings input from the UI panel itself.</span>

1. Start QGIS
2. Go to `Plugins` -> `Manage and Install Plugins...` -> `All` -> Search for `EdgeSense` -> Make sure it is enabled (ticked)
3. Drag and drop your original multi-band .tif file into the QGIS -> Press on the EdgeSense icon: <img src="./logo.png" height=20>.
4. Follow the steps as indicated to get each output layer.
5. To download any layer, select that layer and click on `Save active layer` option.

## Normal Pipeline Usage

### Setup

#### 1. Create and activate a virtual environment

```bash
python3 -m venv edgesense
source ./edgesense/bin/activate
```

#### 2. Install dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Run the complete pipeline

```bash
chmod +x srcipts/run_pipeline.sh
./scripts/run_pipeline.sh
```

### Visualising Trends

```bash
python -m tools.plot_fragmentation_trends.py
```

---

## License

[MIT License](./LICENSE)

## Caveats

* We are getting road masks but we don't have access to road masks for all years so we are just taking the current road mask and applying it to all the years throughout.
* Computation of fragmentation metrics requires edge-core mask, forest mask and road mask so if using the plugin make sure to download and save those before running the fragmentation metrics calculation code.
