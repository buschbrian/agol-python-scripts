r"""Serve the styling check page on 127.0.0.1 with ArcGIS Pro's sign-in, so nobody signs in again (October 23, 2026).

    python reviews/2026-10-23/agol-styling/web/serve_check.py [--port 8797]

ArcGIS Pro Python (PYTHONNOUSERSITE=1), with Pro signed in to the city's ArcGIS Online. GET /token.js answers with a
fresh token from arcpy.GetSigninToken() (it lasts about 30 minutes; reload the page for a new one). The token is never
written to disk and the server listens on 127.0.0.1 only; the page hands it to the SDK's IdentityManager for
www.arcgis.com, tiles.arcgis.com and services9.arcgis.com.
"""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?")[0] != "/token.js":
            return super().do_GET()
        import arcpy
        token = arcpy.GetSigninToken() or {}
        body = f"export default {json.dumps({'token': token.get('token'), 'expires': token.get('expires')})};\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8797)
    port = parser.parse_args().port
    print(f"http://127.0.0.1:{port}/check.html?item=<web map or web scene id>")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
