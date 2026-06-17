"""Hybrid RAG backend combining BM25 + cosine similarity via RRF fusion.

Provides higher retrieval quality than the keyword backend alone by
combining two complementary ranking strategies:

- **BM25** excels at exact-term matching and is robust to document length.
- **Cosine similarity** (TF-IDF vectors) captures semantic overlap even
  when the query and document use different surface forms.

Both rankers are run against the same inverted index and their results
are merged with *Reciprocal Rank Fusion* (RRF), which is parameter-free
and well-suited to combining heterogeneous rankers.

An optional procurement-domain thesaurus expands the query with synonyms
before retrieval, improving recall for common purchasing terms (e.g.
"server" -> "compute", "hosting", "infrastructure").

No AI model is required -- everything runs locally against the indexed
guideline.
"""

import re
from collections.abc import Iterator

from .base import BackendProtocol

# ---------------------------------------------------------------------------
# Procurement thesaurus for query expansion.
#
# Maps a canonical term to its top synonyms.  Only the first two synonyms
# are appended to keep the expanded query focused.  The thesaurus is
# deliberately small and curated -- a larger thesaurus would introduce
# noise that hurts precision on short guideline documents.
# ---------------------------------------------------------------------------
SYNONYMS: dict[str, list[str]] = {
    "server": ["compute", "hosting", "infrastructure", "datacenter"],
    "security": ["cybersecurity", "infosec", "information security", "compliance"],
    "cloud": ["saas", "iaas", "paas", "hosted", "cloud computing"],
    "contract": ["agreement", "engagement", "procurement"],
    "data": ["information", "records", "personal data", "pdpa"],
    "support": ["maintenance", "sla", "service level", "helpdesk"],
    "hardware": ["equipment", "device", "appliance", "physical"],
    "software": ["application", "license", "licensing", "tool"],
    "network": ["connectivity", "infrastructure", "lan", "wan"],
    "audit": ["assessment", "review", "evaluation", "penetration test"],
    "vendor": ["supplier", "provider", "contractor", "service provider"],
    "payment": ["pci", "financial", "transaction", "pci dss"],
    "integration": ["interoperability", "sso", "api", "interface"],
    "cost": ["budget", "pricing", "tco", "total cost of ownership", "financial"],
}


