"""b002 lever corroboration + the info.deception exemption.

Written from the frozen corroboration contract ALONE (Agent B, independent test
writer): `gen/s3_verify.py` was never read, nor any diff of it, nor the
implementer's report.  The module is imported and INTROSPECTED at runtime, and
every renegotiable spelling below (the sidecar's file name, its entry field
names, the shape of a recorded entry) is discovered from what the code actually
produces rather than retyped from the contract.  Nothing here quotes a live
run: every claim, spec, lever, worker and verdict below is synthetic or a copy
of a checked-in fixture, and no test writes into `gen/tests/`.

WHY THE KNOB EXISTS (stated anonymously, as the contract requires)

Measured across two batches of games: undeclared-lever findings ROTATE names
round to round — a keyword almost never repeats in consecutive audits — and one
meta term was sworn dead in two consecutive rounds and reachable in the third,
on near-identical code, while a human who played the game those findings kept
rejecting passed it.  A REAL deception is code: a blind audit that sees it once
sees it every round.  So STABILITY across two independent blind sessions is the
honest reject bar for the lever class, and a single sighting is a warning.
This is R4's per-class policy pulled forward as a per-batch knob, which is why
canon behavior stays the DEFAULT and pin 1 exists: a run that does not opt in
must be the old run, byte for byte.

THE EIGHT PINS, in the contract's order

1. knob OFF (absent or false) — an undeclared lever still rejects, twice
   running, identically; `compute_diff` stays pure;
2. cold start, knob ON — first sighting warns: pass, recorded, history begins;
3. second sighting, knob ON — the same lever next round REJECTS;
4. rotation, knob ON — a different lever next round still passes, and the
   sidecar carries both rounds;
5. a DECLARED lever, detected repeatedly — never a finding, never recorded as
   uncorroborated, but in every sidecar entry (history records detection, not
   verdicts);
6. composition — an exempt-term finding and a first-sighting lever in one
   report: pass, both recorded, `_validate_diff` accepts;
7. the b002 config carries both ruling keys;
8. bad states are loud — a non-bool knob and an unparsable sidecar both raise.

THE SEAM.  The contract places the corroboration pass at the seam the exemption
pass used (`assemble_report` / `decide_verdict`) and keeps `compute_diff` pure,
so these pins drive a FULL `assemble_report` over a planted worker dir — the
one place that has the config (the knob), the worker (the sidecar's home) and
the diff (the round's findings) at once.  If a pin below fails because the pass
lives somewhere else entirely, that is a contract question for lead review, not
a licence to weaken the pin.
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

from gen import s3_verify
from gen.config import REPO_ROOT, load_config

B002_CONFIG = "config/b002-triple.yaml"
TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"

# Contract wording, not code names: the knob, and the diff list a warned lever
# is recorded in.  Both are spelled in the contract, so they are pinned; what
# the contract leaves renegotiable (entry fields, file name, note wording,
# timestamp format) is discovered below instead.
KNOB = "lever_corroboration"
UNCORROBORATED_KEY = "uncorroborated_levers"
EXEMPTED_KEY = "exempted"

VERDICT_PASS, VERDICT_REJECT = "pass", "reject"
MODE_FULL = "full"

# The ruling's own values: budget.cap (already signed) plus the meta term that
# fired dead/dead/reachable across three consecutive audits.
RULING_EXEMPT_TERMS = ["budget.cap", "info.deception"]
RULING_DATE = "2026-09-24"
EXEMPT_TERM = "info.deception"
CLEAN_TERM = "move.grid"

# Two distinct catalog levers: X is the one that repeats, Y is the rotation.
# PIN UPDATE, contract E-1 (2026-10-05): Y was `"mimic"`, which is no longer a
# lever of its own — it is a SPELLING of §7.1 that now folds onto `look-alike`,
# so the catalog it is checked against no longer lists it. Y is that lever
# itself now. The pin's intent is untouched: two DISTINCT catalog levers, one
# repeating and one rotating, which is what the corroboration bar is about.
LEVER_X = "decoy"
LEVER_Y = "look-alike"

GAME_ID = "b002-corroboration-synthetic"
SYNTHETIC_NOTE = "synthetic fixture"


# --------------------------------------------------------------------------
# synthetic verifier inputs
# --------------------------------------------------------------------------


def _evidence() -> list[dict]:
    return [{"path": "game.py", "line": 10, "note": SYNTHETIC_NOTE}]


def _claims(terms: tuple[tuple[str, bool], ...], levers: tuple[str, ...]) -> dict:
    """A minimal valid claims block: (term, reachable) pairs plus levers."""
    return {
        "terms": [
            {"term": term, "reachable": reachable, "evidence": _evidence()}
            for term, reachable in terms
        ],
        "dead_code": [],
        "deceptions": [{"lever": lever, "evidence": _evidence()} for lever in levers],
        "enforcement": [],
        "notes": SYNTHETIC_NOTE,
    }


def _spec(terms: tuple[str, ...], levers: tuple[str, ...]) -> dict:
    return {"game": {"terms": list(terms), "knobs": {"deceptions": list(levers)}}}


def _cfg(base: dict, knob: object = None, *, drop: bool = False) -> dict:
    """The b002 config with the corroboration knob forced on, off or absent."""
    cfg = copy.deepcopy(base)
    cfg.setdefault("verifier", {})
    if drop:
        cfg["verifier"].pop(KNOB, None)
    else:
        cfg["verifier"][KNOB] = knob
    return cfg


# --------------------------------------------------------------------------
# the report-assembly seam, over a planted worker dir
# --------------------------------------------------------------------------


class _Slot:
    """One planted slot: a worker dir, and as many FULL verify rounds as a test
    wants to drive through it.  Rounds share the slot, which is the whole point
    — the sidecar is per-slot and accrues across rounds."""

    def __init__(self, root: Path, cap: object) -> None:
        self.root = root
        self.worker = root / "slot-1"
        shutil.copytree(TOY_WORKER, self.worker, ignore=shutil.ignore_patterns("__pycache__"))
        self.frames_path = root / s3_verify.FRAMES_NAME
        self.frames_path.write_text("{}", encoding="utf-8")
        self._cap = cap
        self.rounds = 0

    def run(
        self,
        cfg: dict,
        *,
        levers: tuple[str, ...] = (),
        declared_levers: tuple[str, ...] = (),
        extra_terms: tuple[str, ...] = (),
        exempt: tuple[str, ...] = (),
    ) -> dict:
        """One audit round: build the diff on the pure path, then assemble."""
        self.rounds += 1
        claims = _claims(((CLEAN_TERM, True), *((t, True) for t in extra_terms)), levers)
        spec = _spec((CLEAN_TERM,), declared_levers)
        if exempt:
            diff = s3_verify.compute_diff(claims, spec, exempt_terms=tuple(exempt))
        else:  # knob off for the exemption pass: prove its default too
            diff = s3_verify.compute_diff(claims, spec)
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
        return s3_verify.assemble_report(
            game_id=GAME_ID,
            worker=self.worker,
            mode=MODE_FULL,
            cfg=cfg,
            cap=self._cap,
            checks=[],
            frames_path=self.frames_path,
            agent=agent,
            diff=diff,
            spec_hash=None,
        )

    # -- the sidecar, discovered rather than spelled ------------------------

    def history_files(self) -> list[Path]:
        """Every file under the slot that looks like the lever history.

        Searched across the whole slot (not just beside the worker) so that a
        sidecar written INSIDE the worker dir is reported as a placement
        failure instead of as a missing file.
        """
        # LEAD FIX (C-3 close): match the LEVER suffix, not the substring
        # "history" — contract C-3 writes a second, term-direction sidecar
        # (`<worker>.term-history.json`) beside this one, and this harness's
        # job is the LEVER history's placement and uniqueness, which both
        # still hold. The suffix comes from the module, never retyped.
        from gen.s3_verify import LEVER_HISTORY_SUFFIX
        return sorted(
            path
            for path in self.root.rglob("*")
            if path.is_file() and path.name.endswith(LEVER_HISTORY_SUFFIX)
        )

    def sidecar(self) -> Path:
        found = self.history_files()
        assert len(found) == 1, (
            "expected exactly ONE lever-history sidecar after a full verify round, found "
            f"{[str(p.relative_to(self.root)) for p in found]} — the contract writes one "
            "per-slot `<worker>.lever-history.json` per slot, on every FULL run (knob on "
            "OR off, so that a later knob-on has real history to read)"
        )
        path = found[0]
        assert path.parent == self.root, (
            f"the sidecar landed at {path.relative_to(self.root)} — the contract puts it "
            "BESIDE the worker (the suffix convention every stage artifact uses), not "
            "inside the edit scope the worker session owns"
        )
        assert path.name.startswith(self.worker.name) and path.name.endswith(".json"), (
            f"sidecar {path.name!r} does not follow the `<worker-dir-name><suffix>.json` "
            f"convention for worker {self.worker.name!r} that frames/report/staged use"
        )
        return path

    def entries(self) -> list:
        return _history_entries(self.sidecar())


def _history_entries(path: Path) -> list:
    """The sidecar's entries, in append order — container shape discovered."""
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        lines = [line for line in text.splitlines() if line.strip()]
        try:  # the other append-only shape: one JSON entry per line
            return [json.loads(line) for line in lines]
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"the sidecar at {path.name} is neither a JSON document nor JSON lines "
                f"({exc}) — the contract requires pipeline state that parses"
            ) from exc
    if isinstance(data, list):
        return list(data)
    if isinstance(data, Mapping):
        lists = [value for value in data.values() if isinstance(value, list)]
        assert len(lists) == 1, (
            f"the sidecar at {path.name} is a mapping with {len(lists)} list fields "
            f"(keys {sorted(data)}) — cannot tell which one holds the appended rounds"
        )
        return list(lists[0])
    raise AssertionError(
        f"the sidecar at {path.name} parsed to {type(data).__name__}, which holds no "
        "per-round entries; the contract appends one entry per audit round"
    )


