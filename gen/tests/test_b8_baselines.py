"""B8 acceptance: the S4 g-sampler + baseline fit (gen/s4_baselines.py).

Run: .venv/bin/python -m pytest gen/tests/test_b8_baselines.py -q

Written FROM THE B8 CONTRACT and from canon, never from the implementation:
`gen/s4_baselines.py` was built in parallel with this file by another agent
and none of its source was read. Every expectation below is either a name or
shape the contract froze, or a canon rule cited at its source:

  architecture.md §3 "S4 — baseline assigner"  — the 5-step algorithm and its
      ORDER (solver_i -> draw g -> reshape -> cap-fit -> batch band).
  decisions.md D7   — baseline_i = solver_i x g_i, g measured at median 2.00
      (IQR 1.54-2.96, n=183), reshaped to official statistics: non-monotonic,
      r(level, log b) ~ +0.65, floor >= 6, ~9x effort span.
  decisions.md D8   — the 5x-baseline per-level battery budget.
  decisions.md D9   — calibration is FLEET-level only: the batch band is
      recorded, never a per-game gate.
  decisions.md D22  — stage-4 is "D7 g-policy + the baselines-fit-in-game-caps
      hard check".
  spec-v0.3.md §2 REQUIRED row 3 — the budget triple the two fixtures
      implement (edge-anchored meter; exhaustion wired to lose() with the win
      check FIRST; the cap accommodates the line plus the g-margin).

CORPUS FACTS (B8 contract, re-verified here at data level in group 8): the
minimum baseline across all 25 officials' metadata.json is 6 (sc25), and 0 of
25 baseline vectors are nondecreasing — every one contains a strict descent.

FIXTURES — gen/tests/fixtures/s4_workers/, authored for this file, each one
engine-verified by the tests that drive it:
  capped_generous/  4 levels, solver 2/3/4/5, caps 120/180/240/300. Every cap
      is 2x the largest 5x-battery need (5 x 6 x solver_i), so cap-fit passes
      on the first draw for every seed: verdict fit, redraws 0.
  capped_tight/     4 levels, solver 2/3/4/5, caps 120/20/240/300. Level 2's
      cap of 20 sits between baseline_2 (<= 6 x 3 = 18, g is clipped at 6.0)
      and 5 x baseline_2 (>= 5 x 6 = 30, the floor), so `fits` is true,
      `battery_fits` is false, and no redraw can ever escape it.
  gen/tests/toy_worker/ is the third, read-only, case: no `lose(` anywhere, so
      every cap measures None and the cap-fit premise is not met.
Cost: the toy has no budget at all, so each cap probe burns BURN_BOUND actions
per candidate per level — a measured ~2.4 s per run_s4 on this machine, which
is why the toy appears in group 7 exactly as many times as the contract asks.

CONTRACT AMBIGUITIES this file had to take a position on (reported to the
lead, never invented quietly):
  A. break_monotonic's "swap ONE rng-chosen INTERIOR pair" cannot mean an
     adjacent pair strictly inside the endpoints at 3 levels (that needs 4),
     yet the contract makes the rule live from 3 levels up. These tests
     therefore assert only what every reading shares: the multiset survives,
     exactly two positions change and they are a transposition, and the
     result has a strict descent. Endpoint-preservation is NOT asserted.
  B. span_rescale and trend_nudge take no `floor` argument, but the contract's
     prose for both re-clamps "so its implied g stays in G_CLIP and >= floor".
     Only the clip half — derivable from the arguments they are given — is
     asserted here.
  C. Error types: the contract says "fail loud on missing/invalid keys" and
     house style is ValueError. A missing/mistyped config key is accepted as
     (KeyError, ValueError, TypeError); the explicit `q1 < median < q3`
     validation is required to be a ValueError.
  D. invariants.span_achieved / trend_achieved have no frozen type; only their
     presence is asserted.
  E. "premise-not-met" is a cap-fit STATUS with no frozen key (`verdict` is
     frozen to "fit"|"cap-fit-reject"), so the toy test asserts the literal
     string appears in the serialised s4-report.json.
  F. s4-report.json is "the full result dict + caps + band + seed + paths"
     with no frozen layout, and the same contract also requires the report to
     carry the cap probe's per-candidate outcomes — which makes `caps` richer
     than the flat `measure_caps` list. These tests therefore assert the
     SUBSTANCE through `_result_block` / `_cap_values` / `_report_seed`, which
     accept the result dict spread at top level or nested under a key, `caps`
     flat or as a block carrying the flat list, and the seed under `seed` or
     metadata.json's frozen `rng_seed`. The report's exact layout is NOT
     asserted, because the contract never froze it.
  G. write_actions(lines, out_dir) reads `out_dir` as the PARENT of
     `actions/`, matching run_s4's output layout.
  H. result["g"] is not specified as the raw draw or the implied post-reshape
     ratio; only its length/shape is asserted, and the clip checks recompute
     the implied g from baseline_actions and the solver lengths.
  I. The contract writes metadata.json "ONLY on verdict fit" and calls
     premise-not-met a cap-fit status, not a verdict; group 7 asserts
     metadata.json exists IFF verdict == "fit", which holds either way.
  J. capfit rows' `level` is read 1-indexed, like the frozen
     actions/level-<i>.json numbering and the contract's own `solver_i`.
  K. For a None cap the contract says the check is "vacuous, recorded"; the
     row is asserted to be present with cap None and neither flag False.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from arcengine import ActionInput, GameAction, GameState

from gen.config import REPO_ROOT, load_config
from gen.frames import _fresh_game, _perform, _reset
from gen.officials import discover_officials
from gen.s3_static import load_worker_classes
from gen.s4_baselines import (
    BATTERY_MARGIN,
    BURN_BOUND,
    G_CLIP,
    SCHEMA_VERSION,
    LineCapture,
    batch_band,
    break_monotonic,
    derive_seed,
    draw_baselines,
    fit_g,
    floor_bump,
    main,
    measure_caps,
    run_s4,
    solver_lines,
    span_rescale,
    trend_nudge,
    write_actions,
)

TESTS = Path(__file__).resolve().parent
TOY = TESTS / "toy_worker"
S4_WORKERS = TESTS / "fixtures/s4_workers"
GENEROUS = S4_WORKERS / "capped_generous"
TIGHT = S4_WORKERS / "capped_tight"
PILOT_CONFIG = "config/b001-pilot.yaml"

# The fixtures KNOW their own numbers — these are the header tables of
# fixtures/s4_workers/*/game.py and solver.py, and of toy_worker/solver.py.
# name -> (worker dir, solver actions per level, enforced cap per level)
FIXTURE_TABLE: dict[str, tuple[Path, tuple[int, ...], tuple[int | None, ...]]] = {
    "generous": (GENEROUS, (2, 3, 4, 5), (120, 180, 240, 300)),
    "tight": (TIGHT, (2, 3, 4, 5), (120, 20, 240, 300)),
    "toy": (TOY, (10, 10), (None, None)),
}
FIXTURE_NAMES = sorted(FIXTURE_TABLE)

# Phi^-1(0.75) — the frozen constant in the contract's sigma formula.
PHI_INV_075 = 0.6744897501960817
TOL = 1e-6

# Frozen dict shapes (B8 contract §"Semantics" step 5 / 6 / 8).
RESULT_KEYS = {"verdict", "baseline_actions", "g", "redraws", "attempts", "invariants"}
ATTEMPT_KEYS = {"attempt", "g", "baselines", "capfit", "ok"}
CAPFIT_KEYS = {"level", "solver", "baseline", "cap", "fits", "battery_fits"}
INVARIANT_KEYS = {"floor_ok", "has_strict_descent", "span_achieved", "trend_achieved"}
METADATA_KEYS = {
    "schema_version",
    "game_id",
    "baseline_actions",
    "g",
    "solver_actions",
    "caps",
    "rng_seed",
    "verdict",
    "provenance",
}
PROVENANCE_KEYS = {"g_config", "arcengine", "python"}
BAND_KEYS = {"median_g", "iqr_g", "config", "within"}

# A hand solver vector for the pure-draw groups: lengths varied enough that
# the 9x span target is representable inside the clip on every level.
DRAW_SOLVER = [4, 7, 5, 9]

# Collection-time discovery (test_officials_conformance.py's pattern): the
# officials parametrisation needs the corpus before any fixture runs.
_CFG = load_config(PILOT_CONFIG)
_OFFICIALS = discover_officials(_CFG)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _span(vector) -> float:
    return max(vector) / min(vector)


def _has_strict_descent(vector) -> bool:
    return any(vector[i] > vector[i + 1] for i in range(len(vector) - 1))


def _log_trend_r(vector) -> float:
    """Pearson r between the level index and ln(baseline) — D7's +0.65 stat."""
    xs = list(range(len(vector)))
    ys = [math.log(v) for v in vector]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    syy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sxy / (sxx * syy)


