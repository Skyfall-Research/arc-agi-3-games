"""Static, REQUIRED-row and solver-quality checks for S2b (B7, agent A).

Three legs of the intent verifier, all pure code + the real engine, all blind
to the spec (`GEN/design/architecture.md` §3, blindness ⊕):

* `run_static_checks` — the five architecture passes: AST `complete_action`
  audit, `sys_click` truthfulness, `-2` reader scan, parsed-field-has-reader,
  palette/reserved collisions.
* `run_required_rows` — exactly eight results, one per `GEN/spec-v0.3.md` §2
  REQUIRED row, in order, with HONEST statuses (`premise-not-met` when the
  row's premise is absent, `deferred` when the row needs a later pipeline
  stage or the agent leg, never a fake pass).
* `run_solver_quality` — no-op-prefix detection, a BFS spot-check on small
  levels, and lag/confirm modelling.

Beside those three sit the GENERATED-ONLY checks, which are deliberately in
none of them (the W2-B pattern: a rule the officials are not held to must not
be able to move their calibrated battery, and a check outside those lists
cannot) — `static.sys-click-generated` (R-07),
`static.level-count-vs-spec` (C-4b), `static.lookalike-declared` (R-09) and
`static.refusal-honest` (R-08, §6:158's never-signal-and-charge). Each names
its own registration seam on the section that defines it.

Canon each rule is grounded in
------------------------------
* FORBIDDEN, `GEN/spec-v0.3.md` §2 / `affordance-language.md` §8:
  "leaving a handler without `complete_action()` — the engine re-runs the
  action (sc25's latent double-charge)"  →  `static.complete-action`.
* REQUIRED 2, §2: "`sys_click` tags are truthful — always (the engine's
  click-action list and RL consumers read them); *visual* marking of
  clickability is a knob"  →  `static.sys-click-truthful`, `required.row2`.
* REQUIRED 5, §2 + affordance §8: "Every `-2` pixel ships with a declared
  reader (which mask consumes it); `-2` nothing reads is forbidden dead
  weight"  →  `static.unread-minus2`, `required.row5`.
* FORBIDDEN, affordance §8: "interface paint conditions keyed to palette
  equality that a real object can collide with — r11l's line painter writes
  wherever `frame==5 or frame==10` and 10 is an object colour: the frame
  under-reports true state. Interface masks must key on geometry, never
  colour equality."  →  `static.palette-hud-collision`, and the same
  signature is the only `fail` mode of `required.row7`.
* REQUIRED 7, §2: "Reserved HUD geometry declared (row 63 / row 0 / col 0 /
  custom); interfaces paint after the board and WILL overwrite it."
* REQUIRED 3, §2 + affordance §5: the budget triple; part (c) ("the cap
  accommodates the solver's line + the g-margin") is an S4 fact, so row 3 is
  `deferred` whenever (a) and (b) hold.
* REQUIRED 4 / 6 / 8, §2, and the conventions paragraph ("static scenery
  pre-fuses per layer at Level init"; "settled frame = `fd.frame[-1]`").
* Solver quality: `GEN/design/difficulty-model.md` §1 "Not raw solver
  length: solver lines carry padding (a 21-no-op staging prefix shipped in
  one tufa baseline)" and §3.5 / architecture S4 step 1-2, which make the
  solver line the unit every baseline is built from (`baseline_i = solver_i
  x g_i`, g drawn from the measured lognormal, median 2.00, IQR 1.54-2.96,
  clipped [1.2, 6]) — padding in the line multiplies straight through.
  Architecture S4 step 1 also settles the lag/confirm question: flushes and
  confirm actions "are part of the line".

The parsed-field pass has no single canon sentence; it implements the
architecture §3 box "parsed-field-has-reader", read in the same spirit as
REQUIRED 5 — data a game defines and nothing consumes is dead weight that
confuses extraction.

CALIBRATION LOG — the 25 signed officials (lead ruling, B7)
---------------------------------------------------------------------------
The target is NOT "zero fails": the canon's FORBIDDEN list was written FROM
corpus defects, so a correct check must fail the officials canon names. Every
check below is written to canon strength, the battery is run across all 25,
and every fail is adjudicated with source evidence into one of three buckets:
a canon-documented defect, a verified-but-undocumented defect (both kept, and
listed in `KNOWN_OFFICIAL_FAILS`), or a check false positive (fixed).

FINAL TALLY: 21/25 officials clean on all 13 checks; 4 officials carry
exactly one fail each, all in `KNOWN_OFFICIAL_FAILS` — r11l and m0r0 on
`static.palette-hud-collision`, sc25 and sk48 on
`static.parsed-field-no-reader`. No other check fails any official.

FALSE POSITIVES FOUND AND FIXED (bucket c), in the order the corpus forced
them:

1. `static.complete-action`, strict reading ("every exit path of `step()`
   calls `complete_action()`") failed 23/25. Evidence: ar25.py:1702-1711
   returns inside an animation tick; bp35.py:4493-4506 alternates on
   `self.heywwwvrogx`; cd82.py:637-641 hands off to `self.hhjooisvrs()`.
   Those are CONTINUATION frames, which the engine is built for
   (`perform_action` re-runs `step()` until `complete_action()`,
   base_game.py:224-236). FIX: an exit is a violation when the engine's
   re-entry would REPEAT what the exit just did — see `analyze_step` for the
   two-case rule (continuation path vs action-handler path).
2. Three dataflow corrections, each a correctness fix rather than a
   loosening: calls inside an `if`/`while` TEST mutate state (vc33.py:2096
   advances its animation in the test, sc25.py:2556 likewise); branch writes
   must merge back into the path state (tu93.py:1250 sets
   `self.kdkehgjrzq = 2` inside an inner `if` and returns after it); local
   aliases carry writes (re86.py:2105 does `vmylhbjiyz = self.cptlsijjli`
   then mutates `vmylhbjiyz.pixels`).
3. `static.complete-action`, cn04.py:1119-1120:
   `if self.current_level.grid_size is None: return` — a defensive guard on
   an engine-owned structure (`Level.grid_size` is Optional, level.py:26,
   but every cn04 level sets it). An exit whose nearest guard is a pure
   ABSENCE test on an engine-owned expression is recorded as `defensive` and
   does not fail.
4. `static.sys-click-truthful`: 6/25 (bp35, cd82, ft09, lf52, s5i5, su15)
   declare ACTION6 with ZERO `sys_click`/`sys_place` sprites — they read raw
   coordinates. "Truthful" is a property of the tags that exist; an empty tag
   set tells no lie, and REQUIRED 2's own second clause makes visual click
   marking a knob. Those PASS, with the fact in the note. (R-07, 2026-09-28:
   GENERATED games are held to the stronger bar — tag your click targets — by
   a SEPARATE check, `static.sys-click-generated`, which is not in
   `run_static_checks` and which the officials' battery never asserts. This
   adjudication, and every count in this log, are unchanged by it.)
5. `static.unread-minus2`: ka59 (4 sprites), ls20 (2), wa30 (1) and dc22 (10)
   ship `-2` on sprites with `collidable=False`. All of them TAG those
   sprites and tag-scan heavily (17-49 sites), which is canon's own reading:
   "ka59 sets collidable=False on -2 interiors (NOT solid); tn36/ls20 use
   BOUNDING_BOX or tag-scans so -2 is inert; dc22 uses -2 as the ONLY
   touchable surface of intangible markers" (affordance §8). A tag scan on a
   tagged carrier is therefore a declared reader; `collidable=False` alone is
   NOT (it is the opposite — see `_sprite_mask_mode`).
6. `required.row6` (explicit layers): bp35, lp85 and sp80 ship no `layer=`
   at all. bp35 paints its board in a `RenderableUserDisplay` (affordance §8
   names bp35/lf52/m0r0 as the structural exceptions) so sprite z-order is
   not its mechanism; lp85 and sp80 have no proven overlap. The row's premise
   is "every overlap that matters", so those are `premise-not-met`.
7. `required.row7` (reserved HUD geometry): ar25, dc22, lp85, ls20 and su15
   first read as "no axis pinned" because each declares its strip through a
   LOCAL — `start_y: int = 63` (dc22.py:9927), `start_x: int = 63`
   (ar25.py:1122), `toxqhfsju = 61` rebound per pip row (ls20.py:1545/1550).
   Three scanner fixes: assignment targets bind only the names they BIND
   (`frame[start_y + i, start_x] = v` binds nothing — `_assigned_names`);
   names resolve against the nearest preceding constant assignment in source
   order (`_frame_write_sites`); and `toxqhfsju : toxqhfsju + 2` folds to
   61:63 (`_int_const` constant folding). All five then declare geometry.
   The rule this settles: a write that pins ONE axis declares a strip even
   when the other axis and the extent are data-chosen (an edge-anchored meter
   draining with the budget is exactly that), and a full-board overlay keyed
   on distance to the avatar (ls20.py:1534, its limited-vision mechanic) is
   not HUD geometry at all. Only an interface where NO write pins an axis
   anywhere fails the row.
8. Pixel scanners were blind to three authoring idioms, which silently
   disabled the palette rules on the games that use them: named colour
   constants (`WALL, PLAYER, GOAL = 4, 9, 12`), `[[WALL] * 8]`,
   `[[TRAIL] * 3 for _ in range(3)]`, and `CRATE_PIXELS = [...]` passed to
   `Sprite(CRATE_PIXELS, …)` by name. `_int_constants`, `_row_values`,
   `_nested_int_lists` and `_pixel_bindings` now resolve all four.
9. `required.row7` no longer inherits the `static.palette-hud-collision`
   verdict: REQUIRED 7 (declare the strip) and FORBIDDEN #1 (do not key paint
   to palette equality) are different contracts, and coupling them produced
   two fails for one line.

NOT FLAGGED, and why (checked because canon mentions it): the sc25 "latent
double-charge" (affordance §6/§8) does not appear in sc25's `step()`. Every
action-guarded exit there writes an animation flag that an EARLIER top-level
guard reads (`self.eycwbtepcvs` sc25.py:2556, `self.ggotuphkheh` sc25.py:2565,
`self.agzbtzaakna` sc25.py:2591), so the engine's re-entry is intercepted
before the handler re-runs — the ar25 idiom, done correctly. Canon cites sc25
under refusal semantics; this leg finds no reachable instance in the code.

Known limitation, stated rather than hidden: `static.complete-action` is a
static approximation. A handler that forgets `complete_action()` but writes a
root an earlier guard reads is a FALSE NEGATIVE here; the worker battery's
runtime probe (R3 in `worker-template/tests/_contracts.py`, which names the
engine's own `ValueError("Action took too many frames")`) is the net for it.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import re
import sys
import traceback
from collections import deque
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from arcengine import ARCBaseGame, GameAction, GameState

from .frames import (
    CLICK_TAGS,
    FrameCapture,
    _fresh_game,
    _perform,
    _reset,
    _sprite_name,
    describe_action,
    mouse,
    quiet,
    settled_grid,
)
from .worker import purge_worker_modules

# --- tunables, every one traced to canon ------------------------------------

# architecture S4 step 2 / config `g.median`: the measured human replay ratio
# median (n=183). A solver line already this far above the engine-optimal
# bound pushes baseline-vs-optimal past the top of the measured IQR (2.96)
# before g is even drawn.
GROSS_SOLVER_RATIO = 2.0

# BFS spot-check budget. The search replays from a fresh instance per node
# line (the contract's "clone/re-instantiate per node line"), so the cost is
# O(nodes x depth) engine actions; these caps keep one spot-check inside a
# second or two on the corpus-sized games that qualify at all.
BFS_MAX_NODES = 4000
BFS_MAX_DEPTH = 40

# Lag / confirm idioms, from the vocabulary groups `state.action_lag` and
# `goal.confirm` (spec §3) and the pilot config's `quotas`.
LAG_CONFIRM_TOKENS = (
    "lag",
    "pending",
    "deferred",
    "delay",
    "flush",
    "confirm",
    "commit",
    "armed",
)

# Engine-owned roots that a `step()` path can never use as progress: the
# engine sets `_action` exactly once per action (`base_game.py:269-279`), so
# touching it proves nothing changed.
NON_PROGRESS_ROOTS = frozenset({"action", "_action"})

# Engine-owned expression roots whose absence-test is a defensive guard
# (adjudication 3 above).
ENGINE_ROOTS = frozenset(
    {"current_level", "camera", "action", "_levels", "_camera", "_action"}
)

# affordance §9: white-0 is the ecosystem's selection/highlight marker.
SELECTION_COLOR = 0

# Rendered palette (spec §2: 16 indices).
COLOR_MIN, COLOR_MAX = 0, 15

STATUSES = ("pass", "fail", "premise-not-met", "deferred", "skipped")

# The adjudicated corpus defects (lead ruling, B7). These four are the ONLY
# `fail` results `run_static_checks` + `run_required_rows` produce across the
# 25 signed officials; every other official is clean on every check. Each
# entry is a verified defect with source evidence, not a suppression — the
# checks still fail them, and the battery asserts this exact set and nothing
# else. `bucket` is "canon" when the canon names the official as the
# violator, "verified" when the defect is real but undocumented and was
# confirmed by reading the whole game file.
KNOWN_OFFICIAL_FAILS: dict[str, dict[str, str]] = {
    "r11l": {
        "check_id": "static.palette-hud-collision",
        "bucket": "canon",
        "citation": (
            "design/objects/affordance-language.md §8 FORBIDDEN: 'interface paint "
            "conditions keyed to palette equality that a real object can collide with "
            "— r11l's line painter writes wherever frame==5 or frame==10 and 10 is an "
            "object colour: the frame under-reports true state.'"
        ),
        "evidence_note": (
            "r11l.py:1390-1392 reads frame[y, x] into a local and repaints that cell "
            "when the value is 5 or 10; colour 10 is carried by board sprites, first "
            "at r11l.py:41 (and by the 7x7/7x3/5x5 pieces at r11l.py:397/438/548, "
            "which the engine places on levels 4-6)."
        ),
    },
    "m0r0": {
        "check_id": "static.palette-hud-collision",
        "bucket": "verified",
        "citation": (
            "design/objects/affordance-language.md §8 FORBIDDEN (same rule as r11l); "
            "spec-v0.3.md §2 FORBIDDEN #1."
        ),
        "evidence_note": (
            "m0r0.py:626 builds the paint mask as `moypuorxop = frame == 0` and "
            "m0r0.py:648 writes `frame[moypuorxop] = pvrabjchrn[moypuorxop]`, so every "
            "colour-0 cell is repainted. Colour 0 is carried by real board sprites: "
            "instantiating the game and scanning `level.get_sprites()` renders finds "
            "one colour-0 sprite in each of levels 0-4 — wahtyt-Level6, "
            "wahtyt-Level11, wahtyt-Level1, wahtyt-Level9, wahtyt-Level2 (declared at "
            "m0r0.py:263/363/147/323/168, first colour-0 row at m0r0.py:149). A real "
            "object can therefore collide with the condition, which is FORBIDDEN #1 "
            "verbatim, with colour 0 where r11l has colour 10. Not named in canon; "
            "kept because the evidence is the rule."
        ),
    },
    "sc25": {
        "check_id": "static.parsed-field-no-reader",
        "bucket": "verified",
        "citation": "design/architecture.md §3 S2b, static pass 'parsed-field-has-reader'.",
        "evidence_note": (
            "sc25.py:1413 (and :1453, :1493) define the level-data field 'rpjr'. The "
            "whole file reads level data exactly twice — sc25.py:1773 get_data('slfh') "
            "and sc25.py:1776 get_data('efvw'); 'rpjr' occurs only in those three "
            "definitions, and the one getattr in the file (sc25.py:2604) reads "
            "self.action.data, not level data."
        ),
    },
    "sk48": {
        "check_id": "static.parsed-field-no-reader",
        "bucket": "verified",
        "citation": "design/architecture.md §3 S2b, static pass 'parsed-field-has-reader'.",
        "evidence_note": (
            "sk48.py:295-296 define 'grouped_pauses' and 'lit_extension' in every "
            "level's data= (16 occurrences, all definitions). sk48 never calls "
            "get_data, never touches Level._data and has no getattr; its only `.data` "
            "reads are sk48.py:748-749 self.action.data.get('x'/'y'), the ACTION "
            "payload."
        ),
    },
}

GAME_FILE_SKIP = frozenset({"solver.py", "__init__.py", "conftest.py", "setup.py"})


# --- result types -----------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    """One pointer a human can follow: a source line, a frame, or the engine."""

    kind: str
    path: str | None = None
    line: int | None = None
    frame_label: str | None = None
    note: str = ""


@dataclass(frozen=True)
class CheckResult:
    """One check's verdict. `status` is one of `STATUSES`; never a fake pass."""

    check_id: str
    leg: str
    status: str
    evidence: tuple[Evidence, ...]
    note: str


def _result(check_id: str, leg: str, status: str, evidence, note: str) -> CheckResult:
    if status not in STATUSES:
        raise ValueError(f"{check_id}: status {status!r} not in {STATUSES}")
    return CheckResult(
        check_id=check_id, leg=leg, status=status, evidence=tuple(evidence), note=note
    )


# --- worker layout ----------------------------------------------------------


def game_source_path(worker_dir: Path) -> Path:
    """The game file in a worker dir OR an official's variant dir.

    Workers ship `game.py` (worker-template). An official ships
    `<slug>.py` next to `metadata.json` (`gen/officials.py`), so the fallback
    is "the one non-solver `.py` here". Fail loud when it is ambiguous — a
    verifier that guessed would attribute evidence to the wrong file.
    """
    worker_dir = Path(worker_dir)
    if not worker_dir.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker_dir}")
    named = worker_dir / "game.py"
    if named.is_file():
        return named
    candidates = sorted(
        p for p in worker_dir.glob("*.py") if p.is_file() and p.name not in GAME_FILE_SKIP
    )
    if len(candidates) != 1:
        raise AssertionError(
            f"{worker_dir}: no game.py and {len(candidates)} candidate game file(s) "
            f"{[p.name for p in candidates]!r} — cannot pick the game source"
        )
    return candidates[0]


def solver_source_path(worker_dir: Path) -> Path | None:
    """`solver.py` when the worker ships one, else None (officials never do)."""
    path = Path(worker_dir) / "solver.py"
    return path if path.is_file() else None


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    # Registration BEFORE exec: dataclass field resolution inside game files
    # looks the module up in sys.modules (`gen/officials.py` documents this).
    sys.modules[module_name] = module
    try:
        with quiet():
            spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def load_worker_classes(worker_dir: Path) -> tuple[type[ARCBaseGame], type | None]:
    """The worker's game class and, when present, its `Solver` class.

    THE PERMISSIVE loader, and the one every in-process stage path funnels
    through: S3-static's own checks, S3's structural gate, S4's baselines, S5's
    battery and S6 (through `_load_worker`). Nothing is cached here — both
    files are re-exec'd on every call — so the entries this function's own
    loads leave in `sys.modules` are never stale.

    Contract E-4: the WORKER's own `sys.modules` entries are evicted FIRST.
    The §7 solver skeleton caches its sibling game under a PATH-derived name,
    which an S2 rewrite does not change, so without this a re-drive in one
    long-lived process pairs a fresh game with a solver that planned against
    the old layout (`gen/worker.py`, "The §7 module-cache eviction").
    """
    purge_worker_modules(worker_dir)
    game_path = game_source_path(worker_dir)
    # Unique per directory: the orchestrator verifies many workers in one
    # process and every worker's file is named `game.py`, so a stem-only
    # module name would have each load clobber the last in `sys.modules`.
    tag = hashlib.sha256(str(game_path.resolve()).encode()).hexdigest()[:12]
    module = _load_module(game_path, f"s3_game_{game_path.stem}_{tag}")
    found = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, ARCBaseGame) and obj is not ARCBaseGame
    ]
    owned = [c for c in found if c.__module__ == module.__name__]
    if owned:
        found = owned
    if len(found) != 1:
        raise AssertionError(
            f"{game_path}: expected exactly ONE ARCBaseGame subclass, found "
            f"{sorted(c.__name__ for c in found)!r}"
        )
    solver_path = solver_source_path(worker_dir)
    solver_cls = None
    if solver_path is not None:
        solver_module = _load_module(solver_path, f"s3_solver_{game_path.stem}_{tag}")
        solver_cls = getattr(solver_module, "Solver", None)
        if not isinstance(solver_cls, type):
            raise AssertionError(f"{solver_path}: must define a class named Solver")
    return found[0], solver_cls


# --- AST primitives ---------------------------------------------------------


def _base_names(cls: ast.ClassDef) -> list[str]:
    names = []
    for base in cls.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


def _derived_classes(tree: ast.AST, root_name: str) -> list[ast.ClassDef]:
    """Classes deriving from `root_name`, directly or through the file.

    tn36's game class is two hops from `ARCBaseGame`, so a one-level check
    would miss it (`tn36.py:2572`).
    """
    classes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    derived: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, node in classes.items():
            if name in derived:
                continue
            bases = _base_names(node)
            if root_name in bases or any(b in derived for b in bases):
                derived.add(name)
                changed = True
    return [classes[name] for name in sorted(derived)]


