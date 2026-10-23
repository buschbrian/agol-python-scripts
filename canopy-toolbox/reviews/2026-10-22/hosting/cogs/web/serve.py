r"""Local servers for the COG web trial: the page on one port, the COGs on another, both on 127.0.0.1 only.

    python reviews/2026-10-22/hosting/cogs/web/serve.py DATA [--page-port 8791] [--data-port 8792]

Standard library only. The data server answers single byte-range requests (206 with Content-Range, 416 when out of range)
and CORS, including the OPTIONS preflight a Range header can trigger, so it behaves like a public bucket with CORS set
for GET and HEAD. The page is served from a different port, so every COG read is a cross-origin request, as it would be
from a bucket. Each request is logged with its range and the bytes sent, which shows what a client actually fetched.
"""
import argparse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sys
import threading

HERE = Path(__file__).resolve().parent
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 1 << 20


class DataHandler(SimpleHTTPRequestHandler):
    """Static files with byte ranges and CORS."""

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, If-None-Match, If-Modified-Since")
        self.send_header("Access-Control-Expose-Headers", "Content-Range, Accept-Ranges, Content-Length, ETag")
        self.send_header("Access-Control-Max-Age", "600")
        # Lets the page's Resource Timing see transfer sizes of cross-origin reads, so it can report bytes fetched.
        self.send_header("Timing-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.end_headers()
        self.log_line()

    def do_HEAD(self):
        try:
            self.serve(head=True)
        finally:
            self.log_line()

    def do_GET(self):
        try:
            self.serve(head=False)
        finally:
            self.log_line()

    def serve(self, head):
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        size = path.stat().st_size
        start, end, status = 0, size-1, HTTPStatus.OK
        header = self.headers.get("Range")
        if header:
            m = RANGE.match(header.strip())
            if not m or (m.group(1) == "" and m.group(2) == ""):
                # Multiple ranges or another unit: answer with the whole file, which HTTP allows.
                header = None
            else:
                if m.group(1) == "":
                    start = max(0, size-int(m.group(2)))
                else:
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size-1)
                if start >= size or start > end:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = HTTPStatus.PARTIAL_CONTENT
        length = end-start+1
        self.send_response(status)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        self.sent = 0 if head else length
        if head:
            return
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining:
                block = f.read(min(CHUNK, remaining))
                if not block:
                    break
                self.wfile.write(block)
                remaining -= len(block)

    def log_request(self, code="-", size="-"):
        self.code = code

    def log_error(self, format, *args):
        pass

    def log_line(self):
        """One line per request once the body is sent: server, time, method, path, range, status, body bytes."""
        sys.stdout.write(f"{self.server.name} {self.log_date_time_string()} {self.command} {self.path} "
                         f"range={self.headers.get('Range', '-')} {int(getattr(self, 'code', 0))} "
                         f"sent={getattr(self, 'sent', 0)}\n")
        sys.stdout.flush()


def handler(root):
    class Rooted(DataHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)
    return Rooted


class Server(ThreadingHTTPServer):
    # http.server sets SO_REUSEADDR, which on Windows lets a second server bind a port another process is listening on,
    # so requests go to whichever answers. Fail instead.
    allow_reuse_address = False


def start(name, root, port):
    server = Server(("127.0.0.1", port), handler(root))
    server.name = name
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"{name}: http://127.0.0.1:{port}/ serving {root}", flush=True)
    return server


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("data", type=Path, help="the COG folder")
    p.add_argument("--page-port", type=int, default=8791)
    p.add_argument("--data-port", type=int, default=8792)
    args = p.parse_args(argv)
    start("page", HERE, args.page_port)
    start("data", args.data.resolve(), args.data_port)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
