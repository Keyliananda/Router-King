# RouterKing MCP Tools

## Status

Die MCP-Struktur liegt direkt im Repo:

- `mcp/server/*` enthaelt die Server-seitigen Tools, Schemas und Safety-Regeln.
- `RouterKing/mcp/*` enthaelt die FreeCAD-/RouterKing-seitige Bridge.
- `mcp/server/freecad_connection.py` kapselt die Verbindungsentscheidung.

Unterstuetzte Verbindungsmodi:

- **embedded** (Default): MCP-Bridge laeuft direkt im FreeCAD-Prozess.
- **socket**: TCP JSON-RPC-Verbindung zu einem laufenden FreeCAD mit Length-Prefixed Framing. Konfigurierbar ueber `ROUTERKING_MCP_HOST` und `ROUTERKING_MCP_PORT`.

## Server starten

```bash
python -m mcp.server.main
```

### Env-Variablen

| Variable | Default | Beschreibung |
|---|---|---|
| `ROUTERKING_MCP_MODE` | `embedded` | Verbindungsmodus (`embedded` oder `socket`) |
| `ROUTERKING_MCP_HOST` | `127.0.0.1` | Host fuer Socket-Transport |
| `ROUTERKING_MCP_PORT` | `4400` | Port fuer Socket-Transport |
| `ROUTERKING_MCP_DEV_TOOLS` | _(leer)_ | `1` / `true` / `yes` aktiviert `routerking_run_script` |

### CLI-Flags

| Flag | Wirkung |
|---|---|
| `--describe` | Manifest (verfuegbare Tools) ausgeben und beenden |
| `--ping` | FreeCAD-Bridge-Healthcheck ausfuehren und beenden |
| `--tool NAME` | Ein einzelnes Tool aufrufen |
| `--payload '{...}'` | JSON-Payload fuer `--tool` (Default: `{}`) |

## Tool-Uebersicht

### FreeCAD-Context-Tools (read)

| Tool | Beschreibung |
|---|---|
| `list_documents` | Alle offenen FreeCAD-Dokumente auflisten |
| `get_active_document` | Aktives Dokument mit Objekt-Baum laden |
| `get_scene_info` | Szene-Ueberblick (Objekte, Typen, Sichtbarkeit) |
| `get_selection_context` | Aktuelle Selektion mit Geometrie-Details |
| `capture_view` | Screenshot der aktuellen 3D-Ansicht |

### RouterKing-Action-Tools

| Tool | Beschreibung |
|---|---|
| `routerking_list_actions` | Alle registrierten Actions mit Parametern auflisten |
| `routerking_apply_actions` | Beliebige Actions ausfuehren (Batch-Schnittstelle) |

### Domain-Tools (Convenience-Wrapper)

Diese Tools kapseln haeufige Workflows als einzelnen Aufruf.

#### `routerking_cam_capabilities`

Liefert lesend, welche CAM-Unterstuetzung der aktuelle RouterKing-/FreeCAD-Kontext anbietet:

- FreeCAD/CAM/Path-Verfuegbarkeit
- unterstuetzte Operationen: `profile`, `pocket`, `drilling`
- erwartetes Operation-Schema
- Default-CAM- und Simple-Engine-Settings
- Postprocessor-Liste
- empfohlene MCP-Pipeline fuer CAM bis Maschinenvalidierung:
  erst `routerking_cam_list_setups`, dann `routerking_cam_list_operations`,
  danach mutierende CAM-Tools oder Postprocessing

```json
{}
```

#### `routerking_cam_list_setups`

Listet vorhandene CAM-Jobs/Setups im aktiven oder benannten FreeCAD-Dokument.
Risikoklasse: `read`. Das Tool erzeugt keine Jobs, Operationen oder Toolpaths.

```json
{
  "document": "Unnamed"
}
```

`document` ist optional. Ohne Angabe wird das aktive Dokument verwendet.

Die Antwort enthaelt `setups[]` mit Feldern wie:

- `id`, `name`, `label`, `type`
- `operation_count`
- `operations` (Operation-IDs)
- `path_available`, `gcode_line_count`
- `post_processor`, `output_path`
- `model`

#### `routerking_cam_list_operations`

Listet vorhandene CAM-Operationen fuer alle Setups oder fuer ein einzelnes
Setup. Risikoklasse: `read`. Das Tool recomputet nichts, erzeugt keine
Toolpaths und postprocessed keinen G-Code.

```json
{
  "setup_id": "Job001",
  "include_paths": false,
  "include_properties": true
}
```

Alle Parameter sind optional. `include_paths=true` liefert nur eine kurze
G-Code-Vorschau je Operation, keinen vollstaendigen Export.

Die Antwort enthaelt `operations[]` mit Feldern wie:

- `id`, `name`, `label`, `type`
- `operation_type`
- `setup_id`
- `enabled`
- `base`
- `path_available`, `gcode_line_count`
- `properties`
- optional `gcode_preview`

