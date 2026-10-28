"""Shape gate: synthetic shapes, exact blocking, and byte-preserving LAS copies; no ArcPy except the last class."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

HAVE_SCIPY = importlib.util.find_spec("numpy") is not None and importlib.util.find_spec("scipy") is not None
ARCPY = importlib.util.find_spec("arcpy") is not None


def groups_of(xyz, single=None, building=None, **kwargs):
    import numpy as np
    from canopy import shape_gate as sg
    xyz = np.asarray(xyz, dtype=float)
    single = np.ones(len(xyz), bool) if single is None else single
    building = np.zeros(len(xyz), bool) if building is None else building
    result = sg.evaluate(xyz, single, building, np.ones(len(xyz), bool), **kwargs)
    return result, sg.select(result, single)


def names(result, mask=None):
    from collections import Counter
    from canopy import shape_gate as sg
    group = result["group"] if mask is None else result["group"][mask]
    return Counter(sg.GROUPS[g] for g in group)


def scenes(seed=0):
    """Synthetic objects in metres: wall, wire, pole, tree crown, clipped hedge, flat roof corner."""
    import numpy as np
    rng = np.random.default_rng(seed)
    x, z = [a.ravel() for a in np.meshgrid(np.arange(0, 10, .25), np.arange(0, 5, .25))]
    wall = np.column_stack([x+rng.uniform(-.05, .05, x.size), rng.normal(0, .01, x.size),
                            2+z+rng.uniform(-.05, .05, x.size)])
    wire = np.column_stack([np.arange(0, 30, .3)+rng.uniform(-.03, .03, 100), rng.normal(0, .02, 100),
                            8+rng.normal(0, .02, 100)])
    height = np.arange(0, 8, .1)
    angle = rng.uniform(0, np.pi, height.size)
    pole = np.column_stack([.12*np.cos(angle), .12*np.sin(angle), height])
    direction = rng.normal(size=(2000, 3)); direction /= np.linalg.norm(direction, axis=1)[:, None]
    crown = direction*(3*rng.uniform(0, 1, 2000)**(1/3))[:, None]+[0, 0, 8]
    along = np.arange(0, 10, .2)
    top = np.column_stack([a.ravel() for a in np.meshgrid(along, np.arange(-.5, .5, .2))])
    top = np.column_stack([top, np.full(len(top), 1.8)])
    side = np.column_stack([a.ravel() for a in np.meshgrid(along, np.arange(.3, 1.8, .2))])
    left = np.column_stack([side[:, 0], np.full(len(side), -.5), side[:, 1]])
    hedge = np.vstack([top, left, left*[1, -1, 1]])+rng.normal(0, .03, (len(top)+2*len(left), 3))
    grid = np.arange(0, 10, .25)
    rx, ry = [a.ravel() for a in np.meshgrid(grid, grid)]
    roof = np.column_stack([rx, ry, np.full(rx.size, 6.)])
    face = np.column_stack([a.ravel() for a in np.meshgrid(grid, np.arange(.5, 6, .5))])
    walls = np.vstack([np.column_stack([face[:, 0], np.full(len(face), -.05), face[:, 1]]),
                       np.column_stack([np.full(len(face), -.05), face[:, 0], face[:, 1]])])
    building = np.vstack([roof, walls])+rng.normal(0, .01, (len(roof)+len(walls), 3))
    return {"wall": wall, "wire": wire, "pole": pole, "crown": crown, "hedge": (hedge, len(top)),
            "building": (building, len(roof))}


@unittest.skipUnless(HAVE_SCIPY, "numpy and scipy required")
class Shapes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = scenes()

    def test_vertical_wall_is_wall_like_and_selected(self):
        result, chosen = groups_of(self.scene["wall"])
        counts = names(result)
        self.assertGreaterEqual(counts["wall_like"], .9*len(self.scene["wall"]), counts)
        self.assertEqual(set(counts), {"wall_like", "mixed"})   # rim points mix wall and edge
        self.assertTrue((chosen == (result["group"] == 1)).all())
        # PDAL's unary verticality sits at the diagnostic's 0.7 gate for this isotropic wall.
        import numpy as np
        self.assertAlmostEqual(float(np.median(result["pdal_verticality"])), .707, delta=.02)

    def test_horizontal_wire_and_vertical_pole_are_split_by_principal_axis(self):
        wire, chosen = groups_of(self.scene["wire"])
        self.assertEqual(names(wire), {"wire": 100})
        self.assertTrue(chosen.all())
        pole, chosen = groups_of(self.scene["pole"])
        self.assertEqual(names(pole), {"pole": 80})
        self.assertTrue(chosen.all())

    def test_sloped_line_is_linear_review_only(self):
        import numpy as np
        t = np.arange(0, 12, .2)
        rake = np.column_stack([t, np.zeros_like(t), 3+t*.7])  # 35 degrees, e.g. a roof rake or guy wire
        result, chosen = groups_of(rake)
        self.assertEqual(names(result), {"linear": len(t)})
        self.assertFalse(chosen.any())

    def test_tree_crown_is_scattered_or_mixed_and_never_selected(self):
        import numpy as np
        crown = self.scene["crown"]
        result, chosen = groups_of(crown)
        self.assertEqual(set(names(result)), {"scattered", "mixed"})
        self.assertFalse(chosen.any())
        self.assertTrue((result["irregular_share"] == 1).all())
        # A crown with 15% single returns fails the return test as well.
        single = np.random.default_rng(1).uniform(size=len(crown)) < .15
        self.assertFalse(groups_of(crown, single)[1].any())

    def test_clipped_hedge_sides_are_a_known_wall_confusion(self):
        import numpy as np
        hedge, top = self.scene["hedge"]
        result, chosen = groups_of(hedge)
        sides = np.arange(len(hedge)) >= top
        self.assertGreater(names(result, sides)["wall_like"], .6*sides.sum())
        self.assertEqual(set(names(result, ~sides)), {"roof_like", "mixed"})
        # Honest outcome of the prespecified rule: a single-return clipped hedge loses most of its
        # sides. Only returns penetrating the hedge protect it.
        self.assertGreater(chosen[sides].mean(), .5)
        self.assertFalse(chosen[~sides].any())
        penetrating = np.random.default_rng(2).uniform(size=len(hedge)) < .5
        self.assertFalse(groups_of(hedge, penetrating)[1][sides & ~penetrating].any())

    def test_flat_roof_and_its_corner_are_never_selected(self):
        import numpy as np
        building, roof = self.scene["building"]
        result, chosen = groups_of(building)
        on_roof = np.arange(len(building)) < roof
        self.assertEqual(set(names(result, on_roof)), {"roof_like", "mixed"})
        self.assertGreater(names(result, on_roof)["roof_like"], .85*roof)
        self.assertFalse(chosen[on_roof].any())
        corner = int(np.argmin(np.linalg.norm(building-[0, 0, 6], axis=1)))
        self.assertEqual(names(result, [corner]), {"mixed": 1})
        # Facade points of the same building are wall-like and selected: class 1, not 6.
        self.assertGreater(chosen[~on_roof].mean(), .6)

    def test_sparse_points_and_nearest_building(self):
        import numpy as np
        wire = self.scene["wire"]
        isolated = np.array([[100., 100, 5], [100.5, 100, 5]])
        xyz = np.vstack([wire, isolated, [[15, 0, 9.5]]])
        building = np.zeros(len(xyz), bool); building[-1] = True
        result, chosen = groups_of(xyz, building=building)
        self.assertEqual(names(result, [100, 101]), {"sparse": 2})
        self.assertEqual(result["neighbors"][100], 2)
        self.assertFalse(chosen[100:102].any())
        near = np.linalg.norm(wire-[15, 0, 9.5], axis=1)
        self.assertTrue(np.allclose(result["nearest_building_m"][:100], np.where(near < 5, near, np.inf)))

    def test_blocks_match_a_single_pass(self):
        import numpy as np
        rng = np.random.default_rng(5)
        parts = [np.column_stack([rng.uniform(0, 30, 3000), rng.uniform(0, 30, 3000), rng.uniform(0, 1, 3000)]),
                 np.column_stack([rng.uniform(0, 30, 400), np.full(400, 12.)+rng.normal(0, .02, 400),
                                  rng.uniform(1, 6, 400)]),
                 np.column_stack([rng.uniform(0, 30, 200), rng.normal(20, .02, 200), rng.normal(7, .02, 200)])]
        xyz = np.vstack(parts)
        single = rng.uniform(size=len(xyz)) < .7
        building = rng.uniform(size=len(xyz)) < .05
        candidate = rng.uniform(size=len(xyz)) < .8
        from canopy import shape_gate as sg
        one = sg.evaluate(xyz, single, building, candidate, radius=2., block=1000)
        many = sg.evaluate(xyz, single, building, candidate, radius=2., block=3.5, chunk=77)
        for key in one:
            np.testing.assert_array_equal(one[key], many[key], err_msg=key)
        self.assertGreater(len(set(one["group"].tolist())), 3)

    def test_min_wall_height_is_checked(self):
        from canopy import shape_gate as sg
        for bad in (-.1, float("nan"), float("inf")):
            with self.assertRaisesRegex(ValueError, "min_wall_height"):
                sg.check_parameters(dict(sg.DEFAULTS, min_wall_height=bad))
        sg.check_parameters(dict(sg.DEFAULTS, min_wall_height=0.))

    def test_parameters_are_checked(self):
        from canopy import shape_gate as sg
        sg.check_parameters(dict(sg.DEFAULTS))
        for key, value in (("radius_m", 0), ("neighbors", 2), ("neighbors", 16.5), ("dominant", .5),
                           ("vertical", 1.2), ("min_single_share", float("nan"))):
            with self.subTest(key=key), self.assertRaises(ValueError):
                sg.check_parameters(dict(sg.DEFAULTS, **{key: value}))


# ------------------------------------------------------------------ LAS copies

def write_las(path, points, modern, seed=0):
    """(x, y, z, class, flags, return number, return count) records; other bytes random.

    flags: modern classification-flag bits (1 synthetic, 2 key point, 4 withheld, 8 overlap) or legacy
    bits (32 synthetic, 64 key point, 128 withheld).
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    size, length = (375, 30) if modern else (227, 20)
    header = bytearray(size); header[:4] = b"LASF"; header[24:26] = bytes([1, 4 if modern else 2])
    struct.pack_into("<HII", header, 94, size, size, 0)
    struct.pack_into("<BHI", header, 104, 6 if modern else 0, length, len(points))
    if modern:
        struct.pack_into("<Q", header, 247, len(points))
    xyz = np.array([p[:3] for p in points])
    struct.pack_into("<3d", header, 131, .001, .001, .001)
    struct.pack_into("<3d", header, 155, 500000, 4500000, 0)
    struct.pack_into("<6d", header, 179, 500000+xyz[:, 0].max(), 500000+xyz[:, 0].min(),
                     4500000+xyz[:, 1].max(), 4500000+xyz[:, 1].min(), xyz[:, 2].max(), xyz[:, 2].min())
    with Path(path).open("wb") as handle:
        handle.write(header)
        for x, y, z, code, flags, number, count in points:
            record = bytearray(rng.integers(0, 256, length, dtype=np.uint8).tobytes())
            struct.pack_into("<iii", record, 0, round(x*1000), round(y*1000), round(z*1000))
            if modern:
                record[14] = number | count << 4
                record[15] = (record[15] & 0xF0) | flags
                record[16] = code
            else:
                record[14] = (record[14] & 0xC0) | number | count << 3
                record[15] = flags | code
            handle.write(record)


