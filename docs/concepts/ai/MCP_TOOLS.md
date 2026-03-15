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
  "operations": [{"type": "profile", "depth": -5.0}],
  "output_path": "/tmp/part.gcode",
  "prefer_cam": true,
  "use_cam_defaults": true
}
```

Alle Parameter sind optional. Ohne Angaben werden Standardwerte verwendet.

#### `routerking_cam_generate_job`

Erzeugt einen CAM-Job und exportiert G-Code. Risikoklasse: `modify`. Liefert automatisch einen Screenshot zurueck.

```json
{
  "model": "Body",
  "operations": [{"type": "pocket", "depth": -3.0}],
  "output_path": "/tmp/job.gcode"
}
```

Alle Parameter sind optional.

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
