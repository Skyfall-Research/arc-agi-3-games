"""B11 — the orchestrator (architecture §4; pilot-plan B11).

The per-slot state machine, the append-only jsonl ledger, resume by content
hash, the human review checkpoint, reject bookkeeping, attrition, and the
per-stage cost table that becomes the batch report (architecture §7, the R5
source).

THE STATE MACHINE IS THE DIAGRAM. `TRANSITIONS` below is architecture §4's
`stateDiagram-v2` transcribed edge for edge, PLUS the five edges contracts
P-1/P-2/P-3 add and the table names one by one — nothing else is legal and an
illegal edge raises `IllegalTransition` rather than being recorded. Four of the
five carry architecture §3's own failure routing, which §4's diagram never drew
an arrow for (the gate at `verified`, S4's cap-fit reject at `gated`, S6's
seed-reject at `reviewed`); until b005 the slot BLOCKED at each of them, and
b004 hit two of the three live. The fifth, `implemented --> dead`, is the
round-cap kill that lets an unattended slot terminate.

The ledger IS the resume state (§4): every transition is appended AFTER the
stage's artifact is on disk, so a kill between the two costs exactly one
idempotent re-run. On restart the ledger replays, `input_hashes` recomputes
the §2 provenance chain (`spec_hash = sha(spec.yaml)`,
`game_hash = sha(game.py + solver.py)`) plus a per-stage input digest, and a
completed stage whose inputs are unchanged never runs again.

Two things this module deliberately does NOT do:

* It never decides the human's decision — UNLESS the batch asks it to, and then
  it says so in the ledger. Reaching `played` stops the run and prints the
  `--review` command; `played --> reviewed` exists only when a human passes
  `review=(slug, "accept")` and `played --> pulled` only for `"pull"`
  (architecture §3 S5: "the human decision ... lands in the batch ledger").
  Contract D-2 gives that stop what it never had: the game is mirrored into the
  play root AT the edge, under a "(review pending)" title, and the stop prints
  the recipe that opens it — so the verdict is cast on a playable build instead
  of on a description of one. Contract P-3.3 adds the one way past it,
  `review.auto_accept`, DEFAULT OFF and armed per batch on the operator's 2026-09-29
  ruling that the pipeline must run without human feedback: armed, the slot
  travels the edge itself with the reason `auto-accept (review.auto_accept)`,
  the batch report names every slug it did that for, and the oversight happens
  post-package.
* It never invents a number. `cost` is read off the stage's own report or
  session result; a stage whose public API surfaces no cost records `None`.

Three numbers the report used to get wrong, ruled by the operator and fixed by
contract D-3 — the R5 report reads all three off this file, so they are stated
here: `usd` covers `PRICED_STAGES` ONLY and every report and footer now says so
(`COST_NOTE`); `respec_runs` is derived from the LEDGER, because the in-memory
counter is 0 on every resume and every real batch resumes; and the attrition
fraction counts DEAD slots only — a human pull at `played` is the review
working, not the batch failing, and it is counted and printed beside the deaths
instead of aborting the batch (`_attrition`, `REVIEW_COMPLETE_NOTE`).

Contract P-A (2026-09-29) adds the two rulings the operator put on the record after
b005-auto died at its round cap and took the batch with it, quoted verbatim:
"We should never kill. Even if it is not satisfied eventually let's not kill."
and "If there's a mismatch of 1-2 terms let's just go ahead with it." They are
implemented as HONESTY, never leniency — the spec is amended to the audited
truth (labels never lie) EARLY (`verifier.reconcile_early`, P-A.1) and in BOTH
directions (`_reconcile_declarations`, P-A.2), a game that outgrew its tier is
promoted rather than refused (P-A.3), and a slot that cannot reconcile PARKS
with its artifacts intact instead of dying (`parked`, P-A.4; outside the
attrition fraction, never a reason to abort). Every knob defaults to today's
bytes and a batch arms them.

Contract E-2 (2026-10-05) is LADDER SANITY — the three ways that ladder was
measured to spin, all on g20261001-5's ledger (2026-10-01):

* it had no MEMORY, so a reconciliation withdrew a term an earlier
  reconciliation had added, on game bytes that never moved, and the spec hash
  returned to the bytes it had left. The amendments are now read back off the
  ledger reasons (`_reconciliation_memory`) and such a finding is refused as
  uncorroborated churn. NOT a knob: an amendment that undoes an amendment is
  incorrect whatever a config says.
* it had no TOP for the downstream lanes: over `verifier.reject_cap` a gate /
  S4 / S6 failure's reason gained `ESCALATE_MARK` and the slot re-specced
  again, with no terminal but `MAX_STEPS_PER_SLOT`'s crash
  (`orchestrator.stage_fail_park` parks it instead).
* and it SPENT BLIND: `_maybe_respec` paid for the S1 session without reading
  the findings it was answering (`orchestrator.respec_feasibility` reads them
  first and parks a provably futile re-spec unspent).

Contract E-5 (2026-10-06) closes what all of that opened: the park had no EXIT.
Five edges reach `parked` and `TRANSITIONS["parked"]` was `{}`, so the RUNBOOK's
"a park is NOT a death: the artifacts stand" was a promise with no mechanism —
b005r2-auto-s001 sat parked since 2026-09-29 on a reject class contract L-1 made
record-only two days later, worker green, $11.41 spent, and `resume` a no-op on
a terminal slot. So `parked` gains one lift edge per edge into it, the lift
restores the state the slot parked FROM (read off the ledger, never chosen), and
it is OPERATOR-INVOKED — `arc-games unpark BATCH_ID SLUG --reason TEXT` ->
`unpark_slot`, which appends one line and runs nothing. NO KNOB: a tree nobody
unparks behaves byte-identically, because nothing in this module can travel
those five edges. And no exemption rides along — the slot re-enters the ordinary
ladder with its whole reject history standing and may park again.

Scale: the pilot is ONE slot (pilot-plan B11, D22). Slots are worked in waves
of `orchestrator.wave_size`, SEQUENTIALLY unless contract P-5's
`orchestrator.parallel_slots` is armed — absent or false (every config written
before P-5, all of which already carry a decorative `workers`) is the
sequential path, byte for byte. Armed beside `workers > 1`, the run becomes a
PARENT: it advances every slot through the S0 edge itself (the draw is one
batch-wide call, so it must happen once and before any fan-out), then spawns
one child per slot per wave — `--slot <slug>`, which is this same module
running exactly that slot — and merges their sidecars into one report. THE OPERATOR'S
RULING stands over the whole of it ("We should never kill"): a child's failure
never interrupts its wave, its ledger state stands, and a resume re-runs it.

CLI:  python -m gen.orchestrator --config config/b001-pilot.yaml
      python -m gen.orchestrator --config … --status
      python -m gen.orchestrator --config … --review <slug>:accept|pull
      python -m gen.orchestrator --config … --slot <slug>   (P-5 child mode)
Exit: 0 every slot terminal · 2 stopped (review / blocked / attrition) ·
      1 usage or config error.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import traceback
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from .config import REPO_ROOT, load_config

SCHEMA_VERSION = "b11.1"
DEFAULT_CONFIG = "config/b001-pilot.yaml"

# --- the §4 vocabulary ------------------------------------------------------

STATES = (
    "ideated", "respec", "spec_ok", "implemented", "verified",
    "gated", "baselined", "played", "reviewed", "packaged",
    "dead", "pulled",
    # Contract P-A.4. OPERATOR RULING (2026-09-29, on the record, verbatim):
    # "We should never kill. Even if it is not satisfied eventually let's not
    # kill." A slot whose verify-lane residual no declaration can answer now
    # STOPS with its artifacts intact instead of dying — terminal for the run,
    # excluded from the attrition ratio, and never a reason to abort a batch.
    "parked",
)
# `parked` is terminal in exactly the way `pulled` is: nothing left to run, and
# nothing failed systemically. The attrition fraction still counts `dead` ONLY
# (`_attrition`), so a parked slot can never abort a batch.
TERMINAL = ("packaged", "dead", "pulled", "parked")

# `[*] --> ideated` — the birth edge. A slot that has never been sampled has
# no from-state, and the ledger line records `"from": null`.
BIRTH: str | None = None

# Architecture §4's stateDiagram-v2, verbatim: {from: {to: the edge's label}}.
# The labels are the diagram's own text and are what the reason codes cite.
#
# --- THE FIVE EDGES §4's DIAGRAM DOES NOT DRAW (contracts P-1, P-2, P-3) -----
#
# Four of them implement architecture §3's OWN failure routing, which §4 simply
# gives no arrow to travel on. §3 names the routes in prose and this file has
# quoted that prose above `STAGE_FAILURE` since B11: "gate → nothing, S4 cap-fit
# → S2 (cap bug), S6 seed-reject → S2 (the layout function is buggy)". Without
# the edges the slot BLOCKED, and b004 (2026-09-28) hit BOTH holes live: the
# role-footprint gate fail blocked slot 1 at `verified` (and was answered by
# downgrading the check to `record` in config/b004-validation.yaml — the
# comment there flags this gap as the follow-up), and the seed-3 package fail
# CRASHED and then had no edge anyway.
#
# OPERATOR RULING (2026-09-29, on the record): "(1) the pipeline must run WITHOUT
# human feedback — scalable autonomy; (2) verifier judgment is NEVER softened;
# residuals resolve by mechanical reconciliation or slot death, not leniency."
# A slot that stops for a human because a diagram lacks an arrow is (1) failing.
# So the three §3 routes get the edges §3 already says they take — all three to
# `spec_ok`, which is where a verifier reject already goes and from which the
# slot re-implements — and the fifth edge, `implemented --> dead`, is P-3's
# round-cap kill: the bound that makes autonomy terminate.
#
# --- THE FOUR PARK EDGES CONTRACT E-2 ADDS ----------------------------------
#
# P-A.4 gave the verify lane a park (`implemented --> parked`) and left every
# OTHER failure lane on the treadmill. Measured on g20261001-5 (2026-10-01,
# ledger on disk): a gate fail routed `verified --> spec_ok` four times over —
# "gate fail 1/1", "gate fail 2/1", then "package fail 3/1" and "package fail
# 4/1" — because over `verifier.reject_cap` the reason merely gains
# `ESCALATE_MARK` and the slot re-specs AGAIN. `verifier.round_cap` cannot bite
# (it counts only `implemented --> spec_ok`) and `orchestrator.respec_cap`
# bounds only the S1 lint-kill loop, so the sole remaining bound was
# `MAX_STEPS_PER_SLOT`, which CRASHES rather than parks.
#
# So each state a downstream reject departs from gains the park its lane never
# had, and the state a futile re-spec is refused at gains one too:
#
#   ("verified", "parked")  gate fail over the cap   (orchestrator.stage_fail_park)
#   ("gated", "parked")     S4 cap-fit over the cap  (     "        "            )
#   ("reviewed", "parked")  package fail over the cap (     "        "            )
#   ("spec_ok", "parked")   a re-spec no spec amendment could answer
#                           (orchestrator.respec_feasibility)
#
# `("gated", "parked")` is NOT in contract E-2's seam map, which names two
# edges; it is here because the rule the contract states is "a DOWNSTREAM stage
# fail", `DOWNSTREAM_REJECT_EDGES` is three states wide, and a park from `gated`
# with no edge drawn would be an `IllegalTransition` CRASH in an armed batch —
# the b004 failure mode this whole ladder exists to end. Deviation declared in
# the handback, not resolved silently.
#
# --- THE FIVE LIFT EDGES CONTRACT E-5 ADDS ----------------------------------
#
# Every edge named so far goes INTO `parked` and none ever came out:
# `TRANSITIONS["parked"]` was `{}`, `grep unpark` found nothing, and the
# RUNBOOK's promise — "A park is NOT a death: the artifacts stand" — had no
# mechanism behind it. LIVE EXHIBIT (lead-verified 2026-10-06):
# b005r2-auto-s001 (two-keys-one-echo), parked 2026-09-29T15:50:31 on
# `round-cap park: undeclared-deception (verify round 5, verifier.round_cap 4;
# the audit rejected again AFTER the declarations were reconciled)` — a reject
# class contract L-1 made RECORD-ONLY two days later. Its worker validates
# green today and $11.41 of paid work stands behind it, with no legal path to
# S6; and `resume` cannot help, because the slot is terminal and the batch
# therefore replays COMPLETE.
#
# So `parked` gains an exit, for EXACTLY the five states that have an edge into
# it — `spec_ok`, `implemented`, `verified`, `gated`, `reviewed`. The lift
# restores THE state the slot parked FROM, read mechanically off the ledger
# (`last_park_line`: the last `… --> parked` line, its `from` field), never a
# state a caller chose: a lift that could pick its destination would be a way
# to skip a stage, and the park's own line is the only honest record of where
# the slot was standing when it stopped.
#
# NOT A KNOB AND NOT A STAGE. The lift is OPERATOR-INVOKED — `arc-games unpark
# BATCH_ID SLUG --reason TEXT` (`gen.cli.cmd_unpark` -> `unpark_slot`), the same
# separation `gen.worker --resync` keeps — and it runs nothing: it appends one
# line and prints the resume command. A tree nobody unparks behaves
# byte-identically to the day before this contract: these edges are unreachable
# without that command, `parked` is still TERMINAL, `NEXT_STAGE["parked"]` is
# still `None`, and no branch of `_work_slot` can travel them.
#
# AND THE RE-ENTRY CARRIES NO EXEMPTION (E-5 §3). The slot re-enters the
# ORDINARY ladder under the batch's CURRENT config with its whole history
# standing. That is structural rather than promised: the lift line's edge is in
# no counter's edge set (`_verifier_rejects_against`, `_verify_rounds`,
# `respec_runs_from_ledger`, `_record`/`replay_ledger`'s reject tallies) and its
# reason begins with `UNPARK_PREFIX`, so it is in no reason-prefix reader's set
# either (`_reconciliation_memory`, `_churn_refused_before`,
# `_reconciled_before`). The stage that parked the slot runs again against the
# same rejects and may park it again — a second operator act, a second line.
#
# CANON ITEM, FLAGGED NOT SILENTLY RESOLVED: the §4 diagram upstream lives in
# duckWM (READ-ONLY here) and still draws neither. The machine is now ahead of
# the diagram on exactly these five arrows (nine with E-2's four, fourteen with
# E-5's five lifts), deliberately and on the ruling above; §4 remains the
# authority for everything else, and an edge outside this table is still an
# `IllegalTransition`.
TRANSITIONS: dict[str | None, dict[str, str]] = {
    BIRTH: {"ideated": "[*] --> ideated"},
    "ideated": {"spec_ok": "lint pass", "respec": "lint kill"},
    "respec": {"ideated": "re-sample"},
    "spec_ok": {"implemented": "validate green", "dead": "green-attempts cap ×2",
                "parked": "futile re-spec park"},
    # `implemented --> dead` REMAINS drawn: b005-auto's ledger carries that line
    # and must still replay. No live code path routes to it any more (contract
    # P-A.4 — `to_state="dead"` appears exactly once in this module, in the s2
    # `GREEN_CAP_DEATHS` path, which is a pre-existing §4 edge and deliberately
    # untouched). The verify lane parks instead.
    "implemented": {"verified": "S2b clean", "spec_ok": "verifier reject ×2 → respec",
                    "dead": "round-cap kill", "parked": "round-cap park"},
    "verified": {"gated": "structural + robustness green",
                 "spec_ok": "gate fail → re-implement",
                 "parked": "gate fail over cap → park"},
    "gated": {"baselined": "g-sampler + cap-fit",
              "spec_ok": "cap-fit fail → re-implement (§3: cap bug)",
              "parked": "cap-fit fail over cap → park"},
    "baselined": {"played": "battery done"},
    "played": {"reviewed": "human accept", "implemented": "crash"},
    "reviewed": {"packaged": "", "pulled": "",
                 "spec_ok": "package fail → re-implement (§3: the layout function is buggy)",
                 "parked": "package fail over cap → park"},
    "packaged": {},
    "dead": {},
    "pulled": {},
    # CONTRACT E-5 — the park's EXIT: one edge per edge INTO `parked` above, and
    # no other. The label names WHO moved the slot, because nothing in this
    # module can: these five are the only edges in the table that no stage and
    # no runner verdict can travel (see `unpark_slot`).
    "parked": {"spec_ok": "operator unpark → spec_ok",
               "implemented": "operator unpark → implemented",
               "verified": "operator unpark → verified",
               "gated": "operator unpark → gated",
               "reviewed": "operator unpark → reviewed"},
}

# The states a park DEPARTS from, derived from the table above rather than
# listed again (contract E-5 §1: "EXACTLY the five states that today have an
# edge INTO parked"). `unpark_slot` needs no such list — it reads the park
# line's own `from` and lets `assert_transition` gate it — so this exists for
# the refusal messages and for the pin that says the two halves of the table
# are the same five states.
PARK_SOURCES: tuple[str, ...] = tuple(sorted(
    str(source) for source, dests in TRANSITIONS.items()
    if source is not BIRTH and "parked" in dests
))

# Which stage OWNS each edge — the ledger line carries no stage field, so the
# stage is recovered from (from, to). `None` = no stage ran (a human decision,
# or the battery-crash routing that follows the battery's own line).
EDGE_STAGE: dict[tuple[str | None, str], str | None] = {
    (BIRTH, "ideated"): "s0_ideas",
    ("respec", "ideated"): "s0_ideas",
    ("ideated", "spec_ok"): "s1_spec",
    ("ideated", "respec"): "s1_spec",
    ("spec_ok", "implemented"): "s2_implement",
    ("spec_ok", "dead"): "s2_implement",
    ("implemented", "verified"): "s3_verify",
    ("implemented", "spec_ok"): "s3_verify",
    # P-3.2b: the round-cap kill is the VERIFIER's verdict standing, so the
    # stage that owns it is the one whose rounds ran out.
    ("implemented", "dead"): "s3_verify",
    # P-A.4: the park has the same owner for the same reason — it IS that
    # verdict standing, with the operator's never-kill ruling applied to the outcome.
    ("implemented", "parked"): "s3_verify",
    # CONTRACT E-2 §2: a downstream park is the SAME verdict standing as that
    # stage's reject, so it has that stage's owner — exactly the reasoning
    # `("implemented", "parked")` above is given.
    ("verified", "gated"): "s3_gate",
    ("verified", "spec_ok"): "s3_gate",          # P-2.1 gate fail
    ("verified", "parked"): "s3_gate",           # E-2 §2 gate fail over the cap
    ("gated", "baselined"): "s4_baselines",
    ("gated", "spec_ok"): "s4_baselines",        # P-2.2 cap-fit fail
    ("gated", "parked"): "s4_baselines",         # E-2 §2 cap-fit over the cap
    ("baselined", "played"): "s5_battery",
    ("played", "reviewed"): None,
    ("played", "implemented"): None,
    ("reviewed", "packaged"): "s6_package",
    ("reviewed", "spec_ok"): "s6_package",       # P-1.2 package fail
    ("reviewed", "parked"): "s6_package",        # E-2 §2 package fail over the cap
    ("reviewed", "pulled"): None,
    # CONTRACT E-2 §3: the session that was NOT spent owns the line. A futile
    # re-spec parks at `spec_ok` without invoking S1, and `s1_spec` is the stage
    # whose work the ledger is recording the absence of.
    ("spec_ok", "parked"): "s1_spec",
    # CONTRACT E-5 §1 — NO STAGE RAN. A lift is an operator act, so it takes the
    # same `None` the two human review decisions above take, and it cannot take
    # the restored state's stage: that stage has NOT run, and naming it would
    # hand `_restage` a "recorded" line whose hashes predate the work it claims.
    # Both readers of this table skip a `None` (`_restage`'s recorded-stage
    # walk, `_cost_table`), which is what keeps a lift out of the resume's stale
    # walk and off every cost row — a lift costs nothing because it does nothing.
    ("parked", "spec_ok"): None,
    ("parked", "implemented"): None,
    ("parked", "verified"): None,
    ("parked", "gated"): None,
    ("parked", "reviewed"): None,
}

STAGES = (
    "s0_ideas", "s1_spec", "s2_implement", "s3_verify",
    "s3_gate", "s4_baselines", "s5_battery", "s6_package",
)

# The stage that runs from each state. `played` runs nothing: it is the human
# checkpoint. Terminal states run nothing by definition.
NEXT_STAGE: dict[str | None, str | None] = {
    BIRTH: "s0_ideas",
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
    # P-A.4: parked is TERMINAL for the run. The artifacts stay on disk and the
    # ledger reason carries the full residual list, so a human (or a later
    # contract) can pick the slot up — but this run runs nothing more for it.
    #
    # CONTRACT E-5 IS THAT LATER CONTRACT, and this row does NOT change: `None`
    # is still the truth. The park's exit is not a stage and no run can travel
    # it — the operator appends the lift line out of band (`unpark_slot`), the
    # slot's state is then the state it parked FROM, and `NEXT_STAGE` of THAT
    # state is what the next resume runs. A stage here would make a parked slot
    # work itself loose on the next resume, which is exactly what P-A.4 refuses.
    "parked": None,
}

# The state a stage lands on success — the `ok: True` contract of a runner.
STAGE_SUCCESS: dict[str, str] = {
    "s0_ideas": "ideated",
    "s1_spec": "spec_ok",
    "s2_implement": "implemented",
    "s3_verify": "verified",
    "s3_gate": "gated",
    "s4_baselines": "baselined",
    "s5_battery": "played",
    "s6_package": "packaged",
}

# Where a stage's FAILURE goes. architecture §3 routes all three of the ones
# §4's diagram left arrowless — "gate → nothing, S4 cap-fit → S2 (cap bug), S6
# seed-reject → S2 (the layout function is buggy)" — and contracts P-1/P-2 give
# them the edges to travel on (see the comment block at `TRANSITIONS`). All
# three land on `spec_ok`, which is §3's "S2" and the state a verifier reject
# already goes to: from there the slot re-implements and re-travels
# verify → gate → S4 → S5 → review honestly, because §2's hash chain re-runs
# every stage whose inputs changed and asserts nothing special to do it.
#
# `None` now means only what it always should have: no state at all (a sampler
# failure is a hard error; a green-loop attempt under the cap appends no line).
STAGE_FAILURE: dict[str, str | None] = {
    "s0_ideas": None,        # a sampler failure is a hard error, not a state
    "s1_spec": "respec",     # lint kill
    "s2_implement": "dead",  # only at GREEN_CAP_DEATHS; below it, no line
    "s3_verify": "spec_ok",  # verifier reject
    "s3_gate": "spec_ok",    # P-2.1: gate fail -> re-implement
    "s4_baselines": "spec_ok",    # P-2.2: cap-fit fail -> re-implement (§3: cap bug)
    "s5_battery": "implemented",  # crash, via `played` (§4: played --> implemented)
    "s6_package": "spec_ok",      # P-1.2: package fail -> re-implement (§3: layout bug)
}

# The three stages whose failure now routes through `spec_ok` on an edge the §4
# diagram does not draw (see `TRANSITIONS`), with the label each one's ledger
# reason leads with and the §3 route it is implementing. `s3_verify` is NOT in
# here: its `implemented --> spec_ok` edge is §4's own and its reason string is
# frozen by contract D-3.
#
# CONTRACT E-2 §2 — WHERE THIS LADDER ENDS. These three routings had NO
# terminal: over `verifier.reject_cap` the reason gained `ESCALATE_MARK` and the
# slot re-specced again, forever (the g20261001-5 exhibit at `TRANSITIONS`).
# `orchestrator.stage_fail_park`, armed, gives each of them the park its lane
# never had — `_work_slot`'s routing branch, the park edges above.
STAGE_REJECT_ROUTING: dict[str, tuple[str, str]] = {
    "s3_gate": ("gate fail", "re-implement"),
    "s4_baselines": ("cap-fit fail", "re-implement (§3: cap bug)"),
    "s6_package": ("package fail", "re-implement (§3: the layout function is buggy)"),
}

# Which state each downstream routing departs FROM — the park's `from_state`
# (contract E-2 §2). Derived from `STAGE_SUCCESS` of the stage before it would
# be clever and wrong: `s5_battery` lands on `played` and the §4 edge into
# `s6_package` is a HUMAN decision, so the states are named.
STAGE_REJECT_STATE: dict[str, str] = {
    "s3_gate": "verified",
    "s4_baselines": "gated",
    "s6_package": "reviewed",
}

# The same three, as EDGES — what `_verifier_rejects_against` counts alongside
# the verifier's own rejects (contract P-2 §3, the loop guard).
DOWNSTREAM_REJECT_EDGES: tuple[tuple[str, str], ...] = tuple(
    (state, "spec_ok") for state in ("verified", "gated", "reviewed")
)

# The slot inputs whose content identifies a stage's work (§2 ⊕ "a stage
# re-runs iff its input hashes changed"). Names resolve through
# `SlotContext.input_paths()`.
STAGE_INPUTS: dict[str, tuple[str, ...]] = {
    "s0_ideas": (),  # rng + config only; the scalar seed enters the digest
    "s1_spec": ("idea",),
    "s2_implement": ("spec_yaml", "spec_md"),
    "s3_verify": ("game", "solver", "spec_yaml"),
    "s3_gate": ("game", "solver", "verifier_report"),
    "s4_baselines": ("game", "solver"),
    "s5_battery": ("game", "solver", "metadata"),
    "s6_package": ("game", "solver", "metadata", "spec_yaml"),
}

# --- names, roots, caps -----------------------------------------------------

LEDGER_NAME = "ledger.jsonl"
BATCH_REPORT_NAME = "batch-report.json"
# Contract P-5's two per-slot artifacts, both inside the batch dir beside the
# ledger they belong to. The SIDECAR is how a child hands its parent the facts
# no ledger line can carry (off-ledger spend, blocked/stale, review_pending,
# invocations, this-run respec count); the LOG is the child's whole stdout and
# stderr, because a child's console is nobody's terminal. Neither is ever
# `batch-report.json`: a child writes no batch report, and the merge does.
SLOT_REPORT_SUFFIX = ".slot-report.json"
SLOT_LOG_SUFFIX = ".slot.log"
LEDGER_KEYS = ("slug", "from", "to", "reason", "hashes", "cost", "ts")
HASH_KEYS = ("spec", "game", "stage_input")
COST_KEYS = ("usd", "tokens_in", "tokens_out")

BATCHES_ROOT = REPO_ROOT / "out" / "batches"
CORPUS_ROOT = REPO_ROOT / "out" / "corpus"   # == s1_spec.CORPUS_ROOT (checked in the runner)
IDEAS_ROOT = REPO_ROOT / "out" / "ideas"     # == s0_ideas.IDEAS_ROOT (checked in the runner)
# The S0 draw's mutex (contract P-5 addendum 1), one per batch, inside the very
# directory it guards. Dot-prefixed and never `idea-NNN.json`: no reader in this
# pipeline scans that directory — every idea path is constructed, never globbed
# — so the file is invisible to everything but the lock.
S0_DRAW_LOCK_NAME = ".sample-batch.lock"
WORKER_DIRNAME = "worker"                    # architecture §2: corpus/<batch>/<slug>/worker/
# `s3_verify.REPORT_SUFFIX`, spelled out: the state machine resolves the S2b
# report's path (a SIBLING of the worker dir) without importing a stage module.
VERIFIER_REPORT_SUFFIX = ".verifier-report.json"
# The declaration-only re-spec marker — another worker SIBLING, written by
# `_maybe_respec` and consumed (once) by the S2 runner.
#
# WHY IT EXISTS. The S2b audit measures the IMPLEMENTATION; the spec must
# DECLARE what that implementation makes reachable. An escalated re-spec that
# answers findings by widening `game.terms` / `knobs.deceptions` changes
# spec.yaml's bytes, so §2's cascade re-runs S2 — and a re-implement rewrites
# the game, handing the next audit a NOVEL surface to find novel findings in.
# Measured on the pilot: three escalated rounds, three brand-new finding sets.
# The game code reads neither field, so a spec change confined to them cannot
# invalidate the game beside it; skipping the re-implement in exactly that
# case freezes the audit surface, and round N+1's mechanical findings become
# round N's minus the newly declared. The marker is the carrier of that one
# decision, and it is SINGLE-SHOT (see `_take_decl_only_marker`).
DECL_ONLY_MARKER_SUFFIX = ".decl-only-respec.json"
DECL_ONLY_REASON = "declaration-only re-spec: implementation revalidated, sessions skipped"
# The gate/S4/S6 failure payload for the NEXT S2 session — another worker
# SIBLING (contracts P-1 §2, P-2 §1/§2).
#
# IT IS THE EXISTING FINDINGS FEED, not a second channel. The verifier-reject
# feed is `reject_reasons` -> `s2_implement.findings_section(report)` appended
# to the next build's prompt, and this file writes the SAME `{verdict: "reject",
# reject_reasons: [{code, detail}]}` shape and renders it through the SAME
# function at the SAME seam in the S2 runner. What it cannot do is ride in the
# verifier's own report: at a gate/S4/S6 failure that report says `pass` (S2b
# accepted the build; the render, the budget or the layout is what failed), the
# gate reads it as S2b's verdict, and s3_verify's judgment is untouchable. So
# the payload is a file of its own carrying the other stages' findings, and the
# stage that OWNS each finding clears it the moment it passes.
STAGE_FINDINGS_SUFFIX = ".stage-findings.json"
# Where a lint-KILLED spec dir goes. A kill leaves spec.yaml/spec.md/
# lint-report.json/idea.json on disk (the S1 runner declares all four), and the
# NEXT S1 attempt writes a second dir carrying the same `idea.json` — which is
# exactly what `_discover_spec_dir` refuses to see. The kill is evidence, not
# rubbish, so it is moved aside rather than deleted.
KILLED_DIRNAME = ".killed"

# The DEFAULT for `verifier.reject_cap` (read by `_reject_cap`), not the cap
# itself: "verifier reject ×2 -> respec" is architecture §4's own number and
# stays the behaviour of every config that writes no key. Contract D-3 §1 wired
# the key that b001 and b002 have both spelled since birth and nothing read —
# both write 2, so wiring it changed no batch's behaviour, only its honesty.
VERIFIER_REJECT_CAP_ESCALATE = 2
GREEN_CAP_DEATHS = 2               # green-attempts cap ×2 -> dead (architecture §4)
# NOT canon: §4 gives `ideated`/`respec` no edge to `dead`, so an idea the
# linter keeps killing cannot die — it blocks. Two strikes is the shape both
# canon caps above use (§3 S2: "two consecutive spec rejects → the slot dies").
# This is now the DEFAULT only: B11's close flagged "RESPEC_CAP=2 not canon",
# and the R2 ruling (operator 2026-09-22) made the cap per-batch config —
# `orchestrator.respec_cap`, read by `_respec_cap`.
RESPEC_CAP = 2
# Livelock guard, not a policy: every loop turn either appends a line or
# consumes one of the caps above, so a run that exceeds this is a wiring bug
# in a runner and says so.
MAX_STEPS_PER_SLOT = 64

CRASH_REASON = "battery crash -> implemented (architecture §4: played --> implemented: crash)"
ESCALATE_REASON = "verifier reject ×{n} -> respec (architecture §4)"
ESCALATE_PREFIX = ESCALATE_REASON.split("{", 1)[0]   # what a replay recognizes
# The ESCALATION MARK: the substring every escalation reason carries, whichever
# stage spent the reject that reached the cap. `ESCALATE_REASON` has always
# ended with it, so every ledger line ever written still matches — which is why
# `_escalated` and `respec_runs_from_ledger` read THIS rather than the prefix
# now that P-2's gate/S4/S6 rejects ride the same ×reject_cap ladder and cannot
# honestly call themselves "verifier reject".
ESCALATE_MARK = ESCALATE_REASON.split("}", 1)[1].strip()   # "-> respec (architecture §4)"
REVIEW_DECISIONS = ("accept", "pull")

# --- contract P-3: the autonomy knobs ---------------------------------------
#
# OPERATOR RULING (2026-09-29, on the record): "(1) the pipeline must run WITHOUT
# human feedback — scalable autonomy; (2) verifier judgment is NEVER softened;
# residuals resolve by mechanical reconciliation or slot death, not leniency."
# Both knobs below default to TODAY'S BYTES (no `verifier.round_cap` = the
# unlimited rounds every batch has run; no `review.auto_accept` = the human stop
# §4 has always halted for) and a batch ARMS them.

# `verifier.round_cap`'s ledger vocabulary. Path (a) — MECHANICAL
# RECONCILIATION — amends the spec's DECLARATIONS to match what the blind audit
# found and buys exactly one confirming round; it is not leniency, because the
# audit's finding is written into the spec rather than waived, and the
# confirming round has to come back clean against the amended declarations.
# Path (b) was the slot's death; contract P-A.4 makes it the slot's PARK.
RECONCILE_REASON = "declaration reconciled to audit: {added}"
RECONCILE_PREFIX = RECONCILE_REASON.split("{", 1)[0]   # what a replay recognizes
ROUND_CAP_KILL_REASON = "round-cap kill: {codes}"
ROUND_CAP_KILL_PREFIX = ROUND_CAP_KILL_REASON.split("{", 1)[0]
# --- contract P-A (2026-09-29, the lenient pass) -----------------------------
#
# THE OPERATOR'S TWO RULINGS, on the record and quoted verbatim wherever this contract
# quotes them:
#   "We should never kill. Even if it is not satisfied eventually let's not
#    kill."
#   "If there's a mismatch of 1-2 terms let's just go ahead with it."
# The honest implementation of the second is NOT leniency: the spec is amended
# to the audited truth (labels never lie), EARLY and in both directions, and the
# amended declarations still have to survive a confirming round. The honest
# implementation of the first is the park below — the slot stops, its artifacts
# stay, and the batch carries on.
ROUND_CAP_PARK_REASON = "round-cap park: {codes}"
ROUND_CAP_PARK_PREFIX = ROUND_CAP_PARK_REASON.split("{", 1)[0]
# P-A.1's ledger vocabulary. `{cap}` is the configured `verifier.reconcile_early`
# and `{changes}` is the amendment, additions with `+` and drops with `-`.
RECONCILE_EARLY_REASON = "declaration reconciled early (<={cap}): {changes}"
RECONCILE_EARLY_PREFIX = RECONCILE_EARLY_REASON.split("{", 1)[0]
# P-A.3's ledger vocabulary: the promotion is the record (idea.json is NEVER
# rewritten — ideas are immutable).
TIER_PROMOTION_REASON = "tier promoted {before}->{after}: {count} declared terms vs budget {budget}"
TIER_PROMOTION_PREFIX = TIER_PROMOTION_REASON.split("{", 1)[0]
# The reject codes a reconciliation can answer, in the TWO directions contract
# P-A.2 gives it.
#
# ADDITIVE (yesterday's whole set): the code is reachable and the spec does not
# say so, so the spec is made to say so.
RECONCILABLE_ADDITIVE_CODES = ("undeclared-term", "undeclared-deception")
# SUBTRACTIVE (new): the spec declares a term the blind audit cannot reach, so
# the DECLARATION is withdrawn. This is the same move in the other direction and
# it is still not leniency — the label is made true rather than the finding
# waived, and the amended spec has to lint and come back clean.
RECONCILABLE_SUBTRACTIVE_CODES = ("dead-spec-term", "unreachable-declared-mechanic")
# Everything else — solver-quality, forbidden-static, the look-alike/refusal
# classes — names a defect in the GAME, and no edit to a declaration can make it
# untrue. Those residuals park the slot (P-A.4); they are never reconciled.
RECONCILABLE_CODES = RECONCILABLE_ADDITIVE_CODES + RECONCILABLE_SUBTRACTIVE_CODES
# The deception entries a reconciliation writes. `game.knobs.deceptions` is
# free text and the audit declares by SUBSTRING containment (case/punct
# stripped), so the lever's own name has to lead the entry for the declaration
# to hold; the rest of the line says who wrote it and why.
#
# `{via}` is WHICH path wrote it, and it is a parameter because both write this
# entry: the round-cap reconciliation and P-A.1's early one. It used to be
# hardcoded "(round_cap)", so an entry the EARLY path wrote named a path it
# never travelled — b005r2's two-keys-one-echo spec is the mislabelled exhibit
# on disk (contract E-1 defect fix #2; shipped entries are not rewritten,
# ideas and corpora being immutable).
RECONCILED_DECEPTION = "{lever}: reconciled from the blind audit ({via})"
RECONCILED_VIA_ROUND_CAP = "round_cap"
RECONCILED_VIA_EARLY = "reconcile_early"
# Where P-A.3 writes the promoted tier. The spec had no tier field at all before
# this contract — `s1_spec._idea_tier` reads the tier off `idea.json`, which is
# IMMUTABLE — so the promotion needs a home of its own, and this is it: a
# declaration ABOUT the game that no generated `game.py` reads (which is why
# `s1_spec.DECLARATION_ONLY_FIELDS` now prunes it from `impl_projection`, or a
# promotion would force a paid rewrite of a game that did not change).
SPEC_TIER_FIELD = "tier"

AUTO_ACCEPT_REASON = "auto-accept (review.auto_accept)"

# --- contract E-2 (2026-10-05, ladder sanity) --------------------------------
#
# THE THREE MEASURED FAILURES, all on g20261001-5's ledger (2026-10-01, lines
# cited as they stand on disk):
#
#  (a) RECONCILIATION PING-PONG. Line 12 reconciled `+manip.terraform`; line 14
#      reconciled `-manip.terraform` one round later, on UNCHANGED game bytes
#      (`hashes.game` 6eca8f66 both times), and the spec hash returned to the
#      byte-identical bd7b492e it had left. Nothing remembered the amendment:
#      `_reconciled_before` is a boolean that deliberately matches only the
#      round cap's prefix, and the early path had no history guard at all.
#  (b) STAGE-FAIL TREADMILL. Lines 7, 10, 21, 28: "gate fail 1/1", "gate fail
#      2/1", "package fail 3/1", "package fail 4/1" — all four to `spec_ok`,
#      the last two over a cap of 1. See `STAGE_REJECT_ROUTING`.
#  (c) BLIND RESPEC SPEND. The spec hash is bd7b492e at line 7 and still
#      bd7b492e at line 8: the escalated re-spec those lines paid for produced
#      a no-op declaration diff, because `_maybe_respec` never read the
#      findings it was answering.
#
# §1's answer is MEMORY (not a knob — a reconciliation that withdraws what a
# reconciliation added is incorrect, armed or not). §2's and §3's are knobs, and
# both default to today's bytes.

# §1's ledger vocabulary. `{churn}` is the REFUSED amendment in
# `_reconcile_changes`'s own spelling (`-manip.terraform`), so the one phrase
# reads the same in a reconciliation line and in a refusal.
CHURN_REFUSED_REASON = "reconciliation churn refused: {churn}"
CHURN_REFUSED_PREFIX = CHURN_REFUSED_REASON.split("{", 1)[0]
# The sentence a churn refusal carries wherever it is named — the ledger line,
# the slot row, the run log. ONE constant because all three must say the same
# thing about the same event.
CHURN_REFUSED_NOTE = (
    "a prior reconciliation settled this declaration in the other direction on "
    "unchanged game bytes; the finding is uncorroborated churn, the declaration "
    "stands (contract E-2 §1)"
)
# §2's ledger vocabulary, built like `ESCALATE_REASON`/`ESCALATE_MARK`: the MARK
# is the fixed substring a reader greps for, because the reason's head is the
# failing stage's own `{label} {count}/{cap}` phrase and cannot be a prefix.
STAGE_FAIL_PARK_MARK = "-> park (orchestrator.stage_fail_park)"
STAGE_FAIL_PARK_REASON = "{label} {count}/{cap} " + STAGE_FAIL_PARK_MARK + ": {codes}"
# §3's ledger vocabulary: a park that names the session it did NOT spend.
RESPEC_FUTILE_REASON = "futile re-spec park (orchestrator.respec_feasibility): {codes}"
RESPEC_FUTILE_PREFIX = RESPEC_FUTILE_REASON.split("{", 1)[0]
# CONTRACT E-5's ledger vocabulary — the one line a lift writes.
#
# IT CARRIES BOTH TEXTS. The operator's own `--reason` says why the park was
# lifted, and the park line's reason is QUOTED after it so the lift is readable
# on its own: a reader of `parked --> implemented` otherwise has to walk back up
# the ledger to learn what the slot was parked for in the first place.
#
# THE OPERATOR TEXT COMES FIRST, and that ordering is load-bearing rather than
# stylistic. Every reason-reader in this module is a PREFIX reader
# (`RECONCILE_PREFIX`, `RECONCILE_EARLY_PREFIX`, `CHURN_REFUSED_PREFIX`,
# `RESPEC_FUTILE_PREFIX`), so a quoted park reason that begins with one of them
# cannot be read as the thing it quotes while `UNPARK_PREFIX` is what the line
# begins with. The one SUBSTRING reader is the batch report's `tier_promoted`
# filter, and it is taught to skip a lift line where it stands.
UNPARK_REASON = 'operator unpark: {text} (lifting the park "{park}")'
UNPARK_PREFIX = UNPARK_REASON.split("{", 1)[0]   # what a replay/report recognizes

# §3's FUTILITY CLASSIFIER — the codes NO spec amendment can answer.
#
# The direction of the list is deliberate and it is CONSERVATIVE: a code in here
# parks a slot without spending a session, so the list is a closed enumeration
# of the classes contract E-2 §3 names, and EVERY other code — known or not —
# reads as spec-answerable and spends the session. Wrongly spending one re-spec
# is a bill; wrongly parking is a game nobody can finish.
#
# The two verifier codes are `REJECT_CODES` minus the reconcilable four
# (s3_verify.py:205-218, reproduced here rather than imported for the reason
# every name in this module is reproduced: the state machine must not drag
# arcengine/numpy in).
FUTILE_VERIFIER_CODES = ("solver-quality", "forbidden-static")
# The GATE-VISUAL card checks, which are claims about what the game PAINTS:
# `s3_visual.CARD_CHECKS` plus the l1 colour floor, in the dashed spelling the
# gate runner prefixes with `gate.`. Reproduced, pinned equal to that tuple by
# `gen/tests/test_e2_ladder.py` so the two cannot drift.
GATE_VISUAL_CHECKS = (
    "l1-color-floor", "field-index", "role-footprint", "win-render",
    "declared-vs-painted", "chrome-extent", "danger-visible", "density",
)
# …and S6's seed reject, the fourth class §3 names: a layout function that
# cannot win at seed N is §3's own "S2 (the layout function is buggy)".
FUTILE_STAGE_CODES = (*(f"gate.{check}" for check in GATE_VISUAL_CHECKS), "s6.seed-reject")
FUTILE_CODES = FUTILE_VERIFIER_CODES + FUTILE_STAGE_CODES
# What a dry-run refusal is ABOUT, so §3 can tell "this amendment cannot lint"
# (evidence of futility) from "I could not read the spec" (evidence of nothing).
# Only `AMENDMENT` ever contributes to a futility verdict.
REFUSED_INPUT = "input"
REFUSED_AMENDMENT = "amendment"

# --- the honesty labels (contract D-3 §5/§6) --------------------------------

# The three stages whose runners surface a cost the ledger can carry. Measured
# off every shipped report, b001 through b003r2: S0 draws with an rng, the S1
# and S2/S3b sessions run on two different drivers and only the priced ones
# report usage, and s3_gate/s4_baselines/s6_package are local compute that
# never calls a model at all.
PRICED_STAGES = ("s2_implement", "s3_verify", "s5_battery")
# ONE constant, both consumers (the batch report's `cost_note` and the CLI/
# `--status` footer): a `$162.34` that silently covers 3 of 8 stages reads as
# the batch's price, and it is not.
COST_NOTE = (
    "usd totals cover " + " + ".join(PRICED_STAGES) + " only; s0/s1 sessions and the "
    "s3_gate/s4_baselines/s6_package compute are unpriced"
)
# The closing note for a batch that ended on HUMAN decisions rather than on
# failure: every slot terminal, nothing dead. b003r2's real shape — one game
# accepted and packaged, one pulled at review — and the reason a pull must
# never again print as BATCH ABORTED.
REVIEW_COMPLETE_NOTE = "review complete"

_UNSET = object()


class IllegalTransition(ValueError):
    """An edge architecture §4 does not draw. A ValueError: it is bad input."""


class LedgerError(ValueError):
    """The ledger on disk contradicts itself or the §4 machine."""


# --- hashing (the §2 provenance chain) --------------------------------------


def _sha256_file(path: Path) -> str | None:
    """sha256 of a file's bytes, or None when it does not exist yet."""
    path = Path(path)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _game_hash(worker_dir: Path | None) -> str | None:
    """`sha(game.py + solver.py)` — architecture §2 ⊕, the provenance chain.

    Literal concatenation in that order, the SAME definition as
    `s6_package.game_hash` (which is not imported here: this module stays
    import-light, and the S6 runner cross-checks the two at the one place the
    heavy import already exists).
    """
    if worker_dir is None:
        return None
    game = Path(worker_dir) / "game.py"
    if not game.is_file():
        return None
    digest = hashlib.sha256()
    digest.update(game.read_bytes())
    solver = Path(worker_dir) / "solver.py"
    if solver.is_file():
        digest.update(solver.read_bytes())
    return digest.hexdigest()


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# --- frames provenance (R-21, contract W2-C) --------------------------------
# `s3_verify.FRAMES_SUFFIX` is the authority for this name; it is reproduced
# here rather than imported for the reason every name in this module is (the
# state machine must not drag arcengine/numpy in, and `gen/s3_visual.py` names
# the same file for the same reason, with the same comment).
FRAMES_SIDECAR_SUFFIX = ".frames.json"       # s3_verify.FRAMES_SUFFIX
GAME_SOURCE_NAME = "game.py"                 # frames.GAME_SOURCE_NAME

