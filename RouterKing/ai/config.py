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
    "optimization": {
        "target_poles": 12,
        "sample_points": 60,
        "max_degree": 3,
        "tolerance": 0.05,
    },
    "provider": {
        "name": "openai",
        "openai_api_key": "",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-4o-mini",
        "openai_reasoning_effort": "off",
    },
    "chat": {
        "system_prompt": "You are RouterKing AI, a helpful assistant for FreeCAD CNC workflows.",
        "temperature": 0.2,
        "max_output_tokens": 512,
    },
    "cam": {
        "safe_z_height": 3.0,
        "min_arc_radius": 0.5,
        "tool_radius": 1.0,
        "max_plunge_step": 2.0,
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
    config["optimization"]["target_poles"] = params.GetInt(
        "opt_target_poles", config["optimization"]["target_poles"]
    )
    config["optimization"]["sample_points"] = params.GetInt(
        "opt_sample_points", config["optimization"]["sample_points"]
    )
    config["optimization"]["max_degree"] = params.GetInt(
        "opt_max_degree", config["optimization"]["max_degree"]
    )
    config["optimization"]["tolerance"] = params.GetFloat(
        "opt_tolerance", config["optimization"]["tolerance"]
    )
    config["provider"]["name"] = params.GetString("provider", config["provider"]["name"])
    config["provider"]["openai_api_key"] = params.GetString(
        "openai_api_key", config["provider"]["openai_api_key"]
    )
    config["provider"]["openai_base_url"] = params.GetString(
        "openai_base_url", config["provider"]["openai_base_url"]
    )
    config["provider"]["openai_model"] = params.GetString(
        "openai_model", config["provider"]["openai_model"]
    )
    config["provider"]["openai_reasoning_effort"] = params.GetString(
        "openai_reasoning_effort", config["provider"]["openai_reasoning_effort"]
    )
    config["chat"]["system_prompt"] = params.GetString(
        "system_prompt", config["chat"]["system_prompt"]
    )
    config["chat"]["temperature"] = params.GetFloat(
        "temperature", config["chat"]["temperature"]
    )
    config["chat"]["max_output_tokens"] = params.GetInt(
        "max_output_tokens", config["chat"]["max_output_tokens"]
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

    model = os.environ.get("ROUTERKING_OPENAI_MODEL")
    if model:
        config["provider"]["openai_model"] = model

    effort = os.environ.get("ROUTERKING_OPENAI_REASONING_EFFORT")
    if effort:
        config["provider"]["openai_reasoning_effort"] = effort
