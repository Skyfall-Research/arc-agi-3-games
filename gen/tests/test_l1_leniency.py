"""Contract L-1 — the IMPLEMENTER's own pins for `verifier.deception_action`.

This is NOT the blind lane's file (`gen/tests/test_v2_leniency.py`, written
from the contract alone and never read from here, nor written by this lane). It
pins the things the implementer decided and has to keep true:

  * the DEFAULT is today's bytes — absent knob and explicit `reject` produce
    the same verdict, the same reasons and the same report keys the stage wrote
    before this contract, with the advisory list empty (pins 1-2);
  * `record` moves the SAME row — lever, code, detail — out of
    `reject_reasons` and into `deception_advisories`, never flipping anything
    else: a lever-only report is a PASS, a lever + a term is still a reject
    that names only the term, and the reconciliation that reads the report off
    disk sees only the term (pins 3-5);
  * the knob is read ONCE, validated at read time, and loud on anything that is
    not one of the two signed words — including on a dry run, where no diff
    exists to be judged (pin 6);
  * the report schema is additive: `deception_advisories` is an OPTIONAL
    top-level key, so every b7.1 report written before this contract still
    validates, while every report this stage writes now carries it in both
    modes (pin 7);
  * the SCOPE GUARDS hold — the corroboration bar still runs FIRST and still
    decides what is worth recording, and the other five reject codes are
    untouched (pin 8);
  * the visibility seam: the stop's reader turns a recorded report into the
    lines it prints, and never raises on a report that is missing, malformed or
    pre-L-1 (pin 9);
  * the arming: the CLI overlay and `config/template.yaml` both carry
    `record`, while the CODE default stays `reject` (pin 10).

HOUSE RULE, and a live-batch one while g20261001-1 runs: every test here is
hermetic — tmp roots only, no network, no driver, and nothing under `out/` is
read or written by any pin (`build_config` is handed explicit tmp roots).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from gen import cli, orchestrator, s3_verify
from gen.config import REPO_ROOT

TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"
TEMPLATE_PATH = REPO_ROOT / "config" / "template.yaml"

KNOB = "deception_action"
ADVISORIES = "deception_advisories"
REJECT, RECORD = "reject", "record"
#: Overlay keys that contracts AFTER L-1 added, subtracted by name from this
#: file's key-count pin so the pin keeps measuring L-1's own delta. Contract
#: E-2 (2026-10-05) is the first entry: `orchestrator.stage_fail_park` and
#: `orchestrator.respec_feasibility`, the park-the-treadmill and
#: skip-the-futile-respec armings.
#:
#: PIN UPDATE, 2026-10-06 (contract Q-1 §4, a licensed overlay-pin edit).
#: `verifier.term_dispute_action` joins by name for the same reason: it is
#: THIS knob's own ruling one finding class over — an `undeclared-term` finding
#: the blind audit itself double-named rides the report instead of the verdict —
#: and L-1's claim is about L-1's seventh key, not about the overlay's size.
LATER_CONTRACT_OVERLAY_KEYS = frozenset({
    "orchestrator.stage_fail_park",
    "orchestrator.respec_feasibility",
    "verifier.term_dispute_action",
})
VERDICT_PASS, VERDICT_REJECT = "pass", "reject"
MODE_FULL, MODE_DRY = "full", "dry-run"

# Two distinct catalog levers, and the terms the diff is built from.
# PIN UPDATE, contract E-1 (2026-10-05): Y was `"mimic"`, which the re-grounded
# catalog no longer lists as a lever of its own — it is a SPELLING of §7.1 and
# folds onto `look-alike`. Y is that lever itself now; the pin still stands on
# two DISTINCT catalog levers, which is all this file's fixtures ask of them.
LEVER_X = "decoy"
LEVER_Y = "look-alike"
CLEAN_TERM = "move.grid"
EXTRA_TERM = "info.legend"

GAME_ID = "l1-leniency-synthetic"
SYNTHETIC_NOTE = "synthetic fixture"


# --------------------------------------------------------------------------
# synthetic verifier inputs (no live run is quoted anywhere in this file)
# --------------------------------------------------------------------------


def _evidence() -> list[dict]:
    return [{"path": "game.py", "line": 10, "note": SYNTHETIC_NOTE}]


def _claims(terms: tuple[str, ...], levers: tuple[str, ...]) -> dict:
    return {
        "terms": [{"term": term, "reachable": True, "evidence": _evidence()} for term in terms],
        "dead_code": [],
        "deceptions": [{"lever": lever, "evidence": _evidence()} for lever in levers],
        "enforcement": [],
        "notes": SYNTHETIC_NOTE,
    }


def _spec(terms: tuple[str, ...]) -> dict:
    return {"game": {"terms": list(terms), "knobs": {"deceptions": []}}}


def _agent(claims: dict) -> dict:
    return {
        "session_id": "synthetic-1",
        "model": "synthetic",
        "usd": 0.0,
        "tokens_in": 1,
        "tokens_out": 1,
        "wall_s": 0.0,
        "staged_copy_verified": True,
        "claims": claims,
    }


def _cfg(action: object = None, **verifier: object) -> dict:
    """The minimum `assemble_report` reads, with the knob set or absent."""
    cfg: dict = {"duckwm_docs": str(REPO_ROOT / "canon"), "verifier": dict(verifier)}
    if action is not None:
        cfg["verifier"][KNOB] = action
    return cfg


@pytest.fixture(scope="session")
def cap() -> object:
    """A real FrameCapture off the checked-in toy worker (the b7 harness shape)."""
    game_cls, solver_cls = s3_verify.load_worker_classes(TOY_WORKER)
    return s3_verify.capture(game_cls, solver_cls)


@pytest.fixture(autouse=True)
def _fixture_wall() -> None:
    """The vocabulary this file's synthetic inputs stand on, checked once."""
    for lever in (LEVER_X, LEVER_Y):
        assert lever in s3_verify.DECEPTION_CATALOG, (
            f"fixture wall: {lever!r} left the signed deception catalog"
        )


