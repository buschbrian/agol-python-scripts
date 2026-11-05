# Remaining review examples — October 25, 2026

Brian clarified that “unfinished slices” meant remaining review examples, not unfinished city
classification. The blind assistant review covers every initially unanswered example: **470 total**,
comprising 4 rare, 109 refined, 47 original and 310 calibration examples.

Assessments are separate provisional assistant judgments: 257 high confidence, 158 medium and 55
unsure/low. Confidence is qualitative, not a measured probability. A 222-example human-review queue
includes all medium/low assessments and all mixed patches. No original human answer was overwritten,
no labels were restored into training, and no calibration or reference-data score was computed.

Only blind unit metadata, source point patches and NAIP 2024 chips were used. Predictions, suspect
flags and sample strata were not consulted. Review sheets show the red target in plan and two
perpendicular profiles, with later imagery as context. Calibration asks for the highest object in the
1 m red column; ground below that object is not a mixed answer. The three training packets instead ask
about every return in their selected red patch and height interval. Roof equipment counts with roofs.

The export verifies that all 470 packet/ID pairs are unique and covered exactly once, and compares
the original four answer files and four unit files with their pre-review SHA-256 hashes. All eight
were unchanged. The earlier ambiguous audit example Q2-0010 remains unresolved; this review does not
complete an official independent accuracy assessment. The point plots retain source meters for review;
public app measurements and model download attributes offer feet.

`export_review.py SOURCE_DIRECTORY OUTPUT_DIRECTORY` validates the frozen inventory and assessments,
then writes the all-assessments CSV, human-review queue, provenance manifest and HTML table linked to
118 visual evidence sheets. CSV fields deliberately use `assistant_label` and `assistant_confidence`;
these are not drop-in human-label restore files. Human acceptance/correction remains a separate step.

Inputs and assessment batches are in this chat's `work/review-examples`. Deliverables are in
`C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\outputs`:
`lidar-assistant-review.html`, `lidar-assistant-assessments.csv`, `lidar-human-review-queue.csv`,
`lidar-assistant-review-manifest.json` and `review-examples/sheets/`.
Generated labels, point/imagery files and datasets stay outside Git. The bounded provenance manifest
in `evidence/` records the verified counts and hashes.
