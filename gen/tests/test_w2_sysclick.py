"""W2-B (R-07) — `sys_click` tightened for GENERATED games. BLIND pins.

Written from the W2-B contract alone, by an agent that never read the
implementation diff. The pre-state was taken from `git show
HEAD:gen/s3_static.py` only, and every "as at HEAD" number below was MEASURED
against a pristine `git archive HEAD` export before the implementer started.

THE RULING (operator, 2026-09-28)
------------------------------
Generated games MUST tag their click targets truthfully — a machine-consumer
guarantee, because RL agents and duck enumerate the engine's click list. A
generated game that declares ACTION6 among its available actions and tags ZERO
sprites `sys_click`/`sys_place` therefore FAILS static, with a reason naming
the ruling ("machine consumers cannot enumerate click targets").

The officials' raw-coordinate idiom stays legal FOR THEM. `static.sys-click-
truthful`'s D8 adjudication 4 passes 6/25 officials (bp35, cd82, ft09, lf52,
s5i5, su15) that declare ACTION6 with zero click sprites, and the B2-calibrated
25-official contract battery (200/200) must hold EXACTLY. So the ruling arrives
as a NEW check id; the old check's id and semantics do not move.

Why no knob: the contract pins this as a RULING, not a measurement pass. It is
a birth-time gate on FUTURE games — the seven shipped games are already
packaged and are not re-gated — so unconfigured behaviour for generated games
is allowed to change and no `static.sys_click_generated` knob is minted. The
house rule still binds the OFFICIALS' path, which is what PIN 4 and PIN 5a
hold to the byte.

HEAD PRE-STATE, measured (this is what the contract-bearing pins invert)
-----------------------------------------------------------------------
At HEAD every one of these is a PASS or an honest non-answer:

  generated + ACTION6 + zero tags    static.sys-click-truthful  pass  (D8 note)
  generated + ACTION6 + tagged       static.sys-click-truthful  pass
  generated, no ACTION6, zero tags   static.sys-click-truthful  premise-not-met
  OFFICIAL + ACTION6 + zero tags     static.sys-click-truthful  pass  (D8 note)
  convoy-in-the-fog (shipped)        static.sys-click-truthful  pass  (D8 note)

Note the third row: a keyboard-only generated game is `premise-not-met` at
HEAD, NOT `pass`. PIN 3 is therefore written as "no static fail", which is what
the contract's "passes" can honestly mean for a row whose premise is absent.

Note also rows 1 and 4: the RAW fixture and the OFFICIAL fixture are the SAME
BYTES staged in two directory layouts. That is the whole experiment — the only
variable is generated-vs-official context, so a pin pair over identical source
isolates exactly the discrimination the contract asks the implementer to make
honestly.

PINS
----
1. generated + ACTION6 + zero tags = FAIL, on a NEW check id, with a reason
   naming enumeration.                                    (fails at HEAD)
2. generated + ACTION6 + tagged = no static fail.          (regression)
3. generated without ACTION6 = no static fail.             (regression)
4. the officials' existing check keeps its D8 semantics — an official
   empty-tag fixture passes exactly as at HEAD, synthetic AND real (cd82).
                                                           (regression)
5. the check id is NEW and the old check is untouched: (a) an official dir
   still yields exactly the five frozen static ids in order — the shape the
   200/200 battery counts; (b) the new id is not the old id; (c) the old
   check's own HEAD matrix still holds.                    (b) fails at HEAD
6. convoy-in-the-fog replayed on a tmp copy = the new fail. (fails at HEAD)

HOW THE NEW CHECK IS FOUND
--------------------------
The contract deliberately does NOT name the new check's symbol or its id — it
leaves the implementer to choose between "key off context the runner already
provides" and "a separate check the official battery does not assert". A blind
test may not assume which. So `_verdicts` collects every CheckResult the module
will produce about clicks for one directory: the public `run_static_checks`
leg, plus every module-level click check it can bind (this is how a verdict
that lives only on the birth-time gate seam — the `_check_sys_click` shape that
`s2_implement._run_static_gate` imports — is still seen). A "new" result is one
whose id is neither of the five frozen static ids nor the birth-time
level-count id.

RULES OBEYED: tmp_path only; `out/` and `duckWM/` are READ-ONLY sources, always
copied to tmp before a replay; no API calls; no network; nothing is committed.
"""

