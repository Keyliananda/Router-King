# RouterKing MCP Tools

## Status

Der erste Implementierungslauf legt die MCP-Struktur direkt im Repo an.
Die aktuelle Verbindungsschicht nutzt vorerst einen eingebetteten Modus:

- `mcp/server/*` enthaelt die Server-seitigen Tools, Schemas und Safety-Regeln.
- `RouterKing/mcp/*` enthaelt die FreeCAD-/RouterKing-seitige Bridge.
- `mcp/server/freecad_connection.py` kapselt die Verbindungsentscheidung.

Ein spaeterer Socket-/RPC-Transport soll hinter derselben Connection-API
eingehangen werden, ohne die Tool-Module neu schneiden zu muessen.

## Server starten

```bash
python -m mcp.server.main
```

### Env-Variablen

| Variable | Default | Beschreibung |
|---|---|---|
| `ROUTERKING_MCP_MODE` | `embedded` | Verbindungsmodus (`embedded` ist aktuell der einzige) |
| `ROUTERKING_MCP_HOST` | `127.0.0.1` | Host fuer kuenftigen Socket-Transport |
| `ROUTERKING_MCP_PORT` | `4400` | Port fuer kuenftigen Socket-Transport |
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
| `routerking_machine_request_status` | -- | -- |
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

## Safety

- Risikoklassen: `read`, `modify`, `machine`, `dangerous_dev`
- `machine`-Aktionen verlangen `confirm=true` und `reason`
- `dangerous_dev` ist hinter `ROUTERKING_MCP_DEV_TOOLS` gegattet
- Vollstaendige Action-Registry mit Risikoklassen: siehe `WORKBENCH_API.md`
