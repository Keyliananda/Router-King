"""RouterKing-side bridge used by the MCP tool layer."""

from __future__ import annotations

import ast
import contextlib
import io
import importlib
import traceback
from dataclasses import asdict
from typing import Any, Callable, Dict, Iterable, List, Mapping

from mcp.server.safety import log_tool_request, validate_risk
from mcp.server.schemas import ActionDefinition, coerce_action, get_action_param, make_response, normalize_actions_payload

try:
    from RouterKing.ai.actions import execute_actions_for_bridge
except Exception:  # pragma: no cover - fallback for FreeCAD import path
    from ai.actions import execute_actions_for_bridge

try:
    from RouterKing.main_thread import run_on_main_thread
except Exception:  # pragma: no cover - fallback for FreeCAD import path
    try:
        from main_thread import run_on_main_thread
    except Exception:
        def run_on_main_thread(fn, timeout=60.0):  # type: ignore[misc]
            return fn()

from . import context as context_helpers
from . import screenshots as screenshot_helpers
from .transactions import DocumentTransaction


ACTION_REGISTRY: Dict[str, ActionDefinition] = {
    "create_document": ActionDefinition(
        name="create_document",
        description="Create a new FreeCAD document.",
        optional_params=("name",),
        risk_class="modify",
    ),
    "create_part_box": ActionDefinition(
        name="create_part_box",
        description="Create Part::Box geometry.",
        required_params=("length", "width", "height"),
        optional_params=("name",),
        risk_class="modify",
    ),
    "create_part_cylinder": ActionDefinition(
        name="create_part_cylinder",
        description="Create Part::Cylinder geometry.",
        required_params=("radius", "height"),
        optional_params=("name",),
        risk_class="modify",
    ),
    "create_part_sphere": ActionDefinition(
        name="create_part_sphere",
        description="Create Part::Sphere geometry.",
        required_params=("radius",),
        optional_params=("name",),
        risk_class="modify",
    ),
    "create_sketch": ActionDefinition(
        name="create_sketch",
        description="Create a sketch object.",
        optional_params=("name",),
        risk_class="modify",
    ),
    "add_rectangle": ActionDefinition(
        name="add_rectangle",
        description="Add a rectangle to a sketch.",
        required_params=("width", "height"),
        optional_params=("sketch", "x", "y"),
        risk_class="modify",
    ),
    "add_circle": ActionDefinition(
        name="add_circle",
        description="Add a circle to a sketch.",
        required_params=("radius",),
        optional_params=("sketch", "x", "y"),
        risk_class="modify",
    ),
    "delete_object": ActionDefinition(
        name="delete_object",
        description="Delete an object from the active document.",
        required_params=("name",),
        risk_class="modify",
    ),
    "translate_object": ActionDefinition(
        name="translate_object",
        description="Translate an object by delta offsets.",
        required_params=("name",),
        optional_params=("dx", "dy", "dz"),
        risk_class="modify",
    ),
    "set_visibility": ActionDefinition(
        name="set_visibility",
        description="Set object visibility.",
        required_params=("name", "visible"),
        risk_class="modify",
    ),
    "analyze_selection": ActionDefinition(
        name="analyze_selection",
        description="Analyze the current selection.",
        risk_class="read",
    ),
    "optimize_splines_preview": ActionDefinition(
        name="optimize_splines_preview",
        description="Create a spline optimization preview.",
        risk_class="modify",
    ),
    "generate_gcode": ActionDefinition(
        name="generate_gcode",
        description="Generate G-code from the active model or selection.",
        optional_params=(
            "model",
            "operations",
            "output_path",
            "prefer_cam",
            "use_cam_defaults",
            "post_processor",
            "feed_rate",
            "plunge_rate",
            "start_depth",
            "final_depth",
            "step_down",
            "step_over",
            "profile_side",
            "profile_direction",
            "machine_profile_path",
        ),
        risk_class="modify",
    ),
    "cam_generate_job": ActionDefinition(
        name="cam_generate_job",
        description="Generate a CAM job and export G-code.",
        optional_params=(
            "model",
            "operations",
            "output_path",
            "prefer_cam",
            "use_cam_defaults",
            "post_processor",
            "feed_rate",
            "plunge_rate",
            "start_depth",
            "final_depth",
            "step_down",
            "step_over",
            "profile_side",
            "profile_direction",
            "machine_profile_path",
        ),
        risk_class="modify",
    ),
    "dxf_generate_gcode": ActionDefinition(
        name="dxf_generate_gcode",
        description="Generate simple CAM G-code from a DXF file.",
        required_params=("dxf_path",),
        optional_params=(
            "output_path",
            "update_ui",
            "use_cam_defaults",
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
        ),
        risk_class="modify",
    ),
    "cam_postprocess": ActionDefinition(
        name="cam_postprocess",
        description="Postprocess raw CAM G-code for machine-safe streaming.",
        required_params=("gcode",),
        optional_params=("machine_profile_path", "feed_rate", "plunge_rate"),
        risk_class="read",
    ),
    "machine_autoconnect": ActionDefinition(
        name="machine_autoconnect",
        description="Auto-detect serial ports and connect to GRBL controller.",
        optional_params=("confirm", "reason"),
        risk_class="machine",
    ),
    "machine_travel_test": ActionDefinition(
        name="machine_travel_test",
        description="XY travel test using machine coordinates (G53).",
        required_params=("max_x", "max_y"),
        optional_params=("margin", "feed", "confirm", "reason"),
        risk_class="machine",
    ),
    "machine_z_speed_test": ActionDefinition(
        name="machine_z_speed_test",
        description="Z axis speed test using relative movement.",
        optional_params=("step", "feed", "direction", "confirm", "reason"),
        risk_class="machine",
    ),
    "machine_connect": ActionDefinition(
        name="machine_connect",
        description="Connect to the GRBL controller.",
        required_params=("port",),
        optional_params=("baudrate", "confirm", "reason"),
        risk_class="machine",
    ),
    "machine_disconnect": ActionDefinition(
        name="machine_disconnect",
        description="Disconnect from the GRBL controller.",
        optional_params=("confirm", "reason"),
        risk_class="machine",
    ),
    "machine_send_line": ActionDefinition(
        name="machine_send_line",
        description="Send a single G-code line to the controller.",
        required_params=("line",),
        optional_params=("confirm", "reason"),
        risk_class="machine",
    ),
    "machine_stream_file": ActionDefinition(
        name="machine_stream_file",
        description="Stream a G-code file to the controller.",
        required_params=("path",),
        optional_params=("confirm", "reason", "machine_profile_path"),
        risk_class="machine",
    ),
    "machine_validate_gcode": ActionDefinition(
        name="machine_validate_gcode",
        description="Validate G-code against machine travel limits before streaming.",
        required_params=("gcode",),
        optional_params=("machine_profile_path",),
        risk_class="read",
    ),
    "machine_stream_gcode": ActionDefinition(
        name="machine_stream_gcode",
        description="Stream G-code text to the controller.",
        required_params=("gcode",),
        optional_params=("confirm", "reason", "machine_profile_path"),
        risk_class="machine",
    ),
    "machine_calculate_offset": ActionDefinition(
        name="machine_calculate_offset",
        description="Calculate optimal G54 offset + G10 command from a toolpath bounding box.",
        required_params=("bounding_box",),
        optional_params=("current_machine_position", "desired_workpiece_corner", "safety_margin_mm", "machine_profile_path"),
        risk_class="read",
    ),
    "machine_feed_hold": ActionDefinition(
        name="machine_feed_hold",
        description="Pause machine motion.",
        optional_params=("confirm", "reason"),
        risk_class="machine",
    ),
    "machine_resume": ActionDefinition(
        name="machine_resume",
        description="Resume machine motion.",
        optional_params=("confirm", "reason"),
        risk_class="machine",
    ),
    "machine_stop": ActionDefinition(
        name="machine_stop",
        description="Stop streaming and motion.",
        optional_params=("confirm", "reason"),
        risk_class="machine",
    ),
    "machine_soft_reset": ActionDefinition(
        name="machine_soft_reset",
        description="Issue a GRBL soft reset.",
        optional_params=("confirm", "reason"),
        risk_class="machine",
    ),
    "machine_request_status": ActionDefinition(
        name="machine_request_status",
        description="Request machine status.",
        optional_params=("confirm", "reason"),
        risk_class="machine",
    ),
    "machine_jog": ActionDefinition(
        name="machine_jog",
        description="Jog the machine by relative offsets.",
        required_params=("feed",),
        optional_params=("dx", "dy", "dz", "confirm", "reason"),
        risk_class="machine",
    ),
    "machine_home": ActionDefinition(
        name="machine_home",
        description="Home all axes synchronously. Blocks until homing cycle completes (up to 60s).",
        optional_params=("confirm", "reason"),
        risk_class="machine",
    ),
    "machine_read_settings": ActionDefinition(
        name="machine_read_settings",
        description="Read GRBL $$ settings and return all parameters.",
        optional_params=("confirm", "reason"),
        risk_class="machine",
    ),
    "machine_probe_z": ActionDefinition(
        name="machine_probe_z",
        description="Probe Z using a conductive touch plate and set Z0.",
        required_params=("block_height",),
        optional_params=("max_depth", "feed", "retract", "confirm", "reason"),
        risk_class="machine",
    ),
    "machine_prepare_manual_xy": ActionDefinition(
        name="machine_prepare_manual_xy",
        description="After Z probing, lower Z to a manual XY setup clearance without changing X/Y.",
        optional_params=("block_height", "descent_percent", "target_clearance", "confirm", "reason"),
        risk_class="machine",
    ),
    "machine_probe_config": ActionDefinition(
        name="machine_probe_config",
        description="Read/update persisted probe defaults in machine_profile.json.",
        optional_params=("block_height", "probe_feed", "retract"),
        risk_class="read",
    ),
    "machine_identify": ActionDefinition(
        name="machine_identify",
        description="Identify machine capabilities: work area, max feeds, spindle, limits, homing, laser mode.",
        optional_params=("confirm", "reason"),
        risk_class="machine",
    ),
}


