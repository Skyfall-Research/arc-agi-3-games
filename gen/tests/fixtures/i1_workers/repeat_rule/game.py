"""I-1 FIXTURE — death-by-repetition LITERALLY: a streak rule beside a budget.

The third contract-I-1 divergence worker. Pressing the SAME action
`STREAK_LIMIT` times in a row ends the play (an anti-spam rule — hidden state,
like a budget counter, but a function of WHAT was played); separately, every
action is charged against a per-level allowance. Any single repeated action
therefore dies at the streak limit, which is all the pre-I-1 burn probe can
ever see; any two actions alternated never build a streak and die at the
allowance.

AUTHORED NUMBERS — `gen/tests/test_i1_instruments.py` asserts these exactly:

    level (1-indexed)              :   1     2
    solver actions (ACTION4 x)     :   2     3
    budget.cap (every action)      :  50    80
    streak limit (same action x N) :   6     6

The goal sits `solver` cells to the right; the solver's line is a short run of
ACTION4 (under the streak limit). Win check first, then the streak, then the
allowance. Row 0 is the meter.

BOARD: 8x8, camera 8x8. Walls frame the play strip x 1..6 / y 2..6. The player
starts at (3, 4), so every direction has room to move.
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL, METER = 4, 9, 12, 7

BOARD = 8
METER_CELLS = 8
PLAYER_START = (3, 4)
STREAK_LIMIT = 6

# level index -> (goal x, per-level cap on EVERY action).
LEVEL_PLAN = ((5, 50), (6, 80))

DIRS = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}


def _level(goal_x: int) -> Level:
    sprites = [
        Sprite([[METER]], name=f"meter_{k}", x=k, y=0, layer=1, collidable=False)
        for k in range(METER_CELLS)
    ]
    sprites += [
        Sprite([[WALL] * BOARD], name="wall_top", x=0, y=1),
        Sprite([[WALL] * BOARD], name="wall_bottom", x=0, y=7),
        Sprite([[WALL]] * 5, name="wall_left", x=0, y=2),
        Sprite([[WALL]] * 5, name="wall_right", x=7, y=2),
        Sprite([[GOAL]], name="goal", x=goal_x, y=PLAYER_START[1], layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=PLAYER_START[0], y=PLAYER_START[1], layer=2),
    ]
    return Level(sprites=sprites)


class RepeatRuleBoard(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="i1-repeat-rule",
            levels=[_level(goal_x) for goal_x, _cap in LEVEL_PLAN],
            camera=Camera(width=BOARD, height=BOARD),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
        self._budget_used = 0
        self._last = None
        self._streak = 0

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

        self._streak = self._streak + 1 if self.action.id == self._last else 1
        self._last = self.action.id
        delta = DIRS.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)
        self._budget_used += 1
        self.complete_action()

        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
        elif self._streak >= STREAK_LIMIT:
            self.lose()  # the repetition rule: what was played
        elif self._budget_used >= self._level_cap:
            self.lose()  # the allowance: how much was played
        self._paint_meter()
