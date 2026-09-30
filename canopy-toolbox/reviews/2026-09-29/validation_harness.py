"""Validation harness for the three pilot tiles: sample, review layers, chips, score.

Run with ArcGIS Pro Python from canopy-toolbox. See VALIDATION.md.

  python reviews/2026-09-29/validation_harness.py sample
  python reviews/2026-09-29/validation_harness.py layers
  python reviews/2026-09-29/validation_harness.py chips --url-file PATH [--per-stratum 4]
  python reviews/2026-09-29/validation_harness.py score [--run NAME=TEMPLATE ...]
        [--flags NAME BASE_TEMPLATE TABLE_TEMPLATE FIELD VALUE[,VALUE]]
  python reviews/2026-09-29/validation_harness.py export-labels --packet-dir PATH [--batch 1|2|all]
  python reviews/2026-09-29/validation_harness.py import-labels PATH/labels.csv
        [--packet PATH/packet.json] [--apply --audit-dir NEW_PATH] [--replace-existing]

TEMPLATE paths may contain {root} and {tile}. Without --run, score looks for the
baseline, refine-roofs, roof-local and deep-learning folders and skips absent ones.
"""
import argparse
import datetime
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from canopy.lidar_root import lidar_root, live  # noqa: E402
ROOT = lidar_root() / "2023-salt-lake-valley" / "runs" / "pilot-2026-09-29"
VALIDATION = ROOT / "validation"
TILES = {"12TVL2804": (428000, 4504000, 429000, 4505000),
         "12TVL3302": (433000, 4502000, 434000, 4503000),
         "12TVL2203": (422000, 4503000, 423000, 4504000)}
SEED = 20260929
DEFAULT_RUNS = [("baseline", r"{root}\{tile}\run"),
                ("refine-roofs", r"{root}\{tile}\run-refined"),
                ("roof-local", r"{root}\roof-local\{tile}\run"),
                ("deep-learning", r"{root}\deep-learning\{tile}")]
WMS_LAYER = "area/3edcdbe1-6e38-445e-8c5c-96e9cb23e2c5/all/all-combined"
CHIP_M, CHIP_PX = 40.0, 400
MAX_CHIPS = 300


def resolve(template, tile, root):
    """A run folder for one tile, or None. Looks one level down when run.json is not
    directly in the folder and exactly one subfolder has one."""
    folder = Path(template.format(root=root, tile=tile))
    if (folder / "run.json").is_file():
        return folder
    if folder.is_dir():
        below = [p.parent for p in folder.glob("*/run.json")]
        if len(below) == 1:
            return below[0]
    return None


def cmd_sample(args):
    from canopy import validation
    document = validation.build_reference(args.root, TILES, args.out, args.seed)
    for entry in document["strata"]:
        print(f"{entry['sample']:9s} {entry['tile']} {entry['stratum']:13s} "
              f"population {entry['population']:>9,}  sampled {entry['sampled']:>3}")
    print(f"Reference: {Path(args.out) / 'reference.gdb'}")


def cmd_layers(args):
    from canopy import validation
    document = json.loads((Path(args.out) / "sample_design.json").read_text(encoding="utf-8"))
    chm, crowns = {}, {}
    for tile in document["tiles"]:
        outputs, _ = validation.run_outputs(live(document["root"]) / tile / document["run_name"])
        chm[tile], crowns[tile] = outputs["chm"], outputs["crowns"]
    result = validation.review_layers(Path(args.out) / "reference.gdb", Path(args.out) / "review",
                                      chm, crowns)
    print(json.dumps(result, indent=2))


