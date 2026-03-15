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
    machine_profile_path: Optional[str] = None,
    confirm: bool = False,
    reason: str = "",
    connection: Optional[FreeCADConnection] = None,
):
    action = {"type": "machine_stream_gcode", "gcode": gcode, "confirm": confirm, "reason": reason}
    if machine_profile_path:
        action["machine_profile_path"] = machine_profile_path
    return routerking_apply_actions(
        {"actions": [action]},
        include_context=True,
        connection=connection,
    )


def routerking_machine_validate_gcode(
    *,
    gcode: str,
    machine_profile_path: Optional[str] = None,
    connection: Optional[FreeCADConnection] = None,
):
    action = {"type": "machine_validate_gcode", "gcode": gcode}
    if machine_profile_path:
        action["machine_profile_path"] = machine_profile_path
    return routerking_apply_actions(
        {"actions": [action]},
        include_context=True,
        connection=connection,
    )


def routerking_machine_stop(*, confirm: bool = False, reason: str = "", connection: Optional[FreeCADConnection] = None):
    return routerking_apply_actions(
        {"actions": [{"type": "machine_stop", "confirm": confirm, "reason": reason}]},
        include_context=True,
        connection=connection,
    )


def routerking_machine_probe_z(
    *,
    block_height: float,
    max_depth: float = -30.0,
    feed: float = 50.0,
    retract: float = 3.0,
    confirm: bool = False,
    reason: str = "",
    connection: Optional[FreeCADConnection] = None,
):
    return routerking_apply_actions(
        {
            "actions": [
                {
                    "type": "machine_probe_z",
                    "block_height": block_height,
                    "max_depth": max_depth,
                    "feed": feed,
                    "retract": retract,
                    "confirm": confirm,
                    "reason": reason,
                }
            ]
        },
        include_context=True,
        connection=connection,
    )


def routerking_machine_probe_config(
    *,
    block_height: Optional[float] = None,
    probe_feed: Optional[float] = None,
    retract: Optional[float] = None,
    connection: Optional[FreeCADConnection] = None,
):
    action = {"type": "machine_probe_config"}
    if block_height is not None:
        action["block_height"] = block_height
    if probe_feed is not None:
        action["probe_feed"] = probe_feed
    if retract is not None:
        action["retract"] = retract
    return routerking_apply_actions(
        {"actions": [action]},
        include_context=True,
        connection=connection,
    )
