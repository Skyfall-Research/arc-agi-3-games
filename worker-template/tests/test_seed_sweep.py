"""THE SEED SWEEP: the packager's layout-seed validation, run IN this loop.

The packager (S6) replays a finished game on a LIST of layout seeds — the
authored default plus derived extras — and refuses the whole game if any one
of them cannot be won. That verdict used to arrive long after the build loop
had closed, so a solver that only solved its own authored layout looked
finished and was rejected at packaging, twice.

The pipeline writes that exact seed list to a sibling of this worker
(`<worker>.seeds.json`). This file drives every seed in it the way the
packager does, so a seed-reject is a RED `make validate` here instead:

  * EXPLICIT construction — `Game(layout_seed=s)` and `Solver(layout_seed=s)`
    for every seed INCLUDING the authored default. No-argument construction is
    a different code path, and it is the one that hid this defect before.
  * THE PACKAGER'S ACTION BOUND — `S6_MAX_ACTIONS` (600), not the scaffold
    battery's 1200. A winning line that needs 700 actions passes
    `test_scaffold.py` and is still refused at packaging.
  * THE PACKAGER'S PASS RULE — WIN, with every authored level credited
    through `next_level()`.

WHEN THESE TESTS SKIP, and why that is a missing premise rather than a pass:
  * there is no sidecar beside this worker — a worker instantiated before this
    mechanism existed, a hand-made tree, or a copy made for the blind audit;
  * `game.py` defines no module-level `build_layout(seed)`, so the
    layout-from-seed contract this sweep enforces does not apply to it.

IF A SEED IS RED, the bug is in `game.py` or `solver.py`:
  * `build_layout(seed)` must be a PURE function of its argument that produces
    a solvable level set for ANY seed — not only for the authored one;
  * `Solver(layout_seed=s)` receives the SAME seed and must DERIVE its line
    from it. A solver that replays the authored layout's line is the exact
    defect this file catches.
Do not edit the tests to make them pass — that is an edit-scope violation and
it is detected.
"""

from __future__ import annotations

import pytest
from arcengine import GameState

from tests._harness import (
    S6_MAX_ACTIONS,
    SEEDS_SIDECAR,
    game_class_in,
    load_game_module,
    load_solver_class,
    read_seed_plan,
    run_solver,
)

# Read ONCE, at collection: the seed list decides how many cases there are.
_PLAN = read_seed_plan()
_SEEDS = () if _PLAN is None else _PLAN.seeds
_BOUND = S6_MAX_ACTIONS if _PLAN is None else _PLAN.max_actions

_NO_SIDECAR = (
    f"no seed sidecar at {SEEDS_SIDECAR} — nothing told this worker which seeds the "
    "packager will validate it at"
)


def _seed_params() -> list:
    """One case per seed; one explicitly skipped case when there are none.

    An empty `parametrize` would also skip, with a reason that says nothing.
    A sidecar that EXISTS but is unusable is reported by the well-formedness
    test below, which is red while these skip — never a silent pass.
    """
    if _SEEDS:
        return [pytest.param(seed, id=str(seed)) for seed in _SEEDS]
    reason = _NO_SIDECAR if _PLAN is None else (
        f"unusable seed sidecar ({_PLAN.error}) — see test_seed_sidecar_is_well_formed"
    )
    return [pytest.param(None, marks=pytest.mark.skip(reason=reason))]


def _build_layout_or_skip():
    """`(module, build_layout)` for this worker, or a skip when §7 is absent."""
    module = load_game_module()
    build = getattr(module, "build_layout", None)
    if not callable(build):
        pytest.skip(
            "game.py defines no module-level build_layout(seed) — the layout-from-seed "
            "contract this sweep enforces does not apply to this worker"
        )
    return module, build


def test_seed_sidecar_is_well_formed():
    """A sidecar that cannot be used is LOUD, never a quiet skip."""
    if _PLAN is None:
        pytest.skip(_NO_SIDECAR)
    assert _PLAN.error is None, _PLAN.error
    assert _PLAN.seeds, f"{_PLAN.path} carries no seeds"
    if _PLAN.count is not None:
        assert _PLAN.count == len(_PLAN.seeds), (
            f"{_PLAN.path} says count={_PLAN.count} but lists {len(_PLAN.seeds)} seed(s) — "
            "the count is what the packager's config asks for"
        )
    assert _PLAN.max_actions == S6_MAX_ACTIONS, (
        f"{_PLAN.path} records max_actions={_PLAN.max_actions} but this scaffold mirrors the "
        f"packager's bound as {S6_MAX_ACTIONS} — the sidecar and the scaffold came from "
        "different generations of the pipeline, so this sweep would not reproduce the "
        "packager's verdict. Re-run the worker resync."
    )


def test_authored_default_is_the_sidecar_seed():
    """The game's baked-in default IS the spec's `layout.seed`.

    The packager validates the seed the GAME records (it reads `layout_seed`
    off a no-argument instance); the sidecar's first seed is the one the SPEC
    authored. A game that bakes a different default is validated at a seed this
    sweep never drives, so the two must agree.
    """
    if _PLAN is None:
        pytest.skip(_NO_SIDECAR)
    if _PLAN.authored_seed is None:
        pytest.skip(f"{_PLAN.path} records no authored default seed")
    module, _build = _build_layout_or_skip()
    game = game_class_in(module)()
    recorded = getattr(game, "layout_seed", None)
    assert recorded == _PLAN.authored_seed, (
        f"Game() records layout_seed={recorded!r} but the authored default is "
        f"{_PLAN.authored_seed!r} (the spec's game.layout.seed). `Game(layout_seed=None)` must "
        "mean THAT seed: it is the first seed the packager validates, and the levels the spec "
        "describes are its levels."
    )


@pytest.mark.parametrize("seed", _seed_params())
def test_solver_wins_every_validation_seed(seed):
    """Every seed the packager will replay, driven here exactly as it drives."""
    module, _build = _build_layout_or_skip()
    game_cls = game_class_in(module)
    solver_cls = load_solver_class()

    result = run_solver(game_cls, solver_cls, max_actions=_BOUND, layout_seed=seed)

    assert result.final_state == GameState.WIN, (
        f"layout_seed={seed}: expected WIN within {_BOUND} actions (the packager's bound), got "
        f"{result.final_state.name} after {len(result.actions)} action(s) at level "
        f"{result.levels_completed}/{result.win_levels}. The solver must derive its line from "
        "the seed it is handed, and every seed's layout must be winnable."
    )
    assert result.win_levels >= 1, f"layout_seed={seed}: win_levels must be at least 1"
    assert result.levels_completed == result.win_levels, (
        f"layout_seed={seed}: WIN with {result.levels_completed}/{result.win_levels} levels "
        "credited — the packager requires every authored level to go through next_level()"
    )
