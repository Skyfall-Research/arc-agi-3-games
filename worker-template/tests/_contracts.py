"""Engine-conformance contracts for one worker game (B2).

Every check is a pure function returning ``list[str]`` of violation
messages; ``[]`` means clean. Nothing here raises on a *game* fault — the
callers decide whether a violation is an assertion (worker battery) or a
row in a calibration table (officials sweep).

SELF-CONTAINED ON PURPOSE: stdlib + numpy + arcengine only, and no import
from ``tests.*``. ``gen/officials.py:load_contracts()`` execs this file
standalone under the module name ``worker_contracts`` to run the same
checks against the 25 signed officials, so this module must import with
no worker package on ``sys.path``. ``tests/_harness.py`` imports FROM
here; never the reverse.

Engine facts these checks are built on (verified against the installed
arcengine 0.9.3 source, base_game.py / enums.py):

- ``perform_action`` renders in a loop until ``complete_action()``; past
  1000 frames it raises ``ValueError("Action took too many frames")``.
  That exception IS the "handler path without complete_action" signature.
- RESET is a full reset when ``_action_count == 0`` or the game is WIN,
  a level reset otherwise. ``set_level()`` zeroes ``_action_count``, and
  ``ONLY_RESET_LEVELS=true`` rewrites the rule entirely — so the runtime
  checks pop that variable before instantiating anything.
- ``next_level()`` credits the level and, on the LAST level, calls
  ``win()`` directly instead of queueing a transition: the winning action
  renders one frame, every earlier transition renders at least two.
- A non-RESET action on a finished game returns early with ``frame=[]``
  AND zeroed counters (the early return passes ``score=``, which is not a
  FrameData field, so ``levels_completed``/``win_levels`` fall back to 0).
  Probing past a terminal state therefore reads as a counter regression
  that the game never committed — the probes re-instantiate instead.
- ``available_actions`` is read off the FRAME, never off the game object.
- ``GameAction(6)`` raises; enum members resolve by NAME only.
- Games PRINT on load and on actions, hence ``quiet()``.
"""

from __future__ import annotations

import ast
import contextlib
import io
import os
import time
from typing import Any

import numpy as np
from arcengine import ActionInput, ARCBaseGame, GameAction, GameState

# Per-action wall of the conformance battery, in SECONDS of process time.
# FROZEN 2026-09-21 from the 25-official calibration run with this same
# code: worst observed single perform_action = 23.61 ms (tu93 action
# probe; per-game maxes otherwise <= 11.07 ms, medians mostly < 1 ms),
# worst RESET = 9.05 ms (tn36; RESET clones every level and is covered
# because worker-side timings include the opening RESET). The bound is
# ~10x that worst observation: a generated game above it is pathological,
# not merely animated. Provenance: GEN design/calibration.md, B2 section
# + out/calibration/officials-latency.json.
PERFORM_ACTION_TIME_BOUND_S: float | None = 0.25

FRAME_SIZE = 64
COLOR_MIN, COLOR_MAX = 0, 15

TERMINAL_STATES = (GameState.WIN, GameState.GAME_OVER)

# ACTION6 probe positions: centre, and both far corners inside the 0-63 box.
CLICK_PROBES: tuple[tuple[int, int], ...] = ((32, 32), (1, 1), (62, 62))

SCORE_ATTRS = frozenset({"_score", "_win_score"})
LIFECYCLE_METHODS = frozenset(
    {"perform_action", "handle_reset", "full_reset", "level_reset", "next_level"}
)
# Mutating methods on os.environ. setdefault/update/pop are the spec'd three;
# clear/popitem are the same kind of write and would otherwise be a hole
# straight through this check (os.environ.clear() drops ONLY_RESET_LEVELS).
ENV_WRITE_METHODS = frozenset({"setdefault", "update", "pop", "clear", "popitem"})
ENV_WRITE_FUNCS = frozenset({"putenv", "unsetenv"})


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------


