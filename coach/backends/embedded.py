"""Embedded SLM backend using llama-cpp-python.

Runs a small GGUF language model directly in-process — no external server
needed.  The default model (Qwen2.5-1.5B-Instruct Q4_K_M, ~1.12 GB) is
downloaded automatically on first use and cached locally.

Requires the optional dependency ``llama-cpp-python``::

    pip install llama-cpp-python

Users may also point ``EMBEDDED_MODEL_PATH`` at any local GGUF file, or
pass ``--model-path`` on the CLI.
"""

import json
import os
from collections.abc import Iterator
from pathlib import Path

from .base import BackendProtocol
from .openai_compat import BackendError, extract_json

# Default model: Qwen2.5-1.5B-Instruct (Q4_K_M quantisation, ~1.12 GB).
# Best size/quality tradeoff for structured procurement output.
DEFAULT_MODEL_REPO = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
DEFAULT_MODEL_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"

# Where cached models are stored.
_MODEL_CACHE = Path.home() / ".purchasing-coach" / "models"


class EmbeddedBackend(BackendProtocol):
    """Runs a small GGUF model locally via llama-cpp-python.

    Parameters
    ----------
    model_path : str or Path, optional
        Explicit path to a GGUF model file.  Takes priority over the
        ``EMBEDDED_MODEL_PATH`` environment variable and the auto-download
        cache.
    model_name : str, optional
        Override the displayed model name (defaults to the file stem).
    n_ctx : int
        Context window size in tokens (default 4096).
    n_threads : int, optional
        CPU threads for inference (defaults to llama.cpp's auto-selection).
    verbose : bool
        If True, llama.cpp prints loading/inference diagnostics to stderr.
    """

    name = "embedded"
    requires_model = True

    def __init__(
        self,
        model_path: str | Path | None = None,
        model_name: str | None = None,
        n_ctx: int = 4096,
        n_threads: int | None = None,
        verbose: bool = False,
    ):
        self._llm = None
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._verbose = verbose

        resolved = self._resolve_model(model_path)
        self.model = model_name or Path(resolved).stem

        try:
            from llama_cpp import Llama  # type: ignore[import-untyped]
        except ImportError as exc:
            raise BackendError(
                "The embedded backend requires llama-cpp-python.\n"
                "Install it with:\n"
                "    pip install llama-cpp-python\n"
                "For GPU acceleration (optional):\n"
                "    CMAKE_ARGS=\"-DGGML_CUDA=on\" pip install "
                "llama-cpp-python"
            ) from exc

        self._llm = Llama(
            model_path=str(resolved),
            n_ctx=self._n_ctx,
            n_threads=self._n_threads,
            verbose=self._verbose,
        )

    # ------------------------------------------------------------------
    # Model resolution
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_model(model_path: str | Path | None = None) -> Path:
        """Find or download the GGUF model file.

        Resolution order:
        1. Explicit ``model_path`` argument
        2. ``EMBEDDED_MODEL_PATH`` environment variable
        3. Cached model in ``~/.purchasing-coach/models/``
        4. Auto-download from HuggingFace Hub
        """
        # 1. Explicit path
        if model_path:
            p = Path(model_path)
            if p.is_file():
                return p
            raise BackendError(f"Model file not found: {p}")

        # 2. Environment variable
        env_path = os.environ.get("EMBEDDED_MODEL_PATH")
        if env_path:
            p = Path(env_path)
            if p.is_file():
                return p
            raise BackendError(
                f"EMBEDDED_MODEL_PATH points to a missing file: {p}"
            )

        # 3. Cache directory — look for any .gguf file
        _MODEL_CACHE.mkdir(parents=True, exist_ok=True)
        cached = list(_MODEL_CACHE.glob("*.gguf"))
        if cached:
            return cached[0]

        # 4. Auto-download
        return EmbeddedBackend._download_model()

    @staticmethod
    def _download_model() -> Path:
        """Download the default model from HuggingFace Hub."""
        try:
            from huggingface_hub import hf_hub_download  # type: ignore[import-untyped]
        except ImportError:
            # llama-cpp-python depends on huggingface-hub, so this should
            # always be available — but handle it gracefully just in case.
            raise BackendError(
                "huggingface-hub is needed to download the default model.\n"
                "Install it with: pip install huggingface-hub\n"
                "Or provide a local GGUF file via --model-path or "
                "EMBEDDED_MODEL_PATH."
            )

        _MODEL_CACHE.mkdir(parents=True, exist_ok=True)
        try:
            path = hf_hub_download(
                repo_id=DEFAULT_MODEL_REPO,
                filename=DEFAULT_MODEL_FILE,
                local_dir=str(_MODEL_CACHE),
            )
        except Exception as exc:
            raise BackendError(
                f"Failed to download model from {DEFAULT_MODEL_REPO}: {exc}\n"
                "You can manually download a GGUF model and pass it with "
                "--model-path /path/to/model.gguf"
            ) from exc
        return Path(path)

    # ------------------------------------------------------------------
    # BackendProtocol implementation
    # ------------------------------------------------------------------
    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        chat_messages = [
            {"role": "system", "content": system},
            *messages,
        ]
        response = self._llm.create_chat_completion(
            messages=chat_messages,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in response:
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
        full_prompt = (
            f"{prompt}\n\nRespond with a single JSON object matching this "
            f"JSON schema, with no extra commentary:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        chat_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": full_prompt},
        ]

        # Try with guided JSON schema first (llama-cpp-python supports
        # this via response_format with a json_schema).
        try:
            response = self._llm.create_chat_completion(
                messages=chat_messages,
                max_tokens=max_tokens,
                stream=False,
                response_format={
                    "type": "json_object",
                    "schema": schema,
                },
            )
            content = response["choices"][0]["message"]["content"]
            return extract_json(content)
        except (TypeError, ValueError, KeyError):
            # Fallback: retry without response_format and parse manually.
            response = self._llm.create_chat_completion(
                messages=chat_messages,
                max_tokens=max_tokens,
                stream=False,
            )
            content = response["choices"][0]["message"]["content"]
            return extract_json(content)

    def health_check(self) -> dict:
        if self._llm is not None:
            return {
                "status": "ok",
                "detail": f"embedded: {self.model} loaded",
            }
        return {"status": "error", "detail": "model not loaded"}

    def load_guideline(
        self,
        guideline_text: str,
        clauses: dict[str, str],
        clause_reqs: dict[str, list],
    ) -> None:
        """Estimate required context size from the guideline length.

        If the guideline is large enough that the current ``n_ctx`` may be
        insufficient, this is logged as a warning.  llama-cpp-python loads
        the model with a fixed context window, so we cannot resize after
        the fact — but we can warn the user.
        """
        # Rough heuristic: ~4 chars per token.  The system prompt includes
        # the guideline plus instructions (~1000 tokens overhead) plus
        # conversation history and response space.
        guideline_tokens = len(guideline_text) // 4
        needed = guideline_tokens + 2048  # overhead + response buffer
        if needed > self._n_ctx:
            import warnings

            warnings.warn(
                f"Guideline is ~{guideline_tokens} tokens but the model "
                f"context window is {self._n_ctx}. Long conversations may "
                "be truncated. Consider using a model with a larger "
                "context window or a retrieval-based backend.",
                stacklevel=2,
            )

    # ------------------------------------------------------------------
    # Class helpers
    # ------------------------------------------------------------------
    @classmethod
    def is_available(cls) -> bool:
        """Return True if llama-cpp-python is importable."""
        try:
            import llama_cpp  # noqa: F401

            return True
        except ImportError:
            return False

    @classmethod
    def has_cached_model(cls) -> bool:
        """Return True if a GGUF model file exists in the cache."""
        if not _MODEL_CACHE.is_dir():
            return False
        return any(_MODEL_CACHE.glob("*.gguf"))
