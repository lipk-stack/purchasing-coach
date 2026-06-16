"""Build a single-file portable app: dist/purchasing-coach.pyz.

The .pyz is a Python zipapp containing the coach package plus its only
runtime dependency (openpyxl, pure Python). On the target machine nothing
needs to be installed — any Python 3.10+ interpreter runs it:

    python purchasing-coach.pyz --guideline guideline.docx

Two build variants are supported:

Standard (default, ~278 KB):
    python scripts/build_portable.py

Embedded (~1.2 GB, includes llama-cpp-python + Qwen2.5-1.5B model):
    python scripts/build_portable.py --with-model

The embedded variant runs a small language model directly in-process,
requiring no external LLM server or API key.

Build (requires pip + network, done by the maintainer, not the end user):

    python scripts/build_portable.py
    python scripts/build_portable.py --with-model
"""

import argparse
import shutil
import subprocess
import sys
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "portable"
DIST = ROOT / "dist"
RUNTIME_DEPS = ["openpyxl"]  # pure-python; pulls in et_xmlfile
EMBEDDED_RUNTIME_DEPS = ["llama-cpp-python"]  # includes huggingface-hub

# Default model for the embedded variant.
EMBEDDED_MODEL_REPO = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
EMBEDDED_MODEL_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"


def build(with_model: bool = False) -> Path:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    # Install runtime dependencies.
    deps = list(RUNTIME_DEPS)
    if with_model:
        deps.extend(EMBEDDED_RUNTIME_DEPS)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet",
         "--target", str(BUILD), *deps],
        check=True,
    )
    shutil.copytree(ROOT / "coach", BUILD / "coach")

    # Optionally bundle the GGUF model into the zipapp.
    if with_model:
        models_dir = BUILD / "coach" / "models"
        models_dir.mkdir(exist_ok=True)
        print(f"Downloading model from {EMBEDDED_MODEL_REPO}...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "huggingface-hub"],
            check=True,
        )
        from huggingface_hub import hf_hub_download

        hf_hub_download(
            repo_id=EMBEDDED_MODEL_REPO,
            filename=EMBEDDED_MODEL_FILE,
            local_dir=str(models_dir),
        )
        print(f"Model saved to {models_dir / EMBEDDED_MODEL_FILE}")

    # Trim what the app doesn't need at runtime.
    for pattern in ("*.dist-info", "__pycache__", "bin"):
        for path in BUILD.rglob(pattern):
            shutil.rmtree(path, ignore_errors=True)

    DIST.mkdir(exist_ok=True)
    suffix = "-embedded" if with_model else ""
    target = DIST / f"purchasing-coach{suffix}.pyz"
    zipapp.create_archive(BUILD, target, main="coach.cli:main",
                          compressed=True)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build portable zipapp")
    parser.add_argument("--with-model", action="store_true",
                        help="Bundle llama-cpp-python + Qwen2.5-1.5B GGUF "
                             "model for fully standalone operation (~1.2 GB)")
    args = parser.parse_args()

    out = build(with_model=args.with_model)
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
