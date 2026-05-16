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

## Naechste Iterationen

- [ ] `routerking_cam_list_setups`: vorhandene CAM-Jobs/Setups im aktiven Dokument
  auflisten.
- [ ] `routerking_cam_list_operations`: Operationen pro Job inklusive Typ,
  Enabled-Status, Base-Geometrie und wichtigsten Properties ausgeben.
- [ ] `routerking_cam_inspect_operation`: eine Operation mit Pfad-/G-Code-Auszug
  und Warnungen inspizieren.
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

Grenze: Das Tool erzeugt noch keine Setups oder Operationen. Es beschreibt den
aktuellen Support und die empfohlene Pipeline. Explizite Setup-/Operation-CRUD-
Tools folgen in separaten, kleineren Iterationen.
