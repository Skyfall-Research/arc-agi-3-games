"""B1 scaffold battery: the game loads, plays, and the solver wins it.

This is the smoke tier — the full engine-conformance and REQUIRED-gate
battery (calibrated against the 25 officials) lands with B2 and extends
this directory.
"""

from __future__ import annotations

import numpy as np
from arcengine import GameState

from tests._harness import (
    MAX_ACTIONS,
    load_game_class,
    load_solver_class,
    run_solver,
)


def test_game_class_loads_and_instantiates():
    game_cls = load_game_class()
    game = game_cls()
    assert isinstance(game.game_id, str) and game.game_id.strip(), (
        "game_id must be a non-empty string"
    )


def test_solver_reaches_win_with_all_levels_credited():
    result = run_solver(load_game_class(), load_solver_class())
    assert result.final_state == GameState.WIN, (
        f"expected WIN within {MAX_ACTIONS} actions, got {result.final_state.name} "
        f"after {len(result.actions)} action(s) at level "
        f"{result.levels_completed}/{result.win_levels}"
    )
    assert result.win_levels >= 1, "win_levels must be at least 1"
    assert result.levels_completed == result.win_levels, (
        f"WIN with {result.levels_completed}/{result.win_levels} levels credited — "
        "every level must go through next_level()"
    )
    assert result.transitions == result.win_levels, (
        f"observed {result.transitions} level transition(s) for "
        f"{result.win_levels} level(s)"
    )


def test_solver_is_deterministic():
    game_cls, solver_cls = load_game_class(), load_solver_class()
    first = run_solver(game_cls, solver_cls)
    second = run_solver(game_cls, solver_cls)
    assert first.actions == second.actions, "solver action sequence differs between runs"
    assert first.final_settled_frame is not None and second.final_settled_frame is not None
    assert np.array_equal(first.final_settled_frame, second.final_settled_frame), (
        "final settled frame differs between identical runs"
    )