def _methods(cls: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _self_root(node: ast.AST) -> str | None:
    """The root attribute of a `self.X[...].y` expression, else None."""
    current = node
    while isinstance(current, (ast.Attribute, ast.Subscript)):
        if isinstance(current, ast.Subscript):
            current = current.value
            continue
        if isinstance(current.value, ast.Name) and current.value.id == "self":
            return current.attr
        current = current.value
    return None


def _is_complete_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and (
        (isinstance(node.func, ast.Attribute) and node.func.attr == "complete_action")
        or (isinstance(node.func, ast.Name) and node.func.id == "complete_action")
    )


def _int_const(node: ast.AST, consts: dict[str, int] | None = None) -> int | None:
    """An int literal, a negated int literal, or a module/class int constant.

    `consts` matters: the worker template and `gen/tests/toy_worker/game.py`
    both name their palette (`WALL, PLAYER, GOAL = 4, 9, 12`), so a scanner
    that only saw literals would read those boards as having no colours at all.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        if isinstance(node.value, bool):
            return None
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _int_const(node.operand, consts)
        return None if inner is None else -inner
    if consts and isinstance(node, ast.Name):
        return consts.get(node.id)
    if isinstance(node, ast.BinOp):
        # `toxqhfsju : toxqhfsju + 2` (ls20.py:1546) is rows 61-63 once the
        # name resolves; without folding, a declared strip reads as computed.
        left = _int_const(node.left, consts)
        right = _int_const(node.right, consts)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.FloorDiv) and right != 0:
            return left // right
        if isinstance(node.op, ast.Mod) and right != 0:
            return left % right
    return None


def _int_constants(tree: ast.AST) -> dict[str, int]:
    """Module- and class-level `NAME = <int>` bindings, ambiguous ones dropped."""
    found: dict[str, list[int]] = {}

    def record(target: ast.AST, value: ast.AST) -> None:
        if isinstance(target, ast.Name):
            const = _int_const(value)
            if const is not None:
                found.setdefault(target.id, []).append(const)
            return
        if (
            isinstance(target, (ast.Tuple, ast.List))
            and isinstance(value, (ast.Tuple, ast.List))
            and len(target.elts) == len(value.elts)
        ):
            for sub_target, sub_value in zip(target.elts, value.elts):
                record(sub_target, sub_value)

    bodies = [getattr(tree, "body", [])]
    bodies += [node.body for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    for body in bodies:
        for stmt in body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    record(target, stmt.value)
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                record(stmt.target, stmt.value)
    return {name: values[0] for name, values in found.items() if len(set(values)) == 1}


def _str_const(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _kwarg(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _condition_roots(cls: ast.ClassDef) -> set[str]:
    """`self.X` roots that any test in the class reads.

    A write to one of these is what makes a continuation frame legitimate:
    the next `step()` call will take a different branch.
    """
    roots: set[str] = set()
    tests: list[ast.AST] = []
    for node in ast.walk(cls):
        if isinstance(node, (ast.If, ast.While, ast.IfExp)):
            tests.append(node.test)
        elif isinstance(node, (ast.BoolOp, ast.Compare)):
            tests.append(node)
        elif isinstance(node, ast.comprehension):
            tests.extend(node.ifs)
        elif isinstance(node, ast.match_case) and node.guard is not None:
            tests.append(node.guard)
    for test in tests:
        for sub in ast.walk(test):
            if isinstance(sub, ast.Attribute):
                root = _self_root(sub)
                if root:
                    roots.add(root)
    return roots - NON_PROGRESS_ROOTS


# --- complete_action dataflow ----------------------------------------------

_UNREACHABLE = "unreachable"


@dataclass
class _Exit:
    lineno: int
    kind: str
    writes: frozenset
    defensive: bool = False
    # True when some enclosing guard tests `self.action`: this exit is on an
    # ACTION-HANDLER path, and the engine re-enters step() for the SAME action.
    action_guarded: bool = False
    # Roots tested by guards that run BEFORE this exit's top-level branch. A
    # write into one of these is what makes the re-entry hit an earlier branch
    # instead of re-running the handler (ar25.py:1702, the corpus idiom).
    earlier_guard_roots: frozenset = frozenset()


class _CompletionAnalyzer:
    """Does every exit of `step()` either complete or make progress?

    Forward "definitely completed" dataflow with three corrections that the
    corpus forced (see the D8 log, adjudication 2): test-expression writes,
    branch writes merged back, and local aliases of `self.<attr>`.
    """

    def __init__(self, cls: ast.ClassDef) -> None:
        self.cls = cls
        self.methods = _methods(cls)
        self.condition_roots = _condition_roots(cls)
        self._completes: dict[str, bool] = {}
        self._writes: dict[str, frozenset] = {}
        self._in_progress: set[str] = set()

    # -- per-method summaries --
    def method_completes(self, name: str) -> bool:
        if name in self._completes:
            return self._completes[name]
        if name in self._in_progress or name not in self.methods:
            return False
        self._in_progress.add(name)
        state, exits, _ = self.walk(self.methods[name].body, False, set(), {})
        result = (state is True or state is _UNREACHABLE) and not exits
        self._in_progress.discard(name)
        self._completes[name] = result
        return result

    def method_writes(self, name: str) -> frozenset:
        if name in self._writes:
            return self._writes[name]
        if name in self._in_progress or name not in self.methods:
            return frozenset()
        self._in_progress.add(name)
        node = self.methods[name]
        aliases: dict[str, str] = {}
        roots: set[str] = set()
        for stmt in ast.walk(node):
            roots |= self.statement_writes(stmt, aliases)
        self._in_progress.discard(name)
        result = frozenset(roots)
        self._writes[name] = result
        return result

    # -- write extraction --
    def expression_writes(self, node: ast.AST | None, aliases: dict[str, str]) -> set[str]:
        """`self.X` roots an expression can mutate (calls, walrus targets)."""
        out: set[str] = set()
        if node is None:
            return out
        for sub in ast.walk(node):
            if isinstance(sub, ast.NamedExpr):
                root = _self_root(sub.target)
                if root:
                    out.add(root)
            if not isinstance(sub, ast.Call) or not isinstance(sub.func, ast.Attribute):
                continue
            func = sub.func
            if isinstance(func.value, ast.Name):
                if func.value.id == "self":
                    if func.attr == "next_level":
                        out.add("__next_level__")
                    elif func.attr in self.methods:
                        out |= self.method_writes(func.attr)
                    continue
                aliased = aliases.get(func.value.id)
                if aliased:
                    out.add(aliased)
                    continue
            root = _self_root(func.value)
            if root:
                out.add(root)
        return out - NON_PROGRESS_ROOTS

    def statement_writes(self, stmt: ast.AST, aliases: dict[str, str]) -> set[str]:
        """`self.X` roots one statement writes, alias-aware, no block descent."""
        out: set[str] = set()
        if isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for target in targets:
                for sub in ast.walk(target):
                    root = _self_root(sub)
                    if root:
                        out.add(root)
                    if isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name):
                        aliased = aliases.get(sub.value.id)
                        if aliased:
                            out.add(aliased)
                    if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                        aliased = aliases.get(sub.value.id)
                        if aliased:
                            out.add(aliased)
            out |= self.expression_writes(getattr(stmt, "value", None), aliases)
            # `local = self.attr` records an alias for later mutation.
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                root = _self_root(stmt.value)
                if isinstance(target, ast.Name) and root:
                    aliases[target.id] = root
        elif isinstance(stmt, ast.Delete):
            for target in stmt.targets:
                root = _self_root(target)
                if root:
                    out.add(root)
        elif isinstance(stmt, (ast.Expr, ast.Return)):
            out |= self.expression_writes(stmt.value, aliases)
        return out - NON_PROGRESS_ROOTS

    @staticmethod
    def _merge(a, b):
        if a is _UNREACHABLE:
            return b
        if b is _UNREACHABLE:
            return a
        return bool(a) and bool(b)

    def _sets_complete(self, stmt: ast.AST) -> bool:
        for node in ast.walk(stmt):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if _is_complete_call(node):
                return True
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            if (
                isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "self"
            ):
                return self.method_completes(call.func.attr)
        return False

    @staticmethod
    def _is_absence_guard(test: ast.AST) -> bool:
        """`X is None` / `not X` on an engine-owned expression (defensive)."""
        parts = test.values if isinstance(test, ast.BoolOp) else [test]
        seen = False
        for part in parts:
            root = None
            if isinstance(part, ast.UnaryOp) and isinstance(part.op, ast.Not):
                root = _self_root(part.operand)
            elif isinstance(part, ast.Compare) and len(part.ops) == 1:
                op = part.ops[0]
                comparator = part.comparators[0]
                is_none = isinstance(comparator, ast.Constant) and comparator.value is None
                if isinstance(op, (ast.Is, ast.Eq)) and is_none:
                    root = _self_root(part.left)
            if root is None or root not in ENGINE_ROOTS:
                return False
            seen = True
        return seen

    @staticmethod
    def _tests_action(test: ast.AST) -> bool:
        """Does this guard read `self.action` (an action-handler branch)?"""
        return any(
            isinstance(sub, ast.Attribute) and _self_root(sub) in NON_PROGRESS_ROOTS
            for sub in ast.walk(test)
        )

    def walk(
        self,
        stmts,
        state,
        written: set[str],
        aliases: dict[str, str],
        defensive=False,
        action_guarded=False,
    ):
        """Return `(fallthrough_state, exits, written)` for a statement list."""
        exits: list[_Exit] = []
        written = set(written)
        aliases = dict(aliases)
        for stmt in stmts:
            if state is _UNREACHABLE:
                break
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(stmt, ast.Return):
                if stmt.value is not None and _is_complete_call(stmt.value):
                    state = True
                written |= self.statement_writes(stmt, aliases)
                if state is not True:
                    exits.append(
                        _Exit(
                            stmt.lineno,
                            "return",
                            frozenset(written),
                            defensive,
                            action_guarded,
                        )
                    )
                state = _UNREACHABLE
                continue
            if isinstance(stmt, (ast.Raise, ast.Break, ast.Continue)):
                state = _UNREACHABLE
                continue
            if isinstance(stmt, ast.If):
                written |= self.expression_writes(stmt.test, aliases)
                branch_defensive = defensive or self._is_absence_guard(stmt.test)
                guarded = action_guarded or self._tests_action(stmt.test)
                s1, e1, w1 = self.walk(
                    stmt.body, state, written, aliases, branch_defensive, guarded
                )
                if stmt.orelse:
                    s2, e2, w2 = self.walk(
                        stmt.orelse, state, written, aliases, defensive, guarded
                    )
                else:
                    s2, e2, w2 = state, [], set(written)
                exits.extend(e1 + e2)
                state = self._merge(s1, s2)
                written |= w1 | w2
                continue
            if isinstance(stmt, (ast.While, ast.For, ast.AsyncFor)):
                head = getattr(stmt, "test", None) or getattr(stmt, "iter", None)
                written |= self.expression_writes(head, aliases)
                _s1, e1, w1 = self.walk(
                    stmt.body, state, written, aliases, defensive, action_guarded
                )
                if stmt.orelse:
                    _s2, e2, w2 = self.walk(
                        stmt.orelse, state, written, aliases, defensive, action_guarded
                    )
                else:
                    e2, w2 = [], set(written)
                exits.extend(e1 + e2)
                written |= w1 | w2
                continue
            if isinstance(stmt, (ast.With, ast.AsyncWith)):
                state, e1, w1 = self.walk(
                    stmt.body, state, written, aliases, defensive, action_guarded
                )
                exits.extend(e1)
                written |= w1
                continue
            if isinstance(stmt, ast.Try):
                sb, e1, wb = self.walk(
                    stmt.body, state, written, aliases, defensive, action_guarded
                )
                written |= wb
                if stmt.orelse:
                    se, e2, we = self.walk(
                        stmt.orelse, sb, written, aliases, defensive, action_guarded
                    )
                    written |= we
                else:
                    se, e2 = sb, []
                exits.extend(e1 + e2)
                merged = se
                for handler in stmt.handlers:
                    sh, eh, wh = self.walk(
                        handler.body, state, written, aliases, defensive, action_guarded
                    )
                    exits.extend(eh)
                    written |= wh
                    merged = self._merge(merged, sh)
                if stmt.finalbody:
                    merged, ef, wf = self.walk(
                        stmt.finalbody, merged, written, aliases, defensive, action_guarded
                    )
                    exits.extend(ef)
                    written |= wf
                state = merged
                continue
            if isinstance(stmt, ast.Match):
                written |= self.expression_writes(stmt.subject, aliases)
                branches, wildcard = [], False
                for case in stmt.cases:
                    sc, ec, wc = self.walk(
                        case.body, state, written, aliases, defensive, action_guarded
                    )
                    exits.extend(ec)
                    branches.append(sc)
                    written |= wc
                    if isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None:
                        wildcard = True
                if not wildcard:
                    branches.append(state)
                merged = _UNREACHABLE
                for branch in branches:
                    merged = self._merge(merged, branch)
                state = merged
                continue
            written |= self.statement_writes(stmt, aliases)
            if self._sets_complete(stmt):
                state = True
        return state, exits, written

    def _guard_roots_before(self, step: ast.FunctionDef, lineno: int) -> frozenset:
        """Roots tested by a top-level `step()` guard that precedes `lineno`.

        The corpus idiom for a legitimate multi-frame handler (ar25.py:1702,
        bp35.py:4494, cd82.py:637) is: an animation guard sits FIRST in
        `step()`, the action branch arms it and returns, and the engine's
        re-entry is caught by that earlier guard instead of re-running the
        handler. A write into one of these roots is therefore the only thing
        that makes an action-guarded early return safe.
        """
        roots: set[str] = set()
        for stmt in step.body:
            if stmt.lineno >= lineno:
                break
            if isinstance(stmt, (ast.If, ast.While)):
                for sub in ast.walk(stmt.test):
                    if isinstance(sub, ast.Attribute):
                        root = _self_root(sub)
                        if root:
                            roots.add(root)
        return frozenset(roots - NON_PROGRESS_ROOTS)

    def analyze_step(self) -> tuple[list[_Exit], list[_Exit]]:
        """`(unjustified_exits, defensive_exits)` for this class's `step()`.

        An exit that leaves `step()` without `complete_action()` is safe only
        when the engine's re-entry does NOT re-run what the exit just did:

        * not action-guarded (a continuation/animation branch): the path must
          write a root some guard reads, so the next `step()` takes a
          different branch;
        * action-guarded (an ACTION-HANDLER path): the path must write a root
          tested by an EARLIER top-level guard, so the re-entry is caught
          before the handler runs again. Anything else re-executes the
          handler's side effects — the sc25 latent double-charge that
          affordance §8 names under the FORBIDDEN rule.
        """
        step = self.methods.get("step")
        if step is None:
            return [], []
        state, exits, written = self.walk(step.body, False, set(), {})
        if state is not True and state is not _UNREACHABLE:
            exits.append(
                _Exit(step.end_lineno or step.lineno, "fallthrough", frozenset(written))
            )
        continuation_roots = self.condition_roots | {"__next_level__"}
        unjustified, defensive = [], []
        for exit_ in exits:
            if exit_.action_guarded:
                earlier = self._guard_roots_before(step, exit_.lineno) | {"__next_level__"}
                exit_.earlier_guard_roots = earlier
                justified = bool(exit_.writes & earlier)
            else:
                justified = bool(exit_.writes & continuation_roots)
            if justified:
                continue
            (defensive if exit_.defensive else unjustified).append(exit_)
        return unjustified, defensive


# --- source model -----------------------------------------------------------


@dataclass
class _Source:
    """One parsed game file, plus the facts every check reads off it."""

    path: Path
    rel: str
    text: str
    tree: ast.AST
    game_classes: list[ast.ClassDef] = field(default_factory=list)
    display_classes: list[ast.ClassDef] = field(default_factory=list)
    int_consts: dict[str, int] = field(default_factory=dict)
    pixel_bindings: dict[str, ast.AST] = field(default_factory=dict)


def _parse_game(worker_dir: Path) -> _Source:
    path = game_source_path(worker_dir)
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:  # a file that does not parse is a hard stop
        raise ValueError(f"{path}:{exc.lineno or 0}: does not parse: {exc.msg}") from exc
    source = _Source(path=path, rel=path.name, text=text, tree=tree)
    source.int_consts = _int_constants(tree)
    source.pixel_bindings = _pixel_bindings(tree, source.int_consts)
    source.game_classes = _derived_classes(tree, "ARCBaseGame")
    source.display_classes = _derived_classes(tree, "RenderableUserDisplay")
    source.display_classes += [
        c
        for c in _derived_classes(tree, "ToggleableUserDisplay")
        if c not in source.display_classes
    ]
    if not source.game_classes:
        raise AssertionError(f"{path}: no ARCBaseGame subclass found in the source")
    return source


def _sprite_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "Sprite")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "Sprite")
        )
    ]


_ROW_NODES = (ast.List, ast.Tuple, ast.BinOp, ast.ListComp)


def _nested_int_lists(node: ast.AST, consts: dict[str, int] | None = None) -> list[ast.AST]:
    """Pixel data: any expression that resolves to a list of int rows.

    Three shapes appear across the corpus and the workers: a literal grid, a
    grid of `[c] * n` rows, and a comprehension `[[c] * n for _ in range(m)]`.
    """
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.ListComp) and len(sub.generators) == 1:
            count = _comprehension_length(sub.generators[0], consts)
            row = _row_values(sub.elt, consts)
            if count is not None and row:
                out.append(sub)
                continue
        if not isinstance(sub, (ast.List, ast.Tuple)):
            continue
        elts = sub.elts
        if not elts or not all(isinstance(e, _ROW_NODES) for e in elts):
            continue
        rows = [_row_values(row, consts) for row in elts]
        if all(row is not None and row for row in rows):
            out.append(sub)
    return out


def _row_values(row: ast.AST, consts: dict[str, int] | None = None) -> list[int] | None:
    """One pixel row as ints: a list/tuple of ints, `[c] * n`, or `[c for …]`.

    All three are corpus/worker idioms — `[[WALL] * 8]` in the toy worker and
    `[[TRAIL] * 3 for _ in range(3)]` in a seeded fixture — and a scanner that
    only understood literal rows reported those boards as carrying no colours
    at all, which silently disabled every palette rule on them.
    """
    if isinstance(row, (ast.List, ast.Tuple)):
        values = [_int_const(v, consts) for v in row.elts]
        return None if any(v is None for v in values) else values
    if isinstance(row, ast.BinOp) and isinstance(row.op, ast.Mult):
        for operand, repeat in ((row.left, row.right), (row.right, row.left)):
            count = _int_const(repeat, consts)
            if count is None or count < 1:
                continue
            inner = _row_values(operand, consts)
            if inner is not None:
                return inner * count
    if isinstance(row, ast.ListComp) and len(row.generators) == 1:
        count = _comprehension_length(row.generators[0], consts)
        element = _int_const(row.elt, consts)
        if count is not None and element is not None:
            return [element] * count
    return None


def _comprehension_length(gen: ast.comprehension, consts: dict[str, int] | None) -> int | None:
    """`for _ in range(n)` -> n; anything else is unknown."""
    if gen.ifs:
        return None
    iterator = gen.iter
    if (
        isinstance(iterator, ast.Call)
        and isinstance(iterator.func, ast.Name)
        and iterator.func.id == "range"
        and len(iterator.args) == 1
    ):
        return _int_const(iterator.args[0], consts)
    if isinstance(iterator, (ast.List, ast.Tuple)):
        return len(iterator.elts)
    return None


def _pixel_cells(literal: ast.AST, consts: dict[str, int] | None = None):
    """`(lineno, value)` for every cell of a nested pixel expression."""
    if isinstance(literal, ast.ListComp):
        count = _comprehension_length(literal.generators[0], consts) or 0
        values = _row_values(literal.elt, consts) or []
        for _ in range(count):
            for value in values:
                yield literal.lineno, value
        return
    for row in literal.elts:
        values = _row_values(row, consts)
        if values is None:
            continue
        lineno = getattr(row, "lineno", literal.lineno)
        for value in values:
            yield lineno, value


def _pixel_bindings(tree: ast.AST, consts: dict[str, int] | None = None) -> dict[str, ast.AST]:
    """Module/class-level `NAME = <pixel grid>` bindings.

    `CRATE_PIXELS = [[-2, …], …]` then `Sprite(CRATE_PIXELS, …)` is an ordinary
    authoring idiom; without this, the sprite looks like it ships no pixels
    and REQUIRED 5 silently has no premise.
    """
    bindings: dict[str, ast.AST] = {}
    bodies = [getattr(tree, "body", [])]
    bodies += [node.body for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    for body in bodies:
        for stmt in body:
            if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
                continue
            target = stmt.targets[0]
            if not isinstance(target, ast.Name):
                continue
            grids = _nested_int_lists(stmt.value, consts)
            if grids and grids[0] is stmt.value:
                bindings[target.id] = stmt.value
    return bindings


def _sprite_pixels(call: ast.Call, source: _Source) -> ast.AST | None:
    """The pixel expression a `Sprite(...)` call takes, names resolved."""
    pixels = _kwarg(call, "pixels")
    if pixels is None and call.args:
        pixels = call.args[0]
    if isinstance(pixels, ast.Name):
        return source.pixel_bindings.get(pixels.id)
    return pixels


def _sprite_pixel_colors(source: _Source) -> dict[int, int]:
    """Colours a real SPRITE carries, mapped to the line they first appear on.

    Scoped to `Sprite(pixels=...)` / `Sprite(<first arg>)` on purpose: a game
    file is full of other nested int lists (level layouts, coordinate tables,
    interface patterns) and counting those as "a colour an object carries"
    would make the palette rules fire on data no object ever renders.
    """
    consts = source.int_consts
    colors: dict[int, int] = {}
    for call in _sprite_calls(source.tree):
        pixels = _sprite_pixels(call, source)
        if pixels is None:
            continue
        for literal in _nested_int_lists(pixels, consts):
            for lineno, value in _pixel_cells(literal, consts):
                if COLOR_MIN <= value <= COLOR_MAX:
                    colors.setdefault(value, lineno)
    return colors


def _minus_two_sites_in_sprites(source: _Source) -> list[int]:
    """-2 rows reachable from a Sprite(...) call, names resolved."""
    return sorted({line for _call, lines in _minus_two_carriers(source) for line in lines})


def _minus_two_sites(tree: ast.AST, consts: dict[str, int] | None = None) -> list[int]:
    """Line numbers of nested-list literals that carry a `-2`."""
    lines = []
    for literal in _nested_int_lists(tree, consts):
        for lineno, value in _pixel_cells(literal, consts):
            if value == -2:
                lines.append(lineno)
    return sorted(set(lines))


# --- static pass 1: complete_action ----------------------------------------


def _check_complete_action(source: _Source) -> CheckResult:
    unjustified: list[tuple[str, _Exit]] = []
    defensive: list[tuple[str, _Exit]] = []
    stepped = False
    for cls in source.game_classes:
        if "step" not in _methods(cls):
            continue
        stepped = True
        bad, defended = _CompletionAnalyzer(cls).analyze_step()
        unjustified += [(cls.name, e) for e in bad]
        defensive += [(cls.name, e) for e in defended]

    if not stepped:
        return _result(
            "static.complete-action",
            "static",
            "premise-not-met",
            [Evidence(kind="code", path=source.rel, note="no step() on any game class")],
            "No game class overrides step(); the engine's own step() completes the "
            "action (base_game.py:331-339), so the FORBIDDEN pattern cannot arise.",
        )

    note_tail = ""
    if defensive:
        note_tail = (
            " Not counted: "
            + ", ".join(f"{cls}:{e.lineno}" for cls, e in defensive)
            + " — defensive absence-guard(s) on engine-owned structure "
            "(D8 adjudication 3, cn04.py:1119)."
        )
    if unjustified:
        evidence = [
            Evidence(
                kind="code",
                path=source.rel,
                line=exit_.lineno,
                note=(
                    f"{cls}.step() {exit_.kind} leaves an ACTION-HANDLER path without "
                    "complete_action(); the engine re-enters step() for the same action "
                    "and no earlier guard intercepts it, so the handler's side effects "
                    "run twice"
                )
                if exit_.action_guarded
                else f"{cls}.step() {exit_.kind} leaves without complete_action() and "
                "writes nothing any guard reads",
            )
            for cls, exit_ in unjustified
        ]
        return _result(
            "static.complete-action",
            "static",
            "fail",
            evidence,
            "FORBIDDEN (spec §2 / affordance §8): 'leaving a handler without "
            "complete_action() — the engine re-runs the action'. These exits leave "
            "step() with the guard state unchanged, so perform_action "
            "(base_game.py:224-236) calls step() again on identical state until it "
            "raises ValueError('Action took too many frames')." + note_tail,
        )
    return _result(
        "static.complete-action",
        "static",
        "pass",
        [
            Evidence(
                kind="code",
                path=source.rel,
                line=_methods(cls).get("step").lineno,
                note=f"{cls.name}.step(): every exit completes or advances guard state",
            )
            for cls in source.game_classes
            if "step" in _methods(cls)
        ],
        "Every step() exit either calls complete_action() or writes a self attribute "
        "a guard reads (a legitimate continuation frame)." + note_tail,
    )


# --- static pass 2: sys_click truthfulness ---------------------------------


def _click_facts(source: _Source) -> dict:
    tag_lines: list[int] = []
    for node in ast.walk(source.tree):
        value = _str_const(node)
        if value in CLICK_TAGS:
            tag_lines.append(node.lineno)
    handler_lines: list[int] = []
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Attribute) and node.attr in ("ACTION6", "ACTION7"):
            handler_lines.append(node.lineno)
        elif isinstance(node, ast.Subscript):
            key = _str_const(node.slice)
            if key in ("x", "y") and _self_root(node.value) == "action":
                handler_lines.append(node.lineno)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and _str_const(node.args[0]) in ("x", "y")
        ):
            handler_lines.append(node.lineno)
    override_line = None
    for cls in source.game_classes:
        method = _methods(cls).get("_is_sprite_clickable_now")
        if method is not None:
            override_line = method.lineno
    return {
        "tag_lines": sorted(set(tag_lines)),
        "handler_lines": sorted(set(handler_lines)),
        "override_line": override_line,
    }


def _handler_targets(source: _Source) -> tuple[set[str], list[int]]:
    """Sprite names/tags the code DISCRIMINATES on, with their lines.

    This is the other half of REQUIRED 2: the engine's click list is one
    fact, and what the click handler actually acts on is the other. A game
    that resolves the clicked cell and then branches on `hit.name == "switch"`
    has declared exactly one click target, whatever else it tagged.
    """
    targets: set[str] = set()
    lines: list[int] = []

    def take(node: ast.AST) -> None:
        value = _str_const(node)
        if value:
            targets.add(value)
            lines.append(node.lineno)
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            for element in node.elts:
                take(element)

    for node in ast.walk(source.tree):
        if isinstance(node, ast.Compare):
            for value in [node.left, *node.comparators]:
                take(value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr.startswith("get_sprites_by") or node.func.attr in (
                "get_sprite_at",
                "set_level_by_name",
            ):
                for argument in node.args:
                    take(argument)
        elif isinstance(node, ast.Subscript):
            take(node.slice)
    return targets, sorted(set(lines))


def _clickable_sprites(worker_dir: Path) -> list[tuple[int, str | None, tuple[str, ...]]]:
    """Every engine-clickable sprite across ALL levels: (level, name, tags).

    `FrameCapture.click_cells` carries the opening level's facts and no tags,
    which is not enough to judge truthfulness for a multi-level game, so this
    asks the engine directly. `_is_sprite_clickable_now` (`base_game.py:581`)
    is honoured exactly as `_get_valid_clickable_actions` honours it.
    """
    game_cls, _solver = load_worker_classes(worker_dir)
    game = _fresh_game(game_cls)
    _reset(game)
    found: list[tuple[int, str | None, tuple[str, ...]]] = []
    for index in range(len(game._levels)):
        with quiet():
            game.set_level(index)
        level = game.current_level
        for tag in CLICK_TAGS:
            for sprite in level.get_sprites_by_tag(tag):
                if not game._is_sprite_clickable_now(sprite):
                    continue
                found.append((index, _sprite_name(sprite), tuple(sprite.tags)))
    return found


def _check_sys_click(source: _Source, cap: FrameCapture, worker_dir: Path) -> CheckResult:
    facts = _click_facts(source)
    declared = GameAction.ACTION6.value in cap.available_action_ids
    tagged = bool(facts["tag_lines"])
    cells = cap.click_cells

    evidence = [
        Evidence(
            kind="engine",
            note=f"available_actions={list(cap.available_action_ids)}; engine click "
            f"list at RESET = {len(cells)} cell(s)",
        )
    ]
    if facts["tag_lines"]:
        evidence.append(
            Evidence(
                kind="code",
                path=source.rel,
                line=facts["tag_lines"][0],
                note=f"sys_click/sys_place tag literal ({len(facts['tag_lines'])} site(s))",
            )
        )
    if facts["override_line"] is not None:
        evidence.append(
            Evidence(
                kind="code",
                path=source.rel,
                line=facts["override_line"],
                note="_is_sprite_clickable_now overridden (base_game.py:581 seam); the "
                "engine click list above already honours it",
            )
        )

    if not tagged and not declared:
        return _result(
            "static.sys-click-truthful",
            "static",
            "premise-not-met",
            evidence,
            "No click tags and no ACTION6 in available_actions — REQUIRED 2 has no "
            "premise here.",
        )
    if tagged and not declared:
        return _result(
            "static.sys-click-truthful",
            "static",
            "fail",
            evidence,
            "sys_click/sys_place sprites exist but ACTION6 is not in "
            "available_actions: the tags advertise a click the game never offers. "
            "REQUIRED 2 (spec §2): 'sys_click tags are truthful — always'.",
        )
    if cells and not facts["handler_lines"]:
        return _result(
            "static.sys-click-truthful",
            "static",
            "fail",
            evidence,
            f"The engine reports {len(cells)} clickable cell(s) but no code path "
            "consumes a click (no ACTION6 reference and no action.data x/y read): "
            "the tags advertise an interaction nothing reads. REQUIRED 2.",
        )

    # The engine's tag facts vs what the handler actually acts on.
    targets, target_lines = _handler_targets(source)
    unhandled: list[tuple[int, str | None, tuple[str, ...]]] = []
    if tagged and targets:
        for level_index, name, tags in _clickable_sprites(worker_dir):
            if name is not None and name in targets:
                continue
            if any(tag in targets for tag in tags):
                continue
            unhandled.append((level_index, name, tags))
    if unhandled:
        evidence.extend(
            Evidence(
                kind="engine",
                note=f"level {level_index}: sprite {name!r} tags={list(tags)} is in the "
                "engine's click list and matches no name or tag the click handler "
                "branches on",
            )
            for level_index, name, tags in unhandled[:4]
        )
        if target_lines:
            evidence.append(
                Evidence(
                    kind="code",
                    path=source.rel,
                    line=target_lines[0],
                    note=f"the handler discriminates on {len(targets)} literal name/tag "
                    "string(s); these are the only click targets it acts on",
                )
            )
        return _result(
            "static.sys-click-truthful",
            "static",
            "fail",
            evidence,
            f"{len(unhandled)} engine-clickable sprite(s) are handled nowhere: the game "
            "tags them sys_click/sys_place, so the engine advertises a click action on "
            "them, but every click path branches on a different name or tag. REQUIRED 2 "
            "(spec §2): 'sys_click tags are truthful — always (the engine's "
            "click-action list and RL consumers read them)'.",
        )

    note = "Tags, the engine click list and the code's click targets agree."
    if declared and not cells:
        note = (
            "ACTION6 is declared with ZERO sys_click/sys_place sprites — the game "
            "reads raw coordinates and the engine click list is empty, which tells no "
            "lie (D8 adjudication 4: 6/25 officials ship this idiom; REQUIRED 2 makes "
            "visual click marking a knob)."
        )
    elif tagged and not targets:
        note = (
            "The click handler does not discriminate by sprite name or tag at all, so "
            "every tagged sprite reaches it; nothing is advertised that the handler "
            "cannot receive."
        )
    return _result("static.sys-click-truthful", "static", "pass", evidence, note)


# --- birth-time only (generated games): click targets must be TAGGED --------
#
# NOT one of the five `run_static_checks` passes, and deliberately not in that
# list — the same standing `_check_level_count` has below, for a structural
# reason: `run_static_checks` + `run_required_rows` IS the B2-calibrated
# 25-official battery when it runs over the corpus, and this rule is one the
# officials are explicitly NOT held to. A new id inside that list would be
# asserted against all 25; a new id outside it cannot move their counts at
# all. Registration is therefore the generated-only seam — S2's birth-time
# gate (`s2_implement._run_static_gate`, which already imports
# `_check_sys_click` and `_check_level_count` from here and runs only over
# workers this pipeline generated).
SYS_CLICK_GENERATED_CHECK = "static.sys-click-generated"


def _generated_source(worker_dir: Path) -> tuple[bool, str]:
    """Is this a GENERATED worker dir, or an official's variant dir?

    The tree already draws this line, in exactly one place, and this reuses it
    rather than inventing a second rule: `game_source_path` above — "Workers
    ship `game.py` (worker-template). An official ships `<slug>.py` next to
    `metadata.json` (`gen/officials.py`)". The game file's NAME is the whole
    discriminator. The scaffold markers beside it are reported as
    corroboration and never required: a tmp replay copy, a one-go fixture or a
    repaired worker can be missing `.scaffold-manifest.json` (`gen/worker.py`
    restores it as a REPAIR, so its absence is a repairable state), and a
    missing repairable file is not evidence that a game came from the signed
    corpus.
    """
    worker_dir = Path(worker_dir)
    if not (worker_dir / "game.py").is_file():
        return False, (
            f"{worker_dir.name}/ ships no game.py — the worker-template layout is "
            "absent, so this source is read as an official's variant dir "
            "(`<slug>.py` beside metadata.json, gen/officials.py)"
        )
    markers = [
        name
        for name in (".scaffold-manifest.json", "solver.py", "Makefile")
        if (worker_dir / name).is_file()
    ]
    corroboration = f"; scaffold markers beside it: {', '.join(markers)}" if markers else ""
    return True, (
        f"{worker_dir.name}/game.py — the worker-template layout, so this is a "
        f"GENERATED game{corroboration}"
    )


def _tagged_click_sprites(worker_dir: Path) -> tuple[list[tuple[int, str | None]], str | None]:
    """Every sprite carrying a `sys_click`/`sys_place` tag, across ALL levels.

    Deliberately NOT `_clickable_sprites`: that one honours
    `_is_sprite_clickable_now` because it judges the engine's click LIST at
    level init, and this asks the weaker question this ruling asks — does the
    game tag ANYTHING? A target a game tags and then gates behind its own
    clickability override is still a target a machine consumer can find, so
    gating it is not the defect here.

    Best-effort by design: a worker whose module cannot be loaded, constructed
    or reset returns the reason instead of raising. This runs inside a
    birth-time gate that owes the loop a verdict and a ledger row, and the
    caller puts the reason in the evidence rather than converting a load
    failure into a silent clean bill.
    """
    found: list[tuple[int, str | None]] = []
    try:
        game_cls, _solver = load_worker_classes(worker_dir)
        game = _fresh_game(game_cls)
        _reset(game)
        for index in range(len(game._levels)):
            with quiet():
                game.set_level(index)
            level = game.current_level
            for tag in CLICK_TAGS:
                for sprite in level.get_sprites_by_tag(tag):
                    found.append((index, _sprite_name(sprite)))
    except Exception as exc:  # noqa: BLE001 — generated code: any failure is evidence
        return [], f"the engine tag probe could not run ({type(exc).__name__}: {exc})"
    return found, None


def _check_sys_click_generated(
    source: _Source, cap: FrameCapture, worker_dir: Path
) -> CheckResult:
    """A GENERATED game that declares ACTION6 must tag its click targets.

    OPERATOR RULING (2026-09-28, refinement R-07). Machine consumers are the
    point: RL agents and duck ENUMERATE the engine's click list
    (`_get_valid_clickable_actions`, base_game.py:522, which is built from
    `get_sprites_by_tag("sys_click")` + `("sys_place")`). A game that declares
    ACTION6 while tagging nothing hands them an empty list for an action that
    is load-bearing, and the only way left to find a target is to guess raw
    coordinates. convoy-in-the-fog (b002) is the exhibit: `available_actions=
    [5, 6]`, an empty engine click list, zero `sys_click`/`sys_place`
    occurrences in its source, and 15 raw-coordinate ACTION6 clicks in its
    solver line.

    GENERATED ONLY, and that is not a hedge. `static.sys-click-truthful` keeps
    its D8 adjudication-4 semantics untouched: 6/25 officials (bp35, cd82,
    ft09, lf52, s5i5, su15) declare ACTION6 with zero tagged sprites and PASS,
    because "truthful" is a property of the tags that exist and an empty tag
    set tells no lie. That adjudication is about the SIGNED corpus, which this
    generator reads and never rewrites. What a generator owes its own output
    is a stronger contract than what a reader owes a corpus it inherited — so
    this is a second, separate check id, and the officials' battery never
    asserts it.

    NO CONFIG KNOB, deliberately (contract W2-B, pinned resolution). The house
    rule — new behavior defaults to today's, unconfigured runs are
    byte-identical — binds on the OFFICIALS' path, and there it holds exactly:
    this check is not in `run_static_checks`/`run_required_rows`, so every
    official's result set is byte-identical to before. For GENERATED games the
    unconfigured behavior MAY change, because this is a RULING rather than a
    measurement pass: it is a birth-time gate on games not yet built, and the
    seven shipped games are already packaged and are not re-gated. A knob
    would make a decided question re-openable per run, which is what a knob is
    for and this is not.

    The fail is stated on a CONJUNCTION of two independent measurements — no
    `sys_click`/`sys_place` literal anywhere in the source AND no tagged
    sprite in any level's engine tag index. Either one alone can be wrong in a
    different direction (the AST is blind to a tag built at runtime; the tag
    index is read at level init), and a fail here rejects a game at birth, so
    it is spent only where both agree the game tags nothing.
    """
    worker_dir = Path(worker_dir)
    generated, layout = _generated_source(worker_dir)
    declared = GameAction.ACTION6.value in cap.available_action_ids
    facts = _click_facts(source)
    tag_lines = facts["tag_lines"]

    evidence = [
        Evidence(kind="code", path=source.rel, note=layout),
        Evidence(
            kind="engine",
            note=f"available_actions={list(cap.available_action_ids)}; engine click "
            f"list at RESET = {len(cap.click_cells)} cell(s); "
            f"{len(tag_lines)} sys_click/sys_place literal(s) in the source",
        ),
    ]

    if not generated:
        return _result(
            SYS_CLICK_GENERATED_CHECK,
            "static",
            "premise-not-met",
            evidence,
            "This source is not a generated worker, and the ruling this check carries "
            "is about what the GENERATOR ships. The officials' raw-coordinate ACTION6 "
            "idiom stays legal for them (D8 adjudication 4: bp35, cd82, ft09, lf52, "
            "s5i5, su15); `static.sys-click-truthful` is the check that judges them, "
            "unchanged.",
        )
    if not declared:
        return _result(
            SYS_CLICK_GENERATED_CHECK,
            "static",
            "pass",
            evidence,
            "ACTION6 is not in available_actions, so the game advertises no click and "
            "there is no click list for a machine consumer to enumerate. A "
            "keyboard-only generated game conforms to the ruling with nothing to tag.",
        )
    if tag_lines:
        evidence.append(
            Evidence(
                kind="code",
                path=source.rel,
                line=tag_lines[0],
                note=f"sys_click/sys_place tag literal ({len(tag_lines)} site(s))",
            )
        )
        return _result(
            SYS_CLICK_GENERATED_CHECK,
            "static",
            "pass",
            evidence,
            "ACTION6 is declared and the game tags click targets sys_click/sys_place, "
            "so the engine's click list is something a machine consumer can enumerate.",
        )

    # Zero literals + ACTION6 declared: before failing a game at birth, ask the
    # ENGINE whether anything is tagged at all (a tag the AST cannot see).
    tagged_sprites, probe_error = _tagged_click_sprites(worker_dir)
    if probe_error is not None:
        evidence.append(Evidence(kind="engine", note=probe_error))
    elif tagged_sprites:
        levels = sorted({index for index, _name in tagged_sprites})
        evidence.append(
            Evidence(
                kind="engine",
                note=f"{len(tagged_sprites)} sys_click/sys_place-tagged sprite(s) across "
                f"level(s) {levels} — tagged without a source literal the AST can see",
            )
        )
        return _result(
            SYS_CLICK_GENERATED_CHECK,
            "static",
            "pass",
            evidence,
            "No sys_click/sys_place literal appears in the source, but the engine's tag "
            "index carries tagged sprites, so the tags are built at runtime and the "
            "click list is still enumerable.",
        )
    else:
        evidence.append(
            Evidence(
                kind="engine",
                note="engine tag index across every level: 0 sys_click/sys_place-tagged "
                "sprite(s)",
            )
        )

    return _result(
        SYS_CLICK_GENERATED_CHECK,
        "static",
        "fail",
        evidence,
        "ACTION6 is declared in available_actions and the game tags ZERO sprites "
        "sys_click/sys_place, so the engine's click list is empty: MACHINE CONSUMERS "
        "CANNOT ENUMERATE CLICK TARGETS — an RL agent or duck reading the engine's "
        "click-action list is told this game has no clickable cell, while the game's "
        "own solution depends on clicking raw coordinates it can only guess. Generated "
        "games must tag the cells a click acts on (operator ruling, 2026-09-28): tag "
        "each click target sys_click (or sys_place), or drop ACTION6 from "
        "available_actions. The officials' untagged idiom is adjudicated legal for the "
        "signed corpus only (D8 adjudication 4) and is not a model to copy.",
    )


# --- birth-time only: implemented levels vs the spec's declared levels ------
#
# NOT one of the five `run_static_checks` passes, and deliberately not in that
# list: the S2b legs are SPEC-BLIND by design (architecture §3, blindness ⊕)
# and this one reads the spec. It runs only where the spec is legitimately in
# scope — S2's birth-time gate (`s2_implement._run_static_gate`), which fires
# in the session that wrote the game and costs one attempt to answer.
#
# Why it exists (contract C-4b): b003r2 slot 1 reached `played` implementing 3
# of its 7 declared levels. The merged gate's level floor reads S4's baseline
# count, S4 runs AFTER the gate, so that floor honestly recorded
# `premise-not-met` and nothing ever re-asked — the mismatch rode through to a
# packaged game ("we need more levels, 3 are too easy").
#
# The implemented count comes from the ENGINE, never from the AST: §7/D13
# levels are built from seeds inside comprehensions, so there is no literal to
# count and an AST count would be a guess dressed as a measurement.
LEVEL_COUNT_CHECK = "static.level-count-vs-spec"


def _declared_level_count(spec_path: Path | None) -> tuple[int | None, str]:
    """`len(spec["game"]["levels"])`, or `(None, why it cannot be read)`.

    EVERY failure mode here is a non-answer, never a defect: a worker with no
    spec beside it (the module CLI, the one-go fixtures) is not something this
    check can judge, and spec bytes that do not parse are a pipeline fact
    rather than a fact about the game.
    """
    if spec_path is None:
        return None, "no spec path was passed to the check"
    spec_path = Path(spec_path)
    if not spec_path.is_file():
        return None, f"no spec file at {spec_path}"
    try:
        doc = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return None, f"{spec_path} could not be read as YAML ({exc})"
    game = doc.get("game") if isinstance(doc, dict) else None
    levels = game.get("levels") if isinstance(game, dict) else None
    if not isinstance(levels, list) or not levels:
        return None, f"{spec_path} carries no non-empty `game.levels` list"
    return len(levels), ""


def _check_level_count(cap: FrameCapture, spec_path: Path | None) -> CheckResult:
    """The level count the game IMPLEMENTS vs the one its spec DECLARES.

    The implemented count is `cap.levels_completed`, and it is the implemented
    count only on a WON solver capture: the gate runs after `make validate`,
    whose scaffold test asserts the solver won with every level credited, so
    completed == total there. Any other capture (a probe, a loss) is an honest
    `premise-not-met` — it says how far a drive got, not how many levels exist.
    """
    evidence = [
        Evidence(
            kind="frame",
            frame_label=cap.records[-1].label if cap.records else None,
            note=f"capture source={cap.source}, win={cap.win}, "
            f"levels_completed={cap.levels_completed}",
        )
    ]
    if cap.source != "solver" or not cap.win:
        return _result(
            LEVEL_COUNT_CHECK,
            "static",
            "premise-not-met",
            evidence,
            "The implemented level count is read off a WON solver capture (the gate runs "
            "after `make validate`, whose scaffold test asserts the solver wins with every "
            f"level credited). This capture is source={cap.source!r}, win={cap.win}, so its "
            "levels_completed says how far one drive got, not how many levels the game "
            "ships — recorded, not failed.",
        )
    declared, why = _declared_level_count(spec_path)
    if declared is None:
        return _result(
            LEVEL_COUNT_CHECK,
            "static",
            "premise-not-met",
            [
                *evidence,
                Evidence(
                    kind="artifact",
                    path=None if spec_path is None else str(spec_path),
                    note=why,
                ),
            ],
            "The declared level count is `game.levels` in the spec this worker was built "
            f"from, and there is none to read: {why}. A worker without a readable spec "
            "beside it is not a defect this check can judge — recorded, not failed.",
        )
    implemented = int(cap.levels_completed)
    evidence.append(
        Evidence(
            kind="artifact",
            path=str(spec_path),
            note=f"`game.levels` declares {declared} level(s)",
        )
    )
    if implemented != declared:
        return _result(
            LEVEL_COUNT_CHECK,
            "static",
            "fail",
            evidence,
            f"The game implements {implemented} level(s) but its spec declares {declared}: "
            f"`game.levels` in {spec_path} has {declared} entr"
            f"{'y' if declared == 1 else 'ies'} and the winning solver capture credits "
            f"{implemented}. Implement every declared level — a game that ships "
            f"{implemented} of {declared} is not the game the spec was signed for.",
        )
    return _result(
        LEVEL_COUNT_CHECK,
        "static",
        "pass",
        evidence,
        f"{implemented} level(s) implemented and credited to the winning solver; "
        f"`game.levels` in {spec_path} declares {declared}. They agree.",
    )


# --- generated-only: look-alikes DRAWN vs look-alikes DECLARED (R-09) -------
#
# NOT one of the five `run_static_checks` passes, and, like
# `static.level-count-vs-spec` above, deliberately not in that list for two
# separate reasons:
#
#   * it reads the SPEC, and the S2b legs are spec-blind by design
#     (architecture §3, blindness ⊕). This one runs on the DIFF side of that
#     boundary — at report assembly, after the blind session has closed, in
#     the same place `compute_diff` compares blind claims against intent — so
#     the auditor never sees a byte of it.
#   * it is GENERATED-ONLY, the W2-B pattern (`static.sys-click-generated`):
#     the officials' battery never asserts it, `run_static_checks` does not
#     carry it, and an official source is `premise-not-met` by construction.
#     The house rule — new behaviour defaults to today's, unconfigured runs
#     byte-identical — therefore holds exactly where W2-B says it binds: on
#     the OFFICIALS' path, whose result sets and counts are untouched.
#
# WHY IT EXISTS (contract A3 / R-09; comparative-audit finding B4). Spec §10
# makes "deception is always a DECLARED property, never an accident" the
# intent verifier's job, and the audit measured it failing in BOTH directions
# on our own shipped games:
#
#   present-but-undeclared — pump-phase-time-echo draws `pump`, `filler` and
#     `block` as three identical 4x4 flat solids (measured: level 7, indices
#     9 / 1 / 0, footprints identical, `block` alone untagged), and its
#     `knobs.deceptions` names neither `filler` nor `block`;
#     pump-flow-match-glow routes FOUR kinds through one `_draw_tile(...,
#     C_PIPE, ..., device=…)` call (game.py:1321-1322) and declares two of
#     them; conduit-watch declares `deceptions: []`.
#   declared-but-absent — pump-flow's palette-overload entry claims fog
#     "color 2" doubles as the junction silhouette, while the silhouette
#     family is drawn in index 3 and index 2 is only ever the fog stub.
#
# THE FALSE-POSITIVE TRAP, pinned: ADJACENCY FUSION. conduit-watch paints one
# 2x2 sprite per lattice cell, and a conduit run is by construction a
# CONNECTED chain — every tile in every level touches another tile of the same
# footprint family (measured: level 0, 3 adjacency pairs over 4 tiles; level
# 2, 8 over 9). Two objects that render orthogonally adjacent do not present
# two silhouettes to a player at all: they fuse into one component, and with a
# shared index they are literally one blob. That is a RENDER consequence of
# tiling, not an authored look-alike, so a family member adjacent to another
# member of its own family is dropped BEFORE the behaviour comparison. This is
# what makes conduit silent — including the seam beacon pair the contract names
# — while pump-phase's three slot tiles, which sit a `PITCH`-wide gap apart,
# still fire.
#
# EVIDENCE, NOT A GATE. The detector is heuristic: it reads footprints, tags
# and one AST idiom, and it is graded against free prose. So it takes
# `off | record | fail` and is born in `record` — findings land on the record
# for the S5 human review and change no verdict. `fail` is the armed gate and
# is opted into per batch, exactly like the gate's own measurement knobs
# (`gen/s3_visual.py`). The verifier's REJECT logic gains nothing from this
# module in `record`: the corroboration machinery already governs rejects.
LOOKALIKE_CHECK = "static.lookalike-declared"
LOOKALIKE_MODES = ("off", "record", "fail")
DEFAULT_LOOKALIKE_MODE = "record"

# A whole-board canvas is not an object: a sprite this large is a LAYER (the
# corpus draws them — pump-flow's `terrain`, mosaic's `board`), and a layer has
# no silhouette to be mistaken for another layer's. Well above the largest
# object footprint the shipped games draw (pump-flow's 64-cell meter).
LOOKALIKE_MAX_CELLS = 512

# The one falsifiable thing in an otherwise free-prose deception entry: the
# palette index it names. "fog color 2", "colour index 9", "idx 3".
_DECLARED_INDEX_RE = re.compile(r"\b(?:colou?rs?|index|indices|idx)\s*#?\s*(\d{1,2})\b")

_ADJACENT = ((1, 0), (-1, 0), (0, 1), (0, -1))

# `gate-0`, `tile-3-2`, `pip_1` — the corpus names sprite INSTANCES by index
# (`name=f"tile-{x}-{y}"`, conduit-watch:526). A spec declares KINDS ("the
# gates share one silhouette"), never instances, so the instance suffix is
# stripped before a family is named or grounded: otherwise every generated
# game reads as undeclared because no prose could ever spell `gate-4`.
_INSTANCE_SUFFIX_RE = re.compile(r"[-_]\d+$")


@dataclass(frozen=True)
class LookalikeReport:
    """The both-direction R-09 answer: what was drawn, what was declared.

    `undeclared_found` — look-alike families the code draws that no declared
    `knobs.deceptions` entry names. `declared_ungrounded` — declared entries
    this module can falsify against the paint sites. Both are lists of
    human-readable finding lines, the shape the report's optional `lookalikes`
    block carries; `result` is the same answer as a `CheckResult`, so a caller
    that arms `fail` can hand it to `decide_verdict` unchanged.
    """

    undeclared_found: tuple[str, ...]
    declared_ungrounded: tuple[str, ...]
    result: CheckResult


def _lookalike_kind(name: str) -> str:
    """An object's KIND: its name with every instance index stripped."""
    kind = str(name)
    while True:
        stripped = _INSTANCE_SUFFIX_RE.sub("", kind)
        if stripped == kind or not stripped:
            return kind
        kind = stripped


def _lookalike_subject_stem(subject: str) -> str:
    """A declared entry names an object by word, not by identifier.

    Squashed to letters and digits (the `_lever_aliases` idiom) and
    de-pluralized, so the sprite name `pump`, the kind key `pumps` and the
    prose "the pump cell" are one subject. Deliberately loose: a loose match
    GROUNDS a family, which suppresses a finding, and for a heuristic detector
    born in `record` the conservative error is to stay quiet.
    """
    stem = re.sub(r"[^a-z0-9]+", "", str(subject).lower())
    if len(stem) > 3 and stem.endswith("s"):
        stem = stem[:-1]
    return stem


def _grounding_entry(subject: str, declared: Sequence[str]) -> str | None:
    """The declared entry whose prose NAMES `subject`, or None.

    A subject is matched by its WORDS, not by its identifier: a spec writer
    declares "the inert pad is drawn in palette index 9 with the same silhouette
    as the clickable pad", and the sprites are called `pad_live` and
    `pad_inert`. Requiring the identifier would make every faithful declaration
    read as undeclared, so ANY word of the identifier (three letters or more)
    being named grounds the subject.

    Deliberately loose, and the looseness runs the safe way: a loose match
    GROUNDS, which SUPPRESSES a finding, and for a heuristic detector born in
    `record` the conservative error is to stay quiet. It is still specific
    enough on the real corpus — pump-phase's four declared entries name `pump`
    and never `filler` or `block`, which is exactly finding B4.
    """
    words = [word for word in re.split(r"[^a-z0-9]+", str(subject).lower()) if word]
    for word in words:
        stem = _lookalike_subject_stem(word)
        if len(stem) < 3:  # "x", "ab" — too short to name anything
            continue
        pattern = re.compile(rf"\b{re.escape(stem)}[a-z]*\b")
        for entry in declared:
            if pattern.search(str(entry).lower()):
                return str(entry)
    return None


def _index_grounding_entry(indices: Sequence[int], declared: Sequence[str]) -> str | None:
    """The declared entry naming a palette index this family is drawn in.

    The other half of the same question, and the half the declared-but-absent
    direction already grades: an entry that says "palette index 9" about a
    family drawn in 9 has named it, whatever it called the objects.
    """
    wanted = {int(index) for index in indices}
    for entry in declared:
        named = {int(raw) for raw in _DECLARED_INDEX_RE.findall(str(entry))}
        if named & wanted:
            return str(entry)
    return None


def _sprite_cells(sprite) -> list[tuple[int, int, int]]:
    """`(y, x, index)` for every painted cell of a sprite, in BOARD coords.

    Painted = index >= 0: `-1` is transparent and `-2` is the engine's mask
    sentinel, and neither is something a player sees as part of a silhouette.
    Works on both pixel shapes the corpus ships — a numpy array and the plain
    list-of-lists that `Sprite(pixels=[[c] * n, …])` takes.
    """
    pixels = getattr(sprite, "pixels", None)
    if pixels is None:
        return []
    origin_x = int(getattr(sprite, "x", 0) or 0)
    origin_y = int(getattr(sprite, "y", 0) or 0)
    out: list[tuple[int, int, int]] = []
    try:
        height = len(pixels)
        for row_index in range(height):
            row = pixels[row_index]
            for column in range(len(row)):
                value = int(row[column])
                if value >= 0:
                    out.append((origin_y + row_index, origin_x + column, value))
    except (TypeError, ValueError, IndexError):  # generated code: any shape is possible
        return []
    return out


@dataclass(frozen=True)
class _LookalikeMember:
    level: int
    name: str
    index: int
    clickable: bool
    cells: frozenset[tuple[int, int]]


def _lookalike_members(
    worker_dir: Path,
) -> tuple[list[_LookalikeMember], dict[str, bool], str | None]:
    """Every FLAT-SOLID object the engine builds, level by level.

    Flat solid = one palette index over the whole painted footprint. That is
    the §7.1 look-alike premise stated in code: an object whose entire tell is
    its outline and its hue, which is what makes two of them mistakable. A
    multi-index sprite (pump-phase's pads, which carry a rim AND a core) draws
    its own distinguishing mark and is not in this family at all.

    The second return is `name -> is it click-tagged`, over EVERY sprite the
    engine builds and not only the flat-solid ones: the paint-site surface
    identifies its family members by sprite name and needs their click contract
    even when the level builder ships them blank (the §7/D13 idiom — born
    blank, painted in `_paint`, which is pump-phase verbatim).

    Best-effort by design, the `_tagged_click_sprites` idiom: a worker whose
    module cannot be loaded, constructed or reset returns the reason instead
    of raising, and the caller puts that reason in the evidence rather than
    turning a load failure into a silent clean bill.
    """
    members: list[_LookalikeMember] = []
    clickable_by_name: dict[str, bool] = {}
    try:
        game_cls, _solver = load_worker_classes(worker_dir)
        game = _fresh_game(game_cls)
        _reset(game)
        for level_index in range(len(game._levels)):
            with quiet():
                game.set_level(level_index)
            for sprite in game.current_level.get_sprites():
                name = _sprite_name(sprite) or "<unnamed>"
                clickable = bool(set(sprite.tags) & set(CLICK_TAGS))
                # A name tagged in ANY level advertises a click contract.
                clickable_by_name[name] = clickable_by_name.get(name, False) or clickable
                painted = _sprite_cells(sprite)
                if not painted or len(painted) > LOOKALIKE_MAX_CELLS:
                    continue
                indices = {value for _y, _x, value in painted}
                if len(indices) != 1:
                    continue
                members.append(
                    _LookalikeMember(
                        level=level_index,
                        name=name,
                        index=next(iter(indices)),
                        clickable=clickable,
                        cells=frozenset((y, x) for y, x, _v in painted),
                    )
                )
    except Exception as exc:  # noqa: BLE001 — generated code: any failure is evidence
        return [], {}, f"the engine sprite probe could not run ({type(exc).__name__}: {exc})"
    return members, clickable_by_name, None


def _shape_key(cells: frozenset[tuple[int, int]]) -> frozenset[tuple[int, int]]:
    """A footprint normalized to its own top-left corner."""
    top = min(y for y, _x in cells)
    left = min(x for _y, x in cells)
    return frozenset((y - top, x - left) for y, x in cells)


def _fused(members: Sequence[_LookalikeMember]) -> set[int]:
    """Positions of members that render ADJACENT to another member.

    THE PINNED FALSE-POSITIVE EXCLUSION (contract A3). Two objects whose
    painted cells touch orthogonally do not present two silhouettes: they fuse
    into one rendered component, and at a shared index they are one
    undifferentiated blob. conduit-watch's lattice is the exhibit — every tile
    abuts the next, including the seam beacon pair — and a tiling is a render
    consequence, never an authored look-alike.
    """
    owner: dict[tuple[int, int], int] = {}
    for position, member in enumerate(members):
        for cell in member.cells:
            owner[cell] = position
    fused: set[int] = set()
    for position, member in enumerate(members):
        for y, x in member.cells:
            for dy, dx in _ADJACENT:
                neighbour = owner.get((y + dy, x + dx))
                if neighbour is not None and neighbour != position:
                    fused.add(position)
                    fused.add(neighbour)
    return fused


def _sprite_lookalike_families(members: Sequence[_LookalikeMember]) -> list[dict]:
    """Per level, flat-solid objects that share a footprint and differ in behaviour.

    Behaviour is the ADVERTISED click contract — the `sys_click`/`sys_place`
    tags REQUIRED 2 makes binding and the engine's click list is built from —
    read at level init, never `_is_sprite_clickable_now`. The override answers
    "is this legal RIGHT NOW", which is game STATE: conduit's own tiles differ
    on it from one board position to the next, and a detector keyed to it would
    be measuring the playthrough rather than the authoring.
    """
    grouped: dict[tuple[int, frozenset[tuple[int, int]]], list[_LookalikeMember]] = {}
    for member in members:
        grouped.setdefault((member.level, _shape_key(member.cells)), []).append(member)

    families: list[dict] = []
    for (level, shape), group in sorted(grouped.items(), key=lambda item: item[0][0]):
        if len(group) < 2:
            continue
        fused = _fused(group)
        kept = [member for position, member in enumerate(group) if position not in fused]
        if len({member.clickable for member in kept}) < 2:
            continue
        clickable = sorted({_lookalike_kind(m.name) for m in kept if m.clickable})
        inert = sorted({_lookalike_kind(m.name) for m in kept if not m.clickable})
        families.append(
            {
                "surface": "sprite",
                "level": level,
                "cells": len(shape),
                "members": len(kept),
                "indices": sorted({member.index for member in kept}),
                "subjects": sorted({_lookalike_kind(member.name) for member in kept}),
                "clickable": clickable,
                "inert": inert,
                "fused_out": sorted({_lookalike_kind(group[p].name) for p in fused}),
            }
        )
    return families


def _kind_key(node: ast.AST) -> str | None:
    """The NAME of a collection a membership test asks about.

    `cfg["pumps"]` -> `pumps`, `self._gates` -> `gates`, `junctions` ->
    `junctions`. These are the code's own kind vocabulary, which is what makes
    "N kinds, one glyph" a statement about authoring rather than about pixels.
    """
    if isinstance(node, ast.Subscript):
        key = _str_const(node.slice)
        return key or None
    if isinstance(node, ast.Attribute):
        return node.attr.lstrip("_") or None
    if isinstance(node, ast.Name):
        return node.id.lstrip("_") or None
    return None


def _or_membership_kinds(node: ast.AST) -> list[str]:
    """Distinct kind names in `x in A or x in B or …`, in source order."""
    if not isinstance(node, ast.BoolOp) or not isinstance(node.op, ast.Or):
        return []
    kinds: list[str] = []
    for value in node.values:
        if not isinstance(value, ast.Compare) or len(value.ops) != 1:
            return []
        if not isinstance(value.ops[0], ast.In):
            return []
        key = _kind_key(value.comparators[0])
        if key is None:
            return []
        if key not in kinds:
            kinds.append(key)
    return kinds


def _named_color_args(call: ast.Call, consts: dict[str, int]) -> list[tuple[str, int]]:
    """Palette constants passed by NAME to `call` — `C_PIPE`, never a bare `3`.

    Named only, on purpose: a game file is full of small ints in palette range
    that are layers, strides and counts (`layer=1`, `PITCH=6`), and treating
    those as colours would make this fire on every call in the corpus. Every
    shipped game names its palette (`C_PIPE = 3`, `C_LOCKED = 9`).
    """
    found: list[tuple[str, int]] = []
    for argument in [*call.args, *(keyword.value for keyword in call.keywords)]:
        if not isinstance(argument, ast.Name):
            continue
        value = consts.get(argument.id)
        if value is None or not (COLOR_MIN <= value <= COLOR_MAX):
            continue
        if (argument.id, value) not in found:
            found.append((argument.id, value))
    return found


def _paint_target_subject(target: ast.AST) -> str | None:
    """Who a `X[...] = <colour>` statement paints.

    The corpus names the object two ways and both are read here: by NAME
    (`level.get_sprites_by_name("pad_live")[0].pixels[:, :] = PAD`, which is the
    §7/D13 blank-then-paint idiom) and by the local it was bound to
    (`cells[:, :] = C_DANGER`). A string literal inside the target wins, because
    it is the sprite's real identity and the local is just a variable.
    """
    for node in ast.walk(target):
        literal = _str_const(node)
        if literal:
            return literal
    node = target
    while isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Attribute):
        return node.attr.lstrip("_") or None
    if isinstance(node, ast.Name):
        return node.id.lstrip("_") or None
    return None


