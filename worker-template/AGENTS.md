# Agent notes for this worker repo

This is an isolated worker repo. Treat the current directory as the repo
root; do not consult any parent checkout.

## Allowed edit scope

- `game.py` — the game implementation
- `solver.py` — the matching solver

**Nothing else.** Do not edit, delete, or add any other file — the
scaffold is hash-manifested and `make validate` fails on any out-of-scope
change. Implement exactly one game (one `ARCBaseGame` subclass in
`game.py`) and one solver (the `Solver` class in `solver.py`).

## Engine score contract

When writing `game.py`:

1. Never mutate `self._score` or `self._win_score` directly.
2. Use a game-specific variable for internal points if needed.
3. Use `self.next_level()` for solved-level progression — it credits the
   level and wins the game automatically on the last level.

Reward and level accounting downstream read the engine's own
`levels_completed / win_levels`; bypassing them breaks scoring silently.

## Engine facts that bite (verified against arcengine 0.9.3)

- `step()` MUST call `self.complete_action()` on **every** handler path —
  the engine keeps calling `step()` and rendering frames until the action
  completes, and errors out after 1000 frames.
- `ActionInput(id=..., data={"x": ..., "y": ...})` — coordinates go in
  `data`; bare `x=`/`y=` kwargs are silently discarded.
- `GameAction(3)` raises — enum members are looked up by NAME
  (`GameAction.ACTION3`), never by value.
- Level completion is the frame's `levels_completed` field, never
  `game._current_level_index`; `next_level()` takes effect on the NEXT
  frame (the engine renders the transition).
- The settled frame after an action is `frame_data.frame[-1]`, not
  `frame[0]` — one action may render several frames.
- Game logic runs in ONE grid orientation of your choosing; keep it
  consistent everywhere (no `[::-1]` flips inside game logic).

## Validation

Run, from this repo root:

    make validate

It checks the edit scope, lints `game.py`/`solver.py`, and runs the test
battery (`tests/`). If validation fails, fix the implementation and rerun
until it passes. Do not modify the tests to make them pass — that is an
edit-scope violation and is detected.

The battery includes the **seed sweep** (`tests/test_seed_sweep.py`): the
packager replays this game on a list of layout seeds and refuses the whole
game if any one of them cannot be won, and that list is now driven here, on
every run. A red seed means `build_layout(seed)` does not produce a solvable
level set for that seed, or the solver is not deriving its line from the seed
it was handed — `Solver(layout_seed=s)` gets the SAME seed the game got, and
replaying the authored layout's line is exactly what this catches.
