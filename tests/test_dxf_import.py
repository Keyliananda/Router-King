import os
import tempfile
import unittest

from RouterKing.cam.dxf_import import generate_gcode_from_dxf, load_dxf_paths
from RouterKing.cam.simple_engine import SimpleJobSettings, generate_gcode_from_paths
from RouterKing.ai.actions import execute_actions_for_bridge


class TestDxfImport(unittest.TestCase):
    def test_load_square_dxf(self):
        here = os.path.dirname(__file__)
        dxf_path = os.path.join(here, "test-square.dxf")
        paths = load_dxf_paths(dxf_path)
        self.assertEqual(len(paths), 1)
        points = paths[0]
        self.assertGreaterEqual(len(points), 4)
        self.assertAlmostEqual(points[0][0], 10.0)
        self.assertAlmostEqual(points[0][1], 10.0)
        self.assertAlmostEqual(points[1][0], 60.0)
        self.assertAlmostEqual(points[1][1], 10.0)
        self.assertAlmostEqual(points[2][0], 60.0)
        self.assertAlmostEqual(points[2][1], 60.0)
        self.assertAlmostEqual(points[3][0], 10.0)
        self.assertAlmostEqual(points[3][1], 60.0)

    def test_simple_engine_multipass(self):
        paths = [[(0.0, 0.0), (10.0, 0.0)]]
        settings = SimpleJobSettings(cut_z=-2.0, pass_depth=1.0, safe_z=5.0)
        gcode = generate_gcode_from_paths(paths, settings)
        self.assertIn("Z-1", gcode)
        self.assertIn("Z-2", gcode)

    def test_generate_gcode_from_dxf(self):
        here = os.path.dirname(__file__)
        dxf_path = os.path.join(here, "test-square.dxf")
        settings = SimpleJobSettings(cut_z=-1.0, safe_z=5.0, feed_rate=700.0)
        gcode = generate_gcode_from_dxf(dxf_path, settings)
        self.assertIn("RouterKing simple CAM", gcode)
        self.assertIn("G21", gcode)
        self.assertIn("F700", gcode)

    def test_dxf_generate_gcode_action_returns_structured_data(self):
        here = os.path.dirname(__file__)
        dxf_path = os.path.join(here, "test-square.dxf")
        handle = tempfile.NamedTemporaryFile("w", suffix=".nc", delete=False)
        output_path = handle.name
        handle.close()
        try:
            response = execute_actions_for_bridge(
                [
                    {
                        "type": "dxf_generate_gcode",
                        "dxf_path": dxf_path,
                        "output_path": output_path,
                        "use_freecad": False,
                        "prefer_ezdxf": False,
                        "feed_rate": 700,
                    }
                ]
            )
            self.assertEqual(response["errors"], [])
            self.assertIn("DXF G-code generated", response["messages"][0])
            data = response["data"]
            self.assertEqual(data["engine"], "simple")
            self.assertEqual(data["output_path"], output_path)
            self.assertIn("RouterKing simple CAM", data["gcode"])
            self.assertGreater(data["line_count"], 0)
            self.assertTrue(os.path.exists(output_path))
        finally:
            try:
                os.remove(output_path)
            except OSError:
                pass

    def test_bulge_arc_lwpolyline(self):
        dxf = "\n".join(
            [
                "0",
                "SECTION",
                "2",
                "ENTITIES",
                "0",
                "LWPOLYLINE",
                "90",
                "2",
                "70",
                "0",
                "10",
                "0.0",
                "20",
                "0.0",
                "42",
                "0.41421356",
                "10",
                "10.0",
                "20",
                "0.0",
                "0",
                "ENDSEC",
                "0",
                "EOF",
                "",
            ]
        )
        handle = tempfile.NamedTemporaryFile("w", suffix=".dxf", delete=False)
        try:
            handle.write(dxf)
            handle.close()
            paths = load_dxf_paths(handle.name)
        finally:
            try:
                os.remove(handle.name)
            except OSError:
                pass

        self.assertEqual(len(paths), 1)
        self.assertGreater(len(paths[0]), 2)
        midpoint = paths[0][len(paths[0]) // 2]
        self.assertGreater(abs(midpoint[1]), 0.1)

    def test_spline_points(self):
        dxf = "\n".join(
            [
                "0",
                "SECTION",
                "2",
                "ENTITIES",
                "0",
                "SPLINE",
                "10",
                "0.0",
                "20",
                "0.0",
                "10",
                "5.0",
                "20",
                "10.0",
                "10",
                "10.0",
                "20",
                "0.0",
                "0",
                "ENDSEC",
                "0",
                "EOF",
                "",
            ]
        )
        handle = tempfile.NamedTemporaryFile("w", suffix=".dxf", delete=False)
        try:
            handle.write(dxf)
            handle.close()
            paths = load_dxf_paths(handle.name)
        finally:
            try:
                os.remove(handle.name)
            except OSError:
                pass

        self.assertEqual(len(paths), 1)
        self.assertEqual(len(paths[0]), 3)


if __name__ == "__main__":
    unittest.main()
