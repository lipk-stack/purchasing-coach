# Changelog

All notable changes to Purchasing Coach are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

Production-quality hardening pass.

### Added
- **Chat answers cite the guideline's own section numbers and support nested
  numbering.** The assistant is now instructed to put the guideline's section /
  clause number (using that guideline's exact numbering, e.g. `4.1`, `5.6`)
  first and in bold next to each point it relies on, and to use a nested,
  indented numbered list when a section has several sub-points so the reply
  mirrors the guideline hierarchy (section `4` → clauses `4.1`, `4.2`). The web
  UI's chat markdown renderer now nests indented bullet/numbered lists inside
  their parent item (an indentation-aware list stack) instead of flattening
  them, carrying each level's source ordinal onto `<li value="N">` so numbering
  is faithful at every depth. Flat lists render exactly as before.
- **Procurement Brief sheet capturing the reverse-prompting interview.** Every
  generated workbook now carries a *Procurement Brief* sheet (placed right after
  *Tender Information*) that records the purchase item, category, and the full
  list of interview questions with the buyer's answers. Because those answers
  drive which guideline sections are pulled into the checklist, this gives the
  reviewer and approver the rationale for the compliance scope on the same
  workbook that's submitted for sign-off — without re-running the interview. The
  sheet is omitted when a workbook is written outside the tender flow, so
  existing callers are unaffected, and it is rebuilt idempotently on re-runs.
- **macOS launcher and a one-zip standalone deployment bundle.** macOS users
  now get a double-clickable `run.command` (the Finder equivalent of Windows'
  `run.bat`; it hands off to `run.sh`). `scripts/build_portable.py --zip`
  assembles a self-contained `dist/purchasing-coach-portable-<variant>.zip`
  containing the app, the sample guideline + template, an end-user `README.md`,
  and a launcher for every OS (`run.command` / `run.sh` / `run.bat`). The shell
  launchers keep their Unix exec bit through the zip, so macOS/Linux recipients
  don't need `chmod`. A prebuilt standard bundle is committed under `dist/`, and
  the portable end-user guide now covers macOS, Linux and Windows.
- **Compliance-rate gauge on the Review & Approval sheet.** The live compliance
  rate now carries a green data bar fixed to a 0%–100% scale, so a reviewer
  sees the submission's standing at a glance and the bar length means the same
  on every workbook. Updates live with the underlying `IFERROR` rate as the
  vendor fills the Vendor Status column.
- **Review & Approval formulas are now verified by computed value, not just
  text.** The summary's live counts (`COUNTIF`/`COUNTIFS`/`COUNTBLANK` over the
  Compliance Tracker, and the divide-by-zero-safe `IFERROR` compliance rate)
  were previously asserted only as formula *strings* — a wrong cell range or an
  off-by-one would have shipped silently, and the headless-LibreOffice render
  check is unavailable in CI. New tests fill the tracker with a known status
  distribution and evaluate the actual generated formulas against the real
  cells, asserting the reviewer sees the correct compliant / non-compliant /
  mandatory-blocker counts and a 0% (not `#DIV/0!`) rate before any vendor
  response.
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

