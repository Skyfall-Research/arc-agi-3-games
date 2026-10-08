"""R2 hotfix #5 acceptance: the S2 session policy carries an `effort` knob.

Run: .venv/bin/python -m pytest gen/tests/test_r2_hotfix5.py -v

The incident (R2, 2026-09-22): S2 sessions at DEFAULT effort sat >30 minutes
in silent extended thinking and died on `SESSION_TIMEOUT_S` (1800s) with
"partial stdout: <empty>" — attempt 1's record shows the DriverError and
tokens_cumulative 0, while S1 (which passes `effort` explicitly since B5's
identical finding) completed every session all day. The fix threads `effort`
through the config session policy; `session()` already validated the value
and omits the flag for None, so configs without the key are byte-identical.

Lead-authored (operator-approved direct patch), same as test_r2_hotfix3.py.
"""

from __future__ import annotations

from gen.backends import SESSION_POLICY_DEFAULTS, get_session_policy
from gen.config import load_config

PILOT = "config/b001-pilot.yaml"


def test_the_localclaude_policy_defaults_carry_effort_none():
    """None = the CLI's default deliberation; the flag is omitted downstream."""
    assert SESSION_POLICY_DEFAULTS["localclaude"]["effort"] is None


def test_a_config_without_the_key_gets_effort_none():
    """Back-compat: every pre-fix config reads exactly as it did."""
    policy = get_session_policy({"backends": {"localclaude": {"session": {
        "permission_mode": "acceptEdits", "allowed_tools": ["Edit"],
    }}}}, "localclaude")
    assert policy["effort"] is None, f"absent key must default to None, got {policy!r}"


def test_the_pilot_config_caps_s2_effort_at_medium():
    """The R2 ruling: S2 runs at S1's all-day-proven deliberation cap."""
    cfg = load_config(PILOT)
    policy = get_session_policy(cfg, "localclaude")
    assert policy["effort"] == "medium", (
        f"{PILOT} must carry backends.localclaude.session.effort: medium — the default-effort "
        f"S2 session died silent on the 1800s timeout. Policy: {policy!r}"
    )
    assert policy["permission_mode"] == "acceptEdits", "the rest of the policy is untouched"
    assert "Edit" in policy["allowed_tools"], "the rest of the policy is untouched"
