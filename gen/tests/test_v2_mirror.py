"""OS-2 blind lane — the public mirror, FROM THE FROZEN CONTRACT ALONE.

Run: .venv/bin/python -m pytest gen/tests/test_v2_mirror.py -q

BLIND PROVENANCE. `docs/v2/contracts/OS-2-public-mirror.md` (frozen
2026-10-08) is the only statement of intent this file was written from, with
`docs/v2/OPENSOURCE-AUDIT.md` as the evidence it builds on. Nothing the
implementer lane creates or rewrites was opened: not `gen/tools/export_public.py`,
not the implementer's own pin file, not LICENSE / NOTICE / README.md /
CONTRIBUTING.md, not the re-arc-3 MIT notice. The PRE-EXISTING seams this file
leans on were read at the frozen pre-contract commit (`git show b207d6c:<path>`)
— never the working tree, which the implementer lane was editing while this
file was written:

  gen/tools/sync_canon.py   `main(--source/--dest/--force)`, `derive_canon_paths`,
                            `parse_provenance` — names and CLI only.
  gen/cli.py                `check_canon(cfg, sample=, rng=)`,
                            `read_provenance_table`, `VENDORED_CANON`, `Check.level`.
  gen/backends.py           `LocalClaudeDriver.session` refusing a bypass mode.
  gen/s6_package.py         `promote_game` refusing a non-packaged verdict.
  gen/orchestrator.py, gen/s1_spec.py, gen/s3_static.py
                            the audit's runtime-string lines, located by phrase.
  gen/tests/test_v2_codex.py               d8's id prefix and its smoke-log path.
  gen/tests/test_officials_conformance.py  the latency writer (session finaliser).
  gen/tests/test_b4_sampler.py, test_b003_tiers_s0.py, test_v2_hardening.py
                            the three autouse snapshot/restore fixtures that
                            rewrite the dedupe history (the mtime touch).

THIS FILE SHIPS IN THE MIRROR, so it must pass the very gate it pins. Every
gate token it plants — the operator's, the surname's and the collaborator's
names, the home-directory / uv-cache / private-tmp path marks, the private
artifact host, and every key-shaped value — is ASSEMBLED AT
RUNTIME (names rot13-encoded, the rest split), so this file's own bytes carry
zero hits. The fresh-export verify pin proves it: this file is inside that
export.

THE PINS (contract §"Blind pins"):

  M1  export — ships-manifest exactness (present/absent per ruling 5), core dirs
      complete and byte-identical, nothing outside the manifest; refuses a
      non-empty target loudly; the source tree is byte-untouched.
  M2  verify — a fresh export verifies clean; each gate class trips LOUDLY on
      one seeded violation planted in a hardlinked scratch copy (nonzero exit,
      the planted location named); the name gate spares "vanish"; the tool runs
      under `python -S` (stdlib-only).
  M3  scrub form — the audit's named RUNTIME strings carry the neutral
      "operator" form, keep their ruling dates, and carry no name.
  M4  canon integrity — the PROVENANCE sha256 table matches the files (through
      `gen.cli.check_canon`), covers exactly the vendored set, carries the
      Tufalabs attribution section; canon carries no machine path, no name.
  M5  sync_canon round trip — a re-sync from duckWM-form bytes reproduces the
      public canon byte-for-byte, deterministically, with a portable stamp that
      keeps the attribution; a plain re-sync over the public canon is a no-op.
  M6  d8 — SKIPS (not fails) without the smoke log; still RUNS with one.
  M7  hermeticity — the two known leak sites leave out/ byte- and
      mtime-identical when exercised under test conditions.

CONTRACT AMBIGUITIES, and the reading each pin takes (reported, never resolved
quietly):

  A. THE EXPORT SPELLING. The contract names only `--verify <dir>`. The export's
     own argv is unspecified, so `_export_into` takes the first spelling
     argparse ACCEPTS among: a positional target, `export <dir>`, and
     `--out/--target/--dest/--to/--into/--output <dir>`. A usage error (exit 2
     with "usage:") moves to the next spelling; any other failure is the tool's
     own answer and is reported verbatim.
  B. THE TARGET. The export goes into an EXISTING EMPTY directory — the literal
     boundary of "refuses a non-empty target" — so an empty dir must be taken.
  C. RUNBOOK / GUIDE / OUTPUT-FORMAT keep their source paths under docs/; the
     mirror preserves relative paths.
  D. ROOT EXTRAS. Ruling 5 does not name `.gitignore`: it is TOLERATED, not
     required (FRONT C.1's "the smoke file must never be tracked" argues for
     shipping one — flagged to the lead). `out/` may hold its `.gitkeep` and
     nothing else; `play-logs-games/` holds exactly its `.gitkeep` (ruling 5).
  E. DEBRIS. `__pycache__`, `*.pyc`, `*.egg-info`, `.DS_Store`, `.git`, `.venv`,
     `.claude` and tool caches are outside the SHIPS manifest, so their presence
     in an export is a failure of exactness.
  F. THE SOURCE SWEEP covers the whole repo except `.git`, `.venv`, tool caches,
     `__pycache__`, `*.egg-info`, and the two operator-live runtime dirs `out/`
     and `play-logs-games/` (batches and the play server write there; sweeping
     them would make the pin flaky against surfaces tests must not cite). It is
     a bytes + mtime sweep: a rewrite with identical bytes is still a touch.
  G. GATE 6 (the mirror's own suite) is not driven through `--verify` here: the
     Acceptance line lists it as a separate conjunct. Should `--verify` run a
     suite anyway, recursion is broken by OS2_MIRROR_NESTED — every tool call
     here sets it, and the export/verify pins skip when they see it.
  H. "OPENSOURCE-AUDIT.md" is listed apart from docs/v2, so it is read as a
     BASENAME that must be absent anywhere; its plant is a stray root copy.
  I. KEY SHAPES. "The same pattern family as OPENSOURCE-AUDIT §9" — §2 names
     the family (the OpenAI-style secret-key prefix, a GitHub personal token, a
     Slack token, an AWS access-key id, a JWT). Each is planted once, with a
     high-entropy body and none of the words an allowlist could forgive.
  J. "THE HIT NAMED" = the planted file's relative path appears in the tool's
     output (a key may be redacted; its location cannot be). The vanish control
     plants benign text in the SAME file and must stay green, so a nonzero exit
     on a plant is attributable to the plant and not to the edit. Plants land on
     a PLANT BASE — the fresh export with games/ trimmed to one game (a 150MB
     scan per plant is nearly this file's whole cost) — which must itself verify
     clean; if the trimmed base does not while the full export does, the full
     export is the base. The full export's own verify is pinned separately.
  K. THE NEUTRAL FORM. The contract's two examples differ ("operator ruling,
     <date>" vs "(operator, <date>)"), so the shared invariant is pinned: the
     word "operator" (word-bounded, any case), the ruling's date kept, no name.
     Strings are located by two phrases each from the audit-cited line, with
     docstrings excluded; backends and s6 are also exercised behaviorally.
  L. THE ROUND TRIP. The duckWM bytes of four scrubbed canon files (cd82, tn36,
     affordance-language, spec-v0.3) are REBUILT from their pre-contract lines,
     line for line ("content otherwise byte-identical" makes the scrub
     line-preserving), into a tmp source; everything else is the public canon
     verbatim. A re-sync must reproduce the public canon byte-for-byte. A plain
     (unforced) re-sync over the public canon must neither refuse nor drop the
     non-derived re-arc-3 MIT notice — otherwise "a future re-sync reproduces
     the public canon" cannot hold.
  M. d8 is pinned through pytest's own machinery in a SCRATCH COPY of the repo
     (REPO_ROOT relocates with gen/config.py), where no smoke log exists — this
     box's live smoke log is never moved. The converse (a present log is NOT
     skipped) closes the vacuous "always skip" hole.
  N. HERMETICITY runs in the same scratch copy: one real test from each
     leak-site module runs under a small `-p` plugin; the officials corpus is
     FAKED (discovery, contracts, class loading) so the latency writer has a
     sample to write; a fake ../duckWM sibling (vendored canon + an empty
     officials dir) lets the pilot config load. Non-vacuity is pinned too: each
     module's test must have SET UP, or the rig reports that it could not
     exercise the seam. NEGATIVE CONTROL, run by hand at write time against the
     pre-contract tree (b207d6c) through this same `_run_rig`: d8 FAILED, the
     latency JSON was WRITTEN, the history's mtime MOVED — the rig catches all
     three leaks it pins.
"""

