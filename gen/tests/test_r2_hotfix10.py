"""R2 hotfix #10 acceptance: accept-latching, reject-reset, transport retry.

Run: .venv/bin/python -m pytest gen/tests/test_r2_hotfix10.py -v

Three behaviours, all of them found live in the pilot's R2 run:

  A. ACCEPT-LATCHING. `played --> implemented: crash` (architecture §4) sends a
     slot back to `implemented`, and `NEXT_STAGE["implemented"]` is `s3_verify`
     — so a battery crash re-buys the S2b audit for a game S2b ALREADY passed,
     on bytes that did not move. When the slot's own history records an
     `implemented -> verified` line against the CURRENT game hash, and S2b's
     report is still beside the worker, the runner latches: back to `verified`,
     no capture, no session, no cost.
  B. COUNTER RESET AT ACCEPT. `_verifier_rejects_against` derives the ×2
     escalation counter from content, so it survives a kill. It counted every
     reject ever recorded against a spec — including rejects the slot had since
     ANSWERED with an accept. Two rejects, an accept, one reject, and the slot
     escalated to respec on a game S2b had just passed. Rejects are counted
     since the last accept.
  C. BATTERY TRANSPORT RETRY. A TLS handshake timeout killed a battery mid-pass
     and the whole run was charged for nothing. A transport failure is retried
     with backoff; an auth failure is not retried at all.

Written against the frozen R2 hotfix-10 mini-contract while `gen/orchestrator.py`
and `gen/s5_battery.py` were changed in parallel. No line of that work was read:
every seam below was located in the PRE-hotfix source and is re-resolved at call
time, so this file COLLECTS cleanly before the implementation lands and fails
named tests rather than the module.

Three standing rules this file keeps (the test_r2_hotfix6/9 precedent):

  * NO API call, ever. Group A drives the REAL `s3_verify` runner with its two
    expensive entries (`frames.capture_worker_isolated` and
    `s3_verify.run_agent_pass`) monkeypatched to raise — reaching one is a
    result, never a spend. Group C's chat is a scripted fake. b11's
    `_no_network_no_agent` guard is re-bound here, so a stray `get_driver`,
    `urlopen` or `create_connection` fails the test loudly.
  * NO writes outside `tmp_path`. Every corpus below is planted under
    `tmp_path`, and b11's `_repo_batches_untouched` guard is re-bound so a
    stray write into the repo batch root fails loudly.
  * NOTHING IS READ OUT OF `out/`. The spec is the committed B5 fixture
    (`fixtures/specs/good-spec.yaml`), the game/solver pair is the committed
    `toy_worker/`, and the S2b report is hand-built here to `REPORT_KEYS`.

WHICH SEAMS WERE DISCOVERED, and where (none of them assumed):

  * `orchestrator.default_runners()["s3_verify"]` — the runner under test in A.
    Its expensive entries are imported INSIDE the runner, so patching the
    module attribute is what the runner sees (h9's group-C precedent).
  * `orchestrator._game_hash(worker_dir)` — `sha(game.py + solver.py)`,
    architecture §2's ⊕. Never recomputed here: a test that re-implemented the
    hash would pass against an implementation that made the same mistake twice.
  * `s3_verify.REPORT_SUFFIX` / `FRAMES_SUFFIX` — the two artifacts a full
    verify leaves as SIBLINGS of the worker dir (`worker.verifier-report.json`,
    `worker.frames.json`). Both are spelled through the constants, never as
    literals, so a rename moves this file with the implementation.
  * `orchestrator._verifier_rejects_against(history, spec)` — group B's target.
    Its second argument is the SPEC HASH (`str | None`): the call site builds it
    as `_sha256_file(spec_dir / "spec.yaml")`, not as a spec document.
  * `orchestrator._line(...)` — every history line below is built through the
    machine's own validated line constructor, in the frozen key order
    (`LEDGER_KEYS`), so a hand-written line cannot drift from what a replay
    produces, and an edge §4 does not draw cannot be tested by accident.
  * `s5_battery._turn_action(chat, model, ledger, *, system, observation,
    action_ids)` — the one function that wraps `chat` today, and so "the turn
    seam" group C drives.
  * The transport constants are DISCOVERED BY NAME (`RETRY` / `RETRIES` /
    `BACKOFF` / `ATTEMPT`, minus B9's unrelated `PROTOCOL_RETRIES`) and the
    sleeps are pinned against them, never against a literal.

Contract readings this file encodes where the hotfix-10 contract left a choice
open — each one is a line to renegotiate, not a fact:

  * "history CONTAINS an accept" is read literally: the accept does NOT have to
    be the last line. The live case is exactly the one where it is not — the
    crash line sits after it — so that history is the primary case, and a bare
    one-line history is the parametrized second. An implementation that looks
    only at `history[-1]` fails the primary case, deliberately.
  * The accept edge is `implemented -> verified` and the reject edge is
    `implemented -> spec_ok` (§4's own two edges out of `implemented`, and
    b11's reading in `_replay`'s reject tally). Nothing here matches on the
    reason TEXT of either.
  * "with `hashes.game` equal to the CURRENT game hash" is pinned on the game
    hash ALONE: every history line in group A carries the true spec hash, and
    A's mismatch case moves `hashes.game` only. If the implementation also
    requires `hashes.spec` to match, every test here still passes — the
    complement (a matching game hash under a MOVED spec hash) is NOT pinned,
    because the contract does not say which way that should go. RECORDED GAP.
  * "the verifier-report sibling deleted -> falls through" is pinned as: the
    forbidden leg is REACHED, and what comes out is `_Reached` and nothing
    else. A `FileNotFoundError`/`KeyError` escaping the latch logic fails the
    test on its exception type, which is the "no exception from the latch
    logic itself" half of that clause.
  * The frames sibling is planted on every group-A drive and never deleted:
    the contract names the REPORT as the artifact whose absence breaks the
    latch. Whether a missing frames file should also break it is NOT pinned.
    RECORDED GAP.
  * The latch's `artifacts` are not pinned to a key set (the contract does not
    fix one). What IS pinned is that every path it declares exists on disk —
    a latch declares artifacts it did not write, so it can only name files that
    were already there.
  * "cost None" is pinned as `result["cost"] is None`, the `_result` shape's
    own "nothing was spent" (not a zero row).
  * B's reset is read as "rejects recorded SINCE the last accept against THIS
    spec". B4's two cases are built so that BOTH readings of an accept of a
    DIFFERENT spec (resets / does not reset S's counter) give the same answer,
    because the contract does not fix that one. RECORDED GAP.
  * Group C drives `_turn_action` because the contract says "the turn yields
    the success" — the transport retry sits INSIDE one turn, not around it. If
    the retry is implemented one level up (around the whole turn, in
    `_run_pass`), every group-C test fails, and that is the renegotiation.
  * The two error messages are built in the OpenRouter driver's own shapes
    (`[openrouter] request to <url> failed: …` for a socket/TLS failure,
    `[openrouter] HTTP 401 from <url>: …` for auth), each carrying the
    substring the contract quotes. Which OTHER transport messages retry
    (connection reset, DNS, a 5xx, a read timeout) is not contracted and not
    pinned here. RECORDED GAP — worth freezing before the next live run.
  * "any sleeps are monkeypatched to record rather than wait" patches
    `time.sleep` AND any module-level callable in `gen.s5_battery` whose name
    contains "sleep", so both `import time; time.sleep(x)` and a
    `from time import sleep` / `_sleep = time.sleep` alias are recorded.
  * Two invariants group C pins that the contract implies rather than states,
    both renegotiable: a failed transport attempt returned no `ChatResult`, so
    the ledger cannot be charged for it; and the transport budget is not B9's
    malformed-reply budget (`PROTOCOL_RETRIES`), so a turn that spent transport
    retries still gets its one protocol correction.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import time
from pathlib import Path

import pytest
from arcengine import GameAction

from gen import frames as frames_module
from gen import orchestrator as orch
from gen import s3_verify as verify_module
from gen import s5_battery as bat
from gen.backends import OPENROUTER_URL, ChatResult, DriverError
from gen.config import load_config

# b11's two standing guards (imported, never copied). Fixtures have to be
# re-bound here, because pytest resolves a fixture by looking up that name in
# the REQUESTING module.
from gen.tests import test_b11_pipeline as b11

_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched

TESTS = Path(__file__).resolve().parent
TOY = TESTS / "toy_worker"
FIXTURES = TESTS / "fixtures/specs"
GOOD_SPEC = FIXTURES / "good-spec.yaml"
IDEA_FIXTURE = FIXTURES / "idea-001.json"

PILOT_CONFIG = "config/b001-pilot.yaml"

#: Loaded at IMPORT — `load_config` resolves a relative path against
#: `gen.config.REPO_ROOT`, which the `batch_home`-style fixtures re-root.
_PILOT_CFG = load_config(PILOT_CONFIG)

BATCH_ID = "b001-pilot"
SLUG = "fogbound-switchyard"

#: stand-in spec hashes. `_check_hashes` takes any string, and group B never
#: needs these to be the digest of anything — they are identities, compared.
SPEC_S = "5" * 64
SPEC_T = "7" * 64
STAGE_INPUT = "a" * 64

#: a game hash that is not the planted worker's (group A's mismatch case).
STALE_GAME = "0" * 64

#: §4's own two edges out of `implemented` — the accept and the reject.
ACCEPT_EDGE = ("implemented", "verified")
REJECT_EDGE = ("implemented", "spec_ok")


# --------------------------------------------------------------------------
# helpers — ledger lines, built by the machine's own validated constructor
# --------------------------------------------------------------------------


def _hashes(spec: str | None, game: str | None) -> dict:
    return {"spec": spec, "game": game, "stage_input": STAGE_INPUT}


def _edge(from_state: str, to_state: str, reason: str, *, spec: str | None,
          game: str | None) -> dict:
    """One ledger line, exactly as a replay reads it back off disk."""
    return orch._line(slug=SLUG, from_state=from_state, to_state=to_state, reason=reason,
                      hashes=_hashes(spec, game), cost=None)


def _accept(game: str, *, spec: str | None = SPEC_S) -> dict:
    return _edge(*ACCEPT_EDGE, "S2b clean", spec=spec, game=game)


def _reject(game: str, *, spec: str | None = SPEC_S) -> dict:
    return _edge(*REJECT_EDGE, "verifier reject: undeclared-deception", spec=spec, game=game)


def _crash_return_history(game: str) -> tuple[dict, ...]:
    """The LIVE shape: S2b accepted, the slot ran on, the battery crashed, and
    §4 sent it back to `implemented` — where `s3_verify` runs again."""
    return (
        _accept(game),
        _edge("verified", "gated", "structural + robustness green (gated)",
              spec=SPEC_S, game=game),
        _edge("gated", "baselined", "g-sampler + cap-fit: 41", spec=SPEC_S, game=game),
        _edge("baselined", "played", "battery complete", spec=SPEC_S, game=game),
        _edge("played", "implemented", "battery crash at pass 2 level 3",
              spec=SPEC_S, game=game),
    )


def _bare_accept_history(game: str) -> tuple[dict, ...]:
    return (_accept(game),)


def _reject_then_reimplement_history(game: str) -> tuple[dict, ...]:
    """Rejects only — S2b rejected and S2 re-implemented. Never an accept."""
    return (
        _reject(game),
        _edge("spec_ok", "implemented", "validate green in 1 attempt(s)",
              spec=SPEC_S, game=game),
    )


def _bare_reject_history(game: str) -> tuple[dict, ...]:
    return (_reject(game),)


# --------------------------------------------------------------------------
# helpers — group A's planted corpus slot and its unit ctx
# --------------------------------------------------------------------------


class _Reached(Exception):
    """Raised by an entry of `s3_verify` that a latched accept must skip."""

    def __init__(self, name: str) -> None:
        super().__init__(f"s3_verify reached {name}() — a latched accept does no verify work")
        self.name = name


def _boom(name: str):
    def forbidden(*args, **kwargs):
        raise _Reached(name)

    return forbidden


#: the two expensive entries. `capture_worker_isolated` spawns a fresh
#: interpreter per capture (R2 hotfix #8); `run_agent_pass` is the paid session.
FORBIDDEN_LEGS = ("capture_worker_isolated", "run_agent_pass")


def _forbid_the_verify_work(monkeypatch) -> None:
    """Both entries are imported INSIDE the runner, so patching the module
    attribute is what the runner sees when it is called."""
    monkeypatch.setattr(frames_module, "capture_worker_isolated",
                        _boom("capture_worker_isolated"))
    monkeypatch.setattr(verify_module, "run_agent_pass", _boom("run_agent_pass"))


def _pass_report(worker: Path, frames_path: Path) -> dict:
    """A clean S2b report, hand-built to `s3_verify.REPORT_KEYS`."""
    agent = {key: None for key in verify_module.AGENT_KEYS}
    agent["staged_copy_verified"] = True
    agent["claims"] = {key: [] for key in verify_module.CLAIMS_KEYS}
    report = {
        "schema_version": verify_module.SCHEMA_VERSION,
        "game_id": SLUG,
        "worker": str(worker),
        "mode": "full",
        "canon": {"payload_chars": 0},
        "frames": str(frames_path),
        "checks": [],
        "required_rows": {},
        "agent": agent,
        "diff": {key: [] for key in verify_module.DIFF_KEYS},
        "verdict": "pass",
        "reject_reasons": [],
        "versions": {},
    }
    assert set(report) == set(verify_module.REPORT_KEYS), (
        "fixture drift: this hand-built report no longer carries exactly "
        f"s3_verify.REPORT_KEYS — missing {sorted(set(verify_module.REPORT_KEYS) - set(report))}, "
        f"extra {sorted(set(report) - set(verify_module.REPORT_KEYS))}"
    )
    return report


def _verify_siblings(worker: Path) -> tuple[Path, Path]:
    """The two files a full verify leaves BESIDE the worker dir — spelled
    through `s3_verify`'s own suffixes, never as literals."""
    return (worker.with_name(worker.name + verify_module.REPORT_SUFFIX),
            worker.with_name(worker.name + verify_module.FRAMES_SUFFIX))


