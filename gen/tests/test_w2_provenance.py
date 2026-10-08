"""W2-C · R-21 — the frames provenance guard, pinned from the contract alone.

THE DEFECT the contract answers. facing-sentinel's `worker.frames.json` was
rendered by `worker.staged/game.py`, not by `worker/game.py` (timestamps
bracket it; `C_INK_DIM` 4 in the sidecar against 1 in the shipped source), so
the audit's single worst visual instance was evidence about code that never
shipped. Nothing in a sidecar records which source produced it, and nothing
downstream can tell a fresh capture from a stale one.

THE CONTRACT (wave 2, W2-C), the two behaviours these pins measure:

1. `gen/frames.py`: `FrameCapture` gains an OPTIONAL `source_sha256` — the
   sha256 of the game source file the capture imported, written by every
   capture path. OPTIONAL is load-bearing in both directions: a sidecar
   without the key loads exactly as today (the seven shipped games replay
   clean), and a capture that has no source file to hash adds nothing new to
   its JSON.
2. `gen/orchestrator.py`: at the s3_gate stage, a sidecar whose
   `source_sha256` is PRESENT and mismatches the current `worker/game.py`
   hash is REFUSED with a distinct reason ("frames provenance: sidecar
   rendered from a different source"); ABSENT is recorded as
   provenance:unrecorded in the gate artifacts and is never refused.

BLINDNESS. Written from the contract text alone, before one line of the
implementation was read. The pre-state consulted was `git show HEAD:
gen/frames.py` and `HEAD:gen/orchestrator.py` — what follows measures the
CONTRACT's behaviour, never the diff's. Pins 1-3 and 6 and 9-12 fail at HEAD;
4, 5, 7, 8 and 13 are the regression half (they must hold at HEAD and after).

RELATIVE, NOT ABSOLUTE, GATE VERDICTS. The shipped slot's own gate verdict is
read once and then used as the comparison point, so a sibling wave-2 lane that
legitimately changes what the gate says about a shipped game moves the
baseline and the tampered/matching runs with it. What is pinned is the
DIFFERENCE the provenance guard makes, which is the only thing this contract
owns.

WRITES. `tmp_path` only. `out/` is a READ-ONLY probe source: the shipped
conduit-watch slot is COPIED into tmp before anything runs it, and a
module-scoped guard re-reads the shipped bytes, sizes and mtimes on teardown,
so a stray write fails HERE rather than surfacing later as a dirty tree. No
API call, no network, no session: every capture below is the real engine over
a checked-in toy worker or a tmp copy of shipped code.

Run: .venv/bin/python -m pytest gen/tests/test_w2_provenance.py -v
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from gen import frames
from gen import orchestrator as orch
from gen.config import REPO_ROOT, load_config
from gen.orchestrator import SlotContext, default_runners

# --- what the contract names -------------------------------------------------

PROVENANCE_FIELD = "source_sha256"

# The reason the contract quotes for the refusal, kept whole for the failure
# messages. The assertions themselves match on WORDS (see `_names_provenance`)
# so that punctuation or a re-ordering of the sentence is not a false failure.
REFUSAL_REASON = "frames provenance: sidecar rendered from a different source"
UNRECORDED = "unrecorded"

# `FrameCapture`'s JSON keys BEFORE this contract. A capture with no source to
# hash must still serialize to exactly these (the wave's house rule: an
# unconfigured run is byte-identical to today's).
LEGACY_CAPTURE_KEYS = (
    "game_id",
    "source",
    "records",
    "click_cells",
    "available_action_ids",
    "solver_actions",
    "levels_completed",
    "win",
)

# --- fixtures on disk --------------------------------------------------------

TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"            # checked in: game.py + solver.py

# The shipped slot the contract names for the corpus regression. READ-ONLY:
# every use below copies it into tmp first.
SHIPPED_SLOT = REPO_ROOT / "out" / "corpus" / "b003r2-simplicity" / "conduit-watch"
SIDECAR_NAME = "worker.frames.json"
VERIFIER_REPORT_NAME = "worker.verifier-report.json"
WORKER_DIRNAME = "worker"
GAME_FILE = "game.py"

# `gate.visual_card: record` — the batch config the shipped slot was built
# under, i.e. a run in which the sidecar is demonstrably consumed at the gate.
CARD_CONFIG = "config/b003r2-simplicity.yaml"
# No `gate.visual_card` key at all: the canon default. The contract puts the
# refusal AT THE STAGE, not behind a card knob, so a mismatch must still stop.
DEFAULT_CONFIG = "config/b001-pilot.yaml"

# A well-formed sha256 that is no file's — the "rendered from a different
# source" case in its simplest honest form (the real incident's shape is a
# sidecar carrying the hash of a `worker.staged/game.py`).
BOGUS_SHA = "0" * 64

IGNORE_CACHES = shutil.ignore_patterns("__pycache__", ".pytest_cache")

# Invented names: they give the planted tree the shape the state machine walks
# and name nothing that has ever been sampled or run.
BATCH_ID = "b-w2c-fixture"
SLOT_SLUG = f"{BATCH_ID}-s001"

needs_shipped = pytest.mark.skipif(
    not (SHIPPED_SLOT / SIDECAR_NAME).is_file(),
    reason=(
        f"{SHIPPED_SLOT}/{SIDECAR_NAME} is absent — out/ is the gitignored live-run tree, so "
        "the shipped-corpus regression has nothing to read on this checkout"
    ),
)


# --- helpers -----------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fingerprint(path: Path) -> tuple:
    stat = path.stat()
    return (_sha256_file(path), stat.st_size, stat.st_mtime_ns)


def _copy_toy_worker(dest: Path) -> Path:
    """The checked-in toy worker, in tmp, ready to be captured."""
    shutil.copytree(TOY_WORKER, dest, ignore=IGNORE_CACHES)
    return dest


def _provenance_of(cap: object) -> object:
    """`cap.source_sha256`, or a failure naming the field the contract adds."""
    if not hasattr(cap, PROVENANCE_FIELD):
        pytest.fail(
            f"{type(cap).__name__} has no {PROVENANCE_FIELD!r}. W2-C part 1: "
            f"'FrameCapture gains OPTIONAL source_sha256 (sha256 of the game source file the "
            f"capture imported)'. Without it nothing records what source a sidecar came from, "
            f"which is the whole R-21 defect. Fields present: {sorted(vars(cap))}"
        )
    return getattr(cap, PROVENANCE_FIELD)


def _carries(value: object, digest: str) -> bool:
    """Does a recorded provenance value carry `digest`?

    The bare hexdigest is the reading; a `sha256:`-style prefix is tolerated
    rather than treated as a defect, because the contract pins the HASH, not
    its spelling.
    """
    return isinstance(value, str) and digest in value


def _note_text(value: object) -> str:
    """An artifact's note as text — including the file's own words if it is one."""
    text = str(value)
    try:
        path = Path(text)
        if path.is_file() and path.stat().st_size <= 64_000:
            text = f"{text}\n{path.read_text(encoding='utf-8', errors='replace')}"
    except (OSError, ValueError):  # a note is not required to be path-shaped
        pass
    return text


def _provenance_notes(result: dict) -> dict[str, str]:
    """Gate artifacts that say something about provenance, key -> note text."""
    notes: dict[str, str] = {}
    for key, value in result["artifacts"].items():
        text = _note_text(value)
        if "provenance" in str(key).lower() or "provenance" in text.lower():
            notes[str(key)] = text
    return notes


def _names_provenance(text: str) -> bool:
    """Word-level test for the contract's distinct refusal reason."""
    words = set(re.findall(r"[a-z0-9]+", str(text).lower()))
    return "provenance" in words and bool(words & {"frames", "frame", "sidecar"})


