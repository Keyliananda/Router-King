"""Local feedback storage for RouterKing AI tools."""

from datetime import datetime, timezone
import json
import os

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None


SCHEMA_VERSION = 1


def record_feedback(key, accepted, meta=None):
    if not key:
        return 1.0
    data = load_feedback()
    entry = data["entries"].setdefault(key, {"accepted": 0, "rejected": 0, "weight": 1.0})
    if accepted:
        entry["accepted"] += 1
    else:
        entry["rejected"] += 1
    entry["weight"] = _calculate_weight(entry["accepted"], entry["rejected"])
    entry["updated_at"] = _timestamp()
    if meta:
        entry["last_meta"] = meta
    save_feedback(data)
    return entry["weight"]


def get_weight(key, default=1.0):
    if not key:
        return default
    data = load_feedback()
    entry = data.get("entries", {}).get(key)
    if not entry:
        return default
    return float(entry.get("weight", default))


def apply_issue_weights(issues):
    if not issues:
        return []
    data = load_feedback()
    entries = data.get("entries", {})
    for issue in issues:
        key = getattr(issue, "feedback_key", "")
        if not key:
            continue
        entry = entries.get(key)
        if entry:
            issue.weight = float(entry.get("weight", issue.weight))
    return sorted(issues, key=lambda issue: issue.weight, reverse=True)


def load_feedback():
    path = get_feedback_path()
    if not os.path.exists(path):
        return {"schema": SCHEMA_VERSION, "entries": {}}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {"schema": SCHEMA_VERSION, "entries": {}}
    if not isinstance(data, dict):
        return {"schema": SCHEMA_VERSION, "entries": {}}
    data.setdefault("schema", SCHEMA_VERSION)
    data.setdefault("entries", {})
    return data


def save_feedback(data):
    path = get_feedback_path()
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def get_feedback_path():
    if App is not None and hasattr(App, "getUserAppDataDir"):
        base = App.getUserAppDataDir()
    else:
        base = os.path.join(os.path.expanduser("~"), ".routerking")
    return os.path.join(base, "ai_feedback.json")


def _calculate_weight(accepted, rejected):
    total = accepted + rejected
    if total <= 0:
        return 1.0
    return (accepted + 1) / (total + 2)


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
