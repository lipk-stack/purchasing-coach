"""The Coach: prompts + parsing on top of a pluggable LLM backend."""

from collections.abc import Iterator

from .guideline import (CORE_SECTIONS, ensure_core_sections,
                       expand_requirements, parse_clauses,
                       parse_clause_requirements, reconcile_requirements,
                       relevant_coverage_questions, sections_from_answers)
from .models import (CHECKLIST_SCHEMA, INTERVIEW_SCHEMA, InterviewPlan,
                     InterviewQuestion, TenderChecklist)

SYSTEM_TEMPLATE = """\
You are Purchasing Coach, an assistant for procurement officers. You answer
questions strictly based on the organisation's purchasing guideline below and
help prepare tender documents that comply with it.

Rules:
- Ground every answer in the guideline, and CITE the guideline's own section /
  clause number next to each point you rely on (e.g. "4.1", "5.6"). Put the
  reference first and in bold, e.g. "- **4.1** — the vendor bears stamp duty".
  Use the numbering exactly as it appears in this guideline.
- If the guideline does not cover a question, say so explicitly instead of
  inventing policy.
- Be concise and practical; the user is preparing a real purchase.
- Structure replies so they can be scanned quickly. Lead with a one-sentence
  answer, then details. Use markdown lists when several requirements or steps
  apply — "- " bullets, or "1. " numbers when order or count matters — one
  item each, the guideline reference first in **bold** (e.g. "- **5.6** —
  annual SOC 2 Type II report"). When a section has several sub-points, use
  NESTED numbering: number the parent items 1., 2., 3. and indent each
  sub-point by two spaces as 1., 2., … so the reply mirrors the guideline's
  hierarchy (e.g. section 4 and its clauses 4.1, 4.2). Use **bold** for
  section/clause numbers and key terms, and a short "### " heading only when an
  answer covers multiple distinct topics. Keep paragraphs to three lines or
  fewer; never answer with one long paragraph.
- Give the answer once. Do not restate the same content a second time in a
  different format (e.g. a bulleted list and then the same points again as
  headed paragraphs) — pick one structure and stop.

<guideline>
{guideline}
</guideline>"""