def _plant_slot(root: Path, cfg: dict, *, provenance: str | None) -> SimpleNamespace:
    """A §2 slot at `verified`, built from a COPY of the shipped conduit slot.

    `corpus/<batch>/<slug>/{spec.yaml,spec.md,worker/}` plus the two siblings
    the gate reads: S2b's verifier report and S2b's frames sidecar. Only the
    sidecar's provenance field is varied:

    * `provenance=None`   — the file exactly as shipped (the key is absent).
    * `provenance="MATCH"` — the key set to the sha256 of THIS copy's
      `worker/game.py`, i.e. an honest fresh capture.
    * anything else       — the key set to that literal digest (a mismatch).
    """
    corpus_dir = root / "corpus" / BATCH_ID
    spec_dir = corpus_dir / SHIPPED_SLOT.name
    spec_dir.mkdir(parents=True)
    for name in ("spec.yaml", "spec.md", SIDECAR_NAME, VERIFIER_REPORT_NAME):
        shutil.copy2(SHIPPED_SLOT / name, spec_dir / name)
    worker = spec_dir / WORKER_DIRNAME
    shutil.copytree(SHIPPED_SLOT / WORKER_DIRNAME, worker, ignore=IGNORE_CACHES)

    sidecar = spec_dir / SIDECAR_NAME
    if provenance is not None:
        digest = _sha256_file(worker / GAME_FILE) if provenance == "MATCH" else provenance
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        payload[PROVENANCE_FIELD] = digest
        sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    ideas_dir = root / "ideas" / BATCH_ID
    ideas_dir.mkdir(parents=True)
    ctx = SlotContext(
        cfg=cfg,
        batch_id=BATCH_ID,
        slug=SLOT_SLUG,
        index=1,
        state="verified",
        stage="s3_gate",
        attempt=1,
        batch_dir=root / "batch",
        ideas_dir=ideas_dir,
        idea_path=ideas_dir / "idea-001.json",
        corpus_dir=corpus_dir,
        spec_dir=spec_dir,
        respec_count=0,
        verifier_rejects=0,
        green_failures=0,
    )
    assert ctx.verifier_report_path is not None and ctx.verifier_report_path.is_file(), (
        "fixture: the gate's S2b input must resolve to the copied report"
    )
    return SimpleNamespace(spec_dir=spec_dir, worker=worker, sidecar=sidecar, ctx=ctx)


