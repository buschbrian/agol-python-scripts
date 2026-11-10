"""Assemble Millcreek raster products from verified October 8 cores; no inference.

Run with ArcGIS Pro Python and PYTHONNOUSERSITE=1. Each native tile job uses a
fresh process. Source rasters and LAS are read-only; all outputs use a new folder.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import arcpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy import common, licensing

PRODUCTS = {
    "chm": "core_chm.tif", "terrain": "dtm.tif", "roof_elevation": "dsm_building.tif",
    "vegetation_support": "vegetation_support.tif", "observed": "observed.tif",
    "building_occlusion": "building_occlusion.tif", "roof_height": "roof_height_m.tif",
}
MASKS = {"vegetation_support", "observed", "building_occlusion"}
WARNING = ("Unvalidated 2023 lidar planning estimates. Roof height is measured class-6 "
           "first/single-return elevation minus interpolated terrain at the same cell; "
           "it is not a surveyed or code-defined building height. Missing cells remain NoData.")


def fingerprint(paths):
    return {str(p): [p.stat().st_size, p.stat().st_mtime_ns] for p in paths}


def values(path):
    if arcpy.Raster(str(path)).pixelType in ("U1", "U2", "U4", "U8"):
        data = arcpy.RasterToNumPyArray(str(path), nodata_to_value=255).astype(np.int16)
        data[data == 255] = -9999
        return data
    return arcpy.RasterToNumPyArray(str(path), nodata_to_value=-9999)


def tile_job(source, output, name):
    source, output = Path(source), Path(output)
    state = json.loads((source / "count.json").read_text(encoding="utf-8"))
    tile = state["tiles"][name]
    original = source / "rasters" / name
    folder = output / "tiles" / name
    folder.mkdir(parents=True, exist_ok=False)
    core = " ".join(map(str, tile["core"]))
    paths = {"chm": str(original / "core_chm.tif")}
    with licensing.extensions("Spatial"):
        for key, filename in PRODUCTS.items():
            if key in ("chm", "roof_height"):
                continue
            target = str(folder / filename)
            with common.environment(str(original / "core_chm.tif")):
                arcpy.management.Clip(str(original / filename), core, target,
                                      maintain_clipping_extent="NO_MAINTAIN_EXTENT")
            paths[key] = target
        with common.environment(paths["terrain"]):
            target = str(folder / PRODUCTS["roof_height"])
            (arcpy.sa.Raster(paths["roof_elevation"]) - arcpy.sa.Raster(paths["terrain"])).save(target)
            paths["roof_height"] = target
    arrays = {key: values(path) for key, path in paths.items()}
    assert len({a.shape for a in arrays.values()}) == 1
    roof, ground, heights = [arrays[k] for k in ("roof_elevation", "terrain", "roof_height")]
    paired = (roof != -9999) & (ground != -9999)
    assert np.array_equal(heights != -9999, paired)
    assert np.array_equal(heights[paired], (roof - ground)[paired])
    observed, chm = arrays["observed"], arrays["chm"]
    assert np.array_equal(observed == 1, chm != -9999)
    assert np.all(chm[chm != -9999] >= 0)
    expected_shape = tuple(tile["shape"])
    assert arrays["chm"].shape == expected_shape
    reference = arcpy.Raster(paths["chm"])
    extent = [reference.extent.XMin, reference.extent.YMin, reference.extent.XMax, reference.extent.YMax]
    for path in paths.values():
        r, _ = common.grid(path, .5, 4_000_000)
        assert (r.width, r.height) == (reference.width, reference.height)
        assert common.same_xy_reference(r.spatialReference, reference.spatialReference)
        assert np.allclose([r.extent.XMin, r.extent.YMin, r.extent.XMax, r.extent.YMax], extent, rtol=0, atol=1e-7)
    result = {"status": "passed", "paths": paths, "shape": list(expected_shape),
              "roof_cells": int(paired.sum()), "negative_roof_height_cells": int((heights[paired] < 0).sum()),
              "observed_cells": int((observed == 1).sum())}
    common.write_json(folder / "result.json", result)
    return result


def fresh_tile(source, output, name):
    folder = Path(output) / "logs"
    folder.mkdir(exist_ok=True)
    with (folder / (name + ".log")).open("w", encoding="utf-8") as log:
        process = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), str(source), str(output),
                                  "--tile", name], stdout=log, stderr=subprocess.STDOUT)
    if process.returncode:
        raise RuntimeError(f"Tile {name} exited {process.returncode}; see {folder / (name + '.log')}")
    return json.loads((Path(output) / "tiles" / name / "result.json").read_text(encoding="utf-8"))


def assemble(source, output, workers):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents:
        raise ValueError("Choose a new folder outside the source count run")
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "products.json"
    if manifest.exists():
        raise FileExistsError("Use a new product directory")
    count = json.loads((source / "count.json").read_text(encoding="utf-8"))
    verification = json.loads((source / "verification.json").read_text(encoding="utf-8"))
    assert count["status"] == "complete" and verification["status"] == "passed"
    inputs = json.loads((source / "inputs.json").read_text(encoding="utf-8"))
    files = list((source / "prepared/points").glob("*.las")) + list((source.parent.parent / "las").glob("*.las"))
    files += list((source / "rasters").glob("*/*.tif"))
    before = fingerprint(files)
    state = {"status": "pilot", "started": time.time(), "source": str(source),
             "source_count_sha256": hashlib.sha256((source / "count.json").read_bytes()).hexdigest(),
             "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             "runtime": common.runtime(), "warning": WARNING, "cell_m": .5,
             "boundary": inputs["boundary"], "source_id": count["source_id"],
             "tiles": {}, "outputs": {}, "source_fingerprints": before}
    common.write_json(manifest, state)
    try:
        names = sorted(count["tiles"])
        state["tiles"][names[0]] = fresh_tile(source, output, names[0])
        state["status"] = "building cores"
        common.write_json(manifest, state)
        print("Pilot passed: paired roof-height math, support and exact grid", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            jobs = {pool.submit(fresh_tile, source, output, name): name for name in names[1:]}
            for future in as_completed(jobs):
                state["tiles"][jobs[future]] = future.result()
                common.write_json(manifest, state)
                print(f"Cores {len(state['tiles'])}/{len(names)}", flush=True)
        state["status"] = "assembling city rasters"
        common.write_json(manifest, state)
        sr = arcpy.SpatialReference(6341)
        with licensing.extensions("Spatial"):
            for key in PRODUCTS:
                unmasked = output / (key + "_context.tif")
                target = output / (key + ("_m.tif" if key in ("chm", "terrain", "roof_elevation", "roof_height") else ".tif"))
                paths = [state["tiles"][name]["paths"][key] for name in names]
                with arcpy.EnvManager(compression="LZW", parallelProcessingFactor="0", cellSize=.5,
                                      outputCoordinateSystem=sr, snapRaster=paths[0], mask=None):
                    arcpy.management.MosaicToNewRaster(paths, str(output), unmasked.name, sr,
                        "8_BIT_UNSIGNED" if key in MASKS else "32_BIT_FLOAT", .5, 1, "FIRST", "FIRST")
                with common.environment(str(unmasked)):
                    arcpy.sa.ExtractByMask(str(unmasked), inputs["boundary"]).save(str(target))
                common.metadata(str(target), f"Millcreek {key}, clipped by city cell centres; 0.5 m. " + WARNING)
                state["outputs"][key] = str(target)
                common.write_json(manifest, state)
                print(f"City raster {key} ready", flush=True)
        # Stream the city mask raster in row blocks; never allocate a city-sized array.
        r = arcpy.Raster(state["outputs"]["observed"])
        totals = {"city_grid_cells": 0, "observed_cells": 0, "missing_cells": 0, "canopy_ge_2m_cells": 0}
        for offset in range(0, r.height, 256):
            rows = min(256, r.height - offset)
            corner = arcpy.Point(r.extent.XMin, r.extent.YMin + offset * .5)
            obs = arcpy.RasterToNumPyArray(state["outputs"]["observed"], corner, r.width, rows, 255).astype(np.int16)
            obs[obs == 255] = -9999
            chm = arcpy.RasterToNumPyArray(state["outputs"]["chm"], corner, r.width, rows, -9999)
            assert np.array_equal(obs == 1, chm != -9999)
            totals["city_grid_cells"] += int((obs != -9999).sum())
            totals["observed_cells"] += int((obs == 1).sum())
            totals["missing_cells"] += int((obs == 0).sum())
            totals["canopy_ge_2m_cells"] += int(((chm != -9999) & (chm >= 2)).sum())
        for key, value in totals.items():
            assert value == count["observation"][key], (key, value, count["observation"][key])
        assert before == fingerprint(files), "A source raster or LAS fingerprint changed"
        state.update(status="complete", finished=time.time(), observation=totals,
                     source_fingerprints_unchanged=True, all_cores_verified=len(names))
        state["seconds"] = state["finished"] - state["started"]
        common.write_json(manifest, state)
        print(json.dumps({k: state[k] for k in ("status", "outputs", "observation", "seconds")}, indent=2), flush=True)
    except BaseException as exc:
        state.update(status="failed", error=str(exc), finished=time.time())
        common.write_json(manifest, state)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--tile")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=2)
    args = parser.parse_args()
    if args.tile:
        tile_job(args.source, args.output, args.tile)
    else:
        assemble(args.source, args.output, args.workers)
