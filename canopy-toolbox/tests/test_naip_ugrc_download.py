import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

REVIEWS = Path(__file__).resolve().parents[1]/"reviews"/"2026-10-01"
spec = importlib.util.spec_from_file_location("naip_ugrc_download", REVIEWS/"naip_ugrc_download.py")
nd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nd)


class Response:
    def __init__(self, headers=None, body=b""):
        self.headers, self.body = headers or {}, body

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Session:
    def __init__(self, body):
        self.body, self.gets = body, 0

    def head(self, url, **kwargs):
        return Response({"Content-Length": str(len(self.body))})

    def get(self, url, **kwargs):
        self.gets += 1
        return Response(body=self.body)


def zip_bytes(directory):
    path = Path(directory)/"made.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("a.tif", b"x"*50)
    return path.read_bytes()


class Urls(unittest.TestCase):
    def test_four_sheets_for_two_quads(self):
        urls = nd.sheet_urls("2024", ("q1320_nw", "q1320_sw"))
        self.assertEqual(sorted(urls), ["q1320_nw_NAIP2024_B4", "q1320_nw_NAIP2024_RGB", "q1320_sw_NAIP2024_B4", "q1320_sw_NAIP2024_RGB"])
        self.assertTrue(urls["q1320_nw_NAIP2024_RGB"].endswith("/naip2024/q1320_nw_NAIP2024_RGB.zip"))


class Fetch(unittest.TestCase):
    def test_check_only_downloads_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            session = Session(zip_bytes(d))
            result = nd.fetch("s", "https://example.invalid/s.zip", d, True, session)
            self.assertEqual((result["status"], session.gets), ("available", 0))
            self.assertFalse((Path(d)/"s.zip").exists())

    def test_download_unzips_and_second_run_does_not_download_again(self):
        with tempfile.TemporaryDirectory() as d:
            session = Session(zip_bytes(d))
            nd.fetch("s", "https://example.invalid/s.zip", d, False, session)
            self.assertTrue((Path(d)/"s"/"a.tif").exists())
            nd.fetch("s", "https://example.invalid/s.zip", d, False, session)
            self.assertEqual(session.gets, 1)

    def test_a_short_file_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            body = zip_bytes(d)
            (Path(d)/"s.zip").write_bytes(body[:-5])
            with self.assertRaises(RuntimeError):
                nd.fetch("s", "https://example.invalid/s.zip", d, False, Session(body))


if __name__ == "__main__":
    unittest.main()
