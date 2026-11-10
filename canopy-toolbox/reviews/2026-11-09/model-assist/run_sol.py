"""Run a footprint batch folder through GPT-6.1 Sol in the Codex CLI, blind, a few sheets per call.

    run_sol.py BATCH_DIR OUT_DIR [--workers 4] [--chunk 15]

BATCH_DIR holds batch_*.json from export_sheets.py. OUT_DIR/footprints receives the same batches and result_NN.jsonl.
"""

import argparse
import concurrent.futures as futures
import json
import shutil
import subprocess
from pathlib import Path

MODEL, EFFORT = "gpt-6.1-sol", "high"
BRIEF = """Blind visual review of LiDAR building outlines in Millcreek, Utah. Do not use any tools or open any file.

The attached images are review sheets, in the same order as the items below. Left panel: LiDAR surface, autumn 2023. Grey
hillshade is ground, green is tree canopy 2 m or taller, yellow through orange to magenta is a roof from 0 m to 12 m or taller.
Right panel: NAIP imagery, July 2024, same extent. Lines: RED is the LiDAR outline in question, WHITE is the county footprint,
CYAN is another LiDAR outline, MAGENTA is the county outline in question. The imagery is newer than the LiDAR and can sit up
to about 2 m off it, so a small shift between panels alone is not evidence of an offset county outline.

Tasks: reshaped and tangle, the red LiDAR outline and the county outline disagree, which geometry fix is right? small, what is
this small LiDAR-only red outline? kept, the county outline has little or no LiDAR roof under it, is that building still
there? joins, one LiDAR building lies over several county outlines, which is right?

Pick exactly one code from the item's task. Use UNSURE when the sheet does not settle it. Confidence: high only when the sheet
clearly settles it, medium for a likely reading, low otherwise.

Reply with one JSON object per line and nothing else, one per item in order:
{"id":"...","answer":"CODE","confidence":"high|medium|low","note":"under 15 words on what you saw"}

Options by task:
"""


def call(codex, tasks, part, cwd, log):
    listing = "\n".join(f"{n + 1}. id {i['id']}, task {i['task']}, facts {json.dumps(i['facts'], ensure_ascii=False)}" for n, i in enumerate(part))
    options = "\n".join(f"{t}: " + "; ".join(f"{c} = {d}" for c, d in opts) for t, opts in tasks.items())
    prompt = f"{BRIEF}{options}\n\nItems:\n{listing}\n"
    args = [codex, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-m", MODEL, "-c", f"model_reasoning_effort={EFFORT}"]
    for item in part:
        args += ["-i", Path(item["sheet"]).name]
    args += ["-o", str(log), "--", "-"]
    for _ in range(2):
        done = subprocess.run(args, input=prompt, text=True, encoding="utf-8", capture_output=True, cwd=cwd, timeout=1800)
        rows = []
        if log.exists():
            rows = [json.loads(s) for s in log.read_text(encoding="utf-8").splitlines() if s.strip().startswith("{")]
        if [r.get("id") for r in rows] == [i["id"] for i in part]:
            return rows
        log.with_suffix(".err").write_text(done.stdout[-3000:] + done.stderr[-3000:], encoding="utf-8")
    raise SystemExit(f"{log.name}: answers did not match the items")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("batches", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk", type=int, default=15)
    a = parser.parse_args()
    codex = shutil.which("codex")
    dest = a.out / "footprints"
    dest.mkdir(parents=True, exist_ok=True)
    tasks, items = None, []
    for path in sorted(a.batches.glob("batch_*.json")):
        batch = json.loads(path.read_text(encoding="utf-8"))
        tasks = batch["tasks"]
        items += batch["items"]
    (dest / "batch_01.json").write_text(json.dumps({"tasks": tasks, "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    cwd = Path(items[0]["sheet"]).parent
    parts = [items[n:n + a.chunk] for n in range(0, len(items), a.chunk)]
    with futures.ThreadPoolExecutor(a.workers) as pool:
        jobs = [pool.submit(call, codex, tasks, part, cwd, dest / f"chunk_{n + 1:03d}.out") for n, part in enumerate(parts)]
        rows = [row for job in jobs for row in job.result()]
    (dest / "result_01.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"{len(rows)} answers from {MODEL} at {EFFORT}")


if __name__ == "__main__":
    main()
