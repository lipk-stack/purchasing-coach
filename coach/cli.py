"""Command-line entry point for the purchasing coach chatbot."""

import argparse
import sys
from pathlib import Path

from . import __version__
from .backends import BackendError, detect_backend
from .documents import load_guideline
from .llm import Coach
from .tender import run_tender_flow

BANNER = """\
Purchasing Coach v{version} — chat with your purchasing guideline.
Guideline: {guideline}
LLM:       {backend} ({model})
Commands:
  /tender   generate a tender checklist (Excel) for an item you want to buy
  /help     show this help
  /quit     exit
Anything else is treated as a question about the guideline."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="purchasing-coach",
        description="Chat with a purchasing guideline and generate tender "
                    "checklists from an Excel template. Works with a local "
                    "LLM via LM Studio or Ollama (no cloud account needed) "
                    "or with the Claude API.",
    )
    parser.add_argument("--guideline", "-g",
                        default=_default("XXEON_IT_Procurement_Guideline.docx",
                                         "guideline_text.md"),
                        help="Path to the guideline (.docx/.md/.txt/.pdf)")
    parser.add_argument("--template", "-t",
                        default=_default("TENDER_TEMPLATE.xlsx"),
                        help="Path to the checklist template (.xlsx); "
                             "a built-in layout is used if omitted")
    parser.add_argument("--out-dir", "-o", default=".",
                        help="Directory for generated checklists")
    parser.add_argument("--backend", "-b", default="auto",
                        choices=["auto", "lmstudio", "ollama", "claude"],
                        help="LLM backend (default: auto-detect LM Studio, "
                             "then Ollama, then Claude API)")
    parser.add_argument("--base-url",
                        help="URL of any OpenAI-compatible server, e.g. "
                             "http://localhost:1234/v1")
    parser.add_argument("--llm-model", "-m",
                        help="Model name (default: first model the local "
                             "server reports / claude-opus-4-8 for Claude)")
    parser.add_argument("--web", "-w", action="store_true",
                        help="Serve a browser chat UI on localhost instead "
                             "of the terminal interface")
    parser.add_argument("--port", "-p", type=int, default=8765,
                        help="Port for the web UI (default: 8765)")
    parser.add_argument("--no-browser", action="store_true",
                        help="With --web, don't auto-open the browser")
    args = parser.parse_args(argv)

    if not args.guideline or not Path(args.guideline).exists():
        print(f"Guideline document not found: {args.guideline!r}\n"
              "Pass one with --guideline /path/to/guideline.docx",
              file=sys.stderr)
        return 2

    try:
        backend = detect_backend(args.backend, args.base_url, args.llm_model)
    except BackendError as exc:
        print(f"LLM setup failed: {exc}", file=sys.stderr)
        return 2

    guideline_text = load_guideline(args.guideline)
    coach = Coach(guideline_text, backend)

    if args.web:
        from .webui import WebUI
        WebUI(coach, backend, args.guideline, args.template,
              args.out_dir).serve(args.port, open_browser=not args.no_browser)
        return 0

    banner = BANNER.format(version=__version__, guideline=args.guideline,
                           backend=backend.name, model=backend.model)
    print(banner)
    history: list[dict] = []
    while True:
        try:
            user = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not user:
            continue
        if user in ("/quit", "/exit", "/q"):
            return 0
        if user == "/help":
            print(banner)
            continue
        if user == "/tender":
            try:
                run_tender_flow(coach, args.template, args.out_dir)
            except KeyboardInterrupt:
                print("\nTender flow cancelled.")
            except Exception as exc:  # surface LLM errors without dying
                print(f"Tender generation failed: {exc}", file=sys.stderr)
            continue

        history.append({"role": "user", "content": user})
        print("coach> ", end="", flush=True)
        reply_parts: list[str] = []
        try:
            for text in coach.answer(history):
                reply_parts.append(text)
                print(text, end="", flush=True)
            print()
        except Exception as exc:
            print(f"\nRequest failed: {exc}", file=sys.stderr)
            history.pop()
            continue
        history.append({"role": "assistant", "content": "".join(reply_parts)})


def _default(*names: str) -> str | None:
    """Find a bundled sample file next to the package, if present.

    Inside a zipapp there is no real filesystem next to the package, so this
    simply returns None and the user passes --guideline/--template.
    """
    try:
        samples = Path(__file__).resolve().parent.parent / "samples"
        for name in names:
            candidate = samples / name
            if candidate.exists():
                return str(candidate)
    except OSError:
        pass
    return None


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
