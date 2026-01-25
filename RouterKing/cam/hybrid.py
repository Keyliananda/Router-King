"""Hybrid CAM integration: use Path/CAM when available, fallback to simple engine."""

from dataclasses import dataclass, field
import os
import tempfile

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None

try:
    from .simple_engine import SimpleJobSettings, generate_gcode_from_paths, paths_from_shape
except ImportError:  # pragma: no cover - fallback for FreeCAD import path
    from cam.simple_engine import SimpleJobSettings, generate_gcode_from_paths, paths_from_shape


@dataclass
class CamJobSettings:
    name: str = "RouterKing Job"
    post_processor: str = "grbl_post"
    output_path: str = ""
    start_depth: float = 0.0
    final_depth: float = -1.0
    step_down: float = 1.0
    profile_side: str = "Outside"
    profile_direction: str = "CCW"
    feed_rate: float = 800.0
    plunge_rate: float = 300.0


@dataclass
class OperationSpec:
    kind: str
    base: object = None
    properties: dict = field(default_factory=dict)


@dataclass
class HybridResult:
    gcode: str
    engine: str
    warnings: list = field(default_factory=list)
    job: object = None


def generate_hybrid_gcode(
    model,
    operations=None,
    cam_settings=None,
    simple_settings=None,
    prefer_cam=True,
):
    warnings = []
    cam_settings = cam_settings or CamJobSettings()
    simple_settings = simple_settings or SimpleJobSettings()

    if prefer_cam:
        try:
            gcode, job = generate_cam_gcode(model, operations, cam_settings)
            return HybridResult(gcode=gcode, engine="cam", warnings=warnings, job=job)
        except Exception as exc:
            warnings.append(f"CAM integration failed, using simple engine: {exc}")

    gcode = generate_simple_gcode(model, simple_settings)
    return HybridResult(gcode=gcode, engine="simple", warnings=warnings, job=None)


def generate_cam_gcode(model, operations=None, cam_settings=None):
    if App is None:
        raise RuntimeError("FreeCAD environment not available.")

    cam_settings = cam_settings or CamJobSettings()
    cam_module = _import_cam_module()
    if cam_module is None:
        raise RuntimeError("CAM/Path module not available.")

    job = _coerce_job(model, cam_module, cam_settings)
    if job is None:
        raise RuntimeError("Failed to create CAM job.")

    _ensure_operations(job, model, operations, cam_settings)
    gcode = _export_gcode(job, cam_settings.post_processor, cam_settings.output_path)
    if not gcode:
        raise RuntimeError("CAM post processor returned empty output.")
    return gcode, job


def generate_simple_gcode(model, settings=None):
    settings = settings or SimpleJobSettings()
    paths = _coerce_paths(model, settings)
    return generate_gcode_from_paths(paths, settings)


def _import_cam_module():
    for name in ("CAM", "Path"):
        module = _import_module(name)
        if module is not None:
            return module
    return None


def _coerce_job(model, cam_module, settings):
    if _looks_like_job(model):
        return model

    job = _create_job(cam_module, settings)
    if job is None:
        job = _create_job_from_paths(settings)

    if job is not None and model is not None:
        _assign_job_model(job, model)
    return job


def _looks_like_job(obj):
    if obj is None:
        return False
    type_id = getattr(obj, "TypeId", "") or ""
    return "Job" in type_id or hasattr(obj, "Operations")


def _create_job(cam_module, settings):
    job = None
    if hasattr(cam_module, "Job") and hasattr(cam_module.Job, "Create"):
        try:
            job = cam_module.Job.Create(settings.name)
        except Exception:
            job = None

    if job is None:
        job = _create_job_from_paths(settings)
    return job


def _create_job_from_paths(settings):
    for module_name in (
        "PathScripts.PathJob",
        "PathScripts.PathJobGui",
    ):
        module = _import_module(module_name)
        if module is None:
            continue
        creator = getattr(module, "Create", None)
        if callable(creator):
            try:
                return creator(settings.name)
            except Exception:
                continue
    return None


def _assign_job_model(job, model):
    try:
        if hasattr(job, "Model"):
            job.Model = [model] if not isinstance(model, (list, tuple)) else list(model)
            return
    except Exception:
        pass

    try:
        if hasattr(job, "Base"):
            job.Base = model
    except Exception:
        pass


def _ensure_operations(job, model, operations, settings):
    if operations is None:
        operations = [OperationSpec(kind="profile")]

    for op_spec in operations:
        op = _create_operation(job, model, op_spec, settings)
        if op is None:
            continue


def _create_operation(job, model, op_spec, settings):
    kind = (op_spec.kind or "").lower()
    module_names, class_name = _operation_module_candidates(kind)
    if not module_names:
        return None

    op = None
    for module_name in module_names:
        module = _import_module(module_name)
        if module is None:
            continue
        op = _instantiate_op(module, class_name, job)
        if op is not None:
            break

    if op is None:
        return None

    base = op_spec.base if op_spec.base is not None else model
    if base is not None:
        _assign_op_base(op, base)

    properties = _default_op_properties(kind, settings)
    properties.update(op_spec.properties or {})
    for key, value in properties.items():
        _set_op_property(op, key, value)

    return op


def _operation_module_candidates(kind):
    if kind == "profile":
        return (("Path.Op.Profile", "PathScripts.PathProfile"), "Profile")
    if kind == "pocket":
        return (("Path.Op.PocketShape", "PathScripts.PathPocketShape"), "PocketShape")
    if kind == "drilling":
        return (("Path.Op.Drilling", "PathScripts.PathDrilling"), "Drilling")
    return ((), "")


