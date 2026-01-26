# Pricing Indicators für Model-Dropdown

**Date:** 2026-01-26  
**Status:** Implemented  
**Chief AI Review:** Recommended (neue Feature)

## Zusammenfassung

Implementierung von dynamischen Kostenindikatoren im Model-Dropdown, die Benutzern auf einen Blick zeigen, wie teuer ein Modell ist.

## Problem

Benutzer können nicht auf einen Blick erkennen, welche Modelle teuer oder günstig sind. Dies führt zu:
- Unerwarteten Kosten bei Verwendung teurer Modelle
- Suboptimaler Modellwahl für einfache Tasks
- Fehlender Transparenz über Preisunterschiede

## Lösung

### 1. Neues Pricing-Modul (`RouterKing/ai/pricing.py`)

Enthält:
- **Pricing-Datenbank**: Alle aktuellen OpenAI-Modellpreise (Stand 2026-01-26)
- **Dynamische Kategorisierung**: Perzentil-basierte Kostenkategorien
- **Zukunftssichere Logik**: Relative Kategorien bleiben korrekt

```python
# Beispiel-Nutzung
from RouterKing.ai.pricing import format_model_with_cost

formatted = format_model_with_cost("gpt-5.2")
# Output: "gpt-5.2 ($$$$)"

formatted = format_model_with_cost("gpt-5-nano")
# Output: "gpt-5-nano ($)"
```

### 2. UI-Integration

**Änderungen in `RouterKing/ui/main_dock.py`:**

1. **`_apply_ai_model_items()`** - Fügt Kostenindikatoren hinzu:
   ```python
   formatted_models = [format_model_with_cost(m) for m in models]
   self._ai_model.addItems(formatted_models)
   ```

2. **`_on_ai_settings_save()`** - Entfernt Kostenindikatoren vor dem Speichern:
   ```python
   model_name = re.sub(r'\s*\([$$]+\)\s*$', '', model_text)
   params.SetString("openai_model", model_name)
   ```

### 3. Kostenkategorien

**Dynamische Perzentil-basierte Kategorisierung:**

| Kategorie | Perzentil | Beispiele | Typische Kosten |
|-----------|-----------|-----------|-----------------|
| `$` | Bottom 25% | gpt-5-nano, gpt-4o-mini, gpt-4.1-nano | $0.05 - $0.50 / 1M tokens |
| `$$` | 25-50% | gpt-5-mini, gpt-4.1-mini | $0.50 - $2.00 / 1M tokens |
| `$$$` | 50-75% | gpt-5, gpt-4o, gpt-4.1, o3 | $2.00 - $10.00 / 1M tokens |
| `$$$$` | Top 25% | gpt-5.2-pro, o1-pro, o3-pro | $10.00+ / 1M tokens |

**Berechnungslogik:**
```python
# Gewichtete Kosten: Input (25%) + Output (75%)
# Spiegelt typische Nutzung wider (mehr Output als Input)
estimated_cost = input_price * 0.25 + output_price * 0.75
```

## Zukunftssicherheit

### Warum Perzentile statt feste Schwellenwerte?

**Problem mit festen Schwellenwerten:**
```python
# ❌ Nicht zukunftssicher
if cost < 1.0:
    return "$"
elif cost < 5.0:
    return "$$"
# Was passiert wenn alle neuen Modelle > $20 kosten?
```

**Lösung mit Perzentilen:**
```python
# ✅ Zukunftssicher
all_costs.sort()
p25 = all_costs[len(all_costs) // 4]
if estimated_cost <= p25:
    return "$"  # Immer die günstigsten 25%
```

### Beispiel-Szenario: GPT-6 Release

**Annahme:** GPT-6 kostet $50/1M tokens (Input)

**Ohne Perzentile:**
- GPT-6 würde als `$$$$` angezeigt (korrekt)
- Aber: gpt-5.2-pro ($21) wäre auch `$$$$` (zu ungenau)

**Mit Perzentilen:**
- GPT-6: `$$$$` (teuerste 25%)
- gpt-5.2-pro: `$$$` (rutscht runter, da GPT-6 teurer)
- gpt-5.2: `$$` (rutscht runter)
- Relative Verhältnisse bleiben korrekt!

## Implementierungsdetails

### Pricing-Datenbank

```python
_MODEL_PRICING = {
    "gpt-5.2": (1.75, 14.00),  # (Input, Output) per 1M tokens
    "gpt-5-mini": (0.25, 2.00),
    # ... alle Modelle
}
```

**Matching-Strategien:**
1. **Direkt**: `gpt-5.2` → exakte Übereinstimmung
2. **Datum-Suffix**: `gpt-4o-2024-08-06` → entfernt Datum, matched `gpt-4o`
3. **Varianten-Suffix**: `gpt-4o-mini-realtime` → matched `gpt-4o-mini`

