"""Blind pins for contract C-3 — term corroboration (the mirror of C-2).

Run: .venv/bin/python -m pytest gen/tests/test_b003_termcorr.py -v

Written from the frozen C-3 contract ALONE (blind test writer).  No in-progress
C-3 diff was read: the term-corroboration surface is described here only as the
contract words it.  What this file is allowed to know, and does: the
PRE-EXISTING verifier surface at `git show HEAD:gen/s3_verify.py` (`DIFF_KEYS`,
the six `REJECT_*` codes, `EXEMPTABLE_FINDINGS`/`EXEMPTED_KEY`, the lever
sidecar and its `corroborated_levers`/`_apply_corroboration` pair, `compute_diff`,
`decide_verdict`, `assemble_report`, `_validate_diff`, `validate_report`), the
already-landed C-2 report seam as named by the contract (`OPTIONAL_REPORT_KEYS`,
`LEVER_WINDOW_REPORT_KEY`), `gen/s2_implement.findings_section` at HEAD, and the
sibling suites `test_b002_corroboration.py` / `test_b003_corrwindow.py`, whose
`_Slot` report-assembly harness this file reuses in shape.  These pins therefore
describe the CONTRACT, not the implementation, and are expected to fail until
C-3 lands.

WHY THE TERM PASS EXISTS (the measured failure, stated from the contract)

The three TERM findings — `dead-spec-term`, `undeclared-term`,
`unreachable-declared-mechanic` — reject on ONE blind round's say-so, and they
ROTATE between rounds exactly as the lever findings did.  Because every ×2
escalation unions the rotated terms into the spec, b003 slot 1 was authored at
5 terms and escalated to 10 on nothing more stable than that rotation.  C-2
fixed this class for deceptions; C-3 is the mirror for terms, and it adds one
thing the lever pass does not need: the finding is DIRECTION-KEYED.  A term
sworn dead in one round and undeclared in the next is not a corroborated
finding — it is the instrument disagreeing with itself, which is precisely the
evidence the pass exists to discount.

THE SIX PINS, in the contract's order

1. the two knob parsers: defaults, the values that parse, the bad-value
   ValueErrors, and the window-without-bool contradiction;
2. `corroborated_terms` — direction-keyed pairs, the window table including the
   direction flip, an empty history, entries validated outside the window, a
   bad window; plus the sidecar the history is built through;
3. `_apply_term_corroboration` — None untouched, cold start demotes with the
   right codes, idempotent, caller's diff unmutated, composes with exemptions;
4. `assemble_report` end to end on a planted slot;
5. `findings_section` renders the advisory block, and without the key is
   byte-identical;
6. the lever machinery is untouched.

AMBIGUITIES RESOLVED (each is quoted in the failure message that depends on it)

  a. NULL BOOL KNOB.  The contract fixes `term_corroboration`'s default (False)
     and says "bool-validated", and separately says the WINDOW's null is the
     absent spelling.  Whether `term_corroboration: null` is therefore "absent"
     (False) or a bad bool (ValueError) is genuinely open, so this file pins it
     NEITHER way and says so here.  Every other non-bool IS pinned, mirroring
     `_lever_corroboration` and the b002 suite's own bad-value list.
  b. NULL WINDOW WHILE OFF.  `{term_corroboration: false, ..._window: null}` is
     read the way `test_b003_corrwindow` reads its mirror: rule "absent/null =>
     None" is unconditional, and a null window windows nothing, so there is no
     contradiction to raise about.  One test, `test_pin1_null_window_is_absent_
     even_when_off`, so an adjudication the other way moves one line.
  c. "corroboration is off" in the contradiction rule means `_term_corroboration
     (cfg)` is false, which covers both a false knob and an absent one.
  d. DIRECTION <-> LIST <-> CODE.  The contract names the directions ("dead",
     "undeclared", "unreachable"), names the three diff lists in that same
     order, and says the entry's `code` is "the reject code the finding would
     have produced".  That forces the mapping this file pins, and it is the
     mapping `EXEMPTABLE_FINDINGS` already froze for the exemption knob.
  e. RECORD ORDER.  The contract says the `uncorroborated_terms` record is
     "sorted" without naming the key.  Read as the mirror of `_apply_exemptions`
     (`sorted(..., key=(entry["term"], entry["would_have_been"]))`): SUBJECT
     first, then code.  Pinned in its own test.
  f. SORTED HISTORY LISTS.  The lever sidecar stores `detected` in the order it
     is handed; C-3's entry is spelled "(sorted lists of vocabulary ids)", an
     addition over that spelling, so sortedness is read as a property of the
     STORED entry and pinned on deliberately unsorted input.  Own test.
  g. THE ADVISORY BLOCK.  The contract freezes the block's prose but says
     "Exact layout your choice within the existing findings_section style", so a
     re-wrap of that paragraph is a layout choice and a hard line-for-line pin
     would pin the wrap rather than the wording.  This file pins the frozen
     sentence with WHITESPACE NORMALIZED, pins that it sits AFTER the last
     reject-reason bullet, and pins each entry's code and term into the block.
  h. WHERE `term_window` SITS.  The contract freezes the SPELLING and says it
     joins `OPTIONAL_REPORT_KEYS`, which is a top-level report set — so the key
     is pinned top-level, its value pinned, and its absence pinned when the pass
     did not run.
  i. A BAD WINDOW AND THE LEVER SIDECAR.  C-2's mirror asserts NO history file
     is written when the config is bad.  Here the term pass "sits beside" the
     lever pass, so a lever sidecar may legitimately already exist by the time
     the term knob is read; this file asserts only that the TERM sidecar was not
     written, which is the whole of what the rule protects.

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

from gen import s2_implement, s3_verify
from gen.config import load_config

# A real config, used ONLY as a base: it supplies `duckwm_docs` and the rest of
# the run metadata `assemble_report` reads.  Every knob this file cares about is
# set or dropped explicitly by `_cfg`, so nothing here depends on what the file
# happens to carry today.
BASE_CONFIG = "config/b002-triple.yaml"
TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"

# Contract wording, not code names.
KNOB = "term_corroboration"
WINDOW_KEY = "term_corroboration_window"
REPORT_WINDOW_KEY = "term_window"
HISTORY_SUFFIX = ".term-history.json"
RECORD_KEY = "uncorroborated_terms"
RECORD_ENTRY_KEYS = {"term", "code", "note"}

# The lever pair, named only so pin 6 can prove it was left alone.
LEVER_KNOB = "lever_corroboration"
LEVER_WINDOW_KEY = "lever_corroboration_window"
# PIN UPDATE, contract E-1 (2026-10-05): B was `"mimic"`, a SPELLING of §7.1
# after the re-grounding rather than a lever of its own, so it folds onto
# `look-alike` — which is what B names now. Two distinct levers, as before.
LEVER_A = "decoy"
LEVER_B = "look-alike"

VERDICT_PASS, VERDICT_REJECT = "pass", "reject"
MODE_FULL = "full"

# Ambiguity (d): the three directions, their diff lists and the reject code each
# would have produced.  `EXEMPTABLE_FINDINGS` froze the list<->code half already.
DIR_DEAD, DIR_UNDECLARED, DIR_UNREACHABLE = "dead", "undeclared", "unreachable"
DIRECTIONS = (DIR_DEAD, DIR_UNDECLARED, DIR_UNREACHABLE)
DIRECTION_LIST = {
    DIR_DEAD: "dead_spec_terms",
    DIR_UNDECLARED: "undeclared_terms",
    DIR_UNREACHABLE: "unreachable_declared_mechanics",
}
DIRECTION_CODE = {
    DIR_DEAD: s3_verify.REJECT_DEAD_SPEC_TERM,
    DIR_UNDECLARED: s3_verify.REJECT_UNDECLARED_TERM,
    DIR_UNREACHABLE: s3_verify.REJECT_UNREACHABLE_DECLARED,
}

# Real signed-vocabulary ids, none of them on the b002 config's exempt list, so
# a finding here is a finding and not a suppressed one.
TERM_FILLER = "move.grid"       # declared AND reachable every round: never a finding
TERM_X = "gate.phase"
TERM_Y = "hazard.timed"
TERM_Z = "state.undo"
EXEMPT_TERM = "budget.cap"      # the b002 ruling's own exempt term

GAME_ID = "b003-termcorr-synthetic"
SYNTHETIC_NOTE = "synthetic fixture"
SESSION_ID = "synthetic"        # constant: two rounds must be byte-comparable

# The frozen advisory prose (ambiguity g), whitespace-normalized.
ADVISORY_SENTENCE = (
    "The audit ALSO recorded these first-sighting term findings — not yet corroborated by "
    "a consecutive round, so they do not reject, but a repeat next round will:"
)
ADVISORY_OPENING = "The audit ALSO recorded these first-sighting term findings"

_ABSENT = object()


# --------------------------------------------------------------------------
# the surface under test, fetched rather than assumed
# --------------------------------------------------------------------------


def _attr(name: str, why: str):
    value = getattr(s3_verify, name, None)
    assert value is not None, f"gen.s3_verify has no `{name}` — {why}"
    return value


def _corroboration_reader():
    reader = getattr(s3_verify, "_term_corroboration", None)
    assert callable(reader), (
        "gen.s3_verify has no `_term_corroboration(cfg)` reader. C-3 §1 names it beside the "
        f"lever pair, reading `verifier.{KNOB}` and returning a bool (default False)"
    )
    return reader


def _window_reader():
    reader = getattr(s3_verify, "_term_window", None)
    assert callable(reader), (
        "gen.s3_verify has no `_term_window(cfg)` reader. C-3 §1 names it beside "
        f"`_term_corroboration`, reading `verifier.{WINDOW_KEY}` and returning int | None"
    )
    return reader


def _corroborated(*args, **kwargs):
    fn = _attr(
        "corroborated_terms",
        "C-3 §3 spells `corroborated_terms(history, window=None) -> frozenset[tuple[str, str]]`",
    )
    return fn(*args, **kwargs)


def _apply(*args, **kwargs):
    fn = _attr(
        "_apply_term_corroboration",
        "C-3 §4 spells `_apply_term_corroboration(diff, corroborated=None) -> dict`, "
        "mirroring `_apply_corroboration`",
    )
    return fn(*args, **kwargs)


def _history_path(worker: Path) -> Path:
    fn = _attr("term_history_path", "C-3 §2 names it beside `lever_history_path`")
    return fn(worker)


def _read_history(path: Path):
    fn = _attr("read_term_history", "C-3 §2 names it beside `read_lever_history`")
    return fn(path)


def _append_history(path: Path, dead, undeclared, unreachable):
    fn = _attr("append_term_history", "C-3 §2 spells it (path, dead, undeclared, unreachable)")
    return fn(path, list(dead), list(undeclared), list(unreachable))


def _record_key() -> str:
    key = getattr(s3_verify, "UNCORROBORATED_TERMS_KEY", None)
    assert key == RECORD_KEY, (
        f"C-3 §4 freezes `UNCORROBORATED_TERMS_KEY = {RECORD_KEY!r}`, got {key!r} — the diff's "
        "record of what stopped rejecting is read by the S2 findings feed and by R5"
    )
    return key


# --------------------------------------------------------------------------
# configs
# --------------------------------------------------------------------------


def _cfg(
    base: Mapping,
    *,
    corroboration: object = _ABSENT,
    window: object = _ABSENT,
    lever_corroboration: object = _ABSENT,
    lever_window: object = _ABSENT,
    exempt: object = _ABSENT,
) -> dict:
    """A config with every knob this file touches forced on, off or ABSENT.

    The base config opts into `exempt_terms` and `lever_corroboration`; both are
    dropped unless a test asks for them, so "knob off" here means genuinely
    nothing set rather than "the b002 ruling, minus the term pass".
    """
    cfg = copy.deepcopy(dict(base))
    verifier = dict(cfg.get("verifier") or {})
    for key in (KNOB, WINDOW_KEY, LEVER_KNOB, LEVER_WINDOW_KEY, "exempt_terms"):
        verifier.pop(key, None)
    for key, value in (
        (KNOB, corroboration),
        (WINDOW_KEY, window),
        (LEVER_KNOB, lever_corroboration),
        (LEVER_WINDOW_KEY, lever_window),
        ("exempt_terms", exempt),
    ):
        if value is not _ABSENT:
            verifier[key] = list(value) if key == "exempt_terms" else value
    cfg["verifier"] = verifier
    return cfg


def _bare(*, corroboration: object = _ABSENT, window: object = _ABSENT) -> dict:
    """The same with no surrounding run config — the readers only need
    `verifier`, exactly as `_lever_corroboration` only needs it."""
    return _cfg({}, corroboration=corroboration, window=window)


def _raises_valueerror(call, where: str, key: str) -> None:
    """A bad config value must be a loud, deliberate ValueError NAMING the key.

    `_lever_corroboration` sets the precedent in this module (ValueError with a
    `noqa: TRY004`, because a bad config value is bad DATA), and C-3 §1 says
    "ValueError naming the key".
    """
    with pytest.raises(ValueError) as caught:
        call()
    assert key in str(caught.value), (
        f"{where} raised ValueError without naming the key: {caught.value!r}. The contract "
        f"requires the message to name `verifier.{key}` so a bad batch config is fixable "
        "from the failure alone"
    )


# --------------------------------------------------------------------------
# synthetic verifier inputs + the report-assembly seam (house style: the
# sibling b002/corrwindow harness, unchanged in shape)
# --------------------------------------------------------------------------


def _evidence() -> list[dict]:
    return [{"path": "game.py", "line": 10, "note": SYNTHETIC_NOTE}]


def _claims(
    *,
    undeclared: tuple[str, ...] = (),
    unreachable: tuple[str, ...] = (),
    levers: tuple[str, ...] = (),
) -> dict:
    """What the blind audit says it saw.

    `undeclared` terms are reachable and absent from the spec; `unreachable`
    terms are SEEN but `reachable: false`; a DEAD term is simply never claimed
    at all, which is what makes the three findings distinct.
    """
    terms = [{"term": TERM_FILLER, "reachable": True, "evidence": _evidence()}]
    terms += [{"term": term, "reachable": True, "evidence": _evidence()} for term in undeclared]
    terms += [{"term": term, "reachable": False, "evidence": _evidence()} for term in unreachable]
    return {
        "terms": terms,
        "dead_code": [],
        "deceptions": [{"lever": lever, "evidence": _evidence()} for lever in levers],
        "enforcement": [],
        "notes": SYNTHETIC_NOTE,
    }


def _spec(*, dead: tuple[str, ...] = (), unreachable: tuple[str, ...] = ()) -> dict:
    """The spec this round is audited against: the filler plus every term the
    round means to declare (a dead one is declared and never claimed; an
    unreachable one is declared and claimed unreachable)."""
    declared = [TERM_FILLER, *dead, *unreachable]
    return {"game": {"terms": declared, "knobs": {"deceptions": []}}}


def _synthetic_diff(**findings: tuple[str, ...]) -> dict:
    """A full, valid diff — every frozen key present, built from `DIFF_KEYS`."""
    diff = {key: [] for key in s3_verify.DIFF_KEYS}
    for direction, terms in findings.items():
        diff[DIRECTION_LIST[direction]] = sorted(terms)
    return diff


class _Slot:
    """One planted slot: a worker dir plus as many FULL verify rounds as a test
    wants to drive through it.  Rounds share the slot — the sidecar is per-slot
    and accrues across rounds, which is the whole subject of this contract."""

    def __init__(self, root: Path, cap: object) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.worker = root / "slot-1"
        shutil.copytree(TOY_WORKER, self.worker, ignore=shutil.ignore_patterns("__pycache__"))
        self.frames_path = root / s3_verify.FRAMES_NAME
        self.frames_path.write_text("{}", encoding="utf-8")
        self._cap = cap
        self.rounds = 0

    def run(
        self,
        cfg: Mapping,
        *,
        dead: tuple[str, ...] = (),
        undeclared: tuple[str, ...] = (),
        unreachable: tuple[str, ...] = (),
        levers: tuple[str, ...] = (),
    ) -> dict:
        """One audit round: build the diff on the pure path, then assemble."""
        self.rounds += 1
        claims = _claims(undeclared=undeclared, unreachable=unreachable, levers=levers)
        diff = s3_verify.compute_diff(claims, _spec(dead=dead, unreachable=unreachable))
        agent = {
            "session_id": SESSION_ID,
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

    def term_sidecar(self) -> Path:
        return _history_path(self.worker)

    def lever_sidecar(self) -> Path:
        return s3_verify.lever_history_path(self.worker)

    def term_entries(self) -> list:
        return _read_history(self.term_sidecar())


def _reason_codes(report: Mapping) -> list[str]:
    return [reason["code"] for reason in report["reject_reasons"]]


def _reason_terms(report: Mapping) -> list[str]:
    return [reason["term"] for reason in report["reject_reasons"] if reason.get("term")]


def _recorded(report: Mapping) -> list[dict]:
    return list(report["diff"].get(RECORD_KEY) or [])


def _recorded_pairs(report: Mapping) -> set[tuple[str, str]]:
    """(code, term) for everything the round demoted to a warning."""
    return {(entry.get("code"), entry.get("term")) for entry in _recorded(report)}


def _normalize(text: str) -> str:
    return " ".join(text.split())


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
    vocab = s3_verify.load_vocab(cfg)
    for term in (TERM_FILLER, TERM_X, TERM_Y, TERM_Z, EXEMPT_TERM):
        assert term in vocab, f"fixture wall: {term!r} left the {len(vocab)}-term signed vocabulary"
    for direction, code in DIRECTION_CODE.items():
        assert code in s3_verify.REJECT_CODES, (
            f"fixture wall: the {direction!r} direction's code {code!r} left REJECT_CODES"
        )
    return cfg


@pytest.fixture
def slot(tmp_path: Path, cap: object) -> _Slot:
    return _Slot(tmp_path / "planted", cap)


@pytest.fixture
def history(tmp_path: Path):
    """A factory: rounds in, the recorded history back — built the only way the
    contract allows (`append_term_history` into tmp), never hand-written."""

    def build(*rounds: tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]) -> list:
        path = tmp_path / "history" / ("slot-1" + HISTORY_SUFFIX)
        for dead, undeclared, unreachable in rounds:
            _append_history(path, dead, undeclared, unreachable)
        return _read_history(path)

    return build


# ==========================================================================
# PIN 1 — the two knob parsers
# ==========================================================================


def test_pin1_config_key_spellings() -> None:
    """C-3 §1 freezes both config keys, read under `verifier:` like every other
    signed knob in this module."""
    assert getattr(s3_verify, "TERM_CORROBORATION_KEY", None) == KNOB, (
        f"C-3 §1: TERM_CORROBORATION_KEY = {KNOB!r}, got "
        f"{getattr(s3_verify, 'TERM_CORROBORATION_KEY', None)!r}"
    )
    assert getattr(s3_verify, "TERM_WINDOW_KEY", None) == WINDOW_KEY, (
        f"C-3 §1: TERM_WINDOW_KEY = {WINDOW_KEY!r}, got "
        f"{getattr(s3_verify, 'TERM_WINDOW_KEY', None)!r}"
    )
    stray = {"verifier": {}, KNOB: True, WINDOW_KEY: 2}
    assert _corroboration_reader()(stray) is False, (
        f"a top-level {KNOB!r} was read as the knob — it lives under `verifier:`, exactly "
        "like the lever pair it mirrors"
    )
    assert _window_reader()(stray) is None, (
        f"a top-level {WINDOW_KEY!r} was read as a window — it lives under `verifier:`"
    )


@pytest.mark.parametrize(
    "cfg",
    [{}, {"verifier": {}}, {"verifier": {"exempt_terms": []}}],
    ids=["no-verifier", "empty-verifier", "other-knobs-only"],
)
def test_pin1_corroboration_defaults_to_false(cfg: dict) -> None:
    """Absent knob -> False: canon behavior is the default and the deviation is
    opted into per batch, byte for byte (the `_lever_corroboration` rule)."""
    assert _corroboration_reader()(cfg) is False, (
        f"`verifier.{KNOB}` absent must read as False (canon = terms reject on one round's "
        f"say-so), got {_corroboration_reader()(cfg)!r} for {cfg!r}"
    )


@pytest.mark.parametrize("value", [True, False], ids=["true", "false"])
def test_pin1_real_bools_parse(value: bool) -> None:
    assert _corroboration_reader()(_bare(corroboration=value)) is value


@pytest.mark.parametrize(
    "value",
    ["true", "false", 1, 0, ["true"], {"enabled": True}],
    ids=["str-true", "str-false", "int-1", "int-0", "list", "mapping"],
)
def test_pin1_non_bool_corroboration_raises(value: object) -> None:
    """A truthy-looking string must not switch a reject policy on or off.

    Same reasoning the b002 suite pins for `lever_corroboration`: silently
    coercing this either hides a reject class or resurrects one, and nobody
    reads the report to find out which.  (Ambiguity (a): `null` is deliberately
    NOT in this list — the contract leaves it open.)
    """
    _raises_valueerror(
        lambda: _corroboration_reader()(_bare(corroboration=value)),
        f"verifier.{KNOB}={value!r}",
        KNOB,
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
    """Absent or null => None: the any-prior-round union, and the reason a run
    that does not opt in stays byte-identical."""
    assert _window_reader()(cfg) is None, (
        f"`verifier.{WINDOW_KEY}` absent or null must read as None (union over every "
        f"recorded round), got {_window_reader()(cfg)!r} for {cfg!r}"
    )


def test_pin1_null_window_is_absent_even_when_off() -> None:
    """Ambiguity (b): `null` IS the absent spelling, so it is not the "window set
    while corroboration is off" contradiction.  The contract's first rule is
    unconditional and a null window windows nothing."""
    cfg = _bare(corroboration=False, window=None)
    assert _window_reader()(cfg) is None, (
        f"{{{KNOB}: false, {WINDOW_KEY}: null}} must read as None. The contract's rule is "
        "unconditional (absent/null => None) and the contradiction it raises on is a window "
        "that would window something; a null one does not. If lead adjudicates the other "
        "way, this single test moves"
    )


@pytest.mark.parametrize("value", [1, 2, 3], ids=["one", "two", "three"])
def test_pin1_positive_int_window_parses(value: int) -> None:
    assert _window_reader()(_bare(corroboration=True, window=value)) == value


@pytest.mark.parametrize(
    "value",
    [0, -1, True, False, "1", 1.0, [1], {"last": 1}],
    ids=["zero", "negative", "true", "false", "str", "float", "list", "mapping"],
)
def test_pin1_bad_window_raises(value: object) -> None:
    """Anything that is not a positive int is a hard error — `0` would be a
    window corroborating nothing (reject-on-sight wearing the knob's name) and
    `"1"` would silently become a window, or silently not."""
    _raises_valueerror(
        lambda: _window_reader()(_bare(corroboration=True, window=value)),
        f"verifier.{WINDOW_KEY}={value!r}",
        WINDOW_KEY,
    )


@pytest.mark.parametrize("corroboration", [False, _ABSENT], ids=["knob-false", "knob-absent"])
def test_pin1_window_without_corroboration_raises(corroboration: object) -> None:
    """The contradiction rule, worded like `_lever_window`'s (ambiguity (c): an
    ABSENT knob is a false one, and the pass is equally not running)."""
    _raises_valueerror(
        lambda: _window_reader()(_bare(corroboration=corroboration, window=2)),
        f"verifier.{WINDOW_KEY}=2 with {KNOB}={'absent' if corroboration is _ABSENT else False}",
        WINDOW_KEY,
    )


def test_pin1_bad_window_fails_before_the_term_sidecar_is_written(
    slot: _Slot, base_cfg: dict
) -> None:
    """Read at the same seam as the knob: a bad window stops the round BEFORE
    the term sidecar is written, so a rejected config never leaves a
    half-recorded history a later round would corroborate against.

    Ambiguity (i): only the TERM sidecar is asserted absent — the term pass sits
    beside the lever pass, which may legitimately have recorded its own round
    already.
    """
    assert not slot.term_sidecar().exists(), "fixture wall: the slot already has a term history"
    cfg = _cfg(base_cfg, corroboration=True, window=0)

    with pytest.raises(ValueError):
        slot.run(cfg, dead=(TERM_X,))

    assert not slot.term_sidecar().exists(), (
        f"a run with an invalid window still wrote {slot.term_sidecar().name} — the knob and "
        "its window are read first, so a bad one fails before any term file is touched"
    )


# ==========================================================================
# PIN 2a — the sidecar
# ==========================================================================


def test_pin2_history_suffix_and_path() -> None:
    """`<worker>.term-history.json`, a SIBLING of the worker: a file inside it
    would trip the worker's own scaffold scope check (the B3 rule)."""
    assert getattr(s3_verify, "TERM_HISTORY_SUFFIX", None) == HISTORY_SUFFIX, (
        f"C-3 §2: TERM_HISTORY_SUFFIX = {HISTORY_SUFFIX!r}, got "
        f"{getattr(s3_verify, 'TERM_HISTORY_SUFFIX', None)!r}"
    )
    worker = Path("/tmp/planted/slot-1")
    path = _history_path(worker)
    assert path == worker.with_name("slot-1" + HISTORY_SUFFIX), (
        f"term_history_path({worker}) = {path} — it is a sibling of the worker named after "
        "it, exactly like `lever_history_path`"
    )
    assert path != s3_verify.lever_history_path(worker), (
        "the term history and the lever history must be SEPARATE files: C-3 §2 pins the "
        "lever sidecar and its entry shape, and a shared file would rewrite it"
    )


