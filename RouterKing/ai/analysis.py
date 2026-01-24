"""Baseline geometry analysis for RouterKing AI tools."""

import math

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None

try:
    from .config import load_config
    from .context import get_selection_context
    from .logging import get_logger
    from .results import AnalysisIssue, AnalysisResult
except ImportError:  # pragma: no cover - fallback for FreeCAD import path
    from ai.config import load_config
    from ai.context import get_selection_context
    from ai.logging import get_logger
    from ai.results import AnalysisIssue, AnalysisResult


_LOG = get_logger("routerking.ai.analysis")


def analyze_selection(context=None):
    if context is None:
        context = get_selection_context()

    result = AnalysisResult()
    config = load_config()
    settings = config["analysis"]

    if context.warnings:
        for warning in context.warnings:
            result.issues.append(
                AnalysisIssue(
                    severity="info",
                    message=warning,
                    suggestion="Select geometry and retry.",
                    feedback_key="analysis.no_selection",
                )
            )
        result.summary = "No selection."
        return result

    total_edges = 0
    spline_edges = 0

    for item in context.items:
        shape = getattr(item.obj, "Shape", None)
        if shape is None or not hasattr(shape, "Edges"):
            result.issues.append(
                AnalysisIssue(
                    severity="warning",
                    message=f"{item.label}: No shape data available.",
                    suggestion="Select a Part/Sketch with geometry.",
                    object_label=item.label,
                    feedback_key="analysis.no_shape",
                )
            )
            continue

        edges = list(shape.Edges)
        total_edges += len(edges)
        spline_edges += _count_spline_edges(edges)
        _check_spline_poles(edges, settings["max_poles_warning"], item.label, result)
        _check_corner_kinks(edges, settings["corner_angle_warn_deg"], item.label, result)
        _check_min_radius(edges, settings["min_radius_warn"], item.label, result)

    result.stats = {
        "objects": len(context.items),
        "edges": total_edges,
        "spline_edges": spline_edges,
    }
    result.summary = f"Analyzed {len(context.items)} object(s)."
    if not result.issues:
        result.issues.append(
            AnalysisIssue(
                severity="info",
                message="No issues detected.",
                suggestion="Geometry looks clean.",
                feedback_key="analysis.no_issues",
            )
        )
    return result


def _count_spline_edges(edges):
    count = 0
    for edge in edges:
        curve = getattr(edge, "Curve", None)
        if curve is None:
            continue
        if _is_spline_curve(curve):
            count += 1
    return count


def _check_spline_poles(edges, max_poles, label, result):
    for edge in edges:
        curve = getattr(edge, "Curve", None)
        if curve is None or not _is_spline_curve(curve):
            continue
        poles = _safe_get_poles(curve)
        if poles is None:
            continue
        if len(poles) > max_poles:
            result.issues.append(
                AnalysisIssue(
                    severity="warning",
                    message=f"{label}: Spline has {len(poles)} control points.",
                    suggestion="Consider reducing control points or re-approximating the curve.",
                    object_label=label,
                    feedback_key="analysis.spline_poles",
                )
            )


def _check_corner_kinks(edges, angle_threshold, label, result):
    if App is None:
        return
    vertex_map = {}
    for edge in edges:
        vertices = getattr(edge, "Vertexes", [])
        if len(vertices) < 2:
            continue
        for index, vertex in enumerate(vertices[:2]):
            point = getattr(vertex, "Point", None)
            if point is None:
                continue
            key = _point_key(point)
            tangent = _edge_tangent_at_vertex(edge, vertex, index == 1)
            if tangent is None:
                continue
            vertex_map.setdefault(key, []).append(tangent)

    for tangents in vertex_map.values():
        if len(tangents) < 2:
            continue
        for i in range(len(tangents)):
            for j in range(i + 1, len(tangents)):
                angle = _angle_between(tangents[i], tangents[j])
                if angle is None:
                    continue
                if angle >= angle_threshold:
                    result.issues.append(
                        AnalysisIssue(
                            severity="warning",
                            message=f"{label}: Sharp corner detected ({angle:.1f} deg).",
                            suggestion="Consider adding a fillet or smoothing the spline.",
                            object_label=label,
                            feedback_key="analysis.corner_kink",
                        )
                    )
                    return


def _check_min_radius(edges, min_radius, label, result):
    for edge in edges:
        curve = getattr(edge, "Curve", None)
        if curve is None or not hasattr(curve, "Radius"):
            continue
        try:
            radius = float(curve.Radius)
        except Exception:
            continue
        if radius > 0 and radius < min_radius:
            result.issues.append(
                AnalysisIssue(
                    severity="warning",
                    message=f"{label}: Small radius detected ({radius:.3f}).",
                    suggestion="Increase radius to reduce toolpath stress.",
                    object_label=label,
                    feedback_key="analysis.min_radius",
                )
            )


def _is_spline_curve(curve):
    type_id = getattr(curve, "TypeId", "")
    class_name = curve.__class__.__name__
    return "Spline" in type_id or "Spline" in class_name or "Bezier" in type_id or "Bezier" in class_name


def _safe_get_poles(curve):
    get_poles = getattr(curve, "getPoles", None)
    if get_poles is None:
        return None
    try:
        return list(get_poles())
    except Exception:
        return None


def _point_key(point, decimals=4):
    return (round(point.x, decimals), round(point.y, decimals), round(point.z, decimals))


def _edge_tangent_at_vertex(edge, vertex, is_last):
    try:
        param = edge.LastParameter if is_last else edge.FirstParameter
        tangent = edge.tangentAt(param)
        if is_last:
            tangent = App.Vector(-tangent.x, -tangent.y, -tangent.z)
        return tangent
    except Exception:
        return None


def _angle_between(vec_a, vec_b):
    try:
        ax, ay, az = vec_a.x, vec_a.y, vec_a.z
        bx, by, bz = vec_b.x, vec_b.y, vec_b.z
        len_a = math.sqrt(ax * ax + ay * ay + az * az)
        len_b = math.sqrt(bx * bx + by * by + bz * bz)
        if len_a == 0.0 or len_b == 0.0:
            return None
        dot = (ax * bx + ay * by + az * bz) / (len_a * len_b)
        dot = max(-1.0, min(1.0, dot))
    except Exception:
        return None
    return math.degrees(math.acos(dot))