@contextlib.contextmanager
def quiet():
    """Swallow stdout/stderr — games print on load and on most actions.

    Exceptions still propagate: this hides noise, never failures.
    """
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


def mouse(x: int, y: int) -> ActionInput:
    """ACTION6 with coordinates that actually arrive.

    ``ActionInput`` is a pydantic model with fields (id, data, reasoning);
    ``ActionInput(id=..., x=1, y=2)`` silently DISCARDS x/y and the click
    lands blank. Games read ``action.data["x"]``.
    """
    return ActionInput(id=GameAction.ACTION6, data={"x": int(x), "y": int(y)})


def settled(fd) -> np.ndarray:
    """The settled board after an action — ``frame[-1]``, not ``frame[0]``.

    One action may render several frames (animation, level transition);
    ``frame[0]`` shows the board mid-animation and reads as "nothing
    happened".
    """
    arr = np.array(fd.frame)
    while arr.ndim > 2:
        arr = arr[-1]
    return arr


def _action_by_id(action_id: int) -> GameAction | None:
    """GameAction for a declared int, by NAME (``GameAction(6)`` raises)."""
    try:
        return GameAction[f"ACTION{int(action_id)}"]
    except (KeyError, ValueError):
        return None


def _declared_actions(fd) -> list[int]:
    """Playable action ids off the FRAME, RESET removed, sorted."""
    return sorted({int(a) for a in fd.available_actions} - {GameAction.RESET.value})


def frame_violations(fd, context: str, *, allow_empty: bool = False) -> list[str]:
    """Every rendered frame must be 64x64, integer, colors 0-15.

    ``allow_empty`` exists for the one engine-true empty case: a non-RESET
    action on an already-finished game returns ``frame=[]`` by design.
    """
    violations: list[str] = []
    frames = fd.frame
    if not frames:
        if not allow_empty:
            violations.append(f"{context}: action returned no frames")
        return violations

    for idx, grid in enumerate(frames):
        try:
            arr = np.asarray(grid)
        except ValueError as exc:  # ragged rows never become an array
            violations.append(f"{context}: frame[{idx}] is not a rectangular grid ({exc})")
            continue
        if arr.shape != (FRAME_SIZE, FRAME_SIZE):
            violations.append(
                f"{context}: frame[{idx}] shape {arr.shape}, expected "
                f"({FRAME_SIZE}, {FRAME_SIZE})"
            )
            continue
        if not np.issubdtype(arr.dtype, np.integer):
            violations.append(f"{context}: frame[{idx}] dtype {arr.dtype} is not integer")
            continue
        lo, hi = int(arr.min()), int(arr.max())
        if lo < COLOR_MIN or hi > COLOR_MAX:
            violations.append(
                f"{context}: frame[{idx}] colors [{lo}, {hi}] outside {COLOR_MIN}-{COLOR_MAX}"
            )
    return violations


# --------------------------------------------------------------------------
# static checks (AST over source text)
# --------------------------------------------------------------------------


def _parse(source: str, filename: str) -> tuple[ast.AST | None, list[str]]:
    """Parse, treating a SyntaxError as a violation rather than a crash."""
    try:
        return ast.parse(source, filename=filename), []
    except SyntaxError as exc:
        return None, [f"{filename}:{exc.lineno or 0}: does not parse: {exc.msg}"]


def _ordered(found: list[tuple[int, str]]) -> list[str]:
    """Violations in source order, deterministic across runs."""
    return [message for _, message in sorted(found, key=lambda item: item[0])]


