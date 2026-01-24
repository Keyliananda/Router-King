import unittest

from RouterKing.ai.cam_analysis import analyze_gcode


class TestCamAnalysis(unittest.TestCase):
    def test_cam_analysis_finds_risks(self):
        text = "\n".join(
            [
                "G21",
                "G0 X0 Y0 Z5",
                "G1 Z0 F100",
                "G2 X10 Y0 I0.1 J0",
                "G0 X20 Y0",
            ]
        )
        result = analyze_gcode(text)
        messages = [issue.message.lower() for issue in result.issues]
        self.assertTrue(any("radius" in message for message in messages))
        self.assertTrue(any("rapid move" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
