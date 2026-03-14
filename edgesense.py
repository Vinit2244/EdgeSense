# ============================================================
# Imports
# ============================================================
import os
import sys
import tempfile
import rasterio
import datetime
import numpy as np
from pathlib import Path

from qgis.PyQt.QtGui import QIcon, QCursor
from qgis.PyQt.QtCore import Qt, QPropertyAnimation, QEasingCurve, QThread, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QAction, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QFrame,
    QSizePolicy, QProgressBar, QGraphicsOpacityEffect,
    QLineEdit, QSpinBox, QDoubleSpinBox, QGridLayout
)

from qgis.core import (
    QgsRasterLayer, QgsProject, Qgis, QgsRasterFileWriter, QgsRasterPipe, QgsMapLayerType
)

sys.path.append(str(Path(__file__).resolve().parents[0]))
from src.utils import read_tif
from src.road_mask import compute_road_mask_plugin
from src.forest_mask import compute_forest_mask_plugin
from src.edge_core_mask import compute_edge_core_mask_plugin
from src.spectral_indices import compute_spectral_indices_plugin
from src.fragmentation_metrics import compute_frag_metrics_plugin

plugin_dir = os.path.dirname(__file__)

# ============================================================
# Stylesheet Constants
# ============================================================
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

INPUT_STYLE = f"""
    QLineEdit, QSpinBox {{
        background-color: #2b2b2b;
        color: #dcdcdc;
        border: 1px solid #404040;
        border-radius: 4px;
        padding: 4px 6px;
        font-size: 11px;
        font-family: {FONT_FAMILY};
    }}
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

SMALL_BTN_STYLE = BTN_STYLE.replace("padding: 6px 12px;", "padding: 4px 8px; font-size: 11px; text-align: center;")

STATUS_READY  = "Ready"
STATUS_DONE   = "Done"
STATUS_LOCKED = "Locked"
STATUS_WORKING = "Working…"


# ============================================================
# Helper Classes/Functions
# ============================================================
# Background worker for the Overpass fetch
class RoadMaskWorker(QThread):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    # Add road_buffer_m
    def __init__(self, forest_mask, meta, road_buffer_m, parent=None):
        super().__init__(parent)
        self.forest_mask = forest_mask
        self.meta        = meta
        self.road_buffer_m = road_buffer_m

    def run(self):
        try:
            road_mask = compute_road_mask_plugin(self.forest_mask, self.meta, self.road_buffer_m)
            self.finished.emit(road_mask)
        except Exception as exc:
            self.error.emit(str(exc))


# ============================================================
# UI Components
# ============================================================
class StepButton(QWidget):
    def __init__(self, step_number, label, parent=None):
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


class OverlayPanel(QWidget):
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


class EdgeSensePlugin:

    def __init__(self, iface):
        self.iface = iface
        self._road_worker = None

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
        self.window.setMinimumWidth(320)

        card = QWidget(self.window)
        card.setObjectName("EdgeSensePanel")
        card.setStyleSheet(PANEL_STYLE)

        card_layout = QVBoxLayout(self.window)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(8)

        # Header
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
            QPushButton {{ background: transparent; color: #888888; border: none; font-size: 12px; font-family: {FONT_FAMILY}; }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        btn_close.clicked.connect(self.window.close)

        header_row.addLayout(title_col)
        header_row.addStretch()
        header_row.addWidget(btn_close)
        root.addLayout(header_row)

        div1 = QFrame()
        div1.setStyleSheet(DIVIDER_STYLE)
        div1.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(div1)

        # Configuration Inputs
        cfg_layout = QVBoxLayout()
        cfg_layout.setSpacing(4)

        # Year Input
        year_row = QHBoxLayout()
        lbl_year = QLabel("Analysis Year:")
        lbl_year.setStyleSheet(f"color: #cccccc; font-size: 11px; font-family: {FONT_FAMILY};")
        self.year_spin = QSpinBox()
        self.year_spin.setRange(1980, 2100)
        self.year_spin.setValue(datetime.datetime.now().year)
        self.year_spin.setStyleSheet(INPUT_STYLE)
        year_row.addWidget(lbl_year)
        year_row.addWidget(self.year_spin)
        year_row.addStretch()
        cfg_layout.addLayout(year_row)

        # ── Configuration Parameters Grid
        params_grid = QGridLayout()
        params_grid.setSpacing(6)

        def add_spin_widget(row, col, label_text, widget):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: #cccccc; font-size: 11px; font-family: {FONT_FAMILY};")
            widget.setStyleSheet(INPUT_STYLE)
            params_grid.addWidget(lbl, row, col*2)
            params_grid.addWidget(widget, row, col*2 + 1)

        # Row 0: Helper Label for 1-based indexing
        index_note = QLabel("Note: Band indices are 1-based (e.g., 1, 2, 3...)")
        index_note.setStyleSheet(f"color: #a0a0a0; font-size: 10px; font-style: italic; font-family: {FONT_FAMILY};")
        params_grid.addWidget(index_note, 0, 0, 1, 4) # Spans 1 row, 4 columns

        # Row 1: Band Indices (Ranges start at 1 now)
        self.red_spin = QSpinBox(); self.red_spin.setRange(1, 20); self.red_spin.setValue(2)
        add_spin_widget(1, 0, "Red Band Idx:", self.red_spin)
        
        self.nir_spin = QSpinBox(); self.nir_spin.setRange(1, 20); self.nir_spin.setValue(3)
        add_spin_widget(1, 1, "NIR Band Idx:", self.nir_spin)

        # Row 2: Band Indices
        self.nnir_spin = QSpinBox(); self.nnir_spin.setRange(1, 20); self.nnir_spin.setValue(4)
        add_spin_widget(2, 0, "n-NIR Band Idx:", self.nnir_spin)

        self.swir_spin = QSpinBox(); self.swir_spin.setRange(1, 20); self.swir_spin.setValue(5)
        add_spin_widget(2, 1, "SWIR Band Idx:", self.swir_spin)

        # Row 3: Thresholds
        self.ndvi_thresh_spin = QDoubleSpinBox(); self.ndvi_thresh_spin.setRange(-1.0, 1.0); self.ndvi_thresh_spin.setSingleStep(0.05); self.ndvi_thresh_spin.setValue(0.4)
        add_spin_widget(3, 0, "NDVI Thresh:", self.ndvi_thresh_spin)
        
        self.ndmi_thresh_spin = QDoubleSpinBox(); self.ndmi_thresh_spin.setRange(-1.0, 1.0); self.ndmi_thresh_spin.setSingleStep(0.05); self.ndmi_thresh_spin.setValue(0.1)
        add_spin_widget(3, 1, "NDMI Thresh:", self.ndmi_thresh_spin)

        # Row 4: Environment Settings
        self.road_buffer_spin = QDoubleSpinBox(); self.road_buffer_spin.setRange(0.0, 500.0); self.road_buffer_spin.setValue(10.0)
        add_spin_widget(4, 0, "Road Buf (m):", self.road_buffer_spin)
        
        self.edge_width_spin = QSpinBox(); self.edge_width_spin.setRange(10, 500); self.edge_width_spin.setValue(100)
        add_spin_widget(4, 1, "Edge Width (m):", self.edge_width_spin)

        # Row 5: Resolution / Scale
        self.scale_spin = QDoubleSpinBox(); self.scale_spin.setRange(0.1, 1000.0); self.scale_spin.setValue(10.0)
        add_spin_widget(5, 0, "Pixel Scale (m):", self.scale_spin)

        cfg_layout.addLayout(params_grid)

        # Output Directory Input
        dir_lbl = QLabel("Output Directory:")
        dir_lbl.setStyleSheet(f"color: #cccccc; font-size: 11px; font-family: {FONT_FAMILY};")
        cfg_layout.addWidget(dir_lbl)

        dir_row = QHBoxLayout()
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("Select output folder...")
        self.dir_input.setReadOnly(True)
        self.dir_input.setStyleSheet(INPUT_STYLE)
        
        btn_browse = QPushButton("Browse")
        btn_browse.setStyleSheet(SMALL_BTN_STYLE)
        btn_browse.clicked.connect(self.select_out_dir)

        dir_row.addWidget(self.dir_input)
        dir_row.addWidget(btn_browse)
        cfg_layout.addLayout(dir_row)

        root.addLayout(cfg_layout)

        div2 = QFrame()
        div2.setStyleSheet(DIVIDER_STYLE)
        div2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(div2)

        # Step buttons
        self.step_run = StepButton(1, "Run Pipeline")
        self.step_save = StepButton(2, "Save Active Layer")

        root.addWidget(self.step_run)
        root.addWidget(self.step_save)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 6)   # Now 6 steps (Load, Indices, Forest, Road, Edge/Core, Metrics)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("""
            QProgressBar { background-color: #1a1a1a; border: 1px solid #333333; border-radius: 2px; }
            QProgressBar::chunk { background-color: #777777; border-radius: 1px; }
        """)
        root.addWidget(self.progress)

        # Footer
        self.footer = QLabel("Waiting for output directory...")
        self.footer.setStyleSheet(f"color: #777777; font-size: 10px; font-family: {FONT_FAMILY}; padding-top: 4px;")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.footer)

        # Connect
        self.step_run.button.clicked.connect(self.run_full_pipeline)
        self.step_save.button.clicked.connect(self.save_output)

        self.check_ready_state()

        main_geo = main_win.geometry()
        x = main_geo.right() - 320 - 20
        y = main_geo.top() + 60
        self.window.move(x, y)
        self.window.show_animated()

    # Helpers ───────────────────────────────────────────────────────

    def select_out_dir(self):
        folder = QFileDialog.getExistingDirectory(self.iface.mainWindow(), "Select Output Directory")
        if folder:
            self.dir_input.setText(folder)
            self.check_ready_state()

    def check_ready_state(self):
        if self.dir_input.text() and Path(self.dir_input.text()).exists():
            self.step_run.set_ready()
            self._update_footer("Ready to run pipeline")
        else:
            self.step_run.set_locked()
            self.step_save.set_locked()
            self._update_footer("Waiting for output directory...")

    def _update_footer(self, text):
        self.footer.setText(text)

    # Full Pipeline Logic ───────────────────────────────────────────

    def run_full_pipeline(self):
        layer = self.iface.activeLayer()

        if not layer or layer.type() != QgsMapLayerType.RasterLayer:
            self.iface.messageBar().pushMessage(
                "EdgeSense",
                "No active raster layer found. Please select a raster in the Layers panel.",
                level=Qgis.MessageLevel.Warning)
            return

        self.image = self.meta = self.ndvi = self.ndmi = None
        self.forest_mask = self.road_mask = self.edge_core = None
        
        self.step_run.set_working()
        self.step_save.set_locked()
        self.progress.setValue(0)

        # Step 1: Load Raster
        path = layer.source()
        self.original_basename = Path(path).stem 
        self.image, self.meta = read_tif(path)
        self.progress.setValue(1)

        # Step 2: Compute Indices (Function expects 0 based indexes, UI is 1-based for user-friendliness)
        red_idx = self.red_spin.value() - 1
        nir_idx = self.nir_spin.value() - 1
        swir_idx = self.swir_spin.value() - 1
        nnir_idx = self.nnir_spin.value() - 1
        
        self.ndvi, self.ndmi = compute_spectral_indices_plugin(self.image, red_idx, nir_idx, swir_idx, nnir_idx)
        self.display_raster(self.ndvi[np.newaxis, ...], "NDVI")
        self.display_raster(self.ndmi[np.newaxis, ...], "NDMI")
        self.progress.setValue(2)

        # Step 3: Compute Forest Mask
        ndvi_th = self.ndvi_thresh_spin.value()
        ndmi_th = self.ndmi_thresh_spin.value()
        
        self.forest_mask = compute_forest_mask_plugin(self.ndvi, self.ndmi, ndvi_th, ndmi_th)
        self.display_raster(self.forest_mask[np.newaxis, ...], "Forest Mask")
        self.progress.setValue(3)
        self._update_footer("Fetching OSM roads…")

        # Step 4: Road Mask (Async Call)
        road_buf = self.road_buffer_spin.value()
        self._road_worker = RoadMaskWorker(self.forest_mask, self.meta, road_buf)
        self._road_worker.finished.connect(self._on_pipeline_road_done)
        self._road_worker.error.connect(self._on_pipeline_road_error)
        self._road_worker.start()

    def _on_pipeline_road_done(self, road_mask):
        self.road_mask = road_mask
        self.display_raster(self.road_mask[np.newaxis, ...], "Road Mask", nodata=255)
        self.progress.setValue(4)
        self._finish_pipeline_edge_core()

    def _on_pipeline_road_error(self, msg):
        self.road_mask = None
        self.progress.setValue(4)
        self._finish_pipeline_edge_core()

    def _finish_pipeline_edge_core(self):
        # Step 5: Compute Edge/Core
        self._update_footer("Computing Edge/Core...")
        working_mask = self.forest_mask.copy()
        
        if self.image is not None and self.meta is not None:
            nodata_val = self.meta.get("nodata")
            if nodata_val is not None:
                nodata_pixels = (
                    np.isnan(self.image[0]) if np.isnan(nodata_val)
                    else (self.image[0] == nodata_val)
                )
                working_mask[nodata_pixels] = 255

        if self.road_mask is not None:
            road_pixels = (self.road_mask == 1) & (working_mask == 1)
            working_mask[road_pixels] = 0

        edge_px = self.edge_width_spin.value() / self.scale_spin.value()  # Convert edge width from meters to pixels
        self.edge_core = compute_edge_core_mask_plugin(working_mask, road_mask=self.road_mask, edge_pixels=edge_px)
        self.display_raster(self.edge_core, "Edge Core", nodata=255)
        self.progress.setValue(5)

        # Step 6: Compute Metrics & Save CSV
        self._update_footer("Calculating fragmentation metrics...")
        year_val = self.year_spin.value()
        out_dir = self.dir_input.text()
        scale_val = self.scale_spin.value()

        summary = compute_frag_metrics_plugin(
            self.forest_mask, 
            self.edge_core, 
            self.road_mask, 
            self.meta, 
            year_val, 
            out_dir,
            scale_val
        )

        self.progress.setValue(6)
        self.step_run.set_done()
        self.step_save.set_ready()
        
        if summary:
            self._update_footer(f"Metrics saved to {Path(out_dir).name}")
            self.iface.messageBar().pushMessage(
                "EdgeSense",
                f"Analysis completed! Found {summary['n_patches']} valid patches. CSVs saved.",
                level=Qgis.MessageLevel.Success)
        else:
            self._update_footer("Pipeline Finished (No valid patches)")
            self.iface.messageBar().pushMessage(
                "EdgeSense",
                "Analysis completed, but no patches >= 0.5ha were found.",
                level=Qgis.MessageLevel.Info)

    # Display raster ────────────────────────────────────────────────

    def display_raster(self, array, name, nodata=None):
        from qgis.core import QgsMultiBandColorRenderer
        temp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
        meta = self.meta.copy()
        meta.update({"count": array.shape[0], "dtype": str(array.dtype)})
        if nodata is not None:
            meta["nodata"] = nodata

        self.current_nodata = nodata
        self.current_layer_array = array

        with rasterio.open(temp.name, "w", **meta) as dst:
            dst.write(array)

        layer = QgsRasterLayer(temp.name, name)
        if array.shape[0] == 3:
            renderer = QgsMultiBandColorRenderer(layer.dataProvider(), 1, 2, 3)
            layer.setRenderer(renderer)

        QgsProject.instance().addMapLayer(layer)

    # Save Raster ───────────────────────────────────────────────────

    def save_output(self):
        layer = self.iface.activeLayer()
        
        if not layer or layer.type() != QgsMapLayerType.RasterLayer:
            self.iface.messageBar().pushMessage(
                "EdgeSense",
                "Please select a valid raster layer in the Layers panel to save.",
                level=Qgis.MessageLevel.Warning)
            return

        out_dir = self.dir_input.text()
        if not out_dir or not Path(out_dir).is_dir():
            self.iface.messageBar().pushMessage(
                "EdgeSense",
                "Please select a valid Output Directory in the panel first.",
                level=Qgis.MessageLevel.Warning)
            return

        # Get original filename (fallback to 'Raster' if it wasn't set by the pipeline)
        base_name = getattr(self, 'original_basename', 'Raster')
        
        # Get and sanitize the active layer name (e.g. "Edge Core" -> "EdgeCore")
        raw_layer_name = layer.name().replace(" ", "")
        safe_layer_name = "".join([c for c in raw_layer_name if c.isalnum() or c in ('-', '_')])
        if not safe_layer_name:
            safe_layer_name = "Mask"

        # Construct the final save path: <original>_<layer>.tif
        file_name = f"{base_name}_{safe_layer_name}.tif"
        path = os.path.join(out_dir, file_name)

        try:
            provider = layer.dataProvider()
            pipe = QgsRasterPipe()
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
                self._update_footer(f"Saved: {file_name}")
                self.iface.messageBar().pushMessage(
                    "EdgeSense", 
                    f"Saved {file_name} successfully!", 
                    level=Qgis.MessageLevel.Success)
            else:
                self.iface.messageBar().pushMessage(
                    "EdgeSense", 
                    f"Save Error Code: {error}", 
                    level=Qgis.MessageLevel.Critical)
                    
        except Exception as e:
            self.iface.messageBar().pushMessage(
                "EdgeSense", 
                f"Error saving file: {str(e)}", 
                level=Qgis.MessageLevel.Critical)
