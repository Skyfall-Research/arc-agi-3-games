"""I-1 FIXTURE — repetition-death and budget.cap DIVERGE. Engine-verified, minimal.

The contract-I-1 divergence worker: a game whose per-level action allowance
(`budget.cap`) is one number and whose death-by-repetition is ANOTHER, so a
probe that reports the first repeated action's GAME_OVER count (the pre-I-1
burn probe) and a probe that measures the allowance give measurably different
answers on every level.

AUTHORED NUMBERS — `gen/tests/test_i1_instruments.py` asserts these exactly:

    level (1-indexed)            :   1     2
    solver actions (ACTION4 x)   :   2     3
    budget.cap (every action)    :  60    90
    lava rows above the start    :   3     4    <- ACTION1 repeated dies here

THE ALLOWANCE: every GAME action is charged, a blocked move included, and
exhaustion is wired to `lose()` WITH THE WIN CHECK FIRST (the 25/25 official
pattern the S4 fixtures share). The meter is the edge-anchored row 0.

THE REPETITION DEATH: a full-width LAVA row sits `lava_rows` cells above the
player's start. Touching it is `lose()` at once. So ACTION1 (up) — the first
declared action, the one the pre-I-1 probe burns — walks the player into the
lava after exactly `lava_rows` presses, long before the allowance could bind.
Nothing about that count is a budget: from the same position one press
earlier, a DOWN, LEFT or RIGHT press survives.

BOARD: 8x8, camera 8x8. Row 0 = meter, row 1 = wall_top, row 7 = wall_bottom,
columns 0 and 7 = walls. The player starts at (1, 6) on the bottom row of the
play strip and the goal sits on the same row, so each solver line is a run of
ACTION4 (right) and never goes near the lava.
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL, METER, LAVA = 4, 9, 12, 7, 2

BOARD = 8
METER_CELLS = 8
PLAYER_START = (1, 6)

# level index -> (goal x, per-level action cap, lava rows above the start).
# solver_i == goal_x - 1.
LEVEL_PLAN = ((3, 60, 3), (4, 90, 4))

DIRS = {
    GameAction.ACTION1: (0, -1),  # up    — toward the lava
    GameAction.ACTION2: (0, 1),   # down  — blocked by wall_bottom from the start
    GameAction.ACTION3: (-1, 0),  # left  — blocked by wall_left from the start
    GameAction.ACTION4: (1, 0),   # right — toward the goal
}


def _level(goal_x: int, lava_rows: int) -> Level:
    sprites = [
        Sprite([[METER]], name=f"meter_{k}", x=k, y=0, layer=1, collidable=False)
        for k in range(METER_CELLS)
    ]
    sprites += [
        Sprite([[WALL] * BOARD], name="wall_top", x=0, y=1),
        Sprite([[WALL] * BOARD], name="wall_bottom", x=0, y=7),
        Sprite([[WALL]] * 5, name="wall_left", x=0, y=2),
        Sprite([[WALL]] * 5, name="wall_right", x=7, y=2),
        Sprite(
            [[LAVA] * 6],
            name="lava",
            x=1,
            y=PLAYER_START[1] - lava_rows,
            layer=1,
            collidable=False,
        ),
        Sprite([[GOAL]], name="goal", x=goal_x, y=PLAYER_START[1], layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=PLAYER_START[0], y=PLAYER_START[1], layer=2),
    ]
    return Level(sprites=sprites)


class HazardBudgetBoard(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="i1-hazard-budget",
            levels=[_level(goal_x, lava) for goal_x, _cap, lava in LEVEL_PLAN],
            camera=Camera(width=BOARD, height=BOARD),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
        """The budget is PER LEVEL and restarts with every level."""
        self._budget_used = 0

    @property
    def _level_cap(self) -> int:
        return LEVEL_PLAN[self.level_index][1]

    def _paint_meter(self) -> None:
        cap = self._level_cap
        remaining = max(0, cap - self._budget_used)
        lit = -(-remaining * METER_CELLS // cap)
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
        lava = self.current_level.get_sprites_by_name("lava")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()  # WIN CHECK FIRST — the winning move is free
        elif player.y == lava.y:
            self.lose()  # the hazard: what was played, not how much
        elif self._budget_used >= self._level_cap:
            self.lose()  # the allowance: how much was played, not what
        self._paint_meter()
