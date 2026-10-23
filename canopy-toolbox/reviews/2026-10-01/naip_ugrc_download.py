"""Download UGRC NAIP quarter-quad sheets (public, no sign-in) into a folder, check them and unzip them.

    python reviews/2026-10-01/naip_ugrc_download.py DEST_DIR [--year 2024] [--quads q1320_nw q1320_sw] [--check]

Defaults are the two NAIP 2024 quarter-quads that cover tile 12TVL2804 (north-west and south-west of quad 1320), each as an RGB
file and a B4 file (about 86 MB in all). --check only asks the server for the file sizes and downloads nothing. Files already in
DEST_DIR are never overwritten: an existing zip is re-checked, an existing extracted folder is left alone. Then run
naip_local_tile.py with --sheets DEST_DIR. The bucket is UGRC's public download store behind raster.utah.gov.
"""
import argparse
from pathlib import Path
import zipfile

import requests

BUCKET = "https://storage.googleapis.com/state-of-utah-sgid-downloads/aerial-photography/naip"
DEFAULT_QUADS = ("q1320_nw", "q1320_sw")
KINDS = ("RGB", "B4")


def sheet_urls(year, quads):
    """{(file stem): url} for every quad and kind."""
    return {f"{q}_NAIP{year}_{k}": f"{BUCKET}/naip{year}/{q}_NAIP{year}_{k}.zip" for q in quads for k in KINDS}


def fetch(stem, url, dest, check_only, session=requests):
    zip_path = Path(dest)/f"{stem}.zip"
    head = session.head(url, timeout=60, allow_redirects=True)
    head.raise_for_status()
    size = int(head.headers["Content-Length"])
    if check_only:
        return {"file": stem, "bytes": size, "status": "available"}
    if not zip_path.exists():
        with session.get(url, stream=True, timeout=300) as response:
            response.raise_for_status()
            with zip_path.open("xb") as handle:
                for chunk in response.iter_content(1 << 20):
                    handle.write(chunk)
    if zip_path.stat().st_size != size:
        raise RuntimeError(f"{zip_path}: {zip_path.stat().st_size} bytes on disk, server says {size}")
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"{zip_path}: corrupt member {bad}")
        folder = Path(dest)/stem
        if not folder.exists():
            archive.extractall(folder)
    return {"file": stem, "bytes": size, "status": "downloaded and checked"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("dest", type=Path)
    p.add_argument("--year", default="2024")
    p.add_argument("--quads", nargs="+", default=list(DEFAULT_QUADS))
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    args.dest.mkdir(parents=True, exist_ok=True)
    total = 0
    for stem, url in sheet_urls(args.year, args.quads).items():
        result = fetch(stem, url, args.dest, args.check)
        total += result["bytes"]
        print(f"{result['file']}: {result['bytes']:,} bytes, {result['status']}")
    print(f"total {total:,} bytes")


if __name__ == "__main__":
    main()
