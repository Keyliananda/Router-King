"""FreeCAD GUI init for RouterKing."""

import FreeCAD as App
import FreeCADGui as Gui
import os

try:
    try:
        from . import routerking_wb
    except Exception:
        import routerking_wb
    Gui.addWorkbench(routerking_wb.RouterKingWorkbench())
except Exception as exc:
    App.Console.PrintError(f"RouterKing InitGui failed: {exc}\\n")

# Initialise the main-thread dispatcher *before* starting the socket server.
# This MUST happen on the Qt main thread (which InitGui.py runs on).
try:
    try:
        from .main_thread import init_dispatcher as _init_dispatcher
    except Exception:
        from main_thread import init_dispatcher as _init_dispatcher
    _dispatcher = _init_dispatcher()
    if _dispatcher is None:
        App.Console.PrintWarning(
            "RouterKing main-thread dispatcher not initialized (Qt unavailable?).\n"
        )
    else:
        App.Console.PrintMessage("RouterKing main-thread dispatcher initialized.\n")
except Exception as exc:
    App.Console.PrintWarning(f"RouterKing main-thread dispatcher failed: {exc}\\n")

# Start the MCP socket server so Claude Desktop can connect
try:
    try:
        from .mcp.socket_server import start_server as _start_mcp_server
    except Exception:
        from mcp.socket_server import start_server as _start_mcp_server
    _start_mcp_server()
except Exception as exc:
    App.Console.PrintWarning(f"RouterKing MCP socket server failed to start: {exc}\\n")


def _routerking_state_dir():
    state_dir = os.environ.get("ROUTERKING_STATE_DIR")
    if state_dir:
        return os.path.expanduser(state_dir)
    state_home = os.environ.get("XDG_STATE_HOME")
    if not state_home:
        state_home = os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(state_home, "routerking")


def _routerking_autoshow_marker_path():
    return os.path.join(_routerking_state_dir(), "autoshow_panel")


def _routerking_should_autoshow_panel():
    try:
        env_value = os.environ.get("ROUTERKING_AUTOSHOW_PANEL")
        if env_value is not None and env_value.strip().lower() not in {"", "0", "false", "no"}:
            return True
        return os.path.exists(_routerking_autoshow_marker_path())
    except Exception as exc:
        App.Console.PrintWarning(f"RouterKing autoshow marker check failed: {exc}\\n")
        return False


def _routerking_clear_autoshow_marker():
    try:
        os.unlink(_routerking_autoshow_marker_path())
    except FileNotFoundError:
        pass
    except Exception:
        pass


def _routerking_autoshow_panel():
    opened = False
    try:
        Gui.activateWorkbench("RouterKingWorkbench")
        try:
            Gui.runCommand("RK_ShowPanel", 0)
            opened = True
        except Exception:
            pass
    except Exception as exc:
        App.Console.PrintWarning(f"RouterKing workbench autoshow activation failed: {exc}\\n")
    try:
        if not opened:
            try:
                from .ui.main_dock import show_panel
            except Exception:
                from ui.main_dock import show_panel
            show_panel()
            opened = True
        try:
            Gui.updateGui()
        except Exception:
            pass
        App.Console.PrintMessage("RouterKing panel opened from restart marker.\n")
        _routerking_clear_autoshow_marker()
    except Exception as exc:
        App.Console.PrintWarning(f"RouterKing panel autoshow attempt failed: {exc}\\n")
        raise


def _routerking_qtcore():
    try:
        from PySide2 import QtCore
    except Exception:
        try:
            from PySide import QtCore
        except Exception:
            return None
    return QtCore


def _routerking_schedule_autoshow_panel():
    def _attempt(remaining):
        try:
            _routerking_autoshow_panel()
            return
        except Exception as exc:
            if remaining <= 0:
                App.Console.PrintWarning(
                    f"RouterKing panel autoshow failed after retries: {exc}\\n"
                )
                return
        if QtCore is not None:
            QtCore.QTimer.singleShot(500, lambda: _attempt(remaining - 1))

    QtCore = _routerking_qtcore()
    if QtCore is not None:
        QtCore.QTimer.singleShot(0, lambda: _attempt(20))
    else:
        _routerking_autoshow_panel()


try:
    if _routerking_should_autoshow_panel():
        _routerking_schedule_autoshow_panel()
except Exception as exc:
    App.Console.PrintWarning(f"RouterKing autoshow bootstrap failed: {exc}\\n")
