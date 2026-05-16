"""RouterKing domain tools exposed by the MCP layer."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .freecad_connection import FreeCADConnection
from .safety import RISK_DANGEROUS_DEV, log_tool_request, validate_risk

LOG = logging.getLogger("routerking.mcp.tools")


def _dev_tools_enabled() -> bool:
    return os.getenv("ROUTERKING_MCP_DEV_TOOLS", "").lower() in ("1", "true", "yes")


def _guard_dev_tool(tool_name: str, payload: dict[str, Any]) -> list[str]:
    return validate_risk(
        tool_name,
        RISK_DANGEROUS_DEV,
        payload,
        dev_tools_enabled=_dev_tools_enabled(),
    )


def routerking_list_actions(connection: Optional[FreeCADConnection] = None):
    return (connection or FreeCADConnection()).invoke("list_actions")


def routerking_cam_capabilities(connection: Optional[FreeCADConnection] = None):
    return (connection or FreeCADConnection()).invoke("cam_capabilities")


def routerking_apply_actions(
    payload: Any,
    *,
    include_context: bool = True,
    capture_view: bool = False,
    screenshot_path: str | None = None,
    connection: Optional[FreeCADConnection] = None,
):
    return (connection or FreeCADConnection()).invoke(
        "apply_actions",
        payload=payload,
        include_context=include_context,
        capture_view=capture_view,
        screenshot_path=screenshot_path,
    )


def routerking_analyze_selection(*, connection: Optional[FreeCADConnection] = None):
    """Run analysis on the current FreeCAD selection."""
    return routerking_apply_actions(
        {"actions": [{"type": "analyze_selection"}]},
        include_context=True,
        connection=connection,
    )


def routerking_optimize_splines_preview(*, connection: Optional[FreeCADConnection] = None):
    """Create a spline optimization preview for the current selection."""
    return routerking_apply_actions(
        {"actions": [{"type": "optimize_splines_preview"}]},
        capture_view=True,
        connection=connection,
    )


def routerking_generate_gcode(
    *,
    model: Optional[str] = None,
    operations: Optional[Any] = None,
    output_path: Optional[str] = None,
    prefer_cam: Optional[bool] = None,
    use_cam_defaults: Optional[bool] = None,
    connection: Optional[FreeCADConnection] = None,
):
    """Generate G-code from the current model or specified parameters."""
    action: dict[str, Any] = {"type": "generate_gcode"}
    for key, val in [("model", model), ("operations", operations), ("output_path", output_path), ("prefer_cam", prefer_cam), ("use_cam_defaults", use_cam_defaults)]:
        if val is not None:
            action[key] = val
    return routerking_apply_actions(
        {"actions": [action]},
        connection=connection,
    )


def routerking_cam_generate_job(
    *,
    model: Optional[str] = None,
    operations: Optional[Any] = None,
    output_path: Optional[str] = None,
    prefer_cam: Optional[bool] = None,
    use_cam_defaults: Optional[bool] = None,
    connection: Optional[FreeCADConnection] = None,
):
    """Generate a CAM job from the current model or specified parameters."""
    action: dict[str, Any] = {"type": "cam_generate_job"}
    for key, val in [("model", model), ("operations", operations), ("output_path", output_path), ("prefer_cam", prefer_cam), ("use_cam_defaults", use_cam_defaults)]:
        if val is not None:
            action[key] = val
    return routerking_apply_actions(
        {"actions": [action]},
        capture_view=True,
        connection=connection,
    )


def routerking_cam_postprocess(
    *,
    gcode: str,
    machine_profile_path: Optional[str] = None,
    feed_rate: Optional[float] = None,
    plunge_rate: Optional[float] = None,
    connection: Optional[FreeCADConnection] = None,
):
    """Postprocess CAM G-code for GRBL-safe machine streaming."""
    action: dict[str, Any] = {"type": "cam_postprocess", "gcode": gcode}
    for key, val in [
        ("machine_profile_path", machine_profile_path),
        ("feed_rate", feed_rate),
        ("plunge_rate", plunge_rate),
    ]:
        if val is not None:
            action[key] = val
    return routerking_apply_actions(
        {"actions": [action]},
        include_context=False,
        connection=connection,
    )


def routerking_run_script(
    code: str,
    *,
    connection: Optional[FreeCADConnection] = None,
):
    """[UNSAFE / DEV ONLY] Execute arbitrary Python in the FreeCAD context.

    Gated behind ROUTERKING_MCP_DEV_TOOLS=1.
    """
    errors = _guard_dev_tool("routerking_run_script", {"code": code})
    if errors:
        return {"success": False, "message": "; ".join(errors), "data": None, "errors": errors}

    snippet = code[:120] + ("..." if len(code) > 120 else "")
    log_tool_request("routerking_run_script", RISK_DANGEROUS_DEV, {"code_snippet": snippet})

    result = (connection or FreeCADConnection()).invoke("run_script", code=code)

    LOG.info(
        "routerking_run_script result success=%s output_len=%d errors=%d",
        result.get("success"),
        len(result.get("data", {}).get("output", "")),
        len(result.get("errors", [])),
    )
    return result


def routerking_console_exec(
    code: str,
    *,
    persist: bool = True,
    connection: Optional[FreeCADConnection] = None,
):
    """[UNSAFE / DEV ONLY] Execute code in persistent FreeCAD console namespace."""
    errors = _guard_dev_tool("routerking_console_exec", {"code": code, "persist": persist})
    if errors:
        return {"success": False, "message": "; ".join(errors), "data": None, "errors": errors}

    snippet = code[:120] + ("..." if len(code) > 120 else "")
    log_tool_request(
        "routerking_console_exec",
        RISK_DANGEROUS_DEV,
        {"code_snippet": snippet, "persist": bool(persist)},
    )
    return (connection or FreeCADConnection()).invoke("console_exec", code=code, persist=bool(persist))


def routerking_console_read(
    *,
    limit: int = 20,
    connection: Optional[FreeCADConnection] = None,
):
    """[UNSAFE / DEV ONLY] Read recent persistent console history entries."""
    errors = _guard_dev_tool("routerking_console_read", {"limit": limit})
    if errors:
        return {"success": False, "message": "; ".join(errors), "data": None, "errors": errors}

    log_tool_request(
        "routerking_console_read",
        RISK_DANGEROUS_DEV,
        {"limit": int(limit)},
    )
    return (connection or FreeCADConnection()).invoke("console_read", limit=int(limit))


def routerking_console_reset(
    *,
    reset_namespace: bool = True,
    clear_history: bool = True,
    connection: Optional[FreeCADConnection] = None,
):
    """[UNSAFE / DEV ONLY] Reset persistent console namespace and/or history."""
    payload = {
        "reset_namespace": bool(reset_namespace),
        "clear_history": bool(clear_history),
    }
    errors = _guard_dev_tool("routerking_console_reset", payload)
    if errors:
        return {"success": False, "message": "; ".join(errors), "data": None, "errors": errors}

    log_tool_request("routerking_console_reset", RISK_DANGEROUS_DEV, payload)
    return (connection or FreeCADConnection()).invoke(
        "console_reset",
        reset_namespace=bool(reset_namespace),
        clear_history=bool(clear_history),
    )
