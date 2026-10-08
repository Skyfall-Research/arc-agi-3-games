"""B11 acceptance: the orchestrator state machine + the merged S3 gate.

Run: .venv/bin/python -m pytest gen/tests/test_b11_pipeline.py -q

Written FROM THE B11 CONTRACT and from canon, never from the implementations:
`gen/orchestrator.py` and `gen/s3_gate.py` were built in parallel with this
file by two other agents and no line of either was read. Every expectation is
either a name/shape the contract froze or a canon rule cited at its source:

  architecture.md §4 — the per-game state machine (the mermaid diagram IS the
      transition table), the batch ledger as the resume state, the worker
      pool, and the `orchestrator.max_attrition` kill criterion.
  architecture.md §3 "S3 — the merged gate" — the four layers, their order,
      the short-circuit, and "a game is `gated` only when all four are green".
  architecture.md §3 S2/S2b/S3d — the failure routings the reject-loop tests
      encode (green-attempts cap, 2 verifier rejects -> escalate, battery
      crashes -> S2).
  architecture.md §2 — the per-game artifact tree the fake stages write, and
      the provenance chain (`spec_hash`, `game_hash`) the resume hashes read.
  architecture.md §5 — `orchestrator: {workers, wave_size, max_attrition}`.
  GEN/provenance/reviews/re-arc-3-source.md:51 — the seven policy NAMES and
      the "120 steps each — all must fail to win" budget (D14: the documented
      behaviour is the whole specification; no re-arc-3 code was opened).
  GEN/tools/acceptance.py THRESHOLDS — the calibrated floors, cited per row:
      `sprite_calls_fail_at` 0 ("official min 1, median 43; no game has
      zero"), `levels_min`/`levels_max` 3/12 around the official 6-10 range,
      `baseline_monotonic_fails` True ("0 of 25 official games are strictly
      monotonic"), `random_beats_l1_fails` True ("0 of 25 official games fall
      to a uniform-random policy"), `loc_warn_below` 200 ("kept low on
      purpose -- a stub detector, not a measure" — a WARN in the reference).

SCRATCH GAMES: every non-fixture game this file needs is authored INSIDE a
test under `tmp_path` (contract: no new repo fixtures). Group 0 proves each
one raw against the engine before any gate code sees it.

NO NETWORK / NO AGENT: an autouse fixture forbids `urlopen`,
`socket.create_connection` and `gen.backends.get_driver`, so a stage that
reached for a real session would fail loudly instead of dialling out. A
second autouse fixture fails any test that writes into the repo's
`out/batches/`.

MEASURED CONFLICTS — reported to the lead, never resolved quietly:

  (1) THE FIXTURE IS RANDOM-BEATABLE. Driven raw (group 0), a uniform-random
      policy over s6_seeded's four declared ids completes level 1 within the
      120-step budget for 69 of 200 rng seeds — including `random.Random(6)`,
      which is exactly `seed_base=0 + policy_index(seeded_random)=6` under
      the contract's frozen seeding rule (it wins at step 81; within 600
      steps it wins in 160/200 runs, median step 140). The contract's group-7
      expectation "each of the seven policies completes ZERO levels on
      fixtures/s6_seeded" is therefore NOT a fact about that fixture — it
      depends entirely on how A indexes the rng. This file does not assert
      the contested outcome: it asserts the GATE RULE invariant (verdict
      `pass` iff every policy completed zero levels, and any policy that did
      complete one is named with its level and step) plus the six
      deterministic policies, which ARE zero on that fixture by measurement.
      The raw measurement is kept as a test so the evidence is checked in.
      CONFIRMED INDEPENDENTLY: the gate's own report on that fixture is
      `verdict: fail`, `failures: [{policy: seeded_random, level: 1, step:
      81}]` — the same step this file measures with no gate code in the loop.
      The lead owns the call (pick a seed_base, change the fixture, or accept
      that the §7 reference is random-beatable).
  (2) THE LOC FLOOR vs THE FIXTURE. `s6_seeded/game.py` is 164 lines by the
      reference's counter (non-blank, non-comment) against a reference
      threshold of 200 — which the reference itself applies as a WARN, never
      a FAIL. "s6_seeded passes the structural floors" therefore holds only
      if A adapted the loc floor as a non-fail row. `test_structural_
      acceptance_on_s6_seeded_has_no_unexplained_fail` carries this
      diagnosis in its message.

CONTRACT AMBIGUITIES this file had to take a position on:
  A. STAGE NAMES are not frozen — the `runners` mapping's keys are unknown.
     `_Runners` is a Mapping that answers for EVERY key (`__missing__` plus a
     `get` override) and pre-populates the key set discovered at runtime from
     the orchestrator's own default runner table, so a dict-merge wiring gets
     fakes too. No stage name is hard-coded.
  B. The RUNNER CTX shape is not frozen. `_ctx_value` reads slug/state/dir
     from a Mapping key or an attribute (one level of nesting), and
     `test_the_runner_ctx_names_its_slug` turns that dependency into ONE
     named failure instead of ten confusing ones.
  C. A FAILED runner's `to_state` has no frozen meaning. The fakes return the
     diagram's destination for routed failures (lint kill -> `respec`,
     verifier reject -> `spec_ok`, battery crash -> `implemented`) and the
     unchanged state for a green-loop failure, because `GREEN_CAP_DEATHS`
     lives on the orchestrator and so the death is B's decision, not the
     runner's.
  D. The BATCH REPORT's key names are not frozen ("per-slug state + per-stage
     cost table + attrition + timestamps"). Cost assertions search the report
     for the exact totals rather than pinning a key; state assertions go
     through `replay_ledger`, which IS frozen.
  E. `replay_ledger`'s per-slug row is "{state, history, rejects…}"; only
     `state` is pinned here, `history` is checked by length.
  F. The ESCALATION SPELLING at `VERIFIER_REJECT_CAP_ESCALATE` is "the reason
     routes respec" — there is no `spec_ok -> respec` edge in §4, so the
     escalation can only live in the reason text. The test asserts the second
     reject's reason differs from the first and names respec/escalation.
  G. The GATE ROW ids are not frozen (only the CheckResult dict shape is), so
     rows are found by keyword over `check_id`, fail-loud with the whole row
     list when no row matches.
  H. WHERE the `random-fails-L1` floor is evaluated is unspecified: the
     contract says it is "consumed from the robustness seeded_random row",
     but §3 runs structural BEFORE robustness. Both readings are accepted —
     the row may be `deferred`/`premise-not-met` at structural time — but a
     computed pass/fail must AGREE with the robustness evidence.
  I. WHERE structural looks for S4 metadata is unspecified (the `<worker>.s4/`
     sibling vs `metadata.json` inside the dir, which is the officials'
     shape). The s6_seeded staging writes BOTH.
  J. The CLI flag names are not frozen. `--config` follows `s4_baselines.main`
     / `s5_battery.main` / `s6_package.main`; `--status` and `--review` are
     the contract's own words. `_cli` fails loudly on "unrecognized
     arguments" so a different spelling surfaces as a named failure.
  K. USAGE EXIT CODES: argparse's own usage exit is 2, which collides with
     the contract's "2 = stopped". Only the bad-config path is asserted to
     be 1.
  L. `main()` may return its code or raise SystemExit; `_cli` accepts either
     (the b9/b10 precedent).
  M. THE BIRTH EDGE. §4's diagram carries `[*] --> ideated`, and an
     append-only ledger whose replay reconstructs state has to record a
     slot's birth. This file requires the STATE-TO-STATE edges to be exactly
     §4's fourteen and admits one extra edge into `ideated` from a birth
     sentinel, whose value is read off `TRANSITIONS` rather than guessed.
  N. THE ARTIFACT PROTOCOL. The runner result's `artifacts` mapping has no
     frozen key names, and the orchestrator verifies that every declared path
     exists but does not learn the slot's spec/worker location from it. The
     fakes therefore write the §2 tree at the paths the ctx itself declares —
     including the batch's idea file — which is what keeps the `spec`/`game`
     resume hashes live under injected fakes.
  O. HOW FAR A CHANGED INPUT REACHES BACK. "Re-queues from that stage" does
     not say whether an UPSTREAM artifact invalidates the stages after it.
     The test asserts the implementation-independent form: the re-run is a
     contiguous SUFFIX of that slug's original stage sequence, and the other
     slug is untouched.
  P. PINNED OFFICIAL EXCEPTIONS. The contract expects zero policy wins on the
     25 officials but allows "KNOWN_OFFICIAL_FAILS-style pinning" for an
     adjudicated exception. The battery therefore requires a pinned official
     to fail EXACTLY its pinned policy/level/step (with a citation and an
     evidence note) and everything else to be clean — and every pin is
     replayed raw here, from the contract's policy semantics, before it is
     believed.
"""

from __future__ import annotations

import copy
import importlib
import json
import random
import shutil
import socket
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml
from arcengine import ActionInput, GameAction

from gen import orchestrator as orch
from gen import s3_gate as gate
from gen.config import REPO_ROOT, load_config
from gen.frames import (
    CENTRE_CLICK,
    TERMINAL_STATES,
    FrameCapture,
    _fresh_game,
    _perform,
    _playable_action_ids,
    _reset,
    capture,
    click_cells,
    mouse,
    settled_grid,
)
from gen.officials import Official, discover_officials, load_official_class
from gen.s3_static import STATUSES, load_worker_classes
from gen.s4_baselines import METADATA_NAME, run_s4
from gen.s4_baselines import OUT_SUFFIX as S4_SUFFIX

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
SEEDED = FIXTURES / "s6_seeded"
TOY = TESTS / "toy_worker"
CONFIG = "config/b001-pilot.yaml"

#: the S4 seed the in-test stage-4 runs use (b10 precedent: verdict `fit`).
S4_SEED = 7

# Collection-time discovery (test_officials_conformance.py / test_b7 pattern):
# the parametrisation needs the slugs before any fixture runs.
_CFG = load_config(CONFIG)
_OFFICIALS = discover_officials(_CFG)
official_param = pytest.mark.parametrize(
    "official", _OFFICIALS, ids=[o.slug for o in _OFFICIALS]
)

# --- the FROZEN vocabulary (B11 contract) ----------------------------------

EXPECTED_STATES = (
    "ideated",
    "respec",
    "spec_ok",
    "implemented",
    "verified",
    "gated",
    "baselined",
    "played",
    "reviewed",
    "packaged",
    "dead",
    "pulled",
    # PIN UPDATE, 2026-09-29 (contract P-A.4), deliberate and justified. THE OPERATOR'S
    # RULING, on the record, verbatim: "We should never kill. Even if it is not
    # satisfied eventually let's not kill." The verify lane's round-cap verdict
    # therefore has a terminal state that is not a death: `parked` keeps the
    # slot's artifacts, stays outside the attrition ratio, and never aborts a
    # batch. `dead` is untouched and `("implemented", "dead")` stays drawn so
    # b005-auto's ledger still replays.
    "parked",
)
EXPECTED_TERMINAL = ("packaged", "dead", "pulled", "parked")

