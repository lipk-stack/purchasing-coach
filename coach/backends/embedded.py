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
import shutil
import sys
from collections.abc import Iterator
from importlib import resources as _resources
from pathlib import Path

from .base import BackendProtocol
from .openai_compat import BackendError, extract_json

# Default model: Qwen2.5-1.5B-Instruct (Q4_K_M quantisation, ~1.12 GB).
# Best size/quality tradeoff for structured procurement output.
DEFAULT_MODEL_REPO = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
DEFAULT_MODEL_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"

# Where cached models are stored.
_MODEL_CACHE = Path.home() / ".purchasing-coach" / "models"

# Package that holds a GGUF model bundled *with* the application — this is
# where ``scripts/build_portable.py --with-model`` drops the file so the model
# ships inside the zipapp and runs with no download.
# NOTE: Cannot use "coach.models" — that name is taken by the dataclass
# module (coach/models.py).
_BUNDLED_PACKAGE = "coach.gguf_models"

# ---------------------------------------------------------------------------
# Generation tuning — small models (1.5B) fall into runaway repetition loops
# unless sampling is constrained and end-of-turn markers are enforced. These
# defaults curb that at the source; the client-side loop guard below is the
# safety net for when they don't.
# ---------------------------------------------------------------------------
_TEMPERATURE = 0.3        # chat: a little randomness breaks repetition cycles
_JSON_TEMPERATURE = 0.1   # structured output: near-deterministic
_TOP_P = 0.9
_TOP_K = 40
_REPEAT_PENALTY = 1.18    # > the llama.cpp default (1.1); discourages loops
# ChatML / common end-of-turn markers, used as a stop-sequence safety net in
# case the GGUF's own EOS metadata is missing or its chat template is
# misdetected — a classic cause of never-ending, looping generation.
_STOP_SEQUENCES = ["<|im_end|>", "<|endoftext|>", "<|eot_id|>", "</s>"]

# Client-side anti-loop guard for streamed chat. Even with the sampling above a
# small model can get stuck repeating a phrase forever, so we cap total output
# and stop when the tail is a short block repeated several times in a row.
_MAX_STREAM_CHARS = 8000
_LOOP_MIN_PERIOD = 6      # ignore trivially short cycles ("...", ", , ,")
_LOOP_MAX_PERIOD = 160
_LOOP_REPEATS = 3         # this many identical consecutive blocks => a loop


def _looping_tail(text: str) -> bool:
    """True if ``text`` ends with a block repeated ``_LOOP_REPEATS`` times.

    Period-agnostic: detects ``XYZXYZXYZ`` for any block length in
    ``[_LOOP_MIN_PERIOD, _LOOP_MAX_PERIOD]``. Normal prose and numbered lists
    (whose items differ) don't match; a model stuck echoing the same sentence
    does.
    """
    n = len(text)
    for period in range(_LOOP_MIN_PERIOD, _LOOP_MAX_PERIOD + 1):
        span = period * _LOOP_REPEATS
        if n < span:
            break
        segment = text[-span:]
        if segment == segment[:period] * _LOOP_REPEATS:
            return True
    return False


def _guard_stream(chunks: Iterator[str]) -> Iterator[str]:
    """Pass streamed text through, stopping on runaway repetition or length.

    Guarantees the stream terminates even if the model never emits a stop
    token: it ends after ``_MAX_STREAM_CHARS`` of output or as soon as the
    accumulated tail looks like a repetition loop.
    """
    buf: list[str] = []
    total = 0
    for chunk in chunks:
        if not chunk:
            continue
        buf.append(chunk)
        total += len(chunk)
        yield chunk
        if total >= _MAX_STREAM_CHARS:
            return
        # Only re-scan the tail; the loop detector never needs more than this.
        if _looping_tail("".join(buf)[-(_LOOP_MAX_PERIOD * _LOOP_REPEATS):]):
            return