from __future__ import annotations

import ast
import base64
import codecs
import filecmp
import hashlib
import importlib
import importlib.util
import json
import os
import random
import re
import shutil
import string
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from gen import cli
from gen.config import REPO_ROOT
from gen.tools import sync_canon

# =============================================================================
# the gate vocabulary — ASSEMBLED AT RUNTIME (this file ships; see the header)
# =============================================================================


def _rot13(text: str) -> str:
    return codecs.decode(text, "rot13")


OPERATOR_FIRST = _rot13("Navfu")
SURNAME = _rot13("Puunoen")
COLLABORATOR = _rot13("Fgrcunar")
NAME_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in (OPERATOR_FIRST, SURNAME, COLLABORATOR)) + r")\b",
    re.IGNORECASE,
)
OPERATOR_RE = re.compile(r"\boperator\b", re.IGNORECASE)

HOME_MARK = "/" + "Users" + "/"
CACHE_MARK = "~/" + ".cache"
PRIVATE_TMP_MARK = "/private" + "/tmp"
ARTIFACT_MARK = "claude.ai" + "/artifact"
PATH_MARKS = (HOME_MARK, CACHE_MARK, PRIVATE_TMP_MARK)

# =============================================================================
# the contracted surfaces
# =============================================================================

EXPORT_MODULE = "gen.tools.export_public"
NESTED_ENV = "OS2_MIRROR_NESTED"
TOOL_TIMEOUT_S = 900

# Ruling 5's SHIPS list, encoded once here (+ NOTICE from FRONT B, pyproject).
SHIPPED_DIRS = ("games", "gen", "config", "canon", "tools", "worker-template")
SHIPPED_ROOT_FILES = ("README.md", "LICENSE", "NOTICE", "CONTRIBUTING.md", "pyproject.toml")
SHIPPED_DOCS = ("docs/RUNBOOK.md", "docs/GUIDE.md", "docs/OUTPUT-FORMAT.md")
TRACKED_EMPTY = ("play-logs-games/.gitkeep",)
TOLERATED_TOP = {".gitignore", "out"}            # ambiguity D
OUT_ALLOWED = {"out/.gitkeep"}
ALLOWED_TOP = {*SHIPPED_DIRS, "docs", "play-logs-games", *SHIPPED_ROOT_FILES, *TOLERATED_TOP}
EXCLUDED_TOP_DIRS = ("audit",)
EXCLUDED_PREFIXES = ("docs/v2/",)
EXCLUDED_BASENAMES = {"IMPLEMENTATION.md", "OPENSOURCE-AUDIT.md"}   # ambiguity H
SMOKE_LOG_REL = "out/smoke/smoke.jsonl"

# Debris: never part of a SHIPS manifest (ambiguity E).
DEBRIS_PARTS = {".git", ".claude", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
DEBRIS_SUFFIXES = (".pyc", ".egg-info")
DEBRIS_NAMES = {".DS_Store"}

# The source sweep's exclusions (ambiguity F).
SWEEP_SKIP_ANYWHERE = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__"}
SWEEP_SKIP_TOP = {"out", "play-logs-games"}

CANON = REPO_ROOT / "canon"
PROVENANCE = CANON / "PROVENANCE.md"
REARC_LICENSE_REL = "third-party/re-arc-3/LICENSE-MIT.md"

# =============================================================================
# small helpers
# =============================================================================


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _files(root: Path) -> set[str]:
    """Every non-directory entry under `root`, as posix paths relative to it."""
    out: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for name in filenames:
            out.add((base / name).relative_to(root).as_posix())
        for name in dirnames:   # a symlinked dir is an entry, not a tree to walk
            if (base / name).is_symlink():
                out.add((base / name).relative_to(root).as_posix())
    return out


def _is_debris(rel: str) -> bool:
    parts = rel.split("/")
    return (
        any(part in DEBRIS_PARTS for part in parts)
        or any(part.endswith(DEBRIS_SUFFIXES) for part in parts)
        or parts[-1] in DEBRIS_NAMES
    )


def _gate_hits(text: str) -> list[str]:
    """Name and machine-path hits — the labels, never the matched secrets."""
    hits = [f"name {m.group(0)!r}" for m in NAME_RE.finditer(text)]
    hits += [f"path mark {mark!r}" for mark in PATH_MARKS if mark in text]
    return hits


def _child_env(**extra: str) -> dict[str, str]:
    """No credentials, no inherited pytest options, no bytecode written into a tree."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.endswith(("_API_KEY", "_TOKEN"))
        and key not in {"PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH"}
    }
    env[NESTED_ENV] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def _tail(proc: subprocess.CompletedProcess, limit: int = 3000) -> str:
    text = f"--- exit {proc.returncode}\n--- stdout\n{proc.stdout}\n--- stderr\n{proc.stderr}"
    return text if len(text) <= limit else "…" + text[-limit:]


def _output(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout or "") + "\n" + (proc.stderr or "")


def _masked(text: str, *paths: Path) -> str:
    """Blank out tmp paths before a name check: pytest's basetemp embeds the OS
    username, which is not a shipped string. Every component-aligned SUFFIX is
    masked (longest first), because a relative spelling of a tmp path keeps only
    the components past its common prefix with the repo — and which components
    those are depends on where the checkout lives."""
    for path in paths:
        for spelling in {str(path), str(path.resolve())}:
            parts = Path(spelling).parts[1:]
            for start in range(len(parts)):
                text = text.replace("/".join(parts[start:]), "<TMP>")
    return text


def _first_difference(a: bytes, b: bytes) -> str:
    left, right = a.decode("utf-8", "replace").split("\n"), b.decode("utf-8", "replace").split("\n")
    for number, (x, y) in enumerate(zip(left, right), 1):
        if x != y:
            return f"line {number}: got {x[:160]!r} / expected {y[:160]!r}"
    return f"line counts differ: {len(left)} vs {len(right)}"


# =============================================================================
# M1 / M2 rig — the export tool, driven through its CLI
# =============================================================================


def _skip_if_nested() -> None:
    if os.environ.get(NESTED_ENV):
        pytest.skip(f"{NESTED_ENV} is set: this run was launched by an export/verify call "
                    "(ambiguity G — no recursive mirror export)")


def _require_export_tool() -> None:
    if importlib.util.find_spec(EXPORT_MODULE) is None:
        pytest.fail(f"{EXPORT_MODULE} is not importable — contract OS-2 FRONT E creates "
                    "gen/tools/export_public.py (the mirror-assembly tool + its --verify gate)")


def _run_tool(args: list[str], *, python_flags: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *python_flags, "-m", EXPORT_MODULE, *args],
        cwd=REPO_ROOT,
        env=_child_env(),
        capture_output=True,
        text=True,
        timeout=TOOL_TIMEOUT_S,
        check=False,
    )


def _is_usage_error(proc: subprocess.CompletedProcess) -> bool:
    return proc.returncode == 2 and "usage:" in proc.stderr and "error:" in proc.stderr


# Ambiguity A: the export spelling is the first one argparse accepts.
EXPORT_SPELLINGS: tuple[tuple[str, ...], ...] = (
    (), ("export",), ("--out",), ("--target",), ("--dest",), ("--to",), ("--into",), ("--output",),
)


def _export_into(target: Path, spellings=EXPORT_SPELLINGS):
    """Run the export; return (proc, spelling). Fails loudly if no spelling parses."""
    rejected = []
    for spelling in spellings:
        proc = _run_tool([*spelling, str(target)])
        if _is_usage_error(proc):
            rejected.append((spelling, proc.stderr.strip().splitlines()[-1:]))
            continue
        return proc, spelling
    pytest.fail(f"{EXPORT_MODULE}: no export spelling was accepted by its argument parser "
                f"(ambiguity A); tried {rejected}")


def _verify(mirror: Path, *, python_flags: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    return _run_tool(["--verify", str(mirror)], python_flags=python_flags)


def _sweep_source(root: Path = REPO_ROOT) -> dict[str, tuple]:
    """relpath -> (size, mtime_ns, sha256) over the source tree (ambiguity F)."""
    rows: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        top = base == root
        dirnames[:] = sorted(
            name for name in dirnames
            if name not in SWEEP_SKIP_ANYWHERE
            and not name.endswith(".egg-info")
            and not (top and name in SWEEP_SKIP_TOP)
        )
        for name in filenames:
            if name.endswith(".pyc") or name in DEBRIS_NAMES:
                continue
            path = base / name
            rel = path.relative_to(root).as_posix()
            stat = path.lstat()
            if path.is_symlink():
                rows[rel] = ("link", os.readlink(path))
            else:
                rows[rel] = (stat.st_size, stat.st_mtime_ns, _sha256(path))
    return rows


def _diff_rows(before: dict, after: dict, limit: int = 25) -> list[str]:
    lines = [f"removed {rel}" for rel in sorted(set(before) - set(after))]
    lines += [f"added {rel}" for rel in sorted(set(after) - set(before))]
    lines += [
        f"changed {rel}: {before[rel]} -> {after[rel]}"
        for rel in sorted(set(before) & set(after))
        if before[rel] != after[rel]
    ]
    return lines[:limit] + ([f"… {len(lines) - limit} more"] if len(lines) > limit else [])


@dataclass
class Export:
    root: Path
    proc: subprocess.CompletedProcess
    spelling: tuple[str, ...]
    source_before: dict
    source_after: dict


@pytest.fixture(scope="module")
def exported(tmp_path_factory) -> Export:
    """ONE fresh export of this repo, into an existing EMPTY dir (ambiguity B)."""
    _skip_if_nested()
    _require_export_tool()
    target = tmp_path_factory.mktemp("os2-export") / "mirror"
    target.mkdir()
    before = _sweep_source()
    proc, spelling = _export_into(target)
    after = _sweep_source()
    if proc.returncode != 0:
        pytest.fail(f"the export into an empty target failed (spelling {spelling}):\n{_tail(proc)}")
    return Export(target, proc, spelling, before, after)


@pytest.fixture(scope="module")
def clean_verify(exported: Export) -> subprocess.CompletedProcess:
    return _verify(exported.root)


def _clone_mirror(src: Path, dst: Path) -> Path:
    """A hardlinked copy: cheap, and a plant breaks only its own link."""

    def link(a, b):
        try:
            os.link(a, b)
        except OSError:
            shutil.copy2(a, b)

    shutil.copytree(src, dst, symlinks=True, copy_function=link)
    return dst


def _plant_text(mirror: Path, rel: str, text: str) -> None:
    """Append `text` to `rel` without touching the base mirror's shared inode."""
    path = mirror / rel
    data = path.read_bytes() if path.is_file() else b""
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data + text.encode("utf-8"))


