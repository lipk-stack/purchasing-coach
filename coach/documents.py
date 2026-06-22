"""Load a guideline document (.docx, .md, .txt, .pdf) into plain text.

The .docx reader uses only the standard library (a .docx file is a zip of
XML), so the app stays portable — no compiled dependencies like lxml.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# A .docx is a zip; its word/document.xml decompresses to plain text that is
# normally tens of KB (the sample guideline is ~40 KB). Cap how much we will
# decompress so a malformed or zip-bomb file — tiny on disk, huge when expanded
# — cannot exhaust memory on the user's machine. 64 MiB is vast headroom for any
# real guideline while still bounding the damage from a hostile or broken file.
_MAX_DOCX_XML_BYTES = 64 * 1024 * 1024


def load_guideline(path: str | Path) -> str:
    """Return the guideline document as plain text with headings preserved.

    Raises a clear, actionable error rather than a cryptic stdlib exception when
    the file is missing, a directory, an unsupported format, corrupt, or empty.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Guideline document not found: {path}")
    if not path.is_file():
        raise ValueError(f"Guideline path is not a file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".docx":
        text = _load_docx(path)
    elif suffix in (".md", ".markdown", ".txt"):
        text = _read_text_file(path)
    elif suffix == ".pdf":
        text = _load_pdf(path)
    else:
        raise ValueError(
            f"Unsupported guideline format '{suffix}'. "
            "Use .docx, .md, .txt or .pdf."
        )

    if not text or not text.strip():
        raise ValueError(
            f"Guideline document '{path.name}' contains no readable text. "
            "Check that it is the right file and is not empty or image-only."
        )
    return text


def _read_text_file(path: Path) -> str:
    """Read a text/markdown file, tolerating common non-UTF-8 encodings.

    Procurement documents are often exported from Windows tools (cp1252). Try
    UTF-8 first (with and without BOM), then cp1252; latin-1 decodes any byte
    sequence, so it is the guaranteed final fallback.
    """
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    # Unreachable in practice (latin-1 never raises) — defensive only.
    return path.read_text(encoding="utf-8", errors="replace")


def _load_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            try:
                info = zf.getinfo("word/document.xml")
            except KeyError as exc:
                raise ValueError(
                    f"'{path.name}' is missing word/document.xml — not a valid "
                    ".docx file."
                ) from exc
            # Fast, clear rejection for a bomb that honestly declares its size.
            if info.file_size > _MAX_DOCX_XML_BYTES:
                raise ValueError(
                    f"'{path.name}' is too large to process: its text content "
                    f"declares {info.file_size:,} bytes "
                    f"(limit {_MAX_DOCX_XML_BYTES:,}). "
                    "Check that this is a real guideline document."
                )
            # Bounded read: also defends against a header that under-reports the
            # true expanded size. We never hold more than the cap in memory.
            with zf.open(info) as member:
                data = member.read(_MAX_DOCX_XML_BYTES + 1)
            if len(data) > _MAX_DOCX_XML_BYTES:
                raise ValueError(
                    f"'{path.name}' expands to more than "
                    f"{_MAX_DOCX_XML_BYTES:,} bytes of text and was refused as a "
                    "possible zip bomb."
                )
    except zipfile.BadZipFile as exc:
        raise ValueError(
            f"'{path.name}' is not a valid .docx file (corrupt, or not a Word "
            "document). If it's a .doc, re-save it as .docx."
        ) from exc

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(
            f"'{path.name}' contains malformed XML and could not be read."
        ) from exc

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
