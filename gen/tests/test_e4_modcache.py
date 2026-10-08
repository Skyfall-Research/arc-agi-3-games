"""Contract E-4 — the §7 module-cache eviction. The IMPLEMENTER's battery.

The defect, in one sentence: the §7 solver skeleton caches its sibling game in
`sys.modules` under a name derived from the game's PATH, and an S2 rewrite does
not change the path — so in one long-lived batch process the next in-process
drive pairs a FRESH game with a solver that planned against the OLD layout.
Measured consequence: lantern-path-parity-trace's seed-INDEPENDENT 5/5
seed-reject (few actions, 0 levels at every seed) whose same bytes pass 5/5 in
a fresh interpreter.

What is pinned here, in groups:

1. DERIVATION PARITY. `gen/worker.worker_module_tags` mirrors the skeleton's
   own name derivation. The pin never re-types the formula: it EXECUTES the
   legacy loader (the pattern every shipped solver carries) and the two
   checked-in fixture solvers, and asserts the names they really plant are the
   names the helper claims. Either side drifting alone fails here.
2. THE DESYNC IS DEAD AT EVERY CALL SITE from work item 2, measured as
   load -> rewrite -> reload -> the solver agrees with the bytes on disk, plus
   a wiring pin per call site and a SWEEP pin that fails if a new in-process
   exec-loader appears in `gen/` without being considered here.
3. THE TWO-CYCLE FAKE BATCH (S2 fix -> S6 revalidate in ONE process) passes
   5/5 seeds, and its NEGATIVE CONTROL: with the eviction reverted the same
   bytes reproduce the lantern signature — 0/5 wins, 0 levels at every seed.
4. S2b's staged copy stays immune for the reason it always was (a DIFFERENT
   path is a different key), pinned so a refactor cannot merge the two paths
   silently.
5. THE RECORDED LIMIT. CPython validates a `.pyc` on mtime-SECONDS + size, so
   a same-size rewrite inside one second can serve stale BYTECODE even to a
   genuinely fresh load. Eviction does not touch that layer; the limit is
   reproduced here deterministically and the record of it in `gen/worker.py` is
   pinned so it cannot be deleted quietly. Group 5 is the only place a
   same-size rewrite appears: every other rewrite here CHANGES THE FILE'S SIZE
   (`_rewrite` asserts it for the worker rewrites), so groups 2-3 and 6 measure
   the module cache and never the bytecode cache.
6. THE NEW TAUGHT SKELETON (work item 3): the payload's own solver loader,
   extracted and exec'd AS WRITTEN, survives an in-process rewrite with no
   eviction at all — and a regression to the path-keyed lookup fails here.

Hermetic: every worker is a tmp copy, nothing is written under `out/` or
`games/`, no driver and no network. The module table is restored after each
test by the autouse fixture below.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest

from gen import (
    frames,
    s2_implement,
    s3_gate,
    s3_static,
    s3_verify,
    s4_baselines,
    s5_battery,
    s6_package,
)
from gen import worker as worker_mod
from gen.worker import (
    PIPELINE_MODULE_PREFIXES,
    purge_worker_modules,
    skeleton_module_names,
    worker_module_names,
    worker_module_tags,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SEEDED = FIXTURES / "s6_seeded"
SEEDED_BROKEN = FIXTURES / "s6_seeded_broken"

#: The authored default (the fixture's `DEFAULT_LAYOUT_SEED`) plus four others:
#: the SHAPE of S6's real validation list (`validation_seeds`) without needing a
#: batch config to derive it.
SEEDS = (13, 101, 202, 303, 404)

#: The fixture's layout namespace, and the "S2 fix" this battery applies to it.
#: Changing the namespace changes the GEOMETRY at every seed while the authored
#: seed stays put — which is what makes a stale plan fail seed-INDEPENDENTLY,
#: the lantern signature. It is also longer than the original, so the `.pyc`
#: layer of group 5 can never be what group 3 is measuring.
NAMESPACE_V1 = '"s6-seeded-gate/layout/v1"'
NAMESPACE_V2 = '"s6-seeded-gate/layout/v2-after-the-s2-fix"'

#: The same idea for a load that must not even construct the engine: the game's
#: authored default seed, which the §7 solver reads straight off the module it
#: loaded (`mod.DEFAULT_LAYOUT_SEED`). So `Solver().layout_seed` IS a one-line
#: readout of which bytes the solver's own loader served.
SEED_LINE_V1 = "DEFAULT_LAYOUT_SEED = 13"
SEED_LINE_V2 = "DEFAULT_LAYOUT_SEED = 1300000007"
SEED_V2 = 1300000007

# The PRE-E-4 skeleton's loader, verbatim — the pattern `out/corpus/*/worker/
# solver.py` carries in every shipped game (lantern's solver.py:13-25 is this
# code) and the one the eviction exists to protect. Kept as a literal because
# the payload no longer teaches it (work item 3) while shipped solvers keep it
# forever; group 1 also runs the two checked-in fixture solvers, so this copy
# cannot be the only thing the parity claim rests on.
LEGACY_SOLVER = '''\
"""A solver carrying the PRE-E-4 §7 sibling-loader, path-keyed."""

import hashlib
import importlib.util
import sys
from pathlib import Path

_GAME_PATH = Path(__file__).resolve().with_name("game.py")


def _game_module():
    name = "game_" + hashlib.sha256(str(_GAME_PATH).encode()).hexdigest()[:12]
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, _GAME_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


class Solver:
    def __init__(self, layout_seed=None):
        mod = _game_module()
        self.layout_seed = mod.DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
'''

#: A game.py with no engine in it at all: group 1 is about module NAMES, and a
#: real `ARCBaseGame` would make the parity pin pay for an engine import it
#: does not read.
BARE_GAME = "DEFAULT_LAYOUT_SEED = 13\nMARK = \"v1\"\n"


# --- hermeticity ------------------------------------------------------------


@pytest.fixture(autouse=True)
def module_table_restored():
    """Drop every module this test exec-loaded from a tmp worker.

    A leaked `game_<tag>` entry is precisely the defect under test, so leaking
    one into the rest of the suite would be the worst possible teardown. Keys
    are dropped when the module's `__file__` lives outside this repo, outside
    the venv and outside the interpreter's own stdlib (i.e. under pytest's tmp
    root), plus any of this pipeline's own loader names, which are re-created
    on demand by design. `base_prefix` is in that keep list deliberately: in a
    venv the stdlib lives there, and dropping a stdlib module another test
    lazily imported would be a far worse side effect than the leak.
    """
    before = set(sys.modules)
    keep_under = (
        str(REPO_ROOT),
        str(Path(sys.prefix).resolve()),
        str(Path(sys.base_prefix).resolve()),
    )
    s6_package._WORKER_CACHE.clear()
    try:
        yield
    finally:
        for name in set(sys.modules) - before:
            module = sys.modules.get(name)
            source = getattr(module, "__file__", None) or ""
            if name.startswith(PIPELINE_MODULE_PREFIXES) or (
                source and not source.startswith(keep_under)
            ):
                del sys.modules[name]
        s6_package._WORKER_CACHE.clear()


# --- helpers ----------------------------------------------------------------


def _copy(source: Path, dest: Path) -> Path:
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def _seeded(tmp_path: Path, name: str = "worker") -> Path:
    """A tmp copy of the §7 reference fixture — engine-valid, wins at any seed."""
    return _copy(SEEDED, tmp_path / name)


def _rewrite(worker: Path, old: str, new: str) -> None:
    """THE S2 FIX, applied in place — and proved to change the file's SIZE.

    Same-size rewrites are the `.pyc` hazard of group 5, which eviction does
    not fix; a group-2 or group-3 measurement that tripped over it would be
    measuring the wrong layer. So the size change is asserted here, once, for
    every rewrite in this file.
    """
    game = worker / "game.py"
    text = game.read_text(encoding="utf-8")
    assert old in text, f"{game}: nothing to rewrite — {old!r} is not in the fixture"
    size_before = game.stat().st_size
    game.write_text(text.replace(old, new), encoding="utf-8")
    assert game.stat().st_size != size_before, (
        "this battery's rewrites must change the file size so the pyc layer "
        "(group 5) can never be what groups 2-3 measure"
    )


def _bare_worker(tmp_path: Path, name: str = "legacy") -> Path:
    """A worker whose solver carries the legacy path-keyed loader."""
    worker = tmp_path / name
    worker.mkdir()
    (worker / "game.py").write_text(BARE_GAME, encoding="utf-8")
    (worker / "solver.py").write_text(LEGACY_SOLVER, encoding="utf-8")
    return worker


def _exec_solver(worker: Path, name: str):
    """Exec-load a solver.py the way `s3_static._load_module` does."""
    spec = importlib.util.spec_from_file_location(name, worker / "solver.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _validate(worker: Path, seeds=SEEDS) -> list[dict]:
    return [s6_package.validate_seed(worker, seed) for seed in seeds]


def _signature(rows: list[dict]) -> list[tuple]:
    return [(row["seed"], row["win"], row["levels_completed"]) for row in rows]


def _reverted(*_args, **_kwargs) -> tuple:
    """The PRE-E-4 behaviour, exactly: evict nothing. The negative control."""
    return ()


# --- 1. derivation parity ---------------------------------------------------


def test_1_the_legacy_skeletons_own_name_is_one_the_helper_derives(tmp_path):
    """THE PARITY PIN. The legacy loader is EXECUTED and the name it plants is
    compared against the helper's derivation — neither side can drift alone."""
    worker = _bare_worker(tmp_path)
    solver_module = _exec_solver(worker, "e4_legacy_solver")

    planted = solver_module._game_module().__name__

    assert planted in skeleton_module_names(worker), (
        f"the skeleton planted {planted!r} and gen/worker.skeleton_module_names claims "
        f"{skeleton_module_names(worker)} — the derivation has drifted from the taught code"
    )
    assert planted in worker_module_names(worker), (
        f"{planted!r} is registered and belongs to this worker, so the sweep must claim it"
    )
    assert purge_worker_modules(worker) == (planted,)
    assert planted not in sys.modules
    assert purge_worker_modules(worker) == (), "eviction must be idempotent"


