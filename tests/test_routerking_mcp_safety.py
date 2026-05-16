import unittest

from RouterKing.mcp.bridge import RouterKingBridge
from mcp.server.machine_tools import (
    routerking_machine_jog,
    routerking_machine_probe_config,
    routerking_machine_probe_z,
    routerking_machine_validate_gcode,
)
from mcp.server.routerking_tools import (
    routerking_cam_capabilities,
    routerking_cam_generate_job,
    routerking_cam_list_operations,
    routerking_cam_list_setups,
    routerking_cam_postprocess,
    routerking_console_exec,
    routerking_generate_gcode,
)
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

    def test_machine_validate_wrapper_builds_expected_action_payload(self):
        connection = StubConnection()
        response = routerking_machine_validate_gcode(
            gcode="G90\nG0 X0",
            machine_profile_path="/tmp/machine_profile.json",
            connection=connection,
        )
        self.assertTrue(response["success"])
        payload = connection.kwargs["payload"]
        self.assertEqual(payload["actions"][0]["type"], "machine_validate_gcode")
        self.assertEqual(payload["actions"][0]["machine_profile_path"], "/tmp/machine_profile.json")

    def test_machine_probe_z_wrapper_builds_expected_action_payload(self):
        connection = StubConnection()
        response = routerking_machine_probe_z(
            block_height=15.0,
            confirm=True,
            reason="touch plate setup",
            connection=connection,
        )
        self.assertTrue(response["success"])
        payload = connection.kwargs["payload"]
        self.assertEqual(payload["actions"][0]["type"], "machine_probe_z")
        self.assertEqual(payload["actions"][0]["block_height"], 15.0)

    def test_machine_probe_config_wrapper_builds_expected_action_payload(self):
        connection = StubConnection()
        response = routerking_machine_probe_config(
            probe_feed=35.0,
            retract=2.0,
            connection=connection,
        )
        self.assertTrue(response["success"])
        payload = connection.kwargs["payload"]
        self.assertEqual(payload["actions"][0]["type"], "machine_probe_config")
        self.assertEqual(payload["actions"][0]["probe_feed"], 35.0)
        self.assertEqual(payload["actions"][0]["retract"], 2.0)

    def test_generate_gcode_wrapper_builds_expected_action_payload(self):
        connection = StubConnection()
        response = routerking_generate_gcode(
            model="Body",
            operations=[{"type": "profile", "depth": -3.0}],
            output_path="/tmp/routerking.nc",
            prefer_cam=True,
            use_cam_defaults=True,
            connection=connection,
        )
        self.assertTrue(response["success"])
        payload = connection.kwargs["payload"]
        action = payload["actions"][0]
        self.assertEqual(action["type"], "generate_gcode")
        self.assertEqual(action["model"], "Body")
        self.assertEqual(action["operations"][0]["type"], "profile")
        self.assertEqual(action["output_path"], "/tmp/routerking.nc")
        self.assertTrue(action["prefer_cam"])
        self.assertTrue(action["use_cam_defaults"])

    def test_cam_capabilities_wrapper_invokes_bridge_operation(self):
        connection = StubConnection()
        response = routerking_cam_capabilities(connection=connection)
        self.assertTrue(response["success"])
        self.assertEqual(connection.operation, "cam_capabilities")

    def test_cam_list_setups_wrapper_invokes_bridge_operation(self):
        connection = StubConnection()
        response = routerking_cam_list_setups(document="Doc", connection=connection)
        self.assertTrue(response["success"])
        self.assertEqual(connection.operation, "cam_list_setups")
        self.assertEqual(connection.kwargs["document"], "Doc")

    def test_cam_list_operations_wrapper_invokes_bridge_operation(self):
        connection = StubConnection()
        response = routerking_cam_list_operations(
            setup_id="Job001",
            include_paths=True,
            include_properties=False,
            connection=connection,
        )
        self.assertTrue(response["success"])
        self.assertEqual(connection.operation, "cam_list_operations")
        self.assertEqual(connection.kwargs["setup_id"], "Job001")
        self.assertTrue(connection.kwargs["include_paths"])
        self.assertFalse(connection.kwargs["include_properties"])

    def test_cam_generate_job_wrapper_builds_expected_action_payload(self):
        connection = StubConnection()
        response = routerking_cam_generate_job(
            model="Body",
            operations=[{"type": "pocket", "depth": -2.0}],
            connection=connection,
        )
        self.assertTrue(response["success"])
        payload = connection.kwargs["payload"]
        self.assertEqual(payload["actions"][0]["type"], "cam_generate_job")
        self.assertEqual(payload["actions"][0]["operations"][0]["type"], "pocket")
        self.assertTrue(connection.kwargs["capture_view"])

    def test_cam_postprocess_wrapper_builds_expected_action_payload(self):
        connection = StubConnection()
        response = routerking_cam_postprocess(
            gcode="G21\nG1 X1",
            machine_profile_path="/tmp/machine_profile.json",
            feed_rate=800,
            plunge_rate=300,
            connection=connection,
        )
        self.assertTrue(response["success"])
        self.assertFalse(connection.kwargs["include_context"])
        payload = connection.kwargs["payload"]
        action = payload["actions"][0]
        self.assertEqual(action["type"], "cam_postprocess")
        self.assertEqual(action["gcode"], "G21\nG1 X1")
        self.assertEqual(action["machine_profile_path"], "/tmp/machine_profile.json")
        self.assertEqual(action["feed_rate"], 800)
        self.assertEqual(action["plunge_rate"], 300)

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


    def test_dangerous_dev_blocked_without_flag(self):
        from mcp.server.safety import RISK_DANGEROUS_DEV, validate_risk

        errors = validate_risk("routerking_run_script", RISK_DANGEROUS_DEV, {"code": "print(1)"}, dev_tools_enabled=False)
        self.assertEqual(len(errors), 1)
        self.assertIn("dangerous development tools are disabled", errors[0])

    def test_dangerous_dev_allowed_with_flag(self):
        from mcp.server.safety import RISK_DANGEROUS_DEV, validate_risk

        errors = validate_risk("routerking_run_script", RISK_DANGEROUS_DEV, {"code": "print(1)"}, dev_tools_enabled=True)
        self.assertEqual(errors, [])

    def test_console_exec_blocked_without_flag(self):
        connection = StubConnection()
        with unittest.mock.patch.dict("os.environ", {}, clear=False):
            response = routerking_console_exec("print('hi')", connection=connection)
        self.assertFalse(response["success"])
        self.assertIn("dangerous development tools are disabled", response["message"])

    def test_console_exec_allowed_with_flag(self):
        connection = StubConnection()
        with unittest.mock.patch.dict("os.environ", {"ROUTERKING_MCP_DEV_TOOLS": "1"}, clear=False):
            response = routerking_console_exec("print('hi')", connection=connection)
        self.assertTrue(response["success"])
        self.assertEqual(connection.operation, "console_exec")
        self.assertEqual(connection.kwargs["code"], "print('hi')")


if __name__ == "__main__":
    unittest.main()
