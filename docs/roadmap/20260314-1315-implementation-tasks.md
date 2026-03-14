# Implementation Tasks 2026-03-14 13:15

## Status 2026-03-14

Bereits umgesetzt in dieser ersten Runde:

- Task Paket 1: Repo-Struktur fuer `mcp/server` und `RouterKing/mcp` angelegt, inkl. Einstiegspunkt in `mcp/server/main.py`
- Task Paket 2: `FreeCADConnection` mit konfigurierbarem Embedded-Mode und `ping()` vorhanden
- Task Paket 3: Bridge, Kontext-, Screenshot- und Transaction-Helfer unter `RouterKing/mcp/` vorhanden
- Task Paket 4: `list_documents`, `get_active_document`, `get_scene_info`, `get_selection_context`, `capture_view` implementiert
- Task Paket 5: `routerking_list_actions` und `routerking_apply_actions` mit Registry-Validierung implementiert
- Task Paket 7: Baseline-Safety fuer Risikoklassen sowie `confirm`/`reason` bei Maschinenaktionen implementiert
- Task Paket 8: erste Machine-Wrapper angelegt, auf bestehende RouterKing-Aktionen gemappt
- Task Paket 10: Basistests fuer Schemas, Bridge und Safety implementiert

Teilweise begonnen:

- Task Paket 11: erste MCP-Tool-Doku in `docs/concepts/ai/MCP_TOOLS.md`

Noch offen:

- Task Paket 6: spezialisierte RouterKing-Domain-Tools
- Task Paket 8: vollstaendige maschinennahe Statusrueckgaben und robustere Laufzeitintegration
- Task Paket 9: optionaler Dev-Fallback
- Task Paket 11: ausfuehrlichere Start-/Nutzungsdokumentation

## Scope

Dieses Dokument zerlegt den MCP-/FreeCAD-/RouterKing-MVP aus `docs/roadmap/20260314-1300.md` in konkrete Implementierungsarbeit.
Es ist als Startpunkt fuer einen neuen Arbeitskontext gedacht.

## Ziel

Am Ende der ersten Umsetzungsrunde soll ein lokaler MCP-Server vorhanden sein, der:

- mit laufendem FreeCAD spricht
- RouterKing-Kontext lesen kann
- bestehende RouterKing-Aktionen ausloesen kann
- Screenshots oder strukturiertes Text-Feedback zurueckgibt
- riskante Maschinenaktionen mit Confirm absichert

## Entscheidungsrahmen

### Technische Leitentscheidung

Wir bauen nicht zuerst einen komplett eigenen MCP-Server from scratch, sondern orientieren uns eng an einem Fork von `neka-nat/freecad-mcp`.

### Pragmatische Arbeitsweise

- Read-only Tools zuerst
- dann RouterKing Action Adapter
- dann CAM/G-Code
- Maschinensteuerung zuletzt
- `run_script` nicht als erster Pfad

## Erwartete Ergebnisstruktur

Es gibt zwei moegliche Integrationsformen.
Fuer den ersten Implementierungslauf ist Variante A bevorzugt.

### Variante A: MCP-Code direkt im RouterKing-Repo

```text
RouterKing/
docs/
mcp/
  server/
    __init__.py
    main.py
    freecad_connection.py
    freecad_tools.py
    routerking_tools.py
    machine_tools.py
    schemas.py
    safety.py
RouterKing/mcp/
  __init__.py
  bridge.py
  context.py
  screenshots.py
  transactions.py
tests/
  test_mcp_schemas.py
  test_routerking_mcp_bridge.py
  test_routerking_mcp_safety.py
```

### Variante B: separater Fork, spaeter Rueckintegration

Wenn zuerst in einem separaten Fork gestartet wird, soll trotzdem dieselbe logische Modulstruktur verwendet werden.

## Task Paket 1: Baseline und Architektur-Fixierung

### Ziel

Die Repo- und Modulstruktur festlegen, damit die Folgearbeit nicht in Provisorien entgleist.

### Tasks

1. MCP-Integrationsvariante festlegen:
   - direkt in diesem Repo
   - oder in separatem Fork mit spaeterer Rueckintegration
2. Zielstruktur fuer `mcp/server` anlegen.
3. Zielstruktur fuer `RouterKing/mcp` anlegen.
4. Kurz dokumentieren, welche Teile aus einem Upstream-Fork uebernommen und welche RouterKing-spezifisch sind.

