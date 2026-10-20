"""Run the FRACTAL fine-tune end to end once the A4000 and memory are free: smoke test, fine-tune, predict, score.

    python reviews/2026-10-20/fractal-finetune/run_finetune.py RUN_DIR [--wait-for-log FILE] [--skip-smoke]

Run with the Myria3D environment's Python (PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set) after make_config.py and create_hdf5.
RUN_DIR holds finetune.yaml and dataset.hdf5. Steps, each logged to RUN_DIR/driver.log; the first failure stops the chain:
0. wait: with --wait-for-log, until a line containing "finished;" is appended to FILE (the Esri building run's log); then until
   commit headroom is at least MIN_COMMIT_GB, never starting below it (the October 20 crashes began at the commit limit);
1. smoke: 5 training and 3 validation batches for one epoch into RUN_DIR/smoke, so a config error costs a minute, not an hour;
2. fine-tune into RUN_DIR (checkpoints/, logs/, hydra/);
3. predict: repeat.py, three passes of the best checkpoint over the colourised 12TVL2804, into RUN_DIR/predict-12TVL2804;
4. score: evaluate_finetune.py on the held-out labels, released consensus against the fine-tuned consensus, to
   RUN_DIR/evaluation.json.
Nothing here writes outside RUN_DIR.
"""
import argparse
import datetime
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(HERE.parents[1].parent/"2026-10-19"/"fractal-city"))
from infer_city import commit_headroom_gb  # noqa: E402

CHECKOUT = Path(r"C:\Users\bbusch\tools\myria3d")
FRACTAL = Path(r"D:\lidar\2023-salt-lake-valley\fractal")
COLOURISED = FRACTAL/"city-20261019"/"colorized"/"12TVL2804.las"
RELEASED = FRACTAL/"city-20261019"/"fractal"/"12TVL2804"/"consensus.las"
LABELS = FRACTAL/"finetune-20261020"/"data"/"val"/"12TVL2804.las"
MIN_COMMIT_GB = 8.0
POLL_SECONDS = 60


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--wait-for-log", type=Path)
    parser.add_argument("--skip-smoke", action="store_true")
    args = parser.parse_args(argv)
    run = args.run_dir.resolve()
    if not (run/"finetune.yaml").is_file() or not (run/"dataset.hdf5").is_file():
        raise FileNotFoundError(f"{run} needs finetune.yaml and dataset.hdf5 (make_config.py, then create_hdf5)")
    for name in ("checkpoints", "predict-12TVL2804", "evaluation.json"):
        if (run/name).exists():
            raise FileExistsError(run/name)
    driver_log = open(run/"driver.log", "a", encoding="utf-8")

    def log(text):
        line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {text}"
        print(line, flush=True)
        driver_log.write(line+"\n")
        driver_log.flush()

    def step(name, command, cwd, log_name):
        log(f"{name}: starting")
        started = time.time()
        with open(run/log_name, "w", encoding="utf-8") as out:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT)
        log(f"{name}: exit {result.returncode} after {time.time()-started:.0f} s (log {log_name})")
        if result.returncode:
            raise SystemExit(f"{name} failed; see {run/log_name}")

    env = dict(os.environ, PYTHONNOUSERSITE="1", LOGS_DIR=str(run/"logs"))
    env["PATH"] = os.pathsep.join([str(Path(sys.prefix)/"Library"/"bin"), env.get("PATH", "")])
    if args.wait_for_log:
        offset = args.wait_for_log.stat().st_size
        log(f"waiting for 'finished;' in {args.wait_for_log}")
        while True:
            with open(args.wait_for_log, encoding="utf-8", errors="replace") as handle:
                handle.seek(offset)
                if "finished;" in handle.read():
                    break
            time.sleep(POLL_SECONDS)
        log("the run being waited for has finished")
    while (free := commit_headroom_gb()) is not None and free < MIN_COMMIT_GB:
        log(f"waiting: {free:.1f} GB commit headroom, need {MIN_COMMIT_GB:.0f} GB")
        time.sleep(10*POLL_SECONDS)
    log(f"commit headroom {free} GB")
    base = [sys.executable, str(CHECKOUT/"run.py"), "--config-path", str(run), "--config-name", "finetune.yaml",
            "task.task_name=finetune"]
    if not args.skip_smoke:
        smoke = run/"smoke"
        step("smoke", base+["trainer.max_epochs=1", "+trainer.limit_train_batches=5", "+trainer.limit_val_batches=3",
                            f"callbacks.model_checkpoint.dirpath={(smoke/'checkpoints').as_posix()}",
                            f"logger.csv.save_dir={(smoke/'logs').as_posix()}", f"hydra.run.dir={(smoke/'hydra').as_posix()}"],
             CHECKOUT, "smoke.log")
    step("fine-tune", base+[f"hydra.run.dir={(run/'hydra').as_posix()}"], CHECKOUT, "finetune.log")
    best = sorted(p for p in (run/"checkpoints").glob("epoch_*.ckpt"))
    if not best:
        raise SystemExit("the fine-tune left no best checkpoint")
    log(f"best checkpoint {best[-1].name}")
    step("predict", [sys.executable, str(TOOLBOX/"reviews"/"2026-09-30"/"fractal"/"repeat.py"), str(COLOURISED),
                     str(run/"predict-12TVL2804"), "--checkpoint", str(best[-1]), "--pass-retries", "2"],
         TOOLBOX, "predict.log")
    step("score", [sys.executable, str(HERE.parent/"evaluate_finetune.py"), str(LABELS), f"released={RELEASED}",
                   f"finetuned={run/'predict-12TVL2804'/'consensus.las'}", "--out", str(run/"evaluation.json")],
         TOOLBOX, "score.log")
    log("all steps complete; see evaluation.json")


if __name__ == "__main__":
    main()
