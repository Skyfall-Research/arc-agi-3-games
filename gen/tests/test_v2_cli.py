"""P-4 blind lane — the zero-YAML CLI: T1-T7, FROM THE FROZEN CONTRACT ALONE.

Run: .venv/bin/python -m pytest gen/tests/test_v2_cli.py -q

BLIND PROVENANCE. `docs/v2/contracts/P-4-cli.md` is the only statement of intent
this file was written from. `gen/cli.py` was never read — not a body, not a
signature listing, not a diff; at the time this file was written the module did
not exist on disk. The surfaces this file DID read are all public, all named by
P-4's own Evidence block or by the brief, and each is cited at the assertion
that leans on it:

  P-4 §Work 1-8 + §"Blind lane"  — every pin below traces to one of T1-T7.
  docs/v2/TRACKER.md             — P-4's board row, suite baseline 3337+12.
  docs/v2/DECISIONS.md           — the founding "small cli or script" ruling.
  config/template.yaml           — the data the CLI materializes FROM; parsed
      here as the raw baseline of every diff (never written to).
  config/b005r2-auto.yaml        — P-4 §Work 2 calls it "the live example of
      the full set", so the AUTONOMY OVERLAY constant below was MEASURED off it
      (its `verifier:`, `tiers:` and `review:` blocks) rather than guessed.
  gen/tests/test_v2_games.py     — the autouse repo-guard pattern (P-4 §Blind
      lane names it: "repo-guard autouse fixture like test_v2_games' — copy
      that pattern"), plus `_shape`.
  gen/tests/test_v2_codex.py     — the `_forbid_all_processes` booby trap (P-4
      T2 names it: "booby-trap pattern from test_v2_codex"), and the fact that
      `load_config` resolves canon against the REPO root, not the config's own
      directory.
  gen/config.REPO_ROOT           — name only, for the repo guard.
  gen/orchestrator / gen.config  — module-level PUBLIC constant NAMES only, for
      T6's snapshot compare. No body was read.

HOUSE RULE, enforced by the autouse guard below: no test may read the CLI's
allocation inputs from, or write anything into, the repo's real `config/`,
`out/batches/` or `games/`. Every root in this file is a tmp root, every
planted config and batch is tmp, HOME is tmp, cwd is tmp, and PATH's driver
binaries are inert tmp stubs that fail loudly if anything ever executes them.

CONTRACT AMBIGUITIES this file had to take a position on. Reported loudly in
the handback, never resolved quietly:

  A. THE PRE-RUN SEAM (T1's own words: "find the seam the implementer exposes,
     e.g. --dry-run or a build_config function; a missing seam is a loud
     finding"). BOTH exist and both are used. `_Lab.materialize` takes the
     LIBRARY seam first (a module-level build callable — `build_config`,
     `resolve_config`, ... — bound by PARAMETER NAME or handed an
     argparse-style namespace) because it is the only one that can be aimed at
     the planted fixtures; `_Lab.dry` drives the ARGV seam (a dry-ish flag on
     `run --help`), and `test_t1f` pins the two against each other end to end.
     With neither, the test FAILS LOUDLY naming every flag and every symbol
     probed, and never runs the un-dry `run`.
  B. THE ROOT SEAM — AND THE FINDING IT PRODUCED. P-4 specifies the id/seed
     scan over `config/` + `out/batches` with no parameter for where those
     live. `_Lab.aim` monkeypatches whichever module-level roots `gen.cli`
     exposes (REPO_ROOT / CONFIG_DIR / BATCHES_DIR / OUT_DIR / TEMPLATE_PATH /
     GAMES_DIR and their aliases), passes a root FLAG if `--help` offers one,
     and always sets tmp cwd + tmp HOME; `_call_build_seam` additionally aims
     every root PARAMETER the build callable offers. Whether the aim took is
     then MEASURED, never assumed. On this machine it takes for the library
     functions and NOT for the commands — see `FINDING_UNAIMABLE` below, which
     is why T3e and all of T5 are red. This file does not "fix" that by
     pointing a test at the real `config/`.
  C. WHERE `--name`'s WORD GOES IN THE FREENESS TEST. §Work 2 gives `n = first
     free among config/ + out/batches ids` and, separately, "`--name` appends
     `-<word>`". It does not say whether `gYYYYMMDD-2-fog` OCCUPIES n=2 for a
     later un-named run. T3 therefore pins the two readings' INTERSECTION as a
     hard invariant (the emitted id collides with no planted config stem and no
     planted batch dir, and shares its `gYYYYMMDD-<n>` prefix with none of
     them), and pins the literal "first free" only on un-named ids.
  D. "A COLLIDING EXPLICIT ID REFUSES" (T3) names a surface the flag list in
     §Work 1 does not contain — §Work 1 has no `--id`. T3e therefore PROBES
     `run --help` for one (`--id`, `--batch-id`, `--batch`) rather than
     assuming it; if the CLI has none the pin is SKIPPED with the reason spelt
     out, so the requirement cannot be lost (the P-1a H4 precedent), and the
     auto-allocator's never-collide half is pinned unconditionally in T3b.
     The implementation DOES ship `--id BATCH_ID`, so T3e runs — and dies on
     `FINDING_UNAIMABLE`, because the collision is checked against the real
     repo's ids and not the planted ones.
  E. T2's "before any config is written… or after writing but before spend —
     pin whichever the implementation does". A single test cannot pin a
     disjunction as an equality, so T2b pins what is NOT optional (loud
     failure, zero processes started, nothing under `games/`) and REPORTS the
     observed order in the assertion text, so the handback can state it.
  F. T4's "the tiers module's own error". `gen/tiers.py` is not a surface this
     lane may read, so "the tiers module's own error" is pinned structurally:
     the bad tier NAME must appear in the message, and the failure must either
     pass through a `tiers.py` frame or name the tier vocabulary — i.e. it must
     not be the CLI's own count message from T4a.
  G. T5's "monkeypatched run entry". P-4's Evidence block names exactly two
     public orchestrator surfaces — `main` (its argparse CLI, `--config X
     [--status]`) and `run_batch` — so BOTH are recorded, on `gen.orchestrator`
     AND on `gen.cli` (a `from gen.orchestrator import run_batch` would
     otherwise escape the patch), plus `subprocess.run`/`Popen` in case the CLI
     shells out to `python -m gen.orchestrator`. Any one of them carrying the
     persisted path satisfies the pin.
  H. NOT COVERED by T1-T7, and so not tested here (flagged to the lead):
     `python -m gen` (§Work 1's `gen/__main__.py`), the `play` subcommand and
     its exit 2 (§Work 5), the narration vocabulary and Ctrl-C resume line
     (§Work 4), the OPENROUTER_API_KEY warn-not-fail wording and the canon sha
     spot-check (§Work 3 — T2 only pins the codex-auth half of the preflight),
     the `pyproject` console script (§Work 6) and the README/RUNBOOK rewrite
     (§Work 7). T7 pinned the `--workers` guard until P-5 landed; it now pins
     the forwarding (LEAD EDIT 2026-09-30 — P-5's licensed T7 rewrite made
     this line false; see contract P-5 §Work 10). §Work 2's
     WRITE to `out/batches/<id>/config.yaml` is also unmeasurable here — see
     `test_t1e`'s skip text, which states the open question rather than
     pretending the pin landed.
  I. THE ONE READ-ONLY LEAK, declared: `test_t1f` and `test_t7b` drive the argv
     surface, which (per `FINDING_UNAIMABLE`) scans the REAL repo to allocate
     an id. Nothing is written — the autouse guard proves that on every test —
     and NO assertion in either test depends on repo state: the id is read back
     and only shape-checked, the seed is pinned by the flag, and every
     allocation pin lives in T3 on the hermetic seam.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import inspect
import io
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from gen import backends as backends_mod
from gen.config import REPO_ROOT

# --------------------------------------------------------------------------- #
# the repo surfaces no test may touch (P-4 §Hard rules + the blind-lane bullet)
# --------------------------------------------------------------------------- #

REPO_CONFIG = REPO_ROOT / "config"
REPO_OUT = REPO_ROOT / "out"
REPO_BATCHES = REPO_OUT / "batches"
REPO_GAMES = REPO_ROOT / "games"
TEMPLATE_PATH = REPO_CONFIG / "template.yaml"
B005R2_PATH = REPO_CONFIG / "b005r2-auto.yaml"

# --------------------------------------------------------------------------- #
# T6 half 2: the constant snapshot MUST straddle the `gen.cli` import, so it is
# taken here — before and after — and compared later. Taking it inside the test
# would measure every other test module's import too (P-4 T6 asks only whether
# IMPORTING gen.cli moves an orchestrator/config constant).
# --------------------------------------------------------------------------- #

_SNAPSHOT_MODULES = ("gen.config", "gen.orchestrator")


def _constants(module) -> dict[str, str]:
    """Public, non-callable, non-class module-level values, by repr."""
    snap: dict[str, str] = {}
    for name, value in vars(module).items():
        if name.startswith("_"):
            continue
        if inspect.ismodule(value) or inspect.isclass(value) or callable(value):
            continue
        try:
            snap[name] = repr(value)
        except (TypeError, ValueError, AttributeError, RecursionError) as exc:
            snap[name] = f"<unreprable: {type(exc).__name__}>"
    return snap


def _snapshot() -> dict[str, dict[str, str]]:
    for name in _SNAPSHOT_MODULES:
        __import__(name)
    return {name: _constants(sys.modules[name]) for name in _SNAPSHOT_MODULES}


#: was something else already holding `gen.cli`? Then T6b cannot measure.
_CLI_PREIMPORTED = "gen.cli" in sys.modules
_CONSTANTS_BEFORE_CLI = _snapshot()

try:
    from gen import cli as cli_mod

    _CLI_IMPORT_ERROR: str | None = None
except ImportError as exc:  # the pre-merge state: gen/cli.py does not exist yet
    cli_mod = None  # type: ignore[assignment]
    _CLI_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

_CONSTANTS_AFTER_CLI = _snapshot()


def _cli():
    """The module under test, or a loud pre-merge failure naming P-4 §Work 1."""
    if cli_mod is None:
        pytest.fail(
            "P-4 §Work 1 requires `gen/cli.py` with `main` (plus `gen/__main__.py`); "
            f"importing `gen.cli` raised {_CLI_IMPORT_ERROR}. Every pin in this file is "
            "blocked on that module existing. EXPECTED PRE-MERGE — never weaken a pin to "
            "make it pass."
        )
    return cli_mod


# --------------------------------------------------------------------------- #
# the contract's own numbers
# --------------------------------------------------------------------------- #

TEMPLATE_BYTES = TEMPLATE_PATH.read_bytes()
TEMPLATE = yaml.safe_load(TEMPLATE_BYTES.decode("utf-8"))

#: §Work 2, MEASURED off config/b005r2-auto.yaml (`verifier:` L409, `tiers:`
#: L634+L637, `review:` L706) — "exactly the b005r2 arming". Dotted keys.
AUTONOMY_OVERLAY: dict[str, object] = {
    "verifier.reject_cap": 1,
    "verifier.round_cap": 4,
    "verifier.reconcile_early": 2,
    "review.auto_accept": True,
    "tiers.knob_defaults_action": "kill",
    "tiers.goal_legible_cap": "obvious",
    #: contract L-1 (2026-10-01), the SEVENTH overlay key and the one that is
    #: not a b005r2 arming: the knob was written after that batch ran, so
    #: config/b005r2-auto.yaml carries no such key. `record` makes an
    #: undeclared-deception finding an advisory on the verifier report instead
    #: of a reject. `config/template.yaml` arms it too, so this key does not
    #: move the materialization diff; the CODE default is still `reject`.
    "verifier.deception_action": "record",
    #: contract E-2 (2026-10-05), the EIGHTH and NINTH, on the same footing as
    #: the seventh: both knobs were written after b005r2 ran, so that config
    #: carries neither. Armed, a downstream stage fail past `verifier.reject_cap`
    #: parks the slot instead of re-speccing it again (g20261001-5 rode that
    #: ladder to "package fail 4/1"), and an escalated re-spec whose findings no
    #: spec amendment could answer is skipped unspent. `config/template.yaml`
    #: arms both too, so neither moves the materialization diff; the CODE
    #: defaults are still false.
    "orchestrator.stage_fail_park": True,
    "orchestrator.respec_feasibility": True,
    #: PIN UPDATE, 2026-10-06 (contract Q-1 §4, a licensed overlay-pin edit, the
    #: E-2 idiom above). The TENTH, on the same footing as the seventh through
    #: ninth: the knob was written after b005r2 ran, so that config carries no
    #: such key. `record` makes a DISPUTED `undeclared-term` finding — one the
    #: blind audit itself grounded under two signed names, measured on
    #: two-keys-one-echo's `pend` queue — a record on the verifier report
    #: instead of a reject. `config/template.yaml` arms it too, so this key does
    #: not move the materialization diff; the CODE default is still `reject`.
    "verifier.term_dispute_action": "record",
}
#: §Work 2, the flag-driven keys. `batch.tier_sequence` is DELETED when --tiers
#: is absent ("else absent (the weighted draw)"), which counts as a diff key.
FLAG_KEYS = (
    "backends.default_driver",
    "batch.id",
    "batch.size",
    "batch.seed",
    "batch.tier_sequence",
)
TOUCHABLE_KEYS = frozenset(AUTONOMY_OVERLAY) | frozenset(FLAG_KEYS)

#: §Work 2 driver mapping, verbatim.
DRIVER_MAP = {"claude": "localclaude", "openai": "codex"}
#: the tier vocabulary every shipped config uses (template `tiers.seed_terms`).
TIERS = tuple(TEMPLATE["tiers"]["seed_terms"])  # ("t1", "t2", "t3")
BAD_TIER = "t9"
#: §Work 2 batch id: `gYYYYMMDD-<n>`, `--name` appends `-<word>`.
ID_RE = re.compile(r"^g(\d{8})-(\d+)(?:-(.+))?$")
#: config/template.yaml `codex.auth_env` — the variable the codex preflight reads.
CODEX_AUTH_ENV = TEMPLATE["backends"]["codex"]["auth_env"]  # "OPENAI_API_KEY"
#: config/template.yaml's own comment: `codex login` writes ~/.codex/auth.json.
CODEX_AUTH_RELPATH = Path(".codex") / "auth.json"

#: ambiguity A — the pre-run seams probed, in order.
DRY_FLAGS = ("--dry-run", "--dry", "--plan", "--print-config", "--no-run", "--check")
BUILD_SEAMS = (
    "build_config",
    "resolve_config",
    "materialize_config",
    "build_run_config",
    "resolved_config",
    "compose_config",
    "make_config",
    "plan_config",
)
#: ambiguity B — the root seams probed.
ROOT_FLAGS = ("--repo-root", "--root", "--repo", "--base-dir", "--project-root")
ROOT_ATTRS: dict[str, tuple[str, ...]] = {
    "repo": ("REPO_ROOT", "ROOT", "PROJECT_ROOT", "BASE_DIR"),
    "config_dir": ("CONFIG_DIR", "CONFIG_ROOT", "CONFIGS_DIR"),
    "batches_dir": ("BATCHES_DIR", "BATCHES_ROOT", "OUT_BATCHES", "OUT_BATCHES_DIR"),
    "out_dir": ("OUT_DIR", "OUT_ROOT"),
    "template": ("TEMPLATE_PATH", "TEMPLATE", "TEMPLATE_FILE", "TEMPLATE_CONFIG"),
    "games_dir": ("GAMES_DIR", "GAMES_ROOT", "SHELF_DIR", "SHELF_ROOT", "SHELF"),
}
#: ambiguity D — the explicit-id seam probed.
ID_FLAGS = ("--id", "--batch-id", "--batch")
#: T5 / ambiguity G — the orchestrator entries recorded.
ORCH_ENTRIES = ("run_batch", "main")

_MISSING = object()

#: MEASURED on this machine, 2026-09-30, and the reason T3e/T5 are red.
FINDING_UNAIMABLE = (
    "LOUD FINDING — P-4 §Blind lane: 'a missing seam that forces you at the real repo is a loud "
    "finding, not a workaround'.\n"
    "  THE COMMAND SURFACE OF gen.cli CANNOT BE AIMED AT A TMP REPO.\n"
    "  * The LIBRARY seam exists and this file rides it: `build_config`, `next_batch_id`, "
    "`next_seed` and `known_batch_ids` all accept `config_dir=` and `batches_root=`.\n"
    "  * The COMMAND seam does not: `run`, `resume` and `status` expose no `--root` / "
    "`--repo-root`, there is no environment override, and the DEFAULTS those functions fall back "
    "to are not redirected by any public module constant. MEASURED: with gen.cli.REPO_ROOT and "
    "gen.cli.CONFIG_DIR both monkeypatched at a tmp clone, `known_batch_ids()` and "
    "`next_batch_id()` still answer from the REAL repo (b001-pilot .. b005r2-auto); only "
    "`next_seed()` moves, and only its config/ half.\n"
    "  * Consequence: `resume BATCH_ID`, `status BATCH_ID` and `run --id` resolve against the "
    "real config/ + out/batches, so these pins cannot be measured hermetically. This file will "
    "NOT point a test at the real repo to turn them green.\n"
    "  FIX (implementer's call, either is fine): (a) thread a `--repo-root PATH` through the "
    "`cmd_*` functions into the `config_dir=`/`batches_root=` parameters that already exist, or "
    "(b) resolve those defaults through the module-level REPO_ROOT / CONFIG_DIR at CALL time so "
    "a monkeypatch reaches them."
)


# --------------------------------------------------------------------------- #
# tiny helpers
# --------------------------------------------------------------------------- #


def _shape(root: Path | None) -> dict[str, object] | None:
    """`{relative path: <dir> | size}` — test_v2_games' cheap big-tree guard."""
    if root is None or not Path(root).exists():
        return None
    root = Path(root)
    return {
        str(path.relative_to(root)): "<dir>" if path.is_dir() else path.stat().st_size
        for path in sorted(root.rglob("*"))
        if "__pycache__" not in path.parts
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _flat(node, prefix: str = "") -> dict[str, object]:
    """Dotted-key flattening of the DICT spine; lists and scalars are leaves."""
    out: dict[str, object] = {}
    for key, value in node.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flat(value, dotted + "."))
        else:
            out[dotted] = value
    return out


