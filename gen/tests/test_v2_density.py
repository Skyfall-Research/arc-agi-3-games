"""Blind pins for FROZEN CONTRACT T-1 — the t1 density band (guidance + card check).

Run: .venv/bin/python -m pytest gen/tests/test_v2_density.py -v

Written from ``docs/v2/contracts/T-1-t1-density-band.md`` ALONE (its "Blind lane"
section, pins B1-B4) by a separate agent while the implementer's change was in
progress. NOT read: the implementer's diff, their ``gen/tests/test_t1_density.py``,
or any uncommitted change to ``gen/s1_spec.py`` / ``gen/s2_implement.py`` /
``gen/s3_visual.py`` / ``gen/visual_canon.py`` / ``config/template.yaml``. Studied
off the COMMITTED tree only (``git show HEAD:``): the visual card's check shapes
(R-01 ``field-index``, R-02 ``role-footprint``, R-03 ``chrome-extent``), the closed
``gate:`` key set and its loud enum readers, the orchestrator's ``s3_gate`` runner
and its ``visual <check>`` fail loop, ``s2_implement.build_payload``, the tier
carriers (``idea.json`` ``tier`` — what ``s1_spec._idea_tier`` reads — and P-A.3's
promoted ``game.tier``), and the card-driving rigs of ``test_w1_winrender.py`` /
``test_l1_leniency.py``.

WHAT THE CONTRACT IS FOR. The parity re-measure (2026-10-06) put the officials'
per-level median ``objects_pcc`` at 47.0 and our five t1 games at 12.0-31.5
(0.26x-0.67x) on both driver lanes, with the one t2 game in band (56.0). The S2
payload's density guidance was tier-blind and the visual card recorded object
counts with no band. T-1 adds a tier-aware density sentence to the payload and a
``density`` row on the card, banded at the officials' measured p25, under a
``gate.density`` knob that defaults to ``record`` and rejects only under ``fail``.

BLIND NAME RESOLUTION. Nothing private is guessed.

* ``gate.density`` is FROZEN by the contract and typed here.
* The card row is found by normalised key ``density`` at the card's top level
  (or one mapping in), and read through its ``passed`` / ``mode`` face — the
  face every committed card check (and the orchestrator's fail loop) uses.
* THE FLOOR IS QUOTED AT RUNTIME off the card's own ``density`` row (B2's rule:
  never a copy of the number typed here). Separately, and only as an independent
  cross-check of the derivation, the officials' p25 and median are MEASURED in
  this file off ``audit/comparative/data/level-metrics.csv`` — the file the
  contract names — with a check that every standard quantile method agrees.
* The tier is staged on EVERY carrier the committed tree has: ``idea.json``'s
  ``tier`` beside the spec, ``game.tier`` in ``spec.yaml``, and any builder
  parameter whose name contains ``tier``. The template config (which carries a
  ``tiers:`` block, so a policy-gated tier reader has its policy) is the base cfg.
  Because ``game.tier`` is written ONLY by a P-A.3 promotion, the production shape
  of an unpromoted slot (``idea.json`` alone) is pinned separately on the card, the
  payload and the gate runner — a band armed only by a label most specs lack would
  pass every both-carrier pin and never fire in a real batch.
* The board metric is the contract's: ``objects_pcc`` = per-colour 4-connected
  components INCLUDING the background (the officials' published definition,
  ``audit_common.pcc_stats``), re-implemented independently below and used to
  self-check every fixture board.

AMBIGUITIES, each restated at its pin:

* **"flags on the card"** is read as the row's ``passed`` being ``False`` (the
  committed precedent: ``field-index`` / ``chrome-extent`` measure the same verdict
  in ``record`` and ``fail``, and the mode only decides whether the gate acts).
* **"fail rejects"** is pinned at the gate itself: the orchestrator's real
  ``s3_gate`` runner is driven with only its engine-touching seams stubbed (the
  capture, the merged gate, the B3 gate checks), the REAL card built from the
  fixture sidecar, and a rig CONTROL (``field_index: fail`` on a white field)
  proving the rig reaches the visual fail loop on any tree.
* **"one at the officials' median passes"** — the median is the officials'
  per-level 47 (measured here), drawn as a 47-``objects_pcc`` board on every level.
* **"per-level median"** is read as the median, over the game's level-START
  boards, of each board's ``objects_pcc``. Every fixture is built so that reading
  and an every-record reading reach one verdict.
* **"shipped-report validation unchanged (additive/optional)"** has no schema
  validator to call in the committed tree (cards are read by the gate loop, the
  stop printers and ``m1_metrics.build_cards``). It is pinned as: (a) a card built
  by the pre-T-1 module (``git show`` of the pre-T-1 commit, loaded into a tmp
  file) is a deep SUBSET of the post-T-1 card on the same fixture; (b) the
  ``density`` knob changes nothing on the card outside its own row; (c) a slot
  with no tier carrier at all (the shape ``m1_metrics.build_cards`` copies:
  ``spec.yaml`` + sidecar only) still builds, under the template and under a
  historical config with no ``tiers:`` block; (d) a card with the row stripped
  still renders.
* **B4's "explicit"** is read as: the ``density`` row names the tier it judged at
  (a ``t1``/``t2``/``t3`` token, or a ``tier``/``scope`` key), and at t2/t3 the
  same under-floor board either does not flag (t1-scoped) or is judged against a
  different floor (tier-scaled). A row ABSENT at t2/t3 counts as t1-scoped only
  if the t1 row itself names its tier.
* **B4 on the payload** is judged per heading-delimited SECTION, not per paragraph:
  a paragraph that only states the officials' measurement is a fact, and the scope
  of the rule it supports is stated in its section (heading or body).
* **The payload guidance** is located by content, not by heading: a paragraph
  carrying density wording, the runtime floor and a percentile/median/t1 cue,
  whose +-1-paragraph window also states the officials' median, names t1, and
  says simplicity is mechanical, not sparse. (The bare number alone cannot be
  the anchor: "25" is also the officials' game count, which the committed
  corpus-numbers card already prints beside the word "density".)

HYGIENE: tmp roots only. No driver, no network, no API call, no engine drive (the
two engine-touching gate seams are stubbed). Nothing under the real ``out/`` or
``games/`` is read or written; ``canon/`` and the audit CSV are read-only;
``../duckWM`` is never touched.
"""

from __future__ import annotations

import copy
import csv
import importlib.util
import inspect
import json
import re
import shutil
import statistics
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path

import pytest
import yaml

from gen.config import REPO_ROOT, load_config

# --- locations ----------------------------------------------------------------

ROOT = Path(REPO_ROOT)
TESTS_DIR = Path(__file__).resolve().parent
CONTRACT_DOC = "docs/v2/contracts/T-1-t1-density-band.md"
LEVEL_METRICS_CSV = ROOT / "audit" / "comparative" / "data" / "level-metrics.csv"
TEMPLATE_PATH = ROOT / "config" / "template.yaml"
CONFIG_DIR = ROOT / "config"
GOOD_SPEC = TESTS_DIR / "fixtures" / "specs" / "good-spec.yaml"
IDEA_FIXTURE = TESTS_DIR / "fixtures" / "specs" / "idea-001.json"

# The last commit before T-1 (the cleanup wave, "suite 4342+1"). B3's additive pin
# loads `gen/s3_visual.py` AS IT STOOD THERE, so the comparison never decays into
# post-T-1-against-itself once T-1 is committed.
PRE_T1_COMMIT = "23e7392848b1dfd486373036de551ee7ba2d169b"

# --- the contract's frozen surface ------------------------------------------

KNOB = "density"          # `gate.density` — typed by the contract itself
ROW = "density"           # "a `density` row on the visual card"
RECORD, FAIL = "record", "fail"
BAD_MODES = ("warn", "Record", "record ", "on", "true", "")
UPPER_TIERS = ("t2", "t3")
OFFICIAL_LEVELS = 183     # the parity re-measure's population: "officials (183 levels)"

