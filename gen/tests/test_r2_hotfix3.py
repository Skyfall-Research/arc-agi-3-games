"""R2 hotfix #3 acceptance: a resume parked at `respec` treats a recorded
stage whose current input files do not exist yet as upstream-PENDING, not
stale — no hash compare, no off-ledger re-run, no crash.

Run: .venv/bin/python -m pytest gen/tests/test_r2_hotfix3.py -v

The incident this pins (R2, 2026-09-22): the pilot blocked at `respec` with 2
lint kills; the cap was raised to 3 in config; the resume then crashed with
`FileNotFoundError: idea not found: .../respec-2/idea-001.json` — `_restage`
built S1's context at the slot's CURRENT respec count (2), whose idea only the
UPCOMING re-sample would draw, saw `_sha256_file -> None != recorded`, and
re-ran the real S1 runner against a nonexistent idea. With fake runners the
same defect is a silent spurious re-run (a paid session in production), so
the discriminating assertions here are the invocation counts — pre-fix, run 2
invokes S1 twice and charges one off-ledger run. The pending row itself is a
start-of-run transient (`_restage` rebuilds the stale list every wave pass),
so the final report is only asserted to carry no rerun-True S1 row.

Resume-from-`respec` is reachable ONLY since `orchestrator.respec_cap` became
configurable: at the fixed cap of 2, `respec` was always a blocked dead-end,
which is why B11's kill/resume matrix never held this state.

Harness: imported from test_b11_pipeline (the test_r2_hotfix2.py precedent),
never copied; its no-network and no-repo-writes guards are adopted.
"""

from __future__ import annotations

import re

from gen.tests import test_b11_pipeline as b11

_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched
batch_home = b11.batch_home
make_cfg = b11.make_cfg

LINT_KILL_REASON = "lint kill: unknown term"
KILL_EDGE = ("ideated", "respec")
RESAMPLE_EDGE = ("respec", "ideated")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _edge_lines(cfg, edge):
    return [line for line in b11._ledger_lines(cfg) if (line["from"], line["to"]) == edge]


def _only_slot(report):
    slots = report["slots"]
    assert len(slots) == 1, f"one-slot batch expected; the report has {len(slots)}"
    return slots[0]


def test_a_resume_parked_at_respec_skips_the_pending_stage_and_completes(make_cfg):
    """Run 1 blocks at the default cap; the cap is raised to 3 between runs
    (the R2 incident, verbatim); run 2 must resume THROUGH `respec`."""
    cfg, _path = make_cfg("r2h3-resume-at-respec")
    cfg["orchestrator"].pop("respec_cap", None)

    # Run 1: two lint kills at the default cap -> blocked, parked at `respec`.
    journal = b11._Journal()
    runners = b11._Runners(
        journal, cfg,
        outcomes={"ideated": b11._Outcome("respec", LINT_KILL_REASON, times=2)},
    )
    first = b11._advance(cfg, runners)
    assert first["stop_reason"] == "blocked", first["stop_reason"]
    assert b11._table(cfg)[_only_slot(first)["slug"]] == "respec", b11._table(cfg)
    assert len(_edge_lines(cfg, KILL_EDGE)) == 2, b11._spine(b11._ledger_lines(cfg))

    # The adjudication: the cap is raised in config between the two runs.
    cfg["orchestrator"]["respec_cap"] = 3

    # Run 2: nothing scripted to fail. Pre-fix this either crashed on the
    # missing respec-2 idea (real runner) or silently re-ran S1 off-ledger
    # against it (fake runner); post-fix the pending stage is skipped and the
    # machine runs on-ledger only. `_advance` answers the `played` stop with
    # an accept and returns the LAST leg's report, so per-leg process fields
    # (invocations, off_ledger) are asserted on the JOURNAL, which records
    # every fake-stage call across all legs.
    journal2 = b11._Journal()
    second = b11._advance(cfg, b11._Runners(journal2, cfg))
    row = _only_slot(second)

    assert row["blocked"] is None, f"the raised cap must unblock the slot: {row['blocked']}"
    assert b11._table(cfg)[row["slug"]] == "packaged", (
        f"the resumed slot must finish the pipeline: {b11._table(cfg)}"
    )
    assert len(_edge_lines(cfg, KILL_EDGE)) == 2, b11._spine(b11._ledger_lines(cfg))
    assert len(_edge_lines(cfg, RESAMPLE_EDGE)) == 2, (
        "the resume must spend the freed strike on re-sample #2: "
        f"{b11._spine(b11._ledger_lines(cfg))}"
    )

    # `_restage` runs per wave pass and rebuilds the stale list each time, so
    # the start-of-run PENDING row for S1 is a transient — by the final
    # report, S1's recorded line is the fresh pass and compares equal. What
    # the final report must NOT carry is a rerun-True S1 row: that is the
    # spurious off-ledger re-run the defect caused.
    s1_rows = [entry for entry in (row["stale"] or []) if entry["stage"] == "s1_spec"]
    assert not any(entry["rerun"] for entry in s1_rows), (
        f"no pass may re-run S1 against an undrawn idea: {row['stale']!r}"
    )
    for entry in s1_rows:
        assert entry.get("pending") and entry["current"] is None, (
            f"an S1 row in this scenario can only be the pending form: {entry!r}"
        )
        assert isinstance(entry["recorded"], str) and SHA256_RE.match(entry["recorded"]), (
            f"the recorded hash stays on the row for the report: {entry!r}"
        )

    # The money assertion, and the one that fails pre-fix in the fake world:
    # across ALL of run 2's legs, S1 fired EXACTLY once (the scheduled,
    # on-ledger attempt after the re-sample). The defect bought a spurious
    # off-ledger S1 call first, making it two.
    assert journal2.count(to_state="spec_ok") == 1, (
        f"run 2 must invoke S1 exactly once; journal saw {journal2.states()}"
    )
    assert journal2.count(to_state="ideated") == 1, (
        f"run 2 re-samples exactly once; journal saw {journal2.states()}"
    )
