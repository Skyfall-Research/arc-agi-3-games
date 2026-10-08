"""Blind pins for contract D-3 — config/report honesty.

Run: .venv/bin/python -m pytest gen/tests/test_d3_honesty.py -v

Written from the frozen D-3 contract ALONE (blind test writer).  No in-progress
D-3 diff of `gen/orchestrator.py`, `gen/s1_spec.py`, `gen/s5_battery.py` or
either touched config was read: every surface this file names was read at
`git show HEAD:` (the implementer began editing the working tree while this
file was being written, which is exactly why HEAD is the only source used).
What this file is allowed to know, and does: those modules' PRE-D-3 surfaces
(`VERIFIER_REJECT_CAP_ESCALATE`, `ESCALATE_REASON`, `ESCALATE_PREFIX`,
`_respec_cap` as the precedent for an optional int reader, `_int_key`,
`STAGES`, `STAGE_SUCCESS`, `TRANSITIONS`, `BIRTH`, `slot_id`, `batch_dir`,
`LEDGER_NAME`, `append_transition`, `replay_ledger`, `run_batch`, `main`,
`s1_spec.run_s1`, `s5_battery.run_battery`, `s4_baselines.run_s4`), the sibling
blind suites `test_b003_corrwindow.py` and `test_b003_confirm.py` (whose
discover-the-name-then-pin-the-behavior style this file keeps), the fake-runner
and `batch_home` harness of `test_b11_pipeline.py`, the `run_s1` writer-injection
harness of `test_b5_spec.py`, the `run_s4` + injected-chat harness of
`test_b9_battery.py`, the checked-in fixtures, and the SHIPPED ledgers under
`out/batches/` (read-only).  These pins therefore describe the CONTRACT, not the
implementation, and are expected to fail until D-3 lands.

WHAT D-3 IS ABOUT (the readiness audit's honesty findings, from the contract)

A config key everyone believed was live (`verifier.reject_cap`, written as 2 by
every live config and read by nothing), two knobs that are stamped into reports
but steer nothing (`lint.strict`, `battery.smoke`), a respec counter that is 0
in every shipped report because it lives in memory and memory dies on resume, a
human PULL counted as attrition so a reviewed-and-pulled batch replays as
"BATCH ABORTED", and usd totals that silently cover 3 of 8 stages.

THE FIVE PINS, in the contract's order

1. `reject_cap`: the reader defaults to 2, honors a configured 5, and errors on
   0/-1/bool/"2"; the escalation threshold follows the configured value, driven
   through the §4 machine with fake runners and asserted by reason-prefix
   counting (`ESCALATE_PREFIX`), never a driver.
2. strict/smoke gone: `_lint_strict` absent from `gen.s1_spec`; a freshly
   written `lint-report.json` carries no `strict`; `s5_battery`'s config parser
   accepts a `battery:` block WITHOUT `smoke` and rejects nothing about it; a
   fresh battery report carries no `smoke`; neither touched config file carries
   the removed keys.
3. `respec_runs` from the ledger: a synthetic ledger with 2 escalation respecs +
   1 lint resample, replayed with FRESH in-memory state, reports 3; the shipped
   b002-triple ledger reports 3/3/3 and b003r2 reports 0/0 with 1 pulled.
4. Attrition is DEAD-only: 1 dead of 2 at max 0.30 aborts, 1 pulled of 2 does
   not and says "review complete"; the shipped b003r2 replay is pinned.
5. `cost_note`: one shared constant, in the report AND the `--status` footer,
   naming the three priced stages.

AMBIGUITIES RESOLVED (each is quoted in the failure message that depends on it)

  a. THE READER'S NAME.  Contract §1 says "new reader in gen/orchestrator.py
     beside the other config validators" and never names it.  `_reject_cap` is
     the direct analogue of the `_respec_cap` beside it (same shape: optional
     key, module-constant default, `_int_key` validation), so this file tries
     that spelling first and then DISCOVERS any callable whose name carries both
     "reject" and "cap" — the pins are on behavior, never on the name.  The
     config key is NOT open: `verifier.reject_cap`, spelled by the contract.
  b. THE ERROR TYPE for a bad `reject_cap`.  The contract says only "int >= 1"
     and "fail-loud".  `_int_key` — the house validator the sibling `_respec_cap`
     routes through — raises ValueError, while `orchestrator_config` raises
     TypeError for a wrong type.  This file accepts EITHER and pins the part the
     contract does fix: the message names the key, so a bad batch config is
     fixable from the failure alone.
  c. A MISSING `verifier:` BLOCK.  §1 gives the key a default but says nothing
     about the block.  Read the `_respec_cap` way (its docstring: "a cfg with no
     `orchestrator:` at all simply takes the default here rather than raising
     twice over"), i.e. default, not raise.  Pinned in its own test
     (`test_pin1_absent_verifier_block_takes_the_default`) so an adjudication the
     other way moves one line.
  d. WHICH EDGE IS "the lint-kill resample edge".  §4 says to count "the
     verifier-escalation edges (ESCALATE_REASON-prefixed) and the lint-kill
     resample edges", and a lint kill is a PAIR of §4 edges
     (`ideated --> respec` then `respec --> ideated`).  Counting both would make
     the contract's own synthetic case ("2 escalation respecs + 1 lint
     resample") come to 4, not 3, so the reading is: one COMPLETE lint-kill
     cycle counts exactly ONCE.  Which of the two edges carries the count is
     left unpinned on purpose — every synthetic ledger here plants complete
     cycles, where both readings agree.  A slot parked AT `respec` (killed, not
     yet re-sampled) is a RECORDED GAP: this file asserts nothing about it.
  e. WHERE `cost_note` SITS in the report.  §6 names the field and says "One
     constant, both consumers", not where it hangs.  So this file searches the
     whole report recursively for that key and pins its VALUE against the shared
     constant (never retyped prose), exactly as the C-2 suite does for
     `lever_window` — position is not pinned.
  f. THE CONSTANT'S NAME.  `COST_NOTE` is tried first, then any module-level
     string whose name carries "cost" and "note", then any upper-case string
     constant that names all three priced stages.  Behavior, not name.
  g. "review complete" WORDING.  §5 writes it two ways ("stopped (review
     complete)" and "prints review-complete"), so both spellings are accepted
     via whitespace/hyphen normalization.  The SURFACE is not open: the
     contract's own replay proof is `--status`, so that is where this file looks.
     Normalizing the whole output has one trap, and it is guarded rather than
     reasoned about: `--status` prints the BATCH ID in its header, so a synthetic
     batch called `d3-review-complete` folds to "d3 review complete" and passes
     the wording pin against any code at all (an earlier draft of this file did
     exactly that against pre-D-3 `gen/orchestrator.py`).  Every id a wording pin
     uses is now inert by construction, and
     `test_pin4_wording_batch_ids_cannot_fake_a_match` keeps it that way.
  h. `respec_runs` IN THE `--status` TABLE.  The contract's verification reads
     respec counts off `--status`, but fixes no column spelling for a table
     whose counter group is currently `lint/resamp/verif/crash/dead`.  The
     NUMBERS are therefore pinned on the batch report's `respec_runs` — the one
     field name §4 spells — and `--status` is pinned only for reporting respecs
     AT ALL (the string "respec" appears, which today's table does not contain).
  i. "1 dead of 2 ⇒ abort" SURFACE.  Pinned on the report's
     `attrition.abort` / `attrition.fraction`, which are unambiguous, plus the
     dead-only arithmetic (`fraction == dead / slots`) that IS change 5.  The
     `--status` side is pinned as the wording discriminator (a 1-dead ledger
     must not claim review-complete), not as an abort banner whose text §5 does
     not fix.
  j. A STRAY REMOVED KEY.  §2/§3 delete `lint.strict` and `battery.smoke` from
     the two TOUCHED configs, but `config/b001-pilot.yaml` and
     `config/b002-triple.yaml` are frozen and still carry both — so "no longer
     required, no longer stamped" has to mean a config that still declares them
     loads, runs, and stamps nothing.  Pinned, and it is the only reading under
     which the frozen batch identities keep working.
  k. THE FROZEN CONFIGS.  `test_pin2_the_frozen_configs_are_not_touched` pins
     the contract's own prohibition ("Do NOT touch … frozen, sha-recorded batch
     identities") by asserting b001/b002 still declare both keys.  If that
     prohibition is ever lifted, this single test moves.
  l. HOW THE REPORT IS BUILT FROM A LEDGER.  "simulate resume (fresh in-memory
     state, report built from the ledger)" is driven through the only public
     builder, `run_batch`, with fake runners and a planted ledger whose slots
     are already terminal — so nothing is invoked to advance a slot and every
     number in the report comes off the replay.  `_restage`'s §2 staleness walk
     does re-invoke recorded stages (the planted corpus artifacts are not in
     tmp); the fakes answer green, which appends no ledger line and cannot
     change a terminal state.
  m. THE REAL LEDGERS.  Read-only, and replayed against a COPY under `tmp_path`
     so the repo's `out/batches/` is never written to (an autouse guard proves
     it).  `--status` is pointed at the real batch dir because it provably
     writes nothing.  Absent ledgers skip LOUDLY.
  n. The real batches are never driven through `main()` without `--status`: a
     resume run would call `default_runners()` and spend money.

This file writes only inside `tmp_path`.  The canon, `out/`, the configs and
every other source file are read-only here.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import socket
import urllib.request
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

from gen import backends, s1_spec, s5_battery
from gen import orchestrator as orch
from gen.backends import ChatResult
from gen.config import REPO_ROOT, load_config
from gen.s1_spec import run_s1
from gen.s4_baselines import run_s4
from gen.s5_battery import run_battery

# --------------------------------------------------------------------------
# the contract's own vocabulary
# --------------------------------------------------------------------------

TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"
SPEC_FIXTURES = TESTS_DIR / "fixtures" / "specs"
IDEA_PATH = SPEC_FIXTURES / "idea-001.json"
GOOD_SPEC = SPEC_FIXTURES / "good-spec.yaml"

#: the two configs D-3 may touch — and the two it may not.
TOUCHED_CONFIGS = ("config/b003-simplicity.yaml", "config/b003r2-simplicity.yaml")
FROZEN_CONFIGS = ("config/b001-pilot.yaml", "config/b002-triple.yaml")
BASE_CONFIG = "config/b003r2-simplicity.yaml"

#: contract spellings, never code names.
REJECT_CAP_KEY = "reject_cap"
VERIFIER_BLOCK = "verifier"
LINT_BLOCK, STRICT_KEY = "lint", "strict"
BATTERY_BLOCK, SMOKE_KEY = "battery", "smoke"
RESPEC_RUNS_FIELD = "respec_runs"
COST_NOTE_FIELD = "cost_note"

#: §5's verdict wording, normalized (ambiguity g); `ABORT` is its opposite.
REVIEW_COMPLETE = "review complete"
ABORT = "abort"

#: batch ids for the two wording pins.  They must not CONTAIN the phrases those
#: pins search for: `--status` prints the batch id in its header, and `_normal`
#: folds hyphens to spaces, so an id like `d3-review-complete` would satisfy the
#: assertion by itself.  `_wording_batch_ids_cannot_fake_a_match` holds the rule.
PULL_WORDING_BATCH = "d3-wording-pull"
DEAD_WORDING_BATCH = "d3-wording-dead"

#: §6: "usd totals cover s2_implement + s3_verify + s5_battery only".
PRICED_STAGES = ("s2_implement", "s3_verify", "s5_battery")
#: the stages §6 calls unpriced — used only to check the note SAYS so.
UNPRICED_MARKERS = ("s0", "s1", "s4", "s6", "gate")

#: the S4 seed `test_b9_battery` proves `toy_worker` is `fit` at.
S4_SEED = 7

#: the shipped ledgers pins 3/4 read: batch id -> (slots, respec per slot,
#: dead, pulled).  Every number here was counted off the ledger's own §4 edges
#: (escalation edges by `ESCALATE_PREFIX`, lint cycles by `ideated --> respec`),
#: which is also what the contract states: "b002: 3/3/3; b003r2: 0/0".
REAL_BATCHES = {
    "b002-triple": {"config": "config/b002-triple.yaml", "respecs": (3, 3, 3),
                    "dead": 0, "pulled": 0},
    "b003r2-simplicity": {"config": "config/b003r2-simplicity.yaml", "respecs": (0, 0),
                          "dead": 0, "pulled": 1},
}

_ABSENT = object()

# Read BEFORE any fixture repoints a root: `load_config` resolves a relative
# config path against `gen.config.REPO_ROOT`.
_BASE_CFG = load_config(BASE_CONFIG)


# --------------------------------------------------------------------------
# the surfaces under test, fetched rather than assumed
# --------------------------------------------------------------------------


def _reject_cap_reader():
    """The `verifier.reject_cap` reader (ambiguity a): name discovered, not guessed."""
    for name in ("_reject_cap", "_verifier_reject_cap", "reject_cap", "verifier_reject_cap"):
        candidate = getattr(orch, name, None)
        if callable(candidate):
            return candidate
    found = [
        value
        for name, value in vars(orch).items()
        if callable(value) and "reject" in name.lower() and "cap" in name.lower()
    ]
    assert len(found) == 1, (
        "gen.orchestrator exposes no reader for `verifier.reject_cap`. D-3 §1: a new reader "
        "beside the other config validators (`_reject_cap`, the shape `_respec_cap` already "
        f"uses) — int >= 1, default VERIFIER_REJECT_CAP_ESCALATE. Candidates found: {len(found)}"
    )
    return found[0]


def _reject_cap(cfg: Mapping):
    return _reject_cap_reader()(cfg)


def _cost_note() -> str:
    """The ONE shared cost-label constant (ambiguities e/f)."""
    direct = getattr(orch, "COST_NOTE", None)
    if isinstance(direct, str) and direct.strip():
        return direct
    named = [
        value
        for name, value in vars(orch).items()
        if isinstance(value, str) and "cost" in name.lower() and "note" in name.lower()
    ]
    if len(named) == 1:
        return named[0]
    by_content = [
        value
        for name, value in vars(orch).items()
        if name.isupper()
        and isinstance(value, str)
        and all(stage in value for stage in PRICED_STAGES)
    ]
    assert len(by_content) == 1, (
        "gen.orchestrator has no shared cost-label constant. D-3 §6: the batch report and the "
        "`--status` footer gain a FIXED `cost_note` string constant (`COST_NOTE`) saying the usd "
        f"totals cover {' + '.join(PRICED_STAGES)} only — ONE constant, both consumers. Found "
        f"{len(named)} name matches and {len(by_content)} content matches"
    )
    return by_content[0]


def _battery_config_parser():
    """`s5_battery`'s `battery:` block parser (§3 names the block, not the function)."""
    for name in ("_battery_config", "battery_config", "parse_battery_config"):
        candidate = getattr(s5_battery, name, None)
        if callable(candidate):
            return candidate
    found = [
        value
        for name, value in vars(s5_battery).items()
        if callable(value) and "battery" in name.lower() and "config" in name.lower()
    ]
    assert len(found) == 1, (
        "gen.s5_battery exposes no `battery:` block parser to ask about `smoke` "
        f"(`_battery_config`); candidates found: {len(found)}"
    )
    return found[0]


