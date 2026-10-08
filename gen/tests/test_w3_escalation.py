"""Blind pins for the escalation shape — contract A2 / R-11 (test-writer half).

Written from the frozen A2 contract ALONE. No implementer diff of
`gen/s1_spec.py` or `gen/tiers.py` was read — not the module, not a patch, not
a report — so every expectation below is the contract's own words turned into
an assertion, and a pin that fails is a disagreement between the contract and
the landed code rather than a test fitted to it. What WAS read: the PRE-STATE
of both files (`git show HEAD:gen/s1_spec.py`, `git show HEAD:gen/tiers.py` at
24d499c), the shipped corpus under `out/` (read-only, copied to tmp before
use), the spec fixtures, and the sibling suites' house style.

The contract, as this file reads it:

  * `RELATIONS` gains `invert` — a level that flips a standing rule. It is NOT
    `new` for the ≤2-consecutive-`new` rule, and (the contract's own
    recommendation) it does NOT satisfy the ≥1-`reuse` requirement: reuse
    stays reuse. Every RELATIONS consumer follows, the §7 prompt text included.
  * `COMPLEXITY_OVERRIDE` stops being a blanket ban and becomes TIER-GATED: t1
    keeps the composition-first line verbatim, t2/t3 state the officials'
    measured rate (~1 new mechanic per 2 levels — `new` on 44.9% of non-first
    levels) as the TARGET, with the term budget named as the ceiling that
    makes bounded novelty safe.
  * A new FIDELITY_RULES entry `silent-levels` warns/kills when the share of
    NON-FIRST levels with an empty `terms_introduced` EXCEEDS a floor
    (default 0.5, config-tunable, loud on bad values). DEFAULT OFF; the
    template arms it at `warn`.
  * S1's curriculum prompt section gains an escalation-axis line naming the
    drawn tier's target relation mix, as a named prompt-synced constant citing
    `escalation.csv`.
  * Unconfigured, nothing moves: the 7 shipped specs re-lint to their own
    shipped `lint-report.json`, rule for rule.

Contract readings this file encodes where A2 left a choice open — each one is
a line to renegotiate, not a fact:

  * REUSE CREDIT IS AN ADJUDICATION PIN. The contract says "decide + document
    whether [invert] satisfies the ≥1-reuse requirement — recommendation: no,
    reuse stays reuse". There is no knob to pin both branches through, so
    `test_invert_does_not_buy_the_reuse_credit` pins the RECOMMENDATION. If
    the implementer documented the other choice, that test is the adjudication
    point and the lead rules — it is not a bug report.
  * TIER-GATING IS PINNED ON THE EFFECTIVE TEXT, not on a shape. A2 may not
    touch `gen/s0_ideas.py`, whose prose prompt renders `COMPLEXITY_OVERRIDE`
    immediately followed by `TIER_TABLE[tier].guidance` (the T-A suite pins
    exactly that adjacency), so the tier-specific words may legitimately land
    in EITHER constant. `_tier_complexity_text` therefore reads both — plus a
    tier-keyed map or a `complexity_override(tier)` callable, if that is the
    shape chosen — and the pins assert on what the tier's prompt actually
    carries.
  * The blanket ban is pinned ABSENT from t2/t3. "t1 keeps the composition-
    first line" is read as "t1 alone keeps it": a t2 prompt carrying both the
    ban and the bounded allowance argues with itself, which is the failure
    R-11 exists to end.
  * The novelty TARGET is pinned absent from t1, the mirror of the reading
    above: A2 §2 gives the measured rate to "t2/t3" and t1 the composition-
    first line, so a t1 prompt stating a ~45%-new target reads as the gate
    applied to the wrong side. This is a derived reading, not a quoted one —
    a second line to renegotiate if the implementer states the rate at every
    tier and gates only the ALLOWANCE.
  * "Exceeds a floor" is read STRICTLY, as the contract's verification line
    spells out ("fires on conduit-class front-loading and not on a spec at the
    floor"): share == floor is silent. `facing-sentinel` ships at exactly
    3/6 = 0.500 and is used as the live at-floor exhibit.
  * The floor's config seam is DISCOVERED, not assumed (constant, `lint_spec`
    keyword, or a `lint:` reader — the contract names none of them). The pins
    fail loudly, naming what was searched, if no seam exists at all.
  * The axis constant is DISCOVERED by its own citation: a module-level string
    in `gen.s1_spec` that cites `escalation.csv`. At HEAD no such constant
    exists and the word "invert" appears nowhere in a built writer prompt, so
    both discovery pins are contract-bearing rather than tautological.
  * DELIBERATELY NOT PINNED: which prompt SECTION the axis line joins (the
    contract says "S1's curriculum prompt section"; the pins assert on the
    whole rendered prompt, so any placement passes), and the exact wording of
    the `silent-levels` finding detail.

Run: .venv/bin/python -m pytest gen/tests/test_w3_escalation.py -v

No driver, no network, no writes outside tmp_path: every test lints in memory
and reads `out/` only through tmp copies.
"""

from __future__ import annotations

import inspect
import json
import re
import shutil
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from gen import s1_spec, tiers
from gen.config import REPO_ROOT, load_config
from gen.s0_ideas import load_vocab
from gen.tiers import TierPolicy

PILOT = "config/b001-pilot.yaml"
TEMPLATE_PATH = REPO_ROOT / "config" / "template.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "specs"
GOOD_PATH = FIXTURES / "good-spec.yaml"
IDEA_PATH = FIXTURES / "idea-001.json"
CORPUS_ROOT = REPO_ROOT / "out" / "corpus"

lint = s1_spec.lint_spec

