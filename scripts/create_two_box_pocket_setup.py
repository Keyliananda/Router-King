"""Create a simple two-box FreeCAD setup for manual boolean pocket positioning."""

from __future__ import annotations

import os
import sys
from pathlib import Path


FREECAD_MOD_PATH = "/Applications/FreeCAD.app/Contents/Resources/Mod"
SCRIPT_PATH = Path(globals().get("__file__", "scripts/create_two_box_pocket_setup.py"))
REPO_ROOT = SCRIPT_PATH.resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "examples"
DOC_PATH = OUTPUT_DIR / "RK_Two_Box_5mm_Pocket_Setup.FCStd"
GCODE_PATH = OUTPUT_DIR / "RK_Two_Box_5mm_Pocket_Setup.nc"


def ensure_freecad_paths() -> None:
    if FREECAD_MOD_PATH not in sys.path and os.path.isdir(FREECAD_MOD_PATH):
        sys.path.append(FREECAD_MOD_PATH)


def set_view(obj, shape_color=None, transparency=None, visibility=True) -> None:
    view = getattr(obj, "ViewObject", None)
    if view is None:
        return
    if shape_color is not None:
        view.ShapeColor = shape_color
    if transparency is not None:
        view.Transparency = transparency
    view.Visibility = visibility


def main() -> None:
    ensure_freecad_paths()

    import FreeCAD as App
    import Path.Main.Job as PathJob
    import Path.Op.PocketShape as PocketShape
    from Path.Post.Processor import PostProcessorFactory

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument("RK_Two_Box_5mm_Pocket_Setup")

    stock = doc.addObject("Part::Box", "Werkstueck_300x200x30mm")
    stock.Label = "Werkstueck 30 x 20 x 3 cm"
    stock.Length = 300
    stock.Width = 200
    stock.Height = 30
    stock.Placement.Base = App.Vector(0, 0, 0)

    cutter = doc.addObject("Part::Box", "Boolean_Koerper_100x200x20mm")
    cutter.Label = "Boolean-Koerper 10 x 20 x 2 cm"
    cutter.Length = 100
    cutter.Width = 200
    cutter.Height = 20
    # Rotated 90 degrees around Z and centered in X/Y. Only the lower 5 mm
    # intersect the stock top, so a boolean cut creates a centered 5 mm pocket.
    cutter.Placement = App.Placement(
        App.Vector(250, 50, 25),
        App.Rotation(App.Vector(0, 0, 1), 90),
    )

    pocketed = doc.addObject("Part::Cut", "Werkstueck_mit_5mm_Tasche")
    pocketed.Label = "Werkstueck mit 5 mm Tasche"
    pocketed.Base = stock
    pocketed.Tool = cutter

    doc.recompute()

    set_view(stock, shape_color=(0.65, 0.70, 0.74), transparency=80, visibility=True)
    set_view(cutter, shape_color=(1.0, 0.18, 0.08), transparency=55, visibility=True)
    set_view(pocketed, shape_color=(0.62, 0.68, 0.72), transparency=0, visibility=True)

    # FreeCAD 1.0 enables the CAM simulator only for internal names beginning
    # with "Job"; keep the label descriptive for humans.
    job = PathJob.Create("Job", [pocketed], None)
    job.Label = "RK 5mm Pocket CAM"
    if hasattr(job, "PostProcessor"):
        job.PostProcessor = "grbl"
    if hasattr(job, "PostProcessorOutputFile"):
        job.PostProcessorOutputFile = str(GCODE_PATH)

    setup = job.SetupSheet
    setup.StartDepthExpression = "30 mm"
    setup.FinalDepthExpression = "25 mm"
    setup.StepDownExpression = "1 mm"
    setup.SafeHeightOffset = "3 mm"
    setup.ClearanceHeightOffset = "6 mm"

    operation = PocketShape.Create("Pocket_5mm", None, job)
    operation.Label = "Pocket 5mm mittig"
    operation.Base = [(pocketed, ["Face7", "Face8", "Face9", "Face10"])]
    operation.StepOver = 35
    operation.OffsetPattern = "ZigZag"
    operation.StartAt = "Center"

    tool_controller = getattr(operation, "ToolController", None)
    if tool_controller is not None:
        tool_controller.HorizFeed = "500 mm/min"
        tool_controller.VertFeed = "150 mm/min"
        tool = getattr(tool_controller, "Tool", None)
        if tool is not None and hasattr(tool, "Diameter"):
            tool.Diameter = "5 mm"

    doc.recompute()

    post = PostProcessorFactory.get_post_processor(job, "grbl")
    post_data = post.export()
    gcode = "\n".join(section for _, section in post_data if section)
    GCODE_PATH.write_text(gcode, encoding="utf-8")

    doc.saveAs(str(DOC_PATH))

    print(f"FreeCAD document: {DOC_PATH}")
    print(f"G-code: {GCODE_PATH}")
    print("Werkstueck: 300 x 200 x 30 mm at X 0..300, Y 0..200, Z 0..30")
    print("Boolean: 100 x 200 x 20 mm, rotated Z 90 deg")
    print("Boolean bounds after rotation: X 50..250, Y 50..150, Z 25..45")
    print("Intersection pocket: 200 x 100 x 5 mm, centered in X/Y")
    print("CAM pocket operation: Face7..Face10, StartDepth 30 mm, FinalDepth 25 mm")


if __name__ == "__main__":
    main()
