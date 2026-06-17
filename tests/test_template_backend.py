"""TemplateBackend: scenario detection, condition eval, clause selection, chat."""

from coach.backends.template import TemplateBackend
from coach.guideline import parse_clause_requirements, parse_clauses

GUIDELINE = """\
# Guideline

## 4 CONTRACT REQUIREMENTS
### 4.1 Terms
Terms must be defined.

## 5 INFORMATION SECURITY
### 5.1 Data Protection
Personal data must be protected.

## 8 HARDWARE REQUIREMENTS
### 8.1 Warranty
Warranty must be specified.
"""


def _backend(with_reqs=True):
    be = TemplateBackend()
    clauses = parse_clauses(GUIDELINE)
    reqs = parse_clause_requirements(GUIDELINE) if with_reqs else {}
    be.load_guideline(GUIDELINE, clauses, reqs)
    return be


# --------------------------- scenario detection ----------------------------
def test_detect_scenario_by_keywords():
    be = TemplateBackend()
    assert be._detect_scenario("rack servers and switches") == "hardware"
    assert be._detect_scenario("annual penetration test") == "cybersecurity"
    assert be._detect_scenario("software licensing subscription") == "software"


def test_detect_scenario_defaults_to_software():
    be = TemplateBackend()
    assert be._detect_scenario("") == "software"
    assert be._detect_scenario("something with no keywords zzz") == "software"


# --------------------------- condition evaluation --------------------------
def test_evaluate_condition_true():
    be = TemplateBackend()
    assert be._evaluate_condition("true", {}) is True


def test_evaluate_condition_equality_and_inequality():
    be = TemplateBackend()
    answers = {"hw_network": "Yes - internal network"}
    assert be._evaluate_condition("hw_network == Yes - internal network", answers)
    assert be._evaluate_condition("hw_network != Standalone", answers)
    assert not be._evaluate_condition("hw_network == Standalone", answers)


def test_evaluate_condition_or():
    be = TemplateBackend()
    answers = {"sw_type": "Cloud/SaaS"}
    assert be._evaluate_condition(
        "sw_type == On-premise OR sw_type == Cloud/SaaS", answers)


def test_fuzzy_match_substring():
    assert TemplateBackend._fuzzy_match("Yes, internal network only", "internal")
    assert not TemplateBackend._fuzzy_match("", "internal")


# --------------------------- interview + checklist -------------------------
def test_interview_plan_returns_scenario_questions():
    be = _backend()
    plan = be.complete_json("", "<item>laptops</item>", {}, "interview_plan")
    assert plan["questions"]
    assert all("key" in q and "question" in q for q in plan["questions"])


def test_checklist_includes_always_and_conditional_sections():
    be = _backend()
    prompt = "<item>rack servers</item>\n<interview>\n\n</interview>"
    result = be.complete_json("", prompt, {}, "tender_checklist")
    roots = {r["ref"].split(".")[0] for r in result["requirements"]}
    # always_sections 4 & 5 plus the always-true hardware section 8.
    assert {"4", "5", "8"} <= roots


def test_checklist_headings_only_guideline_one_row_per_clause():
    be = _backend(with_reqs=False)  # clauses present, no parsed bodies
    prompt = "<item>rack servers</item>\n<interview>\n\n</interview>"
    result = be.complete_json("", prompt, {}, "tender_checklist")
    refs = {r["ref"] for r in result["requirements"]}
    # Sub-clause headings appear individually when there are no granular bodies.
    assert "8.1" in refs


def test_checklist_without_loaded_guideline_emits_synthetic_roots():
    be = TemplateBackend()  # no load_guideline -> no clauses
    prompt = "<item>rack servers</item>\n<interview>\n\n</interview>"
    result = be.complete_json("", prompt, {}, "tender_checklist")
    assert result["requirements"]
    # Synthetic root-level rows that the Coach later grounds/expands.
    assert any(r["ref"] == "8" for r in result["requirements"])


def test_unknown_schema_returns_empty():
    assert TemplateBackend().complete_json("", "", {}, "mystery") == {}


# --------------------------- chat composition ------------------------------
def test_stream_chat_mentions_scenario_and_clauses():
    be = _backend()
    out = "".join(be.stream_chat(
        "", [{"role": "user", "content": "buying servers"}]))
    assert "Hardware Procurement" in out
    assert "Guideline Clauses" in out  # cites applicable clauses


def test_health_check_ok():
    assert TemplateBackend().health_check()["status"] == "ok"
