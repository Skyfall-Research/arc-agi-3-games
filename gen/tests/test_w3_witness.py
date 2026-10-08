"""W3-B3 — R-18 term-implementation witness + R-08 refusal checks. BLIND pins.

Written from the B3 contract alone, by an agent that never read the
implementer's diff. The pre-state is the PHASE-A CLOSE tree (A1's trace
artifact + knob in `gen/frames.py`; A2's invert/silent-levels/tier-gated
override; A3's `lookalikes` report block + `static.lookalike-declared`), and
every "as at pre-state" number below was MEASURED against that tree — from
copies taken into a scratchpad before the implementer started — rather than
read off a diff.

THE CONTRACT (B3)
-----------------
R-18, the exhibit: mosaic-marble-bounce-to-match DECLARES `gate.plate` in
`game.terms`, INTRODUCES it at level 2 (`terms_introduced: [gate.plate]`) and
implements it in ZERO of its 290 lines — and it passed a one-round blind audit
clean. (Measured in the shipped slot: round 1 DID report `gate.plate` dead, and
C-3's corroboration demoted that first sighting to a recording, so the round
passed.) So B3 adds a second, independent signal on the same defect:

  * `gen/s3_verify.py` — the blind S2b prompt asks for a PER-DECLARED-TERM
    implementation site inventory (term -> the code construct that realizes it,
    the bestiary §3 shape), and the report schema gains an OPTIONAL `term_sites`
    block carrying site|absent per term. Absent-site terms feed the EXISTING
    findings machinery as a new direction key, `unimplemented`, riding the
    term-corroboration sidecar exactly the way `dead` / `undeclared` /
    `unreachable` do — C-3's machinery JOINED, never forked.
  * `gen/s3_gate.py` — a check `term-witness` (off|record|fail, default record;
    the template arms record, because a HEURISTIC judgment starts as evidence):
    red when the verifier report carries an absent-site term that corroboration
    CONFIRMED.

  THE PINNED FALSE-POSITIVE TRAP: conduit-watch declares `state.checkpoint` and
  realizes it as the LOCKED set, with no literal "checkpoint" anywhere in its
  source (measured: zero occurrences in `worker/game.py`). "Site" must be
  defined BEHAVIOURALLY, not lexically, or the instrument invents a defect in a
  game that has none.

R-08, the checks half:

  * `gen/s3_static.py` — `static.refusal-honest` (GENERATED-ONLY, the W2-B
    pattern): a refusal path may not BOTH mutate the budget/steps AND paint a
    refusal signal. §6:158's never-both, measured on the AST/source.
  * `refusal-persistence` (s3_visual OR s3_gate — implementer's call, so this
    file searches BOTH): a refusal event whose signal appears in NO settled
    frame while the spec promises persistence is a finding; trace absent is
    not-checked. Mode knob, default record.

PRE-STATE, measured (this is what the contract-bearing pins invert)
-------------------------------------------------------------------
  * `s3_verify.TERM_HISTORY_KEYS` is exactly `("dead", "undeclared",
    "unreachable")` and `TERM_DIRECTIONS` is the three matching triples. There
    is NO `unimplemented` direction, so every PIN 2 assertion fails at
    pre-state with "no `unimplemented` direction".
  * `validate_report` enforces an EXACT top-level key set (`REPORT_KEYS` +
    `OPTIONAL_REPORT_KEYS`), an exact diff key set, an exact `agent` key set and
    an exact claims key set. A `term_sites` block therefore raises wherever it
    is put — which is why PIN 1 is placement-agnostic: the contract does not
    name the block's home, so the pin asks only that SOME placement validates,
    and prints the one it found.
  * `gen.s3_static` exposes no callable whose name mentions refusals, and
    `run_static_checks` returns exactly the five frozen static ids, in order —
    the shape the B2-calibrated 25-official battery (200/200) counts.
  * `gen.s3_gate.structural_acceptance` returns exactly the five frozen gate
    ids, in order, and nothing in `gen.s3_gate` mentions terms or witnesses.
  * `config/template.yaml` carries no key mentioning witnesses, refusals or
    persistence.

THE REFUSAL EXHIBITS, measured on the shipped sources before writing a fixture
-----------------------------------------------------------------------------
Both violations are CROSS-FUNCTION, and that fact shapes every PIN 4 fixture:

  * pump-phase-time-echo — charges at `self._used += 1` (`_resolve`, line 796,
    unconditional and ABOVE both refusal branches) and paints `C_FLASH`
    (`_paint`, lines 924-927 / 933). Bridged by the `_fx_queue` overlay dict.
  * convoy-in-the-fog — decides the refusal in `step()` (line 859,
    `self._refused_at = clicked`), charges via `self._cargo.pop()`
    (`_burn_one_drum`, line 932, reached through `_roll_one_cell`) and paints
    `_tile(REFUSAL)` (`_repaint`, line 1020). Three functions, bridged by the
    `self._refused_at` sentinel. Its own comment says it charges ("the step
    still burns a drum exactly as an ACTION5 advance would").
  * conduit-watch — CLEAN: `_refuse()` (line 741) only makes a pre-coloured
    sprite visible, and the budget decrement (`self._budget -= 1`, line 818) is
    gated behind the `changed` boolean the refusal returns False into.
  * pump-flow-match-glow — CLEAN by budget: `self.charge -= 1` (line 465) lives
    only in the success branch.

So an INTRA-function rule detects NEITHER exhibit, and the contract's own
replay requirement ("pump-phase/convoy fire refusal-honest") forces a reading
that follows the refusal sentinel across the call tree rooted at `step()`. The
PIN 4 fixtures are therefore built on that same shape — a sentinel attribute set
in `step()`, the charge in one helper, the paint in another — and differ from
each other in NOTHING ELSE. That is the control, and it is stated here so a
narrow implementation fails against a named scope rather than a mystery.

PINS
----
1. the report's optional `term_sites` block: (a) a report carrying it
   validates; (b) it round-trips through `write_report`; (c) a report WITHOUT
   it still validates and `SCHEMA_VERSION` is unchanged; (d) it distinguishes a
   term WITH a site from a term whose site is ABSENT; (e) every SHIPPED report
   in `out/` still validates unchanged (real old-report compat, not a
   fabrication); (f) the six pre-existing reject codes all survive.
2. the `unimplemented` direction joins the corroboration sidecar: (a) the
   direction exists in the term machinery; (b) a synthetic TWO-ROUND flow
   demotes round 1 and lets round 2 stand; (c) DIRECTION INDEPENDENCE — a term
   seen `dead` in round 1 does not corroborate an `unimplemented` sighting in
   round 2; (d) the sidecar records the new direction and reads back; (e) a
   pre-B3 three-key history still reads (the two shipped sidecars are the
   exhibit); (f) knob OFF is byte-identical to today.
3. the `term-witness` gate check: (a) modes off|record|fail, default record;
   (b) the template arms record; (c) red on a CONFIRMED absent-site term;
   (d) NOT red on an uncorroborated one (the conduit trap, driven through the
   real two-round machinery rather than a guessed representation); (e) a bad
   mode is loud; (f) the officials' structural battery keeps its five ids.
4. `static.refusal-honest`: (a) the three-way matrix — mutate+paint FAILS,
   silent-charge PASSES, free-signal PASSES; (b) a do-nothing refusal passes;
   (c) generated-only — the same bytes as an official are never a fail;
   (d) `run_static_checks` keeps its five frozen ids; (e) the real exhibits —
   pump-phase and convoy FIRE, conduit and pump-flow are SILENT; (g) SCOPE
   PROBE, reported apart from the matrix: a free refusal whose charge is gated
   by a boolean local, or inside the callee, is still free.
5. `refusal-persistence`: (a) trace ABSENT is not-checked, never a finding;
   (b) trace present + a signal that reaches NO settled board (drawn in an
   animation frame, swallowed before the action settles) + a spec promising
   persistence = finding; (c) a signal that persists = no finding; (d) mode
   knob, default record.

HOW THE NEW SURFACES ARE FOUND (the contract names ids, not symbols)
--------------------------------------------------------------------
The contract names check ids (`term-witness`, `static.refusal-honest`,
`refusal-persistence`) and one direction key (`unimplemented`). It names no
Python symbol, no config path and no home for the report block, so a blind test
may not assume any of them:

  * the detectors — every check-shaped module-level function in the candidate
    module is bound from a pool of named arguments (the `test_w2_sysclick.py` /
    `test_w3_deception.py` idiom) and called; only `CheckResult`s are kept, and
    the verdict under test is the one carrying the contract's id.
  * the mode knobs — their config paths are read back out of `config/template.yaml`,
    which the contract requires to arm them. That makes every mode pin
    path-agnostic, and it is also PIN 3b / PIN 5d.
  * the report block and the direction's diff list — searched over the plausible
    set, and the accepted one is printed in the failure message.

WHAT THE PINS MEASURED (written blind; recorded here after running them)
------------------------------------------------------------------------
At the PRE-STATE this file scored 18 failed / 10 passed / 4 errors — the 10 and
the 4 setup errors are named above, and every other pin was contract-bearing.
Against the landed implementation it scores 32 passed / 2 failed, and the 2 are
one finding, PIN 4g, described next.

RESOLVED WHILE MEASURING (a blind test may be wrong; these were)
-----------------------------------------------------------------
  * "settled frame" — first read as the SIDECAR's sampled boards (reset, level
    transitions, final), which would make a one-step flash a finding. The
    implementation reads it as the STEP's own settled board, and that is the
    better reading: the trace keeps `frame[-1]` per step, so a signal a player
    sees for a whole step IS settled. PIN 5b was rebuilt on an intra-step
    transient, which is the defect the check is actually for.
  * PIN 2a first also required `unimplemented` in `TERM_HISTORY_KEYS`. It does
    not: that would force the migration PIN 2e forbids. The behavioural pin
    (2d — the round is recorded and reads back) is what matters, and it holds.
  * PIN 4's first fixtures kept a refusal-named sprite in EVERY variant "so the
    boards are comparable". That was a confound, not a control: the check reads
    the source, where a sprite constructed with a refusal name is a signal site
    whether or not the game ever shows it, so all four variants fired. A game
    that signals nothing now declares no refusal colour and no refusal sprite.

AMBIGUITIES CARRIED (for the lead, also in the handback)
--------------------------------------------------------
  * PIN 4g is the LIVE finding, and it is a scope report rather than a matrix
    verdict. The charge leg asks "is a budget mutation reachable from the
    refusal path and not structurally skipped?", which is branch position, not
    the guard's value. So a free refusal written `if moved: self._charge()`
    after the branch, or `self._charge(moved)` with the test inside `_charge`,
    is flagged although the refused action provably spends nothing. The error
    direction is a FALSE POSITIVE — it rejects a legal game — and the
    boolean-flag spelling is ordinary Python the four-game corpus happens not
    to contain. B3 permits "the narrow honest version ... and record scope",
    and the check DOES state its scope on every verdict, so this may be
    accepted as written; the lead decides whether the flag idiom is in scope.
  * PIN 2f/3c assume the `unimplemented` finding does NOT become a verifier
    reject: the contract routes "red" to the gate check, whose default is
    `record` ("a HEURISTIC judgment starts as evidence"), and a verifier reject
    would bypass that knob entirely. Both hold as shipped.
  * PIN 2e pins a pre-B3 three-key history READABLE, because
    `_validate_term_history_entry` requires every key in `TERM_HISTORY_KEYS`
    and a fourth required key would orphan both shipped sidecars — including
    mosaic's, the one carrying the `gate.plate` sighting this contract is
    about. It holds as shipped.
  * PIN 5 builds the promise from `knobs.refusal: visible`, which exists today.
    B1's `knobs.refusal_transient` is a PARALLEL lane; the fixtures never set
    it, so they read as "persistence promised" under either schema.

RULES OBEYED: tmp_path only; `out/` is a READ-ONLY source, always copied to tmp
before a replay (reports are read in place, never written); no API calls; no
network; nothing is committed.
"""

