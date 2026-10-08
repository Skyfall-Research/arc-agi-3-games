"""Scripted deterministic solver for the I-1 repeat-rule fixture.

    level (1-indexed) :  1   2
    actions           :  2   3     (total line = 5)

Each level's line is ACTION4 (right) presses from (3, 4) to the goal.
"""

from arcengine import ActionInput, GameAction

PLANS = {
    0: ["ACTION4"] * 2,
    1: ["ACTION4"] * 3,
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
