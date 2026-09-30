"""Multi-file inference rows: one dataset, one tool call, per-file schema-1 manifests (mocked ArcPy)."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from canopy.run_safeguards import prediction_extent

REVIEWS = Path(__file__).resolve().parents[1] / 'reviews' / '2026-09-29'


def load_driver(name):
    spec = importlib.util.spec_from_file_location(name, REVIEWS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MultiFileRow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.driver = load_driver('dl_run')
        self.driver.MODELS = base / 'models'
        self.driver.MODELS.mkdir()
        (self.driver.MODELS / 'Tree_point_classification.dlpk').write_bytes(b'model')
        self.root = base / 'row'
        (self.root / 'tree').mkdir(parents=True)
        self.sources, self.copies = [], []
        for name in ('core', 'halo-a', 'halo-b'):
            source = base / 'prepared' / f'{name}.las'
            source.parent.mkdir(exist_ok=True)
            source.write_bytes(f'baseline {name}'.encode())
            copy = self.root / 'tree' / f'{name}.las'
            copy.write_bytes(source.read_bytes())
            self.sources.append(source)
            self.copies.append(copy)
        self.runtime = MagicMock()
        self.runtime.GetInstallInfo.return_value = {'Version': 'fixture'}
        self.runtime.GetMessages.return_value = 'fixture messages'
        self.runtime.CheckOutExtension.return_value = 'CheckedOut'

        def classify(**kwargs):  # the tool edits every member in place
            for copy in self.copies:
                copy.write_bytes(copy.read_bytes() + b' classified')
        self.classify = classify

    def argv(self, *extra, sources=None, copies=None):
        args = ['dl_run.py', 'tree', '--output-root', str(self.root), '--label', 'prospective holdout']
        for source, copy in zip(sources or self.sources, copies or self.copies):
            args += ['--source', str(source), '--copy', str(copy)]
        return args + list(extra)

    def execute(self, argv):
        with patch.dict('sys.modules', {'arcpy': self.runtime}), patch('sys.argv', argv), \
             patch.object(self.driver.site, 'ENABLE_USER_SITE', False), \
             patch.object(self.driver.subprocess, 'run', side_effect=OSError('no GPU fixture')), \
             patch('builtins.print'):
            self.driver.main()

    def test_all_files_enter_one_dataset_and_each_gets_a_verifiable_manifest(self):
        self.runtime.ddd.ClassifyPointCloudUsingTrainedModel.side_effect = self.classify
        self.execute(self.argv())
        members, lasd = self.runtime.management.CreateLasDataset.call_args.args
        self.assertEqual(members, [str(c.resolve()) for c in self.copies])
        self.assertEqual(lasd, str((self.root / 'tree' / 'tree.lasd').resolve()))
        self.runtime.ddd.ClassifyPointCloudUsingTrainedModel.assert_called_once()
        self.assertNotIn('boundary', self.runtime.ddd.ClassifyPointCloudUsingTrainedModel.call_args.kwargs)
        row = json.loads((self.root / 'work' / 'run-tree.json').read_text())
        self.assertEqual(row['status'], 'complete')
        self.assertEqual(row['data_use_label'], 'prospective holdout')
        self.assertNotIn('source', row)
        self.assertEqual(len(row['files']), 3)
        for entry, source, copy in zip(row['files'], self.sources, self.copies):
            record = json.loads(Path(entry['manifest']).read_text())
            self.assertEqual(Path(entry['manifest']).name, f'run-tree-{copy.stem}.json')
            self.assertEqual(record['status'], 'complete')
            self.assertEqual(record['data_use_label'], 'prospective holdout')
            self.assertEqual(record['row_manifest'], str((self.root / 'work' / 'run-tree.json').resolve()))
            self.assertNotIn('files', record)
            # The shared safeguard accepts each per-file manifest unchanged.
            self.assertIsNone(prediction_extent(record, 'tree', source, copy))
            self.assertEqual(source.read_bytes(), f'baseline {source.stem}'.encode())

    def test_failed_row_marks_every_file_failed_without_outputs(self):
        self.runtime.ddd.ClassifyPointCloudUsingTrainedModel.side_effect = RuntimeError('inference failed')
        with self.assertRaisesRegex(RuntimeError, 'inference failed'):
            self.execute(self.argv())
        row = json.loads((self.root / 'work' / 'run-tree.json').read_text())
        self.assertEqual(row['status'], 'failed')
        for entry in row['files']:
            record = json.loads(Path(entry['manifest']).read_text())
            self.assertEqual(record['status'], 'failed')
            self.assertNotIn('output', record)

    def test_any_stale_copy_refuses_before_any_record(self):
        self.copies[2].write_bytes(b'previous predictions')
        with self.assertRaisesRegex(ValueError, 'differs from baseline'):
            self.execute(self.argv())
        self.assertFalse((self.root / 'work' / 'run-tree.json').exists())
        self.runtime.ddd.ClassifyPointCloudUsingTrainedModel.assert_not_called()

    def test_copies_must_be_dedicated_distinct_and_paired(self):
        outside = self.root / 'elsewhere.las'
        outside.write_bytes(self.sources[0].read_bytes())
        cases = {
            'dedicated copy': self.argv(copies=[outside, *self.copies[1:]]),
            'distinct file names': self.argv(copies=[self.copies[0], self.copies[0], self.copies[2]]),
        }
        for message, argv in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.execute(argv)
        unpaired = self.argv() + ['--source', str(self.sources[0])]
        with self.assertRaisesRegex(ValueError, 'one --copy for each --source'):
            self.execute(unpaired)
        self.assertFalse((self.root / 'work' / 'run-tree.json').exists())

    def test_read_only_copy_is_refused_before_any_record_or_tool_call(self):
        import os
        import stat
        os.chmod(self.copies[0], stat.S_IREAD)
        self.addCleanup(os.chmod, self.copies[0], stat.S_IREAD | stat.S_IWRITE)
        with self.assertRaisesRegex(ValueError, 'read-only'):
            self.execute(self.argv())
        self.assertFalse((self.root / 'work' / 'run-tree.json').exists())
        self.runtime.ddd.ClassifyPointCloudUsingTrainedModel.assert_not_called()

    def test_changed_source_during_inference_fails_the_row(self):
        def classify(**kwargs):
            self.classify()
            self.sources[1].write_bytes(b'modified baseline')
        self.runtime.ddd.ClassifyPointCloudUsingTrainedModel.side_effect = classify
        with self.assertRaisesRegex(RuntimeError, 'source halo-a.las changed'):
            self.execute(self.argv())
        row = json.loads((self.root / 'work' / 'run-tree.json').read_text())
        self.assertEqual(row['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
