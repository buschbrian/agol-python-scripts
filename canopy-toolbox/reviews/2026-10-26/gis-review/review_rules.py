"""Conservative review cues, never presence/demolition labels or training targets."""
import math

FEET_PER_METRE = 1 / .3048


def metres_to_feet(value):
    return value * FEET_PER_METRE if value is not None and math.isfinite(value) else None


def roof_queue(level, height_status):
    flags = []
    priority = 4
    if not level:
        flags.append('NO_HYBRID_MODEL')
        priority = 1
    elif level == 'Esri LOD1.2':
        flags.append('BLOCK_FALLBACK')
        priority = 2
    elif level == 'Esri LOD2.0':
        flags.append('LOD20_FALLBACK')
        priority = 2
    for flag in ('NO_ROOF_SUPPORT', 'NO_CELL_CENTERS', 'LOW_ROOF_SUPPORT',
                 'NEGATIVE_HEIGHT', 'PARTIAL_AOI', 'GEOMETRY_REPAIRED'):
        if flag in (height_status or ''):
            flags.append(flag)
            priority = min(priority, 1 if flag in ('NO_ROOF_SUPPORT', 'NO_CELL_CENTERS') else 2)
    return priority, ';'.join(flags) or 'ROUTINE_REVIEW'


def tree_queue(edge, roof_overlap_pct, roof_center, seam_candidate):
    flags = []
    priority = 4
    if roof_center:
        flags.append('ROOF_CENTER')
        priority = 2
    if roof_overlap_pct >= 25:
        flags.append('ROOF_OVERLAP')
        priority = min(priority, 3)
    if seam_candidate:
        flags.append('SEAM_OVERLAP_CANDIDATE')
        priority = min(priority, 2)
    if edge:
        flags.append('TILE_EDGE')
        priority = min(priority, 3)
    return priority, ';'.join(flags) or 'ROUTINE_REVIEW'


STATUS = [('pending', 'Not reviewed'), ('reviewed', 'Reviewed'), ('follow_up', 'Needs follow-up')]
ROOF_DECISIONS = [
    ('uncertain', 'Uncertain / more evidence needed'), ('present_match', 'Building present; model acceptable'),
    ('present_model_issue', 'Building present; roof/model needs work'),
    ('footprint_mismatch', 'Footprint geometry or alignment needs work'),
    ('absent_2023', 'Evidence of absence at the 2023 survey'),
    ('removed_after_2023', 'Removed after the 2023 survey'),
    ('new_after_2023', 'New or changed after the 2023 survey'), ('other', 'Other (explain in notes)')]
TREE_DECISIONS = [
    ('uncertain', 'Uncertain / more evidence needed'), ('accept_model', 'Tree model acceptable'),
    ('not_tree', 'Not a tree'), ('merged_trees', 'Several trees merged into one model'),
    ('split_duplicate', 'One tree split or duplicated'), ('geometry_issue', 'Crown or trunk geometry needs work'),
    ('tree_reprocess', 'Tree present; rerun reconstruction'), ('insufficient_ground', 'Ground support needs work'),
    ('removed_after_2023', 'Removed after the 2023 survey'), ('other', 'Other (explain in notes)')]
EDIT_FIELDS = ['REVIEW_STATUS', 'REVIEW_DECISION', 'EVIDENCE_SOURCE', 'EVIDENCE_DATE', 'REVIEW_NOTES']
