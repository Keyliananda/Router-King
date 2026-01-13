# RouterKing AI Agent Concept

**Version:** 1.0  
**Status:** Draft  
**Erstellt:** 2026-01-13  
**Autor:** RouterKing Team

---

## 1. Executive Summary

RouterKing integriert einen AI-Agenten, der CNC- und Laser-Workflows intelligent unterstützt. Der Agent kombiniert Large Language Models (LLMs) mit domänenspezifischem Wissen über G-Code, GRBL und Fertigungsprozesse.

**Unique Selling Proposition (USP):**  
Kein existierendes Open-Source-Projekt kombiniert FreeCAD, GRBL-Sender und AI-gestützte G-Code-Optimierung in einem integrierten Workflow.

---

## 2. Vision

> "Der intelligente Copilot für CNC- und Laser-Fertigung"

Der RouterKing AI Agent soll:
- **Anfängern** helfen, schnell produktiv zu werden
- **Experten** repetitive Aufgaben abnehmen
- **Fehler** vor der Ausführung erkennen
- **Optimierungen** vorschlagen, die manuell zeitaufwändig wären

---

## 3. Zielgruppen

| Persona | Bedürfnis | AI-Lösung |
|---------|-----------|-----------|
| **Hobby-Maker** | "Welche Einstellungen für Sperrholz?" | Setup Assistant |
| **Profi-Fertiger** | "Optimiere Toolpaths für Serienproduktion" | G-Code Optimizer |
| **FreeCAD-Neuling** | "Wie erstelle ich eine Tasche?" | CAD/CAM Assistant |
| **Troubleshooter** | "Warum rattert mein Fräser?" | Diagnose Agent |

---

## 4. Kernfunktionen

### 4.1 G-Code Optimizer (Priorität: HOCH)

**Problem:** Manuelles Optimieren von G-Code ist zeitaufwändig und erfordert Expertenwissen.

**Lösung:** AI analysiert G-Code und schlägt Optimierungen vor.

```
┌─────────────────────────────────────────────────────────────┐
│                     G-Code Optimizer Flow                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   [G-Code Input]                                             │
│         │                                                    │
│         ▼                                                    │
│   ┌─────────────┐                                            │
│   │  Parser     │  Extrahiert: Moves, Feed Rates,           │
│   │  (existing) │  Tool Changes, Spindle Commands           │
│   └──────┬──────┘                                            │
│          │                                                   │
│          ▼                                                   │
│   ┌─────────────┐                                            │
│   │  Analyzer   │  Erkennt: Scharfe Ecken, Ineffiziente     │
│   │  (AI)       │  Pfade, Fehlende Ramping, Risiken         │
│   └──────┬──────┘                                            │
│          │                                                   │
│          ▼                                                   │
│   ┌─────────────┐                                            │
│   │  Optimizer  │  Generiert: Optimierte Feed Rates,        │
│   │  (AI)       │  Smoothed Paths, Safety Additions         │
│   └──────┬──────┘                                            │
│          │                                                   │
│          ▼                                                   │
│   [Optimized G-Code] + [Explanation]                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Optimierungen:**
- **Feed Rate Adjustment:** Automatische Anpassung basierend auf Material und Geometrie
- **Corner Smoothing:** Reduzierte Geschwindigkeit in Ecken für bessere Oberfläche
- **Ramping:** Automatisches Hinzufügen von Rampen für Plunge-Moves
- **Tab Placement:** Intelligente Positionierung von Halte-Tabs
- **Collision Detection:** Warnung bei potenziellen Kollisionen

### 4.2 CNC Setup Assistant (Priorität: MITTEL)

**Problem:** Anfänger wissen nicht, welche Einstellungen für ihr Material optimal sind.

**Lösung:** AI empfiehlt Feeds & Speeds basierend auf Material, Werkzeug und Maschine.

```
User: "Ich möchte 12mm Birke-Multiplex fräsen mit einem 6mm Spiralnutfräser"

