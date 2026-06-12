"""Render model markdown for the terminal: ANSI styling, graceful fallback.

Replies stream in as small text chunks that can split a line (or even a
``**bold**`` marker) anywhere, so rendering is line-buffered: a line is
styled and printed once its newline arrives. Without a TTY (or with
NO_COLOR set) the markdown markers are stripped instead of styled, so
piped output stays clean.
"""

import os
import re
import sys

BOLD = "\033[1m"
DIM = "\033[2m"
UNDERLINE = "\033[4m"
CYAN = "\033[36m"
RESET = "\033[0m"

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_FENCE = re.compile(r"^\s*```")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def ansi_enabled(stream=None) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    stream = stream or sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)())


def render_line(line: str, ansi: bool) -> str:
    """Style one complete markdown line for the terminal."""
    heading = _HEADING.match(line)
    if heading:
        text = _inline(heading.group(2), ansi)
        return f"{BOLD}{UNDERLINE}{text}{RESET}" if ansi else text

    bullet = _BULLET.match(line)
    if bullet:
        indent, text = bullet.group(1), _inline(bullet.group(2), ansi)
        return f"{indent}  • {text}"

    numbered = _NUMBERED.match(line)
    if numbered:
        indent, num, text = numbered.groups()
        return f"{indent}  {num}. {_inline(text, ansi)}"

    return _inline(line, ansi)


def _inline(text: str, ansi: bool) -> str:
    if ansi:
        text = _BOLD.sub(f"{BOLD}\\1{RESET}", text)
        text = _CODE.sub(f"{CYAN}\\1{RESET}", text)
    else:
        text = _BOLD.sub(r"\1", text)
        text = _CODE.sub(r"\1", text)
    return text


class StreamPrinter:
    """Feed streamed chunks; complete lines are rendered and printed."""

    def __init__(self, stream=None, ansi: bool | None = None):
        self.stream = stream or sys.stdout
        self.ansi = ansi_enabled(self.stream) if ansi is None else ansi
        self.buffer = ""
        self.in_fence = False
        self.started = False  # anything printed yet?

    def feed(self, text: str) -> None:
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self._emit(line + "\n")

    def close(self) -> None:
        if self.buffer:
            self._emit(self.buffer)
            self.buffer = ""
        self.stream.flush()

    def _emit(self, line: str) -> None:
        text, end = line.rstrip("\n"), "\n" if line.endswith("\n") else ""
        if _FENCE.match(text):  # drop the ``` line, style its contents
            self.in_fence = not self.in_fence
            return
        if self.in_fence:
            rendered = f"  {DIM}{text}{RESET}" if self.ansi else f"  {text}"
        else:
            rendered = render_line(text, self.ansi)
        if not text.strip() and not self.started:
            return  # skip leading blank lines
        self.started = True
        self.stream.write(rendered + end)
        self.stream.flush()


def enable_windows_ansi() -> None:
    """Switch the legacy Windows console into VT/ANSI mode (no-op elsewhere)."""
    if os.name == "nt":  # pragma: no cover
        os.system("")
