"""Pydantic models for structured LLM outputs and the Excel checklist."""

from typing import ClassVar

from pydantic import BaseModel, Field


class InterviewQuestion(BaseModel):
    key: str = Field(description="Short snake_case identifier for the answer")
    question: str = Field(description="The question to ask the buyer, one sentence")


class InterviewPlan(BaseModel):
    questions: list[InterviewQuestion]


class TenderInfo(BaseModel):
    """Fields of the 'Tender Information' sheet in the template."""

    issue_date: str
    submission_deadline: str
    purchase_item: str
    issued_by: str
    requesting_dept: str
    tender_reference: str
    procurement_type: str
    estimated_value: str
    purchase_category: str

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


class RequirementRow(BaseModel):
    ref: str = Field(description="Guideline clause reference, e.g. '5.3'")
    section: str = Field(description="Guideline section title, e.g. 'Access Control'")
    requirement: str = Field(description="The requirement, phrased for the vendor")
    mandatory: str = Field(description="'M' for mandatory or 'O' for optional")


class TenderChecklist(BaseModel):
    tender_info: TenderInfo
    requirements: list[RequirementRow]
