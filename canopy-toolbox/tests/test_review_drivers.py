"""Driver failure manifests and safe dataset construction using synthetic input."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch


REVIEWS = Path(__file__).resolve().parents[1] / 'reviews' / '2026-09-29'


def load_driver(name):
    spec = importlib.util.spec_from_file_location(name, REVIEWS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InferenceDriver(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.driver = load_driver('dl_run')
        self.driver.ROOT = self.root / 'dl'
        self.driver.MODELS = self.root / 'models'
        self.driver.SOURCE = self.root / 'source.las'
        self.driver.SOURCE.write_bytes(b'synthetic baseline')
        (self.driver.ROOT / 'tree').mkdir(parents=True)
        self.driver.MODELS.mkdir()
        self.copy = self.driver.ROOT / 'tree' / '12TVL2804.las'
        self.copy.write_bytes(self.driver.SOURCE.read_bytes())
        (self.driver.MODELS / 'Tree_point_classification.dlpk').write_bytes(b'model')
        self.runtime = MagicMock()
        self.runtime.GetInstallInfo.return_value = {'Version': 'fixture'}
        self.runtime.GetMessages.return_value = 'fixture messages'
        self.runtime.CheckOutExtension.return_value = 'CheckedOut'

    def execute(self):
        with patch.dict('sys.modules', {'arcpy': self.runtime}), patch('sys.argv', ['dl_run.py', 'tree']), \
             patch.object(self.driver.subprocess, 'run', side_effect=OSError('no GPU fixture')), patch('builtins.print'):
            self.driver.main()

    def manifest(self):
        return json.loads((self.driver.ROOT / 'work' / 'run-tree.json').read_text())

    def test_tool_failure_records_failed_not_completed_inference(self):
        self.runtime.ddd.ClassifyPointCloudUsingTrainedModel.side_effect = RuntimeError('inference failed')
        with self.assertRaisesRegex(RuntimeError, 'inference failed'):
            self.execute()
        record = self.manifest()
        self.assertEqual(record['status'], 'failed')
        self.assertNotIn('output', record)
        self.assertEqual(self.driver.SOURCE.read_bytes(), b'synthetic baseline')
        self.runtime.CheckInExtension.assert_called_once_with('3D')

    def test_stale_lasd_is_recreated_from_only_the_dedicated_copy(self):
        self.copy.with_suffix('.lasd').write_bytes(b'stale dataset')
        self.execute()
        args = self.runtime.management.CreateLasDataset.call_args.args
        self.assertEqual(args, (str(self.copy.resolve()), str(self.copy.resolve().with_suffix('.lasd'))))
        self.assertEqual(self.manifest()['status'], 'complete')

    def test_reused_classified_copy_cannot_invalidate_previous_success(self):
        self.execute()
        old = (self.driver.ROOT / 'work' / 'run-tree.json').read_bytes()
        self.copy.write_bytes(b'previous predictions')
        with self.assertRaisesRegex(ValueError, 'differs from baseline'):
            self.execute()
        self.assertEqual((self.driver.ROOT / 'work' / 'run-tree.json').read_bytes(), old)

    def test_setup_failure_also_records_failed_attempt(self):
        self.runtime.management.CreateLasDataset.side_effect = RuntimeError('dataset failed')
        with self.assertRaisesRegex(RuntimeError, 'dataset failed'):
            self.execute()
        self.assertEqual(self.manifest()['status'], 'failed')
        self.runtime.ddd.ClassifyPointCloudUsingTrainedModel.assert_not_called()


    def test_custom_density_and_hag_inputs_are_recorded_without_real_inference(self):
        source=self.root/'thin.las';source.write_bytes(b'thinned fixture')
        root=self.root/'experiment';copy=root/'building'/'thin.las';copy.parent.mkdir(parents=True);copy.write_bytes(source.read_bytes())
        height=self.root/'height.tif';height.write_bytes(b'ground fixture')
        (self.driver.MODELS/'building_point_classification.dlpk').write_bytes(b'building model')
        runtime=self.runtime
        runtime.ddd.ClassifyPointCloudUsingTrainedModel.side_effect=RuntimeError('mock stop')
        argv=['dl_run.py','building','--source',str(source),'--copy',str(copy),'--output-root',str(root),'--reference-height',str(height)]
        with patch.dict('sys.modules',{'arcpy':runtime}),patch('sys.argv',argv),patch('builtins.print'):
            with self.assertRaisesRegex(RuntimeError,'mock stop'):self.driver.main()
        manifest=json.loads((root/'work'/'run-building.json').read_text())
        self.assertEqual(manifest['source']['path'],str(source.resolve()))
        self.assertEqual(manifest['reference_height']['path'],str(height.resolve()))
        self.assertEqual(runtime.ddd.ClassifyPointCloudUsingTrainedModel.call_args.kwargs['reference_height'],str(height.resolve()))
        self.assertEqual(manifest['status'],'failed')


class Imports(unittest.TestCase):
    def test_buildings_import_performs_no_data_processing(self):
        with patch('subprocess.Popen', side_effect=AssertionError('must not run on import')):
            module = load_driver('buildings_driver')
        self.assertTrue(callable(module.main))

    def test_pilot_import_performs_no_data_processing(self):
        with patch('subprocess.Popen', side_effect=AssertionError('must not run on import')):
            module = load_driver('pilot_driver')
        self.assertTrue(callable(module.main))
        self.assertEqual(module.INVENTORY, module.ROOT / 'las-inventory.json')


if __name__ == '__main__':
    unittest.main()
