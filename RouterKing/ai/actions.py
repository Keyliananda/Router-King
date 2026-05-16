"""Action execution helpers for RouterKing AI chat."""

from dataclasses import asdict
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None

# ---------------------------------------------------------------------------
# Thread-safety: FreeCAD GUI objects may only be touched from the Qt main
# thread.  The MCP socket server dispatches requests on worker threads, so
# every FreeCAD-mutating action must be marshalled back via the polling-based
# MainThreadDispatcher (see RouterKing.main_thread).
# ---------------------------------------------------------------------------

try:
    from RouterKing.main_thread import run_on_main_thread
except ImportError:
    try:
        from main_thread import run_on_main_thread
    except ImportError:
        # Fallback: direct execution (tests / headless / no Qt).
        def run_on_main_thread(fn, timeout=60.0):  # type: ignore[misc]
            return fn()

try:
    from ..grbl.postprocessor import postprocess_gcode as grbl_postprocess_gcode
    from ..grbl.validator import (
        calculate_g54_offset,
        load_machine_profile as grbl_load_machine_profile,
        merge_machine_profile as grbl_merge_machine_profile,
        read_grbl_settings as grbl_read_grbl_settings,
        read_machine_status as grbl_read_machine_status,
        resolve_machine_limits as grbl_resolve_machine_limits,
        save_machine_profile as grbl_save_machine_profile,
        validate_gcode as grbl_validate_gcode,
    )
except Exception:
    from grbl.postprocessor import postprocess_gcode as grbl_postprocess_gcode
    from grbl.validator import (
        calculate_g54_offset,
        load_machine_profile as grbl_load_machine_profile,
        merge_machine_profile as grbl_merge_machine_profile,
        read_grbl_settings as grbl_read_grbl_settings,
        read_machine_status as grbl_read_machine_status,
        resolve_machine_limits as grbl_resolve_machine_limits,
        save_machine_profile as grbl_save_machine_profile,
        validate_gcode as grbl_validate_gcode,
    )


# Action types that call FreeCAD / Qt APIs and must execute on the main thread.
_FREECAD_ACTIONS = frozenset({
    "create_document",
    "create_part_box",
    "create_part_cylinder",
    "create_part_sphere",
    "create_sketch",
    "add_rectangle",
    "add_circle",
    "delete_object",
    "translate_object",
    "set_visibility",
    "analyze_selection",
    "optimize_splines_preview",
    "generate_gcode",
    "cam_generate_job",
    "dxf_generate_gcode",
})


_ACTION_HELP: Dict[str, str] = {
    "create_part_box": "Create Part::Box (length, width, height, name?)",
    "create_part_cylinder": "Create Part::Cylinder (radius, height, name?)",
    "create_part_sphere": "Create Part::Sphere (radius, name?)",
    "create_sketch": "Create Sketcher::SketchObject (name?)",
    "add_rectangle": "Add rectangle to sketch (sketch?, x?, y?, width, height)",
    "add_circle": "Add circle to sketch (sketch?, x?, y?, radius)",
    "delete_object": "Delete object by name (name)",
    "translate_object": "Translate object (name, dx, dy, dz)",
    "set_visibility": "Set object visibility (name, visible)",
    "analyze_selection": "Run analysis on current selection (no params)",
    "optimize_splines_preview": "Run spline optimization preview (no params)",
    "generate_gcode": "Generate G-code from selection (output_path?, prefer_cam?)",
    "cam_generate_job": "Create CAM job + operations + post (operations?, output_path?, prefer_cam?)",
    "dxf_generate_gcode": "Generate simple CAM G-code from a DXF file (dxf_path, output_path?)",
    "cam_postprocess": "Postprocess raw CAM G-code for GRBL safety (gcode, feed_rate?, machine_profile_path?)",
    "machine_connect": "Connect to GRBL controller (port, baudrate?)",
    "machine_disconnect": "Disconnect from GRBL controller (no params)",
    "machine_send_line": "Send single G-code/command line (line, confirm=true)",
    "machine_stream_file": "Stream G-code file (path, confirm=true)",
    "machine_validate_gcode": "Validate G-code against machine limits (gcode, machine_profile_path?)",
    "machine_calculate_offset": "Calculate optimal G54 offset command for a G-code bounding box (bounding_box, current_machine_position?, desired_workpiece_corner?)",
    "machine_stream_gcode": "Stream G-code text (gcode, confirm=true)",
    "machine_feed_hold": "Pause motion (confirm=true)",
    "machine_resume": "Resume motion (confirm=true)",
    "machine_stop": "Stop streaming (confirm=true)",
    "machine_soft_reset": "Soft reset GRBL (confirm=true)",
    "machine_request_status": "Request status report (no params)",
    "machine_jog": "Jog move (dx?, dy?, dz?, feed, confirm=true)",
    "machine_home": "Home all axes synchronously, waits for completion (no params)",
    "machine_read_settings": "Read GRBL $$ settings (no params)",
    "machine_identify": "Identify machine: work area, spindle, limits, capabilities (no params)",
    "machine_probe_z": "Probe Z with touch plate and set Z0 (block_height, max_depth?, feed?, retract?, confirm=true)",
    "machine_probe_config": "Read/update persisted probe defaults (block_height?, probe_feed?, retract?)",
}


def get_action_prompt() -> str:
    lines = [
        "You may request RouterKing actions by emitting a JSON block:",
        "```routerking_actions",
        '{"actions":[{"type":"create_part_box","length":20,"width":20,"height":5}]}',
        "```",
        "Only include this block when the user explicitly asks you to create/modify geometry, generate G-code, or control the machine.",
        "Machine-control actions require explicit confirmation: set confirm=true.",
        "CAM actions can inherit RouterKing CAM defaults by setting use_cam_defaults=true.",
        "Allowed actions:",
    ]
    for name, desc in _ACTION_HELP.items():
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


def execute_actions(actions: List[Dict]) -> Tuple[List[str], List[str]]:
    results: List[str] = []
    errors: List[str] = []
    for action in actions or []:
        if not isinstance(action, dict):
            errors.append("Invalid action payload (expected object).")
            continue
        action_type = (action.get("type") or action.get("action") or "").strip()
        params = action.get("params") or {}
        if not isinstance(params, dict):
            params = {}

        handler = _ACTION_HANDLERS.get(action_type)
        if handler is None:
            errors.append(f"Unsupported action: {action_type}")
            continue
        try:
            if action_type in _FREECAD_ACTIONS:
                raw_result = run_on_main_thread(lambda h=handler, a=action, p=params: h(a, p))
            else:
                raw_result = handler(action, params)
            message, action_errors, _ = _coerce_action_handler_result(raw_result)
            if message:
                results.append(message)
            if action_errors:
                errors.extend(action_errors)
        except Exception as exc:
            errors.append(f"{action_type} failed: {exc}")
    return results, errors


def execute_actions_for_bridge(actions: List[Dict]) -> Dict[str, Any]:
    """Bridge-oriented executor that preserves structured action data."""
    messages: List[str] = []
    errors: List[str] = []
    data: Any = None
    for action in actions or []:
        if not isinstance(action, dict):
            errors.append("Invalid action payload (expected object).")
            continue
        action_type = (action.get("type") or action.get("action") or "").strip()
        params = action.get("params") or {}
        if not isinstance(params, dict):
            params = {}

        handler = _ACTION_HANDLERS.get(action_type)
        if handler is None:
            errors.append(f"Unsupported action: {action_type}")
            continue
        try:
            if action_type in _FREECAD_ACTIONS:
                raw_result = run_on_main_thread(lambda h=handler, a=action, p=params: h(a, p))
            else:
                raw_result = handler(action, params)
            message, action_errors, action_data = _coerce_action_handler_result(raw_result)
            if message:
                messages.append(message)
            if action_errors:
                errors.extend(action_errors)
            if action_data is not None:
                data = action_data
        except Exception as exc:
            errors.append(f"{action_type} failed: {exc}")
    return {"messages": messages, "errors": errors, "data": data}


def _coerce_action_handler_result(result: Any) -> tuple[str, List[str], Any]:
    if isinstance(result, dict):
        message = str(result.get("message") or "").strip()
        errors = [str(item) for item in (result.get("errors") or []) if str(item)]
        data = result.get("data")
        return message, errors, data
    if result is None:
        return "", [], None
    return str(result), [], None


def _action_create_part_box(action, params):
    length = _get_param(action, params, "length")
    width = _get_param(action, params, "width")
    height = _get_param(action, params, "height")
    name = _get_param(action, params, "name", default="AI_Box")
    if length is None or width is None or height is None:
        return "create_part_box: length/width/height required."
    obj = _add_part_object("Part::Box", name)
    obj.Length = float(length)
    obj.Width = float(width)
    obj.Height = float(height)
    _recompute()
    return f"Box created: {name} ({length} x {width} x {height} mm)."


def _action_create_part_cylinder(action, params):
    radius = _get_param(action, params, "radius")
    height = _get_param(action, params, "height")
    name = _get_param(action, params, "name", default="AI_Cylinder")
    if radius is None or height is None:
        return "create_part_cylinder: radius/height required."
    obj = _add_part_object("Part::Cylinder", name)
    obj.Radius = float(radius)
    obj.Height = float(height)
    _recompute()
    return f"Cylinder created: {name} (r={radius}, h={height} mm)."


def _action_create_part_sphere(action, params):
    radius = _get_param(action, params, "radius")
    name = _get_param(action, params, "name", default="AI_Sphere")
    if radius is None:
        return "create_part_sphere: radius required."
    obj = _add_part_object("Part::Sphere", name)
    obj.Radius = float(radius)
    _recompute()
    return f"Sphere created: {name} (r={radius} mm)."


def _action_create_sketch(action, params):
    name = _get_param(action, params, "name", default="AI_Sketch")
    doc = _require_doc()
    obj = doc.addObject("Sketcher::SketchObject", _unique_object_name(doc, name))
    _attach_to_active_body(obj)
    _recompute()
    return f"Sketch created: {obj.Name}."


def _action_add_rectangle(action, params):
    width = _get_param(action, params, "width")
    height = _get_param(action, params, "height")
    if width is None or height is None:
        return "add_rectangle: width/height required."
    sketch = _get_target_sketch(action, params)
    if sketch is None:
        return "add_rectangle: no sketch found (use create_sketch or specify sketch name)."

    try:
        import Part
    except Exception:
        return "add_rectangle failed: Part module unavailable."

    x = float(_get_param(action, params, "x", default=0.0))
    y = float(_get_param(action, params, "y", default=0.0))
    w = float(width)
    h = float(height)
    p1 = App.Vector(x, y, 0)
    p2 = App.Vector(x + w, y, 0)
    p3 = App.Vector(x + w, y + h, 0)
    p4 = App.Vector(x, y + h, 0)
    sketch.addGeometry(Part.LineSegment(p1, p2), False)
    sketch.addGeometry(Part.LineSegment(p2, p3), False)
    sketch.addGeometry(Part.LineSegment(p3, p4), False)
    sketch.addGeometry(Part.LineSegment(p4, p1), False)
    _recompute()
    return f"Rectangle added to {sketch.Name} ({w} x {h} mm)."


