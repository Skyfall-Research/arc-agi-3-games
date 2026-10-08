"""R2 hotfix #8 acceptance: the S2b frames capture is PROCESS-ISOLATED.

Run: .venv/bin/python -m pytest gen/tests/test_r2_hotfix8.py -v

THE INCIDENT (R2 pilot, night of 2026-09-22). The verifier leg captures frames
round after round inside ONE long-lived interpreter. A generated solver does
the §7 sibling load — `importlib.util.spec_from_file_location(...)` on its own
`game.py` — and caches the result in `sys.modules` under a FIXED key. Round 5
therefore handed a freshly exec'd solver the STALE game module from round 1 and
died on `module has no attribute 'route'` while the live `game.py` on disk
defined `route` perfectly well. The worker was innocent; the interpreter was
dirty.

THE CONTRACT this file pins: the frames-capture leg runs each capture in a
FRESH `.venv/bin/python` subprocess, via a new callable entry in `gen/frames.py`
or `gen/s3_verify.py`. A process that dies after one capture cannot serve a
stale module to the next one, so the whole bug class dies with it.

Written INDEPENDENTLY of the implementer's diff: no source of `gen/frames.py`
or `gen/s3_verify.py` was read. The entry is DISCOVERED at import time by
inspecting those two modules (see `_discover_entry`), and the discovery report
is printed by `test_an_isolated_capture_entry_is_discoverable`, which is the
first test to read when this file goes red.

Fixtures are built BY HAND into `tmp_path` (`_write_worker`), never under
`out/`; `fixtures/s6_seeded/` is COPIED into `tmp_path` and never edited in
place.

RENEGOTIABLE READINGS — every one of them is a position this file had to take
because the contract froze a behavior, not a signature:

  R1 WHERE/WHAT the entry is. Pinned: a public module-level FUNCTION exists,
     in `gen.frames` or `gen.s3_verify`, that takes a path-ish argument and
     captures frames out of process. NOT pinned: its name, which of the two
     modules holds it, or whether a `__main__` CLI wraps it. Discovery scores
     candidates by name ("capture" / an isolation hint) and by carrying a
     `timeout` parameter. A CLI-ONLY entry with no importable callable fails
     discovery loudly rather than silently passing — renegotiate if that is
     the shape that landed.
  R2 HOW it is called. Arguments are bound BY PARAMETER NAME: `*game*` and
     `*solver*` take the two file paths; failing a `*game*` parameter, the
     first of `*worker*` / `*dir*` / `*path*` / `*src*` / `*root*` takes the
     worker DIRECTORY; a required `*cfg*` / `*config*` takes the pilot config;
     `*timeout*` takes the timeout. A signature this cannot fill fails with
     the signature quoted, never with a confusing TypeError.
  R3 WHAT it returns. Normalized by `_as_capture`: a `FrameCapture` passes
     through, a dict goes through `capture_from_json`, and a tuple's first
     element or a `.capture` attribute is unwrapped. Returning a path to a
     written file is NOT handled — renegotiate if that is the shape.
  R4 "SAME BYTES BOTH PATHS" (contract item 2) is pinned on the CANONICAL
     JSON — `json.dumps(capture_to_json(cap), sort_keys=True)` — because
     `capture_to_json` is the only serialization surface B7 froze. If the
     wrapper also writes its own on-disk file, this pins the structure that
     file must carry, not its byte layout.
  R5 THE ISOLATION PROOF (contract item 1). BOTH forms are present. The
     unconditional pin is DIRECT: the fixture `game.py` appends
     `os.getpid()` + `sys.executable` to a sidecar log at import time, so two
     wrapper captures must record two DIFFERENT pids, neither of them the
     test process. The in-process CONTROL drives the identical rename
     sequence through `gen.frames.capture` and asserts the stale-module
     AttributeError still reproduces there; if it does NOT reproduce, the
     control SKIPS with a pointer to the pid test rather than failing, since
     the bug class is then already dead by some other means. This assumes the
     child imports `game.py` — it must, to build the game.
  R6 "a fresh `.venv/bin/python`" is pinned as `sys.executable`, not as the
     literal path, so the test survives a relocated venv. Under the repo's
     own `.venv/bin/python -m pytest` invocation the two are the same file.
  R7 TIMEOUT (contract item 4) SKIPS with a stated reason if the discovered
     entry exposes no timeout-ish parameter. "Naming seconds" is accepted in
     any ordinary spelling of the budget (`2`, `2.0`, `2s`, `2.0s`); what is
     pinned is that the error identifies itself as a stop, and that the call
     returns long before the hung solver would have.
  R8 FAIL-LOUD (contract item 3) pins the substring "AttributeError" in
     `str(exc)`. The exception TYPE is not pinned (RuntimeError,
     CalledProcessError and a re-raised AttributeError all satisfy the
     contract); only `Exception` is required, so an entry that calls
     `sys.exit` instead of raising fails here, on purpose.
  R9 Two back-to-back children reusing an OS pid is treated as impossible.
"""

