"""The interactive game loop."""
from __future__ import annotations

import os
import time

from rich.prompt import Prompt

from . import ui
from .content import load_all, grouped_by_pattern
from .patterns import NAME_BY_SLUG, SEEDED_SLUGS
from .runner import make_stub, open_in_editor, grade_file
from .scheduler import (
    schedule, build_session, session_counts, xp_for,
    RATING_LABEL, AGAIN, HARD, GOOD, EASY,
)
from .storage import Store, _db_path

MASTERY_REPS = 3
MASTERY_INTERVAL = 7


def mastered(card):
    return bool(card) and card.get("reps", 0) >= MASTERY_REPS and card.get("interval", 0) >= MASTERY_INTERVAL


def _scratch_path(prob):
    root = os.path.join(os.path.dirname(_db_path()), "scratch")
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, prob.id.replace("/", "__") + ".py")


# ---------------------------------------------------------------- review
def _next_due_phrase(new_state):
    iv = int(new_state["interval"])
    if iv <= 0:
        return "[red]again today[/]"
    if iv == 1:
        return "[yellow]tomorrow[/]"
    return f"[green]in {iv} days[/]"


def _rate_and_record(store, prob, mode, passed, solve_seconds):
    ui.rating_help()
    choice = Prompt.ask("Rate", choices=["1", "2", "3", "4"], default="3")
    rating = int(choice)

    card = store.get_card(prob.id)
    first_time = not store.attempts_for(prob.id)
    new_state = schedule(card, rating)
    store.upsert_card(prob.id, new_state["ease"], new_state["interval"],
                      new_state["reps"], new_state["lapses"], new_state["due"])
    store.log_attempt(prob.id, mode, passed, solve_seconds, rating)

    gained = xp_for(rating, first_time, passed is True)
    store.add_xp(gained)
    store.touch_streak()

    ui.console.print(
        f"[grey62]Logged {RATING_LABEL[rating]}"
        + (f" · {solve_seconds:.0f}s" if solve_seconds else "")
        + f" · [bright_magenta]+{gained} XP[/][grey62] · next review {_next_due_phrase(new_state)}[grey62].[/]\n"
    )


def review_one(store, prob, position=None, total=None):
    """Run one card. Returns 'continue' or 'quit'."""
    ui.clear()
    card = store.get_card(prob.id)
    ui.banner(store.get_streak(), store.get_xp(), 0, 0, 0) if False else None
    ui.problem_card(prob, card, position, total)

    hinted = False
    while True:
        action = Prompt.ask(
            "[bold]Action[/]  [cyan]c[/]ode  [cyan]r[/]ecall  [cyan]h[/]int  [cyan]s[/]kip  [cyan]q[/]uit",
            choices=["c", "r", "h", "s", "q"], default="r",
        )
        if action == "h":
            if not hinted:
                ui.show_hint(prob)
                hinted = True
            else:
                ui.console.print("[grey50](hint already shown)[/]")
            continue
        if action == "s":
            ui.console.print("[grey50]Skipped — no schedule change.[/]\n")
            return "continue"
        if action == "q":
            return "quit"
        if action == "r":
            return _recall_mode(store, prob)
        if action == "c":
            return _code_mode(store, prob)


def _recall_mode(store, prob):
    start = time.time()
    ui.console.print("[grey62]Think it through… solve it in your head or on paper / LeetCode.[/]")
    Prompt.ask("[bold]Press Enter to reveal the solution[/]", default="")
    solve_seconds = time.time() - start
    ui.reveal_solution(prob)
    _rate_and_record(store, prob, "recall", None, solve_seconds)
    return "continue"


def _code_mode(store, prob):
    path = _scratch_path(prob)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(make_stub(prob))
    ui.console.print(f"[grey62]Opening your editor on[/] {path}")
    start = time.time()
    opened = open_in_editor(path)
    solve_seconds = time.time() - start
    if not opened:
        ui.console.print(
            "[yellow]No editor found.[/] Set $EDITOR (e.g. `export EDITOR=nano`), "
            f"or edit this file yourself then re-run:\n  {path}\n"
            "Falling back to recall mode for now."
        )
        return _recall_mode(store, prob)

    report = grade_file(prob, path)
    ui.grade_report(report)
    ui.reveal_solution(prob)
    _rate_and_record(store, prob, "code", report["passed"], solve_seconds)
    return "continue"


