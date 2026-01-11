"""FreeCAD GUI init for RouterKing."""

import os
import sys

import FreeCADGui as Gui

# InitGui is loaded as a script, so ensure the Mod parent is on sys.path.
_this_dir = os.path.dirname(__file__)
_mod_dir = os.path.dirname(_this_dir)
if _mod_dir not in sys.path:
    sys.path.insert(0, _mod_dir)

from RouterKing.routerking_wb import RouterKingWorkbench

Gui.addWorkbench(RouterKingWorkbench)