def _action_add_circle(action, params):
    radius = _get_param(action, params, "radius")
    if radius is None:
        return "add_circle: radius required."
    sketch = _get_target_sketch(action, params)
    if sketch is None:
        return "add_circle: no sketch found (use create_sketch or specify sketch name)."

    try:
        import Part
    except Exception:
        return "add_circle failed: Part module unavailable."

    x = float(_get_param(action, params, "x", default=0.0))
    y = float(_get_param(action, params, "y", default=0.0))
    r = float(radius)
    circle = Part.Circle(App.Vector(x, y, 0), App.Vector(0, 0, 1), r)
    sketch.addGeometry(circle, False)
    _recompute()
    return f"Circle added to {sketch.Name} (r={r} mm)."


def _action_delete_object(action, params):
    name = _get_param(action, params, "name")
    if not name:
        return "delete_object: name required."
    doc = _require_doc()
    obj = doc.getObject(str(name))
    if obj is None:
        return f"delete_object: {name} not found."
    doc.removeObject(obj.Name)
    _recompute()
    return f"Deleted object: {obj.Name}."


def _action_translate_object(action, params):
    name = _get_param(action, params, "name")
    if not name:
        return "translate_object: name required."
    doc = _require_doc()
    obj = doc.getObject(str(name))
    if obj is None:
        return f"translate_object: {name} not found."
    dx = float(_get_param(action, params, "dx", default=0.0))
    dy = float(_get_param(action, params, "dy", default=0.0))
    dz = float(_get_param(action, params, "dz", default=0.0))
    placement = obj.Placement
    placement.Base = placement.Base.add(App.Vector(dx, dy, dz))
    obj.Placement = placement
    _recompute()
    return f"Translated {obj.Name} by ({dx}, {dy}, {dz}) mm."


def _action_set_visibility(action, params):
    name = _get_param(action, params, "name")
    if not name:
        return "set_visibility: name required."
    doc = _require_doc()
    obj = doc.getObject(str(name))
    if obj is None:
        return f"set_visibility: {name} not found."
    visible = _get_param(action, params, "visible")
    if visible is None:
        return "set_visibility: visible required."
    try:
        obj.ViewObject.Visibility = bool(visible)
    except Exception:
        return "set_visibility failed: ViewObject unavailable."
    return f"Visibility set for {obj.Name}: {bool(visible)}."


def _action_analyze_selection(action, params):
    try:
        from .analysis import analyze_selection
    except Exception:
        from ai.analysis import analyze_selection
    result = analyze_selection()
    summary = result.summary or ""
    count = len(getattr(result, "issues", []) or [])
    if summary:
        return f"Analysis completed: {summary}"
    return f"Analysis completed: {count} issue(s)."


def _action_optimize_splines_preview(action, params):
    try:
        from .optimization import optimize_selection
    except Exception:
        from ai.optimization import optimize_selection
    result = optimize_selection(create_preview=True)
    count = len(getattr(result, "issues", []) or [])
    return f"Spline optimization preview created ({count} issue(s) reported)."


def _action_generate_gcode(action, params):
    try:
        from ..cam.hybrid import CamJobSettings, SimpleJobSettings, generate_hybrid_gcode
    except Exception:
        from cam.hybrid import CamJobSettings, SimpleJobSettings, generate_hybrid_gcode

    model = _resolve_target_model(action, params)
    if model is None:
        return "generate_gcode: no active object or selection."

    defaults = _load_cam_defaults(params)
    merged_params = _merge_params(defaults, params)
    prefer_cam = _get_param(action, merged_params, "prefer_cam", default=True)
    output_path = _get_param(action, params, "output_path")

    cam_settings = _build_cam_settings(merged_params)
    simple_settings = _build_simple_settings(merged_params)

    result = generate_hybrid_gcode(
        model,
        operations=_parse_operations(merged_params),
        cam_settings=cam_settings,
        simple_settings=simple_settings,
        prefer_cam=bool(prefer_cam),
    )

    gcode = result.gcode or ""
    if result.engine != "cam":
        gcode = _postprocess_gcode_for_machine(
            gcode,
            profile_path=_get_param(action, merged_params, "machine_profile_path"),
            feed_rate=_get_param(action, merged_params, "feed_rate", default=cam_settings.feed_rate),
            plunge_rate=_get_param(action, merged_params, "plunge_rate", default=cam_settings.plunge_rate),
        )
    output_path = _persist_gcode(output_path, cam_settings.output_path, result.engine, gcode)
    _update_gcode_ui(gcode)

    warning_text = ""
    if result.warnings:
        warning_text = " Warnings: " + "; ".join(result.warnings)
    return f"G-code generated via {result.engine}, saved to {output_path}.{warning_text}"


def _action_cam_generate_job(action, params):
    try:
        from ..cam.hybrid import generate_hybrid_gcode
    except Exception:
        from cam.hybrid import generate_hybrid_gcode

    model = _resolve_target_model(action, params)
    if model is None:
        return "cam_generate_job: no active object or selection."

    defaults = _load_cam_defaults(params)
    merged_params = _merge_params(defaults, params)
    prefer_cam = _get_param(action, merged_params, "prefer_cam", default=True)
    output_path = _get_param(action, params, "output_path")
    cam_settings = _build_cam_settings(merged_params)
    simple_settings = _build_simple_settings(merged_params)
    operations = _parse_operations(merged_params)

    result = generate_hybrid_gcode(
        model,
        operations=operations,
        cam_settings=cam_settings,
        simple_settings=simple_settings,
        prefer_cam=bool(prefer_cam),
    )

    gcode = result.gcode or ""
    if result.engine != "cam":
        gcode = _postprocess_gcode_for_machine(
            gcode,
            profile_path=_get_param(action, merged_params, "machine_profile_path"),
            feed_rate=_get_param(action, merged_params, "feed_rate", default=cam_settings.feed_rate),
            plunge_rate=_get_param(action, merged_params, "plunge_rate", default=cam_settings.plunge_rate),
        )
    output_path = _persist_gcode(output_path, cam_settings.output_path, result.engine, gcode)
    _update_gcode_ui(gcode)

    job_name = ""
    if result.job is not None:
        job_name = getattr(result.job, "Name", "") or getattr(result.job, "Label", "")
    job_note = f" Job={job_name}." if job_name else ""
    warning_text = ""
    if result.warnings:
        warning_text = " Warnings: " + "; ".join(result.warnings)
    return f"CAM job generated via {result.engine}, saved to {output_path}.{job_note}{warning_text}"


def _action_dxf_generate_gcode(action, params):
    try:
        from ..cam.dxf_import import generate_gcode_from_dxf
    except Exception:
        from cam.dxf_import import generate_gcode_from_dxf

    dxf_path = _get_param(action, params, "dxf_path") or _get_param(action, params, "path")
    if not dxf_path:
        return "dxf_generate_gcode: dxf_path required."

    defaults = _load_cam_defaults(params)
    merged_params = _merge_params(defaults, params)
    output_path = _get_param(action, params, "output_path")
    update_ui = bool(_get_param(action, params, "update_ui", default=False))

    import_settings = _build_dxf_import_settings(merged_params)
    simple_settings = _build_simple_settings(merged_params)
    gcode = generate_gcode_from_dxf(str(dxf_path), simple_settings, import_settings)
    output_path = _persist_gcode(output_path, "", "simple", gcode)
    if update_ui:
        _update_gcode_ui(gcode)

    data = {
        "gcode": gcode,
        "output_path": output_path,
        "line_count": len([line for line in gcode.splitlines() if line.strip()]),
        "source_path": str(dxf_path),
        "engine": "simple",
        "import_settings": asdict(import_settings),
        "simple_settings": asdict(simple_settings),
    }
    return {
        "message": f"DXF G-code generated via simple engine, saved to {output_path}.",
        "errors": [],
        "data": data,
    }


def _action_cam_postprocess(action, params):
    gcode = _get_param(action, params, "gcode")
    if not gcode:
        return "cam_postprocess: gcode required."
    profile_path = _get_param(action, params, "machine_profile_path")
    feed_rate = _to_float(_get_param(action, params, "feed_rate"))
    plunge_rate = _to_float(_get_param(action, params, "plunge_rate"))
    try:
        result = grbl_postprocess_gcode(
            str(gcode),
            machine_profile_path=str(profile_path) if profile_path else None,
            feed_rate=feed_rate,
            plunge_rate=plunge_rate,
        )
    except Exception as exc:
        return f"cam_postprocess: {exc}"

    processed = result.get("gcode", "") if isinstance(result, dict) else ""
    if not processed:
        return "cam_postprocess: postprocessor produced empty output."

    return {
        "message": (
            f"Postprocessed G-code ({result.get('line_count', 0)} lines, "
            f"safe_z={result.get('safe_z', 0):.3f}, "
            f"injected_F={result.get('injected_feed_count', 0)}, "
            f"replaced_F0={result.get('replaced_f0_count', 0)})."
        ),
        "errors": [],
        "data": result,
    }


