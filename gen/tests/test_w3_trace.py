"""W3-A1 · R-20 — the capture-scope upgrade, pinned from the contract alone.

THE DEFECT the contract answers. Our sidecars keep `fd.frame[-1]` at RESET, at
every level transition and at the end — nothing else. So every TRANSIENT the
game paints between those moments (refusal flashes, CHARGING/LIT_OPEN states,
crush flashes, mid-level boards) exists in the code and in no artifact: four of
conduit's six tile states are real in the source and absent from every settled
frame we ever wrote. And because no record says how many frames the engine
returned for a step, the sc25 capture-artifact class cannot be excluded for our
games at all. The officials' own artifacts carry `trace.jsonl.gz` — which is the
only reason M-1 could recompute their 183 rows.

THE CONTRACT (wave 3, A1), the behaviours these pins measure:

1. `capture_worker` (and therefore `capture_worker_isolated`) additionally
   writes `worker.trace.jsonl.gz` BESIDE the sidecar — one JSONL record per
   `step()`: `{t, action, levels_completed, state, n_anim, frame|same_as_prev}`
   in the officials' format family (hex-row frames, so one decoder serves both
   corpora). `n_anim` is the number of frames the engine returned for the step.
2. The trace carries `source_sha256` in a HEADER line (the W2-C machinery).
3. OPTIONALITY, pinned hard: the settled sidecar's bytes are UNCHANGED, no
   reader anywhere REQUIRES the trace, and a knob `frames.trace` turns it
   on|off. The contract DELEGATES the default to the implementer ("state your
   choice + reasoning; template.yaml arms on if you default off"), so this file
   pins BOTH branches through the knob and DISCOVERS the default at runtime,
   printing what it found (`-s`, or read it off any failure below).
4. W2-C residual (a): the orchestrator's `s4_baselines` stage asks
   `frames_provenance(worker_dir)` before `_post_s4_level_floor` consumes the
   sidecar — mismatch refuses with the same reason, unrecorded is a note and
   never a refusal.

BLINDNESS. Written from the contract text alone. The implementer's diff was
never read: every statement below about the PRE-change pipeline came out of
`git show HEAD:gen/frames.py` and `HEAD:gen/orchestrator.py` (HEAD = the wave-2
close), and the officials' record shape came out of the READ-ONLY canon the
contract names (`GEN/tools/capture_frames.py`'s docstring and the checked-in
`out/frames/*/trace.jsonl.gz` it wrote). Where the contract delegates a decision
nothing here guesses a name: the knob is found by trying every arming mechanism
the house uses (a keyword on the seam, a module-level flag, an environment
variable) and keeping the one that actually FLIPS the artifact, and a mechanism
that cannot be found fails with the full list of what was tried, so the lead can
alias in one line instead of reverse-engineering what the pin wanted.

WHICH PINS FAIL AT HEAD. Every trace pin (1-8, 12-18) — HEAD writes no trace at
all. The optionality/regression half holds at HEAD and after: 9, 10, 11 (sidecar
bytes and keys) and 19-21's non-refusing halves.

WRITES. `tmp_path` only. `out/` is never read or written by this module: the
fixtures are a synthetic worker written into tmp from the source in this file
(a one-step FLASH, a 3-frame animation and a 2-level win — the observability
claim needs a transient that provably exists) plus the checked-in toy worker.
No API call, no network, no session: every capture is the real engine.

Run: .venv/bin/python -m pytest gen/tests/test_w3_trace.py -v -s
"""

from __future__ import annotations

import gzip
import hashlib
import inspect
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from gen import frames
from gen import orchestrator as orch
from gen.config import REPO_ROOT, load_config
from gen.orchestrator import SlotContext, default_runners

# --- what the contract names -------------------------------------------------

# "capture_worker ... additionally writes `worker.trace.jsonl.gz` beside the
# sidecar". The sidecar is `<worker-dir>.frames.json`, a SIBLING of the worker
# dir (orchestrator.FRAMES_SIDECAR_SUFFIX / s3_verify.FRAMES_SUFFIX), so the
# trace is the same derivation with the contract's own suffix — and for a worker
# dir named `worker`, which is what §2's tree names it, that is literally the
# file the contract writes down. Both spellings are checked below.
TRACE_SUFFIX = ".trace.jsonl.gz"
TRACE_NAME = "worker.trace.jsonl.gz"
SIDECAR_SUFFIX = ".frames.json"
WORKER_DIRNAME = "worker"
GAME_FILE = "game.py"

# The record fields the contract lists, and the two spellings of its frame slot.
RECORD_FIELDS = ("t", "action", "levels_completed", "state", "n_anim")
FRAME_KEY = "frame"
SAME_AS_PREV_KEY = "same_as_prev"

# The header line's one required field (contract part 2, the W2-C machinery).
PROVENANCE_FIELD = "source_sha256"

# The knob. `frames.trace` is the config spelling the contract writes down; how
# it reaches `gen/frames.py` is the implementer's business (the contract forbids
# this lane from editing the s2/s3 call sites, so a threaded flag is not even
# available to it), which is why the arming mechanism is DISCOVERED, not named.
KNOB_BLOCK, KNOB_KEY = "frames", "trace"
ON_WORDS = ("on", "true", "yes", "always", "1", "enabled", "record")
OFF_WORDS = ("off", "false", "no", "never", "0", "disabled")

# Environment spellings tried when neither a keyword nor a module flag arms the
# trace. Guesses, and treated as such: one is kept only if it actually flips the
# artifact, and none being found is reported, never asserted away.
ENV_CANDIDATES = ("GEN_FRAMES_TRACE", "FRAMES_TRACE", "GEN_TRACE", "ARC_FRAMES_TRACE")

# The canon default config: no wave-3 block, so it is what an UNCONFIGURED run
# reads (the house rule's "unconfigured runs byte-identical").
DEFAULT_CONFIG = "config/b001-pilot.yaml"
TEMPLATE_PATH = Path(REPO_ROOT) / "config" / "template.yaml"

GRID_SIZE = 64
HEX_DIGITS = "0123456789abcdef"

# --- the synthetic fixture ----------------------------------------------------
# A worker whose behaviour the pins can assert independently of any capture:
#
#   * ACTION5 paints `flash` (colour 6) and takes exactly ANIM_FRAMES engine
#     frames to complete; the NEXT action hides it again. So colour 6 lives in
#     exactly ONE step's settled board, is gone by the next one, and no level
#     transition happens there -> today's sidecar cannot hold it and a per-step
#     trace must. That is the observability claim, made falsifiable.
#   * a blocked move (into the top wall) repeats the previous board exactly ->
#     the `same_as_prev` dedup has something to dedup.
#   * two levels, won at the end -> one real transition record plus the final.
#
# Measured against HEAD before a line of this file was written: 23 solver
# actions; the sidecar keeps 4 records (reset, the two transitions, final) and
# colour 6 appears in none of them; n_anim is 3 at the ACTION5 step, 2 at the
# level transition, 1 everywhere else.

FLASH_COLOR = 6
ANIM_FRAMES = 3
SOLVER_ACTION_COUNT = 23

