"""Standalone G-code preview helpers for RouterKing UI.

The module intentionally has no FreeCAD or Qt import at module load time.
Pure helpers parse 2.5D/3D motion, project it into 2D preview coordinates,
and derive stable colors/bounds. ``render_preview_scene`` is the optional
Qt bridge for a ``QGraphicsScene``.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Iterable, Mapping, Sequence


_WORD_RE = re.compile(r"([A-Za-z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
_PAREN_COMMENT_RE = re.compile(r"\([^)]*\)")
_EPS = 1e-9


@dataclass(frozen=True)
class PreviewPoint:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class PreviewSegment:
    start: PreviewPoint
    end: PreviewPoint
    rapid: bool
    line_no: int
    motion: str

    @property
    def average_z(self) -> float:
        return (self.start.z + self.end.z) / 2.0


@dataclass(frozen=True)
class PreviewBounds:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float


@dataclass(frozen=True)
class PreviewPath:
    segments: tuple[PreviewSegment, ...]
    bounds: PreviewBounds | None


def parse_gcode_preview(gcode: str | Iterable[str], arc_step_radians: float = math.pi / 24.0) -> PreviewPath:
    """Parse G0/G1/G2/G3 moves into 3D preview segments.

    Coordinates are normalized to millimeters. Absolute/relative distance
    modes, inch/mm units, G17/G18/G19 arc planes, IJK/R arcs, and helical arcs
    are handled for preview purposes.
    """
    parser = _PreviewParser(float(arc_step_radians))
    for line_no, raw_line in enumerate(_iter_input_lines(gcode), start=1):
        parser.handle_line(line_no, raw_line)
    return parser.path()


def project_point(point: PreviewPoint, projection: str = "top") -> tuple[float, float]:
    """Project a 3D point into scene coordinates.

    Qt scenes have a downward-positive Y axis, so top/side views invert the
    vertical scene coordinate to keep positive model Y/Z visually upward.
    """
    projection_key = str(projection or "top").lower()
    if projection_key == "top":
        return (point.x, -point.y)
    if projection_key == "side":
        return (point.x, -point.z)
    if projection_key == "front":
        return (point.y, -point.z)
    if projection_key == "iso":
        return (point.x - point.y, (point.x + point.y) * 0.5 - point.z)
    raise ValueError(f"Unsupported projection: {projection!r}")


def project_segment(segment: PreviewSegment, projection: str = "top") -> tuple[float, float, float, float]:
    x0, y0 = project_point(segment.start, projection)
    x1, y1 = project_point(segment.end, projection)
    return (x0, y0, x1, y1)


def projected_bounds(path: PreviewPath | Sequence[PreviewSegment], projection: str = "top") -> tuple[float, float, float, float] | None:
    """Return projected 2D bounds as ``(min_x, min_y, max_x, max_y)``."""
    segments = path.segments if isinstance(path, PreviewPath) else tuple(path)
    min_x = min_y = max_x = max_y = None
    for segment in segments:
        for point in (segment.start, segment.end):
            x, y = project_point(point, projection)
            if min_x is None:
                min_x = max_x = x
                min_y = max_y = y
            else:
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    if min_x is None:
        return None
    return (min_x, min_y, max_x, max_y)


def z_color(
    z: float,
    bounds: PreviewBounds | None,
    *,
    low: tuple[int, int, int] = (0, 90, 220),
    high: tuple[int, int, int] = (235, 130, 35),
) -> tuple[int, int, int]:
    """Map Z depth to an RGB color, low Z blue and high Z orange."""
    if bounds is None or math.isclose(bounds.min_z, bounds.max_z, abs_tol=_EPS):
        ratio = 0.5
    else:
        ratio = (float(z) - bounds.min_z) / (bounds.max_z - bounds.min_z)
        ratio = max(0.0, min(1.0, ratio))
    return tuple(int(round(lo + (hi - lo) * ratio)) for lo, hi in zip(low, high))


def segment_color(segment: PreviewSegment, bounds: PreviewBounds | None) -> tuple[int, int, int]:
    if segment.rapid:
        return (150, 150, 150)
    return z_color(segment.average_z, bounds)


def preview_items(path: PreviewPath, projection: str = "top") -> list[dict]:
    """Return serializable line/color items suitable for tests or custom UI."""
    items = []
    for segment in path.segments:
        items.append(
            {
                "line": project_segment(segment, projection),
                "color": segment_color(segment, path.bounds),
                "rapid": segment.rapid,
                "line_no": segment.line_no,
                "motion": segment.motion,
            }
        )
    return items


def render_preview_scene(scene, path: PreviewPath, projection: str = "top", *, clear: bool = True) -> tuple[float, float, float, float] | None:
    """Render a parsed preview path into a ``QGraphicsScene``.

    The Qt import is lazy so this module remains importable in headless tests.
    The returned bounds are projected pure-helper bounds; callers can use them
    to fit a view after rendering.
    """
    if clear:
        scene.clear()
    if not path.segments:
        return None

    qt_gui = _import_qt_gui()
    for segment in path.segments:
        color = segment_color(segment, path.bounds)
        pen = qt_gui.QPen(qt_gui.QColor(*color), 0)
        scene.addLine(*project_segment(segment, projection), pen)
    return projected_bounds(path, projection)


class _PreviewParser:
    def __init__(self, arc_step_radians: float):
        self._arc_step = max(abs(arc_step_radians), math.pi / 180.0)
        self._segments: list[PreviewSegment] = []
        self._bounds: _BoundsBuilder | None = None
        self._absolute = True
        self._arc_center_absolute = False
        self._unit_scale = 1.0
        self._motion = 0
        self._plane = "G17"
        self._position = PreviewPoint(0.0, 0.0, 0.0)
        self._include_point(self._position)

    def path(self) -> PreviewPath:
        bounds = self._bounds.finish() if self._bounds is not None else None
        return PreviewPath(segments=tuple(self._segments), bounds=bounds)

    def handle_line(self, line_no: int, raw_line: str) -> None:
        cleaned = strip_comments(raw_line)
        if not cleaned:
            return
        words = _parse_words(cleaned)
        if not words:
            return

        line_absolute = self._absolute
        line_unit_scale = self._unit_scale
        line_motion = None
        line_plane = self._plane
        axis_words: dict[str, float] = {}
        center_words: dict[str, float] = {}
        radius = None

        for letter, value in words:
            if letter == "G":
                rounded = round(value)
                if _near(value, 0.0):
                    line_motion = 0
                elif _near(value, 1.0):
                    line_motion = 1
                elif _near(value, 2.0):
                    line_motion = 2
                elif _near(value, 3.0):
                    line_motion = 3
                elif _near(value, 17.0):
                    line_plane = "G17"
                elif _near(value, 18.0):
                    line_plane = "G18"
                elif _near(value, 19.0):
                    line_plane = "G19"
                elif _near(value, 20.0):
                    line_unit_scale = 25.4
                elif _near(value, 21.0):
                    line_unit_scale = 1.0
                elif _near(value, 90.0):
                    line_absolute = True
                elif _near(value, 91.0):
                    line_absolute = False
                elif _near(value, 90.1):
                    self._arc_center_absolute = True
                elif _near(value, 91.1):
                    self._arc_center_absolute = False
                elif rounded in (17, 18, 19):
                    line_plane = f"G{rounded}"

        for letter, value in words:
            scaled = value * line_unit_scale
            if letter in ("X", "Y", "Z"):
                axis_words[letter.lower()] = scaled
            elif letter in ("I", "J", "K"):
                center_words[letter.lower()] = scaled
            elif letter == "R":
                radius = scaled

        active_motion = line_motion if line_motion is not None else self._motion
        target = self._target(axis_words, line_absolute)
        self._plane = line_plane

        if active_motion in (0, 1):
            self._add_line(line_no, target, rapid=active_motion == 0, motion=f"G{active_motion}")
        elif active_motion in (2, 3):
            self._add_arc(line_no, target, center_words, radius, cw=active_motion == 2)

        self._position = target
        self._absolute = line_absolute
        self._unit_scale = line_unit_scale
        if line_motion is not None:
            self._motion = line_motion

    def _target(self, axis_words: Mapping[str, float], absolute: bool) -> PreviewPoint:
        current = {"x": self._position.x, "y": self._position.y, "z": self._position.z}
        for axis, value in axis_words.items():
            current[axis] = value if absolute else current[axis] + value
        return PreviewPoint(current["x"], current["y"], current["z"])

    def _add_line(self, line_no: int, target: PreviewPoint, *, rapid: bool, motion: str) -> None:
        if _same_point(self._position, target):
            self._include_point(target)
            return
        self._append_segment(PreviewSegment(self._position, target, rapid, line_no, motion))

    def _add_arc(
        self,
        line_no: int,
        target: PreviewPoint,
        center_words: Mapping[str, float],
        radius: float | None,
        *,
        cw: bool,
    ) -> None:
        plane = _plane_axes(self._plane)
        start_a = getattr(self._position, plane.axis_a)
        start_b = getattr(self._position, plane.axis_b)
        end_a = getattr(target, plane.axis_a)
        end_b = getattr(target, plane.axis_b)
        start_linear = getattr(self._position, plane.linear_axis)
        end_linear = getattr(target, plane.linear_axis)

        if _near(start_a, end_a) and _near(start_b, end_b):
            self._add_line(line_no, target, rapid=False, motion="G2" if cw else "G3")
            return

        center = self._arc_center(
            start_a,
            start_b,
            end_a,
            end_b,
            center_words,
            radius,
            plane,
            cw,
        )
        if center is None:
            self._add_line(line_no, target, rapid=False, motion="G2" if cw else "G3")
            return

        center_a, center_b, delta = center
        arc_radius = math.hypot(start_a - center_a, start_b - center_b)
        if arc_radius <= _EPS:
            return

        steps = max(8, int(math.ceil(abs(delta) / self._arc_step)))
        previous = self._position
        start_angle = math.atan2(start_b - center_b, start_a - center_a)
        for step in range(1, steps + 1):
            ratio = step / steps
            angle = start_angle + delta * ratio
            point_values = {
                "x": self._position.x,
                "y": self._position.y,
                "z": self._position.z,
            }
            point_values[plane.axis_a] = center_a + math.cos(angle) * arc_radius
            point_values[plane.axis_b] = center_b + math.sin(angle) * arc_radius
            point_values[plane.linear_axis] = start_linear + (end_linear - start_linear) * ratio
            current = PreviewPoint(point_values["x"], point_values["y"], point_values["z"])
            self._append_segment(PreviewSegment(previous, current, False, line_no, "G2" if cw else "G3"))
            previous = current

    def _arc_center(
        self,
        start_a: float,
        start_b: float,
        end_a: float,
        end_b: float,
        center_words: Mapping[str, float],
        radius: float | None,
        plane: "_Plane",
        cw: bool,
    ) -> tuple[float, float, float] | None:
        if plane.center_a in center_words or plane.center_b in center_words:
            center_a_value = center_words.get(plane.center_a, 0.0)
            center_b_value = center_words.get(plane.center_b, 0.0)
            if self._arc_center_absolute:
                center_a, center_b = center_a_value, center_b_value
            else:
                center_a = start_a + center_a_value
                center_b = start_b + center_b_value
            delta = _arc_delta(start_a, start_b, end_a, end_b, center_a, center_b, cw)
            return (center_a, center_b, delta) if delta is not None else None
        if radius is not None:
            return _center_from_radius(start_a, start_b, end_a, end_b, radius, cw)
        return None

    def _append_segment(self, segment: PreviewSegment) -> None:
        self._segments.append(segment)
        self._include_point(segment.start)
        self._include_point(segment.end)

    def _include_point(self, point: PreviewPoint) -> None:
        if self._bounds is None:
            self._bounds = _BoundsBuilder(point)
        else:
            self._bounds.include(point)


@dataclass(frozen=True)
class _Plane:
    axis_a: str
    axis_b: str
    linear_axis: str
    center_a: str
    center_b: str


def _plane_axes(plane: str) -> _Plane:
    if plane == "G18":
        return _Plane("x", "z", "y", "i", "k")
    if plane == "G19":
        return _Plane("y", "z", "x", "j", "k")
    return _Plane("x", "y", "z", "i", "j")


class _BoundsBuilder:
    def __init__(self, point: PreviewPoint):
        self.min_x = self.max_x = point.x
        self.min_y = self.max_y = point.y
        self.min_z = self.max_z = point.z

    def include(self, point: PreviewPoint) -> None:
        self.min_x = min(self.min_x, point.x)
        self.max_x = max(self.max_x, point.x)
        self.min_y = min(self.min_y, point.y)
        self.max_y = max(self.max_y, point.y)
        self.min_z = min(self.min_z, point.z)
        self.max_z = max(self.max_z, point.z)

    def finish(self) -> PreviewBounds:
        return PreviewBounds(self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z)


def strip_comments(line: str) -> str:
    stripped = str(line or "")
    stripped = stripped.split(";", 1)[0]
    previous = None
    while previous != stripped:
        previous = stripped
        stripped = _PAREN_COMMENT_RE.sub("", stripped)
    return stripped.strip()


def _iter_input_lines(gcode: str | Iterable[str]) -> Iterable[str]:
    if isinstance(gcode, str):
        yield from gcode.splitlines()
        return
    for line in gcode:
        yield str(line)


def _parse_words(line: str) -> list[tuple[str, float]]:
    words = []
    for match in _WORD_RE.finditer(line):
        try:
            words.append((match.group(1).upper(), float(match.group(2))))
        except ValueError:
            continue
    return words


def _center_from_radius(
    start_a: float,
    start_b: float,
    end_a: float,
    end_b: float,
    r_value: float,
    cw: bool,
) -> tuple[float, float, float] | None:
    radius = abs(r_value)
    da = end_a - start_a
    db = end_b - start_b
    chord = math.hypot(da, db)
    if chord <= _EPS or chord > 2.0 * radius + _EPS:
        return None
    mid_a = (start_a + end_a) / 2.0
    mid_b = (start_b + end_b) / 2.0
    height = math.sqrt(max(radius * radius - (chord / 2.0) ** 2, 0.0))
    unit_a = -db / chord
    unit_b = da / chord
    candidates = (
        (mid_a + unit_a * height, mid_b + unit_b * height),
        (mid_a - unit_a * height, mid_b - unit_b * height),
    )
    use_large_arc = r_value < 0.0
    best = None
    for center_a, center_b in candidates:
        delta = _arc_delta(start_a, start_b, end_a, end_b, center_a, center_b, cw)
        if delta is None:
            continue
        candidate = (center_a, center_b, delta)
        if best is None:
            best = candidate
        elif use_large_arc and abs(delta) > abs(best[2]):
            best = candidate
        elif not use_large_arc and abs(delta) < abs(best[2]):
            best = candidate
    return best


def _arc_delta(
    start_a: float,
    start_b: float,
    end_a: float,
    end_b: float,
    center_a: float,
    center_b: float,
    cw: bool,
) -> float | None:
    start_angle = math.atan2(start_b - center_b, start_a - center_a)
    end_angle = math.atan2(end_b - center_b, end_a - center_a)
    delta = end_angle - start_angle
    if cw:
        if delta >= 0.0:
            delta -= math.tau
    else:
        if delta <= 0.0:
            delta += math.tau
    return delta


def _same_point(left: PreviewPoint, right: PreviewPoint) -> bool:
    return _near(left.x, right.x) and _near(left.y, right.y) and _near(left.z, right.z)


def _near(left: float, right: float) -> bool:
    return math.isclose(left, right, abs_tol=_EPS)


def _import_qt_gui():
    try:
        from PySide2 import QtGui

        return QtGui
    except ImportError:  # pragma: no cover - FreeCAD fallback
        from PySide import QtGui

        return QtGui