B1 = ("B1 a fixture board under the floor flags on the card; one at the officials' median "
      "passes; the knob matrix (absent/record both never reject; fail rejects).")
B2 = ("B2 the payload carries the tier-aware density guidance with a NUMBER in it, and that "
      "number equals the code's constant (quote the constant at runtime, never hardcode your "
      "own copy).")
B3 = "B3 shipped-report validation unchanged (the new card row is additive/optional)."
B4 = ("B4 t2+ tiers: the band is t1-scoped (or tier-scaled — whichever the implementer "
      "chooses, it must be explicit; probe defensively and fail loudly quoting this clause if "
      "neither is detectable).")
WORK1 = ("Work 1, PAYLOAD GUIDANCE: \"a tier-aware density sentence stating the officials' own "
         "figures (median 47 objects_pcc per level; p25 — MEASURE it off "
         "audit/comparative/data/level-metrics.csv and quote the measured number, never a "
         "guess) and that t1 SIMPLICITY is mechanical (fewer rules), not visual sparseness. "
         "Prompt-sync discipline: the number appears once in code, quoted into the payload.\"")
WORK2 = ("Work 2, THE CARD BAND: \"a `density` row on the visual card — per-level median "
         "objects_pcc against the officials' band (floor = the officials' p25, measured and "
         "named in the code with its derivation). Severity knob like every card check: "
         "`gate.density: record` default-absent = record; `fail` arms rejection. The card "
         "prints the measured value beside the band either way (the R-01/R-02 card idiom).\"")

# The committed (pre-T-1) card check knobs, every one forced to `record` in the
# gate-runner rig so that ONLY `density` (or the control) can stop the fixture.
QUIET_GATE = {
    "visual_card": RECORD, "l1_color_floor": RECORD, "field_index": RECORD,
    "role_footprint": RECORD, "win_render": RECORD, "declared_vs_painted": RECORD,
    "chrome_extent": RECORD, "danger_visible": RECORD,
}

_ABSENT = object()

# --- the fixture boards ----------------------------------------------------------
# 64x64, the ARC camera every committed card metric assumes. A painted field (5,
# affordance §9's background default, declared as `palette.background`) with
# non-touching 2x2 squares in the declared role colours: each square is exactly one
# per-colour component, and the field stays ONE component, so a board drawn with
# `n` objects has objects_pcc == n by construction (and `pcc()` re-checks it).
# Every square sits in rows/cols 4-57, so row 0, row 63 and col 0 — the strips the
# card can locate — stay uniform field.

GRID = 64
BG = 5
YOU, GOAL, DANGER, EXTRA = 9, 14, 8, 12
SQUARE_COLOURS = (YOU, GOAL, DANGER, EXTRA)
SLOT_ORIGINS = tuple((4 + 4 * row, 4 + 4 * col) for row in range(14) for col in range(14))
WHITE = 0

# Object counts, chosen with margin against BOTH plausible readings of "the
# officials' p25" (per-level 25, the contract's; per-game-median 28, the reading
# the derivation pin below rejects) so a fixture's verdict never hinges on which.
UNDER = 11          # well under the floor
BETWEEN = 30        # over the floor, under the median
HIGH = 188          # far over the median

GAME_ID = "t1-density-blind"
IDEA_CARRIER, SPEC_CARRIER = "idea", "spec"
BOTH_CARRIERS = (IDEA_CARRIER, SPEC_CARRIER)
PRODUCTION_CARRIER = (IDEA_CARRIER,)   # an unpromoted slot: S1's idea.json copy only
LIVE, WIN = "NOT_FINISHED", "WIN"

SPEC_MD = """# T-1 blind synthetic — prose spec

MARKER-T1-BLIND-PROSE: belts carry coloured crates past cycleable junctions toward
pads of matching colour.
"""

# --- payload text probes -----------------------------------------------------------

DENSITY_RE = re.compile(r"densit|objects?_pcc|objects? per level|per-level object", re.IGNORECASE)
CUE_RE = re.compile(r"p25|25th|percentile|quartile|\bfloor\b", re.IGNORECASE)
T1_RE = re.compile(r"\bt1\b|\btier[ -]?1\b|\bentry[ -]tier\b", re.IGNORECASE)
TIER_TOKEN_RE = re.compile(r"\bt[123]\b|\btier\b", re.IGNORECASE)
MECHANIC_RE = re.compile(r"mechani|fewer rules", re.IGNORECASE)
SPARSE_RE = re.compile(r"spars|\bempt|\bbare\b|\bthin\b", re.IGNORECASE)

PASS_WORDS = {"pass", "passed", "ok", "clean", "in-band", "inband"}
FAIL_WORDS = {"fail", "failed", "flag", "flagged", "below", "below-band", "violation"}
UNJUDGED_WORDS = {"not-checked", "notchecked", "not-applicable", "n/a", "skipped",
                  "out-of-scope", "unscoped", "exempt"}


# =============================================================================
# measurement helpers (independent of the implementation)
# =============================================================================


def official_objects_pcc() -> list[float]:
    """The officials' per-level `objects_pcc` column, read off the contract's CSV."""
    with LEVEL_METRICS_CSV.open(newline="", encoding="utf-8") as handle:
        return [float(row["objects_pcc"]) for row in csv.DictReader(handle)
                if row["corpus"] == "official"]


def linear_quantile(values: Sequence[float], q: float) -> float:
    """numpy's default (linear) quantile, hand-rolled."""
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def pcc(grid: Sequence[Sequence[int]]) -> int:
    """objects_pcc — per-colour 4-connected components, background INCLUDED."""
    height, width = len(grid), len(grid[0])
    seen = [[False] * width for _ in range(height)]
    count = 0
    for y in range(height):
        for x in range(width):
            if seen[y][x]:
                continue
            count += 1
            colour = grid[y][x]
            seen[y][x] = True
            stack = [(y, x)]
            while stack:
                cy, cx = stack.pop()
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if (0 <= ny < height and 0 <= nx < width and not seen[ny][nx]
                            and grid[ny][nx] == colour):
                        seen[ny][nx] = True
                        stack.append((ny, nx))
    return count


def board(objects: int, *, field: int = BG) -> list[list[int]]:
    """A 64x64 board whose objects_pcc is exactly `objects` (self-checked)."""
    squares = objects - 1
    if not 0 <= squares <= len(SLOT_ORIGINS):  # pragma: no cover - a typo in this file
        raise AssertionError(f"cannot draw {objects} objects on the fixture lattice")
    grid = [[field] * GRID for _ in range(GRID)]
    for number, (top, left) in enumerate(SLOT_ORIGINS[:squares]):
        colour = SQUARE_COLOURS[number % len(SQUARE_COLOURS)]
        for y in range(top, top + 2):
            for x in range(left, left + 2):
                grid[y][x] = colour
    measured = pcc(grid)
    if measured != objects:  # pragma: no cover - the rig's own self-check
        raise AssertionError(f"rig bug: board({objects}) measures objects_pcc={measured}")
    return grid


def record(label: str, seq: int, completed: int, state: str,
           grid: Sequence[Sequence[int]]) -> dict:
    return {"label": label, "seq": seq, "levels_completed": completed, "state": state,
            "grid": [list(row) for row in grid]}


def sidecar(levels: Sequence[Sequence[Sequence[int]]],
            final: Sequence[Sequence[int]]) -> dict:
    """reset (level 1) · one settled record per later level start · the WIN `final`.

    `levels_completed` steps 0, 1, 2, ... so `records[k]` starts level k+1, and the
    trailing WIN record is the win screen, never a level (the committed
    `level_start_indices` rule, which the officials' 183 rows cross-validate).
    """
    rows = [record("reset", 0, 0, LIVE, levels[0])]
    for number, grid in enumerate(levels[1:], start=1):
        rows.append(record(f"step-{7 * number}:ACTION1", number, number, LIVE, grid))
    rows.append(record("final", len(levels), len(levels), WIN, final))
    return {"game_id": GAME_ID, "source": "synthetic", "levels_completed": len(levels),
            "win": True, "records": rows}


