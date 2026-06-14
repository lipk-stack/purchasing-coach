"""LLM backends: local OpenAI-compatible servers (LM Studio, Ollama) and Claude.

The local backends use only the standard library (urllib) so the app can run
as a portable zipapp on machines where nothing can be installed. LM Studio and
Ollama both expose the OpenAI chat-completions API on localhost.
"""

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Iterator

LMSTUDIO_URL = "http://localhost:1234/v1"
OLLAMA_URL = "http://localhost:11434/v1"

# Generous timeout: local models on corporate laptops can be slow.
REQUEST_TIMEOUT = 600


class BackendError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# OpenAI-compatible backend (LM Studio / Ollama / any compatible server)
# --------------------------------------------------------------------------
class OpenAICompatBackend:
    """Talks to any OpenAI-compatible /chat/completions endpoint via urllib."""

    def __init__(self, base_url: str, model: str | None = None,
                 api_key: str | None = None, name: str = "local"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.name = name
        self.model = model or self._first_model()

    # -- public API --------------------------------------------------------
    def stream_chat(self, system: str, messages: list[dict],
                    max_tokens: int = 4096) -> Iterator[str]:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        with self._request("/chat/completions", payload) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if choices:
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield delta

    def complete_json(self, system: str, prompt: str, schema: dict,
                      schema_name: str, max_tokens: int = 8192) -> dict:
        prompt = (
            f"{prompt}\n\nRespond with a single JSON object matching this "
            f"JSON schema, with no extra commentary:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            # LM Studio enforces the schema; servers that only know
            # json_object (or nothing) get a retry without it below.
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema},
            },
        }
        try:
            body = self._request_json("/chat/completions", payload)
        except BackendError:
            payload["response_format"] = {"type": "json_object"}
            try:
                body = self._request_json("/chat/completions", payload)
            except BackendError:
                payload.pop("response_format")
                body = self._request_json("/chat/completions", payload)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise BackendError(f"unexpected response shape: {body}") from exc
        return extract_json(content)

    # -- helpers -----------------------------------------------------------
    def _first_model(self) -> str:
        # LM Studio's OpenAI /v1/models lists every *downloaded* model, so
        # models[0] may be one that isn't loaded and fails to just-in-time load
        # on the first request ("Failed to load model"). Prefer a model the
        # server reports as already loaded (and a chat model, not embeddings).
        loaded = self._lmstudio_model()
        if loaded:
            return loaded
        models = self.list_models()
        if not models:
            raise BackendError(
                f"No model is loaded on {self.base_url}. Load a model in "
                "LM Studio / pull one with 'ollama pull <model>' first, or "
                "pass --llm-model.")
        return models[0]

    def _lmstudio_model(self) -> str | None:
        """Pick a usable chat model from LM Studio's native REST API, if present.

        LM Studio serves an enhanced API at ``/api/v0`` that, unlike the
        OpenAI-compatible ``/v1/models``, reports each model's load ``state``
        ("loaded"/"not-loaded") and ``type`` ("llm"/"vlm"/"embeddings"/...).
        We prefer a model that is already loaded so we never ask the server to
        load one that may fail, and we skip embeddings models that can't chat.
        Returns ``None`` for servers without this endpoint (Ollama, plain
        OpenAI-compatible servers) so the caller falls back to ``/v1/models``.
        """
        root = self.base_url[:-3] if self.base_url.endswith("/v1") \
            else self.base_url
        req = urllib.request.Request(root + "/api/v0/models",
                                     headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.load(resp)
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None
        chat = [m for m in (body.get("data") or [])
                if m.get("id") and m.get("type") in (None, "llm", "vlm")]
        for model in chat:  # an already-loaded chat model is the best choice
            if model.get("state") == "loaded":
                return model["id"]
        return chat[0]["id"] if chat else None

    def list_models(self) -> list[str]:
        req = urllib.request.Request(self.base_url + "/models",
                                     headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.load(resp)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise BackendError(f"cannot reach {self.base_url}: {exc}") from exc
        return [m.get("id") for m in body.get("data") or [] if m.get("id")]

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, path: str, payload: dict):
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(), method="POST")
        try:
            return urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            hint = ""
            if "load model" in detail.lower():
                hint = (f" — the server could not load model '{self.model}'. "
                        "Load a model in LM Studio (or free up memory), then "
                        "retry, or pass --llm-model with one that is loaded.")
            raise BackendError(
                f"{self.base_url}{path} returned {exc.code}: {detail}{hint}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise BackendError(f"cannot reach {self.base_url}: {exc}") from exc

    def _request_json(self, path: str, payload: dict) -> dict:
        with self._request(path, payload) as resp:
            return json.load(resp)


def extract_json(text: str) -> dict:
    """Pull a JSON object out of a model reply (tolerates code fences/prose)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise BackendError(
        "The model did not return valid JSON. A larger/instruction-tuned "
        f"local model may be needed. Reply started with: {text[:200]!r}")


# --------------------------------------------------------------------------
# Claude API backend (optional — requires the anthropic package and a key)
# --------------------------------------------------------------------------
class AnthropicBackend:
    name = "claude"

    def __init__(self, model: str = "claude-opus-4-8"):
        try:
            import anthropic
        except ImportError as exc:
            raise BackendError(
                "The Claude backend needs the 'anthropic' package: "
                "pip install anthropic") from exc
        self.client = anthropic.Anthropic()
        self.model = model

    def _system(self, system: str) -> list[dict]:
        # The guideline is large and identical across turns — cache it.
        return [{"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral"}}]

    def stream_chat(self, system: str, messages: list[dict],
                    max_tokens: int = 4096) -> Iterator[str]:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=self._system(system),
            messages=messages,
        ) as stream:
            yield from stream.text_stream

    def complete_json(self, system: str, prompt: str, schema: dict,
                      schema_name: str, max_tokens: int = 16000) -> dict:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=self._system(system),
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)


# --------------------------------------------------------------------------
# Backend selection
# --------------------------------------------------------------------------
def detect_backend(kind: str = "auto", base_url: str | None = None,
                   model: str | None = None, log=print):
    """Build the requested backend, probing local servers when kind='auto'."""
    if base_url:
        return OpenAICompatBackend(base_url, model, name=kind if kind != "auto"
                                   else "openai-compat")
    if kind == "lmstudio":
        return OpenAICompatBackend(LMSTUDIO_URL, model, name="lmstudio")
    if kind == "ollama":
        return OpenAICompatBackend(OLLAMA_URL, model, name="ollama")
    if kind == "claude":
        return AnthropicBackend(model or "claude-opus-4-8")

    if kind != "auto":
        raise BackendError(f"unknown backend {kind!r}")

    for name, url in (("lmstudio", LMSTUDIO_URL), ("ollama", OLLAMA_URL)):
        try:
            backend = OpenAICompatBackend(url, model, name=name)
            log(f"Using local model '{backend.model}' via {name} ({url})")
            return backend
        except BackendError:
            continue
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        log("No local LLM server found — using the Claude API.")
        return AnthropicBackend(model or "claude-opus-4-8")
    raise BackendError(
        "No LLM available. Start LM Studio (with a model loaded and the local "
        "server enabled) or Ollama on this machine, or set ANTHROPIC_API_KEY "
        "to use the Claude API. You can also point at any OpenAI-compatible "
        "server with --base-url.")