### Deliverables

- leere oder minimale Modulstruktur
- kurzer Architekturhinweis im Code oder in Doku

### Done-Kriterium

- Es gibt einen klaren Einstiegspunkt fuer den Server und einen klaren Einstiegspunkt auf RouterKing-Seite.

## Task Paket 2: FreeCAD Connection Layer

### Ziel

Eine klare Verbindungsschicht zwischen MCP-Server und laufendem FreeCAD schaffen.

### Datei-Ziele

- `mcp/server/freecad_connection.py`
- optional Konfigurationswerte in `mcp/server/main.py` oder `mcp/server/schemas.py`

### Aufgaben

1. Verbindungsklasse fuer das laufende FreeCAD definieren.
2. Host/Port lokal konfigurierbar machen.
3. Health-Check einfuehren:
   - `ping()`
   - klare Fehlermeldung, wenn FreeCAD/Bridge nicht erreichbar ist
4. Rueckgabeformat fuer FreeCAD-Antworten normalisieren:
   - `success`
   - `message`
   - `data`
   - `errors`

### Wichtige Regeln

- kein stilles Verschlucken von Fehlern
- keine direkte Vermischung von MCP-Tool-Code und Transportcode
- Verbindungsfehler muessen fuer den Agenten textlich klar erkennbar sein

### Done-Kriterium

- Der MCP-Server kann FreeCAD-Verbindung pruefen und einen klaren Status zurueckliefern.

## Task Paket 3: RouterKing Bridge im Addon

### Ziel

Die RouterKing-seitige Bruecke schaffen, die bestehende `ai/actions.py`-Logik kontrolliert nach aussen exponiert.

### Datei-Ziele

- `RouterKing/mcp/bridge.py`
- `RouterKing/mcp/context.py`
- `RouterKing/mcp/screenshots.py`
- `RouterKing/mcp/transactions.py`

### Aufgaben

1. `bridge.py`
   - zentrale Einstiegspunkte definieren
   - Aufruf von `RouterKing/ai/actions.py` kapseln
   - Fehler in strukturierte Antworten umformen
2. `context.py`
   - aktives Dokument lesen
   - Auswahl lesen
   - wichtige Modellinfos extrahieren
   - falls moeglich Skizzenstatus/Fehler/aktive Objekte sammeln
3. `screenshots.py`
   - Screenshot-Helfer fuer aktuelle 3D-Ansicht
   - sauberer Fallback, wenn die aktuelle Ansicht keine Screenshots unterstuetzt
4. `transactions.py`
   - einfacher Transaction-Rahmen fuer aendernde Aktionen
   - `open`
   - `commit`
   - `abort`

### Done-Kriterium

- RouterKing hat eine interne, saubere MCP-taugliche API-Schicht, ohne dass der Server direkt ungeordnet in `ai/actions.py` greift.

## Task Paket 4: Read-only MCP Tools

### Ziel

Zuerst alle Kontexte und Rueckmeldungen lesbar machen.

### Datei-Ziele

- `mcp/server/freecad_tools.py`
- `mcp/server/schemas.py`

### Erste Tools

1. `list_documents`
2. `get_active_document`
3. `get_scene_info`
4. `get_selection_context`
5. `capture_view`

### Anforderungen pro Tool

- klare Tool-Beschreibung
- stabile JSON-Parameter
- einheitliche Textantwort
- wo sinnvoll zusaetzliche strukturierte Daten

### Beispiel-Rueckgabe fuer `get_selection_context`

```json
{
  "success": true,
  "data": {
    "document": "ExampleDoc",
    "selection_count": 1,
    "selected_objects": [
      {
        "name": "Pad",
        "label": "Pad",
        "type": "PartDesign::Pad"
      }
    ]
  },
  "errors": []
}
```

### Done-Kriterium

- Der Assistent kann das aktuelle FreeCAD-/RouterKing-Arbeitsumfeld lesen, ohne irgendetwas zu veraendern.

## Task Paket 5: RouterKing Tool Registry

### Ziel

Dem Assistenten eine explizite Liste offiziell unterstuetzter RouterKing-Faehigkeiten geben.

### Datei-Ziele

- `mcp/server/routerking_tools.py`
- optional Hilfsdaten in `mcp/server/schemas.py`

