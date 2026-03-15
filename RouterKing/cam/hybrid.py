"""Hybrid CAM integration: use Path/CAM when available, fallback to simple engine."""

from dataclasses import dataclass, field
import inspect
import logging
import os
import sys
import tempfile
import threading

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None

try:
    from .simple_engine import SimpleJobSettings, generate_gcode_from_paths, paths_from_shape
except ImportError:  # pragma: no cover - fallback for FreeCAD import path
    from cam.simple_engine import SimpleJobSettings, generate_gcode_from_paths, paths_from_shape

try:
    from ..grbl.postprocessor import postprocess_gcode as grbl_postprocess_gcode
except Exception:  # pragma: no cover - fallback for FreeCAD import path
    try:
        from grbl.postprocessor import postprocess_gcode as grbl_postprocess_gcode
    except Exception:  # pragma: no cover - keep CAM export functional without post module
        grbl_postprocess_gcode = None

try:
    from RouterKing.main_thread import get_dispatcher, run_on_main_thread
except ImportError:
    try:
        from main_thread import get_dispatcher, run_on_main_thread
    except ImportError:
        def get_dispatcher():  # type: ignore[misc]
            return None

        def run_on_main_thread(fn, timeout=60.0):  # type: ignore[misc]
            return fn()

LOG = logging.getLogger("routerking.cam.hybrid")


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
            LOG.warning("CAM engine failed, falling back to simple engine", exc_info=True)
            warnings.append(f"CAM integration failed, using simple engine: {exc}")

    gcode = generate_simple_gcode(model, simple_settings)
    return HybridResult(gcode=gcode, engine="simple", warnings=warnings, job=None)


def generate_cam_gcode(model, operations=None, cam_settings=None):
    """Generate CAM G-code on the Qt main thread via MainThreadDispatcher."""
    print("[HYBRID] generate_cam_gcode called, dispatcher active")
    fn = lambda: _generate_cam_gcode_impl(model, operations, cam_settings)
    dispatcher = get_dispatcher()
    if dispatcher is not None:
        run_on_main = getattr(dispatcher, "run_on_main", None)
        if callable(run_on_main):
            return run_on_main(fn)
        dispatch = getattr(dispatcher, "dispatch", None)
        if callable(dispatch):
            return dispatch(fn)
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError(
            "MainThreadDispatcher is not initialized; refusing CAM generation "
            "on worker thread."
        )
    return run_on_main_thread(fn)


def _generate_cam_gcode_impl(model, operations=None, cam_settings=None):
    if App is None:
        raise RuntimeError("FreeCAD environment not available.")

    cam_settings = cam_settings or CamJobSettings()

    # Ensure there is an active document — PathJob.Create requires one.
    doc = App.ActiveDocument
    if doc is None:
        LOG.info("No active document — creating one for CAM job.")
        doc = App.newDocument("RouterKingCAM")

    # Activate CAM workbench so Path.Main.Job etc. become importable.
    _ensure_cam_workbench()

    cam_module = _import_cam_module()
    if cam_module is None:
        raise RuntimeError("CAM/Path module not available — neither 'CAM' nor 'Path' could be imported.")

    _log_cam_environment(cam_module)

    LOG.debug(
        "generate_cam_gcode: cam_module=%s, model=%s (%s), doc=%s",
        getattr(cam_module, "__name__", cam_module),
        getattr(model, "Name", model),
        getattr(model, "TypeId", type(model).__name__),
        doc.Name,
    )

    job = _coerce_job(model, cam_module, cam_settings)
    if job is None:
        raise RuntimeError(
            "Failed to create CAM job — all creation methods exhausted.  "
            f"cam_module={getattr(cam_module, '__name__', '?')}, "
            f"model={getattr(model, 'Name', type(model).__name__)}, "
            f"doc={doc.Name}"
        )

    _ensure_operations(job, model, operations, cam_settings)
    _recompute_document(job, model)
    gcode = _export_gcode(
        job,
        cam_settings.post_processor,
        cam_settings.output_path,
        cam_settings=cam_settings,
    )
    if not gcode:
        raise RuntimeError("CAM post processor returned empty output.")
    return gcode, job


def generate_simple_gcode(model, settings=None):
    """Generate G-code via the simple engine.  Dispatches onto the Qt main thread."""
    return run_on_main_thread(
        lambda: _generate_simple_gcode_impl(model, settings)
    )


