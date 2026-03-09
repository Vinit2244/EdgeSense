#!/usr/bin/env bash

set -e

echo "=========================================================================="
echo "Downloading Administrative Boundaries Dataset from Survey of India website"
echo "=========================================================================="

# create folders
mkdir -p input

echo "Downloading dataset zip (209.95 MB)..."
wget -P input https://surveyofindia.gov.in/documents/State_District_Sub-district_Boundary_of_entire_India.zip

echo "Unzipping dataset..."
unzip input/State_District_Sub-district_Boundary_of_entire_India.zip -d input

echo "Administrative Boundaries Dataset downloaded and unzipped successfully!"
