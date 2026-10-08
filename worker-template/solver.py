"""THE solver file — one of the two files you may edit.

Implement a deterministic `Solver` for the game in `game.py`:

    class Solver:
        def reset(self) -> None:
            '''Fresh episode state.'''

        def next_action(self, frame) -> ActionInput | None:
            '''frame is arcengine FrameData (settled board = frame.frame[-1],
            level = frame.levels_completed). Return the next ActionInput,
            or None to give up. MUST be deterministic — the pipeline
            replays it and compares runs byte-for-byte.'''

The solver must reach state WIN within the action cap (tests/ enforces
1200) with every level credited through `next_level()`.
"""

class Solver:
    def reset(self) -> None:
        pass

    def next_action(self, frame):
        raise NotImplementedError("implement the solver for game.py")
