"""BADGAME FIXTURE — seeded violation: a handler path with no `complete_action()`.

SEEDED VIOLATION (exactly one, check `static.complete-action`): the ACTION5
branch of `step()` returns on its first pass WITHOUT calling
`complete_action()`. `ARCBaseGame.perform_action` loops
`while not is_action_complete(): step()`, so the engine re-runs the handler
and the charge counter is incremented TWICE for one action — the sc25 latent
double-charge, verbatim.

CANON:
  spec-v0.3.md §2 FORBIDDEN — "leaving a handler without `complete_action()`
  (the engine re-runs the action — double-charge)".
  design/objects/affordance-language.md §8 — same rule, with sc25 named.
  Engine: arcengine/base_game.py `perform_action` (the step loop) +
  `complete_action` / `is_action_complete`.

Everything else is deliberately clean: no negative mask pixels, no engine
click tags, no level `data`, no camera interfaces, one level, four movement
actions that all complete exactly once. (The literal tokens the other checks
scan for are kept OUT of this file, prose included, so exactly one check can
possibly fire.)
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


class MissingCompleteAction(ARCBaseGame):
    """Move onto the goal with ACTION1-4; ACTION5 spends one charge."""

    def __init__(self) -> None:
        super().__init__(
            game_id="badgame-missing-complete-action",
            levels=[_level()],
            camera=Camera(width=8, height=8),
            available_actions=[1, 2, 3, 4, 5],
        )
        self._charges = 0

    def step(self) -> None:
        if self.action.id is GameAction.ACTION5:
            self._charges += 1
            if self._charges % 2 == 1:
                # SEEDED VIOLATION: this path leaves the handler without
                # complete_action(). The engine re-enters step() and charges
                # a second time for the same action.
                return
            self.complete_action()
            return

        delta = DIRS.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)
        self.complete_action()

        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
