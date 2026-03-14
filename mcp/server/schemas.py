"""Shared schemas and payload helpers for the RouterKing MCP layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence


@dataclass(frozen=True)
class ActionDefinition:
    name: str
    description: str
    required_params: Sequence[str] = field(default_factory=tuple)
    optional_params: Sequence[str] = field(default_factory=tuple)
    risk_class: str = "modify"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required_params": list(self.required_params),
            "optional_params": list(self.optional_params),
            "risk_class": self.risk_class,
        }


@dataclass
class ToolResponse:
    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "errors": self.errors,
        }


def make_response(
    success: bool,
    message: str,
    data: Mapping[str, Any] | None = None,
    errors: Iterable[str] | None = None,
) -> Dict[str, Any]:
    return ToolResponse(
        success=bool(success),
        message=message,
        data=dict(data or {}),
        errors=[str(error) for error in (errors or []) if str(error)],
    ).to_dict()


def normalize_actions_payload(payload: Any) -> tuple[List[Dict[str, Any]], List[str]]:
    if payload is None:
        return [], ["Expected an action object, a list of actions, or {'actions': [...]}."]

    if isinstance(payload, list):
        return list(payload), []

    if isinstance(payload, Mapping):
        if isinstance(payload.get("actions"), list):
            return list(payload["actions"]), []
        if payload.get("type") or payload.get("action"):
            return [dict(payload)], []
        return [], ["Payload object must contain 'actions' or a single action 'type'."]

    return [], ["Unsupported payload type for actions."]


def coerce_action(action: Any) -> tuple[Dict[str, Any], List[str]]:
    if not isinstance(action, Mapping):
        return {}, ["Action must be an object."]

    action_type = str(action.get("type") or action.get("action") or "").strip()
    if not action_type:
        return {}, ["Action is missing a type."]

    raw_params = action.get("params")
    params = dict(raw_params) if isinstance(raw_params, Mapping) else {}
    normalized = dict(action)
    normalized["type"] = action_type
    normalized["params"] = params
    return normalized, []


def get_action_param(action: Mapping[str, Any], key: str, default: Any = None) -> Any:
    if key in action:
        return action.get(key)
    params = action.get("params")
    if isinstance(params, Mapping) and key in params:
        return params.get(key)
    return default

