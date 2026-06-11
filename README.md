# Purchasing Coach

A portable chatbot that ingests a purchasing guideline document (e.g. an IT
procurement guideline in `.docx`) and lets you:

1. **Chat** — ask questions about the guideline; answers cite clause numbers.
2. **Generate a tender checklist** — type `/tender`, describe what you want to
   buy, answer a short interview driven by the guideline, and get an Excel
   workbook (based on your tender template) with the tender information sheet
   filled in and a compliance tracker listing every applicable requirement
   marked Mandatory/Optional.

It is designed for locked-down corporate machines: it runs against a **local
LLM** served by **LM Studio** or **Ollama** (auto-detected, no cloud account
or API key needed), and ships as a **single-file `.pyz`** that needs nothing
installed beyond a Python interpreter. The Claude API is supported as an
optional backend.

The source documents (`XXEON_IT_Procurement_Guideline.docx` and
`TENDER_TEMPLATE.xlsx`) live in the Google Drive **"Purchasing Guideline"**
folder. The copies under `samples/` are local reconstructions used for
development and tests — regenerate them with `python scripts/make_samples.py`.

## Portable use (no install rights needed)

1. Copy `dist/purchasing-coach.pyz`, your guideline document and your tender
   template onto the machine (a network share or USB stick is fine).
2. Make sure a local LLM server is running:
   - **LM Studio**: load a model, then enable the local server
     (Developer tab → Start Server, default port 1234), or
   - **Ollama**: `ollama serve` with a pulled model (default port 11434).
3. Run it with any Python 3.10+ (the standard python.org "embeddable"
   zip or WinPython work without admin rights):

```
python purchasing-coach.pyz --guideline Guideline.docx --template TENDER_TEMPLATE.xlsx
```

The backend is auto-detected (LM Studio → Ollama → Claude API if an
`ANTHROPIC_API_KEY` is set). Pin it explicitly with `--backend lmstudio`,
`--backend ollama`, `--backend claude`, or point at any OpenAI-compatible
server with `--base-url http://host:port/v1`. Pick a model with
`--llm-model` (otherwise the first model the server reports is used).

> Tip: instruction-tuned models ≥7B (e.g. Qwen 2.5 7B Instruct, Llama 3.1 8B
> Instruct) give noticeably better checklists than smaller models.

## Running from source

```bash
pip install -r requirements.txt        # just openpyxl
python -m coach                        # uses the bundled samples by default
```

Example session:

```
Using local model 'qwen2.5-7b-instruct' via lmstudio (http://localhost:1234/v1)

you> Do cloud vendors need a SOC 2 report?
coach> Yes — clause 5.6 requires cloud and SaaS providers to supply an
annual SOC 2 Type II report to XXEON. ...

you> /tender
What do you want to buy? Describe the item/solution: 200 laptops for the sales team
[1/8] When is the submission deadline?
> 15 July 2026
...
Done. 42 requirements written to: TENDER_CHECKLIST_200_laptops_..._20260610.xlsx
```

Supported guideline formats: `.docx` (parsed with the standard library — no
extra packages), `.md`, `.txt`, and `.pdf` with `pip install pypdf`. If no
template is supplied, a built-in layout matching `TENDER_TEMPLATE.xlsx`
(sheets *Tender Information* and *Compliance Tracker*) is used.

## Development

```bash
pip install -r requirements-dev.txt
python scripts/make_samples.py        # rebuild sample docx/xlsx
pytest                                # offline — LLM calls are faked/mocked
python scripts/build_portable.py      # rebuild dist/purchasing-coach.pyz
```

Project layout:

- `coach/backends.py` — LLM backends: OpenAI-compatible local servers
  (LM Studio/Ollama, stdlib `urllib` only) and optional Claude API
- `coach/documents.py` — guideline loading (docx/md/txt/pdf → text)
- `coach/llm.py` — prompts + response parsing on top of a backend
- `coach/models.py` — dataclass models + JSON schemas for structured output
- `coach/tender.py` — interview flow
- `coach/excel.py` — template-aware checklist writer
- `coach/cli.py` — interactive CLI
- `NOTES.md` — follow-ups for the next iteration
