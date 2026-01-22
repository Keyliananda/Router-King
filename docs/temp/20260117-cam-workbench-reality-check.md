# CAM Workbench Reality Check

**Datum:** 2026-01-17  
**Status:** Fakten-Check abgeschlossen

---

## Die Wahrheit über FreeCAD CAM

### ✅ JA, es existiert!

**Name:** "CAM" Workbench (früher "Path" bis FreeCAD 0.21)

**Location:**
```
/Applications/FreeCAD.app/Contents/Resources/Mod/CAM/
```

**Features:**
- Job System
- Operations (Profile, Pocket, Drilling, etc.)
- Tool Library
- **GRBL Post Processor** ✓
- 34 Post Processors insgesamt

---

## Warum ist es nicht sichtbar?

### Möglichkeit 1: Workbench versteckt

**Check in FreeCAD:**
```
Edit → Preferences → Workbenches → Enabled/Disabled
```

Falls "CAM" in "Disabled" steht → Reaktivieren!

### Möglichkeit 2: FreeCAD Version zu alt

**Mindestversion für CAM:**
- FreeCAD 0.19+ (als "Path")
- FreeCAD 0.21+ (als "CAM")

**Check:**
```
Help → About FreeCAD
```

Falls < 0.19 → Updaten auf FreeCAD 1.0.x

### Möglichkeit 3: macOS App Bundle Issue

**Symptom:** Mod-Verzeichnis nicht im Suchpfad

**Fix:**
```python
# In FreeCAD Python Console:
import sys
sys.path.append('/Applications/FreeCAD.app/Contents/Resources/Mod')
import CAM
print(CAM)
```

Falls `ImportError` → FreeCAD neu installieren

---

## Wie aktiviere ich CAM Workbench?

### Schritt 1: FreeCAD öffnen

### Schritt 2: Workbench-Dropdown

**Oben in der Toolbar:**
```
[Dropdown neben FreeCAD Logo] ▼
```

Suche nach:
- **"CAM"** (FreeCAD 1.0+)
- **"Path"** (FreeCAD 0.19-0.21)

### Schritt 3: Falls nicht in Liste

**A) Preferences prüfen:**
```
Edit → Preferences → Workbenches
```

**B) Addon Manager prüfen:**
```
Tools → Addon Manager → Search "CAM"
```

**C) Python Console Test:**
```python
import CAM
import Path
```

Falls beide `ImportError` → CAM ist nicht installiert!

---

## Option: CAM manuell aktivieren

### Wenn CAM existiert aber nicht sichtbar:

**Via Python Console:**
```python
import FreeCADGui as Gui
import CAM

# Liste alle Workbenches
print(Gui.listWorkbenches())

# CAM aktivieren
Gui.activateWorkbench("CAMWorkbench")
```

---

## Falls CAM wirklich fehlt: Alternative Ansätze

### Option A: FreeCAD Path Addon (Legacy)

**URL:** https://github.com/FreeCAD/FreeCAD-Path

**Install:**
```
Tools → Addon Manager → Legacy → FreeCAD-Path
```

**Hinweis:** Nur für alte FreeCAD Versionen (<0.19)

---

### Option B: Externe CAM-Lösung in RouterKing integrieren

Da wir bereits eine Workbench haben, können wir CAM-Funktionalität direkt einbauen:

#### Variante 1: FreeCAD CAM API nutzen

**Vorteil:** Nutzt vorhandene CAM-Engine

**Code-Beispiel:**
```python
# RouterKing/cam/job.py
import CAM
import Path
from Path.Op.Profile import Profile

def create_grbl_job(shape, tool_diameter, feed_rate):
    """Create CAM job from FreeCAD shape."""
    job = CAM.Job.Create()
    job.Model = shape
    
    # Profile operation
    profile = Profile.Create(job)
    profile.Side = "Outside"
    profile.Direction = "CCW"
    
    # Export G-Code
    gcode = Path.Post.export(job, "grbl_post")
    return gcode
```

**Integration in RouterKing:**
```python
# RouterKing/ui/main_dock.py

def _on_import_dxf_cam(self):
    """Import DXF and generate G-Code via CAM API."""
    try:
        import CAM
        dxf_path = self._select_dxf_file()
        shape = self._import_dxf_shape(dxf_path)
        
        # CAM dialog
        settings = self._show_cam_settings_dialog()
        
        # Generate G-Code
        gcode = create_grbl_job(
            shape=shape,
            tool_diameter=settings["tool_diameter"],
            feed_rate=settings["feed_rate"]
        )
        
        # Load into editor
        self._gcode_edit.setPlainText(gcode)
        self._append_console("G-Code generated via CAM.")
        
    except ImportError:
        self._append_console("CAM module not available. Using simple mode.")
        self._on_import_dxf_simple()
```

---

#### Variante 2: Eigene Simple CAM Engine

**Wenn CAM wirklich nicht verfügbar:**

**Use Case:** DXF Konturen → G-Code (Laser/2D-Fräsen)

**Features:**
- Kontur-Extraktion aus DXF
- Lead-In/Lead-Out
- Multi-Pass (für CNC)
- Laser Power Control (M3/M4)

**Dependencies:**
```python
# Option 1: ezdxf (pip install ezdxf)
import ezdxf

# Option 2: FreeCAD Import API
import Import
```

**Code-Struktur:**
```
RouterKing/
  cam/
    __init__.py
    dxf_import.py      # DXF → FreeCAD Shapes
    toolpath.py        # Shape → Toolpath
    gcode_gen.py       # Toolpath → G-Code
    profiles.py        # Material/Tool Presets
```