def _plant_slot(tmp_path: Path) -> tuple[Path, Path]:
    """`corpus/<batch>/<slug>/` as S2 + a clean S2b left it (architecture §2)."""
    spec_dir = tmp_path / "corpus" / BATCH_ID / SLUG
    worker = spec_dir / orch.WORKER_DIRNAME
    worker.mkdir(parents=True)
    shutil.copy2(TOY / "game.py", worker / "game.py")
    shutil.copy2(TOY / "solver.py", worker / "solver.py")
    (spec_dir / "spec.yaml").write_bytes(GOOD_SPEC.read_bytes())
    (spec_dir / "idea.json").write_bytes(IDEA_FIXTURE.read_bytes())

    report_path, frames_path = _verify_siblings(worker)
    report_path.write_text(
        json.dumps(_pass_report(worker, frames_path), indent=2) + "\n", encoding="utf-8"
    )
    frames_path.write_text(
        json.dumps({"source": "solver", "levels": []}, indent=2) + "\n", encoding="utf-8"
    )
    assert orch._game_hash(worker) is not None, (
        "fixture drift: the planted worker has no game.py, so §2's game hash is None"
    )
    return spec_dir, worker


def _ctx(tmp_path: Path, spec_dir: Path, history, *, verifier_rejects: int = 0):
    """The ctx §4 hands `s3_verify` at `implemented`, built under `tmp_path`."""
    ideas = tmp_path / "ideas" / BATCH_ID
    ideas.mkdir(parents=True, exist_ok=True)
    idea_path = ideas / "idea-001.json"
    if not idea_path.exists():
        idea_path.write_bytes(IDEA_FIXTURE.read_bytes())
    return orch.SlotContext(
        cfg=copy.deepcopy(_PILOT_CFG),
        batch_id=BATCH_ID,
        slug=SLUG,
        index=1,
        state="implemented",
        stage="s3_verify",
        attempt=1,
        batch_dir=tmp_path / "batches" / BATCH_ID,
        ideas_dir=ideas,
        idea_path=idea_path,
        corpus_dir=spec_dir.parent,
        spec_dir=spec_dir,
        respec_count=0,
        verifier_rejects=verifier_rejects,
        green_failures=0,
        history=tuple(history),
    )


