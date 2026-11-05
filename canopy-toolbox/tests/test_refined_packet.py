import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/"reviews"/"2026-10-20"/"refined-cylinders"/"build_refined_packet.py"
spec = importlib.util.spec_from_file_location("build_refined_packet", SCRIPT)
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)


def column(low, high, n):
    return [low+(high-low)*i/(n-1) for i in range(n)]


class Layers(unittest.TestCase):
    def test_a_roof_and_a_tree_above_it_are_two_layers_top_first(self):
        z = column(4.0, 4.3, 20)+column(7.0, 9.0, 30)
        self.assertEqual([(round(a, 2), round(b, 2), n) for a, b, n in rp.layers(z)], [(7.0, 9.0, 30), (4.0, 4.3, 20)])

    def test_small_layers_are_dropped_and_too_few_points_give_nothing(self):
        z = column(4.0, 4.3, 20)+column(7.0, 7.1, 5)
        self.assertEqual(len(rp.layers(z)), 1)
        self.assertEqual(rp.layers(column(1, 2, 5)), [])

    def test_at_most_four_layers(self):
        z = []
        for k in range(6):
            z += column(2.0*k, 2.0*k+0.2, 15)
        self.assertLessEqual(len(rp.layers(z)), 4)


class SubUnits(unittest.TestCase):
    def test_names_slabs_and_blind_fields(self):
        parent = {"UNIT_ID": "Q1-0006", "QUEUE": "Q1_TREE_ON_ROOF", "QUEUE_ORDER": 6, "TILE": "12TVL2804", "X": 1.0, "Y": 2.0,
                  "Z_LOW": 3.0, "Z_HIGH": 9.5, "GROUND_Z": 1.0, "PRIORITY": 0.5}
        subs = rp.sub_units(parent, column(4.0, 4.3, 20)+column(7.0, 9.6, 30), 11)
        self.assertEqual([s["UNIT_ID"] for s in subs], ["Q1-0006-a", "Q1-0006-b"])
        self.assertEqual([s["REVIEW_ORDER"] for s in subs], [11, 12])
        self.assertEqual((subs[0]["Z_LOW"], subs[0]["Z_HIGH"]), (6.95, 9.5))      # never beyond the parent slab
        self.assertEqual((subs[1]["Z_LOW"], subs[1]["Z_HIGH"]), (3.95, 4.35))
        self.assertTrue(all(s["PATCH_R_M"] == 0.5 and s["BASE_CLASS"] is None and s["TREE_MODEL"] is None for s in subs))


if __name__ == "__main__":
    unittest.main()
