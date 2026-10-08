"""Blind pins for the b003 S1 tier contract (contract T-B) — lint + writer prompt.

Run: .venv/bin/python -m pytest gen/tests/test_b003_tiers_s1.py -v

Written from the frozen T-B-tests contract ALONE. No in-progress tier diff of
`gen/s1_spec.py` was read: only that module's PRE-EXISTING public surface
(`lint_spec`, `build_writer_prompt`, `LintReport`, `KILL_RULES`, `REFUSALS` /
`GOAL_LEGIBLE` / `DANGER_TELLS`, `HAZARD_PREFIXES`, `DECEPTION_CATALOG`), the
LANDED `gen/tiers.py` (contract T-A), the existing fixtures and the shipped
artifacts under `out/`. These pins therefore describe the contract, not the
implementation, and are expected to fail until the implementation lands.

House style follows `test_b002_promptsync.py` and the sibling
`test_b003_tiers_s0.py`: every tier fact is READ OUT OF `gen.tiers` at test
time (never retyped), every corpus fact is read off the shipped artifact, the
canon tree is never written, and this file writes nothing at all.

What is pinned, in contract order:

  * the frozen surface — `TIER_TERMS_KILL_SENTENCE` as a template, the four
    tier rules' silence without a policy / an idea / a known tier, and the
    writer prompt's `### Tier contract` section (activation set, position,
    content order, and one line per governing knob);
  1. knob-off byte-identity — every shipped spec lints identically with no
     policy and with `tier_policy=None`, and the prompt is byte-equal when the
     parameter is omitted or None;
  2. prompt-sync — ONE kill sentence, two consumers (the writer prompt and the
     `tier-terms` finding detail);
  3. the retro matrix — the three b002 games against the measured budgets,
     and the warn-action mirror;
  4. the ordinal ceilings, including the hazardless `none` exemption;
  5. distinct-lever counting against `DECEPTION_CATALOG`;
  6. intro pacing — one finding naming every offending 1-based level;
  7. the escalation exemption — `escalation_lint_policy` zeroes the budget and
     nothing else;
  8. `"tier-terms" in KILL_RULES`;
  9. purity — same inputs, same report; no mutation of the policy or the spec.

Five readings this file had to resolve (each is quoted in the failure message
of the pin that depends on it):

  a. The contract writes `lint_spec(...).as_dict()`; the landed `LintReport`
     exposes `to_json_dict()`. `report_dict()` below accepts either name (and
     falls back to `dataclasses.asdict`), so the pin is on the report's
     CONTENT, which is what "byte-identical" means here, not on a method name
     the pre-existing surface does not carry.
  b. "renders immediately after the idea block" is read as: the markdown head
     immediately PRECEDING the tier head is the idea block's own head. The
     idea head's wording is not frozen by the contract, so it is located by
     the word "idea" rather than quoted.
  c. The contract lists `TIER_TABLE[tier].guidance` first in the section with
     no `iff` clause, yet remarks that the kill sentence is present "EVEN when
     prompt_guidance is False" — which only means something if the guidance
     itself is governed by `prompt_guidance`. Reading: the guidance paragraph
     is `prompt_guidance`'s own line. It is pinned PRESENT only under
     `prompt_guidance=True`, and never pinned absent, so these tests hold
     under either reading.
  d. Only the refusal group's position in the knob-defaults line is frozen (it
     is inside the line's frozen prefix). The goal-legible and danger-tell
     groups are pinned as present `/`-joined runs, not in a fixed order.
  e. Pin 1's idea pairing is NOT ambiguous in the shipped tree: each spec dir
     carries its own `idea.json`, and it is used only when its `id` equals the
     spec's `game.idea_ref`. A dir whose linkage fails that check is linted
     with `idea=None`, as the contract directs, and the skipped linkage is
     named in the failure message of the pin that would have used it.
"""

from __future__ import annotations

import dataclasses
import json
import re
from copy import deepcopy
from itertools import pairwise
from pathlib import Path

import pytest
import yaml

from gen import s1_spec, tiers
from gen.config import REPO_ROOT, load_config
from gen.s0_ideas import load_vocab

TESTS_DIR = Path(__file__).resolve().parent
GOOD_SPEC = TESTS_DIR / "fixtures" / "specs" / "good-spec.yaml"
CORPUS_ROOT = REPO_ROOT / "out" / "corpus"
CONFIG_PATH = "config/b002-triple.yaml"

# The three b002 games the contract names by slug (pin 3's retro matrix).
PUMP = "pump-phase-time-echo"
CORE_WARD = "core-ward-phase-gates"
CONVOY = "convoy-in-the-fog"

# The four tier rules, by the ids the contract freezes.
RULE_TERMS = "tier-terms"
RULE_KNOBS = "tier-knob-mismatch"
RULE_LEVERS = "tier-deceptions"
RULE_PACING = "tier-intro-pacing"
TIER_RULES = (RULE_TERMS, RULE_KNOBS, RULE_LEVERS, RULE_PACING)

# The frozen prompt strings. Only the stems the contract quotes are written
# down; everything variable is formatted from `gen.tiers` at test time.
TIER_SECTION_MARK = "### Tier contract"
TIER_SECTION_HEAD = "### Tier contract (tier {tier} — {label})"
KILL_SENTENCE_PREFIX = "TIER TERM BUDGET (tier "
KNOB_LINE_PREFIX = "Tier knob defaults — refusal: "
LEVER_CLAUSE = "declared deception levers: at most {lever_max}"
INTRO_LINE = "Levels after the first introduce at most {cap} new term(s) each"

_OMITTED = object()


# --- the surface under test, reached lazily --------------------------------


def _require(name: str):
    """One T-B symbol, or a failure in the contract's own words."""
    value = getattr(s1_spec, name, None)
    if value is None:
        pytest.fail(
            f"gen.s1_spec exposes no {name} — the T-B contract freezes it as part of the "
            "S1 tier surface; every pin below that reads it depends on the implementation "
            "having landed"
        )
    return value


def lint(spec, vocab, idea=None, policy=_OMITTED):
    """`lint_spec`, with `tier_policy` passed only when this call supplies one."""
    if policy is _OMITTED:
        return s1_spec.lint_spec(spec, vocab, idea)
    try:
        return s1_spec.lint_spec(spec, vocab, idea, tier_policy=policy)
    except TypeError as exc:
        if "tier_policy" not in str(exc):
            raise
        pytest.fail(
            f"gen.s1_spec.lint_spec does not accept tier_policy=... ({exc}) — the frozen "
            "signature is lint_spec(spec, vocab, idea=None, tier_policy=None), and a "
            "policy the linter cannot be handed is a rule that can never fire"
        )


def writer_prompt(cfg, idea, policy=_OMITTED):
    """`build_writer_prompt`, with `tier_policy` passed only when supplied."""
    if policy is _OMITTED:
        return s1_spec.build_writer_prompt(cfg, idea)
    try:
        return s1_spec.build_writer_prompt(cfg, idea, tier_policy=policy)
    except TypeError as exc:
        if "tier_policy" not in str(exc):
            raise
        pytest.fail(
            f"gen.s1_spec.build_writer_prompt does not accept tier_policy=... ({exc}) — "
            "the frozen signature is build_writer_prompt(cfg, idea, *, tier_policy=None, "
            "...); without it the writer is never told the tier it is writing at"
        )