def test_pin2_missing_history_is_a_cold_start(tmp_path: Path) -> None:
    """No file yet -> `[]`, so every finding this round is a first sighting."""
    assert _read_history(tmp_path / ("nothing" + HISTORY_SUFFIX)) == []


def test_pin2_unparsable_history_raises(tmp_path: Path) -> None:
    """Pipeline state must parse: a corrupt history is not an empty one.

    Treating it as empty would silently turn every corroborated term back into a
    first sighting — the exact reject class this knob narrows.
    """
    path = tmp_path / ("slot-1" + HISTORY_SUFFIX)
    path.write_text('[{"ts": "now", "dead": [truncated', encoding="utf-8")
    with pytest.raises(ValueError):
        _read_history(path)


def test_pin2_entry_shape_is_ts_plus_three_directions(history) -> None:
    """Entry `{ts, dead, undeclared, unreachable}` — the lever-history pattern
    with a direction-keyed body."""
    recorded = history(((TERM_X,), (TERM_Y,), (TERM_Z,)))
    assert len(recorded) == 1
    entry = recorded[0]
    assert set(entry) >= {s3_verify.HISTORY_TS_KEY, *DIRECTIONS}, (
        f"one recorded round is {sorted(entry)}; C-3 §2 spells "
        f"{{{s3_verify.HISTORY_TS_KEY}, {', '.join(DIRECTIONS)}}} — the direction is what "
        "makes a term finding corroborable, so it cannot be flattened into one list"
    )
    assert isinstance(entry[s3_verify.HISTORY_TS_KEY], str)
    assert entry[DIR_DEAD] == [TERM_X], entry
    assert entry[DIR_UNDECLARED] == [TERM_Y], entry
    assert entry[DIR_UNREACHABLE] == [TERM_Z], entry


