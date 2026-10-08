"""S4 FIXTURE — the GENEROUS-cap worker (B8). Engine-verified, minimal.

AUTHORED NUMBERS — `gen/tests/test_b8_baselines.py` asserts these exactly:

    level (1-indexed)  :   1     2     3     4
    solver actions     :   2     3     4     5
    per-level cap      : 120   180   240   300
    5 x (6 x solver_i) :  60    90   120   150   <- the largest D8 need

`g` is clipped at 6.0 (architecture §3 S4 step 2), so `baseline_i` can never
exceed `6 x solver_i`; every cap above is TWICE the resulting 5x-battery
requirement, which makes the hard cap-fit check (architecture §3 S4 step 4 +
D8) pass on the first draw for every seed. This worker is the
"verdict fit, redraws 0" case.

THE BUDGET TRIPLE — spec-v0.3 §2 REQUIRED row 3, the 25/25 official pattern:
  * an edge-anchored meter EXISTS: row 0 (the top edge) is reserved HUD
    geometry (REQUIRED row 7) holding eight `meter_<k>` cells that empty
    left-to-right as the level's budget burns down. They are
    `collidable=False`, so they never enter the board's collision space, and
    they paint palette index 7, which no on-board object uses (REQUIRED
    row 8: meter indices off-board).
  * exhaustion is wired to `lose()` WITH THE WIN CHECK FIRST: the action
    that lands on the goal calls `next_level()` and never `lose()`, even
    when it is the action that empties the meter — the winning move is free.
  * the cap accommodates the solver's line plus the g-margin (table above);
    never a tn36-style baseline > cap.

DECLARED REFUSAL SEMANTICS — spec §2 FORBIDDEN ("mixed accidental refusal
semantics; charge-or-signal by RULE, never by accident"): a move blocked by
a wall is CHARGED against the budget. `wall_top` sits directly above the
player's start cell on every level, so ACTION1 (up) at a level's start is
always a charged refusal that neither transitions a level nor ends the game
— that is the action an S4 cap probe burns.

BOARD: 8x8, the camera upscales 8x to 64x64. Row 0 = meter, row 1 and row 7
= walls, columns 0 and 7 = walls, play strip x 1..6 / y 2..6. The player
starts at (1,2) on every level and the goal sits on the same row, so each
solver line is a run of ACTION4 (right). Levels differ only in goal distance
and cap — all that S4 reads.
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL, METER = 4, 9, 12, 7

BOARD = 8
METER_CELLS = 8
PLAYER_START = (1, 2)

# level index -> (goal x, per-level action cap). solver_i == goal_x - 1.
LEVEL_PLAN = ((3, 120), (4, 180), (5, 240), (6, 300))

DIRS = {
    GameAction.ACTION1: (0, -1),  # up   — blocked by wall_top from the start cell
    GameAction.ACTION2: (0, 1),   # down
    GameAction.ACTION3: (-1, 0),  # left
    GameAction.ACTION4: (1, 0),   # right
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
        Sprite([[GOAL]], name="goal", x=goal_x, y=2, layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=PLAYER_START[0], y=PLAYER_START[1], layer=2),
    ]
    return Level(sprites=sprites)


class CappedGenerousBoard(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="s4-capped-generous",
            levels=[_level(goal_x) for goal_x, _cap in LEVEL_PLAN],
            camera=Camera(width=BOARD, height=BOARD),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
        """The budget is PER LEVEL: the engine calls this on RESET and on
        every level transition, and the meter restarts with it."""
        self._budget_used = 0

    @property
    def _level_cap(self) -> int:
        return LEVEL_PLAN[self.level_index][1]

    def _paint_meter(self) -> None:
        cap = self._level_cap
        remaining = max(0, cap - self._budget_used)
        lit = -(-remaining * METER_CELLS // cap)  # ceil: >0 remaining keeps a cell lit
        for k in range(METER_CELLS):
            for sprite in self.current_level.get_sprites_by_name(f"meter_{k}"):
                sprite.set_visible(k < lit)

    def step(self) -> None:
        # RESET runs step() too (base_game.perform_action drives the frame loop
        # for it), and the engine's own accounting does not count it
        # (`_set_action` skips `_action_count` for RESET) — so neither does the
        # budget. A cap is a count of GAME actions (D8).
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
