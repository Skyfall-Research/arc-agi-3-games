"""W3-A3 (R-09) — deception DECLARED, verified both directions. BLIND pins.

Written from the A3 contract alone, by an agent that never read the
implementation diff. The pre-state was taken from `git show HEAD:gen/s3_verify.py`
and `git show HEAD:gen/s3_static.py` only, and every "as at HEAD" number below
was MEASURED against the pristine working tree before the implementer started.

THE CONTRACT (A3, R-09)
-----------------------
§10 makes "deception is always a DECLARED property, never an accident" the
intent verifier's job, and the comparative audit (finding B4) caught it failing
in BOTH directions:

  * present-but-undeclared — pump-phase's pump/filler/block identical flat
    solids (two clickable, one not); pump-flow's four-kinds-one-silhouette;
    conduit's `deceptions: []` beside a fused seam-beacon pair.
  * declared-but-absent — pump-flow's fog-colour deception claims index 2
    while the look-alike is drawn in 3; mosaic's `refusal:visible` describes a
    flash that is not in the source.

So A3 adds two surfaces:

  1. `gen/s3_verify.py` — the blind S2b prompt gains a LOOK-ALIKE INVENTORY
     section (a prompt-synced constant), and the report schema gains an
     OPTIONAL `lookalikes` block carrying both-direction diffs
     (undeclared-found[], declared-ungrounded[]). Optional means b7-era report
     readers are unchanged, and the verifier's REJECT logic gains nothing —
     these findings feed the record and the S5 review, never a new reject.
  2. `gen/s3_static.py` — a code-side detector `static.lookalike-declared`
     (GENERATED-ONLY, the W2-B pattern, outside the officials' battery):
     families of sprites/paint sites sharing an index whose footprints match
     but whose behavior tags/handlers differ, diffed against knobs.deceptions.
     ADJACENCY-FUSION EXCLUSION is pinned: two same-index objects that render
     adjacent fuse into one component as a RENDER consequence, so conduit's
     seam pair must NOT fire. Mode off|record|fail, default record; the
     template arms record (evidence, not a gate).

HEAD PRE-STATE, measured (this is what the contract-bearing pins invert)
-----------------------------------------------------------------------
  * `validate_report` rejects ANY top-level key outside `REPORT_KEYS` +
    `OPTIONAL_REPORT_KEYS`, any diff key outside `DIFF_KEYS` + the three
    optional records, any `agent` key outside `AGENT_KEYS` and any claims key
    outside `CLAIMS_KEYS`. A `lookalikes` block therefore raises wherever it is
    put — which is exactly why PIN 1 is placement-agnostic: the contract does
    not name the block's home, so the pin asks only that SOME placement
    validates, and reports the one it found.
  * the built blind prompt (`build_verifier_prompt`, pilot config + the toy
    worker) contains the word "inventory" ZERO times, while "look-alike" /
    "lookalike" already appear 8 times inside `DECEPTION_HEADER`'s normalizer
    prose. So the new section is detected by "inventory", never by the
    look-alike stem alone, and it must arrive as a module-level CONSTANT whose
    text the prompt quotes verbatim (prompt-synced).
  * `gen.s3_static` exposes NO callable whose name mentions look-alikes, so
    every detector pin below fails at HEAD with "no detector found".
  * `run_static_checks` returns exactly the five frozen static ids, in order —
    the shape the B2-calibrated 25-official battery (200/200) counts.

VERIFIED AS SHIPPED: this file, run against a pristine `git archive HEAD`
export (the real `out/` corpus and `duckWM` linked in read-only), is 15 failed
/ 6 passed. The 15 are the contract-bearing pins below; the 6 are the
regression guards that must hold before AND after (1c, 1e, 2d, 4a, 4b, 5b).

PINS
----
1. the report's optional `lookalikes` block: (a) a report carrying it
   validates, both directions present; (b) it round-trips through
   `write_report` and back; (c) a report WITHOUT it still validates and
   `SCHEMA_VERSION` is still `b7.1` — b7-era readers unchanged; (d) the block
   holds real entries, not just empty lists.        (a,b,d fail at HEAD)
2. the prompt constant: (a) a module-level constant in `gen.s3_verify` names a
   look-alike INVENTORY; (b) the built audit prompt quotes it verbatim;
   (c) it asks BOTH directions (list what is found AND ground what is
   declared); (d) the b7-era sections survive beside it.   (a,b,c fail at HEAD)
3. the static detector `static.lookalike-declared`: (a) FIRES on a synthetic
   two-kinds-one-silhouette worker whose spec declares no deception; (b) SILENT
   when the same bytes' spec declares that look-alike; (c) SILENT on an
   adjacency-fusion fixture (the conduit seam rule, synthesized); (d) mode
   off|record|fail with default record; (e) an invalid mode value is a loud
   ValueError; (f) `config/template.yaml` arms record; (g) the paint-site
   surface fires too (the contract says "sprites/paint sites").
                                                    (a,d,e,f,g fail at HEAD)
4. generated-only: (a) the SAME BYTES staged as an official's variant dir do
   not fail — premise-not-met or pass; (b) an official dir still yields exactly
   the five frozen static ids in order (battery shape unchanged); (c) the new
   id is none of the ids HEAD already ships.            (a,c fail at HEAD)
5. the real exhibits, replayed on tmp copies: (a) pump-phase-time-echo FIRES;
   (b) conduit-watch is SILENT.                             (a fails at HEAD)

HOW THE NEW SURFACES ARE FOUND (the contract names ids, not symbols)
--------------------------------------------------------------------
The contract names the check id (`static.lookalike-declared`) but no Python
symbol, no config path and no home for the report block. A blind test may not
assume any of the three, so each is DISCOVERED:

  * the detector — every module-level function in `gen.s3_static` whose name
    mentions look-alikes or deceptions is bound from a pool of named arguments
    (the `test_w2_sysclick.py` idiom) and called; only `CheckResult`s are kept,
    and the verdict under test is the one carrying the contract's check id. The
    mode is offered BOTH ways, as a `cfg` carrying the template's own knob and
    as a bare `mode` string, because the contract fixes neither seam.
  * the mode knob — its config path is read back out of `config/template.yaml`,
    which the contract requires to arm `record`. That makes every mode pin
    path-agnostic, and it is also PIN 3f.
  * the report block — the placement and the key spelling are searched over the
    plausible set, and the accepted one is printed in the failure message.

AMBIGUITIES CARRIED (for the lead, also in the handback)
--------------------------------------------------------
  * PIN 5b pins conduit SILENT because the contract says so twice ("stay silent
    on conduit's seam pair"; "conduit tmp replay silent"). The audit's own
    conduit exhibit ALSO names a shared index 9 for the source tile and the
    locked track, which is a same-index family that is not the seam pair. If a
    faithful detector fires on THAT, this pin fails and the lead adjudicates —
    it is not a silent pass either way.
  * "fires" is asserted under mode=fail, where firing is unambiguous (status
    `fail`). Under the default `record` the same fixture must NOT fail, which
    is how PIN 3d proves the default differentially.

RULES OBEYED: tmp_path only; `out/` is a READ-ONLY source, always copied to tmp
before a replay; no API calls; no network; nothing is committed.
"""

