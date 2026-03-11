#!/bin/bash

# The 'set -e' command ensures the script stops immediately 
# if any of the python scripts fail or throw an error.
set -e

echo "Starting EdgeSense pipeline..."
echo ""

echo ""
echo "Step 1: Computing Spectral Indices..."
python -m src.spectral_indices

echo ""
echo "Step 2: Creating Forest Masks..."
python -m src.forest_mask

echo ""
echo "Step 3: Separating Edge and Core areas..."
python -m src.edge_core_mask

echo ""
echo "Step 4: Computing Fragmentation Metrics..."
python -m src.fragmentation_metrics

echo ""
echo "EdgeSense pipeline complete."

echo ""
echo "To plot fragmentation trends graphs, run: python -m tools.plot_fragmentation_trends"
