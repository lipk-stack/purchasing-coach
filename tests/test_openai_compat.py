"""OpenAI-compatible backend: JSON extraction, format fallback, presets."""

import io

import pytest

from coach.backends.openai_compat import (
    LMSTUDIO_URL,
    MAX_RESPONSE_BYTES,
    BackendError,
    OpenAICompatBackend,
    _read_bounded,
    extract_json,
)


# ----------------------------- extract_json --------------------------------
def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_fenced_without_language():
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_surrounding_prose():
    assert extract_json('Sure, here you go: {"a": 1, "b": 2} — done!') == {
        "a": 1, "b": 2}


def test_extract_json_invalid_raises():
    with pytest.raises(BackendError, match="did not return valid JSON"):
        extract_json("there is no json here at all")


# ----------------------------- presets / config ----------------------------
def test_provider_preset_sets_base_url_and_name():
    be = OpenAICompatBackend(provider="groq", model="m")
    assert be.base_url == "https://api.groq.com/openai/v1"
    assert be.name == "groq"


def test_explicit_base_url_strips_trailing_slash():
    be = OpenAICompatBackend(base_url="http://host:1/v1/", model="m")
    assert be.base_url == "http://host:1/v1"


def test_default_base_url_is_lmstudio():
    assert OpenAICompatBackend(model="m").base_url == LMSTUDIO_URL


def test_headers_include_auth_only_with_key():
    assert "Authorization" not in OpenAICompatBackend(model="m")._headers()
    headers = OpenAICompatBackend(model="m", api_key="secret")._headers()
    assert headers["Authorization"] == "Bearer secret"


# ----------------------------- complete_json -------------------------------
def test_complete_json_falls_back_through_formats(monkeypatch):
    be = OpenAICompatBackend(base_url="http://x", model="m")
    seen = []

    def fake(path, payload):
        seen.append(payload.get("response_format"))
        if len(seen) < 3:  # fail json_schema then json_object
            raise BackendError("server rejected response_format")
        return {"choices": [{"message": {"content": '{"ok": 1}'}}]}

    monkeypatch.setattr(be, "_request_json", fake)
    out = be.complete_json("sys", "prompt", {"type": "object"}, "plan")
    assert out == {"ok": 1}
    assert seen[0]["type"] == "json_schema"
    assert seen[1]["type"] == "json_object"
    assert seen[2] is None  # response_format dropped on the final attempt


def test_complete_json_unexpected_shape_raises(monkeypatch):
    be = OpenAICompatBackend(base_url="http://x", model="m")
    monkeypatch.setattr(be, "_request_json", lambda p, pl: {"weird": True})
    with pytest.raises(BackendError, match="unexpected response shape"):
        be.complete_json("sys", "prompt", {}, "plan")


# ----------------------------- bounded response read -----------------------
def test_read_bounded_passes_small_body():
    assert _read_bounded(io.BytesIO(b'{"data": []}')) == b'{"data": []}'


def test_read_bounded_allows_body_at_the_cap():
    body = b"x" * MAX_RESPONSE_BYTES
    assert _read_bounded(io.BytesIO(body)) == body


def test_read_bounded_rejects_oversize_body():
    body = b"x" * (MAX_RESPONSE_BYTES + 1)
    with pytest.raises(BackendError, match="implausibly large"):
        _read_bounded(io.BytesIO(body))
