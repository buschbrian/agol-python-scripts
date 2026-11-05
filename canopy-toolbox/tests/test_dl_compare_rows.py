"""Multi-file rows: each file is gated against its own baseline; totals only when all pass."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from canopy.run_safeguards import fingerprint
from tests.las_fixture import write_las
from tests.test_dl_comparison import driver


class RowComparison(unittest.TestCase):
    def setUp(self):
        self.driver = driver()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'tree').mkdir()
        (self.root / 'work').mkdir()
        self.model = self.root / 'model.dlpk'
        self.model.write_bytes(b'synthetic model provenance; not inference')
        self.sources = []
        for name, origin in (('core', (500000, 4500000)), ('halo', (500011, 4500000))):
            source = self.root / f'{name}.las'
            write_las(source, origin=origin)
            self.sources.append(source)

    def prepare(self, status='complete', corrupt=None, label='prospective holdout'):
        files = []
        for source in self.sources:
            data = bytearray(source.read_bytes())
            for offset in range(227, len(data), 20):
                if data[offset+15] not in (7, 18):
                    data[offset+15] = 5 if data[offset+15] == 5 else 0
            if corrupt and source.stem == 'halo':
                corrupt(data)
            output = self.root / 'tree' / source.name
            output.write_bytes(data)
            manifest = self.root / 'work' / f'run-tree-{source.stem}.json'
            record = {'schema_version': 1, 'status': status, 'job': 'tree', 'output_classes': [0, 5],
                      'class_mode': 'EDIT_ALL', 'excluded_class_codes': [7, 18], 'boundary': None,
                      'source': fingerprint(source), 'input': fingerprint(source), 'output': fingerprint(output),
                      'model': fingerprint(self.model), 'data_use_label': label}
            manifest.write_text(json.dumps(record))
            files.append({'source': record['source'], 'input': record['input'], 'output': record['output'],
                          'manifest': str(manifest)})
        row = {'schema_version': 1, 'status': status, 'job': 'tree', 'boundary': None, 'files': files,
               'model': fingerprint(self.model), 'data_use_label': label}
        (self.root / 'work' / 'run-tree.json').write_text(json.dumps(row))

    def execute(self):
        out = self.root / 'comparison.json'
        argv = ['dl_compare.py', '--row-manifest', f"tree={self.root / 'work' / 'run-tree.json'}", '--out', str(out)]
        with patch('sys.argv', argv), patch('builtins.print'):
            try:
                self.driver.main()
                code = 0
            except SystemExit as exc:
                code = exc.code
        return code, json.loads(out.read_text())

    def test_each_file_is_reported_and_totals_are_their_sum(self):
        self.prepare()
        code, result = self.execute()
        self.assertEqual(code, 0)
        tree = result['tree']
        self.assertEqual(tree['status'], 'verified_inference')
        self.assertEqual(set(tree['files']), {'core.las', 'halo.las'})
        self.assertEqual(tree['data_use_label'], 'prospective holdout')
        for name, entry in tree['files'].items():
            self.assertEqual(entry['status'], 'verified_inference')
            self.assertEqual(entry['original'], str(self.root / name))
            self.assertEqual(entry['data_use_label'], 'prospective holdout')
        per_file = [e['crosstab_our_class_by_prediction'] for e in tree['files'].values()]
        for cls, preds in tree['crosstab_our_class_by_prediction'].items():
            for pred, count in preds.items():
                self.assertEqual(count, sum(t.get(cls, {}).get(pred, 0) for t in per_file))
        self.assertEqual(tree['points'], sum(e['points'] for e in tree['files'].values()))
        self.assertEqual(result['key_numbers']['our_5_called_background_by_tree_model']['background'], 0)

    def test_one_corrupted_file_rejects_the_row_without_a_headline(self):
        self.prepare(corrupt=lambda data: data.__setitem__(227+12, data[227+12] ^ 1))
        code, result = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(result['key_numbers'], {})
        tree = result['tree']
        self.assertEqual(tree['status'], 'rejected')
        self.assertIn('halo.las', tree['error'])
        self.assertEqual(tree['files']['core.las']['status'], 'verified_inference')
        self.assertIn('Non-classification', tree['files']['halo.las']['error'])
        self.assertNotIn('crosstab_our_class_by_prediction', tree)

    def test_incomplete_row_is_not_model_evidence(self):
        self.prepare(status='failed')
        code, result = self.execute()
        self.assertEqual(code, 1)
        self.assertIn('did not complete', result['tree']['error'])
        self.assertEqual(result['tree']['files'], {})


if __name__ == '__main__':
    unittest.main()