@dataclass
class PlantBase:
    root: Path
    verify: subprocess.CompletedProcess
    note: str


@pytest.fixture(scope="module")
def plant_base(exported: Export, clean_verify, tmp_path_factory) -> PlantBase:
    """What every seeded violation is planted on: the fresh export, hardlinked,
    with games/ trimmed to its smallest game. A full 150MB scan per plant is
    nearly the whole cost of this file, and the FULL export's clean verify is
    pinned on its own (`test_m2_verify_passes_a_fresh_export`). Attribution only
    needs a base that verifies clean, so the base is verified here; should the
    trimmed base not verify clean while the full export does, the full export
    is used instead and nothing about the pins changes."""
    slim = _clone_mirror(exported.root, tmp_path_factory.mktemp("os2-plant-base") / "m")
    games = sorted(p for p in (slim / "games").iterdir() if p.is_dir())
    if len(games) > 1:
        def weight(game: Path) -> int:
            return sum(f.stat().st_size for f in game.rglob("*") if f.is_file())

        keep = min(games, key=weight)
        for game in games:
            if game != keep:
                shutil.rmtree(game)
    proc = _verify(slim)
    if proc.returncode == 0 or clean_verify.returncode != 0:
        return PlantBase(slim, proc, "the fresh export with games/ trimmed to one game")
    return PlantBase(exported.root, clean_verify, "the full fresh export")


def _require_clean_base(base: PlantBase) -> None:
    if base.verify.returncode != 0:
        pytest.fail(f"the plant base ({base.note}) does not verify clean, so no seeded "
                    f"violation can be attributed to its plant:\n{_tail(base.verify)}")


def _assert_trips(proc: subprocess.CompletedProcess, named: tuple[str, ...], what: str) -> None:
    out = _output(proc)
    assert proc.returncode != 0, f"--verify stayed GREEN over a mirror carrying {what}:\n{_tail(proc)}"
    assert "Traceback (most recent call last)" not in out, (
        f"--verify CRASHED over {what} — a crash is not a gate trip:\n{_tail(proc)}"
    )
    assert any(token in out for token in named), (
        f"--verify tripped on {what} but never named it (expected one of {named}):\n{_tail(proc)}"
    )


# =============================================================================
# M1 — the export
# =============================================================================


def test_m1_export_ships_every_manifest_entry(exported: Export) -> None:
    root = exported.root
    missing = [f"{d}/" for d in SHIPPED_DIRS if not (root / d).is_dir() or not any((root / d).iterdir())]
    missing += [f for f in (*SHIPPED_ROOT_FILES, *SHIPPED_DOCS, *TRACKED_EMPTY)
                if not (root / f).is_file()]
    assert not missing, f"ruling 5's SHIPS list is incomplete in the export: {missing}"


def test_m1_export_copies_are_complete_and_byte_identical(exported: Export) -> None:
    """Core dirs ship WHOLE (debris aside); every shipped file is the source's bytes."""
    root, problems = exported.root, []
    for d in SHIPPED_DIRS:
        source = {rel for rel in _files(REPO_ROOT / d) if not _is_debris(rel)}
        shipped = {rel for rel in _files(root / d) if not _is_debris(rel)}
        problems += [f"missing {d}/{rel}" for rel in sorted(source - shipped)]
        problems += [f"not in the source: {d}/{rel}" for rel in sorted(shipped - source)]
        problems += [
            f"bytes differ: {d}/{rel}"
            for rel in sorted(source & shipped)
            if not filecmp.cmp(REPO_ROOT / d / rel, root / d / rel, shallow=False)
        ]
    for rel in (*SHIPPED_ROOT_FILES, *SHIPPED_DOCS, *TRACKED_EMPTY):
        src, out = REPO_ROOT / rel, root / rel
        if not src.is_file():
            problems.append(f"{rel} ships but has no source file — the mirror is a COPY of this repo")
        elif out.is_file() and not filecmp.cmp(src, out, shallow=False):
            problems.append(f"bytes differ: {rel}")
    assert not problems, "the export is not a faithful copy of the SHIPS manifest:\n  " + "\n  ".join(
        problems[:40])


