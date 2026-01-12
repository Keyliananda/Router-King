# Architecture

RouterKing is a FreeCAD workbench that lives entirely outside the FreeCAD core.
The design goal is to keep FreeCAD upstream clean and add a sender UI as an addon,
so the user still runs a single program (FreeCAD with RouterKing inside).

## Modules
- `RouterKing/Init.py` Minimal FreeCAD init to avoid console side effects.
- `RouterKing/InitGui.py` Workbench registration with FreeCAD GUI.
- `RouterKing/routerking_wb.py` Workbench registration and menu/toolbar.
- `RouterKing/commands.py` Command registration (toolbar/menu entries).
- `RouterKing/ui/` Dock widgets and UI views.
- `RouterKing/grbl/` GRBL transport, queue, and protocol helpers.
- `RouterKing/vendor/` Vendored deps and import helpers (pyserial fallback).
- `RouterKing/Resources/` Icons and FreeCAD resources.

## Entry points
- FreeCAD loads `Init.py` and `InitGui.py` when the workbench is discovered.
- `InitGui.py` registers `RouterKingWorkbench`, which wires toolbar/menu commands
  via `commands.register()`.
- `RK_ShowPanel` opens the dock panel through `ui/main_dock.py:show_panel()`.

## UI structure (current)
- `show_panel()` finds the FreeCAD main window, creates a `QDockWidget`, and
  inserts `RouterKingDockWidget`.
- `RouterKingDockWidget` builds:
  - Title/status labels
  - Port input and Connect button
  - Jog button row (X/Y/Z +/-)
  - Console output panel
- Connect is currently stubbed and writes to the console/FreeCAD status bar.

## GRBL sender (current)
- `grbl/sender.py` owns `GrblSender` and the serial handle.
- `connect()` raises `NotImplementedError`; `disconnect()` flips the state only.
- Serial imports resolve via `vendor.import_serial()` to use system pyserial or
  fall back to the vendored copy.

## Current behavior
1. User activates the RouterKing Panel command.
2. The dock panel opens and the Connect action logs a stub message.
3. No GRBL traffic is sent yet.

## Data flow (planned)
1. User creates CAM in FreeCAD Path and exports G-code.
2. RouterKing loads the G-code and streams it to GRBL.
3. GRBL feedback updates status, alarms, and overrides in the UI.

## Notes
- Avoid FreeCAD core patches; extend with a workbench only.
- Keep GRBL logic independent from UI to allow testing.
- InitGui may be executed without `__file__` defined; avoid relying on it.
- Packaging: use the official FreeCAD app/package plus the workbench; optional
  all-in-one DMG requires proper signing/notarization for distribution.
