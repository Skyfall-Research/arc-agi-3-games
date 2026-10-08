"""E-2 BLIND LANE: ladder sanity — reconciliation memory · terminal stage-fail
routes · respec feasibility.

Run: .venv/bin/python -m pytest gen/tests/test_v2_ladder.py -q

WRITTEN BLIND, FROM THE FROZEN CONTRACT ALONE
---------------------------------------------
Source of every expectation: `docs/v2/contracts/E-2-ladder-sanity.md`,
INCLUDING its Addendum 1 (the lead's rulings on the implementer handback).
Each assertion names the section it comes from. The implementer's own battery
(`gen/tests/test_e2_ladder.py`) exists on disk and was NEVER opened — not its
name list, not one line.

What WAS read, and only to learn surfaces the contract itself names:
  * `gen/orchestrator.py` — the §4 state tables, `run_batch`/`replay_ledger`/
    `append_transition`/`orchestrator_config`'s public signatures, the
    `SlotContext` field names and the runner-result contract. No expectation
    below is copied from an orchestrator constant: where the contract froze a
    STRING this file pins a literal (or derives it from the measured ledger),
    and where the contract left the spelling to the implementer this file pins
    the STRUCTURE the contract demanded instead (see AMBIGUITIES).
  * `gen/cli.py` — `AUTONOMY_OVERLAY`, `EDGE_NARRATION`, `build_config` /
    `render_config` (the `--dry-run` seam).
  * `config/template.yaml` — §2/§3's "Template ARMS true".
  * the rigs the brief told this lane to borrow, THROUGH THEIR OWNER'S NAMES
    and never copied or modified: `test_b11_pipeline` (`batch_home`/`make_cfg`,
    the two write guards, `_Journal`/`_Outcome`/`_Runners`, the ledger
    readers), `test_b005_autonomy` (`_SpecRunners`, the scripted verifier
    reports, the spec/term readers), `test_b10_package` (the play-root guard).

THE READ-ONLY FIXTURE: `out/batches/g20261001-5/ledger.jsonl`, the ledger the
contract's Evidence section measures. It is read, never written, and it is
where this file gets its byte-level "today's bytes" strings from — a pin
copied off the measured artifact rather than retyped from the brief.

WHAT EACH TEST PINS (contract sentence -> test)
-----------------------------------------------
G0  the PREMISE, with no E-2 code in the loop (b005's group-0 discipline):
    the measured ledger still replays, still ends non-terminal on the
    treadmill, and still carries both the ping-pong pair (Evidence (a)) and
    the four downstream rejects, three of them past a cap of 1 (Evidence (b)).
L1  "never WITHDRAW a term a prior reconciliation ADDED, and never RE-ADD one
    a prior reconciliation WITHDREW … the declaration stands, the slot
    proceeds" (§1 / blind-lane L1) — armed AND unarmed, because §1 says the
    memory "is not a knob — a reconciliation that withdraws what a
    reconciliation added is incorrect, armed or not". Plus the untouched case
    (an S1-authored term's FIRST withdrawal still reconciles) and the
    addendum's "free once per churn token (a repeat falls through to the
    ladder)".
L2  "when a DOWNSTREAM stage fail's count exceeds verifier.reject_cap, the
    slot PARKS from its current state" (§2) — unarmed is byte-for-byte the
    measured `gate fail 1/1` / `gate fail 2/1` lines; armed parks from
    `verified`, from `gated` and from `reviewed`; the ladder's only other
    bound is `MAX_STEPS_PER_SLOT`'s CRASH (the negative control); a parked
    ledger replays and a resume stays parked.
L3  "findings no declaration can answer … make the respec FUTILE by
    definition when they are the whole set. Futile → skip the S1 session
    entirely and route to the cap verdict (park under never-kill) with a
    ledger reason naming why no session was spent" (§3) — the S1 runner is
    BOOBY-TRAPPED, and the trap is proven to fire (so the no-invocation pins
    cannot be vacuous). Mixed sets, `s4.*` and unknown codes all spend
    (Addendum 1's futility table, both judgment calls).
L4  "Two knobs, both loud on invalid" (§3) + "every new knob DEFAULTS to
    today's bytes; the CLI overlay and template ARM" (the HOUSE RULE) +
    Addendum 1 item D7/(4) "the knobs are NOT in the report's config block —
    ledger reasons + materialized config are their visibility".
L5  "add the two edges to all four tables … replay must accept them" (§2
    seams) as corrected by Addendum 1 D1 (FOUR park edges; the blind lane
    pins edge PRESENCE, never an exact in-edge set) and D2 (`EDGE_NARRATION`
    is the fifth reader — a parked slot must not be silent).

AMBIGUITIES THIS FILE TOOK A POSITION ON (loudly, never silently)
-----------------------------------------------------------------
A. THE CHURN MECHANISM'S SPELLING IS THE IMPLEMENTER'S. §1 says "the churn
   NAMED in a ledger-visible way — your mechanism, say which", and Addendum 1
   item (2) says only that it is "a declaration-only revalidate continue with
   its own ledger reason". So no literal reason string is pinned for it. What
   IS pinned: a ledger line that names the refused amendment in
   `_reconcile_changes`'s own `+term`/`-term` spelling (§1 quotes
   `-manip.terraform`) AND carries the contract's own word for the event
   ("churn"), on a line that is not the park. Structure, not prose.
B. WHICH EDGE THE CHURN CONTINUE TRAVELS is not pinned either (b005's
   ambiguity C precedent): §1 asks for a "pass-equivalent continue", and the
   addendum rules out a `verified` route for honesty reasons. The pins are
   the OUTCOMES — the declaration stands, the slot proceeds, the event is
   ledger-visible, and the free refusal happens once per token.
C. THE FUTILE PARK'S REASON. §3 requires "a ledger reason naming why no
   session was spent"; the wording is the implementer's. Pinned: every
   finding code appears in the reason, and the reason says something about the
   session/spend (`s1`, `session` or `spent`, case-folded).
D. THE PARK'S `from_state` FOR A CAP-FIT FAIL. The contract's seam map names
   two edges and Addendum 1 D1 ratifies four, with the blind lane pinning
   PRESENCE only. This file additionally DRIVES the `("gated", "parked")`
   lane, because §2's rule is written about "a DOWNSTREAM stage fail" and
   `s4_baselines` is one of the three: an undriven edge in an armed batch is
   exactly the b004 crash this ladder exists to end. Presence is pinned for
   all four; three of the four are driven live.
E. `--dry-run` IS MEASURED THROUGH ITS OWN SEAM. The dry run prints
   `render_config(build_config(...))` and writes nothing; this file pins those
   two functions (with explicit `config_dir`/`batches_root` so nothing in the
   repo is read for an id or a seed and nothing is written), rather than
   driving `main()` through `preflight`, which inspects this machine.
F. `gate-visual` IS A CLASS NAME, NOT A CODE. §3 lists the futile classes as
   "solver-quality, forbidden-static, gate-visual, s6.seed-reject", and
   Addendum 1 confirms "gate-visual = futile as a class per the contract's own
   §3 naming". No producer emits the bare string: the gate's failing rows are
   `gate.<check>` over `s3_visual.CARD_CHECKS` plus the l1 colour floor (and
   S6's are `s6.seed-reject`, which IS literal). The class is therefore pinned
   in the producer's own vocabulary, read off `s3_visual` — a module this
   contract does not touch — exactly as b005's lane read s3_verify's REJECT_*
   spellings. Consequence, reported: a findings row whose code is the bare
   `gate-visual` reads as spec-answerable and SPENDS the session. That is
   correct under §3's closed-enumeration asymmetry ("every other code, known
   or not, spends") and it is also what a legacy or fake runner using that
   spelling would get, so it is named here rather than silently absorbed.
G. A RESUME MAY STILL REFRESH A STAGE FOR A TERMINAL SLOT. §2 ⊕'s re-run
   ("a stage re-runs iff its input hashes changed") is evaluated before the
   state is looked at, so a parked slot whose artifacts moved re-runs a stage
   without advancing. That is pre-existing behaviour — identical for
   `packaged` and `dead` — and under these fakes it fires for rig reasons
   (`spec.md` carries a revision counter). The resume pin is therefore "no
   stage runs FROM a live state and the ledger gains no line", not "no runner
   is called"; the behaviour itself is reported, not asserted either way.

RULES KEPT: no commits, no spend, no drivers, no network (b11's autouse guard
is re-bound), no writes outside `tmp_path` (b11's batch-root guard and b10's
play-root guard are both re-bound), `out/` and `games/` and duckWM read-only,
and no file but this one is touched.

DISCLOSURE — ONE UNAVOIDABLE CONTAMINATION, REPORTED RATHER THAN HIDDEN. The
brief told this lane to borrow `test_b005_autonomy`'s rigs. That file is itself
a blind file the implementer was licensed to pin-update (Addendum 1 D3), and
its `E2_PARK_EDGES` block names the four park edges and both knob names. It
was therefore seen. Nothing in this file is derived from it: D1 of the
addendum states the four edges to this lane directly, and the knob names are
§2's and §3's own. No assertion here was written or changed because of that
block.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

from gen import cli
from gen import orchestrator as orch
from gen import s3_verify as s3v
from gen import s3_visual as s3visual
from gen.config import REPO_ROOT

# The rigs, through their owner's names (the test_iteration_dynamics /
# test_b005_autonomy precedent: borrowed, never copied, never modified).
from gen.tests import test_b005_autonomy as b005
from gen.tests import test_b10_package as b10
from gen.tests import test_b11_pipeline as b11

# --- re-bound guards + fixtures (autouse survives the re-binding) -----------
_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched
_repo_play_root_untouched = b10._repo_play_root_untouched
batch_home = b11.batch_home
make_cfg = b11.make_cfg

# --- the stage names, READ off the orchestrator's own table (b005's rule) ---
S1_STAGE = orch.NEXT_STAGE["ideated"]
S2_STAGE = orch.NEXT_STAGE["spec_ok"]
S2B_STAGE = orch.NEXT_STAGE["implemented"]
S3_GATE_STAGE = orch.NEXT_STAGE["verified"]
S4_STAGE = orch.NEXT_STAGE["gated"]
S6_STAGE = orch.NEXT_STAGE["reviewed"]


# --------------------------------------------------------------------------- #
# the contract's own vocabulary, as literals
# --------------------------------------------------------------------------- #

#: §2/§3: "new knob `orchestrator.stage_fail_park`" / "separate knob
#: `orchestrator.respec_feasibility`". Both bools, both default FALSE.
KNOBS = ("stage_fail_park", "respec_feasibility")

#: §2's seam map + Addendum 1 D1, verbatim: "the contract's own rule ('parks
#: from its current state') plus the 3-wide DOWNSTREAM_REJECT_EDGES plus the
#: futile park at spec_ok force ('verified'|'gated'|'reviewed'|'spec_ok',
#: 'parked')". THE BLIND LANE PINS PRESENCE of all four, never an in-edge set.
PARK_EDGES = (
    ("verified", "parked"),
    ("gated", "parked"),
    ("reviewed", "parked"),
    ("spec_ok", "parked"),
)

#: §2: the three DOWNSTREAM lanes whose failure routed to `spec_ok` with no
#: terminal. `(the state it departs from, the stage that runs there, the label
#: the measured ledger leads its reason with)`.
DOWNSTREAM_LANES = (
    ("verified", S3_GATE_STAGE, "gate fail"),
    ("gated", S4_STAGE, "cap-fit fail"),
    ("reviewed", S6_STAGE, "package fail"),
)
DOWNSTREAM_REJECT_EDGES = tuple((state, "spec_ok") for state, _stage, _label in DOWNSTREAM_LANES)

#: §3's futility classes, and Addendum 1 confirms the table with both judgment
#: calls: "gate-visual + solver-quality + forbidden-static + s6.seed-reject are
#: the futile classes when they are the whole set".
#
#: MEASURED CORRECTION, reported not resolved quietly: `gate-visual` is a CLASS
#: NAME in §3's prose, not a code any producer emits. The gate's own failing
#: rows are spelled `gate.<check>` over `s3_visual.CARD_CHECKS` plus the l1
#: colour floor (the §3 "gate's visual checks" the template comment names), so
#: the class is pinned in the PRODUCER's vocabulary — read off `s3_visual`,
#: which this contract does not touch, exactly as b005's lane read s3_verify's
#: REJECT_* spellings. A bare `gate-visual` row is NOT in the enumeration and
#: spends a session; see the handback.
GATE_VISUAL_CODES = (*(f"gate.{check}" for check in s3visual.CARD_CHECKS), "gate.l1-color-floor")
VERIFIER_FUTILE_CODES = (s3v.REJECT_SOLVER_QUALITY, s3v.REJECT_FORBIDDEN_STATIC)
S6_FUTILE_CODE = "s6.seed-reject"
FUTILE_CODES = (*GATE_VISUAL_CODES, *VERIFIER_FUTILE_CODES, S6_FUTILE_CODE)
#: …and the other side of the asymmetry, Addendum 1 item (3) + (b): "everything
#: else (including s4.* and unknown codes) spends the session" / "s4.* =
#: answerable (doubt → spend)". "The closed-enumeration asymmetry (unknown
#: codes always spend) is the design, confirmed."
#:
#: S4's own rows are `s4.<verdict>`-shaped, so the first is a representative of
#: that family and the second is a code nothing has ever emitted — the two ends
#: of "everything else".
SPENDING_CODES = ("s4.cap-fit", "mystery.code-nobody-has-written-yet")

#: §1's own spelling of an amendment, quoted in the contract as
#: `+manip.terraform` / `-manip.terraform`.
def _token(direction: str, name: str) -> str:
    return f"{direction}{name}"


# --------------------------------------------------------------------------- #
# the read-only fixture: the ledger the contract measured
# --------------------------------------------------------------------------- #

# The E-2 brief measured the LIVE batch at 28 lines. That batch is append-only
# and legitimately CONTINUED (revival #1, 2026-10-05: resumed, S6 passed 5/5,
# packaged at line 37), so the evidence snapshot is frozen here as the
# byte-exact 28-line prefix of the live file at the freeze date — a live
# out/ path can never serve as a test fixture on a pipeline whose whole point
# is that batches resume.
MEASURED_LEDGER = (
    REPO_ROOT / "gen" / "tests" / "fixtures" / "g20261001-5-ledger-at-e2-freeze.jsonl"
)


def _measured_lines() -> list[dict]:
    """The measured ledger, read-only. A MISSING fixture is a loud failure.

    Never a skip: the brief names this file as the replay-shaped pins' source,
    and a silently skipped pin is a pin nobody is keeping.
    """
    assert MEASURED_LEDGER.is_file(), (
        f"the E-2 brief's measured fixture is gone: {MEASURED_LEDGER}. Every "
        "byte-level 'today's bytes' pin in this file is copied off it, so this "
        "is a LOUD finding, not a skip."
    )
    return [
        json.loads(raw)
        for raw in MEASURED_LEDGER.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]


MEASURED = _measured_lines()

#: Evidence (b): "'gate fail 1/1', 'gate fail 2/1', 'package fail 3/1',
#: 'package fail 4/1' — all four to `spec_ok`, the last two over a cap of 1".
MEASURED_DOWNSTREAM = tuple(
    str(line["reason"])
    for line in MEASURED
    if (line["from"], line["to"]) in DOWNSTREAM_REJECT_EDGES
)
MEASURED_GATE_FAILS = tuple(r for r in MEASURED_DOWNSTREAM if r.startswith("gate fail "))
MEASURED_PACKAGE_FAILS = tuple(r for r in MEASURED_DOWNSTREAM if r.startswith("package fail "))


def _measured_gate_tail() -> str:
    """The runner reason the measured gate-fail lines carry after their head.

    DERIVED from the fixture rather than retyped, so L2's byte-identity pin is
    a replay of the measured bytes and not a transcription of them.
    """
    assert MEASURED_GATE_FAILS, (
        "the measured ledger carries no `gate fail` line — Evidence (b)'s "
        f"premise is gone. Downstream reasons found: {MEASURED_DOWNSTREAM}"
    )
    head, sep, tail = MEASURED_GATE_FAILS[-1].partition(": ")
    assert sep and tail, f"the measured gate-fail reason has no `: <reason>` tail: {head!r}"
    return tail


GATE_TAIL = _measured_gate_tail()

#: §1 / Evidence (a): "line 12 reconciled `+manip.terraform`; line 14
#: reconciled `-manip.terraform` one round later, on UNCHANGED game bytes".
PINGPONG_TERM = "manip.terraform"


# --------------------------------------------------------------------------- #
# the rig: b005's spec/verifier runners + a failing downstream stage + the trap
# --------------------------------------------------------------------------- #

#: what the booby-trapped S1 runner raises. §3: "Futile → skip the S1 session
#: ENTIRELY". The trap is proven to fire by
#: `test_l3_the_booby_trap_fires_when_a_session_really_is_spent`.
TRAP = "E-2 §3 BOOBY TRAP: the S1 session was invoked for a provably futile re-spec"


class _LadderRunners(b005._SpecRunners):
    """b005's `_SpecRunners` with two additions this contract needs.

    1. ANY downstream stage can fail with REAL findings rows on the result
       (`findings` — the shape the gate/S4/S6 payload is written from), so §3's
       futility classifier has something to classify and §2's park reason has
       codes to name. b005's `_GateRunners` hardcodes `s3_gate` and one
       `gate-visual` row; this one takes the stage and the rows.
    2. The S1 BOOBY TRAP (§3's "skip the S1 session entirely"): the birth
       spec is allowed, and every later invocation raises. `s1_calls` is the
       count either way, so a test can pin "no second session" without the
       trap and the trap can prove itself.
    """

    def __init__(self, journal, cfg, *, fail_stage=None, findings=(), s1_trap=False, **kwargs):
        self.fail_stage = fail_stage
        self.findings_rows = [dict(row) for row in findings]
        self.s1_trap = s1_trap
        self.s1_calls = 0
        self.fail_calls = 0
        super().__init__(journal, cfg, **kwargs)

    def _make(self, stage: str):
        inner = super()._make(stage)

        def runner(ctx):
            if stage == S1_STAGE:
                self.s1_calls += 1
                if self.s1_trap and self.s1_calls > 1:
                    raise AssertionError(TRAP)
            result = inner(ctx)
            if stage != self.fail_stage or result["ok"]:
                return result
            self.fail_calls += 1
            if not self.findings_rows:
                return result
            rows = [dict(row) for row in self.findings_rows]
            return {**result, "findings": rows, "reject_reasons": rows}

        return runner


def _rows_for(*codes: str) -> list[dict]:
    """Findings rows for `codes`, in the feed's `{code, detail}` shape."""
    return [
        {"code": code, "detail": f"e2 blind lane: a finding whose code is {code}"}
        for code in codes
    ]


def _cfg_for(make_cfg_fixture, batch_id: str, *, knobs=(), reject_cap=None, round_cap=None,
             reconcile_early=None, auto_accept=False, tier="t2") -> tuple[dict, dict]:
    """A size-1 batch cfg, armed only where the scenario needs arming.

    `knobs` names the E-2 knobs to set TRUE; anything not named is ABSENT,
    which the HOUSE RULE makes "today's bytes". The tier block is armed with
    the same numbers `gen/tiers.py` carries (b005's ambiguity E), so either
    reading of the budget fires identically.
    """
    cfg, _path = make_cfg_fixture(batch_id, max_attrition=1.0)
    verifier = dict(cfg.get("verifier") or {})
    if reject_cap is not None:
        verifier["reject_cap"] = reject_cap
    if round_cap is not None:
        verifier["round_cap"] = round_cap
    if reconcile_early is not None:
        verifier["reconcile_early"] = reconcile_early
    cfg["verifier"] = verifier
    if auto_accept:
        cfg["review"] = {"auto_accept": True}
    cfg["tiers"] = {"term_budget": dict(b005.KILL_BUDGETS), "term_budget_action": "kill"}
    orchestrator = dict(cfg.get("orchestrator") or {})
    for knob in knobs:
        orchestrator[knob] = True
    cfg["orchestrator"] = orchestrator
    idea = dict(b005.IDEA)
    idea["tier"] = tier
    return cfg, idea


# --------------------------------------------------------------------------- #
# readers
# --------------------------------------------------------------------------- #


def _lines(cfg) -> list[dict]:
    return b11._ledger_lines(cfg)


def _spine(cfg) -> list[tuple]:
    return b11._spine(_lines(cfg))


def _reasons(cfg, edge=None) -> list[str]:
    return [
        str(line["reason"])
        for line in _lines(cfg)
        if edge is None or (line["from"], line["to"]) == edge
    ]


def _park_lines(cfg) -> list[dict]:
    return [line for line in _lines(cfg) if line["to"] == "parked"]


def _churn_lines(cfg, token: str) -> list[dict]:
    """Ledger lines that NAME a refused amendment (ambiguity A).

    §1: "such a finding is treated as uncorroborated churn … with the churn
    NAMED in a ledger-visible way". The spelling is the implementer's, so the
    test looks for the contract's own two ingredients: the amendment in
    `_reconcile_changes`'s `+term`/`-term` spelling, and the contract's own
    word for the event.
    """
    return [
        line
        for line in _lines(cfg)
        if token in str(line["reason"]) and "churn" in str(line["reason"]).lower()
    ]


def _terms(cfg) -> list[str]:
    return b005._terms_on_disk(cfg)


def _slot_row(report) -> dict:
    return b005._one_slot(report)


def _canon(payload, batch_id: str, home: Path) -> str:
    """One run's bytes, with only the DECLARED volatiles neutralised.

    The three volatiles, and nothing else: the batch id (and therefore every
    slug and path built from it), the tmp home, and the timestamps. Everything
    a knob could move — reasons, edges, costs, counts, report keys — is
    compared literally, which is what makes L4's "absent = byte-identity"
    pin byte-level (the HOUSE RULE's teeth).
    """
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, sort_keys=True)
    text = text.replace(str(home.resolve()), "TMPHOME").replace(str(home), "TMPHOME")
    text = text.replace(batch_id, "BATCH")
    return re.sub(r"\d{4}-\d{2}-\d{2}T[0-9:.+\-]+", "TS", text)


