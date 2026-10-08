"""Blind pins for contract W1-A1 — R-01 painted floor, R-02 multi-tile footprint.

Run: .venv/bin/python -m pytest gen/tests/test_w1_floorfootprint.py -v

Written from ``scratchpad/w1-r01r02-contract.md`` ALONE, by a separate agent.
No in-progress diff of ``gen/visual_canon.py``, ``gen/s2_implement.py``,
``gen/s3_visual.py`` or ``config/template.yaml`` was read while this file was
written; every statement below about the PRE-change pipeline came out of
``git show HEAD:<path>``, which is why the frozen surfaces this file retypes
(``GATE_KEYS``'s two pre-existing entries, the card's five top-level json keys,
the b003r2 card digests) are HEAD's and not the implementer's.  These tests are
EXPECTED TO FAIL against HEAD and to pass against the finished change.

WHAT THE CHANGE IS FOR.  Four of the seven shipped games paint the board in
white index 0 — 76% to 98% of the level-1 frame — so no generated board has a
painted floor and none can use the ecosystem's white-selection idiom, which
affordance §9:252 makes REQUIRED ("reserve `0` for selection").  And in 4 of 7,
the state the player must read is drawn as lone pixels and hairlines.  R-01
puts the painted-floor rule and the 0-reservation into the S2 payload and
measures them on the card; R-02 promotes the already-written multi-tile prose
(``VISUAL_CRAFT``:119-121) to a REQUIRED row and measures per-role connected
components.

BLIND NAME RESOLUTION.  The contract freezes the two checks' NAMES
(``field-index``, ``role-footprint``), their modes, their defaults and their
semantics — it does not freeze the python identifiers.  Nothing here guesses:
the knob keys are read out of ``s3_visual.GATE_KEYS`` (the closed key set a new
knob MUST join, or ``config/template.yaml`` would not load), the mode readers
are found by matching those names, and every card lookup normalises keys
(``field-index``/``field_index``/``fieldIndex`` all resolve).  A name that
cannot be resolved fails with the full list of what the module does offer, so
the lead can alias in one line instead of guessing what the pin wanted.

CONTRACT AMBIGUITIES, each called out again at its pin:

* **"mode off ⇒ report byte-identical to pre-existing card shape (no new gate
  verdict)"** collides with the house convention the same contract states
  ("card metrics are pure functions + record fields; gate checks are
  knob-gated").  Metrics that are always on cannot leave the json byte-
  identical.  Resolved toward the contract's own parenthetical: mode off is
  pinned to add no top-level VERDICT block and no per-record pass/fail field,
  and the two shipped b003r2 cards are pinned byte-for-byte against digests
  measured from HEAD.  If the implementer kept the new per-record metrics
  unconditional, exactly the two digest pins fail and this is the sentence to
  reopen.
* **"level-start record"** is not defined.  Every synthetic sidecar here
  carries the offending (or clean) grid on the ``reset`` record AND on a
  ``levels_completed: 1`` step record, so any reading of the phrase that
  includes level 1's own frame reaches the same verdict.
* **Connectivity** (4- vs 8-connected) is unstated for ``role_component_min``.
  Every synthetic role shape is either a solid rectangle or a pixel isolated by
  a full ring of background, so both readings give the same number.
* **The declared-exception surface** for a "tiny token" is explicitly left to
  the implementer ("reading an existing spec annotation if one fits, else a
  config exemption list").  The pin therefore DISCOVERS it: every extra
  ``GATE_KEYS`` entry plus a list of conventional names is tried, at gate level
  and at config top level, and the failure message prints every shape tried.
  Spec-side surfaces are NOT probed (the contract forbids s1_spec edits and
  asks for a report instead).
* **Fail mode does not raise.**  ``l1_floor_mode`` is the pattern the contract
  names to match, and it records ``passed: False`` and leaves the raising to
  nobody — the orchestrator reads the flag.  These pins expect the same, and
  note that ``gen/orchestrator.py`` is outside the implementer's edit scope, so
  the fail arm can only ever be a recorded flag in this wave.

HYGIENE: tmp_path only.  ``out/corpus`` is read and copied, never written into;
no network, no driver, no engine import, no API call.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
import yaml

from gen.config import REPO_ROOT, load_config
from gen.tests.test_docs_template import _readers, _template_copy

# --- locations ----------------------------------------------------------------

ROOT = Path(REPO_ROOT)
FIXTURE_SPEC = Path(__file__).resolve().parent / "fixtures/specs/good-spec.yaml"
PAYLOAD_CONFIG = "config/b001-pilot.yaml"   # test_b6_payload's own payload config
S2_SOURCE = ROOT / "gen" / "s2_implement.py"
TEMPLATE_PATH = ROOT / "config" / "template.yaml"

SPEC_NAME = "spec.yaml"
FRAMES_NAME = "worker.frames.json"
GATE_DIRNAME = "worker.gate"
REPORT_JSON = "visual-report.json"
REPORT_MD = "visual-report.md"
CONTACT_SHEET = "visual-contact-sheet.png"
REPORT_NAMES = (REPORT_JSON, REPORT_MD, CONTACT_SHEET)

# --- HEAD's frozen surface (git show HEAD:..., never the working file) --------

# `gen/s3_visual.GATE_KEYS` at HEAD.  A new knob joins this tuple or the closed
# key check refuses the config that arms it, which is why it is the one honest
# place to read the new knob names out of.
HEAD_GATE_KEYS = ("visual_card", "l1_color_floor")

# The five top-level keys `build_visual_card` writes into visual-report.json at
# HEAD.  "No new gate verdict" in mode off is pinned against exactly this set.
HEAD_CARD_KEYS = frozenset({"game_id", "l1_color_floor", "official_bands", "per_record", "source"})

# Every module-level string constant `gen/visual_canon.py` carries at HEAD.
# The new payload section is whatever string constant is NOT in this set.
HEAD_VISUAL_CANON_STRINGS = frozenset({
    "VISUAL_CRAFT", "TEACHING_BY_SHOWING", "GRAMMAR_HEADER", "_NUMBERS_CARD",
    "_GAMES_CSV", "_LEVELS_CSV", "_SCHEMA_MD", "_DANGER_KNOB",
})
CONSTANT_NAME_RE = re.compile(r"^_?[A-Z][A-Z0-9_]*$")

# The two b003r2 cards the contract names, and their HEAD bytes.  Measured on a
# clean tree at HEAD with gate `{visual_card: record, l1_color_floor: record}`
# (the card reads nothing else out of cfg), the two sidecars copied into a temp
# dir.  These are the "existing determinism pin" the contract asks mode off to
# hold.
B003R2_ROOT = ROOT / "out" / "corpus" / "b003r2-simplicity"
B003R2_DIGESTS = {
    "conduit-watch": {
        REPORT_JSON: "ce6daa0007c524559ce3c9f6132c5c98bf2f83db38beae10bce04a390cc7333a",
        REPORT_MD: "386ca9df1d3ae671a3ad26a5ea6cff79cc49d53f1f857c8eaa8d72fbea45c4db",
    },
    "mosaic-marble-bounce-to-match": {
        REPORT_JSON: "f9abaa4867922d29ec73064489a8a1e47190737d446f8f239637bf1a849e163f",
        REPORT_MD: "f684dd3889c8f9cc76a1311533efbc40379a1c2fff23fc6174aff4e4769221d2",
    },
}

# --- the contract's frozen surface -------------------------------------------

FIELD_INDEX = "fieldindex"          # the check named `field-index`
ROLE_FOOTPRINT = "rolefootprint"    # the check named `role-footprint`
CHECK_MODES = ("off", "record", "fail")
DEFAULT_MODE = "record"
BAD_MODES = ("on", "true", "Record", "record ", "warn", "kill", "")

# R-02's conservative floor when `render.cell_px` is undeclared.
CONSERVATIVE_FLOOR_PX = 4

# The synthetic boards.  64x64 because every frozen card metric assumes the
# ARC camera, and the shipped sidecars are all 64x64.
GRID_SIDE = 64
CELLS = GRID_SIDE * GRID_SIDE
WHITE = 0
BG = 5          # affordance §9: "`5` black — background/outline default"
YOU = 9
GOAL = 14
DANGER = 8
UNPAINTED = 12  # an index declared by a spec and never drawn on the board

_MISSING = object()


# --- normalised lookup (shape unpinned, meaning pinned) -----------------------


def norm_key(name: object) -> str:
    """`field-index`, `field_index` and `fieldIndex` are one name."""
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def norm_text(text: str) -> str:
    """Backtick- and wrap-insensitive text, `test_b6_payload._norm`'s own rule."""
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


