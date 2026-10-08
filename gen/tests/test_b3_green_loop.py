"""B3 acceptance: the CODED validate-until-green loop + scaffold repair.

Run: .venv/bin/python -m pytest gen/tests/test_b3_green_loop.py -v

Agent sessions are INJECTED fakes — closures that log their call and edit
the real worker dir, exactly where a real `claude`/`codex` session would.
No CLI is ever spawned. Everything downstream of the session is real: real
instantiated workers, the real pipeline scope check and repair, and a real
`make validate` subprocess per attempt (offline, ~0.5 s each).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from gen import backends as backends_mod
from gen import worker as worker_mod
from gen.config import load_config
from gen.s2_implement import (
    ATTEMPTS_SUFFIX,
    REJECT_SUFFIX,
    REJECT_VERDICT,
    REPORT_SUFFIX,
    green_loop,
    sidecar,
)
from gen.worker import (
    IGNORED_DIRS,
    MANIFEST_NAME,
    instantiate_worker,
    repair_worker,
    verify_worker,
)

TOY = Path(__file__).resolve().parent / "toy_worker"

# The canonical seeded bug: give level 1 the level-0 route. The wall at x=4
# blocks it, so the run ends NOT_FINISHED and the battery says "expected WIN".
LEVEL1_PLAN = '1: ["ACTION2"] * 5 + ["ACTION4"] * 5'
LEVEL0_ROUTE = '1: ["ACTION4"] * 5 + ["ACTION2"] * 5'


def _cfg(cap: int) -> dict:
    """Minimal config: with an injected runner, the cap is all green_loop reads."""
    return {"implementer": {"max_green_attempts": cap}}


def _worker(tmp_path: Path, name: str) -> Path:
    """A fresh real worker. Placeholder game.py — red until a fake implements it."""
    dest = tmp_path / name
    instantiate_worker(dest)
    return dest.resolve()


def _install_toy(worker: Path) -> None:
    shutil.copy2(TOY / "game.py", worker / "game.py")
    shutil.copy2(TOY / "solver.py", worker / "solver.py")


def _seed_bug(worker: Path) -> None:
    source = (TOY / "solver.py").read_text(encoding="utf-8")
    bugged = source.replace(LEVEL1_PLAN, LEVEL0_ROUTE)
    assert bugged != source, "seeded-bug anchor not found in the toy solver"
    (worker / "solver.py").write_text(bugged, encoding="utf-8")


def _fake_runner(log: list[dict], on_call=None, *, session_id: str = "fake-{n}"):
    """Stand-in for one agent session: log the call, optionally edit the
    worker (what an agent does), return a session dict."""

    def runner(prompt: str, *, cwd: Path, resume_id: str | None):
        log.append({"prompt": prompt, "cwd": Path(cwd), "resume_id": resume_id})
        n = len(log)
        if on_call is not None:
            on_call(n, Path(cwd))
        return {
            "session_id": session_id.format(n=n),
            "usd_cost": 0.01,
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_s": 0.0,
            "error": None,
        }

    return runner


def _rows(worker: Path) -> list[dict]:
    text = sidecar(worker, ATTEMPTS_SUFFIX).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_reject_at_cap(tmp_path):
    """No-op sessions on a placeholder worker: 12 red attempts, then reject-to-S1."""
    worker = _worker(tmp_path, "w-reject")
    cfg = load_config("config/b001-pilot.yaml")
    assert cfg["implementer"]["max_green_attempts"] == 12, "pilot cap drifted from 12"
    log: list[dict] = []

    report = green_loop(worker, "implement the spec", cfg, session_runner=_fake_runner(log))

    assert report.green is False
    assert report.attempts == 12, "the cap must come from implementer.max_green_attempts"
    assert len(log) == 12
    rows = _rows(worker)
    assert [row["index"] for row in rows] == list(range(1, 13))
    assert not any(row["green"] for row in rows)

    reject = json.loads(sidecar(worker, REJECT_SUFFIX).read_text(encoding="utf-8"))
    assert reject["verdict"] == REJECT_VERDICT == "reject-to-S1"
    assert reject["attempts"] == 12
    assert reject["last_validate_tail"].strip(), "reject must carry the last validate tail"
    assert len(reject["records"]) == 12
    assert not sidecar(worker, REPORT_SUFFIX).exists(), "a reject must not write a green report"


def test_green_at_attempt_3(tmp_path):
    worker = _worker(tmp_path, "w-green3")
    log: list[dict] = []

    def on_call(n: int, cwd: Path) -> None:
        if n == 3:
            _install_toy(cwd)

    report = green_loop(
        worker, "implement the spec", _cfg(12), session_runner=_fake_runner(log, on_call)
    )

    assert report.green is True
    assert report.attempts == 3 and len(log) == 3
    assert [r.green for r in report.records] == [False, False, True]
    rows = _rows(worker)
    assert len(rows) == 3
    assert rows[-1]["green"] is True and rows[-1]["validate_exit"] == 0

    written = json.loads(sidecar(worker, REPORT_SUFFIX).read_text(encoding="utf-8"))
    assert written["green"] is True and written["attempts"] == 3
    assert written["worker"] == str(worker)
    assert not sidecar(worker, REJECT_SUFFIX).exists()
    assert verify_worker(worker) == [], "a green worker must still be scope-clean"


def test_loop_artifacts_live_beside_the_worker(tmp_path):
    """The ledger and verdict are siblings, never inside the worker: the
    scaffold scope check fails on ANY file it did not hash at instantiation,
    so an in-worker ledger would make green unreachable after attempt 1."""
    worker = _worker(tmp_path, "w-sidecar")
    log: list[dict] = []
    report = green_loop(
        worker,
        "implement the spec",
        _cfg(3),
        session_runner=_fake_runner(log, lambda n, cwd: _install_toy(cwd)),
    )

    assert report.green is True and report.attempts == 1
    for suffix in (ATTEMPTS_SUFFIX, REPORT_SUFFIX):
        assert sidecar(worker, suffix).is_file(), f"{suffix} must be written beside the worker"
        assert not (worker / suffix.lstrip(".")).exists(), f"{suffix} leaked into the worker"
    assert verify_worker(worker) == []


def test_seeded_bug_then_fix(tmp_path):
    """The canonical seeded bug goes red with 'expected WIN', and the tail is
    what the next prompt carries back to the agent."""
    worker = _worker(tmp_path, "w-bug")
    _install_toy(worker)
    _seed_bug(worker)
    log: list[dict] = []

    def on_call(n: int, cwd: Path) -> None:
        if n == 2:
            shutil.copy2(TOY / "solver.py", cwd / "solver.py")

    report = green_loop(
        worker, "implement the spec", _cfg(12), session_runner=_fake_runner(log, on_call)
    )

    assert report.records[0].green is False
    assert "expected WIN" in report.records[0].validate_tail
    assert report.green is True and report.attempts == 2
    assert log[0]["prompt"] == "implement the spec"
    assert "expected WIN" in log[1]["prompt"], "the fix prompt must carry the validate tail"
    assert "make validate" in log[1]["prompt"]


def test_scope_violation_repaired(tmp_path):
    """An out-of-scope edit is reverted, reported in the record, and named in
    the next prompt's scope note."""
    worker = _worker(tmp_path, "w-scope")
    log: list[dict] = []

    def on_call(n: int, cwd: Path) -> None:
        if n == 1:
            target = cwd / "tests/test_scaffold.py"
            target.write_text(
                target.read_text(encoding="utf-8") + "\n# agent tampered here\n",
                encoding="utf-8",
            )
        elif n == 2:
            _install_toy(cwd)

    report = green_loop(
        worker, "implement the spec", _cfg(12), session_runner=_fake_runner(log, on_call)
    )

    assert report.records[0].scope_repairs == ["restored tests/test_scaffold.py"]
    assert report.records[1].scope_repairs == []
    assert "Out-of-scope changes were reverted by the pipeline" in log[1]["prompt"]
    assert "restored tests/test_scaffold.py" in log[1]["prompt"]
    assert report.green is True and report.attempts == 2
    assert verify_worker(worker) == []


