"""The Coach: prompts + parsing on top of a pluggable LLM backend."""

from collections.abc import Iterator

from .models import (CHECKLIST_SCHEMA, INTERVIEW_SCHEMA, InterviewPlan,
                     TenderChecklist)

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

<guideline>
{guideline}
</guideline>"""


class Coach:
    def __init__(self, guideline_text: str, backend):
        self.backend = backend
        self.system = SYSTEM_TEMPLATE.format(guideline=guideline_text)

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
        return InterviewPlan.from_dict(data)

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
            "2. requirements: go through the guideline section by section and "
            "include every requirement that applies to this purchase, given "
            "the item type and the interview answers. Skip sections that "
            "clearly do not apply (e.g. hardware sections for a SaaS "
            "purchase). For each row set ref to the guideline clause number, "
            "section to the clause title, requirement to a concise vendor-"
            "facing statement, and mandatory to 'M' when the guideline says "
            "must/shall/mandatory or 'O' when it says should/recommended.\n"
            "Order rows by clause number."
        )
        data = self.backend.complete_json(self.system, prompt,
                                          CHECKLIST_SCHEMA, "tender_checklist",
                                          max_tokens=16000)
        return TenderChecklist.from_dict(data)