#: architecture.md §4's mermaid edges, transcribed one-for-one (the `[*]`
#: pseudo-state's arrows are births/deaths, not transitions between states).
SECTION4_EDGES = (
    ("ideated", "spec_ok"),       # lint pass
    ("ideated", "respec"),        # lint kill
    ("respec", "ideated"),        # re-sample
    ("spec_ok", "implemented"),   # validate green
    ("spec_ok", "dead"),          # green-attempts cap x2
    ("implemented", "verified"),  # S2b clean
    ("implemented", "spec_ok"),   # verifier reject x2 -> respec
    ("verified", "gated"),        # structural + robustness green
    ("gated", "baselined"),       # g-sampler + cap-fit
    ("baselined", "played"),      # battery done
    ("played", "reviewed"),       # human accept
    ("played", "implemented"),    # crash
    ("reviewed", "packaged"),
    ("reviewed", "pulled"),
    # --- NOT in §4's mermaid: the five edges contracts P-1/P-2/P-3 add -------
    # PIN UPDATE, 2026-09-29, deliberate and justified. The first three are
    # architecture §3's OWN failure routing, which §4's diagram simply never
    # drew an arrow for — §3 says "gate -> nothing, S4 cap-fit -> S2 (cap bug),
    # S6 seed-reject -> S2 (the layout function is buggy)" and the machine had
    # to BLOCK the slot instead of travelling them. b004 hit both holes live
    # (a role-footprint gate fail blocked slot 1 at `verified`; the seed-3
    # package fail crashed and then had no edge anyway). The fourth is P-3's
    # round-cap kill, the bound that lets an unattended slot terminate.
    #
    # They are listed HERE rather than exempted, so `test_transitions_are_
    # exactly_the_section_4_edges` still holds the machine to an exact edge set,
    # `test_every_section_4_edge_is_appended` proves each new one appends, and
    # `NON_EDGES` still proves everything else raises. The canon item — §4's
    # diagram in duckWM (READ-ONLY) does not draw them — is flagged in
    # `gen/orchestrator.TRANSITIONS`, on the operator's 2026-09-29 autonomy ruling.
    ("verified", "spec_ok"),      # P-2.1 gate fail -> re-implement
    ("gated", "spec_ok"),         # P-2.2 cap-fit fail -> re-implement (§3: cap bug)
    ("reviewed", "spec_ok"),      # P-1.2 package fail -> re-implement (§3: layout bug)
    ("implemented", "dead"),      # P-3.2b round-cap kill
    # PIN UPDATE, 2026-09-29 (contract P-A.4), deliberate and justified. THE OPERATOR'S
    # RULING, on the record, verbatim: "We should never kill. Even if it is not
    # satisfied eventually let's not kill." Every would-kill outcome of the
    # round-cap verdict — a non-declaration residual, a post-reconciliation
    # reject, a budget overflow past t3, a floor or lint refusal — now travels
    # THIS edge instead. The kill edge above is kept, and kept listed, because
    # b005-auto's ledger carries a line on it and must still replay; no live
    # code path routes to it (`to_state="dead"` survives only in the s2
    # green-attempts-cap path, which this contract does not touch).
    ("implemented", "parked"),    # P-A.4 round-cap park
    # PIN UPDATE, 2026-10-05 (contract E-2 §2/§3), deliberate and justified, and
    # on the SAME ruling P-A.4 is on. P-A.4 gave the park to the verify lane and
    # left every other failure lane without one, so a downstream reject past
    # `verifier.reject_cap` had no terminal at all: g20261001-5's ledger (on
    # disk) rode "gate fail 1/1", "gate fail 2/1", "package fail 3/1" and
    # "package fail 4/1" — three of the four past a cap of 1 — with the only
    # remaining bound being `MAX_STEPS_PER_SLOT`, which CRASHES rather than
    # parks. Each state a downstream reject departs from now has the park its
    # lane never had (`orchestrator.stage_fail_park`), and the fourth is the
    # re-spec seam: a slot at `spec_ok` whose findings no spec amendment could
    # answer parks without spending the S1 session
    # (`orchestrator.respec_feasibility`). Both knobs default FALSE = today's
    # bytes; these edges are unreachable until a batch arms them.
    ("verified", "parked"),       # E-2 §2 gate fail over the cap
    ("gated", "parked"),          # E-2 §2 cap-fit fail over the cap
    ("reviewed", "parked"),       # E-2 §2 package fail over the cap
    ("spec_ok", "parked"),        # E-2 §3 futile re-spec park
    # PIN UPDATE, 2026-10-06 (contract E-5 §1), deliberate and justified, and
    # listed here rather than exempted for the reason every block above is: this
    # test holds the machine to an EXACT edge set, and the five rows below are
    # then proven to append (`test_every_section_4_edge_is_appended`) while
    # `NON_EDGES` keeps proving that everything else raises.
    #
    # Five edges reached `parked` and none left it: `TRANSITIONS["parked"]` was
    # `{}`, `grep unpark` found nothing, and the RUNBOOK's "A park is NOT a
    # death: the artifacts stand" had no mechanism behind it.
    # b005r2-auto-s001 sat parked from 2026-09-29 on a reject class contract
    # L-1 made record-only two days later — worker green, $11.41 spent — with
    # `resume` a no-op on it, because a terminal slot replays COMPLETE. So the
    # park gains one LIFT per edge into it, restoring the state the slot parked
    # FROM (read off the park line, never chosen).
    #
    # UNREACHABLE BY ANY RUN, which is what keeps every batch's bytes: no knob
    # arms these, no stage verdict routes to them, `parked` stays in
    # EXPECTED_TERMINAL and `NEXT_STAGE["parked"]` stays None. The only
    # traveller is the operator command `arc-games unpark BATCH SLUG --reason
    # TEXT`, which appends one line and runs nothing.
    ("parked", "spec_ok"),        # E-5 §1 operator unpark
    ("parked", "implemented"),    # E-5 §1 operator unpark (the b005r2 exhibit's own)
    ("parked", "verified"),       # E-5 §1 operator unpark
    ("parked", "gated"),          # E-5 §1 operator unpark
    ("parked", "reviewed"),       # E-5 §1 operator unpark
)

LEDGER_KEYS = ("slug", "from", "to", "reason", "hashes", "cost", "ts")
HASH_KEYS = ("spec", "game", "stage_input")
COST_KEYS = ("usd", "tokens_in", "tokens_out")

EXPECTED_POLICIES = (
    "noop_like",
    "repeat_first",
    "repeat_configured_single",
    "repeat_up_or_first",
    "cycle_moves",
    "cycle_all",
    "seeded_random",
)
#: the six policies that are deterministic given the game (everything but the
#: rng one) — measured to complete zero levels on s6_seeded (group 0).
DETERMINISTIC_POLICIES = tuple(p for p in EXPECTED_POLICIES if p != "seeded_random")

#: the ids the policy semantics name: the click action and ACTION1 ("up"),
#: plus the ACTION1-4 move block `cycle_moves` intersects with.
CLICK_ACTION_ID = 6
UP_ACTION_ID = 1
MOVE_ACTION_IDS = (1, 2, 3, 4)

FROZEN_GATE_NAMES = (
    "SCHEMA_VERSION",
    "POLICIES",
    "ROBUSTNESS_STEPS",
    "ACCEPTANCE_NAME",
    "ROBUSTNESS_NAME",
    "GATE_SUFFIX",
    "structural_acceptance",
    "robustness",
    "merged_gate",
)
FROZEN_ORCH_NAMES = (
    "SCHEMA_VERSION",
    "STATES",
    "TERMINAL",
    "TRANSITIONS",
    "LEDGER_NAME",
    "BATCH_REPORT_NAME",
    "VERIFIER_REJECT_CAP_ESCALATE",
    "GREEN_CAP_DEATHS",
    "batch_dir",
    "append_transition",
    "replay_ledger",
    "input_hashes",
    "run_batch",
    "main",
)

# --- measured facts this file cites (group 0 proves each one) --------------

#: `random.Random(6)` = seed_base 0 + seeded_random's index in POLICIES.
RANDOM_SEED_THAT_BEATS_SEEDED = 6
#: …and the step at which it clears level 1 of s6_seeded (measured).
RANDOM_BEATS_SEEDED_AT_STEP = 81
#: s6_seeded/game.py by the reference's counter (non-blank, non-comment).
SEEDED_LOC = 164
#: the §7 reference's authored level count.
SEEDED_LEVELS = 6
#: the B1 toy scaffold's level count — below the 6-10 curriculum floor.
TOY_LEVELS = 2

#: the states whose stages are AGENT stages (architecture §3 "Cost" rows) —
#: the fakes report a cost for these and `None` for the pure-code stages, so
#: "cost is never invented" is testable.
COSTED_STATES = ("ideated", "spec_ok", "implemented", "verified", "played")

#: the §2 artifact each fake stage lands on disk BEFORE its transition is
#: appended (contract: "a transition is appended ONLY AFTER the stage's
#: artifact is on disk").
STAGE_ARTIFACTS = {
    "ideated": ("idea.json",),
    "spec_ok": ("spec.yaml", "spec.md", "lint-report.json"),
    "implemented": ("worker/game.py", "worker/solver.py", "actions/level-1.json"),
    "verified": ("verifier-report.json",),
    "gated": ("acceptance-report.json", "robustness-report.json"),
    "baselined": ("metadata.json",),
    "played": ("battery-report.json", "review/panel.json"),
    "packaged": ("package/manifest.json",),
}

#: the happy path through §4 — what a fake stage returns when the test has
#: not scripted something else for that state.
HAPPY_NEXT = {
    None: "ideated",
    "respec": "ideated",
    "ideated": "spec_ok",
    "spec_ok": "implemented",
    "implemented": "verified",
    "verified": "gated",
    "gated": "baselined",
    "baselined": "played",
    "reviewed": "packaged",
}

#: fallback stage-name set when the orchestrator exposes no default runner
#: table to read the real names off (ambiguity A). The names are
#: architecture §3's own stage headings.
FALLBACK_STAGE_NAMES = (
    "s0",
    "s1",
    "s2",
    "s2b",
    "s3",
    "s3d",
    "s4",
    "s5",
    "s6",
    "ideas",
    "spec",
    "implement",
    "verify",
    "gate",
    "baselines",
    "battery",
    "review",
    "package",
)

#: the two report stubs whose contents ARE frozen by the contract's layer
#: rules ('verifier (verdict "pass" required)', 'battery (status "complete"
#: required)').
CLEAN_VERIFIER = {"verdict": "pass", "diff": {"missing": [], "undeclared": []}}
COMPLETE_BATTERY = {"status": "complete", "passes": 1, "levels": []}


# --------------------------------------------------------------------------- #
# helpers — contract adapters (every tolerance is an ambiguity, listed above)
# --------------------------------------------------------------------------- #


def _attr(module, name):
    """A frozen name off a module, fail-loud (the parallel-build read rule)."""
    value = getattr(module, name, None)
    assert value is not None, f"{module.__name__} is missing the frozen name {name!r}"
    return value


