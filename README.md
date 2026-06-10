# Purchasing Coach

A portable command-line chatbot that ingests a purchasing guideline document
(e.g. an IT procurement guideline in `.docx`) and lets you:

1. **Chat** — ask questions about the guideline; answers cite clause numbers.
2. **Generate a tender checklist** — type `/tender`, describe what you want to
   buy, answer a short interview driven by the guideline, and get an Excel
   workbook (based on your tender template) with the tender information sheet
   filled in and a compliance tracker listing every applicable requirement
   marked Mandatory/Optional.

The source documents (`XXEON_IT_Procurement_Guideline.docx` and
`TENDER_TEMPLATE.xlsx`) live in the Google Drive **"Purchasing Guideline"**
folder. The copies under `samples/` are local reconstructions used for
development and tests — regenerate them with `python scripts/make_samples.py`.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # your Claude API key
```

## Usage

```bash
# Uses the bundled samples by default
python -m coach

# Or point at your own documents
python -m coach --guideline /path/to/guideline.docx \
                --template  /path/to/TENDER_TEMPLATE.xlsx \
                --out-dir   ./output
```

Example session:

```
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

Supported guideline formats: `.docx`, `.md`, `.txt` (and `.pdf` with
`pip install pypdf`). If no template is supplied, a built-in layout matching
`TENDER_TEMPLATE.xlsx` (sheets *Tender Information* and *Compliance Tracker*)
is used.

## Development

```bash
pip install -r requirements.txt pytest
python scripts/make_samples.py   # rebuild sample docx/xlsx
pytest                           # offline — LLM calls are faked in tests
```

Project layout:

- `coach/documents.py` — guideline loading (docx/md/txt/pdf → text)
- `coach/llm.py` — Claude API wrapper (chat streaming, structured outputs,
  prompt caching of the guideline)
- `coach/tender.py` — interview flow
- `coach/excel.py` — template-aware checklist writer
- `coach/cli.py` — interactive CLI
- `NOTES.md` — follow-ups for the next iteration