GAME_SRC = '''"""Synthetic worker (W3-A1 blind pins): a one-step flash, on an 8x8 board."""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

WALL, PLAYER, GOAL, FLASH = 4, 9, 12, 6
ANIM_FRAMES = 3

DIRS = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}


def _level():
    sprites = [
        Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
        Sprite([[WALL] * 8], name="wall_bottom", x=0, y=7),
        Sprite([[WALL]] * 6, name="wall_left", x=0, y=1),
        Sprite([[WALL]] * 6, name="wall_right", x=7, y=1),
        Sprite([[GOAL]], name="goal", x=6, y=6, layer=1, collidable=False),
        Sprite([[FLASH] * 3], name="flash", x=2, y=3, layer=3,
               collidable=False, visible=False),
        Sprite([[PLAYER]], name="player", x=1, y=1, layer=2),
    ]
    return Level(sprites=sprites)


class FlashToy(ARCBaseGame):
    """ACTION5 flashes for one action; ACTION1-4 move; reaching the goal levels up."""

    def __init__(self) -> None:
        super().__init__(
            game_id="w3-flash-toy",
            levels=[_level(), _level()],
            camera=Camera(width=8, height=8),
            available_actions=[1, 2, 3, 4, 5],
        )
        self._anim = 0

    def step(self) -> None:
        flash = self.current_level.get_sprites_by_name("flash")[0]
        if self.action.id is GameAction.ACTION5:
            self._anim += 1
            flash.set_visible(True)
            if self._anim >= ANIM_FRAMES:
                self.complete_action()
            return
        self._anim = 0
        flash.set_visible(False)
        delta = DIRS.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)
        self.complete_action()
        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
'''

SOLVER_SRC = '''"""Scripted solver for the synthetic flash worker (W3-A1 blind pins)."""

from arcengine import ActionInput, GameAction

PLANS = {
    0: ["ACTION5", "ACTION1", "ACTION1"] + ["ACTION4"] * 5 + ["ACTION2"] * 5,
    1: ["ACTION4"] * 5 + ["ACTION2"] * 5,
}


class Solver:
    def reset(self) -> None:
        self._cursor = {level: 0 for level in PLANS}

    def next_action(self, frame) -> "ActionInput | None":
        plan = PLANS.get(frame.levels_completed)
        if plan is None:
            return None
        index = self._cursor[frame.levels_completed]
        if index >= len(plan):
            return None
        self._cursor[frame.levels_completed] = index + 1
        return ActionInput(id=GameAction[plan[index]])
'''

TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"          # checked in: game.py + solver.py
IGNORE_CACHES = shutil.ignore_patterns("__pycache__", ".pytest_cache")

# The toy worker's sidecar, as HEAD writes it (`json.dumps(capture_to_json(cap),
# indent=2) + "\\n"` — s3_verify's own spelling). Taken from HEAD before this
# file existed: the contract's "the settled sidecar's bytes are UNCHANGED" is a
# number, not a promise, and this is the number.
TOY_SIDECAR_SHA256 = "a9d08e8b757be2ddea8ea564ef0a3cc59c3c7c7f0b17b56966093cb238184ea6"

# `FrameCapture`'s JSON keys as of HEAD (W2-C's eight plus the optional stamp).
# A trace is a NEW FILE; if any of its vocabulary leaks into the sidecar, the
# optionality the contract pins "hard" is gone.
SIDECAR_KEYS = (
    "game_id",
    "source",
    "records",
    "click_cells",
    "available_action_ids",
    "solver_actions",
    "levels_completed",
    "win",
)
SIDECAR_OPTIONAL_KEYS = (PROVENANCE_FIELD,)
SIDECAR_RECORD_KEYS = ("label", "seq", "levels_completed", "state", "grid")

# Invented names for the planted S4 slot: they give the tree the shape the state
# machine walks and name nothing that has ever been sampled or run.
BATCH_ID = "b-w3a1-fixture"
SLOT_SLUG = f"{BATCH_ID}-s001"
BOGUS_SHA = "0" * 64


# --- helpers: fixtures on disk ------------------------------------------------


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_flash_worker(parent: Path) -> Path:
    """The synthetic worker, at `<parent>/worker/` — the contract's own naming."""
    worker = parent / WORKER_DIRNAME
    worker.mkdir(parents=True, exist_ok=True)
    (worker / GAME_FILE).write_text(GAME_SRC, encoding="utf-8")
    (worker / "solver.py").write_text(SOLVER_SRC, encoding="utf-8")
    return worker


def _copy_toy_worker(parent: Path) -> Path:
    worker = parent / WORKER_DIRNAME
    shutil.copytree(TOY_WORKER, worker, ignore=IGNORE_CACHES)
    return worker


def _trace_path(worker: Path) -> Path:
    return worker.with_name(worker.name + TRACE_SUFFIX)


def _sidecar_path(worker: Path) -> Path:
    return worker.with_name(worker.name + SIDECAR_SUFFIX)


def _sidecar_text(cap: object) -> str:
    """The sidecar bytes as `gen/s3_verify.py` writes them (its one spelling)."""
    return json.dumps(frames.capture_to_json(cap), indent=2) + "\n"


def _gz_sightings(root: Path) -> list[str]:
    """Every trace-ish file anywhere under `root` — for failure messages only."""
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and ("trace" in path.name or path.suffix == ".gz")
    )


# --- helpers: the knob --------------------------------------------------------


@dataclass(frozen=True)
class _Mech:
    """One way of arming the trace, and the two values that flip it."""

    kind: str          # "param" | "attr" | "env"
    name: str
    on: object
    off: object

    @property
    def tag(self) -> str:
        return f"{self.kind}-{self.name}-{self.on!r}".replace("/", "_")

    def label(self) -> str:
        where = {"param": "keyword on capture_worker", "attr": "gen.frames attribute",
                 "env": "environment variable"}[self.kind]
        return f"{where} {self.name}={self.on!r} (off: {self.off!r})"


def _keyword_named_trace(func: object) -> str | None:
    """A keyword parameter of `func` whose name mentions the trace."""
    try:
        sig = inspect.signature(func)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    for name, param in sig.parameters.items():
        if "trace" in name.lower() and param.kind is not param.POSITIONAL_ONLY:
            return name
    return None


def _candidate_mechanisms() -> list[_Mech]:
    """Every arming mechanism worth trying, cheapest and most explicit first."""
    out: list[_Mech] = []

    keyword = _keyword_named_trace(frames.capture_worker)
    if keyword is not None:
        default = inspect.signature(frames.capture_worker).parameters[keyword].default
        if isinstance(default, str):
            out.append(_Mech("param", keyword, "on", "off"))
        else:
            out.append(_Mech("param", keyword, True, False))
            out.append(_Mech("param", keyword, "on", "off"))

    for name in sorted(dir(frames)):
        if name.startswith("_") or "TRACE" not in name.upper():
            continue
        value = getattr(frames, name)
        if isinstance(value, bool):
            out.append(_Mech("attr", name, True, False))
        elif isinstance(value, str) and value.lower() in ON_WORDS + OFF_WORDS:
            out.append(_Mech("attr", name, "on", "off"))

    for name in ENV_CANDIDATES:
        out.append(_Mech("env", name, "1", None))     # truthiness: unset is off
        out.append(_Mech("env", name, "on", "off"))
    return out