def _raised(fn, *args, **kwargs) -> BaseException | None:
    """Run `fn`, return the exception it raised (the raise TYPE is not frozen)."""
    try:
        fn(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 - see docstring
        return exc
    return None


def _walk(node):
    """Every node of a JSON-able payload, depth first."""
    yield node
    if isinstance(node, Mapping):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _walk(value)


def _text(payload) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


def _has_number(payload, target: float, *, tol: float = 1e-6) -> bool:
    """Is `target` present anywhere in the payload as a number? (ambiguity D)"""
    for node in _walk(payload):
        if isinstance(node, bool) or not isinstance(node, (int, float)):
            continue
        if abs(float(node) - float(target)) <= tol:
            return True
    return False


def _edge_set(transitions) -> set[tuple[str, str]]:
    """`TRANSITIONS` normalised to {(from, to)} whatever container B chose."""
    edges: set[tuple[str, str]] = set()
    if isinstance(transitions, Mapping):
        for src, dests in transitions.items():
            if isinstance(dests, (str, bytes)):
                edges.add((str(src), str(dests)))
                continue
            for dest in dests:
                edges.add((str(src), str(dest)))
        return edges
    for item in transitions:
        src, dest = item
        edges.add((str(src), str(dest)))
    return edges


def _birth_state():
    """The raw `from` value the orchestrator uses for `[*] --> ideated`.

    The diagram's birth arrow has no state name; B picks the sentinel (None,
    "", a constant). It is read back off TRANSITIONS rather than guessed.
    """
    transitions = orch.TRANSITIONS
    sources = transitions if isinstance(transitions, Mapping) else [e[0] for e in transitions]
    for source in sources:
        if source in EXPECTED_STATES:
            continue
        for edge in _edge_set({source: transitions[source]} if isinstance(
            transitions, Mapping
        ) else [(source, dest) for src, dest in transitions if src == source]):
            if edge[1] == "ideated":
                return source
    return None


def _ctx_value(ctx, names: tuple[str, ...], *, depth: int = 2):
    """A slug/state/dir off the runner ctx, by key or attribute (ambiguity B)."""
    if ctx is None or depth < 0:
        return None
    if isinstance(ctx, Mapping):
        for name in names:
            value = ctx.get(name)
            if isinstance(value, (str, Path)):
                return value
        for value in ctx.values():
            if isinstance(value, Mapping) or hasattr(value, "__dict__"):
                found = _ctx_value(value, names, depth=depth - 1)
                if found is not None:
                    return found
        return None
    for name in names:
        value = getattr(ctx, name, None)
        if isinstance(value, (str, Path)):
            return value
    for value in vars(ctx).values() if hasattr(ctx, "__dict__") else ():
        if isinstance(value, Mapping) or hasattr(value, "__dict__"):
            found = _ctx_value(value, names, depth=depth - 1)
            if found is not None:
                return found
    return None


def _ctx_slug(ctx) -> str | None:
    value = _ctx_value(ctx, ("slug", "game_slug", "slot_slug", "slot", "name"))
    return str(value) if value is not None else None


def _ctx_state(ctx) -> str | None:
    value = _ctx_value(ctx, ("from_state", "state", "current_state", "from"))
    value = str(value) if value is not None else None
    return value if value in EXPECTED_STATES else None


def _ctx_dir(ctx, slug: str | None) -> Path | None:
    value = _ctx_value(
        ctx, ("slot_dir", "slug_dir", "game_dir", "corpus_dir", "dir", "root", "path")
    )
    if value is None:
        return None
    path = Path(value)
    if path.suffix:  # a file (a ledger, a report) is not a slot dir
        return None
    if slug and path.name != slug:
        path = path / slug
    return path


def _state_of(row) -> str | None:
    """The state out of a `replay_ledger` row (ambiguity E)."""
    if isinstance(row, Mapping):
        value = row.get("state")
        return str(value) if value is not None else None
    return str(row)


def _table(cfg) -> dict[str, str]:
    """slug -> state, replayed from the batch ledger."""
    replayed = orch.replay_ledger(_ledger_path(cfg))
    assert isinstance(replayed, Mapping), (
        f"replay_ledger must return a slug-keyed mapping, got {type(replayed).__name__}"
    )
    return {slug: _state_of(row) for slug, row in replayed.items()}


def _ledger_path(cfg) -> Path:
    return Path(orch.batch_dir(cfg)) / _attr(orch, "LEDGER_NAME")


def _report_path(cfg) -> Path:
    return Path(orch.batch_dir(cfg)) / _attr(orch, "BATCH_REPORT_NAME")


def _ledger_lines(cfg) -> list[dict]:
    path = _ledger_path(cfg)
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _spine(lines, slug: str | None = None) -> list[tuple[str, str]]:
    return [
        (line.get("from"), line.get("to"))
        for line in lines
        if slug is None or line.get("slug") == slug
    ]


# --- gate report readers (ambiguity G) --------------------------------------


def _rows(report) -> list[dict]:
    """Every CheckResult-shaped row in a gate report (check_id + status)."""
    return [
        node
        for node in _walk(report)
        if isinstance(node, Mapping) and "check_id" in node and "status" in node
    ]


def _find_rows(report, needles: tuple[str, ...], exclude: tuple[str, ...] = ()) -> list[dict]:
    found = []
    for row in _rows(report):
        text = f"{row.get('check_id', '')} {row.get('note', '')}".lower()
        if any(needle in text for needle in needles) and not any(bad in text for bad in exclude):
            found.append(row)
    return found


def _one_row(report, needles: tuple[str, ...], exclude: tuple[str, ...] = ()) -> dict:
    found = _find_rows(report, needles, exclude)
    assert found, (
        f"no structural row names any of {needles} (ambiguity G — the row ids are "
        f"not frozen). Rows:\n{_text(_rows(report))}"
    )
    return found[0]


def _failed_rows(report) -> list[dict]:
    return [row for row in _rows(report) if row.get("status") == "fail"]


def _verdict(report) -> str:
    """A layer report's verdict, under either frozen-ish spelling."""
    assert isinstance(report, Mapping), f"expected a report mapping, got {report!r}"
    for key in ("verdict", "status"):
        if key in report:
            return str(report[key])
    raise AssertionError(f"report carries neither `verdict` nor `status`:\n{_text(report)}")


def _policy_row(report, policy: str) -> Mapping:
    """The robustness row for one policy, by value or by key."""
    for node in _walk(report):
        if not isinstance(node, Mapping):
            continue
        if any(isinstance(v, str) and v == policy for v in node.values()):
            return node
    for node in _walk(report):
        if isinstance(node, Mapping) and isinstance(node.get(policy), Mapping):
            return node[policy]
    raise AssertionError(f"the robustness report names no row for {policy!r}:\n{_text(report)}")


def _row_completions(row: Mapping) -> int:
    """How many levels this policy completed, off whatever key spells it."""
    for key, value in row.items():
        name = str(key).lower()
        if isinstance(value, bool):
            if any(word in name for word in ("any", "won", "win", "beat", "completed")):
                return 1 if value else 0
        elif isinstance(value, int) and "complet" in name:
            return value
    for key, value in row.items():
        name = str(key).lower()
        if isinstance(value, (list, tuple)) and any(
            word in name for word in ("trace", "level", "outcome")
        ):
            numbers = [v for v in value if isinstance(v, int) and not isinstance(v, bool)]
            if numbers:
                return max(numbers)
            booleans = [v for v in value if isinstance(v, bool)]
            if booleans:
                return sum(1 for v in booleans if v)
    raise AssertionError(
        "cannot read a levels-completed count off this robustness row (the row "
        f"shape is not frozen):\n{_text(row)}"
    )


# --- CLI (ambiguities J/K/L) ------------------------------------------------


def _cli(argv, capsys) -> tuple[int, str, str]:
    """`orchestrator.main(argv)`, tolerating a returned code or a SystemExit."""
    try:
        code = orch.main(list(argv))
    except SystemExit as exc:
        code = exc.code
    captured = capsys.readouterr()
    assert "unrecognized arguments" not in captured.err, (
        "the CLI rejected a flag spelled from the contract's own words "
        f"(ambiguity J): {captured.err.strip()}"
    )
    return (0 if code is None else int(code)), captured.out, captured.err


# --------------------------------------------------------------------------- #
# helpers — the fake stage runners (contract: "tests ALWAYS inject fakes")
# --------------------------------------------------------------------------- #


@dataclass
class _Call:
    """One fake stage invocation."""

    n: int
    stage: str
    slug: str | None
    from_state: str | None
    to_state: str
    ok: bool
    cost: dict | None


@dataclass
class _Outcome:
    """A scripted non-happy result, keyed by the state it fires FROM."""

    to_state: str
    reason: str
    ok: bool = False
    times: int = 1
    fired: int = 0


@dataclass
class _Journal:
    """The invocation record groups 2-6 read (and the kill-sweep counter)."""

    calls: list[_Call] = field(default_factory=list)
    contexts: list[object] = field(default_factory=list)
    kill_after: int | None = None

    def count(self, *, slug: str | None = None, to_state: str | None = None) -> int:
        return len(
            [
                call
                for call in self.calls
                if (slug is None or call.slug == slug)
                and (to_state is None or call.to_state == to_state)
            ]
        )

    def states(self, slug: str | None = None) -> list[str]:
        return [call.to_state for call in self.calls if slug is None or call.slug == slug]

    def total_cost(self) -> dict:
        totals = {key: 0.0 for key in COST_KEYS}
        for call in self.calls:
            if call.cost is None:
                continue
            for key in COST_KEYS:
                totals[key] += float(call.cost[key])
        return totals


def _default_stage_names() -> tuple[str, ...]:
    """The orchestrator's OWN stage names, read off the module (ambiguity A).

    Read, never guessed: the runner table's keys are what `run_batch` accepts,
    and an orchestrator that validates them (as it should) rejects any name a
    test invented.
    """
    named = getattr(orch, "STAGES", None)
    if isinstance(named, (tuple, list)) and named and all(isinstance(x, str) for x in named):
        return tuple(named)
    for name, value in vars(orch).items():
        if name.startswith("_") or not isinstance(value, Mapping) or not value:
            continue
        if all(isinstance(key, str) for key in value) and all(
            callable(item) for item in value.values()
        ):
            return tuple(value)
    for name, value in vars(orch).items():
        if "STAGE" not in name.upper() or not isinstance(value, (tuple, list)) or not value:
            continue
        if all(isinstance(x, str) for x in value) and not set(value) & set(EXPECTED_STATES):
            return tuple(value)
    return FALLBACK_STAGE_NAMES


def _stage_cost(n: int, to_state: str) -> dict | None:
    """Distinct per-call costs; `None` for the pure-code stages (§3 cost rows)."""
    if to_state not in COSTED_STATES:
        return None
    return {"usd": round(0.01 * n, 4), "tokens_in": 100 * n, "tokens_out": 10 * n}


def _write_artifacts(
    slot_dir: Path, to_state: str, slug: str, revision: int, *, idea_path: Path | None = None
) -> dict:
    """Land the §2 artifacts for `to_state` and return them as `artifacts`.

    The S0 artifact is written BOTH to the batch's idea file (`ctx.idea_path`,
    where the real sampler puts it) and into the slot's corpus dir, carrying
    the same `id` — that pairing is how a slot's corpus dir is findable from
    its idea, and therefore how the spec/game hashes stay live under fakes.
    """
    written = {}
    idea_id = Path(idea_path).stem if idea_path is not None else f"idea-{slug}"
    for rel in STAGE_ARTIFACTS.get(to_state, ()):
        path = slot_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"slug": slug, "state": to_state, "revision": revision}
        if path.name == "idea.json":
            payload = {"id": idea_id, "slug": slug, "revision": revision}
        if path.suffix == ".json":
            body = json.dumps(payload, indent=2)
        elif path.suffix == ".py":
            body = f'"""fake {to_state} artifact for {slug} (rev {revision})."""\n'
        else:
            body = f"# fake {to_state} artifact\nslug: {slug}\nrevision: {revision}\n"
        path.write_text(body + "\n", encoding="utf-8")
        written[Path(rel).name] = str(path)
        if path.name == "idea.json" and idea_path is not None:
            Path(idea_path).parent.mkdir(parents=True, exist_ok=True)
            Path(idea_path).write_text(body + "\n", encoding="utf-8")
            written["idea_path"] = str(idea_path)
    return written


class _Runners(dict):
    """A runner table that answers for EVERY stage name (ambiguity A).

    Pre-populated with the orchestrator's own stage names when it exposes
    them, so a `{**defaults, **runners}` wiring picks the fakes up; any other
    key is fabricated on demand by `__missing__`/`get`.
    """

    def __init__(self, journal: _Journal, cfg, *, outcomes: Mapping | None = None) -> None:
        super().__init__()
        self._journal = journal
        self._cfg = cfg
        self._outcomes = {state: copy.deepcopy(out) for state, out in (outcomes or {}).items()}
        self._cursor: dict[str, str] = {}
        self._revision: dict[str, int] = {}
        for name in _default_stage_names():
            dict.__setitem__(self, name, self._make(name))

    # -- Mapping surface ---------------------------------------------------
    def __missing__(self, stage):
        runner = self._make(str(stage))
        dict.__setitem__(self, stage, runner)
        return runner

    def get(self, stage, default=None):
        return self[stage]

    def __contains__(self, stage) -> bool:
        return True

    # -- the fake itself ---------------------------------------------------
    def _make(self, stage: str):
        def runner(ctx):
            journal = self._journal
            n = len(journal.calls) + 1
            if journal.kill_after is not None and n > journal.kill_after:
                raise KeyboardInterrupt(
                    f"B11 kill sweep: killed before stage call #{n} ({stage})"
                )
            slug = _ctx_slug(ctx)
            key = slug or ""
            state = _ctx_state(ctx) or self._cursor.get(key)
            outcome = self._outcomes.get(state)
            if outcome is not None and outcome.fired >= outcome.times:
                outcome = None
            if outcome is not None:
                outcome.fired += 1
                to_state, reason, ok = outcome.to_state, outcome.reason, outcome.ok
            elif state in HAPPY_NEXT:
                to_state, reason, ok = HAPPY_NEXT[state], f"fake {stage}: green", True
            else:
                # `played` (human-only) and the terminals have no runner edge.
                to_state, reason, ok = state, f"fake {stage}: nothing to do", True

            slug = slug or to_state  # only reachable when the ctx names no slug
            self._revision[key] = self._revision.get(key, 0) + 1
            idea_path = _ctx_value(ctx, ("idea_path",))
            artifacts = {}
            for slot_dir in self._slot_dirs(ctx, slug):
                artifacts.update(
                    _write_artifacts(
                        slot_dir,
                        to_state,
                        slug,
                        self._revision[key],
                        idea_path=Path(idea_path) if idea_path else None,
                    )
                )
            cost = _stage_cost(n, to_state) if ok else None
            self._cursor[key] = to_state
            journal.contexts.append(ctx)
            journal.calls.append(
                _Call(
                    n=n,
                    stage=stage,
                    slug=slug,
                    from_state=state,
                    to_state=to_state,
                    ok=ok,
                    cost=cost,
                )
            )
            return {
                "ok": ok,
                "to_state": to_state,
                "reason": reason,
                "cost": cost,
                "artifacts": artifacts,
            }

        return runner

    def _slot_dirs(self, ctx, slug: str) -> list[Path]:
        """Where the artifacts land: the ctx's dir AND the batch dir's slot."""
        dirs = [Path(orch.batch_dir(self._cfg)) / slug]
        from_ctx = _ctx_dir(ctx, slug)
        if from_ctx is not None and from_ctx not in dirs:
            dirs.append(from_ctx)
        for path in dirs:
            path.mkdir(parents=True, exist_ok=True)
        return dirs


def _slot_files(cfg, journal: _Journal, slug: str, name: str) -> list[Path]:
    """Every copy of one artifact the fakes wrote for `slug`.

    The fakes write into both trees a ctx names — the batch dir and the §2
    corpus dir — so a mutation test has to move all of them.
    """
    trees = [Path(orch.batch_dir(cfg)) / slug]
    for ctx in journal.contexts:
        if _ctx_slug(ctx) != slug:
            continue
        found = _ctx_dir(ctx, slug)
        if found is not None and found not in trees:
            trees.append(found)
    return [tree / name for tree in trees if (tree / name).is_file()]


def _advance(cfg, runners, *, accept: bool = True, rounds: int = 8):
    """Run the batch, answering every `played` stop with a human accept."""
    report = orch.run_batch(cfg, runners=runners)
    for _ in range(rounds):
        pending = [slug for slug, state in _table(cfg).items() if state == "played"]
        if not pending or not accept:
            break
        for slug in pending:
            report = orch.run_batch(cfg, runners=runners, review=(slug, "accept"))
    return report


# --------------------------------------------------------------------------- #
# helpers — scratch games (tmp_path only; group 0 proves each one raw)
# --------------------------------------------------------------------------- #

#: padding so the calibrated loc floor (`loc_warn_below` 200, "a stub
#: detector, not a measure") cannot confound the layer actually under test.
_FILLER = "\n".join(f"filler line {i:03d} — padding, not logic." for i in range(210))

TRIVIAL_GAME = f'''"""SCRATCH — a degenerate game: ANY single game action wins the level.

{_FILLER}
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

GAME_ID = "b11-trivial-win"
WALL, PLAYER, GOAL = 4, 9, 12
LEVEL_COUNT = 6


def _level(index: int) -> Level:
    return Level(sprites=[
        Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
        Sprite([[WALL] * 8], name="wall_bottom", x=0, y=7),
        Sprite([[GOAL]], name="goal", x=6, y=6, layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=1, y=1 + index % 3, layer=2),
    ])


class TrivialWin(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id=GAME_ID,
            levels=[_level(k) for k in range(LEVEL_COUNT)],
            camera=Camera(width=8, height=8),
            available_actions=[1, 2, 3, 4],
        )

    def step(self) -> None:
        self.complete_action()
        if self.action.id != GameAction.RESET:
            self.next_level()
'''

UNWINNABLE_GAME = f'''"""SCRATCH — a sound but unwinnable board: no policy can complete a level.

{_FILLER}
"""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

GAME_ID = "b11-unwinnable"
WALL, PLAYER, MARK = 4, 9, 12
LEVEL_COUNT = 6

DIRS = {{
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}}


def _level(index: int) -> Level:
    return Level(sprites=[
        Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
        Sprite([[WALL] * 8], name="wall_bottom", x=0, y=7),
        Sprite([[WALL]] * 6, name="wall_left", x=0, y=1),
        Sprite([[WALL]] * 6, name="wall_right", x=7, y=1),
        Sprite([[MARK]], name="mark", x=6, y=1 + index % 5, layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=1, y=1 + index % 3, layer=2),
    ])


class Unwinnable(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id=GAME_ID,
            levels=[_level(k) for k in range(LEVEL_COUNT)],
            camera=Camera(width=8, height=8),
            available_actions=[1, 2, 3, 4],
        )

    def step(self) -> None:
        delta = DIRS.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)
        self.complete_action()
'''

