"""Prepare, apply and verify display/context updates. Snapshots are mandatory; no sharing or service edits."""
import argparse
import copy
import datetime
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
REVIEW = HERE.parents[1] / '2026-10-23'
for folder in ('agol-styling', 'agol-apps'):
    sys.path.insert(0, str(REVIEW / folder))
import build_definitions as style
import make_apps as apps
from reader_context import context

PORTAL = 'https://www.arcgis.com/sharing/rest'
MAPS = {'buildings_scene': 'in3d', 'buildings_map': 'buildings2d', 'canopy_map': 'canopy',
        'terrain_map': 'terrain', 'terrain_scene': 'terrain'}
APP_KEYS = {'buildings_app': 'in3d', 'canopy_app': 'canopy', 'terrain_app': 'terrain'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def nodes(layers):
    for node in layers:
        yield node
        yield from nodes(node.get('layers', []))


def prepare(audit):
    before = {p.stem[7:]: read(p) for p in audit.glob('before-*.json')}
    generated = style.web_maps(style.feature_item_data())
    templates = {'buildings_map': generated['buildings'], 'canopy_map': generated['tree-canopy'],
                 'terrain_map': generated['terrain-and-slope'],
                 'buildings_scene': style.buildings_scene(style.scene_item_data()),
                 'terrain_scene': style.terrain_scene()}
    plan = {}
    for key, old in before.items():
        data = copy.deepcopy(old['data'])
        props = copy.deepcopy(old['props'])
        if key in APP_KEYS:
            spec = apps.APPS[APP_KEYS[key]]
            target = apps.properties(spec, data['folderId'])
            # Preserve existing controls except the explicitly requested context/units and terrain profile.
            for name in ('splashContent', 'splashTitle', 'detailsContent', 'info', 'detailsOpenAtStart',
                         'units', 'measureLinearUnit', 'measureAreaUnit', 'elevationProfile',
                         'elevationProfileUnits', 'elevationProfileOpenAtStart', 'mapA11yDesc'):
                if name in target['text']['values']:
                    data['values'][name] = target['text']['values'][name]
            props = {name: target[name] for name in props}
        elif key in MAPS:
            templates_by_id = {n['id']: n for n in nodes(templates[key]['data']['operationalLayers'])}
            for node in nodes(data['operationalLayers']):
                template = templates_by_id.get(node['id'])
                if template is None:
                    continue
                node['title'] = template['title']
                if 'popupInfo' in template:
                    node['popupInfo'] = copy.deepcopy(template['popupInfo'])
                if 'featureCollection' in template:
                    node['featureCollection'] = copy.deepcopy(template['featureCollection'])
                if 'layerDefinition' in template:
                    renderer = template['layerDefinition'].get('drawingInfo', {}).get('renderer')
                    if renderer:
                        node.setdefault('layerDefinition', {}).setdefault('drawingInfo', {})['renderer'] = copy.deepcopy(renderer)
            props['description'] = templates[key]['item']['description']
            for name in ('initialState', 'presentation', 'spatialReference', 'ground', 'heightModelInfo', 'bookmarks'):
                assert data.get(name) == old['data'].get(name), (key, name)
        elif key in ('buildings_layer', 'features'):
            fresh = style.scene_item_data() if key == 'buildings_layer' else style.feature_item_data()
            for layer in data['layers']:
                template = next(n for n in fresh['layers'] if n['id'] == layer['id'])
                layer['popupInfo'] = copy.deepcopy(template['popupInfo'])
                layer.setdefault('layerDefinition', {}).setdefault('drawingInfo', {})['renderer'] = copy.deepcopy(
                    template['layerDefinition']['drawingInfo']['renderer'])
            if key == 'buildings_layer':
                props['description'] += '<h3>Feet-first display and download</h3>' + context('in3d')
            else:
                props['description'] += '<p>Building pop-ups display feet and square feet. Original metric fields '
                props['description'] += 'and the coordinate reference remain unchanged. Canopy-zone areas remain in acres.</p>'
        else:
            raise ValueError(key)
        assert len(props['snippet']) <= 250
        plan[key] = dict(id=old['id'], before_modified=old['modified'], access=old['access'], props=props, data=data)
    fields = {f['name'] for f in read(HERE.parent/'buildings-release/evidence/hosted-layer.json')['fields']}
    popup = plan['buildings_layer']['data']['layers'][0]['popupInfo']
    references = set(re.findall(r'\$feature\.([A-Za-z_][A-Za-z_0-9]*)', json.dumps(popup)))
    assert references <= fields, references - fields
    assert set(plan) == set(MAPS) | set(APP_KEYS) | {'features', 'buildings_layer'}
    write(audit/'plan.json', plan)
    print('Prepared 10 item updates; source fields valid; cameras, slides, coordinates and terrain preserved.')
    return plan


def verify(gis, audit, plan):
    results = {}
    for key, expected in plan.items():
        item = gis.content.get(expected['id'])
        data = item.get_data()
        assert item.access == expected['access'], (key, 'sharing changed')
        assert data == expected['data'], (key, 'settings mismatch')
        for name, value in expected['props'].items():
            actual = item.get(name)
            assert (set(actual or []) == set(value) if name == 'tags' else actual == value), (key, name)
        results[key] = dict(id=item.id, access=item.access, modified=item.modified, data_verified=True,
                            context_verified=True, url=item.url)
    write(audit/'verification.json', dict(verified_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), items=results))
    print('Verified all 10 item contents, context and unchanged sharing.')


