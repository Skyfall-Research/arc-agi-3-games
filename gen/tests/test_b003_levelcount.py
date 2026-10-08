"""Blind pins for contract C-4b — level-count enforcement, both ends.

Run: .venv/bin/python -m pytest gen/tests/test_b003_levelcount.py -v

Written from the frozen C-4b contract ALONE (blind test writer).  No in-progress
C-4b diff of `gen/s3_static.py`, `gen/s2_implement.py` or `gen/orchestrator.py`
was read: every PRE-EXISTING surface those three modules offer was taken from
`git show HEAD:<path>` so that nothing here pins the landed-but-unrelated work
that also sits in the working tree.  What this file is allowed to know, and
does: `s3_static.CheckResult` / `_result` / `STATUSES` / `_check_sys_click` /
`_parse_game`; `s2_implement._run_static_gate`, `green_loop`, `STATIC_GATE_EXIT`
and `SPEC_YAML_NAME`; `frames.FrameCapture`, `capture_from_json` and
`capture_worker_isolated`; `s3_gate.structural_acceptance`, `CHECK_LEVELS`,
`GATE_SUFFIX` and `ACCEPTANCE_NAME`; `orchestrator.SlotContext`,
`default_runners`, `NOTE_ARTIFACTS` and `_check_artifacts`; the sibling blind
suites `test_b003_patchbaseline.py` (file shape, runner-source pins) and
`test_b002_onego.py` (the synthetic green-loop gate worker, whose fixture this
one extends to N levels); and the shipped corpus under `out/`.  These pins
therefore describe the CONTRACT, not the implementation, and are expected to
fail until C-4b lands.

WHY THIS FILE EXISTS (the measured failure, stated from the contract)

b003r2 slot 1 reached `played` having implemented 3 of the 7 levels its spec
declares.  The gate's level floor reads S4's baseline count, S4 runs AFTER the
gate, and nothing re-checks — so the floor recorded `premise-not-met` and the
mismatch rode all the way through.  C-4b answers it at two ends: catch the
mismatch at BIRTH, in the green loop that made it (one prompt to fix), and
re-answer the floor once S4's numbers exist (evidence for review).  Both ends
are pinned here, and the second is V1-RECORDS: it must change no routing.

THE FOUR PINS, in the contract's order

1. `s3_static._check_level_count(cap, spec_path) -> CheckResult`, id
   `static.level-count-vs-spec`: the contract's four-row matrix, built from the
   real b003r2 artifacts, with the declared counts read off the real spec.yaml
   at test time.  A mismatch fails and the note names BOTH numbers and the spec
   path; a premise that is absent (no/ unreadable/ malformed spec, a capture
   that is not a winning solver capture) is `premise-not-met`, NEVER a fail.
2. `s2_implement._run_static_gate` as a multi-check loop: level-only, sys-click
   only, both, neither, and the spec-less shape the one-go fixtures have.
3. `green_loop`'s new keyword-only `spec_path`, default None, and the
   orchestrator s2 runner passing `spec_dir / SPEC_YAML_NAME` (source pin).
4. The post-S4 floor in the `s4_baselines` runner: the rewritten acceptance
   report, the note artifacts, the NOTE_ARTIFACTS membership, and — the point
   of "V1 RECORDS" — a stage result that is unchanged whatever the rows say.

AMBIGUITIES RESOLVED (each is quoted in the failure message that depends on it)

  a. The contract names `_check_level_count(cap, spec_path)` and NOTHING else:
     no worker dir, no `_Source`.  That is read as load-bearing rather than
     shorthand, and `test_pin1_signature_cannot_ast_count` pins it on its own
     line — a check that cannot see the source cannot AST-count levels, which
     is the contract's one explicit prohibition ("NEVER AST-count levels
     (seed-derived comprehensions)").  Every synthetic worker below builds its
     levels with exactly such a comprehension, so an AST counter would also be
     caught behaviorally.
  b. `leg` is pinned to `"static"`, the value every other check in
     `gen/s3_static.py` passes; the contract does not say so out loud.  One
     line to move if the lead adjudicates otherwise.
  c. "Mismatch ⇒ fail" is read symmetrically: implemented > declared fails too
     (`test_pin1_over_implementation_is_also_a_mismatch`).  The MEASURED defect
     was under-implementation, but a game that quietly grew levels its spec
     never declared is the same broken invariant, and the contract's word is
     "mismatch".
  d. "malformed" is read to include `game.levels` that is not a list — an int,
     a string or a mapping.  A mapping is the sharp one, because `len()`
     succeeds on it: a reader that only guards `KeyError` would silently
     declare 0 levels and FAIL a healthy game, which is exactly what
     "premise-not-met, NEVER fail" forbids.
  e. `_run_static_gate`'s new parameter is called by KEYWORD when the landed
     signature has one named `spec_path`, and positionally otherwise; only
     `green_loop`'s spelling is frozen by the contract ("green_loop gains
     keyword-only spec_path"), so the gate's is discovered, not assumed.
  f. Which artifact key carries the MISSING-SIDECAR skip note is not frozen —
     §(b) names `level_floor_note` and `post_s4_acceptance_error` but leaves
     the skip's spelling open.  So the skip is pinned on behavior (a note
     rides, the report on disk is byte-unchanged, nothing crashes, routing is
     untouched), not on a key name.
  g. `"post_s4_acceptance"` is pinned as a PATH artifact and explicitly NOT a
     member of `NOTE_ARTIFACTS`: §(b) spells it `<path>`, and the exemption
     list's own comment says everything else "is still a path that must
     exist".  The test pin's "and the two note keys in NOTE_ARTIFACTS" is read
     as naming the two NOTES.  Pinned on its own line.
  h. The contract's own verification (full suite, venv ruff, the birth-check
     and post-S4 matrices run by hand) is the implementer's and is NOT
     restated here.  `test_b002_onego` is re-run as the contract asks, but by
     the suite, not by this file.

This file writes only inside `tmp_path`.  The canon, `out/`, the configs and
every other source file are read-only here; the shipped b003r2 slots are
COPIED before anything touches them.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from gen import frames, orchestrator, s2_implement, s3_gate, s3_static, s4_baselines
from gen.orchestrator import SlotContext, default_runners
from gen.worker import instantiate_worker

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_PY = REPO_ROOT / "gen" / "orchestrator.py"
S2_IMPLEMENT_PY = REPO_ROOT / "gen" / "s2_implement.py"

# The two shipped b003r2 slots the contract's birth-check matrix names. Read
# only; every test works on a tmp copy of the handful of files it touches.
B003R2 = REPO_ROOT / "out" / "corpus" / "b003r2-simplicity"
SLOT_MISMATCH = B003R2 / "mosaic-marble-bounce-to-match"   # 3 implemented, 7 declared
SLOT_MATCH = B003R2 / "conduit-watch"                      # 8 implemented, 8 declared

# Contract wording, not code names.
CHECK_ID = "static.level-count-vs-spec"
CHECK_LEG = "static"                       # ambiguity b
PREMISE = "premise-not-met"
FAIL, PASS = "fail", "pass"
ACCEPTANCE_ARTIFACT = "post_s4_acceptance"
LEVEL_NOTE_ARTIFACT = "level_floor_note"
ERROR_NOTE_ARTIFACT = "post_s4_acceptance_error"
NOTE_KEYS = (LEVEL_NOTE_ARTIFACT, ERROR_NOTE_ARTIFACT)

RUNNER_S2 = "s2_implement"
RUNNER_S4 = "s4_baselines"
STAGE_S4 = "s4_baselines"
BATCH_ID = "b003-c4b-tests"
SYNTHETIC_PROMPT = "SYNTHETIC SEED PROMPT — no live-run content"

# `gen/frames.py`'s capture schema, frozen here because C-4b says the birth
# check must NEVER touch it (the implemented count is `cap.levels_completed`,
# which the schema already carries).
CAPTURE_KEYS = (
    "game_id",
    "source",
    "records",
    "click_cells",
    "available_action_ids",
    "solver_actions",
    "levels_completed",
    "win",
)

_ABSENT = object()


# --------------------------------------------------------------------------
# the surface under test, fetched rather than assumed
# --------------------------------------------------------------------------


def _level_check():
    """`_check_level_count` — the contract's own spelling for the birth check."""
    fn = getattr(s3_static, "_check_level_count", None)
    assert callable(fn), (
        "gen.s3_static has no `_check_level_count(cap, spec_path) -> CheckResult`. C-4b (a) "
        f"names it, beside `_check_sys_click`, with check id {CHECK_ID!r}"
    )
    return fn