def test_1_the_eviction_really_is_what_makes_the_legacy_loader_reread_disk(tmp_path):
    """The mechanism, isolated: cache hit serves v1, eviction forces the reread."""
    worker = _bare_worker(tmp_path)
    solver_module = _exec_solver(worker, "e4_legacy_solver_reread")
    assert solver_module._game_module().MARK == "v1"

    (worker / "game.py").write_text(BARE_GAME.replace('"v1"', '"v2-rewritten"'), encoding="utf-8")

    assert solver_module._game_module().MARK == "v1", (
        "premise: a path-keyed cache hit must still serve the OLD module — if this ever "
        "stops being true the defect is gone and this battery is measuring nothing"
    )
    purge_worker_modules(worker)
    assert solver_module._game_module().MARK == "v2-rewritten"


@pytest.mark.parametrize("fixture", [SEEDED, SEEDED_BROKEN], ids=["s6_seeded", "s6_seeded_broken"])
def test_1_the_checked_in_fixtures_custom_prefixes_are_covered(tmp_path, fixture):
    """WHY THE SWEEP IS PREFIX-AGNOSTIC. Both fixtures key on the same path tag
    under their OWN prefix (`s6_seeded_game_<tag>`), which a `"game_"`-exact
    eviction would miss entirely — and these are the solvers the S6 suite
    drives."""
    worker = _copy(fixture, tmp_path / "worker")
    _game_cls, solver_cls = s3_static.load_worker_classes(worker)
    solver_cls()  # the sibling load happens in `Solver.__init__`

    claimed = worker_module_names(worker)
    assert claimed, "driving the fixture's solver must leave an entry for this worker"
    assert not set(claimed) & set(skeleton_module_names(worker)), (
        "this fixture uses its OWN prefix, so the skeleton's exact names cannot be what "
        "covers it — the sweep matches the TAG"
    )
    for name in claimed:
        assert any(tag in name for tag in worker_module_tags(worker))
    assert purge_worker_modules(worker) == claimed
    assert not worker_module_names(worker)


