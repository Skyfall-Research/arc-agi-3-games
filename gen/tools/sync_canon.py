"""Re-vendor `canon/` from a duckWM checkout (contract P-2). MAINTAINER TOOL.

    .venv/bin/python -m gen.tools.sync_canon [--source <duckWM canon>] [--force]

`canon/` is the tracked, provenance-stamped SNAPSHOT of the signed generator
canon that ships inside this repo, so the pipeline runs on a machine with no
duckWM sibling at all (operator ruling, 2026-09-29). This module is the only
writer of that tree, and nothing in the pipeline imports it: no stage, no
config reader and no orchestrator path calls anything here.

THE FILE SET IS DERIVED, NEVER LISTED. A hand-maintained list would go stale
the first time a reader learned a new canon path, and the failure mode is a
prompt that is quietly thinner on someone else's clone. So the set is read out
of the readers themselves: every canon-relative `.md`/`.csv` string constant in
the four modules that resolve paths under `duckwm_docs`
(`gen/config.py`, `gen/s0_ideas.py`, `gen/s1_spec.py`, `gen/canon_docs.py`),
plus every file inside the canon DIRECTORIES those modules name (`*_DIR`
constants — today only `canon_docs.BESTIARY_DIR`, whose 25 entries are reached
by slug and so are vendored whole). `gen/tests/test_p2_vendoring.py` pins that
derivation against the vendored tree, so a new canon read with no vendored copy
turns red instead of turning into a `FileNotFoundError` on a stranger's laptop.

duckWM IS READ-ONLY. This tool reads the source and writes only under `--dest`.

REFUSAL IS THE POINT. A vendored file whose bytes differ from what the sync
would write is a DIVERGENCE, and the tool refuses the whole sync (exit 1) and
names every one of them. It cannot tell "the canon moved upstream" from
"someone edited our copy", so it declines to guess and makes the human say
`--force`, which overwrites the divergent files, drops orphans and re-stamps
`PROVENANCE.md`. Files that are simply MISSING from the vendored tree are
copied without `--force`: there is nothing there to clobber, which is also how
the tree is created the first time.

THE POST-COPY NEUTRALIZATION (contract OS-2). The snapshot ships in a PUBLIC
repo, and the duckWM canon was written on one maintainer's machine: bestiary
`Source:`/`Frames:` lines carry absolute home-directory paths, and sign-off,
approval and ruling lines carry a personal name. So what the sync writes — and
what "divergence" is measured against — is `neutralize_canon(source bytes)`,
not the raw source: home-directory paths into the duckWM checkout become
`duckWM/...`, the uv cache root becomes `$UV_CACHE_DIR`, and a personal name
becomes the neutral "operator" with its date kept (`SIGNED OFF (operator,
2026-09-18)`, `operator ruling 2026-09-22`). Nothing else is touched, the rules
are deterministic, and the transform is idempotent, so a re-sync from an
unchanged duckWM reproduces the public canon byte-for-byte instead of
resurrecting what was scrubbed. Third-party files (`third-party/`) are never
rewritten — they ship verbatim under their own license — and a sync whose
output would still carry a path or a name the rules do not cover REFUSES
(exit 2) instead of shipping it. Which names count lives in
`gen/tools/public_hygiene.py`, held as digests so the public tree never spells
them.

ONE FILE HAS NO duckWM SOURCE: `third-party/re-arc-3/LICENSE-MIT.md`, the MIT
notice and attribution for the vendored Tufalabs prompts (ruling 1 of the
2026-10-08 opensourcing rulings). It is GENERATED here (`GENERATED_FILES`), so
the stamped set is "the derived reads + their license notice", a re-sync
rewrites it to the same bytes, and a local edit to it is a divergence like any
other.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - `python gen/tools/sync_canon.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gen.tools import public_hygiene

REPO_ROOT = Path(__file__).resolve().parents[2]
GEN_DIR = REPO_ROOT / "gen"
CANON_ROOT = REPO_ROOT / "canon"
DEFAULT_SOURCE = REPO_ROOT.parent / "duckWM" / "local-docs" / "arc-agi-3-generator"
PROVENANCE_NAME = "PROVENANCE.md"

# The modules that resolve a path under `cfg["duckwm_docs"]` — the `_docs(cfg)`
# helpers plus `config.CANON_FILES`. A fifth module reading the canon would be
# added here; the pin test reads this same tuple, so forgetting is a red test.
CANON_READER_MODULES: tuple[str, ...] = (
    "config.py",
    "s0_ideas.py",
    "s1_spec.py",
    "canon_docs.py",
)

# A canon-relative path as the readers write them: `spec-v0.3.md`,
# `mechanics/objectives.csv`, `third-party/re-arc-3/spec_prompt.md`. Anchored
# at both ends so a sentence mentioning a file cannot match.
_CANON_RELPATH_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|csv)$")

# Literals that LOOK like canon paths and are not. Every entry is a deliberate,
# explained exclusion — the sweep is meant to be noisy, so that a real canon
# read can never be dropped silently.
#   spec.md — S1's OWN OUTPUT (the prose half of a written spec, `out/corpus/
#     <batch>/<slug>/spec.md`), named in that module's docstrings and writers.
NON_CANON_LITERALS: frozenset[str] = frozenset({"spec.md"})

# Canon DIRECTORIES the readers index by name (`bestiary/<slug>.md`, the slug
# coming from the evidence skeleton at runtime). Every file inside one is
# vendored: the code can ask for any of them.
_CANON_DIR_SUFFIX = "_DIR"


# --- derivation --------------------------------------------------------------


def _module_constants(path: Path) -> tuple[dict[str, object], list[str]]:
    """Module-level `NAME = <literal>` assignments, plus every string literal.

    The AST is read rather than the module imported: the derivation must work
    on a checkout whose canon is not present, and importing `gen.config` is
    harmless today but would couple a maintainer tool to every stage's imports.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = list(node.targets)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        value = node.value
        for target in targets:
            if isinstance(target, ast.Name) and value is not None:
                try:
                    constants[target.id] = ast.literal_eval(value)
                except (ValueError, SyntaxError, TypeError):
                    continue
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    return constants, literals