def test_m1_export_carries_nothing_outside_the_manifest(exported: Export) -> None:
    root = exported.root
    files = _files(root)
    top = {p.name for p in root.iterdir()}
    problems = [f"unlisted top-level entry {name!r}" for name in sorted(top - ALLOWED_TOP)]
    problems += [f"excluded dir shipped: {name}/" for name in EXCLUDED_TOP_DIRS if name in top]
    problems += [f"excluded path shipped: {rel}" for rel in sorted(files)
                 if rel.startswith(EXCLUDED_PREFIXES) or rel.split("/")[-1] in EXCLUDED_BASENAMES]
    docs = {rel for rel in files if rel.startswith("docs/")}
    problems += [f"docs/ ships more than RUNBOOK/GUIDE/OUTPUT-FORMAT: {rel}"
                 for rel in sorted(docs - set(SHIPPED_DOCS))]
    problems += [f"out/ ships content beyond its .gitkeep: {rel}" for rel in sorted(files)
                 if rel.startswith("out/") and rel not in OUT_ALLOWED]
    problems += [f"play-logs-games/ ships content beyond its .gitkeep: {rel}" for rel in sorted(files)
                 if rel.startswith("play-logs-games/") and rel not in TRACKED_EMPTY]
    problems += [f"build/VCS debris shipped: {rel}" for rel in sorted(files) if _is_debris(rel)]
    problems += [f"debris dir shipped: {p.relative_to(root).as_posix()}/"
                 for p in root.rglob("*") if p.is_dir() and _is_debris(p.relative_to(root).as_posix())]
    assert SMOKE_LOG_REL not in files, f"{SMOKE_LOG_REL} shipped — it must never leave this box"
    assert not problems, "the export carries content outside ruling 5:\n  " + "\n  ".join(
        sorted(set(problems))[:40])


def test_m1_export_leaves_the_source_tree_untouched(exported: Export) -> None:
    changes = _diff_rows(exported.source_before, exported.source_after)
    assert not changes, (
        "the export touched the SOURCE repo (bytes or mtime; out/ and play-logs-games/ "
        "aside — ambiguity F):\n  " + "\n  ".join(changes)
    )


def test_m1_export_refuses_a_non_empty_target(exported: Export, tmp_path: Path) -> None:
    target = tmp_path / "occupied"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_bytes(b"pre-existing content the export must not touch\n")
    proc, _ = _export_into(target, spellings=(exported.spelling,))
    assert proc.returncode != 0, f"the export ACCEPTED a non-empty target:\n{_tail(proc)}"
    assert _output(proc).strip(), "the refusal was SILENT — the contract says refuse loudly"
    assert "Traceback (most recent call last)" not in _output(proc), (
        f"the refusal is a crash, not a refusal:\n{_tail(proc)}"
    )
    assert _files(target) == {"keep.txt"}, (
        f"the refused export still wrote into the target: {sorted(_files(target))[:10]}"
    )
    assert sentinel.read_bytes() == b"pre-existing content the export must not touch\n"


# =============================================================================
# M2 — the verify gate
# =============================================================================


def test_m2_verify_passes_a_fresh_export(clean_verify: subprocess.CompletedProcess) -> None:
    """THE ACCEPTANCE: `--verify` fully green over a freshly assembled mirror."""
    assert clean_verify.returncode == 0, (
        f"`{EXPORT_MODULE} --verify` is not green over a fresh export:\n{_tail(clean_verify)}"
    )


def test_m2_export_tool_is_stdlib_only(plant_base: PlantBase) -> None:
    """FRONT E says stdlib-only: with `-S` no site-packages exist, and the tool still works."""
    help_proc = _run_tool(["--help"], python_flags=("-S",))
    assert help_proc.returncode == 0, f"`python -S -m {EXPORT_MODULE} --help` failed:\n{_tail(help_proc)}"
    proc = _verify(plant_base.root, python_flags=("-S",))
    out = _output(proc)
    assert "ModuleNotFoundError" not in out and "ImportError" not in out, (
        f"the tool needs a non-stdlib package:\n{_tail(proc)}"
    )
    assert proc.returncode == plant_base.verify.returncode, (
        f"--verify answers differently without site-packages:\n{_tail(proc)}"
    )


GUIDE_REL = "docs/GUIDE.md"


def _key_vectors() -> dict[str, str]:
    """One high-entropy value per key shape of the audit's family (ambiguity I)."""
    rng = random.Random(20261008)
    alnum = string.ascii_letters + string.digits

    def draw(n: int, alphabet: str = alnum) -> str:
        return "".join(rng.choice(alphabet) for _ in range(n))

    def b64(obj: dict) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return {
        "sk-shape": "sk" + "-proj-" + draw(48),
        "github-pat": "gh" + "p_" + draw(36),
        "slack-token": "xo" + "xb-" + draw(12, string.digits) + "-" + draw(13, string.digits)
        + "-" + draw(24),
        "aws-key-id": "AK" + "IA" + draw(16, string.ascii_uppercase + string.digits),
        "jwt": ".".join((b64({"alg": "HS256", "typ": "JWT"}),
                         b64({"sub": draw(12), "iat": 1759900000}),
                         draw(43, alnum + "-_"))),
    }


KEY_VECTORS = _key_vectors()


@pytest.mark.parametrize("shape", sorted(KEY_VECTORS))
def test_m2_verify_trips_on_a_planted_key(shape: str, plant_base: PlantBase, tmp_path: Path) -> None:
    _require_clean_base(plant_base)
    value = KEY_VECTORS[shape]
    forgivable = [w for w in ("fake", "test", "example", "dummy", "sample") if w in value.lower()]
    assert not forgivable, f"rig: the {shape} vector reads as a placeholder ({forgivable})"
    mirror = _clone_mirror(plant_base.root, tmp_path / "m")
    _plant_text(mirror, GUIDE_REL, f"\n{value}\n")
    _assert_trips(_verify(mirror), (GUIDE_REL,), f"a {shape} key-shaped value in {GUIDE_REL}")


NAME_PLANTS = {
    "first-name": lambda: f"\nReviewed by {OPERATOR_FIRST} on 2026-10-08.\n",
    "surname": lambda: f"\nOwner: {SURNAME.upper()}\n",
    "collaborator": lambda: f"\nThanks to {COLLABORATOR.lower()} for the TSV notes.\n",
}


@pytest.mark.parametrize("kind", sorted(NAME_PLANTS))
def test_m2_verify_trips_on_a_planted_name(kind: str, plant_base: PlantBase, tmp_path: Path) -> None:
    _require_clean_base(plant_base)
    mirror = _clone_mirror(plant_base.root, tmp_path / "m")
    _plant_text(mirror, GUIDE_REL, NAME_PLANTS[kind]())
    _assert_trips(_verify(mirror), (GUIDE_REL,), f"a planted {kind} in {GUIDE_REL}")


@pytest.mark.parametrize("rel, line", [
    ("config/template.yaml", "\n# reviewed: {name}\n"),
    ("gen/__init__.py", "\n# {name}\n"),
], ids=["yaml-comment", "python-comment"])
def test_m2_verify_scans_every_shipped_file_kind(rel: str, line: str, plant_base: PlantBase, tmp_path: Path) -> None:
    _require_clean_base(plant_base)
    mirror = _clone_mirror(plant_base.root, tmp_path / "m")
    _plant_text(mirror, rel, line.format(name=OPERATOR_FIRST))
    _assert_trips(_verify(mirror), (rel,), f"the operator's first name in {rel}")


def test_m2_verify_name_gate_spares_vanish(plant_base: PlantBase, tmp_path: Path) -> None:
    """Word-boundary sanity, and the control that makes every plant above attributable."""
    _require_clean_base(plant_base)
    mirror = _clone_mirror(plant_base.root, tmp_path / "m")
    _plant_text(mirror, GUIDE_REL, "\nThe marker vanishes; vanish blocks; it vanished. VANISHING.\n")
    proc = _verify(mirror)
    assert proc.returncode == 0, (
        f"the name gate tripped on 'vanish' (it must be word-bounded):\n{_tail(proc)}"
    )


