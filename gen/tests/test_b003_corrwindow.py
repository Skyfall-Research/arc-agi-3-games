"""Blind pins for contract C-2 — windowed lever corroboration.

Run: .venv/bin/python -m pytest gen/tests/test_b003_corrwindow.py -v

Written from the frozen C-2 contract ALONE (blind test writer).  No in-progress
C-2 diff of `gen/s3_verify.py` was read.  What this file is allowed to know,
and does: that module's PRE-EXISTING corroboration surface as it stands at
`git show HEAD:gen/s3_verify.py` (`read_lever_history`, `append_lever_history`,
`lever_history_path`, `corroborated_levers`, `_apply_corroboration`,
`_lever_corroboration`, `DIFF_KEYS`, `assemble_report`), the sibling suite
`test_b002_corroboration.py` (whose `_Slot` report-assembly harness this file
reuses), and the checked-in `toy_worker` fixture.  These pins therefore
describe the CONTRACT, not the implementation, and are expected to fail until
C-2 lands.

WHY THE WINDOW EXISTS (the measured failure, stated from the contract)

`verifier.lever_corroboration` demotes an undeclared-deception finding to a
warning unless a PRIOR round also named that lever.  "Prior" is ANY prior
round, so across eight audit rounds the history accrues until nearly every
keyword has been named somewhere before and the bar saturates back toward
reject-on-sight — the very behavior the ruling bought its way out of.  The
blind sessions' lever names ROTATE, so a REAL stable deception is named in
CONSECUTIVE rounds while a rotating phantom is not.  Windowing the
corroboration to the last N rounds is what tells those two apart.

THE FOUR PINS, in the contract's order

1. `_lever_window(cfg)` — absent/null => None; 1 and 3 parse; 0, -1, True,
   "1" => ValueError naming the key; a window set while `lever_corroboration`
   is false => ValueError.  Read at the same seam as `_lever_corroboration`,
   i.e. loud BEFORE any file is touched.
2. window semantics on a synthetic history built through
   `append_lever_history`: rounds {a}, {b}, {a,c} => window None gives
   {a,b,c}, window 1 gives {a,c}, window 2 gives {a,b,c}; plus the same
   difference driven end to end through `assemble_report` (the saturation
   measurement: with no window a lever named two rounds ago still rejects,
   with window 1 it does not).
3. byte-compat — `corroborated_levers(history)` == `(history, window=None)` ==
   the union; `_apply_corroboration`'s knob-off behavior on a synthetic diff is
   unchanged; a run with neither knob set rejects exactly as it does today,
   twice running.
4. the report records the window it used under the key `lever_window`.

AMBIGUITIES RESOLVED (each is quoted in the failure message that depends on it)

  a. The contract's rule 1 ("absent/null => None") and its contradiction rule
     ("setting the window while corroboration is false is a ValueError") meet
     at `{lever_corroboration: false, lever_corroboration_window: null}`.
     Reading: `null` IS the absent spelling — rule 1 is unconditional and a
     null window windows nothing, so there is no contradiction to raise about.
     Pinned in its own test (`test_pin1_null_window_is_absent_even_when_off`)
     so an adjudication the other way moves one line.
  b. "corroboration is false" is read as `_lever_corroboration(cfg)` being
     false, which covers BOTH a false knob and an absent one — the reader
     already treats an absent knob as false, and a window over a corroboration
     pass that is not running is the same contradiction either way.
  c. `corroborated_levers(history, window=None)`: the contract offers "or the
     equivalent seam — study the real function".  The real function takes the
     history positionally and returns a frozenset, so the only addition the
     contract can mean is a second parameter; it is pinned by NAME (`window`)
     and by DEFAULT (None), because pin 2 says "assert via corroborated_levers'
     window arg".
  d. Where the report records the window is left open by the contract (the
     corroboration MODE is not recorded in the b7.1 report today, so there is
     nothing to sit beside).  The SPELLING is not open: `lever_window`.  So
     this file searches the whole report recursively for that key and pins its
     VALUE, never its position.  With corroboration on and no window set the
     key is pinned only conditionally (if recorded, it records null) — a
     knob-off run must stay byte-identical, so "always present" is not a thing
     the contract lets this file assume.
  e. Pin 3's "assert nothing in the b002 suite was edited" is not something a
     test can do; per the contract's own instruction it is re-exercised
     instead — `_apply_corroboration` knob-off on a synthetic diff, and a
     two-round knob-off run through the real seam.

This file writes only inside `tmp_path`.  The canon, `out/`, the configs and
every other source file are read-only here.
"""