### Security
- **Generated checklist neutralises spreadsheet formula injection (CWE-1236).**
  The `TENDER_CHECKLIST_*.xlsx` is the deliverable submitted to vendors and
  opened by reviewers/approvers, and its data-derived cells carry text the app
  does not control — guideline clauses (which may come from a vendor-supplied
  document), the buyer's tender answers, and the item description. `openpyxl`
  turns any string beginning with `=` into a *live formula*, so a clause like
  `=HYPERLINK("http://evil","click me")` or a DDE payload would execute when the
  reader opens the workbook; a leading `+`, `-`, `@` (or tab/CR) is a trigger too
  once the sheet is exported to CSV. Every untrusted cell — across the Tender
  Information, Compliance Tracker and Procurement Brief sheets, and the
  `/api/export/csv` download — is now neutralised at the write boundary with an
  apostrophe prefix (Excel's "treat as text" marker), so such values render
  literally and never evaluate. The Review & Approval sheet's own built-in
  `COUNTIF`/`IFERROR` summary cells are written separately and stay live;
  benign content is unchanged.
- **Web UI pins the `Host` header to loopback (DNS-rebinding defence).** The
  local server already binds to `127.0.0.1`, but a malicious page open in the
  user's browser could still reach it by rebinding an attacker-controlled
  hostname to `127.0.0.1`. Every request is now rejected with `403` unless its
  `Host` header is a loopback name (`127.0.0.1`, `localhost`, `[::1]`), with the
  port stripped before comparison. Legitimate loopback access is unchanged.
- **`.docx` guideline loader is bounded against zip bombs.** A `.docx` is a zip,
  and its `word/document.xml` was previously decompressed into memory in full —
  a file that is tiny on disk but expands to gigabytes (a zip bomb, or a corrupt
  file with a malformed size header) could exhaust memory. The loader now refuses
  any `word/document.xml` whose text expands past a 64 MiB cap (vast headroom for
  any real guideline) and never holds more than the cap in memory, defending even
  against a header that under-reports the true expanded size. Legitimate
  documents are unaffected and the error message is clear and actionable.
- **LLM backend bounds the response body it buffers into memory.** The
  OpenAI-compatible backend can be pointed at a remote, user-configured endpoint
  (`--base-url`/`--provider` for OpenAI, Groq, Together, Gemini, …), so a hostile
  or malfunctioning server could return a huge `/models` or `/chat/completions`
  body that `json.load` would buffer in full and exhaust memory — the same
  amplification risk the `.docx` loader guards against. The non-streaming reads
  now refuse any body over a 32 MiB cap (vast headroom for real replies, which
  are tens of KB) with a clear error, reading only one byte past the cap to
  detect the overflow. The streaming chat path is naturally incremental and was
  already unaffected. Error bodies were already truncated; this closes the
  matching gap on success bodies.
- **`.xlsx` checklist template is bounded against zip bombs.** An `.xlsx` is a
  zip too, and the user-supplied `--template` was handed straight to
  `openpyxl.load_workbook`, which would decompress it in full — a template tiny
  on disk but huge when expanded (a zip bomb, or a corrupt archive) could
  exhaust memory before any of our code ran. The template is now validated with
  a bounded, chunked read first and refused if its members decompress past a
  128 MiB whole-archive cap (vast headroom for the ~18 KB real template),
  defending even against a header that under-reports the expanded size; corrupt
  archives get a clear, actionable error. This is the symmetric counterpart to
  the `.docx` guideline and LLM-response guards — the last unbounded compressed
  input is now covered.
- **Web chat normalises the untrusted message history at the boundary.** The
  `/api/chat` endpoint passed the client-supplied `messages` list straight to
  the backend, which reads the query as `messages[-1]["content"]`. A
  hand-crafted POST with a non-dict item or a message missing `content` raised a
  `KeyError`/`TypeError` *after* the chunked `200` response had already started
  streaming. The localhost API is treated as an untrusted boundary (the same
  stance as the DNS-rebinding and path-traversal/body-cap defences), so the
  history is now coerced to well-formed `{role, content}` messages — non-dict
  and non-string-content items are dropped and an out-of-set `role` is coerced
  to `user` — and a body with no usable message is rejected with a clean `400`
  before streaming begins. Well-formed histories are unaffected.
- **Web tender finish normalises the untrusted answer list at the boundary.**
  The `/api/tender/finish` endpoint only checked that `answers` was a list, then
  unpacked each item with `for q, a in answers`. A hand-crafted POST with a
  non-pair item (`5`, `"x"`, `[1, 2, 3]`) raised a `TypeError`/`ValueError` that
  surfaced as an opaque `500` leaking the internal message. Mirroring the chat
  history guard, the answers are now coerced to well-formed `(question, answer)`
  string pairs — non-pair items are dropped — so the checklist builds from
  whatever is usable and never crashes on shape. Well-formed answer lists are
  unaffected.
- **`.pdf` guideline loader is bounded against PDF bombs.** A `.pdf`'s page
  content streams are Flate-compressed too, but `_load_pdf` handed the file to
  `pypdf` and concatenated `extract_text()` across every page with **no bound** —
  the one document loader still unguarded after the `.docx`, `.xlsx`, and
  LLM-response defences. A PDF tiny on disk but with heavily compressed streams
  (or an enormous page count) could expand to a huge amount of text and exhaust
  memory. The loader now (a) refuses any file larger than a 64 MiB on-disk cap
  before `pypdf` is even imported, and (b) accumulates extracted text with a
  running 64 MiB cap, refusing the file the moment it crosses the limit —
  defending against a small-on-disk document whose pages expand without bound.
  Both caps are vast headroom for real guideline PDFs (well under a megabyte); a
  corrupt, encrypted, or non-PDF file now gets a clear, actionable error instead
  of an opaque traceback. This closes the **last unbounded document loader**.
- **`.docx` loader refuses XML entity-expansion ("billion laughs") bombs.** The
  byte cap above bounds the decompressed XML *source*, but an entity-expansion
  bomb is tiny at that level and only explodes when the parser expands its
  nested entities — confirmed still vulnerable on a current `expat` (2.6.1), so
  the existing cap did not defend against it. Office Open XML never declares a
  `<!DOCTYPE`, so the loader now refuses any `word/document.xml` that declares
  one (scanning only the prolog, so an escaped `<!DOCTYPE` in body text can't
  cause a false rejection) — stopping the bomb before ElementTree/`expat` expand
  anything. External-entity (XXE) reads were already safe (ElementTree raises on
  an undefined entity and never resolves `SYSTEM` ids). Legitimate documents are
  unaffected.

### Fixed
- **Portable `.pyz` now propagates the CLI's failure exit code.** The standard
  zipapp's generated entry point called `main()` bare and discarded its return
  value, so the `.pyz` exited `0` even when the CLI failed (e.g. a missing or
  unreadable guideline returns `2`) — masking the error from any wrapper script
  or CI that checks `$?`. The build now writes an explicit `__main__.py` that
  does `sys.exit(main())`, mirroring the embedded bootstrap entry, so a fatal
  error surfaces as a non-zero exit. Successful runs still exit `0`.
- **Chat answers number correctly and aren't shown twice.** Two web-UI chat
  rendering bugs: (1) a numbered answer whose items were separated by sub-bullet
  groups rendered *every* top-level item as "1." — each sub-list closed and
  reopened the `<ol>`, restarting it. The renderer now carries the source
  ordinal onto each `<li value="N">`, so 1, 2, 3 … survive the interruption.
  (2) Reopening a **saved session** re-rendered the assistant's markdown as raw
  text (literal `**`, `1.`), so a revisited answer looked like a second,
  unformatted copy; loaded sessions now render coach replies through the same
  markdown path as the live stream. The system prompt also now tells the model
  to give its answer once and not restate it in a second format.
- **Your own `.docx` guideline now produces a checklist instead of an empty
  one.** The clause parser needs numbered headings, but the `.docx` loader only
  recognised them when they were Word *heading styles* with the number typed
  into the text. Real-world guidelines that use **Word auto-numbering** (the
  number is rendered from the document's list settings, so it isn't in the run
  text) or **manually numbered bold lines** (no heading style) produced zero
  clauses — and therefore a silently empty checklist. The loader now (a) promotes
  a short `N.M Title` line to a heading even without a heading style, and
  (b) synthesises stable hierarchical numbers for styled-but-unnumbered
  (auto-numbered) headings, so both shapes yield a usable checklist. A
  document's own explicit numbering is always preferred when present.
- **An unrecognised guideline no longer fails silently.** When no numbered
  sections are detected, the app now shows a clear, actionable heads-up — on the
  terminal, at the start of the tender flow, and as a banner in the browser UI
  (via a new `guideline_notice`) — telling the user their document's structure
  wasn't recognised and how to fix it, instead of producing an empty checklist
  with no explanation.
- **Launchers verify your files before starting.** `run.sh` / `run.bat` (and the
  portable launchers) now check that the resolved guideline and template exist,
  reporting a renamed or wrong-folder file up front with guidance; echo the
  guideline *and* template actually in use so you can confirm your files were
  picked up; fall back to the built-in layout (with a warning) when the template
  is missing; and clear stale Python bytecode caches so nothing from a previous
  run is reused.
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
- **Internal YAGNI cleanup (no behaviour change).** Removed dead code surfaced
  by a whole-repo review: the unused `coach.DEFAULT_MODEL` constant (the Claude
  default lives in the backend), write-only `_guideline_text` fields stored but
  never read by the keyword/BM25/template backends, and a write-only `_answers`
  field in the template backend. The duplicated `_sentence_chunks` streaming
  helper (identical copies in the keyword and BM25 backends) is now a single
  shared `coach.backends.base.sentence_chunks`. No public behaviour changes; the
  full test suite still passes.
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