PATH_PLANTS = {
    "home-dir": lambda: f"\nSee {HOME_MARK}someone/work/notes.md for the run.\n",
    "uv-cache": lambda: f"\nEngine copy: {CACHE_MARK}/uv/archive-v0/abc/arcengine\n",
    "private-tmp": lambda: f"\nScratch lives in {PRIVATE_TMP_MARK}/os2/run-1\n",
    "artifact-url": lambda: f"\nBoard: https://{ARTIFACT_MARK}/0123abcd\n",
}


@pytest.mark.parametrize("kind", sorted(PATH_PLANTS))
def test_m2_verify_trips_on_a_machine_path_or_private_id(kind: str, plant_base: PlantBase, tmp_path: Path) -> None:
    _require_clean_base(plant_base)
    mirror = _clone_mirror(plant_base.root, tmp_path / "m")
    _plant_text(mirror, GUIDE_REL, PATH_PLANTS[kind]())
    _assert_trips(_verify(mirror), (GUIDE_REL,), f"a planted {kind} in {GUIDE_REL}")


EXCLUDED_PLANTS = {
    "docs-v2": ("docs/v2/TRACKER.md", ("docs/v2",)),
    "implementation-md": ("IMPLEMENTATION.md", ("IMPLEMENTATION.md",)),
    "audit-dir": ("audit/comparative/findings.md", ("audit",)),
    "opensource-audit-md": ("OPENSOURCE-AUDIT.md", ("OPENSOURCE-AUDIT",)),
    "smoke-log": (SMOKE_LOG_REL, ("smoke.jsonl", "out/smoke")),
}


@pytest.mark.parametrize("kind", sorted(EXCLUDED_PLANTS))
def test_m2_verify_trips_on_an_excluded_path(kind: str, plant_base: PlantBase, tmp_path: Path) -> None:
    _require_clean_base(plant_base)
    rel, named = EXCLUDED_PLANTS[kind]
    mirror = _clone_mirror(plant_base.root, tmp_path / "m")
    _plant_text(mirror, rel, "planted by the OS-2 blind lane\n")
    _assert_trips(_verify(mirror), named, f"the excluded path {rel}")


@pytest.mark.parametrize("rel", ("LICENSE", "NOTICE", "CONTRIBUTING.md", "README.md"))
def test_m2_verify_trips_on_a_missing_public_file(rel: str, plant_base: PlantBase, tmp_path: Path) -> None:
    _require_clean_base(plant_base)
    mirror = _clone_mirror(plant_base.root, tmp_path / "m")
    (mirror / rel).unlink()
    _assert_trips(_verify(mirror), (rel.split(".")[0],), f"no {rel}")


# =============================================================================
# M3 — the scrub form of the named runtime strings
# =============================================================================

#: (module, two phrases that together locate the audit-cited string, its date)
RUNTIME_SURFACES = (
    ("gen.backends", ("is a permission bypass", "no permission bypass"), "2026-09-21"),
    ("gen.orchestrator", ("unless review.auto_accept is armed",
                          "the pipeline must run without human feedback"), "2026-09-29"),
    ("gen.orchestrator", ("AUTO-ACCEPTED", "oversight is post-package"), "2026-09-29"),
    ("gen.orchestrator", ("nothing was deleted", "We should never kill"), "2026-09-29"),
    ("gen.s1_spec", ("tiers.goal_legible_cap", "legibility ruling"), "2026-09-29"),
    ("gen.s3_static", ("MACHINE CONSUMERS", "tag the cells a click acts on"), "2026-09-28"),
    ("gen.s6_package", ("only promoted", "games enter games/"), "2026-09-29"),
)
RUNTIME_IDS = ("backends-bypass-refusal", "orchestrator-review-note", "orchestrator-auto-accepted",
               "orchestrator-parked", "s1-goal-legible-lint", "s3-sys-click-lint",
               "s6-promotion-refusal")
NAMED_MODULES = ("gen.backends", "gen.s3_static", "gen.orchestrator", "gen.s1_spec",
                 "gen.s6_package", "gen.tools.sync_canon")


def _runtime_strings(module) -> list[str]:
    """Every string a module can emit at runtime: literals and joined f-strings
    (placeholders as `{}`), docstrings and f-string fragments excluded."""
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                skip.add(id(body[0].value))
        if isinstance(node, ast.JoinedStr):
            skip.update(id(value) for value in node.values)
    found = []
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            found.append("".join(v.value if isinstance(v, ast.Constant) else "{}"
                                 for v in node.values))
    return found


def _assert_neutral(text: str, date: str, where: str) -> None:
    assert not NAME_RE.search(text), f"{where} still carries a NAME: {text[:300]!r}"
    assert OPERATOR_RE.search(text), (
        f"{where} lost its ruling attribution — the neutral form is 'operator' "
        f"(ruling 3): {text[:300]!r}"
    )
    assert date in text, f"{where} dropped its ruling date {date} (ruling 3 keeps dates): {text[:300]!r}"


@pytest.mark.parametrize("module_name, anchors, date", RUNTIME_SURFACES, ids=RUNTIME_IDS)
def test_m3_runtime_string_carries_the_neutral_form(module_name: str, anchors: tuple[str, str],
                                                    date: str) -> None:
    module = importlib.import_module(module_name)
    found = [s for s in _runtime_strings(module) if all(a in s for a in anchors)]
    assert found, (
        f"{module_name}: no runtime string carries both {anchors} any more — the audit-cited "
        "surface moved or was reworded beyond its name (the scrub may change the NAME only)"
    )
    for text in found:
        _assert_neutral(text, date, f"{module_name} runtime string")


def test_m3_backends_bypass_refusal_reads_neutral(tmp_path: Path, monkeypatch) -> None:
    from gen import backends

    def forbidden(*args, **kwargs):   # pragma: no cover — the refusal precedes any spawn
        raise AssertionError(f"a driver process was started: {args!r}")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    mode = min(backends.BYPASS_PERMISSION_MODES)
    with pytest.raises(backends.DriverError) as excinfo:
        backends.LocalClaudeDriver().session("probe", cwd=tmp_path, permission_mode=mode)
    message = _masked(str(excinfo.value), tmp_path)   # the OS username lives in tmp paths
    assert "bypass" in message, f"a different refusal fired: {message!r}"
    _assert_neutral(message, "2026-09-21", "the bypass refusal")


