"""Smart G-code post-processing for GRBL safety compatibility."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from .validator import (
    load_machine_profile,
    parse_gcode_words,
    resolve_capabilities,
    resolve_machine_limits,
    resolve_max_feeds,
    resolve_work_offset,
    strip_gcode_comments,
)


def postprocess_gcode(
    gcode: str | Sequence[str],
    *,
    machine_profile: Optional[Mapping[str, Any]] = None,
    machine_profile_path: Optional[str] = None,
    grbl_settings: Optional[Mapping[str, Any]] = None,
    status: Optional[Mapping[str, Any]] = None,
    feed_rate: Optional[float] = None,
    plunge_rate: Optional[float] = None,  # reserved for future per-axis tuning
) -> dict:
    del plunge_rate

    raw_lines = gcode.splitlines() if isinstance(gcode, str) else [str(line) for line in gcode]
    profile = dict(machine_profile or {})
    if not profile:
        profile, _ = load_machine_profile(machine_profile_path)
    settings = dict(grbl_settings or {})
    if not settings and isinstance(profile.get("settings"), Mapping):
        settings = dict(profile.get("settings") or {})
    status_map = dict(status or {})
    if not status_map and isinstance(profile.get("status"), Mapping):
        status_map = dict(profile.get("status") or {})

    capabilities = resolve_capabilities(profile, settings)
    max_feeds, _ = resolve_max_feeds(profile, settings)
    limits, _ = resolve_machine_limits(profile, settings)
    safe_z = _compute_safe_z(profile, settings, status_map)
    default_feed = _resolve_default_feed(feed_rate, profile, max_feeds)
    default_feed = max(default_feed, 1.0)

    state = {
        "distance_absolute": True,
        "unit_scale": 1.0,  # mm
        "motion": 0,
    }
    removed_commands: list[str] = []
    injected_feed_count = 0
    replaced_f0_count = 0
    clamped_z_count = 0
    body_lines: list[str] = []

    for raw_line in raw_lines:
        cleaned = strip_gcode_comments(raw_line)
        if not cleaned:
            continue
        words = parse_gcode_words(cleaned)
        if not words:
            continue

        machine_coords_block = False
        line_motion = None
        line_absolute = state["distance_absolute"]
        line_scale = state["unit_scale"]

        filtered: list[tuple[str, float]] = []
        for letter, number in words:
            if letter == "G":
                if abs(number - 90.0) < 1e-9:
                    line_absolute = True
                elif abs(number - 91.0) < 1e-9:
                    line_absolute = False
                elif abs(number - 20.0) < 1e-9:
                    line_scale = 25.4
                elif abs(number - 21.0) < 1e-9:
                    line_scale = 1.0
                elif abs(number - 53.0) < 1e-9:
                    machine_coords_block = True
                elif abs(number - 0.0) < 1e-9:
                    line_motion = 0
                elif abs(number - 1.0) < 1e-9:
                    line_motion = 1
                elif abs(number - 2.0) < 1e-9:
                    line_motion = 2
                elif abs(number - 3.0) < 1e-9:
                    line_motion = 3
                filtered.append((letter, number))
                continue
            if letter == "M":
                code = int(round(number))
                if code in (3, 4, 5) and not capabilities.get("spindle_supported", False):
                    removed_commands.append(f"M{code}")
                    continue
                if code in (7, 8, 9) and not capabilities.get("coolant_supported", False):
                    removed_commands.append(f"M{code}")
                    continue
            filtered.append((letter, number))

        if not filtered:
            continue

        # Apply modal changes from this line.
        state["distance_absolute"] = line_absolute
        state["unit_scale"] = line_scale
        if line_motion is not None:
            state["motion"] = line_motion
        motion = state["motion"]

        # Replace F0 and inject missing F on feed/arc lines.
        has_feed = any(letter == "F" for letter, _ in filtered)
        rewritten: list[tuple[str, float]] = []
        for letter, number in filtered:
            if letter == "F" and number <= 0.0:
                rewritten.append(("F", default_feed / state["unit_scale"]))
                replaced_f0_count += 1
            else:
                rewritten.append((letter, number))
        filtered = rewritten

        if motion in (1, 2, 3):
            if not has_feed:
                filtered.append(("F", default_feed / state["unit_scale"]))
                injected_feed_count += 1
            else:
                # Feed exists, but it might still be > machine max after user edit.
                filtered = _clamp_feed_to_machine(filtered, state["unit_scale"], max_feeds, motion)

        # Clamp absolute work Z moves to safe clearance for non-machine-coordinate moves.
        if motion in (0, 1) and line_absolute and not machine_coords_block:
            z_index = next((idx for idx, (letter, _) in enumerate(filtered) if letter == "Z"), None)
            if z_index is not None:
                z_value_mm = filtered[z_index][1] * state["unit_scale"]
                if z_value_mm > safe_z:
                    filtered[z_index] = ("Z", safe_z / state["unit_scale"])
                    clamped_z_count += 1

        body_lines.append(_format_words(filtered))

    header = ["G90 G21 G17", f"G0 Z{_fmt(safe_z)}"]
    processed_lines = header + body_lines
    if not _ends_with_program_stop(processed_lines):
        processed_lines.append("M2")
    processed_gcode = "\n".join(line for line in processed_lines if line.strip())
    if processed_gcode and not processed_gcode.endswith("\n"):
        processed_gcode += "\n"

    return {
        "gcode": processed_gcode,
        "safe_z": safe_z,
        "default_feed": default_feed,
        "line_count": len(processed_lines),
        "removed_commands": removed_commands,
        "injected_feed_count": injected_feed_count,
        "replaced_f0_count": replaced_f0_count,
        "clamped_z_count": clamped_z_count,
        "limits_machine": limits,
    }


def _compute_safe_z(profile: Mapping[str, Any], settings: Mapping[str, Any], status: Mapping[str, Any]) -> float:
    pull_off = (
        _to_float(settings.get("$27"))
        or _to_float(((profile.get("homing") or {}).get("pull_off_mm") if isinstance(profile.get("homing"), Mapping) else None))
        or 3.0
    )
    safe_z = -(pull_off + 2.0)
    try:
        wco, _ = resolve_work_offset(status, profile)
        mpos_z = safe_z + float(wco["z"])
        if mpos_z > -0.1:
            safe_z = (-0.1) - float(wco["z"])
    except Exception:
        pass
    return safe_z


def _resolve_default_feed(
    feed_rate: Optional[float],
    profile: Mapping[str, Any],
    max_feeds: Mapping[str, float],
) -> float:
    if feed_rate is not None and feed_rate > 0:
        return float(feed_rate)

    defaults = profile.get("defaults")
    if isinstance(defaults, Mapping):
        value = _to_float(defaults.get("feed_rate_mm_min"))
        if value and value > 0:
            return value
        value = _to_float(defaults.get("feed_rate"))
        if value and value > 0:
            return value

    x = float(max_feeds.get("x", 0.0))
    y = float(max_feeds.get("y", 0.0))
    if x > 0 and y > 0:
        return min(x, y, 1200.0)
    if x > 0:
        return min(x, 1200.0)
    if y > 0:
        return min(y, 1200.0)
    return 800.0


def _clamp_feed_to_machine(
    words: Sequence[tuple[str, float]],
    unit_scale: float,
    max_feeds: Mapping[str, float],
    motion: int,
) -> list[tuple[str, float]]:
    if motion not in (1, 2, 3):
        return list(words)
    max_xy = min(float(max_feeds.get("x", 1e9)), float(max_feeds.get("y", 1e9)))
    if max_xy <= 0:
        return list(words)
    out: list[tuple[str, float]] = []
    for letter, number in words:
        if letter != "F":
            out.append((letter, number))
            continue
        feed_mm = number * unit_scale
        if feed_mm > max_xy:
            out.append(("F", max_xy / unit_scale))
        else:
            out.append((letter, number))
    return out


def _ends_with_program_stop(lines: Sequence[str]) -> bool:
    for line in reversed(lines):
        text = strip_gcode_comments(line).upper()
        if not text:
            continue
        return "M2" in text or "M30" in text
    return False


def _format_words(words: Sequence[tuple[str, float]]) -> str:
    return " ".join(f"{letter}{_fmt(number)}" for letter, number in words)


def _fmt(value: float) -> str:
    text = f"{float(value):.4f}"
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def _to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None
