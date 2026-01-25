"""DXF import helpers for the simple CAM fallback."""

from dataclasses import dataclass
import math
import os

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None

try:  # FreeCAD Import module is optional.
    import Import
except Exception:  # pragma: no cover - FreeCAD not available in CI
    Import = None

try:  # Optional DXF library.
    import ezdxf
except Exception:  # pragma: no cover - ezdxf not installed
    ezdxf = None

try:
    from .simple_engine import paths_from_shape
except ImportError:  # pragma: no cover - fallback for FreeCAD import path
    from cam.simple_engine import paths_from_shape


@dataclass
class DxfImportSettings:
    deflection: float = 0.1
    arc_segment_angle: float = 10.0
    merge_tolerance: float = 1e-6
    prefer_ezdxf: bool = True
    use_freecad: bool = True


def load_dxf_paths(path, settings=None):
    settings = settings or DxfImportSettings()
    if not os.path.exists(path):
        raise FileNotFoundError(f"DXF file not found: {path}")

    if settings.use_freecad:
        paths = _import_via_freecad(path, settings)
        if paths:
            return paths

    if settings.prefer_ezdxf:
        paths = _import_via_ezdxf(path, settings)
        if paths:
            return paths

    paths = _import_via_basic_parser(path, settings)
    if not paths:
        raise ValueError("No DXF contours found.")
    return paths


def generate_gcode_from_dxf(path, gcode_settings, import_settings=None):
    from .simple_engine import generate_gcode_from_paths

    paths = load_dxf_paths(path, settings=import_settings)
    return generate_gcode_from_paths(paths, settings=gcode_settings)


def _import_via_freecad(path, settings):
    if App is None or Import is None:
        return None

    doc = None
    try:
        if hasattr(Import, "insert") and App is not None:
            doc = App.newDocument()
            Import.insert(path, doc.Name)
        elif hasattr(App, "openDocument"):
            doc = App.openDocument(path)
        else:
            return None

        shapes = []
        for obj in getattr(doc, "Objects", []) or []:
            shape = getattr(obj, "Shape", None)
            if shape is not None:
                shapes.append(shape)

        paths = []
        for shape in shapes:
            paths.extend(paths_from_shape(shape, deflection=settings.deflection))
        return _merge_paths(paths, settings.merge_tolerance)
    except Exception:
        return None
    finally:
        if doc is not None:
            try:
                App.closeDocument(doc.Name)
            except Exception:
                pass


def _import_via_ezdxf(path, settings):
    if ezdxf is None:
        return None

    try:
        doc = ezdxf.readfile(path)
    except Exception:
        return None

    paths = []
    try:
        msp = doc.modelspace()
    except Exception:
        return None

    for entity in msp:
        kind = entity.dxftype()
        if kind == "LWPOLYLINE":
            vertices = []
            try:
                for x_val, y_val, bulge in entity.get_points("xyb"):
                    vertices.append({"point": (x_val, y_val), "bulge": bulge})
            except Exception:
                points = [(pt[0], pt[1]) for pt in entity.get_points()]
                vertices = [{"point": point, "bulge": 0.0} for point in points]

            if vertices:
                points = _expand_bulge_vertices(
                    vertices,
                    bool(entity.closed),
                    settings.arc_segment_angle,
                )
                if len(points) >= 2:
                    paths.append(points)
        elif kind == "POLYLINE":
            vertices = []
            try:
                for vertex in entity.vertices():
                    point = vertex.dxf.location
                    bulge = getattr(vertex.dxf, "bulge", 0.0) or 0.0
                    vertices.append({"point": (point.x, point.y), "bulge": bulge})
            except Exception:
                points = [(pt[0], pt[1]) for pt in entity.points()]
                vertices = [{"point": point, "bulge": 0.0} for point in points]

            if vertices:
                points = _expand_bulge_vertices(
                    vertices,
                    bool(entity.is_closed),
                    settings.arc_segment_angle,
                )
                if len(points) >= 2:
                    paths.append(points)
        elif kind == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            paths.append([(start.x, start.y), (end.x, end.y)])
        elif kind == "CIRCLE":
            center = entity.dxf.center
            radius = entity.dxf.radius
            arc = _approx_arc(
                center.x,
                center.y,
                radius,
                0.0,
                360.0,
                settings.arc_segment_angle,
            )
            if len(arc) >= 2:
                paths.append(arc)
        elif kind == "SPLINE":
            points = _extract_spline_points(entity)
            if len(points) >= 2:
                paths.append(points)
        elif kind == "ARC":
            center = entity.dxf.center
            radius = entity.dxf.radius
            arc = _approx_arc(
                center.x,
                center.y,
                radius,
                entity.dxf.start_angle,
                entity.dxf.end_angle,
                settings.arc_segment_angle,
            )
            if len(arc) >= 2:
                paths.append(arc)

    if not paths:
        return None
    return _merge_paths(paths, settings.merge_tolerance)