def _detected(entry: object) -> list[str]:
    """The lever keywords an entry records — field name discovered."""
    assert isinstance(entry, Mapping), (
        f"a history entry is {type(entry).__name__}, not a mapping — the contract's "
        "entry is {ts, detected}, so a round's detections stay addressable"
    )
    named = [
        value
        for key, value in entry.items()
        if "detect" in str(key).lower() and isinstance(value, list)
    ]
    candidates = named or [
        value
        for value in entry.values()
        if isinstance(value, list) and all(isinstance(item, str) for item in value)
    ]
    assert len(candidates) == 1, (
        f"cannot locate the detected-levers list in a history entry with fields "
        f"{sorted(entry)}: found {len(candidates)} candidate string lists"
    )
    return list(candidates[0])


def _stamp(entry: Mapping) -> object:
    """The entry's timestamp — name and format both renegotiable, so only its
    presence and non-emptiness are pinned."""
    scalars = [
        value
        for value in entry.values()
        if isinstance(value, (str, int, float)) and not isinstance(value, bool)
    ]
    assert scalars, (
        f"a history entry {sorted(entry)} carries no timestamp field — an append-only "
        "log whose rounds are not stamped cannot be read back as history"
    )
    non_empty = [value for value in scalars if str(value).strip()]
    assert non_empty, f"the history entry's timestamp field(s) are empty: {sorted(entry)}"
    return non_empty[0]


