# RouterKing AI Agent Roadmap

**Version:** 1.0  
**Status:** Draft  
**Erstellt:** 2026-01-13  
**Letzte Aktualisierung:** 2026-01-13

---

## Übersicht

Diese Roadmap definiert die Entwicklungsphasen für die Integration eines AI-Agenten in RouterKing. Die Phasen sind so strukturiert, dass jede Phase einen eigenständigen Mehrwert liefert.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        RouterKing AI Roadmap                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Phase 0        Phase 1         Phase 2         Phase 3         Phase 4 │
│  Foundation     MVP             Enhancement     Advanced        Polish   │
│  ─────────     ───             ───────────     ────────        ──────   │
│                                                                          │
│  [████████]    [░░░░░░░░]      [░░░░░░░░]      [░░░░░░░░]     [░░░░░░] │
│   Research      Chat UI         G-Code Opt.     Multi-Agent     UX      │
│   Concept       Basic LLM       Feeds/Speeds    RAG             Offline │
│   Architecture  Simple Tools    Troubleshoot    Learning        Stable  │
│                                                                          │
│  Q1 2026       Q1-Q2 2026      Q2-Q3 2026      Q3-Q4 2026     Q4 2026  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 0: Foundation (✅ Abgeschlossen)

**Zeitraum:** Januar 2026  
**Status:** ✅ Abgeschlossen

### Ziele
- [x] Recherche existierender FreeCAD AI-Projekte
- [x] Konzept-Dokument erstellen
- [x] Roadmap definieren
- [x] Architektur-Entscheidungen treffen

### Deliverables
- [x] `docs/temp/20260113-freecad-ai-agent-research.md`
- [x] `docs/concepts/ai/CONCEPT.md`
- [x] `docs/concepts/ai/ROADMAP.md`

### Entscheidungen
| Entscheidung | Gewählt | Alternativen |
|--------------|---------|--------------|
| Primary LLM Provider | OpenAI (GPT-4) | Anthropic, Ollama |
| Tool Calling | Function Calling | ReAct, Chain-of-Thought |
| UI Integration | Tab im Dock Widget | Separates Fenster |
| Fokus | G-Code Optimierung | CAD Generation |

---

## Phase 1: MVP - Basic Chat Integration

**Zeitraum:** Q1-Q2 2026 (6-8 Wochen)  
**Status:** 🔜 Geplant

### Ziele
Minimale funktionsfähige AI-Integration mit Chat-Interface und einfachen Tools.

### Milestones

#### 1.1 Infrastructure (Woche 1-2)
- [ ] `RouterKing/ai/` Modulstruktur erstellen
- [ ] LLM Provider Abstraction implementieren
- [ ] OpenAI Provider implementieren
- [ ] API Key Management (Environment Variable)
- [ ] Basic Configuration

**Deliverables:**
```
RouterKing/
├── ai/
│   ├── __init__.py
│   ├── agent.py
│   ├── config.py
│   └── providers/
│       ├── __init__.py
│       ├── base.py
│       └── openai.py
```

#### 1.2 Chat UI (Woche 3-4)
- [ ] AI Chat Panel Widget erstellen
- [ ] Chat History Display
- [ ] Message Input mit Send Button
- [ ] Streaming Response Display
- [ ] Provider/Model Selector
- [ ] Integration in `main_dock.py` als Tab

**Deliverables:**
```
RouterKing/
└── ui/
    └── ai_chat_panel.py
```

**UI Mockup:**
```
┌─────────────────────────────────────┐
│ [Control] [G-Code] [AI] [Settings] │
├─────────────────────────────────────┤
│ 🤖 RouterKing AI                    │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Chat History                    │ │
│ │ ...                             │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Message...              [Send]  │ │
│ └─────────────────────────────────┘ │
│                                     │
│ Provider: [OpenAI ▼] [⚙️]          │
└─────────────────────────────────────┘
```

#### 1.3 Basic Tools (Woche 5-6)
- [ ] Tool Base Class
- [ ] `analyze_gcode` Tool (Read-only)
- [ ] `get_machine_status` Tool
- [ ] `explain_grbl_error` Tool
- [ ] Tool Registry

