from .edgesense import EdgeSensePlugin

def classFactory(iface):
    return EdgeSensePlugin(iface)
