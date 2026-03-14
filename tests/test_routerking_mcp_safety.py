import unittest

from RouterKing.mcp.bridge import RouterKingBridge
from mcp.server.machine_tools import routerking_machine_jog
from mcp.server.safety import validate_machine_confirmation


class StubConnection:
    def invoke(self, operation, **kwargs):
        self.operation = operation
        self.kwargs = kwargs
        return {"success": True, "message": "ok", "data": kwargs, "errors": []}


class TestRouterKingMcpSafety(unittest.TestCase):
    def test_validate_machine_confirmation_requires_confirm_and_reason(self):
        errors = validate_machine_confirmation("routerking_machine_jog", {})
        self.assertIn("routerking_machine_jog: confirm=true required.", errors)
        self.assertIn("routerking_machine_jog: reason is required.", errors)

    def test_machine_jog_wrapper_builds_expected_action_payload(self):
        connection = StubConnection()
        response = routerking_machine_jog(feed=300, dx=1.0, confirm=True, reason="fixture test", connection=connection)
        self.assertTrue(response["success"])
        payload = connection.kwargs["payload"]
        self.assertEqual(payload["actions"][0]["type"], "machine_jog")
        self.assertEqual(payload["actions"][0]["reason"], "fixture test")

    def test_bridge_rejects_machine_jog_without_confirm(self):
        bridge = RouterKingBridge(
            action_executor=lambda actions: (["Jog sent."], []),
            context_module=type(
                "StubContextModule",
                (),
                {
                    "get_scene_info": staticmethod(lambda: {"document": None, "object_count": 0, "objects": [], "selection": [], "selection_count": 0, "warnings": []}),
                },
            ),
            screenshot_module=type("StubScreenshot", (), {"capture_view": staticmethod(lambda output_path=None: {"available": False, "path": None, "message": "no screenshot"})}),
            transaction_factory=lambda: type("Tx", (), {"open": lambda self, name="": False, "commit": lambda self: False, "abort": lambda self: False})(),
        )
        response = bridge.apply_actions({"actions": [{"type": "machine_jog", "feed": 300, "dx": 1.0}]}, include_context=False)
        self.assertFalse(response["success"])
        self.assertIn("machine_jog: confirm=true required.", response["errors"])


if __name__ == "__main__":
    unittest.main()
