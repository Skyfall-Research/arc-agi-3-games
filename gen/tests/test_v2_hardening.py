"""H-1 acceptance (BLIND LANE): the hardening wave's promises, from the contract.

Run: .venv/bin/python -m pytest gen/tests/test_v2_hardening.py -q

Written from `docs/v2/contracts/H-1-hardening-wave.md` ALONE, against the
COMMITTED tree (`git show HEAD:…`) for idioms only. The implementer's diff and
`gen/tests/test_h1_hardening.py` were never read, `gen/tests/test_v2_parallel.py`
is NOT imported (its lock-observation idiom is REBUILT here, from `fcntl` up),
and every name this file could have hard-coded is either one the contract spells
or one it DISCOVERS at runtime — so a renegotiated constant cannot make a pin
lie, and cannot make one pass for the wrong reason.

Scope: items 1-4 and the behavioural half of 7-9. Items 5, 6, 10 and 11 are
MEASUREMENTS and the contract gives them to the implementer ("do not guess
them") — nothing here touches them.

The pins, one line each (contract item -> promise):

  1 MODEL-404 FAIL-FAST   a fabricated 404-shaped reply from EITHER driver
                          becomes a loud CONFIG-class failure that consumes no
                          green-loop attempts (group A).
  2 NARRATOR VOCABULARY   the `DECL_ONLY_REASON` hop narrates as REVALIDATION,
                          never as a rebuild; an ordinary build hop is
                          byte-unchanged (group B).
  3 PLAY-SERVER RESCAN    a game added to the served catalog appears in
                          `/api/games` with no restart (group C).
  4 PLAY_COMMAND          the packaged-game hint names `arc-games play` and
                          names `PLAY_GAMES_DIR` nowhere (group D).
  7 MAINTAINER DRAW LOCK  the hand-run S0 drawer takes the pipeline's per-batch
                          draw flock, around the whole draw (group E).
  8 DEDUPE APPEND LOCK    the shared dedupe-history append is flocked (group F).
  9 GATE.GATE DOUBLE      no code the gate emits for its own checks carries a
                          doubled `gate.` prefix (group G).

HERMETIC. No drivers (every driver call here is a fabricated
`subprocess.CompletedProcess`, and the driver/classifier tests forbid
`subprocess` outright), no network (autouse raisers on `urlopen` and
`socket.create_connection`), no sleeping (autouse raiser on `time.sleep` and on
`s2_implement`'s own `_sleep` seam, so a retry ladder fails the test instead of
stalling it). Nothing is written under the real `out/` or `games/`: every root
the code under test resolves at module scope is redirected to `tmp_path`, and
the real dedupe history is snapshotted and restored regardless (the
`test_b4_sampler` discipline). `../duckWM` is read through `load_config` /
`load_vocab` only.

CONTRACT AMBIGUITIES, and the reading each group takes (reported, never
invented quietly):

  A. Item 1 does not say HOW a config-class failure surfaces from the green
     loop. Both readings are accepted: an exception out of `green_loop`, or a
     report whose reject reason is config-class. What is pinned either way is
     the measurable half of the sentence — "before/at attempt 1" and "instead
     of consuming green-loop attempts": the session runner is called ONCE and
     at most one attempt row is written. The pin lives on `green_loop` because
     that is where the 12 attempts were burned; a fix that only preflights the
     configured model name elsewhere would leave this red, and the item says
     the smoke (which uses the CLI default model) cannot catch it.
  B. Item 1 names no classifier. Group A DISCOVERS one by TRUTH TABLE instead
     (404 -> true; a 401/auth text -> false; a wrong-shape work failure ->
     false), which no existing predicate satisfies: `is_infrastructure_error`
     is true for the 401 row. That table also encodes the reading that a 404 is
     NOT infrastructure — an outage BLOCKS a slot after a minutes-long ladder,
     and "a CONFIG error that fails the run loudly" is a different verdict.
  C. Item 2's "or similar" leaves the wording open. Group B pins the two
     properties the sentence states: no rebuild vocabulary (negated mentions
     ALLOWED — "nothing was rebuilt" denies a rebuild, it does not announce
     one) and revalidation vocabulary present. The contract's own suggested
     wording, "checking the build against the amended spec", passes both.
  D. Item 3 licenses either a per-request rescan or a top-level mtime check, so
     group C adds a NEW TOP-LEVEL catalog entry — the only addition both
     mechanisms are required to see. A game added inside an existing entry is
     deliberately not pinned.
  E. Item 9's "fix the producer" is ambiguous: the doubled string is composed
     from `gen/s3_gate`'s prefixed check-id constants AND the gate stage's own
     `gate.`-prefixing of them, so either side could be called the producer.
     Group G is written to pass under BOTH fixes: it discovers whether the
     stage still prefixes a `check_id` (source probe) and asserts the EMITTED
     spelling is single-prefixed either way. FLAGGED: if the fix removes the
     prefixing by a spelling neither probe recognises, this test reads as
     "no prefixing applied" — a false green, never a false red.
  F. Item 7's "same scope" is read as "around the whole draw", which is the
     scope the pipeline's own lock has. Observing it requires the draw itself
     to be a stub (a real hand-run draw spends), so the lock is pinned where
     the CLI path takes it; a lock taken INSIDE `sample_batch` would deadlock
     the pipeline's own lock and is not a reading this file entertains.
"""

from __future__ import annotations

import fcntl
import importlib.util
import inspect
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

from gen import backends as backends_mod
from gen import cli as cli_mod
from gen import orchestrator as orch
from gen import s0_ideas as s0_mod
from gen import s2_implement as s2_mod
from gen import s3_gate as gate_mod
from gen import s6_package as s6_mod
from gen.backends import CodexDriver, DriverError, LocalClaudeDriver
from gen.config import REPO_ROOT, load_config
from gen.s2_implement import ATTEMPTS_SUFFIX, REJECT_SUFFIX, green_loop, sidecar
from gen.worker import instantiate_worker

PILOT = "config/b001-pilot.yaml"
HISTORY_NAME = "dedupe-history.jsonl"
PLAY_SERVER = REPO_ROOT / "tools" / "play" / "server.py"

