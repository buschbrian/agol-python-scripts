r"""Item text and field descriptions for the eight Millcreek LiDAR 2023 items on ArcGIS Online (October 23, 2026).

    set PYTHONNOUSERSITE=1
    set PY="C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
    %PY% apply_metadata.py check                 # render every item file and validate it; no sign-in
    %PY% apply_metadata.py diff [ITEM ...]       # dry run: what would change online, item by item
    %PY% apply_metadata.py apply ITEM ... --go   # write item text (and, for features, field descriptions)
    %PY% apply_metadata.py snapshot OUT.json     # the online state of all eight items and their fields
    %PY% apply_metadata.py readback              # compare what is online with the item files

One Markdown file per item (`<key>.md`) holds everything that is applied: front matter (title, summary, tags, credits),
`# Description`, `# Terms of use`, and `# Fields ...` tables. `{{name}}` pastes a block from `_shared.md`;
`{{fields:N}}` pastes the field table of layer N (or `{{fields:scene}}`) into the description as a data dictionary.

What `apply --go` writes, and nothing else:
- item properties through `item.update(item_properties=...)`: title, snippet, description, tags, accessInformation,
  licenseInfo. Never `data=` or a thumbnail, so renderers, pop-ups and styles (the styling session's) are untouched;
- for the feature service only, per layer, `updateDefinition` with only the `fields` key, each field sent with its name
  and `description` (a JSON string of `{"value", "fieldValueType"}`), so aliases, drawing info and pop-ups stay as they
  are.
It never shares, deletes or moves anything. Sign-in is ArcGIS Pro's active portal, `GIS("pro")`, as upload.py.
"""
import argparse
import datetime
import difflib
import html
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
KEYS = ("features", "slope", "contours", "treetops", "crowns", "hillshade", "buildings3d", "terrain")
SUMMARY_MAX = 250            # ArcGIS Online shows up to 250 characters of a summary in search results
FIELD_DESCRIPTION_MAX = 500  # ArcGIS Online's limit for a field description
VALUE_TYPES = {"nameOrTitle", "description", "typeOrCategory", "countOrAmount", "percentageOrRatio", "measurement",
               "uniqueIdentifier", "orderedOrRanked", "binary", "locationOrPlaceName", "coordinate", "dateAndTime",
               "currency", "emailAddress", "phoneNumber", "url", ""}
CELL = 'style="border:1px solid #c8c8c8;padding:3px 6px;vertical-align:top;text-align:left"'


def shared():
    blocks, name = {}, None
    for line in (HERE/"_shared.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (\w+)\s*$", line)
        if m:
            name = m.group(1)
            blocks[name] = []
        elif name:
            blocks[name].append(line)
    return {k: "\n".join(v).strip() for k, v in blocks.items()}


def table_rows(lines):
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in lines if line.strip().startswith("|")]
    header, body = rows[0], [r for r in rows[2:]]
    return [dict(zip(header, r)) for r in body if len(r) == len(header)]


