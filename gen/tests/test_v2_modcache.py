"""BLIND lane for frozen contract E-4 — worker module-cache isolation.

Written from `docs/v2/contracts/E-4-module-cache-isolation.md` (including
Addendum 1) alone: every assertion message cites the contract sentence it is
accountable to, and nothing here was read out of the implementer's own
battery. The implementation was read only to learn NAMES and SHAPES
(`gen/worker.py`'s eviction section, the three call sites, the §7 skeleton
`gen/s2_implement.LAYOUT_SEED_CONTRACT` teaches).

WHAT THE CONTRACT PROMISES, and where each promise is pinned below:

  §M1  the demonstrated experiment as a pin — a PATH-keyed load, a rewrite,
       and a fresh load that differs from the cache hit; then agreement with
       the bytes on disk at every named call site.          -> `TestM1*`
  §M2  the lantern class end-to-end: an OLD-skeleton pair driven through two
       S2-rewrite -> S6-validate cycles in ONE process. Reverted eviction
       reproduces the seed-INDEPENDENT 0-levels signature; the fix passes at
       every seed.                                          -> `TestM2*`
  §M3  the NEW taught skeleton survives an in-process rewrite with no
       eviction at all.                                     -> `TestM3*`
  §M4  S2b's staged copy is immune by construction (different path, different
       key) and a refactor must not merge the paths silently.
                                                            -> `TestM4*`
  Addendum 1: eviction at the TWO shared pair loaders PLUS S6's own
  `_load_worker` (load-bearing behind its warm stat cache); prefix-agnostic
  tag matching; the stat-in-NAME taught cache; and THE PYC BELT — the purge
  also removes the worker's own `__pycache__`, symlink-refusing and
  absence-tolerant.                       -> `TestEvictionSurface`, `TestBelt`

HERMETIC. Every worker is written into `tmp_path`; nothing under the real
`out/` or `games/` is read or written; no drivers, no network, no spend.
`modcache_guard` is autouse and undoes the two pieces of process-global state
these pins touch — the `sys.modules` entries planted from a tmp worker and
S6's module cache dict.

TWO MEASURED NUANCES, recorded here because a reader of the pins deserves
them (both are reported in the blind handback):

  * the pyc layer the contract records as SECONDARY is REAL and it confounds
    any same-size rewrite: a rewrite that keeps the byte count AND lands in
    the same wall-clock second is served stale bytecode even to a brand-new
    module name. Every rewrite in the module-cache pins below therefore
    CHANGES THE SIZE (what a real S2 fix does), so the thing being measured
    is the module table and not the bytecode cache. The pyc layer gets its
    own red/green pins in `TestBelt`.
  * S6's own purge is load-bearing only when its stat cache is WARM across
    the change, which a plain forward rewrite never leaves it (the new
    mtime+size misses the cache and the shared loader purges on the way
    through). The ordering that leaves it warm is an S2 REVERT to previously
    seen bytes — `shutil.copy2` restores mtime_ns and size exactly — and
    that is the ordering `TestM2OrderedControl` uses.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

from gen import s2_implement, s3_static, s3_verify, s4_baselines, s6_package
from gen import worker as worker_mod

TESTS = Path(__file__).resolve().parent

#: The checked-in §7 reference pair. Its `solver.py` carries the OLD skeleton
#: pattern (a PATH-keyed `sys.modules` short-circuit under the non-"game_"
#: prefix `s6_seeded_game_`), which is exactly the shipped-solver class §M2
#: names — so it is used rather than synthesized. READ-ONLY: copied into
#: `tmp_path` and never edited in place.
S6_SEEDED = TESTS / "fixtures/s6_seeded"

#: The fixture's layout namespace, and the one-token edit that stands in for
#: an S2 rewrite: every level's gate column, gap row, start row and goal row
#: are derived from it, so changing it MOVES the geometry while leaving a
#: perfectly valid, winnable game. It is three bytes LONGER, so the rewrite
#: changes the file SIZE (see the module docstring's first nuance).
FIXTURE_NS_V1 = "s6-seeded-gate/layout/v1"
FIXTURE_NS_V2 = "s6-seeded-gate/layout/v2-e4"

#: Five seeds, the count S6 validates a game at (`package.seeds_validated`),
#: fixed literals so "5/5" and "0/5" are reproducible forever. Deliberately
#: unrelated magnitudes: the §M2 signature claim is that the verdict does not
#: depend on the seed.
SEEDS = (11, 2027, 404, 90210, 7)

#: `validate_seed` drives a solver line; a bound this small keeps a desynced
#: line from burning the default budget while staying far above the ~12
#: actions the fixture's six levels need at any seed.
MAX_ACTIONS = 400

#: The call sites Addendum 1 ratifies, as (name, module holding the imported
#: `purge_worker_modules`, callable -> the Solver class it loaded).
CALL_SITES = {
    "s3_static.load_worker_classes": (
        s3_static,
        lambda w: s3_static.load_worker_classes(w)[1],
    ),
    "s3_verify.load_worker_classes": (
        s3_verify,
        lambda w: s3_verify.load_worker_classes(w)[1],
    ),
    "s6_package._load_worker": (
        s6_package,
        lambda w: s6_package._load_worker(w)[3],
    ),
}

#: The two SHARED pair loaders. Addendum 1: "the sweep proved every stage
#: funnels through them".
SHARED_CALL_SITES = ("s3_static.load_worker_classes", "s3_verify.load_worker_classes")


# --------------------------------------------------------------------------- #
# hermetic scaffolding
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def modcache_guard(tmp_path_factory):
    """Undo the process-global state these pins touch.

    Two pieces: `sys.modules` entries planted by a tmp worker's own
    sibling-loader (popped on the way out, identified by a `__file__` under
    pytest's tmp root — never by name, so a drift in the naming scheme cannot
    make the cleanup silently skip one), and `s6_package._WORKER_CACHE`, which
    is swapped for a fresh dict so one test's warm cache is never another's.
    """
    basetemp = str(tmp_path_factory.getbasetemp())
    before = set(sys.modules)
    real_cache = s6_package._WORKER_CACHE
    s6_package._WORKER_CACHE = {}
    try:
        yield
    finally:
        s6_package._WORKER_CACHE = real_cache
        for name in set(sys.modules) - before:
            origin = getattr(sys.modules.get(name), "__file__", None) or ""
            if origin.startswith(basetemp):
                sys.modules.pop(name, None)


_OUTER_SEQ = itertools.count()


def _exec_file(path: Path):
    """Exec-load one file under a UNIQUE outer name, dropped straight away.

    Unique and immediately unregistered so THIS harness never caches: the only
    cache in play is the one the loaded file keeps for itself, which is the
    thing under measurement.
    """
    name = f"e4blind_outer_{next(_OUTER_SEQ)}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"no import spec for {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _revert_eviction(monkeypatch, *modules):
    """The NEGATIVE CONTROL: the named call sites stop evicting.

    E-4 §Pins: "a long-lived two-cycle fake batch ... that fails under a
    reverted eviction (negative control) and passes now."
    """

    def _noop(worker_dir):
        return ()

    for module in modules:
        monkeypatch.setattr(module, "purge_worker_modules", _noop)


def _copy_fixture(worker: Path) -> Path:
    """A writable copy of the §7 reference pair — the checked-in one is input."""
    worker.mkdir(parents=True, exist_ok=True)
    for name in ("game.py", "solver.py"):
        shutil.copy2(S6_SEEDED / name, worker / name)
    return worker


def _rewrite_fixture_layout(worker: Path) -> None:
    """The stand-in S2 rewrite: move the geometry, keep the game valid."""
    path = worker / "game.py"
    text = path.read_text(encoding="utf-8")
    assert FIXTURE_NS_V1 in text, (
        f"{path}: the fixture no longer spells {FIXTURE_NS_V1!r}, so this lane's stand-in "
        "S2 rewrite does not change the layout — E-4 §M2 needs a rewrite that moves the "
        "geometry while leaving the game winnable"
    )
    path.write_text(text.replace(FIXTURE_NS_V1, FIXTURE_NS_V2), encoding="utf-8")


def _validate_cycle(worker: Path) -> list[dict]:
    """One S6 validation cycle: every seed, in one process, in order."""
    return [
        s6_package.validate_seed(worker, seed, max_actions=MAX_ACTIONS) for seed in SEEDS
    ]


def _signature(rows: list[dict]) -> list[tuple]:
    return [(row["seed"], row["win"], row["levels_completed"]) for row in rows]


# --------------------------------------------------------------------------- #
# the synthetic probe worker: a minimal §7 pair whose solver reports WHICH
# bytes it is planning against. `PROBE` is the sentinel; the solver reads it
# ACROSS its own sibling load, so `Solver(...).probe` is the answer to "what
# did the driven pair see?" that §M1 asks for.
# --------------------------------------------------------------------------- #

_PROBE_GAME_SRC = '''"""Minimal §7 game for the E-4 blind lane. Sentinel: `PROBE`."""

import hashlib

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

GAME_ID = "e4-blind-probe"
DEFAULT_LAYOUT_SEED = 4
LEVEL_COUNT = 2
BOARD = 8
WALL, PLAYER, GOAL = 4, 9, 12
PLAYER_X, PLAYER_Y = 1, 1

#: THE SENTINEL the solver reports back across its sibling load.
PROBE = "__PROBE__"

DIRS = {
    GameAction.ACTION1: (0, -1),
    GameAction.ACTION2: (0, 1),
    GameAction.ACTION3: (-1, 0),
    GameAction.ACTION4: (1, 0),
}


def build_layout(seed):
    """§7: pure, module-level, deterministic, JSON-able, seed-varying."""
    seed = int(seed)
    layout = []
    for index in range(LEVEL_COUNT):
        digest = hashlib.sha256(f"e4-blind-probe:{seed}:{index}".encode()).digest()
        layout.append({"level": index + 1, "goal": [3 + digest[0] % 4, 3 + digest[1] % 4]})
    return layout


def route(spec):
    """The sibling helper the solver calls across the §7 import boundary."""
    goal_x, goal_y = spec["goal"]
    return ["ACTION4"] * (goal_x - PLAYER_X) + ["ACTION2"] * (goal_y - PLAYER_Y)


def _level(spec):
    goal_x, goal_y = spec["goal"]
    return Level(sprites=[
        Sprite([[WALL] * BOARD], name="wall_top", x=0, y=0),
        Sprite([[WALL] * BOARD], name="wall_bottom", x=0, y=BOARD - 1),
        Sprite([[WALL]] * (BOARD - 2), name="wall_left", x=0, y=1),
        Sprite([[WALL]] * (BOARD - 2), name="wall_right", x=BOARD - 1, y=1),
        Sprite([[GOAL]], name="goal", x=goal_x, y=goal_y, layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=PLAYER_X, y=PLAYER_Y, layer=2),
    ])


class ProbeGame(ARCBaseGame):
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

#: The OLD §7 skeleton pattern, verbatim in shape: the sibling game is loaded
#: BY PATH and cached in `sys.modules` under a name derived from THE PATH
#: ALONE. E-4 §The confirmed defect: "Every shipped solver carries it". The
#: prefix is a parameter because Addendum 1 ratifies PREFIX-AGNOSTIC matching
#: ("the checked-in fixtures plant non-'game_' prefixes").
_PROBE_SOLVER_SRC = '''"""Minimal §7 solver for the E-4 blind lane — the OLD PATH-keyed pattern."""

import hashlib
import importlib.util
import sys
from pathlib import Path

from arcengine import ActionInput, GameAction

_GAME_PATH = Path(__file__).resolve().with_name("game.py")
_GAME_TAG = hashlib.sha256(str(_GAME_PATH).encode()).hexdigest()[:12]

#: THE DEFECT, on purpose: keyed on the path, which a rewrite never changes.
_NAME = "__PREFIX__" + _GAME_TAG


def _game_module():
    module = sys.modules.get(_NAME)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(_NAME, _GAME_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build an import spec for {_GAME_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_NAME, None)
        raise
    return module


class Solver:
    def __init__(self, layout_seed=None):
        module = _game_module()
        #: what the DRIVEN PAIR saw — the §M1 measurement surface.
        self.probe = module.PROBE
        self.layout_seed = (
            module.DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        )
        self.plans = [module.route(spec) for spec in module.build_layout(self.layout_seed)]
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

#: The two sentinels. V2 is LONGER, so every rewrite below changes the file
#: size and the pyc layer cannot be the thing being measured.
PROBE_V1 = "v1"
PROBE_V2 = "v2-after-the-s2-rewrite"

#: A non-"game_" prefix, as the checked-in fixtures use (Addendum 1).
PROBE_PREFIX = "e4blind_game_"


def _write_probe_worker(worker: Path, probe: str = PROBE_V1, prefix: str = PROBE_PREFIX) -> Path:
    worker.mkdir(parents=True, exist_ok=True)
    (worker / "game.py").write_text(
        _PROBE_GAME_SRC.replace("__PROBE__", probe), encoding="utf-8"
    )
    (worker / "solver.py").write_text(
        _PROBE_SOLVER_SRC.replace("__PREFIX__", prefix), encoding="utf-8"
    )
    return worker


def _rewrite_probe_game(worker: Path, probe: str = PROBE_V2) -> None:
    (worker / "game.py").write_text(
        _PROBE_GAME_SRC.replace("__PROBE__", probe), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# the eviction helper's promised surface (E-4 §Work 1-2, Addendum 1)
# --------------------------------------------------------------------------- #


class TestEvictionSurface:
    def test_helper_exists_and_returns_what_it_dropped(self, tmp_path):
        """E-4 §Work 1: "one function ... `purge_worker_modules(worker_dir)`
        that computes the skeleton's derived module name(s) for that worker's
        game.py ... and drops them from sys.modules"."""
        assert callable(getattr(worker_mod, "purge_worker_modules", None)), (
            "E-4 §Work 1: the contract promises ONE eviction function "
            "`purge_worker_modules(worker_dir)` — gen.worker has no such callable"
        )
        worker = _write_probe_worker(tmp_path / "w")
        solver_cls = s3_static.load_worker_classes(worker)[1]
        solver_cls(layout_seed=4)  # the skeleton plants its path-keyed entry here

        planted = worker_mod.worker_module_names(worker)
        assert planted, (
            "E-4 §The confirmed defect: the §7 skeleton 'caches the game module in "
            "sys.modules keyed on the game.py PATH hash' — nothing was planted, so this "
            "lane cannot measure the defect at all"
        )
        evicted = worker_mod.purge_worker_modules(worker)
        assert tuple(evicted) == tuple(sorted(planted)), (
            "E-4 §Work 1: the helper must drop the skeleton's derived name(s) and say "
            f"which — planted {planted!r}, reported {evicted!r}"
        )
        for name in planted:
            assert name not in sys.modules, (
                f"E-4 §Work 1: {name!r} was reported evicted but is still in sys.modules"
            )

    def test_helper_accepts_a_str_as_well_as_a_path(self, tmp_path):
        """E-4 §Work 2: invoked "at the top of EVERY stage path" — the stages
        hold worker dirs in both spellings, so both must drive."""
        worker = _write_probe_worker(tmp_path / "w")
        solver_cls = s3_static.load_worker_classes(worker)[1]
        solver_cls(layout_seed=4)
        assert worker_mod.purge_worker_modules(str(worker)), (
            "E-4 §Work 2: a stage path holding the worker dir as a str must get the same "
            "eviction as one holding a Path"
        )

    def test_eviction_is_idempotent(self, tmp_path):
        """E-4 §Work 2: eviction is a precondition cleanup at the top of a
        stage path, so running it twice is not an error — the second call has
        simply nothing left to drop."""
        worker = _write_probe_worker(tmp_path / "w")
        solver_cls = s3_static.load_worker_classes(worker)[1]
        solver_cls(layout_seed=4)
        first = worker_mod.purge_worker_modules(worker)
        second = worker_mod.purge_worker_modules(worker)
        assert first and second == (), (
            "E-4 §Work 2: a second eviction on an already-clean worker must report nothing "
            f"dropped — got {second!r} after {first!r}"
        )

    def test_eviction_mirrors_the_skeletons_exact_derivation(self, tmp_path):
        """E-4 §Work 1: "It mirrors the skeleton's exact derivation (sha256 of
        the resolved path, first 12 hex — pin the parity so neither can drift
        alone)"."""
        worker = _write_probe_worker(tmp_path / "w")
        assert worker_mod.MODULE_TAG_CHARS == 12, (
            "E-4 §Work 1: the derivation keeps the 'first 12 hex' of the path digest — "
            f"gen.worker.MODULE_TAG_CHARS is {worker_mod.MODULE_TAG_CHARS}"
        )
        assert worker_mod.SKELETON_MODULE_PREFIX == "game_", (
            "E-4 §Work 1 / §The confirmed defect: the skeleton's derived name is "
            f"`game_<tag>` — the prefix constant is {worker_mod.SKELETON_MODULE_PREFIX!r}"
        )
        # The skeleton's own expression, from the SOLVER's side.
        spelled = (worker / "solver.py").resolve().with_name("game.py")
        expected = hashlib.sha256(str(spelled).encode("utf-8")).hexdigest()[:12]
        assert expected in worker_mod.worker_module_tags(worker), (
            "E-4 §Work 1: the helper must compute the SAME tag the skeleton derives from "
            f"`Path(__file__).resolve().with_name('game.py')` — {expected!r} missing from "
            f"{worker_mod.worker_module_tags(worker)!r}"
        )
        assert f"game_{expected}" in worker_mod.skeleton_module_names(worker), (
            "E-4 §Work 1: `game_<tag>` for that spelling must be one of the derived "
            "skeleton names"
        )

    def test_eviction_is_prefix_agnostic_on_the_path_tag(self, tmp_path):
        """E-4 Addendum 1: "the prefix-agnostic tag matching (the checked-in
        fixtures plant non-"game_" prefixes)"."""
        worker = _write_probe_worker(tmp_path / "w", prefix="totally_unrelated_prefix_")
        solver_cls = s3_static.load_worker_classes(worker)[1]
        solver_cls(layout_seed=4)
        planted = [n for n in sys.modules if n.startswith("totally_unrelated_prefix_")]
        assert planted, "the probe solver did not plant its entry — the pin cannot measure"
        evicted = worker_mod.purge_worker_modules(worker)
        assert set(planted) <= set(evicted), (
            "E-4 Addendum 1: matching is PREFIX-AGNOSTIC on the 12-hex path tag, so a "
            f"solver caching under {planted!r} must still be evicted — got {evicted!r}"
        )

    def test_eviction_spares_the_pipelines_own_loader_entries(self, tmp_path):
        """E-4 §Work 2: "The stat-keyed caches those loaders already have stay
        — eviction only clears the SKELETON's foreign entries"."""
        worker = _write_probe_worker(tmp_path / "w")
        s3_static.load_worker_classes(worker)
        own = sorted(
            name
            for name in sys.modules
            if name.startswith(("s3_game_", "s3_solver_"))
            and str(tmp_path) in (getattr(sys.modules[name], "__file__", None) or "")
        )
        assert own, (
            "the pipeline's own loader left no entry for this worker — the 'eviction only "
            "clears FOREIGN entries' claim cannot be measured"
        )
        evicted = worker_mod.purge_worker_modules(worker)
        assert not set(own) & set(evicted), (
            "E-4 §Work 2: eviction clears the SKELETON's foreign entries ONLY — it dropped "
            f"this pipeline's own {sorted(set(own) & set(evicted))!r}"
        )
        for name in own:
            assert name in sys.modules, (
                f"E-4 §Work 2: the pipeline's own entry {name!r} must survive eviction"
            )

    def test_eviction_does_not_change_a_missing_workers_error(self, tmp_path):
        """E-4 §Work 2: eviction runs "at the top of" a stage path, so it must
        not become the thing that reports a missing worker — the loader's own
        verdict has to survive."""
        missing = tmp_path / "not-a-worker"
        assert worker_mod.purge_worker_modules(missing) == (), (
            "E-4 §Work 2: eviction on a nonexistent worker dir is a no-op, not a failure"
        )
        with pytest.raises(NotADirectoryError):
            s3_static.load_worker_classes(missing)
        with pytest.raises(FileNotFoundError):
            s3_verify.load_worker_classes(missing)