def test_1_the_pipelines_own_module_entries_are_never_evicted(tmp_path):
    """Contract item 2: eviction clears the skeleton's FOREIGN entries only."""
    worker = _seeded(tmp_path)
    s3_static.load_worker_classes(worker)

    ours = sorted(n for n in sys.modules if n.startswith(PIPELINE_MODULE_PREFIXES))
    assert ours, "the loader registers its own s3_game_/s3_solver_ entries"
    purge_worker_modules(worker)
    assert sorted(n for n in sys.modules if n.startswith(PIPELINE_MODULE_PREFIXES)) == ours


def test_1_every_spelling_of_the_path_is_tagged(tmp_path, monkeypatch):
    """A loader handed a RELATIVE worker dir stamps that spelling into
    `__file__`, and a tmp root that is a symlink (macOS `/tmp`) makes the
    resolved and literal spellings differ. Both must be tagged."""
    worker = _bare_worker(tmp_path)
    monkeypatch.chdir(tmp_path)
    relative = Path(worker.name)

    literal = hashlib.sha256(str(relative / "game.py").encode("utf-8")).hexdigest()[:12]
    resolved = hashlib.sha256(str((worker / "game.py").resolve()).encode("utf-8")).hexdigest()[:12]
    tags = worker_module_tags(relative)
    assert literal in tags and resolved in tags
    # ... and the resolved spelling is shared by both ways of naming the worker.
    assert resolved in worker_module_tags(worker)