def _diff(before: dict, after: dict) -> dict[str, tuple[object, object]]:
    """Every dotted key whose value changed, appeared or vanished."""
    flat_before, flat_after = _flat(before), _flat(after)
    keys = set(flat_before) | set(flat_after)
    return {
        key: (flat_before.get(key, _MISSING), flat_after.get(key, _MISSING))
        for key in sorted(keys)
        if flat_before.get(key, _MISSING) != flat_after.get(key, _MISSING)
    }


def _show(diff: dict[str, tuple[object, object]]) -> str:
    def cell(value):
        return "<absent>" if value is _MISSING else repr(value)

    return "\n".join(f"  {key}: {cell(old)} -> {cell(new)}" for key, (old, new) in diff.items())


def _set_dotted(node: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _del_dotted(node: dict, dotted: str) -> None:
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node.get(part)
        if not isinstance(node, dict):
            return
    node.pop(parts[-1], None)


def _get_dotted(node: dict, dotted: str):
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _today() -> str:
    """Local-date stamp — the same clock `gYYYYMMDD-<n>` is minted from."""
    return time.strftime("%Y%m%d")


_YAML_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:")


def _yaml_in(text: str) -> dict | None:
    """The resolved config printed inside other prose, or None.

    Generic on purpose (no implementer banner is hard-coded): the block is the
    maximal run of YAML-shaped lines — a top-level key, an indented line, a
    list item, a comment or a blank — starting at the first top-level key and
    stopping at the first line that is none of those (a `---` fence included).
    """
    whole = None
    try:
        whole = yaml.safe_load(text)
    except yaml.YAMLError:
        whole = None
    if isinstance(whole, dict) and "batch" in whole:
        return whole
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if _YAML_KEY.match(line)]
    for start in starts:
        end = start
        while end < len(lines):
            line = lines[end]
            if line.startswith("---"):
                break
            if not (
                _YAML_KEY.match(line)
                or not line.strip()
                or line.startswith(("#", " ", "\t"))
                or line.lstrip().startswith("- ")
            ):
                break
            end += 1
        try:
            block = yaml.safe_load("\n".join(lines[start:end]))
        except yaml.YAMLError:
            continue
        if isinstance(block, dict) and "batch" in block:
            return block
    return None


