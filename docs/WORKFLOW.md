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