def test_pin2_stored_lists_are_sorted(history) -> None:
    """Ambiguity (f): the contract spells the entry's bodies as "sorted lists of
    vocabulary ids", an addition over the lever sidecar's as-handed order, so
    sortedness is a property of the STORED entry."""
    unsorted = (TERM_Z, TERM_X, TERM_Y)
    entry = history((unsorted, (), ()))[0]
    assert entry[DIR_DEAD] == sorted(unsorted), (
        f"{list(unsorted)} was stored as {entry[DIR_DEAD]}; C-3 §2 spells the entry's lists "
        "as sorted, so two rounds that found the same terms record the same bytes. If lead "
        "adjudicates the lever spelling (store as handed) instead, this single test moves"
    )


def test_pin2_history_is_append_only_and_survives(history) -> None:
    """Every prior round is rewritten verbatim and this round goes last."""
    recorded = history(((TERM_X,), (), ()), ((), (TERM_Y,), ()), ((), (), (TERM_Z,)))
    assert len(recorded) == 3, f"three appends recorded {len(recorded)} rounds"
    assert [entry[DIR_DEAD] for entry in recorded] == [[TERM_X], [], []]
    assert [entry[DIR_UNDECLARED] for entry in recorded] == [[], [TERM_Y], []]
    assert [entry[DIR_UNREACHABLE] for entry in recorded] == [[], [], [TERM_Z]]