# --------------------------------------------------------------------------
# config helpers
# --------------------------------------------------------------------------


def _cfg(*, block: str = VERIFIER_BLOCK, key: str, value: object = _ABSENT,
         base: Mapping | None = None) -> dict:
    """A deep copy of `base` with one config key forced or removed."""
    cfg = copy.deepcopy(dict(_BASE_CFG if base is None else base))
    inner = dict(cfg.get(block) or {})
    inner.pop(key, None)
    if value is not _ABSENT:
        inner[key] = value
    cfg[block] = inner
    return cfg


def _bare(value: object = _ABSENT) -> dict:
    """The reader needs only the `verifier:` block, as `_respec_cap` needs only one."""
    cfg: dict = {VERIFIER_BLOCK: {}}
    if value is not _ABSENT:
        cfg[VERIFIER_BLOCK][REJECT_CAP_KEY] = value
    return cfg


def _raises_config_error(call, where: str) -> None:
    """A bad config value fails loud, naming the key (ambiguity b)."""
    with pytest.raises((ValueError, TypeError)) as caught:
        call()
    assert REJECT_CAP_KEY in str(caught.value), (
        f"{where} raised {type(caught.value).__name__} without naming the key: "
        f"{str(caught.value)!r}. D-3 §1 wants it fail-loud before spend, and the house "
        f"precedent (`_int_key`, `_respec_cap`) names `{VERIFIER_BLOCK}.{REJECT_CAP_KEY}` so a "
        "bad batch config is fixable from the failure alone"
    )


