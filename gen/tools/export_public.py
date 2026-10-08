"""Assemble — and verify — the PUBLIC MIRROR of this repo (contract OS-2). MAINTAINER TOOL.

    python -m gen.tools.export_public <empty-or-new target dir>
    python -m gen.tools.export_public --verify <assembled mirror dir>

The public repository is a FRESH MIRROR (opensourcing ruling 2, 2026-10-08):
one clean initial commit made from a working tree this tool writes, never this
repo's history. The tool writes that working tree and stops. `git init`, the
commit and the push are the operator's own hands.

WHAT SHIPS is `SHIPS` below — ruling 5's list, encoded once: the functional
core (`games/ gen/ config/ canon/ tools/ worker-template/`), the rewritten
README, the user docs (RUNBOOK, GUIDE, OUTPUT-FORMAT), LICENSE + NOTICE +
CONTRIBUTING, `pyproject.toml`, `.gitignore`, and the two tracked-empty
`.gitkeep` placeholders (`out/`, `play-logs-games/`). Everything else stays
private — the programme board, contracts and rulings (`docs/v2/`, the
opensource audit among them), `IMPLEMENTATION.md`, `audit/`, anything under a
`.claude` directory, and the contents of `out/` and `play-logs-games/`.

The file set is what git sees in the working tree: tracked files plus
untracked files that are not ignored (`git ls-files --cached --others
--exclude-standard`), filtered through `SHIPS`. So an uncommitted file can
ship — the summary lists every one — and an ignored file never can.

GUARANTEES: the source repo is only ever READ (`git ls-files` writes nothing,
and every copy goes target-ward); a non-empty target is REFUSED, as is a target
inside the source repo.

`--verify <dir>` is THE GATE over an assembled mirror — the contract's six
classes, every hit printed `path:line: [class] detail`, exit 1 on any hit:

1. secret: the opensource audit's key-shape family (`public_hygiene`);
2. name: the personal names, word-prefix matched, so "vanish" is safe;
3. path: absolute home-directory paths, the user cache path, macOS temp;
4. link: the private artifact host, the competition team id;
5. layout: every excluded path absent, LICENSE / NOTICE / CONTRIBUTING.md /
   README.md present, the gitignored smoke ledger absent, `out/` and
   `play-logs-games/` holding nothing but their `.gitkeep`;
6. suite: printed, not run — the command that runs the mirror's own suite on
   a tree with no duckWM sibling. It is the slow class, so it is the human's
   (and the lead's) to run.

stdlib only, so it runs on a bare python before anything is installed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

if __package__ in (None, ""):  # pragma: no cover - `python gen/tools/export_public.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gen.tools import public_hygiene

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- ruling 5, encoded once ----------------------------------------------------


@dataclass(frozen=True)
class Ships:
    """What the public mirror carries, and what it must never carry."""

    dirs: tuple[str, ...]
    files: tuple[str, ...]
    excluded: tuple[str, ...]  # repo-relative paths (a dir excludes everything under it)
    required: tuple[str, ...]
    never: tuple[str, ...] = field(default=())  # files that must be absent even if present


SHIPS = Ships(
    dirs=("games", "gen", "config", "canon", "tools", "worker-template"),
    files=(
        "README.md",
        "LICENSE",
        "NOTICE",
        "CONTRIBUTING.md",
        "pyproject.toml",
        ".gitignore",
        "docs/RUNBOOK.md",
        "docs/GUIDE.md",
        "docs/OUTPUT-FORMAT.md",
        "out/.gitkeep",
        "play-logs-games/.gitkeep",
    ),
    excluded=(
        "docs/v2",
        "docs/v2/OPENSOURCE-AUDIT.md",
        "IMPLEMENTATION.md",
        "audit",
    ),
    required=("LICENSE", "NOTICE", "CONTRIBUTING.md", "README.md"),
    never=("out/smoke/smoke.jsonl",),
)

# Directories whose CONTENTS stay private: only the placeholder ships.
EMPTY_DIRS: dict[str, str] = {"out": "out/.gitkeep", "play-logs-games": "play-logs-games/.gitkeep"}

# Never part of the tree, wherever they sit (also never swept by --verify: a
# mirror the human has already set up may hold a venv, git metadata, caches).
_SKIP_PARTS = frozenset({".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"})
_PRIVATE_PART = ".claude"
_OPENSOURCE_AUDIT_NAME = "OPENSOURCE-AUDIT.md"


def _under(rel: str, prefix: str) -> bool:
    return rel == prefix or rel.startswith(prefix.rstrip("/") + "/")


def ships(rel: str, manifest: Ships = SHIPS) -> bool:
    """Whether one repo-relative POSIX path belongs in the public mirror."""
    parts = PurePosixPath(rel).parts
    if _PRIVATE_PART in parts or _SKIP_PARTS.intersection(parts):
        return False
    if PurePosixPath(rel).name == _OPENSOURCE_AUDIT_NAME:
        return False
    if any(_under(rel, prefix) for prefix in manifest.excluded) or rel in manifest.never:
        return False
    for root, placeholder in EMPTY_DIRS.items():
        if _under(rel, root):
            return rel == placeholder
    return rel in manifest.files or any(_under(rel, root) for root in manifest.dirs)


# --- assembly --------------------------------------------------------------------


def source_files(source: Path) -> list[str]:
    """What git sees in the working tree: tracked + untracked-not-ignored, existing."""
    done = subprocess.run(
        ["git", "-C", str(source), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(
            f"`git ls-files` failed in {source} — the export reads its file set from git: "
            f"{done.stderr.decode(errors='replace').strip()}"
        )
    names = sorted({name for name in done.stdout.decode("utf-8").split("\0") if name})
    return [name for name in names if (source / name).is_file()]


def untracked_files(source: Path) -> set[str]:
    done = subprocess.run(
        ["git", "-C", str(source), "ls-files", "-z", "--others", "--exclude-standard"],
        capture_output=True,
        check=False,
    )
    return {name for name in done.stdout.decode("utf-8").split("\0") if name}


@dataclass
class Export:
    target: Path
    shipped: list[str]
    dropped: list[str]
    untracked: list[str]


def export(target: Path, source: Path = REPO_ROOT, manifest: Ships = SHIPS) -> Export:
    """Write the mirror's working tree into `target`. Never writes under `source`."""
    source = source.resolve()
    target = Path(target).resolve()
    if target == source or target.is_relative_to(source):
        raise ValueError(f"refusing to export into the source repo itself: {target}")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise FileExistsError(
            f"refusing a non-empty target: {target} — the mirror is a fresh tree, "
            f"give an empty or new directory"
        )
    files = source_files(source)
    shipped = [rel for rel in files if ships(rel, manifest)]
    dropped = [rel for rel in files if not ships(rel, manifest)]
    missing = [rel for rel in manifest.required if rel not in shipped]
    if missing:
        raise FileNotFoundError(
            f"the source has no {missing} to ship — write them before exporting "
            f"(contract OS-2 FRONT D)"
        )
    untracked = sorted(set(shipped) & untracked_files(source))
    target.mkdir(parents=True, exist_ok=True)
    for rel in shipped:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, dest)
    return Export(target=target, shipped=shipped, dropped=dropped, untracked=untracked)


