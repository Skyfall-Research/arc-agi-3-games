"""S3 — the visual report card (contract V-C).

Nothing in the pipeline measures what a generated game LOOKS like. The blind
audit (`s3_verify`) reads mechanics; the gate's own sprite floor asks only for
"not zero" (`s3_gate.FLOORS["sprites_min"]`); the human review at `played` is
the designated judge of legibility — the `s3_gate._check_loc` precedent says so
in as many words ("the judgement goes to the S5 human review bundle with the
rest of the legibility evidence") — and until now it was handed no evidence at
all. This module is that evidence.

RECORD-FIRST, AND THAT IS THE WHOLE DESIGN
------------------------------------------
Every number here is a MEASUREMENT on the record, not a threshold. Exactly one
check in this module can ever hard-fail a game — the level-1 color floor, at
4 colors, which all 25 signed officials clear (`visual_canon` `l1_colors`
min = 4, and m0r0 sits exactly ON the floor) — and contract V-C gives it a
knob that is born in `record` mode. Nothing else rejects, ever.

That asymmetry was measured, not chosen. Three plausible hard checks were
tried against the three human-ACCEPTED b002 games and every one of them
false-failed a shipped game:

* a render-scale statistic false-fails `core-ward-phase-gates` — contract V-C
  records its run-length mode dropping 6 → 1 across its own levels, so no
  single declared scale describes the game. Measured again under the frozen
  definition BELOW (horizontal runs over every row, background rows included)
  the same game swings 64 → 1, which is the same finding stated harder: the
  statistic is scale evidence, not a scale;
* declared-palette-painted false-fails `core-ward-phase-gates` — `you: 11` is
  legitimately absent from the board until the first click;
* HUD-used-at-reset false-fails `convoy-in-the-fog` — its meter fills from
  empty, so the reset frame's strip is honestly blank.

So `declared_absent`, `reserved_on_board`, `hud_strip_*`, `run_length_profile`
and `block_uniformity` are DATA the review reads, and this module states that
on the card itself. Adding a rejection to any of them re-imports a known
false-fail.

THE TWO AUDITED CHECKS (contract W1-A1)
---------------------------------------
The comparative audit measured two defects that are not judgement calls, and
each earned a check with its own knob, born in `record`:

* `field-index` (R-01) — the board's field must be PAINTED in the declared
  `palette.background`, and white `0` is the ecosystem's selection mark, not
  paint (affordance-language.md §9:L239-240, and its REQUIRED line at L252).
  Four of our seven shipped games left the field white; the officials do it on
  6 of 183 level-start boards, all six one game. So the rule is "`0` is not the
  FIELD unless the spec declares it", never "`0` is banned" — a spec that
  declares `background: 0` passes.
* `role-footprint` (R-02) — a declared role's smallest painted component must
  be at least one full logical cell. The acceptance metric is PER-ROLE
  COMPONENT FLOORS and never a corpus-wide confetti share: the officials'
  median `rl_ones_share` is about four times ours, so steering our games at the
  officials' ones_share would push them toward MORE lone pixels, not fewer
  (audit findings.md §B1 — the direction trap).

Both are per-role/per-record MEASUREMENTS first: in `record` they only write the
card, in `fail` they set `passed: false` for the gate runner to act on, exactly
as `l1_color_floor` does. In `off` a check adds NOTHING to the card — not its
verdict, not its per-record fields — which is what keeps a card built with both
knobs off byte-identical to the two b003r2 cards that shipped before they
existed.

THE TWO MORE (contract W1-A2)
-----------------------------
The same audit measured two more defects on the same frames, and each earned a
check on the same pattern:

* `win-render` (R-04) — the settled `WIN` frame must differ legibly from the
  final level's START frame, counted OUTSIDE the declared `hud.reserved`
  geometry. Four of our seven shipped games render no win at all (one's win
  frame is byte-identical to a frame 84 actions earlier; another's difference is
  mostly its HUD). The floor is `visual_canon.WIN_RENDER_FLOOR_CELLS`, and it is
  the officials' 25th percentile rather than their MIN — see that constant for
  why the usual min rule cannot reproduce the audit's verdicts, and what the
  departure costs.
* `declared-vs-painted` (R-06) — the `declared_absent` facts above have been on
  the card since contract V-C and nothing read them. A declared `you`/`goal`/
  `danger` index absent from EVERY captured record is now a violation row; absent
  from only some records stays a recording, because state-dependent roles are
  legitimate. It carries a KNOWN LIMIT on every card it writes: until the R-20
  capture upgrade, "painted in no captured frame" cannot be told apart from
  "painted by no code path", so `gate.declared_vs_painted_exempt` lets a human
  carry that difference in writing.

Both are born in `record` like every knob before them, and `config/template.yaml`
arms both to `fail`. A pin that compares a card against bytes measured before
this contract has to force them `off` by name — `m1_metrics.build_cards` does.

THE DENSITY BAND (contract T-1)
-------------------------------
The parity re-measure (2026-10-06) found our t1 games drawing boards at
0.26x-0.67x the officials' per-level object density on both driver lanes, while
the t2 game held the band. `density` puts that number on the card: the game's
per-level median `objects_pcc` (the OFFICIALS' object definition, reproduced in
`objects_pcc` below) against the officials' 25th percentile, measured off the
comparative audit's pinned table (`visual_canon.OFFICIAL_DENSITY`, derivation
quoted there). The band is t1-SCOPED (`visual_canon.DENSITY_TIERS`): it applies
to a slot whose tier `visual_canon.spec_tier` reads as t1, and for any other
tier — or none — the measured value is still printed beside the band and the
check reports `not-scoped`, never a verdict. Born `record` like every check
before it (the R-06 rule, below): the block is added to every card unless the
config forces `density: off`.

ZERO NEW ENGINE RUNS
--------------------
The input is the frames sidecar S2b already wrote (`worker.frames.json`: the
reset record, one settled record per level transition, and the final record) —
this module never imports the game, never touches `arcengine`, and never
drives a solver. A card is therefore free, deterministic, and safe to build
after a gate that FAILED.

Determinism: no timestamps, no paths inside the payload, `sort_keys=True` on
the json, and a contact sheet whose only inputs are the grids and a pinned
palette. Same frames + same spec ⇒ byte-identical json AND png.

Outputs land in `<spec_dir>/worker.gate/` beside the gate's own two reports
(architecture §2's per-game artifact tree; never inside `worker/`, which runs
a scope check over its own contents).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from statistics import median

import yaml
from PIL import Image

from .s1_spec import (
    CHROME_CUSTOM,
    CHROME_FIELD,
    CHROME_KINDS,
    CHROME_WHERE,
    HAZARD_PREFIXES,
    HUD_RESERVED,
    PALETTE_MAX,
    PALETTE_MIN,
    TINY_TOKEN_FIELD,
)
from .visual_canon import (
    CHROME_EXTENT_BAND,
    DENSITY_FLOOR_OBJECTS,
    DENSITY_MEDIAN_OBJECTS,
    DENSITY_TIERS,
    OFFICIAL_CHROME,
    OFFICIAL_CHROME_SOURCE,
    OFFICIAL_DENSITY,
    OFFICIAL_DENSITY_SOURCE,
    OFFICIAL_GAMES,
    OFFICIAL_HAZARD_ROWS,
    OFFICIAL_VISUAL_CONSTANTS,
    OFFICIAL_WIN_RENDER,
    OFFICIAL_WIN_RENDER_SOURCE,
    WIN_RENDER_FLOOR_CELLS,
    spec_tier,
)

STAGE = "s3-visual"

# --- the file names (architecture §2's tree, pinned not imported) ------------
# `s3_verify.FRAMES_SUFFIX` and `s3_gate.GATE_SUFFIX` are the authorities for
# these two names; both live in modules that pull `gen/backends` or `arcengine`
# and this module must stay import-light enough to run after ANY gate verdict,
# so they are reproduced here with their source named — `s3_gate`'s own reason
# for naming the S2b/S3d verdict vocabularies rather than importing them.
WORKER_DIRNAME = "worker"                      # orchestrator.WORKER_DIRNAME
FRAMES_NAME = "worker.frames.json"             # worker + s3_verify.FRAMES_SUFFIX
GATE_DIRNAME = "worker.gate"                   # worker + s3_gate.GATE_SUFFIX
SPEC_NAME = "spec.yaml"

REPORT_JSON_NAME = "visual-report.json"
REPORT_MD_NAME = "visual-report.md"
CONTACT_SHEET_NAME = "visual-contact-sheet.png"

# --- the knobs (the `tiers.tier_policy` idiom: fail loud, name the key) ------
VISUAL_CARD_MODES = ("off", "record")
L1_FLOOR_MODES = ("record", "fail")
# The two W1-A1 checks carry the full three-mode enum: `off` (silent, and the
# card keeps its pre-W1-A1 bytes), `record` (measure and report), `fail` (the
# verdict the gate runner may reject on).
CHECK_MODES = ("off", "record", "fail")
GATE_KEYS = (
    "visual_card",
    "l1_color_floor",
    "field_index",
    "role_footprint",
    "role_footprint_exempt",
    "win_render",
    "declared_vs_painted",
    "declared_vs_painted_exempt",
    "chrome_extent",
    "danger_visible",
    "density",
)

DEFAULT_VISUAL_CARD = "off"
DEFAULT_L1_FLOOR = "record"
DEFAULT_FIELD_INDEX = "record"
DEFAULT_ROLE_FOOTPRINT = "record"

# W1-A2's two checks are born in `record`, like every mode knob before them
# (`visual_card`, `l1_color_floor`, `field_index`, `role_footprint`). A new
# rejection earns its place on measured data, not on the day it is written — and
# a check born dormant is the exact "a gate that fires and is not acted on"
# pattern R-06 exists to kill (lead adjudication, W1-A2 mid-flight).
#
# The cost, stated where it bites: a check in `record` adds its block to every
# card, including cards built by configs written before it existed. Pins that
# compare a card against bytes measured before W1-A2 must therefore force these
# two modes `off` explicitly — `audit/comparative/scripts/m1_metrics.build_cards`
# does exactly that, so its shipped-card determinism pin keeps comparing like
# with like. `off` remains the mode in which a card carries exactly the keys it
# carried before these checks were written.
DEFAULT_WIN_RENDER = "record"
DEFAULT_DECLARED_VS_PAINTED = "record"

# Contract B1's two, born `record` on the same rule and carrying the same cost:
# a card built by a config written before them gains their blocks unless the
# config forces them `off` by name.
DEFAULT_CHROME_EXTENT = "record"
DEFAULT_DANGER_VISIBLE = "record"
# Contract T-1's band, born `record` on the same rule and carrying the same cost
# — "follow the R-06 precedent exactly": a config that never names `density` gets
# the block on its card, `off` is the one mode that reproduces a pre-T-1 card
# byte for byte, and only `fail` lets the gate runner reject on it.
DEFAULT_DENSITY = "record"

# The check ids as the card and the reports name them, in the dashed spelling
# the rest of the pipeline uses for check ids (`s3_static.LEVEL_COUNT_CHECK`,
# `static.sys-click-truthful`). The CONFIG keys above stay snake_case, like
# every other key in `config/template.yaml`.
FIELD_INDEX_CHECK = "field-index"
ROLE_FOOTPRINT_CHECK = "role-footprint"
# `role-footprint`'s fourth per-role status (contract W2-D): the SPEC declared
# this role a tiny token in `game.palette.tiny_token`. Kept distinct from the
# operator's `exempt` — see `_role_footprint_check` for why the two are not
# collapsed.
EXEMPT_DECLARED_STATUS = "exempt-declared"
WIN_RENDER_CHECK = "win-render"
DECLARED_VS_PAINTED_CHECK = "declared-vs-painted"
CHROME_EXTENT_CHECK = "chrome-extent"
DANGER_VISIBLE_CHECK = "danger-visible"
DENSITY_CHECK = "density"
MODE_OFF = "off"
# `danger-visible`'s per-level status when the spec's own `knobs.danger_tell`
# declares the behaviour — `role-footprint`'s `EXEMPT_DECLARED_STATUS` idiom: the
# level is still MEASURED and still printed, the declaration only stops it
# setting `passed: false`.
DANGER_EXEMPT_DECLARED = "exempt-declared"

# Every check that adds its own top-level block to the card, in the order the
# markdown renders them. ONE tuple so "is any new check armed?" and "which
# section headings change?" can never disagree — the two places that question is
# asked are `render_markdown` and `_reject_block`.
CARD_CHECKS = (
    FIELD_INDEX_CHECK,
    ROLE_FOOTPRINT_CHECK,
    WIN_RENDER_CHECK,
    DECLARED_VS_PAINTED_CHECK,
    CHROME_EXTENT_CHECK,
    DANGER_VISIBLE_CHECK,
    DENSITY_CHECK,
)

# --- the one number that can reject ------------------------------------------
# `visual_canon.OFFICIAL_VISUAL_CONSTANTS["l1_colors"]` is (min, median, max) =
# (4, 7, 11) over the 25 officials' level-1 boards. The floor is the MIN, which
# means it is a bar an official sits exactly on (m0r0), not a bar chosen to be
# comfortable: it rejects a level 1 drawn in three colors or fewer, and nothing
# else. It is derived here so a re-measurement of the corpus moves it.
L1_COLOR_FLOOR = int(OFFICIAL_VISUAL_CONSTANTS["l1_colors"][0])

RESET_LABEL = "reset"

# --- palette roles + HUD geometry --------------------------------------------
# The §11 palette block's role keys, in declaration order (`s1_spec`
# `_schema_palette`): `you`/`goal` mandatory, `danger` nullable, `background`
# optional (contract V-B). A role whose value is not an int is not a
# declaration about the board, so it is skipped rather than reported absent.
PALETTE_ROLES = ("you", "goal", "danger", "background")

# --- R-01: the field, and the index that is not paint -------------------------
# `0` is the ecosystem's selection/highlight mark (affordance-language.md §9,
# L239-240 + the REQUIRED line at L252). `background` is the role that says what
# the field IS, so it is the one role R-01 reads and the three ROLES below are
# the ones R-02 reads — the split is the two contracts', not this module's.
SELECTION_INDEX = 0
FOOTPRINT_ROLES = ("you", "goal", "danger")
assert set(FOOTPRINT_ROLES) | {"background"} == set(PALETTE_ROLES), (
    "FOOTPRINT_ROLES plus `background` must cover exactly PALETTE_ROLES"
)

# The officials' own field distribution, measured over the 183 official
# level-start frames of the comparative audit's pinned table. Quoted into the
# card beside our measured value — `_official_bands`'s rule, one table further
# out: a number on a card is worth nothing without the population behind it.
#
# SOURCE (READ-ONLY input, re-measurable):
#   audit/comparative/data/level-metrics.csv, rows with `corpus == official`
#   (183 level-start frames over the 25 signed games), columns `modal_value`
#   and `colors_list`. That csv is rebuilt by
#   audit/comparative/scripts/m1_metrics.py, whose per-level rule is
#   `audit_common.level_starts` — the same rule `level_start_indices` below
#   reproduces, cross-validated at 183/183 against `features-level.csv`.
OFFICIAL_FIELD_INDEX: dict[str, object] = {
    "levels": 183,
    "games": 25,
    "modal_zero_levels": 6,          # `modal_value` == 0
    "modal_zero_games": ["g50t"],    # all six rows are one game
    "modal_zero_share": 0.0328,      # 6 / 183
    "paints_zero_levels": 148,       # `0` in `colors_list` — 0 is COMMON as a mark
    "paints_zero_share": 0.8087,     # 148 / 183
    "top_modal_indices": [[5, 73], [4, 39], [10, 15]],   # (index, level count)
}
OFFICIAL_FIELD_INDEX_SOURCE = (
    "audit/comparative/data/level-metrics.csv — the 183 `corpus == official` "
    "level-start rows (25 games), columns `modal_value` (the board's field) and "
    "`colors_list` (every index painted). Rebuilt by "
    "audit/comparative/scripts/m1_metrics.py; its official rows cross-check "
    "183/183 against the manual-play corpus's published `features-level.csv`"
)

# --- R-02: how big one logical cell is ----------------------------------------
# `game.render.cell_px` is the spec's ONE declared render scale (contract V-B;
# `s1_spec.RENDER_FIELDS == ("cell_px",)`), and a logical cell is therefore
# cell_px x cell_px grid cells. Four of our seven shipped games declare no
# `render` block at all (b001/b002 predate V-B), so a floor is still needed
# where nothing is declared: 4 px is the SMALLEST logical cell any official
# could have — the smallest tile scale above 1 in
# `OFFICIAL_VISUAL_CONSTANTS["tile_scale_menu"]` is 2, and 2x2 is 4 px. It is
# deliberately the weakest honest floor: it rejects a lone pixel and a 2-px
# hairline and nothing else.
UNDECLARED_CELL_FLOOR_PX = 4
RENDER_CELL_PX = "cell_px"           # s1_spec.RENDER_FIELDS

# --- R-04: how much of the board a win has to move ----------------------------
# The number itself is `visual_canon.WIN_RENDER_FLOOR_CELLS` — measured over the
# 25 officials and interpolated into the S2 payload from the same constant, so
# the bar an implementer is told about is the bar this check applies. The two
# strings below are the card's own account of where it came from and what it
# costs, in the shape `OFFICIAL_FIELD_INDEX_SOURCE` set for R-01.
WIN_RENDER_FLOOR_SOURCE = (
    f"`visual_canon.WIN_RENDER_FLOOR_CELLS` = the 25 signed officials' 25th-percentile "
    f"win-frame delta ({WIN_RENDER_FLOOR_CELLS} of 4096 cells; {OFFICIAL_WIN_RENDER['p25_game']} "
    f"sits exactly on it). NOT the corpus MIN, which is this repo's usual floor rule: the "
    f"min ({OFFICIAL_WIN_RENDER['min']}, {OFFICIAL_WIN_RENDER['min_game']}) is QUIETER than "
    f"the loudest win the comparative audit judged illegible, so a min-derived floor cannot "
    f"reproduce the audit's own verdicts"
)

# The four exhibits contract W1-A2 names plus the three games it does not, all
# measured on the shipped sidecars with the declared `hud.reserved` strip masked
# off — the same computation `_win_render_check` runs. Written onto every card
# so the floor is read beside the population it was cut from.
WIN_RENDER_CALIBRATION: dict[str, object] = {
    "floor_cells": WIN_RENDER_FLOOR_CELLS,
    "measured_on": "the 7 games this pipeline has shipped, board cells only",
    "fails": [
        {"game": "convoy-in-the-fog", "delta": 0,
         "note": "the WIN frame is byte-identical to the level-8 start, 84 actions earlier"},
        {"game": "core-ward-phase-gates", "delta": 22, "note": "no win indicator at all"},
        {"game": "mosaic-marble-bounce-to-match", "delta": 36,
         "note": "pulled at review; 3 levels. Measured, not excused"},
        {"game": "pump-flow-match-glow", "delta": 65,
         "note": "80 cells whole-frame, 15 of them the declared HUD row; 4 of 7 satisfied "
                 "targets are still fog stubs"},
        {"game": "pump-phase-time-echo", "delta": 123,
         "note": "183 cells whole-frame, 60 of them the declared HUD row. The audit read "
                 "the HUD as TWO rows and reported 80 board cells; this check masks only "
                 "the row the spec declares (`hud.reserved: row0`), so it counts 123"},
    ],
    "passes": [
        {"game": "facing-sentinel-match-the-signal-row", "delta": 321},
        {"game": "conduit-watch", "delta": 632,
         "note": "the win flips 10 pips green and 11 beacons to 14 across the board"},
    ],
    "separation": (
        "the illegible wins top out at 123 board cells and the legible ones start at 321, "
        "so the floor sits inside a ~200-cell empirical gap with margin on both sides"
    ),
    "cost_in_officials": (
        f"{len(OFFICIAL_WIN_RENDER['below_floor_games'])} of {OFFICIAL_WIN_RENDER['games']} "
        f"signed officials sit BELOW this floor "
        f"({', '.join(OFFICIAL_WIN_RENDER['below_floor_games'])}; deltas "
        f"{OFFICIAL_WIN_RENDER['below_floor_deltas']}). Stated because it is the price of "
        f"reproducing the audit's verdicts, and because it is why this check is born `off` "
        f"and has to be armed by name"
    ),
}

# --- R-03: how much board a framed game uses ----------------------------------
# The band itself is `visual_canon.CHROME_EXTENT_BAND` — measured over the 25
# officials and interpolated into the S2 payload from the same constant, so the
# band an implementer is told about is the band this check applies
# (`WIN_RENDER_FLOOR_SOURCE`'s rule).
#
# THE UNIT IS THE PER-GAME MEDIAN, not the per-level value, and that is the
# audit's own definition rather than a convenience: an outside-band flag is
# "our game's per-game median ... outside the FULL observed range of the
# officials' per-game medians" (tracks/m1-visual-metrics.md:324). Comparing one
# level against a band cut from whole-game medians would compare two different
# statistics; comparing medians to medians is why re86 sits ON the floor.
CHROME_EXTENT_LOW, CHROME_EXTENT_HIGH = CHROME_EXTENT_BAND
CHROME_EXTENT_SOURCE = (
    f"`visual_canon.CHROME_EXTENT_BAND` = min..max of the 25 signed officials' PER-GAME "
    f"`occupied_extent` medians ({CHROME_EXTENT_LOW}, {OFFICIAL_CHROME['band_low_game']} .. "
    f"{CHROME_EXTENT_HIGH}, {OFFICIAL_CHROME['band_high_game']}; corpus median "
    f"{OFFICIAL_CHROME['band_median']}). The floor is the corpus MIN — this repo's usual "
    f"floor rule, restored: unlike `win-render`'s 25th percentile it costs no official, "
    f"because every one of the 25 is inside the band by construction"
)

# What the check is calibrated against, written onto every card it builds so the
# band is read beside the population it was cut from (`WIN_RENDER_CALIBRATION`'s
# shape). Measured on the same 7 shipped games, level-start frames only.
CHROME_EXTENT_CALIBRATION: dict[str, object] = {
    "band": [CHROME_EXTENT_LOW, CHROME_EXTENT_HIGH],
    "measured_on": "the 7 games this pipeline has shipped, level-start frames only",
    "ours_median": OFFICIAL_CHROME["ours_median"],
    "ours_ratio": OFFICIAL_CHROME["ours_ratio"],
    "below_band": [
        {"game": game, "median": value}
        for game, value in zip(OFFICIAL_CHROME["ours_below_band"],
                               OFFICIAL_CHROME["ours_below_band_medians"], strict=True)
    ],
    "authored_decor_objects": OFFICIAL_CHROME["ours_authored_decor_objects"],
    "official_decor_rows": OFFICIAL_CHROME["official_decor_rows"],
    "pairing": (
        "the acceptance is PAIRED and neither leg can fail a game alone: a game is rejected "
        "only when its per-game `occupied_extent` median is BELOW the officials' band AND it "
        "declares no `game.chrome` at all. The pairing is the audit contract's own design — "
        "chrome that is not load-bearing inflates extent without improving legibility, so "
        "padding the board satisfies one leg and declaring chrome nobody drew satisfies the "
        "other, and neither clears the check"
    ),
    "above_band_note": (
        "ABOVE the band is RECORDED and never a violation. The audit's band is two-sided and "
        "the R-03 acceptance asks for a median INSIDE it, but the measured defect is emptiness "
        "— no shipped game is above — so a rejection on the high side would be a threshold "
        "with no exhibit behind it, which is the false-fail this module's whole design refuses"
    ),
}

# --- T-1: how many objects an official LEVEL carries ---------------------------
# The numbers are `visual_canon.OFFICIAL_DENSITY` — measured off the comparative
# audit's pinned table and interpolated into the S2 payload's density section
# from the same constant, so the floor an implementer is told about is the floor
# this check applies (`WIN_RENDER_FLOOR_SOURCE`'s rule). The derivation, and why
# the 25th percentile is interpolation-invariant where the 75th is not, is quoted
# at that constant.
DENSITY_FLOOR_SOURCE = (
    f"`visual_canon.DENSITY_FLOOR_OBJECTS` = the 25th percentile of `objects_pcc` over "
    f"the {OFFICIAL_DENSITY['levels']} official level-start boards ({DENSITY_FLOOR_OBJECTS}; "
    f"every interpolation method agrees). Median {DENSITY_MEDIAN_OBJECTS}; "
    f"{OFFICIAL_DENSITY['levels_below_p25']} of {OFFICIAL_DENSITY['levels']} official boards "
    f"sit below the floor. No ceiling: the measured defect is emptiness, and the 75th "
    f"percentile moves with the interpolation method"
)

# What the band is calibrated against, written onto every card the check builds
# (`CHROME_EXTENT_CALIBRATION`'s shape). The officials' half is the SAME
# comparison this check makes — each official's per-level median against the
# floor — run over all 25; ours is the parity re-measure's t1/t2 split. No entry
# below carries `passed` or `status`: the orchestrator quotes every node that
# does into a rebuild prompt, and a calibration row is not this game failing.
DENSITY_CALIBRATION: dict[str, object] = {
    "floor": DENSITY_FLOOR_OBJECTS,
    "officials": {
        "games": OFFICIAL_DENSITY["games"],
        "games_at_or_above_floor": (
            int(OFFICIAL_DENSITY["games"]) - len(OFFICIAL_DENSITY["games_below_floor"])
        ),
        "below_floor": [
            {"game": game, "median": value}
            for game, value in zip(OFFICIAL_DENSITY["games_below_floor"],
                                   OFFICIAL_DENSITY["games_below_floor_medians"], strict=True)
        ],
        "on_floor": list(OFFICIAL_DENSITY["games_on_floor"]),
        "levels": OFFICIAL_DENSITY["levels"],
        "levels_below_floor": OFFICIAL_DENSITY["levels_below_p25"],
    },
    "ours_t1": [
        {"game": game, "median": value, "below_floor": value < DENSITY_FLOOR_OBJECTS}
        for game, value in OFFICIAL_DENSITY["ours_t1"].items()
    ],
    "ours_t2": [
        {"game": game, "median": value, "below_floor": value < DENSITY_FLOOR_OBJECTS}
        for game, value in OFFICIAL_DENSITY["ours_t2"].items()
    ],
    "unit": (
        "the game's PER-LEVEL MEDIAN against the officials' per-level distribution, never "
        "every level: the officials open lighter themselves (level-1 median "
        f"{OFFICIAL_DENSITY['l1_median']}), so one sparse teaching level is the corpus's own "
        "habit and not the defect"
    ),
    "scope": (
        f"the band applies to tier(s) {', '.join(DENSITY_TIERS)} only — the parity re-measure "
        "found the gap at t1 on both driver lanes while the t2 game held the band. Any other "
        "tier, or a slot whose tier cannot be read, is measured and printed and reports "
        "`not-scoped`"
    ),
    "price": (
        f"{len(OFFICIAL_DENSITY['games_below_floor'])} of {OFFICIAL_DENSITY['games']} signed "
        f"officials sit below this floor by their own per-level median — the percentile "
        f"floor's honest cost (`win-render`'s precedent: 6 of 25 there)"
    ),
}

# The chrome region geometry (the `HUD_STRIP_GEOMETRY` idiom): `where` names a
# band along an edge, or the full ring. DEPTH is the spec's own declared logical
# cell (`game.render.cell_px`) and NOT a guess — a game that declares no render
# scale is measured at depth 1, the exact outermost line, and the card says the
# coverage it reports is a LOWER BOUND rather than a number measured against an
# invented band width.
CHROME_DEPTH_FALLBACK_PX = 1
CHROME_EDGES = ("top", "bottom", "left", "right")
CHROME_BORDER = "border"
# The enum and the geometry are one contract, the assert `HUD_STRIP_GEOMETRY`
# carries: a `where` token the §11 schema admits but this module cannot place
# would silently become "not-checked" without anyone noticing.
assert set(CHROME_EDGES) | {CHROME_BORDER, CHROME_CUSTOM} == set(CHROME_WHERE), (
    "CHROME_EDGES plus 'border' and CHROME_CUSTOM must cover exactly s1_spec.CHROME_WHERE"
)

# --- R-13: the grey ramp, and what "lighter" means ----------------------------
# The ARC render palette's achromatic entries, DERIVED from the pinned palette
# rather than listed: an index is on the grey ramp when its RGB triple is
# achromatic. Deriving it means a re-transcription of `ARC_PALETTE_HEX` moves the
# ramp with it, and it is the honest definition of "grey" — indices 6-15 all
# carry colour.
#
# CONCEAL_TERMS is deliberately ONE term. `info.fog` is the only §3 vocabulary
# entry canon defines as a conceal/reveal PAIR — "board state concealed until
# revealed by position/act". The neighbours are excluded on their own
# definitions, not for convenience: `info.hidden_geometry` renders AS the
# background (there is no second index to order), `info.probe` reveals state
# TRANSIENTLY (no settled frame carries the pair), and `info.viewport` moves a
# window rather than lifting a veil.
CONCEAL_TERMS = ("info.fog",)

# The frames sidecar writes `state` as the engine enum's NAME (gen/frames.py
# `"state": r.state`), so the terminal state is this string. Pinned rather than
# imported for the same reason the file names above are: this module must stay
# import-light enough to run after ANY gate verdict, and `gen.frames` pulls
# `arcengine`. `audit_common.WIN_STATE` pins the identical string.
WIN_STATE = "WIN"

# `hud.reserved` is a closed enum in the §11 schema; three of its four values
# name a strip this module can find on a 64x64 grid, and the fourth
# (`custom-rect`) names a geometry the spec does not carry, so the reserved-
# index check is SKIPPED rather than guessed at.
HUD_CUSTOM_RECT = "custom-rect"
HUD_STRIP_GEOMETRY: dict[str, tuple[str, int]] = {
    "row63": ("row", 63),
    "row0": ("row", 0),
    "col0": ("col", 0),
}
HUD_NOT_CHECKED = f"not-checked ({HUD_CUSTOM_RECT})"

# The enum and the geometry table are one contract: a strip token the schema
# admits but this table does not know would silently become "not-checked".
assert set(HUD_STRIP_GEOMETRY) | {HUD_CUSTOM_RECT} == set(HUD_RESERVED), (
    "HUD_STRIP_GEOMETRY plus 'custom-rect' must cover exactly s1_spec.HUD_RESERVED"
)

# --- the block-uniformity curve ----------------------------------------------
# The official tile-scale menu is `OFFICIAL_VISUAL_CONSTANTS["tile_scale_menu"]`
# = (1, 2, 3, 4, 5, 8). Scale 1 is dropped because every grid is trivially 1.0
# uniform at 1x1 blocks — it measures nothing.
BLOCK_SIZES = tuple(
    int(scale) for scale in OFFICIAL_VISUAL_CONSTANTS["tile_scale_menu"] if int(scale) > 1
)

# --- the render palette (pinned, transcribed, verified) -----------------------
# The authoritative render palette is `PALETTE` in the canon's own
# `duckWM/local-docs/arc-agi-3-generator/tools/capture_frames.py:60-65` (16 RGB
# triples, index 0-15). Transcribed here as hex, entry for entry, because the
# canon is a READ-ONLY dependency that this module must not import code from:
#   0 (255,255,255) 1 (204,204,204) 2 (153,153,153) 3 (102,102,102)
#   4 (51,51,51)    5 (0,0,0)       6 (229,58,163)  7 (255,123,204)
#   8 (249,60,49)   9 (30,147,255)  10 (136,216,241) 11 (255,220,0)
#   12 (255,133,27) 13 (146,18,49)  14 (79,204,48)  15 (163,86,214)
ARC_PALETTE_HEX: tuple[str, ...] = (
    "#FFFFFF", "#CCCCCC", "#999999", "#666666",
    "#333333", "#000000", "#E53AA3", "#FF7BCC",
    "#F93C31", "#1E93FF", "#88D8F1", "#FFDC00",
    "#FF851B", "#921231", "#4FCC30", "#A356D6",
)
assert len(ARC_PALETTE_HEX) == PALETTE_MAX - PALETTE_MIN + 1, (
    "ARC_PALETTE_HEX must carry one entry per §11 palette index"
)


def palette_luminance(index: int) -> int:
    """One palette index's luminance, 0 (black) to 255 (white).

    The ramp indices are achromatic, so the red channel IS the luminance and no
    weighting is needed or invented; the function is defined over the whole
    palette anyway (taking the mean of the three channels) so a caller that
    reaches it with a coloured index gets a number rather than a lie.
    """
    hex_value = ARC_PALETTE_HEX[max(PALETTE_MIN, min(PALETTE_MAX, int(index)))].lstrip("#")
    channels = [int(hex_value[at:at + 2], 16) for at in (0, 2, 4)]
    return sum(channels) // len(channels)


# The achromatic entries of the palette above, in index order — 0 white through
# 5 black. DERIVED, not listed (see the R-13 block): an index is on the ramp when
# its three channels agree.
GREY_RAMP: tuple[int, ...] = tuple(
    index for index, value in enumerate(ARC_PALETTE_HEX)
    if len({value.lstrip("#")[at:at + 2] for at in (0, 2, 4)}) == 1
)
assert GREY_RAMP == (0, 1, 2, 3, 4, 5), (
    f"the ARC grey ramp is indices 0-5 (affordance §9's structural colours), got {GREY_RAMP}"
)

# Contact sheet geometry (contract V-C §1): 2 px per cell, 4 px of white
# between tiles, one horizontal strip.
SHEET_CELL_PX = 2
SHEET_GUTTER_PX = 4
SHEET_GUTTER_RGB = (255, 255, 255)


# --- knob parsing -------------------------------------------------------------


def _gate_block(cfg: Mapping) -> Mapping:
    """The `gate:` config block, key-checked — or an empty mapping when absent.

    Closed key set on purpose (the `tiers.tier_policy` rule): these knobs are
    read at the gate, long after the batch has started spending, so a typo that
    silently defaulted would look exactly like a card that was never wanted.
    """
    raw = cfg.get("gate") if isinstance(cfg, Mapping) else None
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError(  # noqa: TRY004 — a config defect; the whole block reports ValueError
            f"gate must be a mapping of gate knobs, got {raw!r}"
        )
    unknown = sorted(str(key) for key in set(raw) - set(GATE_KEYS))
    if unknown:
        raise ValueError(f"gate names unknown keys {unknown} (expected {list(GATE_KEYS)})")
    return raw


def _enum_key(raw: Mapping, key: str, allowed: tuple[str, ...], default: str) -> str:
    value = raw.get(key, default)
    if value not in allowed:
        raise ValueError(f"gate.{key} must be one of {list(allowed)}, got {value!r}")
    return value


def visual_card_mode(cfg: Mapping) -> str:
    """`gate.visual_card` — `off` (the default: the gate never calls the card)."""
    return _enum_key(_gate_block(cfg), "visual_card", VISUAL_CARD_MODES, DEFAULT_VISUAL_CARD)


def l1_floor_mode(cfg: Mapping) -> str:
    """`gate.l1_color_floor` — `record` (the default) or `fail`.

    `record` measures and reports; `fail` lets the ONE hard check in this
    module reject. The default is `record` because a new rejection has to earn
    its place on measured data, not on the day it is written.
    """
    return _enum_key(_gate_block(cfg), "l1_color_floor", L1_FLOOR_MODES, DEFAULT_L1_FLOOR)


def field_index_mode(cfg: Mapping) -> str:
    """`gate.field_index` — `off` | `record` (the default) | `fail` (R-01).

    `off` is not "measure and ignore": it removes the check's fields from the
    card entirely, which is how a card built today reproduces a card built
    before this check existed, byte for byte.
    """
    return _enum_key(_gate_block(cfg), "field_index", CHECK_MODES, DEFAULT_FIELD_INDEX)


def role_footprint_mode(cfg: Mapping) -> str:
    """`gate.role_footprint` — `off` | `record` (the default) | `fail` (R-02)."""
    return _enum_key(_gate_block(cfg), "role_footprint", CHECK_MODES, DEFAULT_ROLE_FOOTPRINT)


def win_render_mode(cfg: Mapping) -> str:
    """`gate.win_render` — `off` | `record` (the default) | `fail` (R-04)."""
    return _enum_key(_gate_block(cfg), "win_render", CHECK_MODES, DEFAULT_WIN_RENDER)


def declared_vs_painted_mode(cfg: Mapping) -> str:
    """`gate.declared_vs_painted` — `off` | `record` (the default) | `fail` (R-06).

    KNOWN LIMIT, and the check says it on every card it writes: the frames
    sidecar records the reset, one settled frame per level transition and the
    final frame. A role absent from all of them is absent from every frame this
    pipeline CAPTURED, which is not the same claim as absent from every code
    path — `conduit-watch` paints `palette.you` (its selection colour) in code
    and appears in no settled record, because every record is a fresh or a
    finished board. Until the R-20 capture upgrade widens what is recorded, the
    difference is not measurable here, which is what
    `gate.declared_vs_painted_exempt` exists to carry.
    """
    return _enum_key(_gate_block(cfg), "declared_vs_painted", CHECK_MODES,
                     DEFAULT_DECLARED_VS_PAINTED)


def chrome_extent_mode(cfg: Mapping) -> str:
    """`gate.chrome_extent` — `off` | `record` (the default) | `fail` (R-03).

    PAIRED acceptance, and the pairing is stated here because it is the whole
    design: `fail` rejects only when the game's per-game `occupied_extent`
    median is BELOW the officials' band AND the spec declares no `game.chrome`.
    Neither leg can reject alone — an empty board that was framed on purpose is
    a style, and a declared chrome list on a board already inside the band is
    nothing to complain about.
    """
    return _enum_key(_gate_block(cfg), "chrome_extent", CHECK_MODES, DEFAULT_CHROME_EXTENT)


def danger_visible_mode(cfg: Mapping) -> str:
    """`gate.danger_visible` — `off` | `record` (the default) | `fail` (R-13)."""
    return _enum_key(_gate_block(cfg), "danger_visible", CHECK_MODES, DEFAULT_DANGER_VISIBLE)


def density_mode(cfg: Mapping) -> str:
    """`gate.density` — `off` | `record` (the default) | `fail` (contract T-1).

    TIER-SCOPED, and the scope is stated here because it decides what `fail`
    can do: the band applies only to a slot whose tier is in
    `visual_canon.DENSITY_TIERS` (t1). Any other tier, or a tier nobody can
    read, is measured and printed and reports `passed: true` — so `fail` can
    reject a t1 game under the officials' floor and nothing else.
    """
    return _enum_key(_gate_block(cfg), "density", CHECK_MODES, DEFAULT_DENSITY)


def declared_vs_painted_exempt(cfg: Mapping) -> dict[tuple[str, str], str]:
    """`gate.declared_vs_painted_exempt` — {(game, role): rationale}.

    R-06's escape hatch, and it carries a WRITTEN REASON where
    `role_footprint_exempt` (a two-part `<game>:<role>` token) does not. The
    asymmetry is the R-20 limit, not a house style:

    * a role-footprint exemption asserts something the check itself can see — a
      token IS 1 px, the card prints the number, and the exemption only says a
      human looked at it and meant it;
    * a declared-vs-painted exemption asserts something the check CANNOT see —
      that the role is painted by a code path no captured frame settles on. The
      frames are silent, so the human's sentence is the only evidence there is,
      and an exemption with no sentence would be indistinguishable from a
      violation somebody wanted to stop seeing.

        gate:
          declared_vs_painted_exempt:
            - "conduit-watch:you:selection colour, painted only while a cell is
               held; no settled record catches it (R-20 capture upgrade)"

    `<game>` is the sidecar's `game_id` (the slug), `<role>` is one of
    `FOOTPRINT_ROLES`, and everything after the second colon is the rationale,
    which must be non-empty. An exempted role is still MEASURED and still
    printed on the card with its reason — the exemption only stops it setting
    `passed: false`.

    Loud on every malformed entry (`role_footprint_exempt`'s rule: a typo must
    not silently exempt nothing, or silently exempt everything). Default: empty.
    """
    raw = _gate_block(cfg).get("declared_vs_painted_exempt", ())
    if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
        raise ValueError(  # noqa: TRY004 — a config defect; the block reports ValueError
            f"gate.declared_vs_painted_exempt must be a list of "
            f"'<game_id>:<role>:<why>' entries, got {raw!r}"
        )
    out: dict[tuple[str, str], str] = {}
    for entry in raw:
        game, separator, rest = str(entry).partition(":")
        role, reason_separator, rationale = rest.partition(":")
        if (not separator or not reason_separator or not game.strip()
                or role.strip() not in FOOTPRINT_ROLES or not rationale.strip()):
            raise ValueError(
                f"gate.declared_vs_painted_exempt entry {entry!r} is not "
                f"'<game_id>:<role>:<why>' with role in {list(FOOTPRINT_ROLES)} and a "
                f"non-empty reason — this check cannot see what the exemption claims "
                f"(the R-20 capture limit), so an exemption nobody explained is not a "
                f"declaration"
            )
        out[(game.strip(), role.strip())] = " ".join(rationale.split())
    return out


def role_footprint_exempt(cfg: Mapping) -> frozenset[tuple[str, str]]:
    """`gate.role_footprint_exempt` — the OPERATOR's tiny tokens, as (game, role).

    THE SECOND OF TWO EXEMPTIONS, and the later one to fire. R-02's escape
    hatch used to have nowhere else to live — `s1_spec._schema_palette` admitted
    no field for "this role is deliberately a 1-px token", and inventing one
    inside `game.render` would have been a key the linter itself calls "not a
    §11 field (ignored downstream)". Contract W2-D gave it a §11 home
    (`game.palette.tiny_token`, read here by `_spec_tiny_token`), so the SPEC's
    author can now declare it up front and the reported status says who did:
    `exempt-declared` for the spec, `exempt` for this list.

    THIS KNOB STAYS, and it is the OPERATOR OVERRIDE. It is what covers the
    seven already-shipped games, whose specs were written before the field
    existed and are not re-specced to add one; and it is the only lever for a
    game whose spec is wrong about itself — a spec that declared no tiny token
    and produced one, where the human looks at the number on the card and
    decides to accept it anyway. A spec-side declaration cannot do that job,
    because by then the spec is the thing under review. One entry per exempted
    thing:

        gate:
          role_footprint_exempt: [conduit-watch:you]

    `<game>` is the sidecar's own `game_id` (which is the slug) and `<role>` is
    one of `FOOTPRINT_ROLES`. An exempted role is still MEASURED and still
    written to the card — the exemption only stops it setting `passed: false`,
    so a declared token can never hide its own size. That is true of both
    exemptions: the spec-side declaration buys a status, never silence.

    Loud on every malformed entry (the `exempt_terms` rule: a typo must not
    silently exempt nothing, or silently exempt everything). Default: empty —
    canon is that nothing is exempt.
    """
    raw = _gate_block(cfg).get("role_footprint_exempt", ())
    if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
        raise ValueError(  # noqa: TRY004 — a config defect; the block reports ValueError
            f"gate.role_footprint_exempt must be a list of '<game_id>:<role>' entries, "
            f"got {raw!r}"
        )
    pairs: set[tuple[str, str]] = set()
    for entry in raw:
        game, separator, role = str(entry).partition(":")
        if not separator or not game.strip() or role.strip() not in FOOTPRINT_ROLES:
            raise ValueError(
                f"gate.role_footprint_exempt entry {entry!r} is not '<game_id>:<role>' with "
                f"role in {list(FOOTPRINT_ROLES)} — an exemption nobody can read is not a "
                f"declaration"
            )
        pairs.add((game.strip(), role.strip()))
    return frozenset(pairs)


# --- paths --------------------------------------------------------------------


def card_paths(spec_dir: Path | str) -> dict[str, Path]:
    """The card's three files under `<spec_dir>/worker.gate/`."""
    gate_dir = Path(spec_dir) / GATE_DIRNAME
    return {
        "json": gate_dir / REPORT_JSON_NAME,
        "md": gate_dir / REPORT_MD_NAME,
        "contact_sheet": gate_dir / CONTACT_SHEET_NAME,
    }


