"""CAM workbench helpers for RouterKing."""

from .dxf_import import DxfImportSettings, generate_gcode_from_dxf, load_dxf_paths
from .hybrid import CamJobSettings, HybridResult, OperationSpec, generate_hybrid_gcode
from .simple_engine import SimpleJobSettings, generate_gcode_from_paths, paths_from_shape
from .templates import (
    GcodeProgram,
    RECTANGLE_POCKET_PRESETS,
    TemplateSpec,
    rectangle_pocket,
    rectangle_pocket_preset,
    square_pocket,
)
from .workbench import CamWorkbenchStatus, activate_cam_workbench, get_cam_workbench_status

__all__ = [
    "CamJobSettings",
    "CamWorkbenchStatus",
    "DxfImportSettings",
    "GcodeProgram",
    "HybridResult",
    "OperationSpec",
    "RECTANGLE_POCKET_PRESETS",
    "SimpleJobSettings",
    "TemplateSpec",
    "activate_cam_workbench",
    "generate_gcode_from_dxf",
    "generate_gcode_from_paths",
    "generate_hybrid_gcode",
    "get_cam_workbench_status",
    "load_dxf_paths",
    "paths_from_shape",
    "rectangle_pocket",
    "rectangle_pocket_preset",
    "square_pocket",
]
