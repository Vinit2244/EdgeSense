import os
import sys
import tempfile
import rasterio
import numpy as np
from pathlib import Path

from qgis.PyQt.QtGui import QIcon, QCursor
from qgis.PyQt.QtCore import Qt, QPropertyAnimation, QEasingCurve, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QAction, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QFrame,
    QSizePolicy, QProgressBar, QGraphicsOpacityEffect
)

from qgis.core import QgsRasterLayer, QgsProject, Qgis, QgsRasterFileWriter, QgsRasterPipe

sys.path.append(str(Path(__file__).resolve().parents[0]))
from src.utils import read_tif
from src.spectral_indices import compute_spectral_indices_plugin
from src.forest_mask import compute_forest_mask_plugin
from src.road_mask import compute_road_mask_plugin
from src.edge_core_mask import compute_edge_core_mask_plugin

plugin_dir = os.path.dirname(__file__)

# ─────────────────────────────────────────────
# Minimalistic Stylesheet Constants
# ─────────────────────────────────────────────

FONT_FAMILY = "'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"

PANEL_STYLE = """
QWidget#EdgeSensePanel {
    background-color: #1e1e1e;
    border: 1px solid #333333;
    border-radius: 4px;
}
"""

TITLE_STYLE = f"""
    color: #ffffff;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.5px;
    font-family: {FONT_FAMILY};
"""

SUBTITLE_STYLE = f"""
    color: #888888;
    font-size: 10px;
    letter-spacing: 1px;
    font-family: {FONT_FAMILY};
    text-transform: uppercase;
"""

DIVIDER_STYLE = """
    background-color: #333333;
    max-height: 1px;
    margin: 4px 0px;
"""

STATUS_LABEL_STYLE = f"""
    font-size: 11px;
    font-family: {FONT_FAMILY};
    padding: 2px 6px;
"""

BTN_STYLE = f"""
    QPushButton {{
        background-color: #2b2b2b;
        color: #dcdcdc;
        border: 1px solid #404040;
        border-radius: 4px;
        padding: 6px 12px;
        font-size: 12px;
        font-family: {FONT_FAMILY};
        text-align: left;
    }}
    QPushButton:hover {{
        background-color: #383838;
        border-color: #5c5c5c;
        color: #ffffff;
    }}
    QPushButton:pressed {{
        background-color: #1f1f1f;
        border-color: #404040;
    }}
    QPushButton:disabled {{
        background-color: #1a1a1a;
        color: #555555;
        border-color: #2a2a2a;
    }}
"""

TOOLTIP_STYLE = f"""
QToolTip {{
    background-color: #1e1e1e;
    color: #cccccc;
    border: 1px solid #404040;
    border-radius: 2px;
    padding: 6px;
    font-size: 11px;
    font-family: {FONT_FAMILY};
}}
"""

STATUS_READY  = "Ready"
STATUS_DONE   = "Done"
STATUS_LOCKED = "Locked"
STATUS_WORKING = "Working…"

# ─────────────────────────────────────────────
# Background worker for the Overpass fetch
# ─────────────────────────────────────────────

class RoadMaskWorker(QThread):
    """
    Fetches the OSM road network and rasterizes it on a background thread
    so the QGIS UI stays responsive during the (potentially slow) HTTP call.
    """
    finished = pyqtSignal(object)   # road_mask array
    error    = pyqtSignal(str)

    def __init__(self, forest_mask, meta, parent=None):
        super().__init__(parent)
        self.forest_mask = forest_mask
        self.meta        = meta

    def run(self):
        try:
            road_mask = compute_road_mask_plugin(self.forest_mask, self.meta)
            self.finished.emit(road_mask)
        except Exception as exc:
            self.error.emit(str(exc))


# ─────────────────────────────────────────────
# Reusable Step Button
# ─────────────────────────────────────────────

