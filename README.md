# RouterKing 👑

**Der intelligente KI-Copilot für CNC- und Laser-Fertigung in FreeCAD**

RouterKing ist eine spezialisierte FreeCAD-Workbench, die den gesamten Workflow von der 2D/3D-Konstruktion bis zum fertigen G-Code durch den Einsatz von Large Language Models (LLMs) und einer integrierten GRBL-Steuerung optimiert.

## 🚀 Haupt-Features im Detail

### 1. KI-Chat-Assistent & Copilot
Ein integriertes Side-Panel, das nicht nur chattet, sondern aktiv auf die FreeCAD-Dokumentstruktur zugreift.
*   **Kontext-Bewusstsein**: Die KI "sieht", was du ausgewählt hast (Kanten, Flächen, Skizzen).
*   **Fehlerdiagnose**: Erkennt instabile Skizzen oder fehlerhafte "Pad"-Operationen und schlägt Lösungen vor.
*   **Automatisierung**: Erstellung von Geometrie durch natürliche Sprache.

### 2. G-Code Optimizer & CAM-Integration
RouterKing schließt die Lücke zwischen CAD und Maschine:
*   **Corner Smoothing**: Automatische Reduktion des Vorschubs in scharfen Kurven zur Vermeidung von Schrittverlusten und Brandspuren.
*   **Ramping & Lead-In**: Intelligentes Eintauchen in das Material statt vertikalem Plunge.
*   **G-Code Risk Check**: Analyse von Rapid-Moves (G0) und potenziellen Kollisionen vor dem Frässtart.

### 3. CNC Setup Assistant
Materialdatenbank-gestützte Empfehlungen für:
*   **Feeds & Speeds**: Berechnung von Vorschub und Drehzahl basierend auf Fräser-Durchmesser und Material (Sperrholz, Alu, Acryl).
*   **Zustellung (Step-down)**: Vorschläge für die maximale Tiefe pro Durchgang zur Schonung des Werkzeugs.

### 4. Integrierter GRBL-Sender
Direkte Steuerung deiner CNC-Maschine aus FreeCAD heraus:
*   **Echtzeit-Monitoring**: Status-Abfrage (Idle, Run, Alarm) und Positionsanzeige.
*   **Jog-Control**: Manuelles Verfahren der Achsen und Nullpunktsetzung.
*   **Konsolen-Zugriff**: Direktes Senden von G-Code Befehlen an die Maschine.

## 🤖 KI-Werkzeuge & Fähigkeiten (Tools)

Die KI verfügt über spezifische "Tools" und Logiken, um aktiv in den Workflow einzugreifen:

### Geometrie-Aktionen (Primitives)
Die KI kann direkt Python-Befehle in FreeCAD ausführen, um Objekte zu erstellen:
*   `Box`: Erstellung von Quadern (z.B. "Erstelle eine Box 20x30x5").
*   `Cylinder`: Erstellung von Zylindern mit Radius/Durchmesser-Erkennung.
*   `Sphere`: Erstellung von Kugeln.
*   **Test-Part**: Automatisches Erzeugen eines Standard-Testobjekts für G-Code-Tests.

### Kontext-Extraktion (`AssistantContext`)
Bei jeder Anfrage werden folgende Daten an die KI übermittelt:
*   **Selektions-Details**: Anzahl der Kanten/Flächen des gewählten Objekts.
*   **Skizzen-Status**: Ist die Skizze "Fully Constrained"? Wie viele Constraints und Geometrie-Elemente sind vorhanden?
*   **Dokument-Metadaten**: Name des aktiven Dokuments und des aktiven Objekts.
*   **Warnungen**: Aktuelle Fehlermeldungen aus der FreeCAD-Konsole.

### Regelbasierte Experten-Logik
Bevor ein teurer LLM-Call erfolgt, prüft RouterKing lokale Regeln für:
*   **Pad-Fehler**: Analyse von offenen Konturen oder Selbstüberschneidungen.
*   **Spline-Optimierung**: Vorschläge zur Glättung von Kurven für flüssigere Fräsbewegungen.
*   **CAM-Check**: Prüfung auf riskante Rapid-Moves im geladenen G-Code.

## 💰 Dynamisches Pricing & Modelle

RouterKing unterstützt eine Vielzahl von Modellen mit integrierter Kostenkontrolle:
*   **Modelle**: GPT-5.2 (Pro/Mini), GPT-4o, Claude 3.5, sowie lokale Modelle via **Ollama** (Llama 3, Mistral).
*   **Preis-Indikatoren**: Im Dropdown wird die relative Kostenkategorie angezeigt:
    *   `$` : Sehr günstig (z.B. gpt-4o-mini)
    *   `$$$$` : High-End Reasoning (z.B. gpt-5.2-pro)
*   **Transparenz**: Vor dem Speichern von Einstellungen werden Kostenindikatoren automatisch bereinigt, um die API-Kompatibilität zu wahren.

## � Technische Architektur

1.  **UI-Layer**: Qt-basiertes Dock-Widget in FreeCAD.
2.  **AI-Core**: Hybrides System aus `assistant.py` (Regeln) und `client.py` (LLM-Kommunikation).
3.  **Action-System**: JSON-basiertes Protokoll (`routerking_actions`), mit dem die KI Änderungen am FreeCAD-Modell vornimmt.
4.  **Hardware-Layer**: Serial-Kommunikation mit GRBL-basierten Controllern.

## 📂 Weiterführende Dokumentation

Detaillierte Konzepte findest du im `docs/` Verzeichnis:
*   Vision & Konzept - Die langfristige Strategie.
*   Roadmap - Geplante Features und Meilensteine.
*   Test-Workflow Guide - Schritt-für-Schritt von DXF zu G-Code.
*   CAM Reality Check - Analyse der FreeCAD CAM-Architektur.
*   Pricing Logic - Details zur Kostenberechnung.

## 🔧 Installation

1.  Repository klonen:
    ```bash
    cd ~/Library/Application\ Support/FreeCAD/Mod  # macOS
    # oder ~/.local/share/FreeCAD/Mod             # Linux
    git clone https://github.com/dein-repo/Router-King.git
    ```
2.  Abhängigkeiten: RouterKing bringt wichtige Bibliotheken (wie `pyserial`) im `vendor/` Ordner mit.
3.  FreeCAD starten und Workbench **RouterKing** wählen.
4.  In den **AI Settings** API-Key hinterlegen (für OpenAI/Anthropic) oder Ollama-URL angeben.

## 📈 Projektstatus

*   **Status**: Phase 1 (MVP)
*   **KI**: Chat-Integration, Kontext-Analyse und Primitive-Erstellung stabil.
*   **CAM**: G-Code Parser und GRBL-Sender funktional.
*   **Nächster Schritt**: Vertiefung der G-Code Optimierungs-Algorithmen (Phase 2).

---
*Entwickelt für Maker, Profis und FreeCAD-Enthusiasten.*