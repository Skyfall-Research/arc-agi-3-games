"""S0 — idea sampler (architecture §3 S0; pilot B4).

Coverage-steered: term-occurrence + objectives + terms×frontier (via
`duckwm_docs`) -> idea.json {id, seed_terms[], objective{primary,secondary},
failure_family, tier, mix_class, prose, dedupe_key}. Batch honors the mix
(hazardless / locus / tier), the D24 objective floors + reach cap, and the
`batch.quotas` term minima. Pure code + ONE driver call per idea for the prose.

The draw order per idea IS the rng contract (never reorder without re-signing
the pilot seeds): hazardless -> locus -> tier -> failure family -> objective ->
seed-term count -> seed terms -> prose. Every weighted draw sorts its
population first, so `sample_batch(cfg, seed=S)` with a fixed prose runner
writes byte-identical files run after run.

The `objective` step is primary, then — only when `ideas.secondary_rate` is
armed above 0 — a secondary (R-10). At the default rate 0.0 that step spends
NO rng at all, so it is the pre-W2-A objective step and every seeded draw ever
recorded still reproduces; `ideas.corpus_share` likewise re-weights the primary
draw without changing how many draws happen.

The legibility tier is `gen/tiers.py`'s table (difficulty-model §3.3), not a
bare string: with a `tiers:` block the drawn tier steers the seed-term count,
the free-slot term bias, the quota boost and the prose prompt's complexity
counterweight, and `batch.tier_sequence` pins a tier per slot. NONE of that
moves the rng contract — the tier draw happens whether or not an override
discards it, and a per-tier seed range is still exactly one `rng.choice` — so
with no `tiers:` block and no sequence every draw is the pre-tier draw.

Two degradations are structural at pilot size (`batch.size: 1`) and each warns
once per batch rather than pretending to enforce:
  * objective FLOORS (8 families, one batch slot) act as weights, not minima;
  * `batch.quotas` term minima cannot fit in one 2-4-term idea, so quota terms
    get a x3 boost in the free-slot draw instead.
Hard floor/quota enforcement at production batch size (~20-40) is NOT in this
module: it needs a signed allocation algorithm (repair pass / round-robin) and
is deliberately left to that decision — floors are weights at EVERY size here.

CLI:  python -m gen.s0_ideas --config config/b001-pilot.yaml --seed 1
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
import random
import re
import sys
import warnings
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import REPO_ROOT, load_config
from .tiers import (
    GLOBAL_SEED_TERMS,
    TIER_TABLE,
    TierPolicy,
    complexity_override,
    tier_policy,
)

# --- canon inputs (READ-ONLY, resolved under cfg["duckwm_docs"]) -------------
VOCAB_CSV = "mechanics/term-occurrence-final.csv"
MATRIX_CSV = "mechanics/game-term-matrix.csv"
OBJECTIVES_CSV = "mechanics/objectives.csv"
# The `corpus` value of the 25 signed officials' rows in every canon table.
OFFICIAL_CORPUS = "official"
FRONTIER_CSV = "mechanics/terms-x-frontier.csv"
DOCTRINE_MD = "third-party/re-arc-3/game_generation_prompt.md"
# Everything ABOVE this line is tufa's IDEA doctrine; below it is their spec
# prompt, which is S1's business (D22 vendors the file whole).
DOCTRINE_MARKER = "— spec prompt starts"

# ADJUDICATED (lead, 2026-09-21): the sampler's vocabulary is the 71-term
# intersection of the occurrence table with the 190x71 matrix columns.
# `term-occurrence-final.csv` carries a 72nd row, `budget.time` — a legacy
# residual (vocabulary-v2-final "Final counts": 71 = draft's 51 − budget.time
# + 21; the matrix has no such column; the D23 figure layer already exempts
# it). Seeding ideas with it would hand S1 a term no game witnesses. Spec §3's
# header still reads "72 terms" — a canon inconsistency flagged to the operator;
# this module anchors on the matrix, and detects drift in BOTH directions.
VOCAB_SIZE = 71
VOCAB_EXEMPT = frozenset({"budget.time"})  # occurrence-only rows allowed to exist

OBJECTIVE_FAMILIES = (
    "reach_goal",
    "cover_targets",
    "collect_all",
    "match_pattern",
    "sequence",
    "survive",
    "connect",
    "balance",
)

# spec-v0.3 §3b crosswalk: a declared family MUST be witnessed by a present
# term (the §11 linter kills specs where it isn't). `goal.keyed` and
# `goal.confirm` are structural MODIFIERS — never a family's witness on their
# own — so they appear nowhere in this map.
WITNESS_MAP: dict[str, tuple[str, ...]] = {
    "reach_goal": ("goal.reach", "goal.rendezvous"),
    "match_pattern": ("goal.pattern_match",),
    "cover_targets": ("goal.cover",),
    "collect_all": ("goal.cover",),
    "sequence": ("goal.sequence",),
    "survive": ("goal.survive",),
    "connect": ("goal.path_connect",),
    "balance": ("phys.balance",),
}

FAILURE_FAMILIES = (
    "belief_maintenance",
    "self_monitoring",
    "agency_attribution",
    "composition_commitment",
    "temporal_perception",
)

# design/difficulty-model.md §3.4 (failure-family drill recipes, idea-stage
# seeds). Each recipe there is TERMS + KNOBS; only the term parts live here —
# the knob parts (`goal_legible: inferable`, `refusal: silent-charged`,
# declared decoys/look-alikes, tight g draws, curriculum shape) are S1's.
FAMILY_RECIPES: dict[str, tuple[str, ...]] = {
    "belief_maintenance": ("info.fog", "info.viewport", "gate.remote", "program.commit"),
    "self_monitoring": ("state.wait",),
    "agency_attribution": ("move.coupled", "agent.echo"),
    "composition_commitment": (
        "program.compose",
        "goal.sequence",
        "goal.confirm",
        "manip.interlock",
    ),
    "temporal_perception": ("gate.phase", "state.wait", "state.action_lag", "hazard.timed"),
}

TIERS = ("t1", "t2", "t3")
LOCI = ("mover", "selection", "click")

# idea.json key order (spec §11 shape; `to_json_dict` emits exactly these).
IDEA_KEYS = (
    "id",
    "seed_terms",
    "objective",
    "failure_family",
    "tier",
    "mix_class",
    "prose",
    "dedupe_key",
)

MIN_SEED_TERMS = 2
MAX_SEED_TERMS = 4
SEED_TERMS_DEFAULT = (MIN_SEED_TERMS, MAX_SEED_TERMS)

# Objective weighting (D24): floors as base weight, a deficit boost toward an
# even 1/8 share of the MEASURED corpus, then the hard reach cap.
DEFICIT_TARGET = 1.0 / len(OBJECTIVE_FAMILIES)
DEFICIT_GAIN = 4.0

# --- R-10: which corpus the objective mix is cut from ------------------------
# `ideas.corpus_share` picks the BASIS of the objective draw. It is one knob
# with two parts, because a share and the rule that turns it into a weight are
# not separable here:
#
#   measured  (DEFAULT, = today, byte-identical) — the share is the 190-row
#     measured corpus (25 officials + 57 fleet-judged + 108 crosswalk-derived,
#     87% tufa) and the rule is D24's DEFICIT BOOST: a family under an even 1/8
#     is lifted toward it. The boost steers AGAINST the corpus on purpose —
#     tufa collapses onto reach/cover — and the audit measured what it actually
#     produces: a near-uniform 9.2-15.9% mix (M-3 §3 / findings A1), with the
#     0.25 reach cap never binding because reach's own boosted share computes
#     0.101.
#   officials — the share is the 25 signed officials' primary distribution
#     (reach_goal 11, match_pattern 6, cover_targets 4, collect_all 2,
#     sequence 1, balance 1, survive 0, connect 0) and the rule is REBASE: the
#     weight IS the share. The operator's R-10 ruling, verbatim, is RESEMBLE THE
#     OFFICIALS, and a deficit boost applied to the officials' own shares would
#     do the opposite of that — it would flatten 11/6/4/2/1/1/0/0 back toward
#     uniform (measured: reach 0.101, survive 0.152). The floors and the reach
#     cap are untouched and run exactly as they do above.
#   blend — the share is 50/50 of the two, under the same REBASE rule.
#
# WHAT `officials` COSTS, stated because it is a real departure: the share is
# multiplied by the floor base, so a family the officials never use as a
# primary (survive, connect — both 0/25) gets weight 0 and becomes UNDRAWABLE,
# and no `batch.mix.objective.floors` entry can rescue it (0 x anything is 0).
# That is the ruling's own content — the officials have no survive-primary and
# no connect-primary game — but it retires the "every family stays drawable"
# property the min-1 base gives `measured`. Use `blend` to keep both tails
# alive (survive 0.015, connect 0.023 measured at N=20,000).
CORPUS_SHARE_MEASURED = "measured"
CORPUS_SHARE_OFFICIALS = "officials"
CORPUS_SHARE_BLEND = "blend"
CORPUS_SHARE_MODES = (CORPUS_SHARE_MEASURED, CORPUS_SHARE_OFFICIALS, CORPUS_SHARE_BLEND)
CORPUS_SHARE_DEFAULT = CORPUS_SHARE_MEASURED

# --- R-10: secondary objectives ---------------------------------------------
# The officials carry a secondary objective 19 of 25 times; our sampler has
# never drawn one (0/11 ideas, `objective.secondary` always null — findings
# A1). `ideas.secondary_rate` is the share of ideas that get one. DEFAULT 0.0,
# and at 0.0 the draw path consumes NO rng at all (see `_draw_core`), which is
# what keeps every seeded historical draw reproducible.
SECONDARY_RATE_DEFAULT = 0.0
QUOTA_BOOST = 3.0
# Failure-family mass floor: every family stays drawable even at 0 frontier
# share (difficulty-model §3.4 quotas families, it does not rank them).
FAMILY_WEIGHT_BASE = 0.5

WEIGHT_SUM_TOL = 1e-6
MAX_DEDUPE_TRIES = 50

IDEAS_ROOT = REPO_ROOT / "out" / "ideas"
# Cross-batch dedupe memory. Module-level on purpose: a test (or a sanity run
# that must not touch the repo's real history) rebinds this path.
DEDUPE_HISTORY_PATH = IDEAS_ROOT / "dedupe-history.jsonl"

# Everything an idea IS, minus the prose: the fields a re-draw at the same seed
# and config must reproduce exactly. `prose` is the one LIVE field (a driver
# call), so it is compared by nobody — see `sample_batch`'s immutability rule.
IDEA_STRUCTURAL_FIELDS = (
    "id",
    "objective",
    "seed_terms",
    "tier",
    "mix_class",
    "failure_family",
    "dedupe_key",
)
# How much of a diverging value an error message quotes.
IDEA_DIVERGENCE_CHARS = 120

FLOORS_WARNING = (
    "batch.size {size} < sum(objective floors) {floor_total}: objective floors "
    "degrade to weights (no family minimum is enforced in this batch)"
)
QUOTAS_WARNING = (
    "batch.quotas {quotas} cannot be satisfied inside one {lo}-{hi}-term idea: "
    "quotas degrade to weight boosts (x{boost} in the free-slot draw)"
)

# --- R-14: the locus facet, DEFINED in the prompt (PROMPT SYNC) --------------
# `interaction locus: <name>` reached the prose prompt as a BARE LABEL and
# nothing ever told the writer what the label means. The comparative audit
# measured the cost (findings A4 / J-3 §5): 4 of 23 premises drift off the
# drawn locus, ALL FOUR on `selection` draws, where the writer read "selection"
# as "click on things" (strike `locus-drift-selection-reads-click`) — 27%
# OFFICIAL-SHAPED on selection against 75% on mover.
#
# The three classes are canon, so the fix is this repo's PROMPT SYNC pattern —
# quote the definition to the agent that is held to it, the way `visual_canon`
# quotes `affordance-language.md` §9 by line — not a new rule of our own.
# VERBATIM ANCHORS, `design/objects/affordance-language.md` §1:
#   L31-34  "12 have a moving avatar object; 13 have none — in those, "you" is
#            a *selection state* (cn04, ar25, re86, s5i5, sb26, tr87…) or a
#            pure click surface (ft09, lp85, su15, vc33, tn36)."
#   L37-42  "REQUIRED: the locus of control must be identifiable within a few
#            actions. Two idioms cover 25/25: (a) *unique-mover* — exactly one
#            object family responds to the arrows, usually hue-unique on board
#            …; (b) *selection-marker* — a persistent mark names the controlled
#            object."
#   L43-44  "White `0` is the selection colour of the ecosystem — the dominant
#            idiom by far (~8/13 selection games)"
# S0's `LOCI` name those same three classes (avatar -> mover, selection-driven
# -> selection, click-only -> click), the mapping `m3_drawspace.OFFICIAL_LOCUS`
# reads the officials' 10/9/6 split with.
#
# ALL THREE are rendered, never just the drawn one: the measured defect is a
# CONFUSION between two of them, and a definition of `selection` alone does not
# tell a writer what it is being distinguished FROM.
LOCUS_CANON_CITE = "design/objects/affordance-language.md §1 (L29-L44)"
LOCUS_DEFINITIONS: dict[str, str] = {
    "mover": (
        "mover — a unique-mover avatar. Exactly one object family responds to the arrow "
        "actions and is usually hue-unique on the board; the player moves THAT object, and "
        "there is no separate mark naming it."
    ),
    "selection": (
        "selection — a selection-marker, NOT a click surface. A PERSISTENT mark (white `0` is "
        "the ecosystem's own selection colour) names which object is currently controlled, it "
        "stays on the board between actions, and the actions that follow apply to the marked "
        "object until the selection moves. The game therefore carries selected-object state: "
        "if nothing is left marked as 'yours' after an action, the idea is a click game, not a "
        "selection game."
    ),
    "click": (
        "click — a pure click surface. Each click acts on the cell it lands on and nothing is "
        "left marked as the player's afterwards: no persistent controlled object, no carried "
        "selection."
    ),
}
assert tuple(LOCUS_DEFINITIONS) == LOCI, "LOCUS_DEFINITIONS must define exactly S0's LOCI"
LOCUS_BLOCK_HEADER = (
    f"What that locus label means — the three loci as {LOCUS_CANON_CITE} defines them. "
    f"Build the idea around the one drawn above and do not substitute another:"
)
#: THE constant the prompt quotes: header + all three definitions, one block.
LOCUS_DEFINITIONS_BLOCK = "\n".join(
    [LOCUS_BLOCK_HEADER, *(f"- {LOCUS_DEFINITIONS[name]}" for name in LOCI)]
)
assert all(name in LOCUS_DEFINITIONS_BLOCK for name in LOCI), (
    "LOCUS_DEFINITIONS_BLOCK must name every locus S0 can draw"
)

OVERRIDE_HEADER = "## Overrides for THIS idea (they take precedence over anything above)"
LEVEL_COUNT_LINE = "Ignore any fixed level-count above — level count is decided downstream."
REPLY_LINE = (
    "Reply with a TITLE line (≤8 words) then one paragraph of 3-6 sentences "
    "describing the game idea built around exactly these mechanics."
)

# --- the prose gate (R2 coherence pass) -------------------------------------
# Re-sample #2 shipped an agentic preamble as an idea: the TITLE was the model
# narrating its own tool use ("I'll check the repo's mechanics vocabulary and
# spec conventions…", 129 chars / 21 words) and the body was 210 chars built
# around a literal `grep -rn … --include=*.py` command. `_parse_prose` is a
# SHAPE parser — first non-empty line is the title, the rest is the body — so
# it accepted that happily, S1 built a writer prompt on top of it, and the
# session died downstream. The thresholds below are read off the observed
# draws, not taste: the two good draws ("Fogbelt Junctions" 17c/2w, "Compose,
# Commit, Rendezvous" 27c/3w) carried 1348 and 1314 chars of body.
PROSE_TITLE_MAX_CHARS = 90  # observed good: 17, 27 · garbage: 129
PROSE_TITLE_MAX_WORDS = 10  # observed good: 2, 3 · garbage: 21
PROSE_TEXT_MIN_CHARS = 400  # observed good: 1348, 1314 · garbage: 210
# Process narration, matched CASE-SENSITIVELY and exactly as written: every one
# of these is a sentence-initial agentic form, so honest game prose ("the gate
# will let me through") does not trip `Let me `.
PROSE_NARRATION_MARKERS = ("I'll ", "I will ", "Let me ", "I need to ", "First, I")
# Tool/shell fragments that cannot occur inside a game concept. Note what is
# NOT here: bare `ls`/`cat` as plain substrings would reject "walls",
# "controls", "scatter" and any game with a cat in it, so they are matched
# below in COMMAND POSITION only. Single backticks are legitimate (good prose
# quotes terms as `terrain.conveyor`); a triple fence is not.
PROSE_TOOL_FRAGMENTS = ("grep ", "--include=", "```", "\n$ ")
_PROSE_SHELL_CMD_RE = re.compile(r"(?:^|[\n;|]|\$ |&&\s*)\s*((?:ls|cat) )")
# Markdown emphasis WRAPPING the title line. Audit R-15: the `#`-lstrip and the
# `title:` prefix strip both miss bolded titles, so `**Fulcrum Pull**`,
# `**Silent Beacon Relay**`, `**Coupled Conduit**` and `**TITLE:** Keyholder's
# Circuit: …` reached idea.json verbatim (4 of 12 fresh draws; also shipped
# conduit-watch). LEADING/TRAILING runs only — interior emphasis is the
# author's ("Push the *red* block" keeps its asterisks), and the R2 prose gates
# below then read the CLEANED title.
_PROSE_EMPHASIS_RE = re.compile(r"^[*_]+|[*_]+$")

# --- R-14: the win the game can never reach ----------------------------------
# affordance §2 is REQUIRED — "goal state must be *checkable* by the game (win
# predicate), and per D11 the solver must reach it" — and nothing in this
# pipeline asserted it at the IDEA stage. The comparative audit graded 4 of 23
# premises non-terminal or unrecoverable (findings A4 / J-3 §5), two of them
# SHIPPED GAMES whose premise sentence states an unbounded objective outright:
#   b002-triple/idea-002 (core-ward-phase-gates) — "the player's only job is to
#     keep it intact FOR AS LONG AS POSSIBLE while colored hazard tokens creep
#     inward"; graded NEAR, strike `win-predicate-not-terminal`.
#   b002-triple/idea-003 (convoy-in-the-fog) — "the only goal is to keep it
#     running FOREVER by NEVER LETTING its fuel run out"; same strike.
#
# SCOPE, and the check is honest about it: this catches STATED non-terminality
# ONLY — a premise that declares an unbounded or loss-only objective in words.
# It cannot see a premise that is non-terminal and does not say so (the audit's
# other two exhibits are `unrecoverable-dead-state`, a reachability judgement
# no regex makes), and it is not a reachability check: D11 reachability is
# still S1's and S3's. A phrase in a MECHANIC clause rather than a goal clause
# is a false reject the corrective retry can answer, which is why the reason
# quotes the exact match.
#
# PRECISION, measured before shipping: over every one of the 25 idea files
# under `out/` these three families fire on exactly the two exhibits above and
# nothing else — 0 false positives across the 5 remaining shipped premises and
# all 10 OFFICIAL-SHAPED premises of the J-3 grading table
# (`audit/comparative/data/j3-premise-grades.csv`). The near misses they must
# NOT catch, and do not: "the consequence of any click is never immediate",
# "never stopping mid-tile", "failure never comes from clicking fast",
# "misjudge the balance until they toggle it", "rather than survive one lucky
# moment", "later layouts keep the same marble/mirror/plate vocabulary". That
# is why `never` is only read next to `let`, why `as long as` is only read next
# to `possible`/`you can`, and why a bare `keep … running` is NOT a family.
NONTERMINAL_WIN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # The objective is given a duration instead of a state.
    (
        "unbounded-duration",
        re.compile(
            r"(?i)\bas long as possible\b"
            r"|\bas long as (?:you|they|the player|one|it) can\b"
            r"|\bforever\b|\bendless(?:ly)?\b|\bnever[- ]ending\b"
            r"|\bindefinitely\b|\bperpetually\b|\bin perpetuity\b"
        ),
    ),
    # There is no winning state at all — only a losing one to postpone.
    (
        "no-terminal-state",
        re.compile(
            r"(?i)\bnever let(?:s|ting)?\b"
            r"|\bthere is no (?:win|winning|end|victory)\b"
            r"|\bnever (?:truly )?(?:ends|finishes|completes)\b"
            r"|\buntil (?:you|they|the player|the run|it)\s+(?:eventually\s+)?"
            r"(?:die|dies|lose|loses|fail|fails)\b"
        ),
    ),
    # Survive/score flavour: the goal is a quantity with no ceiling.
    (
        "survive-unbounded",
        re.compile(
            r"(?i)\bwave after wave\b"
            r"|\b(?:waves?|rounds?|enemies|attackers?)\b[^.;]{0,30}\bkeeps? coming\b"
            r"|\bnever stops? (?:coming|spawning|arriving)\b"
            r"|\bas many\b[^.;]{0,40}\bas (?:possible|you can)\b"
            r"|\bhighest (?:possible )?score\b"
        ),
    ),
)

PROSE_RETRY_LINE = (
    "REJECTED — your previous reply was not an idea: {reasons}. Reply again, and write the "
    "game concept itself — no process narration, no commands."
)

# Consistency of the signed tables themselves — wrong here means every idea is
# wrong, so it fails at import rather than mid-batch.
assert set(WITNESS_MAP) == set(OBJECTIVE_FAMILIES), "WITNESS_MAP must cover every family"
assert set(FAMILY_RECIPES) == set(FAILURE_FAMILIES), "FAMILY_RECIPES must cover every family"
# Same rule across the module boundary: `gen/tiers.py` mirrors the tier names
# and the global seed-term bounds (it may not import this module), so drift in
# either would make a per-tier range validate against the wrong window.
assert set(TIER_TABLE) == set(TIERS), "TIER_TABLE must cover exactly this module's TIERS"
assert GLOBAL_SEED_TERMS == (MIN_SEED_TERMS, MAX_SEED_TERMS), (
    "tiers.GLOBAL_SEED_TERMS must mirror S0's seed-term bounds"
)


@dataclass
class Idea:
    """One S0 idea — the S1 spec-writer's whole input."""

    id: str  # f"{batch_id}-i{n:03d}", n 1-based
    seed_terms: list[str]  # 2-4, unique, vocabulary terms; witness first
    # {"primary": <family>, "secondary": <family>|None}. `secondary` is None
    # unless `ideas.secondary_rate` is armed (R-10); when it is null it is
    # still S1's call, which is what it always was.
    objective: dict
    failure_family: str | None
    tier: str  # t1 | t2 | t3
    mix_class: dict  # {"hazardless": bool, "locus": mover|selection|click}
    prose: dict  # {"title": str, "text": str}
    dedupe_key: str

    def to_json_dict(self) -> dict:
        return {
            "id": self.id,
            "seed_terms": list(self.seed_terms),
            "objective": dict(self.objective),
            "failure_family": self.failure_family,
            "tier": self.tier,
            "mix_class": dict(self.mix_class),
            "prose": dict(self.prose),
            "dedupe_key": self.dedupe_key,
        }


