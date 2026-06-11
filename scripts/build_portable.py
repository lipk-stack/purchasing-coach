"""Build a single-file portable app: dist/purchasing-coach.pyz.

The .pyz is a Python zipapp containing the coach package plus its only
runtime dependency (openpyxl, pure Python). On the target machine nothing
needs to be installed — any Python 3.10+ interpreter runs it:

    python purchasing-coach.pyz --guideline guideline.docx

Build (requires pip + network, done by the maintainer, not the end user):

    python scripts/build_portable.py
"""

import shutil
import subprocess
import sys
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "portable"
DIST = ROOT / "dist"
RUNTIME_DEPS = ["openpyxl"]  # pure-python; pulls in et_xmlfile


def build() -> Path:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet",
         "--target", str(BUILD), *RUNTIME_DEPS],
        check=True,
    )
    shutil.copytree(ROOT / "coach", BUILD / "coach")

    # Trim what the app doesn't need at runtime.
    for pattern in ("*.dist-info", "__pycache__", "bin"):
        for path in BUILD.rglob(pattern):
            shutil.rmtree(path, ignore_errors=True)

    DIST.mkdir(exist_ok=True)
    target = DIST / "purchasing-coach.pyz"
    zipapp.create_archive(BUILD, target, main="coach.cli:main",
                          compressed=True)
    return target


if __name__ == "__main__":
    out = build()
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
