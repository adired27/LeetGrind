# LeetGrind

A terminal trainer for building **coding-interview pattern recognition** through
**forced spaced repetition**. Instead of grinding random LeetCode problems, you
drill a curated bank organized by *pattern → problem*, and an SM-2 scheduler
keeps resurfacing each problem right as you're about to forget it. The goal:
after a couple of weeks of short daily sessions, you *see the pattern* the moment
you read a prompt — before you ever open LeetCode.

The pattern taxonomy and roadmap order follow the structure of ByteByteGo's
*Coding Interview Patterns*. All problem statements, reference solutions,
diagrams, explanations, and tests in this tool are original content written for
LeetGrind; problem **names** map to the well-known LeetCode equivalents so you
can cross-reference.

---

## Quick start

```bash
pip install rich          # the only dependency
python run.py             # launch the trainer
```

Optional sanity check (no interaction, exits 0 on success):

```bash
python run.py --selftest
```

Requires Python 3.10+ (uses `list[int]`-style hints and the stdlib `sqlite3`).

---

## How a session works

From the main menu you can start a **Daily Grind** (whatever's due across all
patterns, plus a few new cards), a **Pattern Drill** (focus one pattern), or
**Browse** the bank.

Each card runs the same loop:

1. **Read** the problem + examples. A timer starts.
2. **Choose your mode:**
   - **Code mode** — LeetGrind drops a stub file (with the signature and helper
     types pre-wired) into your `$EDITOR`. Write a real solution; on save it's
     run against the test cases in an isolated subprocess with a timeout, and
     you get a pass/fail report with the first failing case.
   - **Recall mode** — a flashcard. Think through the approach, then reveal.
3. **Reveal** the reference solution: a clean, self-contained implementation,
   an ASCII diagram where it helps, a "why this works" explanation, and the
   complexity.
4. **Rate yourself** — `Again / Hard / Good / Easy`. That rating feeds the
   scheduler, which sets when you'll next see the card (today, tomorrow, in N
   days…), and logs the attempt (mode, time taken, pass/fail, timestamp).

### The game layer

- **XP + levels** — every review earns XP (more for first solves and passing
  code runs); 100 XP per level.
- **Daily streak** — practice on consecutive days to keep it alive.
- **Mastery roadmap** — the 19 patterns render as a dependency graph with a
  progress bar each; a card counts as *mastered* once it's been recalled
  several times and its interval has stretched past a week.

---

## Spaced repetition (SM-2)

Each problem is a flashcard with `ease`, `interval`, and `reps`. Ratings map to
SM-2 quality scores:

| Button | Meaning                       | Effect                                  |
|--------|-------------------------------|-----------------------------------------|
| Again  | blanked / couldn't reproduce  | resets the rep chain, due again now     |
| Hard   | got it but it was a slog       | shorter interval                        |
| Good   | solid, normal recall           | standard SM-2 growth (1d → 6d → ×ease)  |
| Easy   | instant                        | longer interval, ease bumps up          |

Overdue cards are always prioritized over new ones, so the queue self-balances:
miss a day and you get caught up before you're fed anything new.

---

## Where your data lives

Everything is local SQLite at `~/.leetgrind/progress.db` (cards, attempt log,
XP, streak). Override the location with the `LEETGRIND_DB` environment variable
— handy for keeping separate profiles or a throwaway DB:

```bash
LEETGRIND_DB=/tmp/scratch.db python run.py
```

Code-mode scratch files live under `~/.leetgrind/scratch/` so your in-progress
solutions persist between attempts.

---

## What ships

16 starter problems across 7 foundational patterns, enough for a meaningful
multi-week repetition cycle:

- **Two Pointers** — Pair Sum (sorted), Valid Palindrome, Largest Container
- **Hash Maps & Sets** — Pair Sum (unsorted), Valid Anagram, Contains Duplicate
- **Binary Search** — Search Insert Position, First & Last Occurrences
- **Sliding Windows** — Max Sum Window (size k), Longest Substring w/o Repeats
- **Prefix Sums** — Subarray Sum Equals K, Product of Array Except Self
- **Fast & Slow Pointers** — Happy Number, Find the Duplicate
- **Stacks** — Valid Parentheses, Next Greater Element

The remaining 12 patterns from the roadmap (Linked Lists, Heaps, Intervals,
Trees, Tries, Graphs, Backtracking, DP, Greedy, Sort & Search, Bit Manipulation,
Math & Geometry) are already wired into the roadmap UI as "coming soon" slots —
drop in problem files and they light up automatically.

---

## Adding your own problems

Adding a problem is one self-contained file — no registry to edit, the loader
discovers it automatically.

1. Copy `leetgrind/problems/_TEMPLATE.py` to
   `leetgrind/problems/<pattern_slug>/<short_name>.py`.
2. Fill in the `PROBLEM` dict, write `reference()`, and list `TESTS` (just the
   inputs — expected outputs are computed by running your reference, so the
   answer key can never disagree with the solution).
3. Run `python run.py --selftest` to confirm it loads, runs, and grades.

Three rules the self-test enforces:

- Test inputs and reference outputs must be **JSON-serializable** (the grader
  speaks JSON to a subprocess). Model linked-list/tree problems as plain lists
  in and out.
- `reference()` must be **self-contained** — nest any helper inside it, since
  its source is what's shown as the reference solution.
- For order-insensitive answers, add `check(args, got, expected) -> bool` and
  compare canonically (e.g. `sorted(...)`).

To add a brand-new pattern, append a row to `PATTERNS` in
`leetgrind/patterns.py` (slug, name, prerequisites, `seeded=True`) and create
the matching `leetgrind/problems/<slug>/` directory.

---

## Project layout

```
leetgrind/
  run.py            launcher (python run.py [--selftest])
  selftest.py       non-interactive validation of the whole engine
  requirements.txt  rich
  leetgrind/
    patterns.py     the 19-pattern roadmap + dependency edges
    content.py      auto-discovers problem modules -> Problem objects
    scheduler.py    SM-2 spaced repetition + session building
    storage.py      SQLite: cards, attempts, XP, streak
    runner.py       editor stub + isolated subprocess grader
    ui.py           rich rendering (cards, reports, roadmap, stats)
    app.py          the interactive loop
    commons.py      ListNode/TreeNode + helpers for the solution sandbox
    problems/
      _TEMPLATE.py  copy this to add a problem
      <pattern>/<problem>.py
```

---

## Notes

- The interactive TUI needs a real terminal (it reads keys and opens your
  editor). `--selftest` covers all the non-interactive logic and is safe to run
  in CI.
- Code mode uses `$VISUAL`/`$EDITOR` and falls back to nano/vim/vi/notepad. Set
  `EDITOR` if it can't find one: `export EDITOR=nano`.
