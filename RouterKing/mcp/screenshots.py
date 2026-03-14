"""Screenshot helpers for the active FreeCAD view."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict

try:  # pragma: no cover - FreeCADGui is optional in tests
    import FreeCADGui as Gui
except Exception:  # pragma: no cover - FreeCADGui not available in CI
    Gui = None


def capture_view(output_path: str | None = None, *, width: int = 1600, height: int = 900) -> Dict[str, Any]:
    if Gui is None:
        return {
            "available": False,
            "path": None,
            "message": "Screenshot unavailable: FreeCADGui is not available.",
        }

    active_document = getattr(Gui, "ActiveDocument", None)
    active_view = getattr(active_document, "ActiveView", None)
    if active_view is None:
        return {
            "available": False,
            "path": None,
            "message": "Screenshot unavailable: no active 3D view.",
        }

    path = output_path or _temporary_image_path()
    try:
        active_view.saveImage(path, width, height, "Current")
    except TypeError:
        active_view.saveImage(path, width, height)
    except Exception as exc:
        return {
            "available": False,
            "path": None,
            "message": f"Screenshot failed: {exc}",
        }

    return {
        "available": True,
        "path": path,
        "message": f"Screenshot captured: {os.path.abspath(path)}",
    }


def _temporary_image_path() -> str:
    handle, path = tempfile.mkstemp(prefix="routerking-mcp-", suffix=".png")
    os.close(handle)
    return path