def _verify_runner():
    runners = orch.default_runners()
    assert "s3_verify" in runners, (
        f"default_runners() must key S2b as 's3_verify'; it has {sorted(runners)}"
    )
    return runners["s3_verify"]


def _assert_did_the_real_work(excinfo) -> None:
    """The fall-through pin: one of the two forbidden legs was reached, and
    what came out is `_Reached` — not an error escaping the latch logic."""
    assert excinfo.value.name in FORBIDDEN_LEGS, (
        f"expected the runner to reach one of {list(FORBIDDEN_LEGS)}, it reached "
        f"{excinfo.value.name!r}"
    )


# --------------------------------------------------------------------------
# A: accept-latching — a verified game is not re-verified
# --------------------------------------------------------------------------


LATCHING_HISTORIES = (
    ("crash-return", _crash_return_history),
    ("bare-accept", _bare_accept_history),
)


@pytest.mark.parametrize(
    "build", [h[1] for h in LATCHING_HISTORIES], ids=[h[0] for h in LATCHING_HISTORIES]
)
def test_a_an_accept_against_the_current_game_latches(tmp_path, monkeypatch, build):
    """A.1: to_state `verified`, reason names the latch, no cost, no work."""
    spec_dir, worker = _plant_slot(tmp_path)
    history = build(orch._game_hash(worker))
    _forbid_the_verify_work(monkeypatch)

    result = _verify_runner()(_ctx(tmp_path, spec_dir, history))

    assert result["to_state"] == "verified", (
        "a latched accept re-enters §4 at the state the accept already reached; "
        f"got {result['to_state']!r}"
    )
    assert result["ok"] is True, (
        f"`_work_slot` raises on a non-success to_state out of s3_verify, got {result!r}"
    )
    assert isinstance(result.get("reason"), str) and "latched" in result["reason"].lower(), (
        "the reason has to say the verify was LATCHED — it is the only record on the ledger "
        f"line that this round bought nothing; got {result.get('reason')!r}"
    )
    assert result["cost"] is None, (
        f"a latch spends nothing, so it reports no cost row at all; got {result['cost']!r}"
    )
    for name, path in (result.get("artifacts") or {}).items():
        assert Path(path).exists(), (
            f"a latch declares artifacts it did NOT write, so every one must already be on "
            f"disk: {name}={path}"
        )


