"""Frame capture for the S2b intent verifier (B7, agent A).

The verifier's two evidence sources are the worker's SOURCE and the game's
own FRAMES. This module is the frame leg: it drives a game class through the
real engine and freezes what came back into a `FrameCapture` that is
JSON-round-trippable and byte-stable across runs, so the blind agent pass
(`gen/s3_verify.py`) and the static passes (`gen/s3_static.py`) argue over
the same artifact.

Canon behind the shape
----------------------
* `GEN/design/architecture.md` §3 "S2b — the intent verifier": the agent leg
  sees "ONLY the finished code" plus frames; the static and solver legs read
  the same capture. The digest is what the session is shown.
* `GEN/spec-v0.3.md` §2 Conventions: "settled frame = `fd.frame[-1]`" and "a
  mechanic that must be learnable from trajectories must survive into settled
  frames". Every `FrameRecord.grid` is therefore the SETTLED frame, never
  `frame[0]`.
* `GEN/design/objects/affordance-language.md` §8: "`get_sprites()` is a
  complete inventory in ~19/25 games; the exceptions are structural" — which
  is why the click facts here are read from the engine's own clickable-sprite
  path (`sys_click`/`sys_place` tags + `_is_sprite_clickable_now`) rather than
  re-derived from the frame.
* `GEN/spec-v0.3.md` §2 REQUIRED 2: "`sys_click` tags are truthful — always
  (the engine's click-action list and RL consumers read them)". `click_cells`
  is exactly that engine list, one representative coordinate per clickable
  sprite, so `gen/s3_static.py` can compare it against the code.

Engine facts this module is built on (verified against the installed
arcengine 0.9.3 source):

* `ARCBaseGame.__init__` defaults `available_actions=[1, 2, 3, 4, 5, 6]`
  (`base_game.py:54`) and exposes the list on every `FrameData`
  (`base_game.py:259`). Read it off the FRAME, never off the game object.
* `_get_valid_clickable_actions` (`base_game.py:522`) builds the click list
  from `get_sprites_by_tag("sys_click")` PLUS `get_sprites_by_tag("sys_place")`
  (`base_game.py:534-535`), skips sprites that `_is_sprite_clickable_now`
  (`base_game.py:581`, the documented override seam) rejects, and converts the
  FIRST non-negative rendered pixel of each sprite to screen coordinates via
  `camera._calculate_scale_and_offset()`. `click_cells` reproduces that rule
  verbatim, keeping one representative cell per sprite.
* A finished game answers a non-RESET action with `frame=[]` and the terminal
  state (`base_game.py:207-216`), so the drive loop stops at WIN/GAME_OVER
  instead of probing on.
* RESET at `_action_count == 0` is a FULL reset (`base_game.py:313`);
  `ONLY_RESET_LEVELS=true` in the environment rewrites that rule entirely
  (`base_game.py:311`), so every instantiation here pops the variable first.
  (Corpus trap, `arc-agi-3-games/HANDOFF.md` §Traps.)
* `ActionInput` is a pydantic model with fields `(id, data, reasoning)`;
  `ActionInput(id=..., x=1, y=2)` silently DISCARDS the coordinates — clicks
  must pass `data={"x": ..., "y": ...}` (same §Traps entry).
* `GameAction(6)` raises; enum members resolve by NAME only (same §Traps).

Determinism (contract requirement: two captures of one class must produce
identical `capture_to_json`)
---------------------------------------------------------------------------
Two engine seams leak nondeterminism into a naive capture and both are gated
here rather than papered over:

1. `Sprite.__init__` names an unnamed sprite `str(uuid.uuid4())`
   (`sprites.py:142`). A fresh UUID per instantiation would make
   `ClickCell.sprite_name` differ between two captures of the same class, so a
   name matching the UUID-4 shape is recorded as `None` (an anonymous sprite),
   which is the honest reading: the engine did not name it, the game did not
   either.
2. Probes re-instantiate the game instead of continuing one instance, so no
   probe can observe state another probe left behind, and a probe past a
   terminal state can never read the zeroed counters of the engine's
   finished-game early return.

Anything else that still differs between two captures is a property of the
GAME (its own RNG), and `capture` says so loudly at the call site rather than
hiding it: see `gen/s3_verify.py`'s determinism assertion and the B7 report.

Process isolation (R2 hotfix #8)
--------------------------------
B7 calibrated ONE capture per interpreter. R2 ran five S2b verifier rounds
inside one orchestrator process and round 5 died with

    AttributeError: module 'game_b41ec5f7c01a' has no attribute 'route'

raised from the worker's own `solver.py` — while that round's `game.py` defined
`route` at module level. The name is the GENERATED solver's §7 sibling-loader
name (`"game_" + sha256(<game.py path>)[:12]`), not one of this pipeline's
(`s3_game_*`/`s3_solver_*`): the generated solver looks its sibling up in
`sys.modules` FIRST and the key is derived from the PATH, which does not change
between rounds. So round 5's freshly exec-loaded solver was handed round 4's
game module — stale code from an earlier verify in the same interpreter.

B7's UUID/synthetic-name gate covers THIS module's loads only, and the worker
is generated code: no rule about how a solver names or caches its sibling load
can be relied on. The only fix that holds for code we did not write is a fresh
interpreter per capture, which is what `capture_worker_isolated` buys — an
empty `sys.modules` cannot serve a stale module. `capture_worker` remains the
in-process leg (tests and calibration drive it directly); the subprocess entry
(`python -m gen.frames --worker <dir> --out <frames.json>`) is a thin CLI over
that same function, so both legs produce the same bytes for the same inputs.

Provenance (R-21, contract W2-C)
-------------------------------
A capture is evidence ABOUT a source file, and until this contract nothing in
the artifact said WHICH one. The comparative audit's single worst visual
instance turned on exactly that hole: facing-sentinel's shipped
`worker.frames.json` describes a board its own `worker/game.py` does not paint
(`C_INK_DIM` 4 in the frames, 1 in the source — the sidecar was rendered from
bytes that were later replaced), and every reader downstream measured the old
board while naming the new file.

So a capture that KNOWS its source records it: `FrameCapture.source_sha256` is
the sha256 of the `game.py` bytes the capture imported. It is OPTIONAL in both
directions — `capture(game_cls, ...)` from a class in hand has no file to hash
and records None, and `capture_from_json` still reads every sidecar written
before this contract (the seven shipped games replay unchanged). `to_json`
therefore writes the key only when it is known: an absent key means "not
recorded", never "mismatch", and no reader may require it.

The stamp is taken in `capture_worker`, the one seam that knows the FILE, so
the two legs the "Process isolation" note above pairs — `capture_worker` and
`capture_worker_isolated` — still serialize to identical bytes, stamp included.
A capture driven straight from classes (`capture(game_cls, solver_cls)`) now
serializes to one key FEWER than a worker capture of the same game; that is the
optionality working, not a leak in the process boundary.

The step trace (R-20, contract W3-A1)
-------------------------------------
A `FrameCapture` keeps `fd.frame[-1]` at RESET, at every level transition and
at the end — and NOTHING else. Everything between two kept records is code-only:
refusal flashes, charging/open states, crush animations, every mid-level board.
The comparative audit measured the cost: four of conduit-watch's six tile states
are real in its `game.py` and absent from every settled frame we ever wrote, and
with no record of how many frames an action rendered we cannot even ASK whether
a board we did keep was a mid-animation artifact (the sc25 class).

So a capture may additionally write a TRACE beside its sidecar:
`<worker>.trace.jsonl.gz`, one gzipped JSONL record per engine `perform_action`,
in the officials' own format family (`GEN/tools/capture_frames.py`, read-only
reference): `{t, action, levels_completed, state, n_anim, frame|same_as_prev}`,
the board as 64 hex rows under the officials' exact encoder, deduped against the
previous record. `n_anim` is `len(fd.frame)` — the number of frames the engine
rendered for that step — which is the sc25 detector the sidecar never carried.
One decoder (`read_trace` + `resolve_trace_frames`) therefore serves both
corpora; a leading header line carries the W2-C `source_sha256`, and officials'
header-less traces read through the same function.

LEVEL STARTS, and the read that was tried and dropped. The contract asks for "a
fresh-reset settled grid per level start", and says to study whether the engine
offers a clean reset-read that does not perturb the replay. It does not. A true
fresh reset is out: `handle_reset()` rebuilds the level (`base_game.py:305-321`)
and destroys the very replay being traced. The near-miss is a pure render —
`camera.render(current_level.get_sprites())`, the exact expression
`perform_action` renders (`base_game.py:232`), allocating its own output and
only READING sprite state, so it cannot perturb anything. That was built, and
then MEASURED: it carries no information. `perform_action`'s last act before
returning IS that render, and nothing mutates a sprite between the return and
the caller, so the "level start read" is bit-for-bit the frame the transition
step already recorded — it deduped to `same_as_prev` on 100% of level starts
across eight shipped workers and three fixtures. It was therefore dropped rather
than shipped as a line that only ever repeats its predecessor.

What ships is the contract's own first sentence, "after each level transition,
record the next step", plus its stated fallback, "record the transition frame
AND its n_anim so a reader can at least detect the sc25 condition" — and one
record per step gives both for free: the transition's own settled frame with the
frame COUNT that action rendered, and then the incoming level's board at the
next step. `n_anim > 1` on a transition is exactly the sc25 condition, and it is
now on the record for the first time.

OPTIONAL, AND OFF BY DEFAULT (the house rule). The trace is a NEW file, so
"always on" would leave existing artifacts byte-identical — but the write is a
SIDE EFFECT newly added to a function that until now only returned a value, and
it is reached from call sites this contract may not touch: `s2_implement`'s
green loop captures once per attempt, `s3_verify.main` captures by hand, and
tests drive `capture_worker` over fixture dirs inside the repo and replay dirs
under `out/`. Defaulting on would have all of those start writing a gz file into
directories whose contents are pinned or read-only. Unarmed, therefore, nothing
changes at all: no new file, no extra render, no cost — and `frames.trace: on`
in the batch config arms it. The settled sidecar's BYTES are identical in both
modes; no reader anywhere requires the trace.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from arcengine import ActionInput, ARCBaseGame, GameAction, GameState

from .config import REPO_ROOT

# --- engine constants -------------------------------------------------------

GRID_SIZE = 64
COLOR_MIN, COLOR_MAX = 0, 15
TERMINAL_STATES = (GameState.WIN, GameState.GAME_OVER)

# The two tags `_get_valid_clickable_actions` reads (base_game.py:534-535).
CLICK_TAGS = ("sys_click", "sys_place")

# Probe budget. The contract's caps: at most 8 click cells probed, at most 40
# records in a probe capture (RESET always kept).
MAX_CLICK_PROBES = 8
MAX_PROBE_RECORDS = 40

# The solver drive loop's action budget. Named (rather than left a literal on
# `capture`) so the CLI entry and the subprocess wrapper cannot drift from the
# in-process default they exist to reproduce.
DEFAULT_MAX_ACTIONS = 600

# ACTION6 fallback when a game declares the click action but the engine reports
# no clickable sprite at all (the "click-only" corpus idiom handles raw
# coordinates without tagging: 0/25 officials tag `sys_place`, 11/25 tag
# `sys_click`). One centre probe keeps "every declared action has a frame"
# true, and the resulting record is what makes `static.sys-click-truthful`
# able to say anything at all about such a game.
CENTRE_CLICK = (GRID_SIZE // 2, GRID_SIZE // 2)

# `str(uuid.uuid4())` as the engine writes it (sprites.py:142).
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

_HEX_DIGITS = "0123456789abcdef"

# The same sixteen characters as ASCII codes, for the trace's vectorized row
# encoder (`trace_hex_rows`). Derived from `_HEX_DIGITS` so the two spellings of
# the palette-to-hex map cannot drift.
_HEX_BYTES = np.frombuffer(_HEX_DIGITS.encode("ascii"), dtype=np.uint8)

# The worker file a capture is evidence about (architecture §2's tree). Named
# once so the writer and every provenance reader hash the same file.
GAME_SOURCE_NAME = "game.py"

# A recorded provenance stamp is a lowercase sha256 hex digest or nothing.
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# --- the step trace (R-20, contract W3-A1) ----------------------------------
# See the module header, "The step trace", for what this artifact is and why it
# is unarmed by default.

# Written beside the frames sidecar, under the same `<worker> + suffix` rule
# `s3_verify.FRAMES_SUFFIX` uses, so the two files are siblings by construction.
TRACE_SUFFIX = ".trace.jsonl.gz"

# The first line of one of OUR traces. Officials' traces (`GEN/tools/
# capture_frames.py`) have no header line at all, and `read_trace` reads both.
TRACE_HEADER_KIND = "header"
TRACE_FORMAT = "arc-agi-3-trace/1"
TRACE_GRID_ENCODING = "hex-rows"

# The config block and its one knob. OFF is the default: unarmed, a capture
# writes no trace, renders nothing extra and costs exactly what it did before.
FRAMES_CONFIG_BLOCK = "frames"
TRACE_CONFIG_KEY = "trace"
FRAMES_CONFIG_KEYS = (TRACE_CONFIG_KEY,)
DEFAULT_TRACE = False


# --- dataclasses ------------------------------------------------------------


@dataclass(frozen=True)
class FrameRecord:
    """One settled 64x64 board, labelled by how the capture reached it."""

    label: str
    seq: int
    levels_completed: int
    state: str
    grid: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class ClickCell:
    """One representative clickable coordinate, as the ENGINE reports it."""

    level_index: int
    x: int
    y: int
    sprite_name: str | None


@dataclass(frozen=True)
class FrameCapture:
    """Everything the verifier legs are allowed to know about a game's play.

    `source_sha256` is the R-21 provenance stamp: the sha256 of the `game.py`
    bytes this capture imported, or None when the capture was driven from a
    class already in hand (no file, nothing to hash). OPTIONAL by construction
    — see the module header, "Provenance" — so a sidecar written before the
    contract loads exactly as it always did.
    """

    game_id: str
    source: str
    records: tuple[FrameRecord, ...]
    click_cells: tuple[ClickCell, ...]
    available_action_ids: tuple[int, ...]
    solver_actions: tuple[str, ...]
    levels_completed: int
    win: bool
    source_sha256: str | None = None


# --- engine plumbing --------------------------------------------------------


def source_sha256_of(path: Path | str) -> str:
    """sha256 of a game source file's BYTES — the stamp a capture records.

    Deliberately the same definition as `orchestrator._sha256_file` and
    `s6_package.game_hash`'s first term (sha256 over the raw bytes, no
    normalization): a provenance guard compares two spellings of one number, so
    they have to be the same number. Missing file = `FileNotFoundError`, loudly:
    a capture that could not read its own source has no honest stamp to write.
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _checked_source_sha256(value: object) -> str | None:
    """A provenance stamp on the way IN: a sha256 hex digest, or None."""
    if value is None:
        return None
    if not isinstance(value, str) or not _SHA256_RE.match(value):
        raise ValueError(
            f"source_sha256 must be a lowercase sha256 hex digest or None, got {value!r}"
        )
    return value


