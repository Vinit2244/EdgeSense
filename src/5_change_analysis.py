# ============================================================
# Imports
# ============================================================
import os
import pandas as pd
import config as cfg
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np


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
def main():
    os.makedirs(cfg.visualisations_dir, exist_ok=True)

    df = pd.read_csv(
        os.path.join(cfg.metrics_dir, f"FragMetrics_{cfg.aoi_slug}_AllYears_Summary.csv")
    )
    years = df["year"].values

    # ── Layout: 3 rows × 3 cols (8 panels used, 1 reserved for legend/notes) ──
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

    # ── Panel 1: Total forest area ──────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.fill_between(years, df["total_forest_ha"], alpha=0.15, color=palette["forest"])
    ax1.plot(years, df["total_forest_ha"], marker='o', color=palette["forest"], linewidth=2)
    _annotate_trend(ax1, years, df["total_forest_ha"].values, palette["forest"])
    _style(ax1, "Total Forest Area", ylabel="Hectares")

    # ── Panel 2: Number of patches ──────────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.bar(years, df["n_patches"], color=palette["patches"], alpha=0.75, width=0.6)
    ax2.plot(years, df["n_patches"], marker='s', color=palette["patches"], linewidth=1.5)
    _style(ax2, "Number of Forest Patches (≥0.5 ha)", ylabel="Count")

    # ── Panel 3: Mean patch size ────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.plot(years, df["mean_patch_ha"], marker='o', color=palette["forest"],
             linewidth=2, linestyle='-.')
    _annotate_trend(ax3, years, df["mean_patch_ha"].values, palette["forest"])
    _style(ax3, "Mean Patch Size", ylabel="Hectares")

    # ── Panel 4: Mean Edge:Core ratio ───────────────────────────────────────
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.plot(years, df["mean_edge_core_ratio"], marker='^', color=palette["edge_core"], linewidth=2)
    ax4.axhline(df["mean_edge_core_ratio"].mean(), color=palette["edge_core"],
                linestyle='--', alpha=0.45, linewidth=1, label='Overall mean')
    _annotate_trend(ax4, years, df["mean_edge_core_ratio"].values, palette["edge_core"])
    ax4.set_title("Mean Edge:Core Ratio\n(↑ = more fragmented / stressed)",
                  fontsize=10, fontweight='bold', pad=6)
    ax4.set_xlabel("Year", fontsize=8); ax4.set_ylabel("Ratio", fontsize=8)
    ax4.tick_params(labelsize=8)
    ax4.set_facecolor("#fefefe")
    ax4.grid(True, alpha=0.25, linestyle=':')
    ax4.spines[['top', 'right']].set_visible(False)
    ax4.legend(fontsize=8)

    # ── Panel 5: Core area fraction ─────────────────────────────────────────
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.fill_between(years, df["mean_core_area_fraction"], alpha=0.18, color=palette["core_frac"])
    ax5.plot(years, df["mean_core_area_fraction"], marker='o', color=palette["core_frac"], linewidth=2)
    _annotate_trend(ax5, years, df["mean_core_area_fraction"].values, palette["core_frac"])
    _style(ax5, "Mean Core Area Fraction\n(↓ = shrinking interior refugia)", ylabel="Fraction (0–1)")

    # ── Panel 6: Patch cohesion ─────────────────────────────────────────────
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.plot(years, df["mean_patch_cohesion"], marker='D', color=palette["cohesion"], linewidth=2)
    _annotate_trend(ax6, years, df["mean_patch_cohesion"].values, palette["cohesion"])
    _style(ax6, "Mean Patch Cohesion\n(↓ = more elongated / disaggregated)", ylabel="Cohesion (0–1)")

    # ── Panel 7: Mean shape index ────────────────────────────────────────────
    ax7 = fig.add_subplot(gs[2, 0])
    ax7.plot(years, df["mean_shape_index"], marker='D', color=palette["shape"], linewidth=2)
    _annotate_trend(ax7, years, df["mean_shape_index"].values, palette["shape"])
    _style(ax7, "Mean Shape Index\n(↑ = more irregular patches)", ylabel="Shape Index")

    # ── Panel 8: Stress Pressure Index (composite) ──────────────────────────
    ax8 = fig.add_subplot(gs[2, 1])
    ax8.fill_between(years, df["mean_stress_pressure_index"], alpha=0.20, color=palette["stress"])
    ax8.plot(years, df["mean_stress_pressure_index"], marker='*', markersize=10,
             color=palette["stress"], linewidth=2.2)
    ax8.axhline(df["mean_stress_pressure_index"].mean(), color=palette["stress"],
                linestyle='--', alpha=0.45, linewidth=1, label='Overall mean')
    _annotate_trend(ax8, years, df["mean_stress_pressure_index"].values, palette["stress"])
    ax8.set_title("Stress Pressure Index\n(edge_core_ratio × shape_index  |  ↑ = higher stress)",
                  fontsize=10, fontweight='bold', pad=6)
    ax8.set_xlabel("Year", fontsize=8); ax8.set_ylabel("Index", fontsize=8)
    ax8.tick_params(labelsize=8)
    ax8.set_facecolor("#fff5f5")   # subtle red tint to flag severity
    ax8.grid(True, alpha=0.25, linestyle=':')
    ax8.spines[['top', 'right']].set_visible(False)
    ax8.legend(fontsize=8)

    # ── Panel 9: Metric legend / notes ──────────────────────────────────────
    ax9 = fig.add_subplot(gs[2, 2])
    ax9.axis('off')
    notes = (
        "Metric Guide\n"
        "────────────────────────\n"
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
        "  Composite ecological stress\n"
        "  signal per patch."
    )
    ax9.text(0.05, 0.97, notes, transform=ax9.transAxes,
             fontsize=8.5, verticalalignment='top', family='monospace',
             bbox=dict(boxstyle='round,pad=0.6', facecolor='#eef2f7', edgecolor='#aab4c4', alpha=0.9))

    plt.savefig(
        os.path.join(cfg.visualisations_dir, f"Fragmentation_Trends_{cfg.aoi_slug}.png"),
        dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor()
    )
    print("Plot saved.")


if __name__ == "__main__":
    main()
