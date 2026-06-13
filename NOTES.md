# Iteration notes & follow-ups

Reference this file at the start of each routine run.

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
   in iteration 3), so real model quality has not been exercised — only
   mocked paths. Next run: test a real `/tender` session (one hardware + one
   SaaS item) against LM Studio with a ~7B instruct model and review
   requirement selection; small local models may need the checklist prompt
   split per guideline section.
2. **Checklist size vs local context windows.** The full guideline rides in
   the system prompt (~7K tokens). Fine for 8K+ context models; if users load
   small-context models, add per-category section filtering before the
   checklist call. The clause index from iteration 5 (`coach/guideline.py`,
   `parse_clauses`) gives the heading structure to slice on; extend it to also
   capture each clause's body text, then select relevant sections from the
   interview answers and trim the system prompt for the checklist call. Best
   done together with follow-up 1 so the effect on requirement selection can
   actually be observed.
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
6. **Web UI polish (nice-to-have).** Markdown rendering done (3b), restart
   interview done (4). Remaining: check how the structured-output prompt
   behaves on small local models during the live LLM run (follow-up 1) —
   verbose markdown could bloat 7B model replies.
7. **Drive notes doc.** The "Purchasing Coach – Notes" Google Doc in the
   Drive folder still shows the iteration-2 snapshot; the connected Drive
   tooling can create but not update files. This NOTES.md is canonical.
8. **Check in to main every run.** main was 4 iterations stale until
   iteration 4. After a green run: push the dev branch, then fast-forward
   main to it and push main.