def _action_machine_autoconnect(action, params):
    """Scan serial ports and connect to GRBL directly (no double-open).

    Instead of probing with a separate serial connection (which resets the
    controller via DTR and triggers Alarm), we try sender.connect() directly
    on each candidate port.  This avoids the close-reopen cycle that causes
    spurious GRBL resets.  After connecting, we auto-unlock ($X) if the
    machine is in Alarm state.
    """
    import time

    try:
        from serial.tools import list_ports as _list_ports
    except Exception:
        try:
            from ..vendor import import_serial as _import_serial
            _import_serial()
            from serial.tools import list_ports as _list_ports
        except Exception:
            from vendor import import_serial as _import_serial
            _import_serial()
            from serial.tools import list_ports as _list_ports

    sender = _get_sender()
    if sender is None:
        return "machine_autoconnect: no sender available."

    if sender.is_connected():
        # Already connected – just check state and unlock if needed
        sender.poll()
        sender.request_status()
        time.sleep(0.15)
        sender.poll()
        status = sender.get_status() or {}
        if status.get("state", "").lower() == "alarm":
            sender.send_line("$X")
            time.sleep(0.15)
            sender.poll()
            sender.request_status()
            time.sleep(0.15)
            sender.poll()
            status = sender.get_status() or {}
        state = status.get("state", "?")
        pos = status.get("MPos", status.get("WPos", "?"))
        profile_note = _auto_refresh_machine_profile(sender)
        return f"Already connected. State: {state} | Pos: {pos}{profile_note}"

    ports = list(_list_ports.comports())
    # Filter out Bluetooth
    filtered = []
    for port in ports:
        text = " ".join([str(port.device or ""), str(port.description or "")]).lower()
        if "bluetooth" in text:
            continue
        filtered.append(port)

    if not filtered:
        return "machine_autoconnect: no serial ports found."

    # Rank: prefer USB serial devices
    def _score(port):
        text = " ".join([
            str(port.device or ""), str(port.description or ""),
            str(getattr(port, "manufacturer", "") or ""),
            str(getattr(port, "hwid", "") or ""),
        ]).lower()
        s = 0
        if "usb" in text:
            s += 10
        if "serial" in text:
            s += 5
        if "ch340" in text or "cp210" in text or "ftdi" in text:
            s += 8
        return -s
    filtered.sort(key=_score)

    # Try connecting directly via sender (single open, no probe-then-reopen)
    last_error = None
    for port in filtered:
        device = port.device
        try:
            sender.connect(device)
        except Exception as exc:
            last_error = str(exc)
            continue

        # Connected! Now poll status and auto-unlock if in Alarm
        time.sleep(0.2)
        sender.poll()
        sender.request_status()
        time.sleep(0.15)
        sender.poll()
        status = sender.get_status() or {}
        state = status.get("state", "?")

        if state.lower() == "alarm":
            sender.send_line("$X")
            time.sleep(0.15)
            sender.poll()
            sender.request_status()
            time.sleep(0.15)
            sender.poll()
            status = sender.get_status() or {}
            state = status.get("state", "?")

        pos = status.get("MPos", status.get("WPos", "?"))
        profile_note = _auto_refresh_machine_profile(sender)
        return f"Auto connected to {device}. State: {state} | Pos: {pos}{profile_note}"

    return f"machine_autoconnect: no GRBL controller found. Last error: {last_error}"


def _action_machine_travel_test(action, params):
    """XY travel test using machine coordinates (G53) with safety checks."""
    import time

    sender = _get_sender()
    if sender is None:
        return "machine_travel_test: no sender available."
    if not sender.is_connected():
        return "machine_travel_test: not connected."
    if sender.is_streaming():
        return "machine_travel_test: sender busy."

    sender.poll()
    sender.request_status()
    time.sleep(0.15)
    sender.poll()
    status = sender.get_status() or {}
    state = status.get("state", "").lower()
    if state == "alarm":
        return "machine_travel_test: alarm active. Unlock and home first."

    max_x = float(_get_param(action, params, "max_x", default=0))
    max_y = float(_get_param(action, params, "max_y", default=0))
    margin = float(_get_param(action, params, "margin", default=5.0))
    feed = float(_get_param(action, params, "feed", default=600))

    if max_x <= 0 or max_y <= 0:
        return "machine_travel_test: max_x and max_y required (machine travel limits in mm)."

    target_x = max_x - margin
    target_y = max_y - margin
    if target_x <= 0 or target_y <= 0:
        return f"machine_travel_test: margin ({margin}) too large for limits ({max_x}x{max_y})."

    lines = [
        "G90",
        "G21",
        f"G53 G1 X0 Y0 F{feed:.0f}",
        f"G53 G1 X{target_x:.3f} F{feed:.0f}",
        "G53 G1 X0",
        f"G53 G1 Y{target_y:.3f} F{feed:.0f}",
        "G53 G1 Y0",
    ]
    sender.start_stream(lines)
    return f"Travel test started: X0→{target_x:.1f}→0, Y0→{target_y:.1f}→0 at F{feed:.0f} (margin {margin}mm)."


def _action_machine_z_speed_test(action, params):
    """Z axis speed test using relative coordinates (G91)."""
    import time

    sender = _get_sender()
    if sender is None:
        return "machine_z_speed_test: no sender available."
    if not sender.is_connected():
        return "machine_z_speed_test: not connected."
    if sender.is_streaming():
        return "machine_z_speed_test: sender busy."

    sender.poll()
    sender.request_status()
    time.sleep(0.15)
    sender.poll()
    status = sender.get_status() or {}
    state = status.get("state", "").lower()
    if state == "alarm":
        return "machine_z_speed_test: alarm active. Unlock and home first."

    step = float(_get_param(action, params, "step", default=5.0))
    feed = float(_get_param(action, params, "feed", default=300))
    direction = int(_get_param(action, params, "direction", default=-1))
    if direction >= 0:
        direction = 1
    else:
        direction = -1

    distance = direction * step
    lines = [
        "G91 G21",
        f"G1 Z{distance:.3f} F{feed:.0f}",
        f"G0 Z{-distance:.3f}",
        "G90",
    ]
    sender.start_stream(lines)
    return f"Z speed test: {step:.1f}mm at F{feed:.0f} (direction {'+'if direction > 0 else '-'})."


def _action_create_document(action, params):
    """Create a new FreeCAD document.

    Note: App.newDocument() may not be thread-safe in all FreeCAD builds.
    If it crashes, the user should create the document manually (Ctrl+N).
    """
    if App is None:
        return "create_document: FreeCAD not available."
    name = _get_param(action, params, "name", default="Unnamed")
    try:
        doc = App.newDocument(str(name))
    except Exception as exc:
        return f"create_document failed: {exc}. Please create document manually (Ctrl+N)."
    if doc is None:
        return "create_document: FreeCAD returned None. Please create document manually (Ctrl+N)."
    return f"Document created: {doc.Label}"


def _action_machine_home(action, params):
    """Home all axes synchronously — waits for GRBL 'ok' before returning.

    Uses send_and_collect to block until homing is complete (up to 60s).
    After homing, polls status to return the actual home position.
    """
    import time

    sender = _get_sender()
    if sender is None:
        return "machine_home: no sender available."
    if not sender.is_connected():
        return "machine_home: not connected."
    if sender.is_streaming():
        return "machine_home: sender busy (streaming)."

    # Send $H and wait for completion (homing can take 30-60s)
    lines = sender.send_and_collect("$H", timeout=60.0)

    # Check for errors in the response
    for line in lines:
        if "error" in line.lower() or "alarm" in line.lower():
            return f"machine_home: homing failed: {line}"

    # Poll status to get the actual home position
    time.sleep(0.3)
    sender.poll()
    sender.request_status()
    time.sleep(0.3)
    sender.poll()
    status = sender.get_status() or {}
    state = status.get("state", "?")
    pos = status.get("MPos", status.get("WPos", "?"))

    return f"Homing complete. State: {state} | Pos: {pos}"


def _action_machine_read_settings(action, params):
    """Read GRBL $$ settings and return them as structured data."""
    sender = _get_sender()
    if sender is None:
        return "machine_read_settings: no sender available."
    if not sender.is_connected():
        return "machine_read_settings: not connected."
    if sender.is_streaming():
        return "machine_read_settings: sender busy (streaming)."

    settings = grbl_read_grbl_settings(sender)
    if not settings:
        return "machine_read_settings: no response from GRBL."

    # Build human-readable summary of key settings
    SETTING_NAMES = {
        "$0": "step_pulse_us",
        "$1": "step_idle_delay_ms",
        "$2": "step_port_invert",
        "$3": "direction_port_invert",
        "$4": "step_enable_invert",
        "$5": "limit_pins_invert",
        "$6": "probe_pin_invert",
        "$10": "status_report_mask",
        "$11": "junction_deviation_mm",
        "$12": "arc_tolerance_mm",
        "$13": "report_inches",
        "$20": "soft_limits",
        "$21": "hard_limits",
        "$22": "homing_cycle",
        "$23": "homing_dir_invert",
        "$24": "homing_feed_mm_min",
        "$25": "homing_seek_mm_min",
        "$26": "homing_debounce_ms",
        "$27": "homing_pull_off_mm",
        "$30": "max_spindle_rpm",
        "$31": "min_spindle_rpm",
        "$32": "laser_mode",
        "$100": "x_steps_per_mm",
        "$101": "y_steps_per_mm",
        "$102": "z_steps_per_mm",
        "$110": "x_max_rate_mm_min",
        "$111": "y_max_rate_mm_min",
        "$112": "z_max_rate_mm_min",
        "$120": "x_acceleration_mm_sec2",
        "$121": "y_acceleration_mm_sec2",
        "$122": "z_acceleration_mm_sec2",
        "$130": "x_max_travel_mm",
        "$131": "y_max_travel_mm",
        "$132": "z_max_travel_mm",
    }

    parts = []
    for key in sorted(settings.keys(), key=lambda k: int(k.replace("$", "")) if k.replace("$", "").isdigit() else 999):
        name = SETTING_NAMES.get(key, "")
        label = f"{key}({name})" if name else key
        parts.append(f"{label}={settings[key]}")
    profile_note = _auto_refresh_machine_profile(sender, settings=settings)
    return "GRBL Settings: " + " | ".join(parts) + profile_note


