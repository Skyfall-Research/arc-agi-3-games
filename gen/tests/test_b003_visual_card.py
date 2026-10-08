"""Pins for the b003 visual report card — written BLIND from the frozen contract.

Written from ``b003-vc-tests-contract.md`` ALONE.  ``gen/s3_visual.py`` was
never read while this file was written (it did not exist on disk yet), and no
in-progress diff of ``gen/orchestrator.py`` was read either: the orchestrator's
PRE-EXISTING surface was taken from ``git show HEAD:gen/orchestrator.py``, and
the seam pin below reads the WORKING file as text at run time, which is what
the contract asks for.  Everything here therefore pins the CONTRACT, not the
code: a failure means either the implementation has not landed, or it landed
somewhere other than where the contract froze it.

House style (``test_b003_visual.py``): the card's numbers are never retyped.
Every frozen metric is RE-IMPLEMENTED here from the contract's words and run
against the same shipped sidecars the code was pointed at — the
double-implementation pin.  What *is* retyped is the contract's own frozen
surface (the function names, the file names, the knob enums, the floor),
because the contract is the thing those pins exist to hold still.

What the change is for: a generated game can pass every structural and
robustness gate and still LOOK nothing like an official one.  The visual report
card measures what the frames actually show — colour counts, reserved-index
leakage off the HUD strip, run-length texture, block uniformity, object counts
— writes them beside the gate's other reports, and (in ``record`` mode) changes
no verdict at all.  The l1 colour floor is the one number with a pass/fail
face, and even it only records until ``gate.l1_color_floor`` is set to ``fail``.

Contract ambiguities resolved (each is called out again at its pin):

* **Where a metric lives in the json.**  The contract freezes the metric
  DEFINITIONS and the file names, never the json's nesting.  Every lookup here
  goes through ``dig()``, which finds a name on the record, one level inside
  the record, or on the card, and fails with a message naming every key it
  saw.  Shape is therefore unpinned on purpose; meaning is pinned hard.
* **``run_length_profile.mode`` under a tie.**  The contract gives a tie rule
  for ``objects_cc``'s modal value ("smaller index") but none for the run-length
  mode, and the shipped corpus really does tie: ``pump-phase-time-echo``
  record 6 has run lengths 2 and 4 at equal frequency.  A tied record is pinned
  to "one of the tied modes"; the 39 untied records are pinned exactly.
* **``hud_strip_values``.**  ``colors`` is explicitly "sorted distinct" and this
  key carries no qualifier, so either the sorted-distinct strip or the raw
  64-cell strip is accepted — both pin that the strip was read off the row or
  column ``hud.reserved`` names, which is the point of the metric.
* **``hud_strip_changes`` placement.**  "any record's strip differs from the
  first record's" is a run-level fact stated in a per-record list.  Accepted at
  either level; per-record it may also carry the this-record-differs reading.
* **``declared_absent`` order.**  Frozen as role NAMES with no order, so it is
  compared sorted.  (``background`` is in the contract's role list but not in
  the spec §11 palette schema, so on today's corpus it never fires; the
  recompute carries it anyway.)
* **``block_uniformity`` keys.**  A json object's keys are strings whatever the
  builder used, so both sides are normalised to ``str`` before comparing.
* **``ARC_PALETTE_HEX`` against canon.**  The contract says every hex must
  "appear in" ``GEN tools/capture_frames.py``, but that file states the
  authoritative palette as RGB TUPLES, not hex — it carries no ``#RRGGBB`` at
  all.  Taking "appears" to mean "the canon file states that colour", the
  canon's own encoding is parsed (literal hexes, plus every RGB triple in the
  file) and membership is asserted against that.  A second, stronger pin
  compares the 16 entries IN INDEX ORDER against the canon ``PALETTE`` list,
  because index order is the only thing a palette indexed by a grid int can
  mean; it is kept as its own test so it can be isolated if the lead disagrees.
* **Pin 8's scope.**  "the s3_gate runner's source references ..." then "the
  words ``visual_card_error`` appear".  A runner that calls a module-level
  helper is a legitimate implementation, so the three names are pinned at FILE
  level (hard) and the s3_gate runner body is pinned to mention ``visual`` —
  the seam must be in that runner and not some other stage.

Constraints honoured: no network, no drivers, no engine imports, GEN is opened
read-only, and nothing is written outside ``tmp_path`` — the shipped corpus
dirs are never built in place, only the two sidecar files are copied out.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import groupby
from pathlib import Path

import pytest
import yaml

from gen.config import load_config
from gen.visual_canon import OFFICIAL_VISUAL_CONSTANTS

# --- locations --------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = "config/b002-triple.yaml"  # relative, as every sibling suite loads it
CORPUS_ROOT = REPO_ROOT / "out" / "corpus"
ORCHESTRATOR_SOURCE = REPO_ROOT / "gen" / "orchestrator.py"

# The two sidecars a card is built from, and the gate directory it writes into.
# `worker.gate` is `orchestrator.WORKER_DIRNAME` + `s3_gate.GATE_SUFFIX`; the
# three report names are the contract's.
SPEC_NAME = "spec.yaml"
FRAMES_NAME = "worker.frames.json"
GATE_DIRNAME = "worker.gate"
REPORT_JSON = "visual-report.json"
REPORT_MD = "visual-report.md"
CONTACT_SHEET = "visual-contact-sheet.png"
REPORT_NAMES = (REPORT_JSON, REPORT_MD, CONTACT_SHEET)

# Canon, relative to the config's `duckwm_docs` root.  READ-ONLY, never
# addressed by an absolute path from this repo.
CAPTURE_FRAMES_REL = "tools/capture_frames.py"

# --- the contract's frozen surface ------------------------------------------

GRID_SIDE = 64
BLOCK_SCALES = (2, 3, 4, 5, 8)
PALETTE_ROLES = ("you", "goal", "danger", "background")
L1_FLOOR = 4
RESET_LABEL = "reset"

VISUAL_CARD_MODES = ("off", "record")
L1_FLOOR_MODES = ("record", "fail")
VISUAL_CARD_DEFAULT = "off"
L1_FLOOR_DEFAULT = "record"
GATE_KEYS = ("visual_card", "l1_color_floor")

# `hud.reserved` -> the strip it names.  `custom-rect` has no strip: the card
# says not-checked (pin 7).
STRIP_ROW = {"row63": GRID_SIDE - 1, "row0": 0}
STRIP_COL = "col0"
CUSTOM_RECT = "custom-rect"

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
NOT_CHECKED_RE = re.compile(r"not[-_ ]?checked", re.IGNORECASE)

# Pin 8: the seam, as words in gen/orchestrator.py.
SEAM_NAMES = ("build_visual_card", "visual_card_mode", "visual_card_error")

# The shipped corpus, discovered at import so the per-game pins can be
# parametrized.  A dotted path component is a `.killed` slot, never a shipped
# game.
SHIPPED = tuple(
    sorted(
        (
            path.parent
            for path in CORPUS_ROOT.glob(f"*/*/{FRAMES_NAME}")
            if (path.parent / SPEC_NAME).is_file()
            and not any(part.startswith(".") for part in path.parts)
        ),
        key=lambda directory: directory.name,
    )
)
SHIPPED_IDS = tuple(directory.name for directory in SHIPPED)
EXPECTED_SHIPPED = 4  # the contract's count; the floor it asserts is 3


# --- the independent metric implementation ----------------------------------
# Written from the contract's words alone.  Nothing below imports, calls or
# mirrors gen.s3_visual: the whole value of these functions is that they were
# derived from the same sentences the implementer was given, separately.


def grid_values(grid: Sequence[Sequence[int]]) -> Counter:
    return Counter(value for row in grid for value in row)


def distinct_colors(grid) -> list[int]:
    """`colors` — sorted distinct."""
    return sorted(set(grid_values(grid)))


def modal_value(grid) -> int:
    """The record's modal grid value; a tie goes to the smaller index."""
    counts = grid_values(grid)
    most = max(counts.values())
    return min(value for value, count in counts.items() if count == most)