def test_resume_id_threading(tmp_path):
    worker = _worker(tmp_path, "w-resume")
    log: list[dict] = []

    def on_call(n: int, cwd: Path) -> None:
        if n == 2:
            _install_toy(cwd)

    report = green_loop(
        worker,
        "implement the spec",
        _cfg(12),
        session_runner=_fake_runner(log, on_call, session_id="s{n}"),
    )

    assert report.attempts == 2 and report.green is True
    assert log[0]["resume_id"] is None, "the first session starts fresh"
    assert log[1]["resume_id"] == "s1", "later attempts resume the previous session"
    assert log[0]["cwd"] == worker, "sessions run IN the worker dir"


def test_cost_totals(tmp_path):
    worker = _worker(tmp_path, "w-cost")
    log: list[dict] = []
    report = green_loop(
        worker,
        "implement the spec",
        _cfg(12),
        session_runner=_fake_runner(log, lambda n, cwd: _install_toy(cwd) if n == 2 else None),
    )

    assert report.attempts == 2
    assert report.total_usd == pytest.approx(0.02)
    assert report.total_tokens_in == 200
    assert report.total_tokens_out == 100
    assert report.wall_s > 0


def test_session_error_recorded(tmp_path):
    """A session that raises is recorded and the loop keeps going — the agent
    may have edited files before it died."""

    class FakeDriverError(RuntimeError):
        pass

    worker = _worker(tmp_path, "w-error")
    log: list[dict] = []

    def on_call(n: int, cwd: Path) -> None:
        if n == 1:
            raise FakeDriverError("[localclaude] exit 1: OAuth session expired")
        _install_toy(cwd)

    report = green_loop(
        worker, "implement the spec", _cfg(12), session_runner=_fake_runner(log, on_call)
    )

    error = report.records[0].session["error"]
    assert "FakeDriverError" in error and "OAuth session expired" in error
    assert "session_id" not in report.records[0].session
    assert report.green is True and report.attempts == 2
    assert report.total_usd == pytest.approx(0.01), "an errored session contributes no cost"
    assert _rows(worker)[0]["session"]["error"] == error


