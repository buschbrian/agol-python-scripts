"""Independent output checks for the assembled Millcreek product library."""
import csv
import json
import math
from pathlib import Path
import sys

import arcpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy import common


def main(root):
    root = Path(root).resolve()
    products = json.loads((root/"products.json").read_text(encoding="utf-8"))
    buildings = json.loads((root/"building-heights.json").read_text(encoding="utf-8"))
    assert products["status"] == buildings["status"] == "complete"
    assert products["source_fingerprints_unchanged"]
    reference = arcpy.Raster(products["outputs"]["chm"])
    for path in products["outputs"].values():
        r, c = common.grid(path, .5)
        assert (r.width,r.height) == (reference.width,reference.height)
        assert common.same_xy_reference(r.spatialReference, reference.spatialReference)
        assert np.allclose([r.extent.XMin,r.extent.YMin,r.extent.XMax,r.extent.YMax],
                          [reference.extent.XMin,reference.extent.YMin,reference.extent.XMax,reference.extent.YMax],atol=1e-7,rtol=0)
    roof_cells, negative = 0, 0
    for offset in range(0, reference.height, 128):
        rows = min(128, reference.height-offset)
        corner = arcpy.Point(reference.extent.XMin, reference.extent.YMin+offset*.5)
        arrays = [arcpy.RasterToNumPyArray(products["outputs"][key],corner,reference.width,rows,-9999)
                  for key in ("roof_elevation","terrain","roof_height")]
        roof, ground, height = arrays
        paired = (roof != -9999) & (ground != -9999)
        assert np.array_equal(paired,height != -9999)
        assert np.array_equal(height[paired], (roof-ground)[paired])
        roof_cells += int(paired.sum())
        negative += int((height[paired]<0).sum())
    with open(buildings["csv"],newline="",encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        table = {row["SOURCE_ID"]:row for row in rows}
        assert len(rows) == len(table)
    numeric = ["GRID_CELLS","ROOF_CELLS","NEG_H_CELLS","ROOF_COV_PCT",
               "HEIGHT_P50_M","HEIGHT_P95_M","HEIGHT_MAX_M","AOI_PCT"]
    ids, estimated, repaired = set(),0,0
    fields = ["SOURCE_ID","HEIGHT_STATUS"]+numeric
    for row in arcpy.da.SearchCursor(buildings["output"],fields):
        key,status = row[:2]
        assert key not in ids and key in table
        ids.add(key)
        values = dict(zip(numeric,row[2:]))
        assert status == table[key]["HEIGHT_STATUS"] and status.startswith("UNVALIDATED")
        assert 0 <= values["NEG_H_CELLS"] <= values["ROOF_CELLS"] <= values["GRID_CELLS"]
        assert -.000001 <= values["AOI_PCT"] <= 100.000001
        for field,value in values.items():
            if value is None:
                assert table[key][field] == ""
            else:
                assert math.isfinite(value) and math.isclose(value,float(table[key][field]),rel_tol=1e-12,abs_tol=1e-12)
        if values["ROOF_CELLS"]:
            assert values["HEIGHT_P50_M"] <= values["HEIGHT_P95_M"] <= values["HEIGHT_MAX_M"]
            assert math.isclose(values["ROOF_COV_PCT"],100*values["ROOF_CELLS"]/values["GRID_CELLS"],abs_tol=1e-10)
            estimated += 1
        else:
            assert all(values[f] is None for f in ("HEIGHT_P50_M","HEIGHT_P95_M","HEIGHT_MAX_M"))
        repaired += int("GEOMETRY_REPAIRED" in status)
    assert ids == set(table)
    assert len(ids) == buildings["expected"] == buildings["completed"] == 22042
    assert estimated == buildings["counts"]["with_height"]
    assert repaired == 5
    result = {"status":"passed", "rasters":len(products["outputs"]), "all_grids_match":True,
              "all_city_roof_height_cells_match_paired_subtraction":True,
              "paired_city_roof_cells":roof_cells,"negative_city_roof_height_cells":negative,
              "building_features":len(ids),"buildings_with_height":estimated,
              "all_building_ids_unique":True,"csv_matches_feature_class":True,
              "all_buildings_unvalidated":True,"repaired_geometries_flagged":repaired,
              "source_fingerprints_unchanged":True,"observation":products["observation"]}
    common.write_json(root/"verification.json",result)
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
