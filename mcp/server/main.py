"""CLI entrypoint for the RouterKing MCP module layout.

This file intentionally keeps the transport lightweight for the first
implementation slice. The actual MCP-facing tool functions live in the sibling
modules and can later be mounted onto a real MCP transport once the external
bridge/runtime decision is finalized.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Callable, Dict

from .freecad_connection import FreeCADConnection
from .freecad_tools import capture_view, get_active_document, get_scene_info, get_selection_context, list_documents
from .machine_tools import (
    routerking_machine_connect,
    routerking_machine_disconnect,
    routerking_machine_jog,
    routerking_machine_request_status,
    routerking_machine_stop,
    routerking_machine_stream_gcode,
)
from .routerking_tools import routerking_apply_actions, routerking_list_actions


def build_tool_registry(connection: FreeCADConnection | None = None) -> Dict[str, Callable[..., Dict[str, Any]]]:
    bound_connection = connection or FreeCADConnection()
    return {
        "list_documents": lambda **_: list_documents(bound_connection),
        "get_active_document": lambda **_: get_active_document(bound_connection),
        "get_scene_info": lambda **_: get_scene_info(bound_connection),
        "get_selection_context": lambda **_: get_selection_context(bound_connection),
        "capture_view": lambda **payload: capture_view(connection=bound_connection, output_path=payload.get("output_path")),
        "routerking_list_actions": lambda **_: routerking_list_actions(bound_connection),
        "routerking_apply_actions": lambda **payload: routerking_apply_actions(connection=bound_connection, **payload),
        "routerking_machine_connect": lambda **payload: routerking_machine_connect(connection=bound_connection, **payload),
        "routerking_machine_disconnect": lambda **payload: routerking_machine_disconnect(connection=bound_connection, **payload),
        "routerking_machine_request_status": lambda **payload: routerking_machine_request_status(connection=bound_connection, **payload),
        "routerking_machine_jog": lambda **payload: routerking_machine_jog(connection=bound_connection, **payload),
        "routerking_machine_stream_gcode": lambda **payload: routerking_machine_stream_gcode(connection=bound_connection, **payload),
        "routerking_machine_stop": lambda **payload: routerking_machine_stop(connection=bound_connection, **payload),
    }


def build_manifest() -> Dict[str, Any]:
    return {
        "server": "routerking-mcp",
        "connection_mode": FreeCADConnection().config.mode,
        "tools": sorted(build_tool_registry().keys()),
        "notes": [
            "This MVP slice uses an embedded FreeCAD connection.",
            "A socket/RPC transport can be added behind freecad_connection.py later.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RouterKing MCP development entrypoint")
    parser.add_argument("--describe", action="store_true", help="Print the available tools and exit.")
    parser.add_argument("--ping", action="store_true", help="Run the FreeCAD bridge health check and exit.")
    parser.add_argument("--tool", help="Invoke a tool by name.")
    parser.add_argument("--payload", default="{}", help="JSON payload passed to --tool.")
    args = parser.parse_args(argv)

    if args.describe or (not args.ping and not args.tool):
        print(json.dumps(build_manifest(), indent=2, sort_keys=True))
        return 0

    connection = FreeCADConnection()
    if args.ping:
        print(json.dumps(connection.ping(), indent=2, sort_keys=True))
        return 0

    registry = build_tool_registry(connection)
    handler = registry.get(args.tool)
    if handler is None:
        print(json.dumps({"success": False, "message": f"Unknown tool: {args.tool}"}, indent=2, sort_keys=True))
        return 1

    payload = json.loads(args.payload or "{}")
    result = handler(**payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("success") else 1


if __name__ == "__main__":  # pragma: no cover - CLI wrapper
    raise SystemExit(main())

