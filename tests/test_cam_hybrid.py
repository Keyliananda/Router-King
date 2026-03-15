"""Tests for the hybrid CAM engine, focusing on job creation and error logging."""

import logging
import os
import tempfile
import threading
import unittest
from unittest.mock import ANY, patch

from RouterKing.cam.hybrid import (
    CamJobSettings,
    HybridResult,
    SimpleJobSettings,
    _collect_job_operations,
    _export_gcode,
    _resolve_operation_base,
    _profile_base_for_model,
    _try_create_variants,
    _run_export_variants,
    _assign_job_model,
    generate_hybrid_gcode,
    generate_simple_gcode,
)


class StubModel:
    """Minimal stand-in for a FreeCAD Part object."""

    def __init__(self, name="TestBox"):
        self.Name = name
        self.TypeId = "Part::Box"
        self.Shape = None


class StubJob:
    """Minimal stand-in for a Path::Job object."""

    def __init__(self, name="Job"):
        self.Name = name
        self.Model = []
        self.Base = None
        self.Operations = []


class TestTryCreateVariants(unittest.TestCase):
    """_try_create_variants must try 3-arg, 2-arg, then 1-arg signatures."""

    def test_3_arg_succeeds(self):
        """Create(name, models, template) is the canonical form."""
        calls = []

        def creator(name, models, template):
            calls.append((name, models, template))
            return StubJob(name)

        settings = CamJobSettings(name="TestJob")
        model = StubModel()
        job = _try_create_variants(creator, settings, model, "test")

        self.assertIsNotNone(job)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "TestJob")
        self.assertEqual(calls[0][1], [model])
        self.assertIsNone(calls[0][2])

    def test_falls_back_to_2_arg(self):
        """If 3-arg raises TypeError, try Create(name, models)."""
        calls = []

        def creator(name, models):
            calls.append((name, models))
            return StubJob(name)

        settings = CamJobSettings(name="TestJob")
        model = StubModel()
        job = _try_create_variants(creator, settings, model, "test")

        self.assertIsNotNone(job)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], [model])

    def test_falls_back_to_1_arg(self):
        """If 3-arg and 2-arg raise TypeError, try Create(name)."""
        calls = []

        def creator(name):
            calls.append(name)
            return StubJob(name)

        settings = CamJobSettings(name="TestJob")
        model = StubModel()
        job = _try_create_variants(creator, settings, model, "test")

        self.assertIsNotNone(job)
        self.assertEqual(len(calls), 1)
        # Model should have been assigned via _assign_job_model fallback
        self.assertEqual(job.Model, [model])

    def test_all_fail_returns_none(self):
        """If every signature fails, return None."""

        def creator(*args):
            raise RuntimeError("nope")

        settings = CamJobSettings(name="TestJob")
        job = _try_create_variants(creator, settings, StubModel(), "test")
        self.assertIsNone(job)

    def test_none_model_passes_empty_list(self):
        """When model is None, models list should be []."""
        calls = []

        def creator(name, models, template):
            calls.append(models)
            return StubJob(name)

        settings = CamJobSettings(name="TestJob")
        _try_create_variants(creator, settings, None, "test")

        self.assertEqual(calls[0], [])


class TestRunExportVariants(unittest.TestCase):

    def test_supports_canonical_signature(self):
        calls = []

        def exporter(job, output_path, post_processor):
            calls.append((job, output_path, post_processor))
            return "G1 X0 Y0"

        job = StubJob("ExportJob")
        result = _run_export_variants(exporter, job, "grbl_post", "/tmp/test.nc")
        self.assertEqual(result, "G1 X0 Y0")
        self.assertEqual(len(calls), 1)

    def test_supports_reordered_signature_after_failures(self):
        calls = []

        def exporter(job, post_processor, output_path):
            calls.append((job, post_processor, output_path))
            if post_processor != "grbl_post":
                raise ValueError("wrong post argument")
            if not str(output_path).endswith(".nc"):
                raise ValueError("wrong output argument")
            return "G1 X1 Y1"

        job = StubJob("ExportJob2")
        result = _run_export_variants(exporter, job, "grbl_post", "/tmp/test2.nc")
        self.assertEqual(result, "G1 X1 Y1")
        self.assertGreaterEqual(len(calls), 1)