def declared_absent(grid, palette: Mapping) -> list[str]:
    """Declared you/goal/danger/background indices missing from the grid, by ROLE."""
    present = set(grid_values(grid))
    absent = []
    for role in PALETTE_ROLES:
        index = palette.get(role)
        if isinstance(index, bool) or not isinstance(index, int):
            continue  # undeclared (or null, as a hazardless spec writes `danger`)
        if index not in present:
            absent.append(role)
    return absent


def hud_strip(grid, hud_reserved: str) -> list[int] | None:
    """The HUD strip `hud.reserved` names, or None for `custom-rect`."""
    if hud_reserved in STRIP_ROW:
        return list(grid[STRIP_ROW[hud_reserved]])
    if hud_reserved == STRIP_COL:
        return [row[0] for row in grid]
    return None


def off_strip_values(grid, hud_reserved: str) -> set[int] | None:
    """Every value OUTSIDE the HUD strip, or None for `custom-rect`."""
    if hud_reserved in STRIP_ROW:
        skip = STRIP_ROW[hud_reserved]
        return {value for index, row in enumerate(grid) if index != skip for value in row}
    if hud_reserved == STRIP_COL:
        return {value for row in grid for value in row[1:]}
    return None


def reserved_on_board(grid, reserved: Sequence[int], hud_reserved: str) -> list[int] | None:
    """`palette.reserved` indices present outside the HUD strip."""
    off_strip = off_strip_values(grid, hud_reserved)
    if off_strip is None:
        return None
    return sorted(set(reserved) & off_strip)


def horizontal_runs(grid) -> list[int]:
    """Every horizontal run length, over all rows."""
    lengths: list[int] = []
    for row in grid:
        lengths.extend(len(tuple(group)) for _value, group in groupby(row))
    return lengths


def run_length_modes(lengths: Sequence[int]) -> list[int]:
    """Every tied mode of the run lengths, ascending — see the tie ambiguity."""
    counts = Counter(lengths)
    most = max(counts.values())
    return sorted(length for length, count in counts.items() if count == most)


def run_length_median(lengths: Sequence[int]) -> float:
    return statistics.median(lengths)


def run_length_ones_share(lengths: Sequence[int]) -> float:
    return round(sum(1 for length in lengths if length == 1) / len(lengths), 4)


def block_uniformity(grid) -> dict[str, float]:
    """Fraction of aligned s*s blocks that are single-valued, 4dp, per scale."""
    profile: dict[str, float] = {}
    for scale in BLOCK_SCALES:
        blocks = GRID_SIDE // scale  # the remainder columns/rows are ignored
        uniform = 0
        for block_y in range(blocks):
            for block_x in range(blocks):
                top, left = block_y * scale, block_x * scale
                first = grid[top][left]
                if all(
                    grid[top + dy][left + dx] == first
                    for dy in range(scale)
                    for dx in range(scale)
                ):
                    uniform += 1
        profile[str(scale)] = round(uniform / (blocks * blocks), 4)
    return profile


def objects_cc(grid) -> int:
    """4-connected components of the cells that are not the modal value."""
    background = modal_value(grid)
    seen = [[False] * GRID_SIDE for _ in range(GRID_SIDE)]
    components = 0
    for row in range(GRID_SIDE):
        for col in range(GRID_SIDE):
            if seen[row][col] or grid[row][col] == background:
                continue
            components += 1
            stack = [(row, col)]
            seen[row][col] = True
            while stack:
                y, x = stack.pop()
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = y + dy, x + dx
                    if not (0 <= ny < GRID_SIDE and 0 <= nx < GRID_SIDE):
                        continue
                    if seen[ny][nx] or grid[ny][nx] == background:
                        continue
                    seen[ny][nx] = True
                    stack.append((ny, nx))
    return components


def strip_changes(records: Sequence[Mapping], hud_reserved: str) -> bool:
    """`hud_strip_changes` — any record's strip differs from the first record's."""
    strips = [hud_strip(record["grid"], hud_reserved) for record in records]
    return any(strip != strips[0] for strip in strips[1:])


def reset_index(records: Sequence[Mapping]) -> int:
    """The reset record: the one labelled `reset`, else records[0]."""
    for index, record in enumerate(records):
        if str(record.get("label", "")).strip().lower() == RESET_LABEL:
            return index
    return 0


# --- reading the card without pinning its shape ------------------------------

_MISSING = object()


def dig(container, name: str, depth: int = 2):
    """`name` on this mapping, or one/two levels inside it — shape stays unpinned."""
    if not isinstance(container, Mapping):
        return _MISSING
    if name in container:
        return container[name]
    if depth <= 0:
        return _MISSING
    for value in container.values():
        found = dig(value, name, depth - 1)
        if found is not _MISSING:
            return found
    return _MISSING


def key_map(container) -> list[str]:
    """Every key the card offers at the two levels `dig` searches — for failures."""
    if not isinstance(container, Mapping):
        return []
    keys = list(map(str, container))
    for value in container.values():
        if isinstance(value, Mapping):
            keys.extend(f"{k}" for k in value)
    return sorted(set(keys))


