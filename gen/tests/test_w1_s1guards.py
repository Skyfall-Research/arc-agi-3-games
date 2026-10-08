"""Blind pins for contract W1-B — the S1 fidelity guards (R-16 + R-17).

Run: .venv/bin/python -m pytest gen/tests/test_w1_s1guards.py -v

Written from the frozen W1-B contract ALONE. No line of the implementer's
in-progress `gen/s1_spec.py` was read: the only sources are the contract, the
PRE-change module (`git show HEAD:gen/s1_spec.py`), the LANDED `gen/tiers.py`,
the committed fixtures under `gen/tests/fixtures/specs/`, and the existing
escalation harness (`test_r2_hotfix6` / `test_r2_hotfix7`). These pins
therefore describe the contract, not the implementation, and are expected to
FAIL at HEAD and pass once R-16 + R-17 land.

What is pinned, in the contract's own order:

  1. the registry — `mix-hazardless` and `terms-introduced-coverage` exist as
     rule ids in a module-level registry (the `TIER_RULES` pattern), OUTSIDE
     the closed `KILL_RULES` tuple; each takes an off|warn|kill action knob
     that DEFAULTS OFF, so an unconfigured lint is byte-identical to the
     pre-contract one even for a spec that would trigger both rules; `warn`
     and `kill` behave only under an explicitly armed config; the shipped
     `config/template.yaml` arms both at `warn`;
  2. `mix-hazardless` — fires on a hazardless idea whose spec declares a
     `hazard.`-prefixed term (and on a non-`none` `danger_tell`), stays silent
     when `mix_class.hazardless` is false / absent / there is no idea, and
     stays silent under a declared override;
  3. `terms-introduced-coverage` — fires naming EXACTLY the declared terms no
     level introduces, silent when every term is introduced;
  4. R-17 — an escalated rewrite gets a budget-only re-check under the FULL
     policy: within budget => `ran`, over-budget-then-trimmed => `reconciled`
     (one re-prompt carrying a named budget-reconciliation directive),
     over-budget twice => `failed` (a real kill naming the budget). The
     lint-report records which path was taken;
  5. the stock (non-escalation, non-triggering) lint path is unchanged — the
     report is the one measured at HEAD, key for key.

Readings this file had to resolve. Each is quoted in the failure message of
the pin that depends on it, and each is a line to renegotiate, not a fact:

  a. THE KNOB SURFACE IS DISCOVERED, NEVER ASSUMED. The contract freezes the
     rule ids and the values (off|warn|kill) but leaves the plumbing to the
     implementer, and `lint_spec` is PURE (it never reads config), so the
     actions must arrive as a parameter — the `require_render` precedent.
     `_knob()` below tries every plausible construction against a fixture that
     violates `mix-hazardless` and keeps the one that actually honours
     off/warn/kill. If none does, every knob pin fails naming what was tried.
  b. THE OVERRIDE SURFACE IS DISCOVERED THE SAME WAY. R-16 says "design the
     override surface — a spec annotation or config exemption", so this file
     cannot name it. The grid below is seeded from the implementation's own
     new constants (`OPTIONAL_GAME_FIELDS` / `KNOB_FIELDS` additions, new
     `*OVERRIDE*` / `*EXEMPT*` string constants) before it falls back to
     literal guesses — a spec annotation added house-style is found by name.
  a'. DEFAULT OFF, NOT WARN — LEAD CONTRACT CORRECTION (mid-flight, W1-B).
     The contract text says "DEFAULT warn"; the house-style line above it
     ("canon-default OFF-or-warn behavior with byte-identical reports when
     unconfigured") wins, and the repo already pins it:
     `test_b003_render.py::test_shipped_specs_match_their_shipped_lint_report`
     re-lints every shipped spec UNCONFIGURED and demands its stored report
     back byte-for-byte. Warn-by-default breaks that on convoy-in-the-fog and
     core-ward-phase-gates — the two games R-16's own audit evidence names.
     So: the knobs parse off|warn|kill and default OFF, every firing pin below
     arms its rule EXPLICITLY, and `config/template.yaml` ships them at warn.
  c. "byte-identical" is read as the sibling blind file reads it: equality of
     the report's CONTENT (`to_json_dict()`), which is what a byte-identical
     `lint-report.json` means. The pre-contract content of every fixture used
     here was MEASURED at HEAD and is frozen in `HEAD_STOCK_REPORT`.
  d. The `danger_tell` arm of `mix-hazardless` cannot be isolated: a non-none
     tell with no hazard term is already contradiction rule C1's kill. That
     arm is therefore pinned by the PRESENCE of the `mix-hazardless` finding
     beside C1's kill, never by the report being otherwise clean.
  e. "fires listing exactly the uncovered terms" is read as ONE finding that
     names every uncovered term and no covered one (the `tier-intro-pacing`
     precedent — one finding naming every offender). If the implementation
     emits one finding per term, only the count assertion needs renegotiating;
     the set assertion holds either way and is asserted separately.
  f. `escalation_budget_recheck` is read off the WRITTEN `lint-report.json`
     ("the lint-report must record ..."), with the in-memory report accepted
     as a fallback. The three legs are driven under `term_budget_action:
     kill`, the arming where both readings of "the lint FAILS" agree; whether
     the re-check also fires under `warn` is NOT pinned here.
  g. The re-prompt is pinned as "exactly one extra turn carrying the
     directive", and the directive itself by PROMPT-SYNC: a new module-level
     constant whose longest placeholder-free run appears in that prompt (the
     way `TIER_TERMS_KILL_SENTENCE` is pinned in `test_b003_tiers_s1`). Its
     wording is not pinned.
  h. R-17's final kill is pinned by its DETAIL (it names the budget and the
     ceiling number), not by a rule id — the contract gives the reason no
     registry id, only "a distinct reason naming the loophole".

This file writes nothing outside `tmp_path`, reads nothing out of `out/`, and
makes no API call: `run_s1` is driven with the injected writer stub the
escalation suite already owns, under b11's no-network / no-agent guard.
"""

