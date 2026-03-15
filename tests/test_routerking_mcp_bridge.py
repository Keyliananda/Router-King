import unittest

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