from __future__ import annotations

import copy
import inspect
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml

from gen import s3_gate, s3_static, s3_verify
from gen.config import load_config
from gen.frames import (
    FrameCapture,
    capture_from_json,
    capture_worker,
    read_trace,
    resolve_trace_frames,
    trace_path,
)
from gen.s3_static import CheckResult, run_static_checks

# B3 lets the implementer put `refusal-persistence` in s3_visual OR s3_gate, so
# this file SEARCHES both and must not be held hostage by either. A module that
# will not import is recorded and surfaced in the PIN 5 failure messages rather
# than taking this file's collection down with it — which matters concretely:
# s3_visual is also B1's lane, edited in parallel with this contract.
_S3_VISUAL_IMPORT_ERROR: str | None = None
try:
    from gen import s3_visual
except (ImportError, SyntaxError) as _exc:  # pragma: no cover - depends on the sibling lane
    s3_visual = None  # type: ignore[assignment]
    _S3_VISUAL_IMPORT_ERROR = f"gen.s3_visual could not be imported: {type(_exc).__name__}: {_exc}"

# --------------------------------------------------------------------------- #
# the contract's own names
# --------------------------------------------------------------------------- #

# The three ids B3 spells out.
WITNESS_CHECK_STEMS = ("term-witness", "term_witness", "gate.term-witness")
REFUSAL_HONEST_CHECK = "static.refusal-honest"
PERSISTENCE_CHECK_STEMS = (
    "refusal-persistence",
    "refusal_persistence",
    "static.refusal-persistence",
    "gate.refusal-persistence",
)
# The ONE direction key the contract spells out.
WITNESS_DIRECTION = "unimplemented"

MODE_OFF, MODE_RECORD, MODE_FAIL = "off", "record", "fail"
MODES = (MODE_OFF, MODE_RECORD, MODE_FAIL)
DEFAULT_MODE = MODE_RECORD

# The three directions C-3 froze, measured at pre-state. B3 JOINS them.
HEAD_TERM_DIRECTIONS = ("dead", "undeclared", "unreachable")

# The five static ids frozen by B7 and counted by the 25-official battery.
HEAD_STATIC_IDS = (
    "static.complete-action",
    "static.sys-click-truthful",
    "static.unread-minus2",
    "static.parsed-field-no-reader",
    "static.palette-hud-collision",
)
# The five structural gate ids, in architecture §3 order (`gen.s3_gate`).
HEAD_GATE_IDS = (
    "gate.sprite-density",
    "gate.level-count",
    "gate.baseline-descent",
    "gate.random-fails-l1",
    "gate.source-size",
)
# The six reject codes frozen before B3. The tuple may GROW; none may vanish.
HEAD_REJECT_CODES = (
    "forbidden-static",
    "undeclared-deception",
    "dead-spec-term",
    "undeclared-term",
    "unreachable-declared-mechanic",
    "solver-quality",
)

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "config" / "template.yaml"
PILOT_CONFIG = REPO / "config" / "b001-pilot.yaml"
TOY = REPO / "gen" / "tests" / "toy_worker"
CORPUS = REPO / "out" / "corpus"

# The contract's four named replay sources.
PUMP_PHASE = CORPUS / "b002-triple" / "pump-phase-time-echo"
CONVOY = CORPUS / "b002-triple" / "convoy-in-the-fog"
CONDUIT = CORPUS / "b003r2-simplicity" / "conduit-watch"
MOSAIC = CORPUS / "b003r2-simplicity" / "mosaic-marble-bounce-to-match"
PUMP_FLOW = CORPUS / "b001-pilot" / "pump-flow-match-glow"

# The two games the contract says FIRE, and the two it says stay SILENT.
REFUSAL_FIRES = (("pump-phase-time-echo", PUMP_PHASE), ("convoy-in-the-fog", CONVOY))
REFUSAL_SILENT = (("conduit-watch", CONDUIT), ("pump-flow-match-glow", PUMP_FLOW))

# The two real exhibits R-18 is about.
MOSAIC_TERM = "gate.plate"
CONDUIT_TERM = "state.checkpoint"

# Signed-vocabulary terms the synthetic rounds use. Asserted into the vocabulary
# by a fixture wall below, so a vocabulary change fails loudly here.
TERM_FILLER = "move.grid"
TERM_X = "gate.phase"
TERM_Y = "hazard.timed"

# Spellings a blind test must tolerate for a block the contract writes in prose
# ("report schema gains optional `term_sites` (site|absent per term)").
BLOCK_NAMES = ("term_sites", "term-sites", "termsites", "sites", "implementation_sites")
# ...and for the diff list the `unimplemented` direction's findings live in.
WITNESS_LIST_NAMES = (
    "unimplemented_terms",
    "unimplemented_spec_terms",
    "unimplemented",
    "witness_absent_terms",
    "absent_site_terms",
)

SYNTHETIC_NOTE = "synthetic — written by gen/tests/test_w3_witness.py"
SESSION_ID = "w3b3-blind-session"
GAME_ID = "w3b3-witness"
MODE_FULL = "full"

# The refusal fixtures' one colour, written by nothing else in the source.
C_REFUSE = 6


# --------------------------------------------------------------------------- #
# the refusal fixture family — ONE skeleton, four refusal paths
# --------------------------------------------------------------------------- #
#
# Modelled on the measured exhibits: a sentinel attribute set in the refusal
# branch of `step()`, the charge in `_charge()` and the paint in `_repaint()`,
# so the charge and the paint are NEVER in the same function — which is the
# shape both real violations have.
#
# THE CONTROL, stated precisely. The variants differ in the refusal path AND in
# the machinery that path needs, and in NOTHING else. A game that does not
# signal its refusals does not declare a refusal sprite or a refusal colour
# either — carrying those in a "silent" fixture would be a confound, not a
# control, because the check measures the SOURCE: a sprite constructed with a
# refusal name is a signal site whether or not the fixture ever shows it.
# (Measured: with the sprite present in every variant, all four fired.)

REFUSAL_GAME = '''"""Fixture ({label}): a blocked move on an 8x8 board."""

import numpy as np
from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL = 4, 9, 12
{refusal_const}

DIRS = {{
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}}


def _level():
    return Level(
        sprites=[
            Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
            Sprite([[WALL] * 8], name="wall_bottom", x=0, y=7),
            Sprite([[WALL]] * 6, name="wall_left", x=0, y=1),
            Sprite([[WALL]] * 6, name="wall_right", x=7, y=1),
            Sprite([[GOAL]], name="goal", x=6, y=6, layer=1, collidable=False),
{refusal_sprite}            Sprite([[PLAYER]], name="player", x=1, y=1, layer=2),
        ]
    )


class RefusalToy(ARCBaseGame):
    """{label}: the refusal path {summary}."""

    def __init__(self) -> None:
        super().__init__(
            game_id="w3b3-{slug}",
            levels=[_level(), _level()],
            camera=Camera(width=8, height=8),
            available_actions=[1, 2, 3, 4],
        )
        self._budget = 60
        self._refused_at = None

    def _is_legal(self, target):
        x, y = target
        return 1 <= x <= 6 and 1 <= y <= 6

    def _charge(self{charge_params}):
{charge_body}

    def _repaint(self):
{paint_body}

    def step(self) -> None:
        self._refused_at = None
        player = self.current_level.get_sprites_by_name("player")[0]
        delta = DIRS.get(self.action.id)
        moved = False
        if delta is not None:
            target = (player.x + delta[0], player.y + delta[1])
            if self._is_legal(target):
                self.try_move("player", *delta)
                moved = True
{charge_in_success}
            else:
                # THE REFUSAL BRANCH: the sentinel the paint pass reads.
                self._refused_at = target
{charge_after}
        self._repaint()
        self.complete_action()
        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
'''