def _is_one_transposition(before, after) -> bool:
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    return (
        len(changed) == 2
        and after[changed[0]] == before[changed[1]]
        and after[changed[1]] == before[changed[0]]
    )


def _action_input(entry: dict) -> ActionInput:
    """One `actions/level-<i>.json` entry back into an engine action."""
    action = GameAction[f"ACTION{entry['id']}"]
    data = entry.get("data")
    return ActionInput(id=action, data=data) if data else ActionInput(id=action)


def _transition_sequence(per_level_counts) -> list[int]:
    """levels_completed after each action of a line with these level splits."""
    sequence: list[int] = []
    for index, count in enumerate(per_level_counts):
        sequence.extend([index] * (count - 1))
        sequence.append(index + 1)
    return sequence


def _result_block(report: dict) -> dict:
    """The draw result at the report's frozen path (ambiguity F, RESOLVED).

    Lead ruling at B8 integration: the shipped `b8.1` report layout is frozen
    — the draw result dict lives NESTED under `report["result"]`, the caps
    under `report["caps"]["values"]`, the seed at `report["rng_seed"]`. These
    helpers went from either-reading adapters to layout assertions; a report
    that moves a key now fails here.
    """
    result = report["result"]
    assert isinstance(result, dict), f"report['result'] must be a dict, got {type(result)}"
    assert RESULT_KEYS <= set(result), (
        f"report['result'] is missing frozen keys: {sorted(RESULT_KEYS - set(result))}"
    )
    return result


def _cap_values(report: dict) -> list:
    """The measured per-level caps at the frozen path `caps.values` (see above)."""
    caps = report["caps"]
    assert isinstance(caps, dict), f"report['caps'] must be a dict, got {type(caps)}"
    for key in ("status", "values", "bound", "battery_margin", "has_lose_call", "levels"):
        assert key in caps, f"report['caps'] is missing frozen key {key!r}: {sorted(caps)}"
    return list(caps["values"])


def _report_seed(report: dict) -> int:
    """The seed the run used, at the frozen path `rng_seed` (see above)."""
    assert "rng_seed" in report, f"report carries no rng_seed: {sorted(report)}"
    return report["rng_seed"]


def _bad_cfg(g_block: dict) -> dict:
    cfg = dict(_CFG)
    cfg["g"] = g_block
    return cfg


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "gen.s4_baselines", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def cfg() -> dict:
    return _CFG


