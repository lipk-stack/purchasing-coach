"""Load a guideline document (.docx, .md, .txt, .pdf) into plain text.

The .docx reader uses only the standard library (a .docx file is a zip of
XML), so the app stays portable — no compiled dependencies like lxml.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def load_guideline(path: str | Path) -> str:
    """Return the guideline document as plain text with headings preserved."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Guideline document not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _load_docx(path)
    if suffix in (".md", ".markdown", ".txt"):
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        return _load_pdf(path)
    raise ValueError(
        f"Unsupported guideline format '{suffix}'. Use .docx, .md, .txt or .pdf."
    )


def _load_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))

    lines: list[str] = []
    for para in root.iter(f"{_W}p"):
        text = "".join(node.text or "" for node in para.iter(f"{_W}t")).strip()
        if not text:
            continue
        level = _heading_level(para)
        if level:
            lines.append("#" * min(level, 6) + " " + text)
        else:
            lines.append(text)
    return "\n\n".join(lines)


def _heading_level(para) -> int:
    """Return the heading level of a w:p element, or 0 for body text."""
    style = para.find(f"{_W}pPr/{_W}pStyle")
    if style is None:
        return 0
    name = style.get(f"{_W}val", "").lower()
    if name.startswith("heading"):
        digits = re.sub(r"\D", "", name)
        return int(digits) if digits else 1
    if name in ("title", "subtitle"):
        return 1
    return 0


def _load_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "PDF support requires the 'pypdf' package: pip install pypdf"
        ) from exc
    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)
