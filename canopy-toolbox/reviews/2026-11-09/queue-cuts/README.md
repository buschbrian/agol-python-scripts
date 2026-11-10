# Review queue cuts (November 9, 2026)

Brian approved four cuts that need no model. None of them changes an answer, a public layer or a training label. `trim_queues.py`
worked from the page's live answers file, which held 122 more answers than the repo backup (now backed up).

| Cut | What happened | Items |
|---|---|---:|
| Tree rejects | Open items taken off the page; CFTree's exclusions stand | 32 |
| Tree sample | 30 per band for 8 m and up; open items past that taken off the page | 40 |
| Training examples | Parked with no page built, because fine-tuning stopped on October 21 | 66 |
| Poor-fit outlines | Stop signal on the page (below); nothing removed | up to 770 |

`parked-items.csv` lists the 72 items taken off the page. To undo, stop the server and copy `index.before-trim-20261109.json` over
`index.json` in the page's data folder.

**Tree rejects.** Of the 32, 30 are in `no_trunk`, where only 7 had been answered (5 not a tree, 2 unsure). The 36 of 43 "not a tree"
figure comes mostly from `no_terrain`. Neither group has a "missed tree" answer.

**Tree sample.** Band results stay valid because each band's order is a random draw (seed 20261026), and items were kept in order. 8-12 m has
59 answered and 12-20 m has 50, more than the 30 planned. In 20 m and up, none are answered and the first 30 stay. Bands now differ in
size, so any citywide rate must weight by band, as it already had to.

**Training examples.** The 66 are the `refined` (45), `original` (17) and `rare` (4) items marked `needs_brian` in
`../model-assist/results/model-example-second-read.csv`. The 78 calibration items in that file stay in the treetop calibration queue.

**Poor-fit outlines.** Group 2 of the cleanup queue runs worst first. The progress line counts consecutive OUTLINE_RIGHT answers and says
to stop at 20. Items past the stop keep their regularized outlines and stay open on the page. 20 is a judgment, not a calibrated value.

## November 10: the merged and over-roof tree queues parked

Brian approved parking both queues after the model pass on their open tall trees (see `../model-triage/README.md`).
`park_tree_queues.py` took all 600 off the page (300 merged, 300 over roof). None had an answer or a note. They are appended
to `parked-items.csv`.

**Why.** These queues were drawn by the merged and roof cues to check them. The random tree sample already did that. At 8 m and up,
merged was right 24 of 26 times and roof 4 of 4. Under 8 m, merged was right 13 of 13 and roof 3 of 3. The sample also shows that
merged crowns are the largest problem among tall trees (37 of 91), which is what a second CFTree run needs to know.

**What is lost.** Per-tree answers on these 600. Undo: stop the server and copy `index.before-park-20261110.json` over `index.json`.
