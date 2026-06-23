"""Clause indexing + checklist reconciliation (deterministic, no LLM)."""

from coach.guideline import (atomic_requirements, classify_obligation,
                            clause_sort_key, coverage_questions,
                            ensure_core_sections, expand_requirements,
                            guideline_notice, is_affirmative, normalize_ref,
                            parse_clause_requirements, parse_clauses,
                            reconcile_requirements, relevant_coverage_questions,
                            sections_from_answers, split_into_sentences)
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


def test_split_into_sentences_keeps_abbreviations_and_decimals_whole():
    # A decimal (clause number) and an abbreviation must not split a sentence.
    text = ("Vendors must support v5.6 of the platform. Edge, e.g. the latest "
            "version, must be supported.")
    assert split_into_sentences(text) == [
        "Vendors must support v5.6 of the platform.",
        "Edge, e.g. the latest version, must be supported."]


def test_atomic_requirements_splits_each_obligation_into_its_own_row():
    text = ("Both server and client components must be synchronised with the "
            "local time server. Web-based systems must support Microsoft Edge.")
    assert atomic_requirements(text) == [
        "Both server and client components must be synchronised with the "
        "local time server.",
        "Web-based systems must support Microsoft Edge."]


def test_atomic_requirements_attaches_context_to_nearest_obligation():
    # A non-normative lead-in attaches to the first obligation; trailing
    # context attaches to the obligation it follows — neither becomes its own
    # row, and a single-obligation paragraph is returned unchanged.
    lead = ("This applies to all systems. The vendor must encrypt data at "
            "rest. AES-256 is the baseline.")
    assert atomic_requirements(lead) == [
        "This applies to all systems. The vendor must encrypt data at rest. "
        "AES-256 is the baseline."]
    multi = ("This applies to all systems. The vendor must encrypt data at "
             "rest. Backups must also be encrypted. Keys are rotated yearly.")
    assert atomic_requirements(multi) == [
        "This applies to all systems. The vendor must encrypt data at rest.",
        "Backups must also be encrypted. Keys are rotated yearly."]


def test_parse_clause_requirements_splits_compound_paragraph_per_obligation():
    text = ("### 6.1 Architecture\n\nBoth server and client components must be "
            "synchronised with the local time server. Web-based systems should "
            "support Microsoft Edge.\n")
    rows = parse_clause_requirements(text)["6.1"]
    assert len(rows) == 2
    # Per-statement obligation: the "should" sentence is recommended, not
    # mandatory inherited from the "must" sibling.
    assert rows[0].mandatory == "M"
    assert rows[1].mandatory == "O"


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


HWSW_GUIDELINE = """\
# Guideline

## 5 INFORMATION SECURITY CONSIDERATIONS

### 5.1 Data Protection

Personal data must be protected.

## 6 INTEROPERABILITY

### 6.1 Integration

Systems must integrate.

## 8 HARDWARE REQUIREMENTS

### 8.4 Warranty

Warranty periods must be specified.

## 9 SOFTWARE REQUIREMENTS

### 9.1 Licensing

Licensing terms must be defined.
"""


def test_relevant_coverage_questions_tailors_to_hardware_item():
    clauses = parse_clauses(HWSW_GUIDELINE)
    questions = " ".join(
        q for _, q in relevant_coverage_questions(clauses, "20 Dell laptops")
    ).lower()
    # Hardware is asked; the software/integration item-type questions are not.
    assert "physical hardware" in questions
    assert "software or application licensing" not in questions
    assert "integrate with existing" not in questions
    # Cross-cutting topics are always asked.
    assert "personal data" in questions


def test_relevant_coverage_questions_tailors_to_software_item():
    clauses = parse_clauses(HWSW_GUIDELINE)
    questions = " ".join(
        q for _, q in
        relevant_coverage_questions(clauses, "Microsoft 365 subscription")
    ).lower()
    assert "software or application licensing" in questions
    assert "physical hardware" not in questions


