"""G-code transformation helpers."""

from __future__ import annotations

import math
import re
from typing import Iterable

_WORD_RE = re.compile(r"([A-Za-z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
_PAREN_COMMENT_RE = re.compile(r"\([^)]*\)")
_EPS = 1e-9


def prepare_air_run_lines(gcode, air_z=5.0):
    """Return normalized G-code lines for an air run.

    The transformation is purely textual. It strips comments, removes spindle
    and laser start/stop commands (M3/M4/M5), and clamps Z targets so the
    simulated work-coordinate Z position never drops below ``air_z``.
    """
    transformer = _AirRunTransformer(float(air_z))
    return [
        line
        for line in (transformer.transform_line(raw) for raw in _iter_input_lines(gcode))
        if line
    ]


def prepare_air_run_gcode(gcode, air_z=5.0):
    """Return normalized air-run G-code as a newline-delimited string."""
    return "\n".join(prepare_air_run_lines(gcode, air_z=air_z))


class _AirRunTransformer:
    def __init__(self, air_z):
        self.air_z = air_z
        self.absolute = True
        self.unit_scale = 1.0
        self.motion = 0
        self.z = air_z

    def transform_line(self, raw_line):
        cleaned = _strip_comments(raw_line)
        if not cleaned:
            return ""

        words = _parse_word_tokens(cleaned)
        if not words:
            return _normalize_space(cleaned)

        line_absolute = self.absolute
        line_unit_scale = self.unit_scale
        line_motion = None
        for word in words:
            if word.letter != "G":
                continue
            if _near(word.value, 0.0):
                line_motion = 0
            elif _near(word.value, 1.0):
                line_motion = 1
            elif _near(word.value, 2.0):
                line_motion = 2
            elif _near(word.value, 3.0):
                line_motion = 3
            elif _near(word.value, 20.0):
                line_unit_scale = 25.4
            elif _near(word.value, 21.0):
                line_unit_scale = 1.0
            elif _near(word.value, 90.0):
                line_absolute = True
            elif _near(word.value, 91.0):
                line_absolute = False

        active_motion = line_motion if line_motion is not None else self.motion
        has_spindle_command = any(
            word.letter == "M" and _is_spindle_command(word.value) for word in words
        )
        output = []

        for word in words:
            if word.letter == "M" and _is_spindle_command(word.value):
                continue
            if has_spindle_command and word.letter == "S":
                continue
            if word.letter == "Z" and active_motion in (0, 1, 2, 3):
                z_value = self._safe_z_value(word.value, line_absolute, line_unit_scale)
                output.append("Z" + _format_number(z_value))
                continue
            output.append(word.text)

        self.absolute = line_absolute
        self.unit_scale = line_unit_scale
        if line_motion is not None:
            self.motion = line_motion

        if not output:
            return ""
        if all(part.startswith("S") for part in output):
            return ""
        return " ".join(output)

    def _safe_z_value(self, value, absolute, unit_scale):
        value_mm = value * unit_scale
        target = value_mm if absolute else self.z + value_mm
        safe_target = max(target, self.air_z)
        if abs(safe_target) <= _EPS:
            safe_target = 0.0
        if absolute:
            self.z = safe_target
            return safe_target / unit_scale
        safe_delta = safe_target - self.z
        self.z = safe_target
        return safe_delta / unit_scale


class _Word:
    def __init__(self, letter, number_text):
        self.letter = letter.upper()
        self.number_text = number_text
        self.value = float(number_text)
        self.text = self.letter + number_text


def _iter_input_lines(gcode):
    if isinstance(gcode, str):
        yield from gcode.splitlines()
        return
    if isinstance(gcode, Iterable):
        for line in gcode:
            yield str(line)
        return
    yield str(gcode)


def _strip_comments(line):
    stripped = str(line or "")
    stripped = stripped.split(";", 1)[0]
    previous = None
    while previous != stripped:
        previous = stripped
        stripped = _PAREN_COMMENT_RE.sub("", stripped)
    return stripped.strip()


def _parse_word_tokens(line):
    return [_Word(match.group(1), match.group(2)) for match in _WORD_RE.finditer(line)]


def _is_spindle_command(value):
    nearest = round(value)
    return nearest in (3, 4, 5) and _near(value, float(nearest))


def _near(left, right):
    return math.isclose(left, right, abs_tol=_EPS)


def _normalize_space(line):
    return " ".join(str(line or "").split())


def _format_number(value):
    if abs(value) <= _EPS:
        value = 0.0
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"
