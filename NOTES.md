# Iteration notes & follow-ups

Reference this file at the start of each routine run.

## Iteration 22 — 2026-06-17 (embedded model: stop the infinite loop; make it default)

User: "embedded backend with built-in SLM loops nonstop — fix all issues, make
it the default when no other option is selected, stress test thoroughly, commit
to main." Could not run a live GGUF in-sandbox (no llama-cpp, no model), so
every fix is reasoned from first principles and locked with mocked-Llama tests +
the stress harness.

- **Root causes of the runaway loop (all fixed in `coach/backends/embedded.py`):**
  1. **No sampling constraints / no stop tokens.** `create_chat_completion` was
     called with only messages/max_tokens/stream. Added `repeat_penalty=1.18`,
     `temperature` (0.3 chat / 0.1 JSON), `top_p`/`top_k`, and explicit
     `stop=["<|im_end|>","<|endoftext|>","<|eot_id|>","</s>"]` — a small model
     whose GGUF chat-template/EOS is misdetected otherwise never ends its turn.
  2. **Context overflow.** `Coach` injects the *entire* guideline (~7.4k tokens)
     into every system prompt; with the old `n_ctx=4096` default (and even 8192)
     the prompt overflowed → degenerate, looping output. Added **`_fit_system`**
     (trims the `<guideline>` body to fit the window, keeping structure + a
     truncation marker) and **`_cap_tokens`** (clamps the response budget so
     prompt+reply ≤ `n_ctx`; the checklist call asked for 16000 tokens — bigger
     than the whole window). Default `n_ctx` 4096 → **8192**.
  3. **No client-side stop.** Added **`_guard_stream`** + **`_looping_tail`**: a
     period-agnostic detector that ends the stream when the tail is a block
     repeated ≥3× or output exceeds `_MAX_STREAM_CHARS` (8000). This *guarantees*
     termination regardless of model behaviour, and is the directly-testable fix
     for the reported symptom. (Normal prose / numbered lists don't trip it.)
- **Embedded is now the default AI backend** (`coach/backends/__init__.py`
  auto-detect): after LM Studio → Ollama → Claude(key), it now uses the embedded
  SLM **whenever `llama-cpp-python` is importable** (was: only if a model was
  already cached) — resolving a shipped/cached model or downloading the default
  once, with clear log lines; keyword is the fallback only when llama-cpp is
  absent or construction fails.
- **Tests:** +13 in `tests/test_embedded.py` (anti-loop sampling/stop, runaway
  stream termination, `_looping_tail` true/false cases, length cap, `_fit_system`
  trim, `_cap_tokens` clamp, `complete_json` clamps 16000→n_ctx, auto-default
  selection both ways). **194 unit tests pass.** Stress harness gains an
  *Embedded backend* section that drives the **full chat+interview+checklist
  pipeline on the real 7.4k-token guideline through a deliberately looping fake
  model** and asserts it terminates and still yields a grounded, expanded
  checklist — **all stress tests pass.** ruff clean.
- **Perf caveat / follow-up (unchanged, pre-existing):** feeding the whole
  guideline to a 1.5B model each turn is slow on CPU (prompt eval dominates),
  and trimming at n_ctx=8192 drops ~13% of the guideline tail. The *correct*
  long-term fix is **retrieval-augmented prompting for the embedded model**
  (inject only the clauses relevant to the query, like the keyword/bm25
  backends already index) instead of the full document — this both fixes speed
  and removes the need to trim. Deferred (larger change touching `Coach`); the
  loop/overflow defects the user hit are fully resolved. Users wanting full
  coverage today can pass `--n-ctx 16384`.
- **Drive checked:** guideline + template unchanged (2026-06-10). **main synced.**

## Iteration 21 — 2026-06-17 (UX revamp to WCAG 2.2 AA / international standard)

User: "research design skills … revamp/enhance the UX … to perfect shippable
international standards." The web UI (`coach/webui.py`, single self-contained
HTML page) was already visually strong — design tokens, dark/light themes,
responsive, reduced-motion. The standard that "international" maps to for UX is
**WCAG 2.2 Level AA = ISO/IEC 40500**, so this iteration is a full
accessibility-conformance pass (the highest-value, verifiable UX upgrade), plus
contrast fixes found by measurement.

- **Real defects found & fixed:**
  - **Keyboard inoperable nav.** Sidebar nav items and saved-session rows were
    `<div onclick>` — not focusable, no role, can't activate with Enter/Space
    (WCAG 2.1.1/4.1.2). Converted to real `<button>`s; session row split into a
    focusable open-button + labelled delete-button (no nested buttons).
  - **Contrast failures (measured with the WCAG luminance formula):**
    light-theme `--tx-2` was 3.6–3.8:1 and `--green`-as-text 3.6–3.8:1 (both
    used for ≤12px text → fail AA). Dark `--tx-2` on cards was 4.41:1.
    Retuned: dark `--tx-2 #7882a0→#828ca8` (≥5.0), light `--tx-2
    #7882a0→#646d8c` (≥4.8), light `--green #059669→#047857` (≥5.1). `--tx-3`
    (fails everywhere) is now only on the non-text scrollbar; the 9px progress
    numbers moved to `--tx-2`. **All text ≥4.5:1 in both themes** (re-verified).
    Amber is only ever a background with dark text, so its low text-ratio is
    moot.
  - **No keyboard path for drag-to-reorder** (WCAG 2.1.1). Added `moveRow()` +
    Arrow Up/Down on each row's reorder handle (now a `<button>`), with an
    `aria-live` announcement of the new position.
- **Added (semantics & affordances):** skip-to-content link → `#main`;
  `<div class="main">`→`<main id="main" tabindex="-1">`; one `sr-only` `<h1>`;
  `aria-current="page"` on the active nav (managed in `switchView`, which also
  sets `document.title` and announces the view); `role="region"`+`aria-label`
  per view; `role="search"` + `<label class="sr-only">` for the checklist
  search/section/M-O controls; `role="img"`+`aria-labelledby`/`aria-describedby`
  on both canvas charts with the numbers written into `sr-only` descriptions in
  `drawPie`/`drawBars`; `aria-pressed` (theme) and `aria-expanded` (sidebar)
  kept in sync; visible `:focus-visible` outlines for everything; `<kbd>`-styled
  keyboard hints; `@media(prefers-contrast:more)` and `@media(forced-colors:
  active)` blocks. Decorative glyphs marked `aria-hidden`.
- **Version wiring:** `meta()` now returns the real `coach.__version__` (was
  hardcoded "2.0.0"); the serve banner and the About box (`#aboutVersion`, set
  from `/api/meta`) follow it.
- **Verified:** HTML tag-balance check (no unclosed/mismatched), live server
  smoke (GET / → 200, `/api/meta` version 2.1.0, all landmarks present), and a
  new locking test `test_page_meets_accessibility_contract` (lang, single h1,
  skip link, `<main>`, button nav + `aria-current`, no legacy `<div
  class="nav-item">`, `aria-pressed`/`aria-expanded`, labelled search,
  chart text-alts, `moveRow`/Arrow keys). **185 tests pass, ruff clean.**
- **Follow-up (next UX pass):** true i18n/localization (string externalisation,
  RTL) is not done — the UI is English-only; that's the other reading of
  "international" and is the natural next step if the user wants multi-language.
  Also consider: a contenteditable undo, focus-trap for the mobile sidebar
  overlay, and an automated axe-core/Pa11y check in CI (needs a headless
  browser — not available in this sandbox).
- **Drive checked:** guideline + template unchanged (2026-06-10). **main synced.**

## Iteration 20 — 2026-06-17 (granular: atomic per-obligation checklist rows)