### Zu implementierende Tools

1. `routerking_list_actions`
2. `routerking_apply_actions`

### Aufgaben

1. `routerking_list_actions`
   - baut auf der bestehenden RouterKing-Action-Liste auf
   - liefert pro Action:
     - Name
     - Kurzbeschreibung
     - Pflichtparameter
     - optionale Parameter
     - Risikoklasse
2. `routerking_apply_actions`
   - akzeptiert eine oder mehrere Actions
   - validiert Eingaben
   - fuehrt sie ueber die Bridge aus
   - sammelt Ergebnisse
   - haengt aktualisierten Kontext an
   - haengt Screenshot an, wenn angefordert oder sinnvoll

### Wichtige Zusatzregeln

- keine ungepruefte Action-Passthrough-Schnittstelle
- Action-Namen muessen gegen eine bekannte Registry validiert werden
- Rueckgabe pro Action separat auflisten

### Done-Kriterium

- Ein Agent kann mindestens einfache Geometrieaktionen wie `create_part_box` und `create_sketch` sauber ausloesen.

## Task Paket 6: Spezialisierte RouterKing Tools

### Ziel

Die fuer RouterKing wichtigen Domain-Aktionen zusaetzlich als gut benannte Tools freilegen.

### Tools

1. `routerking_analyze_selection`
2. `routerking_optimize_splines_preview`
3. `routerking_generate_gcode`
4. `routerking_cam_generate_job`

### Aufgaben

1. Diese Tools als klare Wrapper ueber bestehende Action-Handler bauen.
2. Rueckgaben fuer den Agenten verstaendlich machen:
   - was wurde analysiert
   - was wurde erzeugt
   - wo liegt eine Ausgabedatei
   - welche Warnungen gab es
3. Wenn moeglich Screenshots oder Folgekontext anhaengen.

### Done-Kriterium

- Der Assistent kann euren fachlichen Mehrwert nutzen, nicht nur Primitive zeichnen.

## Task Paket 7: Safety Layer

### Ziel

Riskante Aktionen von Anfang an sauber absichern.

### Datei-Ziele

- `mcp/server/safety.py`
- Teile in `mcp/server/machine_tools.py`

### Regeln

1. Risikoklassen definieren:
   - `read`
   - `modify`
   - `machine`
   - optional `dangerous_dev`
2. `machine`-Tools nur mit:
   - `confirm=true`
   - `reason`
3. `dangerous_dev`-Tools standardmaessig deaktivieren.
4. Logging fuer:
   - `modify`
   - `machine`
   - `dangerous_dev`

### Mindestfehlerfaelle

- confirm fehlt
- ungueltige Parameter
- keine Verbindung zur Maschine
- FreeCAD/GRBL nicht verfuegbar

### Done-Kriterium

- Maschinennahe Tools koennen nicht versehentlich durch einen unpraezisen Prompt ausgelost werden.

## Task Paket 8: Machine Tools

### Ziel

Einen kleinen, kontrollierten Satz maschinennaher Tools bereitstellen.

### Datei-Ziele

- `mcp/server/machine_tools.py`

### Erste Tools

1. `routerking_machine_connect`
2. `routerking_machine_disconnect`
3. `routerking_machine_request_status`
4. `routerking_machine_jog`
5. `routerking_machine_stream_gcode`
6. `routerking_machine_stop`

### Anforderungen

- alle auf bestehende RouterKing-Aktionen mappen
- bestaetigungspflicht bei Bewegung/Streaming
- Status immer mitliefern, wenn verfuegbar
- Fehlertext nicht euphemistisch, sondern klar und direkt

### Done-Kriterium

- Das Tooling ist nutzbar, ohne die Sicherheitsgrenzen zu verwischen.

## Task Paket 9: Dev Fallback

### Ziel

Optionaler Notfallpfad fuer Entwicklung, aber explizit vom Produktivpfad getrennt.

### Tool

1. `routerking_run_script`

### Regeln

- nur bei expliziter Aktivierung
- im Tool-Text klar als unsicher markiert
- spaeter auditierbar

### Empfehlung

Nicht im ersten produktiven MVP expose'n, wenn es nicht unbedingt gebraucht wird.

## Task Paket 10: Tests

### Ziel

Die neue Schicht mindestens auf Schema-, Sicherheits- und Adapterebene absichern.

### Datei-Ziele

