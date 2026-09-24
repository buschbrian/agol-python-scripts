"""Per-acquisition record: a slim, path-free summary of a delivery and its markdown rendering.

Pure Python so the record's rules are testable without ArcGIS. delivery.index gathers the
facts with arcpy and hands them here. The record carries tile names, never per-file paths:
header paths are resolved, and a mapped drive resolves to its server share, which should
not land in a public repository. Input paths are kept as the caller passed them, except that a
network (UNC) path is reduced to its final name, since it names the server and share.
"""
from collections import Counter
from datetime import date, timedelta
import re
import statistics

SCHEMA = 1

NOTES = [
    "Header bounds are rectangular screening coverage, not verified point support.",
    "Returns per header area counts every return; it is not nominal pulse density.",
    "Header Z ranges include every class, noise included.",
    "LAS file-creation dates are processing dates, not flight dates.",
]


def public_path(value):
    """A caller-supplied path fit for a public record: a UNC path keeps only its final name."""
    if value is None:
        return None
    text = str(value)
    if not re.match(r"[\\/]{2}", text):
        return text
    parts = [part for part in re.split(r"[\\/]+", text) if part]
    if parts[:2] in (["?", "UNC"], [".", "UNC"]):
        parts = parts[2:]
    # Server and share are the first two parts; with nothing after them there is no safe name.
    return f"{parts[-1]} (network path redacted)" if len(parts) > 2 else "(network path redacted)"


def creation_date(year, day):
    """LAS header year and day of year (1 = January 1) as an ISO date, or None if unset."""
    if not year or not day or not 1 <= day <= 366:
        return None
    value = date(year, 1, 1) + timedelta(days=day - 1)
    return value.isoformat() if value.year == year else None


def tile_entry(row):
    """One tile's facts without its filesystem path."""
    xmin, ymin, xmax, ymax = row["extent"]
    area = (xmax - xmin) * (ymax - ymin)
    dates = row.get("FLIGHT_DATES")
    return {"tile": row["tile"], "points": row["points"], "bytes": row["bytes"],
            "las_version": row["version"], "point_format": row["format"],
            "extent": [xmin, ymin, xmax, ymax], "z_min": row["z_min"], "z_max": row["z_max"],
            "returns_m2": row["points"] / area if area > 0 else None,
            "created": creation_date(row.get("file_creation_year"), row.get("file_creation_day")),
            "flight_dates": dates.split(";") if dates else ([] if "FLIGHT_DATES" in row else None)}


def summarize(tiles):
    density = [t["returns_m2"] for t in tiles if t["returns_m2"] is not None]
    created = sorted({t["created"] for t in tiles if t["created"]})
    summary = {
        "tiles": len(tiles), "points": sum(t["points"] for t in tiles),
        "bytes": sum(t["bytes"] for t in tiles),
        "las_versions": dict(sorted(Counter(t["las_version"] for t in tiles).items())),
        "point_formats": {str(k): v for k, v in sorted(Counter(t["point_format"] for t in tiles).items())},
        "z_min": min(t["z_min"] for t in tiles), "z_max": max(t["z_max"] for t in tiles),
        "returns_m2": {"min": min(density), "median": statistics.median(density),
                       "max": max(density)} if density else None,
        "created": created,
    }
    dated = [t for t in tiles if t["flight_dates"] is not None]
    if dated:
        every = sorted({d for t in dated for d in t["flight_dates"]})
        summary["flight_dates"] = {"first": every[0] if every else None,
                                   "last": every[-1] if every else None, "distinct": every,
                                   "undated_tiles": sorted(t["tile"] for t in dated if not t["flight_dates"])}
    return summary


def flight_groups(tiles):
    """Tiles grouped by their exact set of flight dates, largest group first."""
    groups = {}
    for tile in tiles:
        if tile["flight_dates"]:
            groups.setdefault(tuple(tile["flight_dates"]), []).append(tile["tile"])
    return sorted(((dates, sorted(names)) for dates, names in groups.items()),
                  key=lambda item: (-len(item[1]), item[0]))


def build(rows, label, delivery, crs, generated, swath_index=None, coverage=None):
    tiles = sorted((tile_entry(row) for row in rows), key=lambda t: t["tile"])
    if swath_index and "path" in swath_index:
        swath_index = {**swath_index, "path": public_path(swath_index["path"])}
    if coverage:
        coverage = {**coverage, "boundary": public_path(coverage.get("boundary"))}
        if coverage.get("tile_index"):
            coverage["tile_index"] = {**coverage["tile_index"],
                                      "path": public_path(coverage["tile_index"]["path"])}
    return {"schema": SCHEMA, "label": label, "delivery": public_path(delivery), "generated": generated,
            "crs": crs, "summary": summarize(tiles), "swath_index": swath_index,
            "coverage": coverage, "tiles": tiles, "notes": NOTES}


