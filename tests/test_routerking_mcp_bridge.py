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


if __name__ == "__main__":
    unittest.main()