@contextlib.contextmanager
def quiet():
    """Swallow stdout/stderr — games print on load and on most actions.

    Exceptions still propagate: this hides noise, never failures. (Same rule
    as `gen/officials.py::load_official_class`, which quiets the exec-load.)
    """
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


def _fresh_game(game_cls: type[ARCBaseGame]) -> ARCBaseGame:
    """A quieted fresh instance with `ONLY_RESET_LEVELS` cleared."""
    os.environ.pop("ONLY_RESET_LEVELS", None)
    with quiet():
        game = game_cls()
    if not isinstance(game, ARCBaseGame):
        raise TypeError(
            f"{game_cls!r} did not construct an ARCBaseGame (got {type(game).__name__})"
        )
    return game


def _perform(game: ARCBaseGame, action: ActionInput, *, trace: TraceRecorder | None = None):
    """One engine action — and, when tracing, the one trace record for it.

    The recorder hangs HERE rather than at each call site so "one record per
    `step()`" is true by construction: every engine action this module performs,
    on every path, goes through this function.
    """
    with quiet():
        frame_data = game.perform_action(action)
    if trace is not None:
        trace.step(action, frame_data)
    return frame_data


def _reset(game: ARCBaseGame, *, trace: TraceRecorder | None = None):
    return _perform(game, ActionInput(id=GameAction.RESET), trace=trace)


