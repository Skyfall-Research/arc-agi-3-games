"""B002 resilience acceptance: an infrastructure outage is not a game defect.

Run: .venv/bin/python -m pytest gen/tests/test_b002_resilience.py -q

Written FROM THE CONTRACT ("Sequential resilience (contract 2) — infrastructure
errors are not game defects", frozen 2026-09-24) and from the two sibling
fixture recipes it points at (`test_b3_green_loop.py`, `test_b9_battery.py`).
None of the three edited files — `gen/s5_battery.py`, `gen/s2_implement.py`,
`gen/backends.py` — was read while this file was written. Every name below is
either one the contract itself names or one this file DISCOVERS at runtime,
and every constant it could have hard-coded (both backoff ladders, both try
counts, both needle lists) is MEASURED from the shipped behaviour instead, so
a renegotiated constant cannot make a pin lie and cannot make one pass for the
wrong reason.

The four contract pins, and where they live:

  group A — the battery's rate-limit ladder (contract A1 / pin 1).
      A 429-class error is retried on its own, LONGER ladder and the turn
      succeeds; the retry count is recorded; ladder exhausted leaves the
      existing crash path untouched. REGRESSION: every connection-class
      needle still retries on the transport ladder, byte-identical.
  group B — the green loop's outage handling (contract A2 / pin 2).
      An infrastructure `DriverError` retries the SAME attempt index and
      appends no `AttemptRecord`; the exhausted ladder aborts the loop with
      reject_reason "driver-unavailable" and a verdict file that blames
      infrastructure, not the game.
  group C — non-infrastructure errors (pin 3).
      Byte-for-byte today's behaviour: one attempt consumed, the record's
      `session` is exactly `{"error": "<ExcClass>: <text>"}`.
  group D — the classifier truth table (pin 4).
      auth / usage-limit / rate-limit / CLI-missing -> True; a validate
      failure and a plain RuntimeError -> False. Three of the four True rows
      are REAL `DriverError`s produced here by the shipped drivers (a missing
      key, an HTTP 429, an absent CLI), not texts this file invented.

NO TEST SLEEPS. An autouse fixture replaces `time.sleep` and the modules' own
`_sleep` seam with a recorder for every test in this file, and fails the test
afterwards if the wall clock says a backoff slept for real anyway.

NO NETWORK. An autouse fixture replaces `urllib.request.urlopen` and
`socket.create_connection` with raisers and deletes `OPENROUTER_API_KEY`; the
one fixture that needs a driver to reach "HTTP" installs its own fake
`urlopen` on top and asserts its obviously-fake key never rides an error text.

CONTRACT AMBIGUITIES this file had to take a position on (reported to the
lead, never invented quietly):

  A. "The retry count rides the report next to transport_retries" does not
     name the field. Group A reads the crash record's retry counters BY SHAPE
     (every key containing "retr"), requires `transport_retries` to survive
     and a DISTINCT sibling to carry the rate-limit count, and requires
     `transport_retries` to stay 0 when no transport error ever happened — a
     counter that reports transport retries that did not occur is a lie in
     the report.
  B. A successful battery run surfaces NO retry counter anywhere in its
     report (measured: the shipped report only carries `transport_retries`
     inside `crash`). So "retry count recorded" is pinned on the ledger for
     the recovering turn and on the crash record for the exhausted one, which
     is where the contract sentence sits.
  C. Retry-After is explicitly optional in A1 ("if headers are not reachable
     from the error text, a fixed generous ladder ... and say so in a
     comment"). Nothing here pins a specific ladder: the ladder is measured
     and only its contract-frozen properties are asserted (bounded, more than
     one try, non-decreasing, strictly longer in total than transport's).
  D. `green_loop`'s reject FILE layout for the new reason is not frozen. The
     pins are: `ImplementReport.reject_reason == "driver-unavailable"`, the
     file names that reason, the file says "infrastructure", and its verdict
     is NOT the ordinary `reject-to-S1` — that verdict routes the slot back
     to spec-writing, i.e. it blames the game, which the contract forbids.
  E. Whether a NON-`DriverError` exception carrying infrastructure text (e.g.
     `test_b3_green_loop.py`'s `FakeDriverError("... OAuth session expired")`,
     whose existing pin requires the attempt to be CONSUMED) should classify
     as infrastructure is NOT decidable from the contract, and the two
     readings contradict each other. Nothing here pins it; group C uses only
     unambiguous non-infrastructure texts. FLAGGED TO THE LEAD.
  F. `report.attempts` on a driver-unavailable abort is not frozen. Group B
     asserts `attempts == len(records) == 0`, the only reading of "does NOT
     consume an attempt" that also keeps the report self-consistent.
  G. The orchestrator clause in A2 (GREEN_CAP_DEATHS routing) is explicitly
     out of scope for this contract, so no test here touches the
     orchestrator; the seam is A's to report.
"""