# --------------------------------------------------------------------------- #
# fabricated fixtures — item 1's "404-shaped reply ... for BOTH drivers'
# error shapes". Each is the shape its driver's OWN error path parses: the
# claude lane reports failures as a decodable result payload with
# `is_error: true` and the text in `result` (the committed
# `fixtures/localclaude-authfail-payload.json` is that shape with an auth text
# in it); the codex lane reports them as a `turn.failed` event carrying
# `error.message` (the shape the recorded codex 401s arrive in). Neither
# fixture is a copy of a live record — a 404 has never been captured, which is
# exactly why item 1 asks for a fabricated one.
# --------------------------------------------------------------------------- #

MISSING_CLAUDE_MODEL = "claude-opus-9-20991231"
MISSING_CODEX_MODEL = "gpt-9-codex-max"

CLAUDE_404_PAYLOAD = {
    "is_error": True,
    # `subtype` reads "success" even on failures — the committed fixture's own
    # lesson, reproduced so this fixture cannot pass for the wrong reason.
    "subtype": "success",
    "session_id": "h1-fabricated-404",
    "total_cost_usd": 0,
    "usage": {"input_tokens": 0, "output_tokens": 0},
    "modelUsage": {},
    "terminal_reason": "api_error",
    "type": "result",
    "result": (
        'API Error: 404 {"type":"error","error":{"type":"not_found_error",'
        f'"message":"model: {MISSING_CLAUDE_MODEL}"}}}}'
    ),
}

CODEX_404_EVENTS = (
    {"type": "thread.started", "thread_id": "h1-fabricated-404"},
    {"type": "turn.started"},
    {
        "type": "turn.failed",
        "error": {
            "message": (
                "stream error: unexpected status 404 Not Found: "
                '{"error":{"message":"The requested model '
                f"'{MISSING_CODEX_MODEL}' does not exist or you do not have access to "
                'it.","type":"invalid_request_error","param":"model",'
                '"code":"model_not_found"}}'
            )
        },
    },
)

# The FALSE rows of the classifier truth table (group A). Two are infrastructure
# — the credential, which retrying cannot fix but waiting sometimes can — and
# one is ordinary work coming back wrong. None of the three is a config error.
AUTH_401_TEXTS = (
    ("[localclaude] exit 1, is_error=True: Failed to authenticate: OAuth session "
     "expired and could not be refreshed"),
    "[codex] exit 1, turn.failed: 401 Unauthorized: invalid_api_key",
)
WORK_FAILURE_TEXTS = (
    "[localclaude] payload missing 'result' — fields present: ['subtype', 'type']",
    "make validate is still RED in this worker: 3 failed, 11 passed",
)


# --------------------------------------------------------------------------- #
# hygiene (autouse)
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """NO TEST SLEEPS, and a retry ladder that fires must FAIL rather than wait.

    `s2_implement` reaches its backoff through its own `_sleep` seam; both it
    and `time.sleep` raise here, so item 1's "before/at attempt 1" cannot be
    satisfied by a long quiet wait that the wall clock would hide.
    """

    def forbidden(seconds=0.0):   # pragma: no cover — tripping it is the point
        raise AssertionError(
            f"a test slept for {seconds}s — H-1's pins are all synchronous, and a "
            "backoff ladder reached here means a failure was routed as a retryable "
            "outage instead of as the loud config error item 1 asks for"
        )

    monkeypatch.setattr(time, "sleep", forbidden)
    if hasattr(s2_mod, "_sleep"):
        monkeypatch.setattr(s2_mod, "_sleep", forbidden)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No test dials out. Hard rule, and the drivers are the files under test."""

    def forbidden(*args, **kwargs):   # pragma: no cover
        raise AssertionError("a test tried to open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture(autouse=True)
def _protect_real_trees(monkeypatch, tmp_path):
    """Nothing lands in the real `out/` or `games/`, whatever an item renames.

    Every module-level root the code under test resolves at import is pointed
    into `tmp_path` (by VALUE, so a constant this file does not know the name of
    still moves), and the real dedupe history is snapshotted and restored either
    way, so the repo is byte-identical after the run.
    """
    real_history = REPO_ROOT / "out" / "ideas" / HISTORY_NAME
    before = real_history.read_bytes() if real_history.is_file() else None
    parent_existed = real_history.parent.is_dir()

    ideas_root = tmp_path / "out" / "ideas"
    ideas_root.mkdir(parents=True, exist_ok=True)
    for module in (s0_mod, orch):
        for name, value in list(vars(module).items()):
            if not isinstance(value, Path):
                continue
            if value.name == HISTORY_NAME:
                monkeypatch.setattr(module, name, ideas_root / HISTORY_NAME, raising=False)
            elif value.name == "ideas" and value.parent.name == "out":
                monkeypatch.setattr(module, name, ideas_root, raising=False)

    yield ideas_root

    if before is None:
        if real_history.is_file():
            real_history.unlink()
        if not parent_existed and real_history.parent.is_dir():
            try:
                real_history.parent.rmdir()
            except OSError:
                pass
    elif not real_history.is_file() or real_history.read_bytes() != before:
        # Restore ONLY a real change: rewriting identical bytes still moved the
        # file's mtime on every run (contract OS-2 FRONT C.2, the hermeticity fix).
        real_history.write_bytes(before)


@pytest.fixture
def no_processes(monkeypatch):
    """No child process at all — the driver and classifier pins spawn nothing."""

    def forbidden(*args, **kwargs):   # pragma: no cover
        raise AssertionError(f"a test tried to spawn a process: {args!r}")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


@pytest.fixture
def flock_log(monkeypatch):
    """REBUILT lock observation: record every `fcntl.flock`, then call through.

    Identity by `(st_dev, st_ino)` off the locked descriptor rather than by
    path, because the path a lock was opened under is not recoverable portably
    and because the point is WHICH FILE, not which spelling. Calling through
    means the lock observed is a REAL lock and not a mock of one.

    (`gen/tests/test_v2_parallel.py` has an observation of its own; the contract
    forbids importing it, and nothing here does.)
    """
    real_flock = fcntl.flock
    records: list[tuple[int, int, int]] = []

    def spy(fd, operation):
        try:
            stat = os.fstat(fd)
        except OSError:       # pragma: no cover — a closed fd is the caller's bug
            records.append((operation, -1, -1))
        else:
            records.append((operation, stat.st_dev, stat.st_ino))
        return real_flock(fd, operation)

    monkeypatch.setattr(fcntl, "flock", spy)
    return _FlockLog(records, real_flock)


class _FlockLog:
    """The recorder's view: which inodes were locked, and how."""

    def __init__(self, records, real_flock):
        self.records = records
        self.real_flock = real_flock

    def exclusive_ids(self) -> set[tuple[int, int]]:
        return {
            (dev, ino)
            for operation, dev, ino in self.records
            if operation & fcntl.LOCK_EX
        }

    def held_elsewhere(self, root: Path) -> dict[tuple[int, int], Path]:
        """inode -> path for every file under `root`, so a miss can SAY what
        was locked instead of only that the right thing was not."""
        found: dict[tuple[int, int], Path] = {}
        for path in sorted(root.rglob("*")):
            try:
                stat = path.stat()
            except OSError:   # pragma: no cover
                continue
            found[(stat.st_dev, stat.st_ino)] = path
        return found

    def is_locked_now(self, path: Path) -> bool | None:
        """Is `path` flocked RIGHT NOW by somebody? None = no such file.

        A fresh descriptor on the same file is an independent file description,
        so a non-blocking exclusive request fails exactly when the lock is held
        — including when it is held by this same process (POSIX flock semantics,
        which is this project's only claim). Uses the REAL flock so the probe
        never pollutes the recorder.
        """
        path = Path(path)
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as probe:
            try:
                self.real_flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError):
                return True
            self.real_flock(probe.fileno(), fcntl.LOCK_UN)
            return False


