"""CAM/Path workbench availability helpers."""

from dataclasses import dataclass

try:  # FreeCAD may not be available during tests or linting.
    import FreeCADGui as Gui
except Exception:  # pragma: no cover - FreeCAD not available in CI
    Gui = None


_CANDIDATES = (
    ("CAM", "CAMWorkbench"),
    ("Path", "PathWorkbench"),
)


@dataclass
class CamWorkbenchStatus:
    available: bool
    module_name: str = ""
    workbench_name: str = ""
    reason: str = ""
    workbench_listed: bool = False
    module_imported: bool = False


def get_cam_workbench_status():
    if Gui is None:
        return CamWorkbenchStatus(
            available=False,
            reason="FreeCAD GUI not available.",
        )

    workbench_names = set()
    if hasattr(Gui, "listWorkbenches"):
        try:
            workbench_names = set(Gui.listWorkbenches().keys())
        except Exception:
            workbench_names = set()

    for module_name, workbench_name in _CANDIDATES:
        module_imported = _try_import(module_name)
        workbench_listed = workbench_name in workbench_names
        if module_imported or workbench_listed:
            reason = "Available."
            if module_imported and not workbench_listed:
                reason = "Module imported but workbench not listed."
            elif workbench_listed and not module_imported:
                reason = "Workbench listed but module import failed."
            return CamWorkbenchStatus(
                available=True,
                module_name=module_name,
                workbench_name=workbench_name,
                reason=reason,
                workbench_listed=workbench_listed,
                module_imported=module_imported,
            )

    if workbench_names:
        reason = "No CAM/Path workbench found."
    else:
        reason = "No workbenches reported by FreeCAD."
    return CamWorkbenchStatus(available=False, reason=reason)


def activate_cam_workbench(status=None):
    if Gui is None or not hasattr(Gui, "activateWorkbench"):
        return False, "FreeCAD GUI not available."

    if status is None:
        status = get_cam_workbench_status()

    if not status.available:
        return False, status.reason or "CAM/Path workbench not available."

    if status.module_name:
        _try_import(status.module_name)

    workbench_name = status.workbench_name
    if not workbench_name:
        return False, "No CAM/Path workbench name available."

    try:
        Gui.activateWorkbench(workbench_name)
    except Exception as exc:
        return False, f"Activation failed: {exc}"

    return True, f"Activated {workbench_name}."


def _try_import(module_name):
    try:
        __import__(module_name)
        return True
    except Exception:
        return False
