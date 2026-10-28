"""A v2 package must be shown with its own comparison results."""
import importlib.util
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request

PATH = Path(__file__).resolve().parents[1] / "reviews/2026-10-23/lod2-check/viewer/serve_scene.py"
SPEC = importlib.util.spec_from_file_location("scene_server", PATH)
viewer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(viewer)


class BookmarkVersion(unittest.TestCase):
    def fetch(self, override):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bookmarks.json").write_bytes(b'{"version":1}')
            server = ThreadingHTTPServer(("127.0.0.1", 0), viewer.handler(root, root, {}, override))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/bookmarks.json") as response:
                    return response.read()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_v2_can_override_v1_captions(self):
        self.assertEqual(self.fetch(b'{"version":2}'), b'{"version":2}')

    def test_existing_v1_launcher_keeps_default(self):
        self.assertEqual(self.fetch(None), b'{"version":1}')
