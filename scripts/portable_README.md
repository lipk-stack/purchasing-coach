# Purchasing Coach — Portable Edition

A self-contained purchasing guideline chatbot with an embedded AI model.
No LM Studio, Ollama, API keys, or downloads required.

## Requirements

- **Windows 10/11** (64-bit)
- **Python 3.10+** on your PATH ([download](https://www.python.org/downloads/))
  - Tick "Add Python to PATH" during install
- **~2 GB free RAM** (for the embedded AI model)

## Quick Start

1. Double-click `run.bat`
2. Your browser opens at `http://localhost:8765`
3. Ask questions about the purchasing guideline

## Commands

In the chat UI or terminal:

- `/tender` — generate a tender checklist (Excel) for an item
- `/help` — show available commands
- `/quit` — exit

## Using Your Own Documents

Set environment variables before launching:

```cmd
set GUIDELINE=C:\path\to\your\guideline.docx
set TEMPLATE=C:\path\to\your\template.xlsx
run.bat
```

Or pass flags directly:

```cmd
run.bat --guideline your-guideline.docx --template your-template.xlsx
```

## Options

```
--backend embedded   Force the embedded AI model (default)
--backend keyword    Use the keyword search backend (faster, less smart)
--n-ctx 16384        Increase context window for very long guidelines
--web                Open browser chat UI (default when no flags given)
--port 9000          Use a different port for the web UI
--verbose            Show debug output
```

## What's Inside

- `purchasing-coach-embedded.pyz` — the application with a bundled AI model
- `samples/` — sample guideline and template documents
- `run.bat` — Windows launcher script

The embedded AI model (Qwen2.5-1.5B) runs entirely on your machine.
No data is sent to any external server.