def _id_of(path: Path) -> tuple[int, int]:
    stat = Path(path).stat()
    return (stat.st_dev, stat.st_ino)


# =========================================================================== #
# GROUP A — item 1: MODEL-404 FAIL-FAST
# =========================================================================== #


def _fake_completed(stdout: str, returncode: int = 1):
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(list(cmd), returncode, stdout, "")

    return run


def _driver_404_error(monkeypatch, lane: str, cwd: Path) -> DriverError:
    """Run the fabricated 404 reply through ONE driver's real error path.

    No CLI is spawned: `subprocess.run` returns the fabricated reply, so what is
    exercised is the driver's own payload judging — the place item 1 scopes the
    detection to ("detection in the driver error path").

    The fake is installed in a NESTED context and removed again before this
    returns, so a caller that goes on to drive the green loop gets the real
    `make validate` subprocess and not this fixture's reply.
    """
    if lane == "localclaude":
        driver = LocalClaudeDriver()
        stdout = json.dumps(CLAUDE_404_PAYLOAD)
    else:
        driver = CodexDriver()
        stdout = "\n".join(json.dumps(event) for event in CODEX_404_EVENTS)
    with monkeypatch.context() as only_this_call:
        only_this_call.setattr(subprocess, "run", _fake_completed(stdout))
        with pytest.raises(DriverError) as excinfo:
            driver.session("implement the spec", cwd=cwd)
    return excinfo.value


@pytest.mark.parametrize(
    ("lane", "model"),
    [("localclaude", MISSING_CLAUDE_MODEL), ("codex", MISSING_CODEX_MODEL)],
)
def test_item1a_a_404_reply_from_either_driver_surfaces_loudly(lane, model, monkeypatch,
                                                               tmp_path):
    """Item 1, the fixture half: BOTH drivers' error shapes raise and say what
    happened — the 404 and the model name that was asked for.

    HOLDS ON THE PRE-H-1 TREE (both error paths already fold the reply text into
    the message verbatim). It is here as the premise the rest of group A stands
    on: a fix that swallowed either shape, or that reported a 404 without naming
    the model nobody can find, would be caught here.
    """
    worker = tmp_path / "w"
    worker.mkdir()
    error = _driver_404_error(monkeypatch, lane, worker)
    text = str(error)
    assert "404" in text, f"[{lane}] the 404 must survive into the error text: {text!r}"
    assert model in text, (
        f"[{lane}] the error must name the model that does not exist — item 1's defect is "
        f"12 attempts burned on 'a nonexistent model name': {text!r}"
    )


@pytest.mark.parametrize("lane", ["localclaude", "codex"])
def test_item1b_a_404_is_not_an_infrastructure_outage(lane, monkeypatch, tmp_path):
    """Item 1 asks for "a CONFIG error that fails the run loudly" — which is not
    the outage verdict.

    An infrastructure error retries the SAME attempt up a minutes-long ladder
    and then BLOCKS the slot (nothing is known about the game). A config error
    must fail at second zero instead. So the 404 class must stay outside the
    outage classifier.

    HOLDS ON THE PRE-H-1 TREE (no 404 needle is in that table today). It is a
    regression pin on the cheapest wrong fix: adding "404" to the outage
    substrings, which would route a config bug into a wait-then-block.
    """
    worker = tmp_path / "w"
    worker.mkdir()
    error = _driver_404_error(monkeypatch, lane, worker)
    assert backends_mod.is_infrastructure_error(error) is False, (
        f"[{lane}] a model-not-found 404 was classified as an infrastructure outage, so it "
        "waits out a retry ladder and then blocks the slot. Item 1: it must "
        "'surface as a CONFIG error that fails the run loudly'."
    )
    if hasattr(s2_mod, "_is_infrastructure_outage"):
        assert s2_mod._is_infrastructure_outage(error) is False, (
            f"[{lane}] the green loop's outage test claimed a 404 — same defect as above, "
            "one layer down"
        )


def _one_argument_callables(module):
    """Every function OF this module taking exactly one required positional arg.

    The discovery surface for group A's truth table. Deliberately not filtered
    by name: item 1 names no classifier, so a pin that guessed one would be
    pinning a mechanism. `run`-shaped names are excluded and `subprocess` is
    forbidden by the test's fixture, so a probe cannot spend or spawn.
    """
    out = []
    for name, obj in vars(module).items():
        if not callable(obj) or inspect.isclass(obj):
            continue
        if getattr(obj, "__module__", None) != module.__name__:
            continue
        if re.search(r"(^|_)(run|main|validate|gate|sleep|write|append)", name):
            continue
        try:
            signature = inspect.signature(obj)
        except (TypeError, ValueError):   # pragma: no cover
            continue
        required = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.default is inspect.Parameter.empty
            and parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
        ]
        if len(required) == 1:
            out.append((name, obj))
    return out


