#!/bin/bash

# The 'set -e' command ensures the script stops immediately 
# if any of the python scripts fail or throw an error.
set -e

echo "Starting EdgeSense pipeline..."
echo ""

echo ""
echo "Step 1: Computing NDVI..."
python 1_compute_ndvi.py

echo ""
echo "Step 2: Creating Forest Masks..."
python 2_create_forest_mask.py

echo ""
echo "Step 3: Separating Edge and Core areas..."
python 3_edge_core_separation.py

echo ""
echo "Step 4: Computing Fragmentation Metrics..."
python 4_fragment_metrics.py

echo ""
echo "Step 5: Analyzing Changes and Visualizing Trends..."
python 5_change_analysis.py

echo ""
echo "EdgeSense pipeline complete."