def _instantiate_op(module, class_name, job):
    op_class = getattr(module, class_name, None)
    if op_class is not None and hasattr(op_class, "Create"):
        try:
            return op_class.Create(job)
        except Exception:
            return None
    creator = getattr(module, "Create", None)
    if callable(creator):
        try:
            return creator(job)
        except Exception:
            return None
    return None


def _assign_op_base(op, base):
    for attr in ("Base", "BaseGeometry", "BaseObject"):
        if hasattr(op, attr):
            try:
                setattr(op, attr, base)
                return
            except Exception:
                continue


def _default_op_properties(kind, settings):
    if kind == "profile":
        return {
            "Side": settings.profile_side,
            "Direction": settings.profile_direction,
            "StartDepth": settings.start_depth,
            "FinalDepth": settings.final_depth,
            "StepDown": settings.step_down,
            "HorizFeed": settings.feed_rate,
            "VertFeed": settings.plunge_rate,
        }
    if kind == "pocket":
        return {
            "StartDepth": settings.start_depth,
            "FinalDepth": settings.final_depth,
            "StepDown": settings.step_down,
            "HorizFeed": settings.feed_rate,
            "VertFeed": settings.plunge_rate,
        }
    if kind == "drilling":
        return {
            "StartDepth": settings.start_depth,
            "FinalDepth": settings.final_depth,
            "PeckDepth": settings.step_down,
            "Feed": settings.plunge_rate,
        }
    return {}


def _set_op_property(op, name, value):
    if value is None:
        return False
    if hasattr(op, name):
        try:
            setattr(op, name, value)
            return True
        except Exception:
            return False

    aliases = {
        "HorizFeed": ("FeedRate", "Feed", "HorizontalFeed"),
        "VertFeed": ("PlungeRate", "VerticalFeed", "PlungeFeed"),
        "Feed": ("FeedRate",),
    }
    for alias in aliases.get(name, ()):
        if hasattr(op, alias):
            try:
                setattr(op, alias, value)
                return True
            except Exception:
                return False
    return False


def _export_gcode(job, post_processor, output_path):
    output_path = output_path or ""
    temp_path = ""
    if not output_path:
        handle, temp_path = tempfile.mkstemp(prefix="routerking_", suffix=".nc")
        os.close(handle)
        output_path = temp_path

    exporters = [
        _export_via_path_post,
        _export_via_path_post_command,
        _export_via_path_scripts_post,
    ]
    last_exc = None
    for exporter in exporters:
        try:
            result = exporter(job, post_processor, output_path)
        except Exception as exc:
            last_exc = exc
            continue
        gcode = _read_gcode_output(result, output_path)
        if gcode:
            if temp_path:
                _safe_remove(temp_path)
            return gcode

    if temp_path:
        _safe_remove(temp_path)
    if last_exc is not None:
        raise RuntimeError(last_exc)
    return ""


def _export_via_path_post(job, post_processor, output_path):
    module = _import_module("Path")
    if module is None:
        raise RuntimeError("Path module not available.")
    post = getattr(module, "Post", None)
    if post is None:
        raise RuntimeError("Path.Post not available.")
    export = getattr(post, "export", None)
    if not callable(export):
        raise RuntimeError("Path.Post.export not available.")
    try:
        return export(job, post_processor, output_path)
    except TypeError:
        return export([job], post_processor, output_path)


def _export_via_path_post_command(job, post_processor, output_path):
    module = _import_module("Path")
    if module is None:
        raise RuntimeError("Path module not available.")
    post = getattr(module, "Post", None)
    if post is None:
        raise RuntimeError("Path.Post not available.")
    command = getattr(post, "Command", None)
    if command is None:
        raise RuntimeError("Path.Post.Command not available.")
    export = getattr(command, "export", None)
    if not callable(export):
        raise RuntimeError("Path.Post.Command.export not available.")
    try:
        return export(job, output_path, post_processor)
    except TypeError:
        return export([job], output_path, post_processor)


def _export_via_path_scripts_post(job, post_processor, output_path):
    module = _import_module("PathScripts.PathPost")
    if module is None:
        raise RuntimeError("PathScripts.PathPost not available.")
    command = getattr(module, "Command", None)
    if command is None:
        raise RuntimeError("PathScripts.PathPost.Command not available.")
    export = getattr(command, "export", None)
    if not callable(export):
        raise RuntimeError("PathScripts.PathPost.Command.export not available.")
    try:
        return export(job, output_path, post_processor)
    except TypeError:
        return export([job], output_path, post_processor)


def _read_gcode_output(result, output_path):
    if isinstance(result, bytes):
        try:
            return result.decode("utf-8")
        except Exception:
            return ""
    if isinstance(result, str) and result.strip():
        return result
    if output_path and os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as handle:
                return handle.read()
        except Exception:
            return ""
    return ""


def _coerce_paths(model, settings):
    if _looks_like_paths(model):
        return model
    if _looks_like_path(model):
        return [model]

    paths = paths_from_shape(model, deflection=0.1)
    if not paths:
        raise RuntimeError("Simple engine could not extract any paths.")
    return paths


def _looks_like_paths(value):
    if not isinstance(value, (list, tuple)):
        return False
    if not value:
        return False
    first = value[0]
    if isinstance(first, (list, tuple)) and first:
        if _looks_like_point(first[0]):
            return True
        inner = first[0]
        return isinstance(inner, (list, tuple)) and len(inner) == 2
    return False


def _looks_like_path(value):
    if not isinstance(value, (list, tuple)) or not value:
        return False
    return _looks_like_point(value[0])


def _looks_like_point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    return all(isinstance(item, (int, float)) for item in value)


def _import_module(name):
    try:
        return __import__(name, fromlist=["*"])
    except Exception:
        return None


def _safe_remove(path):
    try:
        os.remove(path)
    except Exception:
        pass
