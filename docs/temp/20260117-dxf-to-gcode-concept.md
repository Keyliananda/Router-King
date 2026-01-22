# DXF zu G-Code Integration - Konzept

**Datum:** 2026-01-17  
**Status:** Entwurf für Chief AI Review  
**Priorität:** Feature Request

---

## Problem

User möchte aus DXF-Dateien direkt G-Code generieren.  
Aktuell: RouterKing ist nur ein GRBL Sender, kein CAM-System.

---

## Analyse: 3 Implementierungs-Optionen

### Option A: FreeCAD Path Integration (empfohlen)
**Ansatz:** RouterKing nutzt FreeCAD's Path Workbench API

**Vorteile:**
- Nutzt existierende, ausgereifte CAM-Engine
- Keine eigene CAM-Logik erforderlich
- Volle Feature-Palette (Pockets, Profiles, Drilling, etc.)

**Nachteile:**
- Abhängigkeit von Path Workbench
- Komplexere Integration

**Workflow:**
```python
# Pseudo-Code
import Path
import Part

# DXF importieren
doc = FreeCAD.open("file.dxf")
shapes = doc.Objects

# Path Job erstellen
job = Path.Job.Create()
job.Model = shapes[0]

# Operation definieren (z.B. Profile)
profile = Path.Profile.Create(job)
profile.Side = "Outside"
profile.Direction = "CCW"

# G-Code generieren
gcode = Path.Post.export(job, "grbl")
```

**Entwicklungsaufwand:** ~3-5 Tage

---

### Option B: Einfache Kontur-Engine (Laser-fokussiert)
**Ansatz:** Eigene Kontur-Extraktion aus DXF, dann G0/G1 G-Code

**Vorteile:**
- Schnelle Implementierung für Laser-Anwendungen
- Unabhängig von Path Workbench
- Volle Kontrolle

**Nachteile:**
- Nur für 2D-Konturen (keine Taschen/Bohrungen)
- Keine Feed-Rate-Optimierung
- Keine Toolpath-Kompensation

**Features:**
- DXF Import (Lines, Polylines, Arcs, Circles)
- Lead-In/Lead-Out
- Laser Power Control (M3/M4/M5)
- Ramp-Down für CNC

**Entwicklungsaufwand:** ~2-3 Tage

---

### Option C: Plugin-Architektur für externe CAM
**Ansatz:** RouterKing ruft externe CAM-Tools auf

**Vorteile:**
- Keine eigene CAM-Implementierung
- User kann beste Tools verwenden

**Nachteile:**
- Plattform-abhängig
- Externe Dependencies

**Entwicklungsaufwand:** ~1-2 Tage

---

## Empfehlung

### Kurzfristig (MVP):
**Option B** - Einfache Kontur-Engine für Laser

**Begründung:**
1. Schnell umsetzbar
2. Deckt 80% der Laser-Anwendungen ab
3. Gibt User sofortigen Mehrwert
4. Keine Abhängigkeit von Path Workbench

**Workflow:**
```
1. DXF Import Button im G-Code Tab
2. Dialog:
   - Tool Diameter (0 für Laser)
   - Feed Rate
   - Plunge Rate (nur CNC)
   - Lead-In/Out Distance
   - Laser Power (M3 S1000)
3. Preview zeigt Toolpaths
4. "Generate G-Code" Button
5. G-Code landet im Editor
6. User kann anpassen und senden
```

### Langfristig:
**Option A** - Volle Path Integration

**Features:**
- Pocket Operations
- Drilling
- Adaptive Toolpaths
- Feed-Rate-Optimization
- Tool Library

---

## UI-Entwurf (Option B)

