"""B2 contract battery: the game obeys the engine, not just the smoke test.

Three static bans over `game.py`/`solver.py` (score mutation, lifecycle
overrides, environment writes) and five runtime checks driven through the
real engine (R2-R5 conformance, W1 transition rendering, W2 latency).

The rules themselves live in `tests/_contracts.py` — one copy, shared with
the pipeline's calibration sweep over the 25 signed officials. Failures
here are game bugs; do not edit the tests (that is an edit-scope
violation and is detected).
"""

from __future__ import annotations

import pytest

from tests._contracts import (
    PERFORM_ACTION_TIME_BOUND_S,
    action_probe_violations,
    double_reset_violations,
    env_tampering_violations,
    lifecycle_override_violations,
    reset_restore_violations,
    reset_violations,
    score_mutation_violations,
)
from tests._harness import (
    WORKER_ROOT,
    load_game_class,
    load_solver_class,
    run_solver,
)

# The two files an implementing agent may write — the only ones worth scanning.
EDITABLE_SOURCES = ("game.py", "solver.py")


def _scan(check) -> list[str]:
    """Run one static check over both editable files, violations pooled."""
    found: list[str] = []
    for name in EDITABLE_SOURCES:
        path = WORKER_ROOT / name
        assert path.is_file(), f"missing worker file: {path}"
        found.extend(check(path.read_text(encoding="utf-8"), name))
    return found


# --------------------------------------------------------------------------
# static bans
# --------------------------------------------------------------------------


def test_static_score_ban():
    violations = _scan(score_mutation_violations)
    assert not violations, (
        "never write self._score / self._win_score — credit a solved level with "
        "self.next_level(), which also wins the game on the last level:\n"
        + "\n".join(violations)
    )


def test_static_lifecycle_ban():
    violations = _scan(lifecycle_override_violations)
    assert not violations, (
        "game logic belongs in step(); overriding the engine's action/reset/level "
        "lifecycle replaces the accounting the scoring reads:\n" + "\n".join(violations)
    )


def test_static_env_ban():
    violations = _scan(env_tampering_violations)
    assert not violations, (
        "a game must not write the process environment — ONLY_RESET_LEVELS alone "
        "changes what RESET means:\n" + "\n".join(violations)
    )


# --------------------------------------------------------------------------
# runtime conformance
# --------------------------------------------------------------------------


def test_reset_validity():
    violations = reset_violations(load_game_class())
    assert not violations, "RESET must open a playable, zeroed game:\n" + "\n".join(violations)


def test_action_probe_completes():
    violations, latencies = action_probe_violations(load_game_class())
    assert not violations, (
        "every declared action must complete and render:\n" + "\n".join(violations)
    )
    assert latencies, "the probe exercised no action — available_actions declared none"
    if PERFORM_ACTION_TIME_BOUND_S is not None:
        slowest = max(latencies)
        assert slowest < PERFORM_ACTION_TIME_BOUND_S, (
            f"slowest probed action took {slowest:.4f}s, bound is "
            f"{PERFORM_ACTION_TIME_BOUND_S}s"
        )


def test_reset_restores():
    violations = reset_restore_violations(load_game_class())
    assert not violations, (
        "RESET must restore the level's opening board:\n" + "\n".join(violations)
    )


def test_double_reset():
    violations = double_reset_violations(load_game_class())
    assert not violations, "RESET must be idempotent:\n" + "\n".join(violations)


# --------------------------------------------------------------------------
# W1 / W2 — measured on the solver's own winning run
# --------------------------------------------------------------------------


def test_level_transitions_render():
    """W1: a level transition the player can still act on must be VISIBLE.

    The engine queues `next_level()` and renders the new level on a second
    pass, so a mid-game transition returns >= 2 frames. The final level is
    the exception: `next_level()` calls `win()` inline, the render loop
    exits after one frame, and there is nothing left to play.
    """
    result = run_solver(load_game_class(), load_solver_class())
    assert result.transition_frame_counts, (
        "the solver completed no level — nothing to check (see test_scaffold.py)"
    )
    for completed, n_frames, was_terminal in result.transition_frame_counts:
        if was_terminal:
            continue
        assert n_frames >= 2, (
            f"the action crediting level {completed} rendered {n_frames} frame(s); a "
            "non-terminal transition must render the new level too (>= 2)"
        )


def test_solve_latency():
    """W2: no single action may blow the per-action wall."""
    if PERFORM_ACTION_TIME_BOUND_S is None:
        pytest.skip("latency bound not frozen yet")
    result = run_solver(load_game_class(), load_solver_class())
    slowest = max(result.action_process_times)
    assert slowest < PERFORM_ACTION_TIME_BOUND_S, (
        f"slowest action of the winning run took {slowest:.4f}s, bound is "
        f"{PERFORM_ACTION_TIME_BOUND_S}s"
    )
