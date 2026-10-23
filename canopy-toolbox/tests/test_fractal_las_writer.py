import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location(
    'fractal_las_writer', Path(__file__).resolve().parents[1] / 'reviews/2026-09-30/fractal/las_writer.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Writer(unittest.TestCase):
    def setUp(self):
        try:
            import laspy
        except ImportError:
            self.skipTest('laspy integration requires Myria3D environment')
        self.laspy = laspy
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.las'
        self.cloud = laspy.LasData(laspy.LasHeader(point_format=8, version='1.4'))
        self.cloud.x = [428000.01, 428000.02, 428000.03]
        self.cloud.y = [4504000.01, 4504000.02, 4504000.03]
        self.cloud.z = [1300.1, 1300.2, 1300.3]
        self.cloud.gps_time = [10.1, 10.2, 10.3]
        self.cloud.intensity = [100, 200, 300]
        self.cloud.classification = [1, 1, 1]
        self.cloud.withheld = [0, 1, 0]
        self.cloud.scanner_channel = [0, 1, 3]
        self.cloud.red = [256, 512, 768]
        self.cloud.write(self.source)
        self.values = np.zeros(3, dtype=[('X','f8'), ('Y','f8'), ('Z','f8'), ('GpsTime','f8'),
                                         ('PredictedClassification','u1'), ('vegetation','f8'), ('entropy','f8')])
        for a, b in [('X','x'), ('Y','y'), ('Z','z'), ('GpsTime','gps_time')]:
            self.values[a] = self.cloud[b]
        self.values['PredictedClassification'] = [5,2,6]
        self.values['vegetation'] = [.9,.1,.2]
        self.values['entropy'] = [.1,.2,.3]
        self.channels = ['PredictedClassification','vegetation','entropy']

    def test_chunked_writer_preserves_source_dimensions_and_adds_channels(self):
        before = self.source.read_bytes()
        out = self.root / 'prediction.las'
        module.write_prediction_las(self.source, self.values, out, self.channels, chunk_size=2)
        self.assertEqual(self.source.read_bytes(), before)
        result = self.laspy.read(out)
        for dim in self.cloud.point_format.dimension_names:
            np.testing.assert_array_equal(result[dim], self.cloud[dim])
        np.testing.assert_array_equal(result.PredictedClassification, [5,2,6])
        np.testing.assert_array_equal(result.vegetation, [.9,.1,.2])
        self.assertFalse(out.with_name(out.name+'.partial.las').exists())

    def test_reordered_or_changed_point_identity_is_refused(self):
        for field in ('X','Y','Z','GpsTime'):
            values = self.values.copy()
            values[field] = values[field][::-1]
            out = self.root / f'bad-{field}.las'
            with self.assertRaisesRegex(ValueError, 'point order'):
                module.write_prediction_las(self.source, values, out, self.channels)
            self.assertFalse(out.exists())

    def test_missing_overlapping_channels_and_changed_counts_are_refused(self):
        for values, channels in [(self.values[:2], self.channels), (self.values, ['missing']),
                                  (self.values, ['classification']), (self.values, ['entropy','entropy'])]:
            with self.assertRaises(ValueError):
                module.write_prediction_las(self.source, values, self.root / 'invalid.las', channels)
        self.assertFalse((self.root/'invalid.las').exists())

    def test_existing_output_or_partial_is_not_overwritten(self):
        out = self.root / 'existing.las'
        out.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):
            module.write_prediction_las(self.source, self.values, out, self.channels)
        self.assertEqual(out.read_bytes(), b'keep')
        partial = self.root / 'pending.las.partial.las'
        partial.write_bytes(b'keep partial')
        with self.assertRaises(FileExistsError):
            module.write_prediction_las(self.source, self.values, self.root/'pending.las', self.channels)


if __name__ == '__main__':
    unittest.main()