def derive_canon_files(gen_dir: Path = GEN_DIR) -> tuple[str, ...]:
    """Every canon-relative FILE path the pipeline's readers can name, sorted.

    Sweeps string literals — not just named constants — because one reader
    (`config.matrix_row_count`) joins its path inline. The cost of the wider
    sweep is that a non-canon `.md`/`.csv` literal in one of these four modules
    has to be declared in `NON_CANON_LITERALS`, which is the trade this file
    wants: a new canon read is caught by default, a false positive is caught by
    a red pin and one commented line.
    """
    found: set[str] = set()
    for name in CANON_READER_MODULES:
        path = gen_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"canon-reading module not found: {path}")
        _constants, literals = _module_constants(path)
        for literal in literals:
            if _CANON_RELPATH_RE.match(literal) and literal not in NON_CANON_LITERALS:
                found.add(literal)
    if not found:
        raise ValueError(
            f"no canon paths derived from {list(CANON_READER_MODULES)} — the readers were "
            f"restructured, and vendoring an empty canon would ship a silently dead pipeline"
        )
    return tuple(sorted(found))


def derive_canon_dirs(gen_dir: Path = GEN_DIR) -> tuple[str, ...]:
    """Canon-relative DIRECTORIES the readers index by name, sorted.

    A `*_DIR` module constant whose value is a relative path with a separator
    in it — today exactly `canon_docs.BESTIARY_DIR`. Its members are reached by
    a slug computed at runtime, so the whole directory is vendored.
    """
    found: set[str] = set()
    for name in CANON_READER_MODULES:
        constants, _literals = _module_constants(gen_dir / name)
        for key, value in constants.items():
            if (
                key.endswith(_CANON_DIR_SUFFIX)
                and isinstance(value, str)
                and "/" in value
                and not value.startswith(("/", "."))
            ):
                found.add(value.rstrip("/"))
    return tuple(sorted(found))


