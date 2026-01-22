"""Configuration helpers for RouterKing AI tools."""

import os

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None


DEFAULT_CONFIG = {
    "analysis": {
        "max_poles_warning": 20,
        "corner_angle_warn_deg": 30.0,
        "min_radius_warn": 0.5,
    },
    "provider": {
        "name": "openai",
        "openai_api_key": "",
        "openai_base_url": "https://api.openai.com/v1",
    },
    "logging": {
        "level": "INFO",
    },
}


def load_config():
    if App is None:
        config = {key: value.copy() for key, value in DEFAULT_CONFIG.items()}
        _apply_env_overrides(config)
        return config

    config = {key: value.copy() for key, value in DEFAULT_CONFIG.items()}
    params = App.ParamGet("User parameter:BaseApp/Preferences/RouterKing/AI")
    config["analysis"]["max_poles_warning"] = params.GetInt(
        "max_poles_warning", config["analysis"]["max_poles_warning"]
    )
    config["analysis"]["corner_angle_warn_deg"] = params.GetFloat(
        "corner_angle_warn_deg", config["analysis"]["corner_angle_warn_deg"]
    )
    config["analysis"]["min_radius_warn"] = params.GetFloat(
        "min_radius_warn", config["analysis"]["min_radius_warn"]
    )
    config["provider"]["name"] = params.GetString("provider", config["provider"]["name"])
    config["provider"]["openai_api_key"] = params.GetString(
        "openai_api_key", config["provider"]["openai_api_key"]
    )
    config["provider"]["openai_base_url"] = params.GetString(
        "openai_base_url", config["provider"]["openai_base_url"]
    )
    config["logging"]["level"] = params.GetString("log_level", config["logging"]["level"])
    _apply_env_overrides(config)
    return config


def _apply_env_overrides(config):
    api_key = os.environ.get("ROUTERKING_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        config["provider"]["openai_api_key"] = api_key

    base_url = os.environ.get("ROUTERKING_OPENAI_BASE_URL")
    if base_url:
        config["provider"]["openai_base_url"] = base_url
