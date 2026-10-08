"""THE DELIBERATE DEFECT — a solver that only solves the DEFAULT seed (B10).

This file is `fixtures/s6_seeded/solver.py` with ONE line changed: the plans
are derived from `DEFAULT_LAYOUT_SEED` instead of from the seed the solver was
handed. `self.layout_seed` is still recorded, so the constructor looks
conformant; the line it plays is simply the authored layout's line.

Consequence, and the whole point of the fixture: S6's seed validation WINS at
the authored seed (the replayed line is that layout's own shortest line) and
FAILS at every other validation seed — the gate wall has moved, the run walks
into it, the plan runs out and the drive ends NOT_FINISHED. That is verdict
`seed-reject` (B10 contract §Semantics 3), routed to S2, with tsv / manifest /
play-mirror NOT written.

The game half is correct: `game.py` honours `layout_seed`, so re-derivation
(same-seed determinism + pairwise distinctness) PASSES here. A seed-ignoring
`build_layout` would be a spec §7 violation — a different, louder failure —
and is deliberately NOT what this fixture models.
"""

import hashlib
import importlib.util
import sys
from collections import deque
from pathlib import Path

from arcengine import ActionInput, GameAction

_GAME_PATH = Path(__file__).resolve().with_name("game.py")

#: BFS expansion order — fixed, so the derived line is deterministic.
_MOVES = (("ACTION1", 0, -1), ("ACTION2", 0, 1), ("ACTION3", -1, 0), ("ACTION4", 1, 0))


def _game_module():
    tag = hashlib.sha256(str(_GAME_PATH).encode()).hexdigest()[:12]
    name = f"s6_seeded_broken_game_{tag}"
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, _GAME_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build an import spec for {_GAME_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _blocked(spec: dict, mod) -> set:
    walls = {(x, y) for x in range(mod.BOARD) for y in (0, mod.WALL_TOP_ROW, mod.BOARD - 1)}
    walls |= {(x, y) for x in (0, mod.BOARD - 1) for y in range(mod.BOARD)}
    walls |= {
        (spec["gate_x"], y)
        for y in range(mod.STRIP_Y_MIN, mod.STRIP_Y_MAX + 1)
        if y != spec["gap_y"]
    }
    return walls


def _plan(spec: dict, mod) -> list:
    start, goal = tuple(spec["player"]), tuple(spec["goal"])
    blocked = _blocked(spec, mod)
    came = {start: None}
    frontier = deque([start])
    while frontier:
        cell = frontier.popleft()
        if cell == goal:
            break
        for name, dx, dy in _MOVES:
            nxt = (cell[0] + dx, cell[1] + dy)
            if not (0 <= nxt[0] < mod.BOARD and 0 <= nxt[1] < mod.BOARD):
                continue
            if nxt in blocked or nxt in came:
                continue
            came[nxt] = (cell, name)
            frontier.append(nxt)
    if goal not in came:
        raise ValueError(f"level {spec['level']}: no route from {start} to {goal}")
    line = []
    cell = goal
    while came[cell] is not None:
        previous, name = came[cell]
        line.append(name)
        cell = previous
    line.reverse()
    return line


class Solver:
    def __init__(self, layout_seed: int | None = None) -> None:
        mod = _game_module()
        self.layout_seed = mod.DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        # THE DEFECT: `mod.DEFAULT_LAYOUT_SEED` where the reference passes
        # `self.layout_seed`. The line is the authored layout's line, always.
        self.plans = [_plan(spec, mod) for spec in mod.build_layout(mod.DEFAULT_LAYOUT_SEED)]
        self.reset()

    def reset(self) -> None:
        self._cursor = [0] * len(self.plans)

    def next_action(self, frame) -> "ActionInput | None":
        level = int(frame.levels_completed)
        if level >= len(self.plans):
            return None
        index = self._cursor[level]
        if index >= len(self.plans[level]):
            return None
        self._cursor[level] = index + 1
        return ActionInput(id=GameAction[self.plans[level][index]])
