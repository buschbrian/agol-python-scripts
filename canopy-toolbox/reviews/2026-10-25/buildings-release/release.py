"""Release the approved October 25 hybrid; prepare is offline, apply requires --go.

Use ArcGIS Pro Python, PYTHONNOUSERSITE=1, and --audit-dir containing inspect_release.py's
before snapshots, hosted-layer.json and hosted-statistics.json. Never uploads or deletes.
"""
import argparse
import copy
import datetime
import gzip
import json
import math
from pathlib import Path
import re
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
REVIEW = HERE.parents[1] / '2026-10-23'
for folder in ('agol-styling', 'agol-apps', 'agol-metadata'):
    sys.path.insert(0, str(REVIEW / folder))
import build_definitions as styling
import make_apps as apps
import apply_metadata as metadata

IDS = {'new_layer': 'ce3617ac9b884bbcbee7c47a3e166999',
       'package': '07919e2df15647ba91ba23a0fd417083',
       'old_layer': '5082b5bd063a4a03847f2082dc3533d1',
       'scene': '5b5bdf4a63c9466fad5884039aa7357f',
       'app': '021866adf7ab40fea430d4d10fc3a934'}
PORTAL = 'https://www.arcgis.com/sharing/rest'
PROP_KEYS = ('title', 'snippet', 'description', 'tags', 'accessInformation', 'licenseInfo')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def check_statistics(layer, stats):
    expected = read(REVIEW / 'wrapup-evidence/release-audit.json')
    assert layer['layerType'] == '3DObject', layer['layerType']
    assert len(layer['fields']) == 45
    fp = stats['FP_ID']['stats']
    assert (fp['count'], fp['sum']) == (21561, 237493394)
    levels = stats['LEVEL']['stats']
    assert levels['totalValuesCount'] == 21561
    assert {r['value']: r['count'] for r in levels['mostFrequentValues']} == expected['model_counts']
    for field, value in expected['package_attribute_totals'].items():
        assert stats[field]['stats']['count'] == value['count'], field
        assert math.isclose(stats[field]['stats']['sum'], value['sum'], rel_tol=0, abs_tol=0.001), field


def prepare(audit):
    layer = read(audit / 'hosted-layer.json')
    check_statistics(layer, read(audit / 'hosted-statistics.json'))
    rendered = metadata.render('buildings3d_v2')
    assert not metadata.problems(rendered), metadata.problems(rendered)
    layer_data = styling.scene_item_data()
    scene_before = read(audit / 'before-scene.json')
    app_before = read(audit / 'before-app.json')
    scene = copy.deepcopy(scene_before['data'])
    nodes = [n for n in scene['operationalLayers'] if n.get('itemId') == IDS['old_layer']]
    assert len(nodes) == 1
    node = nodes[0]
    node.update(itemId=IDS['new_layer'], url=styling.ITEMS['buildings3d']['url'] + '/layers/0',
                title='Buildings with roof forms (three-way hybrid)',
                popupInfo=copy.deepcopy(layer_data['layers'][0]['popupInfo']))
    node.setdefault('layerDefinition', {}).setdefault('drawingInfo', {})['renderer'] = styling.scene_renderer()
    # Keep the live scene's stable layer IDs, slides, camera, terrain and unrelated layers.
    generated_scene = styling.buildings_scene(layer_data)
    scene_props = {k: generated_scene['item'][k] for k in PROP_KEYS}
    app = copy.deepcopy(app_before['data'])
    app['values']['splashContent'] = apps.splash(apps.APPS['in3d'])
    generated_app = apps.properties(apps.APPS['in3d'], app['folderId'])
    app_props = {k: generated_app[k] for k in PROP_KEYS}
    # Check popup/renderer expressions against the service schema, including inline placeholders.
    actual = {f['name'] for f in layer['fields']}
    serialized = json.dumps(layer_data)
    referenced = set(re.findall(r'\$feature\.([A-Za-z_][A-Za-z_0-9]*)', serialized))
    referenced |= set(re.findall(r'\{([A-Z][A-Z_0-9]*)\}', serialized))
    referenced |= {f['fieldName'] for f in node['popupInfo']['fieldInfos']
                   if not f['fieldName'].startswith('expression/')}
    assert referenced <= actual, referenced - actual
    documented = set(re.findall(r'^\| ([A-Za-z_][A-Za-z_0-9]*) \|',
                      (REVIEW/'agol-metadata/buildings3d_v2.md').read_text(encoding='utf-8'), re.M)) - {'Field'}
    assert documented == actual, documented ^ actual
    for props in (rendered['props'], scene_props, app_props):
        assert len(props['snippet']) <= 250
        assert 'planning estimate' in props['snippet'].lower()
    plan = {'new_layer': {'props': rendered['props'], 'data': layer_data},
            'scene': {'props': scene_props, 'data': scene},
            'app': {'props': app_props, 'data': app}}
    write(audit/'release-plan.json', plan)
    styling.write(styling.LAYERS/'buildings3d_item_data.json', layer_data)
    styling.write(styling.MAPS/'in-3d.json', {'item': {**generated_scene['item'], **scene_props}, 'data': scene})
    print('Prepared: 45 documented fields, valid popups, counts and roof totals match; live scene structure preserved.', flush=True)
    return plan


