"""Real geodatabase label exchange, transaction rollback and reference immutability."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('arcpy'), 'ArcGIS Pro Python required')
class LabelExchangeArcGIS(unittest.TestCase):
    def setUp(self):
        import arcpy
        from canopy import validation
        self.arcpy = arcpy
        self.tmp = tempfile.TemporaryDirectory(prefix='canopy_labels_')
        self.root = Path(self.tmp.name)
        self.gdb = self.root / 'reference.gdb'
        self.sr = arcpy.SpatialReference(6341)
        validation.create_reference_gdb(self.gdb, self.sr)
        rows = {}
        for sample in validation.SAMPLES:
            common = dict(tile='T1', stratum='A', SAMPLE_ID=sample+'1', REVIEW_ORDER=1,
                          BATCH=1, x=500000., y=4500000.)
            if sample == 'crown':
                common['shape'] = arcpy.Polygon(arcpy.Array([arcpy.Point(x, y) for x, y in
                    [(499999.,4499999.),(499999.,4500001.),(500001.,4500001.),(500001.,4499999.)]]), self.sr)
            rows[sample] = [common]
        validation.write_units(self.gdb, rows)
        validation.write_design(self.gdb, [dict(sample=s, tile='T1', stratum='A', population=100,
            unit_area_m2=.25 if s in ('cell','omission') else None, target=1, sampled=1,
            frame='fixture', base_run=str(self.root / 'baseline')) for s in rows])
        self.packet = self.root / 'packet'

    def tearDown(self):
        self.arcpy.management.ClearWorkspaceCache()
        self.tmp.cleanup()

    def export(self):
        from canopy import validation
        validation.export_labels(self.gdb, self.packet, batch=1)
        return self.packet / 'labels.csv'

    def edit(self, path, labels):
        with path.open(newline='', encoding='utf-8-sig') as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if row['SAMPLE'] in labels:
                row.update(LABEL=labels[row['SAMPLE']], REVIEWER='Fixture reviewer', REVIEW_DATE='2026-09-29')
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def state(self):
        from canopy import validation
        units, design = validation.read_reference(self.gdb)
        snapshot = {s: [dict(row, shape=bytes(row['shape'].WKB)) for row in rows] for s, rows in units.items()}
        return snapshot, design

    def test_export_and_preview_leave_labels_geometry_and_design_unchanged(self):
        from canopy import validation
        before = self.state()
        path = self.export()
        self.edit(path, {'treetop': 'TREE'})
        plan = validation.import_labels(self.gdb, path, self.packet / 'packet.json')
        self.assertEqual((plan['status'], plan['changed']), ('DRY_RUN', 1))
        self.assertEqual(self.state(), before)
        with path.open(encoding='utf-8-sig') as handle:
            self.assertNotIn('STRATUM', next(csv.reader(handle)))

    def test_apply_edits_only_review_fields_and_reimport_is_idempotent(self):
        from canopy import validation
        before = self.state()
        path = self.export()
        self.edit(path, {'treetop': 'TREE', 'crown': 'CORRECT'})
        audit = self.root / 'audit'
        result = validation.import_labels(self.gdb, path, self.packet / 'packet.json', apply=True, audit_folder=audit)
        self.assertEqual((result['status'], result['changed']), ('APPLIED', 2))
        after = self.state()
        self.assertEqual(before[1], after[1])
        review_fields = {'LABEL','CROWN_LABEL','ROOF_IN_OUTLINE','REVIEWER','REVIEW_DATE','NOTES'}
        for sample, rows in before[0].items():
            for old, new in zip(rows, after[0][sample]):
                self.assertEqual({k:v for k,v in old.items() if k not in review_fields},
                                 {k:v for k,v in new.items() if k not in review_fields})
        self.assertEqual(after[0]['treetop'][0]['LABEL'], 'TREE')
        self.assertEqual(after[0]['treetop'][0]['REVIEWER'], 'Fixture reviewer')
        self.assertEqual(json.loads((audit / 'import.json').read_text())['status'], 'APPLIED')
        again = validation.import_labels(self.gdb, path, self.packet / 'packet.json')
        self.assertEqual((again['changed'], again['unchanged']), (0,2))

    def test_mixed_invalid_labels_never_apply_a_valid_prefix(self):
        from canopy import validation
        path = self.export()
        self.edit(path, {'cell': 'TREE', 'treetop': 'TRE'})
        before = self.state()
        with self.assertRaises(ValueError):
            validation.import_labels(self.gdb, path, self.packet / 'packet.json', apply=True, audit_folder=self.root/'audit')
        self.assertEqual(self.state(), before)

    def test_runtime_failure_after_first_write_rolls_back_all_samples(self):
        from canopy import validation
        path = self.export()
        self.edit(path, {'cell': 'TREE', 'treetop': 'ROOF_OR_BUILDING'})
        before = self.state()
        original = validation._write_label_changes
        def fail_after_first(gdb, changes):
            original(gdb, changes[:1])
            raise RuntimeError('fixture interrupted after one write')
        audit = self.root / 'failed-audit'
        with patch.object(validation, '_write_label_changes', side_effect=fail_after_first):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                validation.import_labels(self.gdb, path, self.packet / 'packet.json', apply=True, audit_folder=audit)
        self.assertEqual(self.state(), before)
        self.assertEqual(json.loads((audit / 'import.json').read_text())['status'], 'ROLLED_BACK')

    def test_changed_reference_geometry_rejects_old_packet(self):
        from canopy import validation
        path = self.export()
        self.edit(path, {'treetop': 'TREE'})
        with self.arcpy.da.UpdateCursor(str(self.gdb / 'treetop_sample'), ['SHAPE@XY']) as cursor:
            for row in cursor:
                row[0] = (500001., 4500000.)
                cursor.updateRow(row)
        before = self.state()
        with self.assertRaisesRegex(ValueError, 'frame'):
            validation.import_labels(self.gdb, path, self.packet / 'packet.json', apply=True, audit_folder=self.root/'audit')
        self.assertEqual(self.state(), before)


if __name__ == '__main__':
    unittest.main()