**Deliverables:**
```
RouterKing/
└── ai/
    └── tools/
        ├── __init__.py
        ├── base.py
        ├── gcode_analyzer.py
        └── grbl_helper.py
```

#### 1.4 Integration & Testing (Woche 7-8)
- [ ] Integration Tests
- [ ] Error Handling
- [ ] Loading States
- [ ] Basic Documentation
- [ ] User Testing

### Akzeptanzkriterien Phase 1
- [ ] User kann Chat-Panel öffnen
- [ ] User kann Fragen stellen und Antworten erhalten
- [ ] AI kann geladenen G-Code analysieren
- [ ] AI kann GRBL-Fehlercodes erklären
- [ ] Streaming funktioniert (Antwort erscheint progressiv)

### Risiken Phase 1
| Risiko | Mitigation |
|--------|------------|
| FreeCAD Python Environment Konflikte | Vendored Dependencies |
| API Key Exposure | Environment Variables |
| Langsame Antworten | Streaming + Progress |

---

## Phase 2: Enhancement - G-Code Intelligence

**Zeitraum:** Q2-Q3 2026 (8-10 Wochen)  
**Status:** 📋 Geplant

### Ziele
Intelligente G-Code Analyse und Optimierung mit domänenspezifischem Wissen.

### Milestones

#### 2.1 G-Code Optimizer (Woche 1-3)
- [ ] `optimize_gcode` Tool
- [ ] Corner Slowdown Optimization
- [ ] Ramping Addition
- [ ] Feed Rate Smoothing
- [ ] Optimization Preview
- [ ] Apply/Reject Workflow

**Features:**
```
User: "Optimiere meinen G-Code"

AI Response:
┌────────────────────────────────────────┐
│ 🔧 Optimierungen gefunden:             │
│                                        │
│ 1. ⚡ Corner Slowdown                  │
│    12 Ecken mit >90° gefunden          │
│    → Feed Rate -30% in Ecken           │
│                                        │
│ 2. 📐 Ramping                          │
│    8 Plunge-Moves ohne Ramping         │
│    → 45° Ramping hinzufügen            │
│                                        │
│ [Preview] [Apply All] [Skip]           │
└────────────────────────────────────────┘
```

#### 2.2 Feeds & Speeds Calculator (Woche 4-5)
- [ ] `get_feeds_speeds` Tool
- [ ] Material Database (JSON)
- [ ] Tool Database (JSON)
- [ ] Calculation Logic
- [ ] Apply to Current Job

**Knowledge Base:**
```json
// RouterKing/ai/knowledge/materials.json
{
  "materials": {
    "birch_plywood": {
      "name": "Birke Multiplex",
      "hardness": "medium",
      "chip_load_factor": 1.0,
      "recommended_tools": ["upcut", "compression"],
      "notes": "Staubt stark, Absaugung empfohlen"
    },
    "acrylic": {
      "name": "Acryl/Plexiglas",
      "hardness": "soft",
      "chip_load_factor": 0.8,
      "recommended_tools": ["single_flute", "o_flute"],
      "notes": "Neigt zum Schmelzen bei zu hoher Drehzahl"
    }
  }
}
```

#### 2.3 Troubleshooting Agent (Woche 6-7)
- [ ] `diagnose_issue` Tool
- [ ] Symptom → Cause Mapping
- [ ] Solution Suggestions
- [ ] Context-Aware Diagnosis (aktuelle Settings)

