"""Export separate assistant assessments; never import labels or write to source packets."""
import argparse
from collections import Counter
import csv
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import shutil

LABELS = {'TREE', 'BUILDING_ROOF', 'WALL', 'WIRE', 'POLE', 'OTHER_STRUCTURE',
          'SHRUB_LOW_VEG', 'GROUND', 'VEHICLE', 'WATER', 'MIXED', 'UNSURE'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(source, output):
    inventory = json.loads((source / 'inventory.json').read_text())
    files = [source / 'assessments.json', *sorted((source / 'batches').glob('*.json'))]
    assessments = [row for path in files for row in json.loads(path.read_text())]
    units = {row['number']: row for row in inventory['units']}
    numbers = [row['number'] for row in assessments]
    if len(numbers) != len(set(numbers)) or set(numbers) != set(units):
        raise ValueError('Assessments must cover every inventory example exactly once')
    if len(units) != 470 or len({(u['packet'], u['UNIT_ID']) for u in units.values()}) != 470:
        raise ValueError('Expected the frozen 470-example inventory with unique packet IDs')
    protected = {}
    for packet, baseline in inventory['protected'].items():
        answer = Path(baseline['answer_path'])
        folder = Path(next(u['folder'] for u in units.values() if u['packet'] == packet))
        current = dict(answer_sha256=digest(answer), units_sha256=digest(folder / 'units.json'))
        if any(current[key] != baseline[key] for key in current):
            raise ValueError(f'{packet}: original answers or units changed; reconcile before export')
        protected[packet] = {**baseline, 'verified_unchanged': True}
    rows = []
    for assessment in sorted(assessments, key=lambda r: r['number']):
        unit = units[assessment['number']]
        if assessment['label'] not in LABELS or assessment['confidence'] not in {'high', 'medium', 'low'}:
            raise ValueError(f'Invalid assessment: {assessment}')
        if not assessment['note'].strip():
            raise ValueError('Every assessment needs an evidence note')
        number = assessment['number']
        needs_review = assessment['confidence'] != 'high' or assessment['label'] in {'UNSURE', 'MIXED'}
        rows.append(dict(number=number, packet=unit['packet'], unit_id=unit['UNIT_ID'],
            unit_token=unit['UNIT_TOKEN'], assistant_label=assessment['label'],
            assistant_confidence=assessment['confidence'], human_review_required=needs_review,
            evidence_note=assessment['note'], reviewer='CODEX_ASSISTANT', review_local_date='2026-10-25',
            target_rule='highest object in red 1 m radius column' if unit['packet'] == 'calibration'
                        else 'all returns in red patch and selected height interval',
            evidence_sheet=f'review-examples/sheets/sheet_{(number-1)//4+1:03d}.png',
            source_packet=unit['folder']))
    output.mkdir(parents=True, exist_ok=True)
    sheets = output / 'review-examples/sheets'
    sheets.mkdir(parents=True, exist_ok=True)
    for index in range(1, 119):
        name = f'sheet_{index:03d}.png'
        shutil.copy2(source / 'sheets' / name, sheets / name)
    def save_csv(name, selected):
        with (output / name).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(selected)
    save_csv('lidar-assistant-assessments.csv', rows)
    queue = [r for r in rows if r['human_review_required']]
    save_csv('lidar-human-review-queue.csv', queue)
    manifest = dict(review_local_date='2026-10-25', exported_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        reviewer='CODEX_ASSISTANT', evidence='blind point patches, orthogonal profiles, NAIP 2024 context',
        prediction_flags_read=False, human_answers_modified=False, training_imported=False,
        calibration_scored=False, reference_data_modified=False, total=len(rows),
        packet_counts=dict(Counter(r['packet'] for r in rows)),
        confidence_counts=dict(Counter(r['assistant_confidence'] for r in rows)),
        label_counts=dict(Counter(r['assistant_label'] for r in rows)), human_review_queue=len(queue),
        protected=protected, assessment_files={p.name: digest(p) for p in files},
        inventory_sha256=digest(source / 'inventory.json'),
        output_sha256={name: digest(output / name) for name in
            ['lidar-assistant-assessments.csv', 'lidar-human-review-queue.csv']},
        limitations=['Assistant judgments are provisional, not human or field reference labels.',
            'Confidence is a qualitative judgment, not a calibrated probability.',
            'NAIP 2024 is later than the lidar and cannot establish same-date object identity.',
            'Small objects and mixed training patches need human review; no official accuracy score is computed.'])
    (output / 'lidar-assistant-review-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    escape = html.escape
    table = []
    for row in rows:
        css = ' class="review"' if row['human_review_required'] else ''
        table.append(f'<tr{css}><td>{row["number"]}</td><td>{escape(row["packet"])}</td>'
            f'<td><a href="{row["evidence_sheet"]}">{escape(row["unit_id"])}</a></td>'
            f'<td>{escape(row["assistant_label"])}</td><td>{row["assistant_confidence"]}</td>'
            f'<td>{escape(row["evidence_note"])}</td></tr>')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>LiDAR assistant review</title>
<style>body{font:16px/1.55 system-ui,sans-serif;color:#203c38;max-width:1300px;margin:2rem auto;padding:0 1.5rem}h1{line-height:1.2}a{color:#08675d}table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{text-align:left;vertical-align:top;padding:.6rem;border-bottom:1px solid #ccd8d5}th{background:#e6efeb}.review{background:#fff5dc}.notice{padding:1rem;background:#e6efeb;border-radius:8px}caption{text-align:left;margin:1rem 0}td:nth-child(4){white-space:nowrap}@media print{body{max-width:none}tr{break-inside:avoid}}</style>
<h1>LiDAR review examples</h1><p>October 25, 2026 · Assistant assessments</p>
<p class="notice"><b>470 unanswered examples inspected.</b> Existing human answers and source packets are unchanged. These are separate provisional assistant assessments, not human reference labels, training imports, or an official calibration score.</p>
<p>257 high confidence · 158 provisional (medium) · 55 unsure (low). The human-review queue contains QUEUE examples: every medium/low assessment and every mixed patch. Confidence is qualitative, not a measured probability.</p>
<p><a href="lidar-assistant-assessments.csv">All assessments (CSV)</a> · <a href="lidar-human-review-queue.csv">Human-review queue (CSV)</a> · <a href="lidar-assistant-review-manifest.json">Provenance and checksums</a> · <a href="lidar-wrapup.html">LiDAR wrap-up</a></p>
<p>Coverage: 4 rare-class, 109 refined, 47 original and 310 calibration examples. Each ID links to a sheet with the red target in plan, two perpendicular point profiles and imagery. Training examples ask about all points in the red patch and height interval; calibration asks for the highest object within the red 1 m column. Ground beneath an object does not make a calibration answer mixed. Roof equipment counts with the building roof.</p>
<p>The point plots retain source meters for precise review; public app measurements and model downloads offer feet. NAIP 2024 is later than the lidar, so imagery supplies context, not same-date truth. Model predictions and triage flags were not used. The 55 unsure answers remain unresolved. The earlier ambiguous audit example Q2-0010 also remains unresolved; no independent accuracy result is claimed.</p>
<table><caption>Amber rows need human review. All assessments remain subject to correction.</caption><thead><tr><th>No.</th><th>Packet</th><th>Example / evidence</th><th>Assistant class</th><th>Confidence</th><th>Evidence note</th></tr></thead><tbody>ROWS</tbody></table></html>'''
    (output / 'lidar-assistant-review.html').write_text(page.replace('QUEUE', str(len(queue))).replace('ROWS', '\n'.join(table)), encoding='utf8')
    print(json.dumps({k: manifest[k] for k in ['total', 'packet_counts', 'confidence_counts', 'human_review_queue']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    export(args.source, args.output)
