# Workflow

## CNC
1. CAD export (STEP/IGES/DXF) or Blender export (STL/OBJ).
2. Import into FreeCAD.
3. Create toolpaths in the Path workbench.
4. Postprocess with the GRBL profile.
5. Send G-code via the RouterKing sender (no external sender app).

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
