"""B004 S2-timeout contract (C-A mission reissue · C-B timeout knob · C-C honest error).

Run: .venv/bin/python -m pytest gen/tests/test_b004_s2timeout.py -v

BLIND LANE. Written from the frozen contract alone by an agent that never read
the implementation diff; the implementation landed in a parallel lane and the
lead merges. Nothing here may be weakened to make a missing symbol pass — a
failure on `BARE_RETRY_TEMPLATE` / `worker_is_bare` / `timeout_s` before the
merge is the expected pre-state, not a test bug.

T1  attempt-1 passthrough — the mission goes to the agent verbatim (unchanged).
T2  written-worker retry — prompt 2 is EXACTLY today's FIX_PROMPT_TEMPLATE bytes.
T3  bare-worker retry — the b004 replay: a timeout that wrote nothing consumes
    its attempt AND re-issues the full mission (C-A).
T4  `worker_is_bare` unit — only the provably untouched scaffold is "bare".
T5  `timeout_s` policy default + config flow (C-B).
T6  `timeout_s` invalid values are loud (C-B).
T7  the honest empty-partials timeout message (C-C).

THREE RULES THIS FILE KEEPS.

  * NO network, NO real `claude`/`codex` CLI. Sessions are injected fake
    runners (the `test_b3_green_loop` rig, reused), drivers are captured
    stand-ins, and the one `_run` test fakes the subprocess layer itself.
    Everything downstream of the session is real: real instantiated workers
    and a real offline `make validate` per attempt.
  * NO assertion against `git show HEAD:` or any diff. Every expectation is
    computed from the LIVE module constants (`FIX_PROMPT_TEMPLATE`,
    `BARE_RETRY_TEMPLATE`, `SESSION_TIMEOUT_S`) at call time, so a stale HEAD
    can never make a pin pass or fail for the wrong reason.
  * The two NEW `gen.s2_implement` names are imported at FUNCTION level
    (`_bare_retry_template` / `_worker_is_bare` below). That still pins them as
    module-level public names — the import statement is the pin — while
    keeping a pre-merge ImportError inside the tests that own it instead of
    erroring the whole module's collection.
"""

from __future__ import annotations

import json
import re
import shutil
import string
import subprocess
from pathlib import Path

import pytest

from gen import backends as backends_mod
from gen.backends import (
    SESSION_POLICY_DEFAULTS,
    SESSION_TIMEOUT_S,
    CodexDriver,
    DriverError,
    LocalClaudeDriver,
    get_session_policy,
)
from gen.config import load_config
from gen.s2_implement import (
    ATTEMPTS_SUFFIX,
    FIX_PROMPT_TEMPLATE,
    _default_session_runner,
    green_loop,
    sidecar,
)
from gen.worker import instantiate_worker

TOY = Path(__file__).resolve().parent / "toy_worker"

MANIFEST_SUFFIX = ".manifest.json"

# A mission distinctive enough that "the full mission text is in prompt 2" is
# a real assertion and not a coincidence of shared boilerplate.
MISSION = (
    "MISSION b004-blind: implement the spec below.\n"
    "SPEC ANCHOR alpha-7: the ward opens only after both gates latch.\n"
    "Write game.py and solver.py until `make validate` is green.\n"
)


# --- the new names, imported where they are used -----------------------------


def _bare_retry_template() -> str:
    """C-A.2: `BARE_RETRY_TEMPLATE` is a module-level constant of s2_implement."""
    from gen.s2_implement import BARE_RETRY_TEMPLATE

    return BARE_RETRY_TEMPLATE


def _worker_is_bare(worker_dir: Path) -> bool:
    """C-A.1: `worker_is_bare(worker_dir) -> bool` is public in s2_implement."""
    from gen.s2_implement import worker_is_bare

    return worker_is_bare(worker_dir)


# --- rig (the test_b3_green_loop pattern, reused) ----------------------------


def _cfg(cap: int) -> dict:
    """Minimal config: with an injected runner, the cap is all green_loop reads."""
    return {"implementer": {"max_green_attempts": cap}}


def _worker(tmp_path: Path, name: str) -> Path:
    """A fresh real worker: placeholder game.py/solver.py, red until implemented."""
    dest = tmp_path / name
    instantiate_worker(dest)
    return dest.resolve()


def _install_toy(worker: Path) -> None:
    shutil.copy2(TOY / "game.py", worker / "game.py")
    shutil.copy2(TOY / "solver.py", worker / "solver.py")