@dataclass
class _Core:
    """Everything an idea is made of EXCEPT the prose (the priced part).

    The dedupe key is decided here, so a collision resamples the whole core
    without ever having spent a driver call.
    """

    hazardless: bool
    locus: str
    tier: str
    failure_family: str | None
    primary: str
    seed_terms: list[str]
    # R-10. Last, with a default, so every pre-W2-A construction still reads
    # the same and an `ideas.secondary_rate: 0.0` core is the pre-W2-A core.
    secondary: str | None = None


def _cfg_get(cfg: Mapping, dotted: str):
    """Fail-loud nested config read: the dotted path IS the error message."""
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            raise KeyError(
                f"config missing {dotted!r} — S0 never defaults a signed pilot knob"
            )
        node = node[part]
    return node


def _docs(cfg: Mapping) -> Path:
    return Path(_cfg_get(cfg, "duckwm_docs"))


def _read_rows(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"canon table not found: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"canon table is empty: {path}")
    return rows


def _canon_stat_key(path: Path) -> tuple[str, int, int] | None:
    """(path, mtime_ns, size) — a canon file's identity, or None if unreadable.

    None means "do not cache": the missing-file error belongs to the loader,
    which raises it with the path in the message, not to this helper.
    """
    try:
        stat = path.stat()
    except OSError:
        return None
    return (str(path), stat.st_mtime_ns, stat.st_size)


def _matrix_terms(cfg: Mapping) -> set[str]:
    """The term columns of the signed 190x71 matrix — the vocabulary anchor."""
    path = _docs(cfg) / MATRIX_CSV
    if not path.is_file():
        raise FileNotFoundError(f"canon table not found: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh), None)
    if not header:
        raise ValueError(f"{path}: empty matrix header")
    terms = {c for c in header if c not in ("slug", "corpus", "n_terms", "rarities")}
    if len(terms) != VOCAB_SIZE:
        raise ValueError(
            f"{path}: expected {VOCAB_SIZE} term columns, found {len(terms)}"
        )
    return terms


def load_vocab(cfg: Mapping) -> dict[str, dict]:
    """term -> {tufa_live, tufa_dead, official}: occurrence rows ∩ matrix columns.

    THE canonical vocabulary is the matrix's 71 term columns; the occurrence
    table supplies the counts. Drift in either direction is a stop: an
    occurrence row with no matrix column (beyond the known VOCAB_EXEMPT
    residuals) or a matrix column with no occurrence row would silently
    reweight every draw in this file.
    """
    path = _docs(cfg) / VOCAB_CSV
    occurrence: dict[str, dict] = {}
    for row in _read_rows(path):
        term = (row.get("term") or "").strip()
        if not term:
            raise ValueError(f"{path}: a row has an empty 'term'")
        if term in occurrence:
            raise ValueError(f"{path}: duplicate term {term!r}")
        try:
            occurrence[term] = {
                "tufa_live": int(row["tufa_live"]),
                "tufa_dead": int(row["tufa_dead"]),
                "official": int(row["official"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}: bad occurrence counts for {term!r}: {exc}") from exc

    matrix = _matrix_terms(cfg)
    orphans = sorted(set(occurrence) - matrix - VOCAB_EXEMPT)
    if orphans:
        raise ValueError(
            f"{path}: occurrence rows with no matrix column (not in VOCAB_EXEMPT): {orphans}"
        )
    missing = sorted(matrix - set(occurrence))
    if missing:
        raise ValueError(f"{path}: matrix term columns missing occurrence rows: {missing}")

    vocab = {term: occurrence[term] for term in sorted(matrix)}
    if len(vocab) != VOCAB_SIZE:
        raise ValueError(
            f"{path}: expected the {VOCAB_SIZE}-term signed vocabulary, found {len(vocab)}"
        )
    required = {t for terms in WITNESS_MAP.values() for t in terms}
    required |= {t for terms in FAMILY_RECIPES.values() for t in terms}
    missing = sorted(required - set(vocab))
    if missing:
        raise ValueError(f"{path}: witness/recipe terms absent from the vocabulary: {missing}")
    return vocab


def load_objective_distribution(cfg: Mapping, *, corpus: str | None = None) -> dict[str, int]:
    """family -> count of `objective_primary` rows in the MEASURED corpus.

    190 rows (25 triage ground-truth + 57 fleet-judged + 108 crosswalk-derived,
    spec §3b). An unknown family value means the CSV and this module disagree
    about the closed vocabulary: that is a stop, not a skip.

    `corpus` (R-10) narrows the COUNT to one corpus — `OFFICIAL_CORPUS` gives
    the 25 signed officials' own primary distribution. It narrows nothing else:
    the closed-vocabulary check above still runs over EVERY row whichever
    corpus is being counted, because a bad family value anywhere means this
    module and the canon disagree, and that is a stop in both modes. `None` is
    the default and counts every row, exactly as this loader always has.
    """
    path = _docs(cfg) / OBJECTIVES_CSV
    counts = dict.fromkeys(OBJECTIVE_FAMILIES, 0)
    for row in _read_rows(path):
        family = (row.get("objective_primary") or "").strip()
        if family not in counts:
            slug = (row.get("slug") or "?").strip()
            raise ValueError(
                f"{path}: row {slug!r} has objective_primary {family!r}, not one of "
                f"{OBJECTIVE_FAMILIES}"
            )
        if corpus is not None and (row.get("corpus") or "").strip() != corpus:
            continue
        counts[family] += 1
    if sum(counts.values()) == 0:
        where = "" if corpus is None else f" with corpus == {corpus!r}"
        raise ValueError(f"{path}: no objective_primary rows{where}")
    return counts


# The officials' co-occurrence table is read ONCE per (file, mtime, size) and
# handed out as fresh copies. `_draw_core` reads `ideas.secondary_rate` off
# `cfg` on every draw — the same way it already reads `batch.mix.hazardless`
# and `batch.mix.locus` — so without this a 6,000-draw MC would parse the same
# 190-row CSV ~4,500 times (measured: 0.55 ms each, 2.5 s a panel). The key is
# the file's own identity, so a canon edit mid-process is re-read, not served
# stale; the cache holds COUNTS, and every caller still builds its own dicts.
_SECONDARY_COUNTS_CACHE: dict[tuple[str, int, int], tuple[dict, dict]] = {}


def load_secondary_distribution(cfg: Mapping) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """The officials' measured primary -> secondary co-occurrence, and the total.

    Returns `(by_primary, overall)` over the 25 `corpus == official` rows of
    `objectives.csv`. A BLANK `objective_secondary` means the game has no
    secondary objective and is counted nowhere (6 of 25 are blank, which is the
    19/25 = 0.76 the `secondary_rate` arming comes from). An unknown non-blank
    value is a stop for the same reason the primary check is one.

    Same file, same parser, same closed-vocabulary rule as the loader above —
    it is a sibling, not a second CSV reader.
    """
    path = _docs(cfg) / OBJECTIVES_CSV
    cached = _SECONDARY_COUNTS_CACHE.get(_canon_stat_key(path))
    if cached is not None:
        by_primary, overall = cached
        return ({f: dict(row) for f, row in by_primary.items()}, dict(overall))

    by_primary = {f: dict.fromkeys(OBJECTIVE_FAMILIES, 0) for f in OBJECTIVE_FAMILIES}
    overall = dict.fromkeys(OBJECTIVE_FAMILIES, 0)
    for row in _read_rows(path):
        slug = (row.get("slug") or "?").strip()
        primary = (row.get("objective_primary") or "").strip()
        if primary not in by_primary:
            raise ValueError(
                f"{path}: row {slug!r} has objective_primary {primary!r}, not one of "
                f"{OBJECTIVE_FAMILIES}"
            )
        if (row.get("corpus") or "").strip() != OFFICIAL_CORPUS:
            continue
        secondary = (row.get("objective_secondary") or "").strip()
        if not secondary:
            continue
        if secondary not in overall:
            raise ValueError(
                f"{path}: row {slug!r} has objective_secondary {secondary!r}, not one of "
                f"{OBJECTIVE_FAMILIES}"
            )
        by_primary[primary][secondary] += 1
        overall[secondary] += 1
    if sum(overall.values()) == 0:
        raise ValueError(
            f"{path}: no `corpus == {OFFICIAL_CORPUS}` row carries an objective_secondary"
        )
    key = _canon_stat_key(path)
    if key is not None:
        _SECONDARY_COUNTS_CACHE[key] = (
            {f: dict(row) for f, row in by_primary.items()},
            dict(overall),
        )
    return by_primary, overall


def load_frontier_shares(cfg: Mapping) -> dict[str, float]:
    """term -> mean_unbeaten_share from `terms-x-frontier.csv` (33 rows).

    CAVEAT (mandatory, carried wherever this table is used): the shares are
    DESCRIPTIVE over n=25 officials. They steer which failure families get
    extra mass; they are NEVER a predictor of a generated game's difficulty.
    """
    path = _docs(cfg) / FRONTIER_CSV
    shares: dict[str, float] = {}
    for row in _read_rows(path):
        term = (row.get("term") or "").strip()
        if not term:
            raise ValueError(f"{path}: a row has an empty 'term'")
        try:
            shares[term] = float(row["mean_unbeaten_share"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}: bad mean_unbeaten_share for {term!r}: {exc}") from exc
    return shares


def load_doctrine(cfg: Mapping) -> str:
    """tufa's idea doctrine — everything ABOVE the spec-prompt marker (D22).

    Included VERBATIM in the prose prompt: it is the only part of the vendored
    file that describes an IDEA (64x64 legibility, few object types, simple
    primitives, diversity). Our overrides are appended after it.
    """
    path = _docs(cfg) / DOCTRINE_MD
    if not path.is_file():
        raise FileNotFoundError(f"doctrine asset not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    cut = next((i for i, line in enumerate(lines) if DOCTRINE_MARKER in line), None)
    if cut is None:
        raise ValueError(f"{path}: marker {DOCTRINE_MARKER!r} not found — vendored file changed?")
    doctrine = "\n".join(lines[:cut]).strip()
    if not doctrine:
        raise ValueError(f"{path}: the idea doctrine above {DOCTRINE_MARKER!r} is empty")
    return doctrine


def _weighted_choice(rng: random.Random, weights: Mapping[str, float]) -> str:
    """One `rng.random()` over a SORTED cumulative population.

    Sorting is the determinism contract: a set iteration order (or a dict built
    in draw order) would make the same seed produce different batches.
    """
    items = sorted(weights.items())
    if not items:
        raise ValueError("weighted draw over an empty population")
    bad = [name for name, w in items if not isinstance(w, (int, float)) or w < 0]
    if bad:
        raise ValueError(f"negative or non-numeric weights: {sorted(bad)}")
    total = float(sum(w for _, w in items))
    if total <= 0.0:
        raise ValueError(f"weights sum to {total} over {[n for n, _ in items]}")
    draw = rng.random() * total
    upto = 0.0
    for name, weight in items:
        upto += weight
        if draw < upto:
            return name
    return items[-1][0]  # float-accumulation guard; unreachable in practice


def _inverse_occurrence(vocab: Mapping[str, dict], term: str) -> float:
    """1 / (1 + tufa_live + official) — rare terms draw harder (coverage steer)."""
    row = vocab[term]
    return 1.0 / (1.0 + row["tufa_live"] + row["official"])


def _official_occurrence(vocab: Mapping[str, dict], term: str) -> float:
    """1 + official — the officials' OWN term frequency (tier bias `common-official`).

    The mirror of `_inverse_occurrence` over the same vocabulary row, for the
    tier that wants a game built out of what the corpus actually leans on
    rather than out of the rare tail the coverage steer buys. The `1.0 +` is
    what keeps the 0-in-officials terms drawable at all: this biases the pool,
    it never truncates it.
    """
    return 1.0 + vocab[term]["official"]


def _check_weight_map(cfg: Mapping, dotted: str, allowed: tuple[str, ...]) -> dict[str, float]:
    """A mix weight map: known keys only, sums to 1 within WEIGHT_SUM_TOL."""
    raw = _cfg_get(cfg, dotted)
    if not isinstance(raw, Mapping) or not raw:
        raise ValueError(f"{dotted} must be a non-empty mapping, got {raw!r}")
    unknown = sorted(set(raw) - set(allowed))
    if unknown:
        raise ValueError(f"{dotted} names unknown keys {unknown} (expected {list(allowed)})")
    weights = {}
    for key, value in raw.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{dotted}.{key} must be a non-negative number, got {value!r}")
        weights[key] = float(value)
    total = sum(weights.values())
    if abs(total - 1.0) > WEIGHT_SUM_TOL:
        raise ValueError(f"{dotted} weights sum to {total!r}, expected 1.0 (±{WEIGHT_SUM_TOL})")
    return weights


def _check_probability(cfg: Mapping, dotted: str) -> float:
    value = _cfg_get(cfg, dotted)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{dotted} must be a probability in [0, 1], got {value!r}")
    return float(value)


def _check_quotas(cfg: Mapping, vocab: Mapping[str, dict]) -> dict[str, int]:
    quotas = _cfg_get(cfg, "batch.quotas") or {}
    if not isinstance(quotas, Mapping):
        raise TypeError(f"batch.quotas must be a mapping, got {quotas!r}")
    unknown = sorted(set(quotas) - set(vocab))
    if unknown:
        raise ValueError(f"batch.quotas names terms outside the vocabulary: {unknown}")
    out = {}
    for term, count in quotas.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError(f"batch.quotas.{term} must be a positive int, got {count!r}")
        out[term] = count
    return out


def _check_floors(cfg: Mapping) -> dict[str, int]:
    floors = _cfg_get(cfg, "batch.mix.objective.floors") or {}
    if not isinstance(floors, Mapping):
        raise TypeError(f"batch.mix.objective.floors must be a mapping, got {floors!r}")
    unknown = sorted(set(floors) - set(OBJECTIVE_FAMILIES))
    if unknown:
        raise ValueError(f"batch.mix.objective.floors names unknown families: {unknown}")
    out = {}
    for family, count in floors.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"floors.{family} must be a non-negative int, got {count!r}")
        out[family] = count
    return out


def corpus_share_mode(cfg: Mapping) -> str:
    """`ideas.corpus_share` — the objective-mix basis. Absent = `measured`.

    A knob reader, in this module's fail-loud shape: absent is the documented
    default (an unconfigured run is the pre-W2-A run), anything else has to be
    one of `CORPUS_SHARE_MODES` or the config is refused before a token is
    spent.
    """
    ideas = cfg.get("ideas") if isinstance(cfg, Mapping) else None
    raw = (ideas or {}).get("corpus_share", CORPUS_SHARE_DEFAULT)
    if raw not in CORPUS_SHARE_MODES:
        raise ValueError(
            f"ideas.corpus_share must be one of {list(CORPUS_SHARE_MODES)}, got {raw!r}"
        )
    return str(raw)


def secondary_rate(cfg: Mapping) -> float:
    """`ideas.secondary_rate` — P(an idea gets a secondary). Absent = 0.0.

    0.0 is not just "rarely": it is the byte-identity guarantee. See
    `_draw_core`, where the rate-0 branch short-circuits before any rng call.
    """
    ideas = cfg.get("ideas") if isinstance(cfg, Mapping) else None
    raw = (ideas or {}).get("secondary_rate", SECONDARY_RATE_DEFAULT)
    if not isinstance(raw, (int, float)) or isinstance(raw, bool) or not 0.0 <= raw <= 1.0:
        raise ValueError(f"ideas.secondary_rate must be a probability in [0, 1], got {raw!r}")
    return float(raw)


def objective_corpus_shares(cfg: Mapping, mode: str | None = None) -> dict[str, float]:
    """family -> its share of the corpus the active basis reads (sums to 1).

    `measured` reproduces the pre-W2-A arithmetic EXACTLY — `count / total`
    over every row of `objectives.csv` — so an unconfigured `objective_weights`
    computes the same floats it always has.
    """
    mode = corpus_share_mode(cfg) if mode is None else mode
    if mode not in CORPUS_SHARE_MODES:
        raise ValueError(
            f"ideas.corpus_share must be one of {list(CORPUS_SHARE_MODES)}, got {mode!r}"
        )
    def normalised(counts: Mapping[str, int]) -> dict[str, float]:
        total = sum(counts.values())
        return {f: counts[f] / total for f in OBJECTIVE_FAMILIES}

    if mode == CORPUS_SHARE_OFFICIALS:
        return normalised(load_objective_distribution(cfg, corpus=OFFICIAL_CORPUS))
    measured = normalised(load_objective_distribution(cfg))
    if mode == CORPUS_SHARE_MEASURED:
        return measured
    official = normalised(load_objective_distribution(cfg, corpus=OFFICIAL_CORPUS))
    return {f: 0.5 * measured[f] + 0.5 * official[f] for f in OBJECTIVE_FAMILIES}


def _check_reach_cap(cfg: Mapping) -> float:
    cap = _cfg_get(cfg, "batch.mix.objective.reach_cap")
    if not isinstance(cap, (int, float)) or isinstance(cap, bool) or not 0.0 < cap < 1.0:
        raise ValueError(f"batch.mix.objective.reach_cap must be in (0, 1), got {cap!r}")
    return float(cap)


def _seed_term_counts(cfg: Mapping) -> list[int]:
    """The candidate n values — `ideas.seed_terms_per_idea` is an inclusive range.

    b001-pilot writes [2, 4] -> [2, 3, 4], the uniform draw the B4 brief
    specifies; reading it from config keeps the signed knob from being dead.
    """
    ideas = cfg.get("ideas") if isinstance(cfg, Mapping) else None
    raw = (ideas or {}).get("seed_terms_per_idea", list(SEED_TERMS_DEFAULT))
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"ideas.seed_terms_per_idea must be [min, max], got {raw!r}")
    lo, hi = raw
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (lo, hi)):
        raise ValueError(f"ideas.seed_terms_per_idea must hold ints, got {raw!r}")
    if not MIN_SEED_TERMS <= lo <= hi <= MAX_SEED_TERMS:
        raise ValueError(
            f"ideas.seed_terms_per_idea must sit inside "
            f"[{MIN_SEED_TERMS}, {MAX_SEED_TERMS}] with min <= max, got {raw!r}"
        )
    return list(range(lo, hi + 1))


def _check_tier_sequence(cfg: Mapping) -> list[str] | None:
    """`batch.tier_sequence` — one pinned tier per slot, or None when absent.

    Absent is the default and means every slot keeps its `batch.tiers` draw.
    Present, it has to name a tier for EVERY slot: a short sequence would
    silently hand the tail back to the draw and a long one would silently drop
    its tail, and either way the batch mix would not be the one written down.
    """
    batch = cfg.get("batch") if isinstance(cfg, Mapping) else None
    raw = batch.get("tier_sequence") if isinstance(batch, Mapping) else None
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)):
        raise ValueError(  # noqa: TRY004 — a config defect; every STRICT config error is ValueError
            f"batch.tier_sequence must be a list of tiers, got {raw!r}"
        )
    unknown = [t for t in raw if t not in TIERS]
    if unknown:
        raise ValueError(
            f"batch.tier_sequence names unknown tiers {unknown} (expected {list(TIERS)})"
        )
    size = _cfg_get(cfg, "batch.size")
    if len(raw) != size:
        raise ValueError(
            f"batch.tier_sequence holds {len(raw)} tiers, expected one per slot "
            f"(batch.size={size!r})"
        )
    return list(raw)


def check_config(cfg: Mapping, vocab: Mapping[str, dict]) -> None:
    """Every STRICT config error, raised before a single prose token is spent."""
    _check_probability(cfg, "batch.mix.hazardless")
    _check_probability(cfg, "ideas.failure_family_share")
    _check_weight_map(cfg, "batch.mix.locus", LOCI)
    _check_weight_map(cfg, "batch.tiers", TIERS)
    _check_floors(cfg)
    _check_reach_cap(cfg)
    corpus_share_mode(cfg)
    secondary_rate(cfg)
    _check_quotas(cfg, vocab)
    _seed_term_counts(cfg)
    tier_policy(cfg)  # the `tiers:` block (absent -> None), every key fail-loud
    _check_tier_sequence(cfg)
    # P-1a item 7: the `backends:` block, so a driver typo or a model role
    # missing for the driver IN USE fails here rather than at `get_driver`,
    # mid-batch, after this stage has already paid for its prose. Imported
    # HERE, like the driver itself is below — an injected prose runner must
    # never need `gen.backends` to import.
    from .backends import check_backends_config

    check_backends_config(cfg)


def objective_weights(cfg: Mapping) -> dict[str, float]:
    """Family -> draw weight: floors x the basis rule, then the hard reach cap.

    `measured` (the default) is D24 verbatim: the boost lifts families
    UNDER-REPRESENTED in the measured corpus (tufa + officials collapse onto
    reach/cover, spec §3b). `officials`/`blend` REBASE instead — the weight is
    the corpus share itself, the operator's R-10 "resemble the officials" ruling — and
    the constant block at `CORPUS_SHARE_MODES` is where that choice is argued.

    The cap is the D24 backstop that keeps reach_goal from eating the batch
    however the corpus shares move, and it is the SAME branch in every mode:
    under `measured` reach's boosted share computes 0.101 and the branch never
    fires (the audit's finding); under `officials` its raw share is 11/25 =
    0.44 and it does.
    """
    floors = _check_floors(cfg)
    reach_cap = _check_reach_cap(cfg)
    mode = corpus_share_mode(cfg)
    shares = objective_corpus_shares(cfg, mode)

    weights: dict[str, float] = {}
    for family in OBJECTIVE_FAMILIES:
        # min 1: a family the config floors at 0 (or omits) still stays drawable
        # — under `measured`. Under a rebased basis a 0-share family is weight 0
        # whatever its floor, which is the departure the constant block records.
        base = max(1.0, float(floors.get(family, 0)))
        corpus_share = shares[family]
        if mode == CORPUS_SHARE_MEASURED:
            weights[family] = base * (
                1.0 + max(0.0, DEFICIT_TARGET - corpus_share) * DEFICIT_GAIN
            )
        else:
            weights[family] = base * corpus_share

    total = sum(weights.values())
    if weights["reach_goal"] / total > reach_cap:
        rest = total - weights["reach_goal"]
        if rest <= 0.0:
            raise ValueError("reach_goal holds all objective weight; cannot apply reach_cap")
        scale = (1.0 - reach_cap) / rest
        weights = {
            family: (reach_cap if family == "reach_goal" else weight * scale)
            for family, weight in weights.items()
        }
    return weights


def failure_family_weights(cfg: Mapping) -> dict[str, float]:
    """Family -> draw weight = 0.5 + mean frontier share over its recipe TERMS.

    CAVEAT (mandatory, difficulty-model §3.4): `terms-x-frontier.csv` is
    DESCRIPTIVE over n=25 officials. It steers WHICH families get extra mass
    and nothing else — it is never a predictor of difficulty, and no downstream
    gate may treat it as one. Recipe terms absent from the table contribute 0.
    """
    shares = load_frontier_shares(cfg)
    return {
        family: FAMILY_WEIGHT_BASE + sum(shares.get(t, 0.0) for t in terms) / len(terms)
        for family, terms in FAMILY_RECIPES.items()
    }


def secondary_weights(cfg: Mapping) -> dict[str, dict[str, float]]:
    """primary -> {secondary family: weight}, from the officials' co-occurrence.

    Built ONCE per batch and handed to `_draw_core`, so the draw itself touches
    no disk. Two rules, both from R-10 and both load-bearing:

    * a secondary is never the primary — the entry is dropped from the map, not
      redrawn, so the draw is still exactly one `rng.random()`;
    * a primary with NO official secondary evidence falls back to the
      officials' OVERALL secondary distribution (minus the primary). Measured,
      that is exactly `survive` and `connect`: they are 0/25 as officials'
      primaries, so they have no row of their own to learn from. Every other
      family has at least one (balance -> reach_goal 1, sequence ->
      match_pattern 1), and the fallback is never empty because the overall
      table names 7 distinct families.
    """
    by_primary, overall = load_secondary_distribution(cfg)
    table: dict[str, dict[str, float]] = {}
    for primary in OBJECTIVE_FAMILIES:
        counts = {f: c for f, c in by_primary[primary].items() if f != primary and c > 0}
        if not counts:
            counts = {f: c for f, c in overall.items() if f != primary and c > 0}
        if not counts:
            raise ValueError(
                f"no officials' secondary evidence for primary {primary!r}, and the overall "
                f"secondary table {overall} offers nothing but {primary!r} itself"
            )
        table[primary] = {f: float(c) for f, c in counts.items()}
    return table


def make_dedupe_key(seed_terms: Collection[str], primary: str) -> str:
    """EXACTLY `"|".join(sorted(seed_terms)) + "::" + primary`.

    seed_terms + PRIMARY, and R-10 deliberately did NOT widen it when the
    secondary objective became drawable: two ideas over the same terms and the
    same primary are the same idea whichever secondary they drew. Nobody widens
    this silently — it is the key already written into
    `out/ideas/dedupe-history.jsonl` for every batch ever run.
    """
    return "|".join(sorted(seed_terms)) + "::" + primary


def _draw_seed_terms(
    rng: random.Random,
    vocab: Mapping[str, dict],
    quotas: Mapping[str, int],
    *,
    primary: str,
    failure_family: str | None,
    n: int,
    free_slot_weight: Callable[[Mapping[str, dict], str], float] = _inverse_occurrence,
) -> list[str]:
    """Witness first, then the failure-family recipe, then rare-term free slots.

    `free_slot_weight` re-weights the FREE slots only (the tier `term_bias`
    knob). The witness and recipe pools keep `_inverse_occurrence`
    unconditionally: those two draws are the idea's crosswalk obligations —
    which witness term a family gets, which recipe term a drill gets — and a
    frequency bias there would quietly re-rank the canon's own lists.
    """
    witnesses = {t: _inverse_occurrence(vocab, t) for t in WITNESS_MAP[primary]}
    chosen = [_weighted_choice(rng, witnesses)]

    if failure_family is not None:
        recipe = FAMILY_RECIPES[failure_family]
        # Skip when the witness already IS a recipe term (e.g. sequence's
        # goal.sequence inside the composition/commitment recipe).
        if not any(term in recipe for term in chosen):
            pool = {t: _inverse_occurrence(vocab, t) for t in recipe if t not in chosen}
            chosen.append(_weighted_choice(rng, pool))

    if len(chosen) > n:
        raise RuntimeError(
            f"seed-term target n={n} is smaller than the required witness+recipe "
            f"terms {chosen} — n >= {MIN_SEED_TERMS} must guarantee room"
        )
    while len(chosen) < n:
        pool = {
            term: free_slot_weight(vocab, term)
            * (QUOTA_BOOST if term in quotas else 1.0)
            for term in vocab
            if term not in chosen
        }
        chosen.append(_weighted_choice(rng, pool))
    return chosen


def _tier_seed_counts(policy: TierPolicy | None, tier: str) -> list[int] | None:
    """This tier's own `n` candidates, or None to keep the global knob's.

    A per-tier range REPLACES `ideas.seed_terms_per_idea` for that tier; it
    never adds a draw, because the caller still spends exactly one
    `rng.choice` on whichever list it gets back.
    """
    ranges = policy.seed_terms if policy is not None else None
    if not ranges or tier not in ranges:
        return None
    lo, hi = ranges[tier]
    return list(range(lo, hi + 1))


def _tier_free_slot_weight(
    policy: TierPolicy | None, tier: str
) -> Callable[[Mapping[str, dict], str], float]:
    """The free-slot weight for this tier — rare (the default) or common-official."""
    bias = (policy.term_bias if policy is not None else None) or {}
    if bias.get(tier) == "common-official":
        return _official_occurrence
    return _inverse_occurrence


def _tier_quotas(
    policy: TierPolicy | None, tier: str, quotas: Mapping[str, int]
) -> Mapping[str, int]:
    """`quotas`, or nothing when this tier is outside `quota_boost_tiers`.

    The boost is a coverage instrument: pointing it at t2/t3 only keeps an
    entry-tier idea off the rare terms a quota exists to chase. Emptying the
    map changes WEIGHTS only — the free-slot loop makes the same number of
    rng calls either way.
    """
    allowed = policy.quota_boost_tiers if policy is not None else None
    if allowed is not None and tier not in allowed:
        return {}
    return quotas


def _draw_core(
    cfg: Mapping,
    rng: random.Random,
    vocab: Mapping[str, dict],
    *,
    quotas: Mapping[str, int],
    objective_w: Mapping[str, float],
    family_w: Mapping[str, float],
    seed_counts: list[int],
    tier_override: str | None = None,
    policy: TierPolicy | None = None,
    secondary_w: Mapping[str, Mapping[str, float]] | None = None,
) -> _Core:
    """The rng contract. Order here is frozen; the pilot seeds depend on it.

    The two tier arguments change WHAT is drawn, never HOW MANY draws happen:
    the `batch.tiers` draw below runs even when `tier_override`
    (`batch.tier_sequence`) throws its result away, a per-tier seed range is
    still one `rng.choice`, and the policy's term bias and quota restriction
    only re-weight a pool the free-slot loop was going to draw from anyway.
    With both absent this function is the pre-tier sampler, line for line.

    The secondary objective (R-10) is the ONE thing here that can add rng
    calls, and its rate is read off `cfg` per draw — exactly how
    `batch.mix.hazardless`, `batch.mix.locus` and `batch.tiers` are already
    read three lines below — NOT injected. That is deliberate: it means this
    function is the whole sampler for any caller that hands it a cfg, so the
    m3 draw-space recipe (`_draw_core(cfg, rng, vocab, **m3_args)`) reflects an
    armed `ideas.secondary_rate` without the audit script having to know the
    knob exists. `secondary_w` is a pure speed seam — the precomputed weight
    table `sample_idea` builds once per batch — and when it is None the table
    is loaded here instead. At the default rate 0.0 neither path runs and this
    function is the pre-W2-A sampler exactly.
    """
    hazardless = rng.random() < _check_probability(cfg, "batch.mix.hazardless")
    locus = _weighted_choice(rng, _check_weight_map(cfg, "batch.mix.locus", LOCI))
    drawn_tier = _weighted_choice(rng, _check_weight_map(cfg, "batch.tiers", TIERS))
    tier = tier_override or drawn_tier

    failure_family = None
    if rng.random() < _check_probability(cfg, "ideas.failure_family_share"):
        failure_family = _weighted_choice(rng, family_w)

    primary = _weighted_choice(rng, objective_w)
    # THE RATE-0 PIN (R-10, house rule). `and` short-circuits, so at rate 0.0 —
    # the default, and what every config without an `ideas.secondary_rate`
    # gets — `rng.random()` below is NEVER EVALUATED and this block consumes
    # zero rng. That is the whole reason it is written as one `and` chain and
    # not as a nested `if`: every seeded draw this repo has ever recorded stays
    # reproducible, because the stream is untouched unless the knob is armed.
    # Do not hoist the `rng.random()` out of this condition.
    rate = secondary_rate(cfg)
    secondary = None
    if rate > 0.0 and rng.random() < rate:
        table = secondary_weights(cfg) if secondary_w is None else secondary_w
        secondary = _weighted_choice(rng, table[primary])
    tier_counts = _tier_seed_counts(policy, tier)
    n = rng.choice(seed_counts if tier_counts is None else tier_counts)
    seed_terms = _draw_seed_terms(
        rng,
        vocab,
        _tier_quotas(policy, tier, quotas),
        primary=primary,
        failure_family=failure_family,
        n=n,
        free_slot_weight=_tier_free_slot_weight(policy, tier),
    )
    return _Core(
        hazardless=hazardless,
        locus=locus,
        tier=tier,
        failure_family=failure_family,
        primary=primary,
        seed_terms=seed_terms,
        secondary=secondary,
    )


def build_prose_prompt(
    cfg: Mapping,
    *,
    seed_terms: Collection[str],
    primary: str,
    failure_family: str | None,
    tier: str,
    hazardless: bool,
    locus: str,
    policy: TierPolicy | None = None,
    secondary: str | None = None,
) -> str:
    """Doctrine (verbatim) + our overrides. The overrides always come LAST.

    `policy.prompt_guidance` is what turns the tier line from a label into an
    instruction: it appends the complexity counterweight and the tier's own
    §3.3 paragraph. Without it (or with no `tiers:` block at all) the prompt is
    byte-identical to the pre-tier one.

    `secondary` (R-10) is None for every unconfigured draw, and the objective
    line it produces then is the pre-W2-A line, word for word.

    The LOCUS BLOCK (R-14) is unconditional: it is not a knob, it is the
    definition of a facet this prompt was already passing as a bare label, and
    the measured cost of passing it bare is in `LOCUS_DEFINITIONS`' comment.
    """
    lines = [
        load_doctrine(cfg),
        "",
        OVERRIDE_HEADER,
        "",
        (
            "Build the game around exactly these mechanics-vocabulary terms "
            "(all of them, nothing else):"
        ),
    ]
    lines += [f"`{term}`" for term in seed_terms]
    if secondary is None:
        lines.append(
            f"Primary objective family: {primary} — the win condition must be the one those "
            f"terms witness, and there is no secondary objective to declare."
        )
    else:
        lines.append(
            f"Primary objective family: {primary} — the win condition must be the one those "
            f"terms witness."
        )
        lines.append(
            f"Secondary objective family: {secondary} — a SUPPORTING condition the game also "
            f"reads, never a second way to win: the idea is over when the {primary} condition "
            f"is met. 19 of the 25 official games carry one."
        )
    if failure_family is not None:
        lines.append(
            f"Agent-failure drill: {failure_family} — the idea should make THAT failure mode "
            f"decide whether a player wins, not raw execution difficulty."
        )
    lines.append(
        f"Legibility tier: {tier} · hazardless: {str(hazardless).lower()} · "
        f"interaction locus: {locus}."
    )
    if policy is not None and policy.prompt_guidance:
        # Straight after the tier line, because both lines are that line's
        # meaning: the vendored doctrine above asks for "decently complicated"
        # and difficulty-by-addition, and these two are the counterweight.
        # LEAD (wave 3, R-11 cross-stage close): the tier-gated override —
        # t1 renders the composition-first line verbatim; t2/t3 render the
        # bounded-novelty allowance, so S0's prose prompt and S1's tier
        # section state the same rule instead of arguing across stages.
        lines.append(complexity_override(tier))
        lines.append(TIER_TABLE[tier].guidance)
    # AFTER the tier guidance, not between it and the tier line: contract T-A
    # pinned those two lines "straight after the tier line, because both lines
    # are that line's meaning", and this block is the LOCUS facet's meaning, so
    # it takes the next slot rather than splitting a pinned pair.
    lines.append(LOCUS_DEFINITIONS_BLOCK)
    lines.append(LEVEL_COUNT_LINE)
    lines.append(REPLY_LINE)
    return "\n".join(lines)


def _strip_prose_emphasis(title: str) -> str:
    """Drop the markdown emphasis runs wrapping a title line (`**X**` -> `X`).

    Leading/trailing only, and never a run in the interior: a title is allowed
    to emphasize a word of its own.
    """
    return _PROSE_EMPHASIS_RE.sub("", title).strip()


def _parse_prose(raw: str) -> dict:
    """First non-empty line = title, the rest = one normalized paragraph."""
    if not isinstance(raw, str):
        raise TypeError(f"prose runner returned {type(raw).__name__}, expected str")
    lines = raw.splitlines()
    index = next((i for i, line in enumerate(lines) if line.strip()), None)
    if index is None:
        raise ValueError("prose runner returned no non-empty lines")
    # Emphasis first, then the `#`/`title:` strips, then emphasis again: bold
    # defeats BOTH orders on its own (`**TITLE:** X` only starts with `title:`
    # once the leading `**` is gone, and only loses its `**` once the prefix
    # is), so each pass needs the other.
    title = _strip_prose_emphasis(lines[index].strip()).lstrip("#").strip()
    # Lead fix on review: the prefix strip itself tolerates emphasis so the
    # interleaved form (`**TITLE**: X` -> `TITLE**: X` after the wrap strip)
    # cannot ship decorated either — the class is closed, not the instances.
    title = re.sub(r"(?i)^title[*_]*\s*:\s*", "", title)
    title = _strip_prose_emphasis(title)
    text = " ".join(line.strip() for line in lines[index + 1 :] if line.strip())
    if not title:
        raise ValueError(f"prose title is empty after stripping decorations: {lines[index]!r}")
    if not text:
        raise ValueError("prose body is empty (a title line alone is not an idea)")
    return {"title": title, "text": text}


def _prose_rejects(title: str, text: str) -> list[str]:
    """Why this prose is not a game idea; `[]` means acceptable. PURE.

    Guards the PROSE channel ONLY. It reads no rng and consumes no draw, so the
    seeded term draw is bit-identical whether or not this gate fires — the
    `sample_batch` determinism contract is untouched (the runner takes a prompt
    and returns text; a retry buys another completion, never another draw).
    """
    if not isinstance(title, str) or not isinstance(text, str):
        return [
            (
                f"prose title/text must both be strings, got title={type(title).__name__}, "
                f"text={type(text).__name__}"
            )
        ]
    reasons: list[str] = []
    for label, value in (("title", title), ("text", text)):
        for marker in PROSE_NARRATION_MARKERS:
            if marker in value:
                reasons.append(f"{label} contains first-person process narration {marker!r}")
        for fragment in PROSE_TOOL_FRAGMENTS:
            if fragment in value:
                reasons.append(f"{label} contains the tool/shell fragment {fragment!r}")
        command = _PROSE_SHELL_CMD_RE.search(value)
        if command is not None:
            reasons.append(
                f"{label} contains the shell command {command.group(1).strip()!r} in command "
                f"position"
            )
        for name, pattern in NONTERMINAL_WIN_PATTERNS:
            unbounded = pattern.search(value)
            if unbounded is not None:
                reasons.append(
                    f"{label} states a non-terminal win ({name}): {unbounded.group(0)!r} — "
                    f"affordance §2 REQUIRES a goal state the game can CHECK and D11 requires "
                    f"the solver to reach it, so the objective cannot be a duration, a score "
                    f"with no ceiling or a loss to postpone"
                )
    if len(title) > PROSE_TITLE_MAX_CHARS:
        reasons.append(
            f"title is {len(title)} chars, over the {PROSE_TITLE_MAX_CHARS}-char cap"
        )
    words = len(title.split())
    if words > PROSE_TITLE_MAX_WORDS:
        reasons.append(f"title is {words} words, over the {PROSE_TITLE_MAX_WORDS}-word cap")
    if len(text) < PROSE_TEXT_MIN_CHARS:
        reasons.append(
            f"text is {len(text)} chars, under the {PROSE_TEXT_MIN_CHARS}-char floor"
        )
    return reasons


def _default_prose_runner(cfg: Mapping) -> Callable[[str], str]:
    """The real S0 runner: one `spec_writer` completion per idea.

    `gen.backends` is imported HERE, not at module import: an injected fake
    never needs a driver (or a logged-in CLI) to exist.
    """
    from .backends import get_driver

    driver, model = get_driver(cfg, "spec_writer")

    def run(prompt: str) -> str:
        return driver.complete(prompt, model=model).text

    return run


def validate_idea_dict(
    d: dict, vocab: Collection[str] | None = None, *, allow_secondary: bool = False
) -> list[str]:
    """Every rule an idea.json must satisfy; [] means valid.

    Pure: no cfg, no disk. `vocab` is the term set the seed terms must come
    from — when it is omitted that ONE rule is skipped (documented deviation
    from the brief's single-argument signature line, which its own rules
    section corrects to `(d, vocab)`; the default keeps both call styles
    working). Every other rule always runs, and each violation is its own
    message so a caller can print them as a list.

    `allow_secondary` (R-10) opens the `objective.secondary` slot, and it
    DEFAULTS TO FALSE — "secondary must be None at S0" is still the rule for
    every caller that does not ask otherwise, which is the whole pre-W2-A
    surface. `sample_batch` passes `ideas.secondary_rate > 0`, so a batch that
    never arms the knob validates its ideas against exactly the old rule. When
    it is open the slot is still closed-vocabulary and still may not repeat the
    primary.
    """
    violations: list[str] = []
    if not isinstance(d, dict):
        return [f"idea must be a dict, got {type(d).__name__}"]

    keys = set(d)
    if keys != set(IDEA_KEYS):
        missing = sorted(set(IDEA_KEYS) - keys)
        unexpected = sorted(keys - set(IDEA_KEYS))
        violations.append(f"keys must be exactly {list(IDEA_KEYS)}: {missing=} {unexpected=}")

    terms = d.get("seed_terms")
    terms_ok = isinstance(terms, list) and all(isinstance(t, str) for t in terms)
    if not terms_ok:
        violations.append(f"seed_terms must be a list of strings, got {terms!r}")
    else:
        if not MIN_SEED_TERMS <= len(terms) <= MAX_SEED_TERMS:
            violations.append(
                f"seed_terms must hold {MIN_SEED_TERMS}-{MAX_SEED_TERMS} terms, got {len(terms)}"
            )
        if len(set(terms)) != len(terms):
            violations.append(f"seed_terms must be unique, got {terms}")
        if vocab is not None:
            unknown = sorted({t for t in terms if t not in vocab})
            if unknown:
                violations.append(f"seed_terms outside the vocabulary: {unknown}")

    objective = d.get("objective")
    primary = None
    if not isinstance(objective, dict):
        violations.append(f"objective must be a dict, got {objective!r}")
    else:
        primary = objective.get("primary")
        if primary not in OBJECTIVE_FAMILIES:
            violations.append(
                f"objective.primary {primary!r} must be one of {list(OBJECTIVE_FAMILIES)}"
            )
        if "secondary" not in objective:
            violations.append("objective.secondary is required (None at S0; S1 decides it)")
        elif objective["secondary"] is not None:
            secondary = objective["secondary"]
            if not allow_secondary:
                violations.append(
                    f"objective.secondary must be None at S0, got {secondary!r}"
                )
            elif secondary not in OBJECTIVE_FAMILIES:
                violations.append(
                    f"objective.secondary {secondary!r} must be one of "
                    f"{list(OBJECTIVE_FAMILIES)}"
                )
            elif secondary == primary:
                violations.append(
                    f"objective.secondary {secondary!r} repeats objective.primary — a "
                    f"secondary objective is a DIFFERENT family"
                )
    if terms_ok and primary in WITNESS_MAP and not any(
        term in WITNESS_MAP[primary] for term in terms
    ):
        violations.append(
            f"objective {primary!r} is unwitnessed: seed_terms must include one of "
            f"{list(WITNESS_MAP[primary])}"
        )

    family = d.get("failure_family")
    if family is not None and family not in FAILURE_FAMILIES:
        violations.append(
            f"failure_family {family!r} must be None or one of {list(FAILURE_FAMILIES)}"
        )
    elif family in FAMILY_RECIPES and terms_ok and not any(
        term in FAMILY_RECIPES[family] for term in terms
    ):
        violations.append(
            f"failure_family {family!r} needs a recipe term in seed_terms: one of "
            f"{list(FAMILY_RECIPES[family])}"
        )

    if d.get("tier") not in TIERS:
        violations.append(f"tier {d.get('tier')!r} must be one of {list(TIERS)}")

    mix_class = d.get("mix_class")
    if not isinstance(mix_class, dict):
        violations.append(f"mix_class must be a dict, got {mix_class!r}")
    else:
        if not isinstance(mix_class.get("hazardless"), bool):
            violations.append(
                f"mix_class.hazardless must be a bool, got {mix_class.get('hazardless')!r}"
            )
        if mix_class.get("locus") not in LOCI:
            violations.append(
                f"mix_class.locus {mix_class.get('locus')!r} must be one of {list(LOCI)}"
            )

    prose = d.get("prose")
    if not isinstance(prose, dict):
        violations.append(f"prose must be a dict, got {prose!r}")
    else:
        for field in ("title", "text"):
            value = prose.get(field)
            if not isinstance(value, str) or not value.strip():
                violations.append(f"prose.{field} must be a non-empty string, got {value!r}")

    key = d.get("dedupe_key")
    if terms_ok and isinstance(primary, str):
        expected = make_dedupe_key(terms, primary)
        if key != expected:
            violations.append(f"dedupe_key {key!r} must be {expected!r}")
    elif not isinstance(key, str) or not key:
        violations.append(f"dedupe_key must be a non-empty string, got {key!r}")

    return violations


def sample_idea(
    cfg: Mapping,
    rng: random.Random,
    *,
    batch_id: str,
    index: int,
    exclude_keys: Collection[str] = frozenset(),
    known_keys: Collection[str] = frozenset(),
    prose_runner: Callable[[str], str] | None = None,
    tier_override: str | None = None,
    policy: TierPolicy | None = None,
) -> Idea:
    """Draw ONE idea: mix -> objective -> seed terms -> dedupe -> prose.

    `exclude_keys` (already drawn this batch) and `known_keys` (recent history,
    injectable so a test never touches disk) are both rejection sets; a
    collision resamples the WHOLE core, and prose is only ever bought for the
    accepted draw. Reads no history file itself — `sample_batch` owns that.

    `tier_override` pins this slot's tier (`batch.tier_sequence`) and survives
    every dedupe redraw — a resample is the same slot, so it is still that
    slot's tier. `policy` is the parsed `tiers:` block; `sample_batch` parses
    it once and passes it down, and a direct caller who omits it gets the
    block parsed from `cfg` here rather than silently ignored.
    """
    if not isinstance(index, int) or isinstance(index, bool) or index < 1:
        raise ValueError(f"index must be a 1-based int, got {index!r}")
    if tier_override is not None and tier_override not in TIERS:
        raise ValueError(f"tier_override {tier_override!r} must be one of {list(TIERS)}")
    vocab = load_vocab(cfg)
    check_config(cfg, vocab)
    if policy is None:
        policy = tier_policy(cfg)

    quotas = _check_quotas(cfg, vocab)
    objective_w = objective_weights(cfg)
    family_w = failure_family_weights(cfg)
    seed_counts = _seed_term_counts(cfg)
    # Built only when the knob is armed: an unconfigured run reads the officials'
    # co-occurrence table not at all, exactly as it never did.
    rate = secondary_rate(cfg)
    secondary_w = secondary_weights(cfg) if rate > 0.0 else None
    banned = set(exclude_keys) | set(known_keys)

    collisions: list[str] = []
    core = None
    for _ in range(MAX_DEDUPE_TRIES):
        candidate = _draw_core(
            cfg,
            rng,
            vocab,
            quotas=quotas,
            objective_w=objective_w,
            family_w=family_w,
            seed_counts=seed_counts,
            tier_override=tier_override,
            policy=policy,
            secondary_w=secondary_w,
        )
        key = make_dedupe_key(candidate.seed_terms, candidate.primary)
        if key not in banned:
            core = candidate
            break
        collisions.append(key)
    if core is None:
        raise RuntimeError(
            f"{batch_id}-i{index:03d}: {MAX_DEDUPE_TRIES} draws all collided with known "
            f"ideas — collisions: {sorted(set(collisions))}"
        )

    runner = prose_runner or _default_prose_runner(cfg)
    prompt = build_prose_prompt(
        cfg,
        seed_terms=core.seed_terms,
        primary=core.primary,
        failure_family=core.failure_family,
        tier=core.tier,
        hazardless=core.hazardless,
        locus=core.locus,
        policy=policy,
        secondary=core.secondary,
    )
    idea_id = f"{batch_id}-i{index:03d}"
    prose = _parse_prose(runner(prompt))
    rejects = _prose_rejects(prose["title"], prose["text"])
    if rejects:
        # ONE corrective retry, then fail LOUD. Never silently accept, truncate
        # or synthesize prose: the orchestrator surfaces mechanical S0 failures,
        # and a fabricated idea costs an S1 session to discover.
        retry_prompt = f"{prompt}\n{PROSE_RETRY_LINE.format(reasons='; '.join(rejects))}"
        prose = _parse_prose(runner(retry_prompt))
        again = _prose_rejects(prose["title"], prose["text"])
        if again:
            raise RuntimeError(
                f"{idea_id}: prose rejected twice — attempt 1: {'; '.join(rejects)} — "
                f"attempt 2 (after the corrective retry): {'; '.join(again)}"
            )

    return Idea(
        id=idea_id,
        seed_terms=list(core.seed_terms),
        objective={"primary": core.primary, "secondary": core.secondary},
        failure_family=core.failure_family,
        tier=core.tier,
        mix_class={"hazardless": core.hazardless, "locus": core.locus},
        prose=prose,
        dedupe_key=make_dedupe_key(core.seed_terms, core.primary),
    )


def batch_out_dir(batch_id: str, out_dir: Path | str | None = None) -> Path:
    return Path(out_dir) if out_dir is not None else IDEAS_ROOT / batch_id


def _history_path() -> Path:
    """Read the module global every call so a test can rebind it."""
    return Path(DEDUPE_HISTORY_PATH)


def load_recent_keys(cfg: Mapping, batch_id: str) -> frozenset[str]:
    """Dedupe keys from the last `ideas.dedupe_window` DISTINCT other batches.

    File order is the window order. The CURRENT batch is excluded entirely —
    both from the count and from the returned keys — so re-running a batch id
    with the same seed reproduces it instead of colliding with itself.
    """
    window = _cfg_get(cfg, "ideas.dedupe_window")
    if not isinstance(window, int) or isinstance(window, bool) or window < 0:
        raise ValueError(f"ideas.dedupe_window must be a non-negative int, got {window!r}")
    path = _history_path()
    if window == 0 or not path.is_file():
        return frozenset()

    rows: list[dict] = []
    order: list[str] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: corrupt dedupe history row: {exc}") from exc
            if not isinstance(row, dict) or "batch_id" not in row or "key" not in row:
                raise ValueError(f"{path}:{lineno}: history row needs batch_id + key: {row!r}")
            rows.append(row)
            if row["batch_id"] != batch_id and row["batch_id"] not in order:
                order.append(row["batch_id"])
    recent = set(order[-window:])
    return frozenset(row["key"] for row in rows if row["batch_id"] in recent)


def _quote(value) -> str:
    text = repr(value)
    return text if len(text) <= IDEA_DIVERGENCE_CHARS else text[:IDEA_DIVERGENCE_CHARS] + "…"


def _kept_idea(path: Path, drawn: Idea) -> Idea:
    """The idea already ON DISK at `path`, once it agrees with the fresh draw.

    Structural agreement is the whole test (`IDEA_STRUCTURAL_FIELDS`): a
    divergence there means the draw itself moved (seed or config), which is
    never something to silently overwrite. Prose is deliberately not compared —
    it is the live field, and the file is the artifact.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: idea file already there is not parsable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(  # noqa: TRY004 — a corrupt artifact, not a caller type error
            f"{path}: idea file already there is not a JSON object: {_quote(data)}"
        )

    fresh = drawn.to_json_dict()
    diverged = [
        f"{field}: on disk {_quote(data.get(field))} != drawn {_quote(fresh[field])}"
        for field in IDEA_STRUCTURAL_FIELDS
        if data.get(field) != fresh[field]
    ]
    if diverged:
        raise ValueError(
            f"{path}: the drawn idea diverges STRUCTURALLY from the file already there "
            f"({'; '.join(diverged)}) — the draw moved (seed or config), so this is a "
            "redraw, not a resume: write it to a fresh batch dir instead."
        )

    prose = data.get("prose")
    if not isinstance(prose, Mapping):
        raise ValueError(  # noqa: TRY004 — a corrupt artifact, not a caller type error
            f"{path}: idea file already there has no 'prose' mapping, so the idea on disk "
            f"cannot be rebuilt: {_quote(prose)}"
        )
    return Idea(
        id=data["id"],
        seed_terms=list(data["seed_terms"]),
        objective=dict(data["objective"]),
        failure_family=data["failure_family"],
        tier=data["tier"],
        mix_class=dict(data["mix_class"]),
        prose=dict(prose),
        dedupe_key=data["dedupe_key"],
    )


def _append_history(batch_id: str, ideas: list[Idea]) -> Path:
    """Append this draw's dedupe keys to the SHARED history, under one flock.

    CONTRACT H-1 item 8 (2026-10-06). The history is one file for every batch
    ever run, and P-5's per-batch draw lock (`orchestrator.s0_draw_lock_path`)
    serializes drawers of the SAME batch only — two DIFFERENT batches drawing at
    once each held their own lock and appended here unguarded, one `write` per
    idea, so their rows could interleave mid-call or tear. The cure is the
    ledger's own idiom (`orchestrator._append_lines`): the call's rows as ONE
    blob, `flock(LOCK_EX)` from before the write to the close, flush + fsync.
    Writer-side only, exactly like the ledger — no reader here takes a lock.

    Out of scope, said once: batch A can still READ the history (its dedupe
    window) before batch B's append lands, so two concurrent batches can draw
    the same key. That is a property of a read-then-append window, not of this
    append, and the window is a de-duplication preference, never a guarantee.
    """
    path = _history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    blob = "".join(
        json.dumps({"batch_id": batch_id, "key": idea.dedupe_key, "ts": stamp}) + "\n"
        for idea in ideas
    )
    with path.open("a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    return path


def sample_batch(
    cfg: Mapping,
    *,
    batch_id: str,
    seed: int | None = None,
    prose_runner: Callable[[str], str] | None = None,
    out_dir: Path | None = None,
) -> list[Idea]:
    """Draw `batch.size` ideas, validate them ALL, then write + record them.

    Determinism contract: same cfg + same seed + same prose runner => the
    written files are byte-identical. (The history file carries a timestamp and
    is deliberately not part of that contract.)

    An idea file already on disk is NEVER overwritten. The prose comes from a
    live driver call, so a second process re-draws structurally identical ideas
    with different prose — and the idea file is what §2 content-addresses, so
    rewriting it restages every stage downstream of a resume for no semantic
    gain. A file already there is therefore kept byte-for-byte once its
    `IDEA_STRUCTURAL_FIELDS` match the fresh draw, a structural divergence
    raises, and only the ideas this call actually WROTE reach the dedupe
    history (nothing was drawn-and-kept, so nothing new belongs in it). The
    returned list describes what is ON DISK: a kept idea is rebuilt from its
    own file, prose included.
    """
    vocab = load_vocab(cfg)
    check_config(cfg, vocab)  # every STRICT error before any prose spend

    size = _cfg_get(cfg, "batch.size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ValueError(f"batch.size must be a positive int, got {size!r}")
    if seed is None:
        seed = _cfg_get(cfg, "batch.seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise TypeError(f"seed must be an int, got {seed!r}")
    rng = random.Random(seed)

    floors = _check_floors(cfg)
    floor_total = sum(floors.values())
    if size < floor_total:
        warnings.warn(
            FLOORS_WARNING.format(size=size, floor_total=floor_total),
            RuntimeWarning,
            stacklevel=2,
        )
    quotas = _check_quotas(cfg, vocab)
    if quotas:
        # Unconditional: this module never enforces term minima, it only boosts
        # their draw weight, so the degradation is real whenever quotas exist.
        warnings.warn(
            QUOTAS_WARNING.format(
                quotas=dict(sorted(quotas.items())),
                lo=MIN_SEED_TERMS,
                hi=MAX_SEED_TERMS,
                boost=int(QUOTA_BOOST),
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    # Parsed ONCE for the whole batch (both are pure reads of cfg, already
    # validated by check_config above) and handed to every slot: the tier
    # policy is a batch property, and slot i takes sequence[i] — the position
    # in the batch, which is what a kept file on disk occupies too.
    policy = tier_policy(cfg)
    sequence = _check_tier_sequence(cfg)

    runner = prose_runner or _default_prose_runner(cfg)
    history = load_recent_keys(cfg, batch_id)
    drawn: set[str] = set()
    ideas: list[Idea] = []
    for index in range(1, size + 1):
        idea = sample_idea(
            cfg,
            rng,
            batch_id=batch_id,
            index=index,
            exclude_keys=drawn,
            known_keys=history,
            prose_runner=runner,
            tier_override=None if sequence is None else sequence[index - 1],
            policy=policy,
        )
        drawn.add(idea.dedupe_key)
        ideas.append(idea)

    # Validate the WHOLE batch before writing any of it: a half-written batch
    # directory is worse than none.
    vocab_terms = set(vocab)
    allow_secondary = secondary_rate(cfg) > 0.0
    for idea in ideas:
        violations = validate_idea_dict(
            idea.to_json_dict(), vocab_terms, allow_secondary=allow_secondary
        )
        if violations:
            raise RuntimeError(f"{idea.id} failed validation: {violations}")

    target = batch_out_dir(batch_id, out_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths = [target / f"idea-{index:03d}.json" for index in range(1, size + 1)]
    # Everything ALREADY there is read and checked BEFORE anything is written,
    # for the reason stated above: a divergence at index 2 must not leave index
    # 1 freshly written behind it.
    kept = {
        path.name: _kept_idea(path, idea)
        for path, idea in zip(paths, ideas, strict=True)
        if path.is_file()
    }
    on_disk: list[Idea] = []
    written: list[Idea] = []
    for path, idea in zip(paths, ideas, strict=True):
        if path.name in kept:
            on_disk.append(kept[path.name])  # a resume: the bytes §2 hashed stay put
            continue
        path.write_text(
            json.dumps(idea.to_json_dict(), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        on_disk.append(idea)
        written.append(idea)
    if written:
        _append_history(batch_id, written)
    return on_disk


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S0 idea sampler (one driver call per idea)")
    parser.add_argument("--config", default="config/b001-pilot.yaml")
    parser.add_argument("--batch-id", default=None, help="default: cfg batch.id")
    parser.add_argument("--seed", type=int, default=None, help="default: cfg batch.seed")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    batch_id = args.batch_id or _cfg_get(cfg, "batch.id")
    # CONTRACT H-1 item 7 (2026-10-06): THE SAME LOCK AT THE SAME SCOPE as the
    # pipeline's drawer (`orchestrator.default_runners`'s `s0_ideas` runner,
    # contract P-5 addendum 1) — the per-batch `.sample-batch.lock`, exclusive,
    # held across the WHOLE `sample_batch` call. This hand-run drawer used to
    # take no lock at all, so a maintainer re-drawing a batch while that batch
    # was live could interleave with a child's re-draw: both read the idea files
    # and the history before either wrote, and the history got the keys twice.
    # The path is the orchestrator's own function, imported here rather than
    # re-spelled, so there is one lock name and not two that could drift apart
    # (and imported HERE because `gen.orchestrator` is a heavy import a library
    # caller of this module never needs).
    from .orchestrator import s0_draw_lock_path

    lock = s0_draw_lock_path(batch_id)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        ideas = sample_batch(cfg, batch_id=batch_id, seed=args.seed)
    for idea in ideas:
        print(
            f"[s0] {idea.id} | {idea.tier} | {idea.mix_class['locus']} | "
            f"{idea.failure_family or '-'} | {idea.objective['primary']} | "
            f"{', '.join(idea.seed_terms)}"
        )
    print(f"[s0] {len(ideas)} idea(s) -> {batch_out_dir(batch_id)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
