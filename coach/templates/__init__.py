"""Scenario templates for the deterministic Template backend.

Re-exports the public API so callers can write::

    from coach.templates import SCENARIOS, KEYWORD_INDEX
"""

from .scenarios import KEYWORD_INDEX, SCENARIOS

__all__ = ["SCENARIOS", "KEYWORD_INDEX"]
