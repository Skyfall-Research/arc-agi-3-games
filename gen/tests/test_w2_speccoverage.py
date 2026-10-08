"""Blind pins for contract W2-D — R-25 docs close + spec-side role coverage.

Run: .venv/bin/python -m pytest gen/tests/test_w2_speccoverage.py -v

Written from the frozen W2-D contract ALONE. No line of the implementer's
in-progress `gen/s1_spec.py`, `gen/s3_visual.py` or `gen/visual_canon.py` was
read: the pre-state is `git show HEAD:...` (HEAD = the wave-1 close commit
`af12122`), where the `FIDELITY_RULES` registry (W1-B / R-16) and the
`role-footprint` check (W1-A1 / R-02) are both already stable, landed surfaces.
Everything else this file leans on is landed and committed: the synthetic
visual-card harness in `test_w1_floorfootprint`, the template reader roster in
`test_docs_template`, and the committed `fixtures/specs/good-spec.yaml`.
These pins therefore describe the contract, not the implementation, and the
contract-bearing ones are expected to FAIL at HEAD and pass once W2-D lands.

THE FIVE PINS, in the contract's own order

  1. `game.palette.tiny_token` schema matrix — absent is SILENCE (the
     unconfigured report is byte-identical to HEAD's); a non-empty list of
     distinct roles drawn from (you, goal, danger) is accepted; an empty list,
     a duplicated role, an unknown role and a non-list are each a schema KILL
     naming the field. This is the `palette.background` / `hazardless_override`
     precedent the contract names: a key written down is a declaration and is
     held to one.
  2. `role-footprint` reads the declaration — a sub-floor role a spec declares
     in `palette.tiny_token` reports status `exempt-declared` with its
     MEASUREMENT still printed and no longer fails the check; a sub-floor role
     the declaration does NOT name still fails; and the operator override
     `gate.role_footprint_exempt` keeps working exactly as it did at HEAD.
  3. `unstated-background` — a THIRD `FIDELITY_RULES` entry (off|warn|kill,
     DEFAULT OFF), so an unconfigured lint of a background-silent spec is
     byte-identical to the pre-contract one (the parity pattern that six of the
     seven shipped specs make load-bearing); armed at `warn` it fires on a spec
     with no `game.palette.background`, naming the canon default and
     field-index; armed at `kill` it refuses; a spec that declares a background
     is silent either way.
  4. `config/template.yaml` arms it at `warn` and the config readers still
     accept the template (the reader roster of `test_docs_template`, extended
     locally with the fidelity-rule and role-footprint readers).
  5. `gen/visual_canon.py`'s hazardless note states BOTH official figures — a
     source-text pin on the numbers 11 and 16 appearing together near a
     `hazardless` mention, never on the prose around them.

Readings this file had to resolve. Each is quoted in the failure message of the
pin that depends on it, and each is a line to renegotiate, not a fact:

  a. THE TINY-TOKEN KILL IS PINNED BY ITS DETAIL, NOT BY A RULE ID. HEAD's
     `_schema_palette` emits every palette schema violation under the rule id
     `schema` (a member of the closed `KILL_RULES` tuple that b5 pins exactly),
     and the contract says "a schema kill" without minting a new id. So each
     malformed shape is pinned as `passed is False` plus a KILL whose detail
     names `tiny_token`; which id carries it is not pinned.
  b. "distinct roles from (you, goal, danger)" is read as the contract writes
     it — `background` is a palette role but NOT a tiny-token role, so
     `tiny_token: [background]` is pinned as a kill. `gen/s3_visual.py`'s
     `FOOTPRINT_ROLES` is exactly that triple at HEAD and is read, not retyped.
  c. `tiny_token: null` is NOT pinned. "absent = silence; present must be a
     non-empty list" reads as a kill, but `palette.danger: null` is a §11 value
     in this schema and the contract does not say which way null falls. The
     five unambiguous malformed shapes are pinned instead.
  d. THE DECLARATION IS READ OFF THE SPEC, THROUGH THE PUBLIC SEAM. Pin 2
     drives `build_visual_card(spec_dir, cfg)` over a synthetic slot rather
     than `_role_footprint_check` directly, so HOW the check receives the
     declaration (the `palette` mapping it already takes, or a new parameter)
     stays the implementer's business. Only the reported status is pinned.
  e. `exempt-declared` is compared NORMALISED (case-folded, `_` and `-` are one
     separator), so `exempt_declared` passes. The operator override's own
     status is pinned only as "an exempt word, and not a fail" — the contract
     changes nothing about it and HEAD reports `exempt`.
  f. A tiny_token declaration naming a role that is ALREADY above the floor is
     not pinned: the contract says the check "reads it as the spec-side
     exemption" without saying whether a passing role reports `pass` or
     `exempt-declared`, and either is honest.
  g. PROMPT SYNC. "reuse the registry, reader and prompt-sync machinery W1-B
     built" is read as W1-B's own doctrine: a rule ARMED TO KILL is quoted to
     the writer it will judge. So `fidelity_section({rule: "kill"})` must
     return a section mentioning the background, and `fidelity_section(None)`
     must still be None (the byte-identical prompt). The WORDING is not pinned.
  h. "byte-identical" is read as the W1-B blind file reads it: equality of the
     report's CONTENT (`to_json_dict()`), which is what a byte-identical
     `lint-report.json` means. `HEAD_STOCK_REPORT` below was MEASURED at HEAD.
  i. The config key that arms the rule is READ from `FIDELITY_ACTION_KEYS`,
     never retyped, so the registry's own `<rule id with underscores>_action`
     convention is the single source of truth for pin 4.
  j. Pin 5's window is +/-20 SOURCE LINES around a `hazardless` mention. It was
     calibrated at HEAD: a 30-line window there still contains `11` and never
     `16`, so the pin cannot pass on HEAD's text by accident.

Part 1's other two deliverables — the same two-figure note in
`docs/RUNBOOK.md`'s config section and in `config/template.yaml`'s mix comment
— are NOT pinned here: the contract's BLIND paragraph scopes pin 5 to
`visual_canon`, and they are named in the implementer's VERIFICATION list.

HYGIENE: tmp_path only, `out/` is read and never written, no API call, nothing
written into the repo tree.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from gen import s1_spec, s3_visual
from gen.config import REPO_ROOT, load_config
from gen.s0_ideas import load_vocab

# The landed harnesses are IMPORTED, never copied (the hotfix7 precedent):
# `test_w1_floorfootprint` owns the synthetic visual-card slot and its tolerant
# card readers, `test_docs_template` owns the template copy + reader roster.
from gen.tests import test_docs_template as dt
from gen.tests import test_w1_floorfootprint as ff

# --- locations ---------------------------------------------------------------

ROOT = Path(REPO_ROOT)
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "specs"
GOOD_SPEC = FIXTURES / "good-spec.yaml"
PILOT_CONFIG = ROOT / "config" / "b001-pilot.yaml"
TEMPLATE_PATH = ROOT / "config" / "template.yaml"
VISUAL_CANON_SOURCE = ROOT / "gen" / "visual_canon.py"
CORPUS_ROOT = ROOT / "out" / "corpus"

# --- the contract's frozen names ---------------------------------------------

#: Part 2(b)'s rule id, spelled by the contract.
RULE_UNSTATED_BACKGROUND = "unstated-background"
#: Part 2(a)'s spec field, under `game.palette`.
TINY_TOKEN_KEY = "tiny_token"
#: Part 2(a)'s new `role-footprint` status.
EXEMPT_DECLARED = "exempt-declared"
#: W1-B's action enum and its canon default, which the third rule joins.
ACTIONS = ("off", "warn", "kill")
DEFAULT_ACTION = "off"
#: What `config/template.yaml` arms the new rule at — NOT the code default.
TEMPLATE_ACTION = "warn"

# --- HEAD's frozen surface (git show HEAD:..., never the working file) -------

#: `gen/s1_spec.FIDELITY_RULES` at HEAD. The third rule JOINS this tuple; a
#: member that vanished would be a W1-B regression, so both are pinned present.
HEAD_FIDELITY_RULES = ("mix-hazardless", "terms-introduced-coverage")
#: MEASURED at HEAD for `fixtures/specs/good-spec.yaml`, which declares NO
#: `palette.background` — the pre-contract report, key for key.
HEAD_STOCK_REPORT = {"passed": True, "kills": [], "warns": [], "spec_hash": ""}
#: MEASURED at HEAD: a 1-px `you` under the conservative 4-px floor reports
#: `fail`, with or without a `palette.tiny_token` declaration beside it. Pin 2
#: is the change of exactly this reading.
HEAD_SUBFLOOR_STATUS = "fail"
#: The gate keys pin 2 writes. All three are HEAD members of `s3_visual.GATE_KEYS`
#: (the closed key set `visual_card_mode` validates), so the cfg below is one
#: the pre-contract reader already accepts.
GATE_CARD_KEY = "visual_card"
GATE_FOOTPRINT_KEY = "role_footprint"
GATE_EXEMPT_KEY = "role_footprint_exempt"

_MISSING = object()


# --- tolerant readers --------------------------------------------------------


def _norm(text: object) -> str:
    """Backtick-, case- and separator-insensitive text.

    `tiny_token`, `tiny-token` and `Tiny Token` are one name, which is what
    lets every pin below quote the contract's spelling without pinning the
    implementer's.
    """
    flat = str(text).replace("`", "")
    flat = re.sub(r"[-_]+", " ", flat)
    return re.sub(r"\s+", " ", flat).strip().lower()


def _findings(report) -> list[dict]:
    return list(report.kills) + list(report.warns)


def _rules_of(findings: Sequence[Mapping]) -> list[str]:
    return [str(entry.get("rule")) for entry in findings]


def _naming(findings: Sequence[Mapping], needle: str) -> list[dict]:
    """Every finding whose rule id or detail names `needle`, normalised."""
    wanted = _norm(needle)
    return [
        dict(entry)
        for entry in findings
        if wanted in _norm(entry.get("rule", "")) or wanted in _norm(entry.get("detail", ""))
    ]


def _with_rule(findings: Sequence[Mapping], rule: str) -> list[dict]:
    """Every finding carrying exactly this rule id (normalised)."""
    wanted = _norm(rule)
    return [dict(entry) for entry in findings if _norm(entry.get("rule", "")) == wanted]


# --- the spec fixtures -------------------------------------------------------


@lru_cache(maxsize=1)
def _vocab() -> frozenset:
    return frozenset(load_vocab(load_config(PILOT_CONFIG)))


@lru_cache(maxsize=1)
def _good_text() -> str:
    return GOOD_SPEC.read_text(encoding="utf-8")


def _base() -> dict:
    """The committed §11 good spec, parsed fresh for every caller.

    It declares no `palette.background`, which is what makes it both pin 1's
    silence fixture and pin 3's offender.
    """
    spec = yaml.safe_load(_good_text())
    assert "background" not in spec["game"]["palette"], (
        "fixture drift: good-spec.yaml now declares `palette.background`, so it can no "
        "longer stand in for the six background-silent shipped specs"
    )
    return spec


def _spec_with_tiny_token(value: object) -> dict:
    spec = _base()
    spec["game"]["palette"][TINY_TOKEN_KEY] = value
    return spec


def _spec_with_background(value: object) -> dict:
    spec = _base()
    spec["game"]["palette"]["background"] = value
    return spec


def _lint(spec: Mapping, *, actions: Mapping[str, str] | None = None, idea: Mapping | None = None):
    """`lint_spec` with the fidelity-rule map, failing loudly on a missing rule.

    A `ValueError` naming an unknown rule id is `resolve_rule_actions`' own
    refusal at HEAD, where the registry has two members. Turning it into a
    readable failure is what makes pin 3 fail at HEAD for the RIGHT reason.
    """
    try:
        return s1_spec.lint_spec(spec, _vocab(), idea, rule_actions=actions)
    except ValueError as exc:
        if actions and RULE_UNSTATED_BACKGROUND in actions:
            pytest.fail(
                f"lint_spec refused the fidelity-rule id {RULE_UNSTATED_BACKGROUND!r}: {exc}. "
                f"W2-D part 2(b) adds it as a THIRD FIDELITY_RULES entry reusing W1-B's "
                f"registry, reader and prompt-sync machinery ('do not invent a parallel "
                f"mechanism'); the registry today is {list(s1_spec.FIDELITY_RULES)}"
            )
        raise


def _armed(spec: Mapping, action: str, *, idea: Mapping | None = None):
    return _lint(spec, actions={RULE_UNSTATED_BACKGROUND: action}, idea=idea)


# --- the synthetic visual-card slot ------------------------------------------


def _game_id() -> str:
    """The synthetic slot's game_id — READ off the harness, never retyped."""
    return str(ff.frames_document([[ff.BG]])["game_id"])


