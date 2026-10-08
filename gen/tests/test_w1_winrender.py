"""Blind pins for contract W1-A2 — R-04 render the win, R-06 declared-vs-painted acted on.

Run: .venv/bin/python -m pytest gen/tests/test_w1_winrender.py -v

Written from ``scratchpad/w1-r04r06-contract.md`` ALONE, by a separate agent, while
the implementer's change was in progress.  No in-progress diff of
``gen/visual_canon.py``, ``gen/s2_implement.py``, ``gen/s3_visual.py``,
``gen/s3_gate.py``, ``gen/orchestrator.py`` or ``config/template.yaml`` was read.
The only things read off the working tree are the PRE-A2 shapes the contract names
as precedents — the phase-1 ``field-index`` / ``role-footprint`` checks, their
``off|record|fail`` knobs and mode readers, ``GATE_KEYS`` as a closed key set, and
the orchestrator's lead-wired fail loop — so that this file pins A2's TWO checks by
the contract's stated semantics and nothing else.  These tests are EXPECTED TO FAIL
against the pre-A2 tree and to pass against the finished change.

WHAT THE CHANGE IS FOR.  R-04: the winning board carries no signal in 4 of the 7
shipped games — convoy's win frame is BYTE-IDENTICAL to a frame 84 actions earlier,
pump-phase's differs from its final level start in 183/4096 px of which 103 are the
two HUD rows, pump-flow's in 80/4096 with four satisfied targets still fog stubs,
and core-ward has no win indicator at all.  Officials always render the win.  R-06:
declared-vs-painted already fails in all 7 and is already flagged on every M-1 card
— "a gate that fires and is not acted on" — so the facts become a card-level verdict
with a knob, and the REVIEW REQUIRED stop names the rows.

BLIND NAME RESOLUTION.  The contract freezes the two checks' NAMES (``win-render``,
``declared-vs-painted``), their modes, their defaults and their semantics — it does
not freeze the python identifiers, and it spells the first knob ``win-render`` in
the template line while spelling the second ``declared_vs_painted`` (see AMBIGUITY 1).
Nothing here guesses: the knob keys are read out of ``s3_visual.GATE_KEYS`` (the
closed key set a new knob MUST join or ``config/template.yaml`` will not load), the
mode readers are found by matching those names and then by behaviour, and every card
lookup normalises keys (``win-render`` / ``win_render`` / ``winRender`` all resolve).
A name that cannot be resolved fails with the full list of what the module does
offer, so the lead can alias in one line instead of guessing what the pin wanted.

CONTRACT AMBIGUITIES, each called out again at its pin:

* **The knob spelling.**  R-04 says template.yaml arms ``win-render: fail`` (dashed)
  while R-06 says ``declared_vs_painted: fail`` (snake), and the house rule inside
  ``gen/s3_visual.py`` is "the CONFIG keys stay snake_case ... the check ids use the
  dashed spelling".  Resolved by never typing either: the knob key comes from
  ``GATE_KEYS`` and the template is checked for whatever key that is.
* **The floor's UNITS.**  "fail below a floor ... pick the floor from the measured
  deltas" is stated in px on 64x64 boards (0 / 80 / 80 must fail, conduit must pass).
  A share would be an equally honest reading, so ``_above_the_eighty_px_exhibit``
  accepts either: an absolute count must exceed 80, a share must exceed 80/4096.
* **Which level start.**  "the last level-start record" (the check's words) and "the
  final level's start frame" (the payload row's words) can differ if a capture's
  last level start is not the final level's.  Every synthetic sidecar here carries
  the SAME board on every non-win record, so both readings reach one verdict.
* **Where the WIN record is found** (``state == "WIN"`` vs the ``final`` label) is
  unstated.  The win sidecars mark the winning frames both ways, exactly as the
  seven shipped sidecars do; the no-win sidecar has neither.
* **The violation-row shape** for R-06 is unstated beyond "a violation row" that the
  review print can list.  Pinned as: a sequence under a violation-ish key whose row
  names the role, resolving several spellings, never one exact schema.
* **The declared-exception surface** ("config exemption naming role+game rationale,
  smallest honest design") is explicitly left to the implementer, so the pin
  DISCOVERS it: every extra ``GATE_KEYS`` entry plus a list of conventional names is
  tried, at gate level and at config top level, with and without a rationale, and
  the failure message prints every shape tried.
* **Which module owns the gate wiring.**  R-06 says ``s3_gate.py``; the pre-A2 tree
  wires ``visual_card`` / ``l1_color_floor`` / ``field-index`` / ``role-footprint``
  in ``gen/orchestrator.py``'s ``s3_gate`` stage instead (``gen/s3_gate.py`` mentions
  the card nowhere).  The wiring pin therefore reads BOTH files as one text.

HYGIENE: tmp_path only — no file under ``out/`` is read or written, no network, no
driver, no engine import, no API call.
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
import yaml

from gen.config import REPO_ROOT, load_config
from gen.tests.test_docs_template import _readers, _template_copy

# --- locations ----------------------------------------------------------------

ROOT = Path(REPO_ROOT)
TEMPLATE_PATH = ROOT / "config" / "template.yaml"
S3_VISUAL_SOURCE = ROOT / "gen" / "s3_visual.py"
S3_GATE_SOURCE = ROOT / "gen" / "s3_gate.py"
ORCHESTRATOR_SOURCE = ROOT / "gen" / "orchestrator.py"

SPEC_NAME = "spec.yaml"
FRAMES_NAME = "worker.frames.json"

# --- the contract's frozen surface -------------------------------------------

WIN_RENDER = "winrender"                    # the check named `win-render`
DECLARED_VS_PAINTED = "declaredvspainted"   # the check named `declared-vs-painted`
CHECK_MODES = ("off", "record", "fail")
DEFAULT_MODE = "record"
BAD_MODES = ("on", "true", "Record", "record ", "warn", "kill", "")

# `gen/s3_visual.GATE_KEYS` on the PRE-A2 tree (phase 1 landed; this is a stable
# pattern, not the implementer's diff).  Used only to work out which entries are
# NEW, which is how the declared-exception surface is discovered rather than guessed.
PRE_A2_GATE_KEYS = (
    "visual_card", "l1_color_floor", "field_index", "role_footprint", "role_footprint_exempt",
)

# The four audit exhibits the floor is calibrated against, and the one that must
# pass.  Quoted into failure messages so a wrong floor names its own evidence.
EXHIBITS = ("convoy", "pump-flow", "pump-phase", "core-ward")
PASSING_EXHIBIT = "conduit-watch"
# pump-phase's win differs from its final level start in 80 BOARD px of 4096 and must
# FAIL, so the floor is above 80 px — or above the same share of a 64x64 board.
EXHIBIT_FAIL_PX = 80
BOARD_CELLS_64 = 64 * 64

# --- the synthetic boards ------------------------------------------------------
# 64x64 because every frozen card metric assumes the ARC camera and all seven
# shipped sidecars are 64x64.  The one exception is the tall board of pin 2, whose
# whole job is a HUD strip LONGER than any floor a 64x64 corpus could calibrate.

GRID_SIDE = 64
TALL_ROWS = 512
WHITE = 0       # affordance §9: the ecosystem's selection mark
BG = 5          # affordance §9: "`5` black — background/outline default"
YOU = 9
GOAL = 14
DANGER = 8
HUD_PAINT = 1   # what a HUD-only "win" repaints its declared strip with

SYNTHETIC_GAME = "w1-a2-synthetic"
RATIONALE = (
    "transient by design: the selection colour is painted by code and never settles "
    "in a captured frame (R-20 capture dependency)"
)

WIN_STATE = "WIN"
LIVE_STATE = "NOT_FINISHED"

_MISSING = object()


# --- normalised lookup (shape unpinned, meaning pinned) -----------------------


def norm_key(name: object) -> str:
    """`win-render`, `win_render` and `winRender` are one name."""
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
            keys.extend(str(key) for key in value)
    return sorted(set(keys))


def strings_in(node: object) -> list[str]:
    """Every string anywhere inside a check block — its prose, whatever it is called."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, Mapping):
        return [text for value in node.values() for text in strings_in(value)]
    if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        return [text for value in node for text in strings_in(value)]
    return []


