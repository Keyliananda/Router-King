"""Rule-based assistant helpers for RouterKing AI chat."""

from dataclasses import dataclass, field
import json
import re

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None

try:
    from .client import send_chat_request
    from .context import get_selection_context
    from .logging import get_logger
    from .actions import execute_actions, get_action_prompt
except ImportError:  # pragma: no cover - fallback for FreeCAD import path
    from ai.client import send_chat_request
    from ai.context import get_selection_context
    from ai.logging import get_logger
    from ai.actions import execute_actions, get_action_prompt


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
    allow_actions=False,
):
    prompt = _last_user_message(messages)
    if prompt:
        if _is_help_request(prompt):
            return AssistantResponse(
                text=_tools_response(allow_actions=allow_actions),
                source="rules",
                used_llm=False,
            )
        if not allow_actions:
            action_response = _try_create_primitive(prompt)
            if action_response:
                return AssistantResponse(text=action_response, source="action", used_llm=False)
        rule_response = rule_based_response(prompt, context=context)
        if rule_response:
            return AssistantResponse(text=rule_response, source="rules", used_llm=False)

    if not allow_llm or not api_key:
        fallback = _fallback_response(context)
        return AssistantResponse(text=fallback, source="rules", used_llm=False)

    if not context_summary and context is not None:
        context_summary = summarize_context(context)

    try:
        outgoing = _inject_context(messages, context_summary)
        if allow_actions:
            outgoing = _inject_action_instructions(outgoing)
        response = send_chat_request(
            api_key,
            base_url or "https://api.openai.com/v1",
            model or "gpt-4o-mini",
            outgoing,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    except Exception as exc:
        _LOG.warning("LLM request failed, falling back to rules: %s", exc)
        fallback = _fallback_response(context)
        return AssistantResponse(text=fallback, source="rules", used_llm=False)

    action_messages = []
    if allow_actions:
        response, action_messages = _apply_llm_actions(response)
    if action_messages:
        response = response.rstrip()
        response += "\n\nAction results:\n" + "\n".join(f"- {msg}" for msg in action_messages)
    return AssistantResponse(text=response, source="llm", used_llm=True)


def rule_based_response(prompt, context=None):
    if not prompt:
        return ""
    text = prompt.lower()
    normalized = _normalize_text(prompt)
    if _contains_any(text, _PAD_TERMS) and _contains_any(text, _FAIL_TERMS):
        return _pad_failure_response(context)
    if _contains_any(text, _ANALYZE_TERMS) and _contains_any(text, ("geometrie", "selektion", "auswahl", "objekt")):
        return _analyze_selection_response()
    if _contains_any(text, _SKETCH_TERMS) and _contains_any(text, _UNSTABLE_TERMS):
        return _sketch_unstable_response(context)
    if _is_test_mill_request(normalized):
        return _create_default_test_part()
    if _contains_any(text, _CAM_TERMS):
        if _contains_any(text, _ANALYZE_TERMS):
            return _analyze_gcode_response()
        if _contains_any(text, _CREATE_TERMS):
            return _generate_cam_job_response()
    if _contains_any(text, _WARNING_TERMS) and _contains_any(text, _CAM_TERMS):
        return _explain_cam_warning_response()
    if _contains_any(text, _START_TERMS) and _contains_any(text, ("job", "fräs", "programm")):
        return _start_job_response()
    if _contains_any(text, ("verbind", "connect")) and _contains_any(text, ("maschine", "fraese", "grbl")):
        return _machine_connect_response(prompt)
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


def _try_create_primitive(prompt):
    if not prompt:
        return ""
    normalized = _normalize_text(prompt)
    if _is_test_mill_request(normalized):
        return _create_default_test_part()
    if _contains_any(normalized, _BOX_TERMS):
        return _create_box_from_prompt(prompt)
    if _contains_any(normalized, _CYL_TERMS):
        return _create_cylinder_from_prompt(prompt)
    if _contains_any(normalized, _SPHERE_TERMS):
        return _create_sphere_from_prompt(prompt)
    return ""


def _create_box_from_prompt(prompt):
    dims = _parse_numbers(prompt)
    if len(dims) == 1:
        length = width = height = dims[0]
        note = " (Wuerfel, gleichseitig)"
    elif len(dims) >= 3:
        length, width, height = dims[0], dims[1], dims[2]
        note = ""
    else:
        return "Bitte nenne die Masse, z.B. 'Box 20x30x10' oder 'Wuerfel 20'."

    return _create_part_box(length, width, height, note=note)


def _create_cylinder_from_prompt(prompt):
    radius = _find_labeled_value(prompt, ("r", "radius"))
    diameter = _find_labeled_value(prompt, ("d", "diameter", "durchmesser"))
    height = _find_labeled_value(prompt, ("h", "height", "hoehe"))
    dims = _parse_numbers(prompt)
    assumed = ""

    if radius is None and diameter is not None:
        radius = diameter / 2.0
    if height is None and len(dims) >= 2:
        height = dims[1]
        if radius is None and diameter is None:
            diameter = dims[0]
            radius = diameter / 2.0
            assumed = " (angenommen: erster Wert = Durchmesser, zweiter = Hoehe)"
    if radius is None and height is not None and len(dims) >= 1:
        radius = dims[0]
        assumed = " (angenommen: erster Wert = Radius)"

    if radius is None or height is None:
        return (
            "Bitte nenne Radius/Durchmesser und Hoehe, z.B. "
            "'Zylinder d10 h20' oder 'Cylinder r5 h20'."
        )

    return _create_part_cylinder(radius, height, note=assumed)


def _create_sphere_from_prompt(prompt):
    radius = _find_labeled_value(prompt, ("r", "radius"))
    diameter = _find_labeled_value(prompt, ("d", "diameter", "durchmesser"))
    dims = _parse_numbers(prompt)
    assumed = ""

    if radius is None and diameter is not None:
        radius = diameter / 2.0
    if radius is None and dims:
        radius = dims[0]
        assumed = " (angenommen: Wert = Radius)"

    if radius is None:
        return "Bitte nenne Radius oder Durchmesser, z.B. 'Kugel r10' oder 'Sphere d20'."

    return _create_part_sphere(radius, note=assumed)


def _create_part_box(length, width, height, note=""):
    if App is None:
        return "FreeCAD ist nicht verfuegbar; Primitive koennen nicht erstellt werden."
    doc = App.ActiveDocument
    if doc is None:
        return "Kein aktives Dokument. Bitte zuerst ein Dokument erstellen/oeffnen und erneut versuchen."
    try:
        name = _unique_object_name(doc, "AI_Box")
        obj = doc.addObject("Part::Box", name)
        obj.Length = float(length)
        obj.Width = float(width)
        obj.Height = float(height)
        doc.recompute()
    except Exception as exc:
        return f"Box konnte nicht erstellt werden: {exc}"
    return (
        f"Box erstellt: {_fmt_mm(length)} x {_fmt_mm(width)} x {_fmt_mm(height)} mm{note}."
    )


def _create_part_cylinder(radius, height, note=""):
    if App is None:
        return "FreeCAD ist nicht verfuegbar; Primitive koennen nicht erstellt werden."
    doc = App.ActiveDocument
    if doc is None:
        return "Kein aktives Dokument. Bitte zuerst ein Dokument erstellen/oeffnen und erneut versuchen."
    try:
        name = _unique_object_name(doc, "AI_Cylinder")
        obj = doc.addObject("Part::Cylinder", name)
        obj.Radius = float(radius)
        obj.Height = float(height)
        doc.recompute()
    except Exception as exc:
        return f"Zylinder konnte nicht erstellt werden: {exc}"
    return f"Zylinder erstellt: r={_fmt_mm(radius)} mm, h={_fmt_mm(height)} mm{note}."


def _create_part_sphere(radius, note=""):
    if App is None:
        return "FreeCAD ist nicht verfuegbar; Primitive koennen nicht erstellt werden."
    doc = App.ActiveDocument
    if doc is None:
        return "Kein aktives Dokument. Bitte zuerst ein Dokument erstellen/oeffnen und erneut versuchen."
    try:
        name = _unique_object_name(doc, "AI_Sphere")
        obj = doc.addObject("Part::Sphere", name)
        obj.Radius = float(radius)
        doc.recompute()
    except Exception as exc:
        return f"Kugel konnte nicht erstellt werden: {exc}"
    return f"Kugel erstellt: r={_fmt_mm(radius)} mm{note}."


def _create_default_test_part():
    response = _create_part_box(30, 20, 5, note=" (Standard-Testteil)")
    if response.startswith("Box erstellt"):
        response += " Hinweis: Fuer eine Testdatei (G-code) bitte das Teil selektieren und 'Generate G-code' nutzen."
    return response


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


def _parse_numbers(text):
    values = []
    for raw in re.findall(r"-?\d+(?:[.,]\d+)?", text or ""):
        try:
            values.append(float(raw.replace(",", ".")))
        except ValueError:
            continue
    return values


def _find_labeled_value(text, labels):
    if not text:
        return None
    normalized = _normalize_text(text)
    for label in labels:
        pattern = rf"(?:^|[^a-z0-9_]){re.escape(label)}\s*=?\s*(-?\d+(?:[.,]\d+)?)"
        match = re.search(pattern, normalized)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                return None
    return None


def _normalize_text(text):
    lowered = (text or "").lower()
    lowered = lowered.replace("\u00e4", "ae")
    lowered = lowered.replace("\u00f6", "oe")
    lowered = lowered.replace("\u00fc", "ue")
    lowered = lowered.replace("\u00df", "ss")
    return lowered


def _is_help_request(prompt):
    if not prompt:
        return False
    normalized = _normalize_text(prompt)
    return _contains_any(normalized, _HELP_TERMS)


def _is_test_mill_request(normalized_text):
    if not normalized_text:
        return False
    if "test" not in normalized_text:
        return False
    if not _contains_any(normalized_text, _TEST_MILL_TERMS):
        return False
    return _contains_any(normalized_text, _TEST_OBJECT_TERMS) or "testfraes" in normalized_text


def _tools_response(allow_actions=False):
    lines = [
        "Ich kann einfache Primitive erzeugen (Box, Zylinder, Kugel) und Hinweise zu Sketch/Pad, Splines und CAM geben.",
        "Beispiele: 'Box 30x20x5', 'Zylinder d10 h20', 'Kugel r8'.",
        f"AI-Aktionen sind aktuell {'aktiviert' if allow_actions else 'deaktiviert'}.",
        "Aktivieren in den AI Settings: 'Allow AI actions' (Enable model-driven edits).",
        "",
        "Tool-Doku (LLM Actions):",
        get_action_prompt(),
    ]
    return "\n".join(lines)


def _fmt_mm(value):
    try:
        return f"{float(value):g}"
    except Exception:
        return str(value)


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


def _inject_action_instructions(messages):
    prompt = get_action_prompt()
    if not prompt:
        return list(messages or [])
    action_message = {"role": "system", "content": prompt}
    if not messages:
        return [action_message]
    new_messages = list(messages)
    if new_messages[0].get("role") == "system":
        new_messages.insert(1, action_message)
    else:
        new_messages.insert(0, action_message)
    return new_messages


def _apply_llm_actions(response_text):
    actions = _extract_actions(response_text)
    if not actions:
        return response_text, []
    cleaned = _strip_action_blocks(response_text)
    results, errors = execute_actions(actions)
    messages = results + [f"Error: {err}" for err in errors]
    return cleaned, messages


def _extract_actions(response_text):
    if not response_text:
        return []
    blocks = re.findall(r"```routerking_actions\s*(\{.*?\})\s*```", response_text, flags=re.DOTALL)
    actions = []
    for block in blocks:
        try:
            payload = json.loads(block)
        except ValueError:
            continue
        if isinstance(payload, dict):
            payload_actions = payload.get("actions")
            if isinstance(payload_actions, list):
                actions.extend(payload_actions)
        elif isinstance(payload, list):
            actions.extend(payload)
    return actions


def _strip_action_blocks(response_text):
    return re.sub(r"```routerking_actions\s*\{.*?\}\s*```", "", response_text, flags=re.DOTALL).strip()


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


def _generate_cam_job_response():
    """Erstellt einen CAM-Job inklusive einer Standard-Profil-Operation."""
    action = {
        "type": "cam_generate_job", 
        "params": {
            "use_cam_defaults": True,
            "operations": [
                {"kind": "Profile", "properties": {"Side": "Outside", "Direction": "CCW"}}
            ]
        }
    }
    
    results, errors = execute_actions([action])
    if errors:
        return f"Fehler beim Erstellen des CAM-Jobs: {errors[0]}"
    return results[0] if results else "CAM-Job wurde erfolgreich erstellt."


def _analyze_selection_response():
    results, errors = execute_actions([{"type": "analyze_selection", "params": {}}])
    if errors:
        return f"Fehler bei der Analyse: {errors[0]}"
    response = results[0] if results else "Analyse abgeschlossen."
    response += "\n\nTipp: Du kannst mich auch fragen 'Optimiere die Splines', um die Geometrie zu verbessern."
    return response


def _get_editor_gcode():
    """Hilfsfunktion: Extrahiert den aktuellen G-Code aus dem UI-Editor."""
    try:
        from ..ui import main_dock
    except Exception:
        try:
            from ui import main_dock
        except Exception:
            return "UI-Komponenten nicht verfuegbar. Bitte lade den G-Code manuell."

    dock = getattr(main_dock, "_dock", None)
    if not dock:
        return "RouterKing Panel ist nicht geoeffnet."
    
    widget = dock.widget()
    editor = getattr(widget, "_gcode_edit", None)
    if not editor:
        return "G-Code Editor konnte nicht gefunden werden."

    gcode_text = editor.toPlainText()
    if not gcode_text.strip():
        return "Es ist kein G-Code im Editor geladen, den ich analysieren koennte."

    return gcode_text


def _analyze_gcode_response():
    """Holt den G-Code aus dem UI und fuehrt die CAM-Analyse aus."""
    gcode_text = _get_editor_gcode()
    if "nicht" in gcode_text or "Panel" in gcode_text:
        return gcode_text

    try:
        from .cam_analysis import analyze_gcode
    except ImportError:
        from ai.cam_analysis import analyze_gcode

    result = analyze_gcode(gcode_text)
    lines = [f"### {result.summary}", ""]
    
    for issue in result.issues:
        icon = "⚠️" if issue.severity == "warning" else "ℹ️"
        lines.append(f"{icon} **{issue.message}**")
        if issue.suggestion:
            lines.append(f"   *Vorschlag: {issue.suggestion}*")
    
    return "\n".join(lines)


def _explain_cam_warning_response():
    """Erklaert spezifische CAM-Warnungen wie den 'Plunge step'."""
    return (
        "Die Warnung 'Plunge step is large' bedeutet, dass der Fraeser eine weite Strecke in Z-Richtung "
        "faehrt, bevor der erste Schnitt erfolgt. Oft ist das der Weg von der Sicherheitshoehe (Z5) "
        "zum ersten Materialkontakt (Z-1). Wenn dein Material bei Z0 liegt, ist das okay. "
        "Pruefe aber, ob der Nullpunkt korrekt gesetzt ist!"
    )


def _start_job_response():
    """Initiiert den Fräsjob direkt aus dem Chat."""
    gcode_text = _get_editor_gcode()
    if not gcode_text or len(gcode_text) < 10:
        return "Ich kann keinen Job starten, da kein G-Code im Editor geladen ist."
    
    results, errors = execute_actions([{
        "type": "machine_stream_gcode", 
        "params": {"gcode": gcode_text, "confirm": True}
    }])
    if errors:
        return f"Job konnte nicht gestartet werden: {errors[0]}"
    return "Sende G-Code an die Maschine... Bitte bleib am Not-Aus!"


def _machine_connect_response(prompt):
    """Versucht eine Verbindung aufzubauen oder fragt nach dem Port."""
    ports = re.findall(r"(?:/dev/|COM)\w+", prompt)
    port = ports[0] if ports else "AUTO"
    
    results, errors = execute_actions([{"type": "machine_connect", "params": {"port": port}}])
    if errors:
        return f"Verbindungsfehler: {errors[0]}\nBitte gib den Port an (z.B. 'Verbinde mit COM3')."
    return results[0] if results else f"Verbindung mit {port} initiiert."


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


_BOX_TERMS = ("box", "cube", "wuerfel", "quader", "kiste")
_CYL_TERMS = ("cylinder", "zylinder", "rolle")
_SPHERE_TERMS = ("sphere", "kugel", "ball")
_PAD_TERMS = ("pad", "extrude", "extrusion", "aufpolster", "aufpolstern")
_FAIL_TERMS = ("fail", "failed", "fehl", "schlaegt", "error", "fehler")
_SKETCH_TERMS = ("sketch", "skizze")
_UNSTABLE_TERMS = ("instabil", "unstable", "underconstrained", "unterb", "loesst sich", "springt")
_SPLINE_TERMS = ("spline", "bezier", "kurve", "control point", "kontrollpunkt")
_CREATE_TERMS = ("erzeuge", "erstelle", "generate", "create", "mach", "bau")
_ANALYZE_TERMS = ("pruef", "check", "analys", "untersuch", "test")
_WARNING_TERMS = ("warnung", "risiko", "gefahr", "plunge", "eintauch")
_START_TERMS = ("start", "lauf", "beginn", "stream", "feuer")
_CAM_TERMS = ("gcode", "toolpath", "cam", "fraese", "fraesen", "toolpath", "tool path")
_HELP_TERMS = (
    "hilfe",
    "help",
    "doc",
    "docs",
    "doku",
    "dokumentation",
    "anleitung",
    "manual",
    "tools",
    "tool",
    "aktionen",
    "actions",
    "faehigkeiten",
    "funktionen",
    "was kannst du",
    "was kann die ki",
    "was kann die ai",
    "was kann routerking",
)
_TEST_MILL_TERMS = ("fraes", "fraese", "fraesen")
_TEST_OBJECT_TERMS = ("objekt", "teil", "part", "sample", "datei", "file", "gcode", "nc")