def card_records(card: Mapping, expected: int) -> list[Mapping]:
    """The card's per-record block, however it is nested."""
    for name in ("records", "frames", "per_record", "record_metrics", "records_metrics"):
        found = dig(card, name)
        if isinstance(found, Sequence) and not isinstance(found, (str, bytes)):
            entries = list(found)
            if entries and all(isinstance(entry, Mapping) for entry in entries):
                return entries
        if isinstance(found, Mapping) and all(
            isinstance(entry, Mapping) for entry in found.values()
        ):
            return list(found.values())
    pytest.fail(
        f"the visual card carries no per-record block (looked for records / frames / "
        f"per_record, at the top level and one level in; the card's keys are "
        f"{key_map(card)}).  Every frozen metric below is defined PER RECORD, so "
        f"there is nothing to compare against the {expected} records of the sidecar"
    )


def metric(name: str, record: Mapping, card: Mapping, *, game: str, index: int):
    """One frozen metric, looked up on the record first and the card second."""
    found = dig(record, name)
    if found is _MISSING:
        found = dig(card, name)
    if found is _MISSING:
        pytest.fail(
            f"{game} record {index}: the visual card carries no {name!r}.  It is one of "
            f"the contract's frozen per-record metrics; the record offers "
            f"{key_map(record)} and the card offers {key_map(card)}"
        )
    return found


def optional_metric(name: str, record: Mapping, card: Mapping):
    """Like `metric`, but absence is an answer (pin 7's `absent/None`)."""
    found = dig(record, name)
    if found is _MISSING:
        found = dig(card, name)
    return found


def as_count(value, *, what: str) -> int:
    """An int count, or the count inside a small wrapper."""
    if isinstance(value, bool):
        pytest.fail(f"{what} came back as a bool, not a count")
    if isinstance(value, int):
        return value
    if isinstance(value, Mapping):
        for key in ("count", "components", "objects", "value", "n"):
            if key in value and isinstance(value[key], int):
                return value[key]
    pytest.fail(f"{what} came back as {value!r}, which carries no integer count")


def as_scale_map(value, *, what: str) -> dict[str, float]:
    """`block_uniformity` as {scale-as-string: fraction}, whatever it was built as."""
    if isinstance(value, Mapping):
        return {str(key): entry for key, entry in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        out: dict[str, float] = {}
        for entry in value:
            if isinstance(entry, Mapping):
                scale = entry.get("scale", entry.get("s", entry.get("size")))
                share = entry.get("fraction", entry.get("uniform", entry.get("value")))
                if scale is not None and share is not None:
                    out[str(scale)] = share
                    continue
            if isinstance(entry, Sequence) and not isinstance(entry, (str, bytes)):
                pair = list(entry)
                if len(pair) == 2:
                    out[str(pair[0])] = pair[1]
                    continue
            pytest.fail(f"{what} carries an entry this suite cannot read: {entry!r}")
        return out
    pytest.fail(f"{what} came back as {value!r}, which is neither a map nor a list")


def flat_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for entry in value.values() for text in flat_strings(entry)]
    if isinstance(value, Sequence):
        return [text for entry in value for text in flat_strings(entry)]
    return []


def jsonish(value):
    """Tuples to lists, keys to strings, numbers to floats — json's own shape."""
    if isinstance(value, Mapping):
        return {str(key): jsonish(entry) for key, entry in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonish(entry) for entry in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return value


def as_hex(channels: Sequence[int]) -> str:
    red, green, blue = (int(channel) for channel in channels)
    return f"#{red:02x}{green:02x}{blue:02x}"


def canon_hexes(source: str) -> set[str]:
    """Every colour the canon capture tool states, as lowercase #rrggbb.

    AMBIGUITY RESOLVED: the canon file carries the authoritative palette as RGB
    tuples, not as hex, so "appears in that file" is read as "that file states
    that colour".  Literal hexes are collected too, so this keeps working if the
    canon ever switches encodings.
    """
    hexes = {match.lower() for match in re.findall(r"#[0-9a-fA-F]{6}", source)}
    for red, green, blue in re.findall(
        r"\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", source
    ):
        channels = (int(red), int(green), int(blue))
        if all(channel <= 255 for channel in channels):
            hexes.add(as_hex(channels))
    return hexes


def canon_palette_list(source: str) -> list[str] | None:
    """The canon `PALETTE = [...]` list, in index order, as #rrggbb — or None."""
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - canon is python, but never assume
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "PALETTE" not in names:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            return None
        if not isinstance(value, (list, tuple)):
            return None
        out = []
        for entry in value:
            if not (isinstance(entry, (list, tuple)) and len(entry) == 3):
                return None
            out.append(as_hex(entry))
        return out
    return None


# --- staging (nothing is ever built inside the shipped corpus) ---------------


def stage(source: Path, dest: Path, *, frames=None, spec=None) -> Path:
    """The two sidecars copied into tmp_path, optionally doctored on the way."""
    dest.mkdir(parents=True, exist_ok=True)
    if frames is None:
        shutil.copyfile(source / FRAMES_NAME, dest / FRAMES_NAME)
    else:
        payload = json.loads((source / FRAMES_NAME).read_text(encoding="utf-8"))
        (dest / FRAMES_NAME).write_text(
            json.dumps(frames(payload), indent=2) + "\n", encoding="utf-8"
        )
    if spec is None:
        shutil.copyfile(source / SPEC_NAME, dest / SPEC_NAME)
    else:
        document = yaml.safe_load((source / SPEC_NAME).read_text(encoding="utf-8"))
        (dest / SPEC_NAME).write_text(
            yaml.safe_dump(spec(document), sort_keys=False, allow_unicode=True, width=4096),
            encoding="utf-8",
        )
    return dest


def frames_of(spec_dir: Path) -> dict:
    return json.loads((spec_dir / FRAMES_NAME).read_text(encoding="utf-8"))


def game_of(spec_dir: Path) -> dict:
    document = yaml.safe_load((spec_dir / SPEC_NAME).read_text(encoding="utf-8"))
    return document.get("game") or {}


# --- fixtures ---------------------------------------------------------------


@pytest.fixture(scope="session")
def s3_visual():
    """The module the contract freezes — imported, never read, while this was written."""
    try:
        import gen.s3_visual as module
    except ImportError as exc:  # pragma: no cover - the pre-implementation state
        pytest.fail(
            f"gen.s3_visual does not import ({exc}) — the b003 visual-card contract "
            "freezes it as the home of build_visual_card, visual_card_mode, "
            "l1_floor_mode and ARC_PALETTE_HEX.  Every pin in this file depends on it"
        )
    return module


@pytest.fixture(scope="session")
def build_visual_card(s3_visual):
    builder = getattr(s3_visual, "build_visual_card", None)
    if builder is None:
        pytest.fail(
            "gen.s3_visual exposes no build_visual_card(spec_dir, cfg) — the contract "
            "freezes that signature as the whole entry point to the report card"
        )
    return builder


@pytest.fixture(scope="session")
def visual_card_mode(s3_visual):
    reader = getattr(s3_visual, "visual_card_mode", None)
    if reader is None:
        pytest.fail("gen.s3_visual exposes no visual_card_mode(cfg)")
    return reader


@pytest.fixture(scope="session")
def l1_floor_mode(s3_visual):
    reader = getattr(s3_visual, "l1_floor_mode", None)
    if reader is None:
        pytest.fail("gen.s3_visual exposes no l1_floor_mode(cfg)")
    return reader


@pytest.fixture(scope="session")
def base_cfg() -> dict:
    """The b002 config — the batch every shipped game in `out/corpus` was built under."""
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="session")
def record_cfg(base_cfg: dict) -> dict:
    """`{gate: {visual_card: "record"}}` over whatever minimal keys the builder needs."""
    return {**base_cfg, "gate": {"visual_card": "record"}}


