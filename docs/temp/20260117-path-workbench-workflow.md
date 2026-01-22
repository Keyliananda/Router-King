# FreeCAD Path Workbench - Schnellstart für DXF → G-Code

**Datum:** 2026-01-17  
**Ziel:** DXF in G-Code umwandeln für GRBL (RouterKing)

---

## Voraussetzungen

- FreeCAD 1.0.x oder neuer
- DXF-Datei mit 2D-Konturen
- RouterKing Workbench installiert

---

## Workflow: DXF → G-Code

### 1. DXF importieren

```
File → Open → deine-datei.dxf
```

**Hinweis:** FreeCAD importiert DXF als Part-Objekte (Lines, Arcs, etc.)

---

### 2. Path Workbench aktivieren

**Im Workbench-Dropdown (oben, neben dem FreeCAD-Logo):**
```
[Dropdown] → "Path" auswählen
```

Jetzt siehst du die Path-Toolbar und das Path-Menü.

---

### 3. Job erstellen

**Path → Job → New Job** (oder Toolbar-Icon)

**Job Setup Dialog:**
```
┌─────────────────────────────────────────────────────────┐
│  Job                                                     │
├─────────────────────────────────────────────────────────┤
│  Model:                                                  │
│    [Select Model] ← Klick und wähle deine DXF-Geometrie │
│                                                          │
│  Output:                                                 │
│    Post Processor: [grbl_post] ← WICHTIG!               │
│    Output File: /path/to/output.nc                       │
│                                                          │
│  Setup:                                                  │
│    Stock:                                                │
│      From Base: ✓                                        │
│      X: [auto]  Y: [auto]  Z: [5.0] mm                   │
│                                                          │
│  Tools:                                                  │
│    [Tool Library] → Tool auswählen oder erstellen        │
│                                                          │
│  [OK] [Cancel]                                           │
└─────────────────────────────────────────────────────────┘
```

**Wichtig:**
- **Post Processor:** Muss `grbl_post` sein (für GRBL-kompatiblen G-Code)
- **Model:** Deine importierte DXF-Geometrie auswählen

---

### 4. Tool (Fräser/Laser) definieren

**Im Job-Dialog → Tools → Tool Library:**

**Für CNC:**
```
Name:     6mm Endmill
Type:     EndMill
Diameter: 6.0 mm
Length:   50.0 mm
```

**Für Laser:**
```
Name:     Laser
Type:     Laser (oder EndMill mit Diameter = 0.1 mm)
Diameter: 0.1 mm
```

**[Add to Job]** klicken.

---

### 5. Operation hinzufügen

**Wichtigste Operations:**

#### A) Profile (Außenkontur schneiden)
```
Path → Profile
```

**Settings:**
- **Base Geometry:** Kanten/Faces auswählen
- **Side:** Outside (Außen), Inside (Innen), or On (Mitte)
- **Direction:** CW (Clockwise) oder CCW (Counter-Clockwise)
- **Depth:**
  - Start Depth: 0 mm
  - Final Depth: -3.0 mm (negativ = runter)
  - Step Down: 1.0 mm (pro Pass)

#### B) Pocket (Tasche ausfräsen)
```
Path → Pocket Shape
```

**Settings:**
- **Base Geometry:** Face auswählen (geschlossene Fläche)
- **Pattern:** ZigZag, Offset, Spiral
- **Step Over:** 40-60% des Tool-Durchmessers

#### C) Drilling (Bohren)
```
Path → Drilling
```

**Settings:**
- **Base Geometry:** Kreise oder Punkte auswählen
- **Peck Depth:** 1.0 mm (schrittweise bohren)

---

### 6. Toolpath berechnen

**Nach jeder Operation:**
```
Rechtsklick auf Operation → Recompute
```

Im 3D-View siehst du jetzt die berechneten Toolpaths (grüne/rote Linien).

---

### 7. G-Code exportieren

**Path → Post Process** (oder Job → Post Process)

