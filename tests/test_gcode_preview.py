import unittest

from RouterKing.ui.gcode_preview import (
    parse_gcode_preview,
    preview_items,
    project_point,
    projected_bounds,
    segment_color,
    z_color,
)


class TestGcodePreview(unittest.TestCase):
    def test_parse_linear_3d_segments_and_bounds(self):
        path = parse_gcode_preview(
            "\n".join(
                [
                    "G90 G21",
                    "G0 X0 Y0 Z5",
                    "G1 X10 Y0 Z-1",
                    "G1 X10 Y5",
                    "G91",
                    "G1 X-2 Z-2",
                ]
            )
        )

        self.assertEqual(len(path.segments), 4)
        self.assertTrue(path.segments[0].rapid)
        self.assertFalse(path.segments[1].rapid)
        self.assertEqual(path.segments[-1].end.x, 8.0)
        self.assertEqual(path.segments[-1].end.y, 5.0)
        self.assertEqual(path.segments[-1].end.z, -3.0)
        self.assertEqual(path.bounds.min_x, 0.0)
        self.assertEqual(path.bounds.max_x, 10.0)
        self.assertEqual(path.bounds.min_y, 0.0)
        self.assertEqual(path.bounds.max_y, 5.0)
        self.assertEqual(path.bounds.min_z, -3.0)
        self.assertEqual(path.bounds.max_z, 5.0)

    def test_units_are_normalized_to_millimeters(self):
        path = parse_gcode_preview("G20 G90\nG1 X1 Y0.5 Z-0.25")

        segment = path.segments[0]
        self.assertAlmostEqual(segment.end.x, 25.4)
        self.assertAlmostEqual(segment.end.y, 12.7)
        self.assertAlmostEqual(segment.end.z, -6.35)

    def test_helical_arc_interpolates_z_and_bounds(self):
        path = parse_gcode_preview(
            "G90 G21\nG0 X0 Y0 Z0\nG2 X10 Y0 Z-2 I5 J0",
        )

        arc_segments = [segment for segment in path.segments if segment.motion == "G2"]
        self.assertGreaterEqual(len(arc_segments), 8)
        self.assertAlmostEqual(arc_segments[-1].end.x, 10.0, places=6)
        self.assertAlmostEqual(arc_segments[-1].end.y, 0.0, places=6)
        self.assertAlmostEqual(arc_segments[-1].end.z, -2.0, places=6)
        self.assertAlmostEqual(path.bounds.min_z, -2.0)
        self.assertAlmostEqual(path.bounds.max_z, 0.0)

    def test_radius_arc_is_segmented(self):
        path = parse_gcode_preview("G90 G21\nG0 X0 Y0\nG3 X10 Y0 R5")

        arc_segments = [segment for segment in path.segments if segment.motion == "G3"]
        self.assertGreaterEqual(len(arc_segments), 8)
        self.assertAlmostEqual(arc_segments[-1].end.x, 10.0, places=6)
        self.assertAlmostEqual(arc_segments[-1].end.y, 0.0, places=6)

    def test_projections_and_projected_bounds(self):
        path = parse_gcode_preview("G90\nG0 X0 Y0 Z3\nG1 X2 Y4 Z-1")
        point = path.segments[-1].end

        self.assertEqual(project_point(point, "top"), (2.0, -4.0))
        self.assertEqual(project_point(point, "side"), (2.0, 1.0))
        self.assertEqual(project_point(point, "front"), (4.0, 1.0))
        self.assertEqual(project_point(point, "iso"), (-2.0, 4.0))
        self.assertEqual(projected_bounds(path, "top"), (0.0, -4.0, 2.0, -0.0))

    def test_preview_items_include_projection_color_and_motion_metadata(self):
        path = parse_gcode_preview("G90\nG0 X0 Y0 Z2\nG1 X1 Y0 Z-2")
        items = preview_items(path, "side")

        self.assertEqual(items[0]["line"], (0.0, -0.0, 0.0, -2.0))
        self.assertEqual(items[0]["color"], (150, 150, 150))
        self.assertTrue(items[0]["rapid"])
        self.assertEqual(items[1]["motion"], "G1")
        self.assertFalse(items[1]["rapid"])

    def test_z_color_maps_bounds_and_constant_z(self):
        path = parse_gcode_preview("G90\nG0 Z5\nG1 X1 Z-5")

        self.assertEqual(z_color(-5, path.bounds), (0, 90, 220))
        self.assertEqual(z_color(5, path.bounds), (235, 130, 35))
        self.assertEqual(segment_color(path.segments[0], path.bounds), (150, 150, 150))

        flat = parse_gcode_preview("G90\nG1 X1 Z0")
        self.assertEqual(z_color(0, flat.bounds), (118, 110, 128))


if __name__ == "__main__":
    unittest.main()