def test_item1c_the_404_class_has_a_config_classifier(monkeypatch, tmp_path, no_processes):
    """Item 1: "detection in the driver error path + routing as a config-class
    failure".

    Routing by class needs something that KNOWS the class, so this sweeps the
    driver module (and the green loop beside it) for a predicate satisfying the
    contract's own three-row table:

        a 404 / model-not-found reply, from EITHER driver   -> true
        an auth 401 (infrastructure: the credential)        -> false
        a failure that ran and came back wrong (the work)   -> false

    No predicate on the pre-H-1 tree satisfies it — `is_infrastructure_error` is
    true for the 401 row — so this is RED for the absence of the detection item
    1 asks for. Both call conventions are tried (exception and text), because
    the contract does not fix one.
    """
    worker = tmp_path / "w"
    worker.mkdir()
    # The two TRUE rows are produced by the real driver paths, not invented here.
    true_rows: list[DriverError] = [
        _driver_404_error(monkeypatch, lane, worker) for lane in ("localclaude", "codex")
    ]
    false_rows = [DriverError(text) for text in AUTH_401_TEXTS + WORK_FAILURE_TEXTS]

    found: list[str] = []
    for module in (backends_mod, s2_mod):
        for name, function in _one_argument_callables(module):
            for convert in (lambda error: error, str):
                try:
                    verdicts = [bool(function(convert(row))) for row in true_rows + false_rows]
                except Exception:   # noqa: BLE001, S112 — a non-predicate is simply not a match
                    continue
                if verdicts == [True, True, False, False, False, False]:
                    found.append(f"{module.__name__}.{name}")
                    break

    assert found, (
        "no predicate in gen/backends.py or gen/s2_implement.py tells a model-not-found "
        "404 from an auth outage and from an ordinary red session. Item 1: "
        "'a driver reply that is a model-not-found / 404 class error must surface as a "
        "CONFIG error' — surfacing AS A CLASS is what nothing here can do.\n"
        f"  true rows (must be recognised): {[str(e)[:90] for e in true_rows]}\n"
        f"  false rows (must not be):       {[str(e)[:70] for e in false_rows]}"
    )


@pytest.mark.parametrize("lane", ["localclaude", "codex"])
def test_item1d_the_green_loop_spends_no_attempts_on_a_404(lane, monkeypatch, tmp_path):
    """Item 1, the whole point: "fails the run loudly INSTEAD OF consuming
    green-loop attempts — g20261001-2 burned 12 attempts on a nonexistent model
    name", routed "before/at attempt 1".

    The cap is set to 3 so the burn is visible and cheap. Two things are
    measured, and they are the sentence's measurable half:

      * the session runner is called ONCE. A second call is attempt 2, which is
        the defect whatever verdict the loop eventually writes.
      * at most one attempt row reaches the ledger, and the verdict is NOT one
        that blames the game (`reject-to-S1` / `attempt-cap`): a config error is
        a verdict on US, the way `driver-unavailable` already is.

    HOW it surfaces is left open (A in the header): an exception out of
    `green_loop` and a config-class reject reason both pass, as long as the
    failure NAMES the model or the 404 — an operator reading it must not have to
    guess which of the two drivers' model names is wrong.
    """
    worker = tmp_path / "worker"
    instantiate_worker(worker)
    model = MISSING_CLAUDE_MODEL if lane == "localclaude" else MISSING_CODEX_MODEL
    error = _driver_404_error(monkeypatch, lane, tmp_path)
    calls: list[str | None] = []

    def runner(prompt, *, cwd, resume_id):
        calls.append(resume_id)
        raise DriverError(str(error))

    cap = 3
    raised: BaseException | None = None
    report = None
    try:
        report = green_loop(
            worker, "implement the spec", {"implementer": {"max_green_attempts": cap}},
            session_runner=runner,
        )
    except BaseException as exc:   # noqa: BLE001 — "fails the run loudly" is a legal reading
        raised = exc

    assert len(calls) == 1, (
        f"[{lane}] a 404-shaped reply was handed to the agent {len(calls)} times under a cap "
        f"of {cap}. Item 1: the failure must be routed 'before/at attempt 1' 'instead of "
        f"consuming green-loop attempts' — g20261001-2 burned 12 of them this way."
    )

    attempts_path = sidecar(worker, ATTEMPTS_SUFFIX)
    rows = (
        [json.loads(line) for line in attempts_path.read_text("utf-8").splitlines() if line.strip()]
        if attempts_path.is_file()
        else []
    )
    assert len(rows) <= 1, (
        f"[{lane}] the attempts ledger grew {len(rows)} rows from one config error: "
        f"{[row.get('index') for row in rows]}. A game that was never judged must not "
        f"collect red attempt records."
    )

    reject_path = sidecar(worker, REJECT_SUFFIX)
    reject = json.loads(reject_path.read_text("utf-8")) if reject_path.is_file() else {}
    loud = str(raised or "") + json.dumps(reject, default=str) + repr(
        getattr(report, "reject_reason", "")
    )
    assert model in loud or "404" in loud, (
        f"[{lane}] nothing in the failure names the 404 or the model that does not exist, so "
        f"the operator cannot act on it:\n  raised: {raised!r}\n  report: {report!r}\n"
        f"  verdict file: {reject or '<none>'}"
    )
    if report is not None:
        assert report.green is False, f"[{lane}] a 404 cannot be a green build"
        assert report.reject_reason not in (s2_mod.ATTEMPT_CAP_REASON, None), (
            f"[{lane}] the loop returned reject_reason {report.reject_reason!r} — the attempt "
            f"cap is a verdict ON THE GAME, and item 1's failure is a CONFIG error"
        )
        assert reject.get("verdict") != s2_mod.REJECT_VERDICT, (
            f"[{lane}] the verdict is {s2_mod.REJECT_VERDICT!r}, which routes the slot back to "
            f"spec-writing: it blames the game for a model name in the config"
        )


# =========================================================================== #
# GROUP B — item 2: NARRATOR VOCABULARY
# =========================================================================== #

# "never as a rebuild": the vocabulary an operator reads as "an hour of work is
# starting now". `build` as a NOUN is deliberately absent from this list — the
# contract's own suggested wording is "checking the build against the amended
# spec".
REBUILD_WORDS = re.compile(
    r"re-?buil[dt](?:ing|s)?|\bbuilt\b|\bbuilding\b|\bbuilds\b", re.IGNORECASE
)
# A DENIAL of a rebuild is not an announcement of one ("the declaration changed,
# nothing was rebuilt"), so a negation inside this window excuses a mention.
NEGATION = re.compile(r"\b(no|not|nothing|never|without|skip\w*|instead of)\b", re.IGNORECASE)
NEGATION_WINDOW = 40
# "must narrate as revalidation ('checking the build against the amended spec'
# or similar)" — both the contract's own words and the word `revalidation`
# itself match this.
REVALIDATION_WORDS = re.compile(r"validat|check", re.IGNORECASE)