from __future__ import annotations

import copy
import inspect
import json
import re
import shutil
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml

from gen import s3_static, s3_verify
from gen.config import load_config
from gen.frames import FrameCapture, capture, capture_from_json
from gen.s3_static import CheckResult, run_static_checks
from gen.s3_verify import (
    SCHEMA_VERSION,
    build_verifier_prompt,
    stage_worker_copy,
    validate_report,
    write_report,
)

# --- the contract's own names ----------------------------------------------
# The ONE symbol the A3 contract spells out: "a code-side detector
# `static.lookalike-declared`".
CHECK_ID = "static.lookalike-declared"
MODE_OFF, MODE_RECORD, MODE_FAIL = "off", "record", "fail"
MODES = (MODE_OFF, MODE_RECORD, MODE_FAIL)
DEFAULT_MODE = MODE_RECORD

# The five static ids frozen by the B7 contract (`test_b7_verify.py` STATIC_IDS)
# and counted by the 25-official battery, in order.
HEAD_STATIC_IDS = (
    "static.complete-action",
    "static.sys-click-truthful",
    "static.unread-minus2",
    "static.parsed-field-no-reader",
    "static.palette-hud-collision",
)

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "config" / "template.yaml"
PILOT_CONFIG = REPO / "config" / "b001-pilot.yaml"
TOY = REPO / "gen" / "tests" / "toy_worker"
PUMP_PHASE = REPO / "out" / "corpus" / "b002-triple" / "pump-phase-time-echo"
CONDUIT = REPO / "out" / "corpus" / "b003r2-simplicity" / "conduit-watch"

# Spellings a blind test must tolerate for a block the contract writes in prose
# ("an optional `lookalikes` block ... undeclared-found[], declared-ungrounded[]").
BLOCK_NAMES = ("lookalikes", "look_alikes", "lookalike", "look_alike", "look-alikes")
FOUND_KEYS = ("undeclared_found", "undeclared-found", "undeclared", "found")
UNGROUNDED_KEYS = ("declared_ungrounded", "declared-ungrounded", "ungrounded")
# The word that is absent from the HEAD prompt and present in the contract's
# section name ("a LOOK-ALIKE INVENTORY section").
INVENTORY_WORD = "inventory"
# The one palette index every synthetic look-alike family below is drawn in
# (the fixtures' `PAD` and `SEAM`), re-derived from the frames by `_assert_rendered`.
PAD_INDEX = 9
LOOKALIKE_STEMS = ("look-alike", "lookalike", "look alike", "look_alike")
# The new constant must ask the auditor to GROUND the declared entries (the
# declared-but-absent half). "ground" alone is not enough as a PROMPT probe —
# `FRAMES_HEADER` already says "ground truth" — but it is a clean probe inside a
# constant that did not exist at HEAD.
GROUND_STEM = "ground"


# --------------------------------------------------------------------------- #
# fixture sources — a family of same-index, same-footprint, different-behavior
# objects, which is the contract's own definition of the thing detected
# --------------------------------------------------------------------------- #

# TWO KINDS, ONE SILHOUETTE. `pad_live` and `pad_inert` are drawn in the SAME
# palette index with the SAME 2x2 footprint; one is tagged `sys_click` and
# handled by name, the other is tagged nothing and handled nowhere. They are
# placed far apart, so the adjacency-fusion exclusion cannot apply.
LOOKALIKE_GAME = '''\
"""Fixture: two identical flat solids — one clickable, one inert."""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

BACKDROP = 5
PAD = 9  # ONE palette index for both pads


def _level() -> Level:
    return Level(
        sprites=[
            Sprite(
                [[BACKDROP] * 12 for _ in range(12)],
                name="backdrop",
                x=0,
                y=0,
                collidable=False,
            ),
            Sprite(
                [[PAD, PAD], [PAD, PAD]],
                name="pad_live",
                x=1,
                y=1,
                layer=1,
                tags=["sys_click"],
            ),
            Sprite(
                [[PAD, PAD], [PAD, PAD]],
                name="pad_inert",
                x=8,
                y=8,
                layer=1,
            ),
        ]
    )


class TwoKindsOneSilhouette(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="w3a3-lookalike",
            levels=[_level()],
            camera=Camera(width=12, height=12),
            available_actions=[6],
        )

    def step(self) -> None:
        if self.action.id is GameAction.ACTION6:
            cell = self.camera.display_to_grid(
                int(self.action.data.get("x", 0)), int(self.action.data.get("y", 0))
            )
            if cell is not None:
                hit = self.current_level.get_sprite_at(cell[0], cell[1])
                # Only `pad_live` is handled. `pad_inert` looks identical and
                # does nothing — the deception this detector is for.
                if hit is not None and hit.name == "pad_live":
                    self.complete_action()
                    self.next_level()
                    return
        self.complete_action()
'''

# THE ADJACENCY-FUSION FIXTURE. The same family, except the two objects render
# side by side (x=4 and x=6, each 2 wide, so columns 5 and 6 touch) and fuse
# into one component. The contract: that is a RENDER consequence, not an
# authored look-alike, and it must NOT fire.
FUSED_GAME = '''\
"""Fixture: two same-index objects that render ADJACENT and fuse."""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

BACKDROP = 5
SEAM = 9  # ONE palette index for both halves of the fused component


def _level() -> Level:
    return Level(
        sprites=[
            Sprite(
                [[BACKDROP] * 12 for _ in range(12)],
                name="backdrop",
                x=0,
                y=0,
                collidable=False,
            ),
            Sprite(
                [[SEAM, SEAM], [SEAM, SEAM]],
                name="seam_live",
                x=4,
                y=4,
                layer=1,
                tags=["sys_click"],
            ),
            Sprite(
                [[SEAM, SEAM], [SEAM, SEAM]],
                name="seam_track",
                x=6,
                y=4,
                layer=1,
            ),
        ]
    )


class FusedSeam(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="w3a3-fused",
            levels=[_level()],
            camera=Camera(width=12, height=12),
            available_actions=[6],
        )

    def step(self) -> None:
        if self.action.id is GameAction.ACTION6:
            cell = self.camera.display_to_grid(
                int(self.action.data.get("x", 0)), int(self.action.data.get("y", 0))
            )
            if cell is not None:
                hit = self.current_level.get_sprite_at(cell[0], cell[1])
                if hit is not None and hit.name == "seam_live":
                    self.complete_action()
                    self.next_level()
                    return
        self.complete_action()
'''