from __future__ import annotations

import dataclasses
import io
import json
import shutil
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from gen import backends, s2_implement, s5_battery
from gen.backends import (
    OPENROUTER_KEY_ENV,
    OPENROUTER_URL,
    ChatResult,
    DriverError,
    LocalClaudeDriver,
    OpenRouterDriver,
)
from gen.config import load_config
from gen.s2_implement import (
    ATTEMPTS_SUFFIX,
    REJECT_SUFFIX,
    REJECT_VERDICT,
    REPORT_SUFFIX,
    green_loop,
    sidecar,
)
from gen.s4_baselines import run_s4
from gen.s5_battery import (
    CSV_NAME,
    REPORT_NAME,
    STATUS_COMPLETE,
    STATUS_CRASH,
    TRANSPORT_ATTEMPTS,
    TRANSPORT_BACKOFF_S,
    TRANSPORT_ERROR_SUBSTRINGS,
    run_battery,
)
from gen.worker import instantiate_worker

TESTS = Path(__file__).resolve().parent
TOY = TESTS / "toy_worker"
PILOT_CONFIG = "config/b001-pilot.yaml"
CFG = load_config(PILOT_CONFIG)

#: the S4 seed the b9 sibling uses on this worker (verdict `fit`).
S4_SEED = 7

MODEL = "fake/duck-v0"
MESSAGES = [{"role": "user", "content": "play"}]

#: never a real key — asserted absent from every error text it could reach.
FAKE_KEY = "sk-or-v1-FAKE-KEY-DO-NOT-USE-0000000000000000"
ABSENT_CLI = "claude-not-installed-b002-resilience"

#: the contract's one frozen string for the new green-loop reject.
DRIVER_UNAVAILABLE = "driver-unavailable"

#: "bounded ladders" is frozen; the contract's own examples are 3 tries. A
#: ladder longer than this is not bounded in any useful sense — a whole
#: sequential run would stall behind one dead slot.
MAX_LADDER_TRIES = 6

#: every test here is arithmetic plus a handful of ~0.6 s `make validate`
#: subprocesses. A test that takes longer slept for real.
WALL_LIMIT_S = 45.0

# A connection-class error (pin 1's regression half) and a rate-limit one.
TRANSPORT_TEXT = "[openrouter] connection reset by peer"
RATE_LIMIT_TEXT = (
    "[openrouter] HTTP 429 from https://openrouter.ai/api/v1/chat/completions: "
    '{"error":{"message":"Rate limit exceeded"}}'
)

# --- the classifier truth table (pin 4) --------------------------------------
# The contract's four True classes, in the phrasings the real surfaces use.
# Three more True rows are REAL errors built by `real_infra_errors` below.
INFRASTRUCTURE_TEXTS = [
    ("auth-oauth", "[localclaude] exit 1: OAuth session expired"),
    ("usage-limit", "[localclaude] exit 1: Claude AI usage limit reached|1758870000"),
    ("usage-limit-prose", "[codex] exit 1: You have hit your usage limit. Try again later."),
    ("rate-limit-prose", "[openrouter] exit 1: rate limit exceeded, please slow down"),
    ("rate-limit-429", RATE_LIMIT_TEXT),
]

# "never classify a session that RAN and failed as infrastructure" (A2).
NOT_INFRASTRUCTURE_TEXTS = [
    (
        "validate-red",
        (
            "[localclaude] exit 1: make validate is RED: tests/test_scaffold.py::test_solver_wins "
            "FAILED — expected WIN, got NOT_FINISHED"
        ),
    ),
    ("game-crash", "[localclaude] exit 1: solver.py raised ValueError on level 2"),
    ("budget-limit", "[localclaude] exit 1: the level budget limit was exceeded by the solver"),
    ("scope-repair", "[localclaude] exit 1: the agent edited tests/test_scaffold.py"),
    ("bare", "boom"),
]


# --------------------------------------------------------------------------- #
# discovery — the contract leaves helper names and constants renegotiable
# --------------------------------------------------------------------------- #


def _sole(module, candidates: list[str], what: str):
    """The one discovered name, or a loud wall naming what was searched for."""
    assert candidates, (
        f"FIXTURE WALL: no {what} found on {module.__name__}. "
        f"Module names: {sorted(n for n in dir(module) if not n.startswith('__'))}"
    )
    assert len(candidates) == 1, f"ambiguous {what} on {module.__name__}: {sorted(candidates)}"
    return getattr(module, candidates[0])


