"""IMPLEMENTER's suite for frozen contract E-5 — the operator unpark.

Run: .venv/bin/python -m pytest gen/tests/test_e5_unpark.py -q

The blind lane for this contract is `gen/tests/test_v2_unpark.py` and is NOT
this file: nothing here was written with it in view (it did not exist on disk
while this was written and was never opened), and nothing here may be read as
covering it.

WHAT E-5 CLOSED. The operator's 2026-09-29 ruling made `parked` the universal
non-death terminal and E-2 added four more park edges, but `TRANSITIONS` mapped
`"parked": {}` — five ways in, none out, and the RUNBOOK's "A park is NOT a
death: the artifacts stand" was a promise with no mechanism. The live exhibit is
b005r2-auto-s001, parked 2026-09-29T15:50:31 on a reject class contract L-1 made
record-only two days later, worker green, $11.41 spent, `resume` a no-op because
the slot is terminal. So:

  §1  FIVE LIFT EDGES, one per edge INTO `parked`, in all the state tables —
      and `parked` stays terminal, stays stage-less, and nothing a RUN executes
      can travel them. Group A.
  §2  THE TOOL — `arc-games unpark BATCH_ID SLUG --reason TEXT`: replay,
      require `parked`, require a reason, append EXACTLY ONE line to the state
      the slot parked FROM, print, run nothing. Groups B (refusals) and C (the
      line's shape).
  §3  NO EXEMPTIONS — the ordinary ladder, the current config, the whole reject
      history, and a re-park is legal. Group D, including the
      park -> lift -> re-park -> lift cycle.
  §4  REPORT HONESTY — the `parked` block is the park the slot is sitting on
      NOW, counted once, with the LATEST reason. Group E, which also pins the
      byte-identity of every pre-E-5 ledger's replay and report blocks.

HERMETIC. `batch_home` + b11's two write guards + the b005/E-2 fake-runner rigs,
all borrowed through their owner's alias (the `test_e2_ladder` precedent:
borrowed, never copied, never modified). No network, no driver, no agent
session, no subprocess. Nothing is read from or written under the repo's real
`out/` or `games/` — the live exhibit enters as its SHAPE (the park line's
reason text, quoted from the contract) rebuilt in `tmp_path`, never as a copy of
the real ledger.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
import yaml

from gen import cli
from gen import orchestrator as orch
from gen import s3_visual as s3vis

# The rigs, through their owners' names. b005 owns the spec/idea-keeping fake
# runners and the scripted S2b reports, b11 owns the journal, the ledger readers
# and the two write guards, and E-2 owns `_armed` (the cfg with
# `orchestrator.stage_fail_park` on, which is what makes a park reachable).
from gen.tests import test_b005_autonomy as b005
from gen.tests import test_b11_pipeline as b11
from gen.tests import test_e2_ladder as e2

REPO_ROOT = Path(__file__).resolve().parents[2]

_no_network_no_agent = b11._no_network_no_agent      # autouse: no urlopen, no driver
_repo_batches_untouched = b11._repo_batches_untouched  # autouse: the real out/ is read-only
batch_home = b11.batch_home
make_cfg = b11.make_cfg

#: THE LIVE EXHIBIT'S SHAPE, quoted from the contract (the reason text only —
#: the ledger it came from is never read). This is an `implemented --> parked`
#: park, which is P-A.4's edge and the one the $11.41 slot is sitting on.
ECHO_PARK_REASON = (
    "round-cap park: undeclared-deception (verify round 5, verifier.round_cap 4; "
    "the audit rejected again AFTER the declarations were reconciled)"
)

#: the §4 spine, walked as far as each state a park departs from. Keyed by the
#: park's `from`, which is also the state a lift must restore.
SPINE_TO = {
    "spec_ok": [(None, "ideated"), ("ideated", "spec_ok")],
    "implemented": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented")],
    "verified": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
                 ("implemented", "verified")],
    "gated": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
              ("implemented", "verified"), ("verified", "gated")],
    "reviewed": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
                 ("implemented", "verified"), ("verified", "gated"), ("gated", "baselined"),
                 ("baselined", "played"), ("played", "reviewed")],
}

#: the five states §1 names, written out so this file asserts the contract's own
#: list rather than the table it is checking.
LIFT_STATES = ("gated", "implemented", "reviewed", "spec_ok", "verified")


# --------------------------------------------------------------------------- #
# helpers — a hermetic parked ledger, built in tmp
# --------------------------------------------------------------------------- #


def _hashes(tag: str = "a") -> dict:
    return {"spec": tag * 8, "game": tag * 8, "stage_input": tag * 8}


def _row(slug: str, frm, to: str, reason: str, *, ts: str = "2026-09-29T15:50:31+00:00") -> dict:
    """One ledger-shaped line in the frozen key order."""
    return {"slug": slug, "from": frm, "to": to, "reason": reason,
            "hashes": _hashes(), "cost": None, "ts": ts}


def _parked_ledger(cfg, *, park_from: str, reason: str) -> tuple[Path, str]:
    """Write a ledger whose single slot walked the §4 spine and then parked.

    NEVER a copy of a real ledger: the spine is this file's own, the park line
    is the contract's quoted reason, and the whole thing lands under the
    `batch_home` tmp root (both of b11's write guards are armed above).
    """
    bdir = Path(orch.batch_dir(cfg))
    bdir.mkdir(parents=True, exist_ok=True)
    ledger = bdir / orch.LEDGER_NAME
    slug = orch.slot_id(orch.batch_config(cfg)["id"], 1)
    rows = [_row(slug, frm, to, f"the §4 walk: {frm} -> {to}") for frm, to in SPINE_TO[park_from]]
    rows.append(_row(slug, park_from, "parked", reason))
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return ledger, slug


def _echo(make_cfg_fixture, batch_id: str = "e5-echo", *, park_from: str = "implemented"):
    """The live exhibit's shape: a size-1 batch with one parked slot."""
    cfg, _path = make_cfg_fixture(batch_id)
    ledger, slug = _parked_ledger(cfg, park_from=park_from, reason=ECHO_PARK_REASON)
    return cfg, ledger, slug


def _persist_config(cfg) -> Path:
    """Put the batch's config where `cli._config_for` prefers to find it.

    `out/batches/<id>/config.yaml` is the P-4 path and the one a real `unpark`
    resolves through; `make_cfg` writes its copy to a bare tmp file, so the
    CLI-level tests persist it here. Still entirely inside the `batch_home` tmp
    root — both of b11's write guards are armed above.
    """
    path = Path(orch.batch_dir(cfg)) / cli.BATCH_CONFIG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


def _lines(ledger: Path) -> list[dict]:
    return [json.loads(raw) for raw in ledger.read_text(encoding="utf-8").splitlines()
            if raw.strip()]


def _state(cfg) -> dict:
    return orch.replay_ledger(Path(orch.batch_dir(cfg)) / orch.LEDGER_NAME)


def _report(cfg) -> dict:
    path = Path(orch.batch_dir(cfg)) / orch.BATCH_REPORT_NAME
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# helpers — a driven batch whose GATE parks the slot
# --------------------------------------------------------------------------- #


class _GateFailsNTimes(b005._SpecRunners):
    """b005's spec rig with a gate that fails its first `fails` invocations.

    WHY NOT the borrowed `b11._Outcome` script every other park test uses. That
    script is keyed by the STATE the runner is called in, and after a lift the
    slot is back at `verified` — which is also the state `_restage`'s §2 ⊕
    re-run of `s2_implement` is called in (MEASURED: this rig rewrites the slot's
    spec artifacts on every landing, so s2's recorded stage-input digest is
    stale on every resume of such a batch, lift or no lift). One state-keyed
    script cannot tell those two calls apart, so the stale re-run consumes the
    gate's scripted failure and BLOCKS the slot before the gate ever runs — a
    fact about the rig, not about the machine. Keying on the gate's own
    invocation count is immune to it, and it is also what §3's scenario is
    actually about: "if the stage that parked it fails again".

    The failing result is the shape the live gate runner returns — `ok: False`,
    `spec_ok`, and `gate.<check id>` findings (`orchestrator._visual_finding`) —
    so the orchestrator writes the real findings payload and the real park
    reason. Nothing else about the rig changes.
    """

    def __init__(self, journal, cfg, *, fails: int, **kwargs):
        self.fails = int(fails)
        self.gate_runs = 0
        self.gate_failures = 0
        super().__init__(journal, cfg, **kwargs)

    def _make(self, stage: str):
        inner = super()._make(stage)
        if stage != b005.S3_GATE_STAGE:
            return inner

        def runner(ctx):
            result = inner(ctx)
            self.gate_runs += 1
            if self.gate_failures >= self.fails:
                return result
            self.gate_failures += 1
            rows = [orch._visual_finding(s3vis.ROLE_FOOTPRINT_CHECK, {"note": b005.GATE_NOTE})]
            return {**result, "ok": False, "to_state": "spec_ok",
                    "reason": "gate fail: visual check", "cost": None,
                    "findings": rows, "reject_reasons": rows}

        return runner


def _parked_by_gate(make_cfg_fixture, batch_id: str, *, fails: int = 2):
    """A size-1 batch driven until its gate parks the slot. Returns (cfg, rig, slug).

    `reject_cap: 1` + `orchestrator.stage_fail_park` is E-2's armed ladder: the
    first gate fail takes today's route to `spec_ok`, the second is over the cap
    and parks from `verified`. `review.auto_accept` keeps the human out of it.
    """
    cfg, idea = e2._armed(make_cfg_fixture, batch_id, tier="t2", reject_cap=1,
                          stage_fail_park=True, review={"auto_accept": True})
    runners = _GateFailsNTimes(b11._Journal(), cfg, fails=fails, idea=idea,
                               verify_reports=[b005._pass_report()])
    b11._advance(cfg, runners)
    slug = orch.slot_id(orch.batch_config(cfg)["id"], 1)
    assert _state(cfg)[slug]["state"] == "parked", (
        f"the premise: the gate must park the slot. Spine:\n"
        f"{b11._spine(b11._ledger_lines(cfg), slug)}"
    )
    return cfg, runners, slug


# --------------------------------------------------------------------------- #
# A — §1 the five lift edges, in every table, and `parked` still terminal
# --------------------------------------------------------------------------- #


def test_a1_exactly_the_five_states_a_park_departs_from_have_a_lift():
    """§1: "EXACTLY the five states that today have an edge INTO parked"."""
    into = sorted(src for src, dests in orch.TRANSITIONS.items()
                  if src is not orch.BIRTH and "parked" in dests)
    assert into == list(LIFT_STATES), (
        f"the states a park departs from moved: {into} vs the contract's {list(LIFT_STATES)}"
    )
    assert sorted(orch.TRANSITIONS["parked"]) == list(LIFT_STATES), (
        "the lift edges must be exactly the in-edges' sources, so no park can be "
        f"unliftable and no lift can land where no park departed: {orch.TRANSITIONS['parked']}"
    )
    assert orch.PARK_SOURCES == LIFT_STATES, (
        f"PARK_SOURCES is derived from the table and must agree: {orch.PARK_SOURCES}"
    )


@pytest.mark.parametrize("state", LIFT_STATES)
def test_a2_each_lift_edge_is_legal_labelled_and_unowned(state):
    """The three tables §1 names, per edge: the label map, EDGE_STAGE, and the
    one gate on the ledger (`assert_transition`)."""
    assert orch.legal_transition("parked", state), f"§4 draws no parked --> {state}"
    label = orch.assert_transition("parked", state)
    assert "unpark" in label.lower(), (
        f"the parked --> {state} label must say who moved the slot; got {label!r}"
    )
    assert ("parked", state) in orch.EDGE_STAGE, (
        f"EDGE_STAGE has no row for ('parked', {state!r}); `_restage` and `_cost_table` "
        "index it DIRECTLY and a missing row is a KeyError on the next resume"
    )
    assert orch.EDGE_STAGE[("parked", state)] is None, (
        "a lift runs NO stage — naming one would claim work that has not happened and "
        f"feed `_restage` hashes that predate it; got {orch.EDGE_STAGE[('parked', state)]!r}"
    )


def test_a3_parked_is_still_terminal_and_still_runs_nothing():
    """§1's standing half: the exit exists, the terminal does not move."""
    assert "parked" in orch.STATES and "parked" in orch.TERMINAL
    assert orch.NEXT_STAGE["parked"] is None, (
        f"NEXT_STAGE runs {orch.NEXT_STAGE['parked']!r} from `parked`; a stage there would "
        "let a parked slot work itself loose on the next resume"
    )
    assert cli.next_stage_line("parked") is None, "a terminal state says nothing is running"


@pytest.mark.parametrize("state", [s for s in orch.STATES
                                   if s != "parked" and s not in LIFT_STATES])
def test_a4_no_other_exit_from_parked_exists(state):
    """The lift restores the state the slot parked FROM and nothing else: every
    other exit is still an IllegalTransition."""
    assert b11._raised(orch.assert_transition, "parked", state) is not None, (
        f"('parked', {state!r}) must stay illegal — a lift that could choose its "
        "destination would be a way to skip a stage"
    )


@pytest.mark.parametrize("state", LIFT_STATES)
def test_a5_a_ledger_carrying_a_lift_line_replays_clean(tmp_path, state):
    """§1: "replay_ledger is table-driven and must accept a lift line (pin it)"."""
    ledger = tmp_path / f"{state}.jsonl"
    rows = [_row("x", frm, to, "walk") for frm, to in SPINE_TO[state]]
    rows.append(_row("x", state, "parked", "park"))
    rows.append(_row("x", "parked", state, "operator unpark: lift"))
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    row = orch.replay_ledger(ledger)["x"]
    assert row["state"] == state, (
        f"a ledger whose last line is ('parked', {state!r}) must replay to {state!r}; "
        f"it replayed to {row['state']!r}"
    )
    assert row["terminal"] is False, "the lifted slot is no longer terminal — that IS the lift"
    assert row["rejects"] == orch._empty_rejects(), "a lift is not a reject tally"


@pytest.mark.parametrize("state", LIFT_STATES)
def test_a6_every_lift_edge_is_narrated_for_the_human(state):
    """The fifth state table (E-2 addendum 1 D2, ratified): `cli.narrate` answers
    None for an un-narrated edge, so a missing row is SILENCE in the `arc-games`
    voice — a slot moving with nothing said about it."""
    edge = ("parked", state)
    assert edge in cli.EDGE_NARRATION, f"cli.EDGE_NARRATION does not narrate {edge}"
    said = cli.narrate(_row("x", *edge, "operator unpark: lift"), seen={})
    assert said and "UNPARKED" in said, f"{edge} narrates as {said!r}"


def test_a7_every_edge_the_machine_can_take_is_still_narrated():
    """The invariant the five new rows have to keep whole, not just satisfy."""
    edges = {(src, dst) for src, outs in orch.TRANSITIONS.items() for dst in outs}
    assert edges - set(cli.EDGE_NARRATION) == set()


# --------------------------------------------------------------------------- #
# B — §2 the refusal matrix: loud, and NOTHING appended
# --------------------------------------------------------------------------- #


def _refused(cfg, ledger, **kwargs):
    """Call the tool, require a loud refusal, require the ledger untouched."""
    before = ledger.read_bytes()
    exc = b11._raised(orch.unpark_slot, cfg, **kwargs)
    assert isinstance(exc, ValueError), (
        f"the refusal must be loud and must be a ValueError (bad input, not a broken "
        f"machine); got {exc!r}"
    )
    assert ledger.read_bytes() == before, (
        "a refused lift appended something — exit 0 only on a written line, and a refusal "
        "writes nothing at all"
    )
    return exc


def test_b1_an_unknown_slug_is_refused_and_names_the_slots(make_cfg):
    cfg, ledger, slug = _echo(make_cfg, "e5-refuse-slug")
    exc = _refused(cfg, ledger, slug="no-such-slot", reason="I checked the worker")
    assert "no-such-slot" in str(exc) and slug in str(exc), (
        f"the refusal must name what was asked for and what exists; got {exc}"
    )


def test_b2_a_slot_that_is_not_parked_is_refused(make_cfg):
    """The tool "REQUIRES the slot's replayed state == 'parked'"."""
    cfg, _path = make_cfg("e5-refuse-state")
    bdir = Path(orch.batch_dir(cfg))
    bdir.mkdir(parents=True, exist_ok=True)
    ledger = bdir / orch.LEDGER_NAME
    slug = orch.slot_id(orch.batch_config(cfg)["id"], 1)
    rows = [_row(slug, frm, to, "walk") for frm, to in SPINE_TO["implemented"]]
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    exc = _refused(cfg, ledger, slug=slug, reason="it looks stuck")
    assert "implemented" in str(exc) and "parked" in str(exc), (
        f"the refusal must say which state the slot is actually in; got {exc}"
    )


def test_b3_a_slot_that_was_lifted_cannot_be_lifted_again(make_cfg):
    """The same refusal, at the one state that LOOKS liftable: a slot whose park
    has already been lifted is not parked any more."""
    cfg, ledger, slug = _echo(make_cfg, "e5-refuse-twice")
    orch.unpark_slot(cfg, slug=slug, reason="first lift")
    _refused(cfg, ledger, slug=slug, reason="second lift, same park")


@pytest.mark.parametrize(("label", "reason"), [
    ("empty", ""), ("spaces", "   "), ("whitespace", "\n\t "), ("none", None), ("number", 0),
])
def test_b4_an_empty_or_blank_reason_is_refused(make_cfg, label, reason):
    """"requires a non-empty --reason" — and blank is empty: a lift nobody gave a
    reason for records that somebody did this and never why."""
    cfg, ledger, slug = _echo(make_cfg, f"e5-refuse-reason-{label}")
    exc = _refused(cfg, ledger, slug=slug, reason=reason)
    assert "reason" in str(exc).lower(), exc


def test_b5_a_batch_with_no_ledger_at_all_is_refused(make_cfg):
    """`replay_ledger` answers `{}` for a missing file, so the slot is unborn and
    not parked — a refusal, never a lift out of nowhere."""
    cfg, _path = make_cfg("e5-refuse-empty")
    slug = orch.slot_id(orch.batch_config(cfg)["id"], 1)
    exc = b11._raised(orch.unpark_slot, cfg, slug=slug, reason="lift it")
    assert isinstance(exc, ValueError), exc
    assert not (Path(orch.batch_dir(cfg)) / orch.LEDGER_NAME).exists(), (
        "a refused lift created the ledger it refused to write to"
    )


def test_b6_the_cli_turns_every_refusal_into_exit_1_in_its_own_voice(make_cfg, capsys):
    """The command's half of §2: loud, exit 1, nothing appended."""
    cfg, ledger, _slug = _echo(make_cfg, "e5-cli-refuse")
    _persist_config(cfg)
    before = ledger.read_bytes()

    code = cli.main(["unpark", "e5-cli-refuse", "nope", "--reason", "x"])
    captured = capsys.readouterr()
    assert code == 1, f"a refusal must exit 1; got {code}\n{captured.err}"
    assert "nope" in captured.err and cli.PROG in captured.err, captured.err
    assert ledger.read_bytes() == before


def test_b7_the_cli_requires_the_reason_flag(capsys):
    """argparse's own refusal, mapped to this CLI's single usage code."""
    code = cli.main(["unpark", "b1", "b1-s001"])
    assert code == 1, "a missing --reason must be a usage refusal, not a lift"


# --------------------------------------------------------------------------- #
# C — §2 the appended line: exactly one, both texts, no cost
# --------------------------------------------------------------------------- #


def test_c1_one_lift_appends_exactly_one_line_to_the_parks_own_from_state(make_cfg):
    cfg, ledger, slug = _echo(make_cfg, "e5-line-one")
    before = _lines(ledger)
    lifted = orch.unpark_slot(cfg, slug=slug, reason="the worker validates green today")
    after = _lines(ledger)

    assert len(after) == len(before) + 1, f"{len(after) - len(before)} lines were appended"
    assert after[:-1] == before, "the lift rewrote a line it was supposed to leave alone"
    line = after[-1]
    assert (line["from"], line["to"]) == ("parked", "implemented"), (
        "the lift restores THE state the slot parked FROM, read off the park line; got "
        f"{(line['from'], line['to'])}"
    )
    assert lifted["to"] == "implemented" and lifted["from"] == "parked"
    assert lifted["stage"] == orch.NEXT_STAGE["implemented"], (
        "the caller is told what the resume will run, so it can print it"
    )
    assert _state(cfg)[slug]["state"] == "implemented"
    assert _state(cfg)[slug]["terminal"] is False


@pytest.mark.parametrize("state", LIFT_STATES)
def test_c2_the_destination_is_read_off_the_park_line_never_chosen(make_cfg, state):
    """Five parks, five different `from` states, one mechanical rule."""
    cfg, _ledger, slug = _echo(make_cfg, f"e5-from-{state}", park_from=state)
    lifted = orch.unpark_slot(cfg, slug=slug, reason="operator says carry on")
    assert lifted["to"] == state, (
        f"a slot parked from {state!r} must be lifted back to {state!r}; got {lifted['to']!r}"
    )
    assert _state(cfg)[slug]["state"] == state


def test_c2b_the_destination_is_not_a_parameter_of_the_tool_at_all():
    """"never a caller-chosen state" — so there is nothing to choose with."""
    taken = set(inspect.signature(orch.unpark_slot).parameters)
    assert taken == {"cfg", "slug", "reason"}, (
        f"the tool takes {sorted(taken)}; a `to`/`state` parameter would make the lift a "
        "way to skip a stage"
    )
    args = cli.build_parser().parse_args(["unpark", "b", "b-s001", "--reason", "r"])
    assert set(vars(args)) == {"command", "batch_id", "slug", "reason", "func"}, (
        f"the command takes {sorted(vars(args))}; §2's spelling is BATCH_ID SLUG "
        "--reason TEXT and nothing else"
    )
    assert args.func is cli.cmd_unpark


def test_c3_the_reason_carries_both_texts_with_the_operators_first(make_cfg):
    """§2: "reason `operator unpark: <text>` + the park line's own reason quoted"."""
    cfg, ledger, slug = _echo(make_cfg, "e5-line-reason")
    text = "L-1 made this reject class record-only; the worker validates 19/19"
    orch.unpark_slot(cfg, slug=slug, reason=text)
    reason = _lines(ledger)[-1]["reason"]

    assert reason.startswith(orch.UNPARK_PREFIX), (
        f"the operator text must come FIRST — every reason reader in the module is a "
        f"prefix reader, so a quoted park reason would otherwise be read as its own: {reason!r}"
    )
    assert text in reason, f"the operator's own words are missing: {reason!r}"
    assert ECHO_PARK_REASON in reason, (
        f"the park line's own reason must be quoted so the lift reads on its own: {reason!r}"
    )


def test_c4_the_lift_line_carries_hashes_and_no_cost(make_cfg):
    """"current hashes; no cost" — a lift does nothing, so it bills nothing."""
    cfg, ledger, slug = _echo(make_cfg, "e5-line-cost")
    orch.unpark_slot(cfg, slug=slug, reason="lifting it")
    line = _lines(ledger)[-1]

    assert line["cost"] is None, f"a lift spends nothing and must record no cost: {line['cost']}"
    assert set(line["hashes"]) == set(orch.HASH_KEYS), (
        f"the hashes block must be the frozen §2 shape; got {sorted(line['hashes'])}"
    )
    assert isinstance(line["hashes"]["stage_input"], str) and line["hashes"]["stage_input"], (
        "the stage-input digest is always computable (it digests names, not file bytes)"
    )
    assert set(line) == set(orch.LEDGER_KEYS), f"the line's keys moved: {sorted(line)}"


def test_c5_the_lift_is_not_counted_by_any_ladder_counter(make_cfg):
    """§3's mechanism rather than its promise: the lift's edge is in no counter's
    edge set, and its reason in no reader's prefix set."""
    cfg, _ledger, slug = _echo(make_cfg, "e5-counters")
    before = _state(cfg)[slug]
    orch.unpark_slot(cfg, slug=slug, reason="carry on")
    after = _state(cfg)[slug]

    assert after["rejects"] == before["rejects"], "a lift moved a reject count"
    assert after["cost"] == before["cost"], "a lift moved a cost total"
    for counter in (orch._verify_rounds, orch.respec_runs_from_ledger):
        assert counter(after["history"]) == counter(before["history"]), (
            f"{counter.__name__} counted the lift line"
        )
    assert (orch._verifier_rejects_against(after["history"], _hashes()["spec"])
            == orch._verifier_rejects_against(before["history"], _hashes()["spec"])), (
        "the reject ladder must stand: §3 says the history stands"
    )
    assert orch._reconciliation_memory(after["history"]) == \
        orch._reconciliation_memory(before["history"])
    assert orch._churn_refused_before(after["history"]) == \
        orch._churn_refused_before(before["history"])


def test_c6_a_quoted_park_reason_is_never_read_as_the_thing_it_quotes(make_cfg):
    """The one SUBSTRING reader in the module (the report's `tier_promoted`): a
    lift QUOTES a reason, and a quotation is not the thing quoted."""
    cfg, ledger, slug = _echo(make_cfg, "e5-quote")
    promoted = orch.TIER_PROMOTION_REASON.format(before="t2", after="t3", count=9, budget=8)
    rows = _lines(ledger)
    rows[-1]["reason"] = f"round-cap park: undeclared-deception ({promoted})"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    orch.unpark_slot(cfg, slug=slug, reason="lifting it")

    entry = _state(cfg)[slug]
    slot = orch._Slot(slug=slug, index=1, state=entry["state"], history=entry["history"],
                      rejects=entry["rejects"], cost=entry["cost"])
    row = orch._slot_report(slot, cfg, orch.batch_config(cfg)["id"], Path(orch.batch_dir(cfg)))
    assert len(row["tier_promoted"]) == 1, (
        "the promotion happened ONCE and the lift only quoted it; the report must not "
        f"count it twice: {row['tier_promoted']}"
    )


def test_c7_the_cli_prints_the_state_restored_and_the_resume_command(make_cfg, capsys):
    """§2: "prints the state restored and the resume command, and runs NO stage"."""
    cfg, ledger, slug = _echo(make_cfg, "e5-cli-print")
    _persist_config(cfg)
    before = len(_lines(ledger))

    code = cli.main(["unpark", "e5-cli-print", slug, "--reason", "the worker is green"])
    out = capsys.readouterr().out
    assert code == 0, f"a written line is exit 0; got {code}"
    assert "implemented" in out, f"the state restored must be printed: {out}"
    assert cli._resume_command("e5-cli-print") in out, (
        f"the resume command is the next step and must be a copy-paste: {out}"
    )
    assert ECHO_PARK_REASON in out, f"what it was parked for belongs in the print: {out}"
    assert len(_lines(ledger)) == before + 1, "the CLI path appended something other than one line"


def test_c8_the_cli_resolves_a_hand_written_config_like_resume_does(make_cfg, monkeypatch,
                                                                   tmp_path, capsys):
    """§2: "wired beside resume/status via `cli._config_for`, so pre-P-4
    hand-written configs keep working" — the batch dir holds no config.yaml here,
    so only the `config/<id>.yaml` fallback can find it."""
    cfg, _ledger, slug = _echo(make_cfg, "e5-handwritten")
    config_dir = tmp_path / "handwritten-config"
    config_dir.mkdir()
    (config_dir / "e5-handwritten.yaml").write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    assert not (Path(orch.batch_dir(cfg)) / cli.BATCH_CONFIG_NAME).exists()

    code = cli.main(["unpark", "e5-handwritten", slug, "--reason", "hand-written config path"])
    assert code == 0, capsys.readouterr().err
    assert _state(cfg)[slug]["state"] == "implemented"


# --------------------------------------------------------------------------- #
# D — §3 no exemptions: the ordinary ladder, and the re-park cycle
# --------------------------------------------------------------------------- #


def test_d1_a_resume_after_the_lift_runs_the_stage_that_parked_it(make_cfg):
    """The whole point of the tool: the gate that parked this slot runs again
    and the batch can finish. (It passes on round 3 here; "it may park again" is
    D2.)"""
    cfg, runners, slug = _parked_by_gate(make_cfg, "e5-resume", fails=2)
    gate_runs_at_park = runners.gate_runs
    journal_at_park = len(runners._journal.calls)

    lifted = orch.unpark_slot(cfg, slug=slug, reason="the render was fixed by hand")
    assert lifted["to"] == "verified", "the gate's park departs from `verified`"
    assert len(runners._journal.calls) == journal_at_park, (
        "the lift RAN a stage — it is a recorded operator act and the resume is the "
        "machine (the `gen.worker --resync` separation)"
    )
    assert runners.gate_runs == gate_runs_at_park

    again = b11._advance(cfg, runners)
    assert runners.gate_runs > gate_runs_at_park, (
        "the resume did not re-run the gate; a lifted slot re-enters the ORDINARY ladder "
        f"at {lifted['to']!r}, whose stage is {orch.NEXT_STAGE['verified']!r}"
    )
    spine = b11._spine(b11._ledger_lines(cfg), slug)
    assert ("parked", "verified") in spine and ("verified", "gated") in spine, spine
    assert again["states"] == {"packaged": 1}, (
        f"the lifted slot must be able to finish: {again['states']}"
    )
    assert again["parked"] == [], (
        f"§4: a lifted slot whose state moved on is not in the parked block: {again['parked']}"
    )


def test_d2_the_park_lift_repark_lift_cycle_is_legal_and_recorded(make_cfg):
    """§3: "if the stage that parked it fails again it may park again (a second
    lift is a new recorded operator act; pin the park -> lift -> re-park -> lift
    cycle under fakes)"."""
    cfg, runners, slug = _parked_by_gate(make_cfg, "e5-cycle", fails=3)

    orch.unpark_slot(cfg, slug=slug, reason="lift 1: I re-rendered the board")
    b11._advance(cfg, runners)
    assert _state(cfg)[slug]["state"] == "parked", (
        "the third gate fail must RE-PARK the slot: no exemption travels with a lift, and "
        "the reject history stands"
    )

    orch.unpark_slot(cfg, slug=slug, reason="lift 2: and again")
    final = b11._advance(cfg, runners)

    spine = b11._spine(b11._ledger_lines(cfg), slug)
    assert spine.count(("verified", "parked")) == 2, f"two parks expected:\n{spine}"
    assert spine.count(("parked", "verified")) == 2, f"two lifts expected:\n{spine}"
    lifts = [line for line in b11._ledger_lines(cfg)
             if str(line["reason"]).startswith(orch.UNPARK_PREFIX)]
    assert [("lift 1" in line["reason"], "lift 2" in line["reason"]) for line in lifts] == \
        [(True, False), (False, True)], (
        f"each lift is its own recorded act with its own operator text: {lifts}"
    )
    assert final["states"] == {"packaged": 1}, final["states"]
    assert final["parked"] == [], (
        "§4 again: the slot was lifted twice and finished, so it is in no parked block"
    )


def test_d3_the_lift_grants_no_exemption_to_the_reject_ladder(make_cfg):
    """§3: "its reject/round history stands". The proof is that the re-park is
    IMMEDIATE — the cap bites on the next gate fail instead of the ladder
    starting over at 1/1, which is what an exemption would look like."""
    cfg, runners, slug = _parked_by_gate(make_cfg, "e5-ladder", fails=3)
    entry = _state(cfg)[slug]
    spec = entry["history"][-1]["hashes"]["spec"]
    before = orch._verifier_rejects_against(entry["history"], spec)
    park_reason = b005._reasons(cfg, ("verified", "parked"))[0]
    assert before == 1 and "2/1" in park_reason, (
        f"the premise: one standing reject, and the park counted it as 2/1 ({before}, "
        f"{park_reason!r})"
    )

    orch.unpark_slot(cfg, slug=slug, reason="lift")
    assert orch._verifier_rejects_against(_state(cfg)[slug]["history"], spec) == before, (
        "the lift moved the reject tally"
    )

    b11._advance(cfg, runners)
    spine = b11._spine(b11._ledger_lines(cfg), slug)
    assert spine[-1] == ("verified", "parked"), (
        f"the re-park must be immediate — a reset ladder would have taken today's "
        f"below-cap route to `spec_ok` first:\n{spine}"
    )
    assert spine.count(("verified", "spec_ok")) == 1, (
        f"the below-cap route was travelled twice, so the ladder restarted:\n{spine}"
    )
    reason = b005._reasons(cfg, ("verified", "parked"))[-1]
    assert orch.STAGE_FAIL_PARK_MARK in reason and "2/1" in reason, (
        f"the re-park counts the STANDING reject, not a fresh one: {reason!r}"
    )


def test_d4_the_lift_touches_nothing_but_the_ledger(make_cfg):
    """P-A.4's promise, kept through the lift: nothing was deleted, and nothing
    is rewritten either — no findings payload cleared, no spec amended."""
    cfg, _runners, slug = _parked_by_gate(make_cfg, "e5-artifacts", fails=2)
    ledger = Path(orch.batch_dir(cfg)) / orch.LEDGER_NAME

    def snapshot():
        return {path: path.read_bytes() for path in b005._readable_files(cfg)
                if path != ledger}

    before = snapshot()
    assert any(path.name.endswith(orch.STAGE_FINDINGS_SUFFIX) for path in before), (
        "the premise: the findings that parked the slot are on disk"
    )
    orch.unpark_slot(cfg, slug=slug, reason="lift")
    assert snapshot() == before, "the lift wrote, moved or cleared an artifact"


def test_d6_a_slot_lifted_from_a_futile_respec_park_re_implements(make_cfg):
    """MEASURED CONSEQUENCE, reported to the lead rather than resolved quietly.

    `_maybe_respec` is a pre-step at `spec_ok` gated on `_escalated(history)`,
    which reads the LAST line — so after a lift the slot re-enters at `spec_ok`
    and takes `NEXT_STAGE["spec_ok"]` (S2, a re-implement) instead of re-running
    the re-spec whose futility parked it. THE LIFT IS NOT WHAT DID THAT: the
    PARK line already ended the escalation's run as the last line, and the lift
    merely makes that state reachable. So nothing is exempted — the escalation
    line, the reject tally and the findings payload the next build reads all
    stand, and the futile S1 session the knob exists not to pay for is still not
    paid for. This pin states the behaviour so a later change to it is
    deliberate.
    """
    spec = _hashes()["spec"]
    escalated = _row("x", "verified", "spec_ok", f"gate fail 2/1 {orch.ESCALATE_MARK}: rows")
    assert orch._escalated([escalated], spec) is True, "the premise: an escalation stands"

    park = _row("x", "spec_ok", "parked", orch.RESPEC_FUTILE_REASON.format(codes="gate.win-render"))
    assert orch._escalated([escalated, park], spec) is False, (
        "the PARK is what stops the escalation reading as the standing fact — before any "
        "lift exists"
    )
    lift = _row("x", "parked", "spec_ok", "operator unpark: lift")
    assert orch._escalated([escalated, park, lift], spec) is False
    assert orch.last_park_line([escalated, park, lift]) == park, (
        "and the park is still findable afterwards, which is what makes a re-park count "
        "once with the latest reason"
    )


def test_d5_a_lifted_slot_runs_under_the_batchs_current_config(make_cfg):
    """§3: "under the batch's CURRENT config". The park was taken with
    `stage_fail_park` armed; disarmed before the resume, the same third gate fail
    takes today's escalation route instead — the lift carries no frozen policy
    with it."""
    cfg, runners, slug = _parked_by_gate(make_cfg, "e5-current-config", fails=3)
    orch.unpark_slot(cfg, slug=slug, reason="lift under a changed config")
    cfg["orchestrator"] = {**cfg["orchestrator"], "stage_fail_park": False}

    b11._advance(cfg, runners)
    spine = b11._spine(b11._ledger_lines(cfg), slug)
    assert spine.count(("verified", "parked")) == 1, (
        f"the disarmed knob must not park the slot a second time:\n{spine}"
    )
    assert spine.count(("verified", "spec_ok")) == 2, (
        f"disarmed, the over-the-cap fail takes today's escalation route:\n{spine}"
    )


# --------------------------------------------------------------------------- #
# E — §4 report honesty, and the byte-identity of every pre-E-5 ledger
# --------------------------------------------------------------------------- #


def _row_for(cfg, slug: str) -> dict:
    entry = _state(cfg)[slug]
    slot = orch._Slot(slug=slug, index=1, state=entry["state"], history=entry["history"],
                      rejects=entry["rejects"], cost=entry["cost"])
    return orch._slot_report(slot, cfg, orch.batch_config(cfg)["id"], Path(orch.batch_dir(cfg)))


def test_e1_a_parked_slot_still_reports_its_park(make_cfg):
    """The standing behaviour, pinned first: nothing about an unlifted park moved."""
    cfg, _ledger, slug = _echo(make_cfg, "e5-report-parked")
    assert _row_for(cfg, slug)["parked"] == [ECHO_PARK_REASON]


def test_e2_a_lifted_park_leaves_the_parked_block(make_cfg):
    """§4: "must not count a slot whose park was lifted and whose state moved on"."""
    cfg, _ledger, slug = _echo(make_cfg, "e5-report-lifted")
    orch.unpark_slot(cfg, slug=slug, reason="lifted and moving on")
    row = _row_for(cfg, slug)
    assert row["parked"] == [], (
        f"the park was lifted and the state moved on; the block must be empty: {row['parked']}"
    )
    assert row["state"] == "implemented"


def test_e3_a_slot_lifted_and_reparked_counts_once_with_the_latest_reason(make_cfg):
    """§4's second sentence, exactly."""
    cfg, ledger, slug = _echo(make_cfg, "e5-report-reparked")
    orch.unpark_slot(cfg, slug=slug, reason="lift")
    later = "round-cap park: undeclared-deception (verify round 9, verifier.round_cap 4)"
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_row(slug, "implemented", "parked", later)) + "\n")

    row = _row_for(cfg, slug)
    assert row["parked"] == [later], (
        "a slot lifted and re-parked counts ONCE, with the LATEST park reason; got "
        f"{row['parked']}"
    )
    assert len([line for line in _state(cfg)[slug]["history"]
                if line["to"] == "parked"]) == 2, "the premise: it really parked twice"