class RouterKingBridge:
    def __init__(
        self,
        *,
        action_executor: Callable[[List[Dict[str, Any]]], Any] | None = None,
        action_registry: Mapping[str, ActionDefinition] | None = None,
        context_module: Any | None = None,
        screenshot_module: Any | None = None,
        transaction_factory: Callable[[], DocumentTransaction] | None = None,
    ) -> None:
        self._action_executor = action_executor or execute_actions_for_bridge
        self._action_registry = dict(action_registry or ACTION_REGISTRY)
        self._context = context_module or context_helpers
        self._screenshots = screenshot_module or screenshot_helpers
        self._transaction_factory = transaction_factory or DocumentTransaction
        self._console_globals: Dict[str, Any] = {"__name__": "__routerking_console__"}
        self._console_history: List[Dict[str, Any]] = []
        self._console_history_limit = 200

    def healthcheck(self) -> Dict[str, Any]:
        active_document = self.get_active_document()
        document = active_document.get("data", {}).get("document")
        errors = list(active_document.get("errors") or [])
        return {
            "freecad_available": not any("FreeCAD is not available." in error for error in errors),
            "active_document": document,
            "errors": errors,
        }

    def list_documents(self) -> Dict[str, Any]:
        payload = self._context.list_documents()
        warnings = payload.get("warnings") or []
        return make_response(
            True,
            f"Found {len(payload.get('documents') or [])} document(s).",
            data=payload,
            errors=warnings,
        )

    def get_active_document(self) -> Dict[str, Any]:
        payload = self._context.get_active_document()
        document = payload.get("document")
        warnings = payload.get("warnings") or []
        success = document is not None
        message = "Active document loaded." if document is not None else "No active document."
        return make_response(success, message, data=payload, errors=warnings)

    def get_scene_info(self) -> Dict[str, Any]:
        payload = self._context.get_scene_info()
        return make_response(
            True,
            f"Scene info collected for {payload.get('object_count', 0)} object(s).",
            data=payload,
            errors=payload.get("warnings") or [],
        )

    def get_selection_context(self) -> Dict[str, Any]:
        payload = self._context.get_selection_context()
        return make_response(
            True,
            f"Selection contains {payload.get('selection_count', 0)} object(s).",
            data=payload,
            errors=payload.get("warnings") or [],
        )

    def capture_view(self, output_path: str | None = None) -> Dict[str, Any]:
        payload = self._screenshots.capture_view(output_path=output_path)
        return make_response(
            bool(payload.get("available")),
            payload.get("message") or "Screenshot request completed.",
            data=payload,
            errors=[] if payload.get("available") else [payload.get("message") or "Screenshot unavailable."],
        )

    def cam_capabilities(self) -> Dict[str, Any]:
        """Return read-only CAM capabilities visible to MCP clients."""
        payload = run_on_main_thread(_collect_cam_capabilities)
        warnings = payload.get("warnings") or []
        return make_response(
            True,
            "CAM capabilities collected.",
            data=payload,
            errors=warnings,
        )

    def cam_list_setups(self, document: str | None = None) -> Dict[str, Any]:
        """List CAM jobs/setups in the active or named FreeCAD document."""
        payload = run_on_main_thread(lambda: _collect_cam_setups(document=document))
        warnings = payload.get("warnings") or []
        return make_response(
            True,
            f"Found {len(payload.get('setups') or [])} CAM setup(s).",
            data=payload,
            errors=warnings,
        )

    def cam_list_operations(
        self,
        setup_id: str | None = None,
        include_paths: bool = False,
        include_properties: bool = True,
    ) -> Dict[str, Any]:
        """List CAM operations, optionally scoped to a setup/job."""
        payload = run_on_main_thread(
            lambda: _collect_cam_operations(
                setup_id=setup_id,
                include_paths=bool(include_paths),
                include_properties=bool(include_properties),
            )
        )
        warnings = payload.get("warnings") or []
        return make_response(
            True,
            f"Found {len(payload.get('operations') or [])} CAM operation(s).",
            data=payload,
            errors=warnings,
        )

    def cam_inspect_operation(
        self,
        operation_id: str,
        setup_id: str | None = None,
        include_gcode: bool = False,
        gcode_lines: int = 30,
        include_properties: bool = True,
        include_warnings: bool = True,
    ) -> Dict[str, Any]:
        """Inspect one CAM operation without modifying the document."""
        payload = run_on_main_thread(
            lambda: _inspect_cam_operation(
                operation_id=operation_id,
                setup_id=setup_id,
                include_gcode=bool(include_gcode),
                gcode_lines=int(gcode_lines),
                include_properties=bool(include_properties),
                include_warnings=bool(include_warnings),
            )
        )
        warnings = payload.get("warnings") or []
        operation = payload.get("operation")
        if operation is None:
            message = payload.get("message") or f"CAM operation not found: {operation_id}"
            return make_response(False, message, data=payload, errors=warnings or [message])
        return make_response(
            True,
            f"CAM operation inspected: {operation.get('id') or operation_id}.",
            data=payload,
            errors=warnings,
        )

    def run_script(self, code: str) -> Dict[str, Any]:
        """Execute arbitrary Python code in the FreeCAD context.

        UNSAFE / DEV ONLY -- intended as a development fallback.
        """
        result = run_on_main_thread(lambda: self._execute_python(code, {}))
        success = len(result["errors"]) == 0
        message = "Script executed." if success else "Script raised an exception."
        return make_response(
            success,
            message,
            data={
                "output": result["stdout"],
                "stderr": result["stderr"],
                "result": result["result"],
            },
            errors=result["errors"],
        )

    def console_exec(self, code: str, persist: bool = True) -> Dict[str, Any]:
        """Execute Python in a persistent FreeCAD console-like namespace."""
        namespace = self._console_globals if persist else {}
        result = run_on_main_thread(lambda: self._execute_python(code, namespace))

        entry = {
            "code": code,
            "success": len(result["errors"]) == 0,
            "output": result["stdout"],
            "stderr": result["stderr"],
            "result": result["result"],
            "errors": result["errors"],
        }
        self._console_history.append(entry)
        if len(self._console_history) > self._console_history_limit:
            self._console_history = self._console_history[-self._console_history_limit:]

        success = entry["success"]
        message = "Console code executed." if success else "Console code raised an exception."
        return make_response(
            success,
            message,
            data={
                "output": entry["output"],
                "stderr": entry["stderr"],
                "result": entry["result"],
                "persist": bool(persist),
                "history_size": len(self._console_history),
            },
            errors=entry["errors"],
        )

    def console_read(self, limit: int = 20) -> Dict[str, Any]:
        """Read recent console execution history entries."""
        try:
            size = max(1, int(limit))
        except Exception:
            size = 20
        entries = self._console_history[-size:]
        return make_response(
            True,
            f"Returned {len(entries)} console entr{'y' if len(entries) == 1 else 'ies'}.",
            data={"entries": entries, "total": len(self._console_history)},
            errors=[],
        )

    def console_reset(self, reset_namespace: bool = True, clear_history: bool = True) -> Dict[str, Any]:
        """Reset persistent console namespace and/or clear console history."""
        if reset_namespace:
            self._console_globals = {"__name__": "__routerking_console__"}
        if clear_history:
            self._console_history = []
        return make_response(
            True,
            "Console state reset.",
            data={
                "reset_namespace": bool(reset_namespace),
                "clear_history": bool(clear_history),
            },
            errors=[],
        )

    def list_actions(self) -> Dict[str, Any]:
        actions = [definition.to_dict() for _, definition in sorted(self._action_registry.items())]
        return make_response(
            True,
            f"Loaded {len(actions)} RouterKing action definitions.",
            data={"actions": actions},
            errors=[],
        )

    def apply_actions(
        self,
        payload: Any,
        *,
        include_context: bool = True,
        capture_view: bool = False,
        screenshot_path: str | None = None,
    ) -> Dict[str, Any]:
        raw_actions, payload_errors = normalize_actions_payload(payload)
        if payload_errors:
            return make_response(False, "Action payload is invalid.", data={"results": []}, errors=payload_errors)

        validated_actions = []
        results = []
        validation_errors = []

        for index, raw_action in enumerate(raw_actions):
            action, action_errors = coerce_action(raw_action)
            if action_errors:
                message = "; ".join(action_errors)
                results.append(_result_item(index, None, False, message, action_errors))
                validation_errors.extend(action_errors)
                continue

            action_type = action["type"]
            definition = self._action_registry.get(action_type)
            if definition is None:
                message = f"Unsupported action: {action_type}"
                results.append(_result_item(index, action_type, False, message, [message]))
                validation_errors.append(message)
                continue

            missing_fields = _missing_required_fields(action, definition)
            if missing_fields:
                message = f"{action_type}: missing required fields: {', '.join(missing_fields)}"
                results.append(_result_item(index, action_type, False, message, [message]))
                validation_errors.append(message)
                continue

            safety_errors = validate_risk(action_type, definition.risk_class, action)
            if safety_errors:
                message = "; ".join(safety_errors)
                results.append(_result_item(index, action_type, False, message, safety_errors))
                validation_errors.extend(safety_errors)
                continue

            validated_actions.append((index, action, definition))

        transaction = self._transaction_factory()
        transaction_open = False
        if any(definition.risk_class == "modify" for _, _, definition in validated_actions):
            transaction_open = transaction.open("RouterKing MCP apply_actions")

        execution_failed = False
        for index, action, definition in validated_actions:
            log_tool_request(action["type"], definition.risk_class, action)
            messages, exec_errors, exec_data = _call_action_executor(self._action_executor, action)
            message = messages[0] if messages else ("; ".join(exec_errors) if exec_errors else "Action completed.")
            success = not exec_errors and not _message_looks_like_error(action["type"], message)
            errors = list(exec_errors)
            if not success and not errors:
                errors = [message]
            results.append(_result_item(index, action["type"], success, message, errors, data=exec_data))
            if not success:
                execution_failed = True
                break

        if transaction_open:
            if execution_failed:
                transaction.abort()
            else:
                transaction.commit()

        results.sort(key=lambda item: item["index"])
        response_data: Dict[str, Any] = {
            "results": results,
            "transaction": {
                "used": bool(transaction_open),
                "aborted": bool(transaction_open and execution_failed),
            },
        }

        if include_context:
            response_data["context"] = self._context.get_scene_info()
        if capture_view:
            response_data["screenshot"] = self._screenshots.capture_view(output_path=screenshot_path)

        success = not validation_errors and not execution_failed and bool(validated_actions or not raw_actions)
        if not raw_actions:
            success = False
        message = "RouterKing actions applied." if success else "RouterKing action execution failed."
        errors = validation_errors[:]
        if execution_failed:
            errors.extend(item for item in results[-1]["errors"] if item)

        return make_response(success, message, data=response_data, errors=errors)

    def _execute_python(self, code: str, namespace: Dict[str, Any]) -> Dict[str, Any]:
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        errors: List[str] = []
        result_repr = ""

        if "__builtins__" not in namespace:
            namespace["__builtins__"] = __builtins__

        try:
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                result = _exec_with_optional_last_expr(code, namespace)
                if result is not None:
                    result_repr = repr(result)
        except Exception:
            errors.append(traceback.format_exc())

        return {
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue(),
            "result": result_repr,
            "errors": errors,
        }