def _config_yaml(relative: str) -> dict:
    """A config file's raw yaml — no `load_config`, so nothing is resolved or added."""
    return yaml.safe_load((REPO_ROOT / relative).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# synthetic ledgers (planted with the real appender, so §4 validates them)
# --------------------------------------------------------------------------

_HASHES = {"spec": None, "game": None, "stage_input": "d3-synthetic-stage-input"}

#: `n` is the module's own cap, so the planted escalation reads exactly like the
#: shipped ones — the prefix, not retyped prose, is what a replay recognizes.
_ESCALATED_REASON = (
    f"{orch.ESCALATE_REASON.format(n=orch.VERIFIER_REJECT_CAP_ESCALATE)}: "
    "verifier reject: synthetic finding"
)

#: name -> (from, to, reason).  Every one is an edge `TRANSITIONS` draws.
EDGES: dict[str, tuple[str | None, str, str]] = {
    "birth": (orch.BIRTH, "ideated", "[*] --> ideated (synthetic)"),
    "lint_kill": ("ideated", "respec", "lint kill: synthetic"),
    "resample": ("respec", "ideated", "re-sample (synthetic)"),
    "lint_pass": ("ideated", "spec_ok", "lint pass (synthetic)"),
    "implement": ("spec_ok", "implemented", "validate green (synthetic)"),
    "reject": ("implemented", "spec_ok", "verifier reject: synthetic finding"),
    "escalate": ("implemented", "spec_ok", _ESCALATED_REASON),
    "verify": ("implemented", "verified", "S2b clean (synthetic)"),
    "gate": ("verified", "gated", "structural + robustness green (synthetic)"),
    "baseline": ("gated", "baselined", "g-sampler + cap-fit (synthetic)"),
    "battery": ("baselined", "played", "battery done (synthetic)"),
    "review": ("played", "reviewed", "human accept"),
    "package": ("reviewed", "packaged", "packaged (synthetic)"),
    "pull": ("reviewed", "pulled", "human pull (architecture §4: reviewed --> pulled)"),
    "green_death": ("spec_ok", "dead", f"green-attempts cap ×{orch.GREEN_CAP_DEATHS}: synthetic"),
}

#: one lint kill AND its re-sample — the complete cycle ambiguity (d) is read on.
LINT_CYCLE = ("lint_kill", "resample")
#: one escalated respec: the reject that escalates, then the re-implement.
ESCALATION = ("escalate", "implement")
SPINE = ("lint_pass", "implement")
TO_PLAYED = ("verify", "gate", "baseline", "battery")
PACKAGED = (*TO_PLAYED, "review", "package")
PULLED = (*TO_PLAYED, "review", "pull")

#: the two full walks pin 4 contrasts: a slot the green cap killed, and a slot a
#: human reviewed and pulled.  `green_death` departs from `spec_ok`, so the dead
#: walk never implements.
WALK_DEAD = ("birth", "lint_pass", "green_death")
WALK_PACKAGED = ("birth", *SPINE, *PACKAGED)
WALK_PULLED = ("birth", *SPINE, *PULLED)


def _replays(steps) -> bool:
    """Is this walk one the §4 machine could have produced, in order?"""
    state = orch.BIRTH
    for step in steps:
        from_state, to_state, _reason = EDGES[step]
        if from_state != state or not orch.legal_transition(from_state, to_state):
            return False
        state = to_state
    return True


def _plant(ledger_path: Path, slug: str, steps) -> list[dict]:
    """Append a §4-legal walk for one slug through the REAL appender.

    `append_transition` validates each EDGE but not the walk, and a ledger that
    does not replay raises inside `replay_ledger` — three stages from the pin
    that planted it.  So the order is checked here, where it is fixable.
    """
    assert _replays(steps), (
        f"fixture wall: the walk {tuple(steps)} is not a §4 sequence — "
        f"{[(EDGES[s][0], EDGES[s][1]) for s in steps]}"
    )
    lines = []
    for step in steps:
        from_state, to_state, reason = EDGES[step]
        lines.append(orch.append_transition(
            ledger_path, slug=slug, from_state=from_state, to_state=to_state,
            reason=reason, hashes=_HASHES, cost=None,
        ))
    return lines


def _fake_runners() -> dict:
    """A runner per §4 stage that lands its success state, spends nothing and
    writes nothing.  Terminal slots invoke none of them; `_restage`'s staleness
    walk may (ambiguity l), and a green answer there appends no ledger line."""

    def make(stage: str):
        def runner(ctx):
            return {"ok": True, "to_state": orch.STAGE_SUCCESS[stage],
                    "reason": f"fake {stage}: green", "cost": None, "artifacts": {}}
        return runner

    return {stage: make(stage) for stage in orch.STAGES}


def _forbidden_runners(calls: list):
    """Runners that record and then FAIL: nothing may be invoked before a bad
    config is rejected (§1 "fail-loud before spend")."""

    def make(stage: str):
        def runner(ctx):
            calls.append(stage)
            raise AssertionError(f"stage {stage!r} was invoked despite an invalid config")
        return runner

    return {stage: make(stage) for stage in orch.STAGES}


# --------------------------------------------------------------------------
# report / status readers
# --------------------------------------------------------------------------


def _find_key(node: object, key: str, path: str = "report") -> list[tuple[str, object]]:
    """Every `key` the payload carries, wherever it sits (ambiguity e)."""
    found: list[tuple[str, object]] = []
    if isinstance(node, Mapping):
        for name, value in node.items():
            spot = f"{path}.{name}"
            if str(name) == key:
                found.append((spot, value))
            found.extend(_find_key(value, key, spot))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_find_key(item, key, f"{path}[{index}]"))
    return found


def _slot_row(report: Mapping, slug: str) -> Mapping:
    rows = [row for row in report["slots"] if row["slug"] == slug]
    assert len(rows) == 1, f"the report has {len(rows)} rows for {slug!r}"
    return rows[0]


def _respec_runs(report: Mapping, slug: str) -> int:
    """The per-slot respec count out of the batch report (ambiguity h)."""
    row = _slot_row(report, slug)
    found = _find_key(row, RESPEC_RUNS_FIELD, f"slots[{slug}]")
    assert found, (
        f"the report row for {slug} carries no {RESPEC_RUNS_FIELD!r} (keys: {sorted(row)}). "
        "D-3 §4: the per-slot row's respec count is DERIVED from the ledger's edges"
    )
    values = {value for _spot, value in found}
    assert len(values) == 1, f"{slug}: the row reports conflicting respec counts {values}"
    value = found[0][1]
    assert isinstance(value, int) and not isinstance(value, bool), (
        f"{slug}: {RESPEC_RUNS_FIELD} is {value!r}; it is a count"
    )
    return value


_PREFIX_RE = re.compile(r"^[^\S\n]*\[[^\]\n]*\][^\S\n]*", re.MULTILINE)


def _flat(text: str) -> str:
    """Status output with its `[b11] ` line prefixes and line breaks flattened,
    so a footer the printer wrapped still reads as one string."""
    return " ".join(_PREFIX_RE.sub(" ", text).split())


def _normal(text: str) -> str:
    """Lower-cased, hyphens folded to spaces (ambiguity g)."""
    return re.sub(r"[\s\-_]+", " ", text.lower()).strip()


def _status(cfg_path: Path, capsys) -> str:
    """`--status` output.  Read-only: it replays the ledger and runs nothing."""
    try:
        code = orch.main(["--config", str(cfg_path), "--status"])
    except SystemExit as exc:   # pragma: no cover - the CLI returns a code
        code = exc.code
    captured = capsys.readouterr()
    assert (0 if code is None else int(code)) == 0, (
        f"`--status` exited {code} for {cfg_path}: {captured.err.strip()}"
    )
    return captured.out


