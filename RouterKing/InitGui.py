"""FreeCAD GUI init for RouterKing."""

import FreeCADGui as Gui

from .routerking_wb import RouterKingWorkbench

Gui.addWorkbench(RouterKingWorkbench)
