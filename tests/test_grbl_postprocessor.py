import unittest

from RouterKing.grbl.postprocessor import postprocess_gcode


PROFILE = {
    "settings": {
        "$110": "2000",
        "$111": "2000",
        "$112": "500",
        "$130": "300",
        "$131": "380",
        "$132": "50",
        "$27": "3",
        "$32": "0",
    },
    "work_offset": {"x": -297.0, "y": -377.0, "z": -3.0},
    "capabilities": {
        "spindle_supported": False,
        "coolant_supported": False,
        "laser_mode": False,
    },
}


class TestGrblPostprocessor(unittest.TestCase):
    def test_adds_header_and_program_end(self):
        raw = "G1 X10\nG1 X20 F0\n"
        result = postprocess_gcode(raw, machine_profile=PROFILE, grbl_settings=PROFILE["settings"], feed_rate=600.0)
        gcode = result["gcode"]
        self.assertTrue(gcode.startswith("G90 G21 G17\n"))
        self.assertIn("G0 Z-5", gcode)
        self.assertIn("G1 X10 F600", gcode)
        self.assertTrue(gcode.strip().endswith("M2"))
        self.assertGreaterEqual(result["injected_feed_count"], 1)
        self.assertGreaterEqual(result["replaced_f0_count"], 1)

    def test_strips_unsupported_m_codes(self):
        raw = "M3 S12000\nM7\nG1 X5 F500\nM5\n"
        result = postprocess_gcode(raw, machine_profile=PROFILE, grbl_settings=PROFILE["settings"], feed_rate=500.0)
        gcode = result["gcode"]
        self.assertNotIn("M3", gcode)
        self.assertNotIn("M5", gcode)
        self.assertNotIn("M7", gcode)
        self.assertIn("G1 X5 F500", gcode)
        self.assertGreaterEqual(len(result["removed_commands"]), 2)

    def test_clamps_unsafe_positive_z(self):
        raw = "G90\nG0 Z11\nG1 Z-1 F200\n"
        result = postprocess_gcode(raw, machine_profile=PROFILE, grbl_settings=PROFILE["settings"])
        gcode = result["gcode"]
        self.assertNotIn("Z11", gcode)
        self.assertIn("Z-5", gcode)
        self.assertGreaterEqual(result["clamped_z_count"], 1)


if __name__ == "__main__":
    unittest.main()