def _slug_line(status_out: str, slug: str) -> str:
    lines = [line for line in status_out.splitlines() if slug in line]
    assert lines, f"`--status` printed no line for {slug}:\n{status_out}"
    return " ".join(lines)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_network_no_driver(monkeypatch):
    """Nothing here dials out or starts an agent session (the B9/B11 rule)."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("a D-3 test opened a network connection or started a session")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.setattr(backends, "get_driver", _forbidden)


@pytest.fixture(autouse=True)
def _repo_batches_untouched():
    """A D-3 test that wrote into the repo's own batch root fails here."""
    root = REPO_ROOT / "out" / "batches"

    def snapshot():
        if not root.exists():
            return None
        return sorted((str(path), path.stat().st_size) for path in root.rglob("*"))

    before = snapshot()
    yield
    assert snapshot() == before, (
        f"a D-3 test wrote into the repo batch root {root} — the shipped ledgers are read-only "
        "evidence and every write in this file belongs in tmp_path"
    )


@pytest.fixture
def batch_home(tmp_path, monkeypatch) -> Path:
    """Point every repo-rooted path in the orchestrator at `tmp_path`."""
    for name, value in list(vars(orch).items()):
        if name.startswith("__") or not isinstance(value, Path):
            continue
        try:
            relative = value.resolve().relative_to(REPO_ROOT)
        except ValueError:
            continue
        monkeypatch.setattr(orch, name, tmp_path / relative)
    return tmp_path


@pytest.fixture
def make_cfg(batch_home, tmp_path):
    """(cfg, config path) for a batch id nobody else uses, rooted in tmp."""

    def _make(batch_id: str, *, size: int = 1, overrides: Mapping | None = None) -> tuple:
        cfg = copy.deepcopy(dict(_BASE_CFG))
        cfg["batch"] = {**cfg["batch"], "id": batch_id, "size": size}
        for block, values in (overrides or {}).items():
            cfg[block] = {**dict(cfg.get(block) or {}), **dict(values)}
        path = tmp_path / f"{batch_id}.yaml"
        path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        return cfg, path

    return _make


@pytest.fixture
def planted(make_cfg):
    """A batch whose ledger is planted from EDGE walks and then replayed with a
    fresh in-memory state — the resume the shipped reports never survived."""

    def _build(batch_id: str, walks) -> tuple[dict, Path, list[str]]:
        cfg, path = make_cfg(batch_id, size=len(walks))
        ledger = orch.batch_dir(cfg) / orch.LEDGER_NAME
        slugs = []
        for index, steps in enumerate(walks, 1):
            slug = orch.slot_id(batch_id, index)
            slugs.append(slug)
            _plant(ledger, slug, steps)
        return cfg, path, slugs

    return _build


@pytest.fixture
def real_replay(batch_home, tmp_path):
    """A shipped ledger, COPIED into tmp and replayed through `run_batch`.

    The copy is what keeps `out/batches/` read-only (ambiguity m); the replay is
    the contract's "report built from the ledger".
    """

    def _replay(batch_id: str) -> dict:
        source = REPO_ROOT / "out" / "batches" / batch_id / orch.LEDGER_NAME
        if not source.is_file():
            pytest.skip(
                f"SKIPPED LOUDLY: the shipped ledger {source} is absent, so D-3's replay proof "
                f"for {batch_id} cannot run here (contract test-pin 3: 'skip loudly if absent')"
            )
        cfg = load_config(REAL_BATCHES[batch_id]["config"])
        destination = orch.batch_dir(cfg)
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination / orch.LEDGER_NAME)
        return orch.run_batch(cfg, runners=_fake_runners())

    return _replay


@pytest.fixture(scope="module")
def s4_toy(tmp_path_factory) -> tuple[Path, list[str]]:
    """Real S4 output for `toy_worker` (seed 7, verdict `fit`) plus the perfect
    replay plan — the b9 harness, so the battery below needs no driver."""
    out_dir = tmp_path_factory.mktemp("d3_s4") / TOY_WORKER.name
    report = run_s4(TOY_WORKER, _BASE_CFG, seed=S4_SEED, out_dir=out_dir)
    assert report["verdict"] == "fit", f"fixture wall: toy_worker S4 verdict {report['verdict']}"
    plan: list[str] = []
    index = 1
    while (out_dir / "actions" / f"level-{index}.json").is_file():
        records = json.loads(
            (out_dir / "actions" / f"level-{index}.json").read_text(encoding="utf-8")
        )
        for record in records:
            data = record.get("data") or {}
            plan.append(
                f"ACTION6 {int(data['x'])} {int(data['y'])}"
                if int(record["id"]) == 6
                else f"ACTION{int(record['id'])}"
            )
        index += 1
    assert plan, f"fixture wall: no actions/level-*.json under {out_dir}"
    return out_dir / "metadata.json", plan


@pytest.fixture
def battery_report(s4_toy, tmp_path):
    """A FRESH battery report, written under tmp with an injected chat."""
    metadata_path, plan = s4_toy

    def _run(battery_block: Mapping) -> dict:
        cfg = copy.deepcopy(dict(_BASE_CFG))
        cfg[BATTERY_BLOCK] = dict(battery_block)
        calls = [0]

        def chat(*args, **kwargs):
            text = plan[calls[0] % len(plan)]
            calls[0] += 1
            return ChatResult(
                driver="openrouter", model_requested=kwargs.get("model") or "fake-model",
                model_reported="fake/duck-v0", text=text, tokens_in=10, tokens_out=5,
                usd_cost=0.001, raw={"fake": True},
            )

        return run_battery(TOY_WORKER, cfg, chat=chat, metadata_path=metadata_path,
                           out_dir=tmp_path / "s5")

    return _run


@pytest.fixture
def lint_report(tmp_path):
    """A FRESH `lint-report.json`, written by `run_s1` with an INJECTED writer."""
    reply = "Synthetic prose for a D-3 pin.\n```yaml\n" + GOOD_SPEC.read_text(
        encoding="utf-8"
    ).rstrip() + "\n```\n"

    def _write(cfg: Mapping, label: str) -> dict:
        result = run_s1(IDEA_PATH, cfg, writer_runner=lambda prompt, *a, **k: reply,
                        out_root=tmp_path / label)
        path = Path(result.out_dir) / "lint-report.json"
        assert path.is_file(), f"run_s1 wrote no lint-report.json under {result.out_dir}"
        return json.loads(path.read_text(encoding="utf-8"))

    return _write


# ==========================================================================
# PIN 1 — `verifier.reject_cap` is WIRED
# ==========================================================================


def test_pin1_the_default_constant_stays_two() -> None:
    """§1: VERIFIER_REJECT_CAP_ESCALATE "= 2, which stays as the DEFAULT constant"."""
    assert orch.VERIFIER_REJECT_CAP_ESCALATE == 2, (
        "D-3 §1 keeps VERIFIER_REJECT_CAP_ESCALATE at 2 and only re-labels its comment as the "
        f"DEFAULT; got {orch.VERIFIER_REJECT_CAP_ESCALATE!r}"
    )
    assert isinstance(orch.VERIFIER_REJECT_CAP_ESCALATE, int)
    assert not isinstance(orch.VERIFIER_REJECT_CAP_ESCALATE, bool)


def test_pin1_absent_key_reads_as_the_default() -> None:
    """Absent `verifier.reject_cap` => the default constant (2)."""
    for label, cfg in (("bare verifier block", _bare()),
                       ("a real config with the key removed",
                        _cfg(key=REJECT_CAP_KEY))):
        assert _reject_cap(cfg) == orch.VERIFIER_REJECT_CAP_ESCALATE, (
            f"{label}: an absent `{VERIFIER_BLOCK}.{REJECT_CAP_KEY}` must read as "
            f"VERIFIER_REJECT_CAP_ESCALATE ({orch.VERIFIER_REJECT_CAP_ESCALATE}) — the shipped "
            f"behaviour; got {_reject_cap(cfg)!r}"
        )


def test_pin1_absent_verifier_block_takes_the_default() -> None:
    """Ambiguity (c): no `verifier:` block at all is the default, not a raise —
    the reading `_respec_cap`'s own docstring sets for the block beside it."""
    for cfg in ({}, {VERIFIER_BLOCK: {}}, {"orchestrator": {}}):
        assert _reject_cap(cfg) == orch.VERIFIER_REJECT_CAP_ESCALATE, (
            f"{cfg!r} must take the default cap. `_respec_cap` says it out loud for its own "
            "block ('a cfg with no `orchestrator:` at all simply takes the default here rather "
            "than raising twice over'); if lead adjudicates the other way, this test moves"
        )


