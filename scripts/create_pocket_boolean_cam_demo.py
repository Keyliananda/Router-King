"""Create a minimal FreeCAD pocket CAM demo.

The document contains a stock cuboid, a second cuboid used as the boolean
pocket volume, the resulting cut body, and a FreeCAD CAM job for a 5 mm pocket.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


FREECAD_MOD_PATH = "/Applications/FreeCAD.app/Contents/Resources/Mod"
SCRIPT_PATH = Path(globals().get("__file__", "scripts/create_pocket_boolean_cam_demo.py"))
REPO_ROOT = SCRIPT_PATH.resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "examples"
DOC_PATH = OUTPUT_DIR / "RK_Pocket_Boolean_5mm.FCStd"
GCODE_PATH = OUTPUT_DIR / "RK_Pocket_Boolean_5mm.nc"


def ensure_freecad_paths() -> None:
    if FREECAD_MOD_PATH not in sys.path and os.path.isdir(FREECAD_MOD_PATH):
        sys.path.append(FREECAD_MOD_PATH)


def set_quantity(obj, name: str, value: str) -> None:
    try:
        setattr(obj, name, value)
    except Exception:
        prop = getattr(obj, name, None)
        if hasattr(prop, "Value"):
            prop.Value = float(value.split()[0])
        else:
            raise


def set_view(obj, shape_color=None, transparency=None, visibility=None) -> None:
    view = getattr(obj, "ViewObject", None)
    if view is None:
        return
    if shape_color is not None:
        view.ShapeColor = shape_color
    if transparency is not None:
        view.Transparency = transparency
    if visibility is not None:
        view.Visibility = visibility


def main() -> None:
    ensure_freecad_paths()

    import FreeCAD as App
    import Path.Main.Job as PathJob
    import Path.Op.PocketShape as PocketShape
    from Path.Post.Processor import PostProcessorFactory

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    doc = App.newDocument("RK_Pocket_Boolean_5mm")

    stock = doc.addObject("Part::Box", "Grundquader_100x60x12")
    stock.Label = "Grundquader 100 x 60 x 12 mm"
    stock.Length = 100
    stock.Width = 60
    stock.Height = 12
    stock.Placement.Base = App.Vector(0, 0, -12)

    cutter = doc.addObject("Part::Box", "Boolean_Tasche_50x30x5")
    cutter.Label = "Boolean Tasche 50 x 30 x 5 mm"
    cutter.Length = 50
    cutter.Width = 30
    cutter.Height = 5
    cutter.Placement.Base = App.Vector(25, 15, -5)

    pocketed = doc.addObject("Part::Cut", "Werkstueck_mit_Tasche_5mm")
    pocketed.Label = "Werkstueck mit 5 mm Tasche"
    pocketed.Base = stock
    pocketed.Tool = cutter

    doc.recompute()

    set_view(stock, shape_color=(0.68, 0.68, 0.68), transparency=75, visibility=True)
    set_view(cutter, shape_color=(1.0, 0.18, 0.08), transparency=40, visibility=True)
    set_view(pocketed, shape_color=(0.70, 0.78, 0.86), transparency=0, visibility=True)

    # FreeCAD 1.0 enables the CAM simulator only when an object's internal
    # name starts with "Job"; the user-facing label can still be descriptive.
    job = PathJob.Create("Job", [pocketed], None)
    job.Label = "RK Pocket 5mm CAM"
    if hasattr(job, "PostProcessor"):
        job.PostProcessor = "grbl"
    if hasattr(job, "PostProcessorOutputFile"):
        job.PostProcessorOutputFile = str(GCODE_PATH)

    setup = job.SetupSheet
    setup.StartDepthExpression = "0 mm"
    setup.FinalDepthExpression = "-5 mm"
    setup.StepDownExpression = "1 mm"
    setup.SafeHeightOffset = "3 mm"
    setup.ClearanceHeightOffset = "6 mm"

    operation = PocketShape.Create("Pocket_5mm_Boolean", None, job)
    operation.Label = "Pocket 5mm aus Boolean-Quader"
    operation.Base = [(pocketed, ["Face7", "Face8", "Face9", "Face10"])]
    operation.StepOver = 35
    operation.OffsetPattern = "ZigZag"
    operation.StartAt = "Center"

    tool_controller = getattr(operation, "ToolController", None)
    if tool_controller is not None:
        set_quantity(tool_controller, "HorizFeed", "500 mm/min")
        set_quantity(tool_controller, "VertFeed", "150 mm/min")
        tool = getattr(tool_controller, "Tool", None)
        if tool is not None and hasattr(tool, "Diameter"):
            set_quantity(tool, "Diameter", "5 mm")

    doc.recompute()

    post = PostProcessorFactory.get_post_processor(job, "grbl")
    post_data = post.export()
    gcode = "\n".join(section for _, section in post_data if section)
    GCODE_PATH.write_text(gcode, encoding="utf-8")

    doc.saveAs(str(DOC_PATH))

    print(f"FreeCAD document: {DOC_PATH}")
    print(f"G-code: {GCODE_PATH}")
    print(f"Pocket depths: {operation.StartDepth} -> {operation.FinalDepth}")
    print(f"Step down: {operation.StepDown}, stepover: {operation.StepOver}%")


if __name__ == "__main__":
    main()