def spec_document(tier: str | None) -> dict:
    """A §11-shaped spec carrying what the card reads, plus the promoted-tier label."""
    game: dict[str, object] = {
        "slug": GAME_ID,
        "title": "T-1 blind synthetic",
        "palette": {"you": YOU, "goal": GOAL, "danger": DANGER, "background": BG,
                    "reserved": [1, 2]},
        "hud": {"reserved": "row63",
                "meter": {"placement": "row63-left", "direction": "shrink-right"}},
        "render": {"cell_px": 2},
    }
    if tier is not None:
        game["tier"] = tier
    return {"game": game}


def idea_document(tier: str) -> dict:
    """The committed idea fixture, re-tiered — `idea.json` is the tier's carrier."""
    idea = json.loads(IDEA_FIXTURE.read_text(encoding="utf-8"))
    idea["id"] = f"{GAME_ID}-i001"
    idea["tier"] = tier
    return idea


def stage_card_slot(directory: Path, levels: Sequence[Sequence[Sequence[int]]],
                    final: Sequence[Sequence[int]] | None = None, *,
                    tier: str | None, carriers: tuple[str, ...] = BOTH_CARRIERS) -> Path:
    """One synthetic slot inside tmp_path: spec.yaml + frames sidecar (+ idea.json).

    `carriers` says where the tier is written: `idea` (the spec dir's `idea.json` copy,
    which S1 writes for every slot — THE production carrier) and/or `spec` (`game.tier`,
    which only a P-A.3 promotion writes)."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "spec.yaml").write_text(
        yaml.safe_dump(spec_document(tier if SPEC_CARRIER in carriers else None),
                       sort_keys=False, allow_unicode=True),
        encoding="utf-8")
    (directory / "worker.frames.json").write_text(
        json.dumps(sidecar(levels, levels[-1] if final is None else final), indent=2) + "\n",
        encoding="utf-8")
    if tier is not None and IDEA_CARRIER in carriers:
        (directory / "idea.json").write_text(
            json.dumps(idea_document(tier), indent=2) + "\n", encoding="utf-8")
    return directory


def uniform_slot(directory: Path, objects: int, *, tier: str | None = "t1",
                 levels: int = 3, carriers: tuple[str, ...] = BOTH_CARRIERS) -> Path:
    grid = board(objects)
    return stage_card_slot(directory, [grid] * levels, tier=tier, carriers=carriers)


# =============================================================================
# reading the card (shape unpinned, meaning pinned)
# =============================================================================


def norm_key(name: object) -> str:
    """`density`, `Density` and `density_band` normalise apart; `objects-pcc` == `objects_pcc`."""
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def find_row(report: Mapping) -> Mapping | None:
    """The card's `density` row: top level first, then one mapping in."""
    for key, value in report.items():
        if norm_key(key) == ROW and isinstance(value, Mapping):
            return value
    for value in report.values():
        if isinstance(value, Mapping):
            for key, inner in value.items():
                if norm_key(key) == ROW and isinstance(inner, Mapping):
                    return inner
    return None


def density_row(report: Mapping, *, label: str, clause: str = B1) -> Mapping:
    row = find_row(report)
    if row is None:
        pytest.fail(
            f"{label}: the visual card carries no `density` row (a mapping keyed `density` at "
            f"the card's top level or one mapping in); the card offers {sorted(map(str, report))}."
            f"\n  {WORK2}\n  {clause}"
        )
    return row


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def walk(node: object, path: str = "") -> Iterator[tuple[str, object]]:
    """(dotted key path, value) for every node under a card row."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            yield here, value
            yield from walk(value, here)
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for index, value in enumerate(node):
            here = f"{path}[{index}]"
            yield here, value
            yield from walk(value, here)


def numbers_in(node: object) -> set[float]:
    return {float(value) for _path, value in walk(node) if is_number(value)}


def strings_in(node: object) -> list[str]:
    found = [value for _path, value in walk(node) if isinstance(value, str)]
    return [node] if isinstance(node, str) else found


def keys_in(node: object) -> list[str]:
    keys: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            keys.append(str(key))
            keys.extend(keys_in(value))
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for value in node:
            keys.extend(keys_in(value))
    return keys


def direct(row: Mapping, wanted: str) -> object:
    for key, value in row.items():
        if norm_key(key) == wanted:
            return value
    return _ABSENT


def verdict(row: Mapping, *, label: str) -> bool:
    """True = in band / not judged, False = FLAGGED. `passed` is the gate's own face."""
    for name in ("passed", "pass", "ok"):
        value = direct(row, name)
        if isinstance(value, bool):
            return value
    for name in ("verdict", "status", "result"):
        value = direct(row, name)
        if isinstance(value, str):
            word = value.strip().lower()
            if word in PASS_WORDS or word in UNJUDGED_WORDS:
                return True
            if word in FAIL_WORDS:
                return False
    pytest.fail(
        f"{label}: the `density` row carries no pass/fail face — it offers "
        f"{sorted(map(str, row))}. Every committed card check reports `passed: bool`, and the "
        f"orchestrator's fail loop rejects on `not check['passed']`; a row with no verdict is a "
        f"measurement the gate can never act on.\n  {WORK2}"
    )


def row_mode(row: Mapping, *, label: str) -> str:
    value = direct(row, "mode")
    if not isinstance(value, str):
        pytest.fail(
            f"{label}: the `density` row carries no `mode` string ({sorted(map(str, row))}). "
            f"Every committed card check records the mode it ran in, so a reader can tell a "
            f"recorded flag from a rejecting one.\n  {WORK2}"
        )
    return value


def _ends_floor(key: str) -> bool:
    normal = norm_key(key)
    return normal.endswith("floor") or normal in {"p25", "officialp25", "floorp25"}


def floor_of(row: Mapping, *, label: str) -> float:
    """The band's FLOOR as the card states it — the code's constant, quoted at runtime."""
    tiers: list[tuple[str, dict[str, float]]] = []
    tiers.append(("key `floor`", {key: float(value) for key, value in row.items()
                                  if norm_key(key) == "floor" and is_number(value)}))
    tiers.append(("a top-level key ending in `floor` / named `p25`",
                  {key: float(value) for key, value in row.items()
                   if _ends_floor(key) and is_number(value)}))
    band: dict[str, float] = {}
    for key, value in row.items():
        if "band" not in norm_key(key):
            continue
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and value \
                and all(is_number(item) for item in value):
            band[f"{key}[0]"] = float(value[0])
        elif isinstance(value, Mapping):
            for inner, item in value.items():
                if norm_key(inner) in {"floor", "low", "p25", "min", "lower"} and is_number(item):
                    band[f"{key}.{inner}"] = float(item)
    tiers.append(("a `band` list's first element / a `band` mapping's floor", band))
    tiers.append(("any nested key ending in `floor` or naming `p25`",
                  {path: float(value) for path, value in walk(row)
                   if is_number(value) and (_ends_floor(path.rsplit(".", 1)[-1])
                                            or "p25" in path.lower())}))
    for _name, candidates in tiers:
        if len(set(candidates.values())) == 1:
            return next(iter(candidates.values()))
    pytest.fail(
        f"{label}: cannot read ONE floor off the `density` row — tried, in order, "
        + "; ".join(f"{name}: {cands or 'none'}" for name, cands in tiers)
        + f". The row offers {sorted(map(str, row))}.\n  {WORK2}\n  {B2}"
    )


