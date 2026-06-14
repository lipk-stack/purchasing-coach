"""Clause indexing + checklist reconciliation (deterministic, no LLM)."""

from coach.guideline import (classify_obligation, clause_sort_key,
                            coverage_questions, ensure_core_sections,
                            expand_requirements, is_affirmative, normalize_ref,
                            parse_clause_requirements, parse_clauses,
                            reconcile_requirements, sections_from_answers)
from coach.models import RequirementRow

GUIDELINE = """\
# XXEON IT Procurement Guideline

## 5 INFORMATION SECURITY CONSIDERATIONS

### 5.6 Audits and Assessments

Annual third-party security audits are mandatory.

## 8 HARDWARE REQUIREMENTS

### 8.4 Warranty and Replacement Policies

Minimum warranty periods must be specified.

### 8.10 Imaginary Later Clause

Spare parts must be available.
"""


def test_parse_clauses_maps_ref_to_heading_title():
    clauses = parse_clauses(GUIDELINE)
    assert clauses["5.6"] == "Audits and Assessments"
    assert clauses["8.4"] == "Warranty and Replacement Policies"
    assert clauses["5"] == "INFORMATION SECURITY CONSIDERATIONS"


def test_parse_clauses_empty_for_unstructured_text():
    assert parse_clauses("just some prose with no headings") == {}


def test_normalize_ref_strips_prefixes():
    assert normalize_ref("Clause 5.3") == "5.3"
    assert normalize_ref("Section 5.6.") == "5.6"
    assert normalize_ref("5.3") == "5.3"


def test_clause_sort_key_is_numeric():
    refs = ["8.10", "5.6", "8.4", "11.1", "5"]
    assert sorted(refs, key=clause_sort_key) == ["5", "5.6", "8.4", "8.10", "11.1"]


def test_reconcile_canonicalises_titles_orders_and_flags():
    clauses = parse_clauses(GUIDELINE)
    rows = [
        RequirementRow("8.4", "Warranties (model paraphrase)",
                       "Declare EoS/EoSL dates.", "M"),
        RequirementRow("Clause 5.6", "Audit stuff",
                       "Supply annual SOC 2 Type II report.", "M"),
        RequirementRow("99.9", "Made up", "Hallucinated requirement.", "O"),
    ]
    cleaned, unverified = reconcile_requirements(rows, clauses)

    # Ordered by clause number, titles replaced with the real headings.
    assert [r.ref for r in cleaned] == ["5.6", "8.4", "99.9"]
    assert cleaned[0].section == "Audits and Assessments"
    assert cleaned[1].section == "Warranty and Replacement Policies"
    # Unknown clause kept (not silently dropped) but reported.
    assert unverified == ["99.9"]
    assert cleaned[2].section == "Made up"


def test_reconcile_dedupes_identical_rows():
    clauses = parse_clauses(GUIDELINE)
    rows = [
        RequirementRow("5.6", "x", "Supply annual SOC 2 report.", "M"),
        RequirementRow("Clause 5.6", "y", "supply annual soc 2 report.", "M"),
    ]
    cleaned, _ = reconcile_requirements(rows, clauses)
    assert len(cleaned) == 1


def test_reconcile_noop_without_clause_index():
    rows = [RequirementRow("8.4", "Warranty", "Declare dates.", "M")]
    cleaned, unverified = reconcile_requirements(rows, {})
    assert cleaned == rows
    assert unverified == []


# ---- granular requirement extraction ------------------------------------

def test_classify_obligation_strong_weak_default():
    assert classify_obligation("Vendors must supply a report.") == "M"
    assert classify_obligation("A TCO analysis should be provided.") == "O"
    # 'must' wins even when a weak word also appears.
    assert classify_obligation("A one-way NDA is recommended but must "
                               "be in place.") == "M"
    # Normative statement without an explicit cue defaults to mandatory.
    assert classify_obligation("Vendors are required to comply.") == "M"


def test_parse_clause_requirements_splits_body_into_rows():
    reqs = parse_clause_requirements(GUIDELINE)
    # Each normative body paragraph becomes its own row with the real title.
    assert [r.requirement for r in reqs["5.6"]] == [
        "Annual third-party security audits are mandatory."]
    assert reqs["8.4"][0].section == "Warranty and Replacement Policies"
    assert reqs["8.4"][0].mandatory == "M"
    # Headings with no normative body get an empty list, not a bogus row.
    assert reqs["5"] == []


def test_parse_clause_requirements_skips_non_normative_prose():
    text = ("### 3.1 Purpose\n\nThis document describes the framework.\n\n"
            "### 4.1 Terms\n\nThe vendor must define deliverables.\n")
    reqs = parse_clause_requirements(text)
    assert reqs["3.1"] == []  # descriptive prose is not a requirement
    assert len(reqs["4.1"]) == 1