def _generate_simple_gcode_impl(model, settings=None):
    settings = settings or SimpleJobSettings()
    paths = _coerce_paths(model, settings)
    return generate_gcode_from_paths(paths, settings)


_cam_wb_activated = False


def _ensure_cam_workbench():
    """Activate the CAM/Path workbench so that ``Path.Main.*`` becomes importable.

    FreeCAD 1.0 ships the Job code in ``Mod/CAM/Path/Main/Job.py``.  That
    directory is only added to ``sys.path`` once the workbench is activated.
    This is a no-op if FreeCADGui is unavailable (tests / headless).
    """
    global _cam_wb_activated
    if _cam_wb_activated:
        return
    try:
        import FreeCADGui as Gui
    except ImportError:
        _cam_wb_activated = True
        return
    for wb_name in ("CAMWorkbench", "PathWorkbench"):
        try:
            Gui.activateWorkbench(wb_name)
            LOG.debug("Activated workbench %s", wb_name)
            _cam_wb_activated = True
            return
        except Exception:
            continue
    LOG.warning("Could not activate CAM or Path workbench")
    _cam_wb_activated = True


def _import_cam_module():
    for name in ("CAM", "Path"):
        module = _import_module(name)
        if module is not None:
            return module
    return None


_cam_env_logged = False
_post_env_logged = False


def _log_cam_environment(cam_module):
    """Log a one-time diagnostic dump of the CAM module structure."""
    global _cam_env_logged
    if _cam_env_logged:
        return
    _cam_env_logged = True

    cam_name = getattr(cam_module, "__name__", str(cam_module))
    public_attrs = [a for a in dir(cam_module) if not a.startswith("_")]
    LOG.info("CAM environment probe — module: %s, attrs: %s", cam_name, public_attrs)

    # Check for Job sub-module/class
    job_obj = getattr(cam_module, "Job", None)
    if job_obj is not None:
        job_attrs = [a for a in dir(job_obj) if not a.startswith("_")]
        LOG.info("  %s.Job attrs: %s", cam_name, job_attrs)
    else:
        LOG.info("  %s.Job: NOT FOUND", cam_name)

    # Probe Path.Main.Job (FreeCAD 1.0+) and PathScripts.PathJob (legacy)
    for probe_name in ("Path.Main.Job", "PathScripts.PathJob"):
        probe_mod = _import_module(probe_name)
        if probe_mod is not None:
            pm_attrs = [a for a in dir(probe_mod) if not a.startswith("_")]
            LOG.info("  %s attrs: %s", probe_name, pm_attrs)
            create_fn = getattr(probe_mod, "Create", None)
            if create_fn is not None:
                try:
                    sig = inspect.signature(create_fn)
                    LOG.info("  %s.Create signature: %s", probe_name, sig)
                except (ValueError, TypeError):
                    LOG.info("  %s.Create: could not inspect signature", probe_name)
        else:
            LOG.info("  %s: NOT AVAILABLE", probe_name)


def _coerce_job(model, cam_module, settings):
    if _looks_like_job(model):
        return model

    job = _create_job(cam_module, settings, model)
    if job is None:
        LOG.error(
            "All CAM job creation methods failed (model=%s, cam_module=%s)",
            getattr(model, "Name", type(model).__name__),
            getattr(cam_module, "__name__", cam_module),
        )
    return job


def _looks_like_job(obj):
    if obj is None:
        return False
    type_id = getattr(obj, "TypeId", "") or ""
    return "Job" in type_id or hasattr(obj, "Operations")


def _create_job(cam_module, settings, model=None):
    cam_name = getattr(cam_module, "__name__", str(cam_module))

    if hasattr(cam_module, "Job"):
        job_cls = cam_module.Job
        if hasattr(job_cls, "Create"):
            LOG.debug(
                "Trying %s.Job.Create (Job attrs: %s)",
                cam_name, [a for a in dir(job_cls) if not a.startswith("_")],
            )
            create = job_cls.Create
            job = _try_create_variants(create, settings, model, f"{cam_name}.Job.Create")
            if job is not None:
                return job
        else:
            LOG.debug(
                "%s.Job exists but has no Create method (attrs: %s)",
                cam_name, [a for a in dir(job_cls) if not a.startswith("_")],
            )
    else:
        LOG.debug("%s has no Job attribute", cam_name)

    return _create_job_from_paths(settings, model)