# ---------------------------------------------------------------- sessions
def run_session(store, problems, session):
    if not session:
        ui.console.print("[green]Nothing queued right now — come back when cards are due, "
                         "or start a Pattern Drill to pull in new ones.[/]")
        Prompt.ask("[grey50]Enter to return[/]", default="")
        return
    total = len(session)
    for i, prob in enumerate(session, 1):
        result = review_one(store, prob, i, total)
        if result == "quit":
            break
    ui.console.print(f"[bold green]Session done.[/] Reviewed up to {i} card(s).")
    Prompt.ask("[grey50]Enter to return to the menu[/]", default="")


def daily_grind(store, problems):
    cards = store.all_cards()
    session = build_session(problems, cards, max_due=20, max_new=5)
    run_session(store, problems, session)


def pattern_drill(store, problems):
    groups = grouped_by_pattern(problems)
    seeded = [s for s in SEEDED_SLUGS if s in groups]
    ui.console.print("[bold]Pick a pattern to drill:[/]")
    for idx, slug in enumerate(seeded, 1):
        c = session_counts(problems, store.all_cards(), slug)
        ui.console.print(f"  [cyan]{idx}[/]  {NAME_BY_SLUG[slug]:<22} "
                         f"[yellow]{c['due']} due[/] · [green]{c['new']} new[/] · {c['total']} total")
    ui.console.print("  [cyan]b[/]  back")
    choice = Prompt.ask("Pattern", choices=[str(i) for i in range(1, len(seeded) + 1)] + ["b"],
                        default="b")
    if choice == "b":
        return
    slug = seeded[int(choice) - 1]
    cards = store.all_cards()
    session = build_session(problems, cards, max_due=20, max_new=8, pattern_slug=slug)
    run_session(store, problems, session)


def browse(store, problems):
    groups = grouped_by_pattern(problems)
    flat = []
    ui.console.print("[bold]All problems:[/]")
    n = 0
    for slug, probs in groups.items():
        ui.console.print(f"[grey62]── {NAME_BY_SLUG.get(slug, slug)} ──[/]")
        for p in probs:
            n += 1
            flat.append(p)
            card = store.get_card(p.id)
            tag = "[green]mastered[/]" if mastered(card) else (
                "[yellow]learning[/]" if card else "[grey50]new[/]")
            ui.console.print(f"  [cyan]{n:>2}[/]  {p.title:<42} "
                             f"[{ui.DIFF_COLOR.get(p.difficulty,'white')}]{p.difficulty:<6}[/] {tag}")
    ui.console.print("  [cyan] b[/]  back")
    choice = Prompt.ask("Pick a number", choices=[str(i) for i in range(1, n + 1)] + ["b"],
                        default="b")
    if choice == "b":
        return
    prob = flat[int(choice) - 1]
    review_one(store, prob)
    Prompt.ask("[grey50]Enter to return[/]", default="")


def show_stats(store, problems):
    groups = grouped_by_pattern(problems)
    cards = store.all_cards()
    ui.mastery_roadmap(groups, cards, mastered)
    mastered_total = sum(1 for p in problems.values() if mastered(cards.get(p.id)))
    ui.stats_panel(store.get_streak(), store.get_xp(), store.attempt_count(),
                   len(store.active_days()), mastered_total, len(problems))
    Prompt.ask("[grey50]Enter to return[/]", default="")


# ---------------------------------------------------------------- entry
def main():
    problems = load_all()
    store = Store()
    if not problems:
        ui.console.print("[red]No problems found in the bank.[/]")
        return
    try:
        while True:
            ui.clear()
            cards = store.all_cards()
            counts = session_counts(problems, cards)
            store_streak = store.get_streak()
            ui.banner(store_streak, store.get_xp(), counts["due"], counts["new"], len(problems))
            ui.main_menu()
            choice = Prompt.ask("Choose", choices=["1", "2", "3", "4", "q"], default="1")
            if choice == "1":
                daily_grind(store, problems)
            elif choice == "2":
                pattern_drill(store, problems)
            elif choice == "3":
                browse(store, problems)
            elif choice == "4":
                show_stats(store, problems)
            elif choice == "q":
                ui.console.print("[bold dark_violet]Keep grinding. See you tomorrow.[/]")
                break
    finally:
        store.close()
