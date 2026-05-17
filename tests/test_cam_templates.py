"""Tests for simple CAM template generation."""

import unittest

from RouterKing.cam.templates import (
    GcodeProgram,
    RECTANGLE_POCKET_PRESETS,
    TemplateSpec,
    rectangle_pocket,
    rectangle_pocket_preset,
    square_pocket,
)


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
        self.assertEqual(program.lines[:8], [
            "; RouterKing rectangle pocket template",
            "; size: 40 x 40 x 5 mm",
            "; tool: 3 mm",
            "; start: X0 Y0",
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

    def test_rectangle_pocket_header_uses_name_and_offsets_local_xy_moves(self):
        spec = self._forty_mm_spec()
        spec.name = "Offset Test"
        spec.start_x = 10.0
        spec.start_y = 20.0

        program = rectangle_pocket(spec)

        self.assertEqual(program.lines[0], "; RouterKing rectangle pocket template: Offset Test")
        self.assertIn("; start: X10 Y20", program.lines)
        self.assertIn("G0 X-8.5 Y1.5", program.lines)
        self.assertIn("G1 X28.5 Y1.5 F500", program.lines)
        self.assertIn("G1 X28.5 Y38.5 F500", program.lines)
        self.assertEqual(program.lines[-2:], ["G0 X10 Y20", "M2"])

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

    def test_tee_tablett_preset_is_named_and_available_as_fresh_spec(self):
        self.assertIn("tee_tablett", RECTANGLE_POCKET_PRESETS)

        direct = RECTANGLE_POCKET_PRESETS["tee_tablett"]
        first = rectangle_pocket_preset("Tee-Tablett")
        second = rectangle_pocket_preset("tee_tablett")
        direct.width = 20.0
        first.width = 10.0

        self.assertEqual(RECTANGLE_POCKET_PRESETS["tee_tablett"].width, 230.0)
        self.assertEqual(second.name, "Tee-Tablett Pocket002 bottom-up 230 x 160 x 4 mm")
        self.assertEqual(second.width, 230.0)
        self.assertEqual(second.height, 160.0)
        self.assertEqual(second.depth, 4.0)
        self.assertEqual(second.tool_diameter, 3.0)
        self.assertEqual(second.step_down, 1.0)
        self.assertEqual(second.step_over, 1.05)
        self.assertEqual(second.feed_rate, 800.0)
        self.assertEqual(second.plunge_rate, 300.0)
        self.assertEqual(second.safe_z, 6.0)
        self.assertEqual(second.origin, "center")

        program = rectangle_pocket(second)

        self.assertEqual(
            program.lines[0],
            "; RouterKing rectangle pocket template: Tee-Tablett Pocket002 bottom-up 230 x 160 x 4 mm",
        )
        self.assertIn("G0 X-113.5 Y-78.5", program.lines)

    def test_preset_accepts_overrides(self):
        spec = rectangle_pocket_preset("tee tablett", start_x=25.0, start_y=30.0)
        program = rectangle_pocket(spec)

        self.assertEqual(spec.start_x, 25.0)
        self.assertEqual(spec.start_y, 30.0)
        self.assertIn("; start: X25 Y30", program.lines)
        self.assertIn("G0 X-88.5 Y-48.5", program.lines)

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
            {"start_x": "left"},
            {"start_y": None},
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