from __future__ import annotations

import inspect
import json
from copy import deepcopy
from functools import lru_cache
from itertools import product
from pathlib import Path

import pytest
import yaml

from gen import s1_spec, tiers
from gen.config import REPO_ROOT
from gen.s0_ideas import load_vocab
from gen.s1_spec import run_s1

# The b11 fake-runner guards, adopted the way `test_r2_hotfix6` adopts them:
# no network, no agent session, and nothing written into the repo batch root.
from gen.tests import test_b11_pipeline as b11

# The escalation harness is IMPORTED, never copied (the hotfix7 precedent):
# h6 owns the planted corpus, the writer stub and the reply shape.
from gen.tests import test_r2_hotfix6 as h6

_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched


# --- the contract's frozen names --------------------------------------------

RULE_MIX = "mix-hazardless"
RULE_COVERAGE = "terms-introduced-coverage"
NEW_RULES = (RULE_MIX, RULE_COVERAGE)
ACTIONS = ("off", "warn", "kill")
#: The CANON default (lead correction a'): unconfigured means off.
DEFAULT_ACTION = "off"
#: What the shipped template arms them at, which is NOT the code default.
TEMPLATE_ACTION = "warn"

#: R-17's honesty field and its three legs.
RECHECK_KEY = "escalation_budget_recheck"
RECHECK_RAN, RECHECK_RECONCILED, RECHECK_FAILED = "ran", "reconciled", "failed"
RECHECK_VALUES = (RECHECK_RAN, RECHECK_RECONCILED, RECHECK_FAILED)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "specs"
GOOD_SPEC = FIXTURES / "good-spec.yaml"
IDEA_PATH = FIXTURES / "idea-001.json"
TEMPLATE_CONFIG = REPO_ROOT / "config" / "template.yaml"

#: One real `hazard.`-prefixed vocabulary term, declared AND introduced, so the
#: hazardless fixture trips R-16 rule 1 and nothing else.
HAZARD_TERM = "hazard.timed"
#: Three real vocabulary terms no level introduces — R-16 rule 2's offenders.
UNCOVERED_TERMS = ("move.grid", "gate.plate", "state.wait")
#: The level (0-based) the fixtures hang their extra `terms_introduced` on.
INTRO_LEVEL = 2

#: MEASURED at HEAD (`git show HEAD:gen/s1_spec.py`) for every fixture this
#: file builds: the committed good spec and each mutation below lint CLEAN
#: before this contract. It is the pre-contract report, key for key.
HEAD_STOCK_REPORT = {"passed": True, "kills": [], "warns": [], "spec_hash": ""}

#: `lint_spec`'s PRE-change parameters — anything else is the new knob surface.
HEAD_LINT_PARAMS = ("spec", "vocab", "idea", "tier_policy", "require_render")
#: The PRE-change spelling of the two key registries an override annotation
#: would join house-style, so an addition to either is discoverable by diff.
HEAD_OPTIONAL_GAME_FIELDS = ("render",)
HEAD_KNOB_FIELDS = ("refusal", "goal_legible", "danger_tell", "deceptions")
#: PRE-change uppercase string constants whose value already says "budget" —
#: excluded when hunting for R-17's new directive constant.
HEAD_BUDGET_CONSTANTS = (
    "BUDGET_LINE",
    "SCHEMA_NOTE",
    "CONTRADICTION_NOTE",
    "LINT_SURFACE_NOTES",
    "TIER_TERMS_KILL_SENTENCE",
)

_MISSING = object()


# --- fixtures, built by mutating the committed good spec ---------------------


@lru_cache(maxsize=1)
def _vocab() -> frozenset:
    return frozenset(load_vocab(h6._cfg()))


@lru_cache(maxsize=1)
def _good_text() -> str:
    return GOOD_SPEC.read_text(encoding="utf-8")


def _base() -> dict:
    """The committed §11 good spec, parsed fresh for every caller."""
    return yaml.safe_load(_good_text())


def _idea() -> dict:
    """The committed pilot idea: tier t2, `mix_class.hazardless: true`."""
    return json.loads(IDEA_PATH.read_text(encoding="utf-8"))


def _idea_with(hazardless: object) -> dict:
    """The idea with its `mix_class.hazardless` facet set, or dropped.

    `_MISSING` drops the facet; None drops the whole `mix_class` block.
    """
    idea = _idea()
    if hazardless is None:
        idea.pop("mix_class", None)
    elif hazardless is _MISSING:
        idea["mix_class"].pop("hazardless", None)
    else:
        idea["mix_class"]["hazardless"] = hazardless
    return idea


def _hazard_spec() -> dict:
    """R-16 rule 1's offender: a `hazard.` term, declared AND introduced.

    Introduced deliberately — that keeps `terms-introduced-coverage` silent,
    so the two new rules are never measured through one another.
    """
    spec = _base()
    spec["game"]["terms"].append(HAZARD_TERM)
    spec["game"]["levels"][INTRO_LEVEL]["terms_introduced"].append(HAZARD_TERM)
    return spec


def _tell_spec() -> dict:
    """The `danger_tell` arm: a non-none tell on a hazardless game (reading d —
    contradiction C1 kills this spec too, which is not this rule's business)."""
    spec = _base()
    spec["game"]["knobs"]["danger_tell"] = "unique-hue"
    return spec


def _uncovered_spec() -> dict:
    """R-16 rule 2's offender: three declared terms no level introduces."""
    spec = _base()
    spec["game"]["terms"].extend(UNCOVERED_TERMS)
    return spec


def _overbudget_spec() -> dict:
    """R-17's offender: 9 terms at a t2 ceiling of 8, otherwise §11-clean —
    every declared term is introduced, so neither new rule fires on it."""
    spec = _uncovered_spec()
    spec["game"]["levels"][INTRO_LEVEL]["terms_introduced"].extend(UNCOVERED_TERMS)
    return spec


