"""RouterKing-side bridge used by the MCP tool layer."""

from __future__ import annotations

import ast
import contextlib
import io
import traceback
from typing import Any, Callable, Dict, Iterable, List, Mapping

from mcp.server.safety import log_tool_request, validate_risk
from mcp.server.schemas import ActionDefinition, coerce_action, get_action_param, make_response, normalize_actions_payload

try:
    from RouterKing.ai.actions import execute_actions
except Exception:  # pragma: no cover - fallback for FreeCAD import path
    from ai.actions import execute_actions

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
        ),
        risk_class="modify",
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
        optional_params=("confirm", "reason"),
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
        self._action_executor = action_executor or execute_actions
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