def test_pin2_malformed_entry_is_rejected_on_read(tmp_path: Path) -> None:
    """Validation mirrors `_validate_history_entry`: the fields the file is READ
    for are not optional, while an extra field a later round adds is tolerated
    (the record is append-only and must stay readable)."""
    good = {s3_verify.HISTORY_TS_KEY: "now", DIR_DEAD: [], DIR_UNDECLARED: [], DIR_UNREACHABLE: []}
    path = tmp_path / ("slot-1" + HISTORY_SUFFIX)

    path.write_text(json.dumps([{**good, "note": "a later field"}]) + "\n", encoding="utf-8")
    assert len(_read_history(path)) == 1, (
        "an entry carrying an EXTRA key was rejected; the sidecar is append-only, so a field "
        "some later round adds must not make an earlier round unreadable"
    )

    for broken, why in (
        ({k: v for k, v in good.items() if k != DIR_DEAD}, f"no {DIR_DEAD!r} list"),
        ({**good, DIR_UNDECLARED: "not-a-list"}, f"a non-list {DIR_UNDECLARED!r}"),
        ({**good, DIR_UNREACHABLE: [1]}, f"a non-string in {DIR_UNREACHABLE!r}"),
        ({**good, s3_verify.HISTORY_TS_KEY: 1}, "a non-string stamp"),
    ):
        path.write_text(json.dumps([broken]) + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            _read_history(path)
            pytest.fail(f"an entry with {why} was read without complaint: {broken!r}")


# ==========================================================================
# PIN 2b — corroborated_terms
# ==========================================================================


def test_pin2_corroborated_terms_signature() -> None:
    """`corroborated_terms(history, window=None)` — the history is the only
    required argument and the window defaults to today's any-prior union."""
    fn = _attr("corroborated_terms", "C-3 §3 names it")
    params = list(inspect.signature(fn).parameters.values())
    required = [p.name for p in params if p.default is inspect.Parameter.empty]
    assert required == [params[0].name] and len(required) == 1, (
        f"corroborated_terms' required parameters are {required} — the window is an OPTIONAL "
        "second argument, so the history stays the only thing a caller must pass"
    )
    by_name = {p.name: p for p in params}
    assert "window" in by_name, (
        f"corroborated_terms has no `window` parameter (signature: {list(by_name)}); C-3 §3 "
        "spells `corroborated_terms(history, window=None)`"
    )
    assert by_name["window"].default is None


def test_pin2_pairs_are_direction_keyed(history) -> None:
    """The corroboration set is `(direction, term)` pairs, not bare terms."""
    recorded = history(((TERM_X,), (TERM_Y,), (TERM_Z,)))
    got = _corroborated(recorded)

    assert isinstance(got, frozenset), (
        f"corroborated_terms returned {type(got).__name__}; the corroboration set is a "
        "frozenset, as the lever one is"
    )
    assert got == {
        (DIR_DEAD, TERM_X),
        (DIR_UNDECLARED, TERM_Y),
        (DIR_UNREACHABLE, TERM_Z),
    }, (
        f"one round recording dead={[TERM_X]}, undeclared={[TERM_Y]}, unreachable={[TERM_Z]} "
        f"corroborated {sorted(got)}; C-3 §3 spells pairs `(direction, term)` with direction "
        f"in {list(DIRECTIONS)} — a bare term set is exactly the conflation the pass exists "
        "to avoid"
    )


def test_pin2_window_semantics_table(history) -> None:
    """The contract's table, on a history built through `append_term_history`.

    Rounds R1{dead: x}, R2{undeclared: x}, R3{dead: y, unreachable: z}:
      window None => every pair       (the any-prior union — today)
      window 1    => R3's pairs only
      window 2    => R2 + R3
    """
    recorded = history(((TERM_X,), (), ()), ((), (TERM_X,), ()), ((TERM_Y,), (), (TERM_Z,)))
    assert len(recorded) == 3, f"fixture wall: three appends recorded {len(recorded)} rounds"

    r1 = {(DIR_DEAD, TERM_X)}
    r2 = {(DIR_UNDECLARED, TERM_X)}
    r3 = {(DIR_DEAD, TERM_Y), (DIR_UNREACHABLE, TERM_Z)}
    expected = {
        None: r1 | r2 | r3,
        1: r3,
        2: r2 | r3,
        3: r1 | r2 | r3,
        10: r1 | r2 | r3,
    }
    for window, want in expected.items():
        got = _corroborated(recorded, window=window)
        assert got == want, (
            f"window={window!r} over rounds [dead:{{{TERM_X}}}], [undeclared:{{{TERM_X}}}], "
            f"[dead:{{{TERM_Y}}}, unreachable:{{{TERM_Z}}}] corroborated {sorted(got)}; the "
            f"contract's table says {sorted(want)} (a window of N unions the LAST N recorded "
            "rounds; None unions them all, and a window longer than the history is the whole "
            "history)"
        )


def test_pin2_window_reads_the_last_rounds_not_the_first(history) -> None:
    recorded = history(((TERM_X,), (), ()), ((TERM_Y,), (), ()), ((TERM_Z,), (), ()))
    got = _corroborated(recorded, window=2)
    assert got == {(DIR_DEAD, TERM_Y), (DIR_DEAD, TERM_Z)}, (
        f"window=2 over three dead rounds corroborated {sorted(got)} — the window is the "
        "TAIL (history[-2:]), which is the whole point: a finding from an old round must age "
        "OUT of the corroboration set"
    )


def test_pin2_direction_flip_never_corroborates(history) -> None:
    """DIRECTION MATTERS (C-3 §3, stated in capitals there): a term dead in one
    round and undeclared in the next corroborates NEITHER finding.

    This is the b003 failure itself — the instrument disagreeing with itself
    about the same term is evidence about the audit, not about the game.
    """
    recorded = history(((TERM_X,), (), ()), ((), (TERM_X,), ()))
    everything = _corroborated(recorded)

    assert (DIR_DEAD, TERM_X) in everything and (DIR_UNDECLARED, TERM_X) in everything
    assert _corroborated(recorded, window=1) == {(DIR_UNDECLARED, TERM_X)}, (
        f"the last round called {TERM_X!r} undeclared, so window 1 corroborates ONLY "
        f"({DIR_UNDECLARED!r}, {TERM_X!r}); a set carrying ({DIR_DEAD!r}, {TERM_X!r}) would "
        "let a rotation vouch for itself across directions"
    )
    assert (DIR_DEAD, TERM_X) not in _corroborated(recorded, window=1)


def test_pin2_empty_history_corroborates_nothing() -> None:
    """A cold start is a cold start whatever the window says."""
    assert _corroborated([]) == frozenset()
    assert _corroborated([], window=1) == frozenset()
    assert _corroborated([], window=None) == frozenset()


def test_pin2_entries_are_validated_outside_the_window() -> None:
    """"every entry validated regardless of window" — a malformed round the
    window would skip is still a corrupt sidecar, and a corrupt sidecar is
    exactly what must not be read past in silence."""
    good = {
        s3_verify.HISTORY_TS_KEY: "now",
        DIR_DEAD: [TERM_X],
        DIR_UNDECLARED: [],
        DIR_UNREACHABLE: [],
    }
    broken = {**good, DIR_DEAD: "not-a-list"}
    with pytest.raises(ValueError):
        _corroborated([broken, good], window=1)


@pytest.mark.parametrize(
    "value", [0, -1, True, "1", 1.5, [1]], ids=["zero", "negative", "bool", "str", "float", "list"]
)
def test_pin2_bad_window_argument_raises(history, value: object) -> None:
    """The function is called by the report seam with a config-read value, but a
    direct caller gets the same guarantee the config reader gives."""
    recorded = history(((TERM_X,), (), ()))
    with pytest.raises(ValueError):
        _corroborated(recorded, window=value)


# ==========================================================================
# PIN 3 — _apply_term_corroboration
# ==========================================================================


def test_pin3_signature_mirrors_apply_corroboration() -> None:
    fn = _attr("_apply_term_corroboration", "C-3 §4 names it")
    params = list(inspect.signature(fn).parameters.values())
    assert len(params) == 2, (
        f"_apply_term_corroboration takes {[p.name for p in params]}; C-3 §4 spells "
        "`(diff, corroborated=None)`, mirroring `_apply_corroboration`"
    )
    assert params[1].name == "corroborated" and params[1].default is None


def test_pin3_none_returns_the_diff_untouched() -> None:
    """`None` means the knob is OFF: the diff itself, unchanged, no record key —
    the default everywhere, so a batch that does not opt in gets today's bytes."""
    diff = _synthetic_diff(dead=(TERM_X,), undeclared=(TERM_Y,), unreachable=(TERM_Z,))
    original = copy.deepcopy(diff)

    for label, out in (("default", _apply(diff)), ("explicit None", _apply(diff, None))):
        assert out == original, f"knob off ({label}) changed the diff: {out!r}"
        assert RECORD_KEY not in out, (
            f"knob off ({label}) added a {RECORD_KEY} record — an absent knob is "
            "byte-identical behavior"
        )
    assert diff == original, "_apply_term_corroboration mutated the caller's diff"


def test_pin3_cold_start_demotes_every_direction_with_its_code() -> None:
    """An EMPTY corroboration set is not `None`: on a cold start every finding is
    a first sighting, leaves its list and is recorded with the reject code it
    would have produced (ambiguity (d))."""
    key = _record_key()
    diff = _synthetic_diff(dead=(TERM_X,), undeclared=(TERM_Y,), unreachable=(TERM_Z,))

    out = _apply(diff, frozenset())

    for direction, term in ((DIR_DEAD, TERM_X), (DIR_UNDECLARED, TERM_Y), (DIR_UNREACHABLE, TERM_Z)):
        assert out[DIRECTION_LIST[direction]] == [], (
            f"{term!r} is still in {DIRECTION_LIST[direction]!r} after a cold-start pass — a "
            "first sighting leaves the reject-bearing list, exactly as an uncorroborated "
            "lever leaves `undeclared_deceptions`"
        )
    assert {(entry["term"], entry["code"]) for entry in out[key]} == {
        (TERM_X, DIRECTION_CODE[DIR_DEAD]),
        (TERM_Y, DIRECTION_CODE[DIR_UNDECLARED]),
        (TERM_Z, DIRECTION_CODE[DIR_UNREACHABLE]),
    }, (
        f"{key} recorded {out[key]}; each entry is {{term, code, note}} with `code` the "
        "reject code the finding WOULD have produced, so nothing the audit found is lost"
    )
    for entry in out[key]:
        assert set(entry) == RECORD_ENTRY_KEYS, (
            f"{key} entry {entry!r} must have exactly {sorted(RECORD_ENTRY_KEYS)} — the "
            "`exempted` and `uncorroborated_levers` records both pin their key set exactly"
        )
        assert isinstance(entry["note"], str) and entry["note"].strip(), (
            "the note is a FIRST_SIGHTING-style constant explaining why this finding did not "
            f"reject, got {entry['note']!r}"
        )
    s3_verify._validate_diff(out)


def test_pin3_corroborated_pair_stays_a_finding() -> None:
    """Only FIRST sightings move: a pair the history already carries in the SAME
    direction keeps its power to reject."""
    diff = _synthetic_diff(dead=(TERM_X,), undeclared=(TERM_Y,))

    out = _apply(diff, frozenset({(DIR_DEAD, TERM_X)}))

    assert out["dead_spec_terms"] == [TERM_X], (
        f"{TERM_X!r} was corroborated as {DIR_DEAD!r} and must stay a reject-bearing finding"
    )
    assert out["undeclared_terms"] == [], f"{TERM_Y!r} is a first sighting and must be demoted"
    assert [entry["term"] for entry in out[RECORD_KEY]] == [TERM_Y]


def test_pin3_wrong_direction_does_not_corroborate() -> None:
    """The pair is the unit: `(undeclared, x)` in the history does not rescue a
    `dead` finding on the same term."""
    diff = _synthetic_diff(dead=(TERM_X,))
    out = _apply(diff, frozenset({(DIR_UNDECLARED, TERM_X)}))
    assert out["dead_spec_terms"] == [], (
        f"a recorded ({DIR_UNDECLARED!r}, {TERM_X!r}) corroborated a {DIR_DEAD!r} finding — "
        "C-3 §3: a term dead in one round and undeclared in the next never corroborates "
        "either finding"
    )


def test_pin3_is_idempotent() -> None:
    """A second application finds the terms already moved and leaves the record
    alone, so the report builder can re-assert the pass over a diff a caller
    already applied it to (the `_apply_exemptions` / `_apply_corroboration`
    rule)."""
    diff = _synthetic_diff(dead=(TERM_X,), unreachable=(TERM_Z,))
    once = _apply(diff, frozenset())
    twice = _apply(once, frozenset())
    assert twice == once, (
        f"applying twice changed the diff:\n once={json.dumps(once, sort_keys=True)}\n"
        f"twice={json.dumps(twice, sort_keys=True)}"
    )


def test_pin3_record_is_sorted_by_term_then_code() -> None:
    """Ambiguity (e): the mirror of `_apply_exemptions`' key — SUBJECT first,
    then the code — so a report diff is stable bytes across runs."""
    diff = _synthetic_diff(dead=(TERM_Z, TERM_X), undeclared=(TERM_Y,), unreachable=())
    out = _apply(diff, frozenset())
    entries = out[RECORD_KEY]
    assert entries == sorted(entries, key=lambda entry: (entry["term"], entry["code"])), (
        f"{RECORD_KEY} is {[(e['term'], e['code']) for e in entries]} — C-3 §4 says the record "
        "is sorted, and `_apply_exemptions` sorts by (term, would_have_been). If lead "
        "adjudicates a code-first order, this single test moves"
    )


def test_pin3_validate_diff_learns_the_optional_key() -> None:
    """`_validate_diff` accepts the new record exactly the way it learned
    `uncorroborated_levers`: optional, so every b7.1 report written before this
    knob existed still validates, and entry-shape validated when present."""
    key = _record_key()
    clean = _synthetic_diff()
    s3_verify._validate_diff(clean)
    assert key not in clean

    good = {**clean, key: [{"term": TERM_X, "code": DIRECTION_CODE[DIR_DEAD], "note": "n"}]}
    s3_verify._validate_diff(good)

    for broken, why in (
        ({"term": TERM_X, "code": DIRECTION_CODE[DIR_DEAD]}, "no `note`"),
        ({"term": TERM_X, "note": "n"}, "no `code`"),
        ({"code": DIRECTION_CODE[DIR_DEAD], "note": "n"}, "no `term`"),
        ({"term": TERM_X, "code": DIRECTION_CODE[DIR_DEAD], "note": "n", "x": 1}, "an extra key"),
        ({"term": 1, "code": DIRECTION_CODE[DIR_DEAD], "note": "n"}, "a non-string term"),
    ):
        with pytest.raises(ValueError):
            s3_verify._validate_diff({**clean, key: [broken]})
            pytest.fail(f"a {key} entry with {why} validated: {broken!r}")


def test_pin3_validate_diff_pins_the_code_to_the_three_term_codes() -> None:
    """The mirror of `_validate_exempted`'s `would_have_been` check: a record
    naming a code this pass cannot produce would misreport what stopped
    rejecting, and the point of the list is that nothing is dropped silently."""
    key = _record_key()
    clean = _synthetic_diff()
    for code in (s3_verify.REJECT_UNDECLARED_DECEPTION, s3_verify.REJECT_SOLVER_QUALITY, "nope"):
        with pytest.raises(ValueError):
            s3_verify._validate_diff({**clean, key: [{"term": TERM_X, "code": code, "note": "n"}]})
            pytest.fail(
                f"a {key} entry claiming code {code!r} validated; only "
                f"{sorted(DIRECTION_CODE.values())} are findings this pass can demote"
            )


def test_pin3_exempt_term_never_reaches_the_term_lists(slot: _Slot, base_cfg: dict) -> None:
    """Exemptions keep running FIRST (C-3 §5): an exempt term's finding is
    recorded under `exempted` and is therefore never a first sighting either —
    one finding, one record, and the diff still validates."""
    key = _record_key()
    cfg = _cfg(base_cfg, corroboration=True, window=1, exempt=[EXEMPT_TERM])

    report = slot.run(cfg, dead=(EXEMPT_TERM,), undeclared=(TERM_Y,))

    assert report["verdict"] == VERDICT_PASS, report["reject_reasons"]
    diff = report["diff"]
    assert [entry["term"] for entry in diff[s3_verify.EXEMPTED_KEY]] == [EXEMPT_TERM]
    assert diff["dead_spec_terms"] == [] and diff["undeclared_terms"] == []
    assert [entry["term"] for entry in diff[key]] == [TERM_Y], (
        f"{key} is {diff[key]} — the exempt term was suppressed BEFORE the corroboration "
        f"pass, so it never reaches the term lists at all and only {TERM_Y!r} is a first "
        "sighting"
    )
    s3_verify._validate_diff(diff)
    assert all(entry[DIR_DEAD] == [] for entry in slot.term_entries()), (
        "the exempt term was appended to the term history — the round's three direction lists "
        "are taken from the diff AFTER exemptions, so an exempt finding cannot corroborate a "
        "later one"
    )


# ==========================================================================
# PIN 4 — assemble_report, end to end on a planted slot
# ==========================================================================


def test_pin4_cold_start_warns_and_starts_the_history(slot: _Slot, base_cfg: dict) -> None:
    """Round one has nothing behind it, so a real finding is recorded, not a
    reject — and the round records ITSELF for later rounds."""
    cfg = _cfg(base_cfg, corroboration=True, window=1)
    report = slot.run(cfg, dead=(TERM_X,))

    assert report["verdict"] == VERDICT_PASS, (
        f"the cold-start round rejected on a first sighting: {report['reject_reasons']}"
    )
    assert _recorded_pairs(report) == {(DIRECTION_CODE[DIR_DEAD], TERM_X)}
    assert len(slot.term_entries()) == 1, "the round must record itself for later rounds"
    assert slot.term_entries()[0][DIR_DEAD] == [TERM_X]


def test_pin4_consecutive_same_direction_sighting_rejects(slot: _Slot, base_cfg: dict) -> None:
    """The contract's second table: R1{undeclared: y}, R2{undeclared: y} — R2
    rejects y.  Window 1 narrows WHICH rounds corroborate; it never switches
    corroboration off."""
    cfg = _cfg(base_cfg, corroboration=True, window=1)
    first = slot.run(cfg, undeclared=(TERM_Y,))
    second = slot.run(cfg, undeclared=(TERM_Y,))

    assert first["verdict"] == VERDICT_PASS, first["reject_reasons"]
    assert second["verdict"] == VERDICT_REJECT, (
        f"{TERM_Y!r} was called undeclared in the IMMEDIATELY preceding round — that is the "
        f"stability bar met inside window 1, so the finding must reject; got "
        f"{second['reject_reasons']}"
    )
    assert _reason_codes(second) == [DIRECTION_CODE[DIR_UNDECLARED]]
    assert _reason_terms(second) == [TERM_Y]
    assert _recorded(second) == [], "a corroborated finding is a reject, not a warning"


def test_pin4_rotation_table_rejects_nothing(tmp_path: Path, cap: object, base_cfg: dict) -> None:
    """The contract's first table, driven through `assemble_report`:
    R1{dead: x}, R2{undeclared: x}, R3{dead: x} under window 1.

      R2 rejects nothing on x — the DIRECTION flipped;
      R3 rejects nothing      — R2 recorded no `dead` entry at all.

    This is the b003 slot-1 escalation: four rounds of rotating term findings
    unioned into the spec, 5 terms to 10, on no stable evidence at all.
    """
    slot = _Slot(tmp_path / "rotation", cap)
    cfg = _cfg(base_cfg, corroboration=True, window=1)

    r1 = slot.run(cfg, dead=(TERM_X,))
    r2 = slot.run(cfg, undeclared=(TERM_X,))
    r3 = slot.run(cfg, dead=(TERM_X,))

    for label, report, direction in (("R1", r1, DIR_DEAD), ("R2", r2, DIR_UNDECLARED), ("R3", r3, DIR_DEAD)):
        assert report["verdict"] == VERDICT_PASS, (
            f"{label} rejected under window 1: {report['reject_reasons']}. The three rounds "
            f"call {TERM_X!r} dead, then undeclared, then dead again — no two CONSECUTIVE "
            "rounds agree on a direction, so nothing here has corroborated anything"
        )
        assert report["reject_reasons"] == [], label
        assert _recorded_pairs(report) == {(DIRECTION_CODE[direction], TERM_X)}, (
            f"{label} did not record its demoted finding: {_recorded(report)} — nothing is "
            "dropped, the record is what S2 and R5 read"
        )
    assert len(slot.term_entries()) == 3, "every round appends its own entry"


def test_pin4_a_round_may_not_corroborate_itself(slot: _Slot, base_cfg: dict) -> None:
    """The frozen order: validate -> read knob+window -> READ history -> APPEND
    this round -> apply.  With any window the history read for round 1 is empty,
    not "this round"."""
    cfg = _cfg(base_cfg, corroboration=True)
    report = slot.run(cfg, dead=(TERM_X,), undeclared=(TERM_Y,), unreachable=(TERM_Z,))

    assert report["verdict"] == VERDICT_PASS, (
        "the cold-start round rejected itself: the history is read BEFORE this round is "
        f"appended, so a finding cannot vouch for itself; got {report['reject_reasons']}"
    )
    assert len(_recorded(report)) == 3
    assert len(slot.term_entries()) == 1


def test_pin4_history_accrues_even_with_the_knob_off(slot: _Slot, base_cfg: dict) -> None:
    """C-3 §5: the history is appended whether the knob is on or off, so a later
    knob-on run has REAL rounds behind it (the lever behavior, matched)."""
    off = _cfg(base_cfg)
    assert KNOB not in off["verifier"] and WINDOW_KEY not in off["verifier"]

    first = slot.run(off, undeclared=(TERM_Y,))
    assert first["verdict"] == VERDICT_REJECT, (
        "with the knob absent a term finding still rejects on one round's say-so — that is "
        f"canon, and it must not change; got {first['verdict']}"
    )
    assert len(slot.term_entries()) == 1, (
        f"a knob-off round wrote no term history ({slot.term_sidecar().name}); the record is "
        "kept either way, or turning the knob on later starts from nothing"
    )

    second = slot.run(_cfg(base_cfg, corroboration=True, window=1), undeclared=(TERM_Y,))
    assert second["verdict"] == VERDICT_REJECT, (
        "the knob-off round recorded a real sighting, so the first knob-ON round after it is "
        f"already corroborated; got {second['verdict']} with {_recorded(second)}"
    )
    assert len(slot.term_entries()) == 2


def test_pin4_report_records_the_window_when_the_pass_ran(slot: _Slot, base_cfg: dict) -> None:
    """`term_window` joins `OPTIONAL_REPORT_KEYS` and is written only when the
    term pass ran — N, or null for the any-prior mode (ambiguity (h))."""
    optional = _attr("OPTIONAL_REPORT_KEYS", "C-2 landed it; C-3 §6 adds the term key to it")
    assert getattr(s3_verify, "TERM_WINDOW_REPORT_KEY", None) == REPORT_WINDOW_KEY, (
        f"C-3 §6: TERM_WINDOW_REPORT_KEY = {REPORT_WINDOW_KEY!r}, got "
        f"{getattr(s3_verify, 'TERM_WINDOW_REPORT_KEY', None)!r}"
    )
    assert REPORT_WINDOW_KEY in optional, (
        f"{REPORT_WINDOW_KEY!r} is not in OPTIONAL_REPORT_KEYS {list(optional)} — a key "
        "written only sometimes has to be optional, or `validate_report` rejects it"
    )
    assert REPORT_WINDOW_KEY not in s3_verify.REPORT_KEYS, (
        "term_window is OPTIONAL, not part of the frozen b7.1 key set — every report written "
        "before this knob existed must still validate"
    )

    windowed = slot.run(_cfg(base_cfg, corroboration=True, window=2), dead=(TERM_X,))
    assert windowed.get(REPORT_WINDOW_KEY) == 2, (
        f"a verdict decided under a narrowed corroboration bar must say how narrow: "
        f"report[{REPORT_WINDOW_KEY!r}] = {windowed.get(REPORT_WINDOW_KEY)!r}, expected 2"
    )
    s3_verify.validate_report(windowed)

    any_prior = slot.run(_cfg(base_cfg, corroboration=True), dead=(TERM_X,))
    assert REPORT_WINDOW_KEY in any_prior and any_prior[REPORT_WINDOW_KEY] is None, (
        "with the pass running and no window the report records null (the any-prior mode), "
        f"got {any_prior.get(REPORT_WINDOW_KEY, '<absent>')!r}"
    )
    s3_verify.validate_report(any_prior)


def test_pin4_report_omits_the_window_when_the_pass_did_not_run(
    slot: _Slot, base_cfg: dict
) -> None:
    """Knob off: no key at all — that is what "canon-default runs write
    byte-identical reports" means."""
    report = slot.run(_cfg(base_cfg), dead=(TERM_X,))
    assert REPORT_WINDOW_KEY not in report, (
        f"a run that opted into nothing wrote {REPORT_WINDOW_KEY!r} = "
        f"{report.get(REPORT_WINDOW_KEY)!r}; C-3 §6 writes it only when the term pass ran"
    )
    s3_verify.validate_report(report)


def test_pin4_recorded_window_is_validated(slot: _Slot, base_cfg: dict) -> None:
    """Validated like `lever_window`: a positive int or null, nothing else — the
    report is read back off disk by the orchestrator and by R5."""
    report = slot.run(_cfg(base_cfg, corroboration=True, window=1), dead=(TERM_X,))
    for bad in (0, -1, "1", 1.5, True):
        with pytest.raises(ValueError):
            s3_verify.validate_report({**report, REPORT_WINDOW_KEY: bad})
            pytest.fail(f"report.{REPORT_WINDOW_KEY} = {bad!r} validated")


def test_pin4_knob_off_report_is_byte_identical_across_two_runs(
    slot: _Slot, base_cfg: dict
) -> None:
    """The byte-identity guarantee, twice running: with no knob set a term
    finding rejects exactly as it does today, and the two reports are the same
    bytes — the accruing sidecar changes nothing a report carries."""
    cfg = _cfg(base_cfg)
    for key in (KNOB, WINDOW_KEY, LEVER_KNOB, LEVER_WINDOW_KEY, "exempt_terms"):
        assert key not in cfg["verifier"], f"fixture wall: {key} survived _cfg"

    first = slot.run(cfg, dead=(TERM_X,), undeclared=(TERM_Y,))
    second = slot.run(cfg, dead=(TERM_X,), undeclared=(TERM_Y,))

    assert first["verdict"] == VERDICT_REJECT
    assert sorted(_reason_codes(first)) == sorted(
        [DIRECTION_CODE[DIR_DEAD], DIRECTION_CODE[DIR_UNDECLARED]]
    )
    assert RECORD_KEY not in first["diff"], (
        f"a run with no knob set carries a {RECORD_KEY} record: {first['diff'].get(RECORD_KEY)!r}"
    )
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True), (
        "two knob-off rounds over the same slot produced different reports — the term pass "
        "must be invisible when nothing opts into it, sidecar or no sidecar"
    )


