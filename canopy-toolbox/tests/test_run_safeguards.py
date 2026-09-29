"""Content provenance, boundary and failed-pilot recovery checks."""
import json
from pathlib import Path
import tempfile
import unittest

from canopy import run_safeguards as guards


class Safeguards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.original, self.output, self.model = [self.root / name for name in ('source.las', 'copy.las', 'model.dlpk')]
        self.original.write_bytes(b'baseline')
        self.output.write_bytes(b'predictions')
        self.model.write_bytes(b'model')
        self.manifest = {"schema_version": 1, "status": "complete", "job": "tree",
            "class_mode": "EDIT_ALL", "output_classes": [0, 5], "excluded_class_codes": [7, 18],
            "boundary": [0, 0, 10, 10], "source": guards.fingerprint(self.original),
            "input": guards.fingerprint(self.original), "output": guards.fingerprint(self.output),
            "model": guards.fingerprint(self.model)}

    def test_no_success_manifest_rejects_untouched_and_failed_copies(self):
        for manifest in ({}, {**self.manifest, 'status': 'failed'}):
            with self.assertRaises(ValueError):
                guards.prediction_extent(manifest, 'tree', self.original, self.output)

    def test_processed_boundary_is_used_automatically(self):
        self.assertEqual(guards.prediction_extent(self.manifest, 'tree', self.original, self.output), [0, 0, 10, 10])
        self.assertEqual(guards.prediction_extent(self.manifest, 'tree', self.original, self.output, [1, 1, 5, 5]), [1, 1, 5, 5])
        with self.assertRaises(ValueError):
            guards.prediction_extent(self.manifest, 'tree', self.original, self.output, [-1, 0, 5, 5])

    def test_changed_source_output_or_model_is_rejected(self):
        for path in (self.original, self.output, self.model):
            before = path.read_bytes()
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                guards.prediction_extent(self.manifest, 'tree', self.original, self.output)
            path.write_bytes(before)

    def test_wrong_job_semantics_or_initial_copy_is_rejected(self):
        for override in ({'job': 'building'}, {'output_classes': [5]}, {'class_mode': 'EDIT_UNCLASSIFIED'},
                         {'excluded_class_codes': []}, {'input': guards.fingerprint(self.output)}):
            with self.assertRaises(ValueError):
                guards.prediction_extent({**self.manifest, **override}, 'tree', self.original, self.output)

    def test_invalid_extent_is_rejected(self):
        for extent in ([0, 0, 0, 1], [0, 0, 1], [0, 0, float('nan'), 1]):
            with self.assertRaises(ValueError):
                guards.valid_extent(extent)

    def test_preparation_folder_is_not_proof_of_success(self):
        folder = self.root / 'prepared'
        self.assertFalse(guards.completed_preparation(folder))
        folder.mkdir()
        with self.assertRaises(ValueError):
            guards.completed_preparation(folder)
        lasd = folder / 'prepared.lasd'
        lasd.write_bytes(b'lasd')
        (folder / 'points').mkdir()
        (folder / 'points' / 'tile.las').write_bytes(b'points')
        manifest = folder / 'preparation.json'
        manifest.write_text(json.dumps({'status': 'failed', 'working_lasd': str(lasd)}))
        with self.assertRaises(ValueError):
            guards.completed_preparation(folder)
        manifest.write_text(json.dumps({'status': 'complete', 'working_lasd': str(lasd)}))
        self.assertTrue(guards.completed_preparation(folder))
        lasd.unlink()
        with self.assertRaises(ValueError):
            guards.completed_preparation(folder)

    def test_existing_run_is_resumed_through_signature_checks(self):
        folder = self.root / 'run'
        self.assertEqual(guards.run_resume_args(folder), [])
        folder.mkdir()
        with self.assertRaises(ValueError):
            guards.run_resume_args(folder)
        for status in ('complete', 'failed', 'running'):
            (folder / 'run.json').write_text(json.dumps({'status': status, 'signature': 'known'}))
            self.assertEqual(guards.run_resume_args(folder), ['--resume'])


if __name__ == '__main__':
    unittest.main()
