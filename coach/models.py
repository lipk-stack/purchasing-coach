"""Plain-dataclass models for LLM structured outputs and the Excel checklist.

Deliberately stdlib-only (no pydantic) so the app can run as a portable
zipapp on machines where compiled packages cannot be installed.
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar


def _text(value: Any, default: str = "TBC") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


@dataclass
class InterviewQuestion:
    key: str
    question: str


@dataclass
class InterviewPlan:
    questions: list[InterviewQuestion] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "InterviewPlan":
        questions = []
        for i, q in enumerate(data.get("questions") or [], start=1):
            if isinstance(q, str):
                questions.append(InterviewQuestion(key=f"q{i}", question=q))
            elif isinstance(q, dict) and q.get("question"):
                questions.append(InterviewQuestion(
                    key=_text(q.get("key"), f"q{i}"),
                    question=str(q["question"]).strip()))
        if not questions:
            raise ValueError("model returned no interview questions")
        return cls(questions=questions)


INTERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string",
                            "description": "short snake_case id"},
                    "question": {"type": "string",
                                 "description": "one-sentence question"},
                },
                "required": ["key", "question"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


@dataclass
class TenderInfo:
    """Fields of the 'Tender Information' sheet in the template."""

    issue_date: str = "TBC"
    submission_deadline: str = "TBC"
    purchase_item: str = "TBC"
    issued_by: str = "TBC"
    requesting_dept: str = "TBC"
    tender_reference: str = "TBC"
    procurement_type: str = "TBC"
    estimated_value: str = "TBC"
    purchase_category: str = "TBC"

    # Maps template cell labels -> model field names.
    TEMPLATE_LABELS: ClassVar[dict[str, str]] = {
        "Issue Date": "issue_date",
        "Submission Deadline": "submission_deadline",
        "Purchase Item": "purchase_item",
        "Issued By": "issued_by",
        "Requesting Dept": "requesting_dept",
        "Tender Reference": "tender_reference",
        "Procurement Type": "procurement_type",
        "Estimated Value": "estimated_value",
        "Purchase Category": "purchase_category",
    }

    @classmethod
    def from_dict(cls, data: dict) -> "TenderInfo":
        return cls(**{name: _text(data.get(name))
                      for name in cls.TEMPLATE_LABELS.values()})


@dataclass
class RequirementRow:
    ref: str
    section: str
    requirement: str
    mandatory: str  # "M" or "O"

    @classmethod
    def from_dict(cls, data: dict) -> "RequirementRow":
        mandatory = _text(data.get("mandatory"), "M").upper()
        if mandatory.startswith("O"):  # "O", "Optional"
            mandatory = "O"
        else:  # "M", "Mandatory" or anything unclear defaults to mandatory
            mandatory = "M"
        return cls(
            ref=_text(data.get("ref"), ""),
            section=_text(data.get("section"), ""),
            requirement=_text(data.get("requirement"), ""),
            mandatory=mandatory,
        )


@dataclass
class TenderChecklist:
    tender_info: TenderInfo
    requirements: list[RequirementRow] = field(default_factory=list)
    # Clause refs the model cited that are not in the guideline (filled in by
    # reconciliation); empty when every ref was verified.
    unverified_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "TenderChecklist":
        rows = [RequirementRow.from_dict(r)
                for r in data.get("requirements") or []
                if isinstance(r, dict)]
        rows = [r for r in rows if r.requirement]
        if not rows:
            raise ValueError("model returned no requirement rows")
        return cls(tender_info=TenderInfo.from_dict(data.get("tender_info") or {}),
                   requirements=rows)


CHECKLIST_SCHEMA = {
    "type": "object",
    "properties": {
        "tender_info": {
            "type": "object",
            "properties": {name: {"type": "string"}
                           for name in TenderInfo.TEMPLATE_LABELS.values()},
            "required": list(TenderInfo.TEMPLATE_LABELS.values()),
            "additionalProperties": False,
        },
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string",
                            "description": "guideline clause number, e.g. '5.3'"},
                    "section": {"type": "string",
                                "description": "clause title"},
                    "requirement": {"type": "string",
                                    "description": "vendor-facing requirement"},
                    "mandatory": {"type": "string", "enum": ["M", "O"]},
                },
                "required": ["ref", "section", "requirement", "mandatory"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["tender_info", "requirements"],
    "additionalProperties": False,
}
