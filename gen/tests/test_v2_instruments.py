"""BLIND pins for frozen contract I-1 — the two S4 instrument reworks (N1-N4).

Run: .venv/bin/python -m pytest gen/tests/test_v2_instruments.py -q

WRITTEN BLIND, from `docs/v2/contracts/I-1-instrument-rework.md` ("Blind lane",
pins N1-N4) alone. The implementer's diff, their pin file
(`test_i1_instruments.py`) and every uncommitted change to `gen/s4_baselines.py`
were never read. What this file was allowed to know, and does:

  * the committed tree at 23e7392 — `gen/s4_baselines.py`'s assigner surfaces
    and its burn probe (`_level_cap` / `_burn`: replay the solver prefix, burn
    the FIRST qualifying declared action until GAME_OVER), read through
    `git show HEAD:` and driven from a `git archive HEAD gen` export in the
    writer's scratchpad so the pre-state was measured on HEAD's own bytes;
  * the S4 rigs of `test_b8_baselines.py` / `test_w3_caps.py` (the fixture
    worker idiom, the minimal `g:` block, the tmp-copy discipline);
  * the audit records the contract names as ground truth: out/pilot/
    b003-freeze.md addendum 16 ("WAVE 3 COMPLETE", the R-05/R-22 paragraph —
    "the burn probe measures death-by-repetition not budget.cap — the real
    R-22 defect"; "D7 (replay ratio) vs effort.csv (human play) are different
    instruments — re-centering g.median 2.00 -> 1.267 is THE OPERATOR'S CALL"),
    IMPLEMENTATION.md's WAVES 1-3 block, audit/comparative/
    refinement-contracts.md R-05/R-22, findings.md C4, tracks/m2-mechanics.md
    §5, and `audit/comparative/data/effort.csv` (READ-ONLY);
  * canon for what the two instruments ARE: canon/spec-v0.3.md §8 and duckWM
    design/decisions.md D7 + difficulty-model.md §2.1 (read-only).

THE TWO g INSTRUMENTS, from their own provenance:
  D7 (today's g.median = 2.00, IQR 1.54-2.96, n=183) is "site baseline ÷
      competent replay" — our play programme's REPLAY-mode counts (solution
      known), one human per game. `g = baseline / line`, so D7 is a g directly.
  effort.csv (comparative audit M-2 §5) is `ratio = actions / baseline` over
      the 25 officials' `features-level.csv` human plays: officials median
      0.789 (n=183). On our side the ratio is exactly `1 / g`, so this
      instrument centers g at 1 / 0.789 = 1.267 — the audit's own figure. The
      two disagree by 0.73 in g (test_n2_* re-derives both from checked-in
      data).

THE N3 FIXTURE — repetition-death and budget.cap made to DIVERGE.
  A generated tmp worker (game.py + solver.py written by `_write_worker`; one
  file is all this lane may add, so the fixture lives here as source text).
  16x16 board, the officials' budget triple (spec §2 row 3, the
  `capped_generous` idiom): a per-level counter charged on EVERY action incl.
  blocked moves, a row-0 meter, exhaustion -> lose() with the win check FIRST.
  The player starts at (1,12); the goal is `dx` cells right (the solver line =
  dx x ACTION4). On a DIVERGENT level a pit sits `k` cells straight up and
  stepping onto it calls lose() with the budget NOT exhausted; on a CONTROL
  level a wall sits directly above, so ACTION1 is a charged refusal. ACTION2
  and ACTION3 are charged refusals (walls) on every level.

  HEAD's probe burns ACTION1 (the first qualifying id) and reports the death
  count: `k` on a divergent level (death by REPETITION — walking the same way
  into the pit) and `C` on a control level (death by BUDGET). Any honest
  measurement of what budget.cap bounds reads `C` everywhere — burning ACTION2
  or ACTION3 dies at exactly `C` on every level (engine-verified in
  test_n0_fixture_diverges_at_the_engine; `k >= 2`, so a one-press probe
  still qualifies ACTION1 and an up/down oscillation never reaches the pit).

      variant   per level (dx, C, k)            HEAD probe (old)   budget.cap
      BASE      (2,41,3) (3,53,-) (4,67,5)      [3, 53, 5]         [41, 53, 67]
      CAP       (2,47,3) (3,59,-) (4,73,5)      [3, 59, 5]         [47, 59, 73]
      PIT       (2,41,6) (3,53,-) (4,67,2)      [6, 53, 2]         [41, 53, 67]
      CONTROL   (2,131,-) (3,157,-) (4,173,-)   [131, 157, 173]    same

  CAP moves C with k fixed: the old figure stays put on the divergent levels,
  budget.cap moves. PIT moves k with C fixed: the old figure moves, budget.cap
  does not. A figure that tracks C through both is a function of budget.cap's
  bounded quantity and of nothing the repetition-death controls; level 2 is
  the agreement level where both phenomena coincide (the unit check). Caps
  are odd primes-ish and never multiples of 5, so no `5 x baseline` vector
  (official-band's derived caps) can coincide with them.

PRE-STATE FACTS (measured on the HEAD export, frozen below):
  P1 unconfigured BASE: verdict cap-fit-reject (no baseline >= 6 fits a cap of
     3 with the 5x margin), caps [3, 53, 5], rng_seed 2196337548 (batch seed
     11), attempts [[6,18,12],[6,6,6],[6,18,10],[7,6,10]].
  P2 HEAD-era knobs (g.cap_fit record + caps.basis official-band) on BASE:
     verdict fit, baselines [6, 6, 6], caps [3, 53, 5] + the band block.
  P3 unconfigured CONTROL: verdict fit, redraws 0, baselines [6, 18, 12],
     caps [131, 157, 173].
  P4 `run_s4_isolated` writes the same normalized bytes as in-process.
  P5 HEAD's S4 reads exactly HEAD_READ_KEYS from its config (a read-logging
     config driven through run_s4); 114 module-level names (HEAD_S4_NAMES).
  P6 No HEAD surface yields the budget vector, a g center within 0.005 of
     1.2667, or a labeled D7 (2.00, 1.54, 2.96) alternative — so N2/N3/N4 are
     RED on the pre-I-1 tree and N1 (+ the N0/N2-data premises) are green.

WRITER'S CONTROLS (mock reworks the writer built from HEAD's source in its
scratchpad — NOT the implementer's code — to prove the probes can go green
and can go red for the right reason):
  A  caps.probe knob + G_CENTERINGS {d7-replay, effort-csv} + g.centering,
     old figure at caps.burn_values ............................. all green
  B  g.cap_probe knob, PROBE_KINDS enum, D7_REPLAY_CENTER dataclass,
     template g.median 1.27, old figure as a per-level column ..... all green
  A-offby1 (reworked figure C-1) ........................ N3 + N4(probe) red
  A-nolabel (old figure left bare at caps.values) ............ N4(probe) red
  A-dropold (old figure not recorded) ........................ N4(probe) red
  A-default (rework made the code default) ........ N1 red (+ N0 premise red)
  A-wrongcenter (knob centers at 1.30, constant says 1.2667) ...... N2 red
  C  function-only rework, no re-centering .... N3 green; N2, N4 x2 red

READINGS TAKEN (ambiguities, reported — never invented quietly):
  A. "The instrument the implementer's memo names" (N2). The memo is a
     handback section this lane cannot read. Reading: effort.csv. The audit's
     own words name the target ("re-centering g.median 2.00 -> 1.267"), and
     the contract's verb "re-center" presupposes the adjudicated ruler is NOT
     D7's (re-centering on D7 moves nothing). If the memo names D7, N2 is a
     false red for the lead to retarget. The derivation is recomputed from
     effort.csv at test time (n=183 guard) and accepted at D7's own quoted
     precision (2 dp, tolerance 0.005: 1.27, 1.267, 1.2667 and 1/0.789 all
     pass). Only the CENTER is pinned: a re-centered IQR is underdetermined
     (shifted, scaled, or re-derived quartiles are all defensible).
  B. Where the re-centered statistic lives (N2) is probed on four channels:
     a knob the assigner READS (logged by driving run_s4 with a read-logging
     config) whose setting moves `fit_g`'s center; a named module constant
     (gen.s4_baselines or a NEW gen module) whose path says median/center/
     effort/g; a new zero-arg helper so named; or config/template.yaml's
     g.median. PRECEDENCE: if any knob moves fit_g's center off 2.00, that
     center IS the statistic the sampler runs on and one such setting must
     land on the target (a matching constant cannot rescue a knob that
     centers elsewhere — writer's control A-wrongcenter); only with no such
     knob do the static channels decide.
  C. Where the reworked probe lives (N3) is probed the same way: every knob
     the assigner newly reads UNION every new *_KEY constant under caps:/g:/
     top level (a read hidden behind `cfg.get("caps") or {}` is invisible to
     the log; a declared key constant is not) set to every new identifier-like constant /
     enum member / mapping name (+ True) — each driven end-to-end through
     run_s4 with every JSON the stage writes harvested — plus new or newly
     keyworded `(worker_dir, lines)` callables. N3 passes iff ONE surface, at
     ONE path, equals budget.cap on all three variants. The quantifier is
     "exists" on purpose: across three constructed variants a coincidence is
     impossible unless the figure IS the budget.
  D. The unit: the old probe reported C on a control level (calls until
     GAME_OVER, the C-th charged action kills), so the reworked figure must
     too — the old figure "stays recorded beside the new one ... for
     comparability", which presupposes one unit. An off-by-one is red.
  E. "Clearly labeled" (N4): the old burn figure must sit in the SAME output
     as the new figure, at a different path, and that path (or a string
     value of a sibling field) must carry one of OLD_PROBE_LABELS. The old D7
     centering must be a named object holding 2.00, 1.54 and 2.96 together
     whose name carries one of OLD_CENTERING_LABELS. A bare `caps.values`
     keeping the old figure while the new one is labeled is read as NOT
     clearly labeled.
  F. N1's "unconfigured" covers TWO configs: no I-1 knob at all (the code
     default), AND the HEAD-era knobs a live template already arms (cap_fit
     record + caps.basis official-band) — an existing batch resumed after
     I-1 must not move either. The CONTROL case adds the hard-mode fit +
     metadata writer path. Byte identity is over every file the stage writes
     (actions/, s4-report.json, metadata.json), normalized ONLY for the tmp
     root and the two runtime version strings. Floats are frozen on this
     machine's libm (the suite's own home).
  G. If the template re-centers g.median, a CLI-materialized batch moves;
     the house rule speaks of the code default, so that is NOT pinned red
     here — channel B simply counts it as a re-centering.

SEAMS (where a lead retargets a false red): `_discover_reads`,
`_knob_configs`, `_function_surfaces`, `_recentering_hits`,
`_named_d7_alternatives`, `_labeled_old_figure`.

Hermetic: every run drives a generated worker under tmp_path; nothing under
out/ or games/ is read or written; effort.csv and config/template.yaml are
read-only; no drivers, no network, no spend.
"""