from __future__ import annotations

import inspect
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import pytest

from gen import s3_static
from gen.frames import FrameCapture, capture, capture_from_json
from gen.s3_static import CheckResult, run_static_checks

REPO = Path(__file__).resolve().parents[2]
CONVOY = REPO / "out/corpus/b002-triple/convoy-in-the-fog"
# PIN UPDATE, 2026-10-06 (contract H-1 item 5 — THE 19TH SKIP), a FIXTURE path
# fix and not a change to what any assertion means. This was
# `REPO.parent / "duckWM/games"`, which stopped resolving when the officials
# moved to `duckWM/games/official/` (2026-09-29; every `config/*.yaml` was
# repointed to `../duckWM/games/official` at the time and this constant was
# not). The corpus WAS beside the repo, so `cd82_copy`'s
# `glob("cd82/*/cd82.py")` matched nothing and
# `test_pin4_real_official_cd82_still_passes` — the control that says the
# D8-calibrated battery has not moved — skipped silently from that day on. The
# path is now the one the configs name; the guard still skips on a clone with no
# duckWM beside it, which is all it was ever for.
DUCKWM_GAMES = REPO.parent / "duckWM" / "games" / "official"

# The five static ids frozen by the B7 contract (`gen/tests/test_b7_verify.py`
# STATIC_IDS), in order. The officials' battery counts this shape.
HEAD_STATIC_IDS = (
    "static.complete-action",
    "static.sys-click-truthful",
    "static.unread-minus2",
    "static.parsed-field-no-reader",
    "static.palette-hud-collision",
)
OLD_CHECK = "static.sys-click-truthful"

# The word the contract's BLIND paragraph requires of the new reason ("a reason
# naming enumeration"), matched as a stem so enumerate/enumeration/enumerable
# all satisfy it.
ENUMERATION_STEM = "enumerat"


# --------------------------------------------------------------------------- #
# fixture sources — minimal, runnable, and clean on the other four checks
# --------------------------------------------------------------------------- #

# Generated worker, the convoy idiom in miniature: ACTION6 is declared and the
# handler reads RAW COORDINATES out of `action.data`; no sprite is tagged.
RAW_CLICK_GAME = '''\
"""Fixture: a generated game that declares ACTION6 and tags NO click sprites."""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL = 4, 9, 12


def _level() -> Level:
    return Level(
        sprites=[
            Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
            Sprite([[WALL] * 8], name="wall_bottom", x=0, y=7),
            Sprite([[GOAL]], name="goal", x=6, y=6, layer=1, collidable=False),
            Sprite([[PLAYER]], name="player", x=1, y=1, layer=2),
        ]
    )


class RawCoordClick(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="w2b-raw-coord",
            levels=[_level()],
            camera=Camera(width=8, height=8),
            available_actions=[1, 6],
        )

    def step(self) -> None:
        if self.action.id is GameAction.ACTION6:
            cell = self.camera.display_to_grid(
                int(self.action.data.get("x", 0)), int(self.action.data.get("y", 0))
            )
            if cell is not None:
                self.try_move("player", 0, 0)
        self.complete_action()
        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
'''

# Generated worker that does the same job TRUTHFULLY: the clickable sprite
# carries `sys_click`, and the handler branches on it.
TAGGED_CLICK_GAME = '''\
"""Fixture: a generated game that declares ACTION6 and TAGS its click target."""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

FRAME, SWITCH = 4, 11


def _level() -> Level:
    return Level(
        sprites=[
            Sprite(
                [[FRAME] * 8 for _ in range(8)],
                name="backdrop",
                x=0,
                y=0,
                collidable=False,
            ),
            Sprite(
                [[SWITCH, SWITCH], [SWITCH, SWITCH]],
                name="switch",
                x=1,
                y=3,
                layer=1,
                tags=["sys_click"],
            ),
        ]
    )


class TaggedClick(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="w2b-tagged",
            levels=[_level()],
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

# Generated worker with no click action at all (the pump-flow shape).
KEYBOARD_GAME = '''\
"""Fixture: a keyboard-only generated game — no ACTION6, no click tags."""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL = 4, 9, 12

