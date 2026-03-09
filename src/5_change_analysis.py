# ============================================================
# Imports
# ============================================================
import os
import pandas as pd
import config as cfg
import matplotlib.pyplot as plt


# ============================================================
# Main
# ============================================================
def main():
    os.makedirs(cfg.visualisations_dir, exist_ok=True)

    df = pd.read_csv(os.path.join(cfg.metrics_dir, f"FragMetrics_{cfg.village_slug}_AllYears_Summary.csv"))

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"Forest Fragmentation Trends ({cfg.years[0]}-{cfg.years[-1]})\n{cfg.village_slug}", fontsize=14, fontweight='bold')

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
    axes[1, 0].axhline(y=df["mean_edge_core_ratio"].mean(), color='red', linestyle='--', alpha=0.5, label='Mean')
    axes[1, 0].legend()

    # Plot 4: Mean shape index
    axes[1, 1].plot(df["year"], df["mean_shape_index"], marker='D', color='purple', linewidth=2)
    axes[1, 1].set_title("Mean Shape Index\n(↑ = more irregular patches)")
    axes[1, 1].set_xlabel("Year"); axes[1, 1].set_ylabel("Shape Index")
    axes[1, 1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(cfg.visualisations_dir, f"Fragmentation_Trends_{cfg.village_slug}.png"), dpi=150)
    print("Plot saved.")

if __name__ == "__main__":
    main()
