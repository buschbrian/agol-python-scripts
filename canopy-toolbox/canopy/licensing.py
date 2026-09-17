"""Extension checkout. Imports arcpy; not importable outside ArcGIS Pro."""

from __future__ import annotations

import contextlib

import arcpy

REQUIRED = ("3D", "Spatial")


@contextlib.contextmanager
def extensions(*names: str):
    names = names or REQUIRED
    checked_out: list[str] = []
    try:
        for name in names:
            if arcpy.CheckExtension(name) != "Available":
                raise RuntimeError(f"the {name} Analyst extension is not available")
            arcpy.CheckOutExtension(name)
            checked_out.append(name)
        yield
    finally:
        for name in reversed(checked_out):
            arcpy.CheckInExtension(name)
