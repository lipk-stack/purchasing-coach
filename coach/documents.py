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

# A .pdf's page content streams are Flate-compressed too, so — like the .docx
# and .xlsx loaders — a file tiny on disk can expand to a huge amount of text (a
# "PDF bomb": a heavily compressed stream, or a document with an enormous page
# count). Bound both the file we will open and the text we accumulate so a
# hostile or broken PDF cannot exhaust memory. The caps match the .docx guard
# (64 MiB); real guideline PDFs are well under a megabyte.
_MAX_PDF_FILE_BYTES = 64 * 1024 * 1024
_MAX_PDF_TEXT_BYTES = 64 * 1024 * 1024


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

    # Collect each non-empty paragraph with its Word heading level (0 = body).
    paras: list[tuple[int, str]] = []
    for para in root.iter(f"{_W}p"):
        text = "".join(node.text or "" for node in para.iter(f"{_W}t")).strip()
        if text:
            paras.append((_heading_level(para), text))
    return _render_markdown(paras)


# A clause number at the very start of a line ("4", "4.1", "5.6.2"), but only
# when followed by a dot, ")" or whitespace — so "24/7" or "10am" are not
# mistaken for clause numbers.
_NUM_PREFIX = re.compile(r"^\d+(?:\.\d+)*(?=[.)\s])")


def _looks_like_heading(text: str) -> bool:
    """True for a short ``N[.N...] Title`` line typed as a manual heading.

    Real guidelines are often authored with the section number typed into a
    bold paragraph rather than a Word *heading style*. We treat such a line as a
    heading when it is short and does not read as a sentence (no trailing
    sentence punctuation), so a numbered body sentence or list item — e.g.
    "4 servers must be delivered by Q3." — is left as body text.
    """
    if not _NUM_PREFIX.match(text):
        return False
    if len(text) > 90 or len(text.split()) > 12:
        return False
    return not text.rstrip().endswith((".", ";", ":", ","))


def _render_markdown(paras: list[tuple[int, str]]) -> str:
    """Render paragraphs to markdown the clause parser understands.

    Headings become ``#``-prefixed lines so :mod:`coach.guideline` can index
    their clause numbers. Two real-world shapes are recovered so a user's own
    document still produces a checklist:

    - a manually numbered heading with no Word heading style (promoted to a
      heading by :func:`_looks_like_heading`), and
    - Word *auto-numbered* headings, where the number is rendered from the
      document's numbering definitions and is therefore absent from the text —
      a stable hierarchical number is synthesised from the heading nesting so
      the clauses can still be referenced. Synthesis only kicks in when the
      document carries no explicit clause numbers at all, so a document's own
      numbering is always preferred.
    """
    has_literal = any(
        _NUM_PREFIX.match(text)
        for level, text in paras
        if level or _looks_like_heading(text)
    )
    counters: list[int] = []
    lines: list[str] = []
    for level, text in paras:
        if not level and _looks_like_heading(text):
            level = _NUM_PREFIX.match(text).group(0).count(".") + 1
        if not level:
            lines.append(text)
        elif _NUM_PREFIX.match(text):
            lines.append("#" * min(level, 6) + " " + text)
        elif not has_literal:
            number = _next_number(counters, level)
            lines.append("#" * min(level, 6) + " " + number + " " + text)
        else:
            lines.append("#" * min(level, 6) + " " + text)
    return "\n\n".join(lines)


def _next_number(counters: list[int], level: int) -> str:
    """Advance hierarchical heading counters and return the dotted number."""
    while len(counters) < level:
        counters.append(0)
    del counters[level:]
    counters[level - 1] += 1
    for i in range(level - 1):  # a deeper heading seen before its parent
        if counters[i] == 0:
            counters[i] = 1
    return ".".join(str(c) for c in counters[:level])


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
    # Fast, clear rejection for a file that is simply too large on disk — the
    # PDF analogue of the .docx "declared size" check.
    size = path.stat().st_size
    if size > _MAX_PDF_FILE_BYTES:
        raise ValueError(
            f"'{path.name}' is too large to process: it is {size:,} bytes "
            f"(limit {_MAX_PDF_FILE_BYTES:,}). "
            "Check that this is a real guideline document."
        )
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "PDF support requires the 'pypdf' package: pip install pypdf"
        ) from exc
    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            total += len(text)
            # Bounded accumulation: defends against a small-on-disk PDF whose
            # compressed streams (or sheer page count) expand to a huge amount
            # of text, the way the .docx loader bounds its decompressed read.
            if total > _MAX_PDF_TEXT_BYTES:
                raise ValueError(
                    f"'{path.name}' expands to more than "
                    f"{_MAX_PDF_TEXT_BYTES:,} bytes of text and was refused as a "
                    "possible PDF bomb."
                )
            parts.append(text)
    except ValueError:
        raise  # our own size/bomb rejections pass straight through
    except Exception as exc:
        raise ValueError(
            f"'{path.name}' could not be read as a PDF (it may be corrupt, "
            "encrypted, or not a real PDF)."
        ) from exc
    return "\n\n".join(parts)