@pytest.fixture(scope="session")
def docs_root(base_cfg: dict) -> Path:
    root = Path(base_cfg["duckwm_docs"]).resolve()
    assert root.is_dir(), (
        f"the config's duckwm_docs resolves to {root}, which is not a directory — run "
        "pytest from the repo root (every sibling suite loads the config by its "
        "relative path)"
    )
    return root


@pytest.fixture(scope="session")
def built(
    build_visual_card, record_cfg: dict, tmp_path_factory: pytest.TempPathFactory
) -> dict:
    """One card per shipped game, built once, in tmp_path — never in `out/corpus`."""
    out: dict[str, dict] = {}
    for source in SHIPPED:
        spec_dir = stage(source, tmp_path_factory.mktemp("b003vc") / source.name)
        card = build_visual_card(spec_dir, record_cfg)
        out[source.name] = {
            "source": source,
            "spec_dir": spec_dir,
            "card": card,
            "frames": frames_of(spec_dir),
            "game": game_of(spec_dir),
        }
    return out


@pytest.fixture
def case(built: dict, game: str) -> dict:
    if game not in built:
        pytest.fail(f"{game} was discovered under out/corpus but no card was built for it")
    return built[game]


def parametrized(func):
    return pytest.mark.parametrize("game", SHIPPED_IDS, ids=SHIPPED_IDS)(func)


def records_pair(case: dict) -> tuple[list[Mapping], list[Mapping], Mapping]:
    """(sidecar records, card records, card) — with their lengths agreed."""
    sidecar = case["frames"]["records"]
    card = case["card"]
    assert isinstance(card, Mapping), (
        f"build_visual_card returned a {type(card).__name__}, not the json dict the "
        "contract freezes as its return value"
    )
    reported = card_records(card, len(sidecar))
    assert len(reported) == len(sidecar), (
        f"the card reports {len(reported)} records but the sidecar carries "
        f"{len(sidecar)} — every frozen metric is defined per record, so a card that "
        "drops or invents one is not measuring the run it was handed"
    )
    return sidecar, reported, card


# --- 0. the corpus this suite measures --------------------------------------


def test_the_shipped_corpus_offers_enough_games_to_measure():
    assert len(SHIPPED) >= 3, (
        f"only {len(SHIPPED)} shipped spec dirs under {CORPUS_ROOT} carry both "
        f"{FRAMES_NAME} and {SPEC_NAME} (found {SHIPPED_IDS}); the contract expects "
        f"{EXPECTED_SHIPPED} and requires at least 3.  The double-implementation pin "
        "is the whole suite, and it has nothing real to run against below that"
    )
    if len(SHIPPED) != EXPECTED_SHIPPED:
        pytest.skip(
            f"NOTE (not a failure): the corpus has {len(SHIPPED)} games, not the "
            f"contract's {EXPECTED_SHIPPED} — {SHIPPED_IDS}"
        )


@parametrized
def test_every_shipped_sidecar_is_the_64x64_grid_the_metrics_assume(case: dict, game: str):
    for index, record in enumerate(case["frames"]["records"]):
        grid = record["grid"]
        assert len(grid) == GRID_SIDE, f"{game} record {index}: {len(grid)} rows, not 64"
        assert all(len(row) == GRID_SIDE for row in grid), (
            f"{game} record {index}: a row is not 64 wide — every frozen metric "
            "(the HUD strip, the block scales, the components) assumes a 64x64 camera"
        )


# --- 1. the double implementation, on real games ----------------------------


@parametrized
def test_the_card_writes_the_three_frozen_files(case: dict, game: str):
    gate_dir = case["spec_dir"] / GATE_DIRNAME
    for name in REPORT_NAMES:
        path = gate_dir / name
        assert path.is_file(), (
            f"{game}: {path} was not written.  The contract freezes the card's three "
            f"artifacts as {GATE_DIRNAME}/{REPORT_NAMES} — they land beside the gate's "
            "other reports so a reviewer finds them where every other verdict lives"
        )
        assert path.stat().st_size > 0, f"{game}: {path} is empty"


@parametrized
def test_the_returned_paths_point_at_those_three_files(case: dict, game: str):
    card = case["card"]
    raw = dig(card, "paths")
    assert raw is not _MISSING, (
        f"{game}: the returned dict carries no 'paths' key.  The contract freezes it "
        f"as the caller's handle on the three artifacts; the card offers {key_map(card)}"
    )
    gate_dir = (case["spec_dir"] / GATE_DIRNAME).resolve()
    resolved = {}
    for text in flat_strings(raw):
        path = Path(text)
        if not path.is_absolute():
            path = case["spec_dir"] / path
        resolved[path.name] = path.resolve()
    assert set(resolved) == set(REPORT_NAMES), (
        f"{game}: the returned paths name {sorted(resolved)}, not the frozen "
        f"{sorted(REPORT_NAMES)}"
    )
    for name, path in resolved.items():
        assert path.is_file(), f"{game}: the returned path {path} does not exist"
        assert path.parent == gate_dir, (
            f"{game}: {name} was returned at {path.parent}, not in {gate_dir}"
        )


@parametrized
def test_colors_and_color_count_match_an_independent_scan(case: dict, game: str):
    sidecar, reported, card = records_pair(case)
    for index, (source, row) in enumerate(zip(sidecar, reported, strict=True)):
        want = distinct_colors(source["grid"])
        got = metric("colors", row, card, game=game, index=index)
        assert list(got) == want, (
            f"{game} record {index}: the card reports colors {list(got)}; an "
            f"independent scan of the same grid finds {want} (sorted distinct)"
        )
        count = metric("color_count", row, card, game=game, index=index)
        assert count == len(want), (
            f"{game} record {index}: color_count is {count}, but the grid carries "
            f"{len(want)} distinct indices"
        )