def _create_job_from_paths(settings, model=None):
    for module_name in (
        "Path.Main.Job",          # FreeCAD 1.0+ canonical location
        "PathScripts.PathJob",    # FreeCAD 0.19–0.21 (legacy)
        "PathScripts.PathJobGui",
        "Path.Job",
        "CAM.Job",
    ):
        module = _import_module(module_name)
        if module is None:
            LOG.debug("Module %s not available", module_name)
            continue
        LOG.debug(
            "Module %s loaded (attrs: %s)",
            module_name, [a for a in dir(module) if not a.startswith("_")],
        )
        creator = getattr(module, "Create", None)
        if not callable(creator):
            LOG.debug("Module %s has no callable Create", module_name)
            continue
        job = _try_create_variants(creator, settings, model, f"{module_name}.Create")
        if job is not None:
            return job
    return None


def _try_create_variants(creator, settings, model, label):
    """Try calling *creator* with 3-arg, 2-arg, then 1-arg signatures.

    FreeCAD 1.0 signature: ``Create(name, base, templateFile=None)``
    where *base* is a list of model objects or object-name strings.
    Legacy builds may accept ``Create(name, models)`` or ``Create(name)``.
    """
    models = [model] if model is not None else []
    errors = []

    LOG.debug(
        "%s: trying creation (creator=%s, model=%s, models=%s)",
        label, creator, getattr(model, "Name", model), models,
    )

    # 3-arg: Create(name, models, template)  — canonical signature
    try:
        job = creator(settings.name, models, None)
        if job is not None:
            LOG.debug("%s succeeded with 3 args", label)
            return job
        LOG.debug("%s with 3 args returned None", label)
    except TypeError as exc:
        LOG.debug("%s with 3 args raised TypeError: %s", label, exc)
        errors.append(f"3-arg TypeError: {exc}")
    except Exception as exc:
        LOG.warning("%s with 3 args failed: %s", label, exc, exc_info=True)
        errors.append(f"3-arg {type(exc).__name__}: {exc}")

    # 2-arg: Create(name, models)
    try:
        job = creator(settings.name, models)
        if job is not None:
            LOG.debug("%s succeeded with 2 args", label)
            return job
        LOG.debug("%s with 2 args returned None", label)
    except TypeError as exc:
        LOG.debug("%s with 2 args raised TypeError: %s", label, exc)
        errors.append(f"2-arg TypeError: {exc}")
    except Exception as exc:
        LOG.warning("%s with 2 args failed: %s", label, exc, exc_info=True)
        errors.append(f"2-arg {type(exc).__name__}: {exc}")

    # 1-arg: Create(name)  — legacy, assign model afterwards
    try:
        job = creator(settings.name)
        if job is not None:
            LOG.debug("%s succeeded with 1 arg (legacy)", label)
            if model is not None:
                _assign_job_model(job, model)
            return job
        LOG.debug("%s with 1 arg returned None", label)
    except Exception as exc:
        LOG.warning("%s with 1 arg failed: %s", label, exc, exc_info=True)
        errors.append(f"1-arg {type(exc).__name__}: {exc}")

    LOG.error("%s: all signatures failed: %s", label, "; ".join(errors))
    return None


def _assign_job_model(job, model):
    try:
        if hasattr(job, "Model"):
            job.Model = [model] if not isinstance(model, (list, tuple)) else list(model)
            return
    except Exception as exc:
        LOG.warning("Failed to assign model via job.Model: %s", exc)

    try:
        if hasattr(job, "Base"):
            job.Base = model
            return
    except Exception as exc:
        LOG.warning("Failed to assign model via job.Base: %s", exc)

    LOG.warning(
        "Could not assign model %s to job %s — no Model or Base attribute",
        getattr(model, "Name", model),
        getattr(job, "Name", job),
    )


def _ensure_operations(job, model, operations, settings):
    if operations is None:
        operations = [OperationSpec(kind="profile")]

    created_ops = 0
    for op_spec in operations:
        op = _create_operation(job, model, op_spec, settings)
        if op is None:
            continue
        created_ops += 1

    if created_ops:
        _recompute_document(job, model)


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

    base = _resolve_operation_base(kind, model, op_spec.base)
    if base is not None:
        _assign_op_base(op, base)

    properties = _default_op_properties(kind, settings)
    properties.update(op_spec.properties or {})
    for key, value in properties.items():
        _set_op_property(op, key, value)

    return op


def _resolve_operation_base(kind, model, explicit_base):
    """Resolve operation base geometry, with CAM-specific defaults."""
    if explicit_base is not None:
        return explicit_base
    if kind == "profile":
        return _profile_base_for_model(model)
    return model


