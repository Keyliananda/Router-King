# RouterKing

RouterKing is a FreeCAD workbench that adds an integrated GRBL sender and a guided CNC/Laser workflow.
Targets are macOS and Linux with GRBL-based machines (tested with FoxAlien Masuter Pro).

Project intent:
- One program to start (FreeCAD with the RouterKing workbench).
- No external sender app required.
- Keep FreeCAD upstream (no core patches); all custom UI and machine logic lives in the addon.

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

## Single-app macOS (recommended)
Install the official FreeCAD 1.0.x app and link the workbench. You still run a single app: FreeCAD with RouterKing inside.

1. Install `FreeCAD.app` into `/Applications` (drag it from the DMG).
2. Link the workbench:
   ```bash
   ./scripts/link_addon.sh
   ```
3. Start FreeCAD and select the `RouterKing` workbench.

## All-in-one app (macOS, experimental)
This builds a self-contained `RouterKing.app` that includes FreeCAD and the workbench. It is not notarized.

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
or by right-clicking the app and choosing Open. For distribution, a
notarized Developer ID build is required.

## Dependencies
- FreeCAD 1.0.x (PySide2)
- pyserial 3.5 (vendored) for GRBL communication

## Tests
Run the test suite from the repo root:

```bash
./scripts/test.sh
```

## Update workflow
- FreeCAD: treat it as an external app; upgrade only when needed.
- RouterKing: `git pull` in this repo (no FreeCAD patches needed).

## Repo layout
- `RouterKing/` FreeCAD workbench package
- `docs/` notes and architecture
- `scripts/` helper scripts

## License
MIT