# --- contract-frozen strings (the only text in this file that is quoted) ----
# The rule id A2 names, and the `lint:` key the registry's own documented
# convention spells for it ("the rule id's hyphens written as underscores").
SILENT_RULE = "silent-levels"
SILENT_KEY = "silent_levels_action"
DEFAULT_FLOOR = 0.5

# HEAD's composition-first line, quoted because A2 says t1 keeps it VERBATIM.
COMPOSITION_FIRST_LINE = (
    "Difficulty comes from legibility, layout, and composition of the SAME mechanics — never "
    "from adding mechanics."
)
# The half of it R-11 lifts for t2/t3: the blanket ban on novelty.
BLANKET_BAN = "never from adding mechanics"

# The officials' measured escalation rate, in any spelling a writer would use.
OFFICIAL_RATE_RE = re.compile(
    r"44\.9|4[45]\s*%|per\s+2\s+levels|per\s+two\s+levels|every\s+other\s+level|"
    r"half\s+(?:of\s+)?(?:the\s+)?(?:non-first\s+)?levels",
    re.IGNORECASE,
)
# The ceiling that makes bounded novelty safe has to be NAMED beside the rate.
CEILING_RE = re.compile(r"budget|ceiling", re.IGNORECASE)

# The axis line's four shares, each tolerant of the rounded and the measured
# spelling (45 / 44.9, 27 / 27.2, 26 / 25.9).
AXIS_SHARE_RES = {
    "new": re.compile(r"4[45](?:\.\d)?\s*%"),
    "compose": re.compile(r"27(?:\.\d)?\s*%"),
    "reuse": re.compile(r"2[56](?:\.\d)?\s*%"),
}

# The shipped spec dirs at contract time. The glob is the rule; this tuple only
# guards against a glob that quietly matches nothing on a tree that HAS run.
FROZEN_SHIPPED = (
    "pump-flow-match-glow",
    "convoy-in-the-fog",
    "core-ward-phase-gates",
    "pump-phase-time-echo",
    "facing-sentinel-match-the-signal-row",
    "conduit-watch",
    "mosaic-marble-bounce-to-match",
)
# The two corpus exhibits the contract names by their measured silent share:
# conduit is 7/7 = 1.000 (front-loaded) and facing-sentinel is 3/6 = 0.500
# (exactly at the default floor).
CONDUIT = "conduit-watch"
AT_FLOOR_SPEC = "facing-sentinel-match-the-signal-row"

_OMITTED = object()


def _shipped_dirs() -> list[Path]:
    return sorted(
        path.parent
        for path in CORPUS_ROOT.glob("*/*/spec.yaml")
        if ".killed" not in path.parts and (path.parent / "lint-report.json").is_file()
    )


SHIPPED_DIRS = _shipped_dirs()
SHIPPED_IDS = [f"{path.parent.name}/{path.name}" for path in SHIPPED_DIRS]
needs_corpus = pytest.mark.skipif(
    not SHIPPED_DIRS,
    reason=(
        "no shipped spec dir under out/corpus — the live-run tree is gitignored, so the "
        "parity pin has nothing to read on this checkout"
    ),
)


# --------------------------------------------------------------------------
# fixtures and helpers
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def vocab() -> set[str]:
    return set(load_vocab(load_config(PILOT)))


@pytest.fixture(scope="module")
def idea() -> dict:
    """The hand-written t2 fixture idea (the real pilot idea's facets)."""
    return json.loads(IDEA_PATH.read_text(encoding="utf-8"))


def _good_spec() -> dict:
    """A fresh parse of the hand-written §11 fixture (never a shared dict)."""
    return yaml.safe_load(GOOD_PATH.read_text(encoding="utf-8"))


def _findings(report) -> list[dict]:
    return [*report.kills, *report.warns]


def _rules(findings) -> list[str]:
    return [f["rule"] for f in findings]


def _why(report) -> str:
    return "; ".join(f"{f['rule']}: {f['detail']}" for f in _findings(report))


def _mentioning(report, rule: str) -> list[dict]:
    return [f for f in _findings(report) if f["rule"] == rule]


def _probe(tmp_path: Path, spec_dir: Path) -> Path:
    """A tmp copy of a shipped spec dir — `out/` is READ-ONLY for this lane."""
    dest = tmp_path / spec_dir.name
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("spec.yaml", "lint-report.json", "idea.json"):
        source = spec_dir / name
        if source.is_file():
            shutil.copy2(source, dest / name)
    return dest


def _load_probe(probe: Path) -> tuple[dict, dict | None]:
    spec = yaml.safe_load((probe / "spec.yaml").read_text(encoding="utf-8"))
    idea_path = probe / "idea.json"
    parsed = json.loads(idea_path.read_text(encoding="utf-8")) if idea_path.is_file() else None
    return spec, parsed


def _relabel(spec: dict, relations, introduced=None) -> dict:
    """`spec` rebuilt with exactly these relations (and terms_introduced).

    Level bodies are cloned from the fixture's own levels, so every field the
    §11 linter reads other than the two under test is untouched.
    """
    levels = spec["game"]["levels"]
    rebuilt = []
    for position, relation in enumerate(relations):
        level = deepcopy(levels[min(position, len(levels) - 1)])
        level["relation_to_prev"] = relation
        if introduced is not None:
            level["terms_introduced"] = list(introduced[position])
        rebuilt.append(level)
    spec["game"]["levels"] = rebuilt
    return spec


def _silent_share(spec: Mapping) -> float:
    """The share this rule is about: NON-FIRST levels with empty terms."""
    levels = spec["game"]["levels"][1:]
    return sum(1 for level in levels if not level.get("terms_introduced")) / len(levels)


