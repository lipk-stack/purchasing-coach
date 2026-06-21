"""Rule-based keyword backend -- answers questions and selects clauses
using BM25 retrieval against the guideline, no AI model required.

This is the zero-dependency fallback backend.  When no local LLM server
or cloud API key is available the Coach falls back to this backend, which
builds a BM25 inverted index over the guideline clauses at load time and
answers questions by retrieving and citing the most relevant sections.

Structured outputs (interview plans and tender checklists) are produced
by combining guideline coverage questions, keyword-based clause selection
and simple pattern extraction -- no generative model involved.
"""

import re
from collections.abc import Iterator

from .base import BackendProtocol, sentence_chunks


class KeywordBackend(BackendProtocol):
    """Deterministic backend that uses BM25 retrieval only.

    Attributes:
        name: Backend identifier shown in the UI and CLI.
        model: Always ``"N/A"`` -- no model is loaded.
        requires_model: ``False``; works entirely without an LLM.
    """

    name = "keyword"
    model = "N/A"
    requires_model = False

    def __init__(self) -> None:
        self._index = None  # InvertedIndex (lazy import)
        self._clauses: dict[str, str] = {}
        self._clause_reqs: dict[str, list] = {}
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
        """Build the BM25 inverted index from the parsed guideline.

        Called once by the Coach orchestration layer after the guideline
        document has been parsed.  The index powers both ``stream_chat``
        (question answering) and ``complete_json`` (clause selection).
        """
        from ..retrieval import InvertedIndex

        self._clauses = clauses
        self._clause_reqs = clause_reqs
        self._index = InvertedIndex()
        self._index.build_from_guideline(guideline_text, clauses, clause_reqs)
        self._loaded = True

    def health_check(self) -> dict:
        """Report indexing status."""
        if self._loaded:
            return {
                "status": "ok",
                "detail": f"keyword: {len(self._clauses)} clauses indexed",
            }
        return {
            "status": "ok",
            "detail": "keyword: ready (no guideline loaded yet)",
        }

    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """Answer by retrieving relevant clauses and composing a cited response.

        Uses the last user message as the query, runs BM25 retrieval over
        the indexed guideline, and yields a markdown-formatted answer that
        cites the top three matching clauses by reference number and title.
        """
        query = messages[-1]["content"] if messages else ""

        if not self._loaded or not self._index:
            yield (
                "The keyword backend is ready, but no guideline has been "
                "loaded yet. Please provide a guideline document to enable "
                "me to answer questions."
            )
            return

        from ..retrieval import BM25Ranker

        ranker = BM25Ranker(self._index)
        results = ranker.score(query, top_k=5)

        if not results:
            yield (
                "I couldn't find any relevant sections in the guideline for "
                "your question. Try rephrasing or ask about a specific topic "
                "covered in the guideline."
            )
            return

        # Compose a response citing the top results
        response_parts: list[str] = [
            "Based on the purchasing guideline, here's what I found:\n",
        ]

        for _i, (_doc_id, _score, meta) in enumerate(results[:3]):
            ref = meta.get("ref", "")
            title = meta.get("title", "General")
            text = meta.get("text", "")
            # Trim text to ~300 chars for readability
            if len(text) > 300:
                text = text[:300] + "..."
            response_parts.append(f"- **{ref}** -- {title}: {text}\n")

        shown = min(3, len(results))
        response_parts.append(
            f"\nThese are the {shown} most relevant sections. "
            "Let me know if you'd like more detail on any specific clause."
        )

        full_response = "\n".join(response_parts)
        # Yield sentence-by-sentence for simulated streaming
        yield from sentence_chunks(full_response)

    def complete_json(
        self,
        system: str,
        prompt: str,
        schema: dict,
        schema_name: str,
        max_tokens: int = 8192,
    ) -> dict:
        """Generate structured JSON using keyword matching against the guideline.

        Dispatches to the interview-plan builder or the checklist builder
        depending on *schema_name*.
        """
        if schema_name == "interview_plan":
            return self._plan_interview(prompt)
        return self._build_checklist(prompt, schema)

    # ------------------------------------------------------------------
    # Interview plan
    # ------------------------------------------------------------------

    def _plan_interview(self, prompt: str) -> dict:
        """Generate interview questions from guideline coverage questions.

        Uses :func:`coach.guideline.coverage_questions` to derive
        applicability questions that are grounded in the actual guideline
        sections.  Falls back to generic procurement questions when the
        guideline has no numbered clauses (unstructured text).
        """
        from ..guideline import relevant_coverage_questions

        # Extract item description from prompt (between <item> tags or the
        # whole prompt when tags are absent) so the questions are tailored to
        # what the buyer is purchasing.
        item_match = re.search(r"<item>(.*?)</item>", prompt, re.DOTALL)
        item_desc = item_match.group(1).strip() if item_match else prompt.strip()

        questions: list[dict[str, str]] = []
        for i, (_keywords, question) in enumerate(
            relevant_coverage_questions(self._clauses, item_desc), 1
        ):
            questions.append({"key": f"cover_{i}", "question": question})

        # If no coverage questions (unstructured guideline), provide generic
        # procurement questions so the interview is never empty.
        if not questions:
            questions = [
                {"key": "q1", "question": "What is the issue date for this tender?"},
                {"key": "q2", "question": "What is the submission deadline?"},
                {
                    "key": "q3",
                    "question": "Who is issuing this tender (department/organisation)?",
                },
                {"key": "q4", "question": "What is the estimated value of this purchase?"},
                {
                    "key": "q5",
                    "question": "Does this purchase involve personal or payment data?",
                },
                {
                    "key": "q6",
                    "question": "Will this connect to internal networks or the internet?",
                },
                {
                    "key": "q7",
                    "question": (
                        "Is this hardware, software, cloud service, "
                        "or professional services?"
                    ),
                },
                {
                    "key": "q8",
                    "question": "What level of ongoing support is required?",
                },
            ]

        # Cap at 16 questions (consistent with LLM backends)
        return {"questions": questions[:16]}

    # ------------------------------------------------------------------
    # Checklist (clause selection)
    # ------------------------------------------------------------------

    def _build_checklist(self, prompt: str, schema: dict) -> dict:
        """Select clauses by keyword-matching interview answers against the guideline.

        Combines the item description and interview Q&A as a single BM25
        query, retrieves matching clauses, and returns a tender-info block
        plus an ordered list of applicable requirements.  Core sections
        (contract terms, information security, compliance/risk) are always
        included when the guideline contains them.
        """
        from ..retrieval import BM25Ranker

        # Extract the interview Q&A text from the prompt
        item_match = re.search(r"<item>(.*?)</item>", prompt, re.DOTALL)
        interview_match = re.search(r"<interview>(.*?)</interview>", prompt, re.DOTALL)

        item_desc = item_match.group(1).strip() if item_match else ""
        qa_text = interview_match.group(1).strip() if interview_match else prompt

        # Combine item description + answers as the retrieval query
        combined_query = f"{item_desc} {qa_text}"

        if not self._loaded:
            return self._empty_checklist(item_desc)

        ranker = BM25Ranker(self._index)
        results = ranker.score(combined_query, top_k=min(20, len(self._clauses)))

        # Select clauses above a relevance threshold
        requirements: list[dict[str, str]] = []
        if results:
            # Keep clauses with score >= 30% of the max score
            max_score = results[0][1] if results else 1
            threshold = max_score * 0.3

            for _doc_id, score, meta in results:
                if score < threshold:
                    continue
                ref = meta.get("ref", "")
                title = meta.get("title", "")
                if not ref:
                    continue

                # Determine M/O from the clause's requirement texts
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
                        "requirement": f"Comply with {ref} {title} requirements",
                        "mandatory": mandatory,
                    }
                )

        # Always add core sections if they exist in the guideline
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

        # Build tender_info with TBC defaults
        tender_info = self._default_tender_info(item_desc)

        # Try to extract values from the interview answers
        self._extract_tender_info(tender_info, qa_text)

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

    @staticmethod
    def _extract_tender_info(info: dict[str, str], qa_text: str) -> None:
        """Try to extract tender info values from interview Q&A text.

        Uses simple pattern matching for dates, currency amounts, and
        department names.  Mutates *info* in place; fields that cannot be
        extracted remain at their TBC default.
        """
        # Look for currency/value patterns (RM, USD, $)
        value_match = re.search(
            r"(?:RM|USD|\$)\s*[\d,]+(?:\.\d+)?", qa_text
        )
        if value_match:
            info["estimated_value"] = value_match.group(0)

        # Look for department names after "department" / "dept" keyword
        dept_match = re.search(
            r"(?:department|dept)\s*[:\-]?\s*([A-Z][A-Za-z\s]+)", qa_text
        )
        if dept_match:
            info["requesting_dept"] = dept_match.group(1).strip()

    @staticmethod
    def _empty_checklist(item_desc: str) -> dict:
        """Return an empty checklist when no guideline is loaded."""
        return {
            "tender_info": {
                "issue_date": "TBC",
                "submission_deadline": "TBC",
                "purchase_item": item_desc or "TBC",
                "issued_by": "TBC",
                "requesting_dept": "TBC",
                "tender_reference": "TBC",
                "procurement_type": "TBC",
                "estimated_value": "TBC",
                "purchase_category": "TBC",
            },
            "requirements": [],
        }