def _level_verdict(cap, spec_path):
    return _level_check()(cap, spec_path)


def _static_gate(worker_dir: Path, spec_path: object = _ABSENT):
    """`_run_static_gate`, with the contract's new argument when one is asked for.

    Ambiguity e: only `green_loop`'s spelling is frozen, so the gate's second
    parameter is discovered — by name when it has one, positionally otherwise.
    """
    fn = getattr(s2_implement, "_run_static_gate", None)
    assert callable(fn), "gen.s2_implement has no `_run_static_gate` — C-4b (a) rebuilds it"
    if spec_path is _ABSENT:
        return fn(worker_dir)
    params = inspect.signature(fn).parameters
    assert len(params) >= 2, (
        f"`_run_static_gate{inspect.signature(fn)}` takes no spec path. C-4b (a): the gate "
        "runs `_check_level_count(cap, spec_path)` beside `_check_sys_click`, and the path "
        "is threaded in from green_loop"
    )
    if "spec_path" in params:
        return fn(worker_dir, spec_path=spec_path)
    return fn(worker_dir, spec_path)


def _sys_click_verdict(worker_dir: Path):
    """The gate's OTHER check, recomputed from the same two public parts."""
    cap = frames.capture_worker_isolated(worker_dir)
    return s3_static._check_sys_click(s3_static._parse_game(worker_dir), cap, worker_dir)


def _names_number(text: str, value: int) -> bool:
    """Is `value` named in `text` as a number in its own right?

    Digit-boundary rather than `str(value) in text`, so "3" does not match the
    "3" inside "203" or "0.3".
    """
    return re.search(rf"(?<![\d.]){value}(?![\d.])", text) is not None


# --------------------------------------------------------------------------
# the shipped b003r2 artifacts (read-only) and tmp copies of them
# --------------------------------------------------------------------------


def _declared(slot: Path) -> int:
    """`len(spec["game"]["levels"])` — read off the real spec.yaml at test time."""
    spec = yaml.safe_load((slot / "spec.yaml").read_text(encoding="utf-8"))
    return len(spec["game"]["levels"])


def _capture(slot: Path):
    """The S2b frames sidecar, rehydrated — no driver, no engine, no subprocess."""
    payload = json.loads((slot / "worker.frames.json").read_text(encoding="utf-8"))
    return frames.capture_from_json(payload)


def _copy_slot_inputs(slot: Path, dest: Path) -> Path:
    """A tmp slot carrying only what the birth check reads: the spec and the
    frames sidecar (plus the worker's source, so the copy is a real slot)."""
    assert slot.is_dir(), (
        f"fixture wall: {slot} is gone — C-4b's birth-check matrix is defined over the two "
        "shipped b003r2 slots"
    )
    dest.mkdir(parents=True)
    shutil.copy2(slot / "spec.yaml", dest / "spec.yaml")
    shutil.copy2(slot / "worker.frames.json", dest / "worker.frames.json")
    shutil.copytree(
        slot / "worker", dest / "worker", ignore=shutil.ignore_patterns("__pycache__")
    )
    return dest


@pytest.fixture
def mismatch_slot(tmp_path: Path) -> SimpleNamespace:
    """b003r2 slot 1: `played` with 3 of its 7 declared levels implemented."""
    dest = _copy_slot_inputs(SLOT_MISMATCH, tmp_path / "slot-mismatch")
    cap, declared = _capture(dest), _declared(dest)
    assert (cap.source, cap.win, cap.levels_completed, declared) == ("solver", True, 3, 7), (
        "fixture wall: the shipped slot is no longer the measured defect — C-4b's Why is "
        f"'3 of its 7 declared levels' and this copy reads source={cap.source!r} "
        f"win={cap.win!r} completed={cap.levels_completed} declared={declared}"
    )
    return SimpleNamespace(dir=dest, cap=cap, declared=declared, spec=dest / "spec.yaml")


@pytest.fixture
def match_slot(tmp_path: Path) -> SimpleNamespace:
    """conduit-watch: 8 implemented, 8 declared — the healthy row."""
    dest = _copy_slot_inputs(SLOT_MATCH, tmp_path / "slot-match")
    cap, declared = _capture(dest), _declared(dest)
    assert (cap.source, cap.win, cap.levels_completed, declared) == ("solver", True, 8, 8), (
        "fixture wall: conduit-watch is C-4b's 8-vs-8 pass row and this copy reads "
        f"source={cap.source!r} win={cap.win!r} completed={cap.levels_completed} "
        f"declared={declared}"
    )
    return SimpleNamespace(dir=dest, cap=cap, declared=declared, spec=dest / "spec.yaml")


# --------------------------------------------------------------------------
# PIN 1 — `_check_level_count`, the contract's four-row matrix
# --------------------------------------------------------------------------