# --- inputs -------------------------------------------------------------------


def _malformed(path: Path, detail: str) -> ValueError:
    """ONE exception family for a defective sidecar, built rather than raised.

    Every shape complaint in this module reports `ValueError`, whatever kind of
    wrongness it found — the caller (the gate runner) catches a card failure and
    records it as evidence, so the family is what matters and a split between
    `TypeError` and `ValueError` would only make that catch wider.
    """
    return ValueError(
        f"{path}: {detail} — the visual card reads S2b's frames sidecar "
        f"({{game_id, source, records: [{{label, seq, levels_completed, state, grid}}]}})"
    )


def _load_frames(spec_dir: Path) -> Mapping:
    """The frames sidecar S2b wrote, shape-checked.

    A missing sidecar is a `FileNotFoundError` by contract: the gate runner
    guards the call, and a card that quietly reported nothing would be
    indistinguishable from a game with nothing wrong.
    """
    path = spec_dir / FRAMES_NAME
    if not path.is_file():
        raise FileNotFoundError(
            f"{spec_dir}: no frames sidecar at {path} — the visual card measures the frames "
            f"S2b already captured and never runs the game (contract V-C §1)"
        )
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise _malformed(path, "the sidecar did not parse to a mapping")
    records = document.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)) or not records:
        raise _malformed(path, "the sidecar carries no non-empty `records` list")
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise _malformed(path, f"record {index} is not a mapping")
        _grid(record, path, index)
    return document