# THE PAINT-SITE SURFACE. The corpus idiom (§7/D13, and pump-phase verbatim):
# sprites are born blank and a `_paint` pass writes one flat colour into them,
# so the look-alike family exists at the PAINT SITE rather than in a pixel
# literal. The contract names both surfaces — "sprites/paint sites".
PAINTED_GAME = '''\
"""Fixture: the look-alike family authored at the PAINT SITES (pump-phase idiom)."""

import numpy as np
from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

BACKDROP = 5
PAD = 9  # ONE palette index, written into both pads by _paint()
SLOT = 2


def _blank(size: int):
    return np.full((size, size), -1, dtype=np.int8)


def _level() -> Level:
    return Level(
        sprites=[
            Sprite(
                np.full((12, 12), BACKDROP, dtype=np.int8),
                name="backdrop",
                x=0,
                y=0,
                collidable=False,
            ),
            Sprite(_blank(SLOT), name="pad_live", x=1, y=1, layer=1, tags=["sys_click"]),
            Sprite(_blank(SLOT), name="pad_inert", x=8, y=8, layer=1),
        ]
    )


class PaintedLookalikes(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="w3a3-painted",
            levels=[_level()],
            camera=Camera(width=12, height=12),
            available_actions=[6],
        )

    def _paint(self) -> None:
        level = self.current_level
        # The same flat index into both footprints: identical on the board.
        level.get_sprites_by_name("pad_live")[0].pixels[:, :] = PAD
        level.get_sprites_by_name("pad_inert")[0].pixels[:, :] = PAD

    def step(self) -> None:
        self._paint()
        if self.action.id is GameAction.ACTION6:
            cell = self.camera.display_to_grid(
                int(self.action.data.get("x", 0)), int(self.action.data.get("y", 0))
            )
            if cell is not None:
                hit = self.current_level.get_sprite_at(cell[0], cell[1])
                if hit is not None and hit.name == "pad_live":
                    self.complete_action()
                    self.next_level()
                    return
        self.complete_action()
'''

# A worker ships a solver beside its game; an official never does.
WORKER_SOLVER = '''\
"""Fixture solver — present so the worker dir has the worker-template shape."""

from arcengine import ActionInput, GameAction


class Solver:
    def reset(self) -> None:
        self._sent = 0

    def next_action(self, frame) -> "ActionInput | None":
        if self._sent:
            return None
        self._sent = 1
        return ActionInput(id=GameAction.RESET)
'''

# The spec's own words for the family above, written the way a spec writer
# would declare it: the catalog keyword, the palette index and the silhouette.
# Deliberately over-explicit, so a detector that grounds by KEYWORD and one that
# grounds by INDEX both find it — a blind test must not pick the grounding rule.
DECLARED_DECEPTION = (
    "look-alike: the inert pad is drawn in palette index 9 with the same 2x2 "
    "flat-solid silhouette as the clickable pad, so two identical-looking "
    "objects behave differently — only one of them is clickable"
)


# --------------------------------------------------------------------------- #
# staging helpers — tmp_path only
# --------------------------------------------------------------------------- #


def _slot(tmp_path: Path, name: str, source: str, deceptions: list[str]) -> tuple[Path, Path]:
    """A slot dir the way the corpus ships one: `<slot>/spec.yaml` + `<slot>/worker/`.

    Returns `(worker_dir, spec_path)`. The layout is copied from
    `out/corpus/<batch>/<slug>/`, so a detector that finds the spec by walking
    up from the worker and one that is handed a `spec_path` both work.
    """
    slot = tmp_path / name
    worker = slot / "worker"
    worker.mkdir(parents=True)
    (worker / "game.py").write_text(source, encoding="utf-8")
    (worker / "solver.py").write_text(WORKER_SOLVER, encoding="utf-8")
    spec_path = slot / "spec.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "game": {
                    "slug": name,
                    "title": name.replace("-", " "),
                    "terms": ["manip.select_cycle"],
                    "knobs": {
                        "refusal": "visible",
                        "goal_legible": True,
                        "danger_tell": "none",
                        "deceptions": list(deceptions),
                    },
                    "levels": [
                        {
                            "relation_to_prev": "first",
                            "terms_introduced": ["manip.select_cycle"],
                            "sketch": "one clickable pad and one inert look-alike",
                        }
                    ],
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return worker, spec_path


def _official(tmp_path: Path, slug: str, source: str) -> Path:
    """An OFFICIAL variant dir: `<slug>.py` + `metadata.json`, no game/solver.

    `gen/officials.py`: the corpus is `games/<slug>/<variant>/`, and
    `s3_static.game_source_path` falls back to "the one non-solver .py here".
    """
    variant = tmp_path / slug / "0a0ad940"
    variant.mkdir(parents=True)
    (variant / f"{slug}.py").write_text(source, encoding="utf-8")
    (variant / "metadata.json").write_text(
        json.dumps({"game_id": f"{slug}-0a0ad940"}) + "\n", encoding="utf-8"
    )
    return variant


def _game_class(path: Path) -> type:
    """Exec-load a fixture game file and return its one ARCBaseGame subclass."""
    import importlib.util
    import sys

    from arcengine import ARCBaseGame

    name = f"w3a3_fixture_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot import {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    found = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and issubclass(obj, ARCBaseGame)
        and obj is not ARCBaseGame
        and obj.__module__ == module.__name__
    ]
    assert len(found) == 1, f"{path}: expected one ARCBaseGame subclass, found {found!r}"
    return found[0]


def _components(grid, color: int) -> list[tuple[int, int, int, int, int]]:
    """4-neighbour connected components of `color`: `(x0, y0, x1, y1, cells)`."""
    height, width = len(grid), len(grid[0])
    seen: set[tuple[int, int]] = set()
    out = []
    for y in range(height):
        for x in range(width):
            if grid[y][x] != color or (x, y) in seen:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            cells = []
            while stack:
                cx, cy = stack.pop()
                cells.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if (
                        0 <= nx < width
                        and 0 <= ny < height
                        and (nx, ny) not in seen
                        and grid[ny][nx] == color
                    ):
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            xs = [c[0] for c in cells]
            ys = [c[1] for c in cells]
            out.append((min(xs), min(ys), max(xs), max(ys), len(cells)))
    return sorted(out)


def _assert_rendered(cap: FrameCapture, *, fused: bool) -> None:
    """Re-derive the fixture's exhibit from the FRAMES rather than trusting it.

    MEASURED on the settled reset frame (the camera upscales the 12x12 board to
    64x64, so the two 2x2 pads render as 10x10 blocks):

      * the look-alike fixtures — TWO components of `PAD_INDEX`, byte-identical
        in size and shape and nowhere near each other: two kinds, one
        silhouette, and the adjacency-fusion exclusion cannot apply.
      * the fused fixture — ONE component, because the two same-index objects
        touch and the render fuses them. That IS the conduit seam condition.

    If the engine's camera scaling ever changes, this fails here rather than
    quietly turning PIN 3a or PIN 3c into a test of something else.
    """
    parts = _components(cap.records[0].grid, PAD_INDEX)
    if fused:
        assert len(parts) == 1, f"the seam pair must render as ONE component, got {parts}"
        return
    assert len(parts) == 2, f"the look-alike pair must render as TWO components, got {parts}"
    first, second = parts
    shapes = [(x1 - x0, y1 - y0, cells) for x0, y0, x1, y1, cells in parts]
    assert shapes[0] == shapes[1], f"the two look-alikes differ in footprint: {parts}"
    assert first[2] + 1 < second[0] or first[3] + 1 < second[1], (
        f"the two look-alikes are adjacent and would fuse: {parts}"
    )


