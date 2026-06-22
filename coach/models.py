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
        if not isinstance(data, dict):
            data = {}
        raw = data.get("questions")
        if not isinstance(raw, list):
            raw = []  # a string here would otherwise iterate char-by-char
        questions = []
        for i, q in enumerate(raw, start=1):
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
        if not isinstance(data, dict):
            data = {}
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
    # Cross-cutting section roots the deterministic safety net had to add
    # because the model didn't select them (e.g. ['4', '11']); empty when the
    # model already covered every core section.
    added_core_sections: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "TenderChecklist":
        if not isinstance(data, dict):
            data = {}
        raw = data.get("requirements")
        if not isinstance(raw, list):
            raw = []
        rows = [RequirementRow.from_dict(r) for r in raw if isinstance(r, dict)]
        rows = [r for r in rows if r.requirement]
        # Non-LLM backends may return empty rows; the Coach's deterministic
        # pipeline (reconcile, expand, ensure_core_sections) fills them in.
        return cls(tender_info=TenderInfo.from_dict(data.get("tender_info") or {}),
                   requirements=rows)


# --------------------------------------------------------------------------
# Session & chat models (for the web UI)
# --------------------------------------------------------------------------
@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: str = ""
    reactions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "reactions": self.reactions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage":
        if not isinstance(data, dict):
            data = {}
        reactions = data.get("reactions")
        if not isinstance(reactions, list):
            reactions = []
        return cls(
            role=str(data.get("role", "user")),
            content=str(data.get("content", "")),
            timestamp=str(data.get("timestamp", "")),
            reactions=reactions,
        )


@dataclass
class Session:
    """A persisted chat session with message history and optional checklist."""

    id: str
    title: str = "New session"
    messages: list[ChatMessage] = field(default_factory=list)
    backend: str = ""
    guideline_path: str = ""
    checklist_data: dict | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "backend": self.backend,
            "guideline_path": self.guideline_path,
            "checklist_data": self.checklist_data,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        if not isinstance(data, dict):
            data = {}
        raw_msgs = data.get("messages")
        if not isinstance(raw_msgs, list):
            raw_msgs = []
        msgs = [ChatMessage.from_dict(m) for m in raw_msgs
                if isinstance(m, dict)]
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "New session")),
            messages=msgs,
            backend=str(data.get("backend", "")),
            guideline_path=str(data.get("guideline_path", "")),
            checklist_data=data.get("checklist_data"),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


@dataclass
class AnalyticsSnapshot:
    """Point-in-time analytics for a tender checklist, rendered by the dashboard."""

    total_requirements: int = 0
    by_section: dict[str, int] = field(default_factory=dict)
    mandatory_count: int = 0
    optional_count: int = 0
    coverage_pct: float = 0.0
    section_heatmap: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_requirements": self.total_requirements,
            "by_section": self.by_section,
            "mandatory_count": self.mandatory_count,
            "optional_count": self.optional_count,
            "coverage_pct": self.coverage_pct,
            "section_heatmap": self.section_heatmap,
        }

    @classmethod
    def from_checklist(
        cls,
        requirements: list[RequirementRow],
        total_clauses: int = 0,
    ) -> "AnalyticsSnapshot":
        """Compute analytics from a list of requirement rows."""
        by_section: dict[str, int] = {}
        mandatory = 0
        optional = 0
        sections_seen: set[str] = set()

        for row in requirements:
            by_section[row.section] = by_section.get(row.section, 0) + 1
            if row.mandatory == "M":
                mandatory += 1
            else:
                optional += 1
            # Track unique section roots for coverage calculation
            root = row.ref.split(".")[0] if row.ref else ""
            if root:
                sections_seen.add(root)

        total = len(requirements)
        coverage = 0.0
        if total_clauses > 0:
            # Coverage = how many top-level sections are represented
            max_sections = max(total_clauses, 1)
            coverage = round(len(sections_seen) / max_sections * 100, 1)

        # Heatmap: normalise section counts to 0–1 range
        heatmap: dict[str, float] = {}
        max_count = max(by_section.values()) if by_section else 1
        for sec, count in by_section.items():
            heatmap[sec] = round(count / max(max_count, 1), 2)

        return cls(
            total_requirements=total,
            by_section=dict(sorted(by_section.items())),
            mandatory_count=mandatory,
            optional_count=optional,
            coverage_pct=coverage,
            section_heatmap=heatmap,
        )


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
