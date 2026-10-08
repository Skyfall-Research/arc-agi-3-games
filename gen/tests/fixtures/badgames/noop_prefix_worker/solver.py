"""BADGAME WORKER FIXTURE — seeded violation: a provably no-op solver prefix.

SEEDED VIOLATION (exactly one, check `solver.noop-prefix`): the winning line
opens with three ACTION1 (up) presses while the player stands at y=1, flush
against `wall_top`. `try_move` reverts every one of them, the game paints no
meter and keeps no counter, so the settled frame after each of the three is
BYTE-IDENTICAL to the RESET frame. The real line is the 10 moves that
follow. A baseline drawn off this 13-action line is inflated by 30% for
nothing.

CANON:
  design/architecture.md §3 "S2b — the intent verifier" — the solver-quality
  leg is "no-op-prefix detect · BFS spot-check small levels · lag/confirm
  modeled".
  spec-v0.3.md preamble (the five extensions over Tufa's design, D22) —
  "solver-quality bar (their padding)".
  design/architecture.md §3 S4 step 1 — the baseline is drawn from the
  length of the solver's real line, which is why padding it is a defect.
"""

from arcengine import ActionInput, GameAction

# 3 no-ops (blocked by wall_top at y=0) + the real 10-move route to (6,6).
PLANS = {
    0: ["ACTION1"] * 3 + ["ACTION4"] * 5 + ["ACTION2"] * 5,
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