def _flat_paint_families(source: _Source, clickable_by_name: Mapping[str, bool]) -> list[dict]:
    """One flat colour written into TWO OR MORE objects whose click contract differs.

    The second paint-site shape, and the one the corpus actually ships most:
    sprites are born blank and a `_paint` pass writes a single palette constant
    into each footprint, so there is no pixel literal for a sprite scan to read
    and — when `_paint` runs from `step()` rather than at level init — nothing
    on the board at level start either. pump-phase is this idiom verbatim.

    The behaviour half is asked of the ENGINE, not guessed: a family is a
    finding only when at least two of its named subjects are real sprites whose
    `sys_click`/`sys_place` contracts DISAGREE. That is what keeps this leg off
    the many legitimate sites where one canvas local is painted several colours.
    """
    painted: dict[tuple[str, int], list[tuple[str, int]]] = {}
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Subscript):
            continue
        if not isinstance(node.value, ast.Name):
            continue
        index = source.int_consts.get(node.value.id)
        if index is None or not (COLOR_MIN <= index <= COLOR_MAX):
            continue
        subject = _paint_target_subject(target)
        if subject is None:
            continue
        painted.setdefault((node.value.id, index), []).append((subject, node.lineno))

    families: list[dict] = []
    for (color_name, index), sites in sorted(painted.items()):
        subjects = sorted({subject for subject, _line in sites})
        known = [subject for subject in subjects if subject in clickable_by_name]
        if len(subjects) < 2 or len(known) < 2:
            continue
        if len({clickable_by_name[subject] for subject in known}) < 2:
            continue
        families.append(
            {
                "surface": "paint-site",
                "level": None,
                "index": index,
                "color_name": color_name,
                "subjects": subjects,
                "clickable": sorted(s for s in known if clickable_by_name[s]),
                "inert": sorted(s for s in known if not clickable_by_name[s]),
                "line": min(line for _subject, line in sites),
                "selector_line": min(line for _subject, line in sites),
            }
        )
    return families


