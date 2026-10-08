"""IMPLEMENTER's suite for frozen contract E-2 — ladder sanity.

Run: .venv/bin/python -m pytest gen/tests/test_e2_ladder.py -q

The blind lane for this contract is `gen/tests/test_v2_ladder.py` and is NOT
this file: nothing here was written with it in view, and nothing here may be
read as covering it.

WHAT E-2 CLOSED, and every group below pins one of the three:

  §1  RECONCILIATION MEMORY — g20261001-5 reconciled `+manip.terraform` at
      ledger line 12 and `-manip.terraform` at line 14, one round later, on
      game bytes that never moved (`hashes.game` 6eca8f66 both times) and with
      the spec hash returning to the byte-identical bd7b492e it had left.
      Groups C (unit), D (a driven batch) and H (the real ledger, replayed).
  §2  TERMINAL STAGE-FAIL ROUTES — the same ledger's lines 7, 10, 21 and 28:
      "gate fail 1/1", "gate fail 2/1", "package fail 3/1", "package fail 4/1",
      three of them past `verifier.reject_cap: 1`, with no terminal but the
      64-step livelock guard's CRASH. Groups A (the tables) and E (driven).
  §3  RESPEC FEASIBILITY — the same ledger's line 7 escalated a re-spec that
      left the spec hash byte-identical: the session was paid for without
      reading the findings it answered. Groups F and G.

HERMETIC. `batch_home` + the b005 rig, both borrowed through their owner's
alias (the `test_v2_leniency` precedent: borrowed, never copied, never
modified). No network, no driver, no agent session, no subprocess, and nothing
written under the repo's `out/` or `games/` — group H reads one real ledger
READ-ONLY and copies it to tmp before touching it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from gen import cli
from gen import orchestrator as orch
from gen import s3_verify as s3v
from gen import s3_visual as s3vis

# The rigs. `_SpecRunners` keeps a REAL §11 spec and a REAL idea on disk and
# plants a scripted S2b report per verify call; `_GateRunners` adds a gate whose
# failure leaves real failing rows behind. Both are b005's, used as-is.
from gen.tests import test_b005_autonomy as b005
from gen.tests import test_b11_pipeline as b11

REPO_ROOT = Path(__file__).resolve().parents[2]
#: the measured ledger the whole contract is written from, READ-ONLY.
#: LEAD REPOINT 2026-10-06: the live batch legitimately CONTINUED (revival #1,
#: 2026-10-05 — resumed, S6 passed 5/5, packaged at line 37), so the evidence
#: this file measures is frozen as the byte-exact 28-line prefix of the live
#: ledger at E-2's freeze date. A live out/ path can never serve as a fixture
#: on a pipeline whose whole point is that batches resume.
G5_LEDGER = (
    REPO_ROOT / "gen" / "tests" / "fixtures" / "g20261001-5-ledger-at-e2-freeze.jsonl"
)

_no_network_no_agent = b11._no_network_no_agent   # autouse: no urlopen, no driver
batch_home = b11.batch_home
make_cfg = b11.make_cfg

#: contract E-2 §1's own exhibit, verbatim from g20261001-5's lines 12 and 14.
CHURN_TERM = "manip.terraform"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _line(frm, to, reason, *, spec="s", game="g"):
    """One ledger-shaped dict — enough for the history readers under test."""
    return {"slug": "x", "from": frm, "to": to, "reason": reason,
            "hashes": {"spec": spec, "game": game, "stage_input": "i"},
            "cost": None, "ts": "2026-10-05T00:00:00+00:00"}


def _armed(make_cfg_fixture, batch_id, *, reject_cap=None, round_cap=None, tier="t2",
           stage_fail_park=None, respec_feasibility=None, reconcile_early=None,
           review=None):
    """b005's `_armed_cfg` plus contract E-2's two orchestrator knobs."""
    cfg, idea = b005._armed_cfg(make_cfg_fixture, batch_id, reject_cap=reject_cap,
                                round_cap=round_cap, tier=tier, review=review)
    if reconcile_early is not None:
        cfg["verifier"] = {**cfg["verifier"], "reconcile_early": reconcile_early}
    orchestrator = dict(cfg.get("orchestrator") or {})
    if stage_fail_park is not None:
        orchestrator["stage_fail_park"] = stage_fail_park
    if respec_feasibility is not None:
        orchestrator["respec_feasibility"] = respec_feasibility
    cfg["orchestrator"] = orchestrator
    return cfg, idea


def _spine(cfg):
    return b11._spine(b11._ledger_lines(cfg))


def _edges_into_parked(table):
    return {src for src, dst in table if dst == "parked"}


# --------------------------------------------------------------------------- #
# A — the state tables and every reader of them (§2, and the lead's sweep)
# --------------------------------------------------------------------------- #

#: the four edges E-2 adds, with the stage that owns each and the phrase its §4
#: label must carry.
E2_EDGES = {
    ("verified", "parked"): ("s3_gate", "park"),
    ("gated", "parked"): ("s4_baselines", "park"),
    ("reviewed", "parked"): ("s6_package", "park"),
    ("spec_ok", "parked"): ("s1_spec", "park"),
}


@pytest.mark.parametrize("edge", sorted(E2_EDGES))
def test_a1_each_new_edge_is_legal_and_labelled(edge):
    src, dst = edge
    assert orch.legal_transition(src, dst), f"§4 draws no {src} --> {dst}"
    label = orch.assert_transition(src, dst)
    assert E2_EDGES[edge][1] in label.lower(), (
        f"the {src} --> {dst} label must say it is a park; got {label!r}"
    )


@pytest.mark.parametrize("edge", sorted(E2_EDGES))
def test_a2_each_new_edge_has_an_owning_stage(edge):
    """`_restage` and `_cost_table` index EDGE_STAGE DIRECTLY — a missing row is
    a KeyError on the next resume, not a missing label."""
    assert edge in orch.EDGE_STAGE, f"EDGE_STAGE has no owner for {edge}"
    assert orch.EDGE_STAGE[edge] == E2_EDGES[edge][0]


def test_a3_parked_is_still_terminal_and_runs_nothing():
    # PIN UPDATE, 2026-10-06 (contract E-5 §1): the park now has an EXIT, so the
    # third line is no longer `== {}`. What this test is FOR is untouched — the
    # park is still terminal for the RUN and still runs no stage — and the exit
    # is reachable only by the operator command `arc-games unpark`, one lift edge
    # per edge INTO `parked` (E-2's four plus P-A.4's `implemented`).
    assert "parked" in orch.TERMINAL
    assert orch.NEXT_STAGE["parked"] is None
    assert set(orch.TRANSITIONS["parked"]) == {src for src, _dst in E2_EDGES} | {"implemented"}


def test_a4_transitions_and_edge_stage_agree_about_parking():
    """One table saying an edge exists and the other not knowing its owner is
    the failure mode `_restage` turns into a KeyError three stages later."""
    assert _edges_into_parked(
        {(src, dst) for src, dests in orch.TRANSITIONS.items() for dst in dests}
    ) == _edges_into_parked(set(orch.EDGE_STAGE))


def test_a5_every_park_edge_is_narrated_for_the_human():
    """The reader the contract's seam map does not name (lead instruction: sweep
    every reader). `cli.narrate` answers None for an un-narrated edge, so a
    missing row is SILENCE in the `arc-games` voice — a slot stopping with
    nothing said about it."""
    for edge in E2_EDGES:
        assert edge in cli.EDGE_NARRATION, f"cli.EDGE_NARRATION does not narrate {edge}"
        said = cli.narrate(_line(*edge, "r"), seen={})
        assert said and "PARKED" in said, f"{edge} narrates as {said!r}"


@pytest.mark.parametrize("edge", sorted(E2_EDGES))
def test_a6_a_ledger_using_each_new_edge_replays_clean(tmp_path, edge):
    """`replay_ledger` is table-driven, and this is the pin that keeps it so."""
    src, dst = edge
    # Walk the §4 spine as far as `src`, then take the park.
    spine = {
        "spec_ok": [(None, "ideated"), ("ideated", "spec_ok")],
        "verified": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
                     ("implemented", "verified")],
        "gated": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
                  ("implemented", "verified"), ("verified", "gated")],
        "reviewed": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
                     ("implemented", "verified"), ("verified", "gated"), ("gated", "baselined"),
                     ("baselined", "played"), ("played", "reviewed")],
    }[src]
    path = tmp_path / "ledger.jsonl"
    rows = [_line(a, b, "walk") for a, b in spine] + [_line(src, dst, "park")]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    table = orch.replay_ledger(path)
    assert table["x"]["state"] == "parked"
    assert table["x"]["terminal"] is True
    assert table["x"]["rejects"]["verifier"] == 0, "a park is not a reject tally"


def test_a7_the_park_is_reachable_from_every_state_a_downstream_reject_departs():
    """`STAGE_REJECT_STATE` is what `_work_slot` parks FROM, and every state in
    it must have the edge or the park is an IllegalTransition crash."""
    assert set(orch.STAGE_REJECT_STATE) == set(orch.STAGE_REJECT_ROUTING)
    for stage, state in orch.STAGE_REJECT_STATE.items():
        assert orch.NEXT_STAGE[state] == stage, (
            f"STAGE_REJECT_STATE says {stage} runs from {state!r}, NEXT_STAGE disagrees"
        )
        assert orch.legal_transition(state, "parked")


# --------------------------------------------------------------------------- #
# B — the two knobs: default false, loud on anything else, and no report drift
# --------------------------------------------------------------------------- #

KNOB_READERS = (("stage_fail_park", orch._stage_fail_park),
                ("respec_feasibility", orch._respec_feasibility))


@pytest.mark.parametrize(("key", "reader"), KNOB_READERS)
@pytest.mark.parametrize("cfg", [
    {}, {"orchestrator": {}}, {"orchestrator": {"workers": 4}},
])
def test_b1_absent_means_false(key, reader, cfg):
    assert reader(cfg) is False


@pytest.mark.parametrize(("key", "reader"), KNOB_READERS)
@pytest.mark.parametrize("value", [True, False])
def test_b2_a_bool_is_read_verbatim(key, reader, value):
    assert reader({"orchestrator": {key: value}}) is value


@pytest.mark.parametrize(("key", "reader"), KNOB_READERS)
@pytest.mark.parametrize("value", [1, 0, "true", "yes", None, 1.0, [], {}])
def test_b3_anything_else_is_a_loud_value_error(key, reader, value):
    """The house rule for every knob in this module: `1` is not a `true`."""
    with pytest.raises(ValueError) as caught:
        reader({"orchestrator": {key: value}})
    assert f"orchestrator.{key}" in str(caught.value)


@pytest.mark.parametrize(("key", "_reader"), KNOB_READERS)
def test_b4_a_bad_value_is_a_config_error_at_second_zero(key, _reader):
    """Validated by `orchestrator_config`, beside `parallel_slots`, so a batch
    cannot discover it three stages and one paid session in."""
    cfg = {"batch": {"id": "x", "size": 1, "seed": 1},
           "orchestrator": {"workers": 1, "wave_size": 1, "max_attrition": 0.3, key: "yes"}}
    with pytest.raises(ValueError) as caught:
        orch.orchestrator_config(cfg)
    assert f"orchestrator.{key}" in str(caught.value)


@pytest.mark.parametrize(("key", "_reader"), KNOB_READERS)
def test_b5_an_unarmed_run_gains_no_report_key(make_cfg, key, _reader):
    """The house rule: absent = today's bytes, report included."""
    cfg, idea = _armed(make_cfg, f"e2-quiet-{key[:4]}", tier="t2")
    runners = b005._SpecRunners(b11._Journal(), cfg, idea=idea,
                                verify_reports=[b005._pass_report()])
    report = b11._advance(cfg, runners)
    assert key not in json.dumps(report["config"]), (
        f"an unarmed batch's report mentions {key}: {report['config']}"
    )
    assert "churn_refused" not in report, "a batch that churned nothing gained the key"
    assert all("churn_refused" not in row for row in report["slots"])
    assert report["parked"] == []