**Beispiel `toolpath.py`:**
```python
class SimpleToolpath:
    def __init__(self, shape, tool_diameter, feed_rate):
        self.shape = shape
        self.tool_diameter = tool_diameter
        self.feed_rate = feed_rate
        self.path = []
    
    def generate_profile(self, side="outside"):
        """Generate profile toolpath."""
        # Offset shape by tool radius
        offset = self.tool_diameter / 2.0
        if side == "outside":
            offset = -offset
        
        contour = self.shape.makeOffsetShape(offset, 0.01)
        
        # Extract edges
        for edge in contour.Edges:
            self.path.extend(self._edge_to_moves(edge))
        
        return self.path
    
    def _edge_to_moves(self, edge):
        """Convert FreeCAD edge to G-Code moves."""
        moves = []
        if edge.Curve.TypeId == "Part::GeomLine":
            start = edge.Vertexes[0].Point
            end = edge.Vertexes[1].Point
            moves.append(("G1", end.x, end.y, self.feed_rate))
        elif edge.Curve.TypeId == "Part::GeomCircle":
            # Arc interpolation
            moves.extend(self._arc_to_moves(edge))
        return moves
```

---

### Option C: Wrapper für externe CAM-Tools

**RouterKing ruft externe Tools auf:**

**Unterstützte Tools:**
- **EstlCAM** (Windows, CLI verfügbar)
- **FlatCAM** (Python, CLI-Mode)
- **PyCAM** (Python, Open Source)
- **dxf2gcode** (Python, Open Source)

**Code-Beispiel:**
```python
import subprocess

def run_external_cam(dxf_path, output_path, tool="flatcam"):
    if tool == "flatcam":
        subprocess.run([
            "flatcam",
            "--headless",
            "--input", dxf_path,
            "--output", output_path,
            "--tool_diameter", "6.0",
            "--feed_rate", "1200"
        ])
    elif tool == "dxf2gcode":
        subprocess.run([
            "dxf2gcode",
            "-i", dxf_path,
            "-o", output_path
        ])
```

---

## Empfehlung: Nächste Schritte

### 1. CAM Workbench Status prüfen

**In FreeCAD Python Console:**
```python
import sys
print("\n".join(sys.path))

try:
    import CAM
    print("✅ CAM available:", CAM)
except ImportError as e:
    print("❌ CAM not available:", e)

try:
    import Path
    print("✅ Path available:", Path)
except ImportError as e:
    print("❌ Path not available:", e)

import FreeCADGui as Gui
workbenches = Gui.listWorkbenches()
print("\nAvailable Workbenches:")
for wb in workbenches:
    print(f"  - {wb}")
```

**Ergebnis bitte hier dokumentieren!**

---

### 2. Falls CAM verfügbar: API-Integration (Variante 1)

**Aufwand:** ~2-3 Tage

**Features:**
- Volle CAM-Power
- GRBL Post Processor inkludiert
- Tool Library
- Job Management

---

### 3. Falls CAM NICHT verfügbar: Simple Engine (Variante 2)

**Aufwand:** ~3-5 Tage

**Features:**
- DXF Kontur-Import
- Profile/Pocket (basic)
- Lead-In/Out
- Multi-Pass
- Laser Mode

---

### 4. Hybrid-Ansatz (empfohlen!)

**CAM verfügbar → nutze CAM API**  
**CAM nicht verfügbar → eigene Simple Engine**

**Code:**
```python
try:
    import CAM
    from .cam_integration import generate_gcode_cam
    USE_CAM = True
except ImportError:
    from .simple_cam import generate_gcode_simple
    USE_CAM = False

def generate_gcode(shape, settings):
    if USE_CAM:
        return generate_gcode_cam(shape, settings)
    else:
        return generate_gcode_simple(shape, settings)
```

---

## Test-Plan

### Test 1: CAM Import
```python
python3 -c "import sys; sys.path.insert(0, '/Applications/FreeCAD.app/Contents/Resources/lib'); import CAM; print(CAM.__file__)"
```

### Test 2: GRBL Post Processor
```python
from Path.Post.scripts import refactored_grbl_post
print(refactored_grbl_post.__file__)
```

### Test 3: Job Creation
```python
import FreeCAD
import CAM

doc = FreeCAD.newDocument()
box = doc.addObject("Part::Box", "Box")
job = CAM.Job.Create()
job.Model = box
print(job)
```

---

## Fazit

**CAM existiert in FreeCAD 1.0+!**

**Nächster Schritt:** Status-Check durchführen und entscheiden:
- Option A: CAM API Integration
- Option B: Simple Engine
- Option C: Hybrid

**Waiting for:** User Feedback nach Status-Check

---

## Status-Check Kommando

**Bitte in FreeCAD Python Console ausführen:**

```python
import sys
import FreeCADGui as Gui

print("=== FreeCAD CAM Status Check ===\n")

# Version
import FreeCAD
print(f"FreeCAD Version: {FreeCAD.Version()}\n")

# CAM Module
try:
    import CAM
    print(f"✅ CAM Module: {CAM.__file__}")
except ImportError as e:
    print(f"❌ CAM Module: {e}")

# Path Module (Legacy)
try:
    import Path
    print(f"✅ Path Module: {Path.__file__}")
except ImportError as e:
    print(f"❌ Path Module: {e}")

# Workbenches
print("\n=== Available Workbenches ===")
for wb in sorted(Gui.listWorkbenches()):
    print(f"  - {wb}")

# GRBL Post Processor
print("\n=== GRBL Post Processor ===")
try:
    from Path.Post.scripts import refactored_grbl_post
    print(f"✅ GRBL Post: {refactored_grbl_post.__file__}")
except ImportError as e:
    print(f"❌ GRBL Post: {e}")

print("\n=== End Status Check ===")
```

**Ergebnis hier einfügen:**
```
(output hier einfügen)
```
