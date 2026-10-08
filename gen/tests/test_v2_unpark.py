"""BLIND lane for frozen contract E-5 — the operator unpark (pins U1-U5).

Run: .venv/bin/python -m pytest gen/tests/test_v2_unpark.py -q

WRITTEN FROM THE CONTRACT ALONE (docs/v2/contracts/E-5-operator-unpark.md,
section "Blind lane"). The implementer's suite is `gen/tests/test_e5_unpark.py`
and NOTHING here was written with it, or with their diff, in view: the only
inputs to this file are the frozen contract text and the COMMITTED tree at
HEAD a71e1ad (the state tables at `gen/orchestrator.py:209-231`,
`append_transition`, `replay_ledger`, `gen/cli.py`'s command seams and the b11
`_Runners` fake-runner rig). Nothing here may be read as covering the
implementer's pins, and nothing here pins an implementation choice the contract
leaves open.

WHAT THE CONTRACT PROMISES, and the pin that holds each promise:

  U1  a parked slot is lifted to its park-line `from` state — read MECHANICALLY
      off the ledger (the last line whose `to` == "parked"; its `from`), never
      caller-chosen — and a resume under fake runners re-runs the stage that
      parked it, to a complete batch. With it: the five lift edges (§1, EXACTLY
      the five states that have an edge INTO parked) and the contracted
      invocation shape `gen unpark BATCH_ID SLUG --reason TEXT` (§2), which
      U1-U4 all drive.
  U2  the refusal matrix — not-parked slot, unknown slug, empty/blank reason —
      each loud, each appending NOTHING.
  U3  one lift = one line: the appended transition is the only mutation, hashes
      present, cost absent, and the reason quotes BOTH texts.
  U4  park -> lift -> re-park -> lift is legal, and the batch report's `parked`
      block counts a slot by its CURRENT state only (§4, report honesty).
  U5  byte-identity: a pre-E-5 ledger (no lift lines) replays exactly as it does
      today — state, counters, cost and every report block. This one is GREEN
      before the feature exists and must stay green after it does; it is the
      regression half of the contract's house rule, "a tree nobody unparks
      behaves byte-identically to today".

HERMETIC. Every fixture is built in `tmp_path` from the park-line SHAPE the
contract quotes (`PARK_REASON` below is b005r2-auto-s001's own reason, verbatim
from the contract's LIVE EXHIBIT). The real `out/` is never read or written —
the orchestrator's repo-rooted paths are redirected by b11's `batch_home`, the
CLI's two roots are redirected beside them, and b11's `_repo_batches_untouched`
guard is aliased in so a leak fails the test that caused it. No network, no
driver, no agent session, no subprocess, no spend, and `../duckWM` is read
(read-only) by nothing but `load_config`'s canon check.

THE SURFACE IS DRIVEN THROUGH THE CLI ENTRY, not through an importable seam:
the contract guarantees the invocation shape and leaves the internals open, so
`cli.main(["unpark", ...])` — which IS what `python -m gen unpark` runs — is
what every pin below calls. It is called IN PROCESS rather than as a subprocess
for one reason: a subprocess would resolve the REAL `out/batches/`, which this
lane is forbidden to touch.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from gen import cli
from gen import orchestrator as orch

# The b11 rig, BORROWED and never modified (the `test_v2_ladder` precedent):
# `batch_home` redirects every repo-rooted path in the orchestrator at tmp,
# `make_cfg` writes a real config for a batch id nobody else uses, and
# `_Runners`/`_Journal`/`_advance` are the fake stage runners contract E-5's
# blind lane asks for by name.
from gen.tests import test_b11_pipeline as b11

_no_network_no_agent = b11._no_network_no_agent        # autouse: no urlopen, no driver
_repo_batches_untouched = b11._repo_batches_untouched  # autouse: the real out/ is sacred
batch_home = b11.batch_home
make_cfg = b11.make_cfg

# --- the park-line SHAPE the contract quotes --------------------------------
#
# b005r2-auto-s001 (two-keys-one-echo), parked 2026-09-29T15:50:31, verbatim
# from the contract's "LIVE EXHIBIT". The reason text matters to the pins twice:
# U3 requires the lift line to QUOTE it, and U4 requires the report to prefer
# the LATEST one when a slot is lifted and parks again.
PARK_REASON = (
    "round-cap park: undeclared-deception (verify round 5, verifier.round_cap 4; "
    "the audit rejected again AFTER the declarations were reconciled)"
)
PARK_TS = "2026-09-29T15:50:31+00:00"

#: the operator's own sentence — contract §2's `--reason TEXT`.
OPERATOR_REASON = "contract L-1 made undeclared-deception record-only; the worker validates green"

#: §1: "EXACTLY the five states that today have an edge INTO parked".
LIFT_STATES = ("spec_ok", "implemented", "verified", "gated", "reviewed")

#: the §4 walk that reaches each of those states, so a fixture ledger replays.
WALK: dict[str, tuple[tuple[str | None, str], ...]] = {
    "spec_ok": ((None, "ideated"), ("ideated", "spec_ok")),
    "implemented": ((None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented")),
    "verified": ((None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
                 ("implemented", "verified")),
    "gated": ((None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
              ("implemented", "verified"), ("verified", "gated")),
    "reviewed": ((None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
                 ("implemented", "verified"), ("verified", "gated"), ("gated", "baselined"),
                 ("baselined", "played"), ("played", "reviewed")),
}

#: stand-in content hashes. `_check_hashes` takes any hex string or None, and a
#: fixture that is not on disk has no real ones — what the pins care about is
#: that the LIFT line carries the three keys at all (U3).
FIXTURE_HASHES = {"spec": "a" * 64, "game": "b" * 64, "stage_input": "c" * 64}

LEDGER_KEYS = ("slug", "from", "to", "reason", "hashes", "cost", "ts")
HASH_KEYS = ("spec", "game", "stage_input")


# --------------------------------------------------------------------------- #
# helpers — the fixture ledger, built in tmp from the shape above
# --------------------------------------------------------------------------- #


def _row(slug: str, frm: str | None, to: str, reason: str, *, ts: str = PARK_TS,
         cost: dict | None = None) -> dict:
    """One ledger line in the frozen key order (`orchestrator._line`'s shape)."""
    return {"slug": slug, "from": frm, "to": to, "reason": reason,
            "hashes": dict(FIXTURE_HASHES), "cost": cost, "ts": ts}


def _park_rows(slug: str, park_from: str, *, reason: str = PARK_REASON) -> list[dict]:
    """A pre-E-5 ledger: the §4 walk to `park_from`, then the park."""
    rows = [_row(slug, frm, to, f"pre-E-5 walk {frm} -> {to}") for frm, to in WALK[park_from]]
    rows.append(_row(slug, park_from, "parked", reason))
    return rows


def _write_ledger(path: Path, rows) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = "".join(json.dumps(row) + "\n" for row in rows).encode("utf-8")
    path.write_bytes(blob)
    return blob


def _lines(path: Path) -> list[dict]:
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines()
            if raw.strip()]


