"""The visual affordance grammar the S2 payload carries (contract V-A).

A generated game has to LOOK like an official one, and the corpus study that
measured how officials look — `design/objects/affordance-language.md`, signed
2026-09-18 — reached the implementer through exactly one door until now:
`canon_docs.load_forbidden_quotes` lifted its §8 FORBIDDEN contracts. The rest
of the study is the measured render grammar (who "you" is, how a goal is drawn,
how danger tells, how a meter anchors, what a refusal costs, what each palette
index means) and it was sitting unread. This module is the door for the rest of
it, plus three things the study does not itself state.

Five blocks ride into the prompt from here, every one of them a STANDING rule
with no config knob — the `s2_implement.VISUAL_LEGIBILITY` pattern:

* `visual_grammar_section` — §§1/2/(3)/5/6/9 quoted VERBATIM through
  `canon_docs.load_affordance_sections`, each with its own line cite, closed by
  one echo line per §5 knob the spec actually declares. §3 (Danger) rides only
  when the spec has danger to render.
* `corpus_numbers_card` — the six measured numbers of
  `OFFICIAL_VISUAL_CONSTANTS`, rendered as render TARGETS, never as gates.
* `VISUAL_CRAFT` — render craft the corpus study never states, distilled from
  the reference pipeline's own prompts.
* `FLOOR_AND_FOOTPRINT` — the two rules the comparative audit measured us
  failing (R-01 paint the field / reserve white-0, R-02 multi-tile footprints
  for load-bearing state), as REQUIRED rows with §9 anchors. The gate measures
  the same two things (`s3_visual` `field-index` / `role-footprint`).
* `WIN_IS_RENDERED` — the third measured failure (R-04): the winning board
  carries no signal in four of our seven shipped games. One REQUIRED row
  carrying the floor `s3_visual` `win-render` enforces, interpolated from
  `WIN_RENDER_FLOOR_CELLS` so the number the writer is told is the number the
  gate reads.
* `density_section(tier)` — the officials' per-level `objects_pcc` figures
  (contract T-1) and the TIER-AWARE line under them: t1 simplicity is
  mechanical, not visual sparseness. Interpolated from `OFFICIAL_DENSITY`, the
  block `s3_visual`'s `density` card band is cut from; the tier comes from
  `spec_tier`, the one reader both consumers share.
* `TEACHING_BY_SHOWING` — the six frame-verified ways the official corpus
  teaches level 1, one bestiary cite per idiom.

GEN (`cfg["duckwm_docs"]`, READ-ONLY) and the officials' feature tables beside
it are the source of every number and every idiom below; this module owns no
visual judgement of its own. Nothing here is paraphrase-and-hope: a quoted
section carries its heading line and the line it starts on, and a number
carries the CSV column it was measured from.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import yaml

from .canon_docs import load_affordance_sections
from .s1_spec import HAZARD_PREFIXES, REFUSAL_TRANSIENT_FIELD
from .tiers import TIERS

# --- the corpus numbers (the `s3_gate.FLOORS` idiom) ------------------------
# Measured, not chosen — and a value is worth nothing without the measurement
# behind it, so every key carries its column in `OFFICIAL_VISUAL_SOURCES`. The
# two tables are the manual-play corpus's own feature extraction over the 25
# officials; their column semantics are `features-schema.md` at that tree root.
# Kept in ONE block for the same reason `FLOORS` is: when the manual-play
# corpus grows, these move in one edit.

OFFICIAL_GAMES = 25  # rows in features-game.csv — the population, not a measurement

OFFICIAL_VISUAL_CONSTANTS: dict[str, int | tuple[float, ...]] = {
    "tile_scale_menu": (1, 2, 3, 4, 5, 8),
    "native_64_count": 13,
    "l1_colors": (4, 7, 11),
    "board_colors_median": (4.5, 9.0, 12.5),
    "objects_median": (9.5, 53.5, 219.0),
    "default_fps": (3, 30),
}

_GAMES_CSV = "duckWM/local-docs/arc-agi-3-games/templates/features-game.csv"
_LEVELS_CSV = "duckWM/local-docs/arc-agi-3-games/templates/features-level.csv"
_SCHEMA_MD = "duckWM/local-docs/arc-agi-3-games/features-schema.md"

OFFICIAL_VISUAL_SOURCES: dict[str, str] = {
    "tile_scale_menu": (
        f"{_GAMES_CSV} column `tile_scale` — the distinct values over all "
        f"{OFFICIAL_GAMES} rows; the schema ({_SCHEMA_MD}) defines it as `64 // board_w`, "
        f"which is why the menu is exactly the divisors the camera admits"
    ),
    "native_64_count": (
        f"{_GAMES_CSV} columns `board_w`/`board_h` — rows with a 64x64 board, every one of "
        f"them at `tile_scale` 1. NOT the tile_scale-1 count, which is 16: ka59 (45x45), "
        f"tu93 (39x39) and dc22 (64x44) also draw at scale 1 on a smaller native board"
    ),
    "l1_colors": (
        f"{_LEVELS_CSV} column `colors`, the {OFFICIAL_GAMES} rows with `level` == 1 — "
        f"min / median / max distinct palette indices on a level-1 board"
    ),
    "board_colors_median": (
        f"{_GAMES_CSV} column `colors_median` (each game's median over its own levels) — "
        f"min / median / max of those {OFFICIAL_GAMES} per-game medians"
    ),
    "objects_median": (
        f"{_GAMES_CSV} column `objects_median` (each game's median over its own levels) — "
        f"min / median / max of those {OFFICIAL_GAMES} per-game medians"
    ),
    "default_fps": (
        f"{_GAMES_CSV} column `default_fps` — min / max over the {OFFICIAL_GAMES} rows "
        f"(ten distinct rates in between; the corpus does not cluster)"
    ),
}

# The registry and the numbers are one contract: a key without a citation is a
# number nobody can re-measure, and a citation without a key is dead prose.
_missing_sources = sorted(set(OFFICIAL_VISUAL_CONSTANTS) - set(OFFICIAL_VISUAL_SOURCES))
_stale_sources = sorted(set(OFFICIAL_VISUAL_SOURCES) - set(OFFICIAL_VISUAL_CONSTANTS))
if _missing_sources or _stale_sources:
    raise ValueError(
        f"OFFICIAL_VISUAL_CONSTANTS and OFFICIAL_VISUAL_SOURCES disagree "
        f"(uncited {_missing_sources}, orphan citations {_stale_sources}) — every pinned "
        f"corpus number must name the column it was measured from"
    )

# --- render craft (distilled, NOT quoted) -----------------------------------
# Distilled from GEN/third-party/re-arc-3/codex_check_visual_prompt.md:31-36
# and spec_prompt.md "## Visual" — distilled, not quoted: that pipeline's
# derived 6x action-budget rule contradicts BUDGET_HEADROOM and must never
# enter this payload.
VISUAL_CRAFT = """\
## Visual craft — distilled render rules from the reference pipeline