def numbers_under(node: object, pattern: re.Pattern[str]) -> dict[str, float]:
    """Every number whose KEY matches `pattern`, anywhere inside a check block."""
    found: dict[str, float] = {}
    if isinstance(node, Mapping):
        for key, value in node.items():
            if (
                pattern.search(str(key))
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                found[str(key)] = value
            found.update(numbers_under(value, pattern))
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for value in node:
            found.update(numbers_under(value, pattern))
    return found


# --- reading a check block ----------------------------------------------------

NOT_CHECKED_RE = re.compile(r"not[-_ ]?checked|\bn/a\b|\bskipp?ed\b|\bunchecked\b", re.IGNORECASE)
NO_WIN_TEXT_RE = re.compile(
    r"not[-_ ]?checked|\bno\b[^.]{0,40}\bwin\b|lacks[^.]{0,30}\bwin\b|without[^.]{0,30}\bwin\b",
    re.IGNORECASE,
)
PASS_KEYS = ("passed", "pass", "ok", "clean")
FAIL_WORDS = {"fail", "failed", "failing", "violation", "violations", "reject", "rejected"}
PASS_WORDS = {"pass", "passed", "ok", "clean", "none"}


def check_block(report: Mapping, check: str, *, label: str) -> Mapping:
    """The card-level block for one of the two new checks."""
    found = find(report, check)
    if found is _MISSING or not isinstance(found, Mapping):
        pytest.fail(
            f"the visual card carries no {label!r} block (a mapping keyed on some spelling "
            f"of {label!r}); the card offers {key_map(report)}.  The contract freezes "
            f"{label!r} as a card-level check beside `l1_color_floor` / `field-index` / "
            f"`role-footprint`, which is the shape it names as the pattern to match"
        )
    return found


def is_not_checked(block: Mapping) -> bool:
    """The check declined to judge this game — structurally, not from free prose."""
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
    """`True` passed, `False` failed, `None` not checked.  `l1_color_floor` is the precedent."""
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
            f"check in this module records the mode it ran in, so a reader can tell a "
            f"recorded failure from a rejecting one"
        )
    return found


# --- the boards ----------------------------------------------------------------


def blank(rows: int, cols: int, value: int) -> list[list[int]]:
    return [[value] * cols for _ in range(rows)]


def paint(grid: list[list[int]], top: int, left: int, height: int, width: int, value: int) -> None:
    for y in range(top, top + height):
        for x in range(left, left + width):
            grid[y][x] = value


def copy_grid(grid: Sequence[Sequence[int]]) -> list[list[int]]:
    return [list(row) for row in grid]


def cell_delta(left: Sequence[Sequence[int]], right: Sequence[Sequence[int]]) -> int:
    """How many cells differ — the number this file's boards are built around."""
    return sum(
        1
        for row_l, row_r in zip(left, right, strict=True)
        for value_l, value_r in zip(row_l, row_r, strict=True)
        if value_l != value_r
    )


def level_board(rows: int = GRID_SIDE, cols: int = GRID_SIDE, *, you: bool = True) -> list[list[int]]:
    """A settled level-start board: a PAINTED field, one block per declared role.

    Every shape sits in rows 4-31 and columns 4-31, which keeps row 0, row 63 and
    column 0 — the three `hud.reserved` strips the card can locate — uniform field,
    so a HUD-only "win" changes exactly the strip and nothing else.
    """
    grid = blank(rows, cols, BG)
    if you:
        paint(grid, 4, 4, 4, 4, YOU)
    paint(grid, 12, 12, 4, 4, GOAL)
    paint(grid, 20, 20, 4, 4, DANGER)
    paint(grid, 28, 28, 2, 2, WHITE)        # the selection mark, and the 5th colour
    return grid


def hud_only_win(board: Sequence[Sequence[int]], token: str) -> list[list[int]]:
    """A "win" that repaints EVERY cell of the declared HUD strip and nothing else."""
    grid = copy_grid(board)
    if token.startswith("row"):
        index = int(token[3:])
        grid[index] = [HUD_PAINT] * len(grid[index])
    elif token.startswith("col"):
        index = int(token[3:])
        for row in grid:
            row[index] = HUD_PAINT
    else:  # pragma: no cover - a typo in this file, not in the implementation
        raise AssertionError(f"unknown hud strip token {token!r}")
    return grid


