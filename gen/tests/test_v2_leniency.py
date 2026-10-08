"""BLIND LANE for frozen contract L-1 — deception findings become record-only.

Run: .venv/bin/python -m pytest gen/tests/test_v2_leniency.py -q

WRITTEN FROM THE CONTRACT ALONE
(`docs/v2/contracts/L-1-deception-record-only.md`, including Addendum 1).
The implementer's own suite, `gen/tests/test_l1_leniency.py`, was NOT read and
neither was their handback.  `gen/s3_verify.py`, `gen/orchestrator.py`,
`gen/cli.py` and `config/template.yaml` were read ONLY for names and call
shapes — every expectation below cites the contract sentence it pins, and the
assertion messages carry that sentence so a red test is fixable from the
failure alone.

THE PINS, contract section by contract section:

  §Blind L1  default = today's bytes ............. group B
  §Blind L2  record mode ......................... group C
  §Blind L3  mixed findings ...................... group D
  §Blind L4  validation .......................... group A
  §Blind L5  the overlay ......................... group E
  §Blind L6  the t1 trap, end to end ............. group F
  §Work 3    VISIBILITY .......................... group F (the stop print)
  §Work 5    SCOPE GUARDS ........................ group G
  Addendum 1 D2 (no moved key) ................... group E
  Addendum 1 D3 (no b7.1 bump; OPTIONAL in validation) ... group C

HOW L6 IS DRIVEN, and why (the contract leaves the choice open: "Drive it
through the orchestrator's fake-runner pattern … OR through the verifier's own
assemble/decide functions if a full-slot drive is disproportionate — your call,
state it").  THE CALL: BOTH, because the trap is a sentence about two different
machines and neither half proves it alone.

  * The verifier half is driven through the REAL `assemble_report` on a planted
    worker (the `test_b003_corrwindow` harness shape), so the reports in group F
    are not hand-written fixtures — they are what the stage really writes for a
    lever-only audit under each knob value.
  * The orchestrator half is a FULL SLOT through `orch.run_batch` on the
    borrowed b005/b11 fake-runner rig, with those REAL reports planted as the
    S2b artifact and the fake stage's ok/to_state DERIVED from the report's own
    verdict (`gen/s3_verify.py::main` exits 0 on `pass` and 2 otherwise, so the
    stage's success IS the report's verdict; the rig cannot read a report, so
    the bridge is made explicit here rather than assumed).
  * The TRAP ITSELF — "an `undeclared-deception` sighting at t1 can neither be
    declared … nor repaired game-side" — is additionally pinned at the one
    function the contract's evidence section names,
    `orchestrator._reconcile_declarations`, on a planted t1 slot.

AMBIGUITIES RESOLVED (reported, not papered over):

  a. "loud at CONFIG LOAD" (§Work 1 / §Blind L4).  `gen/config.load_config` and
     the `s0_ideas.check_config` preflight validate NO `verifier.*` knob — every
     one of them (`exempt_terms`, `lever_corroboration`, `round_cap` …) is read
     and validated at READ time inside its own stage.  The contract's own words
     are "loud at config load, BESIDE THE OTHER VERIFIER KNOBS", so "beside the
     other verifier knobs" is taken as decisive and group A pins the read-time
     idiom — plus the thing that makes it equivalent in practice: a bad value
     stops the stage BEFORE it writes anything, on a full run and on a dry run.
  b. L5's "the overlay diff pin count grows by exactly one key".  Addendum 1
     ratifies this as the AUTONOMY_OVERLAY's own key count 6 -> 7, NOT a new
     moved key in the materialization diff (the template arms `record` too, so
     the overlay changes nothing about that file's value).  Group E pins both
     halves of that ruling — the 7th overlay key, and the EMPTY move.
  c. L6's "every audit round sights a lever" is driven with the corroboration
     bar on its CANON DEFAULT (off), so every round's sighting survives to the
     append site.  The contract puts the corroboration machinery upstream and
     explicitly out of scope ("leave it untouched"), so arming it here would
     measure that contract instead of this one.
  d. §Work 3's "they print … wherever reject_reasons print today" has two
     print sites (the S3 CLI's own line, and the orchestrator's stop).  The
     orchestrator stop is driven for real through `orch.main`; the S3 CLI's
     line needs a real verify run (an agent session and a live worker) and is
     NOT driven here — group F says so out loud instead of skipping silently.

OPERATIONAL NOTE.  A LIVE batch is writing under the repo's `out/` while this
file runs, so the house `_repo_batches_untouched` snapshot guard is deliberately
NOT re-bound: a snapshot diff would race the live ledger and go red on somebody
else's work.  `_repo_is_never_written` below asks the stronger, race-free
question instead.  Hermetic otherwise: tmp roots, no network, no drivers, no
subprocess, nothing written under `out/`.
"""

from __future__ import annotations

import copy
import inspect
import json
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

from gen import cli
from gen import orchestrator as orch
from gen import s3_verify as s3v
from gen import s6_package as s6
from gen.config import load_config

# The rigs, imported and called through their owner's alias (the
# test_b005_autonomy precedent: borrowed, never copied, never modified).
from gen.tests import test_b005_autonomy as b005
from gen.tests import test_b11_pipeline as b11

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"
REAL_TEMPLATE = REPO_ROOT / "config" / "template.yaml"
B005R2_CONFIG = REPO_ROOT / "config" / "b005r2-auto.yaml"

#: A real config, used ONLY as a base: it supplies `duckwm_docs` and the run
#: metadata `assemble_report` reads.  Every `verifier:` key this file depends on
#: is set explicitly by `_cfg` below, so nothing here rides on what the file
#: happens to carry.
BASE_CONFIG = "config/b001-pilot.yaml"

# --- the contract's own vocabulary, not the code's --------------------------
#: §Work 1: "KNOB: `verifier.deception_action`, values `"reject"` … | `"record"`".
KNOB = "deception_action"
#: Overlay keys contracts AFTER L-1 added, subtracted by name from L5's
#: key-count pin so it keeps measuring L-1's own 6 -> 7 delta. Contract E-2
#: (2026-10-05) is the first entry: the park-the-treadmill and
#: skip-the-futile-respec armings.
#:
#: PIN UPDATE, 2026-10-06 (contract Q-1 §4, a licensed overlay-pin edit, the
#: E-2 idiom). `verifier.term_dispute_action` is this knob's own ruling one
#: finding class over — a DISPUTED `undeclared-term` finding rides the report
#: instead of the verdict — and it was written after b005r2 ran, exactly like
#: the two above. L5's claim is L-1's 6 -> 7 delta, so the key is subtracted by
#: name and the count is not bumped.
LATER_CONTRACT_OVERLAY_KEYS = frozenset({
    "orchestrator.stage_fail_park",
    "orchestrator.respec_feasibility",
    "verifier.term_dispute_action",
})
ACTION_REJECT = "reject"
ACTION_RECORD = "record"
#: §Work 2: "a NEW report list `deception_advisories`".
ADVISORIES = "deception_advisories"
#: §Evidence: "REJECT_UNDECLARED_DECEPTION :194".
LEVER_CODE = "undeclared-deception"
TERM_CODE = "undeclared-term"
DEAD_TERM_CODE = "dead-spec-term"
VERDICT_PASS, VERDICT_REJECT = "pass", "reject"
MODE_FULL = "full"
#: §Work 3 / Addendum 1 D5: the stop line's own words.
STOP_PHRASE = "deception advisories (recorded, not rejecting)"
#: Addendum 1 D3: "NO b7.1 bump".
SCHEMA = "b7.1"

