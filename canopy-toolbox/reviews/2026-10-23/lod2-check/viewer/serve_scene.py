r"""Local server for the 3D viewer (October 24, 2026): the page and the scene layer packages as I3S, on 127.0.0.1 only.

    python reviews/2026-10-23/lod2-check/viewer/serve_scene.py OUT --slpk KEY=PATH.slpk [--slpk ...] [--port 8801]

Standard library only. Nothing leaves the machine from here: the packages are read from disk and served to the page.
- /                          the viewer page (web\\)
- /i3s/<key>/SceneServer/layers/0[/...]   the package KEY as an I3S REST scene layer. An .slpk is a zip of the same resources the
                             REST service serves, so a request maps to an entry: layers/0 is 3dSceneLayer.json.gz,
                             nodepages/N, nodes/N/geometries/0, nodes/N/attributes/f_K/0 and statistics/f_K/0 are the entries of
                             the same name with .json.gz or .bin.gz. Gzipped entries are sent as they are, with
                             Content-Encoding: gzip.
- /i3s/<key>/SceneServer     the service listing (one layer)
- POST /save/<name>          writes the body to OUT/<name> (screenshots)
"""
import argparse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import zipfile

HERE = Path(__file__).resolve()
NAME = re.compile(r"^[\w.-]+$")


class Package:
    def __init__(self, path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path)
        self.names = set(self.zip.namelist())
        self.lock = threading.Lock()          # zipfile shares one file pointer

    def entry(self, rest):
        """The zip entry for a path under layers/0, and whether it is gzipped."""
        rest = rest.strip("/")
        if rest == "":
            return "3dSceneLayer.json.gz", True
        for suffix in (".json.gz", ".bin.gz", ".json", ".bin", ".jpg", ".png"):
            if rest+suffix in self.names:
                return rest+suffix, suffix.endswith(".gz")
        return None, False

    def read(self, name):
        with self.lock:
            return self.zip.read(name)


def handler(root, out, packages):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

        def _send(self, body, kind, gzipped=False):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", kind)
            if gzipped:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            m = re.match(r"^/i3s/([\w-]+)/SceneServer(/layers/0)?(/.*)?$", path)
            if not m:
                return super().do_GET()
            pkg = packages.get(m.group(1))
            if pkg is None:
                return self.send_error(HTTPStatus.NOT_FOUND)
            if not m.group(2):
                layer = json.loads(__import__("gzip").decompress(pkg.read("3dSceneLayer.json.gz")))
                listing = {"serviceName": m.group(1), "currentVersion": 11.1, "layers": [
                    {"id": 0, "name": layer.get("name"), "layerType": "3DObject", "alias": layer.get("alias"),
                     "version": layer.get("version"), "spatialReference": layer.get("spatialReference"),
                     "fullExtent": layer.get("fullExtent")}]}
                return self._send(json.dumps(listing).encode(), "application/json")
            entry, gz = pkg.entry(m.group(3) or "")
            if entry is None:
                return self.send_error(HTTPStatus.NOT_FOUND)
            kind = "application/json" if ".json" in entry else "application/octet-stream"
            self._send(pkg.read(entry), kind, gz)

        def do_POST(self):
            parts = self.path.split("/")
            if len(parts) != 3 or parts[1] != "save" or not NAME.match(parts[2]):
                return self.send_error(HTTPStatus.NOT_FOUND)
            (out/parts[2]).write_bytes(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()

        def log_message(self, format, *args):
            pass
    return Handler


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path)
    p.add_argument("--slpk", action="append", required=True, help="KEY=PATH")
    p.add_argument("--port", type=int, default=8801)
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    packages = {}
    for item in a.slpk:
        key, path = item.split("=", 1)
        packages[key] = Package(path)
    server = ThreadingHTTPServer(("127.0.0.1", a.port), handler(HERE.parent/"web", a.out.resolve(), packages))
    print(f"http://127.0.0.1:{a.port}/  packages: {', '.join(packages)}  screenshots to {a.out}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
