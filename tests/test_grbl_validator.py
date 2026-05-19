import unittest

from RouterKing.grbl.validator import (
    calculate_g54_offset,
    merge_machine_profile,
    parse_grbl_coordinate_parameters_lines,
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

    def test_status_wco_overrides_stale_profile_offset(self):
        stale_profile = dict(PROFILE)
        stale_profile["work_offset"] = {"x": -297.0, "y": -347.0, "z": -3.0}
        status = {
            "MPos": "-297.000,-377.000,-3.000",
            "WCO": "-150.000,-190.000,-25.238",
        }
        gcode = "G90 G21\nG54\nG0 Z9\nG0 X112.5 Y-67\nG1 Z-2 F300"
        report = validate_gcode(
            gcode,
            machine_profile=stale_profile,
            grbl_settings=PROFILE["settings"],
            status=status,
        )

        self.assertTrue(report["valid"])
        self.assertEqual(report["offset_source"], "status.WCO")
        self.assertEqual(report["work_offset"], {"x": -150.0, "y": -190.0, "z": -25.238})

    def test_homing_dir_mask_bits_mean_negative_search_direction(self):
        profile = merge_machine_profile(
            {},
            settings={"$22": "1", "$23": "3", "$27": "3", "$130": "300", "$131": "380", "$132": "50"},
            status={},
        )

        self.assertEqual(profile["homing"]["directions"]["x"], "negative")
        self.assertEqual(profile["homing"]["directions"]["y"], "negative")
        self.assertEqual(profile["homing"]["directions"]["z"], "positive")

    def test_merge_machine_profile_does_not_persist_runtime_positions(self):
        profile = merge_machine_profile(
            {
                "home_position_mpos": {"x": -215.2, "y": -295.675, "z": -48.144},
                "machine_position": {"x": -215.2, "y": -295.675, "z": -48.144},
                "work_position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "settings": {"$130": "400", "$131": "400", "$132": "60"},
            },
            settings={"$22": "1", "$23": "3", "$27": "3", "$130": "400", "$131": "400", "$132": "60"},
            status={
                "state": "Idle",
                "MPos": "-297.000,-377.000,-3.000",
                "WPos": "0.000,0.000,0.000",
                "WCO": "-297.000,-377.000,-3.000",
                "FS": "0,0",
            },
        )

        self.assertNotIn("home_position_mpos", profile)
        self.assertNotIn("machine_position", profile)
        self.assertNotIn("work_position", profile)
        self.assertEqual(profile["status"], {"state": "Idle", "WCO": "-297.000,-377.000,-3.000"})
        self.assertEqual(profile["work_offset"], {"x": -297.0, "y": -377.0, "z": -3.0})

    def test_resolve_machine_limits_prefers_current_settings_over_stale_profile_limits(self):
        profile = {
            "machine_limits": {"x": [-300.0, 0.0], "y": [-380.0, 0.0], "z": [-50.0, 0.0]},
            "work_envelope_mm": {"x": 300.0, "y": 380.0, "z": 50.0},
        }
        settings = {"$130": "400.000", "$131": "400.000", "$132": "60.000"}

        limits, source = resolve_machine_limits(profile, settings)

        self.assertEqual(limits, {"x": (-400.0, 0.0), "y": (-400.0, 0.0), "z": (-60.0, 0.0)})
        self.assertEqual(source, "grbl_$$")

    def test_parse_coordinate_parameters_reports_effective_g54_wco(self):
        parsed = parse_grbl_coordinate_parameters_lines(
            [
                "[G54:-150.000,-190.000,-25.000]",
                "[G92:1.000,2.000,3.000]",
                "[TLO:0.250]",
                "[PRB:-1.000,-2.000,-3.000:1]",
                "ok",
            ]
        )

        self.assertEqual(parsed["coordinate_systems"]["G54"], {"x": -150.0, "y": -190.0, "z": -25.0})
        self.assertEqual(parsed["work_offset"], {"x": -149.0, "y": -188.0, "z": -21.75})

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

    def test_rejects_probe_cycle_commands_in_streaming_gcode(self):
        gcode = "G90 G21\nG38.2 Z-20 F50\nG1 X-1 F200"
        report = validate_gcode(
            gcode,
            machine_profile=PROFILE,
            grbl_settings=PROFILE["settings"],
            status=STATUS,
        )
        self.assertFalse(report["valid"])
        reasons = [item["reason"] for item in report["errors"]]
        self.assertTrue(any("G38.x" in reason for reason in reasons))

    def test_rejects_setup_and_homing_commands_in_streaming_gcode(self):
        gcode = "G90 G21\nG10 L20 P1 X0\nG28\nG30\n$H\nG1 X-1 F200"
        report = validate_gcode(
            gcode,
            machine_profile=PROFILE,
            grbl_settings=PROFILE["settings"],
            status=STATUS,
        )

        self.assertFalse(report["valid"])
        reasons = [item["reason"] for item in report["errors"]]
        self.assertTrue(any("G10" in reason for reason in reasons))
        self.assertTrue(any("G28" in reason for reason in reasons))
        self.assertTrue(any("G30" in reason for reason in reasons))
        self.assertTrue(any("Homing" in reason for reason in reasons))

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
