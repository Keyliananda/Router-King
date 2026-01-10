# Architecture

RouterKing is a FreeCAD workbench that lives entirely outside the FreeCAD core.
The design goal is to keep FreeCAD upstream clean and add a sender UI as an addon.

## Modules
- `RouterKing/routerking_wb.py` Workbench registration and menu/toolbar.
- `RouterKing/ui/` Dock widgets and UI views.
- `RouterKing/grbl/` GRBL transport, queue, and protocol helpers.

## Data flow (planned)
1. User creates CAM in FreeCAD Path and exports G-code.
2. RouterKing loads the G-code and streams it to GRBL.
3. GRBL feedback updates status, alarms, and overrides in the UI.

## Notes
- Avoid FreeCAD core patches; extend with a workbench only.
- Keep GRBL logic independent from UI to allow testing.