class TestProfileBaseSelection(unittest.TestCase):

    def test_box_profile_uses_vertical_faces(self):
        class FaceContainer:
            Faces = [object(), object(), object(), object(), object(), object()]

        model = StubModel("TestTeil")
        model.Shape = FaceContainer()
        base = _profile_base_for_model(model)
        self.assertIsInstance(base, list)
        self.assertEqual(len(base), 1)
        self.assertEqual(base[0][0], model)
        self.assertEqual(base[0][1], ["Face1", "Face2", "Face3", "Face4"])

    def test_non_profile_keeps_model_as_base(self):
        model = StubModel("AnyPart")
        base = _resolve_operation_base("pocket", model, None)
        self.assertEqual(base, model)


class TestExportGcode(unittest.TestCase):

    def test_prefers_job_path_togcode_and_writes_output(self):
        class StubPath:
            def toGCode(self):
                return "G90\nG1 X0 Y0"

        class StubJobWithPath:
            Path = StubPath()

        handle, output_path = tempfile.mkstemp(prefix="rk_export_", suffix=".nc")
        os.close(handle)
        try:
            gcode = _export_gcode(StubJobWithPath(), "grbl_post", output_path)
            self.assertIn("G90", gcode)
            with open(output_path, "r", encoding="utf-8") as f:
                written = f.read()
            self.assertEqual(written, gcode)
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)

    def test_fallback_to_operation_paths_when_job_path_empty(self):
        class EmptyPath:
            def toGCode(self):
                return ""

        class OpPath:
            def __init__(self, text):
                self._text = text

            def toGCode(self):
                return self._text

        class Group:
            def __init__(self, out_list):
                self.TypeId = "App::DocumentObjectGroup"
                self.OutList = out_list
                self.Group = out_list

        class Op:
            def __init__(self, name, text):
                self.Name = name
                self.TypeId = "Path::FeaturePython"
                self.Path = OpPath(text)
                self.Base = [("TestTeil", ("Face1", "Face2", "Face3", "Face4"))]

        class StubJobWithOps:
            def __init__(self):
                self.Name = "RouterKing_Job"
                self.Path = EmptyPath()
                self._profile = Op("Profile001", "G1 X1 Y1")
                self.Operations = Group([self._profile])
                self.OutList = [self.Operations]

        handle, output_path = tempfile.mkstemp(prefix="rk_export_", suffix=".nc")
        os.close(handle)
        try:
            gcode = _export_gcode(StubJobWithOps(), "grbl_post", output_path)
            self.assertIn("G1 X1 Y1", gcode)
            with open(output_path, "r", encoding="utf-8") as f:
                written = f.read()
            self.assertIn("G1 X1 Y1", written)
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)


class TestCollectJobOperations(unittest.TestCase):

    def test_excludes_tool_without_base(self):
        class PathObj:
            def __init__(self, text):
                self._text = text

            def toGCode(self):
                return self._text

        class Group:
            def __init__(self, out_list):
                self.OutList = out_list
                self.Group = out_list

        class Obj:
            def __init__(self, name, base, gcode):
                self.Name = name
                self.Path = PathObj(gcode)
                self.Base = base
                self.TypeId = "Path::FeaturePython"

        profile = Obj("Profile", [("Part", ("Face1",))], "G1 X0")
        tool = Obj("TC__Default_Tool", None, "G0 X0")

        class Job:
            def __init__(self):
                self.Operations = Group([profile, tool])
                self.OutList = [self.Operations]

        ops = _collect_job_operations(Job())
        names = [o.Name for o in ops]
        self.assertIn("Profile", names)
        self.assertNotIn("TC__Default_Tool", names)


