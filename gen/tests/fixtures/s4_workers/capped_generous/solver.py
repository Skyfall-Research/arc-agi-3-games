"""Scripted deterministic solver for the S4 generous-cap fixture.

AUTHORED SOLVER LENGTHS — asserted verbatim by gen/tests/test_b8_baselines.py:

    level (1-indexed) :  1   2   3   4
    actions           :  2   3   4   5     (total line = 14)

The player starts at (1,2) and the goal sits at (goal_x, 2), so each level's
line is `goal_x - 1` presses of ACTION4 (right); the last press of each level
lands on the goal and calls `next_level()` — the transition action belongs to
the level it completes (architecture §3 S4 step 1). No padding, no no-op
prefix: every action moves the player one cell.
"""

from arcengine import ActionInput, GameAction

PLANS = {
    0: ["ACTION4"] * 2,
    1: ["ACTION4"] * 3,
    2: ["ACTION4"] * 4,
    3: ["ACTION4"] * 5,
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
