"""Blind pins for contract B1 (wave 3, sub-phase B) — the VISUAL LANE.

Run: .venv/bin/python -m pytest gen/tests/test_w3_visuallane.py -v

Three refinement contracts land together here and this file pins all three by
their stated semantics:

* **R-03 authored chrome** — two authored decor objects exist in the whole
  7-game corpus (pump-flow's decoy junction, facing-sentinel's demo tile);
  our `occupied_extent` is 0.47x the officials' and 3 of 7 games sit BELOW
  their observed band.  The officials' decor is CHROME — letterboxes, bezels,
  panel slabs, dividers — which is why their boards read as places.  So:
  a chrome idiom section in the payload, an optional `game.chrome` §11
  declaration, and a card metric + PAIRED check on the visual card.
* **R-13 danger tells** — pump-flow's tell vanishes twice over (fog-suppressed
  OPEN valve paints no `8`; closed-beat camouflage), pump-phase's hazard is
  never an object at all, and convoy's fog `2` is LIGHTER than its revealed
  rail `3` so revealing reads as shadow.  All 19 official hazard rows are
  placed objects that stand on the board before they bite.
* **R-08 (payload/§11 half)** — refusal that both signals and charges ships in
  2 games against §6:158's "charge silently or signal freely — never both",
  and a refusal the player must learn has to survive into a settled frame or
  be DECLARED transient.

BLINDNESS.  Written from the frozen B1 contract text ALONE, by a separate
agent, while the implementer's change was in flight.  No line of the
implementer's in-progress `gen/visual_canon.py`, `gen/s1_spec.py`,
`gen/s3_visual.py`, `gen/s3_gate.py` or `config/template.yaml` was read.  The
only things read off the tree are the PRE-STATE shapes the contract names as
its own precedents — the W1/W2 card checks and their `off|record|fail` knobs,
`GATE_KEYS` as a closed key set, the `tiny_token` optional-field precedent,
the fidelity-rule registry, and the committed `gen/tests/fixtures/specs/`
corpus — so that these pins describe the CONTRACT and not the implementation.

LAUNCH-TIME DISCRIMINATION NOTE (measured on the phase-A close tree at this
file's start, 2026-09-28; kept as a note, never as a pin — a "new since HEAD"
delta would rot the moment the change is committed).  Every contract-bearing
pin below was checked to FAIL against that tree and is written as a standing
"the live module does X" claim, so it keeps its meaning after the commit:

  * `s3_visual.GATE_KEYS` carried exactly 8 entries — `visual_card`,
    `l1_color_floor`, `field_index`, `role_footprint`,
    `role_footprint_exempt`, `win_render`, `declared_vs_painted`,
    `declared_vs_painted_exempt` — and nothing spelling chrome or danger;
    `CARD_CHECKS` carried the four W1 checks.
  * `s1_spec.FIDELITY_RULES` carried FOUR rules (`mix-hazardless`,
    `terms-introduced-coverage`, `unstated-background`, `silent-levels`) and
    no `refusal-persistence`.  (The launch prompt said five — see AMBIGUITY 6.)
  * A spec carrying `game.chrome` linted with an `unknown-field` WARN
    ("game.chrome: not a §11 field (ignored downstream)"); a
    `knobs.refusal_transient` of ANY type — `true`, `"yes"` — linted
    completely clean, because extra `knobs` keys were unread.
  * `gen/visual_canon.py` contained no occurrence of letterbox / bezel /
    divider / slab / chrome / FRAMED / lighter / transient / persist / "158".
  * The all-checks-off card measured on this file's own fixture hashed to
    `BYTE_PIN_JSON_SHA256` / `BYTE_PIN_MD_SHA256` below — the two numbers the
    off-mode pins freeze FORWARD, not backward.

CONTRACT AMBIGUITIES, each restated at the pin that depends on it:

 1. **`chrome.where` is "<token>" and its vocabulary is unstated.**  The §11
    pins DISCOVER which tokens the linter accepts (`_accepted_where_tokens`)
    instead of naming one, and the card fixtures paint the whole one-cell
    perimeter ring — row 0, row 63, column 0, column 63 — and declare chrome
    over every accepted edge-ish token, so whichever geometry the card reads
    is painted.  If the accepted vocabulary turns out to be free prose, the
    card can locate no region and pin 5d says so in as many words.
 2. **Which side of `refusal-persistence` fires.**  The contract defines the
    PROMISE ("refusal: visible without refusal_transient promises a
    settled-frame-persistent signal") and leaves the S1 finding's trigger to
    the implementer.  Pin 3d therefore sweeps the six refusal x transient
    shapes, requires that SOME shape fires under `kill` (a registry rule that
    can never fire is an inert knob), and hard-pins only the one direction the
    contract's own words fix: `refusal: visible` + `refusal_transient: true`
    is the DECLARED exemption and must never fire.
 3. **`reveal_brightness_ok` when nothing declares fog.**  The contract says
    to compute it "ONLY when unambiguous and record not-checked otherwise,
    honestly", so pin 6g gives the check a spec with no fog/conceal term and
    no grey-ramp role at all, and demands an honest not-checked rather than a
    bare `true`.  The INVERTED-ordering case (convoy) is not pinned on
    synthetic frames because nothing in §11 yet declares which index is the
    concealed one; what is pinned is the payload rule and the canon ramp.
 4. **The camouflage exemption's home.**  "reads `knobs.deceptions` for the §3
    camouflage lever" is the contract's word, and `camouflage` is also a
    `DANGER_TELLS` value, so the exempt fixture declares BOTH
    (`deceptions: ["camouflage"]` and `danger_tell: camouflage`) — either
    reading is satisfied and neither is pinned as the one true home.
 5. **Where the new payload sections ride.**  B1's file list is
    visual_canon / s1_spec / s3_visual / s3_gate / template.yaml and does NOT
    include `gen/s2_implement.py`, which is the module that assembles the S2
    payload out of NAMED `visual_canon` constants.  Pin 4d reads that as
    prompt-sync rather than as a typo: a REQUIRED row the implementer is
    judged on has to be in the prompt the implementer is handed, so the
    payload module must name whichever constant carries it (a two-line wiring:
    one import, one entry in the `sections` list).
 6. **`FIDELITY_RULES` had four entries, not five.**  The launch prompt
    described the phase-A close as carrying five.  Nothing here pins the
    COUNT: pin 3a asks for membership and for the registry's own invariants,
    so a fifth rule landing from elsewhere cannot break it.

HYGIENE: `tmp_path` only.  Nothing under `out/` is read or written, no
network, no driver, no engine run, no API call, no git.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Mapping, Sequence
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from gen import s1_spec, s3_visual, visual_canon
from gen.config import REPO_ROOT, load_config
from gen.s0_ideas import load_vocab

# --- locations ----------------------------------------------------------------

ROOT = Path(REPO_ROOT)
TEMPLATE_PATH = ROOT / "config" / "template.yaml"
PAYLOAD_SOURCE = ROOT / "gen" / "s2_implement.py"
FIXTURES = ROOT / "gen" / "tests" / "fixtures" / "specs"
GOOD_SPEC = FIXTURES / "good-spec.yaml"

SPEC_NAME = "spec.yaml"
FRAMES_NAME = "worker.frames.json"
CARD_JSON = Path("worker.gate") / "visual-report.json"
CARD_MD = Path("worker.gate") / "visual-report.md"

# --- the contract's frozen surface -------------------------------------------

CHROME_EXTENT = "chromeextent"          # the check named `chrome-extent`
DANGER_VISIBLE = "dangervisible"        # the check named `danger-visible`
REFUSAL_PERSISTENCE = "refusal-persistence"
REFUSAL_TRANSIENT = "refusal_transient"
CHROME_FIELD = "chrome"

CHECK_MODES = ("off", "record", "fail")
DEFAULT_MODE = "record"
BAD_MODES = ("on", "true", "Record", "warn", "kill", "")
FIDELITY_ACTIONS = ("off", "warn", "kill")
FIDELITY_DEFAULT = "off"
TEMPLATE_FIDELITY_ACTION = "warn"       # "template arms warn", B1's own words

# The four chrome idioms, frozen by the contract, with the official cite each
# one carries (ft09 letterbox panels, cd82 banner+rules, sk48 inset slab,
# dc22 divider).
CHROME_KINDS = ("letterbox", "panel", "divider", "bezel")
CHROME_CITES = ("ft09", "cd82", "sk48", "dc22")

# R-03's acceptance, quoted: "`occupied_extent` per-game median inside the
# officials' observed 361..2889 band ... **paired with** a card row counting
# authored (non-background) decor objects >= 1"
# (audit/comparative/refinement-contracts.md, R-03).  `occupied_extent` is
# "cells that are not the modal value" (audit_common.occupied_extent), so the
# band is a CELL COUNT on a 4096-cell camera; the fixtures below are built to
# discriminate under a share reading too (52 and 304 of 4096 = 0.013 / 0.074,
# both under 361/4096 = 0.088; 1261 of 4096 = 0.308, inside 0.088..0.705).
OFFICIAL_EXTENT_LOW = 361
OFFICIAL_EXTENT_HIGH = 2889
BOARD_CELLS = 64 * 64

# R-13's corpus fact, quoted: "all 19 official hazard rows" are placed objects.
OFFICIAL_HAZARD_ROWS = 19

# §6:158, the line the never-signal-and-charge row quotes.
REFUSAL_RULE_LINE = "158"

# --- the synthetic boards ------------------------------------------------------
# 64x64 because every frozen card metric assumes the ARC camera and all seven
# shipped sidecars are 64x64.

SIDE = 64
BG = 5                 # affordance §9: "`5` black — background/outline default"
CHROME_INDEX = 3       # a structural grey: the study's own chrome colour family
YOU = 9
GOAL = 14
DANGER = 8
WHITE = 0              # the ecosystem's selection mark
NON_GREY_BG = 11       # a field with NO grey-ramp role anywhere (pin 6g)

WIN_STATE = "WIN"
LIVE_STATE = "NOT_FINISHED"
SYNTHETIC_GAME = "w3-b1-synthetic"

# The greys the canon render palette orders: 0 white (255) .. 5 black (0).
# convoy's exhibit is fog `2` (153,153,153) LIGHTER than revealed rail `3`
# (102,102,102) — so on this ramp a LOWER index is a LIGHTER colour.
GREY_LIGHT, GREY_DARK = 2, 3

# --- the off-mode byte pins ----------------------------------------------------
# MEASURED on the phase-A close tree, on `byte_case()`'s own fixture, with every
# knob in `GATE_KEYS` resolved to its quietest legal value the discovery way
# (`_off_gate`).  They are frozen FORWARD: a card built with every check off
# must still be these bytes once B1 lands, which is what "shipped cards
# byte-identical with new modes off" means.  `l1_color_floor` has no `off` in
# its enum, so it resolves to `record` and its block stays on the card.
BYTE_PIN_JSON_SHA256 = "38bd547112e329cd649c9c56aeacb1f35033a541f6da1cd90ad86e1b2e13b2eb"
BYTE_PIN_MD_SHA256 = "370fedccf068086f1fe5485c6e76ffca55137af2e6847f01dc5f57e727176583"
BYTE_PIN_JSON_BYTES = 3400
BYTE_PIN_TOP_KEYS = ("game_id", "l1_color_floor", "official_bands", "per_record", "source")
BYTE_PIN_PER_RECORD_KEYS = (
    "block_uniformity", "color_count", "colors", "declared_absent", "hud_strip",
    "hud_strip_changes", "hud_strip_values", "label", "levels_completed", "modal_value",
    "objects_cc", "reserved_on_board", "run_length_profile", "seq", "state",
)
BYTE_PIN_OFFICIAL_BANDS_KEYS = (
    "board_colors_median", "default_fps", "l1_colors", "native_64_count",
    "objects_median", "tile_scale_menu",
)

# The unconfigured lint of the committed good spec, measured on the same tree:
# `lint_spec(good, vocab)` with no knob at all.  Frozen forward for the same
# reason — "unconfigured lints byte-identical" is half of B1's replay line.
STOCK_LINT_REPORT = {"passed": True, "kills": [], "warns": [], "spec_hash": ""}

_MISSING = object()


# --- normalised lookup (shape unpinned, meaning pinned) -----------------------


def norm_key(name: object) -> str:
    """`chrome-extent`, `chrome_extent` and `chromeExtent` are one name."""
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def norm_text(text: object) -> str:
    """Backtick- and wrap-insensitive text (`test_b6_payload._norm`'s rule)."""
    return re.sub(r"\s+", " ", str(text).replace("`", "")).strip().lower()


def find(container: object, wanted: str, depth: int = 2) -> object:
    """The value whose KEY normalises to `wanted`, here or `depth` levels in."""
    if not isinstance(container, Mapping):
        return _MISSING
    for key, value in container.items():
        if norm_key(key) == wanted:
            return value
    if depth <= 0:
        return _MISSING
    for value in container.values():
        found = find(value, wanted, depth - 1)
        if found is not _MISSING:
            return found
    return _MISSING


def find_containing(container: object, fragment: str, depth: int = 3) -> object:
    """The value whose normalised KEY CONTAINS `fragment` — the looser reader."""
    if not isinstance(container, Mapping):
        return _MISSING
    for key, value in container.items():
        if fragment in norm_key(key):
            return value
    if depth <= 0:
        return _MISSING
    for value in container.values():
        found = find_containing(value, fragment, depth - 1)
        if found is not _MISSING:
            return found
    return _MISSING


def find_metric(block: object, *fragments: str) -> object:
    """The first metric whose key matches any of `fragments`, in preference order.

    The card's key SPELLINGS are the implementer's; what B1 freezes is the
    measurement.  Each pin names the spellings it would accept, widest last, so
    a rename is never what a pin fails on.
    """
    for fragment in fragments:
        found = find_containing(block, fragment)
        if found is not _MISSING:
            return found
    return _MISSING


def key_map(container: object, depth: int = 2) -> list[str]:
    """Every key a failure message should print, `depth` levels down."""
    if not isinstance(container, Mapping):
        return []
    keys = [str(key) for key in container]
    if depth > 0:
        for value in container.values():
            keys.extend(key_map(value, depth - 1))
    return sorted(set(keys))


def strings_in(node: object) -> list[str]:
    """Every string anywhere inside a block — its prose, whatever it is called."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, Mapping):
        return [text for value in node.values() for text in strings_in(value)]
    if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        return [text for value in node for text in strings_in(value)]
    return []


def numbers_in(node: object) -> list[float]:
    """Every number anywhere inside a block (bools are not numbers here)."""
    if isinstance(node, bool):
        return []
    if isinstance(node, (int, float)):
        return [float(node)]
    if isinstance(node, Mapping):
        return [value for item in node.values() for value in numbers_in(item)]
    if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        return [value for item in node for value in numbers_in(item)]
    return []


# --- reading a check block ----------------------------------------------------

NOT_CHECKED_RE = re.compile(
    r"not[-_ ]?checked|\bn/a\b|\bskipp?ed\b|\bunchecked\b|\bundeclared\b|\bunknown\b",
    re.IGNORECASE,
)
PASS_KEYS = ("passed", "pass", "ok", "clean")
FAIL_WORDS = {"fail", "failed", "failing", "violation", "violations", "reject", "rejected", "red"}
PASS_WORDS = {"pass", "passed", "ok", "clean", "none", "green"}


def check_block(report: Mapping, check: str, *, label: str) -> Mapping:
    """The card-level block for one of B1's two new checks."""
    found = find(report, check)
    if found is _MISSING or not isinstance(found, Mapping):
        pytest.fail(
            f"the visual card carries no {label!r} block (a mapping keyed on some spelling of "
            f"{label!r}); the card offers {key_map(report, depth=0)}.  Contract B1 freezes "
            f"{label!r} as a card-level check beside `l1_color_floor` / `field-index` / "
            f"`role-footprint` / `win-render` — the shape it names as the pattern to match"
        )
    return found


def is_not_checked(block: Mapping) -> bool:
    """The check declined to judge — structurally, not from free prose."""
    for name in ("status", "verdict", "result", "state"):
        value = find(block, name, depth=0)
        if isinstance(value, str) and NOT_CHECKED_RE.search(value):
            return True
    value = find(block, "notchecked", depth=0)
    if isinstance(value, bool) and value:
        return True
    value = find(block, "checked", depth=0)
    return isinstance(value, bool) and not value


def verdict(block: Mapping, *, label: str) -> bool | None:
    """`True` passed, `False` failed, `None` not checked (`l1_color_floor`'s face)."""
    if is_not_checked(block):
        return None
    for name in PASS_KEYS:
        found = find(block, name, depth=0)
        if isinstance(found, bool):
            return found
    for name in ("verdict", "status", "result"):
        found = find(block, name, depth=0)
        if isinstance(found, str):
            word = found.strip().lower()
            if word in PASS_WORDS:
                return True
            if word in FAIL_WORDS:
                return False
    pytest.fail(
        f"{label}: the check block carries no pass/fail face — it offers {key_map(block)}.  "
        f"`l1_color_floor` reports `passed: bool`, and a check with no verdict is a "
        f"measurement the gate can never read"
    )


def mode_of(block: Mapping, *, label: str) -> str:
    found = find(block, "mode", depth=0)
    if not isinstance(found, str):
        pytest.fail(
            f"{label}: the check block carries no `mode` string ({key_map(block)}).  Every "
            f"check in `gen/s3_visual.py` records the mode it ran in, so a reader can tell a "
            f"recorded failure from a rejecting one"
        )
    return found


# --- the boards ----------------------------------------------------------------


def blank(value: int = BG) -> list[list[int]]:
    return [[value] * SIDE for _ in range(SIDE)]


def paint(grid: list[list[int]], top: int, left: int, height: int, width: int,
          value: int) -> None:
    for y in range(top, top + height):
        for x in range(left, left + width):
            grid[y][x] = value


def ring(grid: list[list[int]], value: int = CHROME_INDEX) -> None:
    """A one-cell perimeter — row 0, row 63, column 0, column 63.

    AMBIGUITY 1: this is the geometry EVERY edge-ish `chrome.where` token could
    name (row0 / row63 / col0 / col63 / top / bottom / left / right / edge /
    border / perimeter / frame), painted in one go, so the card finds the
    declared chrome painted whichever token vocabulary the linter accepted.
    252 cells, which keeps the sparse board's `occupied_extent` under the
    officials' 361-cell floor: the paired check's below-band leg stays true.
    """
    for x in range(SIDE):
        grid[0][x] = value
        grid[SIDE - 1][x] = value
    for y in range(SIDE):
        grid[y][0] = value
        grid[y][SIDE - 1] = value


def furniture(grid: list[list[int]], *, danger: bool = True) -> None:
    """The four role blocks every board carries, well clear of the perimeter."""
    paint(grid, 10, 10, 4, 4, YOU)
    paint(grid, 20, 20, 4, 4, GOAL)
    paint(grid, 30, 30, 2, 2, WHITE)
    if danger:
        paint(grid, 40, 40, 4, 4, DANGER)


def sparse_board(*, chrome: bool = False, danger: bool = True,
                 field: int = BG) -> list[list[int]]:
    """An EMPTY-reading board: 52 occupied cells bare, 304 with the chrome ring.

    Both are below the officials' 361-cell floor, which is the below-band leg
    of R-03's paired acceptance.
    """
    grid = blank(field)
    if chrome:
        ring(grid)
    furniture(grid, danger=danger)
    return grid


def dense_board(*, danger: bool = True) -> list[list[int]]:
    """A board INSIDE the officials' band and carrying no authored chrome at all.

    1261 occupied cells of 4096 — inside 361..2889 — so the in-band leg of the
    pairing is true while the chrome count stays 0.
    """
    grid = blank(BG)
    paint(grid, 10, 10, 35, 35, GOAL)
    paint(grid, 4, 4, 4, 4, YOU)
    paint(grid, 50, 50, 2, 2, WHITE)
    if danger:
        paint(grid, 48, 10, 4, 4, DANGER)
    return grid


def occupied_extent(grid: Sequence[Sequence[int]]) -> int:
    """`audit_common.occupied_extent` — cells that are not the modal value."""
    counts: dict[int, int] = {}
    for row in grid:
        for value in row:
            counts[value] = counts.get(value, 0) + 1
    modal = min(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return sum(1 for row in grid for value in row if value != modal)


# --- the sidecars ---------------------------------------------------------------


def record(label: str, seq: int, completed: int, state: str,
           grid: Sequence[Sequence[int]]) -> dict:
    return {"label": label, "seq": seq, "levels_completed": completed, "state": state,
            "grid": [list(row) for row in grid]}


def sidecar(level_grids: Sequence[Sequence[Sequence[int]]],
            win_grid: Sequence[Sequence[int]] | None = None,
            *, game_id: str = SYNTHETIC_GAME) -> dict:
    """reset + one settled frame per level transition + `final`, as S2b writes it.

    One record per level start, in the order handed in, so
    `level_start_indices` sees exactly `len(level_grids)` level starts (the
    trailing WIN record increments the count but is the win screen, not a
    level).
    """
    rows = [record("reset", 0, 0, LIVE_STATE, level_grids[0])]
    for index, grid in enumerate(level_grids[1:], start=1):
        rows.append(record(f"step-{9 * index}:ACTION5", index, index, LIVE_STATE, grid))
    count = len(level_grids)
    rows.append(record("final", count, count, WIN_STATE,
                       win_grid if win_grid is not None else level_grids[-1]))
    return {"game_id": game_id, "source": "synthetic", "levels_completed": count,
            "win": True, "records": rows}


def spec_document(*, chrome: Sequence[Mapping] | None = None, danger: int | None = DANGER,
                  background: int = BG, terms: Sequence[str] = ("move.grid", "hazard.static"),
                  danger_tell: str = "unique-hue", deceptions: Sequence[str] = (),
                  refusal: str = "visible", refusal_transient: object = _MISSING,
                  reserved: Sequence[int] = (1, 2), levels: int = 3) -> dict:
    """A §11-shaped spec carrying everything a visual check could read.

    Fuller than the card needs today on purpose: B1 gives the card new reasons
    to read `terms`, `knobs` and `levels`, and a fixture that carried only
    palette/hud/render would make a check that reads them look broken.
    """
    knobs: dict[str, object] = {
        "refusal": refusal,
        "goal_legible": "obvious",
        "danger_tell": danger_tell,
        "deceptions": list(deceptions),
    }
    if refusal_transient is not _MISSING:
        knobs[REFUSAL_TRANSIENT] = refusal_transient
    palette: dict[str, object] = {
        "you": YOU, "goal": GOAL, "danger": danger,
        "background": background, "reserved": list(reserved),
    }
    game: dict[str, object] = {
        "slug": SYNTHETIC_GAME,
        "title": "W3-B1 synthetic",
        "terms": list(terms),
        "knobs": knobs,
        "palette": palette,
        "hud": {"reserved": "row63",
                "meter": {"placement": "row63-left", "direction": "shrink-right"}},
        "render": {"cell_px": 4},
        "levels": [
            {"relation_to_prev": "new" if index == 0 else "reuse",
             "terms_introduced": list(terms) if index == 0 else [],
             "sketch": f"level {index + 1} of the synthetic fixture"}
            for index in range(levels)
        ],
    }
    if chrome is not None:
        game[CHROME_FIELD] = [dict(entry) for entry in chrome]
    return {"game": game}


def stage_case(directory: Path, frames: Mapping, spec: Mapping) -> Path:
    """One synthetic slot — spec + frames sidecar — inside tmp_path.  Never `out/`."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SPEC_NAME).write_text(
        yaml.safe_dump(dict(spec), sort_keys=False, allow_unicode=True), encoding="utf-8")
    (directory / FRAMES_NAME).write_text(
        json.dumps(dict(frames), indent=2) + "\n", encoding="utf-8")
    return directory


def byte_case(directory: Path) -> Path:
    """THE fixture the off-mode byte pins are frozen against.  Do not edit.

    Three identical sparse level starts and a dense win frame, with the plain
    §11 spec above.  Changing any of it invalidates `BYTE_PIN_JSON_SHA256`,
    which is the point of saying so here.
    """
    board = sparse_board()
    return stage_case(directory, sidecar([board, board, board], dense_board()),
                      spec_document())


# --- the module surface, discovered ------------------------------------------


def _gate_keys() -> tuple[str, ...]:
    keys = getattr(s3_visual, "GATE_KEYS", None)
    if not isinstance(keys, (list, tuple)):
        pytest.fail(
            "gen.s3_visual exposes no GATE_KEYS tuple — it is the closed key set every gate "
            "knob has to join (`_gate_block` refuses an unknown key), and the only honest "
            "place to read B1's two new knob names out of"
        )
    return tuple(str(key) for key in keys)


def _resolve_knob(check: str, label: str) -> str:
    for key in _gate_keys():
        if norm_key(key) == check:
            return key
    pytest.fail(
        f"no gate knob in gen.s3_visual.GATE_KEYS spells {label!r}: the closed key set is "
        f"{list(_gate_keys())}.  B1 arms this check from config/template.yaml and "
        f"`_gate_block` refuses any key the tuple does not carry, so the knob MUST be in "
        f"GATE_KEYS"
    )


def _resolve_reader(knob: str, check: str, label: str):
    """The `<check>_mode(cfg)` reader — by name, then by behaviour."""
    named = [
        (name, value) for name, value in vars(s3_visual).items()
        if callable(value) and not name.startswith("_") and check in norm_key(name)
    ]
    for _name, reader in named:
        try:
            if reader({"gate": {knob: "fail"}}) == "fail":
                return reader
        except Exception:  # noqa: BLE001, S112 — a wrong candidate, not a finding
            continue
    for _name, value in vars(s3_visual).items():
        if not callable(value) or _name.startswith("_"):
            continue
        try:
            if value({"gate": {knob: "fail"}}) == "fail" and value({}) == DEFAULT_MODE:
                return value
        except Exception:  # noqa: BLE001, S112 — as above
            continue
    pytest.fail(
        f"gen.s3_visual exposes no mode reader for {label!r} (gate key {knob!r}).  The house "
        f"pattern is `visual_card_mode` / `l1_floor_mode` / `field_index_mode` / "
        f"`win_render_mode`: a module-level `cfg -> 'off'|'record'|'fail'` reader.  Callables "
        f"whose name mentions the check: {[name for name, _ in named] or 'none'}"
    )


@pytest.fixture(scope="session")
def chrome_key() -> str:
    return _resolve_knob(CHROME_EXTENT, "chrome-extent")


@pytest.fixture(scope="session")
def danger_key() -> str:
    return _resolve_knob(DANGER_VISIBLE, "danger-visible")


@pytest.fixture(scope="session")
def chrome_reader(chrome_key: str):
    return _resolve_reader(chrome_key, CHROME_EXTENT, "chrome-extent")


@pytest.fixture(scope="session")
def danger_reader(danger_key: str):
    return _resolve_reader(danger_key, DANGER_VISIBLE, "danger-visible")


@pytest.fixture(scope="session")
def off_gate(tmp_path_factory) -> dict:
    """Every knob in GATE_KEYS at its quietest legal value — DISCOVERED, not typed.

    B1's own instruction ("force ALL post-A2 check modes off in card-building
    fixtures — enumerate from GATE_KEYS the discovery way"): a knob added
    tomorrow joins this map without anyone editing this file.  `off` is tried
    first, `record` is the fallback for an enum that has no `off`
    (`l1_color_floor`), and a `*_exempt` key takes the empty list.
    """
    spec_dir = byte_case(tmp_path_factory.mktemp("off-gate-probe") / "case")
    gate: dict[str, object] = {
        key: ([] if key.endswith("_exempt") else "off") for key in _gate_keys()
    }
    for _attempt in range(len(gate) + 2):
        try:
            s3_visual.build_visual_card(spec_dir, {"gate": gate})
        except ValueError as exc:
            message = str(exc)
            relaxed = next(
                (key for key in gate if f"gate.{key}" in message and gate[key] == "off"), None)
            if relaxed is None:
                pytest.fail(
                    f"the all-off gate block {gate!r} was refused by gen.s3_visual and the "
                    f"refusal names no knob this fixture can relax: {message}"
                )
            gate[relaxed] = DEFAULT_MODE
            continue
        return gate
    pytest.fail(f"the all-off gate block never settled: {gate!r}")


@pytest.fixture
def build(off_gate: dict, tmp_path: Path):
    """Build one card with every check off except the ones handed in."""

    def make(name: str, frames: Mapping, spec: Mapping, **armed: str) -> Mapping:
        gate = dict(off_gate)
        gate.update(armed)
        return s3_visual.build_visual_card(
            stage_case(tmp_path / name, frames, spec), {"gate": gate})

    return make


# --- the lint surface ---------------------------------------------------------


@lru_cache(maxsize=1)
def _cfg() -> dict:
    """`config/template.yaml`, loaded — every reader pin's one input."""
    if not TEMPLATE_PATH.is_file():
        pytest.fail(f"config/template.yaml missing: {TEMPLATE_PATH}")
    return load_config(TEMPLATE_PATH)


@lru_cache(maxsize=1)
def _vocab() -> frozenset:
    return frozenset(load_vocab(_cfg()))


@lru_cache(maxsize=1)
def _good_spec_text() -> str:
    if not GOOD_SPEC.is_file():
        pytest.fail(f"the committed good spec is missing: {GOOD_SPEC}")
    return GOOD_SPEC.read_text(encoding="utf-8")


def good_spec(**changes: object) -> dict:
    """The committed §11 good spec, parsed fresh, with `game` keys replaced."""
    spec = yaml.safe_load(_good_spec_text())
    for key, value in changes.items():
        if value is _MISSING:
            spec["game"].pop(key, None)
        else:
            spec["game"][key] = value
    return spec


def with_knob(spec: Mapping, name: str, value: object) -> dict:
    out = deepcopy(dict(spec))
    if value is _MISSING:
        out["game"]["knobs"].pop(name, None)
    else:
        out["game"]["knobs"][name] = value
    return out


def lint(spec: Mapping, **kwargs):
    return s1_spec.lint_spec(deepcopy(dict(spec)), _vocab(), None, None, **kwargs)


def findings(report, rule: str) -> list[dict]:
    rows = list(report.kills) + list(report.warns)
    return [row for row in rows if norm_key(row.get("rule")) == norm_key(rule)]


def chrome_findings(report) -> list[dict]:
    """Every kill or warn whose detail mentions `game.chrome`."""
    rows = list(report.kills) + list(report.warns)
    return [row for row in rows if CHROME_FIELD in norm_text(row.get("detail"))]


WHERE_CANDIDATES = (
    # the three strips `s3_visual.HUD_STRIP_GEOMETRY` already knows, first
    "row0", "row63", "col0",
    # then the rest of the perimeter the fixture paints
    "col63", "top", "bottom", "left", "right",
    "edge", "border", "perimeter", "frame", "band",
)


@lru_cache(maxsize=1)
def _accepted_where_tokens() -> tuple[str, ...]:
    """Which `chrome.where` tokens the §11 linter accepts (AMBIGUITY 1).

    A token is accepted when a spec declaring `chrome: [{kind: letterbox,
    where: <token>}]` lints with no kill and no finding about `game.chrome` at
    all — the `tiny_token` bar: a declaration nobody reads is not a
    declaration.
    """
    accepted = []
    for token in WHERE_CANDIDATES:
        report = lint(good_spec(chrome=[{"kind": CHROME_KINDS[0], "where": token}]))
        if report.passed and not chrome_findings(report):
            accepted.append(token)
    return tuple(accepted)


def where_token() -> str:
    tokens = _accepted_where_tokens()
    if not tokens:
        sample = lint(good_spec(chrome=[{"kind": CHROME_KINDS[0], "where": WHERE_CANDIDATES[0]}]))
        pytest.fail(
            f"the §11 linter accepts no `chrome.where` token this file can name.  Tried "
            f"{list(WHERE_CANDIDATES)}, each inside `chrome: [{{kind: letterbox, where: "
            f"<token>}}]` on the committed good spec, and every one of them either killed the "
            f"spec or left a finding naming `game.chrome`.  On `where: "
            f"{WHERE_CANDIDATES[0]}` the linter said kills={sample.kills!r} "
            f"warns={sample.warns!r}.  B1 writes the field as `{{kind: "
            f"letterbox|panel|divider|bezel, where: <token>}}` — the smallest honest schema — "
            f"so SOME token vocabulary has to be accepted; name it and this pin resolves"
        )
    return tokens[0]


def chrome_declaration() -> list[dict]:
    """A chrome declaration over every accepted edge token, capped at four entries.

    One KIND for all of them (the kind the token discovery itself was run
    against), so a schema that cross-checks kind against geometry cannot make
    this fixture's declaration invalid by accident.
    """
    tokens = _accepted_where_tokens()[:4] or [where_token()]
    return [{"kind": CHROME_KINDS[0], "where": token} for token in tokens]


# --- the payload constants ----------------------------------------------------


@lru_cache(maxsize=1)
def _canon_texts() -> dict[str, str]:
    """Every module-level text `gen/visual_canon.py` can put in a payload.

    Keyed by the name the payload would import, and deliberately generous about
    SHAPE: a string constant, every string nested inside a constant mapping or
    tuple (the `KNOB_ECHOES` / `WIN_RENDER_CALIBRATION` shape), and what a
    zero-argument public callable renders (`corpus_numbers_card`'s shape).  A
    rule's WORDS are what these pins read; where the implementer keeps them is
    not pinned.
    """
    texts: dict[str, str] = {}
    for name, value in vars(visual_canon).items():
        if name.startswith("__"):
            continue
        if callable(value):
            if name.startswith("_"):
                continue
            try:
                rendered = value()
            except Exception:  # noqa: BLE001, S112 — it needs arguments; not a payload block
                continue
            if isinstance(rendered, str):
                texts[name] = rendered
            continue
        nested = strings_in(value)
        if nested:
            texts[name] = "\n".join(nested)
    return texts


def _matches(flat: str, anchor: object) -> bool:
    """One anchor: a string, or a tuple of spellings any one of which will do."""
    if isinstance(anchor, tuple):
        return any(option in flat for option in anchor)
    return str(anchor) in flat


def canon_block(*anchors: object, label: str) -> str:
    """The ONE visual_canon text carrying every anchor — its name, for pin 4g."""
    for name, text in sorted(_canon_texts().items()):
        flat = norm_text(text)
        if all(_matches(flat, anchor) for anchor in anchors):
            return name
    pytest.fail(
        f"no text in gen/visual_canon.py carries the {label} rule: no module-level constant "
        f"(or zero-argument renderer) contains all of {list(anchors)} (a tuple means any one "
        f"spelling will do).  Contract B1 puts this row in the S2 payload through this "
        f"module — the `FLOOR_AND_FOOTPRINT` / `WIN_IS_RENDERED` pattern, a REQUIRED row with "
        f"its corpus cites.  The module currently offers these texts: {sorted(_canon_texts())}"
    )


@lru_cache(maxsize=1)
def _payload_source() -> str:
    if not PAYLOAD_SOURCE.is_file():
        pytest.fail(f"gen/s2_implement.py missing: {PAYLOAD_SOURCE}")
    return PAYLOAD_SOURCE.read_text(encoding="utf-8")


# =============================================================================
# PIN 1 — §11: the optional `game.chrome` declaration
# =============================================================================


def test_pin1a_a_declared_chrome_block_is_a_known_field() -> None:
    """`game.chrome` is a §11 field: no kill, and NOT an unknown-field warn."""
    report = lint(good_spec(chrome=[{"kind": CHROME_KINDS[0], "where": where_token()}]))
    assert report.passed, (
        f"a well-formed `game.chrome` declaration killed the committed good spec: "
        f"{report.kills!r}.  B1 adds it as an OPTIONAL §11 field on `palette.tiny_token`'s "
        f"terms — absent is silence, present is a declaration"
    )
    assert not chrome_findings(report), (
        f"a well-formed `game.chrome` declaration is still reported as a finding: "
        f"{chrome_findings(report)!r}.  An optional field joins the KNOWN keys (the "
        f"`OPTIONAL_GAME_FIELDS` idiom `render` / `hazardless_override` follows), which is "
        f"what keeps it off the unknown-field warn — a declaration the linter calls "
        f"'ignored downstream' is not a declaration"
    )


@pytest.mark.parametrize("kind", CHROME_KINDS)
def test_pin1b_every_chrome_kind_in_the_closed_enum_is_accepted(kind: str) -> None:
    """letterbox | panel | divider | bezel — the four idioms, frozen by contract.

    Every accepted `where` token is tried before the kind is called refused, so
    a schema that pairs a kind with a geometry is not what this pin fails on.
    """
    tried = {}
    for token in _accepted_where_tokens() or (where_token(),):
        report = lint(good_spec(chrome=[{"kind": kind, "where": token}]))
        if report.passed and not chrome_findings(report):
            return
        tried[token] = (report.kills, report.warns)
    pytest.fail(
        f"`chrome: [{{kind: {kind}, where: <token>}}]` was refused for every `where` token "
        f"the linter otherwise accepts: {tried!r}.  B1 freezes the enum as "
        f"{list(CHROME_KINDS)} — the four idioms the officials' chrome is made of (ft09 "
        f"letterbox panels, cd82 banner+rules, sk48 inset slab, dc22 divider), and a board "
        f"is FRAMED with whichever of them fits its geometry"
    )


@pytest.mark.parametrize(
    "bad,why",
    [
        ("letterbox", "a bare string, not a list of declarations"),
        ({"kind": "letterbox"}, "a mapping, not a list"),
        ([{"kind": "banner", "where": "row0"}], "a `kind` off the closed enum"),
        ([{"kind": "letterbox"}], "an entry with no `where`"),
        ([{"where": "row0"}], "an entry with no `kind`"),
        (["letterbox:row0"], "an entry that is not a mapping"),
    ],
)
def test_pin1c_malformed_chrome_is_a_schema_kill(bad: object, why: str) -> None:
    """The `tiny_token` precedent: a key written down is HELD to its declaration."""
    report = lint(good_spec(chrome=bad))
    assert not report.passed, (
        f"`game.chrome` = {bad!r} ({why}) linted CLEAN.  B1: 'malformed = schema kill, the "
        f"tiny_token precedent' — a malformed optional field is a kill rather than a silently "
        f"ignored key, because a declaration nobody can read is not a declaration.  "
        f"warns={report.warns!r}"
    )
    assert findings(report, "schema"), (
        f"`game.chrome` = {bad!r} was refused, but under no `schema` rule: "
        f"kills={report.kills!r}.  The contract names the `schema` kill by name (the "
        f"`tiny_token` / `palette.background` precedent), and the rule id is what the writer "
        f"prompt's kill list and the retry reminder key on"
    )


def test_pin1c_an_unknown_chrome_entry_key_is_not_silent() -> None:
    """A key inside a chrome entry that §11 does not know is REPORTED, kill or warn.

    Softer than the shapes above on purpose: `{kind, where}` is B1's "smallest
    honest schema", and whether a fifth key inside an entry is a kill (the
    `game.actions` rule) or a warn (the `game.<field>` rule) is the
    implementer's call.  Silence is the one answer that cannot be right.
    """
    report = lint(good_spec(
        chrome=[{"kind": CHROME_KINDS[0], "where": where_token(), "colour": CHROME_INDEX}]))
    assert not report.passed or chrome_findings(report), (
        "a `game.chrome` entry carrying an unknown key `colour` linted completely clean.  "
        "B1 fixes the entry shape as `{kind: letterbox|panel|divider|bezel, where: <token>}` "
        "— the smallest honest schema — and a key nothing downstream reads is the shape the "
        "linter's own `unknown-field` warn exists for"
    )


def test_pin1c_an_empty_chrome_list_declares_nothing() -> None:
    """`chrome: []` is the tiny_token empty-list case: a kill, not a shrug."""
    report = lint(good_spec(chrome=[]))
    assert not report.passed, (
        "`game.chrome: []` linted clean.  `palette.tiny_token`'s rule, which B1 names as the "
        "precedent: 'an empty list, a repeat, or a role nothing else in §11 knows about "
        "declares nothing, so each is a schema kill rather than a silently ignored field'.  "
        "A game with no authored chrome OMITS the key — absence is the silence"
    )


def test_pin1d_an_absent_chrome_block_is_silence() -> None:
    """The committed good spec declares none and must lint exactly as it always has."""
    report = lint(good_spec())
    assert report.to_json_dict() == STOCK_LINT_REPORT, (
        f"the unconfigured lint of the committed good spec is no longer "
        f"{STOCK_LINT_REPORT!r}: {report.to_json_dict()!r}.  B1's replay line is "
        f"'unconfigured lints byte-identical' — every field B1 adds to §11 is OPTIONAL and "
        f"absence is silence, so a spec that declares none reports what it always reported"
    )


# =============================================================================
# PIN 2 — §11: the optional `knobs.refusal_transient` declaration
# =============================================================================


def test_pin2a_refusal_transient_true_is_accepted() -> None:
    """The declared escape hatch from R-08's persistence promise."""
    report = lint(with_knob(good_spec(), REFUSAL_TRANSIENT, True))
    assert report.passed and not report.warns, (
        f"`knobs.{REFUSAL_TRANSIENT}: true` was refused or warned on: kills={report.kills!r} "
        f"warns={report.warns!r}.  B1 adds it as the OPTIONAL declaration that a refusal "
        f"signal is transient-and-unobservable — the alternative to promising a "
        f"settled-frame-persistent signal"
    )


@pytest.mark.parametrize("bad", ["yes", "true", 1, [], {"transient": True}])
def test_pin2b_a_refusal_transient_that_is_not_a_declaration_is_loud(bad: object) -> None:
    """A key written down is held to one — the `hazardless_override` bar."""
    report = lint(with_knob(good_spec(), REFUSAL_TRANSIENT, bad))
    assert not report.passed, (
        f"`knobs.{REFUSAL_TRANSIENT}: {bad!r}` linted CLEAN.  Before B1 the key was simply "
        f"unread, which is exactly what the contract closes: `{REFUSAL_TRANSIENT}` is a "
        f"boolean DECLARATION that exempts a game from the persistence promise, and a value "
        f"that is not one exempts nothing while looking like it does (the "
        f"`hazardless_override` / `tiny_token` rule: absence is silence, a present key is a "
        f"declaration and is held to one)"
    )


def test_pin2c_an_absent_refusal_transient_is_silence() -> None:
    """Every spec written before B1 is still a valid spec."""
    report = lint(with_knob(good_spec(), REFUSAL_TRANSIENT, _MISSING))
    assert report.to_json_dict() == STOCK_LINT_REPORT, (
        f"dropping `{REFUSAL_TRANSIENT}` changed the unconfigured report to "
        f"{report.to_json_dict()!r}; it must stay {STOCK_LINT_REPORT!r}"
    )


# =============================================================================
# PIN 3 — the `refusal-persistence` fidelity rule (registry, default OFF)
# =============================================================================


def test_pin3a_refusal_persistence_joins_the_fidelity_registry() -> None:
    """One registry, one action enum, one `lint.<rule>_action` spelling."""
    rules = tuple(str(rule) for rule in getattr(s1_spec, "FIDELITY_RULES", ()))
    assert REFUSAL_PERSISTENCE in rules, (
        f"`{REFUSAL_PERSISTENCE}` is not in s1_spec.FIDELITY_RULES ({list(rules)}).  B1: 'a "
        f"FIDELITY-style rule `refusal-persistence` (registry, default OFF, template arms "
        f"warn)' — it JOINS the registry rather than becoming a private mechanism, which is "
        f"the ruling `silent-levels` and `unstated-background` already landed on"
    )
    keys = getattr(s1_spec, "FIDELITY_ACTION_KEYS", {})
    assert REFUSAL_PERSISTENCE in keys, (
        f"`{REFUSAL_PERSISTENCE}` has no `lint.<rule>_action` config key "
        f"(FIDELITY_ACTION_KEYS = {dict(keys)!r}).  A registry rule nobody can arm from "
        f"config is an inert knob — the readiness audit's own finding"
    )
    assert set(keys) == set(rules), (
        f"the registry and its config keys disagree: rules={sorted(rules)} "
        f"keys={sorted(keys)}.  Every rule needs its key and no key may name a rule that "
        f"does not exist"
    )


def test_pin3b_the_rule_is_born_off() -> None:
    """A new rule earns its place on measured data, not on the day it is written."""
    resolved = s1_spec.resolve_rule_actions(None)
    assert resolved.get(REFUSAL_PERSISTENCE) == FIDELITY_DEFAULT, (
        f"the unconfigured action map is {resolved!r}; `{REFUSAL_PERSISTENCE}` must default "
        f"to {FIDELITY_DEFAULT!r}.  Default-off is what keeps every shipped lint report "
        f"byte-identical, and it is the lead correction the whole registry was built under"
    )
    for action in FIDELITY_ACTIONS:
        armed = s1_spec.resolve_rule_actions({REFUSAL_PERSISTENCE: action})
        assert armed.get(REFUSAL_PERSISTENCE) == action, (
            f"arming `{REFUSAL_PERSISTENCE}` to {action!r} resolved to "
            f"{armed.get(REFUSAL_PERSISTENCE)!r} — the rule takes the registry's own "
            f"{list(FIDELITY_ACTIONS)} enum"
        )
    with pytest.raises(ValueError):
        s1_spec.resolve_rule_actions({REFUSAL_PERSISTENCE: "record"})


def test_pin3c_unconfigured_the_promise_shaped_spec_is_untouched() -> None:
    """`refusal: visible` with no transient declaration — silent while unarmed."""
    spec = with_knob(good_spec(), REFUSAL_TRANSIENT, _MISSING)
    spec["game"]["knobs"]["refusal"] = "visible"
    report = lint(spec)
    assert report.to_json_dict() == STOCK_LINT_REPORT, (
        f"the spec B1 describes as PROMISING a settled-frame-persistent signal "
        f"(`refusal: visible`, no `{REFUSAL_TRANSIENT}`) no longer lints clean when the rule "
        f"is unconfigured: {report.to_json_dict()!r}.  Born-off means the report is the one "
        f"this spec always produced until a batch arms the rule by name"
    )


REFUSAL_SHAPES = (
    ("visible", _MISSING),
    ("visible", True),
    ("free", _MISSING),
    ("free", True),
    ("silent-charged", _MISSING),
    ("silent-charged", True),
)


def _armed_report(refusal: str, transient: object, action: str):
    spec = with_knob(good_spec(), REFUSAL_TRANSIENT, transient)
    spec["game"]["knobs"]["refusal"] = refusal
    try:
        return lint(spec, rule_actions={REFUSAL_PERSISTENCE: action})
    except ValueError as exc:
        pytest.fail(
            f"`lint_spec(..., rule_actions={{'{REFUSAL_PERSISTENCE}': {action!r}}})` was "
            f"refused: {exc}.  The action map reaches the rules through this one parameter "
            f"(the registry's own seam — `lint_spec` never reads config), so a rule that is "
            f"not in `FIDELITY_RULES` cannot be armed at all.  See pin 3a"
        )


def test_pin3d_the_rule_can_fire_and_the_declaration_exempts() -> None:
    """AMBIGUITY 2: which shape fires is discovered; what NEVER fires is pinned."""
    fired = {
        (refusal, transient is not _MISSING): bool(
            findings(_armed_report(refusal, transient, "kill"), REFUSAL_PERSISTENCE))
        for refusal, transient in REFUSAL_SHAPES
    }
    assert any(fired.values()), (
        f"armed to `kill`, `{REFUSAL_PERSISTENCE}` fired on none of the six refusal x "
        f"transient shapes: {fired!r}.  A registry rule that can never fire is precisely the "
        f"inert knob the readiness audit went hunting for — B1 ties the rule to R-08's "
        f"promise ('refusal: visible without refusal_transient promises a "
        f"settled-frame-persistent signal'), so SOME shape has to be a finding"
    )
    assert not fired[("visible", True)], (
        f"`refusal: visible` WITH `{REFUSAL_TRANSIENT}: true` still fired "
        f"`{REFUSAL_PERSISTENCE}`.  That declaration IS the contract's escape hatch — R-08: "
        f"'a refusal the player must learn survives into settled frames, OR the spec declares "
        f"it transient' — so a spec that declares it can never be the offender.  Shapes that "
        f"fired: {fired!r}"
    )


def test_pin3e_armed_to_kill_the_rule_is_quoted_to_the_writer() -> None:
    """PROMPT SYNC: a rule that can KILL a session is in the prompt it judges."""
    section = s1_spec.fidelity_section({REFUSAL_PERSISTENCE: "kill"})
    assert section, (
        f"`fidelity_section({{'{REFUSAL_PERSISTENCE}': 'kill'}})` renders nothing.  Every "
        f"fidelity rule armed to kill is quoted to the spec writer being judged by it — one "
        f"sentence, both consumers (`MIX_HAZARDLESS_KILL_SENTENCE` and its four siblings).  "
        f"~80% of this pipeline's reject reasons traced to rules nobody showed the writer"
    )
    flat = norm_text(section)
    assert "refusal" in flat, (
        f"the kill-armed fidelity section never says `refusal`: {section!r}"
    )
    assert s1_spec.fidelity_section({REFUSAL_PERSISTENCE: "warn"}) in (None, ""), (
        "the fidelity section renders for a rule armed only to `warn`.  The gate is `kill` "
        "and not `warn` deliberately: the warn default is a measurement pass whose whole "
        "point is to read what an UNPROMPTED writer does"
    )


# =============================================================================
# PIN 4 — the payload constants (R-03 chrome, R-13 danger, R-08 refusal)
# =============================================================================


def test_pin4a_the_chrome_idioms_ride_with_their_official_cites() -> None:
    """Four idioms, four cites — ft09, cd82, sk48, dc22."""
    name = canon_block(*CHROME_KINDS, *CHROME_CITES, label="chrome idiom")
    text = norm_text(_canon_texts()[name])
    missing = [word for word in (*CHROME_KINDS, *CHROME_CITES) if word not in text]
    assert not missing, f"{name} is missing {missing}"


def test_pin4b_the_chrome_section_says_a_board_is_framed() -> None:
    """The rule, not just the catalogue: authored inert structure marks the edge."""
    name = canon_block("letterbox", "bezel", label="chrome idiom")
    text = norm_text(_canon_texts()[name])
    assert "framed" in text or "world ends" in text, (
        f"`{name}` lists the chrome idioms but never states the rule B1 freezes — 'a board is "
        f"FRAMED — authored inert structure marks where the world ends'.  Without it the "
        f"section is a catalogue of decorations rather than the reason the officials' boards "
        f"read as places"
    )


def test_pin4c_the_danger_index_must_be_painted_on_every_hazard_level() -> None:
    """R-13's first payload rule, with the corpus fact behind it (19 hazard rows)."""
    name = canon_block("danger", "paint", (str(OFFICIAL_HAZARD_ROWS), "nineteen"),
                       label="danger-painted")
    text = norm_text(_canon_texts()[name])
    assert "every level" in text or "each level" in text, (
        f"`{name}` carries the hazard-row count but never says the index must be painted on "
        f"EVERY level that declares the hazard — the rule pump-phase breaks (its hazard is "
        f"never an object) and pump-flow breaks on its fog levels"
    )
    assert "settled" in text, (
        f"`{name}` never says SETTLED frame.  pump-phase's crush flash exists for one frame a "
        f"winning player never sees, so 'painted somewhere' is exactly the claim that passes "
        f"the defect: hazards STAND on the board before they bite"
    )


def test_pin4d_reveal_is_lighter_than_conceal() -> None:
    """R-13's second payload rule — convoy's fog `2` over its revealed rail `3`."""
    name = canon_block("lighter", "reveal", label="reveal/conceal brightness")
    text = norm_text(_canon_texts()[name])
    assert "conceal" in text or "fog" in text, (
        f"`{name}` says something is lighter but never names the concealed state it is "
        f"lighter THAN.  The rule is an ORDERING over a reveal/conceal pair: revealing reads "
        f"as a lamp, not a shadow (convoy paints fog `2` = (153,153,153) over revealed rail "
        f"`3` = (102,102,102) and gets it backwards)"
    )


def test_pin4e_the_never_signal_and_charge_row_quotes_section_6() -> None:
    """R-08's REQUIRED row, with the §6:158 line cite the contract names."""
    name = canon_block("required", REFUSAL_RULE_LINE, "refusal", label="never-signal-and-charge")
    text = norm_text(_canon_texts()[name])
    assert ("never both" in text) or ("silently" in text and "freely" in text), (
        f"`{name}` cites §6:{REFUSAL_RULE_LINE} but never carries its rule — 'charge silently "
        f"or signal freely — never both'.  Two shipped games breach it (pump-phase's flash "
        f"'costs a step and drains pressure anyway'; convoy 'still rolls and still burns a "
        f"drum'), both declaring `refusal: visible`"
    )


def test_pin4f_refusal_persistence_guidance_names_the_transient_declaration() -> None:
    """The other half of R-08: survive into settled frames, or DECLARE transient."""
    name = canon_block("refusal", "settled", "transient", label="refusal-persistence")
    text = norm_text(_canon_texts()[name])
    assert "persist" in text or "survive" in text, (
        f"`{name}` mentions settled frames and transience but never states the obligation: a "
        f"refusal the player must LEARN survives into a settled frame.  conduit's flash is "
        f"structurally unable to (it renders into `frame[-2]` while the sidecar keeps "
        f"`frame[-1]`), which is why the spec has to declare the exception instead"
    )


@pytest.mark.parametrize(
    "anchors,label",
    [
        (CHROME_KINDS, "the chrome idioms (R-03)"),
        (("danger", "paint", (str(OFFICIAL_HAZARD_ROWS), "nineteen")),
         "the danger-painted rule (R-13)"),
        (("required", REFUSAL_RULE_LINE, "refusal"), "the never-signal-and-charge row (R-08)"),
    ],
)
def test_pin4g_the_payload_names_each_new_block(anchors: tuple, label: str) -> None:
    """PROMPT SYNC (AMBIGUITY 5): a REQUIRED row rides into the prompt it judges."""
    name = canon_block(*anchors, label=label)
    assert re.search(rf"\b{re.escape(name)}\b", _payload_source()), (
        f"`gen/visual_canon.{name}` carries {label} and `gen/s2_implement.py` never names it, "
        f"so the block is written and never handed to the implementer it judges.  Every other "
        f"standing rule in that module rides the same two-line wiring — one entry in the "
        f"`from .visual_canon import (...)` list, one entry in the `sections` list "
        f"(`FLOOR_AND_FOOTPRINT`, `WIN_IS_RENDERED`, `TEACHING_BY_SHOWING`).  B1's file list "
        f"does not name s2_implement.py; prompt-sync says it still has to be wired"
    )


# =============================================================================
# PIN 5 — `chrome-extent`: the PAIRED acceptance
# =============================================================================


def test_pin5a_the_knob_exists_and_is_born_recording(chrome_key: str, chrome_reader) -> None:
    assert chrome_reader({}) == DEFAULT_MODE, (
        f"`gate.{chrome_key}` does not default to {DEFAULT_MODE!r} on an empty config "
        f"(it gave {chrome_reader({})!r}).  B1: 'mode off|record|fail default record' — a new "
        f"rejection earns its place on measured data"
    )
    for mode in CHECK_MODES:
        assert chrome_reader({"gate": {chrome_key: mode}}) == mode


@pytest.mark.parametrize("bad", BAD_MODES)
def test_pin5b_a_bad_chrome_mode_is_loud(chrome_key: str, chrome_reader, bad: str) -> None:
    """The `tiers.tier_policy` idiom: fail loud, name the key."""
    with pytest.raises(ValueError, match=chrome_key):
        chrome_reader({"gate": {chrome_key: bad}})


def test_pin5c_below_band_with_no_authored_chrome_fails(build, chrome_key: str) -> None:
    """R-03's own exhibit: an empty board with nothing authored on it."""
    board = sparse_board()
    assert occupied_extent(board) < OFFICIAL_EXTENT_LOW, "the fixture must be below band"
    report = build("bare-sparse", sidecar([board, board, board]), spec_document(),
                   **{chrome_key: "fail"})
    block = check_block(report, CHROME_EXTENT, label="chrome-extent")
    assert verdict(block, label="chrome-extent") is False, (
        f"a board with {occupied_extent(board)} occupied cells of {BOARD_CELLS} — far below "
        f"the officials' {OFFICIAL_EXTENT_LOW}..{OFFICIAL_EXTENT_HIGH} band — and NO `game.chrome` "
        f"declaration passed `chrome-extent`.  That is both legs of R-03's paired acceptance "
        f"failing at once, which is the one case the check exists to reject: 3 of our 7 games "
        f"sit below the band with two authored decor objects between them.  block: "
        f"{dict(block)!r}"
    )


def test_pin5d_below_band_with_authored_chrome_passes(build, chrome_key: str) -> None:
    """Neither leg alone: an empty-but-FRAMED board is not the defect."""
    board = sparse_board(chrome=True)
    assert occupied_extent(board) < OFFICIAL_EXTENT_LOW, "the fixture must stay below band"
    report = build("chromed-sparse", sidecar([board, board, board]),
                   spec_document(chrome=chrome_declaration()), **{chrome_key: "fail"})
    block = check_block(report, CHROME_EXTENT, label="chrome-extent")
    counted = [value for value in numbers_in(find_metric(block, "chrome", "decor")) if value > 0]
    assert counted, (
        f"the card counted no authored chrome for a board whose whole one-cell perimeter is "
        f"painted `{CHROME_INDEX}` and whose spec declares {chrome_declaration()!r}.  "
        f"AMBIGUITY 1: B1 writes `where: <token>` without fixing the token vocabulary, so "
        f"this fixture paints row 0, row 63, col 0 and col 63 and declares chrome over every "
        f"token the §11 linter accepted ({list(_accepted_where_tokens())}).  If the card's "
        f"geometry vocabulary is a different one, say which and this pin resolves.  block: "
        f"{dict(block)!r}"
    )
    assert verdict(block, label="chrome-extent") is not False, (
        f"a below-band board WITH authored chrome was failed by `chrome-extent`.  B1's "
        f"pairing is explicit — 'fail only when occupied_extent is below the officials' band "
        f"AND authored chrome count is 0 — never one leg alone' — because chrome that is not "
        f"load-bearing inflates extent without improving legibility, and the pairing is what "
        f"stops either half being satisfied on its own.  block: {dict(block)!r}"
    )


def test_pin5e_in_band_with_no_authored_chrome_passes(build, chrome_key: str) -> None:
    """The other leg alone: a full board that authored no chrome still passes."""
    board = dense_board()
    extent = occupied_extent(board)
    assert OFFICIAL_EXTENT_LOW <= extent <= OFFICIAL_EXTENT_HIGH, "the fixture must be in band"
    report = build("bare-dense", sidecar([board, board, board]), spec_document(),
                   **{chrome_key: "fail"})
    block = check_block(report, CHROME_EXTENT, label="chrome-extent")
    assert verdict(block, label="chrome-extent") is not False, (
        f"a board with {extent} occupied cells of {BOARD_CELLS} — inside the officials' "
        f"{OFFICIAL_EXTENT_LOW}..{OFFICIAL_EXTENT_HIGH} band — was failed for declaring no "
        f"`game.chrome`.  The pairing forbids exactly this: 'never one leg alone'.  A game "
        f"that fills its board honestly has not committed R-03's defect.  block: "
        f"{dict(block)!r}"
    )


def test_pin5f_the_card_carries_the_authored_chrome_metric(build, chrome_key: str) -> None:
    """`authored_chrome` — a count AND the coverage cells, both on the card."""
    board = sparse_board(chrome=True)
    report = build("chrome-metric", sidecar([board, board, board]),
                   spec_document(chrome=chrome_declaration()), **{chrome_key: DEFAULT_MODE})
    block = check_block(report, CHROME_EXTENT, label="chrome-extent")
    metric = find_metric(block, "authoredchrome", "chrome", "decor")
    assert metric is not _MISSING, (
        f"the chrome-extent block carries no `authored_chrome` metric at all: "
        f"{key_map(block)}.  B1: 'card metric `authored_chrome` (count + coverage cells, "
        f"computed from declared chrome regions painted non-background on level starts)'"
    )
    values = numbers_in(metric)
    assert len(values) >= 2, (
        f"the authored-chrome metric reports {values!r}: B1 asks for TWO numbers, a count and "
        f"the coverage in cells.  A count with no area cannot tell a painted letterbox band "
        f"from a declared one that draws four pixels"
    )
    extent = numbers_in(find_metric(block, "occupiedextent", "extent", "occupied", "occupancy"))
    assert extent, (
        f"the chrome-extent block reports no occupied-extent number ({key_map(block)}).  "
        f"BOTH legs of the paired acceptance have to be readable on the card — the audit's "
        f"own design, and B1 says to state it"
    )
    assert mode_of(block, label="chrome-extent") == DEFAULT_MODE


def test_pin5g_mode_off_removes_the_chrome_block(build, chrome_key: str) -> None:
    """`off` is not 'measure and ignore' — the card reproduces its pre-B1 bytes."""
    board = sparse_board()
    report = build("chrome-off", sidecar([board, board, board]), spec_document(),
                   **{chrome_key: "off"})
    assert find(report, CHROME_EXTENT) is _MISSING, (
        f"`gate.{chrome_key}: off` still wrote a chrome-extent block onto the card.  `off` "
        f"removes the check's fields entirely — that is how a card built today reproduces one "
        f"built before the check existed, byte for byte (`field_index` / `role_footprint` / "
        f"`win_render` all do it).  the card offers {key_map(report, depth=0)}"
    )


# =============================================================================
# PIN 6 — `danger-visible`: the tell is a placed object
# =============================================================================

HAZARD_TERMS = ("move.grid", "hazard.static")


def test_pin6a_the_knob_exists_and_is_born_recording(danger_key: str, danger_reader) -> None:
    assert danger_reader({}) == DEFAULT_MODE, (
        f"`gate.{danger_key}` does not default to {DEFAULT_MODE!r} (it gave "
        f"{danger_reader({})!r}).  B1: 'check `danger-visible` (mode knob, default record)'"
    )
    for mode in CHECK_MODES:
        assert danger_reader({"gate": {danger_key: mode}}) == mode


@pytest.mark.parametrize("bad", BAD_MODES)
def test_pin6b_a_bad_danger_mode_is_loud(danger_key: str, danger_reader, bad: str) -> None:
    with pytest.raises(ValueError, match=danger_key):
        danger_reader({"gate": {danger_key: bad}})


def test_pin6c_a_hazard_level_that_paints_no_danger_index_fails(build, danger_key: str) -> None:
    """pump-phase + pump-flow, synthesised: the tell is absent from settled frames."""
    painted = sparse_board(danger=True)
    unpainted = sparse_board(danger=False)
    report = build("danger-absent", sidecar([painted, unpainted, unpainted]),
                   spec_document(terms=HAZARD_TERMS), **{danger_key: "fail"})
    block = check_block(report, DANGER_VISIBLE, label="danger-visible")
    assert verdict(block, label="danger-visible") is False, (
        f"a game declaring `palette.danger: {DANGER}` and a `hazard.` term painted its danger "
        f"index on level 1 only, and `danger-visible` passed it.  That is pump-flow's fog "
        f"levels (an OPEN valve paints no `8` at all) and pump-phase's hazard (never an "
        f"object on any settled frame) — against all {OFFICIAL_HAZARD_ROWS} official hazard "
        f"rows, which are placed objects that stand on the board before they bite.  block: "
        f"{dict(block)!r}"
    )


def test_pin6d_the_card_records_the_per_level_danger_facts(build, danger_key: str) -> None:
    """`danger_painted_levels` — per level, is the declared danger index present?"""
    painted = sparse_board(danger=True)
    unpainted = sparse_board(danger=False)
    report = build("danger-record", sidecar([painted, unpainted, unpainted]),
                   spec_document(terms=HAZARD_TERMS), **{danger_key: DEFAULT_MODE})
    block = check_block(report, DANGER_VISIBLE, label="danger-visible")
    metric = find_metric(block, "dangerpainted", "paintedlevels", "dangerlevels", "painted")
    assert metric is not _MISSING, (
        f"the danger-visible block carries no `danger_painted_levels` metric: "
        f"{key_map(block)}.  B1 asks for it by name — 'per level: declared danger index "
        f"present?' — because the review needs to see WHICH levels went dark, not just that "
        f"some did"
    )
    assert numbers_in(metric) or strings_in(metric) or isinstance(metric, (list, tuple)), (
        f"the danger_painted_levels metric is {metric!r} — it records nothing per level"
    )
    assert mode_of(block, label="danger-visible") == DEFAULT_MODE, (
        "the card does not record that this run was in `record` mode; the gate runner reads "
        "that field to decide whether a FAIL may reject"
    )


def test_pin6e_a_danger_index_on_every_level_passes(build, danger_key: str) -> None:
    painted = sparse_board(danger=True)
    report = build("danger-painted", sidecar([painted, painted, painted]),
                   spec_document(terms=HAZARD_TERMS), **{danger_key: "fail"})
    block = check_block(report, DANGER_VISIBLE, label="danger-visible")
    assert verdict(block, label="danger-visible") is not False, (
        f"a game that paints its declared danger index on EVERY level-start frame was failed "
        f"by `danger-visible`.  That is the shape the rule asks for — the hazard stands on "
        f"the board before it bites.  block: {dict(block)!r}"
    )


def test_pin6f_a_declared_camouflage_lever_is_exempt(build, danger_key: str) -> None:
    """AMBIGUITY 4: legitimate camouflage is a DECLARED t2/t3 deception lever."""
    painted = sparse_board(danger=True)
    unpainted = sparse_board(danger=False)
    report = build(
        "danger-camouflage", sidecar([painted, unpainted, unpainted]),
        spec_document(terms=HAZARD_TERMS, deceptions=("camouflage",), danger_tell="camouflage"),
        **{danger_key: "fail"})
    block = check_block(report, DANGER_VISIBLE, label="danger-visible")
    assert verdict(block, label="danger-visible") is not False, (
        f"a game whose spec DECLARES the §3 camouflage lever (`knobs.deceptions: "
        f"['camouflage']`, `danger_tell: camouflage`) was failed for hiding its danger index. "
        f"B1: 'the declared-camouflage exemption reads knobs.deceptions for the §3 camouflage "
        f"lever' — R-13's own risk line, because an unexempted check collides head-on with "
        f"R-09's declared-deception machinery.  block: {dict(block)!r}"
    )


def test_pin6g_brightness_is_not_checked_when_nothing_declares_it(build, danger_key: str) -> None:
    """AMBIGUITY 3: honest not-checked beats a claim the spec cannot support."""
    painted = sparse_board(danger=True, field=NON_GREY_BG)
    report = build(
        "brightness-silent", sidecar([painted, painted, painted]),
        spec_document(terms=HAZARD_TERMS, background=NON_GREY_BG, reserved=(12,)),
        **{danger_key: DEFAULT_MODE})
    block = check_block(report, DANGER_VISIBLE, label="danger-visible")
    metric = find_metric(block, "revealbrightness", "brightness", "reveal", "luminance")
    assert metric is not _MISSING, (
        f"the danger-visible block carries no `reveal_brightness_ok` metric at all: "
        f"{key_map(block)}.  B1 names it as a card metric beside `danger_painted_levels`, and "
        f"a metric that is absent when it cannot be computed is indistinguishable from a "
        f"metric nobody wrote"
    )
    said_nothing = (
        metric is None
        or (isinstance(metric, str) and NOT_CHECKED_RE.search(metric))
        or (isinstance(metric, Mapping) and (
            is_not_checked(metric)
            or any(NOT_CHECKED_RE.search(text) for text in strings_in(metric))))
    )
    assert said_nothing, (
        f"`reveal_brightness_ok` = {metric!r} for a spec that declares no fog or conceal "
        f"semantics and no grey-ramp role at all (you {YOU}, goal {GOAL}, danger {DANGER}, "
        f"background {NON_GREY_BG} — none of them in the 0-5 ramp).  B1's own instruction: "
        f"'compute the metric from the two grey-ramp indices' roles ONLY when unambiguous and "
        f"record not-checked otherwise, honestly'.  A bare `true` here is a pass nobody "
        f"measured"
    )


def test_pin6h_the_brightness_convention_is_the_canon_ramp() -> None:
    """Whatever computes brightness must agree with the palette: 2 is lighter than 3."""
    palette = getattr(s3_visual, "ARC_PALETTE_HEX", ())
    assert len(palette) > GREY_DARK, "gen.s3_visual lost its pinned render palette"
    light = int(palette[GREY_LIGHT][1:3], 16)
    dark = int(palette[GREY_DARK][1:3], 16)
    assert light > dark, (
        f"the pinned canon palette no longer makes index {GREY_LIGHT} lighter than index "
        f"{GREY_DARK} ({palette[GREY_LIGHT]} vs {palette[GREY_DARK]}).  convoy's exhibit is "
        f"exactly this pair — fog `2` (153,153,153) over revealed rail `3` (102,102,102) — so "
        f"the ordering the rule depends on is this ramp"
    )
    for module in (s3_visual, visual_canon):
        for name, value in vars(module).items():
            if not callable(value) or "bright" not in name.lower():
                continue
            try:
                lit, drk = value(GREY_LIGHT), value(GREY_DARK)
            except Exception:  # noqa: BLE001, S112 — not an index->brightness reader
                continue
            if isinstance(lit, (int, float)) and isinstance(drk, (int, float)):
                assert lit > drk, (
                    f"{module.__name__}.{name} ranks palette index {GREY_DARK} at least as "
                    f"light as index {GREY_LIGHT} ({drk} vs {lit}) — backwards against the "
                    f"canon ramp, which is convoy's defect reproduced inside the check meant "
                    f"to catch it"
                )


def test_pin6i_mode_off_removes_the_danger_block(build, danger_key: str) -> None:
    painted = sparse_board(danger=True)
    unpainted = sparse_board(danger=False)
    report = build("danger-off", sidecar([painted, unpainted, unpainted]),
                   spec_document(terms=HAZARD_TERMS), **{danger_key: "off"})
    assert find(report, DANGER_VISIBLE) is _MISSING, (
        f"`gate.{danger_key}: off` still wrote a danger-visible block onto the card.  `off` "
        f"removes the check's fields entirely — the pre-B1 card, byte for byte.  the card "
        f"offers {key_map(report, depth=0)}"
    )


# =============================================================================
# PIN 7 — the off-mode byte pins
# =============================================================================


def test_pin7a_every_check_knob_can_be_turned_off(off_gate: dict) -> None:
    """The enumeration itself: a mode knob that cannot be silenced is a knob that

    changes every card ever built.  `l1_color_floor` is the one documented
    exception (its enum is `record|fail`) and it is named here rather than
    assumed.
    """
    stuck = sorted(
        key for key, value in off_gate.items()
        if value not in ("off", []) and key != "l1_color_floor"
    )
    assert not stuck, (
        f"these gate knobs refused `off` and had to be left recording: {stuck}.  Every check "
        f"knob in `gen/s3_visual.py` carries the three-mode enum precisely so a card can "
        f"reproduce its pre-check bytes; `l1_color_floor` is the single grandfathered "
        f"exception.  resolved map: {off_gate!r}"
    )


def test_pin7b_the_all_off_card_json_is_byte_identical(off_gate: dict, tmp_path: Path) -> None:
    """Shipped cards are byte-identical with the new modes off."""
    spec_dir = byte_case(tmp_path / "byte-json")
    s3_visual.build_visual_card(spec_dir, {"gate": dict(off_gate)})
    written = (spec_dir / CARD_JSON).read_bytes()
    report = json.loads(written)
    assert tuple(sorted(report)) == BYTE_PIN_TOP_KEYS, (
        f"the all-off card's top-level keys are {sorted(report)}, not "
        f"{list(BYTE_PIN_TOP_KEYS)}.  With every check off the card carries exactly the keys "
        f"it carried before those checks were written — that is what `off` MEANS in this "
        f"module, and it is the one regression contract W1-A1 froze"
    )
    assert tuple(sorted(report["per_record"][0])) == BYTE_PIN_PER_RECORD_KEYS, (
        f"a per-record row now carries {sorted(report['per_record'][0])}.  B1's new metrics "
        f"(`authored_chrome`, `danger_painted_levels`, `reveal_brightness_ok`) ride under "
        f"their own mode gate, exactly as `index0_share` and `role_component_min` do"
    )
    assert tuple(sorted(report["official_bands"])) == BYTE_PIN_OFFICIAL_BANDS_KEYS, (
        f"`official_bands` now carries {sorted(report['official_bands'])}.  "
        f"`_official_bands` dumps the whole of `OFFICIAL_VISUAL_CONSTANTS` onto EVERY card, "
        f"so a new corpus number (the officials' occupied-extent band, the hazard-row count) "
        f"must live in its own constant the way `OFFICIAL_WIN_RENDER` does — the reason that "
        f"one is not a key of that mapping is written above it in gen/visual_canon.py"
    )
    digest = hashlib.sha256(written).hexdigest()
    assert digest == BYTE_PIN_JSON_SHA256, (
        f"the all-off visual card changed: sha256 {digest} ({len(written)} bytes) against the "
        f"frozen {BYTE_PIN_JSON_SHA256} ({BYTE_PIN_JSON_BYTES} bytes).  B1's replay line is "
        f"'shipped cards byte-identical with new modes off' — with every knob in GATE_KEYS at "
        f"its quietest value ({off_gate!r}) this card measures exactly what it measured "
        f"before the visual lane landed"
    )


def test_pin7c_the_all_off_card_markdown_is_byte_identical(off_gate: dict,
                                                           tmp_path: Path) -> None:
    """The human card too: a new heading with every check off is a changed card."""
    spec_dir = byte_case(tmp_path / "byte-md")
    s3_visual.build_visual_card(spec_dir, {"gate": dict(off_gate)})
    written = (spec_dir / CARD_MD).read_bytes()
    digest = hashlib.sha256(written).hexdigest()
    assert digest == BYTE_PIN_MD_SHA256, (
        f"the all-off visual report markdown changed: sha256 {digest} against the frozen "
        f"{BYTE_PIN_MD_SHA256}.  `render_markdown` renders a section per ARMED check "
        f"(`CARD_CHECKS` + `_reject_block`), so with every new mode off the file is the one "
        f"it rendered before B1 — including the 'exactly one line in this file can ever "
        f"reject' sentence"
    )


# =============================================================================
# PIN 8 — the template arms the lane, and every reader accepts it
# =============================================================================


def _template_copy(tmp_path: Path) -> Path:
    """The template, copied into tmp_path — no reader is handed the real file."""
    if not TEMPLATE_PATH.is_file():
        pytest.fail(f"config/template.yaml missing: {TEMPLATE_PATH}")
    dest = tmp_path / "template.yaml"
    shutil.copyfile(TEMPLATE_PATH, dest)
    return dest


@pytest.fixture
def template_cfg(tmp_path: Path) -> dict:
    return load_config(_template_copy(tmp_path))


def test_pin8a_the_template_arms_both_new_checks(template_cfg: dict, chrome_key: str,
                                                 danger_key: str) -> None:
    gate = template_cfg.get("gate")
    assert isinstance(gate, Mapping), f"config/template.yaml has no `gate:` block: {gate!r}"
    for key in (chrome_key, danger_key):
        assert key in gate, (
            f"config/template.yaml's `gate:` block never mentions `{key}`: "
            f"{sorted(gate)}.  B1 arms the visual lane from this file — the replay line "
            f"names which games each check flags — and a check nobody arms is a check nobody "
            f"reads"
        )
        assert gate[key] in CHECK_MODES, (
            f"`gate.{key}: {gate[key]!r}` is not one of {list(CHECK_MODES)}"
        )
    unknown = sorted(set(gate) - set(_gate_keys()))
    assert not unknown, (
        f"config/template.yaml's gate block names keys `gen/s3_visual.GATE_KEYS` does not "
        f"carry: {unknown}.  `_gate_block` refuses them at load, so the template would not "
        f"load at all"
    )


def test_pin8b_the_template_arms_refusal_persistence_to_warn(template_cfg: dict) -> None:
    """'template arms warn' — B1's own words, the measurement pass."""
    keys = getattr(s1_spec, "FIDELITY_ACTION_KEYS", {})
    action_key = keys.get(REFUSAL_PERSISTENCE)
    assert action_key, (
        f"`{REFUSAL_PERSISTENCE}` has no `lint.<rule>_action` key to arm (see pin 3a)"
    )
    lint_block = template_cfg.get("lint")
    assert isinstance(lint_block, Mapping), f"no `lint:` block in the template: {lint_block!r}"
    assert lint_block.get(action_key) == TEMPLATE_FIDELITY_ACTION, (
        f"config/template.yaml has `lint.{action_key} = "
        f"{lint_block.get(action_key)!r}`; B1 says the template arms this rule at "
        f"{TEMPLATE_FIDELITY_ACTION!r}.  The code default stays `off` (pin 3b) — the template "
        f"is where the measurement pass is switched on, exactly as its four siblings are"
    )
    assert s1_spec.resolve_rule_actions(
        {rule: lint_block[key] for rule, key in keys.items() if key in lint_block}
    )[REFUSAL_PERSISTENCE] == TEMPLATE_FIDELITY_ACTION


def test_pin8c_the_new_mode_readers_accept_the_shipped_template(
    template_cfg: dict, chrome_reader, danger_reader, chrome_key: str, danger_key: str
) -> None:
    """The `test_docs_template` pin 1 discipline: every reader is CALLED on it."""
    for label, reader in ((chrome_key, chrome_reader), (danger_key, danger_reader)):
        try:
            mode = reader(template_cfg)
        except Exception as exc:  # noqa: BLE001 — the pin IS "nothing raises"
            pytest.fail(f"the {label} mode reader rejected config/template.yaml: {exc}")
        assert mode in CHECK_MODES, f"{label} read {mode!r} off the template"


def test_pin8d_the_card_builds_under_the_shipped_template(template_cfg: dict,
                                                          tmp_path: Path) -> None:
    """End to end on the real config: the lane runs on the batch that arms it."""
    spec_dir = stage_case(
        tmp_path / "template-run",
        sidecar([sparse_board(chrome=True)] * 3),
        spec_document(chrome=chrome_declaration(), terms=HAZARD_TERMS))
    report = s3_visual.build_visual_card(spec_dir, template_cfg)
    for check, label in ((CHROME_EXTENT, "chrome-extent"), (DANGER_VISIBLE, "danger-visible")):
        block = check_block(report, check, label=label)
        assert mode_of(block, label=label) in CHECK_MODES