#: Three catalog levers (the live exhibit's own: seamlock sighted 3, and
#: key-strip-rover sighted `camouflage`).
#: PIN UPDATE, contract E-1 (2026-10-05): A was `"camouflage"` and C `"mimic"`.
#: The re-grounded catalog reads both as SPELLINGS — camouflage folds onto §7.2's
#: `palette overload` and mimic onto §7.1's `look-alike` — so neither is a
#: catalog keyword of its own any more. A and C are the LEVERS those sightings
#: were always naming, which keeps the live exhibit's reading intact (the
#: rover's `camouflage` round IS a palette-overload round) and keeps the three
#: distinct, which is what the advisory pins need.
LEVER_A = "palette overload"
LEVER_B = "decoy"
LEVER_C = "look-alike"
#: A vocabulary term the spec will not declare — L3's "1 undeclared term".
STRAY_TERM = "goal.cover"
SPEC_TERM = "move.grid"

GAME_ID = "l1-blind-synthetic"
SYNTHETIC = "synthetic fixture"

#: Every batch id this file allocates, so the repo guard can ask for them BY
#: NAME instead of diffing a root the live batch is writing into.
BATCH_IDS = (
    "l1blind-trap-reject",
    "l1blind-trap-record",
    "l1blind-stop-print",
)

_ABSENT = object()


# --------------------------------------------------------------------------- #
# guards
# --------------------------------------------------------------------------- #

_no_network_no_agent = b11._no_network_no_agent  # autouse: no urlopen, no driver
batch_home = b11.batch_home
make_cfg = b11.make_cfg


@pytest.fixture(autouse=True)
def _repo_is_never_written():
    """Nothing this file names may appear in the repo's own roots.

    Hard rule: "never write under out/ (a LIVE batch is running there)".  The
    house guard snapshots `out/batches/` and diffs it, which would race that
    batch; this asks the race-free question — the ids and the template are mine
    to account for, and the live batch's files are not.
    """
    template_before = REAL_TEMPLATE.read_bytes()
    yield
    assert REAL_TEMPLATE.read_bytes() == template_before, (
        "a test in this file rewrote config/template.yaml; the blind lane touches "
        "exactly one file (L-1 §Hard rules)"
    )
    for batch_id in BATCH_IDS:
        for root in (REPO_ROOT / "out" / "batches", REPO_ROOT / "out" / "corpus",
                     REPO_ROOT / "config"):
            stray = sorted(root.glob(f"{batch_id}*")) if root.is_dir() else []
            assert not stray, (
                f"a test wrote {stray} into the repo's own {root} — L-1 §Hard rules: "
                "'never write under out/ (a LIVE batch is running there)'"
            )


@pytest.fixture(autouse=True)
def _play_root_is_tmp(tmp_path, monkeypatch):
    """The packaged-game mirror points at tmp for every test in this file."""
    monkeypatch.setattr(s6, "PLAY_ROOT", tmp_path / "play")


# --------------------------------------------------------------------------- #
# the verifier harness: synthetic audit rounds through the REAL assemble_report
# (house style: the test_b003_corrwindow `_Slot`, unchanged in shape)
# --------------------------------------------------------------------------- #


def _cfg(base: Mapping, action: object = _ABSENT) -> dict:
    """A run config whose `verifier:` block holds the L-1 knob AND NOTHING ELSE.

    The block is replaced wholesale rather than edited, so no expectation here
    depends on what `BASE_CONFIG` arms — in particular the corroboration bar
    stays on its canon default (ambiguity c).
    """
    cfg = copy.deepcopy(dict(base))
    cfg["verifier"] = {} if action is _ABSENT else {KNOB: action}
    return cfg


def _evidence() -> list[dict]:
    return [{"path": "game.py", "line": 10, "note": SYNTHETIC}]


def _claims(levers: tuple[str, ...] = (), extra_terms: tuple[str, ...] = ()) -> dict:
    """What the blind audit reported this round."""
    terms = [SPEC_TERM, *extra_terms]
    return {
        "terms": [
            {"term": term, "reachable": True, "evidence": _evidence()} for term in terms
        ],
        "dead_code": [],
        "deceptions": [{"lever": lever, "evidence": _evidence()} for lever in levers],
        "enforcement": [],
        "notes": SYNTHETIC,
    }


def _spec() -> dict:
    """A spec declaring one term and ZERO levers — the t1 shape of the exhibit."""
    return {"game": {"terms": [SPEC_TERM], "knobs": {"deceptions": []}}}


class _Round:
    """One planted slot, driven through as many FULL verify rounds as a test wants.

    Every report is the real `assemble_report` output: the knob is read from the
    cfg handed to `run`, and the diff comes off the pure `compute_diff` path, so
    a diff bug and a verdict bug stay distinguishable.
    """

    def __init__(self, root: Path, cap: object) -> None:
        self.root = root
        self.worker = root / "slot-1"
        shutil.copytree(TOY_WORKER, self.worker, ignore=shutil.ignore_patterns("__pycache__"))
        self.frames_path = root / s3v.FRAMES_NAME
        self.frames_path.write_text("{}", encoding="utf-8")
        self._cap = cap
        self.rounds = 0

    def diff(self, *, levers: tuple[str, ...] = (), extra_terms: tuple[str, ...] = ()) -> dict:
        return s3v.compute_diff(_claims(levers, extra_terms), _spec())

    def run(self, cfg: Mapping, *, levers: tuple[str, ...] = (),
            extra_terms: tuple[str, ...] = (), diff: object = _ABSENT) -> dict:
        self.rounds += 1
        claims = _claims(levers, extra_terms)
        agent = {
            "session_id": f"synthetic-{self.rounds}",
            "model": "synthetic",
            "usd": 0.0,
            "tokens_in": 1,
            "tokens_out": 1,
            "wall_s": 0.0,
            "staged_copy_verified": True,
            "claims": claims,
        }
        return s3v.assemble_report(
            game_id=GAME_ID,
            worker=self.worker,
            mode=MODE_FULL,
            cfg=dict(cfg),
            cap=self._cap,
            checks=[],
            frames_path=self.frames_path,
            agent=agent,
            diff=(s3v.compute_diff(claims, _spec()) if diff is _ABSENT else diff),
            spec_hash=None,
        )


@pytest.fixture(scope="session")
def cap() -> object:
    """A real FrameCapture off the checked-in toy worker (b7-style staging)."""
    game_cls, solver_cls = s3v.load_worker_classes(TOY_WORKER)
    return s3v.capture(game_cls, solver_cls)


@pytest.fixture(scope="session")
def base_cfg() -> dict:
    cfg = load_config(BASE_CONFIG)
    for lever in (LEVER_A, LEVER_B, LEVER_C):
        assert lever in s3v.DECEPTION_CATALOG, (
            f"fixture wall: {lever!r} left the signed deception catalog; L-1 is about "
            "levers the blind audit can name"
        )
    return cfg


@pytest.fixture
def slot(tmp_path: Path, cap: object) -> _Round:
    return _Round(tmp_path / "verify", cap)


def _codes(rows) -> list[str]:
    return [str(row.get("code")) for row in rows]


def _levers(rows) -> list[str]:
    return [str(row.get("lever")) for row in rows]


def _reader():
    """`_deception_action(cfg)` — the knob's reader, by name then by search.

    §Work 1 says the knob is read "beside the other verifier knobs" and names no
    function, so a missing reader is a LOUD finding with the candidate list.
    """
    for name in ("_deception_action", "deception_action", "_verifier_deception_action"):
        value = getattr(s3v, name, None)
        if callable(value):
            return value
    candidates = sorted(
        name for name, value in vars(s3v).items()
        if callable(value) and "decept" in name.lower()
    )
    raise AssertionError(
        "gen/s3_verify.py exposes no `deception_action` reader. L-1 §Work 1: "
        "'KNOB: `verifier.deception_action` … Anything else loud at config load, "
        f"beside the other verifier knobs'. Callables naming 'decept': {candidates}"
    )


