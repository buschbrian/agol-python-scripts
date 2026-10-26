# Sample protocol for the attached candidates (pre-registered October 23, 2026)

Written and committed **before Brian answers any item of the sample**. The rule below stays a proposal until the sample
is answered and `reduce_queue.py evaluate` reports. Brian decides whether to adopt it; nothing is applied to any data
by this protocol. **Unvalidated planning estimates from the 2023 LiDAR.**

## What is tested
The 3,671 LiDAR candidates within 2 m of a county building (the groups "against a county building (other)", "lower roof
against a county building" and "corner or edge of a county roof"). Two proposed rules, for each stratum on its own:

- **Rule A (no separate building):** the stratum's pieces are not added as separate buildings. They become part of the
  neighbouring county building or are dropped. A wrong call is a piece Brian would ACCEPT as a separate building.
- **Rule B (merge into the county building):** the stratum's pieces merge into the neighbouring county building's
  outline. A wrong call is any answer other than PART_OF_EXISTING (ACCEPT, VEHICLE, REJECT). It is stricter than A.

## Never settled by rule (always reviewed one by one)
- **Pieces of 80 m² or more.**
- **Pieces whose county building can't be trusted to merge into:** REBUILT_OR_GONE in the alignment study, trees over
  30% or more of it, or under 80% roof under any shift.

Together these are the "needs eyes" group (eyes.csv). Also outside the rule: the offset or rebuilt pairs, the large
and tall and detached candidates, the county footprints with no 2023 roof, and the possible new buildings. Any stratum
that fails stays in front of Brian too.

## Strata and sample (seed 20261023)
| Stratum | Candidates in it | Sample |
|---|---:|---:|
| S1 corner of a county roof (under 15 m²) | 383 | 50 |
| S2 lower roof, under 20 m² | 646 | 50 |
| S3 lower roof, 20-40 m² | 459 | 40 |
| S4 other, under 20 m² | 601 | 50 |
| S5 other, 20-40 m² | 731 | 50 |
| S6 lower or other, 40-80 m² | 408 | 60 |
| **Settled by rule if every stratum passes** | **3,228** | **300** |
| Needs eyes (80 m² or more: 245; risky county building: 223; 25 both) | 443 | — |

Simple random sample within each stratum, drawn once by `reduce_queue.py sample` into sample.csv. The sample items
come first in the attached part of the queue (group "Sample: answer these first"). The page shows nothing about the
rule or the stratum, only the usual facts and guess.

## Decision (per stratum, once every sample item in it is answered)
UNSURE answers are left out of n.
- **Rule A passes** when the Wilson 95% upper bound of the ACCEPT share is at most 12%. With 50 answers that allows
  at most 1 ACCEPT; with 40, none; with 60, at most 2.
- **Rule B passes** when the Wilson 95% upper bound of the share that isn't PART_OF_EXISTING is at most 15%. With 50
  answers that allows at most 2; with 40, at most 1; with 60, at most 3.
- (Correction, made before any answer: the first version of this file said 40 answers allow 1 ACCEPT. Checked with
  `reduce_queue.wilson_upper`; the thresholds are unchanged.)
- **Expected error if adopted:** the stratum's size times the observed share, reported with the size times the upper
  bound.
- **A failed rule falls back to review:** that stratum is reviewed one by one.
- **Thresholds stay fixed.** They are not changed after seeing the answers. A different rule would need a new sample.

## Changes to what the page shows (after pre-registration)
- October 23: a "USA Structures (FEMA, 2010-2020 imagery)" fact was added to every item
  ([usa-structures](../usa-structures/README.md)). It was added before any sample answer was given. The strata,
  sample and thresholds are unchanged. The extra fact can only make Brian's answers better informed; it does not
  change what the rule tests.
