# -*- coding: utf-8 -*-
"""Training Review -- step through TRAINING-label units in ArcGIS Pro.

Two tools used from the training review project (see reviews/2026-09-29/TRAINING_REVIEW.md):

* Next Training Unit: selects the lowest-REVIEW_ORDER unit with a blank LABEL (optionally one
  queue) and zooms the active map to it.
* Label Training Unit: writes LABEL / IMAGERY_USABLE / NOTES / REVIEWER / REVIEW_DATE to the one
  selected unit (label list read from the geodatabase domain), then advances to the next unit.

These are TRAINING labels only. Evaluation samples are never in this project, and a unit inside
the excluded evaluation domain is refused. Pro caches .pyt modules; the core is reloaded on use.
"""
import datetime
import importlib
import json
import os
from pathlib import Path
import sys

import arcpy

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from canopy import training_review as _tr  # noqa: E402
from canopy import training_review_arcpy as _tra  # noqa: E402

DEFAULT_LAYER = "Training units"
VIEW_M = 30.0


def _reload():
    importlib.reload(_tr)
    importlib.reload(_tra)


ADVANCED = "Advanced"


def _param(name, label, datatype, ptype="Required", default=None, values=None, category=None):
    p = arcpy.Parameter(displayName=label, name=name, datatype=datatype, parameterType=ptype, direction="Input")
    if category:
        p.category = category          # Pro collapses a category, so rarely used options stay out of the way
    if values is not None:
        p.filter.type = "ValueList"
        p.filter.list = list(values)
    if default is not None:
        p.value = default
    return p


def _map_layer(value):
    """The arcpy.mp Layer for a parameter value (a Layer object or a layer name in the active map)."""
    if hasattr(value, "getSelectionSet"):
        return value
    project = arcpy.mp.ArcGISProject("CURRENT")
    active = project.activeMap
    if active is None:
        raise ValueError("Open the Training review map first")
    name = str(value)
    for layer in active.listLayers():
        if layer.name == name or layer.longName == name:
            return layer
    raise ValueError(f"Layer {name!r} is not in the active map")


def _fc(layer):
    return arcpy.Describe(layer).catalogPath


def _session_file(fc):
    return Path(fc).parent.parent/"review_session.json"


def _remembered_reviewer(fc):
    try:
        return json.loads(_session_file(fc).read_text(encoding="utf-8")).get("REVIEWER") or ""
    except (OSError, ValueError):
        return ""


def _remember_reviewer(fc, reviewer):
    try:
        _session_file(fc).write_text(json.dumps({"REVIEWER": reviewer}), encoding="utf-8")
    except OSError:
        arcpy.AddWarning("Could not remember the reviewer name")


def _queue_values():
    return list(_tr.QUEUES)


def _go_to_next(layer, queue, view_m):
    """Select the next unlabelled unit and move an open map view to it. Returns its UNIT_ID or None.

    The work is in canopy/training_review_arcpy.go_to_next, which is reloaded on every run."""
    unit_id, messages = _tra.go_to_next(layer, queue or None, view_m, arcpy.mp.ArcGISProject("CURRENT"))
    for level, text in messages:
        (arcpy.AddWarning if level == "warning" else arcpy.AddMessage)(text)
    return unit_id


class Toolbox(object):
    def __init__(self):
        self.label = "Training Review"
        self.alias = "trainingreview"
        self.tools = [NextTrainingUnit, LabelTrainingUnit, LabelSelectedUnits]


class NextTrainingUnit(object):
    def __init__(self):
        self.label = "Next Training Unit"
        self.description = "Select and zoom to the next unlabelled TRAINING unit in REVIEW_ORDER."
        self.canRunInBackground = False

    def getParameterInfo(self):
        return [_param("in_layer", "Training units layer", "GPFeatureLayer", default=DEFAULT_LAYER),
                _param("queue", "Only this queue (optional)", "GPString", "Optional", values=_queue_values()),
                _param("view_m", "View width (m)", "GPDouble", default=VIEW_M, category=ADVANCED)]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        _reload()
        layer = _map_layer(parameters[0].value)
        _go_to_next(layer, parameters[1].valueAsText, parameters[2].value or VIEW_M)