# --------------------------------------------------------------------------- #
# §M1 — the demonstrated experiment, as a pin
# --------------------------------------------------------------------------- #


class TestM1Experiment:
    def test_path_keyed_cache_hit_diverges_from_a_fresh_load(self, tmp_path):
        """E-4 §M1: "path-keyed load -> rewrite -> fresh load differs from
        cache hit". §The confirmed defect: "Demonstrated in isolation: fresh
        load sees v2, the solver's cache hit sees v1"."""
        worker = _write_probe_worker(tmp_path / "w")
        solver_mod = _exec_file(worker / "solver.py")
        assert solver_mod._game_module().PROBE == PROBE_V1

        _rewrite_probe_game(worker)
        on_disk = _exec_file(worker / "game.py").PROBE
        cached = solver_mod._game_module().PROBE

        assert on_disk == PROBE_V2, (
            "E-4 §M1: the rewrite must be visible to a fresh load — 'fresh load sees v2'; "
            f"a fresh load read {on_disk!r}"
        )
        assert cached == PROBE_V1, (
            "E-4 §M1 / §The confirmed defect: the PATH-keyed cache hit must still serve the "
            f"OLD module ('the solver's cache hit sees v1') — it served {cached!r}. Without "
            "this divergence the defect this contract fixes no longer exists and every pin "
            "below is measuring nothing"
        )
        assert cached != on_disk, "E-4 §M1: 'fresh load differs from cache hit'"

    @pytest.mark.parametrize("site", sorted(CALL_SITES))
    def test_the_fix_makes_the_driven_pair_agree_with_disk(self, tmp_path, site):
        """E-4 §M1: "after the fix's eviction at each named call site, the
        driven pair agrees with the bytes on disk". Addendum 1 names them: the
        two shared pair loaders plus S6's own `_load_worker`."""
        _module, drive = CALL_SITES[site]
        worker = _write_probe_worker(tmp_path / "w" / "worker")

        first = drive(worker)(layout_seed=4).probe
        assert first == PROBE_V1, f"{site}: the first drive should see v1, saw {first!r}"

        _rewrite_probe_game(worker)
        after = drive(worker)(layout_seed=4).probe
        assert after == PROBE_V2, (
            f"E-4 §M1: at the named call site {site} 'the driven pair agrees with the bytes "
            f"on disk' — disk holds {PROBE_V2!r} and the driven solver planned against "
            f"{after!r} (the stale sys.modules entry the §7 skeleton planted)"
        )

    @pytest.mark.parametrize("site", SHARED_CALL_SITES)
    def test_negative_control_reverting_a_shared_loaders_eviction_desyncs_it(
        self, tmp_path, monkeypatch, site
    ):
        """E-4 §Pins: the desync scenario "is dead at every call site" — the
        control proves the pin can still SEE it. Addendum 1: eviction lives at
        "the TWO shared pair loaders"."""
        module, drive = CALL_SITES[site]
        _revert_eviction(monkeypatch, module)
        worker = _write_probe_worker(tmp_path / "w" / "worker")

        drive(worker)(layout_seed=4)
        _rewrite_probe_game(worker)
        after = drive(worker)(layout_seed=4).probe
        assert after == PROBE_V1, (
            f"NEGATIVE CONTROL for E-4 §M1 at {site}: with the eviction reverted the driven "
            f"pair must STILL be stale (that is the defect) — it read {after!r}. A control "
            "that passes means the pin above is not testing the eviction"
        )

    def test_negative_control_reverting_every_eviction_desyncs_s6s_entry_point(
        self, tmp_path, monkeypatch
    ):
        """E-4 §Pins + Addendum 1: S6's `_load_worker` sits in FRONT of the
        shared loader, so the pre-fix state at S6's entry point is every
        eviction reverted. (Reverting S6's alone is not enough on a forward
        rewrite — its stat cache misses and the shared loader purges on the
        way through; `TestM2OrderedControl` is the ordering that isolates
        S6's own purge.)"""
        _revert_eviction(monkeypatch, s3_static, s3_verify, s6_package)
        worker = _write_probe_worker(tmp_path / "w" / "worker")

        s6_package._load_worker(worker)[3](layout_seed=4)
        _rewrite_probe_game(worker)
        after = s6_package._load_worker(worker)[3](layout_seed=4).probe
        assert after == PROBE_V1, (
            "NEGATIVE CONTROL for E-4 §M1 at s6_package._load_worker: with eviction reverted "
            f"the pair must still desync — it read {after!r}"
        )

    def test_s4s_loader_is_s3_statics_by_identity(self):
        """E-4 Addendum 1: "s4's loader IS s3_static's, pinned by identity" —
        so covering the shared loader covers §Work 2's "S4's loader"."""
        assert s4_baselines.load_worker_classes is s3_static.load_worker_classes, (
            "E-4 Addendum 1: S4's pair loader IS `s3_static.load_worker_classes` (pinned by "
            "identity). If S4 grows its own loader it needs its own eviction and §Work 2's "
            "call-site list is incomplete"
        )

    def test_every_named_call_site_actually_calls_the_purge(self, tmp_path, monkeypatch):
        """E-4 §Work 2: the helper is "invoked at the top of EVERY stage path
        that exec-loads a worker pair in-process". A refactor that drops the
        call but keeps the import must fail here."""
        for site, (module, drive) in sorted(CALL_SITES.items()):
            seen: list[Path] = []
            real = worker_mod.purge_worker_modules

            def _spy(worker_dir, _seen=seen, _real=real):
                _seen.append(Path(worker_dir))
                return _real(worker_dir)

            monkeypatch.setattr(module, "purge_worker_modules", _spy)
            worker = _write_probe_worker(tmp_path / site.replace(".", "_") / "worker")
            drive(worker)
            monkeypatch.undo()
            assert any(path.resolve() == worker.resolve() for path in seen), (
                f"E-4 §Work 2: {site} must invoke purge_worker_modules for the worker it "
                f"loads — it was called with {seen!r} while loading {worker}"
            )