def _retry_seam():
    """The battery's chat-with-retry wrapper (contract A1's `_chat_with_transport_retry`)."""
    named = getattr(s5_battery, "_chat_with_transport_retry", None)
    if callable(named):
        return named
    return _sole(
        s5_battery,
        [n for n in dir(s5_battery) if "retry" in n.lower() and callable(getattr(s5_battery, n))],
        "chat-with-retry seam",
    )


def _classifier():
    """`is_infrastructure_error` (contract A2 names it; helper names renegotiable)."""
    named = getattr(backends, "is_infrastructure_error", None)
    if callable(named):
        return named
    return _sole(
        backends,
        [
            n
            for n in dir(backends)
            if "infrastructur" in n.lower() and callable(getattr(backends, n))
        ],
        "infrastructure classifier",
    )


def _tries_constant(module, subject: tuple[str, ...]) -> int | None:
    """The declared try count for a ladder, if the module publishes one."""
    counters = ("tries", "attempt", "retr")
    found = [
        n
        for n in dir(module)
        if isinstance(getattr(module, n), int)
        and not isinstance(getattr(module, n), bool)
        and any(word in n.lower() for word in subject)
        and any(word in n.lower() for word in counters)
    ]
    if len(found) != 1:
        return None
    return int(getattr(module, found[0]))


def _ledger():
    """A fresh battery ledger — the only place a successful turn's retry count lands."""
    cls = getattr(s5_battery, "_Ledger", None)
    assert cls is not None and dataclasses.is_dataclass(cls), (
        "FIXTURE WALL: the battery ledger (`_Ledger`) moved; the retry count has no home to read."
    )
    return cls(cap=10_000_000)


def _retry_counters(obj) -> dict[str, int]:
    """Every retry counter on a ledger or on a report's crash record, by shape."""
    if dataclasses.is_dataclass(obj):
        items = {field.name: getattr(obj, field.name) for field in dataclasses.fields(obj)}
    else:
        items = dict(obj)
    return {key: value for key, value in items.items() if "retr" in str(key)}


def _rate_limit_counter(counters: dict[str, int]) -> int:
    """The rate-limit retry count, riding NEXT TO `transport_retries` (A1)."""
    assert "transport_retries" in counters, (
        f"the transport counter must survive unchanged; counters were {sorted(counters)}"
    )
    siblings = {key: value for key, value in counters.items() if key != "transport_retries"}
    assert siblings, (
        "the rate-limit retry count must ride next to transport_retries; "
        f"only {sorted(counters)} present"
    )
    return sum(int(value) for value in siblings.values())


# --------------------------------------------------------------------------- #
# fakes — nothing dials out, nothing spawns a real agent
# --------------------------------------------------------------------------- #


class _Chat:
    """A stand-in for `OpenRouterDriver.chat`: raise `error` for the first
    `fails` calls, then answer from `replies` (cycled, b9's recipe)."""

    def __init__(self, error: str | None = None, *, fails: int = 0, replies=("ACTION1",)) -> None:
        self.error = error
        self.fails = fails
        self.replies = list(replies)
        assert self.replies, "a fake chat needs at least one reply"
        self.calls = 0
        self.answered = 0

    def __call__(self, messages, **kwargs) -> ChatResult:
        self.calls += 1
        if self.error is not None and self.calls <= self.fails:
            raise DriverError(self.error)
        text = self.replies[self.answered % len(self.replies)]
        self.answered += 1
        return ChatResult(
            driver="openrouter",
            model_requested=kwargs.get("model") or MODEL,
            model_reported=None,
            text=text,
            tokens_in=10,
            tokens_out=5,
            usd_cost=0.001,
            raw={"fake": True, "text": text},
        )


def _runner(log: list[dict], *, error=None, fails: int = 0, on_success=None):
    """One agent session (b3's recipe): log the call, raise `error()` for the
    first `fails` calls, otherwise optionally edit the worker and return a
    session dict."""

    def runner(prompt: str, *, cwd: Path, resume_id: str | None):
        log.append({"prompt": prompt, "cwd": Path(cwd), "resume_id": resume_id})
        if error is not None and len(log) <= fails:
            raise error()
        if on_success is not None:
            on_success(len(log), Path(cwd))
        return {
            "session_id": f"fake-{len(log)}",
            "usd_cost": 0.01,
            "tokens_in": 100,
            "tokens_out": 50,
            "duration_s": 0.0,
            "error": None,
        }

    return runner


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _cfg(cap: int) -> dict:
    """b3's minimal config: with an injected runner the cap is all green_loop reads."""
    return {"implementer": {"max_green_attempts": cap}}


