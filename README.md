# Purchasing Coach

A portable chatbot that ingests a purchasing guideline document (e.g. an IT
procurement guideline in `.docx`) and lets you:

1. **Chat** — ask questions about the guideline; answers cite clause numbers.
2. **Generate a tender checklist** — type `/tender`, describe what you want to
   buy, answer a short interview driven by the guideline, and get an Excel
   workbook (based on your tender template) with the tender information sheet
   filled in and a compliance tracker listing every applicable requirement
   marked Mandatory/Optional, ready for the vendor to populate (Vendor Status
   / Vendor Remarks columns) and submit for review and approval. The **Vendor
   Status** column is a dropdown (*Compliant / Partially Compliant /
   Non-Compliant / Not Applicable*) so submissions stay consistent and easy to
   review, and the tracker header is frozen so it stays visible while scrolling
   a long checklist. A **Review & Approval** sheet tallies the vendor's
   submission with live formulas — counts per status, awaiting-response, a
   live *compliance rate* of the applicable requirements, and the *mandatory
   non-compliant* total (the go/no-go figure, conditionally formatted red when
   above zero and green once it clears) — plus a reviewer sign-off block with a
   fixed approval-decision dropdown.

   The checklist is **granular and derived from the guideline in detail**: the
   model decides which clauses apply to your purchase, then each selected
   clause is expanded into its individual, vendor-facing requirements taken
   **verbatim from the guideline body** — so a single clause like *5.3 Access
   Control* becomes one tracker row per obligation (MFA enforced, RBAC
   implemented, SSO integration, password policy, …) rather than one
   paraphrased summary line. M/O is set from the guideline's own wording
   (must/shall → Mandatory, should/recommended → Optional). Rows come out in
   guideline order with the real clause headings, and any clause number the
   model cited that isn't in the guideline is flagged for you to double-check.
   A **safety net** always folds in the cross-cutting compliance sections that
   apply to every procurement — Contract (4), Information Security (5) and
   Compliance & Risk (11) — so they can never be dropped even if the model
   under-selects; you're told when this happens so you can review applicability.

   The interview itself is **reverse-prompted from the guideline and tailored
   to what you're buying**: it probes applicability of the major sections
   present (cloud/SaaS hosting, personal/payment data, cybersecurity
   assessments, support level, contract duration, financial/TCO expectations,
   post-implementation reviews, deployment model), but the **item-type-specific
   questions are matched to the item** — describe "20 laptops" and you're asked
   about hardware (not which software-licensing model you prefer); describe a
   "Microsoft 365 subscription" and you're asked about software/licensing and
   integration (not to list physical hardware). Each question still maps to a
   real guideline section, and a vague item falls back to the full,
   compliance-safe question set so nothing relevant is ever skipped. **Your answers
   drive section inclusion directly:** if you say the purchase includes
   hardware, integration, support, financial/TCO obligations or
   post-implementation reviews, that whole guideline section (8, 6, 7, 10, 12)
   is pulled into the checklist deterministically — even on a weak local model
   that didn't select it — while a clear "no" keeps an irrelevant section out.
   This means the compliance list reflects what you told the interview, not
   just what the model happened to pick.

It is designed for locked-down corporate machines: it runs against a **local
LLM** served by **LM Studio** or **Ollama** (auto-detected, no cloud account
or API key needed), and ships as a **single-file `.pyz`** that needs nothing
installed beyond a Python interpreter. The Claude API is supported as an
optional backend. Use it in the terminal, or pass `--web` for a local
browser chat UI served from the same file.

For a **fully self-contained, portable** deployment with no server and no
cloud, use the **embedded small language model** backend (`--backend embedded`):
it runs a small GGUF model (Qwen2.5-1.5B-Instruct) directly in-process via
`llama-cpp-python`. The model can be **deployed together with the application**
in three ways, checked in this order: a path you pass with `--model-path`, a
model **bundled inside the zipapp** (`python scripts/build_portable.py
--with-model` produces a standalone ~1.2 GB `purchasing-coach-embedded.pyz`), or
a **`models/` folder beside the `.pyz`** (drop any `.gguf` there, or point
`EMBEDDED_MODEL_DIR` at it) — only if none of those are found does it fall back
to a one-time download. Auto-detect also picks the embedded backend
automatically when a model ships with the app. Even with **no model at all**,
the built-in `keyword`, `bm25` and `template` backends generate a guideline-
grounded interview and checklist with zero dependencies.

The source documents (`XXEON_IT_Procurement_Guideline.docx` and
`TENDER_TEMPLATE.xlsx`) live in the Google Drive **"Purchasing Guideline"**
folder. `samples/TENDER_TEMPLATE.xlsx` is the genuine Drive template
(recovered from the original binary; only standard boilerplate parts were
rebuilt). The sample guideline docx is a reconstruction with the same text —
regenerate it with `python scripts/make_samples.py`.

## Quick start (run scripts)

The fastest way to launch — these start the browser chat UI with the bundled
sample guideline and template, after checking that Python is installed:

- **Linux / macOS:** `./run.sh`
- **Windows:** double-click `run.bat` (or run it from a terminal)