def parse(key):
    """The item file as front matter, sections and field tables."""
    text = (HERE/f"{key}.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    front = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        front[k.strip()] = v.strip()
    sections, current = {}, None
    for line in m.group(2).splitlines():
        h = re.match(r"^# (.+)$", line)
        if h:
            current = h.group(1).strip()
            sections[current] = []
        elif current:
            sections[current].append(line)
    fields = {}
    for title, lines in sections.items():
        f = re.match(r"^Fields (layer=(\d+)|document)\s*(\S*)", title)
        if f:
            fields[f.group(2) if f.group(2) is not None else "scene"] = {
                "apply": f.group(2) is not None, "layer_name": f.group(3), "rows": table_rows(lines)}
    return front, {k: "\n".join(v).strip() for k, v in sections.items()}, fields


def dictionary_markdown(rows):
    out = ["| Field | Alias | Type | Units | Description |", "|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| `{r['Field']}` | {r['Alias']} | {r['Type']} | {r['Units']} | {r['Description']} |")
    return "\n".join(out)


def to_html(markdown_text):
    import markdown
    out = markdown.markdown(markdown_text, extensions=["tables"], output_format="html")
    out = out.replace("<table>", '<table style="border-collapse:collapse;font-size:90%">')
    out = re.sub(r"<(td|th)( style=\"text-align: (left|right|center);\")?>", lambda m: f"<{m.group(1)} {CELL}>", out)
    return out


def render(key):
    """Everything that would be sent for one item."""
    front, sections, fields = parse(key)
    blocks = shared()

    def expand(text):
        text = re.sub(r"\{\{fields:(\w+)\}\}", lambda m: dictionary_markdown(fields[m.group(1)]["rows"]), text)
        return re.sub(r"\{\{(\w+)\}\}", lambda m: blocks[m.group(1)], text)

    props = {"title": front["title"], "snippet": front["summary"],
             "tags": [t.strip() for t in front["tags"].split(",") if t.strip()],
             "accessInformation": front["credits"],
             "description": to_html(expand(sections["Description"])),
             "licenseInfo": to_html(expand(sections["Terms of use"]))}
    layer_fields = {}
    for layer, spec in fields.items():
        if not spec["apply"]:
            continue
        layer_fields[int(layer)] = [{"name": r["Field"], "description": json.dumps(
            {"value": r["Description"], "fieldValueType": r["Value type"]})} for r in spec["rows"]]
    return {"key": key, "id": front["id"], "props": props, "fields": layer_fields, "documented": fields}


def problems(r):
    out = []
    p = r["props"]
    if len(p["snippet"]) > SUMMARY_MAX:
        out.append(f"summary is {len(p['snippet'])} characters (limit {SUMMARY_MAX})")
    if "planning estimate" not in p["snippet"].lower():
        out.append("summary lacks the planning-estimate warning")
    for name in ("description", "licenseInfo"):
        if "{{" in p[name]:
            out.append(f"{name} has an unexpanded placeholder")
    if "planning estimate" not in text_of(p["description"]).lower():
        out.append("description lacks the planning-estimate warning")
    for layer, spec in r["documented"].items():
        for row in spec["rows"]:
            if re.search(r"[<>]", row["Description"]):
                # ArcGIS Online answers success but silently drops the whole fields update (seen October 23)
                out.append(f"layer {layer} {row['Field']}: description contains < or >")
            if len(row["Description"]) > FIELD_DESCRIPTION_MAX:
                out.append(f"layer {layer} {row['Field']}: description {len(row['Description'])} characters")
            if row.get("Value type", "") not in VALUE_TYPES:
                out.append(f"layer {layer} {row['Field']}: unknown value type {row.get('Value type')!r}")
    return out


def text_of(markup):
    """Text for comparing: ArcGIS Online rewrites HTML on save, so tags, entities and spacing are ignored."""
    markup = re.sub(r"<(br|/p|/li|/tr|/h\d|/table)[^>]*>", "\n", markup or "")
    markup = re.sub(r"<(td|th)[^>]*>", " | ", markup)
    text = html.unescape(re.sub(r"<[^>]+>", "", markup))
    lines = [re.sub(r"\s+", " ", line).strip(" |") for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def connect():
    from arcgis.gis import GIS
    return GIS("pro")


def online_state(gis, key, item_id):
    item = gis.content.get(item_id)
    state = {"key": key, "id": item_id, "type": item.type, "access": item.access, "props": {
        "title": item.title, "snippet": item.snippet, "tags": list(item.tags or []),
        "accessInformation": item.accessInformation, "description": item.description, "licenseInfo": item.licenseInfo},
        "modified": item.modified, "layers": {}}
    if item.type == "Feature Service":
        for layer in item.layers:
            d = gis.session.get(layer.url, params={"f": "json"}).json()
            state["layers"][d["id"]] = {"name": d["name"], "fields": [
                {k: f.get(k) for k in ("name", "alias", "type", "description")} for f in d["fields"]],
                "drawingInfo_renderer_type": ((d.get("drawingInfo") or {}).get("renderer") or {}).get("type")}
    elif item.type == "Scene Service":
        for layer in gis.session.get(item.url, params={"f": "json"}).json().get("layers", []):
            d = gis.session.get(f"{item.url}/layers/{layer['id']}", params={"f": "json"}).json()
            state["layers"][d["id"]] = {"name": d.get("name"), "fields": [
                {k: f.get(k) for k in ("name", "alias", "type", "description")} for f in d.get("fields", [])]}
    return item, state


def wrap(text):
    return re.sub(r"(?<=[.;:]) (?=[A-Z(])", "\n", text).splitlines()


def diff_item(r, state):
    out = []
    for name, new in r["props"].items():
        old = state["props"].get(name)
        if name == "tags":
            if list(old or []) != new:
                out.append(f"  tags: {old} -> {new}")
            continue
        a, b = (text_of(old), text_of(new)) if name in ("description", "licenseInfo") else (old or "", new)
        if a != b:
            lines = list(difflib.unified_diff(wrap(a), wrap(b), f"online {name}", f"file {name}", lineterm="", n=0))
            out.append(f"  {name}: {len(lines)} diff lines")
            out.extend("    " + line for line in lines)
    for layer, sent in r["fields"].items():
        live = {f["name"]: f for f in state["layers"][layer]["fields"]}
        names = [f["name"] for f in sent]
        missing, extra = sorted(set(live) - set(names)), sorted(set(names) - set(live))
        if missing or extra:
            out.append(f"  layer {layer}: fields not documented {missing}; documented but not in the layer {extra}")
        changed = [f["name"] for f in sent if f["name"] in live and _desc(live[f["name"]].get("description")) !=
                   _desc(f["description"])]
        out.append(f"  layer {layer} ({state['layers'][layer]['name']}): {len(changed)} of {len(sent)} field "
                   f"descriptions would change")
    return out


def _desc(value):
    if not value:
        return None
    try:
        d = json.loads(value) if isinstance(value, str) else value
        return (d.get("value"), d.get("fieldValueType"))
    except ValueError:
        return (value, None)


def cmd_check(args):
    bad = 0
    out = HERE/"rendered"
    out.mkdir(exist_ok=True)
    for key in args.items or KEYS:
        r = render(key)
        issues = problems(r)
        bad += len(issues)
        page = (f"<h1>{html.escape(r['props']['title'])}</h1><p><i>{html.escape(r['props']['snippet'])}</i></p>"
                f"{r['props']['description']}<h2>Terms of use</h2>{r['props']['licenseInfo']}"
                f"<h2>Credits</h2><p>{html.escape(r['props']['accessInformation'])}</p>"
                f"<p>Tags: {html.escape(', '.join(r['props']['tags']))}</p>")
        (out/f"{key}.html").write_text(f"<!doctype html><meta charset='utf-8'><body style='font-family:sans-serif;"
                                       f"max-width:60rem;margin:auto'>{page}</body>", encoding="utf-8")
        print(f"{key}: summary {len(r['props']['snippet'])} chars, description {len(r['props']['description'])} "
              f"chars, {sum(len(v) for v in r['fields'].values())} field descriptions"
              + ("".join(f"\n  PROBLEM {i}" for i in issues) if issues else ""))
    return 1 if bad else 0


def cmd_diff(args, go=False):
    if cmd_check(argparse.Namespace(items=args.items)):
        print("Fix the problems above first.")
        return 1
    gis = connect()
    log = []
    for key in args.items or KEYS:
        r = render(key)
        item, state = online_state(gis, key, r["id"])
        print(f"\n== {key} {r['id']} ({state['type']}, {state['access']})")
        for line in diff_item(r, state):
            print(line)
        if not go:
            continue
        if state["access"] != "private":
            print(f"  note: item is shared ({state['access']}); sharing is left as it is")
        ok = item.update(item_properties=r["props"])
        entry = {"key": key, "id": r["id"], "when": datetime.datetime.now().isoformat(timespec="seconds"),
                 "item_update": ok, "layers": {}}
        print(f"  item.update: {ok}")
        for layer_id, sent in r["fields"].items():
            layer = next(lyr for lyr in item.layers if lyr.properties.id == layer_id)
            result = layer.manager.update_definition({"fields": sent})
            entry["layers"][layer_id] = result
            print(f"  layer {layer_id} updateDefinition (fields only, {len(sent)} fields): {result}")
        log.append(entry)
    if go:
        path = HERE/"record"/"applied.json"
        path.parent.mkdir(exist_ok=True)
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        path.write_text(json.dumps(previous + log, indent=1, default=str), encoding="utf-8")
    return 0


def cmd_snapshot(args):
    gis = connect()
    states = {}
    for key in KEYS:
        _, front_id = key, parse(key)[0]["id"]
        states[key] = online_state(gis, key, front_id)[1]
    Path(args.out).write_text(json.dumps(states, indent=1, default=str), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


def cmd_readback(args):
    gis = connect()
    report, failures = {}, 0
    for key in KEYS:
        r = render(key)
        _, state = online_state(gis, key, r["id"])
        checks = {}
        for name, new in r["props"].items():
            old = state["props"].get(name)
            if name in ("description", "licenseInfo"):
                checks[name] = text_of(old) == text_of(new)
            else:
                checks[name] = (list(old or []) if name == "tags" else old) == new
        for layer_id, sent in r["fields"].items():
            live = {f["name"]: _desc(f.get("description")) for f in state["layers"][layer_id]["fields"]}
            checks[f"layer {layer_id} field descriptions"] = all(live.get(f["name"]) == _desc(f["description"])
                                                                for f in sent)
        failures += sum(not v for v in checks.values())
        report[key] = {"id": r["id"], "access": state["access"], "modified": state["modified"], "matches": checks}
        print(key, state["access"], " ".join(f"{k}={'ok' if v else 'DIFFERS'}" for k, v in checks.items()))
    path = HERE/"record"/"readback.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return 1 if failures else 0


TOPICS = {"farming": "001", "biota": "002", "boundaries": "003", "climatologyMeteorologyAtmosphere": "004",
          "economy": "005", "elevation": "006", "environment": "007", "geoscientificInformation": "008",
          "health": "009", "imageryBaseMapsEarthCover": "010", "inlandWaters": "012", "location": "013",
          "planningCadastre": "015", "society": "016", "structure": "017", "transportation": "018",
          "utilitiesCommunication": "019"}
FLIGHTS = ("2023-10-07", "2023-11-04")
PUBLISHED = "2026-10-23"


def iso_metadata(key, synced_xml):
    """ArcGIS Online keeps an item's metadata (ArcGIS format, shown in the org's ISO 19115-3 style) in step with its
    title, summary, description, tags, credits and terms. This adds what the item text cannot carry: publication date,
    the lidar flight dates as the temporal extent, ISO topic categories, a point of contact, the 0.5 m resolution and a
    lineage statement. Elements already there are replaced, so rerunning gives the same file."""
    import xml.etree.ElementTree as ET
    front = parse(key)[0]
    root = ET.fromstring(synced_xml)
    ident = root.find("dataIdInfo")

    def child(parent, tag, **attrib):
        return ET.SubElement(parent, tag, attrib)

    def replace(parent, tag):
        for old in parent.findall(tag):
            parent.remove(old)
        return child(parent, tag)

    citation = ident.find("idCitation")
    date = replace(citation, "date")
    child(date, "pubDate").text = f"{PUBLISHED}T00:00:00"
    party = replace(citation, "citRespParty")
    child(party, "rpOrgName").text = "City of Millcreek GIS"
    child(child(party, "role"), "RoleCd", value="006")                      # originator
    poc = replace(ident, "idPoC")
    child(poc, "rpOrgName").text = "City of Millcreek GIS"
    child(child(poc, "role"), "RoleCd", value="007")                        # point of contact
    for old in ident.findall("tpCat"):
        ident.remove(old)
    for topic in [t.strip() for t in front["iso_topics"].split(",")]:
        child(child(ident, "tpCat"), "TopicCatCd", value=TOPICS[topic])
    scale = replace(ident, "dataScale")
    child(child(scale, "scaleDist"), "value", uom="m").text = front["resolution_m"]
    ext = ident.find("dataExt")
    for old in ext.findall("tempEle"):
        ext.remove(old)
    period = child(child(child(child(ext, "tempEle"), "TempExtent"), "exTemp"), "TM_Period")
    child(period, "tmBegin").text = f"{FLIGHTS[0]}T00:00:00"
    child(period, "tmEnd").text = f"{FLIGHTS[1]}T00:00:00"
    dq = replace(root, "dqInfo")
    child(child(child(dq, "dqScope"), "scpLvl"), "ScopeCd", value="005")    # dataset
    child(child(dq, "dataLineage"), "statement").text = (
        front["lineage"] + " Lidar flown 2023-10-07 to 2023-11-04 (USGS project UT_2023SaltLakeCo_C24). "
        "Unvalidated planning estimate; not surveyed or field-verified.")
    contact = replace(root, "mdContact")
    child(contact, "rpOrgName").text = "City of Millcreek GIS"
    child(child(contact, "role"), "RoleCd", value="007")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def cmd_metadata(args):
    gis = connect()
    out = HERE/"record"/"metadata"
    out.mkdir(parents=True, exist_ok=True)
    for key in args.items:
        r = render(key)
        item = gis.content.get(r["id"])
        synced = Path(item.metadata).read_text(encoding="utf-8")
        new = iso_metadata(key, synced)
        path = out/f"{key}.xml"
        path.write_text(new, encoding="utf-8")
        print(f"{key}: wrote {path.name} ({len(new)} characters; online now {len(synced)})")
        if not args.go:
            continue
        print(f"  item.update(metadata=...): {item.update(metadata=str(path))}")
        _, state = online_state(gis, key, r["id"])
        same = {n: (text_of(state['props'][n]) == text_of(v) if n in ("description", "licenseInfo") else
                    (list(state['props'][n] or []) if n == "tags" else state['props'][n]) == v)
                for n, v in r["props"].items()}
        print("  item text after the upload: " + " ".join(f"{n}={'ok' if ok else 'CHANGED'}" for n, ok in same.items()))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "diff"):
        sub.add_parser(name).add_argument("items", nargs="*", help=f"any of {', '.join(KEYS)}; default all")
    a = sub.add_parser("apply")
    a.add_argument("items", nargs="+")
    a.add_argument("--go", action="store_true", help="write to ArcGIS Online; without it this is the dry run")
    m = sub.add_parser("metadata")
    m.add_argument("items", nargs="+")
    m.add_argument("--go", action="store_true", help="upload the metadata; without it, only write record/metadata")
    sub.add_parser("snapshot").add_argument("out")
    sub.add_parser("readback")
    args = p.parse_args(argv)
    unknown = [k for k in getattr(args, "items", []) if k not in KEYS]
    if unknown:
        p.error(f"unknown items {unknown}; choose from {', '.join(KEYS)}")
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "diff":
        return cmd_diff(args)
    if args.cmd == "apply":
        return cmd_diff(args, go=args.go)
    if args.cmd == "metadata":
        return cmd_metadata(args)
    if args.cmd == "snapshot":
        return cmd_snapshot(args)
    return cmd_readback(args)


if __name__ == "__main__":
    sys.exit(main())