def building_scene(modern):
    """A facade (class 5) beside a flat roof (class 6), a crown, ground, noise and flagged sentinels."""
    import numpy as np
    rng = np.random.default_rng(7)
    synthetic, keypoint, withheld = (1, 2, 4) if modern else (32, 64, 128)
    points = []
    x, z = [a.ravel() for a in np.meshgrid(np.arange(10, 20, .25), np.arange(.5, 6, .25))]
    for xi, zi in zip(x+rng.uniform(-.05, .05, x.size), z+rng.uniform(-.05, .05, x.size)):
        points.append((xi, 10+rng.normal(0, .01), 100+zi, 5, 0, 1, 1))              # facade
    facade = len(points)
    sentinels = {"keypoint": (15.1, 10, 103.1, 5, keypoint, 1, 1), "withheld": (15.3, 10, 103.3, 5, withheld, 1, 1),
                 "synthetic": (15.2, 10, 102.8, 4, synthetic, 1, 1), "class3": (15.4, 10, 102.9, 3, 0, 1, 1),
                 "class1": (15.6, 10, 103.2, 1, 0, 1, 1), "noise7": (15.7, 10, 103.4, 7, 0, 1, 1),
                 "noise18": (15.8, 10, 103.6, 18, 0, 1, 1), "class4": (16.1, 10, 102.2, 4, 0, 1, 1)}
    index = {}
    for name, point in sentinels.items():
        index[name] = len(points); points.append(point)
    for rx in np.arange(10, 20, .25):
        for ry in np.arange(10.25, 18, .25):
            points.append((rx, ry, 106., 6, 0, 1, 1))                                # roof
    direction = rng.normal(size=(1500, 3)); direction /= np.linalg.norm(direction, axis=1)[:, None]
    crown = direction*(3*rng.uniform(0, 1, 1500)**(1/3))[:, None]+[30, 30, 108]
    crown_start = len(points)
    for (cx, cy, cz), count in zip(crown, rng.integers(1, 4, 1500)):
        points.append((cx, cy, cz, 5, 0, int(rng.integers(1, count+1)), int(count)))
    for gx in np.arange(0, 40, 1.):
        for gy in np.arange(0, 40, 1.):
            points.append((gx, gy, 100., 2, 0, 1, 1))
    return points, facade, index, (crown_start, crown_start+1500)