def _import_via_basic_parser(path, settings):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            pairs = list(_iter_pairs(handle))
    except Exception:
        return []

    paths = []
    in_entities = False
    current_polyline = None

    idx = 0
    while idx < len(pairs):
        code, value = pairs[idx]
        if code == 0 and value == "SECTION":
            if idx + 1 < len(pairs) and pairs[idx + 1] == (2, "ENTITIES"):
                in_entities = True
                idx += 2
                continue
        if code == 0 and value == "ENDSEC":
            in_entities = False
            idx += 1
            continue
        if not in_entities or code != 0:
            idx += 1
            continue

        entity_type = value
        idx += 1
        entity_pairs = []
        while idx < len(pairs) and pairs[idx][0] != 0:
            entity_pairs.append(pairs[idx])
            idx += 1

        if entity_type == "POLYLINE":
            current_polyline = _parse_polyline_header(entity_pairs)
            continue
        if entity_type == "VERTEX" and current_polyline is not None:
            point = _parse_vertex(entity_pairs)
            if point is not None:
                current_polyline["vertices"].append(point)
            continue
        if entity_type == "SEQEND" and current_polyline is not None:
            points = _finalize_polyline(current_polyline, settings.arc_segment_angle)
            if len(points) >= 2:
                paths.append(points)
            current_polyline = None
            continue

        if current_polyline is not None:
            continue

        if entity_type == "LWPOLYLINE":
            vertices, closed = _parse_lwpolyline(entity_pairs)
            points = _expand_bulge_vertices(vertices, closed, settings.arc_segment_angle)
            if len(points) >= 2:
                paths.append(points)
        elif entity_type == "LINE":
            line = _parse_line(entity_pairs)
            if line is not None:
                paths.append(line)
        elif entity_type == "CIRCLE":
            circle = _parse_circle(entity_pairs, settings.arc_segment_angle)
            if circle is not None:
                paths.append(circle)
        elif entity_type == "ARC":
            arc = _parse_arc(entity_pairs, settings.arc_segment_angle)
            if arc is not None:
                paths.append(arc)
        elif entity_type == "SPLINE":
            spline = _parse_spline(entity_pairs)
            if len(spline) >= 2:
                paths.append(spline)

    if not paths:
        return []
    return _merge_paths(paths, settings.merge_tolerance)


def _iter_pairs(lines):
    line_iter = iter(lines)
    for raw_code in line_iter:
        code = raw_code.strip()
        if not code:
            continue
        try:
            code = int(code)
        except ValueError:
            continue
        try:
            value = next(line_iter)
        except StopIteration:
            break
        yield code, value.strip()