def derive_canon_paths(root: Path, gen_dir: Path = GEN_DIR) -> tuple[str, ...]:
    """The COMPLETE stamped set, canon-relative and sorted.

    `root` is the tree the directory members are enumerated from — the duckWM
    source when copying, the vendored `canon/` when checking it. A named canon
    directory that is missing from `root` is a stop: an empty bestiary would
    otherwise "derive" a set that passes every check and starves the payload.

    The set is the derived reads PLUS `GENERATED_FILES` (the license notice the
    vendored third-party files must travel with). Those are added whatever
    `root` is: they are written by this tool, never copied, so they belong to
    the stamped set on both sides.
    """
    root = Path(root)
    paths = set(derive_canon_files(gen_dir)) | set(GENERATED_FILES)
    for rel in derive_canon_dirs(gen_dir):
        directory = root / rel
        if not directory.is_dir():
            raise FileNotFoundError(
                f"canon directory {rel!r} is not present under {root} — the readers index it "
                f"by name, so its members cannot be enumerated"
            )
        members = sorted(p.name for p in directory.iterdir() if p.is_file())
        if not members:
            raise ValueError(f"canon directory {root / rel} is empty")
        paths.update(f"{rel}/{member}" for member in members)
    return tuple(sorted(paths))


# --- the post-copy neutralization (contract OS-2) ------------------------------

# Files under this prefix are third-party and ship VERBATIM under their own
# license: never rewritten, only checked.
THIRD_PARTY_PREFIX = "third-party/"

_NO_PATH_CHARS = r"[^/\s`'\"<>()]"
# A home-directory path INTO the duckWM checkout, up to and including the
# `duckWM/` segment: `<home>/<who>/<...>/duckWM/games/cd82/...` -> `duckWM/games/...`.
_DUCKWM_HOME_RE = re.compile(
    rf"/(?:User[s]|hom[e])/{_NO_PATH_CHARS}+/(?:{_NO_PATH_CHARS}+/)*?duckWM/"
)
# The uv cache root (where the bestiary's engine-simulation cite points).
_UV_CACHE_RE = re.compile(rf"/(?:User[s]|hom[e])/{_NO_PATH_CHARS}+/\.cache/uv/")
_LETTER_RUN_RE = re.compile(r"[A-Za-z]+")

# A personal name is first replaced by a SENTINEL, so the phrase rules below
# can only ever touch text this pass produced — the canon already says
# "operator" in places, and those must come through untouched.
_OP, _OP_UPPER = "\x00op\x00", "\x00OP\x00"
_PHRASE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "<name>'s ruling" / "<name>'s R1 ruling" -> "operator ruling" (the ruled form)
    (re.compile(rf"{_OP}'s ((?:R-?\d+ )?rulings?)\b"), rf"{_OP} \1"),
    (re.compile(rf"{_OP_UPPER}'S (RULINGS?)\b"), rf"{_OP_UPPER} \1"),
    # "for <name>" -> "for the operator" (not "by <name>-tiebreak": a compound)
    (re.compile(rf"\b(for|to|by|from|and|on|with) {_OP}(?![-\w])"), rf"\1 the {_OP}"),
    # a mid-sentence possessive: "the vocabulary <name>'s workstream validated"
    (re.compile(rf"(?<=[a-z,;] ){_OP}'s\b"), f"the {_OP}'s"),
)
_SENTENCE_END = (".", "!", "?")