# --------------------------------------------------------------------------
# recorded warnings, discovered rather than spelled
# --------------------------------------------------------------------------


def _uncorroborated(diff: Mapping) -> list:
    assert UNCORROBORATED_KEY in diff, (
        f"the report's diff carries no {UNCORROBORATED_KEY!r} list (keys: {sorted(diff)}) "
        "— with the knob on, a first-sighting lever finding moves OUT of the reject "
        "reasons and INTO that list; data preserved, reject surface narrowed"
    )
    value = diff[UNCORROBORATED_KEY]
    assert isinstance(value, list), f"{UNCORROBORATED_KEY} is {type(value).__name__}, not a list"
    return value


def _lever_of(entry: object) -> str:
    """The keyword a recorded warning preserves — field name discovered."""
    assert isinstance(entry, Mapping), (
        f"a {UNCORROBORATED_KEY} entry is {type(entry).__name__}, not a mapping — the "
        f"contract follows the {EXEMPTED_KEY!r} pattern exactly ({{lever, note}}), so a "
        "later pass can read both the keyword and why it was not a reject"
    )
    levers = [
        value
        for value in entry.values()
        if isinstance(value, str) and value in s3_verify.DECEPTION_CATALOG
    ]
    assert len(levers) == 1, (
        f"a {UNCORROBORATED_KEY} entry with fields {sorted(entry)} carries {len(levers)} "
        "signed catalog keywords; exactly one (the lever) is expected"
    )
    return levers[0]