def test_m3_s6_promotion_refusal_reads_neutral(tmp_path: Path) -> None:
    from gen import s6_package as s6

    worker = tmp_path / "worker"
    worker.mkdir()
    package = tmp_path / ("worker" + s6.OUT_SUFFIX) / s6.PACKAGE_DIRNAME
    package.mkdir(parents=True)
    (package / s6.MANIFEST_NAME).write_text(json.dumps({"verdict": "pulled", "slug": "worker"}),
                                            encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        s6.promote_game(worker, {}, games_root=tmp_path / "games")
    message = _masked(str(excinfo.value), tmp_path)   # the OS username lives in tmp paths
    assert "only promoted" in message, f"a different refusal fired: {message!r}"
    _assert_neutral(message, "2026-09-29", "the promotion refusal")
    assert not (tmp_path / "games").exists(), "a refused promotion wrote a shelf entry"


@pytest.mark.parametrize("module_name", NAMED_MODULES)
def test_m3_named_modules_carry_no_name_anywhere(module_name: str) -> None:
    """FRONT A scrubs these modules whole — comments and docstrings too."""
    path = Path(importlib.import_module(module_name).__file__)
    hits = [f"{path.name}:{number}" for number, line in
            enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if NAME_RE.search(line)]
    assert not hits, f"{module_name} still names a person on {len(hits)} line(s): {hits[:12]}"


# =============================================================================
# M4 — canon integrity
# =============================================================================


def _canon_files() -> set[str]:
    """Every vendored file, PROVENANCE.md and dotfiles aside (test_v2_canon's rule)."""
    return {rel for rel in _files(CANON)
            if rel != "PROVENANCE.md" and not any(p.startswith(".") for p in rel.split("/"))}


def test_m4_canon_sha_table_matches_every_listed_file() -> None:
    """Reuse the repo's own seam: `check_canon`, with a sample wide enough to be total."""
    check = cli.check_canon({"duckwm_docs": str(cli.VENDORED_CANON)}, sample=10**6,
                            rng=random.Random(0))
    assert check.level == "ok", f"canon/PROVENANCE.md does not vouch for the canon: {check.line()}"


def test_m4_canon_sha_table_covers_exactly_the_vendored_files() -> None:
    listed = set(cli.read_provenance_table(PROVENANCE.read_text(encoding="utf-8")))
    on_disk = _canon_files()
    assert listed == on_disk, (
        f"PROVENANCE.md table vs canon/: unlisted {sorted(on_disk - listed)}, "
        f"listed-but-absent {sorted(listed - on_disk)}"
    )


def test_m4_canon_carries_no_machine_path_and_no_name() -> None:
    hits = []
    for rel in sorted(_canon_files() | {"PROVENANCE.md"}):
        text = (CANON / rel).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            hits += [f"{rel}:{number} {hit}" for hit in _gate_hits(line)]
    assert not hits, f"the vendored canon still carries {len(hits)} hit(s):\n  " + "\n  ".join(
        hits[:30])


def test_m4_provenance_source_stamp_is_portable() -> None:
    source = sync_canon.parse_provenance(PROVENANCE.read_text(encoding="utf-8"))["source"]
    assert not Path(source).is_absolute() and not source.startswith("~"), (
        f"canon/PROVENANCE.md still stamps an absolute source: {source!r}"
    )


def test_m4_provenance_carries_the_tufalabs_attribution_section() -> None:
    text = PROVENANCE.read_text(encoding="utf-8")
    headings = [line for line in text.splitlines() if line.lstrip().startswith("#")]
    assert any(re.search(r"third[- ]party|tufalabs|attribution", h, re.IGNORECASE)
               for h in headings), f"PROVENANCE.md has no third-party section heading: {headings}"
    for needle in ("Tufalabs", "re-arc-3", "MIT", "LICENSE-MIT.md"):
        assert needle in text, f"PROVENANCE.md's attribution never mentions {needle!r} (FRONT B.2)"
    assert "neutraliz" in text.lower(), (
        "PROVENANCE.md carries no post-copy neutralization note naming its divergence from "
        "the duckWM source (FRONT A canon item 2a)"
    )


def test_m4_rearc3_mit_notice_is_vendored_with_its_attribution() -> None:
    notice = CANON / REARC_LICENSE_REL
    assert notice.is_file(), f"FRONT B.1 creates canon/{REARC_LICENSE_REL}"
    text = notice.read_text(encoding="utf-8")
    for needle in ("Permission is hereby granted", "Tufalabs", "re-arc-3", "v0.1.2",
                   "jeroencottaar/taaf-kaggle-source"):
        assert needle in text, f"canon/{REARC_LICENSE_REL} lacks {needle!r} (FRONT B.1)"


# =============================================================================
# M5 — the sync_canon round trip
# =============================================================================


def _duckwm_form() -> dict[str, dict[int, str]]:
    """Pre-contract lines of four scrubbed canon files, i.e. duckWM's bytes there
    (ambiguity L). Assembled at runtime: this file ships."""
    home = HOME_MARK + OPERATOR_FIRST.lower()
    checkout = home + "/Documents/GitHub/arc-agi/duckWM"
    frames = checkout + "/local-docs/arc-agi-3-generator/out/frames"
    cache = home + "/." + "cache/uv/archive-v0/KoydeoUZN85suecI/arcengine"
    op = OPERATOR_FIRST
    return {
        "design/objects/bestiary/cd82.md": {
            3: f"Source: `{checkout}/games/cd82/fb555c5d/cd82.py`",
            5: f"Frames: `{frames}/cd82/`.",
        },
        "design/objects/bestiary/tn36.md": {
            3: f"Source: `{checkout}/games/tn36/ef4dde99/tn36.py` (2647 lines;",
            5: f"Frames: `{frames}/tn36/`.",
            109: f"`{cache}`): `GameState.GAME_OVER` on click **61**",
        },
        "design/objects/affordance-language.md": {
            2: f"# **SIGNED OFF ({op}, 2026-09-18)**",
        },
        "spec-v0.3.md": {
            3: f"> **Status: APPROVED ({op}, 2026-09-21 — D26).** Assembled 2026-09-18 from",
            95: ("## §3 Mechanics vocabulary (source: vocabulary-v2-final.md, SIGNED D20 — 71 "
                 "terms + budget.time kept-flagged/unverified, 16 groups; header corrected per "
                 f"the B4 adjudication, {op}'s R1 ruling 2026-09-22)"),
            109: ("- **budget**: cap(25/141) · time(0/0) — KEPT flagged-unverified "
                  f"({op}'s ruling; any claim must show a wall-clock read)"),
            128: f"from the closed vocabulary {op}'s manual-play workstream validated against",
        },
    }


def _fake_duckwm_source(root: Path) -> Path:
    """A tmp duckWM canon: the public canon's derived files, with the four
    rebuilt files restored to their duckWM bytes. No PROVENANCE, no MIT notice —
    duckWM has neither."""
    src = root / "duckWM" / "local-docs" / "arc-agi-3-generator"
    for rel in sync_canon.derive_canon_paths(CANON):
        target = src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CANON / rel, target)
    for rel, lines in _duckwm_form().items():
        path = src / rel
        if not path.is_file():
            pytest.fail(f"{rel} is no longer a derived canon path; the round-trip rebuild is stale")
        rows = path.read_bytes().decode("utf-8").split("\n")
        for number, text in lines.items():
            rows[number - 1] = text
        path.write_bytes("\n".join(rows).encode("utf-8"))
    return src


def _sync(capsys, *argv: str) -> tuple[int, str]:
    """`sync_canon.main` with an explicit tmp `--dest` — and proof that the live
    canon/ was not written on the way (bytes + mtime)."""
    live_before = _sweep_source(CANON)
    rc = sync_canon.main(list(argv))
    captured = capsys.readouterr()
    touched = _diff_rows(live_before, _sweep_source(CANON))
    assert not touched, f"a sync into a tmp --dest wrote the LIVE canon/: {touched}"
    return rc, captured.out + captured.err


def _without_copied_line(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith("- Copied:"))


@pytest.fixture
def resynced(tmp_path: Path, capsys):
    src = _fake_duckwm_source(tmp_path)
    dest = tmp_path / "canon-out"
    rc, out = _sync(capsys, "--source", str(src), "--dest", str(dest))
    assert rc == 0, f"a sync into an EMPTY dest failed:\n{out[-2000:]}"
    return src, dest


def test_m5_resync_from_duckwm_bytes_reproduces_the_public_canon(resynced) -> None:
    _src, dest = resynced
    wrong = []
    for rel in sync_canon.derive_canon_paths(CANON):
        got, want = (dest / rel), (CANON / rel)
        if not got.is_file():
            wrong.append(f"{rel}: not written")
        elif got.read_bytes() != want.read_bytes():
            wrong.append(f"{rel}: {_first_difference(got.read_bytes(), want.read_bytes())}")
    assert not wrong, (
        "a re-sync from duckWM's bytes does NOT reproduce the public canon (FRONT A canon item "
        "3: the scrub must make it byte-for-byte):\n  " + "\n  ".join(wrong[:20])
    )