# --------------------------------------------------------------------------- #
# GROUP A — §Blind L4: validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "block",
    [{}, {"reject_cap": 2}, {"lever_corroboration": True}],
    ids=["empty-verifier-block", "other-knobs-only", "corroboration-only"],
)
def test_l4_an_absent_knob_reads_as_reject(block):
    """L-1 §Work 1: "Absent key = reject."."""
    assert _reader()({"verifier": dict(block)}) == ACTION_REJECT, (
        "L-1 §Work 1: 'Absent key = reject.' — an unconfigured batch must keep "
        "today's bytes"
    )
    assert _reader()({}) == ACTION_REJECT, (
        "L-1 §Work 1: 'Absent key = reject.' — a config with no `verifier:` block "
        "at all is the same absence"
    )


@pytest.mark.parametrize("value", [ACTION_REJECT, ACTION_RECORD])
def test_l4_the_two_signed_values_are_the_two_the_knob_takes(value):
    """L-1 §Work 1: values `"reject"` (default …) | `"record"`."""
    assert _reader()({"verifier": {KNOB: value}}) == value


@pytest.mark.parametrize(
    "value",
    ["lenient", "RECORD", "Reject", "", "records", True, False, 1, 0, None, [], {},
     ["record"]],
    ids=["lenient", "upper", "title", "empty", "near-miss", "true", "false", "one",
         "zero", "null", "list", "dict", "list-of-record"],
)
def test_l4_a_non_enum_value_is_loud_and_names_the_two_values(value):
    """L-1 §Blind L4: "`deception_action: "lenient"` (or any non-enum) -> loud at
    load, names the two values"."""
    with pytest.raises(ValueError) as caught:
        _reader()({"verifier": {KNOB: value}})
    message = str(caught.value)
    assert KNOB in message, (
        f"L-1 §Blind L4: the refusal must be fixable from the message alone, so it "
        f"names `verifier.{KNOB}`; got {message!r}"
    )
    for word in (ACTION_REJECT, ACTION_RECORD):
        assert word in message, (
            f"L-1 §Blind L4: the refusal 'names the two values'; {word!r} is missing "
            f"from {message!r}"
        )


def test_l4_the_knob_is_read_under_verifier_beside_the_other_knobs():
    """L-1 §Work 1: "Anything else loud at config load, BESIDE the other verifier
    knobs … (follow how existing verifier.* knobs … are read and validated;
    match that idiom exactly)".

    Ambiguity (a): no `verifier.*` knob is validated by `load_config` or the
    `check_config` preflight — each is read and refused at READ time inside its
    own stage.  So "beside the other verifier knobs" is pinned as THE IDIOM: the
    same ValueError-on-bad-data shape its two named neighbours use, and the same
    `verifier:` home (a top-level key is not the knob).
    """
    stray = {KNOB: ACTION_RECORD, "verifier": {}}
    assert _reader()(stray) == ACTION_REJECT, (
        f"a top-level {KNOB!r} was read as the knob — L-1 §Work 1 spells it "
        f"`verifier.{KNOB}`, under the block its neighbours live in"
    )
    for name, bad in (("_exempt_terms", {"exempt_terms": "not-a-list"}),
                      ("_lever_corroboration", {"lever_corroboration": "yes"})):
        neighbour = getattr(s3v, name, None)
        assert callable(neighbour), (
            f"L-1 §Work 1 names the neighbouring knobs this one must match "
            f"(reject_cap, round_cap, reconcile_early, exempt_terms); `{name}` is gone"
        )
        with pytest.raises(ValueError):
            neighbour({"verifier": bad})


def test_l4_a_bad_value_stops_the_stage_before_it_writes(slot, base_cfg, tmp_path):
    """L-1 §Work 1 + §Blind L4: loud, on the FULL path and the dry one.

    The knob decides whether a game is rejected, so a config that misspells it
    must stop the stage rather than fall back to the default and go on rejecting
    exactly the games it was set to let through.
    """
    bad = _cfg(base_cfg, "lenient")
    with pytest.raises(ValueError, match=KNOB):
        slot.run(bad, levers=(LEVER_A,))
    with pytest.raises(ValueError, match=KNOB):
        # `diff=None` — the dry run, which decides no diff codes at all. A knob
        # this stage writes a list for on EVERY report must be refused here too.
        slot.run(bad, diff=None)
    written = [path for path in tmp_path.rglob("*report*.json") if path.is_file()]
    assert not written, (
        f"the stage wrote {written} after refusing the config — L-1 §Work 1: "
        "'Anything else loud at config load'"
    )


# --------------------------------------------------------------------------- #
# GROUP B — §Blind L1: default = today's bytes
# --------------------------------------------------------------------------- #


def test_l1_a_lever_only_diff_still_rejects_under_the_default(slot, base_cfg):
    """L-1 §Blind L1: "absent knob / "reject" -> a lever-only diff still produces
    verdict reject with the undeclared-deception reason"."""
    report = slot.run(_cfg(base_cfg), levers=(LEVER_A,))
    assert report["diff"]["undeclared_deceptions"] == [LEVER_A], (
        "fixture wall: the round did not produce the lever-only diff L1 is about; "
        f"diff={report['diff']}"
    )
    assert report["verdict"] == VERDICT_REJECT, (
        "L-1 §Blind L1: with the knob absent 'a lever-only diff still produces "
        f"verdict reject'; got {report['verdict']!r}"
    )
    assert _codes(report["reject_reasons"]) == [LEVER_CODE], (
        "L-1 §Blind L1: the default rejects 'with the undeclared-deception reason'; "
        f"got {report['reject_reasons']}"
    )
    assert _levers(report["reject_reasons"]) == [LEVER_A], (
        f"the reject reason must still name the lever it is about: "
        f"{report['reject_reasons']}"
    )


def test_l1_the_advisory_list_exists_and_is_empty_under_the_default(slot, base_cfg):
    """L-1 §Blind L1: "`deception_advisories` exists and is []"; §Work 2: "In
    reject mode the report has `deception_advisories: []` (schema stable both
    modes)"."""
    report = slot.run(_cfg(base_cfg), levers=(LEVER_A,))
    assert ADVISORIES in report, (
        f"L-1 §Blind L1: '{ADVISORIES} exists and is []' under the default — the key "
        f"is missing. Report keys: {sorted(report)}"
    )
    assert report[ADVISORIES] == [], (
        f"L-1 §Blind L1: under the default the list is EMPTY, not absent and not "
        f"populated; got {report[ADVISORIES]}"
    )


def test_l1_an_explicit_reject_is_byte_identical_to_the_absent_knob(base_cfg, tmp_path, cap):
    """L-1 §Work 1: `"reject"` is the "default = today's bytes, byte-for-byte"."""
    absent = _Round(tmp_path / "absent", cap).run(_cfg(base_cfg), levers=(LEVER_A, LEVER_B))
    explicit = _Round(tmp_path / "explicit", cap).run(
        _cfg(base_cfg, ACTION_REJECT), levers=(LEVER_A, LEVER_B)
    )
    # The worker path is the one honest difference between two planted slots.
    for report in (absent, explicit):
        report.pop("worker")
    assert absent == explicit, (
        "L-1 §Work 1: '`\"reject\"` (default = today's bytes, byte-for-byte)' — the "
        "absent key and the explicit word must produce the same report"
    )


