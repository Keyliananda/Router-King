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

## All-in-one app (macOS)
This builds a self-contained `RouterKing.app` that includes FreeCAD and the workbench.

```bash
./scripts/build_app.sh --dmg /path/to/FreeCAD.dmg --unquarantine
```

The app will be created in `dist/RouterKing.app` and the DMG in `dist/RouterKing.dmg`.

To set a custom DMG name:

```bash
./scripts/build_app.sh --dmg /path/to/FreeCAD.dmg --dmg-out dist/RouterKing-1.0.dmg --unquarantine
```

Note: The bundle is ad-hoc signed. macOS may still show a one-time
"developer cannot be verified" prompt; allow it once in System Settings
or by right-clicking the app and choosing Open.

If macOS reports the app as "damaged", rebuild with the latest script;
it strips an extra metadata file and re-signs the bundle.

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
