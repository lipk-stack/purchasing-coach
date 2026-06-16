"""Unit tests for the embedded SLM backend (llama-cpp-python mocked)."""

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from coach.backends import BackendError, list_backends, get_backend
from coach.backends.embedded import (
    EmbeddedBackend,
    DEFAULT_MODEL_REPO,
    DEFAULT_MODEL_FILE,
    _MODEL_CACHE,
)


# ---------------------------------------------------------------------------
# Helpers — fake llama-cpp-python module
# ---------------------------------------------------------------------------
def _make_fake_llama_module():
    """Build a fake ``llama_cpp`` module with a mockable Llama class."""
    mod = types.ModuleType("llama_cpp")
    mod.Llama = MagicMock()
    return mod


def _install_fake_llama(monkeypatch):
    """Install a fake llama_cpp module into sys.modules and return it."""
    fake = _make_fake_llama_module()
    monkeypatch.setitem(sys.modules, "llama_cpp", fake)
    return fake


def _make_model_file(tmp_path: Path) -> Path:
    """Create a tiny file pretending to be a GGUF model."""
    model = tmp_path / "test-model.gguf"
    model.write_bytes(b"GGUF" + b"\x00" * 100)
    return model


# ---------------------------------------------------------------------------
# Import / availability tests
# ---------------------------------------------------------------------------
def test_missing_llama_cpp_raises_backend_error(tmp_path):
    """Without llama-cpp-python installed, BackendError with install hint."""
    model = _make_model_file(tmp_path)
    # Ensure llama_cpp is NOT importable
    with patch.dict(sys.modules, {"llama_cpp": None}):
        with pytest.raises(BackendError, match="llama-cpp-python"):
            EmbeddedBackend(model_path=model)


def test_is_available_false_without_llama_cpp():
    with patch.dict(sys.modules, {"llama_cpp": None}):
        assert EmbeddedBackend.is_available() is False


def test_is_available_true_with_llama_cpp(monkeypatch):
    _install_fake_llama(monkeypatch)
    assert EmbeddedBackend.is_available() is True


# ---------------------------------------------------------------------------
# Model resolution tests
# ---------------------------------------------------------------------------
def test_explicit_model_path(tmp_path, monkeypatch):
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)
    backend = EmbeddedBackend(model_path=model)
    assert backend.model == "test-model"
    fake.Llama.assert_called_once()
    call_kwargs = fake.Llama.call_args[1]
    assert call_kwargs["model_path"] == str(model)


def test_missing_explicit_path_raises(tmp_path, monkeypatch):
    _install_fake_llama(monkeypatch)
    with pytest.raises(BackendError, match="not found"):
        EmbeddedBackend(model_path=tmp_path / "nonexistent.gguf")


def test_env_var_model_path(tmp_path, monkeypatch):
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)
    monkeypatch.setenv("EMBEDDED_MODEL_PATH", str(model))
    backend = EmbeddedBackend()
    assert backend.model == "test-model"


def test_env_var_missing_path_raises(monkeypatch):
    _install_fake_llama(monkeypatch)
    monkeypatch.setenv("EMBEDDED_MODEL_PATH", "/nonexistent/model.gguf")
    with pytest.raises(BackendError, match="missing file"):
        EmbeddedBackend()


def test_cached_model_found(tmp_path, monkeypatch):
    fake = _install_fake_llama(monkeypatch)
    # Put a fake GGUF in the cache dir
    monkeypatch.setattr(
        "coach.backends.embedded._MODEL_CACHE", tmp_path
    )
    model = tmp_path / "cached-model.gguf"
    model.write_bytes(b"GGUF")
    backend = EmbeddedBackend()
    assert backend.model == "cached-model"


# ---------------------------------------------------------------------------
# Auto-download tests
# ---------------------------------------------------------------------------
def test_auto_download_resolves_model(tmp_path, monkeypatch):
    """When no model is cached, _resolve_model calls _download_model."""
    fake = _install_fake_llama(monkeypatch)
    fake.Llama.return_value = MagicMock()

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(
        "coach.backends.embedded._MODEL_CACHE", cache_dir
    )

    # Create the model file in a separate directory (not the cache)
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    downloaded = _make_model_file(model_dir)
    download_mock = MagicMock(return_value=downloaded)
    monkeypatch.setattr(EmbeddedBackend, "_download_model", download_mock)

    backend = EmbeddedBackend()
    download_mock.assert_called_once()
    assert backend.model == "test-model"