def test_b6_the_overlay_arms_both_and_the_template_agrees():
    """§2/§3: "Template ARMS true … the CLI AUTONOMY_OVERLAY arms true"."""
    overlay = cli.AUTONOMY_OVERLAY["orchestrator"]
    assert overlay == {"stage_fail_park": True, "respec_feasibility": True}
    template = yaml.safe_load(
        (REPO_ROOT / "config" / "template.yaml").read_text(encoding="utf-8")
    )["orchestrator"]
    for key in overlay:
        assert template[key] is True, f"config/template.yaml does not arm {key}"
    built = cli.apply_overlay({"orchestrator": {"workers": 4, "wave_size": 5}},
                              cli.AUTONOMY_OVERLAY)
    assert built["orchestrator"]["workers"] == 4, "the overlay replaced the block"
    assert built["orchestrator"]["stage_fail_park"] is True


# --------------------------------------------------------------------------- #
# C — §1 the reconciliation memory, as units
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("reason", "expected"), [
    # the round cap's own line, with its parenthetical
    ("declaration reconciled to audit: +a.b (round_cap 4; verifier reject)", ["+a.b"]),
    # both directions, and a tier promotion riding in the notes (it carries a
    # `t1->t2` that a naive scan would read as a withdrawal)
    (("declaration reconciled to audit: +a.b, -c.d (round_cap 4; tier promoted t1->t2: 7 "
      "declared terms vs budget 6; verifier reject)"), ["+a.b", "-c.d"]),
    # P-A.1's early line — the one g20261001-5's ping-pong travelled
    (("declaration reconciled early (<=2): +manip.terraform (verifier reject: "
      "undeclared-term)"), ["+manip.terraform"]),
    (("declaration reconciled early (<=2): -manip.terraform (verifier reject: "
      "dead-spec-term)"), ["-manip.terraform"]),
    # and nothing else is an amendment
    ("reconciliation churn refused: -manip.terraform (a prior reconciliation …)", []),
    ("S2b clean", []),
    ("gate fail 2/1 -> respec (architecture §4): visual role-footprint", []),
    ("declaration reconciled early (<=2 malformed", []),
])
def test_c1_the_changes_parser_reads_the_ledger_reason(reason, expected):
    assert orch._changes_in_reason(reason) == expected