def _spine(path: Path, slug: str | None = None) -> list[tuple[str | None, str]]:
    return [(line["from"], line["to"]) for line in _lines(path)
            if slug is None or line["slug"] == slug]


def _tree(root: Path) -> dict[str, bytes]:
    """Every file under `root`, by relative path — U3's "only mutation" check."""
    return {str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


# --------------------------------------------------------------------------- #
# helpers — the tool's surface (discovered, never assumed)
# --------------------------------------------------------------------------- #


def _subcommands() -> dict[str, argparse.ArgumentParser]:
    """The `arc-games` subcommands, off the parser the CLI builds."""
    found: dict[str, argparse.ArgumentParser] = {}
    for action in cli.build_parser()._actions:
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict) and choices and all(
            isinstance(value, argparse.ArgumentParser) for value in choices.values()
        ):
            found.update(choices)
    return found


def _unpark_subparser() -> argparse.ArgumentParser:
    """The `unpark` subcommand, or a loud failure naming what §2 promised.

    Every pin that drives the tool calls this FIRST, so an absent feature fails
    with the contract clause rather than with argparse's generic usage error
    mapped to exit 1 (which would be indistinguishable from a refusal).
    """
    subs = _subcommands()
    assert "unpark" in subs, (
        "contract E-5 §2 promises a CLI subcommand `gen unpark BATCH_ID SLUG --reason TEXT`, "
        "wired beside resume/status via `cli._config_for`. `gen.cli.build_parser()` offers "
        f"{sorted(subs)} — there is no unpark, so the park still has no exit."
    )
    return subs["unpark"]