def names_a_tier(row: Mapping) -> bool:
    if any(TIER_TOKEN_RE.search(text) for text in strings_in(row)):
        return True
    return any("tier" in norm_key(key) or "scope" in norm_key(key) for key in keys_in(row))


def names_t1(row: Mapping) -> bool:
    return any(T1_RE.search(text) for text in strings_in(row))


def number_re(value: float) -> re.Pattern[str]:
    """`25` / `25.0` as a standalone number (not `p25`, `25th`, `125` or `25.5`)."""
    value = float(value)
    body = rf"{int(value)}(?:\.0+)?" if value.is_integer() else re.escape(f"{value:g}")
    return re.compile(rf"(?<![\w.]){body}(?![\w]|\.\d)")


# =============================================================================
# fixtures: the module, the configs, the builders
# =============================================================================


@pytest.fixture(scope="session")
def official() -> dict:
    """The officials' per-level p25 and median, MEASURED (never typed)."""
    values = official_objects_pcc()
    if len(values) != OFFICIAL_LEVELS:
        pytest.fail(f"rig: {LEVEL_METRICS_CSV} carries {len(values)} official level rows, "
                    f"the parity re-measure's population is {OFFICIAL_LEVELS}")
    p25 = linear_quantile(values, 0.25)
    median = linear_quantile(values, 0.5)
    for method in ("inclusive", "exclusive"):
        quartiles = statistics.quantiles(values, n=4, method=method)
        if quartiles[0] != p25 or quartiles[1] != median:  # pragma: no cover - data drift
            pytest.fail(f"rig: the officials' p25/median are quantile-method dependent "
                        f"({method}: {quartiles[:2]} vs linear {p25}/{median}) — the floor "
                        f"would not be one number")
    if not UNDER < p25 <= BETWEEN < median < HIGH:  # pragma: no cover - fixture design guard
        pytest.fail(f"rig: fixture counts {UNDER}/{BETWEEN}/{HIGH} no longer straddle the "
                    f"measured p25={p25} / median={median}")
    return {"p25": p25, "median": median}


@pytest.fixture(scope="session")
def s3_visual():
    import gen.s3_visual as module
    return module


