"""Read-only FreeCAD context helpers exposed through the MCP bridge."""

from __future__ import annotations

from typing import Any, Dict, List

try:  # pragma: no cover - FreeCAD is optional in tests
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None

try:  # pragma: no cover - FreeCADGui is optional in tests
    import FreeCADGui as Gui
except Exception:  # pragma: no cover - FreeCADGui not available in CI
    Gui = None


def list_documents() -> Dict[str, Any]:
    warnings: List[str] = []
    documents: List[Dict[str, Any]] = []

    if App is None:
        warnings.append("FreeCAD is not available.")
        return {
            "documents": documents,
            "active_document": None,
            "warnings": warnings,
        }

    active_doc = getattr(App, "ActiveDocument", None)
    active_name = getattr(active_doc, "Name", None)
    list_docs = getattr(App, "listDocuments", None)
    raw_documents = list_docs() if callable(list_docs) else {}

    if isinstance(raw_documents, dict):
        for name, document in raw_documents.items():
            documents.append(_serialize_document(document, is_active=(name == active_name)))
    elif active_doc is not None:
        documents.append(_serialize_document(active_doc, is_active=True))

    return {
        "documents": documents,
        "active_document": active_name,
        "warnings": warnings,
    }


def get_active_document() -> Dict[str, Any]:
    if App is None:
        return {
            "document": None,
            "warnings": ["FreeCAD is not available."],
        }

    document = getattr(App, "ActiveDocument", None)
    if document is None:
        return {
            "document": None,
            "warnings": ["No active document."],
        }

    return {
        "document": _serialize_document(document, is_active=True),
        "warnings": [],
    }


def get_selection_context() -> Dict[str, Any]:
    warnings: List[str] = []

    active_document = get_active_document()
    document_name = None
    if active_document.get("document"):
        document_name = active_document["document"].get("name")

    if Gui is None:
        warnings.append("FreeCADGui is not available.")
        return {
            "document": document_name,
            "selection_count": 0,
            "selected_objects": [],
            "warnings": warnings,
        }

    try:
        selection = list(Gui.Selection.getSelection())
    except Exception as exc:
        warnings.append(f"Selection read failed: {exc}")
        selection = []

    objects = [_serialize_object(obj) for obj in selection]
    if not objects and not warnings:
        warnings.append("No selection found.")

    return {
        "document": document_name,
        "selection_count": len(objects),
        "selected_objects": objects,
        "warnings": warnings,
    }


def get_scene_info() -> Dict[str, Any]:
    active_document = get_active_document()
    document = active_document.get("document")
    warnings = list(active_document.get("warnings") or [])
    objects = []

    if document is not None and App is not None:
        current = getattr(App, "ActiveDocument", None)
        for obj in getattr(current, "Objects", []) or []:
            objects.append(_serialize_object(obj))

    selection = get_selection_context()
    warnings.extend(selection.get("warnings") or [])

    return {
        "document": document,
        "object_count": len(objects),
        "objects": objects,
        "selection": selection.get("selected_objects") or [],
        "selection_count": selection.get("selection_count", 0),
        "warnings": _dedupe_strings(warnings),
    }


def _serialize_document(document: Any, *, is_active: bool) -> Dict[str, Any]:
    active_object = getattr(document, "ActiveObject", None)
    return {
        "name": getattr(document, "Name", None),
        "label": getattr(document, "Label", None) or getattr(document, "Name", None),
        "is_active": bool(is_active),
        "object_count": len(getattr(document, "Objects", []) or []),
        "active_object": _serialize_object(active_object) if active_object is not None else None,
    }


def _serialize_object(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}

    type_id = getattr(obj, "TypeId", obj.__class__.__name__)
    payload = {
        "name": getattr(obj, "Name", None),
        "label": getattr(obj, "Label", None) or getattr(obj, "Name", None),
        "type": type_id,
    }

    view_object = getattr(obj, "ViewObject", None)
    if view_object is not None:
        payload["visible"] = bool(getattr(view_object, "Visibility", True))

    if "Sketcher::SketchObject" in str(type_id):
        payload.update(_serialize_sketch(obj))

    return payload


def _serialize_sketch(obj: Any) -> Dict[str, Any]:
    geometry = getattr(obj, "Geometry", None)
    constraints = getattr(obj, "Constraints", None)
    fully_constrained = getattr(obj, "FullyConstrained", None)

    return {
        "geometry_count": len(geometry or []),
        "constraint_count": len(constraints or []),
        "fully_constrained": bool(fully_constrained) if fully_constrained is not None else None,
    }


def _dedupe_strings(values: List[str]) -> List[str]:
    seen = set()
    unique = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique

