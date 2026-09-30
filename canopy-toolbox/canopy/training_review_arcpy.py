"""ArcGIS side of the TRAINING-label review: GDB with coded-value domains, layers, a new review
project, label read/write, imagery-training polygons and a Prepare Point Cloud Training Data
dry run. Pure logic lives in canopy.training_review. Never touches evaluation data except to read
its geometry for the exclusion frame.
"""
import datetime
import json
import os
import shutil
from pathlib import Path

import arcpy
import numpy as np

from . import label_check
from . import training_review as tr

UNITS_FC = "training_units"
PATCHES_FC = "training_patches"
DOMAIN_FC = "training_domain"
EXCLUDED_FC = "excluded_evaluation_areas"
LABEL_DOMAIN = "TRAINING_LABEL"
YES_NO_DOMAIN = "TRAINING_YES_NO"
QUEUE_DOMAIN = "TRAINING_QUEUE"
REFERENCE_SAMPLES = {"treetop": "treetop_sample", "omission": "omission_sample",
                     "cell": "cell_sample", "crown": "crown_sample"}
EVIDENCE_FIELDS = ("PRIORITY", "SELECTION", "CLUSTER_PTS", "PATCH_PTS", "BASE_CLASS", "TREE_MODEL",
                   "BLDG_MODEL", "SHAPE_GROUP", "CAND_FLAG", "EVIDENCE")
UNIT_FIELDS = [
    ("UNIT_ID", "TEXT", 16, None), ("QUEUE", "TEXT", 24, QUEUE_DOMAIN), ("REVIEW_ORDER", "LONG", None, None),
    ("QUEUE_ORDER", "LONG", None, None), ("TILE", "TEXT", 16, None),
    ("X", "DOUBLE", None, None), ("Y", "DOUBLE", None, None),
    ("Z_LOW", "DOUBLE", None, None), ("Z_HIGH", "DOUBLE", None, None), ("GROUND_Z", "DOUBLE", None, None),
    ("HAG_LOW", "DOUBLE", None, None), ("HAG_HIGH", "DOUBLE", None, None), ("PATCH_R_M", "DOUBLE", None, None),
    ("PRIORITY", "DOUBLE", None, None), ("SELECTION", "TEXT", 8, None), ("CLUSTER_PTS", "LONG", None, None),
    ("PATCH_PTS", "LONG", None, None), ("BASE_CLASS", "SHORT", None, None), ("TREE_MODEL", "SHORT", None, None),
    ("BLDG_MODEL", "SHORT", None, None), ("SHAPE_GROUP", "TEXT", 16, None), ("CAND_FLAG", "TEXT", 16, None),
    ("EVIDENCE", "TEXT", 120, None),
    ("LABEL", "TEXT", 24, LABEL_DOMAIN), ("IMAGERY_USABLE", "TEXT", 3, YES_NO_DOMAIN),
    ("REVIEWER", "TEXT", 64, None), ("REVIEW_DATE", "DATE", None, None), ("NOTES", "TEXT", 500, None)]
BUILD_FIELDS = [f[0] for f in UNIT_FIELDS if f[0] not in tr.ANSWER_FIELDS]


# ---------------------------------------------------------------- reading evaluation geometry

def _rings(geometry):
    rings = []
    for part in geometry:
        ring = []
        for point in part:
            if point is None:          # arcpy separates interior rings with None
                if ring:
                    rings.append(ring)
                ring = []
            else:
                ring.append([point.X, point.Y])
        if ring:
            rings.append(ring)
    return rings


def read_reference_units(gdb):
    """Identity and geometry of every evaluation sample unit in reference.gdb (all tiles)."""
    units = []
    for sample, fc in REFERENCE_SAMPLES.items():
        path = str(Path(gdb)/fc)
        if arcpy.Describe(path).spatialReference.factoryCode != 6341:
            raise ValueError(f"{fc} must be EPSG:6341")
        with arcpy.da.SearchCursor(path, ["SHAPE@", "SAMPLE_ID", "TILE"]) as cursor:
            for shape, sample_id, tile in cursor:
                row = {"sample": sample, "SAMPLE_ID": sample_id, "TILE": tile}
                if shape.type == "polygon":
                    row["rings"] = _rings(shape)
                else:
                    row["x"], row["y"] = shape.firstPoint.X, shape.firstPoint.Y
                units.append(row)
    return units


def read_plots(fc):
    if arcpy.Describe(str(fc)).spatialReference.factoryCode != 6341:
        raise ValueError("Census plots must be EPSG:6341")
    with arcpy.da.SearchCursor(str(fc), ["SHAPE@", "PLOT_ID", "TILE"]) as cursor:
        return [{"PLOT_ID": pid, "TILE": tile, "rings": _rings(shape)} for shape, pid, tile in cursor]


def read_candidate_flags(fc, flags=("ROOF_EDGE", "ON_ROOF")):
    with arcpy.da.SearchCursor(str(fc), ["SHAPE@XY", "TREE_ID", "FLAG", "HEIGHT_M"]) as cursor:
        return [{"x": xy[0], "y": xy[1], "tree_id": tid, "flag": flag, "height_m": h}
                for xy, tid, flag, h in cursor if flag in flags]


