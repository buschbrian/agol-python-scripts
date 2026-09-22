"""Offline regression tests for the three standalone GIS utilities."""
import argparse
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT=Path(__file__).resolve().parents[2]

def load(name, filename, modules):
    with patch.dict(sys.modules,modules):
        spec=importlib.util.spec_from_file_location(name,ROOT/filename)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class StandaloneUtilities(unittest.TestCase):
    def badelf(self):
        return load("test_badelf","add_badelf_fields_to_agol.py",{
            "arcgis":types.ModuleType("arcgis"),
            "arcgis.features":types.SimpleNamespace(FeatureLayerCollection=MagicMock()),
            "arcgis.gis":types.SimpleNamespace(GIS=MagicMock())})

    def test_negative_layer_is_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            self.badelf().nonnegative_index("-1")

    def test_existing_badelf_type_and_domain_conflicts_are_reported(self):
        module=self.badelf()
        fields=[{"name":"BADELF_CORR_TYPE","type":"esriFieldTypeString","domain":None}]
        conflicts=module.schema_conflicts(fields)
        self.assertTrue(any("type" in c for c in conflicts))
        self.assertTrue(any("domain" in c for c in conflicts))

    def sketch(self):
        rule=types.SimpleNamespace(name="test_rule",isEnabled=True)
        sr=types.SimpleNamespace(name="test",GCS=types.SimpleNamespace(name="same"),
                                 exportToString=lambda:"same")
        fake=MagicMock()
        fake.env=types.SimpleNamespace(overwriteOutput=False)
        fake.Describe.return_value=types.SimpleNamespace(spatialReference=sr,attributeRules=[rule])
        fake.Exists.side_effect=lambda value: value in ("sketch","template")
        fake.management.GetCount.return_value=["1"]
        module=load("test_sketch","sketch_layer_to_template_schema.py",{"arcpy":fake})
        module.SKETCH_FC="sketch";module.TEMPLATE_FC="template";module.TARGET_FC="target"
        return module,fake

    def test_sketch_dry_run_does_not_export_rules_or_write_dataset(self):
        module,fake=self.sketch()
        module.main()
        fake.management.ExportAttributeRules.assert_not_called()
        fake.management.Copy.assert_not_called()

    def test_failed_append_restores_enabled_rules(self):
        module,fake=self.sketch();module.DRY_RUN=False
        fake.management.Append.side_effect=RuntimeError("simulated failed load")
        with self.assertRaises(RuntimeError):
            module.main()
        fake.management.DisableAttributeRules.assert_called_once_with("target",["test_rule"])
        fake.management.EnableAttributeRules.assert_called_once_with("target",["test_rule"])

    def test_palette_exhaustion_fails_before_any_feature_edit(self):
        fake=MagicMock()
        edges=[(a,b) for a in range(10) for b in range(a+1,10)]
        fake.da.SearchCursor.return_value.__enter__.return_value=iter(edges)
        with patch.dict(sys.modules,{"arcpy":fake}):
            with self.assertRaises(RuntimeError):
                runpy.run_path(str(ROOT/"assign_polygon_colors.py"))
        fake.AddField_management.assert_not_called()
        fake.da.UpdateCursor.assert_not_called()