def _run_gate(root: Path, cfg: dict, *, provenance: str | None) -> SimpleNamespace:
    """Plant a slot, run the real s3_gate runner over it, keep everything."""
    slot = _plant_slot(root, cfg, provenance=provenance)
    before = slot.sidecar.read_bytes()
    result: dict | None = None
    error: BaseException | None = None
    try:
        result = default_runners()["s3_gate"](slot.ctx)
    except BaseException as exc:  # noqa: BLE001 — how a stage fails is itself a pin
        error = exc
    return SimpleNamespace(
        slot=slot,
        result=result,
        error=error,
        sidecar_before=before,
        sidecar_after=slot.sidecar.read_bytes(),
    )


def _result_of(run: SimpleNamespace, what: str) -> dict:
    """The stage result, or a failure saying a refusal must be a ROUTED reject."""
    if run.result is None:
        pytest.fail(
            f"the s3_gate runner raised {type(run.error).__name__}: {run.error} on the "
            f"{what} sidecar. W2-C wants this REFUSED — the orchestrator routes a slot on a "
            f"stage RESULT ({{ok, to_state, reason}}), and an exception out of a runner is not "
            f"a refusal: it appends no ledger line and takes the whole batch down with it. "
            f"(If a raise is the deliberate reading, this is one for the lead to adjudicate.)"
        )
    return run.result


# --- module fixtures ---------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def shipped_tree_untouched():
    """out/ is READ-ONLY. Proven, not asserted in prose."""
    probes = [SHIPPED_SLOT / SIDECAR_NAME, SHIPPED_SLOT / WORKER_DIRNAME / GAME_FILE]
    before = {path: _fingerprint(path) for path in probes if path.is_file()}
    yield
    after = {path: _fingerprint(path) for path in before}
    moved = [str(path) for path in before if before[path] != after[path]]
    assert not moved, (
        f"the shipped corpus was modified by this test module: {moved}. out/ is a read-only "
        "probe source — every use copies it to tmp first"
    )


@pytest.fixture(scope="module")
def card_cfg() -> dict:
    return load_config(CARD_CONFIG)