def _unpark(batch_id: str, slug: str, *, reason: str | None, capsys,
            extra: tuple[str, ...] = ()) -> tuple[int, str]:
    """`gen unpark BATCH_ID SLUG --reason TEXT`, in process. -> (exit code, output)."""
    _unpark_subparser()
    argv = ["unpark", str(batch_id), str(slug), *extra]
    if reason is not None:
        argv += ["--reason", reason]
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out + captured.err


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _cli_roots(batch_home, monkeypatch, tmp_path) -> Path:
    """Redirect the CLI's own two roots beside the orchestrator's (hermetic).

    `batch_home` moves every repo-rooted Path in `gen.orchestrator` into tmp,
    which `cli._batches_root` already follows — this makes that explicit, and
    it also moves the hand-written config SCAN dir, so no pin here reads the
    repo's real `config/` or lists a stranger's batch ids in an error message.
    """
    monkeypatch.setattr(cli, "BATCHES_ROOT", Path(orch.BATCHES_ROOT))
    handwritten = tmp_path / "handwritten-config"
    handwritten.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "CONFIG_DIR", handwritten)
    return handwritten


@pytest.fixture
def parked_batch(make_cfg, _cli_roots):
    """A hermetic batch whose one slot sits where the contract's exhibit sat.

    `rows=` overrides the ledger (U2 needs a slot that never parked) and
    `handwritten=True` puts the config where a pre-P-4 batch kept it, which is
    the fallback `cli._config_for` exists to serve.
    """

    def _make(batch_id: str, park_from: str = "implemented", *,
              reason: str = PARK_REASON, rows=None, handwritten: bool = False):
        cfg, _written = make_cfg(batch_id)
        bdir = Path(orch.batch_dir(cfg))
        slug = orch.slot_id(batch_id, 1)
        ledger = bdir / orch.LEDGER_NAME
        _write_ledger(ledger, _park_rows(slug, park_from, reason=reason)
                      if rows is None else rows)
        text = yaml.safe_dump(cfg, sort_keys=False)
        if handwritten:
            (_cli_roots / f"{batch_id}.yaml").write_text(text, encoding="utf-8")
        else:
            (bdir / cli.BATCH_CONFIG_NAME).write_text(text, encoding="utf-8")
        return SimpleNamespace(cfg=cfg, batch_id=batch_id, slug=slug, bdir=bdir,
                               ledger=ledger, park_from=park_from, park_reason=reason)

    return _make


# --------------------------------------------------------------------------- #
# U1 — the lift, the five edges, and the resume that finishes the batch
# --------------------------------------------------------------------------- #


def test_u1_the_contracted_invocation_shape_exists():
    """§2: "a CLI subcommand `gen unpark BATCH_ID SLUG --reason TEXT`".

    The precondition every other pin drives: two positionals and a `--reason`
    option, on the same parser `resume` and `status` hang off.
    """
    sub = _unpark_subparser()
    options = {name for action in sub._actions for name in action.option_strings}
    assert "--reason" in options, (
        f"§2 spells the operator's note `--reason TEXT`; unpark takes {sorted(options)}"
    )
    positionals = [action.dest for action in sub._actions if not action.option_strings]
    assert len(positionals) == 2, (
        "§2 spells the tool `gen unpark BATCH_ID SLUG --reason TEXT` — two positionals; "
        f"unpark declares {positionals}"
    )
    assert {"resume", "status"} <= set(_subcommands()), (
        "§2 wires unpark BESIDE resume/status; those two have gone missing"
    )


