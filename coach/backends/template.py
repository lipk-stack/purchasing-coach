"""Template / Decision-tree backend for deterministic procurement guidance.

Uses pre-authored scenario trees to guide users through purchasing decisions
and generate compliant checklists — no AI model required.  The four scenarios
(hardware, software, services, cybersecurity) cover the most common IT
procurement categories and map directly to the XXEON IT Procurement Guideline's
section structure.

Every public method is fully deterministic: given the same guideline and the
same user input, the output is identical.  This makes the template backend a
reliable fallback when no LLM server is available, and a useful test harness
for the rest of the pipeline.
"""

import re
from collections.abc import Iterator

from .base import BackendProtocol
from ..templates.scenarios import KEYWORD_INDEX, SCENARIOS

# Matches ``<item>…</item>`` and ``<interview>…</interview>`` blocks that the
# Coach embeds in the prompt for structured-output calls.
_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL)
_INTERVIEW_RE = re.compile(r"<interview>(.*?)</interview>", re.DOTALL)

# Parses ``Q: …\nA: …`` pairs out of the interview block.  The answer runs up to
# the next ``Q:`` marker or the end of the string.
_QA_PAIR_RE = re.compile(
    r"Q:\s*(.+?)\nA:\s*(.+?)(?=\nQ:|\Z)", re.DOTALL
)

# Bare clause number inside a ref string (e.g. "5.3" out of "Clause 5.3").
_REF_NUM_RE = re.compile(r"\d+(?:\.\d+)*")


def _clause_sort_key(ref: str):
    """Numeric sort key for clause references like '5.3' or '11.1'."""
    match = _REF_NUM_RE.search(ref or "")
    if not match:
        return (1, ())
    return (0, tuple(int(p) for p in match.group(0).split(".")))


