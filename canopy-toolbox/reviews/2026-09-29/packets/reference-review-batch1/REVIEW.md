# Independent reference review

Work through each sample type in REVIEW_ORDER. Find SAMPLE_ID in the corresponding ArcGIS sample layer.
Keep SAMPLE, SAMPLE_ID, REVIEW_ORDER and UNIT_TOKEN unchanged. Edit only the five answer fields.
Use acquisition-matched imagery; turn off baseline CHM/crown overlays while answering point questions.
For crown questions, inspect the sampled outline. Keep model outputs and stratum diagnostics hidden.
Do not skip hard cases: use UNSURE and explain the ambiguity in NOTES. Leave unreviewed LABEL cells blank.
REVIEWER is required; REVIEW_DATE must be YYYY-MM-DD. Notes can contain up to 500 characters.
ROOF_IN_OUTLINE is for crowns only (YES, NO or UNSURE); it may remain blank if not assessed.
Review in the seeded order. Choosing only easy cases can bias the stratified estimates.

Point labels:

- TREE: Tree: woody crown at least 2 m tall covers the point
- ROOF_OR_BUILDING: Roof, eave, wall or other part of a building
- OTHER_STRUCTURE: Pole, wire, vehicle, fence, sign, play or other structure
- SHRUB_UNDER_2M: Vegetation under 2 m (shrub, hedge, lawn edge)
- GROUND_OR_OPEN: Ground, pavement, lawn, water; nothing above 2 m
- UNSURE: Cannot tell from the imagery

Crown labels:

- CORRECT: One tree, outline mostly right
- MERGED: Outline covers two or more trees
- SPLIT: Outline is part of a tree that has other outlines
- NOT_A_TREE: Mostly not a tree (roof, structure, shrub)
- UNSURE: Cannot tell from the imagery

[Open the existing ArcGIS review project](H:/lidar/2023-salt-lake-valley/runs/pilot-2026-09-29/validation/review/validation_review.aprx)

The worksheet is for independent answers. packet.json is the coordinator manifest.
Preview the import first; apply requires --apply and a fresh --audit-dir. Then rerun score.