def _capture(worker: Path, mech: _Mech | None = None, *, on: bool = True,
             isolated: bool = False) -> object:
    """One capture of `worker`, with the trace armed / disarmed / left alone.

    Every environment candidate is cleared first, so the "unconfigured" probe is
    genuinely unconfigured whatever the shell carries.
    """
    fn = frames.capture_worker_isolated if isolated else frames.capture_worker
    with pytest.MonkeyPatch.context() as mp:
        for name in ENV_CANDIDATES:
            mp.delenv(name, raising=False)
        kwargs: dict = {}
        if mech is not None:
            value = mech.on if on else mech.off
            if mech.kind == "param":
                if _keyword_named_trace(fn) != mech.name:
                    raise LookupError(f"{fn.__name__} has no {mech.name!r} keyword")
                kwargs[mech.name] = value
            elif mech.kind == "attr":
                mp.setattr(frames, mech.name, value)
            elif mech.kind == "env":
                if value is None:
                    mp.delenv(mech.name, raising=False)
                else:
                    mp.setenv(mech.name, str(value))
        return fn(worker, **kwargs)


# --- helpers: reading a trace -------------------------------------------------


class _BadTrace(ValueError):
    """The trace on disk is not the artifact the contract describes."""


def _read_objects(path: Path) -> list[dict]:
    """The gzipped JSONL, one dict per line — or `_BadTrace` saying why not."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise _BadTrace(
            f"{path.name} is not readable as gzip ({type(exc).__name__}: {exc}). The contract "
            "names the artifact `worker.trace.jsonl.gz`, in the officials' format family — "
            "theirs are gzipped JSONL"
        ) from exc
    objects = []
    for index, line in enumerate(text.splitlines()):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _BadTrace(f"{path.name} line {index + 1} is not JSON ({exc}): {line[:120]!r}")
        if not isinstance(obj, dict):
            raise _BadTrace(f"{path.name} line {index + 1} is a {type(obj).__name__}, not an "
                            "object — one JSONL record per step")
        objects.append(obj)
    if not objects:
        raise _BadTrace(f"{path.name} decoded to no records at all")
    return objects


def _split_header(objects: list[dict]) -> tuple[dict | None, list[dict]]:
    """(header, records). A first line carrying no `t` is the header line."""
    first = objects[0]
    if "t" not in first:
        return first, objects[1:]
    return None, objects


def _decode_frame(value: object) -> tuple[tuple[int, ...], ...]:
    """A trace frame -> an int grid. Tolerant: the ENCODING is pinned separately.

    Hex rows are the officials' spelling (and `frames._hex_row`'s); a list of int
    rows, or one string of rows, decode too, so a frame written some other way
    still gets measured for CONTENT instead of failing every pin at once.
    """
    rows: object = value
    if isinstance(rows, str):
        rows = [row for row in rows.replace(",", "\n").split("\n") if row]
    if not isinstance(rows, (list, tuple)) or not rows:
        raise _BadTrace(f"a record's {FRAME_KEY} is {type(value).__name__}, not a grid: "
                        f"{str(value)[:120]!r}")
    grid: list[tuple[int, ...]] = []
    for row in rows:
        if isinstance(row, str):
            lowered = row.lower()
            if not lowered or any(char not in HEX_DIGITS for char in lowered):
                raise _BadTrace(f"frame row {row[:80]!r} is not hex")
            grid.append(tuple(int(char, 16) for char in lowered))
        elif isinstance(row, (list, tuple)):
            grid.append(tuple(int(cell) for cell in row))
        else:
            raise _BadTrace(f"frame row is a {type(row).__name__}")
    return tuple(grid)


def _is_hex_rows(value: object) -> bool:
    """The officials' encoding exactly: 64 strings of 64 hex digits."""
    return (
        isinstance(value, (list, tuple))
        and len(value) == GRID_SIZE
        and all(
            isinstance(row, str)
            and len(row) == GRID_SIZE
            and all(char in HEX_DIGITS for char in row.lower())
            for row in value
        )
    )


def _trace_grids(records: list[dict]) -> list[tuple[tuple[int, ...], ...]]:
    """Every record's settled board, `same_as_prev` resolved against the last."""
    grids = []
    previous = None
    for index, record in enumerate(records):
        if record.get(FRAME_KEY) is not None:
            grid = _decode_frame(record[FRAME_KEY])
        elif record.get(SAME_AS_PREV_KEY):
            if previous is None:
                raise _BadTrace(f"record {index} says {SAME_AS_PREV_KEY} with no previous frame")
            grid = previous
        else:
            raise _BadTrace(
                f"record {index} carries neither {FRAME_KEY} nor {SAME_AS_PREV_KEY}: "
                f"{sorted(record)}"
            )
        grids.append(grid)
        previous = grid
    return grids


def _match_subsequence(needles: list, haystack: list) -> tuple[list[int] | None, int]:
    """Greedy subsequence match; returns (indices, first unmatched needle).

    Two IDENTICAL consecutive needles may match one haystack element: the
    sidecar's last two records are the winning transition and `final`, which are
    the same board recorded twice for two different reasons, and a trace that
    stepped once is not wrong for holding it once.
    """
    at = -1
    hits: list[int] = []
    for index, needle in enumerate(needles):
        start = at if index and needles[index - 1] == needle else at + 1
        found = next(
            (j for j in range(max(start, 0), len(haystack)) if haystack[j] == needle), None
        )
        if found is None:
            return None, index
        at = found
        hits.append(found)
    return hits, -1


def _has_color(grid: tuple[tuple[int, ...], ...], color: int) -> bool:
    return any(color in row for row in grid)


# --- module fixtures ----------------------------------------------------------


@pytest.fixture(scope="module")
def default_cfg() -> dict:
    return load_config(DEFAULT_CONFIG)


@pytest.fixture(scope="module")
def knob(tmp_path_factory) -> SimpleNamespace:
    """The trace knob, DISCOVERED: what an unconfigured run does, and what flips it.

    The contract hands the implementer the default ("state your choice") and this
    file refuses to guess it: the unconfigured behaviour is MEASURED, then every
    arming mechanism the house uses is tried until one produces the artifact in
    one branch and not in the other. Nothing here asserts — the pins below do,
    so a missing knob fails as a PIN with the contract quoted, not as a fixture
    error with a traceback.
    """
    root = tmp_path_factory.mktemp("w3-knob")

    unconfigured = _write_flash_worker(root / "unconfigured")
    default_cap = _capture(unconfigured)
    default_on = _trace_path(unconfigured).is_file()

    mech: _Mech | None = None
    tried: list[str] = []
    for candidate in _candidate_mechanisms():
        try:
            on_worker = _write_flash_worker(root / f"on-{candidate.tag}")
            _capture(on_worker, candidate, on=True)
            off_worker = _write_flash_worker(root / f"off-{candidate.tag}")
            _capture(off_worker, candidate, on=False)
        except Exception as exc:  # noqa: BLE001 — a mechanism that raises is just not one
            tried.append(f"{candidate.label()}: raised {type(exc).__name__}: {exc}")
            continue
        on_present = _trace_path(on_worker).is_file()
        off_present = _trace_path(off_worker).is_file()
        tried.append(f"{candidate.label()}: armed->{on_present}, disarmed->{off_present}")
        if on_present and not off_present:
            mech = candidate
            break

    found = SimpleNamespace(
        default_on=default_on,
        mech=mech,
        tried=tried,
        sightings=_gz_sightings(root),
        default_sidecar=_sidecar_text(default_cap),
    )
    print(
        "\n[W3-A1 discovery] frames.trace DEFAULT (unconfigured capture_worker): "
        f"{'ON — the trace is written' if default_on else 'OFF — no trace written'}"
        f"\n[W3-A1 discovery] arming mechanism: "
        f"{mech.label() if mech else 'NONE FOUND'}"
        "\n[W3-A1 discovery] mechanisms tried:\n  " + "\n  ".join(tried or ["(none)"])
        + f"\n[W3-A1 discovery] trace-ish files seen: {found.sightings or '(none)'}\n"
    )
    return found


