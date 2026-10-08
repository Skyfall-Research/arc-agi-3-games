"""Scripted solver for the S5 crash fixture — it cannot win, by design.

The line it would play is two presses of ACTION4 per level (the goal sits two
cells to the player's right on all three levels), which is exactly the line a
perfect battery policy plays. `game.py`'s CRASH_AFTER = 4 raises on the
fourth post-RESET action, so this solver completes level 1 and then faults on
level 2. That is the point of the fixture: S4 is never run on it (its cap
probe would trip the fault), and its baselines are hand-written in
`gen/tests/test_b9_battery.py` in S4's own frozen `metadata.json` shape.
"""

from arcengine import ActionInput, GameAction

ACTIONS_PER_LEVEL = 2


class Solver:
    def reset(self) -> None:
        self._cursor: dict[int, int] = {}

    def next_action(self, frame) -> "ActionInput | None":
        level = int(frame.levels_completed)
        index = self._cursor.get(level, 0)
        if index >= ACTIONS_PER_LEVEL:
            return None
        self._cursor[level] = index + 1
        return ActionInput(id=GameAction.ACTION4)
