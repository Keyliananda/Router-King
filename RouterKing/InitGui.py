"""FreeCAD GUI init for RouterKing."""

import FreeCAD as App
import FreeCADGui as Gui

try:
    import routerking_wb
    Gui.addWorkbench(routerking_wb.RouterKingWorkbench)
except Exception as exc:
    App.Console.PrintError(f"RouterKing InitGui failed: {exc}\\n")
