"""Coloring contracts; ArcPy is replaced only at the I/O boundary."""

import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import assign_polygon_colors as coloring


class ColoringTests(unittest.TestCase):
    def test_adjacent_polygons_get_distinct_positive_integer_ids(self):
        adjacency = coloring.build_adjacency([(1, 2), (2, 3), (3, 1)])
        colors = coloring.assign_polygon_colors(adjacency)
        self.assertEqual(set(colors.values()), {1, 2, 3})
        self.assertTrue(all(type(value) is int for value in colors.values()))
        for polygon, neighbors in adjacency.items():
            for neighbor in neighbors:
                self.assertNotEqual(colors[polygon], colors[neighbor])

    def test_a_polygon_listed_as_its_own_neighbor_is_ignored(self):
        adjacency = coloring.build_adjacency([(1, 1), (1, 2)])
        self.assertEqual(adjacency, {1: {2}, 2: {1}})

    def test_exhausted_color_limit_fails_before_writing(self):
        adjacency = coloring.build_adjacency([(1, 2), (2, 3), (3, 1)])
        with self.assertRaises(ValueError):
            coloring.assign_polygon_colors(adjacency, max_colors=2)

    def test_invalid_limits_are_rejected(self):
        for limit in (0, -1, 32768):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                coloring.assign_polygon_colors({1: set()}, max_colors=limit)

    def test_empty_graph_and_isolated_polygon(self):
        self.assertEqual(coloring.assign_polygon_colors({}), {})
        self.assertEqual(coloring.assign_polygon_colors({42: set()}), {42: 1})

    def test_cli_preserves_existing_field_name_and_nine_color_default(self):
        with patch('sys.argv', ['assign_polygon_colors.py', 'polygons', 'neighbors']):
            args = coloring.parse_args()
        self.assertEqual(args.color_field, 'Color_ID')
        self.assertEqual(args.max_colors, 9)
        self.assertEqual(args.id_field, 'OID@')


class LayerTests(unittest.TestCase):
    def setUp(self):
        self.rows = [[1, None], [2, None], [3, None]]
        self.updates = []
        self.api = MagicMock()
        self.api.ListFields.return_value = [
            SimpleNamespace(name='Color_ID', type='SmallInteger')
        ]
        cursor = self.api.da.UpdateCursor.return_value.__enter__.return_value
        cursor.__iter__.side_effect = lambda: iter(self.rows)
        cursor.updateRow.side_effect = lambda row: self.updates.append(list(row))
        self.patch = patch.object(coloring, 'arcpy', self.api)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_existing_integer_field_is_written_once_per_polygon(self):
        # Exercise main so the rescued writer's duplicate pass is observable.
        with patch.object(coloring, 'parse_args', return_value=SimpleNamespace(
            polygon_layer='polygons', neighbor_table='neighbors',
            color_field='Color_ID', id_field='OBJECTID', max_colors=9,
            dry_run=False,
        )), patch.object(coloring, 'read_neighbor_rows', return_value=[(1, 2)]):
            self.api.da.SearchCursor.return_value.__enter__.return_value.__iter__.return_value = iter([(1,), (2,), (3,)])
            with contextlib.redirect_stdout(io.StringIO()):
                coloring.main()
        self.assertEqual(self.updates, [[1, 1], [2, 2], [3, 1]])
        self.api.AddField_management.assert_not_called()

    def test_writer_reads_the_objectid_token_by_default(self):
        self.api.ListFields.return_value = []
        coloring.write_colors_to_layer('polygons', {1: 1, 2: 2, 3: 1}, 'Color_ID')
        self.assertEqual(self.api.da.UpdateCursor.call_args.args, ('polygons', ['OID@', 'Color_ID']))

    def test_missing_field_is_created_as_short_integer(self):
        self.api.ListFields.return_value = []
        coloring.write_colors_to_layer('polygons', {1: 1, 2: 2, 3: 1}, 'Color_ID')
        self.assertEqual(self.api.AddField_management.call_args.args, ('polygons', 'Color_ID', 'SHORT'))
        self.assertEqual(self.updates, [[1, 1], [2, 2], [3, 1]])

    def test_incompatible_field_is_rejected_without_writing(self):
        for field_type in ('String', 'Double', 'OID'):
            with self.subTest(field_type=field_type):
                self.api.ListFields.return_value = [SimpleNamespace(name='Color_ID', type=field_type)]
                with self.assertRaisesRegex(ValueError, 'integer'):
                    coloring.write_colors_to_layer('polygons', {1: 1}, 'Color_ID')
        self.api.da.UpdateCursor.assert_not_called()
        self.api.AddField_management.assert_not_called()

    def test_field_lookup_is_case_insensitive(self):
        self.api.ListFields.return_value = [SimpleNamespace(name='COLOR_ID', type='Integer')]
        coloring.write_colors_to_layer('polygons', {1: 1, 2: 2, 3: 1}, 'Color_ID')
        self.api.AddField_management.assert_not_called()
        self.assertEqual(len(self.updates), 3)

    def test_missing_assignment_is_rejected_instead_of_silently_colored(self):
        with self.assertRaisesRegex(ValueError, 'assignment'):
            coloring.write_colors_to_layer('polygons', {1: 1}, 'Color_ID')

    def test_dry_run_includes_isolated_polygons_and_does_not_write(self):
        self.api.da.SearchCursor.return_value.__enter__.return_value.__iter__.return_value = iter([(1,), (2,), (3,)])
        output = io.StringIO()
        with patch('sys.argv', ['assign_polygon_colors.py', 'polygons', 'neighbors', '--dry-run']), patch.object(coloring, 'read_neighbor_rows', return_value=[(1, 2)]), contextlib.redirect_stdout(output):
            coloring.main()
        self.assertIn('3: 1', output.getvalue())
        self.api.da.UpdateCursor.assert_not_called()
        self.api.AddField_management.assert_not_called()


if __name__ == '__main__':
    unittest.main()