def test_a_the_latch_leaves_the_existing_report_and_frames_byte_identical(tmp_path, monkeypatch):
    """A.1, restated as the invariant that matters: the latch is a no-op on
    disk. A latch that rewrote S2b's report would erase the audit it claims."""
    spec_dir, worker = _plant_slot(tmp_path)
    report_path, frames_path = _verify_siblings(worker)
    before = (report_path.read_bytes(), frames_path.read_bytes())
    _forbid_the_verify_work(monkeypatch)

    _verify_runner()(_ctx(tmp_path, spec_dir, _crash_return_history(orch._game_hash(worker))))

    assert (report_path.read_bytes(), frames_path.read_bytes()) == before, (
        "the latch rewrote S2b's report and/or its frames — it did no verify work, so it has "
        "nothing new to write"
    )


def test_a_a_different_game_hash_does_not_latch(tmp_path, monkeypatch):
    """A.2: the accept is against OTHER bytes, so the audit has to be re-bought."""
    spec_dir, worker = _plant_slot(tmp_path)
    assert STALE_GAME != orch._game_hash(worker), "fixture drift: the stale hash is the real one"
    _forbid_the_verify_work(monkeypatch)

    with pytest.raises(_Reached) as excinfo:
        _verify_runner()(_ctx(tmp_path, spec_dir, _crash_return_history(STALE_GAME)))
    _assert_did_the_real_work(excinfo)


