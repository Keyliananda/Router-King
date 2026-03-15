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
