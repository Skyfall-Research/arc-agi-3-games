"""The legibility-tier engine (contract T-A).

`design/difficulty-model.md` §3.3 — the signed tier table — is the source for
every number and every word below. It has been config since the pilot
(`batch.tiers` draws t1/t2/t3) and dead everywhere else: the drawn tier reached
the S0 prose prompt as one bare string and reached nothing at all downstream.
This module is the table itself, in the one shape the stages can read.

Two halves ride on it. S0 (contract T-A) uses `guidance`, `seed_range` and the
term-bias/quota knobs to draw an idea AT a tier; S1 (contract T-B, not this
one) uses the ordinal ceilings, `core_terms` and `intro_cap` to hold a spec
there. Nothing here draws, prompts or lints — it only says what each tier IS.

The ordinal mapping is how a qualitative canon row becomes a comparable
ceiling: each §3.3 knob column is ranked EASIEST (0) to HARDEST (2) in the
order the table itself lists the tiers, so "this spec's `refusal` sits at or
under its tier's ceiling" is an `<=` on small ints. The three maps' key sets
are the spec §11 knob enums (`s1_spec.REFUSALS` / `GOAL_LEGIBLE` /
`DANGER_TELLS`) — mirrored, never imported, because S1 imports this module.

Caveats a reader of the ordinals needs, both from the canon row itself:
  * `danger_tell: none` ranks 2 because §3.3 lists "none" in the t3 column (a
    game that shows you nothing is the hard end of the tell ladder). A
    HAZARDLESS game also declares `none` — with no danger there is nothing to
    tell — so a t1 hazardless spec sits above its own ceiling on this axis.
    Whoever enforces the ceiling owes that case an exemption; this module only
    states the rank.
  * §3.3's t3 danger column also says "state-dependent", which is not a value
    the spec's `danger_tell` enum can hold. It is prose about WHEN a tell
    fires, so it has no ordinal here; `t3` guidance carries it as words.

Every knob in `TierPolicy` defaults to today's behavior, and `cfg["tiers"]`
absent means None everywhere: a config that never heard of this module draws
exactly the ideas it drew before it existed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

TIERS = ("t1", "t2", "t3")

# --- the ordinal ladders (§3.3 rows -> comparable ceilings) ------------------
REFUSAL_ORDINAL = {"visible": 0, "free": 1, "silent-charged": 2}
GOAL_LEGIBLE_ORDINAL = {"obvious": 0, "inferable": 1, "opaque": 2}
# texture and absence share rank 1: §3.3 lists them as one t2 cell ("texture /
# absence"), i.e. alternatives at the same readability, not a ladder.
DANGER_TELL_ORDINAL = {
    "unique-hue": 0,
    "texture": 1,
    "absence": 1,
    "camouflage": 2,
    "none": 2,
}

# --- the frozen prompt text -------------------------------------------------
# One paragraph per tier, written to be pasted INTO a prompt beside the tier
# line it qualifies. Each one is the §3.3 row read out loud plus the corpus
# fact that justifies its hard edge (t3's 17/25 silent-charged officials, t2's
# median mechanic count), because a prompt that only states a rule gets argued
# with and a prompt that states the measurement does not.
T1_GUIDANCE = (
    "Tier t1 (entry): the game is EASY to read and learn. Refusal is visible; the goal is "
    "obvious from the first frame; danger (if any) has a unique hue and a telegraph; declare "
    "NO deceptions. Use 2-3 seed mechanics and introduce at most one new term per level after "
    "level 1; prefer reusing a seed term in a contrasting context over adding a term."
)
T2_GUIDANCE = (
    "Tier t2 (core): official-typical readability. Refusal is free or visible; the goal is "
    "inferable; danger tells may use texture or absence; at most ONE declared deception lever. "
    "Reuse before composing; keep the mechanic count near the officials' median."
)
T3_GUIDANCE = (
    "Tier t3 (official-grade): hardness comes from legibility, not mechanics volume. Refusal "
    "may be silent-charged (the 17/25 official pattern); the goal may be inferable or opaque; "
    "danger tells may be camouflage, state-dependent, or absent; 2-3 declared deception levers "
    "including lying/hidden classes are allowed. Composed pairs of mechanics are the intent."
)

# The counterweight to the VENDORED idea doctrine (D22,
# `third-party/re-arc-3/game_generation_prompt.md`), which instructs "decently
# complicated" and "every level should introduce additional difficulty" with
# nothing pulling the other way — and the shipped games show it: 10-14
# vocabulary terms against the officials' 4-10 (mean 7.6). It rides AFTER the
# doctrine, because the last word in a prompt is the one that binds.
#
# TIER-GATED SINCE R-11 (contract A2). The counterweight over-corrected: its
# closing clause is a BLANKET ban ("never from adding mechanics"), and the
# comparative audit measured what that produced — we compose where the
# officials introduce (new 19.1% of our non-first levels against their 44.9%;
# compose 44.7% against their 27.2%), 72.3% of our non-first levels introduce
# no term at all against the officials' 183/183 non-blank `new_mechanic`, and
# 0 of 23 premises carry a novelty axis against their 52%. The ban is therefore
# split in two:
#
#   * `COMPOSITION_FIRST_LINE` — the blanket ban, VERBATIM, kept for t1.
#     An entry-tier game is the one place it is right: t1 draws 2-3 core terms
#     and caps introductions at one per level, so "compose, do not add" is the
#     whole curriculum.
#   * `BOUNDED_NOVELTY_LINE` — t2/t3. It states the officials' MEASURED
#     rate as the target shape and names the tier term budget as the ceiling
#     that makes it safe. R-17 re-imposes that budget after an escalation, which
#     is the precondition this line rides on: novelty costs `game.terms`
#     entries, and `game.terms` is capped, so "a new mechanic is allowed" can
#     never become "10-14 terms" again.
#
# `COMPLEXITY_OVERRIDE` itself is UNCHANGED, byte for byte: it is t1's text, it
# is what `gen/s0_ideas.py` renders into the prose prompt today, and the T-A
# suite pins it into that prompt once per tier. Swapping S0 onto
# `complexity_override(tier)` is a ONE-LINE change in a file contract A2 may not
# touch — reported to the lead with the T-A pin it moves, never made here.
#
# The two closing clauses deliberately do NOT carry `COMPLEXITY` in their names.
# The name family is the OVERRIDE BLOCK (`COMPLEXITY_OVERRIDE*`, tier-keyed or
# whole); a bare `COMPLEXITY_*` string holding one tier's clause reads — to a
# person and to a tooling sweep alike — as text every tier gets, which is
# exactly the pre-A2 state the gate replaces.
COMPLEXITY_OVERRIDE_HEAD = (
    "COMPLEXITY OVERRIDE (arc-agi-games tier workstream; overrides the "
    "'decently complicated' / 'every level should introduce additional "
    "difficulty' instruction above): complexity is set by the legibility "
    "tier below. Officials average 7-8 vocabulary terms per game; an "
    "entry-tier game uses fewer."
)
COMPOSITION_FIRST_LINE = (
    "Difficulty comes from legibility, layout, "
    "and composition of the SAME mechanics — never from adding mechanics."
)

# --- the measured escalation shape (contract A2 / R-11) ---------------------
# `audit/comparative/data/escalation.csv`, corpus == official: 183 levels, 158
# of them non-first, each carrying the `relation_to_prev` the audit read off the
# game. The counts are the source and the percentages are derived from them, so
# a reader can re-check either against the csv. `invert` is in this table at
# 3/158 and is the value R-11 makes generatable at all (`s1_spec.RELATIONS`).
ESCALATION_SOURCE = "audit/comparative/data/escalation.csv"
OFFICIAL_NON_FIRST_LEVELS = 158
OFFICIAL_ESCALATION_COUNTS = {"new": 71, "compose": 43, "reuse": 41, "invert": 3}
OFFICIAL_ESCALATION_MIX = {
    relation: round(100 * count / OFFICIAL_NON_FIRST_LEVELS, 1)
    for relation, count in OFFICIAL_ESCALATION_COUNTS.items()
}

BOUNDED_NOVELTY_LINE = (
    "Difficulty comes first from legibility and layout — and a NEW MECHANIC IS ALLOWED, "
    "ON A BUDGET: the officials introduce one on {new_pct}% of their non-first levels "
    "({new_n}/{non_first}, about one new mechanic every two levels; {source}), so a level "
    "that teaches something new is the official shape and not a defect. The ceiling that "
    "keeps it safe is this tier's term budget above: every mechanic you introduce spends a "
    "`game.terms` entry, and that list may not exceed the budget. Compose and reuse still "
    "carry most of the curriculum; what is forbidden is buying difficulty with vocabulary."
).format(
    new_pct=OFFICIAL_ESCALATION_MIX["new"],
    new_n=OFFICIAL_ESCALATION_COUNTS["new"],
    non_first=OFFICIAL_NON_FIRST_LEVELS,
    source=ESCALATION_SOURCE,
)

# The per-tier closing line, and the whole block each tier reads. t1's IS the
# frozen text; t2/t3 swap only the closing clause, so the head — which is what
# names the vendored instruction it overrides — is one string in one place.
COMPLEXITY_TIER_LINES: dict[str, str] = {
    "t1": COMPOSITION_FIRST_LINE,
    "t2": BOUNDED_NOVELTY_LINE,
    "t3": BOUNDED_NOVELTY_LINE,
}
COMPLEXITY_OVERRIDE = f"{COMPLEXITY_OVERRIDE_HEAD} {COMPOSITION_FIRST_LINE}"
COMPLEXITY_OVERRIDE_BY_TIER: dict[str, str] = {
    tier: f"{COMPLEXITY_OVERRIDE_HEAD} {line}" for tier, line in COMPLEXITY_TIER_LINES.items()
}


def complexity_tier_line(tier: str | None) -> str:
    """The closing complexity clause for one tier — the conservative one by default.

    An unknown tier (or None) gets t1's blanket line: this is read on the prompt
    path, where the fallback has to be the text that was shipping before the
    tier gate existed. A tier that is not in the signed table has no measured
    escalation target to hand a writer.
    """
    return COMPLEXITY_TIER_LINES.get(tier or "", COMPOSITION_FIRST_LINE)


def complexity_override(tier: str | None) -> str:
    """The whole COMPLEXITY OVERRIDE block for one tier (head + that tier's line).

    `complexity_override("t1")` IS `COMPLEXITY_OVERRIDE`, byte for byte, and so
    is the unknown-tier fallback — a caller that swaps the constant for this
    function changes nothing at t1 and nothing for an untiered draw.
    """
    return f"{COMPLEXITY_OVERRIDE_HEAD} {complexity_tier_line(tier)}"


@dataclass(frozen=True)
class TierRow:
    """One §3.3 column, as the stages read it.

    `refusal_max` / `goal_legible_max` / `danger_tell_max` are ordinal ceilings
    (inclusive) in the ladders above; `lever_max` counts DECLARED deception
    levers; `core_terms` is the canon "terms" row (core mechanics, not the
    spec's whole `game.terms` list); `seed_range` is the S0 seed-term count;
    `intro_cap` is the per-level new-term ceiling after level 1, or None where
    the canon row sets none.
    """

    tier: str
    label: str
    refusal_max: int
    goal_legible_max: int
    danger_tell_max: int
    lever_max: int
    core_terms: tuple[int, int]
    seed_range: tuple[int, int]
    intro_cap: int | None
    guidance: str


TIER_TABLE: dict[str, TierRow] = {
    "t1": TierRow(
        tier="t1",
        label="entry",
        refusal_max=REFUSAL_ORDINAL["visible"],
        goal_legible_max=GOAL_LEGIBLE_ORDINAL["obvious"],
        danger_tell_max=DANGER_TELL_ORDINAL["unique-hue"],
        lever_max=0,
        core_terms=(2, 3),
        seed_range=(2, 3),
        intro_cap=1,
        guidance=T1_GUIDANCE,
    ),
    "t2": TierRow(
        tier="t2",
        label="core",
        refusal_max=REFUSAL_ORDINAL["free"],
        goal_legible_max=GOAL_LEGIBLE_ORDINAL["inferable"],
        danger_tell_max=DANGER_TELL_ORDINAL["texture"],
        lever_max=1,
        core_terms=(3, 5),
        seed_range=(2, 4),
        intro_cap=None,
        guidance=T2_GUIDANCE,
    ),
    "t3": TierRow(
        tier="t3",
        label="official-grade",
        refusal_max=REFUSAL_ORDINAL["silent-charged"],
        goal_legible_max=GOAL_LEGIBLE_ORDINAL["opaque"],
        danger_tell_max=DANGER_TELL_ORDINAL["camouflage"],
        lever_max=3,
        core_terms=(4, 6),
        seed_range=(3, 4),
        intro_cap=None,
        guidance=T3_GUIDANCE,
    ),
}

# `len(game.terms)` ceilings — anchored to the OFFICIALS' per-game term counts
# (`mechanics/game-term-matrix.csv`, rows with corpus == official, column
# `n_terms`): the 25 sorted are 4,5,5,6,6,6,6,7,7,7,7,7,8,8,8,9,9,9,9,9,9,9,
# 10,10,10 — t1 = p25 (sorted[6]) = 6 · t2 = median = 8 · t3 = max = 10.
# These are NOT the canon `core_terms` counts and must not be read as them:
# §3.3 counts core mechanics, while a spec's `game.terms` also carries the
# incidental and lint-forced terms (measured at ~3 in both corpora), so the
# ceilings sit one overhead above the core row and reproduce the officials'
# own distribution when saturated.
DEFAULT_TERM_BUDGETS = {"t1": 6, "t2": 8, "t3": 10}
# Under 4 no game can carry a witness, a recipe term and anything of its own.
TERM_BUDGET_MIN = 4

# S0's global seed-term bounds, MIRRORED (s0_ideas imports this module, never
# the reverse) — s0_ideas asserts the two agree at import.
GLOBAL_SEED_TERMS = (2, 4)

TERM_BUDGET_ACTIONS = ("warn", "kill")
KNOB_DEFAULTS_ACTIONS = ("off", "warn", "kill")
INTRO_PACING_ACTIONS = ("off", "warn", "kill")
TERM_BIAS_VALUES = ("rare", "common-official")

POLICY_KEYS = (
    "prompt_guidance",
    "term_budget",
    "term_budget_action",
    "knob_defaults_action",
    "intro_pacing_action",
    "seed_terms",
    "term_bias",
    "quota_boost_tiers",
    "g_central",
    "goal_legible_cap",
)

# `g_central` is §3.3's last row (t1 draws g from the p25-p75 centre). It is a
# v2 seam on purpose: the g draw is S4's, downstream of the baselines the b002
# batch was measured with, and turning it on mid-workstream would move numbers
# no tier contract has signed for. Written and false is fine — it documents
# the seam; written and TRUE is a stop.
G_CENTRAL_REFUSAL = (
    "tiers.g_central is a v2 seam, not a knob: the per-tier g draw belongs to S4 "
    "(design/difficulty-model.md §3.5) and no contract has signed it. Remove the key "
    "or set it false."
)


@dataclass(frozen=True)
class TierPolicy:
    """The parsed `tiers:` config block — every field defaulted to today.

    A None dict-field means "the rule is off / the global knob still rules",
    never "an empty selection": `term_budget` None leaves term counts
    unchecked, `seed_terms` None leaves `ideas.seed_terms_per_idea` in charge,
    `term_bias` None leaves every tier on the rare-term coverage steer, and
    `quota_boost_tiers` None leaves the quota boost applying in every tier.
    """

    prompt_guidance: bool = False
    term_budget: dict[str, int] | None = None
    term_budget_action: str = "warn"
    knob_defaults_action: str = "off"
    intro_pacing_action: str = "off"
    seed_terms: dict[str, tuple[int, int]] | None = None
    term_bias: dict[str, str] | None = None
    quota_boost_tiers: tuple[str, ...] | None = None
    # OPERATOR LEGIBILITY RULING (2026-09-29, after playing the echo game):
    # "let's only create obvious goal games instead of inferable too for now".
    # A batch-wide ceiling on `game.knobs.goal_legible`, tightening every
    # tier's own `goal_legible_max` to at most this value. None (the default)
    # = the §3.3 table's per-tier maxes, today's bytes. It ENFORCES through
    # the existing tier-knob-mismatch check, so the parser refuses a cap on a
    # config whose `knob_defaults_action` is off — a cap with no enforcer
    # would be a silent no-op wearing a ruling's name.
    goal_legible_cap: str | None = None


def _bool_key(raw: Mapping, key: str, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 — a config defect; the whole block reports ValueError
            f"tiers.{key} must be a bool, got {value!r}"
        )
    return value


def _enum_key(raw: Mapping, key: str, allowed: tuple[str, ...], default: str) -> str:
    value = raw.get(key, default)
    if value not in allowed:
        raise ValueError(f"tiers.{key} must be one of {list(allowed)}, got {value!r}")
    return value


def _tier_keys(raw: Mapping, key: str) -> None:
    unknown = sorted(str(t) for t in set(raw) - set(TIERS))
    if unknown:
        raise ValueError(f"tiers.{key} names unknown tiers {unknown} (expected {list(TIERS)})")


def _parse_term_budget(raw: Mapping) -> dict[str, int] | None:
    """null (off) · true (the measured defaults) · a full {t1,t2,t3} map."""
    value = raw.get("term_budget")
    if value is None:
        return None
    if value is True:
        return dict(DEFAULT_TERM_BUDGETS)
    if not isinstance(value, Mapping) or set(value) != set(TIERS):
        raise ValueError(
            f"tiers.term_budget must be null, true, or a map over exactly {list(TIERS)}, "
            f"got {value!r}"
        )
    budgets: dict[str, int] = {}
    for tier in TIERS:
        count = value[tier]
        if not isinstance(count, int) or isinstance(count, bool) or count < TERM_BUDGET_MIN:
            raise ValueError(
                f"tiers.term_budget.{tier} must be an int >= {TERM_BUDGET_MIN}, got {count!r}"
            )
        budgets[tier] = count
    return budgets


def _parse_seed_terms(raw: Mapping) -> dict[str, tuple[int, int]] | None:
    """Per-tier [min, max] seed-term counts, each nested in S0's global range."""
    value = raw.get("seed_terms")
    if value is None:
        return None
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"tiers.seed_terms must be a non-empty per-tier mapping, got {value!r}")
    _tier_keys(value, "seed_terms")
    lo_bound, hi_bound = GLOBAL_SEED_TERMS
    ranges: dict[str, tuple[int, int]] = {}
    for tier in TIERS:  # TIERS order, so the parsed map never depends on YAML order
        if tier not in value:
            continue
        bounds = value[tier]
        ok = isinstance(bounds, (list, tuple)) and len(bounds) == 2
        ok = ok and all(isinstance(v, int) and not isinstance(v, bool) for v in bounds)
        if not ok:
            raise ValueError(f"tiers.seed_terms.{tier} must be [min, max] ints, got {bounds!r}")
        lo, hi = bounds
        if not lo_bound <= lo <= hi <= hi_bound:
            raise ValueError(
                f"tiers.seed_terms.{tier} must nest inside [{lo_bound}, {hi_bound}] with "
                f"min <= max, got {bounds!r}"
            )
        ranges[tier] = (lo, hi)
    return ranges


def _parse_term_bias(raw: Mapping) -> dict[str, str] | None:
    value = raw.get("term_bias")
    if value is None:
        return None
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"tiers.term_bias must be a non-empty per-tier mapping, got {value!r}")
    _tier_keys(value, "term_bias")
    bias: dict[str, str] = {}
    for tier in TIERS:
        if tier not in value:
            continue
        mode = value[tier]
        if mode not in TERM_BIAS_VALUES:
            raise ValueError(
                f"tiers.term_bias.{tier} must be one of {list(TERM_BIAS_VALUES)}, got {mode!r}"
            )
        bias[tier] = mode
    return bias


