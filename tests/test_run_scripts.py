"""Smoke tests for platform launch scripts."""

import shutil
import subprocess
import sys

import pytest

from tests.conftest import ROOT


pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="Windows batch launcher tests")


def _run_cmd(command: str, cwd):
    return subprocess.run(
        ["cmd.exe", "/c", command],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )


def test_root_run_bat_parses_and_forwards_help():
    result = _run_cmd("echo. | run.bat --help", ROOT)
    assert result.returncode == 0, result.stdout
    assert "was unexpected at this time" not in result.stdout
    assert "usage: purchasing-coach" in result.stdout


def test_portable_run_bat_parses_and_forwards_help(tmp_path):
    pyz = ROOT / "dist" / "purchasing-coach.pyz"
    if not pyz.exists():
        pytest.skip("portable pyz not built")

    shutil.copy2(ROOT / "scripts" / "portable_run.bat", tmp_path / "run.bat")
    shutil.copy2(pyz, tmp_path / pyz.name)

    result = _run_cmd("echo. | run.bat --help", tmp_path)
    assert result.returncode == 0, result.stdout
    assert "was unexpected at this time" not in result.stdout
    assert "usage: purchasing-coach" in result.stdout