**Diagnosis Flow:**
```
┌─────────────────────────────────────────────────────────────┐
│                    Troubleshooting Flow                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   [User Symptom]                                             │
│         │                                                    │
│         ▼                                                    │
│   ┌─────────────┐                                            │
│   │  Symptom    │  "Fräser rattert"                         │
│   │  Parser     │  → Keywords: rattle, vibration, chatter   │
│   └──────┬──────┘                                            │
│          │                                                   │
│          ▼                                                   │
│   ┌─────────────┐                                            │
│   │  Context    │  Current: 24000 RPM, 1800 mm/min          │
│   │  Enrichment │  Material: Plywood, Tool: 6mm Upcut       │
│   └──────┬──────┘                                            │
│          │                                                   │
│          ▼                                                   │
│   ┌─────────────┐                                            │
│   │  Diagnosis  │  Causes: [Too high RPM, Dull tool,        │
│   │  Engine     │           Loose collet]                   │
│   └──────┬──────┘                                            │
│          │                                                   │
│          ▼                                                   │
│   [Ranked Solutions with Actions]                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### 2.4 Settings Panel (Woche 8)
- [ ] AI Settings UI
- [ ] API Key Input (masked)
- [ ] Model Selection
- [ ] Behavior Toggles
- [ ] Machine Profile

#### 2.5 Testing & Polish (Woche 9-10)
- [ ] Integration Tests
- [ ] Performance Optimization
- [ ] Error Messages verbessern
- [ ] Documentation

### Akzeptanzkriterien Phase 2
- [ ] G-Code kann automatisch optimiert werden
- [ ] Feeds & Speeds werden basierend auf Material berechnet
- [ ] Probleme können diagnostiziert werden
- [ ] Settings können über UI konfiguriert werden

---

## Phase 3: Advanced - Multi-Agent & RAG

**Zeitraum:** Q3-Q4 2026 (10-12 Wochen)  
**Status:** 📋 Geplant

### Ziele
Erweiterte AI-Funktionen mit Retrieval-Augmented Generation und spezialisierten Agenten.

### Milestones

#### 3.1 Anthropic Provider (Woche 1-2)
- [ ] Claude API Integration
- [ ] Provider Switching in UI
- [ ] Model Comparison

#### 3.2 Ollama Provider (Woche 3-4)
- [ ] Lokale LLM Integration
- [ ] Ollama Auto-Detection
- [ ] Model Download Helper
- [ ] Offline Mode

#### 3.3 RAG System (Woche 5-8)
- [ ] Vector Store (ChromaDB oder ähnlich)
- [ ] FreeCAD Documentation Embedding
- [ ] GRBL Documentation Embedding
- [ ] Context Retrieval
- [ ] Hybrid Search (Semantic + Keyword)

**RAG Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│                      RAG System                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   [User Query]                                               │
│         │                                                    │
│         ▼                                                    │
│   ┌─────────────┐     ┌─────────────────────────────────┐   │
│   │  Embedder   │────▶│  Vector Store                   │   │
│   └─────────────┘     │  • FreeCAD Docs                 │   │
│                       │  • GRBL Reference               │   │
│                       │  • Material Database            │   │
│                       │  • Community Q&A                │   │
│                       └──────────────┬──────────────────┘   │
│                                      │                       │
│                                      ▼                       │
│                       ┌─────────────────────────────────┐   │
│                       │  Top-K Relevant Chunks          │   │
│                       └──────────────┬──────────────────┘   │
│                                      │                       │
│                                      ▼                       │
│   ┌─────────────┐     ┌─────────────────────────────────┐   │
│   │  LLM        │◀────│  Augmented Prompt               │   │
│   └──────┬──────┘     │  Query + Context + Instructions │   │
│          │            └─────────────────────────────────┘   │
│          ▼                                                   │
│   [Grounded Response]                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### 3.4 Specialized Agents (Woche 9-10)
- [ ] G-Code Expert Agent
- [ ] Setup Wizard Agent
- [ ] Troubleshooter Agent
- [ ] Agent Router (wählt richtigen Agent)

#### 3.5 Learning & Feedback (Woche 11-12)
- [ ] User Feedback Collection
- [ ] Success/Failure Tracking
- [ ] Personalized Recommendations
- [ ] Usage Analytics (opt-in)

### Akzeptanzkriterien Phase 3
- [ ] Multiple LLM Provider unterstützt
- [ ] Offline-Modus mit Ollama funktioniert
- [ ] RAG liefert relevante Dokumentation
- [ ] Spezialisierte Agenten für verschiedene Tasks

---

## Phase 4: Polish - Production Ready

**Zeitraum:** Q4 2026 (6-8 Wochen)  
**Status:** 📋 Geplant

### Ziele
Stabilität, Performance und User Experience für Production Release.

### Milestones

#### 4.1 Performance (Woche 1-2)
- [ ] Response Caching
- [ ] Token Optimization
- [ ] Lazy Loading
- [ ] Background Processing

#### 4.2 Security (Woche 3-4)
- [ ] Secure API Key Storage (Keychain)
- [ ] Input Sanitization
- [ ] G-Code Validation vor Ausführung
- [ ] Security Audit

#### 4.3 UX Polish (Woche 5-6)
- [ ] Keyboard Shortcuts
- [ ] Accessibility (Screen Reader)
- [ ] Themes (Light/Dark)
- [ ] Animations & Transitions
- [ ] Error Messages verbessern

#### 4.4 Documentation & Release (Woche 7-8)
- [ ] User Guide
- [ ] Video Tutorials
- [ ] API Documentation
- [ ] Release Notes
- [ ] Marketing Material

### Akzeptanzkriterien Phase 4
- [ ] Antwortzeit < 3 Sekunden (cached)
- [ ] Keine bekannten Sicherheitslücken
- [ ] Accessibility WCAG 2.1 AA
- [ ] Vollständige Dokumentation

---

## Ressourcen-Schätzung

### Entwicklungsaufwand

| Phase | Dauer | Aufwand (h) | Komplexität |
|-------|-------|-------------|-------------|
| Phase 0 | 1 Woche | 20h | Niedrig |
| Phase 1 | 8 Wochen | 160h | Mittel |
| Phase 2 | 10 Wochen | 200h | Mittel-Hoch |
| Phase 3 | 12 Wochen | 240h | Hoch |
| Phase 4 | 8 Wochen | 160h | Mittel |
| **Total** | **~39 Wochen** | **~780h** | - |

### API-Kosten (geschätzt)

| Phase | Tokens/Monat | Kosten/Monat |
|-------|--------------|--------------|
| Development | ~500K | ~$5-10 |
| Beta Testing | ~2M | ~$20-40 |
| Production | ~10M | ~$100-200 |

*Basierend auf GPT-4 Turbo Preisen (Stand 2026)*

---

## Abhängigkeiten & Blockers

### Externe Abhängigkeiten

| Abhängigkeit | Benötigt für | Status |
|--------------|--------------|--------|
| OpenAI API Access | Phase 1+ | ✅ Verfügbar |
| Anthropic API Access | Phase 3 | ✅ Verfügbar |
| Ollama | Phase 3 | ✅ Open Source |
| ChromaDB | Phase 3 | ✅ Open Source |

### Interne Abhängigkeiten

| Abhängigkeit | Benötigt für | Status |
|--------------|--------------|--------|
| G-Code Parser | Phase 1+ | ✅ Existiert |
| GRBL Sender | Phase 2+ | ✅ Existiert |
| Settings Infrastructure | Phase 2 | 🔜 Zu erstellen |
| Tab-basiertes UI | Phase 1 | 🔜 Zu erstellen |

---

## Entscheidungspunkte

### Nach Phase 1
- [ ] Weiter mit OpenAI oder Anthropic als Primary?
- [ ] Priorisierung der Phase 2 Features?
- [ ] Community Feedback einbeziehen?

### Nach Phase 2
- [ ] RAG-System notwendig oder overkill?
- [ ] Ollama-Integration priorisieren?
- [ ] Monetarisierung (API-Kosten weitergeben)?

### Nach Phase 3
- [ ] Production Release Timing?
- [ ] Marketing-Strategie?
- [ ] Community Contributions?

---

## Changelog

| Version | Datum | Änderungen |
|---------|-------|------------|
| 1.0 | 2026-01-13 | Initial Roadmap |

---

## Nächste Schritte

1. **Chief AI Review** dieser Roadmap
2. **Entscheidung:** Start Phase 1?
3. **Setup:** OpenAI API Key für Development
4. **Kickoff:** Phase 1.1 Infrastructure