def _paint_site_lookalike_families(source: _Source) -> list[dict]:
    """One paint call, one colour, TWO OR MORE kinds — the pump-flow idiom.

    A sprite-level scan cannot see this family: pump-flow paints its whole
    board into a handful of layer canvases, so the four kinds that share the
    junction glyph are one `terrain` sprite by the time the engine sees them.
    The authoring is still in the source, and it is explicit —

        device = cell in cfg["pumps"] or cell in cfg["junctions"] or cell in cfg["gates"]
        _draw_tile(canvas, cell, C_PIPE, self._arms[cell], device=device)

    — a disjunction over the game's own kind keys, routed through ONE draw
    carrying ONE named palette constant. Both the flag form above and the
    direct form (the disjunction handed to the call itself) are matched.
    """
    families: list[dict] = []
    seen: set[tuple[int, str, tuple[str, ...]]] = set()
    for node in ast.walk(source.tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        flags: dict[str, tuple[list[str], int]] = {}
        for statement in ast.walk(node):
            if (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
            ):
                kinds = _or_membership_kinds(statement.value)
                if len(kinds) >= 2:
                    flags[statement.targets[0].id] = (kinds, statement.lineno)
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            colors = _named_color_args(call, source.int_consts)
            if len(colors) != 1:
                continue
            color_name, color_index = colors[0]
            kinds: list[str] = []
            declared_at = call.lineno
            for argument in [*call.args, *(kw.value for kw in call.keywords)]:
                kinds = kinds or _or_membership_kinds(argument)
            if not kinds:
                referenced = {
                    sub.id for sub in ast.walk(call) if isinstance(sub, ast.Name)
                }
                for flag, (flag_kinds, flag_line) in flags.items():
                    if flag in referenced:
                        kinds, declared_at = flag_kinds, flag_line
                        break
            if len(kinds) < 2:
                continue
            fingerprint = (color_index, source.rel, tuple(kinds))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            families.append(
                {
                    "surface": "paint-site",
                    "level": None,
                    "index": color_index,
                    "color_name": color_name,
                    "subjects": list(kinds),
                    "line": call.lineno,
                    "selector_line": declared_at,
                }
            )
    return families


def _color_constant_sites(source: _Source, index: int) -> list[tuple[str, int]]:
    """`(constant name, line)` for every site that PAINTS `index`.

    Narrowed to paint contexts, and that narrowing is load-bearing: a game file
    carries plenty of small ints in palette range that are not colours, and
    naming them here would answer "where is index 2 painted" with a direction
    table. pump-flow measured: value 2 is `C_FOG` (painted), `LEFT` (a
    direction), `PHASE_TELEGRAPH` and `DRAIN_SLACK` (counters). A PAINT is the
    constant handed to a call (`np.where(stub == -2, C_FOG, stub)`) or written
    into a buffer (`canvas[…] = C_FLOOR`); a comparison, an arithmetic operand
    and a lookup table are not.
    """
    names = {
        name
        for name, value in source.int_consts.items()
        if value == index and COLOR_MIN <= value <= COLOR_MAX
    }
    if not names:
        return []
    painted: set[ast.AST] = set()
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Call):
            painted.update(node.args)
            painted.update(keyword.value for keyword in node.keywords)
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Subscript) for target in targets):
                painted.add(node.value)
    sites = {
        (node.id, node.lineno)
        for node in painted
        if isinstance(node, ast.Name) and node.id in names
    }
    return sorted(sites, key=lambda item: (item[1], item[0]))