def test_u1_exactly_five_lift_edges_and_no_more():
    """§1: new transitions ("parked" -> X) for EXACTLY the five states that
    today have an edge INTO parked (spec_ok, implemented, verified, gated,
    reviewed) — derived from the table itself, not from a copied list."""
    into_parked = {src for src, dests in orch.TRANSITIONS.items() if "parked" in dests}
    assert into_parked == set(LIFT_STATES), (
        "the contract names the five states by the edges INTO parked; the table now draws "
        f"those from {sorted(into_parked)}"
    )
    out_of_parked = set(orch.TRANSITIONS.get("parked") or {})
    assert out_of_parked == into_parked, (
        "§1: the park's exit is EXACTLY its entrances. `TRANSITIONS['parked']` draws "
        f"{sorted(out_of_parked)}; the entrances are {sorted(into_parked)}"
    )


@pytest.mark.parametrize("park_from", LIFT_STATES)
def test_u1_each_lift_edge_is_legal_owned_and_replays_clean(tmp_path, park_from):
    """§1: all four tables learn the edges, and "replay_ledger is table-driven
    and must accept a lift line (pin it)"."""
    assert orch.legal_transition("parked", park_from), f"§4 draws no parked --> {park_from}"
    label = orch.assert_transition("parked", park_from)
    assert isinstance(label, str), f"the parked --> {park_from} edge carries no §4 label"
    assert ("parked", park_from) in orch.EDGE_STAGE, (
        f"EDGE_STAGE has no row for ('parked', {park_from!r}) — `_restage` indexes that table "
        "DIRECTLY on every resume, so a missing row is a KeyError on the next resume"
    )
    assert orch.NEXT_STAGE.get(park_from) is not None, (
        f"a lift to {park_from!r} must land where a stage runs, or the resume the tool prints "
        "has nothing to do"
    )

    slug = "x"
    path = tmp_path / "ledger.jsonl"
    _write_ledger(path, [*_park_rows(slug, park_from),
                         _row(slug, "parked", park_from, f"operator unpark: lift; {PARK_REASON}")])
    table = orch.replay_ledger(path)
    assert table[slug]["state"] == park_from, "the lift line must replay to the park's from-state"
    assert table[slug]["terminal"] is False, "a lifted slot is no longer terminal"
    assert table[slug]["rejects"]["verifier"] == 0, "a lift is not a reject tally"


def test_u1_lift_restores_the_park_from_state_and_a_resume_finishes_the_batch(
        parked_batch, capsys):
    """U1: a parked slot is lifted to its park-line `from` state and a resume
    under fake runners re-runs that stage; the batch completes.

    Also §2's print contract ("prints the state restored and the resume
    command") and §2's "runs NO stage itself" — the lift appends one line and
    the ledger gains nothing else until the resume runs.
    """
    rig = parked_batch("ge5-u1", "implemented")
    assert orch.replay_ledger(rig.ledger)[rig.slug]["state"] == "parked", "fixture is not parked"
    walked = len(_spine(rig.ledger))

    code, out = _unpark(rig.batch_id, rig.slug, reason=OPERATOR_REASON, capsys=capsys)
    assert code == 0, f"§2: exit 0 on a written line; got {code}\n{out}"

    table = orch.replay_ledger(rig.ledger)
    assert table[rig.slug]["state"] == "implemented", (
        "§1: the lift restores THE state the slot parked FROM, read off the ledger's last "
        f"`to == parked` line; the slot is at {table[rig.slug]['state']!r}"
    )
    assert table[rig.slug]["terminal"] is False
    assert _spine(rig.ledger)[walked:] == [("parked", "implemented")], (
        "§2: the lift appends EXACTLY ONE transition and runs no stage"
    )
    assert "implemented" in out, f"§2: the tool prints the state restored; it printed:\n{out}"
    assert "resume" in out.lower() and rig.batch_id in out, (
        f"§2: the tool prints the resume command for this batch; it printed:\n{out}"
    )

    # …and now the machine, not the operator: the resume drives the stage that
    # parked the slot (s3_verify, from `implemented`) and the batch completes.
    journal = b11._Journal()
    report = b11._advance(rig.cfg, b11._Runners(journal, rig.cfg))
    spine = _spine(rig.ledger)
    assert ("implemented", "verified") in spine[walked:], (
        "§3: an unparked slot re-enters the ORDINARY ladder — the stage that parked it must "
        f"run again. The ledger after the lift reads {spine[walked:]}"
    )
    assert orch.replay_ledger(rig.ledger)[rig.slug]["state"] == "packaged", (
        "U1: the batch completes once the park is lifted"
    )
    assert report["status"] == "complete" and report["exit_code"] == 0, (
        f"U1: status={report['status']!r} exit={report['exit_code']}"
    )


