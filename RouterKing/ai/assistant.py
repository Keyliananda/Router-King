"""Rule-based assistant helpers for RouterKing AI chat."""

from dataclasses import dataclass, field

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None

try:
    from .client import send_chat_request
    from .context import get_selection_context
    from .logging import get_logger
except ImportError:  # pragma: no cover - fallback for FreeCAD import path
    from ai.client import send_chat_request
    from ai.context import get_selection_context
    from ai.logging import get_logger


_LOG = get_logger("routerking.ai.assistant")


@dataclass
class AssistantContext:
    selection: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    document: dict = field(default_factory=dict)


@dataclass
class AssistantResponse:
    text: str
    source: str = "rules"
    used_llm: bool = False


def collect_assistant_context(selection_context=None):
    if selection_context is None:
        selection_context = get_selection_context()

    context = AssistantContext()
    context.warnings = list(selection_context.warnings or [])
    for item in selection_context.items:
        context.selection.append(_summarize_selection_item(item))

    if App is not None:
        doc = getattr(App, "ActiveDocument", None)
        if doc is not None:
            context.document = {
                "name": getattr(doc, "Name", ""),
                "label": getattr(doc, "Label", ""),
                "objects": len(getattr(doc, "Objects", []) or []),
                "active_object": _safe_label(getattr(doc, "ActiveObject", None)),
            }
    return context


def summarize_context(context):
    if context is None:
        return ""
    lines = []
    if context.document:
        label = context.document.get("label") or context.document.get("name") or "Active document"
        count = context.document.get("objects")
        active = context.document.get("active_object")
        doc_line = f"{label}"
        if count is not None:
            doc_line += f" (objects={count})"
        if active:
            doc_line += f", active={active}"
        lines.append(f"Document: {doc_line}")
    if context.selection:
        lines.append("Selection:")
        for item in context.selection:
            parts = [item.get("label") or "<unnamed>", item.get("type_id") or "unknown"]
            details = []
            edges = item.get("edges")
            faces = item.get("faces")
            if edges is not None:
                details.append(f"edges={edges}")
            if faces is not None:
                details.append(f"faces={faces}")
            if item.get("sketch_geometry") is not None:
                details.append(f"sketch_geom={item.get('sketch_geometry')}")
            if item.get("sketch_constraints") is not None:
                details.append(f"sketch_constraints={item.get('sketch_constraints')}")
            if item.get("sketch_fully_constrained") is not None:
                details.append(f"sketch_fully_constrained={item.get('sketch_fully_constrained')}")
            detail_text = f" ({', '.join(details)})" if details else ""
            lines.append(f"- {parts[0]} [{parts[1]}]{detail_text}")
    if context.warnings:
        lines.append("Warnings: " + "; ".join(context.warnings))
    return "\n".join(lines)