def _neutralize_names(text: str) -> str:
    def to_sentinel(match: re.Match[str]) -> str:
        word = match.group(0)
        if not public_hygiene.is_person_name(word):
            return word
        return _OP_UPPER if word.isupper() else _OP

    text = _LETTER_RUN_RE.sub(to_sentinel, text)
    if _OP not in text and _OP_UPPER not in text:
        return text
    for pattern, replacement in _PHRASE_RULES:
        text = pattern.sub(replacement, text)
    out: list[str] = []
    cursor = 0
    for match in re.finditer(re.escape(_OP), text):
        before = text[: match.start()].rstrip().rstrip("*_>#").rstrip()
        word = "Operator" if (not before or before.endswith(_SENTENCE_END)) else "operator"
        out.append(text[cursor : match.start()])
        out.append(word)
        cursor = match.end()
    out.append(text[cursor:])
    return "".join(out).replace(_OP_UPPER, "OPERATOR")


def neutralize_canon(rel: str, data: bytes) -> bytes:
    """What the sync writes for `rel`, given the source's bytes.

    Deterministic and idempotent: machine paths become portable, personal
    names become "operator" (dates and every other byte kept). Third-party
    files and anything that is not UTF-8 text come back unchanged — the
    residual check (`neutralization_residue`) still sees them.
    """
    if rel.startswith(THIRD_PARTY_PREFIX):
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    text = _DUCKWM_HOME_RE.sub("duckWM/", text)
    text = _UV_CACHE_RE.sub("$UV_CACHE_DIR/", text)
    text = public_hygiene.HOME_DIR_RE.sub("~/", text)
    text = _neutralize_names(text)
    return text.encode("utf-8")


def neutralization_residue(rel: str, data: bytes) -> list[str]:
    """`rel:line: what` for every path or name the sync would STILL ship.

    Empty on the real canon. A new kind of path or name upstream makes this
    non-empty, and the sync refuses rather than publishing it.
    """
    text = data.decode("utf-8", errors="replace")
    problems = {
        hit.render() for hit in public_hygiene.scan_text(rel, text) if hit.gate in ("name", "path")
    }
    for match in public_hygiene.HOME_DIR_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        problems.add(f"{rel}:{line}: [path] home-directory path")
    return sorted(problems)


# --- the generated license notice (ruling 1, 2026-10-08) ----------------------

RE_ARC_3_LICENSE = "third-party/re-arc-3/LICENSE-MIT.md"

_MIT_TEXT = """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def render_re_arc_3_license() -> str:
    """`third-party/re-arc-3/LICENSE-MIT.md`: attribution + the MIT text."""
    return f"""# Tufalabs re-arc-3 — license and attribution

This directory vendors two files from Tufalabs' re-arc-3, VERBATIM — never
modified, byte-identical to the copy the sha256 table in `canon/PROVENANCE.md`
stamps:

- `game_generation_prompt.md`
- `spec_prompt.md`

They are reference doctrine the generator's idea (S0) and spec (S1) stages
quote into their prompts.

## Attribution

Tufalabs re-arc-3 v0.1.2, © Tufalabs (team: Harold Bessis, Jeroen Cottaar,
Isaiah Pressman, Andries Smit, Michal Tesnar, Stefano Viel), obtained from
Kaggle dataset `jeroencottaar/taaf-kaggle-source` (dataset license field: MIT),
vendored 2026-09-21.

## Where the grant comes from

Stated plainly: the MIT grant is the Kaggle DATASET-LEVEL license field, set by
the bundle's author, Jeroen Cottaar, a member of the Tufalabs team. The bundle
itself carries no LICENSE file of its own; the text below is the standard MIT
license that field names, reproduced so the notice travels with the files.

## MIT License

Copyright (c) Tufalabs