# ==========================================================================
# PIN 5 — the S2 findings feed renders the advisory block
# ==========================================================================


@pytest.fixture
def reject_with_warning(slot: _Slot, base_cfg: dict) -> dict:
    """A REAL reject report that also carries a first-sighting record.

    R1 names two dead terms; R2 repeats one of them (corroborated -> rejects)
    and names a third (first sighting -> recorded).  That is exactly the state
    the advisory block exists to describe.
    """
    cfg = _cfg(base_cfg, corroboration=True, window=1)
    slot.run(cfg, dead=(TERM_X, TERM_Y))
    report = slot.run(cfg, dead=(TERM_X, TERM_Z))

    assert report["verdict"] == VERDICT_REJECT, report
    assert _reason_terms(report) == [TERM_X], report["reject_reasons"]
    assert [entry["term"] for entry in _recorded(report)] == [TERM_Z], _recorded(report)
    return report


def test_pin5_advisory_block_renders_after_the_reject_reasons(reject_with_warning: dict) -> None:
    """The frozen prose, the code+term of every entry, and its POSITION: after
    the reject-reason lines (ambiguity (g) — the wording is frozen, the wrap is
    the implementer's)."""
    rendered = s2_implement.findings_section(reject_with_warning)
    flat = _normalize(rendered)

    assert _normalize(ADVISORY_SENTENCE) in flat, (
        "the rendered findings section does not carry C-3's frozen advisory sentence "
        f"(normalized). Expected:\n  {_normalize(ADVISORY_SENTENCE)}\nGot:\n{rendered}"
    )
    entry = _recorded(reject_with_warning)[0]
    block_at = flat.index(ADVISORY_OPENING)
    assert entry["code"] in flat[block_at:] and entry["term"] in flat[block_at:], (
        f"the advisory block names neither {entry['code']!r} nor {entry['term']!r}; C-3 "
        "renders one line per entry: code, term"
    )
    assert flat.index(TERM_X) < block_at, (
        f"the advisory block was rendered BEFORE the reject-reason line for {TERM_X!r}; C-3 "
        "renders it AFTER them — the rebuild answers the rejects, and reads the warning as "
        "the next round's risk"
    )