def test_c2_the_memory_accumulates_both_directions():
    history = [
        _line("implemented", "spec_ok", "declaration reconciled early (<=2): +a.b (x)"),
        _line("implemented", "spec_ok", "declaration reconciled to audit: -c.d (round_cap 4; x)"),
        _line("implemented", "verified", "S2b clean"),
    ]
    assert orch._reconciliation_memory(history) == {"added": {"a.b"}, "withdrawn": {"c.d"}}


def test_c3_a_withdrawal_of_a_reconciled_addition_is_churn():
    """§1's rule, direction one: never WITHDRAW what a reconciliation ADDED."""
    history = [_line("implemented", "spec_ok",
                     f"declaration reconciled early (<=2): +{CHURN_TERM} (x)")]
    kept, churn = orch._split_churn(
        [{"code": s3v.REJECT_DEAD_SPEC_TERM, "term": CHURN_TERM, "detail": "d"}], history)
    assert kept == []
    assert churn == [f"-{CHURN_TERM}"]


def test_c4_a_re_add_of_a_reconciled_withdrawal_is_churn():
    """§1's rule, direction two: never RE-ADD what a reconciliation WITHDREW."""
    history = [_line("implemented", "spec_ok",
                     f"declaration reconciled to audit: -{CHURN_TERM} (round_cap 4; x)")]
    kept, churn = orch._split_churn(
        [{"code": s3v.REJECT_UNDECLARED_TERM, "term": CHURN_TERM, "detail": "d"}], history)
    assert kept == []
    assert churn == [f"+{CHURN_TERM}"]


def test_c5_an_s1_authored_terms_first_withdrawal_is_untouched():
    """§1's SCOPE: reconciliation-authored changes only. A term the writer put in
    the spec and the audit calls dead has no prior reconciliation to undo."""
    kept, churn = orch._split_churn(
        [{"code": s3v.REJECT_DEAD_SPEC_TERM, "term": "gate.plate", "detail": "d"}],
        [_line("implemented", "verified", "S2b clean")])
    assert churn == []
    assert [row["term"] for row in kept] == ["gate.plate"]


def test_c6_a_partial_churn_keeps_the_rest():
    history = [_line("implemented", "spec_ok",
                     f"declaration reconciled early (<=2): +{CHURN_TERM} (x)")]
    kept, churn = orch._split_churn([
        {"code": s3v.REJECT_DEAD_SPEC_TERM, "term": CHURN_TERM, "detail": "d"},
        {"code": s3v.REJECT_UNDECLARED_TERM, "term": "agent.patrol", "detail": "d"},
    ], history)
    assert churn == [f"-{CHURN_TERM}"]
    assert [row["term"] for row in kept] == ["agent.patrol"]


def test_c7_a_lever_is_remembered_by_the_name_the_finding_uses():
    """`_reconcile_declarations` records a reconciled LEVER in `added` too, and an
    `undeclared-deception` finding names it under `lever`, not `term`."""
    history = [_line("implemented", "spec_ok",
                     "declaration reconciled to audit: -decoy (round_cap 4; x)")]
    kept, churn = orch._split_churn(
        [{"code": s3v.REJECT_UNDECLARED_DECEPTION, "lever": "decoy", "detail": "d"}], history)
    assert (kept, churn) == ([], ["+decoy"])


def test_c8_the_refusal_is_remembered_so_a_repeat_is_not_free():
    refused = f"-{CHURN_TERM}"
    history = [_line("implemented", "spec_ok",
                     f"reconciliation churn refused: {refused} ({orch.CHURN_REFUSED_NOTE}; r)")]
    assert orch._churn_refused_before(history) == {refused}
    assert orch._churn_refused_before([_line("implemented", "verified", "S2b clean")]) == set()


def test_c9_the_churn_line_is_not_itself_an_amendment():
    """A refusal that read back as an amendment would make the memory lie about
    what the spec says."""
    history = [_line("implemented", "spec_ok",
                     f"reconciliation churn refused: -{CHURN_TERM} (note)")]
    assert orch._reconciliation_memory(history) == {"added": set(), "withdrawn": set()}


# --------------------------------------------------------------------------- #
# D — §1 driven through a real batch
# --------------------------------------------------------------------------- #


class _VerdictRunners(b005._SpecRunners):
    """b005's rig with the S2b stage's ok/to_state DERIVED from its own report.

    THE BRIDGE, stated rather than assumed. The borrowed rig decides the verify
    stage's verdict from a scripted `_Outcome`, which can only express a
    CONTIGUOUS run of rejects — and this contract's exhibit is reject (declare
    the term) then reject (call it dead) then pass, with the slot re-entering
    `implemented` through the declaration-only marker in between, which is
    exactly the shape of g20261001-5's lines 12-16. `gen/s3_verify.py::main`
    exits 0 on `pass` and 2 otherwise, so the stage's success IS the report's
    verdict, and deriving it here is the same bridge `test_v2_leniency` makes
    explicit for the same reason.
    """

    def _make(self, stage):
        inner = super()._make(stage)
        if stage != b005.S2B_STAGE:
            return inner

        def runner(ctx):
            result = inner(ctx)        # super() plants report #verify_calls
            if not self.verify_reports:
                return result
            index = min(self.verify_calls - 1, len(self.verify_reports) - 1)
            report = self.verify_reports[index]
            if report.get("verdict") == "pass":
                return result
            codes = ", ".join(str(row.get("code")) for row in report["reject_reasons"])
            return {**result, "ok": False, "to_state": "spec_ok",
                    "reason": f"verifier reject: {codes}"}

        return runner


def _ping_pong_reports(term, *, repeats=1):
    """The g20261001-5 sequence: declare the term, then call it dead."""
    dead = b005._reject_report(b005._dead_term_reason(term), dead_terms=(term,))
    return [
        b005._reject_report(b005._undeclared_term_reason(term), undeclared_terms=(term,)),
        *[dead] * repeats,
        b005._pass_report(),
        b005._pass_report(),
    ]