# The two synthetic curricula the floor pins ride on. Both are the §11 fixture
# with its level list relabelled, so each is otherwise a clean spec.
_SILENT_TERMS = (
    ["goal.cover", "terrain.conveyor", "manip.select_cycle", "info.fog"],
    ["info.telegraph", "info.recall"],
    [],
    [],
    [],
    [],
)
_AT_FLOOR_TERMS = (
    ["goal.cover", "terrain.conveyor"],
    ["manip.select_cycle"],
    ["info.telegraph"],
    [],
    ["info.fog", "info.recall"],
    [],
    [],
)


def _four_of_five_silent() -> dict:
    """6 levels, 4 of the 5 non-first silent — share 0.800, over the floor."""
    return _relabel(
        _good_spec(),
        ("new", "new", "reuse", "compose", "reuse", "compose"),
        _SILENT_TERMS,
    )


def _at_the_floor() -> dict:
    """7 levels, 3 of the 6 non-first silent — share 0.500, AT the floor."""
    return _relabel(
        _good_spec(),
        ("new", "new", "reuse", "compose", "new", "reuse", "compose"),
        _AT_FLOOR_TERMS,
    )


# --- the tier-gated complexity text, whatever shape it landed in ------------


def _probe_call(func, tier: str) -> str | None:
    """`func(tier)` when that is what it is — a shape probe, never a call site."""
    try:
        return str(func(tier))
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


def _tier_complexity_text(tier: str) -> str:
    """Every word the tier's complexity override reaches a prompt with.

    A2 may not edit `gen/s0_ideas.py`, which renders `COMPLEXITY_OVERRIDE` and
    then `TIER_TABLE[tier].guidance` back to back, so the tier-specific words
    may land in either — or in a tier-keyed map, or behind a callable. All four
    shapes are read here; the pins assert on the text, not on the shape.
    """
    # LEAD FIX (A2 close): bare COMPLEXITY* strings are collected ONLY when no
    # tier-keyed/callable shape exists. `COMPLEXITY_OVERRIDE` must survive as a
    # bare str under that exact name (gen/s0_ideas.py:56 imports it; the T-A
    # suite pins isinstance str) AND must keep t1's composition-first line —
    # so a tier-gated implementation necessarily leaves the ban in the bare
    # constant, and collecting it tier-independently made the t2/t3 pins
    # unsatisfiable by construction. Tier-shaped surfaces are the effective
    # text when they exist.
    bare: list[str] = []
    tiered: list[str] = []
    for name, value in sorted(vars(tiers).items()):
        if "COMPLEXITY" not in name.upper():
            continue
        if isinstance(value, str):
            bare.append(value)
        elif isinstance(value, Mapping) and tier in value:
            tiered.append(str(value[tier]))
        elif callable(value):
            rendered = _probe_call(value, tier)
            if rendered is not None:
                tiered.append(rendered)
    parts = tiered if tiered else bare
    parts = [*parts, tiers.TIER_TABLE[tier].guidance]
    return "\n".join(part for part in parts if part)


# --- the escalation-axis constant, discovered by its own citation -----------


def _axis_constants() -> dict[str, str]:
    """Module-level strings in `s1_spec` that cite `escalation.csv`."""
    return {
        name: value
        for name, value in vars(s1_spec).items()
        if name.isupper() and isinstance(value, str) and "escalation.csv" in value
    }


def _invariant_chunks(text: str) -> list[str]:
    """The literal runs of a (possibly `.format`-templated) constant."""
    return [chunk.strip() for chunk in re.split(r"\{[^}]*\}", text) if len(chunk.strip()) >= 15]


def _axis_text() -> tuple[str, str]:
    """(constant name, its text) — failing loudly when none was written."""
    found = _axis_constants()
    if not found:
        pytest.fail(
            "no module-level constant in gen.s1_spec cites `escalation.csv` — A2 §4 asks for "
            "the escalation-axis line as a NAMED, prompt-synced constant citing escalation.csv, "
            "and prompt-sync by construction is what lets the linter and the prompt quote one "
            "source. Searched every upper-case str attribute of gen.s1_spec."
        )
    if len(found) > 1:
        pytest.fail(
            f"{sorted(found)} all cite escalation.csv — the contract names ONE axis constant, "
            "and two make 'the line, once' unpinnable"
        )
    return next(iter(found.items()))


# --- the silent-levels floor seam, discovered ------------------------------

_FLOOR_NAME_RE = re.compile(
    r"silent[_a-z0-9]*(floor|share|threshold|max)|(floor|share|threshold)[_a-z0-9]*silent",
    re.IGNORECASE,
)
_FLOOR_CFG_KEYS = (
    "silent_levels_floor",
    "silent_level_floor",
    "silent_levels_share_floor",
    "silent_levels_max_share",
)
_BAD_FLOORS = (1.5, -0.1, "half")


def _floor_constants() -> dict[str, float]:
    return {
        name: value
        for name, value in vars(s1_spec).items()
        if name.isupper()
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and _FLOOR_NAME_RE.search(name)
    }


def _floor_param() -> str | None:
    for name in inspect.signature(s1_spec.lint_spec).parameters:
        if "floor" in name.lower():
            return name
    return None


def _floor_readers() -> dict[str, object]:
    return {
        name: value
        for name, value in vars(s1_spec).items()
        if callable(value) and not isinstance(value, type) and "floor" in name.lower()
    }


def _floor_seam_report() -> str:
    return (
        f"floor constants {sorted(_floor_constants())}, lint_spec parameter "
        f"{_floor_param()!r}, `lint:` readers {sorted(_floor_readers())}"
    )


def _lint(
    spec: Mapping,
    vocab,
    *,
    idea: Mapping | None = None,
    actions: Mapping[str, str] | None = None,
    floor=_OMITTED,
    monkeypatch=None,
):
    """`lint_spec`, with the floor routed through whichever seam exists."""
    kwargs = {}
    if floor is not _OMITTED:
        param = _floor_param()
        constants = _floor_constants()
        if param is not None:
            kwargs[param] = floor
        elif constants and monkeypatch is not None:
            for name in constants:
                monkeypatch.setattr(s1_spec, name, floor)
        else:
            pytest.fail(
                "the silent-levels floor is config-tunable per A2 §3, but no seam carries a "
                f"tuned value into lint_spec — {_floor_seam_report()}"
            )
    return lint(spec, vocab, idea, None, rule_actions=actions, **kwargs)