@pytest.fixture(scope="module")
def default_cfg() -> dict:
    return load_config(DEFAULT_CONFIG)


@pytest.fixture(scope="module")
def as_shipped(tmp_path_factory, card_cfg) -> SimpleNamespace:
    """The shipped sidecar, untouched: no provenance field at all."""
    return _run_gate(tmp_path_factory.mktemp("as-shipped"), card_cfg, provenance=None)


@pytest.fixture(scope="module")
def mismatched(tmp_path_factory, card_cfg) -> SimpleNamespace:
    """The R-21 incident: a sidecar rendered from some other source."""
    return _run_gate(tmp_path_factory.mktemp("mismatched"), card_cfg, provenance=BOGUS_SHA)


@pytest.fixture(scope="module")
def matched(tmp_path_factory, card_cfg) -> SimpleNamespace:
    """An honest fresh capture: the field names this slot's own game.py."""
    return _run_gate(tmp_path_factory.mktemp("matched"), card_cfg, provenance="MATCH")


@pytest.fixture(scope="module")
def mismatched_unconfigured(tmp_path_factory, default_cfg) -> SimpleNamespace:
    """The same mismatch under a config that declares no visual-card knob."""
    return _run_gate(
        tmp_path_factory.mktemp("mismatched-default"), default_cfg, provenance=BOGUS_SHA
    )


# =============================================================================
# PART 1 — the capture writes its provenance (contract part 1; BLIND pin 1)
# =============================================================================


def test_1_a_fresh_capture_records_the_source_hash(tmp_path):
    """Pin 1. A capture taken through the in-process worker seam records
    `source_sha256` = sha256 of the `game.py` it imported."""
    worker = _copy_toy_worker(tmp_path / "worker")
    expected = _sha256_file(worker / GAME_FILE)

    cap = frames.capture_worker(worker)

    recorded = _provenance_of(cap)
    assert _carries(recorded, expected), (
        f"capture_worker({worker.name}) recorded {PROVENANCE_FIELD}={recorded!r}; the contract "
        f"wants the sha256 of the game source the capture imported, which is {expected} for "
        f"{worker / GAME_FILE}. (The hash is of game.py — 'the current worker/game.py hash' is "
        "what the gate-side comparison is written against.)"
    )


def test_2_the_isolated_capture_records_it_too(tmp_path):
    """Pin 1, the other writer. `capture_worker_isolated` is the seam the gate
    and S2b actually use, and it crosses JSON in both directions — so this also
    proves the field survives `capture_to_json` -> child -> `capture_from_json`."""
    worker = _copy_toy_worker(tmp_path / "worker")
    expected = _sha256_file(worker / GAME_FILE)

    cap = frames.capture_worker_isolated(worker)

    recorded = _provenance_of(cap)
    assert _carries(recorded, expected), (
        f"capture_worker_isolated recorded {PROVENANCE_FIELD}={recorded!r}, expected the sha256 "
        f"of {worker / GAME_FILE} ({expected}). The contract says EVERY writer records it, and "
        "this is the writer whose output becomes worker.frames.json — if it is the one that "
        "forgets, every real sidecar stays unattributable. A None here that the in-process leg "
        "fills also means the field did not survive the child's JSON round trip."
    )


def test_3_the_hash_identifies_the_source_bytes(tmp_path):
    """Pin 1, sharpened: the field tracks the FILE, not a constant. Two copies
    of one worker whose game.py differs by a byte must record different
    hashes — otherwise the gate-side comparison can never fire."""
    first = _copy_toy_worker(tmp_path / "first")
    second = _copy_toy_worker(tmp_path / "second")
    game = second / GAME_FILE
    # A comment: the module still loads and still plays the same game, so the
    # only thing that moved is the bytes the provenance field is about.
    game.write_text(game.read_text(encoding="utf-8") + "\n# W2-C blind pin: edited source\n",
                    encoding="utf-8")

    one = _provenance_of(frames.capture_worker(first))
    two = _provenance_of(frames.capture_worker(second))

    assert _carries(one, _sha256_file(first / GAME_FILE)), (
        f"first copy recorded {one!r}, expected sha256 {_sha256_file(first / GAME_FILE)}"
    )
    assert _carries(two, _sha256_file(second / GAME_FILE)), (
        f"edited copy recorded {two!r}, expected sha256 {_sha256_file(second / GAME_FILE)}"
    )
    assert one != two, (
        f"both copies recorded {one!r} although their game.py files differ. A provenance field "
        "that does not move with the source cannot distinguish a fresh capture from one rendered "
        "by a staged build, which is the defect R-21 exists to catch"
    )