@parametrized
def test_declared_absent_names_the_roles_the_grid_never_shows(case: dict, game: str):
    sidecar, reported, card = records_pair(case)
    palette = case["game"].get("palette") or {}
    for index, (source, row) in enumerate(zip(sidecar, reported, strict=True)):
        want = declared_absent(source["grid"], palette)
        got = metric("declared_absent", row, card, game=game, index=index)
        # AMBIGUITY: the contract freezes role NAMES, never their order.
        assert sorted(got) == sorted(want), (
            f"{game} record {index}: declared_absent is {sorted(got)}; the spec declares "
            f"{ {role: palette.get(role) for role in PALETTE_ROLES if role in palette} } "
            f"and an independent scan finds {sorted(want)} missing from the grid.  A "
            "declared role with no pixels on the board is the card's sharpest single "
            "signal that a game does not render what its spec promised"
        )


@parametrized
def test_reserved_on_board_reads_the_strip_the_spec_declares(case: dict, game: str):
    sidecar, reported, card = records_pair(case)
    hud = (case["game"].get("hud") or {}).get("reserved")
    # A non-strip hud is legal §11 (tidegate-mosaic, b004, declares custom-rect)
    # and belongs to the custom-rect pin — this sweep's premise, not a failure.
    # Was an assert until the first custom-rect game shipped (2026-09-29).
    if hud not in (*STRIP_ROW, STRIP_COL):
        pytest.skip(f"hud.reserved {hud!r} is not a strip form — covered by its own pin")
    reserved = (case["game"].get("palette") or {}).get("reserved") or []
    for index, (source, row) in enumerate(zip(sidecar, reported, strict=True)):
        want = reserved_on_board(source["grid"], reserved, hud)
        got = metric("reserved_on_board", row, card, game=game, index=index)
        assert sorted(got) == want, (
            f"{game} record {index}: reserved_on_board is {sorted(got)}; with "
            f"hud.reserved={hud!r} and palette.reserved={sorted(reserved)} an "
            f"independent scan of everything off that strip finds {want}"
        )


@parametrized
def test_the_hud_strip_values_are_read_off_the_declared_strip(case: dict, game: str):
    sidecar, reported, card = records_pair(case)
    hud = (case["game"].get("hud") or {}).get("reserved")
    if hud not in (*STRIP_ROW, STRIP_COL):
        pytest.skip(f"hud.reserved {hud!r} is not a strip form — covered by its own pin")
    for index, (source, row) in enumerate(zip(sidecar, reported, strict=True)):
        strip = hud_strip(source["grid"], hud)
        got = metric("hud_strip_values", row, card, game=game, index=index)
        # AMBIGUITY: `colors` is explicitly "sorted distinct" and this key carries
        # no qualifier, so the raw strip and its sorted-distinct form both pass.
        assert list(got) in (strip, sorted(set(strip))), (
            f"{game} record {index}: hud_strip_values is {list(got)}; with "
            f"hud.reserved={hud!r} the strip is {strip} (distinct: "
            f"{sorted(set(strip))}).  The strip is where a meter is allowed to live, "
            "so reading the wrong row makes every reserved-leak verdict meaningless"
        )


@parametrized
def test_hud_strip_changes_reports_whether_the_strip_ever_moves(case: dict, game: str):
    sidecar, reported, card = records_pair(case)
    hud = (case["game"].get("hud") or {}).get("reserved")
    if hud not in (*STRIP_ROW, STRIP_COL):
        pytest.skip(f"hud.reserved {hud!r} is not a strip form — covered by its own pin")
    run_level = strip_changes(sidecar, hud)
    first = hud_strip(sidecar[0]["grid"], hud)
    for index, (source, row) in enumerate(zip(sidecar, reported, strict=True)):
        got = metric("hud_strip_changes", row, card, game=game, index=index)
        # AMBIGUITY: "any record's strip differs from the first record's" is a
        # run-level fact stated in a per-record list; per-record it may instead
        # carry the this-record-differs reading.
        allowed = {run_level, hud_strip(source["grid"], hud) != first}
        assert got in allowed, (
            f"{game} record {index}: hud_strip_changes is {got!r}; over this run the "
            f"strip {'does' if run_level else 'does not'} change.  A strip that never "
            "moves is a HUD that shows the player nothing"
        )


@parametrized
def test_the_run_length_profile_matches_an_independent_scan(case: dict, game: str):
    sidecar, reported, card = records_pair(case)
    for index, (source, row) in enumerate(zip(sidecar, reported, strict=True)):
        lengths = horizontal_runs(source["grid"])
        profile = metric("run_length_profile", row, card, game=game, index=index)
        assert isinstance(profile, Mapping), (
            f"{game} record {index}: run_length_profile is {profile!r}, not a mapping "
            "carrying mode / median / ones_share"
        )
        modes = run_length_modes(lengths)
        got_mode = dig(profile, "mode")
        assert got_mode is not _MISSING, (
            f"{game} record {index}: run_length_profile carries no 'mode' "
            f"({key_map(profile)})"
        )
        # AMBIGUITY: the contract gives a tie rule for objects_cc's modal value
        # and none for this mode, and the shipped corpus really does tie (see the
        # module docstring).  A tied record accepts any tied mode; 39 of the 40
        # shipped records have a single mode and are pinned exactly.
        assert got_mode in modes, (
            f"{game} record {index}: the run-length mode is {got_mode!r}; an "
            f"independent scan of {len(lengths)} horizontal runs finds "
            f"{'mode ' + str(modes[0]) if len(modes) == 1 else 'tied modes ' + str(modes)}"
        )
        got_median = dig(profile, "median")
        assert got_median == pytest.approx(run_length_median(lengths), abs=5e-5), (
            f"{game} record {index}: the run-length median is {got_median!r}, not "
            f"{run_length_median(lengths)!r}"
        )
        got_ones = dig(profile, "ones_share")
        assert got_ones == pytest.approx(run_length_ones_share(lengths), abs=5e-5), (
            f"{game} record {index}: ones_share is {got_ones!r}, not "
            f"{run_length_ones_share(lengths)!r} ("
            f"{sum(1 for length in lengths if length == 1)} of {len(lengths)} runs are "
            "length 1).  A board that is mostly 1-cell runs is the per-cell noise the "
            "craft note forbids"
        )


@parametrized
def test_block_uniformity_matches_an_independent_scan(case: dict, game: str):
    sidecar, reported, card = records_pair(case)
    for index, (source, row) in enumerate(zip(sidecar, reported, strict=True)):
        want = block_uniformity(source["grid"])
        raw = metric("block_uniformity", row, card, game=game, index=index)
        got = as_scale_map(raw, what=f"{game} record {index}: block_uniformity")
        assert set(got) == set(want), (
            f"{game} record {index}: block_uniformity covers scales {sorted(got)}; the "
            f"contract freezes {sorted(want)} — the official tile-scale menu, which is "
            "how the card infers what scale a generated game actually drew at"
        )
        for scale in want:
            assert got[scale] == pytest.approx(want[scale], abs=5e-5), (
                f"{game} record {index}: block_uniformity[{scale}] is {got[scale]!r}, "
                f"not {want[scale]!r} (aligned {scale}x{scale} blocks from the origin, "
                f"{GRID_SIDE // int(scale)} per axis, the remainder ignored)"
            )


