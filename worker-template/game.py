"""THE game implementation file — one of the two files you may edit.

Replace this placeholder with exactly ONE `arcengine.ARCBaseGame` subclass
implementing the spec you were given. Contract highlights (AGENTS.md has
the full list):

- `super().__init__(game_id=..., levels=[...], camera=..., available_actions=[...])`
- game logic lives in `step()`; call `self.complete_action()` on every
  handler path
- level progression via `self.next_level()` ONLY; never touch
  `self._score` / `self._win_score`
- one grid orientation throughout; rendered frames are 64x64, colors 0-15

A fresh scaffold intentionally fails `make validate` until this file and
`solver.py` are implemented.
"""