def _profile_base_for_model(model):
    """For box profiles, target vertical side faces Face1..Face4."""
    if model is None:
        return None
    if _looks_like_box_model(model):
        faces = _box_vertical_faces(model)
        if faces:
            return [(model, faces)]
    return model


def _looks_like_box_model(model):
    type_id = getattr(model, "TypeId", "") or ""
    name = getattr(model, "Name", "") or ""
    return ("Box" in type_id) or ("Box" in name)


def _box_vertical_faces(model):
    shape = getattr(model, "Shape", None)
    faces = getattr(shape, "Faces", None)
    if faces is None:
        return []
    try:
        face_count = len(faces)
    except Exception:
        return []
    if face_count < 4:
        return []
    return [f"Face{i}" for i in range(1, 5)]


def _operation_module_candidates(kind):
    if kind == "profile":
        return (("Path.Op.Profile", "PathScripts.PathProfile"), "Profile")
    if kind == "pocket":
        return (("Path.Op.PocketShape", "PathScripts.PathPocketShape"), "PocketShape")
    if kind == "drilling":
        return (("Path.Op.Drilling", "PathScripts.PathDrilling"), "Drilling")
    return ((), "")


def _instantiate_op(module, class_name, job):
    module_name = getattr(module, "__name__", str(module))
    creator = getattr(module, "Create", None)
    if callable(creator):
        # FreeCAD 1.0 signature: Create(name, obj=None, parentJob=None)
        # Legacy signature:      Create(job)
        for call in (
            lambda: creator(class_name, None, job),
            lambda: creator(class_name, parentJob=job),
            lambda: creator(job),
        ):
            try:
                result = call()
                if result is not None:
                    return result
            except TypeError:
                continue
            except Exception as exc:
                LOG.warning("%s.Create failed: %s", module_name, exc)
                return None
    LOG.debug("%s has no callable Create function", module_name)
    return None


def _assign_op_base(op, base):
    for attr in ("Base", "BaseGeometry", "BaseObject"):
        if hasattr(op, attr):
            try:
                setattr(op, attr, base)
                return
            except Exception as exc:
                LOG.debug("op.%s assignment failed: %s", attr, exc)
                continue
    LOG.warning("Could not assign base to operation %s", getattr(op, "Name", op))


def _recompute_document(job=None, model=None):
    """Recompute candidate documents so CAM paths get generated."""
    docs = []
    for obj in (job, model):
        doc = getattr(obj, "Document", None)
        if doc is not None and doc not in docs:
            docs.append(doc)

    if App is not None:
        active_doc = getattr(App, "ActiveDocument", None)
        if active_doc is not None and active_doc not in docs:
            docs.append(active_doc)

    for doc in docs:
        try:
            doc.recompute()
        except Exception as exc:
            LOG.warning("Document recompute failed for %s: %s", getattr(doc, "Name", doc), exc)


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


def _export_gcode(job, post_processor, output_path, cam_settings=None):
    output_path = output_path or ""
    temp_path = ""
    if not output_path:
        handle, temp_path = tempfile.mkstemp(prefix="routerking_", suffix=".nc")
        os.close(handle)
        output_path = temp_path

    _log_post_environment()

    exporters = [
        _export_via_job_path_togcode,          # FreeCAD 1.0+: direct Job.Path.toGCode()
        _export_via_path_post_processor,       # FreeCAD 1.0+: Path.Post.Processor
        _export_via_cam_post_processor,        # FreeCAD 1.0+ alias: CAM.Post.Processor
        _export_via_path_post_command_module,  # FreeCAD 1.0+: Path.Post.Command module
        _export_via_path_post,                 # Older Path.Post.export
        _export_via_path_post_command,         # Older Path.Post.Command.export
        _export_via_path_scripts_post,         # Legacy PathScripts fallback
    ]
    failures = []
    for exporter in exporters:
        try:
            result = exporter(job, post_processor, output_path)
        except Exception as exc:
            LOG.debug("Exporter %s failed: %s", exporter.__name__, exc)
            failures.append(f"{exporter.__name__}: {exc}")
            continue
        gcode = _read_gcode_output(result, output_path)
        if gcode:
            gcode = _postprocess_exported_gcode(gcode, cam_settings=cam_settings)
            if output_path:
                with open(output_path, "w", encoding="utf-8") as handle:
                    handle.write(gcode)
            if temp_path:
                _safe_remove(temp_path)
            return gcode
        failures.append(f"{exporter.__name__}: empty output")

    if temp_path:
        _safe_remove(temp_path)
    if failures:
        raise RuntimeError("All post exporters failed: " + "; ".join(failures))
    return ""


