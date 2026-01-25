"""Simple 2D CAM fallback for RouterKing."""

from dataclasses import dataclass


@dataclass
class SimpleJobSettings:
    safe_z: float = 5.0
    cut_z: float = -1.0
    start_z: float = 0.0
    pass_depth: float = 0.0
    ramp_length: float = 0.0
    lead_in: float = 0.0
    lead_out: float = 0.0
    feed_rate: float = 800.0
    plunge_rate: float = 300.0
    units: str = "mm"
    spindle_speed: int = 0
    laser_power: int = 0
    start_spindle: bool = True


def generate_gcode_from_paths(paths, settings=None):
    if settings is None:
        settings = SimpleJobSettings()

    lines = ["; RouterKing simple CAM"]
    lines.append("G90")
    lines.append("G17")
    if settings.units == "inch":
        lines.append("G20")
    else:
        lines.append("G21")

    if settings.safe_z is not None:
        lines.append(f"G0 Z{_fmt(settings.safe_z)}")

    if settings.start_spindle:
        spindle = _spindle_command(settings)
        if spindle:
            lines.append(spindle)

    if not paths:
        lines.append("; No toolpaths provided")
        lines.append("M2")
        return "\n".join(lines)

    feed_move = f" F{_fmt(settings.feed_rate)}" if settings.feed_rate else ""
    plunge_move = f" F{_fmt(settings.plunge_rate)}" if settings.plunge_rate else ""

    pass_depths = _compute_pass_depths(settings)

    for path in paths:
        points = _sanitize_path(path)
        if len(points) < 2:
            continue
        points = _apply_lead_in_out(points, settings.lead_in, settings.lead_out)
        if len(points) < 2:
            continue

        start_x, start_y = points[0]
        for depth in pass_depths:
            lines.append(f"G0 X{_fmt(start_x)} Y{_fmt(start_y)}")
            if settings.safe_z is not None:
                lines.append(f"G0 Z{_fmt(settings.safe_z)}")

            if depth is None:
                _append_linear_moves(lines, points, feed_move)
            else:
                if settings.ramp_length and settings.ramp_length > 0:
                    start_z = settings.start_z if settings.start_z is not None else 0.0
                    lines.append(f"G1 Z{_fmt(start_z)}{plunge_move}")
                    _append_ramped_moves(
                        lines,
                        points,
                        start_z,
                        depth,
                        settings.ramp_length,
                        feed_move,
                    )
                else:
                    lines.append(f"G1 Z{_fmt(depth)}{plunge_move}")
                    _append_linear_moves(lines, points, feed_move)

            if settings.safe_z is not None:
                lines.append(f"G0 Z{_fmt(settings.safe_z)}")

    lines.append("M5")
    lines.append("M2")
    return "\n".join(lines)


def paths_from_shape(model, deflection=0.1):
    shape = _resolve_shape(model)
    if shape is None or not hasattr(shape, "Edges"):
        raise ValueError("No shape edges available for simple CAM fallback.")

    paths = []
    for edge in getattr(shape, "Edges", []) or []:
        points = _discretize_edge(edge, deflection)
        if len(points) < 2:
            continue
        path = [(pt.x, pt.y) for pt in points if hasattr(pt, "x") and hasattr(pt, "y")]
        if len(path) >= 2:
            paths.append(path)
    return paths


def _resolve_shape(model):
    if model is None:
        return None
    if hasattr(model, "Shape"):
        return getattr(model, "Shape", None)
    return model


def _discretize_edge(edge, deflection):
    if hasattr(edge, "discretize"):
        try:
            return edge.discretize(Deflection=deflection)
        except Exception:
            try:
                return edge.discretize(25)
            except Exception:
                pass
    points = []
    for vertex in getattr(edge, "Vertexes", []) or []:
        point = getattr(vertex, "Point", None)
        if point is not None:
            points.append(point)
    return points


def _spindle_command(settings):
    if settings.laser_power:
        return f"M3 S{int(settings.laser_power)}"
    if settings.spindle_speed:
        return f"M3 S{int(settings.spindle_speed)}"
    return "M3" if settings.start_spindle else ""


