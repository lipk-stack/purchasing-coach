# Purchasing Coach — Portable Edition

A self-contained purchasing-guideline chatbot and tender-checklist generator.
Unzip it, double-click the launcher for your operating system, and a browser
chat UI opens. Nothing to install except Python.

## What's inside

```
purchasing-coach-portable/
├── purchasing-coach.pyz       the whole application in one file
│   (or purchasing-coach-embedded.pyz — bundles an on-device AI model)
├── run.command                macOS  — double-click to launch
├── run.sh                     Linux  — ./run.sh to launch
├── run.bat                    Windows — double-click to launch
├── samples/                   the guideline + tender template to start from
│   ├── XXEON_IT_Procurement_Guideline.docx
│   └── TENDER_TEMPLATE.xlsx
└── README.md                  this guide
```

## Requirements

- **Python 3.10 or newer** on your PATH — [download](https://www.python.org/downloads/)
  - **Windows:** tick *"Add Python to PATH"* during install.
  - **macOS:** install from python.org, or `brew install python`.
  - **Linux:** use your package manager, e.g. `sudo apt install python3`.
- The **embedded** edition (`*-embedded.pyz`) additionally needs **~2 GB free
  RAM** for the on-device AI model. The standard edition needs almost nothing.

## Quick start

| Operating system | How to launch |
|------------------|---------------|
| **macOS**   | Double-click **`run.command`** (first time: right-click → *Open* to clear Gatekeeper). |
| **Windows** | Double-click **`run.bat`**. |
| **Linux**   | Run **`./run.sh`** in a terminal (`chmod +x run.sh` if needed). |

Your browser opens at <http://localhost:8765>. Ask questions about the
guideline, or generate a tender checklist.

> **macOS tip:** if double-clicking shows *"cannot be opened because it is from
> an unidentified developer"*, right-click `run.command` → **Open** → **Open**.
> You only need to do this once.

## Using the chatbot

In the browser UI (or a terminal session) you can type:

- `/tender` — generate a tender compliance checklist (Excel) for an item. The
  bot interviews you about the purchase, then writes a granular, guideline-
  derived checklist (`TENDER_CHECKLIST_*.xlsx`) for vendors to fill in and you
  to review on the built-in **Review & Approval** sheet.
- `/help` — show available commands.
- `/quit` — exit.

## Using your own documents

**Easiest: replace the files in `samples/`.** Put your guideline and template
into the `samples/` folder using the same filenames
(`XXEON_IT_Procurement_Guideline.docx` and `TENDER_TEMPLATE.xlsx`), then launch
as usual. The launcher checks the files exist before starting, prints which
guideline and template it's using so you can confirm, and falls back to a
built-in checklist layout if the template is missing.

**Or point at any path** with environment variables or flags:

**macOS / Linux**

```sh
GUIDELINE=/path/to/your/guideline.docx TEMPLATE=/path/to/template.xlsx ./run.sh
# or
./run.sh --guideline your-guideline.docx --template your-template.xlsx
```

**Windows**

```cmd
set GUIDELINE=C:\path\to\your\guideline.docx
set TEMPLATE=C:\path\to\your\template.xlsx
run.bat
```

Guidelines can be `.docx`, `.pdf`, `.md`, or `.txt`.

### Make sure your guideline produces a checklist

The checklist is built from the guideline's **numbered clauses**, so your
document needs numbered headings like `4 Contract Requirements` and `4.1
Standard Terms` — as Word heading styles (with the number in the heading text),
as plain `N.M Title` lines, or via Word's automatic heading numbering. If no
numbered sections are detected the app shows a heads-up (a banner in the browser
UI) rather than producing an empty checklist; add numbered headings and re-run.

If you supply your own **template**, name its sheets `Tender Information` and
`Compliance Tracker` and give the tracker a header row with `Seq, Ref, Section,
Requirement, M/O, Vendor Status, Vendor Remarks` so your sheets are filled in
place; otherwise the app adds its own sheets. Omit the template to use the
built-in layout.

## Options

These flags work on every launcher (`run.command` / `run.sh` / `run.bat`):

```
--backend keyword    No-AI, deterministic search (default for the standard build)
--backend embedded   Force the bundled on-device AI model (embedded build only)
--backend ollama     Use a local Ollama server
--backend lmstudio   Use a local LM Studio server
--n-ctx 16384        Larger context window for very long guidelines (embedded)
--web                Open the browser chat UI (the default when no flags given)
--port 9000          Serve the web UI on a different port
--verbose            Show debug output
```

## Privacy

The standard build runs entirely on your machine with no network calls. The
embedded build also runs its AI model (Qwen2.5-1.5B) fully on-device — no data
leaves your computer. The guideline itself is for internal use and must not be
shared with vendors; only the generated checklist is for vendor completion.