def _install_toy_game_only(worker: Path) -> None:
    """A WRITTEN worker that is still red: game.py implemented, solver.py not."""
    shutil.copy2(TOY / "game.py", worker / "game.py")


def _fake_runner(log: list[dict], on_call=None, *, session_id: str = "fake-{n}"):
    """One agent session: log the call, optionally edit the worker, return a record."""

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


def _skeleton_match(template: str, text: str) -> dict[str, str] | None:
    """Parse `text` against `template`'s literal skeleton.

    Every literal byte of the template must be present, in order; each `{field}`
    becomes a capture group. A match means "these bytes came out of THIS
    template"; the captures are then asserted one by one. Returns None when the
    skeleton no longer matches at all (the loud, diagnosable failure).
    """
    pattern = ""
    for literal, field, _spec, _conv in string.Formatter().parse(template):
        pattern += re.escape(literal)
        if field:
            pattern += f"(?P<{field}>.*?)"
    matched = re.fullmatch(pattern, text, re.DOTALL)
    return matched.groupdict() if matched else None


# --- T1 ----------------------------------------------------------------------


def test_t1_attempt_one_prompt_is_the_mission_verbatim(tmp_path):
    """Attempt 1 is untouched by this contract: the payload goes through as-is."""
    worker = _worker(tmp_path, "w-t1")
    log: list[dict] = []

    report = green_loop(
        worker,
        MISSION,
        _cfg(2),
        session_runner=_fake_runner(log, lambda n, cwd: _install_toy(cwd)),
    )

    assert report.green is True and report.attempts == 1
    assert len(log) == 1
    assert log[0]["prompt"] == MISSION, "attempt 1 must carry the mission payload verbatim"
    assert log[0]["resume_id"] is None, "the first session starts fresh"
    assert log[0]["cwd"] == worker, "sessions run IN the worker dir"


# --- T2 ----------------------------------------------------------------------


def test_t2_written_worker_retry_is_todays_fix_prompt_bytes(tmp_path):
    """A worker whose editable pair was TOUCHED keeps today's fix-prompt path.

    Attempt 1 writes game.py (so the worker is not bare) and validate stays red;
    prompt 2 must be exactly `FIX_PROMPT_TEMPLATE.format(...)` — expectation
    computed from the live constant, never a copied literal.
    """
    worker = _worker(tmp_path, "w-t2")
    log: list[dict] = []

    def on_call(n: int, cwd: Path) -> None:
        if n == 1:
            _install_toy_game_only(cwd)
        else:
            _install_toy(cwd)

    report = green_loop(worker, MISSION, _cfg(2), session_runner=_fake_runner(log, on_call))

    assert report.attempts == 2 and len(log) == 2
    assert report.records[0].green is False, "attempt 1 must be red for a retry to happen"
    assert report.records[0].scope_repairs == [], "editable-only edits are in scope"

    tail = report.records[0].validate_tail
    assert tail.strip(), "a red attempt must record a validate tail"

    prompt2 = log[1]["prompt"]
    fields = _skeleton_match(FIX_PROMPT_TEMPLATE, prompt2)
    assert fields is not None, (
        "prompt 2 for a WRITTEN worker must still come out of FIX_PROMPT_TEMPLATE "
        f"byte for byte. Got:\n{prompt2!r}"
    )
    assert fields["attempt"] == "2"
    assert fields["cap"] == "2"
    assert fields["validate_tail"] == tail
    assert "Out-of-scope changes were reverted by the pipeline" not in prompt2, (
        "nothing went out of scope, so the scope note must stay quiet"
    )

    expected = FIX_PROMPT_TEMPLATE.format(
        attempt=2, cap=2, validate_tail=tail, scope_note=fields["scope_note"]
    )
    assert prompt2 == expected, "the written-worker retry prompt is byte-pinned to today's"
    assert MISSION not in prompt2, (
        "today's fix prompt does NOT re-issue the mission; only the bare path may"
    )


# --- T3 ----------------------------------------------------------------------


