"""FreeCAD GUI init for RouterKing."""

import FreeCAD as App
import FreeCADGui as Gui

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
