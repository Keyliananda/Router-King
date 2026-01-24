# CAM/Path Workbench Setup

RouterKing expects FreeCAD CAM (or legacy Path) to generate toolpaths.
If the CAM workbench is not visible, use the steps below.

## Quick check (RouterKing)
- Open the G-Code tab.
- Click "Check CAM" to see if CAM/Path is available.
- Click "Activate CAM" to switch to the CAM/Path workbench.

## Enable a hidden workbench
1. Edit -> Preferences -> Workbenches
2. Ensure CAM or Path is not in "Disabled".
3. Restart FreeCAD if needed.

## Addon Manager fallback (older FreeCAD)
1. Tools -> Addon Manager
2. Search for "CAM" or "Path".
3. Install and restart FreeCAD.

## Python console check
Run in the FreeCAD Python console:

```python
import CAM
import Path
import FreeCADGui as Gui
Gui.activateWorkbench("CAMWorkbench")  # or "PathWorkbench"
```

## macOS app bundle path issue
If `import CAM` fails on macOS, add the modules path:

```python
import sys
sys.path.append("/Applications/FreeCAD.app/Contents/Resources/Mod")
import CAM
```
