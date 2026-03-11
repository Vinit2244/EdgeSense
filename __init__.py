def classFactory(iface):
    from .edge_sense import EdgeSensePlugin
    return EdgeSensePlugin(iface)