"""R2 hotfix #2 acceptance: the re-spec cap becomes configurable (and the pilot
raises it to 3), and the writer prompt carries the curriculum note — tested
from the contract.

Run: .venv/bin/python -m pytest gen/tests/test_r2_hotfix2.py -v

Written against the frozen R2 hotfix-2 mini-contract while `gen/orchestrator.py`,
`gen/s1_spec.py` and `config/b001-pilot.yaml` were changed in parallel; no line
of that work was read. What R2 hit: one slot burned its two re-spec strikes and
blocked, and the writer had no standing instruction that a level marked `reuse`
is compulsory — so the same curriculum kill kept coming back.

Two standing rules this file keeps (the test_r2_hotfix.py precedent):

  * NO API call, ever. `build_writer_prompt` is a pure builder, and every
    orchestrator path below is driven by FAKE stage runners.
  * NO writes outside `tmp_path`. `out/` is never touched (`batch_home` re-roots
    every repo path at `tmp_path`, and b11's autouse `_repo_batches_untouched`
    guard is imported so a stray write fails loudly); `config/` is read via
    `load_config` and never written.

THE HARNESS IS IMPORTED, NOT COPIED. `gen/tests/test_b11_pipeline.py` already
owns the fake-runner rig that drives the §4 machine (`_Runners`/`_Outcome`
script a stage's failure by the state it fires FROM; `make_cfg`/`batch_home`
give each test its own batch root). This file imports it rather than growing a
second copy that could drift. Note b11 has NO existing test for the "lint
kill(s) at cap" block — only for a single kill that resamples — so the block is
observed here for the first time, at both caps.

Contract readings this file encodes where the hotfix-2 contract left a choice
open — each one is a line to renegotiate, not a fact:

  * "Invalid values raise ValueError" is taken at its word for ALL SIX named
    values, including the three that are type faults (`"3"`, `2.5`, `None`).
    A `TypeError` there would fail these tests. The repo's own `_int_key`
    validator already answers exactly this set with `ValueError`, so the
    contract's word and the repo's idiom agree; nothing else was assumed.
  * A cfg with NO `orchestrator` block at all is NOT pinned. The contract
    hedges ("an empty dict may or may not be a valid cfg for other reasons"),
    so that case is asserted only as: 2, or a raise the caller can see — never
    a silent `None`/`0`/other number.
  * "3 -> 3, 1 -> 1" is read as the general rule "an int >= 1 is returned
    as-is", and parametrised over 1, 2, 3, 9. An implementation that
    whitelisted only the named values would be wrong for a reason the contract
    plainly implies.
  * "the block reason" is read as the batch report's per-slot
    `blocked["reason"]` — the one place `run_batch` already surfaces it. The
    report's top-level `blocked` list and the slot's replayed state are
    asserted alongside it, so "blocked" cannot be satisfied by a reason string
    on a slot that actually ran on.
  * "a slot with 2 lint kills is NOT blocked (it proceeds to re-sample)" is
    pinned as all three of: no blocked row, a SECOND `respec -> ideated` line
    in the ledger, and the slot reaching a terminal state.
  * "with 3 lint kills it IS blocked" is pinned with an exact count: at cap N
    the block fires on the Nth kill, so the ledger holds exactly N
    `ideated -> respec` lines. Without that count, blocking early with a
    reworded message would pass.
  * "with no config key, behavior is byte-identical to today" is tested with
    the key REMOVED from the cfg mapping, not by trusting the fixture: after
    the pilot config carries `respec_cap: 3`, b11's `make_cfg` (which deep-
    copies the pilot config) hands every test a cfg that already has it.
  * "mirroring the NEG2_NOTATION_HEADER/NEG2_NOTATION_NOTE pattern" is read
    structurally: the NOTE opens with the HEADER, and the HEADER is a one-line
    `###` markdown heading. That is what the mirrored pair is on disk.
  * The rationale clause is matched whitespace-flattened and case-insensitively
    — re-wrapping the constant, or capitalising it at a sentence start, is
    formatting, not contract.
  * The literal value `reuse` is required as a STANDALONE word. The rationale
    clause contains "reused", which would satisfy a plain substring check on
    its own and leave the field's actual value unstated.
  * The "§7 citation" is read as the literal section mark plus 7 (`§7`, or
    `§ 7`), anywhere in the note.
"""