def test_malformed_session_return_raises(tmp_path):
    """A runner returning the wrong SHAPE is a wiring bug: it must raise, not
    get recorded as a session error and burn the whole cap."""
    worker = _worker(tmp_path, "w-shape")

    def bad_runner(prompt, *, cwd, resume_id):
        return "I implemented the game!"

    with pytest.raises(TypeError, match="expected a dict or an object with .to_record"):
        green_loop(worker, "implement the spec", _cfg(12), session_runner=bad_runner)


def test_repair_worker_unit(tmp_path):
    """Direct: tampered scaffold file + stray + broken worker.mk + tampered
    in-worker manifest, all restored, editable files untouched."""
    worker = _worker(tmp_path, "w-repair")
    _install_toy(worker)
    game_before = (worker / "game.py").read_text(encoding="utf-8")

    scaffold = worker / "tests/test_scaffold.py"
    scaffold.write_text(scaffold.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    (worker / "helpers.py").write_text("# stray\n", encoding="utf-8")
    (worker / "worker.mk").write_text("PY := /usr/bin/python3\n", encoding="utf-8")
    (worker / MANIFEST_NAME).write_text('{"editable": [], "files": {}}\n', encoding="utf-8")

    repairs = repair_worker(worker)

    assert verify_worker(worker) == []
    assert sorted(repairs) == sorted(
        [
            f"restored {MANIFEST_NAME}",
            "restored tests/test_scaffold.py",
            "restored worker.mk",
            "deleted stray helpers.py",
        ]
    )
    assert not (worker / "helpers.py").exists()
    assert (worker / "game.py").read_text(encoding="utf-8") == game_before, (
        "repair must never touch the editable files"
    )
    sibling = sidecar(worker, ".manifest.json")
    assert (worker / MANIFEST_NAME).read_text(encoding="utf-8") == sibling.read_text(
        encoding="utf-8"
    )
    scope = subprocess.run(
        ["make", "scope"], cwd=worker, capture_output=True, text=True, timeout=60, check=False
    )
    assert scope.returncode == 0, scope.stdout + scope.stderr


def test_repair_worker_is_a_noop_on_a_clean_worker(tmp_path):
    worker = _worker(tmp_path, "w-clean")
    _install_toy(worker)
    assert repair_worker(worker) == []


def test_repair_refuses_a_drifted_template(tmp_path, monkeypatch):
    """Silently repairing from a template that changed since instantiation
    would produce a worker that validates but does NOT match its manifest."""
    worker = _worker(tmp_path, "w-drift")
    drifted = tmp_path / "template-copy"
    shutil.copytree(
        worker_mod.TEMPLATE_DIR, drifted, ignore=shutil.ignore_patterns(*IGNORED_DIRS)
    )
    target = drifted / "tests/test_scaffold.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# upstream drift\n", encoding="utf-8")
    monkeypatch.setattr(worker_mod, "TEMPLATE_DIR", drifted)

    (worker / "tests/test_scaffold.py").unlink()
    with pytest.raises(RuntimeError, match="template drift") as excinfo:
        repair_worker(worker)
    assert "tests/test_scaffold.py" in str(excinfo.value)
    assert "expects" in str(excinfo.value), "the raise must print both hashes"