def _declared_deception_entries(spec_path: Path | None) -> tuple[list[str], str]:
    """The spec's RAW `game.knobs.deceptions` prose, or `(…, why not)`.

    Raw, not normalized to catalog keywords: `s3_verify._declared_deceptions`
    folds each entry onto its §7.1 lever, and the lever is exactly the part
    this check does NOT need — grounding asks whether the entry NAMES the
    object or the index it is about, and that lives in the prose.

    Every failure mode is a non-answer, never a defect (`_declared_level_count`
    sets the precedent): a worker with no spec beside it is not something this
    check can judge.
    """
    if spec_path is None:
        return [], "no spec path was passed to the check"
    spec_path = Path(spec_path)
    if not spec_path.is_file():
        return [], f"no spec file at {spec_path}"
    try:
        doc = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return [], f"{spec_path} could not be read as YAML ({exc})"
    game = doc.get("game") if isinstance(doc, dict) else None
    knobs = game.get("knobs") if isinstance(game, dict) else None
    if not isinstance(knobs, dict) or "deceptions" not in knobs:
        return [], f"{spec_path} declares no `game.knobs.deceptions` list"
    entries = knobs.get("deceptions") or []
    if not isinstance(entries, list):
        return [], f"{spec_path} `game.knobs.deceptions` is not a list"
    return [str(entry) for entry in entries], ""


def check_lookalike_declared(
    worker_dir: Path,
    spec_path: Path | None,
    *,
    mode: str = DEFAULT_LOOKALIKE_MODE,
) -> CheckResult | None:
    """R-09, verified BOTH directions: look-alikes drawn vs look-alikes declared.

    The check, in the shape every other check in this module has: one
    `CheckResult`, or None when the knob is `off`. `lookalike_report` below is
    the same answer WITH the two direction lists broken out, for the report's
    optional `lookalikes` block; this is the entry a checks list wants.
    """
    found = lookalike_report(worker_dir, spec_path, mode=mode)
    return None if found is None else found.result


def lookalike_report(
    worker_dir: Path,
    spec_path: Path | None,
    *,
    mode: str = DEFAULT_LOOKALIKE_MODE,
) -> LookalikeReport | None:
    """`check_lookalike_declared`'s verdict plus its two direction lists.

    `off` returns None and does nothing at all — no engine probe, no spec read,
    no record. `record` (the default) reports every finding and returns a
    `deferred` result, which `decide_verdict` never rejects on. `fail` returns
    the same findings as a failing `static` check, which does.
    """
    if mode not in LOOKALIKE_MODES:
        raise ValueError(f"lookalike mode must be one of {list(LOOKALIKE_MODES)}, got {mode!r}")
    if mode == "off":
        return None

    worker_dir = Path(worker_dir)
    generated, layout = _generated_source(worker_dir)
    evidence = [Evidence(kind="code", path="game.py", note=layout)]
    if not generated:
        return LookalikeReport(
            (),
            (),
            _result(
                LOOKALIKE_CHECK,
                "static",
                "premise-not-met",
                evidence,
                "This source is not a generated worker. R-09 is a contract on what the "
                "GENERATOR declares about its own games (spec §10: deception is always a "
                "DECLARED property); the signed officials carry no spec to diff against "
                "and this check never judges them.",
            ),
        )

    source = _parse_game(worker_dir)
    declared, why_not = _declared_deception_entries(spec_path)
    members, clickable_by_name, probe_error = _lookalike_members(worker_dir)
    sprite_families = _sprite_lookalike_families(members)
    paint_families = [
        *_flat_paint_families(source, clickable_by_name),
        *_paint_site_lookalike_families(source),
    ]
    families = [*sprite_families, *paint_families]

    if probe_error is not None:
        evidence.append(Evidence(kind="engine", note=probe_error))
    else:
        evidence.append(
            Evidence(
                kind="engine",
                note=f"{len(members)} flat-solid object(s) across every level; "
                f"{len(sprite_families)} sprite family(ies) and {len(paint_families)} "
                f"paint-site family(ies) survive the adjacency-fusion exclusion",
            )
        )

    if why_not:
        return LookalikeReport(
            (),
            (),
            _result(
                LOOKALIKE_CHECK,
                "static",
                "premise-not-met",
                [*evidence, Evidence(kind="artifact", path=str(spec_path or ""), note=why_not)],
                f"The declared side of R-09 is `game.knobs.deceptions` in the spec this "
                f"worker was built from, and there is none to read: {why_not}. "
                f"{len(families)} look-alike family(ies) were found in the code and are "
                f"recorded in the evidence — recorded, not failed.",
            ),
        )

    undeclared: list[str] = []
    for family in families:
        subjects = list(family["subjects"])
        family_indices = family.get("indices") or [family["index"]]
        # Grounded either way a spec writer can name a family: by the OBJECTS it
        # is about, or by the palette INDEX they share. Both are declarations of
        # the same property, and §10 asks for the property, not a spelling.
        if _index_grounding_entry(family_indices, declared) is not None:
            continue
        ungrounded = [name for name in subjects if _grounding_entry(name, declared) is None]
        if not ungrounded:
            continue
        if family["surface"] == "sprite":
            line = (
                f"level {family['level']}: {family['members']} flat-solid object(s) of "
                f"{len(subjects)} kind(s) share one "
                f"{family['cells']}-cell footprint in palette index(es) {family['indices']} "
                f"but not one click contract — clickable {family['clickable']}, inert "
                f"{family['inert']}; no declared deception names {ungrounded}"
            )
            evidence.append(
                Evidence(
                    kind="engine",
                    note=f"level {family['level']} footprint family {subjects} "
                    f"indices={family['indices']} clickable={family['clickable']} "
                    f"inert={family['inert']} fused-out={family['fused_out']}",
                )
            )
        else:
            contract = (
                f" — clickable {family['clickable']}, inert {family['inert']}"
                if "clickable" in family
                else ""
            )
            line = (
                f"{len(subjects)} kinds {subjects} are painted in one palette "
                f"index {family['index']} ({family['color_name']}) at one site, so they "
                f"ship one silhouette{contract}; no declared deception names {ungrounded}"
            )
            evidence.append(
                Evidence(
                    kind="code",
                    path=source.rel,
                    line=family["line"],
                    note=f"one draw, one colour {family['color_name']}="
                    f"{family['index']}, kinds {subjects} selected at line "
                    f"{family['selector_line']}",
                )
            )
        undeclared.append(line)

    drawn_indices = sorted(
        {index for family in families for index in family.get("indices", [])}
        | {family["index"] for family in families if family["surface"] == "paint-site"}
    )
    ungrounded_declarations: list[str] = []
    for entry in declared:
        for raw in _DECLARED_INDEX_RE.findall(entry):
            index = int(raw)
            if not (COLOR_MIN <= index <= COLOR_MAX) or index in drawn_indices:
                continue
            sites = _color_constant_sites(source, index)
            where = (
                ", ".join(f"{name} at {source.rel}:{line}" for name, line in sites[:3])
                if sites
                else "no named palette constant in this source carries it"
            )
            ungrounded_declarations.append(
                f"the declared entry {entry[:80]!r} names palette index {index}, and no "
                f"look-alike family is drawn in it ({where}); the families this game "
                f"actually draws are in index(es) {drawn_indices}"
            )
            evidence.append(
                Evidence(
                    kind="code",
                    path=source.rel,
                    line=sites[0][1] if sites else None,
                    note=f"declared index {index} vs drawn index(es) {drawn_indices}",
                )
            )

    findings = len(undeclared) + len(ungrounded_declarations)
    if not findings:
        return LookalikeReport(
            (),
            (),
            _result(
                LOOKALIKE_CHECK,
                "static",
                "pass",
                evidence,
                f"Every look-alike family this game draws is named by a declared "
                f"`knobs.deceptions` entry, and every declared entry that names a palette "
                f"index names one a family is drawn in. {len(declared)} declared entry(ies), "
                f"{len(families)} family(ies) after the adjacency-fusion exclusion.",
            ),
        )

    note = (
        f"Spec §10: deception is always a DECLARED property, never an accident — and this "
        f"game breaks that in {findings} place(s). "
        f"{len(undeclared)} look-alike family(ies) are DRAWN and undeclared; "
        f"{len(ungrounded_declarations)} declared entry(ies) name a palette index no family "
        f"is drawn in. Declare each family in `game.knobs.deceptions` naming the objects it "
        f"is about, or stop drawing it. Two objects that render ADJACENT are excluded "
        f"(they fuse into one component, which is a render consequence, not an authored "
        f"look-alike)."
    )
    if mode == "fail":
        return LookalikeReport(
            tuple(undeclared),
            tuple(ungrounded_declarations),
            _result(LOOKALIKE_CHECK, "static", "fail", evidence, note),
        )
    return LookalikeReport(
        tuple(undeclared),
        tuple(ungrounded_declarations),
        _result(
            LOOKALIKE_CHECK,
            "static",
            "deferred",
            evidence,
            f"RECORDED, NOT FAILED (`verifier.lookalike_declared: record`). {note}",
        ),
    )


# --- generated-only: §6's never-signal-and-charge rule (R-08) ---------------
#
# NOT one of the five `run_static_checks` passes, and, like
# `static.lookalike-declared` above, deliberately not in that list: it is
# GENERATED-ONLY, the W2-B pattern (`static.sys-click-generated`). The
# officials' battery never asserts it, `run_static_checks` does not carry it,
# and an official source is `premise-not-met` by construction — so the house
# rule ("new behaviour defaults to today's; unconfigured runs are
# byte-identical") holds exactly where W2-B says it binds, on the OFFICIALS'
# path, whose result sets and counts are untouched. Unlike the look-alike
# detector it reads NO spec: §6's rule is a property of the code alone.
#
# THE RULE, quoted from the payload's §6 block (affordance-language.md:L236,
# the same text `gen/canon_docs.py` ships to the implementer): "officials
# either charge silently or signal freely — never both", and the corpus
# measurement under it — 17/25 charge with no signal, 6/25 signal only into
# frames that are swallowed, and **2/25 show a real visible refusal and both
# make refused actions FREE**. A refusal that both draws and costs is the
# FORBIDDEN mixed case.
#
# WHY IT EXISTS (contract B3 / R-08; comparative-audit finding B4): it ships in
# two of our seven games. pump-phase-time-echo's refusal "costs a step and
# drains pressure anyway"; convoy-in-the-fog's "still rolls and still burns a
# drum". Both declare `refusal: visible`.
#
# THE SHAPE THIS CAN SEE, AND THE SCOPE THAT LEAVES (stated because a
# heuristic that hides its reach is worse than a narrow one). The check reads
# the RESOLVE-AND-CONTINUE idiom: an action handler that BINDS a refusal-named
# value ("refused = ('pad', i)", "self._refused_at = clicked") and then keeps
# going. That is the shape both exhibits ship and the only shape in which a
# static reader can tell that the charge happens on the refusal path at all.
# A handler that calls a refusal helper and returns immediately binds nothing
# and is reported `premise-not-met`, NOT `pass` — conduit-watch is exactly
# that (`self._refuse(...); return False`), its refusal is genuinely free, and
# this check declines to take credit for a verdict it did not earn.
#
# The three measurements are independent, and only their CONJUNCTION fails:
#
#   * the refusal PATH — a refusal-named binding inside a method reachable
#     from `step()` (an action resolves refusals; `on_set_level` clearing a
#     refusal flag at level setup is not a refusal path, and the reachability
#     walk is what keeps a level initializer's budget assignment out of the
#     charge set);
#   * the SIGNAL — the source draws the refusal: a sprite named or tagged for
#     it, a palette constant named for it, or a paint attributed to it;
#   * the CHARGE — a BUDGET mutation the refusal path does not skip.
#
# THE CHARGE IS BUDGET-ANCHORED, not "any state mutation", and that is the
# measurement that made the difference: facing-sentinel's refusal calls
# `self._adopt(nxt)` (it adopts the unchanged walk state) and would fail a
# naive any-mutation reading, while its one real charge, `self._charge()`,
# sits in the accept branch. §6's rule is about the BUDGET, so the counter is
# what is looked for — an attribute or method whose own name carries a budget
# word, or anything that calls one (convoy charges through two hops,
# `step -> _roll_one_cell -> _burn_one_drum`).
REFUSAL_HONEST_CHECK = "static.refusal-honest"
REFUSAL_HONEST_MODES = ("off", "record", "fail")
# Born in `record`, like `lookalike_declared` and every `gate:` mode knob: a
# new rejection earns its place on measured data, not on the day it is written.
DEFAULT_REFUSAL_HONEST_MODE = "record"

# What names a refusal. Whole words only (`_identifier_words` splits on `_` and
# camelCase), so `refresh` and `refuel` are not refusals.
REFUSAL_WORDS = frozenset(
    {"refuse", "refused", "refusal", "refusals", "refuses", "refusing"}
)
# What names the budget §6 is about. Every word here is one the SHIPPED corpus
# actually uses for its cost counter, so the list is a transcription rather
# than a guess: `_used` (pump-phase), `_budget` (conduit-watch,
# facing-sentinel), `_burn_one_drum` (convoy), `_charge` (facing-sentinel).
# The rest are the same idea's other spellings; `steps`/`moves`/`turn` are
# deliberately ABSENT — they name the action loop itself in half the corpus and
# would read every handler as a charge.
REFUSAL_BUDGET_WORDS = frozenset(
    {
        "budget", "used", "spent", "charge", "charged", "charges", "cost",
        "costs", "burn", "burned", "burns", "fuel", "energy", "quota",
        "allowance",
    }
)
# The engine calls that move a sprite without writing pixels. A refusal drawn
# by parking a flash sprite (conduit-watch's idiom) paints through these.
_SPRITE_MUTATORS = frozenset(
    {"set_position", "set_interaction", "set_visible", "set_pixels"}
)
# The one entry point the engine calls per action (`base_game.py`), and the
# root of the reachability walk that decides which methods resolve an action.
_STEP_METHOD = "step"


@dataclass(frozen=True)
class RefusalHonestReport:
    """§6's answer: the refusal path's charge sites, and the check that says so.

    `charged_and_signalled` is the list of human-readable finding lines — each
    one a budget mutation the refusal path reaches while the source also draws
    a refusal — and `result` is the same answer as a `CheckResult`, so a caller
    that arms `fail` can hand it to `decide_verdict` unchanged.
    """

    charged_and_signalled: tuple[str, ...]
    result: CheckResult


def _name_words(name: object) -> set[str]:
    """`C_REFUSE` -> {'c', 'refuse'}; `_refused_at` -> {'refused', 'at'}.

    NOT `_identifier_words` above, and the difference is measured rather than
    stylistic: that one splits before EVERY capital, which is right for
    `pendingConfirm` and shreds a SCREAMING_SNAKE_CASE constant into single
    letters (`C_REFUSE` -> {'c','e','f','r','s','u'}). Palette constants are the
    corpus's whole spelling for a refusal colour — `C_REFUSE` in
    facing-sentinel, `REFUSAL` in convoy — so a splitter that cannot read one is
    a splitter that cannot see the signal. Splitting only at a lower->upper
    boundary reads both families. `_identifier_words` keeps its own semantics:
    the lag/confirm scan is calibrated on them.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(name))
    return {word for word in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if word}


def _is_refusal_name(name: object) -> bool:
    return bool(_name_words(name) & REFUSAL_WORDS)


def _is_budget_name(name: object) -> bool:
    return bool(_name_words(name) & REFUSAL_BUDGET_WORDS)


def _mentions_refusal(node: ast.AST) -> bool:
    """Does any identifier or string literal under `node` name a refusal?"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and _is_refusal_name(sub.id):
            return True
        if isinstance(sub, ast.Attribute) and _is_refusal_name(sub.attr):
            return True
        literal = _str_const(sub)
        if literal and _is_refusal_name(literal):
            return True
    return False


def _assign_targets(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        return [node.target]
    return []


def _target_base(target: ast.AST) -> ast.AST:
    while isinstance(target, ast.Subscript):
        target = target.value
    return target


def _is_reset_value(value: ast.AST | None) -> bool:
    """Is this assigned value the "nothing was refused" sentinel?

    A FALSY literal, or `-1` — which is a literal too but arrives as
    `UnaryOp(USub, Constant(1))`, and missing that spelling is what once read
    facing-sentinel's `self._refused = -1` as a refusal decision and then
    charged its whole handler for a refusal it never made.

    The discriminator is measured on the corpus: every clear is a literal
    sentinel (`None` in convoy and pump-phase, `-1` in facing-sentinel) and
    every decision binds something COMPUTED — a name, a call, or a tuple with
    content (`("pad", index)`, `("filler",)`). A missed decision costs an honest
    `premise-not-met`; a missed reset costs a false positive on a correct game,
    so the doubt goes this way.
    """
    if value is None:
        return True
    if (
        isinstance(value, ast.UnaryOp)
        and isinstance(value.op, ast.USub)
        and isinstance(value.operand, ast.Constant)
        and isinstance(value.operand.value, (int, float))
        and not isinstance(value.operand.value, bool)
    ):
        return True
    if isinstance(value, ast.Constant):
        return not value.value
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return not value.elts
    if isinstance(value, ast.Dict):
        return not value.keys
    return False


def _refusal_binding(node: ast.AST) -> bool:
    """Is this statement a refusal DECISION — a refusal-named value bound?

    A sentinel value is a RESET, not a decision: every exhibit clears its marker
    at the top of the handler (`self._refused_at = None`, `self._refused = -1`)
    and clears it again at level setup, and reading those as refusal paths would
    make the whole handler — and every level initializer — a refusal path.
    """
    if isinstance(node, ast.Assign) and _is_reset_value(node.value):
        return False
    if isinstance(node, ast.AnnAssign) and _is_reset_value(node.value):
        return False
    for target in _assign_targets(node):
        base = _target_base(target)
        if isinstance(base, ast.Name) and _is_refusal_name(base.id):
            return True
        if isinstance(base, ast.Attribute) and _is_refusal_name(base.attr):
            return True
    return False


def _assigned_self_attr(node: ast.AST) -> str | None:
    """`self._used += 1` / `self._hud["used"] = …` -> the attribute name."""
    for target in _assign_targets(node):
        base = _target_base(target)
        if (
            isinstance(base, ast.Attribute)
            and isinstance(base.value, ast.Name)
            and base.value.id == "self"
        ):
            return base.attr
    return None


def _self_call_names(node: ast.AST) -> list[str]:
    return [
        sub.func.attr
        for sub in ast.walk(node)
        if isinstance(sub, ast.Call)
        and isinstance(sub.func, ast.Attribute)
        and isinstance(sub.func.value, ast.Name)
        and sub.func.value.id == "self"
    ]


def _refusal_palette_constants(consts: Mapping[str, int]) -> dict[str, int]:
    """Module constants named for a refusal that hold a palette index."""
    return {
        name: value
        for name, value in consts.items()
        if _is_refusal_name(name) and COLOR_MIN <= value <= COLOR_MAX
    }


def _is_paint(node: ast.AST, consts: Mapping[str, int]) -> bool:
    """Does this statement write colour onto something?

    The three idioms the corpus ships: a palette constant into a subscript
    (`tile[:, :] = C_FLASH`, `_flat_paint_families`' own rule), an assignment
    to a sprite's `.pixels`, and an engine sprite mutator call.
    """
    for target in _assign_targets(node):
        if isinstance(target, ast.Subscript) and isinstance(node, ast.Assign):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Name):
                    index = consts.get(sub.id)
                    if index is not None and COLOR_MIN <= index <= COLOR_MAX:
                        return True
                if (
                    isinstance(sub, ast.Constant)
                    and isinstance(sub.value, int)
                    and not isinstance(sub.value, bool)
                    and COLOR_MIN <= sub.value <= COLOR_MAX
                ):
                    return True
        base = target.value if isinstance(target, ast.Subscript) else target
        if isinstance(base, ast.Attribute) and base.attr == "pixels":
            return True
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        func = node.value.func
        if isinstance(func, ast.Attribute) and func.attr in _SPRITE_MUTATORS:
            return True
    return False


def _paint_subject_name(node: ast.AST) -> str | None:
    """Who a paint statement paints, by local or attribute name."""
    for target in _assign_targets(node):
        base = target
        if isinstance(base, ast.Attribute) and base.attr == "pixels":
            base = base.value
        base = _target_base(base)
        if isinstance(base, ast.Attribute):
            return base.attr
        if isinstance(base, ast.Name):
            return base.id
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        func = node.value.func
        if isinstance(func, ast.Attribute):
            owner = func.value
            if isinstance(owner, ast.Name):
                return owner.id
            if isinstance(owner, ast.Attribute):
                return owner.attr
    return None


_COMPOUND = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try,
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
)
# One entry per enclosing `if` a statement sits under:
# (the `If` node, the OTHER limb binds a refusal, this is the `else`).
_Guard = tuple[ast.If, bool, bool]


def _flatten(body: Sequence[ast.stmt], guards: list[_Guard], out: list) -> None:
    """Every statement in `body`, each with the `if` guards it sits under.

    Compound statements are recorded too (a marker anywhere inside one still
    makes its method a refusal path), and their children are recorded
    separately with the guard chain extended — which is what lets the charge
    scan below look at LEAF statements only and never read an `if`'s two limbs
    as one statement.
    """
    for stmt in body:
        out.append((stmt, list(guards)))
        if isinstance(stmt, ast.If):
            body_binds = any(
                _refusal_binding(node) for child in stmt.body for node in ast.walk(child)
            )
            else_binds = any(
                _refusal_binding(node) for child in stmt.orelse for node in ast.walk(child)
            )
            _flatten(stmt.body, [*guards, (stmt, else_binds, False)], out)
            _flatten(stmt.orelse, [*guards, (stmt, body_binds, True)], out)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.Try)):
            for field_name in ("body", "orelse", "finalbody"):
                _flatten(getattr(stmt, field_name, None) or [], guards, out)
            for handler in getattr(stmt, "handlers", None) or []:
                _flatten(handler.body, guards, out)


