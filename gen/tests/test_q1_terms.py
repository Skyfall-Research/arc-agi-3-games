"""Contract Q-1 — the IMPLEMENTER's own pins for `verifier.term_dispute_action`.

This is NOT the blind lane's file (`gen/tests/test_v2_terms.py`, written from
the contract alone; never read from here and never written by this lane). It
pins the things THIS lane decided and now has to keep true:

  * THE COMPARATOR, which the contract left to the implementer: a dispute needs
    SHARED GROUND — one evidence citation both terms cite, or one backticked
    construct both `term_sites` entries name — and nothing looser. Both halves
    are pinned green, and the red case (two findings in one file, no shared
    citation and no shared construct) is pinned beside them, because a false
    dispute silences a real finding and that is the only way this contract can
    make the pipeline worse (pins 1-3);
  * THE EXHIBIT, rebuilt hermetically from the four terms the contract names.
    `info.recall`/`agent.echo` pair on the `pend` site; `terrain.keyed` and
    `gate.key` do NOT, because the audit grounded `gate.key` in nothing at all
    — the measurement this lane reported and the reason the game still rejects
    under `record` (pin 4). The REAL report is read read-only by pin 11 and
    never rebuilt from, and nothing here writes under the real `out/`;
  * THE AUDITOR'S BREAK: a well-formed `distinguishes` makes a finding
    undisputed, so it rejects under `record` too; a malformed one is loud at
    claims validation, and one naming a term the SPEC never declared is
    silently no break rather than an error (pins 5-7);
  * THE KNOB MATRIX: absent == explicit `reject` == today's verdict, reasons
    and report bytes; `record` moves only the disputed rows; anything else is
    loud at read time, on a dry run too (pins 8-10);
  * THE SCHEMA IS ADDITIVE: every verifier report shipped before this contract
    still validates, and a pre-Q-1 `terms` claim with no `distinguishes` still
    validates (pins 11-12);
  * THE SEAMS: the prompt QUOTES the requirement (prompt-sync, not a second
    hand-copied spelling), the stop's reader never raises on a report that is
    missing, malformed or pre-Q-1, and the arming is template + overlay with
    the CODE default still `reject` (pins 13-15).

HOUSE RULE: every test here is hermetic — tmp roots only, no network, no
driver, no spend, duckWM read-only, and nothing is ever WRITTEN under the real
`out/` or `games/`. The two pins that read the real corpus open it read-only.
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
CORPUS = REPO_ROOT / "out" / "corpus"
#: The contract's exhibit, read READ-ONLY by pin 11 and by nothing else.
# LEAD REPOINT 2026-10-06 (standing law: exhibit pins never cite live operator
# surfaces — fourth occurrence). The live report was ROUND 7's when this file
# measured it; Q-1's own live acceptance then ran round 8 and overwrote it
# (with `term_disputes` present and `distinguishes` on both exhibit terms),
# and the slot is parked-but-LIFTABLE so it can move again. Round 8's bytes
# are frozen in gen/tests/fixtures/; round 7's one-pair measurement survives
# in this file's hermetic pins and the contract handback.
EXHIBIT_REPORT = (
    Path(__file__).resolve().parent
    / "fixtures" / "two-keys-one-echo-verifier-report-round8-frozen-2026-10-06.json"
)

KNOB = "term_dispute_action"
REJECT, RECORD = "reject", "record"
DISPUTES = "term_disputes"
DISTINGUISHES = "distinguishes"
VERDICT_PASS, VERDICT_REJECT = "pass", "reject"
MODE_FULL, MODE_DRY = "full", "dry-run"

#: The exhibit's four signed terms, two ADJACENT pairs (contract §The measured
#: class). X_* are the audit's undeclared findings, Y_* the spec's declarations.
X_RECALL, Y_ECHO = "info.recall", "agent.echo"
X_KEYED, Y_KEY = "terrain.keyed", "gate.key"
#: A declared term nothing in these fixtures disputes — the control that proves
#: the knob moves disputed rows and not term findings as a class.
CLEAN_TERM = "move.grid"

GAME_ID = "q1-terms-synthetic"
SYNTHETIC_NOTE = "synthetic fixture"
#: The shared construct of the exhibit's live pair: ONE queue, two signed names.
PEND = "pend"


# --------------------------------------------------------------------------
# synthetic verifier inputs (the real exhibit is quoted by pin 11 alone)
# --------------------------------------------------------------------------


def _evidence(*lines: int) -> list[dict]:
    return [{"path": "game.py", "line": line, "note": SYNTHETIC_NOTE} for line in lines]


class Claim:
    """One term as the blind audit reported it: its citations and its site.

    The two grounding surfaces are kept separate because the comparator reads
    both and the exhibit only pairs on the second one.
    """

    def __init__(
        self,
        term: str,
        *,
        lines: tuple[int, ...] = (10,),
        site: str | None = None,
        frames: tuple[str, ...] = (),
        site_lines: tuple[int, ...] | None = None,
        distinguishes: object = None,
        reachable: bool = True,
        inventoried: bool = True,
    ) -> None:
        self.term = term
        self.lines = lines
        self.site = site
        self.frames = frames
        self.site_lines = lines if site_lines is None else site_lines
        self.distinguishes = distinguishes
        self.reachable = reachable
        self.inventoried = inventoried

    def term_entry(self) -> dict | None:
        """The `claims.terms[]` row, or None for a term the audit never saw."""
        if not self.lines and not self.frames:
            return None
        entry: dict = {"term": self.term, "reachable": self.reachable,
                       "evidence": _evidence(*self.lines)}
        if self.frames:
            entry["frame_refs"] = list(self.frames)
        if self.distinguishes is not None:
            entry[DISTINGUISHES] = self.distinguishes
        return entry

    def site_entry(self) -> dict | None:
        """The `claims.term_sites[]` row — `site: null` is a REAL answer (R-18)."""
        if not self.inventoried:
            return None
        if self.site is None:
            return {"term": self.term, "site": None}
        return {"term": self.term, "site": self.site,
                "evidence": _evidence(*self.site_lines)}


def _claims(*claims: Claim, sites: bool = True) -> dict:
    out: dict = {
        "terms": [entry for entry in (c.term_entry() for c in claims) if entry is not None],
        "dead_code": [],
        "deceptions": [],
        "enforcement": [],
        "notes": SYNTHETIC_NOTE,
    }
    if sites:
        out[s3_verify.TERM_SITES_KEY] = [
            entry for entry in (c.site_entry() for c in claims) if entry is not None
        ]
    return out


def _spec(*terms: str) -> dict:
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
    """The vocabulary this file's synthetic inputs stand on, checked once.

    Every one of these is a signed term, so a vocabulary change breaks the
    fixture loudly here instead of silently turning a pin green for the wrong
    reason.
    """
    vocab = s3_verify.signed_vocab()
    for term in (X_RECALL, Y_ECHO, X_KEYED, Y_KEY, CLEAN_TERM):
        assert term in vocab, f"fixture wall: {term!r} left the signed vocabulary"


class _Slot:
    """One planted slot: a toy worker dir and as many FULL verify rounds as wanted.

    A round is driven through `assemble_report` — the seam that has the run's
    config, its diff and the worker all in hand, which is where both leniency
    rulings are applied — and the diff is built on the PURE path by
    `compute_diff`. The L-1 file's `_Slot`, with the term fixtures this one needs.
    """

    def __init__(self, root: Path, cap: object) -> None:
        import shutil

        self.root = root
        self.worker = root / "slot-1"
        shutil.copytree(TOY_WORKER, self.worker, ignore=shutil.ignore_patterns("__pycache__"))
        self.frames_path = root / s3_verify.FRAMES_NAME
        self.frames_path.write_text("{}", encoding="utf-8")
        self._cap = cap

    def run(self, cfg: dict, *claims: Claim, declared: tuple[str, ...],
            sites: bool = True, mode: str = MODE_FULL) -> dict:
        built = _claims(*claims, sites=sites)
        diff = s3_verify.compute_diff(built, _spec(*declared))
        return s3_verify.assemble_report(
            game_id=GAME_ID,
            worker=self.worker,
            mode=mode,
            cfg=cfg,
            cap=self._cap,
            checks=[],
            frames_path=self.frames_path,
            agent=_agent(built),
            diff=diff,
            spec_hash=None,
        )


@pytest.fixture
def slot(tmp_path: Path, cap: object) -> _Slot:
    return _Slot(tmp_path, cap)


def _codes(rows: list[dict]) -> list[str]:
    return [row["code"] for row in rows]


def _terms(rows: list[dict]) -> list[str]:
    return [row["term"] for row in rows if "term" in row]


def _comparable(report: dict) -> dict:
    """A report with the per-run values that are never equal stripped."""
    out = copy.deepcopy(report)
    out.pop("worker", None)
    return out


# --------------------------------------------------------------------------
# the exhibit, rebuilt hermetically (contract §5: "never write under real out/")
# --------------------------------------------------------------------------


def _echo_pair(**kwargs: object) -> tuple[Claim, Claim]:
    """The live half of the exhibit: two names, one `pend` queue, no shared line.

    The line numbers are the real ones (`info.recall` 479/539/848 against
    `agent.echo` 579/581) precisely because they do NOT intersect — the pairing
    this contract exists for is carried by the SITE prose alone, and a fixture
    that shared a citation would pin a comparator the exhibit never exercises.
    """
    recall = Claim(
        X_RECALL,
        lines=(479, 539, 848),
        site=f"the `{PEND}` tuple: load-bearing and drawn by nothing in _repaint",
        **kwargs,
    )
    echo = Claim(
        Y_ECHO,
        lines=(579, 581),
        site=f"the `{PEND}` FIFO of direction deltas, popped at length > ECHO_LAG",
    )
    return recall, echo


def _keyed_pair() -> tuple[Claim, Claim]:
    """The DEAD half: a declared term the audit grounded in nothing at all.

    `gate.key` carries `site: null` and no `terms` row — the real reply's shape —
    so it has no evidence to share and cannot pair with anything. This is the
    measurement, as a fixture.
    """
    keyed = Claim(
        X_KEYED,
        lines=(468, 476),
        site="gate_blocks' `if colour != key: return True` — passability by body colour",
    )
    key = Claim(Y_KEY, lines=(), site=None)
    return keyed, key


# --------------------------------------------------------------------------
# PIN 1-3 — the comparator (the part the contract left to this lane)
# --------------------------------------------------------------------------


def test_pin1_two_sites_naming_one_construct_pair() -> None:
    """A shared backticked construct is shared ground, with ZERO shared citations."""
    recall, echo = _echo_pair()
    claims = _claims(recall, echo)
    diff = s3_verify.compute_diff(claims, _spec(Y_ECHO))
    citations_x, constructs_x = s3_verify._dispute_grounding(claims, X_RECALL)
    citations_y, constructs_y = s3_verify._dispute_grounding(claims, Y_ECHO)
    assert not (citations_x & citations_y), (
        "fixture wall: the exhibit's two terms share NO citation, which is the whole "
        f"reason the site surface exists; got {sorted(citations_x & citations_y)}"
    )
    assert constructs_x & constructs_y == {PEND}, (
        f"Q-1 §1: both sites name `{PEND}`, so the comparator must see one shared "
        f"construct; it sees {sorted(constructs_x & constructs_y)}"
    )
    disputes = s3_verify.term_disputes(claims, diff)
    assert [(e["term"], e["disputed_with"], e["code"]) for e in disputes] == [
        (X_RECALL, Y_ECHO, s3_verify.REJECT_UNDECLARED_TERM)
    ], f"Q-1 §1: the pair must land as one dispute entry; got {disputes}"
    assert PEND in disputes[0]["shared"], (
        f"the record must say WHAT paired them so it can be argued with; got "
        f"{disputes[0]['shared']!r}"
    )


def test_pin2_one_shared_citation_is_also_shared_ground() -> None:
    """The other surface, alone: one `path:line` both terms cite, no shared site."""
    x = Claim(X_RECALL, lines=(479,), site="the queue nothing repaints")
    y = Claim(Y_ECHO, lines=(479,), site="the replay of the action history")
    claims = _claims(x, y)
    diff = s3_verify.compute_diff(claims, _spec(Y_ECHO))
    _, constructs_x = s3_verify._dispute_grounding(claims, X_RECALL)
    _, constructs_y = s3_verify._dispute_grounding(claims, Y_ECHO)
    assert not (constructs_x & constructs_y), "fixture wall: these sites share no construct"
    disputes = s3_verify.term_disputes(claims, diff)
    assert len(disputes) == 1 and disputes[0]["term"] == X_RECALL, (
        f"Q-1 §1: one shared citation is shared evidence; got {disputes}"
    )
    assert "game.py:479" in disputes[0]["shared"], (
        f"the record must name the shared citation; got {disputes[0]['shared']!r}"
    )


def test_pin3_no_shared_ground_is_no_dispute() -> None:
    """THE RED CASE, and the one that matters most.

    Two findings in one file, adjacent line numbers, prose full of the same
    English words — and no shared citation and no shared construct. A comparator
    that pairs this silences a real finding, which is the only way this contract
    can leave the pipeline worse than it found it.
    """
    keyed, key = _keyed_pair()
    neighbour = Claim(
        "gate.remote",
        lines=(447, 471),
        site="the uc/um latch: `return not (uc if colour == CYAN else um)` is the passability",
    )
    claims = _claims(keyed, key, neighbour)
    diff = s3_verify.compute_diff(claims, _spec(Y_KEY, "gate.remote"))
    assert X_KEYED in diff["undeclared_terms"], "fixture wall: X must be an undeclared finding"
    assert s3_verify.term_disputes(claims, diff) == [], (
        "Q-1 §1: 468/476 against 447/471 share no citation and the two sites share no "
        "construct, so there is no dispute — a shared FILE, a nearby LINE and overlapping "
        "prose are none of them evidence that one behaviour was named twice"
    )


def test_pin3b_a_trivial_shared_span_is_not_a_construct() -> None:
    """`_MIN_CONSTRUCT_CHARS`: two terms quoting `0` have not named one mechanic."""
    x = Claim(X_RECALL, lines=(1,), site="the counter starts at `0` and is never drawn")
    y = Claim(Y_ECHO, lines=(2,), site="the lag is `0` until the queue fills")
    claims = _claims(x, y)
    diff = s3_verify.compute_diff(claims, _spec(Y_ECHO))
    assert s3_verify.term_disputes(claims, diff) == [], (
        "a backticked literal is not a construct's name; pairing on one would dispute "
        "any two terms whose prose happens to quote the same number"
    )


# --------------------------------------------------------------------------
# PIN 4 — the exhibit, end to end, hermetically
# --------------------------------------------------------------------------


def test_pin4_the_exhibit_pairs_one_of_its_two_findings(slot: _Slot) -> None:
    """THE MEASUREMENT, as a pin: one pair, one unpairable finding, still a reject.

    b005r2-auto's two-keys-one-echo re-parked on `undeclared-term ×2`. Under
    `record` ONE of the two leaves the reject path. `terrain.keyed` cannot:
    `gate.key` is grounded in nothing, so there is nothing for it to share. The
    contract's live-acceptance outcome (a) — "the findings pair → the ladder runs
    → packaged" — therefore does NOT follow from arming the knob alone, and this
    pin is where that stays true.

    MEASURED DIFFERENCE from the real round, stated because the fixture is
    honest about it: rebuilt with the corroboration knobs OFF, `gate.key` is
    also a live `dead-spec-term` row. In the real round C-3's term
    corroboration had already demoted that row into `uncorroborated_terms` as a
    first sighting, which is why the shipped report's `dead_spec_terms` is empty
    and its two rejects are the undeclared pair alone. The dead-spec half is
    pinned by 4c; what this pin owns is that Q-1 moves EXACTLY the disputed row
    and leaves both of the others standing.
    """
    recall, echo = _echo_pair()
    keyed, key = _keyed_pair()
    declared = (Y_ECHO, Y_KEY, CLEAN_TERM)
    clean = Claim(CLEAN_TERM, lines=(570,), site="the DIRS lookup, one discrete cell step")
    report = slot.run(_cfg(RECORD), recall, echo, keyed, key, clean, declared=declared)

    assert [(e["term"], e["disputed_with"]) for e in report[DISPUTES]] == [
        (X_RECALL, Y_ECHO)
    ], f"the exhibit has exactly ONE live dispute; got {report[DISPUTES]}"
    assert report["verdict"] == VERDICT_REJECT, (
        "the exhibit still rejects under `record`: `terrain.keyed` is undisputed"
    )
    assert sorted(_terms(report["reject_reasons"])) == sorted([X_KEYED, Y_KEY]), (
        f"only the DISPUTED row may move: {X_KEYED} is unpairable and {Y_KEY}'s dead-spec "
        f"row is nothing's Y. Got {report['reject_reasons']}"
    )
    assert s3_verify.REJECT_UNDECLARED_TERM not in _codes(report["reject_reasons"]) or (
        X_RECALL not in _terms(report["reject_reasons"])
    ), f"{X_RECALL} must have left the reject path; got {report['reject_reasons']}"


def test_pin4b_the_same_exhibit_under_the_default_rejects_on_both(slot: _Slot) -> None:
    recall, echo = _echo_pair()
    keyed, key = _keyed_pair()
    clean = Claim(CLEAN_TERM, lines=(570,), site="the DIRS lookup")
    report = slot.run(_cfg(), recall, echo, keyed, key, clean,
                      declared=(Y_ECHO, Y_KEY, CLEAN_TERM))
    assert sorted(_terms(report["reject_reasons"])) == sorted([X_RECALL, X_KEYED, Y_KEY]), (
        "Q-1 §3: under the default an UNDISPUTED and a DISPUTED finding both reject — the "
        f"knob is the only thing that moves either; got {report['reject_reasons']}"
    )
    assert [(e["term"], e["disputed_with"]) for e in report[DISPUTES]] == [(X_RECALL, Y_ECHO)], (
        "…and the dispute is RECORDED anyway, so the human deciding whether to arm the "
        f"knob can see it; got {report[DISPUTES]}"
    )


def test_pin4c_the_dead_half_of_one_misattribution_rides_the_same_dispute(
    slot: _Slot,
) -> None:
    """Q-1 §3: "the two halves of one misattribution must not count twice".

    The exhibit does NOT exercise this — C-3's term corroboration had already
    demoted its `gate.key` dead-spec finding into `uncorroborated_terms` before
    the diff reached a verdict (measured; see this lane's handback) — so the
    rule is pinned on the fixture that does: a declared Y the audit never saw,
    disputed by an X that shares its ground.
    """
    x = Claim(X_RECALL, lines=(479,), site=f"the `{PEND}` tuple")
    # First, the control that fixes what "dead" means here: a Y the audit DID
    # cite is seen, so it is not a dead-spec finding at all.
    y_seen = Claim(Y_ECHO, lines=(479,), site=None)
    claims = _claims(x, y_seen)
    diff = s3_verify.compute_diff(claims, _spec(Y_ECHO))
    assert diff["dead_spec_terms"] == [], "fixture wall: a cited Y is SEEN, not dead"

    # The real dead-spec shape: Y declared, absent from `terms` entirely, and
    # grounded by a SITE that shares X's construct.
    y_sited = Claim(Y_ECHO, lines=(), site=f"the `{PEND}` FIFO, replayed four behind")
    claims = _claims(x, y_sited)
    diff = s3_verify.compute_diff(claims, _spec(Y_ECHO))
    assert diff["dead_spec_terms"] == [Y_ECHO], (
        f"fixture wall: Y must be a dead-spec finding; diff says {diff['dead_spec_terms']}"
    )
    disputes = s3_verify.term_disputes(claims, diff)
    assert {(e["term"], e["code"]) for e in disputes} == {
        (X_RECALL, s3_verify.REJECT_UNDECLARED_TERM),
        (Y_ECHO, s3_verify.REJECT_DEAD_SPEC_TERM),
    }, f"Q-1 §3: both halves of one misattribution ride one dispute; got {disputes}"

    verdict, kept = s3_verify._apply_term_dispute_action(
        VERDICT_REJECT,
        [
            s3_verify._reason(s3_verify.REJECT_UNDECLARED_TERM, "x", term=X_RECALL),
            s3_verify._reason(s3_verify.REJECT_DEAD_SPEC_TERM, "y", term=Y_ECHO),
        ],
        disputes,
        RECORD,
    )
    assert (verdict, kept) == (VERDICT_PASS, []), (
        f"both halves must leave the reject path together; got {verdict} / {kept}"
    )


def test_pin4d_a_dead_spec_term_nothing_disputes_still_rejects() -> None:
    """The scope guard: `dead-spec-term` is not made lenient as a class."""
    verdict, kept = s3_verify._apply_term_dispute_action(
        VERDICT_REJECT,
        [s3_verify._reason(s3_verify.REJECT_DEAD_SPEC_TERM, "y", term=Y_KEY)],
        [{"term": X_RECALL, "code": s3_verify.REJECT_UNDECLARED_TERM,
          "disputed_with": Y_ECHO, "shared": "both sites name `pend`"}],
        RECORD,
    )
    assert verdict == VERDICT_REJECT and _terms(kept) == [Y_KEY], (
        "only the Y of a LIVE dispute is moved; every other dead-spec finding is "
        f"`decide_verdict`'s decision standing as made. Got {verdict} / {kept}"
    )


# --------------------------------------------------------------------------
# PIN 5-7 — the auditor's break
# --------------------------------------------------------------------------


def test_pin5_a_wellformed_distinguishes_makes_the_finding_undisputed(slot: _Slot) -> None:
    """Q-1 §2: it rejects even under `record` — the auditor answered the question."""
    recall, echo = _echo_pair(
        distinguishes={"term": Y_ECHO,
                       "clause": "the queue is never drawn, so the demand is on memory; "
                                 "agent.echo is an entity replaying the action history"}
    )
    report = slot.run(_cfg(RECORD), recall, echo, declared=(Y_ECHO,))
    assert report[DISPUTES] == [], (
        f"Q-1 §2: a well-formed break leaves NO dispute to record; got {report[DISPUTES]}"
    )
    assert report["verdict"] == VERDICT_REJECT and _terms(report["reject_reasons"]) == [X_RECALL], (
        "Q-1 §2: an undisputed finding rejects under `record` exactly as today; got "
        f"{report['verdict']} / {report['reject_reasons']}"
    )


def test_pin6_a_distinguishes_naming_an_undeclared_term_is_no_break() -> None:
    """Silently no answer, and deliberately not an error.

    "Names a DECLARED term" is the half `validate_claims` cannot check (it knows
    the vocabulary, not the spec), so it is decided here — and WITHOUT raising,
    because discarding a paid blind audit over an auditor naming a term the spec
    happens not to carry is a cost the contract never asked for.
    """
    recall, echo = _echo_pair(
        distinguishes={"term": CLEAN_TERM, "clause": "a real clause about the wrong term"}
    )
    claims = _claims(recall, echo)
    diff = s3_verify.compute_diff(claims, _spec(Y_ECHO))
    s3_verify.validate_claims(claims)  # loud on shape, silent on declaredness
    disputes = s3_verify.term_disputes(claims, diff)
    assert [e["term"] for e in disputes] == [X_RECALL], (
        f"{CLEAN_TERM} is not declared by this spec, so the break does not apply and the "
        f"dispute stands; got {disputes}"
    )


@pytest.mark.parametrize(
    ("value", "why"),
    [
        ("agent.echo", "a bare string is not {term, clause}"),
        ({"term": Y_ECHO}, "no clause"),
        ({"clause": "words"}, "no term"),
        ({"term": Y_ECHO, "clause": ""}, "an empty clause is no reason"),
        ({"term": Y_ECHO, "clause": "words", "extra": 1}, "a key nobody asked for"),
        ({"term": "not-a-term-id", "clause": "words"}, "not a vocabulary id"),
        ({"term": "fake.term", "clause": "words"}, "outside the signed vocabulary"),
        ({"term": X_RECALL, "clause": "words"}, "distinguished from itself"),
    ],
)
def test_pin7_a_malformed_distinguishes_is_loud_at_claims_validation(
    value: object, why: str
) -> None:
    claims = _claims(Claim(X_RECALL, lines=(1,), distinguishes=value))
    with pytest.raises(ValueError, match=DISTINGUISHES):
        s3_verify.validate_claims(claims)


# --------------------------------------------------------------------------
# PIN 8-10 — the knob matrix
# --------------------------------------------------------------------------


def test_pin8_absent_is_explicit_reject_byte_for_byte(tmp_path: Path, cap: object) -> None:
    """The house rule: a config that says nothing gets the stage it had."""
    recall, echo = _echo_pair()
    absent = _Slot(tmp_path / "absent", cap).run(
        _cfg(), recall, echo, declared=(Y_ECHO,))
    explicit = _Slot(tmp_path / "explicit", cap).run(
        _cfg(REJECT), recall, echo, declared=(Y_ECHO,))
    assert _comparable(absent) == _comparable(explicit), (
        "Q-1 §3: `reject` IS the absent key — the two reports must not differ by a byte"
    )
    assert absent["verdict"] == VERDICT_REJECT
    assert _terms(absent["reject_reasons"]) == [X_RECALL]


def test_pin8b_a_no_dispute_run_is_todays_report_plus_an_empty_record(slot: _Slot) -> None:
    """T4's shape, on this lane's own fixture: the key is the ONLY addition."""
    clean = Claim(CLEAN_TERM, lines=(570,), site="the DIRS lookup")
    report = slot.run(_cfg(), clean, declared=(CLEAN_TERM,))
    assert report["verdict"] == VERDICT_PASS and report["reject_reasons"] == []
    assert report[DISPUTES] == [], (
        f"Q-1 §1: the key is written whenever it is COMPUTABLE, `[]` included, so an empty "
        f"answer reads differently from an absent one; got {report.get(DISPUTES)!r}"
    )
    extra = set(report) - set(s3_verify.REPORT_KEYS) - set(s3_verify.OPTIONAL_REPORT_KEYS)
    assert not extra, f"the report gained a key outside the frozen set: {sorted(extra)}"


def test_pin9_a_dry_run_carries_no_dispute_record(slot: _Slot) -> None:
    """Not computable: no agent, no diff, nothing to be about."""
    report = s3_verify.assemble_report(
        game_id=GAME_ID, worker=slot.worker, mode=MODE_DRY, cfg=_cfg(RECORD),
        cap=slot._cap, checks=[], frames_path=slot.frames_path,
        agent=None, diff=None, spec_hash=None,
    )
    assert DISPUTES not in report, (
        f"a dry run has no declared side for a dispute to be about; got {report.get(DISPUTES)!r}"
    )


@pytest.mark.parametrize("value", ["lenient", "Record", "", True, 1, None, ["record"]])
def test_pin10_a_bad_knob_is_loud_at_read_time(value: object) -> None:
    with pytest.raises(ValueError, match=KNOB):
        s3_verify._term_dispute_action({"duckwm_docs": ".", "verifier": {KNOB: value}})


def test_pin10b_the_reader_defaults_and_accepts_the_two_signed_words() -> None:
    assert s3_verify._term_dispute_action({}) == REJECT
    assert s3_verify._term_dispute_action({"verifier": {}}) == REJECT
    assert s3_verify._term_dispute_action({"verifier": "not-a-mapping"}) == REJECT
    assert s3_verify._term_dispute_action({"verifier": {"reject_cap": 1}}) == REJECT
    assert s3_verify._term_dispute_action(_cfg(REJECT)) == REJECT
    assert s3_verify._term_dispute_action(_cfg(RECORD)) == RECORD


def test_pin10c_a_bad_knob_stops_a_dry_run_too(slot: _Slot) -> None:
    """Read unconditionally, before anything is computed or written."""
    with pytest.raises(ValueError, match=KNOB):
        s3_verify.assemble_report(
            game_id=GAME_ID, worker=slot.worker, mode=MODE_DRY, cfg=_cfg("lenient"),
            cap=slot._cap, checks=[], frames_path=slot.frames_path,
            agent=None, diff=None, spec_hash=None,
        )


def test_pin10d_the_action_applier_is_loud_on_an_unsigned_action() -> None:
    with pytest.raises(ValueError, match="term dispute action"):
        s3_verify._apply_term_dispute_action(VERDICT_REJECT, [], [], "lenient")


def test_pin10e_record_leaves_every_other_reject_code_alone() -> None:
    """The scope guard: this knob governs two codes and nothing else."""
    rows = [
        s3_verify._reason(s3_verify.REJECT_FORBIDDEN_STATIC, "s", check_id="c", leg="static"),
        s3_verify._reason(s3_verify.REJECT_UNDECLARED_DECEPTION, "d", lever="decoy"),
        s3_verify._reason(s3_verify.REJECT_UNREACHABLE_DECLARED, "u", term=CLEAN_TERM),
        s3_verify._reason(s3_verify.REJECT_SOLVER_QUALITY, "q", check_id="c",
                          route=s3_verify.SOLVER_ONLY_ROUTE),
        s3_verify._reason(s3_verify.REJECT_UNDECLARED_TERM, "x", term=X_RECALL),
    ]
    disputes = [{"term": X_RECALL, "code": s3_verify.REJECT_UNDECLARED_TERM,
                 "disputed_with": Y_ECHO, "shared": "both sites name `pend`"}]
    verdict, kept = s3_verify._apply_term_dispute_action(
        VERDICT_REJECT, copy.deepcopy(rows), disputes, RECORD)
    assert verdict == VERDICT_REJECT
    assert _codes(kept) == _codes(rows[:-1]), (
        f"only the disputed undeclared-term row may move, in order; got {_codes(kept)}"
    )


# --------------------------------------------------------------------------
# PIN 11-12 — the schema is additive
# --------------------------------------------------------------------------


def test_pin11_every_shipped_verifier_report_still_validates() -> None:
    """READ-ONLY over the real corpus: not one report on disk carries the new key.

    `validate_report` reads reports written months ago. A REQUIRED key here would
    retro-invalidate every one of them, which is why `term_disputes` is optional.
    """
    reports = sorted(CORPUS.glob("*/*/worker.verifier-report.json"))
    assert len(reports) >= 15, (
        f"fixture wall: the corpus should hold the shipped reports; found {len(reports)}"
    )
    # LEAD UPDATE 2026-10-06: "not one report carries the key" was true at this
    # file's writing and stopped being true the same day — Q-1's live
    # acceptance (the echo round-8 audit) wrote the first report WITH it. The
    # claim that MATTERS is optionality both ways: every pre-Q-1 report (the
    # majority) validates without the key, and a report carrying it validates
    # too. Key-absence in the corpus is no longer asserted.
    without_key = 0
    for path in reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        if DISPUTES not in report:
            without_key += 1
        s3_verify.validate_report(report)
    # 14 = the pre-Q-1 population exactly (every report written since — the
    # echo round 8, echo-quilt, and all future games — carries the key, since
    # it is always-written now). This bound can only drop if a pre-Q-1 report
    # is rewritten, which the standing law forbids relying on either way.
    assert without_key >= 14, (
        f"the pre-Q-1 shipped reports should lack {DISPUTES!r}; only {without_key} do — "
        "if reports are being rewritten with the key, optionality is no longer being "
        "exercised by this pin and it needs a frozen corpus"
    )


def test_pin11b_the_exhibits_own_report_pairs_as_this_lane_measured_it() -> None:
    """The frozen ROUND-8 report — the live acceptance's own output.

    LEAD REWRITE 2026-10-06 (with the frozen repoint above): the one-pair
    measurement this pin originally nailed down was ROUND 7's report, which the
    live acceptance overwrote the same day. Round 8's facts are the richer
    exhibit and are pinned here instead: the same two findings stand, BOTH now
    carry a well-formed `distinguishes` naming their declared neighbour — so
    `term_disputes` is EMPTY by the break mechanism, which is contract Q-1's
    outcome (b) exactly — and `gate.key` is still grounded in nothing. Round
    7's one-pair mechanics remain pinned by this file's hermetic fixtures.
    """
    if not EXHIBIT_REPORT.is_file():  # pragma: no cover — the fixture is tracked
        pytest.fail(f"the frozen exhibit is gone: {EXHIBIT_REPORT}")
    report = json.loads(EXHIBIT_REPORT.read_text(encoding="utf-8"))
    claims, diff = report["agent"]["claims"], report["diff"]
    assert diff["undeclared_terms"] == [X_RECALL, X_KEYED], (
        f"fixture wall: the exhibit's two findings are the contract's; got "
        f"{diff['undeclared_terms']}"
    )
    for term, neighbour in ((X_RECALL, Y_ECHO), (X_KEYED, Y_KEY)):
        entry = next(e for e in claims["terms"] if e.get("term") == term)
        broken = entry.get("distinguishes")
        assert isinstance(broken, dict) and broken.get("term") == neighbour and (
            isinstance(broken.get("clause"), str) and broken["clause"].strip()
        ), (
            f"round 8's auditor cited the separating clause on {term} (vs {neighbour}); "
            f"got {broken!r}"
        )
    assert s3_verify.term_disputes(claims, diff) == [], (
        "both findings carry well-formed breaks, so the dispute list is empty BY "
        "DESIGN — a pair appearing here means the break mechanism regressed"
    )
    assert s3_verify._dispute_grounding(claims, Y_KEY) == (frozenset(), frozenset()), (
        f"{Y_KEY} is grounded in nothing — `site: null` and no `terms` row"
    )


def test_pin12_a_pre_q1_terms_claim_still_validates() -> None:
    """Additive: no `distinguishes` anywhere is every reply ever written."""
    claims = _claims(Claim(X_RECALL, lines=(1,)), Claim(Y_ECHO, lines=(2,)))
    assert not any(DISTINGUISHES in entry for entry in claims["terms"])
    s3_verify.validate_claims(claims)
    s3_verify.validate_claims(_claims(Claim(CLEAN_TERM, lines=(1,)), sites=False))


@pytest.mark.parametrize(
    ("entry", "why"),
    [
        ({"term": X_RECALL, "code": "undeclared-term", "disputed_with": Y_ECHO},
         "a missing key"),
        ({"term": X_RECALL, "code": "solver-quality", "disputed_with": Y_ECHO,
          "shared": "s"}, "a code no dispute can name"),
        ({"term": X_RECALL, "code": "undeclared-term", "disputed_with": X_RECALL,
          "shared": "s"}, "disputed with itself"),
        ({"term": X_RECALL, "code": "undeclared-term", "disputed_with": Y_ECHO,
          "shared": ""}, "no shared ground stated"),
    ],
)
def test_pin12b_a_malformed_dispute_record_is_loud(entry: dict, why: str) -> None:
    """Nothing is dropped silently — `_validate_exempted`'s own promise."""
    if not EXHIBIT_REPORT.is_file():  # pragma: no cover
        pytest.skip("no shipped report to mutate in tmp")
    report = json.loads(EXHIBIT_REPORT.read_text(encoding="utf-8"))
    report[DISPUTES] = [entry]
    with pytest.raises(ValueError, match=DISPUTES):
        s3_verify.validate_report(report)


# --------------------------------------------------------------------------
# PIN 13-15 — the seams: the prompt, the stop, the arming
# --------------------------------------------------------------------------


def test_pin13_the_prompt_quotes_the_requirement(tmp_path: Path, cap: object) -> None:
    """Prompt-sync: the built prompt carries the CONSTANT's own words.

    It rides the vocabulary section — the one that already quotes the 71
    definitions with their `*Not:*` clauses verbatim — because the clause the
    field must cite is printed there, and an auditor reads the requirement next
    to the material it answers.
    """
    staged = tmp_path / "toy.staged"
    s3_verify.stage_worker_copy(TOY_WORKER, staged)
    prompt = s3_verify.build_verifier_prompt(_cfg(RECORD), cap, staged)
    assert DISTINGUISHES in prompt, "the prompt never asks for the field the code reads"
    # The prompt-sync claim itself: the CONSTANT reaches the prompt verbatim, so
    # there is one spelling of the requirement and it cannot drift from the code.
    assert s3_verify.DISTINGUISH_HEADER in prompt, (
        "DISTINGUISH_HEADER is not quoted verbatim by the built prompt — prompt-sync "
        "means the constant IS the section, never a hand-copied second spelling"
    )
    assert f'"{DISTINGUISHES}": {{"term"' in s3_verify.DISTINGUISH_HEADER, (
        "the section must show the field's real SHAPE: a brace-doubled or reworded "
        "example is a snippet the auditor cannot copy"
    )
    # It rides the vocabulary section: the clause it asks for is printed above it.
    head = s3_verify.VOCAB_HEADER.format(count=len(s3_verify.signed_vocab())).splitlines()[0]
    assert prompt.index(head) < prompt.index(DISTINGUISHES), (
        "the requirement must come AFTER the definitions it tells the auditor to quote"
    )
    assert prompt.count(DISTINGUISHES) >= 2, (
        "the field is named in the vocabulary section AND in the claims contract, so a "
        "reader of either one knows it exists"
    )


def test_pin14_the_stop_reader_turns_a_report_into_lines(tmp_path: Path) -> None:
    worker = tmp_path / "slot-1"
    worker.mkdir()
    path = worker.with_name(worker.name + orchestrator.VERIFIER_REPORT_SUFFIX)
    path.write_text(json.dumps({DISPUTES: [
        {"term": X_RECALL, "code": "undeclared-term", "disputed_with": Y_ECHO,
         "shared": "both sites name `pend`"},
    ]}), encoding="utf-8")
    lines = orchestrator._term_disputes(str(worker))
    assert len(lines) == 1 and X_RECALL in lines[0] and Y_ECHO in lines[0], (
        f"Q-1 §3: the pairs print at the stop beside the deception advisories; got {lines}"
    )
    assert PEND in lines[0], "the line must carry what grounded the pairing"


@pytest.mark.parametrize("payload", [
    None, "", "{", "[]", '"text"', "{}", f'{{"{DISPUTES}": null}}',
    f'{{"{DISPUTES}": "rows"}}', f'{{"{DISPUTES}": [1, 2]}}',
    f'{{"{DISPUTES}": [{{"term": "x"}}]}}',
])
def test_pin14b_the_stop_reader_never_raises(tmp_path: Path, payload: str | None) -> None:
    """It runs after the batch report is written; a finished run must not die on it."""
    worker = tmp_path / "slot-1"
    worker.mkdir()
    if payload is not None:
        path = worker.with_name(worker.name + orchestrator.VERIFIER_REPORT_SUFFIX)
        path.write_text(payload, encoding="utf-8")
    assert orchestrator._term_disputes(str(worker)) == []
    assert orchestrator._term_disputes(None) == []


def test_pin15_the_template_and_the_overlay_arm_record() -> None:
    tree = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert tree["verifier"][KNOB] == RECORD, (
        "Q-1 §4: `config/template.yaml` ARMS `record` (the armed-recommended file)"
    )
    assert s3_verify._term_dispute_action(tree) == RECORD, "and the reader accepts the template"
    assert cli.AUTONOMY_OVERLAY["verifier"][KNOB] == RECORD, (
        f"Q-1 §4: AUTONOMY_OVERLAY gains verifier.{KNOB}: {RECORD!r}"
    )
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "two-keys-one-echo" in text, (
        "§4: the template arms the knob WITH its measured exhibit in the comment"
    )


def test_pin15b_the_materialized_config_carries_record(tmp_path: Path) -> None:
    """The CLI's own seam, with tmp roots: nothing under `out/` is read or written."""
    configs, batches = tmp_path / "config", tmp_path / "batches"
    configs.mkdir()
    batches.mkdir()
    cfg = cli.build_config(driver="claude", games=1, seed=99,
                           config_dir=configs, batches_root=batches)
    assert cfg["verifier"][KNOB] == RECORD
    assert s3_verify._term_dispute_action(cfg) == RECORD
    assert not list(configs.iterdir()) and not list(batches.iterdir())


def test_pin15c_an_explicit_reject_survives_materialization(tmp_path: Path) -> None:
    """The overlay arms a default, never a floor: a batch may still opt out."""
    template = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    template["verifier"][KNOB] = REJECT
    path = tmp_path / "template.yaml"
    path.write_text(yaml.safe_dump(template), encoding="utf-8")
    overlay = {block: dict(keys) for block, keys in cli.AUTONOMY_OVERLAY.items()}
    overlay["verifier"].pop(KNOB)
    built = cli.apply_overlay(yaml.safe_load(path.read_text(encoding="utf-8")), overlay)
    assert s3_verify._term_dispute_action(built) == REJECT, (
        "a config that says `reject` must get `reject` — the knob is read from the "
        "resolved config and nothing re-arms it"
    )


def test_pin15d_the_code_default_is_still_reject() -> None:
    assert s3_verify.TERM_DISPUTE_ACTION_REJECT == REJECT
    assert s3_verify.TERM_DISPUTE_ACTIONS == (REJECT, RECORD)
    assert s3_verify._term_dispute_action({"verifier": {"deception_action": RECORD}}) == REJECT, (
        "L-1's knob must not arm Q-1's: two rulings, two keys, two defaults"
    )
