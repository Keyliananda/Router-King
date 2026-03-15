"""GRBL-aware G-code validation and machine profile utilities."""

from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

_WORD_RE = re.compile(r"([A-Za-z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
_PAREN_COMMENT_RE = re.compile(r"\([^)]*\)")
_EPS = 1e-9


def default_machine_profile_path() -> Path:
    return Path(__file__).resolve().parents[1] / "machine_profile.json"


def load_machine_profile(profile_path: Optional[str] = None) -> tuple[dict, str]:
    candidates: list[Path] = []
    if profile_path:
        candidates.append(Path(profile_path).expanduser())
    env_path = os.getenv("ROUTERKING_MACHINE_PROFILE", "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.append(default_machine_profile_path())
    candidates.append(Path.cwd() / "machine_profile.json")
    candidates.append(Path.home() / "machine_profile.json")

    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            return data, str(path)
    return {}, ""


def save_machine_profile(profile: Mapping[str, Any], profile_path: Optional[str] = None) -> str:
    target = (
        Path(profile_path).expanduser()
        if profile_path
        else Path(os.getenv("ROUTERKING_MACHINE_PROFILE", "").strip() or default_machine_profile_path())
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(profile), indent=2, sort_keys=True)
    target.write_text(payload + "\n", encoding="utf-8")
    return str(target)


def read_machine_status(sender: Any) -> dict:
    if sender is None:
        return {}
    connected = bool(getattr(sender, "is_connected", lambda: False)())
    if not connected:
        try:
            return dict(getattr(sender, "get_status", lambda: {})() or {})
        except Exception:
            return {}

    status: dict = {}
    try:
        sender.poll()
        sender.request_status()
    except Exception:
        return {}

    deadline = time.time() + 0.6
    while time.time() < deadline:
        try:
            sender.poll()
            raw = sender.get_status() or {}
        except Exception:
            raw = {}
        if raw:
            status = dict(raw)
            if status.get("state", "?") != "?":
                break
        time.sleep(0.05)
    return status


def parse_grbl_settings_lines(lines: Sequence[str]) -> dict:
    settings: dict = {}
    for line in lines or []:
        text = str(line or "").strip()
        if not text.startswith("$") or "=" not in text:
            continue
        key, _, value = text.partition("=")
        settings[key.strip()] = value.strip()
    return settings


def read_grbl_settings(sender: Any) -> dict:
    if sender is None:
        return {}
    if not bool(getattr(sender, "is_connected", lambda: False)()):
        return {}
    if bool(getattr(sender, "is_streaming", lambda: False)()):
        return {}
    try:
        lines = sender.send_and_collect("$$", timeout=2.0)
    except Exception:
        return {}
    return parse_grbl_settings_lines(lines or [])


def merge_machine_profile(
    existing_profile: Optional[Mapping[str, Any]],
    *,
    settings: Optional[Mapping[str, Any]],
    status: Optional[Mapping[str, Any]],
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    merged = dict(existing_profile or {})
    merged.setdefault("created_at", now)
    merged["updated_at"] = now

    settings_map = dict(settings or {})
    status_map = dict(status or {})

    if settings_map:
        merged["settings"] = settings_map
    if status_map:
        merged["status"] = status_map

    work_envelope = {
        "x": abs(_first_number(settings_map.get("$130"), _nested_number(merged, "work_envelope_mm", "x"), 0.0)),
        "y": abs(_first_number(settings_map.get("$131"), _nested_number(merged, "work_envelope_mm", "y"), 0.0)),
        "z": abs(_first_number(settings_map.get("$132"), _nested_number(merged, "work_envelope_mm", "z"), 0.0)),
    }
    merged["work_envelope_mm"] = work_envelope
    merged["machine_limits"] = {
        "x": [-work_envelope["x"], 0.0],
        "y": [-work_envelope["y"], 0.0],
        "z": [-work_envelope["z"], 0.0],
    }

    max_feeds = {
        "x": _first_number(settings_map.get("$110"), _nested_number(merged, "max_feeds_mm_min", "x"), 0.0),
        "y": _first_number(settings_map.get("$111"), _nested_number(merged, "max_feeds_mm_min", "y"), 0.0),
        "z": _first_number(settings_map.get("$112"), _nested_number(merged, "max_feeds_mm_min", "z"), 0.0),
    }
    merged["max_feeds_mm_min"] = max_feeds

    merged["steps_per_mm"] = {
        "x": _first_number(settings_map.get("$100"), _nested_number(merged, "steps_per_mm", "x"), 0.0),
        "y": _first_number(settings_map.get("$101"), _nested_number(merged, "steps_per_mm", "y"), 0.0),
        "z": _first_number(settings_map.get("$102"), _nested_number(merged, "steps_per_mm", "z"), 0.0),
    }

    homing_mask = int(_first_number(settings_map.get("$23"), _nested_number(merged, "homing", "dir_mask"), 0.0))
    pull_off = _first_number(settings_map.get("$27"), _nested_number(merged, "homing", "pull_off_mm"), 3.0)
    merged["homing"] = {
        "enabled": _to_float(settings_map.get("$22")) == 1.0,
        "dir_mask": homing_mask,
        "directions": _decode_homing_directions(homing_mask),
        "pull_off_mm": pull_off,
    }

    mpos = parse_xyz_value(status_map.get("MPos"))
    wpos = parse_xyz_value(status_map.get("WPos"))
    wco = parse_xyz_value(status_map.get("WCO"))
    if wco is None and mpos is not None and wpos is not None:
        wco = {
            "x": mpos["x"] - wpos["x"],
            "y": mpos["y"] - wpos["y"],
            "z": mpos["z"] - wpos["z"],
        }
    if mpos is not None:
        merged["machine_position"] = mpos
        merged["home_position_mpos"] = mpos
    if wpos is not None:
        merged["work_position"] = wpos
    if wco is not None:
        merged["work_offset"] = wco

    laser_mode = _to_float(settings_map.get("$32")) == 1.0
    spindle_max = _first_number(settings_map.get("$30"), _nested_number(merged, "capabilities", "spindle", "max_rpm"), 0.0)
    spindle_min = _first_number(settings_map.get("$31"), _nested_number(merged, "capabilities", "spindle", "min_rpm"), 0.0)
    existing_caps = dict(merged.get("capabilities") or {})
    existing_spindle = bool(existing_caps.get("spindle_supported"))
    spindle_supported = bool(laser_mode or spindle_max > 0.0 or existing_spindle)
    coolant_supported = bool(existing_caps.get("coolant_supported", False))
    merged["capabilities"] = {
        "laser_mode": laser_mode,
        "spindle_supported": spindle_supported,
        "coolant_supported": coolant_supported,
        "spindle": {
            "max_rpm": spindle_max,
            "min_rpm": spindle_min,
        },
    }
    return merged


def resolve_machine_limits(
    profile: Optional[Mapping[str, Any]],
    settings: Optional[Mapping[str, Any]],
) -> tuple[dict, str]:
    profile_map = dict(profile or {})
    settings_map = dict(settings or {})

    limits: dict = {}
    source: dict = {}
    for axis, setting_key in (("x", "$130"), ("y", "$131"), ("z", "$132")):
        profile_value = _profile_travel_value(profile_map, axis, setting_key)
        settings_value = _to_float(settings_map.get(setting_key))
        travel = abs(profile_value if profile_value is not None else settings_value if settings_value is not None else 0.0)
        if travel <= 0.0:
            raise ValueError(f"missing machine travel for {axis.upper()} ({setting_key})")
        limits[axis] = (-travel, 0.0)
        source[axis] = "machine_profile.json" if profile_value is not None else "grbl_$$"

    source_text = source["x"] if len(set(source.values())) == 1 else "machine_profile.json + grbl_$$"
    return limits, source_text


def resolve_max_feeds(
    profile: Optional[Mapping[str, Any]],
    settings: Optional[Mapping[str, Any]],
) -> tuple[dict, str]:
    profile_map = dict(profile or {})
    settings_map = dict(settings or {})
    feeds: dict = {}
    source: dict = {}
    for axis, setting_key in (("x", "$110"), ("y", "$111"), ("z", "$112")):
        profile_value = _profile_feed_value(profile_map, axis, setting_key)
        settings_value = _to_float(settings_map.get(setting_key))
        value = profile_value if profile_value is not None else settings_value
        if value is None or value <= 0.0:
            raise ValueError(f"missing max feed for {axis.upper()} ({setting_key})")
        feeds[axis] = float(value)
        source[axis] = "machine_profile.json" if profile_value is not None else "grbl_$$"
    source_text = source["x"] if len(set(source.values())) == 1 else "machine_profile.json + grbl_$$"
    return feeds, source_text


def resolve_work_offset(
    status: Optional[Mapping[str, Any]],
    profile: Optional[Mapping[str, Any]],
) -> tuple[dict, str]:
    status_map = dict(status or {})
    profile_map = dict(profile or {})

    wco = parse_xyz_value(status_map.get("WCO"))
    if wco is not None:
        return wco, "status.WCO"

    mpos = parse_xyz_value(status_map.get("MPos"))
    wpos = parse_xyz_value(status_map.get("WPos"))
    if mpos is not None and wpos is not None:
        return {
            "x": mpos["x"] - wpos["x"],
            "y": mpos["y"] - wpos["y"],
            "z": mpos["z"] - wpos["z"],
        }, "status.MPos-WPos"

    for key in ("work_offset", "wco", "g54", "g54_offset"):
        value = parse_xyz_value(profile_map.get(key))
        if value is not None:
            return value, f"profile.{key}"

    raise ValueError("unable to determine current work offset (WCO/G54)")


def resolve_start_work_position(
    status: Optional[Mapping[str, Any]],
    wco: Mapping[str, float],
    profile: Optional[Mapping[str, Any]],
) -> dict:
    status_map = dict(status or {})
    profile_map = dict(profile or {})

    wpos = parse_xyz_value(status_map.get("WPos"))
    if wpos is not None:
        return wpos
    mpos = parse_xyz_value(status_map.get("MPos"))
    if mpos is not None:
        return {
            "x": mpos["x"] - float(wco["x"]),
            "y": mpos["y"] - float(wco["y"]),
            "z": mpos["z"] - float(wco["z"]),
        }
    for key in ("work_position", "wpos", "position"):
        value = parse_xyz_value(profile_map.get(key))
        if value is not None:
            return value
    return {"x": 0.0, "y": 0.0, "z": 0.0}


def resolve_capabilities(
    profile: Optional[Mapping[str, Any]],
    settings: Optional[Mapping[str, Any]],
) -> dict:
    profile_map = dict(profile or {})
    settings_map = dict(settings or {})
    caps = dict(profile_map.get("capabilities") or {})
    laser_mode = bool(caps.get("laser_mode", _to_float(settings_map.get("$32")) == 1.0))
    spindle_supported = bool(
        caps.get("spindle_supported")
        or laser_mode
        or _first_number(_nested_value(caps, "spindle", "max_rpm"), settings_map.get("$30"), 0.0) > 0.0
    )
    coolant_supported = bool(caps.get("coolant_supported", False))
    return {
        "laser_mode": laser_mode,
        "spindle_supported": spindle_supported,
        "coolant_supported": coolant_supported,
    }


def validate_gcode(
    gcode: str | Sequence[str],
    *,
    machine_profile: Optional[Mapping[str, Any]] = None,
    grbl_settings: Optional[Mapping[str, Any]] = None,
    status: Optional[Mapping[str, Any]] = None,
    machine_profile_path: Optional[str] = None,
    start_work_position: Optional[Mapping[str, Any]] = None,
) -> dict:
    lines = prepare_gcode_lines(gcode)
    result: dict = {
        "valid": True,
        "errors": [],
        "bounding_box": {"x": [0.0, 0.0], "y": [0.0, 0.0], "z": [0.0, 0.0]},
        "machine_bounding_box": {"x": [0.0, 0.0], "y": [0.0, 0.0], "z": [0.0, 0.0]},
        "estimated_time_seconds": 0,
        "line_count": len(lines),
        "move_count": 0,
    }
    if not lines:
        result["valid"] = False
        result["errors"] = [{"line": 0, "command": "", "reason": "No G-code lines found."}]
        return result

    profile = dict(machine_profile or {})
    profile_source = ""
    if not profile:
        profile, profile_source = load_machine_profile(machine_profile_path)
    settings = dict(grbl_settings or {})
    if not settings and isinstance(profile.get("settings"), Mapping):
        settings = dict(profile.get("settings") or {})
    status_map = dict(status or {})
    if not status_map and isinstance(profile.get("status"), Mapping):
        status_map = dict(profile.get("status") or {})

    try:
        limits, limits_source = resolve_machine_limits(profile, settings)
    except Exception as exc:
        return {
            **result,
            "valid": False,
            "errors": [{"line": 0, "command": "", "reason": str(exc)}],
        }
    try:
        max_feeds, max_feed_source = resolve_max_feeds(profile, settings)
    except Exception as exc:
        return {
            **result,
            "valid": False,
            "errors": [{"line": 0, "command": "", "reason": str(exc)}],
        }
    capabilities = resolve_capabilities(profile, settings)
    try:
        wco, offset_source = resolve_work_offset(status_map, profile)
    except Exception as exc:
        return {
            **result,
            "valid": False,
            "errors": [{"line": 0, "command": "", "reason": str(exc)}],
        }
    start_work = (
        parse_xyz_value(start_work_position) if start_work_position is not None else resolve_start_work_position(status_map, wco, profile)
    )
    if start_work is None:
        start_work = {"x": 0.0, "y": 0.0, "z": 0.0}

    simulation = _simulate_gcode(
        lines=lines,
        start_work=start_work,
        wco=wco,
        limits=limits,
        max_feeds=max_feeds,
        capabilities=capabilities,
    )
    simulation["valid"] = len(simulation["errors"]) == 0
    simulation["offset_source"] = offset_source
    simulation["limits_source"] = limits_source
    simulation["max_feeds_source"] = max_feed_source
    simulation["profile_source"] = profile_source
    simulation["limits_machine"] = limits
    simulation["max_feeds_mm_min"] = max_feeds
    simulation["work_offset"] = wco
    return simulation


def calculate_g54_offset(
    *,
    bounding_box: Mapping[str, Any],
    limits: Mapping[str, Sequence[float]],
    current_machine_position: Optional[Mapping[str, Any]] = None,
    desired_workpiece_corner: Optional[Mapping[str, Any]] = None,
    safety_margin_mm: float = 5.0,
) -> dict:
    margin = max(float(safety_margin_mm), 0.0)
    bbox = _normalize_bbox(bounding_box)
    if bbox is None:
        return {
            "fits": False,
            "warnings": ["Invalid bounding_box; expected {'x':[min,max], 'y':[min,max], 'z':[min,max]}."],
        }

    axis_ranges: dict = {}
    warnings: list[str] = []
    for axis in ("x", "y", "z"):
        axis_limits = limits.get(axis)
        if not axis_limits or len(axis_limits) < 2:
            return {"fits": False, "warnings": [f"Missing machine limits for axis {axis.upper()}."]}
        lmin = float(axis_limits[0])
        lmax = float(axis_limits[1])
        wmin, wmax = bbox[axis]
        wco_min = (lmin + margin) - wmin
        wco_max = (lmax - margin) - wmax
        if wco_min > wco_max:
            return {
                "fits": False,
                "warnings": [
                    f"Toolpath does not fit on axis {axis.upper()} with {margin:.1f}mm safety margin."
                ],
                "axis": axis,
            }
        axis_ranges[axis] = [wco_min, wco_max]

    desired_machine = _extract_desired_machine_corner(desired_workpiece_corner)
    corner_mode = _extract_corner_mode(desired_workpiece_corner)
    wco: dict = {}
    for axis in ("x", "y", "z"):
        selector = corner_mode[axis]
        work_corner = bbox[axis][0] if selector == "min" else bbox[axis][1]
        if desired_machine is not None and axis in desired_machine:
            candidate = desired_machine[axis] - work_corner
        else:
            candidate = 0.5 * (axis_ranges[axis][0] + axis_ranges[axis][1])
        clamped = min(max(candidate, axis_ranges[axis][0]), axis_ranges[axis][1])
        if abs(clamped - candidate) > 1e-6:
            warnings.append(
                f"Adjusted {axis.upper()} offset by {clamped - candidate:.3f}mm to satisfy limits."
            )
        wco[axis] = clamped

    mpos = parse_xyz_value(current_machine_position) if current_machine_position is not None else None
    g10_command = None
    if mpos is not None:
        cmd_pos = {axis: mpos[axis] - wco[axis] for axis in ("x", "y", "z")}
        g10_command = (
            f"G10 L20 P1 X{_fmt(cmd_pos['x'])} Y{_fmt(cmd_pos['y'])} Z{_fmt(cmd_pos['z'])}"
        )
    else:
        warnings.append("Current machine position missing; returning offset only (no G10 command).")

    return {
        "fits": True,
        "warnings": warnings,
        "safety_margin_mm": margin,
        "offset_ranges": axis_ranges,
        "g54_offset": wco,
        "g10_command": g10_command,
        "bounding_box": bbox,
    }


def prepare_gcode_lines(gcode: str | Sequence[str]) -> list[str]:
    if isinstance(gcode, str):
        raw_lines = gcode.splitlines()
    else:
        raw_lines = [str(line) for line in gcode]
    return [line.strip() for line in raw_lines if str(line).strip()]


def strip_gcode_comments(line: str) -> str:
    stripped = str(line or "")
    stripped = stripped.split(";", 1)[0]
    previous = None
    while previous != stripped:
        previous = stripped
        stripped = _PAREN_COMMENT_RE.sub("", stripped)
    return stripped.strip()


def parse_gcode_words(line: str) -> list[tuple[str, float]]:
    words: list[tuple[str, float]] = []
    for match in _WORD_RE.finditer(line):
        letter = match.group(1).upper()
        try:
            value = float(match.group(2))
        except Exception:
            continue
        words.append((letter, value))
    return words


def parse_xyz_value(value: Any) -> Optional[dict]:
    if value is None:
        return None
    if isinstance(value, Mapping):
        x = _to_float(value.get("x", value.get("X")))
        y = _to_float(value.get("y", value.get("Y")))
        z = _to_float(value.get("z", value.get("Z")))
        if x is None or y is None or z is None:
            return None
        return {"x": x, "y": y, "z": z}
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        x = _to_float(value[0])
        y = _to_float(value[1])
        z = _to_float(value[2])
        if x is None or y is None or z is None:
            return None
        return {"x": x, "y": y, "z": z}
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        if len(parts) < 3:
            return None
        x = _to_float(parts[0])
        y = _to_float(parts[1])
        z = _to_float(parts[2])
        if x is None or y is None or z is None:
            return None
        return {"x": x, "y": y, "z": z}
    return None


def _simulate_gcode(
    *,
    lines: Sequence[str],
    start_work: Mapping[str, float],
    wco: Mapping[str, float],
    limits: Mapping[str, Sequence[float]],
    max_feeds: Mapping[str, float],
    capabilities: Mapping[str, Any],
) -> dict:
    pos = {"x": float(start_work["x"]), "y": float(start_work["y"]), "z": float(start_work["z"])}
    bbox = {"x": [pos["x"], pos["x"]], "y": [pos["y"], pos["y"]], "z": [pos["z"], pos["z"]]}
    bbox_machine = _bbox_from_machine_point(_work_to_machine(pos, wco))

    state = {
        "distance_absolute": True,
        "arc_center_absolute": False,
        "unit_scale": 1.0,
        "plane": "G17",
        "motion": 0,
    }
    move_count = 0
    total_seconds = 0.0
    errors: list[dict] = []

    for line_no, raw_line in enumerate(lines, start=1):
        cleaned = strip_gcode_comments(raw_line)
        if not cleaned:
            continue
        words = parse_gcode_words(cleaned)
        if not words:
            continue

        axis_words: dict[str, float] = {}
        center_words: dict[str, float] = {}
        radius_value = None
        line_motion = None
        machine_coords_block = False
        line_distance_mode = state["distance_absolute"]
        feed_word = None
        line_has_mfeed_required_motion = False

        for letter, number in words:
            if letter == "G":
                if _near(number, 0.0):
                    line_motion = 0
                elif _near(number, 1.0):
                    line_motion = 1
                    line_has_mfeed_required_motion = True
                elif _near(number, 2.0):
                    line_motion = 2
                    line_has_mfeed_required_motion = True
                elif _near(number, 3.0):
                    line_motion = 3
                    line_has_mfeed_required_motion = True
                elif _near(number, 17.0):
                    state["plane"] = "G17"
                elif _near(number, 18.0):
                    state["plane"] = "G18"
                elif _near(number, 19.0):
                    state["plane"] = "G19"
                elif _near(number, 20.0):
                    state["unit_scale"] = 25.4
                elif _near(number, 21.0):
                    state["unit_scale"] = 1.0
                elif _near(number, 53.0):
                    machine_coords_block = True
                elif _near(number, 54.0):
                    pass
                elif any(_near(number, value) for value in (38.0, 38.2, 38.3, 38.4, 38.5)):
                    _append_error(
                        errors,
                        line=line_no,
                        command=raw_line,
                        reason="G38.x probing commands are not allowed in normal G-code streaming; use machine_probe_z.",
                    )
                elif any(_near(number, value) for value in (55.0, 56.0, 57.0, 58.0, 59.0)):
                    _append_error(
                        errors,
                        line=line_no,
                        command=raw_line,
                        reason=f"Unsupported work coordinate system G{int(round(number))}; validator uses active G54 only.",
                    )
                elif _near(number, 90.0):
                    state["distance_absolute"] = True
                    line_distance_mode = True
                elif _near(number, 91.0):
                    state["distance_absolute"] = False
                    line_distance_mode = False
                elif _near(number, 90.1):
                    state["arc_center_absolute"] = True
                elif _near(number, 91.1):
                    state["arc_center_absolute"] = False
            elif letter in ("X", "Y", "Z"):
                axis_words[letter.lower()] = number * state["unit_scale"]
            elif letter in ("I", "J", "K"):
                center_words[letter.lower()] = number * state["unit_scale"]
            elif letter == "R":
                radius_value = number * state["unit_scale"]
            elif letter == "F":
                feed_word = number * state["unit_scale"]
                if feed_word <= 0.0:
                    _append_error(errors, line=line_no, command=raw_line, reason="F0/negative feed is invalid.")
            elif letter == "M":
                _check_mcode(
                    line_no=line_no,
                    raw_line=raw_line,
                    number=number,
                    capabilities=capabilities,
                    errors=errors,
                )

        if line_motion is not None:
            state["motion"] = line_motion
        motion = state["motion"]
        if motion not in (0, 1, 2, 3):
            continue

        if line_has_mfeed_required_motion and feed_word is None:
            _append_error(
                errors,
                line=line_no,
                command=raw_line,
                reason="Missing feed rate F on G1/G2/G3 line.",
            )

        target = dict(pos)
        if machine_coords_block:
            current_machine = _work_to_machine(pos, wco)
            for axis in ("x", "y", "z"):
                if axis not in axis_words:
                    continue
                value = axis_words[axis]
                if line_distance_mode:
                    machine_value = value
                else:
                    machine_value = current_machine[axis] + value
                target[axis] = machine_value - float(wco[axis])
        else:
            for axis in ("x", "y", "z"):
                if axis not in axis_words:
                    continue
                value = axis_words[axis]
                if line_distance_mode:
                    target[axis] = value
                else:
                    target[axis] += value

        if motion in (0, 1):
            if not _has_position_change(pos, target):
                continue
            machine_target = _work_to_machine(target, wco)
            _check_machine_limits(
                machine_target=machine_target,
                limits=limits,
                line_no=line_no,
                raw_line=raw_line,
                errors=errors,
            )
            _update_bbox(bbox, target)
            _update_bbox(bbox_machine, machine_target)
            distance = _distance(pos, target)
            if motion == 1 and feed_word and feed_word > 0:
                _check_linear_axis_feeds(
                    start=pos,
                    target=target,
                    feed=feed_word,
                    max_feeds=max_feeds,
                    line_no=line_no,
                    raw_line=raw_line,
                    errors=errors,
                )
                total_seconds += (distance / feed_word) * 60.0
            else:
                rapid_feed = max(max_feeds.values()) if max_feeds else 3000.0
                if rapid_feed > 0:
                    total_seconds += (distance / rapid_feed) * 60.0
            pos = target
            move_count += 1
            continue

        if not _has_position_change(pos, target) and not center_words and radius_value is None:
            continue

        arc_points, arc_length, plane_axes = _build_arc_check_points(
            start=pos,
            target=target,
            plane=state["plane"],
            clockwise=(motion == 2),
            center_words=center_words,
            radius_value=radius_value,
            arc_center_absolute=state["arc_center_absolute"],
            line_no=line_no,
            raw_line=raw_line,
            errors=errors,
        )
        for point in arc_points:
            machine_point = _work_to_machine(point, wco)
            _check_machine_limits(
                machine_target=machine_point,
                limits=limits,
                line_no=line_no,
                raw_line=raw_line,
                errors=errors,
            )
            _update_bbox(bbox, point)
            _update_bbox(bbox_machine, machine_point)
        if feed_word and feed_word > 0:
            _check_arc_feeds(
                feed=feed_word,
                plane_axes=plane_axes,
                start=pos,
                target=target,
                arc_length=arc_length,
                max_feeds=max_feeds,
                line_no=line_no,
                raw_line=raw_line,
                errors=errors,
            )
            total_seconds += (arc_length / feed_word) * 60.0 if arc_length > _EPS else 0.0
        pos = target
        move_count += 1

    return {
        "errors": errors,
        "bounding_box": bbox,
        "machine_bounding_box": bbox_machine,
        "estimated_time_seconds": int(round(max(total_seconds, 0.0))),
        "line_count": len(lines),
        "move_count": move_count,
    }


def _check_mcode(
    *,
    line_no: int,
    raw_line: str,
    number: float,
    capabilities: Mapping[str, Any],
    errors: list[dict],
) -> None:
    code = int(round(number))
    spindle_supported = bool(capabilities.get("spindle_supported", False))
    coolant_supported = bool(capabilities.get("coolant_supported", False))
    if code in (3, 4, 5) and not spindle_supported:
        _append_error(
            errors,
            line=line_no,
            command=raw_line,
            reason=f"M{code} is unsupported on this machine (no spindle/laser capability configured).",
        )
    if code in (7, 8, 9) and not coolant_supported:
        _append_error(
            errors,
            line=line_no,
            command=raw_line,
            reason=f"M{code} coolant command is unsupported.",
        )


def _check_linear_axis_feeds(
    *,
    start: Mapping[str, float],
    target: Mapping[str, float],
    feed: float,
    max_feeds: Mapping[str, float],
    line_no: int,
    raw_line: str,
    errors: list[dict],
) -> None:
    length = _distance(start, target)
    if length <= _EPS:
        return
    for axis in ("x", "y", "z"):
        axis_speed = abs(target[axis] - start[axis]) / length * feed
        axis_limit = float(max_feeds[axis])
        if axis_speed > axis_limit + 1e-6:
            _append_error(
                errors,
                line=line_no,
                command=raw_line,
                reason=(
                    f"Feed exceeds {axis.upper()} axis max. "
                    f"Axis speed {axis_speed:.3f}mm/min > limit {axis_limit:.3f}mm/min."
                ),
            )


def _check_arc_feeds(
    *,
    feed: float,
    plane_axes: tuple[str, str, str],
    start: Mapping[str, float],
    target: Mapping[str, float],
    arc_length: float,
    max_feeds: Mapping[str, float],
    line_no: int,
    raw_line: str,
    errors: list[dict],
) -> None:
    u_axis, v_axis, w_axis = plane_axes
    for axis in (u_axis, v_axis):
        axis_limit = float(max_feeds[axis])
        if feed > axis_limit + 1e-6:
            _append_error(
                errors,
                line=line_no,
                command=raw_line,
                reason=(
                    f"Feed exceeds {axis.upper()} axis max on arc. "
                    f"F{feed:.3f} > limit {axis_limit:.3f}."
                ),
            )
    if arc_length > _EPS:
        axis_speed_w = abs(target[w_axis] - start[w_axis]) / arc_length * feed
        axis_limit_w = float(max_feeds[w_axis])
        if axis_speed_w > axis_limit_w + 1e-6:
            _append_error(
                errors,
                line=line_no,
                command=raw_line,
                reason=(
                    f"Helical arc exceeds {w_axis.upper()} axis max. "
                    f"Axis speed {axis_speed_w:.3f}mm/min > limit {axis_limit_w:.3f}mm/min."
                ),
            )


def _build_arc_check_points(
    *,
    start: Mapping[str, float],
    target: Mapping[str, float],
    plane: str,
    clockwise: bool,
    center_words: Mapping[str, float],
    radius_value: Optional[float],
    arc_center_absolute: bool,
    line_no: int,
    raw_line: str,
    errors: list[dict],
) -> tuple[list[dict], float, tuple[str, str, str]]:
    u_axis, v_axis, w_axis, c1_word, c2_word = _plane_axes(plane)
    su = float(start[u_axis])
    sv = float(start[v_axis])
    eu = float(target[u_axis])
    ev = float(target[v_axis])

    if radius_value is not None:
        center = _arc_center_from_radius(
            su,
            sv,
            eu,
            ev,
            radius_value,
            clockwise=clockwise,
        )
        if center is None:
            _append_error(errors, line=line_no, command=raw_line, reason="Arc radius R is invalid for start/end points.")
            return ([dict(target)], _distance(start, target), (u_axis, v_axis, w_axis))
        cu, cv, sweep_delta = center
    else:
        c1 = center_words.get(c1_word)
        c2 = center_words.get(c2_word)
        if c1 is None and c2 is None:
            _append_error(errors, line=line_no, command=raw_line, reason="Arc move requires I/J/K center offsets or R radius.")
            return ([dict(target)], _distance(start, target), (u_axis, v_axis, w_axis))
        c1 = 0.0 if c1 is None else float(c1)
        c2 = 0.0 if c2 is None else float(c2)
        if arc_center_absolute:
            cu, cv = c1, c2
        else:
            cu, cv = su + c1, sv + c2
        sweep_delta = _arc_sweep_delta((cu, cv), su, sv, eu, ev, clockwise)
        if sweep_delta <= _EPS:
            sweep_delta = 2.0 * math.pi

    radius = math.hypot(su - cu, sv - cv)
    if radius <= _EPS:
        _append_error(errors, line=line_no, command=raw_line, reason="Arc radius is effectively zero.")
        return ([dict(target)], _distance(start, target), (u_axis, v_axis, w_axis))

    start_angle = math.atan2(sv - cv, su - cu)
    end_angle = math.atan2(ev - cv, eu - cu)
    full_circle = _near(su, eu) and _near(sv, ev)
    candidate_angles = [start_angle, end_angle]
    if full_circle:
        candidate_angles = [0.0, 0.5 * math.pi, math.pi, 1.5 * math.pi, start_angle]
    else:
        for angle in (0.0, 0.5 * math.pi, math.pi, 1.5 * math.pi):
            if _angle_on_sweep(angle, start_angle, end_angle, clockwise):
                candidate_angles.append(angle)

    points: list[dict] = []
    for angle in _unique_angles(candidate_angles):
        point = dict(start)
        point[u_axis] = cu + radius * math.cos(angle)
        point[v_axis] = cv + radius * math.sin(angle)
        point[w_axis] = float(start[w_axis])
        points.append(point)
    points.append(dict(target))

    arc_len_2d = abs(sweep_delta) * radius
    dz = float(target[w_axis]) - float(start[w_axis])
    arc_length = math.hypot(arc_len_2d, dz)
    return points, arc_length, (u_axis, v_axis, w_axis)


def _arc_center_from_radius(
    su: float,
    sv: float,
    eu: float,
    ev: float,
    radius_value: float,
    *,
    clockwise: bool,
) -> Optional[tuple[float, float, float]]:
    radius = abs(radius_value)
    dx = eu - su
    dy = ev - sv
    chord = math.hypot(dx, dy)
    if chord <= _EPS or chord > (2.0 * radius + 1e-6):
        return None
    mx = (su + eu) * 0.5
    my = (sv + ev) * 0.5
    h_sq = max(radius * radius - (chord * chord) * 0.25, 0.0)
    h = math.sqrt(h_sq)
    ux = -dy / chord
    uy = dx / chord
    centers = [
        (mx + ux * h, my + uy * h),
        (mx - ux * h, my - uy * h),
    ]

    deltas = []
    for center in centers:
        delta = _arc_sweep_delta(center, su, sv, eu, ev, clockwise)
        deltas.append((center, delta))
    chosen_center, chosen_delta = (min(deltas, key=lambda item: item[1]) if radius_value >= 0 else max(deltas, key=lambda item: item[1]))
    return chosen_center[0], chosen_center[1], chosen_delta


def _arc_sweep_delta(center: tuple[float, float], su: float, sv: float, eu: float, ev: float, clockwise: bool) -> float:
    cu, cv = center
    start_angle = math.atan2(sv - cv, su - cu)
    end_angle = math.atan2(ev - cv, eu - cu)
    if clockwise:
        delta = (start_angle - end_angle) % (2.0 * math.pi)
    else:
        delta = (end_angle - start_angle) % (2.0 * math.pi)
    return 2.0 * math.pi if delta <= _EPS else delta


def _angle_on_sweep(angle: float, start_angle: float, end_angle: float, clockwise: bool) -> bool:
    if clockwise:
        total = (start_angle - end_angle) % (2.0 * math.pi)
        progress = (start_angle - angle) % (2.0 * math.pi)
    else:
        total = (end_angle - start_angle) % (2.0 * math.pi)
        progress = (angle - start_angle) % (2.0 * math.pi)
    return progress <= (total + 1e-8)


def _plane_axes(plane: str) -> tuple[str, str, str, str, str]:
    if plane == "G18":
        return "x", "z", "y", "i", "k"
    if plane == "G19":
        return "y", "z", "x", "j", "k"
    return "x", "y", "z", "i", "j"


def _decode_homing_directions(mask: int) -> dict:
    return {
        "x": "positive" if (mask & 0b001) else "negative",
        "y": "positive" if (mask & 0b010) else "negative",
        "z": "positive" if (mask & 0b100) else "negative",
    }


def _profile_travel_value(profile: Mapping[str, Any], axis: str, setting_key: str) -> Optional[float]:
    axis_u = axis.upper()
    limits = profile.get("machine_limits")
    if isinstance(limits, Mapping):
        item = limits.get(axis) or limits.get(axis_u)
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            return abs(float(item[0]) - float(item[1]))

    work_env = profile.get("work_envelope_mm")
    if isinstance(work_env, Mapping):
        value = _to_float(work_env.get(axis) or work_env.get(axis_u))
        if value is not None:
            return abs(value)

    for key in (setting_key, setting_key.lstrip("$"), f"{axis}_travel", f"{axis}_max_travel"):
        value = _to_float(profile.get(key))
        if value is not None:
            return abs(value)

    for container_key in ("settings", "grbl", "grbl_settings"):
        container = profile.get(container_key)
        if isinstance(container, Mapping):
            value = _to_float(container.get(setting_key) or container.get(setting_key.lstrip("$")))
            if value is not None:
                return abs(value)
    return None


def _profile_feed_value(profile: Mapping[str, Any], axis: str, setting_key: str) -> Optional[float]:
    axis_u = axis.upper()
    feeds = profile.get("max_feeds_mm_min")
    if isinstance(feeds, Mapping):
        value = _to_float(feeds.get(axis) or feeds.get(axis_u))
        if value is not None:
            return value
    for key in (setting_key, setting_key.lstrip("$"), f"{axis}_max_feed"):
        value = _to_float(profile.get(key))
        if value is not None:
            return value
    for container_key in ("settings", "grbl", "grbl_settings"):
        container = profile.get(container_key)
        if isinstance(container, Mapping):
            value = _to_float(container.get(setting_key) or container.get(setting_key.lstrip("$")))
            if value is not None:
                return value
    return None


def _nested_value(payload: Mapping[str, Any], *path: str) -> Any:
    node: Any = payload
    for key in path:
        if not isinstance(node, Mapping):
            return None
        node = node.get(key)
    return node


def _nested_number(payload: Mapping[str, Any], *path: str) -> Optional[float]:
    return _to_float(_nested_value(payload, *path))


def _first_number(*values: Any) -> float:
    for value in values:
        parsed = _to_float(value)
        if parsed is not None:
            return parsed
    return 0.0


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _work_to_machine(work_pos: Mapping[str, float], wco: Mapping[str, float]) -> dict:
    return {
        "x": float(work_pos["x"]) + float(wco["x"]),
        "y": float(work_pos["y"]) + float(wco["y"]),
        "z": float(work_pos["z"]) + float(wco["z"]),
    }


def _bbox_from_machine_point(machine_pos: Mapping[str, float]) -> dict:
    return {
        "x": [float(machine_pos["x"]), float(machine_pos["x"])],
        "y": [float(machine_pos["y"]), float(machine_pos["y"])],
        "z": [float(machine_pos["z"]), float(machine_pos["z"])],
    }


def _check_machine_limits(
    *,
    machine_target: Mapping[str, float],
    limits: Mapping[str, Sequence[float]],
    line_no: int,
    raw_line: str,
    errors: list[dict],
) -> None:
    for axis in ("x", "y", "z"):
        axis_limits = limits.get(axis)
        if not axis_limits or len(axis_limits) < 2:
            continue
        min_v = float(axis_limits[0])
        max_v = float(axis_limits[1])
        value = float(machine_target[axis])
        if value < (min_v - 1e-6) or value > (max_v + 1e-6):
            _append_error(
                errors,
                line=line_no,
                command=raw_line,
                reason=(
                    f"{axis.upper()}={value:.3f} in machine coordinates exceeds limit "
                    f"[{min_v:.3f}, {max_v:.3f}]."
                ),
            )


def _append_error(errors: list[dict], *, line: int, command: str, reason: str) -> None:
    errors.append({"line": int(line), "command": str(command).strip(), "reason": str(reason)})


def _normalize_bbox(bounding_box: Mapping[str, Any]) -> Optional[dict]:
    out: dict = {}
    for axis in ("x", "y", "z"):
        value = bounding_box.get(axis)
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        lo = _to_float(value[0])
        hi = _to_float(value[1])
        if lo is None or hi is None:
            return None
        out[axis] = [min(lo, hi), max(lo, hi)]
    return out


def _extract_corner_mode(desired_workpiece_corner: Optional[Mapping[str, Any]]) -> dict:
    # Default corner for stock setup: Xmin/Ymin at top surface (Zmax).
    mode = {"x": "min", "y": "min", "z": "max"}
    if not isinstance(desired_workpiece_corner, Mapping):
        return mode
    for axis in ("x", "y", "z"):
        raw = str(desired_workpiece_corner.get(f"{axis}_mode", desired_workpiece_corner.get(axis + "_corner", ""))).strip().lower()
        if raw in ("min", "max"):
            mode[axis] = raw
    return mode


def _extract_desired_machine_corner(desired_workpiece_corner: Optional[Mapping[str, Any]]) -> Optional[dict]:
    if not isinstance(desired_workpiece_corner, Mapping):
        return None
    machine = desired_workpiece_corner.get("machine")
    payload = machine if isinstance(machine, Mapping) else desired_workpiece_corner
    out: dict = {}
    for axis in ("x", "y", "z"):
        value = _to_float(payload.get(axis))
        if value is not None:
            out[axis] = value
    return out or None


def _fmt(value: float) -> str:
    text = f"{float(value):.4f}"
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def _update_bbox(bbox: dict, pos: Mapping[str, float]) -> None:
    for axis in ("x", "y", "z"):
        bbox[axis][0] = min(float(bbox[axis][0]), float(pos[axis]))
        bbox[axis][1] = max(float(bbox[axis][1]), float(pos[axis]))


def _distance(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    return math.sqrt(
        (float(a["x"]) - float(b["x"])) ** 2
        + (float(a["y"]) - float(b["y"])) ** 2
        + (float(a["z"]) - float(b["z"])) ** 2
    )


def _has_position_change(start: Mapping[str, float], target: Mapping[str, float]) -> bool:
    return any(not _near(start[axis], target[axis]) for axis in ("x", "y", "z"))


def _near(a: float, b: float, eps: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) <= eps


def _unique_angles(angles: Iterable[float]) -> list[float]:
    unique: list[float] = []
    for angle in angles:
        if any(abs(float(angle) - seen) <= 1e-8 for seen in unique):
            continue
        unique.append(float(angle))
    return unique