def test_u1_a_pre_p4_handwritten_config_still_unparks(parked_batch, capsys):
    """§2: "wired beside resume/status via `cli._config_for`, so pre-P-4
    hand-written configs keep working" — a batch with no persisted
    `out/batches/<id>/config.yaml`, only `config/<id>.yaml`."""
    rig = parked_batch("ge5-u1-handwritten", "verified", handwritten=True)
    assert not (rig.bdir / cli.BATCH_CONFIG_NAME).exists(), "fixture persisted a config"

    code, out = _unpark(rig.batch_id, rig.slug, reason=OPERATOR_REASON, capsys=capsys)
    assert code == 0, f"§2: the hand-written config path must keep working; exit {code}\n{out}"
    assert orch.replay_ledger(rig.ledger)[rig.slug]["state"] == "verified"


# --------------------------------------------------------------------------- #
# U2 — the refusal matrix: loud, and NOTHING appended
# --------------------------------------------------------------------------- #


def _refused(rig, slug, *, reason, capsys) -> str:
    """Drive a refusal and prove the ledger did not move. -> the output.

    The no-append check runs FIRST and unconditionally, because it is the half
    of U2 that matters: a refusal that wrote a line is worse than a crash.
    """
    _unpark_subparser()
    before = rig.ledger.read_bytes()
    argv = ["unpark", rig.batch_id, slug]
    if reason is not None:
        argv += ["--reason", reason]
    crash: BaseException | None = None
    code: int | None = None
    try:
        code = cli.main(argv)
    except BaseException as exc:          # noqa: BLE001 — reported as a failed refusal below
        crash = exc
    out = capsys.readouterr()
    text = out.out + out.err
    assert rig.ledger.read_bytes() == before, (
        "U2: a refused unpark appends NOTHING — the ledger must be byte-identical after"
    )
    assert crash is None, (
        "§2 asks for a LOUD REFUSAL with a nonzero exit code, not a traceback; "
        f"unpark raised {crash!r}"
    )
    assert code != 0, f"§2: exit 0 ONLY on a written line; the refusal exited {code}\n{text}"
    assert text.strip(), "§2: the refusal must be LOUD — it printed nothing at all"
    return text


def test_u2_a_slot_that_is_not_parked_is_refused(parked_batch, capsys):
    """U2 / §2: "REQUIRES the slot's replayed state == `parked`" — a loud
    refusal that appends nothing."""
    slug = orch.slot_id("ge5-u2-notparked", 1)
    rig = parked_batch("ge5-u2-notparked",
                       rows=[_row(slug, frm, to, f"pre-E-5 walk {frm} -> {to}")
                             for frm, to in WALK["implemented"]])
    assert orch.replay_ledger(rig.ledger)[rig.slug]["state"] == "implemented"
    text = _refused(rig, rig.slug, reason=OPERATOR_REASON, capsys=capsys).lower()
    assert "park" in text or "implemented" in text, (
        f"the refusal must say the slot is not parked; it said:\n{text}"
    )


def test_u2_an_unknown_slug_is_refused(parked_batch, capsys):
    """U2 / §2: "Loud refusals: unknown batch/slug" — a slug the ledger has
    never heard of lifts nothing and writes nothing."""
    rig = parked_batch("ge5-u2-unknown")
    missing = f"{rig.batch_id}-s404"
    text = _refused(rig, missing, reason=OPERATOR_REASON, capsys=capsys)
    assert missing in text, f"the refusal must name the slug it could not find:\n{text}"


