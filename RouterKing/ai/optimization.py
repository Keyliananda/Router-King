"""Spline optimization helpers for RouterKing AI tools."""

import re

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None

try:  # Part is only available inside FreeCAD.
    import Part
except Exception:  # pragma: no cover - Part not available in CI
    Part = None

try:
    from .config import load_config
    from .context import get_selection_context
    from .logging import get_logger
    from .results import AnalysisIssue, OptimizationResult, OptimizationTarget
except ImportError:  # pragma: no cover - fallback for FreeCAD import path
    from ai.config import load_config
    from ai.context import get_selection_context
    from ai.logging import get_logger
    from ai.results import AnalysisIssue, OptimizationResult, OptimizationTarget


_LOG = get_logger("routerking.ai.optimization")


def optimize_selection(context=None, create_preview=True):
    if context is None:
        context = get_selection_context()

    result = OptimizationResult()
    config = load_config()
    settings = config["optimization"]

    if context.warnings:
        for warning in context.warnings:
            result.issues.append(
                AnalysisIssue(
                    severity="info",
                    message=warning,
                    suggestion="Select geometry and retry.",
                    feedback_key="optimization.no_selection",
                )
            )
        result.summary = "No selection."
        return result

    if App is None or Part is None:
        result.issues.append(
            AnalysisIssue(
                severity="warning",
                message="FreeCAD Part module not available.",
                suggestion="Run spline optimization inside FreeCAD.",
                feedback_key="optimization.unavailable",
            )
        )
        result.summary = "Optimization unavailable."
        return result

    doc = App.ActiveDocument if create_preview else None
    if create_preview and doc is None:
        result.issues.append(
            AnalysisIssue(
                severity="warning",
                message="No active document.",
                suggestion="Open a document and retry.",
                feedback_key="optimization.no_document",
            )
        )
        create_preview = False

    total_splines = 0
    optimized_edges = 0
    optimized_objects = 0

    transaction_open = False
    success = False
    if create_preview and doc is not None:
        try:
            doc.openTransaction("RouterKing Spline Preview")
            transaction_open = True
        except Exception:
            create_preview = False
            transaction_open = False

    try:
        for item in context.items:
            shape = getattr(item.obj, "Shape", None)
            if shape is None or not hasattr(shape, "Edges"):
                result.issues.append(
                    AnalysisIssue(
                        severity="warning",
                        message=f"{item.label}: No shape data available.",
                        suggestion="Select a Part/Sketch with geometry.",
                        object_label=item.label,
                        feedback_key="optimization.no_shape",
                    )
                )
                continue

            if getattr(shape, "Faces", None):
                if shape.Faces:
                    result.issues.append(
                        AnalysisIssue(
                            severity="warning",
                            message=f"{item.label}: Faces are not preserved in preview.",
                            suggestion="Run optimization on sketch or wire geometry.",
                            object_label=item.label,
                            feedback_key="optimization.faces_not_preserved",
                        )
                    )

            new_edges = []
            object_changes = 0
            for edge in shape.Edges:
                curve = getattr(edge, "Curve", None)
                if curve is None or not _is_spline_curve(curve):
                    new_edges.append(edge)
                    continue

                total_splines += 1
                optimized_edge, before, after = _optimize_edge(edge, settings)
                if optimized_edge is None:
                    new_edges.append(edge)
                    continue

                new_edges.append(optimized_edge)
                object_changes += 1
                optimized_edges += 1
                result.issues.append(
                    AnalysisIssue(
                        severity="info",
                        message=f"{item.label}: Spline reduced from {before} to {after} control points.",
                        suggestion="Preview created.",
                        object_label=item.label,
                        feedback_key="optimization.spline_reduction",
                    )
                )

            if object_changes:
                preview_shape = _shape_from_edges(new_edges)
                if preview_shape is None:
                    result.issues.append(
                    AnalysisIssue(
                        severity="warning",
                        message=f"{item.label}: Failed to build optimized shape.",
                        suggestion="Try a simpler selection.",
                        object_label=item.label,
                        feedback_key="optimization.build_failed",
                    )
                )
                    continue

                result.optimized_targets.append(
                    OptimizationTarget(
                        obj=item.obj,
                        label=item.label,
                        shape=preview_shape,
                        optimized_edges=object_changes,
                    )
                )

                if create_preview and doc is not None:
                    preview_obj = _create_preview_object(doc, item.label, preview_shape)
                    if preview_obj is not None:
                        result.preview_objects.append(preview_obj)

        success = True
    finally:
        if transaction_open and doc is not None:
            try:
                if success:
                    doc.commitTransaction()
                else:
                    doc.abortTransaction()
            except Exception as exc:
                _LOG.warning("Failed to finalize transaction: %s", exc)
            if success:
                try:
                    doc.recompute()
                except Exception:
                    pass

    result.stats = {
        "objects": len(context.items),
        "spline_edges": total_splines,
        "optimized_edges": optimized_edges,
        "preview_objects": len(result.preview_objects),
    }

    optimized_objects = len(result.optimized_targets)
    if optimized_edges:
        result.summary = (
            f"Optimized {optimized_edges} spline edge(s) across {optimized_objects} object(s)."
        )
    else:
        result.summary = "No spline edges eligible for optimization."
        if not result.issues:
            result.issues.append(
                AnalysisIssue(
                    severity="info",
                    message="No spline edges met the reduction criteria.",
                    suggestion="Select splines with many control points.",
                    feedback_key="optimization.no_eligible",
                )
            )
    return result


