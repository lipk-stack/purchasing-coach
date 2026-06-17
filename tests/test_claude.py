"""Claude (Anthropic) backend with the anthropic SDK faked."""

import sys
import types
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from coach.backends.claude_api import AnthropicBackend, BackendError


def _install_fake_anthropic(monkeypatch, *, create_text='{"ok": true}',
                            stream_chunks=("Hello", " world"),
                            models_list_raises=False):
    mod = types.ModuleType("anthropic")

    class _Stream:
        def __init__(self):
            self.text_stream = iter(stream_chunks)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    @contextmanager
    def _stream_cm(**kwargs):
        yield _Stream()

    block = MagicMock()
    block.type = "text"
    block.text = create_text
    response = MagicMock()
    response.content = [block]

    client = MagicMock()
    client.messages.stream = _stream_cm
    client.messages.create = MagicMock(return_value=response)
    if models_list_raises:
        client.models.list = MagicMock(side_effect=RuntimeError("no auth"))
    else:
        client.models.list = MagicMock(return_value=[])

    mod.Anthropic = MagicMock(return_value=client)
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    return client


def test_missing_anthropic_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(BackendError, match="anthropic"):
        AnthropicBackend()


def test_default_model_and_name(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    be = AnthropicBackend()
    assert be.name == "claude"
    assert be.model == "claude-opus-4-8"


def test_stream_chat_yields_text(monkeypatch):
    _install_fake_anthropic(monkeypatch, stream_chunks=("a", "b", "c"))
    be = AnthropicBackend()
    out = list(be.stream_chat("sys", [{"role": "user", "content": "hi"}]))
    assert out == ["a", "b", "c"]


def test_complete_json_parses_text_block(monkeypatch):
    _install_fake_anthropic(monkeypatch, create_text='{"requirements": []}')
    be = AnthropicBackend()
    data = be.complete_json("sys", "prompt", {}, "tender_checklist")
    assert data == {"requirements": []}


def test_health_check_ok_and_error(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    assert AnthropicBackend().health_check()["status"] == "ok"

    _install_fake_anthropic(monkeypatch, models_list_raises=True)
    health = AnthropicBackend().health_check()
    assert health["status"] == "error"
    assert "no auth" in health["detail"]