def _self_score_attr(node: ast.AST) -> str | None:
    """``self._score`` / ``self._win_score`` as an attribute target."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        and node.attr in SCORE_ATTRS
    ):
        return node.attr
    return None


def _unpack_targets(node: ast.AST):
    """Flatten tuple/list/starred assignment targets to leaves."""
    if isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            yield from _unpack_targets(item)
        return
    if isinstance(node, ast.Starred):
        yield from _unpack_targets(node.value)
        return
    yield node


def score_mutation_violations(source: str, filename: str) -> list[str]:
    """Ban direct writes to the engine's score fields.

    Levels are credited by ``next_level()`` only; downstream reward and
    level accounting read the engine's own ``levels_completed`` /
    ``win_levels``, so a direct write breaks scoring silently.
    """
    tree, violations = _parse(source, filename)
    if tree is None:
        return violations

    found: list[tuple[int, str]] = []

    def record(lineno: int, attr: str, kind: str) -> None:
        found.append((lineno, f"{filename}:{lineno}: direct self.{attr} {kind}"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                for candidate in _unpack_targets(target):
                    attr = _self_score_attr(candidate)
                    if attr:
                        record(node.lineno, attr, "assignment")
        elif isinstance(node, ast.AugAssign):
            attr = _self_score_attr(node.target)
            if attr:
                record(node.lineno, attr, "augmented assignment")
        elif isinstance(node, ast.AnnAssign):
            attr = _self_score_attr(node.target)
            if attr:
                record(node.lineno, attr, "annotated assignment")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "self"
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in SCORE_ATTRS
        ):
            record(node.lineno, str(node.args[1].value), "setattr")

    return _ordered(found)


def _class_level_defs(cls: ast.ClassDef) -> list[ast.stmt]:
    """Methods of ``cls``, including conditionally defined ones.

    Descends through if/try/with/for blocks in the class body but stops at
    any nested function (a closure is not a method) or nested class (which
    ``ast.walk`` visits on its own).
    """
    methods: list[ast.stmt] = []

    def visit(body: list[ast.stmt]) -> None:
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(stmt)
            elif isinstance(stmt, ast.ClassDef):
                continue
            else:
                for field in ("body", "orelse", "finalbody"):
                    inner = getattr(stmt, field, None)
                    if isinstance(inner, list):
                        visit([s for s in inner if isinstance(s, ast.stmt)])
                for handler in getattr(stmt, "handlers", []):
                    visit(handler.body)

    visit(cls.body)
    return methods


def lifecycle_override_violations(source: str, filename: str) -> list[str]:
    """Ban overriding the engine's action/reset/level lifecycle.

    Game logic belongs in ``step()``. Overriding any of these replaces the
    engine's own accounting, and the conformance battery below would then
    be measuring the game's reimplementation instead of the engine.
    """
    tree, violations = _parse(source, filename)
    if tree is None:
        return violations

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for method in _class_level_defs(node):
            if method.name in LIFECYCLE_METHODS:
                message = (
                    f"{filename}:{method.lineno}: {node.name}.{method.name}() "
                    "overrides an engine lifecycle method"
                )
                found.append((method.lineno, message))
    return _ordered(found)


def _is_environ(node: ast.AST) -> bool:
    """``os.environ`` or a bare ``environ`` from ``from os import environ``."""
    if isinstance(node, ast.Attribute) and node.attr == "environ":
        return isinstance(node.value, ast.Name) and node.value.id == "os"
    return isinstance(node, ast.Name) and node.id == "environ"


def _environ_subscript(node: ast.AST) -> bool:
    return isinstance(node, ast.Subscript) and _is_environ(node.value)


def env_tampering_violations(source: str, filename: str) -> list[str]:
    """Ban writes to the process environment.

    The harness controls RESET semantics through ``ONLY_RESET_LEVELS``; a
    game that writes the environment can flip reset behaviour underneath
    the battery and the officials calibration.
    """
    tree, violations = _parse(source, filename)
    if tree is None:
        return violations

    found: list[tuple[int, str]] = []

    def record(lineno: int, what: str) -> None:
        found.append((lineno, f"{filename}:{lineno}: writes the process environment ({what})"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                for candidate in _unpack_targets(target):
                    if _environ_subscript(candidate):
                        record(node.lineno, "os.environ[...] = ...")
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            if _environ_subscript(node.target):
                record(node.lineno, "os.environ[...] assignment")
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                if _environ_subscript(target):
                    record(node.lineno, "del os.environ[...]")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            func = node.func
            if func.attr in ENV_WRITE_METHODS and _is_environ(func.value):
                record(node.lineno, f"os.environ.{func.attr}()")
            elif (
                func.attr in ENV_WRITE_FUNCS
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            ):
                record(node.lineno, f"os.{func.attr}()")

    return _ordered(found)


def run_all_static(source: str, filename: str) -> dict[str, list[str]]:
    """Every static check over one source file, keyed by check name."""
    return {
        "score_mutation": score_mutation_violations(source, filename),
        "lifecycle_override": lifecycle_override_violations(source, filename),
        "env_tampering": env_tampering_violations(source, filename),
    }


# --------------------------------------------------------------------------
# runtime checks (fresh instance per check, quieted)
# --------------------------------------------------------------------------


def _fresh_game(game_cls: type[ARCBaseGame]) -> ARCBaseGame:
    """A quieted fresh instance with ONLY_RESET_LEVELS cleared.

    That variable rewrites ``handle_reset``, so leaving it set would make
    R4/R5 measure a different contract than the one the workers ship
    against.
    """
    os.environ.pop("ONLY_RESET_LEVELS", None)
    with quiet():
        return game_cls()


def _perform(game: ARCBaseGame, action: ActionInput):
    with quiet():
        return game.perform_action(action)


def _reset(game: ARCBaseGame):
    return _perform(game, ActionInput(id=GameAction.RESET))


def _started(game_cls: type[ARCBaseGame]) -> tuple[ARCBaseGame, Any]:
    game = _fresh_game(game_cls)
    return game, _reset(game)


def _probe_input(action: GameAction, coords: tuple[int, int] | None) -> ActionInput:
    return mouse(*coords) if coords is not None else ActionInput(id=action)


def _probe_label(action: GameAction, coords: tuple[int, int] | None) -> str:
    return f"{action.name}@{coords}" if coords is not None else action.name


def _probe_failure(label: str, exc: BaseException) -> str:
    """Name the failure, and name the cause when the engine spells it out."""
    if isinstance(exc, ValueError) and "frame" in str(exc).lower():
        return (
            f"{label}: {type(exc).__name__}: {exc} — a step() path returned without "
            "complete_action(); the engine re-renders until the action completes"
        )
    return f"{label}: raised {type(exc).__name__}: {exc}"


def reset_violations(game_cls: type[ARCBaseGame]) -> list[str]:
    """R2: a fresh game answers RESET with a valid, zeroed, playable frame."""
    game, fd = _started(game_cls)
    del game
    violations = frame_violations(fd, "RESET")
    if fd.levels_completed != 0:
        violations.append(f"RESET: levels_completed {fd.levels_completed}, expected 0")
    if fd.win_levels < 1:
        violations.append(f"RESET: win_levels {fd.win_levels}, expected at least 1")
    if fd.state != GameState.NOT_FINISHED:
        violations.append(f"RESET: state {fd.state.name}, expected NOT_FINISHED")
    return violations


def action_probe_violations(
    game_cls: type[ARCBaseGame],
) -> tuple[list[str], list[float]]:
    """R3: every declared action completes, renders, and never rewinds score.

    Returns ``(violations, latency_samples_seconds)`` — process time per
    successful ``perform_action``; failed calls contribute no sample.
    """
    violations: list[str] = []
    latencies: list[float] = []

    game, fd = _started(game_cls)
    declared = _declared_actions(fd)
    if not declared:
        violations.append("RESET frame declares no playable action (available_actions is empty)")
        return violations, latencies

    probes: list[tuple[GameAction, tuple[int, int] | None]] = []
    for action_id in declared:
        action = _action_by_id(action_id)
        if action is None:
            violations.append(
                f"available_actions declares {action_id}, which is not a GameAction id (1-7)"
            )
            continue
        if action is GameAction.ACTION6:
            probes.extend((action, coords) for coords in CLICK_PROBES)
        else:
            probes.append((action, None))

    completed = fd.levels_completed
    win_levels = fd.win_levels

    for action, coords in probes:
        label = _probe_label(action, coords)
        if fd.state in TERMINAL_STATES:
            # A finished game answers non-RESET actions with an empty frame and
            # zeroed counters — probing on would read as a regression the game
            # never committed. Start over instead.
            game, fd = _started(game_cls)
            completed = fd.levels_completed

        start = time.process_time()
        try:
            fd = _perform(game, _probe_input(action, coords))
        except Exception as exc:  # noqa: BLE001 — every failure mode is a violation
            violations.append(_probe_failure(label, exc))
            game, fd = _started(game_cls)
            completed = fd.levels_completed
            continue
        latencies.append(time.process_time() - start)

        violations.extend(frame_violations(fd, label))
        if fd.levels_completed < completed:
            violations.append(
                f"{label}: levels_completed went backwards {completed} -> {fd.levels_completed}"
            )
        completed = fd.levels_completed
        if fd.win_levels != win_levels:
            violations.append(f"{label}: win_levels changed {win_levels} -> {fd.win_levels}")
            win_levels = fd.win_levels

    return violations, latencies


def reset_restore_violations(game_cls: type[ARCBaseGame], probes: int = 8) -> list[str]:
    """R4: RESET restores the opening board after a burst of actions.

    Returns clean when the burst leaves the level (a credited level or a
    terminal state) — RESET is then legitimately not a restore, and the
    trial simply did not exercise the contract.
    """
    game, fd = _started(game_cls)
    opening = settled(fd)
    declared = _declared_actions(fd)
    if not declared:
        return []  # not exercisable; action_probe_violations reports the cause
    completed = fd.levels_completed

    for index in range(probes):
        action = _action_by_id(declared[index % len(declared)])
        if action is None:
            continue  # reported by action_probe_violations
        coords = CLICK_PROBES[0] if action is GameAction.ACTION6 else None
        try:
            fd = _perform(game, _probe_input(action, coords))
        except Exception as exc:  # noqa: BLE001
            return [_probe_failure(f"reset-restore burst, {_probe_label(action, coords)}", exc)]
        if fd.levels_completed != completed or fd.state in TERMINAL_STATES:
            return []

    restored = settled(_reset(game))
    if np.array_equal(restored, opening):
        return []
    if restored.shape != opening.shape:
        detail = f"shape {restored.shape} vs opening {opening.shape}"
    else:
        detail = f"{int(np.count_nonzero(restored != opening))} cell(s) differ"
    return [f"RESET after {probes} action(s) did not restore the opening frame ({detail})"]


def double_reset_violations(game_cls: type[ARCBaseGame]) -> list[str]:
    """R5: RESET is idempotent — two in a row render the same board."""
    game, first = _started(game_cls)
    second = _reset(game)
    frame_one, frame_two = settled(first), settled(second)
    if np.array_equal(frame_one, frame_two):
        return []
    if frame_one.shape != frame_two.shape:
        detail = f"shape {frame_two.shape} vs first {frame_one.shape}"
    else:
        detail = f"{int(np.count_nonzero(frame_one != frame_two))} cell(s) differ"
    return [f"a second RESET rendered a different board ({detail})"]


def run_all_runtime(
    game_cls: type[ARCBaseGame],
) -> tuple[dict[str, list[str]], list[float]]:
    """Every runtime check on one game class.

    Returns ``({check_name: violations}, latency_samples_seconds)``; the
    samples ride alongside rather than inside the dict so the mapping stays
    uniformly ``str -> list[str]`` for the calibration table.
    """
    reset = reset_violations(game_cls)
    probe, latencies = action_probe_violations(game_cls)
    checks = {
        "reset": reset,
        "action_probe": probe,
        "reset_restore": reset_restore_violations(game_cls),
        "double_reset": double_reset_violations(game_cls),
    }
    return checks, latencies
