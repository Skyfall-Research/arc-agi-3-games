"""B005 BLIND LANE: S6 containment (P-1), the failure edges (P-2), autonomy (P-3).

Run: .venv/bin/python -m pytest gen/tests/test_b005_autonomy.py -q

WRITTEN BLIND, FROM THE FROZEN CONTRACT ALONE (b005-autonomy-contract.md). No
git diff, no implementation body, was read to write it. What WAS read, and
only to learn public surfaces the contract itself names:

  * `gen/orchestrator.py`'s §4 tables (TRANSITIONS / EDGE_STAGE / NEXT_STAGE /
    STAGE_SUCCESS / STAGE_FAILURE / STATES / the three caps) — captured LIVE at
    test-writing time and hand-pinned below as literals (T2's requirement, and
    the stale-HEAD lesson: a pin is a copy of today's bytes, never a delta);
  * the runner-result contract `{ok, to_state, reason, cost, artifacts}` and
    `SlotContext`'s field names, which any fake must satisfy;
  * `gen/s6_package.py`'s frozen signatures (`run_s6`, `validation_seeds`,
    `VERDICT_*`, `OUT_SUFFIX`) — the b10 contract's own frozen surface;
  * `gen/s3_verify.py`'s frozen REJECT_* codes and DIFF_KEYS, because the
    contract quotes the code strings as its routing condition;
  * the test rigs the contract told this lane to reuse: `test_b11_pipeline`
    (fake stages, the two write guards, `batch_home`/`make_cfg`),
    `test_b004_solverquality_crash` (the toy_worker crash pattern),
    `test_b10_package` (`_write_worker`, the staged S4 fixture, the play-root
    guard), `test_r2_hotfix6` (the verifier-report plant).

DISCLOSURE — ONE CONTAMINATION, REPORTED RATHER THAN HIDDEN. While grepping
`gen/orchestrator.py` for `_apply_review`'s line number (the contract's own
evidence citation) the file had already moved under this lane: ten lines of a
NEW function's docstring scrolled past, and they named a result key `findings`
for a stage's failure rows. Nothing else of the implementation was read, and no
ASSERTION in this file was changed because of it. The one thing it did change:
`_GateRunners` declares its failing rows under BOTH `reject_reasons` (the feed
shape the contract's Evidence section names) AND `findings`, so that T3 fails
for a routing/propagation defect rather than for a fake speaking the wrong
protocol. The assertion T3 makes is unchanged and implementation-blind: the
rows must end up in a file THIS FILE DID NOT WRITE.

WHAT EACH TEST PINS
-------------------
T1  `run_s6` containment. A copy of `fixtures/s6_seeded` whose `build_layout`
    raises `ValueError("no winning line for level 4")` — the b004 seed-3 crash,
    verbatim — for exactly ONE of the five validation seeds. Pins: run_s6 does
    not raise; the verdict is `seed-reject`; a FAILURE ROW names that seed, the
    exception class, its message and the worker file (`game.py`); and no
    package surface is written (no `package/`, no manifest, no TSV, no play
    mirror). Plus the b004 counter-test: the untouched fixture still packages,
    so the containment cannot be a blanket swallow.
T2  The §4 tables. The four new edges (reviewed→spec_ok, verified→spec_ok,
    gated→spec_ok, implemented→dead) with owners s6_package / s3_gate /
    s4_baselines / s3_verify, the three new STAGE_FAILURE rows, and — the real
    content of T2 — EVERY OTHER ROW BYTE-IDENTICAL to the hand-pinned copy of
    today's tables taken from the live module while writing this file.
T3  Gate-fail routing + the findings feed + the loop guard. A fake s3_gate that
    fails a visual check lands the slot on `spec_ok`, the ledger reason carries
    "gate fail" and the contract's own count string ("1/2"), S2 is invoked
    again, and the failing check id + note reach a findings file this rig did
    not write. The second gate fail carries "2/2" and escalates (the ×cap
    ladder), so implement↔gate cannot loop.
T4  `verifier.round_cap` validation: absent → None; 1 / 0 / -1 / "x" / True →
    ValueError; 2 → 2; 4 → 4.
T5  Mechanical reconciliation, happy path: at round_cap the ONLY residual is
    `undeclared-term: agent.patrol` → spec.yaml's `game.terms` gains the term,
    a ledger reason says "reconciled", the audit is re-run once, and the clean
    confirming round lands `verified`. The slot never dies.
T6  The three guards, one test each: over the tier's KILL budget (t1, 6 terms
    already) → dead; a `dead-spec-term` residual beside the declaration-side
    one → dead; a reconciliation whose confirming round rejects again → dead.
    Every one lands `("implemented", "dead")` with "round-cap kill" in the
    reason.
T7  `review.auto_accept`: absent and false both keep today's human stop (the
    slot sits at `played`, no `played→reviewed` line, s6 never runs, the stop
    names `--review`); true travels `played → reviewed` with an "auto-accept"
    reason naming the knob, runs s6 IN THE SAME `run_batch` call, and the batch
    report carries an `auto_accepted` list holding the slug. A non-bool is a
    loud error.
T8  Byte-identity. With NO `round_cap` and NO `review` block a verifier reject
    routes exactly as today: implemented→spec_ok, ×VERIFIER_REJECT_CAP_ESCALATE
    → the escalation reason routes respec, the declaration is NEVER touched
    (the spec's terms are still the authored six) and no ledger line anywhere
    says "reconcil".

CONTRACT AMBIGUITIES THIS FILE TOOK A POSITION ON (loudly, per the brief)
------------------------------------------------------------------------
A. THE EDGE LABELS. The contract quotes label text ("gate fail → re-implement",
   "package fail → re-implement (§3: the layout function is buggy)", "cap-fit
   fail → re-implement (§3: cap bug)", "round-cap kill") but §4 labels are
   prose and today's table mixes spellings (`×2`, `→`). Each new label is
   asserted to CONTAIN its distinctive phrase, case-folded; the full string is
   not pinned. Every UNCHANGED label IS pinned byte-for-byte.
B. WHERE A FAILED RUNNER'S DESTINATION COMES FROM. b11's rig convention is that
   a routed failure returns the diagram's destination, so T3's fake gate
   returns `to_state="spec_ok"`. T3 therefore cannot distinguish "the
   orchestrator routed it through STAGE_FAILURE" from "the runner said so";
   T2 is what pins the table. Deliberate: a fake that returned the unchanged
   state would test `_check_result`'s tolerance, not the edge.
C. WHICH LEDGER EDGE CARRIES THE RECONCILIATION LINE. P-3.2a says "ledger line
   + report block" and "the slot re-enters `implemented`", but §4 has no
   implemented→implemented edge and the contract does not say whether the
   reject's own spec_ok trip still happens first. T5/T6 assert the OUTCOME —
   the amended spec, a reason containing "reconcil", the extra audit round, the
   landing state — and pin no edge for the reconciliation line itself.
D. round_cap VS reject_cap AT THE SAME ROUND. With both at 2 the round_cap
   reconciliation and the ×2 respec escalation would fire on the same reject
   and the contract does not order them. T5/T6 duck it by arming
   `reject_cap: 5` with `round_cap: 2`, so only the round cap can fire. THE
   COLLISION IS UNTESTED AND UNRESOLVED — flagged for the lead, because b005's
   own config arms `reject_cap: 1`, where a round_cap ≥ 2 may be unreachable.
E. WHERE THE TIER'S KILL BUDGET IS READ. `tiers.DEFAULT_TERM_BUDGETS` and a
   parsed `tiers:` block both express {t1:6, t2:8, t3:10}. T5/T6 arm the config
   block AND use the same numbers, so either reading fires identically.
F. HOW THE FINDING NAMES ITS TERM. The planted reject carries 'agent.patrol' in
   three places at once — `reject_reasons[].detail`, a `term` key beside it,
   and `diff.undeclared_terms` — so no extraction route is privileged.
G. THE AUTO-ACCEPT REPORT BLOCK. `auto_accepted: [slugs]` is looked up by KEY
   anywhere in the batch report (the report's nesting is not frozen; b11's
   ambiguity D), and must be a list containing the slug.
H. `_round_cap`'s NAME. The contract says "read beside `_reject_cap` (same
   style)" and names no function. T4 resolves it by searching the orchestrator
   for a callable whose name contains "round_cap", and fails with the
   candidate list if there is none.

RULES KEPT: no network (b11's autouse guard is re-bound), no CLI, no API, no
writes outside tmp (b11's batch-root guard and b10's play-root guard are both
re-bound), no fixture or test outside this file is modified.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from gen import orchestrator as orch
from gen import s3_gate as gate
from gen import s3_verify as s3v
from gen import s6_package as s6
from gen import tiers
from gen.config import load_config
from gen.s4_baselines import run_s4

# The rigs, imported and called through their owner's alias (the
# test_iteration_dynamics precedent: borrowed, never copied, never modified).
from gen.tests import test_b004_solverquality_crash as b004
from gen.tests import test_b10_package as b10
from gen.tests import test_b11_pipeline as b11

# --- re-bound guards + fixtures (autouse survives the re-binding) -----------
_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched
_repo_play_root_untouched = b10._repo_play_root_untouched
batch_home = b11.batch_home
make_cfg = b11.make_cfg

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
SPEC_FIXTURE = FIXTURES / "specs" / "good-spec.yaml"
IDEA_FIXTURE = FIXTURES / "specs" / "idea-001.json"
PILOT_CONFIG = "config/b001-pilot.yaml"

_CFG = load_config(PILOT_CONFIG)

# --- the stage names, READ off the orchestrator's own table -----------------
S0_STAGE = orch.NEXT_STAGE["respec"]
S1_STAGE = orch.NEXT_STAGE["ideated"]
S2_STAGE = orch.NEXT_STAGE["spec_ok"]
S2B_STAGE = orch.NEXT_STAGE["implemented"]
S3_GATE_STAGE = orch.NEXT_STAGE["verified"]
S4_STAGE = orch.NEXT_STAGE["gated"]
S6_STAGE = orch.NEXT_STAGE["reviewed"]


# --------------------------------------------------------------------------- #
# T2 — TODAY'S §4 TABLES, HAND-PINNED
#
# Transcribed by hand from the LIVE `gen/orchestrator.py` while writing this
# file (2026-09-29). This is the "no other row changed" baseline: the live
# tables minus the four new edges must equal these literals, byte for byte,
# labels included.
# --------------------------------------------------------------------------- #

PINNED_TRANSITIONS: dict[str | None, dict[str, str]] = {
    None: {"ideated": "[*] --> ideated"},
    "ideated": {"spec_ok": "lint pass", "respec": "lint kill"},
    "respec": {"ideated": "re-sample"},
    "spec_ok": {"implemented": "validate green", "dead": "green-attempts cap ×2"},
    "implemented": {"verified": "S2b clean", "spec_ok": "verifier reject ×2 → respec"},
    "verified": {"gated": "structural + robustness green"},
    "gated": {"baselined": "g-sampler + cap-fit"},
    "baselined": {"played": "battery done"},
    "played": {"reviewed": "human accept", "implemented": "crash"},
    "reviewed": {"packaged": "", "pulled": ""},
    "packaged": {},
    "dead": {},
    "pulled": {},
    # PIN UPDATE, 2026-09-29 (contract P-A.4). OPERATOR RULING, on the record,
    # verbatim: "We should never kill. Even if it is not satisfied eventually
    # let's not kill." `parked` is the round-cap verdict's non-death terminal,
    # and like every other terminal state its row is empty. The edge that
    # reaches it is listed in NEW_EDGES below, which is what keeps "no other row
    # changed" an exact check.
    "parked": {},
}

PINNED_EDGE_STAGE: dict[tuple[str | None, str], str | None] = {
    (None, "ideated"): "s0_ideas",
    ("respec", "ideated"): "s0_ideas",
    ("ideated", "spec_ok"): "s1_spec",
    ("ideated", "respec"): "s1_spec",
    ("spec_ok", "implemented"): "s2_implement",
    ("spec_ok", "dead"): "s2_implement",
    ("implemented", "verified"): "s3_verify",
    ("implemented", "spec_ok"): "s3_verify",
    ("verified", "gated"): "s3_gate",
    ("gated", "baselined"): "s4_baselines",
    ("baselined", "played"): "s5_battery",
    ("played", "reviewed"): None,
    ("played", "implemented"): None,
    ("reviewed", "packaged"): "s6_package",
    ("reviewed", "pulled"): None,
}

PINNED_STAGE_FAILURE: dict[str, str | None] = {
    "s0_ideas": None,
    "s1_spec": "respec",
    "s2_implement": "dead",
    "s3_verify": "spec_ok",
    "s3_gate": None,          # P-2.1 fills this with "spec_ok"
    "s4_baselines": None,     # P-2.2 fills this with "spec_ok"
    "s5_battery": "implemented",
    "s6_package": None,       # P-1.2 fills this with "spec_ok"
}

PINNED_NEXT_STAGE: dict[str | None, str | None] = {
    None: "s0_ideas",
    "ideated": "s1_spec",
    "respec": "s0_ideas",
    "spec_ok": "s2_implement",
    "implemented": "s3_verify",
    "verified": "s3_gate",
    "gated": "s4_baselines",
    "baselined": "s5_battery",
    "played": None,
    "reviewed": "s6_package",
    "packaged": None,
    "dead": None,
    "pulled": None,
    # PIN UPDATE, 2026-09-29 (contract P-A.4): parked is TERMINAL for the run —
    # nothing runs from it — on operator ruling, verbatim: "We should never kill.
    # Even if it is not satisfied eventually let's not kill." The slot stops
    # with every artifact intact rather than dying.
    "parked": None,
}

PINNED_STAGE_SUCCESS: dict[str, str] = {
    "s0_ideas": "ideated",
    "s1_spec": "spec_ok",
    "s2_implement": "implemented",
    "s3_verify": "verified",
    "s3_gate": "gated",
    "s4_baselines": "baselined",
    "s5_battery": "played",
    "s6_package": "packaged",
}

PINNED_STATES = (
    "ideated", "respec", "spec_ok", "implemented", "verified",
    "gated", "baselined", "played", "reviewed", "packaged",
    "dead", "pulled",
    # PIN UPDATE, 2026-09-29 (contract P-A.4) — OPERATOR RULING, verbatim: "We
    # should never kill. Even if it is not satisfied eventually let's not kill."
    "parked",
)
PINNED_TERMINAL = ("packaged", "dead", "pulled", "parked")
PINNED_CAPS = {
    "VERIFIER_REJECT_CAP_ESCALATE": 2,
    "GREEN_CAP_DEATHS": 2,
    "RESPEC_CAP": 2,
}

#: the §4 rows P-1/P-2/P-3 add — and, since 2026-09-29, P-A.4's fifth:
#: edge -> (owner stage, the label's phrase).
NEW_EDGES: dict[tuple[str, str], tuple[str, str]] = {
    ("reviewed", "spec_ok"): ("s6_package", "package fail"),
    ("verified", "spec_ok"): ("s3_gate", "gate fail"),
    ("gated", "spec_ok"): ("s4_baselines", "cap-fit fail"),
    ("implemented", "dead"): ("s3_verify", "round-cap kill"),
    # PIN UPDATE, 2026-09-29 (contract P-A.4). OPERATOR RULING, on the record,
    # verbatim: "We should never kill. Even if it is not satisfied eventually
    # let's not kill." Same owner as the kill edge above — it IS that verdict
    # standing, with the outcome the ruling asks for. The kill edge stays in the
    # table (b005-auto's ledger must replay) with no live path routing to it.
    ("implemented", "parked"): ("s3_verify", "round-cap park"),
}

#: the three STAGE_FAILURE rows P-1.2 / P-2.1 / P-2.2 turn from None into an
#: edge. `s3_verify` KEEPS "spec_ok" — the round-cap kill is a separate
#: routing, not that stage's failure state.
NEW_STAGE_FAILURE = {"s3_gate": "spec_ok", "s4_baselines": "spec_ok", "s6_package": "spec_ok"}

#: PIN UPDATE, 2026-10-05 (contract E-2 §2/§3) — the park edges a LATER contract
#: added, exempted from T2's "no other row changed" checks and from nothing else.
#: They are kept OUT of `NEW_EDGES` on purpose: that dict is P-1/P-2/P-3/P-A's
#: own pin, labels included, and widening it would make this file assert E-2's
#: contract instead of recording that E-2 happened. P-A.4 gave the park to the
#: verify lane alone; E-2 gives it to the three downstream lanes
#: (`orchestrator.stage_fail_park`, measured on g20261001-5's four
#: past-the-cap downstream rejects) and to the re-spec seam
#: (`orchestrator.respec_feasibility`). Both knobs default false = today's
#: bytes, so these edges are unreachable unless a batch arms them.
E2_PARK_EDGES: frozenset[tuple[str, str]] = frozenset({
    ("verified", "parked"),
    ("gated", "parked"),
    ("reviewed", "parked"),
    ("spec_ok", "parked"),
})

#: PIN UPDATE, 2026-10-06 (contract E-5 §1) — the park's five LIFT edges, a
#: LATER contract's rows again, exempted from T2's "no other row changed" checks
#: on exactly the terms `E2_PARK_EDGES` above is: they are not P-1/P-2/P-3/P-A's
#: rows changing, and widening `NEW_EDGES` would make this file assert E-5's
#: contract instead of recording that E-5 happened. One lift per edge INTO
#: `parked` (E-2's four plus P-A.4's `implemented`), and they are not reachable
#: by a RUN at all — no knob arms them, no stage verdict routes to them; the
#: only traveller is the operator command `arc-games unpark`. So every batch
#: b001..b005r2 still behaves byte for byte as it did, which is what this file
#: is here to keep true.
E5_LIFT_EDGES: frozenset[tuple[str, str]] = frozenset(
    ("parked", state) for state in
    ({src for src, _dst in E2_PARK_EDGES} | {"implemented"})
)

#: the three sets above, as one exemption — the later contracts' rows.
LATER_CONTRACT_EDGES: frozenset[tuple[str, str]] = E2_PARK_EDGES | E5_LIFT_EDGES


# --------------------------------------------------------------------------- #
# T1 — the crashing worker (the b004 seed-3 replay, as a fixture)
# --------------------------------------------------------------------------- #

#: the b004 crash, verbatim: `ValueError: no winning line for level 4`, seed 3.
CRASH_EXC = "ValueError"
CRASH_MESSAGE = "no winning line for level 4"

#: appended to a COPY of fixtures/s6_seeded/game.py. `build_layout` is a
#: module-level pure function (the §7 contract), so rebinding it here is what
#: every later call — `_serialize_layout`'s rederivation and `Game.__init__`'s
#: own `build_layout(seed)` — resolves to.
CRASH_TAIL = '''

# --- b005 blind-lane override: build_layout CRASHES on exactly one seed -----
_b005_authored_build_layout = build_layout


def build_layout(seed: int) -> list:  # noqa: F811
    """The b004 seed-3 shape: worker code that dies for one seed only."""
    if int(seed) == {bad_seed}:
        raise ValueError("{message}")
    return _b005_authored_build_layout(seed)
'''


@pytest.fixture(scope="session")
def crashing_worker(tmp_path_factory) -> tuple[Path, int, list[int]]:
    """A staged s6_seeded whose build_layout raises for ONE validation seed.

    The seed is COMPUTED from the frozen `validation_seeds` rather than
    guessed, and the tail is appended BEFORE `run_s4` so the worker's bytes
    never move between the two stages. S4 drives the AUTHORED seed, which the
    override leaves alone — asserted here, so a setup defect can never be read
    as a containment defect.
    """
    seeds = s6.validation_seeds(_CFG, b10.SEEDED_GAME_ID, b10.AUTHORED_SEED)
    assert len(seeds) >= 2 and seeds[0] == b10.AUTHORED_SEED, (
        f"fixture drift: validation_seeds no longer leads with the authored seed: {seeds}"
    )
    bad_seed = seeds[1]
    assert bad_seed != b10.AUTHORED_SEED
    root = tmp_path_factory.mktemp("b005s6crash")
    worker = b10._write_worker(
        root / b10.SEEDED.name,
        b10.SEEDED,
        tail=CRASH_TAIL.format(bad_seed=bad_seed, message=CRASH_MESSAGE),
    )
    report = run_s4(worker, _CFG, seed=b10.S4_SEED)
    assert report["verdict"] == "fit", (
        f"setup: S4 must still gate the patched worker (authored seed untouched); "
        f"got {report['verdict']}"
    )
    return worker, bad_seed, seeds


@pytest.fixture(scope="session")
def healthy_worker(tmp_path_factory) -> Path:
    """The same staging, unpatched — the counter-test's subject (b004 pattern)."""
    root = tmp_path_factory.mktemp("b005s6clean")
    worker = b10._write_worker(root / b10.SEEDED.name, b10.SEEDED)
    report = run_s4(worker, _CFG, seed=b10.S4_SEED)
    assert report["verdict"] == "fit", report["verdict"]
    return worker