```
┌─────────────────────────────────────────────────────────┐
│                      G-Code Tab                          │
├─────────────────────────────────────────────────────────┤
│  [Load] [Save] [Import DXF] [Preview]                   │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐│
│  │  G-Code Editor                                       ││
│  │  (generated or loaded)                               ││
│  └─────────────────────────────────────────────────────┘│
│                                                          │
│  ┌─────────────────────────────────────────────────────┐│
│  │  Toolpath Preview                                    ││
│  │  (2D visualization)                                  ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘

[Import DXF] Dialog:
┌─────────────────────────────────────────────────────────┐
│  DXF to G-Code Settings                                  │
├─────────────────────────────────────────────────────────┤
│  Mode:           ○ Laser    ● CNC Router                 │
│                                                          │
│  Tool Diameter:  [6.0] mm                                │
│  Feed Rate:      [1200] mm/min                           │
│  Plunge Rate:    [300] mm/min (CNC only)                 │
│  Cut Depth:      [3.0] mm (CNC only)                     │
│  Pass Depth:     [1.0] mm (CNC only)                     │
│                                                          │
│  Laser Power:    [1000] (0-1000, M3 S value)             │
│                                                          │
│  Lead-In:        [2.0] mm                                │
│  Lead-Out:       [2.0] mm                                │
│                                                          │
│  [Generate G-Code] [Cancel]                              │
└─────────────────────────────────────────────────────────┘
```

---

## Technische Details (Option B)

### Benötigte Module:

1. **DXF Parser:**
   - Library: `ezdxf` (Python, MIT License)
   - Alternative: FreeCAD's `Import.importDXF()`

2. **Toolpath Generator:**
   - Kontur-Extraktion aus DXF Entities
   - Sortierung (minimize rapid moves)
   - Lead-In/Out Generierung
   - G-Code Formatting

3. **G-Code Template:**
```gcode
; Generated by RouterKing from DXF
G21 G90 G17         ; mm, absolute, XY plane
G0 Z5.0             ; safe Z
M3 S1000            ; spindle/laser on

; Contour 1
G0 X10.0 Y10.0      ; rapid to start
G1 Z-1.0 F300       ; plunge (CNC only)
G1 X50.0 Y10.0 F1200
G1 X50.0 Y50.0
; ... more moves

G0 Z5.0             ; retract
M5                  ; spindle/laser off
M2                  ; end program
```

---

## Offene Fragen für Chief AI

1. **Scope:** Option A (volle CAM) oder Option B (simple Konturen)?
2. **UI:** Separater "CAM" Tab oder im G-Code Tab?
3. **Library:** `ezdxf` ok oder FreeCAD API bevorzugt?
4. **Profile-Speicherung:** Material/Tool Presets in FreeCAD Preferences?
5. **Testing:** Sample DXF Dateien im Repo?

---

## Risiken

1. **DXF Kompatibilität:** Nicht alle DXF Features werden unterstützt
2. **Toolpath-Qualität:** Eigene Engine nicht so gut wie Path Workbench
3. **User-Erwartungen:** User erwartet evtl. volle CAM-Features

---

## Nächste Schritte

- [ ] Chief AI Review
- [ ] Entscheidung: Option A, B oder C?
- [ ] Prototyp: DXF Import Dialog
- [ ] Testdaten: Sample DXF Files
- [ ] Dokumentation: User Guide

---

## Alternativen (kein Code erforderlich)

**Workaround:** User nutzt FreeCAD Path Workbench manuell:

```
1. FreeCAD öffnen
2. DXF importieren
3. Path Workbench aktivieren
4. Job → New Job
5. Operations hinzufügen
6. Post Process → GRBL
7. .nc Datei exportieren
8. In RouterKing Workbench:
   - Workbench wechseln
   - G-Code Tab → Load
   - Datei laden und senden
```

**Vorteil:** Nutzt volle Path-Power, keine Entwicklung nötig  
**Nachteil:** 2 Workbenches, mehr Schritte

---

## Fazit

**Empfehlung:** Option B für MVP, später Option A für volle Features.

Dies ist eine **strukturelle Erweiterung** und erfordert Chief AI Approval.