def _build_card(
    tmp_path: Path,
    name: str,
    *,
    tiny_token: object = _MISSING,
    exempt: Sequence[str] = (),
    mode: str = "fail",
    you_shape: str = "pixel",
) -> dict:
    """One synthetic slot's visual card, built inside tmp_path only.

    `you_shape="pixel"` paints `you` as a single pixel — 1 px against R-02's
    conservative 4-px floor, the sub-floor role every pin here is about — while
    `goal` is a full 4x4 cell that clears the floor on every reading.
    """
    spec = ff.spec_document()
    if tiny_token is not _MISSING:
        spec["game"]["palette"][TINY_TOKEN_KEY] = tiny_token
    gate: dict[str, object] = {GATE_CARD_KEY: "record", GATE_FOOTPRINT_KEY: mode}
    if exempt:
        gate[GATE_EXEMPT_KEY] = list(exempt)
    case = ff.stage_case(tmp_path / name, ff.role_board(you_shape), spec)
    return s3_visual.build_visual_card(case, {"gate": gate})


def _role_block(report: Mapping) -> Mapping:
    return ff.check_block(report, ff.ROLE_FOOTPRINT, label="role-footprint")


def _role_entry(block: Mapping, role: str) -> Mapping:
    roles = ff.find(block, "roles", depth=1)
    if isinstance(roles, Mapping):
        for key, value in roles.items():
            if _norm(key) == _norm(role) and isinstance(value, Mapping):
                return value
    pytest.fail(
        f"the `role-footprint` block carries no per-role entry for {role!r} "
        f"({ff.key_map(block)}). R-02 reports per role, never per corpus"
    )


