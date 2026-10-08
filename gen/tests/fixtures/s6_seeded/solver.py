"""Seed-agnostic solver for the S6 §7 reference fixture (B10).

`Solver(layout_seed: int | None = None)` takes the SAME seed the game took
(`None` = `game.DEFAULT_LAYOUT_SEED`) and DERIVES its winning line: it calls
the game module's pure `build_layout(seed)` and breadth-first-searches each
level's geometry. There is no hardcoded move list, so the solver wins at ANY
seed — the property `package.seeds_validated` exists to check
(design/architecture.md §3 S6: "the solver must solve ANY seed (it receives
the same seed)").

The BFS explores in a fixed order (up, down, left, right), so the line is
deterministic; it is also a SHORTEST line, which is what makes the fixture's
`cap = 32 * dist` arithmetic hold (see game.py's header).

`game.py` is imported by PATH, under a name derived from that path, because
the harness loads workers with `importlib.util.spec_from_file_location`
(`gen/s3_static._load_module`) and never puts the worker dir on `sys.path`.
Hashing the path keeps two copies of this fixture (a test that copies it into
`tmp_path`, say) from clobbering each other in `sys.modules`.
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
    name = f"s6_seeded_game_{tag}"
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
    """The level's collidable cells, rebuilt from the layout alone.

    Row 0 is the HUD meter: `collidable=False`, but `wall_top` at row 1 seals
    it off, so treating it as blocked is exact rather than conservative.
    """
    walls = {(x, y) for x in range(mod.BOARD) for y in (0, mod.WALL_TOP_ROW, mod.BOARD - 1)}
    walls |= {(x, y) for x in (0, mod.BOARD - 1) for y in range(mod.BOARD)}
    walls |= {
        (spec["gate_x"], y)
        for y in range(mod.STRIP_Y_MIN, mod.STRIP_Y_MAX + 1)
        if y != spec["gap_y"]
    }
    return walls


def _plan(spec: dict, mod) -> list:
    """The shortest action-name line from the level's start cell to its goal."""
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
        raise ValueError(
            f"level {spec['level']} of layout seed has no route from {start} to {goal} — "
            "build_layout must never emit an unsolvable board (spec §7)"
        )
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
        self.plans = [_plan(spec, mod) for spec in mod.build_layout(self.layout_seed)]
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
