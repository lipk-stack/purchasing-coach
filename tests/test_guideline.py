"""Clause indexing + checklist reconciliation (deterministic, no LLM)."""

from coach.guideline import (clause_sort_key, normalize_ref, parse_clauses,
                            reconcile_requirements)
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

Body text.
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
