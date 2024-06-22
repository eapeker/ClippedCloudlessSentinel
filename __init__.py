
def classFactory(iface):
    from .main import CloudlessImagePlugin
    return CloudlessImagePlugin(iface)