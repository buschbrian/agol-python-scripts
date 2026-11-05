"""Blind reference-label exchange contracts; no ArcPy."""
import copy
import unittest

from canopy import label_exchange as exchange


def frames():
    return [dict(sample='treetop', SAMPLE_ID='TT1', REVIEW_ORDER=2, BATCH=1,
                 TILE='T1', STRATUM='ROOF_LEVEL', x=500000., y=4500000., LABEL=None,
                 REVIEWER=None, REVIEW_DATE=None, NOTES=None, HEIGHT_M=8.),
            dict(sample='treetop', SAMPLE_ID='TT2', REVIEW_ORDER=1, BATCH=1,
                 TILE='T2', STRATUM='NORMAL', x=500002., y=4500000., LABEL=None,
                 REVIEWER=None, REVIEW_DATE=None, NOTES=None, HEIGHT_M=10.),
            dict(sample='crown', SAMPLE_ID='CR1', REVIEW_ORDER=1, BATCH=1,
                 TILE='T1', STRATUM='CR_SMALL', x=500000., y=4500000.,
                 CROWN_LABEL=None, ROOF_IN_OUTLINE=None, REVIEWER=None,
                 REVIEW_DATE=None, NOTES=None, geometry_sha256='crown-outline')]


class LabelExchange(unittest.TestCase):
    def setUp(self):
        self.frames = frames()
        self.digest = exchange.reference_digest(self.frames, [{'population': 100}])
        self.rows = exchange.export_rows(self.frames, self.digest, batch=1)

    def labelled(self, sample='treetop', sample_id='TT1', label='TREE'):
        row = dict(next(r for r in self.rows if r['SAMPLE'] == sample and r['SAMPLE_ID'] == sample_id))
        row.update(LABEL=label, REVIEWER='Brian', REVIEW_DATE='2026-09-29', NOTES='Independent imagery review')
        return row

    def plan(self, rows, **kwargs):
        return exchange.plan_import(rows, self.frames, self.digest, **kwargs)

    def test_export_hides_model_strata_and_coordinate_evidence(self):
        forbidden = {'STRATUM', 'TILE', 'BATCH', 'CONTEXT', 'HEIGHT_M', 'x', 'y', 'BASE_TREE_ID'}
        for row in self.rows:
            self.assertFalse(forbidden & set(row))
            self.assertEqual(set(row), set(exchange.COLUMNS))
        self.assertEqual([r['SAMPLE_ID'] for r in self.rows if r['SAMPLE'] == 'treetop'], ['TT2', 'TT1'])

    def test_batch_selection_preserves_existing_review_order(self):
        self.frames[0]['BATCH'] = 2
        digest = exchange.reference_digest(self.frames, [])
        rows = exchange.export_rows(self.frames, digest, batch=1)
        self.assertNotIn('TT1', [r['SAMPLE_ID'] for r in rows])
        self.assertEqual(len(exchange.export_rows(self.frames, digest, batch=None)), 3)

    def test_digest_is_order_independent_and_ignores_review_edits(self):
        modified = copy.deepcopy(self.frames)
        modified[0].update(LABEL='TREE', REVIEWER='Brian', REVIEW_DATE='2026-09-29', NOTES='Reviewed')
        self.assertEqual(self.digest, exchange.reference_digest(modified[::-1], [{'population': 100}]))
        modified[0]['x'] += 1
        self.assertNotEqual(self.digest, exchange.reference_digest(modified, [{'population': 100}]))

    def test_digest_covers_crown_geometry_and_sampling_design(self):
        modified = copy.deepcopy(self.frames)
        modified[-1]['geometry_sha256'] = 'different-outline'
        self.assertNotEqual(self.digest, exchange.reference_digest(modified, [{'population': 100}]))
        self.assertNotEqual(self.digest, exchange.reference_digest(self.frames, [{'population': 101}]))

    def test_valid_partial_labels_plan_only_review_fields_without_mutation(self):
        before = copy.deepcopy(self.frames)
        # Keep a partial file: an unlabelled exported row can be omitted.
        plan = self.plan([self.labelled(), next(r for r in self.rows if r['SAMPLE'] == 'crown')])
        self.assertEqual(plan['changed'], 1)
        self.assertEqual(plan['blank'], 1)
        change = plan['changes'][0]
        self.assertEqual(change['after']['LABEL'], 'TREE')
        self.assertEqual(set(change['after']), {'LABEL', 'REVIEWER', 'REVIEW_DATE', 'NOTES'})
        self.assertEqual(self.frames, before)

    def test_duplicate_unknown_or_wrong_identity_rows_are_rejected(self):
        row = self.labelled()
        for rows in ([row, row], [{**row, 'SAMPLE_ID': 'missing'}], [{**row, 'SAMPLE': 'cell'}],
                     [{**row, 'REVIEW_ORDER': 999}], [{**row, 'UNIT_TOKEN': 'wrong'}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.plan(rows)

    def test_invalid_label_domains_fail_before_any_changes_are_returned(self):
        for row in (self.labelled(label='TRE'), self.labelled(label='CORRECT'),
                    self.labelled('crown', 'CR1', 'TREE'),
                    {**self.labelled(), 'ROOF_IN_OUTLINE': 'YES'},
                    {**self.labelled('crown', 'CR1', 'CORRECT'), 'ROOF_IN_OUTLINE': 'MAYBE'}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.plan([self.labelled(sample_id='TT2'), row])

    def test_missing_reviewer_date_bad_date_and_overlong_fields_are_rejected(self):
        for edit in ({'REVIEWER': ''}, {'REVIEW_DATE': ''}, {'REVIEW_DATE': '2026-02-30'},
                     {'REVIEW_DATE': '09/29/2026'}, {'REVIEWER': 'x'*65}, {'NOTES': 'x'*501}):
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                self.plan([{**self.labelled(), **edit}])

    def test_unsure_is_recorded_as_reviewed_but_not_usable(self):
        plan = self.plan([self.labelled(label='UNSURE')])
        self.assertEqual((plan['changed'], plan['unsure'], plan['usable']), (1, 1, 0))

    def test_crown_outline_and_roof_answers_are_preserved_separately(self):
        plan = self.plan([{**self.labelled('crown', 'CR1', 'CORRECT'), 'ROOF_IN_OUTLINE': 'UNSURE'}])
        after = plan['changes'][0]['after']
        self.assertEqual(after['CROWN_LABEL'], 'CORRECT')
        self.assertEqual(after['ROOF_IN_OUTLINE'], 'UNSURE')
        self.assertNotIn('LABEL', after)

    def test_existing_conflicting_labels_require_explicit_replacement(self):
        self.frames[0].update(LABEL='ROOF_OR_BUILDING', REVIEWER='First reviewer', REVIEW_DATE='2026-09-28')
        with self.assertRaisesRegex(ValueError, 'existing'):
            self.plan([self.labelled()])
        plan = self.plan([self.labelled()], replace_existing=True)
        self.assertEqual(plan['changes'][0]['before']['LABEL'], 'ROOF_OR_BUILDING')
        self.assertEqual(plan['changes'][0]['after']['LABEL'], 'TREE')

    def test_reimport_is_idempotent_and_preserves_first_reviewer(self):
        self.frames[0].update(LABEL='TREE', REVIEWER='First reviewer', REVIEW_DATE='2026-09-28')
        plan = self.plan([self.labelled()])
        self.assertEqual((plan['changed'], plan['unchanged']), (0, 1))
        self.assertEqual(self.frames[0]['REVIEWER'], 'First reviewer')

    def test_blank_labels_cannot_clear_answers_and_orphan_roof_answers_fail(self):
        self.frames[0].update(LABEL='TREE', REVIEWER='First reviewer')
        plan = self.plan([next(r for r in self.rows if r['SAMPLE_ID'] == 'TT1')])
        self.assertEqual((plan['changed'], plan['blank']), (0, 1))
        self.assertEqual(self.frames[0]['LABEL'], 'TREE')
        crown = next(r for r in self.rows if r['SAMPLE'] == 'crown')
        with self.assertRaises(ValueError):
            self.plan([{**crown, 'ROOF_IN_OUTLINE': 'YES'}])

    def test_extra_columns_and_duplicate_reference_keys_fail_clearly(self):
        with self.assertRaises(ValueError):
            self.plan([{**self.labelled(), 'STRATUM': 'ROOF_LEVEL'}])
        with self.assertRaises(ValueError):
            exchange.reference_digest(self.frames + [self.frames[0]], [])


if __name__ == '__main__':
    unittest.main()