# The artifact key the gate records provenance under, and the five values it can
# take. ONLY `provenance:mismatch` refuses: `provenance:unrecorded` is the whole
# pre-R-21 corpus (the seven shipped sidecars carry no stamp) and a sidecar that
# does not say what rendered it is exactly as trustworthy as it was yesterday.
FRAMES_PROVENANCE_ARTIFACT = "frames_provenance"
PROVENANCE_MATCH = "provenance:match"
PROVENANCE_MISMATCH = "provenance:mismatch"
PROVENANCE_UNRECORDED = "provenance:unrecorded"
PROVENANCE_NO_SIDECAR = "provenance:no-sidecar"
PROVENANCE_NO_SOURCE = "provenance:no-source"

# The distinct refusal reason. The audit's evidence (findings caveat 3, J-1
# escalation 1): facing-sentinel's `worker.frames.json` was rendered from
# `worker.staged/game.py` and then read as if it described `worker/game.py`
# (`C_INK_DIM` 4 in the frames, 1 in the source), so the audit's single worst
# visual instance was measured off a board the shipped game never paints.
FRAMES_PROVENANCE_REASON = "frames provenance: sidecar rendered from a different source"


def frames_provenance(worker_dir: Path | str) -> dict:
    """What the frames sidecar beside `worker_dir` says it was rendered FROM.

    Pure file reading — sha256 of `game.py`'s bytes against the stamp
    `frames.capture_worker` wrote into the sidecar — so this costs no engine
    run, imports nothing heavy, and can be asked at any point in a stage.

    Returns `{status, record, note, sidecar_source_sha256, game_sha256, path}`.
    `status` is one of the five `PROVENANCE_*` values; only `mismatch` is a
    refusal, and a sidecar with no stamp is `unrecorded`, never a refusal (an
    absent key means "this file does not say", which is every sidecar written
    before R-21 and must stay clean). A sidecar that will not parse is
    `unrecorded` too: reading it is the visual card's job and its malformed-file
    verdict is already a note there — this guard only ever answers the question
    it can answer from a stamp.
    """
    worker_dir = Path(worker_dir)
    path = worker_dir.with_name(worker_dir.name + FRAMES_SIDECAR_SUFFIX)
    game_sha = _sha256_file(worker_dir / GAME_SOURCE_NAME)

    def record(status: str, note: str, stamp: str | None = None) -> dict:
        return {
            "status": status, "record": status, "note": note,
            "sidecar_source_sha256": stamp, "game_sha256": game_sha, "path": str(path),
        }

    if not path.is_file():
        return record(PROVENANCE_NO_SIDECAR, f"no frames sidecar at {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return record(PROVENANCE_UNRECORDED, f"{path} could not be read ({exc})")
    if not isinstance(document, Mapping):
        return record(PROVENANCE_UNRECORDED, f"{path} did not parse to a mapping")
    stamp = document.get("source_sha256")
    if stamp is None:
        return record(
            PROVENANCE_UNRECORDED,
            f"{path.name} carries no source_sha256 — it was captured before R-21 and "
            "does not say which source rendered it",
        )
    stamp = str(stamp)
    if game_sha is None:
        return record(
            PROVENANCE_NO_SOURCE,
            f"{worker_dir / GAME_SOURCE_NAME} is not on disk, so the sidecar's stamp "
            "has nothing to be compared against",
            stamp,
        )
    if stamp == game_sha:
        return record(PROVENANCE_MATCH, f"{path.name} was rendered from these game.py bytes",
                      stamp)
    return record(
        PROVENANCE_MISMATCH,
        f"{path.name} records source_sha256={stamp[:12]}… but {GAME_SOURCE_NAME} hashes "
        f"to {game_sha[:12]}…",
        stamp,
    )


# --- the slot context handed to every runner --------------------------------


@dataclass(frozen=True)
class SlotContext:
    """Everything a stage runner is given: one slot, at one stage, right now."""

    cfg: Mapping
    batch_id: str
    slug: str            # the LEDGER key (stable from birth, see `slot_id`)
    index: int           # 1-based slot index within the batch
    state: str | None    # the state this stage runs FROM
    stage: str
    attempt: int         # 1-based invocation of this stage for this slot, this run
    batch_dir: Path
    ideas_dir: Path
    idea_path: Path
    corpus_dir: Path
    spec_dir: Path | None
    respec_count: int
    verifier_rejects: int
    green_failures: int
    history: tuple[dict, ...] = ()
    # The S2b verifier report this stage must ANSWER, set only when §3 S2b
    # escalated to S1 (`_maybe_respec` is the sole non-None constructor). Every
    # other context leaves it None and every stage then behaves exactly as it
    # did before. It is deliberately OUTSIDE the §2 hash chain: `input_hashes`
    # digests `STAGE_INPUTS`, and a re-spec's input is still the idea.
    escalation: Path | None = None

    @property
    def worker_dir(self) -> Path | None:
        """`corpus/<batch-id>/<slug>/worker/` — architecture §2's tree."""
        return None if self.spec_dir is None else self.spec_dir / WORKER_DIRNAME

    @property
    def verifier_report_path(self) -> Path | None:
        """`corpus/<batch-id>/<slug>/worker.verifier-report.json` — S2b's report.

        The ONE derivation of that sibling in the state machine: `input_paths`
        resolves the `verifier_report` stage input through it, and the §3 S2b
        escalation points S1 at the same file.
        """
        worker = self.worker_dir
        return None if worker is None else worker.with_name(worker.name + VERIFIER_REPORT_SUFFIX)

    @property
    def stage_findings_path(self) -> Path | None:
        """`corpus/<batch-id>/<slug>/worker.stage-findings.json` (P-1/P-2).

        The gate's / S4's / S6's failure payload for the NEXT S2 session, in the
        verifier feed's own `{verdict, reject_reasons}` shape and rendered by the
        same `s2_implement.findings_section`. Same `.with_name` idiom as the S2b
        report above, and deliberately OUTSIDE the §2 hash chain for the same
        reason `escalation` is: it is a message to the next build, not an input
        whose content identifies a stage's work.
        """
        worker = self.worker_dir
        return None if worker is None else worker.with_name(worker.name + STAGE_FINDINGS_SUFFIX)

    def input_paths(self) -> dict[str, Path]:
        """The files `STAGE_INPUTS[self.stage]` names, where they can resolve."""
        spec_dir, worker = self.spec_dir, self.worker_dir
        known: dict[str, Path | None] = {
            "idea": self.idea_path,
            "spec_yaml": None if spec_dir is None else spec_dir / "spec.yaml",
            "spec_md": None if spec_dir is None else spec_dir / "spec.md",
            "game": None if worker is None else worker / "game.py",
            "solver": None if worker is None else worker / "solver.py",
            "verifier_report": self.verifier_report_path,
            "metadata": (
                None if worker is None else worker.with_name(worker.name + ".s4") / "metadata.json"
            ),
        }
        unknown = [name for name in STAGE_INPUTS[self.stage] if name not in known]
        if unknown:
            raise KeyError(f"STAGE_INPUTS[{self.stage!r}] names unresolvable input(s) {unknown}")
        return {
            name: path
            for name in STAGE_INPUTS[self.stage]
            if (path := known[name]) is not None
        }

    def to_json_dict(self) -> dict:
        return {
            "slug": self.slug,
            "index": self.index,
            "state": self.state,
            "stage": self.stage,
            "attempt": self.attempt,
            "idea": str(self.idea_path),
            "spec_dir": None if self.spec_dir is None else str(self.spec_dir),
            "worker": None if self.worker_dir is None else str(self.worker_dir),
        }


def input_hashes(slot_ctx: SlotContext) -> dict:
    """`{spec, game, stage_input}` — the resume check's content hashes (§2 ⊕).

    `spec` and `game` are the provenance chain itself; `stage_input` digests
    the files `STAGE_INPUTS[stage]` names (plus, for S0, the scalar rng inputs
    it draws from), so "did this stage's inputs change?" is one comparison
    against the hash the ledger recorded for that stage.
    """
    if not isinstance(slot_ctx, SlotContext):
        # Duck-typed contexts are allowed (a test double), but they must carry
        # everything the §2 chain is computed from, and say so if they do not.
        missing = [name for name in ("cfg", "batch_id", "index", "stage", "spec_dir",
                                     "worker_dir", "respec_count", "input_paths")
                   if not hasattr(slot_ctx, name)]
        if missing:
            raise TypeError(
                f"input_hashes takes a SlotContext (or an object carrying its fields); "
                f"{type(slot_ctx).__name__} is missing {missing}"
            )
    spec_dir = slot_ctx.spec_dir
    spec = None if spec_dir is None else _sha256_file(spec_dir / "spec.yaml")
    game = _game_hash(slot_ctx.worker_dir)

    inputs = {name: _sha256_file(path) for name, path in slot_ctx.input_paths().items()}
    payload: dict = {"stage": slot_ctx.stage, "inputs": inputs}
    if slot_ctx.stage == "s0_ideas":
        # S0 reads no slot file: its inputs are the draw's identity.
        payload["draw"] = {
            "batch_id": slot_ctx.batch_id,
            "index": slot_ctx.index,
            "seed": _sample_seed(slot_ctx.cfg, slot_ctx.respec_count),
        }
    return {"spec": spec, "game": game, "stage_input": _digest(payload)}


# --- config -----------------------------------------------------------------


def _block(cfg: Mapping, name: str) -> Mapping:
    block = cfg.get(name) if isinstance(cfg, Mapping) else None
    if not isinstance(block, Mapping):
        raise KeyError(f"config has no '{name}' block (architecture §5 config surface)")
    return block


def _int_key(block: Mapping, where: str, key: str, *, low: int) -> int:
    if key not in block:
        raise KeyError(f"config missing {where}.{key} (architecture §5)")
    value = block[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise ValueError(f"{where}.{key} must be an int >= {low}, got {value!r}")
    return value


def batch_config(cfg: Mapping) -> dict:
    """`batch.{id,size,seed}`, validated. No new keys (B11 contract)."""
    batch = _block(cfg, "batch")
    batch_id = batch.get("id")
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise ValueError(f"batch.id must be a non-empty string, got {batch_id!r}")
    seed = batch.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError(f"batch.seed must be an int, got {seed!r}")
    return {"id": batch_id, "size": _int_key(batch, "batch", "size", low=1), "seed": seed}


def orchestrator_config(cfg: Mapping) -> dict:
    """`orchestrator.{workers,wave_size,max_attrition}`, validated (§5)."""
    orch = _block(cfg, "orchestrator")
    if "max_attrition" not in orch:
        raise KeyError("config missing orchestrator.max_attrition (architecture §4 kill criteria)")
    attrition = orch["max_attrition"]
    if isinstance(attrition, bool) or not isinstance(attrition, (int, float)):
        raise TypeError(f"orchestrator.max_attrition must be a number, got {attrition!r}")
    if not 0.0 <= float(attrition) <= 1.0:
        raise ValueError(f"orchestrator.max_attrition must sit in [0, 1], got {attrition!r}")
    # Contract P-5's arming knob is validated HERE, beside `workers`, so a
    # malformed value is a config error at second zero like every other
    # orchestrator key. It is deliberately NOT in the returned dict: that dict
    # is the report's `config.orchestrator` block, and an unarmed run's report
    # must gain no key at all (P-5's house rule). `_parallel_slots` is the
    # reader.
    _parallel_slots(cfg)
    # Contract E-2's two, validated HERE for exactly the same reason and on
    # exactly the same terms, and left out of the returned dict for exactly the
    # same one: an unarmed run's report must gain no key at all.
    _stage_fail_park(cfg)
    _respec_feasibility(cfg)
    return {
        "workers": _int_key(orch, "orchestrator", "workers", low=1),
        "wave_size": _int_key(orch, "orchestrator", "wave_size", low=1),
        "max_attrition": float(attrition),
    }


def _parallel_slots(cfg: Mapping) -> bool:
    """`orchestrator.parallel_slots` — does a wave SPAWN? (contract P-5 §1).

    Absent block, absent key and `false` all mean TODAY: one slot at a time,
    in waves, in this process — which is what every batch b001..b005r2 ran and
    what every config already on disk must keep running. `orchestrator.workers`
    has been written in all of them and read by nothing since B11, so the
    number alone can never be the arming: a resume of an old batch would
    otherwise fan out on a `workers: 4` nobody meant.

    `true` arms it, and the parallel path activates only with `workers > 1`
    beside it (`run_batch`) — armed at one worker there is nothing to spawn.

    Validated like every other knob in this file: a non-bool is a loud
    ValueError, and `1` is not a `true`.
    """
    orch = cfg.get("orchestrator") if isinstance(cfg, Mapping) else None
    if not isinstance(orch, Mapping) or "parallel_slots" not in orch:
        return False
    value = orch["parallel_slots"]
    if not isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 — a config defect; every knob here reports ValueError
            f"orchestrator.parallel_slots must be a bool, got {value!r}"
        )
    return value


def _orch_flag(cfg: Mapping, key: str) -> bool:
    """One `orchestrator.<key>` BOOL knob, read on `_parallel_slots`'s terms.

    Absent block, absent key and `false` all mean TODAY, byte for byte; `true`
    arms. A non-bool is a loud ValueError naming the key, and `1` is not a
    `true` — a knob that cannot mean what it says is a config defect, not a
    setting. Factored because contract E-2 adds two of these and the third
    (`parallel_slots`) carries a long contract comment of its own that would be
    lost inside a shared helper.
    """
    orch = cfg.get("orchestrator") if isinstance(cfg, Mapping) else None
    if not isinstance(orch, Mapping) or key not in orch:
        return False
    value = orch[key]
    if not isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 — a config defect; every knob here reports ValueError
            f"orchestrator.{key} must be a bool, got {value!r}"
        )
    return value


def _stage_fail_park(cfg: Mapping) -> bool:
    """`orchestrator.stage_fail_park` — does a downstream fail END? (E-2 §2).

    Absent or `false` is the TREADMILL every batch b001..g20261001-5 ran: over
    `verifier.reject_cap` a gate / S4 / S6 failure's reason gains
    `ESCALATE_MARK` and the slot re-specs again, with no terminal but
    `MAX_STEPS_PER_SLOT`'s crash. Armed, a downstream fail whose count EXCEEDS
    the cap parks the slot from its current state (`STAGE_REJECT_STATE`) —
    the operator's never-kill ruling applied to the lane P-A.4 did not reach.
    """
    return _orch_flag(cfg, "stage_fail_park")


def _respec_feasibility(cfg: Mapping) -> bool:
    """`orchestrator.respec_feasibility` — read the findings BEFORE S1 (E-2 §3).

    Absent or `false` is today: `_maybe_respec` spends the S1 session without
    ever reading the findings it is answering (it only `is_file()`-checks the
    escalation source), which is how g20261001-5 paid for a re-spec that left
    the spec hash unchanged. Armed, the findings are read first and a residual
    no spec amendment could answer skips the session and parks.
    """
    return _orch_flag(cfg, "respec_feasibility")


def _respec_cap(cfg: Mapping) -> int:
    """`orchestrator.respec_cap` — OPTIONAL; absent means `RESPEC_CAP` (2).

    Optional because every config written before the R2 ruling omits it, and
    the default IS the shipped behaviour. Present, it is validated like every
    other orchestrator int (>= 1, and `True` is not a 1). The block itself is
    `orchestrator_config`'s to require — a cfg with no `orchestrator:` at all
    simply takes the default here rather than raising twice over.
    """
    orch = cfg.get("orchestrator") if isinstance(cfg, Mapping) else None
    if not isinstance(orch, Mapping) or "respec_cap" not in orch:
        return RESPEC_CAP
    return _int_key(orch, "orchestrator", "respec_cap", low=1)


def _reject_cap(cfg: Mapping) -> int:
    """`verifier.reject_cap` — the ×N escalation bar; absent means the default.

    WIRED BY CONTRACT D-3 §1. Every batch config since b001 spells
    `verifier: {reject_cap: 2, …}` and NOTHING read it: the escalation compared
    against `VERIFIER_REJECT_CAP_ESCALATE`, so a batch that wrote 3 would still
    have escalated at 2 while its own config claimed otherwise. Both live
    configs write 2 — which is the default — so this changes no behaviour; it
    makes the number the config states the number the machine uses.

    OPTIONAL in the same way `orchestrator.respec_cap` is: a config (or a test
    cfg) with no `verifier:` block keeps the shipped default rather than
    raising for a key it never needed to write. Present, it is validated like
    every other int — >= 1, and `True` is not a 1.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or "reject_cap" not in verifier:
        return VERIFIER_REJECT_CAP_ESCALATE
    return _int_key(verifier, "verifier", "reject_cap", low=1)


def _round_cap(cfg: Mapping) -> int | None:
    """`verifier.round_cap` — the BOUND on a slot's verify rounds (P-3.2).

    Read beside `_reject_cap` and in the same style, with one difference that is
    the whole contract: ABSENT means None, and None means today's behaviour —
    unlimited rounds, exactly what every batch b001..b004 ran. There is no code
    default to fall back on, because there is no canon number: `reject_cap` is
    §4's own `×2 -> respec`, while this cap is contract P-3's answer to the operator's
    2026-09-29 ruling that "the pipeline must run WITHOUT human feedback", and a
    batch that writes no key must keep behaving as it always has.

    Present, it is an int >= 2 and anything else is a loud ValueError. TWO, not
    one: at 1 the very first reject would be the cap, so a slot would never get
    the ordinary reject -> re-implement lap that the ladder is made of — a value
    that cannot mean what it says is a config defect, not a setting.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or "round_cap" not in verifier:
        return None
    return _int_key(verifier, "verifier", "round_cap", low=2)


def _reconcile_early(cfg: Mapping) -> int:
    """`verifier.reconcile_early` — the SMALL-MISMATCH bar (contract P-A.1).

    Read beside `_round_cap` and in the same style. ABSENT is 0 and 0 is OFF:
    an unconfigured run is byte-for-byte today's, which is this workstream's
    house rule and the only reason a knob may exist at all.

    Armed with N >= 1 it implements OPERATOR RULING (2026-09-29, on the record,
    verbatim): "If there's a mismatch of 1-2 terms let's just go ahead with it."
    At ANY rejecting verify round whose findings are ALL declaration-side and
    number at most N, the spec's declarations are amended to the audited truth
    immediately instead of paying for a re-spec — and the amended spec still has
    to come back clean. It is not leniency: the verifier's finding is written
    into the spec, never waived.

    Present, it is an int >= 0 and anything else — `-1`, `"x"`, `True`, `2.0` —
    is a loud ValueError naming the key, because a knob that cannot mean what it
    says is a config defect, not a setting.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or "reconcile_early" not in verifier:
        return 0
    return _int_key(verifier, "verifier", "reconcile_early", low=0)


def _auto_accept(cfg: Mapping) -> bool:
    """`review.auto_accept` — does `played` travel to `reviewed` on its own?

    Contract P-3.3. Absent block, absent key and `false` all mean TODAY: the
    slot stops at `played`, the run prints the `--review` recipe and a HUMAN
    decides (architecture §3 S5 / §4). `true` arms the operator's 2026-09-29 autonomy
    ruling — the slot travels `played --> reviewed` itself and goes on to S6 in
    the same run, and the human oversight happens post-package.

    Validated like every other knob in this file: a non-bool is a loud
    ValueError, and `1` is not a `true`.
    """
    review = cfg.get("review") if isinstance(cfg, Mapping) else None
    if not isinstance(review, Mapping) or "auto_accept" not in review:
        return False
    value = review["auto_accept"]
    if not isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 — a config defect; every knob here reports ValueError
            f"review.auto_accept must be a bool, got {value!r}"
        )
    return value


def batch_dir(cfg: Mapping) -> Path:
    """`out/batches/<batch.id>/` — the ledger's and the batch report's home."""
    return BATCHES_ROOT / batch_config(cfg)["id"]


def slot_report_path(bdir: Path, slug: str) -> Path:
    """`out/batches/<id>/<slug>.slot-report.json` — one child's sidecar (P-5 §2)."""
    return Path(bdir) / f"{slug}{SLOT_REPORT_SUFFIX}"


def slot_log_path(bdir: Path, slug: str) -> Path:
    """`out/batches/<id>/<slug>.slot.log` — one child's stdout+stderr (P-5 §6)."""
    return Path(bdir) / f"{slug}{SLOT_LOG_SUFFIX}"


def s0_draw_lock_path(batch_id: str) -> Path:
    """`out/ideas/<batch>/.sample-batch.lock` — the S0 draw's mutex (P-5 add. 1).

    ONE per batch, not one per `respec-<k>/` sub-draw: the thing two drawers
    really collide over is the dedupe history, which is shared across every
    draw a batch makes, and `respec-<k>/` lives inside this directory anyway.
    """
    return IDEAS_ROOT / batch_id / S0_DRAW_LOCK_NAME


def slot_id(batch_id: str, index: int) -> str:
    """The ledger key for slot `index`: stable from birth through re-samples.

    NOT the game's slug (which only exists once S1 names it, and changes under
    a re-sample) — the ledger needs one key per SLOT for its whole life.
    """
    if not isinstance(index, int) or isinstance(index, bool) or index < 1:
        raise ValueError(f"slot index must be a positive int, got {index!r}")
    return f"{batch_id}-s{index:03d}"


def _sample_seed(cfg: Mapping, respec_count: int) -> int:
    """The S0 seed for a slot's `respec_count`-th sampling (D13 determinism).

    A re-sample MUST draw something new or the linter kills it again for the
    same reason; S0 has no "exclude this kill reason" knob (B4), so the
    re-draw is a deterministic seed stride and the gap is reported, not hidden.
    """
    return batch_config(cfg)["seed"] + 1_000_003 * int(respec_count)


# --- the ledger -------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat()


def legal_transition(from_state: str | None, to_state: str) -> bool:
    """Is `from_state -> to_state` an edge architecture §4 draws?"""
    return to_state in TRANSITIONS.get(from_state, {})


def assert_transition(from_state: str | None, to_state: str) -> str:
    """The edge's §4 label, or `IllegalTransition`. The one gate on the ledger."""
    if from_state is not BIRTH and from_state not in STATES:
        raise IllegalTransition(f"unknown from-state {from_state!r} (states: {list(STATES)})")
    if to_state not in STATES:
        raise IllegalTransition(f"unknown to-state {to_state!r} (states: {list(STATES)})")
    allowed = TRANSITIONS.get(from_state, {})
    if to_state not in allowed:
        raise IllegalTransition(
            f"architecture §4 draws no edge {from_state!r} -> {to_state!r}; "
            f"from {from_state!r} it draws {sorted(allowed) or 'nothing (terminal)'}"
        )
    return allowed[to_state]


def _check_hashes(hashes: object) -> dict:
    if not isinstance(hashes, Mapping):
        raise TypeError(f"hashes must be a mapping with keys {list(HASH_KEYS)}, got {hashes!r}")
    if set(hashes) != set(HASH_KEYS):
        raise ValueError(f"hashes keys must be exactly {list(HASH_KEYS)}, got {sorted(hashes)}")
    for key in HASH_KEYS:
        value = hashes[key]
        if value is not None and not isinstance(value, str):
            raise TypeError(f"hashes.{key} must be a hex string or None, got {value!r}")
    return {key: hashes[key] for key in HASH_KEYS}


def _check_cost(cost: object) -> dict | None:
    if cost is None:
        return None
    if not isinstance(cost, Mapping):
        raise TypeError(f"cost must be None or a mapping with keys {list(COST_KEYS)}, got {cost!r}")
    if set(cost) != set(COST_KEYS):
        raise ValueError(f"cost keys must be exactly {list(COST_KEYS)}, got {sorted(cost)}")
    for key in COST_KEYS:
        value = cost[key]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise TypeError(f"cost.{key} must be a number or None, got {value!r}")
    return {key: cost[key] for key in COST_KEYS}


def _line(*, slug: str, from_state: str | None, to_state: str, reason: str,
          hashes: Mapping, cost: Mapping | None) -> dict:
    """One validated ledger line, in the frozen key order."""
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError(f"slug must be a non-empty string, got {slug!r}")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"reason must be a non-empty string, got {reason!r}")
    assert_transition(from_state, to_state)
    return {
        "slug": slug,
        "from": from_state,
        "to": to_state,
        "reason": reason,
        "hashes": _check_hashes(hashes),
        "cost": _check_cost(cost),
        "ts": _now(),
    }


def _append_lines(ledger_path: Path, lines: Sequence[dict]) -> list[dict]:
    """Append validated lines in ONE write (+fsync): the ledger is the state.

    THE LOCK (contract P-5 §3) is what keeps that true when a batch runs
    parallel slots: every child appends its own slug's lines to this one file,
    and `flock(LOCK_EX)` — held from before the write to the close — is what
    keeps a call's blob whole and, with it, the TWO-LINE PAIRS adjacent (the
    battery-crash route and the review pair are appended as one blob precisely
    so neither half can be lost in a gap). Interleaving BETWEEN calls is legal:
    `replay_ledger` keys everything by slug and checks each slug's own
    ordering, so lines from two slugs may arrive in any order.

    POSIX only, which is this project's only claim (macOS/Linux).
    """
    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    blob = "".join(json.dumps(line) + "\n" for line in lines)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    return list(lines)


def append_transition(ledger_path: Path, *, slug: str, from_state: str | None,
                      to_state: str, reason: str, hashes: Mapping,
                      cost: Mapping | None) -> dict:
    """Append ONE §4 transition and return the line.

    Callers append only AFTER the stage's artifact is on disk (§4: the ledger
    is the resume state, so a line is a claim that the work exists).
    """
    line = _line(slug=slug, from_state=from_state, to_state=to_state,
                 reason=reason, hashes=hashes, cost=cost)
    _append_lines(ledger_path, [line])
    return line