def _ping_pong_run(make_cfg_fixture, batch_id, term, *, repeats=1):
    cfg, idea = _armed(make_cfg_fixture, batch_id, tier="t2", reject_cap=2,
                       reconcile_early=2, review={"auto_accept": True})
    runners = _VerdictRunners(b11._Journal(), cfg, idea=idea,
                              verify_reports=_ping_pong_reports(term, repeats=repeats))
    report = b11._advance(cfg, runners)
    return cfg, runners, report


def test_d1_the_withdrawal_is_refused_and_the_spec_keeps_the_term(make_cfg):
    """§Blind L1's own sentence, driven: "the withdrawal is refused-as-churn, the
    spec keeps the term, the slot proceeds"."""
    term = b005.NEW_TERM
    cfg, _runners, report = _ping_pong_run(make_cfg, "e2-pingpong", term)

    reasons = "\n".join(b005._reasons(cfg))
    assert f"+{term}" in reasons, f"round 1 never reconciled the term in:\n{reasons}"
    assert orch.CHURN_REFUSED_PREFIX in reasons, (
        f"round 2's withdrawal was not refused as churn:\n{reasons}"
    )
    assert term in b005._terms_on_disk(cfg), (
        f"the spec dropped {term} — the churn was not refused: {b005._terms_on_disk(cfg)}"
    )
    # …and the slot PROCEEDED: no park, no block, and the run did not crash on
    # the 64-step livelock guard.
    assert report["parked"] == [], report["parked"]
    assert report["blocked"] == [], report["blocked"]
    assert ("implemented", "verified") in _spine(cfg), (
        f"the slot never got past the audit:\n{_spine(cfg)}"
    )


def test_d2_the_refusal_is_visible_in_the_report_and_names_the_term(make_cfg):
    term = b005.NEW_TERM
    _cfg, _runners, report = _ping_pong_run(make_cfg, "e2-pingpong-vis", term)
    rows = report.get("churn_refused")
    assert rows, f"the batch report does not name the refusal: {sorted(report)}"
    assert any(f"-{term}" in row["reason"] for row in rows), rows
    assert any(orch.CHURN_REFUSED_NOTE in row["reason"] for row in rows), (
        "the refusal must say WHY it is churn, not just that it happened"
    )
    assert any(row.get("churn_refused") for row in report["slots"])


def test_d3_the_refusal_spends_a_round_rather_than_a_session(make_cfg):
    """§1's mechanism, stated: the churn round costs no re-spec. The line is an
    `implemented --> spec_ok` line, so the ladder and `_verify_rounds` still
    advance — the refusal is not a free pass, it is an unpaid one."""
    term = b005.NEW_TERM
    cfg, runners, _report = _ping_pong_run(make_cfg, "e2-pingpong-cost", term)
    churn = [reason for reason in b005._reasons(cfg)
             if reason.startswith(orch.CHURN_REFUSED_PREFIX)]
    assert len(churn) == 1, churn
    history = [line for line in b11._ledger_lines(cfg)
               if line["reason"].startswith(orch.CHURN_REFUSED_PREFIX)]
    assert (history[0]["from"], history[0]["to"]) == ("implemented", "spec_ok")
    assert orch._verify_rounds(b11._ledger_lines(cfg)) >= 2, (
        "the churn round must count toward the slot-wide bound"
    )
    # the S1 runner ran ONCE, for the slot's first spec — never to answer churn
    assert len(b005._stage_calls(runners._journal, "s1_spec")) == 1


def test_d4_a_repeated_churn_stops_being_free(make_cfg):
    """The second sighting falls through to today's ladder instead of buying
    another round — the livelock `MAX_STEPS_PER_SLOT` used to catch by crashing."""
    term = b005.NEW_TERM
    cfg, _runners, _report = _ping_pong_run(make_cfg, "e2-pingpong-twice", term,
                                           repeats=2)
    churn = [reason for reason in b005._reasons(cfg)
             if reason.startswith(orch.CHURN_REFUSED_PREFIX)]
    assert len(churn) == 1, f"the refusal repeated instead of falling through:\n{churn}"
    assert term in b005._terms_on_disk(cfg), "the fall-through withdrew the term after all"
    # the fall-through IS today's ladder: the second sighting takes the ordinary
    # reject edge and the escalation spends the re-spec it always did.
    assert any(orch.ESCALATE_MARK in reason
               for reason in b005._reasons(cfg, ("implemented", "spec_ok"))), (
        f"the repeat did not fall through to the ladder:\n{b005._all_reason_text(cfg)}"
    )


# --------------------------------------------------------------------------- #
# E — §2 the terminal stage-fail routes, driven
# --------------------------------------------------------------------------- #


def _gate_run(make_cfg_fixture, batch_id, *, times, armed, reject_cap=1, findings=None):
    cfg, idea = _armed(make_cfg_fixture, batch_id, tier="t2", reject_cap=reject_cap,
                       stage_fail_park=armed, review={"auto_accept": True})
    runners = _CodedGateRunners(
        b11._Journal(), cfg,
        outcomes={"verified": b11._Outcome("spec_ok", "gate fail: visual check", times=times)},
        idea=idea, verify_reports=[b005._pass_report()], rows=findings)
    report = b11._advance(cfg, runners)
    return cfg, runners, report


class _CodedGateRunners(b005._GateRunners):
    """b005's gate rig with the REAL runner's finding codes.

    The borrowed rig hands back `{"code": "gate-visual"}`, which is its own
    invention; the live gate runner emits `gate.<check id>`
    (`orchestrator._visual_finding`), and the futility classifier reads codes.
    Nothing else about the rig changes.
    """

    def __init__(self, *args, rows=None, **kwargs):
        self._rows = rows or [orch._visual_finding(
            s3vis.ROLE_FOOTPRINT_CHECK, {"note": b005.GATE_NOTE})]
        super().__init__(*args, **kwargs)

    def _make(self, stage):
        inner = super()._make(stage)
        if stage != b005.S3_GATE_STAGE:
            return inner

        def runner(ctx):
            result = inner(ctx)
            if result["ok"]:
                return result
            rows = [dict(row) for row in self._rows]
            return {**result, "findings": rows, "reject_reasons": rows}

        return runner


def test_e1_unarmed_the_treadmill_is_byte_for_byte_todays(make_cfg):
    """The measured line, pinned: "gate fail 2/1" to `spec_ok`, over the cap."""
    cfg, _runners, report = _gate_run(make_cfg, "e2-tread", times=2, armed=None)
    reasons = b005._reasons(cfg, ("verified", "spec_ok"))
    assert len(reasons) == 2, reasons
    assert "gate fail 1/1" in reasons[0] and "gate fail 2/1" in reasons[1], reasons
    assert orch.ESCALATE_MARK in reasons[1], (
        "today's over-the-cap behaviour is the escalation mark, and this pin is what "
        f"makes the armed path a CHANGE rather than a fix: {reasons[1]!r}"
    )
    assert report["parked"] == [], "the unarmed ladder must not park"
    assert ("verified", "parked") not in _spine(cfg)


