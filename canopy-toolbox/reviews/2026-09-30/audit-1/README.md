# Blind audit sample 1 (40 units)

These 40 units were drawn at random (seed 20260930) from the units the independent-evidence triage put forward as easy
(see [TRIAGE.md](../TRIAGE.md)), leaving out every unit a person had already labelled when the draw was made (18). Labelling
them measures how often the triage is right. **The measurement only counts if you label them without seeing the proposal**, so:

- Do not open `../triage/triage-proposals.csv` (or `audit-sample.json`, which lists the class mix) until all 40 are labelled.
- Label each unit exactly as you would any other: from the points and the cross-section, never from what you expect.
- Use **UNSURE** or **MIXED** when you cannot tell. The score counts those as "not confirmed", the cautious reading.

## Steps in ArcGIS Pro

1. In the Training review map, open **Select By Attributes** on the *Training units* layer, choose SQL, and paste the one line
   in [audit-select.txt](audit-select.txt). It selects 40 units, all still unlabelled.
2. Open the layer's attribute table and click **Show selected records**. Those 40 rows are your list.
3. For each row: select it (the map can follow with **Zoom To Selection**), inspect it, then run **Label Training Unit**.
   **Open *Advanced* and untick "Select the next unlabelled unit afterwards".** Otherwise the tool jumps to the next unit
   in the queue order, which is outside this sample.
4. Or label several at once with **Label Selected Units** only if you have looked at each of them and they really are the same.

## Score it

```powershell
training_labels.bat save
python reviews/2026-09-30/audit_sample.py score reviews/2026-09-30/audit-1 --out reviews/2026-09-30/audit-1/score.json
```

It refuses to score while any of the 40 is unlabelled. It reports how many agree, lists the disagreements, and gives the
one-sided 95% lower bound on the share of triage candidates that are right (40 of 40 agreeing gives at least 0.928; 39 of 40
gives at least 0.887). Only after that, and a recorded decision, should any triage candidate become a training label.