@parametrized
def test_objects_cc_matches_an_independent_flood_fill(case: dict, game: str):
    sidecar, reported, card = records_pair(case)
    for index, (source, row) in enumerate(zip(sidecar, reported, strict=True)):
        want = objects_cc(source["grid"])
        raw = metric("objects_cc", row, card, game=game, index=index)
        got = as_count(raw, what=f"{game} record {index}: objects_cc")
        assert got == want, (
            f"{game} record {index}: objects_cc is {got}; an independent 4-connected "
            f"flood fill over the cells that are not the modal value "
            f"({modal_value(source['grid'])}) finds {want}"
        )


@parametrized
def test_the_l1_colour_floor_reads_the_reset_record(case: dict, game: str):
    sidecar, _reported, card = records_pair(case)
    floor = dig(card, "l1_color_floor")
    assert floor is not _MISSING and isinstance(floor, Mapping), (
        f"{game}: the card carries no l1_color_floor mapping ({key_map(card)}).  It is "
        "the one measured number on the card with a pass/fail face"
    )
    index = reset_index(sidecar)
    want = len(distinct_colors(sidecar[index]["grid"]))
    assert dig(floor, "colors") == want, (
        f"{game}: l1_color_floor.colors is {dig(floor, 'colors')!r}; the reset record "
        f"(index {index}, label {sidecar[index].get('label')!r}) carries {want} "
        "distinct indices"
    )
    assert dig(floor, "floor") == L1_FLOOR, (
        f"{game}: l1_color_floor.floor is {dig(floor, 'floor')!r}, not the frozen "
        f"{L1_FLOOR}"
    )
    assert dig(floor, "mode") == L1_FLOOR_DEFAULT, (
        f"{game}: l1_color_floor.mode is {dig(floor, 'mode')!r}; this build passed no "
        f"gate.l1_color_floor, so the default {L1_FLOOR_DEFAULT!r} must be recorded"
    )


def test_the_frozen_floor_is_the_officials_own_level_one_minimum():
    """Grounding, not a second copy: 4 is the corpus minimum, not a chosen number."""
    band = OFFICIAL_VISUAL_CONSTANTS["l1_colors"]
    assert min(band) == L1_FLOOR, (
        f"the frozen l1 floor is {L1_FLOOR} but the measured official level-1 colour "
        f"band is {band}, whose minimum is {min(band)}.  One of the two moved: either "
        "re-measure the corpus or reopen the contract, but they cannot disagree"
    )


@parametrized
def test_the_official_bands_are_the_imported_constants(case: dict, game: str):
    card = case["card"]
    bands = dig(card, "official_bands")
    assert bands is not _MISSING, (
        f"{game}: the card carries no official_bands ({key_map(card)}) — the measured "
        "corpus numbers are what every metric above is READ AGAINST; a card without "
        "them reports numbers with nothing to compare them to"
    )
    assert jsonish(bands) == jsonish(OFFICIAL_VISUAL_CONSTANTS), (
        f"{game}: official_bands is not gen.visual_canon.OFFICIAL_VISUAL_CONSTANTS.  "
        f"Card: {jsonish(bands)!r}.  Import: {jsonish(OFFICIAL_VISUAL_CONSTANTS)!r}.  "
        "The bands must be RENDERED from the pinned constants, never retyped — a "
        "second copy drifts away from the citations that justify it"
    )
    written = json.loads(
        (case["spec_dir"] / GATE_DIRNAME / REPORT_JSON).read_text(encoding="utf-8")
    )
    assert jsonish(dig(written, "official_bands")) == jsonish(OFFICIAL_VISUAL_CONSTANTS), (
        f"{game}: the returned dict carries the right bands but the written "
        f"{REPORT_JSON} does not — the file is what a reviewer reads"
    )


# --- 2. zero-would-fail: the shipped corpus clears the floor -----------------


@parametrized
def test_every_shipped_game_clears_the_l1_colour_floor(case: dict, game: str):
    floor = dig(case["card"], "l1_color_floor")
    assert isinstance(floor, Mapping), f"{game}: no l1_color_floor mapping on the card"
    assert dig(floor, "passed") is True, (
        f"{game}: l1_color_floor.passed is {dig(floor, 'passed')!r} with "
        f"{dig(floor, 'colors')!r} colours against a floor of {L1_FLOOR}.  Every "
        "ACCEPTED game in the shipped corpus clears this floor: a floor that would "
        "have failed work already signed off is a floor set in the wrong place, and "
        "turning gate.l1_color_floor to 'fail' would retroactively kill a packaged game"
    )


# --- 3. determinism ---------------------------------------------------------


@parametrized
def test_two_builds_are_byte_identical(
    case: dict, game: str, build_visual_card, record_cfg: dict
):
    gate_dir = case["spec_dir"] / GATE_DIRNAME
    before = {name: (gate_dir / name).read_bytes() for name in (REPORT_JSON, CONTACT_SHEET)}
    build_visual_card(case["spec_dir"], record_cfg)
    after = {name: (gate_dir / name).read_bytes() for name in (REPORT_JSON, CONTACT_SHEET)}
    for name, first in before.items():
        assert first == after[name], (
            f"{game}: rebuilding the card in the same directory produced a different "
            f"{name}.  Every input is a fixed file and every metric is an ordered scan, "
            "so a difference is a clock, a run id, or an unordered set leaking into a "
            "report that reviewers are meant to diff between rounds"
        )


# --- 4. the knobs -----------------------------------------------------------


def test_the_knob_defaults_are_off_and_record(visual_card_mode, l1_floor_mode):
    assert visual_card_mode({}) == VISUAL_CARD_DEFAULT, (
        "a config with no gate block must leave the visual card OFF.  The card is new "
        "machinery on the gate's path; a batch that never heard of it must behave "
        "exactly as it did before the card existed"
    )
    assert l1_floor_mode({}) == L1_FLOOR_DEFAULT, (
        "a config with no gate block must leave the l1 colour floor in 'record' mode — "
        "it measures and reports, it does not yet kill"
    )


def test_an_empty_gate_block_is_the_same_as_no_gate_block(visual_card_mode, l1_floor_mode):
    # INFERRED from "closed key set + per-key defaults": an empty block declares
    # no knob, so every knob is its default (the `tiers.tier_policy` pattern).
    assert visual_card_mode({"gate": {}}) == VISUAL_CARD_DEFAULT
    assert l1_floor_mode({"gate": {}}) == L1_FLOOR_DEFAULT