def _armed_state(root: Path, knob: SimpleNamespace) -> SimpleNamespace:
    """One ARMED capture of the synthetic worker, parsed as far as it will go."""
    worker = _write_flash_worker(root)
    mech = None if knob.default_on else knob.mech
    cap = None
    error = None
    try:
        cap = _capture(worker, mech, on=True)
    except Exception as exc:  # noqa: BLE001 — how a capture fails is itself evidence
        error = f"{type(exc).__name__}: {exc}"
    path = _trace_path(worker)
    state = SimpleNamespace(
        root=root, worker=worker, cap=cap, capture_error=error, path=path,
        exists=path.is_file(), objects=None, header=None, records=None,
        grids=None, parse_error=None, sightings=_gz_sightings(root),
        mech=mech, knob=knob,
    )
    if state.exists:
        try:
            state.objects = _read_objects(path)
            state.header, state.records = _split_header(state.objects)
            state.grids = _trace_grids(state.records)
        except _BadTrace as exc:
            state.parse_error = str(exc)
    return state


@pytest.fixture(scope="module")
def armed(tmp_path_factory, knob) -> SimpleNamespace:
    """The shared armed capture. READ-ONLY: a test that mutates what it captured
    takes its own (`_armed_state`), because module scope means the next test is
    looking at the same files."""
    return _armed_state(tmp_path_factory.mktemp("w3-armed"), knob)


def _armed_or_fail(state: SimpleNamespace) -> SimpleNamespace:
    """The armed capture, or the contract's own words about why there is none."""
    if state.capture_error is not None:
        pytest.fail(
            f"the armed capture itself failed: {state.capture_error}. A1 part 1 adds a trace "
            "to `capture_worker`; it may not break the capture that carries it"
        )
    if not state.exists:
        pytest.fail(
            f"no trace at {state.path}. A1 part 1: 'capture_worker (and therefore _isolated) "
            f"additionally writes `{TRACE_NAME}` beside the sidecar — one JSONL record per "
            "step()'. Arming used: "
            f"{state.mech.label() if state.mech else 'the default (no knob needed)'}. "
            f"Files written next to / under the worker: {state.sightings or '(none)'}. "
            f"Knob discovery: default_on={state.knob.default_on}, mechanisms tried: "
            + "; ".join(state.knob.tried)
        )
    return state


def _records_or_fail(state: SimpleNamespace) -> list[dict]:
    state = _armed_or_fail(state)
    if state.parse_error is not None:
        pytest.fail(f"the trace is on disk but unreadable: {state.parse_error}")
    return state.records


# =============================================================================
# PART 1 — the artifact exists, where and as the contract says (pins 1-8)
# =============================================================================


def test_1_trace_is_written_beside_the_sidecar(armed):
    """Pin 1. `worker.trace.jsonl.gz`, a SIBLING of the worker dir, exactly as
    the sidecar is — same parent, same stem, the contract's own suffix."""
    state = _armed_or_fail(armed)

    assert state.path.name == TRACE_NAME, f"internal: {state.path.name}"
    assert state.path.parent == _sidecar_path(state.worker).parent, (
        f"the trace landed in {state.path.parent} but the sidecar lives in "
        f"{_sidecar_path(state.worker).parent}; 'beside the sidecar' is one directory"
    )
    assert state.path.stat().st_size > 0, f"{state.path} is empty"


def test_2_trace_is_gzipped_jsonl(armed):
    """Pin 1's format half: gzip, one JSON OBJECT per line (the officials')."""
    state = _armed_or_fail(armed)
    if state.parse_error is not None:
        pytest.fail(state.parse_error)

    assert state.path.read_bytes()[:2] == b"\x1f\x8b", (
        f"{state.path.name} does not start with the gzip magic bytes, although the contract "
        "names a `.jsonl.gz` in the officials' format family"
    )
    assert len(state.objects) >= 2, (
        f"{state.path.name} holds {len(state.objects)} line(s); the contract wants a header "
        "line plus one record per step()"
    )


def test_3_header_line_carries_the_source_sha256(armed):
    """Pin 1's provenance half (contract part 2): 'the trace carries
    source_sha256 (reuse the W2-C machinery) in a header line'."""
    state = _armed_or_fail(armed)
    if state.parse_error is not None:
        pytest.fail(state.parse_error)
    expected = _sha256_file(state.worker / GAME_FILE)

    if state.header is None:
        carriers = [i for i, obj in enumerate(state.objects) if PROVENANCE_FIELD in obj]
        pytest.fail(
            f"{state.path.name}'s first line is already a step record ({sorted(state.objects[0])}"
            f"), so there is no header line. The contract puts {PROVENANCE_FIELD} 'in a header "
            f"line'. Lines carrying the field: {carriers or 'none'}"
        )
    recorded = state.header.get(PROVENANCE_FIELD)
    assert isinstance(recorded, str) and expected in recorded, (
        f"the header records {PROVENANCE_FIELD}={recorded!r}; the W2-C machinery hashes the "
        f"game.py the capture imported, which is {expected} for {state.worker / GAME_FILE}. "
        "A trace that cannot say which source rendered it re-opens exactly the R-21 hole the "
        "sidecar's stamp closed"
    )
    sidecar_stamp = getattr(state.cap, PROVENANCE_FIELD, None)
    assert isinstance(sidecar_stamp, str) and sidecar_stamp in recorded, (
        f"the trace's header says {recorded!r} and the sidecar says {sidecar_stamp!r} about the "
        "SAME capture. Both are the W2-C stamp of the same game.py; two artifacts of one replay "
        "that disagree about their source are worse than one artifact that stays silent"
    )


def test_4_every_record_carries_the_named_fields(armed):
    """Pin 1's record shape: `{t, action, levels_completed, state, n_anim,
    frame|same_as_prev}` — the five always, the frame slot exactly once."""
    records = _records_or_fail(armed)

    missing = [
        (index, [field for field in RECORD_FIELDS if field not in record])
        for index, record in enumerate(records)
    ]
    missing = [(index, fields) for index, fields in missing if fields]
    assert not missing, (
        f"{len(missing)} record(s) are missing contract fields, first: record {missing[0][0]} "
        f"lacks {missing[0][1]} (it carries {sorted(records[missing[0][0]])}). The contract "
        f"lists {list(RECORD_FIELDS)} on every record"
    )
    both, neither = [], []
    for index, record in enumerate(records):
        has_frame = record.get(FRAME_KEY) is not None
        has_same = bool(record.get(SAME_AS_PREV_KEY))
        if has_frame and has_same:
            both.append(index)
        if not has_frame and not has_same:
            neither.append(index)
    assert not both and not neither, (
        f"the frame slot is `{FRAME_KEY}|{SAME_AS_PREV_KEY}` — one or the other. Records with "
        f"both: {both[:5]}; with neither: {neither[:5]}"
    )
    states = {record["state"] for record in records}
    assert states <= {"NOT_FINISHED", "WIN", "GAME_OVER"}, (
        f"records report state(s) {sorted(states)}; the engine's GameState names are what the "
        "sidecar already records and what a shared decoder expects"
    )
    assert records[-1]["state"] == "WIN" and records[-1]["levels_completed"] == 2, (
        f"the synthetic worker wins its 2 levels; the last record says state="
        f"{records[-1]['state']!r} levels_completed={records[-1]['levels_completed']!r}"
    )