def test_m5_resync_never_resurrects_paths_or_names(resynced) -> None:
    _src, dest = resynced
    hits = []
    for rel in sorted(_files(dest)):
        if rel == "PROVENANCE.md":
            continue
        text = (dest / rel).read_text(encoding="utf-8", errors="replace")
        hits += [f"{rel}: {hit}" for hit in _gate_hits(text)]
    assert not hits, f"the re-synced canon resurrected {len(hits)} hit(s): {hits[:20]}"


def test_m5_resync_stamp_is_portable_and_keeps_the_attribution(resynced) -> None:
    _src, dest = resynced
    text = (dest / "PROVENANCE.md").read_text(encoding="utf-8")
    source = sync_canon.parse_provenance(text)["source"]
    assert not Path(source).is_absolute() and not source.startswith("~"), (
        f"the re-sync stamped an ABSOLUTE source path (sync_canon :212 must go portable): {source!r}"
    )
    assert HOME_MARK not in text, "the re-rendered PROVENANCE.md carries a home-directory path"
    masked = _masked(text, dest.parent)   # the tmp root holds both src and dest
    assert not NAME_RE.search(masked), (
        "the re-rendered PROVENANCE.md names a person (sync_canon :233's template)"
    )
    assert OPERATOR_RE.search(text) and "2026-09-29" in text, (
        "the PROVENANCE template lost its neutral 'operator' ruling attribution or its date"
    )
    assert "tufalabs" in text.lower() and "LICENSE-MIT.md" in text, (
        "a re-sync DROPS the Tufalabs attribution section — the template must carry it, or the "
        "next sync silently un-attributes the vendored re-arc-3 files"
    )
    assert "neutraliz" in text.lower(), "a re-sync drops the post-copy neutralization note"


def test_m5_resync_scrub_is_deterministic(tmp_path: Path, capsys) -> None:
    src = _fake_duckwm_source(tmp_path)
    one, two = tmp_path / "one", tmp_path / "two"
    for dest in (one, two):
        rc, out = _sync(capsys, "--source", str(src), "--dest", str(dest))
        assert rc == 0, f"sync into {dest.name} failed:\n{out[-2000:]}"
    assert _files(one) == _files(two), "two syncs of the same source wrote different file sets"
    differ = []
    for rel in sorted(_files(one)):
        a, b = (one / rel).read_bytes(), (two / rel).read_bytes()
        if rel == "PROVENANCE.md":
            a, b = (_without_copied_line(x.decode("utf-8")).encode() for x in (a, b))
        if a != b:
            differ.append(rel)
    assert not differ, f"the scrub is not deterministic — two runs differ in {differ}"


def test_m5_plain_resync_over_the_public_canon_is_a_no_op(tmp_path: Path, capsys) -> None:
    src = _fake_duckwm_source(tmp_path)
    dest = tmp_path / "canon"
    shutil.copytree(CANON, dest, ignore=shutil.ignore_patterns(".DS_Store"))
    rc, out = _sync(capsys, "--source", str(src), "--dest", str(dest))
    assert rc == 0, (
        "an UNFORCED re-sync from duckWM's bytes over the public canon did not succeed — the "
        "scrubbed files or the non-derived MIT notice read as divergent/orphaned:\n" + out[-2500:]
    )
    changed = []
    for rel in sorted(_canon_files()):
        got = dest / rel
        if not got.is_file():
            changed.append(f"{rel}: DELETED")
        elif got.read_bytes() != (CANON / rel).read_bytes():
            changed.append(f"{rel}: rewritten")
    assert not changed, f"a plain re-sync changed the public canon: {changed}"
    rows = cli.read_provenance_table((dest / "PROVENANCE.md").read_text(encoding="utf-8"))
    want = cli.read_provenance_table(PROVENANCE.read_text(encoding="utf-8"))
    assert rows == want, "the re-stamped sha256 table differs from the public canon's"


# =============================================================================
# M6 / M7 rig — a scratch copy of the repo, driven by pytest itself
# =============================================================================

CODEX_MODULE = "test_v2_codex.py"
D8_PREFIX = "test_d8_"
LATENCY_MODULE = "test_officials_conformance.py"
LATENCY_TEST = "test_action_probe"
DEDUPE_MODULES = ("test_b4_sampler.py", "test_b003_tiers_s0.py", "test_v2_hardening.py")
LATENCY_REL = "out/calibration/officials-latency.json"
HISTORY_REL = "out/ideas/dedupe-history.jsonl"
PLANTED_HISTORY = b'{"os2": "planted by the blind lane"}\n'
OLD_NS = 1_000_000_000 * 10**9          # 2001-09-09: any rewrite moves it
SCRATCH_DIRS = ("gen", "config", "canon", "worker-template", "tools")
SCRATCH_ROOT_FILES = ("pyproject.toml", "conftest.py", *SHIPPED_DOCS)

RIG_PLUGIN = '''\
"""Loaded with -p inside the OS-2 blind lane's scratch runs only."""
import json
import os
from pathlib import Path

_SPEC = json.loads(os.environ["OS2_RIG_SPEC"])
_RECORDS = []

if _SPEC.get("fake_officials"):
    import gen.officials as _officials

    class _Contracts:
        def action_probe_violations(self, game_class):
            return [], [0.001]

        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return lambda *args, **kwargs: []

    def _discover(cfg):
        return [_officials.Official(slug="zz00", variant="v0", game_id="zz00-v0",
                                    py_path=Path(_SPEC["fake_py"]), metadata={})]

    _officials.discover_officials = _discover
    _officials.load_contracts = lambda: _Contracts()
    _officials.load_official_class = lambda py_path: type("Zz00", (), {})


def _marked_skip(item):
    return any(True for name in ("skip", "skipif", "xfail") for _ in item.iter_markers(name))


def pytest_collection_modifyitems(session, config, items):
    named = _SPEC.get("named", {})
    first_of = set(_SPEC.get("first_of", []))
    keep, seen = [], set()
    for item in items:
        module = item.path.name
        if module in named:
            if getattr(item, "originalname", item.name).startswith(named[module]):
                keep.append(item)
        elif module in first_of and module not in seen and not _marked_skip(item):
            keep.append(item)
            seen.add(module)
    dropped = [item for item in items if item not in keep]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
    items[:] = keep


def pytest_runtest_logreport(report):
    detail = ""
    if report.skipped and isinstance(report.longrepr, tuple):
        detail = str(report.longrepr[2])
    elif report.longrepr:
        detail = str(report.longrepr)[-1500:]
    _RECORDS.append({"nodeid": report.nodeid, "when": report.when,
                     "outcome": report.outcome, "detail": detail})


def pytest_sessionfinish(session, exitstatus):
    import gen
    Path(_SPEC["results"]).write_text(json.dumps({
        "records": _RECORDS, "gen_file": gen.__file__, "exitstatus": int(exitstatus),
    }), encoding="utf-8")
'''


def _snapshot(root: Path) -> dict[str, tuple]:
    rows: dict[str, tuple] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir() and not path.is_symlink():
            rows[rel] = ("dir",)
        else:
            stat = path.lstat()
            rows[rel] = (stat.st_size, stat.st_mtime_ns, _sha256(path))
    return rows