# The charge shapes, as `(params, statement inside the SUCCESS arm, statement
# AFTER the branch, body of _charge)`. "Charged" means the refusal path reaches
# the decrement. Three spellings of "not charged" are built because they are not
# equivalent to a source-level reader, and the difference is the whole of PIN 4g.
CHARGE_ALWAYS = (
    "",
    "",
    "        self._charge()",
    """\
        # Charged on EVERY action, the refused ones included — pump-phase's
        # unconditional `self._used += 1` above both refusal branches.
        self._budget -= 1""",
)
# THE CANONICAL free refusal, and the one PIN 4a's "free-signal passes" leg
# means: the charge lives in the SUCCESS ARM, so the refusal branch skips it
# structurally. pump-flow-match-glow is written exactly this way
# (`self.charge -= 1` inside the success branch of `FlowState.apply()`), and
# conduit-watch's callee-returns-False shape has the same property — the refusal
# branch and the budget mutation are never on one path.
CHARGE_ON_SUCCESS = (
    "",
    "                self._charge()",
    "",
    """\
        # Reached only from the success arm, so a refusal costs nothing.
        self._budget -= 1""",
)
# The same claim spelled with a BOOLEAN GUARD after the branch. The refused
# action leaves `moved` False and spends nothing, but proving that needs
# dataflow on a local rather than the structural "which branch is this in?".
CHARGE_FLAG_GUARDED = (
    "",
    "",
    """\
        if moved:
            self._charge()""",
    """\
        # Reached only when the guard above said the move happened.
        self._budget -= 1""",
)
# ...and with a CALLEE-side guard: `step()` always calls `_charge`, and
# `_charge` decides. The refused path still spends nothing.
CHARGE_CALLEE_GUARDED = (
    ", moved",
    "",
    "        self._charge(moved)",
    """\
        # The refused action reaches this call, and spends nothing in it.
        if moved:
            self._budget -= 1""",
)

# The paint bodies. "Paints" means the refusal path writes the refusal colour.
PAINT_REFUSAL = """\
        flash = self.current_level.get_sprites_by_name("refusal")[0]
        if self._refused_at is not None:
            flash.pixels[:, :] = C_REFUSE
            flash.set_visible(True)
        else:
            flash.set_visible(False)"""
# ...and the persistent variant, which never takes the signal back down.
PAINT_REFUSAL_PERSISTENT = """\
        flash = self.current_level.get_sprites_by_name("refusal")[0]
        if self._refused_at is not None:
            flash.pixels[:, :] = C_REFUSE
            flash.set_visible(True)"""
PAINT_NOTHING = """\
        # No refusal signal at all: the player is told nothing.
        return"""

# The declarations a SIGNALLING refusal needs, and their absence in a silent
# one. A game that never shows a refusal declares neither the colour nor the
# sprite — see "THE CONTROL" above for why carrying them anyway is a confound.
REFUSAL_CONST = "C_REFUSE = 6  # the refusal signal colour; written by nothing else"
NO_REFUSAL_CONST = (
    "# This game signals nothing on refusal: no refusal colour, no refusal sprite."
)
REFUSAL_SPRITE = """\
            Sprite(
                np.full((1, 1), -1, dtype=np.int8),
                name="refusal",
                x=3,
                y=3,
                layer=3,
                collidable=False,
                visible=False,
            ),
"""

# slug -> (summary, charge, paint) — the matrix the contract names, plus the
# do-nothing negative control and the persistent-signal variant PIN 5c needs.
REFUSAL_VARIANTS = {
    "both": ("charges AND paints (the §6:158 violation)", CHARGE_ALWAYS, PAINT_REFUSAL),
    "silent": ("charges silently", CHARGE_ALWAYS, PAINT_NOTHING),
    "free": ("signals freely", CHARGE_ON_SUCCESS, PAINT_REFUSAL),
    "nothing": ("does nothing at all", CHARGE_ON_SUCCESS, PAINT_NOTHING),
    "persistent": ("signals freely and never clears it", CHARGE_ON_SUCCESS,
                   PAINT_REFUSAL_PERSISTENT),
    "free_flag_guarded": ("signals freely, guarded by a boolean local",
                          CHARGE_FLAG_GUARDED, PAINT_REFUSAL),
    "free_callee_guarded": ("signals freely, guarded across a call boundary",
                            CHARGE_CALLEE_GUARDED, PAINT_REFUSAL),
}
# The two guard spellings PIN 4g probes, by slug and by what the guard is.
GUARDED_FREE_VARIANTS = (
    ("free_flag_guarded", "a boolean local tested after the branch (`if moved:`)"),
    ("free_callee_guarded", "a guard inside the callee (`_charge(moved)`)"),
)

# THE INTRA-STEP TRANSIENT, written standalone rather than through the template
# above because it needs a multi-frame action and the template's whole value is
# that its five variants differ in nothing but the refusal path.
#
# The refusal takes TWO engine passes: the first paints the flash and does NOT
# complete the action, the second hides it and completes. So the action renders
# two frames, the flash is in frame[0], and `frame[-1]` — the SETTLED board, the
# one the trace records and the one a player is left looking at — never carries
# it. That is a refusal signal that appears in no settled frame, against a spec
# that promises `refusal: visible`.
TRANSIENT_GAME = '''"""Fixture (transient): the refusal flashes inside one action and settles away."""

import numpy as np
from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL = 4, 9, 12
C_REFUSE = 6  # the refusal signal colour; written by nothing else

DIRS = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}


def _level():
    return Level(
        sprites=[
            Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
            Sprite([[WALL] * 8], name="wall_bottom", x=0, y=7),
            Sprite([[WALL]] * 6, name="wall_left", x=0, y=1),
            Sprite([[WALL]] * 6, name="wall_right", x=7, y=1),
            Sprite([[GOAL]], name="goal", x=6, y=6, layer=1, collidable=False),
            Sprite(
                np.full((1, 1), -1, dtype=np.int8),
                name="refusal",
                x=3,
                y=3,
                layer=3,
                collidable=False,
                visible=False,
            ),
            Sprite([[PLAYER]], name="player", x=1, y=1, layer=2),
        ]
    )


class TransientRefusalToy(ARCBaseGame):
    """The refusal is drawn for one animation frame and settles away."""

    def __init__(self) -> None:
        super().__init__(
            game_id="w3b3-transient",
            levels=[_level(), _level()],
            camera=Camera(width=8, height=8),
            available_actions=[1, 2, 3, 4],
        )
        self._budget = 60
        self._refused_at = None
        self._anim = 0

    def _is_legal(self, target):
        x, y = target
        return 1 <= x <= 6 and 1 <= y <= 6

    def _charge(self):
        self._budget -= 1

    def _repaint(self):
        flash = self.current_level.get_sprites_by_name("refusal")[0]
        if self._refused_at is not None and self._anim == 1:
            flash.pixels[:, :] = C_REFUSE
            flash.set_visible(True)
        else:
            flash.set_visible(False)

    def step(self) -> None:
        player = self.current_level.get_sprites_by_name("player")[0]
        delta = DIRS.get(self.action.id)
        if delta is None:
            self.complete_action()
            return
        target = (player.x + delta[0], player.y + delta[1])
        if not self._is_legal(target):
            # THE REFUSAL BRANCH: flash on pass 1, settle clean on pass 2.
            self._refused_at = target
            self._anim += 1
            self._repaint()
            if self._anim >= 2:
                self._anim = 0
                self._refused_at = None
                self.complete_action()
            return
        self._refused_at = None
        self._anim = 0
        self.try_move("player", *delta)
        self._charge()
        self._repaint()
        self.complete_action()
        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
'''

# A scripted solver: refuse into the wall once per level, then walk to the goal.
# Player starts at (1,1); ACTION1 from there targets (1,0), which `_is_legal`
# rejects, so step 1 of every level is a refusal and step 2 clears it.
REFUSAL_SOLVER = '''"""Scripted solver for the W3-B3 refusal fixtures."""

from arcengine import ActionInput, GameAction

PLAN = ["ACTION1"] + ["ACTION4"] * 5 + ["ACTION2"] * 5


class Solver:
    def reset(self) -> None:
        self._cursor = {0: 0, 1: 0}

    def next_action(self, frame) -> "ActionInput | None":
        level = frame.levels_completed
        if level not in self._cursor:
            return None
        index = self._cursor[level]
        if index >= len(PLAN):
            return None
        self._cursor[level] = index + 1
        return ActionInput(id=GameAction[PLAN[index]])
'''


# --------------------------------------------------------------------------- #
# staging helpers — tmp_path only
# --------------------------------------------------------------------------- #


def _refusal_source(slug: str) -> str:
    if slug == "transient":
        return TRANSIENT_GAME
    summary, charge, paint = REFUSAL_VARIANTS[slug]
    params, in_success, after, body = charge
    signals = paint is not PAINT_NOTHING
    return REFUSAL_GAME.format(
        label=slug,
        slug=slug,
        summary=summary,
        charge_params=params,
        charge_in_success=in_success,
        charge_after=after,
        charge_body=body,
        paint_body=paint,
        refusal_const=REFUSAL_CONST if signals else NO_REFUSAL_CONST,
        refusal_sprite=REFUSAL_SPRITE if signals else "",
    )


def _slot(tmp_path: Path, slug: str, *, refusal: str = "visible") -> tuple[Path, Path]:
    """A slot the way the corpus ships one: `<slot>/spec.yaml` + `<slot>/worker/`.

    Returns `(worker_dir, spec_path)`. The layout is `out/corpus/<batch>/<slug>/`,
    so a check that walks up from the worker to find the spec and one that is
    handed a `spec_path` both work.
    """
    slot = tmp_path / slug
    worker = slot / "worker"
    worker.mkdir(parents=True)
    (worker / "game.py").write_text(_refusal_source(slug), encoding="utf-8")
    (worker / "solver.py").write_text(REFUSAL_SOLVER, encoding="utf-8")
    spec_path = slot / "spec.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "game": {
                    "slug": slug,
                    "title": slug.replace("-", " "),
                    "terms": [TERM_FILLER],
                    "knobs": {
                        # The PROMISE PIN 5 reads: a visible refusal, with no
                        # `refusal_transient` opt-out (B1's parallel lane).
                        "refusal": refusal,
                        "goal_legible": True,
                        "danger_tell": "none",
                        "deceptions": [],
                    },
                    "levels": [
                        {
                            "relation_to_prev": "first",
                            "terms_introduced": [TERM_FILLER],
                            "sketch": "walk to the goal; the wall refuses",
                        }
                    ],
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return worker, spec_path


