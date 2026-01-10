"""RouterKing workbench definition."""

import os

import FreeCADGui as Gui

from . import commands


class RouterKingWorkbench(Gui.Workbench):
    MenuText = "RouterKing"
    ToolTip = "GRBL sender and CNC/Laser workflow for FreeCAD"
    Icon = os.path.join(os.path.dirname(__file__), "Resources", "icons", "routerking.svg")

    def Initialize(self):
        commands.register()
        self.appendToolbar("RouterKing", commands.COMMANDS)
        self.appendMenu("RouterKing", commands.COMMANDS)

    def Activated(self):
        # Keep activation light; user can open the panel via the toolbar.
        pass

    def Deactivated(self):
        pass