# --------------------------------------------------------------------------- #
# G0 — the measured premise, with no E-2 code in the loop
# --------------------------------------------------------------------------- #


def test_g0_the_measured_ledger_still_replays_clean():
    """Every byte-level pin below is copied off this file; prove it first."""
    table = orch.replay_ledger(MEASURED_LEDGER)
    assert table, f"{MEASURED_LEDGER} replayed to nothing"
    assert len(table) == 1, f"the measured batch ran one slot; got {sorted(table)}"
    row = next(iter(table.values()))
    assert len(row["history"]) == len(MEASURED) == 28, (
        f"the measured ledger is {len(MEASURED)} lines and replays "
        f"{len(row['history'])}; Evidence (a)/(b) cite lines 7..28"
    )


def test_g0_the_measured_ledger_ends_non_terminal_on_the_treadmill():
    """Evidence (b): "the sole remaining bound is MAX_STEPS_PER_SLOT … which
    CRASHES rather than parks" — so the measured slot never reached a terminal
    at all. This is the defect §2 exists to close, recorded as evidence."""
    row = next(iter(orch.replay_ledger(MEASURED_LEDGER).values()))
    assert row["state"] == "spec_ok", (
        f"the measured slot is supposed to have ended mid-ladder at `spec_ok`; "
        f"it is at {row['state']!r}"
    )
    assert row["terminal"] is False, "the measured slot reached a terminal — Evidence (b) is stale"


def test_g0_the_measured_ledger_carries_four_downstream_rejects_three_past_the_cap():
    """Evidence (b), the four lines, verbatim."""
    assert len(MEASURED_DOWNSTREAM) == 4, (
        f"Evidence (b) names four downstream rejects; found {MEASURED_DOWNSTREAM}"
    )
    assert len(MEASURED_GATE_FAILS) == 2 and len(MEASURED_PACKAGE_FAILS) == 2, (
        f"two gate fails and two package fails: {MEASURED_DOWNSTREAM}"
    )
    counts = [reason.split()[2] for reason in MEASURED_DOWNSTREAM]
    assert counts == ["1/1", "2/1", "3/1", "4/1"], (
        f"the measured ladder ran 1/1, 2/1, 3/1, 4/1 past a cap of 1; got {counts}"
    )


def test_g0_the_measured_ledger_carries_the_pingpong_pair_on_unchanged_game_bytes():
    """Evidence (a): `+manip.terraform` then `-manip.terraform` one round
    later, `hashes.game` identical both times. §1's whole premise."""
    added = [line for line in MEASURED if _token("+", PINGPONG_TERM) in str(line["reason"])]
    withdrew = [line for line in MEASURED if _token("-", PINGPONG_TERM) in str(line["reason"])]
    assert len(added) == 1 and len(withdrew) == 1, (
        f"Evidence (a) names exactly one add and one withdraw of {PINGPONG_TERM}; "
        f"found {len(added)} / {len(withdrew)}"
    )
    assert MEASURED.index(withdrew[0]) > MEASURED.index(added[0]), (
        "the withdrawal must come AFTER the addition — that ordering IS the churn"
    )
    assert added[0]["hashes"]["game"] == withdrew[0]["hashes"]["game"], (
        "Evidence (a): the game bytes never moved between the two reconciliations "
        f"({added[0]['hashes']['game']} vs {withdrew[0]['hashes']['game']})"
    )


# --------------------------------------------------------------------------- #
# L1 — reconciliation memory (NOT knob-gated: §1 "armed or not")
# --------------------------------------------------------------------------- #


def _pingpong_run(make_cfg_fixture, batch_id: str, *, knobs, reports, rejects,
                  round_cap=None):
    """Drive one slot through a scripted sequence of rejecting verify rounds.

    `verifier.reconcile_early: 2` is the path Evidence (a) measured ("lines 12
    and 14 are both EARLY reconciliations"), and `reject_cap: 5` keeps the
    ×cap escalation ladder out of the way (b005's ambiguity D precedent) so
    only the reconciliation paths can fire.
    """
    cfg, idea = _cfg_for(make_cfg_fixture, batch_id, knobs=knobs, reject_cap=5,
                         reconcile_early=2, round_cap=round_cap)
    journal = b11._Journal()
    runners = _LadderRunners(
        journal, cfg,
        outcomes={"implemented": b11._Outcome("spec_ok", "verifier reject", times=rejects)},
        idea=idea, verify_reports=reports,
    )
    report = orch.run_batch(cfg, runners=runners)
    return b005._Run(cfg, journal, runners, report)


def _undeclared(term: str) -> dict:
    return b005._undeclared_term_reason(term)


def _dead(term: str) -> dict:
    return b005._dead_term_reason(term)


KNOB_MODES = (("unarmed", ()), ("armed", KNOBS))


@pytest.mark.parametrize(("mode", "knobs"), KNOB_MODES, ids=[m for m, _ in KNOB_MODES])
def test_l1_a_withdrawal_of_a_reconciliation_added_term_is_refused_as_churn(
        make_cfg, mode, knobs):
    """L1 / §1: "never WITHDRAW a term a prior reconciliation ADDED … the
    withdrawal is refused-as-churn, the spec keeps the term, the slot
    proceeds" — and §1 says this is NOT knob-gated, so both modes."""
    term = b005.NEW_TERM
    add = b005._reject_report(_undeclared(term), undeclared_terms=[term])
    drop = b005._reject_report(_dead(term), dead_terms=[term])
    run = _pingpong_run(
        make_cfg, f"v2l-l1-undo-{mode}", knobs=knobs,
        reports=[add, drop, b005._pass_report()], rejects=2,
    )

    terms = _terms(run.cfg)
    assert term in terms, (
        f"§1: the reconciliation ADDED {term!r} and the next round's withdrawal is "
        f"uncorroborated churn — the declaration must STAND. Spec terms: {terms}"
    )
    refused = _churn_lines(run.cfg, _token("-", term))
    assert refused, (
        f"§1 requires the churn NAMED in a ledger-visible way (as "
        f"{_token('-', term)!r}); no ledger reason names it:\n"
        + "\n".join(_reasons(run.cfg))
    )
    assert not _park_lines(run.cfg), (
        f"§1: the slot PROCEEDS past a churn refusal; it parked: "
        f"{[str(line['reason']) for line in _park_lines(run.cfg)]}"
    )
    assert ("implemented", "verified") in _spine(run.cfg), (
        f"the clean third round must still verify the standing declarations: {_spine(run.cfg)}"
    )


def test_l1_the_refused_churn_is_named_in_the_batch_report(make_cfg):
    """§1 "ledger-visible" + Addendum 1 item (5): the churn report keys are
    ADDITIVE — present only when it happened. Here it happened."""
    term = b005.NEW_TERM
    add = b005._reject_report(_undeclared(term), undeclared_terms=[term])
    drop = b005._reject_report(_dead(term), dead_terms=[term])
    run = _pingpong_run(
        make_cfg, "v2l-l1-report", knobs=(),
        reports=[add, drop, b005._pass_report()], rejects=2,
    )
    text = b11._text(run.report)
    assert _token("-", term) in text, (
        f"the batch report never names the refused amendment {_token('-', term)!r}:\n"
        f"{text[:4000]}"
    )
    assert "churn" in text.lower(), (
        "the report names the amendment but never says what the event was "
        f"(§1's own word is 'churn'):\n{text[:4000]}"
    )


@pytest.mark.parametrize(("mode", "knobs"), KNOB_MODES, ids=[m for m, _ in KNOB_MODES])
def test_l1_a_re_add_after_a_reconciliation_withdrew_is_refused_as_churn(make_cfg, mode, knobs):
    """L1 / §1: "and never RE-ADD one a prior reconciliation WITHDREW … the
    inverse (re-add after withdraw) likewise"."""
    term = b005.DEAD_TERM
    drop = b005._reject_report(_dead(term), dead_terms=[term])
    add = b005._reject_report(_undeclared(term), undeclared_terms=[term])
    run = _pingpong_run(
        make_cfg, f"v2l-l1-readd-{mode}", knobs=knobs,
        reports=[drop, add, b005._pass_report()], rejects=2,
    )

    terms = _terms(run.cfg)
    assert term not in terms, (
        f"§1: the reconciliation WITHDREW {term!r}; re-adding it is churn and the "
        f"withdrawal must stand. Spec terms: {terms}"
    )
    refused = _churn_lines(run.cfg, _token("+", term))
    assert refused, (
        f"§1 requires the refused re-addition NAMED as {_token('+', term)!r}; no "
        f"ledger reason does:\n" + "\n".join(_reasons(run.cfg))
    )
    assert not _park_lines(run.cfg), (
        f"the slot must proceed past the refusal: "
        f"{[str(line['reason']) for line in _park_lines(run.cfg)]}"
    )


def test_l1_a_first_ever_withdrawal_of_an_s1_authored_term_still_reconciles(make_cfg):
    """§1's SCOPE, verbatim: "reconciliation-ADDED/WITHDRAWN terms only — an
    S1-authored term withdrawn by first-ever subtractive finding is untouched
    behavior". The negative control on the memory rule."""
    term = b005.DEAD_TERM
    drop = b005._reject_report(_dead(term), dead_terms=[term])
    run = _pingpong_run(
        make_cfg, "v2l-l1-untouched", knobs=KNOBS,
        reports=[drop, b005._pass_report()], rejects=1,
    )

    terms = _terms(run.cfg)
    assert term not in terms, (
        f"a FIRST-EVER subtractive finding against an S1-authored term is untouched "
        f"behaviour and must still withdraw {term!r}: {terms}"
    )
    assert not _churn_lines(run.cfg, _token("-", term)), (
        "nothing was undone, so nothing may be called churn:\n" + "\n".join(_reasons(run.cfg))
    )
    assert not _park_lines(run.cfg), "the untouched case must not park"


def test_l1_the_churn_refusal_is_free_exactly_once_per_token(make_cfg):
    """Addendum 1 item (2): the refusal is "free once per churn token (a repeat
    falls through to the ladder)" — so a finding that churns EVERY round
    cannot livelock. `verifier.round_cap` is armed as the ladder's own
    terminal, so "falls through" has somewhere to fall."""
    term = b005.NEW_TERM
    add = b005._reject_report(_undeclared(term), undeclared_terms=[term])
    drop = b005._reject_report(_dead(term), dead_terms=[term])
    run = _pingpong_run(
        make_cfg, "v2l-l1-oncepertoken", knobs=KNOBS, round_cap=4,
        # add, then the SAME withdrawal every round for the rest of the slot
        reports=[add, drop, drop, drop, drop, drop, drop], rejects=8,
    )

    assert _slot_row(run.report)["terminal"] is True, (
        "a finding that churns every round must still reach a terminal "
        f"(addendum item 2: the repeat falls through to the ladder). Slot: "
        f"{_slot_row(run.report)['state']!r}\n" + "\n".join(_reasons(run.cfg))
    )
    free = [line for line in _churn_lines(run.cfg, _token("-", term)) if line["to"] != "parked"]
    assert len(free) == 1, (
        f"exactly ONE free refusal per churn token; got {len(free)}:\n"
        + "\n".join(str(line["reason"]) for line in free)
    )
    assert term in _terms(run.cfg), (
        f"the declaration still stands through every refusal: {_terms(run.cfg)}"
    )


# --------------------------------------------------------------------------- #
# L2 — the treadmill's top
# --------------------------------------------------------------------------- #


def _downstream_run(make_cfg_fixture, batch_id: str, *, state: str, stage: str, knobs,
                    times: int = 2, codes=(), reason: str | None = None,
                    s1_trap: bool = False):
    """Fail ONE downstream stage `times` times against `verifier.reject_cap: 1`.

    A cap of 1 is the measured config (Evidence (b): "1/1", "2/1" past a cap
    of 1), and it is what makes the SECOND failure the one that "exceeds" the
    cap in §2's sense.
    """
    cfg, idea = _cfg_for(
        make_cfg_fixture, batch_id, knobs=knobs, reject_cap=1,
        auto_accept=(state == "reviewed"),
    )
    journal = b11._Journal()
    runners = _LadderRunners(
        journal, cfg,
        outcomes={state: b11._Outcome("spec_ok", reason or GATE_TAIL, times=times)},
        idea=idea, verify_reports=[b005._pass_report()],
        fail_stage=stage, findings=_rows_for(*codes), s1_trap=s1_trap,
    )
    report = orch.run_batch(cfg, runners=runners)
    return b005._Run(cfg, journal, runners, report)