def _official(tmp_path: Path, slug: str, source: str) -> Path:
    """An OFFICIAL variant dir: `<slug>.py` + `metadata.json`, no game/solver.

    `gen/officials.py`: the corpus is `games/<slug>/<variant>/`, and
    `s3_static.game_source_path` falls back to "the one non-solver .py here".
    """
    variant = tmp_path / slug / "0a0ad940"
    variant.mkdir(parents=True)
    (variant / f"{slug}.py").write_text(source, encoding="utf-8")
    (variant / "metadata.json").write_text(
        json.dumps({"game_id": f"{slug}-0a0ad940"}) + "\n", encoding="utf-8"
    )
    return variant


def _replay(tmp_path: Path, slot: Path, name: str) -> tuple[Path, Path, FrameCapture]:
    """A shipped slot copied out of the READ-ONLY `out/` tree, with its capture.

    The sidecar supplies the capture: re-running the solver would prove nothing
    these pins are about, and `out/` is never written to.
    """
    if not (slot / "worker" / "game.py").is_file():
        pytest.skip(f"{name}'s shipped worker is not in this tree ({slot})")
    dest = tmp_path / name
    dest.mkdir(parents=True)
    shutil.copytree(
        slot / "worker",
        dest / "worker",
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "tests"),
    )
    shutil.copy2(slot / "spec.yaml", dest / "spec.yaml")
    cap = capture_from_json(json.loads((slot / "worker.frames.json").read_text("utf-8")))
    return dest / "worker", dest / "spec.yaml", cap


def _grid_has(grid, color: int) -> bool:
    return any(color in row for row in grid)


def _rows_have_refuse(rows) -> bool:
    """`C_REFUSE` in a trace board (hex rows) or a sidecar board (ints)."""
    digit = f"{C_REFUSE:x}"
    for row in rows:
        if isinstance(row, str):
            if digit in row:
                return True
        elif C_REFUSE in tuple(row):
            return True
    return False


# --------------------------------------------------------------------------- #
# discovery — the contract names ids, not symbols, paths or placements
# --------------------------------------------------------------------------- #

# Public legs this file never calls through the discovery pool: `run_static_checks`
# is called once by `_run_static` itself, and the other two are expensive and can
# produce none of B3's verdicts.
_DENYLIST = frozenset(
    {"run_static_checks", "run_required_rows", "run_solver_quality", "robustness",
     "merged_gate", "structural_acceptance"}
)


def _flat(name: str) -> str:
    return name.lower().replace("_", "").replace("-", "")


def _named_like(name: str, stems: tuple[str, ...]) -> bool:
    flat = _flat(name)
    return any(_flat(stem) in flat for stem in stems)


def _module_functions(module) -> list[tuple[str, object]]:
    if module is None:
        return []
    found = []
    for name, obj in vars(module).items():
        if not inspect.isfunction(obj):
            continue
        if getattr(obj, "__module__", None) != module.__name__:
            continue
        if name.lower() in _DENYLIST:
            continue
        found.append((name, obj))
    return sorted(found)


def _candidates(module, stems: tuple[str, ...]) -> list[tuple[str, object]]:
    """Module-level callables that could produce the verdict under test.

    Deliberately WIDE: the contract names the check ID and no symbol, so a blind
    test that guessed the function's name would report a false failure for a
    correct implementation that spelled it differently. Every CHECK-SHAPED
    function (`_check_*` / `check_*`, the house idiom) is called too, and only
    `CheckResult`s carrying the contract's id are read back. Every directory
    these run against is a tmp copy and these modules are read-only analysis
    code, so calling one costs nothing.
    """
    out = []
    for name, obj in _module_functions(module):
        low = name.lower()
        check_shaped = low.startswith(("_check", "check", "_result_for"))
        if _named_like(name, stems) or check_shaped:
            out.append((name, obj))
    return out


def _bind(fn, pool: dict):
    """Arguments for `fn` drawn from `pool` by parameter NAME, or None."""
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):  # pragma: no cover - builtins only
        return None
    args: list = []
    kwargs: dict = {}
    for name, param in signature.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        if name in pool:
            if param.kind is param.POSITIONAL_ONLY:
                args.append(pool[name])
            else:
                kwargs[name] = pool[name]
        elif param.default is not param.empty:
            if param.kind is param.POSITIONAL_ONLY:
                return None
        else:
            return None
    return args, kwargs


def _as_results(value) -> list[CheckResult]:
    """Every `CheckResult` in a return value, however it was wrapped."""
    if isinstance(value, CheckResult):
        return [value]
    if isinstance(value, (list, tuple)):
        out: list[CheckResult] = []
        for item in value:
            out.extend(_as_results(item))
        return out
    if isinstance(getattr(value, "result", None), CheckResult):
        return [value.result]
    return []


def _call_all(module, stems: tuple[str, ...], pool: dict) -> tuple[list[CheckResult], list[str]]:
    results: list[CheckResult] = []
    diagnostics: list[str] = []
    found = _candidates(module, stems)
    if not found:
        diagnostics.append(
            f"{getattr(module, '__name__', module)} exposes no module-level function named "
            f"like {list(stems)} and no check-shaped function — this is the pre-state"
        )
    for name, fn in found:
        bound = _bind(fn, pool)
        if bound is None:
            diagnostics.append(f"{name}{inspect.signature(fn)}: could not bind from the pool")
            continue
        args, kwargs = bound
        try:
            produced = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - surfaced in the pin's message
            diagnostics.append(f"{name}: raised {type(exc).__name__}: {exc}")
            continue
        results.extend(_as_results(produced))
    return results, diagnostics


def _with_id(results: list[CheckResult], stems: tuple[str, ...]) -> CheckResult | None:
    for result in results:
        if _named_like(str(result.check_id), stems):
            return result
    return None


def _dump(results, diagnostics=()) -> str:
    body = json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False)
    if diagnostics:
        body += "\n\ndiscovery diagnostics:\n  " + "\n  ".join(diagnostics)
    return body


# --- the knobs, read back out of the template the contract requires to arm ---


def _template() -> dict:
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8")) or {}


def _knob_hits(stems: tuple[str, ...]) -> list[tuple[tuple[str, ...], str]]:
    """Every `(path, value)` in template.yaml that reads as this check's knob.

    The contract requires the template to ARM each new check, so the template is
    where a blind test can learn a knob's config path without guessing it. Both
    shapes are accepted: a scalar key (`term_witness: record`) and a block
    (`term_witness: {mode: record}`).
    """
    hits: list[tuple[tuple[str, ...], str]] = []

    def walk(node: object, path: tuple[str, ...], tainted: bool) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = path + (str(key),)
                walk(value, here, tainted or _named_like(str(key), stems))
        elif isinstance(node, str) and tainted and node in MODES:
            hits.append((path, node))

    walk(_template(), (), False)
    return hits


def _knob_path(stems: tuple[str, ...], what: str) -> tuple[str, ...]:
    hits = _knob_hits(stems)
    assert hits, (
        f"B3 pins `config/template.yaml` to arm {what} ('template arms record'). No key "
        f"named like {list(stems)} carries one of {list(MODES)} in {TEMPLATE}. Every mode "
        "pin reads the knob's config path back out of the template, so this blocks them all."
    )
    armed = [path for path, value in hits if value == MODE_RECORD]
    return (armed or [path for path, _ in hits])[0]


def _cfg_with(base: dict, path: tuple[str, ...], mode: str | None) -> dict:
    """`base` with the knob at `path` set to `mode`, or removed for `None`."""
    cfg = copy.deepcopy(base)
    node = cfg
    for key in path[:-1]:
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            node[key] = nxt
        node = nxt
    if mode is None:
        node.pop(path[-1], None)
    else:
        node[path[-1]] = mode
    return cfg


# --- the term machinery, fetched rather than assumed --------------------------


def _term_directions() -> tuple:
    return tuple(getattr(s3_verify, "TERM_DIRECTIONS", ()) or ())


def _history_keys() -> tuple:
    return tuple(getattr(s3_verify, "TERM_HISTORY_KEYS", ()) or ())


def _witness_row():
    """The `(direction, diff_list_key, code)` triple for `unimplemented`, or None."""
    for row in _term_directions():
        if isinstance(row, (tuple, list)) and row and str(row[0]) == WITNESS_DIRECTION:
            return tuple(row)
    return None


def _witness_list_key() -> str:
    """The diff list the `unimplemented` direction's findings live in.

    Discovered from the module's OWN `TERM_DIRECTIONS`, which is the machinery
    the contract says to join — so this never guesses a spelling, it reads the
    one the implementation chose.
    """
    row = _witness_row()
    assert row is not None and len(row) >= 2, (
        f"B3 adds `{WITNESS_DIRECTION}` as a new DIRECTION KEY riding the term-corroboration "
        f"sidecar 'like dead/undeclared do'. `s3_verify.TERM_DIRECTIONS` carries "
        f"{[str(r[0]) for r in _term_directions()]}, with no {WITNESS_DIRECTION!r} row, so the "
        "direction has not joined C-3's machinery. (Pre-state: the three C-3 directions "
        f"{list(HEAD_TERM_DIRECTIONS)}.)"
    )
    return str(row[1])


def _uncorroborated_terms(report) -> list[dict]:
    key = getattr(s3_verify, "UNCORROBORATED_TERMS_KEY", "uncorroborated_terms")
    return list((report.get("diff") or {}).get(key) or [])


