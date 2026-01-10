# RouterKing

RouterKing is a FreeCAD workbench that adds an integrated GRBL sender and a guided CNC/Laser workflow.
The goal is to keep FreeCAD upstream (no core patches) and ship all custom UI and machine logic as an addon.

## Scope (MVP)
- GRBL connect/disconnect and status polling
- Basic controls: homing, unlock, reset, jog, zero X/Y/Z
- G-code streaming with queue and ok/ALARM handling
- CNC/Laser mode switch (post processor profile)
- Setup/calibration screens (steps/mm, limits, spindle/laser params)

## Install (dev, symlink)
Run from the repo root:

```bash
./scripts/link_addon.sh
```

Then start FreeCAD and enable the `RouterKing` workbench.

## Dependencies
- FreeCAD 0.21+ (PySide2)
- pyserial 3.5 (vendored) for GRBL communication

## Update workflow
- FreeCAD: update your FreeCAD install or your upstream clone independently.
- RouterKing: `git pull` in this repo (no FreeCAD patches needed).

## Repo layout
- `RouterKing/` FreeCAD workbench package
- `docs/` notes and architecture
- `scripts/` helper scripts

## License
MIT
