"""Toy game for the B1 scaffold acceptance run — NOT a generated game.

Two levels on an 8x8 board (camera upscales 8x to 64x64): move the player
dot onto the goal tile with ACTION1-4 (up/down/left/right). Level 2 adds a
wall bar that blocks the level-1 route, so the solver must take a
different path (proves collision + per-level plans). Reaching the goal
calls next_level(); the engine wins the game on the last level.
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL = 4, 9, 12

DIRS = {
    GameAction.ACTION1: (0, -1),  # up
    GameAction.ACTION2: (0, 1),   # down
    GameAction.ACTION3: (-1, 0),  # left
    GameAction.ACTION4: (1, 0),   # right
}


def _border():
    return [
        Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
        Sprite([[WALL] * 8], name="wall_bottom", x=0, y=7),
        Sprite([[WALL]] * 6, name="wall_left", x=0, y=1),
        Sprite([[WALL]] * 6, name="wall_right", x=7, y=1),
    ]


def _level(goal_xy, extra_walls=()):
    gx, gy = goal_xy
    sprites = _border() + list(extra_walls) + [
        Sprite([[GOAL]], name="goal", x=gx, y=gy, layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=1, y=1, layer=2),
    ]
    return Level(sprites=sprites)


class ToyScaffold(ARCBaseGame):
    def __init__(self) -> None:
        levels = [
            _level((6, 6)),
            _level((6, 6), extra_walls=[Sprite([[WALL]] * 4, name="wall_mid", x=4, y=1)]),
        ]
        super().__init__(
            game_id="toy-scaffold-01",
            levels=levels,
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
