"""Blind pins for contract P-1a — the auth-independent codex lane.

Run: .venv/bin/python -m pytest gen/tests/test_v2_codex.py -v

BLIND LANE. Written from the frozen plan alone
(the v2 programme's plan file, section "P-1 — codex
first-class" as narrowed by "Sequencing — REVISED 2026-09-30") by an agent that
never read the implementation diff. `docs/v2/contracts/P-1a-codex-code.md` did
not exist when this file was written, so the plan section governs; if the
implementer's brief lands and contradicts a pin below, the BRIEF wins and the
pin is retargeted by the lead — never weakened to make a red test green.

Nothing here may be softened to make a missing symbol pass. A pre-merge failure
on `CodexDriver.preflight`, on `SESSION_POLICY_DEFAULTS["codex"]["effort"]`, on
the `-s read-only` containment or on `backends.codex.session.timeout_s` is the
EXPECTED pre-state, not a test bug.

WHAT WAS READ TO WRITE THIS: the public surfaces of `gen/backends.py`
(constants, dataclasses, both drivers' signatures and docstrings,
`get_session_policy`, `OpenRouterDriver.preflight` as the mirror named by the
plan), `gen/s1_spec.py::_default_writer_runner`, `gen/s0_ideas.py::check_config`'s
signature, `config/template.yaml`'s backends block, and the two pattern files
the brief names (`test_b3_green_loop.py`'s argv pins, `test_b004_s2timeout.py`'s
fake-subprocess rig). No diff, no branch, no `git show`.

THREE RULES THIS FILE KEEPS.

  * NO network and NO `codex` / `claude` binary is ever spawned. Every driver
    test fakes `gen.backends._run` (the b3/b004 rig) or `subprocess` itself, and
    two tests ASSERT that no process was started.
  * Expectations are computed from LIVE module constants at call time
    (`SESSION_TIMEOUT_S`, `SMOKE_TIMEOUT_S`, `DEFAULT_S2_ALLOWED_TOOLS`,
    `S1_WRITER_TOOLS`), except in the byte-identity section (G), where literals
    are deliberate: G exists to catch a constant that MOVED.
  * Tests write only into `tmp_path`. `S1_SCRATCH_ROOT` is redirected so the S1
    writer pins never touch `out/tmp` in the repo.

THE PINS, in the plan's item order.

  A  item 1 — `CodexDriver.complete()` containment: `-s read-only`, a throwaway
     cwd that is not the repo, and a prose-call timeout that reaches the
     subprocess. Plus the localclaude `complete()` byte-identity guard.
  B  item 2 — the effort analog: `SESSION_POLICY_DEFAULTS["codex"]` gains
     `effort` (None default), and a configured value reaches the session argv as
     `-c model_reasoning_effort=<v>` — a PARENT option, so before `resume`.
  C  item 3 — `backends.codex.session.timeout_s: 3600` armed in
     `config/template.yaml`, unconfigured still 1800.
  D  item 4 — the auth preflight's LOUD failure modes, exercised against the
     live 401 records in `out/smoke/smoke.jsonl`. Never a success path: a valid
     key is P-0/P-1b.
  E  item 5 — S1's `_default_writer_runner` consulting `get_session_policy`
     per driver, and never handing a driver a kwarg its `session()` cannot take.
  F  item 7 — `check_config` rejecting a bad `backends` block at load.
  G  byte-identity — the localclaude lane is untouched by all of the above.
  H  P-1b / lead-seam placeholders: skipped, with reasons. No invented fixtures.

ITEM 6 (cost honesty — "codex sessions are unpriced by the CLI" on the
orchestrator `COST_NOTE` seam) IS NOT PINNED HERE as a live test. The plan's
Wave A note makes that seam a LEAD edit made AFTER both Wave-A pairs merge, so a
red pin on it would block the P-1a close for work that is not P-1a's. H4 records
the requirement as a skip so it cannot be lost.
"""

from __future__ import annotations

import inspect
import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from gen import backends as backends_mod
from gen import s0_ideas, s1_spec
from gen.backends import (
    CODEX_SANDBOX_MODES,
    DEFAULT_S2_ALLOWED_TOOLS,
    SESSION_POLICY_DEFAULTS,
    SESSION_TIMEOUT_S,
    SMOKE_TIMEOUT_S,
    CodexDriver,
    DriverError,
    LocalClaudeDriver,
    get_session_policy,
)
from gen.config import REPO_ROOT, load_config

TEMPLATE_PATH = REPO_ROOT / "config" / "template.yaml"
SMOKE_LOG = REPO_ROOT / "out" / "smoke" / "smoke.jsonl"

# The plan's item 1 names one sandbox value for the prose lane and no other.
PROSE_SANDBOX = "read-only"
# The codex key for the reasoning-effort analog: codex has no `--effort` flag,
# so the value rides a `-c` config override (plan item 2, verbatim).
CODEX_EFFORT_KEY = "model_reasoning_effort"
# Never constructed, by either driver, whatever a config says.
BYPASS_FLAGS = (
    "--dangerously-skip-permissions",
    "--dangerously-bypass-approvals-and-sandbox",
)
# Config errors are raised by different families across the stages this file
# touches (`ValueError` in s0_ideas' checkers, `KeyError` in `get_driver`'s
# resolve, `TypeError` in `get_session_policy`'s shape guards). The plan does not
# specify a type for item 7, so the MESSAGE is what is pinned — the
# test_b004_s2timeout T6 interpretation, reused.
CONFIG_ERRORS = (ValueError, KeyError, TypeError, DriverError)


# --- rigs --------------------------------------------------------------------