class StepButton(QWidget):
    """A minimal pipeline step with label, styled button, status badge and rich tooltip."""

    def __init__(self, step_number, label, tooltip_html, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 2)
        outer.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(8)

        chip = QLabel(str(step_number))
        chip.setFixedSize(20, 20)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setStyleSheet(f"""
            background-color: transparent;
            color: #888888;
            border: 1px solid #404040;
            border-radius: 10px;
            font-size: 10px;
            font-family: {FONT_FAMILY};
        """)

        self.button = QPushButton(label)
        self.button.setStyleSheet(BTN_STYLE)
        self.button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.button.setFixedHeight(32)
        self.button.setToolTip(tooltip_html)
        self.button.setToolTipDuration(8000)

        row.addWidget(chip)
        row.addWidget(self.button)

        self.status = QLabel(STATUS_LOCKED)
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight)

        outer.addLayout(row)
        outer.addWidget(self.status)

    def set_status(self, text, color):
        self.status.setText(text)
        self.status.setStyleSheet(STATUS_LABEL_STYLE + f"color: {color};")

    def set_ready(self):
        self.set_status(STATUS_READY, "#aaaaaa")
        self.button.setEnabled(True)

    def set_done(self):
        self.set_status(STATUS_DONE, "#ffffff")
        self.button.setEnabled(True)

    def set_locked(self):
        self.set_status(STATUS_LOCKED, "#555555")
        self.button.setEnabled(False)

    def set_working(self):
        self.set_status(STATUS_WORKING, "#f0a500")
        self.button.setEnabled(False)


# ─────────────────────────────────────────────
# Draggable frameless overlay panel
# ─────────────────────────────────────────────

