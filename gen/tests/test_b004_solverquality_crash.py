"""b004 finding #3 (2026-09-28): a worker solver crash is a verdict, not ours.

LEAD-AUTHORED. The verify stage's solver-quality probe is the one place the
pipeline drives worker code in-process, and b004 crashed the orchestrator
there twice (an IndexError, then a ValueError raised inside the game's own
solver.py mid-drive). `run_solver_quality` must convert ANY worker-code
exception into the existing `solver`-leg fail plumbing — which the verdict
maps to a reject with the solver-only route — and never let it escape.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from gen.frames import ClickCell, FrameCapture, FrameRecord
from gen.s3_static import run_solver_quality

TOY = Path(__file__).resolve().parent / "toy_worker"

CRASHING_SOLVER = '''"""A solver that imports cleanly and dies mid-drive."""

from arcengine import ActionInput, GameAction


class Solver:
    def __init__(self):
        self._queue = [("up", 1, 2), ("down", 3)]

    def next_action(self, frame_data):
        verb, lane, row = self._queue.pop(0)
        return ActionInput(id=GameAction.ACTION1)
'''


def _grid(fill: int) -> tuple:
    return tuple(tuple(fill for _ in range(4)) for _ in range(4))


def _capture() -> FrameCapture:
    return FrameCapture(
        game_id="synthetic-solver-crash",
        source="solver",
        records=(
            FrameRecord(
                label="reset", seq=0, levels_completed=0, state="NOT_FINISHED", grid=_grid(0)
            ),
            FrameRecord(label="final", seq=1, levels_completed=1, state="WIN", grid=_grid(7)),
        ),
        click_cells=(ClickCell(level_index=0, x=1, y=1, sprite_name="fixture_switch"),),
        available_action_ids=(1, 2, 3, 4, 5, 6),
        solver_actions=("ACTION1", "ACTION1"),
        levels_completed=1,
        win=True,
    )


def _worker_with_crashing_solver(tmp_path: Path) -> Path:
    worker = tmp_path / "worker"
    worker.mkdir()
    shutil.copy(TOY / "game.py", worker / "game.py")
    (worker / "solver.py").write_text(CRASHING_SOLVER, encoding="utf-8")
    return worker


def test_worker_solver_crash_is_contained_and_fails_the_solver_leg(tmp_path) -> None:
    """The b004 replay: ValueError inside solver.py -> three results, no raise."""
    worker = _worker_with_crashing_solver(tmp_path)
    results = run_solver_quality(worker, _capture(), bfs_cell_cap=400)

    by_id = {r.check_id: r for r in results}
    assert set(by_id) == {
        "solver.noop-prefix",
        "solver.bfs-spot-check",
        "solver.lag-confirm-modeled",
    }
    assert all(r.leg == "solver" for r in results)

    failing = by_id["solver.noop-prefix"]
    assert failing.status == "fail"
    # The note must name the exception class, the crash site inside the
    # WORKER's file, and say what it means for the verdict.
    assert "ValueError" in failing.note
    assert "solver.py" in failing.note
    assert "cannot be judged" in failing.note

    for check_id in ("solver.bfs-spot-check", "solver.lag-confirm-modeled"):
        assert by_id[check_id].status == "premise-not-met"


def test_healthy_toy_worker_still_gets_the_real_checks(tmp_path) -> None:
    """The containment must not swallow the working path: the untouched toy
    worker drives clean and none of the three results is the crash triad."""
    worker = tmp_path / "worker"
    worker.mkdir()
    shutil.copy(TOY / "game.py", worker / "game.py")
    shutil.copy(TOY / "solver.py", worker / "solver.py")
    results = run_solver_quality(worker, _capture(), bfs_cell_cap=400)
    assert len(results) == 3
    assert not any("cannot be judged" in (r.note or "") for r in results)