def test_a_a_missing_verifier_report_does_not_latch(tmp_path, monkeypatch):
    """A.3: the accept's evidence is gone, so the latch falls through — and the
    latch logic itself raises nothing on the way."""
    spec_dir, worker = _plant_slot(tmp_path)
    report_path, _frames = _verify_siblings(worker)
    report_path.unlink()
    assert not report_path.exists()
    _forbid_the_verify_work(monkeypatch)

    with pytest.raises(_Reached) as excinfo:
        _verify_runner()(
            _ctx(tmp_path, spec_dir, _crash_return_history(orch._game_hash(worker)))
        )
    _assert_did_the_real_work(excinfo)


REJECT_ONLY_HISTORIES = (
    ("reject-then-reimplement", _reject_then_reimplement_history),
    ("bare-reject", _bare_reject_history),
    ("empty", lambda game: ()),
)


@pytest.mark.parametrize(
    "build", [h[1] for h in REJECT_ONLY_HISTORIES], ids=[h[0] for h in REJECT_ONLY_HISTORIES]
)
def test_a_a_history_without_an_accept_never_latches(tmp_path, monkeypatch, build):
    """A.4: only an ACCEPT latches. A reject against this very game hash is the
    opposite record — S2b looked at these bytes and said no."""
    spec_dir, worker = _plant_slot(tmp_path)
    _forbid_the_verify_work(monkeypatch)

    with pytest.raises(_Reached) as excinfo:
        _verify_runner()(_ctx(tmp_path, spec_dir, build(orch._game_hash(worker))))
    _assert_did_the_real_work(excinfo)


