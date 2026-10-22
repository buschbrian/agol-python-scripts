"""Serve the click-through training-label page on this machine only (http://127.0.0.1:8765).

    python reviews/2026-10-20/label-page/serve_label_page.py [--packet PACKET_DIR] [--data DATA_DIR] [--port 8765]

Run with ArcGIS Pro's Python or any Python with numpy (label_page.bat serve does it). Listens on 127.0.0.1 only. Serves the
page beside this file and the data that build_label_data.py wrote. Each answer is checked with training_review.normalize_answer,
the same check `restore` applies, and kept in `<data>/answers/label-page-answers.csv` (backup format, one row per unit).
Nothing here touches the review geodatabase: import the answers with
    training_labels.bat restore --csv <that CSV>            (preview)
    training_labels.bat restore --csv <that CSV> --apply
which writes only units that are still blank in the geodatabase unless you add --replace.

Higher-resolution imagery for the map panel comes from `<data>/imagery-layers.json`, a list of XYZ tile layers you add yourself
(see imagery-layers.example.json beside this file). It lives on the SSD, never in git, because a licensed UGRC Discover link
is unique to the organisation and must not be shared outside it. The server only hands the list to the page on 127.0.0.1.
"""
import argparse
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading
import urllib.parse

HERE = Path(__file__).resolve().parent
TOOLBOX = HERE.parents[2]
sys.path.insert(0, str(TOOLBOX))
from canopy import training_review as tr  # noqa: E402
from canopy.lidar_root import lidar_root  # noqa: E402

PACKET = lidar_root()/"2023-salt-lake-valley"/"runs"/"pilot-2026-09-29"/"training-review"/"packet-20260929"
STATIC = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
CSV_NAME = "label-page-answers.csv"
IMAGERY_NAME = "imagery-layers.json"


def imagery_layers(data_dir):
    """The user's tile layers, checked for shape; an absent file means none. Values are passed through, never logged."""
    path = Path(data_dir)/IMAGERY_NAME
    if not path.exists():
        return {"layers": [], "file": str(path)}
    layers = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(layers, list):
        raise ValueError(f"{path} must hold a JSON list of layers")
    out = []
    for layer in layers:
        url = str(layer.get("url", ""))
        kind = str(layer.get("type") or "xyz").lower()
        if kind == "wms":
            # A WMS such as a Nearmap Custom WMS: one named layer (for Nearmap, one survey date) drawn in web-map tiles.
            if not url.startswith("https://") or not layer.get("layers"):
                raise ValueError(f"{path}: WMS layer {layer.get('name')!r} needs an https URL and 'layers'")
        elif not url.startswith("https://") or not all(k in url for k in ("{z}", "{x}", "{y}")):
            raise ValueError(f"{path}: layer {layer.get('name')!r} needs an https URL with {{z}}, {{x}} and {{y}}")
        out.append({"name": str(layer.get("name") or "imagery"), "type": kind, "url": url,
                    "layers": str(layer.get("layers") or ""), "format": str(layer.get("format") or "image/jpeg"),
                    "attribution": str(layer.get("attribution") or ""), "date": str(layer.get("date") or ""),
                    "maxNativeZoom": int(layer.get("maxNativeZoom") or 19)})
    return {"layers": out, "file": str(path)}


class Store:
    """The page's answers, validated against the packet and saved as a backup-format CSV after every change."""

    def __init__(self, packet_dir, data_dir):
        packet = json.loads((Path(packet_dir)/"packet.json").read_text(encoding="utf-8"))
        if packet.get("schema") != tr.SCHEMA or tr.units_digest(packet["units"]) != packet["units_digest"]:
            raise ValueError("Not an unaltered training review packet")
        self.frame = tr.check_frame(packet["frame"])
        self.units = {u["UNIT_ID"]: u for u in packet["units"]}
        built = json.loads((Path(data_dir)/"units.json").read_text(encoding="utf-8"))
        if built["packet_units_digest"] != packet["units_digest"]:
            raise ValueError("The page data was built from a different packet")
        self.path = Path(data_dir)/"answers"/CSV_NAME
        self.log = self.path.with_name("label-page-log.jsonl")      # append-only record of every save and clear
        self.path.parent.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.rows = {r["UNIT_ID"]: r for r in tr.read_backup(self.path)} if self.path.exists() else {}

    def answer(self, payload, client=None):
        uid = payload.get("UNIT_ID")
        unit = self.units.get(uid)
        if unit is None:
            raise ValueError(f"{uid}: not a unit of this packet")
        with self.lock:
            if not (payload.get("LABEL") or "").strip():
                self.rows.pop(uid, None)                    # cleared on the page: nothing to import for this unit
            else:
                answer = tr.normalize_answer(unit, {**payload, "REVIEW_DATE": datetime.date.today().isoformat()}, self.frame)
                self.rows[uid] = {"UNIT_ID": uid, "QUEUE": unit["QUEUE"], "REVIEW_ORDER": unit["REVIEW_ORDER"],
                                  "UNIT_TOKEN": tr.unit_token(self.frame["digest"], unit), **answer, "CHECK": "OK"}
            self._save()
            with open(self.log, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"time": datetime.datetime.now().isoformat(timespec="seconds"), "UNIT_ID": uid,
                                         "LABEL": (payload.get("LABEL") or "").strip() or None,
                                         "REVIEWER": payload.get("REVIEWER"), "client": client}) + "\n")
        return self.rows.get(uid)

    def _save(self):
        ordered = sorted(self.rows.values(), key=lambda r: (int(r["REVIEW_ORDER"]), r["UNIT_ID"]))
        partial = self.path.with_suffix(".partial")
        partial.write_text(tr.backup_csv(ordered), encoding="utf-8")
        os.replace(partial, self.path)

    def state(self):
        with self.lock:
            return {"csv": str(self.path), "answers": {uid: {k: r.get(k) for k in ("LABEL", "IMAGERY_USABLE", "NOTES", "REVIEWER",
                                                                                   "REVIEW_DATE", "LABEL_BELOW", "SPLIT_Z")}
                                                         for uid, r in self.rows.items()}}


def handler(store, data_dir):
    data_dir = Path(data_dir).resolve()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path in STATIC:
                file = HERE/STATIC[path]
            elif path == "/api/state":
                return self._send(200, store.state())
            elif path == "/api/imagery":
                try:
                    return self._send(200, imagery_layers(data_dir))
                except (ValueError, json.JSONDecodeError) as exc:
                    return self._send(200, {"layers": [], "file": str(data_dir/IMAGERY_NAME), "error": str(exc)})
            elif path.startswith("/data/"):
                file = (data_dir/urllib.parse.unquote(path[len("/data/"):])).resolve()
                if data_dir not in file.parents:
                    return self._send(403, {"error": "outside the data folder"})
            else:
                return self._send(404, {"error": "not found"})
            if not file.is_file():
                return self._send(404, {"error": "not found"})
            self._send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")

        def do_POST(self):
            if urllib.parse.urlparse(self.path).path != "/api/answer":
                return self._send(404, {"error": "not found"})
            try:
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                return self._send(200, {"saved": store.answer(payload, self.headers.get("User-Agent", "")[:120])})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})

        def log_message(self, *args):
            pass

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    data = args.data or args.packet/"label-page"
    store = Store(args.packet, data)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(store, data))
    print(f"Label page: http://127.0.0.1:{args.port}/   (answers: {store.path})", flush=True)
    print("Close this window or press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