#### `routerking_cam_inspect_operation`

Inspiziert eine einzelne CAM-Operation detailliert. Risikoklasse: `read`.
Das Tool erzeugt keine Operationen, recomputet keine Toolpaths, postprocessed
keinen G-Code und veraendert kein FreeCAD-Dokument.

```json
{
  "operation_id": "Profile001",
  "setup_id": "Job001",
  "include_gcode": true,
  "gcode_lines": 30,
  "include_properties": true,
  "include_warnings": true
}
```

`operation_id` ist Pflicht. `setup_id` ist optional und hilft bei mehrfachen
Operation-Namen. `include_gcode=true` liefert nur einen begrenzten Auszug aus
`Path.toGCode`, keinen vollstaendigen Postprocess-Export.

Die Antwort enthaelt:

- `document`
- `setup_id`
- `operation` mit `id`, `name`, `label`, `operation_type`, `enabled`, `base`
- `setup`-Kontext mit Postprocessor, Output-Pfad, Modell und Operation Count
- `base_detail` mit Objekt-/Subelement-Hinweisen
- `properties` und `property_status`
- `path` mit `source`, `gcode_line_count`, `preview`, `preview_truncated`
- `diagnostics` und `warnings`

#### `routerking_analyze_selection`

Analysiert die aktuelle FreeCAD-Selektion. Risikoklasse: `read`.

```json
// Keine Parameter noetig -- arbeitet auf der aktuellen Selektion.
{}
```

#### `routerking_optimize_splines_preview`

Erstellt eine Spline-Optimierungs-Vorschau fuer die aktuelle Selektion. Risikoklasse: `modify`. Liefert automatisch einen Screenshot zurueck.

```json
// Keine Parameter noetig -- arbeitet auf der aktuellen Selektion.
{}
```

#### `routerking_generate_gcode`

Generiert G-Code aus dem aktiven Modell. Risikoklasse: `modify`.

```json
{
  "model": "Body",
  "operations": [
    {
      "type": "profile",
      "base": "Body",
      "properties": {
        "FinalDepth": -5.0,
        "StepDown": 1.0
      }
    }
  ],
  "output_path": "/tmp/part.gcode",
  "prefer_cam": true,
  "use_cam_defaults": true
}
```

Alle Parameter sind optional. Ohne Angaben werden Standardwerte verwendet.

Die direkten Generate-Tools unterstuetzen zusaetzlich die bereits vorhandenen
CAM- und Simple-Fallback-Settings:

- CAM/Path: `post_processor`, `feed_rate`, `plunge_rate`, `start_depth`,
  `final_depth`, `step_down`, `step_over`, `profile_side`,
  `profile_direction`
- Simple-Fallback: `safe_z`, `start_z`, `cut_z`, `pass_depth`, `ramp_length`,
  `lead_in`, `lead_out`, `units`, `spindle_speed`, `laser_power`,
  `start_spindle`
- Postprocessing/Validation: `machine_profile_path`

#### `routerking_cam_generate_job`

Erzeugt einen CAM-Job und exportiert G-Code. Risikoklasse: `modify`. Liefert automatisch einen Screenshot zurueck.

```json
{
  "model": "Body",
  "operations": [
    {
      "type": "pocket",
      "properties": {
        "FinalDepth": -3.0,
        "StepDown": 1.0
      }
    }
  ],
  "output_path": "/tmp/job.gcode"
}
```

Alle Parameter sind optional.

#### `routerking_dxf_generate_gcode`

Generiert Simple-CAM-G-Code aus einer DXF-Datei. Risikoklasse: `modify`, weil
optional eine G-Code-Datei geschrieben und die RouterKing-G-Code-UI aktualisiert
werden kann. Dieses Tool steuert keine Maschine.

```json
{
  "dxf_path": "/tmp/input.dxf",
  "output_path": "/tmp/output.nc",
  "use_cam_defaults": true,
  "safe_z": 5.0,
  "cut_z": -1.0,
  "pass_depth": 0.5,
  "feed_rate": 500,
  "use_freecad": false,
  "prefer_ezdxf": false
}
```

Unterstuetzt werden die Simple-Fallback-Settings sowie DXF-Import-Settings:
`deflection`, `arc_segment_angle`, `merge_tolerance`, `prefer_ezdxf`,
`use_freecad`.

#### `routerking_cam_analyze_gcode`

Analysiert G-Code auf CAM-Risiken wie niedrige Rapid-Moves, kleine Arc-Radien,
Overcut-Risiken und zu grosse Plunge-Schritte. Risikoklasse: `read`. Dieses Tool
arbeitet direkt auf G-Code-Text und benoetigt keine FreeCAD-Verbindung.