from __future__ import annotations

import copy
import inspect
import json
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

from gen import s3_verify
from gen.config import load_config

# A real config, used ONLY as a base: it supplies `duckwm_docs` and the rest of
# the run metadata `assemble_report` reads.  Both corroboration keys are set or
# dropped explicitly by `_cfg` below, so nothing here depends on what the file
# happens to carry.
BASE_CONFIG = "config/b002-triple.yaml"
TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"

# Contract wording, not code names.
KNOB = "lever_corroboration"
WINDOW_KEY = "lever_corroboration_window"
REPORT_WINDOW_KEY = "lever_window"

VERDICT_PASS, VERDICT_REJECT = "pass", "reject"
MODE_FULL = "full"

# Three distinct catalog levers: the contract's a, b, c.
# PIN UPDATE, contract E-1 (2026-10-05): b was `"mimic"` and c `"camouflage"`,
# which the re-grounded catalog reads as SPELLINGS of §7.1 and §7.2 rather than
# levers of their own; they fold onto `look-alike` and `palette overload`, which
# is what b and c are now. Still three DISTINCT levers — the window pins need
# them distinct and need nothing else from them.
LEVER_A = "decoy"
LEVER_B = "look-alike"
LEVER_C = "palette overload"

GAME_ID = "b003-corrwindow-synthetic"
SYNTHETIC_NOTE = "synthetic fixture"

_ABSENT = object()


# --------------------------------------------------------------------------
# the surface under test, fetched rather than assumed
# --------------------------------------------------------------------------


def _window_reader():
    """`_lever_window` — the contract's own spelling for the reader."""
    reader = getattr(s3_verify, "_lever_window", None)
    assert callable(reader), (
        "gen.s3_verify has no `_lever_window(cfg)` reader. C-2 §1 names it, beside "
        f"`_lever_corroboration`, reading `verifier.{WINDOW_KEY}` and returning int | None"
    )
    return reader


def _window(cfg: Mapping):
    return _window_reader()(cfg)


def _cfg(base: Mapping, *, corroboration: object = _ABSENT, window: object = _ABSENT) -> dict:
    """A config with each corroboration key forced on, off or absent."""
    cfg = copy.deepcopy(dict(base))
    verifier = dict(cfg.get("verifier") or {})
    verifier.pop(KNOB, None)
    verifier.pop(WINDOW_KEY, None)
    if corroboration is not _ABSENT:
        verifier[KNOB] = corroboration
    if window is not _ABSENT:
        verifier[WINDOW_KEY] = window
    cfg["verifier"] = verifier
    return cfg


def _bare(*, corroboration: object = _ABSENT, window: object = _ABSENT) -> dict:
    """The same, with no surrounding run config — the reader only needs
    `verifier`, exactly as `_lever_corroboration` only needs it."""
    return _cfg({}, corroboration=corroboration, window=window)


def _raises_valueerror(call, where: str) -> None:
    """A bad config value must be a loud, deliberate ValueError naming the key.

    `_lever_corroboration` sets the precedent in this module (ValueError with a
    `noqa: TRY004` on it, because a bad config value is bad DATA), and C-2 §1
    says "ValueError naming the key".
    """
    with pytest.raises(ValueError) as caught:
        call()
    assert WINDOW_KEY in str(caught.value), (
        f"{where} raised ValueError without naming the key: {caught.value!r}. The contract "
        f"requires the message to name `verifier.{WINDOW_KEY}` so a bad batch config is "
        "fixable from the failure alone"
    )