def _status(entry: Mapping, *, label: str) -> str:
    found = ff.find(entry, "status", depth=0)
    if not isinstance(found, str):
        pytest.fail(
            f"{label}: the role entry carries no `status` string ({ff.key_map(entry)}) — "
            f"it is the field R-02 already reports pass / fail / exempt / not-checked in"
        )
    return _norm(found)


def _measurement(entry: Mapping) -> object:
    """The role's measured smallest component, however the card spells it."""
    for name in ("mincomponent", "smallestcomponent", "componentmin", "rolecomponentmin"):
        found = ff.find(entry, name, depth=0)
        if found is not _MISSING:
            return found
    return _MISSING


# =============================================================================
# PIN 1 — the `game.palette.tiny_token` schema matrix
# =============================================================================


def test_pin1_an_absent_tiny_token_is_silence():
    """Absence is silence: the unconfigured report is HEAD's, key for key."""
    report = _lint(_base())
    assert report.to_json_dict() == HEAD_STOCK_REPORT, (
        f"a spec that declares no `palette.{TINY_TOKEN_KEY}` must lint exactly as it did "
        f"before W2-D (absent = silence); got {report.to_json_dict()}"
    )


@pytest.mark.parametrize(
    "declared",
    [
        pytest.param(["you"], id="you"),
        pytest.param(["goal"], id="goal"),
        pytest.param(["danger"], id="danger"),
        pytest.param(["you", "goal"], id="two-roles"),
        pytest.param(["you", "goal", "danger"], id="all-three-roles"),
    ],
)
def test_pin1_a_valid_tiny_token_is_accepted(declared: list[str]):
    """A non-empty list of DISTINCT roles from (you, goal, danger) is legal."""
    report = _lint(_spec_with_tiny_token(declared))
    offenders = _naming(report.kills, TINY_TOKEN_KEY)
    assert not offenders, (
        f"`palette.{TINY_TOKEN_KEY}: {declared}` is the shape the contract legalises "
        f"(a non-empty list of distinct known roles) and must not kill; got {offenders}"
    )
    assert report.passed, (
        f"`palette.{TINY_TOKEN_KEY}: {declared}` made an otherwise §11-clean spec fail — "
        f"kills {_rules_of(report.kills)}"
    )


