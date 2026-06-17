"""Backend registry and factory.

Provides ``get_backend()`` to instantiate any registered backend by name,
and ``list_backends()`` for the CLI ``--backend`` help text.  Imports are
lazy so that only the selected backend's dependencies are loaded.

Backward-compatible re-exports: ``BackendError``, ``OpenAICompatBackend``,
``extract_json``, ``REQUEST_TIMEOUT``, ``LMSTUDIO_URL``, ``OLLAMA_URL``,
and ``detect_backend`` are all available from this module so existing code
and tests that import them continue to work.
"""

from .base import BackendProtocol
from .openai_compat import (
    BackendError,
    OpenAICompatBackend,
    extract_json,
    LMSTUDIO_URL,
    OLLAMA_URL,
    REQUEST_TIMEOUT,
)

# Public API, including backward-compatible re-exports from openai_compat so
# existing imports (``from coach.backends import BackendError`` etc.) keep
# working after the split into a package.
__all__ = [
    "BackendProtocol",
    "BackendError",
    "OpenAICompatBackend",
    "extract_json",
    "LMSTUDIO_URL",
    "OLLAMA_URL",
    "REQUEST_TIMEOUT",
    "detect_backend",
    "get_backend",
    "list_backends",
    "ALL_BACKENDS",
    "PROVIDER_PRESETS",
]


def detect_backend(kind: str = "auto", base_url: str | None = None,
                   model: str | None = None, log=print,
                   n_ctx: int = 8192) -> BackendProtocol:
    """Backward-compatible alias for ``get_backend()``.

    Existing code (``cli.py``, tests) calls ``detect_backend(kind, base_url,
    model)``.  This wrapper preserves that positional-argument signature
    while delegating to the new ``get_backend()``.
    """
    return get_backend(kind, base_url=base_url, model=model, log=log,
                       n_ctx=n_ctx)

# Every backend name that can be selected via ``--backend``.
ALL_BACKENDS = [
    "auto",
    "lmstudio",
    "ollama",
    "claude",
    "keyword",
    "template",
    "bm25",
    "embedded",
]

# Provider presets for the openai-compat backend.
PROVIDER_PRESETS = [
    "openai",
    "groq",
    "together",
    "gemini",
    "ollama",
    "lmstudio",
    "vllm",
    "text-gen-ui",
]


def get_backend(
    kind: str = "auto",
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    provider: str | None = None,
    model_path: str | None = None,
    n_ctx: int = 8192,
    log=print,
) -> BackendProtocol:
    """Build the requested backend, auto-detecting when ``kind='auto'``.

    Parameters
    ----------
    kind : str
        Backend name: ``auto``, ``lmstudio``, ``ollama``, ``claude``,
        ``keyword``, ``template``, ``bm25``, or ``embedded``.
    base_url : str, optional
        Override the server URL (openai-compat backends only).
    model : str, optional
        Specific model name.
    api_key : str, optional
        API key for cloud providers.
    provider : str, optional
        Provider preset for openai-compat backends (applies known base_url).
    model_path : str, optional
        Path to a local GGUF model file (embedded backend only).
    log : callable
        Logger function for status messages.
    """
    # Explicit provider or base_url -> openai-compat backend
    if base_url or provider:
        return OpenAICompatBackend(
            base_url=base_url,
            model=model,
            api_key=api_key,
            provider=provider,
            name=kind if kind != "auto" else (provider or "openai-compat"),
        )

    if kind == "lmstudio":
        return OpenAICompatBackend(
            base_url=LMSTUDIO_URL, model=model, name="lmstudio"
        )
    if kind == "ollama":
        return OpenAICompatBackend(
            base_url=OLLAMA_URL, model=model, name="ollama"
        )
    if kind == "claude":
        from .claude_api import AnthropicBackend

        return AnthropicBackend(model or "claude-opus-4-8")
    if kind == "keyword":
        from .keyword import KeywordBackend

        return KeywordBackend()
    if kind == "template":
        from .template import TemplateBackend

        return TemplateBackend()
    if kind == "bm25":
        from .bm25 import BM25Backend

        return BM25Backend()
    if kind == "embedded":
        from .embedded import EmbeddedBackend

        return EmbeddedBackend(model_path=model_path, n_ctx=n_ctx)

    if kind != "auto":
        raise BackendError(f"unknown backend {kind!r}")

    # --- auto-detect: try LLM servers first, then fall back to keyword ---
    for name, url in (("lmstudio", LMSTUDIO_URL), ("ollama", OLLAMA_URL)):
        try:
            backend = OpenAICompatBackend(
                base_url=url, model=model, name=name
            )
            log(
                f"Using local model '{backend.model}' via {name} ({url})"
            )
            return backend
        except BackendError:
            continue

    import os

    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "ANTHROPIC_AUTH_TOKEN"
    ):
        from .claude_api import AnthropicBackend

        log("No local LLM server found — using the Claude API.")
        return AnthropicBackend(model or "claude-opus-4-8")

    # Try embedded SLM if llama-cpp-python is installed and a model exists
    try:
        from .embedded import EmbeddedBackend

        if EmbeddedBackend.is_available() and EmbeddedBackend.has_cached_model():
            backend = EmbeddedBackend(model_path=model_path, n_ctx=n_ctx)
            log(
                f"Using embedded model '{backend.model}' (local GGUF). "
                "No external server needed."
            )
            return backend
    except (BackendError, ImportError):
        pass

    # Final fallback: keyword backend (no LLM needed)
    log(
        "No LLM server detected — using the built-in keyword backend. "
        "For AI-powered responses, start LM Studio or Ollama, set "
        "ANTHROPIC_API_KEY, or install llama-cpp-python with a GGUF model."
    )
    from .keyword import KeywordBackend

    return KeywordBackend()


def list_backends() -> list[str]:
    """Return all backend names accepted by ``get_backend()``."""
    return list(ALL_BACKENDS)