**Dialog:**
```
┌─────────────────────────────────────────────────────────┐
│  Post Process                                            │
├─────────────────────────────────────────────────────────┤
│  Post Processor: [grbl_post]                             │
│  Output File:    [Browse...] → output.nc                 │
│  Arguments:      (leer lassen)                           │
│                                                          │
│  [OK] [Cancel]                                           │
└─────────────────────────────────────────────────────────┘
```

**[OK]** → G-Code wird als `.nc` Datei gespeichert.

---

### 8. In RouterKing laden

**Zurück zu RouterKing Workbench:**
```
1. Workbench-Dropdown → "RouterKing"
2. RouterKing Panel öffnen (Toolbar-Icon)
3. Tab "G-Code" wählen
4. [Load] klicken → output.nc auswählen
5. [Preview] prüfen
6. [Start] zum Senden an GRBL
```

---

## Typische Einstellungen für GRBL

### Feeds & Speeds (Beispiel: Sperrholz 10mm)

**Tool:** 6mm Upcut Endmill

**Speeds:**
- **Cutting Feed Rate:** 800-1200 mm/min
- **Plunge Rate:** 200-400 mm/min
- **Rapid (G0):** GRBL Max (meist 3000-5000 mm/min)

**Depths:**
- **Step Down:** 1.5-2.0 mm (pro Pass)
- **Final Depth:** -10.0 mm (durch Material)

**Spindle/Laser:**
- **CNC Spindle:** M3 S18000 (18000 RPM)
- **Laser:** M3 S1000 (0-1000 Power Range)

---

## Laser-spezifische Settings

**Für Laser-Schnitt:**

**In Path Job → Tool:**
```
Type: Laser
Diameter: 0.1 mm (sehr dünn, da Laser keinen Radius hat)
```

**In Post Processor:**
- GRBL Post muss `M3` (Laser On) und `M5` (Laser Off) ausgeben
- `S` Parameter = Laser Power (0-1000)

**Beispiel G-Code:**
```gcode
G21 G90          ; mm, absolute
M3 S800          ; Laser on, 80% power
G0 X10 Y10       ; rapid to start
G1 X50 Y10 F1200 ; cut
G1 X50 Y50
M5               ; Laser off
```

---

## Troubleshooting

### Problem: "No valid shapes selected"
**Lösung:** DXF-Import hat keine geschlossenen Konturen erstellt
- Im Part Workbench: `Part → Create Shape from Wire`
- Oder Konturen manuell verbinden

### Problem: "Post processor not found"
**Lösung:** GRBL Post fehlt
- Preferences → Path → Post Processors
- Path prüfen: `/Applications/FreeCAD.app/Contents/Resources/Mod/Path/PathScripts/post/`
- Falls `grbl_post.py` fehlt: FreeCAD neu installieren

### Problem: G-Code startet nicht bei Z=0
**Lösung:** Job Setup → Geometry → Heights anpassen
- **Safe Height:** 5.0 mm (sicherer Abstand)
- **Clearance Height:** 3.0 mm
- **Start Depth:** 0.0 mm

---

## Weiterführende Ressourcen

- FreeCAD Path Doku: https://wiki.freecad.org/Path_Workbench
- GRBL Post Processor: https://github.com/grbl/grbl/wiki
- Feeds & Speeds Calculator: https://www.cutter-shop.com/speeds-feeds-calculator/

---

## Schnell-Checkliste

- [ ] DXF importiert
- [ ] Path Workbench aktiviert
- [ ] Job erstellt (Post: grbl_post)
- [ ] Tool definiert
- [ ] Operation erstellt (Profile/Pocket/Drilling)
- [ ] Toolpath berechnet (Recompute)
- [ ] G-Code exportiert (.nc)
- [ ] In RouterKing geladen
- [ ] Preview geprüft
- [ ] Maschine gehomed
- [ ] Start gedrückt

---

**Viel Erfolg!** 🎯