def test_1_the_helper_is_type_strict_and_existence_tolerant(tmp_path):
    """Eviction must not change which error a loader raises for a bad worker:
    it never requires the worker to EXIST, so a missing dir is simply nothing
    to evict. A non-path argument is still a programming error."""
    missing = tmp_path / "not-a-worker"
    assert len(worker_module_tags(missing)) >= 2
    assert purge_worker_modules(missing) == ()
    for bad in (None, 7, True, b"bytes"):
        with pytest.raises(TypeError):
            worker_module_tags(bad)


# --- 2. the desync is dead at every call site -------------------------------


def _load_via_s3_static(worker: Path):
    return s3_static.load_worker_classes(worker)[1]


def _load_via_s3_verify(worker: Path):
    return s3_verify.load_worker_classes(worker)[1]


def _load_via_s6(worker: Path):
    return s6_package._load_worker(worker)[3]


CALL_SITES = (
    ("s3_static.load_worker_classes", _load_via_s3_static),
    ("s3_verify.load_worker_classes", _load_via_s3_verify),
    ("s6_package._load_worker", _load_via_s6),
)


@pytest.mark.parametrize("label,load", CALL_SITES, ids=[name for name, _ in CALL_SITES])
def test_2_load_rewrite_reload_leaves_no_stale_solver(tmp_path, label, load):
    """THE SCENARIO, at every call site from work item 2. `Solver().layout_seed`
    is read straight off `mod.DEFAULT_LAYOUT_SEED`, so it says which BYTES the
    solver's own loader served."""
    worker = _seeded(tmp_path)

    solver_cls = load(worker)
    assert solver_cls().layout_seed == 13, f"{label}: premise — the fixture's authored seed"

    _rewrite(worker, SEED_LINE_V1, SEED_LINE_V2)

    solver_cls = load(worker)
    assert solver_cls().layout_seed == SEED_V2, (
        f"{label}: the solver planned against the PREVIOUS game.py — the pair desynced"
    )


@pytest.mark.parametrize(
    "module",
    [s3_static, s3_verify, s6_package],
    ids=["s3_static", "s3_verify", "s6_package"],
)
def test_2_each_call_site_is_wired_to_the_eviction(tmp_path, monkeypatch, module):
    """The WIRING, independent of the body: the loader in each module calls its
    own `purge_worker_modules` with the worker it is about to load."""
    worker = _seeded(tmp_path)
    seen: list[Path] = []

    def recorder(target):
        seen.append(Path(target))
        return worker_mod.purge_worker_modules(target)

    monkeypatch.setattr(module, "purge_worker_modules", recorder)
    if module is s6_package:
        module._load_worker(worker)
    else:
        module.load_worker_classes(worker)

    assert seen, f"{module.__name__} did not evict before exec-loading the pair"
    assert {p.resolve() for p in seen} == {worker.resolve()}


def test_2_the_in_process_capture_leg_agrees_with_disk_after_a_rewrite(tmp_path):
    """`frames.capture_worker` — the in-process capture leg, through
    `s3_verify`'s loader. The isolated leg (`capture_worker_isolated`) was never
    exposed; this pins the one that is."""
    worker = _seeded(tmp_path)
    first = frames.capture_worker(worker)
    assert first.win and first.levels_completed == 6

    _rewrite(worker, NAMESPACE_V1, NAMESPACE_V2)
    second = frames.capture_worker(worker)

    assert second.win, "the capture drove a fresh game with a stale solver plan"
    assert second.levels_completed == 6
    assert second.source_sha256 == hashlib.sha256(
        (worker / "game.py").read_bytes()
    ).hexdigest(), "the capture must be stamped with the bytes it actually ran"
    assert second.solver_actions != first.solver_actions, (
        "premise: the rewrite really did move the geometry"
    )


