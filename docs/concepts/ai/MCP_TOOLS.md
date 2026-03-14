# RouterKing MCP Tools

## Status

Der erste Implementierungslauf legt die MCP-Struktur direkt im Repo an.
Die aktuelle Verbindungsschicht nutzt vorerst einen eingebetteten Modus:

- `mcp/server/*` enthaelt die Server-seitigen Tools, Schemas und Safety-Regeln.
- `RouterKing/mcp/*` enthaelt die FreeCAD-/RouterKing-seitige Bridge.
- `mcp/server/freecad_connection.py` kapselt die Verbindungsentscheidung.

Ein spaeterer Socket-/RPC-Transport soll hinter derselben Connection-API
eingehangen werden, ohne die Tool-Module neu schneiden zu muessen.

## Aktuelle Tools

- `list_documents`
- `get_active_document`
- `get_scene_info`
- `get_selection_context`
- `capture_view`
- `routerking_list_actions`
- `routerking_apply_actions`
- `routerking_machine_connect`
- `routerking_machine_disconnect`
- `routerking_machine_request_status`
- `routerking_machine_jog`
- `routerking_machine_stream_gcode`
- `routerking_machine_stop`

## Safety

- Risikoklassen: `read`, `modify`, `machine`, `dangerous_dev`
- `machine`-Aktionen verlangen bereits jetzt `confirm=true` und `reason`
- `dangerous_dev` ist vorbereitet, aber noch nicht exponiert

