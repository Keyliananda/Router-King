"""Simple audit log helpers for RouterKing AI tools."""

from datetime import datetime, timezone
import os

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None


def format_report_entry(action, result, details=None):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    summary = getattr(result, "summary", "") or "No summary."
    stats = getattr(result, "stats", {}) or {}
    issues = getattr(result, "issues", []) or []
    lines = [f"[{timestamp}] {action}", f"Summary: {summary}"]
    if stats:
        stats_text = ", ".join(f"{key}={value}" for key, value in stats.items())
        lines.append(f"Stats: {stats_text}")
    if details:
        lines.append(f"Details: {details}")
    if issues:
        lines.append("Issues:")
        for issue in issues:
            message = getattr(issue, "message", str(issue))
            severity = getattr(issue, "severity", "info")
            lines.append(f"- {severity}: {message}")
    return "\n".join(lines) + "\n"


def append_report(entry):
    path = get_report_path()
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(entry)


def load_report(max_bytes=200000):
    path = get_report_path()
    if not os.path.exists(path):
        return ""
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        if size > max_bytes:
            handle.seek(-max_bytes, os.SEEK_END)
            data = handle.read()
            prefix = b"... (truncated)\n"
            return (prefix + data).decode("utf-8", errors="replace")
        return handle.read().decode("utf-8", errors="replace")


def clear_report():
    path = get_report_path()
    if os.path.exists(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("")


def get_report_path():
    if App is not None and hasattr(App, "getUserAppDataDir"):
        base = App.getUserAppDataDir()
    else:
        base = os.path.join(os.path.expanduser("~"), ".routerking")
    return os.path.join(base, "ai_audit.log")
