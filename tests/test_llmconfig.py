"""Config resolution: LLM_* / LITELLM_* fallback and /v1 normalization. No LLM key needed."""

from llmconfig import _first_env, _normalize_base


def test_normalize_base_adds_v1():
    assert _normalize_base("https://host.example.com") == "https://host.example.com/v1"


def test_normalize_base_keeps_existing_v1():
    assert _normalize_base("https://host.example.com/v1") == "https://host.example.com/v1"


def test_normalize_base_strips_trailing_slash():
    assert _normalize_base("https://host.example.com/v1/") == "https://host.example.com/v1"


def test_normalize_base_empty_stays_empty():
    assert _normalize_base("") == ""


def test_first_env_prefers_first_non_empty(monkeypatch):
    monkeypatch.delenv("PRIMARY_X", raising=False)
    monkeypatch.setenv("FALLBACK_X", "fallback")
    assert _first_env("PRIMARY_X", "FALLBACK_X") == "fallback"
    monkeypatch.setenv("PRIMARY_X", "primary")
    assert _first_env("PRIMARY_X", "FALLBACK_X") == "primary"


def test_first_env_default_when_all_unset(monkeypatch):
    monkeypatch.delenv("NOPE_A", raising=False)
    monkeypatch.delenv("NOPE_B", raising=False)
    assert _first_env("NOPE_A", "NOPE_B", default="d") == "d"