def _parse_quota_boost_tiers(raw: Mapping) -> tuple[str, ...] | None:
    value = raw.get("quota_boost_tiers")
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError(  # noqa: TRY004 — a config defect; the whole block reports ValueError
            f"tiers.quota_boost_tiers must be a list of tiers, got {value!r}"
        )
    # Membership, never set(): an unhashable entry is a config typo like any
    # other and has to reach the reader as the named ValueError below.
    unknown = sorted({str(t) for t in value if t not in TIERS})
    if unknown:
        raise ValueError(
            f"tiers.quota_boost_tiers names unknown tiers {unknown} (expected {list(TIERS)})"
        )
    return tuple(tier for tier in TIERS if tier in value)


def tier_policy(cfg: Mapping) -> TierPolicy | None:
    """The `tiers:` block, parsed and fully validated — or None when it is absent.

    Fail-loud on EVERY key, and the key name is the error message: this is read
    inside `check_config`, before a batch spends its first prose token, so a
    typo here has to cost nothing. Nothing is inferred or defaulted quietly
    except the documented per-field defaults, all of which reproduce the
    pre-tier behavior.
    """
    raw = cfg.get("tiers") if isinstance(cfg, Mapping) else None
    if raw is None:  # absent, or written empty — the same thing: no policy
        return None
    if not isinstance(raw, Mapping):
        raise ValueError(  # noqa: TRY004 — a config defect; the whole block reports ValueError
            f"tiers must be a mapping of tier knobs, got {raw!r}"
        )
    unknown = sorted(str(k) for k in set(raw) - set(POLICY_KEYS))
    if unknown:
        raise ValueError(f"tiers names unknown keys {unknown} (expected {list(POLICY_KEYS)})")
    if _bool_key(raw, "g_central", False):
        raise ValueError(G_CENTRAL_REFUSAL)
    return TierPolicy(
        prompt_guidance=_bool_key(raw, "prompt_guidance", False),
        term_budget=_parse_term_budget(raw),
        term_budget_action=_enum_key(raw, "term_budget_action", TERM_BUDGET_ACTIONS, "warn"),
        knob_defaults_action=_enum_key(
            raw, "knob_defaults_action", KNOB_DEFAULTS_ACTIONS, "off"
        ),
        intro_pacing_action=_enum_key(raw, "intro_pacing_action", INTRO_PACING_ACTIONS, "off"),
        seed_terms=_parse_seed_terms(raw),
        term_bias=_parse_term_bias(raw),
        quota_boost_tiers=_parse_quota_boost_tiers(raw),
        goal_legible_cap=_parse_goal_legible_cap(raw),
    )