def test_l2_unarmed_a_downstream_fail_past_the_cap_writes_todays_bytes(make_cfg):
    """L2: "gate-fail past cap with stage_fail_park absent → EXACTLY today's
    bytes (the 2/1 respec line, pinned)".

    The pin is BYTE-LEVEL and the expected strings are not retyped: they are
    the measured g20261001-5 lines themselves (Evidence (b)), reproduced by a
    fake gate whose reason is that ledger's own tail.
    """
    run = _downstream_run(make_cfg, "v2l-l2-unarmed", state="verified",
                          stage=S3_GATE_STAGE, knobs=())

    written = _reasons(run.cfg, ("verified", "spec_ok"))
    assert written == list(MEASURED_GATE_FAILS), (
        "unarmed, the downstream ladder must write the measured bytes EXACTLY "
        "(the HOUSE RULE: every new knob defaults to today's bytes).\n"
        f"measured: {list(MEASURED_GATE_FAILS)}\nwritten:  {written}"
    )
    assert not _park_lines(run.cfg), (
        f"unarmed, nothing may park: {[str(l['reason']) for l in _park_lines(run.cfg)]}"
    )
    assert ("verified", "gated") in _spine(run.cfg), (
        f"unarmed, the slot re-specs and carries on past the cap: {_spine(run.cfg)}"
    )


def test_l2_unarmed_the_ladder_has_no_top_but_the_livelock_guard(make_cfg):
    """THE NEGATIVE CONTROL for §2, and it is the contract's own diagnosis:
    "the sole remaining bound is MAX_STEPS_PER_SLOT (:389) which CRASHES
    rather than parks — the exact loop the docstring says must close".

    Without this, every armed pin could pass on a run where the ladder
    happened to terminate by itself.
    """
    cfg, idea = _cfg_for(make_cfg, "v2l-l2-notop", knobs=(), reject_cap=1)
    journal = b11._Journal()
    runners = _LadderRunners(
        journal, cfg,
        outcomes={"verified": b11._Outcome("spec_ok", GATE_TAIL, times=99)},
        idea=idea, verify_reports=[b005._pass_report()], fail_stage=S3_GATE_STAGE,
    )
    with pytest.raises(BaseException) as caught:
        orch.run_batch(cfg, runners=runners)

    assert not isinstance(caught.value, AssertionError), (
        f"the unbounded treadmill must crash on the livelock guard, not on a test "
        f"assertion: {caught.value!r}"
    )
    rejects = _reasons(cfg, ("verified", "spec_ok"))
    assert len(rejects) > 2, (
        f"unarmed, the ladder must run away past the cap — that is the measured "
        f"defect; it wrote {len(rejects)} gate fail(s): {rejects}"
    )
    assert not _park_lines(cfg), (
        "unarmed, the run-away ladder must never reach a park (the HOUSE RULE): "
        f"{[str(line['reason']) for line in _park_lines(cfg)]}"
    )


def test_l2_armed_a_fail_AT_the_cap_does_not_park(make_cfg):
    """§2 says EXCEEDS, not reaches: "a DOWNSTREAM stage fail's count exceeds
    verifier.reject_cap". Armed, the failure that only REACHES the cap is
    still today's re-spec — the control on the off-by-one."""
    run = _downstream_run(make_cfg, "v2l-l2-atcap", state="verified", stage=S3_GATE_STAGE,
                          knobs=("stage_fail_park",), times=1)
    assert not _park_lines(run.cfg), (
        "a single downstream fail against a cap of 1 reaches the cap without "
        f"exceeding it and must not park: "
        f"{[str(line['reason']) for line in _park_lines(run.cfg)]}"
    )
    assert _reasons(run.cfg, ("verified", "spec_ok")) == [MEASURED_GATE_FAILS[0]], (
        "and the line it writes is the measured one, byte for byte: "
        f"{_reasons(run.cfg, ('verified', 'spec_ok'))}"
    )


@pytest.mark.parametrize(("state", "stage", "label"), DOWNSTREAM_LANES,
                         ids=[state for state, _s, _l in DOWNSTREAM_LANES])
def test_l2_armed_a_downstream_fail_past_the_cap_parks_from_its_own_state(
        make_cfg, state, stage, label):
    """§2: "when a DOWNSTREAM stage fail's count exceeds verifier.reject_cap,
    the slot PARKS from its current state … park reason names the stage, the
    count, and the findings codes".

    Ambiguity D: all three downstream lanes are driven, because §2's rule is
    written about "a DOWNSTREAM stage fail" and an undrawn park edge in an
    armed batch is the b004 crash this ladder exists to end (Addendum 1 D1).
    """
    code = GATE_VISUAL_CODES[0] if stage == S3_GATE_STAGE else f"{stage}.blind-lane-finding"
    run = _downstream_run(make_cfg, f"v2l-l2-park-{state}", state=state, stage=stage,
                          knobs=("stage_fail_park",), codes=(code,))

    spine = _spine(run.cfg)
    assert (state, "parked") in spine, (
        f"§2: a {label} past the cap must travel ({state!r}, 'parked') — the park "
        f"departs from the slot's CURRENT state. Spine: {spine}"
    )
    assert (state, "spec_ok") in spine, (
        f"the FIRST failure (at the cap, not past it) is still today's re-spec: {spine}"
    )
    row = _slot_row(run.report)
    assert row["state"] == "parked" and row["terminal"] is True, (
        f"never-kill: the slot ends PARKED and terminal, not dead and not running: {row}"
    )
    assert "dead" not in [line["to"] for line in _lines(run.cfg)], (
        "§2 parks; it never kills (operator 2026-09-29, quoted in the contract)"
    )

    reason = str(_park_lines(run.cfg)[-1]["reason"])
    assert label in reason, f"the park reason must name the stage ({label!r}): {reason}"
    assert "2/1" in reason, (
        f"the park reason must name the count and the cap it exceeded (2/1): {reason}"
    )
    assert code in reason, f"the park reason must name the findings code(s) ({code!r}): {reason}"


def test_l2_armed_the_park_is_the_ladders_top(make_cfg):
    """§2: armed, the knob IS the bound — the same runner that crashes the
    livelock guard unarmed (the control above) now settles."""
    run = _downstream_run(make_cfg, "v2l-l2-top", state="verified", stage=S3_GATE_STAGE,
                          knobs=("stage_fail_park",), times=99)
    assert _slot_row(run.report)["state"] == "parked", _slot_row(run.report)
    assert run.runners.fail_calls == 2, (
        f"the gate must run exactly twice — once at the cap, once past it — then the "
        f"slot parks; it ran {run.runners.fail_calls}×"
    )


@pytest.mark.parametrize(("state", "stage", "_label"), DOWNSTREAM_LANES,
                         ids=[state for state, _s, _l in DOWNSTREAM_LANES])
def test_l2_a_parked_ledger_replays_clean_and_a_resume_stays_parked(
        make_cfg, state, stage, _label):
    """L2: "replay_ledger replays both new edges clean; resume of a parked slot
    stays parked"."""
    run = _downstream_run(make_cfg, f"v2l-l2-resume-{state}", state=state, stage=stage,
                          knobs=("stage_fail_park",))
    ledger = b11._ledger_path(run.cfg)
    before = ledger.read_bytes()

    table = orch.replay_ledger(ledger)
    row = next(iter(table.values()))
    assert row["state"] == "parked" and row["terminal"] is True, (
        f"a ledger ending on ({state!r}, 'parked') must replay to a terminal parked "
        f"slot: {row['state']!r}/{row['terminal']!r}"
    )

    journal = b11._Journal()
    resumed = _LadderRunners(journal, run.cfg, idea=dict(b005.IDEA, tier="t2"),
                             verify_reports=[b005._pass_report()])
    report = orch.run_batch(run.cfg, runners=resumed)
    assert ledger.read_bytes() == before, (
        "a resume of a parked slot must append NOTHING — parked is terminal for the run"
    )
    # NOT `journal.calls == []`: the §2 ⊕ resume refreshes any stage whose
    # INPUT hashes moved before it looks at the state, and under these fakes
    # `spec.md` is rewritten with a new revision on every landing, so a refresh
    # fires for rig reasons that have nothing to do with the park. What the
    # contract claims is that the slot does not ADVANCE, and that is what is
    # pinned: no stage runs FROM a live state. (The refresh-a-terminal-slot
    # behaviour is pre-existing — it is the same for `packaged` and `dead` —
    # and is reported as a flag, not asserted either way.)
    advanced = [call for call in journal.calls if call.from_state != "parked"]
    assert not advanced, (
        f"a resume ran {len(advanced)} stage(s) from a LIVE state for a parked slot: "
        f"{[(c.stage, c.from_state, c.to_state) for c in advanced]}"
    )
    assert _slot_row(report)["state"] == "parked", _slot_row(report)
    assert _slot_row(report)["terminal"] is True, _slot_row(report)