def key_map(container: object) -> list[str]:
    """Every key a failure message should print, two levels down."""
    if not isinstance(container, Mapping):
        return []
    keys = [str(key) for key in container]
    for value in container.values():
        if isinstance(value, Mapping):
            keys.extend(f"{key}" for key in value)
    return sorted(set(keys))


def record_cards(report: Mapping) -> list[Mapping]:
    """The card's per-record list, however it is named."""
    for name in ("perrecord", "records", "frames"):
        found = find(report, name)
        if isinstance(found, Sequence) and not isinstance(found, (str, bytes)):
            entries = list(found)
            if entries and all(isinstance(entry, Mapping) for entry in entries):
                return entries
    pytest.fail(
        f"the visual card carries no per-record block (looked for per_record / records "
        f"/ frames); the card offers {key_map(report)}"
    )


def check_block(report: Mapping, check: str, *, label: str) -> Mapping:
    """The card-level block for one of the two new checks."""
    found = find(report, check)
    if found is _MISSING or not isinstance(found, Mapping):
        pytest.fail(
            f"the visual card carries no {label!r} block (a mapping keyed on some "
            f"spelling of {label!r}); the card offers {key_map(report)}.  The contract "
            f"freezes {label!r} as a card-level check beside `l1_color_floor`, which is "
            f"the shape it names as the pattern to match"
        )
    return found


PASS_KEYS = ("passed", "pass", "ok", "clean")
FAIL_WORDS = {"fail", "failed", "failing", "violation", "violations", "reject", "rejected"}
PASS_WORDS = {"pass", "passed", "ok", "clean", "none"}


def verdict(block: Mapping, *, label: str) -> bool:
    """`True` when the check passed.  `l1_color_floor.passed` is the precedent."""
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
        f"{label}: the check block carries no pass/fail face — it offers "
        f"{key_map(block)}.  `l1_color_floor` reports `passed: bool`, and a check with "
        f"no verdict is a measurement the gate can never read"
    )


def mode_of(block: Mapping, *, label: str) -> str:
    found = find(block, "mode", depth=0)
    if not isinstance(found, str):
        pytest.fail(
            f"{label}: the check block carries no `mode` string ({key_map(block)}).  "
            f"`l1_color_floor` records the mode it ran in so a reader can tell a "
            f"recorded failure from a rejecting one"
        )
    return found


def role_mins(record: Mapping, report: Mapping) -> Mapping:
    """`role_component_min` for one record, as {role: value}, however it is nested."""
    found = find(record, "rolecomponentmin")
    if found is _MISSING:
        found = find(report, "rolecomponentmin")
    if isinstance(found, Mapping):
        return {str(key): value for key, value in found.items()}
    if found is not _MISSING:
        pytest.fail(
            f"role_component_min came back as {found!r}; the contract freezes it as a "
            f"per-ROLE figure (palette.you / palette.goal / palette.danger)"
        )
    per_role = {}
    for role in ("you", "goal", "danger"):
        value = find(record, f"rolecomponentmin{role}", depth=0)
        if value is not _MISSING:
            per_role[role] = value
    if per_role:
        return per_role
    pytest.fail(
        f"the card carries no `role_component_min` for any role — the record offers "
        f"{key_map(record)}.  It is R-02's whole measurement: the smallest connected "
        f"blob a declared role is drawn as"
    )


NOT_CHECKED_RE = re.compile(r"not[-_ ]?checked|n/?a|skipped|undeclared", re.IGNORECASE)


def is_not_checked(value: object) -> bool:
    """An undeclared role's entry: absent, null, or some `not-checked` word."""
    if value is _MISSING or value is None:
        return True
    if isinstance(value, str):
        return bool(NOT_CHECKED_RE.search(value))
    if isinstance(value, Mapping):
        return any(is_not_checked(entry) for entry in value.values())
    return False


# --- the synthetic corpus (tmp_path only) -------------------------------------


def blank(value: int) -> list[list[int]]:
    return [[value] * GRID_SIDE for _ in range(GRID_SIDE)]


def paint(grid: list[list[int]], top: int, left: int, height: int, width: int, value: int) -> None:
    for y in range(top, top + height):
        for x in range(left, left + width):
            grid[y][x] = value


def count(grid: Sequence[Sequence[int]], value: int) -> int:
    return sum(row.count(value) for row in grid)


def white_field_board() -> list[list[int]]:
    """A board whose FIELD is white 0 — the defect 4 of 7 shipped games carry."""
    grid = blank(WHITE)
    paint(grid, 4, 4, 4, 4, YOU)
    paint(grid, 12, 12, 4, 4, GOAL)
    paint(grid, 20, 20, 4, 4, DANGER)
    paint(grid, 28, 28, 4, 4, BG)
    return grid


def painted_field_board() -> list[list[int]]:
    """A board painted in BG, with 0 used only as a selection mark.

    Hand-countable on purpose (pin 3): 512 white cells of 4096 is `index0_share`
    0.125 EXACTLY, so no rounding convention can be mistaken for a wrong scan.
    """
    grid = blank(BG)
    paint(grid, 40, 0, 8, GRID_SIDE, WHITE)     # 8 rows x 64 = 512 white cells
    paint(grid, 4, 4, 4, 4, YOU)
    paint(grid, 12, 12, 4, 4, GOAL)
    paint(grid, 20, 20, 4, 4, DANGER)
    return grid


def role_board(you_shape: str) -> list[list[int]]:
    """A painted board whose `you` is drawn at one of four footprints.

    Every shape is isolated by a full ring of background, so 4-connected and
    8-connected component sizes agree and the connectivity ambiguity cannot
    change the answer.
    """
    grid = blank(BG)
    paint(grid, 50, 50, 2, 2, WHITE)        # a selection mark, and the 4th colour
    paint(grid, 10, 10, 4, 4, GOAL)         # goal always clears any floor
    if you_shape == "pixel":                # 1 px
        grid[30][30] = YOU
    elif you_shape == "triple":             # 3 px, an L
        grid[30][30] = YOU
        grid[30][31] = YOU
        grid[31][30] = YOU
    elif you_shape == "quad":               # 4 px, a 2x2 block
        paint(grid, 30, 30, 2, 2, YOU)
    elif you_shape == "cell":               # 16 px, one 4x4 logical cell
        paint(grid, 30, 30, 4, 4, YOU)
    else:  # pragma: no cover - a typo in this file, not in the implementation
        raise AssertionError(f"unknown you_shape {you_shape!r}")
    return grid


