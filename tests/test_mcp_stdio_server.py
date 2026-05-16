"""Tests for the MCP stdio server protocol layer."""

import json
from unittest import mock

import pytest

from mcp.server.stdio_server import (
    TOOL_SCHEMAS,
    _TOOL_SCHEMA_MAP,
    handle_initialize,
    handle_tools_call,
    handle_tools_list,
)
from mcp.server.main import build_tool_registry


class TestInitialize:
    def test_returns_protocol_version_and_server_info(self):
        resp = handle_initialize(1, {})
        result = resp["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "routerking-mcp"
        assert "tools" in result["capabilities"]

    def test_response_has_matching_id(self):
        resp = handle_initialize(42, {})
        assert resp["id"] == 42
        assert resp["jsonrpc"] == "2.0"


class TestToolsList:
    def test_returns_all_tools(self):
        resp = handle_tools_list(1, {})
        tools = resp["result"]["tools"]
        assert len(tools) == len(TOOL_SCHEMAS)

    def test_each_tool_has_required_fields(self):
        resp = handle_tools_list(1, {})
        for tool in resp["result"]["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"].get("type") == "object"

    def test_known_tools_present(self):
        names = {t["name"] for t in TOOL_SCHEMAS}
        assert "routerking_list_actions" in names
        assert "routerking_console_exec" in names
        assert "routerking_console_read" in names
        assert "routerking_machine_stop" in names
        assert "routerking_machine_validate_gcode" in names
        assert "routerking_machine_probe_z" in names
        assert "routerking_machine_probe_config" in names
        assert "list_documents" in names
        assert "capture_view" in names
        assert "routerking_cam_capabilities" in names
        assert "routerking_cam_list_setups" in names
        assert "routerking_cam_list_operations" in names
        assert "routerking_cam_inspect_operation" in names
        assert "routerking_generate_gcode" in names
        assert "routerking_cam_generate_job" in names
        assert "routerking_cam_postprocess" in names

    def test_all_schema_tools_have_registry_handlers(self):
        registry = build_tool_registry()
        missing = [tool["name"] for tool in TOOL_SCHEMAS if tool["name"] not in registry]
        assert missing == []

    def test_tool_schema_map_matches_tool_schemas(self):
        assert set(_TOOL_SCHEMA_MAP) == {tool["name"] for tool in TOOL_SCHEMAS}
        for tool in TOOL_SCHEMAS:
            assert _TOOL_SCHEMA_MAP[tool["name"]] is tool

    def test_registry_tools_are_advertised_by_schemas(self):
        schema_names = {tool["name"] for tool in TOOL_SCHEMAS}
        registry_names = set(build_tool_registry())
        assert registry_names - schema_names == set()

    def test_cam_postprocess_schema_requires_gcode(self):
        schema = _TOOL_SCHEMA_MAP["routerking_cam_postprocess"]["inputSchema"]
        assert schema["required"] == ["gcode"]
        assert schema["properties"]["feed_rate"]["type"] == "number"

    def test_cam_generation_schemas_expose_operations(self):
        for name in ("routerking_generate_gcode", "routerking_cam_generate_job"):
            schema = _TOOL_SCHEMA_MAP[name]["inputSchema"]
            assert set(schema["properties"]) >= {"model", "operations", "output_path", "prefer_cam", "use_cam_defaults"}
            assert schema["properties"]["prefer_cam"]["type"] == "boolean"
            assert schema["properties"]["use_cam_defaults"]["type"] == "boolean"

    def test_cam_read_only_inspection_schemas_are_filter_only(self):
        setup_schema = _TOOL_SCHEMA_MAP["routerking_cam_list_setups"]["inputSchema"]
        assert set(setup_schema["properties"]) == {"document"}
        assert setup_schema["properties"]["document"]["type"] == "string"
        assert setup_schema["additionalProperties"] is False
        assert "required" not in setup_schema

        operation_schema = _TOOL_SCHEMA_MAP["routerking_cam_list_operations"]["inputSchema"]
        assert set(operation_schema["properties"]) == {"setup_id", "include_paths", "include_properties"}
        assert operation_schema["properties"]["setup_id"]["type"] == "string"
        assert operation_schema["properties"]["include_paths"]["type"] == "boolean"
        assert operation_schema["properties"]["include_properties"]["type"] == "boolean"
        assert operation_schema["additionalProperties"] is False
        assert "confirm" not in operation_schema["properties"]
        assert "reason" not in operation_schema["properties"]

    def test_cam_inspect_operation_schema_requires_operation_id_and_is_read_only(self):
        schema = _TOOL_SCHEMA_MAP["routerking_cam_inspect_operation"]["inputSchema"]
        assert schema["required"] == ["operation_id"]
        assert set(schema["properties"]) == {
            "operation_id",
            "setup_id",
            "include_gcode",
            "gcode_lines",
            "include_properties",
            "include_warnings",
        }
        assert schema["properties"]["operation_id"]["type"] == "string"
        assert schema["properties"]["setup_id"]["type"] == "string"
        assert schema["properties"]["include_gcode"]["type"] == "boolean"
        assert schema["properties"]["gcode_lines"]["type"] == "integer"
        assert schema["properties"]["include_properties"]["type"] == "boolean"
        assert schema["properties"]["include_warnings"]["type"] == "boolean"
        assert schema["additionalProperties"] is False
        assert "confirm" not in schema["properties"]
        assert "reason" not in schema["properties"]


class TestToolsCall:
    @mock.patch("mcp.server.stdio_server._get_registry")
    def test_calls_registered_tool(self, mock_registry):
        mock_registry.return_value = {
            "routerking_list_actions": lambda **_: {"success": True, "data": ["a"]},
        }
        resp = handle_tools_call(1, {"name": "routerking_list_actions", "arguments": {}})
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["success"] is True

    @mock.patch("mcp.server.stdio_server._get_registry")
    def test_unknown_tool_returns_error(self, mock_registry):
        mock_registry.return_value = {}
        resp = handle_tools_call(1, {"name": "nonexistent_tool", "arguments": {}})
        assert "error" in resp
        assert resp["error"]["code"] == -32602

    @mock.patch("mcp.server.stdio_server._get_registry")
    def test_tool_exception_returns_error_content(self, mock_registry):
        mock_registry.return_value = {
            "bad_tool": lambda **_: (_ for _ in ()).throw(RuntimeError("boom")),
        }
        resp = handle_tools_call(1, {"name": "bad_tool", "arguments": {}})
        assert resp["result"]["isError"] is True
        content = json.loads(resp["result"]["content"][0]["text"])
        assert "boom" in content["message"]

    @mock.patch("mcp.server.stdio_server._get_registry")
    def test_tool_exception_wrapped_correctly(self, mock_registry):
        def explode(**_):
            raise ValueError("test error")
        mock_registry.return_value = {"exploder": explode}
        resp = handle_tools_call(1, {"name": "exploder", "arguments": {}})
        assert resp["result"]["isError"] is True
