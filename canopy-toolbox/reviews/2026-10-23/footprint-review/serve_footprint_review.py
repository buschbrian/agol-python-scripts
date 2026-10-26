"""Serve the footprint review page on this machine only (http://127.0.0.1:8770).

    python reviews/2026-10-23/footprint-review/serve_footprint_review.py --data DATA [--port 8770]
    python reviews/2026-10-23/footprint-review/serve_footprint_review.py backup --data DATA [--replace]

Any Python 3 (footprint_review.bat uses ArcGIS Pro's). Listens on 127.0.0.1 only; serves the page beside this file and the
data build_review_data.py wrote. Modelled on the October 20 label page:
- Every answer is checked: a known item, an answer allowed for its queue, initials. A note is optional.
- Answers are kept in DATA/answers/footprint-review-answers.csv, one row per item, rewritten atomically (a partial file
  then a rename) after every change, with an append-only DATA/answers/footprint-review-log.jsonl.
- An answer by one reviewer is never overwritten or cleared by another; the server refuses. A reviewer can change or
  clear their own.
- `backup` copies the answers into the repo (reviews/2026-10-23/footprint-review/answers/footprint-review-answers.csv).
  An answer already there is never changed or removed unless --replace; new ones are added.
"""
import argparse
import csv
import datetime
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading
import urllib.parse

HERE = Path(__file__).resolve().parent
STATIC = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
ANSWERS = {
    "candidates": ("ACCEPT", "PART_OF_EXISTING", "VEHICLE", "REJECT", "UNSURE"),
    "county": ("DEMOLISHED", "STILL_THERE", "MISPLACED", "UNSURE"),
    "newbuild": ("NEW_BUILDING", "NO_BUILDING", "UNSURE"),
    # October 23: what the red LiDAR piece is, beside the magenta county outline (codes of the first version kept)
    "pairs": ("OFFSET", "PART_OF_EXISTING", "BOTH_REAL", "REBUILT", "NOT_A_BUILDING", "UNSURE"),
    # October 26 (reviews/2026-10-26/model-review): footprints the 3D buildings modelled without a roofer LoD2.2 roof,
    # and the CFTree tree models
    "models": ("SIMPLE_OK", "NEEDS_ROOF", "GONE", "OUTLINE_WRONG", "UNDER_TREES", "UNSURE"),
    # October 26, after Brian's first answers: shrubs, brush and roofs taken in with a tree (UNSURE moved from 6 to 9;
    # he had not used it)
    "trees": ("ONE_TREE", "MERGED", "PART_OF_TREE", "NOT_A_TREE", "SHAPE_WRONG", "SHRUBS", "BRUSH", "TREE_WITH_ROOF",
              "UNSURE"),
    "tree_seams": ("SAME_TREE", "SPLIT_TREE", "SEPARATE_TREES", "NOT_A_TREE", "UNSURE"),
    "tree_rejects": ("MISSED_TREE", "NOT_A_TREE", "UNSURE"),
}
COLUMNS = ("ITEM_ID", "QUEUE", "GROUP", "ANSWER", "NOTE", "REVIEWER", "REVIEW_DATE", "REVIEW_TIME")
REPO_BACKUP = HERE/"answers"/"footprint-review-answers.csv"


def read_csv(path):
    if not Path(path).exists():
        return {}
    with open(path, newline="", encoding="utf-8") as handle:
        return {r["ITEM_ID"]: r for r in csv.DictReader(handle) if (r.get("ANSWER") or "").strip()}


