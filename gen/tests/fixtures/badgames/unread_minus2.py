"""BADGAME FIXTURE — seeded violation: a `-2` pixel that nothing reads.

SEEDED VIOLATION (exactly one, check `static.unread-minus2`): the `crate`
sprite ships four `-2` corner pixels and NO code in this file reads `-2` —
no mask threshold, no comparison, no tag scan, no second collision rule.
The engine's own defaults render `>= 0` and pixel-collide `!= -1`, so the
corners are inert dead weight: they cannot be recovered from trajectories
and no reader is declared for them.

CANON:
  spec-v0.3.md §2 REQUIRED row 5 — "Every `-2` pixel ships with a declared
  reader (which mask consumes it); `-2` nothing reads is forbidden dead
  weight" — and §2 FORBIDDEN #4, "unread `-2`".
  design/objects/affordance-language.md §8 — "`-2` semantics are per-game,
  not global … REQUIRED: a generated game states which mask reads every -2
  it ships; -2 without a reader is FORBIDDEN".

Everything else is deliberately clean: no engine click tags, no missing
`complete_action()`, no level `data`, no camera interfaces, one level.
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL, CRATE = 4, 9, 12, 7

DIRS = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}

# SEEDED VIOLATION: the -2 corners have no reader anywhere in this file.
CRATE_PIXELS = [
    [-2, CRATE, -2],
    [CRATE, CRATE, CRATE],
    [-2, CRATE, -2],
]


def _level() -> Level:
    sprites = [
        Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
        Sprite([[WALL] * 8], name="wall_bottom", x=0, y=7),
        Sprite([[WALL]] * 6, name="wall_left", x=0, y=1),
        Sprite([[WALL]] * 6, name="wall_right", x=7, y=1),
        Sprite(CRATE_PIXELS, name="crate", x=3, y=3, layer=1, collidable=False),
        Sprite([[GOAL]], name="goal", x=6, y=1, layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=1, y=1, layer=2),
    ]
    return Level(sprites=sprites)


class UnreadMinusTwo(ARCBaseGame):
    """Move onto the goal with ACTION1-4; the crate is scenery."""

    def __init__(self) -> None:
        super().__init__(
            game_id="badgame-unread-minus2",
            levels=[_level()],
            camera=Camera(width=8, height=8),
            available_actions=[1, 2, 3, 4],
        )

    def step(self) -> None:
        delta = DIRS.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)
        self.complete_action()

        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
