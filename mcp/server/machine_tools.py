"""Machine-oriented wrappers with explicit confirmation requirements."""

from __future__ import annotations

from typing import Optional

from .freecad_connection import FreeCADConnection
from .routerking_tools import routerking_apply_actions


def routerking_machine_connect(
    *,
    port: str,
    baudrate: int = 115200,
    confirm: bool = False,
    reason: str = "",
    connection: Optional[FreeCADConnection] = None,
):
    return routerking_apply_actions(
        {"actions": [{"type": "machine_connect", "port": port, "baudrate": baudrate, "confirm": confirm, "reason": reason}]},
        include_context=True,
        connection=connection,
    )


def routerking_machine_disconnect(*, confirm: bool = False, reason: str = "", connection: Optional[FreeCADConnection] = None):
    return routerking_apply_actions(
        {"actions": [{"type": "machine_disconnect", "confirm": confirm, "reason": reason}]},
        include_context=True,
        connection=connection,
    )


def routerking_machine_request_status(*, confirm: bool = False, reason: str = "", connection: Optional[FreeCADConnection] = None):
    return routerking_apply_actions(
        {"actions": [{"type": "machine_request_status", "confirm": confirm, "reason": reason}]},
        include_context=True,
        connection=connection,
    )


def routerking_machine_jog(
    *,
    feed: float,
    dx: float = 0.0,
    dy: float = 0.0,
    dz: float = 0.0,
    confirm: bool = False,
    reason: str = "",
    connection: Optional[FreeCADConnection] = None,
):
    return routerking_apply_actions(
        {
            "actions": [
                {
                    "type": "machine_jog",
                    "feed": feed,
                    "dx": dx,
                    "dy": dy,
                    "dz": dz,
                    "confirm": confirm,
                    "reason": reason,
                }
            ]
        },
        include_context=True,
        connection=connection,
    )


def routerking_machine_stream_gcode(
    *,
    gcode: str,
    confirm: bool = False,
    reason: str = "",
    connection: Optional[FreeCADConnection] = None,
):
    return routerking_apply_actions(
        {"actions": [{"type": "machine_stream_gcode", "gcode": gcode, "confirm": confirm, "reason": reason}]},
        include_context=True,
        connection=connection,
    )


def routerking_machine_stop(*, confirm: bool = False, reason: str = "", connection: Optional[FreeCADConnection] = None):
    return routerking_apply_actions(
        {"actions": [{"type": "machine_stop", "confirm": confirm, "reason": reason}]},
        include_context=True,
        connection=connection,
    )