def _call_action_executor(
    executor: Callable[[List[Dict[str, Any]]], Any],
    action: Dict[str, Any],
) -> tuple[List[str], List[str], Any]:
    response = executor([action])
    if isinstance(response, tuple) and len(response) == 2:
        messages, errors = response
        return list(messages or []), list(errors or []), None
    if isinstance(response, dict):
        return (
            list(response.get("messages") or []),
            list(response.get("errors") or []),
            response.get("data"),
        )
    if isinstance(response, str):
        return [response], [], None
    return [], ["Action executor returned an unsupported response format."], None


def _missing_required_fields(action: Mapping[str, Any], definition: ActionDefinition) -> List[str]:
    missing = []
    for field in definition.required_params:
        value = get_action_param(action, field)
        if value is None:
            missing.append(field)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field)
    return missing


def _message_looks_like_error(action_type: str, message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return True
    if text.startswith(f"{action_type.lower()}:"):
        return True
    return any(fragment in text for fragment in (" failed:", " not found", " required.", " unavailable"))


def _result_item(
    index: int,
    action_type: str | None,
    success: bool,
    message: str,
    errors: Iterable[str],
    *,
    data: Any = None,
) -> Dict[str, Any]:
    item = {
        "index": index,
        "type": action_type,
        "success": bool(success),
        "message": message,
        "errors": [str(error) for error in errors if str(error)],
    }
    if data is not None:
        item["data"] = data
    return item


def _exec_with_optional_last_expr(code: str, namespace: Dict[str, Any]) -> Any:
    """Execute code and return final expression value when present."""
    tree = ast.parse(code, mode="exec")
    if not tree.body:
        return None

    last_stmt = tree.body[-1]
    if isinstance(last_stmt, ast.Expr):
        exec_body = ast.Module(body=tree.body[:-1], type_ignores=[])  # noqa: S102
        expr = ast.Expression(body=last_stmt.value)
        ast.fix_missing_locations(exec_body)
        ast.fix_missing_locations(expr)
        exec(compile(exec_body, "<routerking-console>", "exec"), namespace, namespace)  # noqa: S102
        return eval(compile(expr, "<routerking-console>", "eval"), namespace, namespace)  # noqa: S307

    exec(compile(tree, "<routerking-console>", "exec"), namespace, namespace)  # noqa: S102
    return None


def _collect_cam_capabilities() -> Dict[str, Any]:
    warnings: List[str] = []
    freecad_available = _module_available("FreeCAD")
    gui_available = _module_available("FreeCADGui")
    cam_modules = {
        "CAM": _module_available("CAM"),
        "Path": _module_available("Path"),
    }
    cam_available = any(cam_modules.values())

    if not freecad_available:
        warnings.append("FreeCAD is not available.")
    if not cam_available:
        warnings.append("FreeCAD CAM/Path module is not available.")

    try:
        from RouterKing.cam.hybrid import CamJobSettings, SimpleJobSettings
    except Exception:  # pragma: no cover - FreeCAD import path fallback
        try:
            from cam.hybrid import CamJobSettings, SimpleJobSettings
        except Exception:
            CamJobSettings = None  # type: ignore[assignment]
            SimpleJobSettings = None  # type: ignore[assignment]

    cam_defaults = asdict(CamJobSettings()) if CamJobSettings is not None else {}
    simple_defaults = asdict(SimpleJobSettings()) if SimpleJobSettings is not None else {}

    return {
        "freecad_available": freecad_available,
        "freecad_gui_available": gui_available,
        "cam_available": cam_available,
        "cam_modules": cam_modules,
        "operation_kinds": [
            {
                "type": "profile",
                "base": "model or selected vertical faces for box-like solids",
                "properties": ["Side", "Direction", "StartDepth", "FinalDepth", "StepDown", "HorizFeed", "VertFeed"],
            },
            {
                "type": "pocket",
                "base": "model or explicit base object",
                "properties": ["StartDepth", "FinalDepth", "StepDown", "HorizFeed", "VertFeed"],
            },
            {
                "type": "drilling",
                "base": "model or explicit base object",
                "properties": ["StartDepth", "FinalDepth", "PeckDepth", "Feed"],
            },
        ],
        "operation_schema": {
            "type": "profile|pocket|drilling",
            "base": "Optional FreeCAD object name.",
            "properties": "Optional FreeCAD CAM operation property overrides.",
        },
        "default_cam_settings": cam_defaults,
        "default_simple_settings": simple_defaults,
        "direct_generation_settings": [
            "post_processor",
            "feed_rate",
            "plunge_rate",
            "start_depth",
            "final_depth",
            "step_down",
            "step_over",
            "profile_side",
            "profile_direction",
            "safe_z",
            "cut_z",
            "start_z",
            "pass_depth",
            "ramp_length",
            "lead_in",
            "lead_out",
            "units",
            "spindle_speed",
            "laser_power",
            "start_spindle",
            "machine_profile_path",
        ],
        "postprocessors": ["grbl_post"],
        "fallback_engine": {
            "name": "simple",
            "available": bool(simple_defaults),
            "notes": "Used when FreeCAD CAM/Path is unavailable or CAM generation fails.",
        },
        "mcp_pipeline": [
            "routerking_cam_capabilities",
            "routerking_cam_list_setups",
            "routerking_cam_list_operations",
            "routerking_cam_inspect_operation",
            "routerking_cam_generate_job",
            "routerking_generate_gcode",
            "routerking_dxf_generate_gcode",
            "routerking_cam_analyze_gcode",
            "routerking_cam_postprocess",
            "routerking_machine_validate_gcode",
            "routerking_machine_stream_gcode",
        ],
        "warnings": warnings,
    }


def _module_available(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def _collect_cam_setups(document: str | None = None) -> Dict[str, Any]:
    warnings: List[str] = []
    doc = _resolve_document(document, warnings)
    if doc is None:
        return {"document": None, "setups": [], "warnings": warnings}

    setups = [_serialize_cam_setup(obj) for obj in _iter_document_objects(doc) if _looks_like_cam_setup(obj)]
    return {
        "document": _document_name(doc),
        "setups": setups,
        "warnings": warnings,
    }


def _collect_cam_operations(
    *,
    setup_id: str | None = None,
    include_paths: bool = False,
    include_properties: bool = True,
) -> Dict[str, Any]:
    warnings: List[str] = []
    doc = _resolve_document(None, warnings)
    if doc is None:
        return {
            "document": None,
            "setup_id": setup_id,
            "operations": [],
            "warnings": warnings,
        }

    setups = [obj for obj in _iter_document_objects(doc) if _looks_like_cam_setup(obj)]
    if setup_id:
        setups = [obj for obj in setups if _object_matches_id(obj, setup_id)]
        if not setups:
            warnings.append(f"CAM setup not found: {setup_id}")

    operations = []
    for setup in setups:
        for op in _collect_operations_for_setup(setup):
            operations.append(
                _serialize_cam_operation(
                    op,
                    setup=setup,
                    include_paths=include_paths,
                    include_properties=include_properties,
                )
            )

    return {
        "document": _document_name(doc),
        "setup_id": setup_id,
        "operations": operations,
        "warnings": warnings,
    }


def _inspect_cam_operation(
    *,
    operation_id: str,
    setup_id: str | None = None,
    include_gcode: bool = False,
    gcode_lines: int = 30,
    include_properties: bool = True,
    include_warnings: bool = True,
) -> Dict[str, Any]:
    warnings: List[str] = []
    if not str(operation_id or "").strip():
        message = "operation_id is required."
        return {"document": None, "setup_id": setup_id, "operation": None, "warnings": [message], "message": message}

    doc = _resolve_document(None, warnings)
    if doc is None:
        message = warnings[0] if warnings else "No active document."
        return {"document": None, "setup_id": setup_id, "operation": None, "warnings": warnings, "message": message}

    setups = [obj for obj in _iter_document_objects(doc) if _looks_like_cam_setup(obj)]
    if setup_id:
        setups = [obj for obj in setups if _object_matches_id(obj, setup_id)]
        if not setups:
            warnings.append(f"CAM setup not found: {setup_id}")

    matches = []
    for setup in setups:
        for op in _collect_operations_for_setup(setup):
            if _object_matches_id(op, operation_id):
                matches.append((setup, op))

    if len(matches) > 1 and not setup_id:
        message = f"CAM operation id is ambiguous: {operation_id}"
        warnings.append(message)
        return {
            "document": _document_name(doc),
            "setup_id": setup_id,
            "operation": None,
            "matches": [
                {
                    "setup_id": _object_id(setup),
                    "operation_id": _object_id(op),
                    "label": getattr(op, "Label", None) or getattr(op, "Name", None),
                }
                for setup, op in matches
            ],
            "warnings": warnings,
            "message": message,
        }

    if matches:
        setup, op = matches[0]
        operation_warnings: List[str] = []
        operation = _serialize_cam_operation(
            op,
            setup=setup,
            include_paths=include_gcode,
            include_properties=include_properties,
            warnings=operation_warnings,
        )
        gcode = _path_to_gcode(getattr(op, "Path", None), operation_warnings)
        line_limit = max(1, int(gcode_lines))
        operation["setup"] = _serialize_cam_setup(setup)
        operation["base_detail"] = _base_detail(op)
        operation["property_status"] = _operation_property_status(operation)
        operation["path"] = _path_summary(gcode, path_obj=getattr(op, "Path", None), line_limit=line_limit)
        operation["diagnostics"] = _diagnose_cam_operation(operation, operation_warnings)
        if include_gcode:
            operation["gcode_excerpt"] = operation["path"]["preview"]
        if include_warnings:
            warnings.extend(operation_warnings)
            warnings.extend(operation["diagnostics"]["warnings"])
        return {
            "document": _document_name(doc),
            "setup_id": _object_id(setup),
            "operation": operation,
            "warnings": _dedupe_warnings(warnings),
        }

    message = f"CAM operation not found: {operation_id}"
    warnings.append(message)
    return {
        "document": _document_name(doc),
        "setup_id": setup_id,
        "operation": None,
        "warnings": warnings,
        "message": message,
    }


def _resolve_document(document: str | None, warnings: List[str]) -> Any | None:
    app = _get_freecad_app()
    if app is None:
        warnings.append("FreeCAD is not available.")
        return None

    if document:
        list_docs = getattr(app, "listDocuments", None)
        documents = list_docs() if callable(list_docs) else {}
        if isinstance(documents, Mapping):
            doc = documents.get(document)
            if doc is not None:
                return doc
        warnings.append(f"Document not found: {document}")
        return None

    doc = getattr(app, "ActiveDocument", None)
    if doc is None:
        warnings.append("No active document.")
    return doc


def _get_freecad_app() -> Any | None:
    try:
        return importlib.import_module("FreeCAD")
    except Exception:
        return None


def _iter_document_objects(doc: Any) -> List[Any]:
    return list(getattr(doc, "Objects", []) or [])


def _document_name(doc: Any) -> str | None:
    return getattr(doc, "Name", None) or getattr(doc, "Label", None)


def _looks_like_cam_setup(obj: Any) -> bool:
    if obj is None:
        return False
    type_id = str(getattr(obj, "TypeId", "") or "")
    name = str(getattr(obj, "Name", "") or "").lower()
    if "Path::Job" in type_id or "PathJob" in type_id:
        return True
    if hasattr(obj, "Operations") and ("job" in type_id.lower() or "job" in name):
        return True
    return hasattr(obj, "Operations") and hasattr(obj, "Path")


def _serialize_cam_setup(job: Any) -> Dict[str, Any]:
    operations = _collect_operations_for_setup(job)
    path_obj = getattr(job, "Path", None)
    gcode = _path_to_gcode(path_obj)
    return {
        "id": _object_id(job),
        "name": getattr(job, "Name", None),
        "label": getattr(job, "Label", None) or getattr(job, "Name", None),
        "type": getattr(job, "TypeId", job.__class__.__name__),
        "operation_count": len(operations),
        "operations": [_object_id(op) for op in operations],
        "path_available": bool(path_obj is not None),
        "gcode_line_count": _line_count(gcode),
        "post_processor": _first_attr(job, ("PostProcessor", "PostProcessorName", "Postprocessor", "OutputPost")),
        "output_path": _first_attr(job, ("OutputFile", "OutputPath", "PathOutput", "FileName")),
        "model": _serialize_ref(_first_attr(job, ("Model", "Base", "BaseObject"))),
    }


def _collect_operations_for_setup(job: Any) -> List[Any]:
    roots = []
    operations = getattr(job, "Operations", None)
    if operations is not None:
        roots.append(operations)
    roots.extend(list(getattr(job, "OutList", []) or []))

    seen = set()
    queue = list(roots)
    ordered = []
    while queue:
        obj = queue.pop(0)
        oid = id(obj)
        if oid in seen:
            continue
        seen.add(oid)
        ordered.append(obj)
        for children_attr in ("Group", "OutList"):
            for child in list(getattr(obj, children_attr, []) or []):
                if id(child) not in seen:
                    queue.append(child)

    return [obj for obj in ordered if _looks_like_cam_operation(job, obj)]


def _looks_like_cam_operation(job: Any, obj: Any) -> bool:
    if obj is None or obj is job:
        return False
    type_id = str(getattr(obj, "TypeId", "") or "")
    name = str(getattr(obj, "Name", "") or "").lower()
    if "Path::Tool" in type_id or "tool" in name and not hasattr(obj, "Path"):
        return False
    if "Path::Feature" in type_id and hasattr(obj, "Path"):
        return True
    if hasattr(obj, "Path") and name.startswith(("profile", "pocket", "drilling", "adaptive", "contour")):
        return True
    return any(_has_non_empty_attr(obj, attr) for attr in ("Base", "BaseGeometry", "BaseObject")) and hasattr(obj, "Path")


def _serialize_cam_operation(
    op: Any,
    *,
    setup: Any,
    include_paths: bool,
    include_properties: bool,
    warnings: List[str] | None = None,
) -> Dict[str, Any]:
    path_obj = getattr(op, "Path", None)
    gcode = _path_to_gcode(path_obj, warnings)
    payload: Dict[str, Any] = {
        "id": _object_id(op),
        "name": getattr(op, "Name", None),
        "label": getattr(op, "Label", None) or getattr(op, "Name", None),
        "type": getattr(op, "TypeId", op.__class__.__name__),
        "operation_type": _infer_operation_type(op),
        "setup_id": _object_id(setup),
        "enabled": _coerce_bool(_first_attr(op, ("Active", "Enabled", "Visibility")), default=True),
        "base": _serialize_ref(_first_attr(op, ("Base", "BaseGeometry", "BaseObject"))),
        "path_available": bool(path_obj is not None),
        "gcode_line_count": _line_count(gcode),
    }
    if include_properties:
        payload["properties"] = _serialize_operation_properties(op)
    if include_paths:
        payload["gcode_preview"] = "\n".join(gcode.splitlines()[:30])
    return payload


def _diagnose_cam_operation(operation: Mapping[str, Any], warnings: List[str]) -> Dict[str, Any]:
    diagnostics: Dict[str, Any] = {
        "ready_for_postprocess": True,
        "warnings": list(warnings),
    }
    if operation.get("enabled") is False:
        diagnostics["ready_for_postprocess"] = False
        diagnostics["warnings"].append("Operation is disabled.")
    if not operation.get("path_available"):
        diagnostics["ready_for_postprocess"] = False
        diagnostics["warnings"].append("Operation has no Path object.")
    if int(operation.get("gcode_line_count") or 0) <= 0:
        diagnostics["ready_for_postprocess"] = False
        diagnostics["warnings"].append("Operation path has no G-code lines.")
    if operation.get("operation_type") == "unknown":
        diagnostics["warnings"].append("Operation type could not be inferred.")
    if operation.get("base") is None:
        diagnostics["warnings"].append("Operation has no base geometry reference.")
    diagnostics["warnings"] = _dedupe_warnings(diagnostics["warnings"])
    return diagnostics


def _base_detail(op: Any) -> Dict[str, Any]:
    raw = {
        "Base": _jsonable(getattr(op, "Base", None)) if hasattr(op, "Base") else None,
        "BaseGeometry": _jsonable(getattr(op, "BaseGeometry", None)) if hasattr(op, "BaseGeometry") else None,
        "BaseObject": _jsonable(getattr(op, "BaseObject", None)) if hasattr(op, "BaseObject") else None,
    }
    objects: List[str] = []
    subelements: List[str] = []
    for value in raw.values():
        _collect_base_parts(value, objects, subelements)
    return {
        "raw": raw,
        "objects": _dedupe_warnings(objects),
        "subelements": _dedupe_warnings(subelements),
        "missing": not any(value not in (None, "", [], {}, ()) for value in raw.values()),
    }


def _collect_base_parts(value: Any, objects: List[str], subelements: List[str]) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if value:
            if "." in value:
                obj, _, sub = value.partition(".")
                objects.append(obj)
                subelements.append(sub)
            else:
                objects.append(value)
        return
    if isinstance(value, Mapping):
        name = value.get("name") or value.get("label")
        if name:
            objects.append(str(name))
        return
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], Mapping):
            name = value[0].get("name") or value[0].get("label")
            if name:
                objects.append(str(name))
            for item in value[1:]:
                _collect_base_parts(item, objects, subelements)
            return
        for item in value:
            _collect_base_parts(item, objects, subelements)


