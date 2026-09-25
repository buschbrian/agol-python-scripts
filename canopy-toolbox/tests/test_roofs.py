"""Roof-model gates and byte-preserving LAS classification regression tests."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

@unittest.skipUnless(importlib.util.find_spec("arcpy") is not None, "ArcGIS Pro Python required")
class RoofRefinement(unittest.TestCase):
    def test_plane_fit_rejects_complex_surface_and_preserves_courtyard(self):
        import numpy as np
        from canopy import roofs
        yy,xx=np.indices((30,30))
        roof=np.full((30,30),np.nan)
        roof[2:24,2:24]=110+.04*xx[2:24,2:24]
        roof[7:12,7:12]=np.nan
        roof[15:18,15:18]+=2
        regions,models=roofs._models(roof,np.full_like(roof,100),1,500000,4500030,25)
        self.assertEqual(len(models),1)
        model=next(iter(models.values()))
        self.assertTrue(model["model_ok"])
        self.assertAlmostEqual(model["plane"][0],.04,places=4)
        self.assertEqual(regions[9,9],0)
        complex_roof=roof.copy();complex_roof[2:24,13:24]+=8
        _,models=roofs._models(complex_roof,np.full_like(roof,100),1,500000,4500030,25)
        self.assertFalse(next(iter(models.values()))["model_ok"])

    def test_only_eligible_classification_bytes_change_in_legacy_and_modern_las(self):
        import numpy as np
        from canopy import roofs
        for modern in (False,True):
            with self.subTest(modern=modern),tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/"points.las"
                # x,y are relative to 500000,4500000; all but distant point lie at roof edge.
                points=[(12.25,8.5,111,5,0), (12.25,8.5,104,5,0),
                        (12.25,8.5,114,5,0), (14.25,8.5,110,5,0),
                        (12.25,8.5,110,2,0), (12.25,8.5,110,1,0),
                        (12.25,8.5,110,7,0), (12.25,8.5,110,5,4 if modern else 128),
                        (12.25,8.5,110,5,1 if modern else 32)]
                size=375 if modern else 227;length=30 if modern else 20
                header=bytearray(size);header[:4]=b"LASF";header[24:26]=bytes([1,4 if modern else 2])
                struct.pack_into("<HII",header,94,size,size,0)
                struct.pack_into("<BHI",header,104,6 if modern else 0,length,len(points))
                if modern:struct.pack_into("<Q",header,247,len(points))
                struct.pack_into("<3d",header,131,.01,.01,.01)
                struct.pack_into("<3d",header,155,500000,4500000,0)
                struct.pack_into("<6d",header,179,500015,500000,4500020,4500000,114,100)
                with path.open("wb") as handle:
                    handle.write(header)
                    for x,y,z,code,flags in points:
                        record=bytearray(length)
                        struct.pack_into("<iii",record,0,round(x*100),round(y*100),round(z*100))
                        record[14]=17 if modern else 9
                        record[15]=flags if modern else flags|code
                        if modern:record[16]=code
                        handle.write(record)
                before=path.read_bytes()
                regions=np.zeros((20,20),dtype=np.int32);regions[2:12,2:12]=1
                model={1:{"model_ok":True,"plane":[0,0,110],"origin":[500007,4500007]}}
                counts=roofs._classify_copy(path,regions,model,1,500000,4500020,1,.35,3,Path(folder)/"changes.npz")
                after=path.read_bytes()
                self.assertEqual(counts,{1:1})
                self.assertEqual([i for i,(a,b) in enumerate(zip(before,after)) if a!=b],
                                 [size+(16 if modern else 15)])
                with np.load(Path(folder)/"changes.npz") as changes:
                    self.assertEqual(changes["point_index"].tolist(),[0])
                    self.assertEqual(changes["previous_class_byte"].tolist(),[5])

    def test_rejected_model_makes_no_changes(self):
        import numpy as np
        from canopy import roofs
        from tests.las_fixture import write_las
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"points.las";write_las(path)
            before=path.read_bytes()
            model={1:{"model_ok":False,"plane":[0,0,110],"origin":[500000,4500000]}}
            counts=roofs._classify_copy(path,np.ones((20,20),dtype=np.int32),model,
                                       1,500000,4500020,1,.35,3,Path(folder)/"changes.npz")
            self.assertEqual(counts,{1:0})
            self.assertEqual(before,path.read_bytes())