def _empty_rejects() -> dict:
    return {"lint_kill": 0, "resample": 0, "verifier": 0, "battery_crash": 0, "green_death": 0}


def _empty_cost() -> dict:
    return {"usd": None, "tokens_in": None, "tokens_out": None}


def _add_cost(total: dict, cost: Mapping | None) -> None:
    if cost is None:
        return
    for key in COST_KEYS:
        value = cost.get(key)
        if value is None:
            continue
        total[key] = value if total[key] is None else total[key] + value


def replay_ledger(ledger_path: Path) -> dict:
    """Replay the jsonl into `slug -> {state, history, rejects, cost, …}`.

    Pure function of the file. Every line is validated against the frozen key
    set AND against §4 (each line's `from` must be the slug's current state),
    so a ledger that cannot have been produced by this machine raises here
    instead of resuming into nonsense. A missing file replays to `{}`.
    """
    ledger_path = Path(ledger_path)
    table: dict[str, dict] = {}
    if not ledger_path.is_file():
        return table
    with ledger_path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            if not raw.strip():
                continue
            try:
                line = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LedgerError(f"{ledger_path}:{lineno}: corrupt jsonl: {exc}") from exc
            if not isinstance(line, Mapping) or set(line) != set(LEDGER_KEYS):
                raise LedgerError(
                    f"{ledger_path}:{lineno}: line keys must be exactly {list(LEDGER_KEYS)}, "
                    f"got {sorted(line) if isinstance(line, Mapping) else type(line).__name__}"
                )
            slug = line["slug"]
            if not isinstance(slug, str) or not slug:
                raise LedgerError(f"{ledger_path}:{lineno}: slug must be a non-empty string")
            entry = table.setdefault(slug, {
                "state": BIRTH, "history": [], "rejects": _empty_rejects(),
                "cost": _empty_cost(), "terminal": False,
                "first_ts": line["ts"], "last_ts": line["ts"],
            })
            try:
                assert_transition(line["from"], line["to"])
            except IllegalTransition as exc:
                raise LedgerError(f"{ledger_path}:{lineno}: {exc}") from exc
            if line["from"] != entry["state"]:
                raise LedgerError(
                    f"{ledger_path}:{lineno}: {slug} is in state {entry['state']!r} but the line "
                    f"departs from {line['from']!r} — the ledger does not replay"
                )
            _check_hashes(line["hashes"])
            _check_cost(line["cost"])
            entry["state"] = line["to"]
            entry["terminal"] = line["to"] in TERMINAL
            entry["history"].append(dict(line))
            entry["last_ts"] = line["ts"]
            _add_cost(entry["cost"], line["cost"])
            edge = (line["from"], line["to"])
            if edge == ("ideated", "respec"):
                entry["rejects"]["lint_kill"] += 1
            elif edge == ("respec", "ideated"):
                entry["rejects"]["resample"] += 1
            elif edge == ("implemented", "spec_ok"):
                entry["rejects"]["verifier"] += 1
            elif edge == ("played", "implemented"):
                entry["rejects"]["battery_crash"] += 1
            elif edge == ("spec_ok", "dead"):
                entry["rejects"]["green_death"] += 1
    return table


def _verifier_rejects_against(history: Sequence[Mapping], spec: str | None) -> int:
    """Verifier rejects standing against THIS spec (§2: hashes are identity).

    A re-spec changes `spec_hash`, which is exactly when the ×2 counter should
    start over — so the counter is derived from content, not kept in memory,
    and survives a kill.

    AN ACCEPT ZEROES THE COUNT. Rejects are counted only from the most recent
    `implemented --> verified` line carrying this same spec hash; with no such
    accept, every reject against the spec counts, exactly as before.

    WHY (R2 pilot, night of 2026-09-22): S2b accepted a worker and, after a
    transient crash knocked the slot back to `implemented`, rejected the
    identical bytes on the §4 re-walk an hour later. The straight sum counted
    that lone post-accept reject alongside a reject from BEFORE the accept and
    escalated ×2 against a spec that had already passed everything. An accept
    is a verdict about the spec too: it says the rejects before it were
    answered, so what the cap measures is the rejects SINCE — consecutive
    failure, which is what "2 verifier rejects → escalate" (§3 S2b) means.

    CONTRACT P-2 §3 — THE LOOP GUARD. The gate's, S4's and S6's failures now
    route to `spec_ok` too (see `STAGE_FAILURE`), and they COUNT toward this
    same ladder, so a render bug the implementer cannot fix escalates to a
    re-spec instead of looping implement↔gate silently.

    AND THE LADDER HAD NO TOP, measured (contract E-2 §2). "Ultimately to the
    respec cap" is what this docstring claimed and it was NOT true:
    `orchestrator.respec_cap` bounds only the S1 lint-kill loop (`slot.state ==
    "respec"`), nothing bounds the ESCALATED re-spec, and `verifier.round_cap`
    counts `implemented --> spec_ok` only — so over the cap the reason merely
    gained `ESCALATE_MARK` and the slot re-specced again. g20261001-5 rode that
    to "gate fail 2/1" and "package fail 4/1". `orchestrator.stage_fail_park`,
    armed, is the top: over the cap the slot PARKS from its current state.

    They are counted on a SEPARATE tally that an accept does NOT zero, and that
    is load-bearing rather than fussy. A gate fail at `verified` is followed by
    a re-implement and a fresh S2b round; if that round passes — which is the
    normal case, since S2b's judgement was never what failed — a shared counter
    would be zeroed by the accept and the next gate fail would start again at 1.
    The slot would ping-pong until `MAX_STEPS_PER_SLOT` crashed the run, which
    is precisely the infinite loop this contract exists to close. An S2b accept
    answers S2b's rejects; it says nothing about a board the gate refused.

    That separate tally is also what `orchestrator.stage_fail_park` measures its
    cap against (contract E-2 §2), which is why that knob can bite where
    `verifier.round_cap` cannot: this number counts the DOWNSTREAM rejects, and
    they are the ones that were looping.
    """
    verifier = 0      # rejects since the last accept (§3 S2b's consecutive pair)
    downstream = 0    # gate/S4/S6 rejects against this spec; an accept cannot answer them
    for line in history:
        if line["hashes"]["spec"] != spec:
            continue
        edge = (line["from"], line["to"])
        if edge == ("implemented", "verified"):
            verifier = 0
        elif edge == ("implemented", "spec_ok"):
            verifier += 1
        elif edge in DOWNSTREAM_REJECT_EDGES:
            downstream += 1
    return verifier + downstream


def respec_runs_from_ledger(history: Sequence[Mapping]) -> int:
    """How often this slot was RE-SPEC'd, counted off the ledger (D-3 §4).

    `_Slot.respec_runs` counts only the re-specs THIS process ran, and every
    real batch reaches `played` across several resumes — so every shipped
    report (b001, b002, b003r2) records `respec_runs: 0` against ledgers
    carrying three escalated rounds apiece. The ledger is the durable record,
    so the REPORT derives the number from it and the counter stays for
    in-process logic only.

    BOTH §4 re-spec flavors count, each at the line that PROVES a re-spec
    happened (the re-spec itself appends none: §4 draws no `spec_ok --> respec`
    edge, and an escalated re-spec rewrites spec.yaml in place):

    * the verifier escalation — an `implemented --> spec_ok` line whose reason
      carries `ESCALATE_MARK`. `_maybe_respec` runs S1 again on exactly that
      line, on this run or on the resume that follows it. The EDGE cannot be
      the discriminator: an ordinary reject below the cap travels the same one
      and re-specs nothing, which is why the reason is read. Contract P-2 §3
      puts the gate's, S4's and S6's rejects on the same ladder, so their edges
      (`DOWNSTREAM_REJECT_EDGES`) count here too when their reason carries the
      mark — the re-spec they trigger is a real re-spec and must be reported as
      one. The MARK rather than the prefix: `ESCALATE_PREFIX` says "verifier
      reject ×N", which a gate fail is not, while every escalation reason ever
      written ends with the mark;
    * the lint kill's re-sample — a `respec --> ideated` line: S0 re-drew and
      S1 wrote this slot a second spec. The kill edge (`ideated --> respec`)
      is deliberately NOT counted: a kill that lands on
      `orchestrator.respec_cap` blocks the slot and no re-spec follows it, so
      counting the kill would report work that never ran.

    AND ONE FLAVOUR IS SUBTRACTED (contract E-2 §3). The sentence above —
    "`_maybe_respec` runs S1 again on exactly that line" — stopped being true
    when `orchestrator.respec_feasibility` was armed: a futile escalation now
    parks the slot WITHOUT invoking S1, and the escalation line it answered
    still carries `ESCALATE_MARK` (it was written by the stage that failed,
    before anybody looked at the findings). Counting it would put a paid
    session on the report that the whole knob exists to not pay for, which is
    the same honesty defect D-3 §4 wrote this function to fix. The futile park
    is terminal and answers exactly one escalation, so one park subtracts one
    run — read off the ledger, like everything else here.
    """
    runs = 0
    for line in history:
        edge = (line["from"], line["to"])
        resampled = edge == ("respec", "ideated")
        escalated = _escalation_line(line)
        if resampled or escalated:
            runs += 1
        elif line["to"] == "parked" and str(line["reason"]).startswith(RESPEC_FUTILE_PREFIX):
            runs -= 1
    return max(runs, 0)


def _verify_rounds(history: Sequence[Mapping]) -> int:
    """Verify rounds this slot has completed STILL REJECTING (contract P-3.2).

    Every `implemented --> spec_ok` line in the slot's whole life, across EVERY
    spec it has ever had. Deliberately not `_verifier_rejects_against`, which is
    per-spec because a re-spec answers the rejects it was written for: this
    counter is the slot's BOUND, and the thing it must bound is a slot that
    re-specs forever. Under `verifier.reject_cap: 1` — what b005 arms — every
    reject re-specs and the per-spec count would be 1 on every round, so a cap
    built on it could never bite.

    A round that PASSED is not counted: the slot moved on, and a later knock-back
    (a battery crash at `played --> implemented`) must not spend a round the
    audit never rejected.
    """
    return sum(1 for line in history
               if (line["from"], line["to"]) == ("implemented", "spec_ok"))


def last_park_line(history: Sequence[Mapping]) -> dict | None:
    """The park a slot is sitting on: the LAST `… --> parked` line (contract E-5).

    ONE derivation, two readers, and they are the two halves of this contract:
    `unpark_slot` lifts the slot back to this line's `from` (never to a state a
    caller named), and `_slot_report` quotes this line's `reason` for the batch
    report's `parked` block. Both read the LAST such line because a lift makes a
    second park possible — "a slot lifted and re-parked counts once, with the
    LATEST park reason" (E-5 §4) — and before this contract there could only
    ever be one, which is why the derivation changes no pre-E-5 report byte.

    `None` means the slot has never parked. Read off the ledger like every other
    count in this module, so it survives a kill and a resume.
    """
    for line in reversed(list(history)):
        if line["to"] == "parked":
            return dict(line)
    return None


def _reconciled_before(history: Sequence[Mapping]) -> bool:
    """Has this slot already spent its ONE mechanical reconciliation (P-3.2a)?

    Read off the ledger reason, so it survives a park and a resume like every
    other count in this module. One is the whole allowance: the reconciliation
    buys a single confirming round, and a slot that rejects AFTER its
    declarations were amended to match the audit has a residual no declaration
    can answer.

    P-A.1's EARLY reconciliations are deliberately NOT counted here. They carry
    their own prefix and this reads only the round cap's, because the contract
    says a slot that needs the early amendment every round "still reaches
    round_cap, where the SAME reconciliation runs (path a) or the slot parks" —
    so the cap's one allowance is the cap's own, not one the early path can have
    spent in advance. What the early path does spend is `_verify_rounds` and the
    reject ladder, which is what makes the cap reachable at all.
    """
    return any(str(line["reason"]).startswith(RECONCILE_PREFIX) for line in history)


def _changes_in_reason(reason: str) -> list[str]:
    """The `+term`/`-term` tokens a RECONCILIATION line's reason carries (E-2 §1).

    THE LEDGER IS THE MEMORY. The amendment a reconciliation made exists in
    exactly one durable place — the reason text `_reconcile_changes` wrote — so
    this reads that text, the same read-off-the-ledger discipline
    `_reconciled_before` above and every count in this module keeps, and it
    therefore survives a kill, a park and a resume.

    BOTH prefixes are parsed, because both paths amend declarations and the
    ping-pong g20261001-5 measured crossed them (line 12 was P-A.1's early path
    at `+manip.terraform`, line 14 the same path at `-manip.terraform`):

        declaration reconciled to audit: +a, -b (round_cap 4; …)
        declaration reconciled early (<=2): +a, -b (…)

    The changes segment is bounded on the right by the ` (` that opens the
    notes, which is unambiguous because `_reconcile_changes` joins NAMES and a
    §11 term carries no bracket. Anything that is not one of the two
    reconciliation reasons yields `[]` — a churn refusal (which amends nothing)
    must never read as an amendment, and `CHURN_REFUSED_PREFIX` is distinct
    precisely so it cannot.
    """
    if reason.startswith(RECONCILE_PREFIX):
        tail = reason[len(RECONCILE_PREFIX):]
    elif reason.startswith(RECONCILE_EARLY_PREFIX):
        # "<=2): +a, -b (…)" — the cap, then the separator its own format string
        # put there. No separator means a reason this helper does not understand.
        _cap, sep, tail = reason[len(RECONCILE_EARLY_PREFIX):].partition("): ")
        if not sep:
            return []
    else:
        return []
    segment = tail.split(" (", 1)[0]
    return [token for token in (part.strip() for part in segment.split(","))
            if token.startswith(("+", "-")) and len(token) > 1]


def _reconciliation_memory(history: Sequence[Mapping]) -> dict[str, set[str]]:
    """Every name a PRIOR reconciliation added or withdrew (contract E-2 §1).

    `{"added": {...}, "withdrawn": {...}}`, accumulated over the slot's whole
    life. A name can appear in both on a ledger written BEFORE this contract —
    g20261001-5's is exactly such a ledger — and that is not a contradiction to
    resolve here: a name on both lists has been settled in both directions, so
    a finding in either direction is churn and `_split_churn` drops it either
    way.

    SCOPE, and it is the contract's: reconciliation-authored changes ONLY. A
    term S1 wrote and the blind audit withdraws by a first-ever subtractive
    finding is in neither set, and its withdrawal is untouched behaviour.
    """
    memory = {"added": set(), "withdrawn": set()}
    for line in history:
        for token in _changes_in_reason(str(line["reason"])):
            key = "added" if token[0] == "+" else "withdrawn"
            memory[key].add(token[1:])
    return memory


def _churn_refused_before(history: Sequence[Mapping]) -> set[str]:
    """The churn tokens this slot has ALREADY had refused once (contract E-2 §1).

    The refusal buys the slot one revalidating round — the same single
    allowance the round cap's reconciliation gets, and for the same reason: a
    finding that recurs AFTER the machine has told the ledger it is churn is no
    longer a one-off flip, and a second free round would be a livelock with no
    terminal but `MAX_STEPS_PER_SLOT`'s crash. On the repeat the slot takes
    today's ladder (below the cap) or parks (at it).
    """
    refused: set[str] = set()
    for line in history:
        reason = str(line["reason"])
        if not reason.startswith(CHURN_REFUSED_PREFIX):
            continue
        segment = reason[len(CHURN_REFUSED_PREFIX):].split(" (", 1)[0]
        refused.update(token for token in (part.strip() for part in segment.split(","))
                       if token.startswith(("+", "-")) and len(token) > 1)
    return refused


def _churn_token(reason: Mapping, memory: Mapping[str, set[str]]) -> str | None:
    """Would reconciling THIS finding undo a prior reconciliation? (E-2 §1).

    Returns the refused amendment as a `+name`/`-name` token, or None when the
    finding is not churn. The two directions are symmetric and both are the
    contract's rule: never WITHDRAW what a reconciliation ADDED, and never
    RE-ADD what a reconciliation WITHDREW.
    """
    code = str(reason.get("code"))
    if code in RECONCILABLE_ADDITIVE_CODES:
        # `undeclared-term` names a `term`, `undeclared-deception` a `lever`;
        # `_reconcile_declarations` records both in `added`, so both are read.
        name = reason.get("term") if reason.get("term") is not None else reason.get("lever")
        if isinstance(name, str) and name in memory["withdrawn"]:
            return f"+{name}"
        return None
    if code in RECONCILABLE_SUBTRACTIVE_CODES:
        name = reason.get("term")
        if isinstance(name, str) and name in memory["added"]:
            return f"-{name}"
    return None


def _split_churn(reasons: Sequence[Mapping],
                 history: Sequence[Mapping]) -> tuple[list[dict], list[str]]:
    """`(the findings still worth reconciling, the churn tokens refused)`.

    Contract E-2 §1, and it applies to BOTH reconciliation paths because the
    rule is about the amendment, not about which knob asked for it. The kept
    findings proceed exactly as they did before this contract; the churn is
    dropped from the reconcilable set and NAMED by every caller.
    """
    memory = _reconciliation_memory(history)
    kept: list[dict] = []
    churn: list[str] = []
    for reason in reasons:
        token = _churn_token(reason, memory)
        if token is None:
            kept.append(dict(reason))
        elif token not in churn:
            churn.append(token)
    return kept, churn


def _escalation_line(line: Mapping) -> bool:
    """Is this ledger line a reject that ESCALATED to a re-spec?

    One definition, three readers (`respec_runs_from_ledger`, `_escalated`, the
    report). An escalation is a reject landing on `spec_ok` — the verifier's own
    §4 edge, or one of contract P-2's three (`DOWNSTREAM_REJECT_EDGES`) — whose
    reason carries `ESCALATE_MARK`.
    """
    edge = (line["from"], line["to"])
    if edge != ("implemented", "spec_ok") and edge not in DOWNSTREAM_REJECT_EDGES:
        return False
    return ESCALATE_MARK in str(line["reason"])


def _escalated(history: Sequence[Mapping], spec: str | None) -> bool:
    """Is the slot sitting on an escalated reject (→ respec) ?"""
    if not history:
        return False
    last = history[-1]
    return _escalation_line(last) and last["hashes"]["spec"] == spec


# --- default runners (the REAL stages; tests always inject fakes) -----------


def _result(ok: bool, to_state: str, reason: str, *, cost: Mapping | None = None,
            artifacts: Mapping | None = None,
            findings: Sequence[Mapping] | None = None) -> dict:
    row = {"ok": ok, "to_state": to_state, "reason": reason,
           "cost": dict(cost) if cost is not None else None,
           "artifacts": dict(artifacts or {})}
    # Only a failure that HAS rows carries the key, so every clean result — and
    # every failure that says it all in its reason — is the mapping this helper
    # has always returned (contracts P-1 §2, P-2 §1/§2).
    if findings:
        row["findings"] = [dict(finding) for finding in findings]
    return row


def _cost(usd: object, tokens_in: object, tokens_out: object) -> dict | None:
    """A cost row from numbers a stage REPORTED. All-unreported -> None."""
    def number(value: object) -> float | int | None:
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value
    row = {"usd": number(usd), "tokens_in": number(tokens_in), "tokens_out": number(tokens_out)}
    return None if all(value is None for value in row.values()) else row


_CARD_ROW_CAP = 12        # rows quoted per failing check
_CARD_ROW_CHARS = 400     # per row; a prompt section, not a data dump


def _failing_card_rows(check: Mapping | None) -> list[str]:
    """The visual card's OWN failing rows for one check, rendered compactly.

    Contract P-2 §1 asks the gate's payload to carry "the card's failing table
    rows" and the card's checks do not share a table shape — `role-footprint`
    keys its verdicts by role, `declared-vs-painted` keeps a `violations` list,
    `win-render` and the rest keep per-level entries. So this walks the block
    rather than knowing six schemas, and quotes exactly the nodes that SAY they
    failed (`status == "fail"`, or `passed is False`) plus every entry of a
    `violations` list, which is a list of failures by definition.

    Bounded on purpose: this text is spliced into an implementer prompt, so it
    is capped at `_CARD_ROW_CAP` rows of `_CARD_ROW_CHARS` each. Nothing here
    may raise — the card is evidence and a malformed one must not take down the
    routing that is reporting the failure.
    """
    rows: list[str] = []

    def walk(node: object, label: str) -> None:
        if len(rows) >= _CARD_ROW_CAP:
            return
        if isinstance(node, Mapping):
            if node is not check and (node.get("status") == "fail"
                                      or node.get("passed") is False):
                rows.append(f"{label}: {json.dumps(node, sort_keys=True, default=str)}")
                return
            for key, value in node.items():
                walk(value, f"{label}.{key}" if label else str(key))
            return
        if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            violations = label.endswith("violations")
            for index, item in enumerate(node):
                if violations and isinstance(item, Mapping):
                    if len(rows) >= _CARD_ROW_CAP:
                        return
                    rows.append(
                        f"{label}[{index}]: {json.dumps(item, sort_keys=True, default=str)}"
                    )
                    continue
                walk(item, f"{label}[{index}]")

    if not isinstance(check, Mapping):
        return []
    walk(check, "")
    return [row[:_CARD_ROW_CHARS] for row in rows]


#: The namespace every gate-side finding code lives under (`gate.<check>`).
GATE_CODE_PREFIX = "gate."


def _gate_code(check_id: str) -> str:
    """`gate.<check>` for a gate check id, prefixed EXACTLY once.

    CONTRACT H-1 item 9 (2026-10-06). The gate's checks come from two modules
    that spell their ids differently: the visual card's are BARE
    (`s3_visual.ROLE_FOOTPRINT_CHECK == "role-footprint"`), but contract B3's
    two already carry the namespace (`s3_gate.TERM_WITNESS_CHECK ==
    "gate.term-witness"`, `s3_gate.REFUSAL_PERSISTENCE_CHECK`). The B3 fail
    loop below prefixed unconditionally, so a failing term-witness row was
    filed under `gate.gate.term-witness`. This is the producer fixed; the
    READERS need nothing, and that is on purpose: `_spec_answerable` is a
    closed-list membership test whose default is "answerable", and neither B3
    check is on the list, so a shipped report carrying the historic doubled
    code reads exactly as it always did (shipped reports are immutable).
    """
    return check_id if check_id.startswith(GATE_CODE_PREFIX) else GATE_CODE_PREFIX + check_id


def _visual_finding(check_key: str, check: Mapping | None) -> dict:
    """One `{code, detail}` row for a failing visual check (contract P-2 §1)."""
    note = "" if not isinstance(check, Mapping) else str(check.get("note") or "")
    parts = [part for part in (note, *_failing_card_rows(check)) if part]
    return {"code": _gate_code(check_key),
            "detail": " | ".join(parts) or f"the visual check {check_key} failed"}


def _s4_cap_fit_detail(report: Mapping, out_dir: Path) -> str:
    """The cap-fit rows a rejected S4 wants the rebuild to fix (contract P-2 §2).

    §3's route for this failure is "S2 (cap bug)": what the implementer must
    change is the BUDGET the game source enforces, per level. S4 already knows
    which levels do not fit — `result.attempts[-1].capfit` is the shipped
    vector's own row set — so the finding quotes those rows rather than telling
    the rebuild only that something did not fit. A report shaped differently
    (an older run, a fake runner) falls back to naming the report on disk, which
    is always true.
    """
    try:
        rows = report["result"]["attempts"][-1]["capfit"]
        failing = [row for row in rows if not (row["fits"] and row["battery_fits"])]
    except (KeyError, IndexError, TypeError):
        failing = []
    if not failing:
        return (f"S4 returned {report.get('verdict')!r}; the measured rows are in "
                f"{out_dir / 's4-report.json'}")
    named = "; ".join(
        f"level {row['level']}: baseline {row['baseline']} against cap {row['cap']}"
        for row in failing[:_CARD_ROW_CAP]
    )
    return (f"the enforced budget cannot hold the baseline on {len(failing)} level(s) — "
            f"{named}. architecture §3 routes this to S2: the CAP in the game source is "
            f"the bug, not the baseline")


def _require_spec_dir(ctx: SlotContext) -> Path:
    if ctx.spec_dir is None:
        raise FileNotFoundError(
            f"{ctx.slug}: no spec dir under {ctx.corpus_dir} carries idea {ctx.idea_path.name} — "
            f"S1 has not written one (stage {ctx.stage})"
        )
    return ctx.spec_dir


def _gate_verifier_report(ctx: SlotContext, report: dict) -> dict:
    """The report the gate's layer 3 consumes, with the LEDGER senior on vintage.

    Verify overwrites `worker.verifier-report.json` every round, so after an
    accept is LATCHED (`_latched_verify`) the file on disk can still be a
    LATER spurious reject of the identical bytes — the exact variance class
    the latch exists for. The gate consumes a verdict, it never re-decides
    one (architecture §3 layer 3); handing it stale evidence re-imports the
    coin flip. Rule, mirroring the latch's asymmetry: when the ledger holds
    an implemented→verified ACCEPT whose `hashes.game` equals the game on
    disk NOW, that accept is senior to an on-disk reject of the same bytes —
    the report passes through with its verdict latched and the provenance
    recorded under `ledger_latch`. A report already carrying an accept, or a
    reject with NO recorded accept of these bytes, passes through untouched.
    """
    if report.get("verdict") == "pass":
        return report
    current = _game_hash(ctx.spec_dir / WORKER_DIRNAME if ctx.spec_dir else None)
    if current is None:
        return report
    for line in reversed(ctx.history):
        if (line.get("from") == "implemented" and line.get("to") == "verified"
                and (line.get("hashes") or {}).get("game") == current):
            latched = dict(report)
            latched["verdict"] = "pass"
            latched["ledger_latch"] = {
                "from_ts": line.get("ts"),
                "overridden_disk_verdict": report.get("verdict"),
                "note": ("on-disk report is a later reject of identical bytes; the "
                         "ledger accept is senior (§2 hashes are identity)"),
            }
            return latched
    return report


def _latched_verify(ctx: SlotContext, *, report_path: Path, frames_path: Path) -> dict | None:
    """S2b's recorded ACCEPT, re-served for game bytes that already earned it.

    THE INCIDENT (R2 pilot, night of 2026-09-22). S2b accepted a worker —
    `implemented --> verified`, "S2b clean", the game hash in the line — and
    REJECTED THE IDENTICAL BYTES on a §4 re-walk an hour later, after a
    transient network error crashed the battery and knocked the slot back to
    `implemented`. The audit leg is an LLM pass, so its verdict is
    nondeterministic at the margin: re-running it over unchanged bytes is a
    coin flip paid for twice, in dollars and in a spurious reject.

    §2 says hashes are identity. A recorded accept whose `hashes.game` equals
    the game on disk NOW is a verdict about exactly these bytes, so serving it
    again is content addressing, not caching. Its artifacts must still be on
    disk — they are the next stage's input (§3 S3's gate reads the report) —
    and when they are not, this returns None and the full real verify runs.
    Missing evidence never errors here; it just un-latches (fail-safe).

    ASYMMETRY IS THE DESIGN. Only ACCEPTS latch. A recorded REJECT never
    short-circuits anything: rejects always re-run. Freezing a possibly
    spurious reject would wedge the slot — nothing but a re-spec could ever
    clear a verdict that is never recomputed — while re-serving a recorded
    accept of identical bytes is precisely what §2's content addressing is
    for. The two directions have different costs when they are wrong, so they
    get different rules.

    Returns the runner result to hand back, or None to verify for real. It
    appends NO ledger line: the runner returns a result and the normal apply
    path records `implemented --> verified`, because a latch is a verdict and
    the state must advance.
    """
    game = _game_hash(ctx.worker_dir)
    if game is None:
        return None   # no game bytes on disk: no identity, nothing to latch
    accepted = [
        line for line in ctx.history
        if (line["from"], line["to"]) == ("implemented", "verified")
        and line["hashes"]["game"] == game
    ]
    if not accepted:
        return None
    if not (report_path.is_file() and frames_path.is_file()):
        return None   # the verdict's evidence is gone: re-verify for real
    latched = accepted[-1]   # the most recent accept OF THESE BYTES
    return _result(
        True, "verified",
        f"S2b verdict latched from {latched['ts']} (game hash unchanged)",
        cost=None,
        artifacts={"verifier_report": report_path, "frames": frames_path},
    )


def _post_s4_level_floor(worker: Path, s4_out_dir: Path) -> dict:
    """Re-answer the gate's level floor once S4's numbers exist (C-4b, part b).

    §4 runs the merged gate BEFORE S4, so `gate.level-count` reads its count
    off an S4 metadata file that does not exist yet and honestly reports
    `premise-not-met` — and nothing ever asks again. b003r2 slot 1 rode that
    hole all the way to `played` with 3 of its 7 declared levels. This is the
    second ask, at the first moment the numbers are real: layer 1 alone (the
    milliseconds path, never `merged_gate` — no engine is driven and no policy
    is replayed), over the capture S2b already wrote and the metadata S4 just
    wrote.

    V1 RECORDS. The rewritten `acceptance-report.json` and the note artifact
    are EVIDENCE for the review; the S4 stage's own ok/state routing is
    untouched whatever the rows say. Promoting this to a blocking floor is a
    later, separate ruling.

    Returns the artifacts to merge into the stage result. Nothing in here can
    fail S4: every path, including a missing frames sidecar, comes back as a
    note artifact.
    """
    from .frames import capture_from_json
    from .s3_gate import (
        ACCEPTANCE_NAME,
        CHECK_LEVELS,
        GATE_SUFFIX,
        ROBUSTNESS_NAME,
        _write_json,
        structural_acceptance,
    )
    from .s3_verify import FRAMES_SUFFIX
    try:
        frames_path = worker.with_name(worker.name + FRAMES_SUFFIX)
        if not frames_path.is_file():
            # Not an error in S4: a slot whose S2b capture is gone (hand-run
            # stage, cleaned tree) simply cannot be re-asked, and that is worth
            # a line in the ledger rather than a crash of a stage that passed.
            return {
                "post_s4_acceptance_error": (
                    f"no S2b frames sidecar at {frames_path} — the post-S4 level re-check "
                    "reads the capture it holds, so the floor was not re-answered"
                )
            }
        cap = capture_from_json(json.loads(frames_path.read_text(encoding="utf-8")))
        gate_dir = worker.with_name(worker.name + GATE_SUFFIX)
        robustness_path = gate_dir / ROBUSTNESS_NAME
        robustness_report = (
            json.loads(robustness_path.read_text(encoding="utf-8"))
            if robustness_path.is_file()
            else None
        )
        # `metadata_dir` is S4's own output dir, so the rows read the baselines
        # this stage just produced rather than whatever the gate saw.
        structural = structural_acceptance(
            worker, cap, robustness_report=robustness_report, metadata_dir=s4_out_dir
        )
        acceptance_path = gate_dir / ACCEPTANCE_NAME
        _write_json(acceptance_path, structural)
        artifacts: dict = {"post_s4_acceptance": acceptance_path}
        row = next(
            (row for row in structural["checks"] if row["check_id"] == CHECK_LEVELS), None
        )
        if row is None:
            artifacts["post_s4_acceptance_error"] = (
                f"the rewritten {ACCEPTANCE_NAME} carries no {CHECK_LEVELS} row"
            )
        elif row["status"] != "pass":
            artifacts["level_floor_note"] = row["note"]
        return artifacts
    except Exception as exc:  # noqa: BLE001 — evidence, never a verdict on S4
        return {"post_s4_acceptance_error": f"{type(exc).__name__}: {exc}"}


def _play_preview(worker: Path, cfg: Mapping) -> dict:
    """Mirror a PLAYABLE build for the review stop (contract D-2).

    §4 halts every slot at `played` for a human verdict, but the play mirror was
    written one edge LATER (`reviewed --> packaged`) — so the reviewer had never
    been handed a playable build by the machine, and every review so far ran on
    a hand-built preview copy. This writes S6's own mirror at the stop instead,
    titled `" (review pending)"`; the packaging pass overwrites the same dir
    with the clean title, and a pull withdraws it (`_withdraw_play_preview`).

    Returns the artifacts to merge into the battery's success result:
    `play_preview` (the dir the play server discovers) or `play_preview_error`
    (a NOTE, never a path). ANY failure comes back as that note — the
    visual-card precedent (contract V-C): a preview is convenience for the
    review, and it must never throw away a paid-for battery run or block the
    edge §4 draws. The imports are INSIDE the try for the same reason, since an
    import of the packager is one of the things that can fail.
    """
    try:
        from .s4_baselines import OUT_SUFFIX as S4_OUT_SUFFIX
        from .s6_package import write_play_preview
        # No `play_root`: the preview lands where THIS orchestrator's own S6 run
        # will write the packaged mirror (`s6_package.PLAY_ROOT`, since the S6
        # runner passes no root either), which is what makes the overwrite at
        # `reviewed --> packaged` retire the preview instead of duplicating it.
        return {
            "play_preview": write_play_preview(
                worker, worker.with_name(worker.name + S4_OUT_SUFFIX), cfg
            )
        }
    except Exception as exc:  # noqa: BLE001 — a preview is convenience, never a verdict
        return {"play_preview_error": f"{type(exc).__name__}: {exc}"}