def _worker(tmp_path: Path, name: str) -> Path:
    worker = tmp_path / name
    instantiate_worker(worker)
    return worker.resolve()


def _install_toy(cwd: Path) -> None:
    shutil.copy2(TOY / "game.py", cwd / "game.py")
    shutil.copy2(TOY / "solver.py", cwd / "solver.py")


def _rows(worker: Path) -> list[dict]:
    path = sidecar(worker, ATTEMPTS_SUFFIX)
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _reply_for(record: dict) -> str:
    """b9's recipe: one `actions/level-<i>.json` record as its reply line."""
    action_id = int(record["id"])
    data = record.get("data") or {}
    if action_id == 6:
        return f"ACTION6 {int(data['x'])} {int(data['y'])}"
    return f"ACTION{action_id}"


def _replay_plan(out_dir: Path) -> list[str]:
    actions_dir = Path(out_dir) / "actions"
    plan: list[str] = []
    index = 1
    while (actions_dir / f"level-{index}.json").is_file():
        records = json.loads((actions_dir / f"level-{index}.json").read_text(encoding="utf-8"))
        plan.extend(_reply_for(record) for record in records)
        index += 1
    assert plan, f"no actions/level-*.json under {actions_dir}"
    return plan


def _measure_ladder(error_text: str, sleeps: list) -> tuple[int, list[float]]:
    """Drive the retry seam to exhaustion: (calls made, backoff steps taken)."""
    chat = _Chat(error_text, fails=10**6)
    mark = len(sleeps)
    with pytest.raises(DriverError):
        _retry_seam()(chat, list(MESSAGES), model=MODEL, ledger=_ledger())
    steps = [float(value) for value in sleeps[mark:]]
    del sleeps[mark:]
    return chat.calls, steps


def _battery(tmp_path: Path, metadata_path: Path, chat, name: str) -> tuple[dict, Path]:
    out_dir = tmp_path / name
    report = run_battery(TOY, CFG, chat=chat, metadata_path=metadata_path, out_dir=out_dir)
    return report, out_dir


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    """Every backoff in this file is RECORDED, never slept (contract: "Backoffs
    must be injectable/patchable so no test sleeps for real")."""
    recorded: list[float] = []
    started = time.monotonic()
    monkeypatch.setattr(time, "sleep", recorded.append)
    for module in (s5_battery, s2_implement, backends):
        if hasattr(module, "_sleep"):
            monkeypatch.setattr(module, "_sleep", recorded.append)
    yield recorded
    elapsed = time.monotonic() - started
    assert elapsed < WALL_LIMIT_S, (
        f"this test ran {elapsed:.1f}s: a backoff slept for real — the ladder is not patchable "
        "through `time.sleep` or a module-level `_sleep`"
    )


