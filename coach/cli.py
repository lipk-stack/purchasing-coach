"""Command-line entry point for the purchasing coach chatbot."""

import argparse
import sys
from pathlib import Path

from . import __version__
from .backends import BackendError, get_backend, list_backends
from .backends.openai_compat import PROVIDER_PRESETS
from .documents import load_guideline
from .format import StreamPrinter, enable_windows_ansi
from .guideline import guideline_notice
from .llm import Coach
from .tender import run_tender_flow

BANNER = """\
Purchasing Coach v{version} — chat with your purchasing guideline.
Guideline: {guideline}
Backend:   {backend} ({model})
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
                    "LLM via LM Studio or Ollama (no cloud account needed), "
                    "any OpenAI-compatible API, the Claude API, a built-in "
                    "embedded small language model (no server needed), or "
                    "keyword/template/BM25 backends (no model required).",
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
                        choices=list_backends(),
                        help="AI backend (default: auto-detect LM Studio, "
                             "then Ollama, then Claude API, then keyword)")
    parser.add_argument("--base-url",
                        help="URL of any OpenAI-compatible server, e.g. "
                             "http://localhost:1234/v1")
    parser.add_argument("--provider",
                        choices=list(PROVIDER_PRESETS.keys()),
                        help="Provider preset for OpenAI-compatible backends "
                             "(e.g. openai, groq, together, gemini)")
    parser.add_argument("--api-key",
                        help="API key for cloud providers (openai-compat "
                             "backend)")
    parser.add_argument("--model-path",
                        help="Path to a local GGUF model file (embedded "
                             "backend). If omitted, looks for a model shipped "
                             "with the app (bundled, or a models/ folder beside "
                             "it), then the cache, then auto-downloads "
                             "Qwen2.5-1.5B.")
    parser.add_argument("--n-ctx", type=int, default=8192,
                        help="Context window size in tokens for the embedded "
                             "backend (default: 8192). Larger values allow "
                             "longer guidelines but use more RAM.")
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
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging to stderr")
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    if not args.guideline or not Path(args.guideline).exists():
        print(f"Guideline document not found: {args.guideline!r}\n"
              "Pass one with --guideline /path/to/guideline.docx",
              file=sys.stderr)
        return 2

    try:
        backend = get_backend(
            args.backend,
            base_url=args.base_url,
            model=args.llm_model,
            api_key=args.api_key,
            provider=args.provider,
            model_path=args.model_path,
            n_ctx=args.n_ctx,
        )
    except BackendError as exc:
        print(f"Backend setup failed: {exc}", file=sys.stderr)
        return 2

    try:
        guideline_text = load_guideline(args.guideline)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Could not load the guideline: {exc}", file=sys.stderr)
        return 2
    coach = Coach(guideline_text, backend)

    notice = guideline_notice(coach.clauses)
    if notice:
        print(notice, file=sys.stderr)

    if args.web:
        from .webui import WebUI
        WebUI(coach, backend, args.guideline, args.template,
              args.out_dir).serve(args.port, open_browser=not args.no_browser)
        return 0

    banner = BANNER.format(version=__version__, guideline=args.guideline,
                           backend=backend.name, model=backend.model)
    print(banner)
    enable_windows_ansi()
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
        printer = StreamPrinter()
        try:
            for text in coach.answer(history):
                reply_parts.append(text)
                printer.feed(text)
            printer.close()
            print()
        except Exception as exc:
            print(f"\nRequest failed: {exc}", file=sys.stderr)
            history.pop()
            continue
        history.append({"role": "assistant", "content": "".join(reply_parts)})


def _configure_logging(verbose: bool) -> None:
    """Send the ``coach`` logger to stderr; DEBUG with --verbose, else WARNING.

    Sets the package logger level explicitly (not just ``basicConfig``, which is
    a no-op when the host application already configured logging) so --verbose
    always takes effect.
    """
    import logging

    level = logging.DEBUG if verbose else logging.WARNING
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(levelname)s %(name)s: %(message)s",
            stream=sys.stderr,
        )
    logging.getLogger("coach").setLevel(level)


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