def flat_ground(value=100., calls=None, nan_below_x=None):
    """A stand-in for hag.raster_builder: flat ground (optionally NoData west of a local x)."""
    def build(folder, extent, cell):
        import numpy as np
        from canopy import hag
        if calls is not None:
            calls.append(list(extent))
        cols, rows = round((extent[2]-extent[0])/cell), round((extent[3]-extent[1])/cell)
        values = np.full((rows, cols), value, np.float32)
        if nan_below_x is not None:
            values[:, :int((500000+nan_below_x-extent[0])/cell)] = np.nan
        return hag.GroundSurface(values, extent[0], extent[3], cell, {"source": "flat test ground"})
    return build


def boundary_walls():
    """Three 8 m x 3 m walls (0.25 m grid) over flat ground at 100 m whose third rows stand exactly
    0.69, 0.70 and 0.71 m above ground; plus ground points. Returns points and the row heights."""
    import numpy as np
    points, rows = [], {}
    for base, (x0, y) in zip((.19, .20, .21), ((2, 10), (20, 10), (2, 30))):
        for x in np.arange(x0, x0+8, .25):
            for k in range(12):
                h = round(base+.25*k, 3)
                points.append((x, y, 100+h, 5, 0, 1, 1))
        rows[round(base+.5, 3)] = y
    for gx in np.arange(0, 40, 1.):
        for gy in np.arange(0, 40, 1.):
            points.append((gx, gy, 100., 2, 0, 1, 1))
    return points, rows