def default_runners() -> dict[str, Callable[[SlotContext], dict]]:
    """The real S0→S6 + gate wiring, one fresh set per run.

    Every import is INSIDE a runner: the state machine, the ledger and resume
    must not drag in arcengine, numpy or a driver (and tests that inject fakes
    must not need a logged-in CLI). The S0 draw is memoized per run because
    `sample_batch` draws the WHOLE batch in one call — and, since contract P-5
    addendum 1, it is also LOCKED, because that one call is the only thing in
    this pipeline two processes can be inside at once.
    """
    memo: dict[tuple, list] = {}

    def s0_ideas(ctx: SlotContext) -> dict:
        from .s0_ideas import IDEAS_ROOT as S0_IDEAS_ROOT
        from .s0_ideas import sample_batch
        if Path(S0_IDEAS_ROOT) != IDEAS_ROOT:
            raise RuntimeError(
                f"idea root drift: s0_ideas.IDEAS_ROOT={S0_IDEAS_ROOT} != {IDEAS_ROOT}"
            )
        seed = _sample_seed(ctx.cfg, ctx.respec_count)
        key = (ctx.batch_id, ctx.respec_count, seed)
        if key not in memo:
            # THE WHOLE CALL, under ONE lock (contract P-5 addendum 1). The
            # parent's S0 pre-pass closes the FIRST draw's races; this closes the
            # re-draw, which is where they actually bite — a slot that lint-kills
            # mid-wave re-samples INSIDE its child, and b002 respec'd three times
            # per slot, so two children drawing at once is a production event and
            # not a corner. Held across the call and not merely around the write
            # because `sample_batch` READS every idea file and the dedupe history
            # before it writes any of them: serialized, the second drawer finds
            # the first's ideas already on disk and keeps them, and the history
            # is appended exactly once — which is exactly what the sequential
            # path gives. (Within ONE batch the dedupe window excludes the batch
            # itself, so seeing a sibling's keys was never the mechanism.)
            # Released by the close, like the ledger's.
            lock = s0_draw_lock_path(ctx.batch_id)
            lock.parent.mkdir(parents=True, exist_ok=True)
            with lock.open("a", encoding="utf-8") as lock_fh:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
                memo[key] = sample_batch(
                    ctx.cfg, batch_id=ctx.batch_id, seed=seed, out_dir=ctx.ideas_dir
                )
        ideas = memo[key]
        if not 1 <= ctx.index <= len(ideas):
            raise IndexError(
                f"S0 drew {len(ideas)} idea(s) for batch {ctx.batch_id}; slot {ctx.slug} "
                f"wants index {ctx.index} (batch.size disagrees with the draw)"
            )
        idea = ideas[ctx.index - 1]
        reason = f"re-sample seed {seed}" if ctx.respec_count else f"S0 sample seed {seed}"
        return _result(True, "ideated", f"{reason}: {idea.id}",
                       artifacts={"idea": ctx.idea_path})

    def s1_spec(ctx: SlotContext) -> dict:
        from .s1_spec import CORPUS_ROOT as S1_CORPUS_ROOT
        from .s1_spec import run_s1
        if Path(S1_CORPUS_ROOT) != CORPUS_ROOT:
            raise RuntimeError(
                f"corpus root drift: s1_spec.CORPUS_ROOT={S1_CORPUS_ROOT} != {CORPUS_ROOT}"
            )
        # A lint kill writes all four artifacts and reports the verdict; a
        # MECHANICAL failure raises out of run_s1 and out of here (fail loud).
        # `ctx.escalation` is None on every path but §3 S2b's escalation, where
        # it is the verifier report the rewrite must answer — and where run_s1
        # pins the slug, so the four artifacts land in the EXISTING dir.
        result = run_s1(ctx.idea_path, ctx.cfg, out_root=CORPUS_ROOT, escalation=ctx.escalation)
        out = Path(result.out_dir)
        artifacts = {
            "spec_yaml": out / "spec.yaml", "spec_md": out / "spec.md",
            "lint_report": out / "lint-report.json", "idea": out / "idea.json",
        }
        if result.report.passed:
            return _result(True, "spec_ok", f"lint pass ({len(result.report.warns)} warn(s))",
                           artifacts=artifacts)
        rules = ", ".join(sorted({kill["rule"] for kill in result.report.kills}))
        return _result(False, "respec", f"lint kill: {rules}", artifacts=artifacts)

    def s2_implement(ctx: SlotContext) -> dict:
        from .s2_implement import (
            SPEC_YAML_NAME,
            _run_validate,
            build_payload,
            findings_section,
            green_loop,
            sidecar,
        )
        from .worker import instantiate_worker, write_seeds_sidecar
        spec_dir = _require_spec_dir(ctx)
        worker = spec_dir / WORKER_DIRNAME
        # A declaration-only re-spec: §2's cascade fired on spec bytes the
        # implementation cannot read, so the game beside it is still the game
        # this spec asks for. Revalidate it — `_run_validate` is the green
        # loop's own validate leg, the one whose exit code every attempt
        # record carries — and skip the sessions that would rewrite it. The
        # marker is consumed either way; a RED validate just falls through to
        # the full green loop, whose own records then tell the story.
        if _take_decl_only_marker(spec_dir) and _run_validate(worker)[0] == 0:
            artifacts = {"game": worker / "game.py", "solver": worker / "solver.py"}
            # The report describes the green loop that BUILT these bytes, so it
            # is cited when it survives — but it is a per-run verdict file the
            # NEXT loop clears up front (`green_loop`'s stale-unlink), so a loop
            # interrupted between that clear and its first green leaves none
            # behind (g20261001-5's resume, 2026-10-05), and this path runs no
            # loop to rewrite one. What this hop vouches for under §4 is the
            # revalidated pair above; the report rides only when it exists.
            report = sidecar(worker, ".implement-report.json")
            if report.is_file():
                artifacts["implement_report"] = report
            return _result(True, "implemented", DECL_ONLY_REASON, cost=None,
                           artifacts=artifacts)
        if not worker.exists():
            instantiate_worker(worker)
            # E-0: the exact seed list S6 will validate this game at, written
            # beside the worker at birth, so the scaffold's seed sweep runs
            # S6's seeds on every `make validate` of the green loop.
            write_seeds_sidecar(worker, ctx.cfg)
        elif not sidecar(worker, ".manifest.json").is_file():
            raise FileNotFoundError(
                f"{worker} exists but has no sibling scaffold manifest — not an instantiated "
                "worker; move it aside rather than have S2 overwrite an unknown tree"
            )
        prompt, _payload_report = build_payload(spec_dir, ctx.cfg)
        # A re-implement after an S2b reject rebuilds from the SAME payload, so
        # without this the rebuild never learns what the blind audit found and
        # repeats it (S2's own `make validate` cannot see a verifier-side
        # finding). Feed the findings, appended after the whole payload. Only a
        # reject on disk feeds: no report, no file, or any other verdict leaves
        # the prompt exactly as it was. Bytes that do not parse are the one
        # loud case — that sibling is pipeline state, and guessing it is not a
        # reject is how a rebuild goes blind again.
        report_path = ctx.verifier_report_path
        # The sha of the baseline this lap was told to patch, or None when it
        # was told nothing (knob off, first build, empty worker). It rides into
        # the runner's artifacts so a lap's row says WHICH bytes it patched.
        baseline_digest: str | None = None
        # Has the C-1 baseline section EARNED its place? Set only inside the
        # reject branch below, which is also where its constant is imported, so
        # the flag being true means the name is bound. The section itself is
        # spliced at the END of the prompt (see there for the ordering reason).
        patch_baseline_rides = False
        if report_path is not None and report_path.is_file():
            try:
                verifier_report = json.loads(report_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{report_path} is not valid JSON ({exc}) — S2 cannot tell whether this "
                    "build is answering a reject; read the file and repair or remove it"
                ) from exc
            if isinstance(verifier_report, Mapping) and verifier_report.get("verdict") == "reject":
                prompt = prompt + "\n" + findings_section(verifier_report)
                # Contract C-1: the findings say what must CHANGE; without this
                # the rebuild re-translates the spec from scratch around them
                # and re-rolls everything the previous lap already had right
                # (b002 slot 3 lost two laps to that seesaw). The previous,
                # validate-green build is already on disk — nothing
                # re-instantiates a worker that exists — so point the session at
                # it. Imported HERE, on the one path that uses it, so the splice
                # reads as one block after the findings it qualifies.
                from .s2_implement import (
                    PATCH_BASELINE_SECTION,
                    baseline_sha,
                    patch_baseline_enabled,
                )
                if patch_baseline_enabled(ctx.cfg):
                    # No game.py, no baseline: a rebuild whose worker was wiped
                    # has nothing to modify, and telling it otherwise would be
                    # a lie about a file that is not there.
                    baseline_digest = baseline_sha(worker)
                    # LEAD FIX (C-1 review): the section claims the baseline
                    # implements THIS SAME SPEC. After an S1 respec the stale
                    # reject report and the previous game.py both survive on
                    # disk, so the claim would be false on exactly the laps
                    # that follow a respec. The report records the spec bytes
                    # its audit ran against (canon.spec_hash = sha256(spec.yaml),
                    # the §2 chain — this file's own S2b leg writes it), so the
                    # baseline rides only when that hash matches the spec being
                    # built; anything else, including a report with no canon
                    # block, means a different spec era and no claim.
                    canon = verifier_report.get("canon")
                    audited = canon.get("spec_hash") if isinstance(canon, Mapping) else None
                    if audited != _sha256_file(spec_dir / SPEC_YAML_NAME):
                        baseline_digest = None
                    if baseline_digest is not None:
                        # The section itself is spliced BELOW, after every
                        # findings block: C-1 §2's order is that the rebuild
                        # reads what it must fix before it is told what to treat
                        # as baseline, and contracts P-1/P-2 add a second
                        # findings block that would otherwise land after it.
                        patch_baseline_rides = True
        # THE SAME FEED, one stage further down (contracts P-1 §2, P-2 §1/§2).
        # A gate / S4 / S6 failure now routes the slot back here, and without
        # this the rebuild would be blind about it in exactly the way a rebuild
        # after an S2b reject was blind before the splice above: S2's own `make
        # validate` cannot see a render measurement, a budget cap-fit or a
        # layout seed that will not solve. The rows were written by the stage
        # that failed, in the verifier feed's own shape, and are rendered by the
        # verifier feed's own function — one channel, two writers.
        stage_findings_path = ctx.stage_findings_path
        if stage_findings_path is not None and stage_findings_path.is_file():
            try:
                stage_findings = json.loads(stage_findings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{stage_findings_path} is not valid JSON ({exc}) — S2 cannot tell "
                    "whether this build is answering a gate/S4/S6 failure; read the file "
                    "and repair or remove it"
                ) from exc
            if isinstance(stage_findings, Mapping) and stage_findings.get("verdict") == "reject":
                prompt = prompt + "\n" + findings_section(stage_findings)
        if patch_baseline_rides:
            # LAST, and after BOTH findings blocks (contract C-1 §2). Every
            # findings_section ends in a newline so payload.md stays
            # newline-terminated; this section must leave the record the same
            # way (lead fix, ambiguity f).
            prompt = prompt + "\n" + PATCH_BASELINE_SECTION + "\n"
        # The record of what was actually sent, findings included when they rode.
        (spec_dir / "payload.md").write_text(prompt, encoding="utf-8")
        baseline_artifact = (
            {} if baseline_digest is None else {"patch_baseline_sha": baseline_digest}
        )
        # The spec rides into the loop for ONE reason: the birth-time gate's
        # level-count check (contract C-4b) compares the levels the build
        # actually ships against the ones `game.levels` declares, and it can
        # only do that where the spec is on disk beside the worker — here.
        report = green_loop(worker, prompt, dict(ctx.cfg),
                            spec_path=spec_dir / SPEC_YAML_NAME)
        cost = _cost(report.total_usd, report.total_tokens_in, report.total_tokens_out)
        if report.green:
            return _result(
                True, "implemented", f"validate green in {report.attempts} attempt(s)",
                cost=cost,
                artifacts={"game": worker / "game.py", "solver": worker / "solver.py",
                           "implement_report": sidecar(worker, ".implement-report.json"),
                           **baseline_artifact},
            )
        return _result(False, "spec_ok", f"green-loop {report.reject_reason} "
                       f"after {report.attempts} attempt(s)", cost=cost,
                       artifacts={"reject": sidecar(worker, ".reject.json"), **baseline_artifact})

    def s3_verify(ctx: SlotContext) -> dict:
        import yaml

        from .frames import (
            capture_to_json,
            capture_worker_isolated,
            trace_enabled,
            trace_path,
        )
        from .s3_static import (
            run_required_rows,
            run_solver_quality,
            run_static_checks,
        )
        from .s3_verify import (
            CONFIRMED_SESSION_KEY,
            FRAMES_SUFFIX,
            REPORT_SUFFIX,
            UNCORROBORATED_KEY,
            UNCORROBORATED_TERMS_KEY,
            _bfs_cell_cap,
            _confirm_pass,
            _summed,
            assemble_report,
            compute_diff,
            run_agent_pass,
            write_report,
        )
        spec_dir = _require_spec_dir(ctx)
        worker = spec_dir / WORKER_DIRNAME
        # The pipeline paths `s3_verify.main` builds for a worker in full mode:
        # report + frames as SIBLINGS of the worker (`_paths`, no --out). The
        # report is the same sibling `SlotContext.verifier_report_path` names.
        # Resolved HERE, once, so the latch below asks about exactly the files
        # a real verify would write.
        report_path = worker.with_name(worker.name + REPORT_SUFFIX)
        frames_path = worker.with_name(worker.name + FRAMES_SUFFIX)
        # BEFORE any staging, capture or session spend: has S2b already
        # accepted these game bytes? (`_latched_verify` — accepts latch,
        # rejects never do.)
        latched = _latched_verify(ctx, report_path=report_path, frames_path=frames_path)
        if latched is not None:
            return latched
        spec_path = spec_dir / "spec.yaml"
        bfs_cell_cap = _bfs_cell_cap(ctx.cfg)   # fail before spending a session
        # Read at the same seam and for the same reason: a contradictory
        # confirmation config (C-4a) must raise before the first session, never
        # between the two.
        confirm_pass = _confirm_pass(ctx.cfg)
        # Read at the same seam for the third time and the same reason (R-20): a
        # bad `frames.trace` value must be a loud ValueError BEFORE the capture
        # and the session, never after either has been paid for.
        trace = trace_enabled(ctx.cfg)
        # One fresh interpreter per capture (R2 hotfix #8): repeated verifier
        # rounds in this long-lived process served a stale sibling game module
        # to a freshly loaded solver — the pilot's round-5 crash.
        #
        # R-20: armed, the SAME capture also writes `<worker>.trace.jsonl.gz`
        # beside the sidecar this stage writes below — one record per engine
        # step, so the transients the sidecar's three kept frames cannot hold
        # (refusal flashes, charging states, mid-level boards) are on the record.
        # The sidecar's own bytes are identical in both modes.
        cap = capture_worker_isolated(worker, trace=trace)
        checks = [
            *run_static_checks(worker, cap),
            *run_required_rows(worker, cap),
            *run_solver_quality(worker, cap, bfs_cell_cap=bfs_cell_cap),
        ]
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        spec_hash = _sha256_file(spec_path)

        def audit_round() -> tuple[dict, dict]:
            """One blind session over THIS capture -> (agent block, report).

            `s3_verify.main` ids a worker by its directory name; in architecture
            §2's tree every worker is literally named `worker/`, so the slug —
            its parent — is the same identity here. Every argument but the agent
            block and its diff is fixed for the slot, so a confirmation round
            below is the same audit, not a different one.
            """
            block = run_agent_pass(ctx.cfg, worker, cap, out_dir=worker.parent)
            return block, assemble_report(
                game_id=spec_dir.name, worker=worker, mode="full", cfg=ctx.cfg, cap=cap,
                checks=checks, frames_path=frames_path, agent=block,
                diff=compute_diff(block["claims"], spec), spec_hash=spec_hash,
            )

        agent, report = audit_round()
        agents = [agent]
        # CONFIRMATION ROUND (contract C-4a; operator ruling 2026-09-25). The
        # corroboration knobs demote a FIRST sighting to a recording and let the
        # round pass — and a pass ends this loop, so without this nothing ever
        # looks at that recording again ("we need at least 2 audits with the same
        # issue … if we just run audit once then we'll never have 2 audits
        # agreeing"). So: a pass whose diff carries ANY uncorroborated record
        # buys ONE second blind session over the SAME capture — capture once,
        # audit twice. Round 1 already appended its rounds to both sidecars, so
        # the existing corroboration machinery does the judging unchanged (with
        # `window: 1` round 2 sees exactly round 1): a re-sighting now rejects,
        # a silence leaves the pass standing. A pass with ZERO findings is not
        # confirmed — there is no claim for a second round to corroborate, and
        # its own new findings would be first sightings demoted just as round
        # 1's would have been, so the second session provably cannot change the
        # verdict.
        #
        # This is NOT the invariant `test_b002_hotfix1` pins. That one is about a
        # PASS being one session plus at most one corrective turn, and it still
        # holds exactly: each `audit_round()` here is one such pass. This is a
        # second PASS, knob-gated, and there is never a third — the confirmation
        # round's own result is final whatever it contains.
        diff_record = report["diff"] or {}
        confirmation_ran = False
        if (
            confirm_pass
            and report["verdict"] == "pass"
            and (diff_record.get(UNCORROBORATED_KEY) or diff_record.get(UNCORROBORATED_TERMS_KEY))
        ):
            first_session = agent["session_id"]
            agent, report = audit_round()
            agents.append(agent)
            confirmation_ran = True
            # Round 1's full report is deliberately not kept — its findings live
            # in the sidecars, which is the design's premise — so the report that
            # lands on disk is the confirmation round's, carrying the id of the
            # session it confirmed. `write_report` validates before writing.
            # LEAD FIX (C-4a review): `agent.session_id` is nullable by design
            # (a driver may report no resume handle), and the report key is a
            # NON-EMPTY string when present — writing a None here would kill a
            # confirmed pass at write_report, after both sessions were paid
            # for. No handle ⇒ no key; the run log's "(confirmed)" mark keys
            # off `confirmation_ran`, never off this field.
            if isinstance(first_session, str) and first_session:
                report[CONFIRMED_SESSION_KEY] = first_session
        frames_path.write_text(json.dumps(capture_to_json(cap), indent=2) + "\n", encoding="utf-8")
        write_report(report, report_path)
        # The stage's bill is the bill for every session it spent, summed the way
        # `run_agent_pass` sums its own turns (a block that reported nothing is
        # not a zero). One block in, `_summed` returns that block's number
        # unchanged, so a run without the knob costs exactly what it always did.
        cost = _cost(_summed(agents, "usd"), _summed(agents, "tokens_in"),
                     _summed(agents, "tokens_out"))
        artifacts = {"verifier_report": report_path, "frames": frames_path}
        if trace:
            # Only when armed: an unconfigured run's ledger line is byte-identical
            # to the one it wrote before this contract, because there is no file
            # to name. The capture wrote it; this only puts it on the record.
            artifacts["frames_trace"] = trace_path(worker)
        if report["verdict"] == "pass":
            # The reason distinguishes the two clean paths for the run log; a
            # reject flows the EXISTING path below with its prefix untouched, so
            # the reject loop and the escalation counters see an ordinary reject.
            confirmed = " (confirmed)" if confirmation_ran else ""
            return _result(True, "verified", f"S2b clean{confirmed}", cost=cost,
                           artifacts=artifacts)
        codes = ", ".join(reason["code"] for reason in report["reject_reasons"])
        return _result(False, "spec_ok", f"verifier reject: {codes}", cost=cost,
                       artifacts=artifacts)

    def s3_gate(ctx: SlotContext) -> dict:
        from .frames import capture_worker_isolated, trace_enabled, trace_path
        from .s3_gate import GATE_SUFFIX, gate_checks, merged_gate
        from .s3_verify import REPORT_SUFFIX
        from .s3_visual import (
            CHROME_EXTENT_CHECK,
            DANGER_VISIBLE_CHECK,
            DECLARED_VS_PAINTED_CHECK,
            DENSITY_CHECK,
            FIELD_INDEX_CHECK,
            ROLE_FOOTPRINT_CHECK,
            WIN_RENDER_CHECK,
            build_visual_card,
            card_paths,
            chrome_extent_mode,
            danger_visible_mode,
            declared_vs_painted_mode,
            density_mode,
            field_index_mode,
            l1_floor_mode,
            role_footprint_mode,
            visual_card_mode,
            win_render_mode,
        )
        spec_dir = _require_spec_dir(ctx)
        worker = spec_dir / WORKER_DIRNAME
        # R-20, read before the stage does any work: an invalid knob is a loud
        # ValueError, never a gate that quietly ran without the trace it was
        # configured to write.
        trace = trace_enabled(ctx.cfg)
        report_path = worker.with_name(worker.name + REPORT_SUFFIX)
        if not report_path.is_file():
            raise FileNotFoundError(
                f"{worker}: no verifier report at {report_path} — the gate's layer 3 "
                "consumes S2b's verdict (architecture §3 S3)"
            )
        # FRAMES PROVENANCE (R-21, contract W2-C). This stage's own capture is
        # isolated and therefore fresh; the STALE risk is the sidecar on disk,
        # which `build_visual_card` below reads instead of running the game (and
        # which `_post_s4_level_floor` reads again at S4). So the guard sits
        # here, in the runner that owns the stage's verdict, ahead of both
        # readers — and OUTSIDE the card's `except Exception -> note` wrapper,
        # which would otherwise downgrade this stop to a note (contract V-C
        # makes every card failure evidence; a provenance refusal is not
        # evidence, it is a refusal). Asking before the gate's engine drive is
        # free and answers the same question: the stamp and the game bytes are
        # both already on disk and nothing this stage does can change either.
        provenance = frames_provenance(worker)
        if provenance["status"] == PROVENANCE_MISMATCH:
            # P-2 §1 routes this to `spec_ok` with every other gate failure,
            # which is the honest resolution and not a downgrade: a re-implement
            # rewrites game.py and S2b re-captures, so the next gate reads a
            # sidecar rendered from the bytes it is judging. The ×reject_cap
            # ladder bounds it if the mismatch is systematic.
            return _result(
                False, "verified",
                f"{FRAMES_PROVENANCE_REASON} ({provenance['note']})",
                artifacts={FRAMES_PROVENANCE_ARTIFACT: provenance["record"]},
                findings=[{"code": "gate.frames-provenance",
                           "detail": str(provenance["note"])}],
            )
        verifier_report = _gate_verifier_report(
            ctx, json.loads(report_path.read_text(encoding="utf-8")))
        out_dir = worker.with_name(worker.name + GATE_SUFFIX)
        # Layer 4 is the battery, which §4 only runs at `baselined --> played`:
        # at `verified` the diagram asks for "structural + robustness green"
        # (plus S2b's verdict), so the battery layer is passed None and a
        # `pending` verdict that short-circuited THERE is a pass at this edge.
        # The capture is isolated for the same reason S2b's is (R2 hotfix #8):
        # it DRIVES the worker's solver, and a generated solver serves itself
        # whatever game module this process cached under the path-derived name
        # — after a re-implement here that is last round's game.
        # R-20: the gate's capture traces too, to the SAME path S2b's did. That
        # is an overwrite, and it is safe for the reason the block above just
        # established — a mismatch between the sidecar's stamp and `game.py`
        # already refused this stage, so the bytes being driven here are the
        # bytes S2b drove, and `capture`'s determinism contract makes the two
        # traces identical. If a trace ever DID differ, the one that survives is
        # the one taken from the source on disk, which is the honest choice.
        # Bound rather than inlined (contract B3): `gate_checks` below reads the
        # SAME capture to ask whether a colour the trace paints ever reaches a
        # settled record, and a second capture would be a second engine drive of
        # the same bytes for an answer this one already holds.
        cap = capture_worker_isolated(worker, trace=trace)
        gate = merged_gate(worker, cap,
                           verifier_report=verifier_report, battery_report=None,
                           out_dir=out_dir)
        verdict, stopped_at = gate["verdict"], gate.get("short_circuited_at")
        # Every non-refusing provenance answer rides on the record (R-21): the
        # ledger line for a gated game now says whether its sidecar named the
        # source that rendered it (`provenance:match`) or said nothing at all
        # (`provenance:unrecorded` — the seven shipped games).
        artifacts = {"gate_dir": out_dir,
                     FRAMES_PROVENANCE_ARTIFACT: provenance["record"]}
        if trace:
            artifacts["frames_trace"] = trace_path(worker)
        # The visual report card (contract V-C). Built AFTER the gate, pass or
        # fail: it measures the frames sidecar S2b already wrote, so it costs no
        # engine run, and a REJECTED game is exactly the one whose look the human
        # most wants to see. It is EVIDENCE, never a blocker — any failure at all
        # is recorded as a note and leaves the gate's own verdict untouched.
        card = None
        if visual_card_mode(ctx.cfg) != "off":
            try:
                card = build_visual_card(spec_dir, ctx.cfg)
            except Exception as exc:  # noqa: BLE001 — a card is evidence, never a verdict
                artifacts["visual_card_error"] = str(exc)
            else:
                artifacts["visual_card"] = card_paths(spec_dir)["json"]
        # The ONE visual check that can reject, and only when the batch asked for
        # it: dormant while `gate.l1_color_floor` is `record` (its default).
        if (card is not None and l1_floor_mode(ctx.cfg) == "fail"
                and not card["l1_color_floor"]["passed"]):
            return _result(False, "verified", "visual l1-color-floor < 4", artifacts=artifacts,
                           findings=[_visual_finding("l1-color-floor",
                                                     card["l1_color_floor"])])
        # The W1 card checks (the W1-A1 pair lead-wired at the wave-1 close;
        # W1-A2's two joined the same loop): the same shape as the floor above —
        # each rejects only when its own knob says `fail`, and the reason names
        # the rule so the ledger line says which one stopped the game. In `off`
        # mode the card carries no block for the check, so `card.get` stays None.
        # A check that could not be measured reports `passed: true` (R-04's
        # not-checked path), so a game whose capture never reached a win is
        # never stopped here.
        # Contract B1's two join the SAME loop: `chrome-extent` reports
        # `passed: true` unless BOTH its legs are red (below band AND zero
        # declared chrome), and `danger-visible` reports `passed: true` whenever
        # it could not measure — a spec that declares no danger index, a tell
        # that declares the hiding, an unreadable grey ramp — so neither can
        # stop a game on something it did not actually see.
        for check_key, mode in ((FIELD_INDEX_CHECK, field_index_mode(ctx.cfg)),
                                (ROLE_FOOTPRINT_CHECK, role_footprint_mode(ctx.cfg)),
                                (WIN_RENDER_CHECK, win_render_mode(ctx.cfg)),
                                (DECLARED_VS_PAINTED_CHECK,
                                 declared_vs_painted_mode(ctx.cfg)),
                                (CHROME_EXTENT_CHECK, chrome_extent_mode(ctx.cfg)),
                                (DANGER_VISIBLE_CHECK, danger_visible_mode(ctx.cfg)),
                                # Contract T-1: `density` reports `passed: true`
                                # unless the slot's tier is in scope (t1) AND its
                                # per-level median is under the officials' floor.
                                (DENSITY_CHECK, density_mode(ctx.cfg))):
            check = None if card is None else card.get(check_key)
            if check is not None and mode == "fail" and not check["passed"]:
                return _result(False, "verified", f"visual {check_key}", artifacts=artifacts,
                               findings=[_visual_finding(check_key, check)])
        # The two contract-B3 checks join the SAME loop, for the reason the W1-A2
        # lesson gives: `gen/s3_gate` has no visual wiring and no knob reading of
        # its own, so a mode-knobbed check belongs where the other mode-knobbed
        # checks are read. `gate_checks` does all of it — both knobs read before
        # either check touches a file, both rows written to the gate dir — so the
        # difference from the loop above is only that the mode is already baked
        # into each row's status (`fail` only in `fail` mode, `deferred` in
        # `record`), which is how `lookalike_report` reports a mode too.
        extra = gate_checks(worker, verifier_report, cap=cap, cfg=ctx.cfg,
                            out_dir=out_dir)
        if extra["path"] is not None:
            artifacts["gate_checks"] = extra["path"]
        for row in extra["checks"]:
            if row.status == "fail":
                # H-1 item 9: these ids ALREADY carry `gate.` (see `_gate_code`);
                # the code is namespaced once and the ledger reason names the
                # bare check, as the visual loop's `visual <check>` does.
                code = _gate_code(row.check_id)
                return _result(False, "verified",
                               f"gate {code.removeprefix(GATE_CODE_PREFIX)}",
                               artifacts=artifacts,
                               findings=[{"code": code, "detail": str(row.note or "")}])
        if verdict == "gated" or (verdict == "pending" and stopped_at == "battery"):
            return _result(True, "gated", f"structural + robustness green ({verdict})",
                           artifacts=artifacts)
        return _result(False, "verified", f"gate {verdict} at layer {stopped_at!r}",
                       artifacts=artifacts,
                       findings=[{"code": f"gate.layer-{stopped_at}",
                                  "detail": f"the merged gate returned {verdict!r} at layer "
                                            f"{stopped_at!r}; its rows are in "
                                            f"{out_dir}"}])

    def s4_baselines(ctx: SlotContext) -> dict:
        from .s4_baselines import METADATA_NAME, OUT_SUFFIX, VERDICT_FIT, run_s4_isolated
        spec_dir = _require_spec_dir(ctx)
        worker = spec_dir / WORKER_DIRNAME
        # FRAMES PROVENANCE, the RESUMED-AT-GATED path (R-21, contract W2-C
        # residual a). The guard the gate runs lives in the `verified --> gated`
        # runner, so a batch RESUMED at `gated` — the ledger's own restart path
        # — enters S4 having never asked the question, and `_post_s4_level_floor`
        # below then reads the sidecar and rewrites `acceptance-report.json` off
        # whatever it holds. That is exactly the facing-sentinel failure mode
        # (the audit measured a board the shipped game never paints), one stage
        # later. So S4 asks too, with the same verdict vocabulary and the same
        # refusal reason.
        #
        # Asked HERE, before `run_s4_isolated`, not merely before the floor
        # re-check: the answer is pure file reading (no engine, no import) and
        # nothing this stage does can change either input, so asking first costs
        # nothing and refuses before the slot pays for a baseline run it would
        # have to discard. ONLY `mismatch` refuses — `unrecorded` is the whole
        # pre-R-21 corpus and rides the record as a note, never a refusal.
        provenance = frames_provenance(worker)
        if provenance["status"] == PROVENANCE_MISMATCH:
            return _result(
                False, "gated",
                f"{FRAMES_PROVENANCE_REASON} ({provenance['note']})",
                artifacts={FRAMES_PROVENANCE_ARTIFACT: provenance["record"]},
                findings=[{"code": "s4.frames-provenance",
                           "detail": str(provenance["note"])}],
            )
        # Isolated for the same stale-cache reason as the two captures above:
        # S4 drives the solver, and in THIS process a solver loaded after a
        # re-implement is handed the game module cached under the path-derived
        # name — a plan that no longer fits the board, so the line dies a few
        # actions in and S4 baselines a non-winning drive. Exit code 2 is a
        # cap-fit reject, not a crash: the helper brings both verdicts home.
        report = run_s4_isolated(worker, ctx.cfg)
        out_dir = worker.with_name(worker.name + OUT_SUFFIX)
        if report["verdict"] == VERDICT_FIT:
            # The gate's level floor, re-asked now that one baseline per level
            # exists (C-4b part b). Records only: the routing below is the same
            # whatever it finds.
            artifacts = {"metadata": out_dir / METADATA_NAME, "actions": out_dir / "actions",
                         FRAMES_PROVENANCE_ARTIFACT: provenance["record"]}
            artifacts.update(_post_s4_level_floor(worker, out_dir))
            return _result(True, "baselined",
                           f"g-sampler + cap-fit: {report['result']['baseline_actions']}",
                           artifacts=artifacts)
        # P-2 §2: §3's third named routing — "S2 (cap bug)". The cap-fit rows
        # the rebuild has to answer are the per-level ones S4 measured; the
        # report on disk is named so the finding points at its own evidence.
        return _result(False, "gated", f"s4 {report['verdict']} (route: S2, cap bug)",
                       artifacts={"s4_report": out_dir / "s4-report.json",
                                  FRAMES_PROVENANCE_ARTIFACT: provenance["record"]},
                       findings=[{"code": f"s4.{report['verdict']}",
                                  "detail": _s4_cap_fit_detail(report, out_dir)}])

    def s5_battery(ctx: SlotContext) -> dict:
        from .s5_battery import OUT_SUFFIX, REPORT_NAME, STATUS_CRASH, run_battery
        spec_dir = _require_spec_dir(ctx)
        worker = spec_dir / WORKER_DIRNAME
        report = run_battery(worker, ctx.cfg)
        out_dir = worker.with_name(worker.name + OUT_SUFFIX)
        cost = _cost(report["usd_total"], report["tokens"]["tokens_in"],
                     report["tokens"]["tokens_out"])
        artifacts = {"battery_report": out_dir / REPORT_NAME}
        if report["status"] == STATUS_CRASH:
            crash = report["crash"] or {}
            return _result(False, "implemented",
                           f"battery crash at pass {crash.get('pass')} level {crash.get('level')}",
                           cost=cost, artifacts=artifacts)
        # token-cap / protocol-failure are OUTCOMES, not crashes: the battery
        # is done and the numbers are recorded (architecture §3 S3d).
        #
        # Contract D-2: this success return OWNS the `baselined --> played` edge
        # that stops for the human, so the playable preview is written here. The
        # crash path above deliberately gets none — it appends `played` only to
        # leave it again for `implemented` in the same write, and a build that
        # crashed the battery is on its way back to S2, not to a reviewer.
        artifacts.update(_play_preview(worker, ctx.cfg))
        return _result(True, "played", f"battery {report['status']}", cost=cost,
                       artifacts=artifacts)

    def s6_package(ctx: SlotContext) -> dict:
        from .s6_package import (
            MANIFEST_NAME,
            OUT_SUFFIX,
            PACKAGE_DIRNAME,
            REPORT_NAME,
            VERDICT_PACKAGED,
            game_hash,
            promote_game,
            run_s6,
        )
        spec_dir = _require_spec_dir(ctx)
        worker = spec_dir / WORKER_DIRNAME
        spec_path = spec_dir / "spec.yaml"
        # The one place the heavy import is already paid for: prove this
        # module's local `_game_hash` is still S6's `sha(game.py + solver.py)`.
        if game_hash(worker) != _game_hash(worker):
            raise RuntimeError(
                "game_hash drift: orchestrator._game_hash disagrees with "
                "s6_package.game_hash (architecture §2 ⊕ provenance chain)"
            )
        report = run_s6(worker, ctx.cfg, spec_path=spec_path if spec_path.is_file() else None)
        out_dir = worker.with_name(worker.name + OUT_SUFFIX)
        if report["verdict"] == VERDICT_PACKAGED:
            # CONTRACT P-3: the packaged-success site is where a game reaches the
            # shared shelf, and this is the ONE call that puts it there. It runs
            # BEFORE the result is built, so the §4 rule holds unchanged — a
            # `packaged` transition is appended only after the stage's artifacts
            # are on disk, and since P-3 the shelf entry is one of them. A
            # promotion that cannot be vouched for therefore fails LOUDLY here
            # rather than appending a `packaged` line for a game nobody can pull.
            # The promoter owns every decision about games/; this is a call site.
            promoted = promote_game(
                worker, ctx.cfg, spec_path=spec_path if spec_path.is_file() else None
            )
            seeds = report["seeds"]   # b10.1 manifest shape: {requested, validated[], …}
            return _result(True, "packaged",
                           f"packaged {len(seeds['validated'])}/{seeds['requested']} seed(s)",
                           artifacts={"manifest": out_dir / PACKAGE_DIRNAME / MANIFEST_NAME,
                                      "promoted_game": promoted["game_dir"]})
        # Contract P-1 §2: the SEED ROWS are the payload. Each failing seed says
        # what went wrong under it — a losing line, or (since P-1) a contained
        # worker crash with the site inside the game's own file — and that is
        # exactly what the rebuild has to make solvable.
        return _result(False, "reviewed",
                       f"s6 {report['verdict']} at seed(s) {report['seeds_failed']} "
                       f"(route: {report['route']})",
                       artifacts={"s6_report": out_dir / REPORT_NAME},
                       findings=[
                           {"code": "s6.seed-reject",
                            "detail": f"seed {detail['seed']}: "
                                      f"{detail.get('reason') or detail.get('error')}"}
                           for detail in report["seed_detail"] if not detail["passed"]
                       ])

    return {
        "s0_ideas": s0_ideas, "s1_spec": s1_spec, "s2_implement": s2_implement,
        "s3_verify": s3_verify, "s3_gate": s3_gate, "s4_baselines": s4_baselines,
        "s5_battery": s5_battery, "s6_package": s6_package,
    }


# --- the run ----------------------------------------------------------------


@dataclass
class _Slot:
    """One slot's live state for the duration of a run."""

    slug: str
    index: int
    state: str | None
    history: list[dict]
    rejects: dict
    cost: dict
    first_ts: str | None = None
    last_ts: str | None = None
    green_failures: int = 0
    invocations: dict = field(default_factory=dict)
    blocked: dict | None = None
    review_pending: bool = False
    # Contract P-3.3: this RUN cast the `played --> reviewed` accept itself.
    # In-memory only, like `respec_runs` beside it — the durable record is the
    # ledger line's `AUTO_ACCEPT_REASON`, and the report reads both.
    auto_accepted: bool = False
    stale: list | None = None
    respec_runs: int = 0
    # Spend that no ledger line can carry: a re-spec and a stale re-run append
    # no transition (§4 has no self-edge) but they DO cost money, so the batch
    # report accounts for them beside the ledger-derived table.
    offledger_cost: dict = field(default_factory=lambda: {"usd": None, "tokens_in": None,
                                                          "tokens_out": None, "runs": 0})
    _respec_done_for: object = _UNSET

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL


def _findings_rows(stage: str, result: Mapping) -> list[dict]:
    """A runner's OPTIONAL `findings` — the rows the next S2 session is told.

    Contracts P-1 §2 / P-2 §1/§2: a failing gate/S4/S6 runner names its failing
    CHECK ROWS here, in the verifier feed's own `{code, detail}` shape, and
    `_write_stage_findings` renders them through `s2_implement.findings_section`
    like any reject. The key is optional and defaults to `[]` — every runner
    that existed before this contract, and every fake runner in the suite, keeps
    returning exactly what it returned — and a failure that names no rows still
    feeds the next build its `reason` (see `_write_stage_findings`).

    Validated like everything else a runner returns: a non-list, or a row
    without a usable `code`, is a wiring bug that must say so here rather than
    render a bullet with a hole in it three stages later.
    """
    rows = result.get("findings") or []
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise TypeError(
            f"runner {stage!r} result 'findings' must be a list of {{code, detail}} rows, "
            f"got {rows!r}"
        )
    checked: list[dict] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise TypeError(
                f"runner {stage!r} result findings[{index}] must be a mapping, got {row!r}"
            )
        code = row.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError(
                f"runner {stage!r} result findings[{index}] has no `code` — a finding is "
                f"identified by its code and there is nothing to quote to the rebuild "
                f"without one: {row!r}"
            )
        checked.append(dict(row))
    return checked


def _check_result(stage: str, result: object) -> dict:
    """A runner's return, validated. Missing cost/artifacts default; the rest is law."""
    if not isinstance(result, Mapping):
        raise TypeError(
            f"runner {stage!r} returned {type(result).__name__}; expected a mapping "
            "{ok, to_state, reason, cost, artifacts}"
        )
    missing = [key for key in ("ok", "to_state", "reason") if key not in result]
    if missing:
        raise KeyError(f"runner {stage!r} result is missing {missing}")
    if not isinstance(result["ok"], bool):
        raise TypeError(f"runner {stage!r} result 'ok' must be a bool, got {result['ok']!r}")
    if result["to_state"] not in STATES:
        raise ValueError(
            f"runner {stage!r} result 'to_state'={result['to_state']!r} is not a §4 state"
        )
    if not isinstance(result["reason"], str) or not result["reason"].strip():
        raise ValueError(f"runner {stage!r} result 'reason' must be a non-empty string")
    artifacts = result.get("artifacts") or {}
    if not isinstance(artifacts, Mapping):
        raise TypeError(f"runner {stage!r} result 'artifacts' must be a mapping")
    return {
        "ok": result["ok"], "to_state": result["to_state"], "reason": result["reason"],
        "cost": _check_cost(result.get("cost")), "artifacts": dict(artifacts),
        "findings": _findings_rows(stage, result),
    }


# Artifact keys that carry a NOTE, not a path. The rule below is "every
# declared artifact is on disk", and it has to stay that way — but contract V-C
# gives the gate runner one artifact that exists precisely BECAUSE a file could
# not be written (`visual_card_error` is the exception text of a visual card
# that failed to build), and contract C-1 gives the S2 runner one that is a
# HASH of a file rather than a path to it (`patch_baseline_sha` — the identity
# of the game.py bytes a rebuild was told to patch; the file itself is already
# declared as the `game` artifact). Existence-checking either would turn a note
# into a run-killing RuntimeError. The exemption is a named list, never a
# pattern: a new note must be added here deliberately, and everything else is
# still a path that must exist.
#
# Contract C-4b adds two more, both from the post-S4 level re-check: the level
# row's own note when that row is not a pass (`level_floor_note` — the evidence
# the review reads), and the reason the re-check could not run at all
# (`post_s4_acceptance_error`), which exists BECAUSE no report was written.
# The report it does write is `post_s4_acceptance`, a real path and therefore
# NOT exempt.
#
# Contract D-2 adds one, for the same reason as the visual card's:
# `play_preview_error` is the exception text of a review preview that could not
# be written, so it exists precisely BECAUSE there is no directory to point at.
# The preview it does write is `play_preview`, a real path and NOT exempt.
#
# Contract W2-C (R-21) adds one: `frames_provenance` is a VERDICT about the
# frames sidecar (`provenance:match` / `:unrecorded` / …), not a path to it —
# the sidecar itself is already declared by the S2b stage as `frames`.
NOTE_ARTIFACTS = (
    "visual_card_error", "patch_baseline_sha", "level_floor_note", "post_s4_acceptance_error",
    "play_preview_error", FRAMES_PROVENANCE_ARTIFACT,
)


def _check_artifacts(stage: str, result: Mapping) -> None:
    """§4: a transition is appended only AFTER the stage's artifact is on disk."""
    for name, path in result["artifacts"].items():
        if name in NOTE_ARTIFACTS:
            continue
        if not Path(path).exists():
            raise RuntimeError(
                f"stage {stage!r} declared artifact {name}={path} but it is not on disk — "
                "no transition is appended for work that does not exist (architecture §4)"
            )


def _is_battery_crash(result: Mapping) -> bool:
    """The battery's crash signal, whichever way the runner spells it.

    architecture §3 S3d routes crashes to S2 and §4 draws that as
    `played --> implemented: crash`; `s5_battery.run_battery` reports it as
    `status: "crash"`. A runner says so with `ok: False`, or by naming
    `implemented` as the state it wants — both mean crash here.
    """
    return (not result["ok"]) or result["to_state"] == "implemented"


# --- the killed-spec archive (what keeps discovery single-valued) -----------


def archive_killed_spec(spec_dir: Path) -> Path:
    """Move a lint-KILLED spec dir to `<parent>/.killed/<name>-<UTC stamp>/`.

    `_discover_spec_dir` is content-addressed — it reads every child's
    `idea.json` — so a killed dir left in `out/corpus/<batch>/` is claimed by
    the same idea as the re-spec that follows it, and the slot crashes on the
    next resume ("a slot has exactly one spec dir"). Archiving is the fix:
    under `.killed/` the dir has no TOP-LEVEL `idea.json`, so the scan walks
    past it, and the kill itself (spec + lint report) is still on disk to read.

    Failures RAISE. A stranded killed dir IS the crash class this prevents, so
    a move that did not happen must never be reported as one.
    """
    spec_dir = Path(spec_dir)
    if not spec_dir.is_dir():
        raise NotADirectoryError(
            f"archive_killed_spec: {spec_dir} is not a directory — nothing to archive"
        )
    graveyard = spec_dir.parent / KILLED_DIRNAME
    graveyard.mkdir(parents=True, exist_ok=True)
    stem = f"{spec_dir.name}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    dest = graveyard / stem
    suffix = 2
    while dest.exists():   # same idea killed twice inside one second
        dest = graveyard / f"{stem}-{suffix}"
        suffix += 1
    spec_dir.rename(dest)  # `.killed/` is a sibling: always the same filesystem
    return dest


def _killed_by_lint(spec_dir: Path) -> bool:
    """Is this corpus dir a kill (or the rubble of one)?

    The S1 runner writes `lint-report.json` beside the spec on EVERY verdict,
    so a dir without one is rubble from a crash mid-write, and a report that
    parses with `passed: false` is a kill. Anything else stays: archiving a
    spec the ledger still claims at `spec_ok` would stand the slot down. A
    report that will not parse is neither verdict and is the operator's call —
    it raises rather than guessing which way to move the dir.
    """
    report = Path(spec_dir) / "lint-report.json"
    if not report.is_file():
        return True
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{report} is not valid JSON ({exc}) — the killed-spec sweep cannot tell a kill "
            "from a pass here; read the dir and move or repair it by hand"
        ) from exc
    return isinstance(payload, Mapping) and payload.get("passed") is False


def sweep_killed_specs(batch_corpus_dir: Path) -> list[Path]:
    """Archive every killed spec dir stranded in `out/corpus/<batch>/`.

    Startup self-heal, not policy: a kill is archived the moment its
    `ideated --> respec` line lands, but a crash BETWEEN the append and the
    move (or a run from before that archiving existed) leaves the dir behind,
    and the next S1 attempt then makes two dirs claim one idea. Sweeping
    before any stage runs turns that LedgerError back into an ordinary
    re-spec.

    Dirs with no `idea.json` are invisible to discovery and are left alone;
    so is `.killed/` itself. Returns the destinations, in iteration order.
    """
    batch_corpus_dir = Path(batch_corpus_dir)
    if not batch_corpus_dir.is_dir():
        return []   # nothing has been written for this batch yet
    moved: list[Path] = []
    for candidate in sorted(batch_corpus_dir.iterdir()):
        if not candidate.is_dir() or candidate.name == KILLED_DIRNAME:
            continue
        if not (candidate / "idea.json").is_file():
            continue
        if _killed_by_lint(candidate):
            moved.append(archive_killed_spec(candidate))
    return moved


def _killed_spec_dir(result: Mapping) -> Path | None:
    """The dir a killed S1 run wrote: the ONE parent all its artifacts share.

    Derived, never re-discovered: `_discover_spec_dir` is the scan that breaks
    when two dirs claim one idea, so it must not be the thing asked which of
    them to archive. `None` when the runner declared no artifacts — it wrote no
    spec dir, so there is no rubble to move.
    """
    parents = {Path(path).parent for path in result["artifacts"].values()}
    if not parents:
        return None
    if len(parents) > 1:
        raise RuntimeError(
            f"s1_spec declared artifacts in {len(parents)} dirs "
            f"{sorted(str(parent) for parent in parents)} — a killed spec dir is the ONE "
            "parent its spec, prose, lint report and idea copy share"
        )
    return parents.pop()


def _discover_spec_dir(corpus_dir: Path, idea_path: Path) -> Path | None:
    """The slot's corpus dir: the one whose `idea.json` carries this idea id.

    S1 names the dir after the SPEC's slug (`s1_spec._slug_dir_name`), which
    the orchestrator cannot predict and must not duplicate — but S1 also
    copies `idea.json` in, so the link is content, not convention.
    """
    corpus_dir, idea_path = Path(corpus_dir), Path(idea_path)
    if not idea_path.is_file() or not corpus_dir.is_dir():
        return None
    idea = json.loads(idea_path.read_text(encoding="utf-8"))
    idea_id = idea.get("id")
    found = []
    for candidate in sorted(corpus_dir.iterdir()):
        copied = candidate / "idea.json"
        if not copied.is_file():
            continue
        if json.loads(copied.read_text(encoding="utf-8")).get("id") == idea_id:
            found.append(candidate)
    if len(found) > 1:
        raise LedgerError(
            f"idea {idea_id!r} is claimed by {len(found)} corpus dirs {[str(p) for p in found]} — "
            "a slot has exactly one spec dir"
        )
    return found[0] if found else None


def _ideas_dir(batch_id: str, respec_count: int) -> Path:
    """`out/ideas/<batch>/` for the first draw, `…/respec-<k>/` for a re-sample."""
    base = IDEAS_ROOT / batch_id
    return base if respec_count == 0 else base / f"respec-{respec_count}"


def _context(cfg: Mapping, slot: _Slot, *, batch_id: str, stage: str,
             bdir: Path) -> SlotContext:
    # The sampling this slot is LIVING IN: re-samples already recorded, plus the
    # one a slot sitting in `respec` is about to draw (§4 `respec --> ideated`).
    # It must not change across the s0 -> s1 hand-off, or S1 would look for the
    # idea in the directory the NEXT re-sample will use.
    respec = slot.rejects["resample"] + (1 if slot.state == "respec" else 0)
    ideas_dir = _ideas_dir(batch_id, respec)
    idea_path = ideas_dir / f"idea-{slot.index:03d}.json"
    corpus_dir = CORPUS_ROOT / batch_id
    spec_dir = _discover_spec_dir(corpus_dir, idea_path)
    spec = None if spec_dir is None else _sha256_file(spec_dir / "spec.yaml")
    return SlotContext(
        cfg=cfg, batch_id=batch_id, slug=slot.slug, index=slot.index, state=slot.state,
        stage=stage, attempt=slot.invocations.get(stage, 0) + 1, batch_dir=bdir,
        ideas_dir=ideas_dir, idea_path=idea_path, corpus_dir=corpus_dir, spec_dir=spec_dir,
        respec_count=respec,
        verifier_rejects=_verifier_rejects_against(slot.history, spec),
        green_failures=slot.green_failures, history=tuple(slot.history),
    )


def _record(slot: _Slot, line: dict) -> None:
    slot.state = line["to"]
    slot.history.append(line)
    slot.first_ts = slot.first_ts or line["ts"]
    slot.last_ts = line["ts"]
    _add_cost(slot.cost, line["cost"])
    edge = (line["from"], line["to"])
    for key, match in (("lint_kill", ("ideated", "respec")),
                       ("resample", ("respec", "ideated")),
                       ("verifier", ("implemented", "spec_ok")),
                       ("battery_crash", ("played", "implemented")),
                       ("green_death", ("spec_ok", "dead"))):
        if edge == match:
            slot.rejects[key] += 1


def _charge_offledger(slot: _Slot, cost: Mapping | None) -> None:
    """Spend from a run that appends no transition (a re-spec, a stale re-run)."""
    slot.offledger_cost["runs"] += 1
    _add_cost(slot.offledger_cost, cost)


def _block_slot(slot: _Slot, *, stage: str, reason: str, note: str) -> str:
    slot.blocked = {"stage": stage, "state": slot.state, "reason": reason, "note": note}
    return "blocked"


def _invoke(stages: Mapping, stage: str, ctx: SlotContext, slot: _Slot) -> dict:
    runner = stages.get(stage)
    if runner is None:
        raise KeyError(
            f"no runner for stage {stage!r} (the run needs it at state {ctx.state!r}); "
            f"runners must cover {list(STAGES)}"
        )
    slot.invocations[stage] = slot.invocations.get(stage, 0) + 1
    result = _check_result(stage, runner(ctx))
    _check_artifacts(stage, result)
    return result


def _work_slot(slot: _Slot, *, cfg: Mapping, batch_id: str, bdir: Path,
               ledger_path: Path, stages: Mapping) -> str:
    """Drive one slot until it stops. Returns terminal|review|blocked."""
    steps = 0
    # Read once per slot: `cfg` does not change under the loop, and a malformed
    # `orchestrator.respec_cap` must say so before any stage runs, not at the
    # first respec three stages in.
    cap = _respec_cap(cfg)
    # Same rule for the other cap (contract D-3 §1): `verifier.reject_cap` is
    # read before this slot's first stage runs, so a malformed value is a config
    # error at second zero rather than at the first verifier reject, three
    # stages and one implementer session into the slot.
    reject_cap = _reject_cap(cfg)
    # Contract P-3's two knobs, read on the SAME terms and for the same reason:
    # a malformed `verifier.round_cap` or `review.auto_accept` is a config error
    # and must be one at second zero, not after a slot has spent five stages.
    round_cap = _round_cap(cfg)
    auto_accept = _auto_accept(cfg)
    # Contract P-A.1's knob, read on exactly the same terms: a malformed
    # `verifier.reconcile_early` is a config error at second zero, not at the
    # first declaration-side reject three stages in.
    reconcile_early = _reconcile_early(cfg)
    # Contract E-2's two, read here for the third time and the same reason. Both
    # are false unless a batch armed them, and false is today's bytes.
    stage_fail_park = _stage_fail_park(cfg)
    while True:
        steps += 1
        if steps > MAX_STEPS_PER_SLOT:
            raise RuntimeError(
                f"{slot.slug}: {steps} steps without settling (state {slot.state!r}) — "
                "a runner is looping; this guard is a wiring check, not a policy"
            )
        if slot.terminal:
            return "terminal"
        if slot.state == "played":
            # architecture §3 S5 / §4: the ONLY ways out are a human accept or
            # a human pull, and nothing here decides for them — UNLESS the batch
            # armed `review.auto_accept` (contract P-3.3, the operator's 2026-09-29
            # autonomy ruling), in which case the machine casts the accept
            # itself, says so in the ledger, and carries on to S6 in the same
            # run. Human oversight is post-package by that ruling.
            if not auto_accept:
                slot.review_pending = True
                return "review"
            ctx = _context(cfg, slot, batch_id=batch_id, stage="s6_package", bdir=bdir)
            _record(slot, append_transition(
                ledger_path, slug=slot.slug, from_state="played", to_state="reviewed",
                reason=AUTO_ACCEPT_REASON, hashes=input_hashes(ctx), cost=None))
            slot.auto_accepted = True
            continue
        if slot.state == "respec" and slot.rejects["lint_kill"] >= cap:
            return _block_slot(
                slot, stage="s0_ideas",
                reason=f"{slot.rejects['lint_kill']} lint kill(s) at cap {cap}",
                note="architecture §4 draws no edge from respec/ideated to dead",
            )
        stage = NEXT_STAGE[slot.state]
        if stage is None:
            raise RuntimeError(f"{slot.slug}: no stage runs from state {slot.state!r}")

        if slot.state == "spec_ok":
            outcome = _maybe_respec(slot, cfg=cfg, batch_id=batch_id, bdir=bdir, stages=stages,
                                    ledger_path=ledger_path)
            if outcome == "blocked":
                return "blocked"
            if outcome == "terminal":
                # Contract E-2 §3: the re-spec was provably futile, so the slot
                # parked at `spec_ok` without spending the session.
                return "terminal"
            if outcome == "respec-ran":
                continue

        ctx = _context(cfg, slot, batch_id=batch_id, stage=stage, bdir=bdir)
        result = _invoke(stages, stage, ctx, slot)
        # Hashes are read AFTER the stage wrote, off a re-resolved context, so
        # the §2 ⊕ chain is recorded as the stage left it: S1's line carries the
        # spec it just wrote, S2's the game it just implemented. The stage-input
        # digest is unaffected — no stage in §3 writes its own inputs — so
        # resume still compares like with like.
        hashes = input_hashes(_context(cfg, slot, batch_id=batch_id, stage=stage, bdir=bdir))

        if stage == "s5_battery" and _is_battery_crash(result):
            # Both lines in ONE write: the battery report is on disk, and the
            # crash route must not be lost in the gap between two appends.
            lines = [
                _line(slug=slot.slug, from_state="baselined", to_state="played",
                      reason=result["reason"], hashes=hashes, cost=result["cost"]),
                _line(slug=slot.slug, from_state="played", to_state="implemented",
                      reason=CRASH_REASON, hashes=hashes, cost=None),
            ]
            for line in _append_lines(ledger_path, lines):
                _record(slot, line)
            continue

        if result["ok"]:
            expected = STAGE_SUCCESS[stage]
            if result["to_state"] != expected:
                raise ValueError(
                    f"runner {stage!r} reported ok with to_state={result['to_state']!r}; "
                    f"architecture §4 lands it on {expected!r}"
                )
            if stage in STAGE_REJECT_ROUTING:
                # The stage that wrote the P-1/P-2 payload has now PASSED, so
                # the findings are answered and must stop being quoted to every
                # later rebuild. Retired HERE, beside the write, so the lifecycle
                # of that file is one thing in one place — a runner (real or
                # fake) reports a verdict and the state machine keeps the books.
                _clear_stage_findings(ctx.spec_dir, stage)
            _record(slot, append_transition(
                ledger_path, slug=slot.slug, from_state=slot.state, to_state=expected,
                reason=result["reason"], hashes=hashes, cost=result["cost"]))
            continue

        # --- failure routing (architecture §4 edges only) -------------------
        if stage == "s2_implement":
            # A driver outage (auth/usage/rate limit — b002 contract 2) says
            # nothing about the game: the loop recorded no attempts and no
            # verdict on the work, so it must not spend a green death. BLOCK
            # the slot loudly instead; a resume retries S2 when the driver is
            # back. The runner's reason embeds the loop's constant verbatim.
            from .s2_implement import DRIVER_UNAVAILABLE_REASON
            if DRIVER_UNAVAILABLE_REASON in result["reason"]:
                _charge_offledger(slot, result["cost"])
                return _block_slot(
                    slot, stage=stage, reason=result["reason"],
                    note="infrastructure outage, not a game failure — "
                         "green_failures not charged (b002 contract 2)",
                )
            slot.green_failures += 1
            if slot.green_failures < GREEN_CAP_DEATHS:
                # No edge, no line (§4 draws no spec_ok self-edge): the slot
                # stays at spec_ok and retries. The attempt still SPENT.
                _charge_offledger(slot, result["cost"])
                continue
            _record(slot, append_transition(
                ledger_path, slug=slot.slug, from_state="spec_ok", to_state="dead",
                reason=f"green-attempts cap ×{GREEN_CAP_DEATHS}: {result['reason']}",
                hashes=hashes, cost=result["cost"]))
            return "terminal"

        if stage == "s3_verify":
            # THE ROUND CAP FIRST (contract P-3.2). It supersedes the ×reject_cap
            # ladder rather than joining it: the ladder's job is to get a slot
            # re-specced, this cap's job is to END the slot — reconciled or dead
            # — so the ladder has nothing left to do once it bites. Unarmed
            # (`round_cap` None), this branch is not entered at all and the
            # routing below is byte-for-byte the routing every batch has run.
            if round_cap is not None and _verify_rounds(slot.history) + 1 >= round_cap:
                outcome = _round_cap_verdict(
                    slot, ctx=ctx, cfg=cfg, result=result, round_cap=round_cap,
                    ledger_path=ledger_path, batch_id=batch_id, bdir=bdir,
                )
                if outcome == "terminal":
                    return "terminal"
                continue
            # CONTRACT P-A.1, below the cap. A small, wholly declaration-side
            # mismatch is amended on the spot instead of costing a re-spec —
            # the operator's "If there's a mismatch of 1-2 terms let's just go ahead
            # with it", implemented as an amendment to the spec rather than a
            # waiver of the finding. Unarmed (`reconcile_early` 0) this branch
            # is not entered at all and the routing below is byte-for-byte the
            # routing every batch has run; a refused reconciliation falls
            # through to that same routing.
            if reconcile_early and _reconcile_early_verdict(
                slot, ctx=ctx, cfg=cfg, result=result, cap=reconcile_early,
                ledger_path=ledger_path, batch_id=batch_id, bdir=bdir,
            ):
                continue
            count = ctx.verifier_rejects + 1
            reason = result["reason"]
            if count >= reject_cap:
                reason = f"{ESCALATE_REASON.format(n=count)}: {reason}"
            _record(slot, append_transition(
                ledger_path, slug=slot.slug, from_state="implemented", to_state="spec_ok",
                reason=reason, hashes=hashes, cost=result["cost"]))
            continue

        if stage in STAGE_REJECT_ROUTING:
            # CONTRACTS P-1 §2 / P-2 §1/§2 — architecture §3's own failure
            # routing, on the edges the §4 diagram never drew. All three land on
            # `spec_ok` (§3's "S2"), and all three COUNT toward the ×reject_cap
            # ladder (P-2 §3, `_verifier_rejects_against`): a render bug the
            # implementer cannot fix escalates to a re-spec and ultimately to
            # the respec cap, so there is no infinite implement↔gate loop. The
            # ledger reason carries the count, the cap and the §3 route, because
            # that ladder is invisible in a state name.
            label, route = STAGE_REJECT_ROUTING[stage]
            count = ctx.verifier_rejects + 1
            reason = f"{label} {count}/{reject_cap} → {route}: {result['reason']}"
            if count >= reject_cap:
                reason = f"{label} {count}/{reject_cap} {ESCALATE_MARK}: {result['reason']}"
            # Written BEFORE the line is appended, for §4's own reason: the
            # ledger line is a claim that the stage's artifact is on disk, and
            # the payload the next S2 session reads is part of that artifact.
            # The park below writes it too: a parked slot's artifacts STAND
            # (P-A.4), and the findings that parked it are the first thing a
            # human picking the slot up has to read.
            _write_stage_findings(ctx.spec_dir, stage, result)
            # CONTRACT E-2 §2 — WHERE THIS LADDER ENDS. Over the cap the reason
            # above merely gains `ESCALATE_MARK` and the slot re-specs AGAIN:
            # g20261001-5 rode that to "gate fail 2/1" and "package fail 4/1"
            # with no terminal but `MAX_STEPS_PER_SLOT`'s crash. Armed, the slot
            # PARKS from the state this routing departs from. Unarmed, this
            # branch is not entered and the routing below is byte for byte the
            # routing every batch has run.
            if stage_fail_park and count > reject_cap:
                park_from = STAGE_REJECT_STATE[stage]
                if park_from != slot.state:
                    # A wiring check, not a policy: the park edge is drawn for
                    # the state this table names, and a line whose `from` is not
                    # the slot's real state would make the ledger unreplayable.
                    raise RuntimeError(
                        f"{slot.slug}: {stage} ran from {slot.state!r} but STAGE_REJECT_STATE "
                        f"names {park_from!r} — the park edge and the §4 walk disagree"
                    )
                codes = (", ".join(str(row["code"]) for row in result["findings"])
                         or str(result["reason"]))
                head = STAGE_FAIL_PARK_REASON.format(
                    label=label, count=count, cap=reject_cap, codes=codes)
                return _park_slot(
                    slot, from_state=park_from,
                    reason=f"{head} ({stage} failed {count} time(s) against "
                           f"verifier.reject_cap {reject_cap}; §3's route was {route}, and a "
                           f"slot that has taken it that often is not being re-implemented "
                           f"into a pass)",
                    hashes=hashes, cost=result["cost"], ledger_path=ledger_path)
            _record(slot, append_transition(
                ledger_path, slug=slot.slug, from_state=slot.state, to_state="spec_ok",
                reason=reason, hashes=hashes, cost=result["cost"]))
            continue

        if stage == "s1_spec":
            _record(slot, append_transition(
                ledger_path, slug=slot.slug, from_state="ideated", to_state="respec",
                reason=result["reason"], hashes=hashes, cost=result["cost"]))
            # The line above already carries the kill's hashes (the ledger
            # stores content, not paths), so the dir can now leave the corpus:
            # the re-sample that follows writes a SECOND dir for this idea, and
            # `_discover_spec_dir` refuses to see two.
            killed = _killed_spec_dir(result)
            if killed is not None:
                archive_killed_spec(killed)
            continue

        if stage == "s0_ideas":
            raise RuntimeError(
                f"{slot.slug}: S0 reported a failure ({result['reason']}) — architecture §4 gives "
                "the sampler no failure edge; an infeasible draw is a config error before spend"
            )

        _charge_offledger(slot, result["cost"])   # spent, but no line can carry it
        return _block_slot(slot, stage=stage, reason=result["reason"],
                           note=f"architecture §4 draws no failure edge out of {slot.state!r}")


def _stage_findings_path(spec_dir: Path) -> Path:
    """`corpus/<batch-id>/<slug>/worker.stage-findings.json` — the P-1/P-2 feed.

    The same `.with_name` sibling idiom `_decl_only_marker_path` below and
    `SlotContext.verifier_report_path` use, so the file sits beside the worker
    and never inside it (a file in the worker tree trips its own scaffold scope
    check and makes `make validate` green unreachable).
    """
    worker = spec_dir / WORKER_DIRNAME
    return worker.with_name(worker.name + STAGE_FINDINGS_SUFFIX)


