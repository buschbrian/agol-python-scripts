# Blind audit sample 2 (40 units)

A fresh test of the corrected triage (`../triage-2`, see [TRIAGE.md](../TRIAGE.md)). Audit 1 is used up: the rules were changed
after it. These 40 units were drawn at random (seed 20260931) from the units the corrected triage puts forward as easy,
leaving out every unit already labelled (58) and so every audit-1 unit. **It only counts if you label them without seeing the
proposal.**

- Do not open `../triage-2/triage-proposals.csv` (or `audit-sample.json`, which lists the class mix) until all 40 are labelled.
- **Label only the returns in the patch** (the rule in the labelling checklist). **Next Training Unit** now prints how many
  points the patch holds and how high they reach; if the object you can see is beside the circle, label what is in the circle,
  or use UNSURE or MIXED. The score counts those two as "not confirmed".
- Judge from the points and the cross-section, not from the imagery or from what you expect.

## Steps in ArcGIS Pro
1. **Select By Attributes** on the *Training units* layer, SQL, and paste the one line in [audit-select.txt](audit-select.txt).
   It selects 40 units, all still unlabelled.
2. Open the attribute table, click **Show selected records**, and label each row with **Label Training Unit**. Open *Advanced* and
   **untick "Select the next unlabelled unit afterwards"**, or the tool leaves the sample.

## Score it
```powershell
training_labels.bat save
python reviews/2026-09-30/audit_sample.py score reviews/2026-09-30/audit-2 --triage reviews/2026-09-30/triage-2/triage-proposals.csv --out reviews/2026-09-30/audit-2/score.json
```
It refuses to score while any of the 40 is unlabelled, and gives the one-sided 95% lower bound on the share of triage candidates that are
right (40 of 40 gives at least 0.928; 39 of 40, 0.887; 38 of 40, 0.851). Only after that, and a recorded decision, should any triage
candidate become a training label.

## Result (October 20, 2026; preliminary)
All 40 were labelled blind on the click-through label page (`../../2026-10-20/label-page`). Brian then removed one, **Q2-0010**, as
ambiguous (it had been answered GROUND, then BUILDING_ROOF; the triage proposed BUILDING_ROOF), so the official score.json waits for it
to be labelled again. Scored both ways before the removal:

| Q2-0010 counted as | Agree | One-sided 95% lower bound | Roof | Tree | Wall |
|---|---:|---:|---:|---:|---:|
| GROUND | 36 of 40 | 0.786 | 22 of 23 | 14 of 15 | 0 of 2 |
| BUILDING_ROOF | 37 of 40 | 0.817 | 23 of 23 | 14 of 15 | 0 of 2 |

The tree miss is a MIXED answer (Q3-0128); both proposed walls were roofs (Q5-0145, Q6-0160). **Decision (Brian, October 20): triage v2
roof and tree AUTO candidates are auto-accepted as training answers, walls never**, with REVIEWER `triage-v2` so they can always be
told apart from human labels (`../../2026-10-20/auto_accept.py`). Choosing roof and tree after seeing the wall result is a choice made
on these data; with two wall units it is a judgement, not a measurement.