def test_download_model_calls_hf_hub(monkeypatch):
    """_download_model uses huggingface_hub.hf_hub_download with defaults."""
    # Remove any cached huggingface_hub module to force re-import
    saved = sys.modules.pop("huggingface_hub", None)
    try:
        fake_hub = types.ModuleType("huggingface_hub")
        fake_hub.hf_hub_download = MagicMock(
            return_value="/fake/path/model.gguf"
        )
        sys.modules["huggingface_hub"] = fake_hub

        result = EmbeddedBackend._download_model()
        fake_hub.hf_hub_download.assert_called_once_with(
            repo_id=DEFAULT_MODEL_REPO,
            filename=DEFAULT_MODEL_FILE,
            local_dir=str(_MODEL_CACHE),
        )
        assert result == Path("/fake/path/model.gguf")
    finally:
        # Restore original sys.modules state
        sys.modules.pop("huggingface_hub", None)
        if saved is not None:
            sys.modules["huggingface_hub"] = saved


def test_auto_download_failure_raises(tmp_path, monkeypatch):
    _install_fake_llama(monkeypatch)
    monkeypatch.setattr(
        "coach.backends.embedded._MODEL_CACHE", tmp_path
    )

    download_mock = MagicMock(
        side_effect=BackendError("Failed to download model")
    )
    monkeypatch.setattr(EmbeddedBackend, "_download_model", download_mock)

    with pytest.raises(BackendError, match="Failed to download"):
        EmbeddedBackend()


# ---------------------------------------------------------------------------
# stream_chat tests
# ---------------------------------------------------------------------------
def test_stream_chat_yields_deltas(tmp_path, monkeypatch):
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)

    # Configure the mock Llama to return streaming chunks.
    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = iter([
        {"choices": [{"delta": {"content": "Hello"}}]},
        {"choices": [{"delta": {"content": " world"}}]},
        {"choices": [{"delta": {}}]},
    ])
    fake.Llama.return_value = mock_llm

    backend = EmbeddedBackend(model_path=model)
    chunks = list(backend.stream_chat(
        "system prompt",
        [{"role": "user", "content": "hi"}],
    ))
    assert chunks == ["Hello", " world"]
    mock_llm.create_chat_completion.assert_called_once()
    call_kwargs = mock_llm.create_chat_completion.call_args[1]
    assert call_kwargs["stream"] is True
    assert call_kwargs["messages"][0]["role"] == "system"


def test_stream_chat_handles_empty_delta(tmp_path, monkeypatch):
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)

    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = iter([
        {"choices": [{"delta": {"content": "A"}}]},
        {"choices": []},  # empty choices
        {"choices": [{"delta": {"content": "B"}}]},
    ])
    fake.Llama.return_value = mock_llm

    backend = EmbeddedBackend(model_path=model)
    result = "".join(backend.stream_chat("sys", []))
    assert result == "AB"


# ---------------------------------------------------------------------------
# complete_json tests
# ---------------------------------------------------------------------------
def test_complete_json_uses_response_format(tmp_path, monkeypatch):
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)

    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": '{"questions": ["Q1", "Q2"]}'}}]
    }
    fake.Llama.return_value = mock_llm

    backend = EmbeddedBackend(model_path=model)
    schema = {"type": "object", "properties": {"questions": {"type": "array"}}}
    result = backend.complete_json("sys", "prompt", schema, "plan")
    assert result == {"questions": ["Q1", "Q2"]}

    call_kwargs = mock_llm.create_chat_completion.call_args[1]
    assert call_kwargs["stream"] is False
    assert "response_format" in call_kwargs
    assert call_kwargs["response_format"]["type"] == "json_object"


