"""Config loading + canon resolution (B0).

The one rule: `duckwm_docs` resolves against THIS repo's root (config values
are written relative to it), never against the caller's CWD. The canon is a
read-only dependency — nothing in gen/ writes into it.

WHAT IT POINTS AT (contract P-2, operator ruling of 2026-09-29). Two forms,
ONE behaviour — this loader neither knows nor cares which it was handed:

* `./canon` — the VENDORED SNAPSHOT tracked in this repo, and what
  `config/template.yaml` now defaults to. It is a byte-identical copy of
  exactly the files the readers ask for, stamped in `canon/PROVENANCE.md`, so
  a clone with no duckWM sibling runs the whole pipeline.
* `../duckWM/local-docs/arc-agi-3-generator` — a live duckWM checkout, which
  every historical batch config still names and which still loads unchanged.

The resolution rule above is what makes the snapshot work at all: `./canon` is
relative to the repo root, so it resolves the same from any CWD. Re-stamping
the snapshot is `gen/tools/sync_canon.py`, a maintainer CLI that nothing in
the pipeline imports.

`duckwm_games` (B2) follows the same rule and the same read-only contract: it
points at the signed officials corpus. It is OPTIONAL — configs written before
B2 must keep loading, and the template now leaves it commented out because it
is 25 game repos rather than documents and is NOT vendored — but when present
it must resolve to a real directory.

THE PUBLIC-CLONE FALLBACK (contract OS-2 FRONT C.3), OFF unless the environment
sets `ARC_GAMES_CANON_FALLBACK=1`. A public clone has no duckWM sibling, yet the
historical batch configs still name it. Armed, and ONLY for a path that points
into that absent sibling (`../duckWM/...`), `duckwm_docs` falls back to the
vendored `./canon` and `duckwm_games` is dropped as absent (it is optional and
never vendored). Every other path — a typo, a missing directory anywhere else,
a present duckWM — fails or loads exactly as it always has. The suite's
`gen/tests/conftest.py` arms it on a clone; the pipeline never does.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDORED_CANON = REPO_ROOT / "canon"
DUCKWM_SIBLING = REPO_ROOT.parent / "duckWM"
CANON_FALLBACK_ENV = "ARC_GAMES_CANON_FALLBACK"


def _falls_back(path: Path) -> bool:
    """Armed, and `path` is inside a duckWM sibling that is not on this disk."""
    if os.environ.get(CANON_FALLBACK_ENV) != "1" or path.exists():
        return False
    return path.is_relative_to(DUCKWM_SIBLING.resolve()) and not DUCKWM_SIBLING.exists()

# Files every pipeline stage assumes present; checked at load so a bad
# duckwm_docs fails here, loudly, not five stages in.
CANON_FILES = (
    "spec-v0.3.md",
    "mechanics/game-term-matrix.csv",
    "mechanics/objectives.csv",
    "design/objects/playbook.md",
)


def load_config(path: str | Path) -> dict:
    cfg_path = Path(path)
    if not cfg_path.is_absolute():
        cfg_path = REPO_ROOT / cfg_path
    if not cfg_path.is_file():
        raise FileNotFoundError(f"config not found: {cfg_path}")
    with cfg_path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise TypeError(f"config did not parse to a mapping: {cfg_path}")
    if "duckwm_docs" not in cfg:
        raise KeyError(f"config missing 'duckwm_docs': {cfg_path}")

    docs = Path(cfg["duckwm_docs"])
    if not docs.is_absolute():
        docs = (REPO_ROOT / docs).resolve()
    if _falls_back(docs):
        docs = VENDORED_CANON.resolve()
    missing = [rel for rel in CANON_FILES if not (docs / rel).is_file()]
    if missing:
        raise FileNotFoundError(
            f"duckwm_docs={docs} is missing canon files {missing} (configured in {cfg_path})"
        )
    cfg["duckwm_docs"] = str(docs)

    # Optional (B2): the officials corpus. Same resolution rule, same fail-loud
    # check — a typo here must surface at load, not mid-calibration.
    if "duckwm_games" in cfg:
        games = Path(cfg["duckwm_games"])
        if not games.is_absolute():
            games = (REPO_ROOT / games).resolve()
        if _falls_back(games):
            del cfg["duckwm_games"]
            return cfg
        if not games.is_dir():
            raise NotADirectoryError(
                f"duckwm_games={games} is not a directory (configured in {cfg_path})"
            )
        cfg["duckwm_games"] = str(games)

    return cfg


def matrix_row_count(cfg: dict) -> int:
    matrix = Path(cfg["duckwm_docs"]) / "mechanics/game-term-matrix.csv"
    with matrix.open(encoding="utf-8", newline="") as fh:
        return sum(1 for _ in csv.DictReader(fh))