# --------------------------------------------------------------------------- #
# L3 — respec feasibility
# --------------------------------------------------------------------------- #


def _futile_reason(cfg) -> str:
    parks = _park_lines(cfg)
    assert parks, (
        "§3: a futile re-spec must PARK (never kill — the cap verdict under "
        "never-kill); no `parked` line was written:\n" + "\n".join(_reasons(cfg))
    )
    return str(parks[-1]["reason"])


def _assert_names_the_unspent_session(reason: str, codes) -> None:
    """§3: "a ledger reason naming why no session was spent" (ambiguity C)."""
    for code in codes:
        assert code in reason, f"the futile-park reason must name the code {code!r}: {reason}"
    lowered = reason.lower()
    assert any(word in lowered for word in ("s1", "session", "spent")), (
        f"§3 requires the reason to say why NO SESSION WAS SPENT: {reason}"
    )


#: §3's two DOWNSTREAM game-side classes, each paired with the producer that
#: actually emits it: the gate's visual card checks, and S6's seed reject (the
#: measured g20261001-5 package fails were seed rejects).
DOWNSTREAM_FUTILE = (
    *(("verified", S3_GATE_STAGE, code) for code in GATE_VISUAL_CODES),
    ("reviewed", S6_STAGE, S6_FUTILE_CODE),
)


@pytest.mark.parametrize(("state", "stage", "code"), DOWNSTREAM_FUTILE,
                         ids=[code for _s, _st, code in DOWNSTREAM_FUTILE])
def test_l3_armed_a_game_side_downstream_findings_set_spends_no_session(
        make_cfg, state, stage, code):
    """L3 / §3: "a findings-set of only game-side codes → NO S1 invocation
    (booby-trap the runner) and the cap-verdict route with the naming
    reason"."""
    run = _downstream_run(make_cfg, f"v2l-l3-futile-{code.replace('.', '-')}",
                          state=state, stage=stage,
                          knobs=("respec_feasibility",), times=1, codes=(code,), s1_trap=True)

    assert run.runners.s1_calls == 1, (
        f"§3: the futile re-spec must skip the S1 session ENTIRELY — S1 ran "
        f"{run.runners.s1_calls}× (1 == the birth spec only)"
    )
    assert ("spec_ok", "parked") in _spine(run.cfg), (
        f"§3 routes a futile re-spec to the cap verdict (park under never-kill), "
        f"from the state it was refused at: {_spine(run.cfg)}"
    )
    _assert_names_the_unspent_session(_futile_reason(run.cfg), (code,))
    assert _slot_row(run.report)["terminal"] is True, _slot_row(run.report)


def test_l3_armed_a_game_side_verifier_residual_spends_no_session(make_cfg):
    """§3's other lane: "_verifier_reject_reasons for the verifier path".
    `solver-quality` + `forbidden-static` are the two verifier-side classes."""
    cfg, idea = _cfg_for(make_cfg, "v2l-l3-futile-verifier",
                         knobs=("respec_feasibility",), reject_cap=1)
    reject = b005._reject_report(*_rows_for(*VERIFIER_FUTILE_CODES))
    journal = b11._Journal()
    runners = _LadderRunners(
        journal, cfg,
        outcomes={"implemented": b11._Outcome("spec_ok", "verifier reject", times=1)},
        idea=idea, verify_reports=[reject], s1_trap=True,
    )
    report = orch.run_batch(cfg, runners=runners)

    assert runners.s1_calls == 1, (
        f"a verifier residual no declaration can answer must spend no session; S1 ran "
        f"{runners.s1_calls}×"
    )
    assert ("spec_ok", "parked") in _spine(cfg), _spine(cfg)
    _assert_names_the_unspent_session(_futile_reason(cfg), VERIFIER_FUTILE_CODES)
    assert _slot_row(report)["terminal"] is True, _slot_row(report)


def test_l3_the_booby_trap_fires_when_a_session_really_is_spent(make_cfg):
    """THE TRAP'S OWN PROOF. Without it, every `s1_calls == 1` pin above could
    be passing because the scenario never reached a re-spec at all."""
    with pytest.raises(AssertionError, match="BOOBY TRAP"):
        _downstream_run(make_cfg, "v2l-l3-trapproof", state="verified", stage=S3_GATE_STAGE,
                        knobs=(), times=1, codes=(GATE_VISUAL_CODES[0],), s1_trap=True)


def test_l3_armed_a_mixed_findings_set_still_runs_the_respec(make_cfg):
    """L3: "a mixed set (one reconcilable term + one game-side) → the respec
    still runs (not futile)"."""
    rows = [
        b005._undeclared_term_reason(b005.NEW_TERM),
        *_rows_for(GATE_VISUAL_CODES[0]),
    ]
    cfg, idea = _cfg_for(make_cfg, "v2l-l3-mixed", knobs=("respec_feasibility",), reject_cap=1)
    journal = b11._Journal()
    runners = _LadderRunners(
        journal, cfg,
        outcomes={"verified": b11._Outcome("spec_ok", GATE_TAIL, times=1)},
        idea=idea, verify_reports=[b005._pass_report()],
        fail_stage=S3_GATE_STAGE, findings=rows,
    )
    orch.run_batch(cfg, runners=runners)

    assert runners.s1_calls >= 2, (
        "§3: a set with ONE spec-answerable finding in it is not futile and the "
        f"session is spent; S1 ran {runners.s1_calls}× (1 == birth only)"
    )
    assert not _park_lines(cfg), (
        f"a mixed set must not park: {[str(l['reason']) for l in _park_lines(cfg)]}"
    )


@pytest.mark.parametrize("code", SPENDING_CODES)
def test_l3_armed_an_s4_or_unknown_code_still_spends_the_session(make_cfg, code):
    """Addendum 1, FUTILITY TABLE CONFIRMED: "(b) s4.* = answerable (doubt →
    spend). The closed-enumeration asymmetry (unknown codes always spend) is
    the design, confirmed." Wrongly parking is the expensive mistake."""
    cfg, idea = _cfg_for(make_cfg, f"v2l-l3-spend-{code.split('.')[0]}",
                         knobs=("respec_feasibility",), reject_cap=1)
    journal = b11._Journal()
    runners = _LadderRunners(
        journal, cfg,
        outcomes={"verified": b11._Outcome("spec_ok", GATE_TAIL, times=1)},
        idea=idea, verify_reports=[b005._pass_report()],
        fail_stage=S3_GATE_STAGE, findings=_rows_for(code),
    )
    orch.run_batch(cfg, runners=runners)

    assert runners.s1_calls >= 2, (
        f"{code!r} is outside §3's closed enumeration, so the session is SPENT; "
        f"S1 ran {runners.s1_calls}×"
    )
    assert not _park_lines(cfg), (
        f"{code!r} must never park a slot unspent: "
        f"{[str(l['reason']) for l in _park_lines(cfg)]}"
    )


def test_l3_unarmed_the_same_futile_set_spends_the_session(make_cfg):
    """L3: "unarmed → today's bytes (S1 spent, pinned)". The HOUSE RULE."""
    run = _downstream_run(make_cfg, "v2l-l3-unarmed", state="verified", stage=S3_GATE_STAGE,
                          knobs=(), times=1, codes=(GATE_VISUAL_CODES[0],))

    assert run.runners.s1_calls >= 2, (
        f"unarmed, the escalated re-spec is paid for exactly as it is today; S1 ran "
        f"{run.runners.s1_calls}×"
    )
    assert not _park_lines(run.cfg), (
        f"unarmed, nothing parks: {[str(l['reason']) for l in _park_lines(run.cfg)]}"
    )
    assert _reasons(run.cfg, ("verified", "spec_ok")) == [MEASURED_GATE_FAILS[0]], (
        "the escalation line the re-spec answers is the measured one, byte for byte: "
        f"{_reasons(run.cfg, ('verified', 'spec_ok'))} vs {[MEASURED_GATE_FAILS[0]]}"
    )


def test_l3_a_futile_park_bills_no_respec_run(make_cfg):
    """Addendum 1 D6 RATIFIED: "respec billing honesty — futile parks un-bill
    the skipped session". A report that billed it would put a paid session on
    the record the knob exists not to pay for."""
    run = _downstream_run(make_cfg, "v2l-l3-billing", state="verified", stage=S3_GATE_STAGE,
                          knobs=("respec_feasibility",), times=1,
                          codes=(GATE_VISUAL_CODES[0],), s1_trap=True)
    row = _slot_row(run.report)
    assert row["respec_runs"] == 0, (
        "D6: the escalation the futile park answered must not be billed as a re-spec "
        f"run; the report says {row['respec_runs']}"
    )