def test_t3_bare_worker_retry_reissues_the_full_mission(tmp_path):
    """THE b004 REPLAY. Attempt 1 dies on the 1800s timeout having written
    nothing; the attempt is consumed (b002 contract 2, unchanged) and attempt 2
    is handed the header, the validate tail AND the full mission (C-A.3)."""
    worker = _worker(tmp_path, "w-t3")
    log: list[dict] = []

    def on_call(n: int, cwd: Path) -> None:
        if n == 1:
            raise DriverError(
                "[localclaude] timed out after 1800s. "
                "partial stdout: <empty> | partial stderr: <empty>"
            )
        _install_toy(cwd)

    report = green_loop(worker, MISSION, _cfg(2), session_runner=_fake_runner(log, on_call))

    # the timeout consumed attempt 1 and the loop kept going
    assert len(log) == 2, "a timed-out session must not be retried for free"
    assert report.attempts == 2 and report.green is True
    rows = _rows(worker)
    assert [row["index"] for row in rows] == [1, 2], "attempt row 1 must be recorded"
    assert "timed out after 1800s" in rows[0]["session"]["error"]

    scaffold_game = (worker / "game.py").read_text(encoding="utf-8")
    assert scaffold_game, "sanity: the worker still has a game.py"

    tail = report.records[0].validate_tail
    assert tail.strip(), "the bare attempt still runs validate and records its tail"

    bare_template = _bare_retry_template()  # fetched first: pre-merge this is the ImportError
    prompt2 = log[1]["prompt"]
    assert "Attempt 2 of" in prompt2, "(a) the attempt header"
    assert tail.strip() in prompt2, "(b) the validate tail travels with the reissue"
    assert MISSION in prompt2, "(c) the FULL mission is re-issued to a bare worker"

    fix_bytes = FIX_PROMPT_TEMPLATE.format(
        attempt=2, cap=2, validate_tail=tail, scope_note=""
    )
    assert prompt2 != fix_bytes, "a bare worker must NOT get the bare fix template"

    expected = bare_template.format(
        attempt=2, cap=2, validate_tail=tail, scope_note="", mission=MISSION
    )
    assert prompt2 == expected, "the bare retry prompt is BARE_RETRY_TEMPLATE, byte for byte"


# --- T4 ----------------------------------------------------------------------


def test_t4_worker_is_bare_only_on_the_untouched_scaffold(tmp_path):
    """Narrow by design: True iff EVERY editable file exists and still hashes to
    its scaffold entry in the sibling manifest. Any write, any deletion → False."""
    fresh = _worker(tmp_path, "w-t4-fresh")
    assert _worker_is_bare(fresh) is True, "a freshly instantiated worker is bare"

    touched_game = _worker(tmp_path, "w-t4-game")
    target = touched_game / "game.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# agent wrote here\n", "utf-8")
    assert _worker_is_bare(touched_game) is False, "a touched game.py is not bare"

    touched_solver = _worker(tmp_path, "w-t4-solver")
    target = touched_solver / "solver.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n# agent wrote here\n", "utf-8")
    assert _worker_is_bare(touched_solver) is False, "a touched solver.py is not bare"

    deleted = _worker(tmp_path, "w-t4-deleted")
    (deleted / "game.py").unlink()
    assert _worker_is_bare(deleted) is False, "a MISSING editable file is not bare either"

    # the sibling manifest is the source of truth, and it is the untouched pair
    # that the fresh case matched (guard against a vacuous True on empty lists)
    manifest = json.loads(sidecar(fresh, MANIFEST_SUFFIX).read_text(encoding="utf-8"))
    assert sorted(manifest["editable"]) == ["game.py", "solver.py"]
    assert all(name in manifest["files"] for name in manifest["editable"])


def test_t4b_worker_is_bare_fails_loud_without_a_manifest(tmp_path):
    """C-A.1: a missing/malformed manifest RAISES — it never answers True/False.

    INTERPRETATION (contract silent on the type): the contract says only "fail
    loud (raise)", so this pins the raise, not a class.
    """
    worker = _worker(tmp_path, "w-t4-nomanifest")
    sidecar(worker, MANIFEST_SUFFIX).unlink()

    # broad on purpose: the contract pins THAT it raises, not which class
    with pytest.raises(Exception):  # noqa: B017
        _worker_is_bare(worker)


# --- T5 ----------------------------------------------------------------------