# --------------------------------------------------------------------------
# synthetic verifier inputs + the report-assembly seam (house style: the
# sibling b002 suite's harness, unchanged in shape)
# --------------------------------------------------------------------------


def _evidence() -> list[dict]:
    return [{"path": "game.py", "line": 10, "note": SYNTHETIC_NOTE}]


def _claims(levers: tuple[str, ...]) -> dict:
    return {
        "terms": [{"term": "move.grid", "reachable": True, "evidence": _evidence()}],
        "dead_code": [],
        "deceptions": [{"lever": lever, "evidence": _evidence()} for lever in levers],
        "enforcement": [],
        "notes": SYNTHETIC_NOTE,
    }


def _spec() -> dict:
    return {"game": {"terms": ["move.grid"], "knobs": {"deceptions": []}}}


def _synthetic_diff(*, undeclared: tuple[str, ...]) -> dict:
    """A full, valid diff — every frozen key present, built from `DIFF_KEYS`."""
    diff = {key: [] for key in s3_verify.DIFF_KEYS}
    diff["deceptions_detected"] = list(undeclared)
    diff["undeclared_deceptions"] = list(undeclared)
    return diff


class _Slot:
    """One planted slot: a worker dir plus as many FULL verify rounds as a test
    wants to drive through it.  Rounds share the slot — the sidecar is per-slot
    and accrues across rounds, which is the whole subject of this contract."""

    def __init__(self, root: Path, cap: object) -> None:
        self.root = root
        self.worker = root / "slot-1"
        shutil.copytree(TOY_WORKER, self.worker, ignore=shutil.ignore_patterns("__pycache__"))
        self.frames_path = root / s3_verify.FRAMES_NAME
        self.frames_path.write_text("{}", encoding="utf-8")
        self._cap = cap
        self.rounds = 0

    def run(self, cfg: Mapping, *, levers: tuple[str, ...] = ()) -> dict:
        """One audit round: build the diff on the pure path, then assemble."""
        self.rounds += 1
        claims = _claims(levers)
        diff = s3_verify.compute_diff(claims, _spec())
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
            cfg=dict(cfg),
            cap=self._cap,
            checks=[],
            frames_path=self.frames_path,
            agent=agent,
            diff=diff,
            spec_hash=None,
        )

    def history_files(self) -> list[Path]:
        return sorted(
            path
            for path in self.root.rglob("*")
            if path.is_file() and "history" in path.name.lower()
        )

    def entries(self) -> list:
        return s3_verify.read_lever_history(s3_verify.lever_history_path(self.worker))


def _reason_codes(report: Mapping) -> list[str]:
    return [reason["code"] for reason in report["reject_reasons"]]


def _recorded_windows(node: object, path: str = "report") -> list[tuple[str, object]]:
    """Every `lever_window` the report carries, wherever it sits (ambiguity d)."""
    found: list[tuple[str, object]] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            spot = f"{path}.{key}"
            if str(key) == REPORT_WINDOW_KEY:
                found.append((spot, value))
            found.extend(_recorded_windows(value, spot))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_recorded_windows(item, f"{path}[{index}]"))
    return found


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
    cfg = load_config(BASE_CONFIG)
    assert MODE_FULL in s3_verify.MODES, f"fixture wall: {MODE_FULL!r} is no longer a mode"
    for lever in (LEVER_A, LEVER_B, LEVER_C):
        assert lever in s3_verify.DECEPTION_CATALOG, (
            f"fixture wall: {lever!r} left the signed deception catalog "
            f"{s3_verify.DECEPTION_CATALOG}"
        )
    return cfg


@pytest.fixture
def slot(tmp_path: Path, cap: object) -> _Slot:
    return _Slot(tmp_path, cap)


