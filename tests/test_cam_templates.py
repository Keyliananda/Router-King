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
        self.assertEqual(program.lines[:10], [
            "; RouterKing rectangle pocket template",
            "; size: 40 x 40 x 5 mm",
            "; tool: 3 mm",
            "; axes: normal (CAD X->machine X, CAD Y->machine Y)",
            "; raster: pass_axis=x, path=forward, final_contour=off",
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

    def test_rectangle_pocket_can_swap_xy_axes(self):
        spec = self._forty_mm_spec()
        spec.width = 30.0
        spec.height = 20.0
        spec.swap_xy = True

        program = rectangle_pocket(spec)

        self.assertIn("; axes: swapped (CAD X->machine Y, CAD Y->machine X)", program.lines)
        self.assertIn("G0 X-8.5 Y-13.5", program.lines)
        self.assertIn("G1 X-8.5 Y13.5 F500", program.lines)

    def test_rectangle_pocket_can_rotate_around_machine_z(self):
        spec = self._forty_mm_spec()
        spec.width = 30.0
        spec.height = 20.0
        spec.rotation_z = 90

        program = rectangle_pocket(spec)

        self.assertIn("; axes: normal (CAD X->machine X, CAD Y->machine Y), Z rotation=90deg", program.lines)
        self.assertIn("G0 X8.5 Y-13.5", program.lines)
        self.assertIn("G1 X8.5 Y13.5 F500", program.lines)

    def test_rectangle_pocket_can_choose_y_axis_passes_and_reverse_order(self):
        spec = self._forty_mm_spec()
        spec.pass_axis = "y"
        spec.path_direction = "reverse"

        program = rectangle_pocket(spec)

        self.assertIn("; raster: pass_axis=y, path=reverse, final_contour=off", program.lines)
        self.assertIn("G0 X18.5 Y-18.5", program.lines[:14])
        self.assertIn("G1 X18.5 Y18.5 F500", program.lines)

    def test_rectangle_pocket_can_add_final_contour_pass(self):
        spec = self._forty_mm_spec()
        spec.final_contour = True
        spec.contour_direction = "ccw"

        program = rectangle_pocket(spec)

        self.assertIn("; raster: pass_axis=x, path=forward, final_contour=ccw", program.lines)
        contour_index = program.lines.index("; final contour ccw")
        self.assertGreater(contour_index, program.lines.index("; depth -5"))
        self.assertIn("G1 X-18.5 Y-18.5 F500", program.lines[contour_index + 1:])
        self.assertIn("G1 X18.5 Y18.5 F500", program.lines[contour_index + 1:])

    def test_rectangle_pocket_can_prefer_cut_start_without_moving_geometry(self):
        spec = self._forty_mm_spec()
        spec.cut_start_x = 18.5
        spec.cut_start_y = 18.5

        program = rectangle_pocket(spec)

        self.assertIn("; cut start target: X18.5 Y18.5", program.lines)
        self.assertIn("; start: X0 Y0", program.lines)
        self.assertIn("G0 X18.5 Y18.5", program.lines[:16])
        self.assertEqual(program.lines[-2:], ["G0 X0 Y0", "M2"])

    def test_rectangle_pocket_first_xy_rapid_targets_selected_cut_start(self):
        spec = self._forty_mm_spec()
        spec.cut_start_x = -18.5
        spec.cut_start_y = -18.5

        program = rectangle_pocket(spec)

        first_depth = program.lines.index("; depth -2")
        self.assertEqual(program.lines[first_depth + 1], "G0 X-18.5 Y-18.5")
        self.assertEqual(program.lines[first_depth + 2], "G1 Z-2 F120")
        second_depth = program.lines.index("; depth -4")
        self.assertEqual(program.lines[second_depth + 1], "G0 X-18.5 Y-18.5")

    def test_rectangle_pocket_records_cad_source_in_header(self):
        spec = self._forty_mm_spec()
        spec.source_document = "tee-tablett"
        spec.source_object = "Body"
        spec.source_feature = "Pocket002"

        program = rectangle_pocket(spec)

        self.assertIn("; source: document=tee-tablett, object=Body, feature=Pocket002", program.lines)

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
        self.assertEqual(second.name, "Tee-Tablett Pocket002 bottom-up 230 x 160 x 4 mm, 38 mm cutter")
        self.assertEqual(second.width, 230.0)
        self.assertEqual(second.height, 160.0)
        self.assertEqual(second.depth, 4.0)
        self.assertEqual(second.tool_diameter, 38.0)
        self.assertEqual(second.step_down, 1.0)
        self.assertEqual(second.step_over, 13.3)
        self.assertEqual(second.feed_rate, 800.0)
        self.assertEqual(second.plunge_rate, 300.0)
        self.assertEqual(second.safe_z, 6.0)
        self.assertEqual(second.origin, "center")
        self.assertEqual(second.rotation_z, 90)
        self.assertEqual(second.source_document, "tee-tablett")
        self.assertEqual(second.source_object, "Body")
        self.assertEqual(second.source_feature, "Pocket002")

        program = rectangle_pocket(second)

        self.assertEqual(
            program.lines[0],
            "; RouterKing rectangle pocket template: Tee-Tablett Pocket002 bottom-up 230 x 160 x 4 mm, 38 mm cutter",
        )
        self.assertIn("; tool: 38 mm", program.lines)
        self.assertIn("; axes: normal (CAD X->machine X, CAD Y->machine Y), Z rotation=90deg", program.lines)
        self.assertIn("; source: document=tee-tablett, object=Body, feature=Pocket002", program.lines)
        self.assertIn("G0 X61 Y-96", program.lines)

    def test_preset_accepts_overrides(self):
        spec = rectangle_pocket_preset("tee tablett", start_x=25.0, start_y=30.0)
        program = rectangle_pocket(spec)

        self.assertEqual(spec.start_x, 25.0)
        self.assertEqual(spec.start_y, 30.0)
        self.assertIn("; start: X25 Y30", program.lines)
        self.assertIn("G0 X86 Y-66", program.lines)

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
            {"pass_axis": "z"},
            {"path_direction": "sideways"},
            {"contour_direction": "inside"},
            {"rotation_z": 45},
            {"start_x": "left"},
            {"start_y": None},
            {"cut_start_x": "left", "cut_start_y": 1.0},
            {"cut_start_x": 1.0},
            {"cut_start_y": 1.0},
            {"source_document": 1},
            {"source_object": 1},
            {"source_feature": 1},
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