Agent Response:
┌────────────────────────────────────────────────────────────┐
│ 📊 Empfohlene Einstellungen für Birke-Multiplex (12mm)     │
├────────────────────────────────────────────────────────────┤
│ Werkzeug:     6mm Upcut Spiralnutfräser                    │
│ Drehzahl:     18.000 RPM                                   │
│ Vorschub:     2.400 mm/min                                 │
│ Eintauchrate: 600 mm/min                                   │
│ Zustellung:   4mm pro Pass (3 Passes)                      │
│ Seitl. Zust.: 3mm (50%)                                    │
├────────────────────────────────────────────────────────────┤
│ 💡 Tipps:                                                   │
│ • Downcut-Fräser für saubere Oberkante verwenden          │
│ • Absaugung empfohlen (Birke staubt stark)                │
│ • Bei Verbrennungen: Vorschub erhöhen                     │
├────────────────────────────────────────────────────────────┤
│ [Übernehmen] [Anpassen] [Mehr Infos]                       │
└────────────────────────────────────────────────────────────┘
```

**Wissensbasis:**
- Materialdatenbank (Holz, Kunststoff, Aluminium, etc.)
- Werkzeugdatenbank (Fräser, Gravierstichel, Laser)
- Maschinendatenbank (Spindelleistung, Arbeitsbereich)

### 4.3 Troubleshooting Agent (Priorität: MITTEL)

**Problem:** Diagnose von CNC-Problemen erfordert Erfahrung.

**Lösung:** AI diagnostiziert Probleme basierend auf Symptomen.

```
User: "Mein Fräser macht ein schleifendes Geräusch"

Agent:
┌────────────────────────────────────────────────────────────┐
│ 🔍 Diagnose: Schleifendes Geräusch                         │
├────────────────────────────────────────────────────────────┤
│ Mögliche Ursachen (nach Wahrscheinlichkeit):               │
│                                                            │
│ 1. ⚠️  Stumpfer Fräser (70%)                               │
│    → Lösung: Fräser wechseln oder schärfen                │
│                                                            │
│ 2. ⚡ Zu hohe Drehzahl für Material (20%)                  │
│    → Lösung: Drehzahl von 24.000 auf 18.000 reduzieren    │
│                                                            │
│ 3. 🔧 Spannzange locker (10%)                              │
│    → Lösung: Spannzange prüfen und nachziehen             │
├────────────────────────────────────────────────────────────┤
│ Aktuelle Einstellungen:                                    │
│ • Drehzahl: 24.000 RPM                                     │
│ • Vorschub: 1.800 mm/min                                   │
│ • Material: Sperrholz                                      │
├────────────────────────────────────────────────────────────┤
│ [Drehzahl anpassen] [Mehr Fragen] [Problem gelöst]         │
└────────────────────────────────────────────────────────────┘
```

### 4.4 CAD/CAM Assistant (Priorität: NIEDRIG)

**Problem:** FreeCAD Path Workbench hat eine steile Lernkurve.

**Lösung:** Natural Language Interface für CAM-Operationen.

```
User: "Erstelle eine Tasche 80x50mm, 8mm tief, mit 2mm Radius in den Ecken"