def _rebuild_mentions(text: str) -> list[str]:
    """Rebuild vocabulary that is not inside a negation — see the header (C)."""
    offenders = []
    for match in REBUILD_WORDS.finditer(text):
        window = text[max(0, match.start() - NEGATION_WINDOW): match.start()]
        if not NEGATION.search(window):
            offenders.append(match.group(0))
    return offenders


def _decl_only_line(**extra) -> dict:
    """One ledger line for the declaration-only re-spec hop.

    The reason is `orchestrator.DECL_ONLY_REASON` — item 2: "the decl-only edge
    is distinguishable by its ledger reason". The edge itself is read off the
    committed ledger fixture `g20261001-5-ledger-at-e2-freeze.jsonl`, where
    every line carrying that reason is `spec_ok --> implemented`.
    """
    line = {
        "slug": "h1-decl-s001",
        "from": "spec_ok",
        "to": "implemented",
        "reason": orch.DECL_ONLY_REASON,
        "hashes": {"spec": "a" * 64, "game": "b" * 64, "stage_input": "c" * 64},
        "cost": None,
        "ts": "2026-10-06T00:00:00+00:00",
    }
    line.update(extra)
    return line


def test_item2a_the_decl_only_hop_narrates_as_revalidation():
    """Item 2: "a declaration-only re-spec hop must narrate as revalidation
    ('checking the build against the amended spec' or similar), never as a
    rebuild — operators read 'rebuilding' and expect an hour".

    Driven through the narrator seam the item names, with the reason the item
    names. Nothing here pins a wording: only that the sentence says revalidation
    and does not announce a build.
    """
    sentence = cli_mod.narrate(_decl_only_line(), seen={})
    assert sentence, (
        "the declaration-only hop narrates as SILENCE (`narrate` answered None). An operator "
        "must never watch a slot move without being told what moved."
    )
    offenders = _rebuild_mentions(sentence)
    assert not offenders, (
        f"the declaration-only re-spec narrates as a rebuild ({offenders}): {sentence!r}\n"
        "Item 2: it 'must narrate as revalidation ... never as a rebuild — operators read "
        "\"rebuilding\" and expect an hour (the 10-01 confusion)'."
    )
    assert REVALIDATION_WORDS.search(sentence), (
        f"nothing in {sentence!r} says the build is being CHECKED. Item 2 asks for "
        "revalidation vocabulary — 'checking the build against the amended spec' or similar."
    )
    generic = cli_mod.EDGE_NARRATION[("spec_ok", "implemented")].format(n=1, shelf="games/")
    assert sentence != generic, (
        "the declaration-only hop still narrates as the generic build row, so its ledger "
        "reason is not being read at all — item 2: 'the decl-only edge is distinguishable by "
        f"its ledger reason (DECL_ONLY_REASON)'. Both said {generic!r}."
    )


def test_item2b_the_live_narrator_says_revalidation_too(tmp_path):
    """The same promise where the operator actually reads it: the ledger tail.

    `LedgerNarrator` is pumped synchronously — `stop()` drains without ever
    starting the daemon thread — so this is the real reader over a real ledger
    file, with no thread and no sleep.
    """
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps(_decl_only_line()) + "\n", encoding="utf-8")
    out = io.StringIO()
    narrator = cli_mod.LedgerNarrator(
        ledger, batch_id="h1-decl", size=1, games_root=tmp_path / "games", out=out
    )
    narrator.stop()
    printed = out.getvalue()

    assert printed.strip(), "the narrator printed nothing for the declaration-only hop"
    offenders = _rebuild_mentions(printed)
    assert not offenders, (
        f"the operator reads a rebuild ({offenders}) for a declaration-only re-spec:\n"
        f"{printed}Item 2: 'operators read \"rebuilding\" and expect an hour'."
    )
    assert REVALIDATION_WORDS.search(printed), (
        f"the narrated hop never says the build is being checked:\n{printed}"
    )


def test_item2c_an_ordinary_build_hop_is_byte_unchanged():
    """The house rule — "every item's default = today's bytes" — on the same
    edge. Item 2 asks for "the narrator's line for that reason, not a new
    table", so a build hop with any OTHER reason must still read exactly as the
    table says.

    HOLDS ON THE PRE-H-1 TREE by construction (the expectation is computed from
    the live table, never copied), and that is the point: it is the pin that
    stops item 2 from rewording the ordinary hop.
    """
    edge = ("spec_ok", "implemented")
    expected = cli_mod.EDGE_NARRATION[edge].format(n=1, shelf="games/")
    ordinary = cli_mod.narrate(
        _decl_only_line(reason="S2 green at attempt 2"), seen={}
    )
    assert ordinary == expected, (
        f"an ordinary {edge[0]} --> {edge[1]} hop no longer narrates as its own table row:\n"
        f"  table: {expected!r}\n  said : {ordinary!r}"
    )
    for state in ("spec_ok", "implemented"):
        caption = cli_mod.next_stage_line(state)
        assert caption == cli_mod.NEXT_STAGE_NARRATION.get(state), (
            f"the {state!r} 'what it is doing now' caption drifted from its own table: "
            f"{caption!r}"
        )


# =========================================================================== #
# GROUP C — item 3: PLAY-SERVER RESCAN
# =========================================================================== #


class _HandlerProbe:
    """One request against the vendored handler, with no socket anywhere.

    `ThreadingHTTPServer` handlers can be driven directly: the response writer
    is the only part of the base class this needs, so the three send methods and
    `wfile` are supplied here and `do_GET` runs unmodified. Nothing binds a port
    — which keeps the hard rule ("no network") true even on a box where
    localhost would have worked.
    """

    def __init__(self, module, path: str):
        self.handler = type(
            "H1Probe",
            (module.Handler,),
            {
                "__init__": lambda handler: None,
                "send_response": lambda handler, code, *rest: setattr(handler, "code", code),
                "send_header": lambda handler, key, value: handler.sent.append((key, value)),
                "end_headers": lambda handler: None,
            },
        )()
        self.handler.path = path
        self.handler.sent = []
        self.handler.code = None
        self.handler.wfile = io.BytesIO()
        self.handler.headers = {}

    def get(self):
        self.handler.do_GET()
        body = self.handler.wfile.getvalue()
        return self.handler.code, body