# --------------------------------------------------------------------------- #
# §M2 — the lantern class end-to-end
# --------------------------------------------------------------------------- #


class TestM2LanternClass:
    """E-4 §M2: "a worker pair whose solver uses the OLD skeleton pattern,
    driven through two S2-rewrite -> S6-validate cycles in ONE process".

    The pair is the checked-in `fixtures/s6_seeded` copy: its solver really
    does short-circuit on a path-keyed `sys.modules` entry (under the
    non-"game_" prefix `s6_seeded_game_`), so this is the shipped-solver class
    and not a synthesized imitation of it.
    """

    def test_the_fixture_solver_still_carries_the_old_skeleton_pattern(self):
        """E-4 §M2 precondition: the pair's solver must be an OLD-pattern one.
        If the fixture is ever modernised this lane is measuring nothing, and
        it must say so rather than go quietly green."""
        source = (S6_SEEDED / "solver.py").read_text(encoding="utf-8")
        assert "sys.modules.get(name)" in source and "st_mtime_ns" not in source, (
            "E-4 §M2 needs 'a worker pair whose solver uses the OLD skeleton pattern'. "
            f"{S6_SEEDED / 'solver.py'} no longer short-circuits on a path-keyed "
            "sys.modules entry, so §M2 below would no longer exercise the lantern class"
        )

    def test_two_cycles_in_one_process_pass_at_every_seed(self, tmp_path):
        """E-4 §M2: "with the fix, 5/5 pass" — across BOTH cycles, in ONE
        process, with the rewrite in between."""
        worker = _copy_fixture(tmp_path / "w" / "worker")
        cycle1 = _validate_cycle(worker)
        assert all(row["win"] for row in cycle1), (
            f"E-4 §M2 cycle 1 must be 5/5 before the rewrite — got {_signature(cycle1)}"
        )
        _rewrite_fixture_layout(worker)
        cycle2 = _validate_cycle(worker)
        assert all(row["win"] for row in cycle2), (
            "E-4 §M2: with the fix the second cycle is 5/5 too — the S2 rewrite landed and "
            f"the re-driven pair agreed with it. Got {_signature(cycle2)}; errors: "
            f"{[row['error'] for row in cycle2 if row['error']]}"
        )
        assert all(row["levels_completed"] == 6 for row in cycle2), (
            f"E-4 §M2: every seed completes every level — got {_signature(cycle2)}"
        )

    def test_negative_control_reverted_eviction_reproduces_the_signature(
        self, tmp_path, monkeypatch
    ):
        """E-4 §M2: "pre-fix behavior (reverted eviction) reproduces the
        all-seeds/0-levels signature". §The confirmed defect names it: "all
        seeds, 7 actions, 0 levels — seed-INDEPENDENT"."""
        _revert_eviction(monkeypatch, s3_static, s3_verify, s6_package)
        worker = _copy_fixture(tmp_path / "w" / "worker")

        cycle1 = _validate_cycle(worker)
        assert all(row["win"] for row in cycle1), (
            "E-4 §M2: the FIRST cycle passes even pre-fix (there is nothing stale yet) — "
            f"got {_signature(cycle1)}"
        )

        _rewrite_fixture_layout(worker)
        cycle2 = _validate_cycle(worker)

        assert not any(row["win"] for row in cycle2), (
            "NEGATIVE CONTROL for E-4 §M2: with eviction reverted the second cycle must "
            f"reject at EVERY seed — got {_signature(cycle2)}"
        )
        assert [row["levels_completed"] for row in cycle2] == [0] * len(SEEDS), (
            "NEGATIVE CONTROL for E-4 §M2: the signature is '0 levels' at every seed "
            f"(§The confirmed defect) — got {_signature(cycle2)}"
        )
        assert len({(row["win"], row["levels_completed"]) for row in cycle2}) == 1, (
            "NEGATIVE CONTROL for E-4 §M2: the signature is seed-INDEPENDENT — every seed "
            f"reaches the identical verdict. Got {_signature(cycle2)}"
        )

    def test_the_same_bytes_pass_once_the_module_table_is_clean(self, tmp_path, monkeypatch):
        """E-4 §The confirmed defect: "the same bytes pass 5/5 under S6's
        validator in a fresh process". The in-process equivalent of that fresh
        process is exactly what the eviction gives, so the SAME rewritten
        bytes that just produced 0/5 must go 5/5 after a purge — proving the
        reject was the module table and never the game."""
        _revert_eviction(monkeypatch, s3_static, s3_verify, s6_package)
        worker = _copy_fixture(tmp_path / "w" / "worker")
        _validate_cycle(worker)
        _rewrite_fixture_layout(worker)
        stale = _validate_cycle(worker)
        assert not any(row["win"] for row in stale), (
            f"the stale cycle should have rejected at every seed — got {_signature(stale)}"
        )

        digest_before = hashlib.sha256((worker / "game.py").read_bytes()).hexdigest()
        worker_mod.purge_worker_modules(worker)   # what a fresh process gives for free
        s6_package._WORKER_CACHE.clear()
        fresh = _validate_cycle(worker)
        digest_after = hashlib.sha256((worker / "game.py").read_bytes()).hexdigest()

        assert digest_before == digest_after, "the bytes must not change between the cycles"
        assert all(row["win"] for row in fresh), (
            "E-4 §The confirmed defect: 'the same bytes pass 5/5 under S6's validator in a "
            "fresh process'. The identical bytes went 0/5 with a stale module table and "
            f"must go 5/5 once it is evicted — got {_signature(fresh)}"
        )