def _seed_rows(payload) -> list[dict]:
    """Every mapping in the report that looks like a per-seed verdict row."""
    return [
        node
        for node in b11._walk(payload)
        if isinstance(node, dict) and "seed" in node and isinstance(node.get("seed"), int)
    ]


def test_t1_the_patched_worker_really_crashes_raw(crashing_worker):
    """Group-0 discipline: prove the premise with no S6 code in the loop.

    Without this, a tail that silently failed to apply would let every
    containment assertion below pass for the wrong reason.
    """
    worker, bad_seed, _seeds = crashing_worker
    module = b10._game_module(worker)
    assert module.build_layout(b10.AUTHORED_SEED), "the authored seed must still build"
    with pytest.raises(ValueError, match=CRASH_MESSAGE):
        module.build_layout(bad_seed)


def test_t1_a_build_layout_crash_is_contained_as_a_seed_failure(crashing_worker, tmp_path):
    """P-1.1: worker code that raises is a VERDICT, never our exception."""
    worker, bad_seed, _seeds = crashing_worker
    out_dir = tmp_path / "crash" / "out"
    play_root = tmp_path / "crash" / "play"

    try:
        report = s6.run_s6(worker, _CFG, out_dir=out_dir, play_root=play_root)
    except BaseException as exc:
        raise AssertionError(
            "P-1.1: every call into worker code during layout rederivation / seed "
            "validation must be wrapped (the s3 `run_solver_quality` pattern) and "
            f"become a FAILURE row. run_s6 raised instead: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    assert report["verdict"] == s6.VERDICT_SEED_REJECT, (
        f"a worker crash at seed {bad_seed} must land the failed verdict "
        f"{s6.VERDICT_SEED_REJECT!r}, got {report['verdict']!r}:\n{b11._text(report)}"
    )

    rows = _seed_rows(report)
    failing = [row for row in rows if row["seed"] == bad_seed]
    assert failing, (
        f"the reject block names no row for the crashing seed {bad_seed} "
        f"(P-1.1: 'the seed's verdict becomes a FAILURE row naming the seed'). "
        f"Rows:\n{b11._text(rows)}"
    )
    row = failing[0]
    assert row.get("win") is not True, f"the crashing seed is recorded as a win: {row}"

    text = b11._text(row)
    for needle, why in (
        (CRASH_EXC, "the exception CLASS"),
        (CRASH_MESSAGE, "the exception MESSAGE"),
        ("game.py", "the worker-file crash site (traceback.extract_tb, last worker frame)"),
    ):
        assert needle in text, (
            f"the failure row does not name {why} ({needle!r}) — P-1.1 requires all "
            f"three. Row:\n{text}"
        )