from __future__ import annotations

import importlib.util
import inspect
import itertools
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest
from arcengine import ARCBaseGame

from gen import frames as frames_mod
from gen import s3_verify as s3_verify_mod
from gen.frames import FrameCapture, capture_from_json, capture_to_json

TESTS = Path(__file__).resolve().parent
S6_SEEDED = TESTS / "fixtures/s6_seeded"
PILOT_CONFIG = "config/b001-pilot.yaml"

#: The solver's sibling-load cache key — DELIBERATELY fixed and synthetic.
#: This is the exact caching shape that served round 5 a round-1 game module.
FIXED_CACHE_KEY = "game_fixedcachekey"

#: The §7 helper the solver calls across the sibling load, and its renamed
#: twin. Round 2 of the bug-class test ships a CONSISTENT pair using the new
#: name, so the only way to see the old name is to be served a stale module.
#: The two names share NO substring, so every `in` check below is unambiguous.
ROUTE_V1 = "route"
ROUTE_V2 = "plan_after_rename"

#: A name no version of the fixture game ever defines (contract item 3).
MISSING_ATTR = "definitely_not_a_real_helper"


# --------------------------------------------------------------------------- #
# the fixture worker: a minimal §7 pair, written by hand into tmp_path
# --------------------------------------------------------------------------- #

_GAME_SRC = '''"""Minimal §7 worker game for the R2 hotfix #8 isolation pins.

Deliberately the smallest thing that is still a §7 worker: a module-level pure
`build_layout(seed)`, a `Game(layout_seed=None)` over it, and the sibling
helper `__ROUTE__` that `solver.py` reaches across the import boundary for.
8x8 board, camera upscales to 64x64, two levels, border walls only, so the
route from the player at (1, 1) to the goal is a clean right-then-down L.
"""

import hashlib

__PID_PROBE__

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

GAME_ID = "r2h8-mini-gate"
DEFAULT_LAYOUT_SEED = 8
LEVEL_COUNT = 2
BOARD = 8
WALL, PLAYER, GOAL = 4, 9, 12
PLAYER_X, PLAYER_Y = 1, 1

DIRS = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}


def build_layout(seed):
    """§7: pure, deterministic, JSON-able, seed-varying."""
    seed = int(seed)
    layout = []
    for index in range(LEVEL_COUNT):
        digest = hashlib.sha256(f"r2h8-mini-gate:{seed}:{index}".encode()).digest()
        layout.append(
            {"level": index + 1, "goal": [3 + digest[0] % 4, 3 + digest[1] % 4]}
        )
    return layout


def __ROUTE__(spec):
    """The sibling helper the solver calls by name across the §7 import."""
    goal_x, goal_y = spec["goal"]
    return ["ACTION4"] * (goal_x - PLAYER_X) + ["ACTION2"] * (goal_y - PLAYER_Y)


def _level(spec):
    goal_x, goal_y = spec["goal"]
    sprites = [
        Sprite([[WALL] * BOARD], name="wall_top", x=0, y=0),
        Sprite([[WALL] * BOARD], name="wall_bottom", x=0, y=BOARD - 1),
        Sprite([[WALL]] * (BOARD - 2), name="wall_left", x=0, y=1),
        Sprite([[WALL]] * (BOARD - 2), name="wall_right", x=BOARD - 1, y=1),
        Sprite([[GOAL]], name="goal", x=goal_x, y=goal_y, layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=PLAYER_X, y=PLAYER_Y, layer=2),
    ]
    return Level(sprites=sprites)


class MiniGate(ARCBaseGame):
    def __init__(self, layout_seed=None):
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed
        self._layout = build_layout(seed)
        super().__init__(
            game_id=GAME_ID,
            levels=[_level(spec) for spec in self._layout],
            camera=Camera(width=BOARD, height=BOARD),
            available_actions=[1, 2, 3, 4],
        )

    def step(self):
        delta = DIRS.get(self.action.id)
        if delta is not None:
            self.try_move("player", *delta)
        self.complete_action()
        player = self.current_level.get_sprites_by_name("player")[0]
        goal = self.current_level.get_sprites_by_name("goal")[0]
        if (player.x, player.y) == (goal.x, goal.y):
            self.next_level()
'''

