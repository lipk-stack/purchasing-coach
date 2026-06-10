"""End-to-end tender flow with a fake Anthropic client (no network)."""

from contextlib import contextmanager
from types import SimpleNamespace

from openpyxl import load_workbook

from coach.llm import Coach
from coach.models import (InterviewPlan, InterviewQuestion, RequirementRow,
                          TenderChecklist, TenderInfo)
from coach.tender import run_tender_flow

PLAN = InterviewPlan(questions=[
    InterviewQuestion(key="deadline", question="When is the submission deadline?"),
    InterviewQuestion(key="dept", question="Which department is requesting this?"),
])

CHECKLIST = TenderChecklist(
    tender_info=TenderInfo(
        issue_date="2026-06-10", submission_deadline="2026-07-01",
        purchase_item="Firewall appliances", issued_by="IT Procurement",
        requesting_dept="Network", tender_reference="XXEON-IT-2026-001",
        procurement_type="Tender", estimated_value="MYR 400,000",
        purchase_category="Hardware"),
    requirements=[
        RequirementRow(ref="8.4", section="Warranty",
                       requirement="Declare End-of-Sale and End-of-Support dates.",
                       mandatory="M"),
    ],
)


class FakeMessages:
    def parse(self, **kwargs):
        model = kwargs["output_format"]
        result = PLAN if model is InterviewPlan else CHECKLIST
        return SimpleNamespace(parsed_output=result)

    @contextmanager
    def stream(self, **kwargs):
        yield SimpleNamespace(text_stream=iter(["See clause 8.4 ", "(Warranty)."]))


class FakeClient:
    messages = FakeMessages()


def make_coach():
    return Coach("guideline text", client=FakeClient())


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
    values = [row for row in tracker.iter_rows(values_only=True)]
    flat = [c for row in values for c in row if c]
    assert "Declare End-of-Sale and End-of-Support dates." in flat


def test_tender_flow_cancels_on_empty_item(tmp_path):
    coach = make_coach()
    out = run_tender_flow(coach, None, tmp_path,
                          ask=lambda prompt: "", say=lambda *a: None)
    assert out is None
