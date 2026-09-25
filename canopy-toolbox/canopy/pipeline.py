"""Buffered raster tiles followed by exact whole-AOI detection and segmentation.

Finite halos cannot guarantee an identical watershed on connected canopy.
Detection and crowns therefore use one canonical grid, with an explicit size cap.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import uuid

import arcpy

from . import bands as band_logic, common, crowns, rasters, treetops
from .tiling import Extent, tile_grid, recommended_overlap, snap_extent


def _signature(lasd, files, parameters):
    inputs = []
    for path in [lasd, *files]:
        path = Path(path).resolve()
        stat = path.stat()
        inputs.append((str(path),stat.st_size,stat.st_mtime_ns))
    code = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        code.update(path.read_bytes())
    # Equivalent CLI/API values (125 vs 125.0, or whitespace in bands) share a signature.
    normalized = dict(parameters)
    for key in ("tile_size", "overlap", "cell_size", "smoothing", "min_crown_area", "building_clearance"):
        normalized[key] = float(normalized[key])
    normalized["extent"] = [float(v) for v in normalized["extent"]]
    normalized["bands"] = band_logic.parse_bands(normalized["bands"])
    state = {"inputs":inputs,"parameters":normalized,"implementation":code.hexdigest()}
    return hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()


def run(lasd, run_folder, extent, tile_size=200, overlap=None, cell_size=.5,
        band_spec=band_logic.DEFAULT_SPEC, smooth_cells=1, min_crown_area=3,
        source_files=None, source_id=None, resume=False, z_unit=None, building_clearance=.35):
    parsed = band_logic.parse_bands(band_spec)
    common.positive(min_crown_area,"Minimum crown area",allow_zero=True)
    common.positive(cell_size, "Cell size")
    common.positive(building_clearance, "Building clearance", allow_zero=True)
    if isinstance(smooth_cells, bool) or int(smooth_cells) != smooth_cells or smooth_cells < 0:
        raise ValueError("Smoothing radius must be a non-negative integer")
    analysis_extent = snap_extent(Extent(*extent), cell_size)
    cells = round(analysis_extent.width/cell_size)*round(analysis_extent.height/cell_size)
    if cells > min(crowns.MAX_CELLS, treetops.MAX_CELLS):
        raise ValueError("Whole-AOI detection and crown segmentation support at most 4,000,000 cells. "
                         "Use a smaller review AOI. Independent AOIs are not reconciled into a citywide inventory.")
    # Halos supply raster interpolation context; they do not bound crown growth.
    minimum_overlap = max(recommended_overlap(parsed), max(b.radius for b in parsed)+smooth_cells*cell_size)
    overlap = minimum_overlap if overlap is None else overlap
    if overlap < minimum_overlap:
        raise ValueError(f"Overlap must be at least {minimum_overlap} metres for these parameters")
    tiles = tile_grid(Extent(*extent),tile_size,overlap,cell_size)
    sr = common.metric_reference(arcpy.Describe(lasd).spatialReference)
    if any((t.buffered.width/cell_size)*(t.buffered.height/cell_size)>crowns.MAX_CELLS for t in tiles):
        raise ValueError("Buffered tiles exceed the in-memory cell limit")
    lasd=str(Path(lasd).resolve())
    root=Path(run_folder).resolve()
    prep_path=Path(lasd).parent/"preparation.json"
    if source_files is None and prep_path.is_file():
        prep=json.loads(prep_path.read_text(encoding="utf8"))
        if Path(prep["working_lasd"]).resolve() != Path(lasd).resolve():
            raise ValueError("Preparation manifest does not match the supplied LAS dataset")
        source_files=list((Path(lasd).parent/"points").glob("*.las"))
        source_id=source_id or prep.get("source_id")
    if not source_files:
        raise ValueError("Supply source_files for resume checks, or use a prepared working-copy LAS dataset")
    source_id=source_id or hashlib.sha256(
        json.dumps([str(Path(p).resolve()) for p in source_files]).encode()).hexdigest()[:24]
    parameters={"extent":list(extent),"tile_size":tile_size,"overlap":overlap,"cell_size":cell_size,
                "bands":band_spec,"smoothing":smooth_cells,"min_crown_area":min_crown_area,
                "source_id":source_id,"z_unit":z_unit,"building_clearance":building_clearance}
    signature=_signature(lasd,source_files,parameters)
    manifest_path=root/"run.json"
    if root.exists():
        if not resume or not manifest_path.exists():
            raise FileExistsError("Run folder exists; choose a new folder or explicitly resume its manifest")
        state=json.loads(manifest_path.read_text(encoding="utf8"))
        if state["signature"] != signature:
            raise ValueError("Inputs, code, or parameters changed; use a new run folder")
        if state["status"] == "complete":
            if not all(arcpy.Exists(path) for path in state["outputs"].values()):
                raise ValueError("Completed run outputs were removed; use a new run folder")
            return state
    else:
        root.mkdir(parents=True)
        state={"signature":signature,"parameters":parameters,"status":"running","tiles":{},
               "runtime":common.runtime(),"analysis_cell_limit":min(crowns.MAX_CELLS,treetops.MAX_CELLS)}
        common.write_json(manifest_path,state)
    state["status"]="running"
    state.pop("error", None)
    try:
        # Pass 1: build halo rasters and retain nonoverlapping cores.
        for tile in tiles:
            record=state["tiles"].get(tile.name,{})
            if record.get("status") in ("rasterized","detected","segmented") and all(
                arcpy.Exists(record[k]) for k in ("chm","core_chm")):
                continue
            attempt=root/(tile.name+"_"+uuid.uuid4().hex[:8]);attempt.mkdir()
            gdb=str(attempt/"tile.gdb");arcpy.management.CreateFileGDB(str(attempt),"tile.gdb")
            products=rasters.build_chm(lasd,str(attempt),cell_size,
                                      tile.buffered.as_arcpy_string(),source_id=source_id,z_unit=z_unit,
                                      building_clearance=building_clearance)
            core_chm=str(attempt/"core_chm.tif")
            with common.environment(products["chm"]):
                arcpy.management.Clip(products["chm"],tile.core.as_arcpy_string(),core_chm,
                                      nodata_value="-9999",maintain_clipping_extent="NO_MAINTAIN_EXTENT")
            state["tiles"][tile.name]={"status":"rasterized","gdb":gdb,"chm":products["chm"],
                                       "core_chm":core_chm,"core":tile.core,"halo":tile.buffered}
            common.write_json(manifest_path,state)
            arcpy.AddMessage(f"{tile.name}: CHM core saved")
        # A new assembly directory on each incomplete retry avoids stale intermediate collisions.
        assembly=root/("assembly_"+uuid.uuid4().hex[:8]);assembly.mkdir()
        gdb=str(assembly/"inventory.gdb");arcpy.management.CreateFileGDB(str(assembly),"inventory.gdb")
        mosaic=str(assembly/"chm.tif")
        arcpy.management.MosaicToNewRaster(
            [state["tiles"][t.name]["core_chm"] for t in tiles],str(assembly),"chm.tif",sr,
            "32_BIT_FLOAT",cell_size,1,"FIRST","FIRST")
        # A halo cannot bound watershed influence or the extent of a flat plateau.
        # Process the assembled grid once to avoid seam-dependent labels and duplicate peaks.
        global_tops=treetops.detect(mosaic,gdb,parsed,smooth_cells=smooth_cells,source_id=source_id)
        final_crowns=crowns.delineate(mosaic,global_tops,gdb,
                                      min_height=parsed[0].low,min_crown_area=min_crown_area)
        reviewed=os.path.join(gdb,"trees_review")
        ids=[row[0] for row in arcpy.da.SearchCursor(global_tops,["TREE_ID"])]
        if len(ids)!=len(set(ids)):
            raise RuntimeError("Duplicate TREE_ID after global detection")
        # Retain a review flag for raster interpolation seams, not approximate crown stitching.
        vertical={t.core.xmax for t in tiles if t.core.xmax < analysis_extent.xmax}
        horizontal={t.core.ymax for t in tiles if t.core.ymax < analysis_extent.ymax}
        near_seam={}
        for tree_id,(x,y) in arcpy.da.SearchCursor(global_tops,["TREE_ID","SHAPE@XY"]):
            near_seam[tree_id]=int(any(abs(x-line)<=overlap for line in vertical) or
                                   any(abs(y-line)<=overlap for line in horizontal))
        for path in (final_crowns,reviewed):
            common.add_fields(path,[("SEAM_REVIEW","SHORT",None)])
            with arcpy.da.UpdateCursor(path,["TREE_ID","SEAM_REVIEW"]) as cursor:
                for row in cursor:
                    row[1]=near_seam[row[0]];cursor.updateRow(row)
            common.metadata(path,"Whole-AOI marker watershed on the canonical CHM. "
                                 "SEAM_REVIEW marks detections near raster-generation seams. "
                                 "Crown areas use exact cell counts, avoiding polygon precision rounding.")
        state["status"]="complete"
        state["outputs"]={"chm":mosaic,"treetops":global_tops,"crowns":final_crowns,"trees_review":reviewed}
        state["quality_status"]="UNVALIDATED; inspect classification, SEAM_REVIEW, and representative imagery"
    except Exception as exc:
        state["status"]="failed";state["error"]=str(exc)
        raise
    finally:
        common.write_json(manifest_path,state)
    return state