# --------------------------------------------------------------------------
# B: `_verifier_rejects_against` — the ×2 counter starts over at an accept
# --------------------------------------------------------------------------


def _count(history, spec: str | None = SPEC_S) -> int:
    return orch._verifier_rejects_against(tuple(history), spec)


GAME = "b" * 64


def test_b_the_counter_is_the_rejects_since_the_last_accept():
    """B.1: reject, accept, reject -> 1. The answered reject is spent."""
    history = (_reject(GAME), _accept(GAME), _reject(GAME))
    assert _count(history) == 1, (
        "an accept ANSWERS every reject recorded against this spec before it; counting them "
        "again escalates a slot to respec on a game S2b has just passed"
    )


def test_b_without_an_accept_the_semantics_are_unchanged():
    """B.2: two rejects and no accept still escalate (the ×2 cap is the point)."""
    history = (_reject(GAME), _reject(GAME))
    assert _count(history) == 2
    assert orch.VERIFIER_REJECT_CAP_ESCALATE == 2, (
        "the cap this counter feeds is §4's `verifier reject ×2 -> respec`; if it moved, this "
        "test's premise moved with it"
    )


def test_b_an_accept_after_the_last_reject_zeroes_the_counter():
    """B.3: reject, accept -> 0."""
    assert _count((_reject(GAME), _accept(GAME))) == 0


def test_b_two_rejects_then_an_accept_then_one_reject_is_one():
    """B.1 at the cap: the slot had escalated, the re-spec was accepted, and
    the next reject starts a fresh pair — not an instant re-escalation."""
    history = (_reject(GAME), _reject(GAME), _accept(GAME), _reject(GAME))
    assert _count(history) == 1


def test_b_an_empty_history_counts_nothing():
    assert _count(()) == 0


def test_b_rejects_of_another_spec_are_never_counted():
    """B.4, half one: a different spec hash is a different identity (§2)."""
    history = (_reject(GAME, spec=SPEC_T), _reject(GAME, spec=SPEC_T))
    assert _count(history, SPEC_S) == 0, (
        "these rejects were recorded against another spec; a re-spec is exactly when the "
        "counter starts over"
    )
    assert _count(history, SPEC_T) == 2, "…and they do still count against their OWN spec"


def test_b_another_specs_accept_does_not_spend_this_specs_rejects():
    """B.4, half two. Both readings of a foreign accept agree on this history
    (the two S rejects follow it either way), so it pins the part the contract
    fixed without pinning the part it left open."""
    history = (_reject(GAME, spec=SPEC_T), _accept(GAME, spec=SPEC_T),
               _reject(GAME), _reject(GAME))
    assert _count(history, SPEC_S) == 2


def test_b_a_none_spec_matches_no_hashed_line():
    """The call site passes None when no spec.yaml is on disk yet."""
    assert _count((_reject(GAME), _accept(GAME), _reject(GAME)), None) == 0


def test_b_the_counter_takes_the_spec_hash_not_the_spec_document():
    """The second argument's shape, pinned where it is built: the call site
    hands it `_sha256_file(spec_dir / "spec.yaml")` — a hex string or None."""
    line = _reject(GAME)
    assert set(line) == set(orch.LEDGER_KEYS), (
        f"fixture drift: a history line no longer has {list(orch.LEDGER_KEYS)}"
    )
    assert set(line["hashes"]) == set(orch.HASH_KEYS)
    assert _count((line,), line["hashes"]["spec"]) == 1, (
        "the counter compares against `hashes.spec` — a hex string — so passing that exact "
        "value back must match the line it came from"
    )


# --------------------------------------------------------------------------
# C: the battery's turn seam retries a TRANSPORT failure, not an auth one
# --------------------------------------------------------------------------


MODEL = "duck/fake-model"
SYSTEM = "you are playing a grid game"
OBSERVATION = "LEVEL 1\n000000\n"
LEDGER_CAP = 10**9

#: `PROTOCOL_RETRIES` is B9 §3's malformed-reply budget — a different contract,
#: never the transport one, whatever the transport constants end up called.
_NOT_TRANSPORT = {"PROTOCOL_RETRIES"}
_RETRY_NAME_RE = re.compile(r"RETRY|RETRIES|BACKOFF|ATTEMPT")