def mouse(x: int, y: int) -> ActionInput:
    """ACTION6 with coordinates that actually arrive (`data=`, not kwargs)."""
    return ActionInput(id=GameAction.ACTION6, data={"x": int(x), "y": int(y)})


def describe_action(action: ActionInput) -> str:
    """Stable one-line action description; click coords in sorted key order."""
    data = {k: action.data[k] for k in sorted(action.data)} if action.data else {}
    return f"{action.id.name}{data or ''}"


def settled_grid(fd) -> tuple[tuple[int, ...], ...]:
    """`fd.frame[-1]` as an immutable int grid — the settled board.

    One action may render several frames (animation, level transition);
    `frame[0]` shows the board mid-animation and reads as "nothing happened"
    (`arc-agi-3-games/HANDOFF.md` §Traps). Fails loud on the shapes the
    conformance battery already rules out, because a capture that quietly
    stored a ragged or out-of-palette grid would poison every downstream leg.
    """
    frames = fd.frame
    if not frames:
        raise ValueError("cannot take a settled frame from an empty frame list")
    arr = np.asarray(frames[-1])
    while arr.ndim > 2:
        arr = arr[-1]
    if arr.shape != (GRID_SIZE, GRID_SIZE):
        raise ValueError(f"settled frame shape {arr.shape}, expected ({GRID_SIZE}, {GRID_SIZE})")
    if not np.issubdtype(arr.dtype, np.integer):
        raise ValueError(f"settled frame dtype {arr.dtype} is not integer")
    lo, hi = int(arr.min()), int(arr.max())
    if lo < COLOR_MIN or hi > COLOR_MAX:
        raise ValueError(f"settled frame colors [{lo}, {hi}] outside {COLOR_MIN}-{COLOR_MAX}")
    return tuple(tuple(int(v) for v in row) for row in arr.tolist())


def _sprite_name(sprite) -> str | None:
    """The sprite's authored name, or None when the engine invented a UUID."""
    name = sprite.name
    if not isinstance(name, str) or _UUID4_RE.match(name):
        return None
    return name


def click_cells(game: ARCBaseGame) -> tuple[ClickCell, ...]:
    """The engine's clickable list for the CURRENT level, one cell per sprite.

    Mirrors `_get_valid_clickable_actions` (`base_game.py:522-579`): both click
    tags, the `_is_sprite_clickable_now` filter, and the first non-negative
    rendered pixel converted to screen coordinates. `sys_every_pixel` sprites
    yield every pixel to the engine; one representative is enough here, and
    the tag itself is code evidence the static leg reads separately.
    """
    level = game.current_level
    sprites: list = []
    for tag in CLICK_TAGS:
        sprites.extend(level.get_sprites_by_tag(tag))

    scale, x_offset, y_offset = game.camera._calculate_scale_and_offset()
    cells: list[ClickCell] = []
    for sprite in sprites:
        if not game._is_sprite_clickable_now(sprite):
            continue
        pixels = sprite.render()
        found = None
        for y in range(pixels.shape[0]):
            for x in range(pixels.shape[1]):
                if pixels[y, x] >= 0:
                    found = (
                        (sprite._x + x) * scale + x_offset,
                        (sprite._y + y) * scale + y_offset,
                    )
                    break
            if found is not None:
                break
        if found is None:
            continue
        cells.append(
            ClickCell(
                level_index=game.level_index,
                x=int(found[0]),
                y=int(found[1]),
                sprite_name=_sprite_name(sprite),
            )
        )
    return tuple(cells)