from __future__ import annotations

import re

import pytest

from gen.config import load_config
from gen.orchestrator import RESPEC_CAP, _respec_cap
from gen.s1_spec import (
    CURRICULUM_NOTE,
    CURRICULUM_NOTE_HEADER,
    NEG2_NOTATION_NOTE,
    SCHEMA_HEADER,
    build_writer_prompt,
)

# The b11 fake-runner rig (imported, never copied — see the module docstring).
# Its helpers are called through `b11.` so every borrowed piece names its
# owner; its fixtures have to be re-bound here, because pytest resolves a
# fixture by looking up that name in the REQUESTING module.
from gen.tests import test_b11_pipeline as b11

#: b11's own guards, adopted deliberately: no network / no agent session, and
#: a fail-loud check that nothing wrote into the repo's `out/batches/`.
_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched
#: `batch_home` re-roots every repo path at `tmp_path`; `make_cfg` deep-copies
#: the pilot config into a batch id nobody else uses.
batch_home = b11.batch_home
make_cfg = b11.make_cfg

PILOT = "config/b001-pilot.yaml"

#: what the fake S1 stage says when the test scripts a lint kill (b11 idiom).
LINT_KILL_REASON = "lint kill: unknown term"

#: the §4 edges the cap counts and the cap releases.
KILL_EDGE = ("ideated", "respec")
RESAMPLE_EDGE = ("respec", "ideated")

#: an `orchestrator` block exactly as §5 spells it, minus the new key.
NO_KEY_BLOCK = {"workers": 4, "wave_size": 5, "max_attrition": 0.30}

#: the pilot's pre-existing `orchestrator` keys — unchanged by the hotfix.
PILOT_ORCHESTRATOR = {"workers": 4, "wave_size": 5, "max_attrition": 0.30}

#: the rationale the note must carry (§7's own doctrine, in the words the
#: curriculum linter already uses when it kills a spec for missing it).
RATIONALE = "a mechanic is not established until it is reused in a contrasting context"

SECTION_7_RE = re.compile(r"§\s*7\b")
STANDALONE_REUSE_RE = re.compile(r"\breuse\b")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _cfg() -> dict:
    return load_config(PILOT)


def _flat(text: str) -> str:
    """Whitespace-normalised, so a re-wrapped note still matches."""
    return " ".join(text.split())


# A hand-written idea carrying exactly what `build_writer_prompt` requires
# (id, seed_terms, prose) — the test_r2_hotfix.py pattern, and the right one
# here too: the curriculum note is static prompt text, so no artifact under
# `out/` needs to exist for this file to run.
MINIMAL_IDEA = {
    "id": "b001-pilot-i001",
    "seed_terms": ["info.fog", "goal.cover"],
    "prose": {
        "title": "Fogbound Switchyard",
        "text": "Belts carry coloured crates past cycleable junctions toward matching pads.",
    },
}


def _drive_lint_kills(make_cfg, batch_id: str, *, cap: int | None, kills: int):
    """One slot whose S1 stage lint-kills `kills` times in a row, under `cap`.

    `cap=None` means "no `orchestrator.respec_cap` key at all" — the default
    path, which must behave exactly as the build did before this hotfix.
    """
    cfg, _path = make_cfg(batch_id)
    if cap is None:
        cfg["orchestrator"].pop("respec_cap", None)
        assert "respec_cap" not in cfg["orchestrator"], (
            "fixture: the default-path test must run with the key ABSENT"
        )
    else:
        cfg["orchestrator"]["respec_cap"] = cap
    journal = b11._Journal()
    runners = b11._Runners(
        journal,
        cfg,
        outcomes={"ideated": b11._Outcome("respec", LINT_KILL_REASON, times=kills)},
    )
    report = b11._advance(cfg, runners)
    return cfg, report