def _replay(tmp_path: Path, slot: Path, name: str) -> tuple[Path, Path, FrameCapture]:
    """A shipped slot copied out of the READ-ONLY `out/` tree, with its capture.

    The sidecar supplies the capture: re-running the solver would prove nothing
    these pins are about, and `out/` is never written to.
    """
    if not (slot / "worker" / "game.py").is_file():
        pytest.skip(f"{name}'s shipped worker is not in this tree ({slot})")
    dest = tmp_path / name
    dest.mkdir(parents=True)
    shutil.copytree(
        slot / "worker",
        dest / "worker",
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "tests"),
    )
    shutil.copy2(slot / "spec.yaml", dest / "spec.yaml")
    cap = capture_from_json(json.loads((slot / "worker.frames.json").read_text("utf-8")))
    return dest / "worker", dest / "spec.yaml", cap


# --------------------------------------------------------------------------- #
# discovery — the contract names an id, not a symbol, a path or a placement
# --------------------------------------------------------------------------- #


# Check-shaped names this test never calls directly: `run_static_checks` is
# called once by `_run` itself, and the other two public legs are expensive
# (`run_solver_quality` drives a BFS) and can produce no look-alike verdict.
_DISCOVERY_DENYLIST = frozenset({"run_static_checks", "run_required_rows", "run_solver_quality"})


def _named_like_lookalike(name: str) -> bool:
    flat = name.lower().replace("_", "").replace("-", "")
    return "lookalike" in flat or "deception" in flat


def _detector_callables() -> list[tuple[str, object]]:
    """Module-level callables in `gen.s3_static` that could produce the verdict.

    Deliberately WIDE, and wider than `test_w2_sysclick.py`'s click filter,
    because the contract names the check ID and no symbol: a blind test that
    guessed the function's name would report a false failure for a correct
    implementation that spelled it differently. So every CHECK-SHAPED function
    (`_check_*` / `check_*`, the house idiom in this module) is called too, not
    only the ones whose name says "look-alike" or "deception", and only
    `CheckResult`s carrying the contract's id are read back. A helper called
    this way either yields no verdict or lands in the diagnostics;
    `gen.s3_static` is a read-only analysis module and every directory here is a
    tmp copy, so calling one costs nothing.

    At HEAD this finds the five existing static checks and NO verdict carrying
    `static.lookalike-declared`, which is what makes every detector pin below
    contract-bearing.
    """
    found = []
    for name, obj in vars(s3_static).items():
        if not inspect.isfunction(obj):
            continue
        if getattr(obj, "__module__", None) != s3_static.__name__:
            continue
        low = name.lower()
        if low in _DISCOVERY_DENYLIST:
            continue
        check_shaped = low.startswith(("_check", "check")) or (
            low.startswith("run") and "generated" in low
        )
        if not (_named_like_lookalike(name) or check_shaped):
            continue
        found.append((name, obj))
    return sorted(found)


def _mode_readers() -> list[tuple[str, object]]:
    """Module-level knob readers: `<lookalike>_mode(cfg)`-shaped functions."""
    found = []
    for name, obj in vars(s3_static).items():
        if not inspect.isfunction(obj):
            continue
        if getattr(obj, "__module__", None) != s3_static.__name__:
            continue
        if not _named_like_lookalike(name) or "mode" not in name.lower():
            continue
        try:
            parameters = list(inspect.signature(obj).parameters.values())
        except (TypeError, ValueError):  # pragma: no cover - builtins only
            continue
        required = [p for p in parameters if p.default is p.empty]
        if len(required) == 1:
            found.append((name, obj))
    return sorted(found)


def _template() -> dict:
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8")) or {}


def _knob_hits() -> list[tuple[tuple[str, ...], str]]:
    """Every `(path, value)` in template.yaml that reads as the look-alike knob.

    The contract requires the template to ARM the detector at `record`, so the
    template is where a blind test can learn the knob's config path without
    guessing it. Both shapes are accepted: a scalar key
    (`lookalike_declared: record`) and a block (`lookalike_declared: {mode: record}`).
    """
    hits: list[tuple[tuple[str, ...], str]] = []

    def walk(node: object, path: tuple[str, ...], tainted: bool) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = path + (str(key),)
                walk(value, here, tainted or _named_like_lookalike(str(key)))
        elif isinstance(node, str) and tainted and node in MODES:
            hits.append((path, node))

    walk(_template(), (), False)
    return hits


def _knob_path() -> tuple[str, ...]:
    hits = _knob_hits()
    assert hits, (
        "A3 pins `config/template.yaml` to arm the look-alike detector at "
        f"{MODE_RECORD!r} ('template arms record'). No key mentioning look-alikes "
        f"carries one of {list(MODES)} in {TEMPLATE}. Every mode pin reads the "
        "knob's config path back out of the template, so this blocks them all."
    )
    armed = [path for path, value in hits if value == MODE_RECORD]
    return (armed or [path for path, _ in hits])[0]


def _cfg_with(mode: str | None) -> dict:
    """The template config with the look-alike knob set to `mode` (or removed).

    A real config, not a stub: a reader that validates its neighbours sees a
    whole batch config, and `mode=None` is the canon default path — the knob
    absent entirely.
    """
    cfg = copy.deepcopy(_template())
    path = _knob_path()
    node = cfg
    for key in path[:-1]:
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            node[key] = nxt
        node = nxt
    if mode is None:
        node.pop(path[-1], None)
    else:
        node[path[-1]] = mode
    return cfg


def _bind(fn, pool: dict):
    """Arguments for `fn` drawn from `pool` by parameter NAME, or None."""
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):  # pragma: no cover - builtins only
        return None
    args: list = []
    kwargs: dict = {}
    for name, param in signature.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        if name in pool:
            if param.kind is param.POSITIONAL_ONLY:
                args.append(pool[name])
            else:
                kwargs[name] = pool[name]
        elif param.default is not param.empty:
            if param.kind is param.POSITIONAL_ONLY:
                return None
        else:
            return None
    return args, kwargs


def _as_results(value) -> list[CheckResult]:
    if isinstance(value, CheckResult):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, CheckResult)]
    return []


def _pool(worker_dir: Path, cap: FrameCapture, spec_path: Path | None, mode: str | None) -> dict:
    """Named arguments a look-alike check could plausibly ask for.

    The mode is offered BOTH ways — as a `cfg` carrying the template's own knob
    and as a bare `mode` string — because the contract fixes neither seam.
    """
    worker_dir = Path(worker_dir)
    spec = None
    if spec_path is not None and Path(spec_path).is_file():
        spec = yaml.safe_load(Path(spec_path).read_text(encoding="utf-8"))
    cfg = _cfg_with(mode) if _knob_hits() else {}
    return {
        "source": s3_static._parse_game(worker_dir),
        "cap": cap,
        "capture": cap,
        "worker_dir": worker_dir,
        "worker": worker_dir,
        "path": worker_dir,
        "game_dir": worker_dir,
        "spec_path": None if spec_path is None else Path(spec_path),
        "spec_file": None if spec_path is None else Path(spec_path),
        "spec": spec,
        "cfg": cfg,
        "config": cfg,
        "mode": DEFAULT_MODE if mode is None else mode,
    }


