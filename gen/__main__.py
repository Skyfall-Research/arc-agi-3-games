"""`python -m gen` — the CLI, for a clone that has not been pip-installed yet.

Contract P-4 §1. `arc-games` (the console script in `pyproject.toml`) and
`python -m gen` are the same entry point; this file exists so the README's very
first command works before `pip install -e .` has put a script on the PATH, and
so the CLI is reachable from a checkout that was merely unzipped.
"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