def ask_assistant(
    messages,
    api_key=None,
    base_url=None,
    model=None,
    reasoning_effort="off",
    temperature=0.2,
    max_output_tokens=512,
    context=None,
    context_summary="",
    allow_llm=True,
):
    prompt = _last_user_message(messages)
    if prompt:
        rule_response = rule_based_response(prompt, context=context)
        if rule_response:
            return AssistantResponse(text=rule_response, source="rules", used_llm=False)

    if not allow_llm or not api_key:
        fallback = _fallback_response(context)
        return AssistantResponse(text=fallback, source="rules", used_llm=False)

    if not context_summary and context is not None:
        context_summary = summarize_context(context)

    try:
        response = send_chat_request(
            api_key,
            base_url or "https://api.openai.com/v1",
            model or "gpt-4o-mini",
            _inject_context(messages, context_summary),
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    except Exception as exc:
        _LOG.warning("LLM request failed, falling back to rules: %s", exc)
        fallback = _fallback_response(context)
        return AssistantResponse(text=fallback, source="rules", used_llm=False)

    return AssistantResponse(text=response, source="llm", used_llm=True)


def rule_based_response(prompt, context=None):
    if not prompt:
        return ""
    text = prompt.lower()
    if _contains_any(text, _PAD_TERMS) and _contains_any(text, _FAIL_TERMS):
        return _pad_failure_response(context)
    if _contains_any(text, _SKETCH_TERMS) and _contains_any(text, _UNSTABLE_TERMS):
        return _sketch_unstable_response(context)
    if _contains_any(text, _SPLINE_TERMS):
        return _spline_response()
    if _contains_any(text, _CAM_TERMS):
        return _cam_response()
    return ""


def _summarize_selection_item(item):
    obj = item.obj
    info = {
        "label": item.label,
        "type_id": item.type_id,
    }
    shape = getattr(obj, "Shape", None)
    if shape is not None and hasattr(shape, "Edges"):
        try:
            info["edges"] = len(shape.Edges)
        except Exception:
            pass
        try:
            info["faces"] = len(getattr(shape, "Faces", []) or [])
        except Exception:
            pass

    type_id = (item.type_id or "").lower()
    class_name = obj.__class__.__name__.lower()
    if "sketch" in type_id or "sketch" in class_name:
        info["sketch_geometry"] = _safe_len(getattr(obj, "Geometry", None))
        info["sketch_constraints"] = _safe_len(getattr(obj, "Constraints", None))
        fully = getattr(obj, "FullyConstrained", None)
        if fully is not None:
            info["sketch_fully_constrained"] = bool(fully)
        solver = getattr(obj, "SolverStatus", None)
        if solver is not None:
            info["sketch_solver"] = str(solver)
    return info


def _safe_len(value):
    if value is None:
        return None
    try:
        return len(value)
    except Exception:
        return None


def _safe_label(obj):
    if obj is None:
        return ""
    return getattr(obj, "Label", None) or getattr(obj, "Name", "") or ""


def _last_user_message(messages):
    for message in reversed(messages or []):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def _inject_context(messages, context_summary):
    if not context_summary:
        return list(messages or [])
    context_message = {
        "role": "system",
        "content": f"Context from the current FreeCAD session:\n{context_summary}",
    }
    if not messages:
        return [context_message]
    new_messages = list(messages)
    if new_messages[0].get("role") == "system":
        new_messages.insert(1, context_message)
    else:
        new_messages.insert(0, context_message)
    return new_messages


def _fallback_response(context=None):
    lines = [
        "Ich kann dazu eine erste Einschaetzung geben, brauche aber mehr Kontext.",
        "Bitte pruefe:",
        "- Sketch/Geometrie selektiert?",
        "- Sketch geschlossen und ohne Selbstschnitt?",
        "- Body aktiv und keine Mehrfachprofile?",
    ]
    if context and context.warnings:
        lines.append(f"Hinweis: {', '.join(context.warnings)}")
    return "\n".join(lines)


def _pad_failure_response(context=None):
    lines = [
        "Moegliche Ursachen fuer einen Pad-Fehler:",
        "- Sketch ist nicht geschlossen (Luecken oder offene Enden).",
        "- Selbstschnitt oder doppelte Kanten im Sketch.",
        "- Mehrere Profile aktiv, die sich schneiden.",
        "- Body nicht aktiv oder falscher Bezug (Datum/Face).",
    ]
    if _context_has_unconstrained_sketch(context):
        lines.append("- Sketch ist nicht vollstaendig gefangen; zusaetzliche Bemaesung hilft.")
    if _context_has_no_sketch(context):
        lines.append("- Keine Skizze selektiert: bitte Sketch auswaehlen und erneut versuchen.")
    return "\n".join(lines)


def _sketch_unstable_response(context=None):
    lines = [
        "Tipps fuer instabile Skizzen:",
        "- Vollstaendig bemaessen (Fully Constrained) oder gezielt Fix-Constraints setzen.",
        "- Redundante/konfliktierende Constraints entfernen.",
        "- Keine doppelten Geometrien oder uebereinanderliegende Linien.",
        "- Externe Referenzen sparsam nutzen (kann instabil machen).",
    ]
    if _context_has_unconstrained_sketch(context):
        lines.append("- Status: Sketch scheint nicht vollstaendig gefangen zu sein.")
    return "\n".join(lines)


def _spline_response():
    return (
        "Spline-Qualitaet verbessern: pruefe die Spline-Analyse und die "
        "\"Preview Spline Optimization\"-Funktion. "
        "Zu viele Kontrollpunkte oder Knicke lassen sich so glatten."
    )


def _cam_response():
    return (
        "CAM-Hinweis: Lade G-Code in den G-Code-Tab und nutze den CAM-Risk-Check, "
        "um kleine Radien oder riskante Rapid-Moves zu erkennen."
    )


def _context_has_no_sketch(context):
    if context is None:
        return False
    if context.warnings:
        return True
    for item in context.selection:
        type_id = (item.get("type_id") or "").lower()
        if "sketch" in type_id:
            return False
    return True


def _context_has_unconstrained_sketch(context):
    if context is None:
        return False
    for item in context.selection:
        if item.get("sketch_fully_constrained") is False:
            return True
    return False


def _contains_any(text, terms):
    return any(term in text for term in terms)


_PAD_TERMS = ("pad", "extrude", "extrusion", "aufpolster", "aufpolstern")
_FAIL_TERMS = ("fail", "failed", "fehl", "schlaegt", "error", "fehler")
_SKETCH_TERMS = ("sketch", "skizze")
_UNSTABLE_TERMS = ("instabil", "unstable", "underconstrained", "unterb", "loesst sich", "springt")
_SPLINE_TERMS = ("spline", "bezier", "kurve", "control point", "kontrollpunkt")
_CAM_TERMS = ("gcode", "toolpath", "cam", "fraese", "fraesen", "toolpath", "tool path")