from __future__ import annotations

import copy
import csv
import dataclasses
import hashlib
import importlib
import inspect
import json
import math
import re
import statistics
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

import pytest
import yaml
from arcengine import ActionInput, GameAction, GameState

import gen.s4_baselines as s4
from gen.config import REPO_ROOT
from gen.frames import TERMINAL_STATES, _fresh_game, _perform, _reset
from gen.s3_static import load_worker_classes

# --------------------------------------------------------------------------- #
# the contract's own words — every red quotes the clause it holds
# --------------------------------------------------------------------------- #

CLAUSE_HOUSE_RULE = (
    "HOUSE RULE: defaults = today's bytes — both reworks ship behind the existing knob "
    "surfaces or as recorded alternatives; an unconfigured batch's S4 numbers must stay "
    "byte-identical, pinned."
)
CLAUSE_N1 = (
    "N1 unconfigured S4 output byte-identical to today on a fixture slot (the HOUSE RULE's "
    "teeth — drive the assigner twice, pre/post shapes equal)."
)
CLAUSE_N2 = (
    "N2 the re-centered g statistic derives from the instrument the implementer's memo "
    "names (probe defensively; red must quote this clause, naming what was promised)."
)
PROMISE_N2 = (
    "PROMISED (Work item 1): 'g.median is centered on one officials instrument (D7) while "
    "effort.csv is a DIFFERENT officials instrument ... re-center on the adjudicated "
    "instrument ... with the old centering preserved as a named alternative'. The audit "
    "record (b003-freeze addendum 16) names the move: 're-centering g.median 2.00 -> 1.267'."
)
CLAUSE_N3 = (
    "N3 the reworked probe's output is a function of budget.cap's own bounded quantity on "
    "a constructed fixture where the two phenomena (repetition-death vs cap) DIVERGE."
)
PROMISE_N3 = (
    "PROMISED (Work item 2): the probe 'measures death-by-repetition, not budget.cap ... "
    "Rework it to measure what `budget.cap` actually bounds'."
)
CLAUSE_N4 = (
    "N4 both old figures remain present-and-labeled where the contract says they stay."
)
PROMISE_N4_CENTER = "PROMISED: 'the old centering preserved as a named alternative'."
PROMISE_N4_PROBE = (
    "PROMISED: 'The old probe's figure stays recorded beside the new one for one release "
    "(comparability), clearly labeled.'"
)

# --------------------------------------------------------------------------- #
# frozen pre-state (HEAD 23e7392, measured on a `git archive HEAD gen` export)
# --------------------------------------------------------------------------- #

