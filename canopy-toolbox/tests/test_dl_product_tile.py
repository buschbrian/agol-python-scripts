"""Full-tile product runs reproduce the baseline run's parameters through the real CLI parser."""
import importlib.util
import sys
import unittest
from unittest.mock import MagicMock, patch

from tests.test_dl_thin import REVIEWS

BASELINE = {"extent": [428000.0, 4504000.0, 429000.0, 4505000.0], "tile_size": 200, "overlap": 15.0,
            "cell_size": 0.5, "bands": "2-6:1.0, 6-12:1.5, 12-20:2.0, 20-:2.5", "smoothing": 1,
            "min_crown_area": 3, "source_id": "d6727c3141d23effdd67fdfe", "z_unit": None,
            "building_clearance": 0.35}


def load():
    spec = importlib.util.spec_from_file_location('dl_product_tile', REVIEWS / 'dl_product_tile.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductRunArguments(unittest.TestCase):
    def setUp(self):
        self.module = load()

    def parsed_run(self, argv):
        """Call canopy's own CLI with the pipeline mocked and return pipeline.run's arguments."""
        pipeline = MagicMock()
        pipeline.run.return_value = {}
        fakes = {name: MagicMock() for name in ('arcpy', 'canopy.common', 'canopy.licensing', 'canopy.preparation')}
        fakes['canopy.pipeline'] = pipeline
        import canopy
        with patch.dict(sys.modules, fakes), patch.object(canopy, 'pipeline', pipeline, create=True), \
                patch.object(canopy, 'common', fakes['canopy.common'], create=True), \
                patch.object(canopy, 'licensing', fakes['canopy.licensing'], create=True), \
                patch.object(canopy, 'preparation', fakes['canopy.preparation'], create=True), \
                patch('builtins.print'):
            from canopy import __main__ as cli
            cli.main(argv)
        return pipeline.run.call_args.args

    def test_arguments_reproduce_every_baseline_processing_parameter(self):
        files = ['a.las', 'b.las']
        argv = self.module.run_arguments(BASELINE, 'product.lasd', 'run', files, True)
        (lasd, output, extent, tile_size, overlap, cell_size, bands, smooth, min_crown, source_files, source_id,
         resume, z_unit, clearance, background_zero) = self.parsed_run(argv)
        self.assertEqual((lasd, output), ('product.lasd', 'run'))
        self.assertEqual(extent, BASELINE['extent'])
        self.assertEqual((tile_size, overlap, cell_size, bands, smooth, min_crown, clearance),
                         (200, 15.0, 0.5, BASELINE['bands'], 1, 3, 0.35))
        self.assertEqual(source_files, files)
        self.assertIsNone(source_id)  # deliberately not the baseline's: it names different points
        self.assertFalse(resume)
        self.assertIsNone(z_unit)
        self.assertTrue(background_zero)

    def test_metres_z_unit_and_background_flag_are_explicit(self):
        argv = self.module.run_arguments(dict(BASELINE, z_unit='metres'), 'l', 'o', ['a.las'], False)
        self.assertIn('--z-metres', argv)
        self.assertNotIn('--classified-background-zero', argv)
        with self.assertRaisesRegex(ValueError, 'z_unit'):
            self.module.run_arguments(dict(BASELINE, z_unit='feet'), 'l', 'o', ['a.las'], False)

    def test_parameter_differences_name_only_changed_keys(self):
        product = dict(BASELINE, source_id='other', classified_background_zero=True, tile_size=200.0)
        diff = self.module.parameter_differences(BASELINE, product)
        self.assertEqual(set(diff), {'source_id', 'classified_background_zero'})
        self.assertFalse(set(diff) & set(self.module.MATCHED))


if __name__ == '__main__':
    unittest.main()