# --- the gate --------------------------------------------------------------------


def mirror_files(root: Path) -> list[str]:
    """Every file in an assembled mirror, repo-relative, minus tool/VCS litter."""
    out = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if _SKIP_PARTS.intersection(PurePosixPath(rel).parts):
            continue
        if path.is_file() or path.is_symlink():
            out.append(rel)
    return out


def layout_hits(root: Path, files: list[str], manifest: Ships = SHIPS) -> list[public_hygiene.Hit]:
    """Class 5: what must be absent is absent, what must be present is present."""
    hits: list[public_hygiene.Hit] = []
    present = set(files)
    for rel in files:
        parts = PurePosixPath(rel).parts
        if _PRIVATE_PART in parts:
            hits.append(public_hygiene.Hit(rel, 0, "layout", "a .claude path is private"))
        elif PurePosixPath(rel).name == _OPENSOURCE_AUDIT_NAME:
            hits.append(public_hygiene.Hit(rel, 0, "layout", "the opensource audit is private"))
        elif any(_under(rel, prefix) for prefix in manifest.excluded):
            hits.append(public_hygiene.Hit(rel, 0, "layout", "excluded by ruling 5"))
        elif rel in manifest.never:
            hits.append(public_hygiene.Hit(rel, 0, "layout", "must never ship"))
        else:
            for root_dir, placeholder in EMPTY_DIRS.items():
                if _under(rel, root_dir) and rel != placeholder:
                    hits.append(public_hygiene.Hit(
                        rel, 0, "layout", f"{root_dir}/ ships empty (only {placeholder})"))
    for rel in manifest.required:
        if rel not in present:
            hits.append(public_hygiene.Hit(rel, 0, "layout", "required file is missing"))
    for excluded in manifest.excluded:
        if (root / excluded).exists() and excluded not in present:
            hits.append(public_hygiene.Hit(excluded, 0, "layout", "excluded path exists"))
    return hits


