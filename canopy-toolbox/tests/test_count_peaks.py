import tempfile
from pathlib import Path
import unittest

import numpy as np
from scipy import ndimage

from canopy import count_peaks, bands


def reference(array, smooth=1):
    mask = count_peaks.local_maxima(array, bands.DEFAULT_BANDS, .5, smooth)
    regions, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    result = []
    for label, box in enumerate(ndimage.find_objects(regions), 1):
        rr, cc = np.nonzero(regions[box] == label)
        rr, cc = rr + box[0].start, cc + box[1].start
        values = array[rr, cc]
        candidates = np.flatnonzero(values == values.max())
        distances = (rr[candidates] - rr.mean())**2 + (cc[candidates] - cc.mean())**2
        selected = candidates[np.argmin(distances)]
        result.append((int(rr[selected]), int(cc[selected]), float(values[selected])))
    return sorted(result)


class CountPeaks(unittest.TestCase):
    def check(self, array, smooth=1):
        for size in (7, 19, 200):
            with tempfile.TemporaryDirectory() as root:
                result = count_peaks.detect(array, bands.DEFAULT_BANDS, .5,
                                            Path(root) / 'work', smooth, size)
                self.assertEqual(sorted(result), reference(array, smooth))

    def test_plateaus_cross_many_blocks_and_diagonal_connections(self):
        array = np.zeros((75, 89), dtype='float32')
        array[10:65, 8:80] = 14
        array[0:4, 0:4] = 22
        array[68, 80] = array[69, 81] = 8
        self.check(array, 0)
        self.check(array, 1)

    def test_missing_support_and_height_band_edges(self):
        rng = np.random.default_rng(17)
        array = rng.choice([np.nan, 0, 1.9, 2, 5.99, 6, 11.99, 12, 19.99, 20, 30],
                           (73, 81)).astype('float32')
        self.check(array)

    def test_empty_and_single_cell_inputs(self):
        for array in (np.full((13, 17), np.nan, dtype='float32'),
                      np.zeros((13, 17), dtype='float32'), np.array([[8]], dtype='float32')):
            self.check(array)

    def test_existing_work_and_invalid_inputs_are_refused(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(FileExistsError):
                count_peaks.detect(np.ones((3, 3)), bands.DEFAULT_BANDS, .5, root)
            with self.assertRaises(ValueError):
                count_peaks.detect(np.ones((3, 3)), bands.DEFAULT_BANDS, .5, Path(root)/'new', block_size=0)


if __name__ == '__main__':
    unittest.main()
