# Dev setup

RouterKing is designed to stay independent from FreeCAD core. Keep FreeCAD upstream and update it separately.

## Option A: Installed FreeCAD
1. Install FreeCAD from the official releases.
2. Link the workbench:
   ```bash
   ./scripts/link_addon.sh
   ```
3. Launch FreeCAD and enable the RouterKing workbench.

## Option A2: All-in-one macOS app
Build a self-contained `RouterKing.app` that bundles FreeCAD and the workbench:

```bash
./scripts/build_app.sh --dmg /path/to/FreeCAD.dmg --unquarantine
```

The app will be created in `dist/RouterKing.app` and the DMG in `dist/RouterKing.dmg`.

To set a custom DMG name:

```bash
./scripts/build_app.sh --dmg /path/to/FreeCAD.dmg --dmg-out dist/RouterKing-1.0.dmg --unquarantine
```

If macOS warns about an unverified developer, allow it once via
System Settings or right-click Open.

## Option B: FreeCAD from GitHub (advanced)
1. Clone FreeCAD upstream somewhere outside this repo:
   ```bash
   git clone https://github.com/FreeCAD/FreeCAD.git
   ```
2. Follow the FreeCAD build instructions for your OS.
3. Update FreeCAD with `git pull` and rebuild as needed.
4. Keep RouterKing as a separate repo (this one) and re-link if needed.

## Notes
- RouterKing does not patch FreeCAD.
- All UI and sender logic lives inside the workbench.
- pyserial is vendored; no extra install step is required.