class BM25Backend(BackendProtocol):
    """Hybrid retrieval backend using BM25 + cosine + RRF fusion.

    Attributes:
        name: Backend identifier shown in the UI and CLI.
        model: Always ``"N/A"`` -- no model is loaded.
        requires_model: ``False``; works entirely without an LLM.
    """

    name = "bm25"
    model = "N/A"
    requires_model = False

    def __init__(self) -> None:
        self._index = None  # InvertedIndex (lazy import)
        self._clauses: dict[str, str] = {}
        self._clause_reqs: dict[str, list] = {}
        self._guideline_text: str = ""
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # BackendProtocol hooks
    # ------------------------------------------------------------------

    def load_guideline(
        self,
        guideline_text: str,
        clauses: dict[str, str],
        clause_reqs: dict[str, list],
    ) -> None:
        """Build the inverted index used by both BM25 and cosine rankers.

        Called once by the Coach orchestration layer after the guideline
        document has been parsed.
        """
        from ..retrieval import InvertedIndex

        self._clauses = clauses
        self._clause_reqs = clause_reqs
        self._guideline_text = guideline_text
        self._index = InvertedIndex()
        self._index.build_from_guideline(guideline_text, clauses, clause_reqs)
        self._loaded = True

    def health_check(self) -> dict:
        """Report indexing status."""
        if self._loaded:
            return {
                "status": "ok",
                "detail": (
                    f"bm25: {len(self._clauses)} clauses indexed "
                    "(hybrid retrieval)"
                ),
            }
        return {
            "status": "ok",
            "detail": "bm25: ready (no guideline loaded yet)",
        }

    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """Answer by hybrid-retrieving relevant clauses and composing a cited response.

        Uses the last user message as the query, expands it with synonyms,
        runs both BM25 and cosine retrieval, fuses the rankings with RRF,
        and yields a markdown-formatted answer citing the top results.
        """
        query = messages[-1]["content"] if messages else ""

        if not self._loaded or not self._index:
            yield (
                "The BM25 backend is ready, but no guideline has been "
                "loaded yet. Please provide a guideline document."
            )
            return

        results = self._hybrid_retrieve(query, top_k=5)

        if not results:
            yield (
                "I couldn't find relevant sections for your question. "
                "Try different keywords or ask about a specific guideline topic."
            )
            return

        # Compose a well-structured response with citations
        response_parts: list[str] = [
            "Based on the guideline, here are the most relevant sections:\n",
        ]

        for i, (doc_id, score, meta) in enumerate(results[:3]):
            ref = meta.get("ref", "")
            title = meta.get("title", "General")
            text = meta.get("text", "")
            # Show more text for the top result
            max_len = 400 if i == 0 else 250
            if len(text) > max_len:
                text = text[:max_len] + "..."
            response_parts.append(f"### {ref} {title}\n{text}\n")

        if len(results) > 3:
            other_refs = ", ".join(
                f"**{meta.get('ref', '?')}**"
                for _, _, meta in results[3:]
            )
            response_parts.append(
                f"Other potentially relevant sections: {other_refs}"
            )

        full = "\n".join(response_parts)
        yield from _sentence_chunks(full)

    def complete_json(
        self,
        system: str,
        prompt: str,
        schema: dict,
        schema_name: str,
        max_tokens: int = 8192,
    ) -> dict:
        """Generate structured JSON using hybrid retrieval.

        Dispatches to the interview-plan builder or the checklist builder
        depending on *schema_name*.
        """
        if schema_name == "interview_plan":
            return self._plan_interview(prompt)
        return self._build_checklist(prompt, schema)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def _expand_query(self, query: str) -> str:
        """Add synonyms from the procurement thesaurus.

        For each word in the query that has a thesaurus entry, the top
        two synonyms are appended to the query string.  This improves
        recall for domain-specific terms without requiring a neural model.
        """
        words = query.lower().split()
        expansions: list[str] = []
        for word in words:
            if word in SYNONYMS:
                expansions.extend(SYNONYMS[word][:2])
        if expansions:
            return query + " " + " ".join(expansions)
        return query

    def _hybrid_retrieve(
        self, query: str, top_k: int = 5
    ) -> list[tuple[int, float, dict]]:
        """Use BM25 + cosine + RRF fusion for high-quality retrieval.

        Steps:
        1. Expand the query with procurement synonyms.
        2. Run BM25 ranking (term-frequency based, robust to length).
        3. Run cosine similarity ranking (TF-IDF vectors, semantic overlap).
        4. Fuse both rankings with Reciprocal Rank Fusion.

        Returns a list of ``(doc_id, fused_score, metadata)`` tuples
        sorted by descending fused score.
        """
        from ..retrieval import BM25Ranker, CosineRanker, rrf_fusion

        expanded = self._expand_query(query)

        bm25 = BM25Ranker(self._index)
        cosine = CosineRanker(self._index)

        # Fetch more candidates than needed so RRF has room to re-rank
        bm25_results = bm25.score(expanded, top_k=top_k * 2)
        cosine_results = cosine.score(expanded, top_k=top_k * 2)

        return rrf_fusion(bm25_results, cosine_results, top_k=top_k)

    # ------------------------------------------------------------------
    # Interview plan
    # ------------------------------------------------------------------

    def _plan_interview(self, prompt: str) -> dict:
        """Generate interview questions from guideline coverage questions.

        Uses the same approach as the keyword backend:
        :func:`coach.guideline.relevant_coverage_questions` for
        guideline-grounded questions tailored to the item, with generic
        procurement fallbacks for unstructured text.
        """
        from ..guideline import relevant_coverage_questions

        item_match = re.search(r"<item>(.*?)</item>", prompt, re.DOTALL)
        item_desc = item_match.group(1).strip() if item_match else prompt.strip()

        # Coverage questions grounded in the guideline's sections, tailored to
        # the item being purchased.
        questions: list[dict[str, str]] = []
        for i, (keywords, question) in enumerate(
            relevant_coverage_questions(self._clauses, item_desc), 1
        ):
            questions.append({"key": f"cover_{i}", "question": question})

        # Generic fallbacks for unstructured guidelines
        if not questions:
            questions = [
                {"key": "q1", "question": "What is the issue date for this tender?"},
                {"key": "q2", "question": "What is the submission deadline?"},
                {"key": "q3", "question": "Who is issuing this tender?"},
                {"key": "q4", "question": "What is the estimated value?"},
                {
                    "key": "q5",
                    "question": "Does this involve personal or payment data?",
                },
                {
                    "key": "q6",
                    "question": "Is it hardware, software, cloud, or services?",
                },
                {
                    "key": "q7",
                    "question": "Will it connect to internal networks?",
                },
                {
                    "key": "q8",
                    "question": "What support level is required?",
                },
            ]

        # Cap at 16 questions (consistent with LLM backends)
        return {"questions": questions[:16]}

    # ------------------------------------------------------------------
    # Checklist (clause selection)
    # ------------------------------------------------------------------

    def _build_checklist(self, prompt: str, schema: dict) -> dict:
        """Use hybrid retrieval to select applicable clauses.

        Combines the item description and interview Q&A as a single query,
        expands it with procurement synonyms, runs BM25 + cosine + RRF
        fusion, and selects clauses above a relevance threshold.  Core
        sections (contract terms, information security, compliance/risk)
        are always included when present in the guideline.
        """
        item_match = re.search(r"<item>(.*?)</item>", prompt, re.DOTALL)
        interview_match = re.search(
            r"<interview>(.*?)</interview>", prompt, re.DOTALL
        )
        item_desc = item_match.group(1).strip() if item_match else ""
        qa_text = interview_match.group(1).strip() if interview_match else prompt

        combined_query = f"{item_desc} {qa_text}"

        if not self._loaded:
            return {
                "tender_info": {
                    k: "TBC"
                    for k in (
                        "issue_date",
                        "submission_deadline",
                        "purchase_item",
                        "issued_by",
                        "requesting_dept",
                        "tender_reference",
                        "procurement_type",
                        "estimated_value",
                        "purchase_category",
                    )
                },
                "requirements": [],
            }

        results = self._hybrid_retrieve(
            combined_query, top_k=min(25, len(self._clauses))
        )

        requirements: list[dict[str, str]] = []
        if results:
            # RRF scores are typically lower than raw BM25 -- use a
            # 25% threshold relative to the top score.
            max_score = results[0][1] if results else 1
            threshold = max_score * 0.25

            for _doc_id, score, meta in results:
                if score < threshold:
                    continue
                ref = meta.get("ref", "")
                title = meta.get("title", "")
                if not ref:
                    continue

                clause_reqs = self._clause_reqs.get(ref, [])
                has_must = any(
                    "must" in r.requirement.lower()
                    or "shall" in r.requirement.lower()
                    for r in clause_reqs
                )
                mandatory = "M" if has_must else "O"

                requirements.append(
                    {
                        "ref": ref,
                        "section": title,
                        "requirement": (
                            f"Comply with {ref} {title} requirements"
                        ),
                        "mandatory": mandatory,
                    }
                )

        # Always include core sections when the guideline contains them
        for core_ref in ("4", "5", "11"):
            for ref, title in self._clauses.items():
                if ref == core_ref or ref.startswith(core_ref + "."):
                    if not any(r["ref"] == ref for r in requirements):
                        requirements.append(
                            {
                                "ref": ref,
                                "section": title,
                                "requirement": (
                                    f"Comply with {ref} {title} requirements"
                                ),
                                "mandatory": "M",
                            }
                        )

        tender_info = self._default_tender_info(item_desc)

        return {
            "tender_info": tender_info,
            "requirements": requirements[:50],  # Cap at 50
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_tender_info(item_desc: str) -> dict[str, str]:
        """Return a tender-info dict with TBC placeholders."""
        ref_slug = (
            item_desc[:20].strip().upper().replace(" ", "-")
            if item_desc
            else "TBC"
        )
        return {
            "issue_date": "TBC",
            "submission_deadline": "TBC",
            "purchase_item": item_desc or "TBC",
            "issued_by": "TBC",
            "requesting_dept": "TBC",
            "tender_reference": f"TENDER-{ref_slug}" if item_desc else "TBC",
            "procurement_type": "TBC",
            "estimated_value": "TBC",
            "purchase_category": "TBC",
        }


# --------------------------------------------------------------------------
# Module-level helpers
# --------------------------------------------------------------------------

def _sentence_chunks(text: str, chunk_size: int = 40) -> Iterator[str]:
    """Split *text* into small word-based chunks for simulated streaming.

    Yields up to *chunk_size* words per chunk, preserving spacing between
    chunks so the streamed output reads naturally when concatenated.
    """
    words = text.split()
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i : i + chunk_size])
        if i + chunk_size < len(words):
            chunk += " "
        yield chunk
