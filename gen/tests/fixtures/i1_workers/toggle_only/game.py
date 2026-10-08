"""I-1 FIXTURE — an allowance only a hidden-state witness can attribute.

The fourth contract-I-1 worker, shaped like conduit-watch: the allowance
charges EFFECTIVE actions only, and at the moment it is exhausted the one
effective action available is the one being played — every other action is a
free no-op (or the win). So the substitution test is uninformative there, and
the allowance is attributed by the hidden-state witness instead: the same
action met the same visible board one period earlier and survived.

    ACTION5  arm      effective iff disarmed (charged)
    ACTION7  disarm   effective iff armed    (charged)
    ACTION1  fire     armed -> WIN; disarmed -> a free no-op

AUTHORED NUMBERS — `gen/tests/test_i1_instruments.py` asserts these exactly:

    level (1-indexed)                    :   1     2
    solver actions (ACTION5, ACTION1)    :   2     2
    budget.cap (effective actions only)  :  40    60

Every single repeated action is free after at most one press, so the pre-I-1
burn probe survives to its bound and reports no cap. The meter (row 0, eight
cells) is coarse, as a meter is: it moves every cap/8 charged actions.

BOARD: 8x8, camera 8x8; a lamp at (3, 4) shows armed (11) or disarmed (3).
"""

import numpy as np
from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, LAMP_OFF, LAMP_ON, METER = 4, 3, 11, 7

BOARD = 8
METER_CELLS = 8

# level index -> per-level cap on EFFECTIVE actions.
LEVEL_PLAN = (40, 60)


def _level() -> Level:
    sprites = [
        Sprite([[METER]], name=f"meter_{k}", x=k, y=0, layer=1, collidable=False)
        for k in range(METER_CELLS)
    ]
    sprites += [
        Sprite([[WALL] * BOARD], name="wall_top", x=0, y=1),
        Sprite([[WALL] * BOARD], name="wall_bottom", x=0, y=7),
        Sprite([[LAMP_OFF]], name="lamp", x=3, y=4, layer=1, collidable=False),
    ]
    return Level(sprites=sprites)


class ToggleOnlyBoard(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="i1-toggle-only",
            levels=[_level() for _cap in LEVEL_PLAN],
            camera=Camera(width=BOARD, height=BOARD),
            available_actions=[1, 5, 7],
        )

    def on_set_level(self, level: Level) -> None:
        self._budget_used = 0
        self._armed = False

    @property
    def _level_cap(self) -> int:
        return LEVEL_PLAN[self.level_index]

    def _paint(self) -> None:
        cap = self._level_cap
        remaining = max(0, cap - self._budget_used)
        lit = -(-remaining * METER_CELLS // cap)
        for k in range(METER_CELLS):
            for sprite in self.current_level.get_sprites_by_name(f"meter_{k}"):
                sprite.set_visible(k < lit)
        lamp = self.current_level.get_sprites_by_name("lamp")[0]
        lamp.pixels = np.array([[LAMP_ON if self._armed else LAMP_OFF]], dtype=np.int8)

    def step(self) -> None:
        action = self.action.id
        if action == GameAction.RESET:
            self.complete_action()
            self._paint()
            return

        if action == GameAction.ACTION1 and self._armed:
            self.complete_action()
            self.next_level()  # the win: fire while armed
            return
        effective = False
        if action == GameAction.ACTION5 and not self._armed:
            self._armed, effective = True, True
        elif action == GameAction.ACTION7 and self._armed:
            self._armed, effective = False, True
        if effective:
            self._budget_used += 1
        self.complete_action()
        if self._budget_used >= self._level_cap:
            self.lose()
        self._paint()
