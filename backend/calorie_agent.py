"""LLM adapter for /cal image analysis."""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Any

import requests

CALORIE_PROMPT = (
    "画像内の食事を解析し、必ずJSONのみで返してください。"
    "スキーマ: "
    '{"schema_version":"calorie_v1","items":[{"food_name":"string|null","calorie":0}],"total_calorie":0}'
)


class CalorieAgentError(RuntimeError):
    """General calorie agent error."""


class CalorieConfigError(CalorieAgentError):
    """Configuration error for calorie agent."""


class CalorieImageParseError(CalorieAgentError):
    """Image parsing / JSON parsing error."""


def _extract_json_text(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text:
        raise CalorieImageParseError("LLM response was empty")

    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        candidate = text[idx : idx + end].strip()
        json.loads(candidate)
        return candidate

    raise CalorieImageParseError("JSON object not found in LLM response")


def _extract_openai_content(body: dict[str, Any]) -> str:
    choices = body.get("choices", [])
    if not isinstance(choices, list) or not choices:
        raise CalorieImageParseError("OpenAI response has no choices")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [str(part.get("text", "")) for part in content if isinstance(part, dict)]
        return "".join(parts).strip()
    return str(content or "")


def _extract_gemini_content(body: dict[str, Any]) -> str:
    candidates = body.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        raise CalorieImageParseError("Gemini response has no candidates")
    content = candidates[0].get("content", {})
    parts = content.get("parts", []) if isinstance(content, dict) else []
    texts = [str(part.get("text", "")) for part in parts if isinstance(part, dict)]
    text = "".join(texts).strip()
    if not text:
        raise CalorieImageParseError("Gemini response text was empty")
    return text


def _analyze_with_openai(image_bytes: bytes, mime_type: str) -> tuple[dict[str, Any], str, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise CalorieConfigError("OPENAI_API_KEY is not configured")

    model = os.getenv("CALORIE_OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{image_b64}"
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": CALORIE_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    }
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise CalorieAgentError(f"OpenAI returned non-JSON response: {response.status_code}") from exc
    if response.status_code >= 400:
        raise CalorieAgentError(f"OpenAI API error: {body}")

    raw_text = _extract_openai_content(body)
    raw_json = _extract_json_text(raw_text)
    parsed = json.loads(raw_json)
    if not isinstance(parsed, dict):
        raise CalorieImageParseError("OpenAI response JSON is not an object")
    return parsed, raw_json, model


def _analyze_with_gemini(image_bytes: bytes, mime_type: str) -> tuple[dict[str, Any], str, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise CalorieConfigError("GEMINI_API_KEY is not configured")

    model = os.getenv("CALORIE_GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": CALORIE_PROMPT},
                    {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                ]
            }
        ]
    }
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": api_key},
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    try:
        body = response.json()
    except ValueError as exc:
        raise CalorieAgentError(f"Gemini returned non-JSON response: {response.status_code}") from exc
    if response.status_code >= 400:
        raise CalorieAgentError(f"Gemini API error: {body}")

    raw_text = _extract_gemini_content(body)
    raw_json = _extract_json_text(raw_text)
    parsed = json.loads(raw_json)
    if not isinstance(parsed, dict):
        raise CalorieImageParseError("Gemini response JSON is not an object")
    return parsed, raw_json, model


def analyze_calorie(image_bytes: bytes, mime_type: str) -> tuple[dict[str, Any], str, str, str]:
    """Analyze meal image via OpenAI/Gemini and return parsed JSON + raw JSON string."""
    provider = os.getenv("CALORIE_PROVIDER", "openai").strip().lower() or "openai"
    if provider == "openai":
        parsed, raw_json, model = _analyze_with_openai(image_bytes, mime_type)
        return parsed, raw_json, provider, model
    if provider == "gemini":
        parsed, raw_json, model = _analyze_with_gemini(image_bytes, mime_type)
        return parsed, raw_json, provider, model
    raise CalorieConfigError(f"Unsupported CALORIE_PROVIDER: {provider}")