def test_t1_a_contained_crash_writes_no_package_surface(crashing_worker, tmp_path):
    """P-1.1: 'package NOT written, no partial artifacts'."""
    worker, _bad_seed, _seeds = crashing_worker
    out_dir = tmp_path / "nosurface" / "out"
    play_root = tmp_path / "nosurface" / "play"
    s6.run_s6(worker, _CFG, out_dir=out_dir, play_root=play_root)

    assert not (out_dir / "package").exists(), (
        f"a failed package left corpus surface behind: "
        f"{sorted(str(p) for p in (out_dir / 'package').rglob('*'))}"
    )
    assert not (out_dir / b10.MANIFEST_REL).exists()
    assert not (out_dir / b10.TSV_REL).exists()
    assert b10._mirror_dirs(play_root) == [], "a failed package wrote a play mirror"


def test_t1_containment_does_not_swallow_the_working_path(healthy_worker, tmp_path):
    """The b004 counter-test: the untouched §7 reference still packages."""
    out_dir = tmp_path / "healthy" / "out"
    play_root = tmp_path / "healthy" / "play"
    report = s6.run_s6(healthy_worker, _CFG, out_dir=out_dir, play_root=play_root)
    assert report["verdict"] == s6.VERDICT_PACKAGED, (
        f"the containment turned a packageable game into {report['verdict']!r}:\n"
        f"{b11._text(report)}"
    )
    assert (out_dir / b10.MANIFEST_REL).is_file()
    assert (out_dir / b10.TSV_REL).is_file()


# --------------------------------------------------------------------------- #
# T2 — the §4 tables carry exactly the four new edges, nothing else moved
# --------------------------------------------------------------------------- #


def _live_transitions_without_new_edges() -> dict:
    """TRANSITIONS with the new destinations removed — today's table.

    `LATER_CONTRACT_EDGES` comes out too (see their own notes): a later
    contract's edges are not this one's rows changing.
    """
    stripped: dict = {}
    for source, dests in orch.TRANSITIONS.items():
        stripped[source] = {
            dest: label
            for dest, label in dests.items()
            if (source, dest) not in NEW_EDGES and (source, dest) not in LATER_CONTRACT_EDGES
        }
    return stripped


def test_t2_the_four_new_edges_are_in_transitions_with_their_labels():
    missing = [edge for edge in NEW_EDGES if edge[1] not in orch.TRANSITIONS.get(edge[0], {})]
    assert not missing, (
        f"TRANSITIONS is missing the new §4 edges {missing} (P-1.2 / P-2.1 / P-2.2 / "
        f"P-3.2b). Live rows:\n{b11._text({str(k): v for k, v in orch.TRANSITIONS.items()})}"
    )
    for (source, dest), (_owner, phrase) in NEW_EDGES.items():
        label = orch.TRANSITIONS[source][dest]
        assert phrase.lower() in str(label).lower(), (
            f"the {source} --> {dest} label must carry {phrase!r} (ambiguity A: the "
            f"phrase, not the full string, is pinned); got {label!r}"
        )


def test_t2_no_other_transitions_row_changed():
    """The real content of T2: today's rows, byte for byte, labels included."""
    live = _live_transitions_without_new_edges()
    assert live == PINNED_TRANSITIONS, (
        "TRANSITIONS moved beyond the four new edges. Left = live minus the new "
        f"edges, right = the hand-pinned copy of today's table.\n"
        f"live:   {b11._text({str(k): v for k, v in live.items()})}\n"
        f"pinned: {b11._text({str(k): v for k, v in PINNED_TRANSITIONS.items()})}"
    )