NO_SPRITE_GAME = f'''"""SCRATCH — an empty board: no sprite constructor anywhere in this file.

The token the floor counts is deliberately absent from this docstring too: the
reference counts the constructor call over the WHOLE source, docstrings
included.

{_FILLER}
"""

from arcengine import ARCBaseGame, Camera, Level

GAME_ID = "b11-no-sprites"
LEVEL_COUNT = 6


class EmptyBoard(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id=GAME_ID,
            levels=[Level(sprites=[]) for _ in range(LEVEL_COUNT)],
            camera=Camera(width=8, height=8),
            available_actions=[1, 2, 3, 4],
        )

    def step(self) -> None:
        self.complete_action()
'''

SCRATCH_GAMES = {
    "trivial": TRIVIAL_GAME,
    "unwinnable": UNWINNABLE_GAME,
    "no_sprites": NO_SPRITE_GAME,
}


def _scratch_worker(root: Path, name: str) -> Path:
    """Write one scratch game as a worker dir under `root` (tmp_path only)."""
    assert name in SCRATCH_GAMES, f"unknown scratch game {name!r}"
    worker = root / name
    worker.mkdir(parents=True, exist_ok=True)
    (worker / "game.py").write_text(SCRATCH_GAMES[name], encoding="utf-8")
    return worker