def test_l1_the_reject_reasons_are_the_untouched_decide_verdict_bytes(slot, base_cfg):
    """L-1 §Blind L1: "(the pre-L-1 behavior, byte-level on the report's
    reject_reasons)".

    `decide_verdict` is the frozen `(verdict, reject_reasons)` seam §Evidence
    names (gen/s3_verify.py:2151).  Under the default the report must carry
    exactly what that seam produced — no re-ordering, no re-wording, nothing
    moved.
    """
    diff = slot.diff(levers=(LEVER_A, LEVER_B, LEVER_C))
    verdict, reasons = s3v.decide_verdict([], copy.deepcopy(diff))
    report = slot.run(_cfg(base_cfg), levers=(LEVER_A, LEVER_B, LEVER_C))
    assert report["verdict"] == verdict, (
        "L-1 §Blind L1: the default verdict is the pre-L-1 one, decided by the "
        f"frozen seam; seam={verdict!r} report={report['verdict']!r}"
    )
    assert report["reject_reasons"] == reasons, (
        "L-1 §Blind L1 pins the default 'byte-level on the report's reject_reasons'. "
        f"The frozen seam produced {reasons}; the report carries "
        f"{report['reject_reasons']}"
    )


# --------------------------------------------------------------------------- #
# GROUP C — §Blind L2: record mode
# --------------------------------------------------------------------------- #


def test_l2_a_lever_only_report_is_a_pass_in_record_mode(slot, base_cfg):
    """L-1 §Blind L2: "the same lever-only diff -> verdict PASS, reject_reasons []";
    §Work 2: "a report whose only findings are levers is a PASS"."""
    report = slot.run(_cfg(base_cfg, ACTION_RECORD), levers=(LEVER_A,))
    assert report["diff"]["undeclared_deceptions"] == [LEVER_A], (
        f"fixture wall: no lever-only diff was produced; diff={report['diff']}"
    )
    assert report["verdict"] == VERDICT_PASS, (
        "L-1 §Blind L2: in record mode the same lever-only diff is a PASS; got "
        f"{report['verdict']!r} with reasons {report['reject_reasons']}"
    )
    assert report["reject_reasons"] == [], (
        "L-1 §Work 2: the lever rows 'never flip the verdict, never count a reject' — "
        f"reject_reasons is {report['reject_reasons']}"
    )


def test_l2_the_advisories_are_the_same_rows_the_default_would_have_rejected_on(
    base_cfg, tmp_path, cap
):
    """L-1 §Blind L2: "the SAME rows (lever, detail, evidence) under
    deception_advisories"; §Work 2: "same row shape, same evidence/corroboration
    content"."""
    levers = (LEVER_A, LEVER_B, LEVER_C)
    rejected = _Round(tmp_path / "rej", cap).run(_cfg(base_cfg), levers=levers)
    recorded = _Round(tmp_path / "rec", cap).run(_cfg(base_cfg, ACTION_RECORD), levers=levers)
    assert recorded[ADVISORIES] == rejected["reject_reasons"], (
        "L-1 §Blind L2: record mode moves 'the SAME rows (lever, detail, evidence)' "
        f"into {ADVISORIES}. The default rejected on {rejected['reject_reasons']}; "
        f"the advisories are {recorded[ADVISORIES]}"
    )
    assert _codes(recorded[ADVISORIES]) == [LEVER_CODE] * len(levers), (
        f"every advisory is an {LEVER_CODE} row: {recorded[ADVISORIES]}"
    )
    assert sorted(_levers(recorded[ADVISORIES])) == sorted(levers), (
        f"the advisories must name every lever the audit sighted: {recorded[ADVISORIES]}"
    )


def test_l2_the_report_schema_is_stable_across_both_modes(base_cfg, tmp_path, cap):
    """L-1 §Work 2: "schema stable both modes"; Addendum 1 D3: "NO b7.1 bump"."""
    levers = (LEVER_A,)
    rejected = _Round(tmp_path / "rej", cap).run(_cfg(base_cfg), levers=levers)
    recorded = _Round(tmp_path / "rec", cap).run(_cfg(base_cfg, ACTION_RECORD), levers=levers)
    assert set(rejected) == set(recorded), (
        "L-1 §Work 2: 'schema stable both modes' — the two modes write different "
        f"top-level keys: reject-only {sorted(set(rejected) - set(recorded))}, "
        f"record-only {sorted(set(recorded) - set(rejected))}"
    )
    for report in (rejected, recorded):
        assert report["schema_version"] == SCHEMA, (
            "Addendum 1 ratified D3: 'NO b7.1 bump'. The report says "
            f"{report['schema_version']!r}"
        )
    assert s3v.SCHEMA_VERSION == SCHEMA, (
        f"Addendum 1 D3 ratified no schema bump; the module now pins "
        f"{s3v.SCHEMA_VERSION!r}"
    )


@pytest.mark.parametrize("action", [_ABSENT, ACTION_REJECT, ACTION_RECORD],
                         ids=["absent", "reject", "record"])
def test_addendum1_d3_the_advisory_key_is_always_written(slot, base_cfg, action):
    """Addendum 1 D3: "`deception_advisories` always-written"."""
    report = slot.run(_cfg(base_cfg, action), levers=(LEVER_A,))
    assert ADVISORIES in report, (
        f"Addendum 1 D3: '{ADVISORIES} always-written' — missing with the knob "
        f"{'absent' if action is _ABSENT else repr(action)}"
    )


def test_addendum1_d3_the_advisory_key_is_optional_in_validation(slot, base_cfg):
    """Addendum 1 D3: "always-written but OPTIONAL in validation, protecting every
    shipped pre-L-1 report (the file's own additive convention)"."""
    report = slot.run(_cfg(base_cfg, ACTION_RECORD), levers=(LEVER_A,))
    pre_l1 = {key: value for key, value in report.items() if key != ADVISORIES}
    pre_l1["verdict"] = VERDICT_REJECT
    pre_l1["reject_reasons"] = list(report[ADVISORIES])
    s3v.validate_report(pre_l1)   # a pre-L-1 report off disk must still validate
    # …and a present one is still CHECKED, not waved through: the key may only
    # carry the one code the ruling moves, or a reject went missing.
    bad = dict(report)
    bad[ADVISORIES] = [{"code": TERM_CODE, "detail": "a term that stopped rejecting"}]
    with pytest.raises(ValueError):
        s3v.validate_report(bad)


# --------------------------------------------------------------------------- #
# GROUP D — §Blind L3: mixed findings
# --------------------------------------------------------------------------- #


def _slot_ctx(cfg: Mapping, root: Path) -> orch.SlotContext:
    """A SlotContext whose `verifier_report_path` is a file this test controls.

    The orchestrator reads the residual it reconciles against off the report on
    disk (§Evidence: "orchestrator consumes via `_verifier_reject_reasons`"), so
    the only honest way to ask "what does reconciliation see?" is to hand it a
    real report at the real path.
    """
    spec_dir = root / "corpus" / "slug"
    (spec_dir / orch.WORKER_DIRNAME).mkdir(parents=True, exist_ok=True)
    return orch.SlotContext(
        cfg=cfg, batch_id="l1blind", slug="slug", index=1, state="implemented",
        stage="s3_verify", attempt=1, batch_dir=root / "batch", ideas_dir=root / "ideas",
        idea_path=root / "ideas" / "idea-001.json", corpus_dir=root / "corpus",
        spec_dir=spec_dir, respec_count=0, verifier_rejects=1, green_failures=0,
    )


def _plant(ctx: orch.SlotContext, report: Mapping) -> Path:
    path = ctx.verifier_report_path
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