def report_dict(report) -> dict:
    """The report's content, whatever the accessor is called (reading (a))."""
    for name in ("as_dict", "to_json_dict", "to_dict"):
        method = getattr(report, name, None)
        if callable(method):
            return method()
    if dataclasses.is_dataclass(report) and not isinstance(report, type):
        return dataclasses.asdict(report)
    raise AssertionError(
        f"a LintReport ({report!r}) exposes none of as_dict/to_json_dict/to_dict and is "
        "not a dataclass — the contract compares whole reports, so there has to be one "
        "way to read all of passed/kills/warns/spec_hash off one"
    )


def findings(report, rule: str) -> list[dict]:
    """Every finding of `rule`, kills and warns together."""
    data = report_dict(report)
    return [f for f in [*data["kills"], *data["warns"]] if f.get("rule") == rule]


def kills_for(report, rule: str) -> list[dict]:
    return [f for f in report_dict(report)["kills"] if f.get("rule") == rule]


def warns_for(report, rule: str) -> list[dict]:
    return [f for f in report_dict(report)["warns"] if f.get("rule") == rule]


def tier_findings(report) -> list[dict]:
    data = report_dict(report)
    return [f for f in [*data["kills"], *data["warns"]] if f.get("rule") in TIER_RULES]


# --- prompt helpers ---------------------------------------------------------