# ==========================================================================
# pin 1 — `invert` is a relation, and the curriculum rule knows what it is
# ==========================================================================


def test_invert_joins_the_relations_enum():
    """A2 §1: `RELATIONS += "invert"`, and the standing three survive."""
    assert "invert" in s1_spec.RELATIONS, (
        f"RELATIONS is {s1_spec.RELATIONS} — A2 §1 adds `invert` (a level that flips a standing "
        "rule, the features-schema sense). `invert` is 3/158 official levels and 0/23 of ours "
        "because the enum cannot express it"
    )
    assert {"new", "reuse", "compose"} <= set(s1_spec.RELATIONS), (
        f"RELATIONS lost a standing member: {s1_spec.RELATIONS} — every shipped spec is written "
        "in the old three and must keep linting"
    )
    assert all(isinstance(value, str) for value in s1_spec.RELATIONS)


def test_an_invert_level_lints_clean(vocab):
    """The §11 fixture with ONE level flipped to `invert` still passes."""
    spec = _good_spec()
    spec["game"]["levels"][3]["relation_to_prev"] = "invert"

    report = _lint(spec, vocab)

    assert report.passed, (
        f"a one-change `invert` mutation of good-spec.yaml no longer passes — {_why(report)}"
    )
    assert report.kills == [], _why(report)


def test_invert_is_not_new_for_the_consecutive_run(vocab):
    """A2 §1: `invert` is not "new" for the ≤2-consecutive-new rule.

    `new, new, invert, new, new, reuse` has no run of three — the invert breaks
    it — so the curriculum rule must be silent.
    """
    spec = _relabel(_good_spec(), ("new", "new", "invert", "new", "new", "reuse"))

    report = _lint(spec, vocab)

    assert not _mentioning(report, "curriculum"), (
        "an `invert` between two pairs of `new` levels tripped the curriculum rule — invert is "
        f"not `new`, so it BREAKS a run rather than extending one: {_why(report)}"
    )
    assert report.passed, _why(report)


def test_invert_does_not_dissolve_the_consecutive_new_rule(vocab):
    """The other half: three real `new` levels still kill, invert or not."""
    spec = _relabel(_good_spec(), ("new", "new", "new", "invert", "reuse", "compose"))

    report = _lint(spec, vocab)

    kills = [f for f in _mentioning(report, "curriculum") if f in report.kills]
    assert kills, (
        f"`new, new, new` no longer kills once `invert` exists — MAX_CONSECUTIVE_NEW is "
        f"{s1_spec.MAX_CONSECUTIVE_NEW} and A2 re-opens BOUNDED novelty, not the run rule: "
        f"{_why(report)}"
    )


def test_invert_does_not_buy_the_reuse_credit(vocab):
    """ADJUDICATION PIN — the contract's recommendation: reuse stays reuse.

    A2 §1 leaves this to the implementer ("decide + document ... recommendation:
    no"). There is no knob to pin both branches through, so this pins the
    recommendation. If the landed code documented the OTHER choice, this is the
    line to renegotiate and the lead rules — it is not a defect report.
    """
    spec = _relabel(_good_spec(), ("new", "invert", "new", "invert", "new", "invert"))

    report = _lint(spec, vocab)

    # LEAD FIX (A2 close): the guard is for a SCHEMA rejection of `invert`;
    # the curriculum reuse kill's own detail literally reads "no level has
    # relation_to_prev 'reuse'" (pinned verbatim elsewhere), so a detail
    # substring match fired on the very finding this test then asserts.
    relation_kills = [
        f for f in report.kills
        if f["rule"] == "schema" and "relation_to_prev" in f["detail"]
    ]
    assert not relation_kills, (
        "the `invert` levels were rejected outright, so this spec never reached the reuse rule "
        f"at all: {_why(report)}"
    )
    reuse_kills = [f for f in report.kills if "reuse" in f["detail"]]
    assert reuse_kills, (
        "a curriculum of `new`/`invert` with no `reuse` level passed the ≥1-reuse rule — A2 §1 "
        "recommends that inverting a standing rule is NOT establishing one, so reuse stays "
        f"reuse. ADJUDICATION: if the implementer documented the opposite, the lead rules. "
        f"Report: {_why(report)}"
    )


def test_the_curriculum_note_names_every_relation():
    """Prompt sync: the §7 note states the enum the linter reads."""
    note = s1_spec.CURRICULUM_NOTE
    missing = [rel for rel in s1_spec.RELATIONS if not re.search(rf"\b{re.escape(rel)}\b", note)]
    assert not missing, (
        f"CURRICULUM_NOTE names the relations but not {missing} — A2 §1 updates the §7 prompt "
        "text that names the enum. A writer judged by a rule it was never shown is the failure "
        "prompt-sync-by-construction exists to prevent"
    )


def test_the_writer_prompt_names_invert(idea):
    """The note rides every writer prompt, so `invert` reaches every writer."""
    prompt = s1_spec.build_writer_prompt(load_config(PILOT), idea)

    assert re.search(r"\binvert\b", prompt, re.IGNORECASE), (
        "the built writer prompt never says `invert` — the relation is unreachable in practice "
        "if the only place it exists is the linter's enum (at HEAD the word appears 0 times in "
        "a 35k-char prompt)"
    )


# ==========================================================================
# pin 2 — shipped-corpus parity, unconfigured
# ==========================================================================