def test_l3_the_term_rejects_alone_while_the_lever_rides_as_an_advisory(slot, base_cfg):
    """L-1 §Blind L3: "levers + 1 undeclared term in record mode -> the term still
    rejects alone; the lever rides as advisory"."""
    report = slot.run(
        _cfg(base_cfg, ACTION_RECORD), levers=(LEVER_A, LEVER_B), extra_terms=(STRAY_TERM,)
    )
    assert report["diff"]["undeclared_terms"] == [STRAY_TERM], (
        f"fixture wall: no undeclared term in the diff; diff={report['diff']}"
    )
    assert report["verdict"] == VERDICT_REJECT, (
        "L-1 §Blind L3: 'the term still rejects' — record mode softens the LEVER "
        f"class and nothing else; got {report['verdict']!r}"
    )
    assert _codes(report["reject_reasons"]) == [TERM_CODE], (
        "L-1 §Blind L3: the term rejects ALONE — no lever row may remain in "
        f"reject_reasons; got {report['reject_reasons']}"
    )
    assert sorted(_levers(report[ADVISORIES])) == sorted([LEVER_A, LEVER_B]), (
        "L-1 §Blind L3: 'the lever rides as advisory'; advisories are "
        f"{report[ADVISORIES]}"
    )


def test_l3_reconciliation_sees_only_the_term(slot, base_cfg, tmp_path):
    """L-1 §Blind L3: "reconciliation sees ONLY the term"; §Work 2: the lever rows
    "never reach reconciliation"."""
    cfg = _cfg(base_cfg, ACTION_RECORD)
    report = slot.run(cfg, levers=(LEVER_A, LEVER_B), extra_terms=(STRAY_TERM,))
    ctx = _slot_ctx(cfg, tmp_path / "ctx")
    _plant(ctx, report)
    reasons = orch._verifier_reject_reasons(ctx)
    assert reasons is not None, (
        "the mixed report is a reject, so the orchestrator must have a residual to "
        "reconcile against"
    )
    assert _codes(reasons) == [TERM_CODE], (
        "L-1 §Blind L3: 'reconciliation sees ONLY the term'. The residual the "
        f"orchestrator reads off the report is {reasons}"
    )


def test_l3_a_lever_only_record_report_leaves_reconciliation_nothing(slot, base_cfg, tmp_path):
    """L-1 §Work 2: the lever rows "never reach reconciliation — a report whose
    only findings are levers is a PASS"."""
    cfg = _cfg(base_cfg, ACTION_RECORD)
    report = slot.run(cfg, levers=(LEVER_A,))
    ctx = _slot_ctx(cfg, tmp_path / "ctx")
    _plant(ctx, report)
    assert orch._verifier_reject_reasons(ctx) is None, (
        "L-1 §Work 2: a lever-only report is a PASS and the levers 'never reach "
        "reconciliation' — the orchestrator was handed a residual anyway"
    )


def test_l3_the_control_the_same_diff_rejects_on_both_under_the_default(slot, base_cfg):
    """The control for L3: without the knob the mixed diff rejects on BOTH codes,
    which is the behaviour L-1 §Blind L1 freezes as today's bytes."""
    report = slot.run(_cfg(base_cfg), levers=(LEVER_A, LEVER_B), extra_terms=(STRAY_TERM,))
    assert sorted(set(_codes(report["reject_reasons"]))) == sorted({LEVER_CODE, TERM_CODE}), (
        "under the default the mixed diff must reject on the lever AND the term; got "
        f"{report['reject_reasons']}"
    )
    assert report[ADVISORIES] == [], (
        f"L-1 §Work 2: 'In reject mode the report has {ADVISORIES}: []'"
    )


# --------------------------------------------------------------------------- #
# GROUP E — §Blind L5: the overlay
# --------------------------------------------------------------------------- #


def _flat(data: Mapping, prefix: str = "") -> dict:
    out: dict = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            out.update(_flat(value, path + "."))
        else:
            out[path] = value
    return out


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """A tmp `config/` + `out/batches/`, aimed at by every id/seed scan."""
    config_dir = tmp_path / "config"
    batches = tmp_path / "out" / "batches"
    config_dir.mkdir(parents=True)
    batches.mkdir(parents=True)
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(orch, "BATCHES_ROOT", batches)
    return config_dir, batches


def _overlay() -> dict:
    overlay = getattr(cli, "AUTONOMY_OVERLAY", None)
    assert isinstance(overlay, Mapping), (
        "L-1 §Work 4: 'CLI: AUTONOMY_OVERLAY gains `verifier.deception_action: "
        '"record"`\' — gen/cli.py exposes no AUTONOMY_OVERLAY'
    )
    return _flat(overlay)


def test_l5_the_overlay_carries_the_knob_at_record():
    """L-1 §Work 4: "AUTONOMY_OVERLAY gains `verifier.deception_action: "record"`"."""
    flat = _overlay()
    dotted = f"verifier.{KNOB}"
    assert flat.get(dotted) == ACTION_RECORD, (
        f"L-1 §Work 4: the overlay must carry {dotted}: {ACTION_RECORD!r}; it carries "
        f"{flat.get(dotted)!r}. Overlay: {flat}"
    )


def test_l5_the_overlay_grew_by_exactly_one_key_to_seven():
    """L-1 §Blind L5: "the overlay diff pin count grows by exactly one key", read
    per Addendum 1 D2 as "the AUTONOMY_OVERLAY's own key count 6->7".

    The six that were there are b005r2's arming, and the seventh cannot be: the
    knob was written after that batch ran, so `config/b005r2-auto.yaml` carries
    no such key.  That absence is what makes "exactly one" measurable.
    """
    # PIN UPDATE, 2026-10-05 (contract E-2 §4, a licensed overlay-pin edit).
    # L5's claim is about L-1's OWN delta (6 -> 7 with `deception_action` as the
    # seventh), so the keys later contracts added are subtracted BY NAME and the
    # count is not bumped: this pin still goes red if an eighth key appears
    # without a contract claiming it here.
    flat = set(_overlay()) - LATER_CONTRACT_OVERLAY_KEYS
    dotted = f"verifier.{KNOB}"
    assert len(flat) == 7, (
        "L-1 §Blind L5 + Addendum 1 D2: the overlay's own key count is 6 -> 7 "
        f"(the b005r2 arming plus `{dotted}`, and excluding "
        f"{sorted(LATER_CONTRACT_OVERLAY_KEYS)}); it holds {len(flat)}: {sorted(flat)}"
    )
    live = yaml.safe_load(B005R2_CONFIG.read_text(encoding="utf-8"))
    # LEAD UPDATE 2026-10-06: "written after that batch ran" was true at L-1's
    # close and is now a dated fact rather than a live absence — revival #3's
    # RECORDED OPERATOR AMENDMENT armed the same value in the live file. The
    # wall therefore accepts absent-or-equal: any OTHER live value would mean
    # the overlay's seventh key no longer matches the file this pin names.
    live_value = (live.get("verifier") or {}).get(KNOB, "record")
    assert live_value == "record", (
        f"fixture wall: config/b005r2-auto.yaml carries `verifier.{KNOB}: {live_value!r}`, "
        "which is neither absent nor the overlay's own 'record'"
    )
    for dotted_key in sorted(set(flat) - {dotted}):
        block, _, key = dotted_key.partition(".")
        assert key in (live.get(block) or {}), (
            f"L-1 §Work 4 calls the other six keys the b005r2 arming, and {dotted_key} "
            "is not in config/b005r2-auto.yaml — the overlay grew by more than the one "
            "key L-1 licensed"
        )


def test_l5_the_materialized_config_carries_the_knob_at_record(roots):
    """L-1 §Blind L5: "CLI-materialized config carries verifier.deception_action:
    record"."""
    cfg = cli.build_config(driver="claude", games=1, seed=7)
    assert (cfg.get("verifier") or {}).get(KNOB) == ACTION_RECORD, (
        "L-1 §Blind L5: the config `arc-games run` would write must carry "
        f"`verifier.{KNOB}: {ACTION_RECORD}`; its verifier block is {cfg.get('verifier')}"
    )
    assert f"{KNOB}: {ACTION_RECORD}" in cli.render_config(cfg), (
        "the knob must survive into the YAML the orchestrator is invoked on, not just "
        "the in-memory dict"
    )


