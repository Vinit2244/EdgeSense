#!/bin/bash

# ==========================================
# Define paths
# ==========================================

# Directory where plugin should be copied
TARGET_DIR="/Users/vinitmehta/Library/Application Support/QGIS/QGIS4/profiles/default/python/plugins/EdgeSense"

# scripts directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# project root (parent of scripts)
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Project root: $PROJECT_ROOT"
echo "Target directory: $TARGET_DIR"

# ==========================================
# Ensure target directory exists
# ==========================================

mkdir -p "$TARGET_DIR"

# ==========================================
# Files/Folders to copy from project root
# ==========================================

ITEMS=(
    "config"
    "src"
    "__init__.py"
    "edgesense.py"
    "LICENSE"
    "logo.png"
    "metadata.txt"
    "README.md"
)

# ==========================================
# Copy files and folders
# ==========================================

for item in "${ITEMS[@]}"
do
    cp -r "$PROJECT_ROOT/$item" "$TARGET_DIR/"
done

echo "Copying files completed."