def test_expand_requirements_fans_out_section_to_subclauses():
    clause_reqs = parse_clause_requirements(GUIDELINE)
    # Model selected the whole of section 8 with one row.
    rows = [RequirementRow("8", "Hardware", "Hardware applies.", "M")]
    expanded = expand_requirements(rows, clause_reqs)
    refs = [r.ref for r in expanded]
    assert refs == ["8.4", "8.10"]
    assert expanded[0].requirement == "Minimum warranty periods must be " \
        "specified."


def test_expand_requirements_keeps_unparsed_rows():
    # A clause the guideline has no parsed body for keeps the model's row.
    clause_reqs = parse_clause_requirements(GUIDELINE)
    rows = [RequirementRow("99.9", "Made up", "Not in the guideline.", "O")]
    expanded = expand_requirements(rows, clause_reqs)
    assert [r.requirement for r in expanded] == ["Not in the guideline."]


def test_expand_requirements_noop_without_body():
    rows = [RequirementRow("8.4", "Warranty", "Declare dates.", "M")]
    assert expand_requirements(rows, {}) == rows


# ---- core-section safety net ---------------------------------------------

CORE_GUIDELINE = """\
## 4 CONTRACT REQUIREMENTS

### 4.1 Standard Contract Terms

The vendor must define deliverables.

## 5 INFORMATION SECURITY CONSIDERATIONS

### 5.6 Audits and Assessments

Annual third-party security audits are mandatory.

## 8 HARDWARE REQUIREMENTS

### 8.4 Warranty and Replacement Policies

Minimum warranty periods must be specified.

## 11 COMPLIANCE AND RISK MANAGEMENT

### 11.1 Regulatory Compliance

The vendor must comply with applicable regulations.
"""


def test_ensure_core_sections_adds_missing_cross_cutting_clauses():
    clause_reqs = parse_clause_requirements(CORE_GUIDELINE)
    # Model only selected a hardware clause and missed every core section.
    rows = [RequirementRow("8.4", "Warranty and Replacement Policies",
                           "Minimum warranty periods must be specified.", "M")]
    merged, added = ensure_core_sections(rows, clause_reqs)
    refs = [r.ref for r in merged]
    # Core sections 4, 5, 11 are folded in, in guideline order, hardware kept.
    assert refs == ["4.1", "5.6", "8.4", "11.1"]
    assert added == ["4", "5", "11"]


def test_ensure_core_sections_no_duplicates_when_already_present():
    clause_reqs = parse_clause_requirements(CORE_GUIDELINE)
    rows = [
        RequirementRow("4.1", "Standard Contract Terms",
                       "The vendor must define deliverables.", "M"),
        RequirementRow("5.6", "Audits and Assessments",
                       "Annual third-party security audits are mandatory.", "M"),
        RequirementRow("11.1", "Regulatory Compliance",
                       "The vendor must comply with applicable regulations.",
                       "M"),
    ]
    merged, added = ensure_core_sections(rows, clause_reqs)
    assert [r.ref for r in merged] == ["4.1", "5.6", "11.1"]
    assert added == []  # nothing had to be added


def test_ensure_core_sections_noop_without_body():
    rows = [RequirementRow("8.4", "Warranty", "Declare dates.", "M")]
    merged, added = ensure_core_sections(rows, {})
    assert merged == rows
    assert added == []


def test_coverage_questions_gated_on_present_sections():
    clauses = parse_clauses(GUIDELINE)  # has sections 5 and 8 only
    questions = [q for _, q in coverage_questions(clauses)]
    joined = " ".join(questions).lower()
    assert "hardware" in joined          # section 8 present
    assert "personal data" in joined     # section 5 present
    assert "support and maintenance" not in joined  # section 7 absent
    # Unstructured guideline grounds no coverage questions.
    assert coverage_questions({}) == []


def test_is_affirmative_reads_yes_no_and_substantive_answers():
    # Explicit and substantive answers count as "applies".
    assert is_affirmative("Yes")
    assert is_affirmative("10 servers and 5 laptops")
    assert is_affirmative("24/7 for three years")
    assert is_affirmative("No on-prem servers but yes to the appliance")
    # Clear negatives and blanks do not.
    assert not is_affirmative("No")
    assert not is_affirmative("None")
    assert not is_affirmative("Not applicable")
    assert not is_affirmative("n/a")
    assert not is_affirmative("")
    assert not is_affirmative("No, this is a pure SaaS subscription")


def test_sections_from_answers_includes_sections_buyer_affirms():
    clauses = parse_clauses(GUIDELINE)  # has sections 5 and 8 only
    answers = [
        ("Does this purchase include physical hardware or equipment?",
         "Yes, 10 rack servers"),
        ("Will the solution store personal data?", "No"),
    ]
    # Hardware (8) is affirmed and present in the guideline; section 9 is not in
    # the guideline so even an affirmative answer can't pull it in.
    assert sections_from_answers(answers, clauses) == ["8"]


def test_sections_from_answers_prunes_negative_and_unstructured():
    clauses = parse_clauses(GUIDELINE)
    answers = [("Does this purchase include physical hardware?",
                "No, software only")]
    assert sections_from_answers(answers, clauses) == []
    # Unstructured guideline grounds nothing.
    assert sections_from_answers(answers, {}) == []