def _optimize_edge(edge, settings):
    curve = getattr(edge, "Curve", None)
    if curve is None or not _is_spline_curve(curve):
        return None, None, None

    poles = _safe_get_poles(curve)
    if poles is None:
        return None, None, None

    before = len(poles)
    target_poles = max(2, int(settings.get("target_poles", 12)))
    if before <= target_poles:
        return None, before, before

    points = _sample_edge(edge, settings, before)
    if len(points) < 2:
        return None, before, before

    new_curve = _approximate_curve(points, settings)
    if new_curve is None:
        return None, before, before

    new_poles = _safe_get_poles(new_curve)
    if new_poles is None:
        return None, before, before

    after = len(new_poles)
    if after >= before:
        return None, before, after

    try:
        new_edge = new_curve.toShape()
    except Exception:
        return None, before, after

    return new_edge, before, after


def _sample_edge(edge, settings, before_poles):
    sample_points = int(settings.get("sample_points", 60))
    sample_points = max(sample_points, before_poles * 3)
    try:
        points = edge.discretize(Number=sample_points)
    except Exception:
        try:
            points = edge.discretize(Deflection=float(settings.get("tolerance", 0.05)))
        except Exception:
            return []
    return list(points) if points else []


def _approximate_curve(points, settings):
    if Part is None:
        return None

    curve = Part.BSplineCurve()
    deg_max = max(1, int(settings.get("max_degree", 3)))
    deg_max = min(deg_max, max(1, len(points) - 1))
    deg_min = min(3, deg_max)
    tolerance = float(settings.get("tolerance", 0.05))
    kwargs = {"DegMin": deg_min, "DegMax": deg_max, "Tolerance": tolerance}

    try:
        curve.approximate(points, **kwargs)
    except TypeError:
        try:
            curve.approximate(points)
        except Exception:
            return None
    except Exception:
        return None
    return curve


def _shape_from_edges(edges):
    if not edges or Part is None:
        return None
    if len(edges) == 1:
        return edges[0]
    try:
        return Part.Compound(edges)
    except Exception:
        return None


def _create_preview_object(doc, label, shape):
    if doc is None:
        return None
    base = _safe_object_name(label)
    name = _unique_object_name(doc, base)
    try:
        preview_obj = doc.addObject("Part::Feature", name)
        preview_obj.Label = f"{label} (Spline Preview)"
        preview_obj.Shape = shape
        view = getattr(preview_obj, "ViewObject", None)
        if view is not None:
            view.LineColor = (0.2, 0.8, 0.4)
            view.LineWidth = 2.0
    except Exception as exc:
        _LOG.warning("Failed to create preview object: %s", exc)
        return None
    return preview_obj


def create_optimized_object(doc, label, shape):
    if doc is None:
        return None
    base = _safe_object_name(f"{label}_optimized")
    name = _unique_object_name(doc, base)
    try:
        optimized_obj = doc.addObject("Part::Feature", name)
        optimized_obj.Label = f"{label} (Spline Optimized)"
        optimized_obj.Shape = shape
        view = getattr(optimized_obj, "ViewObject", None)
        if view is not None:
            view.LineColor = (0.1, 0.4, 0.9)
            view.LineWidth = 2.0
    except Exception as exc:
        _LOG.warning("Failed to create optimized object: %s", exc)
        return None
    return optimized_obj


def _safe_object_name(label):
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", label or "")
    safe = safe.strip("_") or "Spline"
    safe = safe[:40]
    return f"RK_SplinePreview_{safe}"


def _unique_object_name(doc, base):
    name = base
    index = 1
    while doc.getObject(name) is not None:
        name = f"{base}_{index}"
        index += 1
    return name


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