def test_5_frames_are_hex_rows_in_the_officials_encoding(armed):
    """Pin 1's encoding: 'hex-row frame encoding like theirs, so one decoder
    serves both corpora' — 64 strings of 64 hex digits, as `out/frames/*` are."""
    records = _records_or_fail(armed)

    framed = [record for record in records if record.get(FRAME_KEY) is not None]
    assert framed, f"no record carries a {FRAME_KEY} at all"
    bad = [index for index, record in enumerate(framed) if not _is_hex_rows(record[FRAME_KEY])]
    if bad:
        sample = framed[bad[0]][FRAME_KEY]
        shape = (f"{type(sample).__name__} of {len(sample)}" if isinstance(sample, (list, tuple))
                 else type(sample).__name__)
        pytest.fail(
            f"{len(bad)}/{len(framed)} frames are not the officials' hex rows (first is a "
            f"{shape}: {str(sample)[:120]!r}). The contract asks for 'hex-row frame encoding "
            "like theirs, so one decoder serves both corpora' — the officials' trace.jsonl.gz "
            f"writes {GRID_SIZE} strings of {GRID_SIZE} hex digits, which is `frames._hex_row` "
            "exactly. (If a different encoding was chosen deliberately, this is one for the "
            "lead: the one-decoder claim is the contract's stated reason for the format.)"
        )


def test_6_one_record_per_step(armed):
    """Pin 1's granularity: 'one JSONL record per step()'. The synthetic worker
    plays 23 actions after RESET, so the trace covers 24 steps — against a
    sidecar that keeps 4 records. That gap IS the contract."""
    state = _armed_or_fail(armed)
    records = _records_or_fail(armed)
    expected = len(state.cap.solver_actions) + 1     # RESET + one per action

    assert len(state.cap.solver_actions) == SOLVER_ACTION_COUNT, (
        f"fixture drift: the synthetic solver played {len(state.cap.solver_actions)} actions, "
        f"not {SOLVER_ACTION_COUNT}"
    )
    assert len(records) >= expected, (
        f"the trace holds {len(records)} record(s) for {expected} step(s) (RESET + "
        f"{len(state.cap.solver_actions)} solver actions). 'One JSONL record per step()' is the "
        "whole capture-scope upgrade; a trace that samples is the sidecar with extra steps"
    )
    ticks = [record["t"] for record in records]
    assert all(isinstance(tick, int) and not isinstance(tick, bool) for tick in ticks), (
        f"`t` must be the step index; got {ticks[:8]}"
    )
    assert ticks == sorted(ticks), f"`t` runs backwards somewhere: {ticks[:12]}"
    distinct = sorted(set(ticks))
    assert distinct == list(range(distinct[0], distinct[0] + len(distinct))), (
        f"`t` skips steps: {distinct}. Every step() the capture drove must have a record "
        "(extra records at a level start are fine — gaps are not)"
    )
    assert len(distinct) >= expected, (
        f"the trace names {len(distinct)} distinct step(s) for {expected} steps: {distinct}"
    )
    completed = [record["levels_completed"] for record in records]
    assert completed == sorted(completed) and completed[-1] == 2, (
        f"levels_completed must ratchet 0->1->2 across the run; got {completed}"
    )


def test_7_n_anim_counts_the_frames_the_engine_returned(armed):
    """Pin 1's sc25 half: 'n_anim = the number of frames the engine returned for
    the step (fd.frame length)'. Measured, not trusted: the synthetic worker's
    ACTION5 takes exactly 3 engine frames and its level transition takes 2,
    while every other step takes 1."""
    records = _records_or_fail(armed)
    state = armed
    grids = state.grids

    n_anims = [record["n_anim"] for record in records]
    assert all(isinstance(value, int) and not isinstance(value, bool) and value >= 1
               for value in n_anims), (
        f"n_anim must be a frame COUNT (>=1) on every record; got {n_anims[:12]}"
    )
    flash_steps = [index for index, grid in enumerate(grids) if _has_color(grid, FLASH_COLOR)]
    assert flash_steps, (
        "the synthetic worker's flash step is missing from the trace entirely — pin 13 says "
        "more about that"
    )
    assert n_anims[flash_steps[0]] == ANIM_FRAMES, (
        f"the flash step reports n_anim={n_anims[flash_steps[0]]}; the engine returned "
        f"{ANIM_FRAMES} frames for it (the game withholds complete_action() for "
        f"{ANIM_FRAMES} step() calls). n_anim is the ONLY record of the frames a settled "
        "capture throws away — an n_anim that is always 1 cannot exclude the sc25 class"
    )
    transitions = [
        index for index in range(1, len(records))
        if records[index]["levels_completed"] > records[index - 1]["levels_completed"]
    ]
    assert transitions, "no level transition in the trace, although the worker wins 2 levels"
    assert n_anims[transitions[0]] >= 2, (
        f"the level-transition step reports n_anim={n_anims[transitions[0]]}; the engine renders "
        "the incoming level in an extra frame there (base_game's `_really_set_next_level` pass), "
        "so a transition is exactly where a settled-only capture loses a board"
    )
    assert any(value == 1 for value in n_anims), (
        f"every step reports n_anim={set(n_anims)}; a plain move returns ONE frame, so a "
        "constant n_anim is not reading fd.frame at all"
    )


def test_8_same_as_prev_dedupes_a_repeated_board(armed):
    """Pin 1's dedup, the officials' own ('settled frame (hex rows, deduped via
    same_as_prev)'). The synthetic worker walks into a wall at t=3, repeating
    t=2's board exactly."""
    records = _records_or_fail(armed)
    grids = armed.grids

    repeats = [index for index in range(1, len(grids)) if grids[index] == grids[index - 1]]
    assert repeats, "fixture drift: no repeated board in the run, so dedup cannot be measured"
    deduped = [index for index in repeats if records[index].get(SAME_AS_PREV_KEY)]
    assert deduped, (
        f"records {repeats} repeat the previous board and every one of them writes a full "
        f"{FRAME_KEY}. The contract's record slot is `{FRAME_KEY}|{SAME_AS_PREV_KEY}` and the "
        "officials dedup there — it is what keeps a per-step trace affordable. (If writing "
        "every frame was a deliberate call, this is one for the lead to rule on.)"
    )
    for index in deduped:
        assert grids[index] == grids[index - 1], (
            f"record {index} says {SAME_AS_PREV_KEY} but its resolved board differs from "
            f"record {index - 1}'s"
        )


# =============================================================================
# PART 2 — the sidecar is untouched, and nothing requires the trace (pins 9-11)
# =============================================================================


def test_9_the_sidecar_gains_no_trace_vocabulary(armed):
    """Pin 2. 'The settled sidecar's bytes are UNCHANGED (all existing
    byte-stability + hotfix8 + provenance pins are the harness).' A new FILE is
    the contract; a new KEY in the old file is not."""
    state = _armed_or_fail(armed)
    payload = frames.capture_to_json(state.cap)

    assert tuple(payload) == SIDECAR_KEYS + SIDECAR_OPTIONAL_KEYS, (
        f"the sidecar now serializes {tuple(payload)}; HEAD wrote "
        f"{SIDECAR_KEYS + SIDECAR_OPTIONAL_KEYS}. The trace is a NEW artifact file — no part of "
        "it may land in the file every existing byte pin measures"
    )
    for index, record in enumerate(payload["records"]):
        assert tuple(record) == SIDECAR_RECORD_KEYS, (
            f"sidecar record {index} serializes {tuple(record)}, HEAD wrote "
            f"{SIDECAR_RECORD_KEYS} (an n_anim or t that leaked in here changes every "
            "shipped sidecar's bytes)"
        )