@pytest.fixture(autouse=True)
def _no_network_no_key(monkeypatch):
    """No test in this file dials out or sees a real key (b9's SECRETS rule)."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("b002 resilience tests must never open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.delenv(OPENROUTER_KEY_ENV, raising=False)


@pytest.fixture(scope="module")
def s4_metadata(tmp_path_factory) -> tuple[Path, list[str]]:
    """One real stage-4 run on the toy worker (b9's recipe): (metadata, plan)."""
    out_dir = tmp_path_factory.mktemp("b002-s4") / "toy"
    report = run_s4(TOY, CFG, seed=S4_SEED, out_dir=out_dir)
    assert report["verdict"] == "fit", f"S4 verdict {report['verdict']}"
    return out_dir / "metadata.json", _replay_plan(out_dir)


@pytest.fixture
def real_infra_errors(monkeypatch, tmp_path) -> dict[str, DriverError]:
    """The REAL `DriverError`s the shipped drivers raise for three of the
    contract's four infrastructure classes — produced here, never guessed."""
    errors: dict[str, DriverError] = {}

    monkeypatch.delenv(OPENROUTER_KEY_ENV, raising=False)
    with pytest.raises(DriverError) as missing:
        OpenRouterDriver().chat(list(MESSAGES), model=MODEL)
    errors["missing-key"] = missing.value

    def _too_many_requests(request, timeout=None):
        raise urllib.error.HTTPError(
            OPENROUTER_URL,
            429,
            "Too Many Requests",
            {},
            io.BytesIO(b'{"error":{"message":"Rate limit exceeded"}}'),
        )

    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    monkeypatch.setattr(urllib.request, "urlopen", _too_many_requests)
    monkeypatch.setattr(backends, "urlopen", _too_many_requests, raising=False)
    with pytest.raises(DriverError) as throttled:
        OpenRouterDriver().chat(list(MESSAGES), model=MODEL)
    errors["http-429"] = throttled.value

    with pytest.raises(DriverError) as absent:
        LocalClaudeDriver(claude_bin=ABSENT_CLI).session("implement the spec", cwd=tmp_path)
    errors["cli-missing"] = absent.value

    for name, error in errors.items():
        assert FAKE_KEY not in str(error), f"{name}: the key must never ride an error text"
        assert str(error).strip(), f"{name}: an empty error text classifies nothing"
    return errors


# --------------------------------------------------------------------------- #
# group A — pin 1: the battery's rate-limit ladder, and the transport regression
# --------------------------------------------------------------------------- #


def test_a_the_rate_limit_ladder_is_bounded_and_longer_than_the_transport_ladder(sleeps):
    """D1: a 429 matches no connection-class needle today, so it surfaces as a
    CRASH on the first call and §4's crash edge buys a re-implement loop."""
    transport_calls, transport_steps = _measure_ladder(TRANSPORT_TEXT, sleeps)
    rate_calls, rate_steps = _measure_ladder(RATE_LIMIT_TEXT, sleeps)

    assert (transport_calls, transport_steps) == (
        TRANSPORT_ATTEMPTS,
        [float(value) for value in TRANSPORT_BACKOFF_S],
    ), "the transport ladder must be byte-identical to today's"

    assert rate_calls > 1, (
        "a rate-limit error must join the retry class, not crash the battery on the first call"
    )
    assert rate_calls <= MAX_LADDER_TRIES, f"the rate-limit ladder must be bounded: {rate_calls}"
    assert len(rate_steps) == rate_calls - 1, "one backoff between consecutive tries"
    assert all(step > 0 for step in rate_steps), f"every backoff must be positive: {rate_steps}"
    assert rate_steps == sorted(rate_steps), f"the ladder must not shrink: {rate_steps}"
    assert sum(rate_steps) > sum(transport_steps), (
        f"A1: the rate-limit backoff must be LONGER than transport's "
        f"({rate_steps} vs {transport_steps})"
    )

    declared = _tries_constant(s5_battery, ("rate", "throttl"))
    if declared is not None:
        assert declared == rate_calls, "the declared try count must be the one the seam uses"


@pytest.mark.parametrize(
    "text",
    [
        RATE_LIMIT_TEXT,
        "[openrouter] HTTP 429: Too Many Requests",
        "[openrouter] TOO MANY REQUESTS",
        "[openrouter] Rate Limit Exceeded for this model",
        "[localclaude] exit 1: 429 rate_limit_error",
    ],
    ids=["http-429-body", "http-429-terse", "shouty", "mixed-case", "cli-429"],
)
def test_a_every_rate_limit_shape_is_retried_whatever_its_case(text, sleeps):
    """A1 pins "lowercased matching like the transport class" — pinned here on
    behaviour, so the exact needle strings stay renegotiable."""
    calls, steps = _measure_ladder(text, sleeps)
    assert calls > 1, f"not retried: {text!r}"
    assert len(steps) == calls - 1


@pytest.mark.parametrize("needle", list(TRANSPORT_ERROR_SUBSTRINGS))
def test_a_every_transport_needle_still_retries_on_the_transport_ladder(needle, sleeps):
    """Pin 1's regression half, driven off the shipped needle list itself."""
    calls, steps = _measure_ladder(f"[openrouter] {needle}", sleeps)
    assert calls == TRANSPORT_ATTEMPTS, f"{needle!r} left the transport class"
    assert steps == [float(value) for value in TRANSPORT_BACKOFF_S], (
        f"{needle!r} moved off the transport ladder"
    )


def test_a_the_transport_text_used_here_really_is_a_transport_needle():
    """Guard on the regression above: the fixture text must match the class it claims."""
    assert any(needle in TRANSPORT_TEXT.lower() for needle in TRANSPORT_ERROR_SUBSTRINGS)
    assert not any(needle in RATE_LIMIT_TEXT.lower() for needle in TRANSPORT_ERROR_SUBSTRINGS), (
        "the rate-limit fixture text must not be retryable as a transport error"
    )


def test_a_a_recovered_rate_limit_returns_the_reply_and_records_the_retries(sleeps):
    """A1: "retried on the rate-limit ladder, then success" — the turn goes through."""
    tries, _steps = _measure_ladder(RATE_LIMIT_TEXT, sleeps)
    assert 1 < tries <= MAX_LADDER_TRIES, f"there is no rate-limit ladder to recover on: {tries}"
    ledger = _ledger()
    chat = _Chat(RATE_LIMIT_TEXT, fails=tries - 1, replies=("ACTION4",))

    result = _retry_seam()(chat, list(MESSAGES), model=MODEL, ledger=ledger)

    assert getattr(result, "text", None) == "ACTION4", "the recovered turn must answer"
    assert chat.calls == tries
    assert len(sleeps) == tries - 1, f"one backoff per retry: {sleeps}"
    counters = _retry_counters(ledger)
    assert _rate_limit_counter(counters) == tries - 1, f"retries not recorded: {counters}"
    assert counters["transport_retries"] == 0, (
        f"no transport error happened; transport_retries must stay 0: {counters}"
    )


def test_a_a_rate_limited_turn_lets_the_battery_finish(tmp_path, s4_metadata, sleeps):
    """The whole point of D1: a throttle must not cost a re-implement loop."""
    metadata_path, plan = s4_metadata
    chat = _Chat(RATE_LIMIT_TEXT, fails=1, replies=plan)

    report, out_dir = _battery(tmp_path, metadata_path, chat, "s5-throttled")

    assert report["status"] == STATUS_COMPLETE, report["status"]
    assert not report["crash"], f"a survived throttle is not a crash: {report['crash']}"
    assert report["rows"], "the battery must still have played"
    assert sleeps, "the retry must have gone through the (patched) backoff"
    assert (out_dir / REPORT_NAME).is_file() and (out_dir / CSV_NAME).is_file()


def test_a_a_persistent_rate_limit_still_lands_on_the_existing_crash_path(
    tmp_path, s4_metadata, sleeps
):
    """A1: "Retries exhausted -> the existing failure path unchanged" — still a
    crash record, with the retry count riding next to transport_retries."""
    metadata_path, plan = s4_metadata
    tries, _steps = _measure_ladder(RATE_LIMIT_TEXT, sleeps)
    assert 1 < tries <= MAX_LADDER_TRIES, f"a 429 must be retried before it crashes: {tries}"
    chat = _Chat(RATE_LIMIT_TEXT, fails=10**6, replies=plan)

    report, out_dir = _battery(tmp_path, metadata_path, chat, "s5-throttled-out")

    assert report["status"] == STATUS_CRASH, report["status"]
    crash = report["crash"]
    assert isinstance(crash, dict), f"crash must be a dict, got {crash!r}"
    assert {"pass", "level", "error_tail"} <= set(crash), sorted(crash)
    assert "429" in crash["error_tail"], "the crash record must carry the throttle's own text"
    counters = _retry_counters(crash)
    assert _rate_limit_counter(counters) == tries - 1, f"retries not on the report: {counters}"
    assert counters["transport_retries"] == 0, (
        f"no transport error happened; transport_retries must stay 0: {counters}"
    )
    assert chat.calls == tries, "the ladder must be the same one the seam measured"
    assert (out_dir / REPORT_NAME).is_file() and (out_dir / CSV_NAME).is_file()


def test_a_a_persistent_transport_failure_crashes_exactly_as_today(tmp_path, s4_metadata, sleeps):
    """The transport class's own end-to-end behaviour, unchanged."""
    metadata_path, plan = s4_metadata
    chat = _Chat(TRANSPORT_TEXT, fails=10**6, replies=plan)

    report, _out_dir = _battery(tmp_path, metadata_path, chat, "s5-transport-out")

    assert report["status"] == STATUS_CRASH, report["status"]
    assert chat.calls == TRANSPORT_ATTEMPTS
    assert sleeps == [float(value) for value in TRANSPORT_BACKOFF_S]
    assert report["crash"]["transport_retries"] == TRANSPORT_ATTEMPTS - 1


# --------------------------------------------------------------------------- #
# group B — pin 2: an infrastructure outage consumes no attempt
# --------------------------------------------------------------------------- #


def _outage(text: str):
    return lambda: DriverError(text)


OUTAGE_TEXT = "[localclaude] exit 1: OAuth session expired"


@pytest.mark.parametrize(
    "text",
    [
        OUTAGE_TEXT,
        "[localclaude] exit 1: Claude AI usage limit reached|1758870000",
        "[openrouter] HTTP 429 from https://openrouter.ai/api/v1/chat/completions: throttled",
        f"[localclaude] CLI not found: '{ABSENT_CLI}'",
    ],
    ids=["auth", "usage-limit", "rate-limit", "cli-missing"],
)
def test_b_an_outage_blocks_the_slot_and_consumes_no_attempt(text, tmp_path, sleeps):
    """D2: today ANY session exception becomes a consumed attempt, so a
    persistent account outage burns the loop and kills the slot."""
    worker = _worker(tmp_path, "w-outage")
    log: list[dict] = []

    report = green_loop(
        worker,
        "implement the spec",
        _cfg(12),
        session_runner=_runner(log, error=_outage(text), fails=10**6),
    )

    assert report.green is False
    assert report.reject_reason == DRIVER_UNAVAILABLE, (
        f"an infrastructure outage must abort as {DRIVER_UNAVAILABLE!r}, "
        f"not {report.reject_reason!r}"
    )
    assert report.records == [], "an outage must append no AttemptRecord"
    assert report.attempts == 0, "an outage consumes no attempt (contract A2)"
    assert _rows(worker) == [], "an outage must write no attempt ledger row"

    assert 1 < len(log) <= MAX_LADDER_TRIES, f"the ladder must be bounded and retry: {len(log)}"
    assert len(sleeps) == len(log) - 1, f"one backoff per retry: {sleeps}"
    assert all(step > 0 for step in sleeps), f"every backoff must be positive: {sleeps}"

    declared = _tries_constant(s2_implement, ("infra", "driver", "outage", "unavailable"))
    if declared is not None:
        assert declared == len(log), "the declared try count must be the one the loop uses"


def test_b_the_blocked_verdict_blames_infrastructure_not_the_game(tmp_path, sleeps):
    """A2: "a verdict file [that] says the slot is BLOCKED by infrastructure, not
    by the game" — the loud block."""
    worker = _worker(tmp_path, "w-blocked")
    log: list[dict] = []

    report = green_loop(
        worker,
        "implement the spec",
        _cfg(12),
        session_runner=_runner(log, error=_outage(OUTAGE_TEXT), fails=10**6),
    )

    assert report.reject_reason == DRIVER_UNAVAILABLE
    path = sidecar(worker, REJECT_SUFFIX)
    assert path.is_file(), "a blocked slot must still leave a verdict beside the worker"
    raw = path.read_text(encoding="utf-8")
    verdict = json.loads(raw)
    assert DRIVER_UNAVAILABLE in raw, f"the verdict must name the reason: {sorted(verdict)}"
    assert verdict.get("reject_reason") == DRIVER_UNAVAILABLE
    assert "infrastructure" in raw.lower(), "the verdict must say what blocked the slot"
    assert verdict.get("verdict") != REJECT_VERDICT, (
        f"{REJECT_VERDICT!r} routes the slot back to spec-writing — that blames the game"
    )
    assert not sidecar(worker, REPORT_SUFFIX).exists(), "a blocked slot is not a green report"


def test_b_the_same_attempt_index_is_retried_after_an_outage(tmp_path, sleeps):
    """A2: "retry the SAME attempt index" — the outage tries leave no trace and the
    session that finally runs is attempt 1."""
    probe = _worker(tmp_path, "w-probe")
    probe_log: list[dict] = []
    green_loop(
        probe,
        "implement the spec",
        _cfg(12),
        session_runner=_runner(probe_log, error=_outage(OUTAGE_TEXT), fails=10**6),
    )
    tries = len(probe_log)
    assert 1 < tries <= MAX_LADDER_TRIES, f"unusable ladder: {tries}"
    del sleeps[:]

    worker = _worker(tmp_path, "w-recovered")
    log: list[dict] = []
    report = green_loop(
        worker,
        "implement the spec",
        _cfg(12),
        session_runner=_runner(
            log,
            error=_outage(OUTAGE_TEXT),
            fails=tries - 1,
            on_success=lambda n, cwd: _install_toy(cwd),
        ),
    )

    assert len(log) == tries, "the full ladder must be usable before the loop gives up"
    assert report.green is True, "the recovered session must still be able to go green"
    assert report.attempts == 1, "the outage retries must not consume attempt indices"
    assert [record.index for record in report.records] == [1]
    assert report.records[0].session.get("error") is None, (
        "no AttemptRecord may carry the infrastructure failure"
    )
    assert [row["index"] for row in _rows(worker)] == [1]
    assert report.reject_reason is None


def test_b_an_outage_does_not_burn_the_green_attempt_cap(tmp_path, sleeps):
    """The D2 headline: a persistent outage must not spend the 12-attempt cap."""
    worker = _worker(tmp_path, "w-cap")
    log: list[dict] = []
    cap = 12

    report = green_loop(
        worker,
        "implement the spec",
        _cfg(cap),
        session_runner=_runner(log, error=_outage(OUTAGE_TEXT), fails=10**6),
    )

    assert len(log) < cap, f"the outage burned {len(log)} of the {cap} sessions"
    assert report.attempts < cap
    assert report.reject_reason == DRIVER_UNAVAILABLE


# --------------------------------------------------------------------------- #
# group C — pin 3: a non-infrastructure error is consumed exactly as today
# --------------------------------------------------------------------------- #

#: measured against the shipped loop before this contract: the record's
#: `session` is exactly one key, `f"{type(exc).__name__}: {exc}"`.
GAME_ERROR_TEXT = "[localclaude] exit 1: solver.py raised ValueError on level 2"


@pytest.mark.parametrize(
    "factory,expected",
    [
        (
            lambda: DriverError(GAME_ERROR_TEXT),
            f"DriverError: {GAME_ERROR_TEXT}",
        ),
        (
            lambda: RuntimeError("the agent stopped without touching game.py"),
            "RuntimeError: the agent stopped without touching game.py",
        ),
    ],
    ids=["driver-error-that-ran", "plain-runtime-error"],
)
def test_c_a_non_infrastructure_error_consumes_its_attempt_byte_for_byte(
    factory, expected, tmp_path, sleeps
):
    """A2: "Non-infrastructure exceptions keep today's behavior byte-for-byte."""
    worker = _worker(tmp_path, "w-consumed")
    log: list[dict] = []

    report = green_loop(
        worker,
        "implement the spec",
        _cfg(12),
        session_runner=_runner(
            log,
            error=factory,
            fails=1,
            on_success=lambda n, cwd: _install_toy(cwd),
        ),
    )

    assert report.green is True and report.attempts == 2, "the failed attempt was consumed"
    assert len(log) == 2, "a non-infrastructure error is never retried in place"
    assert sleeps == [], "a non-infrastructure error must not go through a backoff"
    record = report.records[0]
    assert record.index == 1 and record.green is False
    assert record.session == {"error": expected}, record.session
    assert _rows(worker)[0]["session"] == {"error": expected}
    assert report.reject_reason is None
    assert report.total_usd == pytest.approx(0.01), "an errored session contributes no cost"


def test_c_a_non_infrastructure_error_still_reaches_the_attempt_cap(tmp_path, sleeps):
    """The cap path is untouched: every red attempt still counts (b3's pin)."""
    worker = _worker(tmp_path, "w-still-capped")
    log: list[dict] = []

    report = green_loop(
        worker,
        "implement the spec",
        _cfg(2),
        session_runner=_runner(log, error=lambda: RuntimeError("boom"), fails=10**6),
    )

    assert report.green is False
    assert report.attempts == 2 and len(log) == 2
    assert [row["index"] for row in _rows(worker)] == [1, 2]
    assert report.reject_reason != DRIVER_UNAVAILABLE
    assert sleeps == []


# --------------------------------------------------------------------------- #
# group D — pin 4: the classifier truth table
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name,text", INFRASTRUCTURE_TEXTS, ids=[n for n, _ in INFRASTRUCTURE_TEXTS]
)
def test_d_the_four_infrastructure_classes_are_true(name, text):
    classify = _classifier()
    assert classify(DriverError(text)) is True, f"{name}: {text!r}"
    assert classify(text) is True, f"{name} (as text): {text!r}"


