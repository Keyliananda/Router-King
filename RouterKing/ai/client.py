"""Minimal OpenAI client helpers for RouterKing AI chat."""

import json
import urllib.error
import urllib.request


DEFAULT_TIMEOUT = 60


def list_models(api_key, base_url):
    if not api_key:
        raise ValueError("Missing API key. Set it in AI settings or via ROUTERKING_OPENAI_API_KEY.")

    base = base_url.rstrip("/")
    url = f"{base}/models"
    payload = _get_json(url, api_key)
    data = payload.get("data", []) if isinstance(payload, dict) else []
    models = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if model_id:
            models.append(model_id)
    return models


def send_chat_request(
    api_key,
    base_url,
    model,
    messages,
    reasoning_effort="off",
    temperature=0.2,
    max_output_tokens=None,
):
    if not api_key:
        raise ValueError("Missing API key. Set it in AI settings or via ROUTERKING_OPENAI_API_KEY.")

    base = base_url.rstrip("/")
    if _uses_responses_api(model):
        url = f"{base}/responses"
        payload = {"model": model, "input": messages}
        if reasoning_effort and reasoning_effort != "off":
            payload["reasoning"] = {"effort": reasoning_effort}
        if max_output_tokens:
            payload["max_output_tokens"] = max_output_tokens
        return _post_json(url, api_key, payload, extractor=_extract_response_text)

    url = f"{base}/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if max_output_tokens:
        payload["max_tokens"] = max_output_tokens
    return _post_json(url, api_key, payload, extractor=_extract_chat_text)


def _post_json(url, api_key, payload, extractor):
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8") if exc.fp else str(exc)
        raise RuntimeError(f"OpenAI request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc

    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise RuntimeError("OpenAI response was not valid JSON.") from exc

    text = extractor(payload)
    if not text:
        raise RuntimeError("OpenAI response did not include any text output.")
    return text


def _get_json(url, api_key):
    headers = {"Authorization": f"Bearer {api_key}"}
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8") if exc.fp else str(exc)
        raise RuntimeError(f"OpenAI request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc

    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise RuntimeError("OpenAI response was not valid JSON.") from exc
    return payload


def _uses_responses_api(model):
    lowered = (model or "").lower()
    return lowered.startswith("o1") or lowered.startswith("o3")


def _extract_chat_text(payload):
    choices = payload.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    return message.get("content", "") or ""


def _extract_response_text(payload):
    text = payload.get("output_text")
    if text:
        return text
    output = payload.get("output", [])
    for item in output:
        for content in item.get("content", []):
            value = content.get("text")
            if value:
                return value
    return ""