class Coach:
    # Hard cap on interview length once the model questions and the
    # guideline-coverage questions are merged.
    MAX_QUESTIONS = 16

    def __init__(self, guideline_text: str, backend):
        self.backend = backend
        self.guideline_text = guideline_text
        self.system = SYSTEM_TEMPLATE.format(guideline=guideline_text)
        self.clauses = parse_clauses(guideline_text)
        self.clause_reqs = parse_clause_requirements(guideline_text)
        # Pre-load the guideline into the backend's retrieval index.
        # LLM backends ignore this (they get the guideline via the system
        # prompt); retrieval-based backends build their index here.
        # Use hasattr to stay compatible with minimal test fakes.
        if hasattr(backend, "load_guideline"):
            backend.load_guideline(guideline_text, self.clauses, self.clause_reqs)

    # ---- chat -----------------------------------------------------------
    def answer(self, history: list[dict]) -> Iterator[str]:
        """Stream the assistant's reply for the given message history."""
        yield from self.backend.stream_chat(self.system, history)

    # ---- tender interview -------------------------------------------------
    def plan_interview(self, item_description: str) -> InterviewPlan:
        """Ask the model which questions to ask about the purchase."""
        prompt = (
            "A user wants to purchase the following item and needs a tender "
            f"checklist:\n\n<item>{item_description}</item>\n\n"
            "Based on the guideline, list the interview questions needed to "
            "(a) fill in the tender information sheet (issue date, submission "
            "deadline, issued by, requesting department, tender reference, "
            "procurement type, estimated value, purchase category) and "
            "(b) determine which guideline requirements apply to this item "
            "(e.g. is it hardware, software, cloud/SaaS, or services; does it "
            "handle personal or payment data; is it internet-facing; does it "
            "involve cybersecurity assessments; deployment model; etc.). "
            "Ask only what is relevant to this item. Keep it to at most 12 "
            "questions, each answerable in a short free-text reply."
        )
        data = self.backend.complete_json(self.system, prompt,
                                          INTERVIEW_SCHEMA, "interview_plan")
        plan = InterviewPlan.from_dict(data)
        return self._ensure_coverage(plan, item_description)

    def _ensure_coverage(self, plan: InterviewPlan,
                         item_description: str = "") -> InterviewPlan:
        """Add guideline-grounded applicability questions the model didn't ask.

        Reverse-prompting must surface enough about the purchase to decide
        which guideline sections apply, so every relevant requirement ends up
        in the checklist. We merge in the coverage questions relevant to this
        item for any major section the model's questions don't already touch,
        capped at ``MAX_QUESTIONS``.
        """
        questions = list(plan.questions)
        asked = " ".join(q.question.lower() for q in questions)
        for i, (keywords, question) in enumerate(
                relevant_coverage_questions(self.clauses, item_description),
                start=1):
            if len(questions) >= self.MAX_QUESTIONS:
                break
            if any(kw in asked for kw in keywords.split(",")):
                continue
            questions.append(InterviewQuestion(key=f"cover_{i}",
                                               question=question))
            asked += " " + question.lower()
        return InterviewPlan(questions=questions)

    def build_checklist(self, item_description: str,
                        answers: list[tuple[str, str]]) -> TenderChecklist:
        """Turn the interview answers into tender info + requirement rows."""
        qa_text = "\n".join(f"Q: {q}\nA: {a}" for q, a in answers)
        prompt = (
            "Produce the tender checklist for this purchase.\n\n"
            f"<item>{item_description}</item>\n\n"
            f"<interview>\n{qa_text}\n</interview>\n\n"
            "Instructions:\n"
            "1. tender_info: fill every field from the interview answers; use "
            "'TBC' where the user did not provide a value. Suggest a sensible "
            "tender_reference if none was given.\n"
            "2. requirements: select EVERY guideline clause that applies to "
            "this purchase, given the item type and the interview answers. "
            "Be comprehensive — it is better to include a borderline clause "
            "than to miss one; the detailed vendor requirements for each "
            "clause are expanded automatically from the guideline text, so "
            "your job is to pick the right clauses, not to summarise them. "
            "Include one row per applicable clause. You may cite a whole "
            "section number (e.g. '5') to include all of its sub-clauses. "
            "Skip only sections that clearly do not apply (e.g. hardware "
            "sections for a pure SaaS subscription). For each row set ref to "
            "the guideline clause number, section to the clause title, "
            "requirement to a short note on why it applies, and mandatory to "
            "'M' or 'O'.\n"
            "Order rows by clause number."
        )
        data = self.backend.complete_json(self.system, prompt,
                                          CHECKLIST_SCHEMA, "tender_checklist",
                                          max_tokens=16000)
        checklist = TenderChecklist.from_dict(data)
        checklist.requirements, checklist.unverified_refs = \
            reconcile_requirements(checklist.requirements, self.clauses)
        # Expand each selected clause into the granular, guideline-verbatim
        # requirements the vendor must fulfil, so the tracker is detailed
        # rather than one paraphrased line per clause.
        checklist.requirements = expand_requirements(
            checklist.requirements, self.clause_reqs)
        # Safety net: always include the cross-cutting compliance sections, plus
        # any item-specific section the buyer's interview answers say applies
        # (e.g. hardware → 8), so an under-selecting model can't drop a section
        # the user told us is relevant.
        sections = tuple(dict.fromkeys(
            CORE_SECTIONS + tuple(sections_from_answers(answers, self.clauses))))
        checklist.requirements, checklist.added_core_sections = \
            ensure_core_sections(checklist.requirements, self.clause_reqs,
                                 sections)
        return checklist