def _test_value(test: ast.AST, falsy: Callable[[str], bool]) -> bool | None:
    """What an `if` test is worth on the refusal path — True, False or unknown.

    Only the shapes a guard is actually written in: a bare local, `not local`,
    and `and`/`or` over those. Everything else is None, and None never excludes
    anything — an unreadable guard must widen the charge set, never narrow it.
    """
    if isinstance(test, ast.Constant):
        return bool(test.value)
    if isinstance(test, ast.Name):
        return False if falsy(test.id) else None
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _test_value(test.operand, falsy)
        return None if inner is None else not inner
    if isinstance(test, ast.BoolOp):
        values = [_test_value(value, falsy) for value in test.values]
        if isinstance(test.op, ast.And):
            if any(value is False for value in values):
                return False
            return True if all(value is True for value in values) else None
        if any(value is True for value in values):
            return True
        return False if all(value is False for value in values) else None
    return None


def _refusal_test_polarity(test: ast.AST) -> bool | None:
    """Which limb of `if <test>:` is the REFUSED one — True=body, False=else.

    A refusal marker is tested three ways across the corpus and the two readings
    are opposite, so the polarity has to be read rather than assumed:
    `if refused:` and `if self._refused_at is not None:` put the refusal in the
    BODY, while `if not refused:` and `if self._refused_at is None:` put it in
    the `else`. Getting this backwards on the `is None` spelling calls a charge
    that only the ACCEPTED action reaches a refusal charge, which is the false
    positive class this function exists to close.

    None whenever the shape is anything else — a test this cannot read must not
    decide which limb is which.
    """
    if isinstance(test, ast.Name) and _is_refusal_name(test.id):
        return True
    if isinstance(test, ast.Attribute) and _is_refusal_name(test.attr):
        return True
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _refusal_test_polarity(test.operand)
        return None if inner is None else not inner
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        left, op, right = test.left, test.ops[0], test.comparators[0]
        names_refusal = (isinstance(left, ast.Name) and _is_refusal_name(left.id)) or (
            isinstance(left, ast.Attribute) and _is_refusal_name(left.attr)
        )
        is_none = isinstance(right, ast.Constant) and right.value is None
        if names_refusal and is_none:
            if isinstance(op, (ast.Is, ast.Eq)):
                return False
            if isinstance(op, (ast.IsNot, ast.NotEq)):
                return True
    return None


def _off_refusal_path(guards: Sequence[_Guard], falsy: Callable[[str], bool]) -> bool:
    """Is a statement under these guards UNREACHABLE by a refused action?

    Three ways to be sure, and nothing else counts:

    * some enclosing `if` binds the refusal in its OTHER limb. That is the
      accept branch, structurally — facing-sentinel's `self._charge()` and
      pump-flow's `self.charge -= 1` both live there.
    * the guard's test is provably False here and this is the body limb (or
      provably True and this is the `else`). This is the FLAG idiom: a handler
      sets `moved = False`, sets it True only in the accept arm, and gates the
      charge on `if moved:`. Structurally the charge is after the branch and a
      "which limb is this?" reader calls it charged; it is not, and calling a
      free refusal charged is the one error class a check that can reject must
      not make.
    * the guard tests the refusal MARKER itself and this is the limb a refused
      action does not take — `_refusal_test_polarity` reads which limb that is,
      because `if refused:` and `if refused is None:` put it on opposite sides.
    """
    for node, sibling_binds, is_else in guards:
        if sibling_binds:
            return True
        polarity = _refusal_test_polarity(node.test)
        if polarity is not None:
            if polarity is not is_else:
                continue          # this IS the refused limb
            return True
        if _mentions_refusal(node.test) and is_else:
            # A refusal test this cannot read exactly: the `else` of one is the
            # not-refused branch under every spelling above, so it stays
            # excluded, and the body stays in scope.
            return True
        value = _test_value(node.test, falsy)
        if value is not None and ((value is False and not is_else) or (value is True and is_else)):
            return True
    return False


def _falsy_locals(statements: Sequence[tuple]) -> Callable[[str], bool]:
    """Which locals are provably falsy wherever a refused action reaches.

    A local qualifies when every binding a refused action REACHES gives it a
    falsy constant, and at least one such binding exists. Bindings in a limb the
    refusal never enters are irrelevant, which is exactly what makes
    `moved = False` / `if accept: moved = True` readable: the refusal path sees
    only the `False`.

    Conservative on purpose — a single binding on the path that is not a falsy
    constant disqualifies the name, and an augmented assignment disqualifies it
    too — because this function's answer only ever REMOVES charge sites.
    """
    reached: dict[str, bool] = {}

    def falsy_none(_name: str) -> bool:
        return False

    for stmt, guards in statements:
        if not isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            continue
        names = [
            target.id
            for target in _assign_targets(stmt)
            if isinstance(target, ast.Name)
        ]
        if not names:
            continue
        # The chain is read WITHOUT local knowledge (`falsy_none`): a binding
        # cannot be excluded by a guard over a local this pass is still deciding
        # about, and the structural exclusions are the ones that matter here.
        if _off_refusal_path(guards, falsy_none):
            continue
        value = getattr(stmt, "value", None)
        is_falsy = (
            isinstance(stmt, ast.Assign)
            and isinstance(value, ast.Constant)
            and not value.value
        )
        for name in names:
            reached[name] = reached.get(name, True) and is_falsy
    return lambda name: reached.get(name, False)


def _callee_is_free(
    call: ast.Call,
    func: ast.FunctionDef,
    falsy: Callable[[str], bool],
    charging: Collection[str],
) -> bool:
    """Does this call provably spend nothing, because the CALLEE guards it?

    The other spelling of the flag idiom, one frame down: the handler calls
    `self._charge(moved)` unconditionally and the callee decides. One hop only,
    positional and keyword arguments both, and only for a parameter the caller
    passes a provably-falsy local into — every other shape returns False and the
    call stays a charge.
    """
    params = [arg.arg for arg in func.args.args[1:]]
    bound: dict[str, bool] = {}
    for position, argument in enumerate(call.args):
        if position < len(params) and isinstance(argument, ast.Name) and falsy(argument.id):
            bound[params[position]] = False
    for keyword in call.keywords:
        if (
            keyword.arg in params
            and isinstance(keyword.value, ast.Name)
            and falsy(keyword.value.id)
        ):
            bound[keyword.arg] = False
    if not bound:
        return False

    statements: list = []
    _flatten(func.body, [], statements)
    sites = [
        (stmt, guards)
        for stmt, guards in statements
        if not isinstance(stmt, _COMPOUND) and _spends(stmt, charging)
    ]
    if not sites:
        return False
    return all(
        _off_refusal_path(guards, bound.__contains__) for _stmt, guards in sites
    )


def _spends(stmt: ast.AST, charging: Collection[str]) -> bool:
    """Does this leaf statement move budget — directly or through a method?"""
    attr = _assigned_self_attr(stmt)
    if attr is not None and _is_budget_name(attr):
        return True
    return any(
        callee in charging and not _is_refusal_name(callee)
        for callee in _self_call_names(stmt)
    )


def _charging_methods(methods: Mapping[str, ast.FunctionDef]) -> set[str]:
    """Methods that spend budget, directly or through another method.

    A fixpoint because the corpus charges through hops: convoy's handler calls
    `_roll_one_cell`, which calls `_burn_one_drum`, which is where the drum —
    the game's whole budget — actually comes off.
    """
    charging = {name for name in methods if _is_budget_name(name)}
    for name, func in methods.items():
        for node in ast.walk(func):
            if not isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                continue
            attr = _assigned_self_attr(node)
            if attr is not None and _is_budget_name(attr):
                charging.add(name)
                break
    changed = True
    while changed:
        changed = False
        for name, func in methods.items():
            if name in charging:
                continue
            if any(callee in charging for callee in _self_call_names(func)):
                charging.add(name)
                changed = True
    return charging


def _action_methods(methods: Mapping[str, ast.FunctionDef]) -> set[str]:
    """`step` and everything it reaches through `self.<method>()` calls.

    §6's rule is about what an ACTION does, so the refusal path is looked for
    here and nowhere else. Without this walk a level initializer that clears a
    refusal flag and assigns the level's budget reads as a charged refusal.
    """
    reachable = {_STEP_METHOD} & set(methods)
    frontier = deque(reachable)
    while frontier:
        for callee in _self_call_names(methods[frontier.popleft()]):
            if callee in methods and callee not in reachable:
                reachable.add(callee)
                frontier.append(callee)
    return reachable


def _refusal_signals(
    source: _Source, methods: Mapping[str, ast.FunctionDef]
) -> list[Evidence]:
    """Every place the source DRAWS a refusal — the `signal freely` half."""
    found: list[Evidence] = []
    for name, value in sorted(_refusal_palette_constants(source.int_consts).items()):
        found.append(
            Evidence(
                kind="code",
                path=source.rel,
                note=f"palette constant {name}={value} is named for a refusal",
            )
        )
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        named_sprite = (isinstance(func, ast.Name) and func.id == "Sprite") or (
            isinstance(func, ast.Attribute) and func.attr == "Sprite"
        )
        if not named_sprite:
            continue
        for keyword in node.keywords:
            if keyword.arg in ("name", "tags") and _mentions_refusal(keyword.value):
                found.append(
                    Evidence(
                        kind="code",
                        path=source.rel,
                        line=node.lineno,
                        note=f"a Sprite is constructed with a refusal {keyword.arg}",
                    )
                )
    for name, func in sorted(methods.items()):
        statements: list = []
        _flatten(func.body, [], statements)
        for stmt, guards in statements:
            if not _is_paint(stmt, source.int_consts):
                continue
            subject = _paint_subject_name(stmt)
            attributed = (
                _is_refusal_name(name)
                or any(_mentions_refusal(node.test) for node, _sib, _else in guards)
                or (subject is not None and _is_refusal_name(subject))
                or _mentions_refusal(stmt)
            )
            if attributed:
                found.append(
                    Evidence(
                        kind="code",
                        path=source.rel,
                        line=stmt.lineno,
                        note=f"{name}() paints a refusal-attributed object",
                    )
                )
    return found


def refusal_palette_indices(worker_dir: Path) -> tuple[int, ...]:
    """The palette indices this source names for a refusal — `C_REFUSE = 6`.

    The one falsifiable thing a refusal signal leaves in the source: the colour
    it is drawn in, named for what it is. `gate.refusal-persistence` reads it to
    ask a question the AST alone cannot — does that colour reach a SETTLED
    frame? — and a source that names no refusal colour returns `()`, which that
    check reports as not-measurable rather than as clean.

    Best-effort about its worker: a directory this cannot parse has no indices
    to give, and the caller puts that on the record rather than raising.
    """
    try:
        source = _parse_game(Path(worker_dir))
    except (OSError, ValueError, AssertionError, NotADirectoryError):
        return ()
    return tuple(sorted(_refusal_palette_constants(source.int_consts).values()))


def check_refusal_honest(
    worker_dir: Path, *, mode: str = DEFAULT_REFUSAL_HONEST_MODE
) -> CheckResult | None:
    """§6:158's never-both rule, as the one `CheckResult` a checks list wants."""
    found = refusal_honest_report(worker_dir, mode=mode)
    return None if found is None else found.result


def refusal_honest_report(
    worker_dir: Path, *, mode: str = DEFAULT_REFUSAL_HONEST_MODE
) -> RefusalHonestReport | None:
    """`check_refusal_honest`'s verdict plus the charge sites behind it.

    `off` returns None and reads nothing at all. `record` (the default) reports
    every finding and returns a `deferred` result, which `decide_verdict` never
    rejects on. `fail` returns the same findings as a failing `static` check,
    which does.
    """
    if mode not in REFUSAL_HONEST_MODES:
        raise ValueError(
            f"refusal-honest mode must be one of {list(REFUSAL_HONEST_MODES)}, got {mode!r}"
        )
    if mode == "off":
        return None

    worker_dir = Path(worker_dir)
    generated, layout = _generated_source(worker_dir)
    evidence = [Evidence(kind="code", path="game.py", note=layout)]
    if not generated:
        return RefusalHonestReport(
            (),
            _result(
                REFUSAL_HONEST_CHECK,
                "static",
                "premise-not-met",
                evidence,
                "This source is not a generated worker. §6's never-signal-and-charge rule "
                "is a contract on what the GENERATOR ships; the 25 signed officials are the "
                "population the rule was MEASURED on (17/25 charge silently, 2/25 signal "
                "and are free) and this check never judges them.",
            ),
        )

    source = _parse_game(worker_dir)
    methods: dict[str, ast.FunctionDef] = {}
    for cls in source.game_classes:
        methods.update(_methods(cls))
    action_methods = _action_methods(methods)
    charging = _charging_methods(methods)
    signals = _refusal_signals(source, methods)

    charges: list[str] = []
    marker_methods: list[str] = []
    for name in sorted(action_methods):
        statements: list = []
        _flatten(methods[name].body, [], statements)
        if not any(_refusal_binding(stmt) for stmt, _guards in statements):
            continue
        marker_methods.append(name)
        falsy = _falsy_locals(statements)
        for stmt, guards in statements:
            if isinstance(stmt, _COMPOUND):
                # A compound statement's children are visited on their own
                # guard chains; reading one whole would count both limbs.
                continue
            if _refusal_binding(stmt) or _is_paint(stmt, source.int_consts):
                continue
            if _off_refusal_path(guards, falsy):
                continue
            attr = _assigned_self_attr(stmt)
            if attr is not None and _is_budget_name(attr):
                charges.append(
                    f"{source.rel}:{stmt.lineno}: {name}() spends `self.{attr}` on a path a "
                    f"refused action reaches"
                )
                continue
            for call in (
                node
                for node in ast.walk(stmt)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
            ):
                callee = call.func.attr
                if callee not in charging or _is_refusal_name(callee):
                    continue
                target = methods.get(callee)
                if target is not None and _callee_is_free(call, target, falsy, charging):
                    continue
                charges.append(
                    f"{source.rel}:{stmt.lineno}: {name}() calls `self.{callee}()`, which "
                    f"spends budget, on a path a refused action reaches"
                )
                break

    evidence.append(
        Evidence(
            kind="code",
            path=source.rel,
            note=f"{len(action_methods)} method(s) reachable from {_STEP_METHOD}(); "
            f"refusal-binding handler(s) {marker_methods or 'none'}; "
            f"{len(signals)} refusal signal site(s); "
            f"budget-spending method(s) {sorted(charging) or 'none'}",
        )
    )
    evidence.extend(signals[:4])

    if not marker_methods:
        return RefusalHonestReport(
            (),
            _result(
                REFUSAL_HONEST_CHECK,
                "static",
                "premise-not-met",
                evidence,
                "No method reachable from step() BINDS a refusal-named value, so this source "
                "does not ship the resolve-and-continue refusal idiom this check reads and "
                "there is no refusal path to measure a charge on. A game whose handler calls "
                "a refusal helper and returns immediately (conduit-watch: `self._refuse(...); "
                "return False`) lands here: its refusal may well be free, and this check "
                "declines to certify a verdict it did not earn. RECORDED, NOT PASSED.",
            ),
        )
    if not signals:
        return RefusalHonestReport(
            (),
            _result(
                REFUSAL_HONEST_CHECK,
                "static",
                "pass",
                evidence,
                f"{len(marker_methods)} refusal-binding handler(s) and NO refusal signal in "
                "the source: nothing is drawn, so §6's `charge silently` mode is the reading "
                "and the never-both rule is not in play. Whether the spec PROMISED a visible "
                "refusal is a different question, asked against the settled frames by "
                "`gate.refusal-persistence`.",
            ),
        )
    if not charges:
        return RefusalHonestReport(
            (),
            _result(
                REFUSAL_HONEST_CHECK,
                "static",
                "pass",
                evidence,
                f"The refusal is DRAWN ({len(signals)} signal site(s)) and FREE: no budget "
                f"mutation sits on a path a refused action reaches in "
                f"{marker_methods}. That is §6's `signal freely` mode, which is what both "
                "officials with a real visible refusal do (ls20, sc25).",
            ),
        )

    note = (
        f"§6:158 — officials either charge silently or signal freely, NEVER BOTH — and this "
        f"game does both. The refusal is drawn ({len(signals)} signal site(s), first at "
        f"{source.rel}:{signals[0].line or 0}) and it still spends budget in {len(charges)} "
        f"place(s): {'; '.join(charges)}. Make the refused action free, or stop drawing the "
        f"refusal. SCOPE: this reads the resolve-and-continue idiom only — a refusal-named "
        f"binding in a method reachable from step(), a budget mutation that branch does not "
        f"skip, and a refusal the source draws — so a clean answer here is not a proof of "
        f"§6 conformance for a game built any other way."
    )
    if mode == "fail":
        return RefusalHonestReport(
            tuple(charges),
            _result(REFUSAL_HONEST_CHECK, "static", "fail", evidence, note),
        )
    return RefusalHonestReport(
        tuple(charges),
        _result(
            REFUSAL_HONEST_CHECK,
            "static",
            "deferred",
            evidence,
            f"RECORDED, NOT FAILED (`verifier.refusal_honest: record`). {note}",
        ),
    )


# --- static pass 3: unread -2 ----------------------------------------------

_MASK_READER_CALLS = frozenset(
    {
        "collides_with",
        "try_move",
        "try_move_sprite",
        "get_sprite_at",
        "get_pixels",
        "get_pixels_at_sprite",
        "render",
        "collide",
    }
)
_MASK_READER_NAMES = frozenset(
    {"BlockingMode", "PIXEL_PERFECT", "BOUNDING_BOX", "NOT_BLOCKED", "InteractionMode"}
)


def _explicit_minus_two_tests(source: _Source) -> list[int]:
    """Lines where the code compares something against `-2` itself."""
    consts = source.int_consts
    lines = []
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Compare):
            values = [node.left] + list(node.comparators)
            if any(_int_const(v, consts) == -2 for v in values):
                lines.append(node.lineno)
        elif isinstance(node, ast.Subscript):
            index = _int_const(node.slice, consts)
            if index == -2:
                lines.append(node.lineno)
    return sorted(set(lines))


def _tag_scan_sites(source: _Source) -> list[int]:
    """Lines where the code reads sprite TAGS (`get_sprites_by_tag`, `in .tags`)."""
    lines = []
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            tag_call = "by_tag" in node.func.attr or node.func.attr == "get_all_tags"
            tagged_lookup = node.func.attr == "get_sprite_at" and len(node.args) >= 3
            if tag_call or tagged_lookup:
                lines.append(node.lineno)
        elif isinstance(node, ast.Compare) and any(
            isinstance(op, (ast.In, ast.NotIn)) for op in node.ops
        ):
            for comparator in node.comparators:
                if any(
                    isinstance(sub, ast.Attribute) and sub.attr in ("tags", "_tags")
                    for sub in ast.walk(comparator)
                ):
                    lines.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr in ("tags", "_tags"):
            lines.append(node.lineno)
    return sorted(set(lines))


def _collision_sites(source: _Source) -> list[int]:
    """Lines where the code makes the engine consult a collision/pixel mask."""
    lines = []
    for node in ast.walk(source.tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MASK_READER_CALLS
        ):
            lines.append(node.lineno)
    return sorted(set(lines))


def _sprite_mask_mode(call: ast.Call) -> tuple[bool, str]:
    """`(collision_mask_is_live, why)` for one Sprite construction.

    Engine defaults (`sprites.py:99-102`): `blocking=PIXEL_PERFECT`,
    `collidable=True`, so a -2 pixel IS solid and the collision mask reads it
    (`collides_with` tests `!= -1`, `sprites.py:555-557`). Turning any of
    those off is the game DECLARING that no mask consumes those pixels — it
    is the opposite of a reader, which is why `collidable=False` alone can
    never satisfy REQUIRED 5.
    """
    collidable = _kwarg(call, "collidable")
    if isinstance(collidable, ast.Constant) and collidable.value is False:
        return False, "collidable=False (collision mask off for this sprite)"
    visible = _kwarg(call, "visible")
    interaction = _kwarg(call, "interaction")
    mode = getattr(interaction, "attr", None) if interaction is not None else None
    if mode in ("INTANGIBLE", "REMOVED"):
        return False, f"interaction={mode} (not collidable)"
    if isinstance(visible, ast.Constant) and visible.value is False and mode is None:
        pass  # invisible-but-solid is still a live collision mask
    blocking = _kwarg(call, "blocking")
    block_mode = getattr(blocking, "attr", None) if blocking is not None else None
    if block_mode == "NOT_BLOCKED":
        return False, "blocking=NOT_BLOCKED (collision mask off for this sprite)"
    if block_mode == "BOUNDING_BOX":
        return True, "blocking=BOUNDING_BOX (the declared mask; -2 inert by declaration)"
    return True, "engine default PIXEL_PERFECT + collidable (mask reads != -1)"


def _minus_two_carriers(source: _Source) -> list[tuple[ast.Call, list[int]]]:
    """Sprite constructions whose pixel data carries a `-2`, with its lines."""
    out = []
    for call in _sprite_calls(source.tree):
        pixels = _sprite_pixels(call, source)
        if pixels is None:
            continue
        lines = [
            lineno
            for literal in _nested_int_lists(pixels, source.int_consts)
            for lineno, value in _pixel_cells(literal, source.int_consts)
            if value == -2
        ]
        if lines:
            out.append((call, sorted(set(lines))))
    return out


