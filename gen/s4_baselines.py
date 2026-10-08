"""S4 — the baseline assigner: g-sampler + hard cap-fit (B8).

Canon: `design/architecture.md` §3 "S4 — baseline assigner", whose five-step
algorithm is the law of this module IN ITS STATED ORDER —

  1. `solver_i` = length of `actions/level-i.json` (the solver's real line,
     lag flushes and confirm actions included: they are part of the line).
  2. draw `g_i` from the measured lognormal (median 2.00, IQR 1.54-2.96,
     n=183), clipped [1.2, 6]  (D7; `design/difficulty-model.md` §2.1).
  3. reshape to official statistics: floor `baseline_i >= 6` · ~9x span ·
     non-monotonic (swap one rng-chosen interior pair when sorted ascending)
     · nudge toward the +0.65 log-trend.
  4. cap-fit (HARD): `baseline_i <= cap_i` with the 5x battery margin
     playable (D8, D22); violation → redraw (<= `g.redraw_cap`) then reject
     to S2 as a cap bug. `g.cap_fit: record` (b002 ruling, operator 2026-09-24)
     keeps the measurement and drops the reject — see `_cap_fit_mode`.
  5. batch band check — fleet-level ONLY (D9): recorded here, never a
     per-game gate. ICC(1) on the play ratio is -0.024 at 183 levels; the
     game explains none of it, so a single game is never re-tuned.

Two rulings this module encodes beyond the bare algorithm text:

* BOTH halves of step 4 are hard (lead ruling, flagged in the approved B8
  plan): `baseline_i <= cap_i` AND `5 * baseline_i <= cap_i`. A game cap that
  truncates the 5x battery budget corrupts B9's measurements, which is the
  same defect class spec §2 row 3 names ("never a tn36-style baseline>cap").
* Baselines exist only for a WINNING solver line (spec §2 row 4: "the goal
  state is game-checkable (win predicate; solver reaches it — D11)"). A
  truncated or losing drive is refused, never silently baselined.

R-05 / R-22 (refinement wave 3) add ONE knob and one unconditional honesty fix:

* `caps.basis: legacy | official-band` (`_caps_basis`). `legacy` is the DEFAULT
  and is byte-for-byte the stage above. `official-band` clips the draw to the
  officials' MEASURED effort band instead of canon's `[1.2, 6]` g clip, and
  records the per-level cap that band implies (`caps_band_block`). The measured
  cap stays the cap-fit reference in both: S4 measures the enforced budget, it
  cannot set it.
* "no measurable cap on any level" is a LOUD recorded condition, never the
  silent pass it was — see `CAPS_UNMEASURED` and `run_s4`.

I-1 (operator 2026-10-06, "Fix both (one small contract)") adds two more knobs and
moves NO default — the house rule: a config that sets neither is byte-for-byte
the stage above.

* `g.centering: d7-replay | effort-blind` (`_g_centering`, `G_INSTRUMENTS`):
  which officials-instrument the g statistic is centred on. The I-1
  adjudication names D7 (`G_CENTERING_ADJUDICATED`). An S4 `solver_i` is a
  solution-known WINNING line split per level by replay through our engine,
  which is exactly the denominator of D7's `baseline / replay_actions`;
  effort.csv divides the same baselines by a FIRST-CONTACT human play, which
  carries a discovery premium (median 1.4375x over the full 183-level join) no
  solver line contains. D7's centre is the centre every batch has been drawn
  at, so `d7-replay` moves no draw under the legacy box; what it re-centres is
  the official-band box and band record, which R-05/R-22 built on effort.csv.
  `effort-blind` is the named alternative — the audit's 2.00 -> 1.267 proposal
  and today's official-band surface — kept for comparability.
* `caps.probe: burn | allowance` (`_caps_probe`): `burn` is the pre-I-1 probe
  and the default. It reports the first repeated action's GAME_OVER count,
  i.e. death-by-repetition — a different phenomenon from the one `budget.cap`
  bounds (shipped exhibits: convoy and core-ward recorded "caps" of 4-38, below
  their own winning solver lines; lantern, seamlock, tidegate and conduit
  recorded none, because a repeated blocked move is free). `allowance` measures
  what `budget.cap` bounds — the in-level action count at which the game ends a
  play WHATEVER is played (`_level_allowance`) — and the burn figure rides
  beside it, labelled, for one release (`LEGACY_BURN_KEY`).

The caps are MEASURED, not declared: the stage replays the solver prefix to
each level's start and burns a deterministic in-level action until the game's
own budget kills it (the default burn probe; I-1's `caps.probe: allowance`
replaces the burn with the attributed allowance probe, `_level_allowance`). What that measures is the cap ACTUALLY ENFORCED in play
(for a globally budgeted game, the budget remaining at that level's start
given the prefix — which is the cap in play there; documented, not
special-cased). A game with no `lose()` call at all has no budget to measure,
so the cap-fit premise is not met — budget REQUIREDness is S1's and S2b row
3's gate, not S4's.

`g` in the result and in `metadata.json` is the IMPLIED ratio of the SHIPPED
integer baselines (`baseline_actions[i] / solver_actions[i]`), not the raw
draw: the reshape moves the draw, and a metadata whose `g` disagreed with its
own `baseline_actions` would be a provenance lie. The raw draw is recoverable
from `rng_seed` + the recorded `(mu, sigma)` — the whole stage is pure and
deterministic given the seed.

CLI:
  python -m gen.s4_baselines --worker out/workers/w001
  python -m gen.s4_baselines --worker gen/tests/toy_worker --seed 7 --out /tmp/s4
Exit 0 = verdict fit, 2 = cap-fit-reject, 1 = crash. `run_s4_isolated` is the
same stage in a fresh interpreter (it drives this CLI with `--cfg-json`) and
reads the report back, so BOTH verdicts come home as a report, never an exit
code — see "process isolation" below.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import itertools
import json
import math
import platform
import random
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from arcengine import ActionInput, GameAction, GameState

from .config import REPO_ROOT, load_config
from .frames import (
    CENTRE_CLICK,
    TERMINAL_STATES,
    _fresh_game,
    _perform,
    _playable_action_ids,
    _reset,
    _stderr_tail,
    click_cells,
    describe_action,
    mouse,
    settled_grid,
)
from .s3_static import game_source_path, load_worker_classes

SCHEMA_VERSION = "b8.1"
DEFAULT_CONFIG = "config/b001-pilot.yaml"

# --- frozen constants, every one traced to canon ----------------------------

# architecture §3 S4 step 2: the drawn ratio is "clipped [1.2, 6]".
G_CLIP = (1.2, 6.0)

# D8 — the 5x-baseline budget convention, adopted from the public benchmark
# runner (519 of 590 death-levels at exactly 5.00x). Every battery we run
# budgets a level at 5x its baseline, so a cap below that is unplayable.
BATTERY_MARGIN = 5

# Give-up bound for the per-level burn probe. The largest baseline in the 25
# officials is 578 (dc22) and the smallest is 6 (sc25); 2000 identical actions
# on one level is ~3.5x the largest official baseline. A level still alive
# after that has no cap this probe can find, and the honest answer is
# "uncapped within the bound" rather than an invented number.
BURN_BOUND = 2000

# Phi^-1(0.75) — the standard-normal quartile used by the lognormal fit.
PHI_INV_075 = 0.6744897501960817

# A log-spread at or below this counts as FLAT. An exact `== 0` test loses to
# float rounding: `sum([ln 6] * 3) / 3` is not bit-identical to `ln 6`, which
# leaves a ~1e-16 "variance" that turns a genuinely flat vector into a
# meaningless correlation (measured: `_log_trend([6, 6, 6])` reported 0.0
# instead of undefined) and would let the span rescale amplify pure noise.
FLAT_LOG_EPS = 1e-12

# D9: the band is RECORDED at the pilot and judged by the R-protocol over a
# real batch. At n=1 game the sample is one game's levels, so the tolerance is
# deliberately generous — this number never changes a verdict.
BAND_TOLERANCE = 0.25

# --- R-05 / R-22: the officials' measured effort distribution ---------------
# Source: `audit/comparative/data/effort.csv` (READ-ONLY calibration input),
# recomputed by the comparative audit's M-2 track over the 25 officials'
# `features-level.csv`. `ratio = actions / baseline` on BOTH corpora — a real
# play's line against the published baseline; on our side `actions` is the S4
# solver line, so our ratio is exactly `1 / g`.
#
#   officials: median 0.789 over n=183 levels; per-GAME medians span
#              0.437 .. 1.084 over the 25 games
#   ours:      median 0.493 over n=43 levels; per-game 0.389 .. 0.735
#
# The audit's load-bearing caveat travels with these numbers: ours are machine
# solver traces, theirs are human plays, so the band is a distribution
# DIRECTION, never a value to hit (findings C4; R-22 Risk).
OFFICIAL_RATIO_MEDIAN = 0.789
OFFICIAL_RATIO_BAND = (0.437, 1.084)

# The same band read as an implied-g box, `g = 1 / ratio`. The upper ratio edge
# (1.084) inverts to g = 0.922 — a baseline BELOW the level's own optimal line.
# That is legal for the officials, whose `actions` is a HUMAN play that may
# overshoot a published baseline, and dishonest for us, whose `actions` is a
# machine optimum: a g below 1 ships a baseline no play of ours can meet. The
# floor is therefore held at 1.0 — the instrument-difference correction the
# audit's own caveat demands, and the one place this box is not a pure
# inversion of the band.
OFFICIAL_G_BOX = (max(1.0, 1.0 / OFFICIAL_RATIO_BAND[1]), 1.0 / OFFICIAL_RATIO_BAND[0])

# `caps.basis` — which cap policy S4 runs (R-05 §1). See `_caps_basis`.
CAPS_BASIS_LEGACY = "legacy"
CAPS_BASIS_OFFICIAL_BAND = "official-band"
CAPS_BASES = (CAPS_BASIS_LEGACY, CAPS_BASIS_OFFICIAL_BAND)
CAPS_BLOCK_KEY = "caps"
CAPS_BASIS_KEY = "basis"

# `caps.probe` — which cap measurement S4 runs (I-1). See `_caps_probe`.
CAPS_PROBE_KEY = "probe"
CAPS_PROBE_BURN = "burn"
CAPS_PROBE_ALLOWANCE = "allowance"
CAPS_PROBES = (CAPS_PROBE_BURN, CAPS_PROBE_ALLOWANCE)
# Every key the `caps:` block may carry; anything else is refused loudly.
CAPS_BLOCK_KEYS = (CAPS_BASIS_KEY, CAPS_PROBE_KEY)

# --- I-1: the officials-instruments the g statistic can be centred on -------
# Two instruments measure the SAME 183 official levels against the SAME
# published baselines (the (game, level, baseline) triples of the two files are
# identical — pinned, gen/tests/test_i1_instruments.py 2d) and disagree, because the play in the
# denominator differs:
#
#   D7     `baseline_actions / replay_actions` — the arcprize.org human
#          REFERENCE replay of each official (solution known, one human per
#          game), replayed through OUR arcengine with exact level splits, WIN
#          on 25/25. Source: duckWM `local-docs/arc-agi-3-agents/out/
#          replay-ratios.csv` (agent-difficulty.md §8; canon D7;
#          difficulty-model.md §2.1). Per level: median 2.00, IQR 1.54-2.96.
#   effort `actions / baseline` with `actions` = the BLIND first-contact play
#          of the games workstream (discovery mode, all fumbling counted;
#          features-schema.md: "blind actions taken"). Source:
#          `audit/comparative/data/effort.csv` (from duckWM features-level.csv).
#          Per level: median ratio 0.789, i.e. g = 1.267.
#
# THE ADJUDICATION (I-1 memo): the ruler for g is the instrument whose
# denominator is the same KIND of play as S4's `solver_i`. `solver_i` is the
# length of a solution-known winning line, split per level by replaying it
# through our engine (`solver_lines`) — D7's denominator, measured by D7's own
# procedure. effort.csv's denominator is a discovery play, which costs a
# median 1.4375x the solution-known replay of the same level (blind / replay
# over the full 183-level join, IQR 1.124-2.081): centring g on it asserts a
# discovery premium of 1.0 for a solver that knows the solution, and ships
# baselines ~37% tighter than the officials' own baseline-to-replay relation.
# The audit's own caveat said as much ("over-fitting to 0.789 calibrates
# against the wrong instrument", R-22 Risk). effort.csv stays the right ruler
# for what it measures — human first-contact effort — which S4 never sees.
G_CENTERING_KEY = "centering"
G_CENTERING_D7 = "d7-replay"
G_CENTERING_EFFORT = "effort-blind"
G_CENTERINGS = (G_CENTERING_D7, G_CENTERING_EFFORT)
G_CENTERING_ADJUDICATED = G_CENTERING_D7

# D7's statistic at canon precision (difficulty-model.md §2.1, spec-v0.3), and
# the per-GAME median g span — the construction effort.csv's 0.437-1.084 band
# uses, here on D7's own column: cd82 1.4375 .. lp85 3.9778 (4 dp, derived
# from the rows by `g_statistics`; pinned in gen/tests/test_i1_instruments.py).
D7_G_MEDIAN = 2.00
D7_G_IQR = (1.54, 2.96)
D7_GAME_G_BAND = (1.4375, 3.9778)
D7_SOURCE = "duckWM/local-docs/arc-agi-3-agents/out/replay-ratios.csv"
# effort.csv read as g (`baseline / actions`), 3 dp like its own ratio column.
EFFORT_G_MEDIAN = 1.267
EFFORT_G_IQR = (0.948, 1.858)
EFFORT_SOURCE = "audit/comparative/data/effort.csv"


@dataclass(frozen=True)
class GInstrument:
    """One officials-instrument, as the g statistic and as the ratio band.

    `median`/`iqr` are per-level g (`baseline / line`) and are what the draw is
    centred on; `g_box` is what `caps.basis: official-band` clips the draw to;
    `ratio_median`/`ratio_band` are the same instrument as `line / baseline`
    (effort.csv's quantity, and what `caps_band_block` judges against).
    """

    name: str
    label: str
    quantity: str
    source: str
    levels: int
    games: int
    median: float
    iqr: tuple[float, float]
    g_box: tuple[float, float]
    ratio_median: float
    ratio_band: tuple[float, float]
    adjudicated: bool


G_INSTRUMENTS: dict[str, GInstrument] = {
    G_CENTERING_D7: GInstrument(
        name=G_CENTERING_D7,
        label=(
            "ADJUDICATED (I-1): D7, baseline / competent human replay — the instrument "
            "whose denominator is a solution-known winning line, as S4's solver_i is; "
            "also the historical centre every batch to date was drawn at"
        ),
        quantity="baseline_actions / replay_actions (arcprize human reference replay)",
        source=D7_SOURCE,
        levels=183,
        games=25,
        median=D7_G_MEDIAN,
        iqr=D7_G_IQR,
        g_box=D7_GAME_G_BAND,
        ratio_median=1.0 / D7_G_MEDIAN,
        ratio_band=(1.0 / D7_GAME_G_BAND[1], 1.0 / D7_GAME_G_BAND[0]),
        adjudicated=True,
    ),
    G_CENTERING_EFFORT: GInstrument(
        name=G_CENTERING_EFFORT,
        label=(
            "NAMED ALTERNATIVE (not adjudicated): effort.csv, blind first-contact play / "
            "baseline — the audit's proposed 2.00 -> 1.267 re-centering and the instrument "
            "the R-05/R-22 official-band box was built on; kept for comparability"
        ),
        quantity="blind actions / baseline (first-contact discovery play)",
        source=EFFORT_SOURCE,
        levels=183,
        games=25,
        median=EFFORT_G_MEDIAN,
        iqr=EFFORT_G_IQR,
        g_box=OFFICIAL_G_BOX,
        ratio_median=OFFICIAL_RATIO_MEDIAN,
        ratio_band=OFFICIAL_RATIO_BAND,
        adjudicated=False,
    ),
}

# --- output layout (the B3/B7 sibling rule) ---------------------------------
# Never inside the worker: any file there trips the worker's own scaffold
# scope check and makes `make validate` green unreachable.
OUT_SUFFIX = ".s4"
ACTIONS_DIRNAME = "actions"
METADATA_NAME = "metadata.json"
REPORT_NAME = "s4-report.json"

# --- vocabulary -------------------------------------------------------------
VERDICT_FIT = "fit"
VERDICT_REJECT = "cap-fit-reject"
# `g.cap_fit` — the two modes of step 4's FINAL violation (b002 ruling, operator
# 2026-09-24). `hard` is canon and the default. `record` is a deviation from
# D8's hard gate, taken as a PILOT ruling: a hard reject permanently blocks a
# game the rest of the pipeline accepted, and budget calibration is a later
# optimisation pass, so the violation is measured and carried rather than
# fatal. The measurement itself is unchanged in both modes.
CAP_FIT_HARD = "hard"
CAP_FIT_RECORD = "record"
# R-22 §3: `reject` is an ALIAS of `hard`, added because R-22's own sentence is
# "move `g.cap_fit` from record to reject" and a config that says `reject`
# should not have to know that canon spells it `hard`. Same code path, same
# verdict, same bytes — the only difference is the word the report echoes.
CAP_FIT_REJECT = "reject"
CAP_FIT_MODES = (CAP_FIT_HARD, CAP_FIT_RECORD, CAP_FIT_REJECT)
CAP_FIT_KEY = "cap_fit"
# Both statuses come from the verifier's frozen status vocabulary
# (`gen/s3_static.STATUSES`), so S3 and S4 use one word for one thing.
CAPS_MEASURED = "measured"
CAPS_PREMISE_NOT_MET = "premise-not-met"
# R-05 §2: the third status. `premise-not-met` is the HONEST all-`None` — the
# game calls no `lose()`, so there is no budget to measure. A game that DOES
# call `lose()` and still measures nothing used to come back `measured` with an
# all-`None` vector, which is a silent pass: cap-fit is vacuous on `None`, so
# such a game ships "clean" because nothing could be checked. Three of our six
# shipped S4 games are exactly that (findings C4: pump-flow, conduit-watch,
# mosaic), and M-2 §8.8 argues it is worse than a measured violation. This
# status, plus `caps.note`, is that condition said out loud.
CAPS_UNMEASURED = "unmeasured"

# Burn outcomes, recorded per candidate action.
BURN_GAME_OVER = "game-over"
BURN_BOUNDED = "bound"
BURN_TRANSITION = "transition"
BURN_WIN = "win"

# --- I-1: the allowance probe's vocabulary ----------------------------------
# The two play shapes: one candidate repeated (the burn probe's only shape) and
# two candidates alternated. Alternation is what lets a play keep spending
# EFFECTIVE actions in a game whose blocked moves are free, and what lets a play
# outlive a death that only a repetition causes.
PLAY_REPEAT = "repeat"
PLAY_ALTERNATE = "alternate"
# How a probe play's GAME_OVER is attributed (`_attribute_death`).
DEATH_ALLOWANCE = "allowance"  # a DIFFERENT action, from the same state, also ends it
DEATH_ACTION_BOUND = "action-bound"  # every other action survives: what was played killed it
DEATH_BELOW_LINE = "below-solver-line"  # the solver lived longer in this level
DEATH_UNTESTED = "untested"  # no other candidate exists to substitute
DEATH_INCONCLUSIVE = "inconclusive"  # no substitute survived having changed the board
# What one substitute did (`_substitute`).
SUBSTITUTE_GAME_OVER = "game-over"
SUBSTITUTE_EXIT = "exit"
SUBSTITUTE_CHANGED = "changed"
SUBSTITUTE_NOOP = "no-op"
# ACTION6 enters the allowance probe as up to this many DISTINCT engine click
# cells (the burn probe uses only the first), so a click-only game still has
# two different actions to alternate and to substitute.
ALLOWANCE_CLICK_CELLS = 3
# ...and, for the raw-coordinate idiom that tags no sprite at all (6/25
# officials — bp35, cd82, ft09, lf52, s5i5, su15 — and convoy-in-the-fog), the
# burn probe's own fallback (`frames.CENTRE_CLICK`, the 64x64 centre) plus the
# two diagonal quadrant centres: a fixed, game-blind set of distinct clicks.
RAW_CLICK_POINTS = (CENTRE_CLICK, (16, 16), (48, 48))
# Where the burn figure rides beside the allowance (report `caps` block); the
# metadata carries `caps_legacy_burn`. One release, for comparability.
LEGACY_BURN_KEY = "legacy_burn"
LEGACY_BURN_LABEL = (
    "pre-I-1 burn probe: the first declared action repeated until GAME_OVER — it measures "
    "death-by-repetition, NOT budget.cap; recorded beside the allowance probe for one "
    "release (comparability) and never a cap-fit input"
)


# --- the captured solver line -----------------------------------------------


@dataclass(frozen=True)
class LineCapture:
    """The winning solver line, split into the levels it completed.

    `per_level[i]` holds level i+1's actions as replayable records
    (`{"id": int, "data": dict | None}`); `described[i]` holds the same
    actions as `frames.describe_action` strings.
    """

    game_id: str
    per_level: tuple[tuple[dict, ...], ...]
    described: tuple[tuple[str, ...], ...]
    win: bool
    levels_completed: int


def _action_record(action: ActionInput) -> dict:
    """One replayable action record. Data keys sorted — bytes are identity."""
    data = {key: action.data[key] for key in sorted(action.data)} if action.data else None
    return {"id": int(action.id.value), "data": data}


def _action_from_record(record: Mapping) -> ActionInput:
    """The inverse of `_action_record` — what makes `actions/*.json` a fact."""
    if not isinstance(record, Mapping) or "id" not in record:
        raise ValueError(f"action record must be a mapping with an 'id', got {record!r}")
    action_id = GameAction.from_id(int(record["id"]))
    data = record.get("data")
    if data is not None and not isinstance(data, Mapping):
        raise ValueError(f"action record 'data' must be a mapping or null, got {data!r}")
    return ActionInput(id=action_id, data=dict(data) if data else {})


def solver_lines(worker_dir: Path, *, max_actions: int = 600) -> LineCapture:
    """Drive the worker's solver and split its WINNING line per level.

    The drive loop mirrors `s3_static._drive_solver` (RESET, then
    `solver.next_action(fd)` until terminal / None / `max_actions`); it is
    re-derived here rather than imported because that helper keeps only
    `describe_action` strings and S4 needs the `ActionInput`s themselves —
    `actions/level-<i>.json` has to replay verbatim.

    The split is architecture §3 S4 step 1's `actions/level-i.json`: an action
    belongs to the level that was current when it was PERFORMED, so the
    transition action belongs to the level it completes.
    """
    worker_dir = Path(worker_dir)
    game_cls, solver_cls = load_worker_classes(worker_dir)
    if solver_cls is None:
        raise ValueError(
            f"{worker_dir}: S4 needs the solver line and this worker ships no solver.py "
            "(architecture §3 S4 step 1: solver_i is the length of the solver's real line)"
        )
    if max_actions < 1:
        raise ValueError(f"max_actions must be >= 1, got {max_actions}")

    game = _fresh_game(game_cls)
    solver = solver_cls()
    reset_fn = getattr(solver, "reset", None)
    if callable(reset_fn):
        reset_fn()
    if not callable(getattr(solver, "next_action", None)):
        raise TypeError(f"{solver_cls.__name__} has no callable next_action(frame_data)")

    fd = _reset(game)
    buckets: dict[int, list[dict]] = {}
    described: dict[int, list[str]] = {}
    for step_index in range(max_actions):
        if fd.state in TERMINAL_STATES:
            break
        action = solver.next_action(fd)
        if action is None:
            break
        if not isinstance(action, ActionInput):
            raise TypeError(
                f"solver returned {type(action).__name__} at action #{step_index + 1}, "
                "expected ActionInput"
            )
        current = int(fd.levels_completed)
        buckets.setdefault(current, []).append(_action_record(action))
        described.setdefault(current, []).append(describe_action(action))
        fd = _perform(game, action)

    win = fd.state is GameState.WIN
    completed = int(fd.levels_completed)
    played = sum(len(v) for v in buckets.values())
    if not win:
        raise ValueError(
            f"{worker_dir}: the solver line ended {fd.state.name} after {played} action(s) "
            f"with {completed} level(s) completed — S4 baselines exist only for a WINNING "
            "line (spec §2 row 4: the solver reaches the goal state — D11)"
        )
    if completed < 1:
        raise ValueError(
            f"{worker_dir}: the line WINs but credits {completed} level(s) — nothing to baseline"
        )

    empty = [index + 1 for index in range(completed) if not buckets.get(index)]
    if empty:
        raise ValueError(
            f"{worker_dir}: level(s) {empty} carry zero solver actions — the per-level split "
            "is wrong (architecture §3 S4 step 1 counts each level's own line)"
        )
    stray = sorted(key for key in buckets if key >= completed)
    if stray:
        raise ValueError(
            f"{worker_dir}: {len(stray)} action bucket(s) past the final level {stray!r} — "
            "the line kept playing after the win"
        )

    return LineCapture(
        game_id=str(fd.game_id),
        per_level=tuple(tuple(buckets[index]) for index in range(completed)),
        described=tuple(tuple(described[index]) for index in range(completed)),
        win=True,
        levels_completed=completed,
    )


def write_actions(lines: LineCapture, out_dir: Path) -> list[Path]:
    """Write `actions/level-<i>.json` (1-indexed) — the stage's facts.

    Stale level files from a previous, longer line are removed: the directory
    describes ONE line, and a leftover `level-7.json` would replay as fact.
    """
    if not isinstance(lines, LineCapture):
        raise TypeError(f"expected a LineCapture, got {type(lines).__name__}")
    actions_dir = Path(out_dir) / ACTIONS_DIRNAME
    actions_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, level in enumerate(lines.per_level, start=1):
        path = actions_dir / f"level-{index}.json"
        path.write_text(
            json.dumps([dict(record) for record in level], indent=2) + "\n", encoding="utf-8"
        )
        written.append(path)
    keep = set(written)
    for stale in sorted(actions_dir.glob("level-*.json")):
        if stale not in keep:
            stale.unlink()
    return written


# --- cap measurement --------------------------------------------------------


def _replay_prefix(game_cls, prefix: Sequence[Mapping], level_index: int):
    """A fresh instance replayed to `level_index`'s start. Fails loud if not.

    Every probe and every burn gets its OWN instance + prefix, which is what
    makes the measurement independent (no probe sees another's state) and
    deterministic — the same rule `frames._capture_probe` follows.
    """
    game = _fresh_game(game_cls)
    fd = _reset(game)
    for record in prefix:
        fd = _perform(game, _action_from_record(record))
    reached = int(fd.levels_completed)
    if reached != level_index or fd.state in TERMINAL_STATES:
        raise ValueError(
            f"replaying {len(prefix)} prefix action(s) landed at levels_completed={reached} "
            f"state={fd.state.name}, expected levels_completed={level_index} in play — the "
            "solver line is not reproducible from its own action records"
        )
    return game, fd


def _burn_action(game, action_id: int) -> ActionInput:
    """The `ActionInput` for a declared action id, at the CURRENT level.

    Click (ACTION6) uses the first cell the ENGINE reports clickable here
    (`frames.click_cells`, which mirrors `_get_valid_clickable_actions`), and
    falls back to `frames.CENTRE_CLICK` for the click-only idiom that tags
    nothing. The coordinate is fixed once, before the burn: "burn the first
    qualifying action repeatedly" means the same action every call.
    """
    action = GameAction.from_id(int(action_id))
    if action is GameAction.RESET:
        raise ValueError("RESET is never a burn candidate — it refills the budget")
    if action is GameAction.ACTION6:
        cells = click_cells(game)
        if cells:
            return mouse(cells[0].x, cells[0].y)
        return mouse(*CENTRE_CLICK)
    return ActionInput(id=action)


def _burn(game_cls, prefix: Sequence[Mapping], level_index: int, action_id: int):
    """Burn one action on a fresh instance+prefix. Returns (calls, outcome).

    `calls` counts perform_action calls IN THE BURN ONLY — D8 budgets count
    actions, and the prefix's actions are the solver's, not the burn's. A burn
    that leaves the level (transition or win) stops being a measurement OF
    this level, so it is abandoned rather than continued: that can only cost a
    candidate, never invent a cap for the wrong level.
    """
    game, _fd = _replay_prefix(game_cls, prefix, level_index)
    action = _burn_action(game, action_id)
    calls = 0
    while calls < BURN_BOUND:
        fd = _perform(game, action)
        calls += 1
        if fd.state is GameState.GAME_OVER:
            return calls, BURN_GAME_OVER
        if fd.state is GameState.WIN:
            return calls, BURN_WIN
        if int(fd.levels_completed) != level_index:
            return calls, BURN_TRANSITION
    return calls, BURN_BOUNDED


def _level_cap(game_cls, prefix: Sequence[Mapping], level_index: int) -> dict:
    """Measure one level's enforced cap. Returns the level's report record."""
    # Only the declared action list is taken from this instance; every probe
    # and the burn each build their own.
    _game, fd = _replay_prefix(game_cls, prefix, level_index)
    action_ids = _playable_action_ids(fd)

    candidates: list[dict] = []
    for action_id in action_ids:
        probe_game, _probe_fd = _replay_prefix(game_cls, prefix, level_index)
        action = _burn_action(probe_game, action_id)
        result = _perform(probe_game, action)
        transitioned = int(result.levels_completed) != level_index
        terminated = result.state in TERMINAL_STATES
        candidates.append(
            {
                "action_id": int(action_id),
                "action": describe_action(action),
                # A candidate qualifies when its frame neither transitions a
                # level nor terminates the game: only such an action can burn
                # budget without leaving the level being measured.
                "qualifies": not transitioned and not terminated,
                "probe": (
                    BURN_TRANSITION
                    if transitioned
                    else (result.state.name if terminated else "in-level")
                ),
                "burn": None,
            }
        )

    cap: int | None = None
    burn_action: str | None = None
    for candidate in candidates:
        if not candidate["qualifies"]:
            continue
        calls, outcome = _burn(game_cls, prefix, level_index, candidate["action_id"])
        candidate["burn"] = {"calls": calls, "outcome": outcome}
        if outcome == BURN_GAME_OVER:
            cap = calls
            burn_action = candidate["action"]
            break

    return {
        "level": level_index + 1,
        "cap": cap,
        "burn_action": burn_action,
        "bound": BURN_BOUND,
        "candidates": candidates,
    }


def _measure_caps_detail(worker_dir: Path, lines: LineCapture):
    """`(caps, per-level records)` — the report needs the per-candidate detail."""
    if not isinstance(lines, LineCapture):
        raise TypeError(f"expected a LineCapture, got {type(lines).__name__}")
    game_cls, _solver_cls = load_worker_classes(Path(worker_dir))
    caps: list[int | None] = []
    detail: list[dict] = []
    for level_index in range(len(lines.per_level)):
        prefix = [record for level in lines.per_level[:level_index] for record in level]
        record = _level_cap(game_cls, prefix, level_index)
        caps.append(record["cap"])
        detail.append(record)
    return tuple(caps), detail


def measure_caps(worker_dir: Path, lines: LineCapture) -> tuple[int | None, ...]:
    """The game's ENFORCED per-level caps; `None` = uncapped within `BURN_BOUND`.

    Per level: replay the solver prefix through the PREVIOUS level's
    completion (this level's own solver actions are never replayed — the
    battery's budget is for a player who has not seen the line), probe each
    declared non-RESET action id ascending on its own fresh instance+prefix,
    then burn the first qualifying one until `GAME_OVER`. If a candidate never
    dies within `BURN_BOUND`, the next qualifying candidate is tried; when all
    are exhausted the level is `None`.

    For a game whose budget is GLOBAL rather than per-level the measured value
    is the budget remaining at that level's start given the prefix — that IS
    the cap enforced there, and cap-fit is right to hold the baseline to it.
    """
    caps, _detail = _measure_caps_detail(worker_dir, lines)
    return caps


def _has_lose_call(worker_dir: Path) -> bool:
    """Does the game source call `lose()` anywhere? (spec §2 row 3's wiring.)

    An AST scan of the game file, matching `self.lose()`-shaped calls and a
    bare `lose()`. A game with no `lose()` at all has no budget to measure, so
    an all-`None` caps vector there is the premise not being met rather than a
    measurement failure.
    """
    tree = ast.parse(game_source_path(Path(worker_dir)).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "lose":
            return True
        if isinstance(func, ast.Name) and func.id == "lose":
            return True
    return False


# --- I-1: the allowance probe (`caps.probe: allowance`) ---------------------
#
# WHAT budget.cap BOUNDS. Canon's term: "game-enforced action cap" — a
# per-level action allowance tracked by the game, whose exhaustion ends the
# play (the officials' StepCounter / MaxSteps / `_max_actions`, decremented per
# action). The defining property is that the ending depends on HOW MUCH was
# played, never on WHAT: at the allowance, the next action ends the play
# whichever action it is. That is also how D8 identified the public runner's
# budget — deaths from hundreds of different plays piling up at one count
# (519 of 590 at exactly 5.00x) — and it is what the burn probe never asked:
# it repeats ONE action and reports the first GAME_OVER, so a lava cell three
# presses up, a deadlock oracle, or a repetition rule is reported as the cap,
# and a game whose blocked moves are free is reported as uncapped.
#
# THE PROBE, per level (fresh instance + the solver prefix, as the burn probe):
#   1. candidates = every declared non-RESET action, ACTION6 expanded to up to
#      `ALLOWANCE_CLICK_CELLS` distinct engine click cells (`RAW_CLICK_POINTS`
#      when the engine reports none); each probed once.
#   2. plays = every ordered PAIR of qualifying candidates alternated, then
#      every qualifying candidate repeated — each run until GAME_OVER, a level
#      exit, or its limit (`BURN_BOUND`, then one below the best allowance found
#      so far: a longer play cannot lower the answer).
#   3. each GAME_OVER at count n is ATTRIBUTED (`_attribute_death`):
#        * n below the solver's own line in this level -> `below-solver-line`
#          (the solver lived longer here, so no allowance ends a play at n —
#          the convoy / core-ward exhibits);
#        * else replay the play's first n-1 actions and substitute each OTHER
#          candidate as the n-th: if one also ends the play -> `allowance`;
#          if every one survives and at least one of them CHANGED the board
#          -> `action-bound` (what was played killed it);
#        * if every survivor changed nothing (a free no-op cannot exhaust an
#          allowance, so its survival says nothing — conduit-watch's levels,
#          where the one effective action is the one being played), the
#          HIDDEN-STATE WITNESS decides: the same action met a pixel-identical
#          board a whole period earlier in this play and survived, so only
#          state the board does not show ended it now -> `allowance`; with no
#          witness -> `inconclusive` (`untested` when no substitute exists).
#   4. cap = the smallest `allowance` count, `None` when there is none.
#
# Order-independent by construction (the minimum over attributed deaths, and a
# play is only ever cut above the running minimum); plays are run alternations
# first because they are the ones that find an allowance early.
#
# Residuals, recorded rather than hidden (each one measured on a real game):
#   * an allowance no probe play can reach alive is `None` — honestly
#     unmeasured, never invented (core-ward: every play dies of a hazard
#     below the solver line long before its 224-1040 turn cap; seamlock: only
#     fusions and stamps are charged, and no probe play accumulates its
#     75-285 cap's worth of them);
#   * a budget drained by ONE action type, where every other action is free
#     but visibly changes the board, is indistinguishable from a positional
#     hazard on that action's axis ("the k-th ACTION5 kills") — the probe
#     declines to certify it (official sb26 L1: burn 64 = its budget,
#     allowance `None`);
#   * when actions cost the allowance unequally (official dc22: a drowning
#     click costs 20 units), the count depends on the action mix and the probe
#     reports the EARLIEST attributable exhaustion among its plays (dc22 L1:
#     61, against StepCounter 128 for a one-unit-per-action play) — the
#     conservative number for cap-fit; refillable allowances (convoy's drums)
#     have no single per-level count at all;
#   * a death at n where a substitute dies of its OWN hazard reads as
#     `allowance` (one step cannot tell them apart).


def _allowance_candidates(game_cls, prefix: Sequence[Mapping], level_index: int) -> list[dict]:
    """The probe's action alphabet at this level's start, each probed once."""
    game, fd = _replay_prefix(game_cls, prefix, level_index)
    records: list[dict] = []
    for action_id in _playable_action_ids(fd):
        if GameAction.from_id(int(action_id)) is GameAction.ACTION6:
            cells: list[tuple[int, int]] = []
            for cell in click_cells(game):
                if (cell.x, cell.y) not in cells:
                    cells.append((cell.x, cell.y))
                if len(cells) == ALLOWANCE_CLICK_CELLS:
                    break
            if not cells:
                cells = list(RAW_CLICK_POINTS[:ALLOWANCE_CLICK_CELLS])
            actions = [mouse(x, y) for x, y in cells]
        else:
            actions = [_burn_action(game, action_id)]
        records.extend(_action_record(action) for action in actions)

    candidates: list[dict] = []
    for record in records:
        probe_game, _probe_fd = _replay_prefix(game_cls, prefix, level_index)
        action = _action_from_record(record)
        result = _perform(probe_game, action)
        transitioned = int(result.levels_completed) != level_index
        terminated = result.state in TERMINAL_STATES
        candidates.append(
            {
                "action_id": int(record["id"]),
                "action": describe_action(action),
                "record": record,
                "qualifies": not transitioned and not terminated,
                "probe": (
                    BURN_TRANSITION
                    if transitioned
                    else (result.state.name if terminated else "in-level")
                ),
            }
        )
    return candidates


def _board_digest(fd) -> bytes:
    """A digest of the settled frame — the visible board, HUD included."""
    return hashlib.sha256(np.ascontiguousarray(fd.frame[-1]).tobytes()).digest()


def _play(game_cls, prefix, level_index: int, pattern: Sequence[Mapping], limit: int):
    """Run one probe play (the pattern cycled) on a fresh instance.

    -> `(calls, outcome, boards)`: `boards[k]` is the settled-board digest after
    k actions (`boards[0]` = the level start), the hidden-state witness's input.
    """
    game, fd = _replay_prefix(game_cls, prefix, level_index)
    actions = [_action_from_record(record) for record in pattern]
    boards = [_board_digest(fd)]
    calls = 0
    while calls < limit:
        fd = _perform(game, actions[calls % len(actions)])
        calls += 1
        if fd.state is GameState.GAME_OVER:
            return calls, BURN_GAME_OVER, boards
        if fd.state is GameState.WIN:
            return calls, BURN_WIN, boards
        if int(fd.levels_completed) != level_index:
            return calls, BURN_TRANSITION, boards
        boards.append(_board_digest(fd))
    return calls, BURN_BOUNDED, boards


def _hidden_state_witness(boards: Sequence[bytes], calls: int, period: int) -> int | None:
    """An earlier step where the SAME action met the SAME board and survived.

    The lethal action was applied to board `boards[calls - 1]`. One or more
    whole periods earlier the play applied that same action (same phase) — if
    the board then was pixel-identical, the action survived it, so only state
    the board does not show (a budget counter whose meter did not visibly move
    in between, a timer, lives) can have ended the play now. Returns that
    earlier step (1-indexed), or None.
    """
    target = boards[calls - 1]
    for index in range(calls - 1 - period, -1, -period):
        if boards[index] == target:
            return index + 1
    return None


def _substitute(
    game_cls, prefix, level_index: int, pattern: Sequence[Mapping], steps: int, substitute
) -> str:
    """Replay the play's first `steps` actions, then `substitute`. -> one of
    `game-over`, `exit` (it won or left the level — the win check runs first,
    so an exit says nothing about an allowance), `changed` (alive, in-level,
    board moved: an informative survival) or `no-op` (alive, board unchanged:
    a free no-op, whose survival cannot speak to an allowance).
    """
    game, fd = _replay_prefix(game_cls, prefix, level_index)
    actions = [_action_from_record(record) for record in pattern]
    for step in range(steps):
        fd = _perform(game, actions[step % len(actions)])
        if fd.state in TERMINAL_STATES or int(fd.levels_completed) != level_index:
            raise ValueError(
                f"a probe play's first {steps} action(s) did not replay alive in level "
                f"{level_index + 1} — the game is not deterministic under action replay"
            )
    before = settled_grid(fd)
    after = _perform(game, _action_from_record(substitute))
    if after.state is GameState.GAME_OVER:
        return SUBSTITUTE_GAME_OVER
    if after.state is GameState.WIN or int(after.levels_completed) != level_index:
        return SUBSTITUTE_EXIT
    return SUBSTITUTE_CHANGED if settled_grid(after) != before else SUBSTITUTE_NOOP


def _attribute_death(
    game_cls, prefix, level_index: int, pattern: Sequence[dict], calls: int,
    candidates: Sequence[dict], survived: int, boards: Sequence[bytes],
) -> dict:
    """Attribute one probe play's GAME_OVER at `calls` (see the section header)."""
    if calls < survived:
        return {"class": DEATH_BELOW_LINE, "survived": survived}
    last = pattern[(calls - 1) % len(pattern)]["action"]
    substitutes = [candidate for candidate in candidates if candidate["action"] != last]
    records = [candidate["record"] for candidate in pattern]
    changed_any = False
    tried: list[dict] = []
    for candidate in substitutes:
        result = _substitute(
            game_cls, prefix, level_index, records, calls - 1, candidate["record"]
        )
        if result == SUBSTITUTE_GAME_OVER:
            return {"class": DEATH_ALLOWANCE, "rule": "substitute",
                    "substitute": candidate["action"]}
        changed_any = changed_any or result == SUBSTITUTE_CHANGED
        tried.append({"action": candidate["action"], "result": result})
    if changed_any:
        # A substitute that DID something survived: what was played killed it.
        # The witness is never consulted here — a repetition rule is hidden
        # state too, and this is exactly the case that must not read as a cap.
        return {"class": DEATH_ACTION_BOUND, "substitutes_survived": tried}
    witness = _hidden_state_witness(boards, calls, len(pattern))
    if witness is not None:
        return {"class": DEATH_ALLOWANCE, "rule": "hidden-state", "witness_step": witness,
                "substitutes_survived": tried}
    return {
        "class": DEATH_INCONCLUSIVE if substitutes else DEATH_UNTESTED,
        "substitutes_survived": tried,
    }


def _level_allowance(game_cls, prefix: Sequence[Mapping], level_index: int, survived: int) -> dict:
    """Measure one level's allowance. Returns the level's report record.

    `survived` is the number of actions a known LIVING play spent in this
    level — S4 passes the solver's own per-level count.
    """
    if isinstance(survived, bool) or not isinstance(survived, int) or survived < 0:
        raise ValueError(f"survived must be an int >= 0, got {survived!r}")
    candidates = _allowance_candidates(game_cls, prefix, level_index)
    usable = [candidate for candidate in candidates if candidate["qualifies"]]
    patterns = [
        (PLAY_ALTERNATE, (first, second))
        for first in usable
        for second in usable
        if first is not second
    ] + [(PLAY_REPEAT, (candidate,)) for candidate in usable]

    best: int | None = None
    plays: list[dict] = []
    for kind, pattern in patterns:
        limit = BURN_BOUND if best is None else best - 1
        if limit < 1:
            break
        records = [candidate["record"] for candidate in pattern]
        calls, outcome, boards = _play(game_cls, prefix, level_index, records, limit)
        death = None
        if outcome == BURN_GAME_OVER:
            death = _attribute_death(
                game_cls, prefix, level_index, pattern, calls, candidates, survived, boards
            )
            if death["class"] == DEATH_ALLOWANCE:
                best = calls  # calls <= limit < best: a strictly smaller allowance
        plays.append(
            {
                "kind": kind,
                "actions": [candidate["action"] for candidate in pattern],
                "limit": limit,
                "calls": calls,
                "outcome": outcome,
                "death": death,
            }
        )

    return {
        "level": level_index + 1,
        "cap": best,
        "survived": survived,
        "bound": BURN_BOUND,
        "candidates": [
            {key: candidate[key] for key in ("action_id", "action", "qualifies", "probe")}
            for candidate in candidates
        ],
        "plays": plays,
    }


def _measure_allowance_detail(worker_dir: Path, lines: LineCapture):
    """`(caps, per-level records)` under the allowance probe."""
    if not isinstance(lines, LineCapture):
        raise TypeError(f"expected a LineCapture, got {type(lines).__name__}")
    game_cls, _solver_cls = load_worker_classes(Path(worker_dir))
    caps: list[int | None] = []
    detail: list[dict] = []
    for level_index, level in enumerate(lines.per_level):
        prefix = [record for done in lines.per_level[:level_index] for record in done]
        record = _level_allowance(game_cls, prefix, level_index, len(level))
        caps.append(record["cap"])
        detail.append(record)
    return tuple(caps), detail


def measure_allowance(worker_dir: Path, lines: LineCapture) -> tuple[int | None, ...]:
    """The game's per-level ALLOWANCE (what `budget.cap` bounds); `None` = none
    measurable. The I-1 counterpart of `measure_caps` — see the section header."""
    caps, _detail = _measure_allowance_detail(worker_dir, lines)
    return caps


# --- the g distribution -----------------------------------------------------


@dataclass(frozen=True)
class _GParams:
    """The `g:` block — architecture §3 S4's only tunables."""

    median: float
    q1: float
    q3: float
    floor: int
    span_target: float
    trend: float
    redraw_cap: int


def _g_params(cfg: Mapping) -> _GParams:
    """Parse + validate `cfg['g']`. No defaults: a missing knob is a config bug."""
    if not isinstance(cfg, Mapping):
        raise TypeError(f"cfg must be a mapping, got {type(cfg).__name__}")
    if "g" not in cfg:
        raise ValueError(
            "config has no 'g' block (architecture §3 S4 Config: g.median, g.iqr, "
            "g.floor, g.span_target, g.trend, g.redraw_cap)"
        )
    block = cfg["g"]
    if not isinstance(block, Mapping):
        raise TypeError(f"config 'g' must be a mapping, got {type(block).__name__}")
    required = ("median", "iqr", "floor", "span_target", "trend", "redraw_cap")
    missing = [key for key in required if key not in block]
    if missing:
        raise ValueError(f"config g: is missing {missing} (architecture §3 S4 Config)")

    median = _as_float(block["median"], "g.median")
    if median <= 0:
        raise ValueError(f"g.median must be > 0, got {median}")
    iqr = block["iqr"]
    if not isinstance(iqr, Sequence) or isinstance(iqr, str) or len(iqr) != 2:
        raise ValueError(f"g.iqr must be a [q1, q3] pair, got {iqr!r}")
    q1 = _as_float(iqr[0], "g.iqr[0]")
    q3 = _as_float(iqr[1], "g.iqr[1]")
    if not 0 < q1 < median < q3:
        raise ValueError(
            f"g.iqr must satisfy 0 < q1 < median < q3, got q1={q1} median={median} q3={q3}"
        )
    floor = block["floor"]
    if not isinstance(floor, int) or isinstance(floor, bool) or floor < 1:
        raise ValueError(f"g.floor must be an int >= 1, got {floor!r}")
    span_target = _as_float(block["span_target"], "g.span_target")
    if span_target <= 1:
        raise ValueError(f"g.span_target must be > 1 (a ratio of max to min), got {span_target}")
    trend = _as_float(block["trend"], "g.trend")
    if not -1.0 < trend < 1.0:
        raise ValueError(f"g.trend must be a correlation in (-1, 1), got {trend}")
    redraw_cap = block["redraw_cap"]
    if not isinstance(redraw_cap, int) or isinstance(redraw_cap, bool) or redraw_cap < 0:
        raise ValueError(f"g.redraw_cap must be an int >= 0, got {redraw_cap!r}")

    # I-1: a configured centering REPLACES the centre (median + IQR) with the
    # named instrument's own statistic; the literals above are still validated
    # (they are required knobs) and `run_s4` records what they were.
    centering = _g_centering(cfg)
    if centering is not None:
        median = centering.median
        q1, q3 = centering.iqr

    return _GParams(median, q1, q3, floor, span_target, trend, redraw_cap)


def _g_centering(cfg: Mapping) -> GInstrument | None:
    """`g.centering` — `None` (absent: the config's own literals) or the named
    officials-instrument (`G_INSTRUMENTS`). Anything else raises.

    The I-1 knob, under the house rule: absent is byte-for-byte today. Its two
    values are the adjudicated `d7-replay` and the named alternative
    `effort-blind` (see the constants block for the adjudication).
    """
    if not isinstance(cfg, Mapping):
        raise TypeError(f"cfg must be a mapping, got {type(cfg).__name__}")
    block = cfg.get("g")
    if not isinstance(block, Mapping) or G_CENTERING_KEY not in block:
        return None
    name = block[G_CENTERING_KEY]
    if not isinstance(name, str) or name not in G_INSTRUMENTS:
        raise ValueError(f"g.centering must be one of {list(G_CENTERINGS)}, got {name!r}")
    return G_INSTRUMENTS[name]


def g_statistics(pairs: Sequence[tuple[str, float]]) -> dict:
    """An officials-instrument's g statistic, from its own per-level rows.

    `pairs` = `(game, g)` per level with `g = baseline / line`. Returns the
    per-level median and quartiles — numpy's linear quantiles, the estimator
    D7's own tool printed (`official_replay_ratios.py`'s `pct`), so the
    published 1.54-2.96 is reproduced rather than a neighbouring estimator's —
    and the per-GAME median span, the construction effort.csv's 0.437-1.084
    band (and so `OFFICIAL_G_BOX`) uses. This is how every `G_INSTRUMENTS`
    number is derived; the pins re-derive them from frozen copies of the files.
    """
    values: list[float] = []
    per_game: dict[str, list[float]] = {}
    for index, pair in enumerate(pairs):
        if not isinstance(pair, Sequence) or isinstance(pair, str) or len(pair) != 2:
            raise ValueError(f"pairs[{index}] must be a (game, g) pair, got {pair!r}")
        game, g = pair
        number = _as_float(g, f"pairs[{index}] g")
        if number <= 0:
            raise ValueError(f"pairs[{index}] g must be > 0, got {number}")
        values.append(number)
        per_game.setdefault(str(game), []).append(number)
    if not values:
        raise ValueError("g_statistics needs at least one level")
    array = np.asarray(values, dtype=float)
    medians = [float(np.median(np.asarray(v, dtype=float))) for v in per_game.values()]
    return {
        "levels": len(values),
        "games": len(per_game),
        "median": float(np.percentile(array, 50)),
        "q1": float(np.percentile(array, 25)),
        "q3": float(np.percentile(array, 75)),
        "game_band": (min(medians), max(medians)),
    }


def _cap_fit_mode(cfg: Mapping) -> str:
    """`g.cap_fit` — `hard` (canon, the default) or `record`. Anything else raises.

    The D8 DEVIATION, taken as a pilot ruling (operator, 2026-09-24): in `record`
    a final cap-fit violation no longer rejects. The check still runs per
    attempt exactly as it does today and every redraw is still spent looking
    for a fitting vector; what changes is only the end of the search — the last
    canon-shaped draw ships and the violation is written into the report and
    `metadata.json` as a `cap_fit` block. The ruling is that an otherwise
    accepted game must not be permanently blocked by a budget the generator can
    re-tune in a later pass; the D8 5x battery convention is unchanged and the
    block is what a later pass reads.

    Absent knob -> `hard`, so a config written before this ruling behaves
    byte-for-byte as it did.
    """
    if not isinstance(cfg, Mapping):
        raise TypeError(f"cfg must be a mapping, got {type(cfg).__name__}")
    block = cfg.get("g")
    if not isinstance(block, Mapping):
        return CAP_FIT_HARD  # `_g_params` owns the "no g: block" failure
    mode = block.get(CAP_FIT_KEY, CAP_FIT_HARD)
    if mode not in CAP_FIT_MODES:
        raise ValueError(f"g.cap_fit must be one of {list(CAP_FIT_MODES)}, got {mode!r}")
    return mode


def _caps_basis(cfg: Mapping) -> str:
    """`caps.basis` — `legacy` (the default) or `official-band`. Else raises.

    The R-05 §1 knob, and the house rule applies in full: an absent `caps:`
    block is `legacy`, and `legacy` is byte-for-byte the stage as it shipped —
    the same draw, the same reshape, the same clip, the same report keys.

    `official-band` changes exactly two things, both documented at their sites:

    * the implied-g box the reshape clips to becomes `OFFICIAL_G_BOX`
      (`[1.0, 2.288]`) instead of canon `G_CLIP` (`[1.2, 6.0]`), which is the
      ONLY lever S4 has over the effort ratio — R-22's acceptance is "re-measured
      per-game median ratio inside the officials' observed 0.437-1.084 span",
      and `ratio = 1 / g`, so the ratio band IS a g box;
    * the report and metadata gain the derived per-level REQUIRED cap
      (`official_band_caps`) plus the band record (`caps_band_block`).

    What it does NOT change, deliberately: the cap-fit halves still run against
    the MEASURED cap. S4 measures the enforced budget with a burn probe; it
    cannot set it (the budget lives in the game source, which is S2's), so a
    derived number standing in for a measured one in `metadata.caps` would be
    the provenance lie this module's header forbids — and cap-fit against a cap
    derived FROM the baseline is a tautology, which would quietly disarm the
    one check R-22 §3 is arming.
    """
    if not isinstance(cfg, Mapping):
        raise TypeError(f"cfg must be a mapping, got {type(cfg).__name__}")
    block = cfg.get(CAPS_BLOCK_KEY)
    if block is None:
        return CAPS_BASIS_LEGACY
    if not isinstance(block, Mapping):
        raise TypeError(f"config 'caps' must be a mapping, got {type(block).__name__}")
    unknown = sorted(key for key in block if key not in CAPS_BLOCK_KEYS)
    if unknown:
        raise ValueError(
            f"config caps: has unknown key(s) {unknown} (only {list(CAPS_BLOCK_KEYS)} are read)"
        )
    basis = block.get(CAPS_BASIS_KEY, CAPS_BASIS_LEGACY)
    if basis not in CAPS_BASES:
        raise ValueError(f"caps.basis must be one of {list(CAPS_BASES)}, got {basis!r}")
    return basis


def _caps_probe(cfg: Mapping) -> str:
    """`caps.probe` — `burn` (the default) or `allowance`. Anything else raises.

    `burn` is the pre-I-1 probe, byte-for-byte, and an absent knob is `burn`.
    `allowance` (I-1) measures what `budget.cap` bounds — see
    `_level_allowance` — and makes it the cap-fit reference, with the burn
    figure recorded beside it under `LEGACY_BURN_KEY` for one release.
    """
    _caps_basis(cfg)  # the block's shape and its unknown-key refusal live there
    block = cfg.get(CAPS_BLOCK_KEY)
    if block is None:
        return CAPS_PROBE_BURN
    probe = block.get(CAPS_PROBE_KEY, CAPS_PROBE_BURN)
    if not isinstance(probe, str) or probe not in CAPS_PROBES:
        raise ValueError(f"caps.probe must be one of {list(CAPS_PROBES)}, got {probe!r}")
    return probe


def _g_box(basis: str, centering: GInstrument | None = None) -> tuple[float, float]:
    """The implied-g box the reshape clips to, per `caps.basis` (and, I-1, per
    `g.centering` under `official-band`).

    `legacy` returns canon `G_CLIP` — the SAME object, so every downstream
    arithmetic is bit-identical to the pre-R-05 stage — whatever the centering:
    canon's [1.2, 6] is D7's own per-level clip. `official-band` returns the
    centering instrument's per-game band (`OFFICIAL_G_BOX` when no centering is
    configured, which is today's effort.csv box).
    """
    if basis not in CAPS_BASES:
        raise ValueError(f"caps.basis must be one of {list(CAPS_BASES)}, got {basis!r}")
    if centering is not None and not isinstance(centering, GInstrument):
        raise TypeError(f"centering must be a GInstrument or None, got {centering!r}")
    if basis == CAPS_BASIS_LEGACY:
        return G_CLIP
    return OFFICIAL_G_BOX if centering is None else centering.g_box


def _as_float(value, what: str) -> float:
    """A finite float, or fail loud. Wrong TYPE -> TypeError, bad VALUE -> ValueError
    (the house split: `frames.capture` raises TypeError for a wrong class and
    ValueError for `max_actions < 1`)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{what} must be a number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{what} must be finite, got {value!r}")
    return result


def fit_g(cfg: Mapping) -> tuple[float, float]:
    """`(mu, sigma)` of the lognormal behind `g`, derived from the config.

    architecture §3 S4 step 2 calls for a "lognormal fit of the n=183 per-level
    ratios: median 2.00, IQR 1.54-2.96". For a lognormal the median IS
    `exp(mu)`, so `mu = ln(median)` exactly. Sigma comes from the quartiles:
    `ln(q3) - mu = mu - ln(q1) = sigma * Phi^-1(0.75)` for a perfect fit. The
    MEASURED IQR is slightly asymmetric in log space around the median
    (`mu - ln 1.54 = 0.2614` vs `ln 2.96 - mu = 0.3920`, i.e. the upper half
    is ~50% wider), so the two half-widths are AVERAGED — one sigma from both
    quartiles rather than a fit that honours one and discards the other.
    """
    params = _g_params(cfg)
    mu = math.log(params.median)
    lower = mu - math.log(params.q1)
    upper = math.log(params.q3) - mu
    sigma = ((lower + upper) / 2.0) / PHI_INV_075
    if sigma <= 0:
        raise ValueError(f"fitted sigma must be > 0, got {sigma} from {params!r}")
    return mu, sigma


# --- the reshapers (architecture §3 S4 step 3, in canon order) --------------


def has_strict_descent(values: Sequence[float]) -> bool:
    """Is the vector non-monotonic in the corpus's sense?

    Corpus fact (lead-verified 2026-09-22 over all 25 officials'
    `metadata.json`): 0 of 25 official baseline vectors are nondecreasing —
    every one contains at least one strict descent. "The rising staircase is
    the tell of a generated game" (difficulty-model.md §2.1), so this is the
    predicate the reshaper has to satisfy.
    """
    return any(a > b for a, b in itertools.pairwise(values))


def _check_vector(baselines: Sequence[float], what: str = "baselines") -> list[float]:
    if not isinstance(baselines, Sequence) or isinstance(baselines, str):
        raise TypeError(f"{what} must be a sequence, got {type(baselines).__name__}")
    if not baselines:
        raise ValueError(f"{what} must be non-empty")
    out: list[float] = []
    for index, value in enumerate(baselines):
        number = _as_float(value, f"{what}[{index}]")
        if number <= 0:
            raise ValueError(f"{what}[{index}] must be > 0, got {number}")
        out.append(number)
    return out


def _check_solver(solver: Sequence[int], length: int) -> list[int]:
    if len(solver) != length:
        raise ValueError(f"solver has {len(solver)} level(s), baselines have {length}")
    out: list[int] = []
    for index, value in enumerate(solver):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"solver[{index}] must be an int >= 1, got {value!r}")
        out.append(int(value))
    return out


def _check_clip(clip: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(clip, Sequence) or len(clip) != 2:
        raise ValueError(f"clip must be a (lo, hi) pair, got {clip!r}")
    lo = _as_float(clip[0], "clip[0]")
    hi = _as_float(clip[1], "clip[1]")
    if not 0 < lo < hi:
        raise ValueError(f"clip must satisfy 0 < lo < hi, got {clip!r}")
    return lo, hi


def floor_bump(baselines: list[float], floor: int) -> list[float]:
    """Clamp every baseline up to `floor` — architecture §3 S4 step 3.

    "enforce floor `baseline_i >= 6`" (D7: "floor >= 6"). The corpus agrees
    exactly: the minimum baseline across all 25 officials is 6 (sc25), so
    `g.floor` IS the corpus minimum, not a margin below it.

    Only ever raises. Note it cannot push an implied g past `G_CLIP`'s top
    either: with `solver_i >= 1` the bumped ratio is `floor / solver_i <= 6`.
    """
    values = _check_vector(baselines)
    if not isinstance(floor, int) or isinstance(floor, bool) or floor < 1:
        raise ValueError(f"floor must be an int >= 1, got {floor!r}")
    return [max(value, float(floor)) for value in values]


def span_rescale(
    baselines: list[float],
    solver: list[int],
    span_target: float,
    clip: tuple[float, float],
) -> list[float]:
    """Stretch/shrink the vector toward the `span_target` max/min ratio.

    architecture §3 S4 step 3: "scale the vector so max/min ~ the 9x span
    target (tolerance band)". difficulty-model.md §2.1 measured that span at
    ~9x cheapest→dearest level and found it independent of level count.

    Done in log space around the geometric mean, so the rescale is symmetric
    and the central tendency of the vector is untouched: every log-deviation
    is multiplied by `ln(span_target) / ln(current_span)`. Each result is then
    re-clamped into its own level's implied-g box `[clip_lo * solver_i,
    clip_hi * solver_i]`, which is why the achieved span only moves TOWARD the
    target and never past it (the unclamped span is exactly the target, and
    clamping can only pull the extremes back in).

    Two no-ops, both by construction: a 1-level vector has no span, and a flat
    vector has no log-spread to scale (you cannot create a span from nothing).

    The `floor` is not a parameter of this frozen signature; `draw_baselines`
    re-applies `floor_bump` immediately afterwards, which is what makes the
    contract's "re-clamped so its implied g stays in G_CLIP and >= floor" true
    at the draw level.
    """
    values = _check_vector(baselines)
    counts = _check_solver(solver, len(values))
    lo, hi = _check_clip(clip)
    target = _as_float(span_target, "span_target")
    if target <= 1:
        raise ValueError(f"span_target must be > 1 (a ratio of max to min), got {target}")
    if len(values) < 2:
        return values

    logs = [math.log(value) for value in values]
    spread = max(logs) - min(logs)
    if spread <= FLAT_LOG_EPS:
        return values
    centre = sum(logs) / len(logs)
    factor = math.log(target) / spread
    out: list[float] = []
    for log_value, count in zip(logs, counts, strict=True):
        scaled = math.exp(centre + (log_value - centre) * factor)
        out.append(min(max(scaled, lo * count), hi * count))
    return out


def break_monotonic(baselines: list[float], rng: random.Random) -> list[float]:
    """Swap ONE rng-chosen interior pair when the vector is nondecreasing.

    architecture §3 S4 step 3, literally: "enforce non-monotonicity (if sorted
    ascending, swap one interior pair chosen by the rng)". The trigger is the
    corpus predicate — the vector has NO strict descent (`has_strict_descent`
    is false) — and the swap is of the adjacent pair `(i, i+1)` with `i` drawn
    from the INTERIOR indices `1 .. n-2`. That index set is why the rule needs
    3 levels to be live and is vacuous below that: at n=2 there is no interior
    index, at n=3 there is exactly one.

    Values are permuted, never changed, so the span is preserved exactly.
    Degenerate case, recorded rather than worked around: when the two swapped
    entries are EQUAL (a vector pinned flat at the floor) the swap is a no-op
    and the vector stays nondecreasing — `draw_baselines` records the outcome
    in `invariants.has_strict_descent`, it does not invent a descent.
    """
    values = _check_vector(baselines)
    if not isinstance(rng, random.Random):
        raise TypeError(f"rng must be a random.Random, got {type(rng).__name__}")
    if len(values) < 3 or has_strict_descent(values):
        return values
    index = rng.randrange(1, len(values) - 1)
    values[index], values[index + 1] = values[index + 1], values[index]
    return values


def _log_trend(values: Sequence[float]) -> float | None:
    """Pearson r between level index and `ln(baseline)`; None when undefined.

    Undefined below 3 levels (r over two points is +-1 by construction) and
    for a flat log vector (zero variance).
    """
    count = len(values)
    if count < 3:
        return None
    ys = [math.log(value) for value in values]
    if max(ys) - min(ys) <= FLAT_LOG_EPS:
        return None
    xs = [float(index) for index in range(count)]
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0.0 or var_y <= 0.0:
        return None
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return cov / math.sqrt(var_x * var_y)


def trend_nudge(
    baselines: list[float],
    solver: list[int],
    trend_target: float,
    clip: tuple[float, float],
) -> list[float]:
    """Tilt the vector in log space toward the +0.65 level/log-baseline trend.

    architecture §3 S4 step 3: "nudge toward the +0.65 log-trend"
    (difficulty-model.md §2.1: "Trend exists (+0.65 in log space) but with
    local inversions" — hence a nudge that runs AFTER the non-monotonicity
    swap and never re-sorts anything).

    The tilt is `ln b_i += alpha * (i - (n-1)/2)`: one monotone parameter, a
    centred linear ramp in the level index. r is strictly increasing in alpha
    (`dr/dt = (1 - r0^2) / (1 + 2 r0 t + t^2)^(3/2) > 0`), so:

    * alpha is solved in closed form for `r(alpha) == trend_target` — the tilt
      lands ON the target, never past it;
    * alpha is then clamped to the widest interval that keeps every implied g
      inside `clip`, so a tilt that would push a level out of the g box stops
      at the box instead. alpha = 0 is always inside that interval, so the
      worst case is "no tilt", never a clip violation;
    * the sign of the applied alpha is the direction from `r0` to the target,
      which is what makes the move direction-testable.

    No-ops: fewer than 3 levels, a flat log vector (r undefined — any tilt at
    all would jump it straight to r = +-1, which is an overshoot), and an
    already-on-target r.
    """
    values = _check_vector(baselines)
    counts = _check_solver(solver, len(values))
    lo, hi = _check_clip(clip)
    target = _as_float(trend_target, "trend_target")
    if not -1.0 < target < 1.0:
        raise ValueError(f"trend_target must be a correlation in (-1, 1), got {target}")

    start = _log_trend(values)
    if start is None or math.isclose(start, target, rel_tol=0.0, abs_tol=1e-12):
        return values

    count = len(values)
    centred = [index - (count - 1) / 2.0 for index in range(count)]
    logs = [math.log(value) for value in values]
    mean_y = sum(logs) / count
    var_x = sum(c * c for c in centred) / count
    var_y = sum((y - mean_y) ** 2 for y in logs) / count

    # t solves (r0 + t) / sqrt(1 + 2 r0 t + t^2) = target for the standardised
    # tilt; alpha rescales it back into log-baseline units.
    ratio = math.sqrt((1.0 - start * start) / (1.0 - target * target))
    t = -start + target * ratio
    alpha_target = t * math.sqrt(var_y / var_x)

    # Per-level bounds are the implied-g box WIDENED to contain the input, so
    # a value that arrived outside its box (only `break_monotonic`'s
    # permutation can do that) is passed through rather than yanked to the
    # bound: a yank would move r by an amount the tilt never chose, which is
    # how "never past the target" would break. For an in-box input — what
    # `draw_baselines` always passes — these ARE the box.
    bounds = [
        (min(lo * count_i, value), max(hi * count_i, value))
        for value, count_i in zip(values, counts, strict=True)
    ]
    alpha_lo, alpha_hi = -math.inf, math.inf
    for value, c, (low, high) in zip(values, centred, bounds, strict=True):
        if c == 0.0:
            continue
        edges = sorted((math.log(low / value) / c, math.log(high / value) / c))
        alpha_lo = max(alpha_lo, edges[0])
        alpha_hi = min(alpha_hi, edges[1])
    alpha = min(max(alpha_target, alpha_lo), alpha_hi)
    if alpha == 0.0:
        return values

    # The clamp is a no-op for any alpha inside that interval; it is kept for
    # float safety only, which is what makes the r move exactly monotone.
    out: list[float] = []
    for value, c, (low, high) in zip(values, centred, bounds, strict=True):
        out.append(min(max(value * math.exp(alpha * c), low), high))
    return out


# --- the draw ---------------------------------------------------------------


def _clip_to_box(baselines: Sequence[float], solver: Sequence[int], clip) -> list[float]:
    """Re-assert architecture §3 S4 step 2's clip on the reshaped vector.

    `break_monotonic` is a PERMUTATION — canon asks it to swap, and a swap can
    land a baseline on a level with a different `solver_i`, which is the one
    reshape that can push an implied g outside `[1.2, 6]` (measured: up to 12.0
    with a 4-vs-2 solver pair). Its frozen signature sees neither the solver
    counts nor the clip, so the clip is re-asserted here, where both live.

    Never breaks the floor: the upper bound is `clip_hi * solver_i >= 6` and
    the lower bound only raises.
    """
    lo, hi = clip
    return [
        min(max(value, lo * count), hi * count)
        for value, count in zip(baselines, solver, strict=True)
    ]


def _invariants(baselines: Sequence[int], floor: int) -> dict:
    """What the reshape actually achieved on the SHIPPED integer vector."""
    values = [int(value) for value in baselines]
    descent: bool | str = (
        has_strict_descent(values) if len(values) >= 3 else "vacuous"
    )
    return {
        "floor_ok": all(value >= floor for value in values),
        "has_strict_descent": descent,
        "span_achieved": max(values) / min(values),
        "trend_achieved": _log_trend(values),
    }


def draw_baselines(
    solver: list[int], caps: list[int | None], cfg: Mapping, seed: int
) -> dict:
    """Draw, reshape and cap-fit one game's baselines. Pure and deterministic.

    The architecture §3 S4 steps, in their stated order, per attempt
    (`attempt k` draws from `random.Random(seed + k)`, so attempt 0 is exactly
    `random.Random(seed)` and every redraw is reproducible on its own):

      a. `g_i = clip(exp(gauss(mu, sigma)), *clip)`, `b_i = solver_i * g_i`
         (D7: baselines are NOT raw solver counts — that produces the
         staircases that fail official shape and inherits solver waste).
      b. reshape: `floor_bump` → `span_rescale` (+ `floor_bump` again, which
         is the floor half of span_rescale's re-clamp) → `break_monotonic`
         (+ `_clip_to_box`, because the swap is a permutation and can land a
         baseline on a level with a different `solver_i`) → `trend_nudge`.
      c. integerize `b_i = max(floor, round(b_i))`, then re-apply the interior
         swap once if rounding collapsed the vector back to nondecreasing.
      d. cap-fit, HARD in both halves: `b_i <= cap_i` AND
         `BATTERY_MARGIN * b_i <= cap_i` (architecture §3 S4 step 4 + D8; a
         cap that truncates the 5x battery budget corrupts B9's numbers).
         `None` caps are vacuous and recorded as such.

    Violation → next attempt; attempts exhausted (`g.redraw_cap` redraws) →
    verdict `cap-fit-reject`, which architecture §3 routes to S2 as a cap bug.
    Under `g.cap_fit: record` (`_cap_fit_mode`) that last step is the only
    thing that changes: every attempt is still drawn and still cap-fitted, and
    the exhausted search returns the LAST canon-shaped vector with the fit
    verdict instead of the reject. The per-attempt `capfit` rows are untouched,
    so `attempts[-1]` carries the violation the caller records.

    The clip is `G_CLIP` under `caps.basis: legacy` (the default, byte-for-byte
    the shipped stage) and `OFFICIAL_G_BOX` under `official-band`, which is the
    officials' measured effort band read as a g box — R-05 §1 / R-22.

    Implied g of the SHIPPED integers sits inside that box up to two
    documented, measured slacks: the floor bump (which cannot itself exceed
    `G_CLIP` — `floor / solver_i <= 6` for `solver_i >= 1` — but CAN exceed the
    narrower official-band top of 2.288 when `solver_i <= 2`, recorded by
    `caps_band_block` as an out-of-band level rather than forced) and integer
    rounding, worth at most `0.5 / solver_i` per level.

    One property canon CANNOT guarantee, so it is recorded rather than forced:
    a vector pinned flat by the floor (every level at `g.floor`) admits no
    strict descent, because the interior swap is a permutation of equal
    values. `invariants.has_strict_descent` reports the truth. Measured over
    400 seeds: 0/400 at 6 and 10 levels with solver 8-60 (the official shape),
    but 65/400 at 3 levels with solver 2-4 — short solver lines are what make
    it reachable.
    """
    params = _g_params(cfg)
    cap_fit_mode = _cap_fit_mode(cfg)  # fail on a bad knob before drawing
    # R-05 §1: the ONE thing `caps.basis` changes in the draw. `legacy` returns
    # canon `G_CLIP` itself, so every line below is bit-identical to the
    # pre-R-05 stage; `official-band` substitutes the officials' effort band,
    # read as the implied-g box it is (`g = 1 / ratio`). I-1: under
    # `official-band` a configured `g.centering` supplies its own instrument's
    # box; with no centering configured this is exactly the call above.
    clip = _g_box(_caps_basis(cfg), _g_centering(cfg))
    counts = _check_solver(list(solver), len(list(solver)))
    if not counts:
        raise ValueError("solver must be non-empty — there is nothing to baseline")
    caps_list = list(caps)
    if len(caps_list) != len(counts):
        raise ValueError(f"caps has {len(caps_list)} level(s), solver has {len(counts)}")
    for index, cap in enumerate(caps_list):
        if cap is None:
            continue
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            raise ValueError(f"caps[{index}] must be an int >= 1 or None, got {cap!r}")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError(f"seed must be an int, got {seed!r}")

    mu, sigma = fit_g(cfg)
    attempts: list[dict] = []
    for attempt in range(params.redraw_cap + 1):
        rng = random.Random(seed + attempt)
        drawn = [
            min(max(math.exp(rng.gauss(mu, sigma)), clip[0]), clip[1]) for _ in counts
        ]
        values = [count * g for count, g in zip(counts, drawn, strict=True)]

        values = floor_bump(values, params.floor)
        values = span_rescale(values, counts, params.span_target, clip)
        values = floor_bump(values, params.floor)
        values = break_monotonic(values, rng)
        values = _clip_to_box(values, counts, clip)
        values = trend_nudge(values, counts, params.trend, clip)

        baselines = [max(params.floor, round(value)) for value in values]
        if len(baselines) >= 3 and not has_strict_descent(baselines):
            baselines = [
                int(value)
                for value in break_monotonic([float(v) for v in baselines], rng)
            ]

        capfit: list[dict] = []
        ok = True
        for level, (count, baseline, cap) in enumerate(
            zip(counts, baselines, caps_list, strict=True), start=1
        ):
            fits = True if cap is None else baseline <= cap
            battery_fits = True if cap is None else BATTERY_MARGIN * baseline <= cap
            capfit.append(
                {
                    "level": level,
                    "solver": count,
                    "baseline": baseline,
                    "cap": cap,
                    "fits": fits,
                    "battery_fits": battery_fits,
                }
            )
            ok = ok and fits and battery_fits

        implied = [
            baseline / count for baseline, count in zip(baselines, counts, strict=True)
        ]
        attempts.append(
            {
                "attempt": attempt,
                "g": implied,
                "baselines": baselines,
                "capfit": capfit,
                "ok": ok,
            }
        )
        if ok:
            return {
                "verdict": VERDICT_FIT,
                "baseline_actions": baselines,
                "g": implied,
                "redraws": attempt,
                "attempts": attempts,
                "invariants": _invariants(baselines, params.floor),
            }

    last = attempts[-1]
    if cap_fit_mode == CAP_FIT_RECORD:
        # The b002 deviation, and ONLY here: the last canon-shaped draw ships
        # (it passed every reshape; the one thing it failed is the cap), the
        # verdict is the fit verdict, and the violation rides `attempts[-1]`
        # for `cap_fit_block` to write into the report and metadata. The result
        # keys are the same ones a fit always carries, so every consumer of a
        # fit — metadata, the band, S5, S6 — reads exactly what it read before.
        return {
            "verdict": VERDICT_FIT,
            "baseline_actions": last["baselines"],
            "g": last["g"],
            "redraws": len(attempts) - 1,
            "attempts": attempts,
            "invariants": _invariants(last["baselines"], params.floor),
        }
    return {
        "verdict": VERDICT_REJECT,
        "baseline_actions": None,
        "g": None,
        "redraws": len(attempts) - 1,
        "attempts": attempts,
        # Reported off the LAST attempt's vector: there is no shipped vector to
        # describe, and the last attempt is the one the reject is written from.
        "invariants": _invariants(last["baselines"], params.floor),
    }


def cap_fit_block(result: Mapping, mode: str) -> dict:
    """What step 4 measured on the SHIPPED vector, as the `cap_fit` record.

    Built from `attempts[-1]`'s own cap-fit rows — the attempt whose baselines
    ship in both modes — so the block can never disagree with
    `baseline_actions`. `margin_needed` is the extra cap that level needs for
    BOTH halves of step 4 to hold (`BATTERY_MARGIN * baseline - cap`): what a
    later budget pass has to move, not a redraw hint. A `None` cap is vacuous
    and never a violation, so every row here has an int cap.
    """
    if mode not in CAP_FIT_MODES:
        raise ValueError(f"mode must be one of {list(CAP_FIT_MODES)}, got {mode!r}")
    rows = result["attempts"][-1]["capfit"]
    violations = [
        {
            "level": row["level"],
            "baseline": row["baseline"],
            "cap": row["cap"],
            "margin_needed": BATTERY_MARGIN * row["baseline"] - row["cap"],
        }
        for row in rows
        if not (row["fits"] and row["battery_fits"])
    ]
    return {"ok": not violations, "mode": mode, "violations": violations}


# --- the official-band cap policy (R-05 §1, R-22) ---------------------------


def official_band_caps(baselines: Sequence[int]) -> list[int]:
    """The per-level cap the officials' own budget convention implies.

    `cap_i = BATTERY_MARGIN * baseline_i`, and that is the WHOLE derivation —
    the officials' enforced budget IS 5x the published baseline (D8, adopted
    from the public runner: 519 of 590 death-levels at exactly 5.00x). The
    officials' effort distribution enters one step earlier, through the
    baseline: under `official-band` the draw's g box is the band itself, so
    `baseline_i = solver_i / ratio_i` with `ratio_i` inside 0.437..1.084, and
    therefore

        cap_i = 5 * solver_i / ratio_i  in  [4.61, 11.44] x solver_i
                                        (6.34 x solver_i at the 0.789 median)

    against today's shipped policy of 15-16x optimal (findings B3.3). That
    factor IS R-05's defect: a competent play moves `solver_i / cap_i` of the
    meter — 6.3% at 16x, where conduit-watch's perfect solve ends every level
    at 60/64 and 4 pixels of 64 move; 15.8% at the official-band median, and
    8.7%-21.7% across the band. The bar moves per action because the budget it
    divides is the one the officials actually run.

    Integers because a budget is a count of actions, and `>= 5 * baseline`
    exactly, never less: `BATTERY_MARGIN` is untouched by this policy (R-05's
    standing instruction) and this cap honors it by construction.
    """
    values: list[int] = []
    for index, baseline in enumerate(baselines):
        if isinstance(baseline, bool) or not isinstance(baseline, int) or baseline < 1:
            raise ValueError(f"baselines[{index}] must be an int >= 1, got {baseline!r}")
        values.append(BATTERY_MARGIN * baseline)
    if not values:
        raise ValueError("baselines must be non-empty — there is no cap to derive")
    return values


def caps_band_block(
    solver: Sequence[int],
    baselines: Sequence[int],
    measured: Sequence[int | None],
    *,
    basis: str = CAPS_BASIS_OFFICIAL_BAND,
    centering: GInstrument | None = None,
) -> dict:
    """The `official-band` record: derived caps, achieved ratios, the conflict.

    RECORD ONLY — nothing here changes a verdict, and nothing here replaces a
    measured fact. `measured_cap` is the cap probe's number (`caps.probe`:
    the burn probe by default, the allowance probe under I-1) and stays the
    cap-fit reference; `required_cap` is what this game's own budget would have
    to be for the meter to read as the officials' does, which is what a later
    budget pass (and the S2 payload) reads.

    THE FLAGGED RULING, recorded in `margin` so the report carries its own
    adjudication. R-05 §1's literal target is "baseline/cap in the officials'
    ratio band", i.e. `cap in [b/1.084, b/0.437] = [0.92 b, 2.29 b]`. D8's
    battery margin needs `cap >= 5 b`. The two intervals are DISJOINT — the
    loosest in-band cap is 2.185x tighter than the margin's floor, 3.945x at
    the 0.789 median, 5.42x at the band's tight edge (the factor is exactly
    `BATTERY_MARGIN * ratio`). No cap satisfies both, so the literal target is
    recorded per level (`literal_target_ok`) and is never a reject, and the
    band is applied where `effort.csv` actually measures it: on
    `actions / baseline`, which is the g box the draw is clipped to. Moving
    `BATTERY_MARGIN` would "resolve" it and is explicitly not on the table.

    I-1: `centering` (a `G_INSTRUMENTS` entry) re-centres the whole record on
    that instrument — its ratio median and per-game band, its source, its box.
    `None` (no `g.centering` configured) is today's effort.csv record, byte for
    byte; so is `effort-blind`, whose band and box are the same constants. The
    conflict flag is now computed (`BATTERY_MARGIN * band_lo > 1`) rather than
    written: it is True on both instruments (2.185 on effort.csv, 1.257 on D7).
    """
    if basis not in CAPS_BASES:
        raise ValueError(f"caps.basis must be one of {list(CAPS_BASES)}, got {basis!r}")
    if centering is not None and not isinstance(centering, GInstrument):
        raise TypeError(f"centering must be a GInstrument or None, got {centering!r}")
    if centering is None:
        (lo, hi), median_ref, source = OFFICIAL_RATIO_BAND, OFFICIAL_RATIO_MEDIAN, EFFORT_SOURCE
    else:
        (lo, hi), median_ref, source = (
            centering.ratio_band, centering.ratio_median, centering.source
        )
    counts = _check_solver(list(solver), len(list(solver)))
    required = official_band_caps(baselines)
    # Materialised once: every length check and every zip below reads the same
    # rows, which an iterator argument would not guarantee.
    measured_caps = list(measured)
    if not (len(counts) == len(required) == len(measured_caps)):
        raise ValueError(
            f"solver has {len(counts)} level(s), baselines {len(required)}, "
            f"measured {len(measured_caps)} — one row per level or nothing"
        )

    rows: list[dict] = []
    ratios: list[float] = []
    for level, (count, baseline, cap_required, cap_measured) in enumerate(
        zip(counts, baselines, required, measured_caps, strict=True), start=1
    ):
        ratio = count / baseline
        ratios.append(ratio)
        rows.append(
            {
                "level": level,
                "solver": count,
                "baseline": int(baseline),
                # `ratio` is effort.csv's own quantity: actions / baseline.
                "ratio": ratio,
                "in_band": lo <= ratio <= hi,
                "measured_cap": cap_measured,
                "required_cap": cap_required,
                # What the game's budget has to gain. `None` when nothing was
                # measured — an unknown gap is not a zero gap.
                "cap_shortfall": None if cap_measured is None else cap_required - cap_measured,
                # The meter-travel number R-05 is about: the share of the
                # budget one competent play consumes.
                "budget_fraction": count / cap_required,
                # The literal §1 target, recorded because it cannot be met
                # alongside the margin — see the docstring.
                "literal_target_ok": lo <= baseline / cap_required <= hi,
            }
        )

    median_ratio = float(np.median(np.asarray(ratios, dtype=float)))
    return {
        "basis": basis,
        "source": source,
        "ratio": {"median": median_ref, "band": [lo, hi]},
        "g_box": list(_g_box(basis, centering)),
        "required": required,
        "ratio_median_achieved": median_ratio,
        # R-22's acceptance, per game: the MEDIAN ratio inside the officials'
        # observed span. Per-level excursions are expected (the officials' own
        # per-level ratios run 0.116..4.333); the median is the datum.
        "in_band": lo <= median_ratio <= hi,
        "levels": rows,
        "margin": {
            "battery_margin": BATTERY_MARGIN,
            # 5b <= 5b, by construction, on every level.
            "satisfied_by_required": all(
                BATTERY_MARGIN * int(baseline) <= cap
                for baseline, cap in zip(baselines, required, strict=True)
            ),
            "literal_target": "baseline/cap inside the officials' ratio band",
            # The loosest in-band cap still sits below 5b exactly when
            # 5 * band_lo > 1 — True on both instruments (see the docstring).
            "literal_target_conflicts": BATTERY_MARGIN * lo > 1.0,
            "shortfall_factor": {
                "loosest": BATTERY_MARGIN * lo,
                "median": BATTERY_MARGIN * median_ref,
                "tightest": BATTERY_MARGIN * hi,
            },
        },
    }


# --- the batch band (D9 — RECORD ONLY) --------------------------------------


def batch_band(g_vectors: list[list[float]], cfg: Mapping) -> dict:
    """Record the batch's g distribution against the config band. Never gates.

    D9 (LOCKED): calibration is fleet-level only — ICC(1) on the play ratio is
    -0.024 at 183 levels, so the game explains none of the variance and a
    per-game difficulty target is never set or tested. architecture §3 S4 step
    5 says the same operationally: "individual games are NEVER re-tuned — a
    failing batch adjusts the NEXT batch's g-params".

    `within` is therefore a RECORD, at a deliberately generous tolerance
    (+-25% on the median and on each IQR endpoint): at the pilot's n=1 game
    the sample is a handful of levels, and the R-protocol — not this
    function — judges a real batch. Nothing here can change a verdict.
    """
    params = _g_params(cfg)
    if not isinstance(g_vectors, Sequence) or isinstance(g_vectors, str):
        raise TypeError(f"g_vectors must be a sequence of vectors, got {g_vectors!r}")
    if not g_vectors:
        raise ValueError("batch_band needs at least one g vector — an empty batch is a bug")
    values: list[float] = []
    for index, vector in enumerate(g_vectors):
        values.extend(_check_vector(vector, f"g_vectors[{index}]"))

    array = np.asarray(values, dtype=float)
    median_g = float(np.median(array))
    q1 = float(np.percentile(array, 25))
    q3 = float(np.percentile(array, 75))
    return {
        "median_g": median_g,
        "iqr_g": [q1, q3],
        "config": {
            "median": params.median,
            "iqr": [params.q1, params.q3],
            "tolerance": BAND_TOLERANCE,
            "games": len(g_vectors),
            "levels": len(values),
        },
        "within": {
            "median": abs(median_g - params.median) <= BAND_TOLERANCE * params.median,
            "iqr": (
                abs(q1 - params.q1) <= BAND_TOLERANCE * params.q1
                and abs(q3 - params.q3) <= BAND_TOLERANCE * params.q3
            ),
        },
    }


# --- seeding ----------------------------------------------------------------


def derive_seed(cfg: Mapping, game_id: str) -> int:
    """The game's S4 rng seed from the batch seed (D13-style derivation).

    `sha256("<batch.seed>:<game_id>:s4")[:8]` — stable across runs, different
    per game and per stage, and recorded in `metadata.rng_seed` so the whole
    draw replays (architecture §3 S4 Executor: "pure code, deterministic given
    `metadata.rng_seed`"). An explicit `--seed` overrides it.
    """
    if not isinstance(cfg, Mapping):
        raise TypeError(f"cfg must be a mapping, got {type(cfg).__name__}")
    batch = cfg.get("batch")
    if not isinstance(batch, Mapping) or "seed" not in batch:
        raise ValueError("config has no 'batch.seed' — S4 cannot derive a per-game seed")
    batch_seed = batch["seed"]
    if isinstance(batch_seed, bool) or not isinstance(batch_seed, int):
        raise TypeError(f"batch.seed must be an int, got {batch_seed!r}")
    if not isinstance(game_id, str):
        raise TypeError(f"game_id must be a string, got {type(game_id).__name__}")
    if not game_id:
        raise ValueError("game_id must be non-empty — the seed is derived from it")
    digest = hashlib.sha256(f"{batch_seed}:{game_id}:s4".encode()).hexdigest()
    return int(digest[:8], 16)


# --- the stage --------------------------------------------------------------


def _versions() -> dict:
    return {
        "arcengine": importlib.metadata.version("arcengine"),
        "python": platform.python_version(),
    }


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _caps_status(caps: Sequence[int | None], has_lose: bool, probe: str) -> tuple[str, str | None]:
    """`(caps.status, caps.note)` for one caps vector — R-05 §2's three-way split.

    "No measurable cap" is LOUD, never a silent pass: nothing measured and no
    `lose()` is the premise not being met (the honest old answer); nothing
    measured WITH a `lose()` wired is `unmeasured`, because that game declares a
    budget the probe cannot find and every cap-fit row on it is vacuous.
    Anything measured is `measured`, with no note. Under the burn probe the two
    notes are the pre-I-1 strings verbatim; the allowance probe says what IT
    could not find.
    """
    if probe not in CAPS_PROBES:
        raise ValueError(f"caps.probe must be one of {list(CAPS_PROBES)}, got {probe!r}")
    caps = list(caps)
    if any(cap is not None for cap in caps):
        return CAPS_MEASURED, None
    if has_lose:
        if probe == CAPS_PROBE_BURN:
            note = (
                f"no cap measurable on any of {len(caps)} level(s) within {BURN_BOUND} burn "
                "action(s), although the game DOES call lose() — every cap-fit row is vacuous, "
                "so this game ships uncalibrated by the check S4 exists to run (R-05 §2)"
            )
        else:
            note = (
                f"no allowance measurable on any of {len(caps)} level(s): no probe play's "
                f"GAME_OVER within {BURN_BOUND} action(s) was count-attributable (each one fell "
                "below the solver's own line in that level, or was caused by the action "
                "played), although the game DOES call lose() — every cap-fit row is vacuous, "
                "so this game ships uncalibrated by the check S4 exists to run (R-05 §2, I-1)"
            )
        return CAPS_UNMEASURED, note
    return CAPS_PREMISE_NOT_MET, (
        f"no cap measurable on any of {len(caps)} level(s): the game calls no lose(), "
        "so there is no budget to measure and cap-fit has no premise (R-05 §2)"
    )


def run_s4(
    worker_dir: Path,
    cfg: Mapping,
    *,
    seed: int | None = None,
    out_dir: Path | None = None,
) -> dict:
    """Run the whole stage for one worker and write its outputs.

    Output dir = `out_dir` or the worker SIBLING `<worker>.s4/` (the B3/B7
    rule: never inside the worker). Written there:

    * `actions/level-<i>.json` — ALWAYS. They are facts about the solver line
      and do not depend on the verdict.
    * `s4-report.json` — ALWAYS: the full draw result plus the cap
      measurement, the band record, the seed and the paths.
    * `metadata.json` — ONLY on verdict `fit`, in the officials' shape
      (`baseline_actions` a plain int list, exactly as the 25 officials ship
      it). On a reject an existing one is removed: a metadata that contradicts
      its own report would poison the battery downstream.

    Under `g.cap_fit: record` the report and the metadata each gain ONE key, a
    `cap_fit` block (`cap_fit_block`), so a shipped over-cap vector says so in
    both places a later pass reads. In `hard`/`reject` mode nothing here changes
    at all.

    Under `caps.basis: official-band` (R-05 §1) the report's `caps` block gains
    `basis` + `band` (`caps_band_block`) and the metadata gains `caps_basis` +
    `caps_required`. Under `legacy` — the default — neither appears, and the
    whole stage is the pre-R-05 stage.

    ONE unconditional change, R-05 §2 and deliberately outside the knob: when
    NO level yields a measurable cap, `caps.status` and a new `caps.note` say
    so. A game that calls `lose()` and still measures nothing is `unmeasured`
    where it used to read `measured` — the silent pass the audit names. Games
    with a measurable cap are untouched, and `metadata.json` never carries the
    note, so metadata stays byte-identical in every case.

    I-1, two more knobs, the same principle — absent writes nothing new:
    `caps.probe: allowance` makes the allowance probe's numbers the caps
    everywhere (status, cap-fit, band, `metadata.caps`) and adds `caps.probe` +
    `caps.legacy_burn` to the report and `caps_probe` + `caps_legacy_burn` to
    the metadata; `g.centering` adds a `centering` record under `config.g`
    (and so under `metadata.provenance.g_config`).

    Nothing written here is time-stamped or path-random, so the same seed
    gives byte-identical files on a re-run.
    """
    worker_dir = Path(worker_dir).resolve()
    if not worker_dir.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker_dir}")
    params = _g_params(cfg)  # fail on a bad config before driving anything
    probe = _caps_probe(cfg)  # I-1 knob, same rule
    centering = _g_centering(cfg)
    target = Path(out_dir) if out_dir is not None else worker_dir.parent / (
        worker_dir.name + OUT_SUFFIX
    )
    target = target.resolve()

    lines = solver_lines(worker_dir)
    action_paths = write_actions(lines, target)
    solver_counts = [len(level) for level in lines.per_level]

    caps, caps_detail = _measure_caps_detail(worker_dir, lines)
    has_lose = _has_lose_call(worker_dir)
    # I-1: under `caps.probe: allowance` the allowance probe's numbers become
    # THE caps (status, cap-fit, band, metadata) and the burn probe's — measured
    # above exactly as before — ride beside them, labelled, for one release.
    legacy_burn = None
    if probe == CAPS_PROBE_ALLOWANCE:
        legacy_status, _legacy_note = _caps_status(caps, has_lose, CAPS_PROBE_BURN)
        legacy_burn = {
            "label": LEGACY_BURN_LABEL,
            "values": list(caps),
            "status": legacy_status,
            "levels": caps_detail,
        }
        caps, caps_detail = _measure_allowance_detail(worker_dir, lines)
    caps_status, caps_note = _caps_status(caps, has_lose, probe)

    rng_seed = seed if seed is not None else derive_seed(cfg, lines.game_id)
    if isinstance(rng_seed, bool) or not isinstance(rng_seed, int):
        raise TypeError(f"seed must be an int, got {rng_seed!r}")
    mu, sigma = fit_g(cfg)
    result = draw_baselines(solver_counts, list(caps), cfg, rng_seed)

    metadata_path = target / METADATA_NAME
    report_path = target / REPORT_NAME
    band = batch_band([result["g"]], cfg) if result["g"] is not None else None
    # `hard` writes no block anywhere: canon behavior is the default and stays
    # byte-for-byte what it was (b002 design principle).
    cap_fit_mode = _cap_fit_mode(cfg)
    cap_fit = cap_fit_block(result, cap_fit_mode) if cap_fit_mode == CAP_FIT_RECORD else None
    # R-05 §1, same principle: `legacy` writes no basis key and no band block,
    # so an unconfigured report is the pre-R-05 report.
    basis = _caps_basis(cfg)
    caps_band = (
        caps_band_block(
            solver_counts, result["baseline_actions"], list(caps), basis=basis,
            centering=centering,
        )
        if basis == CAPS_BASIS_OFFICIAL_BAND and result["baseline_actions"] is not None
        else None
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": "s4",
        "game_id": lines.game_id,
        "worker": str(worker_dir),
        "out_dir": str(target),
        "rng_seed": rng_seed,
        "seed_source": "explicit" if seed is not None else "batch",
        "verdict": result["verdict"],
        "solver": {
            "levels": lines.levels_completed,
            "actions_per_level": solver_counts,
            "actions_total": sum(solver_counts),
            "win": lines.win,
            "described": [list(level) for level in lines.described],
        },
        "caps": {
            "status": caps_status,
            "values": list(caps),
            "bound": BURN_BOUND,
            "battery_margin": BATTERY_MARGIN,
            "has_lose_call": has_lose,
            "levels": caps_detail,
        },
        "g_fit": {"mu": mu, "sigma": sigma, "clip": list(_g_box(basis, centering))},
        "result": result,
        "band": band,
        "config": {
            "g": {
                "median": params.median,
                "iqr": [params.q1, params.q3],
                "floor": params.floor,
                "span_target": params.span_target,
                "trend": params.trend,
                "redraw_cap": params.redraw_cap,
            }
        },
        "paths": {
            "metadata": str(metadata_path) if result["verdict"] == VERDICT_FIT else None,
            "actions": [str(path) for path in action_paths],
            "report": str(report_path),
        },
        "versions": _versions(),
    }
    if caps_note is not None:
        # R-05 §2. Nested under `caps`, beside the status it explains, so every
        # b8-era reader (which key-checks `caps` by membership) is untouched.
        report["caps"]["note"] = caps_note
    if basis != CAPS_BASIS_LEGACY:
        report["caps"][CAPS_BASIS_KEY] = basis
    if caps_band is not None:
        report["caps"]["band"] = caps_band
    if legacy_burn is not None:
        # I-1. `burn` (the default) writes neither key: an unconfigured report
        # is the pre-I-1 report.
        report["caps"][CAPS_PROBE_KEY] = probe
        report["caps"][LEGACY_BURN_KEY] = legacy_burn
    if centering is not None:
        # I-1. Under `config.g`, so `metadata.provenance.g_config` (the same
        # dict) carries it too: which instrument centred this draw, and the
        # configured literals it replaced.
        configured = cfg["g"]
        report["config"]["g"][G_CENTERING_KEY] = {
            "instrument": centering.name,
            "adjudicated": centering.adjudicated,
            "label": centering.label,
            "quantity": centering.quantity,
            "source": centering.source,
            "levels": centering.levels,
            "games": centering.games,
            "configured": {
                "median": _as_float(configured["median"], "g.median"),
                "iqr": [
                    _as_float(configured["iqr"][0], "g.iqr[0]"),
                    _as_float(configured["iqr"][1], "g.iqr[1]"),
                ],
            },
        }
    if cap_fit is not None:
        report[CAP_FIT_KEY] = cap_fit

    if result["verdict"] == VERDICT_FIT:
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "game_id": lines.game_id,
            "baseline_actions": result["baseline_actions"],
            "g": result["g"],
            "solver_actions": solver_counts,
            "caps": list(caps),
            "rng_seed": rng_seed,
            "verdict": result["verdict"],
            "provenance": {
                "g_config": report["config"]["g"],
                "arcengine": report["versions"]["arcengine"],
                "python": report["versions"]["python"],
            },
        }
        if cap_fit is not None:
            # Appended, never folded into `provenance`: S5 and S6 load this file
            # through `s5_battery.load_battery_metadata`, which reads
            # `verdict` + `baseline_actions` and passes every other key through
            # untouched, so an extra top-level key is inert downstream.
            metadata[CAP_FIT_KEY] = cap_fit
        if caps_band is not None:
            # Two keys, same inert-append rule. `caps` above keeps the MEASURED
            # vector — the cap probe's fact — and these say which policy drew
            # the baselines and what budget that policy requires of the game,
            # which is what a later budget pass (and R-05's S2 payload work)
            # reads. Never the other way round: a derived number standing in
            # `caps` would be the provenance lie this module's header forbids.
            metadata["caps_basis"] = basis
            metadata["caps_required"] = caps_band["required"]
        if legacy_burn is not None:
            # I-1, same inert-append rule: `caps` above is the allowance — the
            # cap-fit reference — and the burn figure stays beside it, labelled,
            # for one release.
            metadata["caps_probe"] = probe
            metadata["caps_legacy_burn"] = {
                "label": legacy_burn["label"],
                "values": legacy_burn["values"],
            }
        _write_json(metadata_path, metadata)
    elif metadata_path.is_file():
        metadata_path.unlink()

    _write_json(report_path, report)
    return report


# --- process isolation (b002 hotfix 3) --------------------------------------
# Same mechanism `gen/frames.py` documents under "Process isolation": the
# GENERATED solver looks its sibling game module up in `sys.modules` under a
# PATH-derived name, so a long-lived process that re-implements `game.py`
# hands the next drive a FRESH game and a STALE solver plan. S4 DRIVES the
# solver (`solver_lines`), so it is exposed to exactly that: measured, a drive
# that died a few actions in here came back winning in a fresh interpreter.
# No rule about how generated code caches its imports is available to us, so
# the fix is the same one: an empty `sys.modules` cannot serve stale code.

# Wall-clock bound on ONE isolated S4. Generous by design — the stage drives
# the solver AND burns up to `BURN_BOUND` actions per level — because the only
# thing this number has to catch is a child that never comes back at all.
DEFAULT_S4_TIMEOUT_S = 1800.0


class S4ProcessError(RuntimeError):
    """An isolated S4 did not come back with a readable report."""


def _load_cfg_json(path: Path) -> dict:
    """An ALREADY-RESOLVED config, read verbatim — no `load_config` pass.

    The parent resolved (and canon-checked) the config once; re-resolving it in
    the child would make the child fail on a canon tree it never reads. This
    stage touches only `cfg["g"]`, `cfg.get("caps")` and `cfg.get("batch")` —
    scalars, including both I-1 knobs — so the JSON round-trip is lossless for
    it.
    """
    with Path(path).open(encoding="utf-8") as fh:
        cfg = json.load(fh)
    if not isinstance(cfg, dict):
        raise TypeError(f"--cfg-json did not parse to a mapping: {path}")
    return cfg


def run_s4_isolated(
    worker_dir: Path | str,
    cfg: Mapping,
    *,
    seed: int | None = None,
    out_dir: Path | None = None,
    timeout_s: float = DEFAULT_S4_TIMEOUT_S,
) -> dict:
    """`run_s4` in a FRESH interpreter — the same stage, the same report.

    Runs `python -m gen.s4_baselines --worker … --cfg-json … --out …` under
    THIS interpreter (`sys.executable`, i.e. the venv) with `cwd=REPO_ROOT`
    (so `-m gen.s4_baselines` resolves whether or not the package is
    installed), `stdin` at DEVNULL (an inherited pipe is a silent forever-hang
    in headless runs — the B0 driver lesson in `gen/backends.py`) and absolute
    paths throughout, then reads `s4-report.json` back and returns it. Every
    file the stage writes is written by the child, exactly where `run_s4`
    would have written it.

    EXIT CODES ARE NOT THE VERDICT: `main` exits 0 on a fit and 2 on a cap-fit
    reject, and both are real verdicts with a full report on disk. So a report
    that exists, parses and carries a `verdict` is RETURNED whatever the exit
    code. A timeout, a missing report, an unparsable one or one without a
    verdict raises `S4ProcessError` quoting the tail of the child's stderr.
    """
    worker = Path(worker_dir).resolve()
    if not worker.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker}")
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or timeout_s <= 0:
        raise ValueError(f"timeout_s must be a positive number, got {timeout_s!r}")
    target = Path(out_dir) if out_dir is not None else worker.parent / (worker.name + OUT_SUFFIX)
    target = target.resolve()

    report_path = target / REPORT_NAME
    # An earlier run's report in this dir would be indistinguishable from this
    # run's once the child crashes before writing — and returning a verdict
    # measured on other bytes is the whole defect class this fix is about.
    report_path.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="gen-s4-") as tmp:
        cfg_path = Path(tmp) / "cfg.json"
        # `default=str` so a config carrying resolved Paths still serializes;
        # nothing this stage reads is anything but a scalar.
        cfg_path.write_text(json.dumps(cfg, default=str), encoding="utf-8")
        cmd = [
            sys.executable,
            "-m",
            "gen.s4_baselines",
            "--worker",
            str(worker),
            "--cfg-json",
            str(cfg_path),
            "--out",
            str(target),
        ]
        if seed is not None:
            # Not coerced (the `frames` rule): a non-int seed must die in the
            # child's argparse and surface as an S4ProcessError, never be
            # rounded here into a draw nobody asked for.
            cmd += ["--seed", str(seed)]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=float(timeout_s),
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            raise S4ProcessError(
                f"isolated S4 of {worker} exceeded {float(timeout_s):.0f}s and was killed. "
                f"partial stderr: {_stderr_tail(exc.stderr)}"
            ) from exc

    if not report_path.is_file():
        raise S4ProcessError(
            f"isolated S4 of {worker} exited {proc.returncode} and wrote no report to "
            f"{report_path}. stderr: {_stderr_tail(proc.stderr)}"
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise S4ProcessError(
            f"isolated S4 of {worker} wrote unparsable JSON to {report_path} ({exc}). "
            f"stderr: {_stderr_tail(proc.stderr)}"
        ) from exc
    if not isinstance(report, dict) or "verdict" not in report:
        raise S4ProcessError(
            f"isolated S4 of {worker} exited {proc.returncode} and wrote a "
            f"{REPORT_NAME} with no 'verdict'. stderr: {_stderr_tail(proc.stderr)}"
        )
    return report


# --- CLI --------------------------------------------------------------------


def _fmt(values: Sequence) -> str:
    return ",".join("none" if value is None else str(value) for value in values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S4 baseline assigner — the g-sampler + hard cap-fit"
    )
    parser.add_argument("--worker", required=True, help="worker dir holding game.py + solver.py")
    parser.add_argument(
        "--seed", type=int, default=None, help="override the batch-derived rng seed"
    )
    parser.add_argument("--out", default=None, help="write outputs here instead of <worker>.s4/")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--config", default=DEFAULT_CONFIG)
    source.add_argument(
        "--cfg-json",
        default=None,
        help="an ALREADY-RESOLVED config as JSON (what `run_s4_isolated` passes its child)",
    )
    args = parser.parse_args(argv)

    cfg = _load_cfg_json(args.cfg_json) if args.cfg_json else load_config(args.config)
    worker = Path(args.worker).resolve()
    if not worker.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker}")

    report = run_s4(
        worker, cfg, seed=args.seed, out_dir=Path(args.out) if args.out else None
    )
    result = report["result"]
    invariants = result["invariants"]
    trend = invariants["trend_achieved"]
    print(
        f"[s4] {report['verdict'].upper()} {report['game_id']} | "
        f"{report['solver']['levels']} level(s) | solver {_fmt(report['solver']['actions_per_level'])} "
        f"| baselines {_fmt(result['baseline_actions'] or [])} | redraws {result['redraws']} "
        f"| seed {report['rng_seed']} ({report['seed_source']})"
    )
    print(
        f"[s4] caps {_fmt(report['caps']['values'])} ({report['caps']['status']}, "
        f"bound {BURN_BOUND}, {BATTERY_MARGIN}x margin) | span "
        f"{invariants['span_achieved']:.2f}/{report['config']['g']['span_target']:g} | trend "
        f"{'n/a' if trend is None else format(trend, '+.2f')}/"
        f"{report['config']['g']['trend']:+g} | descent {invariants['has_strict_descent']}"
    )
    if report["band"] is not None:
        band = report["band"]
        print(
            f"[s4] band: median {band['median_g']:.2f} iqr "
            f"{band['iqr_g'][0]:.2f}-{band['iqr_g'][1]:.2f} vs config "
            f"{band['config']['median']:.2f} {band['config']['iqr'][0]:.2f}-"
            f"{band['config']['iqr'][1]:.2f} | within {band['within']} (D9: record only)"
        )
    centering = report["config"]["g"].get(G_CENTERING_KEY)
    if centering is not None:
        print(
            f"[s4] g.centering {centering['instrument']} "
            f"({'adjudicated' if centering['adjudicated'] else 'named alternative'}) | "
            f"median {report['config']['g']['median']:g} iqr "
            f"{report['config']['g']['iqr'][0]:g}-{report['config']['g']['iqr'][1]:g} "
            f"replaced configured {centering['configured']['median']:g} "
            f"{centering['configured']['iqr'][0]:g}-{centering['configured']['iqr'][1]:g}"
        )
    legacy_burn = report["caps"].get(LEGACY_BURN_KEY)
    if legacy_burn is not None:
        print(
            f"[s4] caps.probe {report['caps'][CAPS_PROBE_KEY]} | caps "
            f"{_fmt(report['caps']['values'])} | legacy burn (death-by-repetition, recorded "
            f"for comparability) {_fmt(legacy_burn['values'])}"
        )
    caps_note = report["caps"].get("note")
    if caps_note is not None:
        # R-05 §2: the condition that used to pass in silence, said out loud on
        # the console as well as in the report.
        print(f"[s4] NO MEASURABLE CAP ({report['caps']['status']}) — {caps_note}")
    caps_band = report["caps"].get("band")
    if caps_band is not None:
        rows = caps_band["levels"]
        short = [row for row in rows if row["cap_shortfall"] not in (None, 0)]
        print(
            f"[s4] caps.basis {caps_band['basis']} | ratio median "
            f"{caps_band['ratio_median_achieved']:.3f} vs officials "
            f"{caps_band['ratio']['median']:.3f} "
            f"{caps_band['ratio']['band'][0]:.3f}-{caps_band['ratio']['band'][1]:.3f} | "
            f"in band {caps_band['in_band']} | required caps "
            f"{_fmt(caps_band['required'])} | budget fraction "
            f"{min(row['budget_fraction'] for row in rows):.3f}-"
            f"{max(row['budget_fraction'] for row in rows):.3f}"
        )
        if short:
            detail = "; ".join(
                f"L{row['level']} measured {row['measured_cap']} needs {row['required_cap']} "
                f"(+{row['cap_shortfall']})"
                for row in short
            )
            print(f"[s4] BUDGET SHORTFALL vs the official-band policy — {detail}")
    cap_fit = report.get(CAP_FIT_KEY)
    if cap_fit is not None and not cap_fit["ok"]:
        # One LOUD line: this game ships over its own cap. `record` mode keeps
        # it moving through the pipeline (b002 ruling, 2026-09-24), and this is
        # the line that says the later budget pass has work to do here.
        detail = "; ".join(
            f"L{row['level']} baseline {row['baseline']} vs cap {row['cap']} "
            f"(needs +{row['margin_needed']} for the {BATTERY_MARGIN}x margin)"
            for row in cap_fit["violations"]
        )
        print(
            f"[s4] CAP-FIT VIOLATION RECORDED (g.cap_fit: {cap_fit['mode']}) — "
            f"{detail} | baselines SHIPPED anyway; budget calibration is a later pass"
        )
    if report["verdict"] != VERDICT_FIT:
        for attempt in result["attempts"]:
            bad = [
                f"L{row['level']} baseline {row['baseline']} vs cap {row['cap']}"
                f"{'' if row['fits'] else ' (over cap)'}"
                f"{'' if row['battery_fits'] else f' (5x={BATTERY_MARGIN * row['baseline']} over cap)'}"
                for row in attempt["capfit"]
                if not (row["fits"] and row["battery_fits"])
            ]
            print(f"[s4] reject attempt {attempt['attempt']}: {'; '.join(bad)}")
        print("[s4] route: S2 (cap bug) — architecture §3 S4 failure routing")
    if report["paths"]["metadata"]:
        print(f"[s4] metadata: {report['paths']['metadata']}")
    print(f"[s4] actions: {len(report['paths']['actions'])} file(s) in {report['out_dir']}")
    print(f"[s4] report: {report['paths']['report']}")
    return 0 if report["verdict"] == VERDICT_FIT else 2


if __name__ == "__main__":
    sys.exit(main())