def test_pin1_the_roles_the_contract_names_are_the_ones_the_check_judges():
    """(you, goal, danger) is read off the implementation, not retyped here."""
    roles = getattr(s3_visual, "FOOTPRINT_ROLES", None)
    assert isinstance(roles, (list, tuple)), (
        "gen.s3_visual exposes no FOOTPRINT_ROLES tuple — it is the role set "
        "`role-footprint` judges and the one `tiny_token` draws from"
    )
    assert tuple(roles) == ("you", "goal", "danger"), (
        f"FOOTPRINT_ROLES moved to {tuple(roles)}; the contract writes `tiny_token` as "
        f"'a list of distinct roles from (you, goal, danger)'"
    )


@pytest.mark.parametrize(
    "declared",
    [
        pytest.param([], id="empty-list"),
        pytest.param(["you", "you"], id="duplicated-role"),
        pytest.param(["boss"], id="unknown-role"),
        pytest.param(["background"], id="background-is-not-a-tiny-token-role"),
        pytest.param(["you", 1], id="non-string-entry"),
        pytest.param("you", id="not-a-list"),
    ],
)
def test_pin1_a_malformed_tiny_token_is_a_schema_kill(declared: object):
    """A key written down is a declaration and is held to one.

    Reading (a): the kill is pinned by its DETAIL naming the field, not by a
    rule id — HEAD emits every palette schema violation under `schema`, a
    member of the closed `KILL_RULES` tuple b5 pins exactly.
    """
    report = _lint(_spec_with_tiny_token(declared))
    named = _naming(report.kills, TINY_TOKEN_KEY)
    assert named, (
        f"`palette.{TINY_TOKEN_KEY}: {declared!r}` is not a non-empty list of distinct "
        f"known roles and must be a schema KILL naming the field (the "
        f"`hazardless_override` / `palette.background` precedent: an unusable value is a "
        f"kill, never a silently ignored field). Kills were {_rules_of(report.kills)}, "
        f"warns {_rules_of(report.warns)}"
    )
    assert not report.passed, (
        f"`palette.{TINY_TOKEN_KEY}: {declared!r}` produced the finding {named} but the "
        f"report still passed — `passed` is exactly `kills == []`, so the finding is a warn"
    )


def test_pin1_the_kill_names_the_field_path():
    """The kill says WHICH field, the way every other palette schema kill does."""
    report = _lint(_spec_with_tiny_token([]))
    named = _naming(report.kills, TINY_TOKEN_KEY)
    assert named, "no kill named the field (see the matrix pin above for the full message)"
    details = [_norm(entry["detail"]) for entry in named]
    assert any("palette" in detail for detail in details), (
        f"the tiny_token kill never says it is about `game.palette.{TINY_TOKEN_KEY}` — "
        f"details were {details}"
    )


def test_pin1_a_declared_tiny_token_does_not_disturb_the_rest_of_the_report():
    """The declaration adds no finding of its own to an otherwise clean spec."""
    report = _lint(_spec_with_tiny_token(["you"]))
    assert report.to_json_dict() == HEAD_STOCK_REPORT, (
        f"a VALID `palette.{TINY_TOKEN_KEY}` declaration changed the lint report — it is "
        f"an exemption the visual gate reads, not a §11 finding. Got "
        f"{report.to_json_dict()}"
    )


# =============================================================================
# PIN 2 — `role-footprint` reads the spec-side declaration
# =============================================================================


def test_pin2_the_unexempted_subfloor_role_fails(tmp_path: Path):
    """The guard pin: without a declaration the synthetic slot really violates."""
    report = _build_card(tmp_path, "baseline")
    block = _role_block(report)
    status = _status(_role_entry(block, "you"), label="you (no declaration)")
    assert status == HEAD_SUBFLOOR_STATUS, (
        f"the 1-px `you` must still be a plain `{HEAD_SUBFLOOR_STATUS}` when nothing "
        f"exempts it, or pin 2 below is measuring nothing; got {status!r}"
    )
    assert ff.verdict(block, label="role-footprint") is False, (
        "an unexempted sub-floor role must still fail the check as a whole"
    )


@pytest.mark.parametrize("mode", ["record", "fail"])
def test_pin2_a_declared_tiny_token_role_is_exempt_declared(tmp_path: Path, mode: str):
    """`palette.tiny_token: [you]` flips the sub-floor `you` to exempt-declared."""
    report = _build_card(tmp_path, f"declared-{mode}", tiny_token=["you"], mode=mode)
    block = _role_block(report)
    entry = _role_entry(block, "you")
    status = _status(entry, label="you (tiny_token declared)")
    assert status == _norm(EXEMPT_DECLARED), (
        f"`game.palette.{TINY_TOKEN_KEY}: ['you']` is the spec-side exemption the "
        f"`role-footprint` check must read, reporting status {EXEMPT_DECLARED!r}; the "
        f"card reported {status!r} in mode {mode!r}. At HEAD this reads "
        f"{HEAD_SUBFLOOR_STATUS!r}, which is the change this pin is about"
    )