# --- driver session argv: tools vs allowedTools ------------------------------
# Two different flags from two different parameters (the B5 driver lesson:
# `--allowedTools` only auto-APPROVES, `--tools` LIMITS the surface). B7
# review found `tools` shadowed by the allowed-tools local, which emitted
# `--tools` on EVERY session with the wrong value; these pin the seam.


def _fake_claude_run(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, driver, timeout_s, cwd=None):
        calls.append(list(cmd))
        payload = {
            "result": "ok", "is_error": False, "total_cost_usd": 0.0,
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "session_id": "sess-1",
        }
        proc = subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
        return proc, 0.01

    monkeypatch.setattr(backends_mod, "_run", fake_run)
    return calls


def test_session_allowed_tools_alone_emits_no_tools_flag(monkeypatch, tmp_path):
    calls = _fake_claude_run(monkeypatch)
    backends_mod.LocalClaudeDriver().session(
        "p", cwd=tmp_path, allowed_tools=("Edit", "Write")
    )
    (cmd,) = calls
    assert "--tools" not in cmd, "tools=None must not limit the tool surface"
    at = cmd.index("--allowedTools")
    assert cmd[at + 1 : at + 3] == ["Edit", "Write"]


def test_session_tools_parameter_reaches_the_tools_flag(monkeypatch, tmp_path):
    calls = _fake_claude_run(monkeypatch)
    backends_mod.LocalClaudeDriver().session(
        "p", cwd=tmp_path, tools=("Read",), allowed_tools=("Read", "Glob")
    )
    (cmd,) = calls
    assert cmd[cmd.index("--tools") + 1] == "Read"
    at = cmd.index("--allowedTools")
    assert cmd[at + 1 : at + 3] == ["Read", "Glob"]


def test_session_default_allowed_tools_when_none(monkeypatch, tmp_path):
    calls = _fake_claude_run(monkeypatch)
    backends_mod.LocalClaudeDriver().session("p", cwd=tmp_path)
    (cmd,) = calls
    assert "--tools" not in cmd
    at = cmd.index("--allowedTools")
    expected = list(backends_mod.DEFAULT_S2_ALLOWED_TOOLS)
    assert cmd[at + 1 : at + 1 + len(expected)] == expected
