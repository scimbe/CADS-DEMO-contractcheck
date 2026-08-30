"""Shared LLM/vision configuration and the one OpenAI-compatible chat call.

Both the text summarizer (`summarize.py`) and the visual comparator (`vision.py`)
talk to the same litellm-proxy endpoint, so the endpoint config, .env loading and
the raw `/chat/completions` POST live here once instead of being duplicated.

Env var resolution (first non-empty wins), so the same repo works whether it is
driven by its own `.env` (`LLM_*`) or by the surrounding CADS-Demo wrapper
(`LITELLM_*`):

    base url : LLM_BASE_URL        | LITELLM_BASE_URL
    api key  : LLM_API_KEY         | LITELLM_API_KEY
    text     : LLM_MODEL_NAME      | LITELLM_DEFAULT_MODEL   (default local-devstral-small2)
    vision   : LLM_VISION_MODEL_NAME | LITELLM_VISION_MODEL  (default: same as text model)

The base URL is normalized to end in exactly one `/v1`, so both
`https://host/v1` and `https://host` work.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
_TIMEOUT = httpx.Timeout(180.0, connect=10.0)


class LLMError(RuntimeError):
    pass


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(REPO_ROOT / ".env")


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def _normalize_base(url: str) -> str:
    """Ensure the OpenAI-compatible base URL ends in exactly one `/v1`."""
    url = url.rstrip("/")
    if not url:
        return ""
    if not url.endswith("/v1"):
        url = url + "/v1"
    return url


class LLMConfig:
    base_url: str = _normalize_base(_first_env("LLM_BASE_URL", "LITELLM_BASE_URL"))
    api_key: str = _first_env("LLM_API_KEY", "LITELLM_API_KEY")
    text_model: str = _first_env("LLM_MODEL_NAME", "LITELLM_DEFAULT_MODEL", default="local-devstral-small2")
    vision_model: str = _first_env("LLM_VISION_MODEL_NAME", "LITELLM_VISION_MODEL") or text_model

    # Backward-compatible alias: summarize.py (and its tests) refer to `.model`.
    model: str = text_model

    @classmethod
    def validate(cls) -> None:
        missing = [
            name
            for name, value in (
                ("LLM_BASE_URL/LITELLM_BASE_URL", cls.base_url),
                ("LLM_API_KEY/LITELLM_API_KEY", cls.api_key),
            )
            if not value
        ]
        if missing:
            raise SystemExit(
                f"Missing required config: {', '.join(missing)}. "
                "Run ./install.sh or copy .env.example to .env and fill it in."
            )


def chat_completion(
    messages: list[dict],
    *,
    model: str | None = None,
    max_tokens: int = 800,
    temperature: float = 0,
) -> str:
    """POST to the OpenAI-compatible `/chat/completions` endpoint and return the
    assistant message content. Raises LLMError on an unexpected response shape.

    `messages` may contain multimodal content parts (text + image_url), which the
    vision comparator uses -- this function does not care what is in them.
    """
    resp = httpx.post(
        f"{LLMConfig.base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {LLMConfig.api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model or LLMConfig.text_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Unexpected LLM response shape: {data!r}") from exc