def spec_document(
    *,
    you: int | None = YOU,
    goal: int | None = GOAL,
    danger: int | None = None,
    background: int | object = BG,
    cell_px: int | None = None,
) -> dict:
    """A §11-shaped spec carrying only what the card reads: palette, hud, render."""
    palette: dict[str, object] = {"reserved": [1, 2]}
    if you is not None:
        palette["you"] = you
    if goal is not None:
        palette["goal"] = goal
    palette["danger"] = danger
    if background is not _MISSING:
        palette["background"] = background
    game: dict[str, object] = {
        "slug": "w1-synthetic",
        "title": "W1 synthetic",
        "palette": palette,
        "hud": {"reserved": "row63", "meter": {"placement": "row63-left",
                                               "direction": "shrink-right"}},
    }
    if cell_px is not None:
        game["render"] = {"cell_px": cell_px}
    return {"game": game}


def frames_document(grid: Sequence[Sequence[int]]) -> dict:
    """The S2b sidecar shape, with the board on reset AND on a level-start step.

    AMBIGUITY: the contract says "any level-start record" without defining the
    set.  Carrying the same board on `reset` (level 1's own frame, which the
    audit measured) and on a `levels_completed: 1` step makes every reading of
    the phrase agree.
    """
    rows = [list(row) for row in grid]
    return {
        "game_id": "w1-synthetic",
        "source": "synthetic",
        "records": [
            {"label": "reset", "seq": 0, "levels_completed": 0,
             "state": "NOT_FINISHED", "grid": rows},
            {"label": "step-11:ACTION5", "seq": 1, "levels_completed": 1,
             "state": "NOT_FINISHED", "grid": [list(row) for row in rows]},
            {"label": "final", "seq": 2, "levels_completed": 1,
             "state": "WIN", "grid": [list(row) for row in rows]},
        ],
    }