def test_pin2_the_measurement_is_still_printed(tmp_path: Path):
    """"measurement still printed" — an exemption hides nothing it measured."""
    declared = _role_entry(_role_block(_build_card(tmp_path, "m-declared", tiny_token=["you"])),
                           "you")
    baseline = _role_entry(_role_block(_build_card(tmp_path, "m-baseline")), "you")
    measured, before = _measurement(declared), _measurement(baseline)
    assert measured is not _MISSING and measured is not None, (
        f"the exempt-declared role prints no measurement ({ff.key_map(declared)}); the "
        f"contract says the exemption changes the STATUS and the measurement is still "
        f"printed (the `gate.role_footprint_exempt` precedent: still measured, still "
        f"printed)"
    )
    assert measured == before, (
        f"the declared role's measurement moved under the exemption ({before!r} -> "
        f"{measured!r}) — a declaration must not change what was measured"
    )


def test_pin2_a_declared_tiny_token_clears_the_check(tmp_path: Path):
    """An exempted role is not a failing role: the check as a whole passes."""
    block = _role_block(_build_card(tmp_path, "verdict", tiny_token=["you"]))
    assert ff.verdict(block, label="role-footprint") is True, (
        f"the only sub-floor role is declared in `palette.{TINY_TOKEN_KEY}`, so "
        f"`role-footprint` carries no failure left to report"
    )


def test_pin2_the_declaration_is_per_role(tmp_path: Path):
    """Declaring `goal` tiny does not buy `you` an exemption."""
    block = _role_block(_build_card(tmp_path, "other-role", tiny_token=["goal"]))
    status = _status(_role_entry(block, "you"), label="you (goal declared tiny)")
    assert status == HEAD_SUBFLOOR_STATUS, (
        f"`palette.{TINY_TOKEN_KEY}: ['goal']` exempted `you` as well (status {status!r}) "
        f"— the declaration is a list of the roles the game DELIBERATELY draws smaller, "
        f"role by role, exactly as `gate.role_footprint_exempt` is"
    )


def test_pin2_the_operator_override_still_works(tmp_path: Path):
    """`gate.role_footprint_exempt` remains, unchanged, as the operator override."""
    exempt = [f"{_game_id()}:you"]
    block = _role_block(_build_card(tmp_path, "operator", exempt=exempt))
    entry = _role_entry(block, "you")
    status = _status(entry, label="you (operator exemption)")
    assert "exempt" in status, (
        f"`gate.{GATE_EXEMPT_KEY}: {exempt}` no longer exempts the sub-floor role "
        f"(status {status!r}) — W2-D adds a spec-side declaration beside the operator "
        f"override, it does not replace it"
    )
    assert status != _norm("fail"), f"the operator-exempted role reports {status!r}"
    assert _measurement(entry) not in (_MISSING, None), (
        "the operator-exempted role stopped printing its measurement"
    )
    assert ff.verdict(block, label="role-footprint") is True, (
        "the operator exemption no longer clears the check"
    )


def test_pin2_the_two_exemptions_are_told_apart(tmp_path: Path):
    """Spec-side and operator-side are DIFFERENT statuses, so a report says which
    declaration bought the exemption (the `palette-overload-declared` rule)."""
    spec_side = _status(
        _role_entry(_role_block(_build_card(tmp_path, "d-spec", tiny_token=["you"])), "you"),
        label="you (spec declaration)",
    )
    operator = _status(
        _role_entry(
            _role_block(_build_card(tmp_path, "d-op", exempt=[f"{_game_id()}:you"])), "you"
        ),
        label="you (operator exemption)",
    )
    assert spec_side == _norm(EXEMPT_DECLARED) and spec_side != operator, (
        f"the spec-side exemption reports {spec_side!r} and the operator override "
        f"{operator!r}; the contract names {EXEMPT_DECLARED!r} for the spec-side one "
        f"precisely so a reader can tell a game's own declaration from an operator's"
    )


# =============================================================================
# PIN 3 — `unstated-background`, the third FIDELITY_RULES entry
# =============================================================================


def test_pin3_the_registry_carries_a_third_rule():
    rules = tuple(s1_spec.FIDELITY_RULES)
    assert RULE_UNSTATED_BACKGROUND in rules, (
        f"`{RULE_UNSTATED_BACKGROUND}` is not in FIDELITY_RULES ({list(rules)}). The "
        f"contract is explicit: 'the warn is a THIRD FIDELITY_RULES entry ... reuse the "
        f"registry, reader and prompt-sync machinery W1-B built; do not invent a parallel "
        f"mechanism'"
    )
    missing = [rule for rule in HEAD_FIDELITY_RULES if rule not in rules]
    assert not missing, f"W1-B's rules {missing} left the registry"


def test_pin3_the_rule_has_an_action_key():
    keys = getattr(s1_spec, "FIDELITY_ACTION_KEYS", None)
    assert isinstance(keys, Mapping) and RULE_UNSTATED_BACKGROUND in keys, (
        f"FIDELITY_ACTION_KEYS carries no `lint:` key for {RULE_UNSTATED_BACKGROUND!r} "
        f"({keys}) — every fidelity rule has its own `lint.<rule>_action` knob"
    )