def test_10_toy_sidecar_bytes_are_byte_identical_to_head(tmp_path, knob):
    """Pin 2's number: the checked-in toy worker's sidecar, digest-pinned from
    HEAD, in EVERY mode of the knob (armed, disarmed, unconfigured)."""
    modes: dict[str, str] = {}
    plans = [("unconfigured", None, True)]
    if knob.mech is not None:
        plans += [("armed", knob.mech, True), ("disarmed", knob.mech, False)]
    for label, mech, on in plans:
        worker = _copy_toy_worker(tmp_path / label)
        modes[label] = _sidecar_text(_capture(worker, mech, on=on))

    for label, text in modes.items():
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert digest == TOY_SIDECAR_SHA256, (
            f"the toy worker's sidecar hashes to {digest} in mode {label!r}; at HEAD it hashed "
            f"to {TOY_SIDECAR_SHA256}. The contract pins the settled sidecar's bytes UNCHANGED, "
            "and every b7/hotfix8/W2-C byte pin in this suite is the harness for that claim. "
            "(If gen/tests/toy_worker/ itself was edited, this digest is stale — say so rather "
            "than re-blessing it.)"
        )
    assert len(set(modes.values())) == 1, (
        f"the sidecar's bytes differ between knob modes {sorted(modes)}. The trace may not "
        "change what the settled capture writes, in either direction"
    )


def test_11_no_reader_requires_the_trace(tmp_path, knob):
    """Pin 2's other half: 'no reader anywhere REQUIRES the trace.' Delete it and
    every sidecar consumer must behave exactly as it did before this contract.

    Its OWN capture: this pin deletes the artifact, and the module-scoped one is
    still being measured by the pins after it."""
    state = _armed_or_fail(_armed_state(tmp_path, knob))
    sidecar = _sidecar_path(state.worker)
    sidecar.write_text(_sidecar_text(state.cap), encoding="utf-8")
    state.path.unlink()

    reloaded = frames.capture_from_json(json.loads(sidecar.read_text(encoding="utf-8")))
    assert _sidecar_text(reloaded) == _sidecar_text(state.cap), (
        "the sidecar does not round-trip once the trace is gone"
    )
    assert frames.digest_text(reloaded), "digest_text failed without a trace beside the sidecar"
    provenance = orch.frames_provenance(state.worker)
    assert provenance["status"] == orch.PROVENANCE_MATCH, (
        f"frames_provenance says {provenance['status']!r} ({provenance['note']}) for a sidecar "
        "whose trace was deleted; the guard reads the SIDECAR's stamp and must not have "
        "acquired a dependency on the new file"
    )


# =============================================================================
# PART 3 — what the trace is FOR (pins 12-13)
# =============================================================================


def test_12_sidecar_records_are_a_subsequence_of_the_trace(armed):
    """Pin 3. 'The trace's settled frames reproduce the sidecar records as a
    subsequence (decode + compare)' — the two artifacts describe ONE replay, so
    a decoder that trusts the trace can never contradict the sidecar."""
    state = _armed_or_fail(armed)
    if state.parse_error is not None:
        pytest.fail(state.parse_error)
    sidecar_grids = [record.grid for record in state.cap.records]

    hits, unmatched = _match_subsequence(sidecar_grids, state.grids)
    if hits is None:
        label = state.cap.records[unmatched].label
        pytest.fail(
            f"sidecar record {unmatched} ({label!r}, levels_completed="
            f"{state.cap.records[unmatched].levels_completed}) has no matching board in the "
            f"trace, in order. Sidecar records: "
            f"{[record.label for record in state.cap.records]}; trace steps: {len(state.grids)}. "
            "The trace must SUPERSET the sidecar: every settled frame the sidecar kept was "
            "returned by a step the trace also recorded, so recording frame[0], a pre-step "
            "board, or a different level's board breaks the shared-replay claim"
        )
    assert hits == sorted(hits), f"internal: subsequence indices out of order {hits}"


def test_13_a_one_frame_transient_is_in_the_trace_and_not_the_sidecar(armed):
    """Pin 4, the observability claim itself. The synthetic worker paints colour
    6 for exactly one step, with no level transition there — the shape of every
    refusal flash, CHARGING state and crush flash the audit found to be
    code-only. It must be IN the trace and ABSENT from the sidecar."""
    state = _armed_or_fail(armed)
    if state.parse_error is not None:
        pytest.fail(state.parse_error)

    sidecar_hits = [
        record.label for record in state.cap.records if _has_color(record.grid, FLASH_COLOR)
    ]
    assert not sidecar_hits, (
        f"fixture drift: the settled sidecar already holds the flash ({sidecar_hits}), so this "
        "worker no longer demonstrates anything. The flash must fall between the frames the "
        "sidecar keeps (reset / level transition / final)"
    )
    trace_hits = [index for index, grid in enumerate(state.grids)
                  if _has_color(grid, FLASH_COLOR)]
    assert trace_hits, (
        f"colour {FLASH_COLOR} is painted by exactly one step of this worker and appears in NO "
        f"trace record. That transient is the contract's whole subject: 'our sidecars keep "
        "frame[-1] only, so every transient is code-only'. A trace that cannot show a "
        "one-step flash has not widened the capture scope at all"
    )
    assert len(trace_hits) == 1, (
        f"the flash shows up at trace steps {trace_hits}; it is painted for ONE action. More "
        "than one sighting means the frames are misaligned with the steps that produced them"
    )
    assert state.records[trace_hits[0]]["levels_completed"] == 0, (
        "the flash step is inside level 1, before any transition — that is precisely why the "
        "sidecar cannot hold it"
    )


# =============================================================================
# PART 4 — the knob, both branches, and the default the implementer chose
#          (pins 14-18)
# =============================================================================


def test_14_the_knob_reaches_both_branches(knob):
    """Pin 5. 'A knob `frames.trace` on|off — decide the DEFAULT yourself.' The
    default is the implementer's; the EXISTENCE of both branches is not."""
    if knob.mech is None:
        pytest.fail(
            "no arming mechanism turns the trace on in one branch and off in the other. The "
            "contract requires a knob `frames.trace` on|off whichever way the default went "
            f"(measured default: {'ON' if knob.default_on else 'OFF'}).\nTried:\n  "
            + "\n  ".join(knob.tried)
            + "\nIf the knob is spelled somewhere this could not reach (a config-only path "
            "through the orchestrator, say), name the seam and this pin becomes one line."
        )
    print(f"[W3-A1] knob honoured through: {knob.mech.label()}")


