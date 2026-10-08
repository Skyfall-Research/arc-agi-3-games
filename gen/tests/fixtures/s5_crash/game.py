"""S5 FIXTURE — the CRASHING worker (B9). Engine-verified, minimal.

AUTHORED NUMBERS — `gen/tests/test_b9_battery.py` asserts these exactly:

    levels                    : 3   (1-indexed 1, 2, 3)
    solver actions per level  : 2   2   2
    CRASH_AFTER               : 4   <- the 4th post-RESET action raises

The B9 contract's fixture clause: "the game raises RuntimeError inside
`step()` after a fixed number of post-RESET actions (RESET itself and the
first action must succeed)". The counter is CUMULATIVE over the pass, not
per level, and it is cleared on RESET only — the engine calls `step()` for
RESET too (`base_game.perform_action` drives the frame loop for it), which is
the `fixtures/s4_workers/` lesson: a counting game must not charge on RESET.

WHY 4 AND NOT 2 — the contract also asks for "rows up to the crash kept".
With the goal two cells to the player's right on every level, a perfect
policy spends actions 1-2 completing level 1, action 3 moving on level 2, and
action 4 raises. So a battery pass yields a finished level-1 row BEFORE the
crash lands on level 2, and the "partial rows kept" claim is testable rather
than vacuous. RESET and the first action succeed, as required.

The raised message is short and starts with the fixture's own name, so any
reasonable `crash.error_tail` (str(exc) or a traceback tail) carries the
marker `s5-crash`.

BOARD: 8x8, the camera upscales 8x to 64x64. Row 1 and row 7 are walls,
columns 0 and 7 are walls, the play strip is x 1..6 / y 2..6. The player
starts at (1, 2) on every level and the goal sits at (3, 2), so each level's
line is two presses of ACTION4 (right). There is no budget, no meter and no
`lose()` call: this fixture exists to fault, nothing else. Its baselines are
hand-written in the test (S4 is never run on it — the cap probe would trip
the fault), in the frozen `metadata.json` shape S4 itself writes.
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL = 4, 9, 12

BOARD = 8
PLAYER_START = (1, 2)
GOAL_X = 3
LEVELS = 3

#: post-RESET action index (1-based) whose `step()` raises.
CRASH_AFTER = 4

#: the fault text; the leading token is the marker the tests look for.
CRASH_MESSAGE = "s5-crash fixture: deliberate fault at action 4"

DIRS = {
    GameAction.ACTION1: (0, -1),  # up    — into wall_top from the start cell
    GameAction.ACTION2: (0, 1),   # down
    GameAction.ACTION3: (-1, 0),  # left  — into wall_left from the start cell
    GameAction.ACTION4: (1, 0),   # right — the solver's direction
}


def _level() -> Level:
    """A fresh level; every call builds its own sprites (never shared)."""
    return Level(
        sprites=[
            Sprite([[WALL] * BOARD], name="wall_top", x=0, y=1),
            Sprite([[WALL] * BOARD], name="wall_bottom", x=0, y=7),
            Sprite([[WALL]] * 5, name="wall_left", x=0, y=2),
            Sprite([[WALL]] * 5, name="wall_right", x=7, y=2),
            Sprite([[GOAL]], name="goal", x=GOAL_X, y=2, layer=1, collidable=False),
            Sprite(
                [[PLAYER]],
                name="player",
                x=PLAYER_START[0],
                y=PLAYER_START[1],
                layer=2,
            ),
        ]
    )


class CrashingBoard(ARCBaseGame):
    # Class-level default so the counter exists even if the engine reaches
    # step() before __init__ finishes; RESET re-zeroes it per pass.
    _actions_since_reset = 0

    def __init__(self) -> None:
        super().__init__(
            game_id="s5-crash-board",
            levels=[_level() for _ in range(LEVELS)],
            camera=Camera(width=BOARD, height=BOARD),
            available_actions=[1, 2, 3, 4],
        )
        self._actions_since_reset = 0

    def step(self) -> None:
        if self.action.id == GameAction.RESET:
            self._actions_since_reset = 0
            self.complete_action()
            return

        self._actions_since_reset += 1
        if self._actions_since_reset >= CRASH_AFTER:
            # Raised BEFORE complete_action(): the action never lands, and the
            # exception leaves perform_action() for the battery to catch.
            raise RuntimeError(CRASH_MESSAGE)

        delta = DIRS.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)
        self.complete_action()

        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