def _estimate_tokens(text: str) -> int:
    """Rough token count for budgeting (~4 chars/token, +1 to avoid zero)."""
    return len(text) // 4 + 1


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
        Context window size in tokens (default 8192). The guideline is injected
        into the prompt, so a window smaller than the guideline plus room for a
        reply will cause the system prompt to be trimmed to fit.
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
        n_ctx: int = 8192,
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
        3. A model deployed together with the application (bundled in the
           zipapp, or a ``models/`` folder beside the executable —
           see :meth:`_bundled_model`)
        4. Cached model in ``~/.purchasing-coach/models/``
        5. Auto-download from HuggingFace Hub
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

        # 3. Model shipped with the application (truly portable, no download).
        bundled = EmbeddedBackend._bundled_model()
        if bundled:
            return bundled

        # 4. Cache directory — look for any .gguf file
        _MODEL_CACHE.mkdir(parents=True, exist_ok=True)
        cached = list(_MODEL_CACHE.glob("*.gguf"))
        if cached:
            return cached[0]

        # 5. Auto-download
        return EmbeddedBackend._download_model()

    # ------------------------------------------------------------------
    # Bundled / adjacent model discovery
    # ------------------------------------------------------------------
    @staticmethod
    def _adjacent_model_dirs() -> list[Path]:
        """Directories to scan for a GGUF shipped alongside the application.

        Covers the portable "ship the app + a ``models/`` folder" layout: a
        ``models/`` directory (or a loose ``.gguf``) next to the running
        ``.pyz``/executable, an ``EMBEDDED_MODEL_DIR`` override, and a
        ``models/`` folder next to the installed package source.
        """
        dirs: list[Path] = []
        try:
            app = Path(sys.argv[0]).resolve().parent
            dirs += [app / "models", app]
        except (OSError, IndexError):
            pass
        env_dir = os.environ.get("EMBEDDED_MODEL_DIR")
        if env_dir:
            dirs.append(Path(env_dir))
        try:
            dirs.append(Path(__file__).resolve().parent.parent.parent / "models")
        except OSError:
            pass
        return dirs

    @staticmethod
    def _adjacent_gguf() -> Path | None:
        """First real ``.gguf`` file in an adjacent directory, if any."""
        for d in EmbeddedBackend._adjacent_model_dirs():
            try:
                if d.is_dir():
                    found = sorted(d.glob("*.gguf"))
                    if found:
                        return found[0]
            except OSError:
                continue
        return None

    @staticmethod
    def _packaged_gguf_name() -> str | None:
        """Name of a GGUF bundled in the ``coach.models`` package, if present."""
        try:
            root = _resources.files(_BUNDLED_PACKAGE)
        except (ModuleNotFoundError, TypeError, FileNotFoundError):
            return None
        try:
            for entry in root.iterdir():
                if entry.name.endswith(".gguf"):
                    return entry.name
        except (OSError, FileNotFoundError):
            return None
        return None

    @staticmethod
    def _bundled_model() -> Path | None:
        """Locate a model deployed with the application.

        Prefers a real file in an adjacent ``models/`` folder. A model bundled
        *inside* the zipapp can't be memory-mapped from the archive, so it is
        extracted once into the cache and reused thereafter.
        """
        adjacent = EmbeddedBackend._adjacent_gguf()
        if adjacent:
            return adjacent

        name = EmbeddedBackend._packaged_gguf_name()
        if not name:
            return None
        _MODEL_CACHE.mkdir(parents=True, exist_ok=True)
        dest = _MODEL_CACHE / name
        if not dest.is_file():
            resource = _resources.files(_BUNDLED_PACKAGE) / name
            with _resources.as_file(resource) as real_path:
                shutil.copy2(real_path, dest)
        return dest

    @staticmethod
    def _download_model() -> Path:
        """Download the default model from HuggingFace Hub."""
        try:
            from huggingface_hub import hf_hub_download  # type: ignore[import-untyped]
        except ImportError as exc:
            # llama-cpp-python depends on huggingface-hub, so this should
            # always be available — but handle it gracefully just in case.
            raise BackendError(
                "huggingface-hub is needed to download the default model.\n"
                "Install it with: pip install huggingface-hub\n"
                "Or provide a local GGUF file via --model-path or "
                "EMBEDDED_MODEL_PATH."
            ) from exc

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
    # Context budgeting — the guideline is large and is injected into every
    # prompt; without this the prompt overflows ``n_ctx`` and the model emits
    # degenerate, looping output.
    # ------------------------------------------------------------------
    def _fit_system(self, system: str, reserve_tokens: int) -> str:
        """Trim the system prompt's guideline so the prompt fits the window.

        Keeps room for ``reserve_tokens`` of response plus a little history.
        When the system prompt is too large its ``<guideline>`` body is
        truncated (with a marker) rather than letting the context overflow.
        """
        budget = self._n_ctx - reserve_tokens - 256  # 256 ≈ history/overhead
        if budget < 256 or _estimate_tokens(system) <= budget:
            return system
        max_chars = budget * 4
        open_tag, close_tag = "<guideline>", "</guideline>"
        start = system.find(open_tag)
        end = system.find(close_tag)
        marker = "\n…[guideline truncated to fit the model context window]…\n"
        if start != -1 and end != -1 and end > start:
            head = system[:start + len(open_tag)]
            body = system[start + len(open_tag):end]
            keep = max_chars - len(head) - len(close_tag) - len(marker)
            if keep > 0:
                return head + body[:keep] + marker + system[end:]
        # No guideline block (or no room) — hard truncate as a last resort.
        return system[:max(256, max_chars)] + marker

    def _cap_tokens(self, messages: list[dict], requested: int) -> int:
        """Clamp the response token budget so prompt + reply fit ``n_ctx``."""
        used = sum(_estimate_tokens(m.get("content", "")) for m in messages)
        available = self._n_ctx - used - 32
        return max(128, min(requested, available))

    # ------------------------------------------------------------------
    # BackendProtocol implementation
    # ------------------------------------------------------------------
    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1536,
    ) -> Iterator[str]:
        system = self._fit_system(system, max_tokens)
        chat_messages = [
            {"role": "system", "content": system},
            *messages,
        ]
        response = self._llm.create_chat_completion(
            messages=chat_messages,
            max_tokens=self._cap_tokens(chat_messages, max_tokens),
            stream=True,
            temperature=_TEMPERATURE,
            top_p=_TOP_P,
            top_k=_TOP_K,
            repeat_penalty=_REPEAT_PENALTY,
            stop=_STOP_SEQUENCES,
        )

        def _deltas() -> Iterator[str]:
            for chunk in response:
                choices = chunk.get("choices") or []
                if choices:
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield delta

        # The loop guard guarantees termination even if the model never stops.
        yield from _guard_stream(_deltas())

    def complete_json(
        self,
        system: str,
        prompt: str,
        schema: dict,
        schema_name: str,
        max_tokens: int = 4096,
    ) -> dict:
        full_prompt = (
            f"{prompt}\n\nRespond with a single JSON object matching this "
            f"JSON schema, with no extra commentary:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        system = self._fit_system(system, max_tokens)
        chat_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": full_prompt},
        ]
        capped = self._cap_tokens(chat_messages, max_tokens)
        common = dict(
            messages=chat_messages,
            max_tokens=capped,
            stream=False,
            temperature=_JSON_TEMPERATURE,
            top_p=_TOP_P,
            top_k=_TOP_K,
            repeat_penalty=_REPEAT_PENALTY,
            stop=_STOP_SEQUENCES,
        )

        # Try with guided JSON schema first (llama-cpp-python supports
        # this via response_format with a json_schema).
        try:
            response = self._llm.create_chat_completion(
                response_format={"type": "json_object", "schema": schema},
                **common,
            )
            content = response["choices"][0]["message"]["content"]
            return extract_json(content)
        except (TypeError, ValueError, KeyError):
            # Fallback: retry without response_format and parse manually.
            response = self._llm.create_chat_completion(**common)
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
                f"context window is {self._n_ctx}; the guideline will be "
                "trimmed to fit each prompt. For full coverage, raise the "
                "window with --n-ctx (e.g. 16384) or use a retrieval-based "
                "backend (keyword/bm25/template) which indexes the whole "
                "guideline.",
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
        """Return True if a GGUF model is available without downloading.

        Covers a model deployed with the application (bundled in the zipapp or
        in a ``models/`` folder beside it) as well as the home cache, so
        auto-detect can select the embedded backend when a model ships with the
        app.
        """
        if cls._adjacent_gguf() is not None:
            return True
        if cls._packaged_gguf_name() is not None:
            return True
        return _MODEL_CACHE.is_dir() and any(_MODEL_CACHE.glob("*.gguf"))