def test_e2_armed_the_gate_fail_over_the_cap_parks_from_verified(make_cfg):
    cfg, _runners, report = _gate_run(make_cfg, "e2-gatepark", times=2, armed=True)
    spine = _spine(cfg)
    assert ("verified", "parked") in spine, f"the slot did not park:\n{spine}"
    assert ("verified", "spec_ok") in spine, (
        "the FIRST fail must still take today's route — the park is the cap, not the rule"
    )
    reason = b005._reasons(cfg, ("verified", "parked"))[0]
    assert "gate fail" in reason and "2/1" in reason, reason
    assert orch.STAGE_FAIL_PARK_MARK in reason, reason
    assert "gate.role-footprint" in reason, (
        f"§2: the park reason names the findings codes; got {reason!r}"
    )
    assert "s3_gate" in reason, f"§2: …and the stage; got {reason!r}"
    assert len(report["parked"]) == 1, report["parked"]
    assert report["attrition"]["dead"] == 0, "a park is never attrition"
    assert report["status"] == "complete", (
        f"a parked slot is terminal and must not stop the batch: {report['stop_reason']}"
    )


def test_e3_a_parked_slot_replays_and_resumes_parked(make_cfg):
    cfg, runners, _report = _gate_run(make_cfg, "e2-gatepark-resume", times=2, armed=True)
    table = orch.replay_ledger(Path(orch.batch_dir(cfg)) / orch.LEDGER_NAME)
    slug = next(iter(table))
    assert table[slug]["state"] == "parked" and table[slug]["terminal"]
    before = len(b11._ledger_lines(cfg))
    again = orch.run_batch(cfg, runners=runners)
    assert len(b11._ledger_lines(cfg)) == before, "the resume moved a terminal slot"
    assert again["states"] == {"parked": 1}


def test_e4_a_package_fail_over_the_cap_parks_from_reviewed(make_cfg):
    """§2's second named edge, and the b004 exhibit's own lane."""
    cfg, idea = _armed(make_cfg, "e2-pkgpark", tier="t2", reject_cap=1,
                       stage_fail_park=True, review={"auto_accept": True})
    rows = [{"code": "s6.seed-reject", "detail": "seed 173: no winning line for level 4"}]

    class _S6Runners(b005._SpecRunners):
        def _make(self, stage):
            inner = super()._make(stage)
            if stage != "s6_package":
                return inner

            def runner(ctx):
                result = inner(ctx)
                if result["ok"]:
                    return result
                return {**result, "findings": [dict(row) for row in rows]}

            return runner

    runners = _S6Runners(
        b11._Journal(), cfg,
        outcomes={"reviewed": b11._Outcome("spec_ok", "s6 seed-reject at seed(s) [173]", times=2)},
        idea=idea, verify_reports=[b005._pass_report()])
    b11._advance(cfg, runners)
    spine = _spine(cfg)
    assert ("reviewed", "parked") in spine, f"the slot did not park:\n{spine}"
    reason = b005._reasons(cfg, ("reviewed", "parked"))[0]
    assert "package fail" in reason and "2/1" in reason and "s6.seed-reject" in reason, reason


def test_e5_a_cap_fit_fail_over_the_cap_parks_from_gated(make_cfg):
    """NOT one of the two edges the contract's seam map names — see the handback
    deviation. Without it an armed batch whose S4 keeps rejecting would CRASH on
    an IllegalTransition, which is the b004 failure mode this contract ends."""
    cfg, idea = _armed(make_cfg, "e2-s4park", tier="t2", reject_cap=1,
                       stage_fail_park=True, review={"auto_accept": True})
    runners = b005._SpecRunners(
        b11._Journal(), cfg,
        outcomes={"gated": b11._Outcome("spec_ok", "s4 cap-fit reject", times=2)},
        idea=idea, verify_reports=[b005._pass_report()])
    b11._advance(cfg, runners)
    spine = _spine(cfg)
    assert ("gated", "parked") in spine, f"the slot did not park:\n{spine}"
    reason = b005._reasons(cfg, ("gated", "parked"))[0]
    assert "cap-fit fail" in reason and "2/1" in reason, reason


def test_e6_the_park_leaves_the_findings_on_disk(make_cfg):
    """P-A.4's promise, kept at the new edges: "nothing was deleted — the slot's
    artifacts stand", so the payload that parked it is readable."""
    cfg, _runners, _report = _gate_run(make_cfg, "e2-gatepark-evidence", times=2, armed=True)
    found = [path for path in b005._readable_files(cfg)
             if path.name.endswith(orch.STAGE_FINDINGS_SUFFIX)]
    assert found, "the park deleted the evidence it parked on"
    payload = json.loads(found[0].read_text(encoding="utf-8"))
    assert [row["code"] for row in payload["reject_reasons"]] == ["gate.role-footprint"]


def test_e7_the_park_is_the_cap_not_the_first_fail(make_cfg):
    """Armed, a slot whose gate fails ONCE and then passes is untouched."""
    cfg, _runners, report = _gate_run(make_cfg, "e2-gatepark-once", times=1, armed=True)
    assert report["parked"] == []
    assert ("verified", "gated") in _spine(cfg)


# --------------------------------------------------------------------------- #
# F — §3 the futility classifier
# --------------------------------------------------------------------------- #

#: THE TABLE, stated as a test (the handback states it in prose for the lead).
#: `False` = no spec amendment can answer it = the re-spec is futile when this
#: is the whole set.
FUTILITY_TABLE = {
    # --- verifier codes (s3_verify.REJECT_CODES) ---------------------------
    "undeclared-term": True,                  # declare it (P-A.2 additive)
    "undeclared-deception": True,             # declare the lever
    "dead-spec-term": True,                   # withdraw the declaration
    "unreachable-declared-mechanic": True,    # withdraw the declaration
    "solver-quality": False,                  # the solver plays badly — §3 routes to S2
    "forbidden-static": False,                # the CODE uses a forbidden construct
    # --- the gate's visual card checks ------------------------------------
    "gate.l1-color-floor": False,
    "gate.field-index": False,
    "gate.role-footprint": False,
    "gate.win-render": False,
    "gate.declared-vs-painted": False,
    "gate.chrome-extent": False,
    "gate.danger-visible": False,
    # --- S6 ----------------------------------------------------------------
    "s6.seed-reject": False,                  # §3: "the layout function is buggy"
    # --- NOT futile, deliberately: the conservative direction --------------
    "gate.frames-provenance": True,           # infrastructure, and E-2 does not name it
    "s4.frames-provenance": True,
    "gate.layer-structural": True,            # the merged gate's layers include spec-driven rows
    "s4.cap-fit-reject": True,                # `budget.cap` IS a spec field
    "gate.gate.term-witness": True,           # a declared term with no site — withdraw it
    "s3_gate-fail": True,                     # the no-findings fallback row
    "s6_package-fail": True,
    "something-nobody-has-written-yet": True,
}