def test_4_a_capture_with_no_source_file_adds_nothing_new(tmp_path):
    """Pin 1's optional half + the wave house rule. `capture(game_cls, ...)`
    imported no FILE, so there is nothing to hash: the field is None and the
    JSON carries exactly the keys it carried before this contract."""
    from gen.s3_verify import load_worker_classes

    worker = _copy_toy_worker(tmp_path / "worker")
    game_cls, solver_cls = load_worker_classes(worker)

    cap = frames.capture(game_cls, solver_cls)
    payload = frames.capture_to_json(cap)

    assert getattr(cap, PROVENANCE_FIELD, None) is None, (
        f"a class-level capture recorded {getattr(cap, PROVENANCE_FIELD, None)!r}. It was handed "
        "a CLASS, not a path: inventing a hash here would make provenance a guess"
    )
    assert tuple(payload) == LEGACY_CAPTURE_KEYS, (
        f"capture_to_json wrote keys {tuple(payload)} for a capture with no recorded source. "
        f"The contract's OPTIONAL is two-sided — 'old files simply lack it' — and the wave's "
        f"house rule is that an unconfigured run is byte-identical to today's, so the absent "
        f"case must serialize to exactly {LEGACY_CAPTURE_KEYS}"
    )


# =============================================================================
# PART 2 — the JSON seam stays readable both ways (contract part 1; BLIND pin 2a)
# =============================================================================


def _legacy_payload(tmp_path: Path) -> dict:
    """A real capture's JSON with any provenance field removed — an old sidecar."""
    worker = _copy_toy_worker(tmp_path / "legacy-worker")
    payload = frames.capture_to_json(frames.capture_worker(worker))
    payload.pop(PROVENANCE_FIELD, None)
    return payload


def test_5_an_old_sidecar_loads_and_round_trips_byte_identical(tmp_path):
    """Pin 2. A sidecar written before this contract has no `source_sha256`.
    It must load exactly as today and come back out byte-for-byte — this is the
    seven shipped games' replay, in miniature."""
    payload = _legacy_payload(tmp_path)
    text = json.dumps(payload, indent=2) + "\n"

    cap = frames.capture_from_json(json.loads(text))

    assert getattr(cap, PROVENANCE_FIELD, None) is None, (
        f"an old sidecar loaded with {PROVENANCE_FIELD}="
        f"{getattr(cap, PROVENANCE_FIELD, None)!r}. A file that recorded nothing must read as "
        "recording nothing — a default standing in for a hash would let an unattributable "
        "capture pass the gate-side comparison"
    )
    assert json.dumps(frames.capture_to_json(cap), indent=2) + "\n" == text, (
        "an old sidecar did not round-trip byte-identically. Readers never require the new "
        "field, and a rewrite must not invent one"
    )


def test_6_a_sidecar_carrying_the_field_loads_and_round_trips(tmp_path):
    """Pin 2's other side: the reader must ACCEPT the new key (at HEAD the
    round-trip guard rejects it as an unexpected key) and preserve it."""
    payload = _legacy_payload(tmp_path)
    payload[PROVENANCE_FIELD] = BOGUS_SHA
    text = json.dumps(payload, indent=2) + "\n"

    cap = frames.capture_from_json(json.loads(text))

    assert _carries(_provenance_of(cap), BOGUS_SHA), (
        f"a sidecar carrying {PROVENANCE_FIELD}={BOGUS_SHA} loaded as "
        f"{_provenance_of(cap)!r}. The gate refuses on what the FILE says; a reader that drops "
        "the field silently disarms the guard"
    )
    assert json.dumps(frames.capture_to_json(cap), indent=2) + "\n" == text, (
        "a sidecar carrying the provenance field did not round-trip byte-identically; the "
        "capture JSON is the one artifact every downstream leg argues over"
    )


