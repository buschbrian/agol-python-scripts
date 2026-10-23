import csv
import json
from pathlib import Path
import tempfile
import unittest
import importlib.util
from tests.test_review_drivers import load_driver


class Packet(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'packet';self.driver=load_driver('plot_census_driver')
        self.driver.create_packet(self.root,2,123)

    def test_empty_packet_reports_no_labels_without_importing_arcpy(self):
        result=self.driver.score_packet(self.root,{},1.5,20)
        self.assertEqual(result['status'],'NO_LABELS')
        self.assertEqual(result['sampled_plots'],6)
        self.assertEqual(self.driver.load_census(self.root)[1],{})

    def test_incomplete_review_does_not_become_a_zero_tree_census(self):
        rows=self.driver.read_csv(self.root/'plot_reviews.csv',self.driver.REVIEW_COLUMNS)
        rows[0].update(COMPLETE='YES',REVIEWER='fixture',REVIEW_DATE='2026-09-29',IMAGERY_DATE='2023-08-01')
        with (self.root/'plot_reviews.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=self.driver.REVIEW_COLUMNS);writer.writeheader();writer.writerows(rows)
        with self.assertRaisesRegex(ValueError,'cross-section'): self.driver.load_census(self.root)

    def test_modified_geometry_and_existing_output_are_refused(self):
        with self.assertRaises(FileExistsError): self.driver.create_packet(self.root,2,123)
        with (self.root/'plots.esri.json').open('a') as f:f.write(' ')
        with self.assertRaisesRegex(ValueError,'recorded content'): self.driver.load_census(self.root)

    @unittest.skipUnless(importlib.util.find_spec('arcpy'),'ArcGIS Pro required')
    def test_completed_census_scores_actual_candidate_features(self):
        import arcpy
        import numpy as np
        folder=Path(self.tmp.name)/'run';folder.mkdir()
        arcpy.management.CreateFileGDB(str(folder),'inventory.gdb')
        gdb=str(folder/'inventory.gdb');sr=arcpy.SpatialReference(6341)
        try:
            plots_fc=str(Path(gdb)/'plots')
            arcpy.conversion.JSONToFeatures(str(self.root/'plots.esri.json'),plots_fc,'POLYGON')
            self.assertTrue(all(abs(area-900)<.001 for area, in arcpy.da.SearchCursor(plots_fc,['SHAPE@AREA'])))
            rows=self.driver.read_csv(self.root/'plot_reviews.csv',self.driver.REVIEW_COLUMNS)
            packet=json.loads((self.root/'packet.json').read_text())
            index=next(i for i,p in enumerate(packet['plots']) if p['tile']=='12TVL2804')
            p=packet['plots'][index]
            x,y=p['extent'][:2];pid=p['plot_id']
            rows[index].update(COMPLETE='YES',POINTCLOUD_REVIEW='YES',ALIGNMENT_QA='PASS',REVIEWER='fixture',
                           REVIEW_DATE='2026-09-29',IMAGERY_DATE='2023-08-01')
            with (self.root/'plot_reviews.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=self.driver.REVIEW_COLUMNS);w.writeheader();w.writerows(rows)
            truth=[dict(PLOT_ID=pid,TREE_ID=f't{i}',X=x+dx,Y=y+dy,HEIGHT_M=5,REVIEWER='fixture',
                        REVIEW_DATE='2026-09-29',EVIDENCE='independent synthetic crown') for i,(dx,dy) in enumerate(((5,5),(20,20)))]
            with (self.root/'trees.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=self.driver.TREE_COLUMNS);w.writeheader();w.writerows(truth)
            fc=str(Path(gdb)/'trees_review')
            arcpy.management.CreateFeatureclass(gdb,'trees_review','POINT',spatial_reference=sr)
            arcpy.management.AddField(fc,'TREE_ID','TEXT',field_length=40)
            with arcpy.da.InsertCursor(fc,['TREE_ID','SHAPE@XY']) as cursor:
                for i,(dx,dy) in enumerate(((5,5),(5.5,5),(29,29))): cursor.insertRow([f'p{i}',(x+dx,y+dy)])
            chm=str(folder/'chm.tif')
            arcpy.NumPyArrayToRaster(np.zeros((30,30),dtype=np.float32),arcpy.Point(x,y),1,1).save(chm)
            arcpy.management.DefineProjection(chm,sr)
            for name,geometry in (('treetops','POINT'),('crowns','POLYGON')):
                arcpy.management.CreateFeatureclass(gdb,name,geometry,spatial_reference=sr)
            outputs={'trees_review':fc,'chm':chm,'treetops':str(Path(gdb)/'treetops'),'crowns':str(Path(gdb)/'crowns')}
            (folder/'run.json').write_text(json.dumps({'status':'complete','outputs':outputs,'parameters':{}}))
            result=self.driver.score_packet(self.root,{p['tile']:str(folder)},1.5,20)
            self.assertEqual(result['status'],'PARTIAL')
            self.assertEqual((result['plots'][0]['tp'],result['plots'][0]['fp'],result['plots'][0]['fn']),(1,2,1))
            self.assertEqual(result['scopes']['EXTERNAL_TRANSFER']['status'],'NO_LABELS')
            self.assertIn('12TVL3302',result['scopes']['MILLCREEK_PILOT_TILES']['strata_without_labels'])
        finally: arcpy.management.ClearWorkspaceCache(gdb)