def _demoted_terms(report) -> set[str]:
    return {str(entry.get("term")) for entry in _uncorroborated_terms(report)}


# --------------------------------------------------------------------------- #
# synthetic verifier rounds — the C-3 harness shape, unchanged
# --------------------------------------------------------------------------- #


def _claims() -> dict:
    return {
        "terms": [
            {
                "term": TERM_FILLER,
                "reachable": True,
                "evidence": [{"path": "game.py", "line": 10, "note": SYNTHETIC_NOTE}],
            }
        ],
        "dead_code": [],
        "deceptions": [],
        "enforcement": [],
        "notes": SYNTHETIC_NOTE,
    }


def _agent() -> dict:
    return {
        "session_id": SESSION_ID,
        "model": "synthetic",
        "usd": 0.0,
        "tokens_in": 1,
        "tokens_out": 1,
        "wall_s": 0.0,
        "staged_copy_verified": True,
        "claims": _claims(),
    }


def _diff(**findings) -> dict:
    """A full, valid diff built from `DIFF_KEYS`, plus any discovered list."""
    diff: dict = {key: [] for key in s3_verify.DIFF_KEYS}
    for key, terms in findings.items():
        diff[key] = sorted(terms)
    return diff


class _Slot:
    """One planted slot plus as many FULL verify rounds as a test wants.

    Rounds share the slot — the sidecar is per-slot and accrues across rounds,
    which is the whole subject of the corroboration machinery B3 joins.
    """

    def __init__(self, root: Path, cap: object) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.worker = root / "slot-1"
        shutil.copytree(TOY, self.worker, ignore=shutil.ignore_patterns("__pycache__"))
        self.frames_path = root / s3_verify.FRAMES_NAME
        self.frames_path.write_text("{}", encoding="utf-8")
        self._cap = cap

    def run(self, cfg, **findings) -> dict:
        return s3_verify.assemble_report(
            game_id=GAME_ID,
            worker=self.worker,
            mode=MODE_FULL,
            cfg=dict(cfg),
            cap=self._cap,
            checks=[],
            frames_path=self.frames_path,
            agent=_agent(),
            diff=_diff(**findings),
            spec_hash=None,
        )

    def term_sidecar(self) -> Path:
        return s3_verify.term_history_path(self.worker)

    def entries(self) -> list:
        return s3_verify.read_term_history(self.term_sidecar())


def _corroboration_cfg(base: dict) -> dict:
    """The pilot config with BOTH term-corroboration knobs armed, unwindowed.

    Unwindowed on purpose: a window of 1 would make the two-round pins a test of
    C-2's windowing rather than of the new direction.
    """
    cfg = copy.deepcopy(base)
    verifier = dict(cfg.get("verifier") or {})
    verifier[s3_verify.TERM_CORROBORATION_KEY] = True
    verifier.pop(s3_verify.TERM_WINDOW_KEY, None)
    verifier.pop(s3_verify.LEVER_WINDOW_KEY, None)
    verifier[s3_verify.LEVER_CORROBORATION_KEY] = False
    verifier["exempt_terms"] = []
    cfg["verifier"] = verifier
    return cfg


# --------------------------------------------------------------------------- #
# report helpers — a valid report, and the placements to search
# --------------------------------------------------------------------------- #


def _report(**overrides) -> dict:
    report = {
        "schema_version": s3_verify.SCHEMA_VERSION,
        "game_id": GAME_ID,
        "worker": str(TOY),
        "mode": MODE_FULL,
        "canon": {"docs_root": str(REPO / "canon"), "spec_hash": "a" * 64},
        "frames": {
            "source": "solver",
            "count": 4,
            "levels_completed": 2,
            "win": True,
            "path": "frames.json",
        },
        "checks": [],
        "required_rows": [
            {"row": n, "check_id": f"required.row{n}", "status": "pass"} for n in range(1, 9)
        ],
        "agent": _agent(),
        "diff": {key: [] for key in s3_verify.DIFF_KEYS},
        "verdict": "pass",
        "reject_reasons": [],
        "versions": {"arcengine": "0.9.3", "python": "3.12.0"},
    }
    report.update(overrides)
    return report


def _placements(report: dict) -> dict[str, object]:
    """Where a `term_sites` block could live, by a printable label."""
    return {
        "report": report,
        "report.diff": report["diff"],
        "report.agent": report["agent"],
        "report.agent.claims": report["agent"]["claims"],
    }


def _block_bodies() -> list[tuple[str, object]]:
    """Plausible spellings of "site|absent per term", both real states present.

    Every body says the SAME thing: one term is realized at a named construct
    and one term has no site at all. A blind test may not pick the encoding, so
    it offers the plausible set and reports the one that validated.
    """
    site = "the LOCKED set (`LOCKED = 3`, game.py:85) — the respawn anchor"
    return [
        ("mapping term->site|null", {CONDUIT_TERM: site, MOSAIC_TERM: None}),
        ("mapping term->site|'absent'", {CONDUIT_TERM: site, MOSAIC_TERM: "absent"}),
        (
            "list of {term, site}",
            [{"term": CONDUIT_TERM, "site": site}, {"term": MOSAIC_TERM, "site": None}],
        ),
        (
            "list of {term, site, status}",
            [
                {"term": CONDUIT_TERM, "site": site, "status": "site"},
                {"term": MOSAIC_TERM, "site": None, "status": "absent"},
            ],
        ),
        (
            "two direction lists",
            {"site": [CONDUIT_TERM], "absent": [MOSAIC_TERM]},
        ),
    ]


def _accepted() -> list[tuple[str, dict]]:
    """Every (description, report) whose `term_sites` block `validate_report` takes."""
    accepted = []
    for name in BLOCK_NAMES:
        for shape, body in _block_bodies():
            report = _report()
            for label, holder in _placements(report).items():
                holder[name] = body  # type: ignore[index]
                try:
                    s3_verify.validate_report(report)
                except (ValueError, TypeError):
                    holder.pop(name, None)  # type: ignore[union-attr]
                    continue
                accepted.append((f"{label}.{name} = {shape}", copy.deepcopy(report)))
                holder.pop(name, None)  # type: ignore[union-attr]
    return accepted


# --------------------------------------------------------------------------- #
# session fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def base_cfg() -> dict:
    cfg = load_config(PILOT_CONFIG)
    vocab = s3_verify.load_vocab(cfg)
    for term in (TERM_FILLER, TERM_X, TERM_Y):
        assert term in vocab, (
            f"fixture wall: {term!r} left the {len(vocab)}-term signed vocabulary"
        )
    return cfg


@pytest.fixture(scope="session")
def toy_cap() -> object:
    """A real FrameCapture from the checked-in toy worker (b7-style staging)."""
    game_cls, solver_cls = s3_verify.load_worker_classes(TOY)
    return s3_verify.capture(game_cls, solver_cls)


@pytest.fixture
def slot(tmp_path: Path, toy_cap: object) -> _Slot:
    return _Slot(tmp_path / "planted", toy_cap)


@pytest.fixture(scope="session")
def variants(tmp_path_factory) -> dict[str, tuple[Path, Path, FrameCapture]]:
    """The whole refusal family, staged once and captured WITH a trace.

    `capture_worker(..., trace=True)` is A1's own armed path, so the trace lands
    beside the worker exactly where a reader looks for it.
    """
    root = tmp_path_factory.mktemp("w3b3-refusal")
    built: dict[str, tuple[Path, Path, FrameCapture]] = {}
    for slug in (*REFUSAL_VARIANTS, "transient"):
        worker, spec_path = _slot(root, slug)
        cap = capture_worker(worker, trace=True)
        built[slug] = (worker, spec_path, cap)
    return built


def _variant(variants, slug: str) -> tuple[Path, Path, FrameCapture]:
    return variants[slug]


def _static_pool(worker: Path, cap: FrameCapture, spec_path: Path | None, cfg, mode) -> dict:
    """Named arguments a refusal check could plausibly ask for.

    The mode is offered BOTH ways — as a `cfg` carrying the template's own knob
    and as a bare `mode` string — because the contract fixes neither seam.
    """
    worker = Path(worker)
    spec = None
    if spec_path is not None and Path(spec_path).is_file():
        spec = yaml.safe_load(Path(spec_path).read_text(encoding="utf-8"))
    trace = trace_path(worker)
    return {
        "source": s3_static._parse_game(worker),
        "cap": cap,
        "capture": cap,
        "worker_dir": worker,
        "worker": worker,
        "path": worker,
        "game_dir": worker,
        "spec_path": None if spec_path is None else Path(spec_path),
        "spec_file": None if spec_path is None else Path(spec_path),
        "spec": spec,
        "cfg": cfg,
        "config": cfg,
        "mode": DEFAULT_MODE if mode is None else mode,
        "trace_path": trace if trace.is_file() else None,
        "trace": trace if trace.is_file() else None,
    }


def _run_static(worker, cap, *, spec_path=None, cfg=None, mode=None, stems=None):
    """(results, diagnostics) — every refusal verdict `s3_static` gives this dir."""
    stems = stems or (REFUSAL_HONEST_CHECK, "refusal")
    pool = _static_pool(worker, cap, spec_path, cfg, mode)
    results, diagnostics = _call_all(s3_static, stems, pool)
    # A detector folded into the officials' battery would be a PIN 4d failure,
    # never an invisible one, so its results are collected here too.
    try:
        results.extend(run_static_checks(Path(worker), cap))
    except Exception as exc:  # noqa: BLE001 - surfaced in the pin's message
        diagnostics.append(f"run_static_checks: raised {type(exc).__name__}: {exc}")
    return results, diagnostics


def _honest_verdict(worker, cap, *, spec_path=None, cfg=None, mode=None):
    results, diagnostics = _run_static(worker, cap, spec_path=spec_path, cfg=cfg, mode=mode)
    return _with_id(results, ("refusal-honest", "refusalhonest")), results, diagnostics


# --------------------------------------------------------------------------- #
# PIN 1 — the report's optional `term_sites` block
# --------------------------------------------------------------------------- #


