r"""Local servers for the COG alignment test: the page, the COGs, and a proxy to the private hosted vector tile layers.

    python reviews/2026-10-23/cog-alignment/serve.py OUT [--cogs DIR] [--page-port 8793] [--data-port 8794]

ArcGIS Pro Python (PYTHONNOUSERSITE=1), signed in to the GISMillcreek portal in Pro. Both servers listen on 127.0.0.1 only.
The data server is the COG trial's (byte ranges and CORS, cross-origin from the page as from a bucket). The page server also
answers /proxy/<layer>/... by fetching the same path from the hosted Vector Tile Service with Pro's sign-in token
(arcpy.GetSigninToken, sent with the referer it is bound to), so the private layers draw without sharing them; the token
never reaches the page or the log. The service description gains levels 18-22 (overzoom below); tiles and style pass
through unchanged. POST /save/<name> writes the request body to OUT/<name> (screenshots, results).
"""
import argparse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

import arcpy

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2]/"2026-10-22"/"hosting"/"cogs"/"web"))
sys.path.insert(0, str(HERE.parents[3]))
import serve as trial  # noqa: E402  the COG trial's servers
from canopy.lidar_root import lidar_root  # noqa: E402

COGS = lidar_root()/"2023-salt-lake-valley"/"runs"/"cog-20261022"
SERVICES = {
    # /proxy/contours/VectorTileServer/... maps to this folder's VectorTileServer/...
    "contours": "https://tiles.arcgis.com/tiles/XRrSFvEwSsReIxuA/arcgis/rest/services/"
                "Millcreek_2_m_contours_2023_lidar_planning_estimate",
}
NAME = re.compile(r"^[\w.-]+$")
PASS = ("Content-Type", "Content-Encoding", "Cache-Control", "ETag", "Last-Modified")


def overzoom(body, deepest=22):
    """The service description with levels added past its deepest (17), so the SDK keeps drawing the layer closer than
    1:2,257. Only the description changes: the style's source says maxzoom 17, so the client draws those levels from the
    level 17 tiles, and no tile beyond 17 is ever requested."""
    service = json.loads(body)
    lods = service["tileInfo"]["lods"]
    while lods[-1]["level"] < deepest:
        last = lods[-1]
        lods.append({"level": last["level"]+1, "resolution": last["resolution"]/2, "scale": last["scale"]/2})
    service["maxScale"] = 0
    return json.dumps(service).encode()


def page_handler(root, out, token):
    class Page(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            parts = self.path.split("/", 3)
            if len(parts) > 2 and parts[1] == "proxy":
                return self.proxy(parts[2], parts[3] if len(parts) > 3 else "")
            return super().do_GET()

        def proxy(self, layer, rest):
            if layer not in SERVICES:
                return self.send_error(HTTPStatus.NOT_FOUND)
            path, _, query = rest.partition("?")
            query = urllib.parse.parse_qsl(query, keep_blank_values=True)
            query = urllib.parse.urlencode([(k, v) for k, v in query if k != "token"] + [("token", token["token"])])
            request = urllib.request.Request(f"{SERVICES[layer]}/{path}?{query}", headers={"Referer": token["referer"]})
            try:
                with urllib.request.urlopen(request, timeout=60) as r:
                    body, status, headers = r.read(), r.status, r.headers
            except urllib.error.HTTPError as e:
                body, status, headers = e.read(), e.code, e.headers
            if status == 200 and path == "VectorTileServer":
                body = overzoom(body)
            self.send_response(status)
            for h in PASS:
                if headers.get(h) and h != "Cache-Control":
                    self.send_header(h, headers[h])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            parts = self.path.split("/")
            if len(parts) != 3 or parts[1] != "save" or not NAME.match(parts[2]):
                return self.send_error(HTTPStatus.NOT_FOUND)
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            (out/parts[2]).write_bytes(body)
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()

        def log_message(self, format, *args):
            # Request lines only; a proxied path never carries the token (it is added on the way out).
            sys.stdout.write(f"page {self.log_date_time_string()} {format % args}\n")
            sys.stdout.flush()
    return Page


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path, help="folder for screenshots and results")
    p.add_argument("--cogs", type=Path, default=COGS)
    p.add_argument("--page-port", type=int, default=8793)
    p.add_argument("--data-port", type=int, default=8794)
    args = p.parse_args(argv)
    token = arcpy.GetSigninToken()
    if not token:
        sys.exit("Pro gave no sign-in token: sign in to the portal in ArcGIS Pro first.")
    args.out.mkdir(parents=True, exist_ok=True)
    page = trial.Server(("127.0.0.1", args.page_port), page_handler(HERE.parent/"web", args.out.resolve(), token))
    print(f"page: http://127.0.0.1:{args.page_port}/ (proxy for {', '.join(SERVICES)})", flush=True)
    trial.start("data", args.cogs.resolve(), args.data_port)
    try:
        page.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
