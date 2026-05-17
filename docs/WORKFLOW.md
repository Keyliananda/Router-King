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
- For fast manual-start jobs, use the RouterKing G-Code tab flow:
  `Set Manual Start`, generate/edit a template such as a rectangular pocket,
  `Validate`, then `Show/Apply Air Run`, `Air Run`, or `Start`.
  `Show/Apply Air Run` rewrites the editor to the transformed air-run program
  without sending machine commands. `Air Run` removes spindle commands and
  clamps Z moves to the configured air height so XY can be checked without a
  plunge.
- Template G-code must stay local to the manual start point. It must not contain
  homing, probing, G10 work-offset changes, or G28/G30 return commands; those
  remain explicit machine setup actions.
- MCP machine actions and the visible RouterKing dock share one process-wide
  GRBL sender. Run machine-control actions through that shared sender so the
  dock status, console, and Agent / MCP panel stay current and the operator can
  intervene from the UI.

### G-Code viewer/editor
- The RouterKing G-Code editor and preview are the authority for the program
  that will actually be sent to GRBL. Treat the visible editor content after
  template generation, manual edits, validation, and air-run transforms as the
  source of truth for streaming.
- FreeCAD remains optional for checking geometry, CAM setup, or Path workbench
  output, but it is not the final send preview. If FreeCAD and RouterKing differ,
  validate and correct the RouterKing editor/preview before streaming.
- The preview must make XY motion, Z travel, and plunge/retract behavior clear
  enough to catch wrong origin, wrong depth, missing clearance, and unexpected
  rapid moves before a real run.
- Use the 3D/Z preview for depth-sensitive jobs. A flat XY-only preview is not
  sufficient when the job contains multiple Z levels, probing-derived starts, or
  manual-start templates.
- Use `Show/Apply Air Run` when the operator needs to inspect the transformed
  no-cut program in the editor. Use `Air Run` when the transformed program should
  be streamed with spindle commands removed and Z clamped to the configured air
  height.
- For `Manual Start`, confirm the start point, regenerate or edit the local
  template, validate, inspect the RouterKing preview, then choose air run or real
  start. Manual-start templates must not silently move the work zero.

### Viewer/editor test concept
- Parser/validator tests should cover modal state, units, absolute/relative
  moves, feed/spindle commands, unsupported commands, and line-numbered error
  reporting.
- Transform tests should prove that air-run output removes spindle commands,
  clamps unsafe Z moves to the configured air height, preserves XY intent, and
  leaves the editor with the exact program that would be streamed.
- Preview tests should use small fixture programs with known bounds and known Z
  extrema, including rapid clearance, plunge, retract, arc or segmented motion,
  and manual-start offsets.
- UI workflow tests should cover load/edit/validate/preview/start gating:
  streaming stays disabled until validation passes, `Show/Apply Air Run` does
  not send commands, `Air Run` streams only transformed G-code, and `Start`
  streams the validated editor content.
- Regression fixtures should include at least one FreeCAD-postprocessed GRBL
  file and one RouterKing-generated manual-start template so both optional CAM
  and native quick-job paths stay covered.

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