def _run(
    worker_dir: Path,
    cap: FrameCapture,
    *,
    spec_path: Path | None = None,
    mode: str | None = None,
) -> tuple[list[CheckResult], list[str]]:
    """(results, diagnostics) — every look-alike verdict the module gives this dir."""
    results: list[CheckResult] = []
    diagnostics: list[str] = []
    pool = _pool(worker_dir, cap, spec_path, mode)
    callables = _detector_callables()
    if not callables:
        diagnostics.append(
            "gen.s3_static exposes no module-level function whose name mentions "
            "look-alikes or deceptions (nor a run_*generated* entry point) — this is "
            "the HEAD pre-state"
        )
    for name, fn in callables:
        bound = _bind(fn, pool)
        if bound is None:
            diagnostics.append(f"{name}{inspect.signature(fn)}: could not bind from the pool")
            continue
        args, kwargs = bound
        try:
            produced = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - surfaced in the pin's message
            diagnostics.append(f"{name}: raised {type(exc).__name__}: {exc}")
            continue
        results.extend(_as_results(produced))
    # A detector folded into the officials' battery would be a PIN 4b failure,
    # never an invisible one, so its results are collected here too.
    try:
        results.extend(run_static_checks(worker_dir, cap))
    except Exception as exc:  # noqa: BLE001 - surfaced in the pin's message
        diagnostics.append(f"run_static_checks: raised {type(exc).__name__}: {exc}")
    return results, diagnostics


def _verdict(results: list[CheckResult]) -> CheckResult | None:
    for result in results:
        if result.check_id == CHECK_ID:
            return result
    return None


def _fired(results: list[CheckResult]) -> bool:
    return any(r.check_id == CHECK_ID and r.status == "fail" for r in results)


def _dump(results, diagnostics=()) -> str:
    body = json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False)
    if diagnostics:
        body += "\n\ndiscovery diagnostics:\n  " + "\n  ".join(diagnostics)
    return body


# --------------------------------------------------------------------------- #
# report helpers — a valid b7.1 report, and the block placements to search
# --------------------------------------------------------------------------- #


def _claims() -> dict:
    return {"terms": [], "dead_code": [], "deceptions": [], "enforcement": [], "notes": ""}


def _report(**overrides) -> dict:
    report = {
        "schema_version": SCHEMA_VERSION,
        "game_id": "w3a3-report",
        "worker": str(TOY),
        "mode": "full",
        "canon": {"docs_root": str(REPO / "canon"), "spec_hash": "a" * 64},
        "frames": {
            "source": "solver",
            "count": 4,
            "levels_completed": 2,
            "win": True,
            "path": "frames.json",
        },
        "checks": [
            {
                "check_id": CHECK_ID,
                "leg": "static",
                "status": "pass",
                "evidence": [],
                "note": "no undeclared look-alike family",
            }
        ],
        "required_rows": [
            {"row": n, "check_id": f"required.row{n}", "status": "pass"} for n in range(1, 9)
        ],
        "agent": {
            "session_id": "fake-verifier-1",
            "model": "claude-opus-5",
            "usd": 0.02,
            "tokens_in": 1200,
            "tokens_out": 800,
            "wall_s": 1.5,
            "staged_copy_verified": True,
            "claims": _claims(),
        },
        "diff": {key: [] for key in s3_verify.DIFF_KEYS},
        "verdict": "pass",
        "reject_reasons": [],
        "versions": {"arcengine": "0.9.3", "python": "3.12.0"},
    }
    report.update(overrides)
    return report


def _placements(report: dict) -> dict[str, object]:
    """Where a `lookalikes` block could live, by a printable label."""
    return {
        "report": report,
        "report.diff": report["diff"],
        "report.agent": report["agent"],
        "report.agent.claims": report["agent"]["claims"],
    }


def _block_bodies(entries_found, entries_ungrounded) -> list[tuple[str, dict]]:
    bodies = []
    for found_key in FOUND_KEYS:
        for ungrounded_key in UNGROUNDED_KEYS:
            bodies.append(
                (
                    f"{{{found_key}, {ungrounded_key}}}",
                    {found_key: list(entries_found), ungrounded_key: list(entries_ungrounded)},
                )
            )
    return bodies


def _accepted(entries_found, entries_ungrounded) -> list[tuple[str, dict]]:
    """Every (description, report) whose `lookalikes` block `validate_report` takes."""
    accepted = []
    for name in BLOCK_NAMES:
        for shape, body in _block_bodies(entries_found, entries_ungrounded):
            report = _report()
            for label, holder in _placements(report).items():
                holder[name] = body
                try:
                    validate_report(report)
                except (ValueError, TypeError):
                    holder.pop(name, None)
                    continue
                accepted.append((f"{label}.{name} = {shape}", copy.deepcopy(report)))
                holder.pop(name, None)
    return accepted


# --------------------------------------------------------------------------- #
# session fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def cfg() -> dict:
    return load_config(PILOT_CONFIG)


@pytest.fixture(scope="session")
def toy_prompt(cfg, tmp_path_factory) -> str:
    """The blind audit prompt, built the way `run_agent_pass` builds it."""
    staged = tmp_path_factory.mktemp("w3a3-staged") / "toy.staged"
    stage_worker_copy(TOY, staged)
    return build_verifier_prompt(cfg, capture(_game_class(TOY / "game.py")), staged)


# --------------------------------------------------------------------------- #
# PIN 1 — the report's optional `lookalikes` block
# --------------------------------------------------------------------------- #


def test_pin1a_report_takes_an_optional_lookalikes_block():
    """Both-direction block accepted somewhere in the b7.1 report. Fails at HEAD."""
    accepted = _accepted([], [])
    assert accepted, (
        "A3: 'the report schema gains an optional `lookalikes` block (both-direction "
        "diffs: undeclared-found[], declared-ungrounded[])'. No placement was accepted "
        f"by validate_report. Tried the block under {list(_placements(_report()))} "
        f"named {list(BLOCK_NAMES)} with key pairs {list(FOUND_KEYS)} x "
        f"{list(UNGROUNDED_KEYS)}. At HEAD every one of these raises, which is the "
        "pre-state this pin inverts."
    )