def test_pin3_the_default_is_off():
    resolved = s1_spec.resolve_rule_actions(None)
    assert resolved.get(RULE_UNSTATED_BACKGROUND) == DEFAULT_ACTION, (
        f"the unconfigured action is {resolved.get(RULE_UNSTATED_BACKGROUND)!r}, not "
        f"{DEFAULT_ACTION!r}. DEFAULT OFF is the contract's own word, and it is what keeps "
        f"the shipped-lint-report parity pin green for the six background-silent specs"
    )
    assert s1_spec.lint_rule_actions({}).get(RULE_UNSTATED_BACKGROUND) == DEFAULT_ACTION, (
        "a config with no `lint:` block must resolve the new rule to off"
    )


@pytest.mark.parametrize("action", ["on", "true", "Warn", "warn ", "record", ""])
def test_pin3_an_action_off_the_enum_is_loud(action: str):
    """Invalid knob values are loud ValueErrors (the common-rules house rule)."""
    with pytest.raises(ValueError):
        s1_spec.resolve_rule_actions({RULE_UNSTATED_BACKGROUND: action})
    key = s1_spec.FIDELITY_ACTION_KEYS.get(RULE_UNSTATED_BACKGROUND)
    assert key, (
        f"FIDELITY_ACTION_KEYS carries no `lint:` key for {RULE_UNSTATED_BACKGROUND!r}, so "
        f"there is no knob to hand a bad value to (see the action-key pin)"
    )
    with pytest.raises(ValueError):
        s1_spec.lint_rule_actions({"lint": {key: action}})


@pytest.mark.parametrize("actions", [None, {}], ids=["no-map", "empty-map"])
def test_pin3_unconfigured_lint_is_byte_identical(actions):
    """The parity pattern: a background-silent spec lints exactly as at HEAD."""
    report = _lint(_base(), actions=actions)
    assert report.to_json_dict() == HEAD_STOCK_REPORT, (
        f"an UNCONFIGURED lint of a spec with no `game.palette.background` gained "
        f"findings {report.to_json_dict()}. Six of the seven shipped specs are "
        f"background-silent, so an unconditional warn retroactively falsifies their "
        f"shipped lint reports — which is why the contract makes this a DEFAULT-OFF rule"
    )


def test_pin3_armed_warn_fires_on_a_background_silent_spec():
    report = _armed(_base(), "warn")
    warns = _with_rule(report.warns, RULE_UNSTATED_BACKGROUND)
    assert warns, (
        f"armed at `warn`, a spec with no `game.palette.background` must gain an "
        f"{RULE_UNSTATED_BACKGROUND!r} warn; warns were {_rules_of(report.warns)}, kills "
        f"{_rules_of(report.kills)}"
    )
    assert len(warns) == 1, f"one spec, one unstated-background warn; got {warns}"
    assert not _with_rule(report.kills, RULE_UNSTATED_BACKGROUND) and report.passed, (
        f"`warn` must RECORD, never refuse — kills were {_rules_of(report.kills)}"
    )


def test_pin3_the_warn_names_the_canon_default_and_field_index():
    """"a warn naming the canon default and that field-index reads the declaration"."""
    warns = _with_rule(_armed(_base(), "warn").warns, RULE_UNSTATED_BACKGROUND)
    assert warns, "no unstated-background warn to read (see the firing pin above)"
    detail = _norm(warns[0].get("detail", ""))
    default = getattr(s1_spec, "BACKGROUND_DEFAULT", 5)
    assert "background" in detail, f"the warn never says `background`: {detail!r}"
    assert str(default) in detail, (
        f"the warn does not name the canon default index {default} "
        f"(`s1_spec.BACKGROUND_DEFAULT`, affordance §9): {detail!r}"
    )
    assert "field index" in detail, (
        f"the warn does not say that field-index reads the declaration: {detail!r}. "
        f"That is the half of the sentence the contract spells out — the reader has to "
        f"learn WHY a silent background costs them a check"
    )


def test_pin3_armed_kill_refuses():
    report = _armed(_base(), "kill")
    kills = _with_rule(report.kills, RULE_UNSTATED_BACKGROUND)
    assert kills, (
        f"armed at `kill` the rule must refuse the spec; kills were "
        f"{_rules_of(report.kills)}, warns {_rules_of(report.warns)}"
    )
    assert not report.passed, "a kill that leaves `passed` true is not a kill"


@pytest.mark.parametrize("background", [0, 5, 15], ids=["black0", "canon5", "high15"])
@pytest.mark.parametrize("action", ["warn", "kill"])
def test_pin3_a_declared_background_is_silent(background: int, action: str):
    report = _armed(_spec_with_background(background), action)
    found = _with_rule(_findings(report), RULE_UNSTATED_BACKGROUND)
    assert not found, (
        f"`palette.background: {background}` IS the declaration this rule asks for, so "
        f"the rule must be silent even armed at {action!r}; got {found}"
    )