class TestAssignJobModel(unittest.TestCase):

    def test_assigns_via_model_attr(self):
        job = StubJob()
        model = StubModel()
        _assign_job_model(job, model)
        self.assertEqual(job.Model, [model])

    def test_assigns_via_base_attr(self):
        job = StubJob()
        del job.Model  # force fallback to Base
        model = StubModel()
        _assign_job_model(job, model)
        self.assertEqual(job.Base, model)


class TestGenerateHybridGcodeFallback(unittest.TestCase):
    """generate_hybrid_gcode falls back to simple engine gracefully."""

    def test_simple_engine_with_paths(self):
        """Simple engine works with pre-computed paths."""
        paths = [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]
        result = generate_hybrid_gcode(paths, prefer_cam=False)

        self.assertIsInstance(result, HybridResult)
        self.assertEqual(result.engine, "simple")
        self.assertIn("G90", result.gcode)
        self.assertIsNone(result.job)

    def test_cam_failure_logged_and_falls_back(self):
        """When CAM fails (no FreeCAD), it falls back with a warning."""
        paths = [[(0, 0), (10, 0), (10, 10), (0, 0)]]
        with self.assertLogs("routerking.cam.hybrid", level="WARNING") as cm:
            result = generate_hybrid_gcode(paths, prefer_cam=True)

        self.assertEqual(result.engine, "simple")
        self.assertTrue(len(result.warnings) > 0)
        self.assertTrue(any("CAM integration failed" in w for w in result.warnings))
        self.assertTrue(any("CAM engine failed" in msg for msg in cm.output))


class TestErrorMessagesAreDescriptive(unittest.TestCase):
    """Verify error messages include actionable details."""

    def test_cam_job_failure_includes_model_info(self):
        """The error message should say which model and module failed."""
        from RouterKing.cam.hybrid import generate_cam_gcode

        # With App=None this will raise immediately
        with self.assertRaises(RuntimeError) as ctx:
            generate_cam_gcode(StubModel())

        self.assertIn("not available", str(ctx.exception))


class TestCamGenerateDispatch(unittest.TestCase):
    """generate_cam_gcode must use MainThreadDispatcher.run_on_main when present."""

    def test_uses_dispatcher_run_on_main(self):
        from RouterKing.cam import hybrid

        class StubDispatcher:
            def __init__(self):
                self.calls = 0

            def run_on_main(self, fn, timeout=60.0):
                self.calls += 1
                return fn()

        dispatcher = StubDispatcher()
        expected = ("G1 X0 Y0", StubJob("DispatchJob"))

        with patch.object(hybrid, "get_dispatcher", return_value=dispatcher), \
                patch.object(hybrid, "_generate_cam_gcode_impl", return_value=expected) as impl:
            result = hybrid.generate_cam_gcode(StubModel("DispatchModel"))

        self.assertEqual(result, expected)
        self.assertEqual(dispatcher.calls, 1)
        impl.assert_called_once_with(ANY, None, None)

    def test_falls_back_to_run_on_main_thread_without_dispatcher(self):
        from RouterKing.cam import hybrid

        expected = ("G1 X1 Y1", StubJob("FallbackJob"))
        with patch.object(hybrid, "get_dispatcher", return_value=None), \
                patch.object(hybrid, "run_on_main_thread", return_value=expected) as fallback:
            result = hybrid.generate_cam_gcode(StubModel("FallbackModel"))

        self.assertEqual(result, expected)
        fallback.assert_called_once()

    def test_raises_on_worker_thread_without_dispatcher(self):
        from RouterKing.cam import hybrid

        errors = []

        def _worker():
            with patch.object(hybrid, "get_dispatcher", return_value=None):
                try:
                    hybrid.generate_cam_gcode(StubModel("WorkerNoDispatcher"))
                except Exception as exc:  # noqa: BLE001 - test capture
                    errors.append(str(exc))

        t = threading.Thread(target=_worker, name="worker-no-dispatcher")
        t.start()
        t.join(timeout=5.0)

        self.assertEqual(len(errors), 1)
        self.assertIn("MainThreadDispatcher is not initialized", errors[0])


if __name__ == "__main__":
    unittest.main()