- `tests/test_mcp_schemas.py`
- `tests/test_routerking_mcp_bridge.py`
- `tests/test_routerking_mcp_safety.py`

### Mindesttests

1. Schema-Validierung fuer Tool-Inputs
2. `routerking_apply_actions` lehnt unbekannte Action ab
3. `routerking_machine_jog` ohne Confirm wird abgelehnt
4. Read-only Tools liefern bei fehlendem Dokument sinnvolle Antworten
5. Screenshot-Fallback liefert Text statt harter Exception

### Optional frueh sinnvoll

- Test fuer Transaction-Abbruch bei Action-Fehler
- Test fuer gemischte Action-Liste mit Teilerfolgen

### Done-Kriterium

- Die neue Schicht ist mindestens gegen die offensichtlichsten Fehlpfade abgesichert.

## Task Paket 11: Dokumentation

### Ziel

Der naechste Agent-Lauf soll nicht wieder dieselben Architekturfragen loesen muessen.

### Datei-Ziele

- `docs/concepts/ai/MCP_TOOLS.md`
- `docs/concepts/ai/WORKBENCH_API.md`
- Update in `README.md` nur falls sinnvoll

### Inhalte

1. Wie der MCP-Server gestartet wird
2. Welche Tools es gibt
3. Welche Felder Confirm brauchen
4. Wie visuelles Feedback funktioniert
5. Welche RouterKing-Actions offiziell nach aussen sichtbar sind

### Done-Kriterium

- Ein neuer Kontext kann direkt mit den Doku-Dateien arbeiten, ohne das ganze Repo neu zu reverse engineeren.

## Reihenfolge fuer die Umsetzung

### Reihenfolge A: sinnvoll fuer einen ersten Implementierungslauf

1. Task Paket 1
2. Task Paket 2
3. Task Paket 3
4. Task Paket 4
5. Task Paket 5
6. Task Paket 10
7. Task Paket 6
8. Task Paket 7
9. Task Paket 8
10. Task Paket 11

### Warum diese Reihenfolge

- Erst Verbindung und Kontext, sonst arbeitet der Agent blind.
- Dann Action-Adapter, damit vorhandene RouterKing-Logik wiederverwendet wird.
- Erst danach CAM und Maschine.

## Erster konkreter Arbeitsauftrag fuer den naechsten Kontext

Wenn ein neuer Kontext gestartet wird, sollte der Auftrag moeglichst eng formuliert sein.

Empfohlener Startauftrag:

1. Lege die MCP-Struktur im Repo an.
2. Implementiere den Connection Layer und die Read-only Tools.
3. Implementiere eine erste RouterKing-Bridge mit `routerking_list_actions` und `routerking_apply_actions`.
4. Schreibe die Basistests fuer Schema und Safety.

## Copy-Paste Prompt fuer den naechsten Kontext

```text
Arbeite die Implementierung aus docs/roadmap/20260314-1315-implementation-tasks.md ab.
Starte mit der MCP-Grundstruktur direkt im Repo, nicht in einem externen Fork.
Prioritaet:
1. mcp/server Grundstruktur
2. RouterKing/mcp Bridge
3. Read-only Tools
4. routerking_list_actions
5. routerking_apply_actions
6. Basistests

Wichtig:
- vorhandene RouterKing-Logik wiederverwenden
- kein freies run_script als Primaerschnittstelle
- Maschinensteuerung noch nicht voll ausbauen, nur Safety-Struktur vorbereiten
- nutze bestehende RouterKing/ai/actions.py als Hauptanker fuer das Domain-Mapping
```

## Abnahme fuer die erste Implementierungsrunde

Die erste Runde ist erfolgreich, wenn:

1. die neue Struktur im Repo existiert
2. der MCP-Server startbar ist oder mindestens der Einstiegspunkt klar implementiert ist
3. Read-only Tools vorhanden sind
4. `routerking_list_actions` funktioniert
5. `routerking_apply_actions` fuer einfache Geometrieaktionen funktioniert
6. Basistests fuer Schema und Safety vorhanden sind

## Fazit

Das Dokument ist bewusst auf direkte Umsetzung geschnitten.
Es ersetzt keine Architekturentscheidung, aber es verhindert, dass der naechste Arbeitskontext wieder bei null startet oder in generischem MCP-/FreeCAD-Experimentieren steckenbleibt.