class TestM2OrderedControl:
    """E-4 Addendum 1: S6's own `_load_worker` purge, "proven LOAD-BEARING by
    the ordered negative control (shared-only eviction still fails 0/5 behind
    S6's warm stat cache)".

    THE ORDERING that leaves S6's stat cache warm across a change, measured by
    this lane: an S2 REVERT to bytes this process already drove. `copy2`
    restores mtime_ns and size exactly, so S6's `(path, mtime_ns, size)` key
    matches a cycle it has already cached while the module table still holds
    the module from the cycle in between. The shared loader is then never
    reached, and only S6's own purge can break the desync.
    """

    @staticmethod
    def _three_cycles(worker: Path, pristine: Path) -> list[dict]:
        cycle1 = _validate_cycle(worker)
        assert all(row["win"] for row in cycle1), f"cycle 1: {_signature(cycle1)}"
        key_v1 = s6_package._stat_key((worker / "game.py").resolve())

        _rewrite_fixture_layout(worker)                      # S2 fix
        cycle2 = _validate_cycle(worker)
        assert all(row["win"] for row in cycle2), f"cycle 2: {_signature(cycle2)}"

        shutil.copy2(pristine, worker / "game.py")           # S2 REVERT, stat preserved
        key_back = s6_package._stat_key((worker / "game.py").resolve())
        assert key_back == key_v1, (
            "this control needs S6's stat cache WARM across the revert: the restored "
            f"game.py must stat identically to cycle 1's ({key_v1} vs {key_back})"
        )
        return _validate_cycle(worker)

    def test_shared_only_eviction_still_fails_behind_s6s_warm_stat_cache(
        self, tmp_path, monkeypatch
    ):
        """E-4 Addendum 1: "shared-only eviction still fails 0/5 behind S6's
        warm stat cache" — the control that makes S6's own purge load-bearing
        instead of belt-and-braces."""
        _revert_eviction(monkeypatch, s6_package)   # the TWO shared loaders still evict
        worker = _copy_fixture(tmp_path / "w" / "worker")
        pristine = tmp_path / "pristine-game.py"
        shutil.copy2(worker / "game.py", pristine)

        rows = self._three_cycles(worker, pristine)
        assert not any(row["win"] for row in rows), (
            "E-4 Addendum 1 ORDERED NEGATIVE CONTROL: with S6's own `_load_worker` purge "
            "reverted and only the shared loaders evicting, the drive behind S6's warm stat "
            f"cache must still fail at every seed — got {_signature(rows)}"
        )
        assert [row["levels_completed"] for row in rows] == [0] * len(SEEDS), (
            f"E-4 Addendum 1: the failure is the same 0-levels signature — {_signature(rows)}"
        )

    def test_s6s_own_purge_fixes_that_same_ordering(self, tmp_path):
        """E-4 Addendum 1: S6's `_load_worker` purge is what makes a cache HIT
        re-read `game.py` from disk — same ordering, every eviction live."""
        worker = _copy_fixture(tmp_path / "w" / "worker")
        pristine = tmp_path / "pristine-game.py"
        shutil.copy2(worker / "game.py", pristine)

        rows = self._three_cycles(worker, pristine)
        assert all(row["win"] for row in rows), (
            "E-4 Addendum 1: with S6's own purge live, the same ordering passes at every "
            f"seed — got {_signature(rows)}; errors: "
            f"{[row['error'] for row in rows if row['error']]}"
        )