@pytest.fixture(scope="session")
def lines():
    """Cached `solver_lines` per worker — the drive is deterministic."""
    cache: dict[str, LineCapture] = {}

    def _get(worker: Path) -> LineCapture:
        key = str(worker)
        if key not in cache:
            cache[key] = solver_lines(worker)
        return cache[key]

    return _get


@pytest.fixture(scope="session")
def s4_run(cfg, tmp_path_factory):
    """Cached `run_s4` per (worker, seed) — the toy's cap probe is expensive."""
    cache: dict[tuple[str, int | None], tuple[dict, Path]] = {}

    def _run(worker: Path, seed: int | None = None) -> tuple[dict, Path]:
        key = (str(worker), seed)
        if key not in cache:
            out_dir = tmp_path_factory.mktemp("s4") / worker.name
            cache[key] = (run_s4(worker, cfg, seed=seed, out_dir=out_dir), out_dir)
        return cache[key]

    return _run


# --------------------------------------------------------------------------- #
# frozen surface — the names and constants the contract fixed
# --------------------------------------------------------------------------- #


def test_module_constants_are_the_frozen_values():
    assert G_CLIP == (1.2, 6.0)  # architecture §3 S4 step 2: "clipped [1.2, 6]"
    assert BATTERY_MARGIN == 5  # D8
    assert BURN_BOUND == 2000
    assert SCHEMA_VERSION == "b8.1"


def test_frozen_callables_exist():
    for fn in (
        solver_lines,
        write_actions,
        measure_caps,
        fit_g,
        floor_bump,
        span_rescale,
        break_monotonic,
        trend_nudge,
        draw_baselines,
        batch_band,
        derive_seed,
        run_s4,
        main,
    ):
        assert callable(fn), fn


def test_line_capture_is_the_frozen_dataclass():
    assert dataclasses.is_dataclass(LineCapture)
    assert LineCapture.__dataclass_params__.frozen is True
    assert [f.name for f in dataclasses.fields(LineCapture)] == [
        "game_id",
        "per_level",
        "described",
        "win",
        "levels_completed",
    ]


# --------------------------------------------------------------------------- #
# group 1 — fit_g: the lognormal quartile fit from config
# --------------------------------------------------------------------------- #


def test_fit_g_mu_is_the_log_of_the_configured_median(cfg):
    mu, _sigma = fit_g(cfg)
    assert cfg["g"]["median"] == 2.00
    assert mu == pytest.approx(math.log(2.00), abs=1e-12)
    assert mu == pytest.approx(0.6931471805599453, abs=1e-12)


def test_fit_g_sigma_averages_the_two_quartile_halves(cfg):
    _mu, sigma = fit_g(cfg)
    median = cfg["g"]["median"]
    q1, q3 = cfg["g"]["iqr"]
    left = math.log(median) - math.log(q1)
    right = math.log(q3) - math.log(median)
    # The measured IQR is NOT symmetric around the median in log space; the
    # contract's fit averages the two halves. Prove the asymmetry is real, so
    # this test would catch a one-sided fit.
    assert left != pytest.approx(right, rel=1e-3)
    assert sigma == pytest.approx(((left + right) / 2) / PHI_INV_075, rel=1e-12)
    assert sigma == pytest.approx(0.4843712241145833, abs=1e-12)


@pytest.mark.parametrize(
    "g_block",
    [
        pytest.param({}, id="empty"),
        pytest.param({"iqr": [1.54, 2.96]}, id="no-median"),
        pytest.param({"median": 2.0}, id="no-iqr"),
        pytest.param({"median": 2.0, "iqr": [1.54]}, id="short-iqr"),
        pytest.param({"median": "two", "iqr": [1.54, 2.96]}, id="median-not-a-number"),
    ],
)
def test_fit_g_fails_loud_on_a_missing_or_mistyped_key(g_block):
    with pytest.raises((KeyError, ValueError, TypeError, IndexError)):
        fit_g(_bad_cfg(g_block))


@pytest.mark.parametrize(
    "g_block",
    [
        pytest.param({"median": 2.0, "iqr": [2.50, 2.96]}, id="q1-above-median"),
        pytest.param({"median": 2.0, "iqr": [2.00, 2.96]}, id="q1-equals-median"),
        pytest.param({"median": 2.0, "iqr": [1.54, 1.90]}, id="q3-below-median"),
        pytest.param({"median": 2.0, "iqr": [1.54, 2.00]}, id="q3-equals-median"),
        pytest.param({"median": 2.0, "iqr": [2.96, 1.54]}, id="iqr-reversed"),
        pytest.param({"median": 0.0, "iqr": [1.54, 2.96]}, id="median-zero"),
        pytest.param({"median": -2.0, "iqr": [-2.96, -1.54]}, id="negative"),
    ],
)
def test_fit_g_requires_q1_below_median_below_q3(g_block):
    with pytest.raises(ValueError):
        fit_g(_bad_cfg(g_block))


# --------------------------------------------------------------------------- #
# group 2 — the reshape helpers in isolation (architecture §3 S4 step 3)
# --------------------------------------------------------------------------- #


def test_floor_bump_clamps_to_the_floor():
    assert floor_bump([1.0, 6.0, 9.5, 0.25], 6) == pytest.approx([6.0, 6.0, 9.5, 6.0])


@pytest.mark.parametrize(
    "vector",
    [
        [1.0, 2.0, 3.0],
        [6.0, 6.0, 6.0, 6.0],
        [5.999, 6.001, 42.0],
        [120.0, 7.0, 0.1, 61.5],
    ],
)
def test_floor_bump_never_lowers_a_baseline(vector):
    out = floor_bump(list(vector), 6)
    assert len(out) == len(vector)
    assert all(o >= i for o, i in zip(out, vector))
    assert all(o >= 6 for o in out)