def _parse_lwpolyline(pairs):
    vertices = []
    closed = False
    last_x = None
    pending_bulge = None
    for code, value in pairs:
        if code == 70:
            try:
                closed = bool(int(value) & 1)
            except ValueError:
                closed = False
        elif code == 10:
            try:
                last_x = float(value)
                pending_bulge = None
            except ValueError:
                last_x = None
        elif code == 20 and last_x is not None:
            try:
                vertices.append({"point": (last_x, float(value)), "bulge": pending_bulge or 0.0})
            except ValueError:
                pass
            last_x = None
            pending_bulge = None
        elif code == 42:
            try:
                bulge = float(value)
            except ValueError:
                bulge = 0.0
            if vertices:
                vertices[-1]["bulge"] = bulge
            else:
                pending_bulge = bulge
    return vertices, closed


def _parse_line(pairs):
    start_x = start_y = end_x = end_y = None
    for code, value in pairs:
        try:
            val = float(value)
        except ValueError:
            continue
        if code == 10:
            start_x = val
        elif code == 20:
            start_y = val
        elif code == 11:
            end_x = val
        elif code == 21:
            end_y = val
    if None in (start_x, start_y, end_x, end_y):
        return None
    return [(start_x, start_y), (end_x, end_y)]


def _parse_circle(pairs, segment_angle):
    cx = cy = radius = None
    for code, value in pairs:
        try:
            val = float(value)
        except ValueError:
            continue
        if code == 10:
            cx = val
        elif code == 20:
            cy = val
        elif code == 40:
            radius = val
    if None in (cx, cy, radius):
        return None
    return _approx_arc(cx, cy, radius, 0.0, 360.0, segment_angle)


def _parse_arc(pairs, segment_angle):
    cx = cy = radius = start_angle = end_angle = None
    for code, value in pairs:
        try:
            val = float(value)
        except ValueError:
            continue
        if code == 10:
            cx = val
        elif code == 20:
            cy = val
        elif code == 40:
            radius = val
        elif code == 50:
            start_angle = val
        elif code == 51:
            end_angle = val
    if None in (cx, cy, radius, start_angle, end_angle):
        return None
    return _approx_arc(cx, cy, radius, start_angle, end_angle, segment_angle)


def _parse_polyline_header(pairs):
    closed = False
    for code, value in pairs:
        if code == 70:
            try:
                closed = bool(int(value) & 1)
            except ValueError:
                closed = False
    return {"closed": closed, "vertices": []}


def _parse_vertex(pairs):
    x_val = y_val = None
    bulge = 0.0
    for code, value in pairs:
        try:
            val = float(value)
        except ValueError:
            continue
        if code == 10:
            x_val = val
        elif code == 20:
            y_val = val
        elif code == 42:
            bulge = val
    if x_val is None or y_val is None:
        return None
    return {"point": (x_val, y_val), "bulge": bulge}


def _finalize_polyline(polyline, segment_angle):
    vertices = list(polyline.get("vertices", []))
    return _expand_bulge_vertices(vertices, bool(polyline.get("closed")), segment_angle)


def _parse_spline(pairs):
    control = []
    fit = []
    last_x = None
    last_fit_x = None
    for code, value in pairs:
        try:
            val = float(value)
        except ValueError:
            continue
        if code == 10:
            last_x = val
        elif code == 20 and last_x is not None:
            control.append((last_x, val))
            last_x = None
        elif code == 11:
            last_fit_x = val
        elif code == 21 and last_fit_x is not None:
            fit.append((last_fit_x, val))
            last_fit_x = None
    return fit if fit else control


def _approx_arc(cx, cy, radius, start_angle, end_angle, segment_angle):
    start = math.radians(start_angle)
    end = math.radians(end_angle)
    if end < start:
        end += 2 * math.pi
    delta = end - start
    step_angle = math.radians(max(segment_angle, 1.0))
    steps = max(8, int(abs(delta) / step_angle))
    points = []
    for idx in range(steps + 1):
        angle = start + delta * (idx / steps)
        points.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    return points


