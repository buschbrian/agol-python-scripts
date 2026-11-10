"""Release totals must exclude roofer models replaced by Esri fallbacks."""
import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "reviews/2026-10-23/lod2-check/build_v2_package.py"
SPEC = importlib.util.spec_from_file_location("build_v2_release", SOURCE)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class PackagedRoofSummary(unittest.TestCase):
    def row(self, area):
        return {"ROOF_PLANES_ALL": "2", "ROOF_PLANES": "2",
                **{name: str(area) for name in ("ROOF_AREA_M2", "FLAT_AREA_M2", "SOUTH_AREA_M2",
                                               "EAST_AREA_M2", "WEST_AREA_M2", "NORTH_AREA_M2")}}

    def test_excludes_replaced_roofs(self):
        rows = {1: self.row(10), 2: self.row(20), 3: self.row(1000)}
        result = release.summarize_packaged_roofs(rows, {1, 2})
        self.assertEqual(result["buildings"], 2)
        self.assertEqual(result["roof_planes"], 4)
        self.assertEqual(result["roof_area_m2_total"], 30)
        self.assertEqual(result["flat_area_m2"], 30)

    def test_missing_selected_building_fails(self):
        with self.assertRaises(KeyError):
            release.summarize_packaged_roofs({1: self.row(10)}, {1, 2})

    def test_all_fallbacks_have_zero_roofer_area(self):
        result = release.summarize_packaged_roofs({1: self.row(10)}, set())
        self.assertEqual(result["buildings"], 0)
        self.assertEqual(result["roof_area_m2_total"], 0)

    def test_upload_summary_fits_arcgis_item_limit(self):
        source = SOURCE.parents[2] / "2026-10-22/hosting/upload/upload.py"
        spec = importlib.util.spec_from_file_location("release_upload", source)
        upload = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(upload)
        summary = upload.ITEMS["buildings3d_v2"]["snippet"]
        self.assertLessEqual(len(summary), 250)
        self.assertIn("planning estimate", summary.lower())


if __name__ == "__main__":
    unittest.main()
