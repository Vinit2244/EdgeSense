# from qgis.PyQt.QtWidgets import (
#     QDialog, QVBoxLayout, QPushButton,
#     QLabel, QProgressBar
# )
# from qgis.core import QgsMessageLog
# import subprocess, os
# import sys
# import os

# # Find the real Python interpreter, not the QGIS binary
# def get_python():
#     # Try common QGIS Python locations
#     candidates = [
#         "/usr/local/bin/python3",
#         "/Applications/QGIS-final-4_0_0.app/Contents/MacOS/python3.12",
#         "/Applications/QGIS-final-4_0_0.app/Contents/Frameworks/lib/python3.12",
#     ]
#     for p in candidates:
#         if os.path.isfile(p):
#             return p
#     return "python3"  # fallback

# python = get_python()

# class EdgeSenseDialog(QDialog):
#     def __init__(self, iface):
#         super().__init__()
#         self.iface = iface
#         self.setWindowTitle("EdgeSense – Forest Fragmentation")
#         self.setMinimumWidth(400)
#         self._build_ui()

#     def _build_ui(self):
#         layout = QVBoxLayout()
#         self.progress = QProgressBar()
#         self.progress.setValue(0)
#         btn_run = QPushButton("▶  Run EdgeSense Pipeline")
#         btn_run.clicked.connect(self._run_pipeline)
#         layout.addWidget(QLabel("Click to run the EdgeSense pipeline."))
#         layout.addWidget(btn_run)
#         layout.addWidget(self.progress)
#         self.setLayout(layout)

#     def _run_pipeline(self):
#         steps = [
#             "1_compute_ndvi_ndmi.py",
#             "2_create_forest_mask.py",
#             "3_edge_core_separation.py",
#             "4_fragment_metrics.py",
#             "5_analyse_change.py",
#         ]
#         src_dir = os.path.join(os.path.dirname(__file__), "src")

#         for i, script in enumerate(steps):
#             self.progress.setValue(int((i / len(steps)) * 100))
#             script_path = os.path.join(src_dir, script)
#             try:
#                 result = subprocess.run(
#                     [python, script_path],
#                     check=True,
#                     capture_output=True,
#                     text=True                    # ← decode automatically, no .decode() needed
#                 )
#                 QgsMessageLog.logMessage(f"✓ {script} done", "EdgeSense")
#             except subprocess.CalledProcessError as e:
#                 QgsMessageLog.logMessage(
#                     f"✗ {script} failed:\n{e.stderr}", "EdgeSense"
#                 )
#                 break

#         self.progress.setValue(100)


import runpy
import sys
import os
from qgis.core import QgsMessageLog
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel, QProgressBar

class EdgeSenseDialog(QDialog):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.setWindowTitle("EdgeSense – Forest Fragmentation")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        self.progress = QProgressBar()
        self.progress.setValue(0)
        btn_run = QPushButton("▶  Run EdgeSense Pipeline")
        btn_run.clicked.connect(self._run_pipeline)
        layout.addWidget(QLabel("Click to run the EdgeSense pipeline."))
        layout.addWidget(btn_run)
        layout.addWidget(self.progress)
        self.setLayout(layout)

    def _run_pipeline(self):
        steps = [
            "1_compute_ndvi_ndmi.py",
            "2_create_forest_mask.py",
            "3_edge_core_separation.py",
            "4_fragment_metrics.py",
            "5_analyse_change.py",
        ]
        src_dir = os.path.join(os.path.dirname(__file__), "src")

        # Add src dir to path so inter-script imports (like utils) work
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        for i, script in enumerate(steps):
            self.progress.setValue(int((i / len(steps)) * 100))
            script_path = os.path.join(src_dir, script)
            try:
                runpy.run_path(script_path, run_name="__main__")
                QgsMessageLog.logMessage(f"✓ {script} done", "EdgeSense")
            except Exception as e:
                import traceback
                QgsMessageLog.logMessage(
                    f"✗ {script} failed:\n{traceback.format_exc()}", "EdgeSense"
                )
                break

        self.progress.setValue(100)