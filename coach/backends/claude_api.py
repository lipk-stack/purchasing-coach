"""Claude (Anthropic) API backend.

Requires the ``anthropic`` Python package and an API key set in the
``ANTHROPIC_API_KEY`` or ``ANTHROPIC_AUTH_TOKEN`` environment variable.
"""

import json

from .base import BackendProtocol


class BackendError(RuntimeError):
    pass


class AnthropicBackend(BackendProtocol):
    """Talks to the Claude API via the Anthropic Python SDK."""

    name = "claude"
    requires_model = True

    def __init__(self, model: str = "claude-opus-4-8"):
        try:
            import anthropic
        except ImportError as exc:
            raise BackendError(
                "The Claude backend needs the 'anthropic' package: "
                "pip install anthropic"
            ) from exc
        self.client = anthropic.Anthropic()
        self.model = model

    def _system(self, system: str) -> list[dict]:
        return [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ):
        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=self._system(system),
            messages=messages,
        ) as stream:
            yield from stream.text_stream

    def complete_json(
        self,
        system: str,
        prompt: str,
        schema: dict,
        schema_name: str,
        max_tokens: int = 16000,
    ) -> dict:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=self._system(system),
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {"type": "json_schema", "schema": schema}
            },
        )
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)

    def health_check(self) -> dict:
        try:
            # Lightweight check: try to list models
            self.client.models.list()
            return {"status": "ok", "detail": f"claude: API reachable"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}