def _action_by_id(action_id: int) -> GameAction | None:
    """`GameAction` for a declared int, by NAME (`GameAction(6)` raises)."""
    try:
        return GameAction[f"ACTION{int(action_id)}"]
    except (KeyError, ValueError):
        return None


def _playable_action_ids(fd) -> list[int]:
    """Declared playable ids off the FRAME, RESET removed, ascending."""
    return sorted({int(a) for a in fd.available_actions} - {GameAction.RESET.value})


# --- capture ----------------------------------------------------------------


def capture(
    game_cls: type[ARCBaseGame],
    solver_cls: type | None = None,
    *,
    max_actions: int = DEFAULT_MAX_ACTIONS,
    source_sha256: str | None = None,
    trace: TraceRecorder | None = None,
) -> FrameCapture:
    """Freeze a game's play into a `FrameCapture`.

    With a solver (`source="solver"`), this is the `run_solver` drive loop
    from `worker-template/tests/_harness.py` reduced to what the verifier
    needs: RESET, then `solver.next_action(fd)` until the game terminates, the
    solver returns None, or `max_actions` actions have been played. Settled
    frames are kept at RESET, at every level transition, and at the end.

    Without a solver (`source="probe"`), it is the PROBE PLAN: RESET, then one
    FRESH instance per probe — each declared non-RESET action in ascending id
    order, and for the click action each engine-reported clickable cell (cap
    `MAX_CLICK_PROBES`). Fresh instances are what make a probe capture both
    independent (no probe sees another's state) and deterministic.

    `source_sha256` (R-21) is the provenance stamp of the file `game_cls` was
    loaded from. This function is handed CLASSES, so it cannot discover it: the
    loader passes it (`capture_worker` does), and a caller that loaded the class
    some other way records nothing rather than guessing.

    `trace` (R-20) is an OPTIONAL `TraceRecorder`. Passed one, every engine
    action this capture performs is recorded into it and the caller writes the
    result where it belongs; passed None — the default, and what every call site
    outside `capture_worker` still passes — not one extra render happens and the
    returned capture is byte-identical to the one this function returned before
    the trace existed.
    """
    if not (isinstance(game_cls, type) and issubclass(game_cls, ARCBaseGame)):
        raise TypeError(f"game_cls must be an ARCBaseGame subclass, got {game_cls!r}")
    if max_actions < 1:
        raise ValueError(f"max_actions must be >= 1, got {max_actions}")
    if trace is not None and not isinstance(trace, TraceRecorder):
        raise TypeError(f"trace must be a TraceRecorder or None, got {type(trace).__name__}")
    stamp = _checked_source_sha256(source_sha256)
    if solver_cls is not None:
        return _capture_solver(
            game_cls, solver_cls, max_actions=max_actions, source_sha256=stamp, trace=trace
        )
    return _capture_probe(game_cls, source_sha256=stamp, trace=trace)


def _capture_solver(
    game_cls: type[ARCBaseGame],
    solver_cls: type,
    *,
    max_actions: int,
    source_sha256: str | None = None,
    trace: TraceRecorder | None = None,
) -> FrameCapture:
    if not isinstance(solver_cls, type):
        raise TypeError(f"solver_cls must be a class, got {solver_cls!r}")
    game = _fresh_game(game_cls)
    solver = solver_cls()
    reset_fn = getattr(solver, "reset", None)
    if callable(reset_fn):
        reset_fn()
    if not callable(getattr(solver, "next_action", None)):
        raise TypeError(f"{solver_cls.__name__} has no callable next_action(frame_data)")

    fd = _reset(game, trace=trace)
    records = [
        FrameRecord(
            label="reset",
            seq=0,
            levels_completed=int(fd.levels_completed),
            state=fd.state.name,
            grid=settled_grid(fd),
        )
    ]
    cells = click_cells(game)
    action_ids = tuple(int(a) for a in fd.available_actions)

    actions: list[str] = []
    previous_completed = int(fd.levels_completed)
    for step_index in range(max_actions):
        if fd.state in TERMINAL_STATES:
            break
        action = solver.next_action(fd)
        if action is None:
            break
        if not isinstance(action, ActionInput):
            raise TypeError(
                f"solver returned {type(action).__name__} at action #{step_index + 1}, "
                "expected ActionInput"
            )
        described = describe_action(action)
        actions.append(described)
        fd = _perform(game, action, trace=trace)
        completed = int(fd.levels_completed)
        if completed > previous_completed:
            records.append(
                FrameRecord(
                    label=f"step-{step_index + 1}:{described}",
                    seq=len(records),
                    levels_completed=completed,
                    state=fd.state.name,
                    grid=settled_grid(fd),
                )
            )
        previous_completed = completed

    records.append(
        FrameRecord(
            label="final",
            seq=len(records),
            levels_completed=int(fd.levels_completed),
            state=fd.state.name,
            grid=settled_grid(fd),
        )
    )
    return FrameCapture(
        game_id=str(fd.game_id),
        source="solver",
        records=tuple(records),
        click_cells=cells,
        available_action_ids=action_ids,
        solver_actions=tuple(actions),
        levels_completed=int(fd.levels_completed),
        win=fd.state is GameState.WIN,
        source_sha256=source_sha256,
    )


