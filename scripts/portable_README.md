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

Set environment variables before launching, or pass flags directly.

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
