"""b005r2 BLIND LANE — P-A (early reconciliation / two-directional / auto-retier
/ park) and P-B (the seed self-check in the findings feed), T1-T9.

WRITTEN FROM THE FROZEN CONTRACT ALONE. This file never read `gen/orchestrator.py`,
`gen/s2_implement.py` or any diff of the implementation lane. What it DID read is
exactly what the contract licenses:

  * the contract itself (`b005r2-lenient-contract.md`);
  * `gen/tiers.py` (constants — `DEFAULT_TERM_BUDGETS`, `TIER_TABLE`, `TERM_BUDGET_MIN`);
  * the RIG it is told to reuse — `gen/tests/test_b005_autonomy.py` and
    `gen/tests/test_b11_pipeline.py` — for their names and constructor shapes;
  * LIVE MODULE STATE, observed by RUNNING the pre-implementation pipeline through
    that rig (values, ledger strings, report keys). Everything pinned below as
    "measured" was captured on 2026-09-29 at ~16:30-16:45 IST, with
    `gen/orchestrator.py` at mtime 2026-09-29 04:33 and `gen/s2_implement.py` at
    mtime 2026-09-28 19:10 — i.e. BEFORE the P-A/P-B implementation existed. The
    54-test `test_b005_autonomy.py` suite was green at capture time (its T6 kill
    pins still passed), which is the proof that the capture is pre-state.

Operator rulings this file encodes (2026-09-29, verbatim):
  "We should never kill. Even if it is not satisfied eventually let's not kill."
  "If there's a mismatch of 1-2 terms let's just go ahead with it."

THE LENIENT LANE'S DISCIPLINE. Where the contract names a behaviour, it is pinned
hard. Where the contract leaves a spelling free (which key holds the tier, which
module renders the findings, whether "off" is 0 or None), this file resolves the
seam by search and says so in the failure message, so a red here is a contract
question and never a naming quibble. A contract-named symbol that does not exist
yet is an EXPECTED pre-merge failure: it is reported, never weakened.

WHAT THIS FILE DOES NOT TOUCH. `test_b11_pipeline`'s SECTION4_EDGES pin gains
("implemented", "parked") — that edit belongs to the IMPLEMENTER, with their own
inline justification (contract, blind-lane section, last bullet). Nothing here
edits another file.

MEASURED PRE-STATE THIS FILE PINS (all captured as described above):
  * path a at the round cap travels ("implemented", "spec_ok") with the ledger
    reason `declaration reconciled to audit: +agent.patrol (round_cap 2; verifier
    reject: undeclared-term)` and is followed by an s2 REBUILD, so the stage
    sequence for a 2-reject reconciliation run is s0,s1,s2,s3v,s2,s3v,s2,s3v,...
    (T8 pins this byte for byte);
  * under `reject_cap 1` a single verifier reject escalates to a respec
    (`verifier reject x1 -> respec (architecture §4): ...`, s1_spec invoked a
    SECOND time) — which is what makes T2's "no respec" pin sharp;
  * a batch that trips `max_attrition` reports status "stopped", stop_reason
    "attrition", exit_code 2 and `attrition["abort"]["aborted"] is True`;
  * `report["states"]` is a per-state census ({"dead": 1} / {"played": 1});
  * the §11 spec fixture carries SIX terms and NO tier field anywhere, and the
    additive reconciliation leaves `levels[*].terms_introduced` untouched;
  * `s2_implement.findings_section` renders the snapshot pinned in T9.

RULES KEPT: no network / no agent / no CLI / no writes outside tmp (the rig's
autouse guards are re-bound below), no API spend, no config written, no existing
test or fixture modified.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from gen import orchestrator as orch
from gen import s2_implement, tiers
from gen import s3_verify as s3v

# The rigs, borrowed through their owner's alias (the b005-autonomy precedent).
from gen.tests import test_b005_autonomy as b005
from gen.tests import test_b10_package as b10
from gen.tests import test_b11_pipeline as b11

# --- re-bound guards + fixtures (autouse survives the re-binding) -----------
_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched
_repo_play_root_untouched = b10._repo_play_root_untouched
batch_home = b11.batch_home
make_cfg = b11.make_cfg


# --------------------------------------------------------------------------- #
# vocabulary
# --------------------------------------------------------------------------- #

#: the fixture spec's own six terms (measured: len == 6 == the t1 budget).
BASE_TERMS = b005.BASE_TERMS

#: CANON terms (gen canon vocabulary, 71 entries) that the fixture does NOT
#: declare. They are canon on purpose: a lint kill caused by an invented term
#: would masquerade as a park and the test would be measuring the wrong thing.
T_ONE = b005.NEW_TERM          # "agent.patrol" — the rig's own additive term
T_TWO = "move.push"
T_THREE = "state.wait"
T_FOUR = "terrain.one_way"
T_FIVE = "gate.plate"
EXTRA_TERMS = (T_ONE, T_TWO, T_THREE, T_FOUR, T_FIVE)

#: the tier budgets the contract cites (gen/tiers.py DEFAULT_TERM_BUDGETS).
BUDGETS = tiers.DEFAULT_TERM_BUDGETS

#: the four declaration-side codes P-A.1/P-A.2 may reconcile.
ADDITIVE_CODES = (s3v.REJECT_UNDECLARED_TERM, s3v.REJECT_UNDECLARED_DECEPTION)
SUBTRACTIVE_CODES = (s3v.REJECT_DEAD_SPEC_TERM, s3v.REJECT_UNREACHABLE_DECLARED)
DECLARATION_CODES = ADDITIVE_CODES + SUBTRACTIVE_CODES

#: the key the reader lives under, and the names it may carry (ambiguity: the
#: contract names the CONFIG key, not the python symbol).
CONFIG_KEY = "reconcile_early"
READER_NAMES = (
    "_reconcile_early",
    "reconcile_early",
    "_verifier_reconcile_early",
    "_reconcile_early_cap",
)


def _solver_quality_reason(detail: str = "level 3 is solvable only by pixel-hunting") -> dict:
    """A residual that is NEVER reconcilable, in either direction."""
    return {"code": s3v.REJECT_SOLVER_QUALITY, "detail": detail}


def _reject(*reasons: dict, undeclared=(), dead=()) -> dict:
    return b005._reject_report(
        *reasons, undeclared_terms=list(undeclared), dead_terms=list(dead)
    )


def _undeclared(*terms: str) -> dict:
    """One rejecting report carrying ONE `undeclared-term` finding per term."""
    return _reject(*(b005._undeclared_term_reason(t) for t in terms), undeclared=terms)


def _dead(*terms: str) -> dict:
    return _reject(*(b005._dead_term_reason(t) for t in terms), dead=terms)


# --------------------------------------------------------------------------- #
# the driver: the rig's `_reconciliation_run`, with the new knob wired in
# --------------------------------------------------------------------------- #


def _run(
    make_cfg,
    batch_id: str,
    *,
    tier: str,
    reports: list,
    rejects: int,
    reconcile_early=None,
    round_cap: int = 2,
    reject_cap: int = 5,
    max_attrition: float = 1.0,
) -> b005._Run:
    """One slot, scripted verifier reports, optionally armed with the new knob.

    `reconcile_early=None` means THE KEY IS ABSENT — the unconfigured run T8
    requires. Everything else follows the rig's `_reconciliation_run`.
    """
    cfg, idea = b005._armed_cfg(
        make_cfg,
        batch_id,
        round_cap=round_cap,
        reject_cap=reject_cap,
        tier=tier,
        max_attrition=max_attrition,
    )
    if reconcile_early is not None:
        cfg["verifier"] = {**cfg["verifier"], CONFIG_KEY: reconcile_early}
    journal = b11._Journal()
    runners = b005._SpecRunners(
        journal,
        cfg,
        outcomes={
            "implemented": b11._Outcome(
                "spec_ok", f"verifier reject: {s3v.REJECT_UNDECLARED_TERM}", times=rejects
            )
        },
        idea=idea,
        verify_reports=reports,
    )
    report = orch.run_batch(cfg, runners=runners)
    return b005._Run(cfg, journal, runners, report)


def _spine(run) -> list:
    return b11._spine(b11._ledger_lines(run.cfg))


def _invocations(run) -> dict:
    return dict(b005._one_slot(run.report)["invocations"])


def _haystack(run) -> str:
    """Every place the contract lets an announcement land: ledger + report."""
    return b005._all_reason_text(run.cfg) + "\n" + b11._text(run.report)


def _levels_on_disk(run) -> list:
    return list(b005._spec_on_disk(run.cfg)["game"]["levels"])


def _introduced_on_disk(run) -> list:
    return [list(level.get("terms_introduced") or ()) for level in _levels_on_disk(run)]


def _spec_tier(spec) -> tuple[str | None, str | None]:
    """The tier recorded in spec.yaml, wherever P-A.3's implementer put it.

    Returns (dotted path, value). The §11 schema has NO tier field today
    (MEASURED: `s1_spec.GAME_FIELDS` carries none and the fixture spec carries
    none), so P-A.3's "update the tier field in spec.yaml" necessarily adds one;
    this walks the whole document rather than guessing its name.
    """

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{path}.{key}" if path else str(key)
                named_tier = str(key) == "tier" or str(key).endswith("_tier")
                if named_tier and isinstance(value, str):
                    return here, value
                found = walk(value, here)
                if found[1] is not None:
                    return found
        elif isinstance(node, list):
            for index, value in enumerate(node):
                found = walk(value, f"{path}[{index}]")
                if found[1] is not None:
                    return found
        return None, None

    return walk(spec, "")


# --------------------------------------------------------------------------- #
# premises — if any of these break, every measurement below is about a
# different fixture and the failures mean nothing
# --------------------------------------------------------------------------- #


def test_premise_the_fixture_spec_still_carries_six_terms_and_no_tier():
    assert len(BASE_TERMS) == 6 == BUDGETS["t1"], (
        f"fixture drift: the spec fixture declares {len(BASE_TERMS)} terms; every "
        f"budget arithmetic in this file assumes 6 (== the t1 budget {BUDGETS['t1']})"
    )
    path, value = _spec_tier(yaml.safe_load(b005.SPEC_TEXT))
    assert value is None, (
        f"the fixture spec now carries a tier field at {path!r} ({value!r}); T6 reads "
        "the PROMOTED tier off spec.yaml and needs the authored spec to carry none"
    )


def test_premise_the_extra_terms_are_canon_vocabulary():
    """A non-canon term would lint-kill and every park below would be a lie."""
    from gen import canon_docs

    canon = set(canon_docs.load_term_definitions(b005._CFG))
    unknown = sorted(t for t in EXTRA_TERMS if t not in canon)
    assert not unknown, (
        f"{unknown} are not canon terms — this file's amendments must be canon so "
        "that a park can only come from the guard under test, never from the linter"
    )
    assert not set(EXTRA_TERMS) & set(BASE_TERMS), "the extra terms must be NEW"


def test_premise_the_budgets_are_the_signed_tier_table():
    assert BUDGETS == {"t1": 6, "t2": 8, "t3": 10}, (
        f"gen/tiers.py DEFAULT_TERM_BUDGETS moved: {BUDGETS}. The contract's "
        "t3-is-the-ceiling arithmetic (9 fits t3, 11 does not) is written against "
        "{'t1': 6, 't2': 8, 't3': 10}"
    )
    assert b005.KILL_BUDGETS == BUDGETS, (
        "the rig arms the budget guard from its own copy; the two must agree"
    )


def test_premise_the_declaration_side_codes_are_the_frozen_spellings():
    assert ADDITIVE_CODES == ("undeclared-term", "undeclared-deception")
    assert SUBTRACTIVE_CODES == ("dead-spec-term", "unreachable-declared-mechanic")
    assert s3v.REJECT_SOLVER_QUALITY == "solver-quality"


# --------------------------------------------------------------------------- #
# T1 — the `verifier.reconcile_early` reader
# --------------------------------------------------------------------------- #


def _reader():
    """The reader, by name then by search (the rig's `_round_cap_reader` pattern)."""
    for name in READER_NAMES:
        value = getattr(orch, name, None)
        if callable(value):
            return value
    candidates = sorted(
        name
        for name, value in vars(orch).items()
        if callable(value) and "reconcil" in name.lower()
    )
    raise AssertionError(
        "gen/orchestrator.py exposes no `reconcile_early` reader (P-A.1: 'Reader "
        f"beside `_round_cap`'). Callables naming 'reconcil': {candidates}"
    )


@pytest.mark.parametrize(
    "cfg",
    [
        {},
        {"verifier": {}},
        {"verifier": {"round_cap": 4}},
        {"verifier": {CONFIG_KEY: 0}},
    ],
    ids=["no-verifier-block", "empty-verifier-block", "round_cap-only", "explicit-zero"],
)
def test_t1_absent_or_zero_is_off(cfg):
    """'default 0 = today's bytes; int >= 0 (0 = off)'.

    LENIENT on the spelling of off: 0 (the contract's default) and None (the
    `_round_cap` neighbour's spelling for the same idea) both pass; anything
    truthy does not, because a truthy default would arm the new path unasked.
    """
    value = _reader()(cfg)
    assert value in (0, None), (
        f"an unconfigured run must be OFF (the house rule: byte-identical to "
        f"today). The reader returned {value!r} for {cfg!r}"
    )


@pytest.mark.parametrize("value", [1, 2, 5])
def test_t1_a_positive_int_is_the_value(value):
    assert _reader()({"verifier": {CONFIG_KEY: value}}) == value


@pytest.mark.parametrize(
    "value",
    [-1, "x", True, 2.0],
    ids=["negative", "word", "true", "float"],
)
def test_t1_everything_else_is_a_loud_value_error(value):
    """'anything else a loud ValueError naming the key'."""
    with pytest.raises(ValueError) as caught:
        _reader()({"verifier": {CONFIG_KEY: value}})
    assert CONFIG_KEY in str(caught.value), (
        f"the refusal must NAME the key; got {str(caught.value)!r}"
    )


def test_t1_the_neighbour_reader_is_untouched():
    """The reader is added BESIDE `_round_cap`, not in place of it."""
    assert orch._round_cap({}) is None
    assert orch._round_cap({"verifier": {"round_cap": 3}}) == 3


# --------------------------------------------------------------------------- #
# T2 — the early path: TWO declaration-side findings at N=2, round 1
# --------------------------------------------------------------------------- #


def _early_run(make_cfg, batch_id, **kwargs):
    """Round 1 rejects with TWO undeclared terms; the confirming round is clean."""
    return _run(
        make_cfg,
        batch_id,
        tier="t2",
        reports=[_undeclared(T_ONE, T_TWO), b005._pass_report()],
        rejects=1,
        reconcile_early=2,
        round_cap=4,
        **kwargs,
    )


def test_t2_both_terms_are_reconciled_into_the_spec_at_the_first_reject(make_cfg):
    """P-A.1: at ANY rejecting round whose findings are all declaration-side and
    number <= N, the amendment happens immediately — not at the cap."""
    run = _early_run(make_cfg, "b005r2-early")
    terms = b005._terms_on_disk(run.cfg)
    missing = [t for t in (T_ONE, T_TWO) if t not in terms]
    assert not missing, (
        f"the early reconciliation did not amend the declaration with {missing}. "
        f"round_cap is 4 and only ONE round rejected, so nothing but the EARLY path "
        f"can add them. Spec terms on disk: {terms}"
    )
    assert list(BASE_TERMS) == terms[: len(BASE_TERMS)], (
        f"reconciliation APPENDS — the authored terms moved: {terms}"
    )
    assert len(terms) == len(BASE_TERMS) + 2 == BUDGETS["t2"], (
        f"6 authored + 2 amended = 8 = the t2 budget exactly, so this scenario must "
        f"NOT promote a tier; got {terms}"
    )


def test_t2_the_ledger_announces_it_as_EARLY_and_names_both_additions(make_cfg):
    """P-A.1's reason: `declaration reconciled early (<=N): +a, +b (verifier reject: ...)`."""
    run = _early_run(make_cfg, "b005r2-early-loud")
    text = _haystack(run)
    assert "reconciled early" in text.lower(), (
        "no ledger line announces the EARLY reconciliation — P-A.1 pins the phrase "
        f"'declaration reconciled early'. Ledger + report:\n{text[:3000]}"
    )
    for term in (T_ONE, T_TWO):
        assert f"+{term}" in text, (
            f"the reason must list the addition as '+{term}' (P-A.1: 'list additions "
            f"with +, drops with -'):\n{text[:3000]}"
        )


def test_t2_one_confirming_round_verifies_the_slot(make_cfg):
    """'ONE confirming verify round' — and a clean one lands `verified`."""
    run = _early_run(make_cfg, "b005r2-early-confirm")
    assert run.runners.verify_calls == 2, (
        "the audit must run exactly twice — the rejecting round and ONE confirming "
        f"round after the early reconciliation; it ran {run.runners.verify_calls}x"
    )
    spine = _spine(run)
    assert ("implemented", "verified") in spine, f"the slot never verified: {spine}"
    assert ("implemented", "dead") not in spine, f"never kill: {spine}"
    assert ("implemented", "parked") not in spine, (
        f"an early reconciliation that confirms clean must not park either: {spine}"
    )
    assert b005._one_slot(run.report)["state"] not in ("dead", "parked")


def test_t2_the_early_round_skips_the_respec(make_cfg):
    """'skip respec' — S1 is NOT invoked.

    Armed with `reject_cap 1`, where MEASURED pre-implementation behaviour is that
    the first verifier reject escalates (`verifier reject x1 -> respec`) and
    `s1_spec` runs a SECOND time. The early reconciliation must pre-empt that: the
    reject still counts (a later round will escalate), but this round reconciles.
    """
    run = _early_run(make_cfg, "b005r2-early-norespec", reject_cap=1)
    calls = _invocations(run)
    assert calls.get("s1_spec") == 1, (
        "P-A.1 says the early path SKIPS the respec, so s1_spec must have run once "
        f"(the birth) and no more; invocations: {calls}. Ledger:\n"
        f"{b005._all_reason_text(run.cfg)}"
    )
    assert T_ONE in b005._terms_on_disk(run.cfg), (
        "the reconciliation must still have happened under reject_cap 1"
    )


# --------------------------------------------------------------------------- #
# T3 — the boundary: THREE declaration-side findings at N=2
# --------------------------------------------------------------------------- #


def test_t3_three_findings_at_n2_take_the_ladder_not_the_reconciliation(make_cfg):
    """'their count <= N' is a HARD boundary: 3 > 2 is the normal ladder."""
    run = _run(
        make_cfg,
        "b005r2-boundary",
        tier="t2",
        reports=[_undeclared(T_ONE, T_TWO, T_THREE), b005._pass_report()],
        rejects=1,
        reconcile_early=2,
        round_cap=4,
        reject_cap=1,
    )
    terms = b005._terms_on_disk(run.cfg)
    amended = [t for t in (T_ONE, T_TWO, T_THREE) if t in terms]
    assert not amended, (
        f"THREE declaration-side findings are over N=2 and must NOT be reconciled; "
        f"{amended} were written into the spec anyway: {terms}"
    )
    assert "reconciled early" not in _haystack(run).lower(), (
        "an over-N round must not announce an early reconciliation:\n"
        f"{b005._all_reason_text(run.cfg)}"
    )
    assert _invocations(run).get("s1_spec") == 2, (
        "the normal ladder under reject_cap 1 escalates to a respec (MEASURED "
        f"pre-implementation behaviour: s1_spec runs twice); invocations: "
        f"{_invocations(run)}"
    )


# --------------------------------------------------------------------------- #
# T4 — a non-declaration finding in the mix
# --------------------------------------------------------------------------- #


def test_t4_one_solver_quality_finding_forbids_the_early_path(make_cfg):
    """'EVERY reject reason is declaration-side' — one residual spoils the set.

    Verifier JUDGMENT is never softened: solver-quality is not a labelling
    mismatch and cannot be amended away.
    """
    run = _run(
        make_cfg,
        "b005r2-mixed",
        tier="t2",
        reports=[
            _reject(
                b005._undeclared_term_reason(T_ONE),
                _solver_quality_reason(),
                undeclared=[T_ONE],
            ),
            b005._pass_report(),
        ],
        rejects=1,
        reconcile_early=2,
        round_cap=4,
        reject_cap=1,
    )
    terms = b005._terms_on_disk(run.cfg)
    assert T_ONE not in terms, (
        "a set containing `solver-quality` is not declaration-only and must not be "
        f"reconciled — the spec was amended anyway: {terms}"
    )
    assert "reconciled early" not in _haystack(run).lower(), (
        f"no early reconciliation may be announced:\n{b005._all_reason_text(run.cfg)}"
    )
    assert _invocations(run).get("s1_spec") == 2, (
        f"the mixed set takes the normal ladder; invocations: {_invocations(run)}"
    )


# --------------------------------------------------------------------------- #
# T5 — the NEW subtractive direction
# --------------------------------------------------------------------------- #


def test_t5_a_dead_spec_term_is_removed_from_the_declaration(make_cfg):
    """P-A.2: `dead-spec-term` -> REMOVE the term from `game.terms`.

    At the cap, with the key absent — the subtractive direction is path a's job
    too, not only the early path's.
    """
    doomed = b005.DEAD_TERM
    reject = _dead(doomed)
    run = _run(
        make_cfg,
        "b005r2-subtractive",
        tier="t2",
        reports=[reject, reject, b005._pass_report()],
        rejects=2,
        round_cap=2,
    )
    terms = b005._terms_on_disk(run.cfg)
    assert doomed not in terms, (
        f"the dead term {doomed!r} must be REMOVED from `game.terms` (P-A.2's new "
        f"subtractive direction); the spec still declares {terms}"
    )
    assert terms == [t for t in BASE_TERMS if t != doomed], (
        f"the drop must remove exactly that one term and disturb nothing else: {terms}"
    )
    introduced = _introduced_on_disk(run)
    assert all(doomed not in row for row in introduced), (
        f"`levels[*].terms_introduced` still references the dropped term (P-A.2: "
        f"'and any levels[*].terms_introduced references'). Measured pre-state: the "
        f"fixture introduces {doomed!r} on level 5. Levels now: {introduced}"
    )
    spine = _spine(run)
    assert ("implemented", "verified") in spine, (
        f"the confirming round came back clean but the slot never verified: {spine}"
    )
    assert ("implemented", "dead") not in spine, f"never kill: {spine}"


def test_t5_a_drop_below_the_tier_floor_parks_the_slot(make_cfg):
    """P-A.2 guard: 'a drop below the tier's minimum -> park' (and a lint kill on
    the re-run parks too — both guards route to the same place, which is why this
    strips FIVE of six terms: no reading of "floor" survives one term)."""
    doomed = tuple(t for t in BASE_TERMS if t != "goal.cover")
    assert len(doomed) == 5, doomed
    reject = _dead(*doomed)
    run = _run(
        make_cfg,
        "b005r2-floor",
        tier="t2",
        reports=[reject, reject, b005._pass_report()],
        rejects=2,
        round_cap=2,
    )
    slot = b005._one_slot(run.report)
    assert slot["state"] == "parked", (
        f"stripping 5 of 6 terms drops under every candidate floor (t2 core_terms "
        f"min {tiers.TIER_TABLE['t2'].core_terms[0]}, TERM_BUDGET_MIN "
        f"{tiers.TERM_BUDGET_MIN}) and must PARK, not kill and not proceed. "
        f"State: {slot['state']!r}. Spine: {_spine(run)}"
    )
    assert ("implemented", "dead") not in _spine(run), (
        "operator ruling, 2026-09-29: 'We should never kill.'"
    )
    assert b005._terms_on_disk(run.cfg) == list(BASE_TERMS), (
        "a refused amendment restores the original spec bytes (P-A.2's kept "
        f"invariant); terms on disk: {b005._terms_on_disk(run.cfg)}"
    )


# --------------------------------------------------------------------------- #
# T6 — AUTO-RETIER (the b005-auto death, replayed)
# --------------------------------------------------------------------------- #


def test_t6_the_b005_auto_death_replays_as_a_tier_promotion(make_cfg):
    """P-A.3: 9 declared terms against t2's budget of 8 fits t3 -> PROMOTE.

    This is the death from `out/batches/b005-auto/ledger.jsonl` verbatim in shape:
    'the amended spec declares 9 terms against the t2 budget of 8'. It killed the
    slot and the 1/1 attrition aborted the batch. It must now end verified.
    """
    reject = _undeclared(T_ONE, T_TWO, T_THREE)
    run = _run(
        make_cfg,
        "b005r2-retier",
        tier="t2",
        reports=[reject, reject, b005._pass_report()],
        rejects=2,
        reconcile_early=2,
        round_cap=2,
    )
    terms = b005._terms_on_disk(run.cfg)
    assert len(terms) == 9, (
        f"the replay needs the amended spec to declare 9 terms (6 authored + 3 "
        f"audited) against the t2 budget of {BUDGETS['t2']}; it declares {terms}"
    )
    path, tier = _spec_tier(b005._spec_on_disk(run.cfg))
    assert tier == "t3", (
        "P-A.3: the slot must be PROMOTED t2 -> t3 in spec.yaml (9 terms fits t3's "
        f"ceiling of {BUDGETS['t3']}). spec.yaml carries tier {tier!r} at {path!r}. "
        "MEASURED: the §11 schema had no tier field before this contract, so the "
        "implementer adds one — this walks the whole document to find it."
    )
    text = _haystack(run)
    assert "tier promoted" in text.lower(), (
        "P-A.3 pins the ledger reason 'tier promoted t2->t3: 9 declared terms vs "
        f"budget 8'. Ledger + report:\n{text[:3000]}"
    )
    assert "t3" in text, f"the promotion must name the new tier:\n{text[:3000]}"
    slot = b005._one_slot(run.report)
    assert slot["state"] not in ("dead", "parked"), (
        f"the b005-auto death must now end ALIVE; state {slot['state']!r}, spine "
        f"{_spine(run)}"
    )
    assert ("implemented", "verified") in _spine(run), _spine(run)
    assert "tier_promoted" in b11._text(slot) or "tier_promoted" in b11._text(run.report), (
        "P-A.3 asks for a `tier_promoted` block on the slot row + report; neither "
        f"carries the key. Slot row keys: {sorted(slot)}"
    )


def test_t6_over_the_t3_ceiling_parks_instead_of_promoting(make_cfg):
    """'Over t3's 10 -> park (never trim real mechanics to fit).'"""
    reject = _undeclared(*EXTRA_TERMS)  # 6 + 5 = 11 > 10
    run = _run(
        make_cfg,
        "b005r2-ceiling",
        tier="t3",
        reports=[reject, reject, b005._pass_report()],
        rejects=2,
        round_cap=2,
    )
    slot = b005._one_slot(run.report)
    assert slot["state"] == "parked", (
        f"11 amended terms exceed t3's ceiling of {BUDGETS['t3']} and t3 is the "
        f"CEILING, so the slot parks; state {slot['state']!r}, spine {_spine(run)}"
    )
    assert ("implemented", "dead") not in _spine(run), "never kill"
    assert b005._terms_on_disk(run.cfg) == list(BASE_TERMS), (
        "the over-ceiling amendment must NOT be written (the original bytes are "
        f"restored): {b005._terms_on_disk(run.cfg)}"
    )


# --------------------------------------------------------------------------- #
# T7 — park semantics
# --------------------------------------------------------------------------- #


def _parked_run(make_cfg, batch_id: str, *, max_attrition: float = 1.0):
    """The would-kill scenario from yesterday's path b: a NON-declaration residual
    at the round cap. Yesterday it died; under P-A.4 it parks."""
    reject = _reject(
        b005._undeclared_term_reason(T_ONE),
        _solver_quality_reason(),
        undeclared=[T_ONE],
    )
    return _run(
        make_cfg,
        batch_id,
        tier="t2",
        reports=[reject, reject, reject],
        rejects=3,
        round_cap=2,
        max_attrition=max_attrition,
    )


def test_t7_the_section4_tables_carry_the_parked_edge(make_cfg):
    """P-A.4: edge ("implemented", "parked"), owner s3_verify, label 'round-cap
    park', NEXT_STAGE None — and the dead edge REMAINS so b005-auto's ledger
    replays."""
    assert "parked" in orch.TRANSITIONS.get("implemented", {}), (
        f"TRANSITIONS has no implemented --> parked edge: "
        f"{orch.TRANSITIONS.get('implemented')}"
    )
    label = str(orch.TRANSITIONS["implemented"]["parked"])
    assert "round-cap park" in label.lower(), (
        f"the edge label must carry 'round-cap park'; got {label!r}"
    )
    assert orch.EDGE_STAGE.get(("implemented", "parked")) == "s3_verify", (
        f"the parked edge is owned by s3_verify; EDGE_STAGE says "
        f"{orch.EDGE_STAGE.get(('implemented', 'parked'))!r}"
    )
    assert "parked" in tuple(orch.STATES), (
        f"'parked' must join the §4 state vocabulary; STATES = {tuple(orch.STATES)}"
    )
    assert orch.NEXT_STAGE.get("parked", "MISSING") is None, (
        "parked is TERMINAL for the run — NEXT_STAGE['parked'] must be None, got "
        f"{orch.NEXT_STAGE.get('parked', 'MISSING')!r}"
    )
    assert "dead" in orch.TRANSITIONS.get("implemented", {}), (
        "the ('implemented', 'dead') edge REMAINS in the tables (b005-auto's ledger "
        f"must replay): {orch.TRANSITIONS.get('implemented')}"
    )


def test_t7_a_parked_slot_travels_the_parked_edge_with_its_residuals(make_cfg):
    run = _parked_run(make_cfg, "b005r2-park")
    spine = _spine(run)
    assert ("implemented", "parked") in spine, (
        f"the would-kill outcome must travel implemented --> parked: {spine}"
    )
    assert ("implemented", "dead") not in spine, (
        "operator ruling, 2026-09-29: 'We should never kill. Even if it is not satisfied "
        f"eventually let's not kill.' Spine: {spine}"
    )
    reasons = b005._reasons(run.cfg, ("implemented", "parked"))
    assert reasons, f"the parked edge carries no reason: {b005._all_reason_text(run.cfg)}"
    assert "round-cap park" in reasons[0].lower(), (
        f"the park reason must read 'round-cap park: <codes>'; got {reasons}"
    )
    assert s3v.REJECT_SOLVER_QUALITY in reasons[0], (
        f"'the reason carries the full residual list' — {s3v.REJECT_SOLVER_QUALITY} "
        f"is missing from {reasons[0]!r}"
    )


def test_t7_a_parked_slot_keeps_every_artifact_on_disk(make_cfg):
    """'nothing on disk is deleted'."""
    run = _parked_run(make_cfg, "b005r2-park-artifacts")
    dirs = b005._live_spec_dirs(run.cfg)
    assert len(dirs) == 1, (
        f"the parked slot's corpus dir must stay LIVE (not under "
        f"{orch.KILLED_DIRNAME!r}); found {dirs}"
    )
    slot_dir = dirs[0]
    for name in ("idea.json", "spec.yaml", "worker/game.py"):
        assert (slot_dir / name).is_file(), (
            f"{name} is missing from the parked slot — parking deletes nothing. "
            f"Tree: {sorted(p.name for p in slot_dir.rglob('*'))}"
        )


def test_t7_a_parked_slot_never_aborts_the_batch(make_cfg):
    """'Parked slots are EXCLUDED from the attrition ratio (max_attrition counts
    dead only) and never abort a batch.'

    `max_attrition 0.5` on a ONE-slot batch: MEASURED pre-implementation, the same
    scenario as a death reported status 'stopped', stop_reason 'attrition',
    exit_code 2 and attrition.abort.aborted True. A park must do none of that.
    """
    run = _parked_run(make_cfg, "b005r2-park-attrition", max_attrition=0.5)
    attrition = run.report["attrition"]
    assert attrition.get("abort") in (None, {}, False), (
        f"a parked slot must not tip the attrition abort: {attrition}"
    )
    assert attrition.get("dead") == 0, (
        f"max_attrition counts DEAD only; the parked slot was counted: {attrition}"
    )
    assert run.report.get("stop_reason") != "attrition", (
        f"the batch must COMPLETE, not stop on attrition: "
        f"status={run.report.get('status')!r} stop_reason="
        f"{run.report.get('stop_reason')!r} exit_code={run.report.get('exit_code')!r}"
    )
    assert run.report.get("states") == {"parked": 1}, (
        f"the state census must report the slot as parked: {run.report.get('states')}"
    )


def test_t7_the_batch_report_carries_a_parked_block(make_cfg):
    """'the batch report gains a `parked: [slugs+reasons]` block'."""
    run = _parked_run(make_cfg, "b005r2-park-report")
    assert "parked" in run.report, (
        f"the batch report has no `parked` block; keys: {sorted(run.report)}"
    )
    block = run.report["parked"]
    assert block, f"the `parked` block is empty though a slot parked: {block!r}"
    text = b11._text(block)
    slug = b005._one_slot(run.report)["slug"]
    assert slug in text, f"the block must name the slug {slug!r}: {text}"
    assert "round-cap park" in text.lower() or s3v.REJECT_SOLVER_QUALITY in text, (
        f"the block must carry the park reason beside the slug: {text}"
    )


# --------------------------------------------------------------------------- #
# T8 — unconfigured byte-identity, and the ONE expected delta
# --------------------------------------------------------------------------- #

#: MEASURED pre-implementation (2026-09-29, orchestrator.py mtime 04:33), with
#: `verifier.round_cap 2`, `reject_cap 5`, tier t2 and ONE undeclared term: the
#: path-a ledger reason, byte for byte.
YESTERDAYS_CAP_RECONCILE_REASON = (
    "declaration reconciled to audit: +agent.patrol "
    "(round_cap 2; verifier reject: undeclared-term)"
)

#: MEASURED the same way: the stage sequence and the per-stage invocation census
#: of that run, to the end of the pipeline.
YESTERDAYS_CAP_STAGES = [
    "s0_ideas",
    "s1_spec",
    "s2_implement",
    "s3_verify",
    "s2_implement",
    "s3_verify",
    "s2_implement",
    "s3_verify",
    "s3_gate",
    "s4_baselines",
    "s5_battery",
]
YESTERDAYS_CAP_INVOCATIONS = {
    "s0_ideas": 1,
    "s1_spec": 1,
    "s2_implement": 3,
    "s3_verify": 3,
    "s3_gate": 1,
    "s4_baselines": 1,
    "s5_battery": 1,
}


def test_t8_without_the_key_the_cap_path_is_byte_identical(make_cfg):
    """The house rule: 'unconfigured runs byte-identical to today'.

    No `reconcile_early` key + yesterday's armed `round_cap` = yesterday's run,
    down to the ledger string.
    """
    reject = _undeclared(T_ONE)
    run = _run(
        make_cfg,
        "b005r2-unconfigured",
        tier="t2",
        reports=[reject, reject, b005._pass_report()],
        rejects=2,
        round_cap=2,
    )
    assert CONFIG_KEY not in run.cfg.get("verifier", {}), "this run must be UNCONFIGURED"
    reasons = b005._reasons(run.cfg, ("implemented", "spec_ok"))
    assert YESTERDAYS_CAP_RECONCILE_REASON in reasons, (
        "the round-cap reconciliation reason moved. It was MEASURED pre-merge as:\n"
        f"  {YESTERDAYS_CAP_RECONCILE_REASON}\nand the ledger now carries:\n"
        + "\n".join(f"  {r}" for r in reasons)
        + "\nP-A.1's new wording belongs to the EARLY path only."
    )
    assert "reconciled early" not in _haystack(run).lower(), (
        "an unconfigured run must never take (or announce) the early path"
    )
    assert [call.stage for call in run.journal.calls] == YESTERDAYS_CAP_STAGES, (
        f"the stage sequence moved:\n  live:   "
        f"{[call.stage for call in run.journal.calls]}\n  pinned: {YESTERDAYS_CAP_STAGES}"
    )
    assert _invocations(run) == YESTERDAYS_CAP_INVOCATIONS, (
        f"the invocation census moved:\n  live:   {_invocations(run)}\n"
        f"  pinned: {YESTERDAYS_CAP_INVOCATIONS}"
    )
    assert b005._terms_on_disk(run.cfg) == [*BASE_TERMS, T_ONE], (
        f"the additive amendment itself moved: {b005._terms_on_disk(run.cfg)}"
    )
    assert run.runners.verify_calls == 3


def test_t8_the_one_expected_delta_is_that_the_kill_is_now_a_park(make_cfg):
    """THE ONE DELTA this file documents against `test_b005_autonomy`'s T6.

    That file's `_assert_round_cap_kill` pins ("implemented", "dead") + a
    'round-cap kill' reason + state 'dead' for three scenarios. Under the operator's
    ruling — "We should never kill. Even if it is not satisfied eventually let's
    not kill." — every one of them is now a PARK. The implementer updates those
    three pins and nothing else; this test states the delta from the blind side so
    the two lanes cannot silently disagree about it.
    """
    run = _parked_run(make_cfg, "b005r2-delta")
    slot = b005._one_slot(run.report)
    assert slot["state"] == "parked", (
        "yesterday this scenario (a solver-quality residual surviving to the round "
        f"cap) ended 'dead'; it must now end 'parked'. Got {slot['state']!r}"
    )
    assert ("implemented", "parked") in _spine(run)
    assert ("implemented", "dead") not in _spine(run)
    # ... and everything ELSE about the scenario is unchanged: the residual still
    # refuses reconciliation, and the spec is left exactly as authored.
    assert b005._terms_on_disk(run.cfg) == list(BASE_TERMS), (
        f"nothing is reconciled on the park path: {b005._terms_on_disk(run.cfg)}"
    )
    assert run.runners.verify_calls == 2, (
        "the park happens AT the cap — the audit runs twice and is not re-run past "
        f"it; it ran {run.runners.verify_calls}x"
    )


def test_t8_no_verify_lane_scenario_in_this_file_reaches_dead(make_cfg):
    """P-A.4: 'EVERY would-kill outcome from yesterday's path b routes there
    instead' — the three shapes, in one sweep."""
    shapes = {
        "non-declaration residual": _parked_run(make_cfg, "b005r2-sweep-residual"),
        "budget overflow past t3": _run(
            make_cfg,
            "b005r2-sweep-ceiling",
            tier="t3",
            reports=[_undeclared(*EXTRA_TERMS)] * 2 + [b005._pass_report()],
            rejects=2,
            round_cap=2,
        ),
        "floor / lint refusal": _run(
            make_cfg,
            "b005r2-sweep-floor",
            tier="t2",
            reports=[_dead(*(t for t in BASE_TERMS if t != "goal.cover"))] * 2
            + [b005._pass_report()],
            rejects=2,
            round_cap=2,
        ),
    }
    for why, run in shapes.items():
        assert ("implemented", "dead") not in _spine(run), (
            f"{why}: the verify lane still routes to dead. Spine: {_spine(run)}"
        )
        assert b005._one_slot(run.report)["state"] == "parked", (
            f"{why}: expected 'parked', got {b005._one_slot(run.report)['state']!r}"
        )


# --------------------------------------------------------------------------- #
# T9 (P-B) — the seed self-check in the findings feed
# --------------------------------------------------------------------------- #

#: MEASURED: `s2_implement.findings_section({"verdict": "reject", "reject_reasons":
#: [{"code": "synth-bare"}]})` on 2026-09-29 at 16:31 IST, with gen/s2_implement.py
#: at mtime 2026-09-28 19:10 — i.e. BEFORE P-B could touch it. sha256 below.
SNAPSHOT_NO_SEED = """\
## The blind audit REJECTED the previous build of this game — its findings

- `synth-bare`

Fix EVERY finding above in this rebuild — all of them, not the cheapest ones.

The audit that wrote them re-runs BLIND on whatever you ship: it never reads
the spec, this prompt, your commit message or your final reply, and it
re-derives every mechanic and lever it reports FROM THE CODE ALONE. So each fix
has to change what `game.py` / `solver.py` actually do. Prose cannot answer a
finding — a comment, a docstring or an explanation of why the code is fine
changes nothing the audit can see.

The spec is still the whole surface, and the scope clause above applies
unchanged. A finding is NEVER licence to add surface the spec does not declare:

- reachable-but-undeclared (an extra term, lever, effect or tell the audit
  read off the game) is fixed by REMOVING that behaviour, or by redesigning it
  INSIDE what the spec declares — never by keeping it;
- declared-but-unreachable (the spec names it and the audit could not reach it)
  is fixed by BUILDING it, reachable by a player in ordinary play.
"""
SNAPSHOT_NO_SEED_SHA256 = hashlib.sha256(SNAPSHOT_NO_SEED.encode("utf-8")).hexdigest()

#: the crashing seed of the b005 T1 fixture, as `validation_seeds` draws it.
CRASH_SEED = 1583659104

#: the stage-findings feed, in the shape `_write_stage_findings` writes (MEASURED:
#: {schema_version, stage, verdict, reason, reject_reasons:[{code, detail}]}).
#: TWO variants, because the contract says "code names the seed" while the feed
#: this lane could actually observe names the seed in the DETAIL: a detector that
#: reads either one passes both.
SEED_FEED_SUPERSET = {
    "schema_version": "b11.1",
    "stage": "s6_package",
    "verdict": "reject",
    "reason": f"seed-reject: seed {CRASH_SEED}",
    "reject_reasons": [
        {
            "code": f"s6_package-seed-{CRASH_SEED}",
            "detail": (
                f"seed {CRASH_SEED}: re-deriving the worker's build_layout(seed) "
                f"crashed at seed {CRASH_SEED}: ValueError: no winning line for "
                f"level 4 (at game.py:212)"
            ),
            "seed": CRASH_SEED,
        }
    ],
    "worker_crashes": [
        {
            "seed": CRASH_SEED,
            "exc": "ValueError",
            "message": "no winning line for level 4",
            "where": "game.py:212",
        }
    ],
    "seeds_failed": [CRASH_SEED],
}

SEED_FEED_DETAIL_ONLY = {
    "schema_version": "b11.1",
    "stage": "s6_package",
    "verdict": "reject",
    "reason": f"seed-reject: seed {CRASH_SEED}",
    "reject_reasons": [
        {
            "code": "s6_package-fail",
            "detail": f"seed {CRASH_SEED}: build_layout crashed (ValueError)",
        }
    ],
}

NO_SEED_FEED = {
    "verdict": "reject",
    "reject_reasons": [
        {"code": s3v.REJECT_SOLVER_QUALITY, "detail": "level 2 needs pixel-hunting"}
    ],
}


def _rendered_findings(report) -> str:
    """The S2 findings section as the next worker session sees it.

    P-B may land in `gen/s2_implement.findings_section` or in an orchestrator-side
    wrapper ("wherever the findings render"), so this takes the renderer's output
    plus any orchestrator-owned single-argument renderer whose name mentions
    findings — and concatenates, so either siting passes.
    """
    parts = [s2_implement.findings_section(report)]
    for name, value in sorted(vars(orch).items()):
        if not callable(value) or "findings" not in name.lower():
            continue
        if getattr(value, "__module__", None) != orch.__name__:
            continue  # imported, e.g. findings_section itself
        try:
            extra = value(report)
        except Exception:  # noqa: BLE001, S112 — a helper with another shape is not ours
            continue
        if isinstance(extra, str):
            parts.append(extra)
    return "\n".join(parts)


def _normalised(text: str) -> str:
    """Whitespace-flattened, so a hard-wrapped paragraph still matches."""
    return " ".join(text.split())


@pytest.mark.parametrize(
    "feed",
    [SEED_FEED_SUPERSET, SEED_FEED_DETAIL_ONLY],
    ids=["code-and-detail-name-the-seed", "only-the-detail-names-the-seed"],
)
def test_t9_a_seed_row_appends_the_reproduction_instruction(feed):
    """P-B: seed rows -> one instruction paragraph naming build_layout and the seed."""
    rendered = _rendered_findings(feed)
    assert "build_layout(" in rendered, (
        "P-B: the findings section must demand a `build_layout(<seed>)` "
        f"reproduction when a seed row is present. Rendered:\n{rendered}"
    )
    assert str(CRASH_SEED) in rendered, (
        f"the instruction must name the failing seed {CRASH_SEED}:\n{rendered}"
    )
    flat = _normalised(rendered)
    assert "state in one line that you did" in flat, (
        "P-B's paragraph ends with the one-line statement demand ('state in one "
        f"line that you did'):\n{rendered}"
    )


def test_t9_the_instruction_paragraph_is_the_contract_s_own_sentence():
    """The paragraph, verbatim (whitespace-flattened, because it is hard-wrapped).

    Split out from the test above ON PURPOSE: if only THIS one reds, the delta is
    wording, not behaviour, and the lead can adjudicate in one line.
    """
    expected = _normalised(
        f"Before finishing: reproduce build_layout({CRASH_SEED}) for EVERY seed "
        "named above and verify a winning line exists for every level (the §7 "
        "check); state in one line that you did."
    )
    flat = _normalised(_rendered_findings(SEED_FEED_SUPERSET))
    assert expected in flat, (
        f"P-B quotes the paragraph verbatim:\n  {expected}\nRendered (flattened):\n"
        f"  {flat}"
    )


def test_t9_findings_without_seed_rows_are_byte_identical_to_the_pre_capture():
    """'renders ONLY when seed rows are present; all other findings render
    byte-identical to today.'"""
    live = s2_implement.findings_section(
        {"verdict": "reject", "reject_reasons": [{"code": "synth-bare"}]}
    )
    assert hashlib.sha256(live.encode("utf-8")).hexdigest() == SNAPSHOT_NO_SEED_SHA256, (
        "the no-seed findings render moved off the PRE-IMPLEMENTATION snapshot "
        "(captured 2026-09-29 16:31 IST, before gen/s2_implement.py was touched).\n"
        f"--- pinned ---\n{SNAPSHOT_NO_SEED}\n--- live ---\n{live}"
    )
    assert live == SNAPSHOT_NO_SEED


def test_t9_a_seedless_reject_carries_no_reproduction_demand():
    """The other half of prompt-sync: no seed row, no paragraph."""
    rendered = _rendered_findings(NO_SEED_FEED)
    assert "build_layout(" not in rendered, (
        f"a seedless reject must not carry the seed self-check:\n{rendered}"
    )
    body = s2_implement.findings_section(NO_SEED_FEED)
    expected = SNAPSHOT_NO_SEED.replace(
        "- `synth-bare`",
        f"- `{s3v.REJECT_SOLVER_QUALITY}` — level 2 needs pixel-hunting",
    )
    assert body == expected, (
        "a seedless reject must render exactly today's section with only its own "
        f"bullet swapped in.\n--- expected ---\n{expected}\n--- live ---\n{body}"
    )


# --------------------------------------------------------------------------- #
# the fixture wall — the rig this file borrows, still the rig it was written to
# --------------------------------------------------------------------------- #


def test_the_rig_this_file_subclasses_still_has_the_shape_it_was_written_to():
    for name in ("_SpecRunners", "_armed_cfg", "_reject_report", "_undeclared_term_reason",
                 "_dead_term_reason", "_pass_report", "_terms_on_disk", "_spec_on_disk",
                 "_reasons", "_all_reason_text", "_one_slot", "_live_spec_dirs", "_Run"):
        assert hasattr(b005, name), (
            f"gen/tests/test_b005_autonomy.py no longer exposes {name!r} — this "
            "file borrows the rig by name (the contract's 'do NOT copy 600 lines')"
        )
    assert b005.DEAD_TERM == BASE_TERMS[-1] == "info.recall", (
        f"the rig's DEAD_TERM moved: {b005.DEAD_TERM!r}"
    )
    assert Path(b005.SPEC_FIXTURE).is_file() and Path(b005.IDEA_FIXTURE).is_file()
