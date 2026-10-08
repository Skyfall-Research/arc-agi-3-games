"""S1 — spec writer + linter (architecture §3 S1; pilot B5).

Prompt = tufa doctrine (vendored, verbatim) + spec §11 schema + §3b crosswalk.
Linter = PURE CODE over spec.yaml implementing the full §11 kill list incl.
objective-not-witnessed. idea.json -> spec.yaml + spec.md + lint-report.json.

Two halves, deliberately separable:

* `lint_spec(spec, vocab, idea=None, tier_policy=None)` is PURE — no config, no
  disk, no driver (the tier policy is PASSED IN, never read from config here).
  It takes the parsed yaml and the term set and returns every violation it can
  see. Rules run INDEPENDENTLY: a spec broken six ways yields six kills, and
  each kill's `detail` names the offender (field · term · level index ·
  keyword) so a reject is actionable without re-reading the spec. The one
  short-circuit is structural: if the document has no `game` mapping there is
  nothing for the other rules to read, so that single schema kill is returned
  alone. Rules whose input is itself malformed (e.g. `terms` is not a list of
  strings) are SKIPPED rather than fired on rubble — schema already named that
  offender, and a second derived kill would only hide it.
* `run_s1(idea_path, cfg)` is the impure half: prompt -> writer -> extract ->
  lint -> four artifacts on disk.

`spec_hash` is the sha256 of the spec yaml TEXT, so it identifies the exact
bytes stage 2 will implement. `lint_spec` never sees that text (it is handed a
dict), so it sets `spec_hash=""` and `run_s1` fills the real hash in before
writing the report. A caller that lints a dict it loaded itself and wants a
hash must hash its own text the same way.

ARTIFACTS PERSIST ON KILL: a killed spec still writes idea.json / spec.md /
spec.yaml / lint-report.json. Only the report says kill — the S1 output of a
rejected idea is evidence, and the B11 orchestrator's kill->S0 routing reads it.

CLI:  python -m gen.s1_spec --idea out/ideas/b001-pilot/idea-001.json
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import os
import re
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import yaml

from . import canon_docs, tiers
from .config import REPO_ROOT, load_config
from .s0_ideas import FAILURE_FAMILIES, OBJECTIVE_FAMILIES, WITNESS_MAP, load_vocab

# --- canon inputs (READ-ONLY, resolved under cfg["duckwm_docs"]) -------------
# The WHOLE spec prompt is the asset (D22 vendors the file; S0 takes the idea
# doctrine above the marker, S1 takes this file entire).
DOCTRINE_MD = "third-party/re-arc-3/spec_prompt.md"
DOCTRINE_FIRST_LINE = "You are designing"
# D28 findability crosswalk — the review response's table, not the amendment
# doc: the response is what names the mechanic words agents actually reach for.
CROSSWALK_MD = "provenance/reviews/vocab-review-response.md"
CROSSWALK_START = "## Crosswalk"
CROSSWALK_END = "Amendment doc:"
# §11 is the machine-checkable schema this module lints against; the prompt
# carries it byte-for-byte so the writer and the linter cannot drift.
SPEC_MD = "spec-v0.3.md"
SPEC_SECTION_11 = "## §11"
SPEC_FENCE_OPEN = "```yaml"
SPEC_FENCE_CLOSE = "```"

CORPUS_ROOT = REPO_ROOT / "out" / "corpus"

# --- the §11 closed enums (spec-v0.3 §11 + §5) ------------------------------
# NOT imported from s0_ideas: that module's LOCI is the idea-stage mix spelling
# ("mover"/"selection"/"click"); these are the spec-field spellings. The two
# are bridged by LOCUS_SPEC_SPELLING below, which is prompt-side only.
KILL_RULES = (
    "schema",
    "unknown-terms",
    "objective-unwitnessed",
    "missing-knobs",
    "curriculum",
    "palette-collision",
    "undeclared-deception",
    "contradiction",
)
LOCI = ("unique-mover", "selection", "click-only")
REFUSALS = ("visible", "free", "silent-charged")
GOAL_LEGIBLE = ("obvious", "inferable", "opaque")
DANGER_TELLS = ("unique-hue", "texture", "absence", "camouflage", "none")
HUD_RESERVED = ("row63", "row0", "col0", "custom-rect")
# `invert` JOINS the canon triple at contract A2 / R-11: a level that flips a
# standing rule (the features-schema's own sense of the word). It is 3/158 of
# the officials' non-first levels and 0/47 of ours — un-generatable, because
# this tuple is what `_schema_levels` accepts and the writer was never offered
# the value. The three canon values keep their exact spelling and order, so a
# reader of `escalation.csv` and a reader of this tuple see the same vocabulary.
#
# NOTE FOR THE LEAD, not adapted here: canon `spec-v0.3.md` §11 writes
# `relation_to_prev: new | reuse | compose` (line 314) and §7 repeats it — the
# schema block the writer prompt embeds VERBATIM from READ-ONLY canon therefore
# lists three values while this enum accepts four. The curriculum note below
# states the extension in the prompt, which is what keeps the writer in sync;
# closing the canon side is a duckWM edit this contract may not make.
RELATIONS = ("new", "reuse", "compose", "invert")
RELATION_INVERT = "invert"
LEVELS_MIN, LEVELS_MAX = 6, 10

# §11 `game:` fields — this tuple IS the mandatory list; anything else inside
# `game` is an unknown-field WARN (never a kill: the writer may usefully add
# notes, and stage 2 ignores what it does not read).
GAME_FIELDS = (
    "slug",
    "title",
    "idea_ref",
    "terms",
    "objective",
    "locus",
    "actions",
    "knobs",
    "palette",
    "hud",
    "neg2_readers",
    "layers",
    "layout",
    "levels",
    "budget",
    "solver_notes",
)
KNOB_FIELDS = ("refusal", "goal_legible", "danger_tell", "deceptions")
# --- the transient-refusal declaration (contract B1 / R-08) -----------------
# §6:160's bar for a visible refusal is a signal "persisting >=1 settled frame".
# Six of our seven shipped games' refusal signals appear in ZERO captured
# records and a seventh renders its flash into `frame[-2]`, which cannot survive
# by construction — while all seven declare `knobs.refusal: visible`.
#
# `knobs.refusal_transient` is the DECLARED exception: a refusal signal that is
# deliberately transient and is not something the player has to learn from. It
# is OPTIONAL and a bool — absence is silence, exactly like `palette.background`
# and `palette.tiny_token`, and a key written down is held to one. It is NOT a
# member of `KNOB_FIELDS`, which is the MANDATORY list (a member missing is a
# kill), for the reason `OPTIONAL_GAME_FIELDS` exists one block up.
#
# The EFFECT is split across two contracts and this module owns only the
# PROMISE: `refusal-persistence` below records that a spec declaring
# `refusal: visible` without this key has promised a settled-frame-persistent
# signal. B3's gate check is what reads the promise against A1's trace.
REFUSAL_TRANSIENT_FIELD = "refusal_transient"
OPTIONAL_KNOB_FIELDS = (REFUSAL_TRANSIENT_FIELD,)
# The one `refusal` value that makes the promise. `free` and `silent-charged`
# say nothing about a persistent signal: `silent-charged` promises the opposite,
# and `free` is about cost, not about paint.
REFUSAL_VISIBLE = "visible"
assert REFUSAL_VISIBLE in REFUSALS, "REFUSAL_VISIBLE must name a §5 refusal mode"
ACTION_KEYS = tuple(f"ACTION{i}" for i in range(1, 8))
ACTION_STATES = ("declared", "absent")
LAYERS_VALUE = "explicit"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PALETTE_MIN, PALETTE_MAX = 0, 15
PALETTE_ROLES = ("you", "goal", "danger")
GRID_MIN, GRID_MAX = 1, 64
MAX_CONSECUTIVE_NEW = 2

# --- the render declaration (contract V-B) ----------------------------------
# `VISUAL_LEGIBILITY` rule 1 ("ONE RENDER SCALE") has been INSTRUCTED since
# b002 and never DECLARED, so nothing downstream could compare a built game
# against a stated intent. `game.render` and `game.palette.background` are the
# declaration; both are OPTIONAL, because every spec written before this
# contract is still a valid spec and absence is silence, never a finding.
#
# GAME_FIELDS is the MANDATORY list (a member missing is a kill), so an
# optional field cannot join it — it joins the KNOWN keys instead, which is
# what keeps it off the unknown-field warn.
#
# `hazardless_override` joins it for the same reason (contract W1-B / R-16):
# it is the DECLARED departure from the idea's `mix_class.hazardless` facet,
# every spec written before this contract declares none, and absence is
# silence. See `MIX_HAZARDLESS_KILL_SENTENCE` for what it exempts.
HAZARDLESS_OVERRIDE_FIELD = "hazardless_override"
# --- the chrome declaration (contract B1 / R-03) ----------------------------
# The comparative audit counted TWO authored decor objects in the whole 7-game
# corpus against the officials' 28-31 decor rows, and named the absence the
# direct cause of the emptiness finding: their boards read as PLACES because
# authored inert structure — letterboxes, bezels, panel slabs, dividers — marks
# where the world ends. Our `occupied_extent` is 0.47x theirs and three of seven
# games sit below the officials' whole observed band
# (`visual_canon.OFFICIAL_CHROME`).
#
# `game.chrome` is where a spec DECLARES that structure, and it is the smallest
# honest schema for the job: a list of {kind, where} entries and nothing else.
# It joins `render`/`hazardless_override` on their exact terms — OPTIONAL, so
# every spec written before this contract is still a valid spec and absence is
# silence; a key written down is a DECLARATION and is held to one, so an empty
# list, a non-mapping entry, an unknown `kind` or an unknown `where` is a
# `schema` kill rather than a silently ignored field (the `tiny_token`
# precedent, W2-D).
#
# The EFFECT is `s3_visual._chrome_extent_check`'s business, two stages later,
# and it is PAIRED: a game is flagged only when its `occupied_extent` is below
# the officials' band AND it declares no chrome at all.
CHROME_FIELD = "chrome"
CHROME_ENTRY_FIELDS = ("kind", "where")
# The four idioms the officials draw, named for what they are rather than for
# which game draws them: `visual_canon.CHROME_IS_STRUCTURE` carries the worked
# example and the official cite for each.
CHROME_KINDS = ("letterbox", "panel", "divider", "bezel")
# `where` names a region the visual gate can LOCATE on the board, so that the
# card can report how many cells the declared chrome actually paints. Four edges
# plus the full ring, plus `custom` for a geometry this schema cannot express —
# the `hud.reserved: custom-rect` precedent exactly, including its consequence:
# a `custom` region is counted as a DECLARATION and measured as `not-checked`,
# never measured against a guessed geometry.
CHROME_CUSTOM = "custom"
CHROME_WHERE = ("top", "bottom", "left", "right", "border", CHROME_CUSTOM)
CHROME_DETAIL = (
    f"must be a non-empty list of {{{CHROME_ENTRY_FIELDS[0]}: <one of "
    f"{list(CHROME_KINDS)}>, {CHROME_ENTRY_FIELDS[1]}: <one of {list(CHROME_WHERE)}>}} "
    f"mappings naming the INERT authored structure this game draws (R-03's framing "
    f"rule) — omit the key when it draws none"
)
OPTIONAL_GAME_FIELDS = ("render", HAZARDLESS_OVERRIDE_FIELD, CHROME_FIELD)
RENDER_FIELDS = ("cell_px",)
CELL_PX_MIN, CELL_PX_MAX = 1, 8
# The ARC-AGI-3 camera is 64x64 PIXELS and `layout.grid` counts CELLS, so the
# declared scale times the declared grid has to fit inside it. 4 px x 16 cells
# is exactly 64 and PASSES; the bound is `>`, not `>=`.
CANVAS_PX = 64
# affordance §9: "`5` black — background/outline default (BACKGROUND_COLOR in
# 8+ officials)". The canon default is documentation, never a linter default:
# an absent `background` stays UNSTATED and no rule invents a 5 for it.
BACKGROUND_DEFAULT = 5

# --- the tiny-token declaration (contract W2-D / R-02) ----------------------
# R-02's escape hatch ("if the spec you were given genuinely requires a tiny
# token — a single-pixel marker the mechanic is *about* — draw it and nothing
# else that way", `visual_canon.FLOOR_AND_FOOTPRINT` rule 3) had nowhere in the
# §11 block to live, so it was declared ONLY in batch config
# (`gate.role_footprint_exempt`). That made the exception an OPERATOR's, after
# the fact, about a game already built. `game.palette.tiny_token` is the SPEC's
# own version of it: the roles this game draws smaller than one logical cell ON
# PURPOSE, written down by whoever wrote the spec, before anything is measured.
#
# OPTIONAL, on `palette.background`'s exact terms: absence is silence (no spec
# written before this contract declares one, and no rule invents a claim from
# the silence), but a key written down is a DECLARATION and is held to one —
# an empty list, a repeat, or a role nothing else in §11 knows about declares
# nothing, so each is a schema kill rather than a silently ignored field. The
# roles are `PALETTE_ROLES` because those are the roles `s3_visual`'s
# `role-footprint` check measures; `background` is not among them (it is the
# field, not a thing drawn on it) and naming it is the "unknown role" kill.
#
# The EFFECT is `s3_visual._role_footprint_check`'s business, one stage later:
# a declared role that lands under the floor is measured exactly as before and
# recorded `exempt-declared` instead of `fail`.
TINY_TOKEN_FIELD = "tiny_token"
TINY_TOKEN_DETAIL = (
    f"must be a non-empty list of distinct roles from {list(PALETTE_ROLES)} that this game "
    f"draws SMALLER than one logical cell on purpose (R-02's declared exception) — omit the "
    f"key when it draws none that way"
)

# `lint.require_render` (config-driven; the linter itself stays pure) — the
# detail is one string so the knob's kill reads the same everywhere.
RENDER_REQUIRED_DETAIL = (
    "game.render: missing (required by this batch's config — lint.require_render)"
)

# The §2.8 palette exemption: overloading a semantic index is legal ONLY as a
# DECLARED deception lever ("Overloading is a *declared* deception lever only",
# spec §2 REQUIRED 8 / affordance §7.2), so the exemption keys on this word
# appearing in a knobs.deceptions entry.
OVERLOAD_KEYWORD = "overload"
# C3's escape hatch: a survive objective needs a clock that is NOT the budget.
SURVIVE_CLOCK_TERMS = ("hazard.timed", "state.wait", "gate.phase")
HAZARD_PREFIXES = ("hazard.", "loss.")

# --- deception catalog ------------------------------------------------------
# RE-GROUNDED ON THE SIX SIGNED LEVERS (contract E-1, 2026-10-05). The levers
# are `design/objects/affordance-language.md` §7 "The deception catalog (levers,
# all frame-verified)", signed 2026-09-18, each with its own per-official
# frame-verified exhibits; `canon_docs.load_deception_levers` quotes all six
# VERBATIM into the three prompts that have to agree about them (the writer's,
# the implementer's, the blind auditor's). THIS table is the other half of that
# grounding: which single keyword each lever is reported under, and every other
# spelling that folds onto it.
#
# WHAT E-1 MEASURED. The catalog used to be a flat 11-keyword tuple in which
# "camouflage" and "palette overload" were two levers, "false tell" and "lying
# display" two more, and "look-alike" / "lookalike" / "mimic" / "disguise" four
# — while the prompts handed those words out with NO definitions. So one trait
# could be named four different ways across five audit rounds (b005r2's echo
# game) and six ways across eight (g20261001-1's seamlock) without any single
# naming being wrong. The churn was keyword CHOICE, not open vocabulary: the
# catalog was already closed and regex-matched on both sides. The six levers are
# the unit now, and a spelling is a spelling.
#
# NOTHING PREVIOUSLY MATCHABLE BECAME UNMATCHABLE. Every one of the 11 old
# keywords is still a spelling below and still detects; it folds onto its lever
# instead of standing as one. Declaration is unchanged squashed-substring
# containment, now satisfied by ANY spelling of the lever, so every shipped
# `knobs.deceptions` entry keeps declaring exactly what it declared.
#
# CANON ATTESTATION, carried over: "mimic", "disguise", "false tell" and "fake
# tell" have no occurrence anywhere in design/ + mechanics/ + spec-v0.3.md — they
# are prose synonyms a writer reaches for, kept as language coverage because the
# scanner reads PROSE sketches. "camouflage" is attested (§7.2's own ka59
# wall/letterbox exhibit, and §3's weak-tell list) but it is not a lever of its
# own there: it is how §7.2 reads on the board.
#
# §7.5 IS DELIBERATELY KEYWORDLESS, unchanged by E-1. Its lever is invisible
# load-bearing STATE, but `info.hidden_geometry` is a legitimate §3 vocabulary
# term and hiding geometry is ordinary sketch prose ("a hidden switch behind the
# wall"), so a bare "hidden" keyword would kill honest specs. It is quoted to all
# three prompts (it is canon) and caught where it always was: the
# intent-verifier's both-direction declared-vs-detected diff (§9 gate 3). Giving
# it a keyword would be a POLICY change, and E-1 is vocabulary semantics.
#
# ONE READING TO EXPECT: §7.1's own exhibit list says "r11l's decoy targets", so
# the word "decoy" appears inside the look-alike lever's quote. It is still §7.3's
# keyword, not §7.1's — §7.3 is the lever about an ACTION that is declared,
# unhandled and still charged, and r11l's targets are the §7.1 case of two
# objects that look identical. The pre-E-1 note read `decoy` as a §7.1 synonym
# too; that reading is what made one trait answerable under two keywords.

# Lowercase/punctuation-free matching, needed at import time by the tables
# below (this is why it sits above them rather than with the other helpers).
def _squash(text: str) -> str:
    """Lowercase, punctuation-free form: "Look-Alike splits" -> "lookalikesplits"."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


@dataclass(frozen=True)
class LeverGrounding:
    """One §7 lever: its canon number, its keyword, and its other spellings.

    `number` addresses `canon_docs.load_deception_levers`, which is where the
    lever's signed definition and exhibits live — this record carries no canon
    prose of its own, by design: the text is quoted, never retyped.

    `keyword` is None for exactly one lever, §7.5, which has no catalog word by
    design (see the section header). `aliases` are the other spellings a writer
    or an auditor reaches for, every one of which folds onto `keyword`.
    """

    number: int
    keyword: str | None
    aliases: tuple[str, ...] = ()

    @property
    def spellings(self) -> tuple[str, ...]:
        """Every spelling of this lever, canonical first — empty when keywordless."""
        return () if self.keyword is None else (self.keyword, *self.aliases)


LEVER_GROUNDING: tuple[LeverGrounding, ...] = (
    LeverGrounding(1, "look-alike", ("lookalike", "mimic", "disguise")),
    LeverGrounding(2, "palette overload", ("camouflage",)),
    LeverGrounding(3, "decoy", ()),
    LeverGrounding(4, "lying display", ("false tell", "fake tell")),
    LeverGrounding(5, None, ()),  # §7.5 — uncatalogued on purpose
    LeverGrounding(6, "retrospective punishment", ()),
)
# The keywords a lever is REPORTED under, in the canon's own order: one per
# lever, five of the six (§7.5 has none). Every pipeline surface that names "the
# catalog" names this tuple, and `LEVER_SPELLINGS` below is what MATCHES.
DECEPTION_CATALOG: tuple[str, ...] = tuple(
    lever.keyword for lever in LEVER_GROUNDING if lever.keyword is not None
)
# spelling -> the lever's keyword, for every spelling of every lever. The
# canonical keywords map to themselves, so this is the whole matchable surface.
LEVER_SPELLINGS: dict[str, str] = {
    spelling: lever.keyword
    for lever in LEVER_GROUNDING
    for spelling in lever.spellings
    if lever.keyword is not None
}
# …and the same map keyed by squashed spelling, which is how both sides fold a
# reported word back onto its lever (`s3_verify._lever_aliases` is built from it).
LEVER_FOLD: dict[str, str] = {
    _squash(spelling): keyword for spelling, keyword in LEVER_SPELLINGS.items()
}


def lever_spellings(keyword: str) -> tuple[str, ...]:
    """Every spelling of ONE lever, canonical first.

    Raises on a word that is not a canonical keyword: callers ask this about a
    lever they already hold, and a typo would silently return "no spellings",
    which reads as "nothing declares this lever".
    """
    for lever in LEVER_GROUNDING:
        if lever.keyword == keyword:
            return lever.spellings
    raise KeyError(f"{keyword!r} is not a catalog keyword ({list(DECEPTION_CATALOG)})")


def canonical_lever(name: str) -> str | None:
    """The lever `name` IS a spelling of, or None.

    EXACT membership modulo case and separators — not a substring search: this
    is the question "is this word one of the catalog's own spellings?", which
    `s3_verify._validate_uncorroborated` asks of a recorded lever name and which
    historic reports answer with historic spellings ("camouflage", "false tell").
    `detect_levers` is the substring/inflection reader; this is the registry.
    """
    if not isinstance(name, str):
        raise TypeError(f"lever name must be a str, got {type(name).__name__}")
    return LEVER_FOLD.get(_squash(name))


def _deception_pattern(keyword: str) -> re.Pattern[str]:
    """Word-ish, separator-tolerant, inflection-tolerant match for a keyword.

    "look-alike" matches look-alike / look alike / lookalike / look-alikes;
    "decoy" matches decoy / decoys / decoyed but never a longer unrelated
    word, because the tail is capped at 4 letters and must end the word.
    """
    parts = [re.escape(part) for part in re.split(r"[-\s]+", keyword) if part]
    if not parts:
        raise ValueError(f"empty deception keyword: {keyword!r}")
    return re.compile(
        r"(?<![a-z0-9])" + r"[-\s]*".join(parts) + r"[a-z]{0,4}(?![a-z])",
        re.IGNORECASE,
    )


# (lever keyword, the spelling that matched, its pattern) — the ONE matching
# table, shared with `s3_verify` so S1 and S2b cannot disagree about what the
# word "camouflage" means. Canon lever order, canonical spelling first.
_DECEPTION_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = tuple(
    (keyword, spelling, _deception_pattern(spelling))
    for spelling, keyword in LEVER_SPELLINGS.items()
)

# The one line this module adds to each quoted lever: the keyword the pipeline
# reports it under, the spellings that fold onto it, and the canon citation.
LEVER_KEYWORD_LINE = "   -> reported as `{keyword}`{aliases}. ({source})"
LEVER_ALIAS_CLAUSE = "; also spelled {aliases}, which fold onto it"
# §7.5's line. The lever is quoted because it is canon and the games do it; it
# has no keyword because a bare "hidden" would kill honest specs (section header
# above), so the prompt says which surface catches it instead of leaving a
# reader to guess that the omission is deliberate.
LEVER_KEYWORDLESS_LINE = (
    "   -> NO catalog keyword, deliberately: this lever is declared through the `info.*` "
    "terms it is built from and is caught by the both-direction term diff, never by a "
    "deception keyword. ({source})"
)


def deception_lever_block(cfg: Mapping) -> str:
    """The six signed §7 levers, VERBATIM, each tagged with its catalog keyword.

    ONE renderer, THREE prompts (contract E-1): the spec writer's
    `deception_section`, the implementer's `s2_implement._deception_section` and
    the blind auditor's `s3_verify._deception_section` all quote exactly this
    text, so "declared" and "detected" are two readings of one definition rather
    than of two — the `canon_docs.load_term_definitions` precedent, one
    vocabulary over. Nothing here is written by this module: the lever text comes
    from the canon loader and the keyword line from `LEVER_GROUNDING`.

    Measured reason it exists: five audit rounds of one game used four different
    names for one trait, and eight rounds of another used six, because every
    prompt handed out bare keywords with no definitions. The definition is the
    lever; the keyword is the shorthand.
    """
    levers = canon_docs.load_deception_levers(cfg)
    rows: list[str] = []
    for lever in LEVER_GROUNDING:
        entry = levers[lever.number]
        if lever.keyword is None:
            tag = LEVER_KEYWORDLESS_LINE.format(source=entry.source)
        else:
            aliases = (
                ""
                if not lever.aliases
                else LEVER_ALIAS_CLAUSE.format(
                    aliases=", ".join(f"`{alias}`" for alias in lever.aliases)
                )
            )
            tag = LEVER_KEYWORD_LINE.format(
                keyword=lever.keyword, aliases=aliases, source=entry.source
            )
        rows.append(f"{entry.text}\n{tag}")
    return "\n\n".join(rows)

# A NEGATED mention is not a referenced deception (adjudicated 2026-09-21
# after the first live kill: a spec was killed for the sentence "the discard
# branch is load-bearing, not a decoy" — the writer ASSERTING compliance
# with the anti-fake-depth doctrine). The rule targets USED-but-undeclared
# levers; adversarial smuggling past a dumb scanner is S3's business (the
# declared-vs-detected diff, §9 gate 3).
_NEGATION_RE = re.compile(
    r"(?:\bnot\b|\bno\b|\bnever\b|\bwithout\b|\bisn'?t\b|\baren'?t\b|rather than)"
    r"(?:\s+(?:a|an|the|any|as|some|merely|just|being))*\s*$",
    re.IGNORECASE,
)