def cmd_score(args):
    from canopy import validation
    runs = []
    templates = [tuple(r.split("=", 1)) for r in args.run] if args.run else DEFAULT_RUNS
    for name, template in templates:
        folders = {t: f for t in TILES if (f := resolve(template, t, args.root)) is not None}
        if folders:
            runs.append({"name": name, "folders": folders})
        else:
            print(f"skip {name}: no run.json under {template}")
    for name, base, table, field, values in args.flags or []:
        folders, drop = {}, {}
        for tile in TILES:
            folder = resolve(base, tile, args.root)
            path = table.format(root=args.root, tile=tile)
            if folder is None:
                continue
            try:
                drop[tile] = validation.flagged_ids(path, field, values.split(","))
            except Exception as exc:  # flags are produced elsewhere and may not exist yet
                print(f"skip {name} {tile}: cannot read flags ({exc})")
                continue
            folders[tile] = folder
        if folders:
            runs.append({"name": name, "folders": folders, "drop": drop})
    out = Path(args.out) / "scores" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    report = validation.score(Path(args.out) / "reference.gdb", runs, out, args.replicates, args.seed)
    print(validation._summary(report))
    for name, entry in report["runs"].items():
        for tile, reason in entry["skipped"].items():
            print(f"  {name} {tile} skipped: {reason}")
        for scope, result in entry["scopes"].items():
            info = result["inputs"]
            new = sum(i["new_candidates"] for i in info.values())
            kept = sum(result["treetops"]["retained_by_stratum"].values())
            print(f"  {name} {scope}: {sum(i['run_candidates'] for i in info.values()):,} candidates, "
                  f"{kept} of {result['treetops']['units']} sampled baseline candidates kept, "
                  f"{new:,} candidates outside the sampling frame; "
                  f"crowns changed {result['crowns']['changed_by_run']}")
    print()
    print(report["table"])
    print(f"\nReport: {out}")


def cmd_export_labels(args):
    from canopy import validation
    manifest = validation.export_labels(Path(args.out) / 'reference.gdb', args.packet_dir,
                                       None if args.batch == 'all' else int(args.batch))
    print(json.dumps({'packet': str(Path(args.packet_dir).resolve()),
                      'batch': manifest['batch'], 'exported_counts': manifest['exported_counts']}, indent=2))


def cmd_import_labels(args):
    from canopy import validation
    packet = args.packet or Path(args.csv).parent / 'packet.json'
    result = validation.import_labels(Path(args.out) / 'reference.gdb', args.csv, packet,
        apply=args.apply, audit_folder=args.audit_dir, replace_existing=args.replace_existing)
    print(json.dumps({k: v for k, v in result.items() if k != 'changes'}, indent=2))


# ---------------------------------------------------------------- chips (scratch only)

def _wms_base(url_file):
    base = Path(url_file).read_text(encoding="utf-8").strip()
    if not base.lower().startswith("https://"):
        raise SystemExit("The WMS URL file must hold one https URL")
    return base


def _chip(base, x, y):
    half = CHIP_M / 2
    query = urllib.parse.urlencode({
        "service": "WMS", "request": "GetMap", "version": "1.1.1", "layers": WMS_LAYER,
        "styles": "", "srs": "EPSG:26912", "format": "image/jpeg",
        "bbox": f"{x-half:.2f},{y-half:.2f},{x+half:.2f},{y+half:.2f}",
        "width": CHIP_PX, "height": CHIP_PX})
    url = base + ("&" if "?" in base else "?") + query
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            kind = response.headers.get("Content-Type", "")
            data = response.read()
    except Exception as exc:  # never echo the URL: it carries the key
        raise RuntimeError(f"WMS request failed ({type(exc).__name__})") from None
    if not kind.startswith("image/"):
        raise RuntimeError(f"WMS returned {kind or 'no content type'}, not an image")
    return data