def test_pin5_without_the_key_the_section_is_byte_identical(reject_with_warning: dict) -> None:
    """A knob-off report carries no such key, so `findings_section` must render
    the bytes it always did.  An EMPTY record is the same non-event as an absent
    one — C-3 renders the block only for a NON-EMPTY `uncorroborated_terms`."""
    absent = copy.deepcopy(reject_with_warning)
    del absent["diff"][RECORD_KEY]
    empty = copy.deepcopy(reject_with_warning)
    empty["diff"][RECORD_KEY] = []

    without = s2_implement.findings_section(absent)
    with_empty = s2_implement.findings_section(empty)
    with_block = s2_implement.findings_section(reject_with_warning)

    assert without == with_empty, (
        "an EMPTY uncorroborated_terms list rendered differently from an absent one; C-3 "
        "renders the block only when the key is non-empty, so the two must be the same bytes"
    )
    assert ADVISORY_OPENING not in without, (
        f"a report with no {RECORD_KEY} still rendered the advisory block:\n{without}"
    )
    assert with_block != without, "the record was carried and rendered nothing"
    assert with_block.endswith("\n") and without.endswith("\n"), (
        "findings_section is documented to end with a newline so an appended section leaves "
        "payload.md newline-terminated; the advisory block must not break that"
    )