def test_pin1a_report_takes_an_optional_term_sites_block():
    accepted = _accepted()
    assert accepted, (
        "B3: 'report schema gains optional `term_sites` (site|absent per term)'. No "
        f"placement/spelling was accepted by `validate_report`. Tried {list(BLOCK_NAMES)} at "
        f"{list(_placements(_report()))} in {len(_block_bodies())} body shapes. Pre-state: "
        "`validate_report` enforces exact key sets at every level, so the block raises "
        "wherever it is put until the schema takes it."
    )


def test_pin1b_the_block_round_trips_through_write_report(tmp_path):
    accepted = _accepted()
    assert accepted, "PIN 1a states this failure; see it first."
    label, report = accepted[0]
    path = tmp_path / "verifier-report.json"
    s3_verify.write_report(report, path)
    back = json.loads(path.read_text(encoding="utf-8"))
    s3_verify.validate_report(back)
    assert back == report, (
        f"the accepted `term_sites` placement ({label}) did not survive a write/read "
        "round-trip unchanged"
    )


def test_pin1c_reports_without_the_block_still_validate():
    """REGRESSION GUARD: holds before AND after. b7-era readers unchanged."""
    s3_verify.validate_report(_report())
    assert s3_verify.SCHEMA_VERSION == "b7.1", (
        "B3 adds an OPTIONAL block, which is a data addition and not a schema bump — the "
        f"`lookalikes` precedent one contract over. Got {s3_verify.SCHEMA_VERSION!r}."
    )


def test_pin1d_the_block_distinguishes_a_site_from_an_absent_one():
    accepted = _accepted()
    assert accepted, "PIN 1a states this failure; see it first."
    label, report = accepted[0]
    blob = json.dumps(report)
    assert MOSAIC_TERM in blob and CONDUIT_TERM in blob, (
        f"the accepted block ({label}) dropped one of the two terms — a block that cannot "
        "carry BOTH a realized term and an absent-site one records nothing the gate can read"
    )


def test_pin1e_every_shipped_report_still_validates():
    """REGRESSION GUARD, on REAL bytes: old-report compat is measured, not promised.

    `out/` is read-only here — each file is parsed in place and never written.
    Iterated rather than parametrized so an empty corpus is a LOUD failure: a
    glob that finds nothing would otherwise turn this guard into no test at all.
    """
    shipped = sorted(CORPUS.glob("*/*/worker.verifier-report.json"))
    assert shipped, (
        f"no shipped verifier report found under {CORPUS} — this guard measures old-report "
        "compat on real bytes and cannot run on an empty corpus"
    )
    for path in shipped:
        try:
            s3_verify.validate_report(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, TypeError) as exc:
            pytest.fail(
                f"{path.parent.name}'s SHIPPED report stopped validating: {exc}. B3 adds an "
                "OPTIONAL block, so every report written before it must still validate "
                "unchanged."
            )


def test_pin1f_the_frozen_reject_codes_all_survive():
    """REGRESSION GUARD: the tuple may GROW, but none of the six may vanish."""
    missing = [code for code in HEAD_REJECT_CODES if code not in s3_verify.REJECT_CODES]
    assert not missing, (
        f"reject code(s) {missing} left `REJECT_CODES` — every shipped report carrying one "
        "would stop validating"
    )


# --------------------------------------------------------------------------- #
# PIN 2 — the `unimplemented` direction joins the corroboration sidecar
# --------------------------------------------------------------------------- #


def test_pin2a_the_unimplemented_direction_exists():
    directions = [str(row[0]) for row in _term_directions()]
    assert WITNESS_DIRECTION in directions, (
        f"B3: absent-site terms 'feed the existing findings machinery as a new direction key "
        f"(`{WITNESS_DIRECTION}`) riding the term-corroboration sidecar like dead/undeclared "
        f"do'. `TERM_DIRECTIONS` carries {directions} (pre-state: {list(HEAD_TERM_DIRECTIONS)})."
    )
    # NOT pinned here: membership in `TERM_HISTORY_KEYS`. Whether the sidecar
    # holds the new direction as a REQUIRED key or an optional one is the
    # implementer's call, and requiring it would force exactly the migration
    # PIN 2e says must not happen — `_validate_term_history_entry` demands every
    # key in that tuple, so a fourth required one orphans both shipped sidecars.
    # PIN 2d measures the thing that actually matters (the round is recorded and
    # reads back) behaviourally, which no representation choice can fake.
    kept = [d for d in HEAD_TERM_DIRECTIONS if d not in directions]
    assert not kept, (
        f"C-3 direction(s) {kept} were dropped — the contract says JOIN the machinery, never "
        "fork it"
    )


def test_pin2b_two_round_flow_demotes_then_confirms(slot: _Slot, base_cfg: dict):
    key = _witness_list_key()
    cfg = _corroboration_cfg(base_cfg)

    first = slot.run(cfg, **{key: (TERM_X,)})
    assert TERM_X in _demoted_terms(first), (
        f"round 1's {WITNESS_DIRECTION} sighting of {TERM_X!r} must be DEMOTED to the "
        f"`uncorroborated_terms` record — C-3's bar, which this direction rides. Got "
        f"{_uncorroborated_terms(first)!r}"
    )

    second = slot.run(cfg, **{key: (TERM_X,)})
    assert TERM_X not in _demoted_terms(second), (
        f"round 2 re-sighted {TERM_X!r} in the SAME direction, so round 1's sidecar entry "
        f"corroborates it and it must STAND. Got {_uncorroborated_terms(second)!r}"
    )
    assert TERM_X in (second["diff"].get(key) or []), (
        f"a corroborated finding stays in its diff list {key!r} — that list is what the "
        f"gate check reads. Got {second['diff'].get(key)!r}"
    )


def test_pin2c_directions_are_independent(slot: _Slot, base_cfg: dict):
    """A `dead` sighting must NOT corroborate an `unimplemented` one.

    C-3's own ruling, quoted: "a term called dead in one round and undeclared in
    the next corroborates neither, because those two readings contradict each
    other". The new direction inherits it or it is not the same machinery.
    """
    key = _witness_list_key()
    cfg = _corroboration_cfg(base_cfg)

    slot.run(cfg, dead_spec_terms=(TERM_Y,))
    second = slot.run(cfg, **{key: (TERM_Y,)})
    assert TERM_Y in _demoted_terms(second), (
        f"{TERM_Y!r} was reported `dead` in round 1 and `{WITNESS_DIRECTION}` in round 2. "
        "Those are two different findings, so round 2 is still a FIRST sighting and must be "
        f"demoted. Got {_uncorroborated_terms(second)!r}"
    )


def test_pin2d_the_sidecar_records_the_new_direction(slot: _Slot, base_cfg: dict):
    key = _witness_list_key()
    slot.run(_corroboration_cfg(base_cfg), **{key: (TERM_X,)})
    entries = slot.entries()
    assert entries, "the round recorded no sidecar entry at all"
    last = entries[-1]
    assert WITNESS_DIRECTION in last, (
        f"the recorded round carries {sorted(last)} and no {WITNESS_DIRECTION!r} list — every "
        "round's direction lists are appended so a later round has a real history to "
        "corroborate against"
    )
    assert TERM_X in list(last[WITNESS_DIRECTION]), (
        f"the round found {TERM_X!r} in the {WITNESS_DIRECTION} direction and recorded "
        f"{last[WITNESS_DIRECTION]!r}"
    )


def test_pin2e_a_pre_b3_history_still_reads(tmp_path: Path):
    """The SHIPPED sidecars were written with THREE direction keys.

    `_validate_term_history_entry` requires every key in `TERM_HISTORY_KEYS`, so
    a fourth REQUIRED key makes real pipeline state unreadable — mosaic's own
    sidecar, the one carrying the `gate.plate` sighting this contract is about,
    is the first casualty. Copied to tmp first: `out/` is a read-only source.
    Iterated rather than parametrized so an empty corpus is a LOUD failure.
    """
    shipped = sorted(CORPUS.glob("*/*/worker.term-history.json"))
    assert shipped, (
        f"no shipped term-history sidecar found under {CORPUS} — this guard measures the "
        "migration on real pipeline state and cannot run without it"
    )
    for source in shipped:
        local = tmp_path / f"{source.parent.name}{s3_verify.TERM_HISTORY_SUFFIX}"
        shutil.copy2(source, local)
        try:
            entries = s3_verify.read_term_history(local)
        except (ValueError, TypeError) as exc:
            pytest.fail(
                f"{source.parent.name}'s SHIPPED term sidecar stopped reading: {exc}. It was "
                f"written with {list(HEAD_TERM_DIRECTIONS)}; a fourth REQUIRED direction key "
                "orphans real pipeline state that a later round must corroborate against."
            )
        assert entries, f"{source.parent.name}'s sidecar read back empty"


def test_pin2f_the_knob_off_path_is_unchanged(slot: _Slot, base_cfg: dict):
    """REGRESSION GUARD + the reject-routing ruling.

    With corroboration OFF nothing is demoted, and — the adjudication this file
    carries — a `{direction}` finding must not by itself turn the VERIFIER's
    verdict to reject: B3 routes "red" to the gate check, whose default is
    `record` because "a HEURISTIC judgment starts as evidence". A verifier
    reject would bypass that knob entirely.
    """
    key = _witness_list_key()
    cfg = copy.deepcopy(base_cfg)
    verifier = dict(cfg.get("verifier") or {})
    verifier[s3_verify.TERM_CORROBORATION_KEY] = False
    verifier.pop(s3_verify.TERM_WINDOW_KEY, None)
    verifier["exempt_terms"] = []
    cfg["verifier"] = verifier

    report = slot.run(cfg, **{key: (TERM_X,)})
    assert not _uncorroborated_terms(report), (
        "corroboration is OFF, so nothing may be demoted — the canon path, byte for byte"
    )
    assert report["verdict"] == "pass", (
        f"an `{WITNESS_DIRECTION}` finding rejected the VERIFIER (reasons "
        f"{report['reject_reasons']!r}). B3 gives that decision to the gate's `term-witness` "
        "check, born in `record`. If a verifier reject was deliberate, this pin is the lead's "
        "adjudication point."
    )