- The board's cell structure is bookkeeping and stays invisible: no
  internal grid lines, no outline around every cell, no alternating
  checker fill, no lattice laid over the field. Paint the floor and the
  objects; the player reads the cells from them. The one exception is a
  spec that names a visible grid as something the player must use.
- Render entities as connected multi-tile shapes (2x2, 2x3, 3x3, or longer
  patterned structures), not lone 1x1 colored squares, unless the idea
  absolutely requires a tiny token.
- Use a restrained, harmonious palette: quiet neutral colors for
  background and structure, only a few saturated gameplay colors at once.
  Colors that must be compared must be clearly distinct at a glance.
- Judge every level by its first frame. Each object needs room to stand
  apart from its neighbours, and the goal should be something a player
  can point at before moving. A board that fails either test has a
  layout defect, however sound the rules beneath it: fix placement and
  spacing, not the mechanics.
- Keep animations sparse: a simple one-cell move renders at most one
  intermediate frame plus the final frame; success and refusal feedback
  is brief (one or two frames). Animate only what teaches causality.
- Before you finish, render your own per-level frames and look at them. A
  cramped, merged, or grid-lined board is a defect to fix, not a style
  choice."""

# --- the floor and the footprint (refinement wave 1, R-01 + R-02) -----------
# ONE block for both rules, deliberately: R-01 (paint the field, keep white-0
# for marks) and R-02 (draw load-bearing state in multi-tile shapes) are the
# same instruction to the renderer — what the board is made of and what a thing
# on it is made of — and the comparative audit measured them on the same frames
# (`audit/comparative/tracks/m1-visual-metrics.md`). Splitting them would put
# two halves of one paragraph in two places in the prompt.
#
# Rule 3 is a PROMOTION, not a new rule: `VISUAL_CRAFT` below already says
# "connected multi-tile shapes … not lone 1x1 colored squares" as distilled
# craft. Four of our seven shipped games drew load-bearing state as lone pixels
# anyway, so the rule is restated here as a REQUIRED row with a floor a machine
# can measure (`s3_visual` `role-footprint`) and an exception that has to be
# declared instead of assumed.
#
# Anchors, not quotes-at-large: §9 of the study rides in this same payload
# VERBATIM through `visual_grammar_section` (it is in `GRAMMAR_SECTIONS`), so
# the two lines quoted below sit a few thousand characters above their own
# source and a drift between them is visible in the prompt itself.
FLOOR_AND_FOOTPRINT = """\
## The floor and the footprint (HARD RULES — measured on our own corpus)

Three REQUIRED rows. The grammar is §9 (Palette semantics) of the corpus
study quoted above; the defects are ours, measured over the seven games
this pipeline has shipped.

