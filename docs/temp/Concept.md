# FreeCAD-AI Tool (Workbench) – Concept

## Ziel & Vision
- KI-gestuetztes FreeCAD-Add-on (Workbench), das Anwender:innen beim Modellieren unterstuetzt, typische CAD-Probleme automatisch loest (z. B. schlechte Splines -> saubere Shapes) und perspektivisch CAM-/Fraesprozesse ueberwacht und assistiert.
- Fokus: produktive Hilfe, erklaerbare Entscheidungen, klarer Nutzen in der Praxis.

Das Tool soll:
- operativ helfen ("Wie mache ich X in FreeCAD?")
- geometrisch eingreifen (Analyse & Korrektur von Modellen)
- lernend besser werden
- hardware-nah erweiterbar sein (CNC/Fraese)

## Kernidee
Kein "grosses" All-in-One-Modell, sondern:
- task-spezifische KI-Module
- klare Schnittstellen zwischen FreeCAD <-> KI <-> CAM
- lokal-first + optionale Cloud-KI

Der Fokus liegt auf Produktivitaet & Verstaendlichkeit, nicht auf akademischer KI-Komplexitaet.

## Haupt-Features (Grundkonzept)

### 1) FreeCAD-Workbench
- Eigene Workbench (Python)
- Panels / Buttons fuer KI-Aktionen
- Kontextsensitiv (arbeitet auf aktueller Auswahl)

### 2) Spline & Shape Optimierung (Core Feature)
- Analyse von:
  - Spline-Kontinuitaet (C0/C1/C2)
  - unnoetigen Kontrollpunkten
  - Knicken / Artefakten
- Automatische Vorschlaege:
  - Glaetten
  - Reduzieren
  - Neu-Approximation als saubere Kurve
- Optional:
  - "Before / After"-Vorschau
  - Undo-faehig

Erstes echtes KI-Value-Feature.

### 3) KI-Assistent (operativ)
- Chat-aehnlicher Agent:
  - "Warum schlaegt Pad fehl?"
  - "Warum ist dieser Sketch instabil?"
- Kann:
  - FreeCAD-Objekte analysieren
  - Fehlerquellen erklaeren
  - konkrete Handlungsvorschlaege geben
- Fokus: FreeCAD-Denken erklaeren, nicht nur Befehle nennen

### 4) Fortlaufendes Lernen
- Speicherung von:
  - Nutzer-Aktionen
  - akzeptierten / abgelehnten Vorschlaegen
- Ziel:
  - bessere Defaults
  - projektspezifische Optimierungen
- Datenschutz-freundlich (lokal first)

### 5) Echtzeit-Feedback-Loop
- Beim Editieren:
  - Warnungen bei instabiler Geometrie
  - Hinweise auf spaetere CAM-Probleme
- Nicht blockierend, nur assistierend

### 6) CAM / Fraesen-Integration (Phase 2+)
- Analyse von:
  - Toolpaths
  - kritischen Radien
  - Ueberfraesungen
- Vorbereitung fuer:
  - Fraesen-Ueberwachung
  - Sensor-Daten (optional)
- Langfristig:
  - KI-Agent beobachtet Prozess
  - schlaegt Anpassungen vor (kein autonomes Fraesen!)

### 7) Reporting & Nachvollziehbarkeit
- Automatische Reports:
  - Geometrie-Qualitaet
  - KI-Eingriffe
  - CAM-Risiken
- Wichtig fuer:
  - Lernen
  - Dokumentation
  - Vertrauen in KI-Entscheidungen

## Technische Architektur (High Level)

FreeCAD (Python)
- Workbench
- Zugriff auf:
  - Sketcher
  - Part
  - Path (CAM)

KI-Layer
- Regelbasierte Analyse (Baseline)
- ML-Modelle fuer:
  - Spline-Optimierung
  - Shape-Erkennung
- Optional:
  - OpenAI API (Agent, Erklaerungen)
  - lokale Modelle (spaeter)

Agent-Logik
- Task-basierte Aufrufe
- kein "freier Autopilot"
- deterministische Aktionen + KI-Vorschlaege

## Roadmap