@pytest.mark.parametrize("value", [1, 2, 3, 5, 12], ids=lambda v: f"cap-{v}")
def test_pin1_a_configured_int_is_honored(value: int) -> None:
    """§1: "int >= 1" — 5 is honored, and so is every other positive int."""
    assert _reject_cap(_bare(value)) == value, (
        f"`{VERIFIER_BLOCK}.{REJECT_CAP_KEY}: {value}` must read back as {value}, got "
        f"{_reject_cap(_bare(value))!r}"
    )
    assert _reject_cap(_cfg(key=REJECT_CAP_KEY, value=value)) == value


@pytest.mark.parametrize(
    "value",
    [0, -1, True, False, "2", 2.0, [2], {"cap": 2}, None],
    ids=["zero", "negative", "true", "false", "str", "float", "list", "mapping", "null"],
)
def test_pin1_a_bad_cap_fails_loud(value: object) -> None:
    """§1: int >= 1, fail-loud.  `0` would escalate on the first reject and
    `"2"` would silently become either 2 or nothing, so neither is guessed at.
    `null` is grouped here rather than defaulted: §1 gives the DEFAULT to an
    absent key, and a key written as null is a config someone edited wrong."""
    _raises_config_error(lambda: _reject_cap(_bare(value)),
                         f"{VERIFIER_BLOCK}.{REJECT_CAP_KEY}={value!r}")


def test_pin1_both_live_configs_still_write_two() -> None:
    """§1: "Both live configs already write 2 — behavior identical."  If this
    fails, D-3 changed a live batch's behaviour instead of wiring a dead key."""
    for relative in TOUCHED_CONFIGS:
        raw = _config_yaml(relative)
        cap = (raw.get(VERIFIER_BLOCK) or {}).get(REJECT_CAP_KEY)
        assert cap == orch.VERIFIER_REJECT_CAP_ESCALATE, (
            f"{relative} writes `{VERIFIER_BLOCK}.{REJECT_CAP_KEY}: {cap!r}`; D-3 wires the key "
            f"WITHOUT changing behaviour, which needs it to stay "
            f"{orch.VERIFIER_REJECT_CAP_ESCALATE}"
        )
        assert _reject_cap(load_config(relative)) == orch.VERIFIER_REJECT_CAP_ESCALATE


def test_pin1_a_bad_cap_fails_before_any_stage_is_invoked(make_cfg) -> None:
    """§1: "Read once per run, fail-loud before spend." — no runner, no ledger."""
    cfg, _path = make_cfg("d3-cap-preflight",
                          overrides={VERIFIER_BLOCK: {REJECT_CAP_KEY: 0}})
    calls: list[str] = []

    with pytest.raises((ValueError, TypeError)) as caught:
        orch.run_batch(cfg, runners=_forbidden_runners(calls))

    assert REJECT_CAP_KEY in str(caught.value), str(caught.value)
    assert calls == [], (
        f"a run with an invalid cap still invoked {calls} — the knob is read once per run and "
        "before spend, so a rejected config never costs a session"
    )
    ledger = orch.batch_dir(cfg) / orch.LEDGER_NAME
    assert not ledger.is_file(), f"a rejected config still wrote a ledger at {ledger}"


@pytest.mark.parametrize("cap", [2, 3, 4], ids=lambda c: f"cap-{c}")
def test_pin1_the_escalation_follows_the_configured_cap(make_cfg, cap: int) -> None:
    """The measurement, through the §4 machine with fake runners.

    A verifier that keeps rejecting must produce exactly `cap` reject lines, and
    ONLY the last one may carry `ESCALATE_PREFIX` — that is what "the escalation
    comparison uses the configured value" means, counted off the reasons the
    ledger recorded (no driver anywhere).

    The slot then blocks (an escalated re-spec with no verifier report beside the
    worker is the guard `_maybe_respec` already had); the reject lines are
    already on the ledger, which is what this pin reads.
    """
    cfg, _path = make_cfg(f"d3-cap-{cap}", overrides={VERIFIER_BLOCK: {REJECT_CAP_KEY: cap}})
    rejects = {"n": 0}

    def artifacts(ctx) -> dict:
        """The §2 files the state machine hashes and discovers a spec dir by."""
        slot_dir = ctx.corpus_dir / ctx.slug
        written = {}
        payload = json.dumps({"id": ctx.idea_path.stem, "slug": ctx.slug})
        for relative in ("idea.json", "spec.yaml", "spec.md", "lint-report.json",
                         "worker/game.py", "worker/solver.py"):
            path = slot_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.is_file():
                path.write_text(
                    payload if path.suffix == ".json" else f"# synthetic {relative}\n",
                    encoding="utf-8",
                )
            written[path.name] = str(path)
        ctx.idea_path.parent.mkdir(parents=True, exist_ok=True)
        if not ctx.idea_path.is_file():
            ctx.idea_path.write_text(payload, encoding="utf-8")
        written["idea_path"] = str(ctx.idea_path)
        return written

    def make(stage: str):
        def runner(ctx):
            if stage == "s3_verify" and rejects["n"] < cap:
                rejects["n"] += 1
                return {"ok": False, "to_state": "spec_ok",
                        "reason": f"verifier reject: synthetic finding #{rejects['n']}",
                        "cost": None, "artifacts": artifacts(ctx)}
            return {"ok": True, "to_state": orch.STAGE_SUCCESS[stage],
                    "reason": f"fake {stage}: green", "cost": None, "artifacts": artifacts(ctx)}
        return runner

    orch.run_batch(cfg, runners={stage: make(stage) for stage in orch.STAGES})

    table = orch.replay_ledger(orch.batch_dir(cfg) / orch.LEDGER_NAME)
    slug = orch.slot_id(cfg["batch"]["id"], 1)
    reject_lines = [line for line in table[slug]["history"]
                    if (line["from"], line["to"]) == ("implemented", "spec_ok")]
    escalated = [line["reason"].startswith(orch.ESCALATE_PREFIX) for line in reject_lines]

    assert len(reject_lines) == cap, (
        f"`{VERIFIER_BLOCK}.{REJECT_CAP_KEY}: {cap}` must let {cap} verifier rejects stand "
        f"against one spec before the escalation fires; the ledger recorded {len(reject_lines)}: "
        f"{[line['reason'][:60] for line in reject_lines]}"
    )
    assert escalated == [False] * (cap - 1) + [True], (
        f"with the cap at {cap} exactly the LAST reject may carry "
        f"{orch.ESCALATE_PREFIX!r}; got {escalated} for "
        f"{[line['reason'][:60] for line in reject_lines]} — the comparison is still reading the "
        f"hard-coded {orch.VERIFIER_REJECT_CAP_ESCALATE} instead of the configured value"
    )


# ==========================================================================
# PIN 2 — `lint.strict` and `battery.smoke` are GONE
# ==========================================================================


def test_pin2_lint_strict_reader_is_gone() -> None:
    """§2: "delete `_lint_strict` … and its call sites"."""
    assert not hasattr(s1_spec, "_lint_strict"), (
        "gen.s1_spec still exposes `_lint_strict`. D-3 §2 deletes it: the knob steers nothing, "
        "so reading it is the dishonesty being removed"
    )
    strays = sorted(name for name in vars(s1_spec) if "lint_strict" in name.lower())
    assert strays == [], f"gen.s1_spec still carries {strays}"


def test_pin2_a_fresh_lint_report_has_no_strict_field(lint_report) -> None:
    """§2: "the `strict` field disappears from newly written lint-report.json"."""
    payload = lint_report(_BASE_CFG, "touched")
    assert STRICT_KEY not in payload, (
        f"a freshly written lint-report.json still stamps {STRICT_KEY!r}="
        f"{payload.get(STRICT_KEY)!r} (keys: {sorted(payload)}) — the field goes with the reader"
    )
    for required in ("passed", "kills", "warns", "spec_hash", "idea_ref", "ts"):
        assert required in payload, (
            f"removing {STRICT_KEY!r} must not cost the report {required!r}: {sorted(payload)}"
        )