Any flags you add are forwarded to the app, so the run script doubles as a
shortcut for every option below:

```bash
./run.sh                       # browser UI, bundled samples (default)
./run.sh --backend embedded    # fully offline, in-process model
./run.sh --backend ollama -m llama3.1:8b
./run.sh                       # (Windows: run.bat)
```

Point it at your own documents with environment variables (no flags needed):

```bash
GUIDELINE=MyGuideline.docx TEMPLATE=MyTemplate.xlsx ./run.sh
```

```bat
set GUIDELINE=MyGuideline.docx
set TEMPLATE=MyTemplate.xlsx
run.bat
```

The scripts prefer the prebuilt `dist/purchasing-coach.pyz`; if it's missing
they fall back to running from source (`python -m coach`).

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

4. Prefer a browser over the terminal? Add `--web`:

```
python purchasing-coach.pyz --guideline Guideline.docx --template TENDER_TEMPLATE.xlsx --web
```

This serves a chat page on `http://127.0.0.1:8765/` (localhost only) and
opens it in your default browser. The "Tender checklist" button runs the
same interview as `/tender` in the terminal and ends with a download link
for the generated workbook. `--port` changes the port, `--no-browser`
skips the auto-open.

The page is one self-contained HTML document (inline CSS/JS, system fonts,
no CDN or build step, so it works offline on locked-down machines) with:
light/dark themes (follows the OS setting, with a toggle remembered across
visits), a **Stop** button that cancels a streaming reply (Send turns into
Stop; Esc also stops), copy-to-clipboard on replies, an auto-growing input,
and accessibility built in (ARIA live region for streamed text, labelled
controls, 4.5:1 contrast, 44px touch targets, keyboard and reduced-motion
support).

The backend is auto-detected (LM Studio → Ollama → Claude API if an
`ANTHROPIC_API_KEY` is set). Pin it explicitly with `--backend lmstudio`,
`--backend ollama`, `--backend claude`, or point at any OpenAI-compatible
server with `--base-url http://host:port/v1`. Pick a model with
`--llm-model` (otherwise the first model the server reports is used).

> Tip: instruction-tuned models ≥7B (e.g. Qwen 2.5 7B Instruct, Llama 3.1 8B
> Instruct) give noticeably better checklists than smaller models.

## Models & backends

Pick a backend with `--backend <name>` (default `auto`). The app needs **no
AI model at all** to work — the `keyword`, `bm25` and `template` backends are
fully deterministic and run with zero dependencies — but a real LLM produces
the most natural chat and the smartest clause selection.