def _negated(text: str, start: int) -> bool:
    """True when the 40 chars before `start` end in an explicit negator."""
    return bool(_NEGATION_RE.search(text[max(0, start - 40):start]))

# Consistency of the tables themselves — wrong here means every lint is wrong.
assert set(WITNESS_MAP) == set(OBJECTIVE_FAMILIES), "WITNESS_MAP must cover every family"
assert all(k == k.lower() for k in LEVER_SPELLINGS), "catalog spellings are lowercase"
assert len(LEVER_GROUNDING) == len(canon_docs.LEVER_HEAD_KEYWORDS), (
    "LEVER_GROUNDING must ground every signed §7 lever — the loader is total over them"
)
assert {lever.number for lever in LEVER_GROUNDING} == set(canon_docs.LEVER_HEAD_KEYWORDS), (
    "LEVER_GROUNDING numbers must be the canon's own lever numbers"
)
assert all(
    LEVER_FOLD[_squash(spelling)] == keyword for spelling, keyword in LEVER_SPELLINGS.items()
), "two levers share a squashed spelling — the fold would be ambiguous"

# --- writer prompt text -----------------------------------------------------
OVERRIDE_HEADER = "## Overrides and additional contract (these take precedence over anything above)"
SEED_TERMS_LINE = "The spec's `terms` MUST include every seed term above."
ACTION_MAP_HEADER = "### Action mapping (arcengine `GameAction`, enums.py:53-59)"
ACTION_MAP_LINE = (
    "UP=ACTION1, DOWN=ACTION2, LEFT=ACTION3, RIGHT=ACTION4, SPACE=ACTION5, click=ACTION6, "
    "ACTION7=undo (declare only actions the game uses; the rest are `absent`)."
)
LEVEL_COUNT_LINE = "Choose 6-10 levels (ignore any fixed level-count instruction above)."
# LEAD-AUTHORED (C-4 round, the operator's b003r2 review: the accepted game was "too
# easy and all the levels were essentially the same"). Rendered beside the
# level-count line in the writer prompt AND quoted verbatim into the S2 payload
# (prompt-sync discipline: one string, both consumers) — v1 is guidance only,
# measured at the next batch's review before any lint rule is considered.
LEVEL_VARIETY_LINE = (
    "Every level after the first must name what is NEW about its challenge — a new "
    "constraint, a new composition of the declared mechanics, or a new layout class — "
    "never only a bigger board or a longer solution. Two levels that differ only in "
    "size are one level twice."
)
# §7 is a SPEC obligation, not only an implementer one: S2 builds layouts from
# the seed, but it builds what the spec asked for. The B5 pilot spec scoped
# `layout.seed` to "cosmetic placement jitter" in its prose and would have
# produced a game S6 refuses, so the prompt names that failure mode outright.
LAYOUT_SEED_HEADER = "### §7 `layout.seed` — STRUCTURAL variation is REQUIRED (spec-v0.3 §7, D13)"
LAYOUT_SEED_LINE = (
    "`layout.seed` is the §7 seeding mechanism (spec-v0.3 §7, D13), not decoration: the "
    "implementer builds every level's layout as a FUNCTION of that seed, so the `layout:` "
    "block — and every sentence of prose that touches it — must demand STRUCTURAL variation "
    "under the seed. Walls, object placement and the distances between things all move with "
    "it, while the spec itself (terms, knobs, curriculum, win condition) holds. NEVER scope "
    "`layout.seed` to cosmetics: a spec whose prose says the seed 'only seeds cosmetic "
    "jitter' fails §7 — Tufa's own generator kept exactly this promise-unkept and shipped "
    "zero structural variants. In the level sketches and `solver_notes`, say what the seed "
    "varies and what stays invariant, and make the invariants the puzzle rather than the "
    "coordinates — the solver must win at ANY seed, so never pin a fixed route or a fixed "
    "coordinate as the solution."
)
BUDGET_LINE = (
    "Never author numeric action budgets, move limits, or timer values — the pipeline computes "
    "budgets from the solver later. `budget.counts` is a one-line description of WHAT is "
    "counted, `budget.enforced` is always true."
)
# Every spelling the sketch scanner matches, grouped by the LEVER it folds onto.
# Generated from `LEVER_SPELLINGS`, never retyped (contract E-1: the hand-typed
# version of this list had already drifted a keyword short of the catalog).
DECEPTION_SPELLING_GROUPS = "; ".join(
    " / ".join(lever.spellings) for lever in LEVER_GROUNDING if lever.keyword is not None
)
DECEPTION_WORDS_LINE = (
    f"Use deception-catalog words ({DECEPTION_SPELLING_GROUPS}) in level sketches ONLY when "
    f"that lever is declared in knobs.deceptions. The spellings inside one group are ONE "
    f"lever under several names, so declaring any of them declares all of them. Even negated "
    f"mentions confuse review — prefer neutral words like 'ornamental' or 'inert' when "
    f"denying fake depth."
)
WITNESS_HEADER = "### §3b objective witness map (family <- witnessing term(s))"
WITNESS_LINE = (
    "the declared primary (and secondary if any) must be witnessed by a term present in `terms`."
)
CROSSWALK_HEADER = "Common mechanic names -> our closed vocabulary:"
SCHEMA_HEADER = "### Required output schema (spec-v0.3 §11 — the linter checks exactly this)"
# The §11 line `neg2_readers: [{sprite-class: mask}]` is a TEMPLATE, and it has
# now been read twice as a literal two-key mapping — each reading a lint kill
# ("must be a single-key mapping {sprite-class: mask}"). The schema is canon and
# is embedded verbatim, so the disambiguation lives here, right after it.
NEG2_NOTATION_HEADER = "### Reading the schema above: `{key: value}` templates, not literal keys"
NEG2_NOTATION_NOTE = "\n".join([
    NEG2_NOTATION_HEADER,
    "",
    (
        "Each `neg2_readers` entry is a single-key mapping: the KEY is the sprite class name "
        "itself, the VALUE is that class's mask description."
    ),
    "",
    'CORRECT: `neg2_readers: [{conveyor: "belt cells hide their tokens under fog"}]`',
    (
        'LINT KILL: `neg2_readers: [{sprite-class: conveyor, mask: "…"}]` — two keys, and the '
        "literal words `sprite-class` and `mask` are not field names."
    ),
    "",
    (
        "Throughout the schema above, a lowercase name in KEY position is a meta-variable to "
        "substitute with your game's own name — never a key to copy through literally."
    ),
])
# §7's escalation grammar is a SPEC obligation, and `_curriculum_rule` counts
# three separate things about it. The R2 lint kill was the third: a spec whose
# levels never reuse a mechanic. The rule is canon and is not going to bend, so
# the note states exactly what it counts — no more, no less.
CURRICULUM_NOTE_HEADER = "### §7 escalation grammar — what the linter counts across levels"
CURRICULUM_NOTE = "\n".join([
    CURRICULUM_NOTE_HEADER,
    "",
    (
        "Every level declares `relation_to_prev`, one of "
        + " | ".join(f"`{relation}`" for relation in RELATIONS)
        + ". The linter reads the whole sequence and kills the spec unless ALL THREE hold:"
    ),
    "",
    (
        "1. AT LEAST ONE level carries `relation_to_prev: reuse`. The kill, in the linter's own "
        "words: \"no level has relation_to_prev 'reuse' — a mechanic is not established until "
        "it is reused in a contrasting context (§7)\". A spec without one is a LINT KILL, "
        "whatever else it gets right."
    ),
    (
        "2. At most 2 consecutive levels carry `relation_to_prev: new`. Level 1 counts toward "
        "that run, so `new, new, new` from the top is already a LINT KILL."
    ),
    "3. Between 6 and 10 levels in total (§7).",
    "",
    (
        f"`{RELATION_INVERT}` is the fourth value and the rarest (3 of the officials' 158 "
        f"non-first levels): a level that FLIPS A STANDING RULE the game has already taught — "
        f"the thing that helped you now hurts you, the gate that opened now closes. It counts "
        f"as neither of the two rules above: `{RELATION_INVERT}` is NOT a `new` level, so it "
        f"breaks a run of `new` rather than extending it, and it is NOT a `reuse` level, so a "
        f"spec whose only non-`new` levels are inversions still dies on rule 1. Inverting a rule "
        f"is not the same as establishing it."
    ),
    "",
    (
        "CORRECT: `new, new, reuse, compose, reuse, new` — level 3 reuses level 2's mechanic in "
        "a contrasting context, and no three `new` levels sit in a row."
    ),
    (
        "LINT KILL: `new, compose, new, compose, new, compose` — every level escalates and "
        "nothing is ever reused, so no mechanic is ever established."
    ),
])
# --- the rest of the lint surface (R2 coherence pass) -----------------------
# Three writer sessions died to three DIFFERENT kill-rule families (schema's
# neg2 shape, curriculum, contradiction), each at ~$1-2. Discovering the rule
# set one corpse at a time is the wrong price, so the remaining six families in
# KILL_RULES get the same treatment the first two got: a compact note stating
# what the rule FUNCTION enforces, grounded in its code and validated against
# it. Enum lists interpolate from the module constants so a note cannot drift
# from the rule it documents. `schema` and `curriculum` keep their standalone
# notes (NEG2_NOTATION_NOTE covers only the neg2 entry shape, so `schema` gets
# a second note here for the cross-field checks the §11 block cannot show).


def _note(header: str, body: list[str]) -> str:
    """One lint-surface note: the `###` header, a blank line, then the body."""
    return "\n".join([header, "", *body])


SCHEMA_NOTE_HEADER = "### Schema kills the §11 block above cannot show (`schema` rule)"
SCHEMA_NOTE = _note(SCHEMA_NOTE_HEADER, [
    (
        f"All {len(GAME_FIELDS)} `game.*` fields are mandatory (one kill each) and their types "
        "and enums are exactly as written above; an EXTRA `game.*` key is only a "
        "WARN. Optional VALUES, precisely: `objective.secondary`, "
        "`palette.danger` and `budget.lives` may be null or omitted; nothing else may. Four "
        "checks the schema block cannot show:"
    ),
    "",
    (
        "1. `idea_ref` must equal the stage-0 idea id printed at the top of this prompt, "
        "character for character."
    ),
    (
        f"2. `actions` carries EXACTLY {len(ACTION_KEYS) + 1} keys — {ACTION_KEYS[0]}..."
        f"{ACTION_KEYS[-1]} plus `decoys`. A missing key is a kill AND an unknown key is a kill. "
        f"Each action is {' or '.join(repr(s) for s in ACTION_STATES)}. Every name listed in "
        "`actions.decoys` must be an ACTION key whose own value is 'declared' — a decoy that is "
        "'absent' is a kill (§7.3: a decoy is declared, unhandled, and still charged)."
    ),
    (
        f"3. `budget.enforced` must be literally `true` (§2 gate 3) and `layers` literally "
        f"{LAYERS_VALUE!r} (§2.6). Neither is a knob."
    ),
    (
        f"4. Ints are strict — a bool is NOT an int here, so `layout.seed: true` is a kill. "
        f"`layout.grid` is `[w, h]`, both {GRID_MIN}-{GRID_MAX}. `palette.you`, `palette.goal` "
        f"and every entry of `palette.reserved` are ints {PALETTE_MIN}-{PALETTE_MAX}, and "
        "`palette.reserved` must be NON-EMPTY."
    ),
])
UNKNOWN_TERMS_NOTE_HEADER = "### `terms` is a closed set, twice over (`unknown-terms` rule)"
UNKNOWN_TERMS_NOTE = _note(UNKNOWN_TERMS_NOTE_HEADER, [
    (
        "Every string in `game.terms` must be a §3 vocabulary term — one kill per offender, and "
        "an invented or near-miss spelling (`hazard.spike`, `goal.reach_goal`) is the usual "
        "cause. You MAY carry vocabulary terms beyond the seed terms; you may not invent one."
    ),
    (
        "Every string in every `levels[i].terms_introduced` must already appear in `game.terms`. "
        "The test is membership in `game.terms`, not in the vocabulary, and it ignores level "
        "order — but a term used by a level and never listed in `game.terms` is a kill."
    ),
])
OBJECTIVE_UNWITNESSED_NOTE_HEADER = (
    "### Both objective slots are strict (`objective-unwitnessed` rule)"
)
OBJECTIVE_UNWITNESSED_NOTE = _note(OBJECTIVE_UNWITNESSED_NOTE_HEADER, [
    (
        "The witness map above is enforced on `objective.primary` AND, when you declare one, on "
        "`objective.secondary`: each declared slot needs at least one of ITS family's witness "
        "terms present in `game.terms`, or the spec is killed (one kill per slot). Generated "
        "games get no qualifier exemption."
    ),
    (
        "`objective.secondary: null` is always safe. A second family whose witness term never "
        "reaches `terms` is a kill — so either add that term or leave the slot null."
    ),
])
MISSING_KNOBS_NOTE_HEADER = "### All four §5 knobs, always (`missing-knobs` rule)"
MISSING_KNOBS_NOTE = _note(MISSING_KNOBS_NOTE_HEADER, [
    (
        f"`knobs` must carry all four keys — {', '.join('`' + k + '`' for k in KNOB_FIELDS)}. A "
        "missing key is a kill even when its value would have been the neutral one."
    ),
    f"`refusal`: {' | '.join(REFUSALS)}",
    f"`goal_legible`: {' | '.join(GOAL_LEGIBLE)}",
    f"`danger_tell`: {' | '.join(DANGER_TELLS)}   (see the contradiction rule below)",
    (
        "`deceptions` has no enum, but it must be a LIST OF STRINGS: `[]` means none declared and "
        "is perfectly legal; `null` is a kill."
    ),
])
PALETTE_COLLISION_NOTE_HEADER = "### Palette indices (`palette-collision` rule)"
PALETTE_COLLISION_NOTE = _note(PALETTE_COLLISION_NOTE_HEADER, [
    (
        "Two checks over `palette`. (1) None of `you` / `goal` / `danger` may hold an index that "
        "also appears in `palette.reserved` — one kill per offender (§2.8). (2) No two of those "
        "three may hold the SAME index."
    ),
    (
        f"Check 2 has one exemption and it is literal: the kill becomes a warn only when some "
        f"`knobs.deceptions` entry contains the substring {OVERLOAD_KEYWORD!r} "
        f"(case-insensitive). Spell it `palette overload` and the same entry also declares the "
        f"`palette overload` lever for the sketch scanner below. If you do not mean to overload "
        f"an index, give the three roles three distinct indices, all off the reserved set."
    ),
])
UNDECLARED_DECEPTION_NOTE_HEADER = (
    "### Deception words in sketches are scanned (`undeclared-deception` rule)"
)
UNDECLARED_DECEPTION_NOTE = _note(UNDECLARED_DECEPTION_NOTE_HEADER, [
    (
        "A scanner reads every `levels[i].sketch` — only the sketch, not `solver_notes` and not "
        f"the prose spec — for the {len(DECEPTION_CATALOG)} catalog levers: "
        f"{', '.join(DECEPTION_CATALOG)}. A lever's other spellings match too and FOLD onto it "
        f"(the section below quotes all six). Matching ignores case, tolerates a hyphen or "
        f"space inside the keyword, and tolerates inflections (`decoys`, `disguised`)."
    ),
    (
        "A matched lever that no `knobs.deceptions` entry declares is a kill, one per lever per "
        "level. Declaration is substring containment after case and punctuation are stripped, "
        'and ANY spelling does it: `["mimic"]` declares `look-alike`.'
    ),
    (
        "A mention is skipped ONLY when an explicit negator (not / no / never / without / isn't / "
        "aren't / rather than) sits in the 40 characters immediately before it. Do not lean on "
        "that escape: write `ornamental` or `inert` rather than `not a decoy`."
    ),
])
# The R2 kill was C1, from an idea whose mix said `hazardless: false` while its
# seed terms held no hazard. Every branch is spelled out because the rule reads
# THREE blocks at once (knobs, objective, terms) and no single block shows it.
CONTRADICTION_NOTE_HEADER = (
    "### Knobs must not contradict `terms` (`contradiction` rule — three branches)"
)
CONTRADICTION_NOTE = _note(CONTRADICTION_NOTE_HEADER, [
    (
        "This rule cross-reads `knobs`, `objective` and `terms` together. All three branches are "
        "live and each kills on its own:"
    ),
    "",
    (
        f"C1 — A TELL NEEDS A DANGER. If `knobs.danger_tell` is anything other than `none`, "
        f"`game.terms` MUST hold at least one term beginning "
        f"{' or '.join(p + '*' for p in HAZARD_PREFIXES)}. The whole §3 vocabulary offers exactly "
        f"four: `hazard.crush`, `hazard.static`, `hazard.timed`, `loss.deadlock`. The kill reads "
        f"\"knobs.danger_tell is 'unique-hue' but game.terms holds no hazard.* or loss.* term — "
        f"no danger to tell\". Two legal shapes, pick one on purpose: a game WITH "
        f"danger adds one of those four terms to `terms` (extra vocabulary terms are allowed) "
        f"and keeps its tell; a game with NO danger sets `danger_tell: none`. A `hazardless: "
        f"false` facet in the idea above does NOT put a hazard term into `terms` for you."
    ),
    "",
    (
        "C2 — A VISIBLE REFUSAL CANNOT BE SILENT. When `knobs.refusal` is `visible`, no "
        "`knobs.deceptions` entry may contain BOTH the words `silent` and `decoy` (lowercased "
        "substring test; one kill per offending entry). Either the refusal is `silent-charged`, "
        "or that entry is worded without `silent`."
    ),
    "",
    (
        f"C3 — SURVIVE NEEDS A CLOCK THAT IS NOT THE BUDGET. If `survive` is the primary OR the "
        f"secondary objective and `budget.cap` is in `terms`, then `terms` must ALSO hold at "
        f"least one of {', '.join('`' + t + '`' for t in SURVIVE_CLOCK_TERMS)} — otherwise "
        f"surviving IS exhausting the budget and one counter is doing both jobs (§6). Add a "
        f"clock term, or keep `budget.cap` out of `terms`."
    ),
])
# The single block build_writer_prompt inserts; neg2/curriculum stay standalone.
LINT_SURFACE_NOTE_PARTS: tuple[str, ...] = (
    SCHEMA_NOTE,
    UNKNOWN_TERMS_NOTE,
    OBJECTIVE_UNWITNESSED_NOTE,
    MISSING_KNOBS_NOTE,
    PALETTE_COLLISION_NOTE,
    UNDECLARED_DECEPTION_NOTE,
    CONTRADICTION_NOTE,
)
LINT_SURFACE_NOTES: str = "\n\n".join(LINT_SURFACE_NOTE_PARTS)

# --- the render declaration, in the prompt (contract V-B) -------------------
# STANDING documentation, deliberately NOT knob-gated: the writer prompt gains
# these paragraphs for every config (the V-A precedent), while the lint REPORT
# of a spec that declares neither field — under a config that has not armed
# `lint.require_render` — stays byte-for-byte what it was. That asymmetry is
# the whole design: the writer learns a new thing it MAY declare, and nothing
# already shipped becomes retroactively wrong.
#
# These constants are NOT named `*_NOTE`: that suffix is a discovered family in
# the R2 hotfix-4 suite, where every `*_NOTE` must appear verbatim inside
# LINT_SURFACE_NOTES, and this section renders too late to live in a module
# constant (its corpus line interpolates from `gen.visual_canon`).
RENDER_SECTION_HEADER = "### The render scale and the background (`render`, `palette.background`)"
RENDER_SECTION_SCALE = (
    "`game.render` is OPTIONAL and it is where the spec DECLARES its one render scale: "
    "`render: {{cell_px: N}}`, N an int {cell_min}-{cell_max} — the pixel size of ONE logical "
    "cell, held for EVERY level (the implementer is graded on one render scale; this is where "
    "it is stated rather than guessed). `cell_px` times each half of `layout.grid` must fit the "
    "{canvas}x{canvas} camera: `cell_px: 4` with `grid: [16, 16]` is exactly {canvas}x{canvas} "
    "and passes, `cell_px: 5` with `grid: [13, 13]` is 65x65 and is a `contradiction` KILL. A "
    "`render` block that is not a mapping, carries no `cell_px`, or carries a `cell_px` outside "
    "{cell_min}-{cell_max} is a `schema` KILL; an extra key inside it is only a warn. Some "
    "batches REQUIRE the declaration (`lint.require_render`), and there a spec without one is a "
    "`schema` KILL — so declare it."
)
RENDER_SECTION_BACKGROUND = (
    "`palette.background` is OPTIONAL in the same way: the int {pal_min}-{pal_max} the board is "
    "painted with. Canon's default is {default} (black — affordance §9, \"background/outline "
    "default\"), so leaving the key out means UNSTATED, never wrong; `background: null` IS a "
    "`schema` KILL, because a key written down is a declaration and is held to one. A declared "
    "background may not equal `palette.you`, `palette.goal` or `palette.danger` — a role drawn "
    "in the background's own colour is invisible, so that is a `palette-collision` KILL, "
    "downgraded to the same warn as the palette note above by the same declared "
    "`palette {overload}` lever. It does NOT have to stay off `palette.reserved`: reserving the "
    "background index is ordinary practice, not a collision."
)
RENDER_SECTION_CORPUS = (
    "Corpus: each of the {games} official games renders at ONE scale from the menu {menu} px per "
    "cell, and a level-1 board carries {l1_min}-{l1_max} distinct colors (median {l1_median}) — "
    "the background is one of them. A `cell_px` off that menu is a WARN, never a kill: the menu "
    "is what {games} games happened to measure, not a law of the camera."
)


def render_section() -> str:
    """The standing `render` / `palette.background` documentation, rendered.

    A FUNCTION rather than a constant because of the corpus line: the menu and
    the level-1 colour band interpolate from `gen.visual_canon`, which can only
    be imported lazily (see `_visual_canon` — it imports `HAZARD_PREFIXES` from
    this module, so a top-level import here is a cycle). Every number in the
    paragraphs below comes from a module constant the linter itself reads.
    """
    canon = _visual_canon()
    menu = _tile_scale_menu()
    l1_min, l1_median, l1_max = canon.OFFICIAL_VISUAL_CONSTANTS["l1_colors"]
    return _note(
        RENDER_SECTION_HEADER,
        [
            RENDER_SECTION_SCALE.format(
                cell_min=CELL_PX_MIN, cell_max=CELL_PX_MAX, canvas=CANVAS_PX
            ),
            "",
            RENDER_SECTION_BACKGROUND.format(
                pal_min=PALETTE_MIN,
                pal_max=PALETTE_MAX,
                default=BACKGROUND_DEFAULT,
                overload=OVERLOAD_KEYWORD,
            ),
            "",
            RENDER_SECTION_CORPUS.format(
                games=canon.OFFICIAL_GAMES,
                menu="{" + ", ".join(str(scale) for scale in menu) + "}",
                l1_min=l1_min,
                l1_median=l1_median,
                l1_max=l1_max,
            ),
            "",
            # W2-D ruling (lead; moved here from the palette note — this
            # section sits OUTSIDE the hotfix-4 note budget, the NEG2/
            # CURRICULUM precedent): the spec writer must know the field
            # exists, or every legitimate tiny-token idea dies at the armed
            # role-footprint gate with no spec-side recourse.
            (
                "If a role in `you`/`goal`/`danger` is DELIBERATELY drawn smaller than one "
                f"logical cell — a single-pixel marker the mechanic is about — declare it in "
                f"`palette.{TINY_TOKEN_FIELD}: [<role>, ...]`. The visual gate holds every "
                "declared role to a full-cell footprint unless this field names it; an "
                "undeclared tiny mark is measured as a defect."
            ),
        ],
    )