def _operation_property_status(operation: Mapping[str, Any]) -> Dict[str, Any]:
    properties = dict(operation.get("properties") or {})
    expected_by_kind = {
        "profile": ["Side", "Direction", "StartDepth", "FinalDepth", "StepDown", "HorizFeed", "VertFeed"],
        "pocket": ["StartDepth", "FinalDepth", "StepDown", "HorizFeed", "VertFeed"],
        "drilling": ["StartDepth", "FinalDepth", "PeckDepth", "Feed"],
    }
    expected = expected_by_kind.get(str(operation.get("operation_type") or ""), [])
    return {
        "expected": expected,
        "serialized": list(properties.keys()),
        "missing_expected": [name for name in expected if name not in properties],
    }


def _path_summary(gcode: str, *, path_obj: Any, line_limit: int) -> Dict[str, Any]:
    lines = [line for line in str(gcode or "").splitlines() if line.strip()]
    preview_lines = lines[: max(1, int(line_limit))]
    motion_lines = [line for line in lines if str(line).strip().upper().startswith(("G0", "G1", "G2", "G3"))]
    return {
        "available": bool(path_obj is not None),
        "source": "Path.toGCode" if path_obj is not None else "",
        "gcode_line_count": len(lines),
        "preview": "\n".join(preview_lines),
        "preview_line_count": len(preview_lines),
        "preview_truncated": len(lines) > len(preview_lines),
        "line_limit": max(1, int(line_limit)),
        "first_motion_line": motion_lines[0] if motion_lines else "",
        "last_motion_line": motion_lines[-1] if motion_lines else "",
    }


