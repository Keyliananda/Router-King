"""Command registrations for RouterKing workbench."""

import os

import FreeCADGui as Gui


COMMANDS = [
    "RK_ShowPanel",
]


class CmdShowPanel:
    def GetResources(self):
        icon_path = os.path.join(os.path.dirname(__file__), "Resources", "icons", "routerking.svg")
        return {
            "Pixmap": icon_path,
            "MenuText": "RouterKing Panel",
            "ToolTip": "Open the RouterKing control panel",
        }

    def Activated(self):
        try:
            from .ui.main_dock import show_panel
        except ImportError:
            from ui.main_dock import show_panel

        show_panel()

    def IsActive(self):
        return True


def register():
    Gui.addCommand("RK_ShowPanel", CmdShowPanel())