# --------------------------------------------------------------------------- #
# PIN 3 — the `term-witness` gate check
# --------------------------------------------------------------------------- #


def _gate_pool(report, cfg, mode, worker=None, cap=None) -> dict:
    return {
        "verifier_report": report,
        "report": report,
        "verifier": report,
        "cfg": cfg,
        "config": cfg,
        "mode": DEFAULT_MODE if mode is None else mode,
        "worker_dir": worker,
        "worker": worker,
        "cap": cap,
        "capture": cap,
    }


def _witness_verdict(report, *, cfg=None, mode=None):
    results, diagnostics = _call_all(
        s3_gate, WITNESS_CHECK_STEMS, _gate_pool(report, cfg, mode)
    )
    return _with_id(results, WITNESS_CHECK_STEMS), results, diagnostics


@pytest.fixture
def rounds(slot: _Slot, base_cfg: dict) -> dict:
    """The two real reports PIN 3c/3d need, built by the real machinery.

    Driving the two-round flow rather than hand-writing "confirmed" and
    "uncorroborated" states keeps this pin honest: a blind test must not pick
    the representation the gate reads.
    """
    key = _witness_list_key()
    cfg = _corroboration_cfg(base_cfg)
    first = slot.run(cfg, **{key: (TERM_X,)})
    second = slot.run(cfg, **{key: (TERM_X,)})
    return {"uncorroborated": first, "confirmed": second}


def test_pin3a_mode_knob_semantics_and_the_record_default(rounds):
    report = rounds["confirmed"]
    off, _, diag = _witness_verdict(report, mode=MODE_OFF)
    assert off is None, (
        f"`term-witness` in {MODE_OFF!r} must add no row at all, got {off!r}\n{diag}"
    )

    for mode in (MODE_RECORD, MODE_FAIL):
        found, results, diagnostics = _witness_verdict(report, mode=mode)
        assert found is not None, (
            f"B3 adds a gate check `term-witness` (off|record|fail). No verdict carrying that "
            f"id came back in mode {mode!r}.\n{_dump(results, diagnostics)}"
        )

    default, results, diagnostics = _witness_verdict(report, mode=None)
    recorded, _, _ = _witness_verdict(report, mode=MODE_RECORD)
    assert default is not None and recorded is not None, (
        f"the DEFAULT mode must be `record` — a heuristic judgment starts as evidence.\n"
        f"{_dump(results, diagnostics)}"
    )
    assert default.status == recorded.status, (
        f"the default mode behaved as {default.status!r} and `record` as {recorded.status!r}; "
        "B3 freezes the default at `record`"
    )
    assert default.status != "fail", (
        "the default mode FAILED. `record` reports and changes no verdict; only the armed "
        "`fail` mode is red."
    )


def test_pin3b_the_template_arms_term_witness_at_record():
    path = _knob_path(WITNESS_CHECK_STEMS, "the term-witness check")
    hits = dict(_knob_hits(WITNESS_CHECK_STEMS))
    assert hits.get(path) == MODE_RECORD, (
        f"B3: 'template arms record — a HEURISTIC judgment starts as evidence'. "
        f"`{'.'.join(path)}` is {hits.get(path)!r} in {TEMPLATE}."
    )


def test_pin3c_red_on_a_confirmed_absent_site_term(rounds):
    report = rounds["confirmed"]
    found, results, diagnostics = _witness_verdict(report, mode=MODE_FAIL)
    assert found is not None, (
        f"no `term-witness` verdict came back.\n{_dump(results, diagnostics)}"
    )
    assert found.status == "fail", (
        f"B3: the check is 'red when the verifier report carries an absent-site term that "
        f"corroboration confirmed'. Round 2 re-sighted {TERM_X!r}, so it stands in the diff "
        f"and is confirmed — the check answered {found.status!r}.\n{_dump([found])}"
    )


def test_pin3d_not_red_on_an_uncorroborated_term(rounds):
    """The conduit trap, in its corroboration half.

    Round 1's sighting is a FIRST sighting, demoted to the record. A check that
    goes red on it rejects on exactly the evidence C-3 measured to be unstable —
    and `state.checkpoint`, realized as conduit's LOCKED set with no literal
    "checkpoint" anywhere, is the finding that would be invented.
    """
    report = rounds["uncorroborated"]
    assert TERM_X in _demoted_terms(report), (
        "fixture wall: round 1 did not demote its first sighting; PIN 2b states this failure"
    )
    found, results, diagnostics = _witness_verdict(report, mode=MODE_FAIL)
    if found is None:
        pytest.fail(f"no `term-witness` verdict came back.\n{_dump(results, diagnostics)}")
    assert found.status != "fail", (
        f"the check went red on an UNCORROBORATED first sighting. B3 says red only when "
        f"'corroboration confirmed' it.\n{_dump([found])}"
    )


def test_pin3e_a_bad_mode_is_loud(rounds):
    report = rounds["confirmed"]
    bad = "record-ish"
    raised: list[str] = []
    diagnostics: list[str] = []
    saw_candidate = False
    for name, fn in _candidates(s3_gate, WITNESS_CHECK_STEMS):
        bound = _bind(fn, _gate_pool(report, None, bad))
        if bound is None:
            continue
        args, kwargs = bound
        if bad not in list(kwargs.values()) and bad not in args:
            continue
        saw_candidate = True
        try:
            fn(*args, **kwargs)
        except ValueError as exc:
            raised.append(f"{name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - any other failure is not the pin
            diagnostics.append(f"{name}: {type(exc).__name__}: {exc}")
    assert saw_candidate, (
        "no discovered `term-witness` entry point took a mode argument, so a bad mode cannot "
        "be shown to be loud. PIN 3a states the underlying failure."
    )
    assert raised, (
        f"a mode value outside {list(MODES)} must be a loud ValueError (the "
        "`lookalike_report` / `_enum_key` precedent), not a silent default"
    )


def test_pin3f_the_officials_structural_battery_is_unchanged(tmp_path, toy_cap):
    """REGRESSION GUARD: 'officials' batteries exact'."""
    worker = tmp_path / "battery-worker"
    shutil.copytree(TOY, worker, ignore=shutil.ignore_patterns("__pycache__"))
    report = s3_gate.structural_acceptance(worker, toy_cap)
    ids = tuple(row["check_id"] for row in report["checks"])
    assert ids == HEAD_GATE_IDS, (
        f"`structural_acceptance` returned {list(ids)}; the calibrated five are "
        f"{list(HEAD_GATE_IDS)}. `term-witness` reads the VERIFIER REPORT, so it belongs "
        "outside the structural layer the 25 officials are counted against."
    )


# --------------------------------------------------------------------------- #
# PIN 4 — `static.refusal-honest`
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("slug", "expect_fail"),
    [("both", True), ("silent", False), ("free", False)],
)
def test_pin4a_the_three_way_matrix(variants, slug: str, expect_fail: bool):
    """mutate+paint FAILS; silent-charge PASSES; free-signal PASSES.

    The three fixtures share one skeleton and differ ONLY in `_charge` and
    `_repaint`, and the charge is never in the same function as the paint —
    the measured shape of both real exhibits.
    """
    worker, spec_path, cap = _variant(variants, slug)
    found, results, diagnostics = _honest_verdict(
        worker, cap, spec_path=spec_path, mode=MODE_FAIL
    )
    assert found is not None, (
        f"B3 adds `{REFUSAL_HONEST_CHECK}` (generated-only, the W2-B pattern). No verdict "
        f"carrying that id came back for the {slug!r} fixture.\n{_dump(results, diagnostics)}"
    )
    if expect_fail:
        assert found.status == "fail", (
            f"the {slug!r} refusal path CHARGES (`self._budget -= 1` in `_charge`, reached on "
            "the refused action) and PAINTS (`flash.pixels[:, :] = C_REFUSE` in `_repaint`, "
            "guarded by the `self._refused_at` sentinel). §6:158 is never-both, so this must "
            f"be red; got {found.status!r}.\n{_dump([found])}"
        )
    else:
        assert found.status != "fail", (
            f"the {slug!r} refusal path does only ONE of the two — that is the legal half of "
            f"'charge silently or signal freely, never both'; got {found.status!r}.\n"
            f"{_dump([found])}"
        )


def test_pin4b_a_do_nothing_refusal_passes(variants):
    """The negative control the corpus is full of (conduit's `return False`)."""
    worker, spec_path, cap = _variant(variants, "nothing")
    found, results, diagnostics = _honest_verdict(
        worker, cap, spec_path=spec_path, mode=MODE_FAIL
    )
    assert found is not None, f"no verdict came back.\n{_dump(results, diagnostics)}"
    assert found.status != "fail", (
        f"a refusal that neither charges nor paints cannot violate a never-BOTH rule; got "
        f"{found.status!r}.\n{_dump([found])}"
    )


@pytest.mark.parametrize(
    ("slug", "guard"), GUARDED_FREE_VARIANTS, ids=[s for s, _ in GUARDED_FREE_VARIANTS]
)
def test_pin4g_a_guarded_free_refusal_is_not_a_charge(variants, slug: str, guard: str):
    """SCOPE PROBE, reported separately from the matrix on purpose.

    Same claim as PIN 4a's `free` leg — the refused action spends no budget —
    spelled two other ways. In both, the refusal branch leaves the guard false,
    so the decrement is unreachable from a refused action; proving it needs
    dataflow on the guard rather than the structural "is this statement in an
    arm the refusal branch skips?".

    B3 explicitly permits "the narrow honest version ... and record scope", and
    the shipped check states its own scope ("a budget mutation that branch does
    not skip"). So a failure here is a SCOPE REPORT for the lead, not a matrix
    verdict — but it is worth reporting because the error direction is a FALSE
    POSITIVE: it flags a game that provably never charges for a refusal, and the
    boolean-flag spelling is ordinary Python that the four-game corpus simply
    does not happen to contain.
    """
    worker, spec_path, cap = _variant(variants, slug)
    found, results, diagnostics = _honest_verdict(
        worker, cap, spec_path=spec_path, mode=MODE_FAIL
    )
    assert found is not None, f"no verdict came back.\n{_dump(results, diagnostics)}"
    assert found.status != "fail", (
        f"the refusal is free — the charge is gated by {guard}, and a refused action leaves "
        "that guard false — so this game signals freely and never charges, the LEGAL half of "
        "§6:158. A fail here says the charge leg reads REACHABILITY rather than the guard, "
        f"and rejects a legal game.\n{_dump([found])}"
    )