# --- the chrome + transient-refusal declarations, in the prompt (contract B1)
# STANDING documentation on `render_section`'s exact terms (contract V-B): the
# writer prompt gains these paragraphs for every config, while the lint REPORT
# of a spec that declares neither field stays byte-for-byte what it was under a
# config that has armed nothing. The writer learns two fields it MAY declare and
# nothing already shipped becomes retroactively wrong.
#
# A SECOND SECTION rather than three more paragraphs inside `render_section`:
# that function documents the two fields that say how the board is DRAWN (the
# scale, the field colour), and these two say what is drawn ON it that is not
# gameplay, and what a refusal promises. Its own function for its own subject —
# and, like it, deliberately NOT named `*_NOTE`: that suffix is a discovered
# family in the R2 hotfix-4 suite where every member must appear verbatim inside
# `LINT_SURFACE_NOTES` and count against the note budget, which a section
# interpolating from `gen.visual_canon` cannot do.
CHROME_SECTION_HEADER = (
    "### Authored chrome and the transient refusal (`chrome`, `knobs.refusal_transient`)"
)
CHROME_SECTION_CHROME = (
    "`game.{field}` is OPTIONAL and it is where the spec DECLARES its inert framing "
    "structure: a list of `{{kind: K, where: W}}` entries, K one of {kinds} and W one of "
    "{wheres}. Chrome is drawn once, is never interactive and never load-bearing; it marks "
    "where the world ENDS, which is why an official board reads as a place and an unframed "
    "one reads as a mechanism adrift. A `{field}` that is not a NON-EMPTY list, an entry that "
    "is not a mapping, a missing or unknown `kind`/`where`, or any third key inside an entry "
    "is a `schema` KILL — the key is optional, but a declaration nothing downstream can read "
    "is worse than silence. Omit it entirely when the game draws no chrome."
)
CHROME_SECTION_CORPUS = (
    "Corpus: the {games} officials carry {decor_rows} decor rows and they are almost entirely "
    "chrome — letterbox bands, panel slabs, divider rails, bezel frames. The seven games this "
    "pipeline has shipped carry {ours_decor} authored decor objects between them, their "
    "`occupied_extent` (cells that are not the board's modal index) is {ratio}x the "
    "officials', and {below_n} of the seven sit BELOW the officials' whole observed per-game "
    "band of {band_low}-{band_high}. The gate's `chrome-extent` check is PAIRED: it flags a "
    "game only when it is below that band AND declares no chrome, so neither padding the "
    "board nor declaring chrome you did not draw clears it on its own."
)
CHROME_SECTION_REFUSAL = (
    "`game.knobs.{transient}` is OPTIONAL and is a BOOL. Declaring `refusal: {visible}` "
    "PROMISES a refusal signal that is still visible on a SETTLED frame (§6's bar is a signal "
    "\"persisting >=1 settled frame\"); this pipeline captures settled frames only, so a flash "
    "drawn and cleared inside one action is invisible to it and to any frame-differencing "
    "agent. Write `{transient}: true` when the signal is deliberately momentary and is not "
    "something the player must learn from. A value that is not a bool is a `missing-knobs` "
    "KILL; omitting the key leaves the promise standing. Separately and absolutely: §6 "
    "forbids a refusal that both signals AND charges — charge silently, or signal freely."
)


def chrome_section() -> str:
    """The standing `chrome` / `knobs.refusal_transient` documentation, rendered.

    A FUNCTION for `render_section`'s reason: the corpus paragraph interpolates
    from `gen.visual_canon`, which can only be imported lazily (see
    `_visual_canon` — it imports from this module, so a top-level import here is
    a cycle). Every number below comes from `visual_canon.OFFICIAL_CHROME`, the
    same constant the gate's band is derived from, so the writer is told the
    band it will be measured against.
    """
    chrome = _visual_canon().OFFICIAL_CHROME
    return _note(
        CHROME_SECTION_HEADER,
        [
            CHROME_SECTION_CHROME.format(
                field=CHROME_FIELD,
                kinds="{" + ", ".join(CHROME_KINDS) + "}",
                wheres="{" + ", ".join(CHROME_WHERE) + "}",
            ),
            "",
            CHROME_SECTION_CORPUS.format(
                games=chrome["games"],
                decor_rows=chrome["official_decor_rows"],
                ours_decor=chrome["ours_authored_decor_objects"],
                ratio=chrome["ours_ratio"],
                below_n=len(chrome["ours_below_band"]),
                band_low=chrome["band_low"],
                band_high=chrome["band_high"],
            ),
            "",
            CHROME_SECTION_REFUSAL.format(
                transient=REFUSAL_TRANSIENT_FIELD, visible=REFUSAL_VISIBLE
            ),
        ],
    )


# --- the deception levers, in the prompt (contract E-1) ---------------------
# The `undeclared-deception` note inside LINT_SURFACE_NOTES states the MECHANICS
# (which words the scanner matches, what declaring one means); this section
# states what each lever IS, quoted from the canon. A function and deliberately
# NOT named `*_NOTE` for the same two reasons `render_section` is: that suffix is
# a discovered family in the R2 hotfix-4 suite where every member must appear
# verbatim inside `LINT_SURFACE_NOTES`, and this text interpolates from a canon
# loader, so it cannot be a module constant.
DECEPTION_SECTION_HEADER = "### What each deception lever IS (`affordance-language.md` §7)"
DECEPTION_SECTION_LEAD = (
    "The {count} catalog keywords above are SHORTHAND for these {levers} signed levers, every "
    "one measured on the official corpus. Read the lever before you reach for a word: a trait "
    "named four different ways across four specs is the same lever four times, and the keyword "
    "is only how the pipeline writes it down. Pick the lever your game actually pulls, declare "
    "it in `knobs.deceptions` with the keyword leading the entry, and describe it in your own "
    "words after the colon."
)


def deception_section(cfg: Mapping) -> str:
    """The six signed levers quoted into the writer prompt (contract E-1)."""
    return _note(
        DECEPTION_SECTION_HEADER,
        [
            DECEPTION_SECTION_LEAD.format(
                count=len(DECEPTION_CATALOG), levers=len(LEVER_GROUNDING)
            ),
            "",
            deception_lever_block(cfg),
        ],
    )


# --- the tier contract (contract T-B) ---------------------------------------
# `gen/tiers.py` is the signed tier table (difficulty-model §3.3). S0 draws an
# idea AT a tier; the constants and rules below hold the SPEC there. The
# measured problem they exist for: ideas seed 2-4 terms and the shipped specs
# carry 10-14 against the officials' 4-10 (median 8) — the inflation happens
# inside the writer session, and until now nothing counted `len(game.terms)`.
#
# PROMPT SYNC BY CONSTRUCTION (the b002 pattern). The recovery path for a lint
# kill is a FRESH S0 re-sample, so the next writer never reads the kill report:
# a rule that can kill has to be stated verbatim in the prompt that gets judged
# by it. TIER_TERMS_KILL_SENTENCE is therefore interpolated by BOTH sides —
# `_tier_prompt_section` renders it, and the `tier-terms` finding in
# `_tier_rules` is that same formatted sentence plus the count that broke it.
TIER_TERMS_KILL_SENTENCE = (
    "TIER TERM BUDGET (tier {tier}): `game.terms` may hold at most {budget} entries — the "
    "officials run 4-10 terms per game (median 8), and this ceiling is the signed tier "
    "table's. The linter kills a spec that exceeds it; prefer reusing a declared term in a "
    "new context over adding one."
)
TIER_SECTION_HEADER = "### Tier contract (tier {tier} — {label})"
# LEAD FIX (T-B review): the consequence clause interpolates from the action
# knob — the frozen contract hardcoded "a recorded warn, not a kill", which
# lies under `knob_defaults_action: kill`. A prompt may never misstate what
# the linter will do (the whole prompt-sync doctrine).
TIER_KNOB_DEFAULTS_LINE = (
    "Tier knob defaults — refusal: {refusal}; goal_legible: {goal_legible}; danger_tell: "
    "{danger_tell}; declared deception levers: at most {levers}. Departing from a default is "
    "{consequence}."
)
# The operator's 2026-09-29 legibility ruling, prompt-synced: when a batch caps
# goal_legible below the tier's own max, the writer is told IN the prompt —
# a rule that can end a session is quoted to it. The structure/goal split is
# the ruling's own reasoning (the echo game hid the GOAL behind one
# destructible flicker; hidden STRUCTURE was never the complaint).
GOAL_LEGIBLE_CAP_LINE = (
    "THIS BATCH CAPS goal_legible AT {cap!r} (tiers.goal_legible_cap): the goal and its "
    "evidence must be visible at all times. Hidden STRUCTURE (secret walls, concealed "
    "wiring) is welcome; a hidden OBJECTIVE is not — if the spec carries a hidden-info "
    "term, its goal evidence must persist on every settled frame, never a one-time flicker."
)
TIER_KNOB_CONSEQUENCE = {
    "warn": "a recorded warn, not a kill",
    "kill": "a KILL under this batch's config",
}
TIER_INTRO_PACING_LINE = (
    "Levels after the first introduce at most {cap} new term(s) each (`terms_introduced`)."
)
# --- the escalation axis (contract A2 / R-11) -------------------------------
# The tier section's last part, and the prompt half of the R-11 change. Two
# lines, both prompt-synced by construction:
#
#   1. `tiers.complexity_tier_line(tier)` — the SAME string `COMPLEXITY_OVERRIDE`
#      closes with for that tier. S0's prose prompt states the game's complexity
#      stance to the idea writer; until now S1's spec writer was never told it
#      at all, and S1 is the stage that actually writes `relation_to_prev`.
#   2. `ESCALATION_AXIS_LINE` — the officials' measured relation mix as a TARGET,
#      for t2/t3 only. t1 has no novelty target to state (its whole guidance is
#      compose-first and its `intro_cap` is 1), so it gets line 1 alone: handing
#      an entry-tier writer "new ≈ 45% of levels" would contradict the row above
#      it, and a prompt that argues with itself is the failure T-A was built to
#      avoid.
#
# THE NUMBERS AND THE SOURCE PATH ARE WRITTEN OUT, not interpolated, and the
# import-time assert below is what keeps them honest. This constant is the one
# place a reader — or a reviewer, or the S2b auditor reading a payload — meets
# the corpus claim, and a claim that only exists after `.format` is not a claim
# anyone can check. `{tier}` stays a placeholder because it names the spec being
# written, not the corpus.
ESCALATION_AXIS_TIERS = ("t2", "t3")
ESCALATION_AXIS_LINE = (
    "ESCALATION AXIS (tier {tier}) — the officials' own shape across their 158 non-first "
    "levels (audit/comparative/data/escalation.csv), and this spec's target: `new` ≈ 44.9% "
    "(71 levels), `compose` ≈ 27.2% (43), `reuse` ≈ 25.9% (41), `invert` rare (3). "
    "Plan the `relation_to_prev` sequence against that mix rather than making every level a "
    "composition: about one level in two should teach something genuinely new, and every term "
    "it teaches is listed in that level's `terms_introduced`. The tier term budget is the "
    "ceiling on the whole list, so novelty is spent, not free."
)
# `gen.tiers` reads the mix off `escalation.csv`; this module quotes it. The
# quote is checked against the measurement at import, so the two cannot drift —
# the same guarantee interpolation would give, without hiding the claim.
assert tiers.ESCALATION_SOURCE in ESCALATION_AXIS_LINE, (
    "the axis line must cite the csv it quotes by the path `gen.tiers` names, or the one "
    "written-out citation in this module can drift from the measurement behind it"
)
assert f"{tiers.OFFICIAL_NON_FIRST_LEVELS} non-first" in ESCALATION_AXIS_LINE, (
    "the axis line's denominator must be tiers.OFFICIAL_NON_FIRST_LEVELS"
)
assert all(
    f"{tiers.OFFICIAL_ESCALATION_MIX[relation]}% ({tiers.OFFICIAL_ESCALATION_COUNTS[relation]}"
    in ESCALATION_AXIS_LINE
    for relation in ("new", "compose", "reuse")
), "the axis line's shares and counts must be tiers.OFFICIAL_ESCALATION_* verbatim"
assert f"rare ({tiers.OFFICIAL_ESCALATION_COUNTS['invert']})" in ESCALATION_AXIS_LINE, (
    "the axis line's `invert` count must be tiers.OFFICIAL_ESCALATION_COUNTS['invert']"
)


def escalation_axis_line(tier: str) -> str | None:
    """The axis target for one tier, or None where no measured target applies."""
    if tier not in ESCALATION_AXIS_TIERS:
        return None
    return ESCALATION_AXIS_LINE.format(tier=tier)
# The four tier rule ids. They are deliberately NOT members of KILL_RULES even
# though all four CAN kill (their action knobs take "kill"): KILL_RULES is the
# §11 closed list, and the b5 suite pins it two ways — an exact tuple equality
# AND `test_every_kill_rule_has_a_fixture`, which demands a fixture that trips
# each member through `lint_spec(spec, vocab)`. That call carries no tier
# policy, so a tier rule cannot fire in it BY CONSTRUCTION and no such fixture
# can exist. A tier finding is a POLICY finding: it exists only when a config
# armed it, which is exactly what keeps the §11 list closed.
TIER_RULES = ("tier-terms", "tier-knob-mismatch", "tier-deceptions", "tier-intro-pacing")

# `gen/tiers.py` MIRRORS the three §11 knob enums as ordinal ladders (it may
# not import this module — S1 imports it). A ladder that lost a value would
# silently stop ranking it, so the mirror is asserted at import, beside the
# module's other table-consistency asserts.
assert set(tiers.REFUSAL_ORDINAL) == set(REFUSALS), "tiers.REFUSAL_ORDINAL must mirror REFUSALS"
assert set(tiers.GOAL_LEGIBLE_ORDINAL) == set(GOAL_LEGIBLE), (
    "tiers.GOAL_LEGIBLE_ORDINAL must mirror GOAL_LEGIBLE"
)
assert set(tiers.DANGER_TELL_ORDINAL) == set(DANGER_TELLS), (
    "tiers.DANGER_TELL_ORDINAL must mirror DANGER_TELLS"
)

# --- the fidelity rules (contracts W1-B / R-16, W2-D / R-25) ----------------
# Two channels the §11 surface never guarded, both measured by the comparative
# audit (findings A5; J-4 §6, §7) — and, further down, a third that joined the
# same registry on the same terms:
#
#   * the idea's `mix_class` is not a contract the spec keeps —
#     convoy-in-the-fog drew `hazardless: true` ("There are no hazards anywhere
#     on the board") and shipped `loss.deadlock` with `danger_tell: absence`.
#     `hazardless` was read in exactly one place, to print a facet line into
#     the writer prompt; contradiction rule C1 checks that a TELL has a danger
#     and never that a hazardless idea stayed hazardless.
#   * §11 enforces `terms_introduced ⊆ game.terms` and never the reverse, so a
#     declared term no level introduces is inert vocabulary that still spends
#     the tier budget, the payload and the verifier's attention: 12 such terms
#     across 3 games, 12/12 spec-added (convoy 7, core-ward 2,
#     facing-sentinel 3).
#
# They follow the TIER_RULES registry pattern, NOT the closed KILL_RULES set
# (b5 pins that tuple exactly, and `test_every_kill_rule_has_a_fixture` demands
# a fixture that trips each member through a policy-free `lint_spec(spec,
# vocab)` — which a knob-governed rule cannot have by construction). Each rule
# has a stable id and its own `lint.<rule>_action` knob.
#
# THE DEFAULT IS `off` (LEAD CONTRACT CORRECTION, W1-B mid-flight). The frozen
# contract said `warn`, which contradicts its own house-style line — "canon-
# default OFF-or-warn behavior with byte-identical reports when unconfigured" —
# and the repo ENFORCES the byte-identity half: `test_b003_render.py::
# test_shipped_specs_match_their_shipped_lint_report` re-lints every shipped
# spec against its STORED lint-report, so a rule that fires unasked makes seven
# shipped reports retroactively wrong. Repo precedent controls. The audit's
# "ship as warn first" is satisfied by ARMING them in config, which
# `config/template.yaml` does: the next batch runs them at `warn` and measures
# the kill rate before anyone writes `kill`.
#
# A THIRD CHANNEL JOINS THE SAME REGISTRY (contract W2-D / R-25): a spec that
# declares no `game.palette.background`. R-01's `field-index` check reads that
# declaration to ask whether the board's modal index is the one the spec named,
# and six of the seven shipped specs name none — so the strongest visual check
# this pipeline has is comparing the board against a canon default nobody wrote
# down. That is a fidelity gap of exactly the kind this registry exists for.
#
# IT JOINS THE REGISTRY RATHER THAN BECOMING AN UNCONDITIONAL WARN, and the
# reason is the same byte-identity contract stated above, measured: those six
# background-silent specs are the ones `test_b003_render.py::
# test_shipped_specs_match_their_shipped_lint_report` re-lints against their
# STORED reports. An unconditional warn makes six shipped reports retroactively
# wrong the day it lands. At the `off` default it fires for nobody and
# `config/template.yaml` arms it at `warn`, which is where the measurement
# happens — exactly the path the other two rules took.
#
# A FOURTH CHANNEL JOINS IT (contract A2 / R-11): `silent-levels`, the share of
# non-first levels that introduce NO term at all. 72.3% of our non-first levels
# are silent (34/47) against the officials' 183/183 non-blank `new_mechanic`,
# and per game the shares run 0.43 to 1.00 — conduit-watch is 7/7 silent, i.e.
# every mechanic it has is front-loaded into level 1 and the other six levels
# are layout. This rule JOINS THE REGISTRY rather than becoming a fifth private
# mechanism for the reason W2-D states above and R-16 states before it: one
# registry, one action enum, one `lint.<rule>_action` spelling, and the
# byte-identity of the shipped reports preserved by the same `off` default.
#
# IT IS A FLOOR, NOT A BAN, and the floor is the whole design. The officials
# never go silent, but our curricula legitimately reuse — a compose-heavy game
# that re-reads its mechanics in new layouts is the SHAPE R-11 protects, not a
# defect. The default floor 0.5 is calibrated on the shipped corpus and lands
# where a reader would want it: conduit-watch (1.00), convoy-in-the-fog (0.86),
# mosaic (0.83), pump-phase (0.71) and core-ward (0.71) fire, while
# facing-sentinel (0.50, exactly AT the floor) and pump-flow (0.43) do not.
RULE_MIX_HAZARDLESS = "mix-hazardless"
RULE_TERMS_COVERAGE = "terms-introduced-coverage"
RULE_UNSTATED_BACKGROUND = "unstated-background"
RULE_SILENT_LEVELS = "silent-levels"
# `refusal-persistence` (contract B1 / R-08) JOINS the registry rather than
# becoming a fifth private mechanism, for the reason W2-D and R-16 state before
# it: one registry, one action enum, one `lint.<rule>_action` spelling, and the
# byte-identity of the shipped reports preserved by the same `off` default.
#
# It is a PROMISE rule, and that is what makes it a registry rule rather than a
# gate check: it fires on a spec that declares `refusal: visible` and does NOT
# declare `knobs.refusal_transient`, which is not a defect — it is a spec
# stating that its refusal signal survives into a settled frame. Recording the
# promise is the whole job here; B3's check is what measures the frames against
# it. At `warn` (where `config/template.yaml` arms it) every spec we have ever
# shipped fires, because all seven declare `refusal: visible` and none declares
# the exception, which is exactly the measurement the audit asked for.
RULE_REFUSAL_PERSISTENCE = "refusal-persistence"
FIDELITY_RULES = (
    RULE_MIX_HAZARDLESS,
    RULE_TERMS_COVERAGE,
    RULE_UNSTATED_BACKGROUND,
    RULE_SILENT_LEVELS,
    RULE_REFUSAL_PERSISTENCE,
)
FIDELITY_ACTIONS = ("off", "warn", "kill")
FIDELITY_DEFAULT_ACTION = "off"
# `silent-levels` is the first registry rule with a THRESHOLD as well as an
# action, so it gets a second knob. 0.5 is the calibrated default above; the
# rule fires when the silent share EXCEEDS it, so a spec sitting exactly at the
# floor passes — a floor nobody can sit on is a ban with extra steps.
SILENT_LEVELS_FLOOR_KEY = "silent_levels_floor"
SILENT_LEVELS_FLOOR_DEFAULT = 0.5
# rule id -> the `lint:` key that governs it. The `<rule>_action` spelling is
# the `tiers:` block's (`term_budget_action`, `knob_defaults_action`, …), with
# the rule id's hyphens written as underscores, because a config key is not a
# rule id and inventing a second spelling for one of them would be worse.
FIDELITY_ACTION_KEYS: dict[str, str] = {
    RULE_MIX_HAZARDLESS: "mix_hazardless_action",
    RULE_TERMS_COVERAGE: "terms_introduced_coverage_action",
    RULE_UNSTATED_BACKGROUND: "unstated_background_action",
    RULE_SILENT_LEVELS: "silent_levels_action",
    RULE_REFUSAL_PERSISTENCE: "refusal_persistence_action",
}
assert set(FIDELITY_ACTION_KEYS) == set(FIDELITY_RULES), (
    "every fidelity rule needs its `lint.<rule>_action` key, and no key may name a rule that "
    "does not exist — a knob nobody reads is how an inert knob is born"
)
# The exemption warn ids — the `palette-overload-declared` precedent: an
# exempted violation is RECORDED, never silent, so a report says which
# declaration bought it.
MIX_HAZARDLESS_OVERRIDE_WARN = "mix-hazardless-override"

# PROMPT SYNC BY CONSTRUCTION, the TIER_TERMS_KILL_SENTENCE pattern: one
# sentence per rule, interpolated by BOTH sides — `_fidelity_rules` builds each
# finding's detail from it, and `fidelity_section` renders it into the writer
# prompt for any batch that ARMS the rule to kill. (At `off` and at `warn` the
# prompt stays byte-for-byte what it was: nothing the writer is judged on has
# changed, and the measurement the audit asked for runs on unprompted specs.)
MIX_HAZARDLESS_KILL_SENTENCE = (
    "HAZARDLESS IDEA — the idea above drew `mix_class.hazardless: true`, so this game has no "
    "danger and the spec must say so: `game.terms` may declare no {prefixes} term, and "
    "`knobs.danger_tell` must be `none`. A game that needs a hazard after all declares "
    "`game.{override}: \"<one line saying why>\"` — that string is the whole override surface, "
    "and a spec that carries it keeps its hazard and records the departure as a warn."
)
TERMS_COVERAGE_KILL_SENTENCE = (
    "EVERY DECLARED TERM IS INTRODUCED — each entry of `game.terms` must appear in some "
    "`levels[i].terms_introduced` (§11 already requires the containment the other way, and this "
    "is the reverse of it). A declared term that no level introduces is inert vocabulary: it "
    "spends the tier budget and the verifier's attention and no player ever meets it. Introduce "
    "it in the level that teaches it, or drop it from `game.terms`."
)
UNSTATED_BACKGROUND_KILL_SENTENCE = (
    "DECLARE THE FIELD — `game.palette.background` is the int {pal_min}-{pal_max} the board is "
    "painted with, and this spec must name one. Leaving it out is not neutral: the canon "
    "default is {default} (black — affordance §9, \"background/outline default\"), the gate's "
    "`field-index` check reads the DECLARATION to ask whether the board's modal index is the "
    "index the spec named, and a spec that names none is measured against a default nobody "
    "chose. Write the index the field is actually painted in. (`background` may not equal "
    "`palette.you`, `palette.goal` or `palette.danger` — that is a `palette-collision` kill.)"
)
SILENT_LEVELS_KILL_SENTENCE = (
    "EVERY LEVEL TEACHES SOMETHING — at most {floor_pct}% of the levels after level 1 may "
    "leave `terms_introduced` EMPTY. All {official_n} official levels introduce a mechanic; "
    "{ours_pct}% of ours introduce nothing at all, which is a game whose whole vocabulary is "
    "front-loaded into level 1 and whose remaining levels are re-layouts of it. Reusing a "
    "mechanic in a contrasting context is right and is what `relation_to_prev: reuse` is for — "
    "but a level that introduces nothing should be the minority of the curriculum, not its "
    "shape. Give the quiet levels a term of their own (inside the tier budget), or cut them."
)
REFUSAL_PERSISTENCE_KILL_SENTENCE = (
    "A VISIBLE REFUSAL SURVIVES THE FRAME — `knobs.refusal: {visible}` promises a refusal "
    "signal the player can still see on a SETTLED frame (§6's own bar is a signal "
    "\"persisting >=1 settled frame\"). A flash drawn and cleared inside one action is "
    "invisible to a frame-differencing agent and to this pipeline's capture, which keeps the "
    "settled frame only — so a mechanic taught by refusal is a mechanic nobody can learn. Six "
    "of the seven games this pipeline has shipped paint their refusal signal in ZERO captured "
    "records, and a seventh renders its flash into the frame BEFORE the settled one. Either "
    "make the signal persist, or declare it transient: `game.knobs.{field}: true` says the "
    "refusal signal is deliberately momentary and nothing the player must learn from — that "
    "key is the whole exception surface, and a spec that carries it records the departure as "
    "a warn. (§6's other prohibition is separate and absolute: charge silently or signal "
    "freely, NEVER both.)"
)
FIDELITY_SECTION_HEADER = (
    "### Fidelity rules this batch KILLS on (idea facets, inert vocabulary, the unstated field)"
)
# The audit's two corpus facts, quoted by the sentence above (m2-mechanics /
# `escalation.csv`): the officials' non-first levels and our silent share.
OFFICIAL_NON_FIRST_LEVELS = tiers.OFFICIAL_NON_FIRST_LEVELS
OURS_SILENT_SHARE_PCT = 72.3