def test_pin2_a_config_that_still_declares_lint_strict_stamps_nothing(lint_report) -> None:
    """Ambiguity (j): `config/b001-pilot.yaml` is frozen and still declares
    `lint: {strict: true}`, so the key must be DEAD, not merely absent — the
    frozen batch identities have to keep running and must stamp nothing."""
    frozen = load_config(FROZEN_CONFIGS[0])
    assert (frozen.get(LINT_BLOCK) or {}).get(STRICT_KEY) is True, (
        f"fixture wall: {FROZEN_CONFIGS[0]} no longer declares `{LINT_BLOCK}.{STRICT_KEY}`, so "
        "this test can no longer prove the key is dead rather than absent"
    )
    payload = lint_report(frozen, "frozen")
    assert STRICT_KEY not in payload, (
        f"a config that still declares `{LINT_BLOCK}.{STRICT_KEY}` produced a report stamping "
        f"{payload.get(STRICT_KEY)!r} — nothing reads the key any more, so nothing records it"
    )


def test_pin2_the_battery_parser_accepts_a_block_without_smoke() -> None:
    """§3: "key no longer required, no longer stamped"."""
    parse = _battery_config_parser()
    block = {key: value for key, value in dict(_BASE_CFG[BATTERY_BLOCK]).items()
             if key != SMOKE_KEY}
    assert SMOKE_KEY not in block, "fixture wall: the smoke key was not removed from the block"

    parsed = parse({BATTERY_BLOCK: block})

    assert isinstance(parsed, Mapping), f"the parser returned {type(parsed).__name__}"
    assert SMOKE_KEY not in parsed, (
        f"the parsed battery config still carries {SMOKE_KEY!r}={parsed.get(SMOKE_KEY)!r} — §3 "
        "removes the key from the required list AND from what the stage carries"
    )
    for key in ("model", "passes", "token_cap"):
        assert key in parsed, f"removing {SMOKE_KEY!r} cost the parser {key!r}: {sorted(parsed)}"


def test_pin2_the_battery_parser_still_accepts_a_stray_smoke() -> None:
    """Ambiguity (j) again: both FROZEN configs still write `smoke: true`, so a
    block that carries it must parse — and still not be stamped."""
    parse = _battery_config_parser()
    for relative in FROZEN_CONFIGS:
        frozen = load_config(relative)
        assert (frozen.get(BATTERY_BLOCK) or {}).get(SMOKE_KEY) is True, (
            f"fixture wall: {relative} no longer declares `{BATTERY_BLOCK}.{SMOKE_KEY}`"
        )
        parsed = parse(frozen)
        assert SMOKE_KEY not in parsed, (
            f"{relative} still declares `{BATTERY_BLOCK}.{SMOKE_KEY}` and the parser carried it "
            f"through as {parsed.get(SMOKE_KEY)!r}; the key is dead, and a frozen config must "
            "keep loading without resurrecting it"
        )


def test_pin2_a_fresh_battery_report_has_no_smoke_field(battery_report) -> None:
    """§3: ":937 — no longer stamped"."""
    block = {key: value for key, value in dict(_BASE_CFG[BATTERY_BLOCK]).items()
             if key != SMOKE_KEY}
    block["passes"] = 1   # one pass is enough to write a report; the knob is the subject
    report = battery_report(block)

    found = _find_key(report, SMOKE_KEY, "battery-report")
    assert found == [], (
        f"the battery report still stamps {SMOKE_KEY!r} at {[spot for spot, _v in found]} — "
        f"§3 removes it from the report payload as well as from the required keys"
    )
    assert report["status"], "fixture wall: the battery wrote no status"
    assert "passes" in report["config"] and "token_cap" in report["config"], (
        f"removing {SMOKE_KEY!r} must not cost the report's config block its live knobs: "
        f"{sorted(report['config'])}"
    )


@pytest.mark.parametrize("relative", TOUCHED_CONFIGS)
def test_pin2_the_touched_configs_dropped_both_keys(relative: str) -> None:
    """§2/§3: "delete the `strict: true` line" / "delete the `smoke: true`"."""
    raw = _config_yaml(relative)
    lint = raw.get(LINT_BLOCK) or {}
    battery = raw.get(BATTERY_BLOCK) or {}
    assert STRICT_KEY not in lint, (
        f"{relative} still declares `{LINT_BLOCK}.{STRICT_KEY}`: {lint}"
    )
    assert SMOKE_KEY not in battery, (
        f"{relative} still declares `{BATTERY_BLOCK}.{SMOKE_KEY}`: {battery}"
    )
    assert "require_render" in lint, (
        f"{relative} lost `{LINT_BLOCK}.require_render` — only the dead key goes: {lint}"
    )
    for live in ("model", "passes", "token_cap"):
        assert live in battery, f"{relative} lost `{BATTERY_BLOCK}.{live}`: {battery}"
    assert load_config(relative), f"{relative} no longer loads"


@pytest.mark.parametrize("relative", FROZEN_CONFIGS)
def test_pin2_the_frozen_configs_are_not_touched(relative: str) -> None:
    """Ambiguity (k): "Do NOT touch config/b001-pilot.yaml or
    config/b002-triple.yaml (frozen, sha-recorded batch identities)"."""
    raw = _config_yaml(relative)
    assert (raw.get(LINT_BLOCK) or {}).get(STRICT_KEY) is True, (
        f"{relative} is FROZEN (sha-recorded batch identity) and D-3 touches neither frozen "
        f"config; `{LINT_BLOCK}.{STRICT_KEY}: true` must still be there"
    )
    assert (raw.get(BATTERY_BLOCK) or {}).get(SMOKE_KEY) is True, (
        f"{relative} is FROZEN; `{BATTERY_BLOCK}.{SMOKE_KEY}: true` must still be there"
    )


# ==========================================================================
# PIN 3 — `respec_runs` comes off the LEDGER
# ==========================================================================


def test_pin3_two_escalations_and_one_lint_cycle_report_three(planted) -> None:
    """The contract's own case: 2 escalation respecs + 1 lint resample => 3.

    The in-memory counter is never touched here — the ledger is planted and then
    replayed with fresh state, which is precisely the resume every shipped
    report died on (each one says 0 against a ledger full of respecs).
    """
    walk = ("birth", *LINT_CYCLE, *SPINE, *ESCALATION, *ESCALATION, *PACKAGED)
    cfg, _path, slugs = planted("d3-respec-three", [walk])
    report = orch.run_batch(cfg, runners=_fake_runners())

    row = _slot_row(report, slugs[0])
    assert row["state"] == "packaged", f"fixture wall: the planted slot replayed to {row['state']}"
    assert row["transitions"] == len(walk), (
        f"fixture wall: {row['transitions']} lines replayed for a {len(walk)}-edge walk"
    )
    assert _respec_runs(report, slugs[0]) == 3, (
        "D-3 §4: the report's respec count is DERIVED from the ledger — 2 ESCALATE_REASON-"
        "prefixed edges plus 1 lint-kill resample cycle is 3, not "
        f"{_respec_runs(report, slugs[0])}. A count of 0 is the in-memory counter, which dies "
        "on resume and is 0 in every shipped report"
    )


def test_pin3_one_complete_lint_cycle_counts_exactly_once(planted) -> None:
    """Ambiguity (d): a lint kill is a PAIR of §4 edges, and the pair is ONE
    respec.  Counting both edges would make the contract's own 2+1 case read 4."""
    walk = ("birth", *LINT_CYCLE, *SPINE, *PACKAGED)
    cfg, _path, slugs = planted("d3-respec-lint", [walk])
    report = orch.run_batch(cfg, runners=_fake_runners())

    assert _respec_runs(report, slugs[0]) == 1, (
        "one lint kill + its re-sample is ONE respec run, not two (and not zero): the contract's "
        "'2 escalation respecs + 1 lint resample ⇒ 3' only adds up this way. Got "
        f"{_respec_runs(report, slugs[0])}"
    )


def test_pin3_escalations_alone_are_counted(planted) -> None:
    """The verifier-escalation flavour on its own, recognised by the reason prefix."""
    walk = ("birth", *SPINE, *ESCALATION, *ESCALATION, *PACKAGED)
    cfg, _path, slugs = planted("d3-respec-esc", [walk])
    report = orch.run_batch(cfg, runners=_fake_runners())

    assert _respec_runs(report, slugs[0]) == 2, (
        "two ESCALATE_REASON-prefixed `implemented --> spec_ok` edges are two respec runs; got "
        f"{_respec_runs(report, slugs[0])}"
    )