def test_l5_dry_run_surfaces_the_knob(roots, monkeypatch, capsys):
    """L-1 §Blind L5: "--dry-run surfaces it".

    `preflight` is stubbed out: it probes the machine (drivers, keys, the canon
    stamp) and this lane runs no subprocess and reads no real credential store.
    The rehearsal's settings block is printed before preflight is consulted, so
    the stub cannot change what is measured here.
    """
    monkeypatch.setattr(cli, "preflight", lambda *args, **kwargs: [])
    code = cli.main(["run", "--driver", "claude", "--games", "1", "--seed", "7", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0, f"the rehearsal failed: {out}"
    assert f"{KNOB}: {ACTION_RECORD}" in out, (
        "L-1 §Blind L5: '--dry-run surfaces it' — the rehearsal's settings block never "
        f"shows `{KNOB}`:\n{out}"
    )


def test_addendum1_d2_the_materialization_diff_gains_no_moved_key(roots):
    """Addendum 1 D2, ratified: "template+overlay both carry `record`, so the
    materialization diff gains no moved key".

    L-1 §Work 7's DECISION is the other half: "the template ARMS
    `deception_action: record` … the DEFAULT (absent key) stays reject".
    """
    raw = yaml.safe_load(REAL_TEMPLATE.read_text(encoding="utf-8"))
    assert (raw.get("verifier") or {}).get(KNOB) == ACTION_RECORD, (
        "L-1 §Work 7 DECISION: 'the template ARMS `deception_action: record`'; "
        f"config/template.yaml's verifier block is {raw.get('verifier')}"
    )
    cfg = cli.build_config(driver="claude", games=2, tiers=["t1", "t2"], seed=99)
    before, after = _flat(raw), _flat(cfg)
    moved = (set(before) ^ set(after)) | {
        key for key in set(before) & set(after) if before[key] != after[key]
    }
    assert f"verifier.{KNOB}" not in moved, (
        "Addendum 1 D2: 'the materialization diff gains no moved key' — the template "
        "and the overlay must agree on `record`, so materialising it moves nothing. "
        f"Moved keys: {sorted(moved)}"
    )
    # …and the CODE default is still `reject`: arming the template is not arming
    # the stage (L-1 §Work 1, "Absent key = reject").
    assert _reader()({"verifier": {}}) == ACTION_REJECT


# --------------------------------------------------------------------------- #
# GROUP F — §Blind L6: the t1 trap, end to end (+ §Work 3 VISIBILITY)
# --------------------------------------------------------------------------- #
#
# The exhibit, in the contract's own words: "t1's signed tier table allows 0
# levers (`tier-deceptions`); so an `undeclared-deception` sighting at t1 can
# neither be declared (the amended spec lint-kills — orchestrator.
# _reconcile_declarations:3360 restores and refuses …) nor repaired game-side …
# The slot rides the ladder to round_cap and parks."

#: The lever the fake t1 slot's every audit round sights.
TRAP_LEVER = LEVER_A
#: Two rejecting rounds and the cap set to two, so ONLY the round cap can fire
#: (`reject_cap` is armed well clear of it).
TRAP_ROUND_CAP = 2


def _trap_cfg(make_cfg, batch_id: str, *, tier: str = "t1") -> tuple[dict, dict]:
    """A one-slot batch armed like the live exhibit's own config.

    `tiers.knob_defaults_action: kill` is what gives `tier-deceptions` its teeth
    — the contract's exhibit is a t1 game whose *signed tier table* allows zero
    levers, and an unarmed table refuses nothing.  It is also exactly what
    `gen/cli.py:AUTONOMY_OVERLAY` arms for every autonomous batch.
    """
    cfg, idea = b005._armed_cfg(
        make_cfg, batch_id, round_cap=TRAP_ROUND_CAP, reject_cap=5, tier=tier,
        max_attrition=1.0,
    )
    cfg["tiers"] = {**cfg["tiers"], "knob_defaults_action": "kill"}
    return cfg, idea


def _trap_reports(root: Path, cap: object, action: object, base: Mapping) -> list[dict]:
    """The REAL verifier reports for a t1 slot that sights a lever every round.

    Not hand-written: `assemble_report` writes them, from the same lever-only
    audit, under the knob value the scenario is about.  `base` is passed in
    rather than re-loaded: `batch_home` repoints `gen.config.REPO_ROOT` at tmp,
    so a relative config path no longer resolves inside these scenarios.
    """
    rounds = _Round(root, cap)
    cfg = _cfg(base, action)
    reports = []
    for _ in range(TRAP_ROUND_CAP + 1):
        report = rounds.run(cfg, levers=(TRAP_LEVER,))
        # The rig plants this as the slot's own S2b artifact, so it must speak
        # about the slot's game.
        report["game_id"] = b005.SPEC_SLUG
        reports.append(report)
    return reports


def _drive_trap(make_cfg, batch_id: str, reports: list[dict], *, tier: str = "t1"):
    """One slot through the real orchestrator, with the real reports planted.

    THE BRIDGE, stated rather than assumed (see the module docstring): the fake
    stage's ok/to_state is derived from the planted report's own verdict, which
    is what `gen/s3_verify.py::main` does with its exit code.  A `pass` report
    therefore takes the happy edge and a `reject` report takes the reject edge —
    the rig never decides for itself what the audit said.
    """
    cfg, idea = _trap_cfg(make_cfg, batch_id, tier=tier)
    rejecting = sum(1 for report in reports if report["verdict"] != VERDICT_PASS)
    outcomes = {}
    if rejecting:
        outcomes["implemented"] = b11._Outcome(
            "spec_ok", f"verifier reject: {LEVER_CODE}", times=rejecting
        )
    journal = b11._Journal()
    runners = b005._SpecRunners(journal, cfg, outcomes=outcomes, idea=idea,
                               verify_reports=reports)
    report = orch.run_batch(cfg, runners=runners)
    return b005._Run(cfg, journal, runners, report)


def test_l6_the_trap_itself_a_t1_lever_cannot_be_declared(tmp_path, base_cfg, cap):
    """L-1 §The live exhibit: "an `undeclared-deception` sighting at t1 can neither
    be declared (the amended spec lint-kills — orchestrator.
    _reconcile_declarations … restores and refuses) nor repaired game-side".

    Driven at the function the contract's evidence section names, so the park in
    the next test is explained rather than merely observed.
    """
    cfg, idea = {}, dict(b005.IDEA)
    idea["tier"] = "t1"
    cfg = copy.deepcopy(dict(base_cfg))
    cfg["tiers"] = {"term_budget": dict(b005.KILL_BUDGETS), "term_budget_action": "kill",
                    "knob_defaults_action": "kill"}
    ctx = _slot_ctx(cfg, tmp_path / "trap")
    spec_path = ctx.spec_dir / "spec.yaml"
    spec_path.write_text(b005.SPEC_TEXT, encoding="utf-8")
    ctx.idea_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.idea_path.write_text(json.dumps(idea, indent=2), encoding="utf-8")
    before = spec_path.read_bytes()

    reason = {"code": LEVER_CODE, "lever": TRAP_LEVER,
              "detail": f"the audit detected the {TRAP_LEVER!r} lever; the spec declares []"}
    outcome = orch._reconcile_declarations(ctx, [reason])

    assert outcome["ok"] is False, (
        "L-1 §The live exhibit: at t1 the lever 'can neither be declared … nor "
        f"repaired game-side'. The reconciliation succeeded instead: {outcome}"
    )
    assert "tier-deceptions" in str(outcome["why"]), (
        "L-1 §The live exhibit names the rule that kills the amendment: "
        f"`tier-deceptions`. The refusal says {outcome['why']!r}"
    )
    assert spec_path.read_bytes() == before, (
        "L-1 §The live exhibit: the reconciliation 'restores and refuses' — the spec "
        "must be byte-for-byte what it was after a refused amendment"
    )
    # …and the same lever at t2 IS declarable, which is what makes this a t1 trap
    # and not a blanket refusal.
    idea["tier"] = "t2"
    ctx.idea_path.write_text(json.dumps(idea, indent=2), encoding="utf-8")
    assert orch._reconcile_declarations(ctx, [reason])["ok"] is True, (
        "fixture wall: the trap must be t1's. The same lever was refused at t2 too, "
        "so this scenario no longer measures what L-1 §The live exhibit describes"
    )


def test_l6_in_the_default_the_t1_slot_rides_the_ladder_to_round_cap_and_parks(
    make_cfg, tmp_path, cap, base_cfg, batch_home
):
    """L-1 §Blind L6: "in the default it parks at round_cap exactly as g20261001-1
    was heading"."""
    reports = _trap_reports(tmp_path / "verify-reject", cap, _ABSENT, base_cfg)
    assert [r["verdict"] for r in reports] == [VERDICT_REJECT] * len(reports), (
        "fixture wall: under the default every lever-sighting round must reject "
        f"(L-1 §Blind L1); got {[r['verdict'] for r in reports]}"
    )
    run = _drive_trap(make_cfg, "l1blind-trap-reject", reports)

    spine = b11._spine(b11._ledger_lines(run.cfg))
    assert ("implemented", "parked") in spine, (
        "L-1 §Blind L6: in the default the t1 slot 'parks at round_cap exactly as "
        f"g20261001-1 was heading'. The slot's spine is {spine}"
    )
    parked = run.report.get("parked") or []
    assert parked, f"the batch report records no parked slot: {b11._text(run.report)[:2000]}"
    reason = "\n".join(b005._reasons(run.cfg, ("implemented", "parked")))
    assert LEVER_CODE in reason, (
        "the park must name the residual that caused it — L-1 §The live exhibit: the "
        f"finding 'is un-actionable BY CONSTRUCTION'. The park reason is {reason!r}"
    )
    assert "tier-deceptions" in reason, (
        "L-1 §The live exhibit: the amendment lint-kills on `tier-deceptions`, which "
        f"is why the slot parks. The park reason is {reason!r}"
    )
    assert run.runners.verify_calls == TRAP_ROUND_CAP, (
        f"the slot must spend its {TRAP_ROUND_CAP} rejecting rounds and then park, not "
        f"audit again; it audited {run.runners.verify_calls}×"
    )
    assert b005._deceptions_on_disk(run.cfg) == [], (
        "L-1 §The live exhibit: the lever 'can neither be declared' — the parked "
        "slot's spec must not be left claiming a reconciliation that did not stand"
    )
    # The control for the record-mode run's "never count a reject": under the
    # default the very same sighting DOES count against the slot. (The count is
    # not pinned to a number — the final round leaves on the `parked` edge, which
    # the ledger counts as a park and not as a reject.)
    assert b005._one_slot(run.report)["rejects"]["verifier"] >= 1, (
        "under the default a lever sighting counts a verifier reject against the slot "
        f"(L-1 §Blind L1); the slot's reject ledger is "
        f"{b005._one_slot(run.report)['rejects']}"
    )


def test_l6_in_record_mode_the_t1_slot_passes_verify_and_proceeds(
    make_cfg, tmp_path, cap, base_cfg, batch_home
):
    """L-1 §Blind L6: "in record mode the slot PASSES verify and proceeds (no
    respec, no park)"."""
    reports = _trap_reports(tmp_path / "verify-record", cap, ACTION_RECORD, base_cfg)
    assert [r["verdict"] for r in reports] == [VERDICT_PASS] * len(reports), (
        "fixture wall: in record mode every lever-only round is a PASS (L-1 §Blind "
        f"L2); got {[r['verdict'] for r in reports]}"
    )
    run = _drive_trap(make_cfg, "l1blind-trap-record", reports)

    spine = b11._spine(b11._ledger_lines(run.cfg))
    assert ("implemented", "verified") in spine, (
        "L-1 §Blind L6: 'in record mode the slot PASSES verify and proceeds'. The "
        f"slot's spine is {spine}"
    )
    assert ("implemented", "spec_ok") not in spine, (
        f"L-1 §Blind L6: 'no respec'. The slot was sent back to S1 anyway: {spine}"
    )
    assert ("implemented", "parked") not in spine, (
        f"L-1 §Blind L6: 'no park'. The slot parked anyway: {spine}"
    )
    assert not (run.report.get("parked") or []), (
        f"L-1 §Blind L6: 'no park'; the batch report parks {run.report.get('parked')}"
    )
    assert run.runners.verify_calls == 1, (
        "a passing audit is audited ONCE — the ladder never engages; the slot was "
        f"audited {run.runners.verify_calls}×"
    )
    slot_row = b005._one_slot(run.report)
    assert slot_row["state"] not in ("parked", "dead"), (
        f"the record-mode slot ended at {slot_row['state']!r}"
    )
    assert slot_row["rejects"]["verifier"] == 0, (
        "L-1 §Work 2: the lever rows 'never flip the verdict, NEVER COUNT A REJECT'. "
        f"The slot's reject ledger is {slot_row['rejects']}"
    )


def test_work3_the_recorded_advisory_is_printed_at_the_stop(
    make_cfg, tmp_path, cap, base_cfg, batch_home, monkeypatch, capsys
):
    """L-1 §Work 3 VISIBILITY: "the advisories are not silent — they print at the
    review stop / slot report wherever reject_reasons print today ('deception
    advisories (recorded, not rejecting): …')"; Addendum 1 D5: "stop print
    per-slot".

    Driven through the real `orchestrator.main`, with `run_batch` wrapped so the
    fake runners reach it — the stop print lives in `main`, not in `run_batch`,
    and a record that nobody is shown is the defect this clause exists to close.
    """
    reports = _trap_reports(tmp_path / "verify-stop", cap, ACTION_RECORD, base_cfg)
    cfg, idea = _trap_cfg(make_cfg, "l1blind-stop-print")
    path = tmp_path / "l1blind-stop-print.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    runners = b005._SpecRunners(b11._Journal(), cfg, idea=idea, verify_reports=reports)

    real_run_batch = orch.run_batch
    monkeypatch.setattr(
        orch, "run_batch",
        lambda config, **kwargs: real_run_batch(config, runners=runners, **kwargs),
    )
    orch.main(["--config", str(path)])   # the exit code is the REVIEW stop's, not L-1's
    out = capsys.readouterr().out
    assert "Traceback" not in out, f"the batch crashed instead of stopping:\n{out[-3000:]}"
    assert STOP_PHRASE in out, (
        "L-1 §Work 3: the advisories 'are not silent — they print … "
        f"({STOP_PHRASE!r})'. The run printed:\n{out[-3000:]}"
    )
    advisory_lines = [line for line in out.splitlines() if STOP_PHRASE in line]
    assert any(TRAP_LEVER in line for line in advisory_lines), (
        "L-1 §Work 3: the printed record must name the lever it recorded; the stop "
        f"printed {advisory_lines}"
    )


def test_work3_the_stop_reader_answers_only_for_a_recorded_finding(
    slot, base_cfg, tmp_path
):
    """L-1 §Work 3: the stop prints what the REPORT recorded, and nothing else.

    Addendum 1 D5 puts the print per-slot, so the reader it feeds from is asked
    the three questions a batch can put to it: a recorded finding, a rejecting
    one, and a pre-L-1 report that has no such key at all.
    """
    reader = getattr(orch, "_deception_advisories", None)
    assert callable(reader), (
        "L-1 §Work 3 promises the advisories 'print at the review stop / slot report'; "
        "gen/orchestrator.py exposes no per-slot advisory reader to print from"
    )
    worker = tmp_path / "corpus" / "slug" / orch.WORKER_DIRNAME
    worker.mkdir(parents=True)
    report_path = worker.with_name(worker.name + orch.VERIFIER_REPORT_SUFFIX)

    recorded = slot.run(_cfg(base_cfg, ACTION_RECORD), levers=(LEVER_A, LEVER_B))
    report_path.write_text(json.dumps(recorded, indent=2), encoding="utf-8")
    rows = reader(str(worker))
    assert len(rows) == 2 and all(isinstance(row, str) for row in rows), (
        f"L-1 §Work 3: one printable line per recorded finding; got {rows}"
    )
    assert any(LEVER_A in row for row in rows) and any(LEVER_B in row for row in rows), (
        f"the printed lines must name the levers the report recorded: {rows}"
    )

    rejected = slot.run(_cfg(base_cfg), levers=(LEVER_A,))
    report_path.write_text(json.dumps(rejected, indent=2), encoding="utf-8")
    assert reader(str(worker)) == [], (
        "L-1 §Work 2: 'In reject mode the report has deception_advisories: []' — the "
        "stop must print nothing for a batch that never armed the knob"
    )

    pre_l1 = {key: value for key, value in rejected.items() if key != ADVISORIES}
    report_path.write_text(json.dumps(pre_l1, indent=2), encoding="utf-8")
    assert reader(str(worker)) == [], (
        "Addendum 1 D3: a pre-L-1 report 'carries no such key' and must read as "
        "nothing to print, never as a crash"
    )
    report_path.unlink()
    assert reader(str(worker)) == [] and reader(None) == [], (
        "the stop prints what it can read and never dies on an absent report"
    )


def test_work3_the_s3_cli_print_is_not_driven_here():
    """L-1 §Work 3 has TWO print sites; this lane drives one of them.

    The orchestrator stop is driven for real above.  The S3 stage's own line
    ("wherever reject_reasons print today") needs a live verify run — an agent
    session against a real worker — which this lane may not do (§Hard rules: no
    API spend, no live driver calls).  Rather than skip it silently, the promised
    surface is asserted to EXIST and to be wired to the report's advisory list,
    and the behavioural half is reported as not driven.
    """
    source = inspect.getsource(s3v.main)
    assert STOP_PHRASE in source, (
        f"L-1 §Work 3: the S3 stage must print {STOP_PHRASE!r} 'wherever "
        "reject_reasons print today'; its CLI prints no such line"
    )
    assert "reject_reasons" in source, (
        "fixture wall: the S3 CLI no longer prints reject_reasons, so 'wherever "
        "reject_reasons print today' no longer names a place in this function"
    )


# --------------------------------------------------------------------------- #
# GROUP G — §Work 5: SCOPE GUARDS
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"dead_spec_terms": [SPEC_TERM]}, DEAD_TERM_CODE),
        ({"undeclared_terms": [STRAY_TERM]}, TERM_CODE),
        ({"unreachable_declared_mechanics": [SPEC_TERM]}, "unreachable-declared-mechanic"),
    ],
    ids=["dead-spec-term", "undeclared-term", "unreachable-declared-mechanic"],
)
def test_work5_every_other_reject_code_still_rejects_in_record_mode(
    slot, base_cfg, overrides, expected
):
    """L-1 §Work 5: "`undeclared-term`/`dead-spec-term` and every other reject code
    are untouched"."""
    diff = {key: [] for key in s3v.DIFF_KEYS}
    diff["terms_declared"] = [SPEC_TERM]
    diff["terms_detected_reachable"] = [SPEC_TERM]
    diff["deceptions_detected"] = [LEVER_A]
    diff["undeclared_deceptions"] = [LEVER_A]
    diff.update(overrides)
    report = slot.run(_cfg(base_cfg, ACTION_RECORD), levers=(LEVER_A,), diff=diff)
    assert report["verdict"] == VERDICT_REJECT, (
        f"L-1 §Work 5: {expected!r} is untouched by this contract and must still "
        f"reject in record mode; the verdict is {report['verdict']!r}"
    )
    assert _codes(report["reject_reasons"]) == [expected], (
        f"L-1 §Work 5: only the lever class moves. reject_reasons is "
        f"{report['reject_reasons']}"
    )
    assert _levers(report[ADVISORIES]) == [LEVER_A], (
        f"the lever still rides as an advisory beside it: {report[ADVISORIES]}"
    )


