"""Acquisition-record rules; pure Python, so these run outside ArcGIS Pro."""
import json
import unittest

from canopy import record


def row(tile, x=0, points=400, dated=False, dates=None, year=2024, day=182, version="1.4", fmt=6):
    """A header row as delivery.index builds it; ``dated`` means a swath index was used."""
    result = {"tile": tile, "path": rf"\\server\share\{tile}.las", "points": points, "bytes": 1000,
              "version": version, "format": fmt, "extent": [x, 0, x + 10, 10],
              "z_min": 1300.0, "z_max": 1310.0, "file_creation_year": year, "file_creation_day": day}
    if dated:
        result["FLIGHT_DATES"] = dates
    return result


CRS = {"horizontal": "NAD83(2011) / UTM zone 12N", "horizontal_code": 6341,
       "vertical": "NAVD88 height", "vertical_code": 5703}


class CreationDate(unittest.TestCase):
    def test_day_182_of_a_leap_year_is_june_30(self):
        self.assertEqual(record.creation_date(2024, 182), "2024-06-30")

    def test_day_one_is_january_first(self):
        self.assertEqual(record.creation_date(2023, 1), "2023-01-01")

    def test_unset_or_impossible_values_are_none(self):
        self.assertIsNone(record.creation_date(0, 182))
        self.assertIsNone(record.creation_date(2024, 0))
        self.assertIsNone(record.creation_date(2023, 366))  # 2023 has 365 days


class Build(unittest.TestCase):
    def test_record_carries_tile_names_but_no_filesystem_paths(self):
        built = record.build([row("A"), row("B", x=10)], "test", "G:/delivery", CRS, "2026-09-22")
        for text in (json.dumps(built), record.render(built)):
            self.assertNotIn("server", text)
            self.assertNotIn(".las", text)
        self.assertNotIn("path", {key for tile in built["tiles"] for key in tile})
        self.assertEqual([t["tile"] for t in built["tiles"]], ["A", "B"])

    def test_network_paths_never_reach_either_output(self):
        coverage = {"boundary": r"\\fs.example\hidden-share\City.gdb\Boundaries\MunicipalBoundary",
                    "boundary_m2": 2e6, "covered_m2": 1.5e6, "covered_pct": 75.0,
                    "tile_index": {"path": "//fs.example/hidden-share/index/TI.shp", "field": "Tile_Name",
                                   "touching": 1, "in_hand": 1, "missing": []}}
        swaths = {"path": r"\\?\UNC\fs.example\hidden-share\swaths.shp", "date_field": "DATE_D", "swaths": 1}
        built = record.build([row("A", dated=True, dates="2023-11-02")], "test", r"\\fs.example\hidden-share\Lidar",
                             CRS, "2026-09-22", swaths, coverage)
        for text in (json.dumps(built), record.render(built)):
            self.assertNotIn("fs.example", text)
            self.assertNotIn("hidden-share", text)
        self.assertEqual(built["delivery"], "Lidar (network path redacted)")
        self.assertEqual(built["coverage"]["boundary"], "MunicipalBoundary (network path redacted)")
        self.assertEqual(built["coverage"]["tile_index"]["path"], "TI.shp (network path redacted)")
        self.assertEqual(built["swath_index"]["path"], "swaths.shp (network path redacted)")
        self.assertIn(r"\\fs.example", coverage["boundary"])  # the caller's report keeps the full path

    def test_a_bare_share_keeps_no_name_and_mapped_drives_are_unchanged(self):
        self.assertEqual(record.public_path(r"\\fs.example\hidden-share"), "(network path redacted)")
        self.assertEqual(record.public_path("//fs.example/hidden-share/"), "(network path redacted)")
        self.assertEqual(record.public_path(r"G:\GIS\Lidar"), r"G:\GIS\Lidar")
        self.assertEqual(record.public_path("acquisitions/x/TI.shp"), "acquisitions/x/TI.shp")
        self.assertIsNone(record.public_path(None))

    def test_summary_counts_versions_formats_and_density(self):
        built = record.build([row("A", points=400), row("B", x=10, points=600, version="1.2", fmt=1)],
                             "test", "d", CRS, "2026-09-22")
        s = built["summary"]
        self.assertEqual(s["tiles"], 2)
        self.assertEqual(s["points"], 1000)
        self.assertEqual(s["las_versions"], {"1.2": 1, "1.4": 1})
        self.assertEqual(s["point_formats"], {"1": 1, "6": 1})
        self.assertEqual(s["returns_m2"], {"min": 4.0, "median": 5.0, "max": 6.0})
        self.assertEqual(s["created"], ["2024-06-30"])

    def test_flight_dates_absent_when_no_swath_index_was_used(self):
        built = record.build([row("A")], "test", "d", CRS, "2026-09-22")
        self.assertNotIn("flight_dates", built["summary"])
        self.assertIsNone(built["tiles"][0]["flight_dates"])

    def test_undated_tiles_are_listed_when_a_swath_index_was_used(self):
        built = record.build([row("A", dated=True, dates="2023-11-02"), row("B", x=10, dated=True)],
                             "test", "d", CRS, "2026-09-22", {"swaths": 1})
        self.assertEqual(built["tiles"][1]["flight_dates"], [])
        s = built["summary"]
        self.assertEqual(s["flight_dates"]["undated_tiles"], ["B"])
        self.assertEqual(s["flight_dates"]["first"], "2023-11-02")

    def test_flight_groups_order_largest_first_then_by_dates(self):
        tiles = [{"tile": "C", "flight_dates": ["2023-10-07"]},
                 {"tile": "A", "flight_dates": ["2023-11-02"]},
                 {"tile": "B", "flight_dates": ["2023-11-02"]},
                 {"tile": "D", "flight_dates": []}]
        self.assertEqual(record.flight_groups(tiles),
                         [(("2023-11-02",), ["A", "B"]), (("2023-10-07",), ["C"])])