def test_pin4c_generated_only(tmp_path, variants):
    """The SAME BYTES staged as an official's variant dir are never a fail."""
    worker, _spec, cap = _variant(variants, "both")
    source = (worker / "game.py").read_text(encoding="utf-8")
    variant = _official(tmp_path, "w3b3off", source)
    found, results, diagnostics = _honest_verdict(variant, cap, mode=MODE_FAIL)
    if found is None:
        return  # no row for an official at all is the strongest form of "never judges them"
    assert found.status != "fail", (
        f"the officials' battery must be untouched (the W2-B pattern: an official source is "
        f"`premise-not-met` by construction). Got {found.status!r} on the same bytes that "
        f"fail as a generated worker.\n{_dump(results, diagnostics)}"
    )


def test_pin4d_the_officials_static_battery_is_unchanged(variants):
    """REGRESSION GUARD: the five frozen static ids, in order."""
    worker, _spec, cap = _variant(variants, "both")
    ids = tuple(result.check_id for result in run_static_checks(worker, cap))
    assert ids == HEAD_STATIC_IDS, (
        f"`run_static_checks` returned {list(ids)}; the B2-calibrated battery counts "
        f"{list(HEAD_STATIC_IDS)}. A generated-only check belongs OUTSIDE that list."
    )


@pytest.mark.parametrize(("name", "slot_dir"), REFUSAL_FIRES, ids=[n for n, _ in REFUSAL_FIRES])
def test_pin4e_the_real_exhibits_fire(tmp_path, name: str, slot_dir: Path):
    """'pump-phase/convoy fire refusal-honest' — replayed on tmp copies."""
    worker, spec_path, cap = _replay(tmp_path, slot_dir, name)
    found, results, diagnostics = _honest_verdict(
        worker, cap, spec_path=spec_path, mode=MODE_FAIL
    )
    assert found is not None, (
        f"no `{REFUSAL_HONEST_CHECK}` verdict for {name}.\n{_dump(results, diagnostics)}"
    )
    assert found.status == "fail", (
        f"{name} is one of the contract's two named exhibits and must fire; got "
        f"{found.status!r}.\n{_dump([found])}"
    )


@pytest.mark.parametrize(
    ("name", "slot_dir"), REFUSAL_SILENT, ids=[n for n, _ in REFUSAL_SILENT]
)
def test_pin4f_the_clean_games_stay_silent(tmp_path, name: str, slot_dir: Path):
    """Measured clean before a fixture was written: conduit gates its budget
    behind the `changed` boolean the refusal returns False into, and pump-flow's
    `self.charge -= 1` lives only in the success branch. Neither may fire."""
    worker, spec_path, cap = _replay(tmp_path, slot_dir, name)
    found, _results, _diagnostics = _honest_verdict(
        worker, cap, spec_path=spec_path, mode=MODE_FAIL
    )
    if found is None:
        return
    assert found.status != "fail", (
        f"{name} paints a refusal and never charges for it, which is the LEGAL half of "
        f"§6:158. A fail here is a false positive.\n{_dump([found])}"
    )


# --------------------------------------------------------------------------- #
# PIN 5 — `refusal-persistence` (s3_visual OR s3_gate — both are searched)
# --------------------------------------------------------------------------- #


def _persistence_verdict(worker, cap, *, spec_path=None, cfg=None, mode=None):
    pool = _static_pool(worker, cap, spec_path, cfg, mode)
    results: list[CheckResult] = []
    diagnostics: list[str] = []
    if _S3_VISUAL_IMPORT_ERROR is not None:
        diagnostics.append(_S3_VISUAL_IMPORT_ERROR)
    for module in (s3_visual, s3_gate, s3_static):
        if module is None:
            continue
        produced, notes = _call_all(module, PERSISTENCE_CHECK_STEMS, pool)
        results.extend(produced)
        diagnostics.extend(f"{getattr(module, '__name__', module)}: {n}" for n in notes)
    return _with_id(results, PERSISTENCE_CHECK_STEMS), results, diagnostics


def test_pin5a_trace_absent_is_not_checked(tmp_path, variants):
    """'trace absent = not-checked' — never a finding, never a crash."""
    source_worker, _spec, cap = _variant(variants, "free")
    worker, spec_path = _slot(tmp_path, "free")
    assert not trace_path(worker).is_file(), "fixture wall: the fresh slot has no trace"
    assert trace_path(source_worker).is_file(), (
        "fixture wall: `capture_worker(..., trace=True)` wrote no trace beside the worker — "
        "A1's armed path is the one PIN 5b/5c read"
    )
    found, results, diagnostics = _persistence_verdict(
        worker, cap, spec_path=spec_path, mode=MODE_FAIL
    )
    if found is None:
        return  # no row without a trace is the cleanest reading of "not-checked"
    assert found.status != "fail", (
        f"with no trace beside the worker the check has no premise and must not be a finding; "
        f"got {found.status!r}.\n{_dump(results, diagnostics)}"
    )


def test_pin5b_a_transient_signal_is_a_finding(variants):
    """A refusal drawn inside an action and gone by that action's settled board.

    WHICH "SETTLED FRAME", resolved. The trace records ONE settled board per
    step (`frames.TraceRecorder.step` keeps `frame[-1]`), so a signal a player
    is left looking at for a whole step IS in a settled frame — and the `free`
    variant, whose flash lives for exactly one step before the next action
    clears it, is correctly NOT a finding. The defect this check is for is a
    signal that never reaches ANY settled board: drawn in an animation frame and
    swallowed before the action settles. That is what this fixture does — the
    refusal takes two engine passes, paints on the first and settles clean on
    the second, so `C_REFUSE` is in frame[0] and in no `frame[-1]` anywhere.
    """
    worker, spec_path, cap = _variant(variants, "transient")
    assert trace_path(worker).is_file(), "fixture wall: no trace beside the worker"
    header, records = read_trace(trace_path(worker))
    multi = [record["t"] for record in records if int(record.get("n_anim", 0)) > 1]
    assert multi, (
        "fixture wall: no traced step rendered more than one frame, so this fixture no "
        f"longer shows an intra-step transient (header {header!r})"
    )
    for label, grids in (
        ("the trace's settled boards", resolve_trace_frames(records)),
        ("the sidecar", [list(record.grid) for record in cap.records]),
    ):
        carried = [
            index
            for index, rows in enumerate(grids)
            if rows is not None and _rows_have_refuse(rows)
        ]
        assert not carried, (
            f"fixture wall: the refusal colour survived into {label} at {carried}, so this "
            "fixture no longer shows a signal that reaches no settled frame"
        )
    found, results, diagnostics = _persistence_verdict(
        worker, cap, spec_path=spec_path, mode=MODE_FAIL
    )
    assert found is not None, (
        "B3 adds a `refusal-persistence` check reading A1's trace. No verdict carrying that "
        f"id came back from s3_visual, s3_gate or s3_static.\n{_dump(results, diagnostics)}"
    )
    assert found.status == "fail", (
        "a refusal event whose signal appears in NO settled frame, while the spec promises "
        f"persistence (`knobs.refusal: visible`, no `refusal_transient`), is a finding; got "
        f"{found.status!r}.\n{_dump([found])}"
    )


def test_pin5c_a_persistent_signal_is_no_finding(variants):
    """`persistent` never takes the signal back down, so it survives."""
    worker, spec_path, cap = _variant(variants, "persistent")
    settled = [record for record in cap.records if _grid_has(record.grid, C_REFUSE)]
    assert settled, (
        "fixture wall: the persistent refusal colour reached NO settled frame "
        f"({[r.label for r in cap.records]}), so this fixture no longer shows persistence"
    )
    found, results, diagnostics = _persistence_verdict(
        worker, cap, spec_path=spec_path, mode=MODE_FAIL
    )
    if found is None:
        pytest.fail(f"no `refusal-persistence` verdict came back.\n{_dump(results, diagnostics)}")
    assert found.status != "fail", (
        f"the refusal signal survives into a settled frame, so the promise is kept; got "
        f"{found.status!r}.\n{_dump([found])}"
    )


def test_pin5d_the_persistence_mode_knob_defaults_to_record(variants):
    path = _knob_path(PERSISTENCE_CHECK_STEMS, "the refusal-persistence check")
    hits = dict(_knob_hits(PERSISTENCE_CHECK_STEMS))
    assert hits.get(path) == MODE_RECORD, (
        f"B3: 'Mode knob default record'. `{'.'.join(path)}` is {hits.get(path)!r} in "
        f"{TEMPLATE}."
    )
    worker, spec_path, cap = _variant(variants, "free")
    off, _results, diagnostics = _persistence_verdict(
        worker, cap, spec_path=spec_path, mode=MODE_OFF
    )
    assert off is None, (
        f"`refusal-persistence` in {MODE_OFF!r} must add no row at all, got {off!r}\n"
        f"{diagnostics}"
    )
    default, results, notes = _persistence_verdict(worker, cap, spec_path=spec_path, mode=None)
    assert default is not None, (
        f"the default mode must be `record`, not `off`.\n{_dump(results, notes)}"
    )
    assert default.status != "fail", (
        f"`record` reports and changes no verdict; got {default.status!r}"
    )