def prepared(folder, files, extent=(0, 0, 40, 40)):
    """A completed preparation folder around existing point files."""
    root = Path(folder)/"prepared"
    (root/"points").mkdir(parents=True)
    for name, (points, modern) in files.items():
        write_las(root/"points"/name, points, modern)
    lasd = root/"prepared.lasd"; lasd.write_text("fixture")
    (root/"preparation.json").write_text(json.dumps({
        "status": "complete", "working_lasd": str(lasd), "source_id": "fixture",
        "extent": [500000+extent[0], 4500000+extent[1], 500000+extent[2], 4500000+extent[3]]}))
    return lasd


@unittest.skipUnless(HAVE_SCIPY, "numpy and scipy required")
class Copies(unittest.TestCase):
    def fake_dataset(self, files, output):
        self.written = [Path(p).name for p in files]
        Path(output).write_text("dataset")

    def test_apply_changes_only_class_bytes_of_facade_points_in_legacy_and_modern_las(self):
        import numpy as np
        from canopy import shape_gate as sg
        from canopy.run_safeguards import completed_preparation
        for modern in (False, True):
            with self.subTest(modern=modern), tempfile.TemporaryDirectory() as folder:
                points, facade, sentinel, crown = building_scene(modern)
                lasd = prepared(folder, {"a.las": (points, modern)})
                source = lasd.parent/"points"/"a.las"
                before = source.read_bytes()
                out = Path(folder)/"gated"
                state = sg.run(lasd, out, apply=True, dataset=self.fake_dataset, ground=flat_ground())
                self.assertEqual(state["status"], "complete")
                self.assertEqual(before, source.read_bytes())
                after = (out/"points"/"a.las").read_bytes()
                size, length, byte = (375, 30, 16) if modern else (227, 20, 15)
                differing = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
                self.assertEqual(len(before), len(after))
                with np.load(out/"changes"/"a.npz") as audit:
                    changed = audit["point_index"].tolist()
                    self.assertEqual(differing, [size+i*length+byte for i in changed])
                    self.assertEqual(audit["previous_class_byte"].tolist(), [before[size+i*length+byte] for i in changed])
                    self.assertTrue(set(audit["group"].tolist()) <= {1, 5, 6})
                    self.assertTrue(audit["own_single"].all())
                changed = set(changed)
                keep = {sentinel[name] for name in ("withheld", "synthetic", "class3", "class1", "noise7", "noise18")}
                self.assertFalse(changed & keep)
                self.assertTrue(changed <= set(range(facade)) | {sentinel["keypoint"], sentinel["class4"]})
                self.assertGreater(len(changed & set(range(facade))), .8*facade)
                self.assertIn(sentinel["keypoint"], changed)
                self.assertIn(sentinel["class4"], changed)
                self.assertFalse(changed & set(range(*crown)))
                # Legacy key-point bits survive; the class becomes 1.
                expected = 1 if modern else 64 | 1
                self.assertEqual(after[size+sentinel["keypoint"]*length+byte], expected)
                files = state["files"]["a.las"]
                self.assertEqual(files["changed"], len(changed))
                self.assertEqual(files["changed_by_return"]["single"], len(changed))
                self.assertEqual(files["changed_by_class"]["4"], 1)
                self.assertEqual(self.written, ["a.las"])
                self.assertEqual(state["after"]["a.las"]["classes"]["1"], len(changed)+1)
                self.assertTrue(completed_preparation(out))
                manifest = json.loads((out/"preparation.json").read_text())
                self.assertEqual(manifest["working_lasd"], str(out/"prepared.lasd"))
                self.assertEqual(manifest["source_id"], "fixture")
                with self.assertRaises(FileExistsError):
                    sg.run(lasd, out, apply=True, dataset=self.fake_dataset, ground=flat_ground())

    def test_review_recodes_only_candidates_inside_the_extent(self):
        import numpy as np
        from canopy import shape_gate as sg
        with tempfile.TemporaryDirectory() as folder:
            points, facade, sentinel, crown = building_scene(True)
            far = [(x, y, 100., 2, 0, 1, 1) for x in (35., 39.) for y in (35., 39.)]
            lasd = prepared(folder, {"a.las": (points, True), "far.las": (far, True)})
            gate = [500000, 4500000, 500025, 4500040]   # the facade, not the crown at x = 30
            out = Path(folder)/"review"
            calls = []
            state = sg.run(lasd, out, extent=gate, ground=flat_ground(calls=calls))
            # ground covers the gate plus 20 m, clipped to the prepared extent
            self.assertEqual(calls, [[500000, 4500000, 500040, 4500040]])
            self.assertEqual(state["mode"], "review")
            self.assertFalse((out/"preparation.json").exists())
            self.assertTrue((out/"shape_gate.json").is_file())
            before = (lasd.parent/"points"/"a.las").read_bytes()
            after = (out/"points"/"a.las").read_bytes()
            differing = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
            with np.load(out/"changes"/"a.npz") as audit:
                changed = audit["point_index"].tolist()
                self.assertEqual(differing, [375+i*30+16 for i in changed])
                self.assertTrue(set(audit["new_class_byte"].tolist()) <= set(range(64, 73)))
            eligible = [i for i, p in enumerate(points) if p[3] in (3, 4, 5) and not p[4] & 13 and p[0] <= 25]
            self.assertEqual(changed, eligible)
            self.assertFalse((out/"points"/"far.las").exists())
            wall = state["by_class"]["5"]["groups"]["wall_like"]["points"]
            self.assertGreater(wall, .8*facade)
            self.assertEqual(sum(g["points"] for g in state["by_class"]["5"]["groups"].values()),
                             state["by_class"]["5"]["points"])
            self.assertTrue(state["edge_effects_possible"])

    def test_refusals(self):
        from canopy import shape_gate as sg
        with tempfile.TemporaryDirectory() as folder:
            points, *_ = building_scene(False)
            lasd = prepared(folder, {"a.las": (points, False)})
            g = flat_ground()
            with self.assertRaisesRegex(ValueError, "formats 6-10"):
                sg.run(lasd, Path(folder)/"legacy_review", ground=g)
            self.assertFalse((Path(folder)/"legacy_review").exists())
            with self.assertRaisesRegex(ValueError, "dataset writer"):
                sg.run(lasd, Path(folder)/"no_writer", apply=True, ground=g)
            with self.assertRaisesRegex(ValueError, "ground surface builder"):
                sg.run(lasd, Path(folder)/"no_ground", apply=True, dataset=self.fake_dataset)
            self.assertFalse((Path(folder)/"no_ground").exists())
            with self.assertRaisesRegex(ValueError, "inside the prepared extent"):
                sg.run(lasd, Path(folder)/"outside", extent=[499990, 4500000, 500010, 4500010],
                       apply=True, dataset=self.fake_dataset, ground=g)
            with self.assertRaisesRegex(ValueError, "outside the input preparation"):
                sg.run(lasd, lasd.parent/"inside", apply=True, dataset=self.fake_dataset, ground=g)
            with self.assertRaisesRegex(ValueError, "subset of 3, 4 and 5"):
                sg.run(lasd, Path(folder)/"classes", apply=True, classes=(6,), dataset=self.fake_dataset, ground=g)
            with self.assertRaisesRegex(ValueError, "at most 100"):
                sg.run(lasd, Path(folder)/"many", apply=True, dataset=self.fake_dataset, max_points=100, ground=g)
            state = json.loads((Path(folder)/"many"/"preparation.json").read_text())
            self.assertEqual(state["status"], "failed")

    def test_minimum_wall_height_boundary_in_review_codes_and_audit(self):
        import numpy as np
        from canopy import shape_gate as sg
        with tempfile.TemporaryDirectory() as folder:
            points, rows = boundary_walls()
            lasd = prepared(folder, {"a.las": (points, True)})
            out = Path(folder)/"review"
            state = sg.run(lasd, out, ground=flat_ground())
            self.assertEqual(state["parameters"]["min_wall_height"], .7)
            with np.load(out/"changes"/"a.npz") as audit:
                index, code, hag = audit["point_index"], audit["new_class_byte"], audit["hag_m"]
            z = np.array([points[i][2] for i in index])
            np.testing.assert_allclose(hag, z-100, atol=1e-5)
            shaped = np.isin(code, (65, 72))
            self.assertTrue(((code == 72) == (shaped & (np.round(hag.astype(float), 4) < .7))).all())
            for height, expected in ((.69, 72), (.70, 65), (.71, 65)):
                row = shaped & np.isclose(hag, height, atol=1e-4)
                self.assertGreaterEqual(int(row.sum()), 20, height)       # interior of a 32-point row
                self.assertTrue((code[row] == expected).all(), (height, np.unique(code[row])))
            self.assertTrue((code[shaped & (hag < .6)] == 72).all())
            split = state["wall_height"]
            self.assertEqual(split["wall_shaped"], split["wall_like"]+split["low_wall"])
            self.assertEqual(split["low_wall"], int((code == 72).sum()))
            self.assertEqual(state["by_class"]["5"]["groups"]["low_wall"]["points"], split["low_wall"])
            self.assertEqual(split["candidates_without_ground"], 0)

    def test_low_walls_are_never_applied_and_ground_less_walls_are_low(self):
        import numpy as np
        from canopy import shape_gate as sg
        with tempfile.TemporaryDirectory() as folder:
            points, rows = boundary_walls()
            points = [(x, y, z, c, 0, 1, 1) for x, y, z, c, *_ in points]
            lasd = prepared(folder, {"a.las": (points, True)})
            state = sg.run(lasd, Path(folder)/"apply", apply=True, dataset=lambda f, o: Path(o).write_text("x"),
                           ground=flat_ground())
            with np.load(Path(folder)/"apply"/"changes"/"a.npz") as audit:
                self.assertGreater(len(audit["point_index"]), 0)
                self.assertTrue((np.round(audit["hag_m"].astype(float), 4) >= .7).all())
                self.assertNotIn(sg.LOW_WALL, set(audit["group"].tolist()))
            self.assertGreater(state["wall_height"]["low_wall"], 0)
            # Without ground coverage a wall-shaped point cannot be shown to be tall enough.
            state = sg.run(lasd, Path(folder)/"no_ground", ground=flat_ground(nan_below_x=12))
            self.assertGreater(state["wall_height"]["low_wall_without_ground"], 0)
            with np.load(Path(folder)/"no_ground"/"changes"/"a.npz") as audit:
                west = np.array([points[i][0] < 11.5 for i in audit["point_index"]])
                self.assertTrue(np.isnan(audit["hag_m"][west]).all())
                self.assertFalse((audit["new_class_byte"][west] == 65).any())

    def test_split_low_walls_boundary(self):
        import numpy as np
        from canopy import shape_gate as sg
        group = np.array([sg.WALL_LIKE]*6+[sg.WIRE, sg.POLE, sg.ROOF_LIKE], np.uint8)
        hag = np.array([.69, .69994, .69996, .70, .71, np.nan, .1, .1, .1])
        out = sg.split_low_walls(group, hag, .7)
        self.assertEqual([sg.GROUPS[g] for g in out], ["low_wall", "low_wall", "wall_like", "wall_like", "wall_like",
                                                       "low_wall", "wire", "pole", "roof_like"])
        self.assertEqual(sg.REVIEW_CODES["low_wall"], 72)
        self.assertNotIn(sg.LOW_WALL, sg.APPLY_GROUPS)
        self.assertTrue((sg.split_low_walls(group, hag, 0.) == np.where(np.isnan(hag) & (group == sg.WALL_LIKE),
                                                                        sg.LOW_WALL, group)).all())

    def test_cli_rejects_classes_without_apply(self):
        import contextlib, io
        from canopy.__main__ import main
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            main(["shape-gate", "in.lasd", "out", "--classes", "5"])