def test_2_the_sweep_of_in_process_exec_loaders_is_complete():
    """THE DRIFT GUARD for work item 2's sweep.

    Only four files in `gen/` exec worker code, and each is accounted for:
    `s3_static.py` and `s3_verify.py` are the two pair loaders (both evict);
    `officials.py` loads a read-only corpus game that ships NO solver, so no
    §7 sibling loader exists to go stale; `s2_implement.py`'s occurrence is
    the payload TEXT — the taught skeleton, not a loader. A new file here must
    be reviewed against contract E-4 before this pin is updated.

    Outside `gen/`: `worker-template/tests/_harness.py` exec-loads the pair
    too, but only inside the worker's own `make validate`, which S2 runs as a
    SUBPROCESS (`s2_implement.VALIDATE_CMD` through `subprocess.run`) — one
    fresh interpreter per attempt, with no rewrite in between — and
    `tools/play/server.py` loads a game (never a solver) under one fixed name
    it overwrites on every load.
    """
    found = sorted(
        path.name
        for path in sorted((REPO_ROOT / "gen").glob("*.py"))
        if "exec_module" in path.read_text(encoding="utf-8")
        or "exec(compile" in path.read_text(encoding="utf-8")
    )
    assert found == ["officials.py", "s2_implement.py", "s3_static.py", "s3_verify.py"]

    outside = sorted(
        str(path.relative_to(REPO_ROOT))
        for root in ("worker-template", "tools")
        for path in sorted((REPO_ROOT / root).rglob("*.py"))
        if "exec_module" in path.read_text(encoding="utf-8")
        or "exec(compile" in path.read_text(encoding="utf-8")
    )
    assert outside == ["tools/play/server.py", "worker-template/tests/_harness.py"]
    assert s2_implement.VALIDATE_CMD == ("make", "validate")

    # S4, S5, S3's gate and S6 have no loader of their own: they share
    # s3_static's, which is why evicting there covers their stage paths.
    for module in (s4_baselines, s5_battery, s3_gate, s6_package):
        assert module.load_worker_classes is s3_static.load_worker_classes
    assert "spec_from_file_location" not in (REPO_ROOT / "gen/s4_baselines.py").read_text(
        encoding="utf-8"
    )
    # `frames.capture_worker` deliberately borrows s3_verify's strict loader.
    assert "from .s3_verify import load_worker_classes" in (
        REPO_ROOT / "gen/frames.py"
    ).read_text(encoding="utf-8")


# --- 3. the two-cycle fake batch, and its negative control ------------------


def test_3_a_two_cycle_batch_validates_five_of_five_seeds_in_one_process(tmp_path):
    """S2 fix -> S6 revalidate, in ONE interpreter, exactly as a real slot does
    it. Both cycles must be clean 5/5 wins at 6 levels."""
    worker = _seeded(tmp_path)

    first = _validate(worker)
    assert _signature(first) == [(seed, True, 6) for seed in SEEDS]

    _rewrite(worker, NAMESPACE_V1, NAMESPACE_V2)
    second = _validate(worker)

    assert _signature(second) == [(seed, True, 6) for seed in SEEDS]
    assert [row["error"] for row in second] == [None] * len(SEEDS)