@pytest.fixture
def history(tmp_path: Path):
    """A factory: rounds in, the recorded history back — built the only way the
    contract allows (`append_lever_history` into tmp), never hand-written."""

    def build(*rounds: tuple[str, ...]) -> list:
        path = tmp_path / "planted" / "slot-1.lever-history.json"
        for detected in rounds:
            s3_verify.append_lever_history(path, list(detected))
        return s3_verify.read_lever_history(path)

    return build


# --------------------------------------------------------------------------
# PIN 1 — the reader
# --------------------------------------------------------------------------


def test_pin1_window_key_is_the_contract_spelling_under_verifier() -> None:
    """`LEVER_WINDOW_KEY = "lever_corroboration_window"`, read under `verifier:`."""
    assert getattr(s3_verify, "LEVER_WINDOW_KEY", None) == WINDOW_KEY, (
        "C-2 §1 freezes the config key beside LEVER_CORROBORATION_KEY: "
        f"LEVER_WINDOW_KEY = {WINDOW_KEY!r}, got "
        f"{getattr(s3_verify, 'LEVER_WINDOW_KEY', None)!r}"
    )
    stray = {"verifier": {KNOB: True}, WINDOW_KEY: 2}
    assert _window(stray) is None, (
        f"a top-level {WINDOW_KEY!r} was read as a window — the key lives under "
        "`verifier:`, exactly like the knob it modifies"
    )


@pytest.mark.parametrize(
    "cfg",
    [
        {},
        {"verifier": {}},
        _bare(corroboration=False),
        _bare(corroboration=True),
        _bare(corroboration=True, window=None),
    ],
    ids=["no-verifier", "empty-verifier", "off-no-window", "on-no-window", "on-null-window"],
)
def test_pin1_absent_or_null_window_is_none(cfg: dict) -> None:
    """Absent or null => None: today's any-prior-round behavior, and the reason
    a run that does not opt in stays byte-identical."""
    assert _window(cfg) is None, (
        f"`verifier.{WINDOW_KEY}` absent or null must read as None (any-prior-round "
        f"corroboration, the canon default), got {_window(cfg)!r} for {cfg!r}"
    )


def test_pin1_null_window_is_absent_even_when_off() -> None:
    """Ambiguity (a): `null` is the ABSENT spelling, so it is not the
    "window set while corroboration is false" contradiction.  Rule 1 of the
    contract is unconditional, and a null window windows nothing."""
    cfg = _bare(corroboration=False, window=None)
    assert _window(cfg) is None, (
        f"{{{KNOB}: false, {WINDOW_KEY}: null}} must read as None. The contract's first "
        "rule is unconditional (absent/null => None) and the contradiction it raises on "
        "is a window that would window something; a null one does not. If lead "
        "adjudicates the other way, this single test moves"
    )


@pytest.mark.parametrize("value", [1, 2, 3], ids=["one", "two", "three"])
def test_pin1_positive_int_window_parses(value: int) -> None:
    """A positive int N => only the LAST N history entries corroborate."""
    cfg = _bare(corroboration=True, window=value)
    assert _window(cfg) == value, (
        f"`verifier.{WINDOW_KEY}: {value}` must read back as the int {value}, got "
        f"{_window(cfg)!r}"
    )


@pytest.mark.parametrize(
    "value",
    [0, -1, True, False, "1", 1.0, [1], {"last": 1}],
    ids=["zero", "negative", "true", "false", "str", "float", "list", "mapping"],
)
def test_pin1_bad_window_raises(value: object) -> None:
    """Anything that is not a positive int is a hard error.

    Same reasoning as the bool knob beside it: this value decides which
    findings may reject, so `0` (a window that corroborates nothing, i.e.
    reject-on-sight) and `"1"` (a string that would silently become a window,
    or silently not) are never guessed at.
    """
    cfg = _bare(corroboration=True, window=value)
    _raises_valueerror(lambda: _window(cfg), f"verifier.{WINDOW_KEY}={value!r}")


