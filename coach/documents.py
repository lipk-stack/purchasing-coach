"""Load a guideline document (.docx, .md, .txt, .pdf) into plain text."""

from pathlib import Path


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
    import docx  # python-docx

    document = docx.Document(str(path))
    lines: list[str] = []
    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name or "").lower()
        if style.startswith("heading"):
            try:
                level = int(style.replace("heading", "").strip() or 1)
            except ValueError:
                level = 1
            lines.append("#" * min(level, 6) + " " + text)
        elif style.startswith("title"):
            lines.append("# " + text)
        else:
            lines.append(text)
    return "\n\n".join(lines)


def _load_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "PDF support requires the 'pypdf' package: pip install pypdf"
        ) from exc
    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)