@unittest.skipUnless(importlib.util.find_spec("pdal") is not None and HAVE_SCIPY, "PDAL (ArcGIS Pro) required")
class PdalAgreement(unittest.TestCase):
    def test_features_match_pdal_covariance_features_knn_16(self):
        import numpy as np
        import pdal
        from canopy import shape_gate as sg
        from scipy.spatial import cKDTree
        scene = scenes(3)
        xyz = np.vstack([scene["wall"], scene["wire"]+[40, 0, 0], scene["pole"]+[0, 40, 0], scene["crown"]+[40, 40, 0]])
        array = np.zeros(len(xyz), dtype=[("X", "f8"), ("Y", "f8"), ("Z", "f8")])
        array["X"], array["Y"], array["Z"] = xyz.T
        pipeline = pdal.Pipeline(json.dumps([{"type": "filters.covariancefeatures", "knn": 16, "threads": 1,
                                              "feature_set": "Dimensionality"}]), arrays=[array])
        pipeline.execute()
        out = pipeline.arrays[0]
        found, count, _ = sg.features(xyz, cKDTree(xyz), np.arange(len(xyz)), radius=np.inf)
        self.assertTrue((count == 17).all())
        for mine, theirs in (("linearity", "Linearity"), ("planarity", "Planarity"), ("scattering", "Scattering"),
                             ("pdal_verticality", "Verticality")):
            np.testing.assert_allclose(found[mine], out[theirs], atol=1e-5, err_msg=mine)


@unittest.skipUnless(ARCPY and HAVE_SCIPY, "ArcGIS Pro Python required")
class ApplyDataset(unittest.TestCase):
    def test_cli_apply_writes_a_prepared_dataset_run_can_read(self):
        import arcpy, contextlib, io
        from canopy.__main__ import main
        from canopy.run_safeguards import completed_preparation
        with tempfile.TemporaryDirectory() as folder:
            points, *_ = building_scene(True)
            lasd = prepared(folder, {"a.las": (points, True)})
            lasd.unlink()
            arcpy.management.CreateLasDataset([str(lasd.parent/"points"/"a.las")], str(lasd),
                                              spatial_reference=arcpy.SpatialReference(26912))
            out = Path(folder)/"gated"
            with contextlib.redirect_stdout(io.StringIO()):
                main(["shape-gate", str(lasd), str(out), "--apply"])
            self.assertTrue(completed_preparation(out))
            self.assertEqual(arcpy.Describe(str(out/"prepared.lasd")).spatialReference.factoryCode, 26912)
            arcpy.management.ClearWorkspaceCache()
