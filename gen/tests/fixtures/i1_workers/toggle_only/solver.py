"""Scripted deterministic solver for the I-1 toggle-only fixture.

    level (1-indexed) :  1   2
    actions           :  2   2     (ACTION5 arm, ACTION1 fire — total 4)
"""

from arcengine import ActionInput, GameAction

PLANS = {
    0: ["ACTION5", "ACTION1"],
    1: ["ACTION5", "ACTION1"],
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
