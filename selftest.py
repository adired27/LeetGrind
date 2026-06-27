#!/usr/bin/env python3
"""Non-interactive self-test for LeetGrind.

Validates everything that doesn't need a human at a keyboard:

  1. Every problem module loads and has a well-formed PROBLEM dict.
  2. Every reference solution runs on its own TESTS without crashing, and
     its inputs + outputs are JSON-serializable (required by the subprocess
     grader, which speaks JSON over stdin/stdout).
  3. The SM-2 scheduler behaves (intervals grow on Good/Easy, reset on Again)
     and build_session / session_counts pick sane queues.
  4. Storage round-trips card state, attempts, XP and streak in a temp DB.
  5. The real subprocess grader passes a known-good solution (each problem's
     own reference) and fails an obviously wrong one.

Run:  python selftest.py     (exit code 0 = all good)
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
import textwrap
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from leetgrind import scheduler
from leetgrind.content import load_all, grouped_by_pattern
from leetgrind.patterns import PATTERNS, SEEDED_SLUGS, NAME_BY_SLUG
from leetgrind.runner import grade_file, _HELPERS_SRC
from leetgrind.scheduler import schedule, build_session, session_counts, AGAIN, HARD, GOOD, EASY
from leetgrind.storage import Store

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

_failures = []


def check(name, cond, detail=""):
    mark = PASS if cond else FAIL
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        _failures.append((name, detail))
    return cond


def _json_safe(x):
    try:
        json.dumps(x)
        return True
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------
def test_metadata(problems):
    print("\n[1] Problem metadata")
    required = {
        "id", "pattern_slug", "title", "difficulty", "order", "statement",
        "signature", "func_name", "examples",
    }
    seeded = set(SEEDED_SLUGS)
    ok = True
    for pid, p in problems.items():
        meta_ok = all(getattr(p, k, None) not in (None, "") for k in
                      ("id", "pattern_slug", "title", "signature", "func_name"))
        ok &= check(f"{pid}: required fields present", meta_ok)
        ok &= check(f"{pid}: pattern is in roadmap", p.pattern_slug in NAME_BY_SLUG)
        ok &= check(f"{pid}: pattern marked seeded", p.pattern_slug in seeded)
        ok &= check(f"{pid}: func_name appears in signature",
                    p.func_name in p.signature)
        ok &= check(f"{pid}: has >=1 example", len(p.examples) >= 1)
        ok &= check(f"{pid}: has tests", len(p.tests) >= 1)
    return ok


def test_references(problems):
    print("\n[2] Reference solutions run + JSON-serializable I/O")
    ok = True
    for pid, p in problems.items():
        for i, args in enumerate(p.tests):
            label = f"{pid} case {i}"
            ok &= check(f"{label}: args JSON-safe", _json_safe(list(args)))
            try:
                # clone args the same way the grader does so mutation is isolated
                cloned = [json.loads(json.dumps(a)) if isinstance(a, (list, dict))
                          else a for a in args]
                out = p.reference(*cloned)
            except Exception as e:
                check(f"{label}: reference runs", False, repr(e))
                ok = False
                continue
            ok &= check(f"{label}: output JSON-safe", _json_safe(out))
            # reference must be self-consistent with its own check()
            ok &= check(f"{label}: check(ref output) is True",
                        p.check(args, out, out))
    return ok


def test_scheduler():
    print("\n[3] SM-2 scheduler")
    ok = True
    # New card, pressed Good -> interval 1, reps 1
    s1 = schedule(None, GOOD)
    ok &= check("new+Good -> interval 1, reps 1",
                s1["interval"] == 1 and s1["reps"] == 1, str(s1))
    # Second Good -> interval 6
    s2 = schedule(s1, GOOD)
    ok &= check("2nd Good -> interval 6", s2["interval"] == 6, str(s2))
    # Third Good -> interval grows beyond 6
    s3 = schedule(s2, GOOD)
    ok &= check("3rd Good -> interval > 6", s3["interval"] > 6, str(s3))
    # Again resets reps and makes it due immediately
    sA = schedule(s3, AGAIN)
    ok &= check("Again -> reps 0 + interval 0",
                sA["reps"] == 0 and sA["interval"] == 0, str(sA))
    ok &= check("Again -> lapses incremented", sA["lapses"] == 1, str(sA))
    # Easy interval >= Good interval from same state
    eG = schedule(s2, GOOD)["interval"]
    eE = schedule(s2, EASY)["interval"]
    ok &= check("Easy interval >= Good interval", eE >= eG, f"good={eG} easy={eE}")
    # Ease never drops below the floor
    card = None
    for _ in range(10):
        card = schedule(card, AGAIN)
    ok &= check("ease floored at 1.3", card["ease"] >= 1.3, str(card["ease"]))
    return ok


def test_session(problems):
    print("\n[4] Session building")
    ok = True
    cards = {}  # everything new
    sess = build_session(problems, cards, max_new=5)
    ok &= check("fresh session returns up to max_new", len(sess) == 5, str(len(sess)))
    counts = session_counts(problems, cards)
    ok &= check("counts: all new", counts["new"] == len(problems), str(counts))
    ok &= check("counts: total matches", counts["total"] == len(problems), str(counts))
    # Pattern filter
    sess_tp = build_session(problems, cards, pattern_slug="two_pointers", max_new=10)
    ok &= check("pattern filter keeps only that pattern",
                all(p.pattern_slug == "two_pointers" for p in sess_tp),
                str([p.id for p in sess_tp]))
    return ok


def test_storage(problems):
    print("\n[5] Storage round-trip (temp DB)")
    ok = True
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        store = Store(path)
        pid = next(iter(problems))
        ok &= check("new card is None", store.get_card(pid) is None)
        st = schedule(None, GOOD)
        store.upsert_card(pid, st["ease"], st["interval"], st["reps"],
                          st["lapses"], st["due"])
        got = store.get_card(pid)
        ok &= check("card persists after upsert", got is not None and got["reps"] == 1,
                    str(got))
        store.log_attempt(pid, "code", True, 42.0, GOOD)
        ok &= check("attempt logged", store.attempt_count() == 1)
        ok &= check("attempts_for returns row", len(store.attempts_for(pid)) == 1)
        store.add_xp(10)
        store.add_xp(15)
        ok &= check("xp accumulates", store.get_xp() == 25, str(store.get_xp()))
        s = store.touch_streak()
        ok &= check("streak starts at 1", s == 1, str(s))
        s2 = store.touch_streak()  # same day, should not double-count
        ok &= check("streak stable same day", s2 == 1, str(s2))
        store.close()
        # Reopen to confirm data survived process-level close
        store2 = Store(path)
        ok &= check("data survives reopen", store2.get_xp() == 25)
        store2.close()
    finally:
        os.unlink(path)
    return ok


def _good_solution_file(problem, tmpdir):
    """Write a file whose function body == the reference solution body."""
    src = inspect.getsource(problem.reference)
    # rename `reference` -> the expected func_name
    src = src.replace("def reference(", f"def {problem.func_name}(", 1)
    path = os.path.join(tmpdir, problem.id.replace("/", "__") + "_good.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return path


def _bad_solution_file(problem, tmpdir):
    """A solution that returns a constant — should fail at least one test."""
    body = (
        f"def {problem.func_name}(*args, **kwargs):\n"
        f"    return None\n"
    )
    path = os.path.join(tmpdir, problem.id.replace("/", "__") + "_bad.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


def test_grader(problems):
    print("\n[6] Subprocess grader (real end-to-end)")
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for pid, p in problems.items():
            good = _good_solution_file(p, tmp)
            res = grade_file(p, good)
            ok &= check(f"{pid}: reference solution PASSES grader",
                        res["passed"] is True,
                        res.get("error") or json.dumps(res["detail"])[:200])
            bad = _bad_solution_file(p, tmp)
            resb = grade_file(p, bad)
            ok &= check(f"{pid}: constant-None solution FAILS grader",
                        resb["passed"] is False,
                        "bad solution unexpectedly passed")
    return ok


def main():
    print("=" * 64)
    print("LeetGrind self-test")
    print("=" * 64)
    problems = load_all()
    print(f"Loaded {len(problems)} problems across "
          f"{len(grouped_by_pattern(problems))} patterns "
          f"({len(SEEDED_SLUGS)} seeded of {len(PATTERNS)} total).")

    results = [
        test_metadata(problems),
        test_references(problems),
        test_scheduler(),
        test_session(problems),
        test_storage(problems),
        test_grader(problems),
    ]

    print("\n" + "=" * 64)
    if all(results) and not _failures:
        print(f"{PASS}: all checks green.")
        return 0
    print(f"{FAIL}: {len(_failures)} check(s) failed:")
    for name, detail in _failures:
        print(f"   - {name}: {detail}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