def test_complete_json_fallback_on_type_error(tmp_path, monkeypatch):
    """If response_format causes a TypeError, retry without it."""
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)

    mock_llm = MagicMock()
    # First call (with response_format) raises, second call succeeds.
    mock_llm.create_chat_completion.side_effect = [
        TypeError("unsupported response_format"),
        {"choices": [{"message": {"content": '{"ok": true}'}}]},
    ]
    fake.Llama.return_value = mock_llm

    backend = EmbeddedBackend(model_path=model)
    result = backend.complete_json("sys", "p", {}, "test")
    assert result == {"ok": True}
    assert mock_llm.create_chat_completion.call_count == 2


def test_complete_json_handles_fenced_json(tmp_path, monkeypatch):
    """extract_json strips code fences from the model output."""
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)

    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = {
        "choices": [{"message": {
            "content": '```json\n{"items": [1, 2]}\n```'
        }}]
    }
    fake.Llama.return_value = mock_llm

    backend = EmbeddedBackend(model_path=model)
    result = backend.complete_json("sys", "p", {}, "test")
    assert result == {"items": [1, 2]}


# ---------------------------------------------------------------------------
# health_check tests
# ---------------------------------------------------------------------------
def test_health_check_ok_when_loaded(tmp_path, monkeypatch):
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)
    fake.Llama.return_value = MagicMock()

    backend = EmbeddedBackend(model_path=model)
    health = backend.health_check()
    assert health["status"] == "ok"
    assert "test-model" in health["detail"]


# ---------------------------------------------------------------------------
# load_guideline tests
# ---------------------------------------------------------------------------
def test_load_guideline_warns_on_large_context(tmp_path, monkeypatch):
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)
    fake.Llama.return_value = MagicMock()

    backend = EmbeddedBackend(model_path=model, n_ctx=256)
    # A guideline that's clearly larger than 256 tokens (~1024 chars)
    large_text = "x" * 10000
    with pytest.warns(UserWarning, match="context window"):
        backend.load_guideline(large_text, {}, {})


def test_load_guideline_no_warning_small_text(tmp_path, monkeypatch):
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)
    fake.Llama.return_value = MagicMock()

    backend = EmbeddedBackend(model_path=model, n_ctx=8192)
    # Small text should not trigger a warning.
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        backend.load_guideline("short guideline", {}, {})


# ---------------------------------------------------------------------------
# Registry / factory integration
# ---------------------------------------------------------------------------
def test_embedded_in_list_backends():
    assert "embedded" in list_backends()


def test_factory_creates_embedded(tmp_path, monkeypatch):
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)
    fake.Llama.return_value = MagicMock()

    backend = get_backend("embedded", model_path=str(model))
    assert backend.name == "embedded"
    assert backend.requires_model is True


def test_factory_unknown_backend_raises(monkeypatch):
    from coach.backends import BackendError
    with pytest.raises(BackendError, match="unknown backend"):
        get_backend("nonexistent")


# ---------------------------------------------------------------------------
# has_cached_model tests
# ---------------------------------------------------------------------------
def test_has_cached_model_false_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "coach.backends.embedded._MODEL_CACHE", tmp_path
    )
    assert EmbeddedBackend.has_cached_model() is False


def test_has_cached_model_true_with_gguf(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "coach.backends.embedded._MODEL_CACHE", tmp_path
    )
    (tmp_path / "model.gguf").write_bytes(b"GGUF")
    assert EmbeddedBackend.has_cached_model() is True


def test_has_cached_model_false_no_dir(monkeypatch):
    monkeypatch.setattr(
        "coach.backends.embedded._MODEL_CACHE",
        Path("/nonexistent/dir"),
    )
    assert EmbeddedBackend.has_cached_model() is False


# ---------------------------------------------------------------------------
# Custom model_name override
# ---------------------------------------------------------------------------
def test_custom_model_name(tmp_path, monkeypatch):
    fake = _install_fake_llama(monkeypatch)
    model = _make_model_file(tmp_path)
    fake.Llama.return_value = MagicMock()

    backend = EmbeddedBackend(
        model_path=model, model_name="my-custom-model"
    )
    assert backend.model == "my-custom-model"