def test_e4_the_batch_report_and_status_read_the_same_honest_block(make_cfg):
    """Both report surfaces are state-derived, so they agree: the lifted slot is
    out of the parked list and out of the closing note's count."""
    cfg, runners, slug = _parked_by_gate(make_cfg, "e5-report-batch", fails=2)
    report = _report(cfg)
    assert [entry["slug"] for entry in report["parked"]] == [slug]
    assert report["closing_note"] and "1 parked" in report["closing_note"]
    status = "\n".join(orch._status_lines(cfg))
    assert "parked: 1/1" in status, status

    orch.unpark_slot(cfg, slug=slug, reason="lift")
    again = b11._advance(cfg, runners)
    assert again["parked"] == [], again["parked"]
    assert again["closing_note"] == orch.REVIEW_COMPLETE_NOTE, (
        f"a batch with nothing parked says so plainly: {again['closing_note']!r}"
    )
    assert "parked:" not in "\n".join(orch._status_lines(cfg)), (
        "`--status` prints the park note only when something IS parked"
    )


def test_e5_a_ledger_with_no_lift_line_replays_exactly_as_before(make_cfg):
    """§5's byte-identity pin. The derivation changed (`_slot_report` asks for
    the park the slot is in NOW); the ANSWER for every pre-E-5 ledger did not,
    because without a lift edge `parked` is absorbing — so a park line exists iff
    the slot replays to `parked`, and there is at most one of them."""
    cfg, ledger, slug = _echo(make_cfg, "e5-byte-identity")
    entry = _state(cfg)[slug]

    assert entry["state"] == "parked" and entry["terminal"] is True
    assert len(entry["history"]) == len(SPINE_TO["implemented"]) + 1
    assert entry["rejects"] == orch._empty_rejects()
    assert entry["cost"] == orch._empty_cost()
    row = _row_for(cfg, slug)
    assert row["parked"] == [ECHO_PARK_REASON]
    assert row["tier_promoted"] == [] and row["reconciled"] == []
    assert row["respec_runs"] == 0
    # …and the old derivation and the new one agree on it, which is the proof.
    assert row["parked"] == [str(line["reason"]) for line in entry["history"]
                             if line["to"] == "parked"]
    assert ledger.read_text(encoding="utf-8").count("unpark") == 0, (
        "the fixture must carry no lift line — that is what makes it a pre-E-5 ledger"
    )


def test_e6_a_resume_still_leaves_an_unlifted_park_exactly_where_it_is(make_cfg):
    """The house rule, driven: "a tree nobody unparks behaves byte-identically"."""
    cfg, runners, _slug = _parked_by_gate(make_cfg, "e5-untouched", fails=2)
    ledger = Path(orch.batch_dir(cfg)) / orch.LEDGER_NAME
    before = ledger.read_bytes()

    again = orch.run_batch(cfg, runners=runners)
    assert ledger.read_bytes() == before, "the resume moved a terminal slot"
    assert again["states"] == {"parked": 1}
    assert len(again["parked"]) == 1