def _minus_two_verdict(source: _Source) -> tuple[str, list[Evidence], str]:
    """REQUIRED 5, scoped to the SPRITE that ships each -2.

    "Every `-2` pixel ships with a DECLARED READER (which mask consumes it)"
    is a per-sprite contract, so a file-wide "somebody somewhere collides"
    is not an answer. A carrier is covered when one of these holds:

    1. the code tests `-2` explicitly anywhere (dc22 does, `dc22.py`);
    2. the sprite is tagged AND the game scans tags — canon's own reading of
       ka59 ("sets collidable=False on -2 interiors") and ls20/tn36 ("use
       BOUNDING_BOX or tag-scans so -2 is inert"): the tag scan IS the
       declared consumer;
    3. the sprite's collision mask is live (engine defaults or an explicit
       BOUNDING_BOX) and the game performs collision at all, so the engine's
       `!= -1` mask reads the -2.

    `collidable=False` with no tags and no explicit test is dead weight —
    nothing consumes those pixels at all.
    """
    sites = _minus_two_sites_in_sprites(source)
    if not sites:
        return (
            "premise-not-met",
            [Evidence(kind="code", path=source.rel, note="no -2 in any pixel-data literal")],
            "The game ships no -2 pixel, so REQUIRED 5 has no premise.",
        )

    explicit = _explicit_minus_two_tests(source)
    tag_scans = _tag_scan_sites(source)
    collisions = _collision_sites(source)
    carriers = _minus_two_carriers(source)

    covered: list[str] = []
    orphans: list[tuple[ast.Call, list[int]]] = []
    for call, lines in carriers:
        if explicit:
            covered.append("explicit -2 test")
            continue
        tags = _kwarg(call, "tags")
        tagged = isinstance(tags, (ast.List, ast.Tuple, ast.Set)) and bool(tags.elts)
        if tagged and tag_scans:
            covered.append("tag scan on a tagged carrier")
            continue
        live, why = _sprite_mask_mode(call)
        if live and collisions:
            covered.append(why)
            continue
        orphans.append((call, lines))

    if not carriers:
        # -2 outside any Sprite(...) call: the literal exists but no sprite
        # ships it, so REQUIRED 5's "every -2 PIXEL" has no carrier to bind.
        return (
            "premise-not-met",
            [
                Evidence(
                    kind="code",
                    path=source.rel,
                    line=sites[0],
                    note="-2 appears in pixel-shaped data that no Sprite(...) call takes",
                )
            ],
            "No sprite ships a -2 pixel, so no mask has to declare a reader for one.",
        )

    if orphans:
        evidence = []
        for call, lines in orphans:
            name = _str_const(_kwarg(call, "name") or ast.Constant(value=None))
            _live, why = _sprite_mask_mode(call)
            evidence.append(
                Evidence(
                    kind="code",
                    path=source.rel,
                    line=lines[0],
                    note=f"sprite {name!r} (constructed at {source.rel}:{call.lineno}) "
                    f"ships {len(lines)} -2 row(s); {why}; it carries no tag the game "
                    "scans and the file never tests -2",
                )
            )
        return (
            "fail",
            evidence,
            (
                f"{len(orphans)} of {len(carriers)} -2-carrying sprite(s) have no reader "
                "at all: no explicit -2 test in the file, no tag scan on a tagged "
                "carrier, and no live collision mask. FORBIDDEN (spec §2 / affordance "
                "§8): '-2 without a reader is FORBIDDEN' — 'a generated game states "
                "which mask reads every -2 it ships'."
            ),
        )

    return (
        "pass",
        [
            Evidence(
                kind="code",
                path=source.rel,
                line=carriers[0][1][0],
                note=f"{len(carriers)} -2-carrying sprite(s), each with a declared "
                f"reader: {sorted(set(covered))}",
            )
        ],
        (
            "Every -2-carrying sprite has a declared reader. Engine defaults "
            "(affordance §8): render masks read >=0, pixel-collision masks read != -1."
        ),
    )


def _check_minus_two(source: _Source) -> CheckResult:
    status, evidence, note = _minus_two_verdict(source)
    return _result("static.unread-minus2", "static", status, evidence, note)


# --- static pass 4: parsed field with no reader ----------------------------


def _defined_data_keys(source: _Source) -> dict[str, int]:
    """String keys the game DEFINES in level/config data literals."""
    keys: dict[str, int] = {}
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.Call):
            continue
        value = _kwarg(node, "data")
        if value is None:
            continue
        for sub in ast.walk(value):
            if not isinstance(sub, ast.Dict):
                continue
            for key in sub.keys:
                name = _str_const(key) if key is not None else None
                if name:
                    keys.setdefault(name, key.lineno)
    return keys


def _read_data_keys(source: _Source) -> set[str]:
    """String keys the game READS anywhere (subscripts, get/get_data, `in`)."""
    read: set[str] = set()
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Subscript):
            name = _str_const(node.slice)
            if name:
                read.add(name)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("get", "get_data", "pop", "setdefault") and node.args:
                name = _str_const(node.args[0])
                if name:
                    read.add(name)
        elif isinstance(node, ast.Compare):
            for op, comparator in zip(node.ops, node.comparators):
                if isinstance(op, (ast.In, ast.NotIn)):
                    name = _str_const(node.left)
                    if name:
                        read.add(name)
                    del comparator
    return read


def _check_parsed_fields(source: _Source) -> CheckResult:
    defined = _defined_data_keys(source)
    if not defined:
        return _result(
            "static.parsed-field-no-reader",
            "static",
            "premise-not-met",
            [Evidence(kind="code", path=source.rel, note="no data= dict literal in the file")],
            "The game defines no level/config data fields, so there is nothing that "
            "could go unread.",
        )
    read = _read_data_keys(source)
    orphans = sorted(k for k in defined if k not in read)
    if orphans:
        return _result(
            "static.parsed-field-no-reader",
            "static",
            "fail",
            [
                Evidence(
                    kind="code",
                    path=source.rel,
                    line=defined[key],
                    note=f"level/config field {key!r} is defined and never read",
                )
                for key in orphans
            ],
            f"{len(orphans)} parsed field(s) with no reader anywhere in the game: "
            f"{orphans}. Architecture §3 'parsed-field-has-reader'; same doctrine as "
            "REQUIRED 5 — data nothing consumes is dead weight.",
        )
    return _result(
        "static.parsed-field-no-reader",
        "static",
        "pass",
        [
            Evidence(
                kind="code",
                path=source.rel,
                line=min(defined.values()),
                note=f"{len(defined)} level/config field(s), every one read",
            )
        ],
        f"Every defined data field is read: {sorted(defined)}.",
    )


# --- static pass 5: palette / HUD collisions -------------------------------


@dataclass
class _PaintHit:
    line: int
    color: int
    scoped: bool
    where: str
    selective: bool = False


def _frame_params(func: ast.FunctionDef) -> set[str]:
    """Parameter names that hold the 64x64 frame inside an interface method."""
    names = {a.arg for a in func.args.args if a.arg != "self"}
    return {n for n in names if n == "frame" or "frame" in n}


def _color_gated_paints(
    cls: ast.ClassDef, consts: dict[str, int] | None = None
) -> list[_PaintHit]:
    """Colour-equality conditions that gate a write back into the frame.

    Canon's condition is palette equality that a real object can collide
    with, FULL STOP — neither the write's shape nor its coordinates enter
    into it. Both corpus shapes are therefore hits:

    * ARRAY-LEVEL: `mask = frame == k` then `frame[mask] = pattern[mask]`
      (m0r0.py:626 + 648), or `frame[frame == k] = c`.
    * SCALAR read-compare-write: `v = frame[y, x]` then
      `if v == 5 or v == 10: frame[y, x] = c` (r11l.py:1390-1392) — canon's
      own named exemplar.

    `scoped`/`selective` are recorded for the evidence note only; they do not
    gate the verdict. An earlier revision of this check required
    data-dependent coordinates and was corrected: it let the array-level
    shape through, which is the same FORBIDDEN condition.

    The one gate that DOES apply is canon's own: the keyed colour must appear
    in some real board sprite's pixels. A colour no object ever uses is the
    benign background-fill idiom and must not fail.
    """
    hits: list[_PaintHit] = []
    for func in _methods(cls).values():
        frames = _frame_params(func)
        if not frames:
            continue
        # locals that hold a value READ out of the frame
        frame_values: dict[str, tuple[int, bool]] = {}
        for node in ast.walk(func):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Subscript)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id in frames
            ):
                scoped = _subscript_is_constant(node.value.slice, consts)
                frame_values[node.targets[0].id] = (node.lineno, scoped)

        for node in ast.walk(func):
            if isinstance(node, ast.Compare) and len(node.ops) == 1:
                if not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
                    continue
                color = _int_const(node.comparators[0], consts)
                if color is None or not (COLOR_MIN <= color <= COLOR_MAX):
                    continue
                left = node.left
                if isinstance(left, ast.Name) and left.id in frames:
                    hits.append(
                        _PaintHit(
                            node.lineno, color, False, "frame == color (array mask)", False
                        )
                    )
                elif isinstance(left, ast.Name) and left.id in frame_values:
                    hits.append(
                        _PaintHit(
                            node.lineno,
                            color,
                            frame_values[left.id][1],
                            "value read from frame[...] == color",
                            True,
                        )
                    )
                elif (
                    isinstance(left, ast.Subscript)
                    and isinstance(left.value, ast.Name)
                    and left.value.id in frames
                ):
                    hits.append(
                        _PaintHit(
                            node.lineno,
                            color,
                            _subscript_is_constant(left.slice, consts),
                            "frame[...] == color",
                            True,
                        )
                    )
    return hits


def _assigned_names(target: ast.AST) -> list[str]:
    """Names an assignment target BINDS — never the names it merely reads.

    `frame[start_y + i, start_x] = v` binds nothing: `start_y` and `start_x`
    are reads inside the index. Walking the whole target treats them as
    rebinds and throws away the constants they hold.
    """
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for element in target.elts for name in _assigned_names(element)]
    if isinstance(target, ast.Starred):
        return _assigned_names(target.value)
    return []


def _frame_write_sites(
    func: ast.FunctionDef, base: dict[str, int], frames: set[str]
) -> list[tuple[int, bool]]:
    """`(lineno, pins_an_axis)` for every write into the frame, in source order.

    Reserved HUD geometry is routinely declared through a local and rebound
    per strip: dc22.py:9927 sets `start_y: int = 63` once, while ls20.py:1538
    walks its pip rows with `toxqhfsju = 55` … `toxqhfsju = 61`. Resolving a
    name against the NEAREST PRECEDING constant assignment (a small
    reaching-definitions pass in source order) sees both; a single whole-
    function binding sees neither. A name assigned anything non-constant, or
    bound by a `for` target, is dropped from the environment, so this never
    invents a pin.
    """
    env = dict(base)
    sites: list[tuple[int, bool]] = []

    def rebind(target: ast.AST, value: ast.AST | None) -> None:
        const = _int_const(value, env) if value is not None else None
        for name in _assigned_names(target):
            if const is None:
                env.pop(name, None)
            else:
                env[name] = const

    def visit(stmts) -> None:
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                for target in targets:
                    if (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id in frames
                    ):
                        sites.append((stmt.lineno, _pins_an_axis(target.slice, env)))
                value = None if isinstance(stmt, ast.AugAssign) else getattr(stmt, "value", None)
                for target in targets:
                    rebind(target, value)
                continue
            if isinstance(stmt, (ast.For, ast.AsyncFor)):
                rebind(stmt.target, None)
                visit(stmt.body)
                visit(stmt.orelse)
                continue
            for field_name in ("body", "orelse", "finalbody"):
                inner = getattr(stmt, field_name, None)
                if isinstance(inner, list):
                    visit([s for s in inner if isinstance(s, ast.stmt)])
            for handler in getattr(stmt, "handlers", []):
                visit(handler.body)
            for case in getattr(stmt, "cases", []):
                visit(case.body)

    visit(func.body)
    return sites


def _pins_an_axis(node: ast.AST, consts: dict[str, int] | None = None) -> bool:
    """True when a frame subscript pins at least one axis to a constant.

    REQUIRED 7's reserved geometry is a STRIP: `frame[63, x]` (row 63) and
    `frame[y, 0]` (column 0) both declare one, even though the other axis
    sweeps. A boolean mask or a pair of computed coordinates declares none.
    """
    parts = node.elts if isinstance(node, ast.Tuple) else [node]
    if len(parts) == 1 and not isinstance(parts[0], (ast.Slice, ast.Constant)):
        # `frame[mask]` / `frame[expr]`: nothing pinned unless it is a literal.
        return _int_const(parts[0], consts) is not None
    for part in parts:
        if isinstance(part, ast.Slice):
            bounds = (part.lower, part.upper)
            if all(b is None or _int_const(b, consts) is not None for b in bounds) and any(
                b is not None for b in bounds
            ):
                return True
            continue
        if _int_const(part, consts) is not None:
            return True
    return False


def _subscript_is_constant(node: ast.AST, consts: dict[str, int] | None = None) -> bool:
    """True when every index in a subscript is an int constant or a full slice.

    A constant subscript is DECLARED geometry (REQUIRED 7); a data-dependent
    one can land anywhere on the board.
    """
    parts = node.elts if isinstance(node, ast.Tuple) else [node]
    for part in parts:
        if isinstance(part, ast.Slice):
            for bound in (part.lower, part.upper, part.step):
                if bound is not None and _int_const(bound, consts) is None:
                    return False
            continue
        if _int_const(part, consts) is None:
            return False
    return True


def _check_palette_hud(source: _Source, cap: FrameCapture) -> CheckResult:
    if not source.display_classes:
        return _result(
            "static.palette-hud-collision",
            "static",
            "premise-not-met",
            [
                Evidence(
                    kind="code",
                    path=source.rel,
                    note="no RenderableUserDisplay subclass; nothing paints after the board",
                )
            ],
            "The game ships no interface, so interface paint cannot collide with the "
            "board (affordance §8: 'Interfaces paint AFTER the board').",
        )

    board_colors = _sprite_pixel_colors(source)
    hits = [
        h
        for cls in source.display_classes
        for h in _color_gated_paints(cls, source.int_consts)
    ]
    unscoped = [h for h in hits if h.color in board_colors]
    if unscoped:
        evidence = [
            Evidence(
                kind="code",
                path=source.rel,
                line=hit.line,
                note=f"interface paint gated on {hit.where} (color {hit.color}); a "
                f"board sprite carries that colour at {source.rel}:"
                f"{board_colors[hit.color]}",
            )
            for hit in unscoped
        ]
        label = cap.records[0].label if cap.records else None
        evidence.append(
            Evidence(
                kind="frame",
                frame_label=label,
                note="the settled frame is what a trajectory consumer reads; an "
                "interface that overwrites a board colour makes it under-report state",
            )
        )
        colors = sorted({hit.color for hit in unscoped})
        return _result(
            "static.palette-hud-collision",
            "static",
            "fail",
            evidence,
            "FORBIDDEN (affordance §8): 'interface paint conditions keyed to palette "
            f"equality that a real object can collide with'. Colour(s) {colors} gate "
            "an interface write at data-dependent coordinates and are carried by "
            "board sprites. Canon's own exemplar is r11l's line painter "
            "(r11l.py:1390-1392), which writes wherever frame==5 or frame==10.",
        )

    note = "No interface paint is keyed to a colour any board sprite carries."
    if hits:
        note += (
            f" {len(hits)} colour-gated write(s) were cleared: every keyed colour "
            f"({sorted({h.color for h in hits})}) is off-board — no sprite's pixel "
            "data contains it, so no real object can collide with the condition."
        )
    return _result(
        "static.palette-hud-collision",
        "static",
        "pass",
        [
            Evidence(
                kind="code",
                path=source.rel,
                line=cls.lineno,
                note=f"interface {cls.name}: paint keys on geometry",
            )
            for cls in source.display_classes
        ],
        note,
    )


# --- the five static passes ------------------------------------------------


def run_static_checks(worker_dir: Path, cap: FrameCapture) -> list[CheckResult]:
    """The five architecture §3 static passes over one worker/official dir."""
    source = _parse_game(worker_dir)
    return [
        _check_complete_action(source),
        _check_sys_click(source, cap, Path(worker_dir)),
        _check_minus_two(source),
        _check_parsed_fields(source),
        _check_palette_hud(source, cap),
    ]


# --- the eight REQUIRED rows -----------------------------------------------


def _calls_named(source: _Source, names: tuple[str, ...]) -> list[tuple[int, str]]:
    out = []
    for cls in source.game_classes:
        for node in ast.walk(cls):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in names
            ):
                out.append((node.lineno, node.func.attr))
    return sorted(set(out))


def _edge_band_changes(cap: FrameCapture) -> list[str]:
    """Frame labels whose row 0/63 or col 0/63 differs from the RESET frame."""
    if len(cap.records) < 2:
        return []
    base = cap.records[0].grid
    changed = []
    for record in cap.records[1:]:
        grid = record.grid
        if (
            grid[0] != base[0]
            or grid[-1] != base[-1]
            or [r[0] for r in grid] != [r[0] for r in base]
            or [r[-1] for r in grid] != [r[-1] for r in base]
        ):
            changed.append(record.label)
    return changed


def _row1(source: _Source, cap: FrameCapture, worker_dir: Path) -> CheckResult:
    return _result(
        "required.row1",
        "required",
        "deferred",
        [
            Evidence(
                kind="frame",
                frame_label=cap.records[0].label if cap.records else None,
                note=f"{len(cap.records)} settled frame(s) captured from "
                f"{len(cap.available_action_ids)} declared action(s) — the material the "
                "agent leg re-derives the locus from",
            )
        ],
        "REQUIRED 1 ('the locus of control is identifiable within a few actions') is "
        "the blind agent pass's job per the B7 contract: identifiability is a "
        "judgement about what a fresh reader can infer from the frames, not a static "
        "property of the source.",
    )


def _row2(source: _Source, cap: FrameCapture, worker_dir: Path) -> CheckResult:
    base = _check_sys_click(source, cap, worker_dir)
    return _result("required.row2", "required", base.status, base.evidence, base.note)


def _row3(source: _Source, cap: FrameCapture, worker_dir: Path) -> CheckResult:
    lose_sites = _calls_named(source, ("lose",))
    win_sites = _calls_named(source, ("win", "next_level"))
    edge_changes = _edge_band_changes(cap)
    has_display = bool(source.display_classes)

    if not lose_sites:
        return _result(
            "required.row3",
            "required",
            "premise-not-met",
            [Evidence(kind="code", path=source.rel, note="no lose() call in any game class")],
            "No budget mechanic is wired (nothing calls lose()), so the budget triple "
            "has no premise. affordance §5 makes the meter REQUIRED for generated "
            "games; a game with no exhaustion path is out of that row's scope and the "
            "S1 linter is where the absence is a spec defect.",
        )

    evidence = [
        Evidence(
            kind="code",
            path=source.rel,
            line=lose_sites[0][0],
            note=f"exhaustion wired: lose() at {len(lose_sites)} site(s)",
        )
    ]
    if win_sites:
        evidence.append(
            Evidence(
                kind="code",
                path=source.rel,
                line=win_sites[0][0],
                note=f"win predicate: {len(win_sites)} next_level()/win() site(s)",
            )
        )
    meter_seen = bool(edge_changes) or has_display
    if edge_changes:
        evidence.append(
            Evidence(
                kind="frame",
                frame_label=edge_changes[0],
                note=f"edge band (row 0/63, col 0/63) changes in {len(edge_changes)} "
                "captured frame(s) — an edge-anchored meter drains",
            )
        )
    elif has_display:
        evidence.append(
            Evidence(
                kind="code",
                path=source.rel,
                line=source.display_classes[0].lineno,
                note=f"interface {source.display_classes[0].name} paints after the board",
            )
        )

    note = (
        "Parts (a) meter and (b) exhaustion→lose() are checkable here and hold"
        if meter_seen
        else "Part (b) exhaustion→lose() holds; part (a) could not be OBSERVED — no "
        "edge band changed across the capture and the game ships no interface"
    )
    return _result(
        "required.row3",
        "required",
        "deferred",
        evidence,
        note
        + ". Part (c), 'the cap accommodates the solver's line + the g-margin', is an "
        "S4 fact (architecture S4 step 4, cap-fit check) and cannot be decided before "
        "baselines exist, so the row is deferred rather than passed. affordance §5 "
        "names the defect class this row excludes: tn36 ships baseline 72 > its own "
        "cap 61.",
    )


def _row4(source: _Source, cap: FrameCapture, worker_dir: Path) -> CheckResult:
    win_sites = _calls_named(source, ("win", "next_level"))
    if not win_sites:
        return _result(
            "required.row4",
            "required",
            "fail",
            [
                Evidence(
                    kind="code",
                    path=source.rel,
                    note="no next_level() or win() call in any game class",
                )
            ],
            "REQUIRED 4: 'the goal state is game-checkable (win predicate; solver "
            "reaches it)'. Nothing in this game credits a level or wins, so there is "
            "no win predicate at all.",
        )
    evidence = [
        Evidence(
            kind="code",
            path=source.rel,
            line=win_sites[0][0],
            note=f"win predicate wired: {len(win_sites)} next_level()/win() site(s)",
        ),
        Evidence(
            kind="frame",
            frame_label=cap.records[-1].label if cap.records else None,
            note=f"capture source={cap.source}, levels_completed={cap.levels_completed}, "
            f"win={cap.win}",
        ),
    ]
    if cap.source == "solver" and cap.win:
        return _result(
            "required.row4",
            "required",
            "pass",
            evidence,
            "The win predicate exists and the solver line reaches it: the capture ends "
            f"in WIN after {len(cap.solver_actions)} action(s).",
        )
    if cap.source == "solver":
        return _result(
            "required.row4",
            "required",
            "fail",
            evidence,
            "A win predicate exists but the solver line does not reach it "
            f"(levels_completed={cap.levels_completed}, win={cap.win}). REQUIRED 4 "
            "binds the two halves together (D11: solver reaches the goal).",
        )
    return _result(
        "required.row4",
        "required",
        "deferred",
        evidence,
        "The win predicate exists. The second half ('solver reaches it') cannot be "
        "shown from a PROBE capture — one action per fresh instance never plays a "
        "line. Re-run with the worker's solver to decide it.",
    )


def _row5(source: _Source, cap: FrameCapture, worker_dir: Path) -> CheckResult:
    status, evidence, note = _minus_two_verdict(source)
    del cap
    return _result("required.row5", "required", status, evidence, note)