def _silent_share_limit(floor: object) -> float:
    """One `lint.silent_levels_floor` VALUE, validated — None is the default.

    Loud on everything else, for the reason `resolve_rule_actions` is loud: the
    value reaches a rule that can KILL a writer session straight out of config,
    and a floor typed `0.5%` or `50` would silently disarm (or maximally arm) it.
    A bool is not a number here, the §11 int rule's own convention.

    PRIVATE, and named for the share rather than the knob, on purpose: the ONE
    public floor seam in this module is `lint_silent_levels_floor(cfg)`, which
    takes a whole config like every other `lint.*` reader. Two public callables
    with `floor` in the name and different argument kinds is how a caller — or
    a sweep over this module's readers — hands a config to the wrong one.
    """
    if floor is None:
        return SILENT_LEVELS_FLOOR_DEFAULT
    if isinstance(floor, bool) or not isinstance(floor, (int, float)):
        raise ValueError(  # noqa: TRY004 — a config defect, like every other knob in this module
            f"lint.{SILENT_LEVELS_FLOOR_KEY} must be a number between 0 and 1, got {floor!r} — "
            f"it is the share of non-first levels that may introduce no term"
        )
    if not 0.0 <= float(floor) <= 1.0:
        raise ValueError(
            f"lint.{SILENT_LEVELS_FLOOR_KEY} must be between 0 and 1, got {floor!r} — it is a "
            f"SHARE of the non-first levels, not a percentage or a count"
        )
    return float(floor)


def _silent_levels_sentence(floor: float) -> str:
    """The kill sentence at one floor — one string, both consumers (W1-B pattern)."""
    return SILENT_LEVELS_KILL_SENTENCE.format(
        floor_pct=round(floor * 100, 1),
        official_n=OFFICIAL_NON_FIRST_LEVELS,
        ours_pct=OURS_SILENT_SHARE_PCT,
    )


def fidelity_section(
    actions: Mapping[str, str] | None, *, silent_levels_floor: float | None = None
) -> str | None:
    """The writer-prompt section for whichever fidelity rules are ARMED TO KILL.

    None when nothing is armed to kill — which is every config that exists
    today, so the prompt stays byte-identical. The gate is `kill` and not
    `warn` deliberately: prompt-sync exists so a rule that can KILL a session
    is quoted to the writer being judged by it, while the warn default is a
    measurement pass whose whole point is to read what unprompted writers do.

    Not a `*_NOTE` constant, and not part of `LINT_SURFACE_NOTES`, for the
    reason `render_section` states: the `*_NOTE` family is a discovered set in
    the R2 hotfix-4 suite and every member must sit inside that aggregate
    verbatim, which a conditionally rendered section cannot.
    """
    resolved = resolve_rule_actions(actions)
    items = []
    if resolved[RULE_MIX_HAZARDLESS] == "kill":
        items.append(
            MIX_HAZARDLESS_KILL_SENTENCE.format(
                prefixes=" or ".join(p + "*" for p in HAZARD_PREFIXES),
                override=HAZARDLESS_OVERRIDE_FIELD,
            )
        )
    if resolved[RULE_TERMS_COVERAGE] == "kill":
        items.append(TERMS_COVERAGE_KILL_SENTENCE)
    if resolved[RULE_UNSTATED_BACKGROUND] == "kill":
        items.append(
            UNSTATED_BACKGROUND_KILL_SENTENCE.format(
                pal_min=PALETTE_MIN, pal_max=PALETTE_MAX, default=BACKGROUND_DEFAULT
            )
        )
    if resolved[RULE_SILENT_LEVELS] == "kill":
        items.append(_silent_levels_sentence(_silent_share_limit(silent_levels_floor)))
    if resolved[RULE_REFUSAL_PERSISTENCE] == "kill":
        items.append(
            REFUSAL_PERSISTENCE_KILL_SENTENCE.format(
                visible=REFUSAL_VISIBLE, field=REFUSAL_TRANSIENT_FIELD
            )
        )
    if not items:
        return None
    return _note(FIDELITY_SECTION_HEADER, ["\n\n".join(items)])


def resolve_rule_actions(actions: Mapping[str, str] | None) -> dict[str, str]:
    """Every fidelity rule's action, defaulted — the shape the rules read.

    None (every caller that predates this contract) is the all-`off` map, so a
    `lint_spec` call that never heard of the rules returns the report it always
    returned, finding for finding. A batch opts in through `lint:` config.
    An unknown rule id or an action off the enum is a loud ValueError: these
    reach `lint_spec` from config, and a typo that silently disarmed a rule is
    exactly the inert knob the readiness audit went hunting for.
    """
    if actions is None:
        return dict.fromkeys(FIDELITY_RULES, FIDELITY_DEFAULT_ACTION)
    unknown = sorted(str(rule) for rule in set(actions) - set(FIDELITY_RULES))
    if unknown:
        raise ValueError(f"unknown lint rule id(s) {unknown} (expected {list(FIDELITY_RULES)})")
    resolved = {}
    for rule in FIDELITY_RULES:
        action = actions.get(rule, FIDELITY_DEFAULT_ACTION)
        if action not in FIDELITY_ACTIONS:
            raise ValueError(
                f"lint rule {rule!r} action must be one of {list(FIDELITY_ACTIONS)}, got {action!r}"
            )
        resolved[rule] = action
    return resolved


REPLY_LINE = (
    "End your reply with EXACTLY ONE fenced ```yaml code block containing the completed `game:` "
    "spec. Everything before that block is the prose spec (spec.md)."
)
RETRY_REMINDER = (
    "\n\nREMINDER: your previous reply lacked a single valid fenced ```yaml block with a "
    "top-level `game:` mapping. Reply again, complete, with exactly one such block at the end."
)
# --- §3 S2b escalation (verifier reject ×2 -> S1) ---------------------------
# The escalated re-spec is a REWRITE of a live spec dir, not a new game. The
# pilot proved what a blind re-spec does: handed no findings it re-declared
# nothing the verifier had flagged, and — being nondeterministic — retitled the
# game, so S1 wrote a SECOND corpus dir for one idea. Hence both halves below:
# the findings go INTO the prompt, and the slug is pinned (and enforced after
# the reply, in `run_s1`).
ESCALATION_HEADER = "### IN-PLACE RE-SPEC — this spec's implementation was verifier-rejected ×2"
ESCALATION_INTRO = (
    "You are NOT writing a new game. A spec for the idea above already exists, it was "
    "implemented, and the S2b intent verifier rejected that implementation TWICE — which "
    "escalates to this stage (architecture §3 S2b). Your reply REWRITES that spec IN PLACE: "
    "same slot, same directory, same slug, new spec content. Everything the findings below do "
    "not touch stays as it was; this is surgery on a spec we otherwise want."
)
ESCALATION_FINDINGS_LINE = (
    "The verifier's reject reasons, verbatim — every one of them must be answered:"
)
ESCALATION_RESOLUTION_LINES = (
    (
        "Each finding is resolved IN THE SPEC, not left to the implementation — the verifier "
        "compares the built game against what the spec DECLARES, so an undeclared truth is a "
        "reject however good the game is:"
    ),
    "",
    (
        "- `undeclared-deception` — the audit read that lever off the game. DECLARE it in "
        "`knobs.deceptions` (free text; declaration is substring containment after case and "
        'punctuation are stripped, so `["look-alike splits"]` declares `look-alike`). The '
        "palette-overload lever is the one exact spelling: write `palette overload`, because "
        "that single string is what the palette-collision exemption tests for AND what the "
        "sketch scanner accepts — see the note titled "
        f"'{PALETTE_COLLISION_NOTE_HEADER.removeprefix('### ')}' below."
    ),
    (
        "- `undeclared-term` — a mechanic reachable in play that `game.terms` does not name. ADD "
        "it to `game.terms`: these are §3 vocabulary terms, spelled exactly as the closed set "
        "below spells them."
    ),
    (
        "- `dead-spec-term` / `unreachable-declared-mechanic` — the spec declares it and the "
        "audit cannot reach it. Either give it a GENUINELY reachable mechanic in the levels "
        "(name the level and say how the player meets it), or drop the term from `game.terms`."
    ),
    "",
    (
        "Redesigning a mechanic away is allowed, but DECLARATION IS THE DEFAULT MEDICINE: the "
        "verifier rejected this spec for being silent about what the game does, not for doing "
        "it. The rewrite must still pass the §11 linter below in full."
    ),
)
ESCALATION_SLUG_LINE = (
    "`slug` MUST remain exactly `{slug}`. It is the identity of the directory this rewrite lands "
    "in; a new slug writes a SECOND spec dir for one idea and stops the run. Retitle nothing — "
    "`game.name` and the prose may change, `slug` may not."
)
ESCALATION_DECEPTIONS_LINE = (
    "The spec CURRENTLY declares these deception levers — the same union rule applies on this "
    "axis (round 9 re-flagged levers a rewrite had evicted): your `knobs.deceptions` MUST keep "
    "an entry declaring every one of these, plus every lever the findings name. NEVER remove "
    "one: {levers}"
)
ESCALATION_BASELINE_HEADER = "### YOUR BASELINE — reproduce this spec.yaml byte-for-byte, patched"
ESCALATION_BASELINE_DIRECTIVE = (
    "The document below is the CURRENT spec.yaml. Your reply's ```yaml block must be THIS "
    "DOCUMENT reproduced exactly — same keys, same wording, same order — with ONLY the "
    "additions the findings demand (new `game.terms` entries; new/extended `knobs.deceptions` "
    "entries; a level tweak ONLY if a finding says a declared mechanic is unreachable). Do not "
    "reword a sketch, a title, or any other field: every gratuitous change re-implements the "
    "game and re-rolls the audit. The prose half (before the yaml block) you may write freely."
)
ESCALATION_TERMS_LINE = (
    "The spec CURRENTLY declares these terms, and rounds 3-5 of the pilot oscillated because "
    "rewrites kept EVICTING standing declarations: your `game.terms` MUST be a SUPERSET of "
    "this list plus every term the findings name as reachable-but-undeclared. Remove one of "
    "these ONLY if a finding explicitly says it is dead or unreachable: {terms}"
)
SLUG_REMINDER = (
    "\n\nREMINDER: this is an IN-PLACE re-spec — `game.slug` must be exactly `{required}`, and "
    "your previous reply returned {got}. Reply again, complete, with the whole spec and that "
    "slug unchanged."
)
LINT_KILL_REMINDER = (
    "\n\nREMINDER: your previous rewrite was LINT-KILLED. Fix EXACTLY these and change nothing "
    "else — reply again with the complete spec:\n{kills}"
)
# --- the escalation budget re-check (contract W1-B / R-17) ------------------
# LEAD-ADJUDICATED (b003-freeze.md Addendum 11 adjudication 2):
# `escalation_lint_policy` switches the term budget OFF for an escalated
# rewrite BY DESIGN, and nothing re-imposed it afterwards — facing-sentinel was
# born inside its t1 budget of 6 and two escalation respecs inflated it to 10
# while its stored lint-report still says `passed: true`. So the escalation
# path ships budget-violating specs with honest green reports.
#
# The fix is a SECOND, budget-only re-check after the escalated rewrite lints,
# and the audit's own risk note is the design constraint: a naive re-imposition
# deadlocks "declare what the audit found" against "you are over budget", so
# the re-check's answer to an overrun is a RECONCILIATION TURN, not a bar. One
# turn, then the budget binds.
ESCALATION_BUDGET_RULE = "escalation-term-budget"
# The three states `lint-report.json` records (absent when no re-check ran —
# every non-escalated run, and every escalation under a config with no armed
# tier budget, writes the report it always wrote).
ESCALATION_RECHECK_RAN = "ran"
ESCALATION_RECHECK_RECONCILED = "reconciled"
ESCALATION_RECHECK_FAILED = "failed"
ESCALATION_RECHECK_STATES = (
    ESCALATION_RECHECK_RAN,
    ESCALATION_RECHECK_RECONCILED,
    ESCALATION_RECHECK_FAILED,
)
# PROMPT SYNC, the TIER_TERMS_KILL_SENTENCE pattern again: the reconciliation
# directive and the failure detail below both interpolate that one sentence, so
# the ceiling the writer is asked to hit is the ceiling the finding measures.
# The directive must ALSO lift ESCALATION_TERMS_LINE's superset rule for the
# terms no finding names — otherwise the two instructions are the deadlock the
# audit warned about, spelled across two paragraphs of one prompt.
ESCALATION_BUDGET_REMINDER = (
    "\n\nREMINDER: your rewrite answers the findings but is OVER this game's tier term budget. "
    "{sentence} Your rewrite declares {count}. Reply again with the COMPLETE spec, reconciled: "
    "keep every term the findings name as reachable-but-undeclared, and get back to the ceiling "
    "by FOLDING two declarations into the one mechanic the levels actually carry, or by DROPPING "
    "a term no finding asks for. For this reply only, that outranks the superset rule above — "
    "the standing list may lose a term the findings do not name, and nothing else about the "
    "spec may change."
)
ESCALATION_BUDGET_FAIL_DETAIL = (
    "the escalated re-spec is STILL over its tier term budget after the reconciliation turn. "
    "{sentence} This rewrite declares {count}. The escalation lint runs with the budget switched "
    "off (`escalation_lint_policy`, so audit-forced declarations never bounce off it), and this "
    "budget-only re-check is what closes that loophole: the budget binds at ship time as well as "
    "at authorship, and an unreconciled overrun is not shippable."
)
# == orchestrator.KILLED_DIRNAME, spelled out: the stage never imports the
# state machine. A KILLED escalated rewrite writes its evidence here instead
# of evicting the live spec the ledger claims and the worker implements.
KILLED_DIRNAME = ".killed"
# Idea-stage locus spelling (s0 `mix_class.locus`) -> the §11 `locus` enum.
LOCUS_SPEC_SPELLING = {"mover": "unique-mover", "selection": "selection", "click": "click-only"}

# The two spec fields that are DECLARATIONS ABOUT the game rather than inputs
# to it: no generated `game.py` or `solver.py` reads either one. They exist for
# the S2b intent verifier, which audits the built game AGAINST them.
DECLARATION_ONLY_FIELDS = (
    "game.terms",
    "game.knobs.deceptions",
    # levels[*].terms_introduced is declaration-class too: the Phase-C audit
    # proved byte-level that the worker's validate harness never reads the
    # spec, and §11's unknown-terms rule FORCES a newly declared term into
    # some level's terms_introduced — so without this prune the decl-only
    # marker could never fire for a term addition (it never fired once in
    # the pilot; the one live projection break was exactly one such row).
    "game.levels[*].terms_introduced",
    # CONTRACT P-A.3 (the auto-retier). `game.tier` is the DIFFICULTY LABEL a
    # promotion writes when a reconciled game outgrew the tier its idea was
    # drawn at. It is declaration-class by the same test as the three above: no
    # generated `game.py` or `solver.py` reads it (the tier steers S0's draw and
    # S1's prompt, both upstream of the build), so a spec that gained or changed
    # it describes the same game to build. Without this prune a promotion would
    # break the projection and force a PAID rewrite of an implementation that
    # did not change — the exact cost the decl-only machinery exists to avoid,
    # and a promotion is precisely the case where a declaration moved and the
    # mechanics did not. No spec authored before this contract carries the key,
    # so every projection in the corpus is unchanged.
    "game.tier",
)


