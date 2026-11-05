import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

REVIEWS = Path(__file__).resolve().parents[1]/"reviews"/"2026-09-30"
spec = importlib.util.spec_from_file_location("audit_sample", REVIEWS/"audit_sample.py")
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)


def row(unit, tier="AUTO_CANDIDATE", proposed="BUILDING_ROOF", human=""):
    return {"UNIT_ID": unit, "TIER": tier, "PROPOSED": proposed if tier == "AUTO_CANDIDATE" else "", "HUMAN_LABEL": human}


PROPOSALS = ([row(f"Q6-{i:04d}") for i in range(1, 61)] + [row(f"Q2-{i:04d}", proposed="GROUND") for i in range(1, 21)] +
             [row("Q1-0001", tier="REVIEW"), row("Q1-0002", human="BUILDING_ROOF")])


class Draw(unittest.TestCase):
    def test_pool_is_auto_candidates_nobody_has_labelled(self):
        pool = au.pool_ids(PROPOSALS, labelled={"Q6-0003", "Q2-0001"})
        self.assertEqual(len(pool), 78)                                  # 80 AUTO, minus two labelled since
        self.assertNotIn("Q6-0003", pool)
        self.assertNotIn("Q1-0001", pool)                                # a review unit is never audited
        self.assertNotIn("Q1-0002", pool)                                # a unit labelled when triage ran is excluded

    def test_draw_is_reproducible_sorted_and_recorded(self):
        first = au.draw(PROPOSALS, set(), 40, 20260930)
        again = au.draw(PROPOSALS, set(), 40, 20260930)
        other = au.draw(PROPOSALS, set(), 40, 1)
        self.assertEqual(first, again)
        self.assertNotEqual(first["units"], other["units"])
        self.assertEqual((first["n"], len(set(first["units"])), first["pool_size"]), (40, 40, 80))
        self.assertEqual(first["units"], sorted(first["units"]))
        self.assertEqual(sum(first["class_mix"].values()), 40)
        self.assertEqual(first["pool_sha256"], au.digest(au.pool_ids(PROPOSALS, set())))
        changed = au.draw(PROPOSALS[:-3], set(), 40, 20260930)           # a different pool leaves a different record
        self.assertNotEqual(changed["pool_sha256"], first["pool_sha256"])
        with self.assertRaisesRegex(ValueError, "only 80"):
            au.draw(PROPOSALS, set(), 81, 1)

    def test_the_labeller_files_carry_ids_only_and_a_working_expression(self):
        with tempfile.TemporaryDirectory() as tmp:
            triage, out = Path(tmp, "t.csv"), Path(tmp, "audit")
            import csv
            with open(triage, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["UNIT_ID", "TIER", "PROPOSED", "HUMAN_LABEL"])
                writer.writeheader(); writer.writerows(PROPOSALS)
            au.main(["draw", str(out), "--n", "5", "--triage", str(triage), "--labels", str(Path(tmp, "none.csv"))])
            units = out.joinpath("audit-units.txt").read_text().split()
            self.assertEqual(len(units), 5)
            for name in ("audit-units.txt", "audit-select.txt"):
                text = out.joinpath(name).read_text()
                for proposal in ("BUILDING_ROOF", "GROUND", "AUTO", "PROPOSED"):
                    self.assertNotIn(proposal, text)                     # no proposal leaks into what the labeller sees
            self.assertTrue(out.joinpath("audit-select.txt").read_text().startswith("UNIT_ID IN ('"))
            with self.assertRaises(FileExistsError):
                au.main(["draw", str(out), "--triage", str(triage)])


class Score(unittest.TestCase):
    def sample(self):
        return {"n": 4, "units": ["Q6-0001", "Q6-0002", "Q2-0001", "Q2-0002"]}

    def labels(self, **answers):
        base = {"Q6-0001": "BUILDING_ROOF", "Q6-0002": "BUILDING_ROOF", "Q2-0001": "GROUND", "Q2-0002": "GROUND"}
        base.update({k.replace("_", "-"): v for k, v in answers.items()})
        return [{"UNIT_ID": u, "LABEL": label} for u, label in base.items()]

    def test_lower_bounds_match_known_values(self):
        self.assertAlmostEqual(au.lower_bound(40, 40), 0.928, places=3)
        self.assertAlmostEqual(au.lower_bound(40, 39), 0.887, places=3)
        self.assertAlmostEqual(au.lower_bound(60, 58), 0.899, places=3)
        self.assertEqual(au.lower_bound(10, 0), 0.0)

    def test_agreement_disagreements_and_classes(self):
        result = au.score(self.sample(), PROPOSALS, self.labels(Q2_0002="TREE"))
        self.assertEqual((result["audited"], result["agree"], result["disagree"]), (4, 3, 1))
        self.assertEqual(result["disagreements"][0]["unit"], "Q2-0002")
        self.assertEqual(result["by_class"], {"BUILDING_ROOF": {"audited": 2, "agree": 2}, "GROUND": {"audited": 2, "agree": 1}})
        self.assertLess(result["lower_bound_95"], result["agreement"])

    def test_mixed_and_unsure_are_not_confirmed(self):
        result = au.score(self.sample(), PROPOSALS, self.labels(Q6_0001="MIXED", Q6_0002="UNSURE"))
        self.assertEqual(result["agree"], 2)
        self.assertTrue(all(d["not_confirmed"] for d in result["disagreements"]))

    def test_refuses_while_any_audited_unit_is_unlabelled(self):
        labels = [r for r in self.labels() if r["UNIT_ID"] != "Q2-0002"] + [{"UNIT_ID": "Q2-0002", "LABEL": ""}]
        with self.assertRaisesRegex(ValueError, "1 of 4 audited units are not labelled"):
            au.score(self.sample(), PROPOSALS, labels)


if __name__ == "__main__":
    unittest.main()
