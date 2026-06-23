"""Regression tests for the web UI's client-side markdown rendering.

The renderer lives as JavaScript inside ``webui.PAGE``. The ordered-list
numbering bug (every top-level item rendered as "1." when interrupted by a
sub-bullet group) is verified by executing the real ``md()`` function with
Node when it is available, so the test exercises the shipped code rather than a
Python re-implementation.
"""

import json
import shutil
import subprocess
import textwrap

import pytest

from coach.webui import PAGE


def _extract_md() -> str:
    start = PAGE.index("function md(src){")
    rh = PAGE.index("return html;", start)
    end = PAGE.index("}", rh) + 1
    return PAGE[start:end]


def _run_md(text: str) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to execute the client-side renderer")
    script = _extract_md() + textwrap.dedent(
        """
        const input = JSON.parse(process.argv[1]);
        process.stdout.write(md(input));
        """
    )
    out = subprocess.run(
        [node, "-e", script, json.dumps(text)],
        capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def _ordinals(html: str) -> list[str]:
    import re
    return re.findall(r'<li value="(\d+)"', html)


def test_ordered_list_keeps_counting_across_sub_bullets():
    # The exact shape from the bug report: numbered sections each followed by a
    # bullet group. Previously every <ol> reopened and restarted at 1.
    text = "\n".join([
        "1. **Standard contract terms:**",
        "- The vendor shall bear stamp duty.",
        "- All services must be defined.",
        "2. **Service Level Agreements:**",
        "- KPIs must be specified.",
        "3. **Pricing and payment terms:**",
        "- State all costs.",
    ])
    assert _ordinals(_run_md(text)) == ["1", "2", "3"]


def test_contiguous_ordered_list_still_numbers_correctly():
    text = "1. one\n2. two\n3. three"
    assert _ordinals(_run_md(text)) == ["1", "2", "3"]


def test_loaded_sessions_render_coach_markdown():
    # A reopened session must render coach replies through md(), not as raw
    # text, so the answer isn't shown a second time without formatting.
    start = PAGE.index("async function loadSession(")
    body = PAGE[start:PAGE.index("async function", start + 1)]
    assert "innerHTML=md(" in body