def _write_stage_findings(spec_dir: Path | None, stage: str, result: Mapping) -> Path | None:
    """Record a gate/S4/S6 failure where the NEXT S2 session will read it.

    Contracts P-1 §2 and P-2 §1/§2. The bytes are the verifier feed's own shape
    — `{verdict: "reject", reject_reasons: [{code, detail}]}` — because the S2
    runner renders them with `s2_implement.findings_section`, the one function
    that feed has always used. This is that feed reused, not a second channel:
    the only thing that is new is which stage wrote the rows.

    A runner that declared `findings` gets its rows verbatim (the gate's failing
    check ids and notes, S6's failing seeds). A runner that declared none — a
    fake runner in a test, a failure whose whole story is its one-line reason —
    still feeds ONE row built from the stage and the reason, because the point
    of this file is that a rebuild is never blind about why the last one was
    rejected.

    Returns the path written, or None when there is no spec dir to write beside
    (a fake-runner batch that never made one).
    """
    if spec_dir is None:
        return None
    rows = [dict(row) for row in (result.get("findings") or ())]
    if not rows:
        rows = [{"code": f"{stage}-fail", "detail": str(result["reason"])}]
    # EVERY row carries a non-empty `detail`. Two readers demand it and neither
    # may be handed a bullet with a hole in it: `s2_implement.findings_section`
    # renders it to the rebuild, and `s1_spec._escalation_note` refuses a
    # finding without both fields when this same file answers an escalation.
    for row in rows:
        if not str(row.get("detail") or "").strip():
            row["detail"] = str(result["reason"])
    path = _stage_findings_path(spec_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "stage": stage,
                "verdict": "reject",
                "reason": str(result["reason"]),
                "reject_reasons": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _clear_stage_findings(spec_dir: Path | None, stage: str) -> None:
    """Retire the P-1/P-2 payload once the stage that WROTE it has passed.

    The verifier feed clears itself, because the next verify overwrites the same
    report; this one has to be retired deliberately, or a gate fail answered two
    laps ago would keep being quoted to every later rebuild as if it were still
    true.

    Only its OWN author retires it, which is why the file records the stage that
    wrote it. The three run in §4 order, so a slot re-implementing after an S6
    seed-reject passes the gate and S4 again on its way back to S6 — and a gate
    pass says nothing about whether the layout function still crashes at seed 3.
    A payload that cannot be read is removed rather than left to be re-quoted:
    it can no longer say who owns it.
    """
    if spec_dir is None:
        return
    path = _stage_findings_path(spec_dir)
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        owner = payload.get("stage") if isinstance(payload, Mapping) else None
    except (OSError, ValueError):
        owner = stage
    if owner == stage:
        path.unlink(missing_ok=True)


def _decl_only_marker_path(spec_dir: Path) -> Path:
    """`corpus/<batch-id>/<slug>/worker.decl-only-respec.json` — the marker.

    The ONE derivation of that sibling, the same `.with_name` idiom
    `SlotContext.verifier_report_path` uses for the S2b report.
    """
    worker = spec_dir / WORKER_DIRNAME
    return worker.with_name(worker.name + DECL_ONLY_MARKER_SUFFIX)


def _mark_decl_only_respec(spec_dir: Path, old_spec_bytes: bytes) -> None:
    """Write the marker iff this escalated re-spec changed DECLARATIONS ONLY.

    `s1_spec.impl_projection` is the judge: equal projections mean the two
    specs differ only in fields the game code cannot read, so the standing
    `game.py`/`solver.py` still implement the new spec and need only be
    revalidated. Anything else — a real change, or no worker to revalidate —
    writes nothing AND clears any marker an earlier round left behind, so a
    stale marker can never apply across a change that does matter.
    """
    from .s1_spec import impl_projection
    marker = _decl_only_marker_path(spec_dir)
    worker = spec_dir / WORKER_DIRNAME
    new_spec_bytes = (spec_dir / "spec.yaml").read_bytes()
    if impl_projection(old_spec_bytes) != impl_projection(new_spec_bytes) or not worker.is_dir():
        marker.unlink(missing_ok=True)
        return
    marker.write_text(
        json.dumps(
            {
                "to_spec": hashlib.sha256(new_spec_bytes).hexdigest(),
                "from_spec": hashlib.sha256(old_spec_bytes).hexdigest(),
                "ts": _now(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _take_decl_only_marker(spec_dir: Path) -> bool:
    """CONSUME the marker: does it authorize skipping this re-implement?

    Single-shot by construction — the file is deleted whatever it decided, so
    one marker can never license a second S2 run, and the decision cannot
    outlive the validate it authorized. It applies only when it names the
    spec.yaml that is on disk NOW (the projection it was computed from) and
    the implementation it vouches for is still there to revalidate.
    """
    marker = _decl_only_marker_path(spec_dir)
    if not marker.is_file():
        return False
    try:
        claim = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A marker we cannot read makes no claim; it is still consumed below.
        claim = None
    marker.unlink(missing_ok=True)
    worker = spec_dir / WORKER_DIRNAME
    spec_yaml = spec_dir / "spec.yaml"
    return (
        isinstance(claim, Mapping)
        and spec_yaml.is_file()
        and claim.get("to_spec") == _sha256_file(spec_yaml)
        and (worker / "game.py").is_file()
        and (worker / "solver.py").is_file()
    )


# --- contract P-3.2: the round cap, reconciliation and the kill --------------
#
# WHY THE HELPERS BELOW LIVE IN THIS MODULE. The reconciliation amends a SPEC,
# which looks like s1's work — but s1 authors specs with a writer session and
# this is the pipeline writing its own stage artifact with no session at all,
# and the contract's hard rules keep s1 to the in-process linter CALL. The
# machinery it actually rides is this module's: `_mark_decl_only_respec` /
# `_take_decl_only_marker`, the declaration-only re-spec that already exists
# precisely because widening `game.terms` / `knobs.deceptions` cannot invalidate
# the game beside it. A reconciliation IS that re-spec with the writer replaced
# by a mechanical edit, so it belongs beside it. s1 is reached only for
# `lint_spec` and the budget reader, both pure.


def _verifier_reject_reasons(ctx: SlotContext) -> list[dict] | None:
    """The S2b report's `reject_reasons`, or None when there are none to read.

    Read off disk rather than out of the runner's one-line reason, because the
    reconciliation needs each finding's `term` / `lever` and the reason carries
    only codes. A report that is missing, unreadable or not a reject answers
    None, and every caller treats None as "no residual I can reconcile".
    """
    path = ctx.verifier_report_path
    if path is None or not path.is_file():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(report, Mapping) or report.get("verdict") != "reject":
        return None
    reasons = report.get("reject_reasons")
    if not isinstance(reasons, list) or not reasons:
        return None
    # An entry that is not a mapping names no finding; a report whose entries
    # are ALL like that is a report with nothing to reconcile against, and
    # answers None rather than an empty list the caller would have to re-check.
    usable = [reason for reason in reasons if isinstance(reason, Mapping)]
    return usable or None


def _tier_floor(tier: str) -> int:
    """The per-tier MINIMUM a subtractive reconciliation may not drop under.

    `tiers.TIER_TABLE[tier].core_terms[0]` — difficulty-model §3.3's own "terms"
    row, low end (t1 2 · t2 3 · t3 4). That row counts CORE MECHANICS while
    `game.terms` also carries the incidental and lint-forced terms (measured at
    ~3 of overhead in both corpora), so read as a floor on `len(game.terms)` it
    is DELIBERATELY conservative: it refuses only a spec that has been hollowed
    out past anything its tier could possibly be, and it never argues with a
    spec the linter is happy with. Contract P-A.2 asks for a floor guard and the
    signed table is the only measured minimum there is — the four tier RULES are
    all ceilings (`s1_spec._tier_rules`), so the linter enforces no floor of its
    own and this guard cannot be delegated to it.
    """
    from . import tiers
    return tiers.TIER_TABLE[tier].core_terms[0]


def _next_tier(tier: str) -> str | None:
    """The tier one rung up, or None at the ceiling (contract P-A.3: t3 is it)."""
    from . import tiers
    order = list(tiers.TIERS)
    index = order.index(tier)
    return order[index + 1] if index + 1 < len(order) else None


def _reconcile_declarations(
    ctx: SlotContext, reasons: Sequence[Mapping], *, via: str = RECONCILED_VIA_ROUND_CAP
) -> dict:
    """Amend spec.yaml so its DECLARATIONS match what the blind audit found.

    THE PLAN IS `_plan_reconciliation`; this is the WRITE. Contract E-2 §3 split
    them because the plan is pure — it builds the amended document in memory and
    runs §11's linter on that document, which needs no file at all — while this
    half is the only part that touches disk. Before the split the write came
    FIRST and a lint kill restored the bytes afterwards, so "would this amendment
    even lint?" could not be asked without writing; now `_maybe_respec` asks it
    BEFORE spending an S1 session. The net effect on disk is unchanged on every
    path: a refused amendment used to be written and restored byte for byte, and
    is now simply never written.

    `via` names the path that called — `RECONCILED_VIA_ROUND_CAP` or
    `RECONCILED_VIA_EARLY` — and rides into every deception entry this writes,
    so a declaration says which reconciliation put it there (E-1 defect fix #2;
    the default is the round-cap path, which is the caller this function had
    when the provenance was a hardcoded string).

    Returns the plan's `{"ok": True, "added", "dropped", "before", "changes",
    "tier_promoted"}` once the amendment and its fresh lint report are on disk,
    or the plan's own `{"ok": False, "why": …}` untouched.
    """
    plan = _plan_reconciliation(ctx, reasons, via=via)
    if not plan["ok"]:
        return plan

    import yaml

    spec_path = ctx.spec_dir / "spec.yaml"
    spec_path.write_text(
        yaml.safe_dump(plan["doc"], sort_keys=False, allow_unicode=True,
                       default_flow_style=False),
        encoding="utf-8",
    )
    # LEAD SEAM (2026-09-30, Wave A merge): persist the fresh report. The
    # re-lint in the plan is in-memory only, so every reconciled spec shipped
    # with a lint-report.json whose spec_hash named the PRE-amendment bytes —
    # the b005r2 echo game's stale report is the live exhibit (its relint pin
    # went red for exactly this). Same shape run_s1 writes
    # (s1_spec.py:3921-3934): to_json_dict + idea_ref + a fresh ts, spec_hash
    # from the WRITTEN text.
    report = plan["report"]
    report.spec_hash = hashlib.sha256(
        spec_path.read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()
    (spec_path.parent / "lint-report.json").write_text(
        json.dumps(
            {**report.to_json_dict(),
             "idea_ref": plan["idea"]["id"],
             "ts": datetime.now(UTC).isoformat()},
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "ok": True, "added": plan["added"], "dropped": plan["dropped"],
        "before": plan["before"], "changes": plan["changes"],
        "tier_promoted": plan["tier_promoted"],
    }


def _plan_reconciliation(
    ctx: SlotContext, reasons: Sequence[Mapping], *, via: str = RECONCILED_VIA_ROUND_CAP
) -> dict:
    """The amendment, LINTED, with NOTHING written (contract E-2 §3's dry run).

    Every judgement `_reconcile_declarations` makes is made here, including
    §11's verdict on the amended document; the caller's only remaining job is
    the write. `_maybe_respec` calls this and throws the plan away, which is
    what makes "can any spec amendment answer these findings?" answerable
    before a paid session rather than after it.

    Returns `{"ok": True, "doc", "idea", "report", "added", "dropped",
    "before", "changes", "tier_promoted"}` — `doc` is the amended document,
    `idea` the (possibly tier-overlaid) idea, `report` §11's LintReport — or
    `{"ok": False, "why": "<reason>", "class": REFUSED_INPUT | REFUSED_AMENDMENT}`.
    The class is what contract E-2 §3's futility verdict reads: only
    `REFUSED_AMENDMENT` is evidence ABOUT the amendment (it does not fit the
    tier, it does not lint), while `REFUSED_INPUT` says only that this helper
    could not see enough to judge — a fake-runner batch with no §11 spec on
    disk lands there, and must never read as "no re-spec could help".

    Contract P-3.2a as amended by P-A.2/P-A.3, and the operator's 2026-09-29 rulings
    are the shape of it. Nothing here waives a finding. The audit says
    `agent.patrol` is reachable and the spec does not declare it; the spec is
    made to declare it. The audit says the spec's `info.recall` is not reachable
    at all; the spec stops declaring it. Either way the LABEL is made true, and
    the slot then has to come back CLEAN against the amended declarations before
    it goes anywhere.

    On every `ok: False` path spec.yaml is byte-for-byte what it was — this
    function writes nothing at all — so a slot on its way to `parked` cannot
    leave an amended spec behind claiming a reconciliation that did not stand.

    The guards, all of them the contract's:
      * the amended term count must stay inside the TIER's kill budget
        (`s1_spec.escalation_budget_overrun`, the full policy — the same reader
        R-17's escalation re-check uses) — or, P-A.3, EARN THE NEXT TIER;
      * it must not fall under the tier FLOOR (`_tier_floor`);
      * the amended spec must LINT (the §11 linter, in-process and pure), under
        the PROMOTED tier's rules when a promotion happened;
      * and a finding of a reconcilable code that names no term/lever is not
        silently skipped — there is nothing to declare, so it fails here.
    """
    import yaml

    from . import tiers
    from .s0_ideas import load_vocab
    from .s1_spec import (
        _lint_require_render,
        escalation_budget_overrun,
        escalation_term_budget,
        lint_rule_actions,
        lint_silent_levels_floor,
        lint_spec,
    )

    def refused(why: str, reason_class: str = REFUSED_INPUT) -> dict:
        """One `ok: False` answer, CLASSIFIED (contract E-2 §3).

        The default is `REFUSED_INPUT` deliberately: a refusal is evidence of
        futility only when it is evidence about the AMENDMENT, and the
        conservative direction spends a session rather than parking a slot.
        """
        return {"ok": False, "why": why, "class": reason_class}

    spec_dir = ctx.spec_dir
    if spec_dir is None:
        return refused("the slot has no spec dir to reconcile")
    spec_path = spec_dir / "spec.yaml"
    if not spec_path.is_file():
        return refused(f"no spec.yaml at {spec_path}")

    terms: list[str] = []
    levers: list[str] = []
    doomed: list[str] = []
    for reason in reasons:
        code = reason.get("code")
        if code == "undeclared-term":
            name = reason.get("term")
            if not isinstance(name, str) or not name.strip():
                return refused(f"an undeclared-term finding names no term: {reason!r}")
            terms.append(name)
        elif code == "undeclared-deception":
            lever = reason.get("lever")
            if not isinstance(lever, str) or not lever.strip():
                return refused(f"an undeclared-deception finding names no lever: {reason!r}")
            levers.append(lever)
        elif code in RECONCILABLE_SUBTRACTIVE_CODES:
            # P-A.2's new direction. Both subtractive codes carry the term they
            # are about (`s3_verify._reason(..., term=term)`), and one that does
            # not names nothing to withdraw — the same refusal the additive side
            # makes, for the same reason.
            name = reason.get("term")
            if not isinstance(name, str) or not name.strip():
                return refused(f"a {code} finding names no term: {reason!r}")
            doomed.append(name)

    before = spec_path.read_bytes()
    doc = yaml.safe_load(before)
    if not isinstance(doc, dict) or not isinstance(doc.get("game"), dict):
        return refused(f"{spec_path} is not a §11 spec document")
    game = doc["game"]

    declared_terms = game.get("terms")
    if not isinstance(declared_terms, list):
        return refused(f"game.terms is {declared_terms!r}, not a list")
    added: list[str] = []
    for term in terms:
        if term not in declared_terms:
            declared_terms.append(term)
            added.append(term)

    dropped: list[str] = []
    for term in doomed:
        if term not in declared_terms:
            continue
        declared_terms.remove(term)
        dropped.append(term)
        # §11 enforces `terms_introduced ⊆ game.terms` and never the reverse, so
        # a withdrawn declaration MUST leave the curriculum too or the amended
        # spec lint-kills on a rule the withdrawal itself created. This is the
        # same projection `s1_spec.DECLARATION_ONLY_FIELDS` calls
        # declaration-class for exactly this reason.
        levels = game.get("levels")
        if not isinstance(levels, list):
            continue
        for level in levels:
            if not isinstance(level, dict):
                continue
            introduced = level.get("terms_introduced")
            if isinstance(introduced, list) and term in introduced:
                level["terms_introduced"] = [row for row in introduced if row != term]

    knobs = game.get("knobs")
    if knobs is None:
        knobs = game["knobs"] = {}
    if not isinstance(knobs, dict):
        return refused(f"game.knobs is {knobs!r}, not a mapping")
    deceptions = knobs.get("deceptions")
    if deceptions is None:
        deceptions = knobs["deceptions"] = []
    if not isinstance(deceptions, list):
        return refused(f"game.knobs.deceptions is {deceptions!r}, not a list")
    for lever in levers:
        # SUBSTRING containment is the declaration rule (§10 / s3_verify's
        # `detect_levers`), so an entry that already names this lever needs no
        # second one — and the entry written here leads with the lever's own
        # name precisely so the declaration provably holds.
        if any(isinstance(entry, str) and lever.lower() in entry.lower()
               for entry in deceptions):
            continue
        deceptions.append(RECONCILED_DECEPTION.format(lever=lever, via=via))
        added.append(lever)

    if not added and not dropped:
        return refused("every residual finding is already declared")

    idea = None
    if ctx.idea_path.is_file():
        try:
            idea = json.loads(ctx.idea_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            idea = None
    policy = tiers.tier_policy(ctx.cfg)

    # --- the tier guards (P-A.2 floor, P-A.3 auto-retier) -------------------
    #
    # `idea` is the tier's CARRIER for both the budget reader and the linter
    # (`s1_spec._idea_tier` reads `idea["tier"]`, and the spec has never had a
    # tier field of its own). A promotion must NOT rewrite idea.json — ideas are
    # immutable, P-A.3 — so the promoted tier rides in an in-memory OVERLAY of
    # the idea from here on, and the durable record is `game.tier` in spec.yaml
    # plus the ledger line.
    # Both guards are SILENT on every absence the tier rules are silent on — no
    # `tiers:` block, no idea, no tier the signed table carries, no armed
    # `term_budget`. That is the absent-facet pattern this whole layer keeps: a
    # batch that never heard of tiers reconciles exactly as it did yesterday.
    armed = escalation_term_budget(idea, policy)
    tier_promoted: dict | None = None
    if armed is not None:
        tier, _budget = armed
        floor = _tier_floor(tier)
        if len(declared_terms) < floor:
            return refused(
                f"the amended spec declares {len(declared_terms)} terms, under "
                f"tier {tier}'s floor of {floor}", REFUSED_AMENDMENT)
    overrun = escalation_budget_overrun(doc, idea, policy)
    if overrun is not None:
        tier, budget, count = overrun
        promoted = _next_tier(tier)
        headroom = (
            None if promoted is None or policy is None or policy.term_budget is None
            else policy.term_budget.get(promoted)
        )
        if headroom is None or count > headroom:
            # Over the CEILING (t3's 10, or whatever the batch armed for the top
            # tier). P-A.3 is explicit: never trim real mechanics to fit — the
            # slot parks with the amendment unwritten.
            return refused(
                f"the amended spec declares {count} terms against the {tier} "
                f"budget of {budget}", REFUSED_AMENDMENT)
        # The game outgrew its tier. Promote it, record the promotion in the
        # spec, and re-check against the NEW tier (the linter below runs on the
        # promoted tier's rules through the same overlay).
        game[SPEC_TIER_FIELD] = promoted
        idea = {**(idea or {}), "tier": promoted}
        tier_promoted = {
            "from": tier, "to": promoted, "terms": count,
            "budget": budget, "new_budget": headroom,
            "reason": TIER_PROMOTION_REASON.format(
                before=tier, after=promoted, count=count, budget=budget
            ),
        }
        still_over = escalation_budget_overrun(doc, idea, policy)
        if still_over is not None:
            new_tier, new_budget, new_count = still_over
            return refused(
                f"the amended spec declares {new_count} terms against the "
                f"{new_tier} budget of {new_budget}", REFUSED_AMENDMENT)

    # §11's verdict on the AMENDED DOCUMENT, in memory. `lint_spec` is pure
    # ("no config, no disk" — s1_spec.py:2981) and takes the parsed document, so
    # this never needed the write that used to precede it.
    report = lint_spec(
        doc, set(load_vocab(ctx.cfg)), idea, tier_policy=policy,
        require_render=_lint_require_render(ctx.cfg),
        rule_actions=lint_rule_actions(ctx.cfg),
        silent_levels_floor=lint_silent_levels_floor(ctx.cfg),
    )
    if not report.passed:
        rules = ", ".join(sorted({kill["rule"] for kill in report.kills}))
        return refused(f"the amended spec lint-kills: {rules}", REFUSED_AMENDMENT)
    if idea is None or not isinstance(idea.get("id"), str):
        # The writer below stamps `idea_ref` off this, and `run_s1` has always
        # had a real idea to stamp. An absent one is an INPUT refusal, not a
        # verdict about the amendment: a plan nobody can record is not a plan
        # that failed. (Pre-E-2 this raised a TypeError from the json writer,
        # three lines after the spec had already been overwritten.)
        return refused(f"{ctx.idea_path} carries no idea id to stamp the lint report with")
    return {
        "ok": True, "doc": doc, "idea": idea, "report": report,
        "added": added, "dropped": dropped, "before": before,
        "changes": _reconcile_changes(added, dropped),
        "tier_promoted": tier_promoted,
    }


def _reconcile_changes(added: Sequence[str], dropped: Sequence[str]) -> str:
    """The amendment as one ledger phrase: additions with `+`, drops with `-`.

    Contract P-A.1's own spelling (`+info.recall, -gate.plate`). Additions lead
    because the additive direction is the one every shipped reconciliation has
    taken; within each direction the order is the audit's.
    """
    return ", ".join([*(f"+{name}" for name in added), *(f"-{name}" for name in dropped)])


def _round_cap_verdict(slot: _Slot, *, ctx: SlotContext, cfg: Mapping, result: Mapping,
                       round_cap: int, ledger_path: Path, batch_id: str,
                       bdir: Path) -> str:
    """The slot has spent its `verifier.round_cap`-th rejecting round (P-3.2).

    Two ways out and no third. Path (a): every residual reject reason is
    DECLARATION-SIDE (in EITHER direction now — contract P-A.2), the amendment
    fits the tier budget or earns the next tier (P-A.3) and lints, and the slot
    goes back for exactly ONE confirming round — it re-enters `implemented`
    through the declaration-only re-spec this module already owns, because the
    game bytes are untouched and only the spec's declarations moved. Path (b):
    anything else, and the slot PARKS with the residual codes in the reason.

    PATH (b) IS NO LONGER A DEATH. OPERATOR RULING (2026-09-29, on the record,
    verbatim): "We should never kill. Even if it is not satisfied eventually
    let's not kill." Contract P-A.4 routes every would-kill outcome here to
    `parked` — terminal for the run, artifacts intact, outside the attrition
    ratio, never a reason to abort the batch.

    CONTRACT E-2 §1 adds the CHURN filter, which is not knob-gated because it
    is not a policy: a residual whose only content is "undo what a prior
    reconciliation did" is refused here exactly as it is on the early path.

    Returns "terminal" (the slot parked) or "continue".
    """
    reasons = _verifier_reject_reasons(ctx)
    codes = (", ".join(str(reason.get("code")) for reason in reasons) if reasons
             else str(result["reason"]))

    def park(why: str) -> str:
        return _park_slot(
            slot, from_state="implemented",
            reason=f"{ROUND_CAP_PARK_REASON.format(codes=codes)} "
                   f"(verify round {_verify_rounds(slot.history) + 1}, "
                   f"verifier.round_cap {round_cap}; {why})",
            hashes=input_hashes(_context(cfg, slot, batch_id=batch_id,
                                         stage="s3_verify", bdir=bdir)),
            cost=result["cost"], ledger_path=ledger_path)

    if reasons is None:
        return park("no readable verifier report to reconcile against")
    residual = {str(reason.get("code")) for reason in reasons}
    off_declaration = sorted(residual - set(RECONCILABLE_CODES))
    if off_declaration:
        # A solver-quality failure, a forbidden static, a look-alike: every one
        # of them is a claim about the GAME, and no edit to a declaration can
        # make it true. (A dead spec term and an unreachable declared mechanic
        # left this list at P-A.2 — those ARE declaration-side, in the
        # subtractive direction, and the spec now withdraws the claim.)
        return park(f"residual(s) no declaration can answer: {', '.join(off_declaration)}")

    # CONTRACT E-2 §1. What is left of the residual once the amendments that
    # would undo a prior reconciliation are dropped.
    reasons, churn = _split_churn(reasons, slot.history)
    if churn and not reasons:
        # Churn and NOTHING else. The declarations stand; the slot gets one
        # revalidating round, which at the cap is the same single allowance path
        # (a) buys — and on the REPEAT it parks, because a finding that recurs
        # after the ledger has called it churn is no longer a one-off flip.
        if set(churn) <= _churn_refused_before(slot.history):
            return park(f"{CHURN_REFUSED_REASON.format(churn=', '.join(churn))} "
                        f"a second time — {CHURN_REFUSED_NOTE}")
        return _churn_continue(slot, ctx=ctx, cfg=cfg, result=result, churn=churn,
                               ledger_path=ledger_path, batch_id=batch_id, bdir=bdir)

    if _reconciled_before(slot.history):
        return park("the audit rejected again AFTER the declarations were reconciled")

    outcome = _reconcile_declarations(ctx, reasons, via=RECONCILED_VIA_ROUND_CAP)
    if not outcome["ok"]:
        return park(outcome["why"])

    # The amendment is on disk. Mark it as the declaration-only re-spec it is,
    # so §2's cascade revalidates the standing implementation instead of paying
    # for a rewrite that nothing in the new spec can change, and the slot
    # re-enters `implemented` -> s3_verify for its ONE confirming round.
    _mark_decl_only_respec(ctx.spec_dir, outcome["before"])
    # Hashes re-read AFTER the write: the line records the spec as the
    # reconciliation left it, which is the spec the confirming round audits.
    hashes = input_hashes(_context(cfg, slot, batch_id=batch_id, stage="s3_verify", bdir=bdir))
    _record(slot, append_transition(
        ledger_path, slug=slot.slug, from_state="implemented", to_state="spec_ok",
        reason=f"{RECONCILE_REASON.format(added=outcome['changes'])} "
               f"({_reconcile_notes(outcome, f'round_cap {round_cap}', result, churn=churn)})",
        hashes=hashes, cost=result["cost"]))
    return "continue"


def _park_slot(slot: _Slot, *, from_state: str, reason: str, hashes: Mapping,
               cost: Mapping | None, ledger_path: Path) -> str:
    """Park `slot` from `from_state` — P-A.4's park, LIFTED (contract E-2 §2).

    It was a closure inside `_round_cap_verdict` with `from_state="implemented"`
    hardcoded, which is why no other failure lane could park. Everything else is
    unchanged, including the caller's job of composing the reason: a park names
    the knob that fired, the count and the residual, and only the caller knows
    those.

    OPERATOR RULING (2026-09-29, verbatim) is what every caller is implementing:
    "We should never kill. Even if it is not satisfied eventually let's not
    kill." Terminal for the run, artifacts intact, outside the attrition ratio,
    never a reason to abort a batch.
    """
    _record(slot, append_transition(
        ledger_path, slug=slot.slug, from_state=from_state, to_state="parked",
        reason=reason, hashes=hashes, cost=cost))
    return "terminal"


def _churn_continue(slot: _Slot, *, ctx: SlotContext, cfg: Mapping, result: Mapping,
                    churn: Sequence[str], ledger_path: Path, batch_id: str,
                    bdir: Path) -> str:
    """A round whose WHOLE residual was churn: refuse it and revalidate (E-2 §1).

    THE MECHANISM, stated because the contract leaves the choice to the
    implementer ("your mechanism, say which"). The round resolves the way a
    SUCCESSFUL reconciliation resolves — an `implemented --> spec_ok` line, the
    declaration-only marker, and a `continue` — with one difference: the spec is
    not amended, because the amendment on offer was the undoing of a prior one.
    So no session is spent, no declaration moves, the standing implementation is
    revalidated rather than rewritten, and the slot gets one more audit round.

    WHY NOT A ROUTE TO `verified`. "Pass-equivalent" cannot mean travelling the
    accept edge: `worker.verifier-report.json` on disk says `reject`, the gate
    CONSUMES that verdict and never re-decides it (§3 layer 3,
    `_gate_verifier_report`), and s3_verify is read-only to this contract — so a
    slot pushed to `verified` would simply fail the gate on the same report. The
    honest pass-equivalence available to the orchestrator is the one above: the
    round costs no re-spec and does not park.

    THE REJECT IS STILL A REJECT. The line is an `implemented --> spec_ok` line
    like P-A.1's, so it increments `_verify_rounds` and the reject ladder, and a
    slot that churns forever reaches `verifier.round_cap` — where
    `_churn_refused_before` makes the repeat a park.
    """
    # The same machinery path (a) uses, with the CURRENT bytes as the "before":
    # nothing changed, so the projection is trivially equal and the marker is
    # written, which is what keeps §2's cascade from paying for a rewrite.
    spec_path = None if ctx.spec_dir is None else ctx.spec_dir / "spec.yaml"
    if spec_path is not None and spec_path.is_file():
        _mark_decl_only_respec(ctx.spec_dir, spec_path.read_bytes())
    hashes = input_hashes(_context(cfg, slot, batch_id=batch_id, stage="s3_verify", bdir=bdir))
    _record(slot, append_transition(
        ledger_path, slug=slot.slug, from_state="implemented", to_state="spec_ok",
        reason=f"{CHURN_REFUSED_REASON.format(churn=', '.join(churn))} "
               f"({CHURN_REFUSED_NOTE}; {result['reason']})",
        hashes=hashes, cost=result["cost"]))
    return "continue"


def _reconcile_notes(outcome: Mapping, lead: str | None, result: Mapping,
                     *, churn: Sequence[str] = ()) -> str:
    """The parenthetical every reconciliation line carries: what and why.

    `lead` is the knob that fired (the round cap names itself; P-A.1's early
    reason already carries its own `<=N`, so it passes None), then P-A.3's
    promotion when there was one — that line IS the record of the promotion,
    because idea.json is never rewritten — then the verifier reject this
    amendment answers, verbatim.

    `churn` (contract E-2 §1) is the amendments this round REFUSED while
    reconciling the rest. Named here rather than on a line of its own because a
    partial churn is one event: the reconciliation that happened and the
    withdrawal that did not. Empty — every round before this contract, and every
    round with no prior reconciliation to undo — adds nothing, so the line's
    bytes are unchanged.
    """
    promoted = outcome.get("tier_promoted")
    notes = [] if lead is None else [lead]
    if churn:
        notes.append(f"{CHURN_REFUSED_REASON.format(churn=', '.join(churn))} "
                     f"— {CHURN_REFUSED_NOTE}")
    if promoted:
        notes.append(str(promoted["reason"]))
    notes.append(str(result["reason"]))
    return "; ".join(notes)


def _reconcile_early_verdict(slot: _Slot, *, ctx: SlotContext, cfg: Mapping, result: Mapping,
                             cap: int, ledger_path: Path, batch_id: str, bdir: Path) -> bool:
    """A SMALL declaration-side mismatch, answered on the spot (contract P-A.1).

    OPERATOR RULING (2026-09-29, on the record, verbatim): "If there's a mismatch
    of 1-2 terms let's just go ahead with it." At ANY rejecting verify round —
    not just the cap — where EVERY reject reason is declaration-side and there
    are at most `cap` of them, the re-spec is skipped and the spec's
    declarations are amended immediately, in both directions (P-A.2), buying
    exactly ONE confirming round through the declaration-only marker.

    Returns True when it reconciled (the caller `continue`s on the line this
    wrote) and False when it did not — and False falls THROUGH to today's
    ladder, unchanged, because below the round cap the ladder is still alive and
    a refused reconciliation is not a park.

    THE REJECT IS NOT A FREE PASS. The line this writes is an
    `implemented --> spec_ok` line like any other reject, so it increments
    `_verify_rounds` (the slot-wide bound) and the reject ladder exactly as the
    round-cap reconciliation's line does. A slot that needs this every round
    still reaches `verifier.round_cap`, where the same reconciliation runs or
    the slot parks (P-A.4).

    `_reconciled_before` is deliberately NOT consulted here: it is the ROUND
    CAP's guard ("the audit rejected again AFTER the declarations were
    reconciled" — the one confirming round is final), and applying it to the
    early path would make "a slot needing it every round" impossible to express.

    CONTRACT E-2 §1 — THE CHURN FILTER, and this path is where the measured
    failure happened: g20261001-5's lines 12 and 14 are both EARLY
    reconciliations, `+manip.terraform` then `-manip.terraform`, on game bytes
    that never moved. This path had no history guard at all, by design (the
    docstring above says why), because the design never anticipated
    withdraw-what-you-added. It has one now, and it is not knob-gated.
    """
    reasons = _verifier_reject_reasons(ctx)
    if not reasons or len(reasons) > cap:
        return False
    residual = {str(reason.get("code")) for reason in reasons}
    if residual - set(RECONCILABLE_CODES):
        return False
    reasons, churn = _split_churn(reasons, slot.history)
    if churn and not reasons:
        # Churn and nothing else. One revalidating round on the first sighting;
        # a repeat falls through to today's ladder, which is the bound this path
        # has always relied on (and the round cap parks it there).
        if set(churn) <= _churn_refused_before(slot.history):
            return False
        _churn_continue(slot, ctx=ctx, cfg=cfg, result=result, churn=churn,
                        ledger_path=ledger_path, batch_id=batch_id, bdir=bdir)
        return True
    outcome = _reconcile_declarations(ctx, reasons, via=RECONCILED_VIA_EARLY)
    if not outcome["ok"]:
        return False
    # Same machinery as the cap's path (a): the game bytes did not move, so §2's
    # cascade revalidates the standing implementation instead of paying for a
    # rewrite, and the slot re-enters `implemented` -> s3_verify to confirm.
    _mark_decl_only_respec(ctx.spec_dir, outcome["before"])
    hashes = input_hashes(_context(cfg, slot, batch_id=batch_id, stage="s3_verify", bdir=bdir))
    _record(slot, append_transition(
        ledger_path, slug=slot.slug, from_state="implemented", to_state="spec_ok",
        reason=f"{RECONCILE_EARLY_REASON.format(cap=cap, changes=outcome['changes'])} "
               f"({_reconcile_notes(outcome, None, result, churn=churn)})",
        hashes=hashes, cost=result["cost"]))
    return True


def _stage_findings_reasons(ctx: SlotContext) -> list[dict] | None:
    """The gate/S4/S6 payload's `reject_reasons`, or None (contract E-2 §3).

    `_verifier_reject_reasons`'s twin for the DOWNSTREAM lane. The file is in
    the verifier feed's own `{verdict, reject_reasons}` shape by construction
    (`_write_stage_findings`), which is the whole reason the feed was reused
    rather than a second channel invented — so this reads it the same way, and
    answers None on every absence rather than an empty list a caller would have
    to re-check.
    """
    path = ctx.stage_findings_path
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, Mapping):
        return None
    rows = payload.get("reject_reasons")
    if not isinstance(rows, list) or not rows:
        return None
    usable = [row for row in rows if isinstance(row, Mapping)]
    return usable or None


def _spec_answerable(code: str) -> bool:
    """Could ANY spec amendment answer a finding with this code? (E-2 §3).

    `FUTILE_CODES` is the closed enumeration of the classes contract E-2 §3
    names; every other code answers True, INCLUDING codes this module has never
    seen. That asymmetry is the whole design: a False parks a slot without
    spending a session, so False is reserved for the four classes the contract
    put in writing, and anything else spends the session.
    """
    return code not in FUTILE_CODES


def _respec_futility(ctx: SlotContext, *, downstream: bool) -> dict | None:
    """Is the re-spec this slot is about to pay for PROVABLY futile? (E-2 §3).

    Returns None (spend the session) or `{"codes": [...], "why": "…"}`.

    THE MEASURED FAILURE. g20261001-5 escalated at line 7 and the re-spec that
    answered it left the spec hash at bd7b492e — byte-identical — because
    `_maybe_respec` only `is_file()`-checked the escalation source and never
    read a finding out of it. Two paid sessions produced no-op declaration
    diffs. So the findings are read FIRST, here, and the question asked is the
    narrow one a machine can answer honestly:

      * EVERY finding is game-side (`_spec_answerable` False) -> futile. No
        declaration edit can make a losing solver win or an unpainted role
        visible, and §3 routes all of them to S2.
      * every finding is a RECONCILABLE code and the mechanical amendment they
        imply provably cannot stand — it does not fit the tier, or it
        lint-kills (`_plan_reconciliation`, the dry run, `REFUSED_AMENDMENT`)
        -> futile. A dry run that could not READ the spec (`REFUSED_INPUT`)
        proves nothing and spends the session.
      * ANY mix of the two, any finding whose code is not in the enumeration,
        no readable findings at all -> NOT futile.

    Deliberately silent on everything it cannot measure: no findings file, an
    unreadable one, a row with no code. The session is spent, exactly as it is
    today.
    """
    reasons = _stage_findings_reasons(ctx) if downstream else _verifier_reject_reasons(ctx)
    if not reasons:
        return None
    # DEDUPED, in the findings' own order: the measured exhibit is five
    # `s6.seed-reject` rows (one per failing seed) and a reason that said so
    # five times would bury the one fact it is there to report. The per-seed
    # detail is not lost — the payload itself stays on disk beside the worker.
    codes = list(dict.fromkeys(str(reason.get("code")) for reason in reasons))
    answerable = [code for code in codes if _spec_answerable(code)]
    if not answerable:
        return {
            "codes": codes,
            "why": "no declaration can answer any of them (every finding is a claim about "
                   "the GAME: the solver, the code, the board or the layout)",
        }
    if set(answerable) <= set(RECONCILABLE_CODES):
        # The dry run (contract E-2 §3's split seam): would the amendment these
        # findings imply even survive §11 and the tier? Asked on the
        # RECONCILABLE findings only — the mechanical amendment is defined for
        # those and for nothing else.
        mechanical = [reason for reason in reasons
                      if str(reason.get("code")) in RECONCILABLE_CODES]
        plan = _plan_reconciliation(ctx, mechanical)
        if not plan["ok"] and plan.get("class") == REFUSED_AMENDMENT:
            return {
                "codes": codes,
                "why": f"the only amendment they imply cannot stand ({plan['why']})",
            }
    return None


def _maybe_respec(slot: _Slot, *, cfg: Mapping, batch_id: str, bdir: Path,
                  stages: Mapping, ledger_path: Path | None = None) -> str | None:
    """Run S1 again when the verifier escalated (§4 `implemented --> spec_ok:
    verifier reject ×2 → respec`, §3 S2b "escalate to S1").

    The escalation is a REASON, not a state: §4 draws no `spec_ok --> respec`
    edge, so the slot stays at `spec_ok` and the re-spec rewrites spec.yaml in
    place. A new spec is a new `spec_hash`, which is exactly what clears both
    the escalation and the ×2 counter (§2: hashes are identity).

    The re-spec is ESCALATED: S1 is handed the verifier report this slot was
    rejected on (`ctx.escalation`), so the writer answers findings instead of
    blind-rewriting the same spec. Measured on the pilot: a blind re-spec
    declared none of the flagged levers AND retitled the game, which wrote a
    SECOND corpus dir for one idea and crashed `_discover_spec_dir` three
    stages later. Both halves are guarded here — no report, no escalation; and
    the dir it started from must still be the dir the idea resolves to.

    CONTRACT E-2 §3 adds the THIRD guard, and it is the one that reads the
    findings rather than merely checking that a file of them exists: armed with
    `orchestrator.respec_feasibility`, a residual no spec amendment could
    answer skips the session entirely and parks the slot (`_respec_futility`).
    Unarmed, this function is byte for byte the one every batch has run.

    Returns "respec-ran", "blocked", "terminal" (contract E-2 §3's futile park)
    or None.
    """
    ctx = _context(cfg, slot, batch_id=batch_id, stage="s1_spec", bdir=bdir)
    spec = None if ctx.spec_dir is None else _sha256_file(ctx.spec_dir / "spec.yaml")
    if not _escalated(slot.history, spec) or slot._respec_done_for == spec:
        return None
    # WHICH REPORT ANSWERS THIS ESCALATION (contracts P-1/P-2). The findings S1
    # rewrites against must be the findings that escalated: a verifier reject
    # escalates on `implemented --> spec_ok` and its findings are S2b's report,
    # while a gate / S4 / S6 reject escalates on one of `DOWNSTREAM_REJECT_EDGES`
    # and S2b's report beside it says PASS — handing S1 a pass as an escalation
    # would hand it a report with no `reject_reasons` at all. The payload the
    # failing stage wrote is in the SAME shape for exactly this reason, so the
    # only thing that changes is which file is read.
    before = ctx.spec_dir
    downstream = (slot.history[-1]["from"], slot.history[-1]["to"]) in DOWNSTREAM_REJECT_EDGES
    escalation = ctx.stage_findings_path if downstream else ctx.verifier_report_path
    old_spec_bytes = b""
    if before is not None:
        # A slot WITH a spec dir escalated: the report is the failing stage's
        # output beside that dir's worker, and without it there is nothing to
        # answer. Block BEFORE the spend — a blind re-spec is the failure this
        # path exists to stop. (No spec dir means no rewrite either: S1 runs
        # plain, as it always has, and writes the slot's first dir.)
        if escalation is None or not escalation.is_file():
            # Named per lane, because the two lanes are missing different files:
            # the verifier's own report, or the gate/S4/S6 payload beside it.
            missing = "gate/S4/S6 findings payload" if downstream else "verifier report"
            return _block_slot(
                slot, stage="s1_spec",
                reason=f"escalated without a {missing} at {escalation}",
                note="§3 S2b escalates WITH its findings; a blind re-spec rewrites the same spec",
            )
        # The spec S1 is about to rewrite IN PLACE, read before it is gone:
        # the declaration-only decision below compares this against what the
        # rewrite leaves at the same path. It exists by the invariant that
        # got us here (`spec` above is its hash).
        old_spec_bytes = (before / "spec.yaml").read_bytes()
        ctx = replace(ctx, escalation=escalation)
    # CONTRACT E-2 §3, and this is the LAST moment before the spend. The
    # findings are read off the same file the escalation points S1 at, so what
    # is judged is exactly what the session would have been answering.
    if _respec_feasibility(cfg):
        futile = _respec_futility(ctx, downstream=downstream)
        if futile is not None:
            # Park, never kill (operator 2026-09-29), and name the session that was
            # NOT spent — the whole point of the knob is that the ledger says
            # why a slot stopped without a bill.
            return _park_slot(
                slot, from_state="spec_ok",
                reason=f"{RESPEC_FUTILE_REASON.format(codes=', '.join(futile['codes']))} "
                       f"({futile['why']}; no S1 session was spent)",
                hashes=input_hashes(ctx), cost=None,
                ledger_path=bdir / LEDGER_NAME if ledger_path is None else ledger_path)
    result = _invoke(stages, "s1_spec", ctx, slot)
    _charge_offledger(slot, result["cost"])   # a re-spec appends no line (§4)
    slot._respec_done_for = spec
    slot.respec_runs += 1
    if not result["ok"]:
        return _block_slot(
            slot, stage="s1_spec", reason=f"re-spec {result['reason']}",
            note="architecture §4 draws no edge from spec_ok to respec",
        )
    if before is not None:
        # IN PLACE means in place: same dir, same slug, new spec content. A
        # second dir (a re-titled spec) or a moved one is named HERE, at the
        # stage that caused it, instead of surfacing as a LedgerError from
        # `_discover_spec_dir` at the next stage that resolves a context.
        try:
            after = _discover_spec_dir(ctx.corpus_dir, ctx.idea_path)
        except LedgerError as exc:
            return _block_slot(
                slot, stage="s1_spec",
                reason=f"escalated re-spec of {before} left idea {ctx.idea_path} claimed by more "
                       f"than one spec dir: {exc}",
                note="§3 S2b re-specs IN PLACE — same dir, same slug, new spec content",
            )
        if after != before:
            return _block_slot(
                slot, stage="s1_spec",
                reason=f"escalated re-spec started in {before} but idea {ctx.idea_path} now "
                       f"resolves to {after}",
                note="§3 S2b re-specs IN PLACE — same dir, same slug, new spec content",
            )
        # Same dir, new content, and the rewrite succeeded: decide here —
        # where BOTH versions exist — whether §2's cascade is about to
        # re-implement a game that nothing in the new spec can change.
        _mark_decl_only_respec(before, old_spec_bytes)
    return "respec-ran"


#: The stale-row note for a TERMINAL slot's changed input (contract H-1 item 10).
RESTAGE_TERMINAL_NOTE = (
    "the slot is terminal ({state}); a changed input is REPORTED, never re-run — "
    "nothing downstream can consume a refreshed artifact, so a re-run would only "
    "spend, and would rewrite a finished slot's evidence under a verdict it no "
    "longer supports. A human re-opens the slot (`arc-games unpark` for a park) "
    "if the change matters"
)


def _restage(slot: _Slot, *, cfg: Mapping, batch_id: str, bdir: Path,
             stages: Mapping) -> str | None:
    """Re-run every ALREADY-RECORDED stage whose inputs changed, in §4 order.

    §2 ⊕ is the rule: "a stage re-runs iff its input hashes changed — this is
    also the resume mechanism (§4)", and §4: "recomputes input hashes, and
    re-queues exactly the games whose stage inputs changed". The walk is in
    stage order, and each stage is compared AFTER the earlier ones re-ran, so
    an edited spec re-implements, which changes `game_hash`, which re-verifies,
    re-gates, re-baselines — the cascade §2 describes, with no stage re-running
    on unchanged inputs.

    The machine is forward-only, so a re-run appends NO ledger line: §4 draws
    no self-edge, and the slot's state is still the state it reached. What the
    re-run does change is the artifact, and the batch report says so. A re-run
    that FAILS blocks the slot: the ledger would otherwise keep claiming a
    verdict the refreshed artifact no longer supports.

    `s0_ideas` is reported but never re-run: its "input" is the draw identity
    (batch seed + slot index), and re-drawing would replace the slot's idea —
    a new game, not a refreshed artifact. The human decides that one.

    A TERMINAL slot gets the same treatment for EVERY stage (contract H-1 item
    10, measured 2026-10-06). Both callers run this before `_work_slot` on every
    slot, terminal or not, and the scheduled-stage skip above keys off
    `NEXT_STAGE`, which a terminal state has none of — so a `packaged` slot whose
    spec bytes changed re-invoked `s2_implement`, `s3_verify` and `s6_package`
    (two priced sessions and a re-package of a shipped game), billed them
    off-ledger, and then `_work_slot` returned "terminal" without looking at
    any of it. Now the walk still hashes and still REPORTS every stale stage
    (`rerun: False` + `RESTAGE_TERMINAL_NOTE`), and invokes nothing.
    """
    if not slot.history:
        return None
    recorded: dict[str, dict] = {}
    for line in slot.history:
        stage = EDGE_STAGE[(line["from"], line["to"])]
        if stage is not None:
            recorded[stage] = line
    stale: list[dict] = []
    for stage in STAGES:
        line = recorded.get(stage)
        if line is None:
            continue
        # SCHEDULED is not stale: a recorded line for a stage at/after the
        # one the state machine runs NEXT is from a superseded cycle (a
        # resume parked at `respec` has a recorded S1 kill, and the next
        # re-sample has not drawn `respec-N/idea-001.json` yet — hashing or
        # re-running S1 here reads a file that does not exist). The cycle
        # re-runs that stage ON-LEDGER when its turn comes, so pre-running
        # it off-ledger would either crash on the missing input or bill the
        # same work twice. Stages BEFORE the next scheduled one are the
        # completed pipeline — they get the full §2 stale walk below.
        # Reachable only since the cap became configurable: at the fixed cap
        # of 2, `respec` was always a blocked dead-end, so no resume ever
        # started mid-cycle.
        nxt = NEXT_STAGE.get(slot.state)
        if nxt is not None and STAGES.index(stage) >= STAGES.index(nxt):
            stale.append({"stage": stage, "recorded": line["hashes"]["stage_input"],
                          "current": None, "rerun": False,
                          "pending": f"state {slot.state!r} re-runs {stage} on-ledger"})
            slot.stale = stale
            continue
        ctx = _context(cfg, slot, batch_id=batch_id, stage=stage, bdir=bdir)
        current = input_hashes(ctx)["stage_input"]
        if current == line["hashes"]["stage_input"]:
            continue
        entry = {"stage": stage, "recorded": line["hashes"]["stage_input"],
                 "current": current, "rerun": stage != "s0_ideas" and not slot.terminal}
        stale.append(entry)
        slot.stale = stale
        if stage == "s0_ideas":
            entry["note"] = (
                "the draw identity changed (batch.seed / slot index); S0 is NOT re-run "
                "automatically — re-drawing replaces the slot's idea"
            )
            continue
        if slot.terminal:
            entry["note"] = RESTAGE_TERMINAL_NOTE.format(state=slot.state)
            continue
        result = _invoke(stages, stage, ctx, slot)
        entry["rerun_ok"] = result["ok"]
        entry["rerun_reason"] = result["reason"]
        entry["cost"] = result["cost"]
        _charge_offledger(slot, result["cost"])
        if not result["ok"]:
            return _block_slot(
                slot, stage=stage, reason=f"re-run on changed inputs failed: {result['reason']}",
                note="the ledger still records this stage's earlier verdict (architecture §2 ⊕)",
            )
    return None


def _slots(cfg: Mapping, batch: Mapping, table: Mapping) -> list[_Slot]:
    ids = [slot_id(batch["id"], index) for index in range(1, batch["size"] + 1)]
    unknown = sorted(set(table) - set(ids))
    if unknown:
        raise LedgerError(
            f"ledger holds slug(s) {unknown} that are not slots of batch {batch['id']!r} at "
            f"size {batch['size']} — the config and the ledger disagree"
        )
    slots = []
    for index, slug in enumerate(ids, 1):
        entry = table.get(slug)
        slots.append(_Slot(
            slug=slug, index=index,
            state=entry["state"] if entry else BIRTH,
            history=list(entry["history"]) if entry else [],
            rejects=dict(entry["rejects"]) if entry else _empty_rejects(),
            cost=dict(entry["cost"]) if entry else _empty_cost(),
            first_ts=entry["first_ts"] if entry else None,
            last_ts=entry["last_ts"] if entry else None,
        ))
    return slots


def _withdraw_play_preview(worker_dir: Path | None, game_digest: str | None) -> list[str]:
    """Pull the review preview a PULLED slot left in the play root (D-2).

    The digest is the §2 chain's own `hashes.game` — `sha(game.py + solver.py)`,
    the same number S6 names the mirror dir with — so the pull finds the dir off
    the hashes the ledger line is about to carry, without re-hashing anything.
    No worker dir and no digest mean there is no preview to pull (a fake-runner
    batch, a hand-cleaned tree): an empty withdrawal, not an error.

    Failures RAISE, and the call site runs this BEFORE the ledger lines are
    appended: a withdrawal that did not happen leaves the slot at `played` with
    its review still pending, so the human can re-issue the pull. The
    alternative — a `pulled` line beside a still-playable build in the play menu
    — is the one outcome worth refusing.

    The import is local for the module's standing reason: the state machine, the
    ledger and resume must not drag the packager (and arcengine, numpy) in. A
    pull is a deliberate human action, so paying for it here is fine.
    """
    if worker_dir is None or game_digest is None:
        return []
    from .s6_package import withdraw_play_preview
    return withdraw_play_preview(worker_dir, game_digest[:8])


def _withdraw_shelf_game(worker_dir: Path | None) -> list[str]:
    """Take a pulled game off the shared shelf (contract P-3 §2).

    The unship half of the promotion the packaged-success site performs. A PULLED
    slot normally has nothing on the shelf — `reviewed --> pulled` and
    `reviewed --> packaged` are alternative edges, so a pull means S6 never ran —
    and `withdraw_game` answers that with an empty list rather than an error. The
    call is here anyway because the one case where it is NOT a no-op is the one
    worth covering: a game that was promoted (by an earlier accept, or by the
    backfill) and is being pulled now must not stay shared.

    IT TAKES THE WORKER DIR, NOT `slot.slug`. `slot.slug` is the LEDGER key
    (`b003r2-simplicity-s001`); the shelf is named after the GAME
    (architecture §2's `corpus/<batch>/<slug>/`), so passing the ledger key would
    withdraw nothing and say so cheerfully. `s6_package.game_slug` is the
    promoter's own derivation, which is why the name it returns is the name the
    entry was written under. No worker dir (a fake-runner batch, a hand-cleaned
    tree) means there is nothing to withdraw: an empty list, not an error — the
    same rule `_withdraw_play_preview` above already follows.

    The import is local for this module's standing reason: the state machine, the
    ledger and resume must not drag the packager (and arcengine, numpy) in.
    """
    if worker_dir is None:
        return []
    from .s6_package import game_slug, withdraw_game
    return withdraw_game(game_slug(worker_dir))


def _apply_review(ledger_path: Path, slots: Sequence[_Slot], review: tuple,
                  cfg: Mapping, batch_id: str, bdir: Path) -> dict:
    """The HUMAN decision at `played` — accept, or pull.

    CANON vs CONTRACT (flagged, not silently resolved): the B11 build contract
    says a pull "appends played→pulled", but architecture §4 draws NO
    `played --> pulled` edge — `pulled` is reachable only through
    `reviewed --> pulled`, and §4 is the authority for the machine. A pull
    therefore records what actually happened: a human REVIEWED the game
    (`played --> reviewed`) and pulled it (`reviewed --> pulled`), both lines
    in ONE write so the decision can never be half-recorded. The slot still
    terminalizes inside the one call the contract asks for.
    """
    if (not isinstance(review, (tuple, list))) or len(review) != 2:
        raise ValueError(f"review must be (slug, {REVIEW_DECISIONS}), got {review!r}")
    slug, decision = review
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"review decision must be one of {REVIEW_DECISIONS}, got {decision!r}")
    slot = next((candidate for candidate in slots if candidate.slug == slug), None)
    if slot is None:
        raise ValueError(
            f"no slot {slug!r} in this batch (slots: {[s.slug for s in slots]})"
        )
    if slot.state != "played":
        raise ValueError(
            f"{slug} is in state {slot.state!r}; a review decision only applies at 'played' "
            "(architecture §4)"
        )
    ctx = _context(cfg, slot, batch_id=batch_id, stage="s6_package", bdir=bdir)
    hashes = input_hashes(ctx)
    lines = [_line(slug=slug, from_state="played", to_state="reviewed",
                   reason=f"human {decision}", hashes=hashes, cost=None)]
    # Contract D-2: a pull is the one decision that has to UNDO something. The
    # withdrawal happens first so the line below records what really left the
    # play root, and it is bookkept the way S6's own withdrawal is — a list of
    # the paths removed (`run_s6`'s `withdrawn`), named in the reason and carried
    # in the report's `review.applied`. An accept needs no pull: S6's packaging
    # mirror overwrites the preview dir with the un-suffixed title.
    withdrawn: list[str] = []
    if decision == "pull":
        withdrawn = _withdraw_play_preview(ctx.worker_dir, hashes["game"])
        reason = "human pull (architecture §4: reviewed --> pulled)"
        if withdrawn:
            reason = f"{reason}; withdrew the play preview ({len(withdrawn)} file(s))"
        # Contract P-3 §2/§5: the shelf withdrawal is bookkept with the preview's
        # but is added AFTER the reason is composed, so a pull's LEDGER LINE stays
        # byte-identical to its pre-P-3 text whether or not the game was on the
        # shelf. The paths still reach the report through `review.applied`.
        withdrawn = [*withdrawn, *_withdraw_shelf_game(ctx.worker_dir)]
        lines.append(_line(slug=slug, from_state="reviewed", to_state="pulled",
                           reason=reason, hashes=hashes, cost=None))
    for line in _append_lines(ledger_path, lines):
        _record(slot, line)
    return {"slug": slug, "decision": decision, "to": slot.state, "withdrawn": withdrawn}


def unpark_slot(cfg: Mapping, *, slug: str, reason: str) -> dict:
    """Lift ONE slot's park — contract E-5's operator act, and the whole of it.

    It is the sibling of `_apply_review` above: an out-of-band human decision
    that the LEDGER records and nothing else. It appends EXACTLY ONE line,
    `parked --> <the state the slot parked FROM>`, and it RUNS NO STAGE — the
    lift is a recorded operator act and the resume is the machine, the same
    separation `gen.worker --resync` keeps. The caller (`gen.cli.cmd_unpark`)
    prints the state restored and the resume command; this function spends
    nothing, deletes nothing and touches no artifact.

    THE DESTINATION IS NOT AN ARGUMENT. It is `last_park_line(history)["from"]`,
    read mechanically off the ledger, and `assert_transition` then gates it
    against `TRANSITIONS["parked"]` — so a ledger carrying a park from a state
    the table has no lift for is refused rather than lifted into an edge nobody
    drew. A caller-chosen state would be a way to skip a stage.

    EVERY REFUSAL IS LOUD AND WRITES NOTHING (E-5 §2): a slug that is not a slot
    of this batch, a slot that is not parked, a blank `--reason`. All three raise
    before the one append, so a refused lift leaves the ledger byte-identical —
    and `ValueError` is the right class for all of them for the reason
    `IllegalTransition` gives: it is bad input, not a broken machine.

    NO EXEMPTION TRAVELS WITH THE LIFT (E-5 §3). Nothing here resets a counter,
    clears a findings payload, amends a spec or arms a knob: the slot re-enters
    the ordinary ladder under the batch's CURRENT config with its reject and
    round history standing, and if the stage that parked it fails again it may
    park again. That is one more operator act and one more line.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(
            f"unpark needs a non-empty reason, got {reason!r} — the lift is an operator "
            "act and the ledger is where it is accounted for; a blank reason would "
            "record that somebody did this and never why"
        )
    batch = batch_config(cfg)
    bdir = batch_dir(cfg)
    ledger_path = bdir / LEDGER_NAME
    # The replay is the read: it validates the whole file against §4 (a ledger
    # that cannot have been produced by this machine raises here) and it is what
    # says which state the slot is ACTUALLY in — never the batch report, which
    # may predate the last line.
    slots = _slots(cfg, batch, replay_ledger(ledger_path))
    slot = next((candidate for candidate in slots if candidate.slug == slug), None)
    if slot is None:
        raise ValueError(
            f"no slot {slug!r} in batch {batch['id']!r} (slots: {[s.slug for s in slots]})"
        )
    if slot.state != "parked":
        raise ValueError(
            f"{slug} is in state {slot.state!r}, not 'parked' — there is no park to lift. "
            f"A park is reachable from {list(PARK_SOURCES)}; a slot that merely stopped "
            "is resumed, not unparked"
        )
    park = last_park_line(slot.history)
    if park is None:   # pragma: no cover - replay guarantees a park line here
        raise LedgerError(
            f"{ledger_path}: {slug} replays to 'parked' with no `… --> parked` line — "
            "the ledger does not replay"
        )
    restored = str(park["from"])
    # The hashes are CURRENT (§2 ⊕), read for the stage that will run from the
    # restored state: the lift's provenance claim is "these were the bytes when
    # the park was lifted", which is the only claim it is entitled to make. They
    # are provenance only — `EDGE_STAGE` gives this edge no stage, so no resume
    # and no cost row ever compares against them.
    stage = NEXT_STAGE[restored]
    if stage is None:   # pragma: no cover - wiring check, not a policy
        raise IllegalTransition(
            f"NEXT_STAGE runs nothing from {restored!r}, so lifting a park into it would "
            "strand the slot a second time"
        )
    ctx = _context(cfg, slot, batch_id=batch["id"], stage=stage, bdir=bdir)
    line = append_transition(
        ledger_path, slug=slug, from_state="parked", to_state=restored,
        reason=UNPARK_REASON.format(text=reason.strip(), park=park["reason"]),
        hashes=input_hashes(ctx), cost=None)
    _record(slot, line)
    return {"slug": slug, "from": "parked", "to": restored, "stage": stage,
            "park_reason": str(park["reason"]), "park_ts": str(park["ts"]),
            "line": line, "ledger": str(ledger_path), "batch_id": str(batch["id"])}


def _cost_table(slots: Sequence[_Slot]) -> dict:
    """Per-stage cost, summed off the LEDGER (so a resume keeps earlier spend).

    `off_ledger` is THIS run's spend on stage runs that appended no transition
    — a green-loop attempt under the cap, a re-spec, a stale re-run, a blocked
    stage. §4 gives them no edge, so the ledger cannot carry their cost and the
    report would otherwise under-report the batch's real spend.
    """
    by_stage: dict[str, dict] = {
        stage: {**_empty_cost(), "transitions": 0, "reported": 0} for stage in STAGES
    }
    total = {**_empty_cost(), "reported": 0}
    for slot in slots:
        for line in slot.history:
            stage = EDGE_STAGE[(line["from"], line["to"])]
            if stage is None:
                continue
            row = by_stage[stage]
            row["transitions"] += 1
            if line["cost"] is None:
                continue
            row["reported"] += 1
            total["reported"] += 1
            _add_cost(row, line["cost"])
            _add_cost(total, line["cost"])
    off_ledger = {**_empty_cost(), "runs": 0}
    for slot in slots:
        off_ledger["runs"] += slot.offledger_cost["runs"]
        _add_cost(off_ledger, slot.offledger_cost)
    return {"by_stage": by_stage, "total": total, "off_ledger": off_ledger}


def _attrition(*, dead: int, pulled: int, slots: int, max_attrition: float) -> dict:
    """§4's kill criterion, computed in ONE place for the report and `--status`.

    DEAD ONLY (contract D-3 §5). `pulled` is the HUMAN decision at `played`:
    the review looked at a finished, gated, played game and said no. The abort
    machinery exists for SYSTEMATIC failure — "a systematic failure should stop
    spend, not burn the batch" — and a human pull is the opposite of that: it
    is the review working. Counting it as attrition made b003r2, a batch whose
    two slots BOTH reached the human and one of which was accepted and
    packaged, ship a report stamped BATCH ABORTED.

    The pull is not hidden: it keeps its own count here and is printed beside
    the deaths. It is simply not in the fraction.

    CONTRACT P-A.4 adds a second state that is NOT attrition, on the same
    reasoning and on the operator's 2026-09-29 ruling ("We should never kill. Even if
    it is not satisfied eventually let's not kill."): a `parked` slot is a
    residual nobody could reconcile, not a systematic failure, and it never
    counts here. It needs no parameter to do that — this function counts `dead`
    and only `dead` — but the omission is deliberate and is written down so a
    later reader does not "fix" it.
    """
    fraction = dead / max(slots, 1)
    pulls = (
        f" ({pulled} human pull(s) counted separately — a pull is a review verdict, "
        "not attrition)" if pulled else ""
    )
    return {
        "dead": dead, "pulled": pulled, "slots": slots,
        "fraction": fraction, "max_attrition": max_attrition,
        "over": fraction > max_attrition,
        "reason": (
            f"dead {dead}/{slots} = {fraction:.2f} > max_attrition {max_attrition} — "
            "architecture §4 kill criteria: a systematic failure should stop spend, not "
            f"burn the batch{pulls}"
        ),
    }


def _slot_report(slot: _Slot, cfg: Mapping, batch_id: str, bdir: Path) -> dict:
    ctx = _context(cfg, slot, batch_id=batch_id, stage="s0_ideas", bdir=bdir)
    # CONTRACT E-2 §1: the churn refusals, read off the ledger like everything
    # else here. ADDITIVE AND ONLY WHEN THERE IS ONE (`report["parallel"]`'s
    # pattern, not `parked`'s): the memory rule is not knob-gated, so an
    # always-present key would move every batch's report bytes, and a batch that
    # never churned must report exactly what it reported before this contract.
    churn = [str(line["reason"]) for line in slot.history
             if str(line["reason"]).startswith(CHURN_REFUSED_PREFIX)]
    # CONTRACT E-5 §4 — THE PARK BLOCK IS A CURRENT-STATE FACT. Before this
    # contract a park was the slot's last line forever, so "every park line's
    # reason" and "the park this slot is sitting on" were the same list; with an
    # exit they are not. The block must not count a slot whose park was LIFTED
    # and whose state moved on (its residual is answered, or at least owned by a
    # named operator), and a slot lifted and re-parked must count ONCE, with the
    # LATEST park reason. Both follow from asking the ledger for the park the
    # slot is in RIGHT NOW: `state == "parked"`, and then the last park line
    # (D-3's rule — the report derives its numbers from the ledger, never from
    # what this process happened to do).
    #
    # BYTE-IDENTICAL ON EVERY PRE-E-5 LEDGER, and that is a proof rather than a
    # hope: without a lift edge `parked` is absorbing, so a park line exists iff
    # the slot replays to `parked`, there is at most one of them, and the single
    # element this produces is the single element the comprehension produced.
    park = last_park_line(slot.history) if slot.state == "parked" else None
    return {
        "slug": slot.slug, "index": slot.index, "state": slot.state,
        "terminal": slot.terminal, "review_pending": slot.review_pending,
        "blocked": slot.blocked, "stale": slot.stale,
        "transitions": len(slot.history), "rejects": dict(slot.rejects),
        "green_failures": slot.green_failures,
        # Contract P-3: BOTH read off the LEDGER, for the reason D-3 §4 gives
        # for `respec_runs` — the in-memory flag is 0/False on every resume and
        # every real batch resumes. A reconciled slot is still auto-accepted
        # (P-3.3), so the row that shows the accept must show the amendment
        # beside it or the review reads a game whose spec moved and says nothing.
        "auto_accepted": any(str(line["reason"]) == AUTO_ACCEPT_REASON
                             for line in slot.history),
        # BOTH reconciliation flavors (P-3.2a's at the cap and P-A.1's early
        # one), read off the ledger for the same reason everything else here is.
        "reconciled": [str(line["reason"]) for line in slot.history
                       if str(line["reason"]).startswith(
                           (RECONCILE_PREFIX, RECONCILE_EARLY_PREFIX))],
        # Contract P-A.3: the promotion has no edge of its own (it rides the
        # reconciliation's line), so the row recovers it from that line's
        # reason — the ledger IS the record, idea.json is never rewritten.
        #
        # CONTRACT E-5: and it is the one SUBSTRING reader of a reason in this
        # module, so it is also the one that a lift line — which QUOTES another
        # line's reason verbatim (`UNPARK_REASON`) — could be misread by. A
        # quotation is not the thing quoted: lifting a slot whose promotion rode
        # the park reason must not report a second promotion that never
        # happened. Every other reader is prefix-keyed and needs no guard.
        "tier_promoted": [str(line["reason"]) for line in slot.history
                          if TIER_PROMOTION_PREFIX in str(line["reason"])
                          and not str(line["reason"]).startswith(UNPARK_PREFIX)],
        # Contract P-A.4: what parked this slot, in full. Nothing on disk was
        # deleted, so this reason is the whole story of where to pick it up.
        # CONTRACT E-2 §2: keyed on the TO-state, not on the one edge P-A.4
        # drew. A park now also arrives from `verified`, `gated`, `reviewed` and
        # `spec_ok`, and this row is the batch report's only source for the
        # reason — an edge-keyed filter would report those four as nothing at
        # all, which is the silence this key exists to prevent.
        # CONTRACT E-5 §4: and it is the park the slot is sitting on NOW, not
        # every park it has ever taken (see `park` above).
        "parked": [] if park is None else [str(park["reason"])],
        # THE LEDGER's count, not the in-memory one (contract D-3 §4): the
        # counter beside it is this run's only, and a resume starts it at 0.
        "respec_runs": respec_runs_from_ledger(slot.history),
        "respec_runs_this_run": slot.respec_runs,
        "invocations": dict(sorted(slot.invocations.items())),
        "cost": dict(slot.cost), "off_ledger_cost": dict(slot.offledger_cost),
        "first_ts": slot.first_ts, "last_ts": slot.last_ts,
        "paths": {
            "idea": str(ctx.idea_path),
            "spec_dir": None if ctx.spec_dir is None else str(ctx.spec_dir),
            "worker": None if ctx.worker_dir is None else str(ctx.worker_dir),
        },
        **({"churn_refused": churn} if churn else {}),
    }


# --- contract P-5: parallel slots -------------------------------------------
#
# The whole of it is ONE shape: the parent owns everything that is about the
# BATCH (the S0 draw, the corpus heal, the review, the attrition verdict, the
# report), a child owns exactly one SLOT, and the ledger is still the only
# state either of them shares. Nothing below runs unless
# `orchestrator.parallel_slots` is armed beside `workers > 1`.


def _write_json_atomic(path: Path, payload: Mapping) -> Path:
    """Write a json artifact so no reader can ever see half of one.

    Two readers make this necessary rather than tidy: a parent merging a child's
    sidecar while that child is still writing it, and `_discover_spec_dir`
    scanning the shared corpus dir (which is why S1's `idea.json` copy is
    written this way too).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def run_slot(cfg: Mapping, slug: str, *,
             runners: Mapping[str, Callable] | None = None) -> dict:
    """CHILD MODE (contract P-5 §2): drive EXACTLY one slot, write a sidecar.

    This is `run_batch`'s per-slot body and nothing else. Everything batch-wide
    is deliberately NOT here: `sweep_killed_specs` heals the whole corpus,
    `_apply_review` is a human decision about the batch, and
    `batch-report.json` is the merge — a child that touched any of them would
    be racing its siblings over state that is not its own. What it writes is
    its own slug's ledger lines and its own sidecar, and nothing else.

    The caps are read here on `run_batch`'s terms (contract D-3 §1) because a
    child is where the spending happens: a malformed cap must be a config error
    at second zero, not three stages in.
    """
    started = _now()
    batch = batch_config(cfg)
    orchestrator_config(cfg)
    caps = {"respec_cap": _respec_cap(cfg), "verifier_reject_cap": _reject_cap(cfg),
            "verifier_round_cap": _round_cap(cfg),
            "verifier_reconcile_early": _reconcile_early(cfg)}
    auto_accept = _auto_accept(cfg)
    bdir = batch_dir(cfg)
    bdir.mkdir(parents=True, exist_ok=True)
    ledger_path = bdir / LEDGER_NAME

    stages = default_runners() if runners is None else dict(runners)
    unknown = sorted(set(stages) - set(STAGES))
    if unknown:
        raise KeyError(f"unknown stage runner(s) {unknown}; stages are {list(STAGES)}")

    slots = _slots(cfg, batch, replay_ledger(ledger_path))
    slot = next((candidate for candidate in slots if candidate.slug == slug), None)
    if slot is None:
        # The `_slots` discipline, one slot down: a slug the config cannot
        # produce is a wiring error, and the message hands over the slugs it
        # could have meant rather than the fact that this one was wrong.
        raise ValueError(
            f"--slot {slug!r} is not a slot of batch {batch['id']!r} at size "
            f"{batch['size']} — its slots are {[candidate.slug for candidate in slots]}"
        )

    outcome = _restage(slot, cfg=cfg, batch_id=batch["id"], bdir=bdir, stages=stages)
    if outcome is None:
        outcome = _work_slot(slot, cfg=cfg, batch_id=batch["id"], bdir=bdir,
                             ledger_path=ledger_path, stages=stages)

    path = slot_report_path(bdir, slot.slug)
    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": "orchestrator-slot",
        "batch_id": batch["id"],
        "slug": slot.slug,
        "status": "complete" if slot.terminal else "stopped",
        "outcome": outcome,
        # This slot's own §4 semantics, which are the batch's with one slot in
        # it: 0 when there is nothing left to run, 2 when there is.
        "exit_code": 0 if slot.terminal else 2,
        # The whole row, in-memory-only fields included — it is the ONLY way the
        # parent ever learns this slot's off-ledger spend, its block, its stale
        # re-runs, its review stop, its invocation counts and its re-specs.
        "slot": _slot_report(slot, cfg, batch["id"], bdir),
        "config": {"batch": batch, "caps": caps, "auto_accept": auto_accept},
        "timestamps": {"started": started, "finished": _now()},
        "paths": {"batch_dir": str(bdir), "ledger": str(ledger_path),
                  "slot_report": str(path)},
    }
    _write_json_atomic(path, report)
    return report


#: Children this process launched and is still waiting on, so a SIGINT can be
#: forwarded to them (contract P-5 §4). Written by the default seam only.
_LIVE_CHILDREN: dict[str, subprocess.Popen] = {}
_CHILDREN_LOCK = threading.Lock()


def spawn_slot(*, config_path: str | Path | None, slug: str, batch_dir: Path) -> int:
    """THE SPAWN SEAM (contract P-5 §6): run one slot as a child; return its exit.

    Default: a real subprocess — this same module, `--slot <slug>`, on the same
    config path, environment inherited, stdout and stderr appended to the slot's
    own log because a child's console is nobody's terminal. It BLOCKS; the
    parent runs up to `workers` of these at a time and waits the wave out.

    Reached through the MODULE (`spawn_slot(...)` resolved at call time, never a
    name bound at import) for the reason `gen/cli.py` reaches
    `orchestrator.main` that way: this is the one place a test can substitute an
    in-process child that drives `run_slot` with injected runners against the
    SAME ledger file.
    """
    if config_path is None:
        raise ValueError(
            "the P-5 child is a real subprocess and needs the config PATH to hand it: "
            "run_batch was called with parallel slots armed and no `config_path=`. Pass "
            "it, drive the batch through `python -m gen.orchestrator --config <path>`, "
            "or inject an in-process child through `gen.orchestrator.spawn_slot`"
        )
    log = slot_log_path(batch_dir, slug)
    log.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "-m", "gen.orchestrator",
            "--config", str(config_path), "--slot", slug]
    with log.open("ab") as fh:
        child = subprocess.Popen(argv, stdout=fh, stderr=subprocess.STDOUT)
        with _CHILDREN_LOCK:
            _LIVE_CHILDREN[slug] = child
        try:
            return child.wait()
        finally:
            with _CHILDREN_LOCK:
                _LIVE_CHILDREN.pop(slug, None)


def _interrupt_children() -> list[str]:
    """Forward the parent's SIGINT to every live child (contract P-5 §4).

    The parent then WAITS: the ledger is the truth, and a child killed between
    its artifact and its ledger line is the one outcome worth not causing.
    """
    with _CHILDREN_LOCK:
        live = list(_LIVE_CHILDREN.items())
    signalled = []
    for slug, child in live:
        try:
            child.send_signal(signal.SIGINT)
        except (OSError, ValueError):   # already reaped; nothing to forward to
            continue
        signalled.append(slug)
    return signalled


def _run_wave(wave: Sequence[_Slot], *, config_path: str | Path | None,
              bdir: Path, workers: int) -> list[dict]:
    """Run one wave's slots as children, `workers` at a time, and wait for ALL.

    THE OPERATOR'S NEVER-KILL RULING at process scale (2026-09-29, verbatim: "We should
    never kill. Even if it is not satisfied eventually let's not kill."): a
    child that exits nonzero — or whose launcher raises before there is a child
    at all — does not interrupt this wave and cannot reach another slot's work.
    Its ledger state stands, its row here records what happened, and a resume
    runs it again.
    """
    rows: list[dict] = [{"slug": slot.slug, "exit_code": None, "error": None}
                        for slot in wave]
    print(f"[b11] wave: {len(wave)} slot(s) at {min(workers, len(wave))} worker(s) — "
          f"{', '.join(slot.slug for slot in wave)}")

    def _child(index: int, slug: str) -> None:
        try:
            rows[index]["exit_code"] = int(
                spawn_slot(config_path=config_path, slug=slug, batch_dir=bdir))
        except Exception as exc:  # noqa: BLE001 — never-kill: one launcher's failure
            # may not take the wave down with it. No exit code, because no child
            # ever ran; the error text is the whole story the report can carry.
            rows[index]["error"] = f"{type(exc).__name__}: {exc}"

    pool = ThreadPoolExecutor(max_workers=min(workers, len(wave)))
    try:
        futures = [pool.submit(_child, index, slot.slug)
                   for index, slot in enumerate(wave)]
        try:
            for future in futures:
                future.result()
        except KeyboardInterrupt:
            # §4: FORWARD, then WAIT — `wait` and not another `result()` pass,
            # which would re-raise on the first future and leave the rest of the
            # wave still writing while this process walked away.
            signalled = _interrupt_children()
            print(f"[b11] interrupted — forwarded to {len(signalled)} live child(ren) "
                  f"{signalled}; waiting for them to finish writing", file=sys.stderr)
            wait(futures)
            raise
    finally:
        pool.shutdown(wait=True)
    for row in rows:
        print(f"[b11]   {row['slug']} exited {row['exit_code']}"
              + (f" ({row['error']})" if row["error"] else "")
              + f" | log {slot_log_path(bdir, row['slug'])}")
    return rows


def _force_s0(slots: Sequence[_Slot], *, cfg: Mapping, batch_id: str, bdir: Path,
              ledger_path: Path, stages: Mapping) -> None:
    """Advance every pre-S0 slot through EXACTLY the S0 edge, in THIS process.

    Contract P-5 §4. `sample_batch` draws the WHOLE batch in one call, reads
    every idea file before writing any, writes them non-atomically, and appends
    a shared dedupe history whose read window cannot see another process's
    in-flight draw. One process doing that once, before any child exists, takes
    the FIRST draw out of the race entirely — every child's `_restage` then
    finds S0 recorded with an unchanged digest and never calls the sampler at
    all. It does NOT cover the re-draw a slot that lint-kills mid-wave makes
    inside its own child; that one is serialized by the S0 draw lock in
    `default_runners` (contract P-5 addendum 1), which this pre-pass takes too.

    The draw is not free, and this is deliberately the same spend as today:
    `sample_idea` makes one `spec_writer` completion per idea, and in the
    sequential path the first slot's S0 already draws the whole batch in one
    memoized call. The pre-pass moves that call, it does not add one.

    EXACTLY the S0 edge — the slot is left at `ideated` for its child to pick
    up. `_restage` stays the child's (it is per-slot work), and a `respec` slot
    already at the lint-kill cap is skipped for the same reason `_work_slot`
    blocks it instead of re-drawing: the child records that block.
    """
    cap = _respec_cap(cfg)
    for slot in slots:
        if NEXT_STAGE.get(slot.state) != "s0_ideas":
            continue
        if slot.state == "respec" and slot.rejects["lint_kill"] >= cap:
            continue
        ctx = _context(cfg, slot, batch_id=batch_id, stage="s0_ideas", bdir=bdir)
        result = _invoke(stages, "s0_ideas", ctx, slot)
        if not result["ok"]:
            raise RuntimeError(
                f"{slot.slug}: S0 reported a failure ({result['reason']}) — architecture §4 "
                "gives the sampler no failure edge; an infeasible draw is a config error "
                "before spend"
            )
        expected = STAGE_SUCCESS["s0_ideas"]
        if result["to_state"] != expected:
            raise ValueError(
                f"runner 's0_ideas' reported ok with to_state={result['to_state']!r}; "
                f"architecture §4 lands it on {expected!r}"
            )
        hashes = input_hashes(
            _context(cfg, slot, batch_id=batch_id, stage="s0_ideas", bdir=bdir))
        _record(slot, append_transition(
            ledger_path, slug=slot.slug, from_state=slot.state, to_state=expected,
            reason=result["reason"], hashes=hashes, cost=result["cost"]))


def _refresh_from_ledger(slots: Sequence[_Slot], *, cfg: Mapping, batch: Mapping,
                         ledger_path: Path) -> None:
    """Re-read every slot's LEDGER-derived fields; the parent's own ones stand.

    The parallel parent runs no stage after the S0 pre-pass — the children do —
    so its `_Slot` objects go stale the moment one of them appends. Everything
    the ledger carries is re-read here off a fresh replay; everything it cannot
    carry is either the parent's own (the pre-pass `invocations`) or a child's,
    and `_merge_sidecars` is where the latter arrives.
    """
    fresh = {slot.slug: slot for slot in _slots(cfg, batch, replay_ledger(ledger_path))}
    for slot in slots:
        replayed = fresh[slot.slug]
        slot.state = replayed.state
        slot.history = replayed.history
        slot.rejects = replayed.rejects
        slot.cost = replayed.cost
        slot.first_ts = replayed.first_ts
        slot.last_ts = replayed.last_ts


def _merge_sidecars(slots: Sequence[_Slot], bdir: Path) -> None:
    """Overlay each child's sidecar onto its slot (contract P-5 §5).

    ONLY the fields no ledger line can carry, because everything else is already
    truer in the replay. A slot with no sidecar — a child that died before it
    could write one — keeps the ledger-derived row and leaves those fields at
    their empty values, which is EXACTLY what today's resume path reports for a
    slot this process did not run.

    A sidecar that cannot be read is said out loud and then treated as missing:
    a merge that raised here would lose the other slots' rows too, which is the
    never-kill ruling read at report time.
    """
    for slot in slots:
        path = slot_report_path(bdir, slot.slug)
        if not path.is_file():
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))["slot"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"[b11] WARNING unreadable slot sidecar {path} ({type(exc).__name__}: "
                  f"{exc}) — {slot.slug} is reported from the ledger alone", file=sys.stderr)
            continue
        slot.blocked = row["blocked"]
        slot.stale = row["stale"]
        slot.review_pending = bool(row["review_pending"])
        slot.green_failures = int(row["green_failures"])
        slot.respec_runs = int(row["respec_runs_this_run"])
        # ADDED, not replaced: the parent's own S0 pre-pass is an invocation of
        # this slot's s0 runner and the child never saw it.
        for stage, count in (row["invocations"] or {}).items():
            slot.invocations[stage] = slot.invocations.get(stage, 0) + int(count)
        slot.offledger_cost = dict(row["off_ledger_cost"])


def _run_parallel(slots: Sequence[_Slot], *, cfg: Mapping, batch: Mapping,
                  orch: Mapping, bdir: Path, ledger_path: Path, stages: Mapping,
                  config_path: str | Path | None) -> tuple[dict | None, list[dict]]:
    """PARENT MODE (contract P-5 §4/§5): S0 once, then wave after wave of children.

    `wave_size` stays the batching unit and `workers` the concurrency inside a
    wave. The attrition verdict is re-derived BETWEEN waves off a fresh replay,
    never off this process's memory, because between waves this process has run
    nothing.
    """
    _force_s0(slots, cfg=cfg, batch_id=batch["id"], bdir=bdir,
              ledger_path=ledger_path, stages=stages)
    abort: dict | None = None
    children: list[dict] = []
    waves = [slots[i:i + orch["wave_size"]] for i in range(0, len(slots), orch["wave_size"])]
    for wave in waves:
        if abort is not None:
            break
        children += _run_wave(wave, config_path=config_path, bdir=bdir,
                              workers=orch["workers"])
        _refresh_from_ledger(slots, cfg=cfg, batch=batch, ledger_path=ledger_path)
        dead = sum(1 for slot in slots if slot.state == "dead")
        pulled = sum(1 for slot in slots if slot.state == "pulled")
        checked = _attrition(dead=dead, pulled=pulled, slots=len(slots),
                             max_attrition=orch["max_attrition"])
        if checked["over"]:
            # `tipped_by` names ONE slot because the sequential path does and the
            # report's readers read it that way. In a wave the deaths are
            # concurrent and no slot tipped it alone, so the name is this wave's
            # last death in slot order — the wave is what actually tipped it.
            tipped = [slot.slug for slot in wave if slot.state == "dead"] or [wave[-1].slug]
            abort = {
                "aborted": True, "at": _now(), "tipped_by": tipped[-1],
                **{key: value for key, value in checked.items() if key != "over"},
            }
            break
    _merge_sidecars(slots, bdir)
    return abort, children


def run_batch(cfg: Mapping, *, runners: Mapping[str, Callable] | None = None,
              review: tuple[str, str] | None = None,
              config_path: str | Path | None = None) -> dict:
    """Drive the batch as far as §4 allows and write `batch-report.json`.

    Resume is implicit: the ledger replays, `input_hashes` decides what is
    stale, and the run picks every non-terminal slot up at its own state — a
    completed stage with unchanged inputs is never invoked again.

    `config_path` is the file this cfg was loaded from, and it exists for one
    reason (contract P-5): a spawned child is handed a PATH, never an in-memory
    dict. It is needed only when `orchestrator.parallel_slots` is armed with the
    default spawn seam, and `main` always supplies it.
    """
    started = _now()
    batch = batch_config(cfg)
    orch = orchestrator_config(cfg)
    # Both caps, read ONCE per run and before a single stage is invoked
    # (contract D-3 §1): a malformed cap is a config error, and a config error
    # must never be discovered by a slot that has already spent. They are
    # recorded in the report too — the cap in force, not the cap believed.
    caps = {"respec_cap": _respec_cap(cfg), "verifier_reject_cap": _reject_cap(cfg),
            # Contract P-3: the same rule — the cap in force, not the cap
            # believed. `None` is the unlimited rounds every batch b001..b004
            # ran, and it is recorded as `None` rather than omitted so a report
            # says out loud that no round bound was armed.
            "verifier_round_cap": _round_cap(cfg),
            # Contract P-A.1, recorded on the same terms: 0 is OFF and is what
            # every batch b001..b005 ran.
            "verifier_reconcile_early": _reconcile_early(cfg)}
    # Read here too, and before any slot runs: a malformed `review.auto_accept`
    # must not be discovered by the first slot to reach `played`, five stages in.
    auto_accept = _auto_accept(cfg)
    bdir = batch_dir(cfg)
    bdir.mkdir(parents=True, exist_ok=True)
    ledger_path = bdir / LEDGER_NAME
    report_path = bdir / BATCH_REPORT_NAME

    stages = default_runners() if runners is None else dict(runners)
    unknown = sorted(set(stages) - set(STAGES))
    if unknown:
        raise KeyError(f"unknown stage runner(s) {unknown}; stages are {list(STAGES)}")

    slots = _slots(cfg, batch, replay_ledger(ledger_path))

    # Resume, part 1: heal the corpus before a stage can trip over it. A kill
    # stranded by a crash between its ledger line and its archiving would make
    # two dirs claim one idea (`_discover_spec_dir`). A review run is the human
    # decision, not a fresh run of the machine, so it sweeps nothing.
    if review is None:
        for moved in sweep_killed_specs(CORPUS_ROOT / batch["id"]):
            print(f"[b11] swept killed spec dir -> {moved}")

    review_applied = None
    if review is not None:
        review_applied = _apply_review(ledger_path, slots, review, cfg, batch["id"], bdir)

    abort: dict | None = None
    # CONTRACT P-5. The fan-out is ARMED, never inferred: `orchestrator.workers`
    # has sat in every config since b001 and been read by nothing, so a number
    # alone must not flip an old batch to parallel on resume. Unarmed — which is
    # every config on disk — the loop below is byte for byte the one every batch
    # b001..b005r2 ran, and `children` stays empty, which is what keeps the
    # `complete` expression and the report identical.
    parallel = _parallel_slots(cfg) and orch["workers"] > 1
    children: list[dict] = []
    if parallel:
        abort, children = _run_parallel(
            slots, cfg=cfg, batch=batch, orch=orch, bdir=bdir,
            ledger_path=ledger_path, stages=stages, config_path=config_path)
    else:
        waves = [slots[i:i + orch["wave_size"]]
                 for i in range(0, len(slots), orch["wave_size"])]
        for wave in waves:
            if abort is not None:
                break
            for slot in wave:
                # Resume, part 2: a stage whose inputs changed is re-run even
                # though its transition is already in the ledger (§2 ⊕ / §4).
                blocked = _restage(slot, cfg=cfg, batch_id=batch["id"], bdir=bdir,
                                   stages=stages)
                if blocked is None:
                    _work_slot(slot, cfg=cfg, batch_id=batch["id"], bdir=bdir,
                               ledger_path=ledger_path, stages=stages)
                dead = sum(1 for s in slots if s.state == "dead")
                pulled = sum(1 for s in slots if s.state == "pulled")
                checked = _attrition(dead=dead, pulled=pulled, slots=len(slots),
                                     max_attrition=orch["max_attrition"])
                if checked["over"]:
                    abort = {
                        "aborted": True, "at": _now(), "tipped_by": slot.slug,
                        **{key: value for key, value in checked.items() if key != "over"},
                    }
                    break

    slot_rows = [_slot_report(slot, cfg, batch["id"], bdir) for slot in slots]
    pending = [row["slug"] for row in slot_rows if row["review_pending"]]
    blocked = [row["slug"] for row in slot_rows if row["blocked"]]
    # Contract P-3's two report blocks. Both are ledger-derived (see
    # `_slot_report`), so a resumed batch reports what happened and not what
    # this process happened to do.
    auto_accepted = [row["slug"] for row in slot_rows if row["auto_accepted"]]
    reconciled = [row["slug"] for row in slot_rows if row["reconciled"]]
    # Contract P-A.4: slugs AND reasons, because a park is not a status — it is
    # a residual somebody has to read. Contract P-A.3's promotions ride beside
    # it for the same reason the reconciliations do: the spec moved under the
    # game, and the report is where a human finds that out.
    parked = [{"slug": row["slug"], "reason": reason}
              for row in slot_rows for reason in row["parked"]]
    tier_promoted = [{"slug": row["slug"], "reason": reason}
                     for row in slot_rows for reason in row["tier_promoted"]]
    # Contract E-2 §1, on the same terms and ADDITIVE (see `_slot_report`): the
    # refusals this batch made, or no key at all.
    churn_refused = [{"slug": row["slug"], "reason": reason}
                     for row in slot_rows for reason in row.get("churn_refused", ())]
    states: dict[str, int] = {}
    for row in slot_rows:
        states[str(row["state"])] = states.get(str(row["state"]), 0) + 1
    dead = sum(1 for slot in slots if slot.state == "dead")
    pulled = sum(1 for slot in slots if slot.state == "pulled")
    # Contract P-5: a child that exited nonzero is a slot that did not finish,
    # even in the corner where its ledger state happens to look terminal (a
    # crash after the last append). `children` is empty on the sequential path,
    # so this conjunct is `and True` there and the expression is unchanged.
    child_failures = [row for row in children if row["exit_code"] != 0]
    complete = all(slot.terminal for slot in slots) and abort is None and not child_failures
    attrition = _attrition(dead=dead, pulled=pulled, slots=len(slots),
                           max_attrition=orch["max_attrition"])

    stop_reason = None
    if abort is not None:
        stop_reason = "attrition"
    elif pending:
        stop_reason = "review"
    elif blocked:
        stop_reason = "blocked"
    elif not complete:
        stop_reason = "incomplete"
    # §4 semantics, not a status rename (contract D-3 §5): a batch whose every
    # slot is terminal with nothing dead has nothing left to run and nothing
    # failed — it stops COMPLETE at exit 0, and it says WHY it stopped, so the
    # human pull that ended b003r2 reads as the review working rather than as
    # the batch being killed. `stop_reason` stays reserved for the four ways a
    # run stops with work outstanding.
    #
    # A PARKED slot does not stop the batch (contract P-A.4) and does not make
    # it incomplete — `parked` is terminal — but it is not silence either, so
    # the note counts them beside the review verdict rather than reporting a
    # clean "review complete" over a residual nobody answered.
    closing_note = REVIEW_COMPLETE_NOTE if complete and dead == 0 else None
    if closing_note is not None and parked:
        closing_note = f"{REVIEW_COMPLETE_NOTE}; {len(parked)} parked"

    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": "orchestrator",
        "batch_id": batch["id"],
        "status": "complete" if complete else "stopped",
        "stop_reason": stop_reason,
        "closing_note": closing_note,
        "exit_code": 0 if complete else 2,
        "slots": slot_rows,
        "states": dict(sorted(states.items())),
        "cost": _cost_table(slots),
        "cost_note": _cost_note(cfg),
        "attrition": {
            "dead": attrition["dead"], "pulled": attrition["pulled"],
            "slots": attrition["slots"], "fraction": attrition["fraction"],
            "max_attrition": attrition["max_attrition"],
            "abort": abort,
        },
        # Contract P-3.3, top level because it is a fact about the BATCH: which
        # slugs the machine accepted at `played` instead of a human. Paired with
        # `reconciled` — the slots whose spec DECLARATIONS the round cap amended
        # (P-3.2a) — because an auto-accepted slot that was also reconciled is
        # exactly the one a post-package review must look at hardest.
        "auto_accepted": auto_accepted,
        "reconciled": reconciled,
        # Contract P-A.4, top level for the same reason: which slots stopped
        # with a residual, and WHAT the residual was. Never empty-and-absent —
        # an empty list is the batch saying out loud that nothing parked.
        "parked": parked,
        # Contract P-A.3: which slots outgrew the tier they were drawn at. The
        # idea file still says the ORIGINAL tier (ideas are immutable); this
        # block and the ledger line are the record of the promotion.
        "tier_promoted": tier_promoted,
        "review": {
            "pending": pending,
            "applied": review_applied,
            "auto_accept": auto_accept,
            "auto_accepted": auto_accepted,
            "command": "--review <slug>:accept|pull",
            "note": (
                "architecture §4: played --> reviewed is a HUMAN accept and there is no auto "
                "path — unless review.auto_accept is armed (contract P-3.3, operator ruling, "
                "2026-09-29: the pipeline must run without human feedback; oversight is "
                "post-package)"
            ),
        },
        "blocked": blocked,
        "config": {"batch": batch, "orchestrator": orch, "caps": caps},
        "timestamps": {"started": started, "finished": _now()},
        "paths": {"batch_dir": str(bdir), "ledger": str(ledger_path), "report": str(report_path)},
    }
    if churn_refused:
        # ADDITIVE and ONLY-WHEN-IT-HAPPENED (contract E-2 §1), for the reason
        # `parallel` below is additive: a batch that churned nothing reports
        # exactly what it reported before this contract.
        report["churn_refused"] = churn_refused
    if parallel:
        # ADDITIVE and ARMED-ONLY (contract P-5 §5): the sequential report gains
        # no key, byte-level. `workers` is the number actually usable — the
        # configured one clamped by the wave and by the batch — not the number
        # asked for, and every child's exit code is here because a nonzero one
        # names a slot to resume, never a batch to redo.
        report["parallel"] = {
            "workers": min(orch["workers"], orch["wave_size"], len(slots)),
            "children": children,
        }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


# --- CLI --------------------------------------------------------------------


def _status_lines(cfg: Mapping) -> list[str]:
    """The replayed table — reads the ledger, runs nothing.

    It also reads `orchestrator.max_attrition` (contract D-3 §5): the verdict
    lines below apply the SAME §4 kill criterion the run applies, off the same
    `_attrition` helper, so "did this batch abort?" is answerable from the
    ledger alone — read-only, without spending a cent re-deriving it.

    `respec` is the ledger-derived count (`respec_runs_from_ledger`), the same
    number the batch report now carries.
    """
    batch = batch_config(cfg)
    orch = orchestrator_config(cfg)
    bdir = batch_dir(cfg)
    ledger_path = bdir / LEDGER_NAME
    table = replay_ledger(ledger_path)
    seen = "" if ledger_path.is_file() else " (none yet)"
    header = (f"[b11] {'slug':<22} {'state':<12} {'lines':>5}  "
              f"{'lint/resamp/verif/crash/dead':<28} {'respec':>6} {'usd':>9} "
              f"{'tokens in/out':>16}  last")
    lines = [
        f"[b11] batch {batch['id']} | size {batch['size']} | ledger {ledger_path}{seen}",
        header,
    ]
    terminal = 0
    for index in range(1, batch["size"] + 1):
        slug = slot_id(batch["id"], index)
        entry = table.get(slug)
        if entry is None:
            lines.append(f"[b11] {slug:<22} {'(unborn)':<12} {0:>5}")
            continue
        terminal += 1 if entry["terminal"] else 0
        rejects = entry["rejects"]
        counts = (f"{rejects['lint_kill']}/{rejects['resample']}/{rejects['verifier']}"
                  f"/{rejects['battery_crash']}/{rejects['green_death']}")
        cost = entry["cost"]
        usd = "unreported" if cost["usd"] is None else f"{cost['usd']:.4f}"
        tokens = f"{cost['tokens_in']}/{cost['tokens_out']}"
        lines.append(
            f"[b11] {slug:<22} {entry['state']!s:<12} {len(entry['history']):>5}  "
            f"{counts:<28} {respec_runs_from_ledger(entry['history']):>6} {usd:>9} "
            f"{tokens:>16}  {entry['last_ts']}"
        )
    states: dict[str, int] = {}
    for entry in table.values():
        key = str(entry["state"])
        states[key] = states.get(key, 0) + 1
    lines.append(f"[b11] states: {dict(sorted(states.items())) or '(empty ledger)'}")
    attrition = _attrition(
        dead=sum(1 for entry in table.values() if entry["state"] == "dead"),
        pulled=sum(1 for entry in table.values() if entry["state"] == "pulled"),
        slots=batch["size"], max_attrition=orch["max_attrition"],
    )
    lines.append(
        f"[b11] attrition: {attrition['dead']}/{attrition['slots']} dead = "
        f"{attrition['fraction']:.2f} (max_attrition {attrition['max_attrition']}) | "
        f"{attrition['pulled']} pulled at review (a human verdict, not attrition)"
    )
    # Contract P-A.4: the replayed table says so too, and only when there is
    # something to say — every pre-P-A ledger prints byte-for-byte as it did.
    parked_slugs = sorted(slug for slug, entry in table.items() if entry["state"] == "parked")
    if parked_slugs:
        # Contract E-2 §2/§3: a park is no longer only the verify lane's. It now
        # also arrives from a downstream stage that failed past its cap and from
        # a re-spec no spec amendment could answer, so the note names the class
        # rather than one cause. The REASONS are per-slot and live in the ledger
        # line and the batch report; `--status` is a table.
        lines.append(
            f"[b11] parked: {len(parked_slugs)}/{batch['size']} ({', '.join(parked_slugs)}) — "
            "a residual the machine could not answer; NOT attrition, nothing deleted"
        )
    if attrition["over"]:
        lines.append(f"[b11] BATCH ABORTED: {attrition['reason']}")
    elif terminal == batch["size"] and attrition["dead"] == 0:
        lines.append(
            f"[b11] COMPLETE ({REVIEW_COMPLETE_NOTE}) — {terminal}/{batch['size']} slot(s) "
            "terminal, 0 dead"
        )
    lines.append(f"[b11] cost note: {_cost_note(cfg)}")
    return lines


def _cost_note(cfg: Mapping) -> str:
    """COST_NOTE, extended when an unpriced driver is configured (P-1a item 6).

    codex reports no dollar figures, so a codex batch's usd totals are
    structurally missing — the note must say so instead of letting a zero
    read as free. `gen.backends` is imported HERE, not at module import
    (the s2 runner's own pattern): a report assembled from a ledger replay
    should not require the driver stack to exist.
    """
    from .backends import unpriced_driver_note

    extra = unpriced_driver_note(cfg)
    return f"{COST_NOTE}; {extra}" if extra else COST_NOTE


def _visual_report(spec_dir: str | None) -> Path | None:
    """The slot's `visual-report.md`, when a card was actually built for it.

    Contract V-C: the human review at `played` is the designated judge of
    legibility, and the card is the first evidence it has ever been handed — so
    the stop message names it. `None` whenever there is nothing to name (no
    spec dir yet, the card knob off, a card that failed to build): the review
    message must never print a path to a file that is not there.
    """
    if spec_dir is None:
        return None
    from .s3_visual import card_paths
    path = card_paths(spec_dir)["md"]
    return path if path.is_file() else None


def _declared_violations(spec_dir: str | None) -> list[str]:
    """R-06's violation rows for ONE slot, as the card wrote them.

    Contract W1-A2: `declared-vs-painted` was already firing on all seven
    shipped games and was "a gate that fires and is not acted on" — so the row
    it found is NAMED at the stop, beside the card's path, where the human who
    has to judge the game will read it.

    Nothing here may raise. This runs after the batch report is written, in the
    same print loop as `_visual_report`, and a finished run must not die because
    a card is missing, half-written, or built by a config that never armed the
    check. An unreadable card yields no rows, exactly like an unarmed one.
    """
    if spec_dir is None:
        return []
    try:
        from .s3_visual import (
            DECLARED_VS_PAINTED_CHECK,
            card_paths,
            declared_violation_lines,
        )
        path = card_paths(spec_dir)["json"]
        if not path.is_file():
            return []
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, Mapping):
            return []
        return declared_violation_lines(report.get(DECLARED_VS_PAINTED_CHECK))
    except Exception:  # noqa: BLE001 — the stop prints what it can read, never dies on it
        return []