@needs_corpus
def test_the_glob_sees_every_shipped_spec():
    """The parity pin must not pass by testing nothing."""
    names = {path.name for path in SHIPPED_DIRS}
    missing = sorted(set(FROZEN_SHIPPED) - names)
    assert not missing, (
        f"out/corpus is populated but the specs shipped at A2 time are missing {missing} "
        f"(found {sorted(names)}) — re-freeze FROZEN_SHIPPED if the tree legitimately moved"
    )


@needs_corpus
@pytest.mark.parametrize("spec_dir", SHIPPED_DIRS, ids=SHIPPED_IDS)
def test_shipped_specs_relint_to_their_shipped_report(vocab, tmp_path: Path, spec_dir: Path):
    """The house rule, measured: unconfigured, nothing moves.

    Six of the seven shipped specs sit ABOVE the default silent-levels floor
    (conduit at 7/7), so this is the pin that proves the new rule is really off
    by default rather than merely documented as off.

    POLICY findings are excluded from the comparison, not from the pin: the
    b003-era reports were written under an armed `tiers:` block (facing-sentinel
    ships a `tier-deceptions` warn) and an unconfigured lint cannot reproduce a
    knob-governed finding BY CONSTRUCTION. Both registries are read off the
    module, so `silent-levels` joins the excluded set the moment it is
    registered — and the `no policy rule fired` assertion below is what keeps
    that from becoming a loophole.
    """
    policy_rules = set(s1_spec.TIER_RULES) | set(s1_spec.FIDELITY_RULES)
    probe = _probe(tmp_path, spec_dir)
    spec, idea = _load_probe(probe)
    shipped = json.loads((probe / "lint-report.json").read_text(encoding="utf-8"))

    report = _lint(spec, vocab, idea=idea)

    fired = set(_rules(_findings(report)))
    assert not fired & policy_rules, (
        f"{spec_dir.name}: an UNCONFIGURED lint produced knob-governed finding(s) "
        f"{sorted(fired & policy_rules)} — every registry rule defaults to `off`, and this spec "
        f"has a silent-level share of {_silent_share(spec):.3f}"
    )
    for label, now, then in (
        ("kills", report.kills, shipped["kills"]),
        ("warns", report.warns, shipped["warns"]),
    ):
        expected = Counter(f["rule"] for f in then if f["rule"] not in policy_rules)
        assert Counter(_rules(now)) == expected, (
            f"{spec_dir.name}: {label} changed against the shipped report — now "
            f"{sorted(_rules(now))}, shipped (policy findings excluded) {sorted(expected)}. A2 "
            "rides under the house rule: an unconfigured run is byte-identical"
        )
    if not any(f["rule"] in policy_rules for f in shipped["kills"]):
        assert report.passed == shipped["passed"]


@needs_corpus
def test_the_shipped_corpus_still_front_loads(vocab, tmp_path: Path):
    """The measurement A2 §3 is built on, re-taken from the tmp copies.

    Not a code pin — a fixture-drift guard. `silent-levels` is only worth a
    registry entry while our curricula really do introduce nothing after the
    first level or two, and the floor is only meaningful while a spec sits AT
    it.
    """
    shares = {}
    for spec_dir in SHIPPED_DIRS:
        spec, _ = _load_probe(_probe(tmp_path, spec_dir))
        shares[spec_dir.name] = _silent_share(spec)

    assert shares.get(CONDUIT) == 1.0, (
        f"{CONDUIT} measures {shares.get(CONDUIT)} silent non-first levels, not 7/7 — the "
        "contract's front-loading exhibit moved"
    )
    assert shares.get(AT_FLOOR_SPEC) == DEFAULT_FLOOR, (
        f"{AT_FLOOR_SPEC} measures {shares.get(AT_FLOOR_SPEC)}, not exactly the default floor "
        f"{DEFAULT_FLOOR} — it is this file's live at-floor exhibit"
    )
    over = sorted(name for name, share in shares.items() if share > DEFAULT_FLOOR)
    assert len(over) >= 5, (
        f"only {over} exceed the default floor — the parity pin above has no teeth if the "
        "shipped corpus would not fire the rule when armed"
    )


# ==========================================================================
# pin 3 — the `silent-levels` fidelity rule
# ==========================================================================


def test_silent_levels_joins_the_fidelity_registry():
    """A2 §3: a registry ENTRY — never a new mechanism."""
    assert SILENT_RULE in s1_spec.FIDELITY_RULES, (
        f"FIDELITY_RULES is {s1_spec.FIDELITY_RULES} — A2 §3 adds {SILENT_RULE!r} to the W1-B "
        "registry (same enum, same knob shape, same default), not a mechanism of its own"
    )
    assert tuple(s1_spec.FIDELITY_ACTIONS) == ("off", "warn", "kill"), (
        f"FIDELITY_ACTIONS is {s1_spec.FIDELITY_ACTIONS} — the registry's enum is off|warn|kill"
    )
    assert s1_spec.FIDELITY_ACTION_KEYS[SILENT_RULE] == SILENT_KEY, (
        f"the `lint:` key for {SILENT_RULE!r} is "
        f"{s1_spec.FIDELITY_ACTION_KEYS.get(SILENT_RULE)!r}, not {SILENT_KEY!r} — the registry "
        "documents one spelling: the rule id with its hyphens written as underscores"
    )


def test_silent_levels_defaults_to_off():
    """DEFAULT OFF, stated twice: the resolver and the config reader."""
    assert s1_spec.resolve_rule_actions(None)[SILENT_RULE] == "off", (
        "resolve_rule_actions(None) does not report the new rule as `off` — A2 §3 says DEFAULT "
        "OFF, and the house rule makes an unconfigured run byte-identical"
    )
    assert s1_spec.lint_rule_actions({})[SILENT_RULE] == "off"
    assert s1_spec.lint_rule_actions({"lint": {}})[SILENT_RULE] == "off"


