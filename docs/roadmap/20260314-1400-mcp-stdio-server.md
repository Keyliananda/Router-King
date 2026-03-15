# MCP stdio-Server fuer Claude Code

## Ziel

Claude Code soll den RouterKing MCP-Server direkt als Tool-Provider nutzen koennen. Dafuer muss der Server das MCP-Protokoll (JSON-RPC ueber stdio) sprechen und im Projekt als MCP-Server registriert sein.

## Aktueller Stand

- Alle Tool-Funktionen sind implementiert (`mcp/server/routerking_tools.py`, `machine_tools.py`, `freecad_tools.py`)
- Tool-Registry existiert in `mcp/server/main.py:build_tool_registry()`
- Schemas, Safety und Bridge sind fertig
- Es fehlt: die MCP-Protokollschicht (stdio JSON-RPC) und die Claude-Code-Registrierung

## Was zu tun ist

### 1. MCP stdio-Server implementieren

Datei: `mcp/server/stdio_server.py` (oder `main.py` erweitern)

Der Server muss folgende MCP-Methoden ueber stdin/stdout bedienen:

- `initialize` — Server-Info und Capabilities zurueckgeben
- `tools/list` — alle verfuegbaren Tools mit JSON-Schema zurueckgeben
- `tools/call` — ein Tool mit Parametern ausfuehren und Ergebnis zurueckgeben

Protokoll:

- JSON-RPC 2.0 ueber stdio (eine JSON-Zeile pro Request/Response)
- Content-Type Header wie bei LSP (`Content-Length: ...\r\n\r\n{...}`) — abhaengig vom SDK

Optionen:

- **Option A**: Python `mcp` SDK nutzen (falls als Dependency akzeptabel). Pruefe ob `pip install mcp` ein offizielles SDK liefert.
- **Option B**: Minimaler eigener stdio-Handler ohne externe Abhaengigkeit. Braucht nur ~100 Zeilen fuer init + list + call.

Empfehlung: Pruefe zuerst ob ein `mcp` Python-Package existiert und brauchbar ist. Wenn ja, nutze es. Wenn nicht, baue einen minimalen Handler.

### 2. Tool-Schemas als JSON-Schema exportieren

Jedes Tool braucht fuer `tools/list` ein vollstaendiges JSON-Schema mit:

- `name`: Tool-Name (z.B. `routerking_list_actions`)
- `description`: was das Tool tut
- `inputSchema`: JSON-Schema fuer die Parameter

Die Infos existieren schon in `ACTION_REGISTRY` und den Funktionssignaturen — sie muessen nur in JSON-Schema-Format gebracht werden.

### 3. Claude Code MCP-Konfiguration

Datei: `.claude/mcp.json` im Projekt-Root

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

Alternativ fuer Socket-Modus:

```json
{
  "mcpServers": {
    "routerking": {
      "command": "python3",
      "args": ["-m", "mcp.server.stdio_server"],
      "env": {
        "ROUTERKING_MCP_MODE": "socket",
        "ROUTERKING_MCP_HOST": "127.0.0.1",
        "ROUTERKING_MCP_PORT": "4400"
      }
    }
  }
}
```

### 4. Tests

- Test: stdio-Server antwortet auf `initialize` mit korrekter Server-Info
- Test: `tools/list` liefert alle registrierten Tools mit gueltigen JSON-Schemas
- Test: `tools/call` fuer ein einfaches read-only Tool (z.B. `routerking_list_actions`)
- Test: `tools/call` fuer unbekanntes Tool liefert Fehler

### 5. Dokumentation

- `docs/concepts/ai/MCP_TOOLS.md` aktualisieren: Abschnitt "Claude Code Integration" mit Setup-Anleitung
- Hinweis auf `.claude/mcp.json`

## Reihenfolge

1. Pruefen ob `mcp` Python-SDK existiert und nutzbar ist
2. stdio-Server implementieren
3. JSON-Schemas fuer alle Tools generieren
4. `.claude/mcp.json` anlegen
5. Testen (manuell: `echo '...' | python3 -m mcp.server.stdio_server`)
6. Tests schreiben
7. Doku aktualisieren

## Wichtige Hinweise

- Der stdio-Server laeuft als Subprozess von Claude Code — er muss sauber starten und sich ueber stdin/stdout verstaendigen
- Keine interaktiven Prompts oder Print-Ausgaben auf stdout ausser dem MCP-Protokoll
- Logging nur auf stderr
- Der Server muss auch ohne laufendes FreeCAD starten koennen (Fehler erst bei Tool-Aufruf)

## Copy-Paste Prompt fuer den naechsten Kontext

```text
Implementiere einen MCP stdio-Server fuer Claude Code.
Task-Datei: docs/roadmap/20260314-1400-mcp-stdio-server.md

Der Server soll das MCP-Protokoll (JSON-RPC ueber stdio) sprechen,
damit Claude Code die RouterKing-Tools direkt nutzen kann.

Vorhandene Infrastruktur:
- mcp/server/main.py hat build_tool_registry() mit allen Tools
- mcp/server/freecad_connection.py hat embedded + socket Modus
- Alle Tool-Funktionen sind in routerking_tools.py, machine_tools.py, freecad_tools.py

Zu tun:
1. Pruefe ob ein mcp Python-SDK nutzbar ist (pip install mcp)
2. Implementiere stdio-Server (initialize, tools/list, tools/call)
3. Generiere JSON-Schemas fuer alle Tools
4. Lege .claude/mcp.json an
5. Schreibe Tests
6. Aktualisiere MCP_TOOLS.md
```
