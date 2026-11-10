"""Whole-pulse thinning keeps retained records byte-identical and pulses intact."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from canopy.las_records import header

REVIEWS = Path(__file__).resolve().parents[1] / 'reviews' / '2026-09-29'
X0, Y0 = 500000.0, 4500000.0
EXTENT = [X0, Y0, X0+100, Y0+100]


def load():
    spec = importlib.util.spec_from_file_location('dl_thin', REVIEWS / 'dl_thin.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_pulses(path, pulses=4000, seed=1, fmt=6, evlr=False):
    """Pulses with 1-3 returns, distinct GPS times, varying flight lines and channels."""
    rng = np.random.default_rng(seed)
    records = []
    for pulse in range(pulses):
        count = int(rng.integers(1, 4))
        x, y = rng.uniform(0, 99.99, 2)
        channel, source = pulse % 2, 10 + pulse % 3
        gps = 1000.0 + pulse // 2 * 1e-5          # two channels fire at the same time
        for number in range(1, count+1):
            record = bytearray(30)
            struct.pack_into('<iii', record, 0, round(x*100), round(y*100), round((120 - number)*100))
            struct.pack_into('<H', record, 12, int(rng.integers(0, 65535)))
            record[14] = number | (count << 4)
            record[15] = channel << 4 | int(rng.integers(0, 2)) << 6
            record[16] = 18 if pulse % 97 == 0 else (5 if number < count else 2)
            record[17] = int(rng.integers(0, 255))
            struct.pack_into('<hH', record, 18, int(rng.integers(-100, 100)), source)
            struct.pack_into('<d', record, 22, gps)
            records.append(bytes(record))
    vlr = struct.pack('<H16sHH32s', 0, b'Fixture', 1, 4, b'opaque') + b'\x01\x02\x03\x04'
    head = bytearray(375)
    head[:4] = b'LASF'
    head[24:26] = bytes([1, 4])
    struct.pack_into('<HHHI', head, 90, 1, 2026, 375, 375 + len(vlr))
    struct.pack_into('<I', head, 100, 1)
    struct.pack_into('<BHI', head, 104, fmt, 30, 0)
    struct.pack_into('<3d', head, 131, .01, .01, .01)
    struct.pack_into('<3d', head, 155, X0, Y0, 0)
    struct.pack_into('<6d', head, 179, X0+100, X0, Y0+100, Y0, 120, 100)
    struct.pack_into('<Q', head, 247, len(records))
    if evlr:
        struct.pack_into('<QI', head, 235, 999, 1)
    with open(path, 'wb') as handle:
        handle.write(head); handle.write(vlr); handle.write(b''.join(records))
    return records


class WholePulseThinning(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = load()
        self.source = self.root / 'source.las'
        self.records = write_pulses(self.source)
        self.original = self.source.read_bytes()

    def run_thin(self, name='thin.las', density=0.3, seed=7):
        return self.module.thin(self.source, self.root / name, density, seed, EXTENT)

    def test_retained_records_are_whole_pulses_copied_byte_for_byte_in_order(self):
        record = self.run_thin()
        out = self.root / 'thin.las'
        info = header(out)
        data = out.read_bytes()
        kept = [data[info['offset']+i*30:info['offset']+(i+1)*30] for i in range(info['points'])]
        position = 0
        for item in kept:  # retained records are an ordered subsequence of the source
            position = self.records.index(item, position) + 1
        keys = {}
        for item in kept:
            key = (item[22:30], item[20:22], item[15] >> 4 & 3)
            keys.setdefault(key, []).append(item[14])
        for returns in keys.values():
            self.assertEqual(len(returns), returns[0] >> 4)
            self.assertEqual(sorted(r & 15 for r in returns), list(range(1, len(returns)+1)))
        self.assertEqual(record['thinned_pulse_structure']['complete_pulses'], len(keys))
        self.assertEqual(record['source_pulse_structure']['pulses'], 4000)
        self.assertEqual(record['thinned_points'], info['points'])
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(data[375:375+58], self.original[375:375+58])  # VLR copied

    def test_header_counts_and_bounds_describe_retained_records(self):
        self.run_thin()
        out = self.root / 'thin.las'
        info = header(out)
        data = out.read_bytes()
        raw = np.frombuffer(data, np.uint8, offset=info['offset']).reshape(-1, 30)
        by_return = struct.unpack_from('<15Q', data, 255)
        self.assertEqual(list(by_return[:3]), [int(((raw[:, 14] & 15) == n).sum()) for n in (1, 2, 3)])
        self.assertEqual(struct.unpack_from('<I', data, 107)[0], 0)
        x = raw[:, 0:4].copy().view('<i4').ravel() * .01 + X0
        self.assertAlmostEqual(info['extent'][2], x.max(), places=6)
        self.assertAlmostEqual(info['extent'][0], x.min(), places=6)

    def test_density_is_near_target_and_reproducible_with_the_seed(self):
        first = self.run_thin('a.las')
        second = self.run_thin('b.las')
        other = self.run_thin('c.las', seed=8)
        self.assertEqual(first['output']['sha256'], second['output']['sha256'])
        self.assertNotEqual(first['output']['sha256'], other['output']['sha256'])
        mean = first['thinned_block_density']['all_points_per_m2']['mean']
        self.assertAlmostEqual(mean, first['thinned_points'] / 10000, places=4)
        self.assertLess(abs(first['thinned_points'] / 10000 - 0.3), 0.08)
        self.assertEqual(first['thinned_block_density']['blocks'], 4)
        self.assertLess(first['thinned_block_density']['non_noise_points_per_m2']['mean'], mean)

    def test_existing_output_legacy_formats_and_evlrs_are_refused(self):
        (self.root / 'exists.las').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'new file'):
            self.run_thin('exists.las')
        write_pulses(self.source, pulses=10, evlr=True)
        with self.assertRaisesRegex(ValueError, 'EVLR'):
            self.run_thin('evlr.las')
        self.assertFalse((self.root / 'evlr.las').exists())

    def test_command_writes_a_record_next_to_the_output(self):
        from unittest.mock import patch
        argv = ['dl_thin.py', str(self.source), str(self.root / 'cmd.las'), '--density', '0.3',
                '--extent', *map(str, EXTENT)]
        with patch('sys.argv', argv), patch('builtins.print'):
            self.module.main()
        record = json.loads((self.root / 'cmd.thinning.json').read_text())
        self.assertEqual(record['seed'], 20260929)
        self.assertTrue(record['records_byte_identical_to_source_subset'])


if __name__ == '__main__':
    unittest.main()
