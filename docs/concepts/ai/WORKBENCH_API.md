# RouterKing Workbench API

Mapping zwischen MCP-Tools und der internen ACTION_REGISTRY.

## Architektur

```
MCP-Tool  -->  routerking_apply_actions()  -->  ACTION_REGISTRY  -->  execute_actions()
```

Viele Domain-Tools (`routerking_generate_gcode`, `routerking_cam_generate_job`,
`routerking_cam_postprocess`, etc.) sind Convenience-Wrapper, die intern
`routerking_apply_actions` mit einem vordefinierten Action-Payload aufrufen.
Machine-Tools gehen denselben Weg, setzen aber zusaetzlich `include_context=True`.

Einige read-only CAM-MCP-Tools gehen direkt auf Bridge-Methoden, weil sie keine
Actions ausfuehren und keine Transaktion benoetigen:

- `routerking_cam_capabilities`
- `routerking_cam_list_setups`
- `routerking_cam_list_operations`
- `routerking_cam_inspect_operation`

## Risikoklassen

| Klasse | Bedeutung | Anforderung |
|---|---|---|
| `read` | Nur lesend, keine Seiteneffekte | Keine |
| `modify` | Aendert Dokument oder erzeugt Dateien | Wird in einer `DocumentTransaction` ausgefuehrt (Rollback bei Fehler) |
| `machine` | Steuert physische Hardware (GRBL) | `confirm=true` und `reason` (Freitext) muessen gesetzt sein |
| `dangerous_dev` | Beliebiger Code im FreeCAD-Kontext | `ROUTERKING_MCP_DEV_TOOLS=1` muss als Env-Variable gesetzt sein |

### Confirm-Regeln fuer `machine`-Actions

Jeder Aufruf einer `machine`-Action wird von `validate_machine_confirmation` geprueft:

1. `confirm` muss `true` sein -- sonst Ablehnung.
2. `reason` muss ein nicht-leerer String sein -- sonst Ablehnung.

Beide Fehler werden als strukturierte Fehlermeldungen zurueckgegeben; die Action wird nicht ausgefuehrt.

## ACTION_REGISTRY -- Vollstaendige Referenz

### Geometrie-Erstellung (modify)

| Action | Beschreibung | Pflicht | Optional |
|---|---|---|---|
| `create_part_box` | Part::Box erzeugen | `length`, `width`, `height` | `name` |
| `create_part_cylinder` | Part::Cylinder erzeugen | `radius`, `height` | `name` |
| `create_part_sphere` | Part::Sphere erzeugen | `radius` | `name` |

### Sketcher (modify)

| Action | Beschreibung | Pflicht | Optional |
|---|---|---|---|
| `create_sketch` | Sketch-Objekt erzeugen | -- | `name` |
| `add_rectangle` | Rechteck in Sketch einfuegen | `width`, `height` | `sketch`, `x`, `y` |
| `add_circle` | Kreis in Sketch einfuegen | `radius` | `sketch`, `x`, `y` |

### Dokument-Manipulation (modify)

| Action | Beschreibung | Pflicht | Optional |
|---|---|---|---|
| `delete_object` | Objekt loeschen | `name` | -- |
| `translate_object` | Objekt verschieben | `name` | `dx`, `dy`, `dz` |
| `set_visibility` | Sichtbarkeit setzen | `name`, `visible` | -- |

### Analyse (read)

| Action | Beschreibung | Pflicht | Optional |
|---|---|---|---|
| `analyze_selection` | Aktuelle Selektion analysieren | -- | -- |

### CAM / G-Code (modify)

| Action | Beschreibung | Pflicht | Optional |
|---|---|---|---|
| `optimize_splines_preview` | Spline-Optimierungs-Vorschau | -- | -- |
| `generate_gcode` | G-Code generieren | -- | `model`, `operations`, `output_path`, `prefer_cam`, `use_cam_defaults` |
| `cam_generate_job` | CAM-Job erzeugen und G-Code exportieren | -- | `model`, `operations`, `output_path`, `prefer_cam`, `use_cam_defaults` |
| `dxf_generate_gcode` | Simple-CAM-G-Code aus DXF erzeugen | `dxf_path` | `output_path`, `update_ui`, Simple-CAM-Settings, DXF-Import-Settings |
| `cam_postprocess` | Rohes CAM-G-Code fuer GRBL nachbearbeiten | `gcode` | `machine_profile_path`, `feed_rate`, `plunge_rate` |

### Machine-Steuerung (machine)

Alle Actions in dieser Gruppe verlangen `confirm` und `reason`.

| Action | Beschreibung | Pflicht | Optional |
|---|---|---|---|
| `machine_connect` | GRBL-Controller verbinden | `port` | `baudrate`, `confirm`, `reason` |
| `machine_disconnect` | GRBL-Controller trennen | -- | `confirm`, `reason` |
| `machine_send_line` | Einzelne G-Code-Zeile senden | `line` | `confirm`, `reason` |
| `machine_stream_file` | G-Code-Datei streamen | `path` | `confirm`, `reason` |
| `machine_stream_gcode` | G-Code-Text streamen | `gcode` | `confirm`, `reason` |
| `machine_feed_hold` | Maschinenbewegung pausieren | -- | `confirm`, `reason` |
| `machine_resume` | Maschinenbewegung fortsetzen | -- | `confirm`, `reason` |
| `machine_stop` | Streaming und Bewegung stoppen | -- | `confirm`, `reason` |
| `machine_soft_reset` | GRBL Soft-Reset | -- | `confirm`, `reason` |
| `machine_request_status` | Maschinenstatus abfragen | -- | `confirm`, `reason` |
| `machine_jog` | Maschine relativ bewegen | `feed` | `dx`, `dy`, `dz`, `confirm`, `reason` |
