import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from canopy import las_records
from tests.test_training_review import X0, Y0, write_las

REVIEWS = Path(__file__).resolve().parents[1]/"reviews"/"2026-09-30"
spec = importlib.util.spec_from_file_location("colorize_las", REVIEWS/"colorize_las.py")
cl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cl)

# a 4 x 4 pixel, 1 m NAIP whose bands are distinct: red = 10+col, green = 50+row, blue = 90, nir = 200
NAIP = np.zeros((4, 4, 4), dtype=np.uint8)
NAIP[0] = 10+np.arange(4)[None, :]
NAIP[1] = 50+np.arange(4)[:, None]
NAIP[2] = 90
NAIP[3] = 200
TOP = Y0+4.0


def source(points, path):
    write_las(path, points)


class Colorize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # relative coordinates; (0.5, 3.5) is pixel row 0, col 0; (2.5, 1.5) is row 2, col 2; (9, 9) is off the image
        self.points = [(0.5, 3.5, 100.0, 2), (2.5, 1.5, 101.0, 5), (9.0, 9.0, 102.0, 6), (1.5, 2.5, 103.0, 18)]
        self.src = self.root/"src.las"
        source(self.points, self.src)

    def tearDown(self):
        self.tmp.cleanup()

    def run_colorize(self, extent=None, name="out.las"):
        return cl.colorize(self.src, NAIP, X0, TOP, 1.0, self.root/name, extent)

    def test_colour_is_naip_times_256_and_outside_the_image_is_zero(self):
        self.run_colorize()
        data = (self.root/"out.las").read_bytes()
        info = las_records.header(self.root/"out.las")
        self.assertEqual((info["format"], info["record_length"], info["points"]), (8, 38, 4))
        rows = np.frombuffer(data[info["offset"]:], dtype=np.uint8).reshape(-1, 38)
        rgbn = rows[:, 30:].copy().view("<u2").reshape(-1, 4)
        self.assertEqual(rgbn[0].tolist(), [10*256, 50*256, 90*256, 200*256])        # row 0, col 0
        self.assertEqual(rgbn[1].tolist(), [12*256, 52*256, 90*256, 200*256])        # row 2, col 2
        self.assertEqual(rgbn[2].tolist(), [0, 0, 0, 0])                              # off the image
        self.assertLessEqual(int(rgbn.max()), 255*256)                                # Myria3D asserts this bound

    def test_classification_is_one_and_every_other_byte_is_copied(self):
        self.run_colorize()
        src_rows = np.frombuffer((self.root/"src.las").read_bytes()[las_records.header(self.src)["offset"]:],
                                 dtype=np.uint8).reshape(-1, 30)
        out_info = las_records.header(self.root/"out.las")
        out_rows = np.frombuffer((self.root/"out.las").read_bytes()[out_info["offset"]:], dtype=np.uint8).reshape(-1, 38)
        self.assertEqual(set(out_rows[:, 16].tolist()), {1})                          # the baseline classes are gone
        self.assertEqual(set(src_rows[:, 16].tolist()), {2, 5, 6, 18})
        keep = [i for i in range(30) if i != 16]
        self.assertTrue((out_rows[:, keep] == src_rows[:, keep]).all())               # position, intensity, returns, flags, time

    def test_extent_crops_points_and_bounds_and_the_header_is_consistent(self):
        record = self.run_colorize(extent=(X0, Y0, X0+3.0, Y0+4.0), name="crop.las")
        self.assertEqual(record["points"], 3)                                         # the off-image point is outside the extent
        info = las_records.header(self.root/"crop.las")
        self.assertEqual(info["points"], 3)
        head = (self.root/"crop.las").read_bytes()[:375]
        self.assertEqual(struct.unpack_from("<I", head, 107)[0], 0)                   # legacy count is zero for formats 6 to 10
        self.assertEqual(struct.unpack_from("<Q", head, 235)[0], 0)
        maxx, minx, maxy, miny, maxz, minz = struct.unpack_from("<6d", head, 179)
        self.assertAlmostEqual(maxx, X0+2.5, places=3); self.assertAlmostEqual(minx, X0+0.5, places=3)
        self.assertAlmostEqual(minz, 100.0, places=3); self.assertAlmostEqual(maxz, 103.0, places=3)
        with self.assertRaisesRegex(ValueError, "No points"):
            cl.colorize(self.src, NAIP, X0, TOP, 1.0, self.root/"none.las", (X0+100, Y0+100, X0+101, Y0+101))

    def test_refusals(self):
        self.run_colorize()
        with self.assertRaises(FileExistsError):
            self.run_colorize()
        legacy = self.root/"legacy.las"
        write_las(legacy, self.points, modern=False)
        with self.assertRaisesRegex(ValueError, "point format 6"):
            cl.colorize(legacy, NAIP, X0, TOP, 1.0, self.root/"x.las")


if __name__ == "__main__":
    unittest.main()