def _transport_error(tag: str = "") -> DriverError:
    """What `OpenRouterDriver.chat` raises when the socket/TLS layer fails —
    its own `except OSError` shape, carrying the contract's substring."""
    return DriverError(
        f"[openrouter] request to {OPENROUTER_URL} failed: "
        f"_ssl.c:1000: The handshake operation timed out{tag}"
    )


def _auth_error() -> DriverError:
    """The driver's 401 shape: a key problem, which no amount of waiting fixes."""
    return DriverError(
        f"[openrouter] HTTP 401 from {OPENROUTER_URL}: 401 unauthorized — no auth credentials "
        "found. Fix: export OPENROUTER_API_KEY=…"
    )


class _FakeChat:
    """A scripted chat seam (b9's fake, narrowed): an Exception in the script is
    RAISED on that call, a string is returned as that reply's text."""

    def __init__(self, script) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    def __call__(self, messages, *, model=None, **kwargs) -> ChatResult:
        index = len(self.calls)
        self.calls.append({"messages": messages, "model": model, "kwargs": dict(kwargs)})
        assert index < len(self.script), (
            f"chat was called {index + 1} time(s); this test scripted {len(self.script)}"
        )
        outcome = self.script[index]
        if isinstance(outcome, BaseException):
            raise outcome
        return ChatResult(
            driver="openrouter", model_requested=model or MODEL, model_reported=None,
            text=outcome, tokens_in=1, tokens_out=1, usd_cost=0.0, raw={"fake": True},
        )


@pytest.fixture
def sleeps(monkeypatch) -> list:
    """Every wait the turn asks for, recorded instead of taken."""
    recorded: list = []

    def _record(seconds):
        recorded.append(seconds)

    monkeypatch.setattr(time, "sleep", _record)
    # …and any alias bound at import time (`from time import sleep`, `_sleep = …`).
    for name, value in list(vars(bat).items()):
        if "sleep" in name.lower() and callable(value):
            monkeypatch.setattr(bat, name, _record)
    return recorded


def _retry_constants() -> dict:
    return {
        name: value for name, value in vars(bat).items()
        if name.isupper() and _RETRY_NAME_RE.search(name) and name not in _NOT_TRANSPORT
    }


