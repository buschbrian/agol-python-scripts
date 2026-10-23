import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

REVIEWS = Path(__file__).resolve().parents[1]/"reviews"/"2026-09-30"
spec = importlib.util.spec_from_file_location("naip_fetch", REVIEWS/"naip_fetch.py")
nf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nf)

MS = 1636761600000          # 2021-11-13
OLDER = 1500000000000       # 2017-07-14

FUNCTIONS = [{"name": "NaturalColor", "description": "Natural Color bands red, green, blue (1, 2, 3) displayed with fixed stretch."},
             {"name": "FalseColorComposite", "description": "Bands near-infrared, red, green (4, 1, 2) displayed with fixed stretch."}]
INFO = {"bandCount": 4, "pixelType": "U8", "bands": None, "rasterFunctionInfos": FUNCTIONS}


def scene(oid, category=1, bands=4, date=MS):
    return {"OBJECTID": oid, "Name": f"m_{oid}", "Category": category, "band_count": bands, "acquisition_date": date,
            "vendor": "USDA-FSA-APFO", "agency": "USDA", "resolution_value": 0.6, "resolution_units": "METER",
            "sensor_type": "CNIR", "download_url": "https://example.invalid/x"}


class Response:
    def __init__(self, payload=None, content=b"", status=200):
        self.payload, self.content, self.status_code = payload, content, status

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Session:
    def __init__(self, rows, info=INFO, tiff=b"II*\x00" + b"\x00" * 60, exceeded=False):
        self.rows, self.info, self.tiff, self.exceeded, self.calls = rows, info, tiff, exceeded, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if url.endswith("/query"):
            return Response({"features": [{"attributes": r} for r in self.rows], "exceededTransferLimit": self.exceeded})
        if url.endswith("/exportImage"):
            return Response(content=self.tiff)
        return Response(self.info)


class Selection(unittest.TestCase):
    def test_only_the_newest_primary_four_band_scenes_are_used(self):
        rows = [scene(3), scene(1), scene(2, category=2), scene(4, bands=3), scene(5, date=OLDER), scene(6, date=None)]
        self.assertEqual([s["OBJECTID"] for s in nf.primary_scenes(rows)], [1, 3])
        with self.assertRaisesRegex(ValueError, "No primary"):
            nf.primary_scenes([scene(2, category=2), scene(4, bands=3)])

    def test_bands_must_be_confirmed_red_green_blue_nir_by_the_service_itself(self):
        evidence = nf.verify_bands(INFO)
        self.assertIn("(4, 1, 2)", evidence["FalseColorComposite"])
        swapped = [dict(FUNCTIONS[0], description="bands green, red, blue (1, 2, 3)"), FUNCTIONS[1]]
        shifted = [FUNCTIONS[0], dict(FUNCTIONS[1], description="Bands near-infrared, red, green (1, 2, 3)")]
        for bad in (dict(INFO, bandCount=3), dict(INFO, pixelType="U16"), dict(INFO, rasterFunctionInfos=[]),
                    dict(INFO, rasterFunctionInfos=swapped), dict(INFO, rasterFunctionInfos=shifted),
                    {k: v for k, v in INFO.items() if k != "rasterFunctionInfos"}):
            with self.assertRaises(ValueError):
                nf.verify_bands(bad)

    def test_export_request_is_raw_locked_and_bounded(self):
        params = nf.export_params((428000, 4504000, 429000, 4505000), 6341, 0.5, [198401, 198399])
        self.assertEqual((params["size"], params["bandIds"], params["pixelType"]), ("2000,2000", "0,1,2,3", "U8"))
        self.assertEqual(json.loads(params["renderingRule"]), {"rasterFunction": "None"})
        rule = json.loads(params["mosaicRule"])
        self.assertEqual((rule["mosaicMethod"], rule["lockRasterIds"]), ("esriMosaicLockRaster", [198401, 198399]))
        with self.assertRaisesRegex(ValueError, "exceeds the service limit"):
            nf.export_params((0, 0, 3000, 1000), 6341, 0.5, [1])
        with self.assertRaisesRegex(ValueError, "whole number of cells"):
            nf.export_params((0, 0, 1000.3, 1000), 6341, 0.5, [1])

    def test_a_json_error_body_is_not_accepted_as_a_tiff(self):
        nf.check_tiff(b"II*\x00rest")
        with self.assertRaisesRegex(RuntimeError, "did not return a TIFF"):
            nf.check_tiff(b'{"error":{"code":499,"message":"Token Required"}}')


class Fetch(unittest.TestCase):
    EXTENT = (428000, 4504000, 429000, 4505000)

    def test_writes_image_and_metadata_naip_review_accepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/"naip"
            session = Session([scene(198401), scene(198399), scene(9, category=2)])
            record = nf.fetch("12TVL2804", self.EXTENT, 6341, 0.5, out, session=session)
            image = out/"naip_12TVL2804.tif"
            self.assertTrue(image.is_file())
            saved = json.loads((out/"naip_12TVL2804_metadata.json").read_text())
            self.assertEqual((saved["source"], saved["survey_date"], saved["band_mapping"]),
                             ("NAIP", "2021-11-13", {"red": 1, "green": 2, "blue": 3, "nir": 4}))
            self.assertEqual([s["OBJECTID"] for s in saved["scenes"]], [198399, 198401])
            from canopy.run_safeguards import verify_fingerprint
            verify_fingerprint(saved["image"], image)                      # what naip_review.py checks
            self.assertEqual(record["size_px"], "2000,2000")
            self.assertIn("(1, 2, 3)", saved["band_order_evidence"]["NaturalColor"])   # the evidence is on record
            export = [c for c in session.calls if c[0].endswith("/exportImage")][0][1]
            self.assertEqual(json.loads(export["mosaicRule"])["lockRasterIds"], [198399, 198401])
            with self.assertRaises(FileExistsError):
                nf.fetch("12TVL2804", self.EXTENT, 6341, 0.5, out, session=session)

    def test_refusals_leave_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, session, message in (
                    ("a", Session([scene(1, category=2)]), "No primary"),
                    ("b", Session([scene(1)], info=dict(INFO, bandCount=3)), "four-band"),
                    ("e", Session([scene(1)], info=dict(INFO, rasterFunctionInfos=[])), "Band order is not confirmed"),
                    ("c", Session([scene(1)], tiff=b'{"error":1}'), "did not return a TIFF"),
                    ("d", Session([scene(1)], exceeded=True), "truncated")):
                out = Path(tmp)/name
                with self.assertRaisesRegex((ValueError, RuntimeError), message):
                    nf.fetch("T", self.EXTENT, 6341, 0.5, out, session=session)
                self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
