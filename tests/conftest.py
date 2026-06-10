import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    """Ensure the sample docx/xlsx exist (regenerates them if missing)."""
    from scripts import make_samples

    docx_path = make_samples.SAMPLES / "XXEON_IT_Procurement_Guideline.docx"
    xlsx_path = make_samples.SAMPLES / "TENDER_TEMPLATE.xlsx"
    if not docx_path.exists():
        make_samples.build_docx()
    if not xlsx_path.exists():
        make_samples.build_template()
    return {"guideline": docx_path, "template": xlsx_path}
