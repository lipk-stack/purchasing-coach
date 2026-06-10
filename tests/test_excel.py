from openpyxl import load_workbook

from coach.excel import write_checklist
from coach.models import RequirementRow, TenderInfo

INFO = TenderInfo(
    issue_date="2026-06-10",
    submission_deadline="2026-07-10",
    purchase_item="Endpoint backup SaaS",
    issued_by="IT Procurement",
    requesting_dept="Infrastructure",
    tender_reference="XXEON-IT-2026-014",
    procurement_type="Tender",
    estimated_value="MYR 250,000",
    purchase_category="Cloud Services",
)

ROWS = [
    RequirementRow(ref="5.3", section="Access Control",
                   requirement="Enforce MFA for all user accounts.", mandatory="M"),
    RequirementRow(ref="5.6", section="Audits and Assessments",
                   requirement="Provide annual SOC 2 Type II report.", mandatory="M"),
    RequirementRow(ref="10.1", section="TCO Analysis",
                   requirement="Provide 5-year TCO analysis.", mandatory="O"),
]


def test_write_with_template(samples, tmp_path):
    out = write_checklist(INFO, ROWS, tmp_path / "out.xlsx", samples["template"])
    wb = load_workbook(out)

    info = wb["Tender Information"]
    cells = {info.cell(r, 1).value: info.cell(r, 2).value
             for r in range(1, info.max_row + 1)}
    assert cells["Purchase Item"] == "Endpoint backup SaaS"
    assert cells["Tender Reference"] == "XXEON-IT-2026-014"

    tracker = wb["Compliance Tracker"]
    rows = list(tracker.iter_rows(values_only=True))
    header_idx = next(i for i, r in enumerate(rows) if r and "Seq" in r)
    data = rows[header_idx + 1: header_idx + 1 + len(ROWS)]
    assert data[0][:5] == (1, "5.3", "Access Control",
                           "Enforce MFA for all user accounts.", "M")
    assert data[2][1] == "10.1"


def test_write_without_template(tmp_path):
    out = write_checklist(INFO, ROWS, tmp_path / "no_template.xlsx", None)
    wb = load_workbook(out)
    assert "Tender Information" in wb.sheetnames
    assert "Compliance Tracker" in wb.sheetnames