def _postprocess_exported_gcode(gcode, cam_settings=None):
    if not gcode:
        return gcode
    if grbl_postprocess_gcode is None:
        return gcode
    try:
        result = grbl_postprocess_gcode(
            gcode,
            feed_rate=float(getattr(cam_settings, "feed_rate", 0.0) or 0.0) if cam_settings is not None else None,
            plunge_rate=float(getattr(cam_settings, "plunge_rate", 0.0) or 0.0) if cam_settings is not None else None,
        )
    except Exception as exc:  # pragma: no cover - postprocess must never block export
        LOG.warning("G-code postprocessing failed; using raw CAM output: %s", exc)
        return gcode
    processed = result.get("gcode") if isinstance(result, dict) else None
    if isinstance(processed, str) and processed.strip():
        return processed
    return gcode


def _export_via_job_path_togcode(job, post_processor, output_path):
    """Preferred fast-path: export directly from ``job.Path.toGCode()``."""
    _ = post_processor  # unused; direct path export does not require a post.

    path_obj = getattr(job, "Path", None)
    if path_obj is None:
        raise RuntimeError("job.Path not available.")

    to_gcode = getattr(path_obj, "toGCode", None)
    if not callable(to_gcode):
        raise RuntimeError("job.Path.toGCode not available.")

    gcode = _coerce_gcode_text(to_gcode())

    if not gcode.strip():
        gcode = _export_gcode_from_operation_paths(job)
    if not gcode.strip():
        raise RuntimeError(
            "job.Path.toGCode returned empty output and operation paths contained no G-code."
        )

    if output_path:
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(gcode)
    return gcode


def _export_gcode_from_operation_paths(job):
    """Fallback: concatenate ``op.Path.toGCode()`` for operations under this job."""
    pieces = []
    for op in _collect_job_operations(job):
        path_obj = getattr(op, "Path", None)
        to_gcode = getattr(path_obj, "toGCode", None) if path_obj is not None else None
        if not callable(to_gcode):
            continue
        text = _coerce_gcode_text(to_gcode())
        if text.strip():
            pieces.append(text.strip())
    return "\n".join(pieces)


def _collect_job_operations(job):
    """Collect likely operation objects that belong to *job*."""
    roots = []
    operations = getattr(job, "Operations", None)
    if operations is not None:
        roots.append(operations)
    roots.extend(list(getattr(job, "OutList", []) or []))

    seen = set()
    queue = list(roots)
    ordered = []
    while queue:
        obj = queue.pop(0)
        oid = id(obj)
        if oid in seen:
            continue
        seen.add(oid)
        ordered.append(obj)

        for children_attr in ("Group", "OutList"):
            for child in list(getattr(obj, children_attr, []) or []):
                if id(child) not in seen:
                    queue.append(child)

    ops = []
    for obj in ordered:
        if _looks_like_operation_object(job, obj):
            ops.append(obj)
    return ops


def _looks_like_operation_object(job, obj):
    if obj is None or obj is job:
        return False

    path_obj = getattr(obj, "Path", None)
    to_gcode = getattr(path_obj, "toGCode", None) if path_obj is not None else None
    if not callable(to_gcode):
        return False

    # Exclude tools and setup helper objects (usually no meaningful Base geometry).
    base = getattr(obj, "Base", None)
    base_geom = getattr(obj, "BaseGeometry", None)
    base_obj = getattr(obj, "BaseObject", None)
    has_base = any(val not in (None, (), [], "", ("",)) for val in (base, base_geom, base_obj))
    if has_base:
        return True

    name = str(getattr(obj, "Name", "")).lower()
    return name.startswith(("profile", "pocket", "drilling", "adaptive", "contour"))


def _coerce_gcode_text(result):
    if isinstance(result, bytes):
        return result.decode("utf-8", errors="replace")
    if isinstance(result, str):
        return result
    if isinstance(result, (list, tuple)):
        return "\n".join(str(line) for line in result)
    if result is None:
        return ""
    return str(result)