def _expand_bulge_vertices(vertices, closed, segment_angle):
    if not vertices:
        return []
    points = [vertices[0]["point"]]
    count = len(vertices)
    last_index = count if closed else count - 1
    if last_index <= 0:
        return points
    for idx in range(last_index):
        start = vertices[idx]["point"]
        bulge = vertices[idx].get("bulge", 0.0) or 0.0
        end = vertices[(idx + 1) % count]["point"]
        if bulge:
            arc_points = _bulge_to_points(start, end, bulge, segment_angle)
            points.extend(arc_points[1:])
        else:
            points.append(end)
    return points


def _bulge_to_points(start, end, bulge, segment_angle):
    if bulge == 0.0:
        return [start, end]
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    chord = math.hypot(dx, dy)
    if chord == 0.0:
        return [start, end]
    theta = 4.0 * math.atan(bulge)
    radius = chord / (2.0 * math.sin(abs(theta) / 2.0))
    h = radius * math.cos(abs(theta) / 2.0)
    mx = (x1 + x2) / 2.0
    my = (y1 + y2) / 2.0
    ux = -dy / chord
    uy = dx / chord
    direction = 1.0 if bulge > 0 else -1.0
    cx = mx + ux * h * direction
    cy = my + uy * h * direction
    start_angle = math.atan2(y1 - cy, x1 - cx)
    end_angle = math.atan2(y2 - cy, x2 - cx)
    return _approx_arc_sweep(
        cx,
        cy,
        radius,
        start_angle,
        end_angle,
        segment_angle,
        ccw=bulge > 0,
    )


def _approx_arc_sweep(cx, cy, radius, start_angle, end_angle, segment_angle, ccw=True):
    if radius <= 0:
        return [(cx, cy)]
    delta = end_angle - start_angle
    if ccw:
        if delta <= 0:
            delta += 2 * math.pi
    else:
        if delta >= 0:
            delta -= 2 * math.pi
    step_angle = math.radians(max(segment_angle, 1.0))
    steps = max(8, int(abs(delta) / step_angle))
    points = []
    for idx in range(steps + 1):
        angle = start_angle + delta * (idx / steps)
        points.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    return points


def _extract_spline_points(entity):
    for attr in ("fit_points", "control_points"):
        points = getattr(entity, attr, None)
        if points:
            return _extract_points(points)
    try:
        approximate = list(entity.approximate(segments=50))
    except Exception:
        approximate = []
    return _extract_points(approximate)


def _extract_points(points):
    result = []
    for point in points or []:
        if hasattr(point, "x") and hasattr(point, "y"):
            result.append((point.x, point.y))
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            result.append((point[0], point[1]))
    return result


def _merge_paths(paths, tolerance):
    if tolerance is None or tolerance <= 0:
        return [path for path in paths if len(path) >= 2]

    merged = []
    for path in paths:
        if len(path) < 2:
            continue
        path = _dedupe_points(path, tolerance)
        if len(path) < 2:
            continue
        merged_into = False
        for idx, current in enumerate(merged):
            if _points_close(current[-1], path[0], tolerance):
                merged[idx] = current + path[1:]
                merged_into = True
                break
            if _points_close(current[0], path[-1], tolerance):
                merged[idx] = path + current[1:]
                merged_into = True
                break
            if _points_close(current[0], path[0], tolerance):
                merged[idx] = list(reversed(path)) + current[1:]
                merged_into = True
                break
            if _points_close(current[-1], path[-1], tolerance):
                merged[idx] = current + list(reversed(path))[1:]
                merged_into = True
                break
        if not merged_into:
            merged.append(path)
    return merged


def _dedupe_points(path, tolerance):
    result = []
    for point in path:
        if not result or not _points_close(result[-1], point, tolerance):
            result.append(point)
    return result


def _points_close(a_pt, b_pt, tolerance):
    return abs(a_pt[0] - b_pt[0]) <= tolerance and abs(a_pt[1] - b_pt[1]) <= tolerance
