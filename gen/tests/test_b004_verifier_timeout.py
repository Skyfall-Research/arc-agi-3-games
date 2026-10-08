"""b004 finding #2 (2026-09-28): the verifier session obeys the policy ceiling.

LEAD-AUTHORED (not a blind lane): a three-line seam pin, written after the
first live wave-3 verifier round outgrew the hardcoded 1800s default and the
resulting DriverError crashed the orchestrator. `run_agent_pass` builds its
session kwargs by hand (read-only tools, verifier model) and never consulted
`get_session_policy`, so C-B's `backends.<driver>.session.timeout_s` knob
reached S2 but not S2b. The seam forwards EXACTLY `timeout_s` — the verifier
must never inherit S2's edit-mode policy keys (permission_mode,
allowed_tools), which these pins also assert.

The crash-vs-block routing of a verify-stage DriverError is a SEPARATE flagged
contract, not covered here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gen.config import load_config
from gen.frames import ClickCell, FrameCapture, FrameRecord
from gen.s3_verify import run_agent_pass

GAME_PY = '"""Synthetic fixture game - never played, only staged and cited."""\n'
SOLVER_PY = '"""Synthetic fixture solver - never played, only staged and cited."""\n'


class _Boom(Exception):
    """Sentinel: the session was invoked; nothing after it matters."""


class _KwargsProbe:
    """Driver seam that records `session()` kwargs and refuses to continue."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[dict] = []

    def session(self, prompt: str, **kwargs):
        self.calls.append(dict(kwargs))
        raise _Boom


def _grid(fill: int) -> tuple:
    return tuple(tuple(fill for _ in range(4)) for _ in range(4))


def _capture() -> FrameCapture:
    return FrameCapture(
        game_id="synthetic-b004-verifier-timeout",
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


def _invoke(cfg: dict, root: Path, driver: _KwargsProbe) -> dict:
    worker = root / "worker"
    worker.mkdir(parents=True)
    (worker / "game.py").write_text(GAME_PY, encoding="utf-8")
    (worker / "solver.py").write_text(SOLVER_PY, encoding="utf-8")
    out_dir = root / "out"
    out_dir.mkdir(parents=True)
    with pytest.raises(_Boom):
        run_agent_pass(cfg, worker, _capture(), out_dir=out_dir, driver=driver)
    assert len(driver.calls) == 1, "the probe must have been invoked exactly once"
    return driver.calls[0]


def test_unconfigured_verifier_session_keeps_todays_1800(tmp_path: Path) -> None:
    """b001's config has no session block: the policy default IS the old value."""
    cfg = load_config("config/b001-pilot.yaml")
    kwargs = _invoke(cfg, tmp_path, _KwargsProbe("localclaude"))
    assert kwargs["timeout_s"] == 1800.0


def test_armed_config_reaches_the_verifier_session(tmp_path: Path) -> None:
    cfg = load_config("config/b004-validation.yaml")
    kwargs = _invoke(cfg, tmp_path, _KwargsProbe("localclaude"))
    assert kwargs["timeout_s"] == 3600


def test_only_timeout_crosses_never_s2_edit_policy(tmp_path: Path) -> None:
    """The verifier stays read-only: no permission_mode, no S2 allowed_tools."""
    cfg = load_config("config/b004-validation.yaml")
    kwargs = _invoke(cfg, tmp_path, _KwargsProbe("localclaude"))
    assert "permission_mode" not in kwargs
    assert "effort" not in kwargs
    assert kwargs["tools"] == kwargs["allowed_tools"]
    assert "Edit" not in kwargs["tools"] and "Write" not in kwargs["tools"]


def test_unknown_driver_name_gets_no_timeout_kwarg(tmp_path: Path) -> None:
    """Injected test fakes with their own names keep their exact old call shape."""
    cfg = load_config("config/b001-pilot.yaml")
    kwargs = _invoke(cfg, tmp_path, _KwargsProbe("fake-test-driver"))
    assert "timeout_s" not in kwargs
