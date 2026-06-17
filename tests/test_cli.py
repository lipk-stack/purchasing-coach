"""CLI entry point: argument handling and error/exit codes."""

import builtins

from coach.cli import main


def test_missing_guideline_returns_2(tmp_path, capsys):
    rc = main(["--guideline", str(tmp_path / "nope.docx"), "--backend", "keyword"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err.lower()


def test_empty_guideline_returns_2(tmp_path, capsys):
    empty = tmp_path / "empty.txt"
    empty.write_text("   ")
    rc = main(["--guideline", str(empty), "--backend", "keyword"])
    assert rc == 2
    assert "could not load" in capsys.readouterr().err.lower()


def test_interactive_quit_returns_0(samples, monkeypatch, capsys):
    # Feed a single "/quit" to the interactive loop.
    monkeypatch.setattr(builtins, "input", lambda *a, **k: "/quit")
    rc = main(["--guideline", str(samples["guideline"]), "--backend", "keyword"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Purchasing Coach" in out  # banner printed


def test_help_then_quit(samples, monkeypatch, capsys):
    replies = iter(["/help", "/quit"])
    monkeypatch.setattr(builtins, "input", lambda *a, **k: next(replies))
    rc = main(["--guideline", str(samples["guideline"]), "--backend", "keyword"])
    assert rc == 0
    # Banner shown at startup and again for /help.
    assert capsys.readouterr().out.count("Commands:") >= 2


def test_eof_exits_cleanly(samples, monkeypatch):
    def _raise(*a, **k):
        raise EOFError

    monkeypatch.setattr(builtins, "input", _raise)
    rc = main(["--guideline", str(samples["guideline"]), "--backend", "keyword"])
    assert rc == 0


def test_verbose_flag_enables_debug_logging(samples, monkeypatch):
    import logging

    monkeypatch.setattr(builtins, "input", lambda *a, **k: "/quit")
    rc = main(["--guideline", str(samples["guideline"]),
               "--backend", "keyword", "--verbose"])
    assert rc == 0
    assert logging.getLogger("coach").getEffectiveLevel() <= logging.DEBUG