def apply(gis, audit, plan):
    # Check all items before sending the first update: stop if somebody else edited after the snapshots.
    for key, expected in plan.items():
        item = gis.content.get(expected['id'])
        assert item.modified == expected['before_modified'], (key, 'changed since snapshot')
    applied = []
    for key, expected in plan.items():
        item = gis.content.get(expected['id'])
        props = copy.deepcopy(expected['props'])
        props['tags'] = ','.join(props['tags'])
        response = gis.session.post(f'{PORTAL}/content/users/{item.owner}/items/{item.id}/update',
            data={'f': 'json', **props, 'text': json.dumps(expected['data'])})
        response.raise_for_status()
        assert response.json().get('success') is True, (key, response.json())
        applied.append(key)
        write(audit/'applied.json', applied)
        print('Updated', key, flush=True)
    verify(gis, audit, plan)


def revise(gis, audit):
    """Update only changes to the previously verified plan, without resnapshotting the rollback baseline."""
    old = read(audit/'plan.json')
    verify(gis, audit, old)
    write(audit/'plan-before-revision.json', old)
    write(audit/'verification-before-revision.json', read(audit/'verification.json'))
    plan = prepare(audit)
    for key, expected in plan.items():
        if expected == old[key]:
            continue
        item = gis.content.get(expected['id'])
        props = copy.deepcopy(expected['props'])
        props['tags'] = ','.join(props['tags'])
        response = gis.session.post(f'{PORTAL}/content/users/{item.owner}/items/{item.id}/update',
            data={'f':'json', **props, 'text':json.dumps(expected['data'])})
        response.raise_for_status()
        assert response.json().get('success') is True, (key,response.json())
        print('Revised',key,flush=True)
    verify(gis,audit,plan)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('step', choices=['prepare', 'apply', 'verify', 'revise'])
    p.add_argument('--audit-dir', type=Path, required=True)
    p.add_argument('--go', action='store_true')
    a = p.parse_args()
    if a.step == 'prepare':
        prepare(a.audit_dir)
    else:
        from arcgis.gis import GIS
        gis = GIS('pro')
        plan = read(a.audit_dir/'plan.json')
        if a.step in ('apply','revise'):
            if not a.go:
                raise SystemExit('Apply requires --go')
            if a.step == 'apply':
                apply(gis, a.audit_dir, plan)
            else:
                revise(gis, a.audit_dir)
        else:
            verify(gis, a.audit_dir, plan)
