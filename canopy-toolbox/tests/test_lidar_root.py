import os
import unittest
from pathlib import PureWindowsPath
from unittest import mock

from canopy import lidar_root, run_safeguards


class LidarRootTests(unittest.TestCase):
    def test_unset_keeps_the_conventional_root_and_leaves_paths_alone(self):
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop(lidar_root.ENV, None)
            self.assertEqual(str(lidar_root.lidar_root()), r"H:\lidar")
            for path in (r"H:\lidar\a\b.las", r"D:\lidar\a\b.las", r"C:\other\b.las"):
                self.assertEqual(str(lidar_root.live(path)), path)

    def test_set_translates_recorded_paths_from_any_drive(self):
        with mock.patch.dict(os.environ, {lidar_root.ENV: r"D:\lidar"}):
            self.assertEqual(str(lidar_root.lidar_root()), r"D:\lidar")
            for recorded in (r"H:\lidar\runs\a.las", r"h:/lidar/runs/a.las", r"D:\lidar\runs\a.las"):
                self.assertEqual(PureWindowsPath(lidar_root.live(recorded)), PureWindowsPath(r"D:\lidar\runs\a.las"))

    def test_set_does_not_touch_paths_outside_a_lidar_folder(self):
        with mock.patch.dict(os.environ, {lidar_root.ENV: r"D:\lidar"}):
            for other in (r"C:\data\a.las", r"H:\lidarchive\a.las", r"H:\x\lidar\a.las"):
                self.assertEqual(str(lidar_root.live(other)), other)

    def test_fingerprint_verifies_a_manifest_recorded_under_another_root(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "lidar"
            root.mkdir()
            data = root / "file.las"
            data.write_bytes(b"points")
            recorded = dict(run_safeguards.fingerprint(data), path=r"H:\lidar\file.las")
            with mock.patch.dict(os.environ, {lidar_root.ENV: str(root)}):
                run_safeguards.verify_fingerprint(recorded, r"H:\lidar\file.las")
                run_safeguards.verify_fingerprint(recorded, data)
            os.environ.pop(lidar_root.ENV, None)
            with self.assertRaises((ValueError, OSError)):
                run_safeguards.verify_fingerprint(recorded, data)


if __name__ == "__main__":
    unittest.main()