HEAD_S4_NAMES = frozenset(
    {
        "ACTIONS_DIRNAME", "ActionInput", "BAND_TOLERANCE", "BATTERY_MARGIN", "BURN_BOUND",
        "BURN_BOUNDED", "BURN_GAME_OVER", "BURN_TRANSITION", "BURN_WIN", "CAPS_BASES",
        "CAPS_BASIS_KEY", "CAPS_BASIS_LEGACY", "CAPS_BASIS_OFFICIAL_BAND", "CAPS_BLOCK_KEY",
        "CAPS_MEASURED", "CAPS_PREMISE_NOT_MET", "CAPS_UNMEASURED", "CAP_FIT_HARD",
        "CAP_FIT_KEY", "CAP_FIT_MODES", "CAP_FIT_RECORD", "CAP_FIT_REJECT", "CENTRE_CLICK",
        "DEFAULT_CONFIG", "DEFAULT_S4_TIMEOUT_S", "FLAT_LOG_EPS", "G_CLIP", "GameAction",
        "GameState", "LineCapture", "METADATA_NAME", "Mapping", "OFFICIAL_G_BOX",
        "OFFICIAL_RATIO_BAND", "OFFICIAL_RATIO_MEDIAN", "OUT_SUFFIX", "PHI_INV_075", "Path",
        "REPORT_NAME", "REPO_ROOT", "S4ProcessError", "SCHEMA_VERSION", "Sequence",
        "TERMINAL_STATES", "VERDICT_FIT", "VERDICT_REJECT", "_GParams", "_action_from_record",
        "_action_record", "_as_float", "_burn", "_burn_action", "_cap_fit_mode", "_caps_basis",
        "_check_clip", "_check_solver", "_check_vector", "_clip_to_box", "_fmt", "_fresh_game",
        "_g_box", "_g_params", "_has_lose_call", "_invariants", "_level_cap", "_load_cfg_json",
        "_log_trend", "_measure_caps_detail", "_perform", "_playable_action_ids",
        "_replay_prefix", "_reset", "_stderr_tail", "_versions", "_write_json", "annotations",
        "argparse", "ast", "batch_band", "break_monotonic", "cap_fit_block", "caps_band_block",
        "click_cells", "dataclass", "derive_seed", "describe_action", "draw_baselines",
        "fit_g", "floor_bump", "game_source_path", "has_strict_descent", "hashlib",
        "importlib", "itertools", "json", "load_config", "load_worker_classes", "main", "math",
        "measure_caps", "mouse", "np", "official_band_caps", "platform", "random", "run_s4",
        "run_s4_isolated", "solver_lines", "span_rescale", "subprocess", "sys", "tempfile",
        "trend_nudge", "write_actions",
    }
)
# The two knob enums HEAD ships; a NEW member is a candidate knob value.
HEAD_ENUMS = {
    "CAPS_BASES": ("legacy", "official-band"),
    "CAP_FIT_MODES": ("hard", "record", "reject"),
}
# (block, key) pairs HEAD's run_s4 reads from its config ("" = top level).
HEAD_READ_KEYS = frozenset(
    {
        ("", "batch"), ("", "caps"), ("", "g"), ("batch", "seed"), ("caps", "basis"),
        ("g", "cap_fit"), ("g", "floor"), ("g", "iqr"), ("g", "median"), ("g", "redraw_cap"),
        ("g", "span_target"), ("g", "trend"),
    }
)
# Keyword parameters HEAD's probe-adjacent callables take (a NEW one is a surface).
HEAD_PARAMS = {
    "measure_caps": ("worker_dir", "lines"),
    "_measure_caps_detail": ("worker_dir", "lines"),
    "run_s4": ("worker_dir", "cfg", "seed", "out_dir"),
}
HEAD_GEN_MODULES = frozenset(
    {
        "__init__", "__main__", "backends", "canon_docs", "cli", "config", "frames",
        "officials", "orchestrator", "s0_ideas", "s1_spec", "s2_implement", "s3_gate",
        "s3_static", "s3_verify", "s3_visual", "s4_baselines", "s5_battery", "s6_package",
        "smoke", "tiers", "visual_canon", "worker",
    }
)

# N1 — sha256 of every file the stage writes, normalized (`_normalize`), per case.
_ACTIONS_SHA = {
    "actions/level-1.json": "a07163962f094b06d784b5cd529d7bcea05a0048d233c83d6f75cdf7cf0ede98",
    "actions/level-2.json": "44d6d90b9a494ac37753711857b15c6912a8d2ab1a95d9ee8c90b63825dd1809",
    "actions/level-3.json": "9e1d745bf6d63c98c8ce30b5bafc24cb867773c412f7c0350ea78b2af6a476c1",
}
N1_FROZEN = {
    "legacy-hard/base": {
        "files": {
            **_ACTIONS_SHA,
            "s4-report.json": "a6b8b71c3096b9b8d1fea265ed1f1fa3327d83a37914111fab36c5836d9d5cfb",
        },
        "verdict": "cap-fit-reject",
        "caps": [3, 53, 5],
        "baselines": None,
        "attempts": [[6, 18, 12], [6, 6, 6], [6, 18, 10], [7, 6, 10]],
        "rng_seed": 2196337548,
    },
    "head-knobs/base": {
        "files": {
            **_ACTIONS_SHA,
            "metadata.json": "5e502b11731f1c7ccbd6971912ef11a7f51882a424887cd9d6ac5ed0bbd47c02",
            "s4-report.json": "42c9a29c340d707ff2e34b168f7ba16f7b1b55f90b71a95855232ebdd7594cd3",
        },
        "verdict": "fit",
        "caps": [3, 53, 5],
        "baselines": [6, 6, 6],
        "attempts": [[6, 7, 6], [6, 6, 6], [6, 7, 6], [6, 6, 6]],
        "rng_seed": 2196337548,
    },
    "legacy-hard/control": {
        "files": {
            **_ACTIONS_SHA,
            "metadata.json": "9969af819a65c6c17c51169f66ee34681375c8de83fb0a3a2598978d14e14b86",
            "s4-report.json": "172f24f1f0463dfeb4dd36145cfec016c1008c47f749ecbbe4cf50640c0d2e59",
        },
        "verdict": "fit",
        "caps": [131, 157, 173],
        "baselines": [6, 18, 12],
        "attempts": [[6, 18, 12]],
        "rng_seed": 2196337548,
    },
}

# --------------------------------------------------------------------------- #
# the instruments' checked-in data
# --------------------------------------------------------------------------- #

EFFORT_CSV = REPO_ROOT / "audit" / "comparative" / "data" / "effort.csv"
TEMPLATE = REPO_ROOT / "config" / "template.yaml"
D7_MEDIAN, D7_IQR = 2.00, (1.54, 2.96)  # canon/spec-v0.3.md §8; decisions.md D7
AUDIT_RECENTER_TARGET = 1.267  # b003-freeze addendum 16: "2.00 -> 1.267"
RECENTER_TOL = 0.005  # D7's own quoted precision is 2 dp (reading A)
N_OFFICIAL_LEVELS = 183

OLD_PROBE_LABELS = ("burn", "legacy", "old", "repetition", "previous", "prior", "b8", "before")
# A sibling STRING can label too, minus the words HEAD's own reports already
# carry as unrelated values ("legacy" is a caps.basis value, "b8" the schema).
OLD_PROBE_SIBLING_LABELS = ("burn", "old", "repetition", "previous", "prior", "before")
OLD_CENTERING_LABELS = (
    "d7", "replay", "legacy", "old", "historic", "prior", "previous", "canon", "b8",
)
RECENTER_HINTS = (
    "median", "center", "centre", "recenter", "recentre", "effort", "human", "ruler",
    "instrument",
)

_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,39}$")
CANDIDATE_CAP = 160  # bound on knob configurations tried (reported if hit)

# --------------------------------------------------------------------------- #
# the fixture (see the module docstring's divergence table)
# --------------------------------------------------------------------------- #

