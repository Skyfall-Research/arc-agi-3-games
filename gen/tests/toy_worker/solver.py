"""Scripted deterministic solver for the toy scaffold game.

Level 0: right x5 to (6,1), down x5 to (6,6).
Level 1: the wall bar at x=4 blocks row 1, so go down x5 to (1,6) first,
then right x5 to (6,6).
"""

from arcengine import ActionInput, GameAction

PLANS = {
    0: ["ACTION4"] * 5 + ["ACTION2"] * 5,
    1: ["ACTION2"] * 5 + ["ACTION4"] * 5,
}


class Solver:
    def reset(self) -> None:
        self._cursor = {level: 0 for level in PLANS}

    def next_action(self, frame) -> "ActionInput | None":
        plan = PLANS.get(frame.levels_completed)
        if plan is None:
            return None
        index = self._cursor[frame.levels_completed]
        if index >= len(plan):
            return None
        self._cursor[frame.levels_completed] = index + 1
        return ActionInput(id=GameAction[plan[index]])