def legible_win(board: Sequence[Sequence[int]]) -> list[list[int]]:
    """A win the player can SEE: the top half of the board repaints, clear of row 63.

    2032 of 4096 cells change (the 16 that were already `goal` do not), which clears
    any floor the four exhibits could calibrate — the officials' own win renders are
    "all 60 targets covered" / "twelve filled + backings flipped white".
    """
    grid = copy_grid(board)
    paint(grid, 0, 0, GRID_SIDE // 2, GRID_SIDE, GOAL)
    return grid


# --- the sidecars ---------------------------------------------------------------


def record(label: str, seq: int, completed: int, state: str, grid: Sequence[Sequence[int]]) -> dict:
    return {"label": label, "seq": seq, "levels_completed": completed, "state": state,
            "grid": copy_grid(grid)}


def frames_document(records: Sequence[Mapping], *, game_id: str = SYNTHETIC_GAME) -> dict:
    """The S2b sidecar shape, with the two top-level keys the shipped ones carry."""
    rows = [dict(entry) for entry in records]
    return {
        "game_id": game_id,
        "source": "synthetic",
        "levels_completed": max(int(entry["levels_completed"]) for entry in rows),
        "win": any(entry["state"] == WIN_STATE for entry in rows),
        "records": rows,
    }


def win_sidecar(level_grid: Sequence[Sequence[int]], win_grid: Sequence[Sequence[int]],
                *, game_id: str = SYNTHETIC_GAME) -> dict:
    """reset · a level-2 start · the winning frame · `final`, exactly as S2b writes them.

    Both non-win records carry the SAME board, so "the last level-start record" and
    "the final level's start frame" name one grid (AMBIGUITY 3), and both winning
    records carry the same board, as all seven shipped sidecars do (convoy's
    step-418 ≡ final).
    """
    return frames_document(
        [
            record("reset", 0, 0, LIVE_STATE, level_grid),
            record("step-9:ACTION5", 1, 1, LIVE_STATE, level_grid),
            record("step-21:ACTION5", 2, 2, WIN_STATE, win_grid),
            record("final", 3, 2, WIN_STATE, win_grid),
        ],
        game_id=game_id,
    )


def no_win_sidecar(level_grid: Sequence[Sequence[int]], *, game_id: str = SYNTHETIC_GAME) -> dict:
    """A capture that never reached a win — the facing-sentinel class the contract names."""
    return frames_document(
        [
            record("reset", 0, 0, LIVE_STATE, level_grid),
            record("step-9:ACTION5", 1, 1, LIVE_STATE, level_grid),
            record("step-21:ACTION5", 2, 2, LIVE_STATE, level_grid),
        ],
        game_id=game_id,
    )


def role_sidecar(grids: Sequence[Sequence[Sequence[int]]],
                 *, game_id: str = SYNTHETIC_GAME) -> dict:
    """One record per grid handed in — R-06 aggregates over EVERY record, not level starts."""
    rows = [
        record("reset", 0, 0, LIVE_STATE, grids[0]),
        *(
            record(f"step-{9 * index}:ACTION5", index, index, LIVE_STATE, grid)
            for index, grid in enumerate(grids[1:-1], start=1)
        ),
    ]
    rows.append(record("final", len(grids) - 1, len(grids) - 1, WIN_STATE, grids[-1]))
    return frames_document(rows, game_id=game_id)


def spec_document(
    *,
    you: int | None = YOU,
    goal: int | None = GOAL,
    danger: int | None = DANGER,
    background: int | None = BG,
    hud_reserved: str = "row63",
    cell_px: int | None = 4,
) -> dict:
    """A §11-shaped spec carrying only what the card reads: palette, hud, render."""
    palette: dict[str, object] = {"reserved": [1, 2]}
    if you is not None:
        palette["you"] = you
    if goal is not None:
        palette["goal"] = goal
    palette["danger"] = danger
    if background is not None:
        palette["background"] = background
    game: dict[str, object] = {
        "slug": SYNTHETIC_GAME,
        "title": "W1-A2 synthetic",
        "palette": palette,
        "hud": {"reserved": hud_reserved,
                "meter": {"placement": "row63-left", "direction": "shrink-right"}},
    }
    if cell_px is not None:
        game["render"] = {"cell_px": cell_px}
    return {"game": game}


def stage_case(directory: Path, sidecar: Mapping, spec: Mapping) -> Path:
    """One synthetic slot — spec + frames sidecar — inside tmp_path.  Never `out/`."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SPEC_NAME).write_text(
        yaml.safe_dump(dict(spec), sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    (directory / FRAMES_NAME).write_text(
        json.dumps(dict(sidecar), indent=2) + "\n", encoding="utf-8"
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
def build_card(s3_visual):
    builder = getattr(s3_visual, "build_visual_card", None)
    if builder is None:  # pragma: no cover - frozen by contract V-C
        pytest.fail("gen.s3_visual exposes no build_visual_card(spec_dir, cfg)")
    return builder


def _gate_keys(s3_visual) -> tuple[str, ...]:
    keys = getattr(s3_visual, "GATE_KEYS", None)
    if not isinstance(keys, (list, tuple)):
        pytest.fail(
            "gen.s3_visual exposes no GATE_KEYS tuple — it is the closed key set every gate "
            "knob has to join, and the only honest place to read the two new knob names out of"
        )
    return tuple(str(key) for key in keys)


def _resolve_knob(s3_visual, check: str, label: str) -> str:
    for key in _gate_keys(s3_visual):
        if norm_key(key) == check:
            return key
    pytest.fail(
        f"no gate knob in gen.s3_visual.GATE_KEYS spells {label!r}: the closed key set is "
        f"{list(_gate_keys(s3_visual))}.  The contract arms this check from "
        f"config/template.yaml, and a key the block does not know is refused by its own "
        f"unknown-key check, so the knob MUST be in GATE_KEYS"
    )


@pytest.fixture(scope="session")
def win_key(s3_visual) -> str:
    return _resolve_knob(s3_visual, WIN_RENDER, "win-render")


@pytest.fixture(scope="session")
def declared_key(s3_visual) -> str:
    return _resolve_knob(s3_visual, DECLARED_VS_PAINTED, "declared-vs-painted")


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
        f"pattern is `visual_card_mode` / `l1_floor_mode` / `field_index_mode`: a module-level "
        f"`cfg -> 'off'|'record'|'fail'` reader.  Callables whose name mentions the check: "
        f"{[name for name, _ in named] or 'none'}"
    )


@pytest.fixture(scope="session")
def win_mode(s3_visual, win_key: str):
    return _resolve_reader(s3_visual, win_key, WIN_RENDER, "win-render")


@pytest.fixture(scope="session")
def declared_mode(s3_visual, declared_key: str):
    return _resolve_reader(s3_visual, declared_key, DECLARED_VS_PAINTED, "declared-vs-painted")


@pytest.fixture(scope="session")
def gate_cfg(win_key: str, declared_key: str):
    """`{gate: {...}}` with the pre-A2 knobs held where the template has them."""

    def make(*, win: str = DEFAULT_MODE, declared: str = DEFAULT_MODE,
             extra: Mapping | None = None) -> dict:
        gate: dict[str, object] = {
            "visual_card": "record", "l1_color_floor": "record",
            win_key: win, declared_key: declared,
        }
        if extra:
            gate.update(extra)
        return {"gate": gate}

    return make


@pytest.fixture
def win_case(build_card, gate_cfg, tmp_path: Path):
    """Build a card for one (level board, win board) pair.  Returns the win-render block."""

    def make(level_grid, win_grid, *, mode: str = "fail", hud_reserved: str = "row63",
             name: str = "case") -> Mapping:
        spec_dir = stage_case(
            tmp_path / name,
            win_sidecar(level_grid, win_grid) if win_grid is not None
            else no_win_sidecar(level_grid),
            spec_document(hud_reserved=hud_reserved),
        )
        report = build_card(spec_dir, gate_cfg(win=mode))
        return check_block(report, WIN_RENDER, label="win-render")

    return make


# =============================================================================
# PIN 1 — win-render: the four verdicts the contract freezes
# =============================================================================


def test_pin1_a_win_frame_identical_to_the_level_start_fails_when_armed(win_case):
    """convoy-in-the-fog's exhibit, synthesised: the win frame is the level start."""
    board = level_board()
    block = win_case(board, copy_grid(board), name="identical")
    assert verdict(block, label="win-render") is False, (
        "a WIN frame BYTE-IDENTICAL to the last level-start frame passed `win-render`.  "
        "That is convoy-in-the-fog exactly — its win frame is byte-identical to a frame 84 "
        "actions earlier (step-334 ≡ step-418 ≡ final) — and R-04 exists to reject it.  "
        f"block: {dict(block)!r}"
    )


def test_pin1_a_win_frame_that_only_repaints_the_hud_fails_when_armed(win_case):
    """pump-phase's exhibit: 103 of its 183 changed px are the two HUD rows."""
    board = level_board()
    block = win_case(board, hud_only_win(board, "row63"), name="hud-row63")
    assert verdict(block, label="win-render") is False, (
        "a WIN frame that differs from the level start ONLY inside the declared "
        "`hud.reserved` strip passed `win-render`.  The contract's words: the settled WIN "
        "frame must differ legibly OUTSIDE the declared HUD rows — pump-phase's win 'reads "
        f"as an ordinary mid-level frame' precisely because its delta is mostly HUD.  "
        f"block: {dict(block)!r}"
    )


def test_pin1_a_win_frame_that_repaints_the_board_passes_when_armed(win_case):
    """conduit-watch's exhibit: the win flips pips and beacons ACROSS the board."""
    board = level_board()
    win = legible_win(board)
    changed = cell_delta(board, win)
    block = win_case(board, win, name="legible")
    assert verdict(block, label="win-render") is True, (
        f"a WIN frame that repaints {changed} of {BOARD_CELLS_64} board cells — none of them "
        f"in the declared HUD row — failed `win-render`.  The floor is calibrated to PASS "
        f"conduit-watch (10 pips flipped green, beacons 11 -> 14 across the board), so a "
        f"board-wide repaint has to clear it.  block: {dict(block)!r}"
    )


def test_pin1_a_sidecar_with_no_win_record_is_never_a_failure(win_case):
    """The facing-sentinel class: no WIN record ⇒ not-checked, never fail."""
    block = win_case(level_board(), None, name="no-win")
    assert verdict(block, label="win-render") is not False, (
        "a sidecar with NO WIN record was FAILED by `win-render`.  The contract's own edge "
        "case: 'a game whose sidecar lacks a WIN record (facing-sentinel class) ⇒ "
        "not-checked, never fail' — a capture that never won is a missing measurement, not "
        f"an unrendered win.  block: {dict(block)!r}"
    )


def test_pin1_the_no_win_case_says_it_was_not_checked(win_case):
    """`not-checked` is a REPORTED state, the way `HUD_NOT_CHECKED` already is."""
    block = win_case(level_board(), None, name="no-win-said")
    said = is_not_checked(block) or any(
        NO_WIN_TEXT_RE.search(text) for text in strings_in(block)
    )
    assert said, (
        "the win-render block for a sidecar with no WIN record never says so — it offers "
        f"{key_map(block)} and reads {dict(block)!r}.  The module's own precedent is "
        "`hud_strip: 'not-checked (custom-rect)'`: where the geometry is missing the card "
        "says which measurement it declined, rather than reporting a number measured "
        "against a guess"
    )


def test_pin1_mode_off_leaves_no_win_render_verdict_on_the_card(
    build_card, gate_cfg, tmp_path: Path
):
    """`off` is not 'measure and ignore': the check's fields leave the card entirely."""
    board = level_board()
    spec_dir = stage_case(tmp_path / "win-off", win_sidecar(board, copy_grid(board)),
                          spec_document())
    report = build_card(spec_dir, gate_cfg(win="off"))
    assert find(report, WIN_RENDER) is _MISSING, (
        "gate.win-render `off` still wrote a win-render block onto the card.  `off` removes "
        "the check's fields entirely — that is how a card built today reproduces a card "
        "built before the check existed, byte for byte (the `field_index` / "
        f"`role_footprint` precedent).  the card offers {key_map(report)}"
    )


def test_pin1_record_mode_measures_the_same_failure_without_arming_it(win_case):
    """`record` is born-safe: it MEASURES the identical-win defect and cannot reject."""
    board = level_board()
    block = win_case(board, copy_grid(board), mode=DEFAULT_MODE, name="identical-record")
    assert verdict(block, label="win-render") is False, (
        "in `record` mode the identical-win defect was not even measured; `record` and "
        "`fail` measure identically and the mode only decides what the gate may do about it"
    )
    assert mode_of(block, label="win-render") == DEFAULT_MODE, (
        "the card does not record that this run was in `record` mode — the gate runner reads "
        "that field to decide whether a FAIL is allowed to reject"
    )


# =============================================================================
# PIN 2 — the delta is measured OUTSIDE the declared hud.reserved geometry
# =============================================================================
#
# The trap: a check that diffs the WHOLE grid passes any game whose HUD repaints at
# the win, which is 103 of pump-phase's 183 changed px.  A 64-row board cannot spring
# that trap on its own — its longest strip is 64 cells, below the floor the exhibits
# force (> 80 px) — so this board is 512 rows tall with `hud.reserved: col0`.  Its
# HUD strip is 512 cells and its BOARD delta is exactly 0, so a whole-grid diff reads
# 512 changed cells while an honest one reads none.  A floor above 512 px would make
# the pin toothless but can never make it false: the board delta is 0 under every
# reading, absolute or share.


def _tall_case(build_card, gate_cfg, tmp_path: Path, mode: str = "fail") -> Mapping:
    board = level_board(rows=TALL_ROWS)
    win = hud_only_win(board, "col0")
    assert cell_delta(board, win) == TALL_ROWS, "the tall fixture must change the whole strip"
    spec_dir = stage_case(tmp_path / "hud-col0", win_sidecar(board, win),
                          spec_document(hud_reserved="col0"))
    report = build_card(spec_dir, gate_cfg(win=mode))
    return check_block(report, WIN_RENDER, label="win-render")


def test_pin2_a_hud_only_win_fails_even_when_the_strip_dwarfs_the_floor(
    build_card, gate_cfg, tmp_path: Path
):
    block = _tall_case(build_card, gate_cfg, tmp_path)
    assert verdict(block, label="win-render") is False, (
        f"a WIN frame whose ONLY change is {TALL_ROWS} cells of the declared `hud.reserved` "
        f"strip (`col0`) passed `win-render`, with a board delta of exactly 0.  The contract "
        f"freezes the measurement as 'the cell delta OUTSIDE the declared hud.reserved "
        f"geometry (reuse the _strip_cells/_board_cells helpers)' — this is the case a "
        f"whole-grid diff gets wrong.  block: {dict(block)!r}"
    )


DELTA_KEY_RE = re.compile(r"delta|changed|differ|diff", re.IGNORECASE)


def test_pin2_the_recorded_delta_excludes_the_declared_hud_strip(
    build_card, gate_cfg, tmp_path: Path
):
    """The RECORD has to be honest too, not just the verdict."""
    block = _tall_case(build_card, gate_cfg, tmp_path)
    deltas = numbers_under(block, DELTA_KEY_RE)
    assert deltas, (
        f"the win-render block records no measured delta ({key_map(block)}).  Every check in "
        f"this module prints the number beside its floor — `l1_color_floor` writes `colors` "
        f"beside `floor`, `role-footprint` writes `min_component` beside `floor_px` — because "
        f"a verdict whose measurement is invisible cannot be argued with at the review"
    )
    assert any(value == 0 for value in deltas.values()), (
        f"the win-render record reports {deltas!r} for a win whose BOARD delta is 0 and "
        f"whose HUD strip delta is {TALL_ROWS}.  'Compute the cell delta OUTSIDE the "
        f"declared hud.reserved geometry' means the number on the card is the board's, so a "
        f"human reading the record sees 0 — the same 0 that convoy's win frame deserves"
    )


FLOOR_KEY_RE = re.compile(r"floor|threshold|minimum", re.IGNORECASE)
CALIBRATION_RE = re.compile(
    r"convoy|conduit|pump|core[-_ ]?ward|mosaic|measured|calibrat", re.IGNORECASE
)


def test_pin2_the_check_records_its_floor(build_card, gate_cfg, tmp_path: Path):
    board = level_board()
    spec_dir = stage_case(tmp_path / "floor", win_sidecar(board, legible_win(board)),
                          spec_document())
    block = check_block(build_card(spec_dir, gate_cfg(win="fail")), WIN_RENDER,
                        label="win-render")
    assert numbers_under(block, FLOOR_KEY_RE), (
        f"the win-render block states no floor ({key_map(block)}).  The contract: 'fail below "
        f"a floor ... pick the floor from the measured deltas, document the calibration in "
        f"the check's record' — `role-footprint` writes `floor_px` + `floor_source` and "
        f"`l1_color_floor` writes `floor`, and a rejection whose number is invisible cannot "
        f"be argued with"
    )


def test_pin2_the_floor_sits_above_the_eighty_pixel_exhibits(
    build_card, gate_cfg, tmp_path: Path
):
    """Arithmetic the contract states: pump-phase's 80 board px must FAIL."""
    board = level_board()
    spec_dir = stage_case(tmp_path / "floor-value", win_sidecar(board, legible_win(board)),
                          spec_document())
    block = check_block(build_card(spec_dir, gate_cfg(win="fail")), WIN_RENDER,
                        label="win-render")
    floors = numbers_under(block, FLOOR_KEY_RE)
    if not floors:
        pytest.fail("the win-render block states no floor (see the previous pin)")
    for key, value in sorted(floors.items()):
        # AMBIGUITY 2: an absolute cell count, or a share of the board.  Both readings
        # are honest and the contract states the exhibits in px, so both are accepted.
        measured = value * BOARD_CELLS_64 if 0 < value < 1 else value
        assert measured > EXHIBIT_FAIL_PX, (
            f"win-render {key} = {value!r} is {measured} cell(s) of a 64x64 board, at or "
            f"below the {EXHIBIT_FAIL_PX} px the contract requires to FAIL: pump-phase "
            f"changes 80 board px of 4096 (scattered) and pump-flow 80 px including its HUD, "
            f"and both are exhibits the floor must reject.  The floor is picked from the "
            f"measured deltas, between those and conduit-watch's passing win"
        )


def test_pin2_the_check_documents_its_calibration(build_card, gate_cfg, tmp_path: Path):
    board = level_board()
    spec_dir = stage_case(tmp_path / "calibration", win_sidecar(board, legible_win(board)),
                          spec_document())
    block = check_block(build_card(spec_dir, gate_cfg(win="fail")), WIN_RENDER,
                        label="win-render")
    text = " ".join(strings_in(block))
    assert CALIBRATION_RE.search(text), (
        f"the win-render block carries no calibration note: its prose is {text!r}.  'Document "
        f"the calibration in the check's record' — the four exhibits the floor must fail "
        f"({', '.join(EXHIBITS)}) and the one it must pass ({PASSING_EXHIBIT}) are where the "
        f"number came from, and `role-footprint`'s `floor_source` is the house shape for "
        f"saying so on the card"
    )


# =============================================================================
# PIN 3 — declared-vs-painted: from a per-record fact to a card-level verdict
# =============================================================================


def unpainted_sidecar(count: int = 4) -> dict:
    """`you` is declared and painted on NO record — core-ward's you=11 0/10 exhibit."""
    return role_sidecar([level_board(you=False) for _ in range(count)])


def partly_painted_sidecar(count: int = 4) -> dict:
    """`you` is painted on the reset record only — a legitimate state-dependent role."""
    return role_sidecar(
        [level_board(you=True)] + [level_board(you=False) for _ in range(count - 1)]
    )


VIOLATION_KEYS = ("violations", "violationrows", "rows", "neverpainted", "unpainted", "absent")


def violation_rows(block: Mapping) -> list | None:
    """The card-level list of violation rows, however it is spelled."""
    for name in VIOLATION_KEYS:
        found = find(block, name, depth=1)
        if isinstance(found, Sequence) and not isinstance(found, (str, bytes)):
            return list(found)
    return None


def row_names_role(row: object, role: str) -> bool:
    if isinstance(row, str):
        return re.search(rf"\b{role}\b", row) is not None
    if isinstance(row, Mapping):
        return any(
            (isinstance(value, str) and re.search(rf"\b{role}\b", value))
            for value in row.values()
        ) or any(norm_key(key) == role for key in row)
    return False


def test_pin3_a_role_absent_from_every_record_is_a_violation_when_armed(
    build_card, gate_cfg, tmp_path: Path
):
    spec_dir = stage_case(tmp_path / "never-painted", unpainted_sidecar(), spec_document())
    block = check_block(build_card(spec_dir, gate_cfg(declared="fail")), DECLARED_VS_PAINTED,
                        label="declared-vs-painted")
    assert verdict(block, label="declared-vs-painted") is False, (
        "a DECLARED `palette.you` painted on NO record passed `declared-vs-painted`.  The "
        "contract: 'a declared role index (you/goal/danger) absent from EVERY record = a "
        "violation row'.  The measured exhibits are core-ward you=11 0/10, conduit you=12 "
        f"0/10 and mosaic you=11 0/5.  block: {dict(block)!r}"
    )


def test_pin3_the_violation_row_names_the_role(build_card, gate_cfg, tmp_path: Path):
    spec_dir = stage_case(tmp_path / "rows", unpainted_sidecar(), spec_document())
    block = check_block(build_card(spec_dir, gate_cfg(declared="fail")), DECLARED_VS_PAINTED,
                        label="declared-vs-painted")
    rows = violation_rows(block)
    assert rows, (
        f"the declared-vs-painted block carries no list of violation ROWS ({key_map(block)}).  "
        f"The contract says 'a violation row' and then asks the REVIEW REQUIRED block to name "
        f"'the violation rows ... so a human reviewer sees the list at the stop' — a verdict "
        f"with no rows gives that print nothing to say.  block: {dict(block)!r}"
    )
    assert any(row_names_role(row, "you") for row in rows), (
        f"the violation rows {rows!r} never name the offending role `you`.  A row a reviewer "
        f"cannot act on is the defect R-06 exists to fix — these facts are ALREADY on the M-1 "
        f"cards and were never acted on"
    )


def test_pin3_a_role_absent_from_only_some_records_is_recorded_not_violated(
    build_card, gate_cfg, tmp_path: Path
):
    spec_dir = stage_case(tmp_path / "partly-painted", partly_painted_sidecar(), spec_document())
    block = check_block(build_card(spec_dir, gate_cfg(declared="fail")), DECLARED_VS_PAINTED,
                        label="declared-vs-painted")
    assert verdict(block, label="declared-vs-painted") is not False, (
        "a DECLARED role painted on SOME records and absent from others was made a violation.  "
        "The contract: 'absent from only some records = recorded, never a violation "
        "(state-dependent roles are legitimate)' — core-ward-phase-gates paints `you` only "
        f"after the first click and that game was human-ACCEPTED.  block: {dict(block)!r}"
    )
    rows = violation_rows(block) or []
    assert not any(row_names_role(row, "you") for row in rows), (
        f"a partly-painted `you` still produced a violation row: {rows!r}.  It is recorded, "
        f"never a violation"
    )


def test_pin3_mode_off_leaves_no_declared_vs_painted_verdict(
    build_card, gate_cfg, tmp_path: Path
):
    spec_dir = stage_case(tmp_path / "declared-off", unpainted_sidecar(), spec_document())
    report = build_card(spec_dir, gate_cfg(declared="off"))
    assert find(report, DECLARED_VS_PAINTED) is _MISSING, (
        "gate.declared-vs-painted `off` still wrote a verdict onto the card.  `off` adds "
        "NOTHING — the per-record `declared_absent` facts stay exactly as they were, because "
        f"they shipped before this check existed.  the card offers {key_map(report)}"
    )


def test_pin3_record_mode_records_the_violation_without_arming_it(
    build_card, gate_cfg, tmp_path: Path
):
    spec_dir = stage_case(tmp_path / "declared-record", unpainted_sidecar(), spec_document())
    block = check_block(build_card(spec_dir, gate_cfg(declared=DEFAULT_MODE)),
                        DECLARED_VS_PAINTED, label="declared-vs-painted")
    assert verdict(block, label="declared-vs-painted") is False, (
        "in `record` mode the never-painted role was not measured; `record` and `fail` "
        "measure identically and only the mode decides what the gate may do about it"
    )
    assert mode_of(block, label="declared-vs-painted") == DEFAULT_MODE, (
        "the card does not record that this run was in `record` mode"
    )


R20_RE = re.compile(r"\bR[-_ ]?20\b", re.IGNORECASE)


def test_pin3_the_check_cites_the_r20_capture_dependency(
    build_card, gate_cfg, tmp_path: Path
):
    """The honesty clause: this check cannot see a role painted between settled frames."""
    spec_dir = stage_case(tmp_path / "r20", unpainted_sidecar(), spec_document())
    block = check_block(build_card(spec_dir, gate_cfg(declared="fail")), DECLARED_VS_PAINTED,
                        label="declared-vs-painted")
    in_block = any(R20_RE.search(text) for text in strings_in(block))
    in_source = bool(R20_RE.search(S3_VISUAL_SOURCE.read_text(encoding="utf-8")))
    assert in_block or in_source, (
        "neither the declared-vs-painted record nor gen/s3_visual.py mentions R-20.  The "
        "contract makes the limit load-bearing: 'some mismatches are capture-scope artifacts "
        "— conduit's palette.you IS painted by code but appears in no settled frame because "
        "every record is a fresh/finished board.  Until the R-20 capture upgrade, the check "
        "CANNOT distinguish \"never painted in any frame\" from \"never painted by any code "
        "path\"' — and asks for that dependency in the check's doc line"
    )


# --- the declared-exception surface (discovered, not guessed) -----------------

EXEMPTION_NAME_FALLBACKS = (
    "declared_vs_painted_exempt", "declared_vs_painted_exemptions", "declared_exempt",
    "declared_absent_exempt", "unpainted_exempt", "transient_roles", "exempt_roles",
)

# The vocabulary the contract leaves the surface free to use.  It asks for "a config
# exemption naming role+game rationale, smallest honest design", so every shape below
# names the role, and most name the game and carry a rationale; the bare-role shapes
# are the smallest reading of "smallest honest design".
RICH_EXEMPTIONS: tuple[object, ...] = (
    [f"{SYNTHETIC_GAME}:you"],
    [f"{SYNTHETIC_GAME}:you: {RATIONALE}"],
    {f"{SYNTHETIC_GAME}:you": RATIONALE},
    {SYNTHETIC_GAME: {"you": RATIONALE}},
    {SYNTHETIC_GAME: ["you"]},
    [{"game": SYNTHETIC_GAME, "role": "you", "rationale": RATIONALE}],
    [{"game": SYNTHETIC_GAME, "role": "you", "reason": RATIONALE}],
    [{"game_id": SYNTHETIC_GAME, "role": "you", "why": RATIONALE}],
    [{"role": "you", "rationale": RATIONALE}],
    [f"{SYNTHETIC_GAME}.you"],
    [f"{SYNTHETIC_GAME}/you"],
    ["you"],
    {"you": RATIONALE},
)
BASIC_EXEMPTIONS: tuple[object, ...] = (
    [f"{SYNTHETIC_GAME}:you"],
    [f"{SYNTHETIC_GAME}:you: {RATIONALE}"],
    ["you"],
)


def exemption_attempts(s3_visual, base_gate: Mapping, known: tuple[str, ...]):
    """Every config shape that might declare `you` a legitimately transient role.

    The extra `GATE_KEYS` entries come first and get the whole vocabulary: they are
    the module's OWN declaration of what a gate config may carry, so a surface that
    exists at all is almost certainly one of them.  The conventional names are a
    fallback and get the basic shapes only.
    """
    declared = [key for key in _gate_keys(s3_visual) if key not in known]
    for key in declared:
        for value in RICH_EXEMPTIONS:
            yield f"gate.{key} = {value!r}", {"gate": {**base_gate, key: value}}
    for key in (name for name in EXEMPTION_NAME_FALLBACKS if name not in declared):
        for value in BASIC_EXEMPTIONS:
            yield f"gate.{key} = {value!r}", {"gate": {**base_gate, key: value}}
            yield f"{key} = {value!r} (config top level)", {"gate": dict(base_gate), key: value}


def test_pin3_a_declared_exemption_silences_a_named_role_and_game(
    s3_visual, build_card, gate_cfg, win_key: str, declared_key: str, tmp_path: Path
):
    """The conduit-class escape hatch, DISCOVERED (see the module docstring)."""
    spec_dir = stage_case(tmp_path / "exemption", unpainted_sidecar(), spec_document())
    armed = gate_cfg(declared="fail")
    block = check_block(build_card(spec_dir, armed), DECLARED_VS_PAINTED,
                        label="declared-vs-painted")
    assert verdict(block, label="declared-vs-painted") is False, (
        "the un-exempted never-painted `you` must fail before this pin means anything"
    )

    known = (*PRE_A2_GATE_KEYS, win_key, declared_key)
    refused: list[str] = []
    ignored: list[str] = []
    for label, cfg in exemption_attempts(s3_visual, armed["gate"], known):
        try:
            report = build_card(spec_dir, cfg)
        except Exception as exc:  # noqa: BLE001 — a shape this config does not offer
            refused.append(f"{label} -> {type(exc).__name__}: {exc}")
            continue
        found = find(report, DECLARED_VS_PAINTED)
        if not isinstance(found, Mapping):
            ignored.append(f"{label} -> the card reported no declared-vs-painted block")
            continue
        if verdict(found, label="declared-vs-painted") is not False:
            return
        ignored.append(f"{label} -> accepted, still failing")
    pytest.fail(
        "no config surface silences declared-vs-painted for a DECLARED transient role.  R-06 "
        "requires one — 'provide a declared-exception surface (config exemption naming "
        "role+game rationale, smallest honest design) for the transient-by-design case "
        "(conduit's selection color)' — because until the R-20 capture upgrade this check "
        "cannot tell a role that is never painted from one that is never CAPTURED, and "
        "conduit-watch's `you` is the measured example of the second.\n"
        f"gen.s3_visual.GATE_KEYS: {list(_gate_keys(s3_visual))}\n"
        f"ACCEPTED but did not silence it ({len(ignored)}):\n  " + "\n  ".join(ignored)
        + f"\nREFUSED by the config block ({len(refused)}):\n  " + "\n  ".join(refused[:20])
    )


# =============================================================================
# PIN 4 — the knobs, and the gate wiring that acts on them
# =============================================================================


def test_pin4_both_checks_are_born_in_record_mode(win_mode, declared_mode):
    assert win_mode({}) == DEFAULT_MODE, (
        "a config with no gate block must leave win-render in `record`.  House convention: "
        "mode knobs off|record|fail default RECORD and are armed in template.yaml — a new "
        "rejection earns its place on measured data, not on the day it is written"
    )
    assert declared_mode({}) == DEFAULT_MODE, (
        "a config with no gate block must leave declared-vs-painted in `record`"
    )


def test_pin4_an_empty_gate_block_is_the_same_as_no_gate_block(win_mode, declared_mode):
    assert win_mode({"gate": {}}) == DEFAULT_MODE
    assert declared_mode({"gate": {}}) == DEFAULT_MODE


@pytest.mark.parametrize("mode", CHECK_MODES)
def test_pin4_every_win_render_mode_parses(mode: str, win_mode, win_key: str):
    assert win_mode({"gate": {win_key: mode}}) == mode, (
        f"gate.{win_key}: {mode!r} did not round-trip; the contract freezes the enum as "
        f"{list(CHECK_MODES)}"
    )


@pytest.mark.parametrize("mode", CHECK_MODES)
def test_pin4_every_declared_vs_painted_mode_parses(mode: str, declared_mode, declared_key: str):
    assert declared_mode({"gate": {declared_key: mode}}) == mode, (
        f"gate.{declared_key}: {mode!r} did not round-trip; the contract freezes the enum as "
        f"{list(CHECK_MODES)}"
    )


@pytest.mark.parametrize("bad", BAD_MODES)
def test_pin4_a_win_render_value_outside_the_enum_is_loud(bad: str, win_mode, win_key: str):
    with pytest.raises(ValueError):
        win_mode({"gate": {win_key: bad}})


@pytest.mark.parametrize("bad", BAD_MODES)
def test_pin4_a_declared_value_outside_the_enum_is_loud(bad: str, declared_mode, declared_key: str):
    with pytest.raises(ValueError):
        declared_mode({"gate": {declared_key: bad}})


def test_pin4_both_new_knobs_joined_the_closed_gate_key_set(s3_visual, win_key, declared_key):
    keys = _gate_keys(s3_visual)
    for name in (*PRE_A2_GATE_KEYS, win_key, declared_key):
        assert name in keys, f"GATE_KEYS lost {name!r}: {list(keys)}"
    with pytest.raises(ValueError):
        # The block stays CLOSED: two new knobs are two new keys, not an open door.
        s3_visual.visual_card_mode({"gate": {win_key: "record", "visual-card": "fail"}})


def test_pin4_both_checks_appear_on_the_card_beside_the_existing_visual_records(
    build_card, tmp_path: Path
):
    """Defaults record, and the new blocks sit beside `l1_color_floor` on the same card."""
    board = level_board()
    spec_dir = stage_case(tmp_path / "beside", win_sidecar(board, legible_win(board)),
                          spec_document())
    report = build_card(spec_dir, {"gate": {"visual_card": "record"}})
    for token, label in ((WIN_RENDER, "win-render"), (DECLARED_VS_PAINTED, "declared-vs-painted")):
        block = check_block(report, token, label=label)
        assert mode_of(block, label=label) == DEFAULT_MODE, (
            f"{label} is not in `record` on a config that arms nothing — it reports "
            f"{mode_of(block, label=label)!r}"
        )
    assert isinstance(find(report, "l1colorfloor"), Mapping), (
        "the pre-existing `l1_color_floor` block left the card; the two new checks join the "
        "visual records, they do not replace them"
    )


def _wiring_source() -> str:
    """R-06 says s3_gate.py, the pre-A2 tree wires the card in orchestrator.py (AMBIGUITY 7)."""
    return "\n".join(
        path.read_text(encoding="utf-8") for path in (S3_GATE_SOURCE, ORCHESTRATOR_SOURCE)
    )


def check_id_tokens(s3_visual, token: str, dashed: str) -> list[str]:
    """Every spelling the wiring could name this check by: constant names, then literals."""
    names = [
        name for name, value in sorted(vars(s3_visual).items())
        if isinstance(value, str) and norm_key(value) == token
    ]
    return [*names, dashed, dashed.replace("-", "_")]


@pytest.mark.parametrize(
    ("token", "dashed"),
    ((WIN_RENDER, "win-render"), (DECLARED_VS_PAINTED, "declared-vs-painted")),
    ids=("win-render", "declared-vs-painted"),
)
def test_pin4_the_gate_closure_consults_the_new_check(
    token: str, dashed: str, s3_visual, win_mode, declared_mode
):
    """The seam the phase-1 contract had to leave open: a `fail` arm nothing reads is decoration."""
    source = _wiring_source()
    reader = win_mode if token == WIN_RENDER else declared_mode
    reader_name = getattr(reader, "__name__", "")
    assert reader_name and reader_name in source, (
        f"neither gen/s3_gate.py nor gen/orchestrator.py ever calls {reader_name or dashed!r}.  "
        f"The contract wires the verdict in 'beside visual_card/l1_color_floor (same "
        f"knob-gating pattern)', which on this tree is the `for check_key, mode in ((...))` "
        f"loop in the orchestrator's `s3_gate` stage — without it the template's `fail` arm "
        f"is decoration, the exact defect class R-06 exists to kill"
    )
    candidates = check_id_tokens(s3_visual, token, dashed)
    assert any(name in source for name in candidates), (
        f"the gate wiring never names the {dashed!r} check (tried {candidates}).  The "
        f"rejection reason has to name the rule, the way `f\"visual {{check_key}}\"` already "
        f"does, so the ledger line says which check stopped the game"
    )


def test_pin4_the_wiring_keeps_the_phase_one_checks(win_mode, declared_mode):
    """A2 joins the seam phase 1 built; it does not take it over."""
    source = _wiring_source()
    for name in ("FIELD_INDEX_CHECK", "ROLE_FOOTPRINT_CHECK",
                 "field_index_mode", "role_footprint_mode", "l1_floor_mode"):
        assert name in source, (
            f"the gate wiring lost {name!r} — the W1-A1 checks and the l1 color floor are "
            f"still wired, and this contract adds to that loop rather than replacing it"
        )
    assert getattr(win_mode, "__name__", "") in source
    assert getattr(declared_mode, "__name__", "") in source


# =============================================================================
# PIN 5 — the REVIEW REQUIRED stop lists the violation rows
# =============================================================================


def _orchestrator_module():
    from gen import orchestrator

    return orchestrator


def _helper_sources(module, block: str) -> str:
    """`block` plus the source of every module-level function it names.

    The contract asks for the rows at the stop 'one line per game, like the visual
    card line does today', and today's line is `_visual_report(spec_dirs.get(slug))`
    — a module-level helper called from the loop.  So the pin reads the loop AND
    whatever it calls, and never insists on where the string lives.
    """
    parts = [block]
    for name in sorted(set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", block))):
        candidate = getattr(module, name, None)
        if inspect.isfunction(candidate) and candidate.__module__ == module.__name__:
            try:
                parts.append(inspect.getsource(candidate))
            except OSError:  # pragma: no cover - source always available from disk
                continue
    return "\n".join(parts)


def _pending_review_block() -> tuple[str, str]:
    """(the `for slug in pending:` loop + its helpers, the whole of `main` + its helpers)."""
    module = _orchestrator_module()
    main_source = inspect.getsource(module.main)
    lines = main_source.splitlines()
    start = next(
        (index for index, line in enumerate(lines)
         if re.match(r"\s*for\s+\w+\s+in\s+.*pending", line)),
        None,
    )
    whole = _helper_sources(module, main_source)
    if start is None:
        return "", whole
    indent = len(lines[start]) - len(lines[start].lstrip())
    block = [lines[start]]
    for line in lines[start + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        block.append(line)
    return _helper_sources(module, "\n".join(block)), whole


VIOLATION_WORD_RE = re.compile(r"violation|unpainted|never.{0,12}painted|declared", re.IGNORECASE)


def test_pin5_the_review_required_stop_names_the_violation_rows(s3_visual):
    loop_source, main_source = _pending_review_block()
    assert "REVIEW REQUIRED" in main_source, (
        "gen/orchestrator.py's `main` no longer prints a REVIEW REQUIRED block — that stop is "
        "where the contract puts the violation rows"
    )
    assert loop_source, (
        "gen/orchestrator.py's `main` has no `for slug in pending:` loop to hang the rows on; "
        "the REVIEW REQUIRED block is printed once per pending slug and the contract asks for "
        "'one line per game, like the visual card line does today'"
    )
    candidates = check_id_tokens(s3_visual, DECLARED_VS_PAINTED, "declared-vs-painted")
    where = "the REVIEW REQUIRED loop" if any(name in loop_source for name in candidates) else (
        "elsewhere in main()" if any(name in main_source for name in candidates) else "nowhere"
    )
    assert where == "the REVIEW REQUIRED loop", (
        f"the REVIEW REQUIRED stop never names the declared-vs-painted rows (found: {where}; "
        f"tried {candidates}).  The contract: 'the REVIEW REQUIRED block names the violation "
        f"rows (one line per game, like the visual card line does today) so a human reviewer "
        f"sees the list at the stop' — these facts were ALREADY on every M-1 card and were "
        f"never acted on, which is the whole of R-06"
    )
    assert VIOLATION_WORD_RE.search(loop_source), (
        "the REVIEW REQUIRED loop names the check but never calls the rows what they are; the "
        "line a reviewer reads has to say a declared role was never painted"
    )


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


@pytest.mark.parametrize("check", ("win", "declared"), ids=("win-render", "declared-vs-painted"))
def test_pin6_the_template_arms_the_check_as_fail(check: str, win_key: str, declared_key: str):
    key = win_key if check == "win" else declared_key
    gate = _template_tree().get("gate")
    assert isinstance(gate, dict), f"config/template.yaml has no `gate:` block, got {gate!r}"
    assert gate.get(key) == "fail", (
        f"config/template.yaml has gate.{key} = {gate.get(key)!r}; the contract arms it as "
        f"`fail` (both checks are born in `record` in CODE and armed in the TEMPLATE only — "
        f"the split the house convention names)"
    )


def _extended_readers(win_mode, declared_mode, win_key: str, declared_key: str) -> dict:
    """`test_docs_template._readers()` plus this contract's two — imported, never copied."""
    readers = dict(_readers())
    readers[f"s3_visual.{getattr(win_mode, '__name__', win_key)}"] = win_mode
    readers[f"s3_visual.{getattr(declared_mode, '__name__', declared_key)}"] = declared_mode
    return readers


def test_pin6_the_reader_roster_grew_by_exactly_the_two_new_knobs(
    win_mode, declared_mode, win_key: str, declared_key: str
):
    readers = _extended_readers(win_mode, declared_mode, win_key, declared_key)
    assert len(readers) == len(_readers()) + 2, (
        f"the extended roster is {len(readers)} readers, not {len(_readers())} + 2 — the two "
        f"new mode readers collided with a name already on test_docs_template's table: "
        f"{sorted(readers)}"
    )


def test_pin6_every_knob_reader_accepts_the_armed_template(
    template_cfg: dict, win_mode, declared_mode, win_key: str, declared_key: str
):
    """The whole roster in one pass, so a close can be sequenced from one run."""
    failures = []
    roster = _extended_readers(win_mode, declared_mode, win_key, declared_key)
    for name, reader in sorted(roster.items()):
        try:
            reader(template_cfg)
        except Exception as exc:  # noqa: BLE001 — collected, not swallowed
            failures.append(f"  {name}: {type(exc).__name__}: {exc}")
    assert not failures, (
        f"{len(failures)} config readers rejected the armed config/template.yaml:\n"
        + "\n".join(failures)
        + "\nA gate block is key-CLOSED: arming a knob the readers do not know turns every "
        "stage that reads the gate into a loud crash, one batch too late"
    )


@pytest.mark.parametrize("check", ("win", "declared"), ids=("win-render", "declared-vs-painted"))
def test_pin6_the_armed_template_round_trips_through_its_own_reader(
    check: str, template_cfg: dict, win_mode, declared_mode
):
    reader = win_mode if check == "win" else declared_mode
    assert reader(template_cfg) == "fail", (
        f"the template arms this check but its reader returns {reader(template_cfg)!r} — the "
        f"knob in the yaml and the knob the code reads are not the same key"
    )


def _template_comments() -> str:
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if line.lstrip().startswith("#"))


@pytest.mark.parametrize("word", ("win-render", "declared-vs-painted"))
def test_pin6_the_template_documents_both_checks_in_a_comment(word: str):
    comments = _template_comments()
    assert word in comments or word.replace("-", "_") in comments, (
        f"config/template.yaml arms a check it never explains: no comment mentions {word!r}.  "
        f"Every other knob in that file carries the measurement that justifies it, and the "
        f"contract asks for both of these 'commented'"
    )


def test_pin6_the_template_documents_the_conduit_class_exemption():
    comments = norm_text(_template_comments())
    assert "conduit" in comments and "exempt" in comments, (
        "config/template.yaml never documents the conduit-class exemption.  The contract: "
        "'arm `declared_vs_painted: fail` with the conduit-class exemption documented in "
        "comments' — conduit's `palette.you` IS painted by code and appears in no settled "
        "frame, so a reviewer reading the armed knob has to be told which silence is a "
        "capture artifact and which is a defect"
    )
