"""The orchestrator half of b002 contract 2: an outage blocks, never kills.

LEAD-AUTHORED (the resilience pair's contract scoped the orchestrator out and
instructed a stop-and-report; the reported seam is `_work_slot`'s s2 failure
branch, which charged `green_failures` unconditionally, so two rate-limited
green loops would have routed a SLOT to dead). The guard under test:
a failed s2 result whose reason carries `DRIVER_UNAVAILABLE_REASON` returns
`_block_slot(...)` BEFORE the death counter moves — no ledger line, no
green-death charged, the slot loudly blocked for a later resume.

Run: .venv/bin/python -m pytest gen/tests/test_b002_driverblock.py -v
"""

from __future__ import annotations

import json

import pytest

from gen.orchestrator import GREEN_CAP_DEATHS, _Slot, _work_slot
from gen.s2_implement import DRIVER_UNAVAILABLE_REASON

BATCH_ID = "b-driverblock"
SLUG = f"{BATCH_ID}-s001"


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """A planted slot at spec_ok under tmp roots, plus injectable runners."""
    import gen.orchestrator as orch

    corpus = tmp_path / "corpus" / BATCH_ID
    ideas = tmp_path / "ideas" / BATCH_ID
    spec_dir = corpus / "planted-game"
    (spec_dir / "worker").mkdir(parents=True)
    ideas.mkdir(parents=True)
    idea = json.dumps({"id": f"{BATCH_ID}-i001"})
    (ideas / "idea-001.json").write_text(idea, encoding="utf-8")
    (spec_dir / "idea.json").write_text(idea, encoding="utf-8")
    (spec_dir / "spec.yaml").write_text("game:\n  slug: planted-game\n", encoding="utf-8")
    (spec_dir / "spec.md").write_text("# planted\n", encoding="utf-8")
    (spec_dir / "worker" / "game.py").write_text("G = 1\n", encoding="utf-8")
    (spec_dir / "worker" / "solver.py").write_text("S = 1\n", encoding="utf-8")

    monkeypatch.setattr(orch, "CORPUS_ROOT", tmp_path / "corpus")
    monkeypatch.setattr(orch, "IDEAS_ROOT", tmp_path / "ideas")

    ledger = tmp_path / "ledger.jsonl"
    bdir = tmp_path / "batch"
    bdir.mkdir()

    def drive(runner):
        slot = _Slot(slug=SLUG, index=1, state="spec_ok", history=[],
                     rejects={"lint_kill": 0, "resample": 0, "verifier": 0,
                              "battery_crash": 0, "green_death": 0},
                     cost={}, first_ts=None, last_ts=None)
        calls = {"n": 0}

        def s2_runner(ctx):
            calls["n"] += 1
            return runner(ctx)

        stages = {name: (s2_runner if name == "s2_implement" else _unreachable)
                  for name in orch.STAGES}
        outcome = _work_slot(slot, cfg={"orchestrator": {"respec_cap": 4}},
                             batch_id=BATCH_ID, bdir=bdir,
                             ledger_path=ledger, stages=stages)
        return outcome, slot, calls["n"], ledger

    return drive


def _unreachable(ctx):
    raise AssertionError(f"stage runner for {ctx.stage!r} must not run in this rig")


def _failure(reason: str) -> dict:
    return {"ok": False, "to_state": "spec_ok", "reason": reason,
            "cost": None, "artifacts": {}}


def test_a_driver_unavailable_blocks_without_charging_a_green_death(rig):
    outcome, slot, calls, ledger = rig(
        lambda ctx: _failure(f"green-loop {DRIVER_UNAVAILABLE_REASON} after 0 attempt(s)")
    )

    assert outcome == "blocked", (
        "an infrastructure outage must BLOCK the slot for a later resume — the game was "
        f"never judged; got {outcome!r}"
    )
    assert calls == 1, "a blocked slot must not loop back into the dead driver"
    assert slot.green_failures == 0, (
        "the green-death counter is for games that failed to build; an outage says nothing "
        f"about the game and must not charge it (counter={slot.green_failures})"
    )
    assert slot.state == "spec_ok" and not ledger.exists(), (
        "no §4 edge travels on an outage: state stays, the ledger gets no line"
    )


def test_b_two_outages_never_route_a_slot_to_dead(rig):
    for _ in range(2):
        outcome, slot, _calls, _ledger = rig(
            lambda ctx: _failure(f"green-loop {DRIVER_UNAVAILABLE_REASON} after 0 attempt(s)")
        )
        assert outcome == "blocked" and slot.state != "dead", (
            "contract 2's frozen rule: two infrastructure failures must never kill a slot"
        )


def test_c_an_ordinary_green_failure_still_dies_at_the_cap(rig):
    outcome, slot, calls, ledger = rig(
        lambda ctx: _failure("green-loop attempt-cap after 12 attempt(s)")
    )

    assert outcome == "terminal" and slot.state == "dead", (
        "regression: a real green-loop failure must keep today's routing — "
        f"{GREEN_CAP_DEATHS} failures at the cap route the slot to dead"
    )
    assert calls == GREEN_CAP_DEATHS, (
        f"the failure branch retries below the cap, so the runner is invoked exactly "
        f"{GREEN_CAP_DEATHS} times; got {calls}"
    )
    lines = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()]
    assert [l["to"] for l in lines] == ["dead"], "the dead edge is the one recorded line"