class _Slot:
    """One planted slot: a worker dir, and as many FULL verify rounds as wanted.

    A round is driven through `assemble_report`, which contract L-1 names as
    the seam (it is the one place the run's CONFIG, its diff and the worker are
    all in hand), and the diff is built on the PURE path by `compute_diff`.
    """

    def __init__(self, root: Path, cap: object) -> None:
        import shutil

        self.root = root
        self.worker = root / "slot-1"
        shutil.copytree(TOY_WORKER, self.worker, ignore=shutil.ignore_patterns("__pycache__"))
        self.frames_path = root / s3_verify.FRAMES_NAME
        self.frames_path.write_text("{}", encoding="utf-8")
        self._cap = cap

    def run(self, cfg: dict, *, levers: tuple[str, ...] = (),
            undeclared_terms: tuple[str, ...] = ()) -> dict:
        claims = _claims((CLEAN_TERM, *undeclared_terms), levers)
        diff = s3_verify.compute_diff(claims, _spec((CLEAN_TERM,)))
        return s3_verify.assemble_report(
            game_id=GAME_ID,
            worker=self.worker,
            mode=MODE_FULL,
            cfg=cfg,
            cap=self._cap,
            checks=[],
            frames_path=self.frames_path,
            agent=_agent(claims),
            diff=diff,
            spec_hash=None,
        )


@pytest.fixture
def slot(tmp_path: Path, cap: object) -> _Slot:
    return _Slot(tmp_path, cap)


def _codes(rows: list[dict]) -> list[str]:
    return [row["code"] for row in rows]


def _comparable(report: dict) -> dict:
    """A report with the two per-run values that are never equal stripped."""
    out = copy.deepcopy(report)
    out.pop("worker", None)
    return out


# --------------------------------------------------------------------------
# PIN 1-2 — the default is today's bytes
# --------------------------------------------------------------------------