Agent:
1. Erstellt Sketch mit Rechteck 80x50mm
2. Fügt Fillets (2mm) hinzu
3. Erstellt Pocket Feature (8mm tief)
4. Generiert Path Operation mit aktuellen Einstellungen
5. Exportiert G-Code
```

---

## 5. Technische Architektur

### 5.1 Systemübersicht

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          RouterKing Workbench                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────────┐ │
│  │  GRBL Module   │  │  G-Code Module │  │     AI Agent Module        │ │
│  │  ────────────  │  │  ────────────  │  │     ─────────────────      │ │
│  │  • Sender      │  │  • Parser      │  │  ┌──────────────────────┐  │ │
│  │  • Status      │  │  • Validator   │  │  │   LLM Provider       │  │ │
│  │  • Control     │  │  • Optimizer   │  │  │   (OpenAI/Anthropic/ │  │ │
│  │                │  │                │  │  │    Ollama)           │  │ │
│  └───────┬────────┘  └───────┬────────┘  │  └──────────┬───────────┘  │ │
│          │                   │           │             │              │ │
│          │                   │           │  ┌──────────▼───────────┐  │ │
│          │                   │           │  │   Tool Registry      │  │ │
│          │                   │           │  │   • analyze_gcode    │  │ │
│          │                   │           │  │   • optimize_gcode   │  │ │
│          │                   │           │  │   • get_feeds_speeds │  │ │
│          │                   │           │  │   • diagnose_issue   │  │ │
│          │                   │           │  │   • execute_freecad  │  │ │
│          │                   │           │  └──────────┬───────────┘  │ │
│          │                   │           │             │              │ │
│          │                   │           │  ┌──────────▼───────────┐  │ │
│          │                   │           │  │   Context Manager    │  │ │
│          │                   │           │  │   • Machine State    │  │ │
│          │                   │           │  │   • Current G-Code   │  │ │
│          │                   │           │  │   • Chat History     │  │ │
│          │                   │           │  │   • User Preferences │  │ │
│          │                   │           │  └──────────────────────┘  │ │
│          │                   │           └────────────────────────────┘ │
│          │                   │                         │                │
│          ▼                   ▼                         ▼                │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                         Unified UI Layer                          │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐   │  │
│  │  │ Control     │  │ G-Code      │  │ AI Chat Panel           │   │  │
│  │  │ Panel       │  │ Viewer      │  │ ─────────────────────── │   │  │
│  │  │             │  │             │  │ [User Input]            │   │  │
│  │  │ [Connect]   │  │ [Load]      │  │ [AI Response]           │   │  │
│  │  │ [Home]      │  │ [Stream]    │  │ [Action Buttons]        │   │  │
│  │  │ [Jog]       │  │ [Pause]     │  │ [History]               │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Modulstruktur

```
RouterKing/
├── ai/
│   ├── __init__.py
│   ├── agent.py              # Hauptlogik des AI Agents
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py           # Abstract Base Provider
│   │   ├── openai.py         # OpenAI GPT-4 Integration
│   │   ├── anthropic.py      # Claude Integration
│   │   └── ollama.py         # Lokale LLMs
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py           # Tool Base Class
│   │   ├── gcode_analyzer.py # G-Code Analyse Tool
│   │   ├── gcode_optimizer.py# G-Code Optimierung Tool
│   │   ├── feeds_speeds.py   # Feeds & Speeds Calculator
│   │   ├── troubleshooter.py # Diagnose Tool
│   │   └── freecad_exec.py   # FreeCAD Command Executor
│   ├── context/
│   │   ├── __init__.py
│   │   ├── manager.py        # Context Manager
│   │   ├── machine.py        # Machine State Context
│   │   └── history.py        # Chat History Manager
│   ├── knowledge/
│   │   ├── __init__.py
│   │   ├── materials.json    # Materialdatenbank
│   │   ├── tools.json        # Werkzeugdatenbank
│   │   └── grbl_errors.json  # GRBL Fehlercodes
│   └── config.py             # AI Configuration
├── ui/
│   ├── main_dock.py          # Existing
│   └── ai_chat_panel.py      # NEW: AI Chat Widget
└── ...
```

### 5.3 Tool Definitions (Function Calling)

Der AI Agent nutzt **Function Calling** (OpenAI) bzw. **Tool Use** (Anthropic), um strukturierte Aktionen auszuführen.

```python
# Beispiel: Tool Definition für G-Code Analyse
GCODE_ANALYZER_TOOL = {
    "name": "analyze_gcode",
    "description": "Analysiert G-Code und gibt strukturierte Informationen zurück",
    "parameters": {
        "type": "object",
        "properties": {
            "gcode": {
                "type": "string",
                "description": "Der zu analysierende G-Code"
            },
            "analysis_type": {
                "type": "string",
                "enum": ["summary", "feeds", "toolpaths", "issues"],
                "description": "Art der Analyse"
            }
        },
        "required": ["gcode", "analysis_type"]
    }
}

# Beispiel: Tool Definition für Feeds & Speeds
FEEDS_SPEEDS_TOOL = {
    "name": "get_feeds_speeds",
    "description": "Berechnet optimale Feeds & Speeds für Material und Werkzeug",
    "parameters": {
        "type": "object",
        "properties": {
            "material": {
                "type": "string",
                "description": "Material (z.B. 'birch_plywood', 'acrylic', 'aluminum')"
            },
            "tool_diameter": {
                "type": "number",
                "description": "Werkzeugdurchmesser in mm"
            },
            "tool_type": {
                "type": "string",
                "enum": ["upcut", "downcut", "compression", "ball_nose", "v_bit"],
                "description": "Werkzeugtyp"
            },
            "operation": {
                "type": "string",
                "enum": ["profile", "pocket", "drill", "engrave"],
                "description": "Bearbeitungsart"
            }
        },
        "required": ["material", "tool_diameter", "tool_type"]
    }
}
```

### 5.4 LLM Provider Abstraction

```python
# RouterKing/ai/providers/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Generator

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]] = None,
        stream: bool = False
    ) -> Generator[str, None, None] | Dict[str, Any]:
        """Send a chat completion request."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is configured and available."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for display."""
        pass
