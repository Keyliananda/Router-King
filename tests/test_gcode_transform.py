import unittest

from RouterKing.gcode import prepare_air_run_gcode, prepare_air_run_lines


class TestGcodeTransform(unittest.TestCase):
    def test_air_run_strips_comments_and_removes_spindle_commands(self):
        text = "\n".join(
            [
                "M3 S18000 ; start spindle",
                "G1 X1 Y1 (cut)",
                "M4 S400",
                "M5",
            ]
        )

        self.assertEqual(prepare_air_run_lines(text), ["G1 X1 Y1"])

    def test_air_run_clamps_absolute_z_below_air_z(self):
        lines = prepare_air_run_lines(
            "\n".join(
                [
                    "G90 G21",
                    "G1 Z-2 F200",
                    "G1 X10 Y5 Z-3 F500",
                ]
            ),
            air_z=1.5,
        )

        self.assertEqual(lines[0], "G90 G21")
        self.assertEqual(lines[1], "G1 Z1.5 F200")
        self.assertEqual(lines[2], "G1 X10 Y5 Z1.5 F500")

    def test_air_run_preserves_xy_path_words(self):
        lines = prepare_air_run_lines(
            "\n".join(
                [
                    "G90",
                    "G0 X0 Y0 Z5",
                    "G1 X2.5 Y-1.25 Z-2 F600",
                    "G1 X3 Y4",
                ]
            ),
            air_z=2.0,
        )

        self.assertIn("G1 X2.5 Y-1.25 Z2 F600", lines)
        self.assertIn("G1 X3 Y4", lines)

    def test_air_run_keeps_relative_z_from_dropping_below_air_z(self):
        lines = prepare_air_run_lines(
            "\n".join(
                [
                    "G91",
                    "G1 Z-2 F100",
                    "G1 X1 Y1 Z-1",
                    "G90",
                    "G1 Z-5",
                ]
            ),
            air_z=1.0,
        )

        self.assertEqual(lines[0], "G91")
        self.assertEqual(lines[1], "G1 Z0 F100")
        self.assertEqual(lines[2], "G1 X1 Y1 Z0")
        self.assertEqual(lines[3], "G90")
        self.assertEqual(lines[4], "G1 Z1")

    def test_air_run_gcode_returns_joined_text(self):
        self.assertEqual(
            prepare_air_run_gcode("G90\nM5\nG1 X1 Z-1", air_z=0.5),
            "G90\nG1 X1 Z0.5",
        )

    def test_air_run_collapses_repeated_depth_passes_and_returns_to_start(self):
        lines = prepare_air_run_lines(
            "\n".join(
                [
                    "G90",
                    "G0 Z6",
                    "G0 X0 Y0",
                    "G1 Z-1 F100",
                    "G1 X10 Y0 F500",
                    "G0 Z6",
                    "G0 X0 Y0",
                    "G1 Z-2 F100",
                    "G1 X10 Y0 F500",
                    "G0 Z6",
                    "G0 X5 Y5",
                    "M2",
                ]
            ),
            air_z=3.0,
        )

        self.assertEqual(lines[:-2].count("G0 X0 Y0"), 1)
        self.assertEqual(lines.count("G1 X10 Y0 F500"), 1)
        self.assertEqual(lines[-2:], ["G0 X0 Y0", "M2"])


if __name__ == "__main__":
    unittest.main()
