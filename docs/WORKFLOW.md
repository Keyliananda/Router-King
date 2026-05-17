# Workflow

## CNC
1. CAD export (STEP/IGES/DXF) or Blender export (STL/OBJ).
2. Import into FreeCAD.
3. Create toolpaths in the Path workbench.
4. Postprocess with the GRBL profile.
5. Connect through RouterKing **Auto Connect** before any machine status check
   or streaming attempt. Do not guess or manually select serial ports from an
   agent workflow unless the user explicitly asks for low-level debugging.
6. Send G-code via the RouterKing sender (no external sender app).

### Machine-control rule
- For real CNC runs, the canonical connection path is RouterKing Addon
  Auto Connect first, then status/validation, then stream.
- Direct `machine_connect` with a concrete `/dev/...` port is a recovery/debug
  fallback only. It must not be the default agent behavior for normal jobs.
- Never stream while the machine is not confirmed ready by RouterKing after
  Auto Connect and status validation.
- Before validation or streaming, live GRBL state from the connected controller
  is authoritative. The active WCO/G54 offset must come from the latest status
  report or GRBL coordinate parameters; `machine_profile.json` is only a
  cache/fallback for disconnected validation or missing live data.
- Before a real milling run, home all axes through RouterKing and then verify or
  restore the intended work coordinate zero. Do not treat machine home as the
  workpiece zero for CAM jobs.
- Persisted Z probe defaults for this router are: touch plate height 15 mm,
  probe feed 50 mm/min, retract 3 mm. Use these defaults unless the setup
  explicitly changes.
- For manual XY/XYZ setup after Z probing, use `machine_prepare_manual_xy` or
  the dock's `Prepare Manual XYZ` button. Both lower only Z to the configured
  manual clearance, defaulting to 10% of the touch plate height above work Z0,
  and never change X/Y.
- Optional gamepad jogging is documented in `docs/CONTROLLER_JOG.md`. Keep it
  disabled unless the RouterKing dock is connected, no stream is running, and
  the controller deadman is held.
- MCP machine actions and the visible RouterKing dock share one process-wide
  GRBL sender. Run machine-control actions through that shared sender so the
  dock status, console, and Agent / MCP panel stay current and the operator can
  intervene from the UI.

## Laser
1. CAD or vector import (DXF/SVG) into FreeCAD.
2. Laser toolpath in Path.
3. Postprocess with GRBL laser profile (M4/S output).
4. Send via RouterKing.

## Machine setup
- Steps/mm
- Limits and homing
- Spindle/laser power and feed defaults
- Target controller: GRBL (FoxAlien Masuter Pro)

## CAM/Path workbench
If CAM/Path is missing or disabled, see `docs/CAM_WORKBENCH.md`.
