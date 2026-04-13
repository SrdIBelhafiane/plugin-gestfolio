from qgis.core import QgsProject
from qgis.utils import iface

def rafraichir():
    project = QgsProject.instance()

    # Recharge TOUTES les couches du projet
    for layer in project.mapLayers().values():
        layer.reload()
        layer.triggerRepaint()
    canvas = iface.mapCanvas()
    # Récupère la couche
    layers = project.mapLayersByName("bd_folios_gestfolio")
    if layers:
        layer = layers[0]
        canvas.setExtent(layer.extent())

    # Rafraîchit le canvas
    canvas.refresh()