def _serialize_operation_properties(op: Any) -> Dict[str, Any]:
    names = (
        "Side",
        "Direction",
        "StartDepth",
        "FinalDepth",
        "StepDown",
        "PeckDepth",
        "HorizFeed",
        "VertFeed",
        "Feed",
        "FeedRate",
        "ToolController",
        "Comment",
    )
    data = {}
    for name in names:
        if hasattr(op, name):
            data[name] = _jsonable(getattr(op, name))
    return data


def _infer_operation_type(op: Any) -> str:
    text = " ".join(
        str(value or "")
        for value in (
            getattr(op, "Name", ""),
            getattr(op, "Label", ""),
            getattr(op, "TypeId", ""),
            op.__class__.__name__,
            getattr(getattr(op, "Proxy", None), "__class__", type("", (), {})).__name__,
        )
    ).lower()
    for kind in ("profile", "pocket", "drilling", "adaptive", "contour"):
        if kind in text:
            return kind
    return "unknown"


def _path_to_gcode(path_obj: Any, warnings: List[str] | None = None) -> str:
    to_gcode = getattr(path_obj, "toGCode", None) if path_obj is not None else None
    if not callable(to_gcode):
        if path_obj is None and warnings is not None:
            warnings.append("Path object is missing.")
        elif warnings is not None:
            warnings.append("Path.toGCode is unavailable.")
        return ""
    try:
        result = to_gcode()
    except Exception as exc:
        if warnings is not None:
            warnings.append(f"Path.toGCode failed: {exc}")
        return ""
    if isinstance(result, bytes):
        return result.decode("utf-8", errors="replace")
    if isinstance(result, str):
        return result
    if isinstance(result, (list, tuple)):
        return "\n".join(str(line) for line in result)
    if result is None:
        return ""
    return str(result)


def _object_id(obj: Any) -> str:
    return str(getattr(obj, "Name", None) or getattr(obj, "Label", None) or id(obj))


def _object_matches_id(obj: Any, value: str) -> bool:
    needle = str(value)
    return needle in {
        str(getattr(obj, "Name", "")),
        str(getattr(obj, "Label", "")),
        _object_id(obj),
    }


def _first_attr(obj: Any, names: Iterable[str]) -> Any:
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value not in (None, "", (), [], {}):
                return value
    return None


def _has_non_empty_attr(obj: Any, name: str) -> bool:
    return _first_attr(obj, (name,)) is not None


def _serialize_ref(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_ref(item) for item in value]
    return {
        "name": getattr(value, "Name", None),
        "label": getattr(value, "Label", None) or getattr(value, "Name", None),
        "type": getattr(value, "TypeId", value.__class__.__name__),
    }


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(val) for key, val in value.items()}
    for attr in ("Value", "Name", "Label"):
        if hasattr(value, attr):
            return _jsonable(getattr(value, attr))
    return str(value)


def _line_count(text: str) -> int:
    return len([line for line in str(text or "").splitlines() if line.strip()])


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return bool(value)


def _dedupe_warnings(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
