"""OpenAI-compatible backend with provider presets.

Talks to any server that exposes the ``/chat/completions`` endpoint —
LM Studio, Ollama, OpenAI, Groq, Together AI, Google Gemini (OpenAI-compat
mode), vLLM, and any other compatible server. Uses only the standard
library (``urllib``) so the app stays portable.
"""

import json
import re
import urllib.error
import urllib.request
from collections.abc import Iterator

from .base import BackendProtocol

LMSTUDIO_URL = "http://localhost:1234/v1"
OLLAMA_URL = "http://localhost:11434/v1"

# Generous timeout: local models on corporate laptops can be slow.
REQUEST_TIMEOUT = 600

# Well-known provider presets.  Pass ``provider=`` to the constructor or
# override with explicit ``base_url`` + ``api_key``.
PROVIDER_PRESETS: dict[str, dict] = {
    "openai": {"base_url": "https://api.openai.com/v1"},
    "groq": {"base_url": "https://api.groq.com/openai/v1"},
    "together": {"base_url": "https://api.together.xyz/v1"},
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"
    },
    "ollama": {"base_url": OLLAMA_URL},
    "lmstudio": {"base_url": LMSTUDIO_URL},
    "vllm": {"base_url": "http://localhost:8000/v1"},
    "text-gen-ui": {"base_url": "http://localhost:5000/v1"},
}


class BackendError(RuntimeError):
    """Raised when the backend cannot fulfil a request."""


class OpenAICompatBackend(BackendProtocol):
    """Talks to any OpenAI-compatible ``/chat/completions`` endpoint."""

    name = "openai-compat"
    requires_model = True

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        provider: str | None = None,
        name: str | None = None,
    ):
        if provider and provider in PROVIDER_PRESETS:
            preset = PROVIDER_PRESETS[provider]
            base_url = base_url or preset["base_url"]
        if not base_url:
            base_url = LMSTUDIO_URL
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        if name:
            self.name = name
        elif provider:
            self.name = provider
        else:
            self.name = "openai-compat"
        self.model = model or self._first_model()

    # ------------------------------------------------------------------
    # BackendProtocol implementation
    # ------------------------------------------------------------------
    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> Iterator[str]:
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

    def complete_json(
        self,
        system: str,
        prompt: str,
        schema: dict,
        schema_name: str,
        max_tokens: int = 8192,
    ) -> dict:
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
            raise BackendError(
                f"unexpected response shape: {body}"
            ) from exc
        return extract_json(content)

    def health_check(self) -> dict:
        try:
            models = self.list_models()
            return {
                "status": "ok",
                "detail": f"{self.name}: {len(models)} model(s) available",
            }
        except BackendError as exc:
            return {"status": "error", "detail": str(exc)}

    # ------------------------------------------------------------------
    # Model discovery
    # ------------------------------------------------------------------
    def _first_model(self) -> str:
        loaded = self._lmstudio_model()
        if loaded:
            return loaded
        models = self.list_models()
        if not models:
            raise BackendError(
                f"No model is loaded on {self.base_url}. Load a model in "
                "LM Studio / pull one with 'ollama pull <model>' first, or "
                "pass --llm-model."
            )
        return models[0]

    def _lmstudio_model(self) -> str | None:
        root = (
            self.base_url[:-3]
            if self.base_url.endswith("/v1")
            else self.base_url
        )
        req = urllib.request.Request(
            root + "/api/v0/models", headers=self._headers()
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.load(resp)
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return None
        chat = [
            m
            for m in (body.get("data") or [])
            if m.get("id") and m.get("type") in (None, "llm", "vlm")
        ]

        def rank(model: dict) -> tuple[int, int]:
            not_loaded = 0 if model.get("state") == "loaded" else 1
            is_vision = 1 if model.get("type") == "vlm" else 0
            return (not_loaded, is_vision)

        chat.sort(key=rank)
        return chat[0]["id"] if chat else None

    def list_models(self) -> list[str]:
        req = urllib.request.Request(
            self.base_url + "/models", headers=self._headers()
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.load(resp)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise BackendError(f"cannot reach {self.base_url}: {exc}") from exc
        return [
            m.get("id") for m in body.get("data") or [] if m.get("id")
        ]

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------
    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, path: str, payload: dict):
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            return urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            hint = ""
            if "load model" in detail.lower():
                hint = (
                    f" — the server could not load model '{self.model}'. "
                    "Load a working model in LM Studio (a text/instruct "
                    "model is safest), or pass --llm-model with one that "
                    "loads. If it is a new or multimodal model, your "
                    "LM Studio runtime may be too old to load it — update "
                    "LM Studio's runtime or pick a different model."
                )
            raise BackendError(
                f"{self.base_url}{path} returned {exc.code}: {detail}{hint}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise BackendError(
                f"cannot reach {self.base_url}: {exc}"
            ) from exc

    def _request_json(self, path: str, payload: dict) -> dict:
        with self._request(path, payload) as resp:
            return json.load(resp)


# --------------------------------------------------------------------------
# JSON extraction (tolerates code fences, surrounding prose)
# --------------------------------------------------------------------------
def extract_json(text: str) -> dict:
    """Pull a JSON object out of a model reply."""
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
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise BackendError(
        "The model did not return valid JSON. A larger/instruction-tuned "
        f"local model may be needed. Reply started with: {text[:200]!r}"
    )