def _text(spec: dict) -> str:
    return yaml.safe_dump(spec, sort_keys=False)


def _tier_budget() -> int:
    """The signed ceiling for the fixture idea's tier — READ, never retyped."""
    return tiers.DEFAULT_TERM_BUDGETS[_idea()["tier"]]


def _flat(text: str) -> str:
    return " ".join(text.split())


# --- the knob surface, discovered (reading a) --------------------------------


def _snake(rule: str) -> str:
    return rule.replace("-", "_")


def _new_lint_params() -> list[str]:
    parameters = inspect.signature(s1_spec.lint_spec).parameters.values()
    return [
        p.name
        for p in parameters
        if p.name not in HEAD_LINT_PARAMS
        and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
    ]


def _constructions() -> list[tuple]:
    """Every plausible way to hand `lint_spec` the two action knobs."""
    params = _new_lint_params()
    built: list[tuple] = []

    # (b) one keyword per rule, matched on the rule's own tokens.
    per_rule: dict[str, str] = {}
    for rule in NEW_RULES:
        tokens = rule.split("-")
        for name in params:
            low = name.lower()
            if all(token in low for token in tokens) or tokens[-1] in low:
                per_rule.setdefault(rule, name)
                break
    if len(per_rule) == len(NEW_RULES) and len(set(per_rule.values())) == len(NEW_RULES):
        label = "one keyword per rule (" + ", ".join(
            f"{rule}->{name}" for rule, name in per_rule.items()
        ) + ")"
        built.append((label, lambda actions, m=dict(per_rule): {m[r]: a for r, a in actions.items()}))

    # (a) ONE mapping parameter, keyed by the rule ids or their snake spelling.
    for name in params:
        built.append(
            (f"{name}={{'<rule-id>': action}}", lambda actions, n=name: {n: dict(actions)})
        )
        built.append(
            (
                f"{name}={{'<rule_id>': action}}",
                lambda actions, n=name: {n: {_snake(r): a for r, a in actions.items()}},
            )
        )
    return built


def _raw_lint(spec: dict, idea: dict | None, kwargs: dict):
    return s1_spec.lint_spec(spec, _vocab(), idea, None, **kwargs)


@lru_cache(maxsize=1)
def _knob() -> tuple:
    """(label, builder) for the knob surface, or (None, [what was tried]).

    Calibrated on `mix-hazardless`: the winning construction is the one where
    `off` silences the rule, `warn` records it as a warn and `kill` makes it a
    kill. A construction that is merely ACCEPTED is not enough — a mapping
    parameter that ignores unknown keys would be.
    """
    tried: list[str] = []
    if not _new_lint_params():
        return None, ["lint_spec grew no new parameter at all"]
    for label, build in _constructions():
        try:
            off = _raw_lint(_hazard_spec(), _idea(), build(dict.fromkeys(NEW_RULES, "off")))
            warn = _raw_lint(_hazard_spec(), _idea(), build(dict.fromkeys(NEW_RULES, "warn")))
            kill = _raw_lint(_hazard_spec(), _idea(), build(dict.fromkeys(NEW_RULES, "kill")))
        except Exception as exc:  # noqa: BLE001 — a rejected construction is data
            tried.append(f"{label}: {type(exc).__name__}: {exc}")
            continue
        if _findings(off, RULE_MIX) or not _warns_of(warn, RULE_MIX) or not _kills_of(
            kill, RULE_MIX
        ):
            tried.append(f"{label}: accepted, but off/warn/kill did not move {RULE_MIX!r}")
            continue
        return label, build
    return None, tried


def _lint(spec: dict, idea: dict | None = None, *, actions: dict | None = None, policy=None):
    """`lint_spec` with the two knobs set, or left entirely unconfigured."""
    kwargs: dict = {}
    if actions is not None:
        label, build = _knob()
        if label is None:
            pytest.fail(
                f"contract W1-B pin 1: no discoverable off|warn|kill knob surface for "
                f"{list(NEW_RULES)}. `lint_spec` is pure, so the actions must arrive as a "
                f"parameter (the `require_render` precedent). Its new parameters are "
                f"{_new_lint_params()}; what was tried:\n  " + "\n  ".join(build)
            )
        kwargs = build(actions)
    return s1_spec.lint_spec(deepcopy(spec), _vocab(), idea, policy, **kwargs)


def _armed(action: str = "warn") -> dict:
    """Both rules explicitly armed — the knobs default OFF (correction a')."""
    return dict.fromkeys(NEW_RULES, action)


def _findings(report, rule: str) -> list[dict]:
    return [f for f in list(report.kills) + list(report.warns) if f.get("rule") == rule]


def _kills_of(report, rule: str) -> list[dict]:
    return [f for f in report.kills if f.get("rule") == rule]


def _warns_of(report, rule: str) -> list[dict]:
    return [f for f in report.warns if f.get("rule") == rule]


def _rules(report) -> list[str]:
    return [f.get("rule") for f in list(report.kills) + list(report.warns)]


# --- pin 1: the registry, the knobs, the default -----------------------------


def test_pin1_both_rule_ids_live_in_a_module_level_registry() -> None:
    """House style: a new rule gets a stable id in a registry, the way the four
    tier rules sit in `TIER_RULES`."""
    registries = {
        name: value
        for name, value in vars(s1_spec).items()
        if name.isupper() and isinstance(value, (tuple, list, set, frozenset, dict))
    }
    carrying = sorted(name for name, value in registries.items() if all(r in value for r in NEW_RULES))
    assert carrying, (
        f"contract W1-B R-16: {list(NEW_RULES)} must be registered ids, the `TIER_RULES` "
        f"pattern ('every rule gets a stable id'). No module-level registry in gen/s1_spec.py "
        f"names both; the registries present are {sorted(registries)}"
    )