def test_pin1_absent_knob_still_rejects_on_a_lever(slot: _Slot) -> None:
    report = slot.run(_cfg(), levers=(LEVER_X,))
    assert report["verdict"] == VERDICT_REJECT
    assert _codes(report["reject_reasons"]) == [s3_verify.REJECT_UNDECLARED_DECEPTION], (
        "L-1 §1: an absent knob is the pre-contract behaviour, byte for byte — the lever "
        f"must still reject. Got {report['reject_reasons']!r}"
    )
    assert report["reject_reasons"][0]["lever"] == LEVER_X
    assert report[ADVISORIES] == [], (
        f"L-1 §2: under `reject` the report carries an EMPTY {ADVISORIES!r}, so a reader "
        f"never has to know the batch's knob to read the answer; got {report[ADVISORIES]!r}"
    )


def test_pin2_explicit_reject_is_the_absent_knob(tmp_path: Path, cap: object) -> None:
    """Two planted slots, one diff, two spellings of the default: one report."""
    absent = _Slot(tmp_path / "absent", cap).run(_cfg(), levers=(LEVER_X,))
    explicit = _Slot(tmp_path / "explicit", cap).run(_cfg(REJECT), levers=(LEVER_X,))
    assert _comparable(absent) == _comparable(explicit), (
        "L-1 §1: `deception_action: reject` must be the absent key, byte for byte"
    )


# --------------------------------------------------------------------------
# PIN 3-5 — `record` moves the row and nothing else
# --------------------------------------------------------------------------


def test_pin3_record_turns_a_lever_only_report_into_a_pass(tmp_path: Path, cap: object) -> None:
    rejected = _Slot(tmp_path / "default", cap).run(_cfg(), levers=(LEVER_X,))
    recorded = _Slot(tmp_path / "record", cap).run(_cfg(RECORD), levers=(LEVER_X,))

    assert recorded["verdict"] == VERDICT_PASS, (
        "L-1 §2: a report whose only findings are levers is a PASS under `record`"
    )
    assert recorded["reject_reasons"] == []
    assert recorded[ADVISORIES] == rejected["reject_reasons"], (
        "L-1 §2: the SAME rows ride the advisories — same lever, same detail, same order. "
        f"reject mode: {rejected['reject_reasons']!r}; record mode: {recorded[ADVISORIES]!r}"
    )
    # …and the finding itself is untouched upstream: the diff still names it.
    assert recorded["diff"]["undeclared_deceptions"] == [LEVER_X], (
        "L-1 §5: the knob moves a ROW, it does not edit the audit's diff"
    )


def test_pin3b_every_lever_rides_and_the_order_is_the_decisions_order(
    tmp_path: Path, cap: object
) -> None:
    rejected = _Slot(tmp_path / "default", cap).run(_cfg(), levers=(LEVER_X, LEVER_Y))
    recorded = _Slot(tmp_path / "record", cap).run(_cfg(RECORD), levers=(LEVER_X, LEVER_Y))
    assert len(recorded[ADVISORIES]) == 2, recorded[ADVISORIES]
    assert recorded[ADVISORIES] == rejected["reject_reasons"]
    assert recorded["verdict"] == VERDICT_PASS and recorded["reject_reasons"] == []


def test_pin4_a_term_finding_beside_a_lever_still_rejects_alone(slot: _Slot) -> None:
    report = slot.run(_cfg(RECORD), levers=(LEVER_X,), undeclared_terms=(EXTRA_TERM,))
    assert report["verdict"] == VERDICT_REJECT
    assert _codes(report["reject_reasons"]) == [s3_verify.REJECT_UNDECLARED_TERM], (
        "L-1 §2+§5: the lever rides as an advisory and the TERM still rejects, alone. "
        f"Got {report['reject_reasons']!r}"
    )
    assert report["reject_reasons"][0]["term"] == EXTRA_TERM
    assert _codes(report[ADVISORIES]) == [s3_verify.REJECT_UNDECLARED_DECEPTION]
    assert report[ADVISORIES][0]["lever"] == LEVER_X


