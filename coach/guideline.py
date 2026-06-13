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