def _capture_probe(
    game_cls: type[ARCBaseGame],
    *,
    source_sha256: str | None = None,
    trace: TraceRecorder | None = None,
) -> FrameCapture:
    game = _fresh_game(game_cls)
    fd = _reset(game, trace=trace)
    records = [
        FrameRecord(
            label="reset",
            seq=0,
            levels_completed=int(fd.levels_completed),
            state=fd.state.name,
            grid=settled_grid(fd),
        )
    ]
    cells = click_cells(game)
    action_ids = tuple(int(a) for a in fd.available_actions)
    del game  # every probe below runs on its own fresh instance

    plan: list[ActionInput] = []
    for action_id in _playable_action_ids(fd):
        action = _action_by_id(action_id)
        if action is None:
            # A declared id outside 1-7 is not probeable; the worker
            # conformance battery (R3) is where that becomes a violation.
            continue
        if action is GameAction.ACTION6:
            if cells:
                plan.extend(mouse(cell.x, cell.y) for cell in cells[:MAX_CLICK_PROBES])
            else:
                plan.append(mouse(*CENTRE_CLICK))
        else:
            plan.append(ActionInput(id=action))

    for probe_index, action in enumerate(plan, start=1):
        if len(records) >= MAX_PROBE_RECORDS:
            break
        probe_game = _fresh_game(game_cls)
        probe_fd = _reset(probe_game, trace=trace)
        probe_fd = _perform(probe_game, action, trace=trace)
        del probe_game
        records.append(
            FrameRecord(
                label=f"probe-{probe_index}:{describe_action(action)}",
                seq=len(records),
                levels_completed=int(probe_fd.levels_completed),
                state=probe_fd.state.name,
                grid=settled_grid(probe_fd),
            )
        )

    return FrameCapture(
        game_id=str(fd.game_id),
        source="probe",
        records=tuple(records),
        click_cells=cells,
        available_action_ids=action_ids,
        solver_actions=(),
        levels_completed=int(fd.levels_completed),
        win=fd.state is GameState.WIN,
        source_sha256=source_sha256,
    )


# --- JSON round-trip --------------------------------------------------------


def capture_to_json(cap: FrameCapture) -> dict:
    """JSON-safe dict. `capture_from_json` is its exact inverse.

    `source_sha256` is written ONLY when the capture recorded one (R-21): a
    capture driven from a class in hand serializes to exactly the bytes it did
    before this contract, and an absent key downstream reads as "not recorded".
    """
    if not isinstance(cap, FrameCapture):
        raise TypeError(f"capture_to_json expects a FrameCapture, got {type(cap).__name__}")
    payload = {
        "game_id": cap.game_id,
        "source": cap.source,
        "records": [
            {
                "label": r.label,
                "seq": r.seq,
                "levels_completed": r.levels_completed,
                "state": r.state,
                "grid": [list(row) for row in r.grid],
            }
            for r in cap.records
        ],
        "click_cells": [
            {"level_index": c.level_index, "x": c.x, "y": c.y, "sprite_name": c.sprite_name}
            for c in cap.click_cells
        ],
        "available_action_ids": list(cap.available_action_ids),
        "solver_actions": list(cap.solver_actions),
        "levels_completed": cap.levels_completed,
        "win": cap.win,
    }
    # LAST, and only when known: a sidecar written before R-21 differs from one
    # written after it by exactly one appended line.
    if cap.source_sha256 is not None:
        payload["source_sha256"] = str(cap.source_sha256)
    return payload


_CAPTURE_KEYS = (
    "game_id",
    "source",
    "records",
    "click_cells",
    "available_action_ids",
    "solver_actions",
    "levels_completed",
    "win",
)
_RECORD_KEYS = ("label", "seq", "levels_completed", "state", "grid")
_CELL_KEYS = ("level_index", "x", "y", "sprite_name")

# R-21: keys a capture MAY carry. Optional in the reader is the whole point —
# every sidecar written before the stamp existed must still load.
_CAPTURE_OPTIONAL_KEYS = ("source_sha256",)


def _require_keys(
    d: dict, keys: tuple[str, ...], what: str, optional: tuple[str, ...] = ()
) -> None:
    if not isinstance(d, dict):
        raise TypeError(f"{what}: expected a mapping, got {type(d).__name__}")
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{what}: missing key(s) {missing}")
    known = set(keys) | set(optional)
    extra = [k for k in d if k not in known]
    if extra:
        raise ValueError(f"{what}: unexpected key(s) {sorted(extra)}")


def capture_from_json(d: dict) -> FrameCapture:
    """Exact inverse of `capture_to_json`; fail-loud on any deviation.

    `source_sha256` is the one OPTIONAL key (R-21). Absent, the capture reports
    `source_sha256 is None` — "this sidecar does not say what rendered it",
    which is what every pre-contract sidecar on disk means and is never by
    itself an error. Present, it must be a sha256 hex digest.
    """
    _require_keys(d, _CAPTURE_KEYS, "frames JSON", optional=_CAPTURE_OPTIONAL_KEYS)
    records = []
    for index, raw in enumerate(d["records"]):
        _require_keys(raw, _RECORD_KEYS, f"frames JSON records[{index}]")
        records.append(
            FrameRecord(
                label=str(raw["label"]),
                seq=int(raw["seq"]),
                levels_completed=int(raw["levels_completed"]),
                state=str(raw["state"]),
                grid=tuple(tuple(int(v) for v in row) for row in raw["grid"]),
            )
        )
    cells = []
    for index, raw in enumerate(d["click_cells"]):
        _require_keys(raw, _CELL_KEYS, f"frames JSON click_cells[{index}]")
        name = raw["sprite_name"]
        cells.append(
            ClickCell(
                level_index=int(raw["level_index"]),
                x=int(raw["x"]),
                y=int(raw["y"]),
                sprite_name=None if name is None else str(name),
            )
        )
    return FrameCapture(
        game_id=str(d["game_id"]),
        source=str(d["source"]),
        records=tuple(records),
        click_cells=tuple(cells),
        available_action_ids=tuple(int(a) for a in d["available_action_ids"]),
        solver_actions=tuple(str(a) for a in d["solver_actions"]),
        levels_completed=int(d["levels_completed"]),
        win=bool(d["win"]),
        source_sha256=_checked_source_sha256(d.get("source_sha256")),
    )


# --- the step trace ---------------------------------------------------------
# See the module header, "The step trace (R-20, contract W3-A1)".


def _frames_block(cfg: Mapping) -> Mapping:
    """The `frames:` config block, key-checked — or `{}` when absent.

    Closed key set, the `gate:`/`tiers.tier_policy` rule: this knob is read at
    the top of a stage that is about to spend, so a typo that silently defaulted
    would look exactly like a trace nobody wanted.
    """
    raw = cfg.get(FRAMES_CONFIG_BLOCK) if isinstance(cfg, Mapping) else None
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError(  # noqa: TRY004 — a config defect; the block reports ValueError
            f"{FRAMES_CONFIG_BLOCK} must be a mapping of frames knobs, got {raw!r}"
        )
    unknown = sorted(str(key) for key in set(raw) - set(FRAMES_CONFIG_KEYS))
    if unknown:
        raise ValueError(
            f"{FRAMES_CONFIG_BLOCK} names unknown keys {unknown} "
            f"(expected {list(FRAMES_CONFIG_KEYS)})"
        )
    return raw


