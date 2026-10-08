"""S6 FIXTURE — THE §7 LAYOUT-FROM-SEED REFERENCE (B10). Engine-verified.

THE MECHANICAL CONVENTION this file is the reference implementation of
(spec-v0.3 §7 "layout-from-seed is REQUIRED from birth" + D13; the layout-seed
contract block in design/architecture.md §3 "S6 — packager"):

  * module-level `build_layout(seed: int) -> list` — a PURE function of the
    seed, importable and callable WITHOUT instantiating the game. Same seed →
    equal result; distinct seeds → STRUCTURALLY distinct results (the gate
    column, its gap row, the player's start row and the goal's row all move).
    The result is JSON-able (lists/dicts/ints only), so
    `json.dumps(build_layout(s), sort_keys=True)` is the comparison surface.
  * `Game(layout_seed: int | None = None)` — `None` means THE AUTHORED
    DEFAULT SEED, the module constant `DEFAULT_LAYOUT_SEED = 13` (named for
    D13, the decision this fixture demonstrates). Every instance records
    `self.layout_seed`.
  * `Solver(layout_seed: int | None = None)` receives the SAME seed and solves
    ANY seed: `solver.py` imports `build_layout` from THIS file and BFSes the
    layout it returns. No hardcoded move list anywhere.

BOARD: 8x8, the camera upscales 8x to 64x64. Row 0 = the reserved HUD meter,
row 1 and row 7 = walls, columns 0 and 7 = walls, play strip x 1..6 / y 2..6.
A full-height GATE wall stands at column `gate_x` with exactly one gap at row
`gap_y`, so every level is a "find the gap" board and the shortest line is
forced through it. The player starts at (1, player_y), the goal sits at
(6, goal_y) — different columns always, so no straight-line run reaches it.

LEVELS: exactly 6 — the spec §7 floor of the official 6-10 range.

THE BUDGET TRIPLE — spec-v0.3 §2 REQUIRED row 3, the 25/25 official pattern:
  * an edge-anchored meter EXISTS: row 0 holds eight `meter_<k>` cells that
    empty left-to-right as the level's budget burns. They are
    `collidable=False` (never in the collision space) and paint palette index
    7, which no on-board object uses (REQUIRED row 8: meter indices
    off-board).
  * exhaustion is wired to `lose()` WITH THE WIN CHECK FIRST: the action that
    lands on the goal calls `next_level()` and never `lose()`, even when it is
    the action that empties the meter — the winning move is free.
  * RESET NEVER CHARGES (the `fixtures/s4_workers` lesson): the engine's own
    accounting skips RESET (`_set_action` does not bump `_action_count`), so
    the budget skips it too. A cap is a count of GAME actions (D8).

DECLARED REFUSAL SEMANTICS — spec §2 FORBIDDEN ("mixed accidental refusal
semantics; charge-or-signal by RULE, never by accident"): a move blocked by a
wall is CHARGED against the budget. That is what an S4 cap probe burns
(`gen/s4_baselines._burn` presses ACTION1 from the level's start cell).

THE PER-LEVEL CAP IS DERIVED FROM THE LAYOUT, so S4 fits at EVERY seed:

    dist  = (GOAL_X - PLAYER_X) + |player_y - gap_y| + |gap_y - goal_y|
          = the BFS distance, 5..13 on this board (the gate forces the gap)
    cap   = BUDGET_FACTOR * dist,  BUDGET_FACTOR = 32

`solver_i == dist` (the solver plays a shortest line), S4 clips g at 6.0 so
`baseline_i <= 6 * solver_i`, and D8's battery margin needs
`5 * baseline_i <= cap_i` — i.e. `30 * dist <= 32 * dist`. True with room at
every seed, which is why this fixture packages rather than cap-rejects.
"""

import hashlib

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

GAME_ID = "s6-seeded-gate"

#: `Game(layout_seed=None)` / `Solver(layout_seed=None)` mean THIS seed.
DEFAULT_LAYOUT_SEED = 13

#: exactly the spec §7 floor of the official 6-10 range.
LEVEL_COUNT = 6

#: namespaced so a seed reused by another stage cannot collide with this draw.
LAYOUT_NAMESPACE = "s6-seeded-gate/layout/v1"

WALL, PLAYER, GOAL, METER = 4, 9, 12, 7