### UI-Anzeige

**Dropdown zeigt:**
```
gpt-5.2 ($$$$)
gpt-5.2-pro ($$$$)
gpt-5.1 ($$$)
gpt-5 ($$$)
gpt-5-mini ($$)
gpt-5-nano ($)
```

**Gespeichert wird:**
```
gpt-5.2  ← Ohne Kostenindikator
```

## Testing

**Manuelle Tests:**
```bash
cd /Users/kilianvolz/Code/Router-King
python3 -c "
from RouterKing.ai.pricing import format_model_with_cost
print(format_model_with_cost('gpt-5.2'))
print(format_model_with_cost('gpt-5-nano'))
"
```

**Unit Tests:**
```bash
pytest tests/test_ai_pricing.py -v
```

Tests decken ab:
- ✅ Direkte Modell-Matches
- ✅ Datum-Suffix-Matches
- ✅ Varianten-Suffix-Matches
- ✅ Unbekannte Modelle
- ✅ Kostenkategorien
- ✅ Zukunftssicherheit (Perzentile)

## Zukünftige Wartung

### Modelle (automatisch)

**Keine manuelle Wartung erforderlich!** 

Wenn OpenAI neue Modelle released (z.B. GPT-6, o5):
- ✅ Werden automatisch von der API geladen
- ✅ Werden automatisch gefiltert (wenn sie `gpt-` oder `o\d` Prefix haben)
- ✅ Werden automatisch sortiert (Prefix-Order bereits vorbereitet)

Nur bei **Breaking Changes** in OpenAI's Namensschema müsste `_is_ai_chat_model()` angepasst werden.

### Preise (manuell - quartalsweise)

**Wartungsschritte:**

1. **Preise überprüfen:**
   - Besuche https://platform.openai.com/docs/pricing
   - Vergleiche mit `RouterKing/ai/pricing.py` → `_MODEL_PRICING`

2. **Neue Modelle hinzufügen:**
   ```python
   _MODEL_PRICING = {
       # ... existing models ...
       "gpt-6": (5.00, 40.00),  # Neue Modelle hier
       "gpt-6-mini": (1.00, 8.00),
   }
   ```

3. **Tests ausführen:**
   ```bash
   pytest tests/test_ai_pricing.py -v
   ```

4. **Visuell testen:**
   - FreeCAD starten
   - RouterKing Workbench öffnen
   - AI Settings → "Refresh" klicken
   - Dropdown überprüfen: Kostenindikatoren korrekt?

**Automatisierung (optional):**
- Web-Scraping von pricing page
- GitHub Action für wöchentliche Checks
- PR erstellen bei Preisänderungen

## Vorteile

1. **Transparenz**: Benutzer sehen sofort die Kosten
2. **Bessere Entscheidungen**: Günstige Modelle für einfache Tasks
3. **Kostenoptimierung**: Vermeidung unnötiger Kosten
4. **Zukunftssicher**: Perzentil-basiert, bleibt relativ korrekt

## Limitierungen

1. **Keine API für Preise**: OpenAI bietet keine Pricing-API
2. **Manuelle Wartung**: Preise müssen manuell aktualisiert werden
3. **Approximation**: Kosten hängen von Input/Output-Ratio ab
4. **Keine Batch/Flex-Preise**: Zeigt nur Standard-Tier-Preise

## Alternativen (nicht implementiert)

### Option 1: Absolute Preisanzeige
```
gpt-5.2 ($1.75/$14.00)
gpt-5-nano ($0.05/$0.40)
```
**Nachteil:** Zu viel Information, unübersichtlich

### Option 2: Nur Icon
```
gpt-5.2 💰💰💰💰
gpt-5-nano 💰
```
**Nachteil:** Weniger präzise, Unicode-Probleme

### Option 3: Farbcodierung
```
gpt-5.2 (rot)
gpt-5-nano (grün)
```
**Nachteil:** Schwierig in Qt ComboBox, Accessibility-Probleme

**Gewählte Lösung ($-Symbole):**
- ✅ Universell verständlich
- ✅ Kompakt
- ✅ Funktioniert in allen UIs
- ✅ Accessibility-freundlich

## References

- OpenAI Models API: https://platform.openai.com/docs/api-reference/models/list
- OpenAI Pricing: https://platform.openai.com/docs/pricing
- OpenAI Models Overview: https://platform.openai.com/docs/models
- Code: 
  - `RouterKing/ui/main_dock.py` (Zeilen 63-77, 2211-2241, 2247-2256, 2316-2330)
  - `RouterKing/ai/pricing.py` (Neues Modul)
  - `tests/test_ai_pricing.py` (Tests)