def _count(value):
    return f"{value:,}"


def _percent(value):
    """Two decimals, without rounding a real sliver down to a misleading 0.00%."""
    return "<0.01%" if 0 < value < .005 else f"{value:.2f}%"


def render(record):
    """Markdown facts page for one acquisition. Regenerate it; do not edit it by hand."""
    s, crs = record["summary"], record["crs"]
    lines = [f"# Acquisition facts — {record['label']}", "",
             f"Generated by `canopy index-delivery` on {record['generated']} from `{record['delivery']}`. "
             "This page is machine-written: regenerate it rather than editing it. Declared facts from the "
             "vendor, and their interpretation, belong in the acquisition's RECORD.md.", "",
             "## Delivery", "",
             "| Fact | Value |", "|---|---|",
             f"| Tiles | {_count(s['tiles'])} |",
             f"| Points | {_count(s['points'])} |",
             f"| Size | {s['bytes'] / 1e9:,.2f} GB (decimal) |",
             "| LAS versions | " + ", ".join(f"{k}: {v}" for k, v in s["las_versions"].items()) + " |",
             "| Point formats | " + ", ".join(f"{k}: {v}" for k, v in s["point_formats"].items()) + " |",
             f"| Header Z range | {s['z_min']:.2f} to {s['z_max']:.2f} m, all classes |"]
    if s["returns_m2"]:
        d = s["returns_m2"]
        lines.append(f"| Returns per header m² | {d['min']:.1f} min, {d['median']:.1f} median, {d['max']:.1f} max |")
    lines.append("| File-creation dates | " + (", ".join(s["created"]) or "unset") + " |")
    lines += ["", "## Coordinate reference", "", "| Axis | Declared in the LAS headers |", "|---|---|",
              f"| Horizontal | {crs.get('horizontal') or 'none'}"
              + (f" (EPSG {crs['horizontal_code']})" if crs.get("horizontal_code") else "") + " |",
              f"| Vertical | {crs.get('vertical') or 'none declared'}"
              + (f" (EPSG {crs['vertical_code']})" if crs.get("vertical_code") else "") + " |", "",
              "Compare these against another epoch before differencing surfaces: a datum or geoid mismatch "
              "reads as terrain change."]

    if "flight_dates" in s:
        f = s["flight_dates"]
        lines += ["", "## Flight dates", "",
                  f"From {record['swath_index']['swaths']} swath polygons intersecting each tile's header "
                  f"rectangle: {f['first']} to {f['last']}, {len(f['distinct'])} distinct dates. A tile several "
                  "swaths cross carries every date, because a header rectangle does not say which swath supplied "
                  "which point.", "", "| Dates | Tiles | Names |", "|---|---:|---|"]
        for dates, names in flight_groups(record["tiles"]):
            lines.append(f"| {', '.join(dates)} | {len(names)} | {', '.join(names)} |")
        if f["undated_tiles"]:
            lines += ["", f"No swath intersects: {', '.join(f['undated_tiles'])}."]

    c = record.get("coverage")
    if c:
        lines += ["", "## Coverage of the boundary", "",
                  f"Boundary `{c['boundary']}`: {c['boundary_m2'] / 1e6:.3f} km². Header rectangles cover "
                  f"**{c['covered_pct']:.2f}%** of it ({c['covered_m2'] / 1e4:,.1f} ha)."]
        if c.get("projected_from"):
            lines += ["", f"The boundary was projected from {c['projected_from']} to the delivery CRS"
                      + (f" with `{c['transformation']}`." if c.get("transformation") else " with no datum transformation.")]
        if c.get("outside"):
            lines += ["", f"Delivery tiles not touching the boundary: {', '.join(c['outside'])}."]
        if c.get("tile_index"):
            t = c["tile_index"]
            lines += ["", f"Against `{t['path']}`, the boundary touches {t['touching']} index tiles: "
                      f"{t['in_hand']} in hand, {len(t['missing'])} missing."]
            if t["missing"]:
                lines += ["", "| Missing tile | Boundary area inside | Share of boundary |", "|---|---:|---:|"]
                for m in t["missing"]:
                    lines.append(f"| {m['tile']} | {m['boundary_m2'] / 1e4:,.2f} ha | {_percent(m['share_pct'])} |")

    lines += ["", "## Caveats", ""] + [f"- {note}" for note in record["notes"]] + [""]
    return "\n".join(lines)