```

---

## 6. User Interface

### 6.1 AI Chat Panel

Das AI Chat Panel wird als zusätzlicher Tab im RouterKing Dock Widget integriert.

```
┌─────────────────────────────────────────────────────────────┐
│ RouterKing                                    [_][□][X]     │
├─────────────────────────────────────────────────────────────┤
│ [Control] [G-Code] [AI Assistant] [Settings]                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 🤖 RouterKing AI                                      │  │
│  │                                                       │  │
│  │ ┌─────────────────────────────────────────────────┐   │  │
│  │ │ 👤 Optimiere meinen G-Code für bessere          │   │  │
│  │ │    Oberflächenqualität                          │   │  │
│  │ └─────────────────────────────────────────────────┘   │  │
│  │                                                       │  │
│  │ ┌─────────────────────────────────────────────────┐   │  │
│  │ │ 🤖 Ich habe deinen G-Code analysiert und        │   │  │
│  │ │    folgende Optimierungen gefunden:             │   │  │
│  │ │                                                 │   │  │
│  │ │    📊 Analyse:                                  │   │  │
│  │ │    • 2.847 Bewegungen                           │   │  │
│  │ │    • 12 scharfe Ecken (>90°)                    │   │  │
│  │ │    • Keine Ramping-Moves                        │   │  │
│  │ │                                                 │   │  │
│  │ │    🔧 Vorgeschlagene Optimierungen:             │   │  │
│  │ │    1. Corner Slowdown (-30% in Ecken)           │   │  │
│  │ │    2. Ramping hinzufügen (45° Winkel)           │   │  │
│  │ │    3. Feed Rate Smoothing                       │   │  │
│  │ │                                                 │   │  │
│  │ │    [Alle anwenden] [Einzeln prüfen] [Abbrechen] │   │  │
│  │ └─────────────────────────────────────────────────┘   │  │
│  │                                                       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Nachricht eingeben...                          [Send] │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Provider: [OpenAI ▼]  Model: [gpt-4 ▼]  [⚙️ Settings]     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Quick Actions

Häufige Aktionen werden als Quick Action Buttons bereitgestellt:

```
┌─────────────────────────────────────────────────────────────┐
│ Quick Actions:                                              │
│                                                             │
│ [🔍 G-Code analysieren]  [⚡ Optimieren]  [📊 Feeds & Speeds]│
│ [🔧 Problem diagnostizieren]  [📝 Erklären]                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Sicherheit & Validierung

### 7.1 G-Code Validierung

Bevor optimierter G-Code angewendet wird, durchläuft er eine Validierung:

```python
class GCodeValidator:
    """Validates G-Code before execution."""
    
    def validate(self, gcode: str) -> ValidationResult:
        """
        Validates G-Code for safety and correctness.
        
        Checks:
        - Syntax validity
        - Machine limits (X, Y, Z bounds)
        - Feed rate limits
        - Spindle speed limits
        - Dangerous commands (e.g., rapid moves at cutting depth)
        """
        pass
```

### 7.2 User Confirmation

Kritische Aktionen erfordern Benutzerbestätigung:

- G-Code Modifikationen
- GRBL Settings Änderungen
- Automatische Ausführung von Befehlen

### 7.3 Sandbox Mode

Für Testing und Lernen:
- Simulierte Ausführung ohne echte Maschinenbewegung
- Visualisierung der geplanten Toolpaths
- Dry-Run mit Zeitschätzung

---

## 8. Konfiguration

### 8.1 Settings Panel

```
┌─────────────────────────────────────────────────────────────┐
│ AI Settings                                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Provider:                                                   │
│ ○ OpenAI (GPT-4)                                           │
│ ○ Anthropic (Claude)                                       │
│ ○ Ollama (Local)                                           │
│                                                             │
│ API Key: [••••••••••••••••••••••••]  [Show] [Test]         │
│                                                             │
│ Model: [gpt-4-turbo ▼]                                     │
│                                                             │
│ ─────────────────────────────────────────────────────────  │
│                                                             │
│ Behavior:                                                   │
│ ☑ Automatische G-Code Analyse beim Laden                   │
│ ☑ Warnungen bei potenziellen Problemen                     │
│ ☐ Automatische Optimierung vorschlagen                     │
│                                                             │
│ Language: [Deutsch ▼]                                      │
│                                                             │
│ ─────────────────────────────────────────────────────────  │
│                                                             │
│ Machine Profile:                                            │
│ Max X: [300] mm    Max Y: [400] mm    Max Z: [80] mm       │
│ Max Feed: [3000] mm/min    Max Spindle: [24000] RPM        │
│                                                             │
│                                    [Cancel] [Save]          │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 Konfigurationsdatei