def test_3_with_the_eviction_reverted_the_same_bytes_reproduce_the_signature(
    tmp_path, monkeypatch
):
    """THE NEGATIVE CONTROL. Same worker, same process, same post-fix bytes:
    with the eviction reverted every seed loses with 0 levels (the lantern
    signature — seed-INDEPENDENT, a handful of actions, no level cleared), and
    restoring the eviction turns the identical bytes into 5/5.

    The second leg is the reason `s6_package._load_worker` evicts BEFORE its
    own stat-keyed cache lookup: with only the shared loader's eviction
    restored, S6's warm cache never reaches the shared loader and the batch
    still fails.
    """
    worker = _seeded(tmp_path)
    assert _signature(_validate(worker)) == [(seed, True, 6) for seed in SEEDS]

    _rewrite(worker, NAMESPACE_V1, NAMESPACE_V2)

    monkeypatch.setattr(s3_static, "purge_worker_modules", _reverted)
    monkeypatch.setattr(s6_package, "purge_worker_modules", _reverted)

    rows = _validate(worker)
    assert _signature(rows) == [(seed, False, 0) for seed in SEEDS], (
        "the negative control did not reproduce the defect: without eviction the stale "
        "solver plan must lose at EVERY seed with 0 levels completed"
    )
    assert all("0 level(s) completed" in row["error"] for row in rows)
    assert all(0 < row["actions_total"] <= 20 for row in rows), (
        "the signature includes dying a handful of actions in, not burning the budget"
    )

    # Only the shared loader's eviction back: S6's cache is warm, so the shared
    # loader is never reached and the batch still fails.
    monkeypatch.setattr(s3_static, "purge_worker_modules", worker_mod.purge_worker_modules)
    assert _signature(_validate(worker)) == [(seed, False, 0) for seed in SEEDS]

    # S6's own eviction back: the identical bytes now pass 5/5.
    monkeypatch.setattr(s6_package, "purge_worker_modules", worker_mod.purge_worker_modules)
    assert _signature(_validate(worker)) == [(seed, True, 6) for seed in SEEDS]


def test_3_the_stale_drive_is_seed_independent_and_fresh_bytes_pass_alone(tmp_path, monkeypatch):
    """The other half of the live attribution: the SAME bytes that fail at
    every seed with a stale module pass at every seed when nothing stale is in
    the table (what "they pass 5/5 in a fresh process" means, here)."""
    worker = _seeded(tmp_path)
    _validate(worker, seeds=(13,))                 # plants the v1 module
    _rewrite(worker, NAMESPACE_V1, NAMESPACE_V2)

    monkeypatch.setattr(s3_static, "purge_worker_modules", _reverted)
    monkeypatch.setattr(s6_package, "purge_worker_modules", _reverted)
    stale = _validate(worker)
    assert {row["win"] for row in stale} == {False}
    assert {row["levels_completed"] for row in stale} == {0}

    purge_worker_modules(worker)                   # the eviction, by hand
    s6_package._WORKER_CACHE.clear()
    fresh = _validate(worker)
    assert _signature(fresh) == [(seed, True, 6) for seed in SEEDS]


# --- 4. S2b's staged copy (M4's spirit) -------------------------------------


def test_4_the_staged_copy_keys_differently_and_is_evicted_independently(tmp_path):
    """S2b audits `<worker>.staged`, a copy at a DIFFERENT path, so its loads
    were never part of the defect. Pinned so a refactor that stages into the
    worker's own path — making the two share a cache key — fails here."""
    worker = _seeded(tmp_path, "worker")
    staged = _copy(SEEDED, tmp_path / "worker.staged")

    assert not set(worker_module_tags(worker)) & set(worker_module_tags(staged)), (
        "the staged copy's immunity IS its distinct path: same tags would mean one "
        "cache entry serving both"
    )

    for target in (worker, staged):
        _game_cls, solver_cls = s3_static.load_worker_classes(target)
        solver_cls()
    planted_worker, planted_staged = worker_module_names(worker), worker_module_names(staged)
    assert planted_worker and planted_staged and not set(planted_worker) & set(planted_staged)

    assert purge_worker_modules(worker) == planted_worker
    assert worker_module_names(staged) == planted_staged, (
        "evicting one worker must never evict another's module"
    )


# --- 5. the recorded limit: pyc validation is mtime-SECONDS + size ----------