def test_relevant_coverage_questions_keeps_all_for_vague_item():
    clauses = parse_clauses(HWSW_GUIDELINE)
    vague = [q for _, q in relevant_coverage_questions(clauses, "an IT solution")]
    full = [q for _, q in coverage_questions(clauses)]
    # No item-type signal -> fall back to the full, compliance-safe list.
    assert set(vague) == set(full)


def test_relevant_coverage_questions_empty_without_clauses():
    assert relevant_coverage_questions({}, "laptops") == []


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


# Financial (10) and post-implementation (12) are the only normative top-level
# sections that previously had no coverage question, so the interview did not
# cover the whole guideline. These pin the new answer-driven coverage.
FINPOST_GUIDELINE = """\
# XXEON IT Procurement Guideline

## 10 FINANCIAL CONSIDERATIONS

### 10.1 Total Cost of Ownership (TCO) Analysis

A five-year TCO analysis must be provided.

## 12 POST-IMPLEMENTATION

### 12.1 Performance Evaluation Criteria

Vendors must provide regular performance reports.
"""


def test_coverage_questions_cover_financial_and_post_implementation():
    questions = [q for _, q in coverage_questions(parse_clauses(FINPOST_GUIDELINE))]
    joined = " ".join(questions).lower()
    assert "total cost of ownership" in joined   # section 10 present
    assert "post-implementation" in joined       # section 12 present


def test_sections_from_answers_includes_financial_and_post_implementation():
    clauses = parse_clauses(FINPOST_GUIDELINE)
    questions = dict(coverage_questions(clauses)).values()
    # The merged coverage questions, answered affirmatively, pull in 10 and 12.
    answers = [(q, "Yes") for q in questions]
    assert sections_from_answers(answers, clauses) == ["10", "12"]
    # Declining both keeps them out of the checklist.
    declined = [(q, "No") for q in questions]
    assert sections_from_answers(declined, clauses) == []


# Section 13 (the SBOM declaration) is a granular vendor obligation referenced
# from core section 4.3, but it lives in the "Appendix" — a weak model rarely
# cites it and it is not a CORE_SECTION, so without an answer-driven hook it
# silently dropped out of the checklist. These pin the SBOM coverage.
SBOM_GUIDELINE = """\
# XXEON IT Procurement Guideline

## 9 SOFTWARE REQUIREMENTS

### 9.1 Licensing

Licensing terms must be defined.

## 13 APPENDIX

### 13.1 Software Bill of Materials (SBOM) Template

Vendors are required to complete and submit the SBOM template. The SBOM must
enumerate all software libraries, frameworks, dependencies and third-party
components. Each entry must specify the component name, version and licence.
"""


def test_coverage_asks_for_sbom_when_section_present():
    clauses = parse_clauses(SBOM_GUIDELINE)
    joined = " ".join(q for _, q in coverage_questions(clauses)).lower()
    assert "software bill of materials" in joined
    # A software item keeps the SBOM question; a pure-hardware item drops it.
    sw = " ".join(
        q for _, q in relevant_coverage_questions(clauses, "ERP software suite")
    ).lower()
    assert "software bill of materials" in sw


def test_sections_from_answers_includes_sbom_when_affirmed():
    clauses = parse_clauses(SBOM_GUIDELINE)
    question = dict(coverage_questions(clauses))[
        "sbom,bill of materials,software component,third-party,"
        "dependencies,libraries"
    ]
    assert "13" in sections_from_answers([(question, "Yes")], clauses)
    # Declining keeps the appendix out.
    assert "13" not in sections_from_answers([(question, "No")], clauses)


def test_guideline_notice_flags_unstructured_document():
    # A structured guideline produces no notice; an unstructured one warns the
    # user (so an empty checklist is never a silent failure).
    assert guideline_notice(parse_clauses(GUIDELINE)) is None
    notice = guideline_notice(parse_clauses("Just some prose with no numbers."))
    assert notice and "numbered" in notice.lower()
