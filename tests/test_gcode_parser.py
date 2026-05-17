import unittest

from RouterKing.gcode.parser import filter_spindle_commands, iter_gcode_lines, parse_gcode, prepare_stream_lines


class TestGcodeParser(unittest.TestCase):
    def test_iter_gcode_lines_strips_comments(self):
        text = "G0 X0 Y0 (comment)\n; full line comment\n\nG1 X1 Y1"
        self.assertEqual(list(iter_gcode_lines(text)), ["G0 X0 Y0", "G1 X1 Y1"])

    def test_parse_gcode_segments(self):
        text = "G0 X0 Y0\nG1 X1 Y0\nG1 X1 Y1"
        path = parse_gcode(text)
        self.assertEqual(len(path.segments), 2)
        self.assertEqual(len(path.segments_3d), 2)
        self.assertEqual(path.segments, [(0.0, 0.0, 1.0, 0.0, False), (1.0, 0.0, 1.0, 1.0, False)])

    def test_parse_gcode_arc(self):
        text = "G0 X0 Y0\nG2 X1 Y0 I0.5 J0"
        path = parse_gcode(text)
        self.assertTrue(len(path.segments) >= 8)

    def test_parse_gcode_3d_segments_keep_z_only_moves(self):
        text = "; header\nG0 X0 Y0 Z5 F1000\n\nG1 Z-1 F120\nG1 X2 Y3"
        path = parse_gcode(text)

        self.assertEqual(len(path.segments), 1)
        self.assertEqual(len(path.segments_3d), 3)
        self.assertIs(path.segments3d, path.segments_3d)

        rapid = path.segments_3d[0]
        self.assertEqual((rapid.x0, rapid.y0, rapid.z0), (0.0, 0.0, 0.0))
        self.assertEqual((rapid.x1, rapid.y1, rapid.z1), (0.0, 0.0, 5.0))
        self.assertTrue(rapid.rapid)
        self.assertFalse(rapid.feed)
        self.assertEqual(rapid.feedrate, 1000.0)
        self.assertEqual(rapid.line_number, 2)

        plunge = path.segments_3d[1]
        self.assertEqual((plunge.x0, plunge.y0, plunge.z0), (0.0, 0.0, 5.0))
        self.assertEqual((plunge.x1, plunge.y1, plunge.z1), (0.0, 0.0, -1.0))
        self.assertFalse(plunge.rapid)
        self.assertTrue(plunge.feed)
        self.assertEqual(plunge.feedrate, 120.0)
        self.assertEqual(plunge.line_number, 4)

        xy_feed = path.segments_3d[2]
        self.assertEqual((xy_feed.x1, xy_feed.y1, xy_feed.z1), (2.0, 3.0, -1.0))
        self.assertEqual(xy_feed.feedrate, 120.0)
        self.assertEqual(xy_feed.line_number, 5)

    def test_parse_gcode_arc_interpolates_z_in_3d_segments(self):
        text = "G0 X0 Y0 Z0\nG1 F300\nG2 X1 Y0 Z-1 I0.5 J0"
        path = parse_gcode(text)

        self.assertTrue(len(path.segments_3d) >= 8)
        self.assertTrue(all(segment.line_number == 3 for segment in path.segments_3d))
        self.assertTrue(all(segment.feedrate == 300.0 for segment in path.segments_3d))
        self.assertAlmostEqual(path.segments_3d[-1].z1, -1.0)

    def test_filter_spindle_commands_for_dry_run(self):
        lines, removed = prepare_stream_lines("M3 S18000\nG1 X1\nM5", dry_run=True)
        self.assertEqual(lines, ["G1 X1"])
        self.assertEqual(removed, ["M3 S18000", "M5"])

    def test_filter_spindle_commands_keeps_non_spindle_m_codes(self):
        lines, removed = filter_spindle_commands(["M30", "G1 X1", "M4 S400"])
        self.assertEqual(lines, ["M30", "G1 X1"])
        self.assertEqual(removed, ["M4 S400"])


if __name__ == "__main__":
    unittest.main()