# --------------------------------------------------------------------------- #
# L4 — the two knobs: loud, and invisible until they fire
# --------------------------------------------------------------------------- #

#: §3: "Two knobs, both loud on invalid". `1` is not a `true`: a bool knob that
#: cannot mean what it says is a config defect, not a setting.
NOT_BOOLS = (1, 0, "true", "false", "yes", None, [], {}, 1.0)


@pytest.mark.parametrize("knob", KNOBS)
@pytest.mark.parametrize("value", NOT_BOOLS, ids=[repr(v) for v in NOT_BOOLS])
def test_l4_a_non_bool_knob_is_loud(make_cfg, knob, value):
    """§2 "validated loudly beside parallel_slots" / §3 "both loud on invalid"."""
    cfg, _idea = _cfg_for(make_cfg, f"v2l-l4-bad-{knob}", knobs=())
    cfg["orchestrator"][knob] = value

    exc = b11._raised(orch.orchestrator_config, cfg)
    assert exc is not None, (
        f"orchestrator.{knob} = {value!r} is not a bool and must be refused loudly"
    )
    assert knob in str(exc), f"the error must NAME the key it is about: {exc}"

    journal = b11._Journal()
    runners = _LadderRunners(journal, cfg, idea=dict(b005.IDEA, tier="t2"),
                             verify_reports=[b005._pass_report()])
    assert b11._raised(orch.run_batch, cfg, runners=runners) is not None, (
        f"a malformed orchestrator.{knob} must stop the batch, not be discovered later"
    )
    assert journal.calls == [], (
        f"a config defect must be loud at second zero — {len(journal.calls)} stage(s) ran "
        f"on a cfg whose {knob} is {value!r}"
    )


@pytest.mark.parametrize("knob", KNOBS)
@pytest.mark.parametrize("value", [True, False])
def test_l4_a_bool_knob_is_accepted(make_cfg, knob, value):
    cfg, _idea = _cfg_for(make_cfg, f"v2l-l4-ok-{knob}", knobs=())
    cfg["orchestrator"][knob] = value
    assert orch.orchestrator_config(cfg), f"orchestrator.{knob} = {value!r} must be accepted"


def _root_snapshot(current: Path) -> dict[str, Path]:
    """Every orchestrator root, as a path relative to `current`.

    Taken ONCE, before any re-rooting, so repeated re-roots cannot nest.
    """
    snapshot: dict[str, Path] = {}
    for name, value in list(vars(orch).items()):
        if name.startswith("__") or not isinstance(value, Path):
            continue
        try:
            snapshot[name] = value.resolve().relative_to(current.resolve())
        except ValueError:
            continue
    return snapshot


def _reroot(monkeypatch, snapshot: Mapping[str, Path], home: Path) -> None:
    """Point the orchestrator's roots at `home` (b11's `batch_home`, re-aimed).

    L4's byte-identity pin needs the SAME batch id in three different trees:
    the fake artifacts embed the slug, so two runs under two ids have different
    content and therefore different `hashes` — a difference no knob made. Same
    id, different home, and the only remaining volatiles are the paths and the
    timestamps.
    """
    for name, relative in snapshot.items():
        monkeypatch.setattr(orch, name, home / relative)
    monkeypatch.setattr("gen.config.REPO_ROOT", home)


def _happy_batch(make_cfg_fixture, batch_id: str, *, orchestrator_block) -> tuple[dict, dict]:
    """One full fake batch, driven to a terminal, with the knobs as given."""
    cfg, idea = _cfg_for(make_cfg_fixture, batch_id, reject_cap=5, auto_accept=True)
    cfg["orchestrator"].update(orchestrator_block)
    journal = b11._Journal()
    runners = _LadderRunners(journal, cfg, idea=idea, verify_reports=[b005._pass_report()])
    report = orch.run_batch(cfg, runners=runners)
    assert _slot_row(report)["state"] == "packaged", (
        f"the byte-identity subject must be a COMPLETE batch; it ended at "
        f"{_slot_row(report)['state']!r}"
    )
    return cfg, report


ABSENT_FALSE_TRUE = (
    ("absent", {}),
    ("false", dict.fromkeys(KNOBS, False)),
    ("true", dict.fromkeys(KNOBS, True)),
)


def test_l4_absent_false_and_armed_are_byte_identical_on_a_full_fake_batch(
        make_cfg, batch_home, monkeypatch):
    """L4: "absent = byte-identity on a full fake batch (report + ledger)" —
    the HOUSE RULE's teeth, made byte-level.

    ARMED is in the comparison too, because Addendum 1 D7 RATIFIED "knobs NOT
    in report config.caps — the house rule wins, the parallel_slots
    validate-don't-report precedent": a knob that fired nothing must leave no
    trace at all, not even a config echo. The three runs share ONE batch id in
    three trees, so only the declared volatiles (the tmp home and the
    timestamps) are neutralised; every reason, edge, hash, cost and count is
    compared literally.
    """
    batch_id = "v2l-l4-identity"
    snapshot = _root_snapshot(batch_home)
    assert snapshot, "b11's batch_home re-rooted nothing — the rig moved"
    baseline = None
    for name, block in ABSENT_FALSE_TRUE:
        home = batch_home / f"run-{name}"
        _reroot(monkeypatch, snapshot, home)
        cfg, _report = _happy_batch(make_cfg, batch_id, orchestrator_block=block)
        ledger = _canon(b11._ledger_path(cfg).read_text(encoding="utf-8"), batch_id, home)
        # the report on DISK, not the returned dict: the report's bytes are the
        # artifact a reader diffs between batches.
        on_disk = _canon(b11._report_path(cfg).read_text(encoding="utf-8"), batch_id, home)
        if baseline is None:
            baseline = (name, ledger, on_disk)
            continue
        assert ledger == baseline[1], (
            f"the ledger bytes moved between the {baseline[0]} and {name} runs — a knob "
            f"that fired nothing must change nothing (HOUSE RULE).\n"
            f"--- {baseline[0]}\n{baseline[1]}\n--- {name}\n{ledger}"
        )
        assert on_disk == baseline[2], (
            f"the batch-report bytes moved between the {baseline[0]} and {name} runs "
            f"(Addendum 1 D7: the knobs are NOT in the report)."
        )


@pytest.mark.parametrize(("name", "block"), ABSENT_FALSE_TRUE, ids=[n for n, _b in ABSENT_FALSE_TRUE])
def test_l4_the_report_never_names_either_knob(make_cfg, name, block):
    """Addendum 1 item (4) / D7: "the two knobs are deliberately NOT in the
    report's config block (ledger reasons + materialized config are their
    visibility)"."""
    cfg, report = _happy_batch(make_cfg, f"v2l-l4-quiet-{name}", orchestrator_block=block)
    for payload, where in ((report, "the returned report"),
                           (json.loads(b11._report_path(cfg).read_text(encoding="utf-8")),
                            "the report on disk")):
        text = b11._text(payload)
        for knob in KNOBS:
            assert knob not in text, (
                f"{where} names orchestrator.{knob}; D7 keeps both knobs out of the "
                f"report (the parallel_slots validate-don't-report precedent)"
            )


def test_l4_the_cli_overlay_arms_both_knobs(make_cfg):
    """§2 "the CLI AUTONOMY_OVERLAY arms true (8th key)" / §3 "template +
    overlay arm true"."""
    block = cli.AUTONOMY_OVERLAY.get("orchestrator")
    assert isinstance(block, Mapping), (
        f"AUTONOMY_OVERLAY has no `orchestrator` block to arm: {sorted(cli.AUTONOMY_OVERLAY)}"
    )
    for knob in KNOBS:
        assert block.get(knob) is True, (
            f"the overlay must arm orchestrator.{knob} at exactly True (a bool knob, "
            f"loud on anything else); it carries {block.get(knob)!r}"
        )


def test_l4_the_template_arms_both_knobs():
    """§2 "Template ARMS true (with the 10-01 exhibits in the comment)"."""
    template = yaml.safe_load(
        (REPO_ROOT / "config" / "template.yaml").read_text(encoding="utf-8")
    )
    block = (template or {}).get("orchestrator") or {}
    for knob in KNOBS:
        assert block.get(knob) is True, (
            f"config/template.yaml must arm orchestrator.{knob} at True; it carries "
            f"{block.get(knob)!r}"
        )
    comment = (REPO_ROOT / "config" / "template.yaml").read_text(encoding="utf-8")
    assert "g20261001-5" in comment, (
        "§2: the template arms the knob WITH the 10-01 exhibits in the comment; the "
        "measured batch is not named anywhere in the file"
    )