@pytest.mark.parametrize("code", sorted(FUTILITY_TABLE))
def test_f1_the_futility_table(code):
    assert orch._spec_answerable(code) is FUTILITY_TABLE[code]


def test_f2_the_reconcilable_codes_are_exactly_the_answerable_verifier_codes():
    """The classifier and P-A.2's reconciliation must agree about the verifier's
    six codes, or a residual the spec CAN answer would park."""
    answerable = {code for code in s3v.REJECT_CODES if orch._spec_answerable(code)}
    assert answerable == set(orch.RECONCILABLE_CODES)
    assert set(orch.FUTILE_VERIFIER_CODES) == set(s3v.REJECT_CODES) - answerable


def test_f3_the_gate_visual_list_is_the_cards_own():
    """`GATE_VISUAL_CHECKS` is reproduced, not imported (the module's house rule
    for names it must not drag numpy in for) — this is the anti-drift pin."""
    assert set(orch.GATE_VISUAL_CHECKS) == set(s3vis.CARD_CHECKS) | {"l1-color-floor"}
    for check in orch.GATE_VISUAL_CHECKS:
        # the code the LIVE gate runner emits for this check
        assert orch._visual_finding(check, {"note": "n"})["code"] in orch.FUTILE_CODES


def test_f4_armed_a_game_side_findings_set_spends_no_session(make_cfg):
    """§3: "Futile -> skip the S1 session entirely and route to the cap verdict"."""
    cfg, idea = _armed(make_cfg, "e2-futile", tier="t2", reject_cap=1,
                       respec_feasibility=True, review={"auto_accept": True})
    runners = _CodedGateRunners(
        b11._Journal(), cfg,
        outcomes={"verified": b11._Outcome("spec_ok", "gate fail: visual check", times=4)},
        idea=idea, verify_reports=[b005._pass_report()])

    # The booby trap: the ESCALATED S1 call is the session §3 skips. The slot's
    # FIRST spec is authored by an S1 call too (`ctx.escalation is None`), and
    # that one is not a re-spec and must still happen.
    inner = runners["s1_spec"]
    escalated = []

    def trapped(ctx):
        if getattr(ctx, "escalation", None) is not None:
            escalated.append(ctx)
        return inner(ctx)

    runners["s1_spec"] = trapped
    report = b11._advance(cfg, runners)

    spine = _spine(cfg)
    assert ("spec_ok", "parked") in spine, f"the futile re-spec did not park:\n{spine}"
    assert escalated == [], (
        f"an S1 session was spent on a futile re-spec ({len(escalated)} call(s))"
    )
    assert report["slots"][0]["respec_runs"] == 0, (
        f"the ledger records a re-spec that never ran: {report['slots'][0]['respec_runs']}"
    )
    reason = b005._reasons(cfg, ("spec_ok", "parked"))[0]
    assert reason.startswith(orch.RESPEC_FUTILE_PREFIX), reason
    assert "gate.role-footprint" in reason, f"§3: the reason names the codes; got {reason!r}"
    assert "no S1 session was spent" in reason, reason


def test_f4b_the_ledger_does_not_bill_the_session_it_skipped():
    """A DEFECT this contract had to fix to stay honest (handback finding).

    The escalation line is written by the stage that failed, BEFORE anybody
    looks at the findings, so it carries `ESCALATE_MARK` whether or not a
    session follows — and `respec_runs_from_ledger` read that mark as "a re-spec
    ran". Armed, that would put a paid session on the batch report that the knob
    exists to not pay for.
    """
    escalation = _line("verified", "spec_ok", f"gate fail 1/1 {orch.ESCALATE_MARK}: visual")
    park = _line("spec_ok", "parked",
                 orch.RESPEC_FUTILE_REASON.format(codes="gate.role-footprint")
                 + " (…; no S1 session was spent)")
    assert orch.respec_runs_from_ledger([escalation]) == 1, "today's count, unchanged"
    assert orch.respec_runs_from_ledger([escalation, park]) == 0, (
        "the skipped session is still on the bill"
    )
    # and the subtraction can never run the count negative
    assert orch.respec_runs_from_ledger([park]) == 0


def test_f5_a_mixed_findings_set_still_spends_the_session(make_cfg):
    """§Blind L3: "one reconcilable term + one game-side -> the respec still runs"."""
    cfg, idea = _armed(make_cfg, "e2-futile-mixed", tier="t2", reject_cap=1,
                       respec_feasibility=True, review={"auto_accept": True})
    rows = [
        orch._visual_finding(s3vis.ROLE_FOOTPRINT_CHECK, {"note": b005.GATE_NOTE}),
        {"code": s3v.REJECT_UNDECLARED_TERM, "term": b005.NEW_TERM, "detail": "undeclared"},
    ]
    runners = _CodedGateRunners(
        b11._Journal(), cfg,
        outcomes={"verified": b11._Outcome("spec_ok", "gate fail: visual check", times=1)},
        idea=idea, verify_reports=[b005._pass_report()], rows=rows)
    b11._advance(cfg, runners)
    assert ("spec_ok", "parked") not in _spine(cfg), (
        "a set with one answerable finding in it is not futile"
    )
    assert len(b005._stage_calls(runners._journal, "s1_spec")) >= 2, (
        "the escalated re-spec never ran"
    )


def test_f6_unarmed_the_session_is_spent_exactly_as_today(make_cfg):
    cfg, _runners, report = _gate_run(make_cfg, "e2-futile-off", times=1, armed=None)
    assert ("spec_ok", "parked") not in _spine(cfg)
    assert report["slots"][0]["respec_runs"] >= 1, (
        "today's behaviour is to spend the re-spec, and this pin is what makes the "
        "armed path a change rather than a fix"
    )