# --------------------------------------------------------------------------- #
# §M3 — the NEW taught skeleton
# --------------------------------------------------------------------------- #


def _taught_solver_source() -> str:
    """The solver skeleton the §7 payload TEACHES, lifted verbatim.

    E-4 §M3 pins "the payload's taught loader, exec'd as written", so the text
    is read out of the payload itself rather than copied into this file: a
    payload edit cannot leave this pin testing yesterday's skeleton.
    """
    blocks = re.findall(r"```python\n(.*?)```", s2_implement.LAYOUT_SEED_CONTRACT, re.DOTALL)
    solvers = [block for block in blocks if "_game_module" in block]
    assert len(solvers) == 1, (
        "E-4 §M3 needs 'the payload's taught loader' — found "
        f"{len(solvers)} candidate solver skeleton(s) in "
        "s2_implement.LAYOUT_SEED_CONTRACT, so this lane cannot say which one is taught"
    )
    return solvers[0]


class TestM3TaughtSkeleton:
    def test_the_taught_loader_survives_an_in_process_rewrite_with_no_eviction(self, tmp_path):
        """E-4 §M3: "the payload's taught loader, exec'd as written, survives
        a rewrite in-process (no eviction needed for NEW solvers)". §Work 3:
        the skeleton "becomes staleness-proof — key the cache on (path,
        mtime_ns, size)"."""
        worker = tmp_path / "w"
        worker.mkdir()
        (worker / "game.py").write_text(
            f'PROBE = "{PROBE_V1}"\nDEFAULT_LAYOUT_SEED = 1\n', encoding="utf-8"
        )
        (worker / "solver.py").write_text(_taught_solver_source(), encoding="utf-8")

        taught = _exec_file(worker / "solver.py")
        assert taught._game_module().PROBE == PROBE_V1

        # A size-changing rewrite, as a real S2 fix is (see the module docstring).
        (worker / "game.py").write_text(
            f'PROBE = "{PROBE_V2}"\nDEFAULT_LAYOUT_SEED = 1\n', encoding="utf-8"
        )
        after = taught._game_module().PROBE
        assert after == PROBE_V2, (
            "E-4 §M3: the TAUGHT skeleton must survive an in-process rewrite with NO "
            f"eviction — the same loader object read {after!r} while disk held {PROBE_V2!r}. "
            "A new solver that needs the pipeline's help is not staleness-proof (§Work 3)"
        )

    def test_negative_control_the_old_skeleton_shape_stays_stale(self, tmp_path):
        """E-4 §M3's control: the OLD shape, same experiment, must still go
        stale — otherwise the §M3 pin above would pass for any skeleton."""
        worker = _write_probe_worker(tmp_path / "w")
        solver_mod = _exec_file(worker / "solver.py")
        assert solver_mod._game_module().PROBE == PROBE_V1
        _rewrite_probe_game(worker)
        after = solver_mod._game_module().PROBE
        assert after == PROBE_V1, (
            "NEGATIVE CONTROL for E-4 §M3: the OLD path-keyed shape must STILL be stale "
            f"after the same rewrite — it read {after!r}, so the §M3 experiment does not "
            "discriminate between the two skeletons"
        )

    def test_taught_skeleton_entries_stay_visible_to_the_tag_sweep(self, tmp_path):
        """E-4 Addendum 1: "the stat-in-NAME scheme (keeps new-style entries
        visible to the tag sweep)"."""
        worker = tmp_path / "w"
        worker.mkdir()
        (worker / "game.py").write_text('DEFAULT_LAYOUT_SEED = 1\n', encoding="utf-8")
        (worker / "solver.py").write_text(_taught_solver_source(), encoding="utf-8")

        before = set(sys.modules)
        _exec_file(worker / "solver.py")._game_module()
        planted = sorted(set(sys.modules) - before)
        assert len(planted) == 1, (
            f"the taught loader should plant exactly one entry — planted {planted!r}"
        )
        seen = worker_mod.worker_module_names(worker)
        assert planted[0] in seen, (
            "E-4 Addendum 1: the stat-in-NAME scheme keeps new-style entries visible to the "
            f"tag sweep — {planted[0]!r} is not in {seen!r}, so a worker whose NEW solver "
            "cached a module would be left behind by the eviction"
        )
        assert planted[0] in worker_mod.purge_worker_modules(worker), (
            "E-4 Addendum 1: a visible new-style entry must also be evictable"
        )


