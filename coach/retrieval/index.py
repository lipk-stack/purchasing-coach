"""Postings-list based inverted index with BM25 statistics.

Builds a term -> {doc_id -> term_freq} index from procurement guideline
clauses so that the BM25 and cosine rankers can score queries against
individual clause documents.  Pure-Python, no external dependencies.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .tokenizer import tokenize


class InvertedIndex:
    """Postings-list based inverted index with BM25 statistics.

    Each *document* in the index corresponds to a single guideline clause
    (or top-level section).  Documents are added via :meth:`add` or
    bulk-loaded from a parsed guideline via :meth:`build_from_guideline`.

    Attributes:
        postings:   Mapping from stemmed term to a dict of
                    ``{doc_id: term_frequency}``.
        doc_lengths: Number of tokens in each document (after tokenisation).
        documents:  Metadata dict for each document, keyed by ``doc_id``.
        N:          Total number of documents.
        avgdl:      Mean document length in tokens.
    """

    def __init__(self) -> None:
        self.postings: dict[str, dict[int, int]] = {}
        self.doc_lengths: dict[int, int] = {}
        self.documents: dict[int, dict[str, Any]] = {}
        self.N: int = 0
        self.avgdl: float = 0.0

    # ------------------------------------------------------------------
    # Document ingestion
    # ------------------------------------------------------------------

    def add(self, doc_id: int, text: str, metadata: dict[str, Any] | None = None) -> None:
        """Tokenise *text* and add it as document *doc_id*.

        Args:
            doc_id:   Unique integer identifier for this document.
            text:     Raw text to be tokenised and indexed.
            metadata: Arbitrary metadata stored alongside the document
                      (e.g. ``ref``, ``title``, ``requirements``).
        """
        tokens = tokenize(text)
        self.doc_lengths[doc_id] = len(tokens)
        self.documents[doc_id] = metadata if metadata is not None else {}

        # Build term-frequency map for this document.
        tf_map: dict[str, int] = {}
        for tok in tokens:
            tf_map[tok] = tf_map.get(tok, 0) + 1

        # Merge into the global postings list.
        for term, freq in tf_map.items():
            if term not in self.postings:
                self.postings[term] = {}
            self.postings[term][doc_id] = freq

        self._recompute_stats()

    def build_from_guideline(
        self,
        guideline_text: str,
        clauses: dict[str, str],
        clause_reqs: dict[str, list],
    ) -> None:
        """Build the index from a parsed guideline.

        Each clause (identified by a ref like ``"5.3"``) becomes one
        document.  The document text includes the clause title and all
        requirement paragraphs under that clause.

        Top-level section headings (single-part refs such as ``"5"``) are
        also added as their own documents whose text aggregates every
        requirement across all sub-clauses, giving the ranker a broad
        section-level match target in addition to granular sub-clause
        matches.

        Args:
            guideline_text: The full guideline markdown text (currently
                            unused beyond clause/req data, reserved for
                            future full-text indexing).
            clauses:        ``{ref: heading_title}`` as returned by
                            :func:`coach.guideline.parse_clauses`.
            clause_reqs:    ``{ref: [RequirementRow, ...]}`` as returned by
                            :func:`coach.guideline.parse_clause_requirements`.
        """
        if not clauses:
            return

        # Collect requirement text grouped by exact clause ref.
        req_text_by_ref: dict[str, list[str]] = {}
        for ref, rows in clause_reqs.items():
            texts: list[str] = []
            for row in rows:
                req = getattr(row, "requirement", None)
                if req is None and isinstance(row, dict):
                    req = row.get("requirement", "")
                if req:
                    texts.append(str(req))
            req_text_by_ref[ref] = texts

        doc_id = 0

        # --- per-clause documents (sub-clauses) ---
        for ref in sorted(clauses, key=_clause_sort_key):
            title = clauses[ref]
            parts: list[str] = [title]

            # Gather requirement text for this exact ref.
            for req_text in req_text_by_ref.get(ref, []):
                parts.append(req_text)

            # Also include sub-clause requirement text for this clause
            # (e.g. clause "5.3" gets its own reqs, and if "5.3.1" exists
            # those reqs are folded in as well).
            for other_ref, texts in req_text_by_ref.items():
                if other_ref != ref and other_ref.startswith(ref + "."):
                    for t in texts:
                        parts.append(t)

            doc_text = " ".join(parts)
            req_list = list(req_text_by_ref.get(ref, []))

            metadata = {
                "ref": ref,
                "title": title,
                "section": title,
                "requirements": req_list,
                "kind": "clause",
            }
            self.add(doc_id, doc_text, metadata)
            doc_id += 1

        # --- top-level section documents ---
        # A top-level section is one whose ref has no dots (e.g. "5").
        # These aggregate ALL sub-clause requirement text, giving the
        # ranker a broader match target for section-level queries.
        for ref in sorted(clauses, key=_clause_sort_key):
            if "." in ref:
                continue  # skip sub-clauses
            title = clauses[ref]
            parts = [title]
            req_list: list[str] = []

            # Collect all requirement text from sub-clauses of this section.
            for other_ref, texts in req_text_by_ref.items():
                if other_ref == ref or other_ref.startswith(ref + "."):
                    parts.extend(texts)
                    req_list.extend(texts)

            doc_text = " ".join(parts)
            metadata = {
                "ref": ref,
                "title": title,
                "section": title,
                "requirements": req_list,
                "kind": "section",
            }
            self.add(doc_id, doc_text, metadata)
            doc_id += 1

    # ------------------------------------------------------------------
    # Term statistics
    # ------------------------------------------------------------------

    def tf(self, term: str, doc_id: int) -> int:
        """Term frequency of *term* in document *doc_id*.

        Returns 0 when the term does not appear in the document.
        """
        return self.postings.get(term, {}).get(doc_id, 0)

    def df(self, term: str) -> int:
        """Document frequency: number of documents containing *term*.

        Returns 0 when the term is not in the index at all.
        """
        return len(self.postings.get(term, {}))

    def idf(self, term: str) -> float:
        """Inverse document frequency using the BM25 variant.

        .. math::

            \\text{IDF} = \\log\\!\\left(\\frac{N - df + 0.5}{df + 0.5} + 1\\right)

        Returns 0.0 when there are no documents or the term is unknown.
        """
        if self.N == 0:
            return 0.0
        d = self.df(term)
        return math.log((self.N - d + 0.5) / (d + 0.5) + 1.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recompute_stats(self) -> None:
        """Recalculate *N* and *avgdl* after document additions."""
        self.N = len(self.documents)
        if self.N > 0:
            total = sum(self.doc_lengths.values())
            self.avgdl = total / self.N
        else:
            self.avgdl = 0.0


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

_CLAUSE_NUM_RE = re.compile(r"\d+(?:\.\d+)*")


def _clause_sort_key(ref: str) -> tuple[int, tuple[int, ...]]:
    """Sort key that orders clause refs numerically (5.1 < 5.10 < 11)."""
    m = _CLAUSE_NUM_RE.search(ref or "")
    if not m:
        return (1, ())
    return (0, tuple(int(p) for p in m.group(0).split(".")))