def test_pin1_the_new_rules_stay_out_of_the_closed_kill_list() -> None:
    """`KILL_RULES` is the CLOSED §11 list and b5 pins its exact tuple — a
    policy rule with an action knob is never a member (the contract's own
    house-style line, and the same reasoning `TIER_RULES` carries)."""
    for rule in NEW_RULES:
        assert rule not in s1_spec.KILL_RULES, (
            f"{rule!r} is in KILL_RULES; the contract says new rules follow the TIER_RULES "
            f"registry pattern, NOT the closed KILL_RULES set (b5 pins its exact tuple)"
        )


def test_pin1_the_action_knobs_exist_and_honour_off_warn_kill() -> None:
    """Reading a: the surface is discovered, but its SEMANTICS are the pin."""
    label, build = _knob()
    assert label is not None, (
        f"contract W1-B R-16: each rule needs an off|warn|kill action knob. `lint_spec`'s new "
        f"parameters are {_new_lint_params()}; what was tried:\n  " + "\n  ".join(build)
    )


@pytest.mark.parametrize(
    ("make_spec", "rule"),
    [(_hazard_spec, RULE_MIX), (_uncovered_spec, RULE_COVERAGE)],
    ids=list(NEW_RULES),
)
def test_pin1_unconfigured_is_the_pre_contract_report_on_a_would_be_offender(
    make_spec, rule: str
) -> None:
    """THE STRONGEST REGRESSION PIN (lead correction a'): the knobs default
    OFF, so a spec that WOULD trigger the rule lints byte-for-byte as it did
    before this contract while nothing arms it.

    This is the pin `test_b003_render`'s shipped-spec replay depends on: it
    re-lints every shipped spec unconfigured and demands its stored report
    back. Convoy-in-the-fog and core-ward-phase-gates — R-16's own audit
    evidence — are exactly the specs that would fire warn-by-default.
    """
    bare = _lint(make_spec(), _idea())
    explicit_off = _lint(make_spec(), _idea(), actions=_armed(DEFAULT_ACTION))
    assert bare.to_json_dict() == HEAD_STOCK_REPORT, (
        f"unconfigured, {rule!r} must not fire at all: the knob's canon default is "
        f"{DEFAULT_ACTION!r} and the report must be the pre-contract one (measured at HEAD: "
        f"{HEAD_STOCK_REPORT}), got {bare.to_json_dict()}"
    )
    assert bare.to_json_dict() == explicit_off.to_json_dict(), (
        f"an unconfigured lint must equal an explicit {DEFAULT_ACTION!r}.\n"
        f"  unconfigured: {bare.to_json_dict()}\n  explicit:     {explicit_off.to_json_dict()}"
    )


@pytest.mark.parametrize(
    ("make_spec", "rule"),
    [(_hazard_spec, RULE_MIX), (_uncovered_spec, RULE_COVERAGE)],
    ids=list(NEW_RULES),
)
def test_pin1_warn_records_the_finding_without_failing_the_spec(make_spec, rule: str) -> None:
    """Armed at warn (the template's setting): the rule fires, as a warn."""
    report = _lint(make_spec(), _idea(), actions=_armed("warn"))
    assert _warns_of(report, rule), (
        f"{rule!r} armed at 'warn' must fire on its own offender; the report carried "
        f"{_rules(report)}"
    )
    assert not _kills_of(report, rule), f"{rule!r} at 'warn' is never a kill"
    assert report.passed, f"a {rule!r} warn may not fail the spec: {report.kills}"


@pytest.mark.parametrize(
    ("make_spec", "rule"),
    [(_hazard_spec, RULE_MIX), (_uncovered_spec, RULE_COVERAGE)],
    ids=list(NEW_RULES),
)
def test_pin1_off_restores_the_pre_contract_report_exactly(make_spec, rule: str) -> None:
    """Reading c: both offenders lint CLEAN at HEAD (measured). With the knobs
    off, they must lint clean still — nothing else may have moved."""
    report = _lint(make_spec(), _idea(), actions=_armed("off"))
    assert report.to_json_dict() == HEAD_STOCK_REPORT, (
        f"with both knobs 'off' this spec must lint exactly as it did before contract W1-B "
        f"(measured at HEAD: {HEAD_STOCK_REPORT}), got {report.to_json_dict()}"
    )


@pytest.mark.parametrize(
    ("make_spec", "rule"),
    [(_hazard_spec, RULE_MIX), (_uncovered_spec, RULE_COVERAGE)],
    ids=list(NEW_RULES),
)
def test_pin1_kill_arms_the_rule_as_a_real_kill(make_spec, rule: str) -> None:
    report = _lint(make_spec(), _idea(), actions=_armed("kill"))
    assert _kills_of(report, rule), (
        f"the {rule!r} knob set to 'kill' must put the finding in kills; the report carried "
        f"{_rules(report)}"
    )
    assert not report.passed, "`passed` is exactly `kills == []`"