GAME_SOURCE = '''\
"""I-1 BLIND FIXTURE — written into tmp_path by gen/tests/test_v2_instruments.py.

The budget triple (spec §2 row 3): a per-level counter charged on EVERY
action including blocked moves, a row-0 meter, exhaustion -> lose() with the
win check FIRST. A divergent level adds a pit `k` cells above the start whose
lose() fires with the budget NOT exhausted (death by repetition of ACTION1).
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL, METER, PIT = 4, 9, 12, 7, 8
BOARD = 16
START = (1, 12)
# level index -> (goal dx, budget.cap, pit distance above the start or 0)
LEVEL_PLAN = __PLAN__

DIRS = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}


def _level(goal_dx, cap, pit_k):
    sprites = [
        Sprite([[METER]], name=f"meter_{k}", x=k, y=0, layer=1, collidable=False)
        for k in range(BOARD)
    ]
    sprites += [
        Sprite([[WALL] * BOARD], name="wall_top", x=0, y=1),
        Sprite([[WALL] * BOARD], name="wall_bottom", x=0, y=13),
        Sprite([[WALL]] * 11, name="wall_left", x=0, y=2),
        Sprite([[WALL]] * 11, name="wall_right", x=BOARD - 1, y=2),
        Sprite(
            [[GOAL]], name="goal", x=START[0] + goal_dx, y=START[1], layer=1, collidable=False
        ),
        Sprite([[PLAYER]], name="player", x=START[0], y=START[1], layer=2),
    ]
    if pit_k:
        sprites.append(
            Sprite([[PIT]], name="pit", x=START[0], y=START[1] - pit_k, layer=1, collidable=False)
        )
    else:
        sprites.append(Sprite([[WALL]], name="wall_cap", x=START[0], y=START[1] - 1))
    return Level(sprites=sprites)


class I1InstrumentBoard(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="i1-blind-instruments",
            levels=[_level(*row) for row in LEVEL_PLAN],
            camera=Camera(width=BOARD, height=BOARD),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
        self._budget_used = 0

    @property
    def _cap(self) -> int:
        return LEVEL_PLAN[self.level_index][1]

    def _paint_meter(self) -> None:
        cap = self._cap
        remaining = max(0, cap - self._budget_used)
        lit = -(-remaining * BOARD // cap)
        for k in range(BOARD):
            for sprite in self.current_level.get_sprites_by_name(f"meter_{k}"):
                sprite.set_visible(k < lit)

    def step(self) -> None:
        if self.action.id == GameAction.RESET:
            self.complete_action()
            self._paint_meter()
            return
        delta = DIRS.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)  # a blocked move is still CHARGED
        self._budget_used += 1
        self.complete_action()
        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        pits = self.current_level.get_sprites_by_name("pit")
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()  # WIN CHECK FIRST
        elif pits and (player.x, player.y) == (pits[0].x, pits[0].y):
            self.lose()  # the hazard: death by repetition, budget NOT exhausted
        elif self._budget_used >= self._cap:
            self.lose()  # budget.cap exhaustion
        self._paint_meter()
'''

SOLVER_SOURCE = '''\
"""I-1 BLIND FIXTURE solver: each level is GOAL_DX[i] presses of ACTION4."""

from arcengine import ActionInput, GameAction

GOAL_DX = __DXS__


class Solver:
    def reset(self) -> None:
        self._used = {}

    def next_action(self, frame):
        level = int(frame.levels_completed)
        if level >= len(GOAL_DX):
            return None
        used = self._used.get(level, 0)
        if used >= GOAL_DX[level]:
            return None
        self._used[level] = used + 1
        return ActionInput(id=GameAction.ACTION4)
'''

# (goal dx, budget.cap C, pit distance k or 0) per level.
PLANS = {
    "base": ((2, 41, 3), (3, 53, 0), (4, 67, 5)),
    "cap": ((2, 47, 3), (3, 59, 0), (4, 73, 5)),
    "pit": ((2, 41, 6), (3, 53, 0), (4, 67, 2)),
    "control": ((2, 131, 0), (3, 157, 0), (4, 173, 0)),
}
LEVELS = 3
SOLVER_LINE = (2, 3, 4)


def _budget(variant: str) -> tuple[int, ...]:
    """budget.cap's bounded quantity: the charged-action count that kills."""
    return tuple(cap for _dx, cap, _k in PLANS[variant])


def _old_figure(variant: str) -> tuple[int, ...]:
    """What a first-qualifying-action burn reads: the pit when there is one."""
    return tuple(k if k else cap for _dx, cap, k in PLANS[variant])


BATCH_SEED = 11


def _d7_g(**extra) -> dict:
    g = {
        "median": D7_MEDIAN,
        "iqr": list(D7_IQR),
        "floor": 6,
        "span_target": 9,
        "trend": 0.65,
        "redraw_cap": 3,
    }
    g.update(extra)
    return g


def _cfg_unconfigured() -> dict:
    return {"g": _d7_g(), "batch": {"seed": BATCH_SEED}}


def _cfg_head_knobs() -> dict:
    return {
        "g": _d7_g(cap_fit="record"),
        "caps": {"basis": "official-band"},
        "batch": {"seed": BATCH_SEED},
    }


def _cfg_probe_base() -> dict:
    """N3's base: record mode so every attempt ships metadata (more surfaces)."""
    return {"g": _d7_g(cap_fit="record"), "batch": {"seed": BATCH_SEED}}


N1_CASES = {
    "legacy-hard/base": ("base", _cfg_unconfigured),
    "head-knobs/base": ("base", _cfg_head_knobs),
    "legacy-hard/control": ("control", _cfg_unconfigured),
}

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _write_worker(root: Path, variant: str) -> Path:
    """A fixture SLOT: `<root>/workers/w001` (S4 writes the sibling `w001.s4`)."""
    plan = PLANS[variant]
    worker = root / "workers" / "w001"
    worker.mkdir(parents=True)
    (worker / "game.py").write_text(
        GAME_SOURCE.replace("__PLAN__", repr(tuple(plan))), encoding="utf-8"
    )
    (worker / "solver.py").write_text(
        SOLVER_SOURCE.replace("__DXS__", repr(tuple(row[0] for row in plan))), encoding="utf-8"
    )
    return worker


def _normalize(text: str, root: Path) -> str:
    """Only the tmp root and the two runtime version strings are normalized."""
    for prefix in sorted({str(root), str(root.resolve())}, key=len, reverse=True):
        text = text.replace(prefix, "<ROOT>")
    text = re.sub(r'"arcengine": "[^"]*"', '"arcengine": "<ARCENGINE>"', text)
    return re.sub(r'"python": "[^"]*"', '"python": "<PYTHON>"', text)


def _out_files(out_dir: Path, root: Path) -> dict[str, str]:
    return {
        path.relative_to(out_dir).as_posix(): _normalize(path.read_text(encoding="utf-8"), root)
        for path in sorted(out_dir.rglob("*"))
        if path.is_file()
    }


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_outputs(out_dir: Path) -> dict:
    """Every JSON the stage wrote except the action facts, keyed by relative path."""
    found: dict = {}
    for path in sorted(out_dir.rglob("*.json")):
        rel = path.relative_to(out_dir).as_posix()
        if rel.startswith(s4.ACTIONS_DIRNAME + "/"):
            continue
        try:
            found[rel] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return found


def _tokens(text: str) -> list[str]:
    return [tok for tok in re.split(r"[^a-z0-9]+", str(text).lower()) if tok]


def _labeled(text: str, labels: tuple[str, ...]) -> bool:
    return any(tok.startswith(label) for tok in _tokens(text) for label in labels)


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _children(node) -> Iterator[tuple[str, object]]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            yield f".{key}", value
    elif dataclasses.is_dataclass(node) and not isinstance(node, type):
        for field in dataclasses.fields(node):
            yield f".{field.name}", getattr(node, field.name)
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield f"[{index}]", value
    elif isinstance(node, (set, frozenset)):
        for index, value in enumerate(sorted(node, key=repr)):
            yield f"{{{index}}}", value


def _walk(node, path: str, depth: int = 0) -> Iterator[tuple[str, object]]:
    yield path, node
    if depth >= 8:
        return
    for suffix, child in _children(node):
        yield from _walk(child, path + suffix, depth + 1)


def _leaves(node) -> list[float]:
    return [num for _p, value in _walk(node, "") if (num := _number(value)) is not None]


def _as_vector(value) -> tuple | None:
    """A per-level vector: LEVELS entries, each an integral number or None."""
    if not isinstance(value, (list, tuple)) or len(value) != LEVELS:
        return None
    out: list = []
    for entry in value:
        if entry is None:
            out.append(None)
            continue
        num = _number(entry)
        if num is None or not math.isfinite(num) or num != int(num):
            return None
        out.append(int(num))
    return tuple(out) if any(entry is not None for entry in out) else None


