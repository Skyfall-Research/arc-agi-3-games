"""BADGAME WORKER FIXTURE — the GAME half; the seeded violation is in solver.py.

This game is deliberately CLEAN on every static rule: every path calls
`complete_action()` exactly once, no negative mask pixels, no engine click
tags, no level `data`, no camera interfaces. It exists only so `solver.py` has
something to pad: a blocked move against `wall_top` changes nothing at all,
so a leading run of ACTION1 is a provably frame-identical prefix.

Board: 8x8 (the camera upscales 8x to 64x64), player at (1,1), goal at
(6,6), a solid border. ACTION1-4 are up/down/left/right; reaching the goal
calls `next_level()`, which wins the game on this single level.
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL = 4, 9, 12

DIRS = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}


def _level() -> Level:
    sprites = [
        Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
        Sprite([[WALL] * 8], name="wall_bottom", x=0, y=7),
        Sprite([[WALL]] * 6, name="wall_left", x=0, y=1),
        Sprite([[WALL]] * 6, name="wall_right", x=7, y=1),
        Sprite([[GOAL]], name="goal", x=6, y=6, layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=1, y=1, layer=2),
    ]
    return Level(sprites=sprites)


class NoopPrefixBoard(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="badgame-noop-prefix",
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