def test_t2_edge_stage_names_the_owner_of_each_new_edge():
    for edge, (owner, _phrase) in NEW_EDGES.items():
        assert edge in orch.EDGE_STAGE, (
            f"EDGE_STAGE has no owner for the new edge {edge} (P-1.2: the ledger "
            "recovers the stage from (from, to))"
        )
        assert orch.EDGE_STAGE[edge] == owner, (
            f"{edge} must be owned by {owner!r}, got {orch.EDGE_STAGE[edge]!r}"
        )


def test_t2_no_other_edge_stage_row_changed():
    live = {edge: stage for edge, stage in orch.EDGE_STAGE.items()
            if edge not in NEW_EDGES and edge not in LATER_CONTRACT_EDGES}
    assert live == PINNED_EDGE_STAGE, (
        "EDGE_STAGE moved beyond the four new edges.\n"
        f"live:   {b11._text({str(k): v for k, v in live.items()})}\n"
        f"pinned: {b11._text({str(k): v for k, v in PINNED_EDGE_STAGE.items()})}"
    )


def test_t2_stage_failure_routes_gate_s4_and_s6_to_spec_ok():
    for stage, dest in NEW_STAGE_FAILURE.items():
        assert orch.STAGE_FAILURE.get(stage) == dest, (
            f"STAGE_FAILURE[{stage!r}] must be {dest!r} (§3's own routing, which §4 "
            f"lacked and which blocked b004 live); got {orch.STAGE_FAILURE.get(stage)!r}"
        )


def test_t2_no_other_stage_failure_row_changed():
    expected = {**PINNED_STAGE_FAILURE, **NEW_STAGE_FAILURE}
    assert orch.STAGE_FAILURE == expected, (
        "STAGE_FAILURE moved beyond the three new routings (s3_verify in particular "
        "still fails to `spec_ok` — the round-cap kill is a separate routing).\n"
        f"live:   {b11._text(orch.STAGE_FAILURE)}\n"
        f"pinned: {b11._text(expected)}"
    )


def test_t2_next_stage_and_stage_success_are_untouched():
    """Neither table is in P-1..P-3's scope: `played` still runs NO stage."""
    assert {str(k): v for k, v in orch.NEXT_STAGE.items()} == {
        str(k): v for k, v in PINNED_NEXT_STAGE.items()
    }
    assert orch.STAGE_SUCCESS == PINNED_STAGE_SUCCESS


def test_t2_the_state_vocabulary_and_the_caps_are_untouched():
    assert tuple(orch.STATES) == PINNED_STATES
    assert tuple(orch.TERMINAL) == PINNED_TERMINAL
    for name, value in PINNED_CAPS.items():
        assert getattr(orch, name) == value, (
            f"{name} moved: {getattr(orch, name)!r} != {value!r} (the house rule is "
            "that every new knob defaults to today's bytes)"
        )


# --------------------------------------------------------------------------- #
# the orchestrator rig: b11's fakes + a REAL spec.yaml, a REAL idea, and a
# scripted verifier report / gate report
# --------------------------------------------------------------------------- #

SPEC_TEXT = SPEC_FIXTURE.read_text(encoding="utf-8")
SPEC_SLUG = yaml.safe_load(SPEC_TEXT)["game"]["slug"]
BASE_TERMS = tuple(yaml.safe_load(SPEC_TEXT)["game"]["terms"])
IDEA = json.loads(IDEA_FIXTURE.read_text(encoding="utf-8"))

#: the term the blind audit finds undeclared (the contract's own example).
NEW_TERM = "agent.patrol"
#: a declared term the audit calls dead — the residual that forbids path a.
DEAD_TERM = BASE_TERMS[-1]
#: the lever an `undeclared-deception` finding names.
NEW_LEVER = "false tell"

#: the tier table the contract cites as the KILL bar (gen/tiers.py).
KILL_BUDGETS = {"t1": 6, "t2": 8, "t3": 10}

VERIFIER_REPORT_NAMES = ("worker.verifier-report.json", "verifier-report.json")


def _reject_report(*reasons: dict, undeclared_terms=(), dead_terms=(), levers=()) -> dict:
    """A rejecting S2b report in the feed's own shape (h6's rig precedent)."""
    diff = {key: [] for key in s3v.DIFF_KEYS}
    diff["terms_declared"] = list(BASE_TERMS)
    diff["terms_detected_reachable"] = [
        t for t in BASE_TERMS if t not in dead_terms
    ] + list(undeclared_terms)
    diff["undeclared_terms"] = list(undeclared_terms)
    diff["dead_spec_terms"] = list(dead_terms)
    diff["deceptions_detected"] = list(levers)
    diff["undeclared_deceptions"] = list(levers)
    return {
        "verdict": "reject",
        "game_id": SPEC_SLUG,
        "reject_reasons": [dict(reason) for reason in reasons],
        "diff": diff,
    }


def _pass_report() -> dict:
    diff = {key: [] for key in s3v.DIFF_KEYS}
    diff["terms_declared"] = list(BASE_TERMS)
    diff["terms_detected_reachable"] = list(BASE_TERMS)
    return {
        "verdict": "pass",
        "game_id": SPEC_SLUG,
        "reject_reasons": [],
        "diff": diff,
    }


def _undeclared_term_reason(term: str = NEW_TERM) -> dict:
    """Ambiguity F: the term is in the detail, in a `term` key, and in the diff."""
    return {
        "code": s3v.REJECT_UNDECLARED_TERM,
        "detail": (
            f"'{term}' is reachable in the code and witnessed in play, but the spec "
            f"does not declare it (off-intent)"
        ),
        "term": term,
    }


def _dead_term_reason(term: str = DEAD_TERM) -> dict:
    return {
        "code": s3v.REJECT_DEAD_SPEC_TERM,
        "detail": f"spec declares '{term}' but the audit finds it unreachable in play",
        "term": term,
    }


def _is_real_spec(text: str) -> bool:
    """Is this a §11 spec (as opposed to b11's placeholder spec.yaml)?"""
    try:
        parsed = yaml.safe_load(text)
    except Exception:  # noqa: BLE001 — a half-written file is simply "not a spec"
        return False
    game = parsed.get("game") if isinstance(parsed, dict) else None
    return isinstance(game, dict) and isinstance(game.get("terms"), list)


class _SpecRunners(b11._Runners):
    """b11's rig with three politenesses removed.

    1. A REAL `idea.json` (the committed B5 idea, tier overridable) is written
       wherever the rig wrote its placeholder, so the in-process linter has the
       idea_ref cross-check and the TIER the budget guard needs.
    2. A REAL `spec.yaml` (the committed B5 spec) replaces the rig's
       placeholder on every landing that writes one — and an amendment made by
       the PIPELINE is adopted instead of being overwritten. Without this the
       rig would erase the reconciliation it is supposed to witness.
    3. The S2b artifact is planted per verify call from a scripted list, so a
       round can reject and the confirming round can come back clean.

    Every path this rig writes is recorded in `self.planted`, which is how T3
    can require the findings to land in a file the rig did NOT write.
    """

    def __init__(self, journal, cfg, *, outcomes=None, idea=None, spec_text=SPEC_TEXT,
                 verify_reports=()):
        self.idea_payload = dict(idea if idea is not None else IDEA)
        self.spec_text = spec_text
        self.verify_reports = list(verify_reports)
        self.verify_calls = 0
        self.gate_calls = 0
        self.planted: set[Path] = set()
        self.adopted: list[str] = []
        self._spec_now: dict[str, str] = {}
        super().__init__(journal, cfg, outcomes=outcomes)

    # -- bookkeeping -------------------------------------------------------
    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.planted.add(path.resolve())

    def _spec_paths(self, ctx, slug: str) -> list[Path]:
        paths = [directory / "spec.yaml" for directory in self._slot_dirs(ctx, slug)]
        spec_dir = getattr(ctx, "spec_dir", None)
        if spec_dir is not None:
            candidate = Path(spec_dir) / "spec.yaml"
            if candidate not in paths:
                paths.append(candidate)
        return paths

    def _idea_paths(self, ctx, slug: str) -> list[Path]:
        paths = [directory / "idea.json" for directory in self._slot_dirs(ctx, slug)]
        for attr in ("idea_path", "spec_dir"):
            value = getattr(ctx, attr, None)
            if value is None:
                continue
            candidate = Path(value) if attr == "idea_path" else Path(value) / "idea.json"
            if candidate not in paths:
                paths.append(candidate)
        return paths

    # -- the fake itself ---------------------------------------------------
    def _make(self, stage: str):
        inner = super()._make(stage)

        def runner(ctx):
            result = inner(ctx)
            slug = b11._ctx_slug(ctx) or ""
            self._keep_idea(ctx, slug)
            self._keep_spec(ctx, slug)
            if stage == S2B_STAGE:
                self.verify_calls += 1
                self._plant_verifier_report(ctx, slug)
            return result

        return runner

    def _keep_idea(self, ctx, slug: str) -> None:
        body = json.dumps(self.idea_payload, indent=2, sort_keys=True) + "\n"
        for path in self._idea_paths(ctx, slug):
            if path.is_file() and path.read_text(encoding="utf-8") != body:
                self._write(path, body)

    def _keep_spec(self, ctx, slug: str) -> None:
        paths = self._spec_paths(ctx, slug)
        current = self._spec_now.get(slug, self.spec_text)
        for path in paths:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            if text != current and _is_real_spec(text):
                # the PIPELINE rewrote the spec (a reconciliation) — adopt it.
                current = text
                self.adopted.append(text)
        self._spec_now[slug] = current
        for path in paths:
            if path.is_file() and path.read_text(encoding="utf-8") != current:
                self._write(path, current)

    def _plant_verifier_report(self, ctx, slug: str) -> None:
        if not self.verify_reports:
            return
        index = min(self.verify_calls - 1, len(self.verify_reports) - 1)
        body = json.dumps(self.verify_reports[index], indent=2) + "\n"
        for directory in self._slot_dirs(ctx, slug):
            for name in VERIFIER_REPORT_NAMES:
                self._write(directory / name, body)
        spec_dir = getattr(ctx, "spec_dir", None)
        if spec_dir is not None:
            for name in VERIFIER_REPORT_NAMES:
                self._write(Path(spec_dir) / name, body)