1. **REQUIRED: the playfield is PAINTED.** The field — the index most of
   the board is drawn in — is the index this spec declares in
   `game.palette.background`. A spec that declares none is held to the
   canon default, black `5` (affordance §9: "`5` black —
   background/outline default"). The greys `1-4` are the study's
   structural floor colors and are equally good paint. What the field is
   NOT is white `0`: the officials paint theirs (index `0` is the modal
   index on 6 of 183 official level-start boards, all six of them one
   game), and four of our seven shipped games left theirs white.

2. **REQUIRED: reserve `0` for selection.** Index `0` is the ecosystem's
   MARK, not paint:

   > `0` white — **selection/highlight** (the ecosystem's marker), spent-or-
   > remaining budget, refusal flashes. Semantic; avoid as plain paint.
   > — (affordance-language.md:L239-240, §9)

   and the section's own REQUIRED line, "reserve `0` for selection"
   (affordance-language.md:L252, §9). A board whose field is white has
   spent that index on the floor: the player's selection, the meter's
   remaining budget and a refusal flash all have to be drawn in something
   else, and the one idiom every official shares stops working. Use `0`
   for marks, on a painted field.

   DECLARED EXCEPTION: a game whose idea genuinely needs a white field
   declares it — `game.palette.background: 0` in the §11 block — and then
   draws its selection marks in another index. `0` is not banned; an
   UNDECLARED white field is.

3. **REQUIRED: load-bearing state is drawn in multi-tile shapes.**
   Anything the player has to read to play — "you", the goal, danger, the
   state of a mechanism — is a connected shape of at least
   one full logical cell (`game.render.cell_px` px on a side, so
   cell_px x cell_px pixels), never a lone 1x1 pixel, a scatter of single
   pixels, or a one-pixel hairline. Measured in our own corpus: an avatar drawn
   as 5 isolated pixels, a mirror as 4, a lane as one pixel per cell, a
   whole pipe network as 37 pixels over 10 tiles.

   DECLARED EXCEPTION: if the spec you were given genuinely requires a
   tiny token — a single-pixel marker the mechanic is *about* — draw it
   and nothing else that way. The exception is DECLARED, never assumed by
   the implementation: either the spec itself names the role
   (`game.palette.tiny_token`, the W2-D surface) or the operator exempts
   it at the pipeline level (the gate's `role-footprint` exemption list).
   An undeclared lone pixel reads as a defect and is measured as one.

   GLYPH INK is a contrast decision, not a spare palette index. Ink drawn
   one index off its own tile's fill is unreadable at 64x64 (a shipped
   build drew ink 4 on a fill-3 body), and ink drawn in an index the
   spec's `palette.reserved` names spends a reserved colour on every
   inert tile (the same game's other build: ink 1 against
   `reserved: [5, 1]`). Pick ink that is visibly distinct from its tile
   fill AND outside `palette.reserved`."""

# --- the win, and how much of the board it has to move (R-04) ---------------
# MEASURED, like every other number in this module, and measured HERE rather
# than in `s3_visual` because two consumers need the same integer: the gate
# check that reads the frames and the payload row that tells an implementer
# what it will be held to. That is the prompt-sync discipline — one constant,
# both consumers — and the reason `OFFICIAL_FIELD_INDEX`'s precedent (a corpus
# block living in `s3_visual`) is not followed for this one.
#
# NOT a key of `OFFICIAL_VISUAL_CONSTANTS`, deliberately: `s3_visual._official_bands`
# dumps that whole mapping onto every card, so a key added there would change the
# bytes of a card built with every new check OFF — the one regression contract
# W1-A1 froze.
#
# SOURCE (READ-ONLY input, re-measurable): for each of the 25 signed officials,
# `duckWM/local-docs/arc-agi-3-generator/out/frames/<slug>/trace.jsonl.gz`, the
# cell-for-cell difference between the FIRST record in state `WIN` and the last
# level-start record under `audit_common.level_starts` (the rule
# `s3_visual.level_start_indices` reproduces). Whole 64x64 frame, 4096 cells.
#
# THE FLOOR IS THE OFFICIALS' 25th PERCENTILE, and that departs from this
# repo's usual "the floor is the corpus MIN" discipline (`l1_colors` min = 4,
# an official sitting exactly on it). It departs because the MIN does not
# separate the measured defect: m0r0's win moves 98 cells and tu93's 111, which
# is QUIETER than `pump-phase-time-echo`'s 123 — the game the comparative audit
# recorded as "reads as an ordinary mid-level frame". So "the officials always
# render the win" is true of the exemplars the audit cites (ar25, sb26, sp80)
# and NOT true of the corpus floor, and a min-derived floor would pass three of
# the four exhibits contract W1-A2 requires it to reject.
#
# What the 25th percentile buys, stated as the cost it carries:
#   * it is measurement-INVARIANT — 229 whether the officials' frames are
#     compared whole or with every candidate HUD strip (row 0, row 63, col 0)
#     excluded the way ours are; sk48 sits exactly on it and loses 0 cells to
#     those strips, while the min moves 98 -> 56 and the median 392 -> 384;
#   * it lands inside our own corpus's empirical gap: the four wins the audit
#     calls illegible top out at 123 board cells and the two it calls legible
#     start at 321, so the bar has ~100 cells of margin on both sides;
#   * it would REJECT 6 of the 25 signed officials (listed below). That is the
#     honest price of reproducing the audit's verdicts and it is why the knob
#     is born `off` and has to be armed by name.
OFFICIAL_WIN_RENDER: dict[str, object] = {
    "games": OFFICIAL_GAMES,
    "cells": 4096,                   # the 64x64 camera; whole-frame comparison
    "min": 98, "min_game": "m0r0",
    "p25": 229, "p25_game": "sk48",
    "median": 392, "median_game": "cd82",
    "max": 2169, "max_game": "bp35",
    # Re-measured with rows 0 and 63 and column 0 excluded — the three strips
    # `s3_visual.HUD_STRIP_GEOMETRY` can locate — so that the officials are read
    # on the same footing as a generated game whose declared HUD is masked off.
    "min_hud_excluded": 56,
    "p25_hud_excluded": 229,
    "median_hud_excluded": 384,
    # The games this floor would reject, with their measured deltas.
    "below_floor_games": ["m0r0", "tu93", "sc25", "lp85", "tn36", "re86"],
    "below_floor_deltas": [98, 111, 124, 147, 211, 214],
}

OFFICIAL_WIN_RENDER_SOURCE = (
    "duckWM/local-docs/arc-agi-3-generator/out/frames/<slug>/trace.jsonl.gz, the 25 "
    "signed officials — cells differing between the first record in state `WIN` and "
    "the last level-start record (`audit_common.level_starts`, the rule "
    "`s3_visual.level_start_indices` reproduces). Re-measurable with "
    "audit/comparative/scripts/audit_common.py; whole 64x64 frame, 4096 cells"
)

# The one number the R-04 check rejects on, derived from the block above so a
# re-measurement of the corpus moves it (`s3_visual.L1_COLOR_FLOOR`'s rule).
WIN_RENDER_FLOOR_CELLS = int(OFFICIAL_WIN_RENDER["p25"])

# The payload row. Its own section rather than a fourth row of
# `FLOOR_AND_FOOTPRINT` above: that block's whole argument for being ONE block
# is that R-01 and R-02 are the same instruction to the renderer (what the board
# is made of, what a thing on it is made of), and what the WINNING board says is
# a different instruction. It rides directly under it in the payload.
_WIN_IS_RENDERED = """\
## The win is RENDERED (HARD RULE — measured on our own corpus)

One REQUIRED row, and the pipeline measures it on the frames your game
produces.

**REQUIRED: winning must LOOK like winning.** The settled frame the game
is in when it reaches the `WIN` state must differ legibly from the frame
that STARTED the final level — on the board, outside whatever row or
column `hud.reserved` declares. A meter that ticks in the HUD is not the
win being rendered; the board itself has to say the game is over.

How the officials do it: ar25 covers all 60 of its targets; sb26 fills
twelve cells and flips their backings white; sp80 repaints its cup
maroon. Across the 25 signed officials the win frame moves a median of
{median} of the 4096 cells on the board.

How we have done it, measured over the seven games this pipeline has
shipped: one game's winning frame is BYTE-IDENTICAL to a frame 84
actions earlier, one moves 22 cells, one 36, one 65, and one 123 that
read as ordinary mid-level scatter. Four of seven winning boards carry
no signal at all.

THE FLOOR: at least **{floor} cells** of the board — outside the declared
HUD strip — must differ between the final level's start frame and the
`WIN` frame. That is the officials' 25th percentile. Do not reach it by
enlarging the HUD: cells inside the declared `hud.reserved` strip are
excluded from the count before it is compared.

Spend it on the thing the player was trying to do — the targets they
covered, the shape they completed, the mechanism they opened — not on
decoration. A win screen that repaints the board in a flat colour clears
the floor and teaches nothing."""

WIN_IS_RENDERED = _WIN_IS_RENDERED.format(
    floor=WIN_RENDER_FLOOR_CELLS,
    median=OFFICIAL_WIN_RENDER["median"],
)


# --- R-03: the chrome that makes a board a PLACE ------------------------------
# MEASURED, and measured here for `OFFICIAL_WIN_RENDER`'s exact reason: two
# consumers need the same band — the payload row that tells an implementer what
# a framed board looks like, and `s3_visual`'s `chrome-extent` check that reads
# the frames. One constant, both consumers.
#
# NOT a key of `OFFICIAL_VISUAL_CONSTANTS`, deliberately, on the same rule
# `OFFICIAL_WIN_RENDER` states: `s3_visual._official_bands` dumps that whole
# mapping onto every card, so a key added there would change the bytes of a card
# built with every new check OFF.
#
# SOURCE (READ-ONLY input, re-measurable): `audit/comparative/data/level-metrics.csv`,
# column `occupied_extent` — "cells that are not the modal value", i.e. how much
# of the 64x64 board is used at all (`audit_common.occupied_extent`). The band is
# the min and max of the OFFICIALS' 25 PER-GAME MEDIANS, which is the audit's own
# definition of an outside-band flag and the most permissive band available:
# "the FULL observed range of the officials' per-game medians — min to max over
# all 25, not a percentile band" (`tracks/m1-visual-metrics.md:324`).
#
# THE FLOOR IS THE CORPUS MIN, which restores this repo's usual floor discipline
# — `WIN_RENDER_FLOOR_CELLS` had to depart from it and paid six officials for the
# departure. Here nothing is paid: re86 sits exactly ON 361 and every one of the
# 25 signed officials is inside the band by construction.
OFFICIAL_CHROME: dict[str, object] = {
    "levels": 183,
    "games": OFFICIAL_GAMES,
    # min / median / max of the 25 officials' per-game `occupied_extent` medians.
    "band_low": 361, "band_low_game": "re86",
    "band_median": 1089, "band_median_game": "sc25",
    "band_high": 2889, "band_high_game": "tn36",
    # Ours, measured the same way over the 7 games this pipeline has shipped.
    "ours_games": 7,
    "ours_median": 508,
    "ours_ratio": 0.47,              # 508 / 1089 = 0.4665
    "ours_below_band": ["core-ward-phase-gates", "pump-flow-match-glow",
                        "facing-sentinel-match-the-signal-row"],
    "ours_below_band_medians": [166.5, 249, 272],
    # The decor census behind the rule. The officials' figure is a RANGE because
    # the two blind visual passes counted it differently and the merge kept both
    # (28 rows over 25 games / 31 rows over 17 games); ours is a flat two.
    "official_decor_rows": "28-31",
    "ours_authored_decor_objects": 2,
    "ours_authored_decor": ["pump-flow-match-glow: the decoy junction",
                            "facing-sentinel-match-the-signal-row: the demo tile"],
}

OFFICIAL_CHROME_SOURCE = (
    "audit/comparative/data/level-metrics.csv, column `occupied_extent` (cells that are "
    "not the board's modal value) — the band is min..max of the 25 officials' PER-GAME "
    "medians, the audit's own outside-band rule (tracks/m1-visual-metrics.md:324, table "
    ":160-176). The decor census is the two blind visual passes merged at "
    "findings.md:252 / tracks/j2-visual-judgment.md:68-74"
)

# The two numbers `s3_visual.chrome-extent` compares against, derived from the
# block above so a re-measurement of the corpus moves them (`L1_COLOR_FLOOR`'s rule).
CHROME_EXTENT_BAND: tuple[int, int] = (
    int(OFFICIAL_CHROME["band_low"]), int(OFFICIAL_CHROME["band_high"])
)

_CHROME_IS_STRUCTURE = """\
## A board is FRAMED (HARD RULE — measured on our own corpus)

One REQUIRED row, and the pipeline measures it on the frames your game
produces.

**REQUIRED: author the chrome.** Inert structure — drawn once, never
interactive, never load-bearing — marks where the world ENDS. Without it a
playfield is a small mechanism adrift in an undifferentiated field; with it
the same mechanism reads as a place. The officials' decor rows number
{decor_rows} across the {games} signed games and they are almost entirely
chrome. Ours number **{ours_decor}** across {ours_games} games.

The four idioms, each with the official that draws it:

- **Letterbox band** — a flat inert panel covers the parts of the camera the
  level does not use, so the live region is the only area on the real
  background colour. *ft09* letterboxes three quadrants this way (its
  bestiary's "letterbox panel" decor row, drawn under the play layer).
- **Panel slab** — the floor is inset as its own block of a distinct index
  inside a surround, so the playfield has an edge instead of fading out.
  *sk48* insets a dark-grey playfield slab inside a black surround.
- **Divider rail** — a line or dashed column walls one region off from
  another, so two zones read as two zones. *dc22* letterboxes top and bottom
  and walls off a panel side with a dashed divider column.
- **Bezel / banner frame** — a band plus rules boxes a reference or HUD
  region, so the panel reads as an instrument and not as more board. *cd82*
  draws a mid-grey banner plus two darker rules around its reference panel
  (its bestiary's "HUD chrome" decor row).

THE MEASUREMENT: `occupied_extent` — cells on a level-start board that are
NOT the board's modal index. Across the {games} officials the per-game median
runs **{band_low} ({band_low_game}) to {band_high} ({band_high_game})**,
median {band_median}. Ours is {ours_median}, **{ratio}x** theirs, and
{below_n} of our {ours_games} games sit BELOW the whole observed band.

DECLARE IT: `game.chrome` in the §11 block is a list of
`{{kind: <letterbox|panel|divider|bezel>, where: <region>}}` entries. It is
OPTIONAL and absence is silence — but the gate's `chrome-extent` check is
PAIRED, and the pairing is the point: a game is flagged only when its
`occupied_extent` is below the officials' band AND it declares no chrome at
all. Filling the board with chrome nobody authored, or declaring chrome you
did not draw, each satisfies one leg and neither clears the check. Chrome is
INERT: it must not be clickable, collidable, or readable as state."""

CHROME_IS_STRUCTURE = _CHROME_IS_STRUCTURE.format(
    games=OFFICIAL_GAMES,
    decor_rows=OFFICIAL_CHROME["official_decor_rows"],
    ours_decor=OFFICIAL_CHROME["ours_authored_decor_objects"],
    ours_games=OFFICIAL_CHROME["ours_games"],
    band_low=OFFICIAL_CHROME["band_low"],
    band_low_game=OFFICIAL_CHROME["band_low_game"],
    band_high=OFFICIAL_CHROME["band_high"],
    band_high_game=OFFICIAL_CHROME["band_high_game"],
    band_median=OFFICIAL_CHROME["band_median"],
    ours_median=OFFICIAL_CHROME["ours_median"],
    ratio=OFFICIAL_CHROME["ours_ratio"],
    below_n=len(OFFICIAL_CHROME["ours_below_band"]),
)


# --- T-1: board DENSITY, and why t1 is not sparse ------------------------------
# MEASURED, and measured here for `OFFICIAL_WIN_RENDER`'s exact reason: two
# consumers need the same numbers — the S2 payload's density guidance
# (`density_section`) and `s3_visual`'s `density` card check. One constant, both
# consumers; the payload sentence and the card band are both interpolated from
# the dict below and nowhere else (contract T-1, operator ruling 2026-10-06:
# "Close it: guidance + band check").
#
# NOT a key of `OFFICIAL_VISUAL_CONSTANTS`, on the rule `OFFICIAL_WIN_RENDER`
# states: `s3_visual._official_bands` dumps that whole mapping onto every card.
#
# SOURCE (READ-ONLY input, re-measurable): `audit/comparative/data/level-metrics.csv`,
# column `objects_pcc`, the 183 rows with `corpus == official` — one row per
# level-START board (`audit_common.level_starts`, the rule
# `s3_visual.level_start_indices` reproduces) over the 25 signed games.
# `objects_pcc` is the OFFICIALS' object definition, not ours: for every distinct
# colour on the board INCLUDING the background, count that colour's 4-connected
# components, and sum (`audit_common.pcc_stats`, reimplementing the manual-play
# corpus's `probe_games.object_stats`; its official rows cross-check against the
# published `objects` column 183/183). `s3_visual.objects_pcc` reproduces it.
#
# THE DERIVATION, stated so it can be re-run by hand:
#   vals = sorted(int(r["objects_pcc"]) for r in rows if r["corpus"] == "official")
#   len(vals) == 183; min 7, max 873.
#   median: rank 92 of 183 = 47.
#   p25: 25 — and it is INTERPOLATION-INVARIANT: numpy.percentile(vals, 25) under
#        every method (linear, lower, higher, nearest, midpoint, inverted_cdf,
#        hazen, weibull, median_unbiased) and statistics.quantiles(vals, n=4)
#        under both methods all return 25 (the median likewise returns 47
#        everywhere). 45 of the 183 boards sit strictly below it (24.6%); 138
#        sit at or above.
#   level 1 alone (the 25 rows with `level` == 1): median 26 — the officials
#        open LIGHTER (12 of 25 level-1 boards are under the floor), which is
#        why the unit below is the game's per-level MEDIAN and never every
#        level: a sparse teaching level 1 is the corpus's own habit.
#   p75 is deliberately NOT pinned: it moves 77..80 with the interpolation
#        method, and a ceiling would be a threshold with no exhibit behind it
#        (`CHROME_EXTENT_CALIBRATION["above_band_note"]`'s rule — the measured
#        defect is emptiness, never crowding).
#
# THE UNIT IS ONE GAME'S PER-LEVEL MEDIAN, held against the officials' PER-LEVEL
# distribution — the statistic the parity re-measure reports
# (`audit/comparative/tracks/parity-remeasure-2026-10-06.md`, "PER-LEVEL MEDIANS").
#
# CALIBRATION — the same comparison run over the 25 officials' own per-level
# medians (the R-01/R-04 calibration pattern): 20 of 25 at or above the floor;
# the 5 below are listed below with their medians, and vc33 sits exactly ON the
# floor (25.0). That is the price of a percentile floor and it is the
# `OFFICIAL_WIN_RENDER` precedent (6 of 25 there).
#
# OURS — the same ruler over every game packaged since b004 (the parity
# re-measure, 2026-10-06): the five t1 games cluster at 12-31.5 on BOTH driver
# lanes; the one t2 game (tidegate-mosaic) holds 56. A TIER property, not a lane
# property — which is why the card's band is t1-scoped (`DENSITY_TIERS`).
OFFICIAL_DENSITY: dict[str, object] = {
    "levels": 183,
    "games": OFFICIAL_GAMES,
    "metric": "objects_pcc",
    "min": 7,
    "p25": 25,
    "median": 47,
    "max": 873,
    "levels_below_p25": 45,
    "l1_median": 26,
    # The 25 officials' per-level medians held against the p25 floor.
    "games_below_floor": ["cn04", "sp80", "ka59", "g50t", "wa30"],
    "games_below_floor_medians": [9.5, 15, 16, 18, 21],
    "games_on_floor": ["vc33"],
    # Ours, per-level medians on the same ruler (parity re-measure 2026-10-06).
    "ours_t1": {"twin-signal-rendezvous": 12, "echo-quilt": 18,
                "lantern-path-parity-trace": 24, "seamlock": 27, "key-strip-rover": 31.5},
    "ours_t2": {"tidegate-mosaic": 56},
}

OFFICIAL_DENSITY_SOURCE = (
    "audit/comparative/data/level-metrics.csv, column `objects_pcc` (the officials' object "
    "definition: per-colour 4-connected components summed over every colour, background "
    "included), the 183 `corpus == official` level-start rows over the 25 signed games. "
    "Rebuilt by audit/comparative/scripts/m1_metrics.py; its official rows cross-check "
    "against the manual-play corpus's published `objects` column"
)

# The two numbers both consumers read, derived from the block above so a
# re-measurement of the corpus moves them (`WIN_RENDER_FLOOR_CELLS`'s rule).
DENSITY_FLOOR_OBJECTS = int(OFFICIAL_DENSITY["p25"])
DENSITY_MEDIAN_OBJECTS = int(OFFICIAL_DENSITY["median"])

# THE TIER SCOPE, explicit (contract T-1 B4): the card's band APPLIES to these
# tiers and is RECORDED (measured, printed, never a verdict) for every other tier
# and for a game whose tier cannot be read. t1 is where the gap was measured — the
# t2 game holds the band — and the ruling names "a t1 density band".
DENSITY_TIERS: tuple[str, ...] = ("t1",)

# Where a slot's tier lives, in precedence order. `game.tier` in spec.yaml is the
# DURABLE record of a P-A.3 promotion (`orchestrator.SPEC_TIER_FIELD`, reproduced
# here because this module must not import the orchestrator); `idea.json` is the
# tier the idea was DRAWN at, which S1 copies into the spec dir
# (`s1_spec.run_s1` writes `out_dir / "idea.json"`) and which is never rewritten.
# A promotion therefore wins over the draw.
SPEC_TIER_FIELD = "tier"
IDEA_NAME = "idea.json"
_SPEC_YAML = "spec.yaml"


def spec_tier(spec_dir: Path) -> tuple[str | None, str | None]:
    """(tier, where it was read) for one spec dir — or (None, None).

    ONE reader, both T-1 consumers: the S2 payload picks its density sentence
    with it and the visual card scopes its band with it, so the guidance an
    implementer reads and the band its game is measured against can never be
    keyed to two different tiers.

    Quiet on every absence and every malformed file (`_spec_document`'s rule):
    a tier nobody can read is reported as None and the card says so, never a
    stage crash. Deliberately NOT gated on the batch's `tiers:` policy
    (`s1_spec._idea_tier` is): every idea since the pilot carries its drawn tier,
    and the density gap is a fact about the tier the game was drawn at, not
    about whether this batch armed the §3.3 linter rules.
    """
    spec_dir = Path(spec_dir)
    spec_path = spec_dir / _SPEC_YAML
    if spec_path.is_file():
        try:
            game = _game_block(_spec_document(spec_path))
        except (OSError, ValueError, yaml.YAMLError):
            game = {}
        tier = game.get(SPEC_TIER_FIELD)
        if isinstance(tier, str) and tier in TIERS:
            return tier, f"{_SPEC_YAML} game.{SPEC_TIER_FIELD}"
    idea_path = spec_dir / IDEA_NAME
    if idea_path.is_file():
        try:
            idea = json.loads(idea_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            idea = None
        tier = idea.get(SPEC_TIER_FIELD) if isinstance(idea, Mapping) else None
        if isinstance(tier, str) and tier in TIERS:
            return tier, f"{IDEA_NAME} {SPEC_TIER_FIELD}"
    return None, None


_DENSITY_HEAD = """\
## Board density — an official LEVEL is a busy board (measured)

THE MEASUREMENT: `objects_pcc`, the officials' own object count — for every
colour on a level-start board, background included, count its 4-connected
regions, and sum them. Across the {levels} official level-start boards the
median is **{median}** and the 25th percentile is **{floor}**: three official
boards in four carry {floor} or more. (Per GAME the corpus varies wildly, as the
numbers card above says; per LEVEL, the typical official board is a full one.)
The pipeline measures your game on the same ruler — the median of
`objects_pcc` over your level-start boards — and prints it on the visual card
beside this band.

Density comes from STRUCTURE and REPETITION of what the spec already declares:
walls and room shapes, floor panels, authored chrome, several instances of the
declared pieces, varied layouts. Never from new mechanics, distractors or decoys
the spec does not declare — the scope clause above still binds, and every added
object obeys the footprint and palette rules. More objects, never more noise."""

_DENSITY_T1 = """\
**This spec is tier t1 — and t1 SIMPLICITY IS MECHANICAL, NOT VISUAL.** A t1
game has fewer RULES: fewer terms, one introduction per level, a goal
readable from the first frame. It does NOT have an emptier board. Our own
t1 games measured a per-level median of {ours_low}-{ours_high} ({ratio_low}x-{ratio_high}x
the officials' {median}) on both driver lanes, while our t2 game held {ours_t2}:
sparseness was a habit, not a requirement of the tier. Level 1 may open
lighter — the officials' own level-1 boards have a median of {l1_median} — but
the game's typical level is a full board. THE FLOOR: the visual card's
`density` check flags a t1 game whose per-level median is under **{floor}**
(the officials' 25th percentile)."""

_DENSITY_OTHER = """\
This spec is tier {tier}. The card's `density` band is scoped to
{scope} — the tier where the gap was measured; our t2 game held {ours_t2}, inside
it — so for this game it is recorded beside your number, never a verdict. Land
near the officials' median all the same."""

_DENSITY_UNKNOWN = """\
This spec carries no tier the pipeline can read, so the card's `density` band
(scoped to {scope}) is recorded beside your number, never a verdict. Land near the
officials' median all the same."""


def density_section(tier: str | None) -> str:
    """The tier-aware density guidance, rendered from `OFFICIAL_DENSITY`.

    Every payload carries the head (the officials' figures, the ruler, and where
    density honestly comes from); the tier line under it is the tier-aware half:
    a t1 spec is told that its simplicity is mechanical and that the floor
    applies to it; any other tier — or none — is told the band is recorded only.
    Every number is interpolated from the one constant block above, so the
    figure in the prompt is the figure the card's band is cut at.
    """
    ours_t1 = list(OFFICIAL_DENSITY["ours_t1"].values())
    ours_t2 = list(OFFICIAL_DENSITY["ours_t2"].values())
    median = DENSITY_MEDIAN_OBJECTS
    scope = "/".join(DENSITY_TIERS)
    head = _DENSITY_HEAD.format(levels=OFFICIAL_DENSITY["levels"], median=median,
                                floor=DENSITY_FLOOR_OBJECTS)
    if tier in DENSITY_TIERS:
        low, high = min(ours_t1), max(ours_t1)
        line = _DENSITY_T1.format(
            ours_low=_number(low), ours_high=_number(high),
            ratio_low=f"{low / median:.2f}", ratio_high=f"{high / median:.2f}",
            median=median, ours_t2=_number(ours_t2[0]), floor=DENSITY_FLOOR_OBJECTS,
            l1_median=OFFICIAL_DENSITY["l1_median"],
        )
    elif tier is None:
        line = _DENSITY_UNKNOWN.format(scope=scope)
    else:
        line = _DENSITY_OTHER.format(tier=tier, scope=scope, ours_t2=_number(ours_t2[0]))
    return f"{head}\n\n{line}"


def _number(value: object) -> str:
    """`31.5` stays `31.5`; `12` and `12.0` both print `12`."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


# --- R-13: danger STANDS on the board, and revealing is LIGHTER ---------------
# Two rules, ONE block, for `FLOOR_AND_FOOTPRINT`'s reason: they are the same
# instruction to the renderer — what a threat looks like before it bites, and
# which way a reveal moves the light — and the comparative audit measured both
# on the same frames (`findings.md` B4, J-2 corroborated gaps 8 and 10).
#
# The 19 is the officials' hazard census: every one of the 19 hazard rows over
# the signed corpus is a PLACED OBJECT that stands on the board before it bites
# (findings.md:269). Ours vanish two ways the spec never declared.
OFFICIAL_HAZARD_ROWS = 19

_DANGER_STANDS = """\
## Danger STANDS on the board (HARD RULES — measured on our own corpus)

Two REQUIRED rows, both measured on the frames your game produces.

1. **REQUIRED: a declared danger index is PAINTED.** If the spec declares
   `palette.danger`, that index must appear on a SETTLED frame of every level
   that declares the hazard. All {hazard_rows} hazard rows across the {games}
   signed officials are placed objects that stand on the board before they
   bite — the player reads the threat, then avoids it.

   Ours do not. One shipped game's hazard is never an object at all: a
   one-frame crush flash a winning player never sees, so its declared danger
   index `8` is absent from every settled frame of all eight levels. Another
   paints its `8` on two of its eight level starts and suppresses it under fog
   on the rest — an OPEN valve that paints no danger index at all. Neither
   game DECLARED either behaviour.

   A hazard whose tell is genuinely the absence of a mark declares that:
   `knobs.danger_tell: absence`. A hazard deliberately hidden among
   look-alikes declares `knobs.danger_tell: camouflage`, which is a t2/t3
   deception lever and is held to the deception rules. Anything else must be
   on the board.

2. **REQUIRED: revealing makes the board LIGHTER.** When a game conceals part
   of the board and reveals it (`info.fog`), the concealed state and the
   revealed state are two indices, and the REVEALED one must be the LIGHTER of
   the two. Fog is a veil over a lit world; lifting it turns a lamp on, not
   off.

   A shipped game gets this backwards: its fog is index `2` (153,153,153) and
   the rail it reveals is index `3` (102,102,102), so uncovering a rail makes
   that patch of board DARKER and revealing reads as casting a shadow. The
   grey ramp runs `0` white to `5` black, so the lighter index is the LOWER
   number: pick the concealer DARKER than what it hides."""

DANGER_STANDS = _DANGER_STANDS.format(
    hazard_rows=OFFICIAL_HAZARD_ROWS,
    games=OFFICIAL_GAMES,
)


# --- R-08: never signal AND charge, and a refusal the player must learn -------
# The §6 rule is CANON and is quoted, not paraphrased: `affordance-language.md`
# §6 line 157-158, which the audit lead re-verified verbatim. §6 itself rides in
# this same payload through `visual_grammar_section` (it is in
# `GRAMMAR_SECTIONS`), so the quote below sits a few thousand characters under
# its own source and a drift between them is visible in the prompt itself —
# `FLOOR_AND_FOOTPRINT`'s anchoring rule.
REFUSAL_PERSISTENCE_FRAMES = 1     # §6:160 "persisting >=1 settled frame"

_REFUSAL_NEVER_BOTH = """\
## Refusal: never both, and never invisible (HARD RULES)

Two REQUIRED rows. The grammar is §6 (Refusal) of the corpus study quoted
above; the defects are ours.

1. **REQUIRED: charge silently, or signal freely — never both.** §6 states
   it and names the mixed case FORBIDDEN:

   > The correlation is the design grammar: **officials either charge silently
   > or signal freely — never both.**
   > — (affordance-language.md:L157-158, §6)

   A refused action either costs the player something and says nothing, or
   says something and costs nothing. Two of the seven games this pipeline has
   shipped do both — one's refusal flash "costs a step and drains pressure
   anyway", the other's "still rolls and still burns a drum" — and BOTH
   declare `knobs.refusal: visible`. Pick one semantics and hold it on every
   refusal path in the game.

2. **REQUIRED: a refusal the player must LEARN survives into a settled
   frame.** §6's own bar for a visible refusal is a signal "persisting
   >={frames} settled frame". A signal drawn and cleared inside one action is
   invisible to a frame-differencing agent and to this pipeline's own capture,
   which keeps the settled frame only — so a mechanic taught by refusal is a
   mechanic nobody can learn. Six of our seven games' refusal signals appear
   in ZERO captured records; one renders its flash into the frame BEFORE the
   settled one, which cannot survive by construction.

   DECLARED EXCEPTION: a refusal signal that is deliberately transient and
   not something the player must learn from is declared —
   `knobs.{transient_field}: true` in the §11 block — and then nothing expects
   it in a settled frame. Absent the declaration, `knobs.refusal: visible`
   PROMISES a settled-frame-persistent signal, and the gate reads the
   promise."""

REFUSAL_NEVER_BOTH = _REFUSAL_NEVER_BOTH.format(
    frames=REFUSAL_PERSISTENCE_FRAMES,
    transient_field=REFUSAL_TRANSIENT_FIELD,
)


# --- teaching by showing (the six idioms) -----------------------------------
# One cite per idiom, all six verified line by line against the bestiary:
#   worked example      GEN/design/objects/bestiary/ft09.md:30-31
#                       (the inert tutorial icon + the solved diagram in its hole)
#   progressive legend  bestiary/su15.md:68-70 (the two legends and the flat
#                       `legend mask` rectangles that uncover one rung-group per
#                       level); the contract's candidate range ran to :73, which
#                       is the HUD band / attract ring / L1 furniture rows
#   free auto-demo      bestiary/sc25.md:60 ("L1's first action, which
#                       `qytejzcythm` swallows to play the tutorial demo" — listed
#                       under what is FREE) and :71 (the L1-L3 auto-select knob)
#   indicator wire      bestiary/sb26.md:49 (the L2-only green tutorial wire,
#                       collidable=False: "this pointer means that row")
#   attention pulse     bestiary/lf52.md:29 (the L1-only tutorial pulse ring)
#   stuck hint          bestiary/ar25.md:39 (the L2 hint glyph, armed after 15
#                       moves with no selection change) — the contract left this
#                       line number to be found
# lf52's ring and ar25's glyph are recorded as code-only (cleared before the
# settled frame, so a frame-differencing agent never sees them). They are quoted
# here as the IDIOM, and a generated game should render the idiom into a settled
# frame rather than reproduce the corpus's own invisibility.
TEACHING_BY_SHOWING = """\
## Teaching by showing — the six official idioms

Rule 2 of the visual legibility section says level 1 teaches by showing.
These are the six frame-verified ways the official corpus does it. Use
the one that fits your mechanic; all six share the principle: teach with
inert, level-1-scoped demonstration furniture that costs nothing and
disappears — never a coded legend the player must decrypt.

- Worked example: an already-solved instance of the win condition sits on
  the board from frame one (ft09).
- Progressive legend: the reference panel reveals one entry per level, as
  the mechanic it names arrives — never the whole code table up front
  (su15).
- Free auto-demo: level 1's first action triggers a demonstration of the
  core mechanic before the player's input takes effect, at zero budget
  cost (sc25).
- Indicator wire: a literal connector ties an indicator to the thing it
  indicates, in the level where the pairing must be learned (sb26).
- Attention pulse: a brief pulse ring points at the next useful object
  the first time it matters (lf52).
- Stuck hint: a hint glyph appears only when the player is measurably
  stuck, not before (ar25)."""

# --- the corpus-numbers card ------------------------------------------------
# Every number below is interpolated from OFFICIAL_VISUAL_CONSTANTS: the card
# is a RENDERING of the pinned block, never a second copy of it that can drift
# away from the citations. Only the population size (OFFICIAL_GAMES) and the
# 64x64 camera — neither of them a measured value — are spelled out.
_NUMBERS_CARD = """\
## Official-corpus visual numbers (render targets, not gates)

Measured across the {games} official games (sources pinned in gen/visual_canon.py):

- Render scale: every official uses ONE tile scale from the menu
  {menu} px per logical cell; {native} of {games} render native 64x64
  (scale 1). Pick one scale from the menu and hold it everywhere.
- Colors on the level-1 board: min {l1_min}, median {l1_median}, max {l1_max} — land inside this
  band.
- Colors on the board across levels (per-game median): {colors_min} to {colors_max},
  median {colors_median}.
- Objects on the board (per-game median): {objects_min} to {objects_max}, median {objects_median} —
  density varies wildly; readability never does.
- Frame rate: default_fps {fps_min} to {fps_max}.

A game far outside these bands does not look like an official."""


def corpus_numbers_card() -> str:
    """The pinned corpus numbers as one prompt card, rendered from the constants."""
    menu = OFFICIAL_VISUAL_CONSTANTS["tile_scale_menu"]
    l1_min, l1_median, l1_max = OFFICIAL_VISUAL_CONSTANTS["l1_colors"]
    colors_min, colors_median, colors_max = OFFICIAL_VISUAL_CONSTANTS["board_colors_median"]
    objects_min, objects_median, objects_max = OFFICIAL_VISUAL_CONSTANTS["objects_median"]
    fps_min, fps_max = OFFICIAL_VISUAL_CONSTANTS["default_fps"]
    return _NUMBERS_CARD.format(
        games=OFFICIAL_GAMES,
        menu="{" + ", ".join(str(scale) for scale in menu) + "}",
        native=OFFICIAL_VISUAL_CONSTANTS["native_64_count"],
        l1_min=l1_min,
        l1_median=l1_median,
        l1_max=l1_max,
        colors_min=colors_min,
        colors_median=colors_median,
        colors_max=colors_max,
        objects_min=objects_min,
        objects_median=objects_median,
        objects_max=objects_max,
        fps_min=fps_min,
        fps_max=fps_max,
    )


# --- the quoted grammar -----------------------------------------------------

# Quoted unconditionally; §3 rides only when the spec has danger to render.
GRAMMAR_SECTIONS = (1, 2, 5, 6, 9)
DANGER_SECTION = 3

GRAMMAR_HEADER = """\
## The visual affordance grammar (quoted from the signed canon)

These sections are quoted verbatim from the corpus study
`affordance-language.md`. They describe HOW to render surface the spec
already declares. The scope clause applies unchanged: a lever, decoy, or
idiom quoted here that `knobs.deceptions` does not declare is still a
rejection."""

# One echo per §5 knob, naming the quoted section that governs it — the knob is
# a WORD in the spec until something says which grammar reads it. `danger_tell`
# is echoed only when §3 itself rode along, because its catalog is §3's body.
KNOB_ECHOES: dict[str, str] = {
    "goal_legible": (
        "This spec declares `goal_legible: {value}` — render the goal with §2's idioms at "
        "that legibility; do not make it harder or easier to read than declared."
    ),
    "danger_tell": (
        "This spec declares `danger_tell: {value}` — §3's catalog entry for that tell is "
        "the render rule."
    ),
    "refusal": (
        "This spec declares `refusal: {value}` — §6's rule for that mode is binding: charge "
        "silently or signal freely, never both."
    ),
}
# `danger_tell` is echoed under §3's own condition, never on its own.
_DANGER_KNOB = "danger_tell"


def _spec_document(spec_yaml_path: Path) -> Mapping:
    """The spec's yaml as a mapping — `s2_implement._spec_terms`'s own pattern.

    A spec that does not parse to a mapping has already been caught upstream
    (S1's linter, then `_spec_terms`); this reader stays quiet about shape so a
    payload never fails HERE for a reason another loader states better.
    """
    document = yaml.safe_load(spec_yaml_path.read_text(encoding="utf-8"))
    return document if isinstance(document, Mapping) else {}


def _game_block(document: Mapping) -> Mapping:
    """The §11 `game` mapping — where `terms` and `knobs` both live."""
    game = document.get("game")
    return game if isinstance(game, Mapping) else {}


def _wants_danger(game: Mapping) -> bool:
    """Does this spec have danger to render?

    Either face counts: a `hazard.*`/`loss.*` term in the closed list, or a
    `danger_tell` that is not `none`. S1's C1 rule makes the two agree on a
    linted spec, so the OR is belt-and-braces — and on the roughly half of the
    corpus that is hazardless it keeps a whole catalog of weak tells out of a
    prompt with nothing to point it at.

    R-25: THE TWO OFFICIAL FIGURES, BOTH TRUE. This docstring used to quote
    one of them ("§3's own opening measurement, ~11 of 25") as if it were the
    only one, which is what the readiness audit caught. They are:

    * LETHALITY prose — **11 of 25** officials (0.44) contain no lethal hazard
      at all; budget exhaustion is the only loss. `spec-v0.3.md:176` ("~11/25
      officials have NO lethal hazard") and `affordance-language.md:81`, which
      names all eleven: ar25, cd82, cn04, ft09, lp85, ls20, tr87, tn36, vc33,
      sb26, re86.
    * MATRIX absence — **16 of 25** officials (0.64) carry no `hazard.*` term
      at all: `mechanics/game-term-matrix.csv`, the three columns
      `hazard.crush` / `hazard.static` / `hazard.timed` empty for ar25, cd82,
      cn04, ft09, lf52, lp85, ls20, re86, s5i5, sb26, sc25, sk48, su15, tr87,
      vc33, wa30.

    THE WEDGE is seven games wide and is a DEFINITION difference, not a defect
    in either source: six games are hazard-term-free without being on the
    lethality list (lf52, s5i5, sc25, sk48, su15, wa30), and tn36 is on the
    lethality list while the matrix gives it a hazard term. wa30 is the
    adjudicated exhibit — its `hazard.static` was ruled ABSENT on the note
    "we can kill the purple block, it can't kill us. it just makes our job
    harder", a nuisance-NPC and not a lethal hazard (`adjudication.md:62`).
    The matrix counts "no hazard ENTITY"; the prose counts "no way to DIE".

    THE RULING (operator, 2026-09-28): `batch.mix.hazardless` STAYS 0.5 and
    hazardless is NOT a conformance axis. 0.5 sits between the two figures
    (0.44 and 0.64), it is a sampling knob rather than a target a batch is
    graded against, and nothing in this pipeline measures a batch's realized
    hazardless share against either number — nor should anything start. Only
    the docs are reconciled: this docstring, `docs/RUNBOOK.md` §2 and the
    `batch.mix` comment in `config/template.yaml` now state both figures.

    Canon-side (duckWM `GEN/`) the two sources still each state one figure.
    That reconciliation is OUT OF SCOPE here — duckWM is read-only from this
    repo — and is flagged for the canon owner.
    """
    terms = game.get("terms")
    if isinstance(terms, list) and any(
        isinstance(term, str) and term.startswith(HAZARD_PREFIXES) for term in terms
    ):
        return True
    knobs = game.get("knobs")
    if not isinstance(knobs, Mapping):
        return False
    tell = knobs.get(_DANGER_KNOB)
    return isinstance(tell, str) and tell.strip().lower() != "none"


def _knob_echoes(game: Mapping, *, danger_quoted: bool) -> list[str]:
    """One echo line per knob the spec declares, in `KNOB_ECHOES` order.

    An absent knob gets no line and no complaint: the §11 linter already owns
    `missing-knobs`, and a payload that raised here would turn a spec defect
    into a stage crash one stage too late.
    """
    knobs = game.get("knobs")
    if not isinstance(knobs, Mapping):
        return []
    lines: list[str] = []
    for knob, template in KNOB_ECHOES.items():
        if knob not in knobs:
            continue
        if knob == _DANGER_KNOB and not danger_quoted:
            continue  # the section its rule lives in is not in this payload
        lines.append(template.format(value=knobs[knob]))
    return lines


def visual_grammar_section(cfg: Mapping, spec_yaml_path: Path) -> tuple[str, list[int]]:
    """The quoted affordance grammar for ONE spec + the section numbers it carries.

    Deterministic like every other payload part: the sections come out of the
    canon in canon order, the knob echoes out of the spec, and nothing reads a
    clock or the environment. The returned numbers are what
    `PayloadReport.visual_sections` records, so a run log says which grammar a
    game was built against.

    THE THREE AUTHORED RULES RIDE HERE (contract B1 / R-03, R-13, R-08), each
    directly under the quoted section it hangs off:

    * `CHROME_IS_STRUCTURE` reads §1/§2's "a board is a place" as a render
      instruction and is unconditional — every board has an edge;
    * `DANGER_STANDS` is §3's, so it rides under exactly the condition §3 does
      (`danger_quoted`). A payload with no danger to render does not carry a
      rule about painting it, which is `_wants_danger`'s whole reason;
    * `REFUSAL_NEVER_BOTH` quotes §6, which is always in `GRAMMAR_SECTIONS`, so
      it is unconditional too.

    WHY HERE and not three more imports in `s2_implement`: contract B1's file
    scope is this module, the §11 linter and the visual gate — `s2_implement`
    is not in it, and its `from .visual_canon import (...)` list is therefore
    frozen for this contract. This function is the ONE payload seam that module
    already calls per spec, and it is the right one on the merits: these rules
    are the authored half of sections quoted a few hundred characters above
    them, and `_knob_echoes` already sets the precedent of appending authored
    lines to the quoted body. Promoting them to their own top-level imports is
    a cosmetic follow-up, flagged rather than smuggled.
    """
    game = _game_block(_spec_document(Path(spec_yaml_path)))
    danger_quoted = _wants_danger(game)

    numbers = sorted({*GRAMMAR_SECTIONS, *([DANGER_SECTION] if danger_quoted else [])})
    sections = load_affordance_sections(cfg, numbers)

    parts = [GRAMMAR_HEADER]
    for number in numbers:
        section = sections[number]
        parts.append(f"_Quoted from {section.source}_")
        parts.append(section.text)
    parts.extend(_knob_echoes(game, danger_quoted=danger_quoted))
    # The three B1 payload blocks (CHROME_IS_STRUCTURE / DANGER_STANDS /
    # REFUSAL_NEVER_BOTH) ride from gen/s2_implement.py, which NAMES each one
    # (prompt-sync: the module that assembles the payload names what it
    # carries — lead-wired at the B1 close). DANGER_STANDS's conditionality
    # travels via the returned section numbers (DANGER_SECTION present when
    # the spec has danger to render).
    return "\n\n".join(parts), numbers