def _deception_advisories(worker_dir: str | None) -> list[str]:
    """Contract L-1's recorded deception findings for ONE slot, as details.

    `verifier.deception_action: record` moves an undeclared-deception finding
    out of `reject_reasons` and into the report's `deception_advisories`, where
    it decides nothing. The ruling traded a reject for a RECORD, so the record
    is printed at the stop — beside the declared-vs-painted rows, for the reason
    W1-A2 gives for those: a finding that only ever reached a json file is the
    defect this print exists to close.

    Nothing here may raise, and nothing here re-decides anything. It runs after
    the batch report is written, in the same print loop as
    `_declared_violations`, and an absent, half-written or pre-L-1 report (no
    such key) yields no rows — exactly like a batch that never armed the knob.
    """
    if worker_dir is None:
        return []
    try:
        from .s3_verify import ADVISORIES_KEY
        worker = Path(worker_dir)
        path = worker.with_name(worker.name + VERIFIER_REPORT_SUFFIX)
        if not path.is_file():
            return []
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, Mapping):
            return []
        rows = report.get(ADVISORIES_KEY)
        if not isinstance(rows, list):
            return []
        return [str(row["detail"]) for row in rows
                if isinstance(row, Mapping) and isinstance(row.get("detail"), str)]
    except Exception:  # noqa: BLE001 — the stop prints what it can read, never dies on it
        return []