def cmd_chips(args):
    from PIL import Image, ImageDraw
    from canopy import validation
    units, _ = validation.read_reference(Path(args.out) / "reference.gdb")
    base = _wms_base(args.url_file)
    folder = Path(args.out) / "scratch" / "chips"
    groups = {}
    for sample in args.samples:
        for unit in sorted(units[sample], key=lambda u: u["REVIEW_ORDER"]):
            key = (sample, unit["TILE"], unit["STRATUM"])
            if len(groups.setdefault(key, [])) < args.per_stratum:
                groups[key].append(unit)
    planned = sum(len(v) for v in groups.values())
    if planned > MAX_CHIPS:
        raise SystemExit(f"{planned} chips requested; the limit is {MAX_CHIPS}")
    requests = 0
    scale = CHIP_PX / CHIP_M
    for (sample, tile, stratum), members in sorted(groups.items()):
        tiles = []
        for unit in members:
            cache = folder / "raw" / f"{unit['SAMPLE_ID']}.jpg"
            if not cache.is_file():
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(_chip(base, unit["x"], unit["y"]))
                requests += 1
            image = Image.open(cache).convert("RGB")
            draw = ImageDraw.Draw(image)
            c = CHIP_PX / 2
            for radius, colour in ((1.0, (255, 0, 255)), (3.0, (255, 255, 0))):
                r = radius*scale
                draw.ellipse((c-r, c-r, c+r, c+r), outline=colour, width=2)
            draw.rectangle((0, 0, CHIP_PX, 22), fill=(0, 0, 0))
            draw.text((6, 5), f"{unit['SAMPLE_ID']}  {CHIP_M:.0f} m", fill=(255, 255, 255))
            tiles.append(image)
        columns = min(len(tiles), 4)
        rows = -(-len(tiles) // columns)
        sheet = Image.new("RGB", (columns*CHIP_PX, rows*CHIP_PX + 30), (255, 255, 255))
        ImageDraw.Draw(sheet).text((8, 8), f"{sample} / {tile} / {stratum}  (circles 1 m and 3 m; "
                                   "Nearmap Aug 2023; NAD83 vs NAD83(2011) about 1 m)", fill=(0, 0, 0))
        for i, image in enumerate(tiles):
            sheet.paste(image, ((i % columns)*CHIP_PX, 30 + (i // columns)*CHIP_PX))
        path = folder / f"{sample}-{tile}-{stratum}.jpg"
        sheet.save(path, quality=88)
    print(f"{planned} chips in {len(groups)} contact sheets; {requests} new WMS requests; {folder}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--out", default=str(VALIDATION))
    commands = parser.add_subparsers(dest="command", required=True)
    sample = commands.add_parser("sample", help="Draw the stratified reference sample (once)")
    sample.add_argument("--seed", type=int, default=SEED)
    commands.add_parser("layers", help="Write review .lyrx files and a review .aprx")
    chips = commands.add_parser("chips", help="Nearmap contact sheets per stratum (scratch only)")
    chips.add_argument("--url-file", required=True)
    chips.add_argument("--per-stratum", type=int, default=4)
    chips.add_argument("--samples", nargs="+", default=["treetop", "omission"],
                       choices=["treetop", "omission", "cell", "crown"])
    score = commands.add_parser("score", help="Score run folders against the labels")
    score.add_argument("--run", action="append", help="NAME=TEMPLATE, repeatable")
    score.add_argument("--flags", action="append", nargs=5,
                       metavar=("NAME", "BASE_TEMPLATE", "TABLE_TEMPLATE", "FIELD", "VALUES"),
                       help="Score BASE with candidates whose FIELD is in VALUES removed")
    score.add_argument("--replicates", type=int, default=2000)
    score.add_argument("--seed", type=int, default=0)
    export = commands.add_parser('export-labels', help='Write a blind worksheet for the fixed reference')
    export.add_argument('--packet-dir', required=True)
    export.add_argument('--batch', choices=['1', '2', 'all'], default='1')
    imports = commands.add_parser('import-labels', help='Validate labels; preview by default')
    imports.add_argument('csv')
    imports.add_argument('--packet', type=Path)
    imports.add_argument('--apply', action='store_true')
    imports.add_argument('--audit-dir', type=Path)
    imports.add_argument('--replace-existing', action='store_true')
    args = parser.parse_args(argv)
    {"sample": cmd_sample, "layers": cmd_layers, "chips": cmd_chips, "score": cmd_score,
     'export-labels': cmd_export_labels, 'import-labels': cmd_import_labels}[args.command](args)


if __name__ == "__main__":
    main()