@pytest.mark.parametrize(
    "corroboration", [False, _ABSENT], ids=["knob-false", "knob-absent"]
)
def test_pin1_window_without_corroboration_raises(corroboration: object) -> None:
    """A window with nothing to window is a config contradiction (ambiguity b:
    an ABSENT knob is a false one — the reader beside this one already says
    so, and the pass is equally not running)."""
    cfg = _bare(corroboration=corroboration, window=2)
    _raises_valueerror(
        lambda: _window(cfg),
        f"verifier.{WINDOW_KEY}=2 with {KNOB}={'absent' if corroboration is _ABSENT else False}",
    )


def test_pin1_bad_window_fails_before_any_file_is_touched(slot: _Slot, base_cfg: dict) -> None:
    """Read at the same seam as `_lever_corroboration`: a bad window stops the
    round BEFORE the sidecar is written, so a rejected config never leaves a
    half-recorded history a later round would corroborate against."""
    assert not slot.history_files(), "fixture wall: the planted slot already has a history"
    cfg = _cfg(base_cfg, corroboration=True, window=0)

    with pytest.raises(ValueError):
        slot.run(cfg, levers=(LEVER_A,))

    assert not slot.history_files(), (
        "a run with an invalid window still wrote "
        f"{[p.name for p in slot.history_files()]} — the knob is read first, so a bad one "
        "fails before any file is touched"
    )


# --------------------------------------------------------------------------
# PIN 2 — window semantics
# --------------------------------------------------------------------------


def test_pin2_corroborated_levers_takes_a_window_arg() -> None:
    """Ambiguity (c): one added parameter, named `window`, defaulting to None."""
    params = list(inspect.signature(s3_verify.corroborated_levers).parameters.values())
    required = [p.name for p in params if p.default is inspect.Parameter.empty]
    assert len(required) == 1, (
        f"corroborated_levers' required parameters are {required} — the window is an "
        "OPTIONAL second argument whose default is today's behavior, so the history stays "
        "the only thing a caller must pass"
    )
    by_name = {p.name: p for p in params}
    assert "window" in by_name, (
        f"corroborated_levers has no `window` parameter (signature: {list(by_name)}) — C-2 "
        "§1 spells `corroborated_levers(history, window=None)`"
    )
    assert by_name["window"].default is None, (
        f"`window` defaults to {by_name['window'].default!r}; it must default to None, the "
        "any-prior-round union every existing caller already gets"
    )


def test_pin2_window_semantics_table(history) -> None:
    """The contract's table, on a history built through `append_lever_history`.

    Rounds R1{a}, R2{b}, R3{a,c} corroborating a new R4 finding:
      window None => {a, b, c}   (every prior round — today)
      window 1    => {a, c}      (R3 only)
      window 2    => {a, b, c}   (R2 + R3)
    """
    recorded = history((LEVER_A,), (LEVER_B,), (LEVER_A, LEVER_C))
    assert len(recorded) == 3, f"fixture wall: three appends recorded {len(recorded)} rounds"

    everything = frozenset({LEVER_A, LEVER_B, LEVER_C})
    expected = {
        None: everything,
        1: frozenset({LEVER_A, LEVER_C}),
        2: everything,
        3: everything,
        10: everything,
    }
    for window, want in expected.items():
        got = s3_verify.corroborated_levers(recorded, window=window)
        assert got == want, (
            f"window={window!r} over rounds [{{{LEVER_A}}}, {{{LEVER_B}}}, "
            f"{{{LEVER_A}, {LEVER_C}}}] corroborated {sorted(got)}; the contract's table "
            f"says {sorted(want)} (a window of N unions the LAST N recorded rounds; None "
            "unions them all, and a window longer than the history is the whole history)"
        )
        assert isinstance(got, frozenset), (
            f"window={window!r} returned {type(got).__name__}; the corroboration set is a "
            "frozenset, as it is today"
        )