def _write_game(catalog: Path, slug: str, game_id: str) -> Path:
    """A shelf-shaped catalog entry: `<root>/<slug>/<build>/metadata.json`.

    Two levels deep because that is the layout the vendored server discovers
    (`<root>/*/*/metadata.json`) and the layout `games/` ships.
    """
    build = catalog / slug / "game"
    build.mkdir(parents=True)
    (build / "metadata.json").write_text(
        json.dumps({
            "game_id": game_id,
            "title": slug.replace("-", " ").title(),
            "baseline_actions": [4, 7],
            "default_fps": 4,
        }),
        encoding="utf-8",
    )
    (build / "game.py").write_text("# H-1 catalog fixture; never loaded\n", encoding="utf-8")
    return build


def _load_play_server(monkeypatch, catalog: Path, tag: str):
    """Import the VENDORED server fresh, pointed at a tmp catalog.

    `PLAY_GAMES_DIR` is the server's own override and it is read at import, so
    it is set first; the module is given a unique name so each test gets its own
    startup, which is what "without a server restart" has to be measured
    against. `ONLY_RESET_LEVELS` is set through monkeypatch because the module
    sets it at import and the test process must not keep it.
    """
    monkeypatch.setenv("PLAY_GAMES_DIR", str(catalog))
    monkeypatch.setenv("ONLY_RESET_LEVELS", "true")
    assert PLAY_SERVER.is_file(), f"the vendored play server is missing: {PLAY_SERVER}"
    name = f"h1_play_server_{tag}"
    spec = importlib.util.spec_from_file_location(name, PLAY_SERVER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:                      # pragma: no cover
        sys.modules.pop(name, None)
        raise
    monkeypatch.setattr(module, "LOG_DIR", catalog.parent / "play-logs", raising=False)
    (catalog.parent / "play-logs").mkdir(parents=True, exist_ok=True)
    return module, name


def _api_games(module) -> list[dict]:
    code, body = _HandlerProbe(module, "/api/games").get()
    assert code == 200, f"/api/games answered {code}"
    return json.loads(body)


def test_item3_a_game_added_after_startup_appears_without_a_restart(monkeypatch, tmp_path):
    """Item 3: "the game list is snapshotted at startup, so every new package
    needs a server restart (bitten three times this week). Fix: re-scan the
    catalog on each /api/games request, or on a cheap top-level mtime check".

    A NEW TOP-LEVEL entry is added to the live catalog between two requests —
    the only addition both licensed mechanisms must see (header D) — and the
    second response must carry it, with the server never re-imported.
    """
    catalog = tmp_path / "catalog"
    _write_game(catalog, "alpha-run", "h1-alpha")
    module, name = _load_play_server(monkeypatch, catalog, "rescan")
    try:
        first = {game["game_id"] for game in _api_games(module)}
        assert first == {"h1-alpha"}, f"the startup catalog is wrong: {first}"

        _write_game(catalog, "beta-run", "h1-beta")
        second = {game["game_id"] for game in _api_games(module)}
    finally:
        sys.modules.pop(name, None)

    assert "h1-beta" in second, (
        "a game packaged into the served catalog is invisible to /api/games until the server "
        f"restarts (saw {sorted(second)}). Item 3: re-scan the catalog on each /api/games "
        "request, or on a cheap top-level mtime check."
    )
    assert "h1-alpha" in second, (
        f"the rescan lost a game that was already there: {sorted(second)}"
    )


def test_item3_the_rescan_keeps_the_payload_and_the_play_flow_intact(monkeypatch, tmp_path):
    """Item 3: "Keep the per-game play flow untouched."

    Two requests over an UNCHANGED catalog must be byte-identical (a rescan that
    reordered or re-shaped the list would churn the UI), the private loader path
    must stay out of the payload, and the session endpoints must still answer —
    so a catalog that reloads cannot disturb a sitting in progress.

    Mostly HOLDS ON THE PRE-H-1 TREE (a snapshot is trivially stable); it is the
    guard rail on how item 3 is allowed to achieve the test above.
    """
    catalog = tmp_path / "catalog"
    _write_game(catalog, "alpha-run", "h1-alpha")
    module, name = _load_play_server(monkeypatch, catalog, "stable")
    try:
        _, first = _HandlerProbe(module, "/api/games").get()
        _, second = _HandlerProbe(module, "/api/games").get()
        assert first == second, (
            "two /api/games requests over an unchanged catalog disagree — a rescan must be "
            f"stable:\n  {first!r}\n  {second!r}"
        )
        payload = json.loads(first)
        assert payload and all("py" not in game for game in payload), (
            f"/api/games started leaking the loader path: {payload}"
        )
        state_code, state_body = _HandlerProbe(module, "/api/state").get()
        assert state_code == 200, f"/api/state answered {state_code} — the play flow moved"
        assert isinstance(json.loads(state_body), dict)
    finally:
        sys.modules.pop(name, None)


# =========================================================================== #
# GROUP D — item 4: PLAY_COMMAND ONE-LINER
# =========================================================================== #


def test_item4_the_packaged_game_hint_names_arc_games_play(tmp_path):
    """Item 4: "the packaged-game console hint still prints the stale duckWM
    PLAY_GAMES_DIR one-liner; it should print `arc-games play`".

    Driven on the real pilot config, because that is the config the shipped
    one-liner was built from. `PLAY_GAMES_DIR` must be gone from the WHOLE
    answer, not only from the headline: the item's complaint is that a reader is
    told to drive duckWM's tree, and a stale `server`/`python` path says the
    same thing more quietly.
    """
    cfg = load_config(PILOT)
    try:
        answer = s6_mod.play_command(cfg, tmp_path / "play")
    except TypeError:
        # A fix that no longer needs a root to print `arc-games play` is a
        # legal fix; the promise is the words, not the signature.
        answer = s6_mod.play_command(cfg)

    blob = json.dumps(answer, default=str)
    command = answer["command"] if isinstance(answer, dict) and "command" in answer else blob
    assert "arc-games play" in command, (
        f"the packaged-game hint does not name `arc-games play`: {command!r}\n"
        "Item 4: 'it should print `arc-games play`'."
    )
    assert "PLAY_GAMES_DIR" not in blob, (
        f"the hint still prints the stale duckWM one-liner: {blob}\n"
        "Item 4 names exactly this: the PLAY_GAMES_DIR recipe is the thing to remove."
    )


# =========================================================================== #
# GROUP E — item 7: MAINTAINER-CLI DRAW LOCK
# =========================================================================== #


def test_item7_the_maintainer_drawer_takes_the_batch_draw_lock(monkeypatch, flock_log,
                                                               tmp_path, _protect_real_trees):
    """Item 7: "the hand-run CLI draws WITHOUT the per-batch draw flock the
    pipeline takes (P-5's residual) — take the same lock at the same scope".

    "The same lock" is the path the pipeline's own helper names
    (`orchestrator.s0_draw_lock_path(batch_id)`), and "the same scope" is around
    the whole draw — so the draw itself is stubbed (a real hand-run draw spends;
    header F) and the stub asks, from inside, whether the lock is held.

    Two observations, both rebuilt here: a `fcntl.flock` recorder that calls
    through to the real lock (so what it sees is a real lock), and a
    non-blocking probe from a second descriptor (so "held" means held).
    """
    batch_id = "h1-drawer"
    expected_lock = orch.s0_draw_lock_path(batch_id)
    assert tmp_path in expected_lock.parents, (
        f"the ideas root was not redirected into tmp — refusing to run: {expected_lock}"
    )

    held_during_draw: list[bool | None] = []

    def stub_draw(cfg, *, batch_id, seed=None, **kwargs):
        held_during_draw.append(flock_log.is_locked_now(orch.s0_draw_lock_path(batch_id)))
        return []

    monkeypatch.setattr(s0_mod, "sample_batch", stub_draw)
    monkeypatch.setattr(s0_mod, "load_config", lambda path: {"batch": {"id": batch_id}})

    assert s0_mod.main(["--config", PILOT, "--batch-id", batch_id]) == 0

    assert flock_log.records, (
        "the hand-run drawer took NO lock at all. Item 7: 'the hand-run CLI draws WITHOUT the "
        "per-batch draw flock the pipeline takes (P-5's residual) — take the same lock at the "
        f"same scope'. The pipeline's lock is {expected_lock}."
    )
    locked = flock_log.exclusive_ids()
    elsewhere = [
        str(path) for ids, path in flock_log.held_elsewhere(tmp_path).items() if ids in locked
    ]
    assert expected_lock.is_file(), (
        f"the drawer locked something, but not the per-batch draw lock {expected_lock} — item 7 "
        "says 'the SAME lock', and `orchestrator.s0_draw_lock_path` is the path the pipeline "
        f"uses. Locked instead: {elsewhere}"
    )
    assert _id_of(expected_lock) in locked, (
        f"the drawer took no exclusive flock on {expected_lock.name}. "
        f"flock calls recorded: {flock_log.records or 'none at all'}; "
        f"locked instead: {elsewhere}"
    )
    assert held_during_draw == [True], (
        "the lock was not held FOR THE DRAW itself (same scope as the pipeline's, which wraps "
        f"the whole `sample_batch` call): probe said {held_during_draw}"
    )


# =========================================================================== #
# GROUP F — item 8: CROSS-BATCH DEDUPE RACE
# =========================================================================== #

# The prose a draw needs to get past S0's coherence gate — long enough and
# narrative, so the fake never fails a draw for the wrong reason. (The recipe is
# `test_b4_sampler`'s; the text is this file's own.)
FAKE_PROSE = "Switchyard Drill\n" + (
    "A single selector walks a narrow yard of six by six tiles, and each tile it steps on "
    "either holds or gives way under the weight it carries. Some tiles hide a marker that "
    "only shows once the selector has stood on it, so the first crossing of a board is always "
    "partly blind, and a route that looked cheap costs two extra turns once the markers are "
    "out. The yard asks for every marker to be uncovered before the step counter empties, and "
    "later boards add a second marker colour behind a gate that opens only when the first "
    "colour is fully uncovered, so a plan has to interleave the two without stranding the "
    "selector behind its own discoveries."
)


def test_item8_the_shared_dedupe_history_append_is_flocked(flock_log, tmp_path,
                                                           _protect_real_trees):
    """Item 8: "two DIFFERENT batches appending the shared dedupe history race
    each other (P-5 closed only the within-batch race) — one flock around the
    shared-history append, same idiom as `_append_lines`".

    The real public draw is driven (prose injected, so nothing spends) and the
    recorder watches for an EXCLUSIVE lock on the file that append writes. The
    inode is matched rather than the path, so a `.lock` sidecar beside the
    history counts too; anything else locked under the tmp root is named in the
    failure message rather than guessed at.
    """
    history = s0_mod._history_path()
    assert tmp_path in history.parents, (
        f"the dedupe history was not redirected into tmp — refusing to run: {history}"
    )

    cfg = load_config(PILOT)
    drawn = s0_mod.sample_batch(
        cfg,
        batch_id="h1-dedupe",
        seed=20261006,
        prose_runner=lambda prompt, *args, **kwargs: FAKE_PROSE,
        out_dir=tmp_path / "ideas-out",
    )
    assert drawn, "the draw produced no ideas, so nothing was appended to pin"
    assert history.is_file(), (
        f"the draw wrote no shared dedupe history at {history}; item 8's append is the thing "
        "under test"
    )

    locked = flock_log.exclusive_ids()
    candidates = {_id_of(history)}
    for sibling in sorted(history.parent.iterdir()):
        if sibling.is_file() and history.stem in sibling.name:
            candidates.add(_id_of(sibling))

    assert locked & candidates, (
        f"the shared dedupe-history append took no exclusive flock. Item 8: 'one flock around "
        f"the shared-history append, same idiom as `_append_lines`' — two DIFFERENT batches "
        f"appending this one file race each other.\n"
        f"  history: {history}\n"
        f"  flock calls recorded: {flock_log.records or 'none at all'}\n"
        f"  anything locked under tmp: "
        f"{[str(p) for i, p in flock_log.held_elsewhere(tmp_path).items() if i in locked]}"
    )

    rows = [json.loads(line) for line in history.read_text("utf-8").splitlines() if line.strip()]
    assert len(rows) == len(drawn), (
        f"the locked append wrote {len(rows)} history row(s) for {len(drawn)} drawn idea(s): "
        f"{rows}"
    )


# =========================================================================== #
# GROUP G — item 9: GATE.GATE.* DOUBLE-PREFIX
# =========================================================================== #

# Either of the two spellings by which a stage prefixes a check id with its own
# namespace. Used ONLY to decide whether the stage still prefixes at all — see
# header (E) for why the answer changes nothing about the promise.
PREFIXING_SPELLINGS = (
    re.compile(r"gate\.\{[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*\}"),
    re.compile(r"""["']gate\.["']\s*\+"""),
)


def _gate_rows(tmp_path: Path):
    """The gate's own standalone check rows, driven to a real FAIL.

    `gate_checks` is the single entry point the gate stage calls, and
    `term-witness` goes red on a corroborated finding in armed mode — so this is
    the gate's reason/key builders on a driven fixture, which is what item 9's
    blind sentence asks for. No frames, no worker code, no driver.
    """
    worker = tmp_path / "worker"
    worker.mkdir(exist_ok=True)
    verifier_report = {"diff": {"unimplemented_terms": ["state.wait"]}, "term_window": 2}
    answer = gate_mod.gate_checks(
        worker, verifier_report,
        cfg={"verifier": {"term_witness": "fail"}},
        out_dir=tmp_path / "gate",
    )
    rows = answer["checks"]
    assert any(row.status == "fail" for row in rows), (
        f"fixture drift: no gate row failed, so no code is emitted to inspect: "
        f"{[(row.check_id, row.status) for row in rows]}"
    )
    return rows


def test_item9_the_gate_emits_no_doubled_prefix(tmp_path):
    """Item 9: "some gate-side key or reason carries a doubled `gate.` prefix ...
    Find it (grep `gate.gate`), fix the producer".

    The gate's prefix is DISCOVERED (what its own finding builder puts in front
    of a check key), and whether the stage still applies that prefix to a
    standalone row's `check_id` is read off the live source — so the pin is on
    the EMITTED spelling and passes whichever side of the composition the fix
    lands on (header E). What it refuses is the doubled form reaching a key, a
    reason, or a row's own note.
    """
    rows = _gate_rows(tmp_path)
    prefixed = orch._visual_finding("field-index", {"note": "n"})["code"]
    prefix = prefixed[: -len("field-index")]
    assert prefix.endswith("."), f"could not discover the gate's prefix from {prefixed!r}"

    # LEAD RETARGET 2026-10-06 — header E's caveat, inverted: the source probe
    # could not tell "an f-string gate-prefix exists SOMEWHERE in the module"
    # (the futility list and the layer codes prefix OTHER names, legitimately)
    # from "the stage prefixes a ROW's check_id", so the correct fix read as
    # still-prefixing and the simulation doubled — a false red. The fix gave
    # the composition ONE name, `_gate_code`, so the pin now observes the real
    # seam and stays red if doubling returns through it; the simulation
    # survives only as the pre-fix fallback that keeps this red on a tree
    # with no such seam.
    compose = getattr(orch, "_gate_code", None)
    if compose is not None:
        emitted = {row.check_id: compose(row.check_id) for row in rows}
    else:
        source = inspect.getsource(orch)
        stage_prefixes = any(spelling.search(source) for spelling in PREFIXING_SPELLINGS)
        emitted = {
            row.check_id: (prefix + row.check_id) if stage_prefixes else row.check_id
            for row in rows
        }
    doubled = {
        check_id: code for check_id, code in emitted.items() if (prefix + prefix) in code
    }
    assert not doubled, (
        f"the gate emits a doubled {prefix!r} prefix: {doubled}.\n"
        f"Item 9: 'some gate-side key or reason carries a doubled `gate.` prefix ... fix the "
        f"producer'. The gate's own check ids are {sorted(emitted)}, its visual check ids are "
        f"{list(orch.GATE_VISUAL_CHECKS)}, and the stage "
        f"{'still prefixes' if stage_prefixes else 'no longer prefixes'} a check_id — one "
        f"namespace has to give."
    )
    for row in rows:
        assert prefix + prefix not in str(row.note or ""), (
            f"{row.check_id}'s note carries the doubled prefix: {row.note!r}"
        )
        assert row.check_id.count(prefix) <= 1, (
            f"the check id itself is doubled: {row.check_id!r}"
        )
    assert all(code.startswith(prefix) for code in emitted.values()), (
        f"a gate code lost the gate's own namespace: {emitted}"
    )


def test_item9_readers_stay_tolerant_of_the_historic_doubled_form(tmp_path):
    """Item 9: "keep any shipped-artifact READER tolerant of the historic
    doubled form (shipped reports are immutable)".

    The reader a gate code reaches is the futility classifier that decides
    whether a re-spec can answer it, and both spellings must classify the same:
    a report shipped before the fix must route exactly as it did.

    HOLDS ON THE PRE-H-1 TREE (both spellings already agree). It is the pin that
    stops the fix from being made by teaching the reader only the new spelling.
    """
    rows = _gate_rows(tmp_path)
    prefix = orch._visual_finding("field-index", {"note": "n"})["code"][: -len("field-index")]
    for row in rows:
        stem = row.check_id.removeprefix(prefix)
        single = f"{prefix}{stem}"
        historic = f"{prefix}{prefix}{stem}"
        assert orch._spec_answerable(historic) == orch._spec_answerable(single), (
            f"a shipped report's {historic!r} now routes differently from {single!r} "
            f"({orch._spec_answerable(historic)} vs {orch._spec_answerable(single)}) — item 9: "
            f"'keep any shipped-artifact READER tolerant of the historic doubled form'"
        )


# A guard on this file's own hermeticity: every tmp root above comes from
# pytest, but a stray default argument somewhere could still reach the real
# trees, and a blind file that polluted `out/` or `games/` would be worse than
# no blind file.
def test_this_file_never_writes_the_real_out_or_games_trees(tmp_path):
    """Hard rule: "never write under the real out/ or games/; duckWM read-only"."""
    assert tempfile.gettempdir() in str(tmp_path) or "pytest" in str(tmp_path), tmp_path
    for root in (REPO_ROOT / "out", REPO_ROOT / "games"):
        if not root.is_dir():
            continue
        assert tmp_path not in root.parents, f"{root} is inside the tmp root?"
    assert REPO_ROOT not in Path(s0_mod._history_path()).parents, (
        f"the dedupe history is still pointed at the real tree: {s0_mod._history_path()}"
    )
