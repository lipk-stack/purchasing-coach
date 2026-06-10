# Iteration notes & follow-ups

Reference this file at the start of each routine run.

## Iteration 1 — 2026-06-10

Built the initial working version:

- `python -m coach` CLI: chat over the guideline (streaming, clause citations,
  guideline cached via prompt caching) + `/tender` interview flow that writes
  an Excel checklist (Tender Information + Compliance Tracker sheets).
- Guideline loader for .docx/.md/.txt (.pdf optional via pypdf).
- Template-aware Excel writer: fills the user's TENDER_TEMPLATE.xlsx when
  supplied, otherwise builds an equivalent layout.
- Offline test suite (8 tests, LLM faked) — all green.

## Follow-ups for the next run

1. **Live LLM run untested.** This environment has no `ANTHROPIC_API_KEY`, so
   the real chat/tender quality was not exercised — only the fake-client test
   path. Next run: if a key is available, do a real `/tender` session for one
   hardware and one SaaS item and review the requirement selection quality.
2. **Real template fidelity.** Binary downloads of `TENDER_TEMPLATE.xlsx` and
   the guideline `.docx` from Google Drive (base64 via chat) arrived corrupted,
   so `samples/` holds reconstructions built from the extracted text/structure
   (same sheets, labels and columns). At runtime the app fills the user's real
   template via `--template`, preserving its formatting. Still worth verifying
   the writer against the genuine binary template once a lossless transfer
   path exists (e.g. Drive file download to the execution container).
3. **Drive round-trip.** Consider an option to upload the generated checklist
   back to the "Purchasing Guideline" Drive folder after a tender run.
4. **Guideline sync.** Drive docs last modified 2026-06-10. If they change,
   refresh `samples/guideline_text.md` and rerun `scripts/make_samples.py`.
5. **Nice-to-have:** a lightweight web UI (e.g. Streamlit) on top of
   `coach.llm.Coach` for non-terminal users; CLI is the current interface.
6. **Token optimisation:** the full guideline rides in the (cached) system
   prompt. If guidelines grow much larger, add per-category section filtering
   before the checklist call.