# --------------------------------------------------------------------------- #
# the derivation-parity pin (E-4 §Work 1, §Pins)
# --------------------------------------------------------------------------- #


class TestDerivationParity:
    """E-4 §Work 1: "pin the parity so neither can drift alone"; §Pins: "the
    derivation-parity pin". Mutating EITHER side in a copy must be caught.
    """

    def test_the_skeletons_planted_name_is_exactly_a_derived_name(self, tmp_path):
        worker = _write_probe_worker(tmp_path / "w", prefix="game_")
        before = set(sys.modules)
        _exec_file(worker / "solver.py")._game_module()
        planted = sorted(set(sys.modules) - before)
        assert len(planted) == 1, f"expected one planted entry, got {planted!r}"
        assert planted[0] in worker_mod.skeleton_module_names(worker), (
            "E-4 §Work 1: the helper 'mirrors the skeleton's exact derivation' — the name "
            f"the skeleton actually planted ({planted[0]!r}) is not among the derived names "
            f"{worker_mod.skeleton_module_names(worker)!r}. The two have drifted apart"
        )

    def test_drift_in_a_copy_of_the_skeleton_is_caught(self, tmp_path):
        """E-4 §Work 1: "so neither can drift alone" — the SKELETON side."""
        worker = _write_probe_worker(tmp_path / "w", prefix="game_")
        drifted = (worker / "solver.py").read_text(encoding="utf-8").replace(
            'hexdigest()[:12]', 'hexdigest()[:11]'
        )
        assert "[:11]" in drifted, "the drift edit did not apply — the pin would be vacuous"
        (worker / "solver.py").write_text(drifted, encoding="utf-8")

        before = set(sys.modules)
        _exec_file(worker / "solver.py")._game_module()
        planted = sorted(set(sys.modules) - before)
        assert len(planted) == 1, f"expected one planted entry, got {planted!r}"
        assert planted[0] not in worker_mod.skeleton_module_names(worker), (
            "E-4 §Work 1 derivation-parity CONTROL: a skeleton whose derivation drifted "
            f"(11 hex instead of 12) must NOT match the helper's derived names — "
            f"{planted[0]!r} matched anyway, so the parity pin above cannot see drift"
        )
        assert planted[0] not in worker_mod.worker_module_names(worker), (
            "E-4 §Work 1: a drifted name is also invisible to the tag sweep, which is "
            "precisely why the parity must be pinned rather than assumed"
        )

    def test_drift_on_the_purge_side_is_caught(self, tmp_path, monkeypatch):
        """E-4 §Work 1: "so neither can drift alone" — the HELPER side."""
        worker = _write_probe_worker(tmp_path / "w", prefix="game_")
        before = set(sys.modules)
        _exec_file(worker / "solver.py")._game_module()
        entries = sorted(set(sys.modules) - before)
        assert len(entries) == 1, f"expected one planted entry, got {entries!r}"
        planted = entries[0]
        assert planted in worker_mod.skeleton_module_names(worker)

        monkeypatch.setattr(worker_mod, "MODULE_TAG_CHARS", 11)
        assert planted not in worker_mod.skeleton_module_names(worker), (
            "E-4 §Work 1 derivation-parity CONTROL: with the HELPER's derivation drifted to "
            "11 hex, the skeleton's real name must stop matching — it still matched, so the "
            "parity pin is insensitive to a change on the pipeline side"
        )


