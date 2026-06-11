"""Interactive tender-generation flow: interview the user, write the xlsx."""

import re
from datetime import date
from pathlib import Path

from .excel import write_checklist
from .llm import Coach


def run_tender_flow(coach: Coach, template_path: str | Path | None,
                    out_dir: str | Path = ".",
                    ask=input, say=print) -> Path | None:
    """Run the question/answer flow and write the checklist workbook.

    ``ask``/``say`` are injectable for testing.
    """
    say("\n=== Tender checklist generator ===")
    item = ask("What do you want to buy? Describe the item/solution: ").strip()
    if not item:
        say("No item given — cancelled.")
        return None

    say("\nThinking about the right questions for this purchase...\n")
    plan = coach.plan_interview(item)

    answers: list[tuple[str, str]] = []
    for i, q in enumerate(plan.questions, start=1):
        reply = ask(f"[{i}/{len(plan.questions)}] {q.question}\n> ").strip()
        answers.append((q.question, reply or "TBC"))

    say("\nBuilding the compliance checklist from the guideline...")
    checklist = coach.build_checklist(item, answers)

    out_path = Path(out_dir) / output_name(checklist.tender_info.purchase_item)
    write_checklist(checklist.tender_info, checklist.requirements,
                    out_path, template_path)
    say(f"\nDone. {len(checklist.requirements)} requirements written to: {out_path}")
    say("Review the 'Tender Information' and 'Compliance Tracker' sheets "
        "before sending anything to vendors — the guideline itself must not "
        "be shared externally.")
    return out_path


def output_name(item: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", item).strip("_")[:40] or "tender"
    return f"TENDER_CHECKLIST_{slug}_{date.today():%Y%m%d}.xlsx"
