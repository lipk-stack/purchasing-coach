"""The Coach: prompts + parsing on top of a pluggable LLM backend."""

from collections.abc import Iterator

from .guideline import (coverage_questions, expand_requirements, parse_clauses,
                       parse_clause_requirements, reconcile_requirements)
from .models import (CHECKLIST_SCHEMA, INTERVIEW_SCHEMA, InterviewPlan,
                     InterviewQuestion, TenderChecklist)

SYSTEM_TEMPLATE = """\
You are Purchasing Coach, an assistant for procurement officers. You answer
questions strictly based on the organisation's purchasing guideline below and
help prepare tender documents that comply with it.

Rules:
- Ground every answer in the guideline. Cite the clause numbers (e.g. "5.3")
  you relied on.
- If the guideline does not cover a question, say so explicitly instead of
  inventing policy.
- Be concise and practical; the user is preparing a real purchase.
- Structure replies so they can be scanned quickly. Lead with a one-sentence
  answer, then details. Use markdown: "- " bullet lists when several
  requirements or steps apply (one per bullet, clause reference first, e.g.
  "- **5.6** — annual SOC 2 Type II report"), **bold** for clause numbers
  and key terms, and a short "### " heading only when an answer covers
  multiple distinct topics. Keep paragraphs to three lines or fewer; never
  answer with one long paragraph.

<guideline>
{guideline}
</guideline>"""


class Coach:
    # Hard cap on interview length once the model questions and the
    # guideline-coverage questions are merged.
    MAX_QUESTIONS = 16

    def __init__(self, guideline_text: str, backend):
        self.backend = backend
        self.system = SYSTEM_TEMPLATE.format(guideline=guideline_text)
        self.clauses = parse_clauses(guideline_text)
        self.clause_reqs = parse_clause_requirements(guideline_text)

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
        return self._ensure_coverage(plan)

    def _ensure_coverage(self, plan: InterviewPlan) -> InterviewPlan:
        """Add guideline-grounded applicability questions the model didn't ask.

        Reverse-prompting must surface enough about the purchase to decide
        which guideline sections apply, so every relevant requirement ends up
        in the checklist. We merge in coverage questions for any major section
        the model's questions don't already touch, capped at ``MAX_QUESTIONS``.
        """
        questions = list(plan.questions)
        asked = " ".join(q.question.lower() for q in questions)
        for i, (keywords, question) in enumerate(
                coverage_questions(self.clauses), start=1):
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
        return checklist
