"""Tests for simple CAM template generation."""

import unittest

from RouterKing.cam.templates import GcodeProgram, TemplateSpec, rectangle_pocket, square_pocket


class TestPocketTemplates(unittest.TestCase):
    def _forty_mm_spec(self):
        return TemplateSpec(
            width=40.0,
            height=40.0,
            depth=5.0,
            tool_diameter=3.0,
            step_down=2.0,
            step_over=1.5,
            feed_rate=500.0,
            plunge_rate=120.0,
            safe_z=5.0,
            start_z=0.0,
            origin="center",
        )

    def test_rectangle_pocket_generates_local_grbl_program_for_40mm_pocket(self):
        spec = self._forty_mm_spec()
        program = rectangle_pocket(spec)

        self.assertIsInstance(program, GcodeProgram)
        self.assertEqual(program.template, "rectangle_pocket")
        self.assertEqual(program.spec, spec)
        self.assertEqual(program.lines[:7], [
            "; RouterKing rectangle pocket template",
            "; size: 40 x 40 x 5 mm",
            "; tool: 3 mm",
            "G21",
            "G90",
            "G17",
            "G0 Z5",
        ])
        self.assertIn("G1 Z-2 F120", program.lines)
        self.assertIn("G1 Z-4 F120", program.lines)
        self.assertIn("G1 Z-5 F120", program.lines)
        self.assertIn("G0 X-18.5 Y-18.5", program.lines)
        self.assertIn("G1 X18.5 Y-18.5 F500", program.lines)
        self.assertIn("G1 X18.5 Y18.5 F500", program.lines)
        self.assertEqual(program.lines[-2:], ["G0 X0 Y0", "M2"])
        self.assertEqual(str(program), program.text)
        self.assertEqual(program.gcode, program.text)

    def test_square_pocket_accepts_size_keyword(self):
        program = square_pocket(
            size=40.0,
            depth=5.0,
            tool_diameter=3.0,
            step_down=2.0,
            step_over=1.5,
            feed_rate=500.0,
            plunge_rate=120.0,
            safe_z=5.0,
        )

        self.assertEqual(program.template, "square_pocket")
        self.assertEqual(program.spec.width, 40.0)
        self.assertEqual(program.spec.height, 40.0)
        self.assertEqual(program.lines[0], "; RouterKing square pocket template")

    def test_square_pocket_uses_width_as_size_when_height_is_omitted(self):
        program = square_pocket(
            width=40.0,
            depth=5.0,
            tool_diameter=3.0,
            step_down=2.0,
            step_over=1.5,
            feed_rate=500.0,
            plunge_rate=120.0,
            safe_z=5.0,
        )

        self.assertEqual(program.spec.width, 40.0)
        self.assertEqual(program.spec.height, 40.0)

    def test_lower_left_origin_stays_in_positive_xy(self):
        spec = self._forty_mm_spec()
        spec.origin = "lower_left"
        program = rectangle_pocket(spec)

        self.assertIn("G0 X1.5 Y1.5", program.lines)
        self.assertIn("G1 X38.5 Y1.5 F500", program.lines)
        self.assertIn("G1 X38.5 Y38.5 F500", program.lines)

    def test_program_omits_coordinate_setup_and_probe_commands(self):
        program = rectangle_pocket(self._forty_mm_spec())
        text = program.text.upper()

        for forbidden in ("$H", "G10", "G38", "G53", "G54", "G55", "G56", "G57", "G58", "G59"):
            self.assertNotIn(forbidden, text)

    def test_rejects_invalid_values(self):
        cases = [
            {"width": 0.0},
            {"height": -1.0},
            {"depth": 0.0},
            {"tool_diameter": 0.0},
            {"step_down": 0.0},
            {"step_over": 4.0},
            {"feed_rate": 0.0},
            {"plunge_rate": -10.0},
            {"safe_z": 0.0},
            {"tool_diameter": 41.0},
            {"origin": "g54"},
        ]

        for overrides in cases:
            spec = self._forty_mm_spec()
            for name, value in overrides.items():
                setattr(spec, name, value)
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    rectangle_pocket(spec)

    def test_square_pocket_requires_equal_sides(self):
        spec = self._forty_mm_spec()
        spec.height = 30.0

        with self.assertRaises(ValueError):
            square_pocket(spec)

    def test_rejects_mixed_spec_and_keyword_arguments(self):
        with self.assertRaises(TypeError):
            rectangle_pocket(self._forty_mm_spec(), width=10.0)


if __name__ == "__main__":
    unittest.main()
