"""Only intended class edits may enter a pretrained-model comparison."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


def driver():
    path = Path(__file__).resolve().parents[1] / 'reviews/2026-09-29/dl_compare.py'
    spec = importlib.util.spec_from_file_location('dl_compare_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clone(records):
    # Structured-array copy does not promise to preserve unnamed padding bytes.
    return np.frombuffer(bytearray(records.tobytes()), dtype=records.dtype)


class PointIntegrity(unittest.TestCase):
    def setUp(self):
        self.driver = driver()
        self.driver.CHUNK = 2  # Exercise failures in later chunks too.

    def records(self, modern):
        dtype = np.dtype({'names': ['x', 'y', 'z', 'classification'],
            'formats': ['<i4', '<i4', '<i4', 'u1'],
            'offsets': [0, 4, 8, 16 if modern else 15],
            'itemsize': 34 if modern else 24})  # Include opaque Extra Bytes.
        records = np.zeros(5, dtype=dtype)
        records['x'] = np.arange(5)
        records['classification'] = [5, 6, 7, 18, 5]
        if not modern:
            records['classification'] |= 32
        return records

    def test_class_edits_preserve_packed_flags_and_all_other_bytes(self):
        for modern in (False, True):
            with self.subTest(modern=modern):
                original = self.records(modern)
                prediction = clone(original)
                prediction['classification'][[0, 1, 4]] = [0, 5, 0]
                if not modern:
                    prediction['classification'][[0, 1, 4]] |= 32
                self.driver.validate_point_edits(original, prediction, modern)
                table = self.driver.crosstab(original, prediction, None, modern)
                self.assertEqual(table, {5: {0: 2}, 6: {5: 1}, 7: {7: 1}, 18: {18: 1}})

    def test_changes_to_any_nonclassification_byte_fail(self):
        for modern in (False, True):
            original = self.records(modern)
            cls_byte = 16 if modern else 15
            for byte in range(original.dtype.itemsize):
                if byte == cls_byte:
                    continue
                with self.subTest(modern=modern, byte=byte):
                    prediction = clone(original)
                    prediction.view('u1').reshape(5, -1)[4, byte] ^= 1
                    with self.assertRaisesRegex(ValueError, 'Non-classification'):
                        self.driver.validate_point_edits(original, prediction, modern)

    def test_legacy_classification_flags_cannot_change(self):
        original = self.records(False)
        for flag in (32, 64, 128):
            with self.subTest(flag=flag):
                prediction = clone(original)
                prediction['classification'][4] ^= flag
                with self.assertRaisesRegex(ValueError, 'flags'):
                    self.driver.validate_point_edits(original, prediction, False)

    def test_excluded_noise_classes_cannot_change_inside_processed_area(self):
        for modern in (False, True):
            for index in (2, 3):
                with self.subTest(modern=modern, index=index):
                    original = self.records(modern)
                    prediction = clone(original)
                    prediction['classification'][index] = 0 if modern else 32
                    with self.assertRaisesRegex(ValueError, 'Excluded noise'):
                        self.driver.validate_point_edits(original, prediction, modern)

    def test_classifications_outside_processed_boundary_cannot_change(self):
        original = self.records(True)
        prediction = clone(original)
        prediction['classification'][4] = 0
        processed = lambda records, start, stop: records['x'][start:stop] <= 1
        with self.assertRaisesRegex(ValueError, 'outside.*boundary'):
            self.driver.validate_point_edits(original, prediction, True, processed)

    def test_reporting_extent_does_not_restrict_valid_processing_extent(self):
        original = self.records(True)
        prediction = clone(original)
        prediction['classification'][4] = 0
        self.driver.validate_point_edits(original, prediction, True)
        table = self.driver.crosstab(original, prediction,
            lambda records, start, stop: records['x'][start:stop] < 1)
        self.assertEqual(table, {5: {5: 1}})

    def test_reordering_coincident_points_with_different_returns_is_rejected(self):
        original = self.records(True)
        original['x'][:] = 0
        original.view('u1').reshape(5, -1)[:, 14] = [1, 2, 3, 4, 5]
        rows = original.view('u1').reshape(5, -1)
        prediction = np.frombuffer(rows[[4, 1, 2, 3, 0]].tobytes(), dtype=original.dtype)
        with self.assertRaisesRegex(ValueError, 'Non-classification'):
            self.driver.validate_point_edits(original, prediction, True)

    def test_point_count_and_record_layout_must_match(self):
        original = self.records(True)
        for prediction in (original[:-1], self.records(False)):
            with self.subTest(dtype=prediction.dtype, size=len(prediction)):
                with self.assertRaisesRegex(ValueError, 'count|layout'):
                    self.driver.validate_point_edits(original, prediction, True)

    def test_check_is_read_only_and_handles_empty_frames(self):
        original = self.records(True)
        prediction = clone(original)
        before = (original.tobytes(), prediction.tobytes())
        self.driver.validate_point_edits(original, prediction, True)
        self.assertEqual(before, (original.tobytes(), prediction.tobytes()))
        self.driver.validate_point_edits(original[:0], prediction[:0], True)

    def test_binary_classes_are_checked_across_the_complete_processing_area(self):
        original = self.records(True)
        prediction = clone(original)
        prediction['classification'][[0, 1, 4]] = [0, 5, 6]
        with self.assertRaisesRegex(ValueError, 'unexpected classes'):
            self.driver.validate_point_edits(original, prediction, True, target=5)


class ComparisonCommand(unittest.TestCase):
    def setUp(self):
        from canopy.run_safeguards import fingerprint
        from tests.las_fixture import write_las
        self.driver = driver()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.las'
        write_las(self.source)
        self.driver.ORIGINAL = self.source
        self.driver.ROOT = self.root
        self.driver.COPIES = {name: self.root / f'{name}.las' for name in ('building', 'tree')}
        (self.root / 'work').mkdir()
        self.model = self.root / 'model.dlpk'
        self.model.write_bytes(b'synthetic model provenance; not inference')
        self.fingerprint = fingerprint

    def prepare(self, boundary=None, corrupt=None):
        original = self.source.read_bytes()
        for job, output in self.driver.COPIES.items():
            data = bytearray(original)
            for offset in range(227, len(data), 20):
                x, y = np.frombuffer(data[offset:offset+8], dtype='<i4') / 100
                inside = boundary is None or (boundary[0] <= 500000+x <= boundary[2]
                    and boundary[1] <= 4500000+y <= boundary[3])
                if inside and data[offset+15] not in (7, 18):
                    data[offset+15] = 0
            if corrupt:
                corrupt(data)
            output.write_bytes(data)
            manifest = {'schema_version': 1, 'status': 'complete', 'job': job,
                'output_classes': [0, 6 if job == 'building' else 5], 'class_mode': 'EDIT_ALL',
                'excluded_class_codes': [7, 18], 'boundary': boundary,
                'source': self.fingerprint(self.source), 'input': self.fingerprint(self.source),
                'output': self.fingerprint(output), 'model': self.fingerprint(self.model)}
            (self.root / 'work' / f'run-{job}.json').write_text(json.dumps(manifest))

    def execute(self, extra_args=()):
        output = self.root / 'comparison.json'
        with patch('sys.argv', ['dl_compare.py', '--out', str(output), *extra_args]), patch('builtins.print'):
            try:
                self.driver.main()
                exit_code = 0
            except SystemExit as exc:
                exit_code = exc.code
        return exit_code, json.loads(output.read_text())

    def test_valid_synthetic_class_edits_can_be_reported(self):
        self.prepare()
        code, result = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'verified_inference')
        self.assertTrue(result['key_numbers'])
        self.assertEqual(self.source.read_bytes()[:4], b'LASF')

    def test_intensity_change_with_valid_fingerprints_is_rejected_without_headline(self):
        self.prepare(corrupt=lambda data: data.__setitem__(227+12, data[227+12] ^ 1))
        code, result = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(result['key_numbers'], {})
        self.assertIn('Non-classification', result['building']['error'])

    def test_change_outside_processed_boundary_is_rejected_without_headline(self):
        self.prepare([500000, 4500000, 500002, 4500002],
            corrupt=lambda data: data.__setitem__(227+6*20+15, 0))
        code, result = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(result['key_numbers'], {})
        self.assertIn('boundary', result['building']['error'])

    def test_requested_subset_does_not_redefine_the_processing_boundary(self):
        self.prepare([500000, 4500000, 500010, 4500010])
        code, result = self.execute(['--extent', '500000', '4500000', '500001', '4500001'])
        self.assertEqual(code, 0)
        self.assertEqual(result['building']['processed_extent'], [500000, 4500000, 500010, 4500010])
        self.assertEqual(result['building']['comparison_extent'], [500000, 4500000, 500001, 4500001])

    def test_different_point_format_is_rejected_even_with_same_coordinates(self):
        self.prepare(corrupt=lambda data: data.__setitem__(104, 1))
        code, result = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(result['key_numbers'], {})
        self.assertIn('format', result['building']['error'])

    def test_invalid_classes_outside_reporting_subset_are_rejected(self):
        self.prepare(corrupt=lambda data: data.__setitem__(227+6*20+15, 1))
        code, result = self.execute(['--extent', '500000', '4500000', '500001', '4500001'])
        self.assertEqual(code, 1)
        self.assertEqual(result['key_numbers'], {})
        self.assertIn('unexpected classes', result['building']['error'])

    def test_truncated_prediction_header_is_recorded_as_rejected(self):
        self.prepare(corrupt=lambda data: data.__delitem__(slice(100, None)))
        code, result = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(result['key_numbers'], {})
        self.assertIn('Point integrity rejected', result['building']['error'])


if __name__ == '__main__':
    unittest.main()