def test_the_synthetic_curricula_are_otherwise_clean(vocab):
    """Attribution guard: every finding below is about silent levels alone."""
    for name, spec, share in (
        ("4-of-5-silent", _four_of_five_silent(), 0.8),
        ("at-the-floor", _at_the_floor(), 0.5),
    ):
        assert _silent_share(spec) == pytest.approx(share), name
        report = _lint(spec, vocab)
        assert report.passed, f"{name} is not a clean spec before arming — {_why(report)}"


def test_silent_levels_is_silent_when_unarmed(vocab):
    """The 0.800 spec, unconfigured and explicitly off: nothing fires."""
    for actions in (None, {SILENT_RULE: "off"}):
        report = _lint(_four_of_five_silent(), vocab, actions=actions)
        assert not _mentioning(report, SILENT_RULE), (
            f"the rule fired at actions={actions!r} on a 4/5-silent spec — off means off"
        )


def test_silent_levels_warns_when_armed(vocab):
    """Armed `warn` on 4 of 5 non-first levels silent — the contract's case."""
    report = _lint(_four_of_five_silent(), vocab, actions={SILENT_RULE: "warn"})

    fired = _mentioning(report, SILENT_RULE)
    assert len(fired) == 1, (
        f"armed `warn`, a 0.800-silent curriculum produced {len(fired)} {SILENT_RULE!r} "
        f"finding(s), expected exactly one — {_why(report)}"
    )
    assert fired[0] in report.warns, "a `warn` action must record a WARN, never a kill"
    assert report.passed, "a warn may not fail the spec"
    assert fired[0]["detail"].strip(), "the finding carries no detail"


def test_silent_levels_kills_when_armed_to_kill(vocab):
    report = _lint(_four_of_five_silent(), vocab, actions={SILENT_RULE: "kill"})

    fired = _mentioning(report, SILENT_RULE)
    assert len(fired) == 1 and fired[0] in report.kills, (
        f"armed `kill`, the rule did not kill — {_why(report)}"
    )
    assert not report.passed


def test_a_spec_at_the_floor_does_not_fire(vocab):
    """`exceeds a floor` is STRICT — share == floor is silent (A2 §3)."""
    spec = _at_the_floor()
    assert _silent_share(spec) == DEFAULT_FLOOR

    report = _lint(spec, vocab, actions={SILENT_RULE: "warn"})

    assert not _mentioning(report, SILENT_RULE), (
        f"a curriculum at exactly the floor ({DEFAULT_FLOOR}) fired the rule — the contract's "
        f"verification line reads 'fires on conduit-class front-loading and NOT on a spec at "
        f"the floor': {_why(report)}"
    )


@needs_corpus
def test_the_corpus_exhibits_behave_as_the_contract_says(vocab, tmp_path: Path):
    """The live half of the same two cases, on tmp copies of `out/`."""
    by_name = {path.name: path for path in SHIPPED_DIRS}
    for name, should_fire in ((CONDUIT, True), (AT_FLOOR_SPEC, False)):
        if name not in by_name:
            pytest.skip(f"{name} is absent from this checkout's corpus")
        spec, idea = _load_probe(_probe(tmp_path, by_name[name]))
        report = _lint(spec, vocab, idea=idea, actions={SILENT_RULE: "warn"})
        fired = bool(_mentioning(report, SILENT_RULE))
        assert fired is should_fire, (
            f"{name} (silent share {_silent_share(spec):.3f}) "
            f"{'did not fire' if should_fire else 'fired'} the armed rule, against the "
            f"contract's own worked examples: {_why(report)}"
        )


def test_the_floor_is_a_knob_with_the_contract_s_default():
    """A2 §3: `default floor = 0.5, config-tunable`."""
    constants = _floor_constants()
    param = _floor_param()
    declared = [value for value in constants.values()]
    if param is not None:
        default = inspect.signature(s1_spec.lint_spec).parameters[param].default
        if isinstance(default, (int, float)) and not isinstance(default, bool):
            declared.append(default)
    assert declared, (
        f"no floor seam declares a default — A2 §3 sets the floor at {DEFAULT_FLOOR} and makes "
        f"it config-tunable. Searched: {_floor_seam_report()}"
    )
    assert DEFAULT_FLOOR in declared, (
        f"the floor seam declares {declared}, none of them {DEFAULT_FLOOR} — the default is the "
        "contract's, and our compose-heavy curricula legitimately reuse, hence a floor and not "
        "a ban"
    )


def test_the_floor_knob_is_honored(vocab, monkeypatch):
    """A tuned floor moves the verdict on a fixed 0.800 curriculum."""
    under = _lint(
        _four_of_five_silent(), vocab, actions={SILENT_RULE: "warn"}, floor=0.75,
        monkeypatch=monkeypatch,
    )
    assert _mentioning(under, SILENT_RULE), (
        "floor 0.75 did not fire on a 0.800-silent spec — the knob is inert "
        f"({_floor_seam_report()})"
    )

    monkeypatch.undo()
    over = _lint(
        _four_of_five_silent(), vocab, actions={SILENT_RULE: "warn"}, floor=0.9,
        monkeypatch=monkeypatch,
    )
    assert not _mentioning(over, SILENT_RULE), (
        "floor 0.9 still fired on a 0.800-silent spec — the tuned value is not the one the rule "
        f"compares against ({_floor_seam_report()})"
    )