@pytest.mark.parametrize(
    "baselines, solver",
    [
        pytest.param([9.0, 12.0, 18.0], [3, 6, 12], id="span-2-below-target"),
        pytest.param([6.0, 9.0, 60.0], [3, 6, 12], id="span-10-above-target"),
        pytest.param([4.0, 12.0, 60.0], [3, 6, 12], id="span-15-above-target"),
        pytest.param([10.0, 10.0, 10.0, 10.0], [5, 5, 5, 5], id="span-1-clip-bound"),
        pytest.param([7.0, 30.0, 12.0, 20.0], [5, 5, 5, 5], id="unsorted"),
    ],
)
def test_span_rescale_moves_the_span_toward_the_target_without_crossing(baselines, solver):
    target = _CFG["g"]["span_target"]
    before = _span(baselines)
    out = span_rescale(list(baselines), list(solver), target, G_CLIP)
    assert len(out) == len(baselines)
    lo, hi = sorted((before, float(target)))
    assert lo - TOL <= _span(out) <= hi + TOL
    for value, solver_i in zip(out, solver):
        assert G_CLIP[0] - TOL <= value / solver_i <= G_CLIP[1] + TOL


def test_span_rescale_leaves_a_one_level_vector_alone():
    assert span_rescale([10.0], [4], 9, G_CLIP) == pytest.approx([10.0])


def test_span_rescale_stops_at_the_clip_when_the_target_is_unreachable():
    # Equal solver lengths cap the achievable span at G_CLIP[1]/G_CLIP[0] = 5.
    out = span_rescale([10.0, 10.0, 10.0, 10.0], [5, 5, 5, 5], 50, G_CLIP)
    assert _span(out) <= (G_CLIP[1] / G_CLIP[0]) + TOL
    for value in out:
        assert 6.0 - TOL <= value <= 30.0 + TOL


@pytest.mark.parametrize("seed", range(8))
def test_break_monotonic_swaps_one_pair_of_a_nondecreasing_vector(seed):
    before = [6.0, 10.0, 14.0, 20.0, 27.0]
    assert not _has_strict_descent(before)
    after = break_monotonic(list(before), random.Random(seed))
    assert sorted(after) == sorted(before)
    assert _is_one_transposition(before, after), (before, after)
    assert _has_strict_descent(after)


@pytest.mark.parametrize(
    "vector",
    [
        [6.0, 20.0, 14.0],
        [30.0, 6.0, 10.0, 8.0],
        [12.0, 11.0, 10.0, 9.0, 8.0],
    ],
)
def test_break_monotonic_leaves_a_vector_that_already_descends(vector):
    assert break_monotonic(list(vector), random.Random(0)) == pytest.approx(vector)


@pytest.mark.parametrize("vector", [[6.0], [6.0, 12.0], [12.0, 6.0]])
def test_break_monotonic_is_vacuous_below_three_levels(vector):
    assert break_monotonic(list(vector), random.Random(0)) == pytest.approx(vector)


def test_break_monotonic_is_deterministic_in_its_rng():
    vector = [6.0, 10.0, 14.0, 20.0, 27.0, 33.0]
    first = break_monotonic(list(vector), random.Random(7))
    second = break_monotonic(list(vector), random.Random(7))
    assert first == pytest.approx(second)


def test_break_monotonic_picks_the_pair_with_the_rng():
    vector = [6.0, 10.0, 14.0, 20.0, 27.0, 33.0]
    seen = {tuple(break_monotonic(list(vector), random.Random(s))) for s in range(50)}
    assert len(seen) >= 2, seen


@pytest.mark.parametrize(
    "baselines, solver",
    [
        pytest.param([20.0, 14.0, 10.0, 7.0], [5, 5, 5, 5], id="r-negative"),
        pytest.param([6.0, 10.0, 18.0, 30.0], [5, 5, 5, 5], id="r-positive"),
        pytest.param([18.0, 7.0, 25.0, 12.0], [5, 5, 5, 5], id="r-near-zero"),
        pytest.param([9.0, 8.0, 30.0, 7.0, 24.0], [4, 4, 5, 6, 8], id="mixed-solver"),
    ],
)
def test_trend_nudge_moves_r_toward_the_target_and_never_past_it(baselines, solver):
    target = _CFG["g"]["trend"]
    before = _log_trend_r(baselines)
    out = trend_nudge(list(baselines), list(solver), target, G_CLIP)
    assert len(out) == len(baselines)
    lo, hi = sorted((before, float(target)))
    assert lo - TOL <= _log_trend_r(out) <= hi + TOL
    for value, solver_i in zip(out, solver):
        assert G_CLIP[0] - TOL <= value / solver_i <= G_CLIP[1] + TOL


def test_trend_nudge_direction_is_testable():
    """From r ~ -1 with clip headroom both ways, the tilt must actually move r."""
    baselines = [20.0, 14.0, 10.0, 7.0]
    solver = [5, 5, 5, 5]
    before = _log_trend_r(baselines)
    after = _log_trend_r(trend_nudge(list(baselines), list(solver), 0.65, G_CLIP))
    assert before < 0
    assert after > before


