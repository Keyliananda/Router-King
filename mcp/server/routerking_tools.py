"""RouterKing domain tools exposed by the MCP layer."""

from __future__ import annotations

from typing import Any, Optional

from .freecad_connection import FreeCADConnection


def routerking_list_actions(connection: Optional[FreeCADConnection] = None):
    return (connection or FreeCADConnection()).invoke("list_actions")


def routerking_apply_actions(
    payload: Any,
    *,
    include_context: bool = True,
    capture_view: bool = False,
    screenshot_path: str | None = None,
    connection: Optional[FreeCADConnection] = None,
):
    return (connection or FreeCADConnection()).invoke(
        "apply_actions",
        payload=payload,
        include_context=include_context,
        capture_view=capture_view,
        screenshot_path=screenshot_path,
    )