def _parse_goal_legible_cap(raw: Mapping) -> str | None:
    """`tiers.goal_legible_cap` — the operator's 2026-09-29 legibility ruling knob.

    Absent or null = no cap = today's bytes. A value must be one of the
    `goal_legible` enum's own spellings, and it must have an enforcer: the cap
    tightens the tier-knob-mismatch check, so a config arming the cap with
    `knob_defaults_action: off` is refused loudly rather than shipped inert.
    """
    value = raw.get("goal_legible_cap")
    if value is None:
        return None
    allowed = tuple(GOAL_LEGIBLE_ORDINAL)
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(
            f"tiers.goal_legible_cap must be one of {list(allowed)}, got {value!r}"
        )
    if _enum_key(raw, "knob_defaults_action", KNOB_DEFAULTS_ACTIONS, "off") == "off":
        raise ValueError(
            "tiers.goal_legible_cap has no enforcer: it tightens the "
            "tier-knob-mismatch check, so knob_defaults_action must be warn or "
            "kill on the same config"
        )
    return value


# The table and the ladders are each other's vocabulary — a ceiling that names
# a knob value the enum does not carry would be silently unreachable.
assert set(TIER_TABLE) == set(TIERS), "TIER_TABLE must cover exactly TIERS"
assert set(DEFAULT_TERM_BUDGETS) == set(TIERS), "DEFAULT_TERM_BUDGETS must cover exactly TIERS"
assert all(row.tier == tier for tier, row in TIER_TABLE.items()), "TierRow.tier must be its key"
# The tier gate on the complexity override (contract A2): every tier has a
# closing line, t1's block IS the frozen constant, and the measured mix the
# t2/t3 line quotes sums to its own denominator — a percentage that drifted off
# `escalation.csv` would be a corpus claim nobody could re-check.
assert set(COMPLEXITY_TIER_LINES) == set(TIERS), "COMPLEXITY_TIER_LINES must cover exactly TIERS"
assert set(COMPLEXITY_OVERRIDE_BY_TIER) == set(TIERS), (
    "COMPLEXITY_OVERRIDE_BY_TIER must cover exactly TIERS"
)
assert COMPLEXITY_OVERRIDE_BY_TIER["t1"] == COMPLEXITY_OVERRIDE == complexity_override("t1"), (
    "t1's block is the pre-A2 COMPLEXITY_OVERRIDE verbatim — the contract keeps the "
    "composition-first line at the entry tier, and s0_ideas still ships the constant"
)
assert sum(OFFICIAL_ESCALATION_COUNTS.values()) == OFFICIAL_NON_FIRST_LEVELS, (
    "the official relation counts must partition the 158 non-first official levels"
)