@pytest.fixture(scope="session")
def template_cfg(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """`load_config` on a tmp COPY of the template — the production cfg, `tiers:` included."""
    if not TEMPLATE_PATH.is_file():  # pragma: no cover
        pytest.fail(f"config/template.yaml missing: {TEMPLATE_PATH}")
    dest = tmp_path_factory.mktemp("t1-density-template") / "template.yaml"
    shutil.copyfile(TEMPLATE_PATH, dest)
    return load_config(dest)


def cfg_with(base: Mapping, density: object = _ABSENT, **gate: object) -> dict:
    """`base` with `gate.density` set (or REMOVED, when `_ABSENT`) plus any other gate keys."""
    cfg = copy.deepcopy(dict(base))
    block = dict(cfg.get("gate") or {})
    block.pop(KNOB, None)
    block.update(gate)
    if density is not _ABSENT:
        block[KNOB] = density
    cfg["gate"] = block
    return cfg


def _tier_kwargs(func: Callable, tier: str | None, slot: Path) -> dict:
    """Pass the tier through any parameter the implementer may have added for it."""
    kwargs: dict[str, object] = {}
    for name in inspect.signature(func).parameters:
        low = name.lower()
        if "tier" in low and tier is not None:
            kwargs[name] = tier
        elif low == "idea_path" and (slot / "idea.json").is_file():
            kwargs[name] = slot / "idea.json"
        elif low == "idea" and (slot / "idea.json").is_file():
            kwargs[name] = json.loads((slot / "idea.json").read_text(encoding="utf-8"))
    return kwargs


def build_card(module, slot: Path, cfg: Mapping, *, tier: str | None = "t1") -> dict:
    builder = module.build_visual_card
    report = dict(builder(slot, cfg, **_tier_kwargs(builder, tier, slot)))
    report.pop("paths", None)          # where the files are, not what was measured
    return report


@pytest.fixture
def card(s3_visual, template_cfg, tmp_path: Path):
    """card(objects | levels=[...], final=..., tier=..., density=...) -> (report, slot)."""
    counter = iter(range(1_000))

    def make(objects: int | None = None, *, levels: Sequence[int] | None = None,
             final: int | None = None, tier: str | None = "t1",
             density: object = _ABSENT,
             carriers: tuple[str, ...] = BOTH_CARRIERS) -> tuple[dict, Path]:
        slot = tmp_path / f"slot-{next(counter)}"
        counts = list(levels) if levels is not None else [objects] * 3
        grids = [board(count) for count in counts]
        stage_card_slot(slot, grids, None if final is None else board(final), tier=tier,
                        carriers=carriers)
        return build_card(s3_visual, slot, cfg_with(template_cfg, density), tier=tier), slot

    return make


def _md_density_text(slot: Path, s3_visual) -> str:
    """The human card's density section (a heading naming density, to the next heading)."""
    text = s3_visual.card_paths(slot)["md"].read_text(encoding="utf-8")
    lines = text.splitlines()
    section: list[str] = []
    inside = False
    for line in lines:
        if line.lstrip().startswith("#"):
            inside = bool(re.search(r"densit", line, re.IGNORECASE))
            if inside:
                section.append(line)
            continue
        if inside:
            section.append(line)
    if section:
        return "\n".join(section)
    # No heading of its own: the lines that say "density" (or `objects_pcc`) are the row.
    return "\n".join(line for line in lines if re.search(r"densit|objects_pcc", line, re.IGNORECASE))


# =============================================================================
# B1 — under the floor flags; at the median passes; the knob matrix
# =============================================================================


def test_b1_a_board_under_the_floor_flags_on_the_t1_card(card, official) -> None:
    """B1 (first leg): a t1 game whose every level is drawn UNDER the officials' p25 is
    FLAGGED by the card's `density` row (`passed: false`, the committed card-check face),
    with the knob absent — i.e. in its default `record` mode."""
    report, _slot = card(UNDER)
    row = density_row(report, label=f"t1, {UNDER} objects_pcc/level, knob absent")
    assert verdict(row, label="under-floor t1") is False, (
        f"a t1 game at {UNDER} objects_pcc per level (officials' p25 = {official['p25']:g}, "
        f"measured) is not flagged by the `density` row: {dict(row)!r}.\n  {B1}\n  {WORK2}"
    )


def test_b1_a_board_at_the_officials_median_passes_on_the_t1_card(card, official) -> None:
    """B1 (second leg): "one at the officials' median passes" — every level drawn at the
    officials' MEASURED per-level median (47 at this date) is in band."""
    at_median = int(official["median"])
    report, _slot = card(at_median)
    row = density_row(report, label=f"t1, {at_median} objects_pcc/level")
    assert verdict(row, label="at-median t1") is True, (
        f"a t1 game drawn at the officials' own per-level median ({at_median} objects_pcc) is "
        f"flagged by the `density` row: {dict(row)!r}.\n  {B1}"
    )


def test_b1_the_production_tier_carrier_alone_arms_the_band(card, official) -> None:
    """B1 on the slot a real batch hands the card: an unpromoted t1 game's tier lives only
    in the spec dir's `idea.json` (S1 copies it there; `game.tier` is written only by a
    P-A.3 promotion). With that carrier ALONE the under-floor board still flags and the
    median board still passes — the band is not armed only by a label most specs lack."""
    under, _slot = card(UNDER, carriers=PRODUCTION_CARRIER)
    assert verdict(density_row(under, label="idea-only t1 under-floor"),
                   label="idea-only t1 under-floor") is False, (
        f"with the tier carried only by idea.json (the production shape), an under-floor t1 "
        f"game is not flagged: {find_row(under)!r}\n  {B1}"
    )
    at_median, _slot = card(int(official["median"]), carriers=PRODUCTION_CARRIER)
    assert verdict(density_row(at_median, label="idea-only t1 at median"),
                   label="idea-only t1 at median") is True, f"{find_row(at_median)!r}\n  {B1}"


def test_b1_the_floor_on_the_card_is_the_officials_measured_p25(card, official) -> None:
    """Work 2's derivation, cross-checked blind: the floor the card states (read at runtime
    off the row) equals the officials' PER-LEVEL p25 of `objects_pcc`, measured here off
    the contract's CSV with every standard quantile method agreeing.

    AMBIGUITY: "the officials' p25" could be misread as the p25 of the 25 per-GAME
    medians (28 at this date). The contract pairs it with "median 47 objects_pcc per
    level" — the per-level population — so the per-level p25 is pinned."""
    report, _slot = card(UNDER)
    floor = floor_of(density_row(report, label="t1 under-floor"), label="t1 under-floor")
    assert floor == official["p25"], (
        f"the card's density floor is {floor:g}; the officials' per-level objects_pcc p25 "
        f"measured off {LEVEL_METRICS_CSV.relative_to(ROOT)} is {official['p25']:g} "
        f"(median {official['median']:g}, n={OFFICIAL_LEVELS}).\n  {WORK2}"
    )


@pytest.mark.parametrize(
    ("levels", "final", "flags"),
    [
        ((UNDER, BETWEEN, HIGH), HIGH, False),   # median BETWEEN passes; min-based would flag
        ((UNDER, UNDER, HIGH), UNDER, True),     # median UNDER flags; mean-based would pass
    ],
    ids=["median-over-floor-despite-one-sparse-level", "median-under-floor-despite-one-dense-level"],
)
def test_b1_the_row_judges_the_per_level_median(card, levels, final, flags) -> None:
    """Work 2: the row is "per-level median objects_pcc against the officials' band" —
    a game is judged by the MEDIAN of its levels, not its sparsest level (the first case
    would flag under a min) nor its mean (the second would pass under a mean). The WIN
    board is drawn so an every-record median reaches the same verdict as a level-start one."""
    report, _slot = card(levels=levels, final=final)
    row = density_row(report, label=f"levels {levels}")
    assert verdict(row, label=f"levels {levels}") is (not flags), (
        f"levels drawn at {list(levels)} objects_pcc (median {sorted(levels)[1]}) should "
        f"{'FLAG' if flags else 'PASS'}; the row says {dict(row)!r}.\n  {WORK2}"
    )


@pytest.mark.parametrize("density", [_ABSENT, RECORD, FAIL], ids=["absent", "record", "fail"])
@pytest.mark.parametrize("which", ["under-floor", "at-median"])
def test_b1_the_card_prints_the_measured_value_beside_the_band_either_way(
        card, s3_visual, official, density, which) -> None:
    """Work 2: "The card prints the measured value beside the band either way" — in every
    mode and for a passing and a flagged game alike, the row's json carries the game's
    measured per-level median AND the floor, and the human card (visual-report.md) prints
    both in its density text."""
    objects = UNDER if which == "under-floor" else int(official["median"])
    report, slot = card(objects, density=density)
    label = f"{objects} objects_pcc, density={'absent' if density is _ABSENT else density}"
    row = density_row(report, label=label)
    floor = floor_of(row, label=label)
    numbers = numbers_in(row)
    assert float(objects) in numbers, (
        f"{label}: the game's measured per-level median ({objects}) is not on the `density` "
        f"row (numbers present: {sorted(numbers)}).\n  {WORK2}"
    )
    md = _md_density_text(slot, s3_visual)
    missing = [str(value) for value in (objects, floor) if not number_re(value).search(md)]
    assert md and not missing, (
        f"{label}: visual-report.md's density text does not print {missing} (measured "
        f"{objects} beside floor {floor:g}); density text found: {md[:600]!r}.\n  {WORK2}"
    )


def test_b1_the_knob_matrix_on_the_card(card) -> None:
    """B1's knob matrix, as the card records it: absent -> `record` (default-absent =
    record), `record` -> `record`, `fail` -> `fail`; and the MEASUREMENT is the same in all
    three (the mode decides what the gate does, never what the card sees)."""
    rows = {}
    for density, expected in ((_ABSENT, RECORD), (RECORD, RECORD), (FAIL, FAIL)):
        name = "absent" if density is _ABSENT else density
        report, _slot = card(UNDER, density=density)
        row = density_row(report, label=f"density={name}")
        assert row_mode(row, label=f"density={name}") == expected, (
            f"`gate.density` {name} must run the row in `{expected}` mode; the row records "
            f"{row_mode(row, label=name)!r}.\n  {B1}\n  {WORK2}"
        )
        rows[name] = row
    stripped = {name: {key: value for key, value in row.items() if norm_key(key) != "mode"}
                for name, row in rows.items()}
    assert stripped["absent"] == stripped["record"], (
        f"knob ABSENT and knob `record` must build the same row:\n  {stripped['absent']!r}\n"
        f"  {stripped['record']!r}\n  {B1}"
    )
    assert verdict(rows["fail"], label="fail") is verdict(rows["record"], label="record") \
        is False, f"`fail` and `record` must measure the same flag.\n  {B1}"


@pytest.mark.parametrize("bad", BAD_MODES)
def test_b1_a_density_value_outside_the_enum_is_loud(card, bad: str) -> None:
    """Work 2: "Severity knob like every card check" — every committed card knob is a
    closed enum that raises `ValueError` naming the key on any other value (the gate reads
    it long after the batch started spending; a typo must never silently default).

    The signed word is built first, so this cannot pass on a tree where `density` is
    merely an UNKNOWN gate key (which also raises a ValueError naming it)."""
    try:
        card(UNDER, density=RECORD)
    except ValueError as exc:
        pytest.fail(f"`gate.density: record` itself is refused ({exc}).\n  {WORK2}")
    with pytest.raises(ValueError, match=r"density"):
        card(UNDER, density=bad)


def test_b1_every_shipped_batch_config_builds_the_row_in_record(s3_visual, tmp_path) -> None:
    """B1, "absent ... never reject", over the real batch configs: none of the historical
    `config/*.yaml` names `gate.density`, so every one of them must build the row in
    `record` — a resumed historical batch can never be stopped by the new check."""
    slot = uniform_slot(tmp_path / "slot", UNDER)
    problems: list[str] = []
    configs = sorted(path for path in CONFIG_DIR.glob("*.yaml") if path.name != "template.yaml")
    assert configs, "rig: no historical batch configs under config/"
    for path in configs:
        cfg = load_config(path)
        if KNOB in (cfg.get("gate") or {}):
            problems.append(f"{path.name} names gate.{KNOB} (historical configs must not)")
            continue
        row = find_row(build_card(s3_visual, slot, cfg))
        if row is None:
            problems.append(f"{path.name}: no `density` row")
        elif direct(row, "mode") != RECORD:
            problems.append(f"{path.name}: row mode {direct(row, 'mode')!r}")
    assert not problems, "\n  ".join([f"{B1}", *problems])


# --- the knob matrix at the gate: drive the real `s3_gate` runner -------------------


def _run_gate(monkeypatch: pytest.MonkeyPatch, slot: Path, cfg: Mapping) -> dict:
    """The orchestrator's REAL `s3_gate` runner on a staged slot.

    Stubbed: only the three seams that touch the engine or the worker's code —
    `frames.capture_worker_isolated` (an engine drive), `s3_gate.merged_gate` (the
    structural/robustness layers; stubbed to `gated`) and `s3_gate.gate_checks`
    (contract B3's rows, which read that capture). Everything after them is real:
    the frames-provenance guard, the verifier-report read, `build_visual_card` on the
    fixture sidecar, and the `visual <check>` fail loop this contract arms.

    The slot is the PRODUCTION shape for an unpromoted game: the tier lives only in
    `idea.json` (the spec dir's copy, and the batch's ideas-dir original the context
    points at) — never in `game.tier`, which only a promotion writes. So the runner is
    proven to find the tier the way a real batch hands it over.
    """
    import gen.frames as frames_module
    import gen.s3_gate as gate_module
    from gen import orchestrator
    from gen.s3_verify import REPORT_SUFFIX

    worker = slot / "worker"
    worker.mkdir(exist_ok=True)
    (worker / "game.py").write_text("# T-1 blind synthetic: never executed\n", encoding="utf-8")
    worker.with_name(worker.name + REPORT_SUFFIX).write_text(
        json.dumps({"verdict": "pass"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(frames_module, "capture_worker_isolated",
                        lambda *args, **kwargs: {"synthetic": True})
    monkeypatch.setattr(gate_module, "merged_gate",
                        lambda *args, **kwargs: {"verdict": "gated"})
    monkeypatch.setattr(gate_module, "gate_checks",
                        lambda *args, **kwargs: {"path": None, "checks": []})
    ideas_dir = slot.parent / "ideas"
    ideas_dir.mkdir(exist_ok=True)
    idea_path = ideas_dir / "idea-001.json"
    if (slot / "idea.json").is_file():
        shutil.copyfile(slot / "idea.json", idea_path)
    runner = orchestrator.default_runners()["s3_gate"]
    ctx = orchestrator.SlotContext(
        cfg=cfg, batch_id="t1-density-blind", slug=GAME_ID, index=1, state="verified",
        stage="s3_gate", attempt=1, batch_dir=slot.parent, ideas_dir=ideas_dir,
        idea_path=idea_path, corpus_dir=slot.parent, spec_dir=slot,
        respec_count=0, verifier_rejects=0, green_failures=0,
    )
    result = runner(ctx)
    error = (result.get("artifacts") or {}).get("visual_card_error")
    if error is not None:
        pytest.fail(f"the card raised inside the gate runner (recorded as a note, which "
                    f"would mask any verdict): {error}")
    return result


def test_b1_rig_control_the_gate_runner_reaches_the_visual_fail_loop(
        monkeypatch, template_cfg, tmp_path) -> None:
    """RIG CONTROL (holds on any tree since W1-A1): an ARMED committed check —
    `field_index: fail` on a white (index-0) field the spec never declared — stops the
    driven runner with `visual field-index`. Proves the stubbed runner really reaches the
    loop the B1 matrix below relies on, so a red there is about `density`, not the rig."""
    white = board(BETWEEN, field=WHITE)
    slot = stage_card_slot(tmp_path / "control", [white] * 3, tier="t1",
                           carriers=PRODUCTION_CARRIER)
    cfg = cfg_with(template_cfg, **{**QUIET_GATE, "field_index": FAIL})
    result = _run_gate(monkeypatch, slot, cfg)
    assert result["ok"] is False and "field-index" in result["reason"], (
        f"rig control failed — the driven s3_gate runner did not reject an armed white "
        f"field: {result!r}"
    )


@pytest.mark.parametrize("density", [_ABSENT, RECORD], ids=["absent", "record"])
def test_b1_absent_and_record_never_reject_at_the_gate(
        monkeypatch, template_cfg, tmp_path, density) -> None:
    """B1: "absent/record both never reject" — the real gate runner passes an UNDER-floor
    t1 game to `gated` when `gate.density` is absent or `record` (every other card knob
    held at `record`). The absent leg holds on the pre-T-1 tree too (there is no check)."""
    slot = uniform_slot(tmp_path / "slot", UNDER, carriers=PRODUCTION_CARRIER)
    cfg = cfg_with(template_cfg, density, **QUIET_GATE)
    result = _run_gate(monkeypatch, slot, cfg)
    assert result["ok"] is True and result["to_state"] == "gated", (
        f"gate.density={'absent' if density is _ABSENT else density} stopped an under-floor "
        f"t1 game: {result!r}\n  {B1}"
    )


def test_b1_fail_rejects_at_the_gate(monkeypatch, template_cfg, tmp_path) -> None:
    """B1: "fail rejects" — with `gate.density: fail` the real gate runner REJECTS an
    under-floor t1 game, and its reason names the density rule (the `visual <check>`
    idiom every armed card check uses)."""
    slot = uniform_slot(tmp_path / "slot", UNDER, carriers=PRODUCTION_CARRIER)
    cfg = cfg_with(template_cfg, FAIL, **QUIET_GATE)
    result = _run_gate(monkeypatch, slot, cfg)
    assert result["ok"] is False, (
        f"gate.density=fail let an under-floor t1 game ({UNDER} objects_pcc/level) through "
        f"the gate: {result!r}\n  {B1}"
    )
    assert re.search(r"densit", str(result.get("reason")), re.IGNORECASE), (
        f"the rejection does not name the density rule: reason={result.get('reason')!r}\n  {B1}"
    )


def test_b1_fail_does_not_reject_a_game_in_band(
        monkeypatch, template_cfg, official, tmp_path) -> None:
    """B1 (the median leg under `fail`): the armed check passes a t1 game drawn at the
    officials' per-level median — `fail` rejects the under-floor board, not every board."""
    slot = uniform_slot(tmp_path / "slot", int(official["median"]),
                        carriers=PRODUCTION_CARRIER)
    cfg = cfg_with(template_cfg, FAIL, **QUIET_GATE)
    result = _run_gate(monkeypatch, slot, cfg)
    assert result["ok"] is True and result["to_state"] == "gated", (
        f"gate.density=fail stopped a t1 game at the officials' median: {result!r}\n  {B1}"
    )


# =============================================================================
# B2 — the payload's tier-aware density guidance carries the code's constant
# =============================================================================


def stage_payload_slot(directory: Path, tier: str,
                       carriers: tuple[str, ...] = BOTH_CARRIERS) -> Path:
    """The committed B5 fixture spec + its idea, re-tiered on `carriers`, in tmp_path."""
    directory.mkdir(parents=True, exist_ok=True)
    spec = yaml.safe_load(GOOD_SPEC.read_text(encoding="utf-8"))
    if SPEC_CARRIER in carriers:
        spec["game"]["tier"] = tier
    (directory / "spec.yaml").write_text(
        yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (directory / "spec.md").write_text(SPEC_MD, encoding="utf-8")
    if IDEA_CARRIER in carriers:
        (directory / "idea.json").write_text(
            json.dumps(idea_document(tier), indent=2) + "\n", encoding="utf-8")
    return directory


@pytest.fixture(scope="session")
def payload_for(template_cfg, tmp_path_factory) -> Callable[..., str]:
    """payload_for(tier, carriers) -> the S2 payload for the fixture spec at that tier (cached)."""
    from gen import s2_implement

    cache: dict[tuple[str, tuple[str, ...]], str] = {}

    def build(tier: str, carriers: tuple[str, ...] = BOTH_CARRIERS) -> str:
        key = (tier, carriers)
        if key not in cache:
            root = tmp_path_factory.mktemp(f"payload-{tier}-{'-'.join(carriers)}")
            slot = stage_payload_slot(root / "spec", tier, carriers)
            builder = s2_implement.build_payload
            text, _report = builder(slot, template_cfg, **_tier_kwargs(builder, tier, slot))
            cache[key] = text
        return cache[key]

    return build


@pytest.fixture(scope="session")
def runtime_floor(s3_visual, template_cfg, tmp_path_factory) -> float:
    """THE CODE'S CONSTANT, quoted at runtime: the floor the t1 card's `density` row states."""
    slot = uniform_slot(tmp_path_factory.mktemp("floor") / "slot", UNDER)
    report = build_card(s3_visual, slot, cfg_with(template_cfg))
    return floor_of(density_row(report, label="runtime floor (t1)", clause=B2),
                    label="runtime floor (t1)")


def paragraphs(text: str) -> list[str]:
    return [part for part in re.split(r"\n\s*\n", text) if part.strip()]


def sections(text: str) -> list[str]:
    """The payload cut at its `##`-and-deeper headings (every payload section opens with
    one; a level-1 `#` is left alone so a python comment in a quoted skeleton never cuts)."""
    found: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if re.match(r"#{2,6} ", line) and current:
            found.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        found.append("\n".join(current))
    return found


def guidance_windows(payload: str, floor: float) -> list[str]:
    """Each density paragraph that states the floor as a FIGURE, with its +-1 neighbours.

    The anchor needs more than the bare number: "25" is also the officials' game count,
    printed by the committed corpus-numbers card next to the word "density" (and the word
    "median"). So the anchoring paragraph must also carry a percentile/floor cue or name
    t1 — neither of which the committed numbers card does — or a guidance paragraph that
    forgot the floor could borrow that card's "25" from the paragraph next door.
    """
    parts = paragraphs(payload)
    floor_re = number_re(floor)
    windows = []
    for index, part in enumerate(parts):
        if DENSITY_RE.search(part) and floor_re.search(part) and (
                CUE_RE.search(part) or T1_RE.search(part)):
            windows.append("\n\n".join(parts[max(0, index - 1): index + 2]))
    return windows


def _density_constants() -> list[str]:
    """Diagnostics only: module-level names that look like the density constants."""
    import gen.s1_spec
    import gen.s2_implement
    import gen.s3_visual
    import gen.tiers
    import gen.visual_canon
    found = []
    for module in (gen.s3_visual, gen.visual_canon, gen.s2_implement, gen.s1_spec, gen.tiers):
        for name, value in vars(module).items():
            if re.search(r"DENSITY|PCC", name) and not callable(value) \
                    and not isinstance(value, type(sys)):
                found.append(f"{module.__name__}.{name} = {str(value)[:120]!r}")
    return found


@pytest.mark.parametrize("carriers", [BOTH_CARRIERS, PRODUCTION_CARRIER],
                         ids=["idea+spec", "idea-only(production)"])
def test_b2_the_t1_payload_carries_density_guidance_with_the_codes_floor(
        payload_for, runtime_floor, official, carriers) -> None:
    """B2: the t1 S2 payload carries the tier-aware density guidance, and the NUMBER in it
    is the code's constant — the floor read at runtime off the card's own `density` row,
    never a copy typed here. Work 1 fixes what the guidance says beside it: the officials'
    median per level (MEASURED here: 47), that it is about t1, and that t1 simplicity is
    mechanical (fewer rules), not visual sparseness. Pinned on both tier carriers,
    including the production one alone (the spec dir's `idea.json`, no `game.tier`)."""
    payload = payload_for("t1", carriers)
    windows = guidance_windows(payload, runtime_floor)
    median_re = number_re(official["median"])
    complete = [window for window in windows
                if median_re.search(window) and T1_RE.search(window)
                and MECHANIC_RE.search(window) and SPARSE_RE.search(window)]
    if complete:
        return
    density_paragraphs = [part[:300] for part in paragraphs(payload) if DENSITY_RE.search(part)]
    pytest.fail(
        f"the t1 S2 payload carries no density guidance stating the code's floor "
        f"({runtime_floor:g}, read off the card) beside the officials' median "
        f"({official['median']:g}, measured), naming t1, and saying t1 simplicity is mechanical "
        f"not sparse.\n  anchoring windows found: {len(windows)} — "
        + "; ".join(
            f"[median {'Y' if median_re.search(w) else 'N'} t1 {'Y' if T1_RE.search(w) else 'N'} "
            f"mechanic {'Y' if MECHANIC_RE.search(w) else 'N'} "
            f"sparse {'Y' if SPARSE_RE.search(w) else 'N'}] {w[:200]!r}"
            for w in windows)
        + f"\n  paragraphs mentioning density: {density_paragraphs}"
        + f"\n  density-looking constants in gen/: {_density_constants()}"
        + f"\n  {B2}\n  {WORK1}"
    )


def test_b2_the_guidance_figure_tracks_the_card_not_a_second_copy(
        payload_for, runtime_floor) -> None:
    """B2's prompt-sync half: wherever the t1 payload's density text writes a p25 figure
    directly after its label ("p25 = N", "p25 (N", "25th percentile: N"), N IS the card's
    floor. Lenient by design — it fires only on a POSITIVE reading of a different number,
    never on phrasing it cannot parse (presence is the test above)."""
    payload = payload_for("t1")
    stated: list[str] = []
    for part in paragraphs(payload):
        if not DENSITY_RE.search(part):
            continue
        for match in re.finditer(r"(?:\bp25\b|\b25th percentile\b)[\s=:(,]{1,6}(\d+(?:\.\d+)?)",
                                 part, re.IGNORECASE):
            stated.append(match.group(1))
    drift = [value for value in stated if float(value) != runtime_floor]
    assert not drift, (
        f"the t1 payload's density guidance states p25/floor figure(s) {drift} but the card's "
        f"floor is {runtime_floor:g} — the number must appear once in code and be quoted into "
        f"the payload.\n  {B2}"
    )


# =============================================================================
# B3 — shipped-report validation unchanged: the row is additive / optional
# =============================================================================


def _pre_t1_module(tmp_path: Path):
    """`gen/s3_visual.py` exactly as it stood at the pre-T-1 commit, imported in-package.

    Loaded from a tmp copy under a private module name inside `gen` (so its relative
    imports resolve to the live `gen.s1_spec` / `gen.visual_canon`), and removed from
    `sys.modules` again by the caller. A checkout without that commit (a shallow clone)
    SKIPS loudly — the commit is the baseline, there is no honest substitute.
    """
    try:
        source = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{PRE_T1_COMMIT}:gen/s3_visual.py"],
            capture_output=True, text=True, check=True, timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"B3 baseline unavailable: cannot read gen/s3_visual.py at the pre-T-1 "
                    f"commit {PRE_T1_COMMIT[:12]} ({exc})")
    path = tmp_path / "pre_t1_s3_visual.py"
    path.write_text(source, encoding="utf-8")
    name = "gen._t1_blind_pre_t1_s3_visual"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except ImportError as exc:
        sys.modules.pop(name, None)
        pytest.fail(f"the pre-T-1 card module no longer imports against the live gen/ "
                    f"package ({exc}) — a name it imports from gen.s1_spec / gen.visual_canon "
                    f"was removed or renamed.\n  {B3}")
    return module, name


def deep_subset(old: object, new: object, path: str = "card") -> list[str]:
    """Every place `new` fails to carry what `old` carried (keys may be ADDED, never changed)."""
    if isinstance(old, Mapping):
        if not isinstance(new, Mapping):
            return [f"{path}: was a mapping, now {type(new).__name__}"]
        problems = []
        for key, value in old.items():
            if key not in new:
                problems.append(f"{path}.{key}: removed")
            else:
                problems.extend(deep_subset(value, new[key], f"{path}.{key}"))
        return problems
    if isinstance(old, list):
        if not isinstance(new, list) or len(new) != len(old):
            return [f"{path}: list changed shape"]
        problems = []
        for index, (left, right) in enumerate(zip(old, new, strict=True)):
            problems.extend(deep_subset(left, right, f"{path}[{index}]"))
        return problems
    return [] if old == new else [f"{path}: {old!r} -> {new!r}"]


def test_b3_the_post_t1_card_is_a_superset_of_the_pre_t1_card(
        s3_visual, template_cfg, tmp_path) -> None:
    """B3: "the new card row is additive" — on the same t1 fixture slot and the same
    config (no `gate.density`), the card the pre-T-1 module builds is a deep SUBSET of the
    card the live module builds: every key the shipped cards carried is still there with
    the same value; T-1 may only add. Holds on the pre-T-1 tree (identical modules)."""
    module, name = _pre_t1_module(tmp_path)
    try:
        grids = [board(UNDER), board(BETWEEN), board(HIGH)]
        old_slot = stage_card_slot(tmp_path / "old", grids, board(HIGH), tier="t1")
        new_slot = stage_card_slot(tmp_path / "new", grids, board(HIGH), tier="t1")
        # The pre-T-1 `gate:` block is a CLOSED key set; hand both builders only the
        # keys it knew, so the comparison is one config read by two modules.
        cfg = copy.deepcopy(dict(template_cfg))
        cfg["gate"] = {key: value for key, value in (cfg.get("gate") or {}).items()
                       if key in module.GATE_KEYS}
        old = build_card(module, old_slot, cfg)
        new = build_card(s3_visual, new_slot, cfg)
    finally:
        sys.modules.pop(name, None)
    assert find_row(old) is None, "rig: the pre-T-1 module already wrote a density row"
    problems = deep_subset(old, new)
    assert not problems, "\n  ".join(
        ["T-1 changed what a pre-T-1 card carried:", *problems[:40], B3])


def test_b3_the_density_knob_changes_nothing_outside_its_own_row(card) -> None:
    """B3: the knob is the new row's alone — the same fixture built with `gate.density`
    absent, `record` and `fail` yields byte-identical cards once the `density` row is set
    aside (every shipped check, `per_record`, the bands and the l1 floor untouched)."""
    def without_row(report: dict) -> str:
        kept = {key: value for key, value in report.items() if norm_key(key) != ROW}
        return json.dumps(kept, sort_keys=True)

    built = {}
    for density in (_ABSENT, RECORD, FAIL):
        name = "absent" if density is _ABSENT else density
        report, _slot = card(levels=(UNDER, BETWEEN, HIGH), final=HIGH, density=density)
        built[name] = without_row(report)
    assert built["absent"] == built["record"] == built["fail"], (
        f"`gate.density` changed card content outside the `density` row.\n  {B3}"
    )


@pytest.mark.parametrize("config", ["template", "b001-pilot.yaml"])
def test_b3_a_slot_with_no_tier_carrier_still_builds_its_card(
        s3_visual, template_cfg, tmp_path, config: str) -> None:
    """B3: the row is OPTIONAL as an input requirement — a slot carrying only `spec.yaml`
    and the frames sidecar (no `idea.json`, no `game.tier`: exactly the copy
    `m1_metrics.build_cards` rebuilds every shipped card from) still builds a card, under
    the template and under a historical config with no `tiers:` block at all. Whatever the
    row then says, it must not crash the card the review and the audit read."""
    slot = uniform_slot(tmp_path / "slot", UNDER, tier=None)
    cfg = template_cfg if config == "template" else load_config(CONFIG_DIR / config)
    report = build_card(s3_visual, slot, cfg, tier=None)
    assert report.get("per_record"), f"no card built for a tier-less slot under {config}.\n  {B3}"


def test_b3_a_card_without_the_density_row_still_renders(card, s3_visual) -> None:
    """B3: a card written before T-1 has no `density` row; the live renderer must still
    turn such a card into the human report (the row is optional on READ as well)."""
    report, _slot = card(UNDER)
    shipped = {key: value for key, value in report.items() if norm_key(key) != ROW}
    text = s3_visual.render_markdown(shipped)
    assert isinstance(text, str) and GAME_ID in text, (
        f"render_markdown no longer renders a card without the density row.\n  {B3}"
    )


# =============================================================================
# B4 — t2+ : the band is t1-scoped or tier-scaled, and says which
# =============================================================================


def test_b4_the_t1_row_names_the_tier_it_judged(card) -> None:
    """B4 ("it must be explicit"): the t1 card's `density` row says which tier it judged
    the game at — a `t1` token in its text or a `tier`/`scope` key — so a reader of the card
    can tell a t1-scoped band from a tier-blind one without reading the code."""
    report, _slot = card(UNDER)
    row = density_row(report, label="t1 under-floor", clause=B4)
    assert names_a_tier(row), (
        f"the t1 `density` row never names a tier (no t1/t2/t3 token, no tier/scope key): "
        f"{dict(row)!r}\n  {B4}"
    )


@pytest.mark.parametrize("carriers", [BOTH_CARRIERS, PRODUCTION_CARRIER],
                         ids=["idea+spec", "idea-only(production)"])
@pytest.mark.parametrize("tier", UPPER_TIERS)
def test_b4_the_band_is_t1_scoped_or_tier_scaled_at_upper_tiers(
        card, tier: str, carriers: tuple[str, ...]) -> None:
    """B4: the SAME under-floor board, staged at t2/t3 instead of t1, must show the band is
    either t1-SCOPED (the row does not flag it) or TIER-SCALED (the row judges it against a
    different floor) — and say so (the row names its tier). A row that flags it against the
    t1 floor with no tier on it is a tier-blind band, which is what this clause forbids."""
    t1_report, _slot = card(UNDER, tier="t1", carriers=carriers)
    t1_row = density_row(t1_report, label="t1 under-floor (B4 prerequisite)", clause=B4)
    if verdict(t1_row, label="t1 under-floor") is not False:
        pytest.fail(f"B4 prerequisite: the t1 row does not flag the under-floor board "
                    f"(see B1): {dict(t1_row)!r}\n  {B4}")
    t1_floor = floor_of(t1_row, label="t1 under-floor")

    report, _slot = card(UNDER, tier=tier, carriers=carriers)
    row = find_row(report)
    if row is None:
        assert names_t1(t1_row), (
            f"at {tier} the card carries no `density` row and the t1 row never says it is "
            f"t1-scoped — neither a t1-scoped nor a tier-scaled band is detectable.\n  {B4}"
        )
        return
    assert names_a_tier(row), (
        f"the {tier} `density` row never names the tier it judged (no t1/t2/t3 token, no "
        f"tier/scope key) — the scoping is not explicit: {dict(row)!r}\n  {B4}"
    )
    flagged = verdict(row, label=f"{tier} under-floor") is False
    scaled = flagged and floor_of(row, label=f"{tier} under-floor") != t1_floor
    assert not flagged or scaled, (
        f"at {tier} the under-floor board is flagged against the SAME floor as t1 "
        f"({t1_floor:g}) — the band is tier-blind, neither t1-scoped nor tier-scaled: "
        f"{dict(row)!r}\n  {B4}"
    )


@pytest.mark.parametrize("tier", UPPER_TIERS)
def test_b4_upper_tier_payload_density_guidance_is_tier_explicit(
        payload_for, official, tier: str) -> None:
    """B4 on the payload side: the t2/t3 S2 payload still builds, and any density guidance
    it carries — a section quoting the officials' per-level median, or stating the
    mechanical-not-sparse rule — is explicit about the tier it speaks to (a t1-scoped
    block says t1; a tier-scaled one names its tier): the t1 rule must never reach a
    t2/t3 writer as an unscoped rule.

    The unit is the heading-delimited SECTION a writer reads the rule in (B2 reads a
    +-1-paragraph window for the same reason): a paragraph that only states the
    officials' measurement is a fact, not a tier rule, and its section's heading or body
    is where the scope is stated."""
    payload = payload_for(tier)
    median_re = number_re(official["median"])
    unscoped = [
        section[:400] for section in sections(payload)
        if DENSITY_RE.search(section)
        and (median_re.search(section)
             or (MECHANIC_RE.search(section) and SPARSE_RE.search(section)))
        and not TIER_TOKEN_RE.search(section)
    ]
    assert not unscoped, (
        f"the {tier} payload carries density guidance (the officials' median, or the "
        f"mechanical-not-sparse rule) in a section that names no tier: {unscoped}\n  {B4}"
    )