# --------------------------------------------------------------------------- #
# group 3 — draw_baselines invariants over many seeds
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed", range(60))
def test_draw_baselines_invariants(cfg, seed):
    solver = list(DRAW_SOLVER)
    result = draw_baselines(solver, [None] * len(solver), cfg, seed)

    assert set(result) == RESULT_KEYS
    assert result["verdict"] == "fit"
    assert result["redraws"] == 0

    baselines = result["baseline_actions"]
    assert isinstance(baselines, list) and len(baselines) == len(solver)
    assert all(isinstance(b, int) and not isinstance(b, bool) for b in baselines)

    # D7 floor >= 6 (the corpus minimum, sc25).
    floor = cfg["g"]["floor"]
    assert floor == 6
    assert all(b >= floor for b in baselines)

    # Implied g inside the clip. Integerisation can move a baseline by up to
    # 0.5 of an action, which is 0.5/solver_i of an implied g — allowed for.
    for baseline, solver_i in zip(baselines, solver):
        implied = baseline / solver_i
        assert G_CLIP[0] - 0.5 / solver_i - TOL <= implied
        assert implied <= G_CLIP[1] + 0.5 / solver_i + TOL

    # D7 non-monotonic: officials are 0/25 nondecreasing.
    assert _has_strict_descent(baselines), baselines

    invariants = result["invariants"]
    assert set(invariants) == INVARIANT_KEYS
    assert invariants["floor_ok"] is True
    assert invariants["has_strict_descent"] is True

    assert isinstance(result["g"], list) and len(result["g"]) == len(solver)
    assert all(isinstance(value, float) for value in result["g"])

    assert len(result["attempts"]) == 1
    for attempt in result["attempts"]:
        assert set(attempt) == ATTEMPT_KEYS
        assert len(attempt["capfit"]) == len(solver)
        for row in attempt["capfit"]:
            assert set(row) == CAPFIT_KEYS


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 1234])
def test_draw_baselines_is_deterministic(cfg, seed):
    first = draw_baselines(list(DRAW_SOLVER), [None] * 4, cfg, seed)
    second = draw_baselines(list(DRAW_SOLVER), [None] * 4, cfg, seed)
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_draw_baselines_varies_with_the_seed(cfg):
    seen = {
        tuple(draw_baselines(list(DRAW_SOLVER), [None] * 4, cfg, seed)["baseline_actions"])
        for seed in range(30)
    }
    assert len(seen) > 1


def test_draw_baselines_records_the_monotonic_rule_as_vacuous_below_three_levels(cfg):
    result = draw_baselines([4, 7], [None, None], cfg, 3)
    assert result["invariants"]["has_strict_descent"] == "vacuous"
    assert result["verdict"] == "fit"


# --------------------------------------------------------------------------- #
# group 4 — solver_lines + write_actions (architecture §3 S4 step 1)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_solver_lines_wins_and_splits_by_level(lines, name):
    worker, solver_counts, _caps = FIXTURE_TABLE[name]
    capture = lines(worker)

    assert capture.win is True
    assert capture.levels_completed == len(solver_counts)
    assert len(capture.per_level) == len(solver_counts)
    assert tuple(len(level) for level in capture.per_level) == solver_counts
    assert all(len(level) >= 1 for level in capture.per_level)
    assert sum(len(level) for level in capture.per_level) == sum(solver_counts)

    assert tuple(len(level) for level in capture.described) == solver_counts
    for level in capture.described:
        for described in level:
            assert isinstance(described, str) and described.startswith("ACTION")

    game_cls, _solver_cls = load_worker_classes(worker)
    assert capture.game_id == _fresh_game(game_cls).game_id


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_solver_lines_actions_are_replayable_records(lines, name):
    worker, _solver_counts, _caps = FIXTURE_TABLE[name]
    capture = lines(worker)
    for level in capture.per_level:
        for action in level:
            assert set(action) == {"id", "data"}
            assert isinstance(action["id"], int) and not isinstance(action["id"], bool)
            assert action["id"] != GameAction.RESET.value
            assert action["data"] is None or isinstance(action["data"], dict)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_solver_lines_refuses_a_line_that_does_not_win(name):
    """D11 / spec §2 row 4: baselines exist only for a WINNING line."""
    worker, solver_counts, _caps = FIXTURE_TABLE[name]
    with pytest.raises(ValueError):
        solver_lines(worker, max_actions=sum(solver_counts) - 1)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_actions_files_replay_to_the_same_transition_sequence(lines, tmp_path, name):
    worker, solver_counts, _caps = FIXTURE_TABLE[name]
    capture = lines(worker)

    written = write_actions(capture, tmp_path)
    expected_paths = [
        tmp_path / "actions" / f"level-{i}.json" for i in range(1, len(solver_counts) + 1)
    ]
    assert [Path(p) for p in written] == expected_paths

    payloads = []
    for index, path in enumerate(expected_paths):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, list)
        assert len(payload) == solver_counts[index]
        assert payload == [dict(a) for a in capture.per_level[index]]
        payloads.append(payload)

    game_cls, _solver_cls = load_worker_classes(worker)
    game = _fresh_game(game_cls)
    fd = _reset(game)
    seen = []
    for payload in payloads:
        for entry in payload:
            fd = _perform(game, _action_input(entry))
            seen.append(int(fd.levels_completed))

    assert fd.state is GameState.WIN
    assert seen == _transition_sequence(solver_counts)


# --------------------------------------------------------------------------- #
# group 5 — measure_caps against the authored budgets
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_measure_caps_recovers_the_authored_budget(lines, name):
    worker, _solver_counts, caps = FIXTURE_TABLE[name]
    assert tuple(measure_caps(worker, lines(worker))) == caps


def test_the_toy_worker_never_calls_lose(s4_run):
    """The premise of the cap-fit check: no budget wired at all."""
    assert "lose(" not in (TOY / "game.py").read_text(encoding="utf-8")
    report, _out_dir = s4_run(TOY, 0)
    assert _cap_values(report) == [None, None]
    assert "premise-not-met" in json.dumps(report), json.dumps(report)[:2000]