def test_pin2_window_reads_the_last_rounds_not_the_first(history) -> None:
    """Three distinct rounds, window 2: the LAST two, never the first two."""
    recorded = history((LEVER_A,), (LEVER_B,), (LEVER_C,))
    got = s3_verify.corroborated_levers(recorded, window=2)
    assert got == frozenset({LEVER_B, LEVER_C}), (
        f"window=2 over rounds [{LEVER_A}, {LEVER_B}, {LEVER_C}] corroborated {sorted(got)} "
        f"— the window is the tail (history[-2:]), which is the whole point: a name from "
        "an old round must age OUT of the corroboration set"
    )


def test_pin2_window_over_empty_history_corroborates_nothing() -> None:
    """A cold start is a cold start whatever the window says."""
    assert s3_verify.corroborated_levers([], window=1) == frozenset()
    assert s3_verify.corroborated_levers([], window=None) == frozenset()


def test_pin2_window_1_beats_the_saturation_any_prior_produces(
    tmp_path: Path, cap: object, base_cfg: dict
) -> None:
    """The measurement, end to end through the real seam.

    Rounds name lever A, then B, then A again — the rotation the blind sessions
    actually produce.  With any-prior corroboration round 3 REJECTS on a name
    last seen two rounds ago (the saturation).  With window 1 only round 2
    corroborates, so the rotated name is still a warning.
    """
    outcomes = {}
    for label, window in (("any-prior", _ABSENT), ("window-1", 1)):
        slot = _Slot(tmp_path / label, cap)
        cfg = _cfg(base_cfg, corroboration=True, window=window)
        first = slot.run(cfg, levers=(LEVER_A,))
        second = slot.run(cfg, levers=(LEVER_B,))
        third = slot.run(cfg, levers=(LEVER_A,))
        assert first["verdict"] == VERDICT_PASS, f"{label}: {first['reject_reasons']}"
        assert second["verdict"] == VERDICT_PASS, f"{label}: {second['reject_reasons']}"
        assert len(slot.entries()) == 3, f"{label}: every round appends its own entry"
        outcomes[label] = third

    assert outcomes["any-prior"]["verdict"] == VERDICT_REJECT, (
        f"with no window, {LEVER_A!r} was named in round 1 and again in round 3, so ANY "
        "prior round corroborates and the finding rejects — this is the behavior the "
        "window exists to narrow, and it must not change when the knob is absent"
    )
    assert _reason_codes(outcomes["any-prior"]) == [s3_verify.REJECT_UNDECLARED_DECEPTION]

    third = outcomes["window-1"]
    assert third["verdict"] == VERDICT_PASS, (
        f"with window 1 only round 2 ({LEVER_B!r}) corroborates round 3, so the rotated "
        f"{LEVER_A!r} is a first sighting again and must stay a WARNING; got "
        f"{third['reject_reasons']}"
    )
    assert third["reject_reasons"] == []
    warned = third["diff"].get(s3_verify.UNCORROBORATED_KEY) or []
    recorded = [entry for entry in warned if entry.get("lever") == LEVER_A]
    assert len(recorded) == 1, (
        f"{LEVER_A!r} left the reject reasons but was not recorded in "
        f"{s3_verify.UNCORROBORATED_KEY}: {third['diff'].get(s3_verify.UNCORROBORATED_KEY)} "
        "— nothing is dropped; the record's shape is the one the b002 ruling froze"
    )
    assert third["diff"]["deceptions_detected"] == [LEVER_A]