def test_pin5_reconciliation_reads_only_the_term(slot: _Slot, tmp_path: Path) -> None:
    """The orchestrator's reconciliation reads `reject_reasons` OFF THE REPORT.

    So "never reach reconciliation" is a fact about the file: what is not in
    `reject_reasons` is not in `_verifier_reject_reasons`, which is the only
    thing the amendment pass ever reads.
    """
    mixed = slot.run(_cfg(RECORD), levers=(LEVER_X,), undeclared_terms=(EXTRA_TERM,))
    path = tmp_path / "mixed.verifier-report.json"
    s3_verify.write_report(mixed, path)

    class _Ctx:
        verifier_report_path = path

    reasons = orchestrator._verifier_reject_reasons(_Ctx())
    assert reasons is not None and _codes(reasons) == [s3_verify.REJECT_UNDECLARED_TERM], (
        f"L-1 §2: reconciliation must see ONLY the term; it saw {reasons!r}"
    )

    lever_only = _Slot(tmp_path / "lever-only", slot._cap).run(_cfg(RECORD), levers=(LEVER_X,))
    pass_path = tmp_path / "pass.verifier-report.json"
    s3_verify.write_report(lever_only, pass_path)

    class _PassCtx:
        verifier_report_path = pass_path

    assert orchestrator._verifier_reject_reasons(_PassCtx()) is None, (
        "L-1 §2: a lever-only report is a PASS, so there is no residual to reconcile at all"
    )


# --------------------------------------------------------------------------
# PIN 6 — the knob is read once, and loud
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value", ["lenient", "RECORD", "Record", "", "off", True, False, None, 1, ["record"]]
)
def test_pin6_a_value_outside_the_two_signed_words_is_loud(value: object) -> None:
    with pytest.raises(ValueError) as excinfo:
        s3_verify._deception_action({"duckwm_docs": ".", "verifier": {KNOB: value}})
    message = str(excinfo.value)
    for needle in (f"verifier.{KNOB}", REJECT, RECORD):
        assert needle in message, f"the refusal must name {needle!r}: {message!r}"


def test_pin6b_the_two_signed_words_and_the_absent_key() -> None:
    assert s3_verify._deception_action({}) == REJECT
    assert s3_verify._deception_action({"verifier": {}}) == REJECT
    assert s3_verify._deception_action({"verifier": "not-a-mapping"}) == REJECT
    assert s3_verify._deception_action(_cfg(REJECT)) == REJECT
    assert s3_verify._deception_action(_cfg(RECORD)) == RECORD


def test_pin6c_a_bad_knob_stops_a_dry_run_too(tmp_path: Path, cap: object) -> None:
    """No diff, nothing to judge — and still loud, before anything is written.

    A dry run writes a report, and a config error must not be discovered by the
    first FULL round three stages later.
    """
    frames = tmp_path / s3_verify.FRAMES_NAME
    frames.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match=KNOB):
        s3_verify.assemble_report(
            game_id=GAME_ID, worker=TOY_WORKER, mode=MODE_DRY, cfg=_cfg("lenient"),
            cap=cap, checks=[], frames_path=frames, agent=None, diff=None, spec_hash=None,
        )


def test_pin6d_a_dry_run_report_carries_the_empty_list(tmp_path: Path, cap: object) -> None:
    frames = tmp_path / s3_verify.FRAMES_NAME
    frames.write_text("{}", encoding="utf-8")
    report = s3_verify.assemble_report(
        game_id=GAME_ID, worker=TOY_WORKER, mode=MODE_DRY, cfg=_cfg(RECORD),
        cap=cap, checks=[], frames_path=frames, agent=None, diff=None, spec_hash=None,
    )
    assert report[ADVISORIES] == [], "a run with no diff has nothing to record, and says so"
    assert report["verdict"] == VERDICT_PASS


# --------------------------------------------------------------------------
# PIN 7 — the schema is ADDITIVE
# --------------------------------------------------------------------------