def test_pin1_mismatch_is_a_fail_naming_both_numbers(mismatch_slot: SimpleNamespace) -> None:
    """Row 1: slot-1's real capture + its real spec ⇒ fail naming 3 and 7.

    This is the defect the whole contract exists for, measured on the artifacts
    it actually happened to.
    """
    result = _level_verdict(mismatch_slot.cap, mismatch_slot.spec)

    assert isinstance(result, s3_static.CheckResult), (
        f"_check_level_count returned {type(result).__name__}, not a CheckResult — it is a "
        "check beside `_check_sys_click` and the gate joins their notes"
    )
    assert result.check_id == CHECK_ID, (
        f"check id is {result.check_id!r}; C-4b (a) freezes {CHECK_ID!r} — the id is what the "
        "red tail carries into the next fix prompt"
    )
    assert result.status == FAIL, (
        f"3 implemented vs 7 declared read {result.status!r}, not {FAIL!r}. C-4b (a): "
        f"'Mismatch ⇒ fail'. Note was: {result.note!r}"
    )
    assert _names_number(result.note, 3) and _names_number(result.note, 7), (
        "the fail note must name BOTH numbers (C-4b test pin 1) — the session reading it has "
        f"to know how many levels it owes and how many it built. Note: {result.note!r}"
    )


def test_pin1_fail_note_names_the_spec_path(mismatch_slot: SimpleNamespace) -> None:
    """C-4b (a): "note names both numbers and the spec path"."""
    result = _level_verdict(mismatch_slot.cap, mismatch_slot.spec)
    assert str(mismatch_slot.spec) in result.note, (
        f"the fail note does not name {mismatch_slot.spec} — a mismatch is answered by "
        "reading the spec, so the note says which file declared the number. Note: "
        f"{result.note!r}"
    )


def test_pin1_match_is_a_pass(match_slot: SimpleNamespace) -> None:
    """Row 2: conduit-watch, 8 vs 8 ⇒ pass. A healthy game must ride through."""
    result = _level_verdict(match_slot.cap, match_slot.spec)

    assert result.check_id == CHECK_ID
    assert result.status == PASS, (
        f"8 implemented vs 8 declared read {result.status!r}, not {PASS!r} — this slot is "
        f"the contract's own pass row. Note: {result.note!r}"
    )


def test_pin1_no_spec_is_premise_not_met(match_slot: SimpleNamespace, tmp_path: Path) -> None:
    """Row 3: no spec beside the worker ⇒ `premise-not-met`, never a fail.

    "a worker without a spec beside it — the CLI case and the onego fixtures —
    is not a defect this check can judge" (C-4b (a)).
    """
    for spec_path in (None, tmp_path / "nowhere" / "spec.yaml"):
        result = _level_verdict(match_slot.cap, spec_path)
        assert result.status == PREMISE, (
            f"spec_path={spec_path!r} read {result.status!r}; C-4b (a) says None/missing is "
            f"{PREMISE!r} and NEVER a fail — the module CLI passes None on every run"
        )
        assert result.check_id == CHECK_ID


@pytest.mark.parametrize(
    "name, payload",
    [
        ("not-yaml", "game: [unclosed\n  - {{{\n"),
        ("root-is-a-list", "- a\n- b\n"),
        ("root-is-a-scalar", "just a string\n"),
        ("empty-file", ""),
        ("no-game-block", "meta:\n  id: x\n"),
        ("game-is-not-a-mapping", "game: 7\n"),
        ("no-levels-key", "game:\n  terms: [move.grid]\n"),
        ("levels-is-null", "game:\n  levels:\n"),
        ("levels-is-an-int", "game:\n  levels: 7\n"),
        ("levels-is-a-string", "game:\n  levels: seven\n"),
        ("levels-is-a-mapping", "game:\n  levels: {a: 1, b: 2}\n"),
    ],
)
def test_pin1_malformed_spec_is_premise_not_met(
    match_slot: SimpleNamespace, tmp_path: Path, name: str, payload: str
) -> None:
    """Row 3, continued: "spec_path None / missing / unreadable / malformed ⇒
    premise-not-met, NEVER fail" (C-4b (a)).

    Ambiguity d: `levels-is-a-mapping` is the sharp one — `len()` SUCCEEDS on a
    mapping, so a reader that only guards `KeyError` silently declares 2 levels
    (or 0) and fails a healthy game for an artifact bug.
    """
    spec_path = tmp_path / f"spec-{name}.yaml"
    spec_path.write_text(payload, encoding="utf-8")

    result = _level_verdict(match_slot.cap, spec_path)
    assert result.status == PREMISE, (
        f"a {name} spec read {result.status!r}. C-4b (a): an unreadable or malformed spec is "
        f"{PREMISE!r} and NEVER a fail — a broken artifact is not a defect of the game. "
        f"Note: {result.note!r}"
    )


def test_pin1_unreadable_spec_is_premise_not_met(
    match_slot: SimpleNamespace, tmp_path: Path
) -> None:
    """"unreadable" taken literally: a path that is a DIRECTORY raises on read.

    Its own test because it is the one row that exercises the check's I/O
    guard rather than its parse guard.
    """
    spec_path = tmp_path / "spec.yaml"
    spec_path.mkdir()

    result = _level_verdict(match_slot.cap, spec_path)
    assert result.status == PREMISE, (
        f"an unreadable spec path read {result.status!r}; C-4b (a) says {PREMISE!r}, never a "
        "crash and never a fail"
    )


def test_pin1_a_capture_that_did_not_win_is_premise_not_met(
    match_slot: SimpleNamespace,
) -> None:
    """Row 4: `win=False` ⇒ premise-not-met.

    "Implemented count = `cap.levels_completed`, valid ONLY when `cap.win` and
    `cap.source == "solver"`" — the gate runs after `make validate`, whose
    scaffold test asserts the solver won with every level credited, so
    completed == total THERE and nowhere else.
    """
    lost = dataclasses.replace(match_slot.cap, win=False)
    result = _level_verdict(lost, match_slot.spec)

    assert result.status == PREMISE, (
        f"a capture with win=False read {result.status!r}; without a win "
        "`levels_completed` is a progress count, not an implemented count, so the premise "
        f"of the comparison is not met. Note: {result.note!r}"
    )


def test_pin1_a_non_solver_capture_is_premise_not_met(match_slot: SimpleNamespace) -> None:
    """The other half of row 4: `source != "solver"` (a probe capture)."""
    probed = dataclasses.replace(match_slot.cap, source="probe")
    result = _level_verdict(probed, match_slot.spec)

    assert result.status == PREMISE, (
        f"a capture with source='probe' read {result.status!r}; C-4b (a) admits the count "
        "ONLY from a winning SOLVER capture"
    )


def test_pin1_a_lost_capture_is_premise_not_met_even_when_the_numbers_match(
    match_slot: SimpleNamespace,
) -> None:
    """The premise is checked BEFORE the numbers: 8 completed, 8 declared, but
    no win ⇒ still `premise-not-met`, not an accidental pass.

    An honest non-answer and a pass route identically today, so this pin is
    what keeps the distinction real for the review that reads the report.
    """
    lost = dataclasses.replace(match_slot.cap, win=False)
    assert lost.levels_completed == match_slot.declared, "fixture wall: 8 vs 8"
    assert _level_verdict(lost, match_slot.spec).status == PREMISE


