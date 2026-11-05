r"""Local servers for the COG drawing check: the page and the COGs, both on 127.0.0.1 only.

    python reviews/2026-10-23/cog-drawing/serve.py OUT [--cogs DIR] [--page-port 8795] [--data-port 8796]

Standard library only. The data server is the COG trial's (byte ranges and CORS, cross-origin from the page as from a
bucket). POST /save/<name> writes the request body to OUT/<name> (results, screenshots of failed views).
"""
import argparse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2]/"2026-10-22"/"hosting"/"cogs"/"web"))
import serve as trial  # noqa: E402  the COG trial's servers

COGS = Path(r"H:\lidar\2023-salt-lake-valley\runs\cog-20261022")
NAME = re.compile(r"^[\w.-]+$")


def page_handler(root, out):
    class Page(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_POST(self):
            parts = self.path.split("/")
            if len(parts) != 3 or parts[1] != "save" or not NAME.match(parts[2]):
                return self.send_error(HTTPStatus.NOT_FOUND)
            (out/parts[2]).write_bytes(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()

        def log_message(self, format, *args):
            sys.stdout.write(f"page {self.log_date_time_string()} {format % args}\n")
            sys.stdout.flush()
    return Page


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path, help="folder for results and screenshots")
    p.add_argument("--cogs", type=Path, default=COGS)
    p.add_argument("--page-port", type=int, default=8795)
    p.add_argument("--data-port", type=int, default=8796)
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    page = trial.Server(("127.0.0.1", args.page_port), page_handler(HERE.parent/"web", args.out.resolve()))
    print(f"page: http://127.0.0.1:{args.page_port}/", flush=True)
    trial.start("data", args.cogs.resolve(), args.data_port)
    try:
        page.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