@pytest.mark.parametrize("reason", ["", "   ", "\t\n"], ids=["empty", "spaces", "whitespace"])
def test_u2_an_empty_or_blank_reason_is_refused(parked_batch, capsys, reason):
    """U2 / §2: "requires a non-empty --reason" — the lift is a RECORDED
    operator act, so an unexplained one is refused and appends nothing."""
    rig = parked_batch(f"ge5-u2-reason-{len(reason)}")
    text = _refused(rig, rig.slug, reason=reason, capsys=capsys).lower()
    assert "reason" in text, f"the refusal must name the missing reason; it said:\n{text}"


# --------------------------------------------------------------------------- #
# U3 — one lift = one line
# --------------------------------------------------------------------------- #


def test_u3_one_lift_appends_exactly_one_line_and_nothing_else_moves(parked_batch, capsys):
    """U3: the appended transition is the ONLY mutation; hashes present; cost
    absent/None; the reason quotes BOTH the operator text and the original park
    reason (§2: "reason `operator unpark: <text>` + the park line's own reason
    quoted; current hashes; no cost")."""
    rig = parked_batch("ge5-u3", "gated")
    before_bytes = rig.ledger.read_bytes()
    before_tree = _tree(rig.bdir)

    code, out = _unpark(rig.batch_id, rig.slug, reason=OPERATOR_REASON, capsys=capsys)
    assert code == 0, f"exit {code}\n{out}"

    after_bytes = rig.ledger.read_bytes()
    assert after_bytes.startswith(before_bytes), (
        "U3: the ledger is APPEND-ONLY — the bytes that were there must still be there, "
        "unchanged, as a prefix"
    )
    appended = after_bytes[len(before_bytes):].decode("utf-8").splitlines()
    assert len([raw for raw in appended if raw.strip()]) == 1, (
        f"U3: one lift = one line; the lift appended {appended!r}"
    )

    line = json.loads(appended[0])
    assert tuple(line) == LEDGER_KEYS, (
        f"the lift line must carry the frozen ledger keys {list(LEDGER_KEYS)}, in order; "
        f"got {list(line)}"
    )
    assert (line["from"], line["to"]) == ("parked", "gated"), (
        f"the lift travels parked --> the park line's own `from`; got {line['from']} --> "
        f"{line['to']}"
    )
    assert line["slug"] == rig.slug
    assert set(line["hashes"]) == set(HASH_KEYS), (
        f"§2: current hashes — the three keys {list(HASH_KEYS)}; got {sorted(line['hashes'])}"
    )
    for key, value in line["hashes"].items():
        assert value is None or isinstance(value, str), f"hashes.{key} = {value!r}"
    assert line["cost"] is None, (
        f"§2 says NO COST — a recorded operator act spends nothing; got {line['cost']!r}"
    )

    reason = str(line["reason"])
    assert reason.startswith("operator unpark"), (
        f"§2 spells the reason `operator unpark: <text>`; got {reason!r}"
    )
    assert OPERATOR_REASON in reason, (
        f"U3: the reason must quote the OPERATOR's text verbatim; got {reason!r}"
    )
    assert PARK_REASON in reason, (
        f"U3: the reason must quote the ORIGINAL park reason too — a lift that drops it loses "
        f"the only record of what the slot was parked for; got {reason!r}"
    )

    after_tree = _tree(rig.bdir)
    ledger_rel = str(rig.ledger.relative_to(rig.bdir))
    assert {k: v for k, v in after_tree.items() if k != ledger_rel} == \
           {k: v for k, v in before_tree.items() if k != ledger_rel}, (
        "U3: the appended transition is the ONLY mutation — the lift runs no stage and "
        "rewrites nothing else in the batch directory"
    )


# --------------------------------------------------------------------------- #
# U4 — the cycle, and the report's parked block
# --------------------------------------------------------------------------- #

SECOND_PARK_REASON = "round-cap park: undeclared-deception (verify round 9, verifier.round_cap 4)"


