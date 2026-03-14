"""Action execution helpers for RouterKing AI chat."""

from typing import Dict, List, Tuple

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None


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
    "machine_connect": "Connect to GRBL controller (port, baudrate?)",
    "machine_disconnect": "Disconnect from GRBL controller (no params)",
    "machine_send_line": "Send single G-code/command line (line, confirm=true)",
    "machine_stream_file": "Stream G-code file (path, confirm=true)",
    "machine_stream_gcode": "Stream G-code text (gcode, confirm=true)",
    "machine_feed_hold": "Pause motion (confirm=true)",
    "machine_resume": "Resume motion (confirm=true)",
    "machine_stop": "Stop streaming (confirm=true)",
    "machine_soft_reset": "Soft reset GRBL (confirm=true)",
    "machine_request_status": "Request status report (no params)",
    "machine_jog": "Jog move (dx?, dy?, dz?, feed, confirm=true)",
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
            message = handler(action, params)
            if message:
                results.append(message)
        except Exception as exc:
            errors.append(f"{action_type} failed: {exc}")
    return results, errors


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


def _action_machine_connect(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_connect: RouterKing UI not available."
    port = _get_param(action, params, "port")
    if not port:
        return "machine_connect: port required."
    baudrate = _get_param(action, params, "baudrate", default=115200)
    sender.connect(str(port), int(baudrate))
    return f"Machine connected on {port} (baud {baudrate})."


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
    sender.start_stream(lines)
    return f"Streaming started: {path} ({len(lines)} lines)."


def _action_machine_stream_gcode(action, params):
    sender = _get_sender()
    if sender is None:
        return "machine_stream_gcode: RouterKing UI not available."
    if not _require_machine_confirm(action, params, "machine_stream_gcode"):
        return "machine_stream_gcode: confirm=true required."
    gcode = _get_param(action, params, "gcode")
    if not gcode:
        return "machine_stream_gcode: gcode required."
    lines = [line.strip() for line in str(gcode).splitlines() if line.strip()]
    if not lines:
        return "machine_stream_gcode: no G-code lines found."
    sender.start_stream(lines)
    return f"Streaming started ({len(lines)} lines)."


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
    sender = _get_sender()
    if sender is None:
        return "machine_request_status: RouterKing UI not available."
    sender.request_status()
    status = sender.get_status() or {}
    state = status.get("state", "?")
    return f"Status requested (state={state})."


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


def _get_param(action, params, key, default=None):
    if key in action:
        return action.get(key)
    if key in params:
        return params.get(key)
    return default


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
    "machine_connect": _action_machine_connect,
    "machine_disconnect": _action_machine_disconnect,
    "machine_send_line": _action_machine_send_line,
    "machine_stream_file": _action_machine_stream_file,
    "machine_stream_gcode": _action_machine_stream_gcode,
    "machine_feed_hold": _action_machine_feed_hold,
    "machine_resume": _action_machine_resume,
    "machine_stop": _action_machine_stop,
    "machine_soft_reset": _action_machine_soft_reset,
    "machine_request_status": _action_machine_request_status,
    "machine_jog": _action_machine_jog,
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