def test_pin7_the_key_is_optional_not_required(slot: _Slot) -> None:
    assert ADVISORIES in s3_verify.OPTIONAL_REPORT_KEYS, (
        f"{ADVISORIES!r} must be in OPTIONAL_REPORT_KEYS: `validate_report` reads reports "
        "off disk that were written before this contract existed"
    )
    assert ADVISORIES not in s3_verify.REPORT_KEYS, (
        "a REQUIRED key would retro-invalidate every b7.1 report already on disk"
    )
    assert s3_verify.SCHEMA_VERSION == "b7.1", (
        "L-1 §2: an additive, optional key is NOT a schema bump — this file's own "
        "convention (`exempted`, `uncorroborated_levers`, `lookalikes`, `term_sites`)"
    )
    # A pre-L-1 report: the key removed, everything else untouched.
    legacy = slot.run(_cfg(), levers=(LEVER_X,))
    legacy.pop(ADVISORIES)
    s3_verify.validate_report(legacy)


def test_pin7b_an_advisory_row_is_validated_like_a_reason(slot: _Slot) -> None:
    report = slot.run(_cfg(RECORD), levers=(LEVER_X,))
    s3_verify.validate_report(report)  # the pass/advisory combination is legal

    wrong_code = copy.deepcopy(report)
    wrong_code[ADVISORIES][0]["code"] = s3_verify.REJECT_UNDECLARED_TERM
    with pytest.raises(ValueError, match=s3_verify.REJECT_UNDECLARED_DECEPTION):
        s3_verify.validate_report(wrong_code)

    no_detail = copy.deepcopy(report)
    no_detail[ADVISORIES][0].pop("detail")
    with pytest.raises(ValueError):
        s3_verify.validate_report(no_detail)

    not_a_list = copy.deepcopy(report)
    not_a_list[ADVISORIES] = {"lever": LEVER_X}
    with pytest.raises(ValueError):
        s3_verify.validate_report(not_a_list)


def test_pin7c_a_pass_with_advisories_still_has_no_reject_reasons(slot: _Slot) -> None:
    """The frozen invariant — "a reject states why and a pass states nothing" —
    is about `reject_reasons`, and the advisories do not touch it."""
    report = slot.run(_cfg(RECORD), levers=(LEVER_X,))
    assert report["verdict"] == VERDICT_PASS and report["reject_reasons"] == []
    assert report[ADVISORIES], "fixture wall: this report should carry an advisory"
    s3_verify.validate_report(report)


# --------------------------------------------------------------------------
# PIN 8 — the scope guards
# --------------------------------------------------------------------------


def test_pin8_the_corroboration_bar_still_runs_first(tmp_path: Path, cap: object) -> None:
    """`record` is about what a SURVIVING finding may decide.

    With `lever_corroboration` armed, a FIRST sighting is demoted upstream into
    `uncorroborated_levers` and never becomes a row at all — so it is not an
    advisory either, and the second sighting is the one that gets recorded.
    """
    cfg = _cfg(RECORD, lever_corroboration=True)
    plot = _Slot(tmp_path / "slot", cap)
    first = plot.run(cfg, levers=(LEVER_X,))
    assert first["verdict"] == VERDICT_PASS
    assert first[ADVISORIES] == [], (
        "L-1 §Evidence: the corroboration bar is UPSTREAM of the append site and is left "
        f"untouched — a first sighting records as uncorroborated, not as an advisory: "
        f"{first[ADVISORIES]!r}"
    )
    assert [row["lever"] for row in first["diff"][s3_verify.UNCORROBORATED_KEY]] == [LEVER_X]

    second = plot.run(cfg, levers=(LEVER_X,))
    assert second["verdict"] == VERDICT_PASS, "the corroborated lever must not reject under record"
    assert _codes(second[ADVISORIES]) == [s3_verify.REJECT_UNDECLARED_DECEPTION], (
        "a corroborated lever is exactly what the ruling records: "
        f"{second[ADVISORIES]!r}"
    )