def _only_slot(report) -> dict:
    slots = report["slots"]
    assert len(slots) == 1, f"these tests run a one-slot batch; the report has {len(slots)}"
    return slots[0]


def _edge_lines(cfg, edge: tuple[str, str]) -> list[dict]:
    return [line for line in b11._ledger_lines(cfg) if (line["from"], line["to"]) == edge]


def _block_reason(report) -> str:
    row = _only_slot(report)
    blocked = row["blocked"]
    assert blocked, (
        f"the slot is not blocked at all — state {row['state']!r}, rejects {row['rejects']}, "
        f"stop_reason {report['stop_reason']!r}"
    )
    reason = blocked.get("reason")
    assert isinstance(reason, str) and reason.strip(), (
        f"a blocked slot must carry a non-empty reason, got {reason!r}"
    )
    return reason


# --------------------------------------------------------------------------
# 1: _respec_cap as a pure function
# --------------------------------------------------------------------------


def test_respec_cap_constant_is_still_two():
    """The hotfix makes the cap configurable; it does not move the default."""
    assert RESPEC_CAP == 2


def test_respec_cap_defaults_to_the_constant_when_the_key_is_absent():
    cap = _respec_cap({"orchestrator": dict(NO_KEY_BLOCK)})
    assert cap == 2, f"a config with no orchestrator.respec_cap must read as 2, got {cap!r}"
    assert cap == RESPEC_CAP, (
        f"the default must BE the module constant ({RESPEC_CAP}), not a second literal {cap!r}"
    )


@pytest.mark.parametrize("value", [1, 2, 3, 9])
def test_respec_cap_returns_a_configured_int(value):
    """`3 -> 3`, `1 -> 1` — read as: an int >= 1 comes back as itself."""
    cap = _respec_cap({"orchestrator": {**NO_KEY_BLOCK, "respec_cap": value}})
    assert cap == value, f"orchestrator.respec_cap={value!r} must read back as {value}, got {cap!r}"
    assert isinstance(cap, int) and not isinstance(cap, bool), (
        f"_respec_cap must return a plain int, got {type(cap).__name__}"
    )


@pytest.mark.parametrize(
    "value",
    [0, -1, True, "3", 2.5, None],
    ids=["zero", "negative", "bool-true", "string", "float", "explicit-none"],
)
def test_respec_cap_rejects_an_invalid_value(value):
    """Every one of the contract's six, as ValueError.

    `True` is the one worth naming: it is an `int` subclass, so a bare
    `isinstance(value, int)` check lets `respec_cap: true` through as a cap
    of 1 — a silently different policy, not a config error.
    """
    with pytest.raises(ValueError):
        _respec_cap({"orchestrator": {**NO_KEY_BLOCK, "respec_cap": value}})


def test_respec_cap_never_invents_a_cap_for_a_cfg_with_no_orchestrator_block():
    """The one case the contract hedges: 2, or a raise — never something else."""
    try:
        cap = _respec_cap({})
    except (KeyError, ValueError, TypeError):
        return
    assert cap == 2, (
        f"a cfg with no orchestrator block either defaults to 2 or raises; it returned {cap!r}"
    )


# --------------------------------------------------------------------------
# 2: the cap check in the §4 state machine (b11's fake runners)
# --------------------------------------------------------------------------