def _build_scratch(base: Path) -> Path:
    """`base/arc-agi-games` (a copy of this repo's code) + a fake `base/duckWM`."""
    scratch = base / "arc-agi-games"
    junk = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    for name in SCRATCH_DIRS:
        if (REPO_ROOT / name).is_dir():
            shutil.copytree(REPO_ROOT / name, scratch / name, ignore=junk)
    for rel in SCRATCH_ROOT_FILES:
        if (REPO_ROOT / rel).is_file():
            (scratch / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / rel, scratch / rel)
    sibling = base / "duckWM"
    shutil.copytree(CANON, sibling / "local-docs" / "arc-agi-3-generator", ignore=junk)
    (sibling / "games" / "official").mkdir(parents=True)
    out = scratch / "out"
    (out / "ideas").mkdir(parents=True)
    (out / ".gitkeep").write_bytes(b"")
    history = scratch / HISTORY_REL
    history.write_bytes(PLANTED_HISTORY)
    os.utime(history, ns=(OLD_NS, OLD_NS))
    os.utime(out / ".gitkeep", ns=(OLD_NS, OLD_NS))
    return scratch


@dataclass
class RigRun:
    scratch: Path
    proc: subprocess.CompletedProcess
    results: dict
    before: dict
    after: dict

    def records(self, module: str, prefix: str = "") -> list[dict]:
        return [r for r in self.results.get("records", [])
                if f"{module}::{prefix}" in r["nodeid"]]

    def explain(self) -> str:
        return f"{_tail(self.proc, 2500)}\n--- records\n{json.dumps(self.results, indent=1)[:2500]}"


def _run_rig(base: Path, scratch: Path, spec: dict, targets: list[str], tag: str) -> RigRun:
    plugin_dir = base / "rig-plugin"
    plugin_dir.mkdir(exist_ok=True)
    (plugin_dir / "os2_rig.py").write_text(RIG_PLUGIN, encoding="utf-8")
    results_path = base / f"rig-results-{tag}.json"
    spec = {**spec, "results": str(results_path)}
    env = _child_env(OS2_RIG_SPEC=json.dumps(spec),
                     PYTHONPATH=os.pathsep.join((str(plugin_dir), str(scratch))))
    before = _snapshot(scratch / "out")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-p", "os2_rig", "-p", "no:cacheprovider",
         "-q", "-o", "addopts=", "--basetemp", str(base / f"basetemp-{tag}")],
        cwd=scratch, env=env, capture_output=True, text=True, timeout=TOOL_TIMEOUT_S, check=False,
    )
    after = _snapshot(scratch / "out")
    if not results_path.is_file():
        pytest.fail(f"rig: the scratch pytest run produced no results file:\n{_tail(proc)}")
    results = json.loads(results_path.read_text(encoding="utf-8"))
    run = RigRun(scratch, proc, results, before, after)
    gen_file = Path(results.get("gen_file", "")).resolve()
    if scratch.resolve() not in gen_file.parents:
        pytest.fail(f"rig: the scratch run imported gen from {gen_file}, not from the scratch "
                    "copy — refusing to read anything into it")
    return run


@pytest.fixture(scope="module")
def rig(tmp_path_factory) -> RigRun:
    """Run A: no smoke log; officials faked; one test per dedupe leak module."""
    base = tmp_path_factory.mktemp("os2-rig")
    scratch = _build_scratch(base)
    spec = {
        "fake_officials": True,
        "fake_py": str(base / "duckWM" / "games" / "official" / "zz00" / "v0" / "zz00.py"),
        "named": {CODEX_MODULE: D8_PREFIX, LATENCY_MODULE: LATENCY_TEST},
        "first_of": list(DEDUPE_MODULES),
    }
    targets = [f"gen/tests/{m}" for m in (CODEX_MODULE, LATENCY_MODULE, *DEDUPE_MODULES)]
    return _run_rig(base, scratch, spec, targets, "a")


@pytest.fixture(scope="module")
def rig_with_smoke(rig: RigRun) -> RigRun:
    """Run B: the same scratch, now WITH a smoke log; d8 only."""
    smoke = rig.scratch / SMOKE_LOG_REL
    smoke.parent.mkdir(parents=True, exist_ok=True)
    smoke.write_text("{}\n", encoding="utf-8")
    return _run_rig(rig.scratch.parent, rig.scratch, {"named": {CODEX_MODULE: D8_PREFIX}},
                    [f"gen/tests/{CODEX_MODULE}"], "b")


# =============================================================================
# M6 — d8 on a public clone
# =============================================================================


def test_m6_d8_skips_not_fails_without_the_smoke_log(rig: RigRun) -> None:
    assert "smoke/smoke.jsonl" not in rig.before, "rig: run A must start with no smoke log"
    records = rig.records(CODEX_MODULE, D8_PREFIX)
    assert records, f"rig: no {D8_PREFIX}* test was collected from {CODEX_MODULE}:\n{rig.explain()}"
    outcomes = {(r["when"], r["outcome"]) for r in records}
    failed = [r for r in records if r["outcome"] == "failed"]
    assert not failed, (
        f"d8 FAILS on a clone with no {SMOKE_LOG_REL} (FRONT C.1: it must skip):\n"
        + "\n".join(r["detail"][-600:] for r in failed)
    )
    skipped = [r for r in records if r["outcome"] == "skipped"]
    assert skipped, f"d8 did not skip without the smoke log; outcomes {sorted(outcomes)}"
    assert all(r["detail"].strip() for r in skipped), "d8's skip carries no reason"


def test_m6_d8_still_runs_when_the_smoke_log_exists(rig_with_smoke: RigRun) -> None:
    records = rig_with_smoke.records(CODEX_MODULE, D8_PREFIX)
    assert records, f"rig: d8 was not collected in run B:\n{rig_with_smoke.explain()}"
    skipped = [r for r in records if r["outcome"] == "skipped"]
    assert not skipped, (
        "d8 SKIPS even with a smoke log present — the skip must be conditional on the file's "
        f"absence, or d8 has stopped testing anything: {[r['detail'] for r in skipped]}"
    )


# =============================================================================
# M7 — suite hermeticity at the two known leak sites
# =============================================================================


def test_m7_latency_writer_leaves_out_untouched(rig: RigRun) -> None:
    ran = [r for r in rig.records(LATENCY_MODULE, LATENCY_TEST)
           if r["when"] == "call" and r["outcome"] == "passed"]
    if not ran:
        pytest.fail("rig could not exercise the latency writer (the faked officials' action "
                    f"probe never passed in the scratch run):\n{rig.explain()}")
    assert not (rig.scratch / LATENCY_REL).exists(), (
        f"a test run WROTE {LATENCY_REL} into the repo it ran from (FRONT C.2 — redirect it)"
    )
    leaked = [rel for rel in set(rig.after) - set(rig.before) if "calibration" in rel]
    assert not leaked, f"the latency writer still lands under out/: {sorted(leaked)}"


def test_m7_dedupe_history_is_neither_rewritten_nor_touched(rig: RigRun) -> None:
    unexercised = [
        module for module in DEDUPE_MODULES
        if not any(r["when"] == "setup" and r["outcome"] == "passed" for r in rig.records(module))
    ]
    if unexercised:
        pytest.fail(f"rig could not exercise {unexercised}: no test there set up in the scratch "
                    f"run, so its autouse history fixture never ran:\n{rig.explain()}")
    before, after = rig.before.get("ideas/dedupe-history.jsonl"), rig.after.get(
        "ideas/dedupe-history.jsonl")
    assert after is not None, f"{HISTORY_REL} was DELETED by the run"
    assert after[2] == before[2], f"{HISTORY_REL} was REWRITTEN with different bytes"
    assert after[1] == before[1], (
        f"{HISTORY_REL} was TOUCHED (mtime {before[1]} -> {after[1]}): a snapshot/restore that "
        "rewrites identical bytes is still a write into out/ (FRONT C.2)"
    )


def test_m7_the_leak_site_run_leaves_out_byte_identical(rig: RigRun) -> None:
    changes = _diff_rows(rig.before, rig.after)
    assert not changes, (
        "the scratch run of the leak-site tests changed out/ (paths relative to out/):\n  "
        + "\n  ".join(changes)
    )
