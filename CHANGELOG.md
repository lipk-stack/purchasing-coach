# Changelog

All notable changes to Purchasing Coach are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

Production-quality hardening pass.

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