@pytest.mark.parametrize("name", ["generous", "tight"])
def test_fixture_wires_exhaustion_to_lose_with_the_win_check_first(name):
    """spec §2 REQUIRED row 3, the 25/25 pattern: the winning move is free.

    Level 1 of both fixtures is a cap of 120 and a 2-action line. Burn 118,
    then walk the line: the 120th (cap-th) action either lands on the goal —
    and must WIN the level, not lose the game — or misses it and must lose.
    """
    worker, solver_counts, caps = FIXTURE_TABLE[name]
    cap = caps[0]
    assert (cap, solver_counts[0]) == (120, 2)
    game_cls, _solver_cls = load_worker_classes(worker)
    burn = ActionInput(id=GameAction.ACTION1)
    step = ActionInput(id=GameAction.ACTION4)

    game = _fresh_game(game_cls)
    fd = _reset(game)
    for _ in range(cap - 2):
        fd = _perform(game, burn)
    fd = _perform(game, step)
    assert fd.state is GameState.NOT_FINISHED and int(fd.levels_completed) == 0
    fd = _perform(game, step)  # the cap-th action, and it wins the level
    assert fd.state is not GameState.GAME_OVER
    assert int(fd.levels_completed) == 1

    game = _fresh_game(game_cls)
    fd = _reset(game)
    for _ in range(cap - 1):
        fd = _perform(game, burn)
    assert fd.state is GameState.NOT_FINISHED
    fd = _perform(game, step)  # the cap-th action, and it does not win
    assert fd.state is GameState.GAME_OVER
    assert int(fd.levels_completed) == 0


# --------------------------------------------------------------------------- #
# group 6 — the hard cap-fit check (architecture §3 S4 step 4 + D8)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed", range(20))
def test_generous_caps_fit_on_the_first_attempt(cfg, seed):
    _worker, solver_counts, caps = FIXTURE_TABLE["generous"]
    result = draw_baselines(list(solver_counts), list(caps), cfg, seed)
    assert result["verdict"] == "fit"
    assert result["redraws"] == 0
    assert len(result["attempts"]) == 1
    attempt = result["attempts"][0]
    assert attempt["ok"] is True
    for row in attempt["capfit"]:
        assert row["fits"] is True
        assert row["battery_fits"] is True
        assert row["baseline"] <= row["cap"]
        assert BATTERY_MARGIN * row["baseline"] <= row["cap"]


@pytest.mark.parametrize("seed", range(20))
def test_tight_cap_rejects_after_exhausting_the_redraws(cfg, seed):
    _worker, solver_counts, caps = FIXTURE_TABLE["tight"]
    redraw_cap = cfg["g"]["redraw_cap"]
    assert redraw_cap == 3
    result = draw_baselines(list(solver_counts), list(caps), cfg, seed)

    assert result["verdict"] == "cap-fit-reject"
    assert result["redraws"] == redraw_cap
    assert len(result["attempts"]) == redraw_cap + 1
    assert result["baseline_actions"] is None
    assert result["g"] is None

    for index, attempt in enumerate(result["attempts"]):
        assert attempt["ok"] is False
        assert attempt["attempt"] == index
        assert len(attempt["baselines"]) == len(solver_counts)
        rows = {row["level"]: row for row in attempt["capfit"]}
        assert sorted(rows) == [1, 2, 3, 4]  # 1-indexed, like actions/level-<i>.json
        assert [row["cap"] for row in attempt["capfit"]] == list(caps)
        assert [row["solver"] for row in attempt["capfit"]] == list(solver_counts)
        # the failing level's numbers are recorded, not just a flag
        failing = [row for row in attempt["capfit"] if not row["battery_fits"]]
        assert [row["level"] for row in failing] == [2]
        assert failing[0]["cap"] == 20 and failing[0]["solver"] == 3
        assert BATTERY_MARGIN * failing[0]["baseline"] > failing[0]["cap"]


@pytest.mark.parametrize("seed", range(20))
def test_the_battery_margin_half_is_hard_on_its_own(cfg, seed):
    """Level 2's cap sits BETWEEN baseline and 5 x baseline: `fits` stays true
    and only `battery_fits` fails — and the game is rejected anyway (D8: a cap
    that truncates the battery budget corrupts the measurement)."""
    _worker, solver_counts, caps = FIXTURE_TABLE["tight"]
    result = draw_baselines(list(solver_counts), list(caps), cfg, seed)
    for attempt in result["attempts"]:
        row = next(r for r in attempt["capfit"] if r["level"] == 2)
        assert row["baseline"] <= row["cap"] == 20
        assert row["fits"] is True
        assert row["battery_fits"] is False
        others = [r for r in attempt["capfit"] if r["level"] != 2]
        assert all(r["fits"] is True and r["battery_fits"] is True for r in others)
    assert result["verdict"] == "cap-fit-reject"


def test_none_caps_are_vacuous_but_still_recorded(cfg):
    result = draw_baselines(list(DRAW_SOLVER), [None] * 4, cfg, 5)
    assert result["verdict"] == "fit"
    rows = result["attempts"][0]["capfit"]
    assert len(rows) == 4
    for row in rows:
        assert row["cap"] is None
        assert row["fits"] is not False
        assert row["battery_fits"] is not False


