# MCP CAM Support Roadmap

## Ziel

RouterKing soll fuer MCP-Clients nicht nur "G-Code erzeugen" anbieten, sondern
den CAM-Workflow explizit unterstuetzen: Capabilities pruefen, Setup/Operationen
strukturieren, Toolpaths generieren, Ergebnisse inspizieren, postprocessen und
erst danach Maschinenvalidierung oder Streaming ausfuehren.

## Iteration 1 -- CAM-Discovery und direkte vorhandene Tools

- [x] Vorhandene CAM-Domain-Wrapper als direkte stdio-MCP-Tools bewerben:
  `routerking_generate_gcode`, `routerking_cam_generate_job`,
  `routerking_cam_postprocess`.
- [x] `routerking_cam_capabilities` als read-only MCP-Tool einfuehren.
- [x] Operation-Payload in der Doku auf `type/base/properties` klarziehen.
- [x] Tests fuer Tool-Schema/Registry-Konsistenz und CAM-Wrapper ergaenzen.

## Iteration 2 -- CAM-Projektinspektion

- [x] `routerking_cam_list_setups`: vorhandene CAM-Jobs/Setups im aktiven oder
  benannten Dokument read-only auflisten.
- [x] `routerking_cam_list_operations`: Operationen pro Setup inklusive Typ,
  Enabled-Status, Base-Geometrie, Path-Status und wichtigen Properties read-only
  ausgeben.
- [x] Beide Tools als side-effect-freie Inspektionsschritte vor mutierenden
  CAM-Aktionen dokumentieren.
- [x] Tests fuer Bridge-Serializer, Wrapper und stdio-Schemas ergaenzen.

## Naechste Iterationen

## Iteration 3 -- Einzelne CAM-Operation inspizieren

- [x] `routerking_cam_inspect_operation`: eine Operation mit Setup-Kontext,
  Base-Details, Properties, Path-/G-Code-Auszug und Warnungen read-only
  inspizieren.
- [x] Das Tool als side-effect-frei dokumentieren: keine Operationserzeugung,
  kein Recompute, kein Postprocess, keine Dokumentveraenderung.
- [x] Schema, Wrapper/Bridge und Tests ergaenzen.

## Iteration 4 -- Vorhandene Generate-Parameter direkt via MCP

- [x] Bestehende CAM/Path-Settings aus `CamJobSettings` direkt im Schema fuer
  `routerking_generate_gcode` und `routerking_cam_generate_job` anbieten:
  Postprocessor, Feed/Plunge, Tiefen, Stepdown, Profile Side/Direction.
- [x] Bestehende Simple-Fallback-Settings direkt im Schema anbieten:
  Safe/Start/Cut Z, Pass Depth, Ramp, Lead-in/out, Units, Spindle/Laser.
- [x] `machine_profile_path` fuer vorhandenes GRBL-Postprocessing in den
  Generate-Tools direkt erlauben.
- [x] Wrapper-Tests fuer die Parameterweitergabe ergaenzen.

## Readiness fuer bereits vorhandene CAM-Features

- [x] CAM/Path-Hybrid-Generate per MCP sichtbar.
- [x] Simple-Fallback-Generate per MCP parametrierbar.
- [x] CAM-Postprocess per MCP sichtbar.
- [x] CAM-Projektinspektion per MCP sichtbar.
- [x] CAM-G-Code-Analyse als direktes MCP-Tool anbieten.
- [x] DXF-to-GCode als direktes MCP-Tool anbieten.
- [x] CAM-Operation-Expressions fuer explizite Tiefen/Zustellungen loesen,
  damit `step_down` nicht vom Werkzeugdurchmesser ueberschrieben wird.
- [x] Konservatives Bamboo-Pocket-Preset fuer kleine GRBL-Fraese anbieten.
- [ ] Generate-Ergebnisse strukturierter zurueckgeben (`engine`, `output_path`,
  `warnings`, optional `job_id`).
- [ ] CAM-Workbench-Status/Aktivierung als eigene MCP-Diagnose anbieten.

## Naechste Iterationen

- [ ] `routerking_cam_create_setup`: CAM-Job/Setup ohne sofortigen Postprocess
  erzeugen.
- [ ] `routerking_cam_create_operation`: Profile/Pocket/Drilling-Operation an ein
  Setup haengen.
- [ ] `routerking_cam_generate_toolpaths`: Job/Operationen recomputen und Path-
  Status zurueckgeben, ohne direkt zu posten.
- [ ] `routerking_cam_postprocess` erweitern, sodass optional ein Setup oder
  Operationen statt rohem `gcode` verarbeitet werden koennen.
- [ ] Wichtige Maschinen-Tools als direkte MCP-Tools nachziehen:
  `feed_hold`, `resume`, `home`, `read_settings`, `identify`, `calculate_offset`.

## Feature-Erklaerung

`routerking_cam_capabilities` ist ein lesendes Diagnose- und Planungswerkzeug fuer
Agenten. Vor CAM-Arbeit kann der Agent damit pruefen, ob FreeCAD, GUI und CAM/Path
im aktuellen Kontext verfuegbar sind, welche Operationstypen RouterKing aktuell
unterstuetzt und welche Default-Werte fuer CAM und Simple-Fallback gelten.

`routerking_cam_list_setups` und `routerking_cam_list_operations` ergaenzen diese
Planung um Projektinspektion. Agenten koennen damit vorhandene Jobs, Operationen,
Base-Geometrie, Enabled-Status, relevante Properties und Path/G-Code-Status
erkennen, bevor sie Setups oder Operationen veraendern.

`routerking_cam_inspect_operation` vertieft diese Inspektion fuer eine einzelne
Operation. Es liefert Setup-Kontext, Base-Details, Property-Abdeckung,
begrenzte Path.toGCode-Auszugdaten und Diagnosewarnungen, ohne Toolpaths zu
recomputen oder G-Code zu posten.

Grenze: Das Tool erzeugt noch keine Setups oder Operationen. Es beschreibt den
aktuellen Support und die empfohlene Pipeline. Explizite Setup-/Operation-CRUD-
Tools folgen in separaten, kleineren Iterationen.
