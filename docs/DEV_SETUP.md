# Dev setup

RouterKing stays independent from FreeCAD core. FreeCAD 1.0.x is the base app; RouterKing is a workbench addon.
The goal is still a single program to start: FreeCAD with RouterKing inside.

## Option A: Installed FreeCAD (recommended)
1. Install FreeCAD 1.0.x from the official releases (copy `FreeCAD.app` to `/Applications` on macOS).
2. Link the workbench:
   ```bash
   ./scripts/link_addon.sh
   ```
3. Launch FreeCAD and enable the RouterKing workbench (restart FreeCAD if it was already open).

## Option A2: All-in-one macOS app (experimental)
Build a self-contained `RouterKing.app` that bundles FreeCAD and the workbench.
This is not notarized and may be blocked by Gatekeeper unless you allow it:

```bash
./scripts/build_app.sh --dmg /path/to/FreeCAD.dmg --unquarantine
```

The app will be created in `dist/RouterKing.app` and the DMG in `dist/RouterKing.dmg`.

To set a custom DMG name:

```bash
./scripts/build_app.sh --dmg /path/to/FreeCAD.dmg --dmg-out dist/RouterKing-1.0.dmg --unquarantine
```

If macOS warns about an unverified developer, allow it once via
System Settings or right-click Open. For distribution, a notarized
Developer ID build is required.

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