def test_f7_the_dry_run_judges_without_writing(make_cfg):
    """§3's split seam. `_plan_reconciliation` is what `_maybe_respec` calls
    pre-spend, so it must leave spec.yaml byte-for-byte alone whatever it
    decides — including on the paths that used to write and restore."""
    cfg, idea = _armed(make_cfg, "e2-dryrun", tier="t2")
    runners = b005._SpecRunners(b11._Journal(), cfg, idea=idea,
                                verify_reports=[b005._pass_report()])
    b11._advance(cfg, runners)
    spec_dir = b005._live_spec_dirs(cfg)[0]
    before = (spec_dir / "spec.yaml").read_bytes()
    ctx = orch.SlotContext(
        cfg=cfg, batch_id=orch.batch_config(cfg)["id"], slug="s", index=1, state="implemented",
        stage="s3_verify", attempt=1, batch_dir=Path(orch.batch_dir(cfg)),
        ideas_dir=spec_dir, idea_path=spec_dir / "idea.json", corpus_dir=spec_dir.parent,
        spec_dir=spec_dir, respec_count=0, verifier_rejects=0, green_failures=0,
    )
    plan = orch._plan_reconciliation(
        ctx, [{"code": s3v.REJECT_UNDECLARED_TERM, "term": b005.NEW_TERM, "detail": "d"}])
    assert plan["ok"], plan
    assert b005.NEW_TERM in plan["doc"]["game"]["terms"], "the plan did not amend the doc"
    assert (spec_dir / "spec.yaml").read_bytes() == before, (
        "the dry run wrote to spec.yaml"
    )
    # …and the writer, on the same plan, does.
    outcome = orch._reconcile_declarations(
        ctx, [{"code": s3v.REJECT_UNDECLARED_TERM, "term": b005.NEW_TERM, "detail": "d"}])
    assert outcome["ok"] and outcome["added"] == [b005.NEW_TERM]
    assert b005.NEW_TERM in yaml.safe_load(
        (spec_dir / "spec.yaml").read_text(encoding="utf-8"))["game"]["terms"]
    assert outcome["before"] == before, "the outcome must carry the PRE-amendment bytes"


@pytest.mark.parametrize(("reasons", "expected"), [
    # no spec dir at all — a fake-runner batch. INPUT, never amendment: this is
    # the case that would wrongly park every blind-lane slot.
    ([{"code": "undeclared-term", "term": "a.b", "detail": "d"}], orch.REFUSED_INPUT),
    # a reconcilable code naming nothing: also input, not a verdict
    ([{"code": "undeclared-term", "detail": "d"}], orch.REFUSED_INPUT),
])
def test_f8_an_unreadable_dry_run_is_never_evidence_of_futility(tmp_path, reasons, expected):
    ctx = orch.SlotContext(
        cfg={}, batch_id="b", slug="s", index=1, state="implemented", stage="s3_verify",
        attempt=1, batch_dir=tmp_path, ideas_dir=tmp_path, idea_path=tmp_path / "idea.json",
        corpus_dir=tmp_path, spec_dir=None, respec_count=0, verifier_rejects=0,
        green_failures=0)
    plan = orch._plan_reconciliation(ctx, reasons)
    assert plan["ok"] is False
    assert plan["class"] == expected, plan


def test_f9_the_futility_verdict_is_silent_without_findings(tmp_path):
    """No file, nothing to judge, session spent — the conservative direction."""
    ctx = orch.SlotContext(
        cfg={}, batch_id="b", slug="s", index=1, state="spec_ok", stage="s1_spec",
        attempt=1, batch_dir=tmp_path, ideas_dir=tmp_path, idea_path=tmp_path / "idea.json",
        corpus_dir=tmp_path, spec_dir=None, respec_count=0, verifier_rejects=0,
        green_failures=0)
    assert orch._respec_futility(ctx, downstream=True) is None
    assert orch._respec_futility(ctx, downstream=False) is None


def test_f10_the_findings_reader_handles_every_shape(tmp_path):
    spec_dir = tmp_path / "slug"
    (spec_dir / "worker").mkdir(parents=True)
    ctx = orch.SlotContext(
        cfg={}, batch_id="b", slug="s", index=1, state="spec_ok", stage="s1_spec",
        attempt=1, batch_dir=tmp_path, ideas_dir=tmp_path, idea_path=tmp_path / "idea.json",
        corpus_dir=tmp_path, spec_dir=spec_dir, respec_count=0, verifier_rejects=0,
        green_failures=0)
    path = ctx.stage_findings_path
    assert orch._stage_findings_reasons(ctx) is None       # absent
    path.write_text("{not json", encoding="utf-8")
    assert orch._stage_findings_reasons(ctx) is None       # unreadable
    path.write_text(json.dumps({"reject_reasons": []}), encoding="utf-8")
    assert orch._stage_findings_reasons(ctx) is None       # empty
    path.write_text(json.dumps({"reject_reasons": ["x"]}), encoding="utf-8")
    assert orch._stage_findings_reasons(ctx) is None       # no usable row
    path.write_text(json.dumps({"reject_reasons": [{"code": "s6.seed-reject"}]}),
                    encoding="utf-8")
    assert orch._stage_findings_reasons(ctx) == [{"code": "s6.seed-reject"}]


# --------------------------------------------------------------------------- #
# G — the lifted park
# --------------------------------------------------------------------------- #


def test_g1_the_round_cap_park_is_byte_for_byte_its_old_self(make_cfg):
    """`park()` was a closure with `from_state="implemented"` hardcoded; lifting
    it must not move the one reason it already wrote."""
    cfg, idea = _armed(make_cfg, "e2-roundcap", tier="t2", reject_cap=1, round_cap=2,
                       review={"auto_accept": True})
    quality = {"code": s3v.REJECT_SOLVER_QUALITY, "detail": "the solver loses level 3",
               "route": s3v.SOLVER_ONLY_ROUTE}
    runners = _VerdictRunners(
        b11._Journal(), cfg, idea=idea,
        verify_reports=[b005._reject_report(quality), b005._reject_report(quality)])
    report = b11._advance(cfg, runners)
    assert ("implemented", "parked") in _spine(cfg), _spine(cfg)
    reason = b005._reasons(cfg, ("implemented", "parked"))[0]
    assert reason.startswith(orch.ROUND_CAP_PARK_PREFIX), reason
    assert "verifier.round_cap 2" in reason and s3v.REJECT_SOLVER_QUALITY in reason, reason
    assert len(report["parked"]) == 1


# --------------------------------------------------------------------------- #
# H — the real g20261001-5 ledger, replayed (the contract's verification gate)
# --------------------------------------------------------------------------- #


@pytest.fixture
def g5_history(tmp_path):
    """The measured ledger, COPIED to tmp and replayed. The real file is never
    opened for writing and the repo's `out/` is never touched."""
    if not G5_LEDGER.is_file():
        pytest.skip(f"the measured ledger is not on this machine ({G5_LEDGER})")
    local = tmp_path / "ledger.jsonl"
    shutil.copy2(G5_LEDGER, local)
    table = orch.replay_ledger(local)
    assert len(table) == 1, sorted(table)
    return next(iter(table.values()))["history"]


def test_h1_the_measured_ledger_still_replays_under_the_new_tables(g5_history):
    assert len(g5_history) == 28, len(g5_history)
    assert (g5_history[-1]["from"], g5_history[-1]["to"]) == ("reviewed", "spec_ok")