def _fake_codex_run(monkeypatch, *, message: str = "SMOKE-OK",
                    events: list[dict] | None = None, returncode: int = 0) -> list[dict]:
    """Fake `gen.backends._run` for the codex lane; records every call.

    Writes the `-o` last-message file the driver demands, so a faked call walks
    the SAME success path a green CLI would and the argv it built survives to be
    inspected. Nothing is spawned.
    """
    calls: list[dict] = []
    stream = events if events is not None else [
        {"type": "thread.started", "thread_id": "th-fake-1"},
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
    ]

    def fake_run(cmd, driver, timeout_s, cwd=None):
        calls.append({
            "cmd": list(cmd),
            "driver": driver,
            "timeout_s": timeout_s,
            "cwd": cwd,
            # TemporaryDirectory is gone by the time a test reads this, so the
            # liveness question is answered HERE, inside the call.
            "cwd_is_dir": Path(cwd).is_dir() if cwd is not None else None,
        })
        if "-o" in cmd:
            out_path = Path(cmd[cmd.index("-o") + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(message, encoding="utf-8")
        stdout = "\n".join(json.dumps(event) for event in stream)
        return subprocess.CompletedProcess(list(cmd), returncode, stdout=stdout, stderr=""), 0.01

    monkeypatch.setattr(backends_mod, "_run", fake_run)
    return calls


def _fake_claude_run(monkeypatch) -> list[dict]:
    """Fake `_run` for the claude lane (the `test_b3_green_loop` payload)."""
    calls: list[dict] = []

    def fake_run(cmd, driver, timeout_s, cwd=None):
        calls.append({"cmd": list(cmd), "driver": driver, "timeout_s": timeout_s, "cwd": cwd})
        payload = {
            "result": "ok", "is_error": False, "total_cost_usd": 0.0,
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "session_id": "sess-1",
        }
        return subprocess.CompletedProcess(list(cmd), 0, stdout=json.dumps(payload), stderr=""), 0.01

    monkeypatch.setattr(backends_mod, "_run", fake_run)
    return calls


def _forbid_all_processes(monkeypatch) -> None:
    """Any process start from here on fails the test, loudly and by name.

    Belt AND braces: `_run` is the driver seam, `subprocess.run`/`Popen` is the
    floor under it. A preflight that "checks" a key by invoking the CLI trips
    this — presence-checking is the whole point of failing BEFORE spend.
    """

    def boom(*args, **kwargs):  # pragma: no cover - the assertion IS the body
        raise AssertionError(f"a process was started: {args!r} {kwargs!r}")

    monkeypatch.setattr(backends_mod, "_run", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)


def _last(calls: list[dict]) -> list[str]:
    assert calls, "no driver call was recorded"
    return calls[-1]["cmd"]


def _normalised(cmd: list[str]) -> list[str]:
    """An argv with the per-call `-o` last-message path masked.

    Every codex call opens its own `TemporaryDirectory`, so two otherwise
    identical argvs differ at exactly that token. Masking it is what makes an
    argv-to-argv byte-identity comparison meaningful.
    """
    masked = list(cmd)
    if "-o" in masked:
        masked[masked.index("-o") + 1] = "<tmp>/last_message.txt"
    return masked


def _pair(cmd: list[str], flag: str) -> str:
    """The value that follows `flag` in an argv, with a readable failure."""
    assert flag in cmd, f"{flag!r} missing from argv: {cmd!r}"
    index = cmd.index(flag)
    assert index + 1 < len(cmd), f"{flag!r} is the last token (no value): {cmd!r}"
    return cmd[index + 1]


def _template_cfg(tmp_path: Path) -> dict:
    """`load_config` over a tmp COPY of config/template.yaml.

    `load_config` resolves canon paths against the REPO root, never against the
    config's own location, so a tmp copy loads exactly like the real file while
    keeping every reader's hands out of `config/` (the test_docs_template rule).
    """
    if not TEMPLATE_PATH.is_file():
        pytest.fail(f"config/template.yaml missing: {TEMPLATE_PATH}")
    dest = tmp_path / "template.yaml"
    shutil.copyfile(TEMPLATE_PATH, dest)
    return load_config(dest)


# =============================================================================
# A — item 1: complete() containment
# =============================================================================


def test_a1_codex_complete_pins_the_read_only_sandbox(monkeypatch):
    """Item 1: the S0/S1 prose call runs `-s read-only`.

    complete() is the PURE completion API — the codex twin of the localclaude
    `--tools ""` lesson (backends.py's own comment: without it headless claude
    ran a full agent loop in the caller's cwd and read our test fixtures). An
    un-sandboxed codex prose call is that same gap, still open.
    """
    calls = _fake_codex_run(monkeypatch)
    CodexDriver().complete("draw one idea in prose")

    cmd = _last(calls)
    assert "-s" in cmd or "--sandbox" in cmd, (
        f"codex complete() must contain the prose agent with a sandbox flag: {cmd!r}"
    )
    flag = "-s" if "-s" in cmd else "--sandbox"
    assert _pair(cmd, flag) == PROSE_SANDBOX, (
        f"the prose lane writes nothing, so it runs {PROSE_SANDBOX!r}: {cmd!r}"
    )
    assert PROSE_SANDBOX in CODEX_SANDBOX_MODES, (
        "read-only must stay a value codex 0.142.5 accepts (CODEX_SANDBOX_MODES)"
    )
    assert "workspace-write" not in cmd and "danger-full-access" not in cmd, (
        f"a writable sandbox on the prose call is the gap item 1 closes: {cmd!r}"
    )
    # The sandbox is a `codex exec` PARENT option; the prompt is the trailing
    # positional. Everything flag-shaped must precede it.
    assert cmd.index(flag) < len(cmd) - 1, f"the prompt must stay last: {cmd!r}"


def test_a2_codex_complete_runs_in_a_throwaway_cwd_not_the_repo(monkeypatch):
    """Item 1: "tmp cwd" — an unspecified prose call never roots in the repo."""
    calls = _fake_codex_run(monkeypatch)
    CodexDriver().complete("draw one idea in prose")

    (call,) = calls
    cwd = call["cwd"]
    assert cwd is not None, (
        "complete() passed cwd=None — the child inherits OUR cwd, which at S0 is "
        "the repo root. Item 1 requires a throwaway directory."
    )
    assert call["cwd_is_dir"], f"the prose cwd must exist when the child starts: {cwd!r}"

    resolved = Path(cwd).resolve()
    assert resolved != REPO_ROOT, f"the prose cwd is the repo root: {resolved}"
    assert REPO_ROOT not in resolved.parents, (
        f"the prose cwd is inside the repo tree ({resolved}) — a contained agent "
        "must not be able to reach gen/, out/ or config/ by relative path"
    )
    assert resolved != Path.cwd().resolve(), (
        f"the prose cwd is the caller's cwd ({resolved}) — that is the un-contained state"
    )


def test_a3_an_explicit_cwd_is_honoured_or_refused_but_never_ignored(monkeypatch, tmp_path):
    """AMBIGUITY, pinned as a property rather than a signature.

    The plan says "tmp cwd" and does not say whether complete()'s existing
    `cwd` parameter survives. Both readings are legitimate — keep it (today's
    signature, caller chooses) or drop it (containment is not negotiable) — and
    no caller in the tree passes it today (`s0_ideas.py:1394`, `smoke.py:51`).
    What is NOT legitimate is accepting a cwd and quietly running somewhere
    else, or accepting one and running in the repo.
    """
    calls = _fake_codex_run(monkeypatch)
    explicit = tmp_path / "explicit-cwd"
    explicit.mkdir()

    try:
        CodexDriver().complete("p", cwd=explicit)
    except TypeError:
        pytest.skip(
            "complete() no longer takes `cwd` — containment tightened to "
            "always-tmp. Legitimate reading of item 1; A2 is then the whole pin."
        )

    (call,) = calls
    used = Path(call["cwd"]).resolve()
    assert used == explicit.resolve() or REPO_ROOT not in used.parents, (
        f"an explicit cwd was neither honoured nor replaced by a contained tmp dir: {used}"
    )


def test_a4_codex_complete_timeout_reaches_the_subprocess(monkeypatch):
    """Item 1: "a prose-call timeout parameter" — the value the caller names is
    the value the child is killed on."""
    calls = _fake_codex_run(monkeypatch)
    CodexDriver().complete("p", timeout_s=42.0)
    assert calls[-1]["timeout_s"] == 42.0, (
        f"complete(timeout_s=42.0) must reach _run verbatim: {calls[-1]!r}"
    )


def test_a5_the_default_prose_timeout_is_finite_and_named(monkeypatch):
    """The default is a CONSTANT, not an accident, and it is not unbounded.

    Today's default is `SMOKE_TIMEOUT_S` (300s). Item 1 may introduce a distinct
    prose constant; both are accepted here and anything else is a bare literal
    the next reader cannot find.
    """
    calls = _fake_codex_run(monkeypatch)
    CodexDriver().complete("p")

    used = calls[-1]["timeout_s"]
    assert isinstance(used, (int, float)) and not isinstance(used, bool)
    assert math.isfinite(used) and used > 0, f"the prose call must be killable: {used!r}"
    named = {SMOKE_TIMEOUT_S}
    for candidate in ("PROSE_TIMEOUT_S", "COMPLETE_TIMEOUT_S", "CODEX_PROSE_TIMEOUT_S"):
        value = getattr(backends_mod, candidate, None)
        if isinstance(value, (int, float)):
            named.add(value)
    assert used in named, (
        f"the default prose timeout {used!r} matches no module constant "
        f"(known: {sorted(named)}) — name it so a config can move it"
    )


def test_a6_no_bypass_flag_on_the_prose_call(monkeypatch):
    calls = _fake_codex_run(monkeypatch)
    CodexDriver().complete("p", model="gpt-5.4")
    cmd = _last(calls)
    for flag in BYPASS_FLAGS:
        assert flag not in cmd, f"{flag} must never be constructed: {cmd!r}"


# =============================================================================
# B — item 2: the reasoning-effort analog
# =============================================================================


def test_b1_codex_policy_defaults_gain_effort_defaulting_to_none(monkeypatch):
    """Item 2: `SESSION_POLICY_DEFAULTS["codex"]` gains `effort` (None default).

    None default = an unconfigured codex run is byte-identical to today (no
    `-c` override), the same discipline `localclaude.effort` already keeps.
    """
    codex_defaults = SESSION_POLICY_DEFAULTS["codex"]
    assert "effort" in codex_defaults, (
        f"codex policy defaults must admit `effort`: {codex_defaults!r} — without "
        "it get_session_policy REJECTS backends.codex.session.effort as an unknown key"
    )
    assert codex_defaults["effort"] is None, (
        f"default must be None (the CLI's own deliberation): {codex_defaults!r}"
    )


def test_b2_every_codex_policy_key_is_a_real_session_parameter():
    """Structural: `get_session_policy` returns kwargs that get SPLATTED into
    `session()`. A policy key with no matching parameter is a TypeError at the
    first real worker turn — the failure mode this whole contract exists to
    avoid on the codex lane."""
    for driver_name, driver_cls in (("codex", CodexDriver), ("localclaude", LocalClaudeDriver)):
        parameters = set(inspect.signature(driver_cls.session).parameters)
        policy = get_session_policy({}, driver_name)
        unknown = sorted(set(policy) - parameters)
        assert not unknown, (
            f"{driver_name} policy keys {unknown} are not parameters of "
            f"{driver_cls.__name__}.session (has {sorted(parameters - {'self'})})"
        )


def test_b3_configured_codex_effort_reaches_the_session_argv(monkeypatch, tmp_path):
    """Item 2 end to end: config → get_session_policy → `-c model_reasoning_effort=`."""
    calls = _fake_codex_run(monkeypatch)
    cfg = {"backends": {"codex": {"session": {"effort": "high"}}}}

    policy = get_session_policy(cfg, "codex")
    assert policy["effort"] == "high", f"the configured value must survive: {policy!r}"

    CodexDriver().session("p", cwd=tmp_path, **policy)
    cmd = _last(calls)
    assert "-c" in cmd, f"codex carries effort on a `-c` config override: {cmd!r}"
    assert _pair(cmd, "-c") == f"{CODEX_EFFORT_KEY}=high", (
        f"expected `-c {CODEX_EFFORT_KEY}=high` as ONE adjacent pair: {cmd!r}"
    )
    assert "--effort" not in cmd, (
        f"`--effort` is the CLAUDE flag; codex 0.142.5 has none: {cmd!r}"
    )


def test_b4_no_effort_means_no_config_override(monkeypatch, tmp_path):
    """Byte-identity: an unconfigured codex session is exactly today's argv."""
    calls = _fake_codex_run(monkeypatch)
    driver = CodexDriver()

    driver.session("p", cwd=tmp_path, **get_session_policy({}, "codex"))
    with_policy = _last(calls)
    driver.session("p", cwd=tmp_path)
    bare = _last(calls)

    assert "-c" not in with_policy, (
        f"effort=None must omit the override entirely: {with_policy!r}"
    )
    assert CODEX_EFFORT_KEY not in " ".join(with_policy)
    assert _normalised(with_policy) == _normalised(bare), (
        "the default policy must build the same argv as no policy at all\n"
        f"  policy: {_normalised(with_policy)!r}\n  bare:   {_normalised(bare)!r}"
    )


def test_b5_effort_is_a_parent_option_and_precedes_resume(monkeypatch, tmp_path):
    """The clap lesson, already recorded for `-s`/`--cd` in CodexDriver.session:
    options of the `codex exec` PARENT must precede the `resume` subcommand or
    the binary exits 2 ("unexpected argument found"). `-c` is such an option."""
    calls = _fake_codex_run(monkeypatch)
    CodexDriver().session("p", cwd=tmp_path, resume_id="th-9", effort="high")

    cmd = _last(calls)
    assert "resume" in cmd, f"a resume_id must build the resume shape: {cmd!r}"
    resume_at = cmd.index("resume")
    assert "-c" in cmd and cmd.index("-c") < resume_at, (
        f"`-c` must precede `resume` (clap rejects it after): {cmd!r}"
    )
    assert cmd.index("-s") < resume_at, f"`-s` placement must not regress: {cmd!r}"
    assert cmd.index("--cd") < resume_at, f"`--cd` placement must not regress: {cmd!r}"
    # Positional order is unchanged: [SESSION_ID] then [PROMPT], both trailing.
    assert cmd[-2:] == ["th-9", "p"], f"resume positionals must stay last: {cmd!r}"


def test_b6_a_malformed_effort_never_reaches_the_argv(monkeypatch, tmp_path):
    """A yaml knob takes whatever is typed. Either the driver refuses loudly, or
    it builds a well-formed pair — never `model_reasoning_effort=` with nothing
    after it, and never a python repr shipped to a CLI."""
    calls = _fake_codex_run(monkeypatch)
    for bad in ("", 5, ["high"], True, {"level": "high"}):
        before = len(calls)
        try:
            CodexDriver().session("p", cwd=tmp_path, effort=bad)
        except (DriverError, TypeError, ValueError):
            continue
        assert len(calls) > before, f"effort={bad!r} neither raised nor ran"
        cmd = _last(calls)
        if "-c" not in cmd:
            continue
        value = _pair(cmd, "-c")
        assert value.startswith(f"{CODEX_EFFORT_KEY}="), f"malformed override: {value!r}"
        payload = value.split("=", 1)[1]
        assert payload, f"effort={bad!r} built an EMPTY override: {cmd!r}"
        assert payload == str(bad), (
            f"effort={bad!r} was reshaped into {payload!r} on its way to the CLI"
        )


# =============================================================================
# C — item 3: the codex session timeout, armed in the template
# =============================================================================


def test_c1_the_template_arms_the_codex_session_timeout(tmp_path):
    """Item 3: `backends.codex.session.timeout_s: 3600` — parity with the b004
    ruling. Today the codex block has no `timeout_s` at all, so a codex batch
    silently reverts to 1800 and clips its own worker turns."""
    raw = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    codex_session = ((raw.get("backends") or {}).get("codex") or {}).get("session")
    assert isinstance(codex_session, dict), (
        f"backends.codex.session must be a mapping in the template: {codex_session!r}"
    )
    # yaml-level, so a commented-out key cannot satisfy this pin.
    assert "timeout_s" in codex_session, (
        f"backends.codex.session.timeout_s is missing from the template: {codex_session!r}"
    )
    # LEAD EDIT 2026-10-01: 3600 -> 7200 by operator ruling ("at least 2 hours")
    # after g20261001-1's t1 builds ran 2579s/3372s — 94% of the old budget.
    # The pin's SHAPE is unchanged: both lanes armed, at parity.
    assert codex_session["timeout_s"] == 7200, (
        f"the armed ruling is 7200s on both lanes (2026-10-01): {codex_session!r}"
    )

    cfg = _template_cfg(tmp_path)
    assert get_session_policy(cfg, "codex")["timeout_s"] == 7200
    assert get_session_policy(cfg, "localclaude")["timeout_s"] == 7200, (
        "the localclaude lane must be armed at the same 7200 parity"
    )


def test_c2_an_unconfigured_codex_run_still_reads_1800():
    """Back-compat: every config written before item 3 resolves to today's value."""
    assert SESSION_TIMEOUT_S == 1800.0
    assert get_session_policy({}, "codex")["timeout_s"] == SESSION_TIMEOUT_S
    assert SESSION_POLICY_DEFAULTS["codex"]["timeout_s"] == SESSION_TIMEOUT_S


def test_c3_the_armed_codex_timeout_reaches_the_subprocess(monkeypatch, tmp_path):
    calls = _fake_codex_run(monkeypatch)
    cfg = _template_cfg(tmp_path)
    worker = tmp_path / "worker"
    worker.mkdir()

    CodexDriver().session("p", cwd=worker, **get_session_policy(cfg, "codex"))
    # LEAD EDIT 2026-10-01: value follows the template's 7200 (operator ruling).
    assert calls[-1]["timeout_s"] == 7200, (
        f"the template's codex timeout must be the kill ceiling: {calls[-1]!r}"
    )


# =============================================================================
# D — item 4: the auth preflight (FAILURE MODES ONLY; success is P-0/P-1b)
# =============================================================================

CODEX_AUTH_RELPATH = Path(".codex") / "auth.json"


def _preflight(driver, *, cfg: dict | None = None, auth_env: str = "OPENAI_API_KEY"):
    """Call `CodexDriver.preflight` whatever shape item 4 gave it.

    AMBIGUITY (reported to the lead): the plan says "wire `auth_env`: a
    preflight that fails BEFORE spend ... (mirror OpenRouterDriver.preflight)".
    The mirror takes NO arguments, but codex's var name is configurable
    (`backends.codex.auth_env`), so the preflight must learn it from somewhere.
    This binder accepts every reasonable signature — `preflight()`,
    `preflight(cfg)`, `preflight(*, auth_env=...)` — and fails loudly on one it
    cannot bind, rather than pinning a guess.
    """
    fn = getattr(driver, "preflight", None)
    if fn is None or not callable(fn):
        pytest.fail(
            "CodexDriver.preflight is missing (plan item 4: a preflight that fails "
            "BEFORE spend when the named var is absent AND no ~/.codex/auth.json exists)"
        )
    known = {
        "cfg": cfg or {}, "config": cfg or {},
        "auth_env": auth_env, "env_var": auth_env, "env": auth_env, "env_name": auth_env,
    }
    bound: dict = {}
    for name, parameter in inspect.signature(fn).parameters.items():
        if name in known:
            bound[name] = known[name]
        elif parameter.default is inspect.Parameter.empty and parameter.kind not in (
            inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD
        ):
            pytest.fail(
                f"CodexDriver.preflight has an unbindable required parameter {name!r} "
                f"(signature {inspect.signature(fn)}) — the blind lane knows "
                f"{sorted(known)}; the lead retargets this binder"
            )
    return fn(**bound)


def _no_auth_json(monkeypatch, tmp_path: Path) -> Path:
    """A home with no `~/.codex/auth.json`, however the implementation looks."""
    home = tmp_path / "home-empty"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    _redirect_auth_constant(monkeypatch, home)
    return home


def _with_auth_json(monkeypatch, tmp_path: Path) -> Path:
    """A home that DOES carry a codex login (contents irrelevant, never a key)."""
    home = tmp_path / "home-authed"
    path = home / CODEX_AUTH_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tokens": {"id_token": "fixture-not-a-credential"}}), "utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    _redirect_auth_constant(monkeypatch, home)
    return home


def _redirect_auth_constant(monkeypatch, home: Path) -> None:
    """If item 4 froze the auth.json path into a module constant at import time,
    `HOME` alone cannot move it — retarget the constant too."""
    for name, value in list(vars(backends_mod).items()):
        if not name.isupper() or not isinstance(value, (str, Path)):
            continue
        if "AUTH" in name and "CODEX" in name:
            monkeypatch.setattr(backends_mod, name, type(value)(home / CODEX_AUTH_RELPATH))


def test_d1_the_codex_driver_exposes_a_preflight():
    """Item 4: "no more decorative config" — the lane gets the same
    fail-before-spend verb the OpenRouter lane already has."""
    assert hasattr(CodexDriver, "preflight"), (
        "CodexDriver.preflight is missing — item 4 mirrors "
        "OpenRouterDriver.preflight for the codex lane"
    )
    assert callable(CodexDriver().preflight)


def test_d2_preflight_is_loud_when_neither_the_env_var_nor_auth_json_exists(
    monkeypatch, tmp_path
):
    """The core failure mode. Absent var AND absent login → DriverError that
    names the var and prints the user's own fix, before a cent is spent."""
    _no_auth_json(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _forbid_all_processes(monkeypatch)

    with pytest.raises(DriverError) as excinfo:
        _preflight(CodexDriver())

    message = str(excinfo.value)
    assert "OPENAI_API_KEY" in message, f"the error must name the var: {message!r}"
    assert "codex" in message.lower(), f"the error must name the lane: {message!r}"
    assert "codex login" in message, (
        f"the error must carry the user-side remediation (the same fix the live "
        f"401 records print): {message!r}"
    )


def test_d3_a_present_env_var_passes_without_spending_anything(monkeypatch, tmp_path):
    """Presence-check ONLY. A preflight that validated the key would have to
    call the API — and the three recorded 401s prove the failure this guards is
    a STALE env key shadowing a valid login, which no local check can see."""
    _no_auth_json(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fixture-presence-only")
    _forbid_all_processes(monkeypatch)

    assert _preflight(CodexDriver()) is None, "preflight returns nothing (the mirror's shape)"


def test_d4_an_auth_json_alone_passes(monkeypatch, tmp_path):
    """The plan's AND: the preflight fails only when the var is absent AND no
    `~/.codex/auth.json` exists. A `codex login` with no env var is a valid box."""
    _with_auth_json(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _forbid_all_processes(monkeypatch)

    _preflight(CodexDriver())  # must not raise


def test_d5_a_blank_env_var_counts_as_absent(monkeypatch, tmp_path):
    """`OpenRouterDriver._api_key` strips before judging; the mirror must too —
    `export OPENAI_API_KEY=` in a shell profile is the common shape of "unset"."""
    _no_auth_json(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    _forbid_all_processes(monkeypatch)

    with pytest.raises(DriverError) as excinfo:
        _preflight(CodexDriver())
    assert "OPENAI_API_KEY" in str(excinfo.value)


def test_d6_the_configured_auth_env_name_is_the_one_checked(monkeypatch, tmp_path):
    """"Wire `auth_env` ... no more decorative config": the config names the var,
    so a box whose key lives in a differently-named var must preflight GREEN."""
    _no_auth_json(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MY_CODEX_KEY", "sk-fixture-presence-only")
    _forbid_all_processes(monkeypatch)

    cfg = {"backends": {"codex": {"auth_env": "MY_CODEX_KEY"}}}
    _preflight(CodexDriver(), cfg=cfg, auth_env="MY_CODEX_KEY")  # must not raise


def test_d7_the_configured_auth_env_name_is_what_a_failure_reports(monkeypatch, tmp_path):
    """The mirror image: the named var is ALSO the var the error tells you to set."""
    _no_auth_json(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MY_CODEX_KEY", raising=False)
    _forbid_all_processes(monkeypatch)

    cfg = {"backends": {"codex": {"auth_env": "MY_CODEX_KEY"}}}
    with pytest.raises(DriverError) as excinfo:
        _preflight(CodexDriver(), cfg=cfg, auth_env="MY_CODEX_KEY")
    assert "MY_CODEX_KEY" in str(excinfo.value), (
        f"a failure must name the CONFIGURED var, not a hardcoded one: {excinfo.value}"
    )


def test_d8_the_live_401_records_still_parse_as_codex_auth_failures():
    """The three (now four) recorded 401s in out/smoke/smoke.jsonl are this
    contract's only live failure fixtures. They pin two things: the shape the
    driver turns a `turn.failed` into, and the remediation `_AUTH_HINTS` appends
    — the same sentence the preflight repeats at second zero."""
    # LICENSED EDIT (contract OS-2 FRONT C.1): missing -> SKIP, d9's pattern. The
    # smoke ledger is gitignored by design (it holds OpenAI-masked key
    # fragments), so a public clone never has it and a hard fail made every
    # clone's suite red out of the box. test_os2_mirror pins that it stays
    # ignored and untracked.
    if not SMOKE_LOG.is_file():
        pytest.skip(f"no smoke log on this box ({SMOKE_LOG} is gitignored)")
    records = [json.loads(line) for line in SMOKE_LOG.read_text("utf-8").splitlines() if line.strip()]
    failures = [r for r in records if r.get("driver") == "codex" and r.get("ok") is False]

    assert len(failures) >= 3, (
        f"the plan cites three recorded codex 401s; found {len(failures)} in {SMOKE_LOG}"
    )
    for record in failures:
        error = record["error"]
        assert error.startswith("[codex]"), f"the driver tag is the record's key: {error!r}"
        # LEAD EDIT 2026-10-01: the live ledger grew a SECOND 401 flavor — codex
        # 0.142.5 ignores a bare OPENAI_API_KEY env var and sends NO credential
        # ("Missing bearer"), distinct from the revoked-key "invalid_api_key"
        # rows. Both are auth failures; the hint roundtrip below still runs on
        # every row. (This pin sweeps a LIVE artifact — the growing-corpus test
        # class — so it names the known flavors instead of assuming one.)
        assert "401" in error and ("invalid_api_key" in error or "Missing bearer" in error), (
            f"a codex failure row with an unknown 401 flavor appeared: {error[:160]!r}"
        )
        # Computed from the LIVE constant table, never a literal copy.
        hint = backends_mod._auth_hint(error)
        assert hint.strip(), f"_AUTH_HINTS no longer recognises a real 401: {error[:120]!r}"
        assert "codex login" in hint, f"the codex remediation regressed: {hint!r}"
        assert hint.strip() in error, (
            "the recorded failure carries the hint the live table still produces — "
            f"table says {hint.strip()!r}"
        )


def test_d9_the_401_fixtures_never_carried_a_usable_key():
    """Hygiene pin on the fixtures themselves: OpenAI masks the key in its 401
    body, and this repo must never start carrying an unmasked one in a tracked
    ledger. (The visible prefix/suffix is the API's own redaction.)"""
    if not SMOKE_LOG.is_file():
        pytest.skip("no smoke log on this box")
    text = SMOKE_LOG.read_text("utf-8")
    for line in text.splitlines():
        if "sk-proj-" not in line:
            continue
        assert "*" in line, f"an unmasked key may be in the smoke ledger: {line[:80]!r}"


# =============================================================================
# E — item 5: S1's writer consults the session policy, per driver
# =============================================================================


class _CapturingDriver:
    """A driver that records its session kwargs, writes the two files the S1
    writer demands, and never spawns anything (the b004 `_CapturingDriver`,
    extended to satisfy `_default_writer_runner`'s disk contract)."""

    def __init__(self, name: str = "localclaude") -> None:
        self.name = name
        self.calls: list[dict] = []

    def session(self, prompt: str, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        cwd = Path(kwargs["cwd"])
        cwd.mkdir(parents=True, exist_ok=True)
        (cwd / "spec.md").write_text("# fake spec\n", encoding="utf-8")
        (cwd / "spec.yaml").write_text("title: fake\n", encoding="utf-8")
        return {"session_id": "capture-1", "usd_cost": 0.0,
                "tokens_in": 0, "tokens_out": 0, "duration_s": 0.0}


def _writer_call(monkeypatch, tmp_path: Path, cfg: dict, driver_name: str) -> dict:
    """Run `_default_writer_runner(cfg)` once against a capturing driver."""
    driver = _CapturingDriver(driver_name)
    monkeypatch.setattr(backends_mod, "get_driver", lambda cfg, role=None: (driver, "m-1"))
    monkeypatch.setattr(s1_spec, "S1_SCRATCH_ROOT", tmp_path / "s1-scratch")

    s1_spec._default_writer_runner(cfg)("WRITE THE SPEC")
    assert len(driver.calls) == 1, f"exactly one writer session per idea: {driver.calls!r}"
    return driver.calls[0]


def test_e1_the_codex_writer_gets_its_sandbox_and_no_claude_only_kwargs(monkeypatch, tmp_path):
    """Item 5: per-driver branches (claude: tools/effort; codex: sandbox).

    PRE-STATE (read off `_default_writer_runner` before the contract): the
    runner branches on `driver.name == "localclaude"` for tools/effort and has
    NO codex arm at all, so a codex writer session is sent bare — no sandbox, no
    policy, the driver's own `workspace-write` default silently in force while
    `backends.codex.session` sits unread. That is the gap; this is the pin.
    """
    cfg = {"backends": {"codex": {"session": {"sandbox": "workspace-write"}}}}
    call = _writer_call(monkeypatch, tmp_path, cfg, "codex")

    assert call.get("sandbox") == "workspace-write", (
        f"the codex writer must carry its sandbox from the policy: {call!r}"
    )
    for claude_only in ("tools", "allowed_tools", "effort", "permission_mode"):
        assert claude_only not in call, (
            f"{claude_only!r} is a localclaude-only kwarg; CodexDriver.session would "
            f"raise TypeError on it: {call!r}"
        )


def test_e2_the_configured_codex_writer_sandbox_is_the_one_used(monkeypatch, tmp_path):
    """`get_session_policy` is CONSULTED, not bypassed: change the config, the
    writer changes. (Today the writer never reads the config at all.)"""
    cfg = {"backends": {"codex": {"session": {"sandbox": "read-only"}}}}
    call = _writer_call(monkeypatch, tmp_path, cfg, "codex")
    assert call.get("sandbox") == "read-only", (
        f"backends.codex.session.sandbox must reach the writer: {call!r}"
    )


@pytest.mark.parametrize("driver_name", ["localclaude", "codex"])
def test_e3_every_writer_kwarg_is_a_real_parameter_of_that_driver(monkeypatch, tmp_path,
                                                                  driver_name):
    """The structural pin behind item 5: whatever the branch decides to pass, it
    must be something that driver's `session()` can actually take."""
    call = _writer_call(monkeypatch, tmp_path, {}, driver_name)
    driver_cls = LocalClaudeDriver if driver_name == "localclaude" else CodexDriver
    parameters = set(inspect.signature(driver_cls.session).parameters)
    unknown = sorted(set(call) - parameters - {"prompt"})
    assert not unknown, (
        f"the S1 writer hands {driver_name} the kwargs {unknown}, which "
        f"{driver_cls.__name__}.session does not accept "
        f"(has {sorted(parameters - {'self'})})"
    )


def test_e4_the_localclaude_writer_keeps_the_b5_scoped_tool_surface(monkeypatch, tmp_path):
    """Item 5 must not widen the writer by splatting the S2 policy wholesale.

    `SESSION_POLICY_DEFAULTS["localclaude"]["allowed_tools"]` is the S2 set and
    contains Bash patterns. The S1 writer's set is `S1_WRITER_TOOLS`
    (Write/Edit/Read) because a writer with Bash spent its session exploring the
    repo instead of writing (the B5 record, quoted in the runner's own
    docstring). Consulting the policy may not undo that.
    """
    call = _writer_call(monkeypatch, tmp_path, {}, "localclaude")

    expected = list(s1_spec.S1_WRITER_TOOLS)
    assert list(call.get("tools") or []) == expected, (
        f"the writer's `tools` must stay S1_WRITER_TOOLS: {call!r}"
    )
    assert list(call.get("allowed_tools") or []) == expected, (
        f"the writer's `allowed_tools` must stay S1_WRITER_TOOLS: {call!r}"
    )
    leaked = [t for t in (call.get("allowed_tools") or []) if "Bash" in t]
    assert not leaked, (
        f"the S2 policy's Bash patterns leaked into the S1 writer: {leaked} — "
        "this is the exact B5 regression"
    )
    assert any("Bash" in t for t in DEFAULT_S2_ALLOWED_TOOLS), (
        "sanity: the S2 default set is the one that carries Bash"
    )


def test_e5_an_unconfigured_localclaude_writer_is_byte_identical_to_today(monkeypatch,
                                                                         tmp_path):
    """HOUSE RULE: unconfigured == today. Today the writer sends
    timeout_s=1800.0 and effort="medium" (both hardcoded). After item 5 those
    come from the policy — and for an EMPTY config the values must not move.

    FLAGGED TENSION (lead adjudicates): `SESSION_POLICY_DEFAULTS["localclaude"]
    ["effort"]` is None, so a naive splat of the policy would send effort=None
    here and drop the `--effort` flag — undoing the B5 deliberation cap for
    every pre-item-5 config. Either the writer keeps its own floor or the
    contract intends the default to move; this pin says the OBSERVED value may
    not silently become None.
    """
    call = _writer_call(monkeypatch, tmp_path, {}, "localclaude")

    assert call.get("timeout_s") == 1800.0, (
        f"an unconfigured writer session keeps today's 1800s ceiling: {call!r}"
    )
    assert call.get("effort") == "medium", (
        f"an unconfigured writer keeps today's deliberation cap (B5): {call!r}"
    )
    assert Path(call["cwd"]).is_dir(), "the writer scratch dir must exist before the session"


def test_e6a_a_configured_writer_timeout_reaches_the_writer(monkeypatch, tmp_path):
    """The point of item 5: the knobs stop being decorative for S1 too.

    The writer hardcoded 1800.0 before the contract while
    `backends.localclaude.session.timeout_s` sat armed at 3600 in the template —
    a signed knob that the longest session in the pipeline ignored.
    """
    cfg = {"backends": {"localclaude": {"session": {"effort": "high", "timeout_s": 3600}}}}
    call = _writer_call(monkeypatch, tmp_path, cfg, "localclaude")

    assert call.get("timeout_s") == 3600, (
        f"backends.localclaude.session.timeout_s must reach the writer: {call!r}"
    )


def test_e6b_a_configured_writer_effort_reaches_the_writer(monkeypatch, tmp_path):
    """FLAGGED AMBIGUITY — for the lead, not for whoever runs this file next.

    Item 5 names the branch as "claude: tools/effort". Two readings:
      (a) the branch SUPPLIES tools and effort from the policy — a configured
          `backends.localclaude.session.effort` then steers the writer, and the
          knob is live at S1 as it already is at S2 (this pin);
      (b) the branch hardcodes both, and "consults get_session_policy" covers
          only the keys the writer does not own — the writer keeps `medium` as
          its own B5 floor whatever the config says.
    (b) has a real argument: `SESSION_POLICY_DEFAULTS["localclaude"]["effort"]`
    is None, so under (a) every config that never set the key would drop
    `--effort` and reopen the B5 failure (a writer that thinks for 30+ minutes
    and emits nothing). E5 is the guard that catches exactly that, so (a) is
    only safe if the writer floors a None policy value rather than passing it.

    The lead rules. If (b), DELETE this test and record the ruling next to
    E5 — do not loosen it into an assertion that accepts both.
    """
    cfg = {"backends": {"localclaude": {"session": {"effort": "high", "timeout_s": 3600}}}}
    call = _writer_call(monkeypatch, tmp_path, cfg, "localclaude")

    assert call.get("effort") == "high", (
        f"backends.localclaude.session.effort must reach the writer: {call!r}"
    )


def test_e7_an_unknown_session_key_still_fails_loud_through_the_writer(monkeypatch,
                                                                      tmp_path):
    """`get_session_policy` rejects unknown keys so a typo cannot silently do
    nothing. Routing the writer through it must inherit that, not route around
    it."""
    cfg = {"backends": {"codex": {"session": {"sandbax": "read-only"}}}}
    with pytest.raises((KeyError, TypeError, ValueError, DriverError)) as excinfo:
        _writer_call(monkeypatch, tmp_path, cfg, "codex")
    assert "sandbax" in str(excinfo.value), (
        f"the raise must name the typo'd key: {excinfo.value}"
    )


# =============================================================================
# F — item 7: check_config validates the backends block
# =============================================================================


def _check(cfg: dict) -> None:
    """`check_config` with its vocab, the shape every caller uses."""
    s0_ideas.check_config(cfg, s0_ideas.load_vocab(cfg))


def _expect_reject(cfg: dict, *needles: str) -> str:
    with pytest.raises(CONFIG_ERRORS) as excinfo:
        _check(cfg)
    message = str(excinfo.value)
    for needle in needles:
        assert needle in message, f"the error must name {needle!r}: {message!r}"
    return message


@pytest.mark.parametrize("config_name", ["template.yaml", "b004-validation.yaml",
                                         "b005r2-auto.yaml"])
def test_f1_the_shipped_configs_still_pass_check_config(tmp_path, config_name):
    """No false positives: item 7 adds a gate, it does not invalidate the batch
    configs the pipeline has already run on."""
    source = REPO_ROOT / "config" / config_name
    if not source.is_file():
        pytest.skip(f"{config_name} not in this tree")
    dest = tmp_path / config_name
    shutil.copyfile(source, dest)
    _check(load_config(dest))


def test_f2_an_unknown_default_driver_is_rejected_at_load(tmp_path):
    """"so misconfig fails at load, not mid-batch" — the whole of item 7."""
    cfg = _template_cfg(tmp_path)
    cfg["backends"]["default_driver"] = "gpt4all"
    _expect_reject(cfg, "gpt4all")


def test_f3_an_unknown_per_stage_driver_is_rejected(tmp_path):
    cfg = _template_cfg(tmp_path)
    cfg["backends"]["per_stage"] = {"implementer": "codex-2"}
    _expect_reject(cfg, "codex-2")


def test_f4_a_missing_model_role_for_the_driver_in_use_is_rejected(tmp_path):
    """"model roles present for the driver in use". Today this is a KeyError at
    `get_driver` time — mid-batch, after S0 has already spent prose tokens."""
    cfg = _template_cfg(tmp_path)
    cfg["backends"]["default_driver"] = "codex"
    cfg["backends"]["codex"]["models"].pop("implementer")
    _expect_reject(cfg, "implementer")


def test_f5_a_per_stage_driver_must_carry_its_own_role_model(tmp_path):
    """The route that actually bites: default localclaude, one stage on codex,
    codex missing exactly that role."""
    cfg = _template_cfg(tmp_path)
    cfg["backends"]["per_stage"] = {"verifier": "codex"}
    cfg["backends"]["codex"]["models"].pop("verifier")
    _expect_reject(cfg, "verifier")


def test_f6_roles_missing_for_an_unused_driver_are_tolerated(tmp_path):
    """Scope: "the driver IN USE". Every shipped config carries a codex block
    that has never run; item 7 must not turn those into hard failures."""
    cfg = _template_cfg(tmp_path)
    assert cfg["backends"]["default_driver"] == "localclaude", "template precondition"
    cfg["backends"]["per_stage"] = {}
    cfg["backends"]["codex"].pop("models", None)
    _check(cfg)  # must not raise


def test_f7_a_complete_codex_backends_block_is_accepted(tmp_path):
    """The lane P-1a exists to open must validate."""
    cfg = _template_cfg(tmp_path)
    cfg["backends"]["default_driver"] = "codex"
    _check(cfg)  # must not raise


def test_f8_a_bad_backends_block_is_rejected_before_any_process_starts(monkeypatch,
                                                                      tmp_path):
    """"fails at load, not mid-batch": the rejection may not cost a driver call."""
    cfg = _template_cfg(tmp_path)
    cfg["backends"]["default_driver"] = "not-a-driver"
    _forbid_all_processes(monkeypatch)
    _expect_reject(cfg, "not-a-driver")


def test_f9_an_unknown_stage_role_in_per_stage_is_rejected(tmp_path):
    """INTERPRETATION, flagged for the lead — the weakest pin in section F.

    Item 7 names "driver names, model roles present for the driver in use". An
    unknown per_stage KEY is neither, strictly: `STAGE_ROLES` is exactly
    {spec_writer, implementer, verifier}, and `get_driver` only ever asks for a
    role it was given, so `per_stage: {auditor: codex}` is a knob that silently
    does nothing forever. Reading it as part of "validates the backends block"
    is the natural extension; if the lead reads item 7 narrowly, DELETE this
    test rather than loosen it — F2-F5 carry the contract's own words.
    """
    cfg = _template_cfg(tmp_path)
    cfg["backends"]["per_stage"] = {"auditor": "codex"}
    _expect_reject(cfg, "auditor")


# =============================================================================
# G — byte-identity: the localclaude lane is untouched
# =============================================================================
# Literals, deliberately: G exists to catch a CONSTANT that moved, so computing
# the expectation from the constant would defeat it.


def test_g1_localclaude_complete_argv_is_byte_identical(monkeypatch):
    calls = _fake_claude_run(monkeypatch)
    LocalClaudeDriver().complete("prose please")
    assert _last(calls) == [
        "claude", "-p", "prose please", "--output-format", "json", "--tools", ""
    ], f"the S0/S1 prose argv moved: {_last(calls)!r}"

    LocalClaudeDriver().complete("prose please", model="claude-sonnet-5")
    assert _last(calls) == [
        "claude", "-p", "prose please", "--output-format", "json", "--tools", "",
        "--model", "claude-sonnet-5",
    ], f"the S0/S1 prose argv moved: {_last(calls)!r}"


def test_g2_localclaude_session_argv_is_byte_identical_under_the_default_policy(
    monkeypatch, tmp_path
):
    calls = _fake_claude_run(monkeypatch)
    LocalClaudeDriver().session("p", cwd=tmp_path, **get_session_policy({}, "localclaude"))
    assert _last(calls) == [
        "claude", "-p", "p", "--output-format", "json",
        "--permission-mode", "acceptEdits",
        "--allowedTools", "Edit", "Write", "Read", "Glob", "Grep",
        "Bash(make *)", "Bash(python *)", "Bash(.venv/bin/python *)",
    ], f"the S2 worker argv moved: {_last(calls)!r}"
    assert calls[-1]["timeout_s"] == 1800.0


def test_g3_the_localclaude_policy_defaults_are_unchanged():
    policy = SESSION_POLICY_DEFAULTS["localclaude"]
    assert set(policy) == {"permission_mode", "allowed_tools", "effort", "timeout_s"}, (
        f"a new localclaude policy key must be splattable into session(): {policy!r}"
    )
    assert policy["permission_mode"] == "acceptEdits"
    assert policy["effort"] is None
    assert policy["timeout_s"] == 1800.0
    assert list(policy["allowed_tools"]) == [
        "Edit", "Write", "Read", "Glob", "Grep",
        "Bash(make *)", "Bash(python *)", "Bash(.venv/bin/python *)",
    ]


def test_g4_no_codex_token_ever_reaches_a_claude_argv(monkeypatch, tmp_path):
    """The two lanes share `_run` and a policy shape. They share no flags."""
    calls = _fake_claude_run(monkeypatch)
    driver = LocalClaudeDriver()
    driver.complete("p")
    driver.session("p", cwd=tmp_path, effort="medium", **{
        k: v for k, v in get_session_policy({}, "localclaude").items() if k != "effort"
    })

    for call in calls:
        cmd = call["cmd"]
        for token in ("-s", "--sandbox", "-c", "--cd", "resume", "--skip-git-repo-check"):
            assert token not in cmd, f"a codex token leaked into a claude argv: {cmd!r}"
        assert CODEX_EFFORT_KEY not in " ".join(cmd), f"codex effort key in claude argv: {cmd!r}"
    # …and the claude effort flag is still the claude one.
    assert _pair(calls[-1]["cmd"], "--effort") == "medium"


def test_g5_neither_driver_ever_constructs_a_bypass_flag(monkeypatch, tmp_path):
    """Operator ruling 2026-09-21, restated across the P-1a surface."""
    claude_calls = _fake_claude_run(monkeypatch)
    LocalClaudeDriver().session("p", cwd=tmp_path)
    codex_calls = _fake_codex_run(monkeypatch)
    CodexDriver().session("p", cwd=tmp_path)
    CodexDriver().complete("p")

    for call in [*claude_calls, *codex_calls]:
        joined = " ".join(call["cmd"])
        for flag in BYPASS_FLAGS:
            assert flag not in joined, f"{flag} constructed: {call['cmd']!r}"


# =============================================================================
# H — P-1b and the lead seam: recorded, never invented
# =============================================================================


# P-1b CLOSED (lead, 2026-10-06): the three TODO skips below became real pins
# the day the evidence existed. The fixture is the VERBATIM first green smoke
# (P-0, 2026-10-01 — see fixtures/README.md); nothing in it is hand-written.
SUCCESS_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "codex-success-events.jsonl"


def _success_events() -> list[dict]:
    assert SUCCESS_FIXTURE.is_file(), (
        f"fixture wall: {SUCCESS_FIXTURE} is gone — it is the P-0 capture every "
        "P-1b pin stands on"
    )
    return [json.loads(line) for line in
            SUCCESS_FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_h1_codex_session_id_key_is_pinned_against_a_real_success_payload():
    """P-1b: the resume handle is `thread_id` on the `thread.started` event —
    measured on the first green run (P-0) and pinned here over its verbatim
    capture, exactly as backends.py's own docstring asked ("Pin the exact key
    here once the first green codex session lands")."""
    events = _success_events()
    started = [e for e in events if e.get("type") == "thread.started"]
    assert len(started) == 1 and isinstance(started[0].get("thread_id"), str), (
        "the fixture's thread.started event must carry the top-level `thread_id` "
        f"the extractor was built for; got {started!r}"
    )
    assert backends_mod._codex_session_id(events) == started[0]["thread_id"], (
        "`_codex_session_id` must return the real stream's thread_id — the handle "
        "`codex exec resume <SESSION_ID>` accepts"
    )


def test_h2_codex_success_payload_ledger_fields():
    """P-1b: the success-path ledger fields, pinned over the verbatim capture —
    usd_cost None (codex prices nothing, the cost-note's whole premise),
    tokens from `turn.completed`'s usage block."""
    events = _success_events()
    usage = [e for e in events if e.get("type") == "turn.completed"][-1]["usage"]
    fields = backends_mod._codex_result_fields(events, [])
    assert fields["usd_cost"] is None, (
        f"codex reports no dollars; a non-None usd here ({fields['usd_cost']!r}) would "
        "silently un-justify backends.unpriced_driver_note"
    )
    assert fields["tokens_in"] == usage["input_tokens"] == 29838, (
        f"tokens_in must be the stream's own input_tokens; got {fields['tokens_in']!r}"
    )
    assert fields["tokens_out"] == usage["output_tokens"] == 19, (
        f"tokens_out must be the stream's own output_tokens; got {fields['tokens_out']!r}"
    )


@pytest.mark.skip(reason=(
    "P-1b ACCEPTANCE MET (recorded 2026-10-06, not a unit test): the live "
    "codex single-game run through the FULL unchanged ladder happened twice — "
    "g20261001-5 (lantern-path-parity-trace, resumed to packaged 5/5 on "
    "2026-10-05) and g20261006-1 (echo-quilt, born fresh and packaged 5/5 in "
    "24 minutes on 2026-10-06). Both games are on the tracked shelf; the "
    "TRACKER close log carries the evidence."
))
def test_h3_live_codex_single_game_acceptance():
    raise AssertionError("unreachable while skipped")


# UNSKIPPED AT THE LEAD'S MERGE (2026-09-30), body lead-authored: the
# orchestrator seam landed as `_cost_note(cfg)` at the two COST_NOTE
# consumers, extending the note via backends.unpriced_driver_note.
def test_h4_the_cost_note_says_codex_sessions_are_unpriced():
    from gen import orchestrator as orch

    codex_cfg = {"backends": {"default_driver": "codex", "per_stage": {}}}
    note = orch._cost_note(codex_cfg)
    assert note.startswith(orch.COST_NOTE), note
    assert "codex" in note and "unpriced" in note, note

    claude_cfg = {"backends": {"default_driver": "localclaude", "per_stage": {}}}
    assert orch._cost_note(claude_cfg) == orch.COST_NOTE
