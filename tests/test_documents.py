import zipfile

import pytest

from coach.documents import load_guideline


def test_load_docx(samples):
    text = load_guideline(samples["guideline"])
    assert "Termination Clauses" in text
    assert "Multi-factor authentication" in text
    # headings come through as markdown
    assert "# " in text


def test_load_markdown(samples):
    text = load_guideline(samples["guideline"].parent / "guideline_text.md")
    assert "IT Procurement Guideline" in text


def test_unsupported_format(tmp_path):
    bad = tmp_path / "guideline.xyz"
    bad.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported"):
        load_guideline(bad)


def test_missing_file_raises_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found"):
        load_guideline(tmp_path / "nope.docx")


def test_directory_path_raises(tmp_path):
    with pytest.raises(ValueError, match="not a file"):
        load_guideline(tmp_path)


def test_empty_document_raises(tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n\n  ")
    with pytest.raises(ValueError, match="no readable text"):
        load_guideline(empty)


def test_corrupt_docx_raises_clear_error(tmp_path):
    bad = tmp_path / "broken.docx"
    bad.write_bytes(b"this is not a zip file")
    with pytest.raises(ValueError, match="not a valid .docx"):
        load_guideline(bad)


def test_docx_missing_document_xml_raises(tmp_path):
    # A valid zip, but without word/document.xml.
    bad = tmp_path / "nodoc.docx"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("something_else.xml", "<root/>")
    with pytest.raises(ValueError, match="missing word/document.xml"):
        load_guideline(bad)


def test_oversize_docx_is_refused(tmp_path, monkeypatch):
    # A .docx whose word/document.xml expands past the cap is refused with a
    # clear error rather than being decompressed into memory (zip-bomb guard).
    from coach import documents

    monkeypatch.setattr(documents, "_MAX_DOCX_XML_BYTES", 2000)
    body = "".join(
        f"<w:p><w:t>line {i} of a deliberately large document body</w:t></w:p>"
        for i in range(200)
    )
    xml = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    assert len(xml.encode()) > 2000  # sanity: would exceed the (patched) cap
    big = tmp_path / "huge.docx"
    with zipfile.ZipFile(big, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", xml)
    with pytest.raises(ValueError, match="too large to process"):
        documents.load_guideline(big)


def test_non_utf8_text_file_is_read(tmp_path):
    # Raw cp1252 bytes (0x96 en-dash, 0x92 right quote) that are invalid UTF-8.
    f = tmp_path / "win.txt"
    f.write_bytes(b"Pricing \x96 payment terms \x92must\x92 apply")
    text = load_guideline(f)
    assert "payment terms" in text
