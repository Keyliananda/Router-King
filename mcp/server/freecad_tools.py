"""Read-only MCP-facing FreeCAD tools."""

from __future__ import annotations

from typing import Optional

from .freecad_connection import FreeCADConnection


def list_documents(connection: Optional[FreeCADConnection] = None):
    return (connection or FreeCADConnection()).invoke("list_documents")


def get_active_document(connection: Optional[FreeCADConnection] = None):
    return (connection or FreeCADConnection()).invoke("get_active_document")


def get_scene_info(connection: Optional[FreeCADConnection] = None):
    return (connection or FreeCADConnection()).invoke("get_scene_info")


def get_selection_context(connection: Optional[FreeCADConnection] = None):
    return (connection or FreeCADConnection()).invoke("get_selection_context")


def capture_view(output_path: str | None = None, connection: Optional[FreeCADConnection] = None):
    return (connection or FreeCADConnection()).invoke("capture_view", output_path=output_path)