_SOLVER_SRC = '''"""Minimal §7 solver for the R2 hotfix #8 isolation pins.

It sibling-loads `game.py` BY PATH under a FIXED synthetic module name and
short-circuits on `sys.modules`. That is not a mistake in the fixture: it is a
faithful copy of the caching shape that made round 5 of the pilot read a
round-1 game module, and it is what the process boundary has to neutralise.
"""

import importlib.util
import sys
__SLEEP_IMPORT__
from pathlib import Path

from arcengine import ActionInput, GameAction

_GAME_PATH = Path(__file__).resolve().with_name("game.py")

#: FIXED, not derived from the path — the stale-module trap, on purpose.
_CACHE_KEY = "__CACHE_KEY__"


def _game_module():
    module = sys.modules.get(_CACHE_KEY)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(_CACHE_KEY, _GAME_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build an import spec for {_GAME_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_CACHE_KEY] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_CACHE_KEY, None)
        raise
    return module


class Solver:
    def __init__(self, layout_seed=None):
        __SLEEP_CALL__
        module = _game_module()
        seed = module.DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.plans = [module.__ROUTE__(spec) for spec in module.build_layout(seed)]
        self.reset()

    def reset(self):
        self._cursor = [0] * len(self.plans)

    def next_action(self, frame):
        level = int(frame.levels_completed)
        if level >= len(self.plans):
            return None
        index = self._cursor[level]
        if index >= len(self.plans[level]):
            return None
        self._cursor[level] = index + 1
        return ActionInput(id=GameAction[self.plans[level][index]])
'''

_PID_PROBE_SRC = '''import os as _probe_os
import sys as _probe_sys

with open(__PROBE_PATH__, "a", encoding="utf-8") as _probe_fh:
    _probe_fh.write(f"{_probe_os.getpid()}\\t{_probe_sys.executable}\\n")'''

#: A sleep long enough that a wrapper which waited it out would blow any
#: sane test budget — the timeout pin measures wall time against it.
SLEEP_S = 120.0


def _write_worker(
    worker: Path,
    *,
    route: str = ROUTE_V1,
    solver_calls: str | None = None,
    pid_log: Path | None = None,
    sleep: bool = False,
) -> Path:
    """Write a §7 game.py + solver.py pair into `worker` and return it.

    `route` names the helper game.py DEFINES; `solver_calls` names the helper
    solver.py CALLS (defaults to `route`, i.e. a consistent pair). Passing a
    different `solver_calls` is how contract item 3's broken worker is built.
    """
    worker.mkdir(parents=True, exist_ok=True)
    probe = (
        _PID_PROBE_SRC.replace("__PROBE_PATH__", repr(str(pid_log)))
        if pid_log is not None
        else ""
    )
    game_src = _GAME_SRC.replace("__ROUTE__", route).replace("__PID_PROBE__", probe)
    solver_src = (
        _SOLVER_SRC.replace("__ROUTE__", solver_calls if solver_calls else route)
        .replace("__CACHE_KEY__", FIXED_CACHE_KEY)
        .replace("__SLEEP_IMPORT__", "import time" if sleep else "")
        .replace("__SLEEP_CALL__", f"time.sleep({SLEEP_S})" if sleep else "pass")
    )
    (worker / "game.py").write_text(game_src, encoding="utf-8")
    (worker / "solver.py").write_text(solver_src, encoding="utf-8")
    return worker


def _copy_s6_seeded(worker: Path) -> Path:
    """A writable copy of the §7 reference fixture — the original is read-only."""
    worker.mkdir(parents=True, exist_ok=True)
    for name in ("game.py", "solver.py"):
        shutil.copy2(S6_SEEDED / name, worker / name)
    return worker


