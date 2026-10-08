"""B7 acceptance: the S2b/S3 intent verifier — frames, statics, agent pass, verdict.

Run: .venv/bin/python -m pytest gen/tests/test_b7_verify.py -q

Written FROM THE B7 CONTRACT and from canon, never from the implementation:
`gen/frames.py`, `gen/s3_static.py` and `gen/s3_verify.py` were built in
parallel with this file by other agents and none of their source was read.
Every expectation below is either a name/shape the contract froze or a canon
rule cited at its source.

Agent sessions are INJECTED fakes, exactly as in test_b3_green_loop.py: a
fake `get_driver` returns a driver whose `session()` logs its call, optionally
edits the staged copy, and returns a real `SessionResult`. No CLI is ever
spawned and no network is touched.

The bad-game fixtures under `fixtures/badgames/` each seed EXACTLY ONE
violation and each one runs under the engine (every test that names a fixture
captures frames from it, which is the proof):

  missing_complete_action.py  static.complete-action
      spec §2 FORBIDDEN — "leaving a handler without `complete_action()`
      (the engine re-runs the action — double-charge)"; affordance §8.
  false_sys_click.py          static.sys-click-truthful
      spec §2 REQUIRED row 2 — "`sys_click` tags are truthful — always (the
      engine's click-action list and RL consumers read them)".
  unread_minus2.py            static.unread-minus2
      spec §2 REQUIRED row 5 + FORBIDDEN #4 — "`-2` nothing reads is
      forbidden dead weight"; affordance §8 `-2` semantics.
  readerless_field.py         static.parsed-field-no-reader
      architecture §3 S2b static passes — "parsed-field-has-reader"; spec §3
      operational semantics ("dead code is recorded, never counted").
  hud_collision.py            static.palette-hud-collision
      spec §2 FORBIDDEN #1 + REQUIRED row 7; affordance §8 — "Interface
      masks must key on geometry, never colour equality" (r11l).
  noop_prefix_worker/         solver.noop-prefix
      architecture §3 S2b solver-quality leg ("no-op-prefix detect") and S4
      step 1 (the baseline is the solver's real line).

`gen/tests/toy_worker` is the CLEAN case and is read-only here.

CONTRACT AMBIGUITIES this file had to take a position on (reported to the
lead, not invented quietly):
  A. `validate_claims(claims)` / `validate_report(report)` are frozen as
     one-argument functions, but the prose says the vocabulary is "passed
     in". These tests call the FROZEN one-argument signature, so an
     implementation that requires a vocab argument must default it.
  B. `compute_diff`'s spec dict: the contract calls `terms` "top-level",
     but the real parsed spec.yaml
     (out/corpus/b001-pilot/fogbound-switchyard/spec.yaml, and
     `s1_spec.lint_spec`, which reads `spec["game"]`) nests everything under
     `game:`. These tests pass the REAL parsed shape.
  C. `dead_spec_terms` vs `unreachable_declared_mechanics`: the only reading
     the frozen claims JSON supports is declared-and-never-claimed vs
     declared-and-claimed-with-`reachable: false`. That is what is tested.
  D. `run_static_checks(worker_dir, …)` is handed an official's variant
     directory (`<slug>/<variant>/` holding `<slug>.py`) in the battery,
     because that is the only directory an official has and `--official`
     is the contract's acceptance path.
  E. `--out DIR` for a dry run: the report is located by rglob, since the
     contract fixes `out/verify/<slug>/` for the default but not the layout
     under an explicit `--out`.
  F. `run_agent_pass` has no frozen return shape; it is tested against the
     report's frozen `agent` block, which is the only consumer the contract
     names.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
from arcengine import ARCBaseGame

from gen import backends
from gen import s3_verify as s3_verify_mod
from gen.backends import SessionResult
from gen.config import REPO_ROOT, load_config
from gen.frames import (
    ClickCell,
    FrameCapture,
    FrameRecord,
    capture,
    capture_from_json,
    capture_to_json,
    digest_text,
)
from gen.officials import Official, discover_officials, load_official_class
from gen.s0_ideas import load_vocab
from gen.s1_spec import DECEPTION_CATALOG
from gen.s3_static import (
    KNOWN_OFFICIAL_FAILS,
    CheckResult,
    Evidence,
    run_required_rows,
    run_solver_quality,
    run_static_checks,
)
from gen.s3_verify import (
    assert_unchanged,
    build_verifier_prompt,
    compute_diff,
    decide_verdict,
    extract_claims,
    run_agent_pass,
    stage_worker_copy,
    validate_claims,
    validate_report,
    write_report,
)

TESTS = Path(__file__).resolve().parent
TOY = TESTS / "toy_worker"
BADGAMES = TESTS / "fixtures/badgames"
NOOP_WORKER = BADGAMES / "noop_prefix_worker"
PILOT_CONFIG = "config/b001-pilot.yaml"

# --- frozen ids (B7 contract) ------------------------------------------------
STATIC_IDS = (
    "static.complete-action",
    "static.sys-click-truthful",
    "static.unread-minus2",
    "static.parsed-field-no-reader",
    "static.palette-hud-collision",
)
REQUIRED_IDS = tuple(f"required.row{n}" for n in range(1, 9))
SOLVER_IDS = ("solver.noop-prefix", "solver.bfs-spot-check", "solver.lag-confirm-modeled")
STATUSES = frozenset({"pass", "fail", "premise-not-met", "deferred", "skipped"})
EVIDENCE_KINDS = frozenset({"code", "frame", "engine"})
DIFF_KEYS = (
    "terms_declared",
    "terms_detected_reachable",
    "dead_spec_terms",
    "undeclared_terms",
    "unreachable_declared_mechanics",
    "deceptions_declared",
    "deceptions_detected",
    "undeclared_deceptions",
    "declared_deceptions_undetected",
)
REPORT_KEYS = (
    "schema_version",
    "game_id",
    "worker",
    "mode",
    "canon",
    "frames",
    "checks",
    "required_rows",
    "agent",
    "diff",
    "verdict",
    "reject_reasons",
    "versions",
)
CLAIM_KEYS = ("terms", "dead_code", "deceptions", "enforcement", "notes")
REJECT_CODES = (
    "forbidden-static",
    "undeclared-deception",
    "dead-spec-term",
    "undeclared-term",
    "unreachable-declared-mechanic",
    "solver-quality",
)

# fixture file -> the ONE check id it seeds
SEEDED = {
    "missing_complete_action.py": "static.complete-action",
    "false_sys_click.py": "static.sys-click-truthful",
    "unread_minus2.py": "static.unread-minus2",
    "readerless_field.py": "static.parsed-field-no-reader",
    "hud_collision.py": "static.palette-hud-collision",
}

HEX_ROW_RE = re.compile(r"^[0-9a-f]{64}$")

# The 7 declared terms of the real pilot spec, copied from
# out/corpus/b001-pilot/fogbound-switchyard/spec.yaml (verified 2026-09-22).
PILOT_TERMS = (
    "goal.cover",
    "info.fog",
    "info.telegraph",
    "terrain.conveyor",
    "gate.direct",
    "manip.select_cycle",
    "info.recall",
)

# Collection-time discovery, as in test_officials_conformance.py: the
# parametrisation needs the slugs before any fixture runs.
_CFG = load_config(PILOT_CONFIG)
_OFFICIALS = discover_officials(_CFG)
official_param = pytest.mark.parametrize(
    "official", _OFFICIALS, ids=[o.slug for o in _OFFICIALS]
)
# The smallest official (777 lines) — the acceptance path's subject.
ACCEPTANCE_SLUG = "cd82"


# --------------------------------------------------------------------------- #
# loaders + staging helpers
# --------------------------------------------------------------------------- #

_LOAD_SEQ = itertools.count()


def _load_module(path: Path):
    """Exec-load a fixture file under a unique module name (no sys.modules clashes)."""
    name = f"b7_fixture_{next(_LOAD_SEQ)}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot import {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _game_class(path: Path) -> type:
    module = _load_module(path)
    found = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and issubclass(obj, ARCBaseGame)
        and obj is not ARCBaseGame
        and obj.__module__ == module.__name__
    ]
    assert len(found) == 1, f"{path}: expected one ARCBaseGame subclass, found {found!r}"
    return found[0]


def _solver_class(path: Path) -> type:
    module = _load_module(path)
    solver = getattr(module, "Solver", None)
    assert isinstance(solver, type), f"{path}: no Solver class"
    return solver


def _stage_badgame(dest: Path, filename: str) -> Path:
    """One bad game staged as a worker: `<dest>/game.py`, nothing else."""
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BADGAMES / filename, dest / "game.py")
    return dest


def _stage_worker(dest: Path, source: Path, *, with_solver: bool = True) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "game.py", dest / "game.py")
    if with_solver:
        shutil.copy2(source / "solver.py", dest / "solver.py")
    return dest


def _fails(results) -> list[str]:
    return [r.check_id for r in results if r.status == "fail"]


def _hex_blocks(digest: str) -> int:
    """How many 64-row frames the digest rendered."""
    rows = [line for line in digest.splitlines() if HEX_ROW_RE.match(line.strip())]
    assert len(rows) % 64 == 0, f"digest has {len(rows)} hex rows, not a multiple of 64"
    return len(rows) // 64


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def cfg() -> dict:
    return _CFG


@pytest.fixture(scope="session")
def vocab(cfg) -> dict:
    return load_vocab(cfg)


@pytest.fixture(scope="session")
def bfs_cap(cfg) -> int:
    cap = cfg["verifier"]["bfs_level_size_cap"]
    assert isinstance(cap, int), f"verifier.bfs_level_size_cap must be an int, got {cap!r}"
    return cap


@pytest.fixture(scope="session")
def toy_capture() -> FrameCapture:
    return capture(_game_class(TOY / "game.py"), _solver_class(TOY / "solver.py"))


@pytest.fixture(scope="session")
def toy_worker(tmp_path_factory) -> Path:
    """A writable copy of the clean toy worker (the real one stays untouched)."""
    return _stage_worker(tmp_path_factory.mktemp("toy-clean") / "worker", TOY)


@pytest.fixture(scope="session")
def noop_worker(tmp_path_factory) -> Path:
    return _stage_worker(tmp_path_factory.mktemp("noop") / "worker", NOOP_WORKER)


@pytest.fixture(scope="session")
def official_class():
    """Slug-keyed class cache — officials are expensive to exec-load (ka59: 41k lines)."""
    cache: dict[str, type] = {}

    def _get(official: Official) -> type:
        if official.slug not in cache:
            cache[official.slug] = load_official_class(official.py_path)
        return cache[official.slug]

    return _get


@pytest.fixture(scope="session")
def official_capture(official_class):
    """Slug-keyed probe-capture cache: one probe plan per official per session."""
    cache: dict[str, FrameCapture] = {}

    def _get(official: Official) -> FrameCapture:
        if official.slug not in cache:
            cache[official.slug] = capture(official_class(official))
        return cache[official.slug]

    return _get


# --------------------------------------------------------------------------- #
# group 1 — frames
# --------------------------------------------------------------------------- #


def test_solver_capture_shape(toy_capture):
    """The solver plan: RESET, every level transition, final — on the clean toy."""
    cap = toy_capture
    assert cap.source == "solver"
    assert cap.game_id == "toy-scaffold-01"
    assert cap.win is True and cap.levels_completed == 2
    assert cap.solver_actions, "a solver capture must record the solver's line"
    assert all(isinstance(a, str) and a.startswith("ACTION") for a in cap.solver_actions)
    labels = [r.label for r in cap.records]
    assert labels[0] == "reset" and labels[-1] == "final"
    assert len(set(labels)) == len(labels), f"labels must be unique: {labels}"
    assert [r.seq for r in cap.records] == list(range(len(cap.records)))
    assert all(isinstance(r, FrameRecord) for r in cap.records)
    for record in cap.records:
        assert len(record.grid) == 64 and all(len(row) == 64 for row in record.grid)
        assert all(0 <= value <= 15 for row in record.grid for value in row)
    assert cap.available_action_ids == (1, 2, 3, 4)


def test_solver_capture_is_deterministic():
    """Two captures of the same class must be byte-identical (contract: REQUIRED)."""
    game_cls = _game_class(TOY / "game.py")
    solver_cls = _solver_class(TOY / "solver.py")
    first = capture_to_json(capture(game_cls, solver_cls))
    second = capture_to_json(capture(game_cls, solver_cls))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_capture_json_round_trips(toy_capture):
    payload = capture_to_json(toy_capture)
    json.dumps(payload)  # JSON-safe: no tuples-as-keys, no numpy scalars
    assert capture_from_json(payload) == toy_capture


def test_digest_carries_labels_and_hex_rows(toy_capture):
    digest = digest_text(toy_capture)
    assert toy_capture.game_id in digest
    assert "reset" in digest and "final" in digest
    assert _hex_blocks(digest) == len(toy_capture.records)
    # values 0..15 rendered as 0..9a..f — the grid must survive into the text
    assert any(HEX_ROW_RE.match(line.strip()) for line in digest.splitlines())


@pytest.fixture(scope="session")
def probe_capture_minus2() -> FrameCapture:
    """Probe capture of a 4-action game (unread_minus2): RESET + one per action."""
    return capture(_game_class(BADGAMES / "unread_minus2.py"))


def test_digest_honors_the_frame_cap(probe_capture_minus2):
    capped = digest_text(probe_capture_minus2, max_frames=2)
    assert _hex_blocks(capped) <= 2
    assert "reset" in capped, "the cap must never drop the RESET frame"
    assert _hex_blocks(digest_text(probe_capture_minus2, max_frames=12)) == len(
        probe_capture_minus2.records
    )


def test_probe_plan_covers_every_available_action(probe_capture_minus2):
    cap = probe_capture_minus2
    assert cap.source == "probe"
    assert cap.solver_actions == ()
    assert cap.available_action_ids == (1, 2, 3, 4)
    assert cap.records[0].label == "reset"
    assert len(cap.records) == 5, [r.label for r in cap.records]
    assert len(cap.records) <= 40, "the probe plan is capped at ~40 records"
    assert [r.seq for r in cap.records] == list(range(5))
    assert cap.click_cells == (), "a game with no sys_click sprites has no click cells"


def test_probe_capture_is_deterministic():
    game_cls = _game_class(BADGAMES / "hud_collision.py")
    first = capture_to_json(capture(game_cls))
    second = capture_to_json(capture(game_cls))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_probe_reads_the_engine_click_cells():
    """false_sys_click ships two sys_click sprites; the engine reports both."""
    cap = capture(_game_class(BADGAMES / "false_sys_click.py"))
    assert cap.available_action_ids == (6,)
    assert len(cap.click_cells) == 2, cap.click_cells
    assert len(cap.click_cells) <= 8, "the click probe is capped at 8 cells"
    assert all(isinstance(c, ClickCell) for c in cap.click_cells)
    # The engine's own list at RESET: (8, 24) = switch, (40, 24) = inert_panel.
    assert sorted((c.x, c.y) for c in cap.click_cells) == [(8, 24), (40, 24)]
    assert all(c.level_index == 0 for c in cap.click_cells)
    assert len(cap.records) == 1 + len(cap.click_cells)


# --------------------------------------------------------------------------- #
# group 2 — static passes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("filename,seeded", sorted(SEEDED.items()))
def test_badgame_fails_exactly_its_seeded_check(tmp_path, filename, seeded):
    worker = _stage_badgame(tmp_path / "worker", filename)
    cap = capture(_game_class(worker / "game.py"))  # proof the fixture runs
    assert cap.records, f"{filename} produced no frames"

    results = run_static_checks(worker, cap)
    assert _fails(results) == [seeded], (
        f"{filename} must fail {seeded} and nothing else; got "
        + json.dumps([asdict(r) for r in results], indent=2)
    )
    failed = next(r for r in results if r.status == "fail")
    assert failed.evidence, "a failing static check must carry evidence"
    assert failed.note.strip(), "a failing static check must explain itself"


def test_clean_toy_worker_has_no_static_fail(toy_worker, toy_capture):
    results = run_static_checks(toy_worker, toy_capture)
    assert _fails(results) == [], json.dumps([asdict(r) for r in results], indent=2)


def test_static_results_have_the_frozen_shape(toy_worker, toy_capture):
    results = run_static_checks(toy_worker, toy_capture)
    assert all(isinstance(r, CheckResult) for r in results)
    assert [r.check_id for r in results] == list(STATIC_IDS), (
        "run_static_checks returns the five frozen static checks, in order"
    )
    for result in results:
        assert result.leg == "static"
        assert result.status in STATUSES, result.status
        for item in result.evidence:
            assert isinstance(item, Evidence)
            assert item.kind in EVIDENCE_KINDS, item.kind


def test_static_evidence_points_at_code_or_frames(tmp_path):
    """The seeded HUD collision is provable from BOTH code and frames."""
    worker = _stage_badgame(tmp_path / "worker", "hud_collision.py")
    cap = capture(_game_class(worker / "game.py"))
    failed = next(
        r
        for r in run_static_checks(worker, cap)
        if r.check_id == "static.palette-hud-collision" and r.status == "fail"
    )
    kinds = {item.kind for item in failed.evidence}
    assert kinds & EVIDENCE_KINDS, failed
    labels = {r.label for r in cap.records}
    for item in failed.evidence:
        if item.frame_label is not None:
            assert item.frame_label in labels, f"{item.frame_label!r} is not a captured label"


# --------------------------------------------------------------------------- #
# group 3 — the eight REQUIRED rows (spec §2)
# --------------------------------------------------------------------------- #


def test_required_rows_are_the_eight_in_order(toy_worker, toy_capture):
    results = run_required_rows(toy_worker, toy_capture)
    assert len(results) == 8
    assert [r.check_id for r in results] == list(REQUIRED_IDS)
    assert all(r.leg == "required" for r in results)
    assert all(r.status in STATUSES for r in results)


def test_required_rows_are_honest_on_the_clean_toy(toy_worker, toy_capture):
    """No fake passes: a deferred row states why, a premise-not-met row proves it."""
    results = run_required_rows(toy_worker, toy_capture)
    assert _fails(results) == [], json.dumps([asdict(r) for r in results], indent=2)
    for result in results:
        if result.status == "deferred":
            assert result.note.strip(), f"{result.check_id}: deferred needs a reason"
        if result.status == "premise-not-met":
            assert result.evidence, f"{result.check_id}: needs evidence the premise is absent"


def test_required_rows_run_on_a_probe_capture(tmp_path, probe_capture_minus2):
    """The dry-run path (no solver) still answers all eight rows."""
    worker = _stage_badgame(tmp_path / "worker", "unread_minus2.py")
    results = run_required_rows(worker, probe_capture_minus2)
    assert [r.check_id for r in results] == list(REQUIRED_IDS)
    assert all(r.status in STATUSES for r in results)


# --------------------------------------------------------------------------- #
# group 4 — solver quality
# --------------------------------------------------------------------------- #


def test_noop_prefix_fixture_fails_the_noop_check(noop_worker, bfs_cap):
    cap = capture(
        _game_class(noop_worker / "game.py"), _solver_class(noop_worker / "solver.py")
    )
    assert cap.win is True, "the noop worker must still WIN — only its prefix is padding"
    assert cap.solver_actions[:3] == ("ACTION1", "ACTION1", "ACTION1")

    results = run_solver_quality(noop_worker, cap, bfs_cell_cap=bfs_cap)
    assert [r.check_id for r in results] == list(SOLVER_IDS)
    assert all(r.leg == "solver" for r in results)
    noop = next(r for r in results if r.check_id == "solver.noop-prefix")
    assert noop.status == "fail", json.dumps([asdict(r) for r in results], indent=2)
    assert noop.evidence, "the no-op prefix must be evidenced by the frame-identical labels"


def test_clean_toy_solver_passes_the_solver_leg(toy_worker, toy_capture, bfs_cap):
    results = run_solver_quality(toy_worker, toy_capture, bfs_cell_cap=bfs_cap)
    assert _fails(results) == [], json.dumps([asdict(r) for r in results], indent=2)


def test_no_solver_dir_skips_all_three(tmp_path, probe_capture_minus2, bfs_cap):
    worker = _stage_badgame(tmp_path / "worker", "unread_minus2.py")
    assert not (worker / "solver.py").exists()
    results = run_solver_quality(worker, probe_capture_minus2, bfs_cell_cap=bfs_cap)
    assert [r.check_id for r in results] == list(SOLVER_IDS)
    assert [r.status for r in results] == ["skipped"] * 3
    assert all("no solver" in r.note for r in results)


# --------------------------------------------------------------------------- #
# group 5 — the 25-official calibration battery (D8)
# --------------------------------------------------------------------------- #


@official_param
def test_official_has_no_static_or_required_fail(official_capture, official: Official):
    """The battery matches the ADJUDICATED fail set exactly (lead ruling, B7).

    The original zero-fail target could not hold: canon's FORBIDDEN list was
    written FROM official defects (affordance §8 names r11l's line painter as
    the palette-equality violation), so a check strong enough to catch the
    seeded fixtures necessarily fails the officials canon documents. The corrected D8
    rule: every fail must be a pinned, evidence-cited entry in
    `KNOWN_OFFICIAL_FAILS`; an official outside that map is clean, one inside
    fails EXACTLY its pinned check and nothing else. Drift in either
    direction — a new fail, a vanished fail, a different check — breaks here.

    `worker_dir` is the official's variant directory — the only directory an
    official has, and what `--official` must work against.
    """
    cap = official_capture(official)
    worker_dir = official.py_path.parent
    results = run_static_checks(worker_dir, cap) + run_required_rows(worker_dir, cap)
    failed_ids = sorted(r.check_id for r in results if r.status == "fail")
    pinned = KNOWN_OFFICIAL_FAILS.get(official.slug)
    expected_ids = sorted([pinned["check_id"]]) if pinned else []
    assert failed_ids == expected_ids, (
        f"{official.game_id} ({official.py_path}): expected fails {expected_ids} "
        f"(KNOWN_OFFICIAL_FAILS), got: "
        + json.dumps(
            [asdict(r) for r in results if r.status == "fail"], indent=2
        )
    )


# --------------------------------------------------------------------------- #
# group 6 — the claims block
# --------------------------------------------------------------------------- #


def _evidence(line: int = 61) -> list[dict]:
    return [{"path": "game.py", "line": line, "note": "try_move on ACTION1-4"}]


def _claims(**overrides) -> dict:
    claims = {
        "terms": [
            {
                "term": "move.grid",
                "reachable": True,
                "evidence": _evidence(),
                "frame_refs": ["reset"],
            }
        ],
        "dead_code": [],
        "deceptions": [{"lever": "decoy", "evidence": _evidence(44)}],
        "enforcement": [
            {"claim": "exhaustion calls lose() after the win check", "evidence": _evidence(80)}
        ],
        "notes": "derived from game.py and the frames only",
    }
    claims.update(overrides)
    return claims


def _reply(claims: dict, *, prose: str = "Audit of the code in cwd.") -> str:
    return f"{prose}\n\n```json\n{json.dumps(claims, indent=2)}\n```\n"


def test_extract_claims_takes_the_last_fenced_json_block():
    claims = _claims()
    reply = (
        "First, a sketch I discarded:\n\n```json\n{\"terms\": []}\n```\n\n"
        "The real answer:\n\n" + _reply(claims)
    )
    extracted = extract_claims(reply)
    assert extracted == claims
    assert sorted(extracted) == sorted(CLAIM_KEYS)


def test_extract_claims_rejects_a_reply_with_no_block():
    with pytest.raises(ValueError):
        extract_claims("I read the code but I am not going to fence anything.")


def test_extract_claims_rejects_unparseable_json():
    with pytest.raises(ValueError):
        extract_claims("done\n\n```json\n{\"terms\": [,]}\n```\n")


def test_validate_claims_accepts_a_good_payload():
    validate_claims(_claims())


def test_validate_claims_rejects_unknown_top_level_keys():
    claims = _claims()
    claims["extras"] = []
    with pytest.raises(ValueError):
        validate_claims(claims)
    missing = _claims()
    del missing["notes"]
    with pytest.raises(ValueError):
        validate_claims(missing)


def test_validate_claims_rejects_a_term_outside_the_vocabulary(vocab):
    bogus = "move.teleport"
    assert bogus not in vocab, "pick a term the signed 71 really does not contain"
    claims = _claims(
        terms=[
            {"term": bogus, "reachable": True, "evidence": _evidence(), "frame_refs": ["reset"]}
        ]
    )
    with pytest.raises(ValueError):
        validate_claims(claims)


def test_validate_claims_rejects_a_lever_outside_the_catalog():
    bogus = "vibes-based misdirection"
    assert bogus not in DECEPTION_CATALOG
    claims = _claims(deceptions=[{"lever": bogus, "evidence": _evidence(44)}])
    with pytest.raises(ValueError):
        validate_claims(claims)


def test_validate_claims_rejects_an_evidence_less_claim():
    claims = _claims(
        terms=[{"term": "move.grid", "reachable": True, "evidence": [], "frame_refs": []}]
    )
    with pytest.raises(ValueError):
        validate_claims(claims)


def test_validate_claims_accepts_the_real_catalog_keywords():
    for lever in DECEPTION_CATALOG:
        validate_claims(_claims(deceptions=[{"lever": lever, "evidence": _evidence(44)}]))


# --------------------------------------------------------------------------- #
# group 7 — the diff and the verdict
# --------------------------------------------------------------------------- #


def _spec(terms=PILOT_TERMS, deceptions=()) -> dict:
    """The real parsed spec.yaml shape (top-level `game:`), pilot values."""
    return {
        "game": {
            "slug": "fogbound-switchyard",
            "title": "Fogbound Switchyard",
            "idea_ref": "b001-pilot-i001",
            "terms": list(terms),
            "objective": {"primary": "cover_targets", "secondary": None},
            "locus": "selection",
            "knobs": {
                "refusal": "free",
                "goal_legible": "inferable",
                "danger_tell": "none",
                "deceptions": list(deceptions),
            },
        }
    }


def _term_claim(term: str, reachable: bool = True) -> dict:
    return {
        "term": term,
        "reachable": reachable,
        "evidence": _evidence(120),
        "frame_refs": ["reset"],
    }


def _spec_claims(terms=PILOT_TERMS, *, deceptions=(), unreachable=()) -> dict:
    entries = [_term_claim(t) for t in terms]
    entries += [_term_claim(t, reachable=False) for t in unreachable]
    return _claims(
        terms=entries,
        deceptions=[{"lever": lever, "evidence": _evidence(44)} for lever in deceptions],
    )


def _diff(**overrides) -> dict:
    """A hand-built diff with the frozen keys — the verdict tests never depend
    on compute_diff, so a diff bug and a verdict bug stay distinguishable."""
    diff = {key: [] for key in DIFF_KEYS}
    diff["terms_declared"] = list(PILOT_TERMS)
    diff["terms_detected_reachable"] = list(PILOT_TERMS)
    diff.update(overrides)
    return diff


def _passing_checks() -> list[CheckResult]:
    return [
        CheckResult(check_id=cid, leg="static", status="pass", evidence=(), note="ok")
        for cid in STATIC_IDS
    ] + [
        CheckResult(check_id=cid, leg="required", status="pass", evidence=(), note="ok")
        for cid in REQUIRED_IDS
    ]


def test_diff_has_exactly_the_frozen_keys():
    diff = compute_diff(_spec_claims(), _spec())
    assert sorted(diff) == sorted(DIFF_KEYS)
    assert all(isinstance(diff[key], list) for key in DIFF_KEYS)


def test_diff_is_clean_when_claims_match_the_spec():
    diff = compute_diff(_spec_claims(), _spec())
    assert sorted(diff["terms_declared"]) == sorted(PILOT_TERMS)
    assert sorted(diff["terms_detected_reachable"]) == sorted(PILOT_TERMS)
    for key in (
        "dead_spec_terms",
        "undeclared_terms",
        "unreachable_declared_mechanics",
        "undeclared_deceptions",
        "declared_deceptions_undetected",
    ):
        assert diff[key] == [], f"{key} should be empty on a clean game: {diff[key]!r}"


def test_diff_flags_a_term_the_code_has_and_the_spec_does_not():
    claims = _spec_claims(terms=(*PILOT_TERMS, "budget.cap"))
    diff = compute_diff(claims, _spec())
    assert diff["undeclared_terms"] == ["budget.cap"]
    assert diff["dead_spec_terms"] == []


def test_diff_flags_a_spec_term_the_code_never_implements():
    claims = _spec_claims(terms=[t for t in PILOT_TERMS if t != "gate.direct"])
    diff = compute_diff(claims, _spec())
    assert diff["dead_spec_terms"] == ["gate.direct"]
    assert diff["undeclared_terms"] == []
    assert diff["unreachable_declared_mechanics"] == []


def test_diff_flags_a_declared_mechanic_that_is_unreachable():
    claims = _spec_claims(
        terms=[t for t in PILOT_TERMS if t != "gate.direct"], unreachable=("gate.direct",)
    )
    diff = compute_diff(claims, _spec())
    assert diff["unreachable_declared_mechanics"] == ["gate.direct"]
    assert diff["dead_spec_terms"] == []


def test_diff_normalizes_deceptions_on_both_sides():
    """Catalog-keyword normalization (s1_spec._deception_pattern) both directions."""
    detected = compute_diff(_spec_claims(deceptions=("decoy",)), _spec(deceptions=["decoys"]))
    assert detected["undeclared_deceptions"] == []
    assert detected["declared_deceptions_undetected"] == []
    assert detected["deceptions_declared"] and detected["deceptions_detected"]

    undeclared = compute_diff(_spec_claims(deceptions=("palette overload",)), _spec())
    assert undeclared["undeclared_deceptions"], undeclared
    assert undeclared["declared_deceptions_undetected"] == []

    unseen = compute_diff(_spec_claims(), _spec(deceptions=["palette overload"]))
    assert unseen["declared_deceptions_undetected"], unseen
    assert unseen["undeclared_deceptions"] == []


def test_verdict_passes_on_a_clean_game():
    verdict, reasons = decide_verdict(_passing_checks(), _diff())
    assert verdict == "pass"
    assert reasons == []


def test_verdict_passes_a_dry_run_with_no_diff():
    verdict, reasons = decide_verdict(_passing_checks(), None)
    assert verdict == "pass" and reasons == []


@pytest.mark.parametrize("leg", ["static", "required"])
def test_verdict_rejects_a_failed_contract_check(leg):
    checks = _passing_checks()
    checks[0] = CheckResult(
        check_id=STATIC_IDS[0] if leg == "static" else REQUIRED_IDS[0],
        leg=leg,
        status="fail",
        evidence=(Evidence(kind="code", path="game.py", line=61, note="falls through"),),
        note="handler leaves without complete_action()",
    )
    verdict, reasons = decide_verdict(checks, _diff())
    assert verdict == "reject"
    assert [r["code"] for r in reasons] == ["forbidden-static"]
    assert reasons[0]["detail"].strip()


@pytest.mark.parametrize(
    "key,value,code",
    [
        ("undeclared_deceptions", ["palette overload"], "undeclared-deception"),
        ("dead_spec_terms", ["gate.direct"], "dead-spec-term"),
        ("undeclared_terms", ["budget.cap"], "undeclared-term"),
        ("unreachable_declared_mechanics", ["gate.direct"], "unreachable-declared-mechanic"),
    ],
)
def test_each_diff_reject_code_triggers_in_isolation(key, value, code):
    assert code in REJECT_CODES
    diff = _diff()
    diff[key] = value
    verdict, reasons = decide_verdict(_passing_checks(), diff)
    assert verdict == "reject"
    assert [r["code"] for r in reasons] == [code]
    assert reasons[0]["detail"].strip()


def test_solver_failure_rejects_and_routes_solver_only():
    checks = _passing_checks() + [
        CheckResult(
            check_id="solver.noop-prefix",
            leg="solver",
            status="fail",
            evidence=(Evidence(kind="frame", frame_label="step-1:ACTION1", note="identical"),),
            note="3 leading actions change nothing",
        )
    ]
    verdict, reasons = decide_verdict(checks, _diff())
    assert verdict == "reject"
    assert [r["code"] for r in reasons] == ["solver-quality"]
    assert reasons[0]["route"] == "solver-only", (
        "architecture §3: solver-quality failures route to S2 as solver-only fixes"
    )


def test_declared_but_undetected_deception_is_only_a_warning():
    """A possible verifier FN, human-reviewed at S5 — never a reject by itself."""
    diff = compute_diff(_spec_claims(), _spec(deceptions=["palette overload"]))
    assert diff["declared_deceptions_undetected"]
    verdict, reasons = decide_verdict(_passing_checks(), diff)
    assert verdict == "pass" and reasons == []


def test_a_non_fail_check_status_never_rejects():
    checks = _passing_checks()
    checks[1] = CheckResult(
        check_id=STATIC_IDS[1], leg="static", status="premise-not-met",
        evidence=(Evidence(kind="engine", note="no sys_click sprites"),), note="no clickables",
    )
    checks[2] = CheckResult(
        check_id=REQUIRED_IDS[2], leg="required", status="deferred",
        evidence=(), note="cap-fit needs S4 baselines",
    )
    verdict, reasons = decide_verdict(checks, _diff())
    assert verdict == "pass" and reasons == []


# --------------------------------------------------------------------------- #
# group 8 — the blind agent pass (fake driver)
# --------------------------------------------------------------------------- #


class _FakeDriver:
    """Stand-in for one verifier session: log the call, optionally edit cwd."""

    name = "localclaude"

    def __init__(self, reply: str, on_session=None) -> None:
        self.reply = reply
        self.calls: list[dict] = []
        self._on_session = on_session

    def session(self, prompt: str, **kwargs) -> SessionResult:
        self.calls.append({"prompt": prompt, **kwargs})
        if self._on_session is not None:
            self._on_session(Path(kwargs["cwd"]))
        return SessionResult(
            driver=self.name,
            model_requested=kwargs.get("model"),
            model_reported=kwargs.get("model"),
            text=self.reply,
            usd_cost=0.02,
            tokens_in=1200,
            tokens_out=800,
            duration_s=1.5,
            exit_code=0,
            session_id="fake-verifier-1",
            cmd=["claude", "-p", "<prompt>"],
            raw={},
        )


def _install_fake_driver(monkeypatch, driver: _FakeDriver, roles: list) -> None:
    """Patch BOTH binding sites: gen/ modules import get_driver inside functions."""

    def fake_get_driver(cfg, role=None):
        roles.append(role)
        return driver, "claude-opus-5"

    monkeypatch.setattr(backends, "get_driver", fake_get_driver)
    monkeypatch.setattr(s3_verify_mod, "get_driver", fake_get_driver, raising=False)


def _worker_with_spec(tmp_path: Path) -> Path:
    worker = _stage_worker(tmp_path / "worker", TOY)
    (worker / "spec.yaml").write_text("game:\n  slug: leaky\n", encoding="utf-8")
    (worker / "spec.md").write_text("# MARKER-B7-SPEC-MUST-NOT-LEAK\n", encoding="utf-8")
    (worker / "tests").mkdir()
    (worker / "tests/test_scaffold.py").write_text("# scaffold\n", encoding="utf-8")
    return worker


def test_staged_copy_excludes_every_spec_file(tmp_path):
    worker = _worker_with_spec(tmp_path)
    staged = tmp_path / "staged"
    tree_hash = stage_worker_copy(worker, staged)

    assert isinstance(tree_hash, str) and tree_hash.strip()
    leaked = [p.name for p in staged.rglob("spec*") if p.is_file()]
    assert leaked == [], f"the blind copy must carry no spec files, found {leaked}"
    assert (staged / "game.py").is_file() and (staged / "solver.py").is_file()
    assert (staged / "tests/test_scaffold.py").is_file(), "non-spec subtrees are copied"
    assert worker.resolve() != staged.resolve()
    assert (worker / "spec.yaml").is_file(), "staging must not touch the original worker"


def test_assert_unchanged_accepts_a_clean_copy_and_raises_on_drift(tmp_path):
    worker = _worker_with_spec(tmp_path)
    staged = tmp_path / "staged"
    tree_hash = stage_worker_copy(worker, staged)
    assert_unchanged(staged, tree_hash)  # no drift yet

    (staged / "game.py").write_text("# the session edited a read-only copy\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        assert_unchanged(staged, tree_hash)


def test_verifier_prompt_is_blind_and_carries_canon(cfg, tmp_path, toy_capture):
    worker = _worker_with_spec(tmp_path)
    staged = tmp_path / "staged"
    stage_worker_copy(worker, staged)

    prompt = build_verifier_prompt(cfg, toy_capture, staged)
    assert "MARKER-B7-SPEC-MUST-NOT-LEAK" not in prompt, "the verifier is BLIND to the spec"
    assert "move.grid" in prompt, "the 71-term vocabulary must be in the prompt"
    assert any(lever in prompt.lower() for lever in DECEPTION_CATALOG)
    assert "complete_action" in prompt, "the four FORBIDDEN contracts must be verbatim"
    hex_rows = [line for line in prompt.splitlines() if HEX_ROW_RE.match(line.strip())]
    assert "reset" in prompt and len(hex_rows) >= 64, "the frames digest must be included"


def test_run_agent_pass_with_a_fake_driver(cfg, tmp_path, toy_capture, monkeypatch):
    worker = _worker_with_spec(tmp_path)
    driver = _FakeDriver(_reply(_claims()))
    roles: list = []
    _install_fake_driver(monkeypatch, driver, roles)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    agent = run_agent_pass(cfg, worker, toy_capture, out_dir=out_dir)

    assert len(driver.calls) == 1
    call = driver.calls[0]
    assert roles == ["verifier"], f"the agent pass resolves models.verifier, got {roles!r}"
    session_cwd = Path(call["cwd"]).resolve()
    assert session_cwd != worker.resolve(), "the session must never run in the real worker"
    assert tuple(call.get("tools") or ()) == ("Read", "Glob", "Grep")
    assert tuple(call.get("allowed_tools") or ()) == ("Read", "Glob", "Grep")
    assert "MARKER-B7-SPEC-MUST-NOT-LEAK" not in call["prompt"]

    assert agent["staged_copy_verified"] is True
    assert agent["claims"] == _claims()
    assert agent["session_id"] == "fake-verifier-1"
    assert agent["model"] == "claude-opus-5"
    assert agent["tokens_in"] == 1200 and agent["tokens_out"] == 800
    assert agent["usd"] == pytest.approx(0.02)
    assert agent["wall_s"] >= 0


def test_run_agent_pass_raises_when_the_session_mutates_the_copy(
    cfg, tmp_path, toy_capture, monkeypatch
):
    worker = _worker_with_spec(tmp_path)

    def tamper(cwd: Path) -> None:
        (cwd / "game.py").write_text("# the agent wrote here\n", encoding="utf-8")

    driver = _FakeDriver(_reply(_claims()), on_session=tamper)
    _install_fake_driver(monkeypatch, driver, [])
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with pytest.raises(RuntimeError):
        run_agent_pass(cfg, worker, toy_capture, out_dir=out_dir)


def test_run_agent_pass_fails_loud_on_a_reply_with_no_claims(
    cfg, tmp_path, toy_capture, monkeypatch
):
    worker = _worker_with_spec(tmp_path)
    driver = _FakeDriver("I had a look around. Everything seems fine to me.")
    _install_fake_driver(monkeypatch, driver, [])
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with pytest.raises(ValueError):
        run_agent_pass(cfg, worker, toy_capture, out_dir=out_dir)


# --------------------------------------------------------------------------- #
# group 9 — the report
# --------------------------------------------------------------------------- #


def _checks_as_json() -> list[dict]:
    """CheckResults the way a written report holds them: JSON types only.

    `dataclasses.asdict` keeps `evidence` a TUPLE, which json.dump turns into a
    list — so the in-memory dict a validator sees after a round trip has lists.
    """
    return json.loads(json.dumps([asdict(c) for c in _passing_checks()]))


def _full_report(**overrides) -> dict:
    report = {
        "schema_version": "b7.1",
        "game_id": "toy-scaffold-01",
        "worker": str(TOY),
        "mode": "full",
        "canon": {"docs_root": str(REPO_ROOT / "canon"), "spec_hash": "a" * 64},
        "frames": {
            "source": "solver",
            "count": 4,
            "levels_completed": 2,
            "win": True,
            "path": "frames.json",
        },
        "checks": _checks_as_json(),
        "required_rows": [
            {"row": n, "check_id": f"required.row{n}", "status": "pass"} for n in range(1, 9)
        ],
        "agent": {
            "session_id": "fake-verifier-1",
            "model": "claude-opus-5",
            "usd": 0.02,
            "tokens_in": 1200,
            "tokens_out": 800,
            "wall_s": 1.5,
            "staged_copy_verified": True,
            "claims": _claims(),
        },
        "diff": _diff(),
        "verdict": "pass",
        "reject_reasons": [],
        "versions": {"arcengine": "0.9.3", "python": "3.12.0"},
    }
    report.update(overrides)
    return report


def _dry_run_report() -> dict:
    return _full_report(
        mode="dry-run",
        canon={"docs_root": str(REPO_ROOT / "canon"), "spec_hash": None},
        frames={
            "source": "probe",
            "count": 5,
            "levels_completed": 0,
            "win": False,
            "path": "frames.json",
        },
        agent=None,
        diff=None,
    )


def test_validate_report_accepts_a_full_report():
    validate_report(_full_report())


def test_validate_report_accepts_a_dry_run_report():
    validate_report(_dry_run_report())


@pytest.mark.parametrize("key", REPORT_KEYS)
def test_validate_report_rejects_a_missing_top_level_key(key):
    report = _full_report()
    del report[key]
    with pytest.raises(ValueError):
        validate_report(report)


def test_validate_report_rejects_an_unknown_top_level_key():
    report = _full_report()
    report["extra"] = 1
    with pytest.raises(ValueError):
        validate_report(report)


@pytest.mark.parametrize(
    "overrides",
    [
        {"verdict": "ok"},
        {"mode": "sandbox"},
        {"schema_version": "b7.0"},
        {"frames": {"source": "agent", "count": 4, "levels_completed": 2, "win": True,
                    "path": "frames.json"}},
    ],
    ids=["verdict", "mode", "schema_version", "frames.source"],
)
def test_validate_report_rejects_a_bad_enum(overrides):
    with pytest.raises(ValueError):
        validate_report(_full_report(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"checks": {}},
        {"required_rows": "eight"},
        {"reject_reasons": None},
        {"game_id": 17},
    ],
    ids=["checks", "required_rows", "reject_reasons", "game_id"],
)
def test_validate_report_rejects_a_wrong_type(overrides):
    with pytest.raises((ValueError, TypeError)):
        validate_report(_full_report(**overrides))


def test_validate_report_accepts_a_reject_report():
    """A reject is a valid report: the verdict enum carries it, not an error."""
    validate_report(
        _full_report(
            verdict="reject",
            reject_reasons=[
                {"code": "forbidden-static", "detail": "static.complete-action failed"}
            ],
        )
    )


def test_write_report_round_trips(tmp_path):
    report = _full_report()
    path = tmp_path / "verifier-report.json"
    write_report(report, path)
    assert path.is_file()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written == report
    validate_report(written)


# --------------------------------------------------------------------------- #
# group 10 — acceptance: the CLI dry run on one official
# --------------------------------------------------------------------------- #


def test_cli_dry_run_on_one_official(tmp_path):
    """`--official <slug> --dry-run` is THE acceptance path (B7 contract)."""
    out_dir = tmp_path / "verify-out"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "gen.s3_verify",
            "--config",
            PILOT_CONFIG,
            "--official",
            ACCEPTANCE_SLUG,
            "--dry-run",
            "--out",
            str(out_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, f"exit {proc.returncode}\n{proc.stdout}\n{proc.stderr}"

    reports = sorted(out_dir.rglob("verifier-report.json"))
    assert len(reports) == 1, f"expected one report under {out_dir}, found {reports}"
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    validate_report(report)

    assert report["mode"] == "dry-run"
    assert report["agent"] is None and report["diff"] is None
    assert report["canon"]["spec_hash"] is None
    assert report["frames"]["source"] == "probe"
    assert (reports[0].parent / "frames.json").is_file()
    assert [row for row in report["required_rows"] if row["status"] == "fail"] == []
    assert [c for c in report["checks"] if c["status"] == "fail"] == []
    assert report["verdict"] == "pass" and report["reject_reasons"] == []