def impl_projection(spec_yaml_bytes: bytes) -> str:
    """Hash of everything in a spec.yaml that the IMPLEMENTATION can read.

    Two specs with the same projection describe the same game to build: they
    differ only in `game.terms` and `game.knobs.deceptions`, which the game
    code never reads (see `DECLARATION_ONLY_FIELDS`). An escalated re-spec
    that only widens those lists therefore cannot invalidate the
    implementation sitting beside it — however loudly §2's cascade fires,
    which it does, because the cascade hashes spec.yaml's BYTES and the bytes
    did change. The projection is what tells those two apart.

    DESIGN DECISION — spec.md (the prose half) is deliberately OUTSIDE this
    projection. Implementation correctness is §11-YAML-defined: the contract
    tests generate from the yaml, and the prose is guidance for the writer,
    not a thing the implementation is checked against. So prose edits riding
    along with a declaration-only yaml change do not invalidate an
    implementation. This function is handed yaml bytes only and never opens
    spec.md — that omission IS the decision, recorded here rather than left
    to be inferred from the signature.

    Raises ValueError on bytes that will not parse as yaml or a document that
    is not a mapping: a spec that cannot be read has no projection to compare,
    and silently returning the hash of rubble would equate two broken specs.
    """
    try:
        doc = yaml.safe_load(spec_yaml_bytes)
    except yaml.YAMLError as exc:
        raise ValueError(f"spec yaml does not parse: {exc}") from exc
    if not isinstance(doc, Mapping):
        raise ValueError(  # noqa: TRY004 — a malformed spec is bad data, not a caller type error
            f"spec yaml is not a mapping document (parsed as {type(doc).__name__})"
        )
    pruned = copy.deepcopy(dict(doc))
    game = pruned.get("game")
    if isinstance(game, dict):          # absent/odd `game`: nothing to prune
        game.pop("terms", None)
        game.pop("tier", None)          # contract P-A.3 — see DECLARATION_ONLY_FIELDS
        knobs = game.get("knobs")
        if isinstance(knobs, dict):
            knobs.pop("deceptions", None)
        levels = game.get("levels")
        if isinstance(levels, list):
            for level in levels:
                if isinstance(level, dict):
                    level.pop("terms_introduced", None)
    payload = json.dumps(pruned, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class LintReport:
    """Every §11 violation of one spec. `passed` is exactly `kills == []`.

    Field order is the public contract (callers construct positionally):
    passed, kills, warns, spec_hash. Each kill/warn is
    `{"rule": <KILL_RULES member or warn id>, "detail": str}`.

    `escalation_budget_recheck` (contract W1-B / R-17) is the escalation
    budget re-check's state — one of `ESCALATION_RECHECK_STATES`, or None when
    no re-check ran. It is LAST and it DEFAULTS, so positional construction is
    unchanged; None keeps it out of `to_json_dict` entirely, so every report
    that is not an escalation under an armed tier budget is byte-for-byte the
    report this class has always produced. `lint_spec` never sets it (the
    re-check needs a writer turn, which is `run_s1`'s half of the module).
    """

    passed: bool
    kills: list[dict]
    warns: list[dict]
    spec_hash: str
    escalation_budget_recheck: str | None = None

    def to_json_dict(self) -> dict:
        payload = {
            "passed": self.passed,
            "kills": [dict(k) for k in self.kills],
            "warns": [dict(w) for w in self.warns],
            "spec_hash": self.spec_hash,
        }
        if self.escalation_budget_recheck is not None:
            payload["escalation_budget_recheck"] = self.escalation_budget_recheck
        return payload


@dataclass
class S1Result:
    """One S1 run: what was written, where, and the verdict."""

    spec_text: str
    spec: dict
    report: LintReport
    out_dir: Path
    prompt: str


_MISSING = object()


def _finding(rule: str, detail: str) -> dict:
    return {"rule": rule, "detail": detail}


def _level_label(index: int) -> str:
    """Both index conventions in one label — the reader picks (0-based list
    position, 1-based level number as the corpus and the HUD count them)."""
    return f"levels[{index}] (level {index + 1})"


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_int(value: object) -> bool:
    """bool is an int in Python; a `seed: true` must never pass as an int."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_str_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _in_range(value: object, low: int, high: int) -> bool:
    return _is_int(value) and low <= value <= high


def _is_tiny_token(value: object) -> bool:
    """A usable `game.palette.tiny_token` (contract W2-D): non-empty, distinct, known.

    All three conditions are ONE predicate because they are one claim — "these
    roles, and each of them once, are drawn small on purpose". A list that
    fails any of them declares nothing: `[]` names no role, `["you", "you"]`
    cannot mean anything a single `["you"]` does not, and `["mirror"]` names a
    role no §11 field declares and no check can measure.
    """
    if not _is_str_list(value) or not value:
        return False
    return len(set(value)) == len(value) and all(role in PALETTE_ROLES for role in value)


def _visual_canon() -> ModuleType:
    """`gen.visual_canon`, imported LAZILY — a top-level import would be a CYCLE.

    `visual_canon` does `from .s1_spec import HAZARD_PREFIXES` at ITS module
    level (it decides there whether a spec has danger to render), so this
    module may only reach back into it from inside a function body. The import
    is a `sys.modules` lookup after the first call; nothing here touches disk,
    which is what keeps `lint_spec` pure.
    """
    from . import visual_canon

    return visual_canon


def _tile_scale_menu() -> tuple[int, ...]:
    """The officials' measured tile-scale menu, `{1, 2, 3, 4, 5, 8}` px/cell.

    ONE source: `visual_canon.OFFICIAL_VISUAL_CONSTANTS["tile_scale_menu"]`,
    measured from `features-game.csv`'s `tile_scale` column and cited there. A
    scale off this menu is a WARN here, never a kill — the menu is `64 //
    board_w` over 25 games, not a law of the camera.
    """
    menu = _visual_canon().OFFICIAL_VISUAL_CONSTANTS["tile_scale_menu"]
    return tuple(int(scale) for scale in menu)


# --- rule: schema -----------------------------------------------------------


def _schema_rule(
    game: Mapping, idea: Mapping | None, *, require_render: bool = False
) -> tuple[list[dict], list[dict]]:
    """Mandatory §11 fields, their types and their enums. One kill per offender.

    `require_render` is this batch's `lint.require_render` knob, passed down
    from `lint_spec`: with it armed, an undeclared (or unusable) `game.render`
    is a kill on top of whatever its shape earns.
    """
    kills: list[dict] = []
    warns: list[dict] = []

    def field(name: str) -> object:
        value = game.get(name, _MISSING)
        if value is _MISSING:
            kills.append(_finding("schema", f"game.{name}: missing (mandatory §11 field)"))
        return value

    def bad(name: str, value: object, expected: str) -> None:
        kills.append(_finding("schema", f"game.{name}: {expected}, got {value!r}"))

    slug = field("slug")
    if slug is not _MISSING:
        if not _is_text(slug):
            bad("slug", slug, "must be a non-empty string")
        elif not SLUG_RE.match(slug):
            bad("slug", slug, f"must match {SLUG_RE.pattern} (lowercase id, hyphens only)")

    title = field("title")
    if title is not _MISSING and not _is_text(title):
        bad("title", title, "must be a non-empty string")

    idea_ref = field("idea_ref")
    if idea_ref is not _MISSING:
        if not _is_text(idea_ref):
            bad("idea_ref", idea_ref, "must be a non-empty string (the stage-0 idea id)")
        elif idea is not None and idea.get("id") != idea_ref:
            kills.append(
                _finding(
                    "schema",
                    f"game.idea_ref {idea_ref!r} does not match the idea being specified "
                    f"({idea.get('id')!r})",
                )
            )

    terms = field("terms")
    if terms is not _MISSING and not (_is_str_list(terms) and terms):
        bad("terms", terms, "must be a non-empty list of vocabulary terms (strings)")

    objective = field("objective")
    if objective is not _MISSING:
        if not isinstance(objective, Mapping):
            bad("objective", objective, "must be a mapping {primary, secondary}")
        else:
            primary = objective.get("primary")
            if primary not in OBJECTIVE_FAMILIES:
                bad("objective.primary", primary, f"must be one of {list(OBJECTIVE_FAMILIES)}")
            secondary = objective.get("secondary")
            if secondary is not None and secondary not in OBJECTIVE_FAMILIES:
                bad(
                    "objective.secondary",
                    secondary,
                    f"must be null or one of {list(OBJECTIVE_FAMILIES)}",
                )

    locus = field("locus")
    if locus is not _MISSING and locus not in LOCI:
        bad("locus", locus, f"must be one of {list(LOCI)}")

    actions = field("actions")
    if actions is not _MISSING:
        _schema_actions(actions, kills, bad)

    knobs = field("knobs")
    if knobs is not _MISSING and not isinstance(knobs, Mapping):
        bad("knobs", knobs, "must be a mapping (contents are the missing-knobs rule)")

    palette = field("palette")
    if palette is not _MISSING:
        _schema_palette(palette, kills, bad)

    hud = field("hud")
    if hud is not _MISSING:
        _schema_hud(hud, kills, bad)

    neg2 = field("neg2_readers")
    if neg2 is not _MISSING:
        _schema_neg2(neg2, kills, bad)

    layers = field("layers")
    if layers is not _MISSING and layers != LAYERS_VALUE:
        bad("layers", layers, f"must be the literal {LAYERS_VALUE!r} (§2.6 attestation)")

    layout = field("layout")
    if layout is not _MISSING:
        _schema_layout(layout, kills, bad)

    # `render` is OPTIONAL, so it is NOT fetched through `field()`: absence is
    # silence unless this batch's config armed the knob. LEAD FIX (V-B review):
    # the knob kills on true ABSENCE only — a present-but-malformed block is
    # the shape kill's job, and a "missing" detail about a field that is there
    # is a report that lies. Either way the spec dies with one honest finding.
    render = game.get("render", _MISSING)
    if require_render and render is _MISSING:
        kills.append(_finding("schema", RENDER_REQUIRED_DETAIL))
    if render is not _MISSING:
        _schema_render(render, kills, warns, bad)

    # `hazardless_override` is optional in exactly the way `palette.background`
    # is (contract W1-B / R-16): absence is silence, but a key written down is
    # a declaration and is held to one — an override that says nothing exempts
    # nothing, so an unusable value is a kill rather than a silently ignored
    # field. The override's EFFECT is `_fidelity_rules`' business.
    # `chrome` is optional on `hazardless_override`'s exact terms (contract B1
    # / R-03): absence is silence, a key written down is held to a declaration.
    chrome = game.get(CHROME_FIELD, _MISSING)
    if chrome is not _MISSING:
        _schema_chrome(chrome, kills, bad)

    override = game.get(HAZARDLESS_OVERRIDE_FIELD, _MISSING)
    if override is not _MISSING and not _is_text(override):
        bad(
            HAZARDLESS_OVERRIDE_FIELD,
            override,
            "must be a non-empty string saying WHY this spec departs from the idea's "
            "`mix_class.hazardless` facet — omit the key when it does not",
        )

    levels = field("levels")
    if levels is not _MISSING:
        _schema_levels(levels, kills, bad)

    budget = field("budget")
    if budget is not _MISSING:
        _schema_budget(budget, kills, bad)

    solver_notes = field("solver_notes")
    if solver_notes is not _MISSING and not _is_text(solver_notes):
        bad("solver_notes", solver_notes, "must be non-empty prose (incl. lag/confirm duties)")

    for name in sorted(set(game) - set(GAME_FIELDS) - set(OPTIONAL_GAME_FIELDS)):
        warns.append(
            _finding("unknown-field", f"game.{name}: not a §11 field (ignored downstream)")
        )
    return kills, warns


def _schema_actions(actions: object, kills: list[dict], bad: Callable[..., None]) -> None:
    if not isinstance(actions, Mapping):
        bad("actions", actions, "must be a mapping {ACTION1..ACTION7, decoys}")
        return
    expected = set(ACTION_KEYS) | {"decoys"}
    for name in sorted(expected - set(actions)):
        kills.append(_finding("schema", f"game.actions.{name}: missing (§11 requires it)"))
    for name in sorted(set(actions) - expected):
        kills.append(
            _finding("schema", f"game.actions.{name}: unknown key (allowed: {sorted(expected)})")
        )
    for name in ACTION_KEYS:
        if name in actions and actions[name] not in ACTION_STATES:
            bad(f"actions.{name}", actions[name], f"must be one of {list(ACTION_STATES)}")
    decoys = actions.get("decoys", _MISSING)
    if decoys is _MISSING:
        return
    if not _is_str_list(decoys):
        bad("actions.decoys", decoys, "must be a list of ACTION names (possibly empty)")
        return
    for name in decoys:
        if name not in ACTION_KEYS:
            bad("actions.decoys", name, f"must name an action: {list(ACTION_KEYS)}")
        elif actions.get(name) != "declared":
            # §7.3: a decoy is DECLARED, unhandled and still charged. An
            # `absent` decoy is not a lever, it is a contradiction in the map.
            kills.append(
                _finding(
                    "schema",
                    f"game.actions.decoys names {name}, but game.actions.{name} is "
                    f"{actions.get(name)!r} — a decoy action must be 'declared'",
                )
            )


def _schema_render(
    render: object, kills: list[dict], warns: list[dict], bad: Callable[..., None]
) -> None:
    """`game.render`'s SHAPE only — one declared scale, and nothing else in it.

    The 64-canvas fit and the off-menu scale are `_render_rule`'s business:
    they read `layout.grid` and the corpus menu, neither of which is a shape
    question. This function fires only on rubble.
    """
    if not isinstance(render, Mapping):
        bad("render", render, "must be a mapping {cell_px: int} when declared")
        return
    cell_px = render.get("cell_px", _MISSING)
    if cell_px is _MISSING:
        kills.append(
            _finding(
                "schema",
                "game.render.cell_px: missing — a declared `render` block IS the render scale",
            )
        )
    elif not _in_range(cell_px, CELL_PX_MIN, CELL_PX_MAX):
        bad(
            "render.cell_px",
            cell_px,
            f"must be an int {CELL_PX_MIN}-{CELL_PX_MAX} (pixels per logical cell)",
        )
    # The top-level pattern, one level down: an extra key is a WARN, because a
    # writer's note inside `render` costs nothing and stage 2 reads only what
    # it knows.
    for name in sorted(set(render) - set(RENDER_FIELDS)):
        warns.append(
            _finding("unknown-field", f"game.render.{name}: not a §11 field (ignored downstream)")
        )


def _schema_chrome(chrome: object, kills: list[dict], bad: Callable[..., None]) -> None:
    """`game.chrome`'s SHAPE (contract B1 / R-03) — the declared inert structure.

    ONE kill per offending entry, and the whole-block kill short-circuits: a
    `chrome` that is not a non-empty list declares nothing, and walking a
    non-list to report its entries would turn one defect into a paragraph.

    Every failure here is a KILL rather than an unknown-field warn, on
    `tiny_token`'s exact terms (W2-D): the key is OPTIONAL, so nothing forced
    the writer to type it — but a key written down is a DECLARATION, and a
    declaration nothing downstream can read is worse than silence. The gate's
    `chrome-extent` check reads this list to decide whether a below-band board
    was framed on purpose, and an entry it cannot parse would count as chrome
    while measuring none.
    """
    if not isinstance(chrome, list) or not chrome:
        bad(CHROME_FIELD, chrome, CHROME_DETAIL)
        return
    for position, entry in enumerate(chrome):
        where = f"{CHROME_FIELD}[{position}]"
        if not isinstance(entry, Mapping):
            bad(where, entry, CHROME_DETAIL)
            continue
        for name in sorted(set(CHROME_ENTRY_FIELDS) - set(entry)):
            kills.append(
                _finding("schema", f"game.{where}.{name}: missing (§11 requires it)")
            )
        # An extra key inside an entry is a KILL, not the warn `game.render`
        # gives one: `render` carries a value, so a stray key beside it is a
        # note on a declaration that still reads. A chrome entry IS its two
        # keys, so a third one is a claim this schema cannot carry and the
        # `actions` block's rule applies instead (unknown key, named kill).
        for name in sorted(set(entry) - set(CHROME_ENTRY_FIELDS)):
            kills.append(
                _finding(
                    "schema",
                    f"game.{where}.{name}: unknown key (allowed: {list(CHROME_ENTRY_FIELDS)})",
                )
            )
        kind = entry.get("kind", _MISSING)
        if kind is not _MISSING and kind not in CHROME_KINDS:
            bad(f"{where}.kind", kind, f"must be one of {list(CHROME_KINDS)}")
        spot = entry.get("where", _MISSING)
        if spot is not _MISSING and spot not in CHROME_WHERE:
            bad(
                f"{where}.where",
                spot,
                f"must be one of {list(CHROME_WHERE)} — {CHROME_CUSTOM!r} names a geometry "
                f"this schema cannot express and the gate measures it as not-checked",
            )


def _schema_palette(palette: object, kills: list[dict], bad: Callable[..., None]) -> None:
    if not isinstance(palette, Mapping):
        bad("palette", palette, "must be a mapping {you, goal, danger, reserved}")
        return
    for name in ("you", "goal"):
        if name not in palette:
            kills.append(_finding("schema", f"game.palette.{name}: missing (mandatory §11 field)"))
        elif not _in_range(palette[name], PALETTE_MIN, PALETTE_MAX):
            bad(f"palette.{name}", palette[name], f"must be an int {PALETTE_MIN}-{PALETTE_MAX}")
    danger = palette.get("danger")
    if danger is not None and not _in_range(danger, PALETTE_MIN, PALETTE_MAX):
        bad("palette.danger", danger, f"must be null or an int {PALETTE_MIN}-{PALETTE_MAX}")
    # `background` is OPTIONAL (contract V-B) and, unlike `danger`, it has no
    # §11 null: absence means UNSTATED (canon's default is black-5, affordance
    # §9) while `background: null` is a value that is not an index. A key
    # written down is a declaration and is held to one.
    background = palette.get("background", _MISSING)
    if background is not _MISSING and not _in_range(background, PALETTE_MIN, PALETTE_MAX):
        bad(
            "palette.background",
            background,
            f"must be an int {PALETTE_MIN}-{PALETTE_MAX} — omit the key to leave the background "
            f"unstated (canon default: {BACKGROUND_DEFAULT}, affordance §9)",
        )
    # `tiny_token` is OPTIONAL on `background`'s terms (contract W2-D / R-02):
    # absence is silence, a key written down is a declaration. Held to one
    # here, and read as the role-footprint exemption in `s3_visual`.
    tiny_token = palette.get(TINY_TOKEN_FIELD, _MISSING)
    if tiny_token is not _MISSING and not _is_tiny_token(tiny_token):
        bad(f"palette.{TINY_TOKEN_FIELD}", tiny_token, TINY_TOKEN_DETAIL)
    reserved = palette.get("reserved", _MISSING)
    if reserved is _MISSING:
        kills.append(_finding("schema", "game.palette.reserved: missing (mandatory §11 field)"))
    elif not isinstance(reserved, list) or not reserved:
        bad("palette.reserved", reserved, "must be a non-empty list of palette indices")
    else:
        for index in reserved:
            if not _in_range(index, PALETTE_MIN, PALETTE_MAX):
                bad("palette.reserved", index, f"entries must be ints {PALETTE_MIN}-{PALETTE_MAX}")


def _schema_hud(hud: object, kills: list[dict], bad: Callable[..., None]) -> None:
    if not isinstance(hud, Mapping):
        bad("hud", hud, "must be a mapping {reserved, meter}")
        return
    if "reserved" not in hud:
        kills.append(_finding("schema", "game.hud.reserved: missing (mandatory §11 field)"))
    elif hud["reserved"] not in HUD_RESERVED:
        bad("hud.reserved", hud["reserved"], f"must be one of {list(HUD_RESERVED)}")
    meter = hud.get("meter", _MISSING)
    if meter is _MISSING:
        kills.append(_finding("schema", "game.hud.meter: missing (mandatory §11 field)"))
    elif not isinstance(meter, Mapping):
        bad("hud.meter", meter, "must be a mapping {placement, direction}")
    else:
        for name in ("placement", "direction"):
            if name not in meter:
                kills.append(
                    _finding("schema", f"game.hud.meter.{name}: missing (mandatory §11 field)")
                )
            elif not _is_text(meter[name]):
                bad(f"hud.meter.{name}", meter[name], "must be a non-empty string")


def _schema_neg2(neg2: object, kills: list[dict], bad: Callable[..., None]) -> None:
    # §2.5: every -2 pixel ships with a declared reader. The list may be empty
    # (a game with no -2 declares none) but each entry is one {class: mask}.
    if not isinstance(neg2, list):
        bad("neg2_readers", neg2, "must be a list of single-key {sprite-class: mask} mappings")
        return
    for position, entry in enumerate(neg2):
        where = f"neg2_readers[{position}]"
        if not isinstance(entry, Mapping) or len(entry) != 1:
            bad(where, entry, "must be a single-key mapping {sprite-class: mask}")
            continue
        (key, value), = entry.items()
        if not _is_text(key) or not _is_text(value):
            bad(where, entry, "must map a non-empty sprite-class string to a non-empty mask")


def _schema_layout(layout: object, kills: list[dict], bad: Callable[..., None]) -> None:
    if not isinstance(layout, Mapping):
        bad("layout", layout, "must be a mapping {seed, grid}")
        return
    if "seed" not in layout:
        kills.append(_finding("schema", "game.layout.seed: missing (mandatory §11 field)"))
    elif not _is_int(layout["seed"]):
        bad("layout.seed", layout["seed"], "must be an int (§7: layouts are functions of it)")
    grid = layout.get("grid", _MISSING)
    if grid is _MISSING:
        kills.append(_finding("schema", "game.layout.grid: missing (mandatory §11 field)"))
    elif not isinstance(grid, list) or len(grid) != 2:
        bad("layout.grid", grid, "must be [w, h]")
    else:
        for axis, value in zip(("w", "h"), grid, strict=True):
            if not _in_range(value, GRID_MIN, GRID_MAX):
                bad(f"layout.grid.{axis}", value, f"must be an int {GRID_MIN}-{GRID_MAX}")


def _schema_levels(levels: object, kills: list[dict], bad: Callable[..., None]) -> None:
    # COUNT is the curriculum rule's business; ITEM SHAPE is schema's.
    if not isinstance(levels, list):
        bad("levels", levels, "must be a list of level mappings")
        return
    for position, level in enumerate(levels):
        where = _level_label(position)
        if not isinstance(level, Mapping):
            bad(where, level, "must be a mapping {relation_to_prev, terms_introduced, sketch}")
            continue
        if "relation_to_prev" not in level:
            kills.append(_finding("schema", f"game.{where}.relation_to_prev: missing"))
        elif level["relation_to_prev"] not in RELATIONS:
            bad(f"{where}.relation_to_prev", level["relation_to_prev"],
                f"must be one of {list(RELATIONS)}")
        if "terms_introduced" not in level:
            kills.append(_finding("schema", f"game.{where}.terms_introduced: missing"))
        elif not _is_str_list(level["terms_introduced"]):
            bad(f"{where}.terms_introduced", level["terms_introduced"],
                "must be a list of terms (strings; may be empty)")
        if "sketch" not in level:
            kills.append(_finding("schema", f"game.{where}.sketch: missing"))
        elif not _is_text(level["sketch"]):
            bad(f"{where}.sketch", level["sketch"], "must be non-empty prose")


def _schema_budget(budget: object, kills: list[dict], bad: Callable[..., None]) -> None:
    if not isinstance(budget, Mapping):
        bad("budget", budget, "must be a mapping {enforced, displayed, counts, lives}")
        return
    # §2 gate 3: exhaustion wired to lose(). `enforced: false` is not a knob.
    if budget.get("enforced") is not True:
        bad("budget.enforced", budget.get("enforced"),
            "must be true (§2 gate 3: exhaustion is wired to lose())")
    if "displayed" not in budget:
        kills.append(_finding("schema", "game.budget.displayed: missing (mandatory §11 field)"))
    elif not isinstance(budget["displayed"], bool):
        bad("budget.displayed", budget["displayed"], "must be a bool")
    if "counts" not in budget:
        kills.append(_finding("schema", "game.budget.counts: missing (mandatory §11 field)"))
    elif not _is_text(budget["counts"]):
        bad("budget.counts", budget["counts"], "must be a one-line description of WHAT is counted")
    lives = budget.get("lives")
    if lives is not None and not _is_int(lives):
        bad("budget.lives", lives, "must be null or an int")


# --- rules: everything after schema -----------------------------------------


def _unknown_terms_rule(
    terms: list[str], levels: list, vocab: Collection[str]
) -> list[dict]:
    kills: list[dict] = []
    for term in terms:
        if term not in vocab:
            kills.append(
                _finding("unknown-terms", f"game.terms: {term!r} is not a §3 vocabulary term")
            )
    known = set(terms)
    for position, level in enumerate(levels):
        if not isinstance(level, Mapping):
            continue
        introduced = level.get("terms_introduced")
        if not _is_str_list(introduced):
            continue
        for term in introduced:
            if term not in known:
                kills.append(
                    _finding(
                        "unknown-terms",
                        f"game.{_level_label(position)}.terms_introduced: {term!r} is not in "
                        f"game.terms",
                    )
                )
    return kills


def _objective_rule(objective: Mapping, terms: list[str]) -> list[dict]:
    """§3b: BOTH declared slots are strict for generated games (no qualifier
    exemption — that is the officials-only D24 split rule)."""
    kills: list[dict] = []
    present = set(terms)
    for slot in ("primary", "secondary"):
        family = objective.get(slot)
        if family is None or family not in WITNESS_MAP:
            continue  # absent slot, or schema already killed the value
        witnesses = WITNESS_MAP[family]
        if not present.intersection(witnesses):
            kills.append(
                _finding(
                    "objective-unwitnessed",
                    f"game.objective.{slot} {family!r} is witnessed by "
                    f"{list(witnesses)} — none is in game.terms",
                )
            )
    return kills


def _knobs_rule(knobs: Mapping) -> list[dict]:
    kills: list[dict] = []
    enums = {
        "refusal": REFUSALS,
        "goal_legible": GOAL_LEGIBLE,
        "danger_tell": DANGER_TELLS,
    }
    for name in KNOB_FIELDS:
        if name not in knobs:
            kills.append(
                _finding("missing-knobs", f"game.knobs.{name}: missing (§5 knobs are mandatory)")
            )
            continue
        value = knobs[name]
        if name in enums and value not in enums[name]:
            kills.append(
                _finding(
                    "missing-knobs",
                    f"game.knobs.{name}: {value!r} must be one of {list(enums[name])}",
                )
            )
    if "deceptions" in knobs and not _is_str_list(knobs["deceptions"]):
        kills.append(
            _finding(
                "missing-knobs",
                f"game.knobs.deceptions: {knobs['deceptions']!r} must be a list of catalog "
                f"entries (strings; empty means none declared)",
            )
        )
    # The OPTIONAL knobs (contract B1 / R-08): absent is silence — they are not
    # in `KNOB_FIELDS`, which is the mandatory list, so the loop above never
    # asks for them — but a key written down is a declaration and is held to
    # one. `refusal_transient` is the only member today and it is a bool: a
    # string "true" or a 1 declares nothing this module can act on, and silently
    # ignoring it would exempt a spec that thinks it declared the exception.
    for name in OPTIONAL_KNOB_FIELDS:
        if name in knobs and not isinstance(knobs[name], bool):
            kills.append(
                _finding(
                    "missing-knobs",
                    f"game.knobs.{name}: {knobs[name]!r} must be a bool — omit the key to "
                    f"leave it undeclared (§6's default: a visible refusal persists into a "
                    f"settled frame)",
                )
            )
    return kills


def _curriculum_rule(levels: list) -> list[dict]:
    """§7 escalation grammar. Level 1's relation is unconstrained, but it does
    count toward a run: new/new/new is >2 consecutive `new` wherever it sits.

    `invert` (contract A2 / R-11) needed NO code here, and that is the ruling,
    not an oversight — both tests below are written against the literal string
    `"new"` and the literal string `"reuse"`, so a fourth relation lands on the
    documented semantics by construction:

      * it is NOT `new` for the ≤2-consecutive-new run. An inversion re-reads a
        rule the game already taught; it does not add one, so it BREAKS a run of
        `new` exactly the way `reuse` and `compose` do.
      * it does NOT satisfy the ≥1-reuse requirement (the contract's own
        recommendation, taken: reuse stays reuse). §7's reason for that rule is
        that a mechanic is not established until it is met again in a
        contrasting context — and a level that INVERTS a rule is not a second
        honest encounter with it, it is a contradiction of it. A spec whose only
        non-`new` levels are inversions has still never established anything.

    Both facts are stated in `CURRICULUM_NOTE`, so the writer is judged on the
    semantics it was handed.
    """
    kills: list[dict] = []
    count = len(levels)
    if not LEVELS_MIN <= count <= LEVELS_MAX:
        kills.append(
            _finding(
                "curriculum",
                f"game.levels: {count} level(s), must be {LEVELS_MIN}-{LEVELS_MAX} (§7)",
            )
        )
    relations = [
        level.get("relation_to_prev") if isinstance(level, Mapping) else None for level in levels
    ]
    run_start = 0
    run = 0
    for position, relation in enumerate(relations + [None]):
        if relation == "new":
            if run == 0:
                run_start = position
            run += 1
            continue
        if run > MAX_CONSECUTIVE_NEW:
            span = ", ".join(_level_label(i) for i in range(run_start, run_start + run))
            kills.append(
                _finding(
                    "curriculum",
                    f"{run} consecutive levels with relation_to_prev 'new' ({span}) — "
                    f"at most {MAX_CONSECUTIVE_NEW} in a row (§7)",
                )
            )
        run = 0
    if count and "reuse" not in relations:
        kills.append(
            _finding(
                "curriculum",
                "no level has relation_to_prev 'reuse' — a mechanic is not established until "
                "it is reused in a contrasting context (§7)",
            )
        )
    return kills


def _palette_rule(palette: Mapping, deceptions: list[str]) -> tuple[list[dict], list[dict]]:
    kills: list[dict] = []
    warns: list[dict] = []
    reserved = palette.get("reserved")
    reserved_ok = isinstance(reserved, list) and all(_is_int(i) for i in reserved)
    slots = {}
    for name in PALETTE_ROLES:
        value = palette.get(name)
        if _is_int(value):
            slots[name] = value
    if reserved_ok:
        for name, value in slots.items():
            if value in reserved:
                kills.append(
                    _finding(
                        "palette-collision",
                        f"game.palette.{name} index {value} is also in palette.reserved "
                        f"{sorted(reserved)} (§2.8: semantic indices stay off the reserved set)",
                    )
                )
    # §2.8 / §7.2: one index in several roles is legal ONLY as a declared lever.
    exempting = [entry for entry in deceptions if OVERLOAD_KEYWORD in entry.lower()]
    pairs = [("you", "goal"), ("you", "danger"), ("goal", "danger")]
    # A declared `background` (contract V-B) joins the OVERLOAD pairs and NOT
    # the reserved check above: it is the paint the board starts as, not one of
    # §2.8's three semantic indices, and reserving the background index is
    # ordinary good practice rather than a collision. A role drawn in the
    # background's own colour is invisible — the same §7.2 lever, one row down,
    # so it rides the same exemption branch (do not re-implement it).
    background = palette.get("background")
    if _in_range(background, PALETTE_MIN, PALETTE_MAX):
        slots["background"] = background
        pairs += [("background", name) for name in PALETTE_ROLES]
    for left, right in pairs:
        if left not in slots or right not in slots or slots[left] != slots[right]:
            continue
        pair = f"palette.{left} == palette.{right} == {slots[left]}"
        if exempting:
            warns.append(
                _finding(
                    "palette-overload-declared",
                    f"{pair}: exempted — knobs.deceptions declares {exempting!r} "
                    f"(§2.8 declared palette-overload lever)",
                )
            )
        else:
            kills.append(
                _finding(
                    "palette-collision",
                    f"{pair}: not exempted — no knobs.deceptions entry contains "
                    f"{OVERLOAD_KEYWORD!r}, so the overload is undeclared (§2.8)",
                )
            )
    return kills, warns


def _lever_declared(keyword: str, declared: Sequence[str]) -> bool:
    """True when some already-squashed declaration entry names this LEVER.

    Squashed-substring containment, unchanged — applied to every spelling of the
    lever rather than to one keyword (contract E-1). `["camouflage: the grey
    wall reads as letterbox"]` declares §7.2 exactly as `["palette overload"]`
    does, because camouflage IS how §7.2 reads on the board; before the fold the
    two spellings were two levers and the same spec declared neither of the
    other's sketches.
    """
    return any(
        _squash(spelling) in entry
        for spelling in lever_spellings(keyword)
        for entry in declared
    )


def _deception_rule(levels: list, deceptions: list[str] | None) -> list[dict]:
    """Every catalog lever a sketch uses must be declared in knobs.deceptions.

    `deceptions=None` means the field is present but unreadable (not a list of
    strings): missing-knobs already named that offender, and "you failed to
    declare it" is not established when the declaration cannot be read.

    One kill per LEVER per level (E-1: per lever, where it used to be per
    squashed KEYWORD). A sketch that says both "camouflage" and "palette
    overload" is using one lever twice, and it used to collect two kills for it.
    """
    if deceptions is None:
        return []
    kills: list[dict] = []
    declared = [_squash(entry) for entry in deceptions]
    for position, level in enumerate(levels):
        if not isinstance(level, Mapping):
            continue
        sketch = level.get("sketch")
        if not isinstance(sketch, str):
            continue
        seen: set[str] = set()
        for keyword, spelling, pattern in _DECEPTION_PATTERNS:
            match = next(
                (m for m in pattern.finditer(sketch) if not _negated(sketch, m.start())),
                None,
            )
            if match is None:
                continue
            if keyword in seen:
                continue  # same lever, another spelling — one kill per lever
            seen.add(keyword)
            if _lever_declared(keyword, declared):
                continue
            # The detail names BOTH: the spelling the sketch used (which is the
            # word the writer has to find) and the lever it folds onto (which is
            # what `knobs.deceptions` has to declare).
            lever = (
                f"catalog keyword {keyword!r}"
                if spelling == keyword
                else f"spelling {spelling!r} of catalog keyword {keyword!r}"
            )
            kills.append(
                _finding(
                    "undeclared-deception",
                    f"game.{_level_label(position)}.sketch says {match.group(0)!r} "
                    f"({lever}) but no knobs.deceptions entry declares it",
                )
            )
    return kills


def _render_rule(render: object, layout: object) -> tuple[list[dict], list[dict]]:
    """The two DERIVED render findings: the off-menu scale, the 64-canvas fit.

    Both read a `cell_px` the schema rule already vetted, and the fit also
    reads a `layout.grid` the schema rule already vetted: an unusable view
    means schema named that offender, and this rule stays silent rather than
    piling a second, derived finding on top of it.

    The fit is a `contradiction` — the spec declares a scale AND a grid, and on
    a 64x64 camera the two cannot both be true. It rides that existing rule id
    because the §11 kill list is CLOSED (KILL_RULES), not because a new id
    would have read worse.
    """
    kills: list[dict] = []
    warns: list[dict] = []
    if not isinstance(render, Mapping):
        return kills, warns
    cell_px = render.get("cell_px")
    if not _in_range(cell_px, CELL_PX_MIN, CELL_PX_MAX):
        return kills, warns

    menu = _tile_scale_menu()
    if cell_px not in menu:
        warns.append(
            _finding(
                "render-scale-off-menu",
                f"game.render.cell_px {cell_px} is not on the officials' tile-scale menu "
                f"{{{', '.join(str(scale) for scale in menu)}}} — off-menu, not impossible "
                f"(gen/visual_canon.py OFFICIAL_VISUAL_CONSTANTS['tile_scale_menu'])",
            )
        )

    grid = layout.get("grid") if isinstance(layout, Mapping) else None
    if not (
        isinstance(grid, list)
        and len(grid) == 2
        and all(_in_range(value, GRID_MIN, GRID_MAX) for value in grid)
    ):
        return kills, warns
    width = cell_px * grid[0]
    height = cell_px * grid[1]
    if width > CANVAS_PX or height > CANVAS_PX:
        kills.append(
            _finding(
                "contradiction",
                f"game.render.cell_px {cell_px} x game.layout.grid {list(grid)} = "
                f"{width}x{height} px, past the {CANVAS_PX}x{CANVAS_PX} camera — the declared "
                f"scale cannot draw the declared grid (one render scale, whole board on screen)",
            )
        )
    return kills, warns


def _contradiction_rule(
    game: Mapping, terms: list[str], knobs: Mapping, deceptions: list[str]
) -> list[dict]:
    kills: list[dict] = []
    present = set(terms)

    # C1 — a tell for a danger the term list does not contain.
    danger_tell = knobs.get("danger_tell")
    tell_declared = danger_tell in DANGER_TELLS and danger_tell != "none"
    if tell_declared and not any(term.startswith(HAZARD_PREFIXES) for term in present):
        kills.append(
            _finding(
                "contradiction",
                f"knobs.danger_tell is {danger_tell!r} but game.terms holds no "
                f"{' or '.join(p + '*' for p in HAZARD_PREFIXES)} term — no danger to tell",
            )
        )

    # C2 — a visible refusal cannot also be the silent decoy lever.
    if knobs.get("refusal") == "visible":
        for entry in deceptions:
            low = entry.lower()
            if "silent" in low and "decoy" in low:
                kills.append(
                    _finding(
                        "contradiction",
                        f"knobs.refusal is 'visible' but knobs.deceptions declares {entry!r} — "
                        f"a silent decoy action cannot refuse visibly",
                    )
                )

    # C3 — survive with the budget as its only clock.
    objective = game.get("objective")
    families = set()
    if isinstance(objective, Mapping):
        families = {objective.get("primary"), objective.get("secondary")}
    if "survive" in families and "budget.cap" in present:
        clocks = sorted(present.intersection(SURVIVE_CLOCK_TERMS))
        if not clocks:
            kills.append(
                _finding(
                    "contradiction",
                    "objective 'survive' with 'budget.cap' and none of "
                    f"{list(SURVIVE_CLOCK_TERMS)} in game.terms — the budget is the only clock, "
                    "so surviving IS exhausting it (§6: one counter never means both budget and "
                    "goal.survive)",
                )
            )
    return kills


# --- rules: the fidelity contract (contract W1-B / R-16) --------------------


def _hazardless_idea(idea: Mapping | None) -> bool:
    """True only when the idea's `mix_class.hazardless` facet is literally True.

    Every absence is False — no idea, no `mix_class`, no facet, or a facet that
    is not a bool. The facet is drawn by S0 (`batch.mix.hazardless`) and is the
    only thing that arms `mix-hazardless`: with no idea in hand (the pure
    `lint_spec(spec, vocab)` call) the rule cannot fire at all, which is the
    same absent-facet pattern the tier rules keep.
    """
    if not isinstance(idea, Mapping):
        return False
    mix = idea.get("mix_class")
    return isinstance(mix, Mapping) and mix.get("hazardless") is True


def _fidelity_rules(
    game: Mapping,
    idea: Mapping | None,
    *,
    actions: Mapping[str, str],
    terms: list[str],
    terms_usable: bool,
    levels: list,
    levels_usable: bool,
    knobs: Mapping | None,
    silent_levels_floor: float = SILENT_LEVELS_FLOOR_DEFAULT,
) -> tuple[list[dict], list[dict]]:
    """The two R-16 rules, R-25's third and R-11's fourth. Silent while `off`.

    All three keep the derived-rule silence the rest of this module keeps: a
    view schema already killed (a `terms` that is not a list of strings, a
    `levels` that is not a list, an unreadable `knobs`, a `palette` that is not
    a mapping) is not re-reported here.

    `mix-hazardless` reads ONE declared override — `game.hazardless_override`,
    a non-empty string saying why the spec departs from the facet. A spec that
    carries it keeps its hazard and the departure is RECORDED as a warn, the
    `palette-overload-declared` precedent: an exemption that leaves no trace in
    the report is an exemption nobody can audit.
    """
    kills: list[dict] = []
    warns: list[dict] = []

    def record(rule: str, detail: str, action: str) -> None:
        (kills if action == "kill" else warns).append(_finding(rule, detail))

    hazardless_action = actions[RULE_MIX_HAZARDLESS]
    if hazardless_action != "off" and _hazardless_idea(idea):
        offenders = [
            f"game.terms declares {term!r}"
            for term in (terms if terms_usable else [])
            if term.startswith(HAZARD_PREFIXES)
        ]
        tell = knobs.get("danger_tell") if knobs is not None else None
        if tell in DANGER_TELLS and tell != "none":
            offenders.append(f"game.knobs.danger_tell is {tell!r}")
        override = game.get(HAZARDLESS_OVERRIDE_FIELD)
        if offenders and _is_text(override):
            warns.append(
                _finding(
                    MIX_HAZARDLESS_OVERRIDE_WARN,
                    f"{'; '.join(offenders)} against the idea's mix_class.hazardless: exempted — "
                    f"game.{HAZARDLESS_OVERRIDE_FIELD} declares {_lever_label(override)!r}",
                )
            )
        else:
            sentence = MIX_HAZARDLESS_KILL_SENTENCE.format(
                prefixes=" or ".join(p + "*" for p in HAZARD_PREFIXES),
                override=HAZARDLESS_OVERRIDE_FIELD,
            )
            for offender in offenders:
                record(RULE_MIX_HAZARDLESS, f"{sentence} This spec: {offender}.", hazardless_action)

    coverage_action = actions[RULE_TERMS_COVERAGE]
    if coverage_action != "off" and terms_usable and levels_usable:
        introduced: set[str] = set()
        for level in levels:
            if not isinstance(level, Mapping):
                continue
            entries = level.get("terms_introduced")
            if _is_str_list(entries):
                introduced.update(entries)
        # dict.fromkeys, not set(): the offenders are reported in the spec's
        # OWN declaration order, and a term declared twice is named once.
        uncovered = [term for term in dict.fromkeys(terms) if term not in introduced]
        if uncovered:
            record(
                RULE_TERMS_COVERAGE,
                f"{TERMS_COVERAGE_KILL_SENTENCE} This spec declares {len(uncovered)} term(s) no "
                f"level introduces: {uncovered}.",
                coverage_action,
            )

    # `unstated-background` (contract W2-D) keeps the same derived-rule silence:
    # a `palette` that is not a mapping was already killed by schema, and a
    # `background` that IS written down but unusable was already killed by
    # `_schema_palette` — the key is there, the declaration was made, and this
    # rule's whole question is whether one was made at all.
    background_action = actions[RULE_UNSTATED_BACKGROUND]
    palette = game.get("palette")
    if (
        background_action != "off"
        and isinstance(palette, Mapping)
        and "background" not in palette
    ):
        record(
            RULE_UNSTATED_BACKGROUND,
            UNSTATED_BACKGROUND_KILL_SENTENCE.format(
                pal_min=PALETTE_MIN, pal_max=PALETTE_MAX, default=BACKGROUND_DEFAULT
            )
            + f" This spec declares no `game.palette.background`, so `field-index` will read it "
            f"against the canon default {BACKGROUND_DEFAULT}.",
            background_action,
        )

    # `silent-levels` (contract A2 / R-11). It reads ONLY levels whose
    # `terms_introduced` is a usable list: a level missing the field, or
    # carrying something that is not a list of strings, is already a `schema`
    # kill by name, and counting it as silent would report the same defect twice
    # under a rule that cannot fix it. With no readable non-first level left
    # there is no share to measure and the rule says nothing.
    silent_action = actions[RULE_SILENT_LEVELS]
    if silent_action != "off" and levels_usable:
        readable = [
            (position, level.get("terms_introduced"))
            for position, level in enumerate(levels)
            if position >= 1 and isinstance(level, Mapping)
            and _is_str_list(level.get("terms_introduced"))
        ]
        silent = [position for position, entries in readable if not entries]
        if readable and len(silent) / len(readable) > silent_levels_floor:
            record(
                RULE_SILENT_LEVELS,
                f"{_silent_levels_sentence(silent_levels_floor)} This spec: "
                f"{len(silent)}/{len(readable)} non-first levels introduce no term "
                f"({', '.join(_level_label(position) for position in silent)}).",
                silent_action,
            )

    # `refusal-persistence` (contract B1 / R-08). It reads ONE knob and one
    # optional declaration, and it keeps the derived-rule silence the rest of
    # this block keeps: an unreadable `knobs` is already a `schema` kill, and a
    # `refusal` outside the enum is already a `missing-knobs` kill, so neither
    # is re-reported here under a rule that cannot fix it.
    #
    # The declaration is held to a BOOL, and only `true` exempts. `false` is a
    # spec explicitly saying the signal is NOT transient, which is the promise
    # restated — so it records like the absent key, and the report says which of
    # the two it read.
    refusal_action = actions[RULE_REFUSAL_PERSISTENCE]
    if refusal_action != "off" and knobs is not None:
        declared = knobs.get(REFUSAL_TRANSIENT_FIELD, _MISSING)
        transient = declared is True
        if knobs.get("refusal") == REFUSAL_VISIBLE and not transient:
            record(
                RULE_REFUSAL_PERSISTENCE,
                REFUSAL_PERSISTENCE_KILL_SENTENCE.format(
                    visible=REFUSAL_VISIBLE, field=REFUSAL_TRANSIENT_FIELD
                )
                + f" This spec declares `refusal: {REFUSAL_VISIBLE}` and "
                + (
                    f"no `knobs.{REFUSAL_TRANSIENT_FIELD}`"
                    if declared is _MISSING
                    else f"`knobs.{REFUSAL_TRANSIENT_FIELD}: {declared!r}`"
                )
                + ", so it PROMISES a settled-frame-persistent refusal signal.",
                refusal_action,
            )
    return kills, warns


# --- rules: the tier contract (contract T-B) --------------------------------


def _tier_enum_values(enum: Sequence[str], ordinals: Mapping[str, int], ceiling: int) -> str:
    """The enum values at or under `ceiling`, in the ENUM's own order, "/"-joined.

    t2 `danger_tell` -> "unique-hue/texture/absence" (texture and absence share
    rank 1 — §3.3 lists them as one cell, alternatives at one readability).
    """
    return "/".join(value for value in enum if value in ordinals and ordinals[value] <= ceiling)


def _goal_legible_ceiling(row: tiers.TierRow, policy: tiers.TierPolicy) -> int:
    """The tier's goal_legible ceiling under the batch cap, when one is armed.

    `tiers.goal_legible_cap` (the operator's 2026-09-29 legibility ruling) tightens —
    never loosens — the §3.3 table's per-tier max. None = the row's own max,
    today's bytes.
    """
    if policy.goal_legible_cap is None:
        return row.goal_legible_max
    return min(row.goal_legible_max, tiers.GOAL_LEGIBLE_ORDINAL[policy.goal_legible_cap])


def _idea_tier(idea: Mapping | None, policy: tiers.TierPolicy | None) -> str | None:
    """The tier this idea was drawn at, or None when no tier rule may run.

    Silent on EVERY absence — no policy, no idea, no `tier` facet, or a tier the
    signed table does not carry. That is the absent-facet pattern: a pipeline
    that never heard of the `tiers:` block lints and prompts byte-for-byte as it
    did before this module grew tier rules.
    """
    if policy is None or not isinstance(idea, Mapping):
        return None
    tier = idea.get("tier")
    return tier if isinstance(tier, str) and tier in tiers.TIERS else None


def _lever_label(entry: str) -> str:
    """A declared lever, short enough to name inside one lint detail."""
    text = " ".join(entry.split())
    return text if len(text) <= 48 else text[:45] + "..."


def _declared_levers(deceptions: Sequence[str]) -> list[str]:
    """The DISTINCT deception levers a `knobs.deceptions` list declares.

    Catalog levers are read exactly as `_deception_rule` reads a DECLARATION —
    squashed containment over every SPELLING of the lever — so `["look-alike
    splits"]`, `["lookalike"]` and `["mimic"]` are the same one lever, and a
    single entry naming three catalog levers declares three. That fold is
    contract E-1's: the count is over the canon's six levers, so a spec that
    says "camouflage" in one entry and "palette overload" in the next has
    declared ONE lever twice, not two levers (it used to count two).

    An entry matching no catalog spelling still counts as one lever of its own
    (deduped by its squashed form): §7.5's invisible-state lever is deliberately
    uncatalogued, so "the catalog does not know it" never means "nothing was
    declared" — the tier ceiling counts DECLARATIONS.
    """
    levers: list[str] = []
    seen: set[str] = set()
    for entry in deceptions:
        squashed = _squash(entry)
        matched = False
        for keyword in DECEPTION_CATALOG:
            if not _lever_declared(keyword, [squashed]):
                continue
            matched = True
            if keyword not in seen:
                seen.add(keyword)
                levers.append(keyword)
        if not matched and squashed not in seen:
            seen.add(squashed)
            levers.append(_lever_label(entry))
    return levers


def _tier_rules(
    tier: str,
    policy: tiers.TierPolicy,
    *,
    terms: list[str],
    terms_usable: bool,
    levels: list,
    levels_usable: bool,
    knobs: Mapping | None,
    deceptions: list[str] | None,
) -> tuple[list[dict], list[dict]]:
    """The four tier rules of one already-tiered spec (contract T-B §3).

    Each rule is governed by its own action knob and is silent while that knob
    is "off"; each is ALSO silent when the view it reads is unusable, the
    existing derived-rule pattern (schema already named that offender, and a
    second derived finding would only hide it).

    `danger_tell` is checked only for a spec whose `terms` carry a hazard: a
    hazardless game is FORCED to `danger_tell: none` by contradiction rule C1,
    and `none` ranks 2 on the tell ladder (§3.3 lists it in the t3 column), so
    an unexempted ceiling check would flag every hazardless t1 spec for obeying
    C1 — the caveat `gen/tiers.py`'s own docstring hands to whoever enforces it.
    """
    row = tiers.TIER_TABLE[tier]
    kills: list[dict] = []
    warns: list[dict] = []

    def record(rule: str, detail: str, action: str) -> None:
        (kills if action == "kill" else warns).append(_finding(rule, detail))

    budget = policy.term_budget.get(tier) if policy.term_budget is not None else None
    if budget is not None and terms_usable and len(terms) > budget:
        record(
            "tier-terms",
            TIER_TERMS_KILL_SENTENCE.format(tier=tier, budget=budget)
            + f" This spec declares {len(terms)}.",
            policy.term_budget_action,
        )

    knob_action = policy.knob_defaults_action
    if knob_action != "off" and knobs is not None:
        hazardous = terms_usable and any(term.startswith(HAZARD_PREFIXES) for term in terms)
        goal_ceiling = _goal_legible_ceiling(row, policy)
        checks = (
            ("refusal", REFUSALS, tiers.REFUSAL_ORDINAL, row.refusal_max, True),
            ("goal_legible", GOAL_LEGIBLE, tiers.GOAL_LEGIBLE_ORDINAL, goal_ceiling, True),
            ("danger_tell", DANGER_TELLS, tiers.DANGER_TELL_ORDINAL, row.danger_tell_max,
             hazardous),
        )
        for name, enum, ordinals, ceiling, checked in checks:
            value = knobs.get(name, _MISSING)
            # A knob that is absent belongs to missing-knobs, and a value the
            # enum does not carry belongs to schema: no piling on either.
            if not checked or not isinstance(value, str) or value not in ordinals:
                continue
            if ordinals[value] > ceiling:
                if name == "goal_legible" and ceiling < row.goal_legible_max:
                    # The batch cap is the binding constraint, not the tier
                    # table — say so, or the writer is told the wrong rule
                    # (prompt-sync's mirror: a lint message may not misname
                    # the rule that fired).
                    record(
                        "tier-knob-mismatch",
                        f"game.knobs.goal_legible is {value!r}; this batch caps it at "
                        f"{policy.goal_legible_cap!r} (tiers.goal_legible_cap — the operator's "
                        f"2026-09-29 legibility ruling: the goal must be visible, only "
                        f"structure may hide)",
                        knob_action,
                    )
                    continue
                record(
                    "tier-knob-mismatch",
                    f"game.knobs.{name} is {value!r}, harder than tier {tier} ({row.label}) "
                    f"defaults to — that tier's values are "
                    f"{_tier_enum_values(enum, ordinals, ceiling)} (difficulty-model §3.3)",
                    knob_action,
                )

    if knob_action != "off" and deceptions is not None:
        levers = _declared_levers(deceptions)
        if len(levers) > row.lever_max:
            record(
                "tier-deceptions",
                f"game.knobs.deceptions declares {len(levers)} distinct lever(s) "
                f"({', '.join(repr(lever) for lever in levers)}) — tier {tier} ({row.label}) "
                f"allows at most {row.lever_max}",
                knob_action,
            )

    pacing_action = policy.intro_pacing_action
    if pacing_action != "off" and row.intro_cap is not None and levels_usable:
        offenders = []
        for position, level in enumerate(levels[1:], 1):
            if not isinstance(level, Mapping):
                continue
            introduced = level.get("terms_introduced")
            if _is_str_list(introduced) and len(introduced) > row.intro_cap:
                offenders.append(f"level {position + 1} introduces {len(introduced)}")
        if offenders:
            record(
                "tier-intro-pacing",
                f"tier {tier} ({row.label}) introduces at most {row.intro_cap} new term(s) per "
                f"level after level 1 — {'; '.join(offenders)}",
                pacing_action,
            )
    return kills, warns


def lint_spec(
    spec: Mapping,
    vocab: Collection[str],
    idea: Mapping | None = None,
    tier_policy: tiers.TierPolicy | None = None,
    *,
    require_render: bool = False,
    rule_actions: Mapping[str, str] | None = None,
    silent_levels_floor: float | None = None,
) -> LintReport:
    """Every §11 rule over one parsed spec; PURE (no config, no disk).

    `spec` is the parsed spec.yaml (top-level key "game"). `vocab` is the
    closed term set (`load_vocab(cfg)` or its keys — anything supporting `in`).
    `idea` is the stage-0 idea dict when available: it adds the idea_ref
    cross-check (schema kill), the seed-term warn, and — with `tier_policy` —
    the tier this spec is held to.

    `tier_policy` is the PARSED `tiers:` block (`tiers.tier_policy(cfg)`),
    handed in by the caller so this function stays pure. None, or an idea with
    no tier the signed table carries, and no tier rule runs at all: the report
    is byte-for-byte the one this function has always returned.

    `require_render` is this batch's `lint.require_render` knob (contract V-B),
    handed in for the same reason `tier_policy` is: the knob lives in config
    and this function never reads config. False — every call that existed
    before the knob — lints exactly as it always has; True demands a usable
    `game.render` declaration and kills a spec without one.

    `rule_actions` is this batch's `lint.<rule>_action` map for the fidelity
    rules (contract W1-B / R-16), handed in for the same reason `tier_policy`
    is. None — and any rule left at its `off` default — reports exactly what
    this function reported before the rules existed; a batch arms them in
    `lint:` config (`warn` records, `kill` refuses).

    `silent_levels_floor` is that registry's one THRESHOLD knob (contract A2 /
    R-11), handed in on the same terms. None is the calibrated default 0.5 and
    means nothing at all while `silent-levels` sits at its `off` default; a
    value off [0, 1] is a loud ValueError.

    `spec_hash` is always "" here — this function never sees the spec TEXT, and
    a hash of a re-serialized dict would not identify the bytes stage 2 reads.
    `run_s1` sets the real text hash on the report before writing it.
    """
    actions = resolve_rule_actions(rule_actions)
    # Validated BEFORE the first rule runs, like the action map above: a bad
    # floor is a config defect and must not be discovered halfway through a
    # report.
    floor = _silent_share_limit(silent_levels_floor)
    kills: list[dict] = []
    warns: list[dict] = []
    if not isinstance(spec, Mapping):
        detail = f"spec must be a mapping with a 'game' key, got {type(spec).__name__}"
        return LintReport(False, [_finding("schema", detail)], [], "")
    if "game" not in spec:
        return LintReport(False, [_finding("schema", "spec has no top-level 'game' key")], [], "")
    game = spec["game"]
    if not isinstance(game, Mapping):
        # Nothing below can read a non-mapping: one honest kill beats fifteen
        # derived ones.
        return LintReport(
            False,
            [_finding("schema", f"spec['game'] must be a mapping, got {type(game).__name__}")],
            [],
            "",
        )
    for name in sorted(set(spec) - {"game"}):
        warns.append(_finding("unknown-field", f"spec.{name}: not a §11 top-level key (ignored)"))

    schema_kills, schema_warns = _schema_rule(game, idea, require_render=require_render)
    kills += schema_kills
    warns += schema_warns

    # Views the later rules can trust. A malformed input means schema already
    # named that offender; the derived rule stays silent rather than piling on.
    raw_terms = game.get("terms")
    terms = list(raw_terms) if _is_str_list(raw_terms) else []
    terms_usable = _is_str_list(raw_terms)
    raw_levels = game.get("levels")
    levels = list(raw_levels) if isinstance(raw_levels, list) else []
    levels_usable = isinstance(raw_levels, list)
    knobs = game.get("knobs") if isinstance(game.get("knobs"), Mapping) else None
    raw_deceptions = knobs.get("deceptions", _MISSING) if knobs is not None else _MISSING
    if _is_str_list(raw_deceptions):
        deceptions = list(raw_deceptions)
    elif raw_deceptions is _MISSING:
        deceptions = []  # nothing declared — the levers below may say so
    else:
        deceptions = None  # declared but unreadable — see _deception_rule

    if terms_usable:
        kills += _unknown_terms_rule(terms, levels, vocab)
        objective = game.get("objective")
        if isinstance(objective, Mapping):
            kills += _objective_rule(objective, terms)
    if knobs is not None:
        kills += _knobs_rule(knobs)
    if levels_usable:
        kills += _curriculum_rule(levels)
        kills += _deception_rule(levels, deceptions)
    palette = game.get("palette")
    if isinstance(palette, Mapping):
        palette_kills, palette_warns = _palette_rule(palette, deceptions or [])
        kills += palette_kills
        warns += palette_warns
    if knobs is not None and terms_usable:
        kills += _contradiction_rule(game, terms, knobs, deceptions or [])
    # The render declaration reads `render` and `layout` and nothing else, so
    # it runs on its own terms — a spec with neither block gets nothing.
    render_kills, render_warns = _render_rule(game.get("render"), game.get("layout"))
    kills += render_kills
    warns += render_warns

    if idea is not None:
        seed_terms = idea.get("seed_terms")
        if _is_str_list(seed_terms) and terms_usable:
            absent = [term for term in seed_terms if term not in set(terms)]
            if absent:
                warns.append(
                    _finding(
                        "idea-seed-terms-missing",
                        f"idea {idea.get('id')!r} seed terms absent from game.terms: {absent}",
                    )
                )

    # The fidelity rules (R-16) read the same vetted views the §11 rules do,
    # plus the idea's `mix_class` facet — the first rule in this module that
    # holds the SPEC to what the IDEA was drawn as.
    fidelity_kills, fidelity_warns = _fidelity_rules(
        game,
        idea,
        actions=actions,
        terms=terms,
        terms_usable=terms_usable,
        levels=levels,
        levels_usable=levels_usable,
        knobs=knobs,
        silent_levels_floor=floor,
    )
    kills += fidelity_kills
    warns += fidelity_warns

    # The tier contract runs LAST: it is the one policy layer here, it reads
    # only the views the §11 rules already vetted, and with no policy (or an
    # untiered idea) it adds nothing at all.
    tier = _idea_tier(idea, tier_policy)
    if tier is not None and tier_policy is not None:
        tier_kills, tier_warns = _tier_rules(
            tier,
            tier_policy,
            terms=terms,
            terms_usable=terms_usable,
            levels=levels,
            levels_usable=levels_usable,
            knobs=knobs,
            deceptions=deceptions,
        )
        kills += tier_kills
        warns += tier_warns
    return LintReport(not kills, kills, warns, "")


def escalation_lint_policy(policy: tiers.TierPolicy | None) -> tiers.TierPolicy | None:
    """The lint policy for an S2b-escalated rewrite: the term budget is OFF.

    ESCALATION_TERMS_LINE forces `game.terms` to a SUPERSET of the standing
    list plus the findings' terms — a budget kill there can make the mandated
    rewrite unsatisfiable. The budget binds at authorship; audit-forced
    declarations never bounce off it. Every other tier rule keeps running.
    """
    if policy is None:
        return None
    return replace(policy, term_budget=None)


def escalation_term_budget(
    idea: Mapping | None, policy: tiers.TierPolicy | None
) -> tuple[str, int] | None:
    """(tier, budget) the escalated rewrite is re-checked against, or None.

    None on every absence the tier rules are silent on — no policy, no idea, no
    tier the signed table carries, no armed `term_budget` — and None is what
    keeps the re-check (and its report field) off every run that has no budget
    to re-impose.
    """
    tier = _idea_tier(idea, policy)
    if tier is None or policy is None or policy.term_budget is None:
        return None
    budget = policy.term_budget.get(tier)
    return None if budget is None else (tier, budget)


def escalation_budget_overrun(
    spec: Mapping, idea: Mapping | None, policy: tiers.TierPolicy | None
) -> tuple[str, int, int] | None:
    """(tier, budget, declared) when an escalated rewrite is over its budget.

    PURE, and it reads the FULL policy — never `escalation_lint_policy`'s
    stripped one, which is the whole point: this is the second look the
    escalation path never took. An unusable `game.terms` is not an overrun
    (schema named that offender), so it returns None like every other absence.
    """
    armed = escalation_term_budget(idea, policy)
    if armed is None:
        return None
    tier, budget = armed
    game = spec.get("game") if isinstance(spec, Mapping) else None
    raw_terms = game.get("terms") if isinstance(game, Mapping) else None
    if not _is_str_list(raw_terms) or len(raw_terms) <= budget:
        return None
    return tier, budget, len(raw_terms)


def escalation_budget_findings(
    spec: Mapping, idea: Mapping | None, policy: tiers.TierPolicy | None
) -> list[dict]:
    """The ONE `escalation-term-budget` finding an unreconciled overrun earns.

    [] when the rewrite is within budget, or when no budget is armed. The
    detail interpolates TIER_TERMS_KILL_SENTENCE — the same sentence the writer
    prompt and the `tier-terms` finding carry — so the ceiling named here is
    provably the ceiling the spec was authored against.
    """
    overrun = escalation_budget_overrun(spec, idea, policy)
    if overrun is None:
        return []
    tier, budget, count = overrun
    return [
        _finding(
            ESCALATION_BUDGET_RULE,
            ESCALATION_BUDGET_FAIL_DETAIL.format(
                sentence=TIER_TERMS_KILL_SENTENCE.format(tier=tier, budget=budget), count=count
            ),
        )
    ]


# --- canon assets (read-only; every extraction fails loud) -------------------


def _docs(cfg: Mapping) -> Path:
    if "duckwm_docs" not in cfg:
        raise KeyError("config missing 'duckwm_docs' — S1 reads the canon, never guesses it")
    return Path(cfg["duckwm_docs"])


def load_spec_doctrine(cfg: Mapping) -> str:
    """tufa's SPEC prompt, whole and verbatim (D22 vendors the file).

    Unlike S0 (which cuts the idea doctrine above the marker), S1's asset is
    the entire file: every paragraph of it describes the spec we want written.
    """
    path = _docs(cfg) / DOCTRINE_MD
    if not path.is_file():
        raise FileNotFoundError(f"doctrine asset not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{path}: doctrine asset is empty")
    first = text.splitlines()[0].strip()
    if not first.startswith(DOCTRINE_FIRST_LINE):
        raise ValueError(
            f"{path}: expected the doctrine to open with {DOCTRINE_FIRST_LINE!r}, got "
            f"{first[:60]!r} — vendored file changed?"
        )
    return text


def load_crosswalk(cfg: Mapping) -> str:
    """The D28 findability crosswalk — the review response's own section."""
    path = _docs(cfg) / CROSSWALK_MD
    if not path.is_file():
        raise FileNotFoundError(f"D28 crosswalk not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if CROSSWALK_START in line), None)
    if start is None:
        raise ValueError(f"{path}: no line containing {CROSSWALK_START!r} — document changed?")
    end = next(
        (i for i, line in enumerate(lines[start:], start) if line.startswith(CROSSWALK_END)),
        None,
    )
    if end is None:
        raise ValueError(f"{path}: no line starting {CROSSWALK_END!r} after the crosswalk")
    section = "\n".join(lines[start:end]).strip()
    if not section:
        raise ValueError(f"{path}: the crosswalk section is empty")
    return section


def load_spec_schema(cfg: Mapping) -> str:
    """spec-v0.3 §11's yaml block, byte-for-byte (fences stripped)."""
    path = _docs(cfg) / SPEC_MD
    if not path.is_file():
        raise FileNotFoundError(f"spec not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    heading = next((i for i, line in enumerate(lines) if line.startswith(SPEC_SECTION_11)), None)
    if heading is None:
        raise ValueError(f"{path}: no {SPEC_SECTION_11!r} heading — spec restructured?")
    opening = next(
        (i for i, line in enumerate(lines[heading:], heading) if line.strip() == SPEC_FENCE_OPEN),
        None,
    )
    if opening is None:
        raise ValueError(f"{path}: no {SPEC_FENCE_OPEN!r} fence after {SPEC_SECTION_11!r}")
    closing = next(
        (
            i
            for i, line in enumerate(lines[opening + 1 :], opening + 1)
            if line.strip() == SPEC_FENCE_CLOSE
        ),
        None,
    )
    if closing is None:
        raise ValueError(f"{path}: the §11 {SPEC_FENCE_OPEN!r} fence is never closed")
    schema = "\n".join(lines[opening + 1 : closing]).strip("\n")
    if "game:" not in schema:
        raise ValueError(f"{path}: the §11 block has no 'game:' root — spec restructured?")
    return schema


# --- writer prompt ----------------------------------------------------------


def _idea_prose(idea: Mapping) -> tuple[str, str]:
    prose = idea.get("prose")
    if not isinstance(prose, Mapping):
        raise TypeError(f"idea prose must be a mapping, got {type(prose).__name__}")
    text = prose.get("text")
    if not _is_text(text):
        raise ValueError("idea prose.text is empty — there is no idea to specify")
    title = prose.get("title")
    return (title.strip() if _is_text(title) else str(idea.get("id"))), text.strip()


def _escalation_note(report: Mapping, slug: str, terms: Sequence[str] = (),
                     deceptions: Sequence[str] = (), baseline: str = "") -> str:
    """The §3 S2b escalation section: findings, how to resolve them, the slug.

    `report` is the LOADED `worker.verifier-report.json` (a dict, not a path).
    Every `reject_reasons` entry is rendered VERBATIM — code and detail, in the
    report's order — because the writer's job is to answer those exact strings;
    a report with no findings is the blind re-spec this path exists to prevent,
    so it raises rather than render an empty escalation.
    """
    if not isinstance(report, Mapping):
        raise TypeError(f"escalation report must be a mapping, got {type(report).__name__}")
    reasons = report.get("reject_reasons")
    if not isinstance(reasons, list) or not reasons:
        raise ValueError(
            "escalation report carries no `reject_reasons` — an escalated re-spec without the "
            "verifier's findings would rewrite the spec blind"
        )
    findings = []
    for index, reason in enumerate(reasons):
        code = reason.get("code") if isinstance(reason, Mapping) else None
        detail = reason.get("detail") if isinstance(reason, Mapping) else None
        if not _is_text(code) or not _is_text(detail):
            raise ValueError(
                f"escalation report reject_reasons[{index}] needs `code` and `detail` strings, "
                f"got {reason!r}"
            )
        findings.append(f"- `{code}` — {detail}")
    terms_lines = []
    if terms:
        terms_lines = ["", ESCALATION_TERMS_LINE.format(terms=", ".join(f"`{t}`" for t in terms))]
    if deceptions:
        terms_lines += ["", ESCALATION_DECEPTIONS_LINE.format(
            levers="; ".join(f"`{d}`" for d in deceptions))]
    if baseline.strip():
        terms_lines += ["", ESCALATION_BASELINE_HEADER, "", ESCALATION_BASELINE_DIRECTIVE, "",
                        "```yaml", baseline.strip(), "```"]
    return _note(ESCALATION_HEADER, [
        ESCALATION_INTRO,
        "",
        ESCALATION_FINDINGS_LINE,
        "",
        *findings,
        "",
        *ESCALATION_RESOLUTION_LINES,
        *terms_lines,
        "",
        ESCALATION_SLUG_LINE.format(slug=slug),
    ])


def _tier_section(idea: Mapping, policy: tiers.TierPolicy | None) -> str | None:
    """The writer prompt's tier-contract section, or None when it does not render.

    It renders only for a tiered idea under a policy that has ARMED something
    (guidance, the budget, the knob defaults or the pacing cap); a policy whose
    every tier knob is off would otherwise add a section that binds nothing.

    The term-budget sentence renders whenever the BUDGET is armed, independent
    of `prompt_guidance` — that independence IS the sync guarantee: the rule
    that can kill this spec is quoted to the writer from the same constant the
    linter's finding interpolates.
    """
    tier = _idea_tier(idea, policy)
    if tier is None or policy is None:
        return None
    armed = (
        policy.prompt_guidance
        or policy.term_budget is not None
        or policy.knob_defaults_action != "off"
        or policy.intro_pacing_action != "off"
    )
    if not armed:
        return None
    row = tiers.TIER_TABLE[tier]
    items = [TIER_SECTION_HEADER.format(tier=tier, label=row.label), row.guidance]
    budget = policy.term_budget.get(tier) if policy.term_budget is not None else None
    if budget is not None:
        items.append(TIER_TERMS_KILL_SENTENCE.format(tier=tier, budget=budget))
    if policy.knob_defaults_action != "off":
        goal_ceiling = _goal_legible_ceiling(row, policy)
        items.append(
            TIER_KNOB_DEFAULTS_LINE.format(
                refusal=_tier_enum_values(REFUSALS, tiers.REFUSAL_ORDINAL, row.refusal_max),
                goal_legible=_tier_enum_values(
                    GOAL_LEGIBLE, tiers.GOAL_LEGIBLE_ORDINAL, goal_ceiling
                ),
                danger_tell=_tier_enum_values(
                    DANGER_TELLS, tiers.DANGER_TELL_ORDINAL, row.danger_tell_max
                ),
                levers=row.lever_max,
                consequence=TIER_KNOB_CONSEQUENCE[policy.knob_defaults_action],
            )
        )
        if goal_ceiling < row.goal_legible_max:
            items.append(GOAL_LEGIBLE_CAP_LINE.format(cap=policy.goal_legible_cap))
    if policy.intro_pacing_action != "off" and row.intro_cap is not None:
        items.append(TIER_INTRO_PACING_LINE.format(cap=row.intro_cap))
    # The escalation axis rides LAST and on the SECTION's own arming, not on a
    # knob of its own: it is the tier's complexity stance, the one thing every
    # part above already assumes, and the four knobs each govern a rule while
    # this governs nothing — there is no action to take and nothing to refuse.
    # (A config with no `tiers:` block still renders no section at all, so the
    # prompt of every batch shipped to date is unchanged.)
    items.append(tiers.complexity_tier_line(tier))
    axis = escalation_axis_line(tier)
    if axis is not None:
        items.append(axis)
    return "\n\n".join(items)


def build_writer_prompt(
    cfg: Mapping,
    idea: Mapping,
    *,
    escalation: Mapping | None = None,
    escalation_slug: str | None = None,
    escalation_terms: Sequence[str] | None = None,
    escalation_deceptions: Sequence[str] | None = None,
    escalation_baseline: str | None = None,
    tier_policy: tiers.TierPolicy | None = None,
    rule_actions: Mapping[str, str] | None = None,
    silent_levels_floor: float | None = None,
) -> str:
    """Doctrine (verbatim) + our overrides. The overrides always come LAST.

    Required idea keys: id, seed_terms, prose (the same three `run_s1`
    requires). objective / failure_family / tier / mix_class are rendered when
    present and silently omitted when not — an idea may legitimately carry no
    failure-family drill, and a hand-written idea may carry no mix class.

    `escalation` is the LOADED verifier report of a §3 S2b escalation (verifier
    reject ×2 -> S1). None — every ordinary S1 call — builds exactly the prompt
    it always has, byte for byte; set, it inserts ONE extra section right after
    the idea it rewrites and before everything downstream of it. The slug that
    section pins comes from `escalation_slug` and from nowhere else: the
    report's `game_id` is the spec DIRECTORY's name (`s3_verify` is handed
    `game_id=spec_dir.name`), which is the slug only when S1 could name the dir
    after one, so the existing spec's own `game.slug` is the truth and the
    caller passes it (`run_s1` reads it off the spec being rewritten).
    `escalation_slug` alone, with no report, is ignored.

    `tier_policy` is the parsed `tiers:` block (`tiers.tier_policy(cfg)`). None
    — and any idea with no tier, or a policy with every tier knob off — renders
    NOTHING, so the prompt is byte-for-byte the one this function has always
    built. Set and armed, it inserts one `### Tier contract` section directly
    after the idea: the tier qualifies the idea, so it sits with it, while an
    escalation (which REWRITES that idea's spec) still comes after both.

    `rule_actions` is the fidelity-rule action map (contract W1-B / R-16). A
    section renders ONLY for a rule this batch armed to `kill` — prompt-sync
    for a rule that can end a writer session — so None, and the `warn` default
    every config ships today, build the prompt byte-for-byte as before.
    `silent_levels_floor` is that registry's threshold knob (contract A2), read
    only when `silent-levels` is armed to kill, for the same reason.
    """
    if not isinstance(idea, Mapping):
        raise TypeError(f"idea must be a mapping, got {type(idea).__name__}")
    if escalation is not None and not _is_text(escalation_slug):
        raise ValueError(
            f"an escalated re-spec needs `escalation_slug` (the existing spec's `game.slug`, "
            f"which the rewrite must keep), got {escalation_slug!r}"
        )
    idea_id = idea.get("id")
    if not _is_text(idea_id):
        raise ValueError(f"idea.id must be a non-empty string, got {idea_id!r}")
    seed_terms = idea.get("seed_terms")
    if not _is_str_list(seed_terms) or not seed_terms:
        raise ValueError(f"idea.seed_terms must be a non-empty list of terms, got {seed_terms!r}")
    title, text = _idea_prose(idea)

    family = idea.get("failure_family")
    if family is not None and family not in FAILURE_FAMILIES:
        raise ValueError(
            f"idea.failure_family {family!r} is not one of {list(FAILURE_FAMILIES)}"
        )

    idea_lines = [
        f"### The stage-0 idea (id: {idea_id})",
        "",
        f"**{title}** — {text}",
        "",
        "Seed terms — the §3 vocabulary this game is built from:",
    ]
    idea_lines += [f"`{term}`" for term in seed_terms]
    idea_lines.append(SEED_TERMS_LINE)
    objective = idea.get("objective")
    if isinstance(objective, Mapping) and _is_text(objective.get("primary")):
        idea_lines.append(
            f"Primary objective family: {objective['primary']} — the win condition must be the "
            f"one those terms witness."
        )
    if family is not None:
        idea_lines.append(
            f"Agent-failure drill: {family} — the spec should make THAT failure mode decide "
            f"whether a player wins, not raw execution difficulty."
        )
    mix = idea.get("mix_class") if isinstance(idea.get("mix_class"), Mapping) else {}
    facets = []
    if _is_text(idea.get("tier")):
        facets.append(f"legibility tier: {idea['tier']}")
    if isinstance(mix.get("hazardless"), bool):
        facets.append(f"hazardless: {str(mix['hazardless']).lower()}")
    if _is_text(mix.get("locus")):
        locus = LOCUS_SPEC_SPELLING.get(mix["locus"], mix["locus"])
        facets.append(f"interaction locus: {locus} (the §11 `locus` field)")
    if facets:
        idea_lines.append(" · ".join(facets) + ".")

    witness_lines = [WITNESS_HEADER, ""]
    witness_lines += [
        f"- {family_name} <- " + " or ".join(f"`{term}`" for term in WITNESS_MAP[family_name])
        for family_name in OBJECTIVE_FAMILIES
    ]
    witness_lines += ["", WITNESS_LINE]

    tier_section = _tier_section(idea, tier_policy)
    fidelity = fidelity_section(rule_actions, silent_levels_floor=silent_levels_floor)

    sections = [
        load_spec_doctrine(cfg),
        OVERRIDE_HEADER,
        "\n".join(idea_lines),
        # The tier contract qualifies the idea above (it says how legible the
        # game may be and how much vocabulary it may spend), so it rides
        # immediately after it — and before the escalation, which rewrites it.
        *([] if tier_section is None else [tier_section]),
        # The escalation sits with the idea it rewrites — after the prose that
        # says WHAT the game is, before every section that says how to write
        # one — so the writer reads "rewrite this, keep the slug" before the
        # schema, the crosswalk and the lint surface.
        *([] if escalation is None else [
            _escalation_note(escalation, escalation_slug.strip(), escalation_terms or (),
                             escalation_deceptions or (), escalation_baseline or "")
        ]),
        f"{ACTION_MAP_HEADER}\n\n{ACTION_MAP_LINE}",
        # The variety rule rides directly under the count it qualifies: how
        # many levels, and what each one must ADD (lead-authored, C-4 round).
        f"{LEVEL_COUNT_LINE}\n{LEVEL_VARIETY_LINE}",
        f"{LAYOUT_SEED_HEADER}\n\n{LAYOUT_SEED_LINE}",
        BUDGET_LINE,
        DECEPTION_WORDS_LINE,
        "\n".join(witness_lines),
        "\n".join([CROSSWALK_HEADER, "", load_crosswalk(cfg)]),
        "\n".join([SCHEMA_HEADER, "", SPEC_FENCE_OPEN, load_spec_schema(cfg), SPEC_FENCE_CLOSE]),
        NEG2_NOTATION_NOTE,
        CURRICULUM_NOTE,
        LINT_SURFACE_NOTES,
        # Last of the schema notes: it documents two fields the §11 block above
        # does not carry, and its palette paragraph points back at the
        # palette-collision note inside LINT_SURFACE_NOTES, so it must follow it.
        render_section(),
        # Directly after it (contract B1): the same standing-documentation
        # shape, for the two OTHER optional §11 fields the schema block above
        # does not carry. It follows `render_section` because its chrome
        # paragraph is about what is drawn on the field that section just
        # defined.
        chrome_section(),
        # Then the deception levers themselves (contract E-1). It follows the
        # lint surface because the `undeclared-deception` note inside it is what
        # this section defines the words of, and it is the LAST standing-doc
        # section for the same reason the other two are standing docs: every
        # config gets it and nothing already shipped becomes wrong.
        deception_section(cfg),
        # The fidelity rules ride last of the lint surface, and only when this
        # batch armed one of them to kill (see `fidelity_section`).
        *([] if fidelity is None else [fidelity]),
        REPLY_LINE,
    ]
    return "\n\n".join(sections)


# --- reply -> spec ----------------------------------------------------------

_FENCE_OPEN_RE = re.compile(r"^\s*```+\s*ya?ml\s*$", re.IGNORECASE)
_FENCE_CLOSE_RE = re.compile(r"^\s*```+\s*$")


def extract_spec_yaml(reply: str) -> tuple[str, dict]:
    """(raw text, parsed dict) of the LAST fenced ```yaml block in `reply`.

    Raises ValueError when there is no fenced yaml block, it does not parse, or
    it has no top-level `game:` mapping — all three are the SAME mechanical
    failure from `run_s1`'s point of view (retry once, then give up), never a
    lint kill.
    """
    if not isinstance(reply, str):
        raise TypeError(f"reply must be a str, got {type(reply).__name__}")
    lines = reply.splitlines()
    blocks: list[str] = []
    opening: int | None = None
    for position, line in enumerate(lines):
        if opening is None:
            if _FENCE_OPEN_RE.match(line):
                opening = position
            continue
        if _FENCE_CLOSE_RE.match(line):
            blocks.append("\n".join(lines[opening + 1 : position]))
            opening = None
    if opening is not None:
        # Unterminated final fence: take the rest of the reply. A truncated
        # reply is common and the yaml either parses or it does not.
        blocks.append("\n".join(lines[opening + 1 :]))
    if not blocks:
        raise ValueError("reply contains no fenced ```yaml block")
    raw = blocks[-1].strip("\n")
    if not raw.strip():
        raise ValueError("the last fenced ```yaml block is empty")
    raw += "\n"
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"the last fenced ```yaml block does not parse: {exc}") from exc
    # ValueError, not TypeError, for all three shapes: run_s1's retry keys on
    # exactly one exception type, and a malformed reply is one failure mode.
    if not isinstance(parsed, dict):
        raise ValueError(  # noqa: TRY004 — the retry contract is ValueError
            f"the last fenced ```yaml block parsed to {type(parsed).__name__}, expected a mapping"
        )
    if not isinstance(parsed.get("game"), dict):
        raise ValueError(  # noqa: TRY004 — the retry contract is ValueError
            "the last fenced ```yaml block has no top-level `game:` mapping "
            f"(top-level keys: {sorted(parsed)})"
        )
    return raw, parsed


def batch_of_idea_id(idea_id: str) -> str:
    """"b001-pilot-i001" -> "b001-pilot" (the corpus is laid out per batch)."""
    if not isinstance(idea_id, str) or not idea_id:
        raise ValueError(f"idea id must be a non-empty string, got {idea_id!r}")
    batch, separator, tail = idea_id.rpartition("-i")
    if not separator or not batch or not (tail.isascii() and tail.isdigit()):
        raise ValueError(
            f"idea id {idea_id!r} does not end in '-i<digits>' — cannot derive its batch id"
        )
    return batch


# --- run --------------------------------------------------------------------


# {yaml_path}/{md_path} are ABSOLUTE: the first session run wrote its files
# into its own harness scratchpad because "the current directory" lost to
# the CLI's temporary-files convention (B5 record). Deliverables get
# absolute paths, always.
SESSION_REPLY_TEMPLATE = (
    "Do NOT print the documents in your reply, and do NOT plan at length "
    "before writing. These two files are DELIVERABLES (not temporary files "
    "— never use a scratchpad; write them at exactly these absolute paths). "
    "Work in THIS order, starting immediately: (1) write `{yaml_path}` — "
    "ONLY the completed `game:` yaml mapping, no code fences; (2) write "
    "`{md_path}` section by section, saving after EVERY section (game "
    "overview first, then one section per level, then visuals and solver "
    "notes); (3) re-read the yaml once against the schema and fix anything "
    "off; (4) reply with exactly DONE. Draft decisively — the pipeline's "
    "linter and verifier are the quality gates, and an unfinished spec is "
    "worth nothing."
)
S1_SCRATCH_ROOT = REPO_ROOT / "out" / "tmp"
#: Per-process, per-call uniqueness for the writer scratch (contract P-5 §8).
#: The stamp alone is a WALL-CLOCK SECOND, so two writers starting in the same
#: second — two slots of one parallel batch, or two escalations in one run —
#: named the same directory and, under `exist_ok=True`, silently shared it:
#: same `spec.yaml`, same cwd, two sessions. The pid separates processes and
#: this counter separates calls inside one; `exist_ok` is gone, so a collision
#: that survives both is a loud FileExistsError instead of a corrupt spec.
_WRITER_SCRATCH_SEQ = itertools.count(1)
S1_WRITER_TOOLS = ("Write", "Edit", "Read")
# The writer's deliberation FLOOR, not its setting (P-1a addendum 1). Three real
# attempts at the CLI's own default effort sank 30+ minutes into thinking and
# emitted nothing (B5 record), so `None` — which is what
# `backends.SESSION_POLICY_DEFAULTS["localclaude"]["effort"]` means, "omit the
# flag" — must never reach this session. A config that sets the knob steers the
# writer; a config that leaves it unset gets this, which is exactly what the
# writer ran at before the knob was consulted here at all.
S1_WRITER_EFFORT_FLOOR = "medium"


def _default_writer_runner(cfg: Mapping) -> Callable[[str], str]:
    """The real S1 runner: a file-writing `spec_writer` SESSION per idea.

    Three real attempts proved a single-shot completion is the wrong shape
    for a doctrine-dense spec: headless claude either wandered the repo with
    tools (fixed — `complete()` is tool-less now) or generated/thought past
    every reasonable single-completion wall (900s, 2x 1800s, empty partial
    output). A session in an EMPTY scratch directory with Write/Edit/Read
    only writes the two documents incrementally — the shape headless agents
    are good at, with progress observable on disk. The runner returns the
    canonical "reply" (spec.md text + fenced yaml block) so
    `extract_spec_yaml` and everything after it stay unchanged.

    `gen.backends` is imported HERE, not at module import: an injected fake
    never needs a driver (or a logged-in CLI) to exist.
    """
    from .backends import (
        SESSION_POLICY_DEFAULTS,
        SESSION_TIMEOUT_S,
        get_driver,
        get_session_policy,
    )

    driver, model = get_driver(cfg, "spec_writer")
    # P-1a item 5. The session CEILING is the driver POLICY's, not a hardcode:
    # `backends.<driver>.session.timeout_s` (armed by the b004 ruling) reached
    # S2 and S3 and never reached here, so a config that raised the ceiling
    # still clipped the writer at 1800s. Same shape as the verifier's fix
    # (gen/s3_verify.py, b004 finding #2): ONLY the keys S1 has no opinion
    # about come from the policy. Unconfigured the policy IS 1800.0
    # (backends.SESSION_POLICY_DEFAULTS), so an unconfigured run is
    # byte-identical; an unknown driver keeps the code default rather than
    # silently losing its ceiling.
    policy = (
        get_session_policy(cfg, driver.name)
        if driver.name in SESSION_POLICY_DEFAULTS
        else {}
    )
    timeout_s = policy.get("timeout_s", SESSION_TIMEOUT_S)

    def run(prompt: str) -> str:
        scratch = S1_SCRATCH_ROOT / (
            f"s1-writer-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
            f"-p{os.getpid()}-{next(_WRITER_SCRATCH_SEQ):03d}"
        )
        scratch.mkdir(parents=True)
        session_line = SESSION_REPLY_TEMPLATE.format(
            yaml_path=scratch / "spec.yaml", md_path=scratch / "spec.md"
        )
        session_prompt = prompt.replace(REPLY_LINE, session_line)
        if session_line not in session_prompt:
            session_prompt = f"{prompt}\n\n{session_line}"
        kwargs: dict = {"cwd": scratch, "model": model, "timeout_s": timeout_s}
        if driver.name == "localclaude":
            # BOTH flags: `tools` limits the surface to file work (without it
            # the writer explored the repo over Bash — B5 record);
            # `allowed_tools` auto-approves that surface.
            # The TOOL surface stays HARDCODED on purpose (P-1a item 5): it is
            # a STAGE decision with a recorded incident behind it, and the
            # policy it would otherwise come from is S2's EDIT-mode policy —
            # taking `allowed_tools` from there would hand a doc writer Bash.
            kwargs["tools"] = S1_WRITER_TOOLS
            kwargs["allowed_tools"] = S1_WRITER_TOOLS
            # Cap deliberation: at default effort the writer sank 30+ minutes
            # into thinking without a byte of output (B5 record). The linter
            # and the S3 verifier are the quality gates, not marathon thought.
            # P-1a addendum 1 (the blind lane's flagged ambiguity, adjudicated):
            # the CONFIGURED value steers the writer, exactly as it steers S2
            # off the same key — but `None`, the policy default, is FLOORED to
            # S1_WRITER_EFFORT_FLOOR rather than passed on, so an unconfigured
            # run still sends `--effort medium` and the B5 failure cannot
            # reopen through a knob nobody set.
            kwargs["effort"] = policy.get("effort") or S1_WRITER_EFFORT_FLOOR
        elif driver.name == "codex":
            # codex `session()` takes no tool list; the sandbox IS its scoping
            # (gen/s3_verify.py makes the same call for the verifier, read-only
            # there because that pass may not write). The WRITER must write —
            # spec.yaml and spec.md below are its deliverables — so the policy
            # value stands: `workspace-write` unconfigured, rooted at `scratch`
            # and nothing else. `effort` rides only when configured; None omits
            # the flag, which is what keeps the lane's argv byte-identical.
            kwargs["sandbox"] = policy["sandbox"]
            if policy.get("effort") is not None:
                kwargs["effort"] = policy["effort"]
        driver.session(session_prompt, **kwargs)
        md_path = scratch / "spec.md"
        yaml_path = scratch / "spec.yaml"
        if not md_path.is_file() or not yaml_path.is_file():
            present = sorted(p.name for p in scratch.iterdir())
            raise ValueError(
                f"S1 writer session ended without both files (found {present} in {scratch})"
            )
        md_text = md_path.read_text(encoding="utf-8").strip()
        yaml_text = yaml_path.read_text(encoding="utf-8").strip()
        # Canonical reply shape: prose, then ONE fenced yaml block — exactly
        # what extract_spec_yaml expects, so the rest of run_s1 is unchanged.
        return f"{md_text}\n\n```yaml\n{yaml_text}\n```\n"

    return run


def _lint_require_render(cfg: Mapping) -> bool:
    """`lint.require_render` — this batch's render-declaration knob (V-B).

    It DEFAULTS: every config written before the knob existed (and every future
    config that does not care) lints exactly as it did, which is what makes the
    field optional rather than a flag day. A non-bool is a loud ValueError,
    read before the driver call like the rest.

    (`lint.strict`, which used to sit above this reader, is GONE — contract
    D-3 §2. It was hard-required of every config and stamped into every
    lint-report.json, and no linter rule ever read it: there is exactly one
    §11 linter and it is strict. A knob that only ever recorded itself was
    read as a live switch by everyone who saw it in a config.)
    """
    lint = cfg.get("lint")
    value = lint.get("require_render", False) if isinstance(lint, Mapping) else False
    if not isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 — contract V-B §2 pins ValueError for this knob
            f"lint.require_render must be a bool, got {value!r} — it arms a §11 schema kill"
        )
    return value


def lint_rule_actions(cfg: Mapping) -> dict[str, str]:
    """`lint.<rule>_action` per fidelity rule (contract W1-B / R-16).

    Every key DEFAULTS to `off` (lead correction; see FIDELITY_DEFAULT_ACTION),
    so a config that never heard of these rules lints and reports exactly as it
    did before them — the byte-identity the shipped-report parity pin enforces.
    `config/template.yaml` arms all three at `warn`, which is where the audit's
    measurement pass actually happens. A value off the enum is a loud
    ValueError read before the driver call, like `_lint_require_render` and the
    `tiers:` block: a knob nobody validated is how an inert knob is born.
    """
    lint = cfg.get("lint") if isinstance(cfg, Mapping) else None
    raw = lint if isinstance(lint, Mapping) else {}
    actions: dict[str, str] = {}
    for rule, key in FIDELITY_ACTION_KEYS.items():
        value = raw.get(key, FIDELITY_DEFAULT_ACTION)
        if value not in FIDELITY_ACTIONS:
            raise ValueError(
                f"lint.{key} must be one of {list(FIDELITY_ACTIONS)}, got {value!r} — it governs "
                f"the {rule!r} lint rule"
            )
        actions[rule] = value
    return actions


def lint_silent_levels_floor(cfg: Mapping) -> float:
    """`lint.silent_levels_floor` — the `silent-levels` threshold (A2 / R-11).

    Absent is the calibrated default (`SILENT_LEVELS_FLOOR_DEFAULT`), which is
    inert while the rule sits at its `off` action; a value off [0, 1] is the
    same loud ValueError `_silent_share_limit` raises everywhere else,
    read before the driver call like every other config read in this module.
    """
    lint = cfg.get("lint") if isinstance(cfg, Mapping) else None
    raw = lint if isinstance(lint, Mapping) else {}
    return _silent_share_limit(raw.get(SILENT_LEVELS_FLOOR_KEY))


def _load_idea(idea_path: Path) -> tuple[dict, bytes]:
    if not idea_path.is_file():
        raise FileNotFoundError(f"idea not found: {idea_path}")
    payload = idea_path.read_bytes()
    try:
        idea = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{idea_path}: not valid JSON: {exc}") from exc
    if not isinstance(idea, dict):
        raise ValueError(  # noqa: TRY004 — idea-shape failures are ValueError by contract
            f"{idea_path}: idea must be a JSON object, got {type(idea).__name__}"
        )
    missing = [key for key in ("id", "seed_terms", "prose") if key not in idea]
    if missing:
        raise ValueError(f"{idea_path}: idea missing required key(s) {missing}")
    return idea, payload


def _spec_slug(spec: Mapping) -> str | None:
    """`game.slug`, stripped — None when the document carries no usable one.

    The IDENTITY check (`_slug_dir_name` is the directory-safety one): an
    escalated re-spec compares this against the slug it must keep.
    """
    game = spec.get("game") if isinstance(spec, Mapping) else None
    slug = game.get("slug") if isinstance(game, Mapping) else None
    return slug.strip() if isinstance(slug, str) and slug.strip() else None


def _load_escalation(report_path: Path) -> tuple[dict, str, list[str], list[str], str]:
    """(verifier report, the slug to keep, the terms floor) for a §3 escalation.

    The report is the worker's SIBLING inside the spec dir
    (`…/<slug>/worker.verifier-report.json`), so the spec being rewritten is
    `report_path.parent / "spec.yaml"` and its `game.slug` is the slug — ONE
    source, and it is the existing spec's own field. The report's `game_id` is
    deliberately NOT that source: `s3_verify` is handed `game_id=spec_dir.name`,
    the directory name, which equals the slug only when S1 could name the dir
    after one (a spec with no usable slug lands in `<idea id>-unnamed`).
    """
    report_path = Path(report_path)
    if not report_path.is_file():
        raise FileNotFoundError(f"escalation verifier report not found: {report_path}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{report_path}: not valid JSON: {exc}") from exc
    if not isinstance(report, dict):
        raise ValueError(  # noqa: TRY004 — report-shape failures are ValueError, as for ideas
            f"{report_path}: verifier report must be a JSON object, got {type(report).__name__}"
        )
    spec_path = report_path.parent / "spec.yaml"
    if not spec_path.is_file():
        raise FileNotFoundError(
            f"escalated re-spec has no spec to rewrite: {spec_path} — the report at "
            f"{report_path} does not sit in a spec dir"
        )
    existing = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    slug = _spec_slug(existing if isinstance(existing, Mapping) else {})
    if slug is None:
        raise ValueError(
            f"{spec_path}: no usable `game.slug` — an in-place re-spec has no slug to keep"
        )
    # The existing spec's declared terms — the rewrite's UNION floor. The
    # pilot's rounds 3-5 oscillated because each rewrite declared the latest
    # findings and EVICTED the standing declarations (nothing flags a term
    # that is currently declared, so the writer never saw them); the next
    # audit then flagged the evicted set. The live spec is lint-passed by
    # invariant, so `terms` is a list of vocabulary strings; tolerate absence
    # with [] rather than dying one step before the prompt that fixes it.
    game = existing.get("game") if isinstance(existing, Mapping) else None
    raw_terms = game.get("terms") if isinstance(game, Mapping) else None
    terms = [t for t in raw_terms if _is_text(t)] if isinstance(raw_terms, list) else []
    knobs = game.get("knobs") if isinstance(game, Mapping) else None
    raw_levers = knobs.get("deceptions") if isinstance(knobs, Mapping) else None
    levers = [d for d in raw_levers if _is_text(d)] if isinstance(raw_levers, list) else []
    return report, slug, terms, levers, spec_path.read_text(encoding="utf-8")


def _slug_dir_name(spec: Mapping, idea_id: str) -> str:
    """The spec's slug, or an audit-safe stand-in.

    A killed spec still has to land somewhere: when the slug is missing, not a
    string, or not usable as a single directory name, the artifacts go to
    `<idea id>-unnamed` and the schema kill says the rest.
    """
    game = spec.get("game")
    slug = game.get("slug") if isinstance(game, Mapping) else None
    if isinstance(slug, str):
        slug = slug.strip()
        if slug and slug not in (".", "..") and "/" not in slug and "\\" not in slug:
            return slug
    return f"{idea_id}-unnamed"


def _write_bytes_atomic(path: Path, payload: bytes) -> Path:
    """Write `payload` so a concurrent reader sees either all of it or none.

    The tmp name carries the pid because two processes writing the same target
    must not share a staging file (contract P-5); `os.replace` is atomic within
    a filesystem and both names live in the same directory.
    """
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(payload)
    os.replace(tmp, path)
    return path


def run_s1(
    idea_path: Path,
    cfg: Mapping,
    *,
    writer_runner: Callable[[str], str] | None = None,
    out_root: Path | None = None,
    escalation: Path | None = None,
) -> S1Result:
    """idea.json -> prompt -> writer -> spec.yaml + spec.md + lint-report.json.

    `writer_runner(prompt) -> reply text`; None builds the configured
    `spec_writer` driver. One retry on a malformed reply (no parsable fenced
    yaml block); a second failure raises RuntimeError — that is a MECHANICAL
    failure, distinct from a lint kill, and never writes artifacts.

    A lint KILL is not a failure here: all four artifacts are written and the
    report carries the verdict.

    `escalation` is the path to a `worker.verifier-report.json` when §3 S2b
    escalated this slot (verifier reject ×2 -> S1). It makes the run an
    IN-PLACE REWRITE: the report's findings go into the prompt, the slug of the
    spec beside that report is pinned, and the writer's slug is ENFORCED after
    parsing — one corrective retry, then a RuntimeError (mechanical failure,
    loud), because a drifted slug writes a SECOND spec dir for one idea. With
    the slug held, the four artifacts land in the dir that already exists; the
    `worker/` subtree and the `worker.*` siblings beside it are not touched.

    The `tiers:` block (contract T-B) is parsed ONCE here and reaches both
    halves — the prompt's tier-contract section and every lint of the run. On
    the escalation path the linter runs under `escalation_lint_policy`, i.e.
    with the term budget off: ESCALATION_TERMS_LINE mandates a SUPERSET of the
    standing terms, so a budget kill there could make the ordered rewrite
    unsatisfiable. No `tiers:` block means no policy and no behavior change.

    R-17 (contract W1-B) closes what that exemption left open. After an
    escalated rewrite lints clean under the stripped policy, a SECOND,
    budget-only re-check runs under the FULL one. Over budget buys exactly one
    reconciliation turn (`ESCALATION_BUDGET_REMINDER`: fold or trim, keep every
    term the findings named), because the audit's constraint is that a bare bar
    deadlocks "declare it" against "you are over budget". Still over after that
    turn and the overrun is recorded as an `escalation-term-budget` finding —
    a KILL under `tiers.term_budget_action: kill` (every config shipped to
    date), a warn under `warn`, because this re-check re-imposes the batch's
    own budget rule and may not be harsher than the authorship it mirrors. The
    report records which path the spec took in `escalation_budget_recheck`.
    """
    idea_path = Path(idea_path)
    idea, idea_bytes = _load_idea(idea_path)
    # ONE read of the knob per run, and it reaches EVERY lint below — the first
    # pass and the escalation's lint-kill retry alike. A rewrite that dropped
    # its `render` block would otherwise pass a lint its baseline could not.
    # Read before a driver call is spent, like every config read in this runner.
    require_render = _lint_require_render(cfg)
    # The fidelity-rule knobs, read ONCE on the same terms (W1-B / R-16), and
    # `silent-levels`' floor with them (A2 / R-11) — one read, every lint and
    # both prompt paths below.
    rule_actions = lint_rule_actions(cfg)
    silent_floor = lint_silent_levels_floor(cfg)
    # The `tiers:` block, parsed ONCE per run (absent -> None; every key
    # fail-loud, before the driver call, like `require_render` above).
    policy = tiers.tier_policy(cfg)
    # ONE lint policy for every lint of this run, first pass and retry alike.
    lint_policy = policy if escalation is None else escalation_lint_policy(policy)
    vocab = load_vocab(cfg)
    if escalation is None:
        required_slug = None
        prompt = build_writer_prompt(cfg, idea, tier_policy=policy, rule_actions=rule_actions,
                                     silent_levels_floor=silent_floor)
    else:
        report, required_slug, floor_terms, floor_levers, baseline = _load_escalation(
            Path(escalation))
        # LEAD FIX (T-B review): the escalated PROMPT gets the same stripped
        # policy the escalated LINT runs under. The full policy here told the
        # rewrite "at most N terms" while ESCALATION_TERMS_LINE mandated a
        # superset of the standing list — contradictory instructions on the
        # one path where a confused writer costs a whole lap. Prompt and lint
        # share one policy object on BOTH paths, by construction.
        prompt = build_writer_prompt(cfg, idea, escalation=report, escalation_slug=required_slug,
                                     escalation_terms=floor_terms,
                                     escalation_deceptions=floor_levers,
                                     escalation_baseline=baseline, tier_policy=lint_policy,
                                     rule_actions=rule_actions,
                                     silent_levels_floor=silent_floor)
    runner = writer_runner or _default_writer_runner(cfg)

    reply = runner(prompt)
    try:
        spec_text, spec = extract_spec_yaml(reply)
    except ValueError as first:
        retry_reply = runner(prompt + RETRY_REMINDER)
        try:
            spec_text, spec = extract_spec_yaml(retry_reply)
        except ValueError as second:
            raise RuntimeError(
                f"S1 writer produced no usable spec yaml for {idea['id']} after a retry "
                f"(first: {first}; retry: {second})"
            ) from second
        reply = retry_reply

    if required_slug is not None:
        # Same turn/retry shape as the malformed-reply path above: one
        # corrective turn naming the violation, then a loud mechanical failure.
        drifted = _spec_slug(spec)
        if drifted != required_slug:
            retry_reply = runner(prompt + SLUG_REMINDER.format(
                required=required_slug,
                got=f"`{drifted}`" if drifted is not None else "no usable `game.slug` at all",
            ))
            try:
                spec_text, spec = extract_spec_yaml(retry_reply)
            except ValueError as exc:
                raise RuntimeError(
                    f"S1 escalated re-spec for {idea['id']} produced no usable spec yaml on the "
                    f"slug-correction retry (required slug {required_slug!r}): {exc}"
                ) from exc
            reply = retry_reply
            again = _spec_slug(spec)
            if again != required_slug:
                raise RuntimeError(
                    f"S1 escalated re-spec for {idea['id']} drifted the slug: the in-place "
                    f"rewrite must keep slug {required_slug!r}, the writer returned {drifted!r} "
                    f"and then {again!r} — a new slug writes a SECOND spec dir for one idea"
                )

    out_dir = Path(out_root or CORPUS_ROOT) / batch_of_idea_id(idea["id"]) / _slug_dir_name(
        spec, idea["id"]
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    report = lint_spec(
        spec, set(vocab), idea, tier_policy=lint_policy, require_render=require_render,
        rule_actions=rule_actions, silent_levels_floor=silent_floor,
    )
    if escalation is not None and not report.passed:
        # One corrective turn on a lint kill — the same one-retry idiom as the
        # slug and malformed-reply paths above. An escalated rewrite is surgery
        # on a spec we otherwise want, and the pilot's first informed re-spec
        # died on two one-line misses (a dropped mandatory field + one
        # undeclared sketch word). The retry's verdict stands either way.
        kills = "\n".join(f"- {k['rule']}: {k['detail']}" for k in report.kills)
        retry_reply = runner(prompt + LINT_KILL_REMINDER.format(kills=kills))
        try:
            retry_text, retry_spec = extract_spec_yaml(retry_reply)
        except ValueError as exc:
            raise RuntimeError(
                f"S1 escalated re-spec for {idea['id']} produced no usable spec yaml on the "
                f"lint-kill retry: {exc}"
            ) from exc
        if required_slug is not None and _spec_slug(retry_spec) != required_slug:
            raise RuntimeError(
                f"S1 escalated re-spec for {idea['id']} drifted the slug on the lint-kill "
                f"retry: required {required_slug!r}, got {_spec_slug(retry_spec)!r}"
            )
        reply, spec_text, spec = retry_reply, retry_text, retry_spec
        report = lint_spec(
            spec, set(vocab), idea, tier_policy=lint_policy, require_render=require_render,
            rule_actions=rule_actions, silent_levels_floor=silent_floor,
        )

    # R-17: the budget the escalation lint switched off, re-imposed on the spec
    # that is about to SHIP. It runs only for a rewrite that otherwise passes —
    # a killed one is already routed to `.killed/` below, and spending a writer
    # turn reconciling a spec nobody will implement buys nothing.
    if (
        escalation is not None
        and report.passed
        and escalation_term_budget(idea, policy) is not None
    ):
        report.escalation_budget_recheck = ESCALATION_RECHECK_RAN
        overrun = escalation_budget_overrun(spec, idea, policy)
        if overrun is not None:
            tier, budget, count = overrun
            reconcile = ESCALATION_BUDGET_REMINDER.format(
                sentence=TIER_TERMS_KILL_SENTENCE.format(tier=tier, budget=budget), count=count
            )
            retry_reply = runner(prompt + reconcile)
            try:
                retry_text, retry_spec = extract_spec_yaml(retry_reply)
            except ValueError as exc:
                raise RuntimeError(
                    f"S1 escalated re-spec for {idea['id']} produced no usable spec yaml on the "
                    f"budget-reconciliation retry: {exc}"
                ) from exc
            if required_slug is not None and _spec_slug(retry_spec) != required_slug:
                raise RuntimeError(
                    f"S1 escalated re-spec for {idea['id']} drifted the slug on the "
                    f"budget-reconciliation retry: required {required_slug!r}, got "
                    f"{_spec_slug(retry_spec)!r}"
                )
            reply, spec_text, spec = retry_reply, retry_text, retry_spec
            # The reconciled rewrite is a WHOLE new spec: it is re-linted in
            # full (under the same stripped policy, so the reconciliation is
            # not judged by the budget twice over), and that verdict stands.
            report = lint_spec(
                spec, set(vocab), idea, tier_policy=lint_policy, require_render=require_render,
                rule_actions=rule_actions, silent_levels_floor=silent_floor,
            )
            findings = escalation_budget_findings(spec, idea, policy)
            report.escalation_budget_recheck = (
                ESCALATION_RECHECK_FAILED if findings else ESCALATION_RECHECK_RECONCILED
            )
            if findings:
                # The batch's own budget action decides, exactly as it does at
                # authorship: a config that only RECORDS an over-budget spec
                # may not have its escalations killed by the mirror of that
                # rule. Under `kill` — every config shipped to date — the
                # loophole is closed and the rewrite does not ship.
                if policy is not None and policy.term_budget_action == "kill":
                    report.kills += findings
                    report.passed = False
                else:
                    report.warns += findings
    report.spec_hash = hashlib.sha256(spec_text.encode("utf-8")).hexdigest()

    if escalation is not None and not report.passed:
        # Write-through-staging: a KILLED escalated rewrite must never evict
        # the live spec (the ledger claims its hash and the worker implements
        # it — the pilot lost exactly that spec to a killed rewrite once).
        # The evidence lands under .killed/ beside the archive family.
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        out_dir = out_dir.parent / KILLED_DIRNAME / f"{out_dir.name}-respec-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ATOMIC, and only this one of the four (contract P-5 §7): the orchestrator's
    # `_discover_spec_dir` scans the SHARED corpus dir and bare-`json.loads`es
    # every candidate's idea.json to find the dir that claims a slot's idea. Under
    # parallel slots that scan runs while a sibling is writing its own copy, and a
    # half-written file there is a crash in another slot's run. tmp + os.replace
    # closes the window; the other three artifacts are read only by the slot that
    # wrote them.
    _write_bytes_atomic(out_dir / "idea.json", idea_bytes)
    (out_dir / "spec.md").write_text(reply, encoding="utf-8")
    (out_dir / "spec.yaml").write_text(spec_text, encoding="utf-8")
    (out_dir / "lint-report.json").write_text(
        json.dumps(
            {
                # No `strict` field: contract D-3 §2 removed the knob that
                # stamped it (the §11 linter has always been the only one).
                **report.to_json_dict(),
                "idea_ref": idea["id"],
                "ts": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return S1Result(spec_text=spec_text, spec=spec, report=report, out_dir=out_dir, prompt=prompt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S1 spec writer + §11 linter")
    parser.add_argument("--idea", required=True, help="stage-0 idea.json")
    parser.add_argument("--config", default="config/b001-pilot.yaml")
    parser.add_argument("--out", default=str(CORPUS_ROOT), help="corpus root")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    result = run_s1(Path(args.idea), cfg, out_root=Path(args.out))
    report = result.report
    if report.passed:
        print("[s1] PASS")
    else:
        rules = ", ".join(sorted({kill["rule"] for kill in report.kills}))
        print(f"[s1] KILL: {rules}")
    print(f"[s1] out: {result.out_dir}")
    for warn in report.warns:
        print(f"[s1] warn  {warn['rule']}: {warn['detail']}")
    for kill in report.kills:
        print(f"[s1] kill  {kill['rule']}: {kill['detail']}")
    return 0 if report.passed else 2


if __name__ == "__main__":
    sys.exit(main())