# ==========================================================================
# PIN 6 — the lever machinery is untouched
# ==========================================================================


def test_pin6_lever_sidecar_and_entry_shape_are_pinned(slot: _Slot, base_cfg: dict) -> None:
    """C-3 §2: "The lever sidecar and its entry shape are pinned — do not touch
    them."  One round, both files, each still its own."""
    assert s3_verify.LEVER_HISTORY_SUFFIX == ".lever-history.json"
    assert s3_verify.HISTORY_TS_KEY == "ts" and s3_verify.HISTORY_DETECTED_KEY == "detected"

    slot.run(_cfg(base_cfg, lever_corroboration=True), levers=(LEVER_A,), dead=(TERM_X,))

    lever_entries = s3_verify.read_lever_history(slot.lever_sidecar())
    assert len(lever_entries) == 1
    assert set(lever_entries[0]) == {s3_verify.HISTORY_TS_KEY, s3_verify.HISTORY_DETECTED_KEY}, (
        f"the lever entry is now {sorted(lever_entries[0])} — C-3 pins it as "
        f"{{{s3_verify.HISTORY_TS_KEY}, {s3_verify.HISTORY_DETECTED_KEY}}} and adds its "
        "direction-keyed entry to a SEPARATE file"
    )
    assert lever_entries[0][s3_verify.HISTORY_DETECTED_KEY] == [LEVER_A]
    assert slot.term_sidecar() != slot.lever_sidecar()
    assert len(slot.term_entries()) == 1