def test_the_record_and_fail_pair_parses(visual_card_mode, l1_floor_mode):
    cfg = {"gate": {"visual_card": "record", "l1_color_floor": "fail"}}
    assert visual_card_mode(cfg) == "record"
    assert l1_floor_mode(cfg) == "fail"


@pytest.mark.parametrize("mode", VISUAL_CARD_MODES)
def test_every_visual_card_mode_in_the_enum_parses(mode: str, visual_card_mode):
    assert visual_card_mode({"gate": {"visual_card": mode}}) == mode


@pytest.mark.parametrize("mode", L1_FLOOR_MODES)
def test_every_l1_floor_mode_in_the_enum_parses(mode: str, l1_floor_mode):
    assert l1_floor_mode({"gate": {"l1_color_floor": mode}}) == mode


@pytest.mark.parametrize("bad", ["on", "true", "Record", "off ", "kill", ""])
def test_a_visual_card_value_outside_the_enum_is_a_valueerror(bad: str, visual_card_mode):
    with pytest.raises(ValueError):
        visual_card_mode({"gate": {"visual_card": bad}})


@pytest.mark.parametrize("bad", ["off", "warn", "Fail", "record-only", ""])
def test_an_l1_floor_value_outside_the_enum_is_a_valueerror(bad: str, l1_floor_mode):
    with pytest.raises(ValueError):
        l1_floor_mode({"gate": {"l1_color_floor": bad}})


@pytest.mark.parametrize("stray", ["colour_floor", "visual-card", "l1_colour_floor", "cards"])
def test_an_unknown_gate_key_is_a_valueerror_from_both_readers(
    stray: str, visual_card_mode, l1_floor_mode
):
    cfg = {"gate": {"visual_card": "record", stray: "fail"}}
    with pytest.raises(ValueError):
        visual_card_mode(cfg)
    with pytest.raises(ValueError):
        l1_floor_mode(cfg)


def test_the_gate_block_is_closed_over_exactly_the_two_frozen_keys(
    visual_card_mode, l1_floor_mode
):
    """Both frozen keys together are accepted; nothing else is."""
    cfg = {"gate": dict.fromkeys(GATE_KEYS, "record")}
    assert visual_card_mode(cfg) == "record"
    assert l1_floor_mode(cfg) == "record"


# --- 5. the floor's failing arm ---------------------------------------------


@pytest.fixture(scope="session")
def flat_reset(
    build_visual_card, record_cfg: dict, tmp_path_factory: pytest.TempPathFactory
) -> dict:
    """The first shipped game with its reset grid painted a single colour."""
    if not SHIPPED:
        pytest.skip("no shipped spec dirs to doctor")

    def flatten(payload: dict) -> dict:
        records = payload["records"]
        index = reset_index(records)
        records[index]["grid"] = [[0] * GRID_SIDE for _ in range(GRID_SIDE)]
        return payload

    spec_dir = stage(
        SHIPPED[0], tmp_path_factory.mktemp("b003vcflat") / SHIPPED[0].name, frames=flatten
    )
    card = build_visual_card(spec_dir, record_cfg)
    return {"spec_dir": spec_dir, "card": card}


def test_a_one_colour_reset_fails_the_floor(flat_reset: dict):
    floor = dig(flat_reset["card"], "l1_color_floor")
    assert isinstance(floor, Mapping), "the doctored build carries no l1_color_floor"
    assert dig(floor, "colors") == 1, (
        f"the reset grid was painted a single value but l1_color_floor.colors is "
        f"{dig(floor, 'colors')!r}"
    )
    assert dig(floor, "passed") is False, (
        f"a level-1 board showing ONE colour reports passed={dig(floor, 'passed')!r} "
        f"against a floor of {L1_FLOOR}.  The officials' level-1 minimum is the floor; "
        "a single-colour first frame teaches the player nothing at all"
    )


def test_record_mode_still_writes_every_file_when_the_floor_fails(flat_reset: dict):
    gate_dir = flat_reset["spec_dir"] / GATE_DIRNAME
    for name in REPORT_NAMES:
        assert (gate_dir / name).is_file(), (
            f"{name} was not written for a game that fails the floor.  In 'record' mode "
            "the card never raises and never withholds a report: it measures, writes, "
            "and leaves the verdict alone"
        )


def test_the_markdown_report_mentions_the_floor_it_failed(flat_reset: dict):
    text = (flat_reset["spec_dir"] / GATE_DIRNAME / REPORT_MD).read_text(encoding="utf-8")
    assert "floor" in text.lower(), (
        "the markdown report never says the word 'floor' for a game that failed it.  "
        "The .md is the human face of the card; a failure only the json knows about is "
        f"a failure nobody reads.  Report was:\n{text[:1200]}"
    )


# --- 6. the palette ---------------------------------------------------------


@pytest.fixture(scope="session")
def palette_hex(s3_visual) -> list[str]:
    entry = getattr(s3_visual, "ARC_PALETTE_HEX", None)
    if entry is None:
        pytest.fail(
            "gen.s3_visual exposes no ARC_PALETTE_HEX — the contact sheet renders grid "
            "indices through it, so it is the card's only claim to showing the colours "
            "the engine actually draws"
        )
    return list(entry)


def test_the_palette_is_sixteen_rrggbb_entries(palette_hex: list[str]):
    assert len(palette_hex) == 16, (
        f"ARC_PALETTE_HEX has {len(palette_hex)} entries, not 16 — the ARC palette is "
        "16 indices and the contact sheet indexes it with a raw grid value"
    )
    bad = [entry for entry in palette_hex if not (isinstance(entry, str) and HEX_RE.match(entry))]
    assert not bad, f"ARC_PALETTE_HEX carries entries that are not #RRGGBB: {bad}"


@pytest.fixture(scope="session")
def capture_frames_source(docs_root: Path) -> str:
    path = docs_root / CAPTURE_FRAMES_REL
    if not path.is_file():
        pytest.skip(
            f"the canon capture tool is not on this machine ({path} is missing), so "
            "ARC_PALETTE_HEX CANNOT be checked against the authoritative render "
            "palette and the drift guard is not running.  GEN was resolved from the "
            f"b002 config's duckwm_docs as {docs_root}"
        )
    return path.read_text(encoding="utf-8")


