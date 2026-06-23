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


def test_indented_sub_points_nest_inside_their_parent_item():
    # Indented sub-points must render as a nested list inside the parent <li>,
    # with each level's numbering faithful to the source.
    text = "\n".join([
        "1. **Contract requirements (4)**",
        "  1. Stamp duty borne by vendor (4.1)",
        "  2. Define all deliverables (4.1)",
        "2. **Pricing (4.3)**",
        "  - Itemise all costs",
    ])
    html = _run_md(text)
    # A nested <ol> sits inside the first parent item, before that item closes.
    assert '<li value="1"><strong>Contract requirements (4)</strong><ol>' in html
    assert '<ol><li value="1">Stamp duty' in html
    assert '<li value="2">Define all deliverables (4.1)</li></ol></li>' in html
    # The second parent carries a nested bullet list and keeps ordinal 2.
    assert '<li value="2"><strong>Pricing (4.3)</strong><ul>' in html


def test_flat_bullet_list_unchanged():
    assert _run_md("- a\n- b") == "<ul><li>a</li><li>b</li></ul>"


def test_loaded_sessions_render_coach_markdown():
    # A reopened session must render coach replies through md(), not as raw
    # text, so the answer isn't shown a second time without formatting.
    start = PAGE.index("async function loadSession(")
    body = PAGE[start:PAGE.index("async function", start + 1)]
    assert "innerHTML=md(" in body
