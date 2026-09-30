"""Height above ground: synthetic ground and objects in legacy and modern LAS; ArcPy only in the last class."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

HAVE_NUMPY = importlib.util.find_spec("numpy") is not None
ARCPY = importlib.util.find_spec("arcpy") is not None
X0, Y0 = 500000., 4500000.
WKT = b'PROJCS["fixture"]\0'


def ground_z(x):
    """Synthetic terrain: 100 m rising 5 cm per metre eastward."""
    return 100+.05*x


def scene(seed=0):
    """(x, y, z, class, return number, return count) in local metres: ground, a low curb, a wall,
    a crown, a sub-ground noise return and ground points below their cell value."""
    import numpy as np
    rng = np.random.default_rng(seed)
    rows = []
    for x in np.arange(.1, 19.5, .7):
        for y in np.arange(.1, 19.5, .7):
            rows.append((x, y, ground_z(x)+.02, 2, 1, 1))
    rows += [(x, 5.2, ground_z(x)+.15, 1, 1, 1) for x in np.arange(2, 8, .3)]              # curb
    rows += [(10.2, y, ground_z(10.2)+h, 5, 1, 2) for y in np.arange(2, 6, .4) for h in (.5, 1.5, 2.5)]
    rows += [(15+rng.uniform(-1, 1), 15+rng.uniform(-1, 1), ground_z(15)+rng.uniform(4, 8), 5, 1, 1)
             for _ in range(40)]
    rows += [(3.3, 3.3, ground_z(3.3)-2.5, 7, 1, 1), (4.1, 4.1, ground_z(4.1)-.3, 2, 1, 1)]
    rows += [(19.99, 19.99, ground_z(19.99)+.5, 1, 1, 1), (20., 20., ground_z(20.)+.25, 1, 1, 1)]  # NE edge
    return rows


def surface(nan_cells=(), extent=(0, 0, 20, 20), cell=.5, nan_at=()):
    """Ground values at cell centres of the synthetic terrain (a stand-in for the ArcGIS DTM).
    nan_cells are (row, col); nan_at are local (x, y) whose containing cells become NoData."""
    import numpy as np
    from canopy import hag
    x0, y0, x1, y1 = extent
    cols, rows = round((x1-x0)/cell), round((y1-y0)/cell)
    centres = X0+x0+cell*(np.arange(cols)+.5)
    values = np.tile(ground_z(centres-X0), (rows, 1)).astype(np.float32)
    for r, c in nan_cells:
        values[r, c] = np.nan
    for x, y in nan_at:
        values[min(rows-1, int((y1-y)//cell)), min(cols-1, int((x-x0)//cell))] = np.nan
    return hag.GroundSurface(values, X0+x0, Y0+y1, cell, {"source": "synthetic"})


def write_las(path, rows, modern, padding=b"\0\0\0\0", evlr=b"", seed=1, scale=.01):
    """LAS 1.2 format 1 (legacy) or 1.4 format 6 with a WKT VLR, padding before the points and
    optional EVLR bytes after them; unused record bytes are random."""
    import numpy as np
    rng = np.random.default_rng(seed)
    size, fmt, length = (375, 6, 30) if modern else (227, 1, 28)
    vlr = struct.pack("<H16sHH32s", 0, b"LASF_Projection", 2112, len(WKT), b"WKT") + WKT
    start = size+len(vlr)+len(padding)
    head = bytearray(size); head[:4] = b"LASF"; head[24:26] = bytes([1, 4 if modern else 2])
    head[26:58] = b"HAG fixture".ljust(32, b"\0")
    struct.pack_into("<HHHII", head, 90, 272, 2026, size, start, 1)
    struct.pack_into("<BHI", head, 104, fmt, length, 0 if modern else len(rows))
    numbers = np.bincount([r[4] for r in rows], minlength=16)
    if modern:
        struct.pack_into("<Q", head, 247, len(rows))
        struct.pack_into("<15Q", head, 255, *[int(v) for v in numbers[1:16]])
        if evlr:
            struct.pack_into("<QI", head, 235, start+len(rows)*length, 1)
    else:
        struct.pack_into("<5I", head, 111, *[int(v) for v in numbers[1:6]])
    xyz = np.array([r[:3] for r in rows])
    struct.pack_into("<3d", head, 131, scale, scale, scale)
    struct.pack_into("<3d", head, 155, X0, Y0, 0)
    struct.pack_into("<6d", head, 179, X0+xyz[:, 0].max(), X0+xyz[:, 0].min(), Y0+xyz[:, 1].max(),
                     Y0+xyz[:, 1].min(), xyz[:, 2].max(), xyz[:, 2].min())
    with Path(path).open("wb") as handle:
        handle.write(head); handle.write(vlr); handle.write(padding)
        for x, y, z, code, number, count in rows:
            record = bytearray(rng.integers(0, 256, length, dtype=np.uint8).tobytes())
            struct.pack_into("<iii", record, 0, round(x/scale), round(y/scale), round(z/scale))
            if modern:
                record[14] = number | count << 4
                record[16] = code
            else:
                record[14] = (record[14] & 0xC0) | number | count << 3
                record[15] = (record[15] & 0xE0) | code
            handle.write(record)
        handle.write(evlr)
    return start, length


def an_evlr():
    content = b"opaque evlr payload"
    return struct.pack("<H16sHQ32s", 0, b"fixture", 7, len(content), b"test EVLR") + content


def expected_q(rows, scale=.01):
    import numpy as np
    xyz = np.array([r[:3] for r in rows])
    x, y, z = [np.round(v/scale)*scale for v in (xyz[:, 0], xyz[:, 1], xyz[:, 2])]
    g = surface().sample(x+X0, y+Y0)
    return np.round((z-g)/scale).astype(np.int64), g


@unittest.skipUnless(HAVE_NUMPY, "numpy required")
class Sampling(unittest.TestCase):
    def test_containing_cell_with_edge_cells_and_no_interpolation(self):
        import numpy as np
        s = surface(nan_cells=[(0, 0)])
        x = X0+np.array([.1, .49, .5, 19.99, 20., 20.01, -.01, .2])
        y = Y0+np.array([10, 10, 10, 10, 0., 10, 10, 19.8])
        g = s.sample(x, y)
        centres = [.25, .25, .75, 19.75, 19.75]              # (20, 0): east and south edge cell
        np.testing.assert_allclose(g[:5], [ground_z(c) for c in centres], rtol=0, atol=1e-4)
        self.assertTrue(np.isnan(g[5:]).all())               # outside, or a NoData cell: never extrapolated


@unittest.skipUnless(HAVE_NUMPY, "numpy required")
class ZCopies(unittest.TestCase):
    def test_z_becomes_hag_and_every_other_byte_is_identical_legacy_and_modern(self):
        import numpy as np
        from canopy import hag
        rows = scene()
        q, _ = expected_q(rows)
        for modern in (False, True):
            with self.subTest(modern=modern), tempfile.TemporaryDirectory() as folder:
                source, target = Path(folder)/"a.las", Path(folder)/"out"/"a.las"
                target.parent.mkdir()
                start, length = write_las(source, rows, modern, evlr=an_evlr() if modern else b"")
                before = source.read_bytes()
                row = hag.write_z(source, target, surface())
                self.assertEqual(row["status"], "written")
                self.assertEqual(before, source.read_bytes())
                after = target.read_bytes()
                self.assertEqual(len(before), len(after))
                n = len(rows)
                allowed = set(range(171, 179)) | set(range(211, 227))
                allowed |= {start+i*length+b for i in range(n) for b in range(8, 12)}
                differing = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
                self.assertTrue(differing <= allowed, sorted(differing - allowed)[:5])
                stored = np.array([struct.unpack_from("<i", after, start+i*length+8)[0] for i in range(n)])
                np.testing.assert_array_equal(stored, q)
                scale, = struct.unpack_from("<d", after, 147)
                offset, = struct.unpack_from("<d", after, 171)
                zmax, zmin = struct.unpack_from("<2d", after, 211)
                self.assertEqual((scale, offset), (.01, 0.))
                self.assertEqual((zmax, zmin), (q.max()*.01, q.min()*.01))
                self.assertLess(zmin, -2.4)                               # the noise return stays negative
                self.assertEqual(row["negative"], int((q < 0).sum()))
                self.assertEqual(row["negative_by_class"]["7"], 1)
                self.assertGreaterEqual(row["negative_by_class"]["2"], 1)
                self.assertEqual(row["below_minus_1m"], 1)
                self.assertEqual(after[-len(an_evlr()):] if modern else b"", an_evlr() if modern else b"")
                self.assertTrue(hag.verify_z(source, target, surface())["all_pass"])
                # A single changed non-Z byte fails verification.
                tampered = bytearray(after); tampered[start+length+16] ^= 1
                bad = Path(folder)/"bad.las"; bad.write_bytes(bytes(tampered))
                check = hag.verify_z(source, bad, surface())
                self.assertFalse(check["all_pass"]); self.assertEqual(check["non_z_record_bytes_differing"], 1)
                with self.assertRaises(FileExistsError):
                    hag.write_z(source, target, surface())

    def test_uncovered_points_refuse_the_file_and_are_logged(self):
        import numpy as np
        from canopy import hag
        rows = scene()
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/"a.las", Path(folder)/"a_hag.las"
            write_las(source, rows, True)
            # Cell row 29-30 / col 6 holds ground points; NoData there leaves them uncovered.
            nan = [(29, 6), (30, 6)]
            s = surface(nan_cells=nan)
            xyz = np.array([r[:3] for r in rows])
            expect = np.flatnonzero(np.isnan(s.sample(X0+np.round(xyz[:, 0]*100)/100, Y0+np.round(xyz[:, 1]*100)/100)))
            self.assertGreater(len(expect), 0)
            row = hag.write_z(source, target, s, Path(folder)/"uncovered"/"a.npz", chunk=7)
            self.assertEqual(row["status"], "refused")
            self.assertEqual(row["uncovered"], len(expect))
            self.assertFalse(target.exists())
            self.assertFalse(target.with_name(target.name+".partial").exists())
            with np.load(Path(folder)/"uncovered"/"a.npz") as log:
                np.testing.assert_array_equal(log["point_index"], expect)

    def test_chunking_does_not_change_output(self):
        from canopy import hag
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/"a.las"
            write_las(source, scene(), True)
            hag.write_z(source, Path(folder)/"one.las", surface())
            hag.write_z(source, Path(folder)/"many.las", surface(), chunk=13)
            self.assertEqual((Path(folder)/"one.las").read_bytes(), (Path(folder)/"many.las").read_bytes())


def parse_extrabytes(data):
    """Extra Bytes descriptors of a LAS byte string (independent of canopy.hag)."""
    header_size, = struct.unpack_from("<H", data, 94)
    count, = struct.unpack_from("<I", data, 100)
    at, found = header_size, []
    for _ in range(count):
        user, record, size = struct.unpack_from("<16sHH", data, at+2)
        if user.rstrip(b"\0") == b"LASF_Spec" and record == 4:
            for k in range(size//192):
                d = data[at+54+192*k: at+54+192*(k+1)]
                found.append({"type": d[2], "options": d[3], "name": d[4:36].rstrip(b"\0").decode(),
                              "no_data": struct.unpack_from("<q", d, 40)[0],
                              "scale": struct.unpack_from("<d", d, 112)[0], "offset": struct.unpack_from("<d", d, 136)[0]})
        at += 54+size
    return found, at


@unittest.skipUnless(HAVE_NUMPY, "numpy required")
class ExtraBytes(unittest.TestCase):
    def test_hag_attribute_added_with_original_records_intact_in_las_1_4(self):
        import numpy as np
        from canopy import hag
        rows = scene()
        q, _ = expected_q(rows)
        s = surface(nan_cells=[(0, 39)])      # the NE edge points become no_data
        for modern in (True,):
            with self.subTest(modern=modern), tempfile.TemporaryDirectory() as folder:
                source, target = Path(folder)/"a.las", Path(folder)/"a_eb.las"
                evlr = an_evlr() if modern else b""
                padding = b"\0\0\0\0"
                start, length = write_las(source, rows, modern, padding=padding, evlr=evlr)
                before = source.read_bytes()
                row = hag.write_extrabytes(source, target, s)
                self.assertEqual(row["status"], "written")
                self.assertEqual(row["uncovered_no_data"], 2)
                after = target.read_bytes()
                self.assertEqual(before, source.read_bytes())
                descriptors, vlr_end = parse_extrabytes(after)
                self.assertEqual(descriptors, [{"type": 6, "options": 25, "name": "HeightAboveGround",
                                                "no_data": -2**31, "scale": .01, "offset": 0.}])
                new_start, = struct.unpack_from("<I", after, 96)
                self.assertEqual(new_start, start+54+192)
                self.assertEqual(after[vlr_end:new_start], padding)
                self.assertEqual(struct.unpack_from("<H", after, 105)[0], length+4)
                self.assertEqual(struct.unpack_from("<I", after, 100)[0], 2)
                n = len(rows)
                records = np.frombuffer(after[new_start:new_start+n*(length+4)], np.uint8).reshape(n, length+4)
                original = np.frombuffer(before[start:start+n*length], np.uint8).reshape(n, length)
                np.testing.assert_array_equal(records[:, :length], original)
                values = records[:, length:].copy().view("<i4").ravel()
                np.testing.assert_array_equal(values[:-2], q[:-2])
                self.assertEqual(values[-2:].tolist(), [-2**31]*2)
                if modern:
                    evlr_at, = struct.unpack_from("<Q", after, 235)
                    self.assertEqual(evlr_at, new_start+n*(length+4))
                    self.assertEqual(after[evlr_at:], evlr)
                # header bytes outside the three layout fields (and the EVLR start) are unchanged
                fields = set(range(96, 104)) | {105, 106} | (set(range(235, 243)) if modern else set())
                size = 375 if modern else 227
                self.assertEqual([i for i in range(size) if before[i] != after[i] and i not in fields], [])
                self.assertTrue(hag.verify_extrabytes(source, target, s)["all_pass"])

    def test_legacy_versions_and_files_with_existing_extra_bytes_are_skipped(self):
        from canopy import hag
        with tempfile.TemporaryDirectory() as folder:
            write_las(Path(folder)/"legacy.las", scene(), False)
            row = hag.write_extrabytes(Path(folder)/"legacy.las", Path(folder)/"legacy_eb.las", surface())
            self.assertEqual(row["status"], "skipped")
            self.assertIn("LAS 1.4", row["reason"])
            self.assertFalse((Path(folder)/"legacy_eb.las").exists())
            source = Path(folder)/"a.las"
            write_las(source, scene(), True)
            hag.write_extrabytes(source, Path(folder)/"b.las", surface())
            row = hag.write_extrabytes(Path(folder)/"b.las", Path(folder)/"c.las", surface())
            self.assertEqual(row["status"], "skipped")
            self.assertIn("extra bytes", row["reason"])
            self.assertFalse((Path(folder)/"c.las").exists())


def prepared(folder, files, extent):
    root = Path(folder)/"prepared"
    (root/"points").mkdir(parents=True)
    for name, (rows, modern) in files.items():
        write_las(root/"points"/name, rows, modern)
    lasd = root/"prepared.lasd"; lasd.write_text("fixture")
    (root/"preparation.json").write_text(json.dumps({
        "status": "complete", "working_lasd": str(lasd), "source_id": "fixture",
        "extent": [X0+extent[0], Y0+extent[1], X0+extent[2], Y0+extent[3]]}))
    return lasd


@unittest.skipUnless(HAVE_NUMPY, "numpy required")
class Run(unittest.TestCase):
    def builder(self, nan_at=()):
        calls = []

        def ground(folder, extent, cell):
            calls.append((Path(folder), list(extent), cell))
            s = surface((), [extent[0]-X0, extent[1]-Y0, extent[2]-X0, extent[3]-Y0], cell, nan_at)
            s.record["raster"] = None
            return s
        self.calls = calls
        return ground

    def test_both_modes_manifest_roles_refusal_and_immutable_sources(self):
        from canopy import hag
        core = [r for r in scene() if 4 <= r[0] <= 16 and 4 <= r[1] <= 16]
        halo = [r for r in scene() if r[0] > 16.5]
        with tempfile.TemporaryDirectory() as folder:
            lasd = prepared(folder, {"core.las": (core, True), "halo.las": (halo, False)}, (0, 0, 20, 20))
            before = {p.name: p.read_bytes() for p in (lasd.parent/"points").iterdir()}
            out = Path(folder)/"hag"
            # NoData under a halo point (x 19.99) but not under the core.
            state = hag.run(lasd, out, self.builder(nan_at=[(19.99, 19.99)]), mode="both", label="fixture role")
            self.assertEqual(state["status"], "complete")
            manifest = json.loads((out/"manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["label"], "fixture role")
            union = hag.snap_out([X0+min(r[0] for r in core+halo), Y0+min(r[1] for r in core+halo),
                                  X0+max(r[0] for r in core+halo), Y0+max(r[1] for r in core+halo)])
            self.assertEqual(self.calls[0][1], union)                     # both files' union, snapped out
            self.assertEqual(manifest["files"]["core.las"]["role"], "core")
            self.assertEqual(manifest["files"]["halo.las"]["role"], "halo")
            self.assertEqual(manifest["totals"]["written_z"], ["core.las"])
            self.assertTrue(manifest["core_z_written"])                  # halo refusals keep "complete"
            self.assertEqual(manifest["refused_z"], ["halo.las"])
            self.assertEqual(manifest["totals"]["refused_z"], ["halo.las"])
            self.assertEqual(manifest["files"]["halo.las"]["z"]["uncovered"], 2)
            self.assertEqual(manifest["files"]["halo.las"]["extrabytes"]["status"], "skipped")   # LAS 1.2
            self.assertEqual(manifest["files"]["core.las"]["extrabytes"]["uncovered_no_data"], 0)
            self.assertEqual(manifest["totals"]["skipped_extrabytes"], ["halo.las"])
            self.assertTrue((out/"points"/"core.las").is_file())
            self.assertFalse((out/"points"/"halo.las").exists())
            self.assertTrue((out/"points-extrabytes"/"core.las").is_file())
            self.assertFalse((out/"points-extrabytes"/"halo.las").exists())
            self.assertTrue((out/"uncovered"/"halo.npz").is_file())
            self.assertTrue(manifest["files"]["core.las"]["z"]["verification"]["all_pass"])
            self.assertEqual(manifest["files"]["core.las"]["z"]["output"]["sha256"],
                             hag.digests(out/"points"/"core.las")["sha256"])
            self.assertEqual(manifest["files"]["core.las"]["source"]["md5"],
                             hag.digests(lasd.parent/"points"/"core.las")["md5"])
            self.assertTrue(manifest["sources_unchanged"]["point_files_sha256"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in (lasd.parent/"points").iterdir()})
            with self.assertRaises(FileExistsError):
                hag.run(lasd, out, self.builder())
            with self.assertRaisesRegex(ValueError, "outside the input preparation"):
                hag.run(lasd, lasd.parent/"inside", self.builder())
            with self.assertRaisesRegex(ValueError, "Mode"):
                hag.run(lasd, Path(folder)/"m", self.builder(), mode="zz")

    def test_a_refused_core_is_not_complete(self):
        from canopy import hag
        core = [r for r in scene() if 4 <= r[0] <= 16 and 4 <= r[1] <= 16]
        halo = [r for r in scene() if r[0] > 16.5]
        with tempfile.TemporaryDirectory() as folder:
            lasd = prepared(folder, {"core.las": (core, True), "halo.las": (halo, True)}, (0, 0, 20, 20))
            state = hag.run(lasd, Path(folder)/"hag", self.builder(nan_at=[(4.3, 4.3)]), mode="both")
            self.assertEqual(state["status"], "refused")
            self.assertFalse(state["core_z_written"])
            self.assertIn("core.las", state["error"])
            manifest = json.loads((Path(folder)/"hag"/"manifest.json").read_text())
            self.assertEqual(manifest["status"], "refused")
            self.assertEqual(manifest["files"]["core.las"]["extrabytes"]["status"], "written")
            self.assertGreater(manifest["files"]["core.las"]["extrabytes"]["uncovered_no_data"], 0)

    def test_extrabytes_keep_uncovered_points_as_no_data(self):
        from canopy import hag
        halo = [r for r in scene() if r[0] > 16.5]
        with tempfile.TemporaryDirectory() as folder:
            lasd = prepared(folder, {"halo.las": (halo, True)}, (16, 0, 20, 20))
            state = hag.run(lasd, Path(folder)/"hag", self.builder(nan_at=[(19.99, 19.99)]), mode="extrabytes")
            row = state["files"]["halo.las"]["extrabytes"]
            self.assertEqual((row["status"], row["uncovered_no_data"]), ("written", 2))
            self.assertEqual(state["totals"]["uncovered"], 2)
            self.assertTrue(row["verification"]["all_pass"])
            self.assertNotIn("z", state["files"]["halo.las"])

    def test_extent_selects_files_but_ground_covers_the_whole_preparation(self):
        from canopy import hag
        core = [r for r in scene() if 4 <= r[0] <= 16 and 4 <= r[1] <= 16]
        halo = [r for r in scene() if r[0] > 16.5]
        with tempfile.TemporaryDirectory() as folder:
            lasd = prepared(folder, {"core.las": (core, True), "halo.las": (halo, True)}, (0, 0, 20, 20))
            state = hag.run(lasd, Path(folder)/"hag", self.builder(), extent=[X0+5, Y0+5, X0+6, Y0+6])
            self.assertEqual(list(state["files"]), ["core.las"])
            union = [min(r[0] for r in core+halo), min(r[1] for r in core+halo)]
            ground_extent = self.calls[0][1]
            self.assertLessEqual(ground_extent[0], X0+union[0]); self.assertLessEqual(ground_extent[1], Y0+union[1])
            self.assertGreaterEqual(ground_extent[2], X0+20.)
            self.assertEqual([v % .5 for v in ground_extent], [0.]*4)

    def test_exactly_one_core_even_when_extents_nest(self):
        from canopy import hag
        headers = [{"extent": [-4, -4, 24, 24]}, {"extent": [2, 2, 18, 18]}, {"extent": [18.5, 0, 24, 20]}]
        self.assertEqual(hag.core_index(headers, {"extent": [-4, -4, 24, 24]}), 1)
        self.assertIsNone(hag.core_index(headers, {"extent": [30, 30, 40, 40]}))
        self.assertIsNone(hag.core_index(headers, {}))

    def test_cli_rejects_unknown_mode(self):
        from canopy.__main__ import main
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            main(["hag", "in.lasd", "out", "--mode", "bad"])


@unittest.skipUnless(ARCPY and HAVE_NUMPY, "ArcGIS Pro Python required")
class ArcGISGround(unittest.TestCase):
    def test_cli_builds_the_pipeline_dtm_and_writes_verified_copies(self):
        import arcpy
        import numpy as np
        from canopy.__main__ import main
        # ArcGIS leaves NoData in some edge cells of its TIN, as on real tiles, so the core sits
        # inside a ground-only halo ring, as a prepared tile sits inside its 50 m halo.
        grid = [(x, y) for x in np.arange(-4, 24.01, .5) for y in np.arange(-4, 24.01, .5)]
        core = [(x, y, 100., 2, 1, 1) for x, y in grid if 2 <= x <= 18 and 2 <= y <= 18]
        core += [(10.1, 10.1, 103., 5, 1, 1), (5.3, 7.7, 100.5, 1, 1, 1)]
        ring = [(x, y, 100., 2, 1, 1) for x, y in grid if not (2 <= x <= 18 and 2 <= y <= 18)]
        with tempfile.TemporaryDirectory() as folder:
            lasd = prepared(folder, {"a.las": (core, True), "ring.las": (ring, True)}, (-4, -4, 24, 24))
            lasd.unlink()
            arcpy.management.CreateLasDataset([str(p) for p in sorted((lasd.parent/"points").glob("*.las"))],
                                              str(lasd), spatial_reference=arcpy.SpatialReference(26912))
            out = Path(folder)/"hag"
            with contextlib.redirect_stdout(io.StringIO()):
                main(["hag", str(lasd), str(out), "--mode", "both", "--epsg", "26912"])
            manifest = json.loads((out/"manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["ground"]["raster_spatial_reference"], 26912)
            self.assertEqual(manifest["ground"]["extent"], [X0-4, Y0-4, X0+24, Y0+24])
            self.assertTrue(manifest["ground"]["read_only"])
            self.assertEqual(manifest["files"]["a.las"]["role"], "core")
            self.assertTrue(manifest["files"]["a.las"]["z"]["verification"]["all_pass"])
            self.assertTrue(manifest["files"]["a.las"]["extrabytes"]["verification"]["all_pass"])
            self.assertEqual(manifest["files"]["ring.las"]["role"], "halo")   # its extent nests the core's
            ring_z = manifest["files"]["ring.las"]["z"]
            self.assertEqual(ring_z["status"] == "refused", ring_z["uncovered"] > 0)
            data = (out/"points"/"a.las").read_bytes()
            start, = struct.unpack_from("<I", data, 96)
            z = np.frombuffer(data[start:], np.uint8).reshape(-1, 30)[:, 8:12].copy().view("<i4").ravel()*.01
            np.testing.assert_allclose(z[-2:], [3., .5], atol=.011)
            np.testing.assert_allclose(z[:-2], 0, atol=.011)
            with self.assertRaisesRegex(ValueError, "EPSG:6341"):
                main(["hag", str(lasd), str(Path(folder)/"other")])
            arcpy.management.ClearWorkspaceCache()


if __name__ == "__main__":
    unittest.main()
