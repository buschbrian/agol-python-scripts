import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from tests.test_review_drivers import load_driver
from canopy.run_safeguards import fingerprint


@unittest.skipUnless(importlib.util.find_spec('arcpy'),'ArcGIS Pro required')
class Review(unittest.TestCase):
    def test_four_band_raster_preserves_nodata_and_input(self):
        import arcpy
        from canopy import licensing
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);image=root/'naip.tif';metadata=root/'metadata.json'
            bands=np.array([[[20,200],[0,0]],[[30,30],[0,0]],[[30,30],[0,0]],[[200,20],[0,10]]],dtype=np.uint8)
            arcpy.NumPyArrayToRaster(bands,arcpy.Point(428250,4504250),1,1,0).save(str(image))
            arcpy.management.DefineProjection(str(image),arcpy.SpatialReference(6341))
            before=fingerprint(image)
            metadata.write_text(json.dumps({'source':'NAIP','survey_date':'2023-08-01',
                'band_mapping':{'red':1,'green':2,'blue':3,'nir':4},'image':before}))
            driver=load_driver('naip_review')
            with licensing.extensions('Spatial'):
                result=driver.build(image,metadata,root/'review')
            self.assertEqual(result['status'],'REVIEW_SCREEN_ONLY')
            self.assertEqual(result['counts'],{'LOW_GREENNESS_REVIEW':1,'GREEN_SPECTRAL_SUPPORT':1,'UNKNOWN':2})
            self.assertEqual(fingerprint(image),before)
            with self.assertRaises(FileExistsError):driver.build(image,metadata,root/'review')