def test_pin8b_the_other_reject_codes_are_untouched() -> None:
    assert s3_verify.REJECT_CODES == (
        "forbidden-static",
        "undeclared-deception",
        "dead-spec-term",
        "undeclared-term",
        "unreachable-declared-mechanic",
        "solver-quality",
    ), "L-1 §5: the frozen six are not renegotiated by this contract"
    assert s3_verify.DECEPTION_ACTIONS == (REJECT, RECORD)


def test_pin8c_record_never_moves_a_non_lever_row() -> None:
    reasons = [
        {"code": s3_verify.REJECT_DEAD_SPEC_TERM, "detail": "d", "term": "a.b"},
        {"code": s3_verify.REJECT_UNDECLARED_DECEPTION, "detail": "x", "lever": LEVER_X},
        {"code": s3_verify.REJECT_SOLVER_QUALITY, "detail": "s", "route": "solver-only"},
    ]
    verdict, kept, advisories = s3_verify._apply_deception_action(
        VERDICT_REJECT, copy.deepcopy(reasons), RECORD
    )
    assert verdict == VERDICT_REJECT
    assert kept == [reasons[0], reasons[2]]
    assert advisories == [reasons[1]]

    unchanged = s3_verify._apply_deception_action(VERDICT_REJECT, copy.deepcopy(reasons), REJECT)
    assert unchanged == (VERDICT_REJECT, reasons, [])

    with pytest.raises(ValueError):
        s3_verify._apply_deception_action(VERDICT_REJECT, [], "lenient")


# --------------------------------------------------------------------------
# PIN 9 — the stop prints what it recorded
# --------------------------------------------------------------------------


def test_pin9_the_stop_reader_returns_one_line_per_advisory(slot: _Slot) -> None:
    report = slot.run(_cfg(RECORD), levers=(LEVER_X, LEVER_Y))
    path = slot.worker.with_name(slot.worker.name + orchestrator.VERIFIER_REPORT_SUFFIX)
    s3_verify.write_report(report, path)

    lines = orchestrator._deception_advisories(str(slot.worker))
    assert lines == [row["detail"] for row in report[ADVISORIES]], (
        f"L-1 §3: the stop prints the advisories it recorded; got {lines!r}"
    )


def test_pin9b_the_stop_reader_never_raises(tmp_path: Path, slot: _Slot) -> None:
    assert orchestrator._deception_advisories(None) == []
    assert orchestrator._deception_advisories(str(tmp_path / "nowhere")) == []

    path = slot.worker.with_name(slot.worker.name + orchestrator.VERIFIER_REPORT_SUFFIX)
    for junk in ("", "{", '{"deception_advisories": "not a list"}', '{"verdict": "pass"}', "[]"):
        path.write_text(junk, encoding="utf-8")
        assert orchestrator._deception_advisories(str(slot.worker)) == [], junk


def test_pin9c_a_pre_l1_report_yields_no_lines(slot: _Slot) -> None:
    report = slot.run(_cfg(), levers=(LEVER_X,))
    report.pop(ADVISORIES)
    path = slot.worker.with_name(slot.worker.name + orchestrator.VERIFIER_REPORT_SUFFIX)
    s3_verify.write_report(report, path)
    assert orchestrator._deception_advisories(str(slot.worker)) == []


# --------------------------------------------------------------------------
# PIN 10 — the arming (the template and the overlay), the default in code
# --------------------------------------------------------------------------


def test_pin10_the_template_arms_record() -> None:
    tree = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert tree["verifier"][KNOB] == RECORD, (
        "L-1 §7 DECISION: the template ARMS `record` (the armed-recommended file)"
    )
    assert s3_verify._deception_action(tree) == RECORD, "and the reader accepts the template"


