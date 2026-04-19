# ============================================================
# Imports
# ============================================================
import sys
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

sys.path.append(str(Path(__file__).resolve().parents[1]))
import config as cfg


# ============================================================
# Helper
# ============================================================
def _annotate_trend(ax, x, y, color):
    """Draw a linear trend line and annotate slope direction."""
    if len(x) < 2:
        return
    m, b = np.polyfit(x, y, 1)
    ax.plot(x, m * x + b, linestyle='--', linewidth=1.2, color=color, alpha=0.55, label='Trend')
    ax.legend(fontsize=8)


# ============================================================
# Main
# ============================================================
def analyse_change(df):
    years = df["year"].values

    # Layout: 3 rows × 3 cols
    fig = plt.figure(figsize=(18, 14))
    fig.patch.set_facecolor("#f7f7f2")

    fig.suptitle(
        f"Forest Fragmentation & Ecological Stress Trends  |  {cfg.aoi_slug}  "
        f"({cfg.years[0]}–{cfg.years[-1]})",
        fontsize=15, fontweight='bold', y=0.98
    )

    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.48, wspace=0.35)

    palette = {
        "forest":   "#2d6a4f",
        "patches":  "#6b4226",
        "edge_core":"#d62828",
        "shape":    "#7b2d8b",
        "core_frac":"#1d6fa4",
        "cohesion": "#e07c24",
        "stress":   "#b5000a",
        "log_shape":"#9370db",
    }

    def _style(ax, title, xlabel="Year", ylabel=""):
        ax.set_title(title, fontsize=10, fontweight='bold', pad=6)
        ax.set_xlabel(xlabel, fontsize=8)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.tick_params(labelsize=8)
        ax.set_facecolor("#fefefe")
        ax.grid(True, alpha=0.25, linestyle=':')
        ax.spines[['top', 'right']].set_visible(False)

    # Panel 1 [0, 0]: Metric guide
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_xticks([])
    ax1.set_yticks([])
    ax1.set_facecolor("#eef2f7")
    ax1.spines[['top', 'right']].set_visible(False)
    ax1.spines[['bottom', 'left']].set_color('#aab4c4')
    ax1.set_title("Metric Guide", fontsize=10, fontweight='bold', pad=6)

    notes = (
        "Edge:Core Ratio\n"
        "  Primary hypothesis variable.\n"
        "  Higher → more edge-stressed area.\n\n"
        "Core Area Fraction\n"
        "  Sheltered interior / total area.\n"
        "  Declining = shrinking refugia.\n\n"
        "Patch Cohesion\n"
        "  Spatial compactness (0–1).\n"
        "  Lower = fragmented geometry.\n\n"
        "Shape Index\n"
        "  Perimeter complexity (≥1).\n"
        "  Higher = irregular boundary.\n\n"
        "Stress Pressure Index\n"
        "  Edge:Core × Shape Index.\n"
        "  Composite ecological stress"
    )
    # Placed text right inside the axis box
    ax1.text(0.2, 0.98, notes, transform=ax1.transAxes, fontsize=8, verticalalignment='top', family='monospace')

    # Panel 2 [0, 1]: Total forest area
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.fill_between(years, df["total_forest_ha"], alpha=0.15, color=palette["forest"])
    ax2.plot(years, df["total_forest_ha"], marker='o', color=palette["forest"], linewidth=2)
    _annotate_trend(ax2, years, df["total_forest_ha"].values, palette["forest"])
    _style(ax2, "Total Forest Area", ylabel="Hectares")

    # Panel 3 [0, 2]: Number of patches
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.bar(years, df["n_patches"], color=palette["patches"], alpha=0.75, width=0.6)
    ax3.plot(years, df["n_patches"], marker='s', color=palette["patches"], linewidth=1.5)
    _style(ax3, "Number of Forest Patches (≥0.5 ha)", ylabel="Count")

    # Panel 4 [1, 0]: Mean patch size
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.plot(years, df["mean_patch_ha"], marker='o', color=palette["forest"], linewidth=2, linestyle='-.')
    _annotate_trend(ax4, years, df["mean_patch_ha"].values, palette["forest"])
    _style(ax4, "Mean Patch Size", ylabel="Hectares")

    # Panel 5 [1, 1]: Core area fraction
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.fill_between(years, df["mean_core_area_fraction"], alpha=0.18, color=palette["core_frac"])
    ax5.plot(years, df["mean_core_area_fraction"], marker='o', color=palette["core_frac"], linewidth=2)
    _annotate_trend(ax5, years, df["mean_core_area_fraction"].values, palette["core_frac"])
    _style(ax5, "Mean Core Area Fraction\n(↓ = shrinking interior refugia)", ylabel="Fraction (0–1)")

    # Panel 6 [1, 2]: Patch cohesion
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.plot(years, df["mean_patch_cohesion"], marker='D', color=palette["cohesion"], linewidth=2)
    _annotate_trend(ax6, years, df["mean_patch_cohesion"].values, palette["cohesion"])
    _style(ax6, "Mean Patch Cohesion\n(↓ = more elongated / disaggregated)", ylabel="Cohesion (0–1)")

    # Panel 7 [2, 0]: Edge:Core ratio
    ax7 = fig.add_subplot(gs[2, 0])
    ax7.plot(years, df["total_edge_core_ratio"], marker='^', color=palette["edge_core"], linewidth=2)
    ax7.axhline(df["total_edge_core_ratio"].mean(), color=palette["edge_core"], linestyle='--', alpha=0.45, linewidth=1, label='Overall mean')
    _annotate_trend(ax7, years, df["total_edge_core_ratio"].values, palette["edge_core"])
    ax7.set_title("Edge:Core Ratio\n(↑ = more fragmented / stressed)", fontsize=10, fontweight='bold', pad=6)
    ax7.set_xlabel("Year", fontsize=8); ax7.set_ylabel("Ratio", fontsize=8)
    ax7.tick_params(labelsize=8)
    ax7.set_facecolor("#fefefe")
    ax7.grid(True, alpha=0.25, linestyle=':')
    ax7.spines[['top', 'right']].set_visible(False)
    ax7.legend(fontsize=8)

    # Panel 8 [2, 1]: Mean shape index
    ax8 = fig.add_subplot(gs[2, 1])
    ax8.plot(years, df["mean_shape_index"], marker='D', color=palette["shape"], linewidth=2)
    _annotate_trend(ax8, years, df["mean_shape_index"].values, palette["shape"])
    _style(ax8, "Mean Shape Index\n(↑ = more irregular patches)", ylabel="Shape Index")

    # Panel 9 [2, 2]: Stress Pressure Index (composite)
    ax9 = fig.add_subplot(gs[2, 2])
    ax9.fill_between(years, df["mean_stress_pressure_index"], alpha=0.20, color=palette["stress"])
    ax9.plot(years, df["mean_stress_pressure_index"], marker='*', markersize=10, color=palette["stress"], linewidth=2.2)
    ax9.axhline(df["mean_stress_pressure_index"].mean(), color=palette["stress"], linestyle='--', alpha=0.45, linewidth=1, label='Overall mean')
    _annotate_trend(ax9, years, df["mean_stress_pressure_index"].values, palette["stress"])
    ax9.set_title("Stress Pressure Index\n(edge_core_ratio × shape_index  |  ↑ = higher stress)", fontsize=10, fontweight='bold', pad=6)
    ax9.set_xlabel("Year", fontsize=8); ax9.set_ylabel("Index", fontsize=8)
    ax9.tick_params(labelsize=8)
    ax9.set_facecolor("#fff5f5")   # subtle red tint to flag severity
    ax9.grid(True, alpha=0.25, linestyle=':')
    ax9.spines[['top', 'right']].set_visible(False)
    ax9.legend(fontsize=8)

    out_path = cfg.visualisations_dir / f"Fragmentation_Trends_{cfg.aoi_slug}.png"
    plt.savefig(
        out_path,
        dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor()
    )
    print("Plot saved.")


if __name__ == "__main__":
    all_years_summary = []

    for year in cfg.years:
        year_summary_path = cfg.metrics_dir / f"FragSummary_{cfg.aoi_slug}_{year}.csv"
        if not year_summary_path.exists():
            print(f"Summary CSV for {year} not found, skipping.")
            continue

        year_summary = pd.read_csv(year_summary_path).iloc[0].to_dict()
        all_years_summary.append(year_summary)

    if not all_years_summary:
        print("No summary data found. Run the pipeline first.")
        sys.exit(1)

    cfg.visualisations_dir.mkdir(parents=True, exist_ok=True)
    analyse_change(pd.DataFrame(all_years_summary))
    print("\nFragmentation trends analysis complete.")