# --------------------------------------------------------------------------- #
# the no-spend rig (T2's "booby-trap pattern from test_v2_codex")
# --------------------------------------------------------------------------- #


class _FakePopen:
    """A recorded, inert `Popen` — nothing is ever executed."""

    def __init__(self, cmd, *args, **kwargs):
        self.args = cmd
        self.returncode = 0
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("")
        self.pid = -1

    def communicate(self, *args, **kwargs):
        return "", ""

    def wait(self, *args, **kwargs):
        return 0

    def poll(self):
        return 0

    def kill(self):
        return None

    def terminate(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _describe(args, kwargs) -> str:
    return f"{args!r} {kwargs!r}"


# --------------------------------------------------------------------------- #
# the lab: one tmp repo, aimed at, with every spend seam trapped
# --------------------------------------------------------------------------- #


@dataclass
class Result:
    argv: list[str]
    code: int | None
    stdout: str
    stderr: str
    exc: BaseException | None
    trace: str

    @property
    def text(self) -> str:
        tail = "" if self.exc is None else f"\n{type(self.exc).__name__}: {self.exc}\n{self.trace}"
        return f"{self.stdout}\n{self.stderr}{tail}"

    @property
    def failed(self) -> bool:
        return self.exc is not None or (self.code not in (0, None))

    def __str__(self) -> str:  # pragma: no cover - failure prose only
        return f"`{' '.join(self.argv)}` -> exit {self.code}\n{self.text}"


@dataclass
class Materialized:
    config: dict
    path: Path | None
    result: Result
    via: str

    @property
    def batch_id(self) -> str:
        value = _get_dotted(self.config, "batch.id")
        assert isinstance(value, str), f"batch.id missing from the resolved config: {self.config!r}"
        return value


@dataclass
class _Lab:
    root: Path
    monkeypatch: pytest.MonkeyPatch
    seams: dict[str, str] = field(default_factory=dict)
    calls: list[dict] = field(default_factory=list)
    _help: dict[str, str] = field(default_factory=dict)

    # --- layout ---------------------------------------------------------- #

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def batches_dir(self) -> Path:
        return self.root / "out" / "batches"

    @property
    def games_dir(self) -> Path:
        return self.root / "games"

    @property
    def template(self) -> Path:
        return self.config_dir / "template.yaml"

    def plant_config(self, stem: str, *, seed: int, batch_id: str | None = None) -> Path:
        """A FULL template-derived config in the tmp `config/` (the id/seed scan's
        input). Full, not a stub, because the scan may `load_config` it."""
        data = copy.deepcopy(TEMPLATE)
        data["batch"]["id"] = batch_id or stem
        data["batch"]["seed"] = seed
        path = self.config_dir / f"{stem}.yaml"
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return path

    def plant_batch(self, batch_id: str, *, seed: int | None = None) -> Path:
        directory = self.batches_dir / batch_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "ledger.jsonl").write_text("", encoding="utf-8")
        if seed is not None:
            data = copy.deepcopy(TEMPLATE)
            data["batch"]["id"] = batch_id
            data["batch"]["seed"] = seed
            (directory / "config.yaml").write_text(
                yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
            )
        return directory

    # --- aiming (ambiguity B) -------------------------------------------- #

    def aim(self) -> None:
        module = _cli()
        targets = {
            "repo": self.root,
            "config_dir": self.config_dir,
            "batches_dir": self.batches_dir,
            "out_dir": self.root / "out",
            "template": self.template,
            "games_dir": self.games_dir,
        }
        for kind, names in ROOT_ATTRS.items():
            for name in names:
                if hasattr(module, name):
                    current = getattr(module, name)
                    value = targets[kind]
                    self.monkeypatch.setattr(
                        module, name, str(value) if isinstance(current, str) else value
                    )
                    self.seams[name] = str(value)
                    break

    @property
    def probe_report(self) -> str:
        found = ", ".join(f"{k}={v}" for k, v in sorted(self.seams.items())) or "NONE"
        return (
            f"root seams FOUND on gen.cli: {found}. Probed attributes: "
            f"{sorted(n for names in ROOT_ATTRS.values() for n in names)}; probed flags: "
            f"{list(ROOT_FLAGS)}; cwd and HOME are both {self.root}."
        )

    # --- invoking --------------------------------------------------------- #

    def help_text(self, *subcommand: str) -> str:
        key = " ".join(subcommand)
        if key not in self._help:
            self._help[key] = self.invoke([*subcommand, "--help"]).text
        return self._help[key]

    def options(self, *subcommand: str) -> set[str]:
        return set(re.findall(r"--[A-Za-z][A-Za-z0-9-]*", self.help_text(*subcommand)))

    def invoke(self, argv) -> Result:
        module = _cli()
        main = getattr(module, "main", None)
        if main is None:
            pytest.fail(
                "P-4 §Work 6 pins the console script `arc-games = gen.cli:main`, so `gen.cli` "
                f"must expose `main`; it exposes {sorted(n for n in vars(module) if not n.startswith('_'))}"
            )
        argv = [str(item) for item in argv]
        out, err = io.StringIO(), io.StringIO()
        exc: BaseException | None = None
        trace = ""
        code: int | None = 0
        saved = sys.argv
        sys.argv = ["arc-games", *argv]
        try:
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    returned = main(argv) if _accepts_argv(main) else main()
                    if isinstance(returned, bool):
                        code = int(returned)
                    elif isinstance(returned, int):
                        code = returned
                    else:
                        code = 0
                except SystemExit as stop:
                    code = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
                except BaseException as boom:  # noqa: BLE001 - the CLI's loudness is the pin
                    exc, code = boom, None
                    trace = "".join(traceback.format_tb(boom.__traceback__))
        finally:
            sys.argv = saved
        return Result(argv, code, out.getvalue(), err.getvalue(), exc, trace)

    def run_argv(
        self,
        *,
        driver: str = "claude",
        games: int = 2,
        seed: int | None = None,
        tiers=None,
        name: str | None = None,
        workers: int | None = None,
        dry: str | None = None,
        extra=(),
    ) -> list[str]:
        argv = ["run", "--driver", driver, "--games", str(games)]
        if tiers is not None:
            argv += ["--tiers", tiers if isinstance(tiers, str) else ",".join(tiers)]
        if name is not None:
            argv += ["--name", name]
        if seed is not None:
            argv += ["--seed", str(seed)]
        if workers is not None:
            argv += ["--workers", str(workers)]
        argv += list(extra)
        options = self.options("run")
        for flag in ROOT_FLAGS:
            if flag in options:
                argv += [flag, str(self.root)]
                self.seams[flag] = str(self.root)
                break
        if "--yes" in options:
            argv.append("--yes")
        if dry:
            argv.append(dry)
        return argv

    def dry_flag(self) -> str | None:
        options = self.options("run")
        for flag in DRY_FLAGS:
            if flag in options:
                return flag
        return None

    # --- ambiguity A: the pre-run seam ------------------------------------ #

    def dry(self, **flags) -> tuple[Result, dict | None, Path | None]:
        """The ARGV half of ambiguity A: `run ... --dry-run`, end to end, no spend."""
        flag = self.dry_flag()
        if flag is None:
            pytest.fail(
                "T1 needs a no-spend seam on the argv surface. `run --help` offers "
                f"{sorted(self.options('run'))}, none of {list(DRY_FLAGS)}. LOUD FINDING."
            )
        before = set(self._written())
        result = self.invoke(self.run_argv(dry=flag, **flags))
        config, path = self._harvest(before, result)
        return result, config, path

    def materialize(self, **flags) -> Materialized:
        """The HERMETIC half of ambiguity A.

        The library seam is tried FIRST and the argv seam second, because only
        the library seam can be aimed at the planted fixtures: MEASURED on this
        machine, `gen.cli`'s `build_config` / `next_batch_id` / `next_seed` /
        `known_batch_ids` all take `config_dir=` + `batches_root=`, but the
        `run`/`resume`/`status` commands pass none of them and no public module
        constant redirects the defaults (see `FINDING_UNAIMABLE`). Driving the
        argv surface here would silently measure the REAL repo's config/ and
        out/batches, which the blind-lane bullet forbids. `test_t1f` pins the
        argv surface against this one, end to end, on the keys that do not
        depend on repo state.
        """
        module = _cli()
        result: Result | None = None
        seam = self._build_seam(module)
        if seam is not None:
            name, function = seam
            config = _call_build_seam(function, flags, self)
            return Materialized(
                config, None, Result([f"<{name}()>"], 0, "", "", None, ""), f"gen.cli.{name}()"
            )
        if self.dry_flag():
            result, config, path = self.dry(**flags)
            if config is not None:
                return Materialized(config, path, result, f"`run {self.dry_flag()}`")
        pytest.fail(
            "T1 NEEDS A NO-SPEND SEAM this file can read a resolved config from, and gen.cli "
            f"exposes none that worked. Probed flags on `run --help`: {list(DRY_FLAGS)} (the "
            f"parser offers {sorted(self.options('run'))}); probed callables on gen.cli: "
            f"{list(BUILD_SEAMS)} (the module exposes "
            f"{sorted(n for n in vars(module) if not n.startswith('_'))}). This file will NOT "
            f"run the un-dry `run` to get a config — that is the spend T1 forbids. "
            f"{self.probe_report}\n{result}"
        )

    def _build_seam(self, module):
        for name in BUILD_SEAMS:
            function = getattr(module, name, None)
            if callable(function):
                return name, function
        return None

    def _written(self) -> list[Path]:
        if not self.batches_dir.exists():
            return []
        return sorted(self.batches_dir.glob("*/config.yaml"))

    def _harvest(self, before: set, result: Result | None):
        fresh = [path for path in self._written() if path not in before]
        if len(fresh) == 1:
            return yaml.safe_load(fresh[0].read_text(encoding="utf-8")), fresh[0]
        if len(fresh) > 1:
            pytest.fail(
                f"§Work 2 writes ONE resolved config per run; this call wrote {len(fresh)}: {fresh}"
            )
        if result is not None:
            printed = _yaml_in(result.stdout)
            if printed is not None:
                return printed, None
        return None, None

    # --- spend traps ------------------------------------------------------ #

    def forbid_spend(self) -> None:
        """test_v2_codex's `_forbid_all_processes`, widened to the batch entries.

        Belt AND braces: `backends._run` is the driver seam, `subprocess` is the
        floor under it, and `orchestrator.run_batch`/`main` is the batch itself.
        A materialization that trips ANY of them has spent, which is what T1's
        "WITHOUT spending" and T2's "before any spend" forbid.
        """

        def boom(*args, **kwargs):  # pragma: no cover - the assertion IS the body
            raise AssertionError(f"a process/batch was started: {_describe(args, kwargs)}")

        self.monkeypatch.setattr(backends_mod, "_run", boom, raising=False)
        for name in ("run", "Popen", "call", "check_call", "check_output"):
            self.monkeypatch.setattr(subprocess, name, boom, raising=False)
        for name in ("system", "execv", "execvp", "execvpe", "spawnv", "posix_spawn"):
            self.monkeypatch.setattr(os, name, boom, raising=False)
        self._patch_orchestrator(lambda entry: boom)

        def no_prompt(*args, **kwargs):
            raise AssertionError(
                "the CLI read stdin; §Work 3 says `--yes` skips the final prompt and a "
                f"pre-run/no-spend path must never block on one: {_describe(args, kwargs)}"
            )

        self.monkeypatch.setattr("builtins.input", no_prompt)

    def record_orchestrator(self) -> list[dict]:
        """T5: record instead of trap — every entry, every argv, nothing executed."""

        def recorder(entry):
            def call(*args, **kwargs):
                self.calls.append({"entry": entry, "args": args, "kwargs": kwargs})
                return 0

            return call

        self._patch_orchestrator(recorder)

        def fake_run(cmd, *args, **kwargs):
            self.calls.append({"entry": "subprocess.run", "args": (cmd, *args), "kwargs": kwargs})
            listed = list(cmd) if not isinstance(cmd, (str, bytes)) else [cmd]
            return subprocess.CompletedProcess(listed, 0, stdout="", stderr="")

        def fake_popen(cmd, *args, **kwargs):
            self.calls.append({"entry": "subprocess.Popen", "args": (cmd, *args), "kwargs": kwargs})
            return _FakePopen(cmd)

        self.monkeypatch.setattr(subprocess, "run", fake_run)
        self.monkeypatch.setattr(subprocess, "Popen", fake_popen)
        return self.calls

    def _patch_orchestrator(self, factory) -> None:
        import gen.orchestrator as orch

        module = _cli()
        for name in ORCH_ENTRIES:
            replacement = factory(f"orchestrator.{name}")
            if hasattr(orch, name):
                self.monkeypatch.setattr(orch, name, replacement, raising=False)
            # ambiguity G: `from gen.orchestrator import run_batch` binds a SECOND name.
            bound = getattr(module, name, None)
            if bound is not None and name != "main":
                self.monkeypatch.setattr(module, name, replacement, raising=False)

    def mentions(self, needle: str) -> bool:
        return any(needle in repr(call) for call in self.calls)

    @property
    def call_report(self) -> str:
        if not self.calls:
            return f"NO orchestrator entry was called. Patched: {list(ORCH_ENTRIES)} + subprocess."
        return "\n".join(f"  {call['entry']}: {call['args']!r} {call['kwargs']!r}" for call in self.calls)


