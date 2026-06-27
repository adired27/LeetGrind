#!/usr/bin/env python3
"""LeetGrind launcher.

Usage:
    python run.py            # start the interactive trainer
    python run.py --selftest # run the non-interactive validation suite

The package lives next to this file, so we just make sure this directory is
importable and hand off to leetgrind.app.main().
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _preflight():
    try:
        import rich  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "LeetGrind needs the 'rich' library.\n"
            "Install it with:  pip install rich\n"
        )
        sys.exit(1)


def main():
    if "--selftest" in sys.argv:
        import selftest
        sys.exit(selftest.main())
    _preflight()
    from leetgrind.app import main as app_main
    app_main()


if __name__ == "__main__":
    main()
