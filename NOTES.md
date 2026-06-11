# Iteration notes & follow-ups

Reference this file at the start of each routine run.

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
   `ANTHROPIC_API_KEY` is available in the build environment, so real model
   quality has not been exercised — only mocked paths. Next run: test a real
   `/tender` session (one hardware + one SaaS item) against LM Studio with a
   ~7B instruct model and review requirement selection; small local models
   may need the checklist prompt split per guideline section.
2. **Real template fidelity.** `samples/` still holds reconstructions of the
   Drive originals (binary transfer corrupted in iteration 1). At runtime the
   user's real template is filled via `--template`, preserving formatting,
   but verifying against the genuine binary template is still pending.
3. **Checklist size vs local context windows.** The full guideline rides in
   the system prompt (~7K tokens). Fine for 8K+ context models; if users load
   small-context models, add per-category section filtering before the
   checklist call.
4. **Drive round-trip.** Optionally upload generated checklists back to the
   "Purchasing Guideline" Drive folder after a tender run.
5. **Guideline sync.** Drive docs last modified 2026-06-10. If they change,
   refresh `samples/guideline_text.md` and rerun `scripts/make_samples.py`.
6. **Nice-to-have:** a minimal local web UI (stdlib `http.server`) so
   non-terminal users get a friendlier interface from the same .pyz.