def _vectors(obj, root: str = "") -> list[tuple[str, tuple, object]]:
    """(path, vector, parent) for every per-level vector, incl. per-level-row COLUMNS."""
    found: list[tuple[str, tuple, object]] = []
    for path, node in _walk(obj, root):
        vector = _as_vector(node)
        if vector is not None:
            found.append((path, vector, None))
        if (
            isinstance(node, (list, tuple))
            and len(node) == LEVELS
            and all(isinstance(row, Mapping) for row in node)
        ):
            for key in node[0]:
                column = _as_vector([row.get(key) for row in node])
                if column is not None and all(key in row for row in node):
                    found.append((f"{path}[*].{key}", column, node[0]))
    return found


def _parent_of(obj, path: str):
    """The mapping holding `path`'s last key (for sibling labels), or None."""
    head, sep, _last = path.rpartition(".")
    if not sep:
        return None
    for candidate, node in _walk(obj, ""):
        if candidate == head and isinstance(node, Mapping):
            return node
    return None


def _effort_officials() -> list[dict]:
    with EFFORT_CSV.open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row["corpus"] == "official"]


def _effort_g_center() -> float:
    """effort.csv's officials, read as a g: `1 / median(actions / baseline)`."""
    rows = _effort_officials()
    ratios = [float(row["actions"]) / float(row["baseline"]) for row in rows]
    return 1.0 / statistics.median(ratios)


# --- read-logging config (which knobs does the assigner actually read?) -------


class _ReadLog(dict):
    """A config mapping that logs every key the stage READS (incl. absent ones)."""

    def __init__(self, data=(), log: set | None = None, where: str = "") -> None:
        super().__init__(data)
        self._log = log if log is not None else set()
        self._where = where

    def __getitem__(self, key):
        self._log.add((self._where, key))
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._log.add((self._where, key))
        return super().get(key, default)

    def __contains__(self, key) -> bool:
        self._log.add((self._where, key))
        return super().__contains__(key)


def _logged_cfg(base: Mapping, log: set, extra_blocks: tuple[str, ...] = ()) -> _ReadLog:
    top = _ReadLog({}, log, "")
    for key, value in base.items():
        dict.__setitem__(
            top, key, _ReadLog(value, log, key) if isinstance(value, Mapping) else value
        )
    if "caps" not in base:
        # explicit `basis: legacy` IS the absent block at HEAD (test_w3_caps g2) and,
        # unlike `{}`, survives a `cfg.get("caps") or {}` read idiom
        dict.__setitem__(top, "caps", _ReadLog({"basis": "legacy"}, log, "caps"))
    for block in extra_blocks:
        dict.__setitem__(top, block, _ReadLog({}, log, block))
    return top


def _discover_reads(tmp: Path) -> tuple[set[tuple[str, str]], list[str]]:
    """NEW (block, key) reads of the assigner, beyond HEAD_READ_KEYS. Two rounds:
    the second hands every newly read top-level key an empty logged block."""
    notes: list[str] = []
    found: set[tuple[str, str]] = set()
    extra: tuple[str, ...] = ()
    for round_index in range(2):
        log: set = set()
        cfg = _logged_cfg(_cfg_probe_base(), log, extra)
        root = tmp / f"reads-{round_index}"
        worker = _write_worker(root, "base")
        try:
            s4.run_s4(worker, cfg, out_dir=root / "out")
        except Exception as exc:  # noqa: BLE001 — a probe: reported, never swallowed
            notes.append(f"read-log round {round_index}: run_s4 raised {exc!r}")
            if round_index:
                break
        new = {(where, key) for where, key in log if isinstance(key, str)} - HEAD_READ_KEYS
        found |= new
        top = tuple(sorted(key for where, key in new if where == "" and key not in extra))
        if not top:
            break
        extra = extra + top
    return found, notes


def _new_constants() -> dict[str, object]:
    return {
        name: value
        for name, value in vars(s4).items()
        if not name.startswith("__") and name not in HEAD_S4_NAMES
    }


def _candidate_values() -> list:
    values: set[str] = set()
    for name, value in _new_constants().items():
        if inspect.isroutine(value) or inspect.isclass(value) or inspect.ismodule(value):
            continue
        if isinstance(value, str):
            if not name.endswith("_KEY") and _IDENT.match(value):
                values.add(value)
        elif isinstance(value, (tuple, list, set, frozenset, Mapping)):
            # enum members, or the NAMES of a named-alternatives mapping
            values |= {x for x in value if isinstance(x, str) and _IDENT.match(x)}
    for name, head in HEAD_ENUMS.items():
        current = getattr(s4, name, ())
        if isinstance(current, (tuple, list, set, frozenset)):
            values |= {x for x in current if isinstance(x, str) and x not in head}
    return sorted(values) + [True]


def _place(base: Mapping, where: str, key: str, value) -> dict | None:
    cfg = copy.deepcopy(dict(base))
    if not where:
        cfg[key] = value
        return cfg
    block = cfg.get(where, {})
    if not isinstance(block, Mapping):
        return None
    block = dict(block)
    block[key] = value
    cfg[where] = block
    return cfg


def _knob_configs(base: Mapping, tmp: Path) -> tuple[list[tuple[str, dict]], list[str]]:
    """Every candidate I-1 knob setting the module itself makes discoverable."""
    reads, notes = _discover_reads(tmp)
    keys = {
        value
        for name, value in _new_constants().items()
        if isinstance(value, str) and name.endswith("_KEY") and _IDENT.match(value)
    }
    # reads UNION the module's own *_KEY idiom: a read hidden behind `x or {}` or a
    # copied block is invisible to the log, a declared key constant is not
    placements = set(reads) | {(where, key) for key in keys for where in ("caps", "g", "")}
    values = _candidate_values()
    combos: list[tuple[str, str, object]] = [
        (where, key, value) for where, key in sorted(placements) for value in values
    ]
    for value in values:
        if value in getattr(s4, "CAPS_BASES", ()) and value not in HEAD_ENUMS["CAPS_BASES"]:
            combos.append(("caps", "basis", value))
        if value in getattr(s4, "CAP_FIT_MODES", ()) and value not in HEAD_ENUMS["CAP_FIT_MODES"]:
            combos.append(("g", "cap_fit", value))
    notes.append(
        f"reads beyond HEAD: {sorted(reads)}; new *_KEY values: {sorted(keys)}; "
        f"candidate values: {values}"
    )
    configs: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for where, key, value in combos:
        cfg = _place(base, where, key, value)
        if cfg is None:
            continue
        fingerprint = json.dumps(cfg, sort_keys=True, default=str)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        try:  # cheap validation: the draw + the g fit read every validated knob
            s4.fit_g(cfg)
            s4.draw_baselines(list(SOLVER_LINE), [None] * LEVELS, cfg, 0)
        except (ValueError, TypeError, KeyError) as exc:
            notes.append(f"refused {where or '<top>'}.{key}={value!r}: {exc}")
            continue
        configs.append((f"{where or '<top>'}.{key}={value!r}", cfg))
    if len(configs) > CANDIDATE_CAP:
        notes.append(f"candidate configs truncated {len(configs)} -> {CANDIDATE_CAP}")
        configs = configs[:CANDIDATE_CAP]
    return configs, notes


# --- N3 surfaces ----------------------------------------------------------------


@dataclasses.dataclass
class _Surface:
    label: str
    produce: Callable[[Path, str], object]  # (fresh tmp root, variant) -> harvestable


def _report_surface(label: str, cfg: Mapping, **kwargs) -> _Surface:
    def produce(root: Path, variant: str):
        worker = _write_worker(root, variant)
        out = root / "out"
        s4.run_s4(worker, cfg, out_dir=out, **kwargs)
        return _json_outputs(out)

    return _Surface(label, produce)