def test_pin3_plain_verifier_rejects_are_not_respecs(planted) -> None:
    """§4 counts the ESCALATION edges, not every reject: a reject under the cap
    re-implements against the SAME spec and re-specs nothing."""
    walk = ("birth", *SPINE, "reject", "implement", "reject", "implement", *PACKAGED)
    cfg, _path, slugs = planted("d3-respec-plain", [walk])
    report = orch.run_batch(cfg, runners=_fake_runners())

    row = _slot_row(report, slugs[0])
    assert row["rejects"]["verifier"] == 2, f"fixture wall: {row['rejects']}"
    assert _respec_runs(report, slugs[0]) == 0, (
        "plain (un-escalated) verifier rejects are not respecs — only the "
        f"{orch.ESCALATE_PREFIX!r}-prefixed edges and the lint-kill resamples are. Got "
        f"{_respec_runs(report, slugs[0])} against 2 plain rejects"
    )


@pytest.mark.parametrize("batch_id", sorted(REAL_BATCHES))
def test_pin3_the_shipped_ledgers_report_their_real_respecs(real_replay, batch_id: str) -> None:
    """The replay proof: b002-triple => 3/3/3, b003r2 => 0/0 (contract §Verification)."""
    expected = REAL_BATCHES[batch_id]
    report = real_replay(batch_id)
    slugs = [orch.slot_id(batch_id, index) for index in range(1, len(expected["respecs"]) + 1)]
    got = tuple(_respec_runs(report, slug) for slug in slugs)

    assert got == expected["respecs"], (
        f"{batch_id} replays to respec counts {got}; its ledger's own edges say "
        f"{expected['respecs']}. This is the finding: "
        "'every shipped report says 0 against ledgers full of respecs'"
    )


def test_pin3_status_reports_respecs_at_all(capsys) -> None:
    """Ambiguity (h): the contract's proof reads respec counts off `--status`, so
    the table must report them; the NUMBERS are pinned on the report field
    (above), because §4 fixes no column spelling for this table."""
    batch_id = "b002-triple"
    config = REAL_BATCHES[batch_id]["config"]
    if not (REPO_ROOT / "out" / "batches" / batch_id / orch.LEDGER_NAME).is_file():
        pytest.skip(f"SKIPPED LOUDLY: no shipped ledger for {batch_id}")

    out = _status(REPO_ROOT / config, capsys)

    assert "respec" in out.lower(), (
        "`--status` reports no respec count. D-3's replay proof is '--status … respec_runs now "
        f"match the ledgers (b002: 3/3/3)', and the table only prints "
        f"{'lint/resamp/verif/crash/dead'!r} today:\n{out}"
    )
    for index in range(1, len(REAL_BATCHES[batch_id]["respecs"]) + 1):
        _slug_line(out, orch.slot_id(batch_id, index))


# ==========================================================================
# PIN 4 — a human PULL is not attrition
# ==========================================================================


def _attrition(report: Mapping) -> Mapping:
    attrition = report.get("attrition")
    assert isinstance(attrition, Mapping), f"the report carries no attrition block: {report!r}"
    return attrition


def test_pin4_wording_batch_ids_cannot_fake_a_match() -> None:
    """The guard on the two wording pins below.

    `--status` prints the batch id in its header and `_normal` folds hyphens to
    spaces, so a batch called `d3-review-complete` makes "review complete" appear
    in the output whatever the verdict line says — which is exactly how an
    earlier draft of this file passed against pre-D-3 code.  Every id used by a
    wording pin has to be inert.
    """
    for batch_id in (PULL_WORDING_BATCH, DEAD_WORDING_BATCH, *REAL_BATCHES):
        flat = _normal(batch_id)
        for phrase in (REVIEW_COMPLETE, ABORT):
            assert phrase not in flat, (
                f"batch id {batch_id!r} normalizes to {flat!r}, which contains {phrase!r} — the "
                "wording pins search the whole `--status` output, so the id must not answer for "
                "the verdict line"
            )


def test_pin4_one_dead_of_two_still_aborts(planted) -> None:
    """§5: the kill criteria stay a kill — "the abort machinery exists for
    SYSTEMATIC failure", and a death is exactly that.  1/2 = 0.50 > 0.30."""
    cfg, _path, slugs = planted(
        "d3-attrition-dead", [WALK_DEAD, WALK_PACKAGED]
    )
    assert cfg["orchestrator"]["max_attrition"] == 0.30, cfg["orchestrator"]
    report = orch.run_batch(cfg, runners=_fake_runners())

    attrition = _attrition(report)
    assert attrition["dead"] == 1 and attrition["pulled"] == 0, attrition
    assert attrition["abort"] is not None, (
        "1 dead slot of 2 is 0.50 against max_attrition 0.30 and must still abort the batch: "
        f"{attrition}"
    )
    assert report["status"] == "stopped", report["status"]
    assert _slot_row(report, slugs[0])["state"] == "dead"


def test_pin4_one_pulled_of_two_does_not_abort(planted) -> None:
    """§5: "the kill-fraction counts DEAD slots only".  A human pull is a review
    decision, not a systematic failure, so zero dead is zero attrition."""
    cfg, _path, slugs = planted(
        "d3-attrition-pull", [WALK_PULLED, WALK_PACKAGED]
    )
    report = orch.run_batch(cfg, runners=_fake_runners())

    attrition = _attrition(report)
    assert _slot_row(report, slugs[0])["state"] == "pulled", "fixture wall: nothing was pulled"
    assert attrition["dead"] == 0, attrition
    assert attrition["pulled"] == 1, (
        f"§5: `pulled` gets its OWN count in the report — {attrition}"
    )
    assert attrition["abort"] is None, (
        "a batch with ZERO dead slots whose slots are all terminal must not abort: a human pull "
        f"is a review outcome, and the abort machinery exists for systematic failure. {attrition}"
    )


@pytest.mark.parametrize(
    ("label", "walks", "dead", "pulled"),
    [
        ("dead", [WALK_DEAD, WALK_PACKAGED], 1, 0),
        ("pulled", [WALK_PULLED, WALK_PACKAGED], 0, 1),
        ("clean", [WALK_PACKAGED, WALK_PACKAGED], 0, 0),
    ],
)
def test_pin4_the_kill_fraction_is_dead_over_slots(
    planted, label: str, walks, dead: int, pulled: int
) -> None:
    """The arithmetic that IS change 5: the fraction is dead/slots, and a pull
    never enters it, however it is reported beside it."""
    cfg, _path, _slugs = planted(f"d3-fraction-{label}", walks)
    report = orch.run_batch(cfg, runners=_fake_runners())
    attrition = _attrition(report)

    assert (attrition["dead"], attrition["pulled"]) == (dead, pulled), attrition
    assert attrition["slots"] == len(walks), attrition
    assert attrition["fraction"] == pytest.approx(dead / len(walks)), (
        f"the kill fraction is {attrition['fraction']} for {dead} dead + {pulled} pulled of "
        f"{len(walks)}; §5 counts DEAD slots only, so it must be "
        f"{dead / len(walks)} — a human pull is not attrition"
    )


def test_pin4_a_pulled_batch_says_review_complete_not_aborted(planted, capsys) -> None:
    """§5: such a batch reports "stopped (review complete)" (ambiguity g: the
    contract also writes it "review-complete", so both spellings pass)."""
    cfg, path, _slugs = planted(PULL_WORDING_BATCH, [WALK_PULLED, WALK_PACKAGED])
    orch.run_batch(cfg, runners=_fake_runners())

    out = _status(path, capsys)
    flat = _normal(_flat(out))

    assert REVIEW_COMPLETE in flat, (
        "a batch with zero dead slots, all terminal, one of them a human pull, must say "
        f"'{REVIEW_COMPLETE}' — §5. `--status` said:\n{out}"
    )
    assert ABORT not in flat, (
        f"`--status` still reports an abort for a reviewed-and-pulled batch:\n{out}"
    )