def heads(text: str) -> list[tuple[int, str]]:
    """`(offset, line)` for every markdown head of a prompt."""
    out: list[tuple[int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("#"):
            out.append((offset, line.strip()))
        offset += len(line)
    return out


def tier_section(prompt: str) -> tuple[str, str]:
    """The `### Tier contract` head and its body, up to the next head."""
    marks = [(offset, head) for offset, head in heads(prompt) if TIER_SECTION_MARK in head]
    assert len(marks) == 1, (
        f"the writer prompt carries {len(marks)} '{TIER_SECTION_MARK}' heads "
        f"({[head for _, head in marks]}) — the contract renders exactly ONE tier "
        "section when the policy is armed and the idea's tier is known"
    )
    start = marks[0][0]
    later = [offset for offset, _ in heads(prompt) if offset > start]
    end = min(later) if later else len(prompt)
    return marks[0][1], prompt[start:end]


def allowed_values(values, ordinals, ceiling: int) -> str:
    """The `/`-joined enum values at or under a ceiling, in ENUM order."""
    return "/".join(value for value in values if ordinals[value] <= ceiling)


def knob_line(section: str) -> str:
    """The one line of the section starting with the frozen knob prefix."""
    hits = [line.strip() for line in section.splitlines() if line.strip().startswith(
        KNOB_LINE_PREFIX)]
    assert len(hits) == 1, (
        f"the tier section carries {len(hits)} lines starting {KNOB_LINE_PREFIX!r} "
        f"({hits}) — the contract renders exactly one knob-defaults line while "
        "knob_defaults_action is not 'off'"
    )
    return hits[0]


# --- deception-catalog helpers (pin 5 fixtures, derived never retyped) ------


def squash(text: str) -> str:
    """Lowercase with separators removed — the catalog matcher's superset.

    The real matcher is separator- and inflection-tolerant, so if a keyword's
    squashed form is ABSENT from a squashed text the matcher cannot fire on
    it. That one-directional guarantee is all these fixtures need.
    """
    return re.sub(r"[-\s]+", "", text.lower())


def matched_keywords(text: str) -> set[str]:
    """Every catalog keyword that could possibly match `text`."""
    return {kw for kw in s1_spec.DECEPTION_CATALOG if squash(kw) in squash(text)}


def unambiguous_keywords() -> list[str]:
    """Catalog keywords that no OTHER keyword can be confused with.

    `look-alike` and `lookalike` squash to the same string, so prose carrying
    either one matches two catalog entries; a lever-counting fixture must not
    be built on that pair.
    """
    squashed = {kw: squash(kw) for kw in s1_spec.DECEPTION_CATALOG}
    return [
        kw
        for kw, form in squashed.items()
        if not any(
            other != kw and (form in other_form or other_form in form)
            for other, other_form in squashed.items()
        )
    ]


def lever_entry(keyword: str, tail: str) -> str:
    """A declared-deception entry that matches EXACTLY `keyword`."""
    entry = f"{keyword}: {tail}"
    assert matched_keywords(entry) == {keyword}, (
        f"the fixture entry {entry!r} matches {sorted(matched_keywords(entry))} rather "
        f"than exactly [{keyword!r}] — pin 5 counts DISTINCT catalog keywords, so each "
        "fixture entry has to carry one and only one"
    )
    return entry


# --- fixtures ---------------------------------------------------------------


@pytest.fixture(scope="session")
def cfg() -> dict:
    """The batch config both the linter's vocabulary and the prompt come from."""
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="session")
def vocab(cfg: dict) -> dict:
    """The closed term set `lint_spec` grades `game.terms` against."""
    return load_vocab(cfg)


@pytest.fixture(scope="session")
def good_spec() -> dict:
    """The hand-written §11 fixture spec — the base of every built spec below."""
    return yaml.safe_load(GOOD_SPEC.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def shipped() -> dict[str, dict]:
    """Every shipped spec under `out/corpus`, with its OWN idea.json when linked.

    Reading (e): the dir's `idea.json` is used only when its `id` equals the
    spec's `game.idea_ref`; otherwise the entry carries `idea=None` and the
    spec is linted unpaired, exactly as the contract directs.
    """
    if not CORPUS_ROOT.exists():
        pytest.skip(f"no shipped corpus at {CORPUS_ROOT} — pin 1/3 read real artifacts")
    games: dict[str, dict] = {}
    for spec_path in sorted(CORPUS_ROOT.glob("*/*/spec.yaml")):
        game_dir = spec_path.parent
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        idea = None
        idea_path = game_dir / "idea.json"
        if idea_path.exists():
            candidate = json.loads(idea_path.read_text(encoding="utf-8"))
            game = spec.get("game") if isinstance(spec, dict) else None
            ref = game.get("idea_ref") if isinstance(game, dict) else None
            if isinstance(candidate, dict) and candidate.get("id") == ref:
                idea = candidate
        games[game_dir.name] = {
            "slug": game_dir.name,
            "batch": game_dir.parent.name,
            "dir": game_dir,
            "spec": spec,
            "idea": idea,
        }
    return games


def shipped_game(shipped: dict[str, dict], slug: str) -> dict:
    """One named shipped game, or the contract's words on why the pin cannot run."""
    game = shipped.get(slug)
    if game is None:
        pytest.fail(
            f"no shipped spec {slug!r} under {CORPUS_ROOT} (found "
            f"{sorted(shipped)}) — the contract's retro matrix is measured on the three "
            "b002 games by name; a renamed or missing artifact has to be re-adjudicated "
            "before this pin can mean anything"
        )
    if game["idea"] is None:
        pytest.fail(
            f"the shipped spec {slug!r} carries no idea.json whose id equals its "
            "game.idea_ref — the tier rules are silent without an idea, so this pin "
            "cannot be measured on an unpaired spec (reading (e))"
        )
    return game


@pytest.fixture(scope="session")
def budgets() -> dict[str, int]:
    """The measured per-tier `len(game.terms)` ceilings (contract T-A)."""
    return dict(tiers.DEFAULT_TERM_BUDGETS)


@pytest.fixture(scope="session")
def budget_policy(budgets: dict[str, int]):
    """Pin 2's policy: the measured budgets, killing, everything else today's."""
    return tiers.TierPolicy(term_budget=dict(budgets), term_budget_action="kill")


@pytest.fixture(scope="session")
def armed_policy(budgets: dict[str, int]):
    """Pin 3's armed policy: budgets kill, knob defaults warn, pacing warn."""
    return tiers.TierPolicy(
        term_budget=dict(budgets),
        term_budget_action="kill",
        knob_defaults_action="warn",
        intro_pacing_action="warn",
    )


@pytest.fixture(scope="session")
def kill_sentence() -> str:
    """`TIER_TERMS_KILL_SENTENCE`, the one string both consumers quote."""
    return _require("TIER_TERMS_KILL_SENTENCE")


def fixture_idea(good_spec: dict, tier: str) -> dict:
    """A stage-0 idea for the fixture spec, at `tier`.

    `id` is read off the fixture's own `game.idea_ref` so the pre-existing
    idea_ref cross-check stays satisfied and the tier rules are the only thing
    these pins move; `prose` carries the `{title, text}` shape the pre-existing
    writer prompt requires.
    """
    game = good_spec["game"]
    return {
        "id": game["idea_ref"],
        "tier": tier,
        "seed_terms": list(game["terms"][:4]),
        "objective": game["objective"]["primary"],
        "prose": {
            "title": game["title"],
            "text": "A hand-built stage-0 idea for the b003 tier pins.",
        },
    }


# --- the frozen surface -----------------------------------------------------


def test_tier_terms_kill_sentence_is_a_formattable_template(kill_sentence: str) -> None:
    """One template, `{tier}` and `{budget}`, with the frozen opening."""
    assert kill_sentence.startswith(KILL_SENTENCE_PREFIX), (
        f"TIER_TERMS_KILL_SENTENCE starts {kill_sentence[:40]!r}, not "
        f"{KILL_SENTENCE_PREFIX!r} — the opening is frozen because the finding detail is "
        "pinned to START WITH this sentence, and a reader greps for that stem"
    )
    for field in ("{tier}", "{budget}"):
        assert field in kill_sentence, (
            f"TIER_TERMS_KILL_SENTENCE carries no {field} placeholder "
            f"({kill_sentence!r}) — it is a template formatted per tier by BOTH the "
            "writer prompt and the linter; a hard-coded tier or budget makes the two "
            "consumers drift the moment a budget moves"
        )
    rendered = kill_sentence.format(tier="t1", budget=6)
    assert "{" not in rendered and "}" not in rendered, (
        f"TIER_TERMS_KILL_SENTENCE.format(tier='t1', budget=6) leaves a placeholder "
        f"behind ({rendered!r}) — the template takes exactly those two fields"
    )


# LEAD-CORRECTED PIN (pin 8). The contract said tier-terms joins KILL_RULES;
# that line was written without knowing the b5 suite pins KILL_RULES two ways
# (exact tuple equality at test_b5_spec.py:294 AND a killed-fixture per member
# at :411 — a fixture that trips a tier rule through a policy-free
# `lint_spec(spec, vocab)` cannot exist BY CONSTRUCTION). The frozen surface
# is therefore a separate TIER_RULES registry: KILL_RULES stays the closed
# §11 list of unconditional rules, and a tier finding is a POLICY finding.
# The kill BEHAVIOR (tier-terms lands in `kills` under term_budget_action
# "kill", flipping `passed`) is already pinned by the retro-matrix tests.
def test_tier_rules_registry_is_the_four_ids_outside_kill_rules() -> None:
    """Pin 8 (corrected): the four tier ids, registered, outside the §11 list."""
    assert s1_spec.TIER_RULES == (
        "tier-terms",
        "tier-knob-mismatch",
        "tier-deceptions",
        "tier-intro-pacing",
    ), f"gen.s1_spec.TIER_RULES is {getattr(s1_spec, 'TIER_RULES', None)!r}"
    assert RULE_TERMS not in s1_spec.KILL_RULES, (
        "tier-terms crept into KILL_RULES — that list is pinned closed by the b5 "
        "suite and every member needs a policy-free killed fixture, which a "
        "policy-conditional rule cannot have"
    )


def test_tier_rules_are_silent_without_a_policy_an_idea_or_a_known_tier(
    good_spec: dict, vocab: dict, armed_policy
) -> None:
    """Three separate silences, all frozen in the contract's surface section."""
    spec = deepcopy(good_spec)
    spec["game"]["terms"] = list(spec["game"]["terms"]) + ["state.wait", "info.probe"]
    idea = fixture_idea(good_spec, "t1")

    none_policy = lint(spec, vocab, idea, policy=None)
    assert tier_findings(none_policy) == [], (
        f"tier_policy=None produced tier findings {tier_findings(none_policy)} — a "
        "config that never heard of the tier block has to lint exactly as it did before "
        "the tier work existed"
    )

    no_idea = lint(spec, vocab, None, policy=armed_policy)
    assert tier_findings(no_idea) == [], (
        f"linting with idea=None produced tier findings {tier_findings(no_idea)} — the "
        "tier lives on the IDEA, so without one there is no tier to hold the spec to"
    )

    unknown = lint(spec, vocab, {**idea, "tier": "t9"}, policy=armed_policy)
    assert tier_findings(unknown) == [], (
        f"an idea at an unknown tier 't9' produced tier findings "
        f"{tier_findings(unknown)} — an unknown tier has no row, no ceilings and no "
        "budget, so the rules have nothing to measure against and must stay quiet"
    )


def test_tier_section_renders_after_the_idea_block_in_contract_order(
    cfg: dict, good_spec: dict, budgets: dict[str, int], kill_sentence: str
) -> None:
    """Position (reading (b)) and the frozen content order, all knobs armed."""
    tier = "t1"
    row = tiers.TIER_TABLE[tier]
    policy = tiers.TierPolicy(
        prompt_guidance=True,
        term_budget=dict(budgets),
        term_budget_action="kill",
        knob_defaults_action="warn",
        intro_pacing_action="warn",
    )
    prompt = writer_prompt(cfg, fixture_idea(good_spec, tier), policy=policy)
    head, section = tier_section(prompt)

    assert head == TIER_SECTION_HEAD.format(tier=tier, label=row.label), (
        f"the tier head is {head!r}, not "
        f"{TIER_SECTION_HEAD.format(tier=tier, label=row.label)!r} — the head is frozen "
        "and carries both the tier id and its canon label, because the writer is being "
        "told which §3.3 column it is writing in"
    )

    offsets = [offset for offset, _ in heads(prompt)]
    start = prompt.index(head)
    before = [offset for offset in offsets if offset < start]
    assert before, (
        "the tier section is the FIRST head of the prompt — it renders immediately "
        "after the idea block, so the idea's own head has to precede it"
    )
    previous = next(line for offset, line in heads(prompt) if offset == max(before))
    assert "idea" in previous.lower(), (
        f"the head immediately before the tier section is {previous!r} — the contract "
        "renders the section immediately after the IDEA block (reading (b): the "
        "preceding head is located by the word 'idea', not by its wording), because the "
        "tier qualifies the idea the writer has just read"
    )

    expected_kill = kill_sentence.format(tier=tier, budget=budgets[tier])
    expected_intro = INTRO_LINE.format(cap=row.intro_cap)
    ordered = [
        ("the tier guidance", row.guidance),
        ("the term-budget kill sentence", expected_kill),
        ("the knob-defaults line", KNOB_LINE_PREFIX),
        ("the intro-pacing line", expected_intro),
    ]
    positions = []
    for what, needle in ordered:
        assert needle in section, (
            f"the tier section does not carry {what} ({needle[:60]!r}) — with every tier "
            f"knob armed the section carries all four parts. Section:\n{section}"
        )
        positions.append((what, section.index(needle)))
    for (prev_what, prev_at), (what, at) in pairwise(positions):
        assert prev_at < at, (
            f"{what} (offset {at}) does not follow {prev_what} (offset {prev_at}) — the "
            "contract freezes the order guidance, budget sentence, knob defaults, intro "
            "pacing, so the writer reads the paragraph before the rules it summarises"
        )


def test_each_tier_knob_governs_its_own_line(
    cfg: dict, good_spec: dict, budgets: dict[str, int], kill_sentence: str
) -> None:
    """Any one knob arms the section; each renders only its own part.

    Reading (c): the guidance paragraph is pinned PRESENT under
    `prompt_guidance=True` and is never pinned absent, so this test holds
    whether or not the implementation also emits it for the other knobs.
    """
    tier = "t1"
    row = tiers.TIER_TABLE[tier]
    idea = fixture_idea(good_spec, tier)
    expected_kill = kill_sentence.format(tier=tier, budget=budgets[tier])
    expected_intro = INTRO_LINE.format(cap=row.intro_cap)

    cases = {
        "prompt_guidance": (
            tiers.TierPolicy(prompt_guidance=True),
            [row.guidance],
            [expected_kill, KNOB_LINE_PREFIX, expected_intro],
        ),
        "term_budget": (
            tiers.TierPolicy(term_budget=dict(budgets), term_budget_action="kill"),
            [expected_kill],
            [KNOB_LINE_PREFIX, expected_intro],
        ),
        "knob_defaults_action": (
            tiers.TierPolicy(knob_defaults_action="warn"),
            [KNOB_LINE_PREFIX],
            [expected_kill, expected_intro],
        ),
        "intro_pacing_action": (
            tiers.TierPolicy(intro_pacing_action="warn"),
            [expected_intro],
            [expected_kill, KNOB_LINE_PREFIX],
        ),
    }
    for knob, (policy, present, absent) in cases.items():
        prompt = writer_prompt(cfg, idea, policy=policy)
        assert TIER_SECTION_MARK in prompt, (
            f"a policy with only {knob} active renders no tier section — the contract "
            "arms the section on ANY of prompt_guidance, term_budget, "
            "knob_defaults_action != 'off', intro_pacing_action != 'off'"
        )
        _head, section = tier_section(prompt)
        for needle in present:
            assert needle in section, (
                f"the tier section under a {knob}-only policy is missing its own part "
                f"({needle[:60]!r}) — each knob renders exactly the line it governs. "
                f"Section:\n{section}"
            )
        for needle in absent:
            assert needle not in section, (
                f"the tier section under a {knob}-only policy carries {needle[:60]!r}, "
                "which belongs to a knob this policy leaves off — the four parts are "
                "independently gated, or the 'off' setting means nothing"
            )


def test_knob_defaults_line_lists_the_values_at_or_under_each_ceiling(
    cfg: dict, good_spec: dict
) -> None:
    """The `/`-joined enum values per tier, plus the lever_max clause.

    Reading (d): only the refusal group's position is frozen (it sits inside
    the line's frozen prefix); the other two groups are pinned as present
    `/`-joined runs.
    """
    policy = tiers.TierPolicy(knob_defaults_action="warn")
    for tier in tiers.TIERS:
        row = tiers.TIER_TABLE[tier]
        prompt = writer_prompt(cfg, fixture_idea(good_spec, tier), policy=policy)
        _head, section = tier_section(prompt)
        line = knob_line(section)

        refusals = allowed_values(s1_spec.REFUSALS, tiers.REFUSAL_ORDINAL, row.refusal_max)
        goals = allowed_values(
            s1_spec.GOAL_LEGIBLE, tiers.GOAL_LEGIBLE_ORDINAL, row.goal_legible_max
        )
        tells = allowed_values(
            s1_spec.DANGER_TELLS, tiers.DANGER_TELL_ORDINAL, row.danger_tell_max
        )

        assert line.startswith(KNOB_LINE_PREFIX + refusals), (
            f"the {tier} knob line is {line!r} — it must open "
            f"{KNOB_LINE_PREFIX + refusals!r}: the allowed values are the enum members "
            "whose ordinal is at or under the tier's ceiling, '/'-joined in ENUM order, "
            "and a writer handed a wider list writes a spec the linter then rejects"
        )
        for what, group in (("goal_legible", goals), ("danger_tell", tells)):
            assert group in line, (
                f"the {tier} knob line does not carry the {what} group {group!r} "
                f"({line!r}) — all three ladders are summarised on this one line"
            )
        clause = LEVER_CLAUSE.format(lever_max=row.lever_max)
        assert clause in line, (
            f"the {tier} knob line does not carry {clause!r} ({line!r}) — the lever "
            "ceiling rides with the knob defaults, because tier-deceptions is governed "
            "by the same knob"
        )


def test_the_intro_cap_line_renders_only_for_a_tier_that_has_one(
    cfg: dict, good_spec: dict
) -> None:
    """t1 carries a cap; t2/t3 have none, so they carry no line."""
    policy = tiers.TierPolicy(intro_pacing_action="warn")
    for tier in tiers.TIERS:
        row = tiers.TIER_TABLE[tier]
        prompt = writer_prompt(cfg, fixture_idea(good_spec, tier), policy=policy)
        _head, section = tier_section(prompt)
        if row.intro_cap is None:
            assert "Levels after the first" not in section, (
                f"the {tier} section carries an intro-pacing line although "
                f"TIER_TABLE[{tier!r}].intro_cap is None — §3.3 sets no per-level "
                f"ceiling there. Section:\n{section}"
            )
            continue
        expected = INTRO_LINE.format(cap=row.intro_cap)
        assert expected in section, (
            f"the {tier} section does not carry {expected!r} — the line is frozen "
            f"verbatim (cap {row.intro_cap} read off TIER_TABLE). Section:\n{section}"
        )


def test_no_tier_section_for_an_unknown_or_missing_tier(
    cfg: dict, good_spec: dict, armed_policy
) -> None:
    """An idea without a known tier gets today's prompt, however armed the policy."""
    base = fixture_idea(good_spec, "t1")
    for label, idea in (
        ("no tier key", {k: v for k, v in base.items() if k != "tier"}),
        ("an unknown tier", {**base, "tier": "t9"}),
    ):
        prompt = writer_prompt(cfg, idea, policy=armed_policy)
        assert TIER_SECTION_MARK not in prompt, (
            f"an idea with {label} still rendered a tier section — the contract gates "
            "the section on idea['tier'] in tiers.TIERS, because there is no row to "
            "quote otherwise"
        )


# --- Pin 1: knob-off byte-identity ------------------------------------------


def test_every_shipped_spec_lints_identically_with_no_policy_and_with_none(
    shipped: dict[str, dict], vocab: dict
) -> None:
    """The whole shipped corpus: `tier_policy=None` is today's linter."""
    assert len(shipped) >= 3, (
        f"only {len(shipped)} shipped specs under {CORPUS_ROOT} ({sorted(shipped)}) — "
        "the knob-off replay is measured on the shipped corpus and the contract expects "
        "at least three"
    )
    unpaired = []
    for slug, game in sorted(shipped.items()):
        idea = game["idea"]
        if idea is None:
            unpaired.append(slug)
        without = report_dict(lint(game["spec"], vocab, idea))
        with_none = report_dict(lint(game["spec"], vocab, idea, policy=None))
        assert without == with_none, (
            f"{slug} lints differently with the tier parameter omitted and with "
            f"tier_policy=None:\n  omitted: {without}\n  None:    {with_none}\n"
            "— None is the documented 'no policy' value and must reproduce the "
            "pre-tier report exactly, or every existing lint-report artifact is invalid"
        )
    assert not unpaired, (
        f"these shipped specs were linted with idea=None because their idea.json id "
        f"does not equal their game.idea_ref: {unpaired} — the identity pin still holds "
        "unpaired, but the linkage is worth knowing (reading (e))"
    )


def test_writer_prompt_is_byte_identical_when_the_policy_is_omitted_or_none(
    cfg: dict, shipped: dict[str, dict]
) -> None:
    """A real b002 idea: omitted, None — same bytes, and no tier section."""
    idea = shipped_game(shipped, PUMP)["idea"]
    omitted = writer_prompt(cfg, idea)
    explicit_none = writer_prompt(cfg, idea, policy=None)

    assert omitted == explicit_none, (
        "build_writer_prompt(cfg, idea) and build_writer_prompt(cfg, idea, "
        "tier_policy=None) produced different bytes — the parameter's default IS None, "
        "so the two calls are the same call"
    )
    assert TIER_SECTION_MARK not in omitted, (
        f"the no-policy writer prompt carries {TIER_SECTION_MARK!r} — with no policy "
        "there is no tier contract to state, and the b002 prompts are the byte baseline "
        "this workstream is measured against"
    )


def test_an_all_off_policy_renders_no_tier_section(cfg: dict, good_spec: dict) -> None:
    """A defaulted TierPolicy activates nothing: today's prompt, today's bytes."""
    default = tiers.TierPolicy()
    prompt = writer_prompt(cfg, fixture_idea(good_spec, "t1"), policy=default)

    assert TIER_SECTION_MARK not in prompt, (
        "a defaulted TierPolicy (prompt_guidance False, term_budget None, "
        "knob_defaults_action 'off', intro_pacing_action 'off') still rendered a tier "
        "section — every TierPolicy field defaults to today's behaviour, so a config "
        "that writes an empty tiers block must change nothing"
    )


# --- Pin 2: one string, two consumers ---------------------------------------


def test_one_kill_sentence_reaches_both_the_writer_and_the_linter(
    cfg: dict, shipped: dict[str, dict], vocab: dict, budgets: dict[str, int],
    budget_policy, kill_sentence: str
) -> None:
    """The prompt quotes the sentence the finding then starts with."""
    game = shipped_game(shipped, PUMP)
    idea = game["idea"]
    tier = idea.get("tier")
    assert tier == "t1", (
        f"the shipped {PUMP} idea is at tier {tier!r}, not 't1' — the prompt-sync pin is "
        "measured on the one shipped t1 idea, and the budget it quotes is that tier's"
    )
    assert budgets["t1"] == 6, (
        f"tiers.DEFAULT_TERM_BUDGETS['t1'] is {budgets['t1']}, not the measured 6 (the "
        "officials' p25 n_terms) — the contract's sync pin is written against 6, so a "
        "moved budget has to be re-adjudicated"
    )
    assert budget_policy.prompt_guidance is False, (
        "the prompt-sync pin is written with prompt_guidance False on purpose: the kill "
        "sentence is the SYNC guarantee and ships whether or not the guidance does"
    )

    sentence = kill_sentence.format(tier="t1", budget=budgets["t1"])
    prompt = writer_prompt(cfg, idea, policy=budget_policy)
    assert sentence in prompt, (
        f"the writer prompt does not carry {sentence!r} — with term_budget set the "
        "sentence renders EVEN when prompt_guidance is False, because the writer and "
        "the linter must be told the budget in the same words"
    )

    report = lint(game["spec"], vocab, idea, policy=budget_policy)
    hits = kills_for(report, RULE_TERMS)
    n_terms = len(game["spec"]["game"]["terms"])
    assert len(hits) == 1, (
        f"linting {PUMP} ({n_terms} terms against a t1 budget of {budgets['t1']}) under "
        f"term_budget_action='kill' produced {len(hits)} {RULE_TERMS} kills "
        f"({hits}) — one over-budget spec is one finding"
    )
    detail = hits[0]["detail"]
    assert detail.startswith(sentence), (
        f"the {RULE_TERMS} detail is {detail!r}, which does not START WITH the writer's "
        f"own sentence {sentence!r} — one string, two consumers: the rejected writer has "
        "to read back the exact rule it was given"
    )
    assert detail[len(sentence):] == f" This spec declares {n_terms}.", (
        f"the {RULE_TERMS} detail tail is {detail[len(sentence):]!r}, not "
        f"{' This spec declares ' + str(n_terms) + '.'!r} — the contract freezes the "
        "detail as the formatted sentence plus that one count clause"
    )


# --- Pin 3: the retro matrix ------------------------------------------------


def test_the_armed_policy_kills_every_shipped_spec_over_its_budget(
    shipped: dict[str, dict], vocab: dict, budgets: dict[str, int], armed_policy
) -> None:
    """The three b002 games, retro-linted against the measured budgets."""
    for slug in (PUMP, CORE_WARD, CONVOY):
        game = shipped_game(shipped, slug)
        idea = game["idea"]
        tier = idea.get("tier")
        n_terms = len(game["spec"]["game"]["terms"])
        assert tier in budgets, (
            f"the shipped {slug} idea carries tier {tier!r}, which has no budget in "
            f"{budgets} — the retro matrix is measured per tier"
        )
        assert n_terms > budgets[tier], (
            f"{slug} declares {n_terms} terms at tier {tier} against a budget of "
            f"{budgets[tier]} — the contract's matrix says all three shipped games are "
            "OVER their budget (that is the measurement the budgets were drawn from); "
            "if the artifact changed, the matrix has to be re-measured"
        )

        report = lint(game["spec"], vocab, idea, policy=armed_policy)
        hits = kills_for(report, RULE_TERMS)
        assert hits, (
            f"{slug} ({n_terms} terms, tier {tier}, budget {budgets[tier]}) produced no "
            f"{RULE_TERMS} kill under term_budget_action='kill' — every shipped game is "
            "over budget, which is the whole reason the budget rule exists"
        )
        assert str(n_terms) in hits[0]["detail"], (
            f"the {slug} {RULE_TERMS} detail ({hits[0]['detail']!r}) never states the "
            f"{n_terms} terms the spec actually declares — the finding has to name the "
            "measured count, not only the ceiling"
        )


def test_warn_action_moves_the_same_findings_into_warns(
    shipped: dict[str, dict], vocab: dict, budgets: dict[str, int]
) -> None:
    """Same findings, other list, and `passed` is the no-policy verdict."""
    warn_policy = tiers.TierPolicy(
        term_budget=dict(budgets),
        term_budget_action="warn",
        knob_defaults_action="warn",
        intro_pacing_action="warn",
    )
    kill_policy = dataclasses.replace(warn_policy, term_budget_action="kill")

    for slug in (PUMP, CORE_WARD, CONVOY):
        game = shipped_game(shipped, slug)
        idea = game["idea"]
        killed = lint(game["spec"], vocab, idea, policy=kill_policy)
        warned = lint(game["spec"], vocab, idea, policy=warn_policy)
        baseline = lint(game["spec"], vocab, idea)

        assert kills_for(warned, RULE_TERMS) == [], (
            f"{slug} still produced {RULE_TERMS} KILLS under term_budget_action='warn' "
            f"({kills_for(warned, RULE_TERMS)}) — the action knob decides the list, and "
            "'warn' is the setting a batch uses to measure a budget before enforcing it"
        )
        assert warns_for(warned, RULE_TERMS) == kills_for(killed, RULE_TERMS), (
            f"{slug}'s warn-action findings {warns_for(warned, RULE_TERMS)} are not the "
            f"kill-action findings {kills_for(killed, RULE_TERMS)} — only the severity "
            "moves; the detail is the same sentence either way"
        )
        assert report_dict(warned)["passed"] == report_dict(baseline)["passed"], (
            f"{slug}'s `passed` changed from {report_dict(baseline)['passed']} to "
            f"{report_dict(warned)['passed']} under an all-warn policy — warns never "
            "move the verdict (`passed` is exactly `kills == []`), which is what makes "
            "'warn' a safe measuring setting"
        )


# --- Pin 4: the ordinal ceilings --------------------------------------------


@pytest.fixture()
def knob_policy():
    """Knob defaults warning, nothing else armed — pin 4's isolation."""
    return tiers.TierPolicy(knob_defaults_action="warn")


def test_a_clean_t1_spec_trips_no_ceiling(good_spec: dict, vocab: dict, knob_policy) -> None:
    """The fixture spec at t1: every knob at or under its ceiling."""
    spec = deepcopy(good_spec)
    knobs = spec["game"]["knobs"]
    assert (knobs["refusal"], knobs["goal_legible"]) == ("visible", "obvious"), (
        f"the fixture spec's knobs moved ({knobs}) — pin 4 is built on a spec whose "
        "refusal and goal_legible sit at the t1 floor, so the mutations below are the "
        "only thing under test"
    )
    report = lint(spec, vocab, fixture_idea(good_spec, "t1"), policy=knob_policy)

    assert findings(report, RULE_KNOBS) == [], (
        f"the clean fixture spec produced {findings(report, RULE_KNOBS)} at t1 — "
        "'visible' and 'obvious' are the t1 ceilings themselves, and the ceiling is "
        "INCLUSIVE"
    )
    assert findings(report, RULE_LEVERS) == [], (
        f"the clean fixture spec (no declared deceptions) produced "
        f"{findings(report, RULE_LEVERS)} at t1 — zero declared levers is exactly the "
        "t1 lever_max"
    )


def test_a_refusal_above_the_ceiling_is_flagged_under_both_actions(
    good_spec: dict, vocab: dict
) -> None:
    """`silent-charged` at t1: a warn under warn, a kill under kill."""
    spec = deepcopy(good_spec)
    spec["game"]["knobs"]["refusal"] = "silent-charged"
    idea = fixture_idea(good_spec, "t1")
    assert tiers.REFUSAL_ORDINAL["silent-charged"] > tiers.TIER_TABLE["t1"].refusal_max, (
        "tiers no longer ranks 'silent-charged' above the t1 refusal ceiling — the "
        "mutation this pin is built on is not a violation any more"
    )

    warned = lint(spec, vocab, idea, policy=tiers.TierPolicy(knob_defaults_action="warn"))
    killed = lint(spec, vocab, idea, policy=tiers.TierPolicy(knob_defaults_action="kill"))

    assert warns_for(warned, RULE_KNOBS), (
        f"a t1 spec declaring refusal 'silent-charged' produced no {RULE_KNOBS} warn "
        f"(warns: {report_dict(warned)['warns']}) — silent-charged is the t3 pattern "
        "(17/25 officials) and is two full ranks above an entry-tier game"
    )
    assert any("silent-charged" in f["detail"] for f in warns_for(warned, RULE_KNOBS)), (
        f"the {RULE_KNOBS} warn never names the offending value 'silent-charged' "
        f"({warns_for(warned, RULE_KNOBS)}) — a ceiling finding has to say which knob "
        "value broke it"
    )
    assert kills_for(killed, RULE_KNOBS), (
        f"the same spec under knob_defaults_action='kill' produced no {RULE_KNOBS} kill "
        f"(kills: {report_dict(killed)['kills']}) — the action knob decides the list"
    )
    assert warns_for(killed, RULE_KNOBS) == [], (
        f"knob_defaults_action='kill' left {RULE_KNOBS} findings in warns "
        f"({warns_for(killed, RULE_KNOBS)}) — a rule reports at one severity, not two"
    )


def test_a_goal_above_the_ceiling_is_flagged_and_the_ceiling_value_is_not(
    good_spec: dict, vocab: dict, knob_policy
) -> None:
    """`opaque` at t1 fires; `obvious` (the ceiling itself) does not."""
    idea = fixture_idea(good_spec, "t1")

    opaque = deepcopy(good_spec)
    opaque["game"]["knobs"]["goal_legible"] = "opaque"
    report = lint(opaque, vocab, idea, policy=knob_policy)
    assert any("opaque" in f["detail"] for f in findings(report, RULE_KNOBS)), (
        f"a t1 spec declaring goal_legible 'opaque' produced {findings(report, RULE_KNOBS)} "
        "— an entry-tier game's goal is obvious from the first frame, and 'opaque' is "
        "the t3 value"
    )

    obvious = deepcopy(good_spec)
    obvious["game"]["knobs"]["goal_legible"] = "obvious"
    clean = lint(obvious, vocab, idea, policy=knob_policy)
    assert findings(clean, RULE_KNOBS) == [], (
        f"goal_legible 'obvious' — the t1 ceiling itself — produced "
        f"{findings(clean, RULE_KNOBS)}; the ordinal comparison is `<=`"
    )


def test_a_none_tell_is_exempt_while_the_game_is_hazardless(
    good_spec: dict, vocab: dict, knob_policy
) -> None:
    """The exemption `gen/tiers.py` says the enforcer owes `danger_tell: none`."""
    idea = fixture_idea(good_spec, "t1")
    assert good_spec["game"]["knobs"]["danger_tell"] == "none", (
        "the fixture spec no longer declares danger_tell 'none' — this pin is the "
        "hazardless exemption and needs a hazardless spec that declares it"
    )
    assert not [
        term for term in good_spec["game"]["terms"] if term.startswith(s1_spec.HAZARD_PREFIXES)
    ], (
        f"the fixture spec's terms {good_spec['game']['terms']} now carry a "
        f"{s1_spec.HAZARD_PREFIXES} term — the exemption half of this pin needs a game "
        "with no danger at all"
    )
    assert tiers.DANGER_TELL_ORDINAL["none"] > tiers.TIER_TABLE["t1"].danger_tell_max, (
        "'none' no longer ranks above the t1 danger ceiling — without that rank there "
        "is nothing for the hazardless exemption to exempt"
    )

    hazardless = lint(deepcopy(good_spec), vocab, idea, policy=knob_policy)
    assert findings(hazardless, RULE_KNOBS) == [], (
        f"a HAZARDLESS t1 spec declaring danger_tell 'none' produced "
        f"{findings(hazardless, RULE_KNOBS)} — 'none' ranks 2 only because §3.3 lists it "
        "in the t3 column; with no hazard.*/loss.* term there is no danger to tell, and "
        "flagging it would reject every honest entry-tier game"
    )

    hazard_terms = sorted(t for t in vocab if t.startswith(s1_spec.HAZARD_PREFIXES))
    assert hazard_terms, (
        f"the closed vocabulary carries no term starting with {s1_spec.HAZARD_PREFIXES} "
        "— the hazard half of this pin cannot be built"
    )
    hazardous = deepcopy(good_spec)
    hazardous["game"]["terms"] = [*hazardous["game"]["terms"], hazard_terms[0]]
    report = lint(hazardous, vocab, idea, policy=knob_policy)
    assert findings(report, RULE_KNOBS), (
        f"a t1 spec declaring danger_tell 'none' WITH the hazard term "
        f"{hazard_terms[0]!r} produced no {RULE_KNOBS} finding — the exemption is for "
        "hazardless games only; a game that HAS danger and shows no tell for it is the "
        "hard end of the tell ladder and is exactly what the t1 ceiling excludes"
    )


# --- Pin 5: distinct-lever counting -----------------------------------------


def test_repeated_prose_for_one_lever_counts_once(good_spec: dict, vocab: dict) -> None:
    """Three entries, one catalog keyword: one lever, inside the t2 max."""
    keywords = unambiguous_keywords()
    assert len(keywords) >= 2, (
        f"only {keywords} of gen.s1_spec.DECEPTION_CATALOG are unambiguous — pin 5 needs "
        "two keywords that no other catalog entry can be confused with (look-alike and "
        "lookalike squash to the same string and are excluded on purpose)"
    )
    spec = deepcopy(good_spec)
    spec["game"]["knobs"]["deceptions"] = [
        lever_entry(keywords[0], "the second belt reads as ordinary track"),
        lever_entry(keywords[0], "the east yard repeats that same trick one level later"),
        lever_entry(keywords[0], "and once more on the shared spur, for the last pad"),
    ]
    row = tiers.TIER_TABLE["t2"]
    assert row.lever_max == 1, (
        f"TIER_TABLE['t2'].lever_max is {row.lever_max}, not the 1 this pin is written "
        "against — §3.3 allows core-tier games at most one declared lever"
    )

    report = lint(
        spec, vocab, fixture_idea(good_spec, "t2"),
        policy=tiers.TierPolicy(knob_defaults_action="warn"),
    )
    assert findings(report, RULE_LEVERS) == [], (
        f"three entries all describing {keywords[0]!r} produced "
        f"{findings(report, RULE_LEVERS)} at t2 (lever_max 1) — the count is over "
        "DISTINCT catalog keywords, so restating one lever in three sentences is still "
        "one lever, and counting entries would punish a spec for being explicit"
    )


def test_two_catalog_keywords_exceed_the_t2_lever_max(good_spec: dict, vocab: dict) -> None:
    """Two different keywords: two levers, over the t2 max of one."""
    keywords = unambiguous_keywords()
    spec = deepcopy(good_spec)
    spec["game"]["knobs"]["deceptions"] = [
        lever_entry(keywords[0], "the second belt reads as ordinary track"),
        lever_entry(keywords[1], "one junction in the west yard does nothing at all"),
    ]

    report = lint(
        spec, vocab, fixture_idea(good_spec, "t2"),
        policy=tiers.TierPolicy(knob_defaults_action="warn"),
    )
    hits = findings(report, RULE_LEVERS)
    assert hits, (
        f"a t2 spec declaring {keywords[0]!r} and {keywords[1]!r} — two distinct catalog "
        f"keywords against lever_max 1 — produced no {RULE_LEVERS} finding; two levers "
        "is where a core-tier game stops being core-tier"
    )


def test_an_uncatalogued_entry_counts_as_a_lever_of_its_own(
    good_spec: dict, vocab: dict
) -> None:
    """1 keyword + 1 unmatched entry = 2 > 1, or the catalog is a loophole."""
    keywords = unambiguous_keywords()
    freeform = "the west gantry runs on an unusual schedule the player has to learn"
    assert matched_keywords(freeform) == set(), (
        f"the fixture entry {freeform!r} matches the catalog keywords "
        f"{sorted(matched_keywords(freeform))} — this half of the pin needs prose that "
        "matches NO keyword"
    )
    spec = deepcopy(good_spec)
    spec["game"]["knobs"]["deceptions"] = [
        lever_entry(keywords[0], "the second belt reads as ordinary track"),
        freeform,
    ]

    report = lint(
        spec, vocab, fixture_idea(good_spec, "t2"),
        policy=tiers.TierPolicy(knob_defaults_action="warn"),
    )
    hits = findings(report, RULE_LEVERS)
    assert hits, (
        f"a t2 spec declaring {keywords[0]!r} plus one entry matching no catalog keyword "
        f"produced no {RULE_LEVERS} finding — an entry outside the catalog counts as one "
        "lever of its own (1 + 1 = 2 > 1); counting only catalog hits would let a spec "
        "declare any number of levers by avoiding the eleven words"
    )


# --- Pin 6: intro pacing ----------------------------------------------------


def paced_spec(good_spec: dict, offenders: tuple[int, ...]) -> dict:
    """The fixture spec with each 1-based level in `offenders` introducing 2 terms.

    Every other level after the first introduces at most one term, and every
    declared term is still introduced exactly once.
    """
    spec = deepcopy(good_spec)
    levels = spec["game"]["levels"]
    terms = list(spec["game"]["terms"])
    assert len(terms) >= 2 * len(offenders) + 1, (
        f"the fixture spec declares {len(terms)} terms — not enough to seat "
        f"{len(offenders)} two-term levels plus a first level"
    )
    for level in levels:
        level["terms_introduced"] = []
    pool = list(terms)
    for number in offenders:
        assert 2 <= number <= len(levels), (
            f"level {number} is not a level AFTER the first in a {len(levels)}-level "
            "spec — the cap applies to levels[1:] only"
        )
        levels[number - 1]["terms_introduced"] = [pool.pop(), pool.pop()]
    levels[0]["terms_introduced"] = pool
    return spec


def test_intro_pacing_reports_one_finding_naming_every_offending_level(
    good_spec: dict, vocab: dict
) -> None:
    """One finding; the 1-based level numbers, not the list positions."""
    row = tiers.TIER_TABLE["t1"]
    assert row.intro_cap == 1, (
        f"TIER_TABLE['t1'].intro_cap is {row.intro_cap}, not the 1 this pin is written "
        "against — §3.3 lets an entry-tier game introduce one new term per level"
    )
    policy = tiers.TierPolicy(intro_pacing_action="warn")
    idea = fixture_idea(good_spec, "t1")

    single = lint(paced_spec(good_spec, (6,)), vocab, idea, policy=policy)
    hits = findings(single, RULE_PACING)
    assert len(hits) == 1, (
        f"one over-paced level produced {len(hits)} {RULE_PACING} findings ({hits}) — "
        "the contract reports ONE finding naming every offending level, not one per level"
    )
    assert 6 in [int(n) for n in re.findall(r"\d+", hits[0]["detail"])], (
        f"the {RULE_PACING} detail {hits[0]['detail']!r} never names level 6 — levels are "
        "named by their 1-BASED number, the way the corpus and the HUD count them"
    )

    both = lint(paced_spec(good_spec, (3, 6)), vocab, idea, policy=policy)
    hits = findings(both, RULE_PACING)
    assert len(hits) == 1, (
        f"two over-paced levels produced {len(hits)} {RULE_PACING} findings ({hits}) — "
        "one finding names them all"
    )
    numbers = {int(n) for n in re.findall(r"\d+", hits[0]["detail"])}
    assert {3, 6} <= numbers, (
        f"the {RULE_PACING} detail {hits[0]['detail']!r} names {sorted(numbers)} — both "
        "offending levels (3 and 6, 1-based) have to appear; naming only 2 and 5 would "
        "be the 0-based list positions"
    )


def test_intro_pacing_is_silent_for_a_tier_with_no_cap(good_spec: dict, vocab: dict) -> None:
    """The same spec at t2: §3.3 sets no per-level ceiling there."""
    assert tiers.TIER_TABLE["t2"].intro_cap is None, (
        "TIER_TABLE['t2'].intro_cap is no longer None — this pin is the 'no cap, no "
        "rule' half and needs a tier whose canon row sets none"
    )
    spec = paced_spec(good_spec, (6,))
    report = lint(
        spec, vocab, fixture_idea(good_spec, "t2"),
        policy=tiers.TierPolicy(intro_pacing_action="warn"),
    )
    assert findings(report, RULE_PACING) == [], (
        f"a t2 spec produced {findings(report, RULE_PACING)} — the rule fires only where "
        "the tier row sets an intro_cap, and a None cap is not a cap of zero"
    )


def test_intro_pacing_is_silent_when_its_action_is_off(good_spec: dict, vocab: dict) -> None:
    """`off` is the default and it means off, over-paced spec or not."""
    spec = paced_spec(good_spec, (6,))
    idea = fixture_idea(good_spec, "t1")
    off = tiers.TierPolicy(intro_pacing_action="off", knob_defaults_action="warn")
    assert tiers.TierPolicy().intro_pacing_action == "off", (
        "TierPolicy.intro_pacing_action no longer defaults to 'off' — every tier field "
        "defaults to today's behaviour"
    )

    report = lint(spec, vocab, idea, policy=off)
    assert findings(report, RULE_PACING) == [], (
        f"intro_pacing_action='off' still produced {findings(report, RULE_PACING)} — "
        "'off' is the rule's own knob and the default, so a batch that never opts in "
        "must never see this rule"
    )


# --- Pin 7: the escalation exemption ----------------------------------------


def test_escalation_lint_policy_zeroes_the_budget_and_nothing_else(armed_policy) -> None:
    """None -> None; otherwise the same policy minus `term_budget`."""
    strip = _require("escalation_lint_policy")

    assert strip(None) is None, (
        "escalation_lint_policy(None) is not None — no policy in, no policy out; a "
        "batch without a tiers block must not acquire one on an escalation"
    )

    stripped = strip(armed_policy)
    assert stripped is not None, (
        "escalation_lint_policy(<armed policy>) returned None — an escalation exempts "
        "the TERM BUDGET only; the ceilings, the lever max and the pacing rule still "
        "hold on a re-spec"
    )
    assert stripped.term_budget is None, (
        f"the stripped policy still carries term_budget={stripped.term_budget!r} — a "
        "§3 escalation re-specs an existing game, and holding it to the budget it was "
        "already written over would kill the rewrite before it starts"
    )
    for field in dataclasses.fields(tiers.TierPolicy):
        if field.name == "term_budget":
            continue
        assert getattr(stripped, field.name) == getattr(armed_policy, field.name), (
            f"escalation_lint_policy changed {field.name} from "
            f"{getattr(armed_policy, field.name)!r} to "
            f"{getattr(stripped, field.name)!r} — it zeroes ONE field and leaves the "
            "policy otherwise identical"
        )


def test_escalation_drops_tier_terms_and_keeps_every_other_tier_finding(
    shipped: dict[str, dict], vocab: dict, armed_policy
) -> None:
    """The over-budget shipped spec: budget forgiven, everything else still held."""
    strip = _require("escalation_lint_policy")
    game = shipped_game(shipped, PUMP)
    idea = game["idea"]

    full = lint(game["spec"], vocab, idea, policy=armed_policy)
    stripped = lint(game["spec"], vocab, idea, policy=strip(armed_policy))

    assert kills_for(full, RULE_TERMS), (
        f"{PUMP} produced no {RULE_TERMS} kill under the full policy — this pin needs an "
        "over-budget spec to forgive"
    )
    assert findings(stripped, RULE_TERMS) == [], (
        f"the escalation lint still produced {findings(stripped, RULE_TERMS)} — the "
        "stripped policy has no term_budget, and the rule fires only when one is set"
    )

    others = [f for f in tier_findings(full) if f["rule"] != RULE_TERMS]
    assert others, (
        f"{PUMP} produced no tier finding other than {RULE_TERMS} under the armed policy "
        f"({tier_findings(full)}) — this pin needs one surviving finding to prove the "
        "exemption is narrow; the shipped spec's declared levers and level pacing are "
        "what it was measured on"
    )
    survivors = tier_findings(stripped)
    missing = [f for f in others if f not in survivors]
    assert not missing, (
        f"the escalation lint dropped {missing} (kept {survivors}) — escalation exempts "
        "the term budget and NOTHING else; a re-spec that can quietly raise its refusal "
        "or its lever count has left its tier altogether"
    )


# --- Pin 9: purity ----------------------------------------------------------


def test_lint_spec_is_pure_under_a_tier_policy(
    shipped: dict[str, dict], vocab: dict, armed_policy
) -> None:
    """Same inputs, same report; the policy and the spec come back untouched."""
    game = shipped_game(shipped, CORE_WARD)
    spec = deepcopy(game["spec"])
    idea = deepcopy(game["idea"])
    spec_before = deepcopy(spec)
    idea_before = deepcopy(idea)
    policy_before = deepcopy(armed_policy)

    first = report_dict(lint(spec, vocab, idea, policy=armed_policy))
    second = report_dict(lint(spec, vocab, idea, policy=armed_policy))

    assert first == second, (
        f"two identical lint_spec calls returned different reports:\n  {first}\n  "
        f"{second}\n— lint_spec is PURE (no config, no disk); a tier rule that carries "
        "state between calls makes every lint-report artifact unreproducible"
    )
    assert spec == spec_before, (
        "lint_spec mutated the spec dict it was handed — the caller re-serializes that "
        "same dict to disk, so an in-place edit inside the linter rewrites the game"
    )
    assert idea == idea_before, (
        "lint_spec mutated the idea dict it was handed — ideas are immutable by contract "
        "once drawn (the b002 idea-immutability machinery depends on it)"
    )
    assert armed_policy == policy_before, (
        "lint_spec mutated the TierPolicy it was handed — one policy is parsed per batch "
        "and reused for every game in it, so a linter that edits it leaks one game's "
        "state into the next"
    )