def _note_of(entry: Mapping) -> str:
    notes = [
        value
        for value in entry.values()
        if isinstance(value, str) and value not in s3_verify.DECEPTION_CATALOG and value.strip()
    ]
    assert notes, (
        f"a {UNCORROBORATED_KEY} entry {sorted(entry)} records the lever but no note — the "
        "contract's entry says WHY it was not a reject (first sighting); the wording is "
        "renegotiable, its presence is not"
    )
    return notes[0]


def _levers_recorded(report: Mapping) -> list[str]:
    return [_lever_of(entry) for entry in _uncorroborated(report["diff"])]


def _reason_codes(report: Mapping) -> list[str]:
    return [reason["code"] for reason in report["reject_reasons"]]


def _loud(exc: BaseException, where: str) -> None:
    """A bad state must raise a VALIDATION error, not crash on the way past."""
    assert isinstance(exc, (ValueError, TypeError, RuntimeError)), (
        f"{where} raised {type(exc).__name__}: {exc}. The contract requires a loud, "
        "deliberate rejection (the exemption knob's precedent raises ValueError), not an "
        "incidental crash deeper in the pass"
    )


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def cap() -> object:
    """A real FrameCapture from the checked-in toy worker (b7-style staging)."""
    game_cls, solver_cls = s3_verify.load_worker_classes(TOY_WORKER)
    return s3_verify.capture(game_cls, solver_cls)


@pytest.fixture(scope="session")
def base_cfg() -> dict:
    cfg = load_config(B002_CONFIG)
    assert MODE_FULL in s3_verify.MODES, f"fixture wall: {MODE_FULL!r} is no longer a mode"
    for lever in (LEVER_X, LEVER_Y):
        assert lever in s3_verify.DECEPTION_CATALOG, (
            f"fixture wall: {lever!r} left the signed deception catalog "
            f"{s3_verify.DECEPTION_CATALOG}"
        )
    return cfg


@pytest.fixture
def slot(tmp_path: Path, cap: object) -> _Slot:
    return _Slot(tmp_path, cap)


# --------------------------------------------------------------------------
# PIN 1 — knob off is today's run, round after round
# --------------------------------------------------------------------------


@pytest.mark.parametrize("knob", [None, False], ids=["absent", "false"])
def test_pin1_knob_off_rejects_every_round(slot: _Slot, base_cfg: dict, knob: object) -> None:
    """No opt-in: an undeclared lever rejects on round one and on round two,
    identically.  Two rounds, because the only way an unasked-for corroboration
    read could hide is behind a history that does not exist yet."""
    cfg = _cfg(base_cfg, drop=knob is None, knob=knob)

    first = slot.run(cfg, levers=(LEVER_X,))
    second = slot.run(cfg, levers=(LEVER_X,))

    for label, report in (("round 1", first), ("round 2", second)):
        assert report["verdict"] == VERDICT_REJECT, (
            f"{label}: the knob is OFF, so an undeclared lever must still reject — "
            f"got {report['verdict']} with reasons {report['reject_reasons']}"
        )
        assert _reason_codes(report) == [s3_verify.REJECT_UNDECLARED_DECEPTION], label
        assert LEVER_X in json.dumps(report["reject_reasons"], sort_keys=True), label
        # No behavioral change anywhere: nothing is warned-and-recorded either.
        assert list(report["diff"].get(UNCORROBORATED_KEY, [])) == [], (
            f"{label}: the knob is off but the diff records {UNCORROBORATED_KEY}"
        )

    assert first["diff"] == second["diff"], "knob off: the second round's diff drifted"
    assert first["reject_reasons"] == second["reject_reasons"], (
        "knob off: two identical rounds produced different reject reasons — the second "
        "round read history it must not be reading"
    )