def test_run_s4_routes_the_two_fixtures_to_their_verdicts(s4_run):
    fit_report, fit_out = s4_run(GENEROUS, 0)
    assert fit_report["verdict"] == "fit"
    assert _result_block(fit_report)["redraws"] == 0
    assert _cap_values(fit_report) == list(FIXTURE_TABLE["generous"][2])
    assert (fit_out / "metadata.json").is_file()

    reject_report, reject_out = s4_run(TIGHT, 0)
    assert reject_report["verdict"] == "cap-fit-reject"
    assert _result_block(reject_report)["redraws"] == 3
    assert _cap_values(reject_report) == list(FIXTURE_TABLE["tight"][2])
    assert not (reject_out / "metadata.json").exists()
    # actions files are facts and land on both paths
    for i in range(1, 5):
        assert (reject_out / "actions" / f"level-{i}.json").is_file()
    assert (reject_out / "s4-report.json").is_file()


# --------------------------------------------------------------------------- #
# group 7 — determinism and the acceptance artefacts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed", [0, 1, 17, 99, 2026])
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_run_s4_twice_at_one_seed_is_byte_identical(cfg, tmp_path, name, seed):
    worker, solver_counts, _caps = FIXTURE_TABLE[name]
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first = run_s4(worker, cfg, seed=seed, out_dir=first_dir)
    second = run_s4(worker, cfg, seed=seed, out_dir=second_dir)

    assert first["verdict"] == second["verdict"]
    for i in range(1, len(solver_counts) + 1):
        relative = Path("actions") / f"level-{i}.json"
        assert (first_dir / relative).read_bytes() == (second_dir / relative).read_bytes()

    metadata = first_dir / "metadata.json"
    assert metadata.is_file() is (first["verdict"] == "fit")
    if first["verdict"] == "fit":
        assert metadata.read_bytes() == (second_dir / "metadata.json").read_bytes()


def test_metadata_is_official_shaped(s4_run):
    _report, out_dir = s4_run(GENEROUS, 7)
    metadata = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))

    assert set(metadata) == METADATA_KEYS
    assert metadata["schema_version"] == SCHEMA_VERSION
    assert metadata["verdict"] == "fit"
    assert metadata["rng_seed"] == 7
    assert metadata["solver_actions"] == list(FIXTURE_TABLE["generous"][1])
    assert metadata["caps"] == list(FIXTURE_TABLE["generous"][2])
    assert isinstance(metadata["game_id"], str) and metadata["game_id"]

    baselines = metadata["baseline_actions"]
    assert isinstance(baselines, list) and len(baselines) == 4
    assert all(isinstance(b, int) and not isinstance(b, bool) for b in baselines)
    assert min(baselines) >= 6
    assert _has_strict_descent(baselines)

    assert set(metadata["provenance"]) == PROVENANCE_KEYS


def test_the_report_carries_caps_band_seed_and_paths(s4_run):
    report, out_dir = s4_run(GENEROUS, 7)
    result = _result_block(report)
    assert set(result) == RESULT_KEYS
    assert result["verdict"] == "fit"
    assert _cap_values(report) == list(FIXTURE_TABLE["generous"][2])
    assert _report_seed(report) == 7
    assert set(report["band"]) == BAND_KEYS
    assert "paths" in report
    written = json.loads((out_dir / "s4-report.json").read_text(encoding="utf-8"))
    assert written == report


def test_derive_seed_is_the_frozen_sha256_rule(cfg):
    game_id = "s4-capped-generous"
    digest = hashlib.sha256(f"{cfg['batch']['seed']}:{game_id}:s4".encode()).hexdigest()
    assert derive_seed(cfg, game_id) == int(digest[:8], 16)
    assert derive_seed(cfg, game_id) != derive_seed(cfg, "s4-capped-tight")


def test_run_s4_without_a_seed_derives_one(cfg, tmp_path):
    report = run_s4(GENEROUS, cfg, out_dir=tmp_path)
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert _report_seed(report) == derive_seed(cfg, metadata["game_id"])
    assert metadata["rng_seed"] == _report_seed(report)


# --------------------------------------------------------------------------- #
# group 8 — officials calibration, data level only (no S4 run)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("official", _OFFICIALS, ids=[o.slug for o in _OFFICIALS])
def test_official_baseline_vector_matches_the_corpus_facts(official):
    vector = official.metadata["baseline_actions"]
    assert isinstance(vector, list) and len(vector) >= 3
    assert all(isinstance(v, int) and not isinstance(v, bool) for v in vector)
    assert min(vector) >= _CFG["g"]["floor"], f"{official.slug}: {vector}"
    assert _has_strict_descent(vector), f"{official.slug} is nondecreasing: {vector}"


def test_the_corpus_minimum_baseline_is_the_configured_floor():
    minima = {o.slug: min(o.metadata["baseline_actions"]) for o in _OFFICIALS}
    assert len(minima) == 25
    assert _CFG["g"]["floor"] == 6
    assert min(minima.values()) == 6
    assert sorted(slug for slug, m in minima.items() if m == 6) == ["sc25"]


def test_no_official_baseline_vector_is_nondecreasing():
    nondecreasing = [
        o.slug for o in _OFFICIALS if not _has_strict_descent(o.metadata["baseline_actions"])
    ]
    assert nondecreasing == []


# --------------------------------------------------------------------------- #
# group 9 — the batch band is RECORDED, never a gate (D9)
# --------------------------------------------------------------------------- #


def test_batch_band_records_the_fleet_statistics(cfg):
    band = batch_band([[2.0, 2.0, 2.0, 2.0]], cfg)
    assert set(band) == BAND_KEYS
    assert band["median_g"] == pytest.approx(2.0)
    q1, q3 = band["iqr_g"]
    assert q1 <= q3
    assert set(band["within"]) == {"median", "iqr"}
    assert band["within"]["median"] is True
    assert isinstance(band["within"]["iqr"], bool)
    assert isinstance(band["config"], dict)


def test_batch_band_flags_a_batch_far_outside_the_configured_median(cfg):
    band = batch_band([[6.0, 6.0, 6.0, 6.0]], cfg)
    assert band["median_g"] == pytest.approx(6.0)
    assert band["within"]["median"] is False


