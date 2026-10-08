"""BADGAME FIXTURE — seeded violation: a parsed level field with no reader.

SEEDED VIOLATION (exactly one, check `static.parsed-field-no-reader`): every
`Level` here ships `data={"goal_x": …, "drift_period": …}`. `on_set_level`
reads `goal_x` through `level.get_data("goal_x")` and places the goal with
it; `drift_period` is defined in the level data and read by NO code path in
this file — a parsed field with no consumer, indistinguishable from a
mechanic that was specified and never implemented.

CANON:
  design/architecture.md §3 "S2b — the intent verifier" — the static-pass
  list names `parsed-field-has-reader` alongside the mask reader scan.
  spec-v0.3.md §3 operational semantics — "a term is present iff the code
  implements it reachably; dead code is recorded, never counted"; §2 row 5
  is the same declared-reader doctrine applied to pixel data.

Everything else is deliberately clean: no negative mask pixels, no engine
click tags, no missing `complete_action()`, no camera interfaces, one level.
Level `data` itself is legitimate — only the unread key is the defect.
`on_set_level` is an engine hook ("use this to set level specific data"),
not one of the banned lifecycle overrides.
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL = 4, 9, 12

DIRS = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}


def _level(goal_x: int) -> Level:
    sprites = [
        Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
        Sprite([[WALL] * 8], name="wall_bottom", x=0, y=7),
        Sprite([[WALL]] * 6, name="wall_left", x=0, y=1),
        Sprite([[WALL]] * 6, name="wall_right", x=7, y=1),
        Sprite([[GOAL]], name="goal", x=goal_x, y=1, layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=1, y=1, layer=2),
    ]
    # SEEDED VIOLATION: "drift_period" is parsed into the level and never read.
    return Level(sprites=sprites, data={"goal_x": goal_x, "drift_period": 3})


class ReaderlessField(ARCBaseGame):
    """Move onto the goal with ACTION1-4; the goal column comes from level data."""

    def __init__(self) -> None:
        super().__init__(
            game_id="badgame-readerless-field",
            levels=[_level(6)],
            camera=Camera(width=8, height=8),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
        goal_x = level.get_data("goal_x")
        if goal_x is not None:
            goal = level.get_sprites_by_name("goal")[0]
            goal.set_position(int(goal_x), goal.y)

    def step(self) -> None:
        delta = DIRS.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)
        self.complete_action()

        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