def _fmt(value):
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _compute_pass_depths(settings):
    if settings.cut_z is None:
        return [None]
    pass_depth = settings.pass_depth or 0.0
    if pass_depth <= 0:
        return [settings.cut_z]

    start_z = settings.start_z if settings.start_z is not None else 0.0
    target = settings.cut_z
    if start_z == target:
        return [target]

    step = abs(pass_depth)
    direction = -1.0 if target < start_z else 1.0
    depth = start_z + direction * step
    depths = []
    if direction < 0:
        while depth > target:
            depths.append(depth)
            depth += direction * step
    else:
        while depth < target:
            depths.append(depth)
            depth += direction * step
    if not depths or depths[-1] != target:
        depths.append(target)
    return depths


def _sanitize_path(path):
    points = []
    for point in path or []:
        if hasattr(point, "x") and hasattr(point, "y"):
            candidate = (point.x, point.y)
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            candidate = (float(point[0]), float(point[1]))
        else:
            continue
        if not points or points[-1] != candidate:
            points.append(candidate)
    return points


def _apply_lead_in_out(points, lead_in, lead_out):
    if len(points) < 2:
        return points
    result = list(points)
    if lead_in and lead_in > 0:
        start = result[0]
        next_pt = result[1]
        direction = _normalize((next_pt[0] - start[0], next_pt[1] - start[1]))
        if direction is not None:
            lead = (start[0] - direction[0] * lead_in, start[1] - direction[1] * lead_in)
            result.insert(0, lead)
    if lead_out and lead_out > 0:
        end = result[-1]
        prev = result[-2]
        direction = _normalize((end[0] - prev[0], end[1] - prev[1]))
        if direction is not None:
            lead = (end[0] + direction[0] * lead_out, end[1] + direction[1] * lead_out)
            result.append(lead)
    return result


def _append_linear_moves(lines, points, feed_move):
    for x_val, y_val in points[1:]:
        lines.append(f"G1 X{_fmt(x_val)} Y{_fmt(y_val)}{feed_move}")


def _append_ramped_moves(lines, points, start_z, target_z, ramp_length, feed_move):
    if ramp_length <= 0 or start_z == target_z:
        _append_linear_moves(lines, points, feed_move)
        return

    ramp_delta = target_z - start_z
    total_length = 0.0
    prev_x, prev_y = points[0]
    for x_val, y_val in points[1:]:
        dx = x_val - prev_x
        dy = y_val - prev_y
        total_length += (dx * dx + dy * dy) ** 0.5
        prev_x, prev_y = x_val, y_val
    if total_length <= 0:
        _append_linear_moves(lines, points, feed_move)
        return
    ramp_length = min(ramp_length, total_length)
    remaining = ramp_length
    traveled = 0.0
    prev_x, prev_y = points[0]
    current_z = start_z

    for x_val, y_val in points[1:]:
        dx = x_val - prev_x
        dy = y_val - prev_y
        seg_len = (dx * dx + dy * dy) ** 0.5
        if seg_len <= 0:
            prev_x, prev_y = x_val, y_val
            continue
        if remaining > 0:
            if seg_len <= remaining:
                traveled += seg_len
                current_z = start_z + ramp_delta * (traveled / ramp_length)
                lines.append(
                    f"G1 X{_fmt(x_val)} Y{_fmt(y_val)} Z{_fmt(current_z)}{feed_move}"
                )
                remaining -= seg_len
                prev_x, prev_y = x_val, y_val
                continue

            ratio = remaining / seg_len
            mid_x = prev_x + dx * ratio
            mid_y = prev_y + dy * ratio
            lines.append(
                f"G1 X{_fmt(mid_x)} Y{_fmt(mid_y)} Z{_fmt(target_z)}{feed_move}"
            )
            remaining = 0.0
            prev_x, prev_y = mid_x, mid_y

        lines.append(f"G1 X{_fmt(x_val)} Y{_fmt(y_val)} Z{_fmt(target_z)}{feed_move}")
        prev_x, prev_y = x_val, y_val


def _normalize(vector):
    dx, dy = vector
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return None
    return (dx / length, dy / length)