{_MIT_TEXT}"""


# canon-relative path -> the function that renders it. Written, never copied.
GENERATED_FILES: dict[str, Callable[[], str]] = {
    RE_ARC_3_LICENSE: render_re_arc_3_license,
}


# --- provenance --------------------------------------------------------------


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(source: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(source), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def portable_source(source: Path, repo_root: Path = REPO_ROOT) -> str:
    """`source` spelled relative to the repo root, POSIX separators.

    Contract OS-2: the stamp used to record the maintainer's ABSOLUTE path,
    which ships a home directory in a public file and means nothing on any
    other machine. Relative to the repo root is the spelling the historical
    configs already use for `duckwm_docs` (`../duckWM/local-docs/...`), so the
    stamp now reads the way a config would point at the same checkout.
    """
    rel = os.path.relpath(os.path.abspath(source), os.path.abspath(repo_root))
    return Path(rel).as_posix()


def source_stamp(source: Path) -> dict[str, str]:
    """What the snapshot came from: portable path, duckWM commit, cleanliness."""
    commit = _git(source, "rev-parse", "HEAD") or "unknown"
    status = _git(source, "status", "--porcelain", "--", ".")
    clean = "unknown" if status is None else ("yes" if status == "" else "no")
    return {"source": portable_source(source), "commit": commit, "clean": clean}


def render_provenance(dest: Path, stamp: dict[str, str], paths: tuple[str, ...], today: str) -> str:
    """`canon/PROVENANCE.md` — the snapshot's own receipt, regenerate-able.

    Deliberately plain: `- Key: value` header lines and one pipe table whose
    cells carry no markup, so the self-integrity check is a two-line parse in
    any reader (`gen/tools/sync_canon.parse_provenance` is only the one that
    ships here).
    """
    dest = Path(dest)
    rows = []
    for rel in paths:
        target = dest / rel
        rows.append(f"| {rel} | {target.stat().st_size} | {sha256_of(target)} |")
    body = "\n".join(rows)
    return f"""# canon/ — vendored snapshot of the duckWM generator canon

This tree is a copy of the files the pipeline reads under `duckwm_docs`, at the
same relative paths the readers use, so the generator runs standalone on a
machine with no duckWM checkout (operator ruling, 2026-09-29; contract P-2).
duckWM remains the SOURCE OF TRUTH and remains read-only — this is a snapshot
of it, not a fork of it.

Do not hand-edit these files. Re-stamp the snapshot from a duckWM checkout
with:

    .venv/bin/python -m gen.tools.sync_canon --source <duckWM canon> [--force]

The file set is DERIVED from the readers themselves (see that module); it is
not a list anyone maintains here. To read the canon from a real duckWM
checkout instead of this snapshot, point `duckwm_docs` at it in your config.
The sha256 table below is what lets the snapshot vouch for itself.

## Post-copy neutralization

Every copied file is byte-identical to its duckWM source EXCEPT for one
deterministic scrub the sync tool applies after the copy (contract OS-2):
absolute machine paths become portable ones (a home-directory path into the
duckWM checkout is written `duckWM/...`, the uv cache root `$UV_CACHE_DIR`),
and the personal name in sign-off, approval and ruling attributions becomes
the neutral "operator", every date kept. Nothing else changes — no wording,
no number, no structure. The rules live in `gen/tools/sync_canon.py`
(`neutralize_canon`) and `gen/tools/public_hygiene.py`, so a re-sync from an
unchanged duckWM reproduces these bytes exactly; a config that reads a duckWM
checkout directly sees the un-neutralized originals.

## Third-party: Tufalabs re-arc-3 (MIT)

`third-party/re-arc-3/game_generation_prompt.md` and `spec_prompt.md` are
Tufalabs' re-arc-3 v0.1.2 prompts — copied VERBATIM, never neutralized or
otherwise modified — that the S0 and S1 stages quote as reference doctrine.
They are MIT-licensed: `third-party/re-arc-3/LICENSE-MIT.md` carries the
license text, the attribution, and where the grant comes from. That notice
has no duckWM source; the sync tool writes it, and it is stamped below like
every other file.

## The official games

The bestiary (`design/objects/bestiary/`) and the mechanics tables analyse the
25 official ARC-AGI-3 games published by the ARC Prize Foundation
(arcprize.org). Those games are arcprize's and are NOT vendored here — no game
source, level data or frames. What this canon carries is analysis of them:
derived numbers (counts, per-level values, line citations) and short
quotations used for analysis, with the source of every reading named.

## Snapshot

The source path is relative to the repo root — the spelling the historical
configs use for `duckwm_docs`.