def _read_probe(pid_log: Path) -> list[tuple[int, str]]:
    if not pid_log.exists():
        return []
    rows = []
    for line in pid_log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        pid, _, executable = line.partition("\t")
        rows.append((int(pid), executable))
    return rows


# --------------------------------------------------------------------------- #
# in-process loading (the B7 idiom) — used by the CONTROL and the parity pin
# --------------------------------------------------------------------------- #

_LOAD_SEQ = itertools.count()


def _load_module(path: Path):
    """Exec-load a fixture file under a UNIQUE outer name.

    Unique so the test harness itself never caches; the fixture solver's OWN
    fixed inner key is the thing under test and is untouched by this.
    """
    name = f"r2h8_fixture_{next(_LOAD_SEQ)}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot import {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _game_class(path: Path) -> type:
    module = _load_module(path)
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


def _solver_class(path: Path) -> type:
    module = _load_module(path)
    solver = getattr(module, "Solver", None)
    assert isinstance(solver, type), f"{path}: no Solver class"
    return solver


def _capture_in_process(worker: Path) -> FrameCapture:
    # LEAD ADJUDICATION (W2-C close): the R4 invariant this file pins is "the
    # process boundary must be invisible in the artifact" — the in-process leg
    # is therefore frames.capture_worker (the seam the isolated child itself
    # runs), not a bare class-capture. The two were identical by accident until
    # W2-C's optional source_sha256 stamp: capture_worker knows the file and
    # stamps it, a class in hand has no file and records None. Comparing
    # class-capture to worker-capture measured an INPUT difference, not the
    # process boundary. capture_worker ≡ capture_worker_isolated remains pinned
    # byte-for-byte by the tests below, stamp included.
    from gen.frames import capture_worker

    return capture_worker(worker)


@pytest.fixture(autouse=True)
def _clean_stale_cache_key():
    """Pop the fixture's fixed key around every test.

    Between tests this is hygiene. WITHIN a test it is never touched, so a
    wrapper that secretly ran in-process would still poison its own second
    capture — which is exactly what the bug-class test is looking for.
    """
    sys.modules.pop(FIXED_CACHE_KEY, None)
    yield
    sys.modules.pop(FIXED_CACHE_KEY, None)


# --------------------------------------------------------------------------- #
# R1/R2 — discovering and driving the subprocess entry
# --------------------------------------------------------------------------- #

#: Everything gen.frames already exported before this hotfix (B7 contract).
_IN_PROCESS_NAMES = frozenset(
    {"capture", "capture_to_json", "capture_from_json", "digest_text"}
)
_ISOLATION_HINTS = (
    "isolat",
    "subproc",
    "child",
    "spawn",
    "process",
    "proc",
    "extern",
    "fresh",
    "oop",
)
_PATH_TOKENS = ("game", "solver", "worker", "dir", "path", "src", "root")


def _is_pathish(name: str) -> bool:
    low = name.lower()
    return any(token in low for token in _PATH_TOKENS)


def _discover_entry():
    """Find the subprocess capture entry, or explain what was rejected.

    Returns `(name, module_name, func, signature, report)`; `func` is None when
    nothing qualified and `report` always carries the search evidence.
    """
    scanned: list[str] = []
    ranked: list[tuple[tuple, str, str, object, inspect.Signature]] = []
    for module in (frames_mod, s3_verify_mod):
        for name, obj in sorted(vars(module).items()):
            if name.startswith("_") or not inspect.isfunction(obj):
                continue
            if getattr(obj, "__module__", None) != module.__name__:
                continue
            if name in _IN_PROCESS_NAMES:
                continue
            try:
                sig = inspect.signature(obj)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                continue
            low = name.lower()
            hinted = any(hint in low for hint in _ISOLATION_HINTS)
            about_capture = "capture" in low or "frame" in low
            pathish = any(_is_pathish(p) for p in sig.parameters)
            scanned.append(
                f"{module.__name__}.{name}{sig} "
                f"[capture={about_capture} isolation-hint={hinted} path-arg={pathish}]"
            )
            if not pathish or not (about_capture or hinted):
                continue
            timeouted = any("timeout" in p.lower() for p in sig.parameters)
            ranked.append(
                ((about_capture and hinted, timeouted, hinted), name, module.__name__, obj, sig)
            )
    report = (
        "R2 hotfix #8 discovery — public functions scanned in gen.frames and "
        "gen.s3_verify:\n  " + "\n  ".join(scanned or ["<none>"])
    )
    if not ranked:
        return None, None, None, None, report
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    _, name, module_name, func, sig = ranked[0]
    others = [f"{r[2]}.{r[1]}" for r in ranked[1:]]
    report += f"\n  -> chose {module_name}.{name}{sig}"
    if others:
        report += f" (runners-up: {', '.join(others)})"
    return name, module_name, func, sig, report


