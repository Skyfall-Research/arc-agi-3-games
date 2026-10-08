"""I-1 FIXTURE — a real budget.cap the repeated-action burn can never find.

The second contract-I-1 divergence worker. Here the allowance charges only
EFFECTIVE moves: a move blocked by a wall changes nothing and costs nothing
(the "every action that changes nothing is free" refusal semantics that
lantern-path-parity-trace, conduit-watch, tidegate-mosaic and seamlock ship).
Repeating ONE action walks the player into a wall within two presses, after
which every press is free — so the pre-I-1 burn probe, which only ever
repeats one action, survives to its bound on every level and reports no cap,
although the game calls `lose()` on a real per-level allowance.

AUTHORED NUMBERS — `gen/tests/test_i1_instruments.py` asserts these exactly:

    level (1-indexed)                 :   1     2
    solver actions (ACTION4 x)        :   2     3
    budget.cap (effective moves only) :  40    70

The win check runs first; exhaustion is `lose()`. Row 0 is the meter.

BOARD: 8x8, camera 8x8. Walls frame the play strip x 1..6 / y 2..6. The player
starts at (3, 4) — two free cells above, below and to the left — and the goal
sits on the same row to the right.
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL, METER = 4, 9, 12, 7

BOARD = 8
METER_CELLS = 8
PLAYER_START = (3, 4)

# level index -> (goal x, per-level cap on EFFECTIVE moves).
# solver_i == goal_x - PLAYER_START[0].
LEVEL_PLAN = ((5, 40), (6, 70))

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


class FreeRefusalBoard(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="i1-free-refusal",
            levels=[_level(goal_x) for goal_x, _cap in LEVEL_PLAN],
            camera=Camera(width=BOARD, height=BOARD),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
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

        player = self.current_level.get_sprites_by_name("player")[0]
        before = (player.x, player.y)
        delta = DIRS.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)
        moved = (player.x, player.y) != before
        if moved:
            self._budget_used += 1  # only an EFFECTIVE move is charged
        self.complete_action()

        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()  # WIN CHECK FIRST
        elif self._budget_used >= self._level_cap:
            self.lose()
        self._paint_meter()