def test_pin6_lever_corroboration_is_unchanged_under_the_term_knobs(
    tmp_path: Path, cap: object, base_cfg: dict
) -> None:
    """The corrwindow harness result, re-exercised (a test cannot assert that a
    sibling file was not edited, so the behavior is re-driven instead): a
    knob-off lever finding rejects every round, and a lever-corroborated one
    behaves the same whether the TERM knobs are set or not."""
    off = _Slot(tmp_path / "lever-off", cap)
    cfg_off = _cfg(base_cfg)
    for label, report in (
        ("round 1", off.run(cfg_off, levers=(LEVER_A,))),
        ("round 2", off.run(cfg_off, levers=(LEVER_A,))),
    ):
        assert report["verdict"] == VERDICT_REJECT, (
            f"{label}: with every knob absent an undeclared lever must still reject — got "
            f"{report['verdict']} with {report['reject_reasons']}"
        )
        assert _reason_codes(report) == [s3_verify.REJECT_UNDECLARED_DECEPTION], label

    on = _Slot(tmp_path / "lever-on", cap)
    cfg_on = _cfg(base_cfg, corroboration=True, window=1, lever_corroboration=True, lever_window=1)
    first = on.run(cfg_on, levers=(LEVER_A,))
    rotated = on.run(cfg_on, levers=(LEVER_B,))
    repeated = on.run(cfg_on, levers=(LEVER_B,))

    assert first["verdict"] == VERDICT_PASS, first["reject_reasons"]
    assert rotated["verdict"] == VERDICT_PASS, (
        "a ROTATED lever is a first sighting again under window 1, term knobs or no term "
        f"knobs; got {rotated['reject_reasons']}"
    )
    assert repeated["verdict"] == VERDICT_REJECT, (
        f"{LEVER_B!r} was named in the immediately preceding round, so the lever pass must "
        f"still reject it with the term pass running beside it; got {repeated['verdict']}"
    )
    assert _reason_codes(repeated) == [s3_verify.REJECT_UNDECLARED_DECEPTION]
    assert repeated.get(s3_verify.LEVER_WINDOW_REPORT_KEY) == 1, (
        "the lever pass stopped recording its own window once the term pass joined "
        f"OPTIONAL_REPORT_KEYS: {repeated.get(s3_verify.LEVER_WINDOW_REPORT_KEY)!r}"
    )
    assert repeated.get(REPORT_WINDOW_KEY) == 1, "both passes record their own window"
