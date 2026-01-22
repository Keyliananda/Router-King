"""Selection/context helpers for RouterKing AI tools."""

from dataclasses import dataclass, field


@dataclass
class SelectionItem:
    obj: object
    label: str
    type_id: str


@dataclass
class SelectionContext:
    items: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def get_selection_context():
    try:
        import FreeCADGui as Gui
    except Exception as exc:  # pragma: no cover - FreeCAD not available in CI
        return SelectionContext(warnings=[f"FreeCADGui unavailable: {exc}"])

    items = []
    for obj in Gui.Selection.getSelection():
        label = getattr(obj, "Label", None) or getattr(obj, "Name", "<unnamed>")
        type_id = getattr(obj, "TypeId", obj.__class__.__name__)
        items.append(SelectionItem(obj=obj, label=label, type_id=type_id))
    if not items:
        return SelectionContext(warnings=["No selection found."])
    return SelectionContext(items=items)
