"""Small GRBL-oriented CAM templates for common manual-start jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence, Tuple


Point2D = Tuple[float, float]


@dataclass
class TemplateSpec:
    width: float
    height: float
    depth: float
    tool_diameter: float
    step_down: float
    step_over: float
    feed_rate: float
    plunge_rate: float
    safe_z: float
    start_z: float = 0.0
    origin: str = "center"


@dataclass
class GcodeProgram:
    lines: list[str]
    template: str
    spec: TemplateSpec
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def gcode(self) -> str:
        return self.text

    def __str__(self) -> str:
        return self.text


def rectangle_pocket(spec: Optional[TemplateSpec] = None, **kwargs) -> GcodeProgram:
    """Generate a simple rectangular pocket program in local work coordinates.

    The emitted program assumes the operator already established the desired
    work coordinate zero. It intentionally avoids homing, probing, work-offset,
    or coordinate-system mutation commands.
    """
    spec = _coerce_spec(spec, kwargs)
    _validate_spec(spec)

    paths = _raster_paths(spec)
    depths = _depth_levels(spec.start_z, spec.depth, spec.step_down)
    first_x, first_y = paths[0]

    lines = [
        "; RouterKing rectangle pocket template",
        f"; size: {_fmt(spec.width)} x {_fmt(spec.height)} x {_fmt(spec.depth)} mm",
        f"; tool: {_fmt(spec.tool_diameter)} mm",
        "G21",
        "G90",
        "G17",
        f"G0 Z{_fmt(spec.safe_z)}",
    ]

    for depth in depths:
        lines.append(f"; depth {_fmt(depth)}")
        lines.append(f"G0 X{_fmt(first_x)} Y{_fmt(first_y)}")
        lines.append(f"G1 Z{_fmt(depth)} F{_fmt(spec.plunge_rate)}")
        _append_raster_moves(lines, paths, spec.feed_rate)
        lines.append(f"G0 Z{_fmt(spec.safe_z)}")

    lines.append(f"G0 X{_fmt(0.0)} Y{_fmt(0.0)}")
    lines.append("M2")
    return GcodeProgram(lines=lines, template="rectangle_pocket", spec=spec)


def square_pocket(spec: Optional[TemplateSpec] = None, **kwargs) -> GcodeProgram:
    """Generate a square pocket program.

    Pass either a ``TemplateSpec`` with equal width and height, or keyword
    arguments. For keyword usage, ``size`` may be provided instead of width and
    height.
    """
    if spec is None and "size" in kwargs:
        size = kwargs.pop("size")
        kwargs.setdefault("width", size)
        kwargs.setdefault("height", size)
    elif spec is None and "width" in kwargs and "height" not in kwargs:
        kwargs["height"] = kwargs["width"]
    elif spec is None and "height" in kwargs and "width" not in kwargs:
        kwargs["width"] = kwargs["height"]

    spec = _coerce_spec(spec, kwargs)
    if abs(spec.width - spec.height) > 1e-9:
        raise ValueError("square_pocket requires width and height to be equal.")

    _validate_spec(spec)
    program = rectangle_pocket(spec)
    program.template = "square_pocket"
    program.lines[0] = "; RouterKing square pocket template"
    return program


def _coerce_spec(spec: Optional[TemplateSpec], kwargs: dict) -> TemplateSpec:
    if spec is not None and kwargs:
        raise TypeError("Pass either a TemplateSpec or keyword arguments, not both.")
    if spec is not None:
        if not isinstance(spec, TemplateSpec):
            raise TypeError("spec must be a TemplateSpec instance.")
        return spec
    return TemplateSpec(**kwargs)


def _validate_spec(spec: TemplateSpec) -> None:
    positive_fields = (
        "width",
        "height",
        "depth",
        "tool_diameter",
        "step_down",
        "step_over",
        "feed_rate",
        "plunge_rate",
    )
    for name in positive_fields:
        value = getattr(spec, name)
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero.")

    if spec.safe_z <= spec.start_z:
        raise ValueError("safe_z must be greater than start_z.")

    if spec.tool_diameter > spec.width or spec.tool_diameter > spec.height:
        raise ValueError("tool_diameter must fit inside width and height.")

    if spec.step_over > spec.tool_diameter:
        raise ValueError("step_over must not exceed tool_diameter.")

    if _normalize_origin(spec.origin) not in {"center", "lower_left"}:
        raise ValueError("origin must be 'center' or 'lower_left'.")


def _depth_levels(start_z: float, depth: float, step_down: float) -> list[float]:
    target_z = start_z - depth
    levels = []
    current = start_z
    while current > target_z:
        current = max(target_z, current - step_down)
        levels.append(current)
    return levels


def _raster_paths(spec: TemplateSpec) -> list[Point2D]:
    radius = spec.tool_diameter / 2.0
    x_min, x_max, y_min, y_max = _bounds(spec, radius)
    y_values = _axis_values(y_min, y_max, spec.step_over)

    points = []
    for index, y_val in enumerate(y_values):
        if index % 2 == 0:
            points.append((x_min, y_val))
            points.append((x_max, y_val))
        else:
            points.append((x_max, y_val))
            points.append((x_min, y_val))
    return _dedupe_points(points)


def _bounds(spec: TemplateSpec, radius: float) -> tuple[float, float, float, float]:
    origin = _normalize_origin(spec.origin)
    if origin == "center":
        x_min = -spec.width / 2.0 + radius
        x_max = spec.width / 2.0 - radius
        y_min = -spec.height / 2.0 + radius
        y_max = spec.height / 2.0 - radius
        return x_min, x_max, y_min, y_max

    x_min = radius
    x_max = spec.width - radius
    y_min = radius
    y_max = spec.height - radius
    return x_min, x_max, y_min, y_max


def _axis_values(start: float, stop: float, step: float) -> list[float]:
    values = [start]
    current = start
    while current + step < stop:
        current += step
        values.append(current)
    if values[-1] != stop:
        values.append(stop)
    return values


def _append_raster_moves(lines: list[str], paths: Sequence[Point2D], feed_rate: float) -> None:
    feed = f" F{_fmt(feed_rate)}"
    for x_val, y_val in paths[1:]:
        lines.append(f"G1 X{_fmt(x_val)} Y{_fmt(y_val)}{feed}")


def _dedupe_points(points: Iterable[Point2D]) -> list[Point2D]:
    result = []
    for point in points:
        if not result or result[-1] != point:
            result.append(point)
    return result


def _normalize_origin(origin: str) -> str:
    value = str(origin or "").strip().lower().replace("-", "_")
    aliases = {
        "centre": "center",
        "middle": "center",
        "lowerleft": "lower_left",
        "bottom_left": "lower_left",
        "corner": "lower_left",
    }
    return aliases.get(value, value)


def _fmt(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")