Resumed after the user merged their own work to main (`568e632` "Add portable
embedded bundle with native DLL bootstrap" — author lipk-stack). Fast-forwarded
the dev branch to `origin/main` first (clean ff, no conflicts), re-ran the
suite (**180 passing, ruff clean, 86% cov**), then picked the next enhancement
aimed squarely at the user's core ask: *granular* clauses "derived from the
guideline in detail".

- **Gap found (real, on the genuine guideline):** `parse_clause_requirements`
  mapped **one normative paragraph → one checklist row**, but 28 of the 202
  parsed paragraphs bundle **several distinct vendor obligations in separate
  sentences** — e.g. clause 6.1 "Both server and client components must be
  synchronised with the local time server. Web-based systems must support
  Microsoft Edge." was a *single* row, so the vendor couldn't mark Edge
  compliant but time-sync non-compliant. Not granular enough for a sign-off
  tracker.
- **Fix — atomic splitting (`coach/guideline.py`):** new
  **`split_into_sentences()`** (boundary regex with abbreviation + decimal
  re-merge so "e.g." and clause numbers like "5.6" don't false-split) and
  **`atomic_requirements()`**. The latter splits a paragraph so **every
  normative sentence anchors its own row**; non-normative sentences (lead-in or
  trailing context) attach to the nearest preceding anchor (leading prose → the
  first anchor) so no descriptive sentence becomes a bogus row and no
  obligation loses context. A paragraph with ≤1 normative sentence is returned
  **unchanged** (preserves context — e.g. the descriptive 3.1 stays one row).
  `parse_clause_requirements` now emits one row per atomic statement and
  **M/O-classifies each on its own wording** (a "should" split out of a "must"
  paragraph is now correctly **O**, not inherited **M**).
- **Impact on the real guideline:** 202 → **212** grounded requirement rows
  (+10), each genuinely distinct. Verified end-to-end: full hardware tender
  expands to 205 rows; wrote a real checklist against `TENDER_TEMPLATE.xlsx` →
  3 sheets, 207 tracker rows, reloads cleanly in openpyxl (table + dropdowns +
  review sheet intact).
- Tests: **184 passing** (+4 in `test_guideline.py`: sentence-split keeps
  abbreviations/decimals whole; compound paragraph → per-obligation rows;
  context attaches to nearest obligation / single-obligation unchanged;
  per-statement M/O). ruff clean. Existing tests unaffected (their fixtures are
  single-sentence paragraphs → returned unchanged).
- **Drive checked:** guideline + template both still `modifiedTime
  2026-06-10T13:05:11Z` — no sample refresh needed.
- **main synced** after the green run.
- Follow-up 1 (live-LLM quality review) and the iter-19 embedded follow-ups
  (model quality/perf, embedded Python, GPU, CI for the heavy build,
  cross-platform DLL bootstrap) remain open — all blocked on resources absent
  from this sandbox.

## Iteration 19 — 2026-06-17 (portable embedded bundle: out-of-the-box delivery)

Built and verified a fully portable embedded distribution that runs without
LM Studio, Ollama, API keys, or model downloads — the user only needs
Python 3.10+ on PATH.

### What was done

1. **Native DLL bootstrap** (`scripts/_bootstrap.py`): the embedded zipapp
   can't load C extensions (.pyd) or ctypes DLLs from inside a zip, so a
   bootstrap module extracts numpy and llama-cpp-python to a temp directory
   before any imports. Uses `LLAMA_CPP_LIB_PATH` + `os.add_dll_directory()`
   for DLL resolution. Extraction is cached per zipapp fingerprint (size+mtime).

2. **Build pipeline fixes** (`scripts/build_portable.py --with-model`):
   - Added `--extra-index-url` for pre-built llama-cpp-python wheels (PyPI
     only has source tarballs that need a C compiler).
   - Pinned llama-cpp-python to 0.3.19 — v0.3.30 crashes with
     `STATUS_ILLEGAL_INSTRUCTION` during `q4_K_8x8` tensor repack on some
     CPUs (including i5-13450HX).
   - Renamed bundled model package from `coach/models/` to `coach/gguf_models/`
     — the directory was shadowing `coach/models.py` (dataclasses), breaking
     `RequirementRow` imports.
   - Model downloads are cached in `build/model_cache/` for fast rebuilds.
   - Static `.lib` files stripped from the zipapp.

3. **Context window**: increased default from 4096 → 8192 tokens. Added
   `--n-ctx N` CLI flag threaded through `get_backend()` → `EmbeddedBackend`.

4. **Launcher updates**: `run.bat` now prefers `purchasing-coach-embedded.pyz`
   (delayed expansion). New `scripts/portable_run.bat` defaults to
   `--backend embedded` so the bundled model is always used.

5. **Portable bundle**: `dist/purchasing-coach-portable.zip` (~1 GB) packages
   the embedded `.pyz` + `run.bat` + `samples/` + `README.md`. Tested
   end-to-end from an arbitrary extracted directory — model loads, generates
   responses, `/quit` exits cleanly.

### Verified

- 180 tests pass (no regressions from the `n_ctx` / `gguf_models` changes).
- Embedded zipapp starts, loads the bundled Qwen2.5-1.5B, generates a
  response to a guideline question, and exits on `/quit`.
- Portable bundle works from an arbitrary directory (tested in `%TEMP%`).

### Follow-ups for the next iteration

- **Performance**: the 1.5B model with 8192 context is slow on CPU (~24 tok/s
  prompt eval, ~10 tok/s generation). Consider streaming-first UI, or
  document `--n-ctx 4096` for shorter guidelines to speed things up.
- **Model quality**: Qwen2.5-1.5B gives generic answers for precise clause
  lookups. A 7B Q4 model (~4.7 GB) would fit in 8 GB RAM and give much better
  clause selection — consider offering it as an optional upgrade.
- **Embedded Python**: for truly zero-dependency delivery, bundle the Python
  embeddable distribution (~25 MB) inside the portable zip. This would
  eliminate the Python-on-PATH requirement entirely.
- **GPU support**: the CPU-only wheel is used. For machines with NVIDIA GPUs,
  a CUDA-enabled wheel would dramatically speed up inference.
- **CI for embedded build**: the `--with-model` build is too heavy for GitHub
  Actions (1.1 GB model download). Consider a separate release workflow or
  artifact caching.
- **Cross-platform testing**: the bootstrap was developed and tested on
  Windows. Verify the DLL extraction logic also works on Linux (.so) and
  macOS (.dylib).

## Iteration 18 — 2026-06-17 (loop round 2: another 10 production passes)

Continued the production-quality loop (scheduling tools still unavailable, so
run inline). Running tally appended per pass:

- **Pass 11:** TemplateBackend (decision-tree) coverage 58% → **84%**.
  `test_template_backend.py` (+13): scenario detection, condition evaluation
  (`true`/`==`/`!=`/`OR`/fuzzy), interview plan, always+conditional section
  selection, headings-only one-row-per-clause path, synthetic-root path with no
  loaded guideline, unknown-schema, and chat composition. Total **84% → 86%**,
  180 tests, ruff clean (tests-only).

## Iteration 17 — 2026-06-17 (loop pass 1/10: production-quality foundation)

User started a `/loop` to "enhance everything to production quality, at least 10
times". This is pass 1: packaging, CI, linting — and a real bug the linter
surfaced on its first run.

- **Real bug fixed — duplicate `"true"` dict key dropped a whole section**
  (`coach/templates/scenarios.py`). The `hardware` scenario's
  `conditional_sections` had `"true": ["8"]` **and** `"true": ["12"]`; a dict
  literal keeps only the last, so **section 8 (Hardware Requirements) was
  silently dropped from every hardware tender** built by the template backend.
  Same for `software`: `"true": ["7"]` (Support) was lost to `"true": ["12"]`.
  Merged to `["8","12"]` / `["7","12"]`. New `tests/test_scenarios.py` (4 tests)
  locks both the data and the behaviour (a hardware item now yields section 8,
  a software item section 7). Caught by ruff `F601`.
- **Packaging — `pyproject.toml`** (PEP 621): metadata, classifiers,
  `requires-python>=3.10`, runtime dep `openpyxl` only, optional extras
  (`claude`/`pdf`/`embedded`/`dev`), a **`purchasing-coach` console script**
  (`coach.cli:main`), dynamic version from `coach.__version__`, and tool config
  for **pytest** and **ruff**. `pip install -e ".[dev]"` verified; console
  script runs.
- **pytest scoping fix:** `testpaths=["tests"]` — previously `pytest` from the
  repo root also swept in `stress_test.py` (matches the `*_test.py` glob), so
  every run silently executed the manual stress harness and inflated the count
  (~122 vs the real 107). Now the suite is exactly the 107 real tests; the
  harness still runs manually via `python stress_test.py`.
- **Linting — ruff**, config in `pyproject.toml` (`E4/E7/E9/F/W`; `B`/`UP`
  deferred — see follow-up 13). Fixed all findings: removed unused imports,
  dropped a redundant local re-import + added `__all__` in
  `coach/backends/__init__.py`, hoisted a mid-file `import re` in
  `retrieval/index.py`, removed empty f-strings, cleaned unused test vars.
  `ruff check .` is clean.
- **CI — `.github/workflows/ci.yml`:** on push (`main`, `claude/**`) and PRs —
  a **test matrix on Python 3.10/3.11/3.12** (`ruff check .` + `pytest`) and a
  separate **build job** that builds `dist/purchasing-coach.pyz`, smoke-tests it
  (`/quit` against the keyword backend), and uploads it as an artifact.
  *Untested live here (no GitHub Actions runner in-sandbox) — verify the first
  run goes green; see follow-up 13.*
- **.pyz rebuilt (326 KB)** with the section-8 fix bundled (verified).
  `requirements-dev.txt` gains `ruff`; README Development section updated
  (`pip install -e ".[dev]"`, `ruff check .`, CI note); `.gitignore` gains
  `*.egg-info/`.
- Tests: **107 passing** (the real suite; +4 scenarios), ruff clean.
- **Drive checked:** guideline + template both still `modifiedTime
  2026-06-10T13:05:11Z` — no sample refresh needed.
- **main synced** after the green run (fetch first per iter 15).

## Iteration 16 — 2026-06-17

User request: "add the option to use an embedded SLM that deploys together with
the application and is portable; make the interview questions relevant to the
items/services being purchased, with reference from the guideline." Two distinct
gaps, both closed deterministically (no live LLM needed).

**Part A — item-relevant, guideline-grounded interview questions.**
- The portable `keyword`/`bm25` planners were generating the interview from
  `coverage_questions(clauses)` and **ignoring the item entirely** (the
  `_item_desc` they parsed was unused) — every purchase got the identical full
  question list.
- **`coach/guideline.py` — new `relevant_coverage_questions(clauses, item)`**
  (plus `ITEM_TYPE_ROOTS = {6,8,9}`, `_ITEM_SIGNALS`, `_item_relevance`). Keeps
  the same guideline-grounded questions, but the **item-type-specific** topics
  (integration 6, hardware 8, software 9) are kept only when the item points to
  them — "20 Dell laptops" → hardware asked, software/integration dropped;
  "Microsoft 365 subscription" → software asked, hardware dropped. Cross-cutting
  topics (contract 4, data/security 5, support 7, cloud 11, financial 10,
  post-impl 12, cyber 11.3) are always asked. **Vague item → keep all** (the
  old broad, compliance-safe behaviour) so the interview never under-asks.
  Relevant item-type questions lead the list. `coverage_questions` kept
  unchanged for callers/tests that don't have an item.
- **Wired into all planners:** `keyword.py`, `bm25.py` (now use the item), and
  the LLM path `coach/llm.py` (`plan_interview` → `_ensure_coverage(plan, item)`
  merges the *relevant* coverage questions the model didn't already ask).
- **Verified on the genuine guideline via the keyword backend:** laptops → 10
  Qs with hardware asked / software not; M365 SaaS → 10 Qs with software asked /
  hardware not. The dropped sections aren't force-added either (the
  `sections_from_answers` safety net is answer-driven, so not asking == not
  adding — which is correct for the wrong item type).

**Part B — embedded SLM deployed *with* the app (real portability).**
- **Gap found:** `scripts/build_portable.py --with-model` bundles the GGUF into
  `coach/models/` inside the zipapp, but `EmbeddedBackend._resolve_model` only
  checked an explicit path → `EMBEDDED_MODEL_PATH` → home cache → download — it
  **never looked at the bundled location**, so a "deployed-together" model was
  never found.
- **`coach/backends/embedded.py`:** resolution now inserts a bundled/adjacent
  step (new `_bundled_model`, `_adjacent_model_dirs`, `_adjacent_gguf`,
  `_packaged_gguf_name`): a `models/` folder (or loose `.gguf`) **beside the
  `.pyz`/executable**, an `EMBEDDED_MODEL_DIR` override, or a `models/` folder
  next to the package — checked before the cache/download. A model bundled
  *inside* the zipapp can't be mmap'd from the archive, so it's **extracted once
  into the cache** via `importlib.resources.as_file` then reused. `has_cached_model`
  now also reports a shipped model, so **auto-detect picks the embedded backend**
  when a model ships with the app. CLI `--model-path` help + README updated to
  document the three deploy-together options and the keyword/bm25/template
  zero-dependency fallback.
- Note: the embedded backend still needs `llama-cpp-python` (a compiled dep) —
  that's inherent to running a GGUF in-process and is the documented optional
  install; the standard `.pyz` stays pure-Python. The `--with-model` build
  produces `purchasing-coach-embedded.pyz` (~1.2 GB) for the all-in-one case.

- Tests: **122 passing** (+7: 4 item-relevance in `test_guideline.py`; 3
  bundled/adjacent + packaged-extraction in `test_embedded.py`). **.pyz rebuilt
  (325 KB)** and confirmed to bundle `relevant_coverage_questions` +
  `_bundled_model`/`_adjacent_model_dirs`; smoke-ran the bundled app.
- **Drive checked:** guideline + template both still `modifiedTime
  2026-06-10T13:05:11Z` — no sample refresh needed.
- **Live LLM / live embedded model still untested in-sandbox** (no GGUF, no
  llama-cpp-python, no API key, local servers unreachable). All of this layer is
  deterministic and verified on the real guideline; follow-up 1's live quality
  review stays open. New follow-up 12 added for the embedded variant.
- **main synced** after the green run (verify `git fetch` first per iter 15).

**Docs/UX follow-on (same iteration, user request):** expanded the README with a
full **Models & backends** reference — a table of all eight `--backend` options
(auto/lmstudio/ollama/claude/embedded/keyword/bm25/template) with model,
dependency, network and use-case columns; OpenAI-compatible provider presets; a
"choosing a model" guide; the embedded deploy-with-app resolution order; and
full CLI-options + environment-variable tables. Added a cross-platform **run
script** for easy startup: new `run.sh` (Linux/macOS) and a rewritten `run.bat`
(Windows) — both default to the browser UI with the bundled samples, forward any
extra flags to the app, honour `GUIDELINE`/`TEMPLATE` env vars, and fall back to
`python -m coach` if the `.pyz` is absent. Fixed the stale `coach/backends.py`
reference (now the `coach/backends/` package). No code change — 122 tests still
green; `.pyz` unchanged.

## Iteration 15 — 2026-06-16

Polished the Review & Approval sheet (follow-up 11) so the reviewer's go/no-go
read is immediate, and reconciled the routine state with the user's own overhaul
commits.

- **`coach/excel.py` — `_add_review_sheet` enhancements:**
  - **Live compliance-rate row** — `Compliance rate (of applicable)` =
    `IFERROR(COUNTIF(status,"Compliant")/(total-COUNTIF(status,"Not Applicable")),0)`,
    formatted `0.0%`. Excludes Not Applicable so an N/A-heavy bid isn't
    penalised, and is divide-by-zero safe before the vendor fills anything in.
  - **Conditional formatting on the *Mandatory non-compliant (review blocker)*
    cell** — red (`FFC7CE`/bold `9C0006`) when `>0`, green (`C6EFCE`/`006100`)
    at `0`, so the go/no-go figure is unmissable and updates live with its
    COUNTIFS as the vendor populates the tracker.
- **Web finish note (`coach/webui.py`)** now reports the mandatory count
  (deterministic, known at finish) — `N requirements (M mandatory)` — and
  mentions the Review & Approval sheet tallies compliance rate + mandatory
  non-compliant rows for sign-off. `tender_finish` returns a new `mandatory`
  field. CLI note (`coach/tender.py`) mentions the compliance rate + red flag.
- **Verified end-to-end on the genuine `TENDER_TEMPLATE.xlsx`** (59-row run):
  three sheets, rate formula points at `F3:F61` over 59 rows, conditional
  formatting lands on the blocker cell, `TenderRequirements` table still
  extends (`A2:G61`), workbook reloads cleanly in openpyxl — table + tracker
  dropdown + freeze + review dropdown + new conditional formatting all coexist,
  no corruption. **.pyz rebuilt (323 KB)** and confirmed to bundle the new
  logic. README updated.
- Tests: **115 passing** (+1: `test_review_sheet_compliance_rate_and_blocker_formatting`
  asserts the rate formula/percent format and the red/green CF rules on the
  real template).
- **Drive checked:** guideline (`XXEON_IT_Procurement_Guideline.docx`) and
  template (`TENDER_TEMPLATE.xlsx`) both still `modifiedTime 2026-06-10T13:05:11Z`
  (verified this run) — no sample refresh needed.
- **Reconciliation note:** the two most recent commits (`e53f005` "Major
  overhaul", `22fc212` "Add embedded SLM backend") are the **user's own** work
  (author lipk-stack, 2026-06-16) and pre-date this NOTES entry — they
  restructured `coach/backends.py` into the `coach/backends/` package
  (embedded/claude_api/openai_compat/bm25/keyword/template). Earlier NOTES that
  reference `coach/backends.py` as a single file are stale w.r.t. that layout;
  the code is what's authoritative. All 115 tests (incl. the user's 19 embedded
  tests) pass on top of this iteration's changes.
- **main sync (follow-up 8):** at the start of this run the *local* tracking
  refs looked stale (local `main`/`origin/main` showed the initial commit
  `95b5f6b`), but the real `origin/main` was at the user's latest commit
  `22fc212` (the overhaul/embedded-SLM work had been pushed to main already).
  Fast-forwarded main to the dev branch and pushed: `22fc212..b064cd2`. After
  the push `origin/main == origin/claude/nice-ride-jhcjqj` (verified `0 0`).
  Note for next run: don't trust a stale local `origin/main` ref — `git fetch`
  first before judging the gap.
- **Live LLM still unavailable** in this sandbox (no API key; local
  LM Studio/Ollama ports not reachable) — this layer is deterministic and
  verified on the real template, so it's valuable regardless of backend;
  follow-up 1's live quality review stays open.

## Iteration 14 — 2026-06-15

Closed the review/approval reporting gap: the workbook the vendor populates and
submits is now self-scoring for the reviewer (builds on iter 13's Vendor Status
dropdown — that gave the reviewer a consistent vocabulary; this turns it into an
at-a-glance decision).

- **`coach/excel.py` — new `Review & Approval` sheet (`_add_review_sheet`).**
  Always added (genuine template and the no-template path) whenever the tracker
  has data rows. Two blocks:
  - **Compliance Summary** — *live* formulas over the Compliance Tracker's
    Vendor Status column (`COUNTIF`/`COUNTBLANK`/`COUNTIFS`), so the counts
    update the moment the vendor fills the dropdown: total, Compliant /
    Partially / Non-Compliant / Not Applicable, Awaiting vendor response,
    Mandatory (M) total, and **Mandatory non-compliant (review blocker)** — the
    go/no-go figure (a `COUNTIFS` of M/O="M" AND status="Non-Compliant"). Sheet
    name is quoted (`'Compliance Tracker'!F3:F204`) and the range is the data
    rows only (`header_row+1..last_row`).
  - **Reviewer Sign-off** — Reviewed By / Review Date / Approval Decision /
    Approved By / Approval Date / Comments-Conditions, value cells shaded. The
    Approval Decision cell is a data-validation **list** over the fixed
    `REVIEW_DECISION_OPTIONS` = *Approved / Approved with Conditions / Rejected /
    Resubmission Required* — so the outcome is unambiguous and filterable.
  - `write_checklist` now threads `(header_row, last_row, col)` out of
    `_fill_tracker_sheet` into the review builder. Idempotent: deletes any
    existing `Review & Approval` sheet before rebuilding.
- **Verified end-to-end on the genuine `TENDER_TEMPLATE.xlsx`** with a 202-row
  checklist: three sheets present, summary formulas point at `F3:F204` /
  `E3:E204`, the `TenderRequirements` table still extends to `A2:G204`, the
  decision dropdown lands on the right cell and the workbook reloads cleanly in
  openpyxl (table + tracker validation + freeze + the new review-sheet
  validation all coexist — no corruption). Same confirmed from the **bundled
  .pyz** (280 KB, rebuilt and verified to contain `_add_review_sheet`).
- **Surfaced to the user:** CLI finish note (`coach/tender.py`) and web finish
  note (`coach/webui.py`) now mention the Review & Approval sheet tallying the
  submission for sign-off. README updated (feature list + the no-template note).
- Tests: **69 passing** (+2: review-sheet summary formulas + sign-off decision
  vocabulary on the real template, and review sheet on the no-template path in
  `test_excel.py`).
- **Drive checked:** guideline (`XXEON_IT_Procurement_Guideline.docx`) and
  template (`TENDER_TEMPLATE.xlsx`) both still `modifiedTime 2026-06-10T13:05:11Z`
  (verified this run) — no sample refresh needed.
- **Live LLM still unavailable** in this sandbox (no API key; ports 1234/11434
  closed — checked again). This layer is deterministic and verified on the real
  template, so it's valuable regardless of backend; follow-up 1's live quality
  review stays open.
- **main synced** after the green run (standing instruction).

## Iteration 13 — 2026-06-14

Made the Excel deliverable itself review-/approval-ready (the checklist is
"populated by the vendor and submitted for review and approval" — this
iteration improves that last mile, which was untouched since the granularity
work):

- **`coach/excel.py` — Vendor Status dropdown.** The `Vendor Status` column is
  now a data-validation **list** over every written data row, constrained to a
  fixed vocabulary `VENDOR_STATUS_OPTIONS` = *Compliant / Partially Compliant /
  Non-Compliant / Not Applicable* (`allow_blank=True`, dropdown shown, with an
  error + input prompt). Vendors pick rather than free-type, so a 150–200-row
  submission stays consistent and the reviewer can filter/score against a known
  set. Free-text justification still lives in the adjacent `Vendor Remarks`
  column. No-op when the column or data rows are absent (`_add_status_dropdown`).
- **Frozen header.** `freeze_panes` is set just below the tracker header so the
  title + column headers stay visible while scrolling a long granular checklist.
- **Coexists with the real template's Excel table.** Verified end-to-end on the
  genuine `TENDER_TEMPLATE.xlsx` with a 202-row checklist (all parsed atomic
  requirements): the `TenderRequirements` table extends to `A2:G204`, the
  validation covers `F3:F204`, freeze is `A3`, and the workbook reloads cleanly
  in openpyxl — no corruption from table + validation + freeze together. Same
  result confirmed from the **bundled .pyz** (not just the source tree).
- **Surfaced to the user:** CLI finish note (`coach/tender.py`) and web finish
  note (`coach/webui.py`) now tell the user vendors pick a Vendor Status from
  the dropdown and explain in Vendor Remarks. README updated.
- Tests: **67 passing** (+2: dropdown vocabulary + sqref + freeze on the real
  template, and dropdown present on the no-template path in `test_excel.py`).
  .pyz rebuilt (279 KB) and confirmed to bundle + run the new logic.
- **Drive checked:** guideline (`XXEON_IT_Procurement_Guideline.docx`) and
  template (`TENDER_TEMPLATE.xlsx`) both still `modifiedTime 2026-06-10T13:05:11Z`
  (verified this run) — no sample refresh needed.
- **Live LLM still unavailable** in this sandbox (no API key; LM Studio/Ollama
  localhost not reachable from the container). This layer is deterministic and
  verified on the real template, so it's valuable regardless of backend;
  follow-up 1's live quality review stays open.
- **main synced** after the green run (standing instruction).

## Iteration 12 — 2026-06-14

Second user run: LM Studio still failed, but the cause moved server-side and
the app got hardened against it:

- **Symptom (LM Studio server log):** `clip_init: failed to load model
  '…mmproj-gemma-4-12B-it-QAT-BF16.gguf': load_hparams: unknown projector type:
  gemma4uv` → `Failed to load model`. `gemma-4-12b-it-QAT` is a **multimodal
  (vision) model**; the user's llama.cpp runtime is too old to load its vision
  projector, so LM Studio can't load it at all. **Not an app bug** — no code can
  load an unloadable model.
- **App hardening (`coach/backends.py`):**
  - `_lmstudio_model` now **ranks** candidates `(not_loaded, is_vision)` instead
    of taking the first: already-loaded beats not-loaded, and a plain text
    `llm` beats a vision `vlm`. So when a text model is available the app skips
    fragile vision models like gemma-4-12b entirely — this app never uses
    vision. A loaded vlm still beats an unloaded llm (it already works).
  - The "Failed to load" hint now also names the likely cause (new/multimodal
    model vs. an old runtime) and suggests updating LM Studio's runtime or
    picking a text model — the memory-only wording was off-target for this case.
- **User guidance given:** load a text/instruct model (Qwen2.5-7B-Instruct,
  Llama-3.1-8B-Instruct) — the app auto-picks it; or update LM Studio's
  runtime to one that supports gemma-4 vision; or `--llm-model` to force a
  specific id.
- Tests: **65 passing** (+2: prefer-text-over-vision, loaded-vision-beats-
  unloaded-text in `test_backends.py`). .pyz rebuilt (278 KB), fix confirmed
  bundled.
- **main synced** after the green run.

## Iteration 11 — 2026-06-14

Bug fix from the **first real user run against LM Studio** (closes the
practical side of follow-ups 1/10 — the app finally ran against the user's own
local model and surfaced a model-selection bug):

- **Symptom:** chatting returned `http://localhost:1234/v1/chat/completions
  returned 400: … "Failed to load model 'google/gemma-4-12b-qat'"`. The user
  had a *different* model loaded; the app picked an unloaded one.
- **Root cause:** LM Studio's OpenAI-compatible `/v1/models` lists **every
  downloaded model**, not just the loaded one(s). `_first_model` took
  `models[0]`, so it sent a model id LM Studio then tried to just-in-time load
  — and that one failed (memory/incompatible runtime), even though a usable
  model was already loaded.
- **Fix (`coach/backends.py`):** new `_lmstudio_model()` queries LM Studio's
  **native** `/api/v0/models` endpoint (host root, not `/v1`), which reports
  each model's `state` and `type`. `_first_model` now prefers an
  already-**loaded** chat model (`state == "loaded"`, `type` llm/vlm), so we
  never ask the server to load a model that might fail, and we skip
  **embeddings** models that can't chat. Returns `None` on servers without that
  endpoint (Ollama, plain OpenAI-compatible) → graceful fallback to
  `/v1/models[0]`, unchanged behaviour there.
- **Also:** when a chat request still 400s with a "load model" error, the
  `BackendError` now appends an actionable hint (load a model / free memory /
  pass `--llm-model`) instead of just the raw server JSON.
- Tests: **63 passing** (+2 net: prefer-loaded, skip-embeddings, and
  no-native-API fallback in `test_backends.py`; `test_local_server.py` mock now
  404s `/api/v0/models` to exercise the fallback path cleanly). .pyz rebuilt
  (278 KB) and confirmed to bundle the fix.
- **main synced** after the green run (standing instruction).
- **Follow-up:** the user should re-run chat — it will now pick whatever model
  they have loaded in LM Studio. If they specifically want `gemma-4-12b-qat`,
  it needs to load successfully in LM Studio first (it was failing to load
  server-side; likely RAM/VRAM or runtime). `--llm-model` still forces a
  specific id.

## Iteration 10 — 2026-06-14

Closed the last reverse-prompting coverage gap so the interview now covers
*every* normative section of the guideline (user request: "ask additional
questions as needed to cover the content of the guideline fully"):

- **The gap:** sections **10 Financial Considerations** and **12
  Post-Implementation** were the only normative top-level sections with **no
  coverage question** — every other section (4–9, 11) already had one. They are
  genuine vendor deliverables (10: five-year TCO, ROI projections, payment
  schedules; 12: performance reviews at 3/6/12 months, user-feedback collection,
  continuous-improvement roadmap), so a buyer interview that never asked about
  them could silently drop ~23 vendor obligations on a model that didn't pick
  10/12.
- **`coach/guideline.py` — two new `_COVERAGE` entries** with `include_root`
  `"10"` and `"12"`, wired exactly like the existing item-specific topics
  (6/7/8/9): an affirmative interview answer folds the whole section's atomic
  requirements into the checklist deterministically; a clear "no"/blank keeps it
  out. Kept them **answer-driven rather than in `CORE_SECTIONS`** (the
  conservative call — post-implementation reviews and TCO analyses are
  near-universal but not strictly every-procurement like contract/security/
  compliance; consistent with how 6/7/8/9 are handled). `sections_from_answers`
  docstring updated to list the full mapping (6/7/8/9/10/12).
- **Verified on the genuine guideline:** `coverage_questions` now returns **12**
  questions and covers TCO + post-implementation; affirming both pulls in
  section 10 (**13 rows**) and section 12 (**10 rows**) through the full
  `ensure_core_sections` fold-in; declining both keeps them out.
- **`README.md`** "every major section" list + the answer-driven paragraph now
  mention financial/TCO and post-implementation (sections 10, 12).
- **Drive checked:** guideline (`XXEON_IT_Procurement_Guideline.docx`) and
  template (`TENDER_TEMPLATE.xlsx`) both still `modifiedTime
  2026-06-10T13:05:11Z` (verified this run) — no sample refresh needed.
- **Live LLM still unavailable** (no API key, ports 1234/11434 closed — checked
  again). This layer is deterministic and verified on the real guideline, so
  it's valuable regardless of backend; follow-up 1's live *quality* review stays
  open but the unbacked-section risk it flagged (10/12) is now closed.
- Tests: **61 passing** (+3: `coverage_questions` cover 10/12 and
  `sections_from_answers` include/prune for 10/12 in `test_guideline.py`; an
  affirmative financial+post-impl full-flow add in `test_tender.py`; updated the
  safety-net-note flow assertion to "4, 5, 10, 11, 12"). .pyz rebuilt (278 KB)
  and confirmed to bundle the new coverage + run.
- **main synced** after the green run (standing instruction).

## Iteration 9 — 2026-06-14

Reverse-prompting answers now drive section inclusion deterministically
(closes the item-specific half of follow-up 1 without needing a live LLM —
the buyer's own answers, not just the model, decide which sections apply):

- **`coach/guideline.py`:**
  - `_COVERAGE` entries gained a fourth field, `include_root` — the guideline
    section folded into the checklist when that coverage topic is answered
    affirmatively: integration → **6**, support → **7**, hardware → **8**,
    software → **9** (the cross-cutting 4/5/11 stay always-on via
    `CORE_SECTIONS`; cloud/data/deploy questions map to already-core sections
    so they carry `None`).
  - `is_affirmative(answer)` — compliance-safe yes/no reader: blank or a clear
    negative ("no", "n/a", "not required") with no affirmative cue → does not
    apply; an explicit yes **or any substantive answer** ("10 servers",
    "24/7 for 3 years") → applies. Bare "no" is overridden by a co-occurring
    affirmative ("no on-prem but yes the appliance" → applies).
  - `sections_from_answers(answers, clauses)` — matches each coverage topic's
    keywords against the interview *question* wording (so it works whether the
    question was the model's own or the merged coverage one) and returns the
    section roots whose answer was affirmative, gated on the section existing
    in the guideline.
- **`coach/llm.py`:** `build_checklist` unions `CORE_SECTIONS` with
  `sections_from_answers(answers, …)` and passes the merged set to
  `ensure_core_sections`, so a weak model that selects nothing item-specific
  still yields the sections the buyer flagged. `added_core_sections` now also
  reports answer-driven additions.
- **Surfaced to the user:** CLI + web finish notes reworded from "core
  compliance section(s) …" to "guideline section(s) … (cross-cutting
  compliance plus sections your answers flagged as relevant)"
  (`coach/tender.py`, `coach/webui.py`).
- **Verified on the genuine guideline:** a model that selects ONLY one
  software clause (9.1), with answers affirming software + integration +
  support and denying hardware, now produces a **157-row** checklist —
  Contract 33, Information Security 36, Interoperability 15, Support 27,
  Software 24, Compliance & Risk 22 — and correctly **omits hardware (8)**
  because the buyer said cloud-only. The list now reflects the interview, not
  just the model's pick.
- **Drive checked:** guideline + template both still `modifiedTime
  2026-06-10T13:05:11Z` (verified again this run) — no sample refresh needed.
- **Live LLM still unavailable** in this sandbox (no local server, no API key —
  checked again). This whole layer is deterministic and was verified on the
  real guideline, so it's valuable regardless of backend; the remaining
  *live-quality* review of the model's clause selection (follow-up 1) stays
  open, but it now matters far less since the buyer's answers backstop the
  item-specific sections too.
- Tests: **58 passing** (+5: `is_affirmative`, `sections_from_answers`
  include/prune in `test_guideline.py`; answer-driven add + negative-prune
  through the full flow in `test_tender.py`). README updated. .pyz rebuilt
  (277 KB) and confirmed to bundle `is_affirmative`/`sections_from_answers`.
- **main synced** after the green run (standing instruction).

## Iteration 8 — 2026-06-14

Deterministic safety net for cross-cutting compliance sections (follow-up 1 —
the part doable without a live LLM; guards the "full set of relevant compliance
list" goal against model under-selection):

- **`coach/guideline.py` — `ensure_core_sections()` + `CORE_SECTIONS`:** after
  the model's selections are reconciled and expanded, this always folds in the
  atomic requirements of the sections that apply to *every* procurement —
  **4 Contract, 5 Information Security, 11 Compliance & Risk** — that the
  expanded rows don't already cover, re-sorted into guideline order. Returns the
  merged rows plus the section roots it had to add. Gated on the guideline
  actually containing the section (unstructured guideline adds nothing), de-dupes
  against rows already present, and is a no-op when nothing was added.
- **`coach/llm.py`:** `build_checklist` calls `ensure_core_sections` as the last
  step (after `expand_requirements`) and records the added roots on the new
  `TenderChecklist.added_core_sections` field (`coach/models.py`).
- **Surfaced to the user (transparency for a compliance deliverable):** the CLI
  prints "core compliance section(s) X were added automatically …" and the web
  UI shows the same line in the finish note (`coach/tender.py`,
  `coach/webui.py` return `added_core` from `/api/tender/finish`).
- **Verified on the genuine guideline:** a model that selects ONLY one hardware
  clause (8.4) still yields a **92-row** checklist — Contract 33, Information
  Security 36, Compliance & Risk 22, plus the hardware row — i.e. the compliance
  list can no longer collapse to a near-empty deliverable on a weak model.
- **Drive checked**: guideline (`XXEON_IT_Procurement_Guideline.docx`) and
  template (`TENDER_TEMPLATE.xlsx`) both still `modifiedTime 2026-06-10T13:05:11Z`
  — unchanged since iter 1, no sample refresh needed. The "Purchasing Coach –
  Notes" Doc in the folder is still the iter-2 snapshot (Drive tooling can't
  update it; this NOTES.md remains canonical — follow-up 7).
- **Live LLM still unavailable** in this sandbox (no local server, no API key —
  checked again); the whole safety-net layer is deterministic and was verified
  on the real guideline, so it's valuable regardless of backend. The remaining
  *live-review* part of follow-up 1 stays open.
- Tests: **53 passing** (+5: `ensure_core_sections` add/no-dup/no-op in
  `test_guideline.py`; full-flow safety-net add + CLI note in `test_tender.py`).
  README updated. .pyz rebuilt (276 KB) and confirmed to bundle the new function.
- **main synced** after the green run (standing instruction).

## Iteration 7 — 2026-06-13

Granular, guideline-derived checklist + reverse-prompting coverage (user
request: "checklist of granular clauses and requirements the vendor must
fulfil, derived from the guideline in detail; ask additional questions to
cover the guideline fully"):

- **`coach/guideline.py` — new deterministic granularity layer:**
  - `parse_clause_requirements()` indexes the guideline *body*, not just
    headings: each normative paragraph under a clause becomes one
    `RequirementRow` carrying the real heading title and an M/O flag from its
    own wording. Non-normative prose (Introduction, etc.) is skipped via
    `_NORMATIVE`. On the genuine guideline this yields **202 atomic
    requirements across 65 clauses** (e.g. 5.3 → 8 rows, 5.6 → 9, 4.1 → 7).
  - `classify_obligation()` — strong cues (must/shall/mandatory/required/
    responsible for) → "M", weak (should/recommended/may/where feasible) →
    "O", strong wins; normative-but-uncued defaults to M (guideline is
    must/shall-heavy).
  - `expand_requirements()` — takes the model's grounded clause selections and
    fans each one out into its atomic, guideline-verbatim rows (and its
    sub-clauses, so citing "5" pulls in 5.1–5.7). Clauses with no parsed body
    keep the model's row (headings-only/degenerate guidelines still work).
    De-dupes, preserves within-clause body order, returns guideline order.
  - `coverage_questions()` — applicability questions for every major section
    the guideline actually contains (hardware/software/cloud/data/cyber-
    assessment/integration/support/contract/deployment), gated so an
    unstructured guideline grounds none.
- **`coach/llm.py`:**
  - `build_checklist` now instructs the model to *select* every applicable
    clause comprehensively (one row per clause, whole-section refs allowed)
    rather than paraphrase — then `expand_requirements` produces the detailed
    rows. A simulated hardware purchase (sections 4,5,7,8,10,11,12) now writes
    **158 granular rows** to the real template (table extends to A2:G160),
    each a verbatim vendor obligation with M/O, vs. the old ~handful of
    summary lines.
  - `plan_interview` → `_ensure_coverage()` merges the coverage questions the
    model didn't already ask (keyword de-dup), capped at `MAX_QUESTIONS=16`.
    Guarantees section-applicability coverage even on weak local models.
- **Reconciliation (iter 5) is unchanged and runs first** — canonical titles,
  ordering and unverified-ref flagging still apply, then expansion layers on
  the granularity.
- **Drive checked**: guideline + template unmodified since 2026-06-10
  (verified again this run) — no sample refresh needed.
- **Live LLM still unavailable** in this sandbox (no local server reachable,
  no API key); the whole granularity/coverage layer is deterministic and was
  verified directly on the genuine guideline text + template, so it's valuable
  regardless of backend. Follow-ups 1/2 (live quality review) remain open.
- Tests: **48 passing** (+9: `parse_clause_requirements`, `classify_obligation`,
  `expand_requirements` fan-out/fallback/no-op, `coverage_questions` gating in
  `test_guideline.py`; section-fan-out + coverage-merge through the full flow
  in `test_tender.py`). .pyz rebuilt (275 KB) and confirmed to bundle the new
  functions; end-to-end workbook generation against the real template green.
- **main synced** after the green run (standing instruction).

## Iteration 6 — 2026-06-13

Web UI redesign + browserless stress harness (user request):

- **Researched** current chat-UI / single-file design practices (UXPin,
  TheFrontKit, dev.to LLM-UI, CSS-variables dark-mode guides) and applied the
  high-value, constraint-compatible ones (kept the single self-contained HTML
  page — inline CSS/JS, system fonts, no CDN/build — so it still runs offline
  on locked-down machines).
- **Enhanced `coach/webui.py` page**:
  - Design system via CSS custom properties; **light/dark themes** following
    `prefers-color-scheme`, with a header toggle persisted to `localStorage`
    and applied before first paint (no flash).
  - **Stop button**: Send turns into Stop while a reply streams (Esc also
    stops); cancels via `AbortController`. Abort is detected robustly — undici/
    browser fetch ends an aborted stream cleanly (`done`) rather than throwing,
    so we also check `signal.aborted` after the read loop. Partial reply is
    kept (with an italic "stopped" note) so the conversation stays coherent.
    Server `_chat` now swallows `BrokenPipeError` on client disconnect.
  - Accessibility: chat log is an ARIA live region (`role="log"`,
    `aria-live="polite"`), labelled controls, `role=status` announcements,
    48px (>=44px) touch targets, focus-visible rings, `prefers-reduced-motion`.
  - Polish: PC/You/i avatars, copy-to-clipboard on replies, auto-growing
    textarea, scroll only auto-follows when already at the bottom, responsive
    mobile layout, calmer panel/border styling. The unverified-clause warning
    from iter 5 now renders in red in the web UI too.
- **Installed for use**: a browser binary can't be installed here (Playwright
  CDN, gvt1 and Puppeteer's Chrome download are all blocked by the network
  policy; no system chromium), so the UI tooling is **jsdom** (npm, reachable)
  — a real in-process DOM that runs the page's JS. The harness lives in
  `.design-tools/` (gitignored) and is documented in follow-up 9.
- **Stress tested** (LM Studio on the user's machine is NOT reachable from
  this sandbox — its localhost is isolated; verified). Drove the *real* page
  in jsdom against the *real* `http.server` backed by a streaming LM-Studio
  mock, using Node's global fetch (HTTP streaming + AbortSignal) so the whole
  stack is exercised: **34/34 checks pass** (theme toggle+persist, streaming
  render, caret, Stop/abort keeps partial, markdown table/code/bold, HTML-
  injection escaping, full tender flow incl. unverified warning + download,
  cancel/restart, 400-line markdown x200 in ~100ms, 300 rapid DOM messages).
  HTTP load test (`load_test.py`): **40 concurrent chat streams + 20
  concurrent tender runs OK, 20 mid-stream client aborts, server healthy
  after** — all green.
- Tests: 39 pytest still pass (page wiring assertions preserved); .pyz rebuilt
  (272 KB) and confirmed to bundle the new page.
- **main synced** after the green run.

## Iteration 5 — 2026-06-13

Guideline-grounded checklist (deterministic output fidelity):

- **New `coach/guideline.py`**: `parse_clauses()` indexes the guideline's
  numbered markdown headings (`### 5.6 Audits and Assessments`) into an
  ordered `{ref: title}` map; `reconcile_requirements()` post-processes the
  model's checklist before it is written — it canonicalises each row's
  `section` to the real clause heading, normalises refs (`Clause 5.3` → `5.3`),
  reorders rows into guideline order, drops exact-duplicate rows, and returns
  the clause numbers the model cited that don't exist in the guideline.
- **Why**: addresses the risk flagged in follow-ups 1/2 — small local models
  paraphrase clause titles and occasionally invent clause numbers. This makes
  the Excel deliverable trustworthy and consistent regardless of backend or
  model size, and needs no live LLM to be valuable. The clause index is also
  the building block for the per-section context filtering in follow-up 2.
- **Surfaced everywhere**: `TenderChecklist.unverified_refs` field carries the
  flagged refs; the CLI prints a "could not be matched … please verify" note,
  the web UI `/api/tender/finish` returns `unverified` and the page shows it.
- **Verified on the genuine docx**: 65 clauses parsed from the real Drive
  guideline; reconciliation corrects titles, orders rows and flags a planted
  hallucinated ref. Full end-to-end smoke test of the rebuilt .pyz (269 KB)
  against a mock LM Studio server: tender start/finish + download, workbook
  shows canonical headings, guideline order and the flagged row.
- **Drive checked**: guideline + template unmodified since 2026-06-10 (verified
  again this run) — no sample refresh needed.
- **Live LLM still unavailable** (no local server, no API key in this env);
  follow-ups 1 and 2 (live testing) remain blocked here.
- Tests: 39 passing (+8: new `tests/test_guideline.py` covers parsing, ref
  normalisation, numeric sort, title canonicalisation, dedupe and the
  no-index no-op; `tests/test_tender.py` extended to assert reordering +
  canonical titles + the unverified note through the full flow).
- **main synced** after the green run (standing instruction).

## Iteration 4 — 2026-06-12

Restart-interview control + first check-in to main:

- **Restart interview** (the remaining idea from follow-up 6): during a
  tender interview the "Tender checklist" button becomes "Restart
  interview" and re-asks from the item question; typing `restart` or
  `/tender` mid-flow does the same, `cancel` still aborts. Flow teardown
  is centralised in `endTender()` so the button label/placeholder reset on
  cancel, plan failure and completion alike.
- **main synced**: previous iterations only ever pushed the dev branch, so
  `main` was still at the initial commit; merged the working copy to main
  per the standing instruction. Do this every run from now on.
- **Drive checked**: guideline + template still unmodified since
  2026-06-10; no sample refresh needed.
- **Live LLM still unavailable** (no local server, no API key — checked
  again); follow-ups 1 and 2 remain blocked in this environment.
- Tests: 31 passing (new test pins the restart wiring in the served page);
  page JS evaluated under Node with DOM stubs; .pyz rebuilt (267 KB) and
  smoke-tested end to end (web chat + tender + download) against the mock
  LM Studio server.

## Iteration 3b — 2026-06-12

Structured output formatting (user request):

- System prompt now asks the model to lead with a one-sentence answer and
  use markdown structure (clause-first bullets, **bold** clause numbers,
  sparing ### headings, short paragraphs).
- Web UI renders that markdown properly while streaming: paragraphs,
  bullet/numbered lists, headings, **bold**, `code`, ``` fences and
  | tables |. All input is HTML-escaped before our tags are added, so
  model output can't inject markup.
- New `coach/format.py`: terminal renderer. With a TTY it styles headings
  (bold+underline), clause numbers (bold) and inline code (cyan), and
  shows bullets as "•"; piped/NO_COLOR output gets the markers stripped
  instead. Line-buffered so streamed chunks can split lines or ** markers
  anywhere. Legacy Windows consoles get VT mode enabled at startup.
- Tests: 30 passing (renderer covered incl. chunk-splitting); md() also
  exercised in Node against a representative reply; CLI verified
  end-to-end over the mock LM Studio server; .pyz rebuilt (267 KB).

## Iteration 3 — 2026-06-11

Local web UI + genuine template recovered:

- **Web UI** (`coach/webui.py`, follow-up 6 done): `--web` serves a
  single-page browser chat on `http://127.0.0.1:8765/` from the same .pyz —
  stdlib `http.server` only, no new dependencies. Streams chat replies
  (chunked transfer), runs the tender interview as a guided conversation
  ("Tender checklist" button or typing `/tender`), and ends with a download
  link for the generated workbook. Downloads are restricted to files
  generated in the session; the server binds to localhost only. `--port`
  and `--no-browser` flags added.
- **Real template fidelity** (follow-up 2 done): re-downloaded
  `TENDER_TEMPLATE.xlsx` from Drive. The transferred zip had a handful of
  corrupt members, but every content part (both sheet XMLs, styles, theme,
  sharedStrings, the `TenderRequirements` table) was intact; the corrupt
  parts were all standard boilerplate (`workbook.xml`,
  `[Content_Types].xml`, `docProps/app.xml`, Office customXml) and were
  rebuilt byte-equivalent in meaning. `samples/TENDER_TEMPLATE.xlsx` is now
  the genuine template: labels at A2–A10, tracker header on row 2, merged
  title cells and a real Excel table — the writer handles all of it and
  the table ref extends with the written rows (verified by test + manual
  load).
- **Guideline sync checked**: Drive docs unmodified since 2026-06-10 — no
  refresh needed.
- Tests: 24 passing offline (web UI endpoints exercised over real HTTP).
  End-to-end smoke test of the rebuilt .pyz (264 KB): web UI + chat +
  tender + download against a mock LM Studio server, all green.

## Iteration 2 — 2026-06-11

Local-LLM + portability rework (for corporate machines without install
rights):

- New `coach/backends.py`: pluggable LLM backends. LM Studio and Ollama are
  supported through their OpenAI-compatible localhost APIs using **only the
  standard library** (urllib, SSE streaming, JSON-schema structured output
  with graceful fallback to json_object / plain prompting for servers that
  don't support it). Claude API remains an optional backend (lazy import).
- Backend auto-detection: LM Studio (:1234) → Ollama (:11434) → Claude API if
  a key is set; `--backend`, `--base-url`, `--llm-model` to override. The
  first model reported by the local server is used by default.
- Removed all compiled/runtime dependencies except pure-Python `openpyxl`:
  pydantic → dataclasses + hand-written JSON schemas; python-docx → stdlib
  zipfile/ElementTree docx parser (python-docx is now dev-only for
  `scripts/make_samples.py`).
- Portable distribution: `scripts/build_portable.py` builds
  `dist/purchasing-coach.pyz` (~330 KB zipapp bundling coach + openpyxl).
  Runs with any Python 3.10+ — including the python.org embeddable zip —
  with zero installs: `python purchasing-coach.pyz --guideline g.docx`.
- Tests extended (backend HTTP layer mocked, SSE parsing, JSON-schema
  fallback, model validation); all green offline.

## Iteration 1 — 2026-06-10

Initial working version: CLI chat over the guideline with clause citations,
`/tender` interview flow writing an Excel checklist (Tender Information +
Compliance Tracker) from the template, docx/md/txt loaders, offline tests.

## Follow-ups for the next run

1. **Live LLM run still untested.** Neither a local LLM server nor an
   `ANTHROPIC_API_KEY` is available in the build environment (checked again
   in iterations 3/5/7), so real model quality has not been exercised — only
   mocked paths. Iteration 7 narrowed the model's checklist job to *clause
   selection* (the granular requirement text is now deterministic), which
   makes small-model output far more robust, but the *selection* itself still
   needs a live review. Next run: test a real `/tender` session (one hardware
   + one SaaS item) against LM Studio with a ~7B instruct model and check the
   model picks the right clauses (it can cite whole sections like "5"); under-
   selection now matters more than paraphrase quality. **Two deterministic
   backstops now blunt under-selection:** iter 8 always folds in 4/5/11, and
   iter 9 folds in the item-specific sections (6 interoperability, 7 support,
   8 hardware, 9 software) whenever the buyer's interview answer affirms them —
   so the live review is now mainly a quality check on the model's *extra*
   picks and on the answer wording. **Sections 10 (financial/TCO) and 12
   (post-implementation) are now answer-backed too** (iter 10) — every
   normative top-level section now has a coverage question with answer-driven
   inclusion, so the only remaining unbacked path is a buyer who declines a
   section that nonetheless applies. Open question for the live run: whether
   10/12 should be promoted from answer-driven to `CORE_SECTIONS` (always-on) —
   they're near-universal vendor obligations, but kept answer-driven for now to
   avoid bloating checklists for pure commodity buys; revisit if the live run
   shows buyers routinely want them regardless.
2. **Checklist size vs local context windows.** The full guideline still rides
   in the system prompt (~7K tokens) — fine for 8K+ context models. The clause
   *body* index now exists (`parse_clause_requirements`), so the remaining work
   for small-context models is to trim the system prompt for the checklist call
   to just the candidate sections. Output tokens are no longer the constraint
   (the model emits short clause refs + notes, not full requirement text).
   Best done with follow-up 1 so the effect on clause selection is observable.
   Possible refinement: within a very large selected section, optionally filter
   atomic requirements by the interview answers (today the whole clause's
   requirements are included — deliberately inclusive for compliance safety).
3. **Drive round-trip.** Optionally upload generated checklists back to the
   "Purchasing Guideline" Drive folder after a tender run.
4. **Guideline sync.** Drive docs last modified 2026-06-10 (verified
   unchanged again 2026-06-13). If they change, refresh
   `samples/guideline_text.md` and rerun `scripts/make_samples.py`.
5. **Guideline docx binary.** `samples/XXEON_IT_Procurement_Guideline.docx`
   is still a reconstruction (same text as the Drive original, which is
   unchanged). The docx parser handles it correctly — iteration 5 parsed 65
   clauses cleanly from it. Only worth re-transferring if the parser ever
   misbehaves on the real file.
6. **Web UI polish.** Markdown (3b), restart interview (4), full redesign +
   dark mode + Stop button + a11y (6) all done. Remaining: check how the
   structured-output prompt behaves on small local models during the live LLM
   run (follow-up 1) — verbose markdown could bloat 7B replies. Possible
   nice-to-haves: copy button on individual code blocks, message timestamps.
7. **Drive notes doc.** The "Purchasing Coach – Notes" Google Doc in the
   Drive folder still shows the iteration-2 snapshot; the connected Drive
   tooling can create but not update files. This NOTES.md is canonical.
8. **Check in to main every run.** main was 4 iterations stale until
   iteration 4. After a green run: push the dev branch, then fast-forward
   main to it and push main.
9. **UI stress harness is local-only.** Lives in `.design-tools/` (gitignored;
   needs `npm install jsdom` + the bundled `serve_mock.py`/`ui_test.js`/
   `load_test.py`). Not committed because a real browser can't be installed in
   the web sandbox (Playwright/Puppeteer download hosts are blocked) and we
   don't want node_modules in the repo. If we later want this in CI, either
   vendor a tiny jsdom-free DOM stub or run it where a browser is available.
11. **Review & Approval sheet polish — DONE (iter 15).** Conditional formatting
    turns the *Mandatory non-compliant* cell red when > 0 (green at 0); a live
    compliance-rate % row was added; and the web finish note now reflects the
    mandatory count + the review-sheet summary. Remaining check: confirm the
    formulas + conditional formatting render in **real Excel/LibreOffice** (only
    openpyxl reload is exercised in-sandbox). Other nice-to-have: a data-bar or
    icon-set on the compliance-rate cell.
10. **Live UI test against the user's LM Studio.** The web sandbox cannot
    reach the user's machine localhost (LM Studio at :1234 is isolated —
    verified 2026-06-13), so stress testing used an in-container streaming
    mock. To validate against the real model, run locally:
    `python purchasing-coach.pyz --guideline g.docx --template t.xlsx --web`
    with LM Studio's server started, then exercise chat + Stop + a tender run.
12. **Embedded SLM variant — live test (iter 16).** The bundled-model
    resolution and item-relevant questions are deterministic and verified, but
    the actual GGUF/`llama-cpp-python` path has not run in-sandbox (compiled dep
    + ~1.1 GB model can't be installed/downloaded here). Next run with the tools:
    `python scripts/build_portable.py --with-model` then run the resulting
    `purchasing-coach-embedded.pyz` and confirm (a) the bundled model is
    extracted to the cache and loads, (b) a `/tender` run produces a sane
    checklist, and (c) quality of the 1.5B model's clause selection (the
    deterministic safety nets + item-relevant questions backstop it, but worth a
    look). Also worth trying the "ship `.pyz` + `models/` folder" layout to
    confirm the adjacent-dir path on a real machine.
13. **CI verification + lint tightening (iter 17).** The CI workflow
    (`.github/workflows/ci.yml`) has not run on a real GitHub Actions runner
    from here — confirm the first push goes green (test matrix 3.10–3.12 + the
    build/smoke job). Then tighten ruff by enabling `B` (bugbear) and `UP`
    (pyupgrade): the known findings are duplicate stopwords in
    `retrieval/tokenizer.py` (`B033`, harmless), unused loop vars in
    `bm25.py`/`keyword.py` (`B007`), an empty ABC hook in `backends/base.py`
    (`B027` — add `@abstractmethod` or document), and a `raise ... from` in a
    backend (`B904`). All low-risk; left out of pass 1 to keep the first CI run
    green with minimal churn.

## Loop progress (production-quality, target ≥10 passes)

- **Pass 1 (iter 17):** packaging (`pyproject.toml` + console script), pytest
  scoping fix, ruff lint + clean-up, CI workflow — and fixed a real
  section-dropping bug (`F601`) the linter surfaced.
- **Pass 2 (iter 17):** enabled ruff bugbear (`B`) + pyupgrade (`UP`) and fixed
  every finding — unused loop vars → `_`-prefixed (`B007` in bm25/keyword),
  `raise ... from exc` in the embedded download path (`B904`), duplicate
  stopword set entries removed (`B033`), `Callable` imported from
  `collections.abc` and an unnecessary `encode("utf-8")` modernised (`UP`), and
  a documented `# noqa: B027` on the optional `load_guideline` hook. `ruff
  check .` clean with the stricter ruleset; 107 tests still pass. (Note:
  scheduling tools `ScheduleWakeup`/`CronCreate` are NOT available in this
  environment, so loop passes are run back-to-back inline within the session
  rather than as deferred firings.)
- **Pass 3 (iter 17):** input validation & error handling. `documents.py`
  `load_guideline` now raises clear, actionable errors instead of cryptic
  stdlib ones — rejects directories, corrupt/`.doc` files (`BadZipFile`),
  `.docx` missing `word/document.xml`, malformed XML, and empty/image-only docs;
  text/markdown reading falls back through utf-8 → utf-8-sig → cp1252 → latin-1
  so Windows-exported guidelines load. The CLI wraps `load_guideline` and prints
  a clean message + exit code 2 instead of a traceback. +7 tests
  (`test_documents.py`); 113 total, ruff clean, .pyz rebuilt.
- **Pass 4 (iter 17):** web UI hardening (it's a localhost HTTP service).
  Closed a **path-traversal** risk — session ids (from the URL/JSON body) were
  used directly as filenames (`SESSIONS_DIR/{sid}.json`), so `{"id":"../../evil"}`
  could write outside the sessions dir; ids are now constrained to
  `[A-Za-z0-9_-]{1,64}` (`_session_path` returns None for unsafe ids;
  `save_session` mints a safe id instead of honouring a bad one). Added a
  **request-body cap** (`MAX_BODY_BYTES = 8 MB`, returns 413) so a bogus
  `Content-Length` can't exhaust memory, plus negative/invalid length → 400.
  Added **`X-Content-Type-Options: nosniff`** and `Referrer-Policy: no-referrer`
  to all responses. +3 tests (`test_webui.py`); 116 total, ruff clean, .pyz
  rebuilt (327 KB).
- **Pass 5 (iter 17):** test coverage. The retrieval engine
  (`retrieval/tokenizer`, `index`, `ranker`) and the `keyword`/`bm25` backends
  were at **0%** despite `keyword` being the default no-LLM fallback. Added
  `tests/test_retrieval.py` (+16): tokenizer/stem/ngrams, index build + BM25/df/
  idf stats, BM25/cosine ranking + RRF fusion ordering, and both retrieval
  backends end-to-end (item-tailored interview, checklist build, chat,
  health). Coverage **57% → 77%** (retrieval modules now 88–95%). Wired
  `pytest-cov` into the `dev` extra + `[tool.coverage.run]` config (no failing
  threshold, to keep CI stable). 132 tests, ruff clean. No source change — .pyz
  unchanged.
- **Pass 6 (iter 17):** covered the two remaining 0% modules. `test_claude.py`
  (+5, anthropic SDK faked): missing-package error, default model/name,
  `stream_chat`, `complete_json` JSON parse, `health_check` ok/error →
  `claude_api.py` **100%**. `test_cli.py` (+5): missing guideline → exit 2,
  empty guideline → exit 2 (clean message), interactive `/quit` and `/help`
  flows → exit 0, EOF exits cleanly → `cli.py` **65%** (remainder is the live
  chat-stream body + `--web`). Coverage **77% → 82%**. 142 tests, ruff clean,
  tests-only (no .pyz change).
- **Pass 7 (iter 17):** robustness of the structured-output parsing layer
  (`models.py`). Fixed a real edge: a model returning a **string** (not a list)
  for `questions`/`requirements`/`messages`/`reactions` was iterated
  character-by-character into garbage rows; all `from_dict` methods now guard
  with `isinstance(..., list/dict)` and tolerate a non-dict top-level input.
  `test_models.py` (+12) covers the guards, M/O normalisation, TBC defaults,
  Session/ChatMessage round-trip, and `AnalyticsSnapshot.from_checklist`
  (counts, coverage %, heatmap). `models.py` 77% → **98%**, total **82% → 83%**.
  154 tests, ruff clean, .pyz rebuilt.
- **Pass 8 (iter 17):** logging & observability. The `coach` logger gets a
  `NullHandler` in `coach/__init__.py` (library stays silent unless configured —
  idiomatic). New CLI `--verbose/-v` configures stderr logging; it sets the
  package logger level **explicitly** (not just `basicConfig`, which no-ops when
  a host app already configured logging) so it always takes effect. The web
  server previously **swallowed tracebacks** (suppressed `log_message`, bare
  `except`); it now logs `log.exception` on POST failures and chat-stream errors
  via `coach.webui`. +3 tests (`--verbose` level, 500-is-logged, cli flow);
  156 tests, ruff clean, .pyz rebuilt.
- **Pass 9 (iter 17):** covered the primary live backend `openai_compat.py`.
  `test_openai_compat.py` (+11): `extract_json` (plain / fenced / fenced-no-lang
  / surrounding prose / invalid→BackendError), provider-preset & base-url
  resolution, `_headers` auth, the `complete_json` **format-fallback chain**
  (json_schema → json_object → no response_format), and the unexpected-shape
  error. `openai_compat.py` 82% → **89%**, total **83% → 84%**. 167 tests, ruff
  clean, tests-only (no .pyz change).
- **Pass 10 (iter 17):** project/release hygiene — added `CHANGELOG.md`
  (Keep a Changelog: Unreleased + 2.1.0 / 2.0.0 / 1.0.0) and `CONTRIBUTING.md`
  (dev setup, lint/test/build loop, pure-Python & rebuild-the-.pyz rules),
  linked from the README. Docs-only; 167 tests, ruff clean.

**LOOP COMPLETE — 10 passes done, all synced to main.** Net effect: the app is
materially more production-ready — packaged (`pyproject.toml` + console script),
linted (ruff E/F/W/B/UP, clean), CI-wired (3.10–3.12 matrix + build smoke test),
**~84% test-covered** (was ~57%, retrieval/Claude/CLI/models all went from 0–77%
to 88–100%), with input/parse/network hardening, structured logging, and a real
section-dropping bug fixed.

Remaining backlog for future routine runs: confirm CI goes green on a real
runner (follow-up 13); type hints + mypy in CI; push `template.py` (58%),
`webui.py` and `cli.py` coverage higher; performance pass on retrieval for very
large guidelines; wheel build + tagged release in CI; the still-open live-LLM /
embedded-model exercises (follow-ups 1, 10, 12).