def test_work5_the_corroboration_bar_still_runs_first_and_upstream(slot, base_cfg):
    """L-1 §Evidence: "an undeclared-deception finding already rejects only on a
    corroborated sighting … UPSTREAM of the append site; leave it untouched (it
    still gates what is worth recording)".

    A first sighting under the armed corroboration bar reaches NEITHER list: the
    knob decides where a SURVIVING finding lands, not what survives.
    """
    cfg = _cfg(base_cfg, ACTION_RECORD)
    cfg["verifier"][  # the bar the contract says is upstream and untouched
        "lever_corroboration"] = True
    report = slot.run(cfg, levers=(LEVER_A,))
    assert report[ADVISORIES] == [], (
        "L-1 §Evidence: the corroboration bar is UPSTREAM of the append site and "
        "'still gates what is worth recording' — an uncorroborated first sighting "
        f"was recorded as an advisory anyway: {report[ADVISORIES]}"
    )
    assert report["reject_reasons"] == [], (
        f"an uncorroborated sighting rejects nothing either: {report['reject_reasons']}"
    )
    assert report["diff"].get("uncorroborated_levers"), (
        "fixture wall: the corroboration bar did not run, so this test is not "
        f"measuring what L-1 §Evidence describes; diff={report['diff']}"
    )


