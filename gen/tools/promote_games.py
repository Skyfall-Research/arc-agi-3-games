"""Back-promote every PACKAGED game in `out/corpus/` onto the shelf (contract P-3).

    .venv/bin/python -m gen.tools.promote_games --backfill --dry-run   # discover only
    .venv/bin/python -m gen.tools.promote_games --backfill             # discover + promote

WHY A BACKFILL EXISTS AT ALL. `games/` is new (contract P-3); the games already
packaged under `out/corpus/` predate it, and every one of them is a real accepted
game the team should be able to `git pull`. Wiring promotion into the
orchestrator only serves games packaged from now on, so this tool is the one-time
(re-runnable) pass that catches up — and it stays useful afterwards as the way to
rebuild the whole shelf from `out/` after a shelf edit or a P-3 change.

DISCOVERY IS FROM DISK, NEVER A LIST. The count of games is whatever the corpus
holds: `<corpus>/*/*/*<.s6>/package/manifest.json`. A hand-kept roster of five
games would be wrong the first time a batch landed a sixth, and the failure mode
is a game silently missing from the shelf. (The contract names the narrower
`*/*/worker.s6/package/manifest.json`; the glob here is that pattern with the
worker dir's NAME left open, because `run_s6`'s out dir is `<worker-dir-name>.s6`
for whatever the worker dir is called — the corpus convention is `worker`, and a
differently named one would otherwise be skipped without a word.)

THE VERDICT IS THE FILTER. A game enters the shelf only if its manifest says
`verdict: packaged`. A seed-reject leaves no manifest at all (`run_s6` unlinks
it), and a pull happens at `played` — one edge BEFORE S6 runs — so a pulled game
has no package either; the filter is what makes both facts unnecessary to know.
Anything discovered with another verdict is listed as skipped WITH its verdict
rather than quietly dropped.

NO SPEND, NO ENGINE, NO WORKER CODE. Promotion is a file copy plus one rewritten
manifest (`s6_package.promote_game`), so this tool drives no driver, plays no
seed and executes no game module. `--dry-run` additionally writes nothing at all.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from ..config import REPO_ROOT, load_config
from ..s6_package import (
    DEFAULT_CONFIG,
    GAMES_ROOT,
    MANIFEST_NAME,
    OUT_SUFFIX,
    PACKAGE_DIRNAME,
    VERDICT_PACKAGED,
    promote_game,
    shelf_entry_hash,
)

CORPUS_ROOT = REPO_ROOT / "out" / "corpus"

# `<corpus>/<batch>/<slug>/<worker>.s6/package/manifest.json` — see the module
# docstring for why the worker dir's name is a wildcard.
MANIFEST_GLOB = f"*/*/*{OUT_SUFFIX}/{PACKAGE_DIRNAME}/{MANIFEST_NAME}"

ACTION_PROMOTED = "promoted"
ACTION_REPLACED = "replaced"
ACTION_SKIPPED = "skipped"
ACTION_WOULD_PROMOTE = "would-promote"
ACTION_WOULD_REPLACE = "would-replace"

_TABLE_COLUMNS = ("BATCH", "SLUG", "HASH8", "VERDICT", "ACTION", "SHELF ENTRY")


def _read_manifest(path: Path) -> Mapping | None:
    """The manifest, or None when it will not parse.

    A manifest that is not readable JSON is not promotable, and the discovery
    pass is read-only — so it is reported as a skip with the reason on the row
    instead of ending the scan. `promote_game` is the loud half: it re-reads and
    refuses anything it cannot vouch for.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def discover_packaged(corpus_root: Path | None = None) -> list[dict]:
    """Every S6 package under the corpus, in path order, with its verdict.

    Rows are discovery FACTS, not decisions: `packaged` says whether the verdict
    lets this row onto the shelf, and the caller (`backfill`) is what acts. The
    worker dir is derived by stripping `s6_package.OUT_SUFFIX` from the out dir's
    name — the same sibling rule `run_s6` writes by, inverted. The slug is the
    MANIFEST's, falling back to the slot dir's name when there is no readable
    manifest: `promote_game` refuses a manifest whose slug is not the worker's, so
    the manifest's is the one this table can be held to.
    """
    root = Path(corpus_root) if corpus_root is not None else CORPUS_ROOT
    rows: list[dict] = []
    for manifest_path in sorted(root.glob(MANIFEST_GLOB)):
        out_dir = manifest_path.parent.parent
        slot_dir = out_dir.parent
        worker_dir = slot_dir / out_dir.name[: -len(OUT_SUFFIX)]
        manifest = _read_manifest(manifest_path)
        verdict = None if manifest is None else manifest.get("verdict")
        slug = (manifest or {}).get("slug")
        rows.append({
            "batch": slot_dir.parent.name,
            "slug": slug if isinstance(slug, str) and slug else slot_dir.name,
            "slot_dir": str(slot_dir),
            "worker_dir": str(worker_dir),
            "manifest": str(manifest_path),
            "verdict": verdict,
            "game_hash": (manifest or {}).get("game_hash"),
            "packaged": verdict == VERDICT_PACKAGED,
            "reason": None if manifest is not None else "manifest is not readable JSON",
        })
    return rows