# --------------------------------------------------------------------------- #
# §M4 — S2b's staged-path immunity
# --------------------------------------------------------------------------- #


class TestM4StagedPathImmunity:
    """E-4 §M4: "S2b's staged-path immunity stays (different path, different
    key — pin it so a refactor cannot merge the paths silently)". §Work 2 says
    the same: "S2b drives the STAGED copy at a different path — different key,
    inherently safe, note it".
    """

    @staticmethod
    def _stage(worker: Path) -> Path:
        dest = worker.with_name(worker.name + s3_verify.STAGED_SUFFIX)
        s3_verify.stage_worker_copy(worker, dest)
        return dest

    def test_the_staged_copy_is_a_sibling_at_a_different_path(self, tmp_path):
        """E-4 §M4: a refactor that staged the audit IN PLACE would silently
        merge the keys, so the different-path property is pinned here."""
        worker = _write_probe_worker(tmp_path / "w" / "worker")
        staged = self._stage(worker)
        assert staged.resolve() != worker.resolve(), (
            "E-4 §M4: S2b drives 'the STAGED copy at a different path' — the staged copy "
            f"resolved to the worker itself ({staged})"
        )
        assert worker.resolve() not in staged.resolve().parents, (
            "E-4 §M4: the staged copy is a SIBLING, never a child of the worker"
        )
        with pytest.raises(ValueError):
            s3_verify.stage_worker_copy(worker, worker / "inside")

    def test_staged_copy_tags_are_disjoint_from_the_workers(self, tmp_path):
        """E-4 §M4: "different path, different key"."""
        worker = _write_probe_worker(tmp_path / "w" / "worker")
        staged = self._stage(worker)
        worker_tags = set(worker_mod.worker_module_tags(worker))
        staged_tags = set(worker_mod.worker_module_tags(staged))
        assert worker_tags and staged_tags, "both tag sets must be non-empty"
        assert worker_tags.isdisjoint(staged_tags), (
            "E-4 §M4: the staged copy sits at a different path and therefore derives "
            f"different keys — the two tag sets overlap on "
            f"{sorted(worker_tags & staged_tags)!r}, so an S2b audit and a stage drive "
            "would share a sys.modules entry"
        )

    def test_neither_purge_can_reach_the_others_entries(self, tmp_path):
        """E-4 §M4: staged-path immunity is mutual — the audit cannot evict the
        worker's module and a stage cannot evict the audit's."""
        worker = _write_probe_worker(tmp_path / "w" / "worker")
        staged = self._stage(worker)

        s3_static.load_worker_classes(worker)[1](layout_seed=4)
        s3_static.load_worker_classes(staged)[1](layout_seed=4)
        worker_names = set(worker_mod.worker_module_names(worker))
        staged_names = set(worker_mod.worker_module_names(staged))
        assert worker_names and staged_names and worker_names.isdisjoint(staged_names), (
            "E-4 §M4: each path plants its OWN entry — "
            f"worker {sorted(worker_names)!r} vs staged {sorted(staged_names)!r}"
        )

        assert set(worker_mod.purge_worker_modules(staged)) == staged_names, (
            "E-4 §M4: purging the staged copy touches the staged entries only"
        )
        assert set(worker_mod.worker_module_names(worker)) == worker_names, (
            "E-4 §M4: 'inherently safe' — purging the staged copy must leave the worker's "
            f"own entries alone; {sorted(worker_names)!r} did not survive"
        )
        assert set(worker_mod.purge_worker_modules(worker)) == worker_names


# --------------------------------------------------------------------------- #
# THE PYC BELT (E-4 Addendum 1, "the one-line belt is LICENSED")
# --------------------------------------------------------------------------- #