def test_work5_the_lint_side_tier_deceptions_rule_is_untouched(tmp_path, base_cfg):
    """L-1 §Work 5: "the lint-side `tier-deceptions` rule on DECLARED levers is
    untouched (authorship still can't over-declare its tier)".

    Record mode is about what the AUDIT found.  A spec that DECLARES a lever its
    tier does not allow is still refused, whatever the knob says.
    """
    from gen import tiers as tiers_mod
    from gen.s0_ideas import load_vocab
    from gen.s1_spec import (
        _lint_require_render,
        lint_rule_actions,
        lint_silent_levels_floor,
        lint_spec,
    )

    cfg = copy.deepcopy(dict(base_cfg))
    cfg["verifier"] = {KNOB: ACTION_RECORD}
    cfg["tiers"] = {"term_budget": dict(b005.KILL_BUDGETS), "term_budget_action": "kill",
                    "knob_defaults_action": "kill"}
    doc = yaml.safe_load(b005.SPEC_TEXT)
    doc["game"]["knobs"]["deceptions"] = [f"{TRAP_LEVER}: authored, not audited"]
    report = lint_spec(
        doc, set(load_vocab(cfg)), {**b005.IDEA, "tier": "t1"},
        tier_policy=tiers_mod.tier_policy(cfg),
        require_render=_lint_require_render(cfg),
        rule_actions=lint_rule_actions(cfg),
        silent_levels_floor=lint_silent_levels_floor(cfg),
    )
    assert not report.passed, (
        "L-1 §Work 5: the lint-side `tier-deceptions` rule on DECLARED levers is "
        "untouched — a t1 spec declaring a lever must still be refused"
    )
    assert "tier-deceptions" in {kill["rule"] for kill in report.kills}, (
        f"the refusal must still be `tier-deceptions`; kills are {report.kills}"
    )