def _backoff() -> list[float]:
    """The transport backoff delays, from the module's OWN constant."""
    found = _retry_constants()
    for _name, value in sorted(found.items()):
        if (isinstance(value, (tuple, list)) and value
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
            return [float(v) for v in value]
    raise AssertionError(
        "gen.s5_battery must expose the transport backoff delays as a module constant — a "
        "non-empty tuple/list of seconds whose name carries RETRY/BACKOFF. The "
        f"RETRY/RETRIES/BACKOFF/ATTEMPT names it exposes are {sorted(found) or 'none'}. "
        "Pinning the sleeps against a literal instead would freeze this test to a number the "
        "implementation is free to change."
    )


def _max_attempts() -> int:
    """Total transport attempts for ONE chat call, from the module's constants."""
    found = _retry_constants()
    for name, value in sorted(found.items()):
        if "ATTEMPT" in name and isinstance(value, int) and not isinstance(value, bool):
            return value
    for name, value in sorted(found.items()):
        if "RETRY" in name and isinstance(value, int) and not isinstance(value, bool):
            return value + 1
    return len(_backoff()) + 1


def _turn_seam():
    fn = getattr(bat, "_turn_action", None)
    assert callable(fn), (
        "gen.s5_battery must expose the turn seam `_turn_action(chat, model, ledger, *, system, "
        "observation, action_ids)` — the one function that wraps `chat`; it exposes "
        f"{[n for n in dir(bat) if 'turn' in n.lower() or 'chat' in n.lower()]!r}"
    )
    return fn


def _turn(chat, ledger=None):
    ledger = bat._Ledger(cap=LEDGER_CAP) if ledger is None else ledger
    return _turn_seam()(chat, MODEL, ledger, system=SYSTEM, observation=OBSERVATION,
                        action_ids=[1])


def test_c_the_backoff_table_and_the_attempt_count_agree():
    """The discovery, pinned as an invariant: N delays sit BETWEEN N+1 attempts.
    This test is where a renamed or re-shaped constant surfaces first."""
    delays = _backoff()
    assert _max_attempts() == len(delays) + 1, (
        f"the module says {_max_attempts()} transport attempts but publishes {len(delays)} "
        f"backoff delay(s) ({delays}) — one delay per retry, so these two must agree"
    )
    assert all(delay > 0 for delay in delays), f"a backoff delay must be positive: {delays}"
    assert delays == sorted(delays), f"backoff must not shrink between retries: {delays}"


def test_c_two_transport_failures_then_a_success_yield_the_turn(sleeps):
    """C.1: the turn survives a handshake timeout and returns the real action."""
    chat = _FakeChat([_transport_error(" #1"), _transport_error(" #2"), "ACTION1"])

    action = _turn(chat)

    assert action.id is GameAction.ACTION1, f"the turn must yield the SUCCESS, got {action!r}"
    assert len(chat.calls) == 3, (
        f"two failed attempts plus the one that worked is 3 chat calls; got {len(chat.calls)}"
    )
    assert sleeps == _backoff()[:2], (
        f"the two waits must be the module's own first two backoff delays {_backoff()[:2]}; "
        f"the turn waited {sleeps}"
    )


def test_c_a_retried_turn_is_charged_only_for_the_call_that_answered(sleeps):
    """A failed transport attempt returned no ChatResult, so there is nothing
    to charge for it. RENEGOTIABLE (implied by the contract, not stated)."""
    chat = _FakeChat([_transport_error(" #1"), _transport_error(" #2"), "ACTION1"])
    ledger = bat._Ledger(cap=LEDGER_CAP)

    _turn(chat, ledger)

    assert (ledger.tokens_in, ledger.tokens_out) == (1, 1), (
        "only the answering call carries usage, so the battery's token cap must see exactly "
        f"one charge; it saw {ledger.tokens_in}+{ledger.tokens_out}"
    )
    assert ledger.usd == [0.0], f"one charged call, one usd row; got {ledger.usd}"


def test_c_an_auth_failure_propagates_after_one_call(sleeps):
    """C.2: no key is not a transport problem — waiting cannot fix it."""
    # the trailing reply is what a WRONGLY retrying turn would take: it makes
    # the failure read "it retried", not "the fake ran out of script".
    chat = _FakeChat([_auth_error(), "ACTION1"])

    with pytest.raises(DriverError) as excinfo:
        _turn(chat)

    assert "401" in str(excinfo.value), f"the driver's own error must propagate: {excinfo.value}"
    assert len(chat.calls) == 1, (
        f"a 401 is retried zero times; the turn called chat {len(chat.calls)} time(s)"
    )
    assert sleeps == [], f"nothing is waited for on an auth failure; the turn slept {sleeps}"


def test_c_a_transport_failure_on_every_attempt_propagates_the_last_error(sleeps):
    """C.3: the retry is bounded, and what comes out is the FINAL failure."""
    attempts = _max_attempts()
    script = [_transport_error(f" #{index + 1}") for index in range(attempts)]
    chat = _FakeChat([*script, "ACTION1"])   # the reply one retry too many would take

    with pytest.raises(DriverError) as excinfo:
        _turn(chat)

    assert f"#{attempts}" in str(excinfo.value), (
        f"the error that propagates must be attempt {attempts}'s, not an earlier one; got "
        f"{excinfo.value}"
    )
    assert len(chat.calls) == attempts, (
        f"the module allows {attempts} transport attempt(s); the turn made {len(chat.calls)}"
    )
    assert sleeps == _backoff()[: attempts - 1], (
        f"one wait between each pair of attempts: expected {_backoff()[: attempts - 1]}, "
        f"the turn waited {sleeps}"
    )


def test_c_transport_retries_do_not_consume_the_protocol_retry(sleeps):
    """The two budgets are different contracts: B9 §3's `PROTOCOL_RETRIES` pays
    for a MALFORMED reply, the transport budget pays for a reply that never
    arrived. RENEGOTIABLE (implied by the contract, not stated)."""
    assert bat.PROTOCOL_RETRIES >= 1, (
        f"fixture drift: B9 §3 gives a turn one correction, PROTOCOL_RETRIES={bat.PROTOCOL_RETRIES}"
    )
    chat = _FakeChat([_transport_error(" #1"), _transport_error(" #2"), "nonsense", "ACTION1"])

    action = _turn(chat)

    assert action.id is GameAction.ACTION1
    assert len(chat.calls) == 4, (
        "the turn spent two transport retries and then its ONE protocol correction — a shared "
        f"counter would have given up; got {len(chat.calls)} call(s)"
    )
