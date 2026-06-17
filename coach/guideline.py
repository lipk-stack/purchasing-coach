"""Index the guideline's numbered clauses and reconcile model output to it.

Small local models routinely paraphrase a clause title or cite a clause
number that does not exist. The checklist is the deliverable, so before it is
written we ground every requirement row against the actual guideline:

- the ``section`` column is replaced with the real heading text for that
  clause (so the workbook is consistent with the source, not the model's
  paraphrase),
- rows are ordered the way the guideline is,
- exact duplicate rows are dropped, and
- clause numbers that are not in the guideline are reported so the user knows
  to double-check them.

Everything here is deterministic and works with any backend.
"""

import re

from .models import RequirementRow

# A numbered markdown heading, e.g. "### 5.6 Audits and Assessments" or
# "## 5 INFORMATION SECURITY CONSIDERATIONS". The docx/md/txt loaders all
# emit clauses in this form.
_HEADING = re.compile(r"^#{1,6}\s+(\d+(?:\.\d+)*)\s+(\S.*)$")
# The first clause-number-looking token inside a model-supplied ref string,
# tolerating prefixes like "Clause 5.3" or "Section 5.6.".
_REF = re.compile(r"\d+(?:\.\d+)*")

# Words that make a guideline statement a binding ("M") obligation on the
# vendor versus a recommended ("O") one. Strong wins over weak when both
# appear, and a normative statement with neither defaults to mandatory (the
# guideline is written predominantly in must/shall style).
_STRONG = re.compile(
    r"\b(must|shall|mandatory|mandated|required|requires|require|"
    r"prohibited|may not|must not|shall not|responsible for)\b", re.I)
_WEAK = re.compile(
    r"\b(should|recommended|may|preferred|where feasible|where possible|"
    r"optional|encouraged)\b", re.I)
# A body paragraph is treated as a vendor requirement only if it carries one
# of these obligation cues; this skips descriptive prose (e.g. the
# Introduction) so it never lands in the compliance tracker.
_NORMATIVE = re.compile(
    r"\b(must|shall|mandatory|mandated|required|requires|require|"
    r"prohibited|should|recommended|may not|must not|shall not|"
    r"responsible for|are required|is required)\b", re.I)


def parse_clauses(text: str) -> dict[str, str]:
    """Return an ordered ``{clause_ref: heading_title}`` map for the guideline.

    Insertion order follows the document, which is also numeric order.
    Returns an empty dict when the guideline has no numbered headings (e.g. a
    plain-text guideline) so callers can skip reconciliation gracefully.
    """
    clauses: dict[str, str] = {}
    for line in text.splitlines():
        match = _HEADING.match(line.strip())
        if match:
            ref, title = match.group(1), match.group(2).strip()
            clauses.setdefault(ref, title)
    return clauses


def classify_obligation(text: str) -> str:
    """Return 'M' (binding) or 'O' (recommended) for a requirement statement."""
    if _STRONG.search(text or ""):
        return "M"
    if _WEAK.search(text or ""):
        return "O"
    return "M"


def parse_clause_requirements(text: str) -> dict[str, list[RequirementRow]]:
    """Break the guideline body into granular, per-clause requirement rows.

    Each normative paragraph under a numbered clause heading becomes one
    :class:`RequirementRow`, carrying the clause ref, the real heading title
    and an M/O flag derived from the paragraph's own wording. Non-normative
    prose (e.g. the Introduction) is skipped. The result is the deterministic,
    guideline-derived source of truth the checklist is expanded from, so the
    vendor-facing requirements are detailed and verbatim rather than a model
    paraphrase. Returns an ordered ``{clause_ref: [rows...]}`` map following
    the document; empty for unstructured text.
    """
    by_clause: dict[str, list[RequirementRow]] = {}
    ref: str | None = None
    title = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heading = _HEADING.match(stripped)
        if heading:
            ref, title = heading.group(1), heading.group(2).strip()
            by_clause.setdefault(ref, [])
            continue
        if ref is None or not _NORMATIVE.search(stripped):
            continue
        by_clause[ref].append(
            RequirementRow(ref=ref, section=title, requirement=stripped,
                           mandatory=classify_obligation(stripped)))
    return by_clause


def normalize_ref(ref: str) -> str:
    """Pull the bare clause number out of a model-supplied ref string."""
    match = _REF.search(ref or "")
    return match.group(0) if match else (ref or "").strip()


def clause_sort_key(ref: str):
    """Sort key putting parseable clause numbers in numeric guideline order.

    "5.6" sorts before "5.10" and before "11.1"; refs without a recognisable
    number sort last.
    """
    match = _REF.search(ref or "")
    if not match:
        return (1, ())
    return (0, tuple(int(part) for part in match.group(0).split(".")))