def test_pin3_prompt_sync_rides_the_w1b_machinery():
    """Reading (g): a rule armed to KILL is quoted to the writer it judges."""
    assert s1_spec.fidelity_section(None) is None, (
        "the unconfigured writer prompt must stay byte-identical — `fidelity_section(None)` "
        "returns None at HEAD and has to keep doing so"
    )
    try:
        section = s1_spec.fidelity_section({RULE_UNSTATED_BACKGROUND: "kill"})
    except ValueError as exc:
        pytest.fail(
            f"`fidelity_section` refused {RULE_UNSTATED_BACKGROUND!r} ({exc}) — the new "
            f"rule has to join the SAME registry the prompt-sync section reads"
        )
    assert section, (
        f"a batch that arms {RULE_UNSTATED_BACKGROUND!r} to KILL gets no writer-prompt "
        f"section. W1-B's doctrine, quoted in `fidelity_section`'s own docstring: a rule "
        f"that can kill a session is quoted to the writer being judged by it"
    )
    assert "background" in _norm(section), (
        f"the kill-armed section never mentions the background: {section!r}"
    )


def test_pin3_arming_the_new_rule_leaves_the_w1b_rules_alone():
    """The third entry is additive: arming it arms nothing else."""
    resolved = s1_spec.resolve_rule_actions({RULE_UNSTATED_BACKGROUND: "kill"})
    for rule in HEAD_FIDELITY_RULES:
        assert resolved.get(rule) == DEFAULT_ACTION, (
            f"arming {RULE_UNSTATED_BACKGROUND!r} moved {rule!r} to {resolved.get(rule)!r}"
        )


# --- pin 3, the shipped corpus: the DANGER the contract states plainly --------


def _shipped_dirs() -> list[Path]:
    """Every shipped spec dir — a `spec.yaml` beside a `spec.md`, no `.killed`."""
    if not CORPUS_ROOT.is_dir():
        return []
    return sorted(
        path.parent
        for path in CORPUS_ROOT.glob("*/*/spec.yaml")
        if (path.parent / "spec.md").is_file() and ".killed" not in path.parts
    )


SHIPPED_DIRS = _shipped_dirs()
SHIPPED_IDS = [path.name for path in SHIPPED_DIRS]
needs_corpus = pytest.mark.skipif(
    not SHIPPED_DIRS,
    reason="no shipped spec dir under out/corpus — the live-run tree is gitignored",
)


def _shipped(spec_dir: Path) -> tuple[dict, dict | None]:
    spec = yaml.safe_load((spec_dir / "spec.yaml").read_text(encoding="utf-8"))
    idea_path = spec_dir / "idea.json"
    idea = json.loads(idea_path.read_text(encoding="utf-8")) if idea_path.is_file() else None
    return spec, idea


@needs_corpus
def test_pin3_the_corpus_is_mostly_background_silent():
    """The contract's own measurement, re-measured: six of seven declare none."""
    silent = [
        path.name for path in SHIPPED_DIRS
        if "background" not in (_shipped(path)[0].get("game", {}).get("palette") or {})
    ]
    assert silent, (
        "no shipped spec is background-silent any more, so the parity danger this rule's "
        "DEFAULT OFF exists to avoid has evaporated — re-read the contract before "
        "re-freezing this pin"
    )


@needs_corpus
@pytest.mark.parametrize("spec_dir", SHIPPED_DIRS, ids=SHIPPED_IDS)
def test_pin3_shipped_specs_gain_nothing_unconfigured(spec_dir: Path):
    """The shipped lint reports stay true: unconfigured, the rule is silent."""
    spec, idea = _shipped(spec_dir)
    report = _lint(spec, idea=idea)
    found = _with_rule(_findings(report), RULE_UNSTATED_BACKGROUND)
    assert not found, (
        f"{spec_dir.name}: an unconfigured lint fired {RULE_UNSTATED_BACKGROUND!r} "
        f"({found}) — every shipped dir's `lint-report.json` would be retroactively wrong"
    )


@needs_corpus
@pytest.mark.parametrize("spec_dir", SHIPPED_DIRS, ids=SHIPPED_IDS)
def test_pin3_shipped_specs_warn_exactly_when_armed(spec_dir: Path):
    """Armed, the rule fires on precisely the background-silent shipped specs."""
    spec, idea = _shipped(spec_dir)
    declared = "background" in (spec.get("game", {}).get("palette") or {})
    report = _armed(spec, "warn", idea=idea)
    found = _with_rule(_findings(report), RULE_UNSTATED_BACKGROUND)
    if declared:
        assert not found, f"{spec_dir.name} declares a background but was warned: {found}"
    else:
        assert found, (
            f"{spec_dir.name} declares no `palette.background`, so the ARMED warn must "
            f"fire on it — findings were {_rules_of(_findings(report))}"
        )


# =============================================================================
# PIN 4 — template.yaml arms it at warn, and the readers still accept it
# =============================================================================


@lru_cache(maxsize=1)
def _template_tree() -> dict:
    assert TEMPLATE_PATH.is_file(), f"config/template.yaml missing: {TEMPLATE_PATH}"
    return yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))


def test_pin4_the_template_arms_the_rule_at_warn():
    """Reading (i): the key is READ off FIDELITY_ACTION_KEYS, never retyped."""
    key = s1_spec.FIDELITY_ACTION_KEYS.get(RULE_UNSTATED_BACKGROUND)
    assert key, "no action key to look for (see the registry pin)"
    lint_block = _template_tree().get("lint")
    assert isinstance(lint_block, Mapping), (
        f"config/template.yaml carries no `lint:` block to arm the rule in; it offers "
        f"{sorted(_template_tree())}"
    )
    assert lint_block.get(key) == TEMPLATE_ACTION, (
        f"config/template.yaml must ship `lint.{key}: {TEMPLATE_ACTION}` — the contract's "
        f"'DEFAULT OFF, armed warn in template.yaml'. The block reads "
        f"{dict(lint_block)!r}"
    )


