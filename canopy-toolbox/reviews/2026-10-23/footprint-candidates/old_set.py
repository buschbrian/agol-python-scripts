r"""Which of the 08:30 comparison's 1,219 candidates stayed in the 11:31 rerun's 1,264, which left and which joined.

    python -I reviews/2026-10-23/footprint-candidates/old_set.py OUT_JSON      (ArcGIS Pro env millcreek-py3)

The 08:30 GeoPackage was overwritten by the rerun, so the old set is rebuilt here. Overture is projected the old way
(GeoPandas' default for 4326 -> 6341, a null transformation) and classified with the comparison script's own zonal code,
imported read-only from Z:\GIS\overture\2026-10-21.0\millcreek\lidar_compare.py, using the same MATCH and LIDAR rules.
The rebuild is trusted only if it reproduces the 08:30 README's MATCH x LIDAR table in every cell. The same code on the
current (ITRF08) projection must also reproduce the rerun's GeoPackage classes on every building. Writes only OUT_JSON.
"""
import importlib.util
import json
import sys

import geopandas as gpd
import pandas as pd
import shapely

LC_PATH = r"Z:\GIS\overture\2026-10-21.0\millcreek\lidar_compare.py"
TABLE_0830 = {  # the 08:30 README's outline table (MATCH x LIDAR)
    "MATCH": {"ROOF": 18654, "SOME_ROOF": 167, "NO_ROOF": 58, "OUTSIDE_LIDAR_AOI": 8},
    "PARTIAL": {"ROOF": 1850, "SOME_ROOF": 108, "NO_ROOF": 27, "OUTSIDE_LIDAR_AOI": 1},
    "OVERTURE_ONLY": {"ROOF": 1219, "SOME_ROOF": 80, "NO_ROOF": 203, "OUTSIDE_LIDAR_AOI": 64},
}


def module():
    spec = importlib.util.spec_from_file_location("lidar_compare", LC_PATH)
    lc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lc)
    return lc


def old_overture(lc):
    import duckdb
    con = duckdb.connect()
    df = con.sql(f"""select id, source_datasets, class, subtype, height, num_floors,
                                         names.primary as name, geometry
                                  from '{lc.HERE}/buildings.parquet'""").df()
    geom = shapely.from_wkb(df.pop("geometry").map(bytes))
    return gpd.GeoDataFrame(df, geometry=geom, crs=4326).to_crs(lc.CRS)


def classify(lc, ov, county, ras):
    """MATCH and LIDAR exactly as lidar_compare.main assigns them."""
    ov = ov.join(lc.zonal(ov, ras, "L_"))
    inter = gpd.overlay(ov[["id", "geometry"]], county[["C_IDX", "geometry"]], how="intersection", keep_geom_type=True)
    inter["A"] = inter.area
    best = inter.sort_values("A", ascending=False).drop_duplicates("id").set_index("id")
    ov = ov.set_index("id")
    ov["C_IDX"] = best["C_IDX"]
    ov["OVL_M2"] = best["A"]
    ov["N_COUNTY"] = inter.groupby("id").size()
    ov["N_COUNTY"] = ov["N_COUNTY"].fillna(0).astype(int)
    ca = county.set_index("C_IDX").geometry.area
    m = ov["C_IDX"].notna()
    union = ov.loc[m].area + ca.loc[ov.loc[m, "C_IDX"]].values - ov.loc[m, "OVL_M2"]
    ov.loc[m, "IOU"] = ov.loc[m, "OVL_M2"] / union
    ov["OVL_OF_OV"] = ov["OVL_M2"].fillna(0) / ov.area

    def match(r):
        if r.N_COUNTY == 0 or r.OVL_OF_OV < 0.1:
            return "OVERTURE_ONLY"
        return "MATCH" if r.IOU >= 0.5 else "PARTIAL"

    def lidar(r):
        if pd.isna(r.L_ROOF_COV_PCT) or r.L_AOI_PCT < 50:
            return "OUTSIDE_LIDAR_AOI"
        if r.L_ROOF_COV_PCT >= lc.ROOF_MIN_PCT:
            return "ROOF"
        return "NO_ROOF" if r.L_ROOF_COV_PCT < lc.ROOF_NONE_PCT else "SOME_ROOF"
    ov["MATCH"] = ov.apply(match, axis=1)
    ov["LIDAR"] = ov.apply(lidar, axis=1)
    return ov[["source_datasets", "MATCH", "LIDAR", "L_ROOF_COV_PCT", "IOU", "OVL_OF_OV"]]


def main(out):
    lc = module()
    county = gpd.read_file(f"{lc.PROD}/buildings.gdb", layer="building_heights")
    county["C_IDX"] = county.index
    ras = lc.Rasters()
    old = classify(lc, old_overture(lc), county, ras)
    table = old.groupby(["MATCH", "LIDAR"]).size().unstack(fill_value=0)
    reproduced = {k: {c: int(table.loc[k].get(c, 0)) for c in v} for k, v in TABLE_0830.items()}
    assert reproduced == TABLE_0830, reproduced
    new = classify(lc, lc.load_overture(), county, ras)
    gpkg = gpd.read_file(lc.OUT + "/overture_vs_lidar.gpkg", layer="overture_buildings").set_index("id")
    differ = int(((new["MATCH"] != gpkg.loc[new.index, "MATCH"]) | (new["LIDAR"] != gpkg.loc[new.index, "LIDAR"])).sum())
    assert differ == 0, differ

    def classes(df):
        return {f"{m} / {l}": int(n) for (m, l), n in df.groupby(["MATCH", "LIDAR"]).size().items()}

    def cand(df):
        return set(df.index[(df.MATCH == "OVERTURE_ONLY") & (df.LIDAR == "ROOF")])
    a, b = cand(old), cand(new)
    assert len(a) == 1219 and len(b) == 1264
    left, joined = sorted(a - b), sorted(b - a)
    result = {"old_0830": len(a), "new_1131": len(b), "stayed": len(a & b), "left": len(left), "joined": len(joined),
              "old_table_reproduced": True, "new_classes_equal_gpkg": True,
              "left_now": classes(new.loc[left]), "joined_was": classes(old.loc[joined]),
              "left_by_source": new.loc[left, "source_datasets"].value_counts().to_dict(),
              "joined_by_source": new.loc[joined, "source_datasets"].value_counts().to_dict(),
              "left_ids": left, "joined_ids": joined}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print(json.dumps({k: v for k, v in result.items() if not k.endswith("_ids")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