def test_5_a_same_size_same_second_rewrite_can_serve_stale_bytecode(tmp_path, monkeypatch):
    """THE SECONDARY LAYER, reproduced deterministically — recorded, NOT fixed.

    `SourceLoader.get_code` validates a cached `.pyc` against `int(st.mtime)`
    and `st.st_size` only, so a rewrite that keeps the byte count and lands in
    the same wall-clock second is served from the stale bytecode even by a
    FRESH load under a brand-new module name. `os.utime` makes that condition
    exact instead of a race. Eviction decides which module object is reused,
    never which bytes the loader compiles, so this is outside the fix.
    """
    # LEAD UPDATE 2026-10-06: the premise WRITES a pyc, which a host shell
    # exporting PYTHONDONTWRITEBYTECODE=1 silently forbids (the interpreter
    # starts with the switch on). The test owns its premise.
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    source = tmp_path / "layer.py"
    source.write_text('MARK = "v1"\n', encoding="utf-8")

    def fresh(name: str):
        spec = importlib.util.spec_from_file_location(name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    assert fresh("e4_pyc_1").MARK == "v1"
    assert (tmp_path / "__pycache__").is_dir(), "premise: the first load cached bytecode"

    stat_before = source.stat()
    source.write_text('MARK = "v2"\n', encoding="utf-8")       # SAME size
    os.utime(source, ns=(stat_before.st_atime_ns, stat_before.st_mtime_ns + 1))
    assert source.stat().st_size == stat_before.st_size
    assert int(source.stat().st_mtime) == int(stat_before.st_mtime)

    assert fresh("e4_pyc_2").MARK == "v1", (
        "if this ever reads v2, CPython's pyc validation has changed and the caveat "
        "recorded in gen/worker.py can be revisited"
    )
    # And the belt that does work, for a caller that needs the guarantee.
    bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        shutil.rmtree(tmp_path / "__pycache__")
        assert fresh("e4_pyc_3").MARK == "v2"
    finally:
        sys.dont_write_bytecode = bytecode


def test_5_the_belt_closes_the_layer_at_the_purge_seam(tmp_path, monkeypatch):
    """THE PYC BELT, with its own negative control.

    A worker whose `game.py` is rewritten SAME-SIZE inside one second (the
    condition the test above proves is served stale): with the belt reverted a
    purge is not enough — the legacy loader re-execs and still compiles the
    OLD bytecode — and with the belt live the same purge reads the new source.
    """
    # LEAD UPDATE 2026-10-06: same premise ownership as the test above — the
    # host's PYTHONDONTWRITEBYTECODE must not decide whether the pyc exists.
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    worker = _bare_worker(tmp_path, "belt")
    solver_module = _exec_solver(worker, "e4_belt_solver")
    assert solver_module._game_module().MARK == "v1"
    cache = worker / worker_mod.BYTECODE_CACHE_DIR
    assert cache.is_dir(), "premise: the first load cached bytecode inside the worker"

    game = worker / "game.py"
    stat_before = game.stat()
    game.write_text(BARE_GAME.replace('"v1"', '"v2"'), encoding="utf-8")  # SAME size
    os.utime(game, ns=(stat_before.st_atime_ns, stat_before.st_mtime_ns + 1))
    assert game.stat().st_size == stat_before.st_size
    assert int(game.stat().st_mtime) == int(stat_before.st_mtime)

    # Leg A — the belt reverted: the module eviction alone cannot win.
    monkeypatch.setattr(worker_mod, "purge_worker_bytecode", _reverted)
    worker_mod.purge_worker_modules(worker)
    assert cache.is_dir(), "premise: the reverted belt left the stale pyc in place"
    assert solver_module._game_module().MARK == "v1", (
        "premise of the belt: with the pyc kept, a fresh exec of the same source still "
        "runs the stale bytecode — if this reads v2 the belt has nothing to close"
    )

    # Leg B — the belt live: the identical purge now reaches the source.
    monkeypatch.undo()
    assert worker_mod.purge_worker_modules(worker)  # the module entry goes again
    assert not cache.exists(), "the belt must remove the worker's own __pycache__"
    assert solver_module._game_module().MARK == "v2"


def test_5_the_belt_is_absence_tolerant_and_never_leaves_the_worker_tree(tmp_path):
    """(a) and (b) of the belt's requirements, pinned.

    No cache dir is nothing to do; a `__pycache__` SYMLINK is refused rather
    than followed, so no tree outside the worker can be reached from here; and
    the scaffold's own `tests/__pycache__` is not the belt's business.
    """
    worker = _bare_worker(tmp_path, "tolerant")
    assert worker_mod.purge_worker_bytecode(worker) == ()
    assert worker_mod.purge_worker_bytecode(tmp_path / "missing-worker") == ()

    # A symlinked cache dir pointing OUTSIDE the worker: refused, target intact.
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("precious", encoding="utf-8")
    (worker / worker_mod.BYTECODE_CACHE_DIR).symlink_to(outside, target_is_directory=True)
    assert worker_mod.purge_worker_bytecode(worker) == ()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "precious"
    assert (worker / worker_mod.BYTECODE_CACHE_DIR).is_symlink(), "the link itself stays"

    # The scaffold's test-dir cache is left alone.
    (worker / "tests").mkdir()
    scaffold_cache = worker / "tests" / worker_mod.BYTECODE_CACHE_DIR
    scaffold_cache.mkdir()
    (scaffold_cache / "x.pyc").write_bytes(b"\x00")
    worker_mod.purge_worker_modules(worker)
    assert (scaffold_cache / "x.pyc").is_file()


def test_5_the_caveat_is_recorded_where_the_eviction_lives():
    """The contract asks for the record, so the record is pinned: a reader of
    `gen/worker.py` must still be told that eviction is not the whole story."""
    doc = worker_mod.__doc__ or ""
    for marker in (
        "purge_worker_modules",
        "pyc",
        "SECONDS",
        "capture_worker_isolated",
        "THE BELT",
        "__pycache__",
    ):
        assert marker in doc, f"gen/worker.py's header no longer records {marker!r}"


# --- 6. the NEW taught skeleton (work item 3) -------------------------------


def _taught_solver_block() -> str:
    """The solver code the §7 payload now teaches, exactly as a reader gets it."""
    fences = s2_implement.LAYOUT_SEED_CONTRACT.split("```python")
    assert len(fences) == 3, (
        "the §7 section is expected to carry exactly two python blocks (game, solver); "
        f"found {len(fences) - 1}"
    )
    return fences[2].split("```")[0]


def test_6_the_taught_skeleton_keys_its_cache_on_the_files_bytes():
    """THE LICENSED PAYLOAD EDIT, pinned: a regression to the path-keyed
    lookup — the defect — fails here instead of shipping into every new
    solver."""
    block = _taught_solver_block()
    compile(block, "<taught solver skeleton>", "exec")  # it must be real Python

    for marker in ("_GAME_PATH.stat()", "st.st_mtime_ns", "st.st_size", "_GAME_CACHE"):
        assert marker in block, f"the taught loader no longer carries {marker!r}"
    assert 'f"game_{_GAME_TAG}_{key[0]}_{key[1]}"' in block, (
        "the taught name keeps the PATH TAG as its prefix and appends the stat, so "
        "gen/worker.py's sweep still recognises a new solver's entries as this worker's"
    )
    assert "sys.modules.get(" not in block, (
        "the taught loader must not READ sys.modules for its cache: that lookup is keyed "
        "on the path alone and is the E-4 defect"
    )
    assert "sys.modules[name] = module" in block, (
        "registration BEFORE exec stays — dataclass field resolution inside a game reads "
        "sys.modules[__name__]"
    )
    # And the prose rule that explains it to the implementing agent.
    assert "key any cache of that load on the FILE'S BYTES" in s2_implement.LAYOUT_SEED_CONTRACT


def test_6_a_solver_built_from_the_taught_skeleton_needs_no_eviction(tmp_path):
    """Exec'd AS WRITTEN, the new loader survives an in-process rewrite on its
    own: new bytes, new stat key, new module — no help from the pipeline."""
    worker = tmp_path / "taught"
    worker.mkdir()
    (worker / "game.py").write_text(BARE_GAME, encoding="utf-8")
    (worker / "solver.py").write_text(_taught_solver_block(), encoding="utf-8")

    solver_module = _exec_solver(worker, "e4_taught_solver")
    assert solver_module._game_module().MARK == "v1"

    (worker / "game.py").write_text(
        BARE_GAME.replace('"v1"', '"v2-rewritten"'), encoding="utf-8"
    )

    assert solver_module._game_module().MARK == "v2-rewritten", (
        "the taught loader must read the new bytes with no eviction at all"
    )
    assert len(worker_module_names(worker)) == 2, (
        "both loads are registered under DISTINCT stat-derived names, which is why the "
        "second could not be served the first"
    )
    # The old pattern's one guarantee is kept: a repeat call with unchanged
    # bytes is still a cache hit, not a re-exec.
    assert solver_module._game_module() is solver_module._game_module()
