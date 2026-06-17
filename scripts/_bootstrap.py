"""Bootstrap for the portable zipapp (.pyz).

Extracts packages that contain native code (numpy, llama-cpp-python) from
the zipapp to a temp directory so C extensions and ctypes DLLs can load
properly, then hands off to the real CLI entry point.

This file is the __main__.py inside the zipapp.  Python's zipapp launcher
executes it automatically when ``python purchasing-coach.pyz`` is run.
"""

import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

# Top-level packages known to contain C extensions or native DLLs.
# These must be extracted from the zipapp so the OS loader can find them.
_NATIVE_PACKAGES = {"numpy", "numpy.libs", "llama_cpp"}


def _find_native_packages(archive_path: Path) -> set[str]:
    """Return top-level package names inside the zip that contain native files."""
    native = set()
    with zipfile.ZipFile(str(archive_path)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            top = name.split("/")[0]
            ext = name.rsplit(".", 1)[-1].lower()
            if ext in ("pyd", "dll", "so", "dylib"):
                native.add(top)
    return native


def _extract_packages(archive_path: Path, extract_dir: Path,
                      packages: set[str]) -> None:
    """Extract entire packages from the zipapp to *extract_dir*."""
    with zipfile.ZipFile(str(archive_path)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            top = name.split("/")[0]
            if top in packages:
                dest = extract_dir / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(info.filename))


def main() -> None:
    archive = Path(sys.argv[0]).resolve()
    if not str(archive).lower().endswith(".pyz"):
        # Running from source, nothing to bootstrap
        from coach.cli import main as cli_main
        sys.exit(cli_main())

    # Determine which packages need extraction (native code can't run from zip).
    pkgs = _find_native_packages(archive) | _NATIVE_PACKAGES

    # Use a stable cache directory so we only extract once per build.
    # Fingerprint with the zipapp's size + mtime to invalidate on rebuild.
    stat = archive.stat()
    fingerprint = f"{stat.st_size}_{int(stat.st_mtime)}"
    cache_dir = Path(tempfile.gettempdir()) / f"purchasing_coach_native_{fingerprint}"

    if not cache_dir.exists():
        # Atomic-ish: extract to a temp dir, then rename
        tmp = cache_dir.with_suffix(".tmp")
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        try:
            _extract_packages(archive, tmp, pkgs)
            tmp.rename(cache_dir)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise

    # Put extracted packages ahead of the zipapp on sys.path so Python
    # finds the real .pyd / .dll files on disk.
    sys.path.insert(0, str(cache_dir))

    # Point llama-cpp-python at the extracted DLLs.
    lib_dir = cache_dir / "llama_cpp" / "lib"
    if lib_dir.is_dir():
        os.environ["LLAMA_CPP_LIB_PATH"] = str(lib_dir)
        if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(lib_dir))

    from coach.cli import main as cli_main
    sys.exit(cli_main())


if __name__ == "__main__":
    main()