@pytest.mark.parametrize(
    "name,text", NOT_INFRASTRUCTURE_TEXTS, ids=[n for n, _ in NOT_INFRASTRUCTURE_TEXTS]
)
def test_d_a_session_that_ran_and_failed_is_never_infrastructure(name, text):
    classify = _classifier()
    assert classify(DriverError(text)) is False, f"{name}: {text!r}"
    assert classify(text) is False, f"{name} (as text): {text!r}"


def test_d_a_plain_runtime_error_is_not_infrastructure():
    classify = _classifier()
    assert classify(RuntimeError("boom")) is False
    assert classify(ValueError("solver.py disagreed with the spec on level 3")) is False


@pytest.mark.parametrize("name", ["missing-key", "http-429", "cli-missing"])
def test_d_the_real_driver_errors_are_infrastructure(name, real_infra_errors):
    """The truth table's strongest rows: errors the shipped drivers actually
    raise, built by this test rather than guessed from prose."""
    error = real_infra_errors[name]
    classify = _classifier()
    assert classify(error) is True, f"{name}: {str(error)!r}"
    assert classify(str(error)) is True, f"{name} (as text): {str(error)!r}"


def test_d_a_real_outage_reaches_the_green_loop_as_a_block(tmp_path, real_infra_errors, sleeps):
    """The classifier and the loop agree: a real driver outage blocks the slot."""
    error = real_infra_errors["cli-missing"]
    worker = _worker(tmp_path, "w-real-outage")
    log: list[dict] = []

    report = green_loop(
        worker,
        "implement the spec",
        _cfg(12),
        session_runner=_runner(log, error=lambda: DriverError(str(error)), fails=10**6),
    )

    assert report.reject_reason == DRIVER_UNAVAILABLE
    assert report.records == [] and _rows(worker) == []