def test_pin4_a_dead_batch_does_not_claim_review_complete(planted, capsys) -> None:
    """Ambiguity (i): the wording is a DISCRIMINATOR.  A batch that really did
    lose a slot must not borrow the review-complete line."""
    cfg, path, _slugs = planted(DEAD_WORDING_BATCH, [WALK_DEAD, WALK_PACKAGED])
    orch.run_batch(cfg, runners=_fake_runners())

    out = _status(path, capsys)
    assert REVIEW_COMPLETE not in _normal(_flat(out)), (
        "a batch that lost a slot to the green cap is not 'review complete'; §5 gives that "
        f"wording to a batch with ZERO dead whose slots are all terminal:\n{out}"
    )


def test_pin4_the_shipped_b003r2_replay_no_longer_aborts(real_replay) -> None:
    """The recorded finding: b003r2's ledger is one packaged game and one human
    pull, and it replays as BATCH ABORTED (0 dead, 1 pulled, 1/2 = 0.50)."""
    batch_id = "b003r2-simplicity"
    expected = REAL_BATCHES[batch_id]
    report = real_replay(batch_id)
    attrition = _attrition(report)

    assert attrition["dead"] == expected["dead"], attrition
    assert attrition["pulled"] == expected["pulled"], attrition
    assert attrition["fraction"] == pytest.approx(0.0), (
        f"{batch_id} replays to kill-fraction {attrition['fraction']} — its only non-packaged "
        "slot was PULLED by a human, and the fraction counts dead slots only"
    )
    assert attrition["abort"] is None, (
        f"{batch_id} still replays as an attrition abort: {attrition['abort']}"
    )
    assert json.dumps(report).lower().count("aborted") == 0, (
        "the b003r2 batch report still carries an ABORTED claim"
    )


def test_pin4_the_shipped_b003r2_status_says_review_complete(capsys) -> None:
    """§Verification: "b003r2 prints review-complete not ABORTED"."""
    batch_id = "b003r2-simplicity"
    if not (REPO_ROOT / "out" / "batches" / batch_id / orch.LEDGER_NAME).is_file():
        pytest.skip(f"SKIPPED LOUDLY: no shipped ledger for {batch_id}")

    out = _status(REPO_ROOT / REAL_BATCHES[batch_id]["config"], capsys)
    flat = _normal(_flat(out))

    assert ABORT not in flat, (
        f"the b003r2 ledger replayed through `--status` still prints an abort:\n{out}"
    )
    assert REVIEW_COMPLETE in flat, (
        "the b003r2 ledger is one packaged game and one human pull — `--status` must report "
        f"review-complete:\n{out}"
    )
    assert "pulled" in flat, (
        f"`--status` must still show the pull it is no longer counting as attrition:\n{out}"
    )


# ==========================================================================
# PIN 5 — the cost label
# ==========================================================================


def test_pin5_the_cost_note_names_the_three_priced_stages() -> None:
    """§6: "usd totals cover s2_implement + s3_verify + s5_battery only"."""
    note = _cost_note()
    assert isinstance(note, str) and note.strip(), f"the cost note is {note!r}"
    missing = [stage for stage in PRICED_STAGES if stage not in note]
    assert not missing, (
        f"the cost note does not name {missing}: {note!r}. §6 names the three priced stages so a "
        "reader of the batch report knows what the usd total is a total OF"
    )


def test_pin5_the_cost_note_says_the_rest_is_unpriced() -> None:
    """§6: "s0/s1 sessions and gate/S4/S6 compute are unpriced".  The exact
    spelling of that half is not frozen, so this pin asks only that the note
    bounds itself and points at what it leaves out."""
    note = _cost_note()
    flat = note.lower()
    assert "only" in flat or "unpriced" in flat, (
        f"the cost note does not bound itself: {note!r}. §6's own words are 'cover … only' and "
        "'are unpriced' — without one of them the note reads like a full accounting"
    )
    named = [marker for marker in UNPRICED_MARKERS if marker in flat]
    assert len(named) >= 2, (
        f"the cost note points at none of the unpriced stages ({UNPRICED_MARKERS}): {note!r}. §6: "
        "'s0/s1 sessions and gate/S4/S6 compute are unpriced'"
    )


def test_pin5_the_batch_report_carries_the_shared_constant(planted) -> None:
    """§6: the batch report gains the `cost_note` — the CONSTANT, not a copy of
    its prose (ambiguity e: this file pins the value, never the position)."""
    cfg, _path, _slugs = planted("d3-costnote-report", [WALK_PACKAGED])
    report = orch.run_batch(cfg, runners=_fake_runners())
    note = _cost_note()

    found = _find_key(report, COST_NOTE_FIELD)
    assert found, (
        f"the batch report carries no {COST_NOTE_FIELD!r} anywhere (top-level keys: "
        f"{sorted(report)}; cost keys: {sorted(report['cost'])}). §6 gives the report the fixed "
        "cost-label constant"
    )
    for spot, value in found:
        assert value == note, (
            f"{spot} carries {value!r}, not the shared constant {note!r} — §6: 'One constant, "
            "both consumers'"
        )

    written = orch.batch_dir(cfg) / orch.BATCH_REPORT_NAME
    assert written.is_file(), f"no batch report on disk at {written}"
    assert _find_key(json.loads(written.read_text(encoding="utf-8")), COST_NOTE_FIELD), (
        f"{written.name} on disk carries no {COST_NOTE_FIELD!r} — the report of record is the "
        "R5 source, and it is the one that has to say what the total covers"
    )


def test_pin5_the_status_footer_carries_the_shared_constant(planted, capsys) -> None:
    """§6: "the --status footer" gains the same constant."""
    cfg, path, _slugs = planted("d3-costnote-status", [WALK_PACKAGED])
    orch.run_batch(cfg, runners=_fake_runners())

    out = _status(path, capsys)
    note = _cost_note()

    assert _flat(note) in _flat(out), (
        f"the `--status` footer does not carry the cost note. §6: one constant, BOTH consumers "
        f"(the batch report and the --status footer).\nnote: {note!r}\nstatus:\n{out}"
    )
    for stage in PRICED_STAGES:
        assert stage in out, f"`--status` does not name the priced stage {stage!r}:\n{out}"


def test_pin5_the_same_constant_reaches_both_consumers(planted, capsys) -> None:
    """"One constant, both consumers" — asserted as identity between the two
    surfaces, so a future edit cannot drift one copy against the other."""
    cfg, path, _slugs = planted("d3-costnote-both", [WALK_PACKAGED])
    report = orch.run_batch(cfg, runners=_fake_runners())
    out = _status(path, capsys)

    from_report = {value for _spot, value in _find_key(report, COST_NOTE_FIELD)}
    assert from_report, f"no {COST_NOTE_FIELD!r} in the report: {sorted(report)}"
    assert len(from_report) == 1, f"the report carries conflicting cost notes: {from_report}"
    note = from_report.pop()
    assert note == _cost_note(), (
        f"the report's note {note!r} is not the module constant {_cost_note()!r}"
    )
    assert _flat(note) in _flat(out), (
        f"the report and `--status` do not print the same note.\nreport: {note!r}\nstatus:\n{out}"
    )


# LEAD-AUTHORED ADDITION (not part of the blind suite): the blind writer noted
# that once the implementation exposed a labelled respec column in --status, a
# numeric pin became possible — but writing it blind-side after seeing the
# column would pin the implementation, not the contract. As the lead I add it
# deliberately: the REAL b002 ledger's respec counts must be visible in the
# operator's own status view, not only in the report field.
def test_lead_status_shows_real_b002_respec_counts(capsys):
    from pathlib import Path as _Path

    import pytest as _pytest
    ledger = _Path("out/batches/b002-triple/ledger.jsonl")
    if not ledger.is_file():
        _pytest.skip(f"real b002 ledger absent at {ledger} — fresh clone")
    from gen import orchestrator as _orch
    rc = _orch.main(["--config", "config/b002-triple.yaml", "--status"])
    out = capsys.readouterr().out
    assert rc == 0
    slot_lines = [line for line in out.splitlines() if "b002-triple-s" in line]
    assert len(slot_lines) == 3, out
    for line in slot_lines:
        assert " 3" in line, (
            "each b002 slot ran exactly 3 escalation respecs (ledger-counted); "
            f"the status row must show it: {line!r}"
        )