```json
{
  "gcode": "G21\nG90\nG0 Z1\nG0 X10 Y0",
  "cam_settings": {
    "safe_z_height": 3.0,
    "min_arc_radius": 0.5,
    "tool_radius": 1.0,
    "max_plunge_step": 2.0
  }
}
```

#### `routerking_cam_postprocess`

Postprocessed rohen CAM-G-Code fuer GRBL-sicheres Streaming. Risikoklasse: `read`.
Dieses Tool steuert keine Maschine und kann genutzt werden, bevor `routerking_machine_validate_gcode`
oder `routerking_machine_stream_gcode` aufgerufen wird.

```json
{
  "gcode": "G21\nG90\nG1 X10 F500",
  "machine_profile_path": "/tmp/machine_profile.json",
  "feed_rate": 500,
  "plunge_rate": 150
}
```

### Dev-Tool

#### `routerking_run_script`

Fuehrt beliebigen Python-Code im FreeCAD-Kontext aus. Risikoklasse: `dangerous_dev`.

**Sicherheitshinweis:** Dieses Tool ist standardmaessig deaktiviert. Es wird nur freigegeben, wenn `ROUTERKING_MCP_DEV_TOOLS=1` gesetzt ist. Ohne diese Variable wird jeder Aufruf sofort abgelehnt. Das Tool ist ausschliesslich fuer die Entwicklung gedacht und darf niemals in Produktionsumgebungen aktiviert werden.

```json
{
  "code": "import FreeCAD\nprint(FreeCAD.ActiveDocument.Name)"
}
```

### Machine-Tools (machine)

Alle Machine-Tools verlangen `confirm=true` und `reason` (Freitext). Sie nutzen `include_context=True`, sodass die Antwort immer den aktuellen Szene-Kontext enthaelt.

| Tool | Pflicht-Param | Optionale Params |
|---|---|---|
| `routerking_machine_connect` | `port` | `baudrate` (Default: 115200) |
| `routerking_machine_disconnect` | -- | -- |
| `routerking_machine_request_status` | -- | -- (liefert strukturierte Statusdaten) |
| `routerking_machine_jog` | `feed` | `dx`, `dy`, `dz` |
| `routerking_machine_stream_gcode` | `gcode` | -- |
| `routerking_machine_stop` | -- | -- |

Beispiel:

```json
{
  "port": "/dev/ttyUSB0",
  "baudrate": 115200,
  "confirm": true,
  "reason": "Verbindung zum Controller herstellen"
}
```

### Strukturierte Maschinen-Statusdaten

`routerking_machine_request_status` liefert in `results[].data.machine_status` strukturierte GRBL-Daten:

```json
{
  "state": "Idle",
  "machine_position": {"x": 0.0, "y": 0.0, "z": 0.0},
  "work_position": {"x": 0.0, "y": 0.0, "z": 0.0},
  "feed_speed": {"feed": 500.0, "spindle": 12000.0},
  "connected": true,
  "streaming": false,
  "paused": false,
  "stream_progress": {"sent": 0, "acked": 0, "total": 0},
  "last_error": null,
  "raw": {"state": "Idle", "MPos": "0.000,0.000,0.000", "FS": "500,12000"}
}
```

- `state`: GRBL-Zustand (Idle, Run, Hold, Alarm, etc.)
- `machine_position` / `work_position`: geparstes x/y/z oder `null` wenn nicht verfuegbar
- `feed_speed`: aktueller Vorschub und Spindeldrehzahl
- `stream_progress`: Fortschritt beim G-Code-Streaming
- `raw`: ungeparstes GRBL-Status-Dictionary fuer Debugging

## Claude Code Integration

Der MCP-Server kann direkt von Claude Code als Tool-Provider genutzt werden. Dafuer liegt die Konfiguration in `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "routerking": {
      "command": "python3",
      "args": ["-m", "mcp.server.stdio_server"],
      "cwd": "/Users/kilianvolz/Code/Router-King",
      "env": {
        "ROUTERKING_MCP_MODE": "embedded"
      }
    }
  }
}
```

Der stdio-Server spricht JSON-RPC 2.0 ueber stdin/stdout (eine JSON-Zeile pro Message) und implementiert:

- `initialize` — Server-Info und Capabilities
- `tools/list` — alle Tools mit JSON-Schema
- `tools/call` — Tool ausfuehren und Ergebnis zurueckgeben

Fuer Socket-Modus statt embedded: `ROUTERKING_MCP_MODE=socket` und `ROUTERKING_MCP_HOST`/`ROUTERKING_MCP_PORT` setzen.

Manueller Test:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python3 -m mcp.server.stdio_server
```

## Safety

- Risikoklassen: `read`, `modify`, `machine`, `dangerous_dev`
- `machine`-Aktionen verlangen `confirm=true` und `reason`
- `dangerous_dev` ist hinter `ROUTERKING_MCP_DEV_TOOLS` gegattet
- Vollstaendige Action-Registry mit Risikoklassen: siehe `WORKBENCH_API.md`