def test_15_the_documented_default_matches_what_an_unconfigured_run_does(knob):
    """Pin 5's default half, discovered and RECORDED. The contract lets either
    choice stand; what it does not let stand is a default nobody can name."""
    template = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    block = template.get(KNOB_BLOCK) if isinstance(template, dict) else None
    armed_in_template = isinstance(block, dict) and KNOB_KEY in block
    value = block.get(KNOB_KEY) if armed_in_template else None

    in_template = (
        f"{KNOB_BLOCK}.{KNOB_KEY} = {value!r}" if armed_in_template
        else f"no {KNOB_BLOCK}.{KNOB_KEY} block"
    )
    print(f"[W3-A1] DEFAULT = {'on' if knob.default_on else 'off'}; "
          f"config/template.yaml carries {in_template}")
    assert armed_in_template, (
        f"config/template.yaml carries no `{KNOB_BLOCK}.{KNOB_KEY}`. The wave's house rule is "
        "that template.yaml is where a new knob is armed, and the contract says so again for "
        f"this one ('template.yaml arms on if you default off'). Measured default: "
        f"{'ON' if knob.default_on else 'OFF'}"
    )
    spelling = str(value).strip().lower()
    assert spelling in ON_WORDS + OFF_WORDS, (
        f"{KNOB_BLOCK}.{KNOB_KEY} = {value!r} in config/template.yaml is neither an on nor an "
        f"off spelling ({list(ON_WORDS + OFF_WORDS)})"
    )
    if not knob.default_on:
        assert spelling in ON_WORDS, (
            f"the default is OFF and config/template.yaml sets {KNOB_BLOCK}.{KNOB_KEY}="
            f"{value!r}. The contract: 'template.yaml arms on if you default off' — otherwise "
            "no configured run ever writes the artifact this contract exists to produce"
        )


def test_16_the_isolated_leg_agrees_with_the_in_process_leg(tmp_path, knob):
    """Pin 5's process boundary: 'capture_worker (and THEREFORE _isolated)'. The
    isolated leg is the one S2b, the gate and S4 actually call, so a trace only
    the in-process leg writes is a trace no run ever produces."""
    in_process = _write_flash_worker(tmp_path / "in-process")
    isolated = _write_flash_worker(tmp_path / "isolated")
    # A module-level flag cannot reach a fresh interpreter; a keyword the CLI
    # also takes, and an environment variable, both can.
    crossing = knob.mech is not None and (
        knob.mech.kind == "env"
        or (knob.mech.kind == "param"
            and _keyword_named_trace(frames.capture_worker_isolated) == knob.mech.name)
    )
    mech = knob.mech if (crossing and not knob.default_on) else None

    _capture(in_process, mech, on=True)
    try:
        _capture(isolated, mech, on=True, isolated=True)
    except LookupError:
        _capture(isolated, None, isolated=True)
        mech = None

    here, there = _trace_path(in_process).is_file(), _trace_path(isolated).is_file()
    assert there == here, (
        f"the in-process leg {'wrote' if here else 'wrote no'} trace and the isolated leg "
        f"{'wrote' if there else 'wrote none'}, under the same arming "
        f"({mech.label() if mech else 'the default'}). The contract makes the isolated leg "
        "follow: 'capture_worker (and therefore _isolated) additionally writes ...', and the "
        "child is a CLI over the same function precisely so the two legs cannot drift"
    )
    if here:
        first = _read_objects(_trace_path(in_process))
        second = _read_objects(_trace_path(isolated))
        assert len(first) == len(second), (
            f"the two legs traced the same worker to {len(first)} and {len(second)} records; "
            "both drive the identical replay"
        )
    else:
        print("[W3-A1] isolated-leg check ran in the DISARMED branch (no process-crossing knob "
              "was discovered): agreement pinned, armed child not reachable from here")


def test_17_an_armed_capture_writes_only_beside_the_worker(armed):
    """Pin 5's blast radius: an armed capture writes beside the worker it was
    handed and nowhere else — no second tree, no out/, no repo-relative dump."""
    state = _armed_or_fail(armed)
    written = _gz_sightings(state.root)

    assert written, "internal: an armed capture wrote nothing"
    for name in written:
        assert not Path(name).is_absolute(), f"internal: {name}"
    assert all(name.startswith(WORKER_DIRNAME) for name in written), (
        f"an armed capture wrote {written} under the tmp root; everything it writes belongs "
        f"beside the worker dir it was handed ({TRACE_NAME})"
    )


def test_18_a_bad_knob_value_is_loud(knob):
    """The wave's common rule: 'invalid knob values are loud ValueErrors read
    before work.' The reader's NAME is the implementer's, so it is discovered —
    and if the knob has no cfg reader at all, the pin falls back to requiring
    that the knob is at least reachable (test 14's mechanism)."""
    readers = {}
    for module in (frames, orch):
        for name in dir(module):
            if name.startswith("__") or "trace" not in name.lower():
                continue
            candidate = getattr(module, name)
            if not callable(candidate) or isinstance(candidate, type):
                continue
            try:
                sig = inspect.signature(candidate)
            except (TypeError, ValueError):
                continue
            required = [
                param for param in sig.parameters.values()
                if param.default is param.empty
                and param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
            ]
            if len(required) == 1:
                readers[f"{module.__name__}.{name}"] = candidate

    if not readers:
        print("[W3-A1] no cfg reader for frames.trace was discoverable in gen.frames / "
              "gen.orchestrator — the loud-value rule is unmeasured here (lead: adjudicate)")
        assert knob.mech is not None or knob.default_on, (
            "the trace has neither a discoverable config reader nor a working knob"
        )
        return

    bad_cfg = {KNOB_BLOCK: {KNOB_KEY: "banana"}}
    verdicts = {}
    for name, reader in readers.items():
        try:
            verdicts[name] = f"returned {reader(bad_cfg)!r}"
        except ValueError as exc:
            verdicts[name] = f"ValueError: {exc}"
        except Exception as exc:  # noqa: BLE001 — the point is WHICH exception
            verdicts[name] = f"{type(exc).__name__}: {exc}"
    print(f"[W3-A1] cfg readers found: {verdicts}")
    assert any(verdict.startswith("ValueError") for verdict in verdicts.values()), (
        f"no discovered reader rejects {KNOB_BLOCK}.{KNOB_KEY}='banana' with a ValueError: "
        f"{verdicts}. The wave's common rule makes an invalid knob value a loud ValueError read "
        "before work, so a typo cannot silently disable the artifact"
    )


# =============================================================================
# PART 5 — W2-C residual (a): the S4 provenance ask (pins 19-21)
# =============================================================================


def _plant_s4_slot(root: Path, cfg: dict, *, provenance: str | None) -> SimpleNamespace:
    """A §2 slot at `gated`, with the synthetic worker and a real sidecar.

    `provenance=None` is the pre-R-21 file (no stamp at all — the seven shipped
    games); `"MATCH"` is an honest fresh capture; anything else is the incident:
    a sidecar rendered from some other source.
    """
    corpus_dir = root / "corpus" / BATCH_ID
    spec_dir = corpus_dir / "w3-flash-slot"
    spec_dir.mkdir(parents=True)
    worker = _write_flash_worker(spec_dir)
    payload = frames.capture_to_json(frames.capture_worker(worker))
    if provenance is None:
        payload.pop(PROVENANCE_FIELD, None)
    elif provenance != "MATCH":
        payload[PROVENANCE_FIELD] = provenance
    sidecar = _sidecar_path(worker)
    sidecar.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    ideas_dir = root / "ideas" / BATCH_ID
    ideas_dir.mkdir(parents=True)
    ctx = SlotContext(
        cfg=cfg, batch_id=BATCH_ID, slug=SLOT_SLUG, index=1, state="gated",
        stage="s4_baselines", attempt=1, batch_dir=root / "batch", ideas_dir=ideas_dir,
        idea_path=ideas_dir / "idea-001.json", corpus_dir=corpus_dir, spec_dir=spec_dir,
        respec_count=0, verifier_rejects=0, green_failures=0,
    )
    return SimpleNamespace(spec_dir=spec_dir, worker=worker, sidecar=sidecar, ctx=ctx)