def test_every_palette_entry_is_a_colour_the_canon_tool_states(
    palette_hex: list[str], capture_frames_source: str
):
    # AMBIGUITY RESOLVED: the canon file states the palette as RGB tuples, not
    # hex, so "appears in that file" is read as "that file states that colour".
    stated = canon_hexes(capture_frames_source)
    assert stated, (
        f"GEN {CAPTURE_FRAMES_REL} states no colours this suite can parse — neither "
        "#RRGGBB literals nor RGB triples.  The provenance of ARC_PALETTE_HEX can no "
        "longer be checked; re-read the canon tool before touching this pin"
    )
    missing = [entry for entry in palette_hex if entry.lower() not in stated]
    assert not missing, (
        f"ARC_PALETTE_HEX carries {missing}, which GEN {CAPTURE_FRAMES_REL} never "
        "states.  That file cites the engine's own ARC_COLOR_MAP as the authoritative "
        "render palette: a colour invented here makes the contact sheet a picture of a "
        "game nobody is playing"
    )


def test_the_palette_is_the_canon_palette_in_index_order(
    palette_hex: list[str], capture_frames_source: str
):
    """STRONGER THAN THE CONTRACT'S LETTER, on purpose — isolate it if the lead disagrees.

    The contract pins membership only.  But a palette indexed by a raw grid value
    has exactly one meaningful order, and the canon tool renders with
    ``PALETTE[clamp(value)]``; an entry at the wrong index paints the wrong colour
    while passing every membership check.
    """
    canon = canon_palette_list(capture_frames_source)
    if canon is None:
        pytest.skip(
            f"GEN {CAPTURE_FRAMES_REL} no longer carries a literal `PALETTE = [...]` "
            "list this suite can parse, so index order cannot be checked"
        )
    assert [entry.lower() for entry in palette_hex] == canon, (
        "ARC_PALETTE_HEX is not the canon render palette in index order.  Card: "
        f"{[entry.lower() for entry in palette_hex]}.  Canon: {canon}"
    )


# --- 7. custom-rect: the one HUD form the card cannot check ------------------


@pytest.fixture(scope="session")
def custom_rect(
    build_visual_card, record_cfg: dict, tmp_path_factory: pytest.TempPathFactory
) -> dict:
    """The first shipped game with `hud.reserved` doctored to `custom-rect`."""
    if not SHIPPED:
        pytest.skip("no shipped spec dirs to doctor")

    def rewrite(document: dict) -> dict:
        document["game"]["hud"]["reserved"] = CUSTOM_RECT
        return document

    spec_dir = stage(
        SHIPPED[0], tmp_path_factory.mktemp("b003vcrect") / SHIPPED[0].name, spec=rewrite
    )
    card = build_visual_card(spec_dir, record_cfg)
    return {"spec_dir": spec_dir, "card": card, "frames": frames_of(spec_dir)}


def test_a_custom_rect_hud_reports_the_reserved_check_as_not_checked(custom_rect: dict):
    card = custom_rect["card"]
    text = json.dumps(card, default=str) + (
        custom_rect["spec_dir"] / GATE_DIRNAME / REPORT_MD
    ).read_text(encoding="utf-8")
    assert NOT_CHECKED_RE.search(text), (
        f"a spec declaring hud.reserved: {CUSTOM_RECT!r} produces a card that never "
        "says 'not-checked'.  The card cannot know where a custom rectangle sits, so "
        "it cannot tell a reserved index on the HUD from one leaked onto the board — "
        "and a silently skipped check reads exactly like a passed one"
    )


def test_a_custom_rect_hud_reports_no_reserved_on_board(custom_rect: dict):
    card = custom_rect["card"]
    reported = card_records(card, len(custom_rect["frames"]["records"]))
    for index, row in enumerate(reported):
        got = optional_metric("reserved_on_board", row, card)
        assert got is _MISSING or got is None, (
            f"record {index}: reserved_on_board is {got!r} for a custom-rect HUD.  With "
            "no strip to exclude, any value the card puts here is a guess presented as "
            "a measurement"
        )


# --- 8. the orchestrator seam (source-level; the runner is never run) --------


@pytest.fixture(scope="session")
def orchestrator_source() -> str:
    assert ORCHESTRATOR_SOURCE.is_file(), f"{ORCHESTRATOR_SOURCE} does not exist"
    return ORCHESTRATOR_SOURCE.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def s3_gate_runner_body(orchestrator_source: str) -> str:
    """The `def s3_gate(...)` runner, sliced out of the file as TEXT.

    Source-level on purpose: running the real runner needs a live worker, a
    capture and a driver, none of which belong in this suite.
    """
    lines = orchestrator_source.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if re.match(r"^\s*def s3_gate\(", line)]
    assert len(starts) == 1, (
        f"gen/orchestrator.py defines {len(starts)} `def s3_gate(` runners; this pin "
        "assumes exactly one"
    )
    start = starts[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        here = len(line) - len(line.lstrip())
        if here <= indent and re.match(r"^\s*(def |class |@)", line):
            end = index
            break
    return "".join(lines[start:end])


@pytest.mark.parametrize("name", SEAM_NAMES)
def test_the_orchestrator_carries_the_visual_card_seam(name: str, orchestrator_source: str):
    # AMBIGUITY RESOLVED: pinned at FILE level.  A runner that calls a
    # module-level helper is a legitimate implementation, and the contract's own
    # wording for the guard is "the words ... appear".
    assert name in orchestrator_source, (
        f"gen/orchestrator.py never mentions {name!r}.  The card is built on the gate's "
        "path or it is built nowhere: a report nothing calls is a report that silently "
        "stops being written the first time the pipeline changes shape"
    )


def test_the_seam_is_inside_the_s3_gate_runner(s3_gate_runner_body: str):
    assert "visual" in s3_gate_runner_body, (
        "the s3_gate runner's body never mentions anything visual, so the card is "
        "wired into some other stage.  The contract puts it at the gate, where the "
        f"other reports are written.  Body:\n{s3_gate_runner_body}"
    )


def test_card_failure_cannot_change_the_gate_verdict(orchestrator_source: str):
    assert "visual_card_error" in orchestrator_source, (
        "gen/orchestrator.py never uses the word 'visual_card_error'.  That word is the "
        "contract's proxy for the guard: a card that raises — a malformed sidecar, a "
        "PIL failure, a palette index out of range — must be caught, recorded under "
        "that name, and must leave the gate's verdict exactly where it was.  Measurement "
        "machinery must never be able to fail a game"
    )


def test_the_gate_runner_still_returns_only_its_two_verdicts(s3_gate_runner_body: str):
    """The guard's whole point: the runner's verdict surface is unchanged."""
    for verdict in ("gated", "verified"):
        assert f'"{verdict}"' in s3_gate_runner_body, (
            f"the s3_gate runner no longer returns {verdict!r}.  The visual card is a "
            "recorder: it adds an artifact, it does not add an edge to the state "
            f"machine.  Body:\n{s3_gate_runner_body}"
        )
