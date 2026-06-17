"""Dataclass models: from_dict robustness + session/analytics paths."""

import pytest

from coach.models import (
    AnalyticsSnapshot,
    ChatMessage,
    InterviewPlan,
    RequirementRow,
    Session,
    TenderChecklist,
    TenderInfo,
)


# --------------------------- robustness guards -----------------------------
def test_interview_plan_string_questions_does_not_iterate_chars():
    # A string for "questions" must not become one question per character.
    with pytest.raises(ValueError, match="no interview questions"):
        InterviewPlan.from_dict({"questions": "hello"})


def test_interview_plan_non_dict_input():
    with pytest.raises(ValueError):
        InterviewPlan.from_dict("not a dict")


def test_interview_plan_mixed_items():
    plan = InterviewPlan.from_dict({"questions": [
        "bare string question",
        {"key": "k2", "question": "dict question"},
        {"no_question": "ignored"},
        12345,
    ]})
    assert [q.question for q in plan.questions] == [
        "bare string question", "dict question"]


def test_tender_checklist_string_requirements_is_empty():
    cl = TenderChecklist.from_dict({"requirements": "oops", "tender_info": {}})
    assert cl.requirements == []


def test_tender_checklist_non_dict_input():
    cl = TenderChecklist.from_dict(None)
    assert cl.requirements == []
    assert cl.tender_info.purchase_item == "TBC"


def test_requirement_row_mandatory_normalisation():
    assert RequirementRow.from_dict({"requirement": "x"}).mandatory == "M"
    assert RequirementRow.from_dict(
        {"requirement": "x", "mandatory": "Optional"}).mandatory == "O"
    assert RequirementRow.from_dict(
        {"requirement": "x", "mandatory": "weird"}).mandatory == "M"


def test_tender_info_defaults_to_tbc():
    info = TenderInfo.from_dict({"purchase_item": "Laptops"})
    assert info.purchase_item == "Laptops"
    assert info.issue_date == "TBC"


# --------------------------- session round-trip ----------------------------
def test_session_round_trip():
    s = Session(
        id="abc", title="T",
        messages=[ChatMessage(role="user", content="hi", reactions=["👍"])],
        backend="keyword",
    )
    restored = Session.from_dict(s.to_dict())
    assert restored.id == "abc"
    assert restored.messages[0].content == "hi"
    assert restored.messages[0].reactions == ["👍"]


def test_chat_message_string_reactions_ignored():
    m = ChatMessage.from_dict({"role": "user", "content": "x",
                               "reactions": "not-a-list"})
    assert m.reactions == []


def test_session_string_messages_ignored():
    s = Session.from_dict({"id": "x", "messages": "nope"})
    assert s.messages == []


# --------------------------- analytics -------------------------------------
def test_analytics_snapshot_counts_and_heatmap():
    rows = [
        RequirementRow("5.1", "Security", "MFA", "M"),
        RequirementRow("5.2", "Security", "RBAC", "M"),
        RequirementRow("8.4", "Hardware", "Warranty", "O"),
    ]
    snap = AnalyticsSnapshot.from_checklist(rows, total_clauses=10)
    assert snap.total_requirements == 3
    assert snap.mandatory_count == 2
    assert snap.optional_count == 1
    assert snap.by_section["Security"] == 2
    # Two distinct section roots (5, 8) over 10 clauses -> 20% coverage.
    assert snap.coverage_pct == 20.0
    # Heatmap is normalised to the busiest section.
    assert snap.section_heatmap["Security"] == 1.0


def test_analytics_snapshot_empty():
    snap = AnalyticsSnapshot.from_checklist([])
    assert snap.total_requirements == 0
    assert snap.coverage_pct == 0.0
    assert snap.section_heatmap == {}
