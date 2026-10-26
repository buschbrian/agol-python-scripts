import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

module_path=Path(__file__).resolve().parents[1]/'run_city.py'
spec=importlib.util.spec_from_file_location('cityrun',module_path)
city=importlib.util.module_from_spec(spec);spec.loader.exec_module(city)


class Ownership(unittest.TestCase):
    def test_common_border_has_one_owner_and_stable_id(self):
        left=[0,0,1000,1000];right=[1000,0,2000,1000];point=[1000.,500.,12.]
        self.assertFalse(city.owns(left,point));self.assertTrue(city.owns(right,point))
        self.assertEqual(city.model_id(point),city.model_id(tuple(point)))
        self.assertNotEqual(city.model_id(point),city.model_id([1000.,500.,12.01]))

    def test_halo_requires_neighbors_without_distant_tiles(self):
        a=dict(id='a',core=[0,0,1000,1000]);b=dict(id='b',core=[1000,0,2000,1000]);d=dict(id='d',core=[2000,0,3000,1000])
        self.assertEqual(city.tile_neighbors(a,[a,b,d],100),['a','b'])


class Staging(unittest.TestCase):
    def test_class_flags_ground_support_and_immutable_source(self):
        import laspy
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);laspath=root/'source.las';terrain=root/'terrain.tif'
            las=laspy.create(point_format=8,file_version='1.4')
            las.x=[.25,.75,1.25,.25,.75,1.25,1.75,.25]
            las.y=[1.75,1.75,1.75,.75,.75,.75,.75,.25]
            las.z=[103,101,110,105,105,105,105,102]
            las.classification=[5,5,5,6,5,5,5,3]
            las.withheld=[0,0,0,0,1,0,0,0]
            las.overlap=[0,0,0,0,0,1,0,0]
            las.synthetic=[0,0,0,0,0,0,1,0]
            las.write(laspath)
            digest=hashlib.sha256(laspath.read_bytes()).hexdigest(); stat=laspath.stat()
            with rasterio.open(terrain,'w',driver='GTiff',width=2,height=2,count=1,dtype='float32',
                crs='EPSG:6341',transform=from_origin(0,2,1,1),nodata=-9999) as target:
                target.write(np.array([[100,-9999],[100,100]],dtype='float32'),1)
            config=dict(run_dir=str(root),terrain=str(terrain),min_height_m=2,config_hash='test')
            tile=dict(id='test',path=str(laspath),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns,point_count=8,core=[0,0,2,2])
            city.stage(config,tile)
            points=np.load(root/'staged/test.npy')
            np.testing.assert_allclose(points,[[.25,1.75,103],[.25,.25,102]])
            self.assertEqual(hashlib.sha256(laspath.read_bytes()).hexdigest(),digest)
            audit=json.loads((root/'staged/test.json').read_text())
            self.assertEqual(audit['unknown_ground_points'],1)
            city.stage(config,tile) # completed stage is resumable
            np.testing.assert_array_equal(points,np.load(root/'staged/test.npy'))


if __name__=='__main__':unittest.main()
