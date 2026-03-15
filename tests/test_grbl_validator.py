import unittest

from RouterKing.grbl.validator import (
    calculate_g54_offset,
    resolve_machine_limits,
    validate_gcode,
)


PROFILE = {
    "settings": {
        "$110": "2000",
        "$111": "2000",
        "$112": "500",
        "$130": "300",
        "$131": "380",
        "$132": "50",
        "$23": "3",
        "$27": "3",
        "$32": "0",
    },
    "work_offset": {"x": -297.0, "y": -377.0, "z": -3.0},
    "work_position": {"x": 0.0, "y": 0.0, "z": 0.0},
    "capabilities": {
        "spindle_supported": False,
        "coolant_supported": False,
        "laser_mode": False,
    },
}

STATUS = {"WCO": "-297.000,-377.000,-3.000", "WPos": "0.000,0.000,0.000"}


class TestGrblValidator(unittest.TestCase):
    def test_valid_program(self):
        gcode = "G90 G21\nG1 X-1 Y-1 Z-1 F300\nG1 X-2 Y-2 Z-1 F300"
        report = validate_gcode(
            gcode,
            machine_profile=PROFILE,
            grbl_settings=PROFILE["settings"],
            status=STATUS,
        )
        self.assertTrue(report["valid"])
        self.assertEqual(report["errors"], [])
        self.assertGreaterEqual(report["move_count"], 2)
        self.assertGreaterEqual(report["estimated_time_seconds"], 0)
        self.assertAlmostEqual(report["bounding_box"]["x"][1], 0.0)

    def test_rejects_limit_violation(self):
        gcode = "G90 G21\nG1 Z11 F300"
        report = validate_gcode(
            gcode,
            machine_profile=PROFILE,
            grbl_settings=PROFILE["settings"],
            status=STATUS,
        )
        self.assertFalse(report["valid"])
        self.assertEqual(report["errors"][0]["line"], 2)
        self.assertIn("Z=", report["errors"][0]["reason"])

    def test_rejects_missing_or_zero_feed(self):
        gcode = "G90 G21\nG1 X1\nG1 X2 F0"
        report = validate_gcode(
            gcode,
            machine_profile=PROFILE,
            grbl_settings=PROFILE["settings"],
            status=STATUS,
        )
        self.assertFalse(report["valid"])
        reasons = [item["reason"] for item in report["errors"]]
        self.assertTrue(any("Missing feed rate" in reason for reason in reasons))
        self.assertTrue(any("F0/negative feed" in reason for reason in reasons))

    def test_rejects_unsupported_machine_commands(self):
        gcode = "M3 S1000\nM7\nG1 X-1 F200"
        report = validate_gcode(
            gcode,
            machine_profile=PROFILE,
            grbl_settings=PROFILE["settings"],
            status=STATUS,
        )
        self.assertFalse(report["valid"])
        reasons = [item["reason"] for item in report["errors"]]
        self.assertTrue(any("M3" in reason for reason in reasons))
        self.assertTrue(any("M7" in reason for reason in reasons))

    def test_calculate_offset_success_and_command(self):
        limits, _ = resolve_machine_limits(PROFILE, PROFILE["settings"])
        result = calculate_g54_offset(
            bounding_box={"x": [0.0, 100.0], "y": [0.0, 120.0], "z": [-10.0, 0.0]},
            limits=limits,
            current_machine_position={"x": -150.0, "y": -200.0, "z": -10.0},
            desired_workpiece_corner={
                "machine": {"x": -250.0, "y": -300.0, "z": -20.0},
                "x_mode": "min",
                "y_mode": "min",
                "z_mode": "max",
            },
            safety_margin_mm=5.0,
        )
        self.assertTrue(result["fits"])
        self.assertIn("G10 L20 P1", result["g10_command"])

    def test_calculate_offset_no_fit(self):
        limits, _ = resolve_machine_limits(PROFILE, PROFILE["settings"])
        result = calculate_g54_offset(
            bounding_box={"x": [0.0, 400.0], "y": [0.0, 100.0], "z": [-10.0, 0.0]},
            limits=limits,
            safety_margin_mm=5.0,
        )
        self.assertFalse(result["fits"])
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