def test_pin2_consecutive_sighting_still_rejects_under_window_1(
    slot: _Slot, base_cfg: dict
) -> None:
    """The other half of the measurement: a REAL deception is named in
    CONSECUTIVE rounds, and window 1 must still reject it."""
    cfg = _cfg(base_cfg, corroboration=True, window=1)
    first = slot.run(cfg, levers=(LEVER_A,))
    second = slot.run(cfg, levers=(LEVER_A,))

    assert first["verdict"] == VERDICT_PASS, first["reject_reasons"]
    assert second["verdict"] == VERDICT_REJECT, (
        f"{LEVER_A!r} was named in the IMMEDIATELY preceding round — that is the stability "
        "bar met inside any window, so the finding must reject; window 1 narrows which "
        "rounds corroborate, it never switches corroboration off"
    )
    assert _reason_codes(second) == [s3_verify.REJECT_UNDECLARED_DECEPTION]
    assert LEVER_A in json.dumps(second["reject_reasons"], sort_keys=True)


def test_pin2_a_round_may_not_corroborate_itself(slot: _Slot, base_cfg: dict) -> None:
    """The append-after-read order stays frozen: with window 1 the history read
    for round 1 is empty, not "this round"."""
    cfg = _cfg(base_cfg, corroboration=True, window=1)
    report = slot.run(cfg, levers=(LEVER_A,))
    assert report["verdict"] == VERDICT_PASS, (
        "the cold-start round rejected itself: with any window, the history is read BEFORE "
        f"this round is appended, so {LEVER_A!r} cannot vouch for itself; got "
        f"{report['reject_reasons']}"
    )
    assert len(slot.entries()) == 1, "the round must still record itself for later rounds"


# --------------------------------------------------------------------------
# PIN 3 — byte-compat with the knob absent
# --------------------------------------------------------------------------


def test_pin3_no_window_arg_equals_window_none_equals_the_union(history) -> None:
    """Four synthetic rounds, computed by hand: the union is
    {a, b, c} — and the no-arg call, the explicit None and that union are one
    and the same set."""
    recorded = history((LEVER_A,), (LEVER_B,), (LEVER_A, LEVER_C), ())
    union = frozenset({LEVER_A, LEVER_B, LEVER_C})

    no_arg = s3_verify.corroborated_levers(recorded)
    explicit = s3_verify.corroborated_levers(recorded, window=None)

    assert no_arg == explicit == union, (
        f"over four rounds the no-arg call gave {sorted(no_arg)} and window=None gave "
        f"{sorted(explicit)}; both must be the any-prior union {sorted(union)} — every "
        "existing caller passes no window and must get today's bytes"
    )


def test_pin3_apply_corroboration_knob_off_is_unchanged() -> None:
    """Re-exercised rather than assumed (ambiguity e): with the knob off
    (`None`), `_apply_corroboration` leaves a synthetic diff exactly as it
    found it; with a set it still demotes and records."""
    diff = _synthetic_diff(undeclared=(LEVER_A,))
    original = copy.deepcopy(diff)

    off_default = s3_verify._apply_corroboration(diff)
    off_explicit = s3_verify._apply_corroboration(diff, None)

    for label, out in (("default", off_default), ("explicit None", off_explicit)):
        assert out == original, f"knob off ({label}) changed the diff: {out!r}"
        assert s3_verify.UNCORROBORATED_KEY not in out, (
            f"knob off ({label}) added a {s3_verify.UNCORROBORATED_KEY} record — an absent "
            "knob is byte-identical behavior"
        )
    assert diff == original, "_apply_corroboration mutated the caller's diff"

    cold = s3_verify._apply_corroboration(diff, frozenset())
    assert cold["undeclared_deceptions"] == [], "an empty corroboration set is not None"
    assert [entry["lever"] for entry in cold[s3_verify.UNCORROBORATED_KEY]] == [LEVER_A]
    s3_verify._validate_diff(cold)

    corroborated = s3_verify._apply_corroboration(diff, frozenset({LEVER_A}))
    assert corroborated["undeclared_deceptions"] == [LEVER_A], (
        "a corroborated lever stays a reject-bearing finding"
    )


