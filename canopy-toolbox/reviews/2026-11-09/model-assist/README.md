# First model pass on the open LiDAR reviews (November 9, 2026)

Brian chose this on November 9: models take a blind first pass and he looks only at what they cannot settle. Nothing here
changes `footprint-review-answers.csv`, a public layer or a training label. Results are provisional.

## Footprints

`export_sheets.py` draws one sheet per item: the review page's LiDAR chip beside local NAIP 2024, with the page's outlines.
262 items are shuffled together: the 125 outlines2 items Brian has answered (the test) and the 137 open ones. The models get
the sheet and the side-panel facts without address or parcel number. They do not get the group, his answers or any rule
proposal. Esri World Imagery and UGRC Discover are not sent to a model.

**Pass rule, fixed before any result was read.** For each task with open items (reshaped, small, tangle): among test items
the model marked high confidence, it must match Brian's answer code on at least 85%, with at least 10 such items. An open item
is settled provisionally only if its task passes and the model marked it high confidence and did not answer UNSURE or
NEEDS_EDIT. Every other open item goes to Brian. The test uses his October 27 answers as committed.

**Result: no task passed, so all 137 open items stay with Brian.** Sonnet 5.5, exact answer code against his 125 answers:
reshaped 4 of 18, small 14 of 24, tangle 1 of 3, joins 9 of 40, county kept 11 of 40. It marked 3 of those 125 high
confidence, so the gate could not be met anyway. Its calls in `results/` are context only. The sheets carry 0.6 m NAIP
where Brian's page has zoomable high-resolution imagery, so this does not say how a model would do with better imagery.

**Retest with Opus 5.5 (high effort), same sheets and rule, the 125 test items only: no task passed** (`results-opus/`). Exact
matches: reshaped 6 of 18, small 12 of 24, tangle 0 of 3, joins 12 of 40, county kept 17 of 40; 47 of 125 overall against
Sonnet's 39. High-confidence calls: 12 of 23 matched, small 5 of 6 (under the 10-item minimum), reshaped 2 of 5. Opus was not
run on the 137 open items.

**Retest with GPT-6.1 Sol (high effort, Codex CLI 0.167.0, `run_sol.py`), same test: no task passed** (`results-sol/`). Exact
matches: reshaped 6 of 18, small 13 of 24, tangle 0 of 3, joins 3 of 40, county kept 14 of 40; 36 of 125 overall. High-confidence
calls: 16 of 43 matched, small 5 of 6, reshaped 6 of 14. Sol was not run on the open items.

## Examples

The 222 examples in the October 25 human queue get an independent second read from the same blind sheets. Brian sees those
where the two reads disagree or either read is UNSURE. Agreement between two models is not a human label and is not imported.

**Result:** 78 of 222 agree (second read: 4 high, 51 medium, 23 low confidence); 144 go to Brian (79 with an UNSURE, 65 real
conflicts). No human answer exists for these examples, so the agreement rate is unmeasured against a person.