def verify(root: Path, manifest: Ships = SHIPS) -> list[public_hygiene.Hit]:
    """Classes 1-5 over an assembled mirror. Empty means the gate is green."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"no mirror at {root}")
    files = mirror_files(root)
    hits = layout_hits(root, files, manifest)
    for rel in files:
        path = root / rel
        if path.is_symlink():
            hits.append(public_hygiene.Hit(rel, 0, "layout", "symlink in the mirror"))
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        hits.extend(public_hygiene.scan_text(rel, text))
    return hits


def suite_command(root: Path) -> str:
    """Class 6, printed: the mirror's own suite, on a tree with no duckWM sibling."""
    return (
        f"cd {root} && git init -q && git add -A && git commit -qm 'mirror' && "
        f"python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]' && "
        f".venv/bin/python -m pytest gen/tests -q   "
        f"# expect: zero failed; `ls {root.parent}/duckWM` must not exist"
    )


# --- CLI ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m gen.tools.export_public",
        description="Assemble the public mirror's working tree (contract OS-2), or verify one.",
    )
    parser.add_argument("target", nargs="?", help="an empty or new directory to write the mirror into")
    parser.add_argument("--verify", metavar="DIR", help="run the gate over an assembled mirror")
    parser.add_argument("--source", default=str(REPO_ROOT), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if bool(args.target) == bool(args.verify):
        parser.error("give exactly one of: a target directory, or --verify DIR")

    if args.target:
        try:
            result = export(Path(args.target), Path(args.source))
        except (FileExistsError, FileNotFoundError, ValueError, RuntimeError) as exc:
            print(f"export_public: {exc}", file=sys.stderr)
            return 2
        print(f"wrote {len(result.shipped)} files to {result.target}")
        print(f"left private: {len(result.dropped)} files")
        if result.untracked:
            print(f"shipped UNCOMMITTED ({len(result.untracked)}) — commit them before publishing:")
            for rel in result.untracked:
                print(f"  {rel}")
        print(f"\nnext: python -m gen.tools.export_public --verify {result.target}")
        return 0

    root = Path(args.verify).resolve()
    try:
        hits = verify(root)
    except NotADirectoryError as exc:
        print(f"export_public: {exc}", file=sys.stderr)
        return 2
    for hit in hits:
        print(hit.render())
    by_gate: dict[str, int] = {}
    for hit in hits:
        by_gate[hit.gate] = by_gate.get(hit.gate, 0) + 1
    summary = ", ".join(f"{gate} {count}" for gate, count in sorted(by_gate.items())) or "none"
    print(f"\ngate classes 1-5 over {root}: {len(hits)} hit(s) ({summary})")
    print(f"class 6 (run it yourself): {suite_command(root)}")
    return 1 if hits else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