ENTRY_NAME, ENTRY_MODULE, ENTRY, ENTRY_SIG, DISCOVERY_REPORT = _discover_entry()


def _pilot_cfg():
    from gen.config import load_config

    return load_config(PILOT_CONFIG)


def _first_param(names, token: str) -> str | None:
    return next((n for n in names if token in n.lower()), None)


def _bind(worker: Path, *, timeout: float | None):
    """R2: fill the discovered signature by parameter name."""
    params = ENTRY_SIG.parameters
    names = [
        n
        for n, p in params.items()
        if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    values: dict[str, object] = {}

    game_param = _first_param(names, "game")
    if game_param is not None:
        values[game_param] = worker / "game.py"
        solver_param = _first_param(names, "solver")
        if solver_param is not None:
            values[solver_param] = worker / "solver.py"
    else:
        dir_param = next(
            (
                p
                for token in ("worker", "dir", "path", "src", "root")
                for p in [_first_param(names, token)]
                if p is not None
            ),
            None,
        )
        if dir_param is None:
            pytest.fail(
                "R2 (renegotiable): cannot bind the worker to "
                f"{ENTRY_MODULE}.{ENTRY_NAME}{ENTRY_SIG} — no game/worker/dir/path "
                f"parameter.\n{DISCOVERY_REPORT}"
            )
        values[dir_param] = worker

    cfg_param = _first_param(names, "cfg") or _first_param(names, "config")
    if cfg_param is not None and params[cfg_param].default is inspect.Parameter.empty:
        values[cfg_param] = _pilot_cfg()

    if timeout is not None:
        timeout_param = _first_param(names, "timeout")
        if timeout_param is not None:
            values[timeout_param] = timeout

    args, kwargs = [], {}
    for name in names:
        if name not in values:
            continue
        if params[name].kind is inspect.Parameter.POSITIONAL_ONLY:
            args.append(values[name])
        else:
            kwargs[name] = values[name]
    return args, kwargs


def _capture_isolated(worker: Path, *, timeout: float | None = None):
    """Drive the discovered subprocess entry against one worker directory."""
    if ENTRY is None:
        pytest.fail(
            "R2 hotfix #8 CONTRACT: no subprocess frames-capture entry is importable "
            f"from gen.frames or gen.s3_verify.\n{DISCOVERY_REPORT}"
        )
    args, kwargs = _bind(worker, timeout=timeout)
    try:
        return ENTRY(*args, **kwargs)
    except TypeError as exc:
        if "argument" not in str(exc):
            raise
        pytest.fail(
            "R2 (renegotiable): the name-based binding does not fit "
            f"{ENTRY_MODULE}.{ENTRY_NAME}{ENTRY_SIG} — called with "
            f"args={args!r} kwargs={sorted(kwargs)}; TypeError: {exc}"
        )


def _as_capture(result) -> FrameCapture:
    """R3: normalize whatever the entry returns to a FrameCapture."""
    if isinstance(result, FrameCapture):
        return result
    if isinstance(result, dict):
        return capture_from_json(result)
    if isinstance(result, tuple) and result:
        return _as_capture(result[0])
    inner = getattr(result, "capture", None)
    if inner is not None and inner is not result:
        return _as_capture(inner)
    pytest.fail(
        "R3 (renegotiable): the subprocess entry returned "
        f"{type(result).__name__} — expected a FrameCapture, a capture_to_json dict, "
        "a tuple leading with one, or an object carrying `.capture`."
    )


def _canon(cap: FrameCapture) -> str:
    """R4: the canonical serialization both paths are compared on."""
    return json.dumps(capture_to_json(cap), sort_keys=True)


def _timeout_param_name() -> str | None:
    if ENTRY_SIG is None:
        return None
    return _first_param(list(ENTRY_SIG.parameters), "timeout")


# --------------------------------------------------------------------------- #
# group 0 — the entry itself
# --------------------------------------------------------------------------- #


def test_an_isolated_capture_entry_is_discoverable():
    """READ THIS FIRST when the file goes red: it prints the whole search."""
    assert ENTRY is not None, (
        "R2 hotfix #8 CONTRACT: the S2b frames-capture leg must expose a callable "
        "that captures out of process, in gen/frames.py or gen/s3_verify.py.\n"
        f"{DISCOVERY_REPORT}"
    )
    assert callable(ENTRY), DISCOVERY_REPORT


def test_the_fixture_worker_is_a_real_section_7_pair(tmp_path):
    """The fixture must be a genuine §7 worker, or none of the pins mean anything."""
    worker = _write_worker(tmp_path / "worker")
    module = _load_module(worker / "game.py")

    layout = module.build_layout(module.DEFAULT_LAYOUT_SEED)
    assert module.build_layout(module.DEFAULT_LAYOUT_SEED) == layout, "§7: pure in the seed"
    assert json.dumps(layout, sort_keys=True), "§7: the layout must be JSON-able"
    assert len(layout) == module.LEVEL_COUNT == 2
    assert callable(getattr(module, ROUTE_V1)), f"the sibling helper {ROUTE_V1!r} must exist"

    cap = _capture_in_process(worker)
    assert cap.win is True and cap.levels_completed == 2, (
        f"the fixture solver must beat both levels in process; got "
        f"win={cap.win} levels={cap.levels_completed}"
    )
    assert sys.modules.get(FIXED_CACHE_KEY) is not None, (
        "the fixture solver must really register the fixed cache key — that trap "
        "IS the incident this hotfix is about"
    )


# --------------------------------------------------------------------------- #
# group 1 — contract item 1: THE BUG CLASS DIES
# --------------------------------------------------------------------------- #


def _rename_round_two(worker: Path) -> None:
    """Replace the pair with a CONSISTENT one that renamed the helper.

    Both files are rewritten together, so nothing on disk mentions the old
    name any more: a round-2 failure on `route` can ONLY come from a module
    that was cached before this call.
    """
    _write_worker(worker, route=ROUTE_V2)
    game_src = (worker / "game.py").read_text(encoding="utf-8")
    solver_src = (worker / "solver.py").read_text(encoding="utf-8")
    assert f"def {ROUTE_V2}(" in game_src, "round 2's game.py must define the RENAMED helper"
    assert f"def {ROUTE_V1}(" not in game_src, "round 2's game.py must drop the old helper"
    assert f"module.{ROUTE_V2}(" in solver_src, "round 2's solver.py must call the new name"
    assert f"module.{ROUTE_V1}(" not in solver_src, (
        "round 2 is a CONSISTENT pair — the solver must not still call the old name"
    )


def test_the_stale_sibling_module_bug_class_dies_under_the_wrapper(tmp_path):
    """THE PIN. Two captures, one test process, the helper renamed between them.

    Round 1 captures a worker whose helper is `route`. `game.py` and
    `solver.py` are then replaced by a CONSISTENT pair that calls
    `route_after_rename`. Under the pilot's in-process capture the second
    round dies on `module has no attribute 'route_after_rename'`, because the
    solver's fixed cache key still points at round 1's game module. Under a
    process-isolated capture there is nothing left to be stale.
    """
    worker = _write_worker(tmp_path / "worker", route=ROUTE_V1)
    first = _as_capture(_capture_isolated(worker))
    assert first.win is True and first.levels_completed == 2, (
        f"round 1 must be a clean win; got win={first.win} levels={first.levels_completed}"
    )

    _rename_round_two(worker)
    second = _as_capture(_capture_isolated(worker))
    assert second.win is True and second.levels_completed == 2, (
        "round 2 is a CONSISTENT pair on disk — a failure here is the pilot's "
        "stale-module bug surviving the hotfix; got "
        f"win={second.win} levels={second.levels_completed}"
    )
    assert second.records, "round 2 must produce frames, not an empty capture"
    assert sys.modules.get(FIXED_CACHE_KEY) is None, (
        f"a capture must not register {FIXED_CACHE_KEY!r} in the PARENT interpreter — "
        "that residue is precisely what poisoned round 5 of the pilot"
    )


def test_two_wrapper_captures_run_in_two_different_child_processes(tmp_path):
    """R5, the UNCONDITIONAL isolation pin: different pids, both not us.

    `game.py` logs `os.getpid()` and `sys.executable` at import. A capture that
    ran in-process would record THIS process; a capture that reused a warm
    worker process would record the same pid twice. Neither is allowed.
    """
    pid_log = tmp_path / "pids.tsv"
    worker = _write_worker(tmp_path / "worker", pid_log=pid_log)

    _as_capture(_capture_isolated(worker))
    first_rows = _read_probe(pid_log)
    pid_log.write_text("", encoding="utf-8")
    _as_capture(_capture_isolated(worker))
    second_rows = _read_probe(pid_log)

    assert first_rows and second_rows, (
        "the fixture game.py must be imported by each capture; the probe log was "
        f"{first_rows!r} then {second_rows!r}"
    )
    first_pids = {pid for pid, _ in first_rows} - {os.getpid()}
    second_pids = {pid for pid, _ in second_rows} - {os.getpid()}
    assert first_pids, f"capture 1 imported game.py only in THIS process: {first_rows!r}"
    assert second_pids, f"capture 2 imported game.py only in THIS process: {second_rows!r}"
    assert first_pids.isdisjoint(second_pids), (
        "each capture must get a FRESH interpreter — a process shared across captures "
        f"can still serve a stale module. pids {sorted(first_pids)} vs "
        f"{sorted(second_pids)}"
    )
    # R6: "a fresh .venv/bin/python" pinned as this interpreter, not a literal path.
    for pid, executable in first_rows + second_rows:
        if pid == os.getpid():
            continue
        assert executable == sys.executable, (
            f"the child must run {sys.executable} (the venv interpreter running these "
            f"tests), got {executable!r}"
        )


def test_the_in_process_control_reproduces_the_stale_module_bug(tmp_path):
    """R5's CONTROL: the same sequence, driven through `gen.frames.capture`.

    This is the contrast that gives the wrapper test its meaning. It SKIPS
    rather than fails if the bug does not reproduce, because a bug class that
    is already dead in process is not a reason to fail the hotfix — the
    unconditional pid test still holds the isolation property.
    """
    worker = _write_worker(tmp_path / "worker", route=ROUTE_V1)
    first = _capture_in_process(worker)
    assert first.win is True, "the control's round 1 must win, exactly as the wrapper's does"

    _rename_round_two(worker)
    try:
        _capture_in_process(worker)
    except AttributeError as exc:
        assert ROUTE_V2 in str(exc), (
            "the control must die on the RENAMED helper (the stale round-1 module has "
            f"only {ROUTE_V1!r}); got: {exc}"
        )
        return
    pytest.skip(
        "in-process capture no longer reproduces the stale-sibling AttributeError, so "
        "this control has nothing to contrast; isolation stays pinned directly by "
        "test_two_wrapper_captures_run_in_two_different_child_processes"
    )


# --------------------------------------------------------------------------- #
# group 2 — contract item 2: SAME BYTES BOTH PATHS
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fixture", ["mini", "s6_seeded"])
def test_the_subprocess_path_serializes_exactly_what_the_in_process_path_does(
    tmp_path, fixture
):
    """R4: same worker, both paths, identical canonical capture JSON."""
    worker = tmp_path / "worker"
    if fixture == "mini":
        _write_worker(worker)
    else:
        _copy_s6_seeded(worker)

    in_process = _capture_in_process(worker)
    isolated = _as_capture(_capture_isolated(worker))

    assert in_process.win is True, "the fixture must be a winning worker on both paths"
    assert isolated.win == in_process.win
    assert isolated.levels_completed == in_process.levels_completed
    assert isolated.source == in_process.source, (
        f"both paths must report the same capture source; got {isolated.source!r} "
        f"vs {in_process.source!r}"
    )
    assert isolated.game_id == in_process.game_id
    assert len(isolated.records) == len(in_process.records)
    assert _canon(isolated) == _canon(in_process), (
        "the process boundary must be invisible in the artifact: "
        "json.dumps(capture_to_json(cap), sort_keys=True) must match exactly"
    )


# --------------------------------------------------------------------------- #
# group 3 — contract item 3: FAIL-LOUD
# --------------------------------------------------------------------------- #


def test_a_child_that_raises_makes_the_wrapper_raise_with_the_child_error(tmp_path):
    """R8: never a silent empty capture — the child's error class comes back."""
    worker = _write_worker(tmp_path / "worker", solver_calls=MISSING_ATTR)
    assert MISSING_ATTR not in (worker / "game.py").read_text(encoding="utf-8"), (
        "the fixture must call an attribute the game genuinely does not define"
    )

    # R8: the exception TYPE is deliberately NOT pinned, only its message.
    with pytest.raises(Exception) as excinfo:
        _capture_isolated(worker)

    message = f"{type(excinfo.value).__name__}: {excinfo.value}"
    assert "AttributeError" in message, (
        "a dead child must surface its error class to the parent, not a silent empty "
        f"capture; the wrapper raised: {message}"
    )
    assert str(excinfo.value).strip(), "the raised error must carry a message"


def test_a_child_that_cannot_even_import_fails_loud(tmp_path):
    """The same guarantee one layer down: a game.py that will not import."""
    worker = _write_worker(tmp_path / "worker")
    (worker / "game.py").write_text(
        "raise RuntimeError('R2H8-GAME-IMPORT-EXPLODED')\n", encoding="utf-8"
    )

    # R8: the exception TYPE is deliberately NOT pinned, only its message.
    with pytest.raises(Exception) as excinfo:
        _capture_isolated(worker)

    message = f"{type(excinfo.value).__name__}: {excinfo.value}"
    assert "R2H8-GAME-IMPORT-EXPLODED" in message or "RuntimeError" in message, (
        f"the child's import failure must reach the caller; the wrapper raised: {message}"
    )


# --------------------------------------------------------------------------- #
# group 4 — contract item 4: TIMEOUT
# --------------------------------------------------------------------------- #


def test_a_hung_child_is_killed_by_the_timeout(tmp_path):
    """R7: a tiny timeout on a sleeping solver raises, fast, and says so."""
    timeout_param = _timeout_param_name()
    if ENTRY is None:
        pytest.fail(
            "R2 hotfix #8 CONTRACT: no subprocess capture entry is importable.\n"
            f"{DISCOVERY_REPORT}"
        )
    if timeout_param is None:
        pytest.skip(
            "R7 (renegotiable): the discovered entry "
            f"{ENTRY_MODULE}.{ENTRY_NAME}{ENTRY_SIG} exposes no timeout parameter, so "
            "the contract's timeout leg has no surface to test. Renegotiate if the "
            "timeout landed under a name this does not match."
        )

    worker = _write_worker(tmp_path / "worker", sleep=True)
    budget = 2.0
    started = time.monotonic()
    # R8: the exception TYPE is deliberately NOT pinned, only its message.
    with pytest.raises(Exception) as excinfo:
        _capture_isolated(worker, timeout=budget)
    elapsed = time.monotonic() - started

    message = f"{type(excinfo.value).__name__}: {excinfo.value}".lower()
    # R7: "naming seconds" is accepted in any ordinary spelling of the budget
    # (2, 2.0, 2s, 2.0s) — the contract pins that the error IDENTIFIES itself,
    # not how a float is formatted.
    seconds = {f"{budget}", f"{budget:g}", f"{budget}s", f"{budget:g}s"}
    assert (
        any(token in message for token in seconds)
        or "timed out" in message
        or "timeout" in message
    ), (
        "a killed child must raise a TIMEOUT-flavoured error naming the seconds or "
        f'saying "timed out"; got: {message}'
    )
    assert any(word in message for word in ("timed out", "timeout", "exceed", "kill", "expire")), (
        "the error must say the child was STOPPED, not merely mention a number; "
        f"got: {message}"
    )
    assert elapsed < SLEEP_S / 2, (
        f"the wrapper waited {elapsed:.1f}s on a {budget}s timeout — it must kill the "
        f"child, not sit out the solver's {SLEEP_S}s sleep"
    )


def test_a_healthy_child_is_untouched_by_a_generous_timeout(tmp_path):
    """The timeout must not become a second failure mode for good workers."""
    if _timeout_param_name() is None:
        pytest.skip("R7 (renegotiable): the discovered entry exposes no timeout parameter")

    worker = _write_worker(tmp_path / "worker")
    cap = _as_capture(_capture_isolated(worker, timeout=300.0))
    assert cap.win is True and cap.levels_completed == 2, (
        f"a generous timeout must change nothing; got win={cap.win} "
        f"levels={cap.levels_completed}"
    )
