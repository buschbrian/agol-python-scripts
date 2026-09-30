"""Product copies restore ground, apply the declared conflict policy and never touch raw outputs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from canopy.las_records import header
from canopy.run_safeguards import fingerprint
from tests.test_dl_thin import REVIEWS, X0, Y0, write_pulses


class ProductAssembly(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        spec = importlib.util.spec_from_file_location('dl_product', REVIEWS / 'dl_product.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.baseline = self.root / 'base.las'
        write_pulses(self.baseline, pulses=300)
        info = header(self.baseline)
        data = bytearray(self.baseline.read_bytes())
        raw = np.frombuffer(data, np.uint8, offset=info['offset']).reshape(-1, 30)
        self.base = raw[:, 16].copy()
        rng = np.random.default_rng(3)
        noise = np.isin(self.base, (7, 18))
        self.tree = np.where(noise, self.base, rng.choice([0, 5], len(self.base))).astype(np.uint8)
        self.build = np.where(noise, self.base, rng.choice([0, 6], len(self.base))).astype(np.uint8)
        self.paths = {}
        for job, classes in (('tree', self.tree), ('building', self.build)):
            copy = bytearray(data)
            view = np.frombuffer(copy, np.uint8, offset=info['offset']).reshape(-1, 30)
            view[:, 16] = classes
            path = self.root / f'{job}.las'
            path.write_bytes(bytes(copy))
            manifest = {'status': 'complete', 'boundary': [X0, Y0, X0+100, Y0+100],
                        'source': fingerprint(self.baseline), 'output': fingerprint(path)}
            compare = {job: {'status': 'verified_inference', 'processed_extent': manifest['boundary']}}
            (self.root / f'{job}-run.json').write_text(json.dumps(manifest))
            (self.root / f'{job}-compare.json').write_text(json.dumps(compare))
            self.paths[job] = path

    def assemble(self, name='product.las', building=True):
        extra = (self.root / 'building-run.json', self.root / 'building-compare.json') if building else ()
        return self.module.assemble(self.baseline, self.root / 'tree-run.json', self.root / 'tree-compare.json',
                                    self.root / name, *extra)

    def test_policy_restores_ground_and_resolves_conflicts_to_tree(self):
        raw_before = {job: path.read_bytes() for job, path in self.paths.items()}
        record = self.assemble()
        out = self.root / 'product.las'
        info = header(out)
        got = np.frombuffer(out.read_bytes(), np.uint8, offset=info['offset']).reshape(-1, 30)
        noise = np.isin(self.base, (7, 18))
        ground = (self.base == 2) & ~noise
        expected = np.zeros_like(self.base)
        expected[self.build == 6] = 6
        expected[self.tree == 5] = 5
        expected[ground] = 2
        expected[noise] = self.base[noise]
        np.testing.assert_array_equal(got[:, 16], expected)
        base = np.frombuffer(self.baseline.read_bytes(), np.uint8, offset=info['offset']).reshape(-1, 30)
        np.testing.assert_array_equal(np.delete(got, 16, axis=1), np.delete(base, 16, axis=1))
        self.assertEqual(record['counts']['conflict_tree5_building6_resolved_to_tree'],
                         int(((self.tree == 5) & (self.build == 6) & ~ground & ~noise).sum()))
        self.assertEqual({job: path.read_bytes() for job, path in self.paths.items()}, raw_before)
        self.assertEqual(record['raw_outputs_before'], record['raw_outputs_after'])

    def expected(self, conflict_value):
        noise = np.isin(self.base, (7, 18))
        ground = (self.base == 2) & ~noise
        conflict = (self.tree == 5) & (self.build == 6) & ~ground & ~noise
        expected = np.zeros_like(self.base)
        expected[self.build == 6] = 6
        expected[self.tree == 5] = 5
        expected[conflict] = conflict_value
        expected[ground] = 2
        expected[noise] = self.base[noise]
        return expected, int(conflict.sum())

    def classes(self, name):
        out = self.root / name
        info = header(out)
        return np.frombuffer(out.read_bytes(), np.uint8, offset=info['offset']).reshape(-1, 30)[:, 16]

    def test_building_wins_and_conflict_class_policies(self):
        for policy, value, key in (('building-wins', 6, 'conflict_tree5_building6_resolved_to_building'),
                                   ('conflict-class', 65, 'conflict_tree5_building6_to_class_65'),
                                   ('conflict-class', 200, 'conflict_tree5_building6_to_class_200')):
            with self.subTest(policy=policy, value=value):
                name = f'{policy}-{value}.las'
                record = self.module.assemble(self.baseline, self.root / 'tree-run.json',
                                              self.root / 'tree-compare.json', self.root / name,
                                              self.root / 'building-run.json', self.root / 'building-compare.json',
                                              policy=policy, conflict_class=value)
                expected, conflicts = self.expected(value)
                self.assertGreater(conflicts, 0)
                got = self.classes(name)
                np.testing.assert_array_equal(got, expected)
                counts = record['counts']
                self.assertEqual(counts['conflict_tree5_building6'], conflicts)
                self.assertEqual(counts[key], conflicts)
                self.assertEqual(counts['tree_5'], int((got == 5).sum()))
                self.assertEqual(counts['building_6'], int((got == 6).sum()))
                self.assertEqual(counts['background_0'], int((got == 0).sum()))
                self.assertEqual(record['conflict_policy'], policy)
                self.assertEqual(record['conflict_class'], value if policy == 'conflict-class' else None)

    def test_policies_partition_the_same_points(self):
        records = {}
        for policy in ('tree-wins', 'building-wins', 'conflict-class'):
            records[policy] = self.module.assemble(
                self.baseline, self.root / 'tree-run.json', self.root / 'tree-compare.json',
                self.root / f'{policy}.las', self.root / 'building-run.json', self.root / 'building-compare.json',
                policy=policy)['counts']
        conflicts = records['tree-wins']['conflict_tree5_building6']
        self.assertEqual(records['tree-wins']['tree_5'], records['building-wins']['tree_5'] + conflicts)
        self.assertEqual(records['building-wins']['building_6'], records['tree-wins']['building_6'] + conflicts)
        self.assertEqual(records['conflict-class']['tree_5'], records['building-wins']['tree_5'])
        self.assertEqual(records['conflict-class']['building_6'], records['tree-wins']['building_6'])
        self.assertEqual(len({r['background_0'] for r in records.values()}), 1)

    def test_invalid_policy_arguments_are_refused_before_writing(self):
        building = (self.root / 'building-run.json', self.root / 'building-compare.json')
        cases = [(dict(policy='building-wins'), (), 'needs a building prediction'),
                 (dict(policy='conflict-class', conflict_class=6), building, 'user-definable'),
                 (dict(policy='conflict-class', conflict_class=256), building, 'user-definable'),
                 (dict(policy='majority'), building, 'Unknown conflict policy')]
        for kwargs, extra, message in cases:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, message):
                self.module.assemble(self.baseline, self.root / 'tree-run.json', self.root / 'tree-compare.json',
                                     self.root / 'refused.las', *extra, **kwargs)
        self.assertFalse((self.root / 'refused.las').exists())

    def test_multi_file_row_comparison_is_matched_by_manifest(self):
        manifest = self.root / 'tree-run.json'
        other = self.root / 'other-run.json'
        row = {'tree': {'status': 'verified_inference', 'files': {
            'base.las': {'status': 'verified_inference', 'inference_manifest': str(manifest),
                         'processed_extent': [X0, Y0, X0+100, Y0+100]},
            'halo.las': {'status': 'verified_inference', 'inference_manifest': str(other)}}}}
        (self.root / 'tree-compare.json').write_text(json.dumps(row))
        record = self.assemble('row-product.las', building=False)
        self.assertEqual(record['counts']['building_6'], 0)
        row['tree']['files']['base.las']['status'] = 'rejected'
        (self.root / 'tree-compare.json').write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError, 'verified binary integrity'):
            self.assemble('refused.las', building=False)
        row['tree']['files']['base.las']['status'] = 'verified_inference'
        row['tree']['status'] = 'rejected'
        (self.root / 'tree-compare.json').write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError, 'verified binary integrity'):
            self.assemble('refused.las', building=False)

    def test_tree_only_product_has_no_building_class(self):
        record = self.assemble(building=False)
        self.assertEqual(record['counts']['building_6'], 0)
        self.assertIsNone(record['building_manifest'])

    def test_unverified_or_partial_inference_is_refused(self):
        (self.root / 'tree-compare.json').write_text(json.dumps({'tree': {'status': 'rejected'}}))
        with self.assertRaisesRegex(ValueError, 'verified binary integrity'):
            self.assemble(building=False)
        manifest = json.loads((self.root / 'tree-run.json').read_text())
        manifest['boundary'] = [X0, Y0, X0+50, Y0+50]
        (self.root / 'tree-run.json').write_text(json.dumps(manifest))
        (self.root / 'tree-compare.json').write_text(json.dumps(
            {'tree': {'status': 'verified_inference', 'processed_extent': manifest['boundary']}}))
        with self.assertRaisesRegex(ValueError, 'contain every baseline point'):
            self.assemble(building=False)
        self.assertFalse((self.root / 'product.las').exists())


if __name__ == '__main__':
    unittest.main()
