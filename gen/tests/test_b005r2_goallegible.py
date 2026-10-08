"""The operator's 2026-09-29 legibility ruling: `tiers.goal_legible_cap`.

LEAD-AUTHORED. "let's only create obvious goal games instead of inferable too
for now" — a batch-wide ceiling on `game.knobs.goal_legible`, tightening the
§3.3 per-tier maxes through the EXISTING tier-knob-mismatch check. Default
absent = today's bytes; the parser refuses a cap with no enforcer.
"""

from __future__ import annotations

import pytest

from gen import tiers
from gen.s1_spec import GOAL_LEGIBLE_CAP_LINE, _goal_legible_ceiling


def _policy(**over) -> tiers.TierPolicy:
    raw = {"knob_defaults_action": "kill", **over}
    return tiers.tier_policy({"tiers": raw})


def test_absent_cap_is_todays_bytes() -> None:
    policy = _policy()
    assert policy.goal_legible_cap is None
    for tier, row in tiers.TIER_TABLE.items():
        assert _goal_legible_ceiling(row, policy) == row.goal_legible_max, tier


def test_cap_obvious_tightens_every_tier_to_zero() -> None:
    policy = _policy(goal_legible_cap="obvious")
    assert policy.goal_legible_cap == "obvious"
    for tier, row in tiers.TIER_TABLE.items():
        assert _goal_legible_ceiling(row, policy) == 0, tier


def test_cap_never_loosens() -> None:
    """t1's own max is already 'obvious'; a looser cap must not raise it."""
    policy = _policy(goal_legible_cap="opaque")
    row = tiers.TIER_TABLE["t1"]
    assert _goal_legible_ceiling(row, policy) == row.goal_legible_max == 0


@pytest.mark.parametrize("bad", ["visible", "OBVIOUS", 1, True, [], "x"])
def test_invalid_cap_is_loud(bad) -> None:
    with pytest.raises(ValueError, match="goal_legible_cap"):
        tiers.tier_policy({"tiers": {"knob_defaults_action": "kill",
                                     "goal_legible_cap": bad}})


def test_cap_without_enforcer_is_refused() -> None:
    with pytest.raises(ValueError, match="no enforcer"):
        tiers.tier_policy({"tiers": {"goal_legible_cap": "obvious"}})


def test_lint_fires_on_inferable_under_the_cap() -> None:
    """A t2 spec declaring `inferable` — legal by the tier table — dies under
    the cap, and the message names the cap and the ruling, not the tier."""
    from gen.s1_spec import lint_spec

    spec = {
        "game": {
            "title": "Cap Probe",
            "knobs": {"refusal": "visible", "goal_legible": "inferable",
                      "danger_tell": "none", "deceptions": []},
        },
    }
    report = lint_spec(
        spec, (), idea={"tier": "t2"},
        tier_policy=_policy(goal_legible_cap="obvious"),
    )
    rows = [f for f in (list(report.kills) + list(report.warns))
            if "tier-knob-mismatch" in str(f) and "goal_legible" in str(f)]
    assert rows, f"the cap did not fire: kills={report.kills!r} warns={report.warnings!r}"
    text = str(rows[0])
    assert "goal_legible_cap" in text and "legibility ruling" in text


def test_prompt_states_the_cap() -> None:
    line = GOAL_LEGIBLE_CAP_LINE.format(cap="obvious")
    assert "CAPS goal_legible AT 'obvious'" in line
    assert "Hidden STRUCTURE" in line and "hidden OBJECTIVE is not" in line
