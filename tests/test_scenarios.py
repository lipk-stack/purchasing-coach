"""Decision-tree scenario data + TemplateBackend section selection.

Regression coverage for the duplicate ``"true"`` dict-key bug, where a repeated
key silently dropped a whole section from a scenario (section 8 from hardware,
section 7 from software).
"""

from coach.backends.template import TemplateBackend
from coach.templates.scenarios import SCENARIOS

GUIDELINE = """\
# Guideline

## 4 CONTRACT REQUIREMENTS
### 4.1 Terms
Terms must be defined.

## 5 INFORMATION SECURITY
### 5.1 Data
Data must be protected.

## 7 SUPPORT AND MAINTENANCE
### 7.1 SLA
SLA must be defined.

## 8 HARDWARE REQUIREMENTS
### 8.1 Warranty
Warranty must be specified.

## 9 SOFTWARE REQUIREMENTS
### 9.1 Licensing
Licensing must be defined.

## 11 COMPLIANCE AND RISK
### 11.1 Audit
Audits are mandatory.

## 12 POST-IMPLEMENTATION
### 12.1 Review
Performance reviews are required.
"""


def test_hardware_scenario_always_includes_hardware_section():
    # The "true" (always-applies) condition must keep section 8; the duplicate
    # key previously overwrote it with section 12 only.
    true_sections = SCENARIOS["hardware"]["conditional_sections"]["true"]
    assert "8" in true_sections
    assert "12" in true_sections


def test_software_scenario_always_includes_support_section():
    true_sections = SCENARIOS["software"]["conditional_sections"]["true"]
    assert "7" in true_sections
    assert "12" in true_sections


def _refs_for(item: str, interview: str = "") -> set[str]:
    """Run TemplateBackend's checklist builder and return the section roots."""
    from coach.guideline import parse_clause_requirements, parse_clauses

    backend = TemplateBackend()
    backend.load_guideline(
        GUIDELINE, parse_clauses(GUIDELINE),
        parse_clause_requirements(GUIDELINE),
    )
    prompt = f"<item>{item}</item>\n<interview>\n{interview}\n</interview>"
    result = backend.complete_json("", prompt, {}, "tender_checklist")
    return {r["ref"].split(".")[0] for r in result["requirements"]}


def test_hardware_checklist_contains_hardware_section():
    roots = _refs_for("rack servers and switches")
    assert "8" in roots, f"hardware section missing from {roots}"


def test_software_checklist_contains_support_section():
    roots = _refs_for("Microsoft 365 software subscription")
    assert "7" in roots, f"support section missing from {roots}"
