# Iteration notes & follow-ups

Reference this file at the start of each routine run.

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
   selection now matters more than paraphrase quality. Consider a deterministic
   safety net that always includes the cross-cutting sections (4 Contract, 5
   Information Security, 11 Compliance & Risk) regardless of model output.
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
10. **Live UI test against the user's LM Studio.** The web sandbox cannot
    reach the user's machine localhost (LM Studio at :1234 is isolated —
    verified 2026-06-13), so stress testing used an in-container streaming
    mock. To validate against the real model, run locally:
    `python purchasing-coach.pyz --guideline g.docx --template t.xlsx --web`
    with LM Studio's server started, then exercise chat + Stop + a tender run.