#: the visual check T3's gate fails on, and the note that has to travel.
GATE_CHECK_ID = "visual.hue-contrast"
GATE_NOTE = (
    "card row 3: the goal hue equals the background hue at cell_px 4 "
    "(b005-blind-gate-note)"
)
GATE_ROW = {"check_id": GATE_CHECK_ID, "leg": "visual", "status": "fail", "note": GATE_NOTE}


class _GateRunners(_SpecRunners):
    """…and a gate whose failure leaves REAL failing rows on disk.

    The rig writes the gate's two reports where the stage writes them
    (`<worker>.gate/`) and into the slot dir, declares them as artifacts, and
    ALSO hands the rows back in the result under `reject_reasons` (the findings
    feed's own shape, contract Evidence §4) and `findings` (see the DISCLOSURE
    in this module's docstring). What it never does is write the rows into any
    findings file — that is what T3 requires the PIPELINE to do.
    """

    def _make(self, stage: str):
        inner = super()._make(stage)
        if stage != S3_GATE_STAGE:
            return inner

        def runner(ctx):
            result = inner(ctx)
            if result["ok"]:
                return result
            self.gate_calls += 1
            artifacts = self._plant_gate_reports(ctx, b11._ctx_slug(ctx) or "")
            rows = [
                {
                    "code": "gate-visual",
                    "check_id": GATE_CHECK_ID,
                    "detail": GATE_NOTE,
                    "note": GATE_NOTE,
                }
            ]
            return {
                **result,
                "artifacts": {**(result.get("artifacts") or {}), **artifacts},
                "reject_reasons": rows,
                "findings": rows,
            }

        return runner

    def _plant_gate_reports(self, ctx, slug: str) -> dict:
        payload = {
            "verdict": "fail",
            "schema_version": getattr(gate, "SCHEMA_VERSION", "b11"),
            "checks": [dict(GATE_ROW)],
            "failures": [dict(GATE_ROW)],
        }
        body = json.dumps(payload, indent=2) + "\n"
        artifacts: dict[str, str] = {}
        directories = list(self._slot_dirs(ctx, slug))
        spec_dir = getattr(ctx, "spec_dir", None)
        if spec_dir is not None:
            gate_dir = Path(spec_dir) / (orch.WORKER_DIRNAME + gate.GATE_SUFFIX)
            if gate_dir not in directories:
                directories.append(gate_dir)
        for directory in directories:
            for name in (gate.ACCEPTANCE_NAME, gate.ROBUSTNESS_NAME):
                path = directory / name
                self._write(path, body)
                artifacts[f"{directory.name}:{name}"] = str(path)
        return artifacts


# --------------------------------------------------------------------------- #
# helpers — reading the run back
# --------------------------------------------------------------------------- #


def _corpus_dir(cfg) -> Path:
    return Path(orch.CORPUS_ROOT) / orch.batch_config(cfg)["id"]


def _live_spec_dirs(cfg) -> list[Path]:
    corpus = _corpus_dir(cfg)
    if not corpus.is_dir():
        return []
    return sorted(
        path
        for path in corpus.iterdir()
        if path.is_dir() and path.name != orch.KILLED_DIRNAME and (path / "idea.json").is_file()
    )


def _spec_on_disk(cfg) -> dict:
    """The one live spec.yaml the run leaves behind, parsed."""
    dirs = _live_spec_dirs(cfg)
    assert len(dirs) == 1, f"expected exactly one live corpus dir, found {dirs}"
    path = dirs[0] / "spec.yaml"
    assert path.is_file(), f"no spec.yaml under {dirs[0]}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _terms_on_disk(cfg) -> list[str]:
    return list(_spec_on_disk(cfg)["game"]["terms"])


def _deceptions_on_disk(cfg) -> list[str]:
    return list(_spec_on_disk(cfg)["game"]["knobs"]["deceptions"])


def _reasons(cfg, edge=None) -> list[str]:
    return [
        str(line["reason"])
        for line in b11._ledger_lines(cfg)
        if edge is None or (line["from"], line["to"]) == edge
    ]


def _all_reason_text(cfg) -> str:
    return "\n".join(_reasons(cfg))


def _stage_calls(journal, stage: str) -> list:
    return [call for call in journal.calls if call.stage == stage]


