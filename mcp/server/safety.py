"""Risk classes and safety guards for RouterKing MCP tools."""

from __future__ import annotations

import logging
from typing import Any, Mapping


LOG = logging.getLogger("routerking.mcp.safety")

RISK_READ = "read"
RISK_MODIFY = "modify"
RISK_MACHINE = "machine"
RISK_DANGEROUS_DEV = "dangerous_dev"

RISK_CLASSES = {
    RISK_READ,
    RISK_MODIFY,
    RISK_MACHINE,
    RISK_DANGEROUS_DEV,
}


def validate_risk(
    tool_name: str,
    risk_class: str,
    payload: Mapping[str, Any] | None = None,
    *,
    dev_tools_enabled: bool = False,
) -> list[str]:
    payload = payload or {}

    if risk_class not in RISK_CLASSES:
        return [f"{tool_name}: unsupported risk class '{risk_class}'."]

    if risk_class == RISK_DANGEROUS_DEV and not dev_tools_enabled:
        return [f"{tool_name}: dangerous development tools are disabled."]

    if risk_class == RISK_MACHINE:
        return validate_machine_confirmation(tool_name, payload)

    return []


def validate_machine_confirmation(tool_name: str, payload: Mapping[str, Any]) -> list[str]:
    errors = []
    confirm = _get_value(payload, "confirm")
    if not bool(confirm):
        errors.append(f"{tool_name}: confirm=true required.")

    reason = str(_get_value(payload, "reason") or "").strip()
    if not reason:
        errors.append(f"{tool_name}: reason is required.")

    return errors


def log_tool_request(tool_name: str, risk_class: str, payload: Mapping[str, Any] | None = None) -> None:
    if risk_class not in {RISK_MODIFY, RISK_MACHINE, RISK_DANGEROUS_DEV}:
        return
    LOG.info("tool=%s risk=%s payload=%s", tool_name, risk_class, dict(payload or {}))


def _get_value(payload: Mapping[str, Any], key: str) -> Any:
    if key in payload:
        return payload.get(key)
    params = payload.get("params")
    if isinstance(params, Mapping) and key in params:
        return params.get(key)
    return None