class _CapturingDriver:
    """A driver that records the session kwargs and never spawns anything."""

    def __init__(self, name: str = "localclaude") -> None:
        self.name = name
        self.calls: list[dict] = []

    def session(self, prompt: str, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        return {
            "session_id": "capture-1",
            "usd_cost": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "duration_s": 0.0,
            "error": None,
        }


def test_t5a_both_drivers_default_timeout_s_to_the_module_constant():
    """C-B.1: symmetric defaults. An unconfigured run keeps today's 1800s."""
    assert SESSION_TIMEOUT_S == 1800.0
    for driver in ("localclaude", "codex"):
        assert SESSION_POLICY_DEFAULTS[driver]["timeout_s"] == SESSION_TIMEOUT_S, (
            f"{driver} policy defaults must carry timeout_s "
            f"(got {SESSION_POLICY_DEFAULTS[driver]!r})"
        )


def test_t5b_a_config_without_the_key_reads_1800():
    """Back-compat: every pre-b004 config resolves to today's value."""
    cfg = {"backends": {"localclaude": {"session": {"permission_mode": "acceptEdits"}}}}
    assert get_session_policy(cfg, "localclaude")["timeout_s"] == 1800.0
    assert get_session_policy({}, "codex")["timeout_s"] == 1800.0


def test_t5c_configured_timeout_s_reaches_the_session_kwargs(monkeypatch, tmp_path):
    """The whole plumbing run: config → get_session_policy → session() kwargs."""
    driver = _CapturingDriver()
    monkeypatch.setattr(backends_mod, "get_driver", lambda cfg, role=None: (driver, None))

    cfg = {
        "implementer": {"backend": "localclaude"},
        "backends": {"localclaude": {"session": {"timeout_s": 3600}}},
    }
    runner = _default_session_runner(cfg, None)
    runner("p", cwd=tmp_path, resume_id=None)

    (call,) = driver.calls
    assert call["timeout_s"] == 3600, (
        f"backends.localclaude.session.timeout_s must splat into session(): {call!r}"
    )


def test_t5d_an_unconfigured_run_still_splats_the_1800_default(monkeypatch, tmp_path):
    """HOUSE RULE: unconfigured == today. The effective value is still 1800s."""
    driver = _CapturingDriver()
    monkeypatch.setattr(backends_mod, "get_driver", lambda cfg, role=None: (driver, None))

    runner = _default_session_runner({"implementer": {"backend": "localclaude"}}, None)
    runner("p", cwd=tmp_path, resume_id=None)

    (call,) = driver.calls
    assert call["timeout_s"] == SESSION_TIMEOUT_S


def test_t5e_the_b004_validation_config_arms_3600():
    """C-B.4: the 2026-09-28 ruling, armed in the config the batch runs on."""
    cfg = load_config("config/b004-validation.yaml")
    policy = get_session_policy(cfg, "localclaude")
    assert policy["timeout_s"] == 3600, (
        "config/b004-validation.yaml must carry backends.localclaude.session.timeout_s: 3600 "
        f"(measured legit attempt-1 range 252-1646s; 1800 clipped ~30%). Policy: {policy!r}"
    )
    assert policy["permission_mode"] == "acceptEdits", "the rest of the policy is untouched"


# --- T6 ----------------------------------------------------------------------


def _no_subprocess(monkeypatch) -> list[list[str]]:
    """Arm `_run` so a VALID session would succeed — an invalid one must never
    get this far."""
    calls: list[list[str]] = []

    def fake_run(cmd, driver, timeout_s, cwd=None):
        calls.append(list(cmd))
        payload = {
            "result": "ok",
            "is_error": False,
            "total_cost_usd": 0.0,
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "session_id": "sess-1",
        }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr=""), 0.01

    monkeypatch.setattr(backends_mod, "_run", fake_run)
    return calls


@pytest.mark.parametrize("bad", [0, -5, "abc", float("inf"), float("nan")])
def test_t6_invalid_timeout_s_is_a_loud_localclaude_error(monkeypatch, tmp_path, bad):
    """C-B.2: not a real, finite, positive number → DriverError naming driver,
    key and got-value. INTERPRETATION: the contract's test lane allows
    "DriverError/TypeError as specified"; C-B specifies DriverError, so both are
    accepted here and the MESSAGE is what is pinned."""
    calls = _no_subprocess(monkeypatch)

    with pytest.raises((DriverError, TypeError)) as excinfo:
        LocalClaudeDriver().session("p", cwd=tmp_path, timeout_s=bad)

    message = str(excinfo.value)
    assert "timeout_s" in message, f"the error must name the key: {message!r}"
    assert "localclaude" in message, f"the error must name the driver: {message!r}"
    assert str(bad) in message, f"the error must print the got-value: {message!r}"
    assert calls == [], "an invalid value must be rejected BEFORE the subprocess"


