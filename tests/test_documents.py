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
    try:
        load_guideline(bad)
    except ValueError as exc:
        assert "Unsupported" in str(exc)
    else:
        raise AssertionError("expected ValueError")