def test_7_unknown_keys_are_still_rejected(tmp_path):
    """The fail-loud round-trip guard is relaxed for ONE named key, not in
    general: a sidecar carrying some other field is still a loud error."""
    payload = _legacy_payload(tmp_path)
    payload["rendered_by"] = "worker.staged/game.py"

    with pytest.raises((ValueError, TypeError)) as caught:
        frames.capture_from_json(payload)

    assert "rendered_by" in str(caught.value), (
        f"the rejection did not name the offending key: {caught.value}. Widening the reader to "
        f"accept {PROVENANCE_FIELD} must not widen it to accept anything"
    )


# =============================================================================
# PART 3 — the gate seam (contract part 2; BLIND pins 2b, 3, 4)
# =============================================================================


@needs_shipped
def test_8_an_absent_field_is_recorded_unrecorded_and_never_refused(as_shipped):
    """Pin 2b. The shipped sidecar records no source. The gate must say so —
    `provenance: unrecorded` in the gate artifacts — and must NOT refuse: six
    of the seven shipped games would otherwise stop dead at the gate."""
    result = _result_of(as_shipped, "as-shipped")

    assert not _names_provenance(result["reason"]), (
        f"a sidecar with no {PROVENANCE_FIELD} was refused: {result['reason']!r}. The contract "
        "is explicit — 'absent = recorded as provenance:unrecorded ... never refused'"
    )
    notes = _provenance_notes(result)
    assert notes, (
        f"the gate reported nothing about provenance for a sidecar that records none. Artifacts "
        f"were {sorted(result['artifacts'])}; the contract wants the absence RECORDED as "
        f"provenance:{UNRECORDED} in the gate artifacts, because 'nothing records what source a "
        "sidecar came from' is the finding this contract answers"
    )
    assert any(UNRECORDED in text.lower() for text in notes.values()), (
        f"the gate's provenance note(s) {notes} do not say {UNRECORDED!r} — an absence recorded "
        "in words nobody can grep for is not a record"
    )
    orch._check_artifacts("s3_gate", result)  # a note is not a path: it must be exempted


@needs_shipped
def test_9_a_mismatched_sidecar_is_refused_with_the_distinct_reason(mismatched):
    """Pin 3. A sidecar whose recorded source is not this worker's game.py is
    the facing-sentinel incident exactly. It must be REFUSED, and the reason
    must name the rule rather than hide inside a generic gate verdict."""
    result = _result_of(mismatched, "mismatched")

    assert result["ok"] is False, (
        f"a sidecar recording a source that is not this slot's game.py came back ok="
        f"{result['ok']!r} to_state={result['to_state']!r} reason={result['reason']!r}. W2-C: "
        f"such a sidecar 'is REFUSED with a distinct reason ({REFUSAL_REASON!r})'"
    )
    assert _names_provenance(result["reason"]), (
        f"the refusal reason is {result['reason']!r}, which names neither provenance nor the "
        f"sidecar. The contract asks for a DISTINCT reason — {REFUSAL_REASON!r} — so the run log "
        "says why the slot stopped and the next reader is not left re-deriving it"
    )


@needs_shipped
def test_10_the_refusal_is_a_stop_not_a_silent_note(mismatched):
    """Pin 4. The difference between this and `unrecorded`: a mismatch does not
    merely annotate the run, it ends it. The slot must not advance, and the
    reason the ledger records must be the provenance one."""
    result = _result_of(mismatched, "mismatched")

    orch._check_result("s3_gate", result)  # a refusal still has to be a routable result
    assert result["to_state"] != "gated", (
        f"the mismatched run still advanced the slot to {result['to_state']!r}. A stale sidecar "
        "that reaches `gated` is exactly the audit's failure: the visual evidence downstream "
        "belongs to code that was never shipped"
    )
    assert result["to_state"] not in ("baselined", "played", "reviewed", "packaged"), (
        f"the mismatched run routed forward to {result['to_state']!r}"
    )
    assert _names_provenance(result["reason"]), (
        f"the stage's REASON is {result['reason']!r}; the provenance failure must be the routing "
        "signal itself, not a side note left in the artifacts while the run reports something "
        f"else. Provenance-bearing artifacts on this run: {_provenance_notes(result)}"
    )
    assert UNRECORDED not in result["reason"].lower(), (
        f"the refusal reason {result['reason']!r} calls the mismatch {UNRECORDED!r}; the two "
        "cases are different verdicts and must read differently"
    )