class Render(unittest.TestCase):
    def test_minimal_record_renders_without_optional_sections(self):
        text = record.render(record.build([row("A")], "2023 test", "d", CRS, "2026-09-22"))
        self.assertIn("# Acquisition facts — 2023 test", text)
        self.assertIn("EPSG 6341", text)
        self.assertIn("EPSG 5703", text)
        self.assertNotIn("## Flight dates", text)
        self.assertNotIn("## Coverage", text)
        self.assertIn("## Caveats", text)

    def test_missing_vertical_reference_is_said_plainly(self):
        crs = {"horizontal": "UTM", "horizontal_code": 26912, "vertical": None, "vertical_code": None}
        text = record.render(record.build([row("A")], "t", "d", crs, "2026-09-22"))
        self.assertIn("| Vertical | none declared |", text)

    def test_coverage_section_lists_missing_tiles_and_projection(self):
        coverage = {"boundary": "city", "boundary_m2": 2e6, "covered_m2": 1.5e6, "covered_pct": 75.0,
                    "projected_from": "WGS 1984 Web Mercator (EPSG 3857)", "transformation": "T1",
                    "outside": [], "tile_index": {"path": "ti.shp", "field": "Tile_Name", "touching": 3,
                                                  "in_hand": 2, "missing": [
                                                      {"tile": "X", "boundary_m2": 5e5, "share_pct": 25.0}]}}
        text = record.render(record.build([row("A")], "t", "d", CRS, "2026-09-22", coverage=coverage))
        self.assertIn("**75.00%**", text)
        self.assertIn("projected from WGS 1984 Web Mercator (EPSG 3857)", text)
        self.assertIn("`T1`", text)
        self.assertIn("| X | 50.00 ha | 25.00% |", text)

    def test_a_real_sliver_is_not_rounded_to_zero(self):
        self.assertEqual(record._percent(0.0045), "<0.01%")
        self.assertEqual(record._percent(0.0), "0.00%")
        self.assertEqual(record._percent(0.41), "0.41%")