def _accepts_argv(main) -> bool:
    """`main(argv)` (testable) vs `main()` (console-script shape) — both supported."""
    try:
        parameters = [
            parameter
            for parameter in inspect.signature(main).parameters.values()
            if parameter.kind
            in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD, parameter.VAR_POSITIONAL)
        ]
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return False
    return bool(parameters)


def _call_build_seam(function, flags: dict, lab: _Lab) -> dict:
    """Bind T1's flags onto a build callable BY PARAMETER NAME (ambiguity A)."""
    aliases = {
        "driver": ("driver",),
        "games": ("games", "size", "n_games", "game_count", "count", "n"),
        "seed": ("seed",),
        "tiers": ("tiers", "tier_sequence", "tier_list"),
        "name": ("name", "label", "topic", "suffix"),
        "workers": ("workers", "worker_count", "slots"),
    }
    values = {
        "driver": flags.get("driver", "claude"),
        "games": flags.get("games", 2),
        "seed": flags.get("seed"),
        "tiers": flags.get("tiers"),
        "name": flags.get("name"),
        "workers": flags.get("workers"),
    }
    if isinstance(values["tiers"], str):
        values["tiers"] = values["tiers"].split(",")
    #: ambiguity B: whatever ROOT parameters the seam offers get aimed at tmp too, so the
    #: id/seed scan reads the planted fixtures and not the repo's real `config/`.
    roots = {
        "root": lab.root,
        "repo_root": lab.root,
        "config_dir": lab.config_dir,
        "batches_root": lab.batches_dir,
        "batches_dir": lab.batches_dir,
        "out_root": lab.root / "out",
        "template_path": lab.template,
        "games_root": lab.games_dir,
        "yes": True,
    }
    signature = inspect.signature(function)
    parameters = signature.parameters
    positional = [p for p in parameters.values() if p.kind is p.POSITIONAL_OR_KEYWORD]
    if len(positional) == 1 and positional[0].name in ("args", "ns", "namespace", "opts", "options"):
        namespace = SimpleNamespace(**values, **roots)
        result = function(namespace)
    else:
        kwargs = {}
        for logical, names in aliases.items():
            for candidate in names:
                if candidate in parameters:
                    kwargs[candidate] = values[logical]
                    break
        for extra, value in roots.items():
            if extra in parameters:
                kwargs[extra] = value
                lab.seams[f"{function.__name__}({extra}=)"] = str(value)
        unmet = [
            parameter.name
            for parameter in parameters.values()
            if parameter.default is parameter.empty
            and parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
            and parameter.name not in kwargs
        ]
        if unmet:
            pytest.fail(
                f"T1's build seam `{function.__name__}{signature}` has required parameters this "
                f"file cannot bind from P-4's flag list: {unmet}. Ambiguity A: the seam must be "
                "drivable from `--driver/--games/--tiers/--name/--seed/--workers` alone."
            )
        result = function(**kwargs)
    if isinstance(result, tuple):
        result = next((item for item in result if isinstance(item, dict)), result[0])
    if not isinstance(result, dict):
        pytest.fail(
            f"T1's build seam `{function.__name__}` returned {type(result).__name__}, not the "
            "resolved config mapping the byte-level dict diff needs."
        )
    return result


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _repo_is_never_the_workspace():
    """P-4 §Hard rules: tmp roots only, and `config/template.yaml` is READ-ONLY.

    `config/` is small, so it is guarded by sha as well as shape (T6's template
    immutability is a standing invariant, not one test's). `out/batches/` and
    `games/` are guarded by shape — names plus sizes catch any entry a stray
    call would add, remove or resize, at no hashing cost per test.
    """
    watched = {
        f"the repo config dir {REPO_CONFIG}": REPO_CONFIG,
        f"the repo batches dir {REPO_BATCHES}": REPO_BATCHES,
        f"the repo shelf {REPO_GAMES}": REPO_GAMES,
    }
    before = {what: _shape(root) for what, root in watched.items()}
    template_before = _sha(TEMPLATE_PATH)
    yield
    for what, root in watched.items():
        assert _shape(root) == before[what], f"a test wrote into {what}"
    assert _sha(TEMPLATE_PATH) == template_before, (
        f"a test modified {TEMPLATE_PATH} — P-4 §Hard rules: 'template.yaml read-only to the "
        "CLI and to you'"
    )


