# Dynamic Model Loading - OpenAI API

**Date:** 2026-01-26  
**Status:** Implemented  
**Chief AI Review:** Not required (minor improvement)

## Problem

Die RouterKing AI-Integration zeigte nur veraltete Modelle (gpt-4o, gpt-4o-mini) an, obwohl OpenAI bereits die GPT-5-Serie veröffentlicht hat.

## Solution

### Bereits implementiert (keine Änderung nötig)

Das System lädt **bereits dynamisch** alle verfügbaren Modelle von der OpenAI API:

```python
# In RouterKing/ai/client.py
def list_models(api_key, base_url):
    url = f"{base}/models"
    payload = _get_json(url, api_key)
    # Returns all model IDs from OpenAI API
```

Die API-Dokumentation: https://platform.openai.com/docs/api-reference/models/list

### Durchgeführte Verbesserungen

1. **Erweiterte Default-Modellliste** (`RouterKing/ui/main_dock.py`):
   ```python
   _DEFAULT_AI_MODELS = ["gpt-5.2", "gpt-5-mini", "gpt-4o", "gpt-4o-mini"]
   ```

2. **Erweiterte Shortlist** mit allen GPT-5-Varianten:
   - gpt-5.2, gpt-5.2-pro
   - gpt-5.1, gpt-5, gpt-5-pro
   - gpt-5-mini, gpt-5-nano
   - o4-mini, o3, o3-mini, o3-pro

3. **Zukunftssichere Sortierung**:
   ```python
   _AI_MODEL_PREFIX_ORDER = [
       "gpt-6", "gpt-5", "gpt-4.1", "gpt-4o", 
       "o5", "o4", "o3", "o2", "o1", 
       "gpt-4", "gpt-3.5"
   ]
   ```
   - Berücksichtigt bereits GPT-6 und o5 für zukünftige Releases

4. **Verbesserte Dokumentation** in `_is_ai_chat_model()`:
   - Klarere Kommentare zur Filterlogik
   - Regex `^o\d` erkennt automatisch alle o-series Modelle (o1, o2, o3, o4, o5, etc.)

## Wie es funktioniert

1. **Beim Klick auf "Refresh"**:
   - System ruft `GET https://api.openai.com/v1/models` auf
   - Erhält alle verfügbaren Modelle (inkl. neue Releases)

2. **Filterung**:
   - Schließt Fine-tuned-Modelle aus (`ft:*`)
   - Schließt spezialisierte Modelle aus (audio, vision, embeddings, etc.)
   - **Inkludiert automatisch alle neuen GPT-X und oX Modelle**

3. **Sortierung**:
   - Priorisiert Modelle nach `_AI_MODEL_PREFIX_ORDER`
   - Neuere Modelle (höhere Versionsnummern) erscheinen zuerst
   - Zeigt maximal 12 Modelle im Dropdown

## Verfügbare GPT-5 Modelle (Stand 2026-01-26)

Laut OpenAI-Dokumentation:
- **gpt-5.2** - Bestes Modell für Coding und agentic tasks
- **gpt-5.2-pro** - Noch intelligentere Version
- **gpt-5.1** - Vorgängerversion mit konfigurierbarem reasoning effort
- **gpt-5** - Ältere GPT-5 Version
- **gpt-5-mini** - Schneller und kostengünstiger
- **gpt-5-nano** - Am schnellsten und günstigsten

## Testing

Nach FreeCAD-Neustart:
1. RouterKing Workbench öffnen
2. AI Settings → "Refresh" Button klicken
3. Model-Dropdown sollte alle GPT-5-Modelle zeigen

## Preisanzeige im Dropdown

### Problem

Benutzer können nicht auf einen Blick erkennen, welche Modelle teuer oder günstig sind.

### Lösung

Implementierung eines dynamischen Pricing-Systems mit visuellen Kostenindikatoren:

```python
# RouterKing/ai/pricing.py
def calculate_cost_tier(model_id: str) -> str:
    """
    Berechnet die Kostenkategorie basierend auf Perzentilen.
    Bleibt zukunftssicher, da die Kategorien relativ sind.
    """
```

**Kostenindikatoren:**
- `$` - Bottom 25% (sehr günstig): gpt-5-nano, gpt-4o-mini, gpt-4.1-nano
- `$$` - 25-50% (günstig): gpt-5-mini, gpt-4.1-mini
- `$$$` - 50-75% (moderat): gpt-5, gpt-4o, gpt-4.1
- `$$$$` - Top 25% (teuer): gpt-5.2-pro, o1-pro, o3-pro

**Beispiel im Dropdown:**
```
gpt-5.2 ($$$$)
gpt-5-mini ($$)
gpt-5-nano ($)
gpt-4o ($$$)
gpt-4o-mini ($)
```

### Zukunftssicherheit

**Dynamische Perzentil-Berechnung:**
1. System sammelt alle bekannten Modellpreise
2. Berechnet Perzentile (25%, 50%, 75%)
3. Kategorisiert Modelle relativ zu allen anderen

**Wenn neue Modelle kommen:**
- ✅ Preise werden in `_MODEL_PRICING` hinzugefügt
- ✅ Perzentile werden automatisch neu berechnet
- ✅ Kategorien bleiben relativ korrekt

**Beispiel:** Wenn GPT-6 mit Preis $50/1M tokens kommt:
- Wird als `$$$$` kategorisiert (teurer als alles andere)
- Andere Modelle bleiben in ihren relativen Kategorien
- Keine manuelle Anpassung der Schwellenwerte nötig

### Wartung

**Regelmäßige Updates erforderlich:**
- Preise müssen manuell aus https://platform.openai.com/docs/pricing aktualisiert werden
- Neue Modelle müssen zu `_MODEL_PRICING` hinzugefügt werden
- **Empfehlung:** Quartalsweise Überprüfung der Preise

**Automatisierungsmöglichkeit (zukünftig):**
- OpenAI bietet **keine** Pricing-API
- Könnte via Web-Scraping automatisiert werden
- Oder: Community-gepflegte Pricing-Datenbank

## Zukünftige Wartung

### Modelle (automatisch)

**Keine manuelle Wartung erforderlich!** 

Wenn OpenAI neue Modelle released (z.B. GPT-6, o5):
- ✅ Werden automatisch von der API geladen
- ✅ Werden automatisch gefiltert (wenn sie `gpt-` oder `o\d` Prefix haben)
- ✅ Werden automatisch sortiert (Prefix-Order bereits vorbereitet)

Nur bei **Breaking Changes** in OpenAI's Namensschema müsste `_is_ai_chat_model()` angepasst werden.

### Preise (manuell)

**Quartalsweise Wartung empfohlen:**

1. Besuche https://platform.openai.com/docs/pricing
2. Aktualisiere `RouterKing/ai/pricing.py` → `_MODEL_PRICING`
3. Füge neue Modelle hinzu
4. Teste mit `pytest tests/test_ai_pricing.py`

## References

- OpenAI Models API: https://platform.openai.com/docs/api-reference/models/list
- OpenAI Pricing: https://platform.openai.com/docs/pricing
- OpenAI Models Overview: https://platform.openai.com/docs/models
- Code: 
  - `RouterKing/ui/main_dock.py` (Zeilen 63-77, 2211-2241, 2247-2256)
  - `RouterKing/ai/pricing.py` (Neues Modul)
  - `tests/test_ai_pricing.py` (Tests)
