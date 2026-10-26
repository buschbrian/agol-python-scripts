# Making the footprint review queue smaller (October 23, 2026)

**Direction changed on October 26.** After answering 25 of the attached sample (13 part of the existing building, 8
separate) and leaving notes such as "redo all - lidar has correct shape", Brian decided the LiDAR outline is the truth
for whole buildings and the county footprints should be redrawn from it, not kept and patched. Everything below
assumes the county footprints as the frame and the attached pieces as things to merge into them. The LiDAR-first
outlines and their comparison with the county layer, [lidar-footprints](../../2026-10-26/lidar-footprints), replace
that frame. The pre-registered rule here has not been applied and should not be.

Brian asked to "go ahead and look through all of those four ideas as to making the review queue smaller". All four
were sized on the real data with [reduce_queue.py](reduce_queue.py) (`size.json`). The scope is the part of the review
that is mostly noise: the 3,671 LiDAR candidates within 2 m of a county building, and the 456 offset or rebuilt pairs.
The large and tall (252), detached (2,286), county no-roof (586) and new-building (208) queues are outside it.
**Unvalidated planning estimates from the 2023 LiDAR.** Nothing was applied to any data, and Brian's 31 answers are
untouched.

Time uses Brian's label-page pace: 5 s per attached candidate, 6 s per sample item, 10 s per pair or parcel, 6 s per
yes/no swap.

## Comparison
| Idea | Left for Brian | Estimated hours | Risk of a wrong merge | Needs from Brian |
|---|---|---:|---|---|
| Today | 3,671 attached + 456 pairs | 6.4 | none (he decides each) | every item |
| 1. Measure the county misalignment first ([county-alignment](../county-alignment/README.md)) | 3,671 + 456 (4 and 2 explained) | 6.4 | none | nothing; done |
| 2. Review by parcel | 3,289 parcel questions (2,632 parcels hold a single item) | about 9 | low, but each question is harder | a new, more complex question per parcel |
| 3. Settle the attached queue by sample | 300 sample + 443 that always need eyes + 456 pairs, plus any stratum that fails | 2.4 best case; +1 h per large failed stratum | bounded: 12% upper bound of separate buildings lost per passing stratum (rule A), 15% for wrong merges (rule B) | 300 answers first (about 30 min) |
| 4. LiDAR outline as the shape, county as the record | 3,434 county buildings to swap (1.12 pieces each) | 5.7 if each swap is reviewed; 0 if applied blind | high if blind: 308 of the buildings have trees over 30%+, under 80% roof, or are rebuilt or gone; eaves widen every outline | a yes/no per swap, or a validated rule |

- **1 doesn't shrink anything.** The county layer has no systematic shift (0.36 m per building, no shared neighbourhood
  shift), so realignment explains 4 candidates and 2 pairs. Its per-building result is already a fact on the page.
- **2 barely groups.** 80% of the parcels hold one item and 110 hold three or more (at most 12). Fewer questions but
  harder ones: about 9 hours against 6.4.
- **3 is the one that cuts.** If every stratum passes, 3,228 attached pieces are settled by rule from 300 answers.
  Brian then looks at the 443 that no rule may place, and at the pairs.
- **4 is a way of applying merges, not of deciding them.** A county building that keeps its ID and attributes and
  takes the LiDAR outline as its shape is the right output for every piece judged part of it. But done blind it would
  merge trees, vehicles and eaves into 3,434 buildings, and reviewed one by one it saves little.

## Recommendation
**Do 3 now, keep 1 as context, use 4 later as the output for accepted merges, and skip 2.**
1. **Answer the sample (300, about 30 minutes).** In the LiDAR candidates queue, choose Group "Sample: answer these
   first". The rule and its pass/fail test were written down before any answer, in [PROTOCOL.md](PROTOCOL.md)
   (commit ec07c36, worked examples corrected in 6cff7cf before any answer).
2. **Run `reduce_queue.py evaluate`.** For each stratum it reports whether rule A (no separate building) and rule B
   (merge into the county building) pass, with the expected number of wrong calls and its upper bound. Brian decides
   which to adopt.
3. **Look at the "Needs eyes" group (443):** pieces of 80 m² or more, and pieces whose county building is rebuilt or
   gone, has trees over 30% or more of it, or under 80% roof under any shift. Then any stratum that failed, and the
   pairs.
4. **Apply the adopted merges idea-4 style, in a derived layer:** the county building keeps its ID and attributes,
   and its outline gains the merged LiDAR pieces (or takes the regularized roof outline). The County's data is not
   edited.

### What the rule could never place
- **eyes.csv (443):** 245 pieces of 80 m² or more and 223 on a doubtful county building (25 are both). Their size or
  their neighbour makes a blanket call unsafe.
- **Any stratum that fails its test.**
- **The other queues:** the pairs, the large and tall, detached, county no-roof and new-building queues. They are real
  decisions, not noise.

## Built into the review page
In the LiDAR candidates queue, the attached part is now grouped in this order: **Sample: answer these first** (300),
**Needs eyes** (443), then the three earlier attached groups, now 2,928 items (1,442 other, 1,153 lower roof, 333
corner of a county roof). Those are the ones a passing rule would settle. The page says nothing about the rule or the
stratum. Applied with `footprint_review.bat facts` (it reads `sample.csv` and `eyes.csv` here when present).

## Files
| File | Meaning |
|---|---|
| [PROTOCOL.md](PROTOCOL.md) | the pre-registered rules, strata and decision |
| sample.csv | the 300 sample items (seed 20261023), with stratum and stratum size |
| eyes.csv | the 443 items no rule may place, with the reason |
| size.json | the figures in the comparison |
| evaluation.json | written by `evaluate` once Brian has answered |