class TemplateBackend(BackendProtocol):
    """Deterministic procurement guidance using decision-tree scenarios.

    The backend detects the procurement category from free-text keywords,
    presents the matching scenario's interview questions, and assembles a
    tender checklist by evaluating the scenario's conditional section rules
    against the buyer's answers.  All guidance text is pre-authored — no
    generative model is involved.
    """

    name = "template"
    model = "N/A"
    requires_model = False

    def __init__(self):
        self._clauses: dict[str, str] = {}
        self._clause_reqs: dict[str, list] = {}
        self._guideline_text: str = ""
        # Retained across calls so follow-up chat can reference the last
        # detected scenario.  Always re-detected from the prompt when
        # possible, so stale state never causes incorrect output.
        self._current_scenario: str | None = None
        self._answers: dict[str, str] = {}

    # ------------------------------------------------------------------
    # BackendProtocol — optional hooks
    # ------------------------------------------------------------------
    def load_guideline(
        self,
        guideline_text: str,
        clauses: dict[str, str],
        clause_reqs: dict[str, list],
    ) -> None:
        """Store guideline data for clause matching and citation."""
        self._clauses = clauses
        self._clause_reqs = clause_reqs
        self._guideline_text = guideline_text

    def health_check(self) -> dict:
        """Always healthy — no external dependencies."""
        return {"status": "ok", "detail": "template: ready (no model needed)"}

    # ------------------------------------------------------------------
    # BackendProtocol — required interface
    # ------------------------------------------------------------------
    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """Compose guidance from the scenario's pre-written advisory texts.

        Detects the procurement category from the last user message, then
        yields the scenario's general, security, and contract guidance along
        with citations to the applicable guideline clauses.  Text is yielded
        line-by-line to simulate streaming.
        """
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        scenario_name = self._detect_scenario(last_user_msg)
        self._current_scenario = scenario_name
        scenario = SCENARIOS[scenario_name]

        response = self._compose_chat_response(scenario_name, scenario)

        # Yield line-by-line for a natural streaming feel.
        for line in response.split("\n"):
            yield line + "\n"

    def complete_json(
        self,
        system: str,
        prompt: str,
        schema: dict,
        schema_name: str,
        max_tokens: int = 8192,
    ) -> dict:
        """Generate structured JSON using decision-tree logic.

        Supports two schema names used by the Coach orchestration layer:

        ``interview_plan``
            Detects the procurement scenario from the item description and
            returns the scenario's pre-authored interview questions.

        ``tender_checklist``
            Parses the interview answers embedded in the prompt, evaluates
            the scenario's conditional section rules, selects the applicable
            guideline clauses, and returns a complete tender checklist.
        """
        if schema_name == "interview_plan":
            return self._build_interview_plan(prompt)
        if schema_name == "tender_checklist":
            return self._build_tender_checklist(prompt)

        # Unknown schema — return a minimal valid object so the Coach doesn't
        # crash.  The two schemas above are the only ones the Coach uses.
        return {}

    # ------------------------------------------------------------------
    # Scenario detection
    # ------------------------------------------------------------------
    def _detect_scenario(self, text: str) -> str:
        """Match *text* against scenario keywords.

        Returns the scenario name with the most keyword matches, or
        ``"software"`` as the safe default (software procurement has the
        broadest overlap with generic IT purchasing).
        """
        text_lower = (text or "").lower()
        if not text_lower:
            return "software"

        scores: dict[str, int] = {}
        for keyword, scenario_name in KEYWORD_INDEX.items():
            if keyword in text_lower:
                scores[scenario_name] = scores.get(scenario_name, 0) + 1

        if not scores:
            return "software"
        return max(scores, key=lambda k: scores[k])

    # ------------------------------------------------------------------
    # Condition evaluation
    # ------------------------------------------------------------------
    def _evaluate_condition(self, condition: str, answers: dict) -> bool:
        """Evaluate a condition string against collected interview answers.

        Supported syntax::

            true                                    → always True
            key == value                            → equality check
            key != value                            → inequality check
            cond1 OR cond2                          → logical OR

        Matching is case-insensitive and tolerates substring overlap so that
        free-text answers (e.g. "We need about 300 laptops") still match
        option values like "End-user Devices" when the user's response
        contains the option text or vice versa.
        """
        condition = condition.strip()
        if condition.lower() == "true":
            return True

        # Split on ' OR ' (space-delimited to avoid matching 'OR' inside
        # option values like "Mission-critical OR Important").
        sub_conditions = re.split(r"\s+OR\s+", condition)
        for sub in sub_conditions:
            sub = sub.strip()
            if self._evaluate_simple(sub, answers):
                return True
        return False

    def _evaluate_simple(self, expr: str, answers: dict) -> bool:
        """Evaluate a single ``key == value`` or ``key != value`` expression."""
        if " == " in expr:
            key, value = expr.split(" == ", 1)
            return self._fuzzy_match(
                answers.get(key.strip(), ""), value.strip()
            )
        if " != " in expr:
            key, value = expr.split(" != ", 1)
            return not self._fuzzy_match(
                answers.get(key.strip(), ""), value.strip()
            )
        # Unrecognised expression — treat as false to be safe.
        return False

    @staticmethod
    def _fuzzy_match(answer: str, option: str) -> bool:
        """Case-insensitive match tolerating substring overlap.

        Returns ``True`` when *answer* and *option* are equal (ignoring case
        and surrounding whitespace), or when one is a substring of the other.
        This lets free-text answers like "Yes, it connects to the internal
        network" match the option "Yes - internal network" via the shared
        substring, while still rejecting clearly different values.
        """
        a = (answer or "").strip().lower()
        o = (option or "").strip().lower()
        if not a or not o:
            return False
        if a == o:
            return True
        if o in a or a in o:
            return True
        return False

    # ------------------------------------------------------------------
    # Clause selection
    # ------------------------------------------------------------------
    def _select_clauses_for_sections(
        self, section_roots: list[str]
    ) -> list[dict]:
        """Return requirement row dicts for every clause under *section_roots*.

        For each section root (e.g. ``"5"``), the method finds all guideline
        clauses whose ref starts with that root.  When the guideline has
        parsed granular requirements (``self._clause_reqs``), a single
        root-level row is returned — the Coach's ``expand_requirements``
        pass will replace it with the full set of atomic rows.  When no
        granular requirements exist (e.g. a headings-only guideline), one
        row per individual clause is returned instead.

        When no clauses have been loaded into the backend (the Coach does
        not call ``load_guideline`` on the backend), a synthetic root-level
        row is emitted for each section root.  The Coach's own
        ``reconcile_requirements`` and ``expand_requirements`` passes will
        ground these rows against the real guideline and expand them into
        granular requirement rows.

        Each dict has the keys ``ref``, ``section``, ``requirement``, and
        ``mandatory``, matching the ``CHECKLIST_SCHEMA`` in
        :mod:`coach.models`.
        """
        rows: list[dict] = []
        seen: set[str] = set()

        for root in section_roots:
            if root in seen:
                continue

            # Find every clause in the guideline that belongs to this section.
            matching = sorted(
                (
                    ref
                    for ref in self._clauses
                    if ref == root or ref.startswith(root + ".")
                ),
                key=_clause_sort_key,
            )

            if not matching:
                # No clauses loaded (or section absent from guideline).
                # Emit a synthetic root-level row; the Coach's
                # reconcile_requirements will ground it and
                # expand_requirements will replace it with granular rows
                # from the guideline body.
                seen.add(root)
                rows.append(
                    {
                        "ref": root,
                        "section": f"Section {root}",
                        "requirement": (
                            f"Applicable per guideline Section {root}"
                        ),
                        "mandatory": "M",
                    }
                )
                continue

            # Does the guideline have parsed body requirements for this
            # section?  If so, the Coach's expansion pass will replace a
            # root-level row with the granular rows — we only need to emit
            # one placeholder per root.
            has_granular = any(
                cref == root or cref.startswith(root + ".")
                for cref in self._clause_reqs
            )

            if has_granular:
                seen.add(root)
                title = self._clauses.get(root, "")
                if not title:
                    # Root heading may not exist; use the first child.
                    for ref in matching:
                        title = self._clauses[ref]
                        break
                rows.append(
                    {
                        "ref": root,
                        "section": title or f"Section {root}",
                        "requirement": (
                            f"Applicable per guideline Section {root}"
                        ),
                        "mandatory": "M",
                    }
                )
            else:
                # No granular body — emit one row per clause heading so the
                # checklist still lists every applicable requirement.
                for ref in matching:
                    if ref not in seen:
                        seen.add(ref)
                        rows.append(
                            {
                                "ref": ref,
                                "section": self._clauses[ref],
                                "requirement": (
                                    f"Required per clause {ref} of the "
                                    "guideline"
                                ),
                                "mandatory": "M",
                            }
                        )

        rows.sort(key=lambda r: _clause_sort_key(r["ref"]))
        return rows

    # ------------------------------------------------------------------
    # Prompt parsing helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_item(prompt: str) -> str:
        """Pull the item description out of a ``<item>…</item>`` block."""
        match = _ITEM_RE.search(prompt)
        return match.group(1).strip() if match else ""

    def _parse_interview(self, prompt: str) -> dict[str, str]:
        """Parse ``Q:/A:`` pairs from the prompt and map to scenario keys.

        Each question is matched against the current scenario's question list
        by case-insensitive substring comparison.  The answer is then mapped
        to the closest predefined option (or stored as-is when no option
        matches).  Returns a ``{question_key: answer_or_option}`` dict
        suitable for :meth:`_evaluate_condition`.
        """
        interview_match = _INTERVIEW_RE.search(prompt)
        if not interview_match:
            return {}

        text = interview_match.group(1).strip()
        if not text or not self._current_scenario:
            return {}

        scenario = SCENARIOS[self._current_scenario]
        answers: dict[str, str] = {}

        for question_text, answer_text in _QA_PAIR_RE.findall(text):
            question_text = question_text.strip()
            answer_text = answer_text.strip()

            # Find the scenario question that best matches this Q text.
            for sq in scenario["questions"]:
                sq_q = sq["question"].lower()
                qt_lower = question_text.lower()
                if sq_q in qt_lower or qt_lower in sq_q:
                    matched = self._match_answer(answer_text, sq["options"])
                    answers[sq["key"]] = matched or answer_text
                    break

        return answers

    @staticmethod
    def _match_answer(answer: str, options: list[str]) -> str:
        """Map a free-text answer to the closest predefined option.

        Tries exact match first, then substring overlap.  Returns the matched
        option string, or ``""`` when nothing matches.
        """
        a = answer.strip().lower()
        if not a:
            return ""
        # Exact match.
        for opt in options:
            if a == opt.strip().lower():
                return opt
        # Substring match.
        for opt in options:
            o = opt.strip().lower()
            if o in a or a in o:
                return opt
        return ""

    # ------------------------------------------------------------------
    # Structured-output builders
    # ------------------------------------------------------------------
    def _build_interview_plan(self, prompt: str) -> dict:
        """Return the scenario's pre-authored questions as an interview plan."""
        item_text = self._extract_item(prompt)
        scenario_name = self._detect_scenario(item_text)
        self._current_scenario = scenario_name
        scenario = SCENARIOS[scenario_name]

        questions = [
            {"key": q["key"], "question": q["question"]}
            for q in scenario["questions"]
        ]
        return {"questions": questions}

    def _build_tender_checklist(self, prompt: str) -> dict:
        """Assemble a complete tender checklist from the decision tree.

        1. Extracts the item description and interview answers from the
           prompt.
        2. Detects (or re-uses) the procurement scenario.
        3. Evaluates the scenario's conditional section rules against the
           collected answers to determine which guideline sections apply.
        4. Selects the matching clauses from the loaded guideline.
        5. Returns the data in ``CHECKLIST_SCHEMA`` format; the Coach's
           post-processing (reconciliation, expansion, core-section safety
           net) runs afterwards as usual.
        """
        item_text = self._extract_item(prompt)

        # Detect scenario from the item description (stateless — doesn't
        # depend on a prior plan_interview call).
        scenario_name = self._detect_scenario(item_text)
        self._current_scenario = scenario_name
        scenario = SCENARIOS[scenario_name]

        # Parse interview answers and evaluate conditions.
        answers = self._parse_interview(prompt)
        self._answers = answers

        # Collect applicable section roots.
        sections: list[str] = list(scenario["always_sections"])
        for condition, section_list in scenario["conditional_sections"].items():
            if self._evaluate_condition(condition, answers):
                for sec in section_list:
                    if sec not in sections:
                        sections.append(sec)

        # Build requirement rows from the applicable sections.
        requirement_rows = self._select_clauses_for_sections(sections)

        # Tender information — default to TBC; fill what we can from the
        # item description and the scenario name.
        tender_info = {
            "issue_date": "TBC",
            "submission_deadline": "TBC",
            "purchase_item": item_text or "TBC",
            "issued_by": "TBC",
            "requesting_dept": "TBC",
            "tender_reference": "TBC",
            "procurement_type": "TBC",
            "estimated_value": "TBC",
            "purchase_category": scenario["name"],
        }

        return {
            "tender_info": tender_info,
            "requirements": requirement_rows,
        }

    # ------------------------------------------------------------------
    # Chat response composition
    # ------------------------------------------------------------------
    def _compose_chat_response(
        self, scenario_name: str, scenario: dict
    ) -> str:
        """Build a markdown advisory response for the given scenario.

        Combines the scenario's pre-authored guidance texts with citations
        to the applicable guideline clauses drawn from the loaded guideline.
        """
        parts: list[str] = []

        # --- Header + general guidance ---
        parts.append(f"### {scenario['name']} Guidance\n")
        parts.append(scenario["guidance"]["general"])

        # --- Applicable clauses ---
        clause_refs: list[tuple[str, str]] = []
        for section in scenario["always_sections"]:
            for ref, title in self._clauses.items():
                if ref == section or ref.startswith(section + "."):
                    clause_refs.append((ref, title))
        clause_refs.sort(key=lambda pair: _clause_sort_key(pair[0]))

        if clause_refs:
            parts.append("\n**Applicable Guideline Clauses:**\n")
            for ref, title in clause_refs:
                parts.append(f"- **{ref}** — {title}")

        # --- Security ---
        parts.append("\n### Security Considerations\n")
        parts.append(scenario["guidance"]["security"])

        # --- Contract ---
        parts.append("\n### Contract Terms\n")
        parts.append(scenario["guidance"]["contract"])

        # --- Next steps ---
        parts.append(
            "\nWould you like me to prepare a tender checklist for this "
            "procurement? Just describe the item or service you're looking "
            "at and I'll walk you through the relevant questions."
        )

        return "\n".join(parts)