def test_h2_the_ping_pong_is_on_the_record_and_the_memory_sees_it(g5_history):
    """§1's exhibit: line 12 added the term, line 14 withdrew it, and the game
    hash never moved."""
    twelve, fourteen = g5_history[11], g5_history[13]
    assert orch._changes_in_reason(twelve["reason"]) == [f"+{CHURN_TERM}"]
    assert orch._changes_in_reason(fourteen["reason"]) == [f"-{CHURN_TERM}"]
    assert twelve["hashes"]["game"] == fourteen["hashes"]["game"], (
        "the exhibit is a flip on UNCHANGED game bytes"
    )
    assert g5_history[10]["hashes"]["spec"] == fourteen["hashes"]["spec"], (
        "…and the spec hash returned to the bytes it had left"
    )
    # the memory as it stood when line 14's finding arrived
    assert orch._reconciliation_memory(g5_history[:13])["added"] == {CHURN_TERM, "goal.cover",
                                                                    "terrain.trail"}
    kept, churn = orch._split_churn(
        [{"code": s3v.REJECT_DEAD_SPEC_TERM, "term": CHURN_TERM, "detail": "d"}],
        g5_history[:13])
    assert (kept, churn) == ([], [f"-{CHURN_TERM}"]), (
        "the measured withdrawal would not have been refused"
    )


def test_h3_the_treadmill_is_on_the_record_and_the_knob_would_have_parked_it(g5_history):
    """§2's exhibit, and WHERE the armed run would have diverged: the counts are
    1, 2, 3, 4 against a cap of 1, so the SECOND downstream fail is the first
    one over it."""
    downstream = [(index, line) for index, line in enumerate(g5_history, 1)
                  if (line["from"], line["to"]) in orch.DOWNSTREAM_REJECT_EDGES]
    assert [index for index, _ in downstream] == [7, 10, 21, 28]
    assert [line["from"] for _, line in downstream] == ["verified"] * 2 + ["reviewed"] * 2
    for count, (_index, line) in enumerate(downstream, 1):
        assert f"{count}/1" in line["reason"], line["reason"]
        assert orch.ESCALATE_MARK in line["reason"], (
            "today's over-the-cap outcome is the escalation mark and another re-spec"
        )
    # armed, line 10 is a park from `verified` and lines 11-28 never happen.
    assert orch.legal_transition("verified", "parked")
    assert orch.EDGE_STAGE[("verified", "parked")] == "s3_gate"


def test_h4_the_blind_respec_spend_is_on_the_record(g5_history):
    """§3's exhibit: the escalated re-spec at line 7 left the spec hash
    byte-identical, so the session bought a no-op declaration diff."""
    assert orch._escalation_line(g5_history[6]), g5_history[6]["reason"]
    assert g5_history[6]["hashes"]["spec"] == g5_history[7]["hashes"]["spec"], (
        "the re-spec that line 7 paid for changed the spec after all"
    )
    assert orch.respec_runs_from_ledger(g5_history) == 4, (
        "four escalations, four re-spec sessions on the bill"
    )


def test_h4b_the_real_findings_payload_classifies_as_futile():
    """§3's classifier against REAL data, not a fixture: the payload the measured
    batch's last package fail left on disk. Read-only; skipped where the corpus
    is not on this machine."""
    payload = (REPO_ROOT / "out" / "corpus" / "g20261001-5" / "lantern-path-parity-trace"
               / f"worker{orch.STAGE_FINDINGS_SUFFIX}")
    if not payload.is_file():
        pytest.skip(f"the measured corpus is not on this machine ({payload})")
    rows = json.loads(payload.read_text(encoding="utf-8"))["reject_reasons"]
    codes = [str(row["code"]) for row in rows]
    assert codes and set(codes) == {"s6.seed-reject"}, codes
    assert not [code for code in codes if orch._spec_answerable(code)], (
        "the measured residual reads as answerable, so the knob would still have "
        "paid for the no-op re-spec it was written to skip"
    )


def test_h5_the_measured_ledger_has_no_parked_line_and_the_report_would_say_so(g5_history):
    """The outcome diff, as an assertion: the real run parked nothing and ended
    non-terminal at `spec_ok`."""
    assert not [line for line in g5_history if line["to"] == "parked"]
    assert g5_history[-1]["to"] not in orch.TERMINAL


# --------------------------------------------------------------------------- #
# I — scope guards
# --------------------------------------------------------------------------- #


def test_i1_the_repo_is_never_written(make_cfg):
    """Every path this contract's code writes is derived from the orchestrator's
    roots, which `batch_home` redirects — so a batch driven here cannot reach
    the repo's own `out/` or `games/`."""
    cfg, _idea = _armed(make_cfg, "e2-scope")
    for root in ("BATCHES_ROOT", "CORPUS_ROOT", "IDEAS_ROOT"):
        value = Path(getattr(orch, root))
        assert REPO_ROOT not in value.parents and value != REPO_ROOT, value
    assert str(Path(orch.batch_dir(cfg))).startswith(str(Path(orch.BATCHES_ROOT)))


def test_i2_the_contract_touched_no_other_stage_module():
    """s3_verify / s1_spec / s2_implement are READ-ONLY to E-2, so the two knob
    names must appear in NO stage module."""
    for name in ("s1_spec", "s2_implement", "s3_verify", "s3_gate", "s4_baselines",
                 "s5_battery", "s6_package"):
        body = (REPO_ROOT / "gen" / f"{name}.py").read_text(encoding="utf-8")
        for knob in ("stage_fail_park", "respec_feasibility"):
            assert knob not in body, f"gen/{name}.py mentions {knob}"


def test_i3_the_defaults_are_todays_bytes_on_a_full_fake_batch(make_cfg):
    """L4's byte-identity question, asked the way this suite can ask it: an
    unarmed batch's report and ledger carry no E-2 vocabulary at all."""
    cfg, idea = _armed(make_cfg, "e2-identity", tier="t2")
    runners = b005._SpecRunners(b11._Journal(), cfg, idea=idea,
                                verify_reports=[b005._pass_report()])
    report = b11._advance(cfg, runners)
    blob = json.dumps(report) + "\n" + "\n".join(b005._reasons(cfg))
    for token in (orch.STAGE_FAIL_PARK_MARK, orch.CHURN_REFUSED_PREFIX,
                  orch.RESPEC_FUTILE_PREFIX, "stage_fail_park", "respec_feasibility",
                  "churn_refused"):
        assert token not in blob, f"an unarmed batch's output mentions {token!r}"
    assert report["status"] == "complete" and report["states"] == {"packaged": 1}


def test_i4_the_blind_lanes_file_is_not_this_one():
    """The hard rule, as a pin: the implementer never writes the blind file."""
    assert Path(__file__).name == "test_e2_ladder.py"
    assert not (Path(__file__).parent / "test_v2_ladder.py").samefile(Path(__file__)) \
        if (Path(__file__).parent / "test_v2_ladder.py").exists() else True