def test_pin1_template_config_ships_both_knobs_set_to_warn() -> None:
    """R-16: 'template.yaml gains the two knobs, commented, set warn.'

    The CODE default is off (correction a'); the shipped template ARMS both at
    warn, which is how a batch measures the kill rate before arming further.
    The KEY SPELLING is the implementer's; what is pinned is that a knob whose
    name carries the rule's own tokens is present and its value is 'warn'.
    """
    raw = TEMPLATE_CONFIG.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    found: dict[str, list[str]] = {rule: [] for rule in NEW_RULES}

    def walk(node, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                name = str(key).lower().replace("-", "_")
                for rule, needles in (
                    (RULE_MIX, ("hazardless",)),
                    (RULE_COVERAGE, ("coverage", "introduced")),
                ):
                    if any(needle in name for needle in needles) and value == TEMPLATE_ACTION:
                        found[rule].append(f"{trail}{key}")
                walk(value, f"{trail}{key}.")
        elif isinstance(node, list):
            for item in node:
                walk(item, trail)

    walk(parsed, "")
    for rule, hits in found.items():
        assert hits, (
            f"config/template.yaml must ship {rule!r}'s action knob set to {TEMPLATE_ACTION!r} "
            f"(R-16: 'template.yaml gains the two knobs, commented, set warn'). No key naming "
            f"that rule carries the value {TEMPLATE_ACTION!r}"
        )
    for rule in NEW_RULES:
        assert rule in raw or _snake(rule) in raw, (
            f"the knob must be COMMENTED — {rule!r} does not appear anywhere in "
            f"config/template.yaml, so a reader cannot tell what the knob arms"
        )


# --- pin 2: mix_class fidelity ----------------------------------------------


def test_pin2_mix_hazardless_fires_on_a_declared_hazard_term() -> None:
    """The convoy-in-the-fog defect: `hazardless: true` shipped beside
    `loss.deadlock`, and no lint rule ever read the facet."""
    report = _lint(_hazard_spec(), _idea(), actions=_armed())
    findings = _findings(report, RULE_MIX)
    assert findings, (
        f"an idea with mix_class.hazardless=true whose spec declares {HAZARD_TERM!r} must trip "
        f"{RULE_MIX!r} (R-16 (a): `hazardless` was read at s1_spec.py:2177 to print a prompt "
        f"facet and by NO lint rule). The report carried {_rules(report)}"
    )
    detail = " ".join(f.get("detail", "") for f in findings)
    assert HAZARD_TERM in detail or "hazardless" in detail.lower(), (
        f"the finding must name what it caught — the offending term or the facet; got {detail!r}"
    )


def test_pin2_mix_hazardless_fires_on_a_non_none_danger_tell() -> None:
    """R-16 rule 1's second half. Reading d: C1 kills this spec too, so only
    the PRESENCE of the fidelity finding is pinned, never a clean report."""
    report = _lint(_tell_spec(), _idea(), actions=_armed())
    assert _findings(report, RULE_MIX), (
        f"a hazardless idea whose spec declares a non-'none' danger_tell must trip "
        f"{RULE_MIX!r} ('the spec may not declare any HAZARD_PREFIXES term NOR a non-none "
        f"danger_tell'). The report carried {_rules(report)}"
    )


@pytest.mark.parametrize(
    ("hazardless", "why"),
    [
        (False, "the idea says the game HAS hazards"),
        (_MISSING, "the idea declares no `hazardless` facet"),
        (None, "the idea carries no `mix_class` block at all"),
    ],
    ids=["hazardless-false", "facet-absent", "mix_class-absent"],
)
def test_pin2_mix_hazardless_is_silent_without_the_claim(hazardless: object, why: str) -> None:
    """The absent-facet pattern `_idea_tier` already sets: silent on EVERY
    absence, so a pipeline that never made the claim lints as it always did."""
    report = _lint(_hazard_spec(), _idea_with(hazardless), actions=_armed())
    assert not _findings(report, RULE_MIX), (
        f"{RULE_MIX!r} may only fire on a spec whose idea DECLARES hazardless=true — here {why}; "
        f"got {_findings(report, RULE_MIX)}"
    )


def test_pin2_mix_hazardless_is_silent_without_an_idea() -> None:
    """`lint_spec(spec, vocab)` — the call b5's whole fixture suite makes — has
    no idea to read the claim from, so the rule cannot fire in it."""
    report = _lint(_hazard_spec(), actions=_armed())
    assert not _findings(report, RULE_MIX), (
        f"{RULE_MIX!r} reads `idea.mix_class.hazardless`; with no idea it must be silent "
        f"(the tier rules' own absent-input pattern). Got {_findings(report, RULE_MIX)}"
    )
    assert report.to_json_dict() == HEAD_STOCK_REPORT, (
        f"and the report must be the pre-contract one, measured at HEAD: got "
        f"{report.to_json_dict()}"
    )


def _override_candidates() -> list[tuple]:
    """(placement, key, value) triples to try as "an explicit declared override".

    Reading b: seeded from the implementation's OWN new names first — a field
    added to `OPTIONAL_GAME_FIELDS` or `KNOB_FIELDS`, or a new `*OVERRIDE*` /
    `*EXEMPT*` string constant — then literal guesses.
    """
    keys: list[str] = []
    keys += [f for f in s1_spec.OPTIONAL_GAME_FIELDS if f not in HEAD_OPTIONAL_GAME_FIELDS]
    keys += [f for f in s1_spec.KNOB_FIELDS if f not in HEAD_KNOB_FIELDS]
    for name, value in vars(s1_spec).items():
        if not name.isupper() or not isinstance(value, str) or name == "OVERRIDE_HEADER":
            continue
        if ("OVERRIDE" in name or "EXEMPT" in name) and value and " " not in value and len(value) <= 40:
            keys.append(value)
    keys += [
        "hazardless_override",
        "hazardless_exemption",
        "mix_class_override",
        "mix_override",
        "hazard_override",
        "lint_override",
        "lint_overrides",
        "lint_exempt",
        "exempt_rules",
        "overrides",
    ]
    values = [True, RULE_MIX, [RULE_MIX], "signed: the hazard IS this game's deception"]
    seen: set[str] = set()
    ordered = [k for k in keys if not (k in seen or seen.add(k))]
    return list(product(("game", "knobs", "spec"), ordered, values))


def test_pin2_a_declared_override_silences_the_rule() -> None:
    """R-16: '...unless the spec carries an explicit declared override'.

    Guarded against a vacuous pass two ways: the un-annotated fixture must
    FIRE first, and an annotation only counts as the override if the spec is
    still otherwise clean — silencing the rule by breaking the spec is not an
    override.
    """
    assert _findings(_lint(_hazard_spec(), _idea(), actions=_armed()), RULE_MIX), (
        "this pin is only meaningful while the un-annotated fixture trips the rule"
    )
    tried: list[str] = []
    for placement, key, value in _override_candidates():
        spec = _hazard_spec()
        target = {"game": spec["game"], "knobs": spec["game"]["knobs"], "spec": spec}[placement]
        target[key] = value
        try:
            report = _lint(spec, _idea(), actions=_armed())
        except Exception as exc:  # noqa: BLE001 — a rejected annotation is data
            tried.append(f"{placement}.{key} = {value!r}: {type(exc).__name__}: {exc}")
            continue
        if not _findings(report, RULE_MIX) and not report.kills:
            return
        tried.append(f"{placement}.{key} = {value!r}")
    pytest.fail(
        f"contract W1-B R-16 rule 1: a spec carrying an explicit declared override must silence "
        f"{RULE_MIX!r}. No annotation this file can reach does. The override surface is the "
        f"implementer's design (reading b) — if it is neither a `game`/`knobs` annotation nor a "
        f"name reachable from OPTIONAL_GAME_FIELDS / KNOB_FIELDS / a new *OVERRIDE* constant, "
        f"this pin needs the real spelling. Tried {len(tried)} annotations:\n  "
        + "\n  ".join(tried[:24])
    )


def test_pin2_is_silent_on_the_shipped_hazardless_spec() -> None:
    """The committed good spec IS the hazardless case done right (no hazard
    term, `danger_tell: none`): the rule may not fire on obedience."""
    report = _lint(_base(), _idea(), actions=_armed())
    assert not _findings(report, RULE_MIX), (
        f"{RULE_MIX!r} fired on a hazardless spec that declares no hazard term and "
        f"`danger_tell: none` — exactly what contradiction rule C1 FORCES. Got "
        f"{_findings(report, RULE_MIX)}"
    )


# --- pin 3: the reverse containment -----------------------------------------


def test_pin3_coverage_fires_naming_exactly_the_uncovered_terms() -> None:
    """R-16 (b): §11 enforces `terms_introduced ⊆ game.terms` (s1_spec.py:418)
    and never the reverse — 12 declared terms across 3 games are introduced by
    no level."""
    spec = _uncovered_spec()
    report = _lint(spec, _idea(), actions=_armed())
    findings = _findings(report, RULE_COVERAGE)
    assert findings, (
        f"{RULE_COVERAGE!r} must fire: {list(UNCOVERED_TERMS)} are declared in game.terms and "
        f"introduced by no level. The report carried {_rules(report)}"
    )
    detail = " ".join(f.get("detail", "") for f in findings)
    missing = [term for term in UNCOVERED_TERMS if term not in detail]
    assert not missing, (
        f"the finding must list EXACTLY the uncovered terms; {missing} are not named in "
        f"{detail!r}"
    )
    covered = [term for term in _base()["game"]["terms"] if term in detail]
    assert not covered, (
        f"the finding names {covered}, which every level DOES introduce — 'exactly the "
        f"uncovered terms' means no false accusation rides along: {detail!r}"
    )


def test_pin3_coverage_is_one_finding_for_all_offenders() -> None:
    """Reading e — the `tier-intro-pacing` precedent (one finding naming every
    offender). Renegotiable: the set pin above holds either way."""
    findings = _findings(_lint(_uncovered_spec(), _idea(), actions=_armed()), RULE_COVERAGE)
    assert len(findings) == 1, (
        f"{RULE_COVERAGE!r} should raise ONE finding listing every uncovered term, the way "
        f"`tier-intro-pacing` raises one finding naming every offending level; got "
        f"{len(findings)}: {findings}"
    )


def test_pin3_coverage_is_silent_when_every_term_is_introduced() -> None:
    """The committed good spec introduces all six of its terms across levels
    1, 2 and 5 — the rule may not fire on it, with or without an idea."""
    for idea in (None, _idea()):
        report = _lint(_base(), idea, actions=_armed())
        assert not _findings(report, RULE_COVERAGE), (
            f"{RULE_COVERAGE!r} fired on a spec whose every declared term IS introduced "
            f"(idea={'present' if idea else 'absent'}): {_findings(report, RULE_COVERAGE)}"
        )


def test_pin3_coverage_needs_no_idea() -> None:
    """The reverse containment is a property of the SPEC alone — unlike
    `mix-hazardless` it has nothing to read off the idea."""
    report = _lint(_uncovered_spec(), actions=_armed())
    assert _findings(report, RULE_COVERAGE), (
        f"{RULE_COVERAGE!r} compares game.terms against the levels' terms_introduced and needs "
        f"no idea; it stayed silent on `lint_spec(spec, vocab)`. Report: {_rules(report)}"
    )


def test_pin3_the_two_rules_never_measure_each_other() -> None:
    """Fixture hygiene, asserted rather than assumed: the hazard fixture
    introduces its term and the coverage fixture declares no hazard."""
    assert not _findings(_lint(_hazard_spec(), _idea(), actions=_armed()), RULE_COVERAGE)
    assert not _findings(_lint(_uncovered_spec(), _idea(), actions=_armed()), RULE_MIX)


def test_pin3_lint_spec_stays_pure() -> None:
    """Same inputs, same report; and neither the spec nor the idea is mutated."""
    spec, idea = _uncovered_spec(), _idea()
    before_spec, before_idea = deepcopy(spec), deepcopy(idea)
    first = s1_spec.lint_spec(spec, _vocab(), idea).to_json_dict()
    second = s1_spec.lint_spec(spec, _vocab(), idea).to_json_dict()
    assert first == second, "two lints of one spec must agree"
    assert spec == before_spec, "lint_spec must not mutate the spec it reads"
    assert idea == before_idea, "lint_spec must not mutate the idea it reads"


# --- pin 4: R-17, the budget re-check after an escalation respec --------------


def _budget_cfg(action: str = "kill") -> dict:
    """The pilot config with the signed term budgets armed."""
    cfg = h6._cfg()
    cfg["tiers"] = {"term_budget": True, "term_budget_action": action}
    return cfg


def _escalate(tmp_path: Path, replies: list[str], cfg: dict) -> tuple:
    """One escalated re-spec, driven the way `test_r2_hotfix7` drives it."""
    planted = h6._plant_corpus(tmp_path)
    log: list[str] = []
    result = run_s1(
        h6.IDEA_PATH,
        cfg,
        writer_runner=h6._writer([h6._reply(text) for text in replies], log),
        out_root=tmp_path,
        escalation=planted["report"],
    )
    assert Path(result.out_dir).resolve().is_relative_to(tmp_path.resolve()), (
        f"every artifact of this suite lands under tmp_path; got {result.out_dir}"
    )
    return result, log, planted


def _recheck(result) -> object:
    """Reading f: `escalation_budget_recheck` off the WRITTEN lint-report."""
    written = json.loads(
        (Path(result.out_dir) / "lint-report.json").read_text(encoding="utf-8")
    )
    if RECHECK_KEY in written:
        return written[RECHECK_KEY]
    value = getattr(result.report, RECHECK_KEY, _MISSING)
    if value is not _MISSING:
        return value
    pytest.fail(
        f"contract W1-B R-17: 'the lint-report must record `{RECHECK_KEY}` (ran / reconciled / "
        f"failed) so reports are honest about which path a spec took'. The written report "
        f"carries {sorted(written)} and the LintReport has no such attribute"
    )


def test_pin4_a_rewrite_inside_the_budget_records_that_the_recheck_ran(tmp_path: Path) -> None:
    """The quiet leg: nothing to reconcile, but the report still says so."""
    result, log, _ = _escalate(tmp_path, [_text(_base())], _budget_cfg())
    assert len(log) == 1, f"a rewrite inside its budget buys no extra turn; got {len(log)}"
    assert result.report.passed, f"the rewrite is §11-clean and within budget: {result.report.kills}"
    assert _recheck(result) == RECHECK_RAN, (
        f"a rewrite that never exceeded its tier budget records {RECHECK_RAN!r}; got "
        f"{_recheck(result)!r}"
    )


def test_pin4_an_over_budget_rewrite_is_reprompted_once_and_reconciles(tmp_path: Path) -> None:
    """R-17's whole point: the loophole is closed by a reconciliation prompt,
    'never a bare bar that deadlocks declare-it against you're-over-budget'."""
    budget = _tier_budget()
    over = _overbudget_spec()
    assert len(over["game"]["terms"]) > budget, "fixture: the rewrite must exceed its tier budget"

    result, log, planted = _escalate(
        tmp_path, [_text(over), _text(_base())], _budget_cfg()
    )

    assert len(log) == 2, (
        f"the over-budget rewrite is re-prompted ONCE ('re-prompted ONCE with an explicit "
        f"budget-reconciliation directive'); the writer saw {len(log)} turns"
    )
    assert result.report.passed, (
        f"the reconciled rewrite is within budget and must stand as the verdict: "
        f"{result.report.kills}"
    )
    assert len(result.spec["game"]["terms"]) <= budget
    assert _recheck(result) == RECHECK_RECONCILED, (
        f"a rewrite that went over budget and then folded back records "
        f"{RECHECK_RECONCILED!r}; got {_recheck(result)!r}"
    )
    assert Path(result.out_dir).resolve() == planted["corpus"].resolve(), (
        f"a reconciled rewrite passes, so it lands IN PLACE; got {result.out_dir}"
    )


def test_pin4_the_reconciliation_prompt_is_a_prompt_synced_named_constant(tmp_path: Path) -> None:
    """Reading g: the directive is a named module constant (the way
    `TIER_TERMS_KILL_SENTENCE` is), and it is what the re-prompt carries."""
    budget = _tier_budget()
    _, log, _ = _escalate(tmp_path, [_text(_overbudget_spec()), _text(_base())], _budget_cfg())
    assert len(log) >= 2, "no re-prompt was issued at all"
    directive = log[1]

    constants = {
        name: value
        for name, value in vars(s1_spec).items()
        if name.isupper()
        and isinstance(value, str)
        and name not in HEAD_BUDGET_CONSTANTS
        and "budget" in value.lower()
    }
    assert constants, (
        "R-17: 'add the directive line as a named constant, prompt-synced the way "
        "TIER_TERMS_KILL_SENTENCE is'. gen/s1_spec.py grew no new module-level string constant "
        "that mentions the budget"
    )

    flat = _flat(directive)
    synced = []
    for name, value in constants.items():
        stem = max(_flat(value).split("{"), key=len)
        stem = stem.split("}")[-1].strip()
        if stem and stem in flat:
            synced.append(name)
    assert synced, (
        f"the re-prompt must be built FROM the named directive constant (prompt-sync: one "
        f"sentence, two consumers). None of {sorted(constants)} has a placeholder-free run "
        f"inside the re-prompt. Its tail was: {directive[-400:]!r}"
    )
    assert str(budget) in directive, (
        f"the reconciliation directive must state the ceiling it is asking the rewrite to fold "
        f"to ({budget}); the re-prompt never names it"
    )


def test_pin4_a_rewrite_that_stays_over_budget_is_killed(tmp_path: Path) -> None:
    """THE TRAP PIN, from the facing-sentinel record: a stored lint-report that
    says `passed: true` while a fresh authorship lint kills the spec."""
    budget = _tier_budget()
    over = _text(_overbudget_spec())
    result, log, planted = _escalate(tmp_path, [over, over], _budget_cfg())

    assert 2 <= len(log) <= 3, f"one reconciliation turn, then the verdict stands; got {len(log)}"
    assert not result.report.passed, (
        f"R-17: 'if the second attempt is still over budget, the lint FAILS (a real kill)'. The "
        f"rewrite declares {len(result.spec['game']['terms'])} terms against a tier budget of "
        f"{budget} and the report says passed={result.report.passed}"
    )
    named = [
        kill
        for kill in result.report.kills
        if "budget" in kill.get("detail", "").lower() and str(budget) in kill.get("detail", "")
    ]
    assert named, (
        f"the kill needs 'a distinct reason naming the loophole' — one that names the budget and "
        f"the ceiling {budget} (reading h: the rule id is not pinned). Got {result.report.kills}"
    )
    assert _recheck(result) == RECHECK_FAILED, (
        f"a rewrite still over budget after its reconciliation turn records {RECHECK_FAILED!r}; "
        f"got {_recheck(result)!r}"
    )
    out_dir = Path(result.out_dir)
    assert out_dir.parent.name == s1_spec.KILLED_DIRNAME, (
        f"a KILLED escalated rewrite is evidence under {s1_spec.KILLED_DIRNAME}/ and must never "
        f"evict the live spec (hotfix #7's standing behavior); got {out_dir}"
    )
    assert planted["spec"].read_text(encoding="utf-8").strip().endswith("the REJECTED draft"), (
        "the live spec's bytes must survive an R-17 kill untouched"
    )


def test_pin4_the_recheck_uses_the_full_policy_not_the_escalation_one(tmp_path: Path) -> None:
    """The mechanism, pinned as a fact about the two policies: the escalated
    lint really does run with the budget off (`escalation_lint_policy`), so the
    kill above can only come from a SECOND, budget-only pass."""
    policy = tiers.TierPolicy(term_budget=dict(tiers.DEFAULT_TERM_BUDGETS), term_budget_action="kill")
    stripped = s1_spec.escalation_lint_policy(policy)
    assert stripped.term_budget is None, (
        "escalation_lint_policy must still switch the budget off at authorship — R-17 adds a "
        "re-check, it does not revoke the b003 Addendum 11 adjudication"
    )
    assert _lint(_overbudget_spec(), _idea(), policy=stripped).passed, (
        "the 9-term rewrite passes the escalated lint — that IS the loophole R-17 closes"
    )
    assert not _lint(_overbudget_spec(), _idea(), policy=policy).passed, (
        "and the same spec is killed by a fresh authorship lint (the facing-sentinel record)"
    )


def test_pin4_no_tier_policy_means_no_recheck_and_no_change(tmp_path: Path) -> None:
    """A config that never heard of `tiers:` escalates exactly as it did before
    this contract — measured at HEAD: 9 terms, one turn, passed."""
    cfg = h6._cfg()
    assert "tiers" not in cfg, "fixture drift: the pilot config must carry no tiers block"
    result, log, _ = _escalate(tmp_path, [_text(_overbudget_spec())], cfg)
    assert len(log) == 1, f"no budget, no reconciliation turn; got {len(log)}"
    assert result.report.passed, f"unchanged pre-contract behavior: {result.report.kills}"
    written = json.loads(
        (Path(result.out_dir) / "lint-report.json").read_text(encoding="utf-8")
    )
    assert written.get(RECHECK_KEY, RECHECK_RAN) in RECHECK_VALUES, (
        f"when the field is written at all it must hold one of {list(RECHECK_VALUES)}; got "
        f"{written.get(RECHECK_KEY)!r}"
    )


def test_pin4_the_recorded_value_is_always_one_of_the_three(tmp_path: Path) -> None:
    """The field is an enum, not free text — reports have to be comparable."""
    result, _, _ = _escalate(tmp_path, [_text(_base())], _budget_cfg())
    assert _recheck(result) in RECHECK_VALUES, (
        f"`{RECHECK_KEY}` must be one of {list(RECHECK_VALUES)}; got {_recheck(result)!r}"
    )


# --- pin 5: the stock path is untouched --------------------------------------


@pytest.mark.parametrize(
    ("with_idea", "with_policy"),
    [(False, False), (True, False), (True, True)],
    ids=["spec-only", "spec+idea", "spec+idea+budget"],
)
def test_pin5_the_stock_lint_path_is_byte_identical(with_idea: bool, with_policy: bool) -> None:
    """The regression pin. The committed good spec trips NEITHER new rule — six
    terms, all introduced; hazardless with no hazard term and `danger_tell:
    none` — so its report must be the one measured at HEAD, key for key."""
    policy = (
        tiers.TierPolicy(term_budget=dict(tiers.DEFAULT_TERM_BUDGETS), term_budget_action="kill")
        if with_policy
        else None
    )
    report = _lint(_base(), _idea() if with_idea else None, policy=policy)
    assert report.to_json_dict() == HEAD_STOCK_REPORT, (
        f"contract W1-B pin 5: a spec that triggers none of the new rules must lint exactly as "
        f"it did before (measured at HEAD: {HEAD_STOCK_REPORT}); got {report.to_json_dict()}"
    )


def test_pin5_the_report_gains_no_new_keys_on_the_stock_path() -> None:
    """Reading c, stated on its own so a failure names the right cause: the
    R-17 honesty field belongs to the escalation path, not to every report."""
    keys = set(_lint(_base(), _idea()).to_json_dict())
    assert keys == set(HEAD_STOCK_REPORT), (
        f"the stock lint-report's keys are frozen at {sorted(HEAD_STOCK_REPORT)}; got "
        f"{sorted(keys)}. `{RECHECK_KEY}` is recorded on the ESCALATION path"
    )


def test_pin5_unconfigured_and_both_knobs_off_agree_on_a_clean_spec() -> None:
    """The knobs may not perturb a spec that trips neither rule, whichever way
    a batch configures them."""
    bare = _lint(_base(), _idea()).to_json_dict()
    for action in ACTIONS:
        configured = _lint(_base(), _idea(), actions=_armed(action)).to_json_dict()
        assert configured == bare, (
            f"with the knobs at {action!r} a non-triggering spec must lint identically to an "
            f"unconfigured run; got {configured} vs {bare}"
        )


def test_pin5_the_shipped_fixture_still_passes_every_section_11_rule() -> None:
    """A guard on this whole file: if the good spec ever stops linting clean,
    every measured baseline above is stale and must be re-measured, not
    adapted."""
    report = _lint(_base(), _idea())
    assert report.passed and not report.warns, (
        f"gen/tests/fixtures/specs/good-spec.yaml no longer lints clean — the HEAD baselines in "
        f"this file were measured against it. kills={report.kills} warns={report.warns}"
    )