def _row6(source: _Source, cap: FrameCapture, worker_dir: Path) -> CheckResult:
    sprites = _sprite_calls(source.tree)
    layered = [
        keyword.value.lineno
        for call in sprites
        for keyword in call.keywords
        if keyword.arg == "layer"
    ]
    set_layer = _calls_named(source, ("set_layer",))
    set_layer += [
        (node.lineno, "set_layer")
        for node in ast.walk(source.tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set_layer"
    ]
    if len(sprites) < 2:
        return _result(
            "required.row6",
            "required",
            "premise-not-met",
            [
                Evidence(
                    kind="code",
                    path=source.rel,
                    note=f"{len(sprites)} Sprite construction(s) in the file — no overlap "
                    "to order",
                )
            ],
            "REQUIRED 6 governs 'every overlap that matters'; with fewer than two "
            "sprites there is no overlap.",
        )
    if layered or set_layer:
        line = min(layered) if layered else set_layer[0][0]
        return _result(
            "required.row6",
            "required",
            "pass",
            [
                Evidence(
                    kind="code",
                    path=source.rel,
                    line=line,
                    note=f"explicit z: {len(layered)} layer= kwarg(s), "
                    f"{len(set(set_layer))} set_layer() call(s)",
                )
            ],
            "Explicit layer values are declared; z-order does not fall back to "
            "declaration order (REQUIRED 6; affordance §8 records three officials that "
            "drop the stock layer sort, one of them shipping an invisible mechanic).",
        )
    if source.display_classes:
        return _result(
            "required.row6",
            "required",
            "premise-not-met",
            [
                Evidence(
                    kind="code",
                    path=source.rel,
                    line=source.display_classes[0].lineno,
                    note=f"board painted through {source.display_classes[0].name}, a "
                    "RenderableUserDisplay, not through sprite z-order",
                )
            ],
            "No layer= anywhere, but the board is painted by an interface — the "
            "structural exception affordance §8 records for bp35/lf52/m0r0, where "
            "sprite layering is not the render mechanism. D8 adjudication 6.",
        )
    return _result(
        "required.row6",
        "required",
        "premise-not-met",
        [
            Evidence(
                kind="code",
                path=source.rel,
                line=sprites[0].lineno,
                note=f"{len(sprites)} sprite(s), no layer= and no set_layer(); no "
                "interface either",
            )
        ],
        "No explicit layers are declared. Whether any overlap MATTERS is not decidable "
        "from the source alone (a one-sprite-per-cell board never overlaps), so the "
        "row's premise is unproven rather than violated. D8 adjudication 6 — lp85 and "
        "sp80 sit here.",
    )


def _row7(source: _Source, cap: FrameCapture, worker_dir: Path) -> CheckResult:
    if not source.display_classes:
        return _result(
            "required.row7",
            "required",
            "premise-not-met",
            [
                Evidence(
                    kind="code",
                    path=source.rel,
                    note="no RenderableUserDisplay subclass — nothing paints after the board",
                )
            ],
            "REQUIRED 7 governs reserved HUD geometry; with no interface there is no "
            "reserved strip to declare.",
        )
    # REQUIRED 7 is about DECLARED geometry, which is a different contract from
    # FORBIDDEN #1 (palette-keyed paint). They are judged separately so one
    # interface defect cannot produce two fails for the same line.
    constant, variable = [], []
    for cls in source.display_classes:
        for func in _methods(cls).values():
            frames = _frame_params(func)
            if not frames:
                continue
            for lineno, pinned in _frame_write_sites(func, source.int_consts, frames):
                (constant if pinned else variable).append(lineno)
    evidence = [
        Evidence(
            kind="code",
            path=source.rel,
            line=cls.lineno,
            note=f"interface {cls.name}",
        )
        for cls in source.display_classes
    ]
    if constant:
        evidence.append(
            Evidence(
                kind="code",
                path=source.rel,
                line=min(constant),
                note=f"{len(constant)} frame write(s) at constant geometry",
            )
        )
    if variable and not constant:
        evidence.append(
            Evidence(
                kind="code",
                path=source.rel,
                line=min(variable),
                note=f"all {len(variable)} frame write(s) land at computed row AND "
                "column — no axis is pinned to a constant",
            )
        )
        return _result(
            "required.row7",
            "required",
            "fail",
            evidence,
            "REQUIRED 7: 'Reserved HUD geometry declared (row 63 / row 0 / col 0 / "
            "custom)'. Every write this interface makes chooses both its row and its "
            "column at runtime, so no strip is reserved anywhere in the source and the "
            "interface can land on any board cell. affordance §8: 'Interfaces paint "
            "AFTER the board ... and WILL overwrite it'.",
        )
    if variable:
        evidence.append(
            Evidence(
                kind="code",
                path=source.rel,
                line=min(variable),
                note=f"{len(variable)} frame write(s) at computed coordinates",
            )
        )
        return _result(
            "required.row7",
            "required",
            "deferred",
            evidence,
            "Some writes pin a row or column (the reserved strip IS declared) and "
            "others choose both coordinates at runtime, so what the rest of the "
            "interface reserves is a runtime fact this leg cannot pin down. Neither a "
            "violation nor a pass. A meter whose strip is fixed and whose EXTENT "
            "varies with the budget is the edge-anchored idiom REQUIRED 7 permits "
            "('row 63 / row 0 / col 0 / custom'; affordance §5's placement histogram "
            "includes ls20's rows 61-62 pips), and a full-board overlay keyed on "
            "distance to the avatar is a vision mechanic, not HUD geometry — this "
            "leg cannot tell those apart from an undeclared strip, so it defers.",
        )
    return _result(
        "required.row7",
        "required",
        "pass",
        evidence,
        "Every interface write lands at constant geometry — the reserved strip is "
        "declared in the source (REQUIRED 7: 'row 63 / row 0 / col 0 / custom').",
    )


def _row8(source: _Source, cap: FrameCapture, worker_dir: Path) -> CheckResult:
    board_colors = _sprite_pixel_colors(source)
    frame_colors: set[int] = set()
    for record in cap.records:
        for row in record.grid:
            frame_colors.update(row)
    selection_on_board = SELECTION_COLOR in board_colors
    evidence = [
        Evidence(
            kind="code",
            path=source.rel,
            line=board_colors.get(SELECTION_COLOR),
            note=f"sprite pixel-data colours: {sorted(board_colors)}",
        ),
        Evidence(
            kind="frame",
            frame_label=cap.records[0].label if cap.records else None,
            note=f"rendered colours across the capture: {sorted(frame_colors)}",
        ),
    ]
    if not selection_on_board:
        return _result(
            "required.row8",
            "required",
            "pass",
            evidence,
            "White-0 is not painted into any board sprite, so the ecosystem's "
            "selection/highlight index stays reserved (affordance §9; REQUIRED 8).",
        )
    return _result(
        "required.row8",
        "required",
        "deferred",
        evidence,
        "Colour 0 (white — affordance §9's selection/highlight marker, 'Semantic; "
        "avoid as plain paint') appears in board sprite data. REQUIRED 8 makes "
        "overloading legal when it is a DECLARED deception lever (affordance §7.2), "
        "and the declaration lives in spec.yaml, which this leg never sees "
        "(architecture §3 blindness ⊕). The diff step decides it; the evidence is "
        "recorded here.",
    )


_ROW_CHECKS = (_row1, _row2, _row3, _row4, _row5, _row6, _row7, _row8)


def run_required_rows(worker_dir: Path, cap: FrameCapture) -> list[CheckResult]:
    """Exactly eight results, `required.row1`..`required.row8`, in spec §2 order."""
    source = _parse_game(worker_dir)
    results = [check(source, cap, Path(worker_dir)) for check in _ROW_CHECKS]
    expected = [f"required.row{i}" for i in range(1, 9)]
    if [r.check_id for r in results] != expected:
        raise AssertionError(f"REQUIRED rows out of contract order: {[r.check_id for r in results]}")
    return results


# --- solver quality ---------------------------------------------------------


def _identifier_words(name: str) -> set[str]:
    """`pending_confirm` / `pendingConfirm` -> {'pending', 'confirm'}."""
    spaced = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    return {word for word in spaced.lower().split("_") if word}


def _lag_confirm_sites(path: Path) -> list[tuple[int, str]]:
    """Identifiers and data strings carrying a lag/confirm idiom, with lines.

    An AST scan on purpose: a raw substring sweep matches `flag` for `lag` and
    reads a docstring that merely SAYS "flush" as an implementation — which
    is how a solver blind to a confirm step passed this check in testing.
    Docstrings are excluded; identifiers are split on `_`/camelCase so only
    whole words count.
    """
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        raise ValueError(f"{path}:{exc.lineno or 0}: does not parse: {exc.msg}") from exc

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))

    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        words: set[str] = set()
        if isinstance(node, ast.Name):
            words = _identifier_words(node.id)
        elif isinstance(node, ast.Attribute):
            words = _identifier_words(node.attr)
        elif isinstance(node, ast.arg):
            words = _identifier_words(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            words = _identifier_words(node.name)
        elif isinstance(node, ast.keyword) and node.arg:
            words = _identifier_words(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            words = _identifier_words(node.value)
        matched = words & set(LAG_CONFIRM_TOKENS)
        if matched:
            hits.append((getattr(node, "lineno", 0), min(matched)))
    return sorted(set(hits))


def _drive_solver(game_cls, solver_cls, *, max_actions: int = 600):
    """Replay the solver line, keeping EVERY settled frame.

    `FrameCapture` deliberately keeps only RESET / transitions / final, which
    is right for the agent prompt and useless for no-op detection, so this leg
    drives the game again and holds the full per-action trace.
    """
    game = _fresh_game(game_cls)
    solver = solver_cls()
    reset_fn = getattr(solver, "reset", None)
    if callable(reset_fn):
        reset_fn()
    fd = _reset(game)
    trace = [("reset", settled_grid(fd), int(fd.levels_completed), fd.state.name)]
    actions: list[str] = []
    for _ in range(max_actions):
        if fd.state in (GameState.WIN, GameState.GAME_OVER):
            break
        action = solver.next_action(fd)
        if action is None:
            break
        described = describe_action(action)
        fd = _perform(game, action)
        actions.append(described)
        trace.append((described, settled_grid(fd), int(fd.levels_completed), fd.state.name))
    return actions, trace


def _noop_prefix(trace) -> int:
    """How many leading actions left the settled frame and counters untouched."""
    count = 0
    for index in range(1, len(trace)):
        _, grid, completed, state = trace[index]
        _, prev_grid, prev_completed, prev_state = trace[index - 1]
        if grid == prev_grid and completed == prev_completed and state == prev_state:
            count += 1
            continue
        break
    return count


def _playable_cells(game_cls) -> int:
    """Cells of the opening level — `grid_size` when set, else the camera."""
    game = _fresh_game(game_cls)
    _reset(game)
    size = game.current_level.grid_size
    if size:
        return int(size[0]) * int(size[1])
    return int(game.camera._width) * int(game.camera._height)


def _bfs_optimal_to_first_level(game_cls, action_ids, *, max_nodes, max_depth):
    """Shortest action line that credits a level, or None within budget.

    BFS over ACTION LINES replayed from a fresh instance (the contract's
    "clone/re-instantiate per node line"); the visited set is keyed on the
    settled frame plus the engine counters, which is what collapses the
    search on a small board.
    """
    with quiet():
        start_game = _fresh_game(game_cls)
        start_fd = _reset(start_game)
    start_key = (settled_grid(start_fd), int(start_fd.levels_completed), start_fd.state.name)
    seen = {start_key}
    queue = deque([((), start_key)])
    expansions = 0
    while queue:
        line, _key = queue.popleft()
        if len(line) >= max_depth:
            continue
        for action_id in action_ids:
            if expansions >= max_nodes:
                return None
            expansions += 1
            game = _fresh_game(game_cls)
            fd = _reset(game)
            terminal = False
            for replay in line + (action_id,):
                fd = _perform(game, _simple_action(replay))
                if fd.state in (GameState.WIN, GameState.GAME_OVER):
                    terminal = True
                    break
            if not fd.frame:
                continue
            candidate = line + (action_id,)
            if int(fd.levels_completed) > 0 or fd.state is GameState.WIN:
                return len(candidate)
            if terminal:
                continue
            key = (settled_grid(fd), int(fd.levels_completed), fd.state.name)
            if key in seen:
                continue
            seen.add(key)
            queue.append((candidate, key))
    return None


def _simple_action(action_id: int):
    from arcengine import ActionInput

    if action_id == GameAction.ACTION6.value:
        return mouse(32, 32)
    return ActionInput(id=GameAction[f"ACTION{action_id}"])


def run_solver_quality(
    worker_dir: Path, cap: FrameCapture, *, bfs_cell_cap: int
) -> list[CheckResult]:
    """No-op prefix, BFS spot-check, lag/confirm modelling (leg "solver")."""
    worker_dir = Path(worker_dir)
    solver_path = solver_source_path(worker_dir)
    if solver_path is None:
        return [
            _result(check_id, "solver", "skipped", [], "no solver")
            for check_id in (
                "solver.noop-prefix",
                "solver.bfs-spot-check",
                "solver.lag-confirm-modeled",
            )
        ]

    source = _parse_game(worker_dir)
    # Worker code is untrusted, and this is the ONE place the pipeline runs it
    # in-process (capture is process-isolated; validate runs in the worker's
    # own pytest). b004 (2026-09-28) crashed the whole orchestrator TWICE here
    # — an IndexError and then a ValueError raised inside a game's own
    # solver.py mid-drive — killing the run instead of judging the game. A
    # solver that cannot be driven is a REJECT with a solver-only route (the
    # existing `solver`-leg fail plumbing), never an orchestrator crash.
    try:
        game_cls, solver_cls = load_worker_classes(worker_dir)
        actions, trace = _drive_solver(game_cls, solver_cls)
    except Exception as exc:  # noqa: BLE001 — any worker-code crash is a verdict
        frames = traceback.extract_tb(exc.__traceback__)
        ours = [f for f in frames if str(worker_dir) in (f.filename or "")]
        site = ours[-1] if ours else (frames[-1] if frames else None)
        where = f"{Path(site.filename).name}:{site.lineno}" if site else "unknown site"
        note = (
            f"driving the worker's own solver crashed: {type(exc).__name__}: "
            f"{exc} (at {where}) — a solver that cannot be driven cannot be judged"
        )
        crashed = [Evidence(kind="code", path="solver.py", note=note[:400])]
        return [
            _result("solver.noop-prefix", "solver", "fail", crashed, note),
            _result(
                "solver.bfs-spot-check", "solver", "premise-not-met", crashed,
                "the solver drive crashed before this check could run",
            ),
            _result(
                "solver.lag-confirm-modeled", "solver", "premise-not-met", crashed,
                "the solver drive crashed before this check could run",
            ),
        ]
    lag_game = _lag_confirm_sites(source.path)
    lag_solver = _lag_confirm_sites(solver_path)

    return [
        _noop_result(source, actions, trace, lag_game),
        _bfs_result(source, game_cls, cap, actions, trace, lag_game, bfs_cell_cap),
        _lag_result(source, solver_path, cap, lag_game, lag_solver),
    ]


def _noop_result(source: _Source, actions, trace, lag_game) -> CheckResult:
    prefix = _noop_prefix(trace)
    if not actions:
        return _result(
            "solver.noop-prefix",
            "solver",
            "premise-not-met",
            [Evidence(kind="code", path="solver.py", note="the solver emitted no actions")],
            "There is no line to inspect for padding.",
        )
    if prefix:
        evidence = [
            Evidence(
                kind="frame",
                frame_label=trace[index][0],
                note=f"action #{index} left the settled frame, levels_completed and "
                "state identical",
            )
            for index in range(1, prefix + 1)
        ]
        if lag_game:
            evidence.append(
                Evidence(
                    kind="code",
                    path=source.rel,
                    line=lag_game[0][0],
                    note=f"game implements a lag/confirm idiom ({lag_game[0][1]}) at "
                    f"{len(lag_game)} site(s)",
                )
            )
            return _result(
                "solver.noop-prefix",
                "solver",
                "deferred",
                evidence,
                f"The line opens with {prefix} frame-identical action(s), but the game "
                "implements action-lag/confirm, where an arming or staging action "
                "CORRECTLY changes no settled pixel. architecture S4 step 1 counts "
                "'lag flushes and confirm actions' as part of the line, so frame "
                "identity is not evidence of padding here. The pilot batch requires "
                "such games by quota (config batch.quotas: goal.confirm, "
                "state.action_lag), which is why this is deferred and not failed.",
            )
        return _result(
            "solver.noop-prefix",
            "solver",
            "fail",
            evidence,
            f"The line opens with {prefix} action(s) that change nothing observable, "
            f"out of {len(actions)}. difficulty-model §1: 'solver lines carry padding "
            "(a 21-no-op staging prefix shipped in one tufa baseline)' — and "
            "architecture S4 step 1 makes the line the unit every baseline is built "
            "from, so the padding multiplies straight into baseline_i = solver_i x g_i. "
            "Caveat kept honest: frame identity does not prove a no-op for a game with "
            "invisible load-bearing state (affordance §7.5), which is why this routes "
            "to S2 as a solver-only fix rather than a spec reject.",
        )
    return _result(
        "solver.noop-prefix",
        "solver",
        "pass",
        [
            Evidence(
                kind="frame",
                frame_label=trace[1][0] if len(trace) > 1 else None,
                note="the first action changes the settled frame or the counters",
            )
        ],
        f"No leading no-op: the line's {len(actions)} action(s) start working immediately.",
    )


def _bfs_result(source, game_cls, cap, actions, trace, lag_game, bfs_cell_cap) -> CheckResult:
    cells = _playable_cells(game_cls)
    if cells > bfs_cell_cap:
        return _result(
            "solver.bfs-spot-check",
            "solver",
            "skipped",
            [
                Evidence(
                    kind="engine",
                    note=f"opening level is {cells} playable cell(s), over the "
                    f"verifier.bfs_level_size_cap of {bfs_cell_cap}",
                )
            ],
            "Architecture §3 scopes this pass to 'BFS spot-check small levels'; this "
            "level is outside the configured cap.",
        )

    first_transition = None
    for index in range(1, len(trace)):
        if trace[index][2] > trace[index - 1][2]:
            first_transition = index
            break
    if first_transition is None:
        return _result(
            "solver.bfs-spot-check",
            "solver",
            "premise-not-met",
            [
                Evidence(
                    kind="frame",
                    frame_label=trace[-1][0],
                    note=f"the solver line never credits a level "
                    f"(levels_completed={trace[-1][2]})",
                )
            ],
            "With no level transition in the line there is nothing to compare an "
            "optimal bound against; REQUIRED 4 is where a non-winning solver is "
            "reported.",
        )

    action_ids = sorted(set(cap.available_action_ids) - {GameAction.RESET.value})
    depth_cap = min(BFS_MAX_DEPTH, max(4, first_transition))
    optimal = _bfs_optimal_to_first_level(
        game_cls, action_ids, max_nodes=BFS_MAX_NODES, max_depth=depth_cap
    )
    if optimal is None:
        return _result(
            "solver.bfs-spot-check",
            "solver",
            "deferred",
            [
                Evidence(
                    kind="engine",
                    note=f"BFS found no level-1 win within {BFS_MAX_NODES} expansions / "
                    f"depth {depth_cap} over actions {action_ids}",
                )
            ],
            "No optimal bound was established inside the search budget, so the line "
            "cannot be judged against one. Reported as deferred rather than passed: an "
            "unbounded search is not evidence of a tight solver.",
        )

    evidence = [
        Evidence(
            kind="engine",
            note=f"BFS over the real engine: level 1 is winnable in {optimal} action(s); "
            f"the solver spends {first_transition}",
        )
    ]
    if first_transition <= optimal * GROSS_SOLVER_RATIO:
        return _result(
            "solver.bfs-spot-check",
            "solver",
            "pass",
            evidence,
            f"The line is {first_transition / optimal:.2f}x the engine-optimal bound on "
            f"level 1, inside the {GROSS_SOLVER_RATIO}x bar (config g.median / "
            "difficulty-model §2.1: the measured human replay ratio median is 2.00, "
            "n=183, and baselines are solver x g on top of this line).",
        )
    if lag_game:
        evidence.append(
            Evidence(
                kind="code",
                path=source.rel,
                line=lag_game[0][0],
                note=f"game implements a lag/confirm idiom ({lag_game[0][1]}) at "
                f"{len(lag_game)} site(s)",
            )
        )
        return _result(
            "solver.bfs-spot-check",
            "solver",
            "deferred",
            evidence,
            f"The line is {first_transition / optimal:.2f}x the bound, above the "
            f"{GROSS_SOLVER_RATIO}x bar, but the game implements action-lag/confirm "
            "mechanics and architecture S4 step 1 counts 'lag flushes and confirm "
            "actions' as part of the line — a plain BFS over the raw action set does "
            "not model them, so the bound is not comparable here.",
        )
    return _result(
        "solver.bfs-spot-check",
        "solver",
        "fail",
        evidence,
        f"The solver spends {first_transition} action(s) on a level the engine clears "
        f"in {optimal} ({first_transition / optimal:.2f}x), with no lag/confirm "
        f"mechanic to justify the excess. Over the {GROSS_SOLVER_RATIO}x bar every "
        "baseline built from this line (baseline_i = solver_i x g_i, architecture S4) "
        "inherits the padding; difficulty-model §1 names this the 'not raw solver "
        "length' defect. Routes to S2 as a solver-only fix.",
    )


def _lag_result(source, solver_path, cap, lag_game, lag_solver) -> CheckResult:
    if not lag_game:
        return _result(
            "solver.lag-confirm-modeled",
            "solver",
            "premise-not-met",
            [
                Evidence(
                    kind="code",
                    path=source.rel,
                    note=f"no lag/confirm idiom in the game source (searched for "
                    f"{list(LAG_CONFIRM_TOKENS)})",
                )
            ],
            "The game implements neither action-lag nor a confirm step, so there is "
            "nothing for the solver to model.",
        )
    evidence = [
        Evidence(
            kind="code",
            path=source.rel,
            line=lag_game[0][0],
            note=f"game lag/confirm idiom {lag_game[0][1]!r} at {len(lag_game)} site(s)",
        )
    ]
    if lag_solver:
        evidence.append(
            Evidence(
                kind="code",
                path=solver_path.name,
                line=lag_solver[0][0],
                note=f"solver handles it: {lag_solver[0][1]!r} at {len(lag_solver)} site(s)",
            )
        )
        return _result(
            "solver.lag-confirm-modeled",
            "solver",
            "pass",
            evidence,
            "The solver's source carries the same lag/confirm idiom as the game, so "
            "the flushes and confirm actions are part of its line (architecture S4 "
            "step 1).",
        )
    if cap.win:
        evidence.append(
            Evidence(
                kind="frame",
                frame_label=cap.records[-1].label if cap.records else None,
                note="the captured line still wins the game",
            )
        )
        return _result(
            "solver.lag-confirm-modeled",
            "solver",
            "pass",
            evidence,
            "The solver's source names no lag/confirm idiom, but its line clears the "
            "game under the mechanic — the behaviour is accounted for even though the "
            "naming is not.",
        )
    return _result(
        "solver.lag-confirm-modeled",
        "solver",
        "fail",
        evidence,
        "The game implements a lag/confirm mechanic, the solver's source shows no sign "
        "of modelling it, and the line does not win. architecture S4 step 1: lag "
        "flushes and confirm actions 'are part of the line'; a solver that ignores "
        "them produces a line the baselines cannot be built from. Routes to S2 as a "
        "solver-only fix.",
    )