def get_json(gis, url):
    response = gis.session.get(url, params={'f':'json'})
    response.raise_for_status()
    result = response.json()
    assert 'error' not in result, result
    return result


def update(gis, item_id, props, data=None):
    item = gis.content.get(item_id)
    payload = {'f':'json', **props}
    if isinstance(payload.get('tags'), list):
        payload['tags'] = ','.join(payload['tags'])
    if data is not None:
        payload['text'] = json.dumps(data)
    response = gis.session.post(f'{PORTAL}/content/users/{item.owner}/items/{item_id}/update', data=payload)
    response.raise_for_status()
    result = response.json()
    assert result.get('success') is True, result


def anon(url):
    with urllib.request.urlopen(url + ('&' if '?' in url else '?') + 'f=json', timeout=60) as response:
        body = response.read()
    # SceneServer serves precompressed I3S resources, including to clients requesting identity encoding.
    if body.startswith(b'\x1f\x8b'):
        body = gzip.decompress(body)
    result = json.loads(body)
    assert 'error' not in result, result
    return result


def verify(gis, audit, plan):
    result = {'verified_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'items': {}}
    for key, item_id in IDS.items():
        item = gis.content.get(item_id)
        expected_access = 'private' if key in ('package', 'app') else 'public'
        assert item.access == expected_access, (key, item.access)
        result['items'][key] = {'id': item_id, 'access': item.access, 'protected': item.protected, 'url': item.url}
        if key in plan:
            assert item.get_data() == plan[key]['data'], f'{key}: item data differs'
            for prop in PROP_KEYS:
                expected, actual = plan[key]['props'][prop], item.get(prop)
                if prop in ('description', 'licenseInfo'):
                    expected, actual = metadata.text_of(expected), metadata.text_of(actual)
                assert expected == actual, (key, prop)
        if expected_access == 'public':
            assert anon(f'{PORTAL}/content/items/{item_id}')['access'] == 'public'
    for key in ('new_layer', 'package'):
        assert result['items'][key]['protected'] is True
    scene = anon(f'{PORTAL}/content/items/{IDS["scene"]}/data')
    assert scene == plan['scene']['data']
    url = result['items']['new_layer']['url'] + '/layers/0'
    layer = anon(url)
    stats = {info['name']: anon(url + '/' + info['href'].removeprefix('./'))
             for info in layer['statisticsInfo'] if info['name'] in read(audit/'hosted-statistics.json')}
    check_statistics(layer, stats)
    result['anonymous_statistics_match'] = True
    result['package_bytes'] = gis.content.get(IDS['package']).size
    assert result['package_bytes'] == 21228379
    write(audit/'release-verification.json', result)
    print(json.dumps(result), flush=True)


def apply(gis, audit, plan):
    # Refuse a concurrent/manual scene or app edit; idempotent if a previous apply reached this plan.
    for key in ('scene', 'app'):
        item = gis.content.get(IDS[key])
        before = read(audit/f'before-{key}.json')
        current = item.get_data()
        assert current in (before['data'], plan[key]['data']), f'{key} changed since snapshot'
        if current == before['data']:
            assert item.modified == before['modified'], f'{key} properties changed since snapshot'
    for key in ('new_layer', 'package'):
        assert gis.content.get(IDS[key]).protect(enable=True)
    for key in ('new_layer', 'package'):
        update(gis, IDS[key], plan['new_layer']['props'], plan['new_layer']['data'] if key == 'new_layer' else None)
    print('New layer and source package metadata saved; delete protection enabled.', flush=True)
    gis.content.get(IDS['new_layer']).sharing.sharing_level = 'EVERYONE'
    assert anon(f'{PORTAL}/content/items/{IDS["new_layer"]}')['access'] == 'public'
    assert anon(styling.ITEMS['buildings3d']['url'] + '/layers/0')['layerType'] == '3DObject'
    print('New layer is publicly readable. Updating the existing scene and app.', flush=True)
    for key in ('scene', 'app'):
        update(gis, IDS[key], plan[key]['props'], plan[key]['data'])
    verify(gis, audit, plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=('prepare','apply','verify','rollback'))
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--go', action='store_true')
    args = parser.parse_args()
    if args.step in ('apply','rollback') and not args.go:
        parser.error('Mutations require --go; prepare the plan first.')
    if args.step == 'prepare':
        prepare(args.audit_dir)
        return
    from arcgis.gis import GIS
    gis = GIS('pro')
    assert gis.users.me.username == 'GISMillcreek'
    plan = read(args.audit_dir/'release-plan.json')
    if args.step == 'apply':
        apply(gis, args.audit_dir, plan)
    elif args.step == 'verify':
        verify(gis, args.audit_dir, plan)
    else:
        for key in ('scene', 'app'):
            item = gis.content.get(IDS[key])
            assert item.get_data() == plan[key]['data'], f'{key} changed after release; review before rollback'
        for key in ('scene', 'app'):
            before = read(args.audit_dir/f'before-{key}.json')
            update(gis, IDS[key], {k: before[k] for k in PROP_KEYS}, before['data'])
            assert gis.content.get(IDS[key]).get_data() == before['data']
        print('Original scene and app restored; both layers and all packages retained.')


if __name__ == '__main__':
    main()