@pytest.fixture
def lab(tmp_path, monkeypatch) -> _Lab:
    """A tmp repo the CLI is aimed at, with every spend seam booby-trapped."""
    root = tmp_path / "clone"
    (root / "config").mkdir(parents=True)
    (root / "out" / "batches").mkdir(parents=True)
    (root / "games").mkdir()
    (root / "home").mkdir()
    shutil.copyfile(TEMPLATE_PATH, root / "config" / "template.yaml")
    # P-2 vendored canon: a read-only symlink keeps a canon spot-check green
    # without copying 38 files per test. Never written through.
    canon = REPO_ROOT / "canon"
    if canon.is_dir():
        (root / "canon").symlink_to(canon, target_is_directory=True)

    stub_bin = root / "bin"
    stub_bin.mkdir()
    for binary in ("claude", "codex"):
        stub = stub_bin / binary
        stub.write_text(
            "#!/bin/sh\necho 'blind-lane stub: this binary must never be executed' >&2\nexit 97\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)

    monkeypatch.chdir(root)
    monkeypatch.setenv("HOME", str(root / "home"))
    monkeypatch.setenv("PATH", f"{stub_bin}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("PLAY_GAMES_DIR", str(root / "games"))

    workbench = _Lab(root=root, monkeypatch=monkeypatch)
    workbench.aim()
    workbench.forbid_spend()
    return workbench


# =============================================================================
# T1 — materialization: template + overlay + flags, and nothing else
# =============================================================================


def _t1(lab: _Lab) -> Materialized:
    """T1's exact invocation: `run --driver claude --games 2 --seed 99 --tiers t1,t2`."""
    return lab.materialize(driver="claude", games=2, seed=99, tiers="t1,t2")


def _expected(observed_id: str, *, driver="claude", games=2, seed=99, tiers=("t1", "t2")) -> dict:
    expected = copy.deepcopy(TEMPLATE)
    for dotted, value in AUTONOMY_OVERLAY.items():
        _set_dotted(expected, dotted, value)
    _set_dotted(expected, "backends.default_driver", DRIVER_MAP[driver])
    _set_dotted(expected, "batch.id", observed_id)
    _set_dotted(expected, "batch.size", games)
    _set_dotted(expected, "batch.seed", seed)
    if tiers is None:
        _del_dotted(expected, "batch.tier_sequence")
    else:
        _set_dotted(expected, "batch.tier_sequence", list(tiers))
    return expected


def test_t1a_the_resolved_config_is_template_plus_overlay_plus_flags(lab):
    """T1: resolved == template + overlay + flags, exactly."""
    made = _t1(lab)
    expected = _expected(made.batch_id)
    drift = _diff(expected, made.config)
    assert not drift, (
        f"T1: the resolved config (via {made.via}) is not `template + overlay + flags`. "
        f"Divergences (expected -> resolved):\n{_show(drift)}\n"
        f"The overlay this file holds is MEASURED off config/b005r2-auto.yaml: {AUTONOMY_OVERLAY}"
    )


def test_t1b_the_diff_against_the_raw_template_is_exactly_the_overlay_and_flag_keys(lab):
    """T1: "differs from raw template EXACTLY on the overlay+flag keys"."""
    made = _t1(lab)
    drift = _diff(TEMPLATE, made.config)
    stray = {key: value for key, value in drift.items() if key not in TOUCHABLE_KEYS}
    assert not stray, (
        "T1: the CLI moved template keys that are neither the AUTONOMY OVERLAY nor a flag "
        f"(§Work 2). Stray keys:\n{_show(stray)}\nLicensed keys: {sorted(TOUCHABLE_KEYS)}"
    )
    for dotted, value in AUTONOMY_OVERLAY.items():
        assert _get_dotted(made.config, dotted) == value, (
            f"T1 overlay: {dotted} is {_get_dotted(made.config, dotted)!r}, the b005r2 arming "
            f"P-4 §Work 2 names is {value!r} (raw template: "
            f"{_get_dotted(TEMPLATE, dotted)!r})"
        )
    assert _get_dotted(made.config, "backends.default_driver") == "localclaude", (
        "§Work 2 driver mapping: claude -> localclaude in backends.default_driver, got "
        f"{_get_dotted(made.config, 'backends.default_driver')!r}"
    )
    assert _get_dotted(made.config, "batch.size") == 2, "§Work 2: size = --games"
    assert _get_dotted(made.config, "batch.seed") == 99, "§Work 2: --seed wins over the auto seed"
    assert _get_dotted(made.config, "batch.tier_sequence") == ["t1", "t2"], (
        "§Work 2: tier_sequence comes from --tiers"
    )
    overlay_constant = getattr(_cli(), "AUTONOMY_OVERLAY", None)
    assert overlay_constant is not None, (
        "§Work 2: the AUTONOMY OVERLAY is 'an explicit module-level dict'; gen.cli has no "
        "AUTONOMY_OVERLAY"
    )
    assert _flat(overlay_constant) == AUTONOMY_OVERLAY, (
        "§Work 2: the overlay must be 'exactly the b005r2 arming'. gen.cli.AUTONOMY_OVERLAY "
        f"flattens to {_flat(overlay_constant)}; config/b005r2-auto.yaml carries "
        f"{AUTONOMY_OVERLAY}"
    )
    assert ID_RE.match(made.batch_id), (
        f"§Work 2 batch id shape is `gYYYYMMDD-<n>` (+`-<word>` with --name); got {made.batch_id!r}"
    )
    assert ID_RE.match(made.batch_id).group(1) == _today(), (
        f"§Work 2: the id's date is today's; got {made.batch_id!r} on {_today()}"
    )


def test_t1c_without_tiers_the_weighted_draw_is_restored(lab):
    """§Work 2: "tier_sequence from --tiers ... else absent (the weighted draw)".

    The template SHIPS `batch.tier_sequence: [t1, t2]`, so "absent" is a
    deletion the CLI has to perform, not a no-op.
    """
    assert _get_dotted(TEMPLATE, "batch.tier_sequence") is not _MISSING, (
        "this pin assumes config/template.yaml ships a batch.tier_sequence; it no longer does"
    )
    made = lab.materialize(driver="claude", games=2, seed=99, tiers=None)
    assert _get_dotted(made.config, "batch.tier_sequence") is _MISSING, (
        "§Work 2: with no --tiers the resolved config must carry NO tier_sequence (the weighted "
        f"draw); it carries {_get_dotted(made.config, 'batch.tier_sequence')!r}"
    )
    drift = _diff(_expected(made.batch_id, tiers=None), made.config)
    assert not drift, f"T1 (no --tiers):\n{_show(drift)}"


def test_t1d_materializing_a_config_spends_nothing(lab):
    """T1: "the config must be writable and inspectable WITHOUT spending"."""
    made = _t1(lab)  # every process/batch seam is trapped by the `lab` fixture
    assert made.config, "no resolved config came back"
    assert not lab.calls, f"a batch entry was reached during materialization:\n{lab.call_report}"


def test_t1e_the_resolved_config_lands_under_out_batches(lab):
    """§Work 2: "Write the RESOLVED config to out/batches/<id>/config.yaml"."""
    made = _t1(lab)
    path = made.path
    if path is None:
        # LEAD RE-POINT (2026-09-30, at the Wave C merge). This pin's original
        # skip named the two resolutions it would accept, and BOTH now exist:
        # write_config grew `batches_root=` and gen.cli.BATCHES_ROOT is a
        # public call-time constant. The no-write --dry-run stands as RATIFIED
        # (rehearsals must not burn batch ids), so §Work 2's write is pinned
        # here through the parameter route against the lab's tmp root.
        from gen import cli as _cli

        path = _cli.write_config(
            made.config, _cli.render_config(made.config), batches_root=lab.batches_dir
        )
    assert path == lab.batches_dir / made.batch_id / "config.yaml", (
        f"§Work 2: the resolved config belongs at out/batches/<id>/config.yaml; it is at "
        f"{path} with batch.id {made.batch_id!r}. {lab.probe_report}"
    )
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == made.config


def test_t1f_the_argv_dry_run_resolves_the_same_config_end_to_end(lab):
    """T1 through the ARGV surface: `run ... --dry-run`, no spend, same answer.

    THE ONE READ-ONLY LEAK IN THIS FILE, declared: because the command surface
    cannot be aimed (`FINDING_UNAIMABLE`), this dry run scans the REAL repo's
    `config/` + `out/batches` to allocate its id. Nothing is written (the
    autouse guard proves it) and NOTHING ASSERTED HERE DEPENDS ON REPO STATE —
    the id is read back and only shape-checked, and the seed is pinned by the
    flag. Every id/seed ALLOCATION pin lives in T3, on the hermetic seam.
    """
    result, printed, _ = lab.dry(driver="claude", games=2, seed=99, tiers="t1,t2")
    assert not result.failed, f"T1: the no-spend dry run must succeed on this machine.\n{result}"
    assert not lab.calls, f"the dry run reached a batch entry:\n{lab.call_report}"
    if printed is None:
        pytest.fail(
            "T1: `run --dry-run` must make the resolved config INSPECTABLE without spending; "
            "nothing on stdout parsed as a YAML mapping with a `batch` key, and nothing was "
            f"written under {lab.batches_dir}.\n{result}"
        )
    batch_id = _get_dotted(printed, "batch.id")
    assert isinstance(batch_id, str) and ID_RE.match(batch_id), (
        f"§Work 2 id shape `gYYYYMMDD-<n>`; the dry run printed {batch_id!r}"
    )
    drift = _diff(_expected(batch_id), printed)
    assert not drift, (
        "T1: the config the ARGV surface resolves differs from `template + overlay + flags`:\n"
        f"{_show(drift)}\n{result}"
    )


# =============================================================================
# T2 — driver mapping + the codex path
# =============================================================================


def test_t2a_openai_maps_to_codex_in_default_driver(lab, monkeypatch):
    """T2: "openai->codex lands in default_driver".

    The auth variable is set to an obvious non-key so the presence-only codex
    preflight (P-1a, presence-only per P-4 §Work 3) passes and the MAPPING is
    what the test measures. Nothing is ever executed: `lab` traps every process
    seam, so a preflight that tries to run the binary fails this test loudly.
    """
    monkeypatch.setenv(CODEX_AUTH_ENV, "blind-lane-placeholder-not-a-key")
    made = lab.materialize(driver="openai", games=1, seed=99, tiers=TIERS[0])
    assert _get_dotted(made.config, "backends.default_driver") == "codex", (
        "§Work 2 driver mapping: openai -> codex in backends.default_driver, got "
        f"{_get_dotted(made.config, 'backends.default_driver')!r}"
    )
    assert _get_dotted(made.config, "backends.codex.auth_env") == CODEX_AUTH_ENV, (
        "the codex block must survive materialization untouched"
    )


def test_t2b_no_codex_auth_anywhere_fails_loudly_and_spawns_nothing(lab, monkeypatch):
    """T2: with no codex auth the preflight fails LOUDLY, before spend.

    Ambiguity E: P-4 lets the failure land either side of the config write, so
    the pins here are the parts that are NOT optional — the run fails, it says
    why in terms an operator can act on, and NOT ONE process starts (the
    booby trap from test_v2_codex is what proves the last part).
    """
    monkeypatch.delenv(CODEX_AUTH_ENV, raising=False)
    for name in list(os.environ):
        if "CODEX" in name.upper() or name.upper().startswith("OPENAI"):
            monkeypatch.delenv(name, raising=False)
    auth = Path(os.environ["HOME"]) / CODEX_AUTH_RELPATH
    assert not auth.exists(), f"the tmp HOME is not clean: {auth}"

    dry = lab.dry_flag()
    argv = lab.run_argv(driver="openai", games=1, tiers=TIERS[0], dry=dry)
    result = lab.invoke(argv)

    assert result.failed, (
        "§Work 3: a codex run with no auth anywhere must fail LOUDLY before any spend; this one "
        f"succeeded.\n{result}"
    )
    text = result.text.lower()
    assert "codex" in text or "openai" in text, (
        f"§Work 3: the failure must name the driver whose auth is missing.\n{result}"
    )
    assert any(word in text for word in ("auth", "login", "key", CODEX_AUTH_ENV.lower())), (
        "§Work 3: the failure must say it is an AUTH failure (the operator's next action is "
        f"`codex login` or exporting {CODEX_AUTH_ENV}).\n{result}"
    )
    assert not lab.calls, f"a batch entry was reached despite the failed preflight:\n{lab.call_report}"
    assert _shape(lab.games_dir) == {}, "a failed preflight promoted something to the shelf"
    # ambiguity E, REPORTED not asserted: which side of the write the failure lands on.
    written = sorted(path.parent.name for path in lab.batches_dir.glob("*/config.yaml"))
    assert written == [] or len(written) == 1, (
        f"a failing preflight wrote {len(written)} resolved configs: {written}"
    )


# =============================================================================
# T3 — id and seed allocation
# =============================================================================


def _require_aimed_command_surface(lab: _Lab) -> None:
    """Every argv-driven pin below needs the CLI to see the PLANTED ids, not the repo's."""
    seen = set(_cli().known_batch_ids())
    planted = {path.name for path in lab.batches_dir.iterdir() if path.is_dir()}
    planted |= {path.stem for path in lab.config_dir.glob("*.yaml")} - {"template"}
    if seen != planted:
        pytest.fail(
            f"{FINDING_UNAIMABLE}\n\n  OBSERVED HERE: the CLI's own `known_batch_ids()` answers "
            f"{sorted(seen)}; this test planted {sorted(planted)} under {lab.root}. "
            f"{lab.probe_report}"
        )


def _aimed(lab: _Lab, made: Materialized, what: str, expected, got) -> str:
    return (
        f"T3 {what}: expected {expected!r}, got {got!r} (via {made.via}). If the value looks like "
        f"it came from the REAL repo's config/ or out/batches, the CLI has no root seam this "
        f"file could aim — that is a LOUD FINDING, not a test bug. {lab.probe_report}"
    )


def test_t3a_the_next_id_is_the_first_free_n(lab):
    """§Work 2: "batch id auto `gYYYYMMDD-<n>` (n = first free among config/ + out/batches ids)"."""
    today = _today()
    lab.plant_config(f"g{today}-1", seed=3)
    lab.plant_batch(f"g{today}-3", seed=3)
    made = lab.materialize(driver="claude", games=1, seed=99, tiers=TIERS[0])
    expected = f"g{today}-2"
    assert made.batch_id == expected, (
        _aimed(lab, made, "first-free id", expected, made.batch_id)
        + " (AMBIGUITY: 'first free' is read here as the smallest free n — the gap. A "
        f"max-taken+1 implementation would answer g{today}-4 and must be adjudicated, not "
        "silently accepted.)"
    )


def test_t3b_the_allocated_id_never_collides(lab):
    """T3: "the next id increments and never collides" — the reading-independent half."""
    today = _today()
    planted = [f"g{today}-1", f"g{today}-2", f"g{today}-4"]
    lab.plant_config(planted[0], seed=2)
    lab.plant_config(planted[1], seed=2)
    lab.plant_batch(planted[2], seed=2)
    lab.plant_batch(f"g{today}-3-fog", seed=2)
    made = lab.materialize(driver="claude", games=1, seed=99, tiers=TIERS[0])
    taken_configs = {path.stem for path in lab.config_dir.glob("*.yaml")}
    taken_batches = {path.name for path in lab.batches_dir.iterdir() if path.is_dir()}
    assert made.batch_id not in taken_configs | taken_batches, (
        f"T3: the allocated id {made.batch_id!r} collides with an existing one. "
        f"config/: {sorted(taken_configs)}; out/batches/: {sorted(taken_batches)}"
    )
    match = ID_RE.match(made.batch_id)
    assert match, f"T3: {made.batch_id!r} is not `gYYYYMMDD-<n>[-word]`"
    prefix = f"g{match.group(1)}-{match.group(2)}"
    clashes = [
        name for name in taken_configs | taken_batches if name == prefix or name.startswith(prefix + "-")
    ]
    assert not clashes, (
        f"T3: the allocated id {made.batch_id!r} reuses the ordinal {prefix!r}, already held by "
        f"{clashes} (ambiguity C: whether a `--name`d id occupies its n is unspecified, so this "
        "pin is the intersection of both readings — an ordinal is never handed out twice)."
    )


def test_t3c_the_auto_seed_is_the_max_plus_one(lab):
    """§Work 2: "seed auto = max(batch.seed across config/*.yaml and out/batches/*/config.yaml) + 1"."""
    lab.plant_config("alpha", seed=41)
    lab.plant_config("beta", seed=12)
    lab.plant_batch("gamma", seed=17)
    lab.plant_batch("delta")  # no config.yaml: contributes nothing
    made = lab.materialize(driver="claude", games=1, tiers=TIERS[0])
    got = _get_dotted(made.config, "batch.seed")
    assert got == 42, _aimed(lab, made, "auto seed (max 41 across both scans, +1)", 42, got)


def test_t3d_an_explicit_seed_and_name_are_respected(lab):
    """§Work 2: "unless --seed"; "--name appends `-<word>`"."""
    lab.plant_config("alpha", seed=41)
    made = lab.materialize(driver="claude", games=1, seed=7, name="fog", tiers=TIERS[0])
    assert _get_dotted(made.config, "batch.seed") == 7, (
        "§Work 2: --seed overrides the max+1 auto seed; got "
        f"{_get_dotted(made.config, 'batch.seed')!r} with config/alpha.yaml at seed 41"
    )
    assert made.batch_id.endswith("-fog"), (
        f"§Work 2: --name appends `-<word>`; the id is {made.batch_id!r}"
    )
    match = ID_RE.match(made.batch_id)
    assert match and match.group(3) == "fog", (
        f"§Work 2 id shape with --name: `gYYYYMMDD-<n>-fog`; got {made.batch_id!r}"
    )


def test_t3e_a_colliding_explicit_id_refuses(lab):
    """T3: "a colliding explicit id refuses" (ambiguity D — probed, never assumed)."""
    options = lab.options("run")
    flag = next((candidate for candidate in ID_FLAGS if candidate in options), None)
    if flag is None:
        pytest.skip(
            "T3's 'a colliding explicit id refuses' names a surface §Work 1's flag list does not "
            f"contain: `run --help` offers {sorted(options)}, none of {list(ID_FLAGS)}. RECORDED "
            "AS A SKIP so the requirement is not lost (the P-1a H4 precedent); T3b pins the "
            "auto-allocator's never-collide half unconditionally. LEAD CALL: either the flag "
            "lands or T3's sentence is struck."
        )
    taken = f"g{_today()}-1"
    lab.plant_batch(taken, seed=2)
    _require_aimed_command_surface(lab)
    result = lab.invoke(
        lab.run_argv(
            driver="claude", games=1, tiers=TIERS[0], extra=(flag, taken), dry=lab.dry_flag()
        )
    )
    assert result.failed, f"T3: `{flag} {taken}` collides with a planted batch and must refuse.\n{result}"
    assert taken in result.text, f"T3: the refusal must name the colliding id {taken!r}.\n{result}"
    assert not lab.calls, f"a colliding id still reached a batch entry:\n{lab.call_report}"


# =============================================================================
# T4 — tier validation
# =============================================================================


def test_t4a_a_tier_count_mismatch_names_both_numbers(lab):
    """T4: "--tiers count != --games -> loud error naming both numbers"."""
    result = lab.invoke(lab.run_argv(driver="claude", games=2, tiers=",".join(TIERS), dry=lab.dry_flag()))
    assert result.failed, (
        f"§Work 2: --tiers "
        f"'must name exactly N tiers'; 3 tiers against --games 2 must refuse.\n{result}"
    )
    text = result.text
    assert "3" in text and "2" in text, (
        f"T4: the error must name BOTH numbers (3 tiers, 2 games).\n{result}"
    )
    lowered = text.lower()
    assert "tier" in lowered, f"T4: the error must say which flag is wrong.\n{result}"
    assert not lab.calls, f"a bad --tiers still reached a batch entry:\n{lab.call_report}"


def test_t4b_an_unknown_tier_name_raises_the_tiers_modules_own_error(lab):
    """T4: "bad tier name -> the tiers module's own error" (ambiguity F)."""
    result = lab.invoke(
        lab.run_argv(driver="claude", games=2, tiers=f"{TIERS[0]},{BAD_TIER}", dry=lab.dry_flag())
    )
    assert result.failed, f"T4: `{BAD_TIER}` is not a tier; the run must refuse.\n{result}"
    assert BAD_TIER in result.text, f"T4: the error must name the offending tier.\n{result}"
    from_tiers_module = "tiers.py" in result.text
    names_vocabulary = all(tier in result.text for tier in TIERS)
    assert from_tiers_module or names_vocabulary, (
        "T4: 'the tiers module's own error' — the failure neither passed through a `gen/tiers.py` "
        f"frame nor named the tier vocabulary {list(TIERS)}, so it reads as the CLI inventing its "
        f"own validation instead of delegating (ambiguity F).\n{result}"
    )
    assert not lab.calls, f"an unknown tier still reached a batch entry:\n{lab.call_report}"


# =============================================================================
# T5 — resume / status
# =============================================================================


@pytest.fixture
def persisted(lab) -> tuple[str, Path]:
    """A batch whose resolved config is already on disk (what §Work 2 guarantees)."""
    batch_id = f"g{_today()}-1"
    lab.plant_batch(batch_id, seed=5)
    lab.plant_batch(f"g{_today()}-2", seed=6)
    lab.record_orchestrator()
    return batch_id, lab.batches_dir / batch_id / "config.yaml"


def test_t5a_resume_invokes_the_orchestrator_on_the_persisted_config(lab, persisted):
    """T5: "resume invokes the orchestrator on the PERSISTED config path"."""
    batch_id, config_path = persisted
    _require_aimed_command_surface(lab)
    result = lab.invoke(["resume", batch_id])
    assert lab.calls, (
        "T5: `resume` reached no orchestrator entry. Recorded surfaces: "
        f"{list(ORCH_ENTRIES)} on gen.orchestrator and gen.cli, plus subprocess.run/Popen "
        f"(ambiguity G).\n{result}"
    )
    assert lab.mentions(str(config_path)), (
        f"T5: `resume {batch_id}` must invoke the orchestrator on the PERSISTED config "
        f"{config_path} — 'resume and reproducibility come free' (§Work 2). What was invoked:\n"
        f"{lab.call_report}\n{result}"
    )
    assert not result.failed, f"T5: `resume {batch_id}` failed on a valid batch.\n{result}"


def test_t5b_status_passes_through_to_the_orchestrator(lab, persisted):
    """T5: "status passthrough" — §Evidence: the orchestrator's CLI is `--config X --status`."""
    batch_id, config_path = persisted
    _require_aimed_command_surface(lab)
    result = lab.invoke(["status", batch_id])
    assert lab.calls, f"T5: `status` reached no orchestrator entry.\n{result}"
    assert lab.mentions(str(config_path)), (
        f"T5: `status {batch_id}` must reach the orchestrator on {config_path}.\n"
        f"{lab.call_report}\n{result}"
    )
    blob = repr(lab.calls) + result.text
    assert "status" in blob.lower(), (
        "T5: the status passthrough must carry the status request (the orchestrator's own CLI "
        f"spells it `--status`).\n{lab.call_report}\n{result}"
    )


@pytest.mark.parametrize("subcommand", ["resume", "status"])
def test_t5c_an_unknown_batch_id_is_loud_and_lists_the_known_ids(lab, persisted, subcommand):
    """T5: "unknown batch id -> loud, lists known ids"."""
    _require_aimed_command_surface(lab)
    known = sorted(path.name for path in lab.batches_dir.iterdir() if path.is_dir())
    result = lab.invoke([subcommand, "no-such-batch-42"])
    assert result.failed, f"T5: `{subcommand} no-such-batch-42` must refuse loudly.\n{result}"
    assert "no-such-batch-42" in result.text, (
        f"T5: the refusal must name the id that was asked for.\n{result}"
    )
    missing = [batch_id for batch_id in known if batch_id not in result.text]
    assert not missing, (
        f"T5: an unknown batch id must LIST the known ids; {missing} are missing from the message "
        f"(known on disk: {known}).\n{result}"
    )
    assert not lab.calls, f"an unknown batch id still reached the orchestrator:\n{lab.call_report}"


# =============================================================================
# T6 — template immutability + no existing behavior changed
# =============================================================================


def test_t6a_no_cli_call_touches_the_template(lab):
    """T6: "template bytes unchanged by any CLI call"."""
    repo_before = _sha(TEMPLATE_PATH)
    tmp_before = _sha(lab.template)
    lab.plant_config("alpha", seed=41)
    lab.plant_batch(f"g{_today()}-1", seed=41)
    dry = lab.dry_flag()
    for argv in (
        ["--help"],
        ["run", "--help"],
        lab.run_argv(driver="claude", games=2, seed=99, tiers="t1,t2", dry=dry),
        lab.run_argv(driver="claude", games=1, tiers=TIERS[0], name="fog", dry=dry),
        lab.run_argv(driver="claude", games=2, tiers=",".join(TIERS), dry=dry),
        lab.run_argv(driver="claude", games=1, workers=2, tiers=TIERS[0], dry=dry),
        ["status", f"g{_today()}-1"],
        ["resume", "no-such-batch"],
    ):
        lab.invoke(argv)
    assert _sha(lab.template) == tmp_before, (
        f"§Work 2: 'The template file itself is NEVER modified'; {lab.template} changed"
    )
    assert _sha(TEMPLATE_PATH) == repo_before, (
        f"§Hard rules: template.yaml is read-only to the CLI; {TEMPLATE_PATH} changed"
    )
    assert yaml.safe_load(lab.template.read_text(encoding="utf-8")) == TEMPLATE


def test_t6b_importing_gen_cli_moves_no_orchestrator_or_config_constant(lab):
    """T6: "importing gen.cli changes no orchestrator/config constants (snapshot-compare)".

    The two snapshots straddle this module's `import gen.cli` (module scope,
    above), so the delta is attributable to that import and to nothing else.
    """
    _cli()
    pairs = []
    if not _CLI_PREIMPORTED:
        # this file got there first: the straddling snapshots are the measurement.
        pairs.append(("this file's own `import gen.cli`", _CONSTANTS_BEFORE_CLI, _CONSTANTS_AFTER_CLI))
    # ...and an order-independent measurement either way: re-execute gen/cli.py in
    # isolation and compare across it. (Another test module imports gen.cli before
    # this one in a full-suite run, so the straddling pair alone is not reliable.)
    before = _snapshot()
    original = sys.modules.get("gen.cli")
    package = sys.modules.get("gen")
    try:
        sys.modules.pop("gen.cli", None)
        importlib.import_module("gen.cli")
        after = _snapshot()
    finally:
        if original is not None:
            sys.modules["gen.cli"] = original
            if package is not None:
                package.cli = original
    pairs.append(("a fresh `import gen.cli`", before, after))

    drift = {
        f"{module} across {what}": _diff(first[module], second[module])
        for what, first, second in pairs
        for module in _SNAPSHOT_MODULES
        if _diff(first[module], second[module])
    }
    assert not drift, (
        "§Work 8: 'NO behavioral change to any existing module: cli.py composes'. Importing "
        "gen.cli moved these public module-level constants:\n"
        + "\n".join(f"{module}:\n{_show(changes)}" for module, changes in drift.items())
    )


def test_t6c_the_cli_is_a_composer_not_a_batch_runner(lab):
    """T6/§Work 8: the materialization path enters no existing batch entry at all."""
    _t1(lab)
    assert not lab.calls, (
        "§Work 8: materializing a config must not enter the orchestrator; it did:\n"
        f"{lab.call_report}"
    )


# =============================================================================
# T7 — the workers guard
# =============================================================================


def test_t7a_workers_two_is_accepted_and_forwarded(lab):
    """T7, REWRITTEN FOR P-5 — one of that contract's three licensed edits.

    P-4 §Work 1 wrote the flag as "accepted, FORWARDED WHEN P-5 LANDS; until
    then >1 = loud 'not yet supported'". P-5 has landed, so the refusal this
    test used to pin is gone by design and the other half of the same sentence
    is what it pins now: `--workers 2` resolves into the config, as BOTH keys —
    `orchestrator.parallel_slots: true` (the arming, because the count alone has
    sat unread in every config since b001) and `orchestrator.workers: 2`.
    """
    result, config, _ = lab.dry(driver="claude", games=2, seed=99, tiers="t1,t2", workers=2)
    assert not result.failed, (
        f"P-5 §Work 9: `--workers 2` is accepted and forwarded, not refused.\n{result}"
    )
    assert "not yet supported" not in result.text.lower(), (
        f"P-5 §Work 9: the P-4 placeholder refusal must be gone.\n{result}"
    )
    assert not lab.calls, f"--workers 2 on a no-spend run reached a batch entry:\n{lab.call_report}"
    if config is None:
        pytest.skip(
            "ambiguity A: the dry run does not surface the resolved config as data, so the "
            "forwarding cannot be measured here. The acceptance half (exit 0, no refusal, "
            "no spend) is pinned above."
        )
    assert _get_dotted(config, "orchestrator.parallel_slots") is True, (
        "P-5 §Work 9: `--workers N>1` must write `orchestrator.parallel_slots: true` — the "
        "arming, without which an old config's decorative `workers` would flip a resume to "
        f"parallel. Resolved orchestrator block: {config.get('orchestrator')!r}"
    )
    assert _get_dotted(config, "orchestrator.workers") == 2, (
        "P-5 §Work 9: `--workers N` must write `orchestrator.workers: N` beside the arming. "
        f"Resolved orchestrator block: {config.get('orchestrator')!r}"
    )


def test_t7b_workers_one_is_accepted(lab):
    """T7: "--workers 1 accepted" — and resolves exactly as without the flag.

    Unchanged by P-5 in substance (the second of that contract's three licensed
    edits is this message): `--workers 1` has nothing to arm, so its resolved
    config must stay byte-identical to the no-flag one. P-5's house rule is that
    an unarmed run behaves exactly as today, and this is that rule at the flag
    layer.
    """
    result, config, _ = lab.dry(driver="claude", games=2, seed=99, tiers="t1,t2", workers=1)
    assert not result.failed, f"T7: `--workers 1` is accepted (§Work 1), not refused.\n{result}"
    lowered = result.text.lower()
    assert "not yet supported" not in lowered, (
        f"T7: `--workers 1` must NOT draw the P-5 refusal.\n{result}"
    )
    assert not lab.calls, f"--workers 1 on a no-spend run reached a batch entry:\n{lab.call_report}"
    if config is None:
        pytest.skip(
            "ambiguity A: the dry run does not surface the resolved config as data, so the "
            "`--workers 1 == no --workers` equality cannot be measured here. The acceptance half "
            "(exit 0, no P-5 refusal, no spend) is pinned above."
        )
    drift = _diff(_expected(_get_dotted(config, "batch.id")), config)
    assert not drift, (
        "T7: `--workers 1` is accepted and must resolve to the same config as no --workers at "
        f"all — one worker has nothing to parallelise, so P-5 writes nothing:\n{_show(drift)}"
    )
