"""Interactive tender-generation flow: interview the user, write the xlsx."""

import re
from datetime import date
from pathlib import Path
from collections.abc import Callable

from .excel import write_checklist
from .llm import Coach

# Callback signature: (current_step, total_steps, question_text)
ProgressCallback = Callable[[int, int, str], None]


def run_tender_flow(coach: Coach, template_path: str | Path | None,
                    out_dir: str | Path = ".",
                    ask=input, say=print,
                    on_progress: ProgressCallback | None = None) -> Path | None:
    """Run the question/answer flow and write the checklist workbook.

    ``ask``/``say`` are injectable for testing.
    ``on_progress`` is called before each question with (step, total, question).
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
        if on_progress:
            on_progress(i, len(plan.questions), q.question)
        reply = ask(f"[{i}/{len(plan.questions)}] {q.question}\n> ").strip()
        answers.append((q.question, reply or "TBC"))

    say("\nBuilding the compliance checklist from the guideline...")
    checklist = coach.build_checklist(item, answers)

    out_path = Path(out_dir) / output_name(checklist.tender_info.purchase_item)
    write_checklist(checklist.tender_info, checklist.requirements,
                    out_path, template_path)
    say(f"\nDone. {len(checklist.requirements)} requirements written to: {out_path}")
    if checklist.added_core_sections:
        secs = ", ".join(checklist.added_core_sections)
        say(f"Note: guideline section(s) {secs} were added automatically "
            "to ensure full coverage (cross-cutting compliance plus sections "
            "your answers flagged as relevant) — review whether every row "
            "applies.")
    if checklist.unverified_refs:
        refs = ", ".join(checklist.unverified_refs)
        say(f"Note: {len(checklist.unverified_refs)} clause reference(s) "
            f"could not be matched to the guideline ({refs}) — please verify "
            "those rows.")
    say("Review the 'Tender Information' and 'Compliance Tracker' sheets "
        "before sending anything to vendors — the guideline itself must not "
        "be shared externally. Vendors pick a Vendor Status (Compliant / "
        "Partially Compliant / Non-Compliant / Not Applicable) from the "
        "dropdown and explain in Vendor Remarks, then return it for review. "
        "The 'Review & Approval' sheet then tallies their submission live "
        "(compliance rate and any mandatory non-compliant rows, flagged red) "
        "for your sign-off and approval decision.")
    return out_path


def output_name(item: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", item).strip("_")[:40] or "tender"
    return f"TENDER_CHECKLIST_{slug}_{date.today():%Y%m%d}.xlsx"
