"""Citywide tables for the README (October 23, 2026): verdicts by roof type and lidar roof coverage, ground-level shares,
the hybrid and failure counts, from lod2_check.py measure's CSV. Plain Python with numpy; AUCs need scipy (run from Pro Python)."""
import csv, sys, numpy as np, collections
rows=[r for r in csv.DictReader(open(sys.argv[1]+r"\lod2-check.csv",encoding="utf-8"))]
f=lambda r,k: float(r[k]) if r[k] not in ("","None") else np.nan
print(collections.Counter(r["VERDICT"] for r in rows))
for k in ("LOD20_GROUND_PCT","LOD12_GROUND_PCT"):
    v=np.array([f(r,k) for r in rows]); print(k, "n", (~np.isnan(v)).sum(), ">0", (v>0).sum(), ">=5", (v>=5).sum(), ">=10", (v>=10).sum(), ">=50", (v>=50).sum(), ">=90", (v>=90).sum())
ok=[r for r in rows if r["VERDICT"] in ("better","same")]
g=np.array([f(r,"LOD20_GROUND_PCT") for r in ok])
print("passing with LOD20 ground >=5%", (g>=5).sum(), ">=10%", (g>=10).sum(), ">=20%", (g>=20).sum())
print(" of those >=10%, coverage<80:", sum(1 for r in ok if f(r,"LOD20_GROUND_PCT")>=10 and f(r,"ROOF_COV_PCT")<80))
# LOD1.2 at ground
l12g=[r for r in rows if f(r,"LOD12_GROUND_PCT")>=50]
print("LOD1.2 blocks mostly at ground:", len(l12g), collections.Counter(r["VERDICT"] for r in l12g), "cov<80:", sum(f(r,"ROOF_COV_PCT")<80 for r in l12g))
print("   largest", sorted([(round(f(r,"FOOTPRINT_M2")), r["FP_ID"], round(f(r,"ROOF_COV_PCT"))) for r in l12g], reverse=True)[:8])
# hybrid: LOD2 where better/same and LOD20 ground < 10%
hyb=[r for r in rows if r["VERDICT"] in ("better","same") and not f(r,"LOD20_GROUND_PCT")>=10]
print("hybrid LOD2.0:", len(hyb), "of", len(rows), "area", round(sum(f(r,"FOOTPRINT_M2") for r in hyb)), "of", round(sum(f(r,"FOOTPRINT_M2") for r in rows)))
# pooled measures for hybrid surface vs all-LOD12 vs all-LOD20 on judged
j=[r for r in rows if r["VERDICT"]!="too-few"]; H={r["FP_ID"] for r in hyb}
def pooled(pick):
    c=w5=w1=0
    for r in j:
        k=pick(r); n=f(r,k+"_CELLS"); c+=n; w5+=n*f(r,k+"_WITHIN_05_PCT"); w1+=n*f(r,k+"_WITHIN_1_PCT")
    return round(w5/c,2), round(w1/c,2)
print("pooled w05,w1: LOD1.2", pooled(lambda r:"LOD12"), "LOD2.0", pooled(lambda r:"LOD20"), "hybrid", pooled(lambda r:"LOD20" if r["FP_ID"] in H else "LOD12"))
# per type summary for README with ground
for t in ("multi-level","steep-pitched","pitched","flat-parapet","flat","other","too-few"):
    p=[r for r in rows if r["ROOF_TYPE"]==t]; c=collections.Counter(r["VERDICT"] for r in p)
    pj=[r for r in p if r["VERDICT"]!="too-few"]
    med=lambda k: np.nanmedian([f(r,k) for r in pj]) if pj else np.nan
    print(f"| {t} | {len(p):,} | {c['better']:,} | {c['same']:,} | {c['worse']:,} | {c['broken']:,} | {med('LOD20_ABS_P50_M'):.2f} / {med('LOD12_ABS_P50_M'):.2f} | {med('LOD20_ABS_P95_M'):.2f} / {med('LOD12_ABS_P95_M'):.2f} | {med('LOD20_WITHIN_05_PCT'):.0f} / {med('LOD12_WITHIN_05_PCT'):.0f} | {med('LOD20_WITHIN_1_PCT'):.0f} / {med('LOD12_WITHIN_1_PCT'):.0f} | {sum(1 for r in p if r['FP_ID'] in H):,} |")
p=rows; c=collections.Counter(r["VERDICT"] for r in p); pj=j
med=lambda k: np.nanmedian([f(r,k) for r in pj])
print(f"| all | {len(p):,} | {c['better']:,} | {c['same']:,} | {c['worse']:,} | {c['broken']:,} | {med('LOD20_ABS_P50_M'):.2f} / {med('LOD12_ABS_P50_M'):.2f} | {med('LOD20_ABS_P95_M'):.2f} / {med('LOD12_ABS_P95_M'):.2f} | {med('LOD20_WITHIN_05_PCT'):.0f} / {med('LOD12_WITHIN_05_PCT'):.0f} | {med('LOD20_WITHIN_1_PCT'):.0f} / {med('LOD12_WITHIN_1_PCT'):.0f} | {len(H):,} |")
for name, lo, hi in (("under 80%",0,80),("80-95%",80,95),("95% and over",95,1e9)):
    p=[r for r in rows if lo<=f(r,"ROOF_COV_PCT")<hi]; c=collections.Counter(r["VERDICT"] for r in p)
    print(f"| {name} | {len(p):,} | {c['better']:,} | {c['same']:,} | {c['worse']:,} | {c['broken']:,} | {c['too-few']:,} | {sum(1 for r in p if f(r,'LOD20_GROUND_PCT')>=10):,} | {sum(1 for r in p if f(r,'LOD12_GROUND_PCT')>=50):,} |")
print("broken flags", collections.Counter(fl for r in rows if r["VERDICT"]=="broken" for fl in r["NOTE"].split(";")))
bad=[r for r in j if r["VERDICT"] in ("worse","broken")]
print("bad dropped>0 or ground>=10:", sum(1 for r in bad if f(r,"LOD20_DROPPED_PCT")>0 or f(r,"LOD20_GROUND_PCT")>=10), "of", len(bad))
print("bad with cov>=95 and dropped>=10:", sum(1 for r in bad if f(r,"ROOF_COV_PCT")>=95 and f(r,"LOD20_DROPPED_PCT")>=10))
print("too-few FP_CELLS median", np.median([f(r,"FP_CELLS") for r in rows if r["VERDICT"]=="too-few"]))

# predictability: AUC of simple attributes for bad = worse|broken
bad = np.array([r["VERDICT"] in ("worse","broken") for r in j])
def auc(x, y):
    x=np.asarray(x,float); ok=~np.isnan(x); x,y=x[ok],y[ok]
    from scipy.stats import rankdata
    rk=rankdata(x); n1=y.sum(); n0=len(y)-n1
    return (rk[y].sum()-n1*(n1+1)/2)/(n1*n0)
for k in ("LOD20_TOOL_RMSE","LOD20_TOOL_PCT_HI","LOD12_TOOL_RMSE","ROOF_COV_PCT","FOOTPRINT_M2","RELIEF_M","SLOPE_P50_DEG","LOD20_DROPPED_PCT","LOD20_ABS_P95_M"):
    print("AUC", k, round(auc([f(r,k) for r in j], bad),3))