def stage_case(directory: Path, grid: Sequence[Sequence[int]], spec: Mapping) -> Path:
    """One synthetic slot — spec + frames sidecar — inside tmp_path."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SPEC_NAME).write_text(
        yaml.safe_dump(dict(spec), sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    (directory / FRAMES_NAME).write_text(
        json.dumps(frames_document(grid), indent=2) + "\n", encoding="utf-8"
    )
    return directory


# --- fixtures: the module, the knob names, the readers ------------------------


@pytest.fixture(scope="session")
def s3_visual():
    try:
        import gen.s3_visual as module
    except ImportError as exc:  # pragma: no cover - only before the module exists
        pytest.fail(f"gen.s3_visual does not import ({exc})")
    return module


@pytest.fixture(scope="session")
def visual_canon():
    import gen.visual_canon as module

    return module


@pytest.fixture(scope="session")
def build_card(s3_visual):
    builder = getattr(s3_visual, "build_visual_card", None)
    if builder is None:  # pragma: no cover - frozen by contract V-C
        pytest.fail("gen.s3_visual exposes no build_visual_card(spec_dir, cfg)")
    return builder


def _gate_keys(s3_visual) -> tuple[str, ...]:
    keys = getattr(s3_visual, "GATE_KEYS", None)
    if not isinstance(keys, (list, tuple)):
        pytest.fail(
            "gen.s3_visual exposes no GATE_KEYS tuple — it is the closed key set every "
            "gate knob has to join, and the only honest place to read the two new knob "
            "names out of"
        )
    return tuple(str(key) for key in keys)


def _resolve_knob(s3_visual, check: str, label: str) -> str:
    for key in _gate_keys(s3_visual):
        if norm_key(key) == check:
            return key
    pytest.fail(
        f"no gate knob in gen.s3_visual.GATE_KEYS spells {label!r}: the closed key set "
        f"is {list(_gate_keys(s3_visual))}.  The contract arms this check from "
        f"config/template.yaml, and an unarmed knob key is refused by the block's own "
        f"unknown-key check, so the knob MUST be in GATE_KEYS"
    )


@pytest.fixture(scope="session")
def field_key(s3_visual) -> str:
    return _resolve_knob(s3_visual, FIELD_INDEX, "field-index")


@pytest.fixture(scope="session")
def role_key(s3_visual) -> str:
    return _resolve_knob(s3_visual, ROLE_FOOTPRINT, "role-footprint")


def _resolve_reader(s3_visual, knob: str, check: str, label: str):
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
    for name, value in vars(s3_visual).items():
        if not callable(value) or name.startswith("_"):
            continue
        try:
            if value({"gate": {knob: "fail"}}) == "fail" and value({}) == DEFAULT_MODE:
                return value
        except Exception:  # noqa: BLE001, S112 — as above
            continue
    pytest.fail(
        f"gen.s3_visual exposes no mode reader for {label!r} (gate key {knob!r}).  The "
        f"contract freezes `visual_card_mode` / `l1_floor_mode` as the pattern: a "
        f"module-level `cfg -> 'off'|'record'|'fail'` reader.  Callables whose name "
        f"mentions the check: {[name for name, _ in named] or 'none'}"
    )


@pytest.fixture(scope="session")
def field_mode(s3_visual, field_key: str):
    return _resolve_reader(s3_visual, field_key, FIELD_INDEX, "field-index")


@pytest.fixture(scope="session")
def role_mode(s3_visual, role_key: str):
    return _resolve_reader(s3_visual, role_key, ROLE_FOOTPRINT, "role-footprint")


@pytest.fixture(scope="session")
def gate_cfg(field_key: str, role_key: str):
    """`{gate: {...}}` with both pre-existing knobs held where HEAD has them."""

    def make(*, field: str = DEFAULT_MODE, role: str = DEFAULT_MODE) -> dict:
        # Lead edit at the W1-A2 close: the two phase-2 checks default RECORD
        # (adjudicated), so every card THIS file builds forces them off — its
        # byte pins compare against cards from before those checks existed
        # (the same compare-like-with-like rule as m1_metrics' off-dict).
        return {"gate": {"visual_card": "record", "l1_color_floor": "record",
                         "win_render": "off", "declared_vs_painted": "off",
                         # Lead edit at the wave-3 B1 close: same rule, two
                         # more record-default checks forced off.
                         "chrome_extent": "off", "danger_visible": "off",
                         # Contract T-1 (licensed implementer edit, reported
                         # in the handback): same rule, one more.
                         "density": "off",
                         field_key: field, role_key: role}}

    return make


@pytest.fixture(scope="session")
def payload_text(tmp_path_factory: pytest.TempPathFactory) -> str:
    """The real S2 payload for the hand-written §11 fixture spec.

    Built once: the canon parsers read a dozen files out of the READ-ONLY
    duckWM tree, and every payload pin reads the same string.
    """
    from gen.s2_implement import build_payload

    cfg = load_config(PAYLOAD_CONFIG)
    spec_dir = tmp_path_factory.mktemp("w1payload") / "spec"
    spec_dir.mkdir()
    shutil.copy2(FIXTURE_SPEC, spec_dir / SPEC_NAME)
    (spec_dir / "spec.md").write_text(
        "# Fogbound Switchyard\n\nThe prose face of the fixture spec.\n", encoding="utf-8"
    )
    payload, _report = build_payload(spec_dir, cfg)
    return payload


@pytest.fixture(scope="session")
def new_sections(visual_canon) -> dict[str, str]:
    """Every module-level string constant `visual_canon` grew for this contract."""
    return {
        name: value
        for name, value in vars(visual_canon).items()
        if isinstance(value, str)
        and CONSTANT_NAME_RE.match(name)
        and name not in HEAD_VISUAL_CANON_STRINGS
    }


# =============================================================================
# PIN 1 — the payload carries both rules, as named constants
# =============================================================================

# Each entry: (what the contract asks for, a predicate over the NORMALISED text).
# Stems and alternations on purpose — the pin is that the RULE is stated, not
# that the implementer used one particular sentence.
SECTION_REQUIREMENTS: tuple[tuple[str, object], ...] = (
    (
        "R-01(1): the declared background index is named as `game.palette.background`",
        lambda text: "palette.background" in text,
    ),
    (
        "R-01(1): the playfield is PAINTED in it (a painted floor, not an empty field)",
        lambda text: "paint" in text,
    ),
    (
        "R-01(1): that index must not be 0 unless the spec declares it deliberately",
        lambda text: re.search(r"(not|never|avoid)[^.]{0,60}\b0\b", text) is not None,
    ),
    (
        "R-01(2): index 0 is RESERVED for selection/highlight",
        lambda text: "reserv" in text and "selection" in text,
    ),
    (
        "R-01: the §9 anchor the rule is quoted from",
        lambda text: re.search(r"§\s*9\b|section 9\b|:2(39|40|52)\b", text) is not None,
    ),
    (
        "R-01: the canon file the §9 rule lives in",
        lambda text: "affordance-language" in text,
    ),
    (
        "R-02: entities are connected MULTI-TILE shapes",
        lambda text: "multi-tile" in text or "multi tile" in text,
    ),
    (
        "R-02: ... not lone 1x1 squares",
        lambda text: "1x1" in text,
    ),
    (
        "R-02: with the declared-exception escape hatch",
        lambda text: "declar" in text and ("unless" in text or "exception" in text),
    ),
    (
        "R-01/R-02 are stated as REQUIRED rows, not as suggestions",
        lambda text: "required" in text,
    ),
)


def test_pin1_visual_canon_grew_a_named_payload_section(new_sections: dict[str, str]):
    """The house pattern: payload rules are NAMED CONSTANTS, not inline prose."""
    assert new_sections, (
        "gen/visual_canon.py carries no module-level string constant beyond HEAD's "
        f"{sorted(HEAD_VISUAL_CANON_STRINGS)}.  The contract's own words: 'a new named "
        "payload section (constant) stating the two rules with the §9 citation' — the "
        "`VISUAL_CRAFT` / `TEACHING_BY_SHOWING` pattern, so the rule can be quoted into "
        "the payload and pinned by a test instead of retyped"
    )


SECTION_IDS = (
    "palette.background", "painted", "not-0-unless-declared", "0-reserved-for-selection",
    "section-9-anchor", "canon-file", "multi-tile", "not-1x1", "declared-exception",
    "REQUIRED",
)


@pytest.mark.parametrize(("what", "predicate"), SECTION_REQUIREMENTS, ids=SECTION_IDS)
def test_pin1_the_new_section_states_every_frozen_rule(
    what: str, predicate, new_sections: dict[str, str]
):
    """Source-text pins on the constants, never on a paraphrase of the payload."""
    if not new_sections:
        pytest.fail("gen/visual_canon.py grew no new named payload section (see pin 1's first test)")
    text = norm_text("\n\n".join(new_sections.values()))
    assert predicate(text), (
        f"the new payload section(s) {sorted(new_sections)} never state — {what}.\n"
        f"Canon: affordance-language.md §9:239-240 ('`0` white — selection/highlight "
        f"(the ecosystem's marker)... Semantic; avoid as plain paint') and §9:252 "
        f"(REQUIRED: 'reserve `0` for selection'); R-02's prose already exists at "
        f"gen/visual_canon.py:119-121 and this contract promotes it to a REQUIRED row.\n"
        f"Text measured:\n{text[:1500]}"
    )


def test_pin1_the_new_section_is_quoted_into_the_payload_by_s2_implement(
    new_sections: dict[str, str]
):
    """`s2_implement.py` names the constant, beside the existing grammar sections."""
    if not new_sections:
        pytest.fail("gen/visual_canon.py grew no new named payload section")
    source = S2_SOURCE.read_text(encoding="utf-8")
    carriers = [
        name for name, text in new_sections.items()
        if "palette.background" in norm_text(text) or "multi-tile" in norm_text(text)
    ]
    assert carriers, (
        f"none of the new constants {sorted(new_sections)} carries either rule, so none "
        f"of them is the section this contract asks for"
    )
    missing = [name for name in carriers if name not in source]
    assert not missing, (
        f"gen/s2_implement.py never names {missing} — a payload section nothing quotes "
        f"is a rule the implementer never reads.  The contract puts it 'beside the "
        f"existing grammar sections', where VISUAL_CRAFT and TEACHING_BY_SHOWING ride"
    )


@pytest.mark.parametrize(
    ("what", "pattern"),
    [
        ("the declared background index", r"palette\.background"),
        ("the §9 anchor", r"§\s*9\b|section 9\b"),
    ],
    ids=["palette.background", "section-9-anchor"],
)
def test_pin1_the_built_s2_payload_carries_the_new_rule(what: str, pattern: str, payload_text: str):
    """End to end: the real payload text, not just the constant.

    Both anchors are MEASURED ABSENT from HEAD's payload (the §9 body is quoted
    through `load_affordance_sections`, but under its file/line source cite, and
    `palette.background` is never mentioned at all), so each one bites.
    """
    assert re.search(pattern, norm_text(payload_text)) is not None, (
        f"the S2 payload never states {what} (/{pattern}/).  The rule exists to be read "
        f"by the implementer agent: a rule that only the card measures arrives one "
        f"whole stage too late to change what gets drawn"
    )


# =============================================================================
# PIN 2 — field-index: white fields fail, declared white fields pass
# =============================================================================


def build_case(
    build_card, tmp_path: Path, name: str, grid, spec: Mapping, cfg: Mapping
) -> tuple[dict, Path]:
    spec_dir = stage_case(tmp_path / name, grid, spec)
    return build_card(spec_dir, cfg), spec_dir


def field_verdict(report: Mapping) -> tuple[Mapping, bool, str]:
    block = check_block(report, FIELD_INDEX, label="field-index")
    return block, verdict(block, label="field-index"), mode_of(block, label="field-index")


def test_pin2_a_white_field_with_a_declared_non_zero_background_fails(
    build_card, gate_cfg, tmp_path: Path
):
    report, _dir = build_case(
        build_card, tmp_path, "white-field",
        white_field_board(), spec_document(background=BG), gate_cfg(field="fail"),
    )
    block, passed, mode = field_verdict(report)
    assert mode == "fail", f"field-index ran in {mode!r} mode; the config armed 'fail'"
    assert passed is False, (
        f"a board whose modal index is white 0 while the spec declares "
        f"`palette.background: {BG}` passed field-index ({dict(block)}).  That is the "
        f"exact defect the audit found in 4 of 7 shipped games: the FIELD is 0, so the "
        f"board has no painted floor and the ecosystem's white-selection idiom "
        f"(affordance §9:252 REQUIRED) is unusable"
    )


def test_pin2_a_white_field_a_spec_never_declared_fails(build_card, gate_cfg, tmp_path: Path):
    """INFERRED, and load-bearing: the shipped games declare no background at all.

    The rule is "fail when the modal ... is 0 AND the spec does not declare
    `background: 0`".  An absent declaration is not a declaration of 0, and the
    contract's own replay expects the check to flag four shipped games — none of
    which could declare a background before contract V-B existed.
    """
    report, _dir = build_case(
        build_card, tmp_path, "white-field-undeclared",
        white_field_board(), spec_document(background=_MISSING), gate_cfg(field="fail"),
    )
    _block, passed, _mode = field_verdict(report)
    assert passed is False, (
        "a board whose modal index is white 0, from a spec that declares no background "
        "at all, passed field-index.  Silence is not a declaration: the contract's "
        "replay requires this check to flag the four white-field shipped games, and not "
        "one of them declares `palette.background`"
    )


def test_pin2_a_white_field_declared_as_the_background_passes(build_card, gate_cfg, tmp_path: Path):
    """The KNOWN EDGE the contract names: '0 is not the field unless declared'.

    g50t, a signed official, is modal-0 on some levels.  The rule is never
    "0 is banned".
    """
    report, _dir = build_case(
        build_card, tmp_path, "white-field-declared",
        white_field_board(), spec_document(background=WHITE), gate_cfg(field="fail"),
    )
    _block, passed, _mode = field_verdict(report)
    assert passed is True, (
        "a board whose modal index is 0 FAILED field-index even though its spec "
        "declares `palette.background: 0`.  The contract's KNOWN EDGE is explicit — at "
        "least one official (g50t) is modal-0 on some levels, and the rule is '0 is not "
        "the field unless declared', NEVER '0 is banned'"
    )


def test_pin2_a_board_painted_in_its_declared_background_passes(
    build_card, gate_cfg, tmp_path: Path
):
    report, _dir = build_case(
        build_card, tmp_path, "painted-field",
        painted_field_board(), spec_document(background=BG), gate_cfg(field="fail"),
    )
    _block, passed, _mode = field_verdict(report)
    assert passed is True, (
        f"a board painted in its own declared `palette.background: {BG}`, using 0 only "
        f"as a selection mark, FAILED field-index.  This is precisely the shape the "
        f"officials ship (ls20's grey maze floor, ka59's grey rooms, dc22's charcoal "
        f"board) and the shape R-01 exists to produce"
    )


def test_pin2_record_mode_measures_the_same_failure_without_arming_it(
    build_card, gate_cfg, tmp_path: Path
):
    """`record` is the birth mode: the number is on the card, the verdict is not."""
    report, spec_dir = build_case(
        build_card, tmp_path, "white-field-record",
        white_field_board(), spec_document(background=BG), gate_cfg(field="record"),
    )
    block, passed, mode = field_verdict(report)
    assert mode == "record", f"field-index reports mode {mode!r} for a config that armed 'record'"
    assert passed is False, (
        f"in `record` mode field-index reports {dict(block)} — the MEASUREMENT must not "
        f"depend on the mode.  `l1_color_floor` is the pattern: it computes `passed` "
        f"either way and lets the knob decide who acts on it"
    )
    for name in REPORT_NAMES:
        assert (spec_dir / GATE_DIRNAME / name).is_file(), (
            f"{name} was not written for a game that fails field-index in record mode.  "
            f"Record mode never withholds a report"
        )


def test_pin2_mode_off_adds_no_new_gate_verdict(build_card, gate_cfg, tmp_path: Path):
    """AMBIGUITY (see the module docstring): "byte-identical" read as "no verdict".

    Pinned at the TOP LEVEL, where `l1_color_floor` lives and where a gate
    verdict would have to appear to be readable by the gate runner.
    """
    _report, spec_dir = build_case(
        build_card, tmp_path, "white-field-off",
        white_field_board(), spec_document(background=BG), gate_cfg(field="off", role="off"),
    )
    written = json.loads((spec_dir / GATE_DIRNAME / REPORT_JSON).read_text(encoding="utf-8"))
    assert set(written) == set(HEAD_CARD_KEYS), (
        f"with both checks OFF the written {REPORT_JSON} carries top-level keys "
        f"{sorted(written)}; HEAD's card carries {sorted(HEAD_CARD_KEYS)}.  The contract "
        f"pins mode off to 'report byte-identical to pre-existing card shape (no new "
        f"gate verdict)': a batch that never heard of these checks must get the card it "
        f"got before they existed"
    )


def test_pin2_mode_off_puts_no_pass_fail_field_on_a_record(build_card, gate_cfg, tmp_path: Path):
    _report, spec_dir = build_case(
        build_card, tmp_path, "white-field-off-records",
        white_field_board(), spec_document(background=BG), gate_cfg(field="off", role="off"),
    )
    written = json.loads((spec_dir / GATE_DIRNAME / REPORT_JSON).read_text(encoding="utf-8"))
    for index, record in enumerate(record_cards(written)):
        strays = [key for key in record if norm_key(key) in {"passed", "pass", "verdict"}]
        assert not strays, (
            f"record {index} carries {strays} with both checks OFF.  A per-record "
            f"pass/fail face IS a gate verdict, wherever it is written"
        )


@pytest.mark.parametrize("game", sorted(B003R2_DIGESTS), ids=sorted(B003R2_DIGESTS))
@pytest.mark.parametrize("report_name", (REPORT_JSON, REPORT_MD), ids=("json", "md"))
def test_pin2_mode_off_leaves_the_shipped_b003r2_cards_byte_identical(
    game: str, report_name: str, build_card, gate_cfg, tmp_path: Path
):
    """The contract's own regression, against digests measured on HEAD.

    The two shipped cards are rebuilt from READ-ONLY copies of their sidecars,
    with both new checks off, and compared to the bytes HEAD produced.  If this
    is the only pin that fails, the implementation made the new per-record
    METRICS unconditional — read the module docstring's first ambiguity before
    changing anything.
    """
    source = B003R2_ROOT / game
    if not (source / FRAMES_NAME).is_file() or not (source / SPEC_NAME).is_file():
        pytest.skip(f"{source} is not on this machine; the byte-identity pin cannot run")
    spec_dir = tmp_path / game
    spec_dir.mkdir(parents=True)
    for name in (FRAMES_NAME, SPEC_NAME):
        shutil.copyfile(source / name, spec_dir / name)
    build_card(spec_dir, gate_cfg(field="off", role="off"))
    digest = hashlib.sha256((spec_dir / GATE_DIRNAME / report_name).read_bytes()).hexdigest()
    assert digest == B003R2_DIGESTS[game][report_name], (
        f"{game}'s {report_name} is no longer the file HEAD wrote when both new checks "
        f"are off (sha256 {digest}, HEAD {B003R2_DIGESTS[game][report_name]}).  The "
        f"contract: 'Cards must remain byte-identical for the two shipped b003r2 cards "
        f"when your checks run in mode OFF (regression: the existing determinism pin)'"
    )


def test_pin2_two_builds_in_record_mode_are_byte_identical(build_card, gate_cfg, tmp_path: Path):
    """The existing determinism pin, extended over the new fields."""
    spec_dir = stage_case(tmp_path / "determinism", painted_field_board(),
                          spec_document(background=BG, cell_px=4))
    cfg = gate_cfg()
    build_card(spec_dir, cfg)
    before = {name: (spec_dir / GATE_DIRNAME / name).read_bytes() for name in REPORT_NAMES}
    build_card(spec_dir, cfg)
    for name, first in before.items():
        assert first == (spec_dir / GATE_DIRNAME / name).read_bytes(), (
            f"rebuilding the card produced a different {name}.  Every new metric is an "
            f"ordered scan of a fixed grid, so a difference is an unordered set (a role "
            f"map, a component list) leaking into a report reviewers diff between rounds"
        )


# =============================================================================
# PIN 3 — index0_share and modal_matches_bg, on a hand-built grid
# =============================================================================


def test_pin3_index0_share_is_the_measured_fraction_of_white_cells(
    build_card, gate_cfg, tmp_path: Path
):
    grid = painted_field_board()
    whites = count(grid, WHITE)
    assert whites == 512 and CELLS == 4096, (
        f"this test's own fixture drifted: {whites} white cells of {CELLS}"
    )
    report, _dir = build_case(
        build_card, tmp_path, "share", grid, spec_document(background=BG), gate_cfg(),
    )
    for index, record in enumerate(record_cards(report)):
        share = find(record, "index0share", depth=1)
        assert share is not _MISSING, (
            f"record {index} carries no `index0_share` ({key_map(record)}).  R-01 "
            f"freezes it as a per-record card field: the share of the board painted in "
            f"the index §9 reserves for selection"
        )
        assert share == pytest.approx(whites / CELLS, abs=5e-5), (
            f"record {index}: index0_share is {share!r}; the grid paints {whites} of "
            f"{CELLS} cells white, which is {whites / CELLS} exactly (chosen to need no "
            f"rounding convention at all)"
        )


def test_pin3_modal_matches_bg_is_true_when_the_field_is_the_declared_background(
    build_card, gate_cfg, tmp_path: Path
):
    report, _dir = build_case(
        build_card, tmp_path, "modal-true",
        painted_field_board(), spec_document(background=BG), gate_cfg(),
    )
    for index, record in enumerate(record_cards(report)):
        matched = find(record, "modalmatchesbg", depth=1)
        assert matched is not _MISSING, (
            f"record {index} carries no `modal_matches_bg` ({key_map(record)})"
        )
        assert matched is True, (
            f"record {index}: modal_matches_bg is {matched!r} for a board whose modal "
            f"index is {BG} and whose spec declares `palette.background: {BG}`"
        )


def test_pin3_modal_matches_bg_is_false_when_the_field_is_not_what_was_declared(
    build_card, gate_cfg, tmp_path: Path
):
    report, _dir = build_case(
        build_card, tmp_path, "modal-false",
        painted_field_board(), spec_document(background=3), gate_cfg(),
    )
    for index, record in enumerate(record_cards(report)):
        matched = find(record, "modalmatchesbg", depth=1)
        assert matched is False, (
            f"record {index}: modal_matches_bg is {matched!r} for a board whose modal "
            f"index is {BG} while the spec declares `palette.background: 3` — a board "
            f"that does not paint the floor it promised"
        )


def test_pin3_modal_matches_bg_says_nothing_when_no_background_is_declared(
    build_card, gate_cfg, tmp_path: Path
):
    """"when declared" — an undeclared background is silence, never a False."""
    report, _dir = build_case(
        build_card, tmp_path, "modal-undeclared",
        painted_field_board(), spec_document(background=_MISSING), gate_cfg(),
    )
    for index, record in enumerate(record_cards(report)):
        matched = find(record, "modalmatchesbg", depth=1)
        assert matched is _MISSING or matched is None, (
            f"record {index}: modal_matches_bg is {matched!r} for a spec that declares "
            f"no background.  The field is defined 'when declared'; reporting False "
            f"against an absent declaration reads as a defect the spec never had "
            f"(`declared_absent`'s own precedent)"
        )


# =============================================================================
# PIN 4 — role-footprint: load-bearing state drawn as a lone pixel
# =============================================================================


def role_verdict(report: Mapping) -> tuple[Mapping, bool, str]:
    block = check_block(report, ROLE_FOOTPRINT, label="role-footprint")
    return block, verdict(block, label="role-footprint"), mode_of(block, label="role-footprint")


def test_pin4_a_one_pixel_you_fails_when_armed(build_card, gate_cfg, tmp_path: Path):
    report, _dir = build_case(
        build_card, tmp_path, "pixel-you",
        role_board("pixel"), spec_document(cell_px=4), gate_cfg(role="fail"),
    )
    block, passed, mode = role_verdict(report)
    assert mode == "fail", f"role-footprint ran in {mode!r} mode; the config armed 'fail'"
    assert passed is False, (
        f"a declared `palette.you` drawn as ONE pixel, on a game declaring "
        f"`render.cell_px: 4` (a logical cell is 16 px), passed role-footprint "
        f"({dict(block)}).  This is the audit's 4-of-7 defect: facing-sentinel's avatar "
        f"is 5 isolated px, mosaic's mirror is 4, core-ward's lane is 1 px per cell"
    )


def test_pin4_a_full_logical_cell_of_you_passes(build_card, gate_cfg, tmp_path: Path):
    report, _dir = build_case(
        build_card, tmp_path, "cell-you",
        role_board("cell"), spec_document(cell_px=4), gate_cfg(role="fail"),
    )
    _block, passed, _mode = role_verdict(report)
    assert passed is True, (
        "a declared `palette.you` drawn as a 4x4 block — exactly one logical cell at "
        "the declared `render.cell_px: 4` — FAILED role-footprint.  The floor is "
        "'< one full logical cell', so a component of exactly cell_px**2 clears it"
    )


def test_pin4_an_undeclared_role_is_recorded_not_checked(build_card, gate_cfg, tmp_path: Path):
    """`danger: null` is a §11 value meaning 'this game has no danger'."""
    report, _dir = build_case(
        build_card, tmp_path, "undeclared-danger",
        role_board("cell"), spec_document(danger=None, cell_px=4), gate_cfg(role="fail"),
    )
    _block, passed, _mode = role_verdict(report)
    assert passed is True, (
        "a hazardless game (`palette.danger: null`) failed role-footprint.  An "
        "undeclared role is not a claim about the board and cannot be measured against "
        "one"
    )
    for index, record in enumerate(record_cards(report)):
        mins = role_mins(record, report)
        assert is_not_checked(mins.get("danger", _MISSING)), (
            f"record {index}: role_component_min reports {mins.get('danger')!r} for a "
            f"role the spec declares as null.  The contract counts these: 'Where a "
            f"shipped game lacks a declared role index the check records not-checked'"
        )


def test_pin4_a_declared_but_unpainted_role_is_not_a_failure(build_card, gate_cfg, tmp_path: Path):
    """The measured false-fail the card was built around, held open.

    `core-ward-phase-gates` — human-ACCEPTED — declares `you: 11` and does not
    paint it until the first click.  R-02 scopes the check to roles "declared
    AND painted" for exactly this reason.
    """
    report, _dir = build_case(
        build_card, tmp_path, "unpainted-goal",
        role_board("cell"), spec_document(goal=UNPAINTED, cell_px=4), gate_cfg(role="fail"),
    )
    _block, passed, _mode = role_verdict(report)
    assert passed is True, (
        f"a declared `palette.goal: {UNPAINTED}` that is never painted on the board "
        f"FAILED role-footprint.  A role with no pixels has no smallest component; "
        f"rejecting on it re-imports the declared-palette-painted false-fail that "
        f"contract V-C already measured and killed"
    )


def test_pin4_role_component_min_is_the_measured_smallest_blob(
    build_card, gate_cfg, tmp_path: Path
):
    """Both shapes are isolated, so 4- and 8-connectivity agree (see the docstring)."""
    report, _dir = build_case(
        build_card, tmp_path, "mins",
        role_board("pixel"), spec_document(cell_px=4), gate_cfg(),
    )
    for index, record in enumerate(record_cards(report)):
        mins = role_mins(record, report)
        assert mins.get("you") == 1, (
            f"record {index}: role_component_min['you'] is {mins.get('you')!r}; the "
            f"board paints `you` as a single isolated pixel"
        )
        assert mins.get("goal") == 16, (
            f"record {index}: role_component_min['goal'] is {mins.get('goal')!r}; the "
            f"board paints `goal` as one 4x4 block, 16 cells"
        )


@pytest.mark.parametrize(
    ("shape", "size", "expected_pass"),
    [("pixel", 1, False), ("triple", 3, False), ("quad", 4, True), ("cell", 16, True)],
    ids=["1px", "3px", "4px", "16px"],
)
def test_pin4_without_a_declared_render_the_floor_is_the_conservative_four(
    shape: str, size: int, expected_pass: bool, build_card, gate_cfg, tmp_path: Path
):
    """`else a documented conservative floor of 4 px` — the undeclared-render arm."""
    report, _dir = build_case(
        build_card, tmp_path, f"norender-{shape}",
        role_board(shape), spec_document(cell_px=None), gate_cfg(role="fail"),
    )
    _block, passed, _mode = role_verdict(report)
    assert passed is expected_pass, (
        f"a `you` drawn as a {size} px component, on a spec that declares no "
        f"`render.cell_px`, reports passed={passed!r} (expected {expected_pass!r}).  "
        f"The contract's fallback is a conservative floor of {CONSERVATIVE_FLOOR_PX} px, "
        f"and the comparison is '< one full logical cell', so {CONSERVATIVE_FLOOR_PX} px "
        f"itself clears it"
    )


def test_pin4_the_metric_is_per_role_components_and_never_ones_share(s3_visual):
    """The HARD PROHIBITION from the audit record, pinned as source text.

    The officials' median `ones_share` is 4x OURS, so a corpus `ones_share`
    target moves the board the WRONG WAY (findings.md §B1).  `run_length_profile`
    keeps reporting it as DATA; what must never exist is a rejection that reads
    it.
    """
    source = Path(s3_visual.__file__).read_text(encoding="utf-8")
    body = source[source.find("def "):]
    offenders = [
        line.strip()
        for line in body.splitlines()
        if "ones_share" in line and re.search(r"[<>]=?|floor|threshold|reject|fail", line)
    ]
    assert not offenders, (
        "gen/s3_visual.py compares `ones_share` against something:\n  "
        + "\n  ".join(offenders)
        + "\nThe audit record's HARD PROHIBITION: the acceptance metric is per-role "
        "component floors, NEVER rl_ones_share — the officials' median ones_share is 4x "
        "ours, so a corpus target on it pushes generated boards further from the corpus, "
        "not closer (the direction trap in findings.md §B1)"
    )


# --- the declared-exception surface (discovered, not guessed) -----------------

EXEMPTION_NAME_FALLBACKS = (
    "role_footprint_exempt", "role_footprint_exempt_roles", "role_footprint_exemptions",
    "footprint_exempt", "exempt_roles", "tiny_token_roles", "tiny_tokens",
)

# The vocabulary the contract leaves the surface free to key on: the ROLE name,
# the palette INDEX that role declares, the game's own slug, and the two
# qualified forms that join them.  `SYNTHETIC_SLUG` is what `spec_document`
# writes, and `YOU` is the index it declares for the role drawn as one pixel.
SYNTHETIC_SLUG = "w1-synthetic"
BASIC_EXEMPTIONS = (["you"], ("you",), "you", True, {"you": True})
RICH_EXEMPTIONS = (
    *BASIC_EXEMPTIONS,
    [YOU], YOU, str(YOU), [str(YOU)],
    [SYNTHETIC_SLUG], SYNTHETIC_SLUG,
    [f"{SYNTHETIC_SLUG}:you"], [f"{SYNTHETIC_SLUG}.you"], [f"{SYNTHETIC_SLUG}/you"],
    {SYNTHETIC_SLUG: ["you"]}, {SYNTHETIC_SLUG: True},
    [{"slug": SYNTHETIC_SLUG, "role": "you"}], [{"game": SYNTHETIC_SLUG, "role": "you"}],
    ["you: declared tiny token"],
)


def exemption_attempts(s3_visual, base_gate: Mapping, known: tuple[str, ...]):
    """Every config shape that might declare `you` a deliberate tiny token.

    The extra `GATE_KEYS` entries come first and get the whole vocabulary:
    they are the module's OWN declaration of what a gate config may carry, so a
    surface that exists at all is almost certainly one of them.  The
    conventional names are a fallback and get the basic shapes only, which
    keeps the sweep to a few dozen card builds.
    """
    declared = [key for key in _gate_keys(s3_visual) if key not in known]
    for key in declared:
        for value in RICH_EXEMPTIONS:
            yield f"gate.{key} = {value!r}", {"gate": {**base_gate, key: value}}
    for key in (name for name in EXEMPTION_NAME_FALLBACKS if name not in declared):
        for value in BASIC_EXEMPTIONS:
            yield f"gate.{key} = {value!r}", {"gate": {**base_gate, key: value}}
            yield f"{key} = {value!r} (config top level)", {"gate": dict(base_gate), key: value}


def test_pin4_a_declared_tiny_token_silences_the_check(
    s3_visual, build_card, gate_cfg, field_key: str, role_key: str, tmp_path: Path
):
    """The escape hatch, DISCOVERED (see the module docstring's fourth ambiguity).

    The contract leaves the surface to the implementer and forbids s1_spec
    edits, so only config surfaces are probed: every extra `GATE_KEYS` entry
    plus the conventional names, at gate level and at config top level.  Each
    rejected shape is recorded with its REASON — a shape the config refused
    outright is a different finding from one it accepted and then ignored.
    """
    spec_dir = stage_case(tmp_path / "tiny-token", role_board("pixel"), spec_document(cell_px=4))
    armed = gate_cfg(role="fail")
    _block, passed, _mode = role_verdict(build_card(spec_dir, armed))
    assert passed is False, (
        "the un-exempted one-pixel `you` must fail before this pin means anything"
    )

    known = (*HEAD_GATE_KEYS, field_key, role_key)
    refused: list[str] = []
    ignored: list[str] = []
    for label, cfg in exemption_attempts(s3_visual, armed["gate"], known):
        try:
            report = build_card(spec_dir, cfg)
        except Exception as exc:  # noqa: BLE001 — a shape this config does not offer
            refused.append(f"{label} -> {type(exc).__name__}: {exc}")
            continue
        block = find(report, ROLE_FOOTPRINT)
        if not isinstance(block, Mapping):
            ignored.append(f"{label} -> the card reported no role-footprint block")
            continue
        if verdict(block, label="role-footprint") is True:
            return
        ignored.append(f"{label} -> accepted, still failing")
    pytest.fail(
        "no config surface silences role-footprint for a DECLARED tiny token.  R-02 "
        "requires one — 'a declared-exception surface (\"tiny token\" must be declared; "
        "design the smallest honest surface ... else a config exemption list)' — because "
        "VISUAL_CRAFT's own rule ends 'unless the idea absolutely requires a tiny "
        "token', and a check with no escape hatch turns that clause into a lie.\n"
        f"gen.s3_visual.GATE_KEYS: {list(_gate_keys(s3_visual))}\n"
        f"ACCEPTED but did not silence it ({len(ignored)}):\n  " + "\n  ".join(ignored)
        + f"\nREFUSED by the config block ({len(refused)}):\n  " + "\n  ".join(refused[:20])
        + "\nIf the surface is spec-side instead, say so in the report: the contract asks "
        "for that finding rather than an s1_spec edit."
    )


# =============================================================================
# PIN 5 — the two knobs
# =============================================================================


def test_pin5_both_checks_are_born_in_record_mode(field_mode, role_mode):
    assert field_mode({}) == DEFAULT_MODE, (
        "a config with no gate block must leave field-index in `record`.  A new "
        "rejection earns its place on measured data, never on the day it is written — "
        "and this one would retroactively kill four shipped, human-ACCEPTED games"
    )
    assert role_mode({}) == DEFAULT_MODE, (
        "a config with no gate block must leave role-footprint in `record`"
    )


def test_pin5_an_empty_gate_block_is_the_same_as_no_gate_block(field_mode, role_mode):
    assert field_mode({"gate": {}}) == DEFAULT_MODE
    assert role_mode({"gate": {}}) == DEFAULT_MODE


@pytest.mark.parametrize("mode", CHECK_MODES)
def test_pin5_every_field_index_mode_parses(mode: str, field_mode, field_key: str):
    assert field_mode({"gate": {field_key: mode}}) == mode, (
        f"gate.{field_key}: {mode!r} did not round-trip; the contract freezes the enum "
        f"as {list(CHECK_MODES)}"
    )


@pytest.mark.parametrize("mode", CHECK_MODES)
def test_pin5_every_role_footprint_mode_parses(mode: str, role_mode, role_key: str):
    assert role_mode({"gate": {role_key: mode}}) == mode, (
        f"gate.{role_key}: {mode!r} did not round-trip; the contract freezes the enum "
        f"as {list(CHECK_MODES)}"
    )


@pytest.mark.parametrize("bad", BAD_MODES)
def test_pin5_a_field_index_value_outside_the_enum_is_loud(bad: str, field_mode, field_key: str):
    with pytest.raises(ValueError):
        field_mode({"gate": {field_key: bad}})


@pytest.mark.parametrize("bad", BAD_MODES)
def test_pin5_a_role_footprint_value_outside_the_enum_is_loud(bad: str, role_mode, role_key: str):
    with pytest.raises(ValueError):
        role_mode({"gate": {role_key: bad}})


def test_pin5_both_new_knobs_joined_the_closed_gate_key_set(s3_visual, field_key, role_key):
    keys = _gate_keys(s3_visual)
    for name in (*HEAD_GATE_KEYS, field_key, role_key):
        assert name in keys, f"GATE_KEYS lost {name!r}: {list(keys)}"
    with pytest.raises(ValueError):
        # The block stays CLOSED: two new knobs are two new keys, not an open door.
        s3_visual.visual_card_mode({"gate": {field_key: "record", "visual-card": "fail"}})


# =============================================================================
# PIN 6 — config/template.yaml arms both, and every knob reader still accepts it
# =============================================================================


def _template_tree() -> dict:
    if not TEMPLATE_PATH.is_file():  # pragma: no cover - the template is shipped
        pytest.fail(f"config/template.yaml missing: {TEMPLATE_PATH}")
    tree = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert isinstance(tree, dict), f"template did not parse to a mapping: {type(tree).__name__}"
    return tree


@pytest.fixture
def template_cfg(tmp_path: Path) -> dict:
    """`load_config` over a tmp COPY — test_docs_template's own hygiene rule."""
    return load_config(_template_copy(tmp_path))


@pytest.mark.parametrize("check", ("field", "role"), ids=("field-index", "role-footprint"))
def test_pin6_the_template_arms_the_check_as_fail(check: str, field_key: str, role_key: str):
    key = field_key if check == "field" else role_key
    gate = _template_tree().get("gate")
    assert isinstance(gate, dict), f"config/template.yaml has no `gate:` block, got {gate!r}"
    assert gate.get(key) == "fail", (
        f"config/template.yaml has gate.{key} = {gate.get(key)!r}; the contract arms it "
        f"as `fail` (both checks are born in `record` in CODE and armed in the TEMPLATE "
        f"only — that split is the house pattern this contract names)"
    )


def _extended_readers(field_mode, role_mode, field_key: str, role_key: str) -> dict:
    """The 17 readers `test_docs_template` already pins, plus this contract's two.

    Imported, never copied: the contract's own instruction.  When a later wave
    adds a knob, that file stays the single roster and this one only adds its
    own entries.
    """
    readers = dict(_readers())
    readers[f"s3_visual.{getattr(field_mode, '__name__', field_key)}"] = field_mode
    readers[f"s3_visual.{getattr(role_mode, '__name__', role_key)}"] = role_mode
    return readers


def test_pin6_the_reader_roster_grew_by_exactly_the_two_new_knobs(
    field_mode, role_mode, field_key: str, role_key: str
):
    readers = _extended_readers(field_mode, role_mode, field_key, role_key)
    assert len(readers) == len(_readers()) + 2, (
        f"the extended roster is {len(readers)} readers, not {len(_readers())} + 2 — the "
        f"two new mode readers collided with a name already on "
        f"test_docs_template's table: {sorted(readers)}"
    )


def test_pin6_every_knob_reader_accepts_the_armed_template(
    template_cfg: dict, field_mode, role_mode, field_key: str, role_key: str
):
    """The whole roster in one pass, so a close can be sequenced from one run."""
    failures = []
    for name, reader in sorted(_extended_readers(field_mode, role_mode, field_key, role_key).items()):
        try:
            reader(template_cfg)
        except Exception as exc:  # noqa: BLE001 — collected, not swallowed
            failures.append(f"  {name}: {type(exc).__name__}: {exc}")
    assert not failures, (
        f"{len(failures)} config readers rejected the armed config/template.yaml:\n"
        + "\n".join(failures)
        + "\nA gate block is key-CLOSED: arming a knob the readers do not know turns "
        "every stage that reads the gate into a loud crash, one batch too late"
    )


@pytest.mark.parametrize("check", ("field", "role"), ids=("field-index", "role-footprint"))
def test_pin6_the_armed_template_round_trips_through_its_own_reader(
    check: str, template_cfg: dict, field_mode, role_mode
):
    reader = field_mode if check == "field" else role_mode
    assert reader(template_cfg) == "fail", (
        f"the template arms this check but its reader returns {reader(template_cfg)!r} — "
        f"the knob in the yaml and the knob the code reads are not the same key"
    )


def test_pin6_the_template_documents_both_checks_in_a_comment():
    """`commented`, twice, in the contract's own words."""
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    comments = "\n".join(line for line in text.splitlines() if line.lstrip().startswith("#"))
    for word in ("field-index", "role-footprint"):
        assert word in comments or word.replace("-", "_") in comments, (
            f"config/template.yaml arms a check it never explains: no comment mentions "
            f"{word!r}.  Every other knob in that file carries the measurement that "
            f"justifies it, and the contract asks for both of these 'commented'"
        )


# ---------------------------------------------------------------------------
# lead-authored at the wave-1 close: the orchestrator seam both A1 agents
# flagged. The gate closure must consult BOTH new checks' modes and reject
# with a reason naming the rule — without this wiring the template's two
# `fail` arms are decoration (the exact defect class R-06 exists to kill).
# ---------------------------------------------------------------------------


def test_lead_orchestrator_wires_both_checks_to_fail():
    import inspect

    from gen import orchestrator

    src = inspect.getsource(orchestrator)
    assert "FIELD_INDEX_CHECK, field_index_mode(ctx.cfg)" in src.replace("\n", " ").replace(
        "  ", " "
    ) or "FIELD_INDEX_CHECK" in src
    for name in ("FIELD_INDEX_CHECK", "ROLE_FOOTPRINT_CHECK",
                 "field_index_mode", "role_footprint_mode"):
        assert name in src, f"orchestrator gate wiring missing {name}"
    assert 'f"visual {check_key}"' in src, "rejection reason must name the failing rule"