def test_pin1_knob_off_still_accrues_history(slot: _Slot, base_cfg: dict) -> None:
    """Frozen clause: with the knob off the sidecar is STILL written, so a
    later knob-on batch has real history to corroborate against."""
    cfg = _cfg(base_cfg, drop=True)
    slot.run(cfg, levers=(LEVER_X,))
    slot.run(cfg, levers=(LEVER_Y,))

    entries = slot.entries()
    assert len(entries) == 2, f"two rounds appended {len(entries)} entries: {entries}"
    assert _detected(entries[0]) == [LEVER_X]
    assert _detected(entries[1]) == [LEVER_Y]


def test_pin1_compute_diff_stays_pure() -> None:
    """Frozen: the history is threaded in as an explicit parameter with a
    default meaning knob-off — `compute_diff` never grows an I/O handle."""
    params = list(inspect.signature(s3_verify.compute_diff).parameters.values())
    required = [p for p in params if p.default is inspect.Parameter.empty]

    assert [p.name for p in required] == ["claims", "spec"], (
        "compute_diff gained a required parameter beyond (claims, spec): "
        f"{[p.name for p in required]} — every addition must default to knob-off"
    )
    impure = [
        p.name
        for p in params
        if any(mark in p.name.lower() for mark in ("path", "dir", "cfg", "config", "worker"))
    ]
    assert not impure, (
        f"compute_diff gained {impure}: the contract keeps it PURE (no config read, no "
        "sidecar path) and puts the corroboration pass at the assemble/verdict seam"
    )


# --------------------------------------------------------------------------
# PIN 2 — cold start: the first sighting is a warning
# --------------------------------------------------------------------------


def test_pin2_cold_start_warns_and_starts_history(slot: _Slot, base_cfg: dict) -> None:
    """No sidecar yet = no history = a first sighting.  The finding leaves the
    reject reasons, is recorded instead, and history begins with this round."""
    assert not slot.history_files(), "fixture wall: the planted slot already has a history"
    cfg = _cfg(base_cfg, True)

    report = slot.run(cfg, levers=(LEVER_X,))

    assert report["verdict"] == VERDICT_PASS, (
        "a first-sighting lever is a WARNING, not a reject — a blind audit that sees a "
        f"real deception sees it every round; got {report['reject_reasons']}"
    )
    assert report["reject_reasons"] == []
    assert _levers_recorded(report) == [LEVER_X]
    assert _note_of(_uncorroborated(report["diff"])[0])
    # Suppressed is not dropped: the round's own detection survives in the diff.
    assert report["diff"]["deceptions_detected"] == [LEVER_X]

    entries = slot.entries()
    assert len(entries) == 1, f"the cold-start round appended {len(entries)} entries"
    assert _detected(entries[0]) == [LEVER_X]
    assert _stamp(entries[0])


# --------------------------------------------------------------------------
# PIN 3 — a second sighting is the honest reject
# --------------------------------------------------------------------------


