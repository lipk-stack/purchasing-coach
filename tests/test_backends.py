"""Unit tests for the OpenAI-compatible local backend (urllib mocked)."""

import io
import json

import pytest

from coach import backends
from coach.backends import BackendError, OpenAICompatBackend, extract_json
from coach.models import InterviewPlan, RequirementRow, TenderChecklist


# ---- extract_json ---------------------------------------------------------
def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_fenced_json():
    text = "Here you go:\n```json\n{\"a\": 1}\n```\nthanks"
    assert extract_json(text) == {"a": 1}


def test_extract_json_with_prose():
    assert extract_json('Sure! {"a": {"b": 2}} hope that helps') == {"a": {"b": 2}}


def test_extract_json_failure():
    with pytest.raises(BackendError):
        extract_json("I cannot answer that.")


# ---- model validation -----------------------------------------------------
def test_interview_plan_accepts_string_questions():
    plan = InterviewPlan.from_dict({"questions": ["When?", "Who?"]})
    assert [q.question for q in plan.questions] == ["When?", "Who?"]


def test_requirement_row_normalises_mandatory():
    assert RequirementRow.from_dict({"requirement": "x", "mandatory": "optional"}).mandatory == "O"
    assert RequirementRow.from_dict({"requirement": "x", "mandatory": "Mandatory"}).mandatory == "M"
    assert RequirementRow.from_dict({"requirement": "x"}).mandatory == "M"


def test_checklist_requires_rows():
    with pytest.raises(ValueError):
        TenderChecklist.from_dict({"tender_info": {}, "requirements": []})


def test_tender_info_defaults_to_tbc():
    checklist = TenderChecklist.from_dict({
        "tender_info": {"purchase_item": "Laptops"},
        "requirements": [{"ref": "1", "section": "s", "requirement": "r",
                          "mandatory": "M"}],
    })
    assert checklist.tender_info.purchase_item == "Laptops"
    assert checklist.tender_info.issue_date == "TBC"


# ---- HTTP layer (urllib mocked) -------------------------------------------
class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _make_backend(monkeypatch, responses):
    """Backend whose urlopen returns queued FakeResponses and logs requests."""
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req)
        body = responses.pop(0)
        if isinstance(body, Exception):
            raise body
        return FakeResponse(body)

    monkeypatch.setattr(backends.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_first_model_prefers_loaded_chat_model(monkeypatch):
    # LM Studio's native /api/v0/models lists every downloaded model with its
    # load state and type. We must pick the one already loaded — not the first
    # listed (which here would fail to load) and not the embeddings model.
    native = json.dumps({"data": [
        {"id": "google/gemma-4-12b-qat", "type": "llm", "state": "not-loaded"},
        {"id": "text-embedding-nomic", "type": "embeddings", "state": "loaded"},
        {"id": "qwen2.5-7b-instruct", "type": "llm", "state": "loaded"},
    ]}).encode()
    _make_backend(monkeypatch, [native])
    backend = OpenAICompatBackend("http://localhost:1234/v1")
    assert backend.model == "qwen2.5-7b-instruct"


def test_first_model_falls_back_to_first_chat_when_none_loaded(monkeypatch):
    native = json.dumps({"data": [
        {"id": "text-embedding-nomic", "type": "embeddings", "state": "loaded"},
        {"id": "qwen2.5-7b-instruct", "type": "llm", "state": "not-loaded"},
    ]}).encode()
    _make_backend(monkeypatch, [native])
    backend = OpenAICompatBackend("http://localhost:1234/v1")
    assert backend.model == "qwen2.5-7b-instruct"


def test_first_model_prefers_text_over_vision_when_none_loaded(monkeypatch):
    # A text-only app should skip a vision model (vlm) like gemma-4-12b — whose
    # vision projector often fails to load — when a plain text model exists.
    native = json.dumps({"data": [
        {"id": "google/gemma-4-12b-qat", "type": "vlm", "state": "not-loaded"},
        {"id": "qwen2.5-7b-instruct", "type": "llm", "state": "not-loaded"},
    ]}).encode()
    _make_backend(monkeypatch, [native])
    backend = OpenAICompatBackend("http://localhost:1234/v1")
    assert backend.model == "qwen2.5-7b-instruct"


def test_first_model_loaded_vision_beats_unloaded_text(monkeypatch):
    # A vision model that is already loaded works for text, so it still beats a
    # text model that would need a risky just-in-time load.
    native = json.dumps({"data": [
        {"id": "qwen2.5-7b-instruct", "type": "llm", "state": "not-loaded"},
        {"id": "gemma-3-vision", "type": "vlm", "state": "loaded"},
    ]}).encode()
    _make_backend(monkeypatch, [native])
    backend = OpenAICompatBackend("http://localhost:1234/v1")
    assert backend.model == "gemma-3-vision"


def test_first_model_falls_back_to_v1_models_without_native_api(monkeypatch):
    import urllib.error

    # Non-LM-Studio server: /api/v0/models is absent, so use /v1/models[0].
    no_native = urllib.error.URLError("not found")
    v1 = json.dumps({"data": [{"id": "llama3.1:8b"}]}).encode()
    _make_backend(monkeypatch, [no_native, v1])
    backend = OpenAICompatBackend("http://localhost:11434/v1")
    assert backend.model == "llama3.1:8b"


def test_stream_chat_parses_sse(monkeypatch):
    sse = b"\n".join([
        b'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        b'data: {"choices":[{"delta":{"content":"lo"}}]}',
        b"data: [DONE]",
    ])
    _make_backend(monkeypatch, [sse])
    backend = OpenAICompatBackend("http://x/v1", model="m")
    out = "".join(backend.stream_chat("sys", [{"role": "user", "content": "hi"}]))
    assert out == "Hello"


def test_complete_json_falls_back_without_schema_support(monkeypatch):
    import urllib.error

    ok = json.dumps({"choices": [{"message": {"content": '{"questions": ["Q1"]}'}}]}).encode()
    err = urllib.error.HTTPError("u", 400, "bad response_format", {},
                                 io.BytesIO(b"unsupported"))
    calls = _make_backend(monkeypatch, [err, ok])
    backend = OpenAICompatBackend("http://x/v1", model="m")
    data = backend.complete_json("sys", "prompt", {"type": "object"}, "plan")
    assert data == {"questions": ["Q1"]}
    # first call used json_schema, retry switched to json_object
    first = json.loads(calls[0].data)
    second = json.loads(calls[1].data)
    assert first["response_format"]["type"] == "json_schema"
    assert second["response_format"]["type"] == "json_object"
