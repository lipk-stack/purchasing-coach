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
requiring no external LLM server or API key.  Native DLLs are extracted
to a temp directory at startup (via the bundled _bootstrap.py).

Build (requires pip + network, done by the maintainer, not the end user):

    python scripts/build_portable.py
    python scripts/build_portable.py --with-model
"""

import argparse
import shutil
import subprocess
import sys
import zipapp
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "portable"
DIST = ROOT / "dist"
SCRIPTS = ROOT / "scripts"
RUNTIME_DEPS = ["openpyxl"]  # pure-python; pulls in et_xmlfile
EMBEDDED_RUNTIME_DEPS = ["llama-cpp-python==0.3.19"]  # includes huggingface-hub; pinned: 0.3.30 repack crashes on some CPUs

# Pre-built wheel index for llama-cpp-python (avoids compiling from source).
WHEEL_INDEX = "https://abetlen.github.io/llama-cpp-python/whl/cpu"

# Default model for the embedded variant.
EMBEDDED_MODEL_REPO = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
EMBEDDED_MODEL_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"


def build(with_model: bool = False) -> Path:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    # Install runtime dependencies.
    deps = list(RUNTIME_DEPS)
    pip_args = [sys.executable, "-m", "pip", "install", "--quiet",
                "--target", str(BUILD)]
    if with_model:
        deps.extend(EMBEDDED_RUNTIME_DEPS)
        pip_args += ["--extra-index-url", WHEEL_INDEX]
    pip_args += deps
    subprocess.run(pip_args, check=True)

    shutil.copytree(ROOT / "coach", BUILD / "coach")

    # Install the bootstrap module for native DLL extraction (embedded only).
    if with_model:
        shutil.copy2(SCRIPTS / "_bootstrap.py", BUILD / "_bootstrap.py")

    # Optionally bundle the GGUF model into the zipapp.
    if with_model:
        models_dir = BUILD / "coach" / "gguf_models"
        models_dir.mkdir(exist_ok=True)

        # Check for a cached copy before downloading (~1.1 GB).
        model_cache = ROOT / "build" / "model_cache" / EMBEDDED_MODEL_FILE
        if model_cache.is_file():
            print(f"Using cached model: {model_cache}")
            shutil.copy2(model_cache, models_dir / EMBEDDED_MODEL_FILE)
        else:
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
            # Cache the downloaded model for faster rebuilds.
            model_cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(models_dir / EMBEDDED_MODEL_FILE, model_cache)
        print(f"Model saved to {models_dir / EMBEDDED_MODEL_FILE}")

    # Trim what the app doesn't need at runtime.
    for pattern in ("*.dist-info", "__pycache__", "bin"):
        for path in BUILD.rglob(pattern):
            shutil.rmtree(path, ignore_errors=True)
    # Also strip static .lib files (only DLLs needed at runtime).
    for path in BUILD.rglob("*.lib"):
        path.unlink(missing_ok=True)

    DIST.mkdir(exist_ok=True)
    suffix = "-embedded" if with_model else ""
    target = DIST / f"purchasing-coach{suffix}.pyz"

    if with_model:
        # Use the bootstrap entry point that extracts native DLLs before
        # the app starts (llama-cpp-python uses ctypes to load DLLs from
        # a path derived from __file__, which doesn't work inside a zip).
        zipapp.create_archive(BUILD, target, main="_bootstrap:main",
                              compressed=True)
    else:
        zipapp.create_archive(BUILD, target, main="coach.cli:main",
                              compressed=True)
    return target


# Documents that ship in the bundle so it works out of the box.
SAMPLE_FILES = ("XXEON_IT_Procurement_Guideline.docx", "TENDER_TEMPLATE.xlsx")
# Launchers copied into the bundle root, renamed to the names users expect.
# (source name in scripts/, name in the bundle, is-executable)
BUNDLE_LAUNCHERS = (
    ("portable_run.command", "run.command", True),   # macOS double-click
    ("portable_run.sh", "run.sh", True),              # Linux / macOS terminal
    ("portable_run.bat", "run.bat", False),           # Windows double-click
)


def _add_file(zf: zipfile.ZipFile, src: Path, arcname: str,
              executable: bool = False) -> None:
    """Add ``src`` to the zip, preserving a Unix exec bit when requested.

    macOS/Linux launchers must stay executable after unzip, so the Unix mode
    is written into the zip entry's external attributes (the high 16 bits).
    """
    info = zipfile.ZipInfo.from_file(src, arcname)
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if executable else 0o644
    info.external_attr = (mode & 0xFFFF) << 16
    with src.open("rb") as fh:
        zf.writestr(info, fh.read())


def make_bundle(pyz_path: Path, with_model: bool = False) -> Path:
    """Assemble a standalone deployment zip: app + samples + launchers + guide.

    The result unzips to a self-contained folder where an end user double-clicks
    the launcher for their OS (run.command / run.bat / run.sh) and the browser
    chat UI opens — no install beyond Python 3.10+.
    """
    variant = "embedded" if with_model else "standard"
    name = f"purchasing-coach-portable-{variant}"
    DIST.mkdir(exist_ok=True)
    target = DIST / f"{name}.zip"
    target.unlink(missing_ok=True)

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        # The application itself.
        _add_file(zf, pyz_path, f"{name}/{pyz_path.name}")
        # The sample guideline + template so it runs out of the box.
        for fname in SAMPLE_FILES:
            _add_file(zf, ROOT / "samples" / fname, f"{name}/samples/{fname}")
        # Cross-platform launchers (shell ones stay executable).
        for src_name, dst_name, executable in BUNDLE_LAUNCHERS:
            _add_file(zf, SCRIPTS / src_name, f"{name}/{dst_name}", executable)
        # The end-user guide.
        _add_file(zf, SCRIPTS / "portable_README.md", f"{name}/README.md")

    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build portable zipapp")
    parser.add_argument("--with-model", action="store_true",
                        help="Bundle llama-cpp-python + Qwen2.5-1.5B GGUF "
                             "model for fully standalone operation (~1.2 GB)")
    parser.add_argument("--zip", action="store_true",
                        help="Also assemble a standalone deployment zip "
                             "(app + samples + macOS/Windows/Linux launchers "
                             "+ user guide) under dist/")
    args = parser.parse_args()

    out = build(with_model=args.with_model)
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")

    if args.zip:
        bundle = make_bundle(out, with_model=args.with_model)
        print(f"wrote {bundle} ({bundle.stat().st_size / 1024:.0f} KB)")