@pytest.mark.parametrize("bad", _BAD_FLOORS, ids=["above-one", "negative", "not-a-number"])
def test_a_bad_floor_is_a_loud_value_error(bad):
    """The common rule: invalid knob values are loud ValueErrors read before work."""
    cfg = {"lint": {key: bad for key in _FLOOR_CFG_KEYS}}
    readers = {**_floor_readers(), "lint_rule_actions": s1_spec.lint_rule_actions}

    raised = []
    for name, reader in readers.items():
        try:
            reader(cfg)
        except ValueError:
            raised.append(name)
        except TypeError:
            continue  # not a cfg-shaped reader; keep looking
    param = _floor_param()
    if param is not None:
        try:
            lint(_good_spec(), set(), None, None, **{param: bad})
        except ValueError:
            raised.append(f"lint_spec({param}=)")

    assert raised, (
        f"a floor of {bad!r} was accepted in silence by every seam — invalid knob values are "
        f"loud ValueErrors read before a batch spends its first token. Searched: "
        f"{_floor_seam_report()} with cfg keys {list(_FLOOR_CFG_KEYS)}"
    )


def test_a_bad_silent_levels_action_is_loud():
    """The registry's own contract, extended to the new key."""
    with pytest.raises(ValueError):
        s1_spec.lint_rule_actions({"lint": {SILENT_KEY: "warm"}})
    with pytest.raises(ValueError):
        s1_spec.resolve_rule_actions({SILENT_RULE: "warm"})


def test_the_kill_sentence_reaches_the_prompt_when_armed_to_kill():
    """The registry pattern: a rule that can KILL is quoted to the writer."""
    section = s1_spec.fidelity_section({SILENT_RULE: "kill"})
    assert section, (
        f"fidelity_section({{{SILENT_RULE!r}: 'kill'}}) rendered nothing — every registry rule "
        "carries one prompt-synced sentence interpolated by BOTH sides, and A2 §3 says the new "
        "entry is 'never a new mechanism'"
    )
    assert s1_spec.fidelity_section({SILENT_RULE: "warn"}) is None, (
        "the section rendered at `warn` — the registry gates prompt text on `kill` so the warn "
        "pass measures what UNPROMPTED writers do"
    )


def test_the_closed_kill_rule_list_is_untouched():
    """A policy finding is not a §11 kill rule — the b5 tuple stays closed."""
    assert SILENT_RULE not in s1_spec.KILL_RULES, (
        f"{SILENT_RULE!r} joined KILL_RULES — the §11 list is closed and pinned two ways; a "
        "knob-governed rule cannot have the fixture that pin demands"
    )


# ==========================================================================
# pin 4 — COMPLEXITY_OVERRIDE, tier-gated
# ==========================================================================


def test_the_s0_machinery_can_still_render_the_override():
    """A2 may not edit `gen/s0_ideas.py`, which imports this name and joins it."""
    override = getattr(tiers, "COMPLEXITY_OVERRIDE", None)
    assert override is not None, (
        "tiers.COMPLEXITY_OVERRIDE is gone — `gen/s0_ideas.py` imports it by name and is NOT in "
        "A2's file list, so the name has to survive the rewrite"
    )
    assert isinstance(override, str) and override.strip(), (
        f"tiers.COMPLEXITY_OVERRIDE is a {type(override).__name__} — s0_ideas appends it "
        "straight into a list of prompt lines and the T-A suite asserts it is a str, so a map "
        "or a callable in that NAME breaks a file this contract may not touch (put the "
        "tier-specific words in the tier guidance, or report the call site for the lead)"
    )


def test_t1_keeps_the_composition_first_line_verbatim():
    """A2 §2: t1 keeps the composition-first line VERBATIM."""
    text = _tier_complexity_text("t1")
    assert COMPOSITION_FIRST_LINE in text, (
        "the t1 complexity text no longer carries the composition-first line verbatim:\n"
        f"expected -> {COMPOSITION_FIRST_LINE!r}\ngot -> {text!r:.600}\n"
        "A2 §2 gates the override by tier and freezes t1's line as it stands"
    )


@pytest.mark.parametrize("tier", ["t2", "t3"])
def test_t2_and_t3_state_the_officials_measured_rate(tier: str):
    """A2 §2: the officials' rate as the TARGET, the term budget as the ceiling."""
    text = _tier_complexity_text(tier)

    assert OFFICIAL_RATE_RE.search(text), (
        f"the {tier} complexity text names no escalation rate:\n{text!r:.600}\nA2 §2 asks it to "
        "state the officials' measured shape — ~1 new mechanic per 2 levels, `new` on 44.9% of "
        "non-first levels — as the target, because a prompt that states the measurement is not "
        "argued with"
    )
    assert CEILING_RE.search(text), (
        f"the {tier} complexity text states a novelty rate but never names the ceiling that "
        f"makes it safe:\n{text!r:.600}\nR-17 re-imposes the term budget after escalation, and "
        "that is the whole reason bounded novelty can be re-opened at all"
    )


@pytest.mark.parametrize("tier", ["t2", "t3"])
def test_the_blanket_ban_does_not_reach_t2_or_t3(tier: str):
    """The sentence R-11 exists to lift, gone from the tiers it bound wrongly."""
    text = _tier_complexity_text(tier)
    assert BLANKET_BAN not in text, (
        f"the {tier} complexity text still says {BLANKET_BAN!r}:\n{text!r:.600}\nA2 §2 lifts the "
        "blanket ban for t2/t3 — 0/23 of our premises carry a novelty axis against the "
        "officials' 52%, BY DESIGN, and a prompt carrying both the ban and the allowance argues "
        "with itself"
    )