- Source: {stamp["source"]}
- duckWM commit: {stamp["commit"]}
- Source tree clean: {stamp["clean"]}
- Copied: {today}
- Files: {len(paths)}

## Files

| path | bytes | sha256 |
| --- | --- | --- |
{body}
"""


_HEADER_RE = re.compile(r"^- ([^:]+):\s*(.*)$")
_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([0-9a-f]{64})\s*\|$")


def parse_provenance(text: str) -> dict:
    """`PROVENANCE.md` -> {source, commit, clean, copied, files: {rel: (bytes, sha)}}."""
    header: dict[str, str] = {}
    files: dict[str, tuple[int, str]] = {}
    for line in text.splitlines():
        row = _ROW_RE.match(line.strip())
        if row:
            files[row.group(1)] = (int(row.group(2)), row.group(3))
            continue
        head = _HEADER_RE.match(line.strip())
        if head:
            header[head.group(1).strip().lower()] = head.group(2).strip()
    missing = [key for key in ("source", "duckwm commit", "copied") if key not in header]
    if missing:
        raise ValueError(f"PROVENANCE.md is missing header fields {missing}")
    if not files:
        raise ValueError("PROVENANCE.md carries no file table")
    return {
        "source": header["source"],
        "commit": header["duckwm commit"],
        "clean": header.get("source tree clean", "unknown"),
        "copied": header["copied"],
        "files": files,
    }


def verify_provenance(dest: Path = CANON_ROOT) -> list[str]:
    """Self-integrity: every row's sha256 and size match the vendored bytes.

    Returns the complaints, empty when the stamp tells the truth.
    """
    dest = Path(dest)
    stamp_path = dest / PROVENANCE_NAME
    if not stamp_path.is_file():
        return [f"{stamp_path} is missing"]
    record = parse_provenance(stamp_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for rel, (size, digest) in sorted(record["files"].items()):
        target = dest / rel
        if not target.is_file():
            problems.append(f"{rel}: listed in PROVENANCE.md, absent from the tree")
            continue
        actual_size = target.stat().st_size
        if actual_size != size:
            problems.append(f"{rel}: PROVENANCE.md says {size} bytes, file is {actual_size}")
        actual = sha256_of(target)
        if actual != digest:
            problems.append(f"{rel}: PROVENANCE.md says sha256 {digest}, file is {actual}")
    listed = set(record["files"])
    on_disk = {
        str(path.relative_to(dest))
        for path in dest.rglob("*")
        if path.is_file() and path.name != PROVENANCE_NAME
    }
    for rel in sorted(on_disk - listed):
        problems.append(f"{rel}: vendored but absent from PROVENANCE.md")
    return problems


# --- the sync ----------------------------------------------------------------


@dataclass
class SyncPlan:
    """What a sync would do, before it does any of it."""

    source: Path
    dest: Path
    paths: tuple[str, ...] = ()
    new: list[str] = field(default_factory=list)  # absent from dest — safe to copy
    changed: list[str] = field(default_factory=list)  # DIVERGENT — needs --force
    same: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)  # vendored, no longer derived
    # rel -> the bytes the sync writes: the NEUTRALIZED source, or a generated file
    expected: dict[str, bytes] = field(default_factory=dict)

    @property
    def blocked(self) -> list[str]:
        """Everything a plain (unforced) run refuses to touch."""
        return sorted(self.changed + self.orphans)


def plan_sync(source: Path, dest: Path = CANON_ROOT) -> SyncPlan:
    source, dest = Path(source), Path(dest)
    if not source.is_dir():
        raise NotADirectoryError(f"canon source is not a directory: {source}")
    paths = derive_canon_paths(source)
    plan = SyncPlan(source=source, dest=dest, paths=paths)
    residue: list[str] = []
    for rel in paths:
        if rel in GENERATED_FILES:
            expected = GENERATED_FILES[rel]().encode("utf-8")
        else:
            origin = source / rel
            if not origin.is_file():
                raise FileNotFoundError(
                    f"{origin} is named by a reader and missing from the source canon — "
                    f"vendoring it would ship a hole"
                )
            expected = neutralize_canon(rel, origin.read_bytes())
        residue.extend(neutralization_residue(rel, expected))
        plan.expected[rel] = expected
        target = dest / rel
        if not target.is_file():
            plan.new.append(rel)
        elif target.read_bytes() == expected:
            plan.same.append(rel)
        else:
            plan.changed.append(rel)
    if residue:
        raise ValueError(
            "the post-copy neutralization would still ship a machine path or a personal "
            "name — extend gen/tools/sync_canon.neutralize_canon (or public_hygiene) "
            "before syncing:\n  " + "\n  ".join(residue)
        )
    if dest.is_dir():
        derived = set(paths)
        for path in sorted(dest.rglob("*")):
            if not path.is_file() or path.name == PROVENANCE_NAME:
                continue
            rel = str(path.relative_to(dest))
            if rel not in derived:
                plan.orphans.append(rel)
    return plan


def apply_sync(plan: SyncPlan, today: str | None = None) -> None:
    """Write what differs and re-stamp. Assumes the refusal already passed.

    What is written is `plan.expected` — the neutralized source, or the
    generated notice — never the raw source bytes. An identical file is left
    alone rather than rewritten with the same bytes: the snapshot is tracked,
    and a sync that changes nothing should show up as an empty diff, not as
    every file touched.
    """
    plan.dest.mkdir(parents=True, exist_ok=True)
    for rel in plan.new + plan.changed:
        target = plan.dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(plan.expected[rel])
    for rel in plan.orphans:
        (plan.dest / rel).unlink()
    stamp = source_stamp(plan.source)
    text = render_provenance(
        # The LOCAL calendar date (via an aware UTC now), because the stamp is
        # read by a human asking "how old is this snapshot?".
        plan.dest,
        stamp,
        plan.paths,
        today or datetime.now(tz=UTC).astimezone().date().isoformat(),
    )
    (plan.dest / PROVENANCE_NAME).write_text(text, encoding="utf-8")


def _summary(plan: SyncPlan) -> str:
    lines = [
        f"source : {plan.source}",
        f"dest   : {plan.dest}",
        (
            f"derived: {len(plan.paths)} files "
            f"({len(plan.same)} identical, {len(plan.new)} new, "
            f"{len(plan.changed)} divergent, {len(plan.orphans)} orphaned)"
        ),
    ]
    for label, rows in (
        ("new", plan.new),
        ("DIVERGENT", plan.changed),
        ("ORPHAN", plan.orphans),
    ):
        for rel in rows:
            lines.append(f"  {label:>9}  {rel}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m gen.tools.sync_canon",
        description="Re-vendor canon/ from a duckWM checkout (maintainer tool; duckWM is "
        "read-only and is only ever read).",
    )
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE),
        help=f"the duckWM canon root to copy FROM (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--dest",
        default=str(CANON_ROOT),
        help=f"the vendored tree to write (default: {CANON_ROOT})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite vendored files that diverge from the source, drop orphans, re-stamp",
    )
    args = parser.parse_args(argv)

    try:
        plan = plan_sync(Path(args.source), Path(args.dest))
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"sync_canon: {exc}", file=sys.stderr)
        return 2

    print(_summary(plan))
    if plan.blocked and not args.force:
        print(
            f"\nREFUSED: {len(plan.blocked)} vendored file(s) diverge from the source.\n"
            f"Nothing was written. A local canon edit and an upstream canon change look the "
            f"same from here, so the overwrite is yours to authorize: re-run with --force.",
            file=sys.stderr,
        )
        return 1
    if not (plan.new or plan.changed or plan.orphans):
        print("\nup to date; re-stamping PROVENANCE.md")
    apply_sync(plan)
    print(f"\nwrote {len(plan.paths)} files + {PROVENANCE_NAME} under {plan.dest}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