### Phase 0 – Grundlagen
- FreeCAD Workbench Skeleton
- UI-Panel + Buttons
- Zugriff auf aktuelle Auswahl
- Logging / Debug-Modus

### Phase 1 – Spline-KI (MVP)
- Spline-Analyse (Regeln)
- einfache Glaettungs-Algorithmen
- erste KI-Vorschlaege
- Preview + Undo

Erster echter Nutzen.

### Phase 2 – KI-Assistent
- Kontext-Analyse (Sketch, Body, Errors)
- textuelle Erklaerungen
- OpenAI-Anbindung (Agent-Style)
- Prompt-Engineering auf FreeCAD-Domaene

### Phase 3 – Lernsystem
- Feedback speichern
- einfache Gewichtung ("funktioniert oft / selten")
- personalisierte Vorschlaege

### Phase 4 – CAM-Integration
- Toolpath-Analyse
- Fraes-Risiko-Checks
- Vorbereitung Hardware-Hooks

### Phase 5 – Hardware-Agent (optional)
- Fraesen-Monitoring (read-only)
- KI-gestuetzte Hinweise
- Sicherheits-first Design

## Umsetzungsschritte (konkret)
1. [x] Projektstruktur fuer die Workbench festlegen
   - Ordner fuer Workbench-Code, UI, Ressourcen, Tests
   - Basis-Konfiguration, Logging-Setup, Versionsinfo

2. [ ] FreeCAD-Workbench-Skeleton bauen
   - Workbench-Registrierung
   - Commands/Actions als Platzhalter
   - Minimaler Panel-Container

3. [x] Auswahl- und Kontextzugriff implementieren
   - Aktuelle Selektion lesen
   - Typen/Geometrie sicher extrahieren
   - Fehlertoleranz fuer ungueltige Objekte

4. [x] Analyse-Pipeline definieren
   - Ein einheitliches Analyse-Result-Format
   - Baseline-Regelpruefungen (Spline-Kontinuitaet, Knicke)

5. [x] Spline-Optimierung (MVP) implementieren
   - Glaettung und Reduktion der Kontrollpunkte
   - Neu-Approximation als Option
   - Parameter mit sinnvollen Defaults

6. [ ] Preview + Undo integrieren
   - Vorher/Nachher-Vorschau
   - Transaktionen fuer Undo/Redo
   - Nicht-destruktive Vorschau-Objekte

7. [ ] UI-Workflow fuer KI-Aktionen
   - Ergebnisliste + kurze Erklaerungen
   - "Anwenden" vs. "Verwerfen"
   - Status/Progress-Anzeige

8. [ ] Reporting/Logging ergaenzen
   - Report-Panel fuer Geometrie-Qualitaet
   - Audit-Trail der KI-Eingriffe

9. [ ] KI-Assistent vorbereiten (Phase 2)
   - Kontextsammler (Sketch, Body, Fehler)
   - Textantworten aus Regelwissen
   - Schnittstelle fuer optionale LLM-Anbindung

10. [ ] Lernsystem-Stub (Phase 3)
   - Feedback-Speicherung lokal
   - einfache Gewichtung der Vorschlaege

11. [ ] CAM-Analyse vorbereiten (Phase 4)
   - Toolpath-Parsing
   - Risiko-Checks (Radien, Ueberfraesung)

12. [ ] Tests und Qualitaet
   - Unit-Tests fuer Analyse/Optimierung
   - kleine Beispielmodelle als Fixture

13. [ ] Hardware-Agent (optional) planen
   - Read-only Monitoring (Status, Sensor-Daten)
   - Sicherheitsregeln + Alarm-Klassen
   - Simulationsmodus fuer Tests

14. [ ] Release-/Addon-Paket vorbereiten
   - Addon-Manager Metadaten + Versionsschema
   - Changelog + Migrationshinweise
   - Minimaler Setup-Guide

15. [ ] Dokumentation & Feedback-Loop
   - Quickstart + Beispielmodelle
   - Troubleshooting/FAQ
   - Feedback sammeln und Roadmap iterieren

## Philosophie
- Assistenz statt Autonomie
- erklaerbare KI
- Handwerk + Software
- KI als Werkzeug, nicht als Blackbox