def _call_surface(label: str, fn: Callable, **kwargs) -> _Surface:
    def produce(root: Path, variant: str):
        worker = _write_worker(root, variant)
        return fn(worker, s4.solver_lines(worker), **kwargs)

    return _Surface(label, produce)


def _function_surfaces(values: list) -> list[_Surface]:
    """New `(worker_dir, lines, ...)` callables, and new keywords on HEAD's ones."""
    surfaces: list[_Surface] = []
    for name, fn in sorted(vars(s4).items()):
        if not inspect.isfunction(fn) or getattr(fn, "__module__", "") != s4.__name__:
            continue
        params = list(inspect.signature(fn).parameters.values())
        required = [
            p
            for p in params
            if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        names = [p.name.lower() for p in required]
        shaped = len(names) == 2 and "worker" in names[0] and "line" in names[1]
        if name not in HEAD_S4_NAMES and shaped:
            surfaces.append(_call_surface(f"{name}(worker, lines)", fn))
        if name in HEAD_PARAMS:
            extra = [p.name for p in params if p.name not in HEAD_PARAMS[name]]
            for keyword in extra:
                for value in values:
                    if name == "run_s4":
                        surfaces.append(
                            _report_surface(
                                f"run_s4(..., {keyword}={value!r})",
                                _cfg_probe_base(),
                                **{keyword: value},
                            )
                        )
                    else:
                        surfaces.append(
                            _call_surface(f"{name}(..., {keyword}={value!r})", fn, **{keyword: value})
                        )
    return surfaces


@pytest.fixture(scope="module")
def probe_discovery(tmp_path_factory) -> dict:
    """Discover every candidate reworked-probe surface ONCE; evaluate N3 on it."""
    tmp = tmp_path_factory.mktemp("i1-probe")
    configs, notes = _knob_configs(_cfg_probe_base(), tmp)
    surfaces = [_report_surface("unconfigured (code default)", _cfg_probe_base())]
    surfaces += [_report_surface(f"run_s4 with {label}", cfg) for label, cfg in configs]
    surfaces += _function_surfaces(_candidate_values())

    counter = iter(range(10**6))
    produced: dict[tuple[str, str], object] = {}

    def produce(surface: _Surface, variant: str):
        key = (surface.label, variant)
        if key not in produced:
            root = tmp / f"s{next(counter)}"
            try:
                produced[key] = surface.produce(root, variant)
            except Exception as exc:  # noqa: BLE001 — every failure lands in diagnostics
                produced[key] = exc
        return produced[key]

    passing: list[tuple[str, str]] = []
    diagnostics: list[str] = []
    for surface in surfaces:
        obj = produce(surface, "base")
        if isinstance(obj, Exception):
            diagnostics.append(f"{surface.label}: raised {obj!r}")
            continue
        vectors = _vectors(obj)
        diagnostics.append(
            f"{surface.label}: per-level vectors on BASE = "
            + "; ".join(f"{path}={list(vec)}" for path, vec, _p in vectors[:12])
        )
        for path, vector, _parent in vectors:
            if vector != _budget("base"):
                continue
            ok = True
            for variant in ("cap", "pit"):
                other = produce(surface, variant)
                got = (
                    None
                    if isinstance(other, Exception)
                    else {p: v for p, v, _q in _vectors(other)}.get(path)
                )
                if got != _budget(variant):
                    diagnostics.append(
                        f"  {surface.label} @ {path}: BASE matched budget.cap but {variant.upper()} "
                        f"read {got} vs budget.cap {list(_budget(variant))}"
                    )
                    ok = False
            if ok:
                passing.append((surface.label, path))
    return {
        "surfaces": surfaces,
        "passing": passing,
        "diagnostics": diagnostics,
        "notes": notes,
        "base_objects": {s.label: produced.get((s.label, "base")) for s in surfaces},
    }


# --- N2 / N4 static harvest -------------------------------------------------------


def _harvest_modules() -> tuple[list[tuple[str, object]], list[str]]:
    """gen.s4_baselines plus every NEW gen module ('any sibling the instruments live in')."""
    modules: list[tuple[str, object]] = [("gen.s4_baselines", s4)]
    notes: list[str] = []
    for path in sorted((REPO_ROOT / "gen").glob("*.py")):
        if path.stem in HEAD_GEN_MODULES:
            continue
        name = f"gen.{path.stem}"
        try:
            modules.append((name, importlib.import_module(name)))
        except Exception as exc:  # noqa: BLE001 — an unimportable sibling is a note
            notes.append(f"{name}: import raised {exc!r}")
    return modules, notes


def _module_data(module) -> Iterator[tuple[str, object]]:
    for name, value in vars(module).items():
        if name.startswith("__"):
            continue
        if inspect.ismodule(value) or inspect.isclass(value) or inspect.isroutine(value):
            continue
        if callable(value):
            continue
        yield name, value


def _named_objects() -> tuple[list[tuple[str, object]], list[str]]:
    """(dotted path, object) for every module-level datum, new zero-arg hinted
    helper result, and the template's YAML tree."""
    modules, notes = _harvest_modules()
    objects: list[tuple[str, object]] = []
    for module_name, module in modules:
        for name, value in _module_data(module):
            objects.append((f"{module_name}.{name}", value))
        for name, fn in vars(module).items():
            if (
                not inspect.isfunction(fn)
                or getattr(fn, "__module__", "") != module.__name__
                or (module is s4 and name in HEAD_S4_NAMES)
                or not any(_labeled(name, (hint,)) for hint in RECENTER_HINTS + ("centering",))
            ):
                continue
            required = [
                p
                for p in inspect.signature(fn).parameters.values()
                if p.default is p.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
            ]
            if required:
                continue
            try:
                objects.append((f"{module_name}.{name}()", fn()))
            except Exception as exc:  # noqa: BLE001 — a probe: reported, never swallowed
                notes.append(f"{module_name}.{name}(): raised {exc!r}")
    try:
        objects.append(("config/template.yaml", yaml.safe_load(TEMPLATE.read_text("utf-8"))))
    except (OSError, yaml.YAMLError) as exc:
        notes.append(f"template.yaml unreadable: {exc!r}")
    return objects, notes


def _recentering_hits(target: float, tmp: Path) -> tuple[list[str], list[str], list[str]]:
    """Where the re-centered g center shows up (reading B).

    Returns (knob_centers, static_hits, seen). `knob_centers` lists every knob
    setting that MOVES fit_g's center off D7's 2.00 — when any exists, THAT is
    the re-centered statistic the sampler runs on, and it decides N2 on its own
    (a matching constant the sampler never reads cannot buy the pin). Only when
    no knob moves the center do the static channels (named constant, hinted
    zero-arg helper, template g.median) decide.
    """
    static_hits: list[str] = []
    knob_centers: list[str] = []
    seen: list[str] = []
    objects, notes = _named_objects()
    for root, obj in objects:
        for path, node in _walk(obj, root):
            num = _number(node)
            if num is None or not 0.5 < num < 3.5:
                continue
            tail = path.split("config/template.yaml", 1)[-1]
            hinted = any(
                tok.startswith(hint) for tok in _tokens(tail) for hint in RECENTER_HINTS
            ) or "g" in _tokens(tail)
            if not hinted:
                continue
            seen.append(f"{path}={num!r}")
            if abs(num - target) <= RECENTER_TOL:
                static_hits.append(f"static {path} = {num!r}")
    configs, knob_notes = _knob_configs({"g": _d7_g(), "batch": {"seed": BATCH_SEED}}, tmp)
    notes += knob_notes
    for label, cfg in configs:
        try:
            center = math.exp(s4.fit_g(cfg)[0])
        except Exception as exc:  # noqa: BLE001 — a probe: reported, never swallowed
            notes.append(f"fit_g under {label} raised {exc!r}")
            continue
        seen.append(f"knob {label} -> fit_g center {center!r}")
        if abs(center - D7_MEDIAN) > 1e-9:
            knob_centers.append(f"knob {label}: fit_g centers g at {center!r}")
    return knob_centers, static_hits, seen + notes


def _named_d7_alternatives() -> tuple[list[str], list[str]]:
    """Named objects holding D7's 2.00 / 1.54 / 2.96 together (reading E)."""
    labeled: list[str] = []
    unlabeled: list[str] = []
    objects, notes = _named_objects()
    want = (D7_MEDIAN, *D7_IQR)
    for root, obj in objects:
        for path, node in _walk(obj, root):
            if not (
                isinstance(node, (Mapping, list, tuple))
                or (dataclasses.is_dataclass(node) and not isinstance(node, type))
            ):
                continue
            leaves = _leaves(node)
            if not leaves or len(leaves) > 12:
                continue
            if not all(any(abs(leaf - w) <= 1e-9 for leaf in leaves) for w in want):
                continue
            if path == "config/template.yaml.g":
                continue  # the live g: line is not an alternative, it is the setting
            name = path.split("config/template.yaml", 1)[-1]
            (labeled if _labeled(name, OLD_CENTERING_LABELS) else unlabeled).append(path)
    return labeled, unlabeled + notes


def _labeled_old_figure(obj, new_path: str) -> tuple[list[str], list[str]]:
    """Paths (!= new_path) in `obj` holding the OLD probe figure, labeled or not."""
    labeled: list[str] = []
    unlabeled: list[str] = []
    old = _old_figure("base")
    for path, vector, row in _vectors(obj):
        if vector != old or path == new_path:
            continue
        parent = row if row is not None else _parent_of(obj, path)
        sibling_text = " ".join(
            value
            for value in (parent.values() if isinstance(parent, Mapping) else ())
            if isinstance(value, str) and not value.startswith("/")
        )
        if _labeled(path, OLD_PROBE_LABELS) or _labeled(sibling_text, OLD_PROBE_SIBLING_LABELS):
            labeled.append(path)
        else:
            unlabeled.append(path)
    return labeled, unlabeled


# --------------------------------------------------------------------------- #
# N0 — the fixture's divergence, proven at the engine (green both sides)
# --------------------------------------------------------------------------- #


def _engine_burn(worker: Path, variant: str, level: int, action: GameAction) -> tuple[int, str]:
    game_cls, _solver = load_worker_classes(worker)
    game = _fresh_game(game_cls)
    fd = _reset(game)
    for done in range(level):
        for _ in range(PLANS[variant][done][0]):
            fd = _perform(game, ActionInput(id=GameAction.ACTION4))
    assert int(fd.levels_completed) == level and fd.state not in TERMINAL_STATES
    for calls in range(1, 1000):
        fd = _perform(game, ActionInput(id=action))
        if fd.state is GameState.GAME_OVER:
            return calls, "game-over"
        if fd.state is GameState.WIN or int(fd.levels_completed) != level:
            return calls, "left-level"
    return 1000, "alive"


@pytest.mark.parametrize("variant", sorted(PLANS))
def test_n0_fixture_diverges_at_the_engine(tmp_path: Path, variant: str) -> None:
    """N3's premise, at the ENGINE: on every level a charged refusal (ACTION2,
    ACTION3) dies at exactly budget.cap, while ACTION1 dies at the pit (`k`) on a
    divergent level and at budget.cap on a control level. The two phenomena are
    measurably different on BASE/CAP/PIT levels 1 and 3, equal on level 2 and on
    every CONTROL level. Independent of gen.s4_baselines (green both sides)."""
    worker = _write_worker(tmp_path, variant)
    for level, (_dx, cap, pit) in enumerate(PLANS[variant]):
        assert _engine_burn(worker, variant, level, GameAction.ACTION2) == (cap, "game-over")
        assert _engine_burn(worker, variant, level, GameAction.ACTION3) == (cap, "game-over")
        expected = pit if pit else cap
        assert _engine_burn(worker, variant, level, GameAction.ACTION1) == (expected, "game-over")
        assert pit == 0 or 2 <= pit < cap, "k >= 2 keeps ACTION1 a qualifying one-press probe"
    if variant != "control":
        assert _old_figure(variant) != _budget(variant), "the fixture must DIVERGE"


@pytest.mark.parametrize("variant", ["base", "cap", "pit"])
def test_n0_the_unconfigured_probe_reads_repetition_death(tmp_path: Path, variant: str) -> None:
    """N3's premise through the REAL stage, unconfigured: S4's caps are the
    repetition-death figure (`k` on divergent levels), so on this fixture the
    two instruments disagree by construction — moving C (CAP) leaves the
    divergent levels' figure unmoved, moving k (PIT) moves it. This is the R-22
    defect reproduced; it must stay true post-I-1 (the HOUSE RULE: the
    unconfigured figure is today's). Green both sides."""
    worker = _write_worker(tmp_path, variant)
    report = s4.run_s4(worker, _cfg_unconfigured(), out_dir=tmp_path / "out")
    assert tuple(report["caps"]["values"]) == _old_figure(variant)
    assert tuple(report["caps"]["values"]) != _budget(variant)


# --------------------------------------------------------------------------- #
# N1 — unconfigured S4 output byte-identical to today (green both sides)
# --------------------------------------------------------------------------- #


def _drive(root: Path, variant: str, cfg: Mapping, *, isolated: bool = False) -> tuple:
    worker = _write_worker(root, variant)
    if isolated:
        report = s4.run_s4_isolated(worker, cfg)
    else:
        report = s4.run_s4(worker, cfg)
    out_dir = worker.parent / (worker.name + s4.OUT_SUFFIX)
    return report, _out_files(out_dir, root)


@pytest.mark.parametrize("case", sorted(N1_CASES))
def test_n1_unconfigured_s4_output_is_byte_identical(tmp_path: Path, case: str) -> None:
    """N1 / the HOUSE RULE: the assigner, driven TWICE on a fixture slot with no
    I-1 knob set, writes exactly the files HEAD 23e7392 wrote, byte-for-byte
    (normalized only for the tmp root and the runtime version strings). Cases
    (reading F): code defaults on the divergent BASE (hard reject, report only);
    the HEAD-era armed knobs cap_fit record + official-band (fit, metadata,
    band block); code defaults on CONTROL (hard fit + metadata)."""
    variant, make_cfg = N1_CASES[case]
    frozen = N1_FROZEN[case]
    first_report, first = _drive(tmp_path / "run-1", variant, make_cfg())
    _second_report, second = _drive(tmp_path / "run-2", variant, make_cfg())
    assert first == second, f"{CLAUSE_N1} — two drives of one slot disagree ({case})"

    readable = {
        "verdict": first_report["verdict"],
        "caps": first_report["caps"]["values"],
        "baselines": first_report["result"]["baseline_actions"],
        "attempts": [a["baselines"] for a in first_report["result"]["attempts"]],
        "rng_seed": first_report["rng_seed"],
    }
    expected = {key: frozen[key] for key in readable}
    assert readable == expected, f"{CLAUSE_HOUSE_RULE} ({case}): the S4 NUMBERS moved"

    digests = {name: _sha(text) for name, text in first.items()}
    assert sorted(digests) == sorted(frozen["files"]), (
        f"{CLAUSE_N1} ({case}): the stage now writes {sorted(digests)}, "
        f"HEAD wrote {sorted(frozen['files'])}"
    )
    moved = sorted(name for name in digests if digests[name] != frozen["files"][name])
    assert not moved, f"{CLAUSE_N1} ({case}): bytes changed in {moved}"


def test_n1_the_isolated_child_writes_the_same_bytes(tmp_path: Path) -> None:
    """N1 through the pipeline's own entry point: `run_s4_isolated` (a fresh
    interpreter running `python -m gen.s4_baselines`) on the unconfigured BASE
    slot writes the frozen HEAD bytes too (pre-state fact P4)."""
    _report, files = _drive(tmp_path, "base", _cfg_unconfigured(), isolated=True)
    frozen = N1_FROZEN["legacy-hard/base"]["files"]
    assert {name: _sha(text) for name, text in files.items()} == frozen, CLAUSE_N1


# --------------------------------------------------------------------------- #
# N2 — the re-centered g statistic derives from the named instrument
# --------------------------------------------------------------------------- #


def test_n2_the_two_instruments_disagree_in_the_checked_in_data() -> None:
    """N2's ground truth, re-derived from checked-in data (green both sides):
    effort.csv's officials give `ratio = actions / baseline` median 15/19 =
    0.789 over n=183, i.e. a g center of 19/15 = 1.2667 — the audit's "1.267"
    to 3 dp — while D7 centers g at 2.00 (canon §8). The two instruments
    disagree by 0.73 in g: the finding the contract rules on."""
    rows = _effort_officials()
    assert len(rows) == N_OFFICIAL_LEVELS, (
        f"effort.csv carries {len(rows)} official levels, the audit's instrument has "
        f"{N_OFFICIAL_LEVELS} — N2's derivation would be against different data"
    )
    center = _effort_g_center()
    assert center == pytest.approx(19 / 15, abs=1e-12)
    assert round(center, 3) == AUDIT_RECENTER_TARGET
    assert abs(D7_MEDIAN - center) > 0.7


def test_n2_recentered_g_derives_from_effort_csv(tmp_path: Path) -> None:
    """N2: the re-centered g center equals effort.csv's officials median read
    as a g (`1 / median(actions / baseline)` = 1.2667), at D7's quoted 2-dp
    precision (reading A: the instrument named is effort.csv).

    Precedence (reading B): if any knob the assigner reads MOVES fit_g's center
    off 2.00, the sampler's own center under that knob is the statistic, and
    one such setting must land on the target — a matching constant cannot
    rescue a knob that centers elsewhere. With no such knob, a hinted named
    constant (gen.s4_baselines / a new gen module), a hinted zero-arg helper,
    or template.yaml's g.median at the target passes. RED on the pre-I-1 tree.
    """
    target = _effort_g_center()
    knob_centers, static_hits, seen = _recentering_hits(target, tmp_path)
    expected = (
        f"Expected a g center of {target:.4f} (effort.csv officials, n={N_OFFICIAL_LEVELS}: "
        f"1 / median(actions / baseline)) +/- {RECENTER_TOL}."
    )
    if knob_centers:
        on_target = [
            entry
            for entry in knob_centers
            if abs(float(entry.rsplit(" ", 1)[-1]) - target) <= RECENTER_TOL
        ]
        assert on_target, (
            f"I-1 N2 RED — contract: '{CLAUSE_N2}' {PROMISE_N2} {expected} The assigner's "
            f"re-centering knob(s) center the sampler elsewhere: {knob_centers}. Seen: {seen}"
        )
        return
    assert static_hits, (
        f"I-1 N2 RED — contract: '{CLAUSE_N2}' {PROMISE_N2} {expected} No knob moves fit_g's "
        f"center and no constant, helper or template value carries it. Seen: {seen}"
    )


# --------------------------------------------------------------------------- #
# N3 — the reworked probe measures budget.cap, not repetition-death
# --------------------------------------------------------------------------- #


def test_n3_reworked_probe_is_a_function_of_budget_cap(probe_discovery: dict) -> None:
    """N3: SOME discoverable reworked-probe surface (reading C), at ONE path,
    reads budget.cap's bounded quantity on all three variants — [41,53,67] on
    BASE, [47,59,73] on CAP (C moved, k fixed), [41,53,67] on PIT (k moved, C
    fixed) — where the HEAD probe reads [3,53,5] / [3,59,5] / [6,53,2]. Exact,
    in the old probe's own unit (reading D: level 2, where the phenomena
    coincide, must still read C). RED on the pre-I-1 tree."""
    passing = probe_discovery["passing"]
    assert passing, (
        f"I-1 N3 RED — contract: '{CLAUSE_N3}' {PROMISE_N3} On the fixture the old probe "
        f"reads {[list(_old_figure(v)) for v in ('base', 'cap', 'pit')]} and budget.cap is "
        f"{[list(_budget(v)) for v in ('base', 'cap', 'pit')]} (BASE/CAP/PIT); no surface "
        f"read budget.cap on all three. Surfaces tried: "
        f"{[s.label for s in probe_discovery['surfaces']]}. Diagnostics: "
        f"{probe_discovery['diagnostics']}. Notes: {probe_discovery['notes']}"
    )
    for _label, path in passing:
        assert _budget("base") != _old_figure("base"), path  # the divergence is live


# --------------------------------------------------------------------------- #
# N4 — both old figures stay, labeled
# --------------------------------------------------------------------------- #


def test_n4_the_d7_centering_is_preserved_as_a_named_alternative() -> None:
    """N4 (figure 1): D7's centering — median 2.00, IQR 1.54-2.96 — survives the
    re-centering as a NAMED object (module constant / mapping entry / dataclass
    in gen.s4_baselines or a new gen module, or a named template block other
    than the live `g:` line) holding all three numbers together, its name
    carrying one of OLD_CENTERING_LABELS (reading E). RED on the pre-I-1 tree:
    HEAD keeps those numbers only in configs."""
    labeled, other = _named_d7_alternatives()
    assert labeled, (
        f"I-1 N4 RED — contract: '{CLAUSE_N4}' {PROMISE_N4_CENTER} No named object holds "
        f"D7's (2.00, 1.54, 2.96) under a label from {OLD_CENTERING_LABELS}. Unlabeled "
        f"holders / notes: {other}"
    )


def test_n4_the_old_burn_figure_is_recorded_beside_the_new_one_and_labeled(
    probe_discovery: dict,
) -> None:
    """N4 (figure 2): in the SAME output that carries the reworked probe's
    figure (N3's passing surface), the HEAD probe's figure for that fixture —
    [3, 53, 5] on BASE, pre-state fact P1 — is also recorded, at a different
    path, labeled as the old/burn instrument by its path or a sibling string
    (reading E). RED on the pre-I-1 tree (there is no new figure to sit beside)."""
    passing = probe_discovery["passing"]
    assert passing, (
        f"I-1 N4 RED — contract: '{CLAUSE_N4}' {PROMISE_N4_PROBE} No reworked-probe figure "
        "was found (see N3), so the old figure has nothing to be recorded beside."
    )
    findings: list[str] = []
    for label, new_path in passing:
        obj = probe_discovery["base_objects"].get(label)
        labeled, unlabeled = _labeled_old_figure(obj, new_path)
        if labeled:
            return
        findings.append(f"{label} (new figure @ {new_path}): unlabeled old figure at {unlabeled}")
    pytest.fail(
        f"I-1 N4 RED — contract: '{CLAUSE_N4}' {PROMISE_N4_PROBE} The old probe figure "
        f"{list(_old_figure('base'))} is not present-and-labeled (labels {OLD_PROBE_LABELS}) "
        f"beside the new one: {findings}"
    )
