"""Read/write the tender checklist Excel workbook based on the template."""

from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .models import RequirementRow, TenderInfo

INFO_SHEET = "Tender Information"
TRACKER_SHEET = "Compliance Tracker"
TRACKER_HEADERS = ["Seq", "Ref", "Section", "Requirement", "M/O",
                   "Vendor Status", "Vendor Remarks"]

# Standardised values the vendor/service provider picks from when populating
# the "Vendor Status" column. A fixed vocabulary (rather than free text) keeps
# the submitted checklist consistent and lets the reviewer filter/score it
# during review and approval. Free-text justification still goes in the
# adjacent "Vendor Remarks" column.
VENDOR_STATUS_OPTIONS = [
    "Compliant",
    "Partially Compliant",
    "Non-Compliant",
    "Not Applicable",
]


def write_checklist(
    tender_info: TenderInfo,
    requirements: list[RequirementRow],
    out_path: str | Path,
    template_path: str | Path | None = None,
) -> Path:
    """Fill the tender template with the interview results and save it.

    If ``template_path`` is given the workbook is loaded from it (preserving
    its formatting); otherwise a fresh workbook with the same layout is built.
    """
    out_path = Path(out_path)
    if template_path and Path(template_path).exists():
        wb = load_workbook(str(template_path))
    else:
        wb = create_blank_template()

    _fill_info_sheet(wb, tender_info)
    _fill_tracker_sheet(wb, requirements)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
    return out_path


def _fill_info_sheet(wb, tender_info: TenderInfo) -> None:
    ws = _find_sheet(wb, INFO_SHEET)
    values = {label: getattr(tender_info, attr)
              for label, attr in TenderInfo.TEMPLATE_LABELS.items()}
    found = set()
    for row in ws.iter_rows():
        for cell in row:
            label = str(cell.value).strip() if cell.value else ""
            if label in values:
                target = ws.cell(row=cell.row, column=cell.column + 1)
                target.value = values[label]
                target.alignment = Alignment(vertical="top", wrap_text=True)
                found.add(label)
    # Labels missing from the template are appended at the bottom.
    for label in values:
        if label not in found:
            row = ws.max_row + 1
            ws.cell(row=row, column=1, value=label).font = Font(bold=True)
            ws.cell(row=row, column=2, value=values[label])


def _fill_tracker_sheet(wb, requirements: list[RequirementRow]) -> None:
    ws = _find_sheet(wb, TRACKER_SHEET)
    header_row = _find_header_row(ws)
    col = {str(c.value).strip(): c.column for c in ws[header_row] if c.value}

    row = header_row + 1
    for seq, req in enumerate(requirements, start=1):
        entries = {
            "Seq": seq,
            "Ref": req.ref,
            "Section": req.section,
            "Requirement": req.requirement,
            "M/O": req.mandatory,
            "Vendor Status": "",
            "Vendor Remarks": "",
        }
        for header, value in entries.items():
            if header in col:
                cell = ws.cell(row=row, column=col[header], value=value)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        row += 1

    last_row = row - 1
    _extend_table(ws, header_row, last_row)
    _add_status_dropdown(ws, header_row, last_row, col)
    # Keep the header (and the tender title above it) visible while the
    # reviewer scrolls a long, granular checklist.
    if last_row > header_row:
        ws.freeze_panes = ws.cell(row=header_row + 1, column=1)


def _add_status_dropdown(ws, header_row: int, last_row: int,
                         col: dict[str, int]) -> None:
    """Constrain the Vendor Status column to the standard compliance values.

    The vendor populates this column with a dropdown choice, so submissions are
    consistent and the reviewer can filter and approve against a fixed
    vocabulary. No-op when the column is absent or there are no data rows.
    """
    status_col = col.get("Vendor Status")
    if not status_col or last_row <= header_row:
        return
    letter = get_column_letter(status_col)
    options = ",".join(VENDOR_STATUS_OPTIONS)
    dv = DataValidation(type="list", formula1=f'"{options}"',
                        allow_blank=True, showDropDown=False)
    dv.error = "Pick one of the standard compliance statuses."
    dv.errorTitle = "Invalid status"
    dv.prompt = "Select the vendor's compliance status for this requirement."
    dv.promptTitle = "Vendor Status"
    dv.add(f"{letter}{header_row + 1}:{letter}{last_row}")
    ws.add_data_validation(dv)


def _find_sheet(wb, name: str):
    for ws in wb.worksheets:
        if ws.title.strip().lower() == name.lower():
            return ws
    ws = wb.create_sheet(name)
    if name == TRACKER_SHEET:
        for i, header in enumerate(TRACKER_HEADERS, start=1):
            ws.cell(row=1, column=i, value=header).font = Font(bold=True)
    return ws


def _find_header_row(ws) -> int:
    for row in ws.iter_rows(max_row=20):
        values = {str(c.value).strip() for c in row if c.value}
        if "Seq" in values and "Requirement" in values:
            return row[0].row
    # No header found — write one on the first empty row.
    row = ws.max_row + 1 if ws.max_row > 1 or ws["A1"].value else 1
    for i, header in enumerate(TRACKER_HEADERS, start=1):
        ws.cell(row=row, column=i, value=header).font = Font(bold=True)
    return row


def _extend_table(ws, header_row: int, last_row: int) -> None:
    """If the sheet has an Excel table over the tracker, grow it to fit."""
    if last_row <= header_row:
        return
    for table in getattr(ws, "tables", {}).values():
        start, _ = table.ref.split(":")
        if int("".join(filter(str.isdigit, start))) == header_row:
            last_col = get_column_letter(ws.max_column)
            table.ref = f"{start}:{last_col}{last_row}"


def create_blank_template() -> Workbook:
    """Build a workbook matching the TENDER_TEMPLATE.xlsx layout."""
    wb = Workbook()
    title_font = Font(bold=True, size=14)
    label_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")

    ws = wb.active
    ws.title = INFO_SHEET
    ws["A1"] = "TENDER INFORMATION"
    ws["A1"].font = title_font
    for i, label in enumerate(TenderInfo.TEMPLATE_LABELS, start=3):
        cell = ws.cell(row=i, column=1, value=label)
        cell.font = label_font
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 60

    ws = wb.create_sheet(TRACKER_SHEET)
    ws["A1"] = "IT PROCUREMENT COMPLIANCE TRACKER"
    ws["A1"].font = title_font
    for i, header in enumerate(TRACKER_HEADERS, start=1):
        cell = ws.cell(row=3, column=i, value=header)
        cell.font = header_font
        cell.fill = header_fill
    widths = [6, 8, 28, 80, 6, 16, 30]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    return wb
