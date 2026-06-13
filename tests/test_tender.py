"""End-to-end tender flow with a fake LLM backend (no network)."""

from openpyxl import load_workbook

from coach.llm import Coach
from coach.tender import run_tender_flow

PLAN = {
    "questions": [
        {"key": "deadline", "question": "When is the submission deadline?"},
        {"key": "dept", "question": "Which department is requesting this?"},
    ]
}

CHECKLIST = {
    "tender_info": {
        "issue_date": "2026-06-10", "submission_deadline": "2026-07-01",
        "purchase_item": "Firewall appliances", "issued_by": "IT Procurement",
        "requesting_dept": "Network", "tender_reference": "XXEON-IT-2026-001",
        "procurement_type": "Tender", "estimated_value": "MYR 400,000",
        "purchase_category": "Hardware",
    },
    "requirements": [
        # Out of order, with a paraphrased section and a hallucinated clause,
        # so the reconciliation path is exercised end to end.
        {"ref": "8.4", "section": "Warranty (paraphrased)",
         "requirement": "Declare End-of-Sale and End-of-Support dates.",
         "mandatory": "M"},
        {"ref": "5.6", "section": "Audits",
         "requirement": "Supply an annual SOC 2 Type II report.",
         "mandatory": "M"},
        {"ref": "99.9", "section": "Imaginary",
         "requirement": "A requirement that is not in the guideline.",
         "mandatory": "O"},
    ],
}

GUIDELINE = """\
## 5 INFORMATION SECURITY CONSIDERATIONS

### 5.6 Audits and Assessments

## 8 HARDWARE REQUIREMENTS

### 8.4 Warranty and Replacement Policies
"""


class FakeBackend:
    name = "fake"
    model = "fake-model"

    def stream_chat(self, system, messages, max_tokens=4096):
        assert "guideline" in system
        yield from ["See clause 8.4 ", "(Warranty)."]

    def complete_json(self, system, prompt, schema, schema_name,
                      max_tokens=8192):
        return PLAN if schema_name == "interview_plan" else CHECKLIST


def make_coach():
    return Coach(GUIDELINE, FakeBackend())


def test_chat_answer_streams():
    coach = make_coach()
    reply = "".join(coach.answer([{"role": "user", "content": "warranty?"}]))
    assert reply == "See clause 8.4 (Warranty)."


def test_tender_flow_writes_workbook(tmp_path):
    coach = make_coach()
    scripted = iter(["Firewall appliances for the data centre",
                     "1 July 2026", "Network team"])
    out = run_tender_flow(coach, template_path=None, out_dir=tmp_path,
                          ask=lambda prompt: next(scripted), say=lambda *a: None)
    assert out is not None and out.exists()

    wb = load_workbook(out)
    tracker = wb["Compliance Tracker"]
    flat = [c for row in tracker.iter_rows(values_only=True) for c in row if c]
    assert "Declare End-of-Sale and End-of-Support dates." in flat
    # Section titles are canonicalised to the real guideline headings.
    assert "Warranty and Replacement Policies" in flat
    assert "Audits and Assessments" in flat


def test_tender_flow_reconciles_against_guideline(tmp_path):
    coach = make_coach()
    scripted = iter(["Firewall appliances", "1 July 2026", "Network team"])
    notes: list[str] = []
    out = run_tender_flow(coach, None, tmp_path,
                          ask=lambda prompt: next(scripted),
                          say=lambda *a: notes.append(" ".join(map(str, a))))
    wb = load_workbook(out)
    tracker = wb["Compliance Tracker"]
    refs = [row[1] for row in tracker.iter_rows(min_row=4, values_only=True)
            if row[1]]
    # Rows are reordered into guideline order (5.6 before 8.4 before 99.9).
    assert refs == ["5.6", "8.4", "99.9"]
    # The hallucinated clause is flagged for the user.
    assert any("99.9" in n and "could not be matched" in n for n in notes)


def test_tender_flow_cancels_on_empty_item(tmp_path):
    coach = make_coach()
    out = run_tender_flow(coach, None, tmp_path,
                          ask=lambda prompt: "", say=lambda *a: None)
    assert out is None
