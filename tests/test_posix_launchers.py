"""Tests for the macOS/Linux launchers and the standalone deployment zip."""

import shutil
import subprocess
import sys
import zipfile

import pytest

from scripts import build_portable
from tests.conftest import ROOT

PYZ = ROOT / "dist" / "purchasing-coach.pyz"
BUNDLE_ROOT = "purchasing-coach-portable-standard"


# --- Standalone deployment zip (cross-platform: no subprocess) ---------------

def test_make_bundle_has_app_samples_launchers_and_guide(tmp_path, monkeypatch):
    if not PYZ.exists():
        pytest.skip("portable pyz not built")
    monkeypatch.setattr(build_portable, "DIST", tmp_path)
    out = build_portable.make_bundle(PYZ, with_model=False)

    assert out.parent == tmp_path
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        expected = {
            f"{BUNDLE_ROOT}/purchasing-coach.pyz",
            f"{BUNDLE_ROOT}/run.command",          # macOS double-click
            f"{BUNDLE_ROOT}/run.sh",               # Linux / macOS terminal
            f"{BUNDLE_ROOT}/run.bat",              # Windows
            f"{BUNDLE_ROOT}/README.md",            # the user guide
            f"{BUNDLE_ROOT}/samples/XXEON_IT_Procurement_Guideline.docx",
            f"{BUNDLE_ROOT}/samples/TENDER_TEMPLATE.xlsx",
        }
        assert expected <= names

        # The shell launchers must keep their Unix exec bit so a real unzip
        # (macOS Finder / `unzip`) leaves them runnable; run.bat need not.
        modes = {i.filename: (i.external_attr >> 16) & 0o777
                 for i in zf.infolist()}
        assert modes[f"{BUNDLE_ROOT}/run.command"] & 0o111
        assert modes[f"{BUNDLE_ROOT}/run.sh"] & 0o111


# --- Launcher smoke tests (POSIX only: they invoke /bin/sh) ------------------

posix_only = pytest.mark.skipif(sys.platform == "win32",
                                reason="POSIX shell launcher tests")


def _run_sh(args, cwd):
    return subprocess.run(
        ["sh", *args], cwd=cwd, text=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=60, check=False,
    )


@posix_only
def test_root_run_sh_forwards_help():
    result = _run_sh(["./run.sh", "--help"], ROOT)
    assert result.returncode == 0, result.stdout
    assert "usage: purchasing-coach" in result.stdout


@posix_only
def test_root_run_command_delegates_to_run_sh():
    # run.command is the macOS double-click entry; it must hand off to run.sh.
    result = _run_sh(["./run.command", "--help"], ROOT)
    assert result.returncode == 0, result.stdout
    assert "usage: purchasing-coach" in result.stdout


@posix_only
def test_portable_bundle_launcher_finds_pyz_and_forwards_help(tmp_path):
    if not PYZ.exists():
        pytest.skip("portable pyz not built")
    shutil.copy2(ROOT / "scripts" / "portable_run.sh", tmp_path / "run.sh")
    shutil.copy2(PYZ, tmp_path / PYZ.name)
    (tmp_path / "samples").mkdir()
    for fname in ("XXEON_IT_Procurement_Guideline.docx", "TENDER_TEMPLATE.xlsx"):
        shutil.copy2(ROOT / "samples" / fname, tmp_path / "samples" / fname)

    result = _run_sh(["run.sh", "--help"], tmp_path)
    assert result.returncode == 0, result.stdout
    assert "usage: purchasing-coach" in result.stdout
