"""Simple document transaction wrapper for RouterKing MCP actions."""

from __future__ import annotations

try:  # pragma: no cover - FreeCAD is optional in tests
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None


class DocumentTransaction:
    def __init__(self) -> None:
        self._open = False
        self._name = None

    def open(self, name: str = "RouterKing MCP") -> bool:
        document = self._get_document()
        if document is None:
            return False
        try:
            document.openTransaction(name)
        except Exception:
            return False
        self._open = True
        self._name = name
        return True

    def commit(self) -> bool:
        if not self._open:
            return False
        document = self._get_document()
        if document is None:
            return False
        try:
            document.commitTransaction()
        except Exception:
            return False
        self._open = False
        return True

    def abort(self) -> bool:
        if not self._open:
            return False
        document = self._get_document()
        if document is None:
            return False
        try:
            document.abortTransaction()
        except Exception:
            return False
        self._open = False
        return True

    def is_open(self) -> bool:
        return self._open

    def _get_document(self):
        if App is None:
            return None
        return getattr(App, "ActiveDocument", None)

