import os
import tempfile
import unittest

from RouterKing.cam.dxf_import import load_dxf_paths
from RouterKing.cam.simple_engine import SimpleJobSettings, generate_gcode_from_paths


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