def _grid(record: Mapping, path: Path, index: int) -> list[list[int]]:
    """One record's grid as rows of ints — rectangular or it is not a grid."""
    grid = record.get("grid")
    if not isinstance(grid, list) or not grid:
        raise _malformed(path, f"record {index} carries no `grid`")
    widths = set()
    rows: list[list[int]] = []
    for row in grid:
        if not isinstance(row, list) or not row:
            raise _malformed(path, f"record {index} has a grid row that is not a non-empty list")
        for value in row:
            if isinstance(value, bool) or not isinstance(value, int):
                raise _malformed(path, f"record {index} has a non-int grid cell {value!r}")
        widths.add(len(row))
        rows.append(list(row))
    if len(widths) != 1:
        raise _malformed(path, f"record {index} grid is ragged (row widths {sorted(widths)})")
    return rows


def _spec_tiny_token(palette: Mapping) -> frozenset[str]:
    """`game.palette.tiny_token` — the roles the SPEC declares it draws small.

    Contract W2-D: R-02's exception now has a §11 home (`s1_spec`
    `TINY_TOKEN_FIELD`), so the declaration can come from whoever wrote the
    spec instead of only from an operator editing batch config after the game
    exists. This reader keeps `_spec_visuals`' rule — quiet about shape, since
    S1's schema already kills a `tiny_token` that is not a non-empty list of
    distinct known roles — and keeps only roles this check actually measures,
    so a malformed declaration exempts nothing rather than everything.
    """
    declared = palette.get(TINY_TOKEN_FIELD)
    if not isinstance(declared, list):
        return frozenset()
    return frozenset(role for role in declared if role in FOOTPRINT_ROLES)


def _spec_visuals(spec_dir: Path) -> tuple[Mapping, Mapping, Mapping]:
    """`game.palette`, `game.hud` and `game.render` from the spec — quiet about shape.

    `visual_canon._spec_document`'s rule applies unchanged: a spec that does not
    parse to the §11 shape has already been caught by S1's linter and by S2's
    payload loader, so a defect must not be re-reported HERE, one stage later
    and in worse words. A missing `spec.yaml` raises (the read does), because
    the palette and HUD lines would otherwise read as "nothing declared".
    """
    document = yaml.safe_load((spec_dir / SPEC_NAME).read_text(encoding="utf-8"))
    game = document.get("game") if isinstance(document, Mapping) else None
    game = game if isinstance(game, Mapping) else {}
    palette = game.get("palette")
    hud = game.get("hud")
    render = game.get("render")
    return (palette if isinstance(palette, Mapping) else {},
            hud if isinstance(hud, Mapping) else {},
            render if isinstance(render, Mapping) else {})


def _spec_declarations(spec_dir: Path) -> dict:
    """`game.chrome`, `game.knobs` and the level curriculum — quiet about shape.

    A SECOND reader beside `_spec_visuals` rather than a wider return from it:
    that function's three-tuple is what four call sites and every pin already
    expect, and re-parsing one small yaml costs nothing measurable next to the
    frames sidecar this module also reads.

    Quiet about shape for `_spec_visuals`' reason — S1's linter and S2's payload
    loader have both already refused a malformed §11 — and with the
    `_spec_tiny_token` consequence made explicit: a chrome entry this reader
    cannot parse declares NOTHING. It is dropped rather than counted, so a
    malformed declaration can never buy the pairing's second leg.
    """
    document = yaml.safe_load((spec_dir / SPEC_NAME).read_text(encoding="utf-8"))
    game = document.get("game") if isinstance(document, Mapping) else None
    game = game if isinstance(game, Mapping) else {}

    raw_chrome = game.get(CHROME_FIELD)
    chrome: list[dict] = []
    if isinstance(raw_chrome, list):
        for entry in raw_chrome:
            if not isinstance(entry, Mapping):
                continue
            kind, where = entry.get("kind"), entry.get("where")
            if kind in CHROME_KINDS and where in CHROME_WHERE:
                chrome.append({"kind": kind, "where": where})

    knobs = game.get("knobs")
    terms = game.get("terms")
    levels = game.get("levels")
    return {
        CHROME_FIELD: chrome,
        "knobs": knobs if isinstance(knobs, Mapping) else {},
        "terms": [term for term in terms if isinstance(term, str)] if isinstance(terms, list)
        else [],
        "levels": levels if isinstance(levels, list) else [],
    }


def _hazard_start_level(levels: Sequence) -> int | None:
    """The first level whose `terms_introduced` names a hazard term, 1-based.

    `None` means no level introduces one, which this module reads as "the
    declared danger is a STANDING declaration" — every level is in scope. That
    is the honest default: `palette.danger` is a game-level declaration and the
    curriculum is the only thing that could ever narrow it, so a curriculum that
    says nothing narrows nothing.
    """
    for position, level in enumerate(levels, start=1):
        if not isinstance(level, Mapping):
            continue
        entries = level.get("terms_introduced")
        if not isinstance(entries, list):
            continue
        if any(isinstance(term, str) and term.startswith(HAZARD_PREFIXES) for term in entries):
            return position
    return None


def _declared_indices(palette: Mapping) -> dict[str, int]:
    """The role → index map, keeping only roles declared as an int.

    `danger: null` is a §11 value meaning "this game has no danger" and an
    absent `background` means "unstated" (canon default black-5) — neither is a
    claim about what is painted, so neither can be absent from a board.
    """
    declared: dict[str, int] = {}
    for role in PALETTE_ROLES:
        value = palette.get(role)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        declared[role] = value
    return declared


def _reserved_indices(palette: Mapping) -> list[int]:
    reserved = palette.get("reserved")
    if not isinstance(reserved, list):
        return []
    return [v for v in reserved if isinstance(v, int) and not isinstance(v, bool)]


def _strip_token(hud: Mapping) -> str | None:
    """The `hud.reserved` token when this module can find its strip, else None."""
    token = hud.get("reserved")
    return token if isinstance(token, str) and token in HUD_STRIP_GEOMETRY else None


# --- the frozen metrics (pure functions, one grid in) -------------------------


def colors(grid: Sequence[Sequence[int]]) -> list[int]:
    """The sorted distinct palette indices painted on this board."""
    return sorted({value for row in grid for value in row})


def modal_value(grid: Sequence[Sequence[int]]) -> int:
    """The most common index on the board; ties go to the SMALLER index.

    This stands in for "background" in `objects_cc` on purpose: a declared
    `palette.background` may legitimately be absent from a board (the contract
    V-C measurement that killed declared-palette-painted as a hard check), and
    a component count taken against an absent value counts the whole board.
    """
    counts = Counter(value for row in grid for value in row)
    return min(counts.items(), key=lambda item: (-item[1], item[0]))[0]


