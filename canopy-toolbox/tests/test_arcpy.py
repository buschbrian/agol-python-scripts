"""ArcGIS regression fixtures; skipped in plain Python environments."""
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest

ARCPY = importlib.util.find_spec("arcpy") is not None

@unittest.skipUnless(ARCPY, "ArcGIS Pro Python required")
class ArcGISRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global arcpy, np, bands, treetops, crowns, cover, rasters
        import arcpy
        import numpy as np
        from canopy import bands, treetops, crowns, cover, rasters
        cls.root = Path(tempfile.mkdtemp(prefix="canopy_tests_"))
        cls.gdb = str(cls.root/"tests.gdb")
        cls.sr = arcpy.SpatialReference(26912)
        arcpy.management.CreateFileGDB(str(cls.root), "tests.gdb")
        arcpy.env.parallelProcessingFactor = "0"
        arcpy.env.scratchWorkspace = str(cls.root)
        for ext in ["Spatial", "3D"]:
            arcpy.CheckOutExtension(ext)

    @classmethod
    def tearDownClass(cls):
        for ext in ["3D", "Spatial"]:
            arcpy.CheckInExtension(ext)
        arcpy.management.ClearWorkspaceCache(cls.gdb)
        shutil.rmtree(cls.root, ignore_errors=True)

    def raster(self, name, array, cell=1):
        path = str(self.root/(name+".tif"))
        arcpy.NumPyArrayToRaster(np.asarray(array, dtype=np.float32), arcpy.Point(500000,4500000),
                                cell,cell,-9999).save(path)
        arcpy.management.DefineProjection(path,self.sr)
        return path

    def zones(self,name,entries):
        path=os.path.join(self.gdb,name)
        arcpy.management.CreateFeatureclass(self.gdb,name,"POLYGON",spatial_reference=self.sr)
        arcpy.management.AddField(path,"ZONE_KEY","TEXT",field_length=20)
        with arcpy.da.InsertCursor(path,["SHAPE@","ZONE_KEY"]) as cursor:
            for key,x,y,w,h in entries:
                vertices=[(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)]
                geometry=arcpy.Polygon(arcpy.Array([arcpy.Point(500000+a,4500000+b) for a,b in vertices]),self.sr)
                cursor.insertRow([geometry,key])
        return path

    def test_cone_crown_contains_all_137_cells_and_input_unchanged(self):
        yy,xx=np.indices((21,21))
        array=np.maximum(0,12-np.hypot(yy-10,xx-10)*1.5)
        chm=self.raster("cone",array)
        tops=treetops.detect(chm,self.gdb,bands.DEFAULT_BANDS,prefix="cone_")
        fields_before=[f.name for f in arcpy.ListFields(tops)]
        self.assertEqual(int(arcpy.management.GetCount(tops)[0]),1)
        result=crowns.delineate(chm,tops,self.gdb,prefix="cone_")
        values=list(arcpy.da.SearchCursor(result,["HEIGHT_M","CROWN_AREA_M2"]))
        self.assertEqual(values,[(12.0,137.0)])
        self.assertEqual(fields_before,[f.name for f in arcpy.ListFields(tops)])

    def test_diagonal_plateau_is_one_seed(self):
        array=np.zeros((7,7),dtype=np.float32);array[3,3]=10;array[4,4]=10
        self.assertEqual(len(treetops.peak_cells(array,bands.DEFAULT_BANDS,1,0)),1)

    def test_no_trees_has_valid_empty_outputs(self):
        chm=self.raster("empty",np.zeros((5,5)))
        tops=treetops.detect(chm,self.gdb,bands.DEFAULT_BANDS,prefix="empty_")
        result=crowns.delineate(chm,tops,self.gdb,prefix="empty_")
        self.assertEqual(int(arcpy.management.GetCount(result)[0]),0)

    def test_watershed_does_not_cross_unknown_or_bare_cells(self):
        data=np.full((3,7),10.0);mask=np.ones(data.shape,dtype=bool);mask[:,3]=False
        labels=crowns.segment(data,mask,[(1,1,1)])
        self.assertTrue((labels[:,:3]==1).all())
        self.assertTrue((labels[:,3:]==0).all())

    def test_adjacent_seeds_are_preserved(self):
        data=np.full((7,7),5.0)
        labels=crowns.segment(data,np.ones(data.shape,dtype=bool),[(3,1,1),(3,5,2)])
        self.assertEqual(labels[3,1],1);self.assertEqual(labels[3,5],2)
        self.assertTrue((labels>0).all())

    def test_partial_cover_uses_raster_resolution_and_preserves_missing_zones(self):
        chm=self.raster("partial",[[10,10,-9999,-9999]]*4)
        zones=self.zones("partial_zones",[("partial",0,0,4,4),("missing",10,10,4,4),
                                         ("overlap",0,0,2,4), ("partial",0,0,4,4),
                                         ("tiny",.05,.05,.1,.1)])
        result=cover.summarize(chm,zones,"ZONE_KEY",os.path.join(self.gdb,"partial_cover"))
        fields=["ZONE_ID","CANOPY_M2","ZONE_M2","GRID_M2","OBSERVED_M2","MISSING_M2","CANOPY_PCT","COVERAGE_PCT"]
        rows={r[0]:r[1:] for r in arcpy.da.SearchCursor(result,fields)}
        self.assertEqual(rows["partial"],(8.0,16.0,16.0,8.0,8.0,None,50.0))
        self.assertEqual(rows["missing"],(0.0,16.0,16.0,0.0,16.0,None,0.0))
        self.assertEqual(rows["overlap"][-2:],(100.0,100.0))
        self.assertEqual(rows["tiny"][2:5],(0.0,0.0,0.0))
        # New output in the same workspace must not collide with an intermediate.
        cover.summarize(chm,zones,"ZONE_KEY",os.path.join(self.gdb,"partial_cover_again"))
        with self.assertRaises(ValueError):
            cover.summarize(chm,zones,"ZONE_KEY",os.path.join(self.gdb,"bad_resolution"),cell_size=.5)

    def test_workspace_contract_rejects_folder_before_processing(self):
        with self.assertRaises(ValueError):
            treetops.detect("unused",str(self.root),bands.DEFAULT_BANDS)


    def test_las_gap_and_class_one_do_not_become_canopy(self):
        from tests.las_fixture import write_las
        las=str(self.root/"classified.las");write_las(las)
        lasd=str(self.root/"classified.lasd")
        arcpy.management.CreateLasDataset(las,lasd,spatial_reference=self.sr,compute_stats="COMPUTE_STATS")
        outputs=rasters.build_chm(lasd,str(self.root),cell_size=1,prefix="classified_",z_unit="metres")
        for xy in ["500005.5 4500003.5","500005.5 4500005.5","500005.5 4500006.5"]:
            self.assertEqual(float(arcpy.management.GetCellValue(outputs["chm"],xy)[0]),0.0)
        self.assertEqual(float(arcpy.management.GetCellValue(outputs["chm"],"500001.5 4500003.5")[0]),10.0)

    def test_las_without_vegetation_is_observed_noncanopy(self):
        from tests.las_fixture import write_las
        las=str(self.root/"ground_only.las");write_las(las,vegetation=False)
        # Also exercise a genuinely empty building filter.
        data=bytearray(Path(las).read_bytes())
        for position in range(227,len(data),20):
            if data[position+15] == 6:data[position+15]=1
        Path(las).write_bytes(data)
        lasd=str(self.root/"ground_only.lasd")
        arcpy.management.CreateLasDataset(las,lasd,spatial_reference=self.sr,compute_stats="COMPUTE_STATS")
        result=rasters.build_chm(lasd,str(self.root),cell_size=1,prefix="ground_",z_unit="metres")
        self.assertEqual(float(arcpy.management.GetCellValue(result["chm"],"500005.5 4500003.5")[0]),0.0)
        self.assertEqual(int(arcpy.management.GetRasterProperties(result["building"],"ALLNODATA")[0]),1)


    def test_units_reject_geographic_and_feet(self):
        from canopy import common
        for code in (4326,2232):
            with self.assertRaises(ValueError):
                common.metric_reference(arcpy.SpatialReference(code))

    def test_all_unknown_raster_has_no_trees(self):
        chm=self.raster("unknown",np.full((5,5),-9999))
        tops=treetops.detect(chm,self.gdb,bands.DEFAULT_BANDS,prefix="unknown_")
        result=crowns.delineate(chm,tops,self.gdb,prefix="unknown_")
        self.assertEqual(int(arcpy.management.GetCount(result)[0]),0)

    def test_tiled_rasters_use_exact_global_detection_and_crowns(self):
        from unittest.mock import patch
        from canopy import pipeline
        from tests.las_fixture import write_las
        las=str(self.root/"runner.las");write_las(las)
        lasd=str(self.root/"runner.lasd")
        arcpy.management.CreateLasDataset(las,lasd,spatial_reference=self.sr,compute_stats="COMPUTE_STATS")
        yy,xx=np.indices((80,80))
        array=np.maximum(0,12-np.hypot(yy-39,xx-39)*.35)
        # Long flat plateau crosses multiple cores and exceeds any finite local neighbourhood.
        array[3:7,2:78]=5
        chm=self.raster("runner_surface",array)
        folder=str(self.root/"runner")
        kwargs=dict(extent=[500000,4500000,500080,4500080],tile_size=40,overlap=15,
                    cell_size=1,source_files=[las],source_id="fixture",z_unit="metres")
        with patch.object(pipeline.rasters,"build_chm",return_value={"chm":chm}):
            state=pipeline.run(lasd,folder,**kwargs)
        outputs=state["outputs"]
        tops=treetops.detect(outputs["chm"],self.gdb,bands.DEFAULT_BANDS,prefix="whole_",source_id="fixture")
        polygons=crowns.delineate(outputs["chm"],tops,self.gdb,prefix="whole_")
        fields=["TREE_ID","CROWN_AREA_M2","HEIGHT_M"]
        self.assertEqual(sorted(arcpy.da.SearchCursor(outputs["crowns"],fields)),
                         sorted(arcpy.da.SearchCursor(polygons,fields)))
        self.assertEqual(state["outputs"],pipeline.run(lasd,folder,resume=True,**kwargs)["outputs"])
        equivalent=dict(kwargs);equivalent["tile_size"]=40.0;equivalent["cell_size"]=1.0
        self.assertEqual(state["outputs"],pipeline.run(lasd,folder,resume=True,**equivalent)["outputs"])
        with self.assertRaises(ValueError):
            pipeline.run(lasd,folder,resume=True,min_crown_area=4,**kwargs)
        with self.assertRaises(ValueError):
            pipeline.run(lasd,str(self.root/"too_large"),[500000,4500000,502001,4502001],
                         cell_size=1,source_files=[las])

    def test_upper_building_surface_occludes_lower_vegetation_but_preserves_overhang(self):
        import struct
        from tests.las_fixture import write_las
        las=self.root/"occlusion.las";write_las(las)
        data=bytearray(las.read_bytes())
        new_points=[(1,1,115),(2,1,108),(1,2,110.2),(2,2,110.5)]
        count=struct.unpack_from("<I",data,107)[0]+len(new_points)
        struct.pack_into("<I",data,107,count);struct.pack_into("<I",data,111,count)
        for x,y,z in new_points:
            data.extend(struct.pack("<iiiHBBbBH",round(x*100),round(y*100),round(z*100),10,9,6,0,0,0))
        las.write_bytes(data)
        lasd=str(self.root/"occlusion.lasd")
        arcpy.management.CreateLasDataset(str(las),lasd,spatial_reference=self.sr,compute_stats="COMPUTE_STATS")
        outputs=rasters.build_chm(lasd,str(self.root),cell_size=1,prefix="occlusion_",z_unit="metres")
        for x,y,expected in [(1.5,1.5,0),(2.5,1.5,10),(1.5,2.5,10),(2.5,2.5,0)]:
            xy=f"{500000+x} {4500000+y}"
            self.assertEqual(float(arcpy.management.GetCellValue(outputs["chm"],xy)[0]),expected)
            self.assertEqual(float(arcpy.management.GetCellValue(outputs["observed"],xy)[0]),1)
        self.assertEqual(float(arcpy.management.GetCellValue(outputs["occlusion"],"500001.5 4500001.5")[0]),1)