class OverlayPanel(QWidget):
    """Frameless panel that floats over the QGIS main window and is draggable."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._drag_pos = None

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade.setDuration(150)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def show_animated(self):
        self.show()
        self._fade.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


# ─────────────────────────────────────────────
# Plugin
# ─────────────────────────────────────────────

class EdgeSensePlugin:

    def __init__(self, iface):
        self.iface = iface
        self._road_worker = None   # keep a reference so GC doesn't kill the thread

        self.image       = None
        self.meta        = None
        self.ndvi        = None
        self.ndmi        = None
        self.forest_mask = None
        self.road_mask   = None
        self.edge_core   = None
        self.current_layer_array = None
        self.current_nodata      = None

    def initGui(self):
        icon = os.path.join(plugin_dir, "logo.png")
        self.action = QAction(QIcon(icon), "EdgeSense", self.iface.mainWindow())
        self.iface.addToolBarIcon(self.action)
        self.action.triggered.connect(self.open_panel)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        del self.action

    def open_panel(self):
        if hasattr(self, 'window') and self.window:
            try:
                if not self.window.isHidden():
                    self.window.raise_()
                    return
            except RuntimeError:
                self.window = None

        main_win = self.iface.mainWindow()

        self.window = OverlayPanel(main_win)
        self.window.setObjectName("EdgeSenseWrapper")
        self.window.setMinimumWidth(300)
        self.window.setStyleSheet(TOOLTIP_STYLE)

        card = QWidget(self.window)
        card.setObjectName("EdgeSensePanel")
        card.setStyleSheet(PANEL_STYLE)

        card_layout = QVBoxLayout(self.window)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(6)

        # ── Header ────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(0)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title = QLabel("EdgeSense")
        title.setStyleSheet(TITLE_STYLE + "cursor: grab;")

        sub = QLabel("Forest Edge Core Analysis")
        sub.setStyleSheet(SUBTITLE_STYLE)

        title_col.addWidget(title)
        title_col.addWidget(sub)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(20, 20)
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #888888;
                border: none;
                font-size: 12px;
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                color: #ffffff;
            }}
        """)
        btn_close.clicked.connect(self.window.close)

        header_row.addLayout(title_col)
        header_row.addStretch()
        header_row.addWidget(btn_close)
        root.addLayout(header_row)

        div = QFrame()
        div.setStyleSheet(DIVIDER_STYLE)
        div.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(div)
        root.addSpacing(4)

        # ── Step buttons ──────────────────────────────────────────────
        self.step_load = StepButton(
            1, "Load Active Raster",
            "Reads the raster currently selected in the QGIS Layers panel."
        )
        self.step_ndvi = StepButton(
            2, "Compute NDVI + NDMI",
            "Calculates NDVI and NDMI from the loaded image."
        )
        self.step_mask = StepButton(
            3, "Compute Forest Mask",
            "Derives a binary forest / non-forest mask using NDVI and NDMI thresholds."
        )
        self.step_road = StepButton(
            4, "Fetch Road Mask (OSM)",
            "Downloads the road network from OpenStreetMap via Overpass API and "
            "rasterizes it onto the same grid as the forest mask.<br><br>"
            "<b>Note:</b> requires an internet connection. Road pixels are "
            "reclassified as non-forest before edge/core analysis so that roads "
            "do not generate spurious forest edges."
        )
        self.step_edge = StepButton(
            5, "Compute Edge / Core",
            "Labels each forest pixel as Edge or Core based on proximity to "
            "non-forest pixels (roads are already excluded)."
        )
        self.step_save = StepButton(
            6, "Save Active Layer",
            "Exports the currently selected raster layer in the QGIS Layers panel as a GeoTIFF."
        )

        for step in [self.step_load, self.step_ndvi, self.step_mask,
                     self.step_road, self.step_edge, self.step_save]:
            root.addWidget(step)

        # ── Progress bar ──────────────────────────────────────────────
        root.addSpacing(6)
        self.progress = QProgressBar()
        self.progress.setRange(0, 5)   # 5 processing steps
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #777777;
                border-radius: 1px;
            }
        """)
        root.addWidget(self.progress)

        # ── Footer ────────────────────────────────────────────────────
        self.footer = QLabel("No raster loaded")
        self.footer.setStyleSheet(f"""
            color: #777777;
            font-size: 10px;
            font-family: {FONT_FAMILY};
            padding-top: 4px;
        """)
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.footer)

        # ── Connect ───────────────────────────────────────────────────
        self.step_load.button.clicked.connect(self.load_raster)
        self.step_ndvi.button.clicked.connect(self.run_indices)
        self.step_mask.button.clicked.connect(self.run_forest_mask)
        self.step_road.button.clicked.connect(self.run_road_mask)
        self.step_edge.button.clicked.connect(self.run_edge_core)
        self.step_save.button.clicked.connect(self.save_output)

        self._reset_pipeline_ui()

        main_geo     = main_win.geometry()
        panel_width  = 300
        x = main_geo.right() - panel_width - 20
        y = main_geo.top() + 60
        self.window.move(x, y)

        self.window.show_animated()

    # ── Pipeline state helpers ─────────────────────────────────────────

    def _reset_pipeline_ui(self):
        self.step_load.set_ready()
        for step in [self.step_ndvi, self.step_mask, self.step_road,
                     self.step_edge, self.step_save]:
            step.set_locked()
        self.progress.setValue(0)

    def _update_footer(self, text):
        self.footer.setText(text)

    # ── Step 1 – Load ─────────────────────────────────────────────────

    def load_raster(self):
        layer = self.iface.activeLayer()

        from qgis.core import QgsMapLayerType
        if not layer or layer.type() != QgsMapLayerType.RasterLayer:
            self.iface.messageBar().pushMessage(
                "EdgeSense",
                "No active raster layer found. Please select a raster in the Layers panel.",
                level=Qgis.MessageLevel.Warning)
            return

        path = layer.source()

        # Wipe previous run from memory
        self.image = self.meta = self.ndvi = self.ndmi = None
        self.forest_mask = self.road_mask = self.edge_core = None
        self.current_layer_array = self.current_nodata = None
        self._reset_pipeline_ui()

        self.image, self.meta = read_tif(path)

        self.step_load.set_done()
        self.step_ndvi.set_ready()
        self.progress.setValue(1)
        self._update_footer(f"Loaded: {os.path.basename(path)}")
        self.iface.messageBar().pushMessage("EdgeSense", "Raster loaded successfully.")

    # ── Step 2 – Indices ──────────────────────────────────────────────

    def run_indices(self):
        if self.image is None:
            self.iface.messageBar().pushMessage(
                "EdgeSense", "Load a raster first (Step 1).",
                level=Qgis.MessageLevel.Warning)
            return

        self.ndvi, self.ndmi = compute_spectral_indices_plugin(self.image)

        self.display_raster(self.ndvi[np.newaxis, ...], "NDVI")
        self.display_raster(self.ndmi[np.newaxis, ...], "NDMI")
        self.current_layer_array = self.ndvi[np.newaxis, ...]

        self.step_ndvi.set_done()
        self.step_mask.set_ready()
        self.progress.setValue(2)
        self._update_footer("NDVI & NDMI computed")

    # ── Step 3 – Forest Mask ──────────────────────────────────────────

    def run_forest_mask(self):
        if self.ndvi is None:
            self.iface.messageBar().pushMessage(
                "EdgeSense", "Compute NDVI first (Step 2).",
                level=Qgis.MessageLevel.Warning)
            return

        self.forest_mask = compute_forest_mask_plugin(self.ndvi, self.ndmi)
        self.display_raster(self.forest_mask[np.newaxis, ...], "Forest Mask")
        self.current_layer_array = self.forest_mask[np.newaxis, ...]

        self.step_mask.set_done()
        self.step_road.set_ready()   # road mask is next; edge is still locked
        self.step_save.set_ready()
        self.progress.setValue(3)
        self._update_footer("Forest mask computed")

    # ── Step 4 – Road Mask ────────────────────────────────────────────

    def run_road_mask(self):
        if self.forest_mask is None:
            self.iface.messageBar().pushMessage(
                "EdgeSense", "Compute forest mask first (Step 3).",
                level=Qgis.MessageLevel.Warning)
            return

        # Lock the button and show a working indicator while the thread runs
        self.step_road.set_working()
        self.step_edge.set_locked()
        self._update_footer("Querying OpenStreetMap…")

        self._road_worker = RoadMaskWorker(
            forest_mask = self.forest_mask,
            meta        = self.meta,
        )
        self._road_worker.finished.connect(self._on_road_mask_done)
        self._road_worker.error.connect(self._on_road_mask_error)
        self._road_worker.start()

    def _on_road_mask_done(self, road_mask):
        self.road_mask = road_mask
        self.display_raster(self.road_mask[np.newaxis, ...], "Road Mask", nodata=255)
        self.current_layer_array = self.road_mask[np.newaxis, ...]

        n_road_px = int(np.sum(road_mask == 1))

        self.step_road.set_done()
        self.step_edge.set_ready()
        self.step_save.set_ready()
        self.progress.setValue(4)
        self._update_footer(f"Road mask: {n_road_px:,} road pixels")
        self.iface.messageBar().pushMessage(
            "EdgeSense",
            f"Road mask computed — {n_road_px:,} road pixels rasterized from OSM.")

    def _on_road_mask_error(self, msg):
        # Overpass failed — warn the user but allow the pipeline to continue
        # without road subtraction (edge/core will use the plain forest mask).
        self.road_mask = None
        self.iface.messageBar().pushMessage(
            "EdgeSense",
            f"Road mask fetch failed: {msg}  — continuing without road subtraction.",
            level=Qgis.MessageLevel.Warning)
        self.step_road.set_status("Failed", "#cc4444")
        self.step_road.button.setEnabled(True)   # allow retry
        self.step_edge.set_ready()
        self._update_footer("Road mask unavailable — OSM fetch failed")

    # ── Step 5 – Edge / Core ──────────────────────────────────────────

    def run_edge_core(self):
        if self.forest_mask is None:
            self.iface.messageBar().pushMessage(
                "EdgeSense", "Compute forest mask first (Step 3).",
                level=Qgis.MessageLevel.Warning)
            return

        # Apply nodata from the source image
        working_mask = self.forest_mask.copy()
        if self.image is not None and self.meta is not None:
            nodata_val = self.meta.get("nodata")
            if nodata_val is not None:
                nodata_pixels = (
                    np.isnan(self.image[0]) if np.isnan(nodata_val)
                    else (self.image[0] == nodata_val)
                )
                working_mask[nodata_pixels] = 255

        # Subtract road pixels from forest before edge/core computation
        if self.road_mask is not None:
            n_before     = int(np.sum(working_mask == 1))
            road_pixels  = (self.road_mask == 1) & (working_mask == 1)
            working_mask[road_pixels] = 0
            n_roads      = n_before - int(np.sum(working_mask == 1))
            road_note    = f"{n_roads:,} forest px reclassified as road"
        else:
            road_note = "no road mask applied"

        self.edge_core = compute_edge_core_mask_plugin(working_mask)
        self.display_raster(self.edge_core, "Edge Core", nodata=255)
        self.current_layer_array = self.edge_core

        self.step_edge.set_done()
        self.step_save.set_ready()
        self.progress.setValue(5)
        self._update_footer(f"Edge/Core computed ({road_note})")

    # ── Display raster ────────────────────────────────────────────────

    def display_raster(self, array, name, nodata=None):
        from qgis.core import QgsMultiBandColorRenderer

        temp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
        meta = self.meta.copy()
        meta.update({
            "count": array.shape[0],
            "dtype": str(array.dtype)
        })
        if nodata is not None:
            meta["nodata"] = nodata

        self.current_nodata = nodata

        with rasterio.open(temp.name, "w", **meta) as dst:
            dst.write(array)

        layer = QgsRasterLayer(temp.name, name)

        if array.shape[0] == 3:
            renderer = QgsMultiBandColorRenderer(layer.dataProvider(), 1, 2, 3)
            layer.setRenderer(renderer)

        QgsProject.instance().addMapLayer(layer)

    # ── Step 6 – Save ─────────────────────────────────────────────────

    def save_output(self):
        layer = self.iface.activeLayer()

        if not layer or layer.type() != Qgis.LayerType.Raster:
            self.iface.messageBar().pushMessage(
                "EdgeSense",
                "Please select a valid raster layer in the Layers panel to save.",
                level=Qgis.MessageLevel.Warning)
            return

        path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            f"Save {layer.name()} — EdgeSense",
            "",
            "GeoTIFF (*.tif)"
        )
        if not path:
            return

        try:
            provider = layer.dataProvider()
            pipe     = QgsRasterPipe()
            pipe.set(provider.clone())

            file_writer = QgsRasterFileWriter(path)
            error = file_writer.writeRaster(
                pipe,
                provider.xSize(),
                provider.ySize(),
                provider.extent(),
                layer.crs()
            )

            if error == 0:
                self._update_footer(f"Saved: {os.path.basename(path)}")
                self.iface.messageBar().pushMessage(
                    "EdgeSense",
                    f"Layer '{layer.name()}' saved successfully.",
                    level=Qgis.MessageLevel.Success)
            else:
                self.iface.messageBar().pushMessage(
                    "EdgeSense",
                    f"Failed to save layer. Error code: {error}",
                    level=Qgis.MessageLevel.Critical)

        except Exception as e:
            self.iface.messageBar().pushMessage(
                "EdgeSense",
                f"Error saving file: {str(e)}",
                level=Qgis.MessageLevel.Critical)
