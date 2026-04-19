#!/bin/bash

# The 'set -e' command ensures the script stops immediately 
# if any of the python scripts fail or throw an error.
set -e

echo "Starting EdgeSense pipeline..."

echo ""
echo "Step 1: Computing Spectral Indices..."
python src/spectral_indices.py

echo ""
echo "Step 2: Creating Forest Masks..."
python src/forest_mask.py

echo ""
echo "Step 3: Computing Road Masks (OpenStreetMap)..."
python src/road_mask.py

echo ""
echo "Step 4: Separating Edge and Core areas (road-adjusted)..."
python src/edge_core_mask.py

echo ""
echo "Step 5: Computing Fragmentation Metrics..."
python src/fragmentation_metrics.py

echo ""
echo "EdgeSense pipeline complete."

echo ""
echo "To plot fragmentation trends graphs, run: python tools/plot_fragmentation_trends.py"