class TestBelt:
    """E-4 Addendum 1: "purge also removes the worker's __pycache__, with its
    own red/green pin". The layer it defends is the one §The confirmed defect
    records: "pyc validation is mtime-seconds+size, so a same-size same-second
    rewrite can serve stale bytecode even to fresh loads".
    """

    @staticmethod
    def _plant_pyc(worker: Path) -> Path:
        """Load `game.py` once so CPython writes the worker's `__pycache__`.

        Bytecode writing is forced ON for the duration: a `-B` interpreter
        would otherwise make the red leg below silently un-measurable.
        """
        worker.mkdir(parents=True, exist_ok=True)
        (worker / "game.py").write_text(f'PROBE = "{PROBE_V1}"\n', encoding="utf-8")
        saved = sys.dont_write_bytecode
        sys.dont_write_bytecode = False
        try:
            assert _exec_file(worker / "game.py").PROBE == PROBE_V1
        finally:
            sys.dont_write_bytecode = saved
        cache = worker / "__pycache__"
        assert cache.is_dir() and any(cache.iterdir()), (
            "E-4 Addendum 1: 'real workers DO carry __pycache__ (make validate writes it)' — "
            f"no bytecode cache appeared at {cache}, so the belt's red/green pins cannot be "
            "measured in this interpreter"
        )
        return cache

    @staticmethod
    def _same_size_same_second_rewrite(worker: Path) -> None:
        """The §The-confirmed-defect scenario, forced: identical size, and the
        source's mtime restored so the pyc's seconds+size check still passes.
        """
        path = worker / "game.py"
        before = path.stat()
        replacement = f'PROBE = "{"x" * len(PROBE_V1)}"\n'
        path.write_text(replacement, encoding="utf-8")
        assert path.stat().st_size == before.st_size, "the rewrite must keep the byte count"
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

    def test_negative_control_a_same_size_same_second_rewrite_is_served_stale(self, tmp_path):
        """E-4 §The confirmed defect: "a same-size same-second rewrite can
        serve stale bytecode even to fresh loads". The RED leg: without the
        belt, a brand-new module name still gets v1."""
        worker = tmp_path / "w"
        self._plant_pyc(worker)
        self._same_size_same_second_rewrite(worker)
        served = _exec_file(worker / "game.py").PROBE
        assert served == PROBE_V1, (
            "RED LEG for E-4 Addendum 1's belt: a same-size same-second rewrite must still "
            f"be served the STALE bytecode by a fresh load — it read {served!r}. Without "
            "this the belt's green leg below is measuring nothing"
        )

    def test_the_purge_makes_that_same_rewrite_go_fresh(self, tmp_path):
        """E-4 Addendum 1: "purge_worker_modules also removes the worker's
        __pycache__ ... so no stale pyc survives an eviction"."""
        worker = tmp_path / "w"
        cache = self._plant_pyc(worker)
        self._same_size_same_second_rewrite(worker)

        worker_mod.purge_worker_modules(worker)
        assert not cache.exists(), (
            "E-4 Addendum 1: 'purge also removes the worker's __pycache__' — "
            f"{cache} survived purge_worker_modules"
        )
        served = _exec_file(worker / "game.py").PROBE
        assert served == "x" * len(PROBE_V1), (
            "GREEN LEG for E-4 Addendum 1's belt: after the purge the same rewrite must be "
            f"compiled from SOURCE — the load still read {served!r}"
        )

    def test_the_belt_reports_what_it_removed(self, tmp_path):
        """E-4 Addendum 1 names the belt as its own seam, so its result is a
        surface this lane drives directly."""
        worker = tmp_path / "w"
        cache = self._plant_pyc(worker)
        removed = worker_mod.purge_worker_bytecode(worker)
        assert tuple(removed) == (cache,), (
            f"E-4 Addendum 1: the belt reports the cache dir it removed — got {removed!r}"
        )
        assert not cache.exists()

    def test_the_belt_refuses_a_symlinked_pycache(self, tmp_path):
        """E-4 Addendum 1: the belt is "symlink-refusing" — nothing outside the
        worker tree may be reached through it."""
        worker = tmp_path / "w"
        worker.mkdir()
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        keep = outside / "do-not-delete.txt"
        keep.write_text("precious", encoding="utf-8")
        link = worker / "__pycache__"
        link.symlink_to(outside, target_is_directory=True)

        assert worker_mod.purge_worker_bytecode(worker) == (), (
            "E-4 Addendum 1: a symlinked __pycache__ is REFUSED, not followed — the belt "
            "reported a removal"
        )
        assert keep.exists() and keep.read_text(encoding="utf-8") == "precious", (
            "E-4 Addendum 1: symlink-refusing — the belt reached outside the worker tree and "
            f"deleted {keep}"
        )
        assert link.is_symlink(), "the refused link itself is left as it was"
        assert worker_mod.purge_worker_modules(worker) == (), (
            "E-4 Addendum 1: the belt's refusal must not turn the purge into a failure"
        )

    def test_the_belt_tolerates_an_absent_pycache(self, tmp_path):
        """E-4 Addendum 1: the belt is "absence-tolerant"."""
        worker = tmp_path / "w"
        worker.mkdir()
        assert worker_mod.purge_worker_bytecode(worker) == (), (
            "E-4 Addendum 1: absence-tolerant — a worker with no __pycache__ is nothing to "
            "do, not an error"
        )
        assert worker_mod.purge_worker_bytecode(tmp_path / "never-existed") == (), (
            "E-4 Addendum 1: absence-tolerant extends to a worker dir that is not there — "
            "eviction runs at the TOP of a stage path (§Work 2), before any existence "
            "verdict the loader owns"
        )

    def test_the_belt_touches_only_the_workers_own_cache(self, tmp_path):
        """E-4 Addendum 1: "the worker's __pycache__" — the one beside the pair
        this pipeline loads, not every cache in the tree."""
        worker = tmp_path / "w"
        cache = self._plant_pyc(worker)
        nested = worker / "tests" / "__pycache__"
        nested.mkdir(parents=True)
        (nested / "marker.txt").write_text("scaffold pytest", encoding="utf-8")
        sibling = tmp_path / "__pycache__"
        sibling.mkdir()

        worker_mod.purge_worker_bytecode(worker)
        assert not cache.exists(), "the worker's own cache goes"
        assert nested.is_dir() and (nested / "marker.txt").exists(), (
            "E-4 Addendum 1: the belt removes 'the worker's __pycache__' — it reached into "
            f"{nested}, which belongs to the scaffold's own pytest"
        )
        assert sibling.is_dir(), (
            f"E-4 Addendum 1: the belt must stay inside the worker — {sibling} was removed"
        )

    @staticmethod
    def _probe_worker_with_a_warm_pyc(worker: Path) -> Path:
        """A probe worker loaded once through the real call site, pyc written.

        Then `game.py` is rewritten SAME-SIZE and its mtime restored, so the
        only thing that can still serve v1 is the bytecode cache: both
        sentinels are two characters wide, so the file's byte count is
        unchanged and §The confirmed defect's seconds+size validator passes.
        """
        _write_probe_worker(worker, probe="v1")
        saved = sys.dont_write_bytecode
        sys.dont_write_bytecode = False
        try:
            s3_static.load_worker_classes(worker)
        finally:
            sys.dont_write_bytecode = saved
        cache = worker / "__pycache__"
        assert cache.is_dir() and any(path.name.startswith("game.") for path in cache.iterdir()), (
            "E-4 Addendum 1: 'real workers DO carry __pycache__' — the pipeline's own load "
            f"left no game bytecode at {cache}, so this pin cannot be measured"
        )
        before = (worker / "game.py").stat()
        _rewrite_probe_game(worker, probe="v2")
        assert (worker / "game.py").stat().st_size == before.st_size, (
            "this pin needs a SAME-SIZE rewrite; the two sentinels are both two characters"
        )
        os.utime(worker / "game.py", ns=(before.st_atime_ns, before.st_mtime_ns))
        return worker

    def test_negative_control_without_the_belt_a_call_site_serves_stale_bytecode(
        self, tmp_path, monkeypatch
    ):
        """E-4 Addendum 1's RED leg at a real call site: evicting the module
        table alone is NOT the same fix, because "pyc validation is
        mtime-seconds+size" (§The confirmed defect)."""
        worker = self._probe_worker_with_a_warm_pyc(tmp_path / "w" / "worker")
        monkeypatch.setattr(worker_mod, "purge_worker_bytecode", lambda worker_dir: ())
        served = s3_static.load_worker_classes(worker)[1](layout_seed=4).probe
        assert served == "v1", (
            "RED LEG for E-4 Addendum 1: with only the module-table eviction, a same-size "
            f"same-second rewrite is still served stale through the pyc — it read {served!r}. "
            "Without this the green leg below is measuring nothing"
        )

    def test_a_pipeline_call_site_clears_the_bytecode_too(self, tmp_path):
        """E-4 §Work 2 + Addendum 1: the belt sits "at the same seam" as the
        eviction, so a stage path that evicts leaves no stale pyc behind —
        "no stale pyc survives an eviction"."""
        worker = self._probe_worker_with_a_warm_pyc(tmp_path / "w" / "worker")
        served = s3_static.load_worker_classes(worker)[1](layout_seed=4).probe
        assert served == "v2", (
            "E-4 Addendum 1 GREEN leg: the belt runs at the eviction seam, so a stage path "
            "that re-loads the pair compiles the worker's game from SOURCE even when the "
            f"rewrite kept the size and the second — the driven pair read {served!r} while "
            "disk held 'v2'"
        )
