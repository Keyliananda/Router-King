import unittest
from types import SimpleNamespace

from RouterKing.mcp.bridge import ACTION_REGISTRY, RouterKingBridge


class StubContextModule:
    @staticmethod
    def list_documents():
        return {"documents": [], "active_document": None, "warnings": ["FreeCAD is not available."]}

    @staticmethod
    def get_active_document():
        return {"document": None, "warnings": ["No active document."]}

    @staticmethod
    def get_selection_context():
        return {
            "document": None,
            "selection_count": 0,
            "selected_objects": [],
            "warnings": ["No selection found."],
        }

    @staticmethod
    def get_scene_info():
        return {
            "document": None,
            "object_count": 0,
            "objects": [],
            "selection": [],
            "selection_count": 0,
            "warnings": ["No active document."],
        }


class StubScreenshotModule:
    @staticmethod
    def capture_view(output_path=None):
        return {
            "available": False,
            "path": None,
            "message": "Screenshot unavailable: FreeCADGui is not available.",
        }


class StubTransaction:
    def __init__(self):
        self.opened = False
        self.aborted = False
        self.committed = False

    def open(self, name="RouterKing MCP"):
        self.opened = True
        return True

    def commit(self):
        self.committed = True
        return True

    def abort(self):
        self.aborted = True
        return True


class StubPath:
    def __init__(self, gcode):
        self._gcode = gcode

    def toGCode(self):
        return self._gcode


class StubCamOperation:
    def __init__(self, name, label, gcode):
        self.Name = name
        self.Label = label
        self.TypeId = "Path::FeaturePython"
        self.Path = StubPath(gcode)
        self.Base = "Body.Face1"
        self.Active = True
        self.StartDepth = 0.0
        self.FinalDepth = -1.0
        self.StepDown = 1.0
        self.HorizFeed = 800.0
        self.VertFeed = 300.0


class StubCamGroup:
    def __init__(self, children):
        self.Name = "Operations"
        self.Label = "Operations"
        self.TypeId = "App::DocumentObjectGroup"
        self.Group = children
        self.OutList = children


class StubCamJob:
    def __init__(self):
        self.Name = "Job001"
        self.Label = "Setup 1"
        self.TypeId = "Path::Job"
        self.Path = StubPath("G21\nG0 X0")
        self.Model = "Body"
        self.PostProcessor = "grbl_post"
        self.OutputFile = "/tmp/job001.nc"
        self._profile = StubCamOperation("Profile001", "Outside Profile", "G1 X1\nG1 Y1")
        self._pocket = StubCamOperation("Pocket001", "Pocket", "G1 X2\nG1 Y2")
        self.Operations = StubCamGroup([self._profile, self._pocket])
        self.OutList = [self.Operations]


