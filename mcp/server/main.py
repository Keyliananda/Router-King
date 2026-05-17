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
    routerking_machine_prepare_manual_xy,
    routerking_machine_probe_config,
    routerking_machine_probe_z,
    routerking_machine_request_status,
    routerking_machine_stop,
    routerking_machine_stream_gcode,
    routerking_machine_validate_gcode,
)
from .routerking_tools import (
    CAM_SETTING_KEYS,
    routerking_analyze_selection,
    routerking_apply_actions,
    routerking_cam_capabilities,
    routerking_cam_generate_job,
    routerking_cam_inspect_operation,
    routerking_cam_list_operations,
    routerking_cam_list_setups,
    routerking_cam_postprocess,
    routerking_cam_analyze_gcode,
    routerking_console_exec,
    routerking_console_read,
    routerking_console_reset,
    routerking_dxf_generate_gcode,
    routerking_generate_gcode,
    routerking_list_actions,
    routerking_open_panel,
    routerking_optimize_splines_preview,
    routerking_run_script,
    routerking_ui_state,
)


def build_tool_registry(connection: FreeCADConnection | None = None) -> Dict[str, Callable[..., Dict[str, Any]]]:
    bound_connection = connection or FreeCADConnection()
    return {
        "list_documents": lambda **_: list_documents(bound_connection),
        "get_active_document": lambda **_: get_active_document(bound_connection),
        "get_scene_info": lambda **_: get_scene_info(bound_connection),
        "get_selection_context": lambda **_: get_selection_context(bound_connection),
        "capture_view": lambda **payload: capture_view(connection=bound_connection, output_path=payload.get("output_path")),
        "routerking_list_actions": lambda **_: routerking_list_actions(bound_connection),
        "routerking_open_panel": lambda **_: routerking_open_panel(connection=bound_connection),
        "routerking_ui_state": lambda **_: routerking_ui_state(connection=bound_connection),
        "routerking_apply_actions": lambda **kwargs: routerking_apply_actions(
            payload=kwargs.get("payload"),
            include_context=kwargs.get("include_context", True),
            capture_view=kwargs.get("capture_view", False),
            screenshot_path=kwargs.get("screenshot_path"),
            connection=bound_connection,
        ),
        "routerking_cam_capabilities": lambda **_: routerking_cam_capabilities(connection=bound_connection),
        "routerking_cam_list_setups": lambda **payload: routerking_cam_list_setups(
            document=payload.get("document"),
            connection=bound_connection,
        ),
        "routerking_cam_list_operations": lambda **payload: routerking_cam_list_operations(
            setup_id=payload.get("setup_id"),
            include_paths=payload.get("include_paths", False),
            include_properties=payload.get("include_properties", True),
            connection=bound_connection,
        ),
        "routerking_cam_inspect_operation": lambda **payload: routerking_cam_inspect_operation(
            operation_id=payload.get("operation_id", ""),
            setup_id=payload.get("setup_id"),
            include_gcode=payload.get("include_gcode", False),
            gcode_lines=payload.get("gcode_lines", 30),
            include_properties=payload.get("include_properties", True),
            include_warnings=payload.get("include_warnings", True),
            connection=bound_connection,
        ),
        "routerking_run_script": lambda **payload: routerking_run_script(
            code=payload.get("code", ""),
            connection=bound_connection,
        ),
        "routerking_analyze_selection": lambda **_: routerking_analyze_selection(connection=bound_connection),
        "routerking_optimize_splines_preview": lambda **_: routerking_optimize_splines_preview(connection=bound_connection),
        "routerking_generate_gcode": lambda **payload: routerking_generate_gcode(
            model=payload.get("model"),
            operations=payload.get("operations"),
            output_path=payload.get("output_path"),
            prefer_cam=payload.get("prefer_cam"),
            use_cam_defaults=payload.get("use_cam_defaults"),
            connection=bound_connection,
            **{key: payload.get(key) for key in CAM_SETTING_KEYS},
        ),
        "routerking_cam_generate_job": lambda **payload: routerking_cam_generate_job(
            model=payload.get("model"),
            operations=payload.get("operations"),
            output_path=payload.get("output_path"),
            prefer_cam=payload.get("prefer_cam"),
            use_cam_defaults=payload.get("use_cam_defaults"),
            connection=bound_connection,
            **{key: payload.get(key) for key in CAM_SETTING_KEYS},
        ),
        "routerking_cam_postprocess": lambda **payload: routerking_cam_postprocess(
            gcode=payload.get("gcode", ""),
            machine_profile_path=payload.get("machine_profile_path"),
            feed_rate=payload.get("feed_rate"),
            plunge_rate=payload.get("plunge_rate"),
            connection=bound_connection,
        ),
        "routerking_cam_analyze_gcode": lambda **payload: routerking_cam_analyze_gcode(
            gcode=payload.get("gcode", ""),
            cam_settings=payload.get("cam_settings"),
        ),
        "routerking_dxf_generate_gcode": lambda **payload: routerking_dxf_generate_gcode(
            dxf_path=payload.get("dxf_path", ""),
            output_path=payload.get("output_path"),
            update_ui=payload.get("update_ui", False),
            use_cam_defaults=payload.get("use_cam_defaults"),
            connection=bound_connection,
            **{
                key: payload.get(key)
                for key in (
                    "safe_z",
                    "cut_z",
                    "start_z",
                    "pass_depth",
                    "ramp_length",
                    "lead_in",
                    "lead_out",
                    "feed_rate",
                    "plunge_rate",
                    "units",
                    "spindle_speed",
                    "laser_power",
                    "start_spindle",
                    "deflection",
                    "arc_segment_angle",
                    "merge_tolerance",
                    "prefer_ezdxf",
                    "use_freecad",
                )
            },
        ),
        "routerking_console_exec": lambda **payload: routerking_console_exec(
            code=payload.get("code", ""),
            persist=payload.get("persist", True),
            connection=bound_connection,
        ),
        "routerking_console_read": lambda **payload: routerking_console_read(
            limit=payload.get("limit", 20),
            connection=bound_connection,
        ),
        "routerking_console_reset": lambda **payload: routerking_console_reset(
            reset_namespace=payload.get("reset_namespace", True),
            clear_history=payload.get("clear_history", True),
            connection=bound_connection,
        ),
        "routerking_machine_connect": lambda **payload: routerking_machine_connect(connection=bound_connection, **payload),
        "routerking_machine_disconnect": lambda **payload: routerking_machine_disconnect(connection=bound_connection, **payload),
        "routerking_machine_request_status": lambda **payload: routerking_machine_request_status(connection=bound_connection, **payload),
        "routerking_machine_jog": lambda **payload: routerking_machine_jog(connection=bound_connection, **payload),
        "routerking_machine_validate_gcode": lambda **payload: routerking_machine_validate_gcode(connection=bound_connection, **payload),
        "routerking_machine_stream_gcode": lambda **payload: routerking_machine_stream_gcode(connection=bound_connection, **payload),
        "routerking_machine_probe_z": lambda **payload: routerking_machine_probe_z(connection=bound_connection, **payload),
        "routerking_machine_prepare_manual_xy": lambda **payload: routerking_machine_prepare_manual_xy(connection=bound_connection, **payload),
        "routerking_machine_probe_config": lambda **payload: routerking_machine_probe_config(connection=bound_connection, **payload),
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
