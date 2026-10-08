"""BADGAME FIXTURE — seeded violation: an untruthful `sys_click` tag.

SEEDED VIOLATION (exactly one, check `static.sys-click-truthful`):
`inert_panel` carries the `sys_click` tag, so the engine advertises a click
action on it — `base_game._get_valid_clickable_actions` builds its list from
`current_level.get_sprites_by_tag("sys_click")` — but NO code path here ever
handles it. The ACTION6 handler acts only when the clicked cell resolves to
the sprite named `switch`; a click on `inert_panel` is charged and does
nothing. The engine's click list (and every RL consumer reading it) is lied
to. `_is_sprite_clickable_now` is NOT overridden, so the tag facts are the
whole truth about clickability here.

CANON:
  spec-v0.3.md §2 REQUIRED row 2 — "`sys_click` tags are truthful — always
  (the engine's click-action list and RL consumers read them); *visual*
  marking of clickability is a knob."
  Engine: arcengine/base_game.py `_get_valid_clickable_actions` (the
  `sys_click` tag scan) and `_is_sprite_clickable_now` (the override seam).

Everything else is deliberately clean: no negative mask pixels, no missing
`complete_action()`, no level `data`, no camera interfaces, one level.
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

FRAME, SWITCH, PANEL = 4, 11, 6


def _level() -> Level:
    sprites = [
        Sprite([[FRAME] * 8 for _ in range(8)], name="backdrop", x=0, y=0, collidable=False),
        Sprite(
            [[SWITCH, SWITCH], [SWITCH, SWITCH]],
            name="switch",
            x=1,
            y=3,
            layer=1,
            tags=["sys_click"],
        ),
        # SEEDED VIOLATION: tagged clickable, handled nowhere.
        Sprite(
            [[PANEL, PANEL], [PANEL, PANEL]],
            name="inert_panel",
            x=5,
            y=3,
            layer=1,
            tags=["sys_click"],
        ),
    ]
    return Level(sprites=sprites)


class FalseSysClick(ARCBaseGame):
    """Click the switch to finish; the second tagged panel does nothing."""

    def __init__(self) -> None:
        super().__init__(
            game_id="badgame-false-sys-click",
            levels=[_level()],
            camera=Camera(width=8, height=8),
            available_actions=[6],
        )

    def step(self) -> None:
        if self.action.id is GameAction.ACTION6:
            cell = self.camera.display_to_grid(
                int(self.action.data.get("x", 0)), int(self.action.data.get("y", 0))
            )
            if cell is not None:
                hit = self.current_level.get_sprite_at(cell[0], cell[1])
                if hit is not None and hit.name == "switch":
                    self.complete_action()
                    self.next_level()
                    return
        self.complete_action()