def write_csv(path, rows, order):
    text = io.StringIO()
    w = csv.DictWriter(text, COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows({k: r.get(k, "") for k in COLUMNS} for r in sorted(rows.values(), key=lambda r: order.get(r["ITEM_ID"], 1e9)))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    partial.write_text(text.getvalue(), encoding="utf-8")
    os.replace(partial, path)


class Store:
    def __init__(self, data_dir):
        index = json.loads((Path(data_dir)/"index.json").read_text(encoding="utf-8"))
        self.items = {it["id"]: it for it in index["items"]}
        self.order = {it["id"]: it["order"] for it in index["items"]}
        self.path = Path(data_dir)/"answers"/"footprint-review-answers.csv"
        self.log = self.path.with_name("footprint-review-log.jsonl")
        self.lock = threading.Lock()
        self.rows = read_csv(self.path)
        unknown = set(self.rows) - set(self.items)
        if unknown:
            raise ValueError(f"{len(unknown)} saved answers are for items this data does not have, e.g. {sorted(unknown)[:3]}")

    def answer(self, payload, client=None):
        item_id = payload.get("ITEM_ID")
        item = self.items.get(item_id)
        if item is None:
            raise ValueError(f"{item_id}: not an item of this review")
        answer = (payload.get("ANSWER") or "").strip()
        reviewer = (payload.get("REVIEWER") or "").strip()[:40]
        note = " ".join(str(payload.get("NOTE") or "").split())[:500]
        if not reviewer:
            raise ValueError("Type your initials first (Initials box, top right)")
        if answer and answer not in ANSWERS[item["queue"]]:
            raise ValueError(f"{answer}: not an answer for the {item['queue']} queue")
        with self.lock:
            old = self.rows.get(item_id)
            if old and old["REVIEWER"] != reviewer:
                raise ValueError(f"{item_id} was answered by {old['REVIEWER']}; another reviewer's answer is never changed here")
            if not answer:
                self.rows.pop(item_id, None)
            else:
                now = datetime.datetime.now()
                self.rows[item_id] = {"ITEM_ID": item_id, "QUEUE": item["queue"], "GROUP": item["group"], "ANSWER": answer,
                                      "NOTE": note, "REVIEWER": reviewer, "REVIEW_DATE": now.date().isoformat(),
                                      "REVIEW_TIME": now.time().isoformat(timespec="seconds")}
            write_csv(self.path, self.rows, self.order)
            with open(self.log, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"time": datetime.datetime.now().isoformat(timespec="seconds"), "ITEM_ID": item_id,
                                         "ANSWER": answer or None, "NOTE": note or None, "REVIEWER": reviewer,
                                         "client": client}) + "\n")
        return self.rows.get(item_id)

    def state(self):
        with self.lock:
            return {"csv": str(self.path), "answers": {k: {c: r[c] for c in ("ANSWER", "NOTE", "REVIEWER", "REVIEW_DATE")}
                                                        for k, r in self.rows.items()}}


def backup(data_dir, replace=False):
    """Merge the page's answers into the repo copy; existing repo answers are kept unless replace."""
    store = Store(data_dir)
    repo = read_csv(REPO_BACKUP)
    added = changed = kept = 0
    for item_id, row in store.rows.items():
        old = repo.get(item_id)
        if old is None:
            repo[item_id] = row
            added += 1
        elif any(old.get(k) != row.get(k) for k in ("ANSWER", "NOTE", "REVIEWER")):
            if replace:
                repo[item_id] = row
                changed += 1
            else:
                kept += 1
    write_csv(REPO_BACKUP, repo, store.order)
    print(f"{REPO_BACKUP}: {added} added, {changed} replaced, {kept} differing kept as they were "
          f"({'--replace to take the page answers' if kept else 'nothing differs'}); {len(repo)} answers in the backup")


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
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "backup":
        p = argparse.ArgumentParser(description="Copy the page's answers into the repo")
        p.add_argument("--data", type=Path, required=True)
        p.add_argument("--replace", action="store_true")
        a = p.parse_args(argv[1:])
        return backup(a.data, a.replace)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--port", type=int, default=8770)
    a = p.parse_args(argv)
    store = Store(a.data)
    server = ThreadingHTTPServer(("127.0.0.1", a.port), handler(store, a.data))
    print(f"Footprint review: http://127.0.0.1:{a.port}/   (answers: {store.path})", flush=True)
    print("Close this window or press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
