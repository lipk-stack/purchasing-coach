from openpyxl import load_workbook

from coach.excel import VENDOR_STATUS_OPTIONS, write_checklist
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


def _status_column_letter(tracker):
    for row in tracker.iter_rows(max_row=20):
        for cell in row:
            if cell.value and str(cell.value).strip() == "Vendor Status":
                return cell.column_letter, cell.row
    raise AssertionError("Vendor Status header not found")


def test_vendor_status_dropdown_and_freeze(samples, tmp_path):
    out = write_checklist(INFO, ROWS, tmp_path / "dv.xlsx", samples["template"])
    wb = load_workbook(out)
    tracker = wb["Compliance Tracker"]

    letter, header_row = _status_column_letter(tracker)
    # A list validation covers the written Vendor Status cells with the
    # standard compliance vocabulary.
    last_row = header_row + len(ROWS)
    target = f"{letter}{header_row + 1}:{letter}{last_row}"
    dv = next((d for d in tracker.data_validations.dataValidation
               if d.type == "list" and target in str(d.sqref)), None)
    assert dv is not None
    for option in VENDOR_STATUS_OPTIONS:
        assert option in dv.formula1
    # Header stays visible while scrolling the checklist.
    assert tracker.freeze_panes == f"A{header_row + 1}"


def test_status_dropdown_without_template(tmp_path):
    out = write_checklist(INFO, ROWS, tmp_path / "dv_blank.xlsx", None)
    wb = load_workbook(out)
    tracker = wb["Compliance Tracker"]
    dvs = list(tracker.data_validations.dataValidation)
    assert any(d.type == "list" for d in dvs)