BOARD = 8
METER_CELLS = 8
METER_ROW = 0
WALL_TOP_ROW = 1
STRIP_Y_MIN, STRIP_Y_MAX = 2, 6
STRIP_ROWS = STRIP_Y_MAX - STRIP_Y_MIN + 1
PLAYER_X, GOAL_X = 1, 6
GATE_X_MIN, GATE_X_MAX = 2, 5
GATE_COLUMNS = GATE_X_MAX - GATE_X_MIN + 1

#: cap = BUDGET_FACTOR * BFS distance (header arithmetic: 32 > 5 * 6.0).
BUDGET_FACTOR = 32

DIRS = {
    GameAction.ACTION1: (0, -1),  # up   — blocked by wall_top from row 2
    GameAction.ACTION2: (0, 1),   # down
    GameAction.ACTION3: (-1, 0),  # left
    GameAction.ACTION4: (1, 0),   # right
}


def build_layout(seed: int) -> list:
    """The §7 layout function: PURE, deterministic, JSON-able, seed-varying.

    One dict per level, keys sorted by `json.dumps(..., sort_keys=True)` at the
    comparison site. `hashlib.sha256` (not `hash()`, which is salted per
    process) is what makes "same seed → same layout" hold across runs, and
    4 * 5 * 5 * 5 = 500 geometries per level over 6 levels is a 1.5e16 space —
    distinct seeds collide only by astronomical accident.
    """
    seed = int(seed)
    layout = []
    for index in range(LEVEL_COUNT):
        digest = hashlib.sha256(f"{LAYOUT_NAMESPACE}:{seed}:{index}".encode()).digest()
        gate_x = GATE_X_MIN + digest[0] % GATE_COLUMNS
        gap_y = STRIP_Y_MIN + digest[1] % STRIP_ROWS
        player_y = STRIP_Y_MIN + digest[2] % STRIP_ROWS
        goal_y = STRIP_Y_MIN + digest[3] % STRIP_ROWS
        dist = (GOAL_X - PLAYER_X) + abs(player_y - gap_y) + abs(gap_y - goal_y)
        layout.append(
            {
                "level": index + 1,
                "gate_x": gate_x,
                "gap_y": gap_y,
                "player": [PLAYER_X, player_y],
                "goal": [GOAL_X, goal_y],
                "cap": BUDGET_FACTOR * dist,
            }
        )
    return layout


def _level(spec: dict) -> Level:
    sprites = [
        Sprite([[METER]], name=f"meter_{k}", x=k, y=METER_ROW, layer=1, collidable=False)
        for k in range(METER_CELLS)
    ]
    sprites += [
        Sprite([[WALL] * BOARD], name="wall_top", x=0, y=WALL_TOP_ROW),
        Sprite([[WALL] * BOARD], name="wall_bottom", x=0, y=BOARD - 1),
        Sprite([[WALL]] * STRIP_ROWS, name="wall_left", x=0, y=STRIP_Y_MIN),
        Sprite([[WALL]] * STRIP_ROWS, name="wall_right", x=BOARD - 1, y=STRIP_Y_MIN),
    ]
    sprites += [
        Sprite([[WALL]], name=f"gate_{y}", x=spec["gate_x"], y=y)
        for y in range(STRIP_Y_MIN, STRIP_Y_MAX + 1)
        if y != spec["gap_y"]
    ]
    sprites += [
        Sprite([[GOAL]], name="goal", x=spec["goal"][0], y=spec["goal"][1], layer=1,
               collidable=False),
        Sprite([[PLAYER]], name="player", x=spec["player"][0], y=spec["player"][1], layer=2),
    ]
    return Level(sprites=sprites)


class SeededGateBoard(ARCBaseGame):
    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        # Assigned BEFORE super(): the engine builds and enters level 0 during
        # __init__, and `on_set_level` -> `_level_cap` reads `self._layout`.
        self.layout_seed = seed
        self._layout = build_layout(seed)
        super().__init__(
            game_id=GAME_ID,
            levels=[_level(spec) for spec in self._layout],
            camera=Camera(width=BOARD, height=BOARD),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
        """The budget is PER LEVEL: the engine calls this on RESET and on every
        level transition, and the meter restarts with it."""
        self._budget_used = 0

    @property
    def _level_cap(self) -> int:
        return self._layout[self.level_index]["cap"]

    def _paint_meter(self) -> None:
        cap = self._level_cap
        remaining = max(0, cap - self._budget_used)
        lit = -(-remaining * METER_CELLS // cap)  # ceil: >0 remaining keeps a cell lit
        for k in range(METER_CELLS):
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
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()  # WIN CHECK FIRST — the winning move is free
        elif self._budget_used >= self._level_cap:
            self.lose()  # exhaustion -> lose()
        self._paint_meter()
