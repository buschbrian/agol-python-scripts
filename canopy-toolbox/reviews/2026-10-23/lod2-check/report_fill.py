"""The fill trial (fill_trial.py) against the October 22 massing on 12TVL2804, on the buildings judged in both with the same
compared cells (October 23, 2026). Plain Python with numpy."""
import csv, numpy as np, collections
R=r"H:\lidar\2023-salt-lake-valley\runs"
def load(p): return {r["FP_ID"]: r for r in csv.DictReader(open(p+r"\lod2-check.csv",encoding="utf-8"))}
old=load(R+r"\lod2-check-pilot-20261023"); new=load(R+r"\lod2-check-fill-trial-20261023")
f=lambda r,k: float(r[k]) if r.get(k) not in ("","None",None) else np.nan
ids=[i for i in new if i in old and old[i]["VERDICT"]!="too-few" and new[i]["VERDICT"]!="too-few"
     and abs(f(old[i],"COMPARED_CELLS")-f(new[i],"COMPARED_CELLS"))==0]
print("judged in both:", len(ids))
print("old", collections.Counter(old[i]["VERDICT"] for i in ids)); print("new", collections.Counter(new[i]["VERDICT"] for i in ids))
print("transitions", collections.Counter((old[i]["VERDICT"], new[i]["VERDICT"]) for i in ids if old[i]["VERDICT"]!=new[i]["VERDICT"]))
for src,name in ((old,"old"),(new,"new")):
    for k in ("LOD20","LOD12"):
        c=sum(f(src[i],k+"_CELLS") for i in ids)
        g=np.array([f(src[i],k+"_GROUND_PCT") for i in ids])
        print(name,k,"pooled w05 %.2f w1 %.2f"%(sum(f(src[i],k+"_CELLS")*f(src[i],k+"_WITHIN_05_PCT") for i in ids)/c, sum(f(src[i],k+"_CELLS")*f(src[i],k+"_WITHIN_1_PCT") for i in ids)/c),
              "ground>=10%:", int((g>=10).sum()), ">=50%:", int((g>=50).sum()), "median p95 %.2f"%np.nanmedian([f(src[i],k+"_ABS_P95_M") for i in ids]))
low=[i for i in ids if f(old[i],"ROOF_COV_PCT")<80]
print("cov<80:", len(low), "old", collections.Counter(old[i]["VERDICT"] for i in low), "new", collections.Counter(new[i]["VERDICT"] for i in low))
print("new broken/worse", [(i, new[i]["VERDICT"], new[i]["NOTE"], old[i]["VERDICT"]) for i in ids if new[i]["VERDICT"] in ("broken","worse")])