@pytest.mark.parametrize("bad", [0, -5, "abc", float("inf")])
def test_t6b_invalid_timeout_s_is_a_loud_codex_error(monkeypatch, tmp_path, bad):
    """Symmetric: C-B.1 adds the key to BOTH drivers, so BOTH must check it."""
    calls = _no_subprocess(monkeypatch)

    with pytest.raises((DriverError, TypeError)) as excinfo:
        CodexDriver().session("p", cwd=tmp_path, timeout_s=bad)

    message = str(excinfo.value)
    assert "timeout_s" in message, f"the error must name the key: {message!r}"
    assert "codex" in message, f"the error must name the driver: {message!r}"
    assert calls == [], "an invalid value must be rejected BEFORE the subprocess"


def test_t6c_a_valid_timeout_s_still_runs(monkeypatch, tmp_path):
    """The guard rejects only the invalid: a good value reaches the subprocess."""
    calls = _no_subprocess(monkeypatch)
    LocalClaudeDriver().session("p", cwd=tmp_path, timeout_s=3600)
    assert len(calls) == 1, "a finite positive timeout_s must not be rejected"


# --- T7 ----------------------------------------------------------------------


def _fake_timeout_subprocess(monkeypatch, out: str, err: str) -> None:
    """Make the subprocess layer time out with the given partials.

    Both shapes are covered without looking at `_run`'s body: a `subprocess.run`
    implementation gets the partials off `TimeoutExpired.output/.stderr`; a
    `Popen` implementation gets `TimeoutExpired` from the first `communicate()`
    and the same partials from the post-kill one.
    """

    def fake_run(cmd, *args, timeout=None, **kwargs):
        raise subprocess.TimeoutExpired(cmd, timeout or 0, output=out, stderr=err)

    class _FakePopen:
        def __init__(self, cmd, *args, **kwargs):
            self.args = cmd
            self.returncode = None
            self.stdin = self.stdout = self.stderr = None
            self._communicated = 0

        def communicate(self, input=None, timeout=None):
            self._communicated += 1
            if self._communicated == 1:
                raise subprocess.TimeoutExpired(self.args, timeout or 0, output=out, stderr=err)
            return out, err

        def kill(self):
            self.returncode = -9

        def terminate(self):
            self.returncode = -15

        def wait(self, timeout=None):
            self.returncode = -9
            return self.returncode

        def poll(self):
            return self.returncode

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", _FakePopen)


def test_t7a_an_empty_partial_timeout_says_no_output_was_captured(monkeypatch, tmp_path):
    """C-C: print-mode buffers until completion, so empty partials are
    STRUCTURAL. The message must stop implying missing evidence."""
    _fake_timeout_subprocess(monkeypatch, "", "")

    with pytest.raises(DriverError) as excinfo:
        backends_mod._run(["/bin/sleep", "60"], "localclaude", 12.0, cwd=tmp_path)

    message = str(excinfo.value)
    assert "timed out after" in message, (
        f"downstream matching and the attempt records key off this prefix: {message!r}"
    )
    assert "12s" in message, f"the effective timeout is the stamp: {message!r}"
    assert "no output captured" in message, f"C-C's honest wording is missing: {message!r}"
    assert "<empty>" not in message, (
        f"the old 'partial stdout: <empty>' implied evidence that cannot exist: {message!r}"
    )


def test_t7b_a_real_partial_keeps_todays_format(monkeypatch, tmp_path):
    """Other callers (codex, non-print-mode) DO produce partials: show them."""
    _fake_timeout_subprocess(monkeypatch, "half a level generated", "a warning line")

    with pytest.raises(DriverError) as excinfo:
        backends_mod._run(["/bin/sleep", "60"], "codex", 30.0, cwd=tmp_path)

    message = str(excinfo.value)
    assert "timed out after" in message and "30s" in message
    assert "partial stdout" in message, f"today's partial display must survive: {message!r}"
    assert "half a level generated" in message, f"the captured stdout is shown: {message!r}"
    assert "a warning line" in message, f"the captured stderr is shown: {message!r}"
    assert "no output captured" not in message, (
        f"the honest branch is for EMPTY partials only: {message!r}"
    )


def test_t7c_the_timeout_error_type_is_unchanged(monkeypatch, tmp_path):
    """The attempt records and the outage ladder key off DriverError; a timeout
    must stay a DriverError and must NOT leak subprocess.TimeoutExpired."""
    _fake_timeout_subprocess(monkeypatch, "", "")

    with pytest.raises(DriverError) as excinfo:
        backends_mod._run(["/bin/sleep", "60"], "localclaude", 1.0, cwd=tmp_path)

    assert not isinstance(excinfo.value, subprocess.TimeoutExpired)