def _run_s4(root: Path, cfg: dict, *, provenance: str | None) -> SimpleNamespace:
    """The real `s4_baselines` runner over a planted slot, S4's own burn-probe
    subprocess stubbed to a FIT verdict.

    The stub is the only way to ask this question in milliseconds, and it is
    honest about the seam: whether the provenance ask sits before or after the
    S4 run (the contract only says 'before `_post_s4_level_floor` consumes the
    sidecar'), the stage still has to route the mismatch. Whether the stub was
    reached is reported, never pinned.
    """
    from gen import s4_baselines as s4

    slot = _plant_s4_slot(root, cfg, provenance=provenance)
    calls: list[Path] = []

    def fake_run_s4_isolated(worker_dir, cfg, **kwargs):
        calls.append(Path(worker_dir))
        return {
            "verdict": s4.VERDICT_FIT,
            "game_id": "w3-flash-toy",
            "result": {"baseline_actions": [11, 11]},
        }

    before = slot.sidecar.read_bytes()
    result = error = None
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(s4, "run_s4_isolated", fake_run_s4_isolated)
        try:
            result = default_runners()["s4_baselines"](slot.ctx)
        except BaseException as exc:  # noqa: BLE001 — how a stage fails is itself a pin
            error = exc
    return SimpleNamespace(
        slot=slot, result=result, error=error, s4_ran=bool(calls),
        sidecar_unchanged=slot.sidecar.read_bytes() == before,
    )


def _result_of(run: SimpleNamespace, what: str) -> dict:
    if run.result is None:
        pytest.fail(
            f"the s4_baselines runner raised {type(run.error).__name__}: {run.error} on the "
            f"{what} sidecar. A refusal is a ROUTED result ({{ok, to_state, reason}}); an "
            "exception out of a runner appends no ledger line and takes the batch down with it"
        )
    return run.result


def _mentions_provenance(text: str) -> bool:
    """Does a reason or artifact say 'provenance'?

    A substring, deliberately: the gate's own spellings are the artifact KEY
    `frames_provenance` and the record values `provenance:mismatch` /
    `provenance:unrecorded`, and a word-split on either would miss.
    """
    return "provenance" in str(text).lower()


@pytest.fixture(scope="module")
def s4_mismatched(tmp_path_factory, default_cfg) -> SimpleNamespace:
    return _run_s4(tmp_path_factory.mktemp("s4-mismatch"), default_cfg, provenance=BOGUS_SHA)


@pytest.fixture(scope="module")
def s4_unrecorded(tmp_path_factory, default_cfg) -> SimpleNamespace:
    return _run_s4(tmp_path_factory.mktemp("s4-unrecorded"), default_cfg, provenance=None)


@pytest.fixture(scope="module")
def s4_matched(tmp_path_factory, default_cfg) -> SimpleNamespace:
    return _run_s4(tmp_path_factory.mktemp("s4-matched"), default_cfg, provenance="MATCH")


def test_19_s4_refuses_a_mismatched_sidecar(s4_mismatched):
    """Pin 6. W2-C residual (a): 'the resumed-at-gated path — s4_baselines asks
    frames_provenance(worker_dir) before _post_s4_level_floor consumes the
    sidecar (mismatch = the same refusal reason)'. A run resumed at `gated`
    never passes the s3_gate guard, so today a stale sidecar walks straight into
    the post-S4 level floor and is measured as if it were fresh."""
    result = _result_of(s4_mismatched, "mismatched")
    print(f"[W3-A1] s4 mismatch: S4's own run was "
          f"{'reached' if s4_mismatched.s4_ran else 'short-circuited'} before the refusal")

    assert result["ok"] is False, (
        f"s4_baselines returned ok={result['ok']} to_state={result['to_state']!r} reason="
        f"{result['reason']!r} for a sidecar stamped with a source that is not this worker's "
        "game.py. The gate refuses exactly this at s3_gate; the resumed-at-gated path reaches "
        "S4 without ever passing that guard, which is the residual this contract closes"
    )
    reason = str(result["reason"])
    artifacts = {str(key): str(value) for key, value in result["artifacts"].items()}
    assert _mentions_provenance(reason) or any(
        _mentions_provenance(key) or _mentions_provenance(value)
        for key, value in artifacts.items()
    ), (
        f"the refusal reads {reason!r} with artifacts {sorted(artifacts)}; the contract asks for "
        f"'the same refusal reason' the gate uses — {orch.FRAMES_PROVENANCE_REASON!r} — so the "
        "ledger line for a resumed slot says the same thing as the one for a gated slot"
    )
    consumed = [key for key in artifacts if "post_s4" in key or "acceptance" in key]
    assert not consumed, (
        f"the refusal still carries {consumed}: `_post_s4_level_floor` consumed the sidecar "
        "anyway. The contract puts the ask BEFORE that reader — a refused capture must not "
        "also be measured"
    )
    assert s4_mismatched.sidecar_unchanged, "the stage rewrote the sidecar it refused"


def test_20_s4_does_not_refuse_an_unrecorded_sidecar(s4_unrecorded):
    """Pin 6's other half: 'unrecorded = note, never refuse.' Every sidecar
    written before R-21 — the seven shipped games — carries no stamp, and a file
    that does not say what rendered it is exactly as trustworthy as yesterday."""
    result = _result_of(s4_unrecorded, "unrecorded (pre-R-21)")

    assert result["ok"] is True, (
        f"s4_baselines refused a sidecar with NO provenance stamp (reason: "
        f"{result['reason']!r}). 'Unrecorded = note, never refuse' — refusing here would stop "
        "every slot whose capture predates R-21"
    )
    artifacts = {str(key): str(value) for key, value in result["artifacts"].items()}
    noted = _mentions_provenance(result["reason"]) or any(
        _mentions_provenance(key) or _mentions_provenance(value)
        for key, value in artifacts.items()
    )
    assert noted, (
        f"nothing in the S4 result mentions provenance for an unstamped sidecar (reason "
        f"{result['reason']!r}, artifacts {sorted(artifacts)}). The contract asks for a NOTE, "
        "which is what makes 'this capture does not say what rendered it' visible in the ledger "
        "instead of silent"
    )


def test_21_s4_passes_a_matching_sidecar_through(s4_matched):
    """Pin 6's control: an honest fresh capture routes exactly as it does today,
    and the post-S4 level floor still gets to run."""
    result = _result_of(s4_matched, "matching")

    assert result["ok"] is True and result["to_state"] == "baselined", (
        f"a sidecar stamped with THIS worker's game.py routed to ok={result['ok']} "
        f"to_state={result['to_state']!r} reason={result['reason']!r}; the provenance ask must "
        "be invisible when the stamp matches"
    )
    assert s4_matched.s4_ran, "S4's own run was skipped for a clean slot"
    keys = sorted(str(key) for key in result["artifacts"])
    assert any("post_s4" in key or "metadata" in key for key in keys), (
        f"the clean path returned artifacts {keys}; `_post_s4_level_floor` is what runs after "
        "the ask passes (C-4b part b) and it must still run"
    )