@needs_shipped
def test_11_a_matching_sidecar_flows_through_clean(matched, as_shipped):
    """Pin 3's other half: match = clean. A sidecar that honestly records this
    worker's game.py must behave exactly as the same sidecar without the field
    — same verdict, same reason, no new error artifact, no refusal."""
    result = _result_of(matched, "matching")
    baseline = _result_of(as_shipped, "as-shipped")

    assert not _names_provenance(result["reason"]), (
        f"a sidecar whose {PROVENANCE_FIELD} equals sha256(worker/game.py) was refused: "
        f"{result['reason']!r}. Only a MISMATCH is a refusal"
    )
    assert (result["ok"], result["to_state"], result["reason"]) == (
        baseline["ok"], baseline["to_state"], baseline["reason"]
    ), (
        f"recording an honest provenance changed the gate's own verdict: matching run "
        f"{(result['ok'], result['to_state'], result['reason'])} vs the same slot with no field "
        f"{(baseline['ok'], baseline['to_state'], baseline['reason'])}"
    )
    new_errors = {
        key: value for key, value in result["artifacts"].items()
        if "error" in str(key).lower() and key not in baseline["artifacts"]
    }
    assert not new_errors, (
        f"the matching sidecar produced new error artifact(s) {new_errors}. A seam that reads "
        f"worker.frames.json must ACCEPT the field this contract writes into it — a card or "
        "check that now fails on a well-formed sidecar is the regression"
    )
    notes = _provenance_notes(result)
    assert not any(UNRECORDED in text.lower() for text in notes.values()), (
        f"a recorded, matching provenance was reported as {UNRECORDED!r}: {notes}"
    )


@needs_shipped
def test_12_the_refusal_does_not_depend_on_the_visual_card_knob(mismatched_unconfigured):
    """Pin 3, unconfigured. The contract puts the refusal at the s3_gate STAGE
    and mints no knob for it. A batch that never asks for a visual card must
    still stop on a sidecar that came from another source — otherwise the guard
    is armed only where someone happened to switch a report on."""
    result = _result_of(mismatched_unconfigured, "mismatched (no card knob)")

    assert result["ok"] is False and _names_provenance(result["reason"]), (
        f"under {DEFAULT_CONFIG} (no gate.visual_card key, canon default) a mismatched sidecar "
        f"came back ok={result['ok']!r} reason={result['reason']!r}. The guard is a RULING at "
        "the stage, not a property of the card: no knob was minted for it"
    )


@needs_shipped
def test_13_the_shipped_conduit_sidecar_passes_the_seam_untouched(as_shipped):
    """Pin 5, the corpus regression. conduit-watch is a PACKAGED game: its
    sidecar predates this contract, and the gate must read it, record the
    absence, and leave the file exactly as it found it."""
    result = _result_of(as_shipped, "as-shipped")
    payload = json.loads(as_shipped.slot.sidecar.read_text(encoding="utf-8"))

    assert as_shipped.sidecar_after == as_shipped.sidecar_before, (
        "the gate rewrote the shipped sidecar it was only asked to read. A guard that edits the "
        "evidence it checks destroys the thing it is guarding"
    )
    assert PROVENANCE_FIELD not in payload, (
        f"the gate back-filled {PROVENANCE_FIELD} into a shipped sidecar. An unrecorded source "
        "stays unrecorded: a hash written now would claim a capture was taken from a file it was "
        "never taken from — the R-21 defect, manufactured"
    )
    assert not _names_provenance(result["reason"]), (
        f"the shipped conduit-watch slot was refused on provenance grounds: {result['reason']!r}. "
        "The seven shipped games carry no provenance field and must replay clean"
    )