def _readable_files(cfg) -> list[Path]:
    roots = [Path(orch.batch_dir(cfg)), _corpus_dir(cfg)]
    found: dict[Path, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in (".json", ".yaml", ".yml", ".md", ".txt"):
                found[path.resolve()] = path
    return list(found.values())


@dataclass(frozen=True)
class _Run:
    """One driven batch: the cfg it ran on, the rig, and what came back."""

    cfg: dict
    journal: object
    runners: object
    report: dict


def _one_slot(report) -> dict:
    slots = report["slots"]
    assert len(slots) == 1, f"these scenarios run one-slot batches; got {len(slots)}"
    return slots[0]


def _armed_cfg(make_cfg, batch_id: str, *, round_cap=None, reject_cap=None, tier=None,
               review=None, max_attrition=None) -> tuple[dict, dict]:
    """A size-1 batch cfg, armed only where a scenario needs arming."""
    cfg, _path = make_cfg(batch_id, max_attrition=max_attrition or 1.0)
    verifier = dict(cfg.get("verifier") or {})
    if reject_cap is not None:
        verifier["reject_cap"] = reject_cap
    if round_cap is not None:
        verifier["round_cap"] = round_cap
    cfg["verifier"] = verifier
    if review is not None:
        cfg["review"] = review
    # ambiguity E: the KILL bar, armed in config with the same numbers
    # `gen/tiers.py` carries, so either reading of "the tier's KILL budget"
    # fires identically.
    cfg["tiers"] = {"term_budget": dict(KILL_BUDGETS), "term_budget_action": "kill"}
    idea = dict(IDEA)
    if tier is not None:
        idea["tier"] = tier
    return cfg, idea


# --------------------------------------------------------------------------- #
# T3 — the gate-fail edge, the findings feed, the loop guard
# --------------------------------------------------------------------------- #


def test_t3_a_gate_fail_routes_the_slot_back_to_spec_ok(make_cfg):
    """P-2.1: `("verified", "spec_ok")`, owner s3_gate."""
    cfg, idea = _armed_cfg(make_cfg, "b005-gate-route", tier="t2")
    journal = b11._Journal()
    runners = _GateRunners(
        journal,
        cfg,
        outcomes={"verified": b11._Outcome("spec_ok", "gate fail: visual check", times=1)},
        idea=idea,
        verify_reports=[_pass_report()],
    )
    orch.run_batch(cfg, runners=runners)

    spine = b11._spine(b11._ledger_lines(cfg))
    assert ("verified", "spec_ok") in spine, (
        "a failing gate must travel §3's own routing back to `spec_ok` instead of "
        f"blocking the slot. Spine: {spine}"
    )
    assert runners.gate_calls >= 1
    # …and the slot really re-implemented: S2 ran again after the gate fail.
    assert len(_stage_calls(journal, S2_STAGE)) >= 2, (
        f"S2 was invoked {len(_stage_calls(journal, S2_STAGE))}×; a gate fail that "
        "routes to `spec_ok` must be re-implemented"
    )


def test_t3_the_gate_fail_ledger_reason_names_the_failure_and_its_count(make_cfg):
    """P-2.3: 'Document the counting in the ledger reason string'."""
    cfg, idea = _armed_cfg(make_cfg, "b005-gate-reason", tier="t2")
    journal = b11._Journal()
    runners = _GateRunners(
        journal,
        cfg,
        outcomes={"verified": b11._Outcome("spec_ok", "gate fail: visual check", times=1)},
        idea=idea,
        verify_reports=[_pass_report()],
    )
    orch.run_batch(cfg, runners=runners)

    reasons = _reasons(cfg, ("verified", "spec_ok"))
    assert reasons, f"no ledger line for the gate-fail edge:\n{_all_reason_text(cfg)}"
    reason = reasons[0]
    assert "gate fail" in reason.lower(), (
        f"the gate-fail reason must say so (contract's own string, "
        f"'gate fail 1/2 -> re-implement'); got {reason!r}"
    )
    cap = orch._reject_cap(cfg)
    assert f"1/{cap}" in reason, (
        f"the reason must document the loop-guard count as `1/{cap}` (P-2.3: gate "
        f"routings COUNT toward the verifier-reject ladder); got {reason!r}"
    )


def test_t3_the_failing_check_reaches_the_next_s2_session(make_cfg):
    """P-2.1: the gate's failing rows feed the next S2 via the EXISTING feed.

    The rig plants its rows ONLY in the gate's own reports; a hit there proves
    nothing. The assertion is that the id and the note are readable in the
    findings feed AT THE MOMENT the next S2 session runs.

    LEAD ADJUDICATION (2026-09-29): the blind draft searched all files AFTER
    the batch — but the pipeline retires a stage's findings the moment that
    stage passes again (retire-on-pass, the anti-stale-findings lifecycle), so
    once the retry gate goes green the file is gone by design. The feed's
    promise is what the NEXT S2 session sees, not what survives the batch, so
    the pin snapshots `ctx.stage_findings_path` inside the S2 runner itself.
    """
    cfg, idea = _armed_cfg(make_cfg, "b005-gate-feed", tier="t2")
    journal = b11._Journal()

    class _SnappingRunners(_GateRunners):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.s2_findings: list[str] = []

        def _make(self, stage: str):
            inner = super()._make(stage)
            if stage != S2_STAGE:
                return inner

            def runner(ctx):
                path = getattr(ctx, "stage_findings_path", None)
                if path is not None and Path(path).is_file():
                    self.s2_findings.append(Path(path).read_text(encoding="utf-8"))
                return inner(ctx)

            return runner

    runners = _SnappingRunners(
        journal,
        cfg,
        outcomes={"verified": b11._Outcome("spec_ok", "gate fail: visual check", times=1)},
        idea=idea,
        verify_reports=[_pass_report()],
    )
    orch.run_batch(cfg, runners=runners)

    fed = [text for text in runners.s2_findings
           if GATE_CHECK_ID in text and "b005-blind-gate-note" in text]
    assert fed, (
        "no S2 invocation could read the gate's failing check id + note from "
        f"the findings feed (P-2.1); snapshots taken: {len(runners.s2_findings)} "
        f"-> {runners.s2_findings!r}"
    )


def test_t3_the_loop_guard_escalates_the_second_gate_fail(make_cfg):
    """P-2.3: ×reject_cap -> respec, so implement<->gate cannot loop."""
    cfg, idea = _armed_cfg(make_cfg, "b005-gate-loop", tier="t2", reject_cap=2)
    journal = b11._Journal()
    runners = _GateRunners(
        journal,
        cfg,
        outcomes={"verified": b11._Outcome("spec_ok", "gate fail: visual check", times=2)},
        idea=idea,
        verify_reports=[_pass_report()],
    )
    report = orch.run_batch(cfg, runners=runners)

    reasons = _reasons(cfg, ("verified", "spec_ok"))
    assert len(reasons) == 2, (
        f"expected exactly two gate fails before the ladder fires, got {reasons}"
    )
    assert "1/2" in reasons[0] and "2/2" in reasons[1], (
        f"the loop-guard count must advance across the two fails: {reasons}"
    )
    # The escalation's LANDING is not frozen (b11 ambiguity F): it shows up as a
    # respec, as escalation wording in the reason, or as a loud block — any of
    # the three proves the ladder fired instead of looping.
    spine = b11._spine(b11._ledger_lines(cfg))
    blocked = report.get("blocked") or []
    escalated = (
        ("ideated", "respec") in spine
        or any(word in reasons[1].lower() for word in ("respec", "escalat"))
        or bool(blocked)
    )
    assert escalated, (
        "at the reject cap a gate fail must escalate (respec / escalation reason / a "
        f"loud block), not loop. Spine: {spine}\nReasons: {reasons}\nreport.blocked: "
        f"{blocked}"
    )
    assert runners.gate_calls <= 2, (
        f"the gate ran {runners.gate_calls}× — the ladder did not bound the loop"
    )


# --------------------------------------------------------------------------- #
# T4 — `verifier.round_cap` validation
# --------------------------------------------------------------------------- #


def _round_cap_reader():
    """The `round_cap` reader, by name then by search (ambiguity H)."""
    for name in ("_round_cap", "round_cap", "_verifier_round_cap"):
        value = getattr(orch, name, None)
        if callable(value):
            return value
    candidates = sorted(
        name for name, value in vars(orch).items() if callable(value) and "round" in name.lower()
    )
    raise AssertionError(
        "gen/orchestrator.py exposes no `round_cap` reader (P-3.2: 'read beside "
        f"`_reject_cap`, same style'). Callables naming 'round': {candidates}"
    )


@pytest.mark.parametrize(
    "cfg",
    [{}, {"verifier": {}}, {"verifier": {"reject_cap": 2}}],
    ids=["no-verifier-block", "empty-verifier-block", "reject_cap-only"],
)
def test_t4_round_cap_absent_is_none(cfg):
    """'absent = None = today's unlimited behavior' — the house rule."""
    assert _round_cap_reader()(cfg) is None


@pytest.mark.parametrize("value", [2, 3, 4, 10])
def test_t4_round_cap_accepts_an_int_of_two_or_more(value):
    assert _round_cap_reader()({"verifier": {"round_cap": value}}) == value


@pytest.mark.parametrize(
    "value",
    [1, 0, -1, "x", "2", True, False, 2.0, None, [], {}],
    ids=["one", "zero", "negative", "word", "numeric-string", "true", "false",
         "float", "null", "list", "dict"],
)
def test_t4_round_cap_refuses_everything_that_is_not_an_int_ge_two(value):
    """'else int >= 2, loud ValueError otherwise' — invalid values are LOUD."""
    with pytest.raises(ValueError):
        _round_cap_reader()({"verifier": {"round_cap": value}})


def test_t4_reject_cap_still_reads_its_own_key():
    """The neighbour the new reader is styled on, unchanged."""
    assert orch._reject_cap({}) == orch.VERIFIER_REJECT_CAP_ESCALATE
    assert orch._reject_cap({"verifier": {"reject_cap": 5}}) == 5


# --------------------------------------------------------------------------- #
# T5 — mechanical reconciliation, happy path
# --------------------------------------------------------------------------- #


def _reconciliation_run(make_cfg, batch_id: str, *, tier: str, reports: list, rejects: int,
                        max_attrition: float = 1.0):
    """Drive one slot to the round cap on a scripted verifier script."""
    cfg, idea = _armed_cfg(
        make_cfg, batch_id, round_cap=2, reject_cap=5, tier=tier, max_attrition=max_attrition
    )
    journal = b11._Journal()
    runners = _SpecRunners(
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
    return _Run(cfg, journal, runners, report)


def test_t5_a_declaration_only_residual_is_reconciled_into_the_spec(make_cfg):
    """P-3.2a: the pipeline writes its own stage artifact — LOUD."""
    reject = _reject_report(_undeclared_term_reason(), undeclared_terms=[NEW_TERM])
    run = _reconciliation_run(
        make_cfg, "b005-reconcile", tier="t2",
        reports=[reject, reject, _pass_report()], rejects=2,
    )

    terms = _terms_on_disk(run.cfg)
    assert NEW_TERM in terms, (
        f"at the round cap a declaration-side residual must be reconciled into "
        f"`game.terms`; the spec still declares {terms}"
    )
    assert list(BASE_TERMS) == terms[: len(BASE_TERMS)], (
        f"reconciliation APPENDS; the authored terms moved: {terms}"
    )


def test_t5_the_reconciliation_is_announced_in_the_ledger_and_the_report(make_cfg):
    reject = _reject_report(_undeclared_term_reason(), undeclared_terms=[NEW_TERM])
    run = _reconciliation_run(
        make_cfg, "b005-reconcile-loud", tier="t2",
        reports=[reject, reject, _pass_report()], rejects=2,
    )

    reasons = _all_reason_text(run.cfg)
    assert "reconcil" in reasons.lower(), (
        f"no ledger line announces the reconciliation (ambiguity C: the EDGE is not "
        f"pinned, the announcement is). Ledger reasons:\n{reasons}"
    )
    haystack = reasons + b11._text(run.report)
    assert NEW_TERM in haystack, (
        f"the reconciliation never names the term it added ('declaration reconciled "
        f"to audit: +{NEW_TERM}'):\n{haystack[:3000]}"
    )


def test_t5_the_slot_re_enters_the_audit_once_and_the_clean_round_verifies(make_cfg):
    """P-3.2a: ONE confirming round; a clean audit lands `verified`."""
    reject = _reject_report(_undeclared_term_reason(), undeclared_terms=[NEW_TERM])
    run = _reconciliation_run(
        make_cfg, "b005-reconcile-confirm", tier="t2",
        reports=[reject, reject, _pass_report()], rejects=2,
    )

    assert run.runners.verify_calls == 3, (
        "the audit must run exactly three times — two rejecting rounds and ONE "
        f"confirming round after the reconciliation; it ran {run.runners.verify_calls}×"
    )
    spine = b11._spine(b11._ledger_lines(run.cfg))
    assert ("implemented", "verified") in spine, (
        f"the confirming round came back clean but the slot never verified: {spine}"
    )
    assert ("implemented", "dead") not in spine, (
        f"a reconciled slot that confirms clean must NOT die: {spine}"
    )
    assert _one_slot(run.report)["state"] != "dead"


def test_t5_a_declaration_side_deception_residual_reconciles_into_the_knobs(make_cfg):
    """P-3.2a's other half: levers land in `game.knobs.deceptions`."""
    reject = _reject_report(
        {
            "code": s3v.REJECT_UNDECLARED_DECEPTION,
            "detail": f"the audit detected the '{NEW_LEVER}' lever; the spec declares []",
            "lever": NEW_LEVER,
        },
        levers=[NEW_LEVER],
    )
    run = _reconciliation_run(
        make_cfg, "b005-reconcile-lever", tier="t2",
        reports=[reject, reject, _pass_report()], rejects=2,
    )

    declared = _deceptions_on_disk(run.cfg)
    assert any(NEW_LEVER in str(entry) for entry in declared), (
        f"the lever must be declared so substring containment holds (the contract's "
        f"own spelling: '<lever>: reconciled from the blind audit (round_cap)'); "
        f"deceptions on disk: {declared}"
    )


# --------------------------------------------------------------------------- #
# T6 — the reconciliation guards, one test each
# --------------------------------------------------------------------------- #


# PIN UPDATE, 2026-09-29 (contract P-A.4), deliberate and justified. THE OPERATOR'S
# RULING, on the record, verbatim: "We should never kill. Even if it is not
# satisfied eventually let's not kill." Every would-kill outcome of the
# round-cap verdict now travels `("implemented", "parked")` with a "round-cap
# park" reason and lands the slot in `parked` — terminal, artifacts intact,
# outside the attrition ratio. The assertions are otherwise the ones this helper
# has always made; only the destination moved.
def _assert_round_cap_park(cfg, report, *, why: str):
    spine = b11._spine(b11._ledger_lines(cfg))
    assert ("implemented", "parked") in spine, (
        f"{why}: the slot must travel the `implemented --> parked` edge "
        f"(P-A.4, owner s3_verify). Spine: {spine}"
    )
    assert ("implemented", "dead") not in spine, (
        f"{why}: the verify lane must never kill again (operator 2026-09-29). Spine: {spine}"
    )
    reasons = _reasons(cfg, ("implemented", "parked"))
    assert reasons and "round-cap park" in reasons[0].lower(), (
        f"{why}: the park reason must be 'round-cap park: <codes>'; got {reasons}"
    )
    assert _one_slot(report)["state"] == "parked", _one_slot(report)


def test_t6_an_over_budget_reconciliation_promotes_the_tier(make_cfg):
    """PIN UPDATE, 2026-09-29 (contract P-A.3), deliberate and justified.

    This scenario used to pin a KILL: tier t1 (bar 6) with the authored six, so
    the seventh term could not be added. P-A.3 changes what that means — "When
    the amended term count exceeds the slot's tier budget but fits the NEXT tier
    up (t1->t2, t2->t3; t3 is the ceiling), promote" — because a game that
    outgrew its tier is a tiering fact, not a defect. Seven terms fit t2's bar
    of 8, so the slot is promoted, the amendment IS written, and the confirming
    round verifies. The refusal this test used to make survives at the CEILING
    (over t3 -> parked), which is the blind lane's pin.
    """
    reject = _reject_report(_undeclared_term_reason(), undeclared_terms=[NEW_TERM])
    run = _reconciliation_run(
        make_cfg, "b005-overbudget", tier="t1",
        reports=[reject, reject, _pass_report()], rejects=2,
    )
    assert len(BASE_TERMS) == KILL_BUDGETS["t1"], (
        f"fixture drift: the t1 bar is {KILL_BUDGETS['t1']} and the fixture spec "
        f"declares {len(BASE_TERMS)} terms — the over-budget premise is gone"
    )
    assert NEW_TERM in _terms_on_disk(run.cfg), (
        "the amendment that earned the promotion must be written: "
        f"{_terms_on_disk(run.cfg)}"
    )
    assert _spec_on_disk(run.cfg)["game"].get("tier") == "t2", (
        "the promoted tier is recorded in spec.yaml (idea.json is NOT touched — "
        f"ideas are immutable): {_spec_on_disk(run.cfg)['game'].get('tier')!r}"
    )
    assert json.loads(
        (_live_spec_dirs(run.cfg)[0] / "idea.json").read_text(encoding="utf-8")
    )["tier"] == "t1", "P-A.3: idea.json's tier is immutable and must still read t1"
    reasons = _all_reason_text(run.cfg)
    assert "tier promoted t1->t2" in reasons, (
        f"the ledger must carry the promotion line ('tier promoted t1->t2: 7 declared "
        f"terms vs budget 6'):\n{reasons}"
    )
    spine = b11._spine(b11._ledger_lines(run.cfg))
    assert ("implemented", "dead") not in spine and ("implemented", "parked") not in spine, (
        f"a promotable over-budget amendment neither kills nor parks: {spine}"
    )
    assert _one_slot(run.report)["state"] != "parked"


def test_t6_a_non_declaration_residual_parks_the_slot(make_cfg):
    """PIN UPDATE, 2026-09-29 (contracts P-A.2 + P-A.4), deliberate and justified.

    Two changes, both the contract's. (1) The residual this scenario used to
    carry was `dead-spec-term`, which P-A.2 makes RECONCILABLE in the
    subtractive direction — the spec withdraws a declaration the audit cannot
    reach — so it no longer forbids anything. The residual here is therefore
    `solver-quality`, which the contract lists among the ones "no declaration
    can answer". (2) The outcome is a PARK, not a death, on OPERATOR RULING, on
    the record, verbatim: "We should never kill. Even if it is not satisfied
    eventually let's not kill."
    """
    reject = _reject_report(
        _undeclared_term_reason(),
        {
            "code": s3v.REJECT_SOLVER_QUALITY,
            "detail": "solver.wins_every_level failed: the solver loses level 3",
            "check_id": "solver.wins_every_level",
        },
        undeclared_terms=[NEW_TERM],
    )
    run = _reconciliation_run(
        make_cfg, "b005-solverquality", tier="t2",
        reports=[reject, reject, _pass_report()], rejects=2,
    )
    _assert_round_cap_park(run.cfg, run.report, why="a solver-quality residual at the cap")
    assert s3v.REJECT_SOLVER_QUALITY in _reasons(run.cfg, ("implemented", "parked"))[0], (
        "the park reason must carry the residual CODES: "
        f"{_reasons(run.cfg, ('implemented', 'parked'))}"
    )
    assert NEW_TERM not in _terms_on_disk(run.cfg), (
        f"nothing is reconciled on path b: {_terms_on_disk(run.cfg)}"
    )


def test_t6_a_dead_spec_term_residual_reconciles_in_the_subtractive_direction(make_cfg):
    """The other half of the change above (contract P-A.2), pinned where the
    scenario it replaced used to live: a `dead-spec-term` residual withdraws the
    declaration instead of forbidding the reconciliation. The label is made
    true; the finding is not waived.
    """
    reject = _reject_report(
        _dead_term_reason(),
        dead_terms=[DEAD_TERM],
    )
    run = _reconciliation_run(
        make_cfg, "b005-deadterm", tier="t2",
        reports=[reject, reject, _pass_report()], rejects=2,
    )
    terms = _terms_on_disk(run.cfg)
    assert DEAD_TERM not in terms, (
        f"the unreachable declaration must be WITHDRAWN from game.terms: {terms}"
    )
    for level in _spec_on_disk(run.cfg)["game"]["levels"]:
        assert DEAD_TERM not in (level.get("terms_introduced") or []), (
            "§11 enforces `terms_introduced ⊆ game.terms`, so the withdrawal must "
            f"leave the curriculum too: {level}"
        )
    assert f"-{DEAD_TERM}" in _all_reason_text(run.cfg), (
        f"a drop is announced with a leading '-':\n{_all_reason_text(run.cfg)}"
    )
    spine = b11._spine(b11._ledger_lines(run.cfg))
    assert ("implemented", "verified") in spine, (
        f"the confirming round came back clean but the slot never verified: {spine}"
    )


def test_t6_a_reconciliation_that_rejects_again_parks_the_slot(make_cfg):
    """P-3.2a: 'if it rejects again -> path b'. The confirming round is final.

    PIN UPDATE, 2026-09-29 (contract P-A.4): path b is a PARK now, on THE OPERATOR'S
    RULING, on the record, verbatim: "We should never kill. Even if it is not
    satisfied eventually let's not kill." The finality is unchanged — the audit
    rejected AFTER the declarations were reconciled, and no further declaration
    can answer that — only the outcome is.
    """
    reject = _reject_report(_undeclared_term_reason(), undeclared_terms=[NEW_TERM])
    run = _reconciliation_run(
        make_cfg, "b005-postreject", tier="t2",
        reports=[reject, reject, reject], rejects=3,
    )
    _assert_round_cap_park(run.cfg, run.report, why="the confirming round rejected again")
    assert run.runners.verify_calls == 3, (
        "the confirming round is ONE round: the audit must not be re-run past it; "
        f"it ran {run.runners.verify_calls}×"
    )


# --------------------------------------------------------------------------- #
# T7 — `review.auto_accept`
# --------------------------------------------------------------------------- #


def _played_run(make_cfg, batch_id: str, *, review=None):
    cfg, idea = _armed_cfg(make_cfg, batch_id, tier="t2", review=review)
    journal = b11._Journal()
    runners = _SpecRunners(journal, cfg, idea=idea, verify_reports=[_pass_report()])
    report = orch.run_batch(cfg, runners=runners)
    return _Run(cfg, journal, runners, report)


@pytest.mark.parametrize(
    "review", [None, {"auto_accept": False}], ids=["absent", "false"]
)
def test_t7_without_auto_accept_the_played_stop_is_todays_bytes(make_cfg, capsys, review):
    """P-3.3: 'key absent/false = today's human stop'."""
    run = _played_run(make_cfg, "b005-stop", review=review)
    captured = capsys.readouterr()

    table = b11._table(run.cfg)
    assert set(table.values()) == {"played"}, (
        f"the run must still stop at the human checkpoint: {table}"
    )
    spine = b11._spine(b11._ledger_lines(run.cfg))
    assert ("played", "reviewed") not in spine, f"the slot auto-travelled anyway: {spine}"
    assert not _stage_calls(run.journal, S6_STAGE), "s6 ran without a review decision"
    haystack = captured.out + captured.err + b11._text(run.report)
    assert "--review" in haystack, (
        "today's played stop names the `--review` command (b11's pin); the stop text "
        f"is now:\n{haystack[:2000]}"
    )


def test_t7_auto_accept_travels_played_to_reviewed_and_packages_in_the_same_run(make_cfg):
    """P-3.3: no STOPPED (review), no human edge, s6 in the SAME run."""
    run = _played_run(
        make_cfg, "b005-autoaccept", review={"auto_accept": True}
    )
    spine = b11._spine(b11._ledger_lines(run.cfg))
    assert ("played", "reviewed") in spine, (
        f"`review.auto_accept: true` must travel played --> reviewed by itself: {spine}"
    )
    assert ("reviewed", "packaged") in spine, (
        f"…and continue to s6 in the same run (no second run_batch leg): {spine}"
    )
    assert _stage_calls(run.journal, S6_STAGE), "s6 was never invoked"
    assert b11._table(run.cfg) == {next(iter(b11._table(run.cfg))): "packaged"}


def test_t7_the_auto_accept_ledger_reason_names_the_knob(make_cfg):
    run = _played_run(
        make_cfg, "b005-autoaccept-reason", review={"auto_accept": True}
    )
    reasons = _reasons(run.cfg, ("played", "reviewed"))
    assert reasons, "no ledger line for the auto-accepted review edge"
    reason = reasons[0].lower()
    assert "auto-accept" in reason and "review.auto_accept" in reasons[0], (
        "the contract's own reason string is 'auto-accept (review.auto_accept)'; got "
        f"{reasons[0]!r}"
    )


def test_t7_the_batch_report_lists_the_auto_accepted_slugs(make_cfg):
    """P-3.3: 'The batch report carries an `auto_accepted: [slugs]` block.'"""
    run = _played_run(
        make_cfg, "b005-autoaccept-report", review={"auto_accept": True}
    )
    slug = _one_slot(run.report)["slug"]
    blocks = [
        node["auto_accepted"]
        for node in b11._walk(run.report)
        if isinstance(node, dict) and "auto_accepted" in node
    ]
    assert blocks, (
        f"the batch report carries no `auto_accepted` block (ambiguity G: looked up "
        f"by key anywhere in the report):\n{b11._text(run.report)[:3000]}"
    )
    assert any(slug in list(block or []) for block in blocks), (
        f"`auto_accepted` does not list the slug {slug!r}: {blocks}"
    )


def test_t7_a_non_bool_auto_accept_is_a_loud_error(make_cfg):
    """'true, validated bool' — the house rule: invalid values are loud."""
    cfg, idea = _armed_cfg(make_cfg, "b005-autoaccept-bad", tier="t2",
                           review={"auto_accept": "yes"})
    journal = b11._Journal()
    runners = _SpecRunners(journal, cfg, idea=idea, verify_reports=[_pass_report()])
    with pytest.raises(ValueError):
        orch.run_batch(cfg, runners=runners)


# --------------------------------------------------------------------------- #
# T8 — byte-identity for an unconfigured batch
# --------------------------------------------------------------------------- #


def test_t8_an_unconfigured_cfg_routes_a_verifier_reject_exactly_as_today(make_cfg):
    """No round_cap, no review block: today's ladder, pinned against the live
    constants — reject -> spec_ok, ×VERIFIER_REJECT_CAP_ESCALATE -> respec."""
    cap = orch.VERIFIER_REJECT_CAP_ESCALATE
    cfg, _path = make_cfg("b005-byte-identity", max_attrition=1.0)
    assert "round_cap" not in (cfg.get("verifier") or {}), "the scenario's premise"
    assert "review" not in cfg, "the scenario's premise"
    assert orch.STAGE_FAILURE["s3_verify"] == "spec_ok", "today's verifier routing"

    reject = _reject_report(_undeclared_term_reason(), undeclared_terms=[NEW_TERM])
    journal = b11._Journal()
    runners = _SpecRunners(
        journal,
        cfg,
        outcomes={
            "implemented": b11._Outcome(
                "spec_ok", f"verifier reject: {s3v.REJECT_UNDECLARED_TERM}", times=cap
            )
        },
        idea=dict(IDEA),
        verify_reports=[reject, reject, _pass_report()],
    )
    orch.run_batch(cfg, runners=runners)

    rejects = _reasons(cfg, ("implemented", "spec_ok"))
    assert len(rejects) == cap, (
        f"an unconfigured batch must still take {cap} rejects before escalating: {rejects}"
    )
    assert rejects[0] != rejects[-1] and any(
        word in rejects[-1].lower() for word in ("respec", "escalat")
    ), f"at the cap the reason routes respec (b11's pin): {rejects}"

    spine = b11._spine(b11._ledger_lines(cfg))
    assert ("implemented", "dead") not in spine, (
        f"no round_cap is armed, so nothing may round-cap-kill: {spine}"
    )


def test_t8_an_unconfigured_cfg_never_touches_the_declaration(make_cfg):
    """The autonomy knobs default to today's bytes: no spec is amended."""
    cap = orch.VERIFIER_REJECT_CAP_ESCALATE
    cfg, _path = make_cfg("b005-byte-identity-spec", max_attrition=1.0)
    reject = _reject_report(_undeclared_term_reason(), undeclared_terms=[NEW_TERM])
    journal = b11._Journal()
    runners = _SpecRunners(
        journal,
        cfg,
        outcomes={
            "implemented": b11._Outcome(
                "spec_ok", f"verifier reject: {s3v.REJECT_UNDECLARED_TERM}", times=cap
            )
        },
        idea=dict(IDEA),
        verify_reports=[reject, reject, _pass_report()],
    )
    orch.run_batch(cfg, runners=runners)

    assert _terms_on_disk(cfg) == list(BASE_TERMS), (
        "with no `verifier.round_cap` the declaration must never be reconciled: "
        f"{_terms_on_disk(cfg)}"
    )
    assert "reconcil" not in _all_reason_text(cfg).lower(), (
        f"an unconfigured batch announced a reconciliation:\n{_all_reason_text(cfg)}"
    )
    assert not runners.adopted, (
        f"something rewrote spec.yaml on an unconfigured batch: {runners.adopted}"
    )


# --------------------------------------------------------------------------- #
# grounding pins — the constants the scenarios above are written against
# --------------------------------------------------------------------------- #


def test_the_reject_codes_this_file_routes_on_are_the_frozen_spellings():
    """P-3.2's condition is a literal set of code strings."""
    assert s3v.REJECT_UNDECLARED_TERM == "undeclared-term"
    assert s3v.REJECT_UNDECLARED_DECEPTION == "undeclared-deception"
    assert s3v.REJECT_DEAD_SPEC_TERM == "dead-spec-term"
    assert s3v.REJECT_UNREACHABLE_DECLARED == "unreachable-declared-mechanic"
    assert s3v.REJECT_SOLVER_QUALITY == "solver-quality"


def test_the_tier_kill_budgets_this_file_arms_are_the_signed_table():
    assert tiers.DEFAULT_TERM_BUDGETS == KILL_BUDGETS


def test_the_spec_fixture_still_carries_the_premise_of_t5_and_t6():
    game = yaml.safe_load(SPEC_TEXT)["game"]
    assert NEW_TERM not in game["terms"], "T5's term must start UNdeclared"
    assert game["knobs"]["deceptions"] == [], "T5's lever must start UNdeclared"
    assert IDEA["id"] == game["idea_ref"], "the idea/spec cross-check the linter makes"
    assert len(game["terms"]) == KILL_BUDGETS["t1"], (
        "T6's over-budget premise: the fixture sits exactly on the t1 bar"
    )


def test_the_b004_crash_pattern_this_file_copies_is_still_the_precedent():
    """T1 is the s3 containment pattern applied to s6 — pin the precedent."""
    assert hasattr(b004, "CRASHING_SOLVER")
    assert b004.TOY.is_dir()