def _action_machine_probe_z(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_probe_z: no sender available."
    if not sender.is_connected():
        return "machine_probe_z: not connected."
    if sender.is_streaming():
        return "machine_probe_z: sender busy (streaming)."
    if not _require_machine_confirm(action, params, "machine_probe_z"):
        return "machine_probe_z: confirm=true required."

    profile, _ = grbl_load_machine_profile(None)
    probe_config = _extract_probe_config(profile)

    if not _has_param(action, params, "block_height"):
        return "machine_probe_z: block_height required."
    block_height = _to_float(_get_param(action, params, "block_height"))
    if block_height is None:
        return "machine_probe_z: block_height must be numeric."
    if block_height <= 0.0:
        return "machine_probe_z: block_height must be > 0."

    max_depth = _to_float(_get_param(action, params, "max_depth", default=-30.0))
    if max_depth is None:
        max_depth = -30.0
    if max_depth >= 0.0:
        return "machine_probe_z: max_depth must be negative (probing down)."

    feed = _to_float(_get_param(action, params, "feed"))
    if feed is None:
        feed = _to_float(probe_config.get("probe_feed"))
    if feed is None:
        feed = 50.0
    if feed <= 0.0:
        return "machine_probe_z: feed must be > 0."

    retract = _to_float(_get_param(action, params, "retract"))
    if retract is None:
        retract = _to_float(probe_config.get("retract_height"))
    if retract is None:
        retract = 3.0
    if retract < 0.0:
        return "machine_probe_z: retract must be >= 0."

    status_before = _read_machine_status(sender)
    state = str((status_before or {}).get("state", "")).strip().lower()
    if state != "idle":
        return f"machine_probe_z: machine must be Idle, got '{state or '?'}'."
    if _status_probe_pin_triggered(status_before):
        return "machine_probe_z: probe pin already triggered (ALARM:5). Remove touch plate/check wiring."

    probe_timeout = (abs(max_depth) / feed) * 60.0 + 10.0
    probe_command = f"G91 G38.2 Z{max_depth:.3f} F{feed:.3f}"

    try:
        probe_lines = sender.send_and_collect(probe_command, timeout=probe_timeout)
    except Exception as exc:
        return f"machine_probe_z: probing command failed: {exc}"
    finally:
        try:
            sender.send_and_collect("G90", timeout=1.5)
        except Exception:
            pass

    prb = None
    alarm_line = ""
    for line in probe_lines:
        text = str(line or "").strip()
        if not alarm_line and text.upper().startswith("ALARM:"):
            alarm_line = text
        parsed = _parse_probe_response_line(text)
        if parsed is not None:
            prb = parsed

    if alarm_line.startswith("ALARM:5"):
        return "machine_probe_z: probe already triggered at start (ALARM:5). Remove plate/check wiring."

    if alarm_line.startswith("ALARM:4") or (prb is not None and int(prb["success"]) == 0):
        _unlock_after_probe_fail(sender)
        return "machine_probe_z: probing failed (no contact, ALARM:4). Machine unlocked with $X."

    if prb is None:
        if alarm_line:
            return f"machine_probe_z: probing failed: {alarm_line}"
        return "machine_probe_z: probing failed (missing [PRB:x,y,z:s] response)."

    if int(prb["success"]) != 1:
        _unlock_after_probe_fail(sender)
        return "machine_probe_z: probing failed (probe status != 1). Machine unlocked with $X."

    if retract > 0.0:
        try:
            retract_timeout = max(2.0, (retract / max(feed, 1.0)) * 60.0 + 2.0)
            retract_lines = sender.send_and_collect(f"G91 G0 Z{retract:.3f}", timeout=retract_timeout)
        except Exception as exc:
            return f"machine_probe_z: retract failed: {exc}"
        finally:
            try:
                sender.send_and_collect("G90", timeout=1.5)
            except Exception:
                pass
        retract_error = next(
            (str(line).strip() for line in retract_lines if str(line).strip().lower().startswith(("error", "alarm"))),
            "",
        )
        if retract_error:
            return f"machine_probe_z: retract failed: {retract_error}"

    set_zero_command = f"G10 L20 P1 Z{block_height:.3f}"
    try:
        set_zero_lines = sender.send_and_collect(set_zero_command, timeout=2.0)
    except Exception as exc:
        return f"machine_probe_z: failed to set Z zero: {exc}"
    set_zero_error = next(
        (str(line).strip() for line in set_zero_lines if str(line).strip().lower().startswith(("error", "alarm"))),
        "",
    )
    if set_zero_error:
        return f"machine_probe_z: failed to set Z zero: {set_zero_error}"

    status_after = _read_machine_status(sender)
    work_pos = _parse_position((status_after or {}).get("WPos"))

    return {
        "message": (
            f"Z probe successful at X{prb['x']:.3f} Y{prb['y']:.3f} Z{prb['z']:.3f}. "
            f"Applied {set_zero_command}."
        ),
        "errors": [],
        "data": {
            "success": True,
            "probe_position": {"x": prb["x"], "y": prb["y"], "z": prb["z"]},
            "block_height": float(block_height),
            "new_z_zero": "Z0 is now at workpiece surface",
            "work_position": work_pos,
        },
    }


def _action_machine_probe_config(action, params):
    has_updates = any(_has_param(action, params, key) for key in ("block_height", "probe_feed", "retract"))
    profile, profile_path = grbl_load_machine_profile(None)
    profile_data = dict(profile or {})
    current = _extract_probe_config(profile_data)

    if not has_updates:
        return {
            "message": "Probe configuration loaded.",
            "errors": [],
            "data": {
                "probe": current,
                "profile_path": profile_path,
                "probe_pin_invert": _probe_pin_invert((profile_data.get("settings") or {})),
            },
        }

    updated = dict(current)
    if _has_param(action, params, "block_height"):
        block_height = _to_float(_get_param(action, params, "block_height"))
        if block_height is None or block_height <= 0.0:
            return "machine_probe_config: block_height must be > 0."
        updated["block_height"] = float(block_height)
    if _has_param(action, params, "probe_feed"):
        probe_feed = _to_float(_get_param(action, params, "probe_feed"))
        if probe_feed is None or probe_feed <= 0.0:
            return "machine_probe_config: probe_feed must be > 0."
        updated["probe_feed"] = float(probe_feed)
    if _has_param(action, params, "retract"):
        retract = _to_float(_get_param(action, params, "retract"))
        if retract is None or retract < 0.0:
            return "machine_probe_config: retract must be >= 0."
        updated["retract_height"] = float(retract)

    profile_data["probe"] = updated
    saved_path = grbl_save_machine_profile(profile_data, profile_path or None)
    return {
        "message": f"Probe configuration saved: {saved_path}",
        "errors": [],
        "data": {
            "probe": updated,
            "profile_path": saved_path,
            "probe_pin_invert": _probe_pin_invert((profile_data.get("settings") or {})),
        },
    }


def _action_machine_identify(action, params):
    """Identify machine: read settings, version, status → build machine profile."""
    import time

    sender = _get_sender()
    if sender is None:
        return "machine_identify: no sender available."
    if not sender.is_connected():
        return "machine_identify: not connected."
    if sender.is_streaming():
        return "machine_identify: sender busy (streaming)."

    profile = {}

    # 1) Read $$ settings
    settings_lines = sender.send_and_collect("$$", timeout=2.0)
    settings = {}
    for line in settings_lines:
        line = line.strip()
        if line.startswith("$") and "=" in line:
            key, _, value = line.partition("=")
            settings[key.strip()] = value.strip()
    profile["settings"] = settings

    # 2) Read $I (build info)
    time.sleep(0.1)
    info_lines = sender.send_and_collect("$I", timeout=1.5)
    profile["build_info"] = [l.strip() for l in info_lines if l.strip()]

    # 3) Get current status
    time.sleep(0.1)
    sender.poll()
    sender.request_status()
    deadline = time.time() + 0.5
    while time.time() < deadline:
        sender.poll()
        status = sender.get_status()
        if status and status.get("state", "?") != "?":
            break
        time.sleep(0.05)
    status = sender.get_status() or {}
    profile["status"] = status

    # 4) Extract machine capabilities
    capabilities = {}

    # Work area
    def _float(key, default=0.0):
        try:
            return float(settings.get(key, default))
        except (ValueError, TypeError):
            return default

    capabilities["work_area"] = {
        "x_mm": _float("$130"),
        "y_mm": _float("$131"),
        "z_mm": _float("$132"),
    }
    capabilities["max_feed_rates"] = {
        "x_mm_min": _float("$110"),
        "y_mm_min": _float("$111"),
        "z_mm_min": _float("$112"),
    }
    capabilities["acceleration"] = {
        "x_mm_sec2": _float("$120"),
        "y_mm_sec2": _float("$121"),
        "z_mm_sec2": _float("$122"),
    }
    capabilities["steps_per_mm"] = {
        "x": _float("$100"),
        "y": _float("$101"),
        "z": _float("$102"),
    }
    capabilities["soft_limits"] = _float("$20") == 1.0
    capabilities["hard_limits"] = _float("$21") == 1.0
    capabilities["homing_enabled"] = _float("$22") == 1.0
    capabilities["homing_dir_invert"] = int(_float("$23"))
    capabilities["laser_mode"] = _float("$32") == 1.0
    capabilities["spindle"] = {
        "max_rpm": _float("$30"),
        "min_rpm": _float("$31"),
    }
    capabilities["report_inches"] = _float("$13") == 1.0

    profile["capabilities"] = capabilities

    # 5) Build summary string
    wa = capabilities["work_area"]
    mf = capabilities["max_feed_rates"]
    sp = capabilities["spindle"]
    state = status.get("state", "?")
    pos = status.get("MPos", status.get("WPos", "?"))

    summary_parts = [
        f"State: {state}",
        f"Pos: {pos}",
        f"Work Area: X={wa['x_mm']}mm Y={wa['y_mm']}mm Z={wa['z_mm']}mm",
        f"Max Feed: X={mf['x_mm_min']} Y={mf['y_mm_min']} Z={mf['z_mm_min']} mm/min",
        f"Spindle: {sp['min_rpm']}-{sp['max_rpm']} RPM",
        f"Soft Limits: {'ON' if capabilities['soft_limits'] else 'OFF'}",
        f"Hard Limits: {'ON' if capabilities['hard_limits'] else 'OFF'}",
        f"Homing: {'ON' if capabilities['homing_enabled'] else 'OFF'}",
        f"Laser Mode: {'ON' if capabilities['laser_mode'] else 'OFF'}",
    ]
    if profile["build_info"]:
        summary_parts.append(f"Build: {'; '.join(profile['build_info'][:3])}")

    return " | ".join(summary_parts)


def _action_machine_connect(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_connect: RouterKing UI not available."
    port = _get_param(action, params, "port")
    if not port:
        return "machine_connect: port required."
    baudrate = _get_param(action, params, "baudrate", default=115200)
    sender.connect(str(port), int(baudrate))
    profile_note = _auto_refresh_machine_profile(sender)
    return f"Machine connected on {port} (baud {baudrate}).{profile_note}"


def _action_machine_disconnect(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_disconnect: RouterKing UI not available."
    sender.disconnect()
    return "Machine disconnected."


def _action_machine_send_line(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_send_line: RouterKing UI not available."
    if not _require_machine_confirm(action, params, "machine_send_line"):
        return "machine_send_line: confirm=true required."
    line = _get_param(action, params, "line")
    if not line:
        return "machine_send_line: line required."
    sender.send_line(str(line))
    return f"Line sent: {line}"


def _action_machine_stream_file(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_stream_file: RouterKing UI not available."
    if not _require_machine_confirm(action, params, "machine_stream_file"):
        return "machine_stream_file: confirm=true required."
    path = _get_param(action, params, "path")
    if not path:
        return "machine_stream_file: path required."
    lines = _read_gcode_file(str(path))
    if not lines:
        return "machine_stream_file: no G-code lines found."
    profile_path = _get_param(action, params, "machine_profile_path")
    profile, _ = grbl_load_machine_profile(str(profile_path) if profile_path else None)
    status = grbl_read_machine_status(sender)
    settings = grbl_read_grbl_settings(sender)
    report = grbl_validate_gcode(
        lines,
        machine_profile=profile,
        grbl_settings=settings,
        status=status,
        machine_profile_path=str(profile_path) if profile_path else None,
    )
    if not report.get("valid", False):
        first = (report.get("errors") or [{}])[0]
        reason = first.get("reason") or "G-code is unsafe."
        line_no = first.get("line", "?")
        return f"machine_stream_file: validation failed on line {line_no}: {reason}"
    sender.start_stream(lines)
    return f"Streaming started: {path} ({len(lines)} lines, est {report.get('estimated_time_seconds', 0)}s)."


def _action_machine_validate_gcode(action, params):
    sender = _get_sender()
    gcode = _get_param(action, params, "gcode")
    if not gcode:
        return "machine_validate_gcode: gcode required."

    lines = _prepare_gcode_lines(str(gcode))
    if not lines:
        return "machine_validate_gcode: no G-code lines found."

    profile_path = _get_param(action, params, "machine_profile_path")
    try:
        profile, _ = grbl_load_machine_profile(str(profile_path) if profile_path else None)
        status = grbl_read_machine_status(sender) if sender is not None else {}
        settings = grbl_read_grbl_settings(sender) if sender is not None else {}
        report = grbl_validate_gcode(
            lines,
            machine_profile=profile,
            grbl_settings=settings,
            status=status,
            machine_profile_path=str(profile_path) if profile_path else None,
        )
    except Exception as exc:
        return f"machine_validate_gcode: {exc}"

    bbox = report.get("bounding_box") or {"x": [0.0, 0.0], "y": [0.0, 0.0], "z": [0.0, 0.0]}
    if report.get("valid"):
        message = (
            "G-code validation passed "
            f"({report.get('move_count', 0)} move(s), "
            f"~{report.get('estimated_time_seconds', 0)}s). "
            f"Work bbox: X[{bbox['x'][0]:.3f}, {bbox['x'][1]:.3f}] "
            f"Y[{bbox['y'][0]:.3f}, {bbox['y'][1]:.3f}] "
            f"Z[{bbox['z'][0]:.3f}, {bbox['z'][1]:.3f}]"
        )
        errors = []
    else:
        first = (report.get("errors") or [{}])[0]
        reason = first.get("reason") or "Validation failed."
        message = f"G-code validation failed: {reason}"
        errors = [f"line {item.get('line', '?')}: {item.get('reason', '')}" for item in (report.get("errors") or [])]

    return {
        "message": message,
        "errors": errors,
        "data": report,
    }


def _action_machine_stream_gcode(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_stream_gcode: RouterKing UI not available."
    if not _require_machine_confirm(action, params, "machine_stream_gcode"):
        return "machine_stream_gcode: confirm=true required."
    gcode = _get_param(action, params, "gcode")
    if not gcode:
        return "machine_stream_gcode: gcode required."
    lines = _prepare_gcode_lines(str(gcode))
    if not lines:
        return "machine_stream_gcode: no G-code lines found."
    profile_path = _get_param(action, params, "machine_profile_path")
    try:
        profile, _ = grbl_load_machine_profile(str(profile_path) if profile_path else None)
        status = grbl_read_machine_status(sender)
        settings = grbl_read_grbl_settings(sender)
        report = grbl_validate_gcode(
            lines,
            machine_profile=profile,
            grbl_settings=settings,
            status=status,
            machine_profile_path=str(profile_path) if profile_path else None,
        )
    except Exception as exc:
        return f"machine_stream_gcode: validation failed: {exc}"
    if not report.get("valid", False):
        first = (report.get("errors") or [{}])[0]
        reason = first.get("reason") or "G-code is unsafe."
        line_no = first.get("line", "?")
        return f"machine_stream_gcode: validation failed on line {line_no}: {reason}"
    sender.start_stream(lines)
    return f"Streaming started ({len(lines)} lines, est {report.get('estimated_time_seconds', 0)}s)."


def _action_machine_calculate_offset(action, params):
    bounding_box = _get_param(action, params, "bounding_box")
    if not isinstance(bounding_box, dict):
        return "machine_calculate_offset: bounding_box required."

    sender = _get_sender()
    status = grbl_read_machine_status(sender) if sender is not None else {}
    settings = grbl_read_grbl_settings(sender) if sender is not None else {}

    profile_path = _get_param(action, params, "machine_profile_path")
    profile, _ = grbl_load_machine_profile(str(profile_path) if profile_path else None)
    try:
        limits, _ = grbl_resolve_machine_limits(profile, settings)
    except Exception as exc:
        return f"machine_calculate_offset: {exc}"

    current_machine_position = _get_param(action, params, "current_machine_position")
    if current_machine_position is None and isinstance(status, dict):
        current_machine_position = status.get("MPos")
    desired_workpiece_corner = _get_param(action, params, "desired_workpiece_corner", default={})
    safety_margin = float(_get_param(action, params, "safety_margin_mm", default=5.0))

    result = calculate_g54_offset(
        bounding_box=bounding_box,
        limits=limits,
        current_machine_position=current_machine_position,
        desired_workpiece_corner=desired_workpiece_corner if isinstance(desired_workpiece_corner, dict) else {},
        safety_margin_mm=safety_margin,
    )
    if not result.get("fits", False):
        warning_text = "; ".join(result.get("warnings") or ["Toolpath does not fit machine limits."])
        return {
            "message": f"machine_calculate_offset: {warning_text}",
            "errors": [warning_text],
            "data": result,
        }

    g10 = result.get("g10_command")
    if g10:
        message = f"Calculated G54 offset. Apply with: {g10}"
    else:
        message = "Calculated G54 offset range, but current machine position is missing so G10 command was not generated."
    return {
        "message": message,
        "errors": [],
        "data": result,
    }


def _action_machine_feed_hold(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_feed_hold: RouterKing UI not available."
    if not _require_machine_confirm(action, params, "machine_feed_hold"):
        return "machine_feed_hold: confirm=true required."
    sender.send_realtime_command("!")
    return "Feed hold requested."


def _action_machine_resume(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_resume: RouterKing UI not available."
    if not _require_machine_confirm(action, params, "machine_resume"):
        return "machine_resume: confirm=true required."
    sender.send_realtime_command("~")
    return "Resume requested."


def _action_machine_stop(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_stop: RouterKing UI not available."
    if not _require_machine_confirm(action, params, "machine_stop"):
        return "machine_stop: confirm=true required."
    sender.stop_stream()
    return "Streaming stopped."


def _action_machine_soft_reset(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_soft_reset: RouterKing UI not available."
    if not _require_machine_confirm(action, params, "machine_soft_reset"):
        return "machine_soft_reset: confirm=true required."
    sender.send_soft_reset()
    return "Soft reset sent."


def _action_machine_request_status(action, params):
    import time

    sender = _get_sender()
    if sender is None:
        return "machine_request_status: RouterKing UI not available."

    # Poll any pending lines first, then request fresh status
    sender.poll()
    sender.request_status()

    # Wait briefly for the GRBL response to arrive via reader thread
    deadline = time.time() + 0.5
    while time.time() < deadline:
        sender.poll()
        status = sender.get_status()
        if status and status.get("state", "?") != "?":
            break
        time.sleep(0.05)

    status = sender.get_status() or {}
    progress = sender.get_progress() or {}
    state = status.get("state", "?")
    pos_parts = []
    for key in ("MPos", "WPos"):
        if key in status:
            pos_parts.append(f"{key}:{status[key]}")
    pos_str = ", ".join(pos_parts) if pos_parts else "unknown"

    parts = [f"State: {state}", f"Position: {pos_str}"]
    if progress.get("streaming"):
        parts.append(f"Streaming: {progress['acked']}/{progress['total']} lines")
        if progress.get("paused"):
            parts.append("(paused)")
    if sender.get_disconnect_reason():
        parts.append(f"Disconnect: {sender.get_disconnect_reason()}")
    last_err = status.get("last_error") or progress.get("last_error")
    if last_err:
        parts.append(f"Error: {last_err}")

    return " | ".join(parts)


def _action_machine_jog(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_jog: RouterKing UI not available."
    if not _require_machine_confirm(action, params, "machine_jog"):
        return "machine_jog: confirm=true required."
    dx = _get_param(action, params, "dx", default=0.0)
    dy = _get_param(action, params, "dy", default=0.0)
    dz = _get_param(action, params, "dz", default=0.0)
    feed = _get_param(action, params, "feed", default=300.0)
    if float(dx) == 0.0 and float(dy) == 0.0 and float(dz) == 0.0:
        return "machine_jog: dx/dy/dz required."
    parts = []
    if float(dx) != 0.0:
        parts.append(f"X{dx}")
    if float(dy) != 0.0:
        parts.append(f"Y{dy}")
    if float(dz) != 0.0:
        parts.append(f"Z{dz}")
    command = "$J=G91 " + " ".join(parts) + f" F{feed}"
    sender.send_line(command)
    return f"Jog sent: {command}"


def _postprocess_gcode_for_machine(gcode_text, *, profile_path=None, feed_rate=None, plunge_rate=None):
    if not gcode_text:
        return gcode_text
    try:
        result = grbl_postprocess_gcode(
            gcode_text,
            machine_profile_path=str(profile_path) if profile_path else None,
            feed_rate=_to_float(feed_rate),
            plunge_rate=_to_float(plunge_rate),
        )
    except Exception:
        return gcode_text
    processed = result.get("gcode") if isinstance(result, dict) else None
    return processed if isinstance(processed, str) and processed.strip() else gcode_text


def _auto_refresh_machine_profile(sender, settings=None):
    try:
        existing_profile, existing_path = grbl_load_machine_profile(None)
        had_profile = bool(existing_profile)
        settings_map = dict(settings or {}) or grbl_read_grbl_settings(sender)
        status = grbl_read_machine_status(sender)
        merged = grbl_merge_machine_profile(existing_profile, settings=settings_map, status=status)
        target_path = grbl_save_machine_profile(merged, existing_path or None)
        note = f" Profile updated: {target_path}."
        if not had_profile:
            note += " First-time profile created; run machine_identify for full characterization."
        return note
    except Exception as exc:
        return f" Profile update skipped: {exc}"


def _parse_position(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        return {"raw": text}
    try:
        return {
            "x": float(parts[0]),
            "y": float(parts[1]),
            "z": float(parts[2]),
        }
    except Exception:
        return {"raw": text}


def _parse_feed_speed(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parts = [p.strip() for p in text.split(",")]
    try:
        feed = float(parts[0])
    except Exception:
        return {"raw": text}
    data = {"feed": feed}
    if len(parts) > 1:
        try:
            data["spindle"] = float(parts[1])
        except Exception:
            return {"raw": text}
    return data


def _status_probe_pin_triggered(status):
    if not isinstance(status, dict):
        return False
    pins = str(status.get("Pn") or "").upper()
    return "P" in pins


def _parse_probe_response_line(line):
    match = _PRB_RESPONSE_RE.match(str(line or "").strip())
    if not match:
        return None
    try:
        return {
            "x": float(match.group("x")),
            "y": float(match.group("y")),
            "z": float(match.group("z")),
            "success": int(match.group("s")),
        }
    except Exception:
        return None


def _unlock_after_probe_fail(sender):
    if sender is None:
        return
    try:
        sender.send_and_collect("$X", timeout=2.0)
    except Exception:
        return


def _probe_pin_invert(settings):
    try:
        return int(float((settings or {}).get("$6", 0))) == 1
    except Exception:
        return False


def _extract_probe_config(profile):
    probe = dict((profile or {}).get("probe") or {})
    block_height = _to_float(probe.get("block_height"))
    probe_feed = _to_float(probe.get("probe_feed"))
    retract_height = _to_float(probe.get("retract_height"))
    return {
        "block_height": 15.0 if block_height is None else float(block_height),
        "probe_feed": 50.0 if probe_feed is None else float(probe_feed),
        "retract_height": 3.0 if retract_height is None else float(retract_height),
    }


def _get_param(action, params, key, default=None):
    if key in action:
        return action.get(key)
    if key in params:
        return params.get(key)
    return default


def _has_param(action, params, key):
    return key in action or key in params


def _require_doc():
    if App is None:
        raise RuntimeError("FreeCAD is not available.")
    doc = App.ActiveDocument
    if doc is None:
        raise RuntimeError("No active document. Please create/open a document first.")
    return doc


def _add_part_object(type_id, name):
    doc = _require_doc()
    obj_name = _unique_object_name(doc, name or type_id.replace("::", "_"))
    return doc.addObject(type_id, obj_name)


def _recompute():
    if App is None:
        return
    doc = App.ActiveDocument
    if doc is None:
        return
    try:
        doc.recompute()
    except Exception:
        pass


def _unique_object_name(doc, base):
    if doc is None:
        return base
    try:
        if doc.getObject(base) is None:
            return base
    except Exception:
        return base
    for idx in range(1, 1000):
        name = f"{base}{idx:03d}"
        try:
            if doc.getObject(name) is None:
                return name
        except Exception:
            return name
    return base


def _get_target_sketch(action, params):
    doc = _require_doc()
    sketch_name = _get_param(action, params, "sketch")
    if sketch_name:
        obj = doc.getObject(str(sketch_name))
        if _is_sketch(obj):
            return obj
    active = getattr(App, "ActiveDocument", None)
    if active is not None:
        obj = getattr(active, "ActiveObject", None)
        if _is_sketch(obj):
            return obj
    for obj in getattr(doc, "Objects", []) or []:
        if _is_sketch(obj):
            return obj
    return None


def _is_sketch(obj):
    if obj is None:
        return False
    type_id = getattr(obj, "TypeId", "")
    return "Sketcher::SketchObject" in type_id


def _attach_to_active_body(obj):
    if obj is None or App is None:
        return
    doc = App.ActiveDocument
    if doc is None:
        return
    body = getattr(doc, "ActiveObject", None)
    if body is None:
        return
    if getattr(body, "TypeId", "") == "PartDesign::Body":
        try:
            body.addObject(obj)
        except Exception:
            pass


_GCODE_WORD_RE = re.compile(r"([A-Za-z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
_PAREN_COMMENT_RE = re.compile(r"\([^)]*\)")
_EPS = 1e-9
_PRB_RESPONSE_RE = re.compile(
    r"^\[PRB:(?P<x>[+-]?(?:\d+(?:\.\d*)?|\.\d+)),(?P<y>[+-]?(?:\d+(?:\.\d*)?|\.\d+)),(?P<z>[+-]?(?:\d+(?:\.\d*)?|\.\d+)):(?P<s>[01])\]$"
)


def _prepare_gcode_lines(gcode_text):
    return [line.strip() for line in str(gcode_text or "").splitlines() if line.strip()]


def _validate_gcode_lines_for_machine(lines, sender, profile_path=None):
    if not lines:
        raise ValueError("no G-code lines found.")

    profile, profile_source = _load_machine_profile(profile_path)
    status = _read_machine_status(sender)
    settings = _read_grbl_settings(sender)
    limits, limits_source = _resolve_machine_limits(profile, settings)
    wco, offset_source = _resolve_work_offset(status, profile)
    start_work = _resolve_start_work_position(status, wco, profile)

    report = _simulate_gcode_motion(lines, start_work=start_work, wco=wco, limits=limits)
    report["limits_machine"] = limits
    report["limits_source"] = limits_source
    report["offset_source"] = offset_source
    report["profile_source"] = profile_source
    return report


def _simulate_gcode_motion(lines, *, start_work, wco, limits):
    pos = dict(start_work)
    bbox = {
        "x": [pos["x"], pos["x"]],
        "y": [pos["y"], pos["y"]],
        "z": [pos["z"], pos["z"]],
    }
    state = {
        "distance_absolute": True,
        "arc_center_absolute": False,
        "unit_scale": 1.0,  # millimeter units for validation
        "plane": "G17",
        "motion": 0,  # G0 as modal default
    }
    move_count = 0

    for line_no, raw_line in enumerate(lines, start=1):
        cleaned = _strip_gcode_comments(raw_line)
        if not cleaned:
            continue
        words = _parse_gcode_words(cleaned)
        if not words:
            continue

        axis_words: Dict[str, float] = {}
        center_words: Dict[str, float] = {}
        radius_value = None
        line_motion = None
        machine_coords_block = False

        for letter, number in words:
            if letter == "G":
                if _near(number, 0.0):
                    line_motion = 0
                elif _near(number, 1.0):
                    line_motion = 1
                elif _near(number, 2.0):
                    line_motion = 2
                elif _near(number, 3.0):
                    line_motion = 3
                elif _near(number, 17.0):
                    state["plane"] = "G17"
                elif _near(number, 18.0):
                    state["plane"] = "G18"
                elif _near(number, 19.0):
                    state["plane"] = "G19"
                elif _near(number, 20.0):
                    state["unit_scale"] = 25.4
                elif _near(number, 21.0):
                    state["unit_scale"] = 1.0
                elif _near(number, 53.0):
                    machine_coords_block = True
                elif _near(number, 54.0):
                    # Validator uses the active G54/WCO offset as requested.
                    pass
                elif any(_near(number, value) for value in (38.0, 38.2, 38.3, 38.4, 38.5)):
                    raise ValueError(
                        f"line {line_no}: G38.x probing commands are not allowed in normal G-code streaming. "
                        "Use machine_probe_z."
                    )
                elif any(_near(number, value) for value in (55.0, 56.0, 57.0, 58.0, 59.0)):
                    raise ValueError(
                        f"line {line_no}: unsupported work coordinate system G{int(round(number))}. "
                        "Validator currently supports active G54/WCO only."
                    )
                elif _near(number, 90.0):
                    state["distance_absolute"] = True
                elif _near(number, 91.0):
                    state["distance_absolute"] = False
                elif _near(number, 90.1):
                    state["arc_center_absolute"] = True
                elif _near(number, 91.1):
                    state["arc_center_absolute"] = False
            elif letter in ("X", "Y", "Z"):
                axis_words[letter.lower()] = number * state["unit_scale"]
            elif letter in ("I", "J", "K"):
                center_words[letter.lower()] = number * state["unit_scale"]
            elif letter == "R":
                radius_value = number * state["unit_scale"]

        if line_motion is not None:
            state["motion"] = line_motion
        motion = state["motion"]
        if motion not in (0, 1, 2, 3):
            continue

        target = dict(pos)
        if machine_coords_block:
            current_machine = _work_to_machine(pos, wco)
            for axis in ("x", "y", "z"):
                if axis not in axis_words:
                    continue
                value = axis_words[axis]
                if state["distance_absolute"]:
                    machine_value = value
                else:
                    machine_value = current_machine[axis] + value
                target[axis] = machine_value - wco[axis]
        else:
            for axis in ("x", "y", "z"):
                if axis not in axis_words:
                    continue
                value = axis_words[axis]
                if state["distance_absolute"]:
                    target[axis] = value
                else:
                    target[axis] += value

        if motion in (0, 1):
            if not _has_position_change(pos, target):
                continue
            _check_machine_limits(target, wco, limits, line_no, raw_line)
            _update_bbox(bbox, target)
            pos = target
            move_count += 1
            continue

        if not _has_position_change(pos, target) and not center_words and radius_value is None:
            continue

        arc_points = _build_arc_check_points(
            start=pos,
            target=target,
            plane=state["plane"],
            clockwise=(motion == 2),
            center_words=center_words,
            radius_value=radius_value,
            arc_center_absolute=state["arc_center_absolute"],
            line_no=line_no,
            raw_line=raw_line,
        )
        for point in arc_points:
            _check_machine_limits(point, wco, limits, line_no, raw_line)
            _update_bbox(bbox, point)
        pos = target
        move_count += 1

    return {
        "move_count": move_count,
        "bbox_work": bbox,
    }


def _build_arc_check_points(
    *,
    start,
    target,
    plane,
    clockwise,
    center_words,
    radius_value,
    arc_center_absolute,
    line_no,
    raw_line,
):
    u_axis, v_axis, w_axis, c1_word, c2_word = _plane_axes(plane)
    su = start[u_axis]
    sv = start[v_axis]
    eu = target[u_axis]
    ev = target[v_axis]

    if radius_value is not None:
        cu, cv = _arc_center_from_radius(
            su,
            sv,
            eu,
            ev,
            radius_value,
            clockwise=clockwise,
            line_no=line_no,
            raw_line=raw_line,
        )
    else:
        c1 = center_words.get(c1_word)
        c2 = center_words.get(c2_word)
        if c1 is None and c2 is None:
            raise ValueError(
                f"line {line_no}: arc move requires I/J/K center offsets or R radius. "
                f"Line: {raw_line.strip()}"
            )
        c1 = 0.0 if c1 is None else c1
        c2 = 0.0 if c2 is None else c2
        if arc_center_absolute:
            cu, cv = c1, c2
        else:
            cu, cv = su + c1, sv + c2

    radius = math.hypot(su - cu, sv - cv)
    if radius <= _EPS:
        raise ValueError(f"line {line_no}: invalid arc radius ~0. Line: {raw_line.strip()}")

    start_angle = math.atan2(sv - cv, su - cu)
    end_angle = math.atan2(ev - cv, eu - cu)
    full_circle = _near(su, eu) and _near(sv, ev)

    candidate_angles = [start_angle, end_angle]
    if full_circle:
        candidate_angles = [0.0, math.pi * 0.5, math.pi, math.pi * 1.5, start_angle]
    else:
        for angle in (0.0, math.pi * 0.5, math.pi, math.pi * 1.5):
            if _angle_on_sweep(angle, start_angle, end_angle, clockwise):
                candidate_angles.append(angle)

    points = []
    for angle in _unique_angles(candidate_angles):
        point = dict(start)
        point[u_axis] = cu + radius * math.cos(angle)
        point[v_axis] = cv + radius * math.sin(angle)
        point[w_axis] = start[w_axis]
        points.append(point)

    # Include end point explicitly (important for helical arcs / final position).
    points.append(dict(target))
    return points


def _arc_center_from_radius(su, sv, eu, ev, radius_value, *, clockwise, line_no, raw_line):
    radius = abs(radius_value)
    dx = eu - su
    dy = ev - sv
    chord = math.hypot(dx, dy)
    if chord <= _EPS:
        raise ValueError(
            f"line {line_no}: arc with R and identical start/end is unsupported. Line: {raw_line.strip()}"
        )
    if chord > (2.0 * radius + 1e-6):
        raise ValueError(
            f"line {line_no}: arc radius R{radius_value:g} too small for chord length. Line: {raw_line.strip()}"
        )

    mx = (su + eu) * 0.5
    my = (sv + ev) * 0.5
    h_sq = max(radius * radius - (chord * chord) * 0.25, 0.0)
    h = math.sqrt(h_sq)
    ux = -dy / chord
    uy = dx / chord
    centers = [
        (mx + ux * h, my + uy * h),
        (mx - ux * h, my - uy * h),
    ]

    deltas = []
    for center in centers:
        delta = _arc_sweep_delta(center, su, sv, eu, ev, clockwise)
        deltas.append((center, delta))
    if radius_value >= 0:
        chosen = min(deltas, key=lambda item: item[1])
    else:
        chosen = max(deltas, key=lambda item: item[1])
    return chosen[0]


def _arc_sweep_delta(center, su, sv, eu, ev, clockwise):
    cu, cv = center
    start_angle = math.atan2(sv - cv, su - cu)
    end_angle = math.atan2(ev - cv, eu - cu)
    if clockwise:
        delta = (start_angle - end_angle) % (2.0 * math.pi)
    else:
        delta = (end_angle - start_angle) % (2.0 * math.pi)
    if delta <= _EPS:
        return 2.0 * math.pi
    return delta


def _angle_on_sweep(angle, start_angle, end_angle, clockwise):
    if clockwise:
        total = (start_angle - end_angle) % (2.0 * math.pi)
        progress = (start_angle - angle) % (2.0 * math.pi)
    else:
        total = (end_angle - start_angle) % (2.0 * math.pi)
        progress = (angle - start_angle) % (2.0 * math.pi)
    return progress <= (total + 1e-8)


def _plane_axes(plane):
    if plane == "G18":
        return "x", "z", "y", "i", "k"
    if plane == "G19":
        return "y", "z", "x", "j", "k"
    return "x", "y", "z", "i", "j"


def _parse_gcode_words(line):
    words = []
    for match in _GCODE_WORD_RE.finditer(line):
        letter = match.group(1).upper()
        try:
            number = float(match.group(2))
        except Exception:
            continue
        words.append((letter, number))
    return words


def _strip_gcode_comments(line):
    stripped = str(line or "")
    stripped = stripped.split(";", 1)[0]
    previous = None
    while previous != stripped:
        previous = stripped
        stripped = _PAREN_COMMENT_RE.sub("", stripped)
    return stripped.strip()


def _work_to_machine(work_pos, wco):
    return {
        "x": work_pos["x"] + wco["x"],
        "y": work_pos["y"] + wco["y"],
        "z": work_pos["z"] + wco["z"],
    }


def _check_machine_limits(work_pos, wco, limits, line_no, raw_line):
    machine = _work_to_machine(work_pos, wco)
    for axis in ("x", "y", "z"):
        minimum, maximum = limits[axis]
        value = machine[axis]
        if value < (minimum - 1e-6) or value > (maximum + 1e-6):
            axis_u = axis.upper()
            raise ValueError(
                f"line {line_no}: axis {axis_u} exceeds machine limits. "
                f"Work {axis_u}={work_pos[axis]:.3f} -> Machine {axis_u}={value:.3f}, "
                f"allowed [{minimum:.3f}, {maximum:.3f}]. "
                f"Line: {raw_line.strip()}"
            )


def _update_bbox(bbox, pos):
    for axis in ("x", "y", "z"):
        bbox[axis][0] = min(bbox[axis][0], pos[axis])
        bbox[axis][1] = max(bbox[axis][1], pos[axis])


def _has_position_change(start, target):
    return any(not _near(start[axis], target[axis]) for axis in ("x", "y", "z"))


def _near(a, b, eps=1e-9):
    return abs(float(a) - float(b)) <= eps


def _read_machine_status(sender):
    if sender is None:
        return {}
    status = {}
    is_connected = bool(getattr(sender, "is_connected", lambda: False)())
    if not is_connected:
        try:
            raw = sender.get_status()
        except Exception:
            raw = None
        return dict(raw or {})

    sender.poll()
    sender.request_status()
    deadline = time.time() + 0.6
    while time.time() < deadline:
        sender.poll()
        raw = sender.get_status() or {}
        if raw:
            status = dict(raw)
            if status.get("state", "?") != "?":
                break
        time.sleep(0.05)
    return status


def _read_grbl_settings(sender):
    if sender is None:
        return {}
    if not bool(getattr(sender, "is_connected", lambda: False)()):
        return {}
    if bool(getattr(sender, "is_streaming", lambda: False)()):
        return {}
    try:
        lines = sender.send_and_collect("$$", timeout=2.0)
    except Exception:
        return {}
    settings = {}
    for line in lines or []:
        text = str(line or "").strip()
        if not text.startswith("$") or "=" not in text:
            continue
        key, _, value = text.partition("=")
        settings[key.strip()] = value.strip()
    return settings


def _load_machine_profile(profile_path=None):
    candidates = []
    if profile_path:
        candidates.append(Path(profile_path).expanduser())
    env_path = os.getenv("ROUTERKING_MACHINE_PROFILE", "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.append(Path.cwd() / "machine_profile.json")
    candidates.append(Path.home() / "machine_profile.json")

    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            return data, str(path)
    return {}, ""


def _resolve_machine_limits(profile, settings):
    limits = {}
    source = {}
    for axis, setting_key in (("x", "$130"), ("y", "$131"), ("z", "$132")):
        profile_value = _profile_travel_value(profile, axis, setting_key)
        settings_value = _to_float(settings.get(setting_key))
        value = profile_value if profile_value is not None else settings_value
        if value is None:
            raise ValueError(
                f"missing machine travel for {axis.upper()}. "
                f"Provide machine_profile.json or readable GRBL setting {setting_key}."
            )
        travel = abs(value)
        limits[axis] = (-travel, 0.0)
        source[axis] = "machine_profile.json" if profile_value is not None else "grbl_$$"

    source_text = source["x"]
    if len({source["x"], source["y"], source["z"]}) > 1:
        source_text = "machine_profile.json + grbl_$$"
    return limits, source_text


def _profile_travel_value(profile, axis, setting_key):
    if not isinstance(profile, dict):
        return None
    axis_u = axis.upper()
    axis_item = profile.get(axis) or profile.get(axis_u)
    if isinstance(axis_item, dict):
        for key in ("travel", "max_travel", "max", "size"):
            value = _to_float(axis_item.get(key))
            if value is not None:
                return value
    else:
        value = _to_float(axis_item)
        if value is not None:
            return value

    for key in (setting_key, setting_key.lstrip("$"), f"{axis}_travel", f"{axis}_max_travel", f"max_travel_{axis}"):
        value = _to_float(profile.get(key))
        if value is not None:
            return value

    for container_key in ("settings", "grbl", "grbl_settings"):
        container = profile.get(container_key)
        if isinstance(container, dict):
            value = _to_float(container.get(setting_key))
            if value is not None:
                return value
            value = _to_float(container.get(setting_key.lstrip("$")))
            if value is not None:
                return value

    limits = profile.get("limits")
    if isinstance(limits, dict):
        axis_limits = limits.get(axis) or limits.get(axis_u)
        if isinstance(axis_limits, dict):
            for key in ("travel", "max_travel", "max", "size"):
                value = _to_float(axis_limits.get(key))
                if value is not None:
                    return value
        else:
            value = _to_float(axis_limits)
            if value is not None:
                return value

    travel = profile.get("travel")
    if isinstance(travel, dict):
        value = _to_float(travel.get(axis) or travel.get(axis_u))
        if value is not None:
            return value

    capabilities = profile.get("capabilities")
    if isinstance(capabilities, dict):
        work_area = capabilities.get("work_area")
        if isinstance(work_area, dict):
            value = _to_float(work_area.get(f"{axis}_mm"))
            if value is not None:
                return value
            value = _to_float(work_area.get(axis) or work_area.get(axis_u))
            if value is not None:
                return value

    return None


def _resolve_work_offset(status, profile):
    wco = _parse_xyz_value(status.get("WCO")) if isinstance(status, dict) else None
    if wco is not None:
        return wco, "status.WCO"

    mpos = _parse_xyz_value(status.get("MPos")) if isinstance(status, dict) else None
    wpos = _parse_xyz_value(status.get("WPos")) if isinstance(status, dict) else None
    if mpos is not None and wpos is not None:
        return {
            "x": mpos["x"] - wpos["x"],
            "y": mpos["y"] - wpos["y"],
            "z": mpos["z"] - wpos["z"],
        }, "status.MPos-WPos"

    for key in ("work_offset", "wco", "g54", "g54_offset"):
        value = _parse_xyz_value(profile.get(key) if isinstance(profile, dict) else None)
        if value is not None:
            return value, f"profile.{key}"

    raise ValueError(
        "unable to determine current work offset (WCO/G54). "
        "Provide a machine profile with work_offset or ensure status includes WCO or MPos/WPos."
    )


def _resolve_start_work_position(status, wco, profile):
    if isinstance(status, dict):
        wpos = _parse_xyz_value(status.get("WPos"))
        if wpos is not None:
            return wpos
        mpos = _parse_xyz_value(status.get("MPos"))
        if mpos is not None:
            return {
                "x": mpos["x"] - wco["x"],
                "y": mpos["y"] - wco["y"],
                "z": mpos["z"] - wco["z"],
            }

    for key in ("work_position", "wpos", "position"):
        value = _parse_xyz_value(profile.get(key) if isinstance(profile, dict) else None)
        if value is not None:
            return value
    return {"x": 0.0, "y": 0.0, "z": 0.0}


def _parse_xyz_value(value):
    if value is None:
        return None
    if isinstance(value, dict):
        x = _to_float(value.get("x", value.get("X")))
        y = _to_float(value.get("y", value.get("Y")))
        z = _to_float(value.get("z", value.get("Z")))
        if x is None or y is None or z is None:
            return None
        return {"x": x, "y": y, "z": z}
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        x = _to_float(value[0])
        y = _to_float(value[1])
        z = _to_float(value[2])
        if x is None or y is None or z is None:
            return None
        return {"x": x, "y": y, "z": z}
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        if len(parts) < 3:
            return None
        x = _to_float(parts[0])
        y = _to_float(parts[1])
        z = _to_float(parts[2])
        if x is None or y is None or z is None:
            return None
        return {"x": x, "y": y, "z": z}
    return None


def _to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _unique_angles(angles):
    unique = []
    for angle in angles:
        if any(abs(angle - seen) <= 1e-8 for seen in unique):
            continue
        unique.append(angle)
    return unique


_ACTION_HANDLERS = {
    "create_part_box": _action_create_part_box,
    "create_part_cylinder": _action_create_part_cylinder,
    "create_part_sphere": _action_create_part_sphere,
    "create_sketch": _action_create_sketch,
    "add_rectangle": _action_add_rectangle,
    "add_circle": _action_add_circle,
    "delete_object": _action_delete_object,
    "translate_object": _action_translate_object,
    "set_visibility": _action_set_visibility,
    "analyze_selection": _action_analyze_selection,
    "optimize_splines_preview": _action_optimize_splines_preview,
    "generate_gcode": _action_generate_gcode,
    "cam_generate_job": _action_cam_generate_job,
    "dxf_generate_gcode": _action_dxf_generate_gcode,
    "cam_postprocess": _action_cam_postprocess,
    "machine_autoconnect": _action_machine_autoconnect,
    "machine_travel_test": _action_machine_travel_test,
    "machine_z_speed_test": _action_machine_z_speed_test,
    "create_document": _action_create_document,
    "machine_connect": _action_machine_connect,
    "machine_disconnect": _action_machine_disconnect,
    "machine_send_line": _action_machine_send_line,
    "machine_stream_file": _action_machine_stream_file,
    "machine_validate_gcode": _action_machine_validate_gcode,
    "machine_stream_gcode": _action_machine_stream_gcode,
    "machine_calculate_offset": _action_machine_calculate_offset,
    "machine_feed_hold": _action_machine_feed_hold,
    "machine_resume": _action_machine_resume,
    "machine_stop": _action_machine_stop,
    "machine_soft_reset": _action_machine_soft_reset,
    "machine_request_status": _action_machine_request_status,
    "machine_jog": _action_machine_jog,
    "machine_home": _action_machine_home,
    "machine_read_settings": _action_machine_read_settings,
    "machine_probe_z": _action_machine_probe_z,
    "machine_probe_config": _action_machine_probe_config,
    "machine_identify": _action_machine_identify,
}


def _resolve_target_model(action=None, params=None):
    params = params or {}
    if App is None:
        return None
    doc = App.ActiveDocument
    if doc is not None:
        name = _get_param(action or {}, params, "model")
        if name:
            obj = doc.getObject(str(name))
            if obj is not None:
                return obj
    try:
        from .context import get_selection_context
    except Exception:
        try:
            from ai.context import get_selection_context
        except Exception:
            get_selection_context = None
    if get_selection_context is not None:
        selection = get_selection_context()
        if selection.items:
            return selection.items[0].obj
    if doc is None:
        return None
    return getattr(doc, "ActiveObject", None)


def _write_temp_gcode(gcode_text):
    import tempfile
    import os

    fd, path = tempfile.mkstemp(prefix="routerking-ai-", suffix=".nc")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(gcode_text)
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        raise
    return path


def _write_gcode(path, gcode_text):
    with open(path, "w") as handle:
        handle.write(gcode_text)


def _build_cam_settings(params):
    try:
        from ..cam.hybrid import CamJobSettings
    except Exception:
        from cam.hybrid import CamJobSettings
    cam_settings = CamJobSettings()
    if "post_processor" in params:
        cam_settings.post_processor = str(params["post_processor"])
    if "output_path" in params and params["output_path"]:
        cam_settings.output_path = str(params["output_path"])
    for key in ("start_depth", "final_depth", "step_down", "feed_rate", "plunge_rate"):
        if key in params:
            setattr(cam_settings, _snake_to_attr(key), float(params[key]))
    if "profile_side" in params:
        cam_settings.profile_side = str(params["profile_side"])
    if "profile_direction" in params:
        cam_settings.profile_direction = str(params["profile_direction"])
    if "name" in params:
        cam_settings.name = str(params["name"])
    return cam_settings


def _build_simple_settings(params):
    try:
        from ..cam.simple_engine import SimpleJobSettings
    except Exception:
        from cam.simple_engine import SimpleJobSettings
    simple_settings = SimpleJobSettings()
    if "feed_rate" in params:
        simple_settings.feed_rate = float(params["feed_rate"])
    if "plunge_rate" in params:
        simple_settings.plunge_rate = float(params["plunge_rate"])
    if "safe_z" in params:
        simple_settings.safe_z = float(params["safe_z"])
    if "cut_z" in params:
        simple_settings.cut_z = float(params["cut_z"])
    if "start_z" in params:
        simple_settings.start_z = float(params["start_z"])
    if "pass_depth" in params:
        simple_settings.pass_depth = float(params["pass_depth"])
    if "ramp_length" in params:
        simple_settings.ramp_length = float(params["ramp_length"])
    if "lead_in" in params:
        simple_settings.lead_in = float(params["lead_in"])
    if "lead_out" in params:
        simple_settings.lead_out = float(params["lead_out"])
    if "units" in params:
        simple_settings.units = str(params["units"])
    if "spindle_speed" in params:
        simple_settings.spindle_speed = int(params["spindle_speed"])
    if "laser_power" in params:
        simple_settings.laser_power = int(params["laser_power"])
    if "start_spindle" in params:
        simple_settings.start_spindle = bool(params["start_spindle"])
    return simple_settings


def _build_dxf_import_settings(params):
    try:
        from ..cam.dxf_import import DxfImportSettings
    except Exception:
        from cam.dxf_import import DxfImportSettings

    settings = DxfImportSettings()
    for key in ("deflection", "arc_segment_angle", "merge_tolerance"):
        if key in params:
            setattr(settings, key, float(params[key]))
    if "prefer_ezdxf" in params:
        settings.prefer_ezdxf = bool(params["prefer_ezdxf"])
    if "use_freecad" in params:
        settings.use_freecad = bool(params["use_freecad"])
    return settings


def _parse_operations(params):
    ops_payload = params.get("operations")
    if not isinstance(ops_payload, list):
        return None
    try:
        from ..cam.hybrid import OperationSpec
    except Exception:
        from cam.hybrid import OperationSpec
    operations = []
    doc = App.ActiveDocument if App is not None else None
    for op in ops_payload:
        if not isinstance(op, dict):
            continue
        kind = op.get("kind") or op.get("type")
        if not kind:
            continue
        base = op.get("base")
        base_obj = None
        if isinstance(base, str) and doc is not None:
            base_obj = doc.getObject(base)
        elif base is not None:
            base_obj = base
        properties = op.get("properties") or {}
        operations.append(OperationSpec(kind=kind, base=base_obj, properties=properties))
    return operations or None


def _persist_gcode(output_path, cam_output_path, engine, gcode_text):
    path = output_path or cam_output_path or ""
    if not path:
        return _write_temp_gcode(gcode_text)
    if engine == "cam" and cam_output_path:
        return cam_output_path
    _write_gcode(path, gcode_text)
    return path


def _update_gcode_ui(gcode_text):
    try:
        from ..ui import main_dock
    except Exception:
        try:
            from ui import main_dock
        except Exception:
            return
    dock = getattr(main_dock, "_dock", None)
    if dock is None:
        return
    try:
        widget = dock.widget()
    except Exception:
        widget = None
    if widget is None:
        return
    editor = getattr(widget, "_gcode_edit", None)
    if editor is None:
        return
    try:
        editor.setPlainText(gcode_text)
    except Exception:
        return
    try:
        widget._update_preview()
    except Exception:
        pass


def _snake_to_attr(name):
    mapping = {
        "start_depth": "start_depth",
        "final_depth": "final_depth",
        "step_down": "step_down",
        "feed_rate": "feed_rate",
        "plunge_rate": "plunge_rate",
    }
    return mapping.get(name, name)


def _merge_params(defaults, overrides):
    merged = dict(defaults or {})
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        merged[key] = value
    return merged


def _load_cam_defaults(params):
    if not params:
        return {}
    use_defaults = bool(params.get("use_cam_defaults"))
    if not use_defaults:
        return {}
    defaults = _load_cam_defaults_from_ui()
    if defaults:
        return defaults
    return _load_cam_defaults_from_prefs()


def _load_cam_defaults_from_ui():
    try:
        from ..ui import main_dock
    except Exception:
        try:
            from ui import main_dock
        except Exception:
            return {}
    dock = getattr(main_dock, "_dock", None)
    if dock is None:
        return {}
    try:
        widget = dock.widget()
    except Exception:
        widget = None
    if widget is None:
        return {}
    defaults = getattr(widget, "_cam_generate_defaults", None)
    if isinstance(defaults, dict):
        return dict(defaults)
    return {}


def _load_cam_defaults_from_prefs():
    if App is None:
        return {}
    params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/CAM")
    return {
        "prefer_cam": params.GetBool("prefer_cam", True),
        "preset_name": params.GetString("preset_name", "Custom"),
        "units": params.GetString("units", "mm"),
        "feed_rate": params.GetFloat("feed_rate", 800.0),
        "plunge_rate": params.GetFloat("plunge_rate", 300.0),
        "post_processor": params.GetString("post_processor", "grbl_post"),
        "start_depth": params.GetFloat("start_depth", 0.0),
        "final_depth": params.GetFloat("final_depth", -1.0),
        "step_down": params.GetFloat("step_down", 1.0),
        "profile_side": params.GetString("profile_side", "Outside"),
        "profile_direction": params.GetString("profile_direction", "CCW"),
        "safe_z": params.GetFloat("safe_z", 5.0),
        "start_z": params.GetFloat("start_z", 0.0),
        "cut_z": params.GetFloat("cut_z", -1.0),
        "pass_depth": params.GetFloat("pass_depth", 0.0),
        "ramp_length": params.GetFloat("ramp_length", 0.0),
        "lead_in": params.GetFloat("lead_in", 0.0),
        "lead_out": params.GetFloat("lead_out", 0.0),
        "spindle_speed": params.GetInt("spindle_speed", 0),
        "laser_power": params.GetInt("laser_power", 0),
        "start_spindle": params.GetBool("start_spindle", True),
    }


def _require_machine_confirm(action, params, name):
    confirm = _get_param(action, params, "confirm", default=False)
    return bool(confirm)


def _get_sender():
    # Primary: use the global singleton (works with and without UI)
    try:
        from ..grbl.manager import get_sender as _mgr_get
    except ImportError:
        try:
            from grbl.manager import get_sender as _mgr_get
        except ImportError:
            _mgr_get = None

    if _mgr_get is not None:
        sender = _mgr_get(create=True)
        if sender is not None:
            return sender

    # Fallback: try UI dock widget (backwards compatibility)
    try:
        from ..ui import main_dock
    except Exception:
        try:
            from ui import main_dock
        except Exception:
            return None
    dock = getattr(main_dock, "_dock", None)
    if dock is None:
        return None
    try:
        widget = dock.widget()
    except Exception:
        widget = None
    if widget is None:
        return None
    return getattr(widget, "_sender", None)


def _read_gcode_file(path):
    with open(path, "r") as handle:
        return [line.strip() for line in handle.readlines() if line.strip()]