def test_the_novelty_target_does_not_reach_t1():
    """The gate cuts both ways: t1 is the tier that keeps the old line.

    A2 §2 gives the officials' rate to t2/t3 only. A t1 prompt carrying both
    the composition-first line and a ~45%-new target would contradict itself in
    exactly the way the blanket ban contradicts t2's.
    """
    t1 = _tier_complexity_text("t1")
    assert not OFFICIAL_RATE_RE.search(t1), (
        f"the t1 complexity text states the officials' novelty rate:\n{t1!r:.600}\nA2 §2 gives "
        "the measured rate to t2/t3 as their TARGET and leaves t1 composition-first"
    )
    for tier in ("t2", "t3"):
        assert _tier_complexity_text(tier) != t1, (
            f"the complexity text for {tier} is identical to t1's — A2 §2 says TIER-GATED, and "
            "one sentence for every tier is the state R-11 is replacing"
        )


# ==========================================================================
# pin 5 — the escalation-axis line in the rendered prompt
# ==========================================================================


def test_the_axis_constant_names_the_target_mix():
    """A2 §4: a named, prompt-synced constant citing escalation.csv."""
    name, text = _axis_text()

    for relation, pattern in AXIS_SHARE_RES.items():
        assert pattern.search(text), (
            f"{name} states no {relation} share matching {pattern.pattern}:\n{text!r:.600}\n"
            "A2 §4 names the drawn tier's target relation mix — new ≈ 45% of non-first levels, "
            "compose ≈ 27%, reuse ≈ 26%"
        )
    assert re.search(r"\binvert\b", text, re.IGNORECASE), (
        f"{name} never mentions `invert`:\n{text!r:.600}\nthe axis line names the whole mix, "
        "and `invert rare` is the fourth quarter of it"
    )


def test_the_axis_line_reaches_an_armed_t2_prompt(idea):
    """It renders, once, in a t2 writer prompt."""
    name, text = _axis_text()
    chunks = _invariant_chunks(text)
    assert chunks, f"{name} has no literal run of 15+ chars to pin against: {text!r:.300}"
    longest = max(chunks, key=len)
    cfg = load_config(PILOT)
    assert idea["tier"] == "t2", "fixture drift: the fixture idea is no longer a t2 idea"

    armed = {
        "guidance": TierPolicy(prompt_guidance=True),
        "fully-armed": TierPolicy(
            prompt_guidance=True,
            term_budget=dict(tiers.DEFAULT_TERM_BUDGETS),
            knob_defaults_action="warn",
            intro_pacing_action="warn",
        ),
    }
    for label, policy in armed.items():
        prompt = s1_spec.build_writer_prompt(cfg, idea, tier_policy=policy)
        missing = [chunk for chunk in chunks if chunk not in prompt]
        assert not missing, (
            f"the {label} t2 prompt is missing {len(missing)} literal run(s) of {name}, first "
            f"{missing[0]!r:.120} — A2 §4 puts the axis line in S1's curriculum prompt section"
        )
        assert prompt.count(longest) == 1, (
            f"{name} appears {prompt.count(longest)} times in the {label} t2 prompt, not once — "
            "a prompt that states its target mix twice is a prompt arguing with itself"
        )


def test_the_axis_line_is_absent_when_no_tier_is_armed(idea):
    """The house rule: an unconfigured run's prompt is byte-identical."""
    name, text = _axis_text()
    longest = max(_invariant_chunks(text), key=len)
    cfg = load_config(PILOT)

    for label, policy in (("no-policy", None), ("neutral", TierPolicy())):
        prompt = s1_spec.build_writer_prompt(cfg, idea, tier_policy=policy)
        assert longest not in prompt, (
            f"the {label} prompt carries {name} — the axis line names the DRAWN TIER's target "
            "mix, and the house rule keeps an unconfigured run's prompt byte-identical to "
            "today's. ADJUDICATION if the line was deliberately made standing text"
        )


# ==========================================================================
# pin 6 — the template arms the rule, and every reader still accepts it
# ==========================================================================


@pytest.fixture()
def template_cfg(tmp_path: Path) -> dict:
    """`config/template.yaml`, loaded from a tmp copy."""
    if not TEMPLATE_PATH.is_file():
        pytest.fail(f"config/template.yaml missing: {TEMPLATE_PATH}")
    dest = tmp_path / "template.yaml"
    shutil.copy2(TEMPLATE_PATH, dest)
    return load_config(dest)


def test_the_template_arms_silent_levels_at_warn(template_cfg: dict):
    """A2 §3: DEFAULT OFF; template arms warn."""
    actions = s1_spec.lint_rule_actions(template_cfg)

    assert actions[SILENT_RULE] == "warn", (
        f"config/template.yaml resolves {SILENT_RULE!r} to {actions[SILENT_RULE]!r} — A2 §3 arms "
        f"it at `warn` there (`lint.{SILENT_KEY}`), which is where the measurement pass happens: "
        "our compose-heavy curricula legitimately reuse, so the kill rate gets measured before "
        "anyone writes `kill`"
    )


def test_every_s1_config_reader_accepts_the_template(template_cfg: dict):
    """A knob nobody validated is how an inert knob is born."""
    readers = {
        "lint_rule_actions": s1_spec.lint_rule_actions,
        "tier_policy": tiers.tier_policy,
        **_floor_readers(),
    }
    failures = {}
    for name, reader in readers.items():
        try:
            reader(template_cfg)
        except Exception as exc:  # noqa: BLE001 — the point is to report, not to raise
            failures[name] = f"{type(exc).__name__}: {exc}"
    assert not failures, (
        f"{len(failures)}/{len(readers)} readers rejected config/template.yaml: {failures}"
    )


def test_the_armed_template_lints_the_fixture_without_new_kills(vocab, template_cfg: dict):
    """Armed at the template's own settings, a clean spec stays passing."""
    actions = s1_spec.lint_rule_actions(template_cfg)

    report = lint(_good_spec(), vocab, None, None, rule_actions=actions)

    assert not any(f["rule"] == SILENT_RULE for f in report.kills), (
        f"the template's armed settings KILL on the §11 fixture — `warn` records, it does not "
        f"refuse: {_why(report)}"
    )