def test_the_default_cap_still_blocks_the_second_lint_kill(make_cfg):
    """No config key: byte-identical to today — two strikes and the slot blocks."""
    cfg, report = _drive_lint_kills(make_cfg, "r2h2-default-cap", cap=None, kills=5)

    reason = _block_reason(report)
    assert "at cap 2" in reason, f"the default block must still read 'at cap 2'; got {reason!r}"
    row = _only_slot(report)
    assert report["blocked"] == [row["slug"]], (
        f"the batch report must name the blocked slot: {report['blocked']}"
    )
    assert report["stop_reason"] == "blocked", report["stop_reason"]
    assert b11._table(cfg)[row["slug"]] == "respec", (
        f"a blocked slot parks at respec (§4 draws it no edge to dead): {b11._table(cfg)}"
    )
    assert len(_edge_lines(cfg, KILL_EDGE)) == 2, (
        "the default cap stops the slot on its SECOND lint kill: "
        f"{b11._spine(b11._ledger_lines(cfg))}"
    )
    assert len(_edge_lines(cfg, RESAMPLE_EDGE)) == 1, (
        f"exactly one re-sample fits under the default cap: {b11._spine(b11._ledger_lines(cfg))}"
    )


def test_a_configured_cap_of_three_lets_the_second_lint_kill_resample(make_cfg):
    """cap 3, two kills: NOT blocked — the slot re-samples and runs on."""
    cfg, report = _drive_lint_kills(make_cfg, "r2h2-cap3-under", cap=3, kills=2)

    row = _only_slot(report)
    assert row["blocked"] is None, (
        f"two lint kills sit UNDER a cap of 3, so nothing may block: {row['blocked']}"
    )
    assert report["blocked"] == [], f"the batch report blocks nobody here: {report['blocked']}"
    assert len(_edge_lines(cfg, KILL_EDGE)) == 2, b11._spine(b11._ledger_lines(cfg))
    assert len(_edge_lines(cfg, RESAMPLE_EDGE)) == 2, (
        "the second kill must buy a second `respec -> ideated` re-sample: "
        f"{b11._spine(b11._ledger_lines(cfg))}"
    )
    assert b11._table(cfg)[row["slug"]] == "packaged", (
        f"the slot the raised cap saved must finish the pipeline: {b11._table(cfg)}"
    )


def test_a_configured_cap_of_three_blocks_the_third_lint_kill(make_cfg):
    """cap 3, kills forever: blocked on the THIRD, and the reason says cap 3."""
    cfg, report = _drive_lint_kills(make_cfg, "r2h2-cap3-over", cap=3, kills=5)

    reason = _block_reason(report)
    assert "at cap 3" in reason, (
        f"the block must name the CONFIGURED cap, not the default; got {reason!r}"
    )
    assert "at cap 2" not in reason, f"the default cap must not leak into the reason: {reason!r}"
    row = _only_slot(report)
    assert report["blocked"] == [row["slug"]], report["blocked"]
    assert report["stop_reason"] == "blocked", report["stop_reason"]
    assert b11._table(cfg)[row["slug"]] == "respec", b11._table(cfg)
    assert len(_edge_lines(cfg, KILL_EDGE)) == 3, (
        "a cap of 3 must be spent in full — three lint kills, then the block: "
        f"{b11._spine(b11._ledger_lines(cfg))}"
    )
    assert len(_edge_lines(cfg, RESAMPLE_EDGE)) == 2, (
        f"two re-samples fit under a cap of 3: {b11._spine(b11._ledger_lines(cfg))}"
    )


# --------------------------------------------------------------------------
# 3: the pilot config carries the raised cap
# --------------------------------------------------------------------------


def test_the_pilot_config_raises_the_cap_to_four():
    cfg = _cfg()
    block = cfg["orchestrator"]
    assert block.get("respec_cap") == 4, (
        f"{PILOT} must carry orchestrator.respec_cap: 4, got {block.get('respec_cap')!r}"
    )
    assert _respec_cap(cfg) == 4, "the loaded pilot config must read back as a cap of 4"


