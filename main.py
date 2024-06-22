
import os
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QDateEdit, QWidget
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer, Qgis
import ee
import requests
from osgeo import gdal

# GDAL istisnalarını etkinleştirme
gdal.UseExceptions()

# Google Earth Engine Kimlik Doğrulama ve Başlatma
try:
    ee.Initialize()
except Exception as e:
    ee.Authenticate()
    ee.Initialize()

class CloudlessImagePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.initGui()

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action = QAction(QIcon(icon_path), 'ClippedCloudlessSentinel', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        # Eğer menüye eklemek isterseniz aşağıdaki satırı ekleyin:
        # self.iface.addPluginToMenu('ClippedCloudlessSentinel', self.action)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        # Eğer menüye eklemek isterseniz aşağıdaki satırı ekleyin:
        # self.iface.removePluginMenu('ClippedCloudlessSentinel', self.action)

    def run(self):
        self.dialog = QWidget()
        layout = QVBoxLayout()

        self.shape_label = QLabel('Shapefile Path:')
        layout.addWidget(self.shape_label)
        self.shape_input = QLineEdit()
        layout.addWidget(self.shape_input)
        self.shape_button = QPushButton('Browse')
        self.shape_button.clicked.connect(self.browse_shape)
        layout.addWidget(self.shape_button)

        self.start_date_label = QLabel('Start Date:')
        layout.addWidget(self.start_date_label)
        self.start_date_input = QDateEdit()
        layout.addWidget(self.start_date_input)

        self.end_date_label = QLabel('End Date:')
        layout.addWidget(self.end_date_label)
        self.end_date_input = QDateEdit()
        layout.addWidget(self.end_date_input)

        self.submit_button = QPushButton('Download Image')
        self.submit_button.clicked.connect(self.download_image)
        layout.addWidget(self.submit_button)

        self.dialog.setLayout(layout)
        self.dialog.show()

    def browse_shape(self):
        shape_path, _ = QFileDialog.getOpenFileName(None, 'Select Shapefile', '', 'Shapefiles (*.shp)')
        self.shape_input.setText(shape_path)

    def download_image(self):
        shape_path = self.shape_input.text()
        start_date = self.start_date_input.date().toString('yyyy-MM-dd')
        end_date = self.end_date_input.date().toString('yyyy-MM-dd')

        # Shapefile'ı yükleme
        shapefile = QgsVectorLayer(shape_path, 'shapefile', 'ogr')
        if not shapefile.isValid():
            self.iface.messageBar().pushMessage('Error', 'Invalid shapefile', level=Qgis.Critical)
            return

        # Shapefile'dan alan sınırlarını al
        extent = shapefile.extent()
        aoi = ee.Geometry.Rectangle([extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()])

        # En az bulutlu görüntüyü bulma
        collection = ee.ImageCollection('COPERNICUS/S2') \
            .filterDate(start_date, end_date) \
            .filterBounds(aoi) \
            .sort('CLOUDY_PIXEL_PERCENTAGE', True) \
            .first()

        true_color = collection.visualize(bands=['B4', 'B3', 'B2'], min=0, max=3000)

        # Her bir bandı ve true color görüntüyü indirme URL'leri
        band_urls = {}
        bands = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B9', 'B10', 'B11', 'B12']
        for band in bands:
            band_urls[band] = collection.select(band).getDownloadURL({
                'scale': 30,
                'crs': 'EPSG:4326',
                'region': aoi,
                'format': 'GEO_TIFF'
            })

        true_color_url = true_color.getDownloadURL({
            'scale': 30,
            'crs': 'EPSG:4326',
            'region': aoi,
            'format': 'GEO_TIFF'
        })

        # Dosya kaydetme dialogu
        save_directory = QFileDialog.getExistingDirectory(None, 'Select Save Directory')
        if not save_directory:
            return

        # Bantları ve true color görüntüsünü indirme ve QGIS'e yükleme
        try:
            for band, url in band_urls.items():
                response = requests.get(url)
                response.raise_for_status()
                band_path = os.path.join(save_directory, f'{band}.tif')
                with open(band_path, 'wb') as file:
                    file.write(response.content)
                self.iface.messageBar().pushMessage('Success', f'{band} downloaded successfully!', level=Qgis.Info)
                self.load_raster(band_path, band)

            response = requests.get(true_color_url)
            response.raise_for_status()
            true_color_path = os.path.join(save_directory, 'true_color.tif')
            with open(true_color_path, 'wb') as file:
                file.write(response.content)
            self.iface.messageBar().pushMessage('Success', 'True color image downloaded successfully!', level=Qgis.Info)
            self.load_raster(true_color_path, 'true_color')

        except requests.exceptions.RequestException as e:
            self.iface.messageBar().pushMessage('Error', f'Failed to download image: {str(e)}', level=Qgis.Critical)
            return

    def load_raster(self, raster_path, layer_name):
        dataset = gdal.Open(raster_path)
        if dataset is None:
            self.iface.messageBar().pushMessage('Error', f'Failed to open the raster dataset with GDAL: {layer_name}', level=Qgis.Critical)
            return

        raster_layer = QgsRasterLayer(raster_path, layer_name)
        if raster_layer.isValid():
            QgsProject.instance().addMapLayer(raster_layer)
            self.iface.messageBar().pushMessage('Success', f'Raster layer loaded successfully: {layer_name}', level=Qgis.Info)
        else:
            self.iface.messageBar().pushMessage('Error', f'Failed to load raster layer: {layer_name}', level=Qgis.Critical)