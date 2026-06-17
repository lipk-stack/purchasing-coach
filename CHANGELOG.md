# Changelog

All notable changes to Purchasing Coach are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

Production-quality hardening pass.

### Added
- **SBOM declaration now covered by the checklist (closes a coverage gap).**
  Section 13.1 (the Software Bill of Materials declaration) is a granular,
  mandatory vendor obligation referenced from core section 4.3, but it lives in
  the guideline's "Appendix" — a weak model rarely cites it and it is not a
  cross-cutting core section, so its requirements silently dropped out of
  generated checklists. The interview now asks an answer-driven SBOM question
  (tied to section 13), gated to software-bearing purchases, so a buyer
  procuring software/SaaS is reliably prompted and the four atomic SBOM
  requirements are folded into the compliance tracker — while a pure hardware
  commodity buy is not asked for a Software BOM.

### Fixed
- **Embedded model no longer loops forever.** Small GGUF models (the bundled
  Qwen2.5-1.5B) could stream the same phrase endlessly. Root causes addressed:
  (1) generation now uses anti-repetition sampling (`repeat_penalty` 1.18,
  bounded `temperature`/`top_p`/`top_k`) and explicit ChatML/EOS **stop
  sequences** so the model ends its turn even if the GGUF's template is
  misdetected; (2) a client-side **loop guard** (`_guard_stream`) terminates the
  stream on detected repetition or after a hard character cap, guaranteeing it
  never hangs; (3) the full guideline (~7.4k tokens) was injected into every
  prompt and overflowed the context window — the system prompt is now **trimmed
  to fit** `n_ctx` (`_fit_system`) and the response budget is **clamped** so
  prompt + reply always fit (`_cap_tokens`), fixing the overflow that produced
  degenerate output. The embedded default context window is now 8192.

### Changed
- **The embedded backend is now the default AI backend.** When no LM Studio /
  Ollama server is running and no `ANTHROPIC_API_KEY` is set, auto-detect uses
  the embedded SLM whenever `llama-cpp-python` is installed (resolving a model
  shipped with the app or cached locally, downloading the default only on first
  use), falling back to the keyword backend only when llama-cpp is unavailable.

### Added
- **WCAG 2.2 AA accessibility revamp of the web UI** (adopted internationally
  as ISO/IEC 40500). Full keyboard operation: the sidebar navigation and saved
  sessions are now real `<button>`s (not click-only `<div>`s), every control
  has a visible `:focus-visible` ring, and drag-to-reorder in the checklist has
  an arrow-key equivalent. Screen-reader semantics: a skip-to-content link,
  `<main>`/`<nav>` landmarks, a single `<h1>`, `aria-current` on the active nav
  item, `role="region"` on each view, labelled checklist search/filter
  controls, a status live-region that announces view changes and reorders, and
  text alternatives (`role="img"` + described numbers) for the canvas charts.
  Stateful controls expose state (`aria-pressed` theme toggle, `aria-expanded`
  sidebar toggle). All text now meets **≥4.5:1 contrast in both themes**
  (darkened `--tx-2`, and light-theme `--green`, verified with the WCAG
  formula), with `prefers-contrast` and `forced-colors` support added. The web
  About box and `meta` endpoint now report the real package version.
- **Atomic, per-obligation checklist rows** — a guideline requirement
  paragraph that bundles several distinct vendor obligations in separate
  sentences (e.g. clause 6.1 "Both server and client components must be
  synchronised with the local time server. Web-based systems must support
  Microsoft Edge.") is now split so each obligation is a separately verifiable
  checklist row. Every atomic statement is M/O-classified on its own wording,
  so a "should" sentence bundled into a "must" paragraph is correctly flagged
  recommended rather than inheriting mandatory. Non-normative lead-in or
  trailing context attaches to the nearest obligation (never becomes a row of
  its own), and single-obligation paragraphs are left whole. New
  `atomic_requirements()` / `split_into_sentences()` in `coach/guideline.py`;
  the real XXEON guideline expands from 202 to 212 grounded requirements.
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
