"""
EcoLand-OS | Module 3 | Step 5: Change Analysis & Visualization
Tracks edge:core ratio and patch metrics across 2018-2024
"""

# NOTE: i havent tried this yet

import pandas as pd
import matplotlib.pyplot as plt
import os

METRICS_DIR = "../output/fragmentation_metrics"
PLOT_DIR    = "../output/plots"
os.makedirs(PLOT_DIR, exist_ok=True)

df = pd.read_csv(os.path.join(METRICS_DIR, "FragMetrics_AllYears_Summary.csv"))

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("Module 3: Forest Fragmentation Trends (2018-2024)\nRampachodavaram Mandal",
             fontsize=14, fontweight='bold')

# Plot 1: Total forest area
axes[0, 0].plot(df["year"], df["total_forest_ha"], marker='o', color='green', linewidth=2)
axes[0, 0].set_title("Total Forest Area (ha)")
axes[0, 0].set_xlabel("Year"); axes[0, 0].set_ylabel("Hectares")
axes[0, 0].grid(True, alpha=0.3)

# Plot 2: Number of patches
axes[0, 1].plot(df["year"], df["n_patches"], marker='s', color='brown', linewidth=2)
axes[0, 1].set_title("Number of Forest Patches (≥0.5 ha)")
axes[0, 1].set_xlabel("Year"); axes[0, 1].set_ylabel("Count")
axes[0, 1].grid(True, alpha=0.3)

# Plot 3: Mean Edge:Core ratio (KEY fragmentation indicator)
axes[1, 0].plot(df["year"], df["mean_edge_core_ratio"], marker='^', color='red', linewidth=2)
axes[1, 0].set_title("Mean Edge:Core Ratio\n(↑ = more fragmented)")
axes[1, 0].set_xlabel("Year"); axes[1, 0].set_ylabel("Ratio")
axes[1, 0].grid(True, alpha=0.3)
axes[1, 0].axhline(y=df["mean_edge_core_ratio"].mean(),
                    color='red', linestyle='--', alpha=0.5, label='Mean')
axes[1, 0].legend()

# Plot 4: Mean shape index
axes[1, 1].plot(df["year"], df["mean_shape_index"], marker='D', color='purple', linewidth=2)
axes[1, 1].set_title("Mean Shape Index\n(↑ = more irregular patches)")
axes[1, 1].set_xlabel("Year"); axes[1, 1].set_ylabel("Shape Index")
axes[1, 1].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(os.path.join(PLOT_DIR, "Module3_Fragmentation_Trends.png"), dpi=150)
plt.show()
print("Plot saved.")