def trace_enabled(cfg: Mapping) -> bool:
    """`frames.trace` — `off` (the DEFAULT) or `on`.

    Both spellings of each value are accepted and nothing else is: YAML 1.1
    resolves a bare `on`/`off` to a bool before this ever sees it, while a JSON
    config or a quoted value arrives as the string. `1`/`0`/`"true"` raise
    rather than guess — an invalid knob is a loud ValueError read before the
    stage does any work (the wave's common rule).
    """
    value = _frames_block(cfg).get(TRACE_CONFIG_KEY, DEFAULT_TRACE)
    if value is True or value == "on":
        return True
    if value is False or value == "off":
        return False
    raise ValueError(
        f"{FRAMES_CONFIG_BLOCK}.{TRACE_CONFIG_KEY} must be on|off "
        f"(YAML `on`/`off`, or the strings 'on'/'off'), got {value!r}"
    )


def trace_path(worker_dir: Path | str) -> Path:
    """Where a worker's trace goes: beside its frames sidecar."""
    worker_dir = Path(worker_dir)
    return worker_dir.with_name(worker_dir.name + TRACE_SUFFIX)


def trace_hex_rows(frame) -> list[str]:
    """One board as hex rows — the OFFICIALS' encoding, byte for byte.

    `GEN/tools/capture_frames.py::hex_rows` is `format(int(v) & 0xF, "x")` per
    cell; `_HEX_DIGITS[v & 0xF]` is that same character for every int, so one
    decoder reads both corpora. The MASK (rather than this module's bare
    `_HEX_DIGITS[v]` lookup, which raises past 15) is deliberate: the trace
    records EVERY step, including the ones `settled_grid` never validates, and a
    tracer that raised on a stray paint index would kill captures that succeed
    today. Out-of-palette paint stays the conformance battery's business, not
    the recorder's.

    Vectorized rather than looped because this runs once per engine step on a
    64x64 board: the per-cell `format()` call the officials' one-shot tool can
    afford cost ~370% of a shipped worker's whole capture when measured, and a
    gather plus one `bytes.decode` per row costs ~4% of that.
    """
    arr = np.asarray(frame)
    while arr.ndim > 2:
        arr = arr[-1]
    codes = _HEX_BYTES[np.asarray(arr, dtype=np.int64) & 0xF]
    return [row.tobytes().decode("ascii") for row in np.atleast_2d(codes)]


class TraceRecorder:
    """Buffers one capture's step records; `write_trace` puts them on disk.

    Buffered rather than streamed so the header line can carry facts the capture
    only knows once it has run (game id, record count) and so a capture that
    raises leaves no half-written artifact behind.

    `t` is the step ordinal: `t=0` is the RESET and every later record is one
    engine action, which is the officials' own `t` (they emit exactly one record
    per action too). Nothing else ever occupies a line — see the module header,
    "LEVEL STARTS", for the pure-render line that was built, measured to be a
    duplicate of its predecessor every single time, and dropped.
    """

    __slots__ = ("_previous_rows", "records")

    def __init__(self) -> None:
        self.records: list[dict] = []
        self._previous_rows: list[str] | None = None

    def _append(
        self,
        action: list,
        levels_completed: int,
        state: str,
        n_anim: int,
        rows: list[str] | None,
    ) -> None:
        # Key ORDER is the officials' order (t, action, levels_completed, state,
        # n_anim, frame|same_as_prev); `json.dumps` preserves it, so the two
        # corpora's lines differ only in content.
        record: dict = {
            "t": len(self.records),
            "action": action,
            "levels_completed": int(levels_completed),
            "state": str(state),
            "n_anim": int(n_anim),
        }
        if rows is not None:
            if rows == self._previous_rows:
                record["same_as_prev"] = True
            else:
                record["frame"] = rows
            self._previous_rows = rows
        self.records.append(record)

    def step(self, action: ActionInput, fd) -> None:
        """One engine `perform_action` — the whole of what a step returned.

        A finished game answers with `frame=[]` (`base_game.py:207-216`), which
        records as `n_anim: 0` and no frame key at all: exactly what the
        officials' recorder writes for the same case.
        """
        frames = fd.frame
        data = {key: action.data[key] for key in sorted(action.data)} if action.data else {}
        self._append(
            [int(action.id.value), data],
            fd.levels_completed,
            fd.state.name,
            len(frames) if frames else 0,
            trace_hex_rows(frames[-1]) if frames else None,
        )


def trace_bytes(
    recorder: TraceRecorder,
    *,
    game_id: str,
    source: str,
    source_sha256: str | None = None,
) -> bytes:
    """The gzipped JSONL a trace is, as BYTES — deterministic by construction.

    `mtime=0` and a `BytesIO` with no `.name` keep the gzip header free of the
    two fields that would otherwise make two traces of one capture differ
    (timestamp, embedded filename), so a trace is byte-stable the way every
    other artifact in this pipeline is.

    `source_sha256` (W2-C) rides the HEADER line and, like the sidecar's key, is
    written only when it is known — a capture driven from a class in hand has no
    file to hash and says nothing rather than guessing.
    """
    if not isinstance(recorder, TraceRecorder):
        raise TypeError(f"trace_bytes expects a TraceRecorder, got {type(recorder).__name__}")
    header = {
        "kind": TRACE_HEADER_KIND,
        "format": TRACE_FORMAT,
        "game_id": str(game_id),
        "source": str(source),
        "records": len(recorder.records),
        "grid": TRACE_GRID_ENCODING,
    }
    stamp = _checked_source_sha256(source_sha256)
    if stamp is not None:
        header["source_sha256"] = stamp
    body = "".join(
        json.dumps(line, separators=(",", ":")) + "\n"
        for line in (header, *recorder.records)
    ).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as archive:
        archive.write(body)
    return buffer.getvalue()


