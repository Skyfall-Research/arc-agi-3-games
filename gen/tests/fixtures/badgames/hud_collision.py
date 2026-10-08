"""BADGAME FIXTURE — seeded violation: interface paint keyed to palette equality.

SEEDED VIOLATION (exactly one, check `static.palette-hud-collision`):
`RouteOverlay.render_interface` paints its route wherever the frame already
equals `TRAIL`, and `TRAIL` is also the colour of a real board object (the
`crate` sprite). Interfaces paint AFTER the board, so every crate pixel is
repainted `ROUTE` in the settled frame: the frame under-reports the true
board state. This is r11l's line painter (`frame==5 or frame==10` with 10 an
object colour), reproduced at minimum size.

The rest of the HUD is deliberately COMPLIANT so the seeded fact is isolated:
the status strip is keyed to GEOMETRY (row 63, a declared reserved row) and
no board sprite is placed in row 63.

CANON:
  spec-v0.3.md §2 FORBIDDEN #1 — "interface paint keyed to palette equality
  a real object can collide with (the frame lies)"; §2 REQUIRED row 7 —
  "Reserved HUD geometry declared (row 63 / row 0 / col 0 / custom);
  interfaces paint after the board and WILL overwrite it".
  design/objects/affordance-language.md §8 — "FORBIDDEN: interface paint
  conditions keyed to palette equality that a real object can collide with
  … Interface masks must key on geometry, never colour equality" (r11l).
  Engine: arcengine/camera.py `render` runs every interface over the 64x64
  output after the board is composited.

Everything else is deliberately clean: no negative mask pixels, no engine
click tags, no missing `complete_action()`, no level `data`, one level.
"""

import numpy as np
from arcengine import ARCBaseGame, Camera, GameAction, Level, RenderableUserDisplay, Sprite

PLAYER, GOAL = 9, 14
TRAIL = 10          # the crate's colour AND the overlay's match key — the collision
ROUTE = 13          # what the overlay paints
TRACK, SPENT = 1, 0  # status-strip indices, kept off the board
HUD_ROW = 63        # declared reserved geometry
STRIP_SPENT = 12    # how much of the strip reads "spent" (fixed: no hidden state)


class RouteOverlay(RenderableUserDisplay):
    """Status strip (geometry-keyed, fine) + route wash (colour-keyed, FORBIDDEN)."""

    def render_interface(self, frame: np.ndarray) -> np.ndarray:
        frame[HUD_ROW, :] = TRACK
        frame[HUD_ROW, :STRIP_SPENT] = SPENT
        # SEEDED VIOLATION: the route is painted wherever the FRAME equals
        # TRAIL, and the crate on the board is TRAIL — so the crate is
        # repainted as route and the settled frame lies about the board.
        frame[frame == TRAIL] = ROUTE
        return frame


def _level() -> Level:
    return Level(
        sprites=[
            Sprite([[TRAIL] * 3 for _ in range(3)], name="crate", x=20, y=20, collidable=False),
            Sprite([[GOAL] * 2 for _ in range(2)], name="goal", x=40, y=40, layer=1,
                   collidable=False),
            Sprite([[PLAYER] * 2 for _ in range(2)], name="player", x=4, y=4, layer=2),
        ]
    )


class HudCollision(ARCBaseGame):
    """Walk the player onto the goal with ACTION1-4; the HUD owns row 63."""

    def __init__(self) -> None:
        super().__init__(
            game_id="badgame-hud-collision",
            levels=[_level()],
            camera=Camera(width=64, height=64, interfaces=[RouteOverlay()]),
            available_actions=[1, 2, 3, 4],
        )

    def step(self) -> None:
        deltas = {
            GameAction.ACTION1: (0, -1),
            GameAction.ACTION2: (0, 1),
            GameAction.ACTION3: (-1, 0),
            GameAction.ACTION4: (1, 0),
        }
        delta = deltas.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)
        self.complete_action()

        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
