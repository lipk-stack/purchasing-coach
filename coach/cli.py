"""Command-line entry point for the purchasing coach chatbot."""

import argparse
import os
import sys
from pathlib import Path

from . import DEFAULT_MODEL, __version__
from .documents import load_guideline
from .llm import Coach
from .tender import run_tender_flow

BANNER = """\
Purchasing Coach v{version} — chat with your purchasing guideline.
Loaded guideline: {guideline}
Commands:
  /tender   generate a tender checklist (Excel) for an item you want to buy
  /help     show this help
  /quit     exit
Anything else is treated as a question about the guideline."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="purchasing-coach",
        description="Chat with a purchasing guideline and generate tender "
                    "checklists from an Excel template.",
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
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("Note: no ANTHROPIC_API_KEY found in the environment. "
              "Set it before chatting:\n  export ANTHROPIC_API_KEY=sk-ant-...",
              file=sys.stderr)

    if not args.guideline or not Path(args.guideline).exists():
        print(f"Guideline document not found: {args.guideline!r}\n"
              "Pass one with --guideline /path/to/guideline.docx", file=sys.stderr)
        return 2

    guideline_text = load_guideline(args.guideline)
    coach = Coach(guideline_text, model=args.model)

    print(BANNER.format(version=__version__, guideline=args.guideline))
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
            print(BANNER.format(version=__version__, guideline=args.guideline))
            continue
        if user == "/tender":
            try:
                run_tender_flow(coach, args.template, args.out_dir)
            except KeyboardInterrupt:
                print("\nTender flow cancelled.")
            except Exception as exc:  # surface API errors without dying
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
    """Find a bundled sample file next to the package, if present."""
    samples = Path(__file__).resolve().parent.parent / "samples"
    for name in names:
        candidate = samples / name
        if candidate.exists():
            return str(candidate)
    return None


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
