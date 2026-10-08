"""B0/B3 — agent driver abstraction (D25).

One interface, two drivers, uniform across S1/S2/S3:
  localclaude -> local `claude` CLI (claude -p for single-shot; headless worker
                 session for S2, wrapped by the coded green-loop)
  codex       -> local `codex` CLI (codex exec; --cd <worker> for S2 — the
                 upstream re-arc-3 shape)
Selected per stage via config `backends.{default_driver,per_stage}`.
Captures cost per call (claude --output-format json usage; codex token counts
where reported; wall-time always) into the run ledger.

B0 shipped single-shot `complete()`. B3 adds `session()` — one S2 worker turn
run inside a worker directory with tools scoped and a resume handle returned,
so the coded green-loop can chain turns. Both modes share the same payload
parsers (`_claude_payload`/`_claude_fields`, `_codex_*`), so a CLI shape change
is fixed in one place. Auth belongs to the CLIs (OAuth session / key in the
user's environment) — this module never reads, stores, or logs credential
values, and never constructs a permission-bypass flag.

Payload shapes verified against the installed CLIs (claude 2.1.232,
codex-cli 0.142.5) on 2026-09-21; fixtures under gen/tests/fixtures/.
Notably: claude reports auth failures with exit 1 + is_error=true and the
error text in `result` while `subtype` still reads "success" — so exit code
and is_error are the error signals, never subtype.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

SMOKE_TIMEOUT_S = 300.0
# S2 worker turns are long by design; the green-loop caps attempts, not minutes.
SESSION_TIMEOUT_S = 1800.0

# --- S2 session policy (B3) -------------------------------------------------
# Operator ruling 2026-09-21: scoped tools, no permission bypass. The worker gets
# exactly what reaching green needs — edit its game, read around it, run its
# make/python targets — and nothing more. `--dangerously-skip-permissions` is
# never constructed anywhere in this module.
DEFAULT_S2_ALLOWED_TOOLS = (
    "Edit", "Write", "Read", "Glob", "Grep",
    "Bash(make *)", "Bash(python *)", "Bash(.venv/bin/python *)",
)
DEFAULT_PERMISSION_MODE = "acceptEdits"
# `--permission-mode` choices, read off `claude --help` (2.1.232) on 2026-09-21.
CLAUDE_PERMISSION_MODES = frozenset(
    {"acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan"}
)
# The bypass under its own name — refused by the ruling above, config or not.
BYPASS_PERMISSION_MODES = frozenset({"bypassPermissions"})

DEFAULT_CODEX_SANDBOX = "workspace-write"
# `-s/--sandbox` choices, read off `codex exec --help` (0.142.5) on 2026-09-21.
CODEX_SANDBOX_MODES = frozenset({"read-only", "workspace-write", "danger-full-access"})
# P-1a item 1. `complete()` is the PURE single-shot completion API (S0 prose),
# and until P-1a it constructed NO `-s` at all and inherited the CALLER's cwd —
# so an S0 draw run from the repo root opened a tool-capable codex agent inside
# this repository. Read-only + a private cwd is codex's nearest equivalent of
# the localclaude lane's `--tools ""` (the B5 lesson, see complete() below).
CODEX_COMPLETE_SANDBOX = "read-only"

# P-1a item 4 — the auth preflight's two sources. `backends.codex.auth_env`
# NAMES the variable (its value never appears in config, and this module never
# reads, stores or logs the value itself); `codex login` writes the file. EITHER
# one present is a pass — the 401s on record are a stale env key shadowing a
# login, which presence alone cannot and must not judge.
CODEX_AUTH_ENV_DEFAULT = "OPENAI_API_KEY"


def codex_auth_file() -> Path:
    """`~/.codex/auth.json`, resolved AT CALL TIME, never at import.

    LEAD FIX 2026-10-01: this was a module-level constant, so a test's tmp HOME
    could never redirect it — latent until the first real `codex login` put an
    auth.json on this box and test_v2_cli's T2b started finding it through the
    patched environment. Same class, same cure as P-4's call-time root
    constants.
    """
    return Path.home() / ".codex" / "auth.json"

# Code-side fallbacks for get_session_policy() — a config written before B3
# (no backends.<driver>.session block) must still start a worker.
SESSION_POLICY_DEFAULTS = {
    "localclaude": {
        "permission_mode": DEFAULT_PERMISSION_MODE,
        "allowed_tools": list(DEFAULT_S2_ALLOWED_TOOLS),
        # None = the CLI's default deliberation. The R2 pilot found that an
        # UNCAPPED S2 session can sit >30 min in silent thinking and die on
        # SESSION_TIMEOUT_S with zero output (B5 recorded the same for S1,
        # which is why run_s1 passes effort explicitly). `session()` validates
        # the value and omits the flag when None, so old configs are
        # byte-identical.
        "effort": None,
        # The wall-clock ceiling on ONE worker turn, in seconds. Code default =
        # SESSION_TIMEOUT_S (1800), so an unconfigured run is exactly today's
        # run. MEASURED over b001-b003: legitimate attempt-1 sessions ran
        # 252-1646s, and 6 of ~20 attempt-1 sessions died ON this ceiling with
        # empty output — 1800 clips roughly the top 30% of the distribution.
        # Raising it is a config decision (see `backends.<driver>.session
        # .timeout_s`), never a code one.
        "timeout_s": SESSION_TIMEOUT_S,
    },
    # Symmetric: both drivers' session() take `timeout_s`, so both admit the
    # key. The codex lane has never completed a smoke (AUTH-2), so 1800 here is
    # the code default and nothing more.
    #
    # `effort` (P-1a item 2) is the codex ANALOG of the localclaude key above:
    # codex has no `--effort` flag, so the equivalent is the config override
    # `-c model_reasoning_effort=<v>` on the `codex exec` parent. Born None =
    # the flag is omitted, so every config written before P-1a — and
    # `get_session_policy({}, "codex")` — is byte-identical.
    "codex": {
        "sandbox": DEFAULT_CODEX_SANDBOX,
        "effort": None,
        "timeout_s": SESSION_TIMEOUT_S,
    },
}

# Substring (lowercased) -> user-side remediation, appended to DriverError
# messages so an auth failure at any stage prints its own fix.
_AUTH_HINTS = (
    ("oauth session expired", "remediation (user-side): run `claude auth login` in a terminal, then re-run"),
    ("failed to authenticate", "remediation (user-side): run `claude auth login` in a terminal, then re-run"),
    ("invalid_api_key", "remediation (user-side): set a valid OPENAI_API_KEY, or unset it and `codex login`, then re-run"),
    ("401 unauthorized", "remediation (user-side): set a valid OPENAI_API_KEY, or unset it and `codex login`, then re-run"),
)


class DriverError(RuntimeError):
    """A driver call failed: non-zero exit, error payload, bad shape, or timeout."""


class DriverConfigError(DriverError):
    """The CALL was misconfigured: the provider says the requested model does not exist.

    CONTRACT H-1 item 1 (2026-10-06). A subclass, so every `except DriverError`
    in the pipeline still catches it — but a class of its own, because it is
    neither of the two things a DriverError used to be able to mean: it is not
    the WORK failing (no agent ever ran, so the green loop has nothing to judge
    and must not spend an attempt), and it is not an OUTAGE (waiting cannot
    create a model, so the infrastructure ladder must not retry it either). It
    is a config typo, and the only correct handling is to stop the run loudly
    at the first sighting. Raised by `_driver_failure` when the provider's reply
    matches `is_model_config_error`; routed by `s2_implement.green_loop`, which
    re-raises it instead of recording an attempt.
    """


def _excerpt(text: str, limit: int = 500) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]} … {text[-half:]}"


def _auth_hint(text: str) -> str:
    low = (text or "").lower()
    for needle, hint in _AUTH_HINTS:
        if needle in low:
            return f"\n{hint}"
    return ""


# The remediation a model-config failure prints (contract H-1 item 1), worded
# like `_AUTH_HINTS` so every user-side fix in this module reads the same way.
MODEL_CONFIG_HINT = (
    "remediation (user-side): the provider does not serve the requested model — this is "
    "a CONFIG error, not an outage, and no retry can fix it. Correct the model name in "
    "`backends.<driver>.models.<role>` (or the --model you passed), then re-run"
)


def _driver_failure(message: str, evidence: str) -> DriverError:
    """The exception for a failed provider reply: config-class when it says so.

    `message` is the caller's composed text (unchanged for every failure that is
    not a model-config one — those keep their exact bytes and their exact
    class). `evidence` is the RAW reply text the class is decided from, never
    the excerpt in the message, so a needle past the excerpt's cut is still
    seen. `is_model_config_error` lives with the other failure-classification
    table at the bottom of this module and is resolved at call time.
    """
    if is_model_config_error(evidence):
        return DriverConfigError(f"{message}\n{MODEL_CONFIG_HINT}")
    return DriverError(message)


@dataclass
class CompletionResult:
    driver: str
    model_requested: str | None
    model_reported: str | None
    text: str
    usd_cost: float | None  # None = the CLI did not report a $ figure (never estimated)
    tokens_in: int | None  # as reported by the CLI; full usage payload in `raw`
    tokens_out: int | None
    duration_s: float
    exit_code: int
    cmd: list[str]
    raw: dict

    def to_record(self) -> dict:
        return asdict(self)


@dataclass
class SessionResult:
    """One S2 worker turn.

    Same ledger fields as CompletionResult plus `session_id` — the handle the
    green-loop feeds back as `resume_id` to continue the same conversation.
    None means the CLI did not report one (never fabricated; see
    `_codex_session_id`).
    """

    driver: str
    model_requested: str | None
    model_reported: str | None
    text: str
    usd_cost: float | None  # None = the CLI did not report a $ figure (never estimated)
    tokens_in: int | None
    tokens_out: int | None
    duration_s: float
    exit_code: int
    session_id: str | None
    cmd: list[str]
    raw: dict

    def to_record(self) -> dict:
        return asdict(self)


def _check_timeout_s(driver: str, timeout_s: object) -> None:
    """A session timeout must be a finite, positive number of seconds.

    Called from both drivers' `session()` — the one layer that sees the value
    whether the caller came through `get_session_policy` (where the config key
    `backends.<driver>.session.timeout_s` lands) or called `session()` direct.
    Config is yaml, so the value can be anything: a bool is not a duration,
    a string would reach `subprocess.run` and blow up there blaming the CLI,
    `inf`/`nan` is a session nothing ever kills, and <= 0 kills it at birth.
    All four are config typos in a signed knob, so they fail here, loudly,
    before a worker turn is opened.
    """
    key = f"backends.{driver}.session.timeout_s"
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
        raise DriverError(
            f"[{driver}] timeout_s must be a number of seconds, got {timeout_s!r} "
            f"({type(timeout_s).__name__}) — set {key} to a positive number"
        )
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise DriverError(
            f"[{driver}] timeout_s must be finite and > 0, got {timeout_s!r} "
            f"— set {key} to a positive number of seconds"
        )


def _check_codex_sandbox(driver: str, sandbox: object) -> None:
    """`-s/--sandbox` must name a mode the installed CLI accepts.

    Lifted out of `CodexDriver.session()` verbatim (P-1a item 1) so
    `complete()`, which now constructs the same flag, refuses the same values
    with the same message. The `isinstance` guard is new and only widens what
    is CAUGHT: a yaml list reaching `in frozenset` used to raise an unhandled
    TypeError, which blamed nothing in particular.
    """
    if not isinstance(sandbox, str) or sandbox not in CODEX_SANDBOX_MODES:
        raise DriverError(
            f"[{driver}] unknown sandbox {sandbox!r} — "
            f"codex 0.142.5 accepts {sorted(CODEX_SANDBOX_MODES)}"
        )


def _check_codex_effort(driver: str, effort: object) -> str:
    """The `-c model_reasoning_effort=<v>` value — SHAPE checked, enum is not.

    TODO(P-1b): pin the accepted value enum off `codex exec --help` (0.142.5)
    when the lane first runs. P-1a is a hermetic contract and may not invoke
    the binary, so inventing an enum here would be exactly the fabrication
    `_codex_session_id` refuses further down this file. What IS checkable
    without the CLI is that the value cannot corrupt the override it rides in:
    `-c` takes one `key=value` token, so whitespace (which would split the
    token) and `=` (which would move the key) are refused, and so is anything
    that is not a non-empty string.
    """
    key = f"backends.{driver}.session.effort"
    if not isinstance(effort, str) or not effort:
        raise DriverError(
            f"[{driver}] effort must be a non-empty string, got {effort!r} "
            f"({type(effort).__name__}) — set {key} to a codex reasoning-effort "
            "value, or null to omit the flag"
        )
    if any(char.isspace() for char in effort) or "=" in effort:
        raise DriverError(
            f"[{driver}] effort {effort!r} carries whitespace or '=' — it is sent as the "
            f"single token `model_reasoning_effort={effort}` to `codex -c`, which either "
            f"would break; set {key} to a bare value"
        )
    return effort


def _codex_auth_fix(auth_env: str) -> str:
    """The user-side remediation line, worded exactly as `_AUTH_HINTS` does."""
    return f"set a valid {auth_env}, or unset it and `codex login`, then re-run"


def _run(cmd: list[str], driver: str, timeout_s: float, cwd: Path | None = None) -> tuple[subprocess.CompletedProcess, float]:
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s,
            cwd=str(cwd) if cwd else None, check=False,
            # A CLI child must NEVER wait on our stdin: an inherited open pipe
            # is a silent forever-hang in headless runs.
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        # Surface what the child had printed — a timeout with partial output
        # localizes the stall.
        def _txt(blob) -> str:
            if blob is None:
                return ""
            return blob if isinstance(blob, str) else blob.decode("utf-8", "replace")

        out, err = _excerpt(_txt(exc.stdout)), _excerpt(_txt(exc.stderr))
        if not out and not err:
            # C-C (2026-09-28): "partial stdout: <empty>" was read for a year as
            # evidence that the session stalled before its first byte. It is
            # not. `claude -p --output-format json` BUFFERS the whole payload
            # until completion, so for a claude session those partials are
            # STRUCTURALLY empty however much work the agent did — the old
            # message implied evidence that cannot exist. Say the truth
            # instead. The exception type and the "timed out after Ns" prefix
            # are preserved verbatim: the attempt records and
            # `is_infrastructure_error`'s deliberate NON-match both key off
            # them.
            raise DriverError(
                f"[{driver}] timed out after {timeout_s:.0f}s with no output captured "
                "(print-mode buffers until completion — empty partials say nothing "
                "about progress)."
            ) from exc
        raise DriverError(
            f"[{driver}] timed out after {timeout_s:.0f}s. partial stdout: "
            f"{out or '<empty>'} | partial stderr: {err or '<empty>'}"
        ) from exc
    except FileNotFoundError as exc:
        raise DriverError(f"[{driver}] CLI not found: {cmd[0]!r}") from exc
    return proc, time.monotonic() - t0


def _claude_payload(proc: subprocess.CompletedProcess, driver: str) -> dict:
    """Decode and judge a `claude --output-format json` stdout payload.

    The result JSON arrives on stdout even for auth failures (exit 1,
    is_error=true, error text in `result`) — parse first, then judge. `subtype`
    reads "success" on those, so exit code and is_error are the only error
    signals. Shared by complete() and session().
    """
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise _driver_failure(
            f"[{driver}] exit {proc.returncode}, non-JSON stdout: "
            f"{_excerpt(proc.stdout)} | stderr: {_excerpt(proc.stderr)}"
            + _auth_hint(proc.stdout + proc.stderr),
            proc.stdout + proc.stderr,
        ) from None
    if proc.returncode != 0 or payload.get("is_error"):
        detail = payload.get("result") or _excerpt(proc.stderr)
        raise _driver_failure(
            f"[{driver}] exit {proc.returncode}, is_error={payload.get('is_error')}: {detail}"
            + _auth_hint(str(detail)),
            f"{payload.get('result') or ''}\n{proc.stderr}",
        )
    return payload


@dataclass
class _ClaudeFields:
    text: str
    usd_cost: float
    tokens_in: int | None
    tokens_out: int | None
    model_reported: str | None
    session_id: str | None


def _claude_fields(payload: dict, driver: str) -> _ClaudeFields:
    """Pull the ledger fields out of a claude result payload (fail-loud on shape).

    `session_id` is the CLI's own field — the same value `--resume` takes.
    """
    for key in ("result", "total_cost_usd", "usage"):
        if key not in payload:
            raise DriverError(
                f"[{driver}] payload missing {key!r} — fields present: {sorted(payload)}"
            )
    usage = payload["usage"]
    model_usage = payload.get("modelUsage") or {}
    session_id = payload.get("session_id")
    return _ClaudeFields(
        text=payload["result"],
        usd_cost=float(payload["total_cost_usd"]),
        tokens_in=usage.get("input_tokens"),
        tokens_out=usage.get("output_tokens"),
        model_reported=next(iter(model_usage)) if len(model_usage) == 1 else None,
        session_id=session_id if isinstance(session_id, str) and session_id else None,
    )


class LocalClaudeDriver:
    name = "localclaude"

    def __init__(self, claude_bin: str = "claude"):
        self.claude_bin = claude_bin

    def complete(self, prompt: str, *, model: str | None = None,
                 timeout_s: float = SMOKE_TIMEOUT_S) -> CompletionResult:
        # `--tools ""` disables ALL tools: complete() is the PURE single-shot
        # completion API (S0 prose, S1 spec writing). Without it, headless
        # claude runs a full agent loop in the caller's cwd — the first real
        # S1 call spent 30+ minutes running git and READING OUR TEST FIXTURES
        # instead of answering (B5 smoke, 2026-09-21). Tool-ful work is
        # session()'s job, scoped by the S2 policy.
        cmd = [self.claude_bin, "-p", prompt, "--output-format", "json", "--tools", ""]
        if model:
            cmd += ["--model", model]
        proc, duration = _run(cmd, self.name, timeout_s)
        payload = _claude_payload(proc, self.name)
        fields = _claude_fields(payload, self.name)
        return CompletionResult(
            driver=self.name,
            model_requested=model,
            model_reported=fields.model_reported,
            text=fields.text,
            usd_cost=fields.usd_cost,
            tokens_in=fields.tokens_in,
            tokens_out=fields.tokens_out,
            duration_s=duration,
            exit_code=proc.returncode,
            cmd=cmd,
            raw=payload,
        )

    def session(self, prompt: str, *, cwd: Path, model: str | None = None,
                resume_id: str | None = None, timeout_s: float = SESSION_TIMEOUT_S,
                permission_mode: str = DEFAULT_PERMISSION_MODE,
                allowed_tools: Sequence[str] | None = None,
                effort: str | None = None,
                tools: Sequence[str] | None = None) -> SessionResult:
        """One S2 worker turn: `claude -p` with tools scoped, run inside `cwd`.

        Shape verified against `claude --help` (2.1.232) on 2026-09-21:
          claude -p <prompt> --output-format json --permission-mode <mode>
                 --allowedTools <t1> <t2> … [--model <m>] [--resume <id>]
        `--allowedTools <tools...>` is variadic and takes comma- or
        space-separated patterns; every argument appended after it here starts
        with `-`, so the list cannot swallow one. `--resume <session_id>` is
        valid alongside `-p`, and the id comes from the previous turn's
        `session_id` — parsed by the same helpers complete() uses.

        Refuses a bypass permission mode and never constructs
        `--dangerously-skip-permissions` (operator ruling 2026-09-21).
        """
        if not cwd.is_dir():
            # Checked here because subprocess would raise FileNotFoundError and
            # _run would then blame the CLI binary instead of the worker dir.
            raise DriverError(f"[{self.name}] worker cwd is not a directory: {cwd}")
        _check_timeout_s(self.name, timeout_s)
        if permission_mode not in CLAUDE_PERMISSION_MODES:
            raise DriverError(
                f"[{self.name}] unknown permission_mode {permission_mode!r} — "
                f"claude 2.1.232 accepts {sorted(CLAUDE_PERMISSION_MODES)}"
            )
        if permission_mode in BYPASS_PERMISSION_MODES:
            raise DriverError(
                f"[{self.name}] permission_mode {permission_mode!r} is a permission bypass "
                "— refused (operator ruling 2026-09-21: scoped tools, no permission bypass)"
            )
        if isinstance(allowed_tools, str):
            raise DriverError(
                f"[{self.name}] allowed_tools must be a sequence of tool patterns, not the "
                f"bare string {allowed_tools!r} (it would be split into characters)"
            )
        allowed = list(DEFAULT_S2_ALLOWED_TOOLS if allowed_tools is None else allowed_tools)
        if not allowed or not all(isinstance(t, str) and t for t in allowed):
            raise DriverError(
                f"[{self.name}] allowed_tools must be non-empty strings, got {allowed!r} "
                "— pass None for the S2 default set"
            )

        cmd = [self.claude_bin, "-p", prompt, "--output-format", "json",
               "--permission-mode", permission_mode, "--allowedTools", *allowed]
        if model:
            cmd += ["--model", model]
        if resume_id:
            cmd += ["--resume", resume_id]
        if effort is not None:
            # `claude --help` (2.1.232): low, medium, high, xhigh, max. Used
            # by S1 to cap runaway deliberation on doc-writing sessions
            # (three real attempts sank 30+ min into thinking; B5 record).
            if effort not in ("low", "medium", "high", "xhigh", "max"):
                raise DriverError(f"[{self.name}] unknown effort {effort!r}")
            cmd += ["--effort", effort]
        if tools is not None:
            # --tools LIMITS the built-in tool SET; --allowedTools only
            # auto-APPROVES within it. A doc-writing session restricted with
            # allowedTools alone still explored the repo with Bash (B5
            # record) — sessions that must not roam pass both.
            if not tools or any(not isinstance(t, str) or not t for t in tools):
                raise DriverError(
                    f"[{self.name}] tools must be non-empty strings, got {tools!r} "
                    "(use complete() for a no-tools call)"
                )
            cmd += ["--tools", ",".join(tools)]
        proc, duration = _run(cmd, self.name, timeout_s, cwd=cwd)
        payload = _claude_payload(proc, self.name)
        fields = _claude_fields(payload, self.name)
        return SessionResult(
            driver=self.name,
            model_requested=model,
            model_reported=fields.model_reported,
            text=fields.text,
            usd_cost=fields.usd_cost,
            tokens_in=fields.tokens_in,
            tokens_out=fields.tokens_out,
            duration_s=duration,
            exit_code=proc.returncode,
            session_id=fields.session_id,
            cmd=cmd,
            raw=payload,
        )


def _find_usage_events(events: list[dict]) -> list[dict]:
    """Every dict under a 'usage' key that carries token integers, in stream order."""
    found: list[dict] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            usage = node.get("usage")
            if isinstance(usage, dict) and any(
                isinstance(usage.get(k), int) for k in ("input_tokens", "output_tokens")
            ):
                found.append(usage)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for event in events:
        walk(event)
    return found


def _codex_events(stdout: str) -> tuple[list[dict], list[str]]:
    """Split `codex exec --json` stdout into decoded JSONL events + undecodable lines."""
    events: list[dict] = []
    unparsed: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            unparsed.append(line)
            continue
        if isinstance(event, dict):
            events.append(event)
    return events, unparsed


def _codex_guard(proc: subprocess.CompletedProcess, events: list[dict], driver: str) -> None:
    """Raise unless the run succeeded: non-zero exit or a `turn.failed` event."""
    failed = [e for e in events if e.get("type") == "turn.failed"]
    if proc.returncode != 0 or failed:
        detail = (
            (failed[0].get("error") or {}).get("message")
            if failed else _excerpt(proc.stderr or proc.stdout)
        )
        raise _driver_failure(
            f"[{driver}] exit {proc.returncode}"
            f"{', turn.failed' if failed else ''}: {_excerpt(str(detail))}"
            + _auth_hint(str(detail) + proc.stderr),
            # Provider-side text only: without a `turn.failed`, `detail` can be
            # an excerpt of STDOUT — the event stream, agent messages included —
            # and an agent's own words must never decide a stop-the-run class.
            f"{detail if failed else ''}\n{proc.stderr}",
        )


def _codex_last_message(msg_path: Path, events: list[dict],
                        proc: subprocess.CompletedProcess, driver: str) -> str:
    """Read the `-o` last-agent-message file; a green run that wrote none is a failure."""
    if not msg_path.is_file() or not msg_path.read_text(encoding="utf-8").strip():
        raise DriverError(
            f"[{driver}] exit 0 but no last message was written — "
            f"events: {[e.get('type') for e in events][-8:]} | stderr: {_excerpt(proc.stderr)}"
        )
    return msg_path.read_text(encoding="utf-8").strip()


def _codex_result_fields(events: list[dict], unparsed: list[str]) -> dict:
    """The ledger fields shared by codex complete() and session()."""
    usage_events = _find_usage_events(events)
    last_usage = usage_events[-1] if usage_events else {}
    cost = next(
        (e[k] for e in events for k in ("total_cost_usd", "cost_usd")
         if isinstance(e.get(k), (int, float))),
        None,
    )
    model_reported = next(
        (e[k] for e in events for k in ("model",) if isinstance(e.get(k), str)),
        None,
    )
    return {
        "model_reported": model_reported,
        "usd_cost": float(cost) if cost is not None else None,
        "tokens_in": last_usage.get("input_tokens"),
        "tokens_out": last_usage.get("output_tokens"),
        "raw": {
            "event_types": [e.get("type") for e in events],
            "usage_events": usage_events,
            "unparsed_lines": len(unparsed),
            "unparsed_first": unparsed[0] if unparsed else None,
        },
    }


# `codex exec --json` tags its session-open event `thread.started` (the 0.142.5
# binary's serde table lists exactly: thread.started, turn.started,
# turn.completed, turn.failed, item.started, item.updated, item.completed).
# `session_meta` is the on-disk rollout spelling, kept here because the same
# scan reads a rollout line if one is ever piped in.
_CODEX_SESSION_EVENT_TYPES = ("thread.started", "session.created", "session_meta")
# Never a bare "id" off an arbitrary event — item.* events carry their own ids.
_CODEX_SESSION_ID_KEYS = ("thread_id", "session_id", "conversation_id", "threadId")
_CODEX_SESSION_EVENT_ID_KEYS = (*_CODEX_SESSION_ID_KEYS, "id")


def _codex_session_id(events: list[dict]) -> str | None:
    """Best-effort resume handle from a codex event stream; None when absent.

    NOT confirmed against a green run — no codex success payload exists yet
    (auth blocked since B0; see gen/tests/fixtures/README.md). What is verified
    on this box (2026-09-21): the event tag is `thread.started`, and the on-disk
    rollout writes `session_meta` whose payload.id == payload.session_id == the
    UUID that `codex exec resume <SESSION_ID>` accepts. So: scan the
    session-open events first (where a bare `id` is safe), then any event for an
    explicit thread/session key, and return None rather than invent a handle —
    the green-loop must treat None as "cannot resume, start fresh". Pin the
    exact key here once the first green codex session lands.
    """
    def pick(node: dict, keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = node.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    for event in events:
        if event.get("type") not in _CODEX_SESSION_EVENT_TYPES:
            continue
        for node in (event, event.get("payload")):
            if isinstance(node, dict):
                found = pick(node, _CODEX_SESSION_EVENT_ID_KEYS)
                if found:
                    return found
    for event in events:
        for node in (event, event.get("payload")):
            if isinstance(node, dict):
                found = pick(node, _CODEX_SESSION_ID_KEYS)
                if found:
                    return found
    return None


class CodexDriver:
    name = "codex"

    def __init__(self, codex_bin: str = "codex"):
        self.codex_bin = codex_bin

    def complete(self, prompt: str, *, model: str | None = None,
                 timeout_s: float = SMOKE_TIMEOUT_S, cwd: Path | None = None,
                 sandbox: str = CODEX_COMPLETE_SANDBOX) -> CompletionResult:
        """One single-shot codex completion, CONTAINED (P-1a item 1).

        Shape (`-s` belongs to the `codex exec` parent and precedes the rest;
        the prompt is always last):

            codex exec -s <sandbox> --skip-git-repo-check --json -o <tmp>
                 [-m <model>] <prompt>

        TWO containment changes against the pre-P-1a shape, and both exist
        because this is the PURE completion API — S0 prose asks a question and
        wants an answer, not an agent loop:

        * `-s read-only` by default. Before P-1a no `-s` was constructed at
          all, so the CLI's own default applied to a call that has no business
          writing anything. This is the codex analog of the localclaude lane's
          `--tools ""` (see LocalClaudeDriver.complete: without it the first
          real S1 call spent 30+ minutes reading our test fixtures).
        * a PRIVATE cwd. `cwd=None` used to inherit the caller's directory,
          which for `gen/s0_ideas._default_prose_runner` is the repo root; it
          now runs in the same temp dir the `-o` file already lives in. An
          explicitly passed `cwd` is honoured unchanged.

        `--cd` is deliberately NOT constructed: the process cwd is the whole
        story for a fresh `exec`, and `session()`'s `--cd` exists only because
        `resume` needs the parent to carry it.
        """
        _check_timeout_s(self.name, timeout_s)
        _check_codex_sandbox(self.name, sandbox)
        with tempfile.TemporaryDirectory(prefix="codex-exec-") as tmp:
            msg_path = Path(tmp) / "last_message.txt"
            cmd = [self.codex_bin, "exec", "-s", sandbox,
                   "--skip-git-repo-check", "--json", "-o", str(msg_path)]
            if model:
                cmd += ["-m", model]
            cmd.append(prompt)
            proc, duration = _run(
                cmd, self.name, timeout_s, cwd=Path(tmp) if cwd is None else cwd
            )
            events, unparsed = _codex_events(proc.stdout)
            _codex_guard(proc, events, self.name)
            text = _codex_last_message(msg_path, events, proc, self.name)

        fields = _codex_result_fields(events, unparsed)
        return CompletionResult(
            driver=self.name,
            model_requested=model,
            model_reported=fields["model_reported"],
            text=text,
            usd_cost=fields["usd_cost"],
            tokens_in=fields["tokens_in"],
            tokens_out=fields["tokens_out"],
            duration_s=duration,
            exit_code=proc.returncode,
            cmd=cmd,
            raw=fields["raw"],
        )

    def preflight(self, *, auth_env: str = CODEX_AUTH_ENV_DEFAULT,
                  auth_file: Path | None = None) -> None:
        """Presence-check the codex credential and discard it (P-1a item 4).

        Mirrors `OpenRouterDriver.preflight`: a stage calls this BEFORE it
        spends time (or tokens) so a missing credential is a usage error at
        second zero instead of a failure mid-batch. The codex CLI authenticates
        from either the named environment variable or a `codex login` on this
        box, so EITHER present is a pass.

        This checks PRESENCE only, and that is the whole guarantee: the four
        codex failures on record (`out/smoke/smoke.jsonl`) are 401s from a
        STALE env key, which is present and wrong. A preflight cannot tell a
        stale key from a live one without spending — it can only refuse to
        spend when there is nothing to spend with.

        The value is never returned, logged, or put in a message. Call sites:
        `gen/smoke.py` today; the P-4 CLI's pre-spend preflight next.
        """
        if not isinstance(auth_env, str) or not auth_env.strip():
            raise DriverError(
                f"[{self.name}] auth_env must be a non-empty variable NAME, got "
                f"{auth_env!r} — see backends.codex.auth_env"
            )
        name = auth_env.strip()
        if (os.environ.get(name) or "").strip():
            return
        path = codex_auth_file() if auth_file is None else Path(auth_file)
        if path.is_file():
            return
        raise DriverError(
            f"[{self.name}] no {name} in the environment and no codex login on this box "
            f"({path} is absent) — the codex lane authenticates from one or the other. "
            f"Fix: {_codex_auth_fix(name)}"
        )

    def session(self, prompt: str, *, cwd: Path, model: str | None = None,
                resume_id: str | None = None, timeout_s: float = SESSION_TIMEOUT_S,
                sandbox: str = DEFAULT_CODEX_SANDBOX,
                effort: str | None = None) -> SessionResult:
        """One S2 worker turn: `codex exec` rooted at `cwd`, sandboxed.

        Shapes verified against `codex exec --help` / `codex exec resume --help`
        (0.142.5) on 2026-09-21 (`[-c …]` added by P-1a, same parent placement
        rule as `--cd`/`-s`; omitted entirely when `effort` is None):
          fresh   codex exec --cd <cwd> -s <sandbox> [-c <k>=<v>]
                       --skip-git-repo-check --json -o <tmp> [-m <model>] <prompt>
          resume  codex exec --cd <cwd> -s <sandbox> [-c <k>=<v>] resume
                       --skip-git-repo-check --json -o <tmp> [-m <model>]
                       <session_id> <prompt>

        `codex exec resume [OPTIONS] [SESSION_ID] [PROMPT]` carries --json, -o,
        -m and --skip-git-repo-check itself, so the session keeps the same
        parsing as a fresh run. It does NOT accept -s/--sandbox or -C/--cd:
        those live only on the `codex exec` parent and must precede the
        subcommand. Checked both placements — after `resume`, clap exits 2
        ("unexpected argument '-s' found"); before it, the full command parses.
        Both shapes were parse-checked with a trailing `--help`, which
        short-circuits before any session starts; whether the parent's
        --cd/-s also bind the *resumed* turn at runtime is NOT verified here
        and needs the lead's first real resume. `cwd` is passed to the
        subprocess as well, so --cd and the process agree either way.

        `--dangerously-bypass-approvals-and-sandbox` is never constructed.
        """
        if not cwd.is_dir():
            # Checked here because subprocess would raise FileNotFoundError and
            # _run would then blame the CLI binary instead of the worker dir.
            raise DriverError(f"[{self.name}] worker cwd is not a directory: {cwd}")
        _check_timeout_s(self.name, timeout_s)
        _check_codex_sandbox(self.name, sandbox)

        with tempfile.TemporaryDirectory(prefix="codex-session-") as tmp:
            msg_path = Path(tmp) / "last_message.txt"
            # --cd/-s belong to the `codex exec` parent and must come first —
            # `resume` rejects them (clap: "unexpected argument '-s' found").
            cmd = [self.codex_bin, "exec", "--cd", str(cwd), "-s", sandbox]
            if effort is not None:
                # codex has NO `--effort` flag (LocalClaudeDriver.session's
                # analog); the equivalent is a config override, and it rides on
                # the PARENT for the same clap reason --cd/-s do. None omits it,
                # which is what keeps an unconfigured run byte-identical.
                cmd += ["-c", f"model_reasoning_effort={_check_codex_effort(self.name, effort)}"]
            if resume_id:
                cmd.append("resume")
            # The rest `resume` accepts in its own right, so both shapes parse
            # and are read back by the same helpers.
            cmd += ["--skip-git-repo-check", "--json", "-o", str(msg_path)]
            if model:
                cmd += ["-m", model]
            if resume_id:
                cmd.append(resume_id)  # positional [SESSION_ID], then [PROMPT]
            cmd.append(prompt)
            proc, duration = _run(cmd, self.name, timeout_s, cwd=cwd)
            events, unparsed = _codex_events(proc.stdout)
            _codex_guard(proc, events, self.name)
            text = _codex_last_message(msg_path, events, proc, self.name)

        fields = _codex_result_fields(events, unparsed)
        return SessionResult(
            driver=self.name,
            model_requested=model,
            model_reported=fields["model_reported"],
            text=text,
            usd_cost=fields["usd_cost"],
            tokens_in=fields["tokens_in"],
            tokens_out=fields["tokens_out"],
            duration_s=duration,
            exit_code=proc.returncode,
            session_id=_codex_session_id(events),
            cmd=cmd,
            raw=fields["raw"],
        )


DRIVERS = {LocalClaudeDriver.name: LocalClaudeDriver, CodexDriver.name: CodexDriver}

STAGE_ROLES = ("spec_writer", "implementer", "verifier")


def get_driver(cfg: dict, role: str | None = None):
    """Resolve (driver, model) for a stage role from cfg['backends'].

    role=None (smoke/probes) -> the default driver with no model pinned.
    """
    backends = cfg["backends"]
    if role is not None and role not in STAGE_ROLES:
        raise KeyError(f"unknown stage role {role!r} — expected one of {STAGE_ROLES}")
    name = (backends.get("per_stage") or {}).get(role) or backends["default_driver"]
    if name not in DRIVERS:
        raise KeyError(f"unknown driver {name!r} — expected one of {sorted(DRIVERS)}")
    driver = DRIVERS[name]()
    model = None
    if role is not None:
        models = backends[name]["models"]
        if role not in models:
            raise KeyError(f"backends.{name}.models missing role {role!r} (has {sorted(models)})")
        model = models[role]
    return driver, model


def get_session_policy(cfg: dict, driver_name: str) -> dict:
    """The S2 session policy for `driver_name`: config layered over code defaults.

    Reads `backends.<driver>.session` from cfg on top of SESSION_POLICY_DEFAULTS,
    so a config written before B3 (no session block) still starts a worker with
    the signed defaults. Returns kwargs for that driver's `session()` — exactly
    the keys of that driver's `SESSION_POLICY_DEFAULTS` block:
      localclaude -> {"permission_mode", "allowed_tools", "effort", "timeout_s"}
      codex       -> {"sandbox", "effort", "timeout_s"}   ("effort" added by P-1a)

    Structure is validated here and fails loud — an unknown key is a typo that
    would otherwise silently do nothing. Value checks (mode/sandbox names, the
    permission-bypass refusal) live in the drivers' session(), the one place
    they are enforced whether the caller came through this function or not.
    """
    if driver_name not in SESSION_POLICY_DEFAULTS:
        raise KeyError(
            f"unknown driver {driver_name!r} — expected one of {sorted(SESSION_POLICY_DEFAULTS)}"
        )
    defaults = SESSION_POLICY_DEFAULTS[driver_name]
    block = (cfg.get("backends") or {}).get(driver_name) or {}
    configured = block.get("session") or {}
    if not isinstance(configured, dict):
        raise TypeError(
            f"backends.{driver_name}.session must be a mapping, "
            f"got {type(configured).__name__}"
        )
    unknown = sorted(set(configured) - set(defaults))
    if unknown:
        raise KeyError(
            f"backends.{driver_name}.session has unknown keys {unknown} "
            f"— expected any of {sorted(defaults)}"
        )
    policy = {**defaults, **configured}
    if "allowed_tools" in policy:
        tools = policy["allowed_tools"]
        if isinstance(tools, str) or not isinstance(tools, Sequence):
            raise TypeError(
                f"backends.{driver_name}.session.allowed_tools must be a list of tool "
                f"patterns, got {tools!r}"
            )
        policy["allowed_tools"] = list(tools)
    return policy


# --- the codex lane's config surface (P-1a items 4, 6, 7) --------------------


def codex_auth_env(cfg: Mapping) -> str:
    """`backends.codex.auth_env` — the variable name the codex preflight checks.

    Until P-1a nothing read this key, so every config in the tree carried a
    decorative `auth_env: OPENAI_API_KEY`. Absent it still defaults, so a
    config that never wrote the key behaves exactly as it did; a key written
    as anything but a non-empty NAME is a loud ValueError, because a credential
    VALUE in a tracked config is the one mistake this repo must never let pass
    quietly — and because a typo here would preflight the wrong variable.
    """
    backends = cfg.get("backends") if isinstance(cfg, Mapping) else None
    block = backends.get("codex") if isinstance(backends, Mapping) else None
    if not isinstance(block, Mapping) or "auth_env" not in block:
        return CODEX_AUTH_ENV_DEFAULT
    value = block["auth_env"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"backends.codex.auth_env must be a non-empty variable NAME, got {value!r} "
            "— it names the environment variable the codex preflight checks; the VALUE "
            "never appears in config"
        )
    return value.strip()


# P-1a item 6 — the DATA half of the cost-honesty note. The codex CLI reports
# no dollar figure at all (`_codex_result_fields` can only fill `usd_cost` from
# a `total_cost_usd`/`cost_usd` event key, and codex emits neither), so a codex
# batch's cost table is structurally $0.0000 and would read as free.
# THE SEAM IS THE LEAD'S: `gen/orchestrator.py`'s COST_NOTE consumers get
#     note = COST_NOTE
#     extra = backends.unpriced_driver_note(cfg)
#     if extra:
#         note = f"{note}; {extra}"
# after Wave A merges (the approved plan keeps two pairs out of orchestrator.py).
UNPRICED_DRIVERS = frozenset({"codex"})
UNPRICED_DRIVER_NOTES = {"codex": "codex sessions are unpriced by the CLI"}


def configured_driver_names(cfg: Mapping) -> list[str]:
    """The driver names this config actually uses, in resolution order.

    `backends.default_driver` first, then each `backends.per_stage` value, each
    name once. TOLERANT BY DESIGN — it is read by reporting code, not by a
    validator, so a malformed block yields fewer names rather than an
    exception. `check_backends_config` is the function that judges.
    """
    backends = cfg.get("backends") if isinstance(cfg, Mapping) else None
    if not isinstance(backends, Mapping):
        return []
    names: list[str] = []
    default = backends.get("default_driver")
    if isinstance(default, str) and default:
        names.append(default)
    per_stage = backends.get("per_stage")
    if isinstance(per_stage, Mapping):
        for role in STAGE_ROLES:
            name = per_stage.get(role)
            if isinstance(name, str) and name:
                names.append(name)
    return list(dict.fromkeys(names))


def unpriced_driver_note(cfg: Mapping) -> str | None:
    """The cost-honesty sentence for cfg's drivers, or None when all are priced.

    None for every batch run to date (localclaude everywhere), which is what
    makes the lead's one-line seam a no-op until a codex batch runs.
    """
    notes = [
        UNPRICED_DRIVER_NOTES[name]
        for name in configured_driver_names(cfg)
        if name in UNPRICED_DRIVERS
    ]
    return "; ".join(notes) if notes else None


def check_backends_config(cfg: Mapping) -> None:
    """Every `backends:` error, raised before a batch spends anything (P-1a 7).

    Called from `gen/s0_ideas.check_config`, whose docstring is the bar:
    "Every STRICT config error, raised before a single prose token is spent."
    Until P-1a a driver typo surfaced at `get_driver` MID-BATCH, after S0 had
    already paid for its prose.

    AN ABSENT `backends` BLOCK IS SKIPPED, silently and deliberately. Partial
    configs are handed to `check_config` all over the suite and by every caller
    that only wants the sampler; such a config already fails loudly at
    `get_driver`, and refusing it here would change behaviour for configs this
    contract has no ruling about. A block that is PRESENT is judged in full.

    Only drivers IN USE are checked. Every config in the tree carries a
    complete, unused `backends.codex` block — checking the unused lane would
    turn a spare-tyre config into a refused one.

    Every failure is a ValueError carrying the dotted path, matching
    `check_config`'s contract (`get_driver` raises KeyError for the same
    mistake later, which is exactly the late failure this replaces).
    """
    if not isinstance(cfg, Mapping) or "backends" not in cfg:
        return
    backends = cfg["backends"]
    if not isinstance(backends, Mapping):
        raise ValueError(  # noqa: TRY004 — check_config's contract is ValueError (P-1a §7d)
            f"backends must be a mapping, got {type(backends).__name__} — it carries "
            "default_driver, per_stage and one block per driver"
        )

    default = backends.get("default_driver")
    if not isinstance(default, str) or not default:
        raise ValueError(
            f"backends.default_driver must be a driver name, got {default!r} "
            f"— expected one of {sorted(DRIVERS)}"
        )
    if default not in DRIVERS:
        raise ValueError(
            f"backends.default_driver {default!r} is not a driver — expected one of "
            f"{sorted(DRIVERS)}"
        )

    per_stage = backends.get("per_stage") or {}
    if not isinstance(per_stage, Mapping):
        raise ValueError(  # noqa: TRY004 — check_config's contract is ValueError (P-1a §7d)
            "backends.per_stage must be a mapping of stage role -> driver, got "
            f"{type(per_stage).__name__}"
        )
    for role, name in per_stage.items():
        if role not in STAGE_ROLES:
            raise ValueError(
                f"backends.per_stage has unknown stage role {role!r} — expected any of "
                f"{list(STAGE_ROLES)}"
            )
        if not isinstance(name, str) or name not in DRIVERS:
            raise ValueError(
                f"backends.per_stage.{role} {name!r} is not a driver — expected one of "
                f"{sorted(DRIVERS)}"
            )

    for name in configured_driver_names(cfg):
        block = backends.get(name)
        if not isinstance(block, Mapping):
            raise ValueError(  # noqa: TRY004 — check_config's contract is ValueError (P-1a §7d)
                f"backends.{name} must be a mapping — {name!r} is in use "
                "(default_driver/per_stage) and needs its own block"
            )
        models = block.get("models")
        if not isinstance(models, Mapping):
            raise ValueError(  # noqa: TRY004 — check_config's contract is ValueError (P-1a §7d)
                f"backends.{name}.models must be a mapping of stage role -> model, got "
                f"{type(models).__name__}"
            )
        missing = [
            role for role in STAGE_ROLES
            if not (isinstance(models.get(role), str) and models[role].strip())
        ]
        if missing:
            raise ValueError(
                f"backends.{name}.models is missing {missing} — {name!r} is in use and "
                f"every stage role in {list(STAGE_ROLES)} must name a model"
            )

    if CodexDriver.name in configured_driver_names(cfg):
        codex_auth_env(cfg)  # raises on a malformed auth_env


# --- OpenRouter: the battery player (B9, D12) --------------------------------
# D12 (LOCKED 2026-09-17): the difficulty battery is played by OUR agent, the
# duck, over OpenRouter, at the D8 budget. That lane is not a CLI: it is one
# HTTPS chat completion per turn, no tools, no cwd, no resume handle — so it
# gets its own verb (`chat`) and its own result shape rather than being bent
# into complete()/session(). stdlib `urllib` only; no new dependency (the B9
# contract's rule, and the repo's).
#
# SECRETS. The key lives in the environment as OPENROUTER_API_KEY and belongs
# to the operator. This module checks its PRESENCE, puts its value in exactly one
# place — the Authorization header of the request — and nowhere else: not in
# `cmd`-style records (there are none), not in `ChatResult.raw`, not in any
# DriverError. `_scrub` is the belt-and-braces for the one path we do not
# control, a server that echoes a request back inside an error body.

OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_TIMEOUT_S = 120.0
# Carried verbatim in every missing/rejected-key error: the user's own fix.
OPENROUTER_EXPORT_LINE = f"export {OPENROUTER_KEY_ENV}=<your key>"
# OpenRouter's usage-accounting opt-in: with it the response's `usage` block
# carries token counts and, when the account exposes it, `cost`. Verified
# against the live API at the lead's smoke — until then the fakes in tests
# freeze OUR ChatResult shape, never theirs.
OPENROUTER_USAGE_REQUEST = {"include": True}
_OPENROUTER_MESSAGE_KEYS = ("role", "content")


def _scrub(text: str, secret: str) -> str:
    """`text` with `secret` replaced — a key value never travels in a message."""
    if secret and secret in text:
        return text.replace(secret, "<redacted>")
    return text


def _usage_int(value: object) -> int | None:
    """A usage token count, or None. A bool or a non-int is not a count."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _usage_float(value: object) -> float | None:
    """A usage cost, or None. Never estimated here (CompletionResult's rule)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


@dataclass(frozen=True)
class ChatResult:
    """One chat completion, in the ledger's vocabulary.

    `tokens_in`/`tokens_out`/`usd_cost` are None when the response's `usage`
    block did not carry them — missing numbers are NEVER invented, exactly as
    for CompletionResult/SessionResult. What an unreported number costs is the
    spending stage's call: `gen/s5_battery.py` charges a documented
    conservative estimate so a usage-less lane cannot run unbounded.

    `raw` is the decoded response body. It contains what the server sent and
    never anything we sent, so no credential can reach it.
    """

    driver: str
    model_requested: str
    model_reported: str | None
    text: str
    tokens_in: int | None
    tokens_out: int | None
    usd_cost: float | None
    raw: dict

    def to_record(self) -> dict:
        return asdict(self)


class OpenRouterDriver:
    """The battery player's transport: one POST, one reply, no state.

    NO session mode. A battery turn is a complete conversation on its own and
    the stage owns the turn-to-turn state (gen/s5_battery.py states the choice
    and its token math), so there is no resume handle to fabricate.
    """

    name = "openrouter"

    def __init__(self, url: str = OPENROUTER_URL):
        self.url = url

    def _api_key(self) -> str:
        """The key from the environment. Fails loud, prints the user's fix.

        The VALUE is returned only to the one caller that puts it in the auth
        header; it is never returned out of this class (see `preflight`).
        """
        key = (os.environ.get(OPENROUTER_KEY_ENV) or "").strip()
        if not key:
            raise DriverError(
                f"[{self.name}] no {OPENROUTER_KEY_ENV} in the environment — the battery "
                f"plays through OpenRouter (D12). Fix: {OPENROUTER_EXPORT_LINE}"
            )
        return key

    def preflight(self) -> None:
        """Presence-check the key and discard it.

        A stage calls this before it spends time driving a game, so a missing
        key is a usage error at second zero instead of a crash mid-battery.
        """
        self._api_key()

    def _payload(self, messages: Sequence[dict], model: str, max_tokens: int) -> dict:
        """The request body, built from ONLY role/content + the frozen knobs."""
        if isinstance(messages, str) or not isinstance(messages, Sequence) or not messages:
            raise DriverError(
                f"[{self.name}] messages must be a non-empty list of "
                f"{{'role','content'}} mappings, got {type(messages).__name__}"
            )
        if not isinstance(model, str) or not model.strip():
            raise DriverError(f"[{self.name}] model must be a non-empty string, got {model!r}")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
            raise DriverError(
                f"[{self.name}] max_tokens must be a positive int, got {max_tokens!r}"
            )
        cleaned = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise DriverError(
                    f"[{self.name}] messages[{index}] must be a mapping, "
                    f"got {type(message).__name__}"
                )
            missing = [key for key in _OPENROUTER_MESSAGE_KEYS if key not in message]
            if missing:
                raise DriverError(f"[{self.name}] messages[{index}] missing {missing}")
            role, content = message["role"], message["content"]
            if not isinstance(role, str) or not role:
                raise DriverError(
                    f"[{self.name}] messages[{index}].role must be a non-empty string"
                )
            if not isinstance(content, str):
                raise DriverError(
                    f"[{self.name}] messages[{index}].content must be a string, "
                    f"got {type(content).__name__}"
                )
            # Only these two keys are forwarded: nothing the caller happens to
            # hang on a message can ride along to a third party.
            cleaned.append({"role": role, "content": content})
        return {
            "model": model,
            "messages": cleaned,
            "max_tokens": max_tokens,
            "usage": dict(OPENROUTER_USAGE_REQUEST),
        }

    def chat(self, messages: list[dict], *, model: str,
             max_tokens: int = 1024, timeout_s: float = OPENROUTER_TIMEOUT_S) -> ChatResult:
        """POST one chat completion and read the reply.

        Request shape (stdlib urllib, no session, no retry — retries are the
        caller's policy):

            POST {OPENROUTER_URL}
            Authorization: Bearer <$OPENROUTER_API_KEY>
            Content-Type: application/json
            {"model": …, "messages": [{"role","content"} …],
             "max_tokens": …, "usage": {"include": true}}

        Raises DriverError on a missing key, a transport failure, a non-2xx
        status (status + body excerpt), an undecodable body, an API-level
        `error` object, or a response that carries no assistant text. Token
        counts and cost come from the response's `usage` block when it has
        them and are None when it does not.
        """
        key = self._api_key()
        body = json.dumps(self._payload(messages, model, max_tokens)).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                raw_body = response.read().decode("utf-8", "replace")
                status = int(response.status)
        except urllib.error.HTTPError as exc:  # a URLError subclass — catch it first
            try:
                detail = exc.read().decode("utf-8", "replace")
            except Exception:  # noqa: BLE001 — a body we cannot read is not the failure
                detail = str(exc.reason)
            hint = (
                f" Fix: {OPENROUTER_EXPORT_LINE}"
                if exc.code in (401, 403)
                else ""
            )
            raise _driver_failure(
                f"[{self.name}] HTTP {exc.code} from {self.url}: "
                f"{_scrub(_excerpt(detail), key)}{hint}",
                f"HTTP {exc.code}\n{_scrub(detail, key)}",
            ) from None
        except OSError as exc:  # URLError, TimeoutError, DNS, TLS …
            raise DriverError(
                f"[{self.name}] request to {self.url} failed: {_scrub(str(exc), key)}"
            ) from None

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            raise DriverError(
                f"[{self.name}] HTTP {status} with a non-JSON body: "
                f"{_scrub(_excerpt(raw_body), key)}"
            ) from None
        if not isinstance(payload, dict):
            raise DriverError(
                f"[{self.name}] HTTP {status} body decoded to "
                f"{type(payload).__name__}, expected an object"
            )
        # OpenRouter can answer 200 with an `error` object instead of choices.
        error = payload.get("error")
        if isinstance(error, dict):
            raise _driver_failure(
                f"[{self.name}] API error {error.get('code')}: "
                f"{_scrub(_excerpt(str(error.get('message') or error)), key)}",
                f"API error {error.get('code')}: {_scrub(str(error), key)}",
            )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise DriverError(
                f"[{self.name}] response carries no choices — keys present: {sorted(payload)}"
            )
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message")
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str):
            raise DriverError(
                f"[{self.name}] choices[0] carries no message.content "
                f"(finish_reason={first.get('finish_reason')!r})"
            )
        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        reported = payload.get("model")
        return ChatResult(
            driver=self.name,
            model_requested=model,
            model_reported=reported if isinstance(reported, str) and reported else None,
            text=text,
            tokens_in=_usage_int(usage.get("prompt_tokens")),
            tokens_out=_usage_int(usage.get("completion_tokens")),
            usd_cost=_usage_float(usage.get("cost")),
            raw=payload,
        )


# Registered by mutation, not by rewriting the literal above: the B9 addition
# to this file is append-only.
DRIVERS[OpenRouterDriver.name] = OpenRouterDriver


# --- infrastructure vs. the work (b002 contract 2, D2) ----------------------
#
# THE DEFECT this answers: `s2_implement.green_loop` turns ANY exception from a
# session runner into a consumed attempt. A DriverError for an expired OAuth
# session, an account usage limit, a 429 or a `claude` binary that is not on
# PATH therefore spends the green-attempt cap on an outage, and two such runs
# route the SLOT to dead (`orchestrator.GREEN_CAP_DEATHS`) — an account limit
# killing a game.
#
# THE LINE, and it is the whole contract: a session that RAN and FAILED is
# never infrastructure. The driver timing out mid-session, a payload whose
# shape is wrong, `codex` writing no last message, a red `make validate`, a
# refused permission mode — all of those are the work or the wiring, they are
# the green loop's own business, and NONE of their wordings appears below. Only
# the call never reaching a working agent at all is infrastructure: the
# credential, the account, the throttle, the missing binary.
#
# Matched on TEXT, because text is all a DriverError carries: every raise site
# in this module folds its cause into a message and most use `from None`. The
# needles are therefore this module's own wordings where it has them (the
# `_AUTH_HINTS` table, `_run`'s FileNotFoundError branch, `_api_key`) and the
# vendors' where it does not — those are marked, because they are NOT verified
# against a live failure on this box, exactly as `_codex_session_id` marks its
# own unverified key. This tuple is the renegotiable part of the contract; the
# `is_infrastructure_error` semantics above it are not.
INFRASTRUCTURE_ERROR_SUBSTRINGS = (
    # --- auth: the credential, not the work ---------------------------------
    # Verified here: the four needles of the `_AUTH_HINTS` remediation table,
    # which exist precisely because these are the strings the two CLIs print.
    "oauth session expired",
    "failed to authenticate",
    "invalid_api_key",
    "401 unauthorized",
    # Verified here: `OpenRouterDriver._api_key`'s own refusal, composed from
    # the constant so a renamed env var moves the needle with it.
    f"no {OPENROUTER_KEY_ENV.lower()} in the environment",
    # Verified here: `CodexDriver.preflight`'s refusal (P-1a item 4). Keyed on
    # the half of the sentence that does NOT carry the variable name, because
    # the name is configurable (`backends.codex.auth_env`) and the needle must
    # not move with it. A credential that is absent is the same class of
    # failure as one that is rejected — the call never reaches an agent.
    "no codex login on this box",
    # UNVERIFIED (vendor wordings, not seen on this box): API error bodies.
    "authentication_error",
    "no auth credentials",
    # --- usage limits: the account, not the work ----------------------------
    # UNVERIFIED (vendor wordings): "Claude AI usage limit reached|<epoch>",
    # an exhausted plan, an empty balance. No amount of retrying fixes these,
    # and that is the point: they must BLOCK the slot loudly instead of
    # quietly spending its attempts.
    "usage limit",
    "quota exceeded",
    "insufficient_quota",
    "credit balance is too low",
    # --- rate limits: the throttle, not the work ----------------------------
    # "429" is deliberately bare: every shape a 429 reaches us in spells the
    # number (`HTTP 429 from …`, `API error 429:`, `API Error: 429 {…}`) and
    # no two of them spell it the same way. The cost of the false positive it
    # buys is bounded and visible — a bounded wait, then a verdict file that
    # quotes the error text verbatim — while the false negative is the defect
    # this contract exists to fix.
    "429",
    "too many requests",
    "rate limit",
    "rate-limit",
    "rate_limit",
    # --- the CLI itself is missing ------------------------------------------
    "cli not found",  # verified: `_run`'s FileNotFoundError branch
)


# --- the config vs. the work (contract H-1 item 1) --------------------------
#
# THE DEFECT: g20261001-2 named a model that does not exist (`gpt-5.4-codex`).
# Every codex session died before an agent ran, with
#   `[codex] exit 1, turn.failed: unexpected status 404 Not Found: The model
#    `gpt-5.4-codex` does not exist or you do not have access to it., url: …`
# (out/corpus/g20261001-2/patrol-cover-yard/worker.attempts.jsonl).
# That text is neither the work (`is_infrastructure_error`'s line: a session
# that RAN and failed) nor an outage (none of the needles above match it), so
# the green loop did the only other thing it knew: consumed an attempt per
# reply — 12 per loop, two loops, 24 rows, and the SLOT went to `dead` on
# "green-attempts cap ×2" (out/batches/g20261001-2/ledger.jsonl) over a typo.
# And the smoke could not have caught it: it runs on the CLI's DEFAULT model.
#
# So a reply that says "no such model" is its own, third class: a CONFIG error.
# `_driver_failure` raises `DriverConfigError` for it at the driver's own error
# path, and `s2_implement.green_loop` re-raises that before recording anything.
#
# Matched on TEXT for the reason the table above is. Bare "404" is deliberately
# NOT a needle (unlike the bare "429" above): a 404 always arrives with words
# around it in every shape below, and a bare number is too cheap a match for a
# class whose handling is to STOP the run.
MODEL_CONFIG_ERROR_SUBSTRINGS = (
    # Verified here: the codex/OpenAI reply on record (g20261001-2, above) —
    # both halves of it, so either wording alone still routes.
    "does not exist or you do not have access to it",
    "404 not found",
    # UNVERIFIED (vendor wordings, not seen on this box): the Anthropic API's
    # error type for an unknown model, which `claude -p` surfaces in `result`
    # as `API Error: 404 {"type":"error","error":{"type":"not_found_error",…}}`;
    # OpenAI's / OpenRouter's error codes; and the HTTP-status spellings this
    # module's OWN raise sites compose (`HTTP 404 from …`, `API error 404: …`).
    "not_found_error",
    "model_not_found",
    "model not found",
    "api error: 404",
    "api error 404",
    "http 404",
)


def is_model_config_error(error: object) -> bool:
    """Does this failure say the requested MODEL does not exist (a config error)?

    Takes an exception or a string and returns False for anything else, on
    `is_infrastructure_error`'s terms and for its reason (called from inside
    exception handlers; an unreadable failure must not be promoted to a class
    whose handling is to stop the run).
    """
    if isinstance(error, BaseException):
        text = str(error)
    elif isinstance(error, str):
        text = error
    else:
        return False
    low = text.lower()
    return any(needle in low for needle in MODEL_CONFIG_ERROR_SUBSTRINGS)


def is_infrastructure_error(error: object) -> bool:
    """Is this failure the DRIVER being unavailable, rather than the work failing?

    True for exactly four classes — auth, usage/account limits, rate limits,
    and a CLI that is not installed — matched case-insensitively against the
    error's text (`INFRASTRUCTURE_ERROR_SUBSTRINGS`, whose comments name the
    raise site or the vendor for every needle).

    Takes an exception OR a string, because the two callers have different
    things in hand. Anything else returns False rather than raising: this
    function is called from inside exception handlers, and the conservative
    direction is to let an unreadable failure be treated as ordinary work —
    it costs one attempt, where a wrong True blocks a whole slot.

    NOT infrastructure, and each of these is a deliberate exclusion:
      * a session that ran and TIMED OUT (`_run`'s TimeoutExpired branch) —
        the agent was there and was working, it just took too long;
      * a payload with the wrong shape, a `codex` run that wrote no last
        message, a non-JSON stdout — the call landed and came back wrong;
      * every local refusal in `session()` (bad cwd, unknown permission_mode,
        a permission bypass, bad allowed_tools/effort/tools) — a config bug,
        which retrying hides and which must fail on the first attempt;
      * transport failures (handshake/timeout/connection-reset) — a separate
        class with a separate, much shorter retry, owned by the caller that
        has one (`gen/s5_battery.py`'s `TRANSPORT_ERROR_SUBSTRINGS`);
      * a model that does not exist (`is_model_config_error`, contract H-1
        item 1) — a CONFIG error, which waiting cannot fix: it stops the run.
    """
    if isinstance(error, BaseException):
        text = str(error)
    elif isinstance(error, str):
        text = error
    else:
        return False
    low = text.lower()
    return any(needle in low for needle in INFRASTRUCTURE_ERROR_SUBSTRINGS)
