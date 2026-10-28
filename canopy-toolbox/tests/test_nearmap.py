"""Offline checks for the dated Nearmap WMS contract."""
import tempfile
import unittest
import importlib.util
from io import BytesIO
from unittest.mock import patch
from pathlib import Path

from nearmap_historical_wms import layers_from_capabilities, read_service, request_bbox


class NearmapHistoricalWMS(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('arcpy'),'ArcGIS Pro required')
    def test_dated_export_has_correct_rgb_geometry_without_optional_libraries(self):
        import arcpy
        import numpy as np
        from PIL import Image
        import nearmap_historical_wms as helper
        rgb=np.zeros((256,256,3),dtype=np.uint8);rgb[:,:,0]=80;rgb[:,:,1]=120;rgb[:,:,2]=160
        data=BytesIO();Image.fromarray(rgb).save(data,format='JPEG')
        class Response:
            content=data.getvalue()
            headers={'Content-Type':'image/jpeg'}
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'dated.tif'
            rows=[{'name':'survey','dates':['2023-08-01'],'srs':['EPSG:6341']}]
            with patch.object(helper,'request',return_value=Response()):
                metadata=helper.export('private URL never recorded','survey','2023-08-01',out,256,256,rows)
            raster=arcpy.Raster(str(out))
            self.assertEqual(raster.bandCount,3)
            self.assertAlmostEqual(raster.extent.XMin,428100)
            self.assertAlmostEqual(raster.extent.YMax,4504400)
            self.assertEqual(raster.spatialReference.factoryCode,6341)
            self.assertEqual(metadata['survey_date'],'2023-08-01')
            self.assertNotIn('private URL',out.with_suffix('.json').read_text())
            array=arcpy.RasterToNumPyArray(raster)
            self.assertTrue(np.allclose(array[:,0,0],(80,120,160),atol=2))
            del raster,array

    def test_only_dated_layers_are_listed_with_inherited_srs(self):
        xml=b'''<WMT_MS_Capabilities version="1.1.1"><Capability><Layer>
        <SRS>EPSG:4326 EPSG:3857</SRS><Title>Millcreek</Title>
        <Layer><Name>latest</Name><Title>Combined latest</Title></Layer>
        <Layer><Name>survey_2023_10</Name><Title>2023-10-21 Salt Lake City</Title></Layer>
        </Layer></Capability></WMT_MS_Capabilities>'''
        rows=layers_from_capabilities(xml)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['dates'],['2023-10-21'])
        self.assertEqual(rows[0]['srs'],['EPSG:3857','EPSG:4326'])

    def test_requires_custom_service_and_keeps_pilot_extent(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'url.txt'
            path.write_text('https://api.nearmap.com/wms/v1/latest/apikey/fake')
            with self.assertRaises(ValueError): read_service(path)
            path.write_text('https://api.nearmap.com/wms/v1/places/example/apikey/fake')
            self.assertEqual(read_service(path),path.read_text())
        self.assertEqual(request_bbox('EPSG:6341'),(428100,4504100,428400,4504400))

if __name__=='__main__': unittest.main()