def _term_disputes(worker_dir: str | None) -> list[str]:
    """Contract Q-1's attribution disputes for ONE slot, as lines.

    `term_disputes` records the pairs in BOTH knob modes — an audit that gave one
    observed behaviour two signed vocabulary names — and under
    `verifier.term_dispute_action: record` those findings no longer reject. Both
    readings are things a human needs off the log rather than out of a json file,
    which is the defect the L-1 print above exists to close and this one closes
    for the term half.

    Nothing here may raise and nothing here re-decides anything, exactly as
    `_deception_advisories` promises: an absent, half-written or pre-Q-1 report
    (no such key) yields no rows.
    """
    if worker_dir is None:
        return []
    try:
        from .s3_verify import TERM_DISPUTES_KEY
        worker = Path(worker_dir)
        path = worker.with_name(worker.name + VERIFIER_REPORT_SUFFIX)
        if not path.is_file():
            return []
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, Mapping):
            return []
        rows = report.get(TERM_DISPUTES_KEY)
        if not isinstance(rows, list):
            return []
        return [
            f"{row['code']}: {row['term']} vs the declared {row['disputed_with']} "
            f"— {row['shared']}"
            for row in rows
            if isinstance(row, Mapping)
            and all(isinstance(row.get(key), str)
                    for key in ("code", "term", "disputed_with", "shared"))
        ]
    except Exception:  # noqa: BLE001 — the stop prints what it can read, never dies on it
        return []


def _play_recipe(cfg: Mapping) -> str:
    """S6's `arc-games play --root …` one-liner for the review stop (D-2).

    ONE line per STOP, not per slot: the recipe names the play ROOT, which is the
    batch's and not the slot's, and the menu it opens lists every pending
    game — printing it once per pending slug would repeat the same string.

    `play_command` is S6's, so the reviewer's command is the packager's. It used
    to be a `PLAY_GAMES_DIR=…` line built from the config's resolved
    `duckwm_docs`; contract H-1 item 4 made it the command this repo actually
    ships. It is PRINTED, never run. A recipe that cannot be built comes back
    as a short note rather than an exception: this runs after the batch report
    is written, and a finished run must not die on a print — but it must not
    print a command it did not build either.
    """
    try:
        from .s6_package import PLAY_ROOT, play_command
        return play_command(cfg, PLAY_ROOT)["command"]
    except Exception as exc:  # noqa: BLE001 — the stop prints what it can derive, honestly
        return f"(no play recipe: {type(exc).__name__}: {exc})"


def _print_slot_row(row: Mapping) -> None:
    """One slot's console line, plus its stale re-runs and its block.

    The same three constructs for the batch's rows and for a `--slot` child's
    single row — one shape, printed in one place, so the two consoles cannot
    drift into two dialects of the same fact.
    """
    print(
        f"[b11] {row['slug']} | {row['state']} | {row['transitions']} transition(s) | "
        f"rejects {row['rejects']} | invocations {row['invocations']}"
    )
    for entry in row["stale"] or ():
        what = "re-ran" if entry["rerun"] else "NOT re-run"
        print(f"[b11]   {entry['stage']}: inputs changed since the ledger — {what}")
    if row["blocked"] is not None:
        print(f"[b11]   BLOCKED at {row['blocked']['stage']}: {row['blocked']['reason']}")
        print(f"[b11]   {row['blocked']['note']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="B11 orchestrator — the architecture §4 state machine, ledger and resume"
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--status", action="store_true",
                        help="print the replayed ledger table and exit")
    parser.add_argument("--review", default=None, metavar="SLUG:accept|pull",
                        help="the HUMAN decision at `played` (architecture §4)")
    parser.add_argument("--slot", default=None, metavar="SLUG",
                        help="CHILD MODE (contract P-5): run EXACTLY this slot, write "
                             "its sidecar report and exit; writes no batch report")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:   # argparse exits 2 on usage; this CLI exits 1
        return 0 if exc.code == 0 else 1

    if args.slot is not None and (args.status or args.review is not None):
        # `--status` replays the whole batch and `--review` is a decision about
        # it; `--slot` is one slot's worker. Combining them would ask a child to
        # speak for the batch, which is the one thing a child must never do.
        print("[b11] ERROR --slot is the parallel CHILD mode: it runs one slot and "
              "writes no batch report. --status and --review are batch-level and "
              "cannot be combined with it", file=sys.stderr)
        return 1

    review: tuple[str, str] | None = None
    if args.review is not None:
        slug, sep, decision = args.review.partition(":")
        if not sep or decision not in REVIEW_DECISIONS or not slug:
            print(f"[b11] ERROR --review wants '<slug>:accept' or '<slug>:pull', "
                  f"got {args.review!r}", file=sys.stderr)
            return 1
        review = (slug, decision)

    try:
        cfg = load_config(args.config)
        if args.status:
            for line in _status_lines(cfg):
                print(line)
            return 0
        if args.slot is not None:
            slot_report = run_slot(cfg, args.slot)
            _print_slot_row(slot_report["slot"])
            print(f"[b11] slot report: {slot_report['paths']['slot_report']}")
            print(f"[b11] SLOT {slot_report['status'].upper()} ({slot_report['outcome']})")
            return slot_report["exit_code"]
        report = run_batch(cfg, review=review, config_path=args.config)
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        # The message alone buried the crash site on the first live b004
        # IndexError (2026-09-28): a bare "tuple index out of range" names no
        # stage, no slot and no line. The operator re-runs blind. Print the
        # full chain; the one-line summary stays for grep.
        traceback.print_exc(file=sys.stderr)
        print(f"[b11] ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    for row in report["slots"]:
        _print_slot_row(row)
    total = report["cost"]["total"]
    usd = "unreported" if total["usd"] is None else f"${total['usd']:.4f}"
    print(f"[b11] cost {usd} | tokens {total['tokens_in']}/{total['tokens_out']} "
          f"| {total['reported']} priced transition(s)")
    off = report["cost"]["off_ledger"]
    if off["runs"]:
        off_usd = "unreported" if off["usd"] is None else f"${off['usd']:.4f}"
        print(f"[b11] off-ledger {off['runs']} run(s) (no §4 edge to record them): {off_usd} "
              f"| tokens {off['tokens_in']}/{off['tokens_out']}")
    for stage, row in report["cost"]["by_stage"].items():
        if row["transitions"]:
            stage_usd = "unreported" if row["usd"] is None else f"${row['usd']:.4f}"
            print(f"[b11]   {stage:<14} {row['transitions']:>2} transition(s) | {stage_usd} | "
                  f"tokens {row['tokens_in']}/{row['tokens_out']}")
    # The label on every figure above (contract D-3 §6) — the same constant the
    # report and `--status` carry, printed where the totals are read.
    print(f"[b11] cost note: {report['cost_note']}")
    attrition = report["attrition"]
    if attrition["dead"] or attrition["pulled"]:
        print(f"[b11] attrition: {attrition['dead']}/{attrition['slots']} dead = "
              f"{attrition['fraction']:.2f} (max_attrition {attrition['max_attrition']}) | "
              f"{attrition['pulled']} pulled at review (a human verdict, not attrition)")
    command = f".venv/bin/python -m gen.orchestrator --config {args.config}"
    spec_dirs = {row["slug"]: row["paths"]["spec_dir"] for row in report["slots"]}
    pending = report["review"]["pending"]
    for slug in pending:
        print(f"[b11] REVIEW REQUIRED {slug} @ played — architecture §4 has no auto path out")
        print(f"[b11]   accept: {command} --review {slug}:accept")
        print(f"[b11]   pull:   {command} --review {slug}:pull")
        # The legibility evidence the review is the judge of (contract V-C).
        # Named only when it is really there: the card is knob-gated, so on a
        # batch that did not ask for one there is nothing to point at.
        card = _visual_report(spec_dirs.get(slug))
        if card is not None:
            print(f"[b11]   visual: {card}")
        # Contract W1-A2 R-06: the rows the card found, ONE line per game — the
        # `visual:` line's own shape. Printed whether the knob is `record` or
        # `fail`, because at `played` the reviewer is the judge either way, and
        # a finding that only ever reached a json file is the defect this
        # contract was written to close.
        violations = _declared_violations(spec_dirs.get(slug))
        if violations:
            print(f"[b11]   declared-vs-painted: {'; '.join(violations)}")
    # Contract L-1: every slot whose verifier RECORDED a deception finding
    # instead of rejecting on it, one line per slot — the `declared-vs-painted:`
    # line's own shape. Over every slot rather than the pending ones, and
    # deliberately: under `review.auto_accept` there is no review stop to carry
    # them, and a parked slot's advisory is the thing a human reading the log
    # most needs to see.
    for row in report["slots"]:
        advisories = _deception_advisories(row["paths"]["worker"])
        if advisories:
            print(f"[b11] {row['slug']} deception advisories (recorded, not rejecting): "
                  f"{'; '.join(advisories)}")
        # Contract Q-1, in the same loop and over every slot for the same reason
        # the L-1 line gives: a PARKED slot's dispute is the thing a human
        # reading the log most needs to see, and under `review.auto_accept` there
        # is no review stop to carry it. ONE LINE PER DISPUTE, not per slot — a
        # pair names two terms and what grounded them, which does not read when
        # several are joined onto one line.
        for line in _term_disputes(row["paths"]["worker"]):
            print(f"[b11] {row['slug']} term dispute — {line}")
    # Contract P-3: what the machine decided for itself, printed where a human
    # reading the run log will see it beside the review block it replaced. A
    # reconciled slot is named too — its spec's DECLARATIONS moved under it, and
    # the post-package review is the first human to see that.
    for slug in report["auto_accepted"]:
        print(f"[b11] AUTO-ACCEPTED {slug} @ played — {AUTO_ACCEPT_REASON}; "
              "oversight is post-package (operator ruling, 2026-09-29)")
    for row in report["slots"]:
        for line in row["reconciled"]:
            print(f"[b11] RECONCILED {row['slug']}: {line}")
    # Contract E-2 §1, printed in the same loop and for the same reason: a
    # refused amendment is a thing the machine decided on its own, and it is
    # invisible in a state name. Only when there was one.
    for entry in report.get("churn_refused", ()):
        print(f"[b11] CHURN REFUSED {entry['slug']}: {entry['reason']}")
    # Contract P-A.3 / P-A.4, printed in the same place and for the same reason:
    # a promoted tier and a parked residual are both things the machine decided
    # on its own, and both are invisible in a state name.
    for entry in report["tier_promoted"]:
        print(f"[b11] TIER PROMOTED {entry['slug']}: {entry['reason']}")
    for entry in report["parked"]:
        print(f"[b11] PARKED {entry['slug']}: {entry['reason']}")
        print("[b11]   nothing was deleted — the slot's artifacts stand; parked slots are "
              "outside the attrition ratio and never abort a batch (operator ruling, "
              "2026-09-29: "
              '"We should never kill. Even if it is not satisfied eventually let\'s not kill.")')
        # CONTRACT E-5: …and now the exit has a name. A console line only — no
        # ledger line, no report key, nothing automatic: the advisory that says
        # "the artifacts stand" was, until this contract, the end of the road,
        # and a human reading it had no way to learn a lift exists.
        print(f"[b11]   it can be lifted by hand: arc-games unpark {report['batch_id']} "
              f"{entry['slug']} --reason '<why>', then resume")
    if pending:
        # Contract D-2: the reviewer's playable build. Every pending slot was
        # mirrored into the play root at its own `baselined --> played` edge and
        # shows there as "… (review pending)", so the stop hands over the recipe
        # that opens it — once, because the root is shared.
        print(f"[b11]   play (every pending game, '(review pending)' in the menu): "
              f"{_play_recipe(cfg)}")
    # Contract P-5, printed only on a run that actually spawned: how many
    # children ran, and every one that did not exit 0 — named, because a
    # nonzero child is a slot to resume and never a batch to redo.
    fanout = report.get("parallel")
    if fanout is not None:
        failures = [row for row in fanout["children"] if row["exit_code"] != 0]
        print(f"[b11] parallel: {len(fanout['children'])} child run(s) at "
              f"{fanout['workers']} worker(s); {len(failures)} did not exit 0")
        for row in failures:
            print(f"[b11]   {row['slug']} exited {row['exit_code']}"
                  + (f" ({row['error']})" if row["error"] else "")
                  + " — its ledger state stands; a resume re-runs exactly it")
    abort = report["attrition"]["abort"]
    if abort is not None:
        print(f"[b11] BATCH ABORTED: {abort['reason']}")
    print(f"[b11] ledger: {report['paths']['ledger']}")
    print(f"[b11] report: {report['paths']['report']}")
    # `closing_note` only ever names a batch that stopped because there was
    # nothing left to run and nothing had failed (contract D-3 §5).
    stop = report["stop_reason"] or report["closing_note"]
    print(f"[b11] {report['status'].upper()}" + (f" ({stop})" if stop else ""))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
