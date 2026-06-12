"""Terminal markdown rendering: ANSI styling and plain-text fallback."""

import io

from coach.format import BOLD, CYAN, DIM, RESET, UNDERLINE, StreamPrinter

REPLY = (
    "Yes — MFA is required.\n"
    "\n"
    "### Access control\n"
    "- **5.3** — enforce MFA for all accounts\n"
    "* **5.4** — quarterly access reviews\n"
    "1. agree the SLA\n"
    "Run `ollama serve` first.\n"
)


def render(text: str, ansi: bool, chunks: int = 1) -> str:
    out = io.StringIO()
    printer = StreamPrinter(out, ansi=ansi)
    step = max(1, len(text) // chunks)
    for i in range(0, len(text), step):
        printer.feed(text[i:i + step])
    printer.close()
    return out.getvalue()


def test_plain_strips_markdown_markers():
    text = render(REPLY, ansi=False)
    assert text == (
        "Yes — MFA is required.\n"
        "\n"
        "Access control\n"
        "  • 5.3 — enforce MFA for all accounts\n"
        "  • 5.4 — quarterly access reviews\n"
        "  1. agree the SLA\n"
        "Run ollama serve first.\n"
    )


def test_ansi_styles_headings_bold_and_code():
    text = render(REPLY, ansi=True)
    assert f"{BOLD}{UNDERLINE}Access control{RESET}" in text
    assert f"  • {BOLD}5.3{RESET} — enforce MFA for all accounts" in text
    assert f"{CYAN}ollama serve{RESET}" in text


def test_streaming_chunks_split_anywhere():
    # Tiny chunks can split lines and ** markers; output must not change.
    assert render(REPLY, ansi=True, chunks=200) == render(REPLY, ansi=True)


def test_code_fences_are_indented_and_markers_dropped():
    text = render("Try:\n```\npip install x\n```\ndone\n", ansi=False)
    assert text == "Try:\n  pip install x\ndone\n"
    ansi = render("```\npip install x\n```\n", ansi=True)
    assert f"  {DIM}pip install x{RESET}\n" == ansi


def test_final_line_without_newline_is_flushed():
    assert render("clause **5.6** applies", ansi=False) == "clause 5.6 applies"


def test_leading_blank_lines_are_skipped():
    assert render("\n\nanswer\n", ansi=False) == "answer\n"