DIRS = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}


def _level() -> Level:
    return Level(
        sprites=[
            Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
            Sprite([[GOAL]], name="goal", x=6, y=6, layer=1, collidable=False),
            Sprite([[PLAYER]], name="player", x=1, y=1, layer=2),
        ]
    )


class KeyboardOnly(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="w2b-keyboard",
            levels=[_level()],
            camera=Camera(width=8, height=8),
            available_actions=[1, 2, 3, 4],
        )

    def step(self) -> None:
        delta = DIRS.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)
        self.complete_action()
        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
'''

# A worker ships a solver beside its game; an official never does. Staging one
# keeps the generated fixtures structurally identical to a real worker dir, so
# a discriminator reading EITHER `game.py` or `solver.py` sees the same truth.
WORKER_SOLVER = '''\
"""Fixture solver — present so the worker dir has the worker-template shape."""

from arcengine import ActionInput, GameAction


class Solver:
    def reset(self) -> None:
        self._sent = 0

    def next_action(self, frame) -> "ActionInput | None":
        if self._sent:
            return None
        self._sent = 1
        return ActionInput(id=GameAction.RESET)
'''


# --------------------------------------------------------------------------- #
# staging helpers — tmp_path only
# --------------------------------------------------------------------------- #


def _worker(tmp_path: Path, name: str, source: str) -> Path:
    """A GENERATED worker dir: `game.py` + `solver.py`, the worker-template shape."""
    worker = tmp_path / name
    worker.mkdir(parents=True)
    (worker / "game.py").write_text(source, encoding="utf-8")
    (worker / "solver.py").write_text(WORKER_SOLVER, encoding="utf-8")
    return worker


def _official(tmp_path: Path, slug: str, source: str) -> Path:
    """An OFFICIAL variant dir: `<slug>.py` + `metadata.json`, no game/solver.

    `gen/officials.py`: the corpus is `games/<slug>/<variant>/` holding
    `<slug>.py` and `metadata.json`, and `s3_static.game_source_path` falls back
    to "the one non-solver .py here" for exactly this layout.
    """
    variant = tmp_path / slug / "0a0ad940"
    variant.mkdir(parents=True)
    (variant / f"{slug}.py").write_text(source, encoding="utf-8")
    (variant / "metadata.json").write_text(
        json.dumps({"game_id": f"{slug}-0a0ad940"}) + "\n", encoding="utf-8"
    )
    return variant


def _game_class(path: Path) -> type:
    """Exec-load a fixture game file and return its one ARCBaseGame subclass."""
    import importlib.util
    import sys

    from arcengine import ARCBaseGame

    name = f"w2b_fixture_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot import {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
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


def _synthetic_capture(action_ids, click_cells=()) -> FrameCapture:
    """A capture built by hand, to hold `available_action_ids` as the variable.

    Used where running the engine would prove nothing the contract asks about
    (a real official's 25-check replay, and the old check's "tagged but ACTION6
    not declared" row). Only the eight documented fields are set, so the
    optional field W2-C adds to `FrameCapture` cannot break this.
    """
    return FrameCapture(
        game_id="w2b-synthetic",
        source="probe",
        records=(),
        click_cells=tuple(click_cells),
        available_action_ids=tuple(action_ids),
        solver_actions=(),
        levels_completed=0,
        win=False,
    )


# --------------------------------------------------------------------------- #
# discovery — the contract names no symbol for the new check
# --------------------------------------------------------------------------- #


def _click_check_callables() -> list[tuple[str, object]]:
    """Module-level click CHECKS (verdict producers), by name.

    Deliberately narrow: the name must mention clicks AND read as a check, so
    the AST helpers (`_click_facts`, `_clickable_sprites`, `_handler_targets`)
    are not called. At HEAD this finds exactly `_check_sys_click`.
    """
    found = []
    for name, obj in vars(s3_static).items():
        if not inspect.isfunction(obj):
            continue
        if getattr(obj, "__module__", None) != s3_static.__name__:
            continue
        low = name.lower()
        if "click" not in low:
            continue
        if not low.startswith(("_check", "check", "run")):
            continue
        found.append((name, obj))
    return sorted(found)


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
    if isinstance(value, CheckResult):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, CheckResult)]
    return []


def _verdicts(worker_dir: Path, cap: FrameCapture, *, generated: bool):
    """(results, diagnostics) — every click verdict the module gives this dir.

    `generated` is offered to the seams by name as a courtesy. The contract
    mints no knob, so an implementation that reads the directory itself simply
    ignores it; one that takes the fact as a parameter is told the truth.
    """
    results = list(run_static_checks(worker_dir, cap))
    diagnostics: list[str] = []
    pool = {
        "source": s3_static._parse_game(worker_dir),
        "cap": cap,
        "capture": cap,
        "worker_dir": Path(worker_dir),
        "path": Path(worker_dir),
        "game_dir": Path(worker_dir),
        "generated": generated,
        "is_generated": generated,
        "spec_path": None,
    }
    for name, fn in _click_check_callables():
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

    unique: list[CheckResult] = []
    seen = set()
    for result in results:
        key = (result.check_id, result.status, result.note)
        if key not in seen:
            seen.add(key)
            unique.append(result)
    return unique, diagnostics


def _is_new(result: CheckResult) -> bool:
    """A verdict the contract did not inherit from HEAD."""
    return (
        result.check_id not in HEAD_STATIC_IDS
        and result.check_id != s3_static.LEVEL_COUNT_CHECK
    )


def _fails(results) -> list[CheckResult]:
    return [r for r in results if r.status == "fail"]


def _one(results, check_id: str) -> CheckResult:
    matching = [r for r in results if r.check_id == check_id]
    assert matching, f"no {check_id} verdict in {_dump(results)}"
    return matching[0]


def _dump(results, diagnostics=()) -> str:
    body = json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False)
    if diagnostics:
        body += "\n\ndiscovery diagnostics:\n  " + "\n  ".join(diagnostics)
    return body


# --------------------------------------------------------------------------- #
# READ-ONLY sources, always replayed from a tmp copy
# --------------------------------------------------------------------------- #


@pytest.fixture
def convoy_replay(tmp_path):
    """convoy-in-the-fog's SHIPPED worker + sidecar, copied to tmp.

    The contract's exhibit: `available_action_ids [5, 6]`, `click_cells []`,
    zero `sys_click` occurrences in `worker/game.py`, 15 load-bearing
    raw-coordinate ACTION6 clicks. `out/` is READ-ONLY, so the replay runs on
    the copy and the shipped sidecar supplies the capture (re-running the
    solver would prove nothing this pin is about).
    """
    if not (CONVOY / "worker" / "game.py").is_file():
        pytest.skip(f"convoy's shipped worker is not in this tree ({CONVOY})")
    worker = tmp_path / "convoy-worker"
    shutil.copytree(
        CONVOY / "worker",
        worker,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "tests"),
    )
    sidecar = json.loads((CONVOY / "worker.frames.json").read_text(encoding="utf-8"))
    cap = capture_from_json(sidecar)
    # The exhibit, re-derived here rather than trusted: if convoy ever stops
    # being the raw-coordinate ACTION6 game, this pin must say so, not silently
    # test something else.
    assert 6 in cap.available_action_ids, cap.available_action_ids
    assert cap.click_cells == (), cap.click_cells
    body = (worker / "game.py").read_text(encoding="utf-8")
    assert "sys_click" not in body and "sys_place" not in body
    return worker, cap


@pytest.fixture
def cd82_copy(tmp_path):
    """A REAL D8-adjudicated official (cd82), copied out of the read-only corpus.

    cd82 declares `available_actions=[1, 2, 3, 4, 5, 6]` and carries zero
    `sys_click`/`sys_place` — one of the 6/25 the D8 adjudication passes.
    """
    matches = sorted(DUCKWM_GAMES.glob("cd82/*/cd82.py"))
    if not matches:
        pytest.skip(f"the read-only officials corpus is not beside this repo ({DUCKWM_GAMES})")
    variant = tmp_path / "cd82" / matches[0].parent.name
    variant.mkdir(parents=True)
    shutil.copy(matches[0], variant / "cd82.py")
    meta = matches[0].parent / "metadata.json"
    if meta.is_file():
        shutil.copy(meta, variant / "metadata.json")
    body = (variant / "cd82.py").read_text(encoding="utf-8")
    assert "sys_click" not in body and "sys_place" not in body
    return variant


# --------------------------------------------------------------------------- #
# PIN 1 — generated + ACTION6 + zero tags = fail, naming enumeration
# --------------------------------------------------------------------------- #


def test_pin1_generated_action6_without_tags_fails(tmp_path):
    """The ruling itself. At HEAD this is a PASS carrying the D8 note."""
    worker = _worker(tmp_path, "raw", RAW_CLICK_GAME)
    cap = capture(_game_class(worker / "game.py"))
    assert 6 in cap.available_action_ids, cap.available_action_ids
    assert cap.click_cells == (), "the fixture tags nothing, so the engine lists no click cell"

    results, diagnostics = _verdicts(worker, cap, generated=True)
    new_fails = [r for r in _fails(results) if _is_new(r)]
    assert new_fails, (
        "W2-B ruling: a GENERATED game that declares ACTION6 and tags ZERO "
        "sys_click/sys_place sprites must FAIL static on a NEW check id. Nothing new "
        "failed here.\n" + _dump(results, diagnostics)
    )
    failed = new_fails[0]
    assert ENUMERATION_STEM in failed.note.lower(), (
        f"{failed.check_id}'s reason must name the ruling — 'machine consumers cannot "
        f"ENUMERATE click targets'. Got: {failed.note!r}"
    )
    assert failed.evidence, f"{failed.check_id} must carry evidence a human can follow"


def test_pin1_the_new_fail_is_the_only_new_verdict_that_fails(tmp_path):
    """One ruling, one verdict: the fixture is clean on every other axis."""
    worker = _worker(tmp_path, "raw", RAW_CLICK_GAME)
    cap = capture(_game_class(worker / "game.py"))
    results, diagnostics = _verdicts(worker, cap, generated=True)
    inherited = [r.check_id for r in _fails(results) if not _is_new(r)]
    assert inherited == [], (
        "the RAW fixture is deliberately clean on the five inherited static checks; "
        f"these failed too: {inherited}\n" + _dump(results, diagnostics)
    )


# --------------------------------------------------------------------------- #
# PIN 2 — generated + tagged = pass
# --------------------------------------------------------------------------- #


def test_pin2_generated_with_tagged_click_targets_passes(tmp_path):
    """Tag your click targets and the ruling has nothing to say."""
    worker = _worker(tmp_path, "tagged", TAGGED_CLICK_GAME)
    cap = capture(_game_class(worker / "game.py"))
    assert 6 in cap.available_action_ids, cap.available_action_ids
    assert cap.click_cells, "the fixture tags a clickable sprite; the engine must list it"

    results, diagnostics = _verdicts(worker, cap, generated=True)
    assert _fails(results) == [], (
        "a generated game that TAGS its click targets satisfies the ruling and must not "
        "fail static.\n" + _dump(results, diagnostics)
    )
    assert _one(results, OLD_CHECK).status == "pass"


# --------------------------------------------------------------------------- #
# PIN 3 — generated without ACTION6 = pass
# --------------------------------------------------------------------------- #


def test_pin3_generated_keyboard_only_game_passes(tmp_path):
    """No click action, no premise. Measured at HEAD as `premise-not-met`.

    The ruling is keyed on DECLARING ACTION6. A keyboard-only generated game
    (the pump-flow shape) advertises no click, so there is no click list for a
    machine consumer to enumerate and nothing here may fail.
    """
    worker = _worker(tmp_path, "keyboard", KEYBOARD_GAME)
    cap = capture(_game_class(worker / "game.py"))
    assert 6 not in cap.available_action_ids, cap.available_action_ids

    results, diagnostics = _verdicts(worker, cap, generated=True)
    assert _fails(results) == [], (
        "a generated game that never declares ACTION6 cannot violate the ruling.\n"
        + _dump(results, diagnostics)
    )
    assert _one(results, OLD_CHECK).status in ("pass", "premise-not-met")


# --------------------------------------------------------------------------- #
# PIN 4 — the officials' check keeps its D8 semantics
# --------------------------------------------------------------------------- #


def test_pin4_official_with_empty_tags_passes_exactly_as_at_head(tmp_path):
    """THE CONTROLLED PAIR: identical bytes, official layout, opposite verdict.

    This stages the PIN 1 source as an official variant dir. The source is
    byte-for-byte the game that must now fail as a generated worker, so any
    difference in verdict is attributable to generated-vs-official context and
    to nothing else. D8 adjudication 4 must still pass it.
    """
    variant = _official(tmp_path, "zz99", RAW_CLICK_GAME)
    cap = _synthetic_capture((1, 6))

    results, diagnostics = _verdicts(variant, cap, generated=False)
    assert _fails(results) == [], (
        "D8 adjudication 4: an OFFICIAL that declares ACTION6 with zero click sprites "
        "reads raw coordinates and tells no lie — 6/25 officials ship this idiom and the "
        "B2-calibrated battery (200/200) must hold EXACTLY.\n" + _dump(results, diagnostics)
    )
    old = _one(results, OLD_CHECK)
    assert old.status == "pass", old
    assert "D8" in old.note, (
        "the officials' pass must still be the D8 adjudication, stated in the note as at "
        f"HEAD. Got: {old.note!r}"
    )


def test_pin4_real_official_cd82_still_passes(cd82_copy):
    """The synthetic control, repeated on a REAL member of the D8 six."""
    cap = _synthetic_capture((1, 2, 3, 4, 5, 6))
    results, diagnostics = _verdicts(cd82_copy, cap, generated=False)
    assert _fails(results) == [], (
        "cd82 is one of the six officials D8 adjudication 4 passes (it declares ACTION6 "
        "with zero sys_click/sys_place). A fail here moves the calibrated battery.\n"
        + _dump(results, diagnostics)
    )
    assert _one(results, OLD_CHECK).status == "pass"


# --------------------------------------------------------------------------- #
# PIN 5 — the check id is new; the old check is untouched
# --------------------------------------------------------------------------- #


def test_pin5a_official_dir_yields_exactly_the_five_frozen_static_ids(tmp_path):
    """The battery's shape. The officials' path stays byte-identical (house rule).

    `run_static_checks` is what the 25-official contract battery drives, and
    `gen/tests/test_b7_verify.py` freezes its five ids. Whatever seam the new
    check lives on, it must not grow this list for an OFFICIAL source.
    """
    variant = _official(tmp_path, "zz99", RAW_CLICK_GAME)
    results = run_static_checks(variant, _synthetic_capture((1, 6)))
    assert [r.check_id for r in results] == list(HEAD_STATIC_IDS), (
        "the officials' static leg must still be the five frozen checks, in order.\n"
        + _dump(results)
    )


def test_pin5b_the_ruling_lands_on_a_new_check_id(tmp_path):
    """A NEW id — the existing check's official semantics are not mutated."""
    worker = _worker(tmp_path, "raw", RAW_CLICK_GAME)
    cap = capture(_game_class(worker / "game.py"))
    results, diagnostics = _verdicts(worker, cap, generated=True)

    failed = _fails(results)
    assert failed, (
        "the ruling must produce a fail for this worker.\n" + _dump(results, diagnostics)
    )
    new_fails = [r for r in failed if _is_new(r)]
    assert new_fails, (
        "the ruling must land on a NEW check id. The contract forbids mutating "
        f"{OLD_CHECK}'s semantics, because the officials' battery asserts them. Failing "
        f"ids were {[r.check_id for r in failed]}.\n" + _dump(results, diagnostics)
    )
    for result in new_fails:
        assert result.check_id != OLD_CHECK
        assert result.check_id not in HEAD_STATIC_IDS
        assert result.check_id.strip(), "a check id must not be blank"


def test_pin5c_the_old_check_keeps_its_head_matrix(tmp_path):
    """`static.sys-click-truthful`'s own rows, measured at HEAD, still hold.

    Two rows the ruling must not disturb, both read off the same fixtures:
      tagged sprites + ACTION6 NOT declared  ->  fail (the tags lie)
      no tags + no ACTION6                   ->  premise-not-met
    """
    tagged = _worker(tmp_path, "tagged", TAGGED_CLICK_GAME)
    lying = _one(
        _verdicts(tagged, _synthetic_capture((1, 2, 3, 4)), generated=True)[0],
        OLD_CHECK,
    )
    assert lying.status == "fail", (
        "REQUIRED 2 at HEAD: sys_click sprites with no ACTION6 in available_actions "
        f"advertise a click the game never offers. Got {lying.status!r}: {lying.note!r}"
    )

    keyboard = _worker(tmp_path, "keyboard", KEYBOARD_GAME)
    quiet = _one(
        _verdicts(keyboard, _synthetic_capture((1, 2, 3, 4)), generated=True)[0],
        OLD_CHECK,
    )
    assert quiet.status == "premise-not-met", (
        "REQUIRED 2 at HEAD: no tags and no ACTION6 leaves the row with no premise. "
        f"Got {quiet.status!r}: {quiet.note!r}"
    )


# --------------------------------------------------------------------------- #
# PIN 6 — convoy-in-the-fog replayed = the new fail
# --------------------------------------------------------------------------- #


def test_pin6_convoy_shipped_worker_replays_as_the_new_fail(convoy_replay):
    """The audit exhibit, on a tmp copy of the shipped worker.

    convoy advertises `available_action_ids [5, 6]` with `click_cells []` and
    zero `sys_click` occurrences, and 15 raw-coordinate ACTION6 clicks are
    load-bearing (audit findings B4 + contradiction (a)). At HEAD it replays
    CLEAN — `static.sys-click-truthful` passes with the D8 note. Under the
    ruling it is exactly the game a machine consumer cannot enumerate.

    Shipped games are not re-gated; this is the proof the gate would have
    caught it, not a demand that convoy be withdrawn.
    """
    worker, cap = convoy_replay
    results, diagnostics = _verdicts(worker, cap, generated=True)
    new_fails = [r for r in _fails(results) if _is_new(r)]
    assert new_fails, (
        "convoy-in-the-fog is the contract's exhibit: a GENERATED game declaring ACTION6 "
        "with zero sys_click/sys_place sprites. Replayed on a tmp copy it must produce "
        "the new fail.\n" + _dump(results, diagnostics)
    )
    assert ENUMERATION_STEM in new_fails[0].note.lower(), new_fails[0].note


def test_pin6_convoy_inherited_checks_are_unmoved(convoy_replay):
    """Only the ruling changes convoy's verdict; HEAD's five are untouched.

    Measured at HEAD: convoy is clean on all five (two passes, two
    premise-not-met, and `static.sys-click-truthful` passing on D8).
    """
    worker, cap = convoy_replay
    results, diagnostics = _verdicts(worker, cap, generated=True)
    inherited = [r.check_id for r in _fails(results) if not _is_new(r)]
    assert inherited == [], (
        "convoy replays clean on the five inherited static checks at HEAD; the ruling "
        f"must not move them. These failed: {inherited}\n" + _dump(results, diagnostics)
    )


# ---------------------------------------------------------------------------
# lead-authored at the W2-B close: the birth-gate wiring (the blind file's
# ambiguity 6). The check must actually RIDE the generated-only static gate
# in s2_implement, and the payload must teach the rule it enforces — the
# blessing of the zero-tags idiom is corrected to a generated-game FAIL.
# ---------------------------------------------------------------------------


def test_lead_birth_gate_runs_the_generated_check():
    from gen import s2_implement, s3_static

    assert s3_static.SYS_CLICK_GENERATED_CHECK in s2_implement.GATE_CHECK_IDS
    import inspect

    gate_src = inspect.getsource(s2_implement._run_static_gate)
    assert "_check_sys_click_generated" in gate_src


def test_lead_payload_teaches_the_ruling_not_the_old_blessing():
    from gen.s2_implement import SYS_CLICK_ALGORITHM

    assert "TAG your click targets" in SYS_CLICK_ALGORITHM
    assert "legal for THEM and" in SYS_CLICK_ALGORITHM
    # the old text blessed the untagged idiom as an honest passing shape
    assert "both are honest" not in SYS_CLICK_ALGORITHM
