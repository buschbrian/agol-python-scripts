import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location(
    "fractal_repeat", Path(__file__).resolve().parents[1] / "reviews/2026-09-30/fractal/repeat.py")
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)


class Votes(unittest.TestCase):
    def test_majorities_unanimity_and_three_way_tie(self):
        majority, share, tie, strict = fr.votes([[5, 2, 1], [5, 2, 5], [6, 2, 6]])
        np.testing.assert_array_equal(majority, [5, 2, 0])
        np.testing.assert_allclose(share, [2 / 3, 1, 1 / 3])
        np.testing.assert_array_equal(tie, [False, False, True])
        np.testing.assert_array_equal(strict, [True, True, False])

    def test_plurality_is_not_strict_majority(self):
        majority, share, tie, strict = fr.votes([[5, 5], [5, 5], [6, 6], [1, 6], [2, 1]])
        np.testing.assert_array_equal(majority, [5, 0])
        np.testing.assert_allclose(share, [0.4, 0.4])
        np.testing.assert_array_equal(tie, [False, True])
        self.assertFalse(strict.any())

    def test_invalid_votes_refused(self):
        for invalid in ([[1], [2]], [[0], [2], [2]], [[1.5], [2], [2]]):
            with self.assertRaises(ValueError):
                fr.votes(invalid)


class Consensus(unittest.TestCase):
    def setUp(self):
        try:
            import laspy
        except ImportError:
            self.skipTest("laspy integration requires Myria3D environment")
        self.laspy = laspy
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        las = laspy.LasData(laspy.LasHeader(point_format=8, version="1.4"))
        las.x = [428000.01, 428000.02, 428000.03]
        las.y = [4504000.01, 4504000.02, 4504000.03]
        las.z = [1300.1, 1300.2, 1300.3]
        las.intensity = [100, 200, 300]
        las.classification = [1, 1, 1]
        self.source = self.root / "source.las"
        las.write(self.source)
        self.predictions = []
        for index, codes in enumerate(([5, 2, 1], [5, 2, 5], [6, 2, 6])):
            copy = laspy.read(self.source)
            copy.add_extra_dim(laspy.ExtraBytesParams(name="PredictedClassification", type=np.uint8))
            copy.PredictedClassification = codes
            path = self.root / f"prediction-{index}.las"
            copy.write(path)
            self.predictions.append(path)

    def test_chunked_consensus_preserves_input_and_reports_agreement(self):
        before = fr.sha256(self.source)
        out = self.root / "consensus.las"
        result = fr.consensus(self.source, self.predictions, out, chunk_size=2)
        self.assertEqual(fr.sha256(self.source), before)
        self.assertEqual((result["points"], result["tie_points"], result["unanimous_points"]), (3, 1, 1))
        read = self.laspy.read(out)
        np.testing.assert_array_equal(read.MajorityClassification, [5, 2, 0])
        np.testing.assert_array_equal(read.intensity, [100, 200, 300])
        with self.assertRaises(FileExistsError):
            fr.consensus(self.source, self.predictions, out)

    def test_reordered_points_rejected(self):
        copy = self.laspy.read(self.predictions[0])
        copy.intensity = [300, 200, 100]
        copy.write(self.predictions[0])
        with self.assertRaisesRegex(ValueError, "source dimension intensity"):
            fr.consensus(self.source, self.predictions, self.root / "bad.las")
        self.assertFalse((self.root / "bad.las").exists())

    def test_missing_predictions_and_changed_count_rejected(self):
        copy = self.laspy.read(self.source)
        copy.write(self.predictions[0])
        with self.assertRaisesRegex(ValueError, "Missing PredictedClassification"):
            fr.consensus(self.source, self.predictions, self.root / "missing.las")
        copy.points = copy.points[:2]
        copy.write(self.predictions[0])
        with self.assertRaisesRegex(ValueError, "point count"):
            fr.consensus(self.source, self.predictions, self.root / "short.las")


if __name__ == "__main__":
    unittest.main()