```json
{
  "ai": {
    "provider": "openai",
    "api_key": "${ROUTERKING_API_KEY}",
    "model": "gpt-4-turbo",
    "temperature": 0.3,
    "max_tokens": 4096,
    "language": "de"
  },
  "behavior": {
    "auto_analyze": true,
    "show_warnings": true,
    "auto_suggest_optimization": false,
    "require_confirmation": true
  },
  "machine": {
    "max_x": 300,
    "max_y": 400,
    "max_z": 80,
    "max_feed_rate": 3000,
    "max_spindle_speed": 24000
  }
}
```

---

## 9. Datenschutz

### 9.1 Was wird gesendet?

| Daten | Gesendet? | Grund |
|-------|-----------|-------|
| G-Code | ✅ Ja | Für Analyse und Optimierung |
| Chat-Nachrichten | ✅ Ja | Für Antwortgenerierung |
| Machine Settings | ⚠️ Optional | Für kontextbezogene Empfehlungen |
| Persönliche Daten | ❌ Nein | Nicht erforderlich |

### 9.2 Lokale Alternative

Für datenschutzsensible Anwendungen:
- **Ollama** mit lokalen Modellen (Llama 3, Mistral)
- Keine Daten verlassen den Rechner
- Eingeschränkte Leistung im Vergleich zu GPT-4/Claude

---

## 10. Metriken & Erfolg

### 10.1 Erfolgskriterien

| Metrik | Ziel |
|--------|------|
| Time to First Success | < 30 Sekunden |
| User Satisfaction | > 4.0/5.0 |
| G-Code Optimization Rate | > 80% Verbesserung |
| Error Detection Rate | > 95% |
| False Positive Rate | < 5% |

### 10.2 Feedback Loop

- In-App Feedback ("War diese Antwort hilfreich?")
- Anonymisierte Nutzungsstatistiken (opt-in)
- Community Feedback über GitHub Issues

---

## 11. Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| LLM Halluzination | Mittel | Hoch | Validierung + User Confirmation |
| API-Ausfall | Niedrig | Mittel | Fallback zu Ollama |
| Hohe API-Kosten | Mittel | Niedrig | Token-Limit + Caching |
| Langsame Antworten | Mittel | Niedrig | Streaming + Progress Indicator |
| Sicherheitslücken | Niedrig | Hoch | Code Review + Sandbox |

---

## 12. Abhängigkeiten

### 12.1 Externe Abhängigkeiten

| Dependency | Version | Zweck |
|------------|---------|-------|
| openai | ^1.0 | OpenAI API Client |
| anthropic | ^0.18 | Anthropic API Client |
| httpx | ^0.27 | HTTP Client für Ollama |

### 12.2 Interne Abhängigkeiten

- `RouterKing/gcode/parser.py` - G-Code Parsing
- `RouterKing/grbl/sender.py` - GRBL Kommunikation
- `RouterKing/ui/main_dock.py` - UI Integration

---

## 13. Offene Fragen

1. **API Key Storage:** Keychain vs. Config File?
2. **Streaming:** SSE oder WebSocket für Echtzeit-Antworten?
3. **Caching:** Wie lange sollen Antworten gecacht werden?
4. **Multi-Language:** Soll der Agent mehrsprachig sein?
5. **Offline Mode:** Welche Features funktionieren ohne Internet?

---

## 14. Referenzen

- [CAD-Assistant (ICCV 2025)](https://github.com/dimitrismallis/CAD-Assistant)
- [cadgent](https://github.com/brukg/cadgent)
- [CADomatic](https://github.com/yas1nsyed/CADomatic)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [Anthropic Tool Use](https://docs.anthropic.com/claude/docs/tool-use)

---

## Changelog

| Version | Datum | Änderungen |
|---------|-------|------------|
| 1.0 | 2026-01-13 | Initial Draft |