def test_l4_the_materialized_config_carries_both_and_the_dry_run_prints_them(tmp_path):
    """L4: "CLI --dry-run surfaces them".

    Ambiguity E: measured through the dry run's own seam — `build_config` +
    `render_config`, which is the exact text `run --dry-run` prints between
    its two markers — with explicit roots so nothing is read from or written
    to the repo's own `config/` or `out/batches/`.
    """
    config_dir = tmp_path / "config"
    batches_root = tmp_path / "batches"
    config_dir.mkdir()
    batches_root.mkdir()
    cfg = cli.build_config(
        driver=next(iter(sorted(cli.DRIVER_CHOICES))), games=1, tiers=None,
        name="e2blind", seed=1, workers=None,
        config_dir=config_dir, batches_root=batches_root,
    )
    for knob in KNOBS:
        assert cfg["orchestrator"].get(knob) is True, (
            f"the materialized config must carry orchestrator.{knob}: {cfg['orchestrator']}"
        )
    printed = cli.render_config(cfg).splitlines()
    for knob in KNOBS:
        assert f"  {knob}: true" in printed, (
            f"the text `--dry-run` prints must show `{knob}: true` under orchestrator; "
            f"orchestrator lines printed: "
            f"{[line for line in printed if ':' in line and not line.startswith('#')][:40]}"
        )
    assert not any(batches_root.iterdir()), "a dry run writes nothing"
    assert not any(config_dir.iterdir()), "a dry run writes nothing"


# --------------------------------------------------------------------------- #
# L5 — the state tables
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("from_state", "to_state"), PARK_EDGES,
                         ids=[f"{a}-{b}" for a, b in PARK_EDGES])
def test_l5_each_park_edge_is_present_and_consistent(from_state, to_state):
    """L5 as corrected by Addendum 1 D1: "THE BLIND LANE pins edge PRESENCE
    (all four), never an exact in-edge set" — in TRANSITIONS (with the §4
    label), in EDGE_STAGE (with an owner), and accepted by `assert_transition`.
    """
    row = orch.TRANSITIONS.get(from_state)
    assert isinstance(row, Mapping) and to_state in row, (
        f"§2's seam: ({from_state!r}, {to_state!r}) is missing from TRANSITIONS — "
        f"an armed batch parking from {from_state!r} would raise IllegalTransition. "
        f"Row: {row}"
    )
    assert str(row[to_state]).strip(), (
        f"the §4 label map gives ({from_state!r}, {to_state!r}) an empty label; §2 "
        "requires the routing to be readable in the diagram's own words"
    )
    assert (from_state, to_state) in orch.EDGE_STAGE, (
        f"EDGE_STAGE does not name an owner for ({from_state!r}, {to_state!r}); the "
        "ledger line carries no stage field, so an unowned edge is unattributable"
    )
    owner = orch.EDGE_STAGE[(from_state, to_state)]
    assert owner in orch.STAGES, (
        f"the owner of ({from_state!r}, {to_state!r}) is {owner!r}, which is not one of "
        f"{list(orch.STAGES)}"
    )
    assert b11._raised(orch.assert_transition, from_state, to_state) is None, (
        f"assert_transition refuses ({from_state!r}, {to_state!r}) — §2: 'replay must "
        "accept them'"
    )


@pytest.mark.parametrize(("from_state", "to_state"), PARK_EDGES,
                         ids=[f"{a}-{b}" for a, b in PARK_EDGES])
def test_l5_each_park_edge_appends_and_replays(tmp_path, from_state, to_state):
    """§2 seams: "replay must accept them (replay_ledger is table-driven — pin
    it)". Appended and replayed, one edge per case."""
    ledger = tmp_path / f"{from_state}-{to_state}.jsonl"
    hashes = {"spec": "a" * 8, "game": "b" * 8, "stage_input": "c" * 8}
    orch.append_transition(ledger, slug="e2-park-probe", from_state=None,
                           to_state="ideated", reason="birth", hashes=hashes, cost=None)
    # walk the §4 spine to `from_state` so the replay's own "each line departs
    # from the slug's current state" check is satisfied by a real walk.
    walk = {
        "spec_ok": [("ideated", "spec_ok")],
        "verified": [("ideated", "spec_ok"), ("spec_ok", "implemented"),
                     ("implemented", "verified")],
        "gated": [("ideated", "spec_ok"), ("spec_ok", "implemented"),
                  ("implemented", "verified"), ("verified", "gated")],
        "reviewed": [("ideated", "spec_ok"), ("spec_ok", "implemented"),
                     ("implemented", "verified"), ("verified", "gated"),
                     ("gated", "baselined"), ("baselined", "played"),
                     ("played", "reviewed")],
    }[from_state]
    for src, dst in [*walk, (from_state, to_state)]:
        orch.append_transition(ledger, slug="e2-park-probe", from_state=src, to_state=dst,
                               reason="the §4 walk" if dst != to_state else "park",
                               hashes=hashes, cost=None)

    row = orch.replay_ledger(ledger)["e2-park-probe"]
    assert row["state"] == "parked", (
        f"a ledger whose last line is ({from_state!r}, {to_state!r}) must replay to "
        f"`parked`; it replayed to {row['state']!r}"
    )
    assert row["terminal"] is True, "L5: parked stays terminal on the replay too"


#: PIN UPDATE, 2026-10-06 (contract E-5 §1) — the park's EXIT, which E-2 pinned
#: shut. The two assertions below said "no edge leaves `parked`", and that was
#: E-2's truth: E-2 added edges INTO the park and the park had no tool to let
#: anyone out. E-5 adds exactly one LIFT edge per edge INTO `parked` — this
#: file's own `PARK_EDGES` (E-2's four) plus P-A.4's `implemented` — reachable
#: ONLY by the operator command `arc-games unpark`, never by a run. So what E-2
#: actually needed pinned survives unchanged and is pinned below: `parked` stays
#: in STATES and in TERMINAL, `NEXT_STAGE["parked"]` stays None (no stage runs
#: from it, so no resume can work a parked slot loose), and every exit that is
#: NOT one of the five lifts is still an `IllegalTransition`.
E5_LIFT_STATES = frozenset({src for src, _dst in PARK_EDGES} | {"implemented"})


def test_l5_parked_stays_terminal_in_every_table():
    """L5: "parked stays terminal in both"."""
    assert "parked" in orch.STATES, "`parked` left the §4 vocabulary"
    assert "parked" in orch.TERMINAL, "L5: `parked` must stay TERMINAL"
    assert orch.NEXT_STAGE["parked"] is None, (
        f"NEXT_STAGE runs {orch.NEXT_STAGE['parked']!r} from `parked`; a terminal state "
        "runs nothing"
    )
    assert set(orch.TRANSITIONS["parked"]) == E5_LIFT_STATES, (
        "E-2 adds edges INTO `parked`; the only edges OUT are contract E-5's five operator "
        f"lifts, one per in-edge: {sorted(orch.TRANSITIONS['parked'])} vs "
        f"{sorted(E5_LIFT_STATES)}"
    )


@pytest.mark.parametrize("to_state", [s for s in orch.STATES
                                      if s != "parked" and s not in E5_LIFT_STATES])
def test_l5_no_edge_leaves_parked(to_state):
    """The other half of "parked stays terminal": every exit E-5 does not draw
    is still illegal — nothing a RUN executes can leave the park."""
    assert b11._raised(orch.assert_transition, "parked", to_state) is not None, (
        f"('parked', {to_state!r}) must be an IllegalTransition — nothing runs from a "
        "terminal state, and E-5's lift restores only the state the slot parked FROM"
    )


@pytest.mark.parametrize(("from_state", "to_state"), PARK_EDGES,
                         ids=[f"{a}-{b}" for a, b in PARK_EDGES])
def test_l5_a_park_edge_is_never_silent_in_the_cli_voice(from_state, to_state):
    """Addendum 1 D2 RATIFIED: "cli.EDGE_NARRATION is the fifth state-table
    reader … a parked slot must not be silent in the arc-games voice"."""
    sentence = cli.narrate(
        {"slug": "e2-narrate-probe", "from": from_state, "to": to_state, "reason": "park"},
        seen={},
    )
    assert sentence, (
        f"({from_state!r}, {to_state!r}) is narrated as nothing — a human would watch the "
        "slot stop and never be told (Addendum 1 D2)"
    )
    assert "park" in sentence.lower(), (
        f"the sentence for ({from_state!r}, {to_state!r}) never says the slot parked: "
        f"{sentence!r}"
    )