class TestRouterKingMcpBridge(unittest.TestCase):
    def test_list_actions_returns_registry(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.list_actions()
        self.assertTrue(response["success"])
        self.assertEqual(len(response["data"]["actions"]), len(ACTION_REGISTRY))

    def test_cam_capabilities_returns_supported_operation_kinds(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.cam_capabilities()
        self.assertTrue(response["success"])
        kinds = {item["type"] for item in response["data"]["operation_kinds"]}
        self.assertEqual(kinds, {"profile", "pocket", "drilling"})
        self.assertIn("routerking_cam_postprocess", response["data"]["mcp_pipeline"])

    def test_cam_list_setups_returns_read_only_setup_summary(self):
        called = []
        job = StubCamJob()
        app = SimpleNamespace(ActiveDocument=SimpleNamespace(Name="Doc", Objects=[job]))
        bridge = RouterKingBridge(
            action_executor=lambda actions: called.append(actions),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        with unittest.mock.patch.dict("sys.modules", {"FreeCAD": app}):
            response = bridge.cam_list_setups()
        self.assertTrue(response["success"])
        self.assertEqual(called, [])
        self.assertEqual(len(response["data"]["setups"]), 1)
        setup = response["data"]["setups"][0]
        self.assertEqual(setup["name"], "Job001")
        self.assertEqual(setup["label"], "Setup 1")
        self.assertEqual(setup["operation_count"], 2)
        self.assertEqual(setup["post_processor"], "grbl_post")

    def test_cam_list_operations_returns_operations_for_setup(self):
        job = StubCamJob()
        app = SimpleNamespace(ActiveDocument=SimpleNamespace(Name="Doc", Objects=[job]))
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        with unittest.mock.patch.dict("sys.modules", {"FreeCAD": app}):
            response = bridge.cam_list_operations(setup_id="Job001", include_paths=True)
        self.assertTrue(response["success"])
        operations = response["data"]["operations"]
        self.assertEqual(len(operations), 2)
        self.assertEqual(operations[0]["setup_id"], "Job001")
        self.assertEqual(operations[0]["operation_type"], "profile")
        self.assertEqual(operations[0]["gcode_line_count"], 2)
        self.assertIn("gcode_preview", operations[0])
        self.assertEqual(operations[0]["properties"]["FinalDepth"], -1.0)

    def test_cam_list_operations_unknown_setup_returns_warning(self):
        job = StubCamJob()
        app = SimpleNamespace(ActiveDocument=SimpleNamespace(Name="Doc", Objects=[job]))
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        with unittest.mock.patch.dict("sys.modules", {"FreeCAD": app}):
            response = bridge.cam_list_operations(setup_id="Missing")
        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["operations"], [])
        self.assertIn("CAM setup not found: Missing", response["errors"])

    def test_cam_inspect_operation_returns_path_excerpt_and_properties(self):
        called = []
        job = StubCamJob()
        app = SimpleNamespace(ActiveDocument=SimpleNamespace(Name="Doc", Objects=[job]))
        bridge = RouterKingBridge(
            action_executor=lambda actions: called.append(actions),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        with unittest.mock.patch.dict("sys.modules", {"FreeCAD": app}):
            response = bridge.cam_inspect_operation(
                operation_id="Profile001",
                setup_id="Job001",
                include_gcode=True,
                gcode_lines=10,
            )
        self.assertTrue(response["success"])
        self.assertEqual(called, [])
        self.assertEqual(response["data"]["setup_id"], "Job001")
        operation = response["data"]["operation"]
        self.assertEqual(operation["id"], "Profile001")
        self.assertEqual(operation["operation_type"], "profile")
        self.assertEqual(operation["gcode_line_count"], 2)
        self.assertEqual(operation["gcode_excerpt"], "G1 X1\nG1 Y1")
        self.assertEqual(operation["path"]["source"], "Path.toGCode")
        self.assertFalse(operation["path"]["preview_truncated"])
        self.assertEqual(operation["properties"]["FinalDepth"], -1.0)
        self.assertEqual(operation["setup"]["id"], "Job001")
        self.assertEqual(response["errors"], [])

    def test_cam_inspect_operation_unknown_operation_returns_error(self):
        job = StubCamJob()
        app = SimpleNamespace(ActiveDocument=SimpleNamespace(Name="Doc", Objects=[job]))
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        with unittest.mock.patch.dict("sys.modules", {"FreeCAD": app}):
            response = bridge.cam_inspect_operation(operation_id="MissingOp")
        self.assertFalse(response["success"])
        self.assertIsNone(response["data"]["operation"])
        self.assertIn("CAM operation not found: MissingOp", response["errors"])

    def test_apply_actions_rejects_unknown_action(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.apply_actions({"actions": [{"type": "not_real"}]})
        self.assertFalse(response["success"])
        self.assertIn("Unsupported action: not_real", response["errors"])

    def test_apply_actions_can_execute_simple_geometry_action(self):
        def executor(actions):
            self.assertEqual(actions[0]["type"], "create_part_box")
            return (["Box created."], [])

        bridge = RouterKingBridge(
            action_executor=executor,
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.apply_actions({"actions": [{"type": "create_part_box", "length": 10, "width": 20, "height": 5}]})
        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["results"][0]["message"], "Box created.")
        self.assertTrue(response["data"]["transaction"]["used"])

    def test_get_active_document_returns_clear_no_document_response(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.get_active_document()
        self.assertFalse(response["success"])
        self.assertEqual(response["message"], "No active document.")
        self.assertIn("No active document.", response["errors"])

    def test_capture_view_uses_text_fallback(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.capture_view()
        self.assertFalse(response["success"])
        self.assertIn("Screenshot unavailable", response["message"])


    def test_analyze_selection_builds_correct_payload(self):
        captured = {}

        def executor(actions):
            captured["actions"] = actions
            return (["Analysis complete."], [])

        bridge = RouterKingBridge(
            action_executor=executor,
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.apply_actions(
            {"actions": [{"type": "analyze_selection"}]},
            include_context=True,
        )
        self.assertTrue(response["success"])
        self.assertEqual(captured["actions"][0]["type"], "analyze_selection")
        self.assertIn("context", response["data"])

    def test_generate_gcode_filters_none_params(self):
        captured = {}

        def executor(actions):
            captured["actions"] = actions
            return (["G-code generated."], [])

        bridge = RouterKingBridge(
            action_executor=executor,
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        action = {"type": "generate_gcode", "output_path": "/tmp/out.gcode"}
        response = bridge.apply_actions({"actions": [action]})
        self.assertTrue(response["success"])
        sent_action = captured["actions"][0]
        self.assertEqual(sent_action["type"], "generate_gcode")
        self.assertEqual(sent_action["output_path"], "/tmp/out.gcode")
        self.assertNotIn("model", sent_action)
        self.assertNotIn("operations", sent_action)
        self.assertNotIn("prefer_cam", sent_action)
        self.assertNotIn("use_cam_defaults", sent_action)

    def test_cam_generate_job_includes_capture_view(self):
        captured = {}

        def executor(actions):
            captured["actions"] = actions
            return (["Job created."], [])

        bridge = RouterKingBridge(
            action_executor=executor,
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.apply_actions(
            {"actions": [{"type": "cam_generate_job"}]},
            capture_view=True,
        )
        self.assertTrue(response["success"])
        self.assertIn("screenshot", response["data"])

    def test_cam_postprocess_action_requires_gcode(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.apply_actions({"actions": [{"type": "cam_postprocess"}]}, include_context=False)
        self.assertFalse(response["success"])
        self.assertIn("cam_postprocess: missing required fields: gcode", response["errors"])

    def test_cam_postprocess_action_is_read_only(self):
        captured = {}

        def executor(actions):
            captured["actions"] = actions
            return {"messages": ["Postprocessed."], "errors": [], "data": {"gcode": "G21"}}

        bridge = RouterKingBridge(
            action_executor=executor,
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.apply_actions({"actions": [{"type": "cam_postprocess", "gcode": "G21"}]}, include_context=False)
        self.assertTrue(response["success"])
        self.assertEqual(captured["actions"][0]["type"], "cam_postprocess")
        self.assertFalse(response["data"]["transaction"]["used"])

    def test_dxf_generate_gcode_action_requires_dxf_path(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.apply_actions({"actions": [{"type": "dxf_generate_gcode"}]}, include_context=False)
        self.assertFalse(response["success"])
        self.assertIn("dxf_generate_gcode: missing required fields: dxf_path", response["errors"])

    def test_dxf_generate_gcode_action_uses_modify_transaction(self):
        captured = {}

        def executor(actions):
            captured["actions"] = actions
            return {
                "messages": ["DXF generated."],
                "errors": [],
                "data": {"engine": "simple", "output_path": "/tmp/out.nc"},
            }

        bridge = RouterKingBridge(
            action_executor=executor,
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.apply_actions(
            {"actions": [{"type": "dxf_generate_gcode", "dxf_path": "/tmp/in.dxf"}]},
            include_context=False,
        )
        self.assertTrue(response["success"])
        self.assertEqual(captured["actions"][0]["type"], "dxf_generate_gcode")
        self.assertEqual(captured["actions"][0]["dxf_path"], "/tmp/in.dxf")
        self.assertTrue(response["data"]["transaction"]["used"])
        self.assertEqual(response["data"]["results"][0]["data"]["engine"], "simple")

    def test_run_script_executes_code(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.run_script("print('hello world')")
        self.assertTrue(response["success"])
        self.assertEqual(response["message"], "Script executed.")
        self.assertIn("hello world", response["data"]["output"])

    def test_run_script_captures_errors(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        response = bridge.run_script("raise ValueError('boom')")
        self.assertFalse(response["success"])
        self.assertEqual(response["message"], "Script raised an exception.")
        self.assertTrue(len(response["errors"]) > 0)
        self.assertIn("ValueError", response["errors"][0])
        self.assertIn("boom", response["errors"][0])

    def test_console_exec_persists_namespace(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        first = bridge.console_exec("x = 41")
        self.assertTrue(first["success"])
        second = bridge.console_exec("x + 1")
        self.assertTrue(second["success"])
        self.assertEqual(second["data"]["result"], "42")

    def test_console_read_and_reset(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["ok"], []),
            context_module=StubContextModule,
            screenshot_module=StubScreenshotModule,
            transaction_factory=StubTransaction,
        )
        bridge.console_exec("print('hello')")
        bridge.console_exec("123")
        history = bridge.console_read(limit=5)
        self.assertTrue(history["success"])
        self.assertEqual(history["data"]["total"], 2)
        self.assertEqual(len(history["data"]["entries"]), 2)

        reset = bridge.console_reset(reset_namespace=True, clear_history=True)
        self.assertTrue(reset["success"])
        history_after = bridge.console_read(limit=5)
        self.assertEqual(history_after["data"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