def test_pin3_second_sighting_rejects(slot: _Slot, base_cfg: dict) -> None:
    """Stability across two independent blind sessions: the same lever next
    round rejects with the normal undeclared-deception reason."""
    cfg = _cfg(base_cfg, True)
    first = slot.run(cfg, levers=(LEVER_X,))
    assert first["verdict"] == VERDICT_PASS, "fixture wall: round 1 should warn, not reject"

    second = slot.run(cfg, levers=(LEVER_X,))

    assert second["verdict"] == VERDICT_REJECT, (
        f"{LEVER_X!r} was detected in a PREVIOUS round's entry and again now — that is "
        "the stability bar met, so the finding must reject"
    )
    assert _reason_codes(second) == [s3_verify.REJECT_UNDECLARED_DECEPTION]
    assert LEVER_X in json.dumps(second["reject_reasons"], sort_keys=True)
    assert LEVER_X not in _levers_recorded(second), (
        "a corroborated lever is a reject reason, not a recorded warning — it must not "
        "appear in both surfaces"
    )
    assert len(slot.entries()) == 2, "the rejecting round must still append its own entry"


# --------------------------------------------------------------------------
# PIN 4 — rotation: a different lever is still a first sighting
# --------------------------------------------------------------------------


def test_pin4_rotation_still_passes(slot: _Slot, base_cfg: dict) -> None:
    """Round 1 lever X, round 2 lever Y only: rotation is exactly what the
    measurement found, and it must not accumulate into a reject."""
    cfg = _cfg(base_cfg, True)
    first = slot.run(cfg, levers=(LEVER_X,))
    second = slot.run(cfg, levers=(LEVER_Y,))

    assert first["verdict"] == VERDICT_PASS, first["reject_reasons"]
    assert second["verdict"] == VERDICT_PASS, (
        f"{LEVER_Y!r} has never been seen before — a rotated name is not corroboration; "
        f"got {second['reject_reasons']}"
    )
    assert _levers_recorded(second) == [LEVER_Y]

    entries = slot.entries()
    assert len(entries) == 2, f"two rounds, {len(entries)} history entries: {entries}"
    assert _detected(entries[0]) == [LEVER_X], "round 1's entry was rewritten — append only"
    assert _detected(entries[1]) == [LEVER_Y]


# --------------------------------------------------------------------------
# PIN 5 — history records detection, not verdicts
# --------------------------------------------------------------------------


def test_pin5_declared_lever_is_recorded_but_never_a_finding(
    slot: _Slot, base_cfg: dict
) -> None:
    """A lever the spec DECLARES, detected in both rounds: no finding either
    round, nothing recorded as uncorroborated, and both sidecar entries carry
    it — so a later undeclared sighting of the same keyword corroborates."""
    cfg = _cfg(base_cfg, True)
    first = slot.run(cfg, levers=(LEVER_X,), declared_levers=(LEVER_X,))
    second = slot.run(cfg, levers=(LEVER_X,), declared_levers=(LEVER_X,))

    for label, report in (("round 1", first), ("round 2", second)):
        assert report["verdict"] == VERDICT_PASS, f"{label}: {report['reject_reasons']}"
        assert report["reject_reasons"] == [], label
        assert LEVER_X not in _levers_recorded(report), (
            f"{label}: a DECLARED lever is not a finding at all, so it can never be an "
            "uncorroborated one"
        )
        assert report["diff"]["deceptions_declared"] == [LEVER_X], label

    entries = slot.entries()
    assert len(entries) == 2, f"two rounds appended {len(entries)} entries"
    for index, entry in enumerate(entries):
        assert _detected(entry) == [LEVER_X], (
            f"entry {index} does not record the declared lever — the history records "
            "every keyword the audit DETECTED, declared or not"
        )


# --------------------------------------------------------------------------
# PIN 6 — the two recorded surfaces compose
# --------------------------------------------------------------------------


