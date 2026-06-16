"""Abstract base class for all Purchasing Coach backends.

Every backend — whether LLM-powered, rule-based, or retrieval-augmented —
implements the same two-method protocol so the Coach orchestration layer
(``llm.py``) is completely backend-agnostic.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator


class BackendProtocol(ABC):
    """Interface that every backend must implement.

    Attributes:
        name: Human-readable backend identifier (e.g. ``"keyword"``).
        model: Model name or ``"N/A"`` for rule-based backends.
        requires_model: ``True`` for LLM backends that need a loaded model;
            ``False`` for deterministic / retrieval-based backends.
    """

    name: str = ""
    model: str = "N/A"
    requires_model: bool = False

    # ------------------------------------------------------------------
    # Required interface
    # ------------------------------------------------------------------
    @abstractmethod
    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """Yield text chunks for a conversational reply.

        ``system`` is the system prompt (which for this app always embeds
        the guideline). ``messages`` is the ``[{role, content}]`` history.
        """

    @abstractmethod
    def complete_json(
        self,
        system: str,
        prompt: str,
        schema: dict,
        schema_name: str,
        max_tokens: int = 8192,
    ) -> dict:
        """Return a JSON object validated against *schema*.

        Used for structured outputs (interview plans, tender checklists).
        """

    # ------------------------------------------------------------------
    # Optional hooks — defaults are safe no-ops
    # ------------------------------------------------------------------
    def health_check(self) -> dict:
        """Return ``{"status": "ok"|"error", "detail": str}``.

        The web UI polls this for the connection status indicator.
        """
        return {"status": "ok", "detail": self.name or "unknown"}

    def load_guideline(
        self,
        guideline_text: str,
        clauses: dict[str, str],
        clause_reqs: dict[str, list],
    ) -> None:
        """Pre-load the guideline into the backend's retrieval index.

        LLM backends ignore this (they receive the guideline via the system
        prompt). Retrieval-based backends build their index here.
        """