def test_pin1_over_implementation_is_also_a_mismatch(match_slot: SimpleNamespace) -> None:
    """Ambiguity c: implemented > declared is a mismatch too, and fails.

    The measured defect was under-implementation; the contract's word is
    "mismatch", and a game that grew a level its spec never declared has the
    same broken invariant. One line to move if the lead adjudicates otherwise.
    """
    grown = dataclasses.replace(match_slot.cap, levels_completed=match_slot.declared + 1)
    result = _level_verdict(grown, match_slot.spec)

    assert result.status == FAIL, (
        f"{match_slot.declared + 1} implemented vs {match_slot.declared} declared read "
        f"{result.status!r}; C-4b (a) says 'Mismatch ⇒ fail' and does not make the "
        "comparison one-sided"
    )
    assert _names_number(result.note, match_slot.declared + 1)
    assert _names_number(result.note, match_slot.declared)


def test_pin1_result_is_a_well_formed_check_row(mismatch_slot: SimpleNamespace) -> None:
    """Every status the check can return is a legal one, on the `static` leg
    (ambiguity b), with a non-empty note — the S2b report renders these rows."""
    results = [
        _level_verdict(mismatch_slot.cap, mismatch_slot.spec),
        _level_verdict(mismatch_slot.cap, None),
    ]
    for result in results:
        assert result.status in s3_static.STATUSES, f"{result.status!r} not in STATUSES"
        assert result.leg == CHECK_LEG, (
            f"leg is {result.leg!r}; every check in gen/s3_static.py passes {CHECK_LEG!r} "
            "(ambiguity b — the contract does not say so out loud)"
        )
        assert result.note.strip(), "a check row with no note explains nothing to the session"
        assert isinstance(result.evidence, tuple)


