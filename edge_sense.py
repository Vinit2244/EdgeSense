from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from .edge_sense_dialog import EdgeSenseDialog

class EdgeSensePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dlg = None

    def initGui(self):
        self.action = QAction("EdgeSense", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("EdgeSense", self.action)

    def unload(self):
        self.iface.removePluginMenu("EdgeSense", self.action)
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        self.dlg = EdgeSenseDialog(self.iface)
        self.dlg.show()