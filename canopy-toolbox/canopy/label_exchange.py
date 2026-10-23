"""Blind reference worksheets and validated edit plans. No ArcPy or file writes."""
import datetime
import hashlib
import json

from .validation_metrics import POINT_LABELS, CROWN_LABELS, YES_NO

COLUMNS = ('SAMPLE', 'SAMPLE_ID', 'REVIEW_ORDER', 'UNIT_TOKEN', 'LABEL',
           'ROOF_IN_OUTLINE', 'REVIEWER', 'REVIEW_DATE', 'NOTES')
REVIEW_FIELDS = {'LABEL', 'CROWN_LABEL', 'ROOF_IN_OUTLINE', 'REVIEWER', 'REVIEW_DATE', 'NOTES'}
LABEL_FIELDS = {'treetop': 'LABEL', 'cell': 'LABEL', 'omission': 'LABEL', 'crown': 'CROWN_LABEL'}


def _hash(value):
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _index(frames):
    index = {}
    for unit in frames:
        key = (unit['sample'], unit['SAMPLE_ID'])
        if key[0] not in LABEL_FIELDS or not key[1] or key in index:
            raise ValueError('Reference sample identities must be known and unique')
        index[key] = unit
    return index


def reference_digest(frames, design):
    """Bind the worksheet to the sampling frame and geometry, independent of labels."""
    index = _index(frames)
    units = [{k: v for k, v in index[key].items() if k not in REVIEW_FIELDS}
             for key in sorted(index)]
    ordered_design = sorted(design, key=lambda row: json.dumps(row, sort_keys=True))
    return _hash({'units': units, 'design': ordered_design})


def _token(reference, unit):
    return _hash([reference, unit['sample'], unit['SAMPLE_ID'], unit['REVIEW_ORDER']])


def _text(value):
    return '' if value is None else str(value)


def _review_values(unit):
    fields = [LABEL_FIELDS[unit['sample']], 'REVIEWER', 'REVIEW_DATE', 'NOTES']
    if unit['sample'] == 'crown':
        fields.insert(1, 'ROOF_IN_OUTLINE')
    result = {field: unit.get(field) for field in fields}
    date = result['REVIEW_DATE']
    if isinstance(date, (datetime.date, datetime.datetime)):
        result['REVIEW_DATE'] = date.isoformat()
    return result


def export_rows(frames, reference, batch=1):
    """Retain the seeded review order, exposing only identity and review answers."""
    if batch not in (None, 1, 2):
        raise ValueError('Batch must be 1, 2 or all')
    index = _index(frames)
    rows = []
    for unit in sorted(index.values(), key=lambda u: (u['sample'], u['REVIEW_ORDER'], u['SAMPLE_ID'])):
        if batch is not None and unit['BATCH'] != batch:
            continue
        answers = _review_values(unit)
        rows.append(dict(zip(COLUMNS, [unit['sample'], unit['SAMPLE_ID'], unit['REVIEW_ORDER'],
            _token(reference, unit), _text(answers[LABEL_FIELDS[unit['sample']]]),
            _text(answers.get('ROOF_IN_OUTLINE')), _text(answers['REVIEWER']),
            _text(answers['REVIEW_DATE'])[:10], _text(answers['NOTES'])])))
    return rows


def plan_import(rows, frames, reference, replace_existing=False):
    """Validate the whole submitted worksheet before returning any proposed edits.

    Blank labels leave existing answers intact. Repeated identical answers preserve
    their original reviewer metadata. Replacing an answer requires explicit opt-in.
    """
    index, seen = _index(frames), set()
    result = {'changed': 0, 'blank': 0, 'unchanged': 0, 'usable': 0, 'unsure': 0, 'changes': []}
    for row in rows:
        if set(row) != set(COLUMNS):
            raise ValueError('Worksheet columns differ from the exported label schema')
        key = (row['SAMPLE'], row['SAMPLE_ID'])
        if key in seen or key not in index:
            raise ValueError(f'Duplicate or unknown sample identity: {key}')
        seen.add(key)
        unit = index[key]
        if _text(row['REVIEW_ORDER']) != _text(unit['REVIEW_ORDER']) or row['UNIT_TOKEN'] != _token(reference, unit):
            raise ValueError(f'Sample identity/frame token changed: {key}')
        label = _text(row['LABEL']).strip().upper()
        roof = _text(row['ROOF_IN_OUTLINE']).strip().upper()
        if not label:
            if roof:
                raise ValueError(f'Roof answer requires a crown outline label: {key}')
            result['blank'] += 1
            continue
        allowed = CROWN_LABELS if key[0] == 'crown' else POINT_LABELS
        if label not in allowed or (key[0] != 'crown' and roof) or (roof and roof not in YES_NO):
            raise ValueError(f'Invalid label domain for {key}')
        reviewer = _text(row['REVIEWER']).strip()
        date = _text(row['REVIEW_DATE']).strip()
        notes = _text(row['NOTES'])
        if not reviewer or len(reviewer) > 64 or len(notes) > 500:
            raise ValueError(f'Reviewer is required (max 64 chars); notes max 500 chars: {key}')
        try:
            if len(date) != 10 or datetime.date.fromisoformat(date).isoformat() != date:
                raise ValueError()
        except ValueError:
            raise ValueError(f'Review date must be a valid YYYY-MM-DD date: {key}') from None
        before = _review_values(unit)
        label_field = LABEL_FIELDS[key[0]]
        same_answer = before[label_field] == label and (key[0] != 'crown' or _text(before['ROOF_IN_OUTLINE']) == roof)
        result['usable' if label != 'UNSURE' else 'unsure'] += 1
        if same_answer and not replace_existing:
            result['unchanged'] += 1
            continue
        if before[label_field] not in (None, '') and not same_answer and not replace_existing:
            raise ValueError(f'Conflicting existing label requires explicit replacement: {key}')
        after = {label_field: label, 'REVIEWER': reviewer, 'REVIEW_DATE': date, 'NOTES': notes or None}
        if key[0] == 'crown':
            after['ROOF_IN_OUTLINE'] = roof or None
        if before == after:
            result['unchanged'] += 1
            continue
        result['changes'].append({'sample': key[0], 'sample_id': key[1], 'before': before, 'after': after})
    result['changed'] = len(result['changes'])
    return result