def write_trace(
    path: Path | str,
    recorder: TraceRecorder,
    *,
    game_id: str,
    source: str,
    source_sha256: str | None = None,
) -> int:
    """Write the trace to `path`; returns the bytes written."""
    payload = trace_bytes(
        recorder, game_id=game_id, source=source, source_sha256=source_sha256
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return len(payload)


def read_trace(path: Path | str) -> tuple[dict, list[dict]]:
    """`(header, records)` from a trace — OURS or an official's.

    A first line carrying `kind: header` is the header; anything else means the
    file has none (the officials' traces are pure step records) and the header
    comes back empty. No reader is REQUIRED to call this — the trace is optional
    everywhere — but everything that does read one reads it here.
    """
    with gzip.open(Path(path), "rt", encoding="utf-8") as archive:
        lines = [json.loads(line) for line in archive if line.strip()]
    if lines and isinstance(lines[0], dict) and lines[0].get("kind") == TRACE_HEADER_KIND:
        return lines[0], lines[1:]
    return {}, lines


def resolve_trace_frames(records: list[dict]) -> list[list[str] | None]:
    """Each record's board with `same_as_prev` expanded back into hex rows.

    None where a record carried no frame at all (the engine's finished-game
    early return). This is the other half of the one decoder the two corpora
    share: officials' records dedupe with the same key.
    """
    resolved: list[list[str] | None] = []
    previous: list[str] | None = None
    for record in records:
        if record.get("same_as_prev"):
            rows = previous
        elif "frame" in record:
            rows = [str(row) for row in record["frame"]]
        else:
            rows = None
        if rows is not None:
            previous = rows
        resolved.append(rows)
    return resolved


# --- worker capture, one fresh interpreter each -----------------------------
# See the module header, "Process isolation (R2 hotfix #8)", for the incident
# these two functions answer.

# Wall-clock bound on ONE isolated capture. Generous by design: a real worker's
# capture plus interpreter start is seconds, and the only thing this number has
# to catch is a child that never comes back at all.
DEFAULT_CAPTURE_TIMEOUT_S = 600.0

# How much of a failed child's stderr the raised error quotes.
STDERR_TAIL_CHARS = 2000

# The child's output file inside the wrapper's own temp dir. Never a pipe:
# games PRINT on load and on most actions, so stdout cannot carry the payload.
_FRAMES_TMP_NAME = "frames.json"


class CaptureProcessError(RuntimeError):
    """An isolated capture did not come back with a readable `FrameCapture`."""


def _stderr_tail(blob: object) -> str:
    """The end of a child's stderr, for an error message."""
    if isinstance(blob, bytes):
        blob = blob.decode("utf-8", "replace")
    if not isinstance(blob, str) or not blob.strip():
        return "<empty>"
    text = blob.strip()
    if len(text) > STDERR_TAIL_CHARS:
        return "…" + text[-STDERR_TAIL_CHARS:]
    return text


def capture_worker(
    worker_dir: Path | str,
    *,
    max_actions: int = DEFAULT_MAX_ACTIONS,
    trace: bool = DEFAULT_TRACE,
) -> FrameCapture:
    """IN-PROCESS: load a worker's game/solver classes, then `capture` them.

    The two-call idiom every stage spells out by hand (`load_worker_classes`,
    then `capture`), named once — so the subprocess entry below can be a thin
    CLI over EXACTLY this behavior instead of a second implementation of it.

    The loader is `gen/s3_verify.py`'s deliberately, because that is the one the
    S3 run path used before isolation: it is the strict reading (exactly one
    ARCBaseGame subclass DEFINED in game.py, never one merely imported by it)
    and the only one that turns bytecode writing off while it execs, so a verify
    still writes nothing into the worker it audits. `gen/s3_static.py`'s loader
    is the permissive one; swapping it in here would change which game.py files
    are accepted, which is not this fix's business.

    The import is function-local: `gen/s3_verify.py` imports this module.

    This is also the ONE seam that knows a capture's source FILE, so it is where
    the R-21 provenance stamp is taken: the sha256 of the `game.py` the loader
    just imported, hashed AFTER the load so the bytes stamped are the bytes that
    ran. `capture_worker_isolated` is a CLI over this function and its child
    ends here too, which is why both legs still serialize identically.

    `trace` (R-20) is the one thing this function does BESIDES returning a
    capture: armed, it writes `<worker>.trace.jsonl.gz` beside the sidecar. It
    is False by default and the returned `FrameCapture` is identical either way
    — see the module header, "The step trace", for why the write is unarmed
    unless a batch asks for it.
    """
    from .s3_verify import load_worker_classes

    worker_dir = Path(worker_dir)
    game_cls, solver_cls = load_worker_classes(worker_dir)
    recorder = TraceRecorder() if trace else None
    cap = capture(
        game_cls,
        solver_cls,
        max_actions=max_actions,
        source_sha256=source_sha256_of(worker_dir / GAME_SOURCE_NAME),
        trace=recorder,
    )
    if recorder is not None:
        write_trace(
            trace_path(worker_dir),
            recorder,
            game_id=cap.game_id,
            source=cap.source,
            source_sha256=cap.source_sha256,
        )
    return cap


def capture_worker_isolated(
    worker_dir: Path | str,
    *,
    max_actions: int = DEFAULT_MAX_ACTIONS,
    timeout_s: float = DEFAULT_CAPTURE_TIMEOUT_S,
    trace: bool = DEFAULT_TRACE,
) -> FrameCapture:
    """`capture_worker` in a FRESH interpreter — the same capture, isolated.

    Runs `python -m gen.frames --worker … --out …` under THIS interpreter
    (`sys.executable`, i.e. the venv), reads the child's JSON back through
    `capture_from_json`, and returns the capture the caller would have got in
    process. An empty `sys.modules` is the whole point: no module a previous
    round exec-loaded — under any name, cached by anyone's loader — can be
    served to this one.

    Fail-loud, never partial: a timeout, a nonzero exit, a missing file,
    unparsable JSON or a payload `capture_from_json` rejects all raise
    `CaptureProcessError` quoting the tail of the child's stderr.

    The child runs with `cwd=REPO_ROOT` (so `-m gen.frames` resolves whether or
    not the package is installed, and so the capture's cwd is the same for every
    caller), `stdin` at DEVNULL (an inherited pipe is a silent forever-hang in
    headless runs — the B0 driver lesson in `gen/backends.py`), and absolute
    paths for both the worker and the output file.

    `trace` (R-20) passes `--trace` to the child, which writes the trace itself
    from `capture_worker`. Its path is derived from the WORKER, never from
    `--out`, so the artifact lands beside the sidecar exactly where the
    in-process leg puts it and the child's own temp dir never sees it.
    """
    worker = Path(worker_dir).resolve()
    if not worker.is_dir():
        raise FileNotFoundError(f"worker dir not found: {worker}")
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or timeout_s <= 0:
        raise ValueError(f"timeout_s must be a positive number, got {timeout_s!r}")
    if max_actions < 1:
        raise ValueError(f"max_actions must be >= 1, got {max_actions}")

    with tempfile.TemporaryDirectory(prefix="gen-frames-") as tmp:
        out_path = Path(tmp) / _FRAMES_TMP_NAME
        cmd = [
            sys.executable,
            "-m",
            "gen.frames",
            "--worker",
            str(worker),
            "--out",
            str(out_path),
            "--max-actions",
            # Not coerced: a non-int budget must fail in the child's argparse
            # (and surface as a CaptureProcessError), never be truncated here
            # into a capture that silently played a different number of actions.
            str(max_actions),
        ]
        if trace:
            cmd.append("--trace")
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=float(timeout_s),
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            raise CaptureProcessError(
                f"isolated capture of {worker} exceeded {float(timeout_s):.0f}s and was "
                f"killed. partial stderr: {_stderr_tail(exc.stderr)}"
            ) from exc
        if proc.returncode != 0:
            raise CaptureProcessError(
                f"isolated capture of {worker} exited {proc.returncode}. "
                f"stderr: {_stderr_tail(proc.stderr)}"
            )
        if not out_path.is_file():
            raise CaptureProcessError(
                f"isolated capture of {worker} exited 0 but wrote no frames to "
                f"{out_path.name}. stderr: {_stderr_tail(proc.stderr)}"
            )
        payload_text = out_path.read_text(encoding="utf-8")

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise CaptureProcessError(
            f"isolated capture of {worker} wrote unparsable JSON ({exc}). "
            f"stderr: {_stderr_tail(proc.stderr)}"
        ) from exc
    try:
        return capture_from_json(payload)
    except (TypeError, ValueError) as exc:
        raise CaptureProcessError(
            f"isolated capture of {worker} wrote a payload that is not a FrameCapture "
            f"({exc}). stderr: {_stderr_tail(proc.stderr)}"
        ) from exc


# --- digest -----------------------------------------------------------------


def _hex_row(row: tuple[int, ...]) -> str:
    return "".join(_HEX_DIGITS[v] for v in row)


def select_records(cap: FrameCapture, max_frames: int) -> tuple[FrameRecord, ...]:
    """Which frames the digest shows when the capture exceeds `max_frames`.

    Priority, per the B7 contract: "reset" always, every level transition
    (a record whose `levels_completed` exceeds the record before it), "final"
    always; the rest are dropped FROM THE MIDDLE, keeping the earliest
    survivors, because the opening probes are what identify the locus of
    control (spec §2 REQUIRED 1).
    """
    if max_frames < 1:
        raise ValueError(f"max_frames must be >= 1, got {max_frames}")
    records = cap.records
    if len(records) <= max_frames:
        return records

    previous = 0
    keep: set[int] = set()
    for index, record in enumerate(records):
        transition = record.levels_completed > previous
        if record.label in ("reset", "final") or transition:
            keep.add(index)
        previous = record.levels_completed
    # Always keep the first and last record even if a game labels neither.
    keep.add(0)
    keep.add(len(records) - 1)

    if len(keep) > max_frames:
        ordered = sorted(keep)
        keep = set(ordered[: max_frames - 1]) | {ordered[-1]}
    else:
        for index in range(len(records)):
            if len(keep) >= max_frames:
                break
            keep.add(index)
    return tuple(records[index] for index in sorted(keep))


def digest_text(cap: FrameCapture, *, max_frames: int = 12) -> str:
    """The frames as the blind verifier session sees them.

    Header (game id, capture source, declared actions, engine click cells,
    solver line length, win) then up to `max_frames` settled boards, each as
    64 hex rows (rendered values 0-15 map to `0`-`9`,`a`-`f`; `GEN/spec-v0.3.md`
    §2 pins the palette at 16 indices). Hex keeps one board to 64 lines of 64
    characters, which is what makes a dozen boards affordable in one prompt.
    When frames are dropped the header says which and why.
    """
    if not isinstance(cap, FrameCapture):
        raise TypeError(f"digest_text expects a FrameCapture, got {type(cap).__name__}")
    shown = select_records(cap, max_frames)

    cells = ", ".join(
        f"({c.x},{c.y})@L{c.level_index}{'' if c.sprite_name is None else ' ' + c.sprite_name}"
        for c in cap.click_cells
    )
    lines = [
        f"game_id: {cap.game_id}",
        f"capture source: {cap.source}",
        f"declared available_actions: {list(cap.available_action_ids)}",
        f"engine sys_click/sys_place cells ({len(cap.click_cells)}): {cells or 'none'}",
        f"solver line length: {len(cap.solver_actions)} action(s)",
        f"levels_completed: {cap.levels_completed}  win: {cap.win}",
        f"frames captured: {len(cap.records)}; shown: {len(shown)}",
    ]
    if len(shown) < len(cap.records):
        kept_seqs = {r.seq for r in shown}
        dropped = [r.label for r in cap.records if r.seq not in kept_seqs]
        lines.append(
            "frame selection: RESET, every level transition and the final frame are "
            "always kept; the middle is dropped to fit the cap. dropped: "
            + ", ".join(dropped)
        )
    lines.append(
        "grid encoding: 64 rows x 64 columns, one hex digit per cell "
        "(0-9 = colors 0-9, a-f = colors 10-15)."
    )

    for record in shown:
        lines.append("")
        lines.append(
            f"--- frame {record.seq} [{record.label}] state={record.state} "
            f"levels_completed={record.levels_completed}"
        )
        lines.extend(_hex_row(row) for row in record.grid)
    return "\n".join(lines) + "\n"


# --- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """One worker's capture, in THIS process, serialized to `--out`.

    The child half of `capture_worker_isolated`, and useful by hand. It adds
    nothing to `capture_worker`: whatever this writes is what the in-process
    call returns, `capture_to_json`-encoded exactly as `gen/s3_verify.py` writes
    the frames artifact (indent=2, trailing newline).

    The payload goes to a FILE, never to stdout: games print on load and on most
    actions, and a print landing in the middle of the JSON would be a corrupt
    capture that looked like a parse bug.

    `--trace` (R-20) is the only flag that writes anywhere but `--out`, and it
    writes where `capture_worker` always writes a trace: beside the worker.
    """
    parser = argparse.ArgumentParser(
        prog="python -m gen.frames",
        description="Capture one worker's frames in this process and write them to --out.",
    )
    parser.add_argument("--worker", required=True, help="worker dir holding game.py (+ solver.py)")
    parser.add_argument("--out", required=True, help="write the frames JSON here")
    parser.add_argument(
        "--max-actions",
        type=int,
        default=DEFAULT_MAX_ACTIONS,
        help=f"solver drive-loop budget (default {DEFAULT_MAX_ACTIONS})",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help=(
            f"also write the step trace to <worker>{TRACE_SUFFIX} beside the sidecar "
            "(R-20; off unless asked for)"
        ),
    )
    args = parser.parse_args(argv)

    cap = capture_worker(args.worker, max_actions=args.max_actions, trace=args.trace)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(capture_to_json(cap), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
