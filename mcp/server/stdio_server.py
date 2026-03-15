"""Minimal MCP stdio server speaking JSON-RPC 2.0 over stdin/stdout.

Claude Code launches this as a subprocess and communicates via the
Model Context Protocol.  Logging goes to stderr only.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, List

from .main import build_tool_registry
from .freecad_connection import FreeCADConnection

LOG = logging.getLogger("routerking.mcp.stdio")

# ---------------------------------------------------------------------------
# Tool JSON-Schema definitions
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    # -- FreeCAD read tools --
    {
        "name": "list_documents",
        "description": "List all open FreeCAD documents.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_active_document",
        "description": "Get the active FreeCAD document with its object tree.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_scene_info",
        "description": "Get scene overview (objects, types, visibility).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_selection_context",
        "description": "Get current selection with geometry details.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "capture_view",
        "description": "Capture a screenshot of the current 3D view.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_path": {"type": "string", "description": "File path for the screenshot."},
            },
            "additionalProperties": False,
        },
    },
    # -- RouterKing action tools --
    {
        "name": "routerking_list_actions",
        "description": "List all registered RouterKing actions with their parameters and risk classes.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "routerking_apply_actions",
        "description": "Execute one or more RouterKing actions (batch interface).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "payload": {
                    "description": "Action payload, e.g. {\"actions\": [{\"type\": \"...\"}]}.",
                },
                "include_context": {"type": "boolean", "default": True},
                "capture_view": {"type": "boolean", "default": False},
                "screenshot_path": {"type": "string"},
            },
            "required": ["payload"],
            "additionalProperties": False,
        },
    },
    {
        "name": "routerking_run_script",
        "description": "[UNSAFE / DEV ONLY] Execute Python code in FreeCAD and return stdout/stderr.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute."},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "routerking_console_exec",
        "description": "[UNSAFE / DEV ONLY] Execute Python in persistent console namespace and return output.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute."},
                "persist": {"type": "boolean", "default": True},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "routerking_console_read",
        "description": "[UNSAFE / DEV ONLY] Read recent console execution history entries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "routerking_console_reset",
        "description": "[UNSAFE / DEV ONLY] Reset persistent console namespace and/or clear history.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reset_namespace": {"type": "boolean", "default": True},
                "clear_history": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
    },
    # -- Machine tools --
    {
        "name": "routerking_machine_connect",
        "description": "Connect to a CNC machine via serial port. Requires confirm=true and reason.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "string", "description": "Serial port, e.g. /dev/ttyUSB0."},
                "baudrate": {"type": "integer", "default": 115200},
                "confirm": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["port", "confirm", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "routerking_machine_disconnect",
        "description": "Disconnect from the CNC machine. Requires confirm=true and reason.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["confirm", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "routerking_machine_request_status",
        "description": "Request current machine status (GRBL state, position, feed). Requires confirm=true and reason.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["confirm", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "routerking_machine_jog",
        "description": "Jog the CNC machine. Requires confirm=true and reason.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "feed": {"type": "number", "description": "Feed rate in mm/min."},
                "dx": {"type": "number", "default": 0.0},
                "dy": {"type": "number", "default": 0.0},
                "dz": {"type": "number", "default": 0.0},
                "confirm": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["feed", "confirm", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "routerking_machine_validate_gcode",
        "description": "Validate G-code against machine limits before streaming.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gcode": {"type": "string", "description": "G-code to validate."},
                "machine_profile_path": {"type": "string", "description": "Optional path to machine_profile.json."},
            },
            "required": ["gcode"],
            "additionalProperties": False,
        },
    },
    {
        "name": "routerking_machine_stream_gcode",
        "description": "Stream G-code to the CNC machine. Requires confirm=true and reason.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gcode": {"type": "string", "description": "G-code to stream."},
                "machine_profile_path": {"type": "string", "description": "Optional path to machine_profile.json."},
                "confirm": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["gcode", "confirm", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "routerking_machine_stop",
        "description": "Emergency stop the CNC machine. Requires confirm=true and reason.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["confirm", "reason"],
            "additionalProperties": False,
        },
    },
]

_TOOL_SCHEMA_MAP = {t["name"]: t for t in TOOL_SCHEMAS}

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _ok(id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _error(id: Any, code: int, message: str, data: Any = None) -> dict:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id, "error": err}


# ---------------------------------------------------------------------------
# Request handlers
# ---------------------------------------------------------------------------

_registry: Dict[str, Any] | None = None


def _get_registry():
    global _registry
    if _registry is None:
        _registry = build_tool_registry()
    return _registry


def handle_initialize(id: Any, _params: dict) -> dict:
    return _ok(id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {
            "name": "routerking-mcp",
            "version": "0.1.0",
        },
    })


def handle_tools_list(id: Any, _params: dict) -> dict:
    return _ok(id, {"tools": TOOL_SCHEMAS})


def handle_tools_call(id: Any, params: dict) -> dict:
    name = params.get("name", "")
    arguments = params.get("arguments", {})

    registry = _get_registry()
    handler = registry.get(name)
    if handler is None:
        return _error(id, -32602, f"Unknown tool: {name}")

    try:
        result = handler(**arguments)
    except Exception as exc:
        LOG.exception("Tool %s raised", name)
        return _ok(id, {
            "content": [{"type": "text", "text": json.dumps({"success": False, "message": str(exc)})}],
            "isError": True,
        })

    return _ok(id, {
        "content": [{"type": "text", "text": json.dumps(result, default=str)}],
        "isError": not result.get("success", True),
    })


HANDLERS = {
    "initialize": handle_initialize,
    "notifications/initialized": None,  # notification, no response
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}

# ---------------------------------------------------------------------------
# stdio main loop
# ---------------------------------------------------------------------------


def _read_message() -> dict | None:
    """Read one JSON-RPC message from stdin (newline-delimited)."""
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)


def _write_message(msg: dict) -> None:
    """Write one JSON-RPC message to stdout (newline-delimited)."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    LOG.info("RouterKing MCP stdio server starting")

    while True:
        try:
            msg = _read_message()
        except json.JSONDecodeError as exc:
            LOG.warning("Invalid JSON: %s", exc)
            continue

        if msg is None:
            LOG.info("stdin closed, shutting down")
            break

        method = msg.get("method")
        id_ = msg.get("id")
        params = msg.get("params", {})

        if method not in HANDLERS:
            if id_ is not None:
                _write_message(_error(id_, -32601, f"Method not found: {method}"))
            continue

        handler = HANDLERS[method]
        if handler is None:
            # notification — no response
            continue

        response = handler(id_, params)
        _write_message(response)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