def _export_via_path_post_processor(job, post_processor, output_path):
    """FreeCAD 1.0+: ``Path.Post.Processor`` or ``Path.Post.Command``."""
    module = _resolve_module("Path.Post")
    if module is None:
        raise RuntimeError("Path.Post module not available.")
    # Try Processor first, then Command
    for attr in ("Processor", "Command"):
        processor = getattr(module, attr, None)
        if processor is None:
            continue
        export = getattr(processor, "export", None) or getattr(processor, "Export", None)
        if not callable(export):
            continue
        return _run_export_variants(export, job, post_processor, output_path)
    raise RuntimeError("Path.Post has no usable export function.")


def _export_via_cam_post_processor(job, post_processor, output_path):
    """FreeCAD 1.0+: ``CAM.Post.Processor`` or ``CAM.Post.Command``."""
    module = _resolve_module("CAM.Post")
    if module is None:
        raise RuntimeError("CAM.Post module not available.")
    for attr in ("Processor", "Command"):
        processor = getattr(module, attr, None)
        if processor is None:
            continue
        export = getattr(processor, "export", None) or getattr(processor, "Export", None)
        if not callable(export):
            continue
        return _run_export_variants(export, job, post_processor, output_path)
    raise RuntimeError("CAM.Post has no usable export function.")


def _export_via_path_post_command_module(job, post_processor, output_path):
    """FreeCAD 1.0+: direct module import ``Path.Post.Command``."""
    module = _resolve_module("Path.Post.Command")
    if module is None:
        raise RuntimeError("Path.Post.Command module not available.")
    export = getattr(module, "export", None) or getattr(module, "Export", None)
    if not callable(export):
        raise RuntimeError("Path.Post.Command module has no export function.")
    return _run_export_variants(export, job, post_processor, output_path)


def _export_via_path_post(job, post_processor, output_path):
    module = _resolve_module("Path")
    if module is None:
        raise RuntimeError("Path module not available.")
    post = getattr(module, "Post", None)
    if post is None:
        raise RuntimeError("Path.Post not available.")
    export = getattr(post, "export", None)
    if not callable(export):
        raise RuntimeError("Path.Post.export not available.")
    return _run_export_variants(export, job, post_processor, output_path)


def _export_via_path_post_command(job, post_processor, output_path):
    module = _resolve_module("Path")
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
    return _run_export_variants(export, job, post_processor, output_path)


def _export_via_path_scripts_post(job, post_processor, output_path):
    module = _resolve_module("PathScripts.PathPost")
    if module is None:
        raise RuntimeError("PathScripts.PathPost not available.")
    direct_export = getattr(module, "export", None) or getattr(module, "Export", None)
    if callable(direct_export):
        return _run_export_variants(direct_export, job, post_processor, output_path)
    command = getattr(module, "Command", None)
    if command is None:
        raise RuntimeError("PathScripts.PathPost.Command not available.")
    export = getattr(command, "export", None) or getattr(command, "Export", None)
    if not callable(export):
        raise RuntimeError("PathScripts.PathPost.Command.export not available.")
    return _run_export_variants(export, job, post_processor, output_path)


def _run_export_variants(export_fn, job, post_processor, output_path):
    """Run post exporter across FreeCAD API signature variants."""
    candidates = (
        (job, output_path, post_processor),
        ([job], output_path, post_processor),
        (job, post_processor, output_path),
        ([job], post_processor, output_path),
        (job, output_path),
        ([job], output_path),
        (job, post_processor),
        ([job], post_processor),
        (job,),
        ([job],),
    )
    errors = []
    for args in candidates:
        try:
            return export_fn(*args)
        except TypeError as exc:
            errors.append(f"TypeError: {exc}")
            continue
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            continue
    raise RuntimeError(
        "Post export failed for all known signatures: " + "; ".join(errors)
    )


def _resolve_module(name):
    module = sys.modules.get(name)
    if module is not None:
        return module
    return _import_module(name)


def _log_post_environment():
    """Log once which post-processing modules are currently loaded."""
    global _post_env_logged
    if _post_env_logged:
        return
    _post_env_logged = True

    post_modules = sorted(
        m for m in sys.modules.keys()
        if "post" in m.lower() and (m.startswith("Path") or m.startswith("CAM"))
    )
    print("[HYBRID] post modules loaded:", post_modules)
    LOG.info("Post module probe (loaded): %s", post_modules)


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
    except Exception as exc:
        LOG.debug("Import of '%s' failed: %s", name, exc)
        return None


def _safe_remove(path):
    try:
        os.remove(path)
    except Exception:
        pass
