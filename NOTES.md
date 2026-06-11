# Iteration notes & follow-ups

Reference this file at the start of each routine run.

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
   checklist call. Best done together with follow-up 1 so the effect on
   requirement selection can actually be observed.
3. **Drive round-trip.** Optionally upload generated checklists back to the
   "Purchasing Guideline" Drive folder after a tender run.
4. **Guideline sync.** Drive docs last modified 2026-06-10 (verified
   unchanged 2026-06-11). If they change, refresh `samples/guideline_text.md`
   and rerun `scripts/make_samples.py`.
5. **Guideline docx binary.** `samples/XXEON_IT_Procurement_Guideline.docx`
   is still a reconstruction (same text as the Drive original, which is
   unchanged). Only worth re-transferring if the docx parser ever misbehaves
   on the real file.
6. **Web UI polish (nice-to-have).** Replies render as plain text in the
   browser — light markdown rendering (bold/lists) would read better; a
   "restart interview" button mid-flow could help too.
7. **Drive notes doc.** The "Purchasing Coach – Notes" Google Doc in the
   Drive folder still shows the iteration-2 snapshot; the connected Drive
   tooling can create but not update files. This NOTES.md is canonical.