def backfill(
    corpus_root: Path | None = None,
    games_root: Path | None = None,
    cfg: Mapping | None = None,
    *,
    dry_run: bool = False,
) -> dict:
    """Promote every packaged game the corpus holds. Re-runnable, byte-idempotent.

    `dry_run` is the read-only half the P-3 verification gate asks for: it
    discovers, decides and reports WITHOUT writing, so an operator sees what
    would land before anything does. The two passes agree by construction — the
    same rows, the same filter, the same shelf lookup — so a dry run is a
    prediction, not a separate code path.

    Idempotence is `promote_game`'s (the slug dir is replaced wholesale), so
    running this twice leaves byte-identical trees; the second run's rows just
    say `replaced` with `same_game_hash: true`.

    `cfg` is passed straight to `promote_game`, which type-checks it and reads
    nothing from it (signature parity with `run_s6`); a library call may leave it
    empty, and the CLI hands over the config it loaded.
    """
    rows = discover_packaged(corpus_root)
    config: Mapping = {} if cfg is None else cfg
    for row in rows:
        if not row["packaged"]:
            row["action"] = ACTION_SKIPPED
            row["reason"] = row["reason"] or f"verdict {row['verdict']!r}"
            row["entry"] = None
            continue
        existing = shelf_entry_hash(row["slug"], games_root)
        replacing = existing is not None
        if dry_run:
            row["action"] = ACTION_WOULD_REPLACE if replacing else ACTION_WOULD_PROMOTE
            row["entry"] = f"{row['slug']}/game"
            row["same_game_hash"] = (existing == row["game_hash"]) if replacing else None
            continue
        result = promote_game(
            Path(row["worker_dir"]), config, games_root=games_root
        )
        replaced = result["replaced"]
        row["action"] = ACTION_REPLACED if replaced is not None else ACTION_PROMOTED
        row["entry"] = f"{result['slug']}/game"
        row["game_dir"] = result["game_dir"]
        row["levels"] = result["levels"]
        row["entries"] = result["entries"]
        row["same_game_hash"] = None if replaced is None else replaced["same_game_hash"]
    promoted = [row for row in rows if row.get("action") in
                (ACTION_PROMOTED, ACTION_REPLACED, ACTION_WOULD_PROMOTE, ACTION_WOULD_REPLACE)]
    return {
        "corpus_root": str(Path(corpus_root) if corpus_root is not None else CORPUS_ROOT),
        "games_root": str(Path(games_root) if games_root is not None else GAMES_ROOT),
        "dry_run": bool(dry_run),
        # DISCOVERED is the disk count, which is the number the contract asks for
        # (P-3 §3): how many packages exist, not how many we expected.
        "discovered": len(rows),
        "promoted": len(promoted),
        "skipped": len(rows) - len(promoted),
        "rows": rows,
    }


def format_table(result: Mapping) -> str:
    """The backfill table — one row per DISCOVERED package, plus the counts."""
    rows: Sequence[Mapping] = result["rows"]
    cells = [list(_TABLE_COLUMNS)] + [
        [
            str(row["batch"]),
            str(row["slug"]),
            (row["game_hash"] or "-")[:8],
            str(row["verdict"]),
            str(row.get("action") or "-"),
            str(row.get("entry") or (row.get("reason") or "-")),
        ]
        for row in rows
    ]
    widths = [max(len(cell[index]) for cell in cells) for index in range(len(_TABLE_COLUMNS))]
    lines = [
        "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)).rstrip()
        for row in cells
    ]
    lines.insert(1, "  ".join("-" * width for width in widths))
    mode, landed = (("DRY RUN (nothing written)", "would land on the shelf")
                    if result["dry_run"] else ("PROMOTED", "on the shelf"))
    lines.append("")
    lines.append(
        f"{mode}: discovered {result['discovered']} package(s) under {result['corpus_root']}; "
        f"{result['promoted']} {landed}, {result['skipped']} skipped by verdict"
    )
    lines.append(f"shelf root: {result['games_root']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Back-promote packaged games from out/corpus onto games/ (contract P-3)"
    )
    parser.add_argument(
        "--backfill", action="store_true",
        help="scan the corpus and promote every packaged game (the tool's only mode)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="discover and report only — writes nothing",
    )
    parser.add_argument(
        "--corpus", default=str(CORPUS_ROOT), help=f"corpus root to scan (default: {CORPUS_ROOT})",
    )
    parser.add_argument(
        "--games-root", default=str(GAMES_ROOT), help=f"shelf root to write (default: {GAMES_ROOT})",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)

    # The mode is EXPLICIT on purpose: this tool writes into a tracked directory,
    # so a bare invocation does nothing rather than guessing that a backfill was
    # what someone meant.
    if not args.backfill:
        print(
            "promote_games: nothing was done — pass --backfill (add --dry-run to discover "
            "only). The shelf is tracked in git, so writing it is never the default.",
            file=sys.stderr,
        )
        return 2

    try:
        cfg = load_config(args.config)
        result = backfill(
            Path(args.corpus), Path(args.games_root), cfg, dry_run=args.dry_run,
        )
    except (OSError, ValueError, TypeError, KeyError, AssertionError) as exc:
        print(f"promote_games: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(format_table(result))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