def _loc(path: Path) -> int:
    """The reference counter: non-blank, non-comment lines (acceptance.py)."""
    return len(
        [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    )


def _action(action_id: int, cell: tuple[int, int] | None = None) -> ActionInput:
    """One action input; the click action carries coordinates in `data`."""
    if action_id == CLICK_ACTION_ID:
        x, y = cell if cell is not None else CENTRE_CLICK
        return mouse(x, y)
    return ActionInput(id=GameAction[f"ACTION{action_id}"])


def _quietest_id(game_cls, ids: list[int]) -> int:
    """`noop_like`: the id whose single probe changes the settled frame least,
    ties to the lowest id (the contract's frozen wording), measured on FRESH
    instances so no probe sees another's state."""
    base = _fresh_game(game_cls)
    before = settled_grid(_reset(base))
    changes = {}
    for action_id in ids:
        fresh = _fresh_game(game_cls)
        _reset(fresh)
        after = settled_grid(_perform(fresh, _action(action_id)))
        changes[action_id] = sum(
            1 for row_a, row_b in zip(before, after) for a, b in zip(row_a, row_b) if a != b
        )
    return min(ids, key=lambda i: (changes[i], i))


def _raw_line(game_cls, policy: str, *, steps: int, seed_base: int = 0) -> tuple[int, int | None]:
    """One of the seven policies driven RAW from the contract's semantics.

    Independent of `gen.s3_gate`: this is what the gate's rows are checked
    against (group 0) and what every pinned official exception is replayed
    with (group 8).
    """
    assert policy in EXPECTED_POLICIES, policy
    game = _fresh_game(game_cls)
    frame = _reset(game)
    ids = _playable_action_ids(frame)
    assert ids, "a game with no declared non-RESET action cannot be driven"
    cells = click_cells(_fresh_game(game_cls))
    first_cell = (cells[0].x, cells[0].y) if cells else CENTRE_CLICK
    rng = random.Random(seed_base + EXPECTED_POLICIES.index(policy))
    moves = [i for i in ids if i in MOVE_ACTION_IDS] or list(ids)
    quietest = _quietest_id(game_cls, ids) if policy == "noop_like" else None

    completed, first = 0, None
    for index in range(steps):
        if frame.state in TERMINAL_STATES:
            break
        cell = None
        if policy == "noop_like":
            action_id = quietest
        elif policy == "repeat_first":
            action_id = ids[0]
        elif policy == "repeat_configured_single":
            action_id = CLICK_ACTION_ID if CLICK_ACTION_ID in ids else ids[0]
            cell = first_cell if action_id == CLICK_ACTION_ID else None
        elif policy == "repeat_up_or_first":
            action_id = UP_ACTION_ID if UP_ACTION_ID in ids else ids[0]
        elif policy == "cycle_moves":
            action_id = moves[index % len(moves)]
        elif policy == "cycle_all":
            action_id = ids[index % len(ids)]
        else:  # seeded_random
            action_id = rng.choice(ids)
            cell = (rng.randrange(64), rng.randrange(64))
        frame = _perform(game, _action(action_id, cell))
        if int(frame.levels_completed) > completed:
            completed = int(frame.levels_completed)
            first = first if first is not None else index + 1
    return completed, first


def _drive(game_cls, pick, *, steps: int) -> tuple[int, str, int | None]:
    """Raw engine drive: (levels completed, final state, first winning step)."""
    game = _fresh_game(game_cls)
    frame = _reset(game)
    ids = _playable_action_ids(frame)
    completed, first = 0, None
    for index in range(steps):
        if frame.state in TERMINAL_STATES:
            break
        action_id = pick(index, ids)
        action = (
            mouse(32, 32)
            if action_id == 6
            else ActionInput(id=GameAction[f"ACTION{action_id}"])
        )
        frame = _perform(game, action)
        if int(frame.levels_completed) > completed:
            completed = int(frame.levels_completed)
            first = first if first is not None else index + 1
    return completed, str(frame.state), first


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _no_network_no_agent(monkeypatch):
    """No test here dials out or starts a real agent session (B11 rule)."""

    def _forbidden(*args, **kwargs):
        raise AssertionError(
            "B11 tests never open a network connection or start an agent session"
        )

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    backends = importlib.import_module("gen.backends")
    monkeypatch.setattr(backends, "get_driver", _forbidden)


@pytest.fixture(autouse=True)
def _repo_batches_untouched():
    """A B11 test that wrote into the repo's own batch root fails here."""
    root = REPO_ROOT / "out" / "batches"

    def snapshot():
        return sorted(str(path) for path in root.rglob("*")) if root.exists() else None

    before = snapshot()
    yield
    assert snapshot() == before, f"a B11 test wrote into the repo batch root {root}"


@pytest.fixture
def batch_home(tmp_path, monkeypatch) -> Path:
    """Point every repo-rooted path in the orchestrator at `tmp_path`."""
    patched = {}
    for name, value in list(vars(orch).items()):
        if name.startswith("__") or not isinstance(value, Path):
            continue
        try:
            relative = value.resolve().relative_to(REPO_ROOT)
        except ValueError:
            continue
        patched[name] = tmp_path / relative
        monkeypatch.setattr(orch, name, tmp_path / relative)
    # …and the shared root, for a batch_dir computed off gen.config directly.
    monkeypatch.setattr("gen.config.REPO_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def make_cfg(batch_home, tmp_path):
    """(cfg dict, config path) for a batch id nobody else uses."""

    def _make(batch_id: str, *, size: int = 1, max_attrition: float | None = None) -> tuple:
        cfg = copy.deepcopy(_CFG)
        cfg["batch"]["id"] = batch_id
        cfg["batch"]["size"] = size
        if max_attrition is not None:
            cfg["orchestrator"]["max_attrition"] = max_attrition
        path = tmp_path / f"{batch_id}.yaml"
        path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        return cfg, path

    return _make


@pytest.fixture(scope="session")
def official_class():
    """Slug-keyed class cache — officials are expensive to exec-load."""
    cache: dict[str, type] = {}

    def _get(official: Official) -> type:
        if official.slug not in cache:
            cache[official.slug] = load_official_class(official.py_path)
        return cache[official.slug]

    return _get


@pytest.fixture(scope="session")
def official_capture(official_class):
    """Slug-keyed probe-capture cache: one probe plan per official."""
    cache: dict[str, FrameCapture] = {}

    def _get(official: Official) -> FrameCapture:
        if official.slug not in cache:
            cache[official.slug] = capture(official_class(official))
        return cache[official.slug]

    return _get


@pytest.fixture(scope="session")
def seeded_staged(tmp_path_factory) -> tuple[Path, FrameCapture, dict]:
    """A tmp copy of fixtures/s6_seeded with its REAL S4 metadata beside it.

    `run_s4` is executed in-test (b10 pattern), so `<worker>.s4/metadata.json`
    lands in tmp and never in the repo's `out/`. The metadata is ALSO copied
    into the worker dir itself, which is the officials' own shape — ambiguity
    I: where the structural descent floor looks for it is not frozen.
    """
    root = tmp_path_factory.mktemp("b11seeded")
    worker = root / SEEDED.name
    shutil.copytree(SEEDED, worker, ignore=shutil.ignore_patterns("__pycache__"))
    report = run_s4(worker, _CFG, seed=S4_SEED)
    assert report["verdict"] == "fit", f"s6_seeded: S4 verdict {report['verdict']}"
    s4_dir = worker.parent / (worker.name + S4_SUFFIX)
    metadata = json.loads((s4_dir / METADATA_NAME).read_text(encoding="utf-8"))
    shutil.copyfile(s4_dir / METADATA_NAME, worker / METADATA_NAME)
    game_cls, _solver = load_worker_classes(worker)
    return worker, capture(game_cls), metadata


@pytest.fixture(scope="session")
def scratch_root(tmp_path_factory) -> Path:
    """One tmp home for the scratch games, written once per session."""
    root = tmp_path_factory.mktemp("b11scratch")
    for name in SCRATCH_GAMES:
        _scratch_worker(root, name)
    return root


@pytest.fixture(scope="session")
def scratch_capture(scratch_root):
    """Probe capture per scratch game, cached."""
    cache: dict[str, tuple[Path, FrameCapture]] = {}

    def _get(name: str) -> tuple[Path, FrameCapture]:
        if name not in cache:
            worker = scratch_root / name
            game_cls, _solver = load_worker_classes(worker)
            cache[name] = (worker, capture(game_cls))
        return cache[name]

    return _get


# --------------------------------------------------------------------------- #
# group 0 — the scratch games and the fixture, proven RAW against the engine
# (no gen.s3_gate / gen.orchestrator call in this group)
# --------------------------------------------------------------------------- #


def test_the_trivial_scratch_game_falls_to_a_single_action(scratch_root):
    """One game action = one level; six = WIN. The robustness FAIL subject."""
    game_cls, _solver = load_worker_classes(scratch_root / "trivial")
    completed, state, first = _drive(game_cls, lambda k, ids: ids[0], steps=12)
    assert first == 1, "the first game action must already complete level 1"
    assert completed == 6, f"expected all six levels, got {completed}"
    assert state == "GameState.WIN", state


def test_the_unwinnable_scratch_game_completes_no_level(scratch_root):
    """The merged-gate control: structurally sound, no level ever completes."""
    game_cls, _solver = load_worker_classes(scratch_root / "unwinnable")
    for policy in EXPECTED_POLICIES:
        for seed_base in (0, 3, 11):
            completed, first = _raw_line(game_cls, policy, steps=240, seed_base=seed_base)
            assert completed == 0, (
                f"{policy} (seed_base {seed_base}) completed {completed} level(s) at step "
                f"{first} on a game with no win condition"
            )


def test_the_no_sprite_scratch_game_declares_no_sprites(scratch_root):
    """Zero `Sprite(` calls — the sprite floor's fail (official min 1)."""
    source = (scratch_root / "no_sprites" / "game.py").read_text(encoding="utf-8")
    assert "Sprite(" not in source
    game_cls, _solver = load_worker_classes(scratch_root / "no_sprites")
    probe = capture(game_cls)
    assert probe.records, "the empty board must still produce probe frames"
    assert probe.levels_completed == 0


def test_every_scratch_game_clears_the_loc_stub_detector(scratch_root):
    """The padding is deliberate: loc must not confound the layer under test."""
    for name in SCRATCH_GAMES:
        loc = _loc(scratch_root / name / "game.py")
        assert loc > 200, f"{name}: {loc} loc, under the reference's 200-line stub floor"


def test_the_six_deterministic_policies_complete_no_level_on_s6_seeded():
    """RAW proof of the contract's zero-completion claim, for the six that
    do not draw from an rng. `noop_like` is resolved exactly as the contract
    spells it: the id whose single probe changes the settled frame least,
    ties to the lowest id."""
    game_cls, _solver = load_worker_classes(SEEDED)
    ids = _playable_action_ids(_reset(_fresh_game(game_cls)))
    assert ids == [1, 2, 3, 4], ids
    assert _quietest_id(game_cls, ids) == 1, "a wall-blocked move is the quietest probe here"
    for policy in DETERMINISTIC_POLICIES:
        completed, first = _raw_line(game_cls, policy, steps=gate.ROBUSTNESS_STEPS)
        assert completed == 0, f"{policy} completed {completed} level(s) on s6_seeded (step {first})"


def test_uniform_random_beats_s6_seeded_level_one_at_the_default_policy_seed():
    """THE MEASURED CONFLICT (1). A uniform-random policy over s6_seeded's
    four ids clears level 1 at step 81 under `random.Random(6)` — which is
    `seed_base=0 + POLICIES.index("seeded_random")`, the gate's DEFAULT. The
    contract's "all seven complete zero levels on s6_seeded" is therefore not
    a property of the fixture; it is a property of A's rng indexing. Kept as
    a test so the evidence is checked in and cannot rot silently."""
    game_cls, _solver = load_worker_classes(SEEDED)
    rng = random.Random(RANDOM_SEED_THAT_BEATS_SEEDED)
    completed, _state, first = _drive(
        game_cls, lambda k, ids: rng.choice(ids), steps=gate.ROBUSTNESS_STEPS
    )
    assert completed >= 1, (
        "s6_seeded is no longer random-beatable at Random(6) — the conflict "
        "reported for B11 group 7 has moved; re-adjudicate the gate expectation"
    )
    assert first == RANDOM_BEATS_SEEDED_AT_STEP, first

    beaten = 0
    for seed in range(200):
        rng = random.Random(seed)
        hits, _state, _first = _drive(
            game_cls, lambda k, ids, r=rng: r.choice(ids), steps=gate.ROBUSTNESS_STEPS
        )
        beaten += 1 if hits else 0
    assert beaten > 0, "the base rate measured for the lead was 69/200 seeds"


def test_the_seeded_fixture_sits_under_the_loc_stub_floor():
    """THE MEASURED CONFLICT (2), pinned: 164 loc against a 200 reference."""
    assert _loc(SEEDED / "game.py") == SEEDED_LOC


# --------------------------------------------------------------------------- #
# group 1 — the transition table (architecture §4 is the authority)
# --------------------------------------------------------------------------- #


def test_the_frozen_names_exist_on_both_modules():
    missing_gate = [name for name in FROZEN_GATE_NAMES if getattr(gate, name, None) is None]
    missing_orch = [name for name in FROZEN_ORCH_NAMES if getattr(orch, name, None) is None]
    assert missing_gate == [], f"gen/s3_gate.py is missing {missing_gate}"
    assert missing_orch == [], f"gen/orchestrator.py is missing {missing_orch}"


def test_both_schema_versions_are_the_frozen_string():
    assert gate.SCHEMA_VERSION == "b11.1"
    assert orch.SCHEMA_VERSION == "b11.1"


def test_states_and_terminal_are_the_frozen_vocabulary():
    assert tuple(orch.STATES) == EXPECTED_STATES
    assert tuple(orch.TERMINAL) == EXPECTED_TERMINAL
    assert set(EXPECTED_TERMINAL) <= set(EXPECTED_STATES)


def test_the_ledger_and_report_names_are_the_frozen_filenames():
    assert orch.LEDGER_NAME == "ledger.jsonl"
    assert orch.BATCH_REPORT_NAME == "batch-report.json"


def test_the_reject_caps_are_the_architecture_numbers():
    """§3 S2b "bounded: 2 verifier rejects → escalate to S1"; §3 S2 "two
    consecutive spec rejects → the slot dies"."""
    assert orch.VERIFIER_REJECT_CAP_ESCALATE == 2
    assert orch.GREEN_CAP_DEATHS == 2


def test_transitions_are_exactly_the_section_4_edges():
    """State-to-state, edge for edge. The ONE admissible extra is the
    diagram's own birth arrow `[*] --> ideated`, which an append-only ledger
    has to be able to record (ambiguity M)."""
    edges = _edge_set(orch.TRANSITIONS)
    births = {edge for edge in edges if edge[0] not in EXPECTED_STATES}
    assert edges - births == set(SECTION4_EDGES), (
        "TRANSITIONS must be architecture §4's diagram, edge for edge.\n"
        f"missing: {sorted(set(SECTION4_EDGES) - edges)}\n"
        f"extra:   {sorted(edges - births - set(SECTION4_EDGES))}"
    )
    assert {edge[1] for edge in births} <= {"ideated"}, (
        f"only `[*] --> ideated` may leave the birth pseudo-state: {sorted(births)}"
    )


@pytest.mark.parametrize(("from_state", "to_state"), SECTION4_EDGES)
def test_every_section_4_edge_is_appended(tmp_path, from_state, to_state):
    ledger = tmp_path / "ledger.jsonl"
    line = orch.append_transition(
        ledger,
        slug="edge-probe",
        from_state=from_state,
        to_state=to_state,
        reason="the §4 edge",
        hashes={"spec": "a" * 8, "game": "b" * 8, "stage_input": "c" * 8},
        cost=None,
    )
    assert isinstance(line, Mapping), f"append_transition returned {type(line).__name__}"
    assert set(LEDGER_KEYS) <= set(line), f"line keys {sorted(line)} lack {LEDGER_KEYS}"
    assert (line["from"], line["to"]) == (from_state, to_state)
    on_disk = [json.loads(raw) for raw in ledger.read_text(encoding="utf-8").splitlines() if raw]
    assert len(on_disk) == 1, on_disk
    assert on_disk[0]["from"] == from_state and on_disk[0]["to"] == to_state


NON_EDGES = tuple(
    (src, dst)
    for src in EXPECTED_STATES
    for dst in EXPECTED_STATES
    if (src, dst) not in SECTION4_EDGES
)


@pytest.mark.parametrize(("from_state", "to_state"), NON_EDGES)
def test_every_non_edge_raises(tmp_path, from_state, to_state):
    ledger = tmp_path / "ledger.jsonl"
    exc = _raised(
        orch.append_transition,
        ledger,
        slug="edge-probe",
        from_state=from_state,
        to_state=to_state,
        reason="not a §4 edge",
        hashes={"spec": None, "game": None, "stage_input": None},
        cost=None,
    )
    assert exc is not None, f"{from_state} -> {to_state} is not a §4 edge and must raise"
    assert not ledger.exists() or ledger.read_text(encoding="utf-8").strip() == "", (
        "an illegal transition must not reach the append-only ledger"
    )


def test_an_unknown_state_raises():
    for pair in (("ideated", "nirvana"), ("nirvana", "ideated")):
        exc = _raised(
            orch.append_transition,
            Path("/dev/null"),
            slug="edge-probe",
            from_state=pair[0],
            to_state=pair[1],
            reason="unknown state",
            hashes={},
            cost=None,
        )
        assert exc is not None, f"{pair} names a state outside STATES and must raise"


def test_replay_ledger_reads_back_what_append_transition_wrote(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    spine = (
        (_birth_state(), "ideated"),  # the diagram's `[*] --> ideated`
        ("ideated", "spec_ok"),
        ("spec_ok", "implemented"),
        ("implemented", "verified"),
    )
    for from_state, to_state in spine:
        orch.append_transition(
            ledger,
            slug="replay-probe",
            from_state=from_state,
            to_state=to_state,
            reason="spine",
            hashes={"spec": "s", "game": "g", "stage_input": "i"},
            cost={"usd": 0.5, "tokens_in": 10, "tokens_out": 1},
        )
    table = orch.replay_ledger(ledger)
    assert set(table) == {"replay-probe"}
    row = table["replay-probe"]
    assert _state_of(row) == "verified"
    history = row.get("history") if isinstance(row, Mapping) else None
    assert history is not None, f"the replayed row carries no history: {row!r}"
    assert len(history) == len(spine), history


# --------------------------------------------------------------------------- #
# group 2 — a full fake-runner run: ideated -> played -> reviewed -> packaged
# --------------------------------------------------------------------------- #


@pytest.fixture
def happy_run(make_cfg, capsys):
    """One size-1 batch driven to the played stop with fake runners."""
    cfg, cfg_path = make_cfg("b11-happy")
    journal = _Journal()
    runners = _Runners(journal, cfg)
    report = orch.run_batch(cfg, runners=runners)
    captured = capsys.readouterr()
    return cfg, cfg_path, journal, runners, report, captured.out + captured.err


def test_the_runner_ctx_names_its_slug(happy_run):
    """Ambiguity B, isolated: every other multi-slug test depends on this."""
    _cfg, _path, journal, _runners, _report, _out = happy_run
    assert journal.contexts, "no stage runner was invoked at all"
    slugs = {_ctx_slug(ctx) for ctx in journal.contexts}
    assert None not in slugs, (
        "a runner ctx exposed no slug under any spelling tried by `_ctx_slug` "
        f"(ambiguity B): {journal.contexts[0]!r}"
    )


def test_a_fake_run_stops_at_played_for_review(happy_run):
    cfg, _path, journal, _runners, _report, _out = happy_run
    table = _table(cfg)
    assert len(table) == 1, f"batch.size 1 must produce one slot, got {table}"
    assert set(table.values()) == {"played"}, (
        f"the run must stop at `played` for the human: {table}\n"
        f"stages invoked: {journal.states()}"
    )


def test_the_run_up_to_played_walks_the_section_4_spine(happy_run):
    cfg, _path, _journal, _runners, _report, _out = happy_run
    slug = next(iter(_table(cfg)))
    spine = _spine(_ledger_lines(cfg), slug)
    assert spine == [
        (_birth_state(), "ideated"),  # `[*] --> ideated`
        ("ideated", "spec_ok"),
        ("spec_ok", "implemented"),
        ("implemented", "verified"),
        ("verified", "gated"),
        ("gated", "baselined"),
        ("baselined", "played"),
    ], spine


def test_every_ledger_line_carries_the_frozen_keys(happy_run):
    cfg, _path, _journal, _runners, _report, _out = happy_run
    lines = _ledger_lines(cfg)
    assert lines, "the ledger is empty"
    for line in lines:
        assert set(LEDGER_KEYS) <= set(line), f"line keys {sorted(line)}: {line}"
        assert line["ts"], "every transition is timestamped (ISO-8601 UTC)"
        assert isinstance(line["hashes"], Mapping), line["hashes"]
        assert set(HASH_KEYS) <= set(line["hashes"]), line["hashes"]
        if line["cost"] is not None:
            assert set(COST_KEYS) <= set(line["cost"]), line["cost"]


def test_a_stage_that_reports_no_cost_lands_as_null(happy_run):
    """"NEVER invented — read off stage reports where they exist"."""
    cfg, _path, _journal, _runners, _report, _out = happy_run
    by_state = {line["to"]: line for line in _ledger_lines(cfg)}
    for state in ("gated", "baselined"):
        assert by_state[state]["cost"] is None, (
            f"the pure-code stage that produced `{state}` reported no cost; the "
            f"ledger invented one: {by_state[state]['cost']}"
        )
    for state in ("spec_ok", "implemented"):
        assert by_state[state]["cost"] is not None, by_state[state]


def test_the_played_stop_names_the_review_command(happy_run):
    cfg, _path, _journal, _runners, report, out = happy_run
    slug = next(iter(_table(cfg)))
    haystack = out + _text(report)
    if _report_path(cfg).is_file():
        haystack += _report_path(cfg).read_text(encoding="utf-8")
    assert "--review" in haystack, (
        "the played stop must name the `--review` command (contract §Review "
        f"checkpoint). Captured output + report:\n{haystack[:2000]}"
    )
    assert slug in haystack, "…and the slug the human has to decide about"


def test_review_accept_carries_the_slot_to_packaged(happy_run):
    cfg, _path, _journal, runners, _report, _out = happy_run
    slug = next(iter(_table(cfg)))
    orch.run_batch(cfg, runners=runners, review=(slug, "accept"))
    assert _table(cfg) == {slug: "packaged"}, _table(cfg)
    spine = _spine(_ledger_lines(cfg), slug)
    assert spine[-2:] == [("played", "reviewed"), ("reviewed", "packaged")], spine


def test_costs_are_summed_into_the_batch_report(happy_run):
    cfg, _path, journal, runners, _report, _out = happy_run
    slug = next(iter(_table(cfg)))
    report = orch.run_batch(cfg, runners=runners, review=(slug, "accept"))
    totals = journal.total_cost()
    assert totals["tokens_in"] > 0, "the fakes reported costs; the journal lost them"
    for key in COST_KEYS:
        assert _has_number(report, totals[key]), (
            f"the batch report carries no summed `{key}` = {totals[key]} "
            f"(ambiguity D — the key name is not frozen, the TOTAL is).\n"
            f"report:\n{_text(report)}"
        )
    assert _report_path(cfg).is_file(), f"no {orch.BATCH_REPORT_NAME} on disk"


def test_the_batch_report_records_the_terminal_state_per_slug(happy_run):
    cfg, _path, _journal, runners, _report, _out = happy_run
    slug = next(iter(_table(cfg)))
    report = orch.run_batch(cfg, runners=runners, review=(slug, "accept"))
    text = _text(report)
    assert slug in text and "packaged" in text, text
    on_disk = json.loads(_report_path(cfg).read_text(encoding="utf-8"))
    assert slug in _text(on_disk) and "packaged" in _text(on_disk)


def test_batch_dir_is_the_out_batches_path(make_cfg):
    cfg, _path = make_cfg("b11-where")
    path = Path(orch.batch_dir(cfg))
    assert path.name == "b11-where", path
    assert path.parent.name == "batches" and path.parent.parent.name == "out", path


# --------------------------------------------------------------------------- #
# group 3 — the kill/resume sweep (the ledger IS the resume state, §4)
# --------------------------------------------------------------------------- #


@dataclass
class _SweepRow:
    """One kill point's evidence."""

    kill_after: int
    killed_calls: int
    resumed_calls: int
    table: dict
    replayed_clean: bool


@pytest.fixture(scope="module")
def kill_sweep(tmp_path_factory):
    """Kill after EVERY stage boundary, resume, and record what happened.

    Module scoped: the sweep drives ~2N batches and all three group-3 tests
    read the same evidence. Each kill point gets its own batch id, so the runs
    never share a ledger. The path patching is undone before the fixture
    RETURNS — a module-scoped patch that outlived the sweep would silently
    redirect every later test in this file.
    """
    root = tmp_path_factory.mktemp("b11sweep")

    def cfg_for(batch_id: str) -> dict:
        cfg = copy.deepcopy(_CFG)
        cfg["batch"]["id"] = batch_id
        cfg["batch"]["size"] = 1
        return cfg

    with pytest.MonkeyPatch.context() as patch:
        for name, value in list(vars(orch).items()):
            if name.startswith("__") or not isinstance(value, Path):
                continue
            try:
                relative = value.resolve().relative_to(REPO_ROOT)
            except ValueError:
                continue
            patch.setattr(orch, name, root / relative)
        patch.setattr("gen.config.REPO_ROOT", root)

        # the unkilled baseline
        clean_cfg = cfg_for("b11-sweep-clean")
        clean_journal = _Journal()
        _advance(clean_cfg, _Runners(clean_journal, clean_cfg))
        clean_table = _table(clean_cfg)
        clean_calls = len(clean_journal.calls)
        assert clean_calls > 0, "the clean run invoked no stage at all"
        assert set(clean_table.values()) <= set(EXPECTED_TERMINAL), clean_table

        rows = []
        for kill_after in range(clean_calls):
            cfg = cfg_for(f"b11-sweep-k{kill_after}")
            killed = _Journal(kill_after=kill_after)
            runners = _Runners(killed, cfg)
            with pytest.raises(KeyboardInterrupt):
                _advance(cfg, runners)
            resumed = _Journal()
            _advance(cfg, _Runners(resumed, cfg))
            table = _table(cfg)
            replayed = orch.replay_ledger(_ledger_path(cfg))
            rows.append(
                _SweepRow(
                    kill_after=kill_after,
                    killed_calls=len(killed.calls),
                    resumed_calls=len(resumed.calls),
                    table=table,
                    replayed_clean=isinstance(replayed, Mapping) and set(replayed) == set(table),
                )
            )
        return {
            "clean_table": clean_table,
            "clean_calls": clean_calls,
            "clean_states": clean_journal.states(),
            "stage_names": _default_stage_names(),
            "rows": rows,
        }


def test_kill_after_every_stage_boundary_reaches_the_same_terminal_state(kill_sweep):
    """Slugs are derived from the batch id, so each kill point has its own
    slug names; what must be identical is the terminal TABLE — one slot per
    batch, in the same terminal state the unkilled run reached."""
    expected = sorted(kill_sweep["clean_table"].values())
    for row in kill_sweep["rows"]:
        assert sorted(row.table.values()) == expected, (
            f"kill after stage call #{row.kill_after} resumed to {row.table}, "
            f"the unkilled run reached {kill_sweep['clean_table']}"
        )
        assert len(row.table) == len(kill_sweep["clean_table"]), row.table
        assert set(row.table.values()) <= set(EXPECTED_TERMINAL), row.table


def test_a_resume_never_reinvokes_a_completed_stage(kill_sweep):
    """The invocation count is the proof: killed calls + resumed calls must
    equal the unkilled run's calls exactly — one more means a completed stage
    ran twice, one fewer means work was dropped."""
    total = kill_sweep["clean_calls"]
    for row in kill_sweep["rows"]:
        assert row.killed_calls == row.kill_after, (
            f"the kill harness recorded {row.killed_calls} calls before killing at "
            f"#{row.kill_after}"
        )
        assert row.killed_calls + row.resumed_calls == total, (
            f"kill after #{row.kill_after}: {row.killed_calls} + {row.resumed_calls} "
            f"stage invocations != {total} — a completed stage was re-invoked "
            "(or work was dropped) on resume"
        )


def test_the_resumed_ledger_replays_clean(kill_sweep):
    for row in kill_sweep["rows"]:
        assert row.replayed_clean, (
            f"kill after #{row.kill_after}: replay_ledger does not reproduce the "
            f"final table {row.table}"
        )


# --------------------------------------------------------------------------- #
# group 4 — input hashes: a changed stage input re-queues exactly that slug
# --------------------------------------------------------------------------- #


@pytest.fixture
def two_slot_run(make_cfg):
    """A size-2 batch parked at the played stop, plus its journal."""
    cfg, _path = make_cfg("b11-hashes", size=2)
    journal = _Journal()
    runners = _Runners(journal, cfg)
    orch.run_batch(cfg, runners=runners)
    table = _table(cfg)
    assert len(table) == 2, f"batch.size 2 must produce two slots, got {table}"
    assert set(table.values()) == {"played"}, table
    return cfg, journal, runners


def test_a_clean_rerun_invokes_no_stage(two_slot_run):
    """"a completed stage with unchanged inputs never re-runs" (§4)."""
    cfg, _journal, _runners = two_slot_run
    again = _Journal()
    orch.run_batch(cfg, runners=_Runners(again, cfg))
    assert again.calls == [], f"an unchanged re-run re-invoked {again.states()}"
    assert set(_table(cfg).values()) == {"played"}, _table(cfg)


def test_mutating_one_slugs_stage_input_requeues_exactly_that_slug(two_slot_run):
    """§2's provenance chain as the resume mechanism: the changed slug re-queues
    at the stage whose input moved, and the untouched slug is left alone."""
    cfg, journal, _runners = two_slot_run
    table = _table(cfg)
    target, other = sorted(table)
    original = [call.stage for call in journal.calls if call.slug == target]
    games = _slot_files(cfg, journal, target, "worker/game.py")
    assert games, f"the fake S2 stage wrote no worker/game.py for {target}"
    for path in games:
        path.write_text(
            path.read_text(encoding="utf-8") + "\n# the game changed: new game_hash\n",
            encoding="utf-8",
        )

    again = _Journal()
    orch.run_batch(cfg, runners=_Runners(again, cfg))
    assert again.calls, "a changed stage input must re-queue its slug (§2 provenance chain)"
    assert again.count(slug=other) == 0, (
        f"{other} was re-queued although nothing of its changed: {again.states(other)}"
    )
    # "re-queues FROM that stage": the re-run is a CONTIGUOUS SUFFIX of the
    # slug's original stage sequence — it picks the pipeline up at the stage
    # the change invalidated and runs forward from there. Which stage that is
    # depends on the stage-input map, so the suffix property is the
    # implementation-independent form of the contract's claim.
    replay = [call.stage for call in again.calls if call.slug == target]
    assert replay == original[len(original) - len(replay):], (
        "the re-queue must resume the pipeline at the invalidated stage and run "
        f"forward: original {original}, re-run {replay}"
    )
    assert _table(cfg)[target] == "played", _table(cfg)


def test_input_hashes_change_when_the_spec_changes(two_slot_run):
    """The frozen `input_hashes(slot_ctx)`, driven with a ctx the orchestrator
    itself handed a runner (ambiguity B again)."""
    cfg, journal, _runners = two_slot_run
    table = _table(cfg)
    target = min(table)
    # the LAST ctx for the slug: by then every §2 artifact the hashes cover
    # is on disk (the first ctx is the pre-idea one, hashes empty by design).
    ctx = [c for c in journal.contexts if _ctx_slug(c) == target][-1]
    before = orch.input_hashes(ctx)
    assert isinstance(before, Mapping), f"input_hashes returned {type(before).__name__}"
    assert set(HASH_KEYS) <= set(before), (
        f"input_hashes keys {sorted(before)} must cover the ledger's {HASH_KEYS}"
    )
    assert before["spec"] and before["game"], (
        "a slot parked at `played` has a spec and a worker on disk; the resume "
        f"hashes must see them: {before}"
    )
    for path in _slot_files(cfg, journal, target, "spec.yaml"):
        path.write_text(path.read_text(encoding="utf-8") + "\n# mutated\n", encoding="utf-8")
    after = orch.input_hashes(ctx)
    assert after["spec"] != before["spec"], (
        f"the spec hash did not move after spec.yaml changed: {before} -> {after}"
    )
    assert after["game"] == before["game"], "only the spec changed"


# --------------------------------------------------------------------------- #
# group 5 — the reject loops and the attrition abort
# --------------------------------------------------------------------------- #


def test_a_lint_kill_routes_through_respec_and_resamples(make_cfg):
    """§4: `ideated --> respec: lint kill`, `respec --> ideated: re-sample`."""
    cfg, _path = make_cfg("b11-lint")
    journal = _Journal()
    runners = _Runners(
        journal,
        cfg,
        outcomes={"ideated": _Outcome("respec", "lint kill: unknown term", times=1)},
    )
    _advance(cfg, runners)
    slug = next(iter(_table(cfg)))
    spine = _spine(_ledger_lines(cfg), slug)
    assert spine[:4] == [
        (_birth_state(), "ideated"),
        ("ideated", "respec"),
        ("respec", "ideated"),
        ("ideated", "spec_ok"),
    ], spine
    kill = next(line for line in _ledger_lines(cfg) if line["to"] == "respec")
    assert "lint" in str(kill["reason"]).lower(), kill
    assert _table(cfg)[slug] == "packaged", _table(cfg)


def test_two_verifier_rejects_escalate_to_respec(make_cfg):
    """§3 S2b: "bounded: 2 verifier rejects → escalate to S1"; the §4 edge is
    `implemented --> spec_ok`, so the escalation can only be in the reason
    (ambiguity F)."""
    cfg, _path = make_cfg("b11-verifier")
    journal = _Journal()
    runners = _Runners(
        journal,
        cfg,
        outcomes={"implemented": _Outcome("spec_ok", "verifier reject: dead mechanic", times=2)},
    )
    _advance(cfg, runners)
    slug = next(iter(_table(cfg)))
    lines = _ledger_lines(cfg)
    rejects = [line for line in lines if (line["from"], line["to"]) == ("implemented", "spec_ok")]
    assert len(rejects) == orch.VERIFIER_REJECT_CAP_ESCALATE, (
        f"expected {orch.VERIFIER_REJECT_CAP_ESCALATE} verifier rejects, got {len(rejects)}: "
        f"{_spine(lines, slug)}"
    )
    second = str(rejects[-1]["reason"]).lower()
    assert second != str(rejects[0]["reason"]).lower(), (
        "the reject that reaches the cap must not read like the first one "
        f"(both: {second!r})"
    )
    assert "respec" in second or "escalat" in second, (
        f"at VERIFIER_REJECT_CAP_ESCALATE the reason must route respec: {second!r}"
    )
    row = orch.replay_ledger(_ledger_path(cfg))[slug]
    assert orch.VERIFIER_REJECT_CAP_ESCALATE in [
        value for value in row.values() if isinstance(value, int) and not isinstance(value, bool)
    ] or "reject" in _text(row).lower(), (
        f"the replayed row keeps no reject bookkeeping: {_text(row)}"
    )


def test_two_green_loop_failures_kill_the_slot(make_cfg):
    """§4: `spec_ok --> dead: green-attempts cap ×2` (GREEN_CAP_DEATHS)."""
    cfg, _path = make_cfg("b11-green", max_attrition=1.0)
    journal = _Journal()
    runners = _Runners(
        journal,
        cfg,
        outcomes={
            "spec_ok": _Outcome(
                "spec_ok", "green-attempts cap reached", times=orch.GREEN_CAP_DEATHS
            )
        },
    )
    _advance(cfg, runners)
    table = _table(cfg)
    slug = next(iter(table))
    assert table[slug] == "dead", f"two green-loop failures must kill the slot: {table}"
    spine = _spine(_ledger_lines(cfg), slug)
    assert ("spec_ok", "dead") in spine, spine
    death = next(line for line in _ledger_lines(cfg) if line["to"] == "dead")
    assert "green" in str(death["reason"]).lower(), death


def test_a_battery_crash_returns_the_slot_to_implemented(make_cfg):
    """§4: `played --> implemented: crash` — "wire exactly the diagram"."""
    cfg, _path = make_cfg("b11-crash")
    journal = _Journal()
    runners = _Runners(
        journal,
        cfg,
        outcomes={"baselined": _Outcome("implemented", "battery crash: engine fault", times=1)},
    )
    _advance(cfg, runners)
    slug = next(iter(_table(cfg)))
    spine = _spine(_ledger_lines(cfg), slug)
    assert ("played", "implemented") in spine, (
        "a battery crash re-implements THROUGH played — the diagram has no "
        f"baselined -> implemented edge. spine: {spine}"
    )
    crash = next(line for line in _ledger_lines(cfg) if line["to"] == "implemented" and line["from"] == "played")
    assert "crash" in str(crash["reason"]).lower(), crash
    assert spine.count(("baselined", "played")) >= 2, spine
    assert _table(cfg)[slug] == "packaged", _table(cfg)


def test_attrition_aborts_the_batch_at_size_one(make_cfg):
    """§4 kill criteria: dead+pulled over `orchestrator.max_attrition` stops
    the batch. At size 1 one death is 100% against the pilot's 30%."""
    cfg, _path = make_cfg("b11-attrition")
    assert cfg["orchestrator"]["max_attrition"] == 0.30, cfg["orchestrator"]
    journal = _Journal()
    runners = _Runners(
        journal,
        cfg,
        outcomes={
            "spec_ok": _Outcome(
                "spec_ok", "green-attempts cap reached", times=orch.GREEN_CAP_DEATHS
            )
        },
    )
    report = _advance(cfg, runners)
    table = _table(cfg)
    assert set(table.values()) == {"dead"}, table
    haystack = _text(report)
    if _report_path(cfg).is_file():
        haystack += _report_path(cfg).read_text(encoding="utf-8")
    assert "attrition" in haystack.lower(), (
        f"the batch report must record the attrition abort:\n{haystack[:2000]}"
    )
    assert "abort" in haystack.lower() or "stopped" in haystack.lower(), haystack[:2000]


# --------------------------------------------------------------------------- #
# group 6 — the human-only review checkpoint
# --------------------------------------------------------------------------- #


def test_no_run_passes_played_by_itself(make_cfg):
    """"No other path out of `played` exists" — three runs, still played."""
    cfg, _path = make_cfg("b11-review-none")
    journal = _Journal()
    runners = _Runners(journal, cfg)
    for _ in range(3):
        orch.run_batch(cfg, runners=runners)
    table = _table(cfg)
    assert set(table.values()) == {"played"}, table
    spine = _spine(_ledger_lines(cfg))
    assert ("played", "reviewed") not in spine, spine
    assert ("played", "implemented") not in spine, spine


def test_review_accept_appends_played_to_reviewed_and_continues(make_cfg):
    cfg, _path = make_cfg("b11-review-accept")
    journal = _Journal()
    runners = _Runners(journal, cfg)
    orch.run_batch(cfg, runners=runners)
    slug = next(iter(_table(cfg)))
    orch.run_batch(cfg, runners=runners, review=(slug, "accept"))
    spine = _spine(_ledger_lines(cfg), slug)
    assert ("played", "reviewed") in spine, spine
    assert _table(cfg)[slug] == "packaged", _table(cfg)
    accept = next(line for line in _ledger_lines(cfg) if line["to"] == "reviewed")
    assert "accept" in str(accept["reason"]).lower() or "human" in str(accept["reason"]).lower()


def test_review_pull_terminalizes_the_slot(make_cfg):
    cfg, _path = make_cfg("b11-review-pull", max_attrition=1.0)
    journal = _Journal()
    runners = _Runners(journal, cfg)
    orch.run_batch(cfg, runners=runners)
    slug = next(iter(_table(cfg)))
    before = len(journal.calls)
    orch.run_batch(cfg, runners=runners, review=(slug, "pull"))
    table = _table(cfg)
    assert table[slug] == "pulled", table
    spine = _spine(_ledger_lines(cfg), slug)
    assert ("played", "reviewed") in spine and ("reviewed", "pulled") in spine, spine
    assert ("reviewed", "packaged") not in spine, spine
    orch.run_batch(cfg, runners=runners)
    assert _table(cfg)[slug] == "pulled", "a terminal slot must not be re-queued"
    assert len(journal.calls) == before, (
        f"a pulled slot re-invoked stages: {journal.states(slug)[before:]}"
    )


def test_an_unknown_review_verb_raises(make_cfg):
    cfg, _path = make_cfg("b11-review-verb")
    journal = _Journal()
    runners = _Runners(journal, cfg)
    orch.run_batch(cfg, runners=runners)
    slug = next(iter(_table(cfg)))
    exc = _raised(orch.run_batch, cfg, runners=runners, review=(slug, "maybe"))
    assert exc is not None, "only `accept` and `pull` leave `played`"
    assert _table(cfg)[slug] == "played", _table(cfg)


# --------------------------------------------------------------------------- #
# group 7 — the gate on real games (engine-driven)
# --------------------------------------------------------------------------- #


def test_the_policy_tuple_is_the_documented_seven():
    """re-arc-3-source.md:51 — the documented list, in order (D14)."""
    assert tuple(gate.POLICIES) == EXPECTED_POLICIES
    assert gate.ROBUSTNESS_STEPS == 120, "the documented budget: 120 steps each"
    assert gate.ACCEPTANCE_NAME == "acceptance-report.json"
    assert gate.ROBUSTNESS_NAME == "robustness-report.json"
    assert gate.GATE_SUFFIX == ".gate"


@pytest.fixture(scope="session")
def seeded_robustness(seeded_staged):
    worker, _cap, _metadata = seeded_staged
    return gate.robustness(worker)


def test_robustness_reports_a_row_for_each_of_the_seven_policies(seeded_robustness):
    for policy in EXPECTED_POLICIES:
        row = _policy_row(seeded_robustness, policy)
        assert isinstance(row, Mapping), f"{policy}: {row!r}"
    text = _text(seeded_robustness)
    assert str(gate.ROBUSTNESS_STEPS) in text, (
        f"the report must record the {gate.ROBUSTNESS_STEPS}-step budget it drove"
    )


def test_the_six_deterministic_policies_complete_no_level_through_the_gate(seeded_robustness):
    """The half of the contract's claim that IS true of the fixture (group 0
    proves it raw)."""
    beaten = {
        policy: _row_completions(_policy_row(seeded_robustness, policy))
        for policy in DETERMINISTIC_POLICIES
    }
    assert set(beaten.values()) == {0}, (
        f"a deterministic degenerate policy completed a level on s6_seeded: {beaten}"
    )


def test_the_robustness_verdict_follows_the_gate_rule_on_s6_seeded(seeded_robustness):
    """THE MEASURED CONFLICT (1) — the contested outcome is NOT asserted here.
    What is asserted is the GATE RULE itself: the verdict is `pass` iff every
    policy completed zero levels, and a policy that completed one is named
    with its level and step."""
    completions = {
        policy: _row_completions(_policy_row(seeded_robustness, policy))
        for policy in EXPECTED_POLICIES
    }
    verdict = _verdict(seeded_robustness)
    clean = set(completions.values()) == {0}
    assert (verdict == "pass") is clean, (
        f"verdict {verdict!r} contradicts the rows {completions} — the gate rule is "
        "`pass` iff all seven policies complete zero levels"
    )
    if not clean:
        text = _text(seeded_robustness)
        for policy, hits in completions.items():
            if hits:
                assert policy in text, policy
                assert "level" in text.lower() and "step" in text.lower(), (
                    "a policy that beat a level must be reported with its level "
                    f"and step: {text[:2000]}"
                )


def test_robustness_fails_loudly_on_the_trivial_scratch_game(scratch_capture):
    """One action wins level 1, so all seven policies must beat it."""
    worker, _cap = scratch_capture("trivial")
    report = gate.robustness(worker)
    assert _verdict(report) != "pass", _text(report)
    completions = {
        policy: _row_completions(_policy_row(report, policy)) for policy in EXPECTED_POLICIES
    }
    assert min(completions.values()) >= 1, (
        f"every policy wins this game in one action; the gate saw {completions}"
    )
    text = _text(report)
    assert "seeded_random" in text, "the report must name the policy that won"
    assert "level" in text.lower() and "step" in text.lower(), (
        f"…with the level and the step it won at:\n{text[:2000]}"
    )


def test_robustness_is_deterministic(scratch_capture):
    worker, _cap = scratch_capture("unwinnable")
    first = gate.robustness(worker, seed_base=3)
    second = gate.robustness(worker, seed_base=3)
    assert _text(first) == _text(second), "same inputs, same robustness report"


def test_structural_floors_pass_on_s6_seeded(seeded_staged):
    """6 levels, sprites, and a non-monotonic staircase from the REAL S4
    metadata run in-test."""
    worker, cap, metadata = seeded_staged
    report = gate.structural_acceptance(worker, cap)
    rows = _rows(report)
    assert rows, f"structural_acceptance produced no CheckResult rows:\n{_text(report)}"

    sprites = _one_row(report, ("sprite",))
    assert sprites["status"] == "pass", sprites
    levels = _one_row(report, ("level",), exclude=("descent", "monoton", "staircase", "random"))
    assert levels["status"] == "pass", levels
    assert str(SEEDED_LEVELS) in _text(levels), (
        f"the levels row must evidence the {SEEDED_LEVELS} authored levels: {levels}"
    )
    descent = _one_row(report, ("descent", "monoton", "staircase"))
    assert descent["status"] == "pass", (
        "the staircase floor must read the in-test S4 metadata "
        f"(baseline_actions={metadata['baseline_actions']}): {descent}"
    )


def test_structural_rows_are_check_result_shaped(seeded_staged):
    worker, cap, _metadata = seeded_staged
    report = gate.structural_acceptance(worker, cap)
    for row in _rows(report):
        assert {"check_id", "leg", "status", "evidence", "note"} <= set(row), row
        assert row["status"] in STATUSES, f"{row['check_id']}: {row['status']!r}"
        assert row["leg"] == "gate", f"{row['check_id']}: leg {row['leg']!r}"


def test_structural_acceptance_on_s6_seeded_has_no_unexplained_fail(
    seeded_staged, seeded_robustness
):
    """The contract's "s6_seeded passes". Two measured tensions can make this
    fail, and both are diagnoses, not surprises:
      * the loc floor — s6_seeded/game.py is 164 non-blank non-comment lines
        against the reference's 200, which the reference applies as a WARN
        ("a stub detector, not a measure"), never a FAIL;
      * random-fails-L1 — a uniform-random policy clears level 1 of this
        fixture at Random(6) (group 0), so a truthfully-consumed row fails.
    """
    worker, cap, _metadata = seeded_staged
    report = gate.structural_acceptance(worker, cap)
    failed = [row["check_id"] for row in _failed_rows(report)]
    assert failed == [], (
        f"structural floors failed on the §7 reference fixture: {failed}\n"
        f"loc={_loc(SEEDED / 'game.py')} (reference warns under 200); "
        f"robustness verdict={_verdict(seeded_robustness)}\n{_text(report)}"
    )


def test_the_random_floor_agrees_with_the_robustness_evidence(
    seeded_staged, seeded_robustness
):
    """Ambiguity H: the row may be deferred at structural time (structural runs
    FIRST), but a computed verdict must match what the seeded_random row saw."""
    worker, cap, _metadata = seeded_staged
    report = gate.structural_acceptance(worker, cap)
    row = _one_row(report, ("random",))
    assert row["status"] in STATUSES, row
    beaten = _row_completions(_policy_row(seeded_robustness, "seeded_random")) > 0
    if row["status"] in ("pass", "fail"):
        assert (row["status"] == "fail") is beaten, (
            f"the random-fails-L1 floor says {row['status']!r} while the robustness "
            f"seeded_random row completed {'a level' if beaten else 'nothing'}"
        )


def test_the_levels_floor_is_premise_honest_on_the_two_level_toy():
    """The B1 toy has 2 levels against the §7 curriculum's 6-10. The contract:
    "premise-honest for legacy fixtures: recorded, not failed" — what it must
    never be is a silent pass."""
    game_cls, solver_cls = load_worker_classes(TOY)
    report = gate.structural_acceptance(TOY, capture(game_cls, solver_cls))
    row = _one_row(report, ("level",), exclude=("descent", "monoton", "staircase", "random"))
    assert row["status"] in STATUSES, row
    assert row["status"] != "pass", (
        f"{TOY_LEVELS} levels cannot pass the 6-10 curriculum floor silently: {row}"
    )
    assert row["status"] != "skipped", f"a skipped floor records nothing: {row}"
    assert str(TOY_LEVELS) in _text(row), f"the row must record the level count: {row}"


def test_the_descent_floor_is_premise_not_met_without_s4_metadata(scratch_capture):
    """"…when S4 metadata is present, else premise-not-met"."""
    worker, cap = scratch_capture("unwinnable")
    assert not (worker / METADATA_NAME).exists()
    assert not (worker.parent / (worker.name + S4_SUFFIX)).exists()
    report = gate.structural_acceptance(worker, cap)
    row = _one_row(report, ("descent", "monoton", "staircase"))
    assert row["status"] == "premise-not-met", (
        f"no baselines exist, so the staircase floor has no premise: {row}"
    )


def test_the_sprite_floor_fails_on_the_empty_board(scratch_capture):
    """`sprite_calls_fail_at` 0 — "official min 1, median 43; no game has zero"."""
    worker, cap = scratch_capture("no_sprites")
    report = gate.structural_acceptance(worker, cap)
    row = _one_row(report, ("sprite",))
    assert row["status"] == "fail", row


# --------------------------------------------------------------------------- #
# group 8 — the 25-official calibration battery (both layers)
# --------------------------------------------------------------------------- #


@official_param
def test_official_structural_floors_are_clean(official_capture, official: Official):
    """"Floors 25/25 clean (they were calibrated so)" — the floors come from
    the officials' own distribution, so a fail here is either a mis-adapted
    threshold or a corpus that moved."""
    worker_dir = official.py_path.parent
    report = gate.structural_acceptance(worker_dir, official_capture(official))
    failed = [row["check_id"] for row in _failed_rows(report)]
    assert failed == [], (
        f"{official.game_id} ({official.py_path}) fails {failed}; an exception must be "
        f"pinned with evidence (KNOWN_OFFICIAL_FAILS-style), not silent:\n{_text(report)}"
    )


@official_param
def test_official_survives_all_seven_degenerate_policies(official: Official):
    """"0 of 25 official games fall to a uniform-random policy" (the calibrated
    `random_beats_l1_fails`), extended by architecture §3 to all seven.

    The contract's escape hatch is a PINNED, evidence-cited exception (the B7
    `KNOWN_OFFICIAL_FAILS` pattern): an official outside the pin map must be
    clean, and one inside must fail EXACTLY its pinned policy/level/step.
    Drift in either direction breaks here; the pin itself is replayed raw by
    `test_every_pinned_official_exception_replays_raw`.
    """
    worker_dir = official.py_path.parent
    report = gate.robustness(worker_dir)
    completions = {
        policy: _row_completions(_policy_row(report, policy)) for policy in EXPECTED_POLICIES
    }
    beaten = {policy: hits for policy, hits in completions.items() if hits}
    pinned = _pins().get(official.slug)
    if pinned is None:
        assert beaten == {}, (
            f"{official.game_id}: degenerate policies completed levels {beaten} — "
            f"adjudicate at source with evidence before pinning:\n{_text(report)}"
        )
        assert _verdict(report) == "pass", _text(report)
        return

    assert set(beaten) == {pinned["policy"]}, (
        f"{official.game_id} is pinned for {pinned['policy']!r} only, but {sorted(beaten)} "
        f"completed levels:\n{_text(report)}"
    )
    failures = report.get("failures")
    assert isinstance(failures, list) and len(failures) == 1, (
        f"the pinned exception must be reported once, with its level and step: {failures}"
    )
    failure = failures[0]
    assert (failure["policy"], failure["level"], failure["step"]) == (
        pinned["policy"],
        pinned["level"],
        pinned["step"],
    ), f"the pinned exception drifted: pinned {pinned}, measured {failure}"
    assert str(pinned.get("citation", "")).strip(), "a pin without a canon citation is not adjudicated"
    assert str(pinned.get("evidence_note", "")).strip(), "a pin without evidence is not adjudicated"
    assert gate.is_pinned_official_fail(official.slug, failure) is True, failure


def _pins() -> Mapping:
    """A's evidence-pinned official exceptions (contract: "KNOWN_OFFICIAL_FAILS-style")."""
    pins = getattr(gate, "KNOWN_OFFICIAL_FAILS", None)
    assert isinstance(pins, Mapping), (
        "the gate must expose its pinned official exceptions as a mapping "
        f"(got {type(pins).__name__}) — an unpinned exception is not adjudicated"
    )
    return pins


def test_pinned_official_exceptions_are_named_officials_and_policies():
    for slug, pin in _pins().items():
        assert slug in {official.slug for official in _OFFICIALS}, slug
        assert pin["policy"] in EXPECTED_POLICIES, pin
        assert int(pin["level"]) >= 1 and int(pin["step"]) >= 1, pin


def test_every_pinned_official_exception_replays_raw(official_class):
    """The pin is not taken on trust: each one is re-driven from the contract's
    own policy semantics (`_raw_line`), with no gate code in the loop."""
    for slug, pin in _pins().items():
        official = next(o for o in _OFFICIALS if o.slug == slug)
        game_cls = official_class(official)
        completed, first = _raw_line(
            game_cls, pin["policy"], steps=gate.ROBUSTNESS_STEPS
        )
        assert completed >= int(pin["level"]), (
            f"{slug}: the pinned {pin['policy']} exception does not reproduce raw "
            f"(completed {completed}, pinned level {pin['level']})"
        )
        assert first == int(pin["step"]), (
            f"{slug}: pinned at step {pin['step']}, raw replay completed level 1 at {first}"
        )
        # …and the OTHER six policies stay clean on that same official.
        for policy in EXPECTED_POLICIES:
            if policy == pin["policy"]:
                continue
            hits, _at = _raw_line(game_cls, policy, steps=gate.ROBUSTNESS_STEPS)
            assert hits == 0, f"{slug}: {policy} also completes {hits} level(s) — the pin is too narrow"


# --------------------------------------------------------------------------- #
# group 9 — merged_gate: the §3 layer order, the short circuit, pending
# --------------------------------------------------------------------------- #


def _layers(result) -> Mapping:
    assert isinstance(result, Mapping), f"merged_gate returned {type(result).__name__}"
    layers = result.get("layers")
    assert isinstance(layers, Mapping), f"merged_gate result has no `layers`:\n{_text(result)}"
    return layers


def _layer_status(layers: Mapping, name: str) -> str:
    layer = layers.get(name)
    assert layer is not None, f"no `{name}` layer in {sorted(layers)}"
    if isinstance(layer, Mapping):
        for key in ("status", "verdict"):
            if key in layer:
                return str(layer[key])
        raise AssertionError(f"the `{name}` layer carries no status:\n{_text(layer)}")
    return str(layer)


def test_merged_gate_has_the_four_layers_and_the_frozen_keys(scratch_capture, tmp_path):
    worker, cap = scratch_capture("unwinnable")
    result = gate.merged_gate(
        worker,
        cap,
        verifier_report=CLEAN_VERIFIER,
        battery_report=COMPLETE_BATTERY,
        out_dir=tmp_path / "gate",
    )
    assert {"schema_version", "layers", "verdict", "short_circuited_at", "paths"} <= set(
        result
    ), sorted(result)
    assert result["schema_version"] == gate.SCHEMA_VERSION
    assert {"structural", "robustness", "verifier", "battery"} <= set(_layers(result))
    assert result["verdict"] in ("gated", "rejected", "pending"), result["verdict"]


def test_a_clean_run_of_all_four_layers_is_gated(scratch_capture, tmp_path):
    """§3: "a game is `gated` only when all four are green"."""
    worker, cap = scratch_capture("unwinnable")
    result = gate.merged_gate(
        worker,
        cap,
        verifier_report=CLEAN_VERIFIER,
        battery_report=COMPLETE_BATTERY,
        out_dir=tmp_path / "gate",
    )
    assert result["verdict"] == "gated", (
        "structurally sound, unwinnable by every degenerate policy, clean verifier, "
        f"complete battery:\n{_text(result)}"
    )
    assert not result["short_circuited_at"], result["short_circuited_at"]


def test_a_structural_failure_short_circuits_before_robustness(
    scratch_capture, monkeypatch, tmp_path
):
    """Layer 1 is milliseconds and runs first; layer 2 must not run at all.
    The control call in the same test proves the patch point is live, so a
    zero count cannot be an artefact of patching the wrong name."""
    real_robustness = gate.robustness
    calls: list[Path] = []

    def counting(worker_dir, **kwargs):
        calls.append(Path(worker_dir))
        return real_robustness(worker_dir, **kwargs)

    monkeypatch.setattr(gate, "robustness", counting)

    bad_worker, bad_cap = scratch_capture("no_sprites")
    result = gate.merged_gate(
        bad_worker,
        bad_cap,
        verifier_report=CLEAN_VERIFIER,
        battery_report=COMPLETE_BATTERY,
        out_dir=tmp_path / "bad",
    )
    assert calls == [], f"robustness ran after a structural failure: {calls}"
    assert result["verdict"] == "rejected", _text(result)
    assert "structural" in str(result["short_circuited_at"]), result["short_circuited_at"]

    good_worker, good_cap = scratch_capture("unwinnable")
    gate.merged_gate(
        good_worker,
        good_cap,
        verifier_report=CLEAN_VERIFIER,
        battery_report=COMPLETE_BATTERY,
        out_dir=tmp_path / "good",
    )
    assert len(calls) == 1, (
        "the control call must reach the patched robustness — otherwise the "
        "zero count above proves nothing"
    )


def test_a_beaten_game_short_circuits_at_robustness(scratch_capture, tmp_path):
    worker, cap = scratch_capture("trivial")
    result = gate.merged_gate(
        worker,
        cap,
        verifier_report=CLEAN_VERIFIER,
        battery_report=COMPLETE_BATTERY,
        out_dir=tmp_path / "gate",
    )
    assert result["verdict"] == "rejected", _text(result)
    assert "robustness" in str(result["short_circuited_at"]) or "structural" in str(
        result["short_circuited_at"]
    ), result["short_circuited_at"]


def test_a_missing_verifier_report_leaves_that_layer_pending(scratch_capture, tmp_path):
    worker, cap = scratch_capture("unwinnable")
    result = gate.merged_gate(
        worker,
        cap,
        verifier_report=None,
        battery_report=COMPLETE_BATTERY,
        out_dir=tmp_path / "gate",
    )
    assert _layer_status(_layers(result), "verifier") == "pending", _text(result)
    assert result["verdict"] == "pending", _text(result)
    assert "verifier" in str(result["short_circuited_at"]), result["short_circuited_at"]


def test_a_missing_battery_report_leaves_that_layer_pending(scratch_capture, tmp_path):
    worker, cap = scratch_capture("unwinnable")
    result = gate.merged_gate(
        worker,
        cap,
        verifier_report=CLEAN_VERIFIER,
        battery_report=None,
        out_dir=tmp_path / "gate",
    )
    assert _layer_status(_layers(result), "verifier") == "pass", _text(result)
    assert _layer_status(_layers(result), "battery") == "pending", _text(result)
    assert result["verdict"] == "pending", _text(result)
    assert "battery" in str(result["short_circuited_at"]), result["short_circuited_at"]


def test_a_rejecting_verifier_rejects_the_gate(scratch_capture, tmp_path):
    worker, cap = scratch_capture("unwinnable")
    result = gate.merged_gate(
        worker,
        cap,
        verifier_report={"verdict": "reject", "diff": {"missing": ["goal.confirm"]}},
        battery_report=COMPLETE_BATTERY,
        out_dir=tmp_path / "gate",
    )
    assert result["verdict"] == "rejected", _text(result)
    assert "verifier" in str(result["short_circuited_at"]), result["short_circuited_at"]


def test_an_incomplete_battery_is_not_a_green_layer(scratch_capture, tmp_path):
    worker, cap = scratch_capture("unwinnable")
    result = gate.merged_gate(
        worker,
        cap,
        verifier_report=CLEAN_VERIFIER,
        battery_report={"status": "crash", "error": "engine fault"},
        out_dir=tmp_path / "gate",
    )
    assert result["verdict"] != "gated", _text(result)
    assert "battery" in str(result["short_circuited_at"]), result["short_circuited_at"]


def test_merged_gate_writes_both_reports_under_the_gate_dir(scratch_capture, tmp_path):
    """§2 report names; default output is the `<worker>.gate/` sibling."""
    worker, cap = scratch_capture("unwinnable")
    out_dir = tmp_path / "explicit"
    result = gate.merged_gate(
        worker,
        cap,
        verifier_report=CLEAN_VERIFIER,
        battery_report=COMPLETE_BATTERY,
        out_dir=out_dir,
    )
    for name in (gate.ACCEPTANCE_NAME, gate.ROBUSTNESS_NAME):
        assert (out_dir / name).is_file(), f"{name} was not written under {out_dir}"
        json.loads((out_dir / name).read_text(encoding="utf-8"))
        assert name in _text(result["paths"]), result["paths"]

    staged = tmp_path / "sibling" / worker.name
    shutil.copytree(worker, staged)
    game_cls, _solver = load_worker_classes(staged)
    probe = capture(game_cls)
    # The default output is the `<worker>.gate/` SIBLING. The repo root is
    # pointed at the tmp tree for this call so the gate's own D25 boundary
    # (gen/ never writes into a sister repo — where the officials live) does
    # not turn a tmp worker into the out-of-repo case, which the next block
    # covers on purpose.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("gen.config.REPO_ROOT", tmp_path)
        if hasattr(gate, "REPO_ROOT"):
            patch.setattr(gate, "REPO_ROOT", tmp_path)
        gate.merged_gate(
            staged,
            probe,
            verifier_report=CLEAN_VERIFIER,
            battery_report=COMPLETE_BATTERY,
        )
    default_dir = staged.parent / (staged.name + gate.GATE_SUFFIX)
    assert (default_dir / gate.ACCEPTANCE_NAME).is_file(), sorted(
        p.name for p in staged.parent.iterdir()
    )
    assert (default_dir / gate.ROBUSTNESS_NAME).is_file()


def test_an_official_is_never_gated_into_the_sister_repo(official_capture, tmp_path):
    """D25 repo boundary: the officials corpus is READ-ONLY, so the default
    `<worker>.gate/` sibling of an official must never be written — the gate
    either refuses it or is handed an `out_dir` inside this repo."""
    official = _OFFICIALS[0]
    worker_dir = official.py_path.parent
    sibling = worker_dir.parent / (worker_dir.name + gate.GATE_SUFFIX)
    exc = _raised(
        gate.merged_gate,
        worker_dir,
        official_capture(official),
        verifier_report=CLEAN_VERIFIER,
        battery_report=COMPLETE_BATTERY,
    )
    assert exc is not None, (
        f"the gate wrote (or would write) {sibling} — inside duckWM, which gen/ "
        "never writes to (D25)"
    )
    assert not sibling.exists(), f"a report was written into the officials corpus: {sibling}"
    # …and with an out_dir inside this repo's tmp space it runs normally.
    result = gate.merged_gate(
        worker_dir,
        official_capture(official),
        verifier_report=CLEAN_VERIFIER,
        battery_report=COMPLETE_BATTERY,
        out_dir=tmp_path / "official-gate",
    )
    assert (tmp_path / "official-gate" / gate.ACCEPTANCE_NAME).is_file(), _text(result)


def test_merged_gate_is_deterministic(scratch_capture, tmp_path):
    worker, cap = scratch_capture("unwinnable")
    first = gate.merged_gate(
        worker,
        cap,
        verifier_report=CLEAN_VERIFIER,
        battery_report=COMPLETE_BATTERY,
        out_dir=tmp_path / "gate",
    )
    second = gate.merged_gate(
        worker,
        cap,
        verifier_report=CLEAN_VERIFIER,
        battery_report=COMPLETE_BATTERY,
        out_dir=tmp_path / "gate",
    )
    assert _text(first) == _text(second), "merged_gate must be deterministic (contract)"


# --------------------------------------------------------------------------- #
# group 10 — the CLI (no stage runs in this group: every slot is already at
# a stop or terminal, so a real runner would have nothing to do)
# --------------------------------------------------------------------------- #


def test_status_prints_the_replayed_table_and_exits_zero(make_cfg, capsys):
    cfg, cfg_path = make_cfg("b11-cli-status")
    journal = _Journal()
    orch.run_batch(cfg, runners=_Runners(journal, cfg))
    slug = next(iter(_table(cfg)))
    capsys.readouterr()

    code, out, err = _cli(["--config", str(cfg_path), "--status"], capsys)
    assert code == 0, f"--status exits 0; got {code}. stderr:\n{err}"
    assert slug in out, f"--status prints the replayed table:\n{out}"
    assert "played" in out, out


def test_a_bad_config_path_is_a_usage_error(make_cfg, tmp_path, capsys):
    """Contract: `1 usage`. (Ambiguity K: argparse's own usage exit is 2.)"""
    make_cfg("b11-cli-usage")
    missing = tmp_path / "no-such-config.yaml"
    code, _out, _err = _cli(["--config", str(missing)], capsys)
    assert code == 1, f"a missing config is a usage error (exit 1); got {code}"


def test_the_played_stop_exits_two_and_names_the_review_command(make_cfg, capsys):
    cfg, cfg_path = make_cfg("b11-cli-stop")
    journal = _Journal()
    orch.run_batch(cfg, runners=_Runners(journal, cfg))
    slug = next(iter(_table(cfg)))
    before = len(journal.calls)
    capsys.readouterr()

    code, out, err = _cli(["--config", str(cfg_path)], capsys)
    assert code == 2, f"a run stopped at the review checkpoint exits 2; got {code}"
    assert "--review" in out + err, f"the stop must name the review command:\n{out}\n{err}"
    assert slug in out + err, out + err
    assert len(journal.calls) == before, "the resume must not re-invoke a completed stage"
    assert _table(cfg)[slug] == "played", _table(cfg)


def test_a_terminal_batch_exits_zero(make_cfg, capsys):
    cfg, cfg_path = make_cfg("b11-cli-clean")
    journal = _Journal()
    runners = _Runners(journal, cfg)
    orch.run_batch(cfg, runners=runners)
    slug = next(iter(_table(cfg)))
    orch.run_batch(cfg, runners=runners, review=(slug, "accept"))
    assert _table(cfg) == {slug: "packaged"}, _table(cfg)
    capsys.readouterr()

    code, _out, err = _cli(["--config", str(cfg_path)], capsys)
    assert code == 0, f"a terminal-clean batch exits 0; got {code}. stderr:\n{err}"