class GroundRaster:
    """Nearest-cell ground elevation from a metre-unit raster (read once)."""

    def __init__(self, path):
        info = arcpy.Describe(str(path))
        self.x0, self.y1 = info.extent.XMin, info.extent.YMax
        self.cell = info.meanCellWidth
        self.array = arcpy.RasterToNumPyArray(str(path), nodata_to_value=np.nan).astype(float)

    def sample(self, x, y):
        col = int((x-self.x0)//self.cell)
        row = int((self.y1-y)//self.cell)
        if 0 <= row < self.array.shape[0] and 0 <= col < self.array.shape[1]:
            value = self.array[row, col]
            return None if np.isnan(value) else float(value)
        return None


# ---------------------------------------------------------------- review geodatabase

def create_domains(gdb):
    arcpy.management.CreateDomain(str(gdb), LABEL_DOMAIN, "Training label (never an evaluation answer)", "TEXT", "CODED")
    for code, (meaning, _) in tr.LABELS.items():
        arcpy.management.AddCodedValueToDomain(str(gdb), LABEL_DOMAIN, code, f"{code}: {meaning}"[:250])
    arcpy.management.CreateDomain(str(gdb), YES_NO_DOMAIN, "Imagery usable for this label", "TEXT", "CODED")
    for code in tr.YES_NO:
        arcpy.management.AddCodedValueToDomain(str(gdb), YES_NO_DOMAIN, code, code)
    arcpy.management.CreateDomain(str(gdb), QUEUE_DOMAIN, "Training review queue", "TEXT", "CODED")
    for code, meaning in tr.QUEUES.items():
        arcpy.management.AddCodedValueToDomain(str(gdb), QUEUE_DOMAIN, code, f"{tr.QUEUE_CODES[code]}: {meaning}"[:250])


def create_review_gdb(gdb, units, frame, mask=None, sr=None):
    """New GDB: unit points, patch circles, allowed-domain and excluded-area polygons."""
    gdb = Path(gdb)
    if gdb.exists():
        raise FileExistsError(f"{gdb} exists")
    sr = sr or arcpy.SpatialReference(6341)
    arcpy.management.CreateFileGDB(str(gdb.parent), gdb.name)
    create_domains(gdb)
    arcpy.management.CreateFeatureclass(str(gdb), UNITS_FC, "POINT", spatial_reference=sr)
    arcpy.management.AddFields(str(gdb/UNITS_FC), [[n, t, n, length or "", "", d or ""] for n, t, length, d in UNIT_FIELDS])
    with arcpy.da.InsertCursor(str(gdb/UNITS_FC), ["SHAPE@XY", *BUILD_FIELDS]) as cursor:
        for u in units:
            cursor.insertRow([(u["X"], u["Y"]), *[u.get(f) for f in BUILD_FIELDS]])
    arcpy.management.CreateFeatureclass(str(gdb), PATCHES_FC, "POLYGON", spatial_reference=sr)
    arcpy.management.AddFields(str(gdb/PATCHES_FC), [["UNIT_ID", "TEXT", "UNIT_ID", 16], ["QUEUE", "TEXT", "QUEUE", 24],
                                                    ["REVIEW_ORDER", "LONG"]])
    with arcpy.da.InsertCursor(str(gdb/PATCHES_FC), ["SHAPE@", "UNIT_ID", "QUEUE", "REVIEW_ORDER"]) as cursor:
        for u in units:
            circle = arcpy.PointGeometry(arcpy.Point(u["X"], u["Y"]), sr).buffer(u["PATCH_R_M"])
            cursor.insertRow([circle, u["UNIT_ID"], u["QUEUE"], u["REVIEW_ORDER"]])
    _excluded_areas(gdb, frame, sr)
    if mask is not None:
        _domain_polygons(gdb, mask, sr)
    return gdb


def _excluded_areas(gdb, frame, sr):
    """Buffers (EVAL_BUFFER_M) of evaluation features near the training tile, for display."""
    arcpy.management.CreateFeatureclass(str(gdb), EXCLUDED_FC, "POLYGON", spatial_reference=sr)
    arcpy.management.AddFields(str(gdb/EXCLUDED_FC), [["SOURCE", "TEXT", "SOURCE", 32], ["FEATURE_ID", "TEXT", "FEATURE_ID", 40],
                                                     ["BUFFER_M", "DOUBLE"]])
    t = frame["training_extent"]
    reach = frame["buffer_m"]+tr.PATCH_RADIUS_M
    with arcpy.da.InsertCursor(str(gdb/EXCLUDED_FC), ["SHAPE@", "SOURCE", "FEATURE_ID", "BUFFER_M"]) as cursor:
        for f in frame["features"]:
            if f["kind"] == "point":
                geometry = arcpy.PointGeometry(arcpy.Point(*f["coords"]), sr)
            else:
                geometry = arcpy.Polygon(arcpy.Array([arcpy.Array([arcpy.Point(*v) for v in ring]) for ring in f["coords"]]), sr)
            e = geometry.extent
            if e.XMax < t[0]-reach or e.XMin > t[2]+reach or e.YMax < t[1]-reach or e.YMin > t[3]+reach:
                continue
            cursor.insertRow([geometry.buffer(frame["buffer_m"]), f["source"], f["id"], frame["buffer_m"]])


def _domain_polygons(gdb, mask_info, sr):
    mask, x0, y0, cell = mask_info
    # Pin the workspaces: a stale arcpy.env workspace (e.g. from another tool run) would receive
    # the temporary raster otherwise.
    with arcpy.EnvManager(workspace=str(gdb), scratchWorkspace=str(Path(gdb).parent)):
        raster = arcpy.NumPyArrayToRaster(np.flipud(mask).astype(np.uint8), arcpy.Point(x0, y0), cell, cell, 0)
        mask_raster = str(Path(gdb)/"domain_mask")
        raster.save(mask_raster)
        del raster
        arcpy.management.DefineProjection(mask_raster, sr)
        temp = str(Path(gdb)/"domain_raw")
        arcpy.conversion.RasterToPolygon(mask_raster, temp, "NO_SIMPLIFY", "Value")
        arcpy.management.MakeFeatureLayer(temp, "domain_raw_lyr", "gridcode = 1")
        arcpy.management.Dissolve("domain_raw_lyr", str(Path(gdb)/DOMAIN_FC))
        arcpy.management.Delete("domain_raw_lyr")
        arcpy.management.Delete(temp)
        arcpy.management.Delete(mask_raster)
    arcpy.management.AddField(str(Path(gdb)/DOMAIN_FC), "NOTE", "TEXT", field_length=200)
    with arcpy.da.UpdateCursor(str(Path(gdb)/DOMAIN_FC), ["NOTE"]) as cursor:
        for _ in cursor:
            cursor.updateRow([f"Allowed patch centres ({cell} m raster; exact distances are enforced on export)"])


def read_review_rows(fc):
    fields = ["OID@", *[f[0] for f in UNIT_FIELDS]]
    rows = []
    with arcpy.da.SearchCursor(str(fc), fields) as cursor:
        for values in cursor:
            row = dict(zip(fields, values))
            if isinstance(row["REVIEW_DATE"], (datetime.date, datetime.datetime)):
                row["REVIEW_DATE"] = row["REVIEW_DATE"].date().isoformat() if isinstance(row["REVIEW_DATE"], datetime.datetime) \
                    else row["REVIEW_DATE"].isoformat()
            rows.append(row)
    return rows


def domain_codes(workspace, name=LABEL_DOMAIN):
    for domain in arcpy.da.ListDomains(str(workspace)):
        if domain.name == name:
            return list(domain.codedValues)
    raise ValueError(f"Domain {name} not found in {workspace}")


def write_answer(fc, oid, answer, replace=False):
    """Write one validated answer to one unit. Refuses to overwrite a different label unless replace."""
    fields = ["OID@", *tr.ANSWER_FIELDS]
    with arcpy.da.UpdateCursor(str(fc), fields, f"{arcpy.Describe(str(fc)).OIDFieldName} = {int(oid)}") as cursor:
        rows = 0
        for row in cursor:
            rows += 1
            before = dict(zip(tr.ANSWER_FIELDS, row[1:]))
            if before["LABEL"] and before["LABEL"] != answer["LABEL"] and not replace:
                raise ValueError(f"Unit already labelled {before['LABEL']}; tick 'Replace existing label' to change it")
            cursor.updateRow([row[0], answer["LABEL"], answer["IMAGERY_USABLE"], answer["REVIEWER"],
                              datetime.datetime.fromisoformat(answer["REVIEW_DATE"]), answer["NOTES"]])
    if rows != 1:
        raise ValueError(f"Expected exactly one unit with OID {oid}, found {rows}")
    return before


def packet_for(fc):
    """The packet.json beside the review GDB (identity, frame and units); verified before use."""
    path = Path(str(fc)).parent.parent/"packet.json"
    if not path.is_file():
        raise FileNotFoundError(f"packet.json not found beside {Path(str(fc)).parent}")
    document = json.loads(path.read_text(encoding="utf-8"))
    tr.check_frame(document["frame"])
    if tr.units_digest(document["units"]) != document["units_digest"]:
        raise ValueError("packet.json units were altered")
    return document


def next_unit_row(fc, queue=None):
    return tr.next_unit(read_review_rows(fc), queue or None)


def label_unit(fc, selected_oids, raw_answer, document=None, replace=False, today=None):
    """Validate and write one answer to the single selected unit (the Label Training Unit tool core).

    Refuses zero or several selected units, labels outside the GDB domain, and units whose patch is
    in the excluded evaluation domain (re-checked against the packet frame)."""
    oids = sorted({int(o) for o in selected_oids})
    if len(oids) != 1:
        raise ValueError(f"Select exactly one training unit (selected: {len(oids)})")
    document = document or packet_for(fc)
    rows = {r["OID@"]: r for r in read_review_rows(fc)}
    row = rows.get(oids[0])
    if row is None:
        raise ValueError(f"No training unit with OID {oids[0]}")
    units = {u["UNIT_ID"]: u for u in document["units"]}
    unit = units.get(row["UNIT_ID"])
    if unit is None:
        raise ValueError(f"{row['UNIT_ID']} is not a unit of this packet")
    for key in tr.IDENTITY_FIELDS:
        b = unit[key]
        a = row[key]
        if a is None or ((abs(float(a)-float(b)) > .005) if isinstance(b, float) else str(a) != str(b)):
            raise ValueError(f"{row['UNIT_ID']}: identity field {key} changed")
    answer = tr.normalize_answer(unit, raw_answer, document["frame"], labels=domain_codes(Path(str(fc)).parent), today=today)
    before = write_answer(fc, oids[0], answer, replace)
    return {"UNIT_ID": row["UNIT_ID"], "before": before, "after": answer,
            "warnings": label_warnings(fc, [(row["UNIT_ID"], answer["LABEL"])])}


def load_patch_stats(fc):
    """Per-unit patch statistics from patch_stats.json beside the packet; {} when the file is absent or unreadable."""
    path = Path(str(fc)).parent.parent/"patch_stats.json"
    try:
        units = json.loads(path.read_text(encoding="utf-8"))["units"]
    except (OSError, ValueError, KeyError):
        return {}
    nan = float("nan")
    return {uid: {"n": s["n"], **{k: (nan if s.get(k) is None else s[k]) for k in ("min", "mean", "max")}}
            for uid, s in units.items()}


def patch_note(unit_id, stats):
    """One sentence telling the reviewer what the unit's own patch holds."""
    s = stats.get(unit_id)
    if s is None:
        return "Patch heights are not available (run training_review_driver.py patch-stats)."
    if not s["n"]:
        return "The patch holds no points."
    def height(v):
        return f"{0.0 if abs(v) < 0.05 else v:.1f}"          # no "-0.0"
    return (f"The patch holds {s['n']} points, {height(s['min'])} to {height(s['max'])} m above ground "
            f"(mean {height(s['mean'])} m). Label what these points are, not an object beside the circle.")


def label_warnings(fc, unit_ids_and_labels):
    """Non-blocking warnings for labels the patch's own points cannot support (see canopy/label_check.py)."""
    stats = load_patch_stats(fc)
    out = []
    for uid, label in unit_ids_and_labels:
        if uid in stats:
            out += [f"{uid}: {reason}. Check the label, or use UNSURE or MIXED."
                    for reason in label_check.check_label(label, stats[uid])]
    return out


MAX_BULK = 500


def write_answers(fc, oids, answer):
    """Write one validated answer to several units in a single pass. Returns the number of rows written."""
    fields = ["OID@", *tr.ANSWER_FIELDS]
    oid_field = arcpy.Describe(str(fc)).OIDFieldName
    where = f"{oid_field} IN ({','.join(str(int(o)) for o in sorted(oids))})"
    written = 0
    with arcpy.da.UpdateCursor(str(fc), fields, where) as cursor:
        for row in cursor:
            cursor.updateRow([row[0], answer["LABEL"], answer["IMAGERY_USABLE"], answer["REVIEWER"],
                              datetime.datetime.fromisoformat(answer["REVIEW_DATE"]), answer["NOTES"]])
            written += 1
    return written


def label_units(fc, selected_oids, raw_answer, document=None, replace=False, today=None, max_units=MAX_BULK,
                history_dir=None):
    """Validate and write one answer to every selected unit (the Label Selected Units tool core).

    All or nothing: each unit is checked first (identity, label domain, reviewer, date, the excluded evaluation
    domain, and the replace guard) and nothing is written if any unit fails. A batch is capped at max_units so a
    whole-table selection cannot be labelled by accident. The answers being overwritten are saved first to
    history_dir (a JSON file per batch), and the written labels are read back.
    """
    oids = sorted({int(o) for o in selected_oids})
    if not oids:
        raise ValueError("Select at least one training unit")
    if len(oids) > max_units:
        raise ValueError(f"{len(oids)} units are selected; at most {max_units} can be labelled at once")
    document = document or packet_for(fc)
    rows = {r["OID@"]: r for r in read_review_rows(fc)}
    units = {u["UNIT_ID"]: u for u in document["units"]}
    labels = domain_codes(Path(str(fc)).parent)
    problems, answers, before = [], {}, []
    for oid in oids:
        row = rows.get(oid)
        if row is None:
            problems.append(f"OID {oid}: no such training unit")
            continue
        unit = units.get(row["UNIT_ID"])
        if unit is None:
            problems.append(f"{row['UNIT_ID']}: not a unit of this packet")
            continue
        drift = [k for k in tr.IDENTITY_FIELDS
                 if row[k] is None or ((abs(float(row[k])-float(unit[k])) > .005) if isinstance(unit[k], float)
                                       else str(row[k]) != str(unit[k]))]
        if drift:
            problems.append(f"{row['UNIT_ID']}: identity field {drift[0]} changed")
            continue
        try:
            answers[oid] = tr.normalize_answer(unit, raw_answer, document["frame"], labels=labels, today=today)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        current = row.get("LABEL")
        if current and current != answers[oid]["LABEL"] and not replace:
            problems.append(f"{row['UNIT_ID']}: already labelled {current}; tick Replace to change it")
        before.append({"UNIT_ID": row["UNIT_ID"], **{k: row.get(k) for k in tr.ANSWER_FIELDS}})
    if problems:
        shown = "; ".join(problems[:5]) + (f"; and {len(problems)-5} more" if len(problems) > 5 else "")
        raise ValueError(f"Nothing was written. {len(problems)} of {len(oids)} selected units failed: {shown}")
    label = next(iter(answers.values()))["LABEL"]
    if history_dir is not None:
        history_dir = Path(str(history_dir))
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        (history_dir/f"bulk-{stamp}.json").write_text(json.dumps(
            {"label": label, "units": len(oids), "previous_answers": before}, indent=1, default=str), encoding="utf-8")
    written = write_answers(fc, oids, next(iter(answers.values())))
    after = {r["OID@"]: r for r in read_review_rows(fc)}
    wrong = [after[o]["UNIT_ID"] for o in oids if after[o]["LABEL"] != label]
    if written != len(oids) or wrong:
        raise RuntimeError(f"Read-back mismatch after bulk write: wrote {written} of {len(oids)}; wrong {wrong[:5]}")
    return {"units": len(oids), "label": label, "ids": [after[o]["UNIT_ID"] for o in oids],
            "replaced": sum(1 for b in before if b["LABEL"] and b["LABEL"] != label),
            "warnings": label_warnings(fc, [(after[o]["UNIT_ID"], label) for o in oids])}


def selected_oids(layer):
    """The OIDs actually selected in a layer (read back, not assumed)."""
    fids = arcpy.Describe(layer).FIDSet
    return sorted(int(v) for v in fids.replace(";", " ").split()) if fids else []


def select_unit(layer, oid):
    """Select exactly one unit through the standard Select Layer By Attribute tool and read the selection back.

    Returns True when the layer really holds that one selection. False means the layer's definition query hides the
    unit (or the layer is not the units layer).
    """
    oid_field = arcpy.Describe(layer).OIDFieldName
    arcpy.management.SelectLayerByAttribute(layer, "NEW_SELECTION", f"{oid_field} = {int(oid)}")
    return selected_oids(layer) == [int(oid)]


def clear_selection(layer):
    arcpy.management.SelectLayerByAttribute(layer, "CLEAR_SELECTION")


def pick_map_view(project):
    """(view, note): the active map or scene view, else an open one, else None with the reason.

    Stepping through the attribute table makes the table the active view, which has no camera. The map (or the 3D
    scene) is still open beside it, so its view is moved instead of giving up. A 2D map is preferred over a scene.
    """
    view = getattr(project, "activeView", None)
    if view is not None and hasattr(view, "camera"):
        return view, ""
    ordered = sorted(project.listMaps(), key=lambda m: getattr(m, "mapType", "MAP") == "SCENE")
    for m in ordered:
        candidate = getattr(m, "defaultView", None)
        if candidate is not None and hasattr(candidate, "camera"):
            return candidate, ("The active view is not a map, so the open map view was moved instead. "
                               "Switch to the map to see the unit.")
    return None, ("No map or scene view is open (the active view is a table or layout), so nothing was moved. "
                  "Open the Training review map or the 3D scene, beside the table if you like.")


def move_view(view, row, view_m, spatial_reference):
    """Move a map view to an extent around the unit, or a scene view to look straight down on it. Returns "map"/"scene"."""
    kind = getattr(getattr(view, "map", None), "mapType", "MAP")
    if kind == "SCENE":
        camera = view.camera
        camera.X, camera.Y = row["X"], row["Y"]
        camera.Z = float(row["Z_HIGH"])+float(view_m)
        camera.pitch, camera.heading = -90, 0
        view.camera = camera
        return "scene"
    half = float(view_m)/2
    view.camera.setExtent(arcpy.Extent(row["X"]-half, row["Y"]-half, row["X"]+half, row["Y"]+half,
                                       spatial_reference=spatial_reference))
    return "map"


def go_to_next(layer, queue, view_m, project):
    """Select the next unlabelled unit and move an open map view to it (the Next Training Unit core).

    Returns (UNIT_ID or None, [(level, message)]) with level "info" or "warning"; the caller reports them.
    """
    messages = []
    fc = arcpy.Describe(layer).catalogPath
    row = next_unit_row(fc, queue or None)
    if row is None:
        clear_selection(layer)
        return None, [("info", "No unlabelled units remain" + (f" in {queue}" if queue else "") + ".")]
    if not select_unit(layer, row["OID@"]):
        messages.append(("warning", f"{row['UNIT_ID']} could not be selected: it is hidden by the layer's definition "
                                    "query. Switch the query to 'Unlabelled (all queues)' or the matching queue."))
    view, note = pick_map_view(project)
    if view is None:
        messages.append(("warning", note + f" {row['UNIT_ID']} is selected; find it in the table."))
    else:
        move_view(view, row, view_m, arcpy.Describe(fc).spatialReference)
        if note:
            messages.append(("info", note))
    hag = ""
    if row.get("HAG_LOW") is not None:
        hag = f", {row['HAG_LOW']:.1f} to {row['HAG_HIGH']:.1f} m above ground"
    messages.append(("info", f"{row['UNIT_ID']} (order {row['REVIEW_ORDER']}, {row['QUEUE']}): label the returns within "
                             f"{row['PATCH_R_M']} m of the point between Z {row['Z_LOW']:.1f} and {row['Z_HIGH']:.1f} m{hag}."))
    messages.append(("info", patch_note(row["UNIT_ID"], load_patch_stats(fc))))
    return row["UNIT_ID"], messages


# ---------------------------------------------------------------- layers and project

def _field_info(fc, hidden):
    info = arcpy.FieldInfo()
    for field in arcpy.ListFields(str(fc)):
        info.addField(field.name, field.name, "HIDDEN" if field.name in hidden else "VISIBLE", "NONE")
    return info


def _save_layer(fc, name, path, hidden=()):
    if arcpy.Exists(name):            # a temporary layer left by an earlier build that stopped part-way
        arcpy.management.Delete(name)
    temp = arcpy.management.MakeFeatureLayer(str(fc), name, field_info=_field_info(fc, hidden))[0]
    try:
        arcpy.management.SaveToLayerFile(temp, str(path), "ABSOLUTE")
    finally:
        arcpy.management.Delete(temp)
    return arcpy.mp.LayerFile(str(path))


def _style(layer, fill, outline, width, size=None, marker=None):
    try:
        symbology = layer.symbology
        symbol = symbology.renderer.symbol
        if marker:
            symbol.applySymbolFromGallery(marker)
        symbol.color = {"RGB": fill}
        symbol.outlineColor = {"RGB": outline}
        if size:
            symbol.size = size
        else:
            symbol.outlineWidth = width
        layer.symbology = symbology
    except Exception as exc:  # cosmetic only
        arcpy.AddWarning(f"Could not style {layer.name}: {exc}")


def queue_queries():
    queries = [{"name": "Unlabelled (all queues)", "sql": "LABEL IS NULL", "isActive": True},
               {"name": "All units", "sql": "1 = 1", "isActive": False}]
    for queue, meaning in tr.QUEUES.items():
        queries.append({"name": f"{tr.QUEUE_CODES[queue]} unlabelled: {meaning}"[:120],
                        "sql": f"QUEUE = '{queue}' AND LABEL IS NULL", "isActive": False})
    queries.append({"name": "Labelled (check answers)", "sql": "LABEL IS NOT NULL", "isActive": False})
    return queries


SCENE_NAME = "Training review 3D"
SCENE_POINT_BUDGET = 1_500_000        # the LAS layer's default of 4 million points is heavy for a scene


def add_scene(project, gdb, lasd, layers_dir, point_budget=SCENE_POINT_BUDGET):
    """Add the "Training review 3D" local scene: the tile's LAS points plus the review layers, ready to open.

    A reviewer then has the surrounding points in 3D without finding the tile. The scene uses the tile's projected system
    (EPSG 6341); arcpy scenes are local by default. The LAS layer draws at most point_budget points (Pro's default is
    4 million) to keep the scene light, and only the layer's own definition is changed: setting the scene's definition
    after adding layers removes them. Returns notes; an existing scene is refused.
    """
    if any(m.name == SCENE_NAME for m in project.listMaps()):
        raise FileExistsError(f"The project already has a scene named {SCENE_NAME!r}")
    layers_dir = Path(layers_dir)
    scene = project.createMap(SCENE_NAME, "SCENE")
    notes = []
    for layer in scene.listLayers():
        scene.removeLayer(layer)
    scene.spatialReference = arcpy.SpatialReference(6341)
    las = scene.addDataFromPath(str(lasd))
    las.name = f"Lidar all returns (3D, at most {point_budget:,} points drawn)"
    try:
        cim = las.getDefinition("V3")
        cim.pointBudget = int(point_budget)
        cim.showLegends = False
        las.setDefinition(cim)
    except Exception as exc:
        notes.append(f"Scene LAS layer settings not applied: {exc}")
    for name in ("excluded_evaluation_areas.lyrx", "training_patches.lyrx", "training_units.lyrx"):
        file = layers_dir/name
        if file.is_file():
            scene.addLayer(arcpy.mp.LayerFile(str(file)))
        else:
            notes.append(f"{name} not found; not added to the scene")
    return notes


def build_project(packet, gdb, lasd, toolbox=None, scene=True):
    """New .aprx (copy of the install's Blank.aprx) plus .lyrx files. Existing files are refused."""
    packet, gdb = Path(packet), Path(gdb)
    template = Path(arcpy.GetInstallInfo()["InstallDir"]) / r"Resources\ArcToolBox\Services\routingservices\data\Blank.aprx"
    project_path = packet/"training_review.aprx"
    layers = packet/"layers"
    if project_path.exists() or layers.exists():
        raise FileExistsError(f"{project_path} or {layers} exists")
    layers.mkdir()
    shutil.copyfile(template, project_path)
    project = arcpy.mp.ArcGISProject(str(project_path))
    for existing in project.listMaps():
        project.deleteItem(existing)
    review_map = project.createMap("Training review", "MAP")
    for layer in review_map.listLayers():
        review_map.removeLayer(layer)
    review_map.spatialReference = arcpy.SpatialReference(6341)
    notes = []
    try:
        imagery = review_map.addDataFromPath("https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer")
        imagery.name = "Esri World Imagery (visual reference only; record capture date)"
    except Exception as exc:
        notes.append(f"World Imagery not added: {exc}")
    las = review_map.addDataFromPath(str(lasd))
    las.name = "Lidar all returns (elevation stretch; classes hidden)"
    try:
        cim = las.getDefinition("V3")
        cim.showLegends = False
        cim.lASDatasetFilter = None
        las.setDefinition(cim)
    except Exception as exc:
        notes.append(f"LAS layer CIM not adjusted: {exc}")
    written = {}
    excluded = _save_layer(gdb/EXCLUDED_FC, "Excluded: evaluation units + buffer (never label here)", layers/"excluded_evaluation_areas.lyrx")
    _style(excluded.listLayers()[0], [255, 0, 0, 15], [255, 0, 0, 100], 1.0)
    excluded.save(); review_map.addLayer(arcpy.mp.LayerFile(str(layers/"excluded_evaluation_areas.lyrx")))
    written["excluded"] = str(layers/"excluded_evaluation_areas.lyrx")
    if arcpy.Exists(str(gdb/DOMAIN_FC)):
        domain = _save_layer(gdb/DOMAIN_FC, "Training domain (allowed patch centres)", layers/"training_domain.lyrx")
        _style(domain.listLayers()[0], [0, 0, 0, 0], [0, 200, 0, 100], 1.0)
        domain.listLayers()[0].visible = False
        domain.save(); review_map.addLayer(arcpy.mp.LayerFile(str(layers/"training_domain.lyrx")))
        written["domain"] = str(layers/"training_domain.lyrx")
    patches = _save_layer(gdb/PATCHES_FC, "Training patches (label = returns inside, Z_LOW..Z_HIGH)", layers/"training_patches.lyrx")
    _style(patches.listLayers()[0], [0, 0, 0, 0], [255, 255, 0, 100], 1.5)
    patches.save(); review_map.addLayer(arcpy.mp.LayerFile(str(layers/"training_patches.lyrx")))
    written["patches"] = str(layers/"training_patches.lyrx")
    units_file = _save_layer(gdb/UNITS_FC, "Training units", layers/"training_units.lyrx", hidden=EVIDENCE_FIELDS)
    unit_layer = units_file.listLayers()[0]
    _style(unit_layer, [0, 0, 0, 0], [0, 255, 255, 100], 0, size=16, marker="Circle 2")
    try:
        unit_layer.updateDefinitionQueries(queue_queries())
    except Exception as exc:
        notes.append(f"Definition queries not set: {exc}")
    try:
        label = unit_layer.listLabelClasses()[0]
        label.expression = "$feature.UNIT_ID"
        label.visible = True
        unit_layer.showLabels = True
    except Exception as exc:
        notes.append(f"Labels not set: {exc}")
    units_file.save()
    review_map.addLayer(arcpy.mp.LayerFile(str(layers/"training_units.lyrx")))
    written["units"] = str(layers/"training_units.lyrx")
    evidence = _save_layer(gdb/UNITS_FC, "Training units with model evidence (optional, may bias)", layers/"training_units_evidence.lyrx")
    evidence.listLayers()[0].visible = False
    evidence.save()
    written["units_evidence"] = str(layers/"training_units_evidence.lyrx")
    try:
        project.defaultGeodatabase = str(gdb)
        project.homeFolder = str(packet)
    except Exception as exc:
        notes.append(f"Default geodatabase/home folder not set: {exc}")
    if scene:
        try:
            notes += add_scene(project, gdb, lasd, layers)
        except Exception as exc:
            notes.append(f"3D scene not added: {exc}")
    if toolbox:
        notes += attach_toolbox(project, toolbox)
    project.save()
    del project
    return {"project": str(project_path), "layers": written, "notes": notes}


def _toolbox_path(project, entry):
    """An entry's full path. Pro stores a path relative to the project folder when both are on the same drive."""
    return os.path.normcase(os.path.normpath(os.path.join(str(project.homeFolder), entry["toolboxPath"])))


def toolbox_entries(project, toolbox):
    """(present, stale): whether this exact toolbox is listed, and the other entries with the same file name."""
    name = Path(str(toolbox)).name.lower()
    want = os.path.normcase(os.path.normpath(str(toolbox)))
    present, stale = False, []
    for entry in project.toolboxes:
        if Path(entry["toolboxPath"]).name.lower() != name:
            continue
        if _toolbox_path(project, entry) == want:
            present = True
        else:
            stale.append(entry["toolboxPath"])
    return present, stale


def attach_toolbox(project, toolbox):
    """Attach TrainingReview.pyt, keeping the project's existing toolbox entries.

    updateToolboxes only adds: it never removes an entry, and Pro 3.7 raises "No valid default toolbox was set"
    for Blank.aprx (its default Blank.atbx does not exist) but has still added the entry. Success is therefore
    judged from the full path in project.toolboxes, not the file name, so a stale entry cannot pass for it.
    An entry already present is not added twice."""
    if toolbox_entries(project, toolbox)[0]:
        return []
    error = ""
    try:
        project.updateToolboxes(list(project.toolboxes)+[{"toolboxPath": str(toolbox), "isDefaultToolbox": False}])
    except Exception as exc:
        error = str(exc)
    if toolbox_entries(project, toolbox)[0]:
        return [f"Toolbox attached (Pro reported: {error})"] if error else []
    return [f"Toolbox not added: {error}"]


def repair_project(aprx, toolbox, backup=True):
    """Point the project's Training Review toolbox at this machine's TrainingReview.pyt and save.

    The project stores the toolbox by absolute path, so a project built on one machine shows the toolbox broken on
    another (the laptop's V:\\Developer path does not exist on the workstation). This adds the working entry. arcpy
    cannot remove one, so a stale entry stays and is returned in stale_entries to be removed in Pro (Catalog >
    Toolboxes > right-click > Remove); it only shows a red X. A copy of the project file is kept first. Pro must not
    have the project open. Returns {"toolbox", "backup", "notes", "stale_entries", "broken_layers"}; broken_layers
    lists layers whose data cannot be found.
    """
    aprx = Path(str(aprx))
    toolbox = Path(str(toolbox))
    if not toolbox.is_file():
        raise FileNotFoundError(f"Toolbox not found: {toolbox}")
    kept = None
    if backup:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        kept = aprx.with_name(f"{aprx.stem}.before-repair-{stamp}{aprx.suffix}")
        shutil.copy2(aprx, kept)
    project = arcpy.mp.ArcGISProject(str(aprx))
    notes = attach_toolbox(project, toolbox)
    stale = toolbox_entries(project, toolbox)[1]
    project.save()
    broken = []
    for m in project.listMaps():
        for layer in m.listLayers():
            if layer.isBroken:
                broken.append(f"{m.name}/{layer.name}")
    del project
    return {"toolbox": str(toolbox), "backup": None if kept is None else str(kept), "notes": notes,
            "stale_entries": stale, "broken_layers": broken}


# ---------------------------------------------------------------- exports

def write_boundaries(gdb, squares, sr=None):
    sr = sr or arcpy.SpatialReference(6341)
    out = {}
    for name, rects in squares.items():
        fc = f"{name.lower()}_boundary"
        arcpy.management.CreateFeatureclass(str(gdb), fc, "POLYGON", spatial_reference=sr)
        with arcpy.da.InsertCursor(str(Path(gdb)/fc), ["SHAPE@"]) as cursor:
            for x0, y0, x1, y1 in rects:
                cursor.insertRow([arcpy.Polygon(arcpy.Array([arcpy.Point(x0, y0), arcpy.Point(x0, y1),
                                                             arcpy.Point(x1, y1), arcpy.Point(x1, y0)]), sr)])
        out[name] = str(Path(gdb)/fc)
    return out


def imagery_patches(gdb, rows, raster, sr=None):
    """Polygon patches with CLASSVALUE for Export Training Data For Deep Learning (Classified Tiles).

    Only exportable labels with IMAGERY_USABLE = YES. Units whose patch is not inside the raster
    extent are refused (no silent drop)."""
    info = arcpy.Describe(str(raster))
    if info.bandCount != 4:
        raise ValueError(f"Imagery training needs the verified four-band NAIP raster; found {info.bandCount} bands")
    sr = sr or info.spatialReference
    if sr.factoryCode != 6341:
        raise ValueError("Imagery raster must be EPSG:6341 to match the review units")
    e = info.extent
    chosen = [r for r in rows if r["LABEL"] in tr.EXPORT_LABELS and r.get("IMAGERY_USABLE") == "YES"]
    outside = [r["UNIT_ID"] for r in chosen if r["X"]-r["PATCH_R_M"] < e.XMin or r["X"]+r["PATCH_R_M"] > e.XMax
               or r["Y"]-r["PATCH_R_M"] < e.YMin or r["Y"]+r["PATCH_R_M"] > e.YMax]
    if outside:
        raise ValueError(f"{len(outside)} labelled patches lie outside the imagery raster, e.g. {outside[:5]}")
    fc = str(Path(gdb)/"imagery_training_patches")
    arcpy.management.CreateFeatureclass(str(gdb), "imagery_training_patches", "POLYGON", spatial_reference=sr)
    arcpy.management.AddFields(fc, [["CLASSVALUE", "SHORT"], ["CLASSNAME", "TEXT", "CLASSNAME", 24],
                                    ["UNIT_ID", "TEXT", "UNIT_ID", 16]])
    with arcpy.da.InsertCursor(fc, ["SHAPE@", "CLASSVALUE", "CLASSNAME", "UNIT_ID"]) as cursor:
        for r in chosen:
            circle = arcpy.PointGeometry(arcpy.Point(r["X"], r["Y"]), sr).buffer(r["PATCH_R_M"])
            cursor.insertRow([circle, tr.IMAGERY_CLASS[r["LABEL"]], r["LABEL"], r["UNIT_ID"]])
    return fc, len(chosen)


def export_imagery_chips(raster, fc, out_folder, tile=256, stride=128):
    """Run Export Training Data For Deep Learning (Spatial Analyst copy of the tool; Classified Tiles)."""
    if arcpy.CheckExtension("Spatial") != "Available":
        raise RuntimeError("Spatial Analyst is not available for Export Training Data For Deep Learning")
    arcpy.CheckOutExtension("Spatial")
    try:
        arcpy.sa.ExportTrainingDataForDeepLearning(
            str(raster), str(out_folder), fc, "TIFF", tile, tile, stride, stride, "ONLY_TILES_WITH_FEATURES",
            "Classified_Tiles", 0, "CLASSVALUE", 0)
    finally:
        arcpy.CheckInExtension("Spatial")
    return arcpy.GetMessages()


def las_dataset(las, lasd):
    arcpy.management.CreateLasDataset(str(las), str(lasd), spatial_reference=arcpy.SpatialReference(6341),
                                      compute_stats="COMPUTE_STATS")
    return str(lasd)


def prepare_point_cloud(lasd, out_pctd, training_boundary, validation_boundary, block_size=50., excluded=None,
                        block_point_limit=8192):
    """Prepare Point Cloud Training Data (3D Analyst). Data preparation only; no training."""
    if arcpy.CheckExtension("3D") != "Available":
        raise RuntimeError("3D Analyst is not available")
    arcpy.CheckOutExtension("3D")
    try:
        arcpy.ddd.PreparePointCloudTrainingData(
            str(lasd), f"{block_size} Meters", str(out_pctd), str(training_boundary), None, str(validation_boundary),
            None, block_point_limit, None, list(excluded or [tr.IGNORE_CODE, *tr.NOISE_CODES]))
    finally:
        arcpy.CheckInExtension("3D")
    return arcpy.GetMessages()