def test_an_out_of_band_batch_never_changes_a_verdict(cfg):
    """D9: individual games are NEVER re-tuned; the band adjusts the NEXT
    batch's g-params, so no band outcome may reach a per-game verdict."""
    assert batch_band([[6.0] * 4], cfg)["within"]["median"] is False
    _worker, solver_counts, caps = FIXTURE_TABLE["generous"]
    result = draw_baselines(list(solver_counts), list(caps), cfg, 0)
    assert result["verdict"] == "fit"
    assert "band" not in result and "within" not in result


def test_the_report_records_the_band_beside_an_untouched_verdict(s4_run):
    report, _out_dir = s4_run(GENEROUS, 0)
    assert report["verdict"] == "fit"
    assert set(report["band"]) == BAND_KEYS
    assert isinstance(report["band"]["within"]["median"], bool)
    reject, _reject_dir = s4_run(TIGHT, 0)
    assert reject["verdict"] == "cap-fit-reject"
    assert "band" in reject


# --------------------------------------------------------------------------- #
# group 10 — the CLI end to end
# --------------------------------------------------------------------------- #


def test_cli_exits_zero_and_writes_metadata_for_the_generous_fixture(tmp_path):
    out_dir = tmp_path / "s4-out"
    proc = _cli(
        "--worker", str(GENEROUS),
        "--config", PILOT_CONFIG,
        "--out", str(out_dir),
        "--seed", "11",
    )
    assert proc.returncode == 0, f"exit {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert any(
        line.startswith("[s4]") for line in (proc.stdout + proc.stderr).splitlines()
    ), proc.stdout + proc.stderr

    report = json.loads((out_dir / "s4-report.json").read_text(encoding="utf-8"))
    assert report["verdict"] == "fit"
    metadata = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["rng_seed"] == 11
    assert metadata["verdict"] == "fit"
    for i in range(1, 5):
        assert (out_dir / "actions" / f"level-{i}.json").is_file()


def test_cli_exits_two_on_the_tight_fixture(tmp_path):
    out_dir = tmp_path / "s4-out"
    proc = _cli("--worker", str(TIGHT), "--config", PILOT_CONFIG, "--out", str(out_dir))
    assert proc.returncode == 2, f"exit {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert any(
        line.startswith("[s4]") for line in (proc.stdout + proc.stderr).splitlines()
    ), proc.stdout + proc.stderr

    report = json.loads((out_dir / "s4-report.json").read_text(encoding="utf-8"))
    assert report["verdict"] == "cap-fit-reject"
    assert not (out_dir / "metadata.json").exists()
    for i in range(1, 5):
        assert (out_dir / "actions" / f"level-{i}.json").is_file()


def test_cli_default_output_is_the_worker_sibling(tmp_path):
    """B3/B7 sibling rule: `<worker>.s4/`, never inside the worker."""
    worker = tmp_path / "capped_generous"
    shutil.copytree(GENEROUS, worker, ignore=shutil.ignore_patterns("__pycache__"))
    proc = _cli("--worker", str(worker), "--config", PILOT_CONFIG)
    assert proc.returncode == 0, f"exit {proc.returncode}\n{proc.stdout}\n{proc.stderr}"

    sibling = tmp_path / "capped_generous.s4"
    assert (sibling / "s4-report.json").is_file()
    assert (sibling / "metadata.json").is_file()
    assert (sibling / "actions" / "level-1.json").is_file()
    assert not (worker / "s4-report.json").exists()
    assert not (worker / "actions").exists()


# --------------------------------------------------------------------------- #
# lead-ruling tests (B8 integration): the flat-at-floor degenerate window
# --------------------------------------------------------------------------- #
# Agent A measured (400 seeds, recorded in gen/s4_baselines.py's docstring):
# a vector pinned flat at the floor admits no strict descent — the interior
# swap permutes equal values — at ~16% incidence for 3 levels x solver 2-4,
# and 0/400 at 6+ levels with official-shaped solver counts. The ruling:
# `invariants.has_strict_descent` RECORDS the truth rather than forcing a
# descent that would fake the corpus statistic. These tests pin both sides.


def test_flat_at_floor_records_no_descent_honestly(cfg):
    """Tiny solver counts CAN land flat at the floor; the record says so."""
    solver = [2, 2, 2]
    seen_false = []
    for seed in range(200):
        result = draw_baselines(solver, [None] * 3, cfg, seed)
        assert result["verdict"] == "fit"
        invariants = result["invariants"]
        assert invariants["floor_ok"] is True
        baselines = result["baseline_actions"]
        assert all(b >= cfg["g"]["floor"] for b in baselines)
        if invariants["has_strict_descent"] is False:
            seen_false.append((seed, baselines))
            # the documented shape: no descent means the vector is
            # nondecreasing (a permutation of equal values where it is flat)
            assert not _has_strict_descent(baselines)
    assert seen_false, (
        "expected the measured ~16% flat-at-floor incidence to appear at least "
        "once in 200 seeds for solver [2,2,2]; the degenerate window has moved"
    )


@pytest.mark.parametrize("seed", range(100))
def test_official_shaped_draws_always_have_a_descent(cfg, seed):
    """At official-shaped level counts and solver sizes the descent always
    lands (agent A measured 0/400 misses at 6 and 10 levels; this pins it)."""
    solver = [8, 12, 20, 30, 45, 60]
    result = draw_baselines(solver, [None] * len(solver), cfg, seed)
    assert result["verdict"] == "fit"
    assert result["invariants"]["has_strict_descent"] is True
    assert _has_strict_descent(result["baseline_actions"])
