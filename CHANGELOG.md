# Changelog

All notable changes to Purchasing Coach are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

Production-quality hardening pass.

### Added
- **Portable embedded bundle** — `python scripts/build_portable.py --with-model`
  now produces a fully self-contained `dist/purchasing-coach-embedded.pyz`
  (~1 GB) with the Qwen2.5-1.5B GGUF model bundled inside. A companion
  `dist/purchasing-coach-portable.zip` packages the `.pyz` with a launcher
  (`run.bat`), sample documents, and an end-user README for true
  extract-and-run distribution.
- **Native DLL bootstrap** (`scripts/_bootstrap.py`) — the embedded zipapp
  extracts numpy and llama-cpp-python to a temp directory at startup, since
  C extensions and ctypes DLLs cannot be loaded from inside a Python zip
  archive. Uses `LLAMA_CPP_LIB_PATH` and `os.add_dll_directory()` for DLL
  resolution. Extraction is cached per build fingerprint.
- `--n-ctx N` CLI flag (default 8192) to control the embedded model's context
  window size. Larger values allow longer guidelines at the cost of more RAM.
- `run.bat` now prefers `purchasing-coach-embedded.pyz` over the standard
  build when both are present (delayed expansion, auto-detect).
- `coach/gguf_models/` package directory for bundled GGUF model files
  (separate from `coach/models.py` which holds dataclasses).
- `scripts/portable_run.bat` and `scripts/portable_README.md` for the
  portable bundle distribution.
- Build script uses `--extra-index-url` for pre-built llama-cpp-python wheels
  (avoids compiling from source), caches the downloaded model in
  `build/model_cache/` for faster rebuilds, and strips `.lib` static files.

### Fixed
- `coach/models/` directory (GGUF storage) shadowed `coach/models.py`
  (dataclasses module) — renamed to `coach/gguf_models/` and updated
  `_BUNDLED_PACKAGE` in `embedded.py`.
- Pinned `llama-cpp-python` to 0.3.19 in the build script; v0.3.30 crashes
  with `STATUS_ILLEGAL_INSTRUCTION` on `q4_K_8x8` tensor repack on some CPUs.
- Default context window increased from 4096 → 8192 tokens so the sample
  guideline (~7376 tokens) fits without immediate truncation.

### Added
- `pyproject.toml` with PEP 621 metadata, optional extras
  (`claude`/`pdf`/`embedded`/`dev`), a `purchasing-coach` console script, and
  tool config for pytest, ruff and coverage.
- GitHub Actions CI (`.github/workflows/ci.yml`): lint + test matrix on
  Python 3.10/3.11/3.12, plus a portable-build smoke-test job.
- Cross-platform run scripts: `run.sh` (Linux/macOS) and an updated `run.bat`
  (Windows).
- `--verbose/-v` flag and a library `coach` logger (NullHandler by default);
  the web server now logs server-side tracebacks.
- Test suite grown to cover the previously-untested retrieval engine,
  keyword/bm25/Claude backends, CLI, and models — overall coverage ~57% → ~84%.

### Fixed
- **Section-dropping bug:** duplicate `"true"` keys in the template backend's
  decision tree silently dropped section 8 (hardware) and section 7 (support)
  from generated checklists.
- Guideline loading now raises clear, actionable errors (corrupt/non-`.docx`,
  missing `word/document.xml`, malformed XML, empty/image-only) and falls back
  through utf-8 → utf-8-sig → cp1252 → latin-1 for Windows-exported text.
- Structured-output parsing tolerates malformed model JSON (a string where a
  list is expected is no longer iterated character-by-character).

### Security
- Web UI: fixed session-id path traversal (ids constrained to a safe charset),
  capped request bodies (413), and added `X-Content-Type-Options: nosniff` and
  `Referrer-Policy: no-referrer`.

## [2.1.0]

### Added
- Embedded small-language-model backend (`--backend embedded`) that runs a GGUF
  model in-process and can be **deployed with the app** (bundled in the zipapp,
  a `models/` folder beside it, or `EMBEDDED_MODEL_DIR`).
- Interview questions tailored to the item being purchased while staying
  grounded in the guideline (hardware vs. software vs. integration topics).
- Review & Approval sheet polish: live compliance-rate %, and conditional
  formatting flagging mandatory non-compliant rows.

## [2.0.0]

### Added
- Multi-backend architecture: LM Studio / Ollama / any OpenAI-compatible server,
  the Claude API, and zero-dependency `keyword`, `bm25` and `template` backends.
- Enterprise web UI (`--web`) with dark mode, streaming, stop button, sessions
  and analytics.

## [1.0.0]

### Added
- Initial release: CLI chat over a purchasing guideline with clause citations,
  a `/tender` interview that writes an Excel compliance checklist from a
  template, and a portable single-file `.pyz` build.
