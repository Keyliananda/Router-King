"""Small GRBL-oriented CAM templates for common manual-start jobs."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Iterator, Mapping, Optional, Sequence, Tuple

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
    name: Optional[str] = None
    start_x: float = 0.0
    start_y: float = 0.0
    swap_xy: bool = False
    cut_start_x: Optional[float] = None
    cut_start_y: Optional[float] = None
    source_document: Optional[str] = None
    source_object: Optional[str] = None
    source_feature: Optional[str] = None


_RECTANGLE_POCKET_PRESET_SPECS = {
    "tee_tablett": TemplateSpec(
        name="Tee-Tablett Pocket002 bottom-up 230 x 160 x 4 mm, 38 mm cutter",
        width=230.0,
        height=160.0,
        depth=4.0,
        tool_diameter=38.0,
        step_down=1.0,
        step_over=13.3,
        feed_rate=800.0,
        plunge_rate=300.0,
        safe_z=6.0,
        start_z=0.0,
        origin="center",
        source_document="tee-tablett",
        source_object="Body",
        source_feature="Pocket002",
    ),
}


class _TemplatePresetMapping(Mapping[str, TemplateSpec]):
    def __init__(self, specs: Mapping[str, TemplateSpec]) -> None:
        self._specs = specs

    def __getitem__(self, key: str) -> TemplateSpec:
        return replace(self._specs[key])

    def __iter__(self) -> Iterator[str]:
        return iter(self._specs)

    def __len__(self) -> int:
        return len(self._specs)


RECTANGLE_POCKET_PRESETS: Mapping[str, TemplateSpec] = _TemplatePresetMapping(
    _RECTANGLE_POCKET_PRESET_SPECS
)


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

    local_paths = _orient_paths(_raster_paths(spec), spec)
    paths = _offset_paths(local_paths, spec.start_x, spec.start_y)
    if spec.cut_start_x is not None and spec.cut_start_y is not None:
        paths = _prefer_start_near(paths, spec.cut_start_x, spec.cut_start_y)
    depths = _depth_levels(spec.start_z, spec.depth, spec.step_down)
    first_x, first_y = paths[0]

    lines = [
        _template_header("rectangle pocket", spec),
        f"; size: {_fmt(spec.width)} x {_fmt(spec.height)} x {_fmt(spec.depth)} mm",
        f"; tool: {_fmt(spec.tool_diameter)} mm",
        f"; axes: {'swapped' if spec.swap_xy else 'normal'}",
        f"; start: X{_fmt(spec.start_x)} Y{_fmt(spec.start_y)}",
        "G21",
        "G90",
        "G17",
        f"G0 Z{_fmt(spec.safe_z)}",
    ]
    source_lines = _source_header_lines(spec)
    if source_lines:
        lines[5:5] = source_lines
    if spec.cut_start_x is not None and spec.cut_start_y is not None:
        lines.insert(5, f"; cut start target: X{_fmt(spec.cut_start_x)} Y{_fmt(spec.cut_start_y)}")

    for depth in depths:
        lines.append(f"; depth {_fmt(depth)}")
        lines.append(f"G0 X{_fmt(first_x)} Y{_fmt(first_y)}")
        lines.append(f"G1 Z{_fmt(depth)} F{_fmt(spec.plunge_rate)}")
        _append_raster_moves(lines, paths, spec.feed_rate)
        lines.append(f"G0 Z{_fmt(spec.safe_z)}")

    lines.append(f"G0 X{_fmt(spec.start_x)} Y{_fmt(spec.start_y)}")
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
    program.lines[0] = _template_header("square pocket", spec)
    return program


def rectangle_pocket_preset(name: str, **overrides) -> TemplateSpec:
    """Return a named rectangular pocket preset as a fresh ``TemplateSpec``."""
    key = _normalize_preset_name(name)
    try:
        spec = _RECTANGLE_POCKET_PRESET_SPECS[key]
    except KeyError as exc:
        available = ", ".join(sorted(_RECTANGLE_POCKET_PRESET_SPECS))
        raise KeyError(f"Unknown rectangle pocket preset '{name}'. Available presets: {available}.") from exc
    return replace(spec, **overrides)


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

    for name in ("start_x", "start_y"):
        value = getattr(spec, name)
        if not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be numeric.")
    if spec.cut_start_x is None and spec.cut_start_y is not None:
        raise ValueError("cut_start_x must be set when cut_start_y is set.")
    if spec.cut_start_y is None and spec.cut_start_x is not None:
        raise ValueError("cut_start_y must be set when cut_start_x is set.")
    for name in ("cut_start_x", "cut_start_y"):
        value = getattr(spec, name)
        if value is not None and not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be numeric when set.")
    for name in ("source_document", "source_object", "source_feature"):
        value = getattr(spec, name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{name} must be a string when set.")


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


def _offset_paths(points: Sequence[Point2D], start_x: float, start_y: float) -> list[Point2D]:
    return [(x_val + start_x, y_val + start_y) for x_val, y_val in points]


def _orient_paths(points: Sequence[Point2D], spec: TemplateSpec) -> list[Point2D]:
    oriented = [(y_val, x_val) for x_val, y_val in points] if spec.swap_xy else list(points)
    return oriented


def _prefer_start_near(points: Sequence[Point2D], target_x: float, target_y: float) -> list[Point2D]:
    variants = _path_variants(points)
    return min(variants, key=lambda variant: _distance_sq(variant[0], (target_x, target_y)))


def _path_variants(points: Sequence[Point2D]) -> list[list[Point2D]]:
    base = list(points)
    pair_swapped = []
    for index in range(0, len(base), 2):
        pair = base[index:index + 2]
        pair_swapped.extend(reversed(pair))

    row_reversed = []
    for index in range(len(base) - 2, -1, -2):
        row_reversed.extend(base[index:index + 2])

    variants = [
        base,
        list(reversed(base)),
        pair_swapped,
        list(reversed(pair_swapped)),
        row_reversed,
        list(reversed(row_reversed)),
    ]
    deduped = []
    seen = set()
    for variant in variants:
        key = tuple(variant)
        if key not in seen and variant:
            seen.add(key)
            deduped.append(variant)
    return deduped


def _distance_sq(left: Point2D, right: Point2D) -> float:
    dx = left[0] - right[0]
    dy = left[1] - right[1]
    return dx * dx + dy * dy


def _source_header_lines(spec: TemplateSpec) -> list[str]:
    values = [
        ("document", spec.source_document),
        ("object", spec.source_object),
        ("feature", spec.source_feature),
    ]
    parts = [f"{label}={value}" for label, value in values if value]
    if not parts:
        return []
    return [f"; source: {', '.join(parts)}"]


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


def _normalize_preset_name(name: str) -> str:
    return str(name or "").strip().lower().replace("-", "_").replace(" ", "_")


def _template_header(kind: str, spec: TemplateSpec) -> str:
    suffix = f": {spec.name.strip()}" if spec.name and spec.name.strip() else ""
    return f"; RouterKing {kind} template{suffix}"


def _fmt(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")
