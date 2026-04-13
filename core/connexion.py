from qgis.core import QgsProject, QgsDataSourceUri
import psycopg2


def connecter():
    layer_name = "geo_r_0_0_1_ht_bt"  # le nom de la couche déjà dans QGIS
    layers = QgsProject.instance().mapLayersByName(layer_name)

    if layers:
        layer = layers[0]
        uri = QgsDataSourceUri(layer.source())
        conn = psycopg2.connect(
        host=uri.host(),
        port=uri.port(),
        dbname=uri.database(),
        user=uri.username(),
        password=uri.password()
)
    return conn




"""   # pour lister les connexions
from qgis.core import QgsSettings

# Récupère toutes les clés de configuration QGIS
settings = QgsSettings()
all_keys = settings.allKeys()

# Préfixe des connexions PostgreSQL
prefix = "PostgreSQL/connections/"

# On extrait les noms uniques de connexion
connections = set()
for key in all_keys:
    if key.startswith(prefix):
        conn_name = key[len(prefix):].split("/")[0]
        connections.add(conn_name)

connections = list(connections)
print("Connexions PostgreSQL disponibles :", connections)"""


"""from qgis.core import QgsProject, QgsDataSourceUri

layer_name = "ma_couche"  # le nom de la couche déjà dans QGIS
layers = QgsProject.instance().mapLayersByName(layer_name)

if layers:
    layer = layers[0]
    uri = QgsDataSourceUri(layer.source())
    host = uri.host()
    port = uri.port()
    database = uri.database()
    username = uri.username()
    password = uri.password()  # vide si Auth Manager non utilisé
    print(host, port, database, username, password)"""