def test_pin10b_the_overlay_carries_the_seventh_key() -> None:
    assert cli.AUTONOMY_OVERLAY["verifier"][KNOB] == RECORD, (
        f"L-1 §4: AUTONOMY_OVERLAY gains verifier.{KNOB}: {RECORD!r}"
    )
    flat = {f"{block}.{key}" for block, keys in cli.AUTONOMY_OVERLAY.items() for key in keys}
    # PIN UPDATE, 2026-10-05 (contract E-2 §4, a licensed overlay-pin edit).
    # L-1's claim is "the overlay is SEVEN keys with mine as the seventh", and
    # that is what is still asserted — the keys E-2 added afterwards are
    # subtracted by name rather than the count being bumped, so this pin cannot
    # be satisfied by a later contract quietly adding an eighth key of its own.
    assert len(flat - LATER_CONTRACT_OVERLAY_KEYS) == 7, (
        f"L-1 §4: the overlay is seven keys now (plus {sorted(LATER_CONTRACT_OVERLAY_KEYS)}, "
        f"added by later contracts), got {sorted(flat)}"
    )


def test_pin10c_the_materialized_config_carries_record(tmp_path: Path) -> None:
    """The CLI's own seam, with tmp roots: nothing under `out/` is read."""
    configs, batches = tmp_path / "config", tmp_path / "batches"
    configs.mkdir()
    batches.mkdir()
    cfg = cli.build_config(driver="claude", games=1, seed=99,
                           config_dir=configs, batches_root=batches)
    assert cfg["verifier"][KNOB] == RECORD
    assert s3_verify._deception_action(cfg) == RECORD
    # and the materialization is still a dict nobody wrote to disk
    assert not list(configs.iterdir()) and not list(batches.iterdir())


def test_pin10d_the_code_default_is_still_reject() -> None:
    """The house rule: a config that says nothing gets the stage it had."""
    assert s3_verify.DECEPTION_ACTION_REJECT == REJECT
    assert s3_verify._deception_action({"verifier": {"reject_cap": 1}}) == REJECT


def test_pin10e_the_historical_batch_configs_are_untouched() -> None:
    """The 2026-10-01 precedent (the timeout arming): template only.

    A batch config that already ran must keep reading as the run it was, so the
    knob appears in none of them — and every one of them therefore keeps the
    pre-L-1 behaviour exactly.
    """
    # LEAD UPDATE 2026-10-06: what this pin guards against is SILENT
    # retro-arming. A dated RECORDED OPERATOR AMENDMENT on a batch being
    # RESUMED is the sanctioned other thing — the 2026-10-01 seamlock rescue's
    # pattern, applied to b004-validation and b005r2-auto for the revivals —
    # so a config carrying the knob passes IFF its raw text also carries the
    # amendment marker beside it. A knob with no marker is still the silent
    # arming this pin exists to refuse.
    armed = []
    for path in sorted((REPO_ROOT / "config").glob("*.yaml")):
        if path.name == "template.yaml":
            continue
        raw = path.read_text(encoding="utf-8")
        tree = yaml.safe_load(raw)
        verifier = (tree or {}).get("verifier")
        if (isinstance(verifier, dict) and KNOB in verifier
                and "RECORDED OPERATOR AMENDMENT" not in raw):
            armed.append(path.name)
    assert not armed, (
        f"these historical batch configs gained {KNOB!r} with NO recorded-amendment "
        f"marker: {armed} — a config of record must not be retro-armed silently "
        "(DECISIONS.md, 2026-10-01: 'template only — historical/live batch configs "
        "untouched'; the recorded-amendment path is the seamlock precedent)"
    )


def test_pin10f_the_live_report_shape_is_json_round_trippable(slot: _Slot,
                                                              tmp_path: Path) -> None:
    """What S6 and the review read is a FILE: the advisories survive it."""
    report = slot.run(_cfg(RECORD), levers=(LEVER_X,))
    path = tmp_path / "round-trip.verifier-report.json"
    s3_verify.write_report(report, path)
    back = json.loads(path.read_text(encoding="utf-8"))
    assert back[ADVISORIES] == report[ADVISORIES]
    s3_verify.validate_report(back)