def test_u4_a_re_park_after_a_lift_is_legal_and_a_second_lift_works(parked_batch, capsys):
    """U4 / §3: "if the stage that parked it fails again it may park again (a
    second lift is a new recorded operator act; pin the park -> lift -> re-park
    -> lift cycle)". The re-park is appended through the machine's own
    `append_transition`, so "legal" means what the state machine says."""
    rig = parked_batch("ge5-u4-cycle", "implemented")

    code, out = _unpark(rig.batch_id, rig.slug, reason=OPERATOR_REASON, capsys=capsys)
    assert code == 0, f"first lift: exit {code}\n{out}"
    assert orch.replay_ledger(rig.ledger)[rig.slug]["state"] == "implemented"

    # the stage parks it AGAIN — the ordinary ladder's own edge, unchanged
    orch.append_transition(rig.ledger, slug=rig.slug, from_state="implemented",
                           to_state="parked", reason=SECOND_PARK_REASON,
                           hashes=dict(FIXTURE_HASHES), cost=None)
    assert orch.replay_ledger(rig.ledger)[rig.slug]["state"] == "parked", (
        "§3: a re-park after a lift must replay — the lift is not an exemption"
    )

    before = len(_lines(rig.ledger))
    second = "second lift: the audit's residual is record-only under L-1"
    code, out = _unpark(rig.batch_id, rig.slug, reason=second, capsys=capsys)
    assert code == 0, f"second lift: exit {code}\n{out}"

    lines = _lines(rig.ledger)
    assert len(lines) == before + 1, "the second lift is ONE new recorded act"
    assert (lines[-1]["from"], lines[-1]["to"]) == ("parked", "implemented")
    assert second in lines[-1]["reason"], "the second lift carries its OWN operator text"
    assert SECOND_PARK_REASON in lines[-1]["reason"], (
        "§1: the lift is read off THE LAST line whose `to` == parked — so the reason it "
        f"quotes is the LATEST park's, not the first one's. Got {lines[-1]['reason']!r}"
    )
    assert orch.replay_ledger(rig.ledger)[rig.slug]["state"] == "implemented"


def test_u4_the_report_counts_a_relifted_slot_once_with_the_latest_reason(
        parked_batch, capsys):
    """U4 / §4: "a slot lifted and re-parked counts once, with the LATEST park
    reason" — and the block is ledger-derived (D-3's rule)."""
    rig = parked_batch("ge5-u4-report", "implemented")
    code, out = _unpark(rig.batch_id, rig.slug, reason=OPERATOR_REASON, capsys=capsys)
    assert code == 0, f"exit {code}\n{out}"
    orch.append_transition(rig.ledger, slug=rig.slug, from_state="implemented",
                           to_state="parked", reason=SECOND_PARK_REASON,
                           hashes=dict(FIXTURE_HASHES), cost=None)

    report = orch.run_batch(rig.cfg, runners=b11._Runners(b11._Journal(), rig.cfg))
    mine = [entry for entry in report["parked"] if entry["slug"] == rig.slug]
    assert len(mine) == 1, (
        f"§4: a slot lifted and re-parked counts ONCE; the report lists {mine}"
    )
    assert mine[0]["reason"] == SECOND_PARK_REASON, (
        f"§4: with the LATEST park reason; the report shows {mine[0]['reason']!r}"
    )
    assert report["states"] == {"parked": 1}, f"states: {report['states']}"


def test_u4_the_report_forgets_a_park_whose_slot_moved_on(parked_batch, capsys):
    """U4 / §4: "the batch report's `parked` block must not count a slot whose
    park was lifted and whose state moved on" — the report counts the slot per
    its CURRENT state only."""
    rig = parked_batch("ge5-u4-movedon", "implemented")
    code, out = _unpark(rig.batch_id, rig.slug, reason=OPERATOR_REASON, capsys=capsys)
    assert code == 0, f"exit {code}\n{out}"

    report = b11._advance(rig.cfg, b11._Runners(b11._Journal(), rig.cfg))
    assert orch.replay_ledger(rig.ledger)[rig.slug]["state"] == "packaged", "the slot never moved"
    assert [entry for entry in report["parked"] if entry["slug"] == rig.slug] == [], (
        "§4 report honesty: this slot's park was LIFTED and the slot packaged — a report that "
        f"still lists it is reporting a residual nobody has. Got {report['parked']}"
    )
    assert report["states"] == {"packaged": 1}, f"states: {report['states']}"
    assert report["closing_note"] == "review complete", (
        "the closing note counts the report's parked block, so an honest block means no "
        f"\"; N parked\" tail here. Got {report['closing_note']!r}"
    )


