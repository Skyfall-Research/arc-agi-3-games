"""Load-and-drive harness for the worker's game + solver.

Engine facts this code relies on (verified against arcengine 0.9.3
source): perform_action(ActionInput) returns FrameData whose frames are
64x64 int grids; settled frame = frame[-1]; RESET at action-count 0 is a
full reset; next_level() credits levels_completed and wins the game on the
last level; a finished game answers non-RESET actions with an EMPTY frame
list and the terminal state.

The engine-conformance RULES live in `_contracts.py` (self-contained so
the pipeline can run them against the officials); this module is the
load-and-drive layer on top and imports FROM there, never the reverse.

It also reads the pipeline's seed sidecar (`read_seed_plan`) and drives a
game at an EXPLICIT layout seed (`run_solver(..., layout_seed=s)`), which is
what `tests/test_seed_sweep.py` needs to reproduce the packager's own
layout-seed validation inside this loop.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from arcengine import ActionInput, ARCBaseGame, GameAction, GameState

from tests._contracts import frame_violations, quiet

WORKER_ROOT = Path(__file__).resolve().parents[1]
MAX_ACTIONS = 1200

# --- the S6 seed sweep's shared truth (contract E-0) ------------------------
# S6's own solver-drive bound, `gen/s6_package.MAX_ACTIONS`. Mirrored here
# because this tree is standalone and cannot import the pipeline, and pinned
# against that constant by `gen/tests/test_e0_seeds.py` — two diverging bounds
# is how the seed-reject class was born: a solver needing 700 actions is green
# under the scaffold battery's 1200 and a seed-reject at S6's 600.
S6_MAX_ACTIONS = 600

#: `<worker>.seeds.json` — the pipeline's seed sidecar. A SIBLING of this
#: worker, never a file inside it (new files here are edit-scope violations),
#: so it is absent in a hand-made tree and in the blind audit's staged copy.
SEEDS_SIDECAR = WORKER_ROOT.with_name(WORKER_ROOT.name + ".seeds.json")


@dataclass(frozen=True)
class SeedPlan:
    """The seed list S6 will validate this game at, as the sidecar records it.

    `error` is None exactly when the sidecar is usable. A sidecar that exists
    but carries no usable seed list sets it instead of pretending the sweep
    passed — silence there would be the one failure mode this whole mechanism
    exists to remove.
    """

    seeds: tuple[int, ...]
    max_actions: int
    authored_seed: int | None
    game_id: str | None
    batch_seed: int | None
    count: int | None
    path: Path
    error: str | None = None


def _seed_plan_error(path: Path, note: str) -> SeedPlan:
    return SeedPlan(
        seeds=(), max_actions=S6_MAX_ACTIONS, authored_seed=None, game_id=None,
        batch_seed=None, count=None, path=path, error=f"{path}: {note}",
    )


def read_seed_plan(path: Path | None = None) -> SeedPlan | None:
    """The seed sidecar beside this worker, or None when there is none.

    ABSENT IS A PREMISE, NOT A FAILURE: a worker instantiated before E-0, a
    hand-made tree, the toy fixtures and the blind audit's staged copy all have
    no sidecar, and the sweep skips for them. Anything else — unparseable
    bytes, a missing or empty seed list, a non-int or repeated seed, a
    non-positive bound — comes back as a `SeedPlan` carrying `error`.
    """
    path = SEEDS_SIDECAR if path is None else Path(path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _seed_plan_error(path, f"unreadable seed sidecar ({exc})")
    if not isinstance(payload, dict):
        return _seed_plan_error(
            path, f"seed sidecar is not a JSON object (got {type(payload).__name__})"
        )

    raw = payload.get("seeds")
    if not isinstance(raw, list) or not raw:
        return _seed_plan_error(path, f"'seeds' must be a non-empty list, got {raw!r}")
    seeds: list[int] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int):
            return _seed_plan_error(path, f"'seeds' holds a non-int: {value!r}")
        if value in seeds:
            return _seed_plan_error(path, f"'seeds' repeats {value!r} — S6's list is distinct")
        seeds.append(int(value))

    bound = payload.get("max_actions", S6_MAX_ACTIONS)
    if isinstance(bound, bool) or not isinstance(bound, int) or bound < 1:
        return _seed_plan_error(path, f"'max_actions' must be a positive int, got {bound!r}")

    authored = payload.get("authored_seed")
    if authored is not None and (isinstance(authored, bool) or not isinstance(authored, int)):
        return _seed_plan_error(path, f"'authored_seed' must be an int or null, got {authored!r}")
    count = payload.get("count")
    if count is not None and (isinstance(count, bool) or not isinstance(count, int)):
        return _seed_plan_error(path, f"'count' must be an int or null, got {count!r}")
    game_id = payload.get("game_id")
    if game_id is not None and not isinstance(game_id, str):
        return _seed_plan_error(path, f"'game_id' must be a string or null, got {game_id!r}")
    batch_seed = payload.get("batch_seed")
    if batch_seed is not None and (isinstance(batch_seed, bool) or not isinstance(batch_seed, int)):
        return _seed_plan_error(path, f"'batch_seed' must be an int or null, got {batch_seed!r}")

    return SeedPlan(
        seeds=tuple(seeds), max_actions=int(bound),
        authored_seed=None if authored is None else int(authored),
        game_id=game_id, batch_seed=None if batch_seed is None else int(batch_seed),
        count=None if count is None else int(count), path=path, error=None,
    )


def _load_module(path: Path, module_name: str):
    if not path.is_file():
        raise FileNotFoundError(f"missing worker file: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None, f"cannot import {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    # Games print on import; quiet() hides the noise, never the exception.
    with quiet():
        spec.loader.exec_module(module)
    return module


def load_game_module(path: Path | None = None):
    """Exec-load `game.py` and return the MODULE.

    The §7 `build_layout(seed)` contract lives at module level, beside the
    game class, so the seed sweep needs the module and not only the class.
    """
    return _load_module(path or WORKER_ROOT / "game.py", "worker_game")


def game_class_in(module) -> type[ARCBaseGame]:
    """The one `ARCBaseGame` subclass `module` defines."""
    candidates = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and issubclass(obj, ARCBaseGame)
        and obj is not ARCBaseGame
        and obj.__module__ == module.__name__
    ]
    if len(candidates) != 1:
        raise AssertionError(
            f"game.py must define exactly ONE ARCBaseGame subclass, found "
            f"{[c.__name__ for c in candidates]!r}"
        )
    return candidates[0]


def load_game_class(path: Path | None = None) -> type[ARCBaseGame]:
    return game_class_in(load_game_module(path))


def load_solver_class(path: Path | None = None) -> type:
    module = _load_module(path or WORKER_ROOT / "solver.py", "worker_solver")
    solver_cls = getattr(module, "Solver", None)
    if not isinstance(solver_cls, type):
        # AssertionError on purpose (not TypeError): this is a contract
        # breach the battery must report as a test FAILURE, not an error.
        raise AssertionError("solver.py must define a class named Solver")  # noqa: TRY004
    return solver_cls


def check_frame_data(fd, *, context: str) -> None:
    """Every rendered frame must be 64x64, integer, colors 0-15.

    The rules live in `_contracts.frame_violations` (one copy, shared with
    the officials calibration); this is the assert-shaped front door.
    """
    violations = frame_violations(fd, context)
    assert not violations, "\n".join(violations)


def describe_action(action: ActionInput) -> str:
    data = {k: action.data[k] for k in sorted(action.data)} if action.data else {}
    return f"{action.id.name}{data or ''}"


@dataclass
class RunResult:
    final_state: GameState
    levels_completed: int
    win_levels: int
    actions: list[str] = field(default_factory=list)
    transitions: int = 0
    final_settled_frame: np.ndarray | None = None
    # process_time() seconds, one entry per perform_action call INCLUDING the
    # opening RESET (which clones every level and is often the slowest call).
    action_process_times: list[float] = field(default_factory=list)
    # One entry per observed level transition:
    # (levels_completed_after, len(fd.frame), was_terminal_after).
    # The engine queues a transition and renders it on a second pass, so a
    # non-terminal transition renders >= 2 frames; the LAST level instead
    # calls win() inline and renders one. Hence the terminal flag.
    transition_frame_counts: list[tuple[int, int, bool]] = field(default_factory=list)


def run_solver(
    game_cls: type[ARCBaseGame],
    solver_cls: type,
    *,
    max_actions: int = MAX_ACTIONS,
    layout_seed: int | None = None,
) -> RunResult:
    """Drive the solver against the game; `layout_seed` picks the construction.

    `layout_seed=None` is the AUTHORED default and constructs both classes with
    NO argument — exactly what this harness has always done, and what the
    scaffold battery still does.

    An int is passed EXPLICITLY as `layout_seed=` to BOTH classes, which is how
    `gen/s6_package.validate_seed` constructs them for every seed it validates,
    the authored one included. The distinction is not cosmetic: a game that
    reads its seed only in the no-argument path, or a solver that plans from a
    module constant instead of the seed it was handed, is green under no-arg
    construction and a seed-reject under S6's.
    """
    with quiet():
        game = game_cls() if layout_seed is None else game_cls(layout_seed=int(layout_seed))
    solver = solver_cls() if layout_seed is None else solver_cls(layout_seed=int(layout_seed))
    solver.reset()

    # `result` below holds THIS list object, so later appends land in it.
    timings: list[float] = []

    def perform(action: ActionInput):
        start = time.process_time()
        with quiet():
            fd = game.perform_action(action)
        timings.append(time.process_time() - start)
        return fd

    fd = perform(ActionInput(id=GameAction.RESET))
    check_frame_data(fd, context="RESET")
    prev_completed = fd.levels_completed
    result = RunResult(
        final_state=fd.state,
        levels_completed=fd.levels_completed,
        win_levels=fd.win_levels,
        final_settled_frame=np.asarray(fd.frame[-1]),
        action_process_times=timings,
    )

    for step_idx in range(max_actions):
        if fd.state in (GameState.WIN, GameState.GAME_OVER):
            break
        action = solver.next_action(fd)
        if action is None:
            break
        assert isinstance(action, ActionInput), (
            f"solver returned {type(action).__name__}, expected ActionInput"
        )
        result.actions.append(describe_action(action))
        fd = perform(action)
        check_frame_data(fd, context=f"action #{step_idx + 1} {result.actions[-1]}")
        if fd.levels_completed > prev_completed:
            result.transitions += fd.levels_completed - prev_completed
            terminal = fd.state in (GameState.WIN, GameState.GAME_OVER)
            result.transition_frame_counts.append(
                (fd.levels_completed, len(fd.frame), terminal)
            )
        prev_completed = fd.levels_completed
        result.final_settled_frame = np.asarray(fd.frame[-1])
        result.final_state = fd.state
        result.levels_completed = fd.levels_completed
        result.win_levels = fd.win_levels

    return result