def test_pin3_both_knobs_absent_is_todays_run_twice_running(
    slot: _Slot, base_cfg: dict
) -> None:
    """Neither knob set: an undeclared lever rejects on round one and on round
    two, identically — the b002 pin-1 guarantee, re-exercised with the window
    key in the file's vocabulary."""
    cfg = _cfg(base_cfg)
    assert WINDOW_KEY not in cfg["verifier"] and KNOB not in cfg["verifier"]

    first = slot.run(cfg, levers=(LEVER_A,))
    second = slot.run(cfg, levers=(LEVER_A,))

    for label, report in (("round 1", first), ("round 2", second)):
        assert report["verdict"] == VERDICT_REJECT, (
            f"{label}: both knobs are absent, so an undeclared lever must still reject — "
            f"got {report['verdict']} with {report['reject_reasons']}"
        )
        assert _reason_codes(report) == [s3_verify.REJECT_UNDECLARED_DECEPTION], label
        assert list(report["diff"].get(s3_verify.UNCORROBORATED_KEY, [])) == [], label
    assert first["diff"] == second["diff"], "knobs absent: the second round's diff drifted"
    assert first["reject_reasons"] == second["reject_reasons"]


def test_pin3_corroboration_on_without_a_window_is_any_prior(
    slot: _Slot, base_cfg: dict
) -> None:
    """The window absent is NOT the window off: corroboration still runs, and
    it still runs over every prior round."""
    cfg = _cfg(base_cfg, corroboration=True)
    first = slot.run(cfg, levers=(LEVER_A,))
    second = slot.run(cfg, levers=(LEVER_B,))
    third = slot.run(cfg, levers=(LEVER_A,))

    assert first["verdict"] == VERDICT_PASS, first["reject_reasons"]
    assert second["verdict"] == VERDICT_PASS, second["reject_reasons"]
    assert third["verdict"] == VERDICT_REJECT, (
        "with no window the b002 behavior is unchanged: a lever named in ANY prior round "
        f"corroborates, so round 3's {LEVER_A!r} rejects; got {third['reject_reasons']}"
    )


# --------------------------------------------------------------------------
# PIN 4 — the report records the window it used
# --------------------------------------------------------------------------


def test_pin4_report_records_the_window(slot: _Slot, base_cfg: dict) -> None:
    """`lever_window: <N>` somewhere in the report (ambiguity d: the spelling is
    frozen by the contract, the position is not) — a verdict decided under a
    narrowed corroboration bar must say how narrow it was, or the R5 report
    cannot tell two batches apart."""
    cfg = _cfg(base_cfg, corroboration=True, window=1)
    report = slot.run(cfg, levers=(LEVER_A,))

    found = _recorded_windows(report)
    assert found, (
        f"the report records no {REPORT_WINDOW_KEY!r} anywhere (top-level keys: "
        f"{sorted(report)}; diff keys: {sorted(report['diff'])}). C-2 §1: the report "
        "records the window used, beside the corroboration mode if one is recorded and in "
        "the report's mode-adjacent metadata otherwise"
    )
    spots = {spot: value for spot, value in found}
    assert all(value == 1 for value in spots.values()), (
        f"the report records {spots} for a run with window 1 — the value is the window "
        "actually used"
    )
    assert all(isinstance(value, int) and not isinstance(value, bool) for value in spots.values())
    s3_verify.validate_report(report)


def test_pin4_recorded_window_is_null_when_no_window_is_set(
    slot: _Slot, base_cfg: dict
) -> None:
    """Corroboration on, no window: if the report records the field at all it
    records null (ambiguity d — this file does not pin the field PRESENT here,
    because a run that opts into nothing must stay byte-identical)."""
    cfg = _cfg(base_cfg, corroboration=True)
    report = slot.run(cfg, levers=(LEVER_A,))

    for spot, value in _recorded_windows(report):
        assert value is None, (
            f"{spot} records {value!r} for a run with no window; the contract's own "
            "spelling is `<N or null>`, and the any-prior mode is the null one"
        )
    s3_verify.validate_report(report)
