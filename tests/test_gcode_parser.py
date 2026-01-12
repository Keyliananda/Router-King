import unittest

from RouterKing.gcode.parser import iter_gcode_lines, parse_gcode


class TestGcodeParser(unittest.TestCase):
    def test_iter_gcode_lines_strips_comments(self):
        text = "G0 X0 Y0 (comment)\n; full line comment\n\nG1 X1 Y1"
        self.assertEqual(list(iter_gcode_lines(text)), ["G0 X0 Y0", "G1 X1 Y1"])

    def test_parse_gcode_segments(self):
        text = "G0 X0 Y0\nG1 X1 Y0\nG1 X1 Y1"
        path = parse_gcode(text)
        self.assertEqual(len(path.segments), 2)

    def test_parse_gcode_arc(self):
        text = "G0 X0 Y0\nG2 X1 Y0 I0.5 J0"
        path = parse_gcode(text)
        self.assertTrue(len(path.segments) >= 8)


if __name__ == "__main__":
    unittest.main()