def test_pin6_exempt_term_and_first_sighting_compose(slot: _Slot, base_cfg: dict) -> None:
    """One report, both suppressions: an exempt term's finding and a lever's
    first sighting.  Pass, both lists populated, and the diff still validates —
    a recorded finding that cannot be written out records nothing."""
    cfg = _cfg(base_cfg, True)

    report = slot.run(cfg, levers=(LEVER_X,), extra_terms=(EXEMPT_TERM,), exempt=(EXEMPT_TERM,))

    assert report["verdict"] == VERDICT_PASS, (
        "an exempt term plus a first-sighting lever leaves nothing to reject on; got "
        f"{report['reject_reasons']}"
    )
    assert report["reject_reasons"] == []

    diff = report["diff"]
    exempted = [entry for entry in diff[EXEMPTED_KEY] if entry.get("term") == EXEMPT_TERM]
    assert len(exempted) == 1, f"{EXEMPT_TERM!r} not recorded once in {diff[EXEMPTED_KEY]}"
    assert exempted[0]["would_have_been"], "the exempted entry lost what it would have been"
    assert _levers_recorded(report) == [LEVER_X]

    s3_verify._validate_diff(diff)


# --------------------------------------------------------------------------
# PIN 7 — the b002 config opts into the ruling
# --------------------------------------------------------------------------


def test_pin7_b002_config_carries_the_ruling() -> None:
    raw = yaml.safe_load((REPO_ROOT / B002_CONFIG).read_text(encoding="utf-8"))

    assert raw["verifier"]["exempt_terms"] == RULING_EXEMPT_TERMS
    assert raw["verifier"][KNOB] is True, (
        f"verifier.{KNOB} must be the boolean true, not "
        f"{raw['verifier'].get(KNOB)!r} — a non-bool is a hard error at read time"
    )
    # The values survive the signed-vocabulary check the exemption pass runs.
    assert list(s3_verify._exempt_terms(load_config(B002_CONFIG))) == RULING_EXEMPT_TERMS


def test_pin7_both_keys_carry_their_provenance_comment() -> None:
    """Repo convention: every deviation knob cites the ruling that bought it."""
    comments = [
        line.strip()
        for line in (REPO_ROOT / B002_CONFIG).read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("#")
    ]
    joined = "\n".join(comments).lower()

    assert EXEMPT_TERM in joined, (
        f"no comment cites {EXEMPT_TERM!r} — the exemption rests on a measured "
        "dead/dead/reachable rotation plus a human play verdict, and the file is where "
        "that provenance lives"
    )
    assert "corrobor" in joined, f"no comment explains verifier.{KNOB}"
    assert RULING_DATE in joined, f"no comment carries the ruling date {RULING_DATE}"


# --------------------------------------------------------------------------
# PIN 8 — bad states are loud
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["true", "false", 1, ["true"], {"enabled": True}],
    ids=["str-true", "str-false", "int", "list", "mapping"],
)
def test_pin8_non_bool_knob_raises(slot: _Slot, base_cfg: dict, value: object) -> None:
    """A truthy-looking string must not switch a reject policy on or off."""
    cfg = _cfg(base_cfg, value)
    try:
        report = slot.run(cfg, levers=(LEVER_X,))
    except Exception as exc:  # noqa: BLE001 — the type is asserted right below
        _loud(exc, f"verifier.{KNOB}={value!r}")
        return
    pytest.fail(
        f"verifier.{KNOB}={value!r} did not raise; the run returned "
        f"{report['verdict']!r}. A non-bool must be a hard error: silently coercing it "
        "either hides a reject class or resurrects one, and nobody reads the report to "
        "find out which"
    )


def test_pin8_unparsable_sidecar_raises(slot: _Slot, base_cfg: dict) -> None:
    """Pipeline state must parse: a corrupt history is not an empty history.

    Treating it as empty would silently turn every corroborated lever back into
    a first sighting — the exact reject class this knob narrows.
    """
    cfg = _cfg(base_cfg, True)
    slot.run(cfg, levers=(LEVER_X,))
    sidecar = slot.sidecar()
    sidecar.write_text('{"detected": [truncated', encoding="utf-8")

    try:
        report = slot.run(cfg, levers=(LEVER_X,))
    except Exception as exc:  # noqa: BLE001 — the type is asserted right below
        _loud(exc, f"an unparsable {sidecar.name}")
        return
    pytest.fail(
        f"an unparsable {sidecar.name} was tolerated; the round returned "
        f"{report['verdict']!r}. The findings-feed precedent is that unparsable pipeline "
        "state raises"
    )