def test_the_pilot_keeps_every_other_orchestrator_key():
    """The hotfix ADDS a key. `workers`, `wave_size` and `max_attrition` are
    architecture §5's own surface and are not renegotiated here."""
    block = _cfg()["orchestrator"]
    missing = sorted(set(PILOT_ORCHESTRATOR) - set(block))
    assert not missing, f"{PILOT} dropped pre-existing orchestrator key(s) {missing}"
    for key, expected in PILOT_ORCHESTRATOR.items():
        assert block[key] == expected, (
            f"orchestrator.{key} moved: expected {expected!r}, found {block[key]!r}"
        )


# --------------------------------------------------------------------------
# 4: the curriculum note
# --------------------------------------------------------------------------


def test_the_curriculum_note_mirrors_the_header_note_pattern():
    assert isinstance(CURRICULUM_NOTE_HEADER, str) and CURRICULUM_NOTE_HEADER.strip(), (
        "CURRICULUM_NOTE_HEADER must be non-empty text"
    )
    assert isinstance(CURRICULUM_NOTE, str) and CURRICULUM_NOTE.strip(), (
        "CURRICULUM_NOTE must be non-empty text"
    )
    assert "\n" not in CURRICULUM_NOTE_HEADER, (
        f"the header is one line, like NEG2_NOTATION_HEADER: {CURRICULUM_NOTE_HEADER!r}"
    )
    assert CURRICULUM_NOTE_HEADER.startswith("###"), (
        "the mirrored pattern is a `###` markdown heading, so the prompt's sections stay "
        f"navigable; got {CURRICULUM_NOTE_HEADER!r}"
    )
    assert CURRICULUM_NOTE.startswith(CURRICULUM_NOTE_HEADER), (
        "CURRICULUM_NOTE must OPEN with CURRICULUM_NOTE_HEADER (the NEG2 pattern) — a header "
        f"nobody reads is a second source of truth. Note starts: {CURRICULUM_NOTE[:120]!r}"
    )


def test_the_curriculum_note_names_the_field_the_value_the_reason_and_the_kill():
    note = CURRICULUM_NOTE
    flat = _flat(note)

    assert "relation_to_prev" in note, (
        "the note must name the §11 field literally (`relation_to_prev`) — the writer has to "
        "spell it, not infer it"
    )
    assert STANDALONE_REUSE_RE.search(note), (
        "the note must name the VALUE `reuse` as a word of its own; 'reused' inside the "
        f"rationale does not tell the writer what to write. Note: {note!r}"
    )
    assert RATIONALE.lower() in flat.lower(), (
        "the note must carry the rationale verbatim — 'a mechanic is not established until it "
        f"is reused in a contrasting context' — so the rule reads as doctrine. Note: {note!r}"
    )
    assert SECTION_7_RE.search(flat), (
        f"the note must cite §7, the canon section the rule comes from. Note: {note!r}"
    )
    assert re.search(r"(?i)kill", flat), (
        "the note must say that a spec with no `reuse` level is a lint KILL, not a preference "
        f"— that is the whole reason it exists. Note: {note!r}"
    )


def test_the_writer_prompt_carries_the_curriculum_note_after_the_neg2_note():
    prompt = build_writer_prompt(_cfg(), MINIMAL_IDEA)

    assert SCHEMA_HEADER in prompt, "the schema section header is the anchor; it must be present"
    assert NEG2_NOTATION_NOTE in prompt, "the neg2 note must still be in the prompt, verbatim"
    assert CURRICULUM_NOTE in prompt, (
        "the prompt must carry CURRICULUM_NOTE VERBATIM — a paraphrase in the prompt and a "
        "constant nobody reads is two sources of truth"
    )

    schema_at = prompt.index(SCHEMA_HEADER)
    neg2_at = prompt.index(NEG2_NOTATION_NOTE)
    curriculum_at = prompt.index(CURRICULUM_NOTE)
    assert neg2_at > schema_at, (
        f"the neg2 note still follows the schema header ({neg2_at} vs {schema_at})"
    )
    assert curriculum_at > neg2_at, (
        "the curriculum note belongs AFTER the neg2 note — both correct how the schema above "
        f"is read, and the order is the contract's ({curriculum_at} vs {neg2_at})"
    )
