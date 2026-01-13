# FreeCAD AI Agent Research

**Datum:** 2026-01-13  
**Status:** Recherche abgeschlossen, Empfehlung für Chief AI Review

---

## Zusammenfassung

Es gibt bereits mehrere existierende FreeCAD AI-Integrationen. Die Arbeit wäre **nicht umsonst**, da wir entweder:
1. Ein bestehendes Projekt als Basis nutzen können
2. Einen spezialisierten AI-Agent für CNC/Laser-Workflows bauen können (einzigartig!)

---

## Existierende Projekte (nach Relevanz sortiert)

### 1. **CAD-Assistant** ⭐⭐⭐ (34 Stars)
- **URL:** https://github.com/dimitrismallis/CAD-Assistant
- **Paper:** ICCV 2025 (akademisch fundiert!)
- **Ansatz:** Tool-Augmented VLLM Framework
- **Features:**
  - Generiert FreeCAD Python-Code
  - Multimodal: Text, Sketches, 3D Scans
  - Erweiterbar mit eigenen Tools
- **Relevanz für RouterKing:** Sehr hoch – könnte als Basis für G-Code Optimierung dienen

### 2. **CADomatic** ⭐⭐ (20 Stars)
- **URL:** https://github.com/yas1nsyed/CADomatic
- **Ansatz:** Text-to-CAD mit Gemini API
- **Features:**
  - Generiert parametrische FreeCAD Python Scripts
  - Hugging Face Demo verfügbar
  - v2.0 plant: Image-based Validation + Feedback Loop
- **Relevanz:** Mittel – fokussiert auf CAD-Generierung, nicht CNC

### 3. **cadgent** ⭐ (2 Stars)
- **URL:** https://github.com/brukg/cadgent
- **Ansatz:** FreeCAD Workbench mit LLM-Integration
- **Features:**
  - Natural Language → FreeCAD Commands
  - Checkpoint System (Git-like)
  - Model Inspection
  - Chat Interface
- **Relevanz für RouterKing:** **SEHR HOCH** – Architektur sehr ähnlich!
  - Auch ein FreeCAD Workbench
  - Nutzt OpenAI API
  - Hat UI-Panel mit Chat

### 4. **openAI-to-freeCAD-workflow** (13 Stars)
- **URL:** https://github.com/giuliano-t/openAI-to-freeCAD-workflow
- **Ansatz:** RAG (Retrieval-Augmented Generation)
- **Features:**
  - Natural Language → FreeCAD Python Scripts
  - RAG für bessere Ergebnisse
- **Relevanz:** Mittel – Jupyter Notebook basiert

### 5. **Agentic-CAD** (1 Star)
- **URL:** https://github.com/dishax57/Agentic-CAD
- **Ansatz:** LangGraph-basierte Multi-Agent Architektur
- **Features:**
  - Modulare LLM Agents
  - Create, Modify, Manage 3D Shapes
- **Relevanz:** Interessant für Agent-Architektur

---

## Mögliche AI-Integrationen für RouterKing

### Option A: G-Code Optimierungs-Agent (EINZIGARTIG!)
**Kein existierendes Projekt macht das!**

```
User: "Optimiere meinen G-Code für bessere Oberflächenqualität"
Agent: 
  1. Analysiert G-Code (Feed rates, Toolpaths)
  2. Erkennt Probleme (zu schnelle Ecken, ineffiziente Pfade)
  3. Schlägt Optimierungen vor
  4. Generiert optimierten G-Code
```

**Use Cases:**
- Feed Rate Optimization basierend auf Material
- Toolpath Smoothing
- Ramping Entry/Exit
- Tab-Placement Vorschläge
- Erkennung von Kollisionsrisiken

### Option B: CNC Setup Assistant
```
User: "Ich möchte 10mm Sperrholz fräsen"
Agent:
  1. Empfiehlt Fräser (6mm Upcut Spirale)
  2. Empfiehlt Feeds & Speeds
  3. Empfiehlt Passes (3x 3.5mm)
  4. Generiert GRBL Settings
```

### Option C: Troubleshooting Agent
```
User: "Mein Fräser macht Geräusche beim Eintauchen"
Agent:
  1. Diagnose: Zu hoher Plunge Rate
  2. Lösung: Ramping aktivieren
  3. Automatische Anpassung im G-Code
```

### Option D: CAD-to-CAM Assistant (wie cadgent)
```
User: "Erstelle eine Tasche 50x30mm, 5mm tief"
Agent:
  1. Generiert FreeCAD Path Operation
  2. Exportiert G-Code
  3. Sendet an GRBL
```

---

## Technische Architektur-Vorschlag

```
┌─────────────────────────────────────────────────────────┐
│                    RouterKing Workbench                  │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │  GRBL       │  │  G-Code     │  │  AI Agent       │  │
│  │  Sender     │  │  Parser     │  │  Module         │  │
│  └─────────────┘  └─────────────┘  └────────┬────────┘  │
│                                              │           │
│  ┌───────────────────────────────────────────▼────────┐  │
│  │                   AI Agent Core                     │  │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────┐  │  │
│  │  │ OpenAI/    │  │ Tool       │  │ Context      │  │  │
│  │  │ Anthropic  │  │ Definitions│  │ Manager      │  │  │
│  │  │ API        │  │ (G-Code,   │  │ (Scene,      │  │  │
│  │  │            │  │  GRBL,     │  │  Machine,    │  │  │
│  │  │            │  │  Material) │  │  History)    │  │  │
│  │  └────────────┘  └────────────┘  └──────────────┘  │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                     Chat UI Panel                    │  │
│  │  [User Input] ──────────────────────────────────────│  │
│  │  [AI Response with Actions] ────────────────────────│  │
│  │  [Execute] [Modify] [Cancel] ───────────────────────│  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Empfehlung

### Kurzfristig (MVP):
1. **cadgent als Inspiration** für Chat-UI und LLM-Integration
2. **Fokus auf G-Code Optimierung** (einzigartiger USP!)
3. **OpenAI API** mit Function Calling

### Langfristig:
1. **CAD-Assistant Tools** integrieren (akademisch fundiert)
2. **Lokale LLMs** (Ollama) als Option
3. **RAG** mit FreeCAD/GRBL Dokumentation

---

## Nächste Schritte

- [ ] Chief AI Review dieser Analyse
- [ ] Entscheidung: Welche Option (A/B/C/D)?
- [ ] API Key Management (OpenAI/Anthropic)
- [ ] Prototyp: Chat Panel in RouterKing
- [ ] Tool Definitions für G-Code/GRBL

---

## Risiken

1. **API Kosten** – OpenAI/Anthropic Nutzung kostet Geld
2. **Latenz** – API Calls dauern 1-5 Sekunden
3. **Offline-Nutzung** – Nicht möglich ohne lokales LLM
4. **Halluzinationen** – LLM könnte ungültigen G-Code generieren

---

## Fazit

**Die Arbeit ist NICHT umsonst!**

RouterKing hat eine **einzigartige Nische**: AI-gestützte CNC/Laser Workflows.
Kein existierendes Projekt kombiniert:
- FreeCAD Workbench
- GRBL Sender
- AI Agent für G-Code Optimierung

**Empfehlung:** Mit Option A (G-Code Optimierung) starten, da dies den größten Mehrwert bietet und kein anderes Projekt dies macht.