# --------------------------------------------------------------------------- #
# U5 — byte-identity: a pre-E-5 ledger replays exactly as it does today
# --------------------------------------------------------------------------- #
#
# THE HOUSE RULE's regression half: "a tree nobody unparks behaves
# byte-identically to today". These pins are GREEN before the feature exists —
# that is the point. They are written as absolute expectations rather than as a
# diff against a baseline, because the blind lane has no pre-E-5 tree to diff
# against: every number below is what the committed machine produces today.


@pytest.mark.parametrize("park_from", LIFT_STATES)
def test_u5_a_pre_e5_park_ledger_replays_unchanged(tmp_path, park_from):
    """U5: replaying a pre-E-5 ledger (no lift lines) is unchanged — state and
    terminal flag included."""
    slug = "x"
    path = tmp_path / "ledger.jsonl"
    rows = _park_rows(slug, park_from)
    _write_ledger(path, rows)
    entry = orch.replay_ledger(path)[slug]
    assert entry["state"] == "parked"
    assert entry["terminal"] is True, "parked is still terminal for a slot nobody unparked"
    assert len(entry["history"]) == len(rows)
    assert entry["history"][-1]["reason"] == PARK_REASON
    assert entry["first_ts"] == PARK_TS and entry["last_ts"] == PARK_TS


def test_u5_the_pre_e5_counters_are_unchanged(tmp_path):
    """U5: "state, counters" — the reject tallies and the cost roll-up a
    pre-E-5 ledger replays to, unchanged."""
    slug = "x"
    cost = {"usd": 0.5, "tokens_in": 1200, "tokens_out": 300}
    rows = [
        _row(slug, None, "ideated", "walk"),
        _row(slug, "ideated", "respec", "lint kill"),
        _row(slug, "respec", "ideated", "re-sample"),
        _row(slug, "ideated", "spec_ok", "lint pass"),
        _row(slug, "spec_ok", "implemented", "validate green", cost=cost),
        _row(slug, "implemented", "spec_ok", "verifier reject"),
        _row(slug, "spec_ok", "implemented", "validate green"),
        _row(slug, "implemented", "parked", PARK_REASON),
    ]
    path = tmp_path / "ledger.jsonl"
    _write_ledger(path, rows)
    entry = orch.replay_ledger(path)[slug]
    assert entry["state"] == "parked" and entry["terminal"] is True
    assert entry["rejects"] == {"lint_kill": 1, "resample": 1, "verifier": 1,
                                "battery_crash": 0, "green_death": 0}
    assert entry["cost"] == cost, "a park carries no cost of its own"


def test_u5_the_pre_e5_report_blocks_are_unchanged(parked_batch):
    """U5: "report blocks" — a batch whose one slot is parked and that nobody
    unparked reports exactly what it reports today."""
    rig = parked_batch("ge5-u5-report", "implemented")
    before = rig.ledger.read_bytes()

    report = orch.run_batch(rig.cfg, runners=b11._Runners(b11._Journal(), rig.cfg))

    assert rig.ledger.read_bytes() == before, (
        "a run over an all-terminal batch appends nothing — the park is still terminal"
    )
    assert report["status"] == "complete" and report["exit_code"] == 0
    assert report["stop_reason"] is None
    assert report["closing_note"] == "review complete; 1 parked"
    assert report["parked"] == [{"slug": rig.slug, "reason": PARK_REASON}]
    assert report["states"] == {"parked": 1}
    assert report["blocked"] == [] and report["review"]["pending"] == []
    assert report["attrition"]["dead"] == 0 and report["attrition"]["fraction"] == 0.0
    assert report["attrition"]["abort"] is None