def test_pin1b_the_block_round_trips_through_write_report(tmp_path):
    """Written and read back unchanged, still valid. Fails at HEAD."""
    accepted = _accepted([], [])
    assert accepted, "no accepted `lookalikes` placement — see PIN 1a"
    label, report = accepted[0]
    path = tmp_path / "verifier-report.json"
    write_report(report, path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    validate_report(loaded)
    assert loaded == report, f"{label} did not round-trip: {loaded!r}"


def test_pin1c_reports_without_the_block_still_validate():
    """b7-era readers unchanged: no block, no schema bump. Holds at HEAD."""
    validate_report(_report())
    assert SCHEMA_VERSION == "b7.1", (
        "A3 pins the lookalikes block OPTIONAL so that 'b7-era report readers "
        f"[are] unchanged'; a schema_version move to {SCHEMA_VERSION!r} breaks that "
        "promise for every report already on disk"
    )


def test_pin1d_the_block_carries_findings_not_just_empty_lists():
    """A record that cannot hold a finding records nothing. Fails at HEAD."""
    candidates = [
        (["look-alike"], ["palette overload"]),
        (
            [{"index": 9, "note": "pad_live vs pad_inert, same 2x2 solid"}],
            [{"index": 2, "note": "declared at index 2, drawn in 3"}],
        ),
        ([{"note": "two kinds, one silhouette"}], [{"note": "no paint site grounds it"}]),
    ]
    tried = []
    for found, ungrounded in candidates:
        accepted = _accepted(found, ungrounded)
        if accepted:
            return
        tried.append(found)
    pytest.fail(
        "the optional `lookalikes` block validated only when both directions were "
        f"EMPTY: no entry shape in {tried!r} was accepted anywhere. The block exists to "
        "carry both-direction findings, so the lead should record the entry schema the "
        "implementation actually pins."
    )


def test_pin1e_the_reject_vocabulary_is_unchanged():
    """A3: 'the verifier's reject logic gains NOTHING yet'. Holds at HEAD."""
    assert s3_verify.REJECT_CODES == (
        "forbidden-static",
        "undeclared-deception",
        "dead-spec-term",
        "undeclared-term",
        "unreachable-declared-mechanic",
        "solver-quality",
    ), (
        "A3 is explicit: 'the verifier's reject logic gains NOTHING yet (findings feed "
        "the record + review, not new rejects — the corroboration machinery already "
        "governs rejects)'. A seventh reject code is a new gate, not a record."
    )
    # A report whose look-alike findings are recorded still passes: `validate_report`
    # enforces "a reject states why and a pass states nothing", so a block that
    # implied a reject could not validate beside `verdict: pass` and empty reasons.
    accepted = _accepted(["look-alike"], ["palette overload"]) or _accepted([], [])
    for label, report in accepted:
        assert report["verdict"] == "pass" and not report["reject_reasons"], label


# --------------------------------------------------------------------------- #
# PIN 2 — the LOOK-ALIKE INVENTORY prompt constant
# --------------------------------------------------------------------------- #


def _prompt_constants() -> list[tuple[str, str]]:
    """Module-level string constants in `gen.s3_verify`, by name."""
    return sorted(
        (name, value)
        for name, value in vars(s3_verify).items()
        if name.isupper() and isinstance(value, str)
    )


def _inventory_constants() -> list[tuple[str, str]]:
    out = []
    for name, value in _prompt_constants():
        low = value.lower()
        if INVENTORY_WORD in low and any(stem in low for stem in LOOKALIKE_STEMS):
            out.append((name, value))
    return out


def test_pin2a_a_lookalike_inventory_constant_exists():
    """The section is a prompt-synced CONSTANT, not inline text. Fails at HEAD."""
    found = _inventory_constants()
    assert found, (
        "A3: 'the blind S2b prompt gains a LOOK-ALIKE INVENTORY section "
        "(prompt-synced constant)'. No module-level string constant in gen.s3_verify "
        f"mentions both {INVENTORY_WORD!r} and a look-alike stem. At HEAD the string "
        f"constants are {[name for name, _ in _prompt_constants()]}, and the built "
        "prompt says 'inventory' zero times."
    )


def _literal_body(value: str) -> str:
    """The longest placeholder-free run of a constant.

    `DECEPTION_HEADER` and `VOCAB_HEADER` are `.format()` templates, so a new
    section constant may be one too. Matching the whole string would then fail
    for a correct implementation; matching its longest literal run proves the
    same thing — the prompt carries THIS constant's own words.
    """
    parts = [chunk.strip() for chunk in re.split(r"\{[^}]*\}", value)]
    return max(parts, key=len) if parts else ""


def test_pin2b_the_constant_is_quoted_verbatim_in_the_built_prompt(toy_prompt):
    """Prompt-synced means the prompt QUOTES it. Fails at HEAD."""
    found = _inventory_constants()
    assert found, "no look-alike inventory constant — see PIN 2a"
    quoted = [
        name
        for name, value in found
        if _literal_body(value) and _literal_body(value) in toy_prompt
    ]
    assert quoted, (
        "a LOOK-ALIKE INVENTORY constant exists but the built audit prompt does not "
        f"quote it: {[name for name, _ in found]}. Prompt-synced means the constant IS "
        "the section — a hand-copied second spelling is the drift this repo's "
        "prompt-sync rule exists to prevent."
    )
    assert INVENTORY_WORD in toy_prompt.lower(), (
        "the built prompt never says 'inventory' — measured 0 times at HEAD, so this "
        "is the word the new section adds"
    )


def test_pin2c_the_section_asks_both_directions():
    """List what is found AND ground what is declared. Fails at HEAD."""
    found = _inventory_constants()
    assert found, "no look-alike inventory constant — see PIN 2a"
    grounding = [name for name, value in found if GROUND_STEM in value.lower()]
    assert grounding, (
        "A3 asks the auditor for BOTH directions: 'the auditor lists every family of "
        "same-index-same-footprint-different-behavior objects it finds AND every "
        "declared knobs.deceptions entry it can/cannot ground'. The new constant(s) "
        f"{[name for name, _ in found]} never mention grounding, so only the "
        "undeclared-found half was asked for."
    )


def test_pin2d_the_b7_prompt_sections_survive(toy_prompt):
    """The new section is an addition, not a rewrite. Holds at HEAD."""
    for name in ("MISSION", "CLAIMS_CONTRACT", "DECEPTION_HEADER"):
        constant = getattr(s3_verify, name)
        head = constant.splitlines()[0]
        assert head in toy_prompt, f"{name} no longer reaches the built prompt"


# --------------------------------------------------------------------------- #
# PIN 3 — the static detector `static.lookalike-declared`
# --------------------------------------------------------------------------- #


@pytest.fixture
def undeclared(tmp_path):
    """Two kinds, one silhouette; the spec declares NO deception."""
    worker, spec_path = _slot(tmp_path, "undeclared", LOOKALIKE_GAME, [])
    cap = capture(_game_class(worker / "game.py"))
    _assert_rendered(cap, fused=False)
    return worker, spec_path, cap


@pytest.fixture
def declared(tmp_path):
    """The SAME BYTES, with the look-alike declared in knobs.deceptions."""
    worker, spec_path = _slot(tmp_path, "declared", LOOKALIKE_GAME, [DECLARED_DECEPTION])
    cap = capture(_game_class(worker / "game.py"))
    _assert_rendered(cap, fused=False)
    return worker, spec_path, cap


@pytest.fixture
def fused(tmp_path):
    """Same index, same footprint, rendering ADJACENT — a render consequence."""
    worker, spec_path = _slot(tmp_path, "fused", FUSED_GAME, [])
    cap = capture(_game_class(worker / "game.py"))
    _assert_rendered(cap, fused=True)
    return worker, spec_path, cap


@pytest.fixture
def painted(tmp_path):
    """The family authored at the PAINT SITES (the corpus idiom).

    Renders IDENTICALLY to the `undeclared` fixture — same two components, same
    footprints, same index — so the only variable between PIN 3a and PIN 3g is
    where the family is authored: pixel literals versus paint sites.
    """
    worker, spec_path = _slot(tmp_path, "painted", PAINTED_GAME, [])
    cap = capture(_game_class(worker / "game.py"))
    _assert_rendered(cap, fused=False)
    return worker, spec_path, cap


def test_pin3a_fires_on_two_kinds_one_silhouette(undeclared):
    """The detector itself. Fails at HEAD (no detector exists)."""
    worker, spec_path, cap = undeclared
    results, diagnostics = _run(worker, cap, spec_path=spec_path, mode=MODE_FAIL)
    assert _fired(results), (
        f"A3: `{CHECK_ID}` must find 'families of sprites/paint sites sharing an index "
        "whose footprints match but whose behavior tags/handlers differ, diffed against "
        "knobs.deceptions'. This worker draws pad_live and pad_inert in ONE palette "
        "index with ONE 2x2 footprint, tags only one sys_click, handles only that one "
        "by name, and its spec declares `deceptions: []`. Under mode=fail that is the "
        f"detector's whole premise.\n\n{_dump(results, diagnostics)}"
    )


def test_pin3b_silent_when_the_lookalike_is_declared(declared):
    """Declared is not a defect — the diff is against knobs.deceptions."""
    worker, spec_path, cap = declared
    results, diagnostics = _run(worker, cap, spec_path=spec_path, mode=MODE_FAIL)
    assert _verdict(results) is not None, (
        f"no `{CHECK_ID}` verdict at all on a generated worker — the detector owes "
        f"every generated game an answer.\n\n{_dump(results, diagnostics)}"
    )
    assert not _fired(results), (
        "the SAME BYTES as PIN 3a, whose spec declares the look-alike verbatim "
        f"({DECLARED_DECEPTION!r}), still fired. A declared deception is the property "
        f"§10 asks for, not a finding.\n\n{_dump(results, diagnostics)}"
    )


def test_pin3c_silent_on_the_adjacency_fusion_fixture(fused):
    """ADJACENCY-FUSION EXCLUSION, pinned hard by the contract."""
    worker, spec_path, cap = fused
    results, diagnostics = _run(worker, cap, spec_path=spec_path, mode=MODE_FAIL)
    assert _verdict(results) is not None, (
        f"no `{CHECK_ID}` verdict at all on a generated worker.\n\n"
        f"{_dump(results, diagnostics)}"
    )
    assert not _fired(results), (
        "A3, pinned hard: 'two same-index objects that render adjacent (fusing into one "
        "component) are a RENDER consequence, not an authored look-alike — the conduit "
        "seam pair must NOT fire it'. seam_live and seam_track sit at x=4 and x=6, two "
        f"cells wide each, so they touch.\n\n{_dump(results, diagnostics)}"
    )


def test_pin3d_mode_knob_semantics_and_the_record_default(undeclared):
    """off | record | fail, default record. Fails at HEAD."""
    worker, spec_path, cap = undeclared

    fail_results, fail_diagnostics = _run(worker, cap, spec_path=spec_path, mode=MODE_FAIL)
    assert _fired(fail_results), (
        f"mode={MODE_FAIL!r} must reject the undeclared family — see PIN 3a.\n\n"
        f"{_dump(fail_results, fail_diagnostics)}"
    )

    record_results, record_diagnostics = _run(worker, cap, spec_path=spec_path, mode=MODE_RECORD)
    record = _verdict(record_results)
    assert record is not None, (
        f"mode={MODE_RECORD!r} records the finding, so it must still produce a "
        f"`{CHECK_ID}` verdict.\n\n{_dump(record_results, record_diagnostics)}"
    )
    assert record.status != "fail", (
        "A3: 'a detector this heuristic starts as evidence, not a gate', so "
        f"mode={MODE_RECORD!r} must NOT fail the same family mode={MODE_FAIL!r} "
        f"rejects.\n\n{_dump(record_results, record_diagnostics)}"
    )
    assert record.evidence, (
        f"mode={MODE_RECORD!r} recorded nothing: the verdict carries no evidence, so "
        "the finding the record exists for is lost.\n\n"
        f"{_dump(record_results, record_diagnostics)}"
    )

    default_results, default_diagnostics = _run(worker, cap, spec_path=spec_path, mode=None)
    default = _verdict(default_results)
    assert default is not None, (
        f"an unconfigured run produced no `{CHECK_ID}` verdict, so the DEFAULT is not "
        f"{MODE_RECORD!r}.\n\n{_dump(default_results, default_diagnostics)}"
    )
    assert default.status == record.status, (
        f"A3 pins the default mode {MODE_RECORD!r}. With the knob absent the verdict is "
        f"{default.status!r}; with the knob set to {MODE_RECORD!r} it is "
        f"{record.status!r}.\n\n{_dump(default_results, default_diagnostics)}"
    )

    off_results, off_diagnostics = _run(worker, cap, spec_path=spec_path, mode=MODE_OFF)
    assert not _fired(off_results), (
        f"mode={MODE_OFF!r} still failed the worker.\n\n{_dump(off_results, off_diagnostics)}"
    )
    off = _verdict(off_results)
    assert off is None or off.status in ("skipped", "premise-not-met", "pass"), (
        f"mode={MODE_OFF!r} must produce no finding — got {off!r}.\n\n"
        f"{_dump(off_results, off_diagnostics)}"
    )


def _loud_on(worker: Path, cap: FrameCapture, spec_path: Path, bad: str):
    """(loud, quiet) — which look-alike seams raise ValueError on a bad mode.

    Both seams are tried, because the contract fixes neither: the knob READER
    (`<lookalike>_mode(cfg)`) and the detector itself. One loud seam satisfies
    the house rule; a seam that merely fails differently is reported, never
    counted.
    """
    loud: list[str] = []
    quiet: list[str] = []
    bad_cfg = _cfg_with(bad)
    for name, reader in _mode_readers():
        try:
            reader(bad_cfg)
        except ValueError:
            loud.append(f"{name}(cfg)")
        except Exception as exc:  # noqa: BLE001 - reported, not counted
            quiet.append(f"{name}(cfg): raised {type(exc).__name__}: {exc}")
        else:
            quiet.append(f"{name}(cfg): returned without raising")
    pool = _pool(worker, cap, spec_path, bad)
    # NARROW here, unlike `_detector_callables`: loudness must be attributed to a
    # look-alike seam, and a neighbouring `_check_*` that happens to raise
    # ValueError on this fixture would otherwise be counted as this knob's rigour.
    for name, fn in _detector_callables():
        if not _named_like_lookalike(name):
            continue
        bound = _bind(fn, pool)
        if bound is None:
            continue
        args, kwargs = bound
        try:
            fn(*args, **kwargs)
        except ValueError:
            loud.append(name)
        except Exception as exc:  # noqa: BLE001 - reported, not counted
            quiet.append(f"{name}: raised {type(exc).__name__}: {exc}")
        else:
            quiet.append(f"{name}: returned without raising")
    return loud, quiet


def test_pin3e_an_invalid_mode_is_a_loud_value_error(undeclared):
    """The house rule: invalid knob values are loud ValueErrors. Fails at HEAD."""
    worker, spec_path, cap = undeclared
    # "warn" is a real mode word for a NEIGHBOURING registry (the W1-B fidelity
    # rules are off|warn|kill), which is exactly the typo this rule is for.
    loud, quiet = _loud_on(worker, spec_path=spec_path, cap=cap, bad="warn")
    assert loud, (
        "A3's binding house rule: 'invalid knob values are loud ValueErrors read "
        f"before work'. Mode {'warn'!r} is outside {list(MODES)} and no look-alike "
        "seam raised ValueError — a detector that silently falls back to a default "
        "reads to anyone auditing the batch as a mode that is not there.\n\n  "
        + "\n  ".join(quiet or ["no look-alike seam could be bound at all"])
    )


def test_pin3f_the_template_arms_record():
    """A3: 'template arms record'. Fails at HEAD."""
    hits = _knob_hits()
    assert hits, (
        "config/template.yaml carries no look-alike detector knob. A3: 'Mode "
        "off|record|fail default record; template arms record (a detector this "
        "heuristic starts as evidence, not a gate)'."
    )
    armed = [(path, value) for path, value in hits if value == MODE_RECORD]
    assert armed, (
        f"the template's look-alike knob(s) {hits!r} do not arm {MODE_RECORD!r}"
    )


def test_pin3g_the_paint_site_surface_fires(painted):
    """'sprites/paint sites' — the corpus idiom is painted, not literal."""
    worker, spec_path, cap = painted
    results, diagnostics = _run(worker, cap, spec_path=spec_path, mode=MODE_FAIL)
    assert _fired(results), (
        "A3 names BOTH surfaces: 'families of sprites/paint sites sharing an index'. "
        "This worker is the corpus idiom (and pump-phase's own): both pads are born "
        "blank and `_paint` writes ONE flat index into both footprints, one tagged "
        "sys_click and handled by name, the other neither, with `deceptions: []`. A "
        "detector that only reads pixel literals sees nothing here and will miss the "
        f"shipped exhibits too.\n\n{_dump(results, diagnostics)}"
    )


# --------------------------------------------------------------------------- #
# PIN 4 — generated-only, the W2-B pattern
# --------------------------------------------------------------------------- #


def test_pin4a_an_official_variant_dir_is_not_judged(tmp_path):
    """The SAME BYTES in an official's layout: premise-not-met or pass."""
    variant = _official(tmp_path, "w3a3", LOOKALIKE_GAME)
    cap = capture(_game_class(variant / "w3a3.py"))
    results, diagnostics = _run(variant, cap, spec_path=None, mode=MODE_FAIL)
    assert not _fired(results), (
        "A3: the detector is 'generated-only, the W2-B pattern, outside the officials' "
        "battery'. These are the PIN 3a bytes staged as `<slug>.py` + metadata.json, so "
        "the only variable is generated-vs-official context.\n\n"
        f"{_dump(results, diagnostics)}"
    )
    verdict = _verdict(results)
    assert verdict is None or verdict.status in ("premise-not-met", "pass", "skipped"), (
        f"an official's dir got a `{CHECK_ID}` status of {verdict.status!r}.\n\n"
        f"{_dump(results, diagnostics)}"
    )


def test_pin4b_the_officials_battery_shape_is_unchanged(tmp_path):
    """`run_static_checks` still returns exactly the five frozen ids, in order."""
    variant = _official(tmp_path, "w3a3b", LOOKALIKE_GAME)
    cap = capture(_game_class(variant / "w3a3b.py"))
    ids = tuple(result.check_id for result in run_static_checks(variant, cap))
    assert ids == HEAD_STATIC_IDS, (
        "the B2-calibrated 25-official battery counts this shape (200/200); a "
        "generated-only detector must not join the five architecture §3 passes"
    )


def test_pin4c_the_detector_id_is_new(undeclared):
    """`static.lookalike-declared` is none of the ids HEAD ships. Fails at HEAD."""
    worker, spec_path, cap = undeclared
    results, diagnostics = _run(worker, cap, spec_path=spec_path, mode=MODE_FAIL)
    assert _verdict(results) is not None, (
        f"no verdict carries the contract's id {CHECK_ID!r}.\n\n"
        f"{_dump(results, diagnostics)}"
    )
    assert CHECK_ID not in HEAD_STATIC_IDS
    assert CHECK_ID != s3_static.LEVEL_COUNT_CHECK
    assert CHECK_ID != s3_static.SYS_CLICK_GENERATED_CHECK


# --------------------------------------------------------------------------- #
# PIN 5 — the shipped exhibits, replayed on tmp copies
# --------------------------------------------------------------------------- #


def test_pin5a_pump_phase_replay_fires(tmp_path):
    """The audit's present-but-undeclared exhibit. Fails at HEAD."""
    worker, spec_path, cap = _replay(tmp_path, PUMP_PHASE, "pump-phase-time-echo")
    # The exhibit re-derived rather than trusted: pump/filler/block are flat
    # solids built from blank slots and painted, and two of the three are
    # clickable while the block is not.
    body = (worker / "game.py").read_text(encoding="utf-8")
    assert 'name="block"' in body and "CLICK_FILL" in body and "CLICK_PUMP" in body
    results, diagnostics = _run(worker, cap, spec_path=spec_path, mode=MODE_FAIL)
    assert _fired(results), (
        "A3's first exhibit (finding B4): pump-phase's pump/filler/block identical flat "
        "solids, two clickable and one not, with no matching entry in its four declared "
        f"deceptions.\n\n{_dump(results, diagnostics)}"
    )


def test_pin5b_conduit_replay_is_silent(tmp_path):
    """The adjacency-fusion exclusion on the real seam pair."""
    worker, spec_path, cap = _replay(tmp_path, CONDUIT, "conduit-watch")
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    assert spec["game"]["knobs"]["deceptions"] == [], (
        "conduit's `deceptions: []` is the premise of this pin — if the shipped spec "
        "changed, this pin is testing something else"
    )
    results, diagnostics = _run(worker, cap, spec_path=spec_path, mode=MODE_FAIL)
    assert not _fired(results), (
        "A3 says this twice — 'the conduit seam pair must NOT fire it' and 'conduit tmp "
        "replay silent'. NOTE FOR THE LEAD: the audit's conduit exhibit also names a "
        "shared index 9 for the source tile and the locked track, which is a same-index "
        "family that is NOT the seam pair; if that is what fired here, the contract's "
        "two silence statements need adjudicating rather than this pin needing a "
        f"weaker assertion.\n\n{_dump(results, diagnostics)}"
    )