def objects_cc(grid: Sequence[Sequence[int]]) -> int:
    """4-connected components of the cells that are NOT the modal value.

    The official corpus's own `objects` column counts connected non-background
    regions (`features-schema.md`); this is that count with the modal value
    standing in for a background the spec may not have declared. Flood fill is
    iterative — a 64x64 board of one non-modal blob would blow a recursive one.
    """
    background = modal_value(grid)
    height, width = len(grid), len(grid[0])
    seen = [[False] * width for _ in range(height)]
    found = 0
    for y in range(height):
        for x in range(width):
            if seen[y][x] or grid[y][x] == background:
                continue
            found += 1
            stack = [(y, x)]
            seen[y][x] = True
            while stack:
                cy, cx = stack.pop()
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < height and 0 <= nx < width and not seen[ny][nx] \
                            and grid[ny][nx] != background:
                        seen[ny][nx] = True
                        stack.append((ny, nx))
    return found


def run_length_profile(grid: Sequence[Sequence[int]]) -> dict:
    """Horizontal run lengths over every row: {mode, median, ones_share}.

    The render-scale statistic, and the reason it is DATA: a board drawn at
    tile scale s tends to a run-length mode of s, but `core-ward-phase-gates`
    — human-accepted — does not hold one across its own levels (contract V-C
    measured 6 → 1; measured here, with background rows counted as the
    definition says, 64 → 1). Every row counts, including uniform ones, so a
    sparse board's mode is its board width: that is honest about the board and
    useless as a gate, which is exactly why it only ever records.

    `ones_share` is the share of runs a single cell long — the "1x1 confetti"
    tell the reference pipeline's render craft warns about, again as a number.
    Mode ties go to the SHORTER run, so the statistic never flatters a board.
    """
    lengths: list[int] = []
    for row in grid:
        run = 1
        for previous, value in pairwise(row):
            if value == previous:
                run += 1
            else:
                lengths.append(run)
                run = 1
        lengths.append(run)
    counts = Counter(lengths)
    mode = min(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    ones = counts.get(1, 0)
    return {
        "mode": mode,
        "median": median(lengths),
        "ones_share": round(ones / len(lengths), 4),
    }


def block_uniformity(grid: Sequence[Sequence[int]]) -> dict[str, float]:
    """For each official tile scale: the share of aligned s x s blocks that are flat.

    A CURVE, never a verdict — read it beside `run_length_profile`. A board
    genuinely drawn at scale s shows a shelf at s; a board of 1x1 confetti
    decays immediately. Remainder rows/columns are ignored (the blocks are
    origin-aligned, exactly as a scale-s renderer lays them down).
    """
    height, width = len(grid), len(grid[0])
    curve: dict[str, float] = {}
    for size in BLOCK_SIZES:
        rows, cols = height // size, width // size
        if not rows or not cols:
            curve[str(size)] = 0.0
            continue
        flat = 0
        for by in range(rows):
            for bx in range(cols):
                first = grid[by * size][bx * size]
                if all(
                    grid[by * size + dy][bx * size + dx] == first
                    for dy in range(size)
                    for dx in range(size)
                ):
                    flat += 1
        curve[str(size)] = round(flat / (rows * cols), 4)
    return curve


def declared_absent(grid: Sequence[Sequence[int]], palette: Mapping) -> list[str]:
    """Declared roles whose index is not painted on THIS board. Data, never a verdict.

    Measured false-fail (contract V-C): `core-ward-phase-gates` declares
    `you: 11` and does not paint it until the first click, and the game was
    human-accepted. An absent role is a question for the review, not an answer.
    """
    painted = {value for row in grid for value in row}
    declared = _declared_indices(palette)
    return [role for role in PALETTE_ROLES
            if role in declared and declared[role] not in painted]


# --- the W1-A1 metrics (pure functions, one grid in) --------------------------


def index0_share(grid: Sequence[Sequence[int]]) -> float:
    """Share of cells painted white `0` — the ecosystem's selection index.

    DATA on its own: `0` is common in the official corpus as a MARK (it is
    painted somewhere on 148 of 183 official level-start boards) and the defect
    R-01 names is `0` being the FIELD, which `modal_value` decides. A high share
    beside a modal of 0 is a white board; a low share beside any other modal is
    exactly what the corpus does.
    """
    cells = sum(len(row) for row in grid)
    zeros = sum(1 for row in grid for value in row if value == SELECTION_INDEX)
    return round(zeros / cells, 4)


def modal_matches_bg(grid: Sequence[Sequence[int]], palette: Mapping) -> bool | None:
    """Is the board's field the index the spec DECLARED? `None` when none is declared.

    `None` is not a failure and must never be read as one: `background` is an
    optional §11 field (contract V-B) and six of our seven shipped games omit
    it, which means "unstated", not "wrong".
    """
    declared = _declared_indices(palette).get("background")
    if declared is None:
        return None
    return modal_value(grid) == declared


def component_sizes(grid: Sequence[Sequence[int]], index: int) -> list[int]:
    """Sizes of the 4-connected components painted in ONE palette index, ascending.

    `objects_cc`'s flood fill with a different predicate: that one partitions
    every non-modal cell (the officials' `objects` semantics), this one walks a
    single colour, which is what a per-role footprint is. Iterative for the same
    reason: a 64x64 board of one colour would blow a recursive fill.
    """
    height, width = len(grid), len(grid[0])
    seen = [[False] * width for _ in range(height)]
    sizes: list[int] = []
    for y in range(height):
        for x in range(width):
            if seen[y][x] or grid[y][x] != index:
                continue
            size = 0
            stack = [(y, x)]
            seen[y][x] = True
            while stack:
                cy, cx = stack.pop()
                size += 1
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < height and 0 <= nx < width and not seen[ny][nx] \
                            and grid[ny][nx] == index:
                        seen[ny][nx] = True
                        stack.append((ny, nx))
            sizes.append(size)
    return sorted(sizes)


def role_component_min(grid: Sequence[Sequence[int]],
                       palette: Mapping) -> dict[str, int | None]:
    """Per declared role: its SMALLEST painted component on this board, or `None`.

    One entry per role in `FOOTPRINT_ROLES` that the spec declares as an int;
    `None` means the role's index is not painted on this board at all, which is
    a measured non-defect — `core-ward-phase-gates` declares `you: 11` and does
    not paint it until the first click, and that game was human-ACCEPTED. A role
    the spec does not declare gets no entry.
    """
    declared = _declared_indices(palette)
    out: dict[str, int | None] = {}
    for role in FOOTPRINT_ROLES:
        if role not in declared:
            continue
        sizes = component_sizes(grid, declared[role])
        out[role] = sizes[0] if sizes else None
    return out


def smallest_painted_component(grid: Sequence[Sequence[int]]) -> dict:
    """The smallest component of ANY non-field index on this board. DATA, never a verdict.

    The role floors are the acceptance metric (contract W1-A1's hard
    prohibition, and the reason it is a prohibition: a corpus-wide confetti
    share moves the wrong way). This is the number that makes an UNDECLARED lone
    pixel visible to the human review anyway — the audit's own mosaic finding is
    a 4-pixel mirror drawn in an index that game declares no role for, so no
    per-role floor can ever see it. Ties go to the smaller index.
    """
    field = modal_value(grid)
    best: tuple[int, int] | None = None
    for index in sorted({value for row in grid for value in row} - {field}):
        sizes = component_sizes(grid, index)
        if sizes and (best is None or sizes[0] < best[0]):
            best = (sizes[0], index)
    if best is None:                     # a board painted in exactly one index
        return {"index": None, "size": None}
    return {"index": best[1], "size": best[0]}


# --- the B1 metrics (pure functions, one grid in) -----------------------------


def occupied_extent(grid: Sequence[Sequence[int]]) -> int:
    """Cells that are NOT the modal value — "how much board is used at all".

    `audit/comparative/scripts/audit_common.py:occupied_extent`, reproduced here
    (that tree is an audit script, not an importable package) against the same
    `modal_value` rule this module already uses for `objects_cc`. The two are
    deliberately paired upstream: `objects_cc` partitions exactly these cells,
    so 200 objects over 300 cells (confetti) and over 3,000 (a dense scene) are
    the same object count and different boards.

    Cross-checked at 50/50 against the `ours` rows of
    `audit/comparative/data/level-metrics.csv`, level start for level start, on
    all seven shipped sidecars.
    """
    field = modal_value(grid)
    return sum(1 for row in grid for value in row if value != field)


def objects_pcc(grid: Sequence[Sequence[int]]) -> int:
    """The OFFICIALS' object count: per-colour 4-connected components, summed.

    `audit/comparative/scripts/audit_common.py:pcc_stats` (its first value),
    reproduced here for `occupied_extent`'s reason — that tree is an audit script,
    not an importable package — and stated in its words: for every distinct
    colour on the board INCLUDING the background, label that colour's
    4-connected components and sum the counts. That is the manual-play corpus's
    `probe_games.object_stats`, and it is NOT `objects_cc` above, which counts
    components of the non-modal cells only; the two answer different questions
    and are never mixed in one number.

    The per-colour component sets partition the grid, so this is ONE pass of
    monochromatic flood fills rather than one pass per colour (the same answer,
    in O(cells)). Iterative, like `objects_cc`: a single-colour 64x64 board would
    blow a recursive fill.

    Cross-checked against the `ours` rows of
    `audit/comparative/data/level-metrics.csv` on a frozen copy of a shipped
    sidecar (`gen/tests/test_t1_density.py`), and against `pcc_stats` itself.
    """
    height, width = len(grid), len(grid[0])
    seen = [[False] * width for _ in range(height)]
    found = 0
    for y in range(height):
        for x in range(width):
            if seen[y][x]:
                continue
            colour = grid[y][x]
            found += 1
            stack = [(y, x)]
            seen[y][x] = True
            while stack:
                cy, cx = stack.pop()
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < height and 0 <= nx < width and not seen[ny][nx] \
                            and grid[ny][nx] == colour:
                        seen[ny][nx] = True
                        stack.append((ny, nx))
    return found


def chrome_region_cells(height: int, width: int, where: str,
                        depth: int) -> set[tuple[int, int]] | None:
    """The (y, x) cells one declared chrome region covers, or None when not locatable.

    `None` is `CHROME_CUSTOM` and only that: a geometry the §11 schema cannot
    express, reported `not-checked` rather than measured against a guess — the
    `hud.reserved: custom-rect` rule, one field over.

    `depth` is clamped into the grid so a declared `cell_px` larger than the
    board yields the whole board rather than an empty set, and floored at 1 so
    a region always has at least its outermost line.
    """
    if where == CHROME_CUSTOM:
        return None
    band = max(1, min(int(depth), height, width))
    regions = {
        "top": {(y, x) for y in range(band) for x in range(width)},
        "bottom": {(y, x) for y in range(height - band, height) for x in range(width)},
        "left": {(y, x) for y in range(height) for x in range(band)},
        "right": {(y, x) for y in range(height) for x in range(width - band, width)},
    }
    if where == CHROME_BORDER:
        return set().union(*regions.values())
    return regions[where]


def authored_chrome(grid: Sequence[Sequence[int]], chrome: Sequence[Mapping],
                    depth: int) -> dict:
    """The declared chrome COUNT and how many cells of it this board paints.

    The count is the verdict's half of the pairing and the coverage is data:
    `_chrome_extent_check` rejects on "declares no chrome at all", never on a
    coverage number, because no coverage threshold has been calibrated and this
    module does not invent thresholds (the three measured false-fails in the
    module docstring are what that rule is made of).

    COVERAGE IS A UNION, not a sum: two declared regions may overlap (a
    `border` and a `top` do), and counting a cell twice would report more chrome
    than the board carries. It counts cells that are NOT the board's field
    index, so an empty letterbox band — declared and never drawn — measures
    zero and says so.
    """
    height = len(grid)
    width = len(grid[0]) if height else 0
    field = modal_value(grid) if height and width else None
    band = max(1, min(int(depth), height, width)) if height and width else int(depth)
    regions: list[dict] = []
    covered: set[tuple[int, int]] = set()
    for entry in chrome:
        cells = chrome_region_cells(height, width, str(entry["where"]), band)
        row = {"kind": entry["kind"], "where": entry["where"],
               "region_cells": None, "painted_cells": None, "status": "not-checked"}
        if cells is not None:
            painted = {(y, x) for (y, x) in cells if grid[y][x] != field}
            covered |= painted
            row.update({"region_cells": len(cells), "painted_cells": len(painted),
                        "status": "measured"})
        regions.append(row)
    return {
        "declared_count": len(chrome),
        "regions": regions,
        "coverage_cells": len(covered),
        "depth_px": band,
    }


def grey_ramp_layers(grid: Sequence[Sequence[int]]) -> list[dict]:
    """The grey-ramp indices painted on this board that are NOT its field.

    Sorted by descending area, ties broken by index, so the first entry is the
    widest authored grey layer. That ordering IS the role reading R-13's
    brightness rule rests on and it is stated where it is computed: at a level
    START a veil covers and the thing under it does not, so the larger-area grey
    is the CONCEALER. `_danger_visible_check` refuses to read it whenever the
    ordering is not unambiguous.

    The field itself is excluded for `objects_cc`'s reason: the index most of
    the board is drawn in is the floor, not a layer on it.
    """
    field = modal_value(grid)
    counts = Counter(value for row in grid for value in row)
    return [
        {"index": index, "cells": counts[index], "luminance": palette_luminance(index)}
        for index in sorted(
            (value for value in counts if value in GREY_RAMP and value != field),
            key=lambda value: (-counts[value], value),
        )
    ]


def level_start_indices(records: Sequence[Mapping]) -> list[tuple[int, int]]:
    """[(level number, record index)] — which records START a level.

    The rule is `audit/comparative/scripts/audit_common.py:level_starts`,
    reproduced here (that tree is an audit script, not an importable package)
    and stated in its own words: `records[0]` starts level 1, and the FIRST
    record whose `levels_completed` increments to k starts level k+1 UNLESS its
    state is WIN, in which case it is the win screen and not a level at all.
    `previous` advances on every increment, WIN included, so a trailing `final`
    record that repeats the winning count cannot re-open a level.

    Cross-validated where it matters: summed over the 25 officials this rule
    yields exactly the 183 rows of the manual-play corpus's `features-level.csv`.
    Both W1-A1 checks read ONLY these records — a mid-level frame is a board
    caught mid-move, and a rule about how a level is DRAWN is a rule about how
    it is handed to the player.
    """
    if not records:
        raise ValueError("no records")
    starts = [(1, 0)]
    previous = records[0].get("levels_completed")
    for index, record in enumerate(records[1:], start=1):
        completed = record.get("levels_completed")
        if not isinstance(completed, int) or not isinstance(previous, int):
            continue
        if completed > previous:
            if record.get("state") != WIN_STATE:
                starts.append((completed + 1, index))
            previous = completed
    return starts


def _strip_cells(grid: Sequence[Sequence[int]], token: str) -> list[int]:
    kind, index = HUD_STRIP_GEOMETRY[token]
    if kind == "row":
        return list(grid[index]) if index < len(grid) else []
    return [row[index] for row in grid if index < len(row)]


def _board_cells(grid: Sequence[Sequence[int]], token: str) -> list[int]:
    """Every cell OUTSIDE the declared HUD strip."""
    kind, index = HUD_STRIP_GEOMETRY[token]
    if kind == "row":
        return [value for y, row in enumerate(grid) if y != index for value in row]
    return [value for row in grid for x, value in enumerate(row) if x != index]


def _comparable_cells(grid: Sequence[Sequence[int]], token: str | None) -> list[int]:
    """`_board_cells` when a strip is declared and locatable, the whole grid when not.

    A spec whose `hud.reserved` is `custom-rect` (or absent) declares a geometry
    this module cannot find, and the rule everywhere else in this file is that
    such a spec is measured against NO guessed geometry — so R-04 compares the
    whole frame and the card says which of the two it did.
    """
    if token is None:
        return [value for row in grid for value in row]
    return _board_cells(grid, token)


def win_record_index(records: Sequence[Mapping]) -> int | None:
    """Index of the FIRST record in state `WIN`, or `None` when there is none.

    FIRST, not last: the settled frame the game is in at the moment it is won is
    what a player sees, and the trailing `final` record is a re-read of the same
    board. Measured on all seven shipped sidecars, the two give an identical
    delta — so the choice costs nothing today and is the honest one if a game
    ever animates past its own win screen.

    `None` is a real outcome, not a defect: a sidecar can end in any state, and
    R-04 reports `not-checked` rather than failing a game whose capture never
    reached a win.
    """
    for index, record in enumerate(records):
        if record.get("state") == WIN_STATE:
            return index
    return None


def cell_delta(left: Sequence[int], right: Sequence[int]) -> int:
    """How many positions two equal-length cell lists disagree on."""
    return sum(1 for a, b in zip(left, right, strict=True) if a != b)


# --- the card -----------------------------------------------------------------


def _record_card(record: Mapping, *, palette: Mapping, hud: Mapping,
                 first_strip: list[int] | None,
                 field_index: str = MODE_OFF, role_footprint: str = MODE_OFF,
                 chrome_extent: str = MODE_OFF, danger_visible: str = MODE_OFF,
                 chrome: Sequence[Mapping] = (), footprint_depth: int = 1) -> dict:
    """Every frozen metric for ONE record, plus the record's own identity.

    Every mode gates its OWN fields: a check in `off` mode adds nothing here,
    which is what makes a card built with all of them off byte-identical to the
    two b003r2 cards that shipped before any of them existed. `record` and
    `fail` measure identically — the mode only decides what the verdict below is
    allowed to do about it.
    """
    grid = [list(row) for row in record["grid"]]
    token = _strip_token(hud)
    board_colors = colors(grid)
    card = {
        "label": record.get("label"),
        "seq": record.get("seq"),
        "levels_completed": record.get("levels_completed"),
        "state": record.get("state"),
        "colors": board_colors,
        "color_count": len(board_colors),
        "modal_value": modal_value(grid),
        "objects_cc": objects_cc(grid),
        "run_length_profile": run_length_profile(grid),
        "block_uniformity": block_uniformity(grid),
        "declared_absent": declared_absent(grid, palette),
    }
    if field_index != MODE_OFF:
        card.update({
            "index0_share": index0_share(grid),
            "modal_matches_bg": modal_matches_bg(grid, palette),
        })
    if role_footprint != MODE_OFF:
        card.update({
            "role_component_min": role_component_min(grid, palette),
            "smallest_painted_component": smallest_painted_component(grid),
        })
    if chrome_extent != MODE_OFF:
        card.update({
            "occupied_extent": occupied_extent(grid),
            "authored_chrome": authored_chrome(grid, chrome, footprint_depth),
        })
    if danger_visible != MODE_OFF:
        declared_danger = _declared_indices(palette).get("danger")
        card.update({
            "danger_index": declared_danger,
            "danger_painted": (
                None if declared_danger is None
                else any(declared_danger in row for row in grid)
            ),
            "grey_ramp_layers": grey_ramp_layers(grid),
        })
    if token is None:
        # No strip this module can find: the two HUD measurements and the
        # reserved-index check all rest on the same geometry, so all three say
        # so rather than reporting a number measured against a guess.
        card.update({
            "hud_strip": HUD_NOT_CHECKED,
            "hud_strip_values": None,
            "hud_strip_changes": None,
            "reserved_on_board": None,
        })
        return card
    strip = _strip_cells(grid, token)
    board = set(_board_cells(grid, token))
    card.update({
        "hud_strip": token,
        "hud_strip_values": sorted(set(strip)),
        "hud_strip_changes": first_strip is not None and strip != first_strip,
        "reserved_on_board": sorted(
            index for index in set(_reserved_indices(palette)) if index in board
        ),
    })
    return card


def _l1_color_floor(per_record: Sequence[Mapping], mode: str) -> dict:
    """The one check that can reject, measured on the reset frame."""
    reset = next((row for row in per_record if row["label"] == RESET_LABEL), None)
    fallback = reset is None
    if reset is None:
        reset = per_record[0]
    count = reset["color_count"]
    return {
        "mode": mode,
        "colors": count,
        "floor": L1_COLOR_FLOOR,
        "passed": count >= L1_COLOR_FLOOR,
        "record": reset["label"],
        "from_reset_label": not fallback,
        "note": (
            f"measured on the record labelled {RESET_LABEL!r}"
            if not fallback else
            f"no record is labelled {RESET_LABEL!r}; measured on records[0] "
            f"({reset['label']!r}) instead"
        ),
    }


def _field_index_check(per_record: Sequence[Mapping], starts: Sequence[tuple[int, int]],
                       *, mode: str, palette: Mapping) -> dict:
    """R-01 — is the field PAINTED, and is white `0` still free for selection?

    Fails on exactly one thing: a level-start board whose modal index is `0`
    when the spec has not declared `palette.background: 0`. Everything else it
    measures — the share of `0` on each board, whether the modal matches a
    declared background at all — rides as data, because neither has a
    calibrated threshold and `0` itself is NOT banned (one official, g50t, has
    a white field on all six of its levels).
    """
    declared = _declared_indices(palette).get("background")
    per_level = [
        {
            "level": level,
            "record": per_record[index]["label"],
            "modal_value": per_record[index]["modal_value"],
            "index0_share": per_record[index]["index0_share"],
            "modal_matches_bg": per_record[index]["modal_matches_bg"],
        }
        for level, index in starts
    ]
    white = [row for row in per_level if row["modal_value"] == SELECTION_INDEX]
    declared_white = declared == SELECTION_INDEX
    mismatched = [row["level"] for row in per_level if row["modal_matches_bg"] is False]
    return {
        "check": FIELD_INDEX_CHECK,
        "mode": mode,
        "declared_background": declared,
        "selection_index": SELECTION_INDEX,
        "levels_measured": len(per_level),
        "per_level": per_level,
        "white_field_levels": [row["level"] for row in white],
        "declared_mismatch_levels": mismatched,
        "passed": declared_white or not white,
        "official_context": dict(OFFICIAL_FIELD_INDEX),
        "official_source": OFFICIAL_FIELD_INDEX_SOURCE,
        "note": (
            f"white field DECLARED (`palette.background: {SELECTION_INDEX}`) — the rule is "
            f"that `{SELECTION_INDEX}` is not the field unless the spec says so, not that "
            f"`{SELECTION_INDEX}` is banned"
            if declared_white else
            "`declared_mismatch_levels` is DATA, not part of the verdict: a declared "
            "background may legitimately be off a board, the same measured false-fail that "
            "keeps `declared_absent` out of every gate"
        ),
    }


def _footprint_floor(render: Mapping) -> tuple[int, str]:
    """(floor in px, why) — one full logical cell, or the conservative fallback."""
    cell_px = render.get(RENDER_CELL_PX)
    if isinstance(cell_px, bool) or not isinstance(cell_px, int) or cell_px < 1:
        return UNDECLARED_CELL_FLOOR_PX, (
            f"no `game.render.{RENDER_CELL_PX}` declared (b001/b002 specs predate contract "
            f"V-B), so the floor is the conservative {UNDECLARED_CELL_FLOOR_PX} px — the "
            f"smallest logical cell any official could have (tile scale 2, 2x2)"
        )
    return cell_px * cell_px, (
        f"`game.render.{RENDER_CELL_PX}: {cell_px}` — one logical cell is "
        f"{cell_px}x{cell_px} = {cell_px * cell_px} px"
    )


def _role_footprint_check(per_record: Sequence[Mapping], starts: Sequence[tuple[int, int]],
                          *, mode: str, palette: Mapping, render: Mapping,
                          exempt: frozenset[tuple[str, str]], game_id: object) -> dict:
    """R-02 — is each DECLARED role drawn at least one full logical cell big?

    Per role, never per corpus. The acceptance metric is a per-role component
    floor and it must never become a board-wide 1x1 share: the officials' median
    `rl_ones_share` is about four times ours, so a corpus target on that number
    would steer generated games toward MORE lone pixels (audit findings.md §B1).

    FOUR ways a role is NOT judged, all of them measured non-defects:
    undeclared (`danger: null` is a §11 value meaning "no danger"), declared but
    unpainted on every level start (`core-ward-phase-gates` paints `you` only
    after the first click, and shipped), exempt-DECLARED (the spec's own
    `game.palette.tiny_token` names the role — contract W2-D), and exempt (an
    operator's `gate.role_footprint_exempt` entry). Every one of them is still
    MEASURED and still printed; the exemptions only stop a role setting
    `passed: false`.

    THE TWO EXEMPTIONS ARE KEPT APART IN THE REPORT, deliberately: they are
    different claims by different people at different times. `exempt-declared`
    is the SPEC's author saying, before the game existed, that this role is a
    tiny token on purpose; `exempt` is an operator saying, about a game already
    built, that they looked at the number and meant it. A card that collapsed
    them would lose exactly the distinction a review needs — whether the small
    token was designed or forgiven — so the status says which, and a role
    covered by both reports the spec's.
    """
    floor, floor_source = _footprint_floor(render)
    declared = _declared_indices(palette)
    tiny_token = _spec_tiny_token(palette)
    roles: dict[str, dict] = {}
    for role in FOOTPRINT_ROLES:
        exempted = (str(game_id), role) in exempt
        spec_declared = role in tiny_token
        if role not in declared:
            roles[role] = {
                "declared": None, "status": "not-checked", "exempt": exempted,
                "tiny_token_declared": spec_declared,
                "levels_painted": 0, "min_component": None, "worst_level": None,
                "reason": f"the spec declares no `palette.{role}` index",
            }
            continue
        painted = [
            (per_record[index]["role_component_min"].get(role), level)
            for level, index in starts
        ]
        painted = [(size, level) for size, level in painted if size is not None]
        entry = {
            "declared": declared[role],
            "exempt": exempted,
            "tiny_token_declared": spec_declared,
            "levels_painted": len(painted),
            "min_component": None,
            "worst_level": None,
            "reason": None,
        }
        if not painted:
            entry.update({
                "status": "not-checked",
                "reason": (
                    f"declared index {declared[role]} is painted on no level-start record — a "
                    f"measured non-defect (a human-ACCEPTED game paints `you` only after the "
                    f"first click)"
                ),
            })
        else:
            smallest, worst_level = min(painted)
            entry.update({
                "min_component": smallest,
                "worst_level": worst_level,
                "status": (
                    "pass" if smallest >= floor
                    else EXEMPT_DECLARED_STATUS if spec_declared
                    else "exempt" if exempted
                    else "fail"
                ),
            })
            if smallest < floor and spec_declared:
                entry["reason"] = (
                    f"below the floor at {smallest} px, exempted by the spec's own "
                    f"`game.palette.{TINY_TOKEN_FIELD}` as a declared tiny token"
                )
            elif smallest < floor and exempted:
                entry["reason"] = (
                    f"below the floor at {smallest} px, exempted by "
                    f"`gate.role_footprint_exempt` as a declared tiny token"
                )
        roles[role] = entry

    smallest_any = min(
        (
            (per_record[index]["smallest_painted_component"]["size"],
             per_record[index]["smallest_painted_component"]["index"], level)
            for level, index in starts
            if per_record[index]["smallest_painted_component"]["size"] is not None
        ),
        default=None,
    )
    return {
        "check": ROLE_FOOTPRINT_CHECK,
        "mode": mode,
        "floor_px": floor,
        "floor_source": floor_source,
        "levels_measured": len(starts),
        "roles": roles,
        # What the SPEC declared, in FOOTPRINT_ROLES order — on the card even
        # when no declared role turns out to be small, so a reader can tell a
        # spec that declared nothing from one whose declaration was not needed.
        "tiny_token_declared": [role for role in FOOTPRINT_ROLES if role in tiny_token],
        "not_checked": sorted(
            role for role, entry in roles.items() if entry["status"] == "not-checked"
        ),
        "passed": not any(entry["status"] == "fail" for entry in roles.values()),
        "smallest_painted_component": (
            None if smallest_any is None else
            {"size": smallest_any[0], "index": smallest_any[1], "level": smallest_any[2]}
        ),
        "note": (
            "`smallest_painted_component` is DATA over EVERY painted index, not a verdict: "
            "it is how an undeclared lone pixel (the audit's mosaic mirror is drawn in an "
            "index that spec declares no role for) stays visible to the review without "
            "becoming a threshold"
        ),
    }


def _win_render_check(records: Sequence[Mapping], per_record: Sequence[Mapping],
                      starts: Sequence[tuple[int, int]], *, mode: str, hud: Mapping) -> dict:
    """R-04 — does the winning board LOOK different from the last level's start?

    One comparison: the first `WIN` record against the record that started the
    final level, counting cells that differ OUTSIDE the declared `hud.reserved`
    strip. A meter that ticks is not a win being rendered, which is exactly the
    defect the comparative audit measured — one shipped game's win frame is
    byte-identical to a frame 84 actions earlier, and another's differs almost
    entirely inside its HUD.

    THREE ways this is NOT judged, and none of them can fail a game:

    * no record is in state `WIN` — the capture never reached a win, so there is
      no win frame to read (contract W1-A2 names the facing-sentinel class; on
      the shipped corpus every sidecar in fact carries one);
    * the `WIN` record IS the last level-start record — a capture whose first
      settled frame is already the win screen has no start frame to differ from;
    * the two frames are different shapes — a cell-for-cell delta is undefined,
      and a guessed alignment would be a number nobody could re-derive.

    The HUD delta rides as DATA beside the verdict. It is the number that makes
    the defect legible: `pump-phase-time-echo` moves 183 cells between those two
    frames and 60 of them are the row its spec reserves.
    """
    token = _strip_token(hud)
    level, start_index = starts[-1]
    win_index = win_record_index(records)
    check = {
        "check": WIN_RENDER_CHECK,
        "mode": mode,
        "floor_cells": WIN_RENDER_FLOOR_CELLS,
        "floor_source": WIN_RENDER_FLOOR_SOURCE,
        "hud_strip": HUD_NOT_CHECKED if token is None else token,
        "level_start_level": level,
        "level_start_record": per_record[start_index]["label"],
        "win_record": None if win_index is None else per_record[win_index]["label"],
        "win_state": WIN_STATE,
        "cells_compared": None,
        "delta_cells": None,
        "hud_delta_cells": None,
        "delta_share": None,
        "status": "not-checked",
        "reason": None,
        "passed": True,
        "official_context": dict(OFFICIAL_WIN_RENDER),
        "official_source": OFFICIAL_WIN_RENDER_SOURCE,
        "calibration": WIN_RENDER_CALIBRATION,
        "note": (
            "`hud_delta_cells` is DATA, never part of the verdict: it is how much of the "
            "difference between the two frames the declared HUD strip accounts for, and it "
            "is deliberately EXCLUDED from `delta_cells` so a win cannot be rendered by "
            "moving a meter"
        ),
    }
    if win_index is None:
        check["reason"] = (
            f"no record in the sidecar carries state {WIN_STATE!r} — this capture never "
            f"reached a win, so there is no winning board to measure"
        )
        return check
    if win_index == start_index:
        check["reason"] = (
            f"the {WIN_STATE} record IS the last level-start record "
            f"({per_record[win_index]['label']!r}) — there is no start frame for it to "
            f"differ from"
        )
        return check

    win_cells = _comparable_cells(records[win_index]["grid"], token)
    start_cells = _comparable_cells(records[start_index]["grid"], token)
    if len(win_cells) != len(start_cells):
        check["reason"] = (
            f"the {WIN_STATE} frame and the level-{level} start frame are different shapes "
            f"({len(win_cells)} vs {len(start_cells)} comparable cells) — a cell-for-cell "
            f"delta is undefined"
        )
        return check

    delta = cell_delta(win_cells, start_cells)
    hud_delta = None
    if token is not None:
        hud_delta = cell_delta(_strip_cells(records[win_index]["grid"], token),
                               _strip_cells(records[start_index]["grid"], token))
    check.update({
        "cells_compared": len(win_cells),
        "delta_cells": delta,
        "hud_delta_cells": hud_delta,
        "delta_share": round(delta / len(win_cells), 4) if win_cells else None,
        "status": "measured",
        "passed": delta >= WIN_RENDER_FLOOR_CELLS,
    })
    return check


def _declared_vs_painted_check(per_record: Sequence[Mapping], *, mode: str, palette: Mapping,
                               exempt: Mapping[tuple[str, str], str], game_id: object) -> dict:
    """R-06 — a declared role that NO captured frame ever paints.

    The per-record `declared_absent` facts have been on the card since contract
    V-C and nothing ever read them, which is the defect this check closes: the
    comparative audit found declared-vs-painted mismatches on all seven shipped
    games and every one of them was already printed on an M-1 card, "a gate that
    fires and is not acted on".

    The aggregation is the whole design, and it is deliberately narrow:

    * absent from EVERY record — a VIOLATION row. A spec that declares
      `palette.you: 11` and never paints 11 is either mis-declared or drawing
      the player in something else, and neither is readable;
    * absent from SOME records — RECORDED and never a violation. State-dependent
      roles are legitimate: `pump-flow-match-glow` paints `danger` on 4 of its
      10 records because its hazard is not always on the board;
    * absent from none — clean.

    `background` is not judged here even though `declared_absent` measures it:
    R-01's `field-index` already owns the declared-background question and owns
    it better (it compares against the board's MODAL index, not against "painted
    anywhere"), and two checks failing one game for one fact is one check too
    many.

    THE R-20 LIMIT, which this check states on every card it writes: the sidecar
    holds the reset frame, one settled frame per level transition and the final
    frame. "Absent from every record" therefore means absent from every frame
    the pipeline CAPTURED — `conduit-watch` paints `palette.you` in code and in
    no settled record, because every record is a fresh or a finished board.
    Until the R-20 capture upgrade this check cannot tell that apart from a role
    no code path paints, and `gate.declared_vs_painted_exempt` is where a human
    carries the difference in writing.
    """
    declared = _declared_indices(palette)
    measured = len(per_record)
    roles: dict[str, dict] = {}
    violations: list[dict] = []
    for role in FOOTPRINT_ROLES:
        exemption = exempt.get((str(game_id), role))
        if role not in declared:
            roles[role] = {
                "declared": None, "status": "not-checked", "exempt": exemption is not None,
                "exempt_reason": exemption, "records_measured": measured,
                "records_painted": 0,
                "reason": f"the spec declares no `palette.{role}` index",
            }
            continue
        absent = sum(1 for row in per_record if role in row["declared_absent"])
        painted = measured - absent
        entry = {
            "declared": declared[role],
            "exempt": exemption is not None,
            "exempt_reason": exemption,
            "records_measured": measured,
            "records_painted": painted,
            "status": "painted",
            "reason": None,
        }
        if painted == 0:
            entry["status"] = "exempt" if exemption is not None else "violation"
            entry["reason"] = (
                f"declared index {declared[role]} is painted on NO captured record "
                f"(0/{measured})"
                + (f"; exempted: {exemption}" if exemption is not None
                   else " — either the spec mis-declares the role or the game draws it in "
                        "some other index")
            )
            if exemption is None:
                violations.append({
                    "role": role,
                    "declared": declared[role],
                    "records_painted": 0,
                    "records_measured": measured,
                })
        elif painted < measured:
            entry["status"] = "partial"
            entry["reason"] = (
                f"painted on {painted} of {measured} record(s) — RECORDED, never a "
                f"violation: a state-dependent role is legitimately off some boards"
            )
        roles[role] = entry

    return {
        "check": DECLARED_VS_PAINTED_CHECK,
        "mode": mode,
        "records_measured": measured,
        "roles_judged": list(FOOTPRINT_ROLES),
        "roles": roles,
        "violations": violations,
        "passed": not violations,
        "capture_caveat": (
            "the frames sidecar carries the reset record, one settled record per level "
            "transition and the final record, so 'absent from every record' means absent "
            "from every frame CAPTURED — not absent from every code path. `conduit-watch` "
            "paints `palette.you` in code and in no settled frame. The R-20 capture "
            "upgrade is what would let this check tell the two apart; until then "
            "`gate.declared_vs_painted_exempt` carries the difference, in writing, per "
            "game and role"
        ),
        "note": (
            "`background` is measured by `declared_absent` and judged by R-01 "
            "(`field-index`) instead: that check asks whether the board's MODAL index is "
            "the declared one, which is the stronger question"
        ),
    }


def _chrome_depth(render: Mapping) -> tuple[int, str]:
    """(band depth in px, why) — one logical cell, or the exact outermost line.

    NOT `_footprint_floor`: that returns an AREA (cell_px squared, the size of
    one logical cell) and this is a DEPTH (how far in from the edge a band
    reaches). Sharing the number would make a 4x4 cell a 16-px-deep letterbox.

    The fallback is 1 rather than `UNDECLARED_CELL_FLOOR_PX`'s conservative 4,
    and the difference is deliberate: a footprint floor is a bar a game must
    clear, so the weakest honest value is the right one, while a band depth
    decides what gets MEASURED. A guessed 4-px band on a game that declared no
    scale would report chrome coverage from cells nobody said were chrome. Depth
    1 is the only value that is not a guess, and the card says the coverage it
    reports is therefore a lower bound.
    """
    cell_px = render.get(RENDER_CELL_PX)
    if isinstance(cell_px, bool) or not isinstance(cell_px, int) or cell_px < 1:
        return CHROME_DEPTH_FALLBACK_PX, (
            f"no `game.render.{RENDER_CELL_PX}` declared, so a declared chrome band is "
            f"measured at its exact outermost line ({CHROME_DEPTH_FALLBACK_PX} px) rather "
            f"than at a guessed width — `coverage_cells` is a LOWER BOUND on what a thicker "
            f"band actually paints"
        )
    return cell_px, (
        f"`game.render.{RENDER_CELL_PX}: {cell_px}` — a declared chrome band is one logical "
        f"cell deep, so {cell_px} px in from its edge"
    )


def _chrome_extent_check(per_record: Sequence[Mapping], starts: Sequence[tuple[int, int]],
                         *, mode: str, chrome: Sequence[Mapping], depth_note: str) -> dict:
    """R-03 — is the board FRAMED, or is it a mechanism adrift in an empty field?

    ONE verdict from TWO legs, and it rejects only when BOTH are red:

    * the game's per-game `occupied_extent` median is BELOW the officials'
      observed band, and
    * the spec declares no `game.chrome` at all.

    The pairing is contract R-03's own acceptance, not a softening of it, and
    each leg exists because the other one is gameable: extent alone rewards
    padding a board with meaningless paint, and a chrome count alone rewards
    declaring structure nobody drew. `CHROME_EXTENT_CALIBRATION["pairing"]` says
    this on every card the check writes.

    ABOVE the band is measured and RECORDED and never a violation — see that
    same calibration block: the measured defect is emptiness, no shipped game is
    above the band, and a rejection with no exhibit behind it is the false-fail
    this module refuses on principle.

    The MEDIAN is the unit because the officials' band is a band of per-game
    medians (`CHROME_EXTENT_SOURCE`). A single quiet level inside an otherwise
    dense game is not the defect R-03 measured.
    """
    per_level = [
        {
            "level": level,
            "record": per_record[index]["label"],
            "occupied_extent": per_record[index]["occupied_extent"],
            "below_band": per_record[index]["occupied_extent"] < CHROME_EXTENT_LOW,
        }
        for level, index in starts
    ]
    extents = [row["occupied_extent"] for row in per_level]
    game_median = median(extents) if extents else None
    below = game_median is not None and game_median < CHROME_EXTENT_LOW
    above = game_median is not None and game_median > CHROME_EXTENT_HIGH
    # The card's chrome facts come from the level-START records only, for
    # `_field_index_check`'s reason: a rule about how a board is FRAMED is a
    # rule about the board as it is handed to the player.
    #
    # ONE `authored_chrome` mapping carries every chrome fact — the count that
    # is half the verdict, the coverage that is evidence, the per-region rows and
    # the declaration itself. Deliberately not also a flat `authored_chrome_count`
    # beside it: two keys for one number is how the two drift, and a reader
    # sweeping the block for "the chrome metric" would find whichever came first.
    declared = per_record[starts[0][1]]["authored_chrome"] if starts else None
    if declared is None:
        declared = {"declared_count": len(chrome), "regions": [], "coverage_cells": 0,
                    "depth_px": None}
    declared = {**declared, "declared": list(chrome)}
    count = declared["declared_count"]
    return {
        "check": CHROME_EXTENT_CHECK,
        "mode": mode,
        "band": [CHROME_EXTENT_LOW, CHROME_EXTENT_HIGH],
        "band_source": CHROME_EXTENT_SOURCE,
        "levels_measured": len(per_level),
        "per_level": per_level,
        # Named for the metric rather than for the game: this IS the
        # `occupied_extent` number the band is a band of, and the band is a band
        # of per-game MEDIANS (`CHROME_EXTENT_SOURCE`).
        "occupied_extent_median": game_median,
        "below_band": below,
        "above_band": above,
        "authored_chrome": declared,
        "chrome_depth_note": depth_note,
        "passed": not (below and count == 0),
        "calibration": CHROME_EXTENT_CALIBRATION,
        "official_context": dict(OFFICIAL_CHROME),
        "official_source": OFFICIAL_CHROME_SOURCE,
        "note": (
            f"PAIRED acceptance: this game's median is {_fmt(game_median)} against the officials' "
            f"{CHROME_EXTENT_LOW}-{CHROME_EXTENT_HIGH}, and it declares {count} chrome "
            f"entr{'y' if count == 1 else 'ies'} — a rejection needs BOTH a below-band median "
            f"and a zero count"
        ),
    }


def _danger_visible_check(per_record: Sequence[Mapping], starts: Sequence[tuple[int, int]],
                          *, mode: str, palette: Mapping, knobs: Mapping,
                          terms: Sequence[str], levels: Sequence) -> dict:
    """R-13 — does the declared danger STAND on the board, and does revealing LIGHTEN it?

    TWO legs on one card, because they are one instruction to the renderer (see
    `visual_canon.DANGER_STANDS`), and each can be `not-checked` on its own.

    LEG 1, `danger_painted_levels`. When the spec declares `palette.danger`, that
    index must appear on the level-START board of every level from the one that
    introduces the hazard onward. Exhibits: one shipped game paints its declared
    `8` on two of eight level starts and suppresses it under fog on the other
    six; another never paints its `8` at all, because its hazard is a one-frame
    crush flash. A spec that declares no danger index is `not-checked` — an
    undeclared hazard is R-06's question, not this one.

    THE EXEMPTION IS THE DANGER TELL, and this is the contract's one adjudicated
    call, so it is stated in full. R-13's risk line asks that a declared
    camouflage not be punished (it would collide with R-09). `knobs.deceptions`
    is a list of FREE PROSE, and on the shipped corpus three of the seven games
    carry an entry containing the word camouflage — about a dual-role junction,
    about look-alike pads, about depot markings — none of them about the hazard.
    Keying the exemption on that prose would exempt both R-13 exhibits and
    every future game that ever writes the word, which is exactly the "silently
    exempt everything" failure `role_footprint_exempt` refuses. So the exemption
    is `knobs.danger_tell`, the §3 catalog entry that states how THIS game's
    danger tells:

    * `camouflage` — the §3 lever R-13's risk line names. Declared, so exempt.
    * `absence` — §3's other hiding tell: the danger IS the missing mark, so a
      declared index that is off the board is the declared tell.
    * `none` — the spec declares no danger tell, so there is nothing to hold it
      to and the leg is `not-checked`.

    `knobs.deceptions` is still READ and recorded (`deception_camouflage`), so a
    reviewer sees the prose beside the verdict and can overrule it — the fact is
    on the card either way, which is the `palette-overload-declared` rule.

    LEG 2, `reveal_brightness_ok`. Measured ONLY when the spec declares a
    conceal term (`CONCEAL_TERMS`) and the grey ramp reads unambiguously: every
    level-start board must paint EXACTLY TWO non-field grey indices, the SAME
    two on every level, with a STRICT area difference in the same direction
    every time. Then the wider layer is the concealer and the narrower is what
    it hides, and the rule is that the revealed index is the LIGHTER one.

    Anything less is `not-checked` and says which condition failed. That
    strictness is the honest part: nothing in today's §11 declares which index
    is fog and which is revealed, so the area ordering is the only role signal
    there is, and it is worth reading only when it never wavers. Measured on the
    corpus it separates cleanly — one shipped game shows the same pair 2/3 with
    the same ordering on all eight levels (and gets the brightness backwards),
    while another declares `info.fog` too but swings between one, two and three
    grey layers whose identities change level to level, and is honestly reported
    as unreadable rather than guessed at.
    """
    declared = _declared_indices(palette).get("danger")
    tell = knobs.get("danger_tell")
    tell = tell if isinstance(tell, str) else None
    deceptions = knobs.get("deceptions")
    camouflage_prose = [
        entry for entry in (deceptions if isinstance(deceptions, list) else [])
        if isinstance(entry, str) and "camouflage" in entry.lower()
    ]
    exempt_tell = tell in ("camouflage", "absence")
    hazard_terms = [term for term in terms if term.startswith(HAZARD_PREFIXES)]
    hazard_from = _hazard_start_level(levels)

    per_level: list[dict] = []
    violations: list[dict] = []
    for level, index in starts:
        row = {
            "level": level,
            "record": per_record[index]["label"],
            "painted": per_record[index]["danger_painted"],
            "in_scope": hazard_from is None or level >= hazard_from,
            "status": "not-checked",
        }
        if declared is None:
            row["reason"] = "the spec declares no `palette.danger` index"
        elif tell == "none":
            row["reason"] = "`knobs.danger_tell: none` — the spec declares no danger tell"
        elif not row["in_scope"]:
            row["reason"] = (
                f"the curriculum introduces its first hazard term at level {hazard_from}"
            )
        elif row["painted"]:
            row["status"] = "painted"
        elif exempt_tell:
            row["status"] = DANGER_EXEMPT_DECLARED
            row["reason"] = f"`knobs.danger_tell: {tell}` declares a hiding tell"
        else:
            row["status"] = "violation"
            row["reason"] = f"declared danger index {declared} is on no level-{level} start board"
            violations.append({"level": level, "declared": declared})
        per_level.append(row)

    brightness = _reveal_brightness(per_record, starts, terms=terms)
    return {
        "check": DANGER_VISIBLE_CHECK,
        "mode": mode,
        "declared_danger": declared,
        "danger_tell": tell,
        "hazard_terms": hazard_terms,
        "hazard_from_level": hazard_from,
        "exempt_by_tell": exempt_tell,
        "deception_camouflage": camouflage_prose,
        "levels_measured": len(per_level),
        "danger_painted_levels": per_level,
        "violations": violations,
        "reveal_brightness_ok": brightness["ok"],
        "reveal_brightness": brightness,
        "conceal_terms": list(CONCEAL_TERMS),
        "official_hazard_rows": OFFICIAL_HAZARD_ROWS,
        "passed": not violations and brightness["ok"] is not False,
        "note": (
            f"all {OFFICIAL_HAZARD_ROWS} hazard rows across the {OFFICIAL_GAMES} signed "
            f"officials are PLACED OBJECTS that stand on the board before they bite. The "
            f"exemption is `knobs.danger_tell` and NOT `knobs.deceptions`: the deceptions "
            f"list is free prose and three of our seven games mention camouflage about "
            f"something that is not the hazard, so keying on it would exempt everything. The "
            f"prose is recorded in `deception_camouflage` for the reviewer"
        ),
    }


def _reveal_brightness(per_record: Sequence[Mapping], starts: Sequence[tuple[int, int]],
                       *, terms: Sequence[str]) -> dict:
    """R-13 leg 2 — is the revealed state LIGHTER than the state that hid it?

    `ok` is tri-state and the third value is the honest one: `True` clean,
    `False` inverted, `None` not-checked with `reason` saying which condition
    was not met. Never guessed.
    """
    declared = [term for term in terms if term in CONCEAL_TERMS]
    result: dict = {
        "ok": None,
        "conceal_terms_declared": declared,
        "per_level": [],
        "concealer": None,
        "revealed": None,
        "reason": None,
    }
    if not declared:
        result["reason"] = (
            f"the spec declares no conceal term ({list(CONCEAL_TERMS)}), so it claims no "
            f"reveal/conceal pair to order"
        )
        return result
    per_level = [
        {"level": level, "layers": per_record[index]["grey_ramp_layers"]}
        for level, index in starts
    ]
    result["per_level"] = per_level
    if not per_level:
        result["reason"] = "no level-start record to measure"
        return result
    if any(len(row["layers"]) != 2 for row in per_level):
        counts = sorted({len(row["layers"]) for row in per_level})
        result["reason"] = (
            f"a reveal/conceal pair is TWO non-field grey indices on every level-start board; "
            f"this game paints {counts} of them across its levels, so which index conceals "
            f"and which is revealed cannot be read without guessing"
        )
        return result
    pairs = {tuple(layer["index"] for layer in row["layers"]) for row in per_level}
    if len(pairs) != 1:
        result["reason"] = (
            f"the two non-field grey indices are not the SAME pair on every level "
            f"({sorted(pairs)}) — a pair whose members change roles between levels is not a "
            f"reveal/conceal pair this check can read"
        )
        return result
    if any(row["layers"][0]["cells"] == row["layers"][1]["cells"] for row in per_level):
        result["reason"] = (
            "the two grey layers cover the SAME number of cells on some level, so neither is "
            "the wider (concealing) one"
        )
        return result
    concealer, revealed = next(iter(per_level))["layers"]
    result.update({
        "concealer": dict(concealer),
        "revealed": dict(revealed),
        "ok": revealed["luminance"] > concealer["luminance"],
        "reason": (
            f"index {concealer['index']} covers more of every level-start board than index "
            f"{revealed['index']}, so it is the concealer; revealing must make the board "
            f"LIGHTER, i.e. luminance {revealed['luminance']} must exceed "
            f"{concealer['luminance']}"
        ),
    })
    return result


def density_verdict(values: Sequence[float], tier: str | None) -> dict:
    """The band's verdict over ONE game's per-level `objects_pcc` values — pure.

    Split out of `_density_check` so the calibration can run the check's own
    decision over numbers it did not measure from a sidecar: the officials'
    per-level values come out of the comparative audit's pinned table, and
    `gen/tests/test_t1_density.py` feeds all 25 through this function (the
    R-01/R-04 calibration pattern). `_density_check` measures, this decides.

    `status` is one of `below-floor` (in scope and under the floor — the one
    status `passed: false` goes with), `under-median` (in scope, inside the band,
    under the officials' median: recorded, never rejected), `in-band`,
    `not-scoped` (the tier is outside `DENSITY_TIERS`, or unreadable) and
    `not-checked` (no values at all — unreachable from a sidecar, which always
    starts level 1).
    """
    numbers = list(values)
    game_median = median(numbers) if numbers else None
    applies = tier in DENSITY_TIERS
    below_floor = game_median is not None and game_median < DENSITY_FLOOR_OBJECTS
    below_median = game_median is not None and game_median < DENSITY_MEDIAN_OBJECTS
    if game_median is None:
        status = "not-checked"
    elif not applies:
        status = "not-scoped"
    elif below_floor:
        status = "below-floor"
    elif below_median:
        status = "under-median"
    else:
        status = "in-band"
    return {
        "objects_pcc_median": game_median,
        "ratio_to_official_median": (
            None if game_median is None else round(game_median / DENSITY_MEDIAN_OBJECTS, 2)
        ),
        "applies": applies,
        "below_floor": below_floor,
        "below_official_median": below_median,
        "status": status,
        "passed": not (applies and below_floor),
    }


def _density_check(records: Sequence[Mapping], starts: Sequence[tuple[int, int]],
                   *, mode: str, tier: str | None, tier_source: str | None) -> dict:
    """T-1 — does a t1 board carry an official level's worth of objects?

    The game's per-level MEDIAN `objects_pcc`, over the level-START records
    (`_field_index_check`'s reason: a rule about how a board is drawn is a rule
    about the board as it is handed to the player), against the officials'
    25th-percentile floor. Below the floor is the finding; at or above it is
    inside the band — and between the floor and the officials' median it is
    RECORDED as `under-median`, which no mode can reject on.

    SCOPED, explicitly (contract T-1 B4): the band applies only when the slot's
    tier is in `DENSITY_TIERS`. For any other tier, or a tier `spec_tier` cannot
    read, the number is still measured and printed beside the band and the check
    reports `not-scoped` with `passed: true` — so `fail` stops a t1 game under
    the floor and nothing else.

    No ceiling, on `chrome-extent`'s rule: the measured defect is emptiness, and
    a high-side rejection would have no exhibit behind it.

    Reads `records` (the grids) rather than `per_record`: the per-record cards
    stay exactly as they were, so the always-recorded block below is the ONE
    thing a `record`-mode card gains over an `off` one (the R-06 precedent).
    """
    per_level = []
    for level, index in starts:
        value = objects_pcc(records[index]["grid"])
        per_level.append({
            "level": level,
            "record": records[index].get("label"),
            "objects_pcc": value,
            "below_floor": value < DENSITY_FLOOR_OBJECTS,
        })
    verdict_row = density_verdict([row["objects_pcc"] for row in per_level], tier)
    game_median = verdict_row["objects_pcc_median"]
    applies, below_floor = verdict_row["applies"], verdict_row["below_floor"]
    scope = "/".join(DENSITY_TIERS)
    tier_words = (f"tier `{tier}` (read from {tier_source})" if tier is not None
                  else "no readable tier (no `game.tier` in spec.yaml, no `tier` in idea.json)")
    if not applies:
        verdict = (f"{tier_words}: the band is scoped to {scope}, so this is RECORDED and never "
                   f"a verdict")
    elif below_floor:
        verdict = (f"{tier_words}: BELOW the officials' floor — t1 simplicity is mechanical "
                   f"(fewer rules), not visual sparseness; draw denser boards from structure "
                   f"and repetition of the declared pieces, never from undeclared mechanics")
    else:
        verdict = f"{tier_words}: at or above the officials' floor"
    # The verdict keys (`objects_pcc_median`, `ratio_to_official_median`,
    # `applies`, `below_floor`, `below_official_median`, `status`, `passed`) come
    # from `density_verdict` verbatim — one decision, never re-derived here.
    return {
        **verdict_row,
        "check": DENSITY_CHECK,
        "mode": mode,
        "metric": "objects_pcc",
        "band": {"floor": DENSITY_FLOOR_OBJECTS, "official_median": DENSITY_MEDIAN_OBJECTS,
                 "ceiling": None},
        "band_source": DENSITY_FLOOR_SOURCE,
        "tier": tier,
        "tier_source": tier_source,
        "tier_scope": list(DENSITY_TIERS),
        "levels_measured": len(per_level),
        "per_level": per_level,
        "calibration": DENSITY_CALIBRATION,
        "official_source": OFFICIAL_DENSITY_SOURCE,
        "note": (
            f"per-level median `objects_pcc` {_fmt(game_median)} over {len(per_level)} "
            f"level-start record(s) against the officials' floor {DENSITY_FLOOR_OBJECTS} "
            f"(p25) and median {DENSITY_MEDIAN_OBJECTS} — {verdict}"
        ),
    }


def declared_violation_lines(check: Mapping | None) -> list[str]:
    """R-06's violation rows as human lines — ONE renderer, every consumer.

    The card's markdown and the orchestrator's REVIEW REQUIRED block both print
    these rows, and a reviewer who reads one and then the other must not have to
    reconcile two spellings of the same finding.
    """
    if not isinstance(check, Mapping):
        return []
    rows = check.get("violations")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    return [
        f"`palette.{row['role']}` (index {row['declared']}) painted on "
        f"{row['records_painted']}/{row['records_measured']} record(s)"
        for row in rows
        if isinstance(row, Mapping)
    ]


def _official_bands() -> dict:
    """`visual_canon.OFFICIAL_VISUAL_CONSTANTS`, json-shaped. Quoted, never re-measured."""
    return {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in OFFICIAL_VISUAL_CONSTANTS.items()
    }


def build_visual_card(spec_dir: Path | str, cfg: Mapping) -> dict:
    """Measure one slot's already-captured frames and write the three card files.

    Returns the report json with a `paths` mapping added (the three files,
    relative to `spec_dir`). The written json carries the report only: a path
    is where a file IS, not something measured about the game, and keeping it
    out is what makes two builds byte-identical wherever the corpus lives.
    """
    spec_dir = Path(spec_dir)
    visual_card_mode(cfg)                    # validate the whole block, loudly
    floor_mode = l1_floor_mode(cfg)
    field_mode = field_index_mode(cfg)
    footprint_mode = role_footprint_mode(cfg)
    exempt = role_footprint_exempt(cfg)
    win_mode = win_render_mode(cfg)
    painted_mode = declared_vs_painted_mode(cfg)
    painted_exempt = declared_vs_painted_exempt(cfg)
    chrome_mode = chrome_extent_mode(cfg)
    danger_mode = danger_visible_mode(cfg)
    density = density_mode(cfg)

    frames = _load_frames(spec_dir)
    palette, hud, render = _spec_visuals(spec_dir)
    records = list(frames["records"])

    # The §11 declarations the two B1 checks read. Parsed unconditionally (it is
    # one small yaml) but handed only to the modes that are armed, so the `off`
    # byte-identity contract is decided by `_record_card`'s own gates and not by
    # what this function happened to read.
    declarations = _spec_declarations(spec_dir)
    chrome = declarations[CHROME_FIELD]
    chrome_depth, chrome_depth_note = _chrome_depth(render)

    token = _strip_token(hud)
    first_strip = None if token is None else _strip_cells(records[0]["grid"], token)
    per_record = [
        _record_card(record, palette=palette, hud=hud, first_strip=first_strip,
                     field_index=field_mode, role_footprint=footprint_mode,
                     chrome_extent=chrome_mode, danger_visible=danger_mode,
                     chrome=chrome, footprint_depth=chrome_depth)
        for record in records
    ]
    report = {
        "game_id": frames.get("game_id"),
        "source": frames.get("source"),
        "per_record": per_record,
        "l1_color_floor": _l1_color_floor(per_record, floor_mode),
        "official_bands": _official_bands(),
    }
    # Every W1 check adds its key to the report ONLY when armed: a card built
    # with all four knobs `off` carries exactly the keys it carried before those
    # contracts, which is the determinism pin the two shipped b003r2 cards hold
    # us to. The W1-A1 pair reads the level-START records; W1-A2's `win-render`
    # reads the last of them against the WIN record, and `declared-vs-painted`
    # reads every record (a role is absent from a capture, not from a level).
    if any(mode != MODE_OFF for mode in (field_mode, footprint_mode, win_mode,
                                         chrome_mode, danger_mode, density)):
        starts = level_start_indices(records)
        if density != MODE_OFF:
            # The tier is read only when the check is armed — an `off` card
            # touches nothing it did not touch before T-1 existed.
            tier, tier_source = spec_tier(spec_dir)
            report[DENSITY_CHECK] = _density_check(
                records, starts, mode=density, tier=tier, tier_source=tier_source)
        if chrome_mode != MODE_OFF:
            report[CHROME_EXTENT_CHECK] = _chrome_extent_check(
                per_record, starts, mode=chrome_mode, chrome=chrome,
                depth_note=chrome_depth_note)
        if danger_mode != MODE_OFF:
            report[DANGER_VISIBLE_CHECK] = _danger_visible_check(
                per_record, starts, mode=danger_mode, palette=palette,
                knobs=declarations["knobs"], terms=declarations["terms"],
                levels=declarations["levels"])
        if field_mode != MODE_OFF:
            report[FIELD_INDEX_CHECK] = _field_index_check(
                per_record, starts, mode=field_mode, palette=palette)
        if footprint_mode != MODE_OFF:
            report[ROLE_FOOTPRINT_CHECK] = _role_footprint_check(
                per_record, starts, mode=footprint_mode, palette=palette, render=render,
                exempt=exempt, game_id=frames.get("game_id"))
        if win_mode != MODE_OFF:
            report[WIN_RENDER_CHECK] = _win_render_check(
                records, per_record, starts, mode=win_mode, hud=hud)
    if painted_mode != MODE_OFF:
        report[DECLARED_VS_PAINTED_CHECK] = _declared_vs_painted_check(
            per_record, mode=painted_mode, palette=palette, exempt=painted_exempt,
            game_id=frames.get("game_id"))

    paths = card_paths(spec_dir)
    paths["json"].parent.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    paths["md"].write_text(render_markdown(report), encoding="utf-8")
    write_contact_sheet([record["grid"] for record in records], paths["contact_sheet"])
    return {**report,
            "paths": {name: str(path.relative_to(spec_dir)) for name, path in paths.items()}}


# --- the human summary --------------------------------------------------------


_MD_PREAMBLE = """\
# Visual report card — {game_id}

Frames source: `{source}` · {count} record(s) measured from `{frames}` (no engine
run: this card reads the sidecar S2b already wrote).

**These are RECORDS for the human review, not gates.** Every number below is a
measurement handed to the `played` review, which architecture §3 makes the judge
of legibility (the `s3_gate._check_loc` precedent: where no rejection threshold is
calibrated, the number goes on the record and the judgement goes to the review).
{reject_block}
"""

# The one-check sentence, kept verbatim: a card with both W1-A1 checks `off`
# renders the file it rendered before they existed, byte for byte.
_MD_REJECT_ONE = """\
Exactly one line in this file can ever reject a game — the level-1 color floor —
and it is in `{floor_mode}` mode for this run."""

_MD_REJECT_MANY = """\
{count} checks in this file can reject a game, each under its own knob and each
born in `record`:

- the level-1 color floor — `{floor_mode}`
{others}

A check in `record` measures and reports; only `fail` rejects."""

_MD_BANDS = """\
Official bands below are quoted from `gen/visual_canon.OFFICIAL_VISUAL_CONSTANTS`,
measured over the {games} signed officials:

- **color_count** — level-1 board colors, min {l1_min} / median {l1_median} / max {l1_max};
  per-game median across all levels runs {cm_min} to {cm_max} (median {cm_median}).
- **objects_cc** — per-game `objects_median`, min {obj_min} / median {obj_median} / max {obj_max}.
  Density varies wildly in the corpus; readability never does.
- **run mode** — the official tile-scale menu is {menu}, and a board drawn at
  scale s tends to a run-length mode of s. NOT a target and deliberately not a
  gate: uniform background rows pull the mode to the full board width, and a
  human-ACCEPTED b002 game swings between mode 64 and mode 1 across its own
  levels. Read it beside the block-uniformity curve below, which is the steadier
  scale estimate; read `ones_share` for the 1x1-confetti tell.
"""


def _fmt(value: object) -> str:
    """A run-length median prints as `3`, not `3.0` — `statistics.median` returns both."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _verdict_word(check: Mapping) -> str:
    """`PASS`/`FAIL` plus what this run is allowed to do about it."""
    word = "PASS" if check["passed"] else "FAIL"
    tail = ("." if check["mode"] == "fail"
            else " — recording only; this run cannot reject on it.")
    return f"**{word}** in `{check['mode']}` mode{tail}"


def _md_field_index(report: Mapping) -> list[str]:
    """R-01's section — absent from the file entirely when the check is off."""
    check = report.get(FIELD_INDEX_CHECK)
    if check is None:
        return []
    official = check["official_context"]
    declared = check["declared_background"]
    parts = [
        (f"## Painted field + the white-{check['selection_index']} reservation "
         f"(`{check['check']}`)\n"),
        (
            f"- declared `palette.background`: "
            f"{'unstated (the canon default, black 5, applies)' if declared is None else declared}"
            f"; {check['levels_measured']} level-start record(s) measured.\n"
            f"- level(s) whose FIELD is white {check['selection_index']}: "
            f"{', '.join(str(level) for level in check['white_field_levels']) or '—'}\n"
            f"- {_verdict_word(check)}\n"
            f"- {check['note']}.\n"
        ),
        (
            f"Officials, for scale: the board's modal index is "
            f"{check['selection_index']} on {official['modal_zero_levels']} of "
            f"{official['levels']} level-start boards "
            f"({official['modal_zero_share']:.1%}), all of them one game "
            f"({', '.join(official['modal_zero_games'])}) — while index "
            f"{check['selection_index']} is painted SOMEWHERE on "
            f"{official['paints_zero_levels']} of {official['levels']} "
            f"({official['paints_zero_share']:.1%}). White is everywhere in the corpus as a "
            f"MARK and almost nowhere as the floor. Source: {check['official_source']}.\n"
        ),
        "| level | record | modal | index0_share | modal == declared bg |",
        "| ---: | --- | ---: | ---: | --- |",
    ]
    for row in check["per_level"]:
        matches = row["modal_matches_bg"]
        parts.append(
            f"| {row['level']} | `{row['record']}` | {row['modal_value']} "
            f"| {row['index0_share']:.4f} "
            f"| {'—' if matches is None else ('yes' if matches else 'no')} |"
        )
    parts.append("")
    return parts


def _footprint_exempt_marks(entry: Mapping) -> str:
    """The `(exempt)` / `(tiny_token)` suffix on a role's status cell.

    BOTH are printed when both are set: a role an operator exempted AND the
    spec declared is two people agreeing, and a card that showed only one of
    them would hide the other's signature. The old single-word `(exempt)`
    spelling is kept for the operator's list so a card built before contract
    W2-D still reads the same for the same input.
    """
    marks = []
    if entry.get("exempt"):
        marks.append("exempt")
    if entry.get("tiny_token_declared"):
        marks.append(TINY_TOKEN_FIELD)
    return f" ({', '.join(marks)})" if marks else ""


def _md_role_footprint(report: Mapping) -> list[str]:
    """R-02's section — absent from the file entirely when the check is off."""
    check = report.get(ROLE_FOOTPRINT_CHECK)
    if check is None:
        return []
    parts = [
        f"## Role footprints — one full logical cell (`{check['check']}`)\n",
        (
            f"- floor: **{check['floor_px']} px** per connected component "
            f"({check['floor_source']}).\n"
            f"- measured on {check['levels_measured']} level-start record(s), per DECLARED "
            f"role. The acceptance metric is this per-role floor and never a board-wide 1x1 "
            f"share — the officials' median `ones_share` is about 4x ours, so a corpus target "
            f"on that number would steer a game toward MORE lone pixels.\n"
            f"- {_verdict_word(check)}\n"
        ),
        "| role | declared index | level starts painted | smallest component | status |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for role in FOOTPRINT_ROLES:
        entry = check["roles"][role]
        smallest = entry["min_component"]
        painted = ("—" if entry["declared"] is None
                   else f"{entry['levels_painted']}/{check['levels_measured']}")
        parts.append(
            f"| `{role}` | {'—' if entry['declared'] is None else entry['declared']} "
            f"| {painted} "
            f"| {'—' if smallest is None else f'{smallest} px'} "
            f"| {entry['status']}{_footprint_exempt_marks(entry)} |"
        )
    parts.append("")
    for role in FOOTPRINT_ROLES:
        reason = check["roles"][role]["reason"]
        if reason:
            parts.append(f"- `{role}`: {reason}.")
    smallest_any = check["smallest_painted_component"]
    if smallest_any is not None:
        parts.append(
            f"- smallest component of ANY painted index over the level starts: "
            f"**{smallest_any['size']} px** (index {smallest_any['index']}, level "
            f"{smallest_any['level']}). {check['note']}."
        )
    parts.append("")
    return parts


def _md_win_render(report: Mapping) -> list[str]:
    """R-04's section — absent from the file entirely when the check is off."""
    check = report.get(WIN_RENDER_CHECK)
    if check is None:
        return []
    calibration = check["calibration"]
    official = check["official_context"]
    parts = [
        f"## The win is rendered (`{check['check']}`)\n",
        (
            f"- floor: **{check['floor_cells']} board cell(s)** of difference between the "
            f"`{check['win_state']}` frame and the final level's start frame, measured "
            f"OUTSIDE the declared HUD strip (`{check['hud_strip']}`).\n"
            f"- compared: `{check['win_record']}` against `{check['level_start_record']}` "
            f"(the level-{check['level_start_level']} start).\n"
        ),
    ]
    if check["status"] != "measured":
        parts.append(
            f"- **NOT CHECKED** — {check['reason']}. A game whose capture carries no "
            f"winning board is never failed on one.\n"
        )
    else:
        parts.append(
            f"- measured: **{check['delta_cells']}** of {check['cells_compared']} board "
            f"cell(s) differ ({check['delta_share']:.1%})"
            + (f"; a further {check['hud_delta_cells']} cell(s) differ INSIDE the declared "
               f"HUD strip and are excluded from the count."
               if check["hud_delta_cells"] is not None else
               " (no locatable HUD strip: the whole frame was compared).")
            + f"\n- {_verdict_word(check)}\n"
        )
    parts.append(
        f"Officials, for scale: the win frame moves a median of {official['median']} of "
        f"{official['cells']} cells ({official['median_game']}), min {official['min']} "
        f"({official['min_game']}), max {official['max']} ({official['max_game']}). "
        f"Source: {official['games']} signed games, {check['official_source']}.\n"
    )
    parts.append(
        f"Calibration — {calibration['separation']}. Measured on "
        f"{calibration['measured_on']}:\n"
    )
    parts.append("| game | board cells changed at the win | under this floor |")
    parts.append("| --- | ---: | --- |")
    for row in calibration["fails"]:
        parts.append(f"| `{row['game']}` | {row['delta']} | FAIL |")
    for row in calibration["passes"]:
        parts.append(f"| `{row['game']}` | {row['delta']} | pass |")
    parts.append("")
    parts.append(f"- {check['floor_source']}.")
    parts.append(f"- COST: {calibration['cost_in_officials']}.")
    parts.append(f"- {check['note']}.")
    parts.append("")
    return parts


def _md_declared_vs_painted(report: Mapping) -> list[str]:
    """R-06's section — absent from the file entirely when the check is off."""
    check = report.get(DECLARED_VS_PAINTED_CHECK)
    if check is None:
        return []
    parts = [
        f"## Declared roles nothing ever paints (`{check['check']}`)\n",
        (
            f"- {check['records_measured']} captured record(s); roles judged: "
            f"{', '.join(f'`{role}`' for role in check['roles_judged'])}.\n"
            f"- a role absent from EVERY record is a violation; absent from SOME is "
            f"recorded and never a violation.\n"
            f"- {_verdict_word(check)}\n"
        ),
        "| role | declared index | records painted | status |",
        "| --- | ---: | ---: | --- |",
    ]
    for role in check["roles_judged"]:
        entry = check["roles"][role]
        painted = ("—" if entry["declared"] is None
                   else f"{entry['records_painted']}/{entry['records_measured']}")
        parts.append(
            f"| `{role}` | {'—' if entry['declared'] is None else entry['declared']} "
            f"| {painted} | {entry['status']} |"
        )
    parts.append("")
    for role in check["roles_judged"]:
        reason = check["roles"][role]["reason"]
        if reason:
            parts.append(f"- `{role}`: {reason}.")
    rows = declared_violation_lines(check)
    parts.append("")
    parts.append(
        "Violation row(s): " + ("; ".join(rows) if rows else "—") + "\n"
    )
    parts.append(f"KNOWN CAPTURE LIMIT — {check['capture_caveat']}.\n")
    parts.append(f"{check['note']}.\n")
    return parts


def _md_chrome_extent(report: Mapping) -> list[str]:
    """R-03's section — absent from the file entirely when the check is off."""
    check = report.get(CHROME_EXTENT_CHECK)
    if check is None:
        return []
    low, high = check["band"]
    calibration = check["calibration"]
    chrome = check["authored_chrome"]
    where = "below" if check["below_band"] else ("above" if check["above_band"] else "inside")
    parts = [
        f"## Is the board FRAMED (`{check['check']}`)\n",
        (
            f"- band: **{low}-{high}** `occupied_extent` (cells that are not the board's modal "
            f"index), the officials' full per-game-median range.\n"
            f"- this game: **{_fmt(check['occupied_extent_median'])}** median over "
            f"{check['levels_measured']} level-start record(s) — {where} the band.\n"
            f"- declared `game.chrome` entries: **{chrome['declared_count']}**"
            + (
                " — " + ", ".join(
                    f"`{entry['kind']}`@`{entry['where']}`" for entry in chrome["declared"]
                )
                if chrome["declared"] else " (none)"
            )
            + f".\n- {_verdict_word(check)}\n"
            f"- {check['note']}.\n"
        ),
        "| level | record | occupied_extent | below band |",
        "| --- | --- | ---: | --- |",
    ]
    for row in check["per_level"]:
        parts.append(
            f"| {row['level']} | `{row['record']}` | {row['occupied_extent']} "
            f"| {'YES' if row['below_band'] else '—'} |"
        )
    parts.append("")
    if chrome["regions"]:
        parts.append(
            f"Declared chrome, measured on the first level-start board at a band depth of "
            f"{chrome['depth_px']} px ({chrome['coverage_cells']} cell(s) of authored chrome "
            f"painted in total):\n"
        )
        parts.append("| kind | where | region cells | painted | status |")
        parts.append("| --- | --- | ---: | ---: | --- |")
        for region in chrome["regions"]:
            parts.append(
                f"| `{region['kind']}` | `{region['where']}` "
                f"| {_fmt(region['region_cells']) if region['region_cells'] is not None else '—'} "
                f"| {_fmt(region['painted_cells']) if region['painted_cells'] is not None else '—'}"
                f" | {region['status']} |"
            )
        parts.append("")
        parts.append(f"- {check['chrome_depth_note']}.")
    parts.append(
        f"PAIRING — {calibration['pairing']}.\n"
    )
    parts.append(f"ABOVE THE BAND — {calibration['above_band_note']}.\n")
    below = ", ".join(
        "`{}` {}".format(row["game"], _fmt(row["median"]))
        for row in calibration["below_band"]
    )
    parts.append(
        f"Calibration, measured on {calibration['measured_on']}: our per-game median is "
        f"{calibration['ours_median']}, **{calibration['ours_ratio']}x** the officials' "
        f"{check['official_context']['band_median']}, and "
        f"{len(calibration['below_band'])} of seven sit below the band ({below}). "
        f"The officials carry {calibration['official_decor_rows']} decor rows; we carry "
        f"{calibration['authored_decor_objects']} authored decor objects in seven games.\n"
    )
    parts.append(f"- {check['band_source']}.")
    parts.append(f"- Source: {check['official_source']}.")
    parts.append("")
    return parts


def _md_danger_visible(report: Mapping) -> list[str]:
    """R-13's section — absent from the file entirely when the check is off."""
    check = report.get(DANGER_VISIBLE_CHECK)
    if check is None:
        return []
    declared = check["declared_danger"]
    brightness = check["reveal_brightness"]
    parts = [
        f"## Danger stands on the board (`{check['check']}`)\n",
        (
            f"- declared `palette.danger`: "
            f"{'—' if declared is None else declared}; `knobs.danger_tell`: "
            f"`{check['danger_tell']}`; hazard term(s): "
            f"{', '.join(f'`{term}`' for term in check['hazard_terms']) or '—'}.\n"
            f"- {check['levels_measured']} level-start record(s) measured"
            + (
                f", from level {check['hazard_from_level']} onward (the level that introduces "
                f"the first hazard term)"
                if check["hazard_from_level"] not in (None, 1) else ""
            )
            + f".\n- {_verdict_word(check)}\n"
        ),
        "| level | record | danger index painted | status |",
        "| --- | --- | --- | --- |",
    ]
    for row in check["danger_painted_levels"]:
        painted = "—" if row["painted"] is None else ("yes" if row["painted"] else "**no**")
        parts.append(
            f"| {row['level']} | `{row['record']}` | {painted} | {row['status']} |"
        )
    parts.append("")
    for row in check["danger_painted_levels"]:
        if row.get("reason") and row["status"] in ("violation", DANGER_EXEMPT_DECLARED):
            parts.append(f"- level {row['level']}: {row['reason']}.")
    parts.append("")
    parts.append("### Reveal brightness — revealing must make the board LIGHTER\n")
    if brightness["ok"] is None:
        parts.append(f"- **NOT CHECKED** — {brightness['reason']}.\n")
    else:
        concealer, revealed = brightness["concealer"], brightness["revealed"]
        parts.append(
            f"- concealer: index **{concealer['index']}** (luminance "
            f"{concealer['luminance']}, {concealer['cells']} cells on level 1); revealed: "
            f"index **{revealed['index']}** (luminance {revealed['luminance']}, "
            f"{revealed['cells']} cells).\n"
            f"- **{'PASS' if brightness['ok'] else 'INVERTED'}** — {brightness['reason']}.\n"
        )
    if check["deception_camouflage"]:
        parts.append(
            f"`knobs.deceptions` carries {len(check['deception_camouflage'])} entr"
            f"{'y' if len(check['deception_camouflage']) == 1 else 'ies'} mentioning "
            f"camouflage. RECORDED, never an exemption — the exemption is "
            f"`knobs.danger_tell` (see below), and the prose is here so a reviewer can "
            f"overrule that:\n"
        )
        for entry in check["deception_camouflage"]:
            parts.append(f"  - {' '.join(str(entry).split())[:300]}")
        parts.append("")
    parts.append(f"{check['note']}.\n")
    return parts


def _md_density(report: Mapping) -> list[str]:
    """T-1's section — absent from the file entirely when the check is off."""
    check = report.get(DENSITY_CHECK)
    if check is None:
        return []
    band = check["band"]
    calibration = check["calibration"]
    officials = calibration["officials"]
    median_value = check["objects_pcc_median"]
    # Where the number sits, said the same way whether or not the band applies:
    # a `not-scoped` game is still told it is below the floor when it is.
    where = ("BELOW the floor" if check["below_floor"]
             else "inside the band, under the officials' median"
             if check["below_official_median"]
             else "at or above the officials' median")
    scope = ", ".join(f"`{tier}`" for tier in check["tier_scope"])
    parts = [
        f"## Board density (`{check['check']}`)\n",
        (
            f"- band: floor **{band['floor']}** `objects_pcc` (the officials' 25th percentile "
            f"over {officials['levels']} level-start boards), official median "
            f"{band['official_median']}, no ceiling.\n"
            f"- this game: **{_fmt(median_value)}** per-level median over "
            f"{check['levels_measured']} level-start record(s) "
            f"({_fmt(check['ratio_to_official_median'])}x the officials' median) — {where}.\n"
            f"- tier: "
            + (f"`{check['tier']}` (from {check['tier_source']})" if check["tier"] is not None
               else "unreadable")
            + f"; the band is scoped to {scope} — "
            + ("it APPLIES to this game" if check["applies"]
               else "`not-scoped`: recorded beside the band, never a verdict")
            + f".\n- {_verdict_word(check)}\n"
            f"- {check['note']}.\n"
        ),
        "| level | record | objects_pcc | below floor |",
        "| --- | --- | ---: | --- |",
    ]
    for row in check["per_level"]:
        parts.append(
            f"| {row['level']} | `{row['record']}` | {row['objects_pcc']} "
            f"| {'YES' if row['below_floor'] else '—'} |"
        )
    parts.append("")
    below = ", ".join(
        "`{}` {}".format(row["game"], _fmt(row["median"])) for row in officials["below_floor"]
    )
    ours = ", ".join(
        "`{}` {}{}".format(row["game"], _fmt(row["median"]),
                           " (below)" if row["below_floor"] else "")
        for row in calibration["ours_t1"]
    )
    ours_t2 = ", ".join(
        "`{}` {}".format(row["game"], _fmt(row["median"])) for row in calibration["ours_t2"]
    )
    parts.append(
        f"Calibration — the same comparison over the {officials['games']} signed officials' own "
        f"per-level medians: **{officials['games_at_or_above_floor']} of {officials['games']}** "
        f"at or above the floor; below: {below}; on the floor: "
        f"{', '.join(f'`{game}`' for game in officials['on_floor']) or '—'}. Ours at t1: "
        f"{ours}; at t2: {ours_t2}.\n"
    )
    parts.append(f"UNIT — {calibration['unit']}.\n")
    parts.append(f"SCOPE — {calibration['scope']}.\n")
    parts.append(f"PRICE — {calibration['price']}.\n")
    parts.append(f"- {check['band_source']}.")
    parts.append(f"- Source: {check['official_source']}.")
    parts.append("")
    return parts


def _reject_block(report: Mapping, floor_mode: str) -> str:
    """Which checks on this card could reject, and in what mode. Off ⇒ the old sentence."""
    armed = [report[key] for key in CARD_CHECKS if key in report]
    if not armed:
        return _MD_REJECT_ONE.format(floor_mode=floor_mode)
    return _MD_REJECT_MANY.format(
        count=len(armed) + 1,
        floor_mode=floor_mode,
        others="\n".join(f"- `{check['check']}` — `{check['mode']}`" for check in armed),
    )


def render_markdown(report: Mapping) -> str:
    """The card a human reads. Deterministic: it is a rendering of the json."""
    bands = report["official_bands"]
    l1_min, l1_median, l1_max = bands["l1_colors"]
    cm_min, cm_median, cm_max = bands["board_colors_median"]
    obj_min, obj_median, obj_max = bands["objects_median"]
    floor = report["l1_color_floor"]
    per_record = report["per_record"]

    parts = [
        _MD_PREAMBLE.format(
            game_id=report["game_id"], source=report["source"], count=len(per_record),
            frames=FRAMES_NAME, reject_block=_reject_block(report, floor["mode"]),
        ),
        (
            "## Level-1 color floor\n"
            if any(key in report for key in CARD_CHECKS)
            else "## Level-1 color floor — the one check that can reject\n"
        ),
        (
            f"- reset record `{floor['record']}` paints **{floor['colors']}** distinct color(s); "
            f"floor is {floor['floor']} (the official level-1 MIN — m0r0 sits exactly on it).\n"
            f"- **{'PASS' if floor['passed'] else 'FAIL'}** in `{floor['mode']}` mode"
            + ("." if floor["mode"] == "fail" else
               " — recording only; this run cannot reject on it.") + "\n"
            f"- {floor['note']}.\n"
        ),
        *_md_field_index(report),
        *_md_role_footprint(report),
        *_md_win_render(report),
        *_md_declared_vs_painted(report),
        *_md_chrome_extent(report),
        *_md_danger_visible(report),
        *_md_density(report),
        "## Per-record measurements\n",
        "| record | state | colors | objects_cc | run mode | run median | ones_share |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in per_record:
        run = row["run_length_profile"]
        parts.append(
            f"| `{row['label']}` | {row['state']} | {row['color_count']} | {row['objects_cc']} "
            f"| {run['mode']} | {_fmt(run['median'])} | {run['ones_share']:.4f} |"
        )
    parts.append("")
    parts.append(_MD_BANDS.format(
        games=OFFICIAL_GAMES, l1_min=l1_min, l1_median=l1_median, l1_max=l1_max,
        cm_min=cm_min, cm_median=cm_median, cm_max=cm_max,
        obj_min=obj_min, obj_median=obj_median, obj_max=obj_max,
        menu="{" + ", ".join(str(scale) for scale in bands["tile_scale_menu"]) + "}",
    ))

    parts.append("## Declared palette vs painted board\n")
    parts.append(
        "A declared role missing from a board is a QUESTION, not a defect: a "
        "human-accepted b002 game declares `you` and does not paint it until the first "
        "click.\n"
    )
    for row in per_record:
        absent = ", ".join(row["declared_absent"]) or "—"
        parts.append(f"- `{row['label']}`: declared-but-unpainted role(s): {absent}")
    parts.append("")

    parts.append("## HUD strip\n")
    strip = per_record[0]["hud_strip"]
    if strip == HUD_NOT_CHECKED:
        parts.append(
            f"`hud.reserved` names no strip this card can locate — reported as "
            f"`{HUD_NOT_CHECKED}`, and the reserved-index check is skipped rather than "
            f"measured against a guessed geometry.\n"
        )
    else:
        changed = any(row["hud_strip_changes"] for row in per_record)
        parts.append(
            f"Declared strip: `{strip}`. The strip changes across the run: "
            f"**{'yes' if changed else 'no'}** (a meter that fills from empty reads as an "
            f"unused HUD on the reset frame — the measured reason this is not a gate).\n"
        )
        for row in per_record:
            on_board = ", ".join(str(index) for index in row["reserved_on_board"]) or "—"
            values = ", ".join(str(value) for value in row["hud_strip_values"]) or "—"
            parts.append(
                f"- `{row['label']}`: distinct values in the strip [{values}] · reserved "
                f"index/indices painted OUTSIDE the strip: {on_board}"
            )
        parts.append("")

    parts.append("## Block uniformity — a curve, never a verdict\n")
    parts.append(
        "Share of origin-aligned s x s blocks that are a single color, one column per "
        "official tile scale. A board genuinely drawn at scale s shows a shelf at s.\n"
    )
    sizes = [str(size) for size in BLOCK_SIZES]
    parts.append("| record | " + " | ".join(f"{size}x{size}" for size in sizes) + " |")
    parts.append("| --- | " + " | ".join("---:" for _ in sizes) + " |")
    for row in per_record:
        curve = row["block_uniformity"]
        parts.append(
            f"| `{row['label']}` | " + " | ".join(f"{curve[size]:.4f}" for size in sizes) + " |"
        )
    parts.append("")
    parts.append(
        f"Contact sheet: `{CONTACT_SHEET_NAME}` — one tile per record, "
        f"{SHEET_CELL_PX} px per cell, in the canon render palette.\n"
    )
    return "\n".join(parts)


# --- the contact sheet --------------------------------------------------------


def _rgb(index: int) -> tuple[int, int, int]:
    """One palette index as RGB, clamped the way the canon's own renderer clamps."""
    hex_value = ARC_PALETTE_HEX[max(PALETTE_MIN, min(PALETTE_MAX, int(index)))]
    return (int(hex_value[1:3], 16), int(hex_value[3:5], 16), int(hex_value[5:7], 16))


def write_contact_sheet(grids: Sequence[Sequence[Sequence[int]]], path: Path) -> Path:
    """One tile per record in a single horizontal strip, white gutters between.

    The eye is the point: the numbers above say a board has 6 colors and 12
    objects, and only the picture says whether those 12 objects are legible.
    Deterministic — Pillow writes no timestamp chunk, and every pixel comes
    from the grids and `ARC_PALETTE_HEX`.
    """
    tiles = []
    for grid in grids:
        height, width = len(grid), len(grid[0])
        tile = Image.new("RGB", (width, height))
        tile.putdata([_rgb(value) for row in grid for value in row])
        tiles.append(tile.resize((width * SHEET_CELL_PX, height * SHEET_CELL_PX),
                                 Image.Resampling.NEAREST))
    sheet_width = sum(tile.width for tile in tiles) + SHEET_GUTTER_PX * (len(tiles) - 1)
    sheet = Image.new("RGB", (sheet_width, max(tile.height for tile in tiles)),
                      SHEET_GUTTER_RGB)
    offset = 0
    for tile in tiles:
        sheet.paste(tile, (offset, 0))
        offset += tile.width + SHEET_GUTTER_PX
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, format="PNG")
    return path