def test_pin4_the_reader_resolves_the_template_arming():
    actions = s1_spec.lint_rule_actions(_template_tree())
    assert actions.get(RULE_UNSTATED_BACKGROUND) == TEMPLATE_ACTION, (
        f"`lint_rule_actions` reads the template's arming as "
        f"{actions.get(RULE_UNSTATED_BACKGROUND)!r}, not {TEMPLATE_ACTION!r}"
    )
    for rule in HEAD_FIDELITY_RULES:
        assert actions.get(rule) == TEMPLATE_ACTION, (
            f"the template's W1-B arming of {rule!r} changed to {actions.get(rule)!r}; "
            f"W2-D appends its own comment lines, it never rewrites the block"
        )


def _extension_readers() -> dict[str, object]:
    """The LOCAL roster extension: every reader W2-D's own knobs travel through.

    `test_docs_template._readers()` is the shipped roster and is swept beside
    these; it does not carry the fidelity-rule reader or either role-footprint
    reader, which are exactly the ones this contract's template lines feed.
    """
    return {
        "s1_spec.lint_rule_actions": s1_spec.lint_rule_actions,
        "s1_spec.resolve_rule_actions": lambda cfg: s1_spec.resolve_rule_actions(
            s1_spec.lint_rule_actions(cfg)
        ),
        "s3_visual.role_footprint_mode": s3_visual.role_footprint_mode,
        "s3_visual.role_footprint_exempt": s3_visual.role_footprint_exempt,
    }


@pytest.mark.parametrize("reader_name", sorted(_extension_readers()))
def test_pin4_the_extension_readers_accept_the_template(reader_name: str, tmp_path: Path):
    cfg = load_config(dt._template_copy(tmp_path))
    reader = _extension_readers()[reader_name]
    try:
        reader(cfg)
    except Exception as exc:  # noqa: BLE001 — the pin is "no reader refuses it"
        pytest.fail(
            f"{reader_name} refused config/template.yaml: {type(exc).__name__}: {exc}. "
            f"W2-D appends its own comment/knob lines to the template; every reader that "
            f"parses the blocks it touches has to keep accepting the whole file"
        )


def test_pin4_the_shipped_reader_roster_still_accepts_the_template(tmp_path: Path):
    """The sibling roster, swept in one go so the lead reads every failure at once."""
    cfg = load_config(dt._template_copy(tmp_path))
    failures = []
    for name, reader in sorted(dt._readers().items()):
        try:
            reader(cfg)
        except Exception as exc:  # noqa: BLE001 — collected, then reported together
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failures, (
        "config/template.yaml is no longer accepted by every shipped config reader "
        "(wave-2 lanes append to this file, so a failure here may belong to a sibling "
        "lane and is REPORTED, not adapted to):\n  " + "\n  ".join(failures)
    )


# =============================================================================
# PIN 5 — visual_canon's hazardless note states BOTH official figures
# =============================================================================

#: The two official figures the contract reconciles: lethality prose ~11/25 and
#: the matrix's `hazard.*`-absence 16/25. Pinned as NUMBERS near the mention,
#: never as prose.
HAZARDLESS_FIGURES = ("11", "16")
#: Reading (j): calibrated at HEAD, where even a 30-line window around the one
#: `hazardless` mention holds `11` and never `16`.
HAZARDLESS_WINDOW_LINES = 20


def _number_present(number: str, text: str) -> bool:
    return bool(re.search(rf"(?<!\d){re.escape(number)}(?!\d)", text))


def test_pin5_visual_canon_still_mentions_hazardless():
    lines = VISUAL_CANON_SOURCE.read_text(encoding="utf-8").splitlines()
    assert any("hazardless" in line.lower() for line in lines), (
        f"{VISUAL_CANON_SOURCE} mentions `hazardless` nowhere — R-25 reconciles that "
        f"note, it does not delete it"
    )


def test_pin5_the_hazardless_note_states_both_official_figures():
    """Both figures in one place: ~11/25 (lethality prose) and 16/25 (matrix)."""
    lines = VISUAL_CANON_SOURCE.read_text(encoding="utf-8").splitlines()
    windows = []
    for index, line in enumerate(lines):
        if "hazardless" not in line.lower():
            continue
        lo = max(0, index - HAZARDLESS_WINDOW_LINES)
        hi = min(len(lines), index + HAZARDLESS_WINDOW_LINES + 1)
        windows.append((index + 1, "\n".join(lines[lo:hi])))
    assert windows, "no `hazardless` mention to read (see the mention pin above)"
    hits = [
        line_no for line_no, window in windows
        if all(_number_present(number, window) for number in HAZARDLESS_FIGURES)
    ]
    assert hits, (
        f"no `hazardless` note in {VISUAL_CANON_SOURCE.name} carries BOTH figures "
        f"{HAZARDLESS_FIGURES} within {HAZARDLESS_WINDOW_LINES} lines. R-25 per the operator's "
        f"ruling: the '~11 of 25' comment is reconciled to state both official figures "
        f"(lethality prose ~11/25 = 0.44; matrix `hazard.*`-absence 16/25 = 0.64) and the "
        f"ruling that `batch.mix.hazardless` stays 0.5 because hazardless is NOT a "
        f"conformance axis. Mentions found at lines "
        f"{[line_no for line_no, _ in windows]}"
    )