def reconcile_requirements(
    rows: list[RequirementRow], clauses: dict[str, str]
) -> tuple[list[RequirementRow], list[str]]:
    """Ground requirement rows against the clause index.

    Returns the cleaned rows and the list of clause refs that are not in the
    guideline (in their first-seen order). When ``clauses`` is empty the rows
    are returned unchanged and nothing is reported as unverified.
    """
    if not clauses:
        return rows, []

    cleaned: list[RequirementRow] = []
    seen: set[tuple[str, str]] = set()
    unverified: list[str] = []
    for row in rows:
        ref = normalize_ref(row.ref)
        dedupe_key = (ref, row.requirement.strip().lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        title = clauses.get(ref)
        if title is None:
            if ref and ref not in unverified:
                unverified.append(ref)
        else:
            row.section = title  # canonicalise to the real heading
        row.ref = ref
        cleaned.append(row)

    cleaned.sort(key=lambda r: clause_sort_key(r.ref))
    return cleaned, unverified


def expand_requirements(
    rows: list[RequirementRow], clause_reqs: dict[str, list[RequirementRow]]
) -> list[RequirementRow]:
    """Expand each selected clause into its granular guideline requirements.

    ``rows`` are the model's grounded selections (after
    :func:`reconcile_requirements`); each one names a clause the model judged
    applicable to the purchase. For every such clause this replaces the single
    model row with the full set of atomic requirement rows parsed from the
    guideline body for that clause — and for any of its sub-clauses, so citing
    a whole section (e.g. "5") pulls in 5.1–5.7. Clauses the guideline has no
    parsed body for (e.g. a headings-only document) keep the model's own row,
    so the function degrades gracefully. Rows are de-duplicated and returned in
    guideline order; the within-clause order of the source body is preserved.
    """
    if not clause_reqs:
        return rows

    out: list[RequirementRow] = []
    seen: set[tuple[str, str]] = set()

    def push(row: RequirementRow) -> None:
        key = (row.ref, row.requirement.strip().lower())
        if key not in seen:
            seen.add(key)
            out.append(row)

    for row in rows:
        ref = normalize_ref(row.ref)
        atomic: list[RequirementRow] = []
        for cref, reqs in clause_reqs.items():
            if cref == ref or cref.startswith(ref + "."):
                atomic.extend(reqs)
        if atomic:
            for r in atomic:
                push(RequirementRow(r.ref, r.section, r.requirement,
                                    r.mandatory))
        else:
            push(row)

    out.sort(key=lambda r: clause_sort_key(r.ref))
    return out


# Sections that apply to essentially every procurement regardless of the item
# type — contract terms, information security and compliance/risk management.
# A compliance deliverable must never silently drop these, so they are always
# folded into the checklist even when the model fails to select them (small
# local models under-select). Gated on the guideline actually containing the
# section, so an unstructured guideline adds nothing.
CORE_SECTIONS = ("4", "5", "11")


def ensure_core_sections(
    rows: list[RequirementRow],
    clause_reqs: dict[str, list[RequirementRow]],
    core: tuple[str, ...] = CORE_SECTIONS,
) -> tuple[list[RequirementRow], list[str]]:
    """Guarantee the cross-cutting core sections are present in the checklist.

    The model selects the item-specific clauses; this deterministic safety net
    adds the atomic requirements of every core section the guideline contains
    that ``rows`` don't already cover, then returns the merged set in guideline
    order together with the section roots that had to be added (so the user can
    be told the safety net fired). With no parsed body (e.g. an unstructured
    guideline) nothing is added and ``rows`` is returned unchanged.
    """
    if not clause_reqs:
        return rows, []

    out = list(rows)
    seen = {(r.ref, r.requirement.strip().lower()) for r in out}
    present_roots = {normalize_ref(r.ref).split(".")[0] for r in rows}
    added_roots: list[str] = []
    for cref, reqs in clause_reqs.items():
        root = cref.split(".")[0]
        if root not in core:
            continue
        if root not in present_roots and root not in added_roots and reqs:
            added_roots.append(root)
        for r in reqs:
            key = (r.ref, r.requirement.strip().lower())
            if key not in seen:
                seen.add(key)
                out.append(RequirementRow(r.ref, r.section, r.requirement,
                                          r.mandatory))
    out.sort(key=lambda r: clause_sort_key(r.ref))
    return out, sorted(added_roots, key=clause_sort_key)


# Applicability questions derived from the guideline's top-level sections. Each
# entry is (section root that must exist for the question to be asked, dedupe
# keywords, question, include_root). They are merged into the interview so the
# reverse-prompting covers every major part of the guideline and the model can
# decide which sections apply — even on small models that under-ask. Gated on
# the guideline actually having that section.
#
# ``include_root`` is the section that is folded into the checklist
# deterministically when the buyer answers this question affirmatively (None
# for questions whose section is already always-on or only narrows wording).
# This is what ties the reverse-prompting answers to the compliance list: if
# the buyer says the purchase includes hardware, every hardware clause is
# included even on a model that missed section 8.
_COVERAGE = [
    ("4", ("contract duration", "renewal", "termination", "contract term"),
     "What is the expected contract duration, and are there renewal, "
     "extension or termination conditions to plan for?", None),
    ("5", ("personal data", "pdpa", "payment", "pci", "sensitive data"),
     "Will the solution store, process or transmit personal data (PDPA) or "
     "payment-card data (PCI DSS)?", None),
    ("5", ("internet-facing", "network", "production system", "exposed"),
     "Will the solution be internet-facing or connect to XXEON's internal "
     "network and production systems?", None),
    ("6", ("integrat", "interoper", "sso", "existing system"),
     "Does the solution need to integrate with existing XXEON systems, "
     "databases, browsers or single sign-on?", "6"),
    ("7", ("support", "maintenance", "sla", "uptime"),
     "What level of ongoing support and maintenance is required (e.g. 24/7 or "
     "business hours), and over what period?", "7"),
    ("8", ("hardware", "equipment", "appliance", "device", "physical"),
     "Does this purchase include physical hardware or equipment (e.g. servers, "
     "appliances, end-user devices)? If so, list the main items.", "8"),
    ("9", ("software", "licen", "application", "subscription"),
     "Does it include software or application licensing? If so, which model is "
     "preferred (perpetual, subscription or SaaS)?", "9"),
    ("10", ("total cost", "ownership", "tco", "roi", "payment schedule",
            "financial"),
     "What are the financial expectations — should the vendor provide a "
     "five-year Total Cost of Ownership and ROI analysis, and what payment "
     "schedule (monthly, quarterly or annual) is preferred?", "10"),
    ("12", ("post-implementation", "performance review", "user feedback",
            "continuous improvement", "roadmap", "go-live"),
     "After go-live, will you require post-implementation performance reviews, "
     "user feedback collection, and a continuous improvement roadmap from the "
     "vendor?", "12"),
    ("11", ("cloud", "hosted", "saas", "iaas", "paas", "hosting"),
     "Is the vendor providing cloud or hosted services (SaaS/IaaS/PaaS), and "
     "where would the data be hosted?", None),
    ("11.3", ("cybersecurity assessment", "penetration", "pen test",
              "compromise assessment", "security assessment"),
     "Is this a cybersecurity assessment service such as a penetration test or "
     "compromise assessment?", None),
    ("5", ("on-premise", "on-prem", "deploy", "hybrid"),
     "Will the solution be deployed on-premise, in the cloud, or as a "
     "hybrid?", None),
]

# A clearly negative free-text answer ("no", "none", "not applicable", ...).
_NEGATIVE = re.compile(
    r"\b(no|nope|none|nil|n/?a|not\s+(applicable|required|needed|relevant)|"
    r"isn'?t|aren'?t|won'?t|will\s+not|doesn'?t|does\s+not|do\s+not|don'?t|"
    r"never|without)\b", re.I)
# Words that explicitly affirm, so "no hardware but yes to the appliance" still
# counts as a yes rather than being pruned by the bare "no".
_AFFIRMATIVE = re.compile(
    r"\b(yes|yep|yeah|yup|correct|indeed|affirmative|sure|include[sd]?|"
    r"required|needed|will|does|do|has|have|both|some|several)\b", re.I)


def is_affirmative(answer: str) -> bool:
    """Decide whether an interview answer says a topic applies.

    Compliance-safe and inclusive: a blank answer or a clearly negative one
    ("no", "n/a", "not required") with no affirmative cue is treated as "does
    not apply"; everything else — an explicit yes, or any substantive answer
    such as "10 servers" or "24/7 for 3 years" — is treated as "applies".
    """
    text = (answer or "").strip()
    if not text:
        return False
    if _NEGATIVE.search(text) and not _AFFIRMATIVE.search(text):
        return False
    return True


def coverage_questions(clauses: dict[str, str]) -> list[tuple[str, str]]:
    """Return guideline-grounded applicability questions for the interview.

    Each is ``(dedupe_keywords_csv, question)``. Only questions whose section
    exists in the guideline are returned; empty for unstructured guidelines so
    we never ask questions the guideline can't ground.
    """
    if not clauses:
        return []
    present = set(clauses)
    out: list[tuple[str, str]] = []
    for root, keywords, question, _include in _COVERAGE:
        if any(ref == root or ref.startswith(root + ".") for ref in present):
            out.append((",".join(keywords), question))
    return out


# The item-type-specific coverage topics — these are the questions that only
# apply to a particular kind of purchase (hardware vs. software vs. an
# integration), so they are the ones worth tailoring to the item. Everything
# else (contract, data/security, support, cloud, financial, post-implementation,
# cybersecurity assessment) can apply to any purchase and is always asked.
ITEM_TYPE_ROOTS = {"6", "8", "9"}

# Plain-language cues that signal an item-type topic is relevant, beyond the
# topic's own dedupe keywords. Lets "20 laptops" select the hardware question
# and "Microsoft 365 subscription" select the software question without the
# buyer having to use the guideline's own vocabulary.
_ITEM_SIGNALS = {
    "6": ("integrat", "interoper", "sso", "single sign", "api", "interface",
          "connector", "plugin", "ldap", "active directory", "saml", "oauth",
          "existing system"),
    "8": ("hardware", "equipment", "appliance", "device", "physical", "laptop",
          "desktop", "notebook", "pc", "workstation", "server", "monitor",
          "printer", "scanner", "switch", "router", "firewall", "storage",
          "nas", "san", "rack", "ups", "peripheral", "tablet", "phone",
          "handset", "camera", "sensor", "cabling", "kiosk"),
    "9": ("software", "licen", "application", "subscription", "app", "saas",
          "platform", "suite", "erp", "crm", "office", "microsoft", "adobe",
          "antivirus", "database", "middleware", "module", "portal"),
}


def _item_relevance(include_root: str, keywords, item_lower: str) -> int:
    """Count how many of a topic's cues appear in the item description."""
    cues = set(keywords) | set(_ITEM_SIGNALS.get(include_root, ()))
    return sum(1 for cue in cues if cue and cue in item_lower)


def relevant_coverage_questions(
    clauses: dict[str, str], item_description: str
) -> list[tuple[str, str]]:
    """Coverage questions tailored to the item or service being purchased.

    Same guideline-grounded questions as :func:`coverage_questions`, but the
    item-type-specific topics (integration 6, hardware 8, software 9) are kept
    only when the item description points to them — so a buyer purchasing
    laptops isn't asked which software-licensing model they prefer, and a SaaS
    buyer isn't asked to list physical hardware. The relevant item-type
    questions lead the list. Cross-cutting topics are always kept because they
    can apply to any purchase. When the item gives no signal for any item-type
    topic (a vague description), all topics are kept — the previous broad,
    compliance-safe behaviour — so the interview never under-asks.
    """
    if not clauses:
        return []
    present = set(clauses)
    item_lower = (item_description or "").lower()

    available = []
    for root, keywords, question, include_root in _COVERAGE:
        if not any(ref == root or ref.startswith(root + ".") for ref in present):
            continue
        gated = include_root in ITEM_TYPE_ROOTS
        score = (_item_relevance(include_root, keywords, item_lower)
                 if gated else 0)
        available.append((",".join(keywords), question, gated, score))

    any_item_match = any(gated and score > 0
                         for _, _, gated, score in available)

    leading: list[tuple[str, str]] = []
    rest: list[tuple[str, str]] = []
    for csv, question, gated, score in available:
        if not gated:
            rest.append((csv, question))
        elif score > 0:
            leading.append((csv, question))      # relevant to this item
        elif not any_item_match:
            rest.append((csv, question))          # vague item — keep it
        # else: a clearly different item type — drop this question.
    return leading + rest



def sections_from_answers(
    answers: list[tuple[str, str]], clauses: dict[str, str]
) -> list[str]:
    """Section roots to force-include based on affirmative interview answers.

    Reverse-prompting exists so the buyer's own answers decide which
    item-specific guideline sections apply. For every coverage topic tied to a
    section (integration → 6, support → 7, hardware → 8, software → 9,
    financial → 10, post-implementation → 12), if the
    matching interview answer is affirmative the whole section is pulled into
    the checklist deterministically — independent of the model's clause
    selection, so a weak model can't drop a section the buyer said applies.
    Matching is by the question's wording (the model's own phrasing or the
    merged coverage question), gated on the section existing in the guideline;
    empty for unstructured guidelines.
    """
    if not clauses:
        return []
    present = set(clauses)
    roots: list[str] = []
    for _gate, keywords, _question, include_root in _COVERAGE:
        if not include_root or include_root in roots:
            continue
        if not any(ref == include_root or ref.startswith(include_root + ".")
                   for ref in present):
            continue
        for question, answer in answers:
            ql = (question or "").lower()
            if any(kw in ql for kw in keywords) and is_affirmative(answer):
                roots.append(include_root)
                break
    return roots