| `--backend` | What it runs | Model used | Extra dependency | Network | Best for |
|-------------|--------------|------------|------------------|---------|----------|
| `auto` *(default)* | First available of: LM Studio → Ollama → Claude API → embedded → keyword | depends on what it finds | none (lazy) | none until it reaches Claude | just works on any machine |
| `lmstudio` | [LM Studio](https://lmstudio.ai) local server (`http://localhost:1234/v1`, OpenAI-compatible) | the model loaded in LM Studio | none (stdlib HTTP) | localhost only | local GPU/CPU, friendly UI |
| `ollama` | [Ollama](https://ollama.com) (`http://localhost:11434/v1`) | the pulled/served model | none (stdlib HTTP) | localhost only | simple local CLI server |
| `claude` | Anthropic **Claude API** | `claude-opus-4-8` (override `--llm-model`) | `pip install anthropic` | cloud | highest quality, no local GPU |
| `embedded` | A **GGUF model in-process** via `llama-cpp-python` | Qwen2.5-1.5B-Instruct Q4_K_M (~1.1 GB), or any GGUF you supply | `pip install llama-cpp-python` | only the first download (or none if the model ships with the app) | fully offline, self-contained, no server |
| `keyword` | Keyword retrieval over the guideline | none | none | none | zero-dependency fallback |
| `bm25` | BM25 + cosine **hybrid retrieval** | none | none | none | better retrieval, still no model |
| `template` | Pre-authored decision-tree scenarios (hardware/software/services/cybersecurity) | none | none | none | predictable, audited guidance |

**Any OpenAI-compatible server** also works without a dedicated backend name —
use a preset or a raw URL:

```bash
# Presets (add --api-key for the cloud ones): openai, groq, together, gemini,
# vllm, text-gen-ui, ollama, lmstudio
python purchasing-coach.pyz -g Guideline.docx --provider groq --api-key $GROQ_KEY -m llama-3.1-70b-versatile
python purchasing-coach.pyz -g Guideline.docx --provider openai --api-key $OPENAI_KEY -m gpt-4o-mini

# Or point at any server directly:
python purchasing-coach.pyz -g Guideline.docx --base-url http://my-host:8000/v1 -m my-model
```

### Choosing a model

- **LM Studio / Ollama / OpenAI-compatible:** an **instruction-tuned model ≥7B**
  gives the best clause selection — e.g. *Qwen2.5-7B-Instruct*,
  *Llama-3.1-8B-Instruct*, *Mistral-7B-Instruct*. Avoid vision (`vlm`) and
  embedding-only models (the app auto-skips them on LM Studio). The granular
  requirement text is taken verbatim from the guideline, so even a modest model
  mainly needs to pick the right clauses.
- **Embedded (`--backend embedded`):** defaults to **Qwen2.5-1.5B-Instruct
  (Q4_K_M)** — small enough to ship with the app and run on a laptop CPU. Swap in
  any GGUF (e.g. a *Qwen2.5-7B-Instruct Q4_K_M*, ~4.7 GB, for better quality if
  you have the RAM) via `--model-path`, a `models/` folder beside the app, or
  `EMBEDDED_MODEL_DIR` (see below).
- **Claude:** defaults to `claude-opus-4-8`; override with `--llm-model`.

### Deploying the embedded model *with* the application

The embedded backend looks for a model in this order, so you can ship one
however suits your environment (only if none is found does it download once):

1. `--model-path /path/to/model.gguf` — an explicit file.
2. `EMBEDDED_MODEL_PATH` — same, via environment variable.
3. **Bundled inside the zipapp** — `python scripts/build_portable.py
   --with-model` builds a standalone `dist/purchasing-coach-embedded.pyz`
   (~1.2 GB) with the GGUF inside; it's extracted to the cache once on first run.
4. **A `models/` folder next to the `.pyz`** (or the loose `.gguf` beside it),
   or a folder pointed to by `EMBEDDED_MODEL_DIR` — the "ship the app + a models
   folder" layout.
5. The local cache `~/.purchasing-coach/models/`.
6. One-time download of the default model from Hugging Face.

`auto` will also select `embedded` automatically when a model is bundled or
sits beside the app.

### Command-line options

| Option | Purpose |
|--------|---------|
| `-g, --guideline PATH` | Guideline document (`.docx` / `.md` / `.txt` / `.pdf`) |
| `-t, --template PATH` | Tender template `.xlsx` (a built-in layout is used if omitted) |
| `-o, --out-dir DIR` | Where generated checklists are written |
| `-b, --backend NAME` | `auto` *(default)*, `lmstudio`, `ollama`, `claude`, `embedded`, `keyword`, `bm25`, `template` |
| `--provider NAME` | OpenAI-compatible preset: `openai`, `groq`, `together`, `gemini`, `vllm`, `text-gen-ui`, `ollama`, `lmstudio` |
| `--base-url URL` | Any OpenAI-compatible server, e.g. `http://host:port/v1` |
| `--api-key KEY` | API key for cloud OpenAI-compatible providers |
| `--model-path PATH` | GGUF file for the `embedded` backend |
| `-m, --llm-model NAME` | Model name/id (server-reported default, or `claude-opus-4-8`) |
| `-w, --web` | Serve the browser chat UI instead of the terminal |
| `-p, --port N` | Web UI port (default `8765`) |
| `--no-browser` | With `--web`, don't auto-open the browser |

### Environment variables

| Variable | Used by | Effect |
|----------|---------|--------|
| `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` | `claude`, `auto` | Enables the Claude API backend |
| `EMBEDDED_MODEL_PATH` | `embedded` | Explicit GGUF file path |
| `EMBEDDED_MODEL_DIR` | `embedded` | Folder to scan for a bundled `.gguf` |
| `GUIDELINE` / `TEMPLATE` | `run.sh` / `run.bat` | Default documents for the run scripts |

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
(sheets *Tender Information* and *Compliance Tracker*) is used. A
*Review & Approval* sheet is always added with the compliance summary and
reviewer sign-off block.

## Development

```bash
pip install -e ".[dev]"               # editable install + pytest/ruff/python-docx
python scripts/make_samples.py        # rebuild sample docx/xlsx
ruff check .                          # lint
pytest                                # offline — LLM calls are faked/mocked
python scripts/build_portable.py      # rebuild dist/purchasing-coach.pyz
```

Packaging/metadata and tool config (pytest, ruff) live in `pyproject.toml`;
installing also provides a `purchasing-coach` console script. Lint and the full
test matrix (Python 3.10–3.12) plus a portable-build smoke test run in CI on
every push/PR (`.github/workflows/ci.yml`). See
[CONTRIBUTING.md](CONTRIBUTING.md) for the dev workflow and
[CHANGELOG.md](CHANGELOG.md) for release notes.

Project layout:

- `coach/backends/` — pluggable backends (one module each): `openai_compat`
  (LM Studio/Ollama/any OpenAI-compatible server, stdlib `urllib` only),
  `claude_api`, `embedded` (in-process GGUF), and the no-model `keyword`,
  `bm25` and `template` backends; `__init__.py` is the registry/factory
- `coach/documents.py` — guideline loading (docx/md/txt/pdf → text)
- `coach/guideline.py` — clause index, granular per-clause requirement
  extraction + expansion, interview coverage questions (grounding)
- `coach/llm.py` — prompts + response parsing on top of a backend
- `coach/models.py` — dataclass models + JSON schemas for structured output
- `coach/tender.py` — interview flow
- `coach/excel.py` — template-aware checklist writer
- `coach/cli.py` — interactive CLI
- `coach/webui.py` — local browser UI (stdlib `http.server`)
- `NOTES.md` — follow-ups for the next iteration