class LabelTrainingUnit(object):
    def __init__(self):
        self.label = "Label Training Unit"
        self.description = ("Write a TRAINING label to the one selected unit (never an evaluation answer), "
                            "then advance to the next unlabelled unit.")
        self.canRunInBackground = False

    def getParameterInfo(self):
        return [_param("in_layer", "Training units layer", "GPFeatureLayer", default=DEFAULT_LAYER),
                _param("label", "Label", "GPString", values=list(_tr.LABELS)),
                _param("imagery_usable", "Imagery usable for this label", "GPString", "Optional", values=list(_tr.YES_NO)),
                _param("notes", "Notes (max 500 characters)", "GPString", "Optional"),
                _param("reviewer", "Reviewer", "GPString"),
                _param("replace", "Replace an existing different label", "GPBoolean", "Optional", default=False,
                       category=ADVANCED),
                _param("advance", "Advance to the next unit after saving", "GPBoolean", "Optional", default=True,
                       category=ADVANCED),
                _param("queue", "Advance within this queue only (optional)", "GPString", "Optional",
                       values=_queue_values(), category=ADVANCED),
                _param("view_m", "View width (m)", "GPDouble", "Optional", default=VIEW_M, category=ADVANCED)]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        layer, label, _, _, reviewer = parameters[:5]
        if layer.value is None:
            return
        try:
            fc = _fc(layer.value)
            codes = _tra.domain_codes(Path(fc).parent)
            if list(label.filter.list) != codes:
                label.filter.list = codes      # always the GDB's coded-value domain
            if not reviewer.altered and not reviewer.value:
                reviewer.value = _remembered_reviewer(fc) or None
        except Exception:  # validation must not raise; execute reports real errors
            pass

    def updateMessages(self, parameters):
        notes = parameters[3].valueAsText or ""
        if len(notes) > 500:
            parameters[3].setErrorMessage("Notes are limited to 500 characters")

    def execute(self, parameters, messages):
        _reload()
        layer = _map_layer(parameters[0].value)
        fc = _fc(layer)
        selected = layer.getSelectionSet() or []
        answer = {"LABEL": parameters[1].valueAsText, "IMAGERY_USABLE": parameters[2].valueAsText,
                  "NOTES": parameters[3].valueAsText, "REVIEWER": parameters[4].valueAsText,
                  "REVIEW_DATE": datetime.date.today().isoformat()}
        result = _tra.label_unit(fc, selected, answer, replace=bool(parameters[5].value))
        _remember_reviewer(fc, result["after"]["REVIEWER"])
        before = result["before"]["LABEL"]
        arcpy.AddMessage(f"{result['UNIT_ID']}: {before or '(blank)'} -> {result['after']['LABEL']}")
        for warning in result.get("warnings", []):
            arcpy.AddWarning(warning)
        if parameters[6].value is None or parameters[6].value:
            _go_to_next(layer, parameters[7].valueAsText, parameters[8].value or VIEW_M)


class LabelSelectedUnits(object):
    def __init__(self):
        self.label = "Label Selected Units"
        self.description = ("Write one TRAINING label to every selected unit at once (select them with the map's "
                            "selection tools or in the attribute table). All or nothing: if any selected unit fails "
                            "a check, none is written. At most %d units per run." % _tra.MAX_BULK)
        self.canRunInBackground = False

    def getParameterInfo(self):
        return [_param("in_layer", "Training units layer", "GPFeatureLayer", default=DEFAULT_LAYER),
                _param("label", "Label for every selected unit", "GPString", values=list(_tr.LABELS)),
                _param("imagery_usable", "Imagery usable for this label", "GPString", "Optional", values=list(_tr.YES_NO)),
                _param("notes", "Notes (max 500 characters)", "GPString", "Optional"),
                _param("reviewer", "Reviewer", "GPString"),
                _param("replace", "Replace existing different labels", "GPBoolean", "Optional", default=False,
                       category=ADVANCED),
                _param("advance", "Select the next unlabelled unit afterwards", "GPBoolean", "Optional", default=True,
                       category=ADVANCED),
                _param("queue", "Advance within this queue only (optional)", "GPString", "Optional",
                       values=_queue_values(), category=ADVANCED),
                _param("view_m", "View width (m)", "GPDouble", "Optional", default=VIEW_M, category=ADVANCED)]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        layer, label, _, _, reviewer = parameters[:5]
        if layer.value is None:
            return
        try:
            fc = _fc(layer.value)
            codes = _tra.domain_codes(Path(fc).parent)
            if list(label.filter.list) != codes:
                label.filter.list = codes
            if not reviewer.altered and not reviewer.value:
                reviewer.value = _remembered_reviewer(fc) or None
        except Exception:  # validation must not raise; execute reports real errors
            pass

    def updateMessages(self, parameters):
        notes = parameters[3].valueAsText or ""
        if len(notes) > 500:
            parameters[3].setErrorMessage("Notes are limited to 500 characters")

    def execute(self, parameters, messages):
        _reload()
        layer = _map_layer(parameters[0].value)
        fc = _fc(layer)
        selected = _tra.selected_oids(layer)
        answer = {"LABEL": parameters[1].valueAsText, "IMAGERY_USABLE": parameters[2].valueAsText,
                  "NOTES": parameters[3].valueAsText, "REVIEWER": parameters[4].valueAsText,
                  "REVIEW_DATE": datetime.date.today().isoformat()}
        history = Path(fc).parent.parent/"bulk-history"
        result = _tra.label_units(fc, selected, answer, replace=bool(parameters[5].value), history_dir=history)
        _remember_reviewer(fc, answer["REVIEWER"])
        shown = ", ".join(result["ids"][:8]) + (" ..." if result["units"] > 8 else "")
        arcpy.AddMessage(f"Labelled {result['units']} units as {result['label']} ({shown})"
                         + (f"; {result['replaced']} had a different label." if result["replaced"] else "."))
        for warning in result.get("warnings", []):
            arcpy.AddWarning(warning)
        if parameters[6].value is None or parameters[6].value:
            _go_to_next(layer, parameters[7].valueAsText, parameters[8].value or VIEW_M)
