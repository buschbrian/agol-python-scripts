"""Bind a fresh worksheet to the exact copied independent frame; never label it."""
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from canopy import common, validation


def main(root):
    review=Path(root).resolve()/"independent-review"
    out=review/"ready"
    packet=validation.export_labels(str(review/"reference.gdb"),str(out),batch=1)
    old=json.loads((review/"packet.json").read_text(encoding="utf-8"))
    assert set(map(tuple,packet["units"]))==set(map(tuple,old["units"]))
    assert packet["reference_units"]==old["reference_units"]==1468
    preview=validation.import_labels(str(review/"reference.gdb"),str(out/"labels.csv"),str(out/"packet.json"),apply=False)
    with (out/"labels.csv").open(newline="",encoding="utf-8-sig") as handle:
        rows=list(csv.DictReader(handle))
    assert len(rows)==743 and all(not r["LABEL"] for r in rows)
    common.write_json(review/"ready-preview.json",{k:v for k,v in preview.items() if k!="changes"})
    common.write_json(review/"ready.json",{"status":"passed","reference":str(review/"reference.gdb"),
        "worksheet":str(out/"labels.csv"),"packet":str(out/"packet.json"),"rows":len(rows),
        "same_fixed_sample_ids":True,"all_labels_blank":True,"import_preview":preview["status"],
        "reference_frame_digest":packet["frame_digest"],"original_reference_unchanged":True})
    print(json.dumps({"status":"passed","rows":len(rows),"preview":preview["status"],"worksheet":str(out/"labels.csv")},indent=2))


if __name__=="__main__":main(sys.argv[1])
