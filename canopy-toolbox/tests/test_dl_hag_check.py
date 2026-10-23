"""A HAG baseline may differ from its absolute baseline only in Z and the declared header Z fields."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from canopy.las_records import header
from tests.test_dl_thin import REVIEWS, write_pulses


class HagCheck(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        spec = importlib.util.spec_from_file_location('dl_hag_check', REVIEWS / 'dl_hag_check.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.module.CHUNK = 7
        self.absolute = self.root / 'abs.las'
        write_pulses(self.absolute, pulses=40)
        with open(self.absolute, 'ab') as handle:
            handle.write(b'opaque trailing EVLR fixture')
        self.info = header(self.absolute)

    def hag(self, edit):
        data = bytearray(self.absolute.read_bytes())
        count = self.info['points']*self.info['record_length']
        edit(data, np.frombuffer(data, np.uint8, count=count, offset=self.info['offset']).reshape(
            -1, self.info['record_length']))
        path = self.root / 'hag.las'
        path.write_bytes(bytes(data))
        return path

    def rewrite_z(self, data, records):
        records[:, 8:12] = np.frombuffer(np.arange(len(records), dtype='<i4').tobytes(), np.uint8).reshape(-1, 4)
        struct.pack_into('<d', data, 171, 0.0)
        struct.pack_into('<2d', data, 211, 5.0, 0.0)

    def test_z_only_rewrite_is_accepted(self):
        result = self.module.check(self.absolute, self.hag(self.rewrite_z))
        self.assertEqual(result['status'], 'non_z_bytes_identical')
        self.assertEqual(result['header_z_fields']['z_offset']['hag'], 0.0)
        self.assertGreater(result['records_with_changed_z'], 0)

    def test_paired_predictions_count_agreement_by_index(self):
        def predict(data, records, classes):
            records[:, 16] = classes
        n = self.info['points']
        a_classes = np.where(np.arange(n) % 3 == 0, 5, 0).astype(np.uint8)
        h_classes = a_classes.copy()
        h_classes[:4] = [5, 5, 0, 0]
        pair = {}
        for name, classes in (('abs', a_classes), ('hag', h_classes)):
            path = self.hag(lambda data, records: predict(data, records, classes))
            pair[name] = path.rename(self.root / f'{name}-out.las')
        result = self.module.paired_predictions(pair['abs'], pair['hag'], 5)
        both = int(((a_classes == 5) & (h_classes == 5)).sum())
        self.assertEqual(result['target_both'], both)
        self.assertEqual(result['target_absolute_only'], int(((a_classes == 5) & (h_classes != 5)).sum()))
        self.assertEqual(result['target_hag_only'], int(((a_classes != 5) & (h_classes == 5)).sum()))
        self.assertFalse(result['identical_predictions'])
        same = self.module.paired_predictions(pair['abs'], pair['abs'], 5)
        self.assertTrue(same['identical_predictions'])

    def test_any_other_change_is_rejected(self):
        def classification(data, records):
            self.rewrite_z(data, records)
            records[-1, 16] ^= 1

        def x_scale(data, records):
            self.rewrite_z(data, records)
            data[131] ^= 1

        def evlr(data, records):
            self.rewrite_z(data, records)
            data[-1] ^= 1

        for name, edit, message in (('classification', classification, 'Non-Z point bytes'),
                                    ('x scale', x_scale, 'outside the Z fields'),
                                    ('trailing', evlr, 'after the point records')):
            with self.subTest(name=name):
                result = self.module.check(self.absolute, self.hag(edit))
                self.assertEqual(result['status'], 'rejected')
                self.assertIn(message, result['error'])


if __name__ == '__main__':
    unittest.main()