def test_pin1_signature_cannot_ast_count(mismatch_slot: SimpleNamespace) -> None:
    """Ambiguity a + the contract's one prohibition: "NEVER AST-count levels
    (seed-derived comprehensions)".

    `_check_level_count(cap, spec_path)` is given the capture and the spec and
    NOTHING else — no worker dir, no parsed source — so counting levels off the
    AST is not reachable from inside it. Pinned structurally here and
    behaviorally by every synthetic worker below, each of which builds its
    levels with exactly such a comprehension.
    """
    params = inspect.signature(_level_check()).parameters
    required = [
        name
        for name, param in params.items()
        if param.default is inspect.Parameter.empty
        and param.kind
        not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    assert len(required) == 2, (
        f"_check_level_count takes required parameters {required}; C-4b (a) gives it exactly "
        "(cap, spec_path) — a check that cannot see the worker's source cannot AST-count "
        "levels, which the contract forbids outright"
    )
    leaked = [name for name in params if "worker" in name or "source" in name]
    assert not leaked, (
        f"_check_level_count takes {leaked} — the contract hands it the capture and the spec "
        "only; the implemented count is `cap.levels_completed`"
    )


def test_pin1_the_capture_schema_is_untouched() -> None:
    """"NEVER touch `frames._CAPTURE_KEYS`" (C-4b (a)).

    The implemented count already rides the capture, so the fix needs no schema
    change — and a schema change would invalidate every frames sidecar on disk,
    including the ones the post-S4 half of this contract rehydrates.
    """
    assert tuple(frames._CAPTURE_KEYS) == CAPTURE_KEYS, (
        "gen/frames.py's capture schema moved. C-4b (a) forbids it: `levels_completed` is "
        f"already in the payload. Now: {tuple(frames._CAPTURE_KEYS)}"
    )


# --------------------------------------------------------------------------
# synthetic workers for the multi-check gate (pin 2)
# --------------------------------------------------------------------------

# Extended from `gen/tests/test_b002_onego.py`'s gate fixture: one 8x8 level
# repeated N times, one declared action (ACTION6 = click). `switch` is tagged
# `sys_click` and the click handler branches on it BY NAME. The untruthful
# build adds `inert_panel`: also tagged, so the engine advertises a click on it
# and every RL consumer reads that list — but no code path handles it. That is
# the `static.sys-click-truthful` failure the birth gate already catches; the
# LEVEL count is the second, new axis, and the two are varied independently
# here because C-4b turns the gate into a multi-check loop.
#
# NOTE the level list is a COMPREHENSION (`for _ in range(N)`), deliberately:
# it is the seed-derived shape the contract says an AST counter gets wrong.
_GAME = '''\
"""SYNTHETIC level-count gate fixture — authored in test_b003_levelcount.py."""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

BACKDROP, SWITCH, PANEL = 4, 11, 6
LEVELS = {levels}


def _level() -> Level:
    sprites = [
        Sprite([[BACKDROP] * 8 for _ in range(8)], name="backdrop", x=0, y=0,
               collidable=False),
        Sprite([[SWITCH, SWITCH], [SWITCH, SWITCH]], name="switch", x=1, y=3,
               layer=1, tags=["sys_click"]),
    ]
{panel}
    return Level(sprites=sprites)


class LevelCountFixtureGame(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="{game_id}",
            levels=[_level() for _ in range(LEVELS)],
            camera=Camera(width=8, height=8),
            available_actions=[6],
        )

    def step(self) -> None:
        if self.action.id is GameAction.ACTION6:
            cell = self.camera.display_to_grid(
                int(self.action.data.get("x", 0)), int(self.action.data.get("y", 0))
            )
            if cell is not None:
                hit = self.current_level.get_sprite_at(cell[0], cell[1])
                if hit is not None and hit.name == "switch":
                    self.complete_action()
                    self.next_level()
                    return
        self.complete_action()
'''

_PANEL = """    sprites.append(
        Sprite([[PANEL, PANEL], [PANEL, PANEL]], name="inert_panel", x=5, y=3,
               layer=1, tags=["sys_click"])
    )"""

_SOLVER = '''\
"""SYNTHETIC deterministic solver — one click on the switch clears one level."""

from arcengine import ActionInput, GameAction

SWITCH_DISPLAY_XY = (12, 28)  # centre of the 2x2 switch at grid (1, 3), scale 8
LEVELS = {levels}


class Solver:
    def reset(self) -> None:
        self._clicks = 0

    def next_action(self, frame):
        if self._clicks >= LEVELS:
            return None
        self._clicks += 1
        x, y = SWITCH_DISPLAY_XY
        return ActionInput(id=GameAction.ACTION6, data={{"x": x, "y": y}})
'''


def _build_worker(dest: Path, *, levels: int, truthful: bool) -> Path:
    """An instantiated worker whose solver wins `levels` levels."""
    instantiate_worker(dest)
    dest = Path(dest).resolve()
    (dest / "game.py").write_text(
        _GAME.format(
            levels=levels,
            panel="" if truthful else _PANEL,
            game_id=f"levelcount-{'truthful' if truthful else 'untruthful'}-{levels}",
        ),
        encoding="utf-8",
    )
    (dest / "solver.py").write_text(_SOLVER.format(levels=levels), encoding="utf-8")
    return dest


def _write_spec(path: Path, declared: int) -> Path:
    """A minimal spec.yaml: only `game.levels`, which is all the check reads."""
    path.write_text(
        yaml.safe_dump(
            {"game": {"levels": [{"index": i, "note": "synthetic"} for i in range(declared)]}},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _gate_worker(root: Path, name: str, *, levels: int, truthful: bool) -> SimpleNamespace:
    slot = root / name
    slot.mkdir(parents=True)
    worker = _build_worker(slot / "worker", levels=levels, truthful=truthful)
    return SimpleNamespace(slot=slot, worker=worker, levels=levels, truthful=truthful)


@pytest.fixture(scope="module")
def gate_workers(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """Two workers, built and CAPTURED once: `_run_static_gate` writes nothing.

    Each capture is a fresh interpreter (`capture_worker_isolated`), which is
    what the gate itself uses, so the fixture wall below measures the same
    thing the gate will.
    """
    root = tmp_path_factory.mktemp("gate-workers")
    truthful = _gate_worker(root, "truthful", levels=2, truthful=True)
    untruthful = _gate_worker(root, "untruthful", levels=2, truthful=False)

    for built, expected in ((truthful, PASS), (untruthful, FAIL)):
        verdict = _sys_click_verdict(built.worker)
        assert verdict.status == expected, (
            f"fixture wall: the {'truthful' if built.truthful else 'untruthful'} worker was "
            f"expected to {expected} static.sys-click-truthful, got {verdict.status} — "
            f"{verdict.note}"
        )
        built.sys_click = verdict
        cap = frames.capture_worker_isolated(built.worker)
        assert (cap.source, cap.win, cap.levels_completed) == ("solver", True, built.levels), (
            "fixture wall: the synthetic solver must WIN every level, or the level check's "
            f"premise is not met at all — got source={cap.source!r} win={cap.win!r} "
            f"completed={cap.levels_completed}"
        )
    return SimpleNamespace(truthful=truthful, untruthful=untruthful)


# --------------------------------------------------------------------------
# PIN 2 — `_run_static_gate` as a multi-check loop
# --------------------------------------------------------------------------


def test_pin2_level_failure_alone_reds_the_gate(
    gate_workers: SimpleNamespace, tmp_path: Path
) -> None:
    """A worker that passes sys-click and fails the level count ⇒ (False, msg)
    carrying that check's id and note VERBATIM — the pinned red-tail shape."""
    built = gate_workers.truthful
    spec = _write_spec(tmp_path / "spec.yaml", built.levels + 3)
    expected = _level_verdict(frames.capture_worker_isolated(built.worker), spec)
    assert expected.status == FAIL, f"fixture wall: {expected.status} — {expected.note}"

    ok, message = _static_gate(built.worker, spec)

    assert ok is False, (
        "a green `make validate` with a level-count mismatch is still a RED attempt: C-4b's "
        "whole point is to catch the mismatch in the session that made it"
    )
    assert CHECK_ID in message, f"the gate message does not name {CHECK_ID}: {message!r}"
    assert expected.note in message, (
        "the failing check's note must ride the message VERBATIM — it is the tail the ledger "
        f"records and the next fix prompt quotes. Message: {message!r}"
    )


def test_pin2_sys_click_failure_alone_is_unchanged(
    gate_workers: SimpleNamespace, tmp_path: Path
) -> None:
    """The check that was already there still decides on its own, and the new
    one stays out of the message when it passes."""
    built = gate_workers.untruthful
    spec = _write_spec(tmp_path / "spec.yaml", built.levels)

    ok, message = _static_gate(built.worker, spec)

    assert ok is False
    assert built.sys_click.check_id in message
    assert built.sys_click.note in message, (
        "the sys-click note no longer rides the gate message verbatim — C-4b leaves the "
        f"exit-125 mechanics and the red-tail shape untouched. Message: {message!r}"
    )
    assert CHECK_ID not in message, (
        "the level check PASSED here (implemented == declared) and must contribute nothing "
        f"to the message: only failing checks are joined. Message: {message!r}"
    )


def test_pin2_both_failures_are_both_reported(
    gate_workers: SimpleNamespace, tmp_path: Path
) -> None:
    """"any `fail` ⇒ (False, joined message) with EACH failing check's check_id
    and note verbatim" — a session must not fix one and rediscover the other."""
    built = gate_workers.untruthful
    spec = _write_spec(tmp_path / "spec.yaml", built.levels + 4)
    level = _level_verdict(frames.capture_worker_isolated(built.worker), spec)
    assert level.status == FAIL, f"fixture wall: {level.status} — {level.note}"

    ok, message = _static_gate(built.worker, spec)

    assert ok is False
    missing = [
        piece
        for piece in (built.sys_click.check_id, built.sys_click.note, level.check_id, level.note)
        if piece not in message
    ]
    assert not missing, (
        f"the joined gate message is missing {missing} — C-4b (a) joins EACH failing check's "
        f"check_id and note. Message: {message!r}"
    )


def test_pin2_both_passing_is_true_and_an_empty_message(
    gate_workers: SimpleNamespace, tmp_path: Path
) -> None:
    """Green-with-gate-pass is still the only green, and it says nothing."""
    built = gate_workers.truthful
    spec = _write_spec(tmp_path / "spec.yaml", built.levels)

    assert _static_gate(built.worker, spec) == (True, ""), (
        "a worker that passes both checks must return exactly (True, '') — the gate's "
        "message becomes the attempt tail, and a passing attempt has nothing to say"
    )


def test_pin2_no_spec_leaves_sys_click_alone_deciding(gate_workers: SimpleNamespace) -> None:
    """The one-go fixtures' shape: a worker with no spec beside it.

    "No spec beside the worker ⇒ level check premise-skipped and sys-click
    alone decides" (C-4b test pin 2). This is what keeps the spec-less 1-level
    `test_b002_onego` gate fixtures green, and it is checked BOTH ways so a
    premise skip cannot be mistaken for a pass or for a fail.
    """
    passing = _static_gate(gate_workers.truthful.worker, None)
    assert passing == (True, ""), (
        "a 2-level worker with NO spec must stay green: the level check has no declared "
        f"count to compare against and is premise-skipped. Got {passing!r}"
    )

    ok, message = _static_gate(gate_workers.untruthful.worker, None)
    assert ok is False
    assert gate_workers.untruthful.sys_click.note in message
    assert CHECK_ID not in message, (
        "a premise-skipped check must not appear in the gate message at all: "
        f"'premise-not-met' is an honest non-answer, never a reject. Message: {message!r}"
    )


def test_pin2_the_gate_still_defaults_to_no_spec(gate_workers: SimpleNamespace) -> None:
    """Called the way today's callers call it — one argument — nothing changes.

    The module CLI is exactly this caller (C-4b (a): "the module CLI keeps None
    ⇒ the new check is premise-skipped there").
    """
    assert _static_gate(gate_workers.truthful.worker) == (True, "")
    ok, message = _static_gate(gate_workers.untruthful.worker)
    assert ok is False and CHECK_ID not in message


# --------------------------------------------------------------------------
# PIN 3 — `green_loop(spec_path=…)` and the orchestrator s2 runner
# --------------------------------------------------------------------------


class _Recorder:
    """A session runner that runs no session and records what it was asked."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(self, prompt: str, **_kwargs: object) -> dict:
        self.prompts.append(prompt)
        return {
            "session_id": f"synthetic-{len(self.prompts)}",
            "usd": 0.0,
            "tokens_in": 1,
            "tokens_out": 1,
            "wall_s": 0.0,
            "exit_code": 0,
            "text": "synthetic session",
        }


def _loop_cfg(attempts: int) -> dict:
    return {"implementer": {"max_green_attempts": attempts, "session_token_cap": "400k"}}


def _green_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    """`make validate` GREEN, so only the gate can turn the attempt red."""
    monkeypatch.setattr(s2_implement, "_run_validate", lambda worker_dir: (0, "validate: GREEN"))


def test_pin3_green_loop_takes_a_keyword_only_spec_path_defaulting_none() -> None:
    """C-4b (a): "green_loop gains keyword-only `spec_path: Path | None = None`"."""
    params = inspect.signature(s2_implement.green_loop).parameters
    assert "spec_path" in params, (
        "green_loop has no `spec_path` parameter; C-4b threads the spec path from the "
        f"orchestrator through the loop to the gate. Signature: "
        f"{inspect.signature(s2_implement.green_loop)}"
    )
    param = params["spec_path"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY, (
        f"`spec_path` is {param.kind.description}; the contract says keyword-only, beside "
        "`session_runner`, `model`, `max_attempts` and `on_attempt`"
    )
    assert param.default is None, (
        f"`spec_path` defaults to {param.default!r}, not None — the default IS the CLI case "
        "and the one-go fixtures' case, where the new check is premise-skipped"
    )


def test_pin3_green_loop_threads_the_spec_path_to_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through the real loop: a level mismatch is a red attempt with
    the sentinel exit, and the finding reaches the next prompt."""
    worker = _build_worker(tmp_path / "slot" / "worker", levels=2, truthful=True)
    spec = _write_spec(tmp_path / "slot" / "spec.yaml", 5)
    expected = _level_verdict(frames.capture_worker_isolated(worker), spec)
    assert expected.status == FAIL, f"fixture wall: {expected.status} — {expected.note}"

    _green_validate(monkeypatch)
    runner = _Recorder()
    report = s2_implement.green_loop(
        worker, SYNTHETIC_PROMPT, _loop_cfg(2), session_runner=runner, spec_path=spec
    )

    assert report.green is False, "green-with-gate-pass is the ONLY green"
    first = report.records[0]
    assert first.validate_exit == s2_implement.STATIC_GATE_EXIT, (
        f"the gate's red attempt carries exit {first.validate_exit}, not the sentinel "
        f"{s2_implement.STATIC_GATE_EXIT} — C-4b leaves the exit-125 mechanics untouched"
    )
    assert expected.check_id in first.validate_tail
    assert expected.note in first.validate_tail
    assert len(runner.prompts) == 2 and expected.note in runner.prompts[1], (
        "the level-count finding must reach the NEXT attempt's prompt — one prompt to fix is "
        "the whole reason the check moved to birth time"
    )


def test_pin3_green_loop_without_a_spec_path_is_the_one_go_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same worker, same 2 levels, no `spec_path`: green on attempt one.

    This is the `test_b002_onego` fixtures' shape, and it MUST stay green — the
    contract's own verification says so.
    """
    worker = _build_worker(tmp_path / "slot" / "worker", levels=2, truthful=True)
    _write_spec(tmp_path / "slot" / "spec.yaml", 5)   # on disk, never passed in

    _green_validate(monkeypatch)
    runner = _Recorder()
    report = s2_implement.green_loop(
        worker, SYNTHETIC_PROMPT, _loop_cfg(2), session_runner=runner
    )

    assert report.green is True, (
        "with no spec_path the level check is premise-skipped; a gate that went hunting for "
        "a spec.yaml beside the worker would red this attempt and break every spec-less "
        "fixture in the suite"
    )
    assert report.attempts == 1
    assert runner.prompts == [SYNTHETIC_PROMPT]


# --- the two source-text pins (modules read as TEXT, never executed) --------


def _module_text(path: Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def _function_def(path: Path, name: str) -> ast.FunctionDef:
    """The named `def` in a module, wherever it nests (the runners are closures
    inside `default_runners()`)."""
    text = _module_text(path)
    for node in ast.walk(ast.parse(text, filename=str(path))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"no `def {name}` in {path} — this file pins it by name")


def _calls(func: ast.FunctionDef, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    ]


def test_pin3_the_s2_runner_passes_spec_dir_over_spec_yaml_name() -> None:
    """C-4b (a): "the orchestrator's s2 runner passes `spec_dir / SPEC_YAML_NAME`".

    Read off the AST of the runner's own `green_loop(...)` call, so the pin is
    on what is PASSED — `gen/orchestrator.py` already mentions SPEC_YAML_NAME
    elsewhere in that runner for the spec-hash latch, and a bare text search
    would pass on that alone.
    """
    runner = _function_def(ORCHESTRATOR_PY, RUNNER_S2)
    calls = _calls(runner, "green_loop")
    assert calls, f"the {RUNNER_S2} runner no longer calls green_loop()"

    keywords = {kw.arg: kw.value for call in calls for kw in call.keywords if kw.arg}
    assert "spec_path" in keywords, (
        f"the {RUNNER_S2} runner calls green_loop without `spec_path=`; C-4b (a) threads "
        "`spec_dir / SPEC_YAML_NAME` in from here — the orchestrator is the ONLY caller that "
        "knows where the spec is"
    )
    passed = ast.unparse(keywords["spec_path"])
    assert "SPEC_YAML_NAME" in passed, (
        f"the runner passes spec_path={passed} — the contract spells it "
        "`spec_dir / SPEC_YAML_NAME`, the one constant `gen/s2_implement.py` already defines "
        "for that filename"
    )
    assert "spec_dir" in passed, f"spec_path={passed} is not resolved against the spec dir"


def test_pin3_the_module_cli_keeps_spec_path_none() -> None:
    """C-4b (a): "the module CLI keeps None (⇒ the new check is premise-skipped
    there)" — a worker driven by hand has no slot around it to find a spec in."""
    main = _function_def(S2_IMPLEMENT_PY, "main")
    calls = _calls(main, "green_loop")
    assert calls, "gen/s2_implement.py's `main` no longer calls green_loop()"

    for call in calls:
        passed = {kw.arg for kw in call.keywords if kw.arg}
        assert "spec_path" not in passed, (
            "the module CLI passes spec_path; C-4b keeps it None there, so `--worker` mode "
            "stays exactly as it is and the new check is premise-skipped"
        )


# --------------------------------------------------------------------------
# PIN 4 — the post-S4 floor in the `s4_baselines` runner
# --------------------------------------------------------------------------


def _copy_s4_slot(dest: Path) -> Path:
    """A tmp copy of conduit-watch's slot — worker, frames sidecar, gate dir and
    S4 output. The shipped slot is never written to."""
    assert SLOT_MATCH.is_dir(), f"fixture wall: {SLOT_MATCH} is gone"
    dest.mkdir(parents=True)
    shutil.copy2(SLOT_MATCH / "spec.yaml", dest / "spec.yaml")
    shutil.copy2(SLOT_MATCH / "worker.frames.json", dest / "worker.frames.json")
    for name in ("worker", "worker.gate", "worker.s4"):
        shutil.copytree(
            SLOT_MATCH / name, dest / name, ignore=shutil.ignore_patterns("__pycache__")
        )
    return dest


@pytest.fixture
def s4_slot(tmp_path: Path) -> SimpleNamespace:
    """conduit-watch on tmp, plus the `SlotContext` the runner is handed.

    A REAL `SlotContext` (not a duck) so every field the runner may touch is
    present and typed — the `test_b002_hotfix2` pattern.
    """
    corpus_dir = tmp_path / "corpus" / BATCH_ID
    spec_dir = _copy_s4_slot(corpus_dir / SLOT_MATCH.name)
    ideas_dir = tmp_path / "ideas" / BATCH_ID
    ideas_dir.mkdir(parents=True)

    worker = spec_dir / "worker"
    gate_dir = worker.with_name(worker.name + s3_gate.GATE_SUFFIX)
    ctx = SlotContext(
        cfg={},
        batch_id=BATCH_ID,
        slug=SLOT_MATCH.name,
        index=1,
        state="gated",
        stage=STAGE_S4,
        attempt=1,
        batch_dir=tmp_path / "batch",
        ideas_dir=ideas_dir,
        idea_path=ideas_dir / "idea-001.json",
        corpus_dir=corpus_dir,
        spec_dir=spec_dir,
        respec_count=0,
        verifier_rejects=0,
        green_failures=0,
    )
    return SimpleNamespace(
        spec_dir=spec_dir,
        worker=worker,
        gate_dir=gate_dir,
        acceptance=gate_dir / s3_gate.ACCEPTANCE_NAME,
        s4_dir=worker.with_name(worker.name + s4_baselines.OUT_SUFFIX),
        frames_path=worker.with_name(worker.name + ".frames.json"),
        ctx=ctx,
    )


def _doctor_baselines(s4_slot: SimpleNamespace, count: int) -> list[int]:
    """Cut S4's baseline vector down to `count` entries — the 3-of-7 defect,
    reproduced in the numbers the floor actually reads."""
    path = s4_slot.s4_dir / s4_baselines.METADATA_NAME
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["baseline_actions"] = metadata["baseline_actions"][:count]
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata["baseline_actions"]


def _drive_s4(s4_slot: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Run the real S4 runner with S4 itself stubbed out.

    `run_s4_isolated` is replaced by the slot's OWN shipped `s4-report.json`,
    so the runner sees the fit verdict it really saw — without re-driving a
    solver, and without rewriting the metadata this test doctored.
    """
    report = json.loads((s4_slot.s4_dir / "s4-report.json").read_text(encoding="utf-8"))
    assert report["verdict"] == s4_baselines.VERDICT_FIT, (
        f"fixture wall: the shipped S4 report is {report['verdict']!r}; the post-S4 re-check "
        "rides the FIT branch"
    )
    calls: list[Path] = []

    def _fake(worker_dir, cfg, **_kwargs):
        calls.append(Path(worker_dir))
        return report

    monkeypatch.setattr(s4_baselines, "run_s4_isolated", _fake)
    result = default_runners()[RUNNER_S4](s4_slot.ctx)
    assert [path.resolve() for path in calls] == [s4_slot.worker.resolve()], (
        f"the S4 runner drove {calls} instead of [{s4_slot.worker}]"
    )
    return result


def _level_row(report: dict) -> dict:
    rows = {check["check_id"]: check for check in report["checks"]}
    assert s3_gate.CHECK_LEVELS in rows, (
        f"the rewritten acceptance report has no {s3_gate.CHECK_LEVELS} row; it carries "
        f"{sorted(rows)}"
    )
    return rows[s3_gate.CHECK_LEVELS]


def test_pin4_real_metadata_rewrites_a_passing_level_row(
    s4_slot: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With S4's real 8-entry vector the floor is finally ANSWERED, and passes.

    The shipped report recorded `premise-not-met` for this row — S4 had not run
    when the gate did. That is the hole C-4b (b) closes.
    """
    before = json.loads(s4_slot.acceptance.read_text(encoding="utf-8"))
    assert _level_row(before)["status"] == "premise-not-met", (
        "fixture wall: the shipped acceptance report's level row was the recorded "
        "`premise-not-met` that let the 3-of-7 mismatch ride through"
    )

    result = _drive_s4(s4_slot, monkeypatch)

    after = json.loads(s4_slot.acceptance.read_text(encoding="utf-8"))
    row = _level_row(after)
    assert row["status"] == PASS, (
        f"the re-answered level row is {row['status']!r} for a game with 8 baselines and 8 "
        f"levels. Note: {row['note']!r}"
    )
    assert after["layer"] == "structural", (
        f"the rewritten report's layer is {after['layer']!r}; C-4b (b) says "
        "`structural_acceptance` — the milliseconds path — and NEVER merged_gate, which "
        "would re-run the 7 robustness policies after every S4"
    )
    assert ACCEPTANCE_ARTIFACT in result["artifacts"], (
        f"the runner declared no {ACCEPTANCE_ARTIFACT!r} artifact; C-4b (b) records the "
        f"rewritten report so the review can read it. Artifacts: {sorted(result['artifacts'])}"
    )
    assert Path(result["artifacts"][ACCEPTANCE_ARTIFACT]) == s4_slot.acceptance
    assert LEVEL_NOTE_ARTIFACT not in result["artifacts"], (
        "the level row PASSED, so no note artifact rides: C-4b (b) adds it only 'when the "
        "level row is not pass'"
    )


def test_pin4_doctored_metadata_fails_the_row_and_notes_it(
    s4_slot: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The measured defect, in the numbers: 3 baselines under an 8-level spec.

    The floor's §7-contract band is 6-10, so a 3-level game fails it — and the
    note reaches the ledger as an artifact, which is the "evidence for review"
    the contract asks for.
    """
    baselines = _doctor_baselines(s4_slot, 3)
    assert len(baselines) == 3

    result = _drive_s4(s4_slot, monkeypatch)

    row = _level_row(json.loads(s4_slot.acceptance.read_text(encoding="utf-8")))
    assert row["status"] == FAIL, (
        f"with only {baselines} on disk the level row is {row['status']!r}; the whole point "
        "of the post-S4 re-check is that THIS is the shape that rode through b003r2"
    )
    assert LEVEL_NOTE_ARTIFACT in result["artifacts"], (
        f"the level row failed and no {LEVEL_NOTE_ARTIFACT!r} artifact rides. C-4b (b): "
        "'when the level row is not pass, a note artifact'. Artifacts: "
        f"{sorted(result['artifacts'])}"
    )
    assert result["artifacts"][LEVEL_NOTE_ARTIFACT] == row["note"], (
        "the note artifact must be the ROW'S note verbatim — a paraphrase is a second source "
        f"of truth. Artifact: {result['artifacts'][LEVEL_NOTE_ARTIFACT]!r}; row: {row['note']!r}"
    )


@pytest.mark.parametrize("baselines", [None, 3])
def test_pin4_the_stage_result_is_unchanged_whatever_the_rows_say(
    s4_slot: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, baselines: int | None
) -> None:
    """V1 RECORDS. "the runner's ok/state routing is unchanged whatever the rows
    say (promotion to blocking is a later, separate ruling)".

    A failing floor that silently started BLOCKING slots would be a routing
    change smuggled in under a recording contract, so both metadata shapes are
    driven through the same assertions.
    """
    if baselines is not None:
        _doctor_baselines(s4_slot, baselines)

    result = _drive_s4(s4_slot, monkeypatch)

    assert result["ok"] is True, (
        f"the S4 stage reported ok={result['ok']!r} (reason: {result['reason']!r}) — C-4b (b) "
        "is V1 RECORDS: a fit is still a fit whatever the re-checked floor says"
    )
    assert result["to_state"] == "baselined", (
        f"the S4 stage routed to {result['to_state']!r}; a recorded floor changes no edge"
    )
    assert "g-sampler" in result["reason"], (
        f"the fit reason line changed to {result['reason']!r} — the re-check appends "
        "artifacts, not a new verdict"
    )


def test_pin4_a_missing_frames_sidecar_skips_the_recheck(
    s4_slot: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"missing sidecar ⇒ skip the re-check with a note in artifacts (never
    crash S4)".

    Ambiguity f: which key carries the skip note is not frozen, so this pins
    the behavior — nothing crashes, nothing routes differently, the report on
    disk is byte-unchanged, and a note rides.
    """
    s4_slot.frames_path.unlink()
    before = s4_slot.acceptance.read_bytes()

    result = _drive_s4(s4_slot, monkeypatch)

    assert result["ok"] is True and result["to_state"] == "baselined", (
        "a missing S2b frames sidecar must not fail or reroute S4 — the re-check is "
        "evidence, and evidence that cannot be gathered is a note"
    )
    assert s4_slot.acceptance.read_bytes() == before, (
        "the acceptance report was rewritten although the re-check could not run: without a "
        "capture there are no new rows, and overwriting the old ones loses the record"
    )
    notes = {
        key: value
        for key, value in result["artifacts"].items()
        if key in orchestrator.NOTE_ARTIFACTS
    }
    assert notes, (
        "no note artifact explains the skipped re-check. C-4b (b): 'missing sidecar ⇒ skip "
        f"the re-check with a note in artifacts'. Artifacts: {sorted(result['artifacts'])}"
    )
    assert all(str(value).strip() for value in notes.values()), f"empty note(s): {notes}"


def test_pin4_a_missing_sidecar_declares_no_rewritten_report(
    s4_slot: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ambiguity f, on its own line: with the re-check skipped there is no
    re-answered report, so the runner must not point the review at the stale one."""
    s4_slot.frames_path.unlink()
    result = _drive_s4(s4_slot, monkeypatch)

    assert ACCEPTANCE_ARTIFACT not in result["artifacts"], (
        f"the runner declared {ACCEPTANCE_ARTIFACT!r} after skipping the re-check — that key "
        "means 'here is the floor re-answered with S4's numbers', and nothing re-answered it"
    )


def test_pin4_a_crashing_recheck_cannot_fail_the_stage(
    s4_slot: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"Wrap the re-check so no exception in it can fail the S4 stage; record
    `post_s4_acceptance_error` instead."

    The failure is injected at `structural_acceptance`, the one call C-4b (b)
    names, so the wrap is measured where the contract puts it.
    """
    def _boom(*_args, **_kwargs):
        raise RuntimeError("synthetic post-S4 re-check failure")

    monkeypatch.setattr(s3_gate, "structural_acceptance", _boom)
    result = _drive_s4(s4_slot, monkeypatch)

    assert result["ok"] is True and result["to_state"] == "baselined", (
        "an exception inside the recorded re-check failed the S4 stage; C-4b (b) wraps it "
        "precisely so a V1 recording step can never cost a slot its baselines"
    )
    assert ERROR_NOTE_ARTIFACT in result["artifacts"], (
        f"no {ERROR_NOTE_ARTIFACT!r} artifact after the re-check raised. Artifacts: "
        f"{sorted(result['artifacts'])}"
    )
    assert "synthetic post-S4 re-check failure" in str(result["artifacts"][ERROR_NOTE_ARTIFACT]), (
        "the error note must carry the exception text, or the review cannot tell a broken "
        f"re-check from a silent one. Note: {result['artifacts'][ERROR_NOTE_ARTIFACT]!r}"
    )


def test_pin4_the_note_keys_are_exempt_from_the_on_disk_rule() -> None:
    """C-4b (b): "(extend NOTE_ARTIFACTS)" — twice, once per note.

    §4's rule is "every declared artifact is on disk"; a note is not a path, so
    existence-checking one would turn a record into a run-killing RuntimeError.
    """
    missing = [key for key in NOTE_KEYS if key not in orchestrator.NOTE_ARTIFACTS]
    assert not missing, (
        f"{missing} are not in orchestrator.NOTE_ARTIFACTS, which is "
        f"{orchestrator.NOTE_ARTIFACTS} — C-4b (b) extends the named exemption list for both "
        "notes it introduces"
    )


def test_pin4_the_rewritten_report_is_a_path_not_a_note() -> None:
    """Ambiguity g, on its own line: `post_s4_acceptance` is `<path>` in the
    contract, so it stays subject to §4's existence check.

    Exempting it would let a runner declare a report it never wrote — the exact
    failure `_check_artifacts` exists to catch.
    """
    assert ACCEPTANCE_ARTIFACT not in orchestrator.NOTE_ARTIFACTS, (
        f"{ACCEPTANCE_ARTIFACT!r} is in NOTE_ARTIFACTS. C-4b (b) spells it "
        "'\"post_s4_acceptance\": <path>', and the exemption list's own comment says "
        "everything that is not a note 'is still a path that must exist'"
    )


@pytest.mark.parametrize("baselines", [None, 3])
def test_pin4_every_declared_artifact_survives_the_section_4_check(
    s4_slot: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, baselines: int | None
) -> None:
    """The runner's artifacts, run past the rule that consumes them.

    `_check_artifacts` is what the run loop applies before appending a
    transition: a note that is not exempt, or a path that is not on disk, kills
    the run there. This is the end-to-end proof that C-4b's new keys are
    declared correctly.
    """
    if baselines is not None:
        _doctor_baselines(s4_slot, baselines)
    result = _drive_s4(s4_slot, monkeypatch)

    orchestrator._check_artifacts(STAGE_S4, result)
