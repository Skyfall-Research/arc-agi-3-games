"""E-0 (in-loop seed validation) — the IMPLEMENTER's own battery.

Run: .venv/bin/python -m pytest gen/tests/test_e0_seeds.py -q

THE DEBT E-0 PAYS: S6 validates a finished game at a LIST of layout seeds and
refuses the game if any one of them cannot be won, but nothing inside the build
loop could run that list — so a solver that only solved its own authored layout
reached `implemented` looking finished and was refused at packaging (twice:
b004's twin-signal, and the g20261001-5 lantern slot at the cap). E-0 writes
the exact seed list beside the worker at birth and the scaffold sweeps it on
every `make validate`.

WHAT THIS FILE PINS, and why each pin exists

 1. DERIVATION PARITY — the sidecar's list is `s6_package.validation_seeds`'
    own output, never a second implementation, and for the lantern slot it
    equals the five seeds S6 ACTUALLY recorded in its shipped seed-reject
    report (`worker.s6/s6-report.json`). The hand-rolled sha256 derivation is
    re-done here from the contract's description, so a drift in the pipeline's
    derivation fails against arithmetic this file owns.
 2. SIBLING, NEVER INSIDE — the sidecar is `<worker>.seeds.json` beside the
    tree; writing it leaves the edit scope clean (a file inside the worker
    would be an edit-scope violation on the agent's very first `make validate`).
 3. ONE BOUND — the scaffold's `S6_MAX_ACTIONS` mirror, the sidecar's recorded
    `max_actions` and `s6_package.MAX_ACTIONS` are the SAME number. Two
    diverging bounds is how this failure class was born: the lantern worker was
    green under the harness's 1200 and a seed-reject under S6's 600.
 4. THE SWEEP CATCHES WHAT S6 CATCHES — driven through the real `make validate`
    on real fixtures, and cross-checked seed-by-seed against S6's own
    `validate_seed` in BOTH directions: the reference pair is green under both,
    the seed-reject twin is red under both, on the same seeds.
 5. S6-PARITY SEMANTICS — construction kwargs are OBSERVED (explicit
    `layout_seed=` on both classes for every seed, including the authored one;
    no-argument construction is still exactly what the old battery does), and
    the sweep passes S6's 600 bound, not the harness default.
 6. PREMISE-SKIPS — no sidecar, or no `build_layout`, is a SKIP; the toy
    fixtures stay green (test_b1_acceptance requires that). A sidecar that
    exists and is unusable is LOUD.
 7. RESYNC — absent an explicit resync an existing worker is byte-for-byte as
    it was, template drift raising included; after one it is on today's
    scaffold with both manifests rebuilt, the sidecar written, the editable
    pair byte-untouched, and its repair path working again.
 8. THE SEAM — the orchestrator's S2 runner writes the sidecar exactly where
    it instantiates a worker, pinned on the runner's own AST.

HERMETIC: every worker is built under `tmp_path`; the real `out/` and `games/`
and the shipped `worker-template/` are snapshot-guarded by an autouse fixture;
no driver, no network, no spend. The lantern slot and the fixtures are READ
and copied, never written.

NOT THIS FILE: `gen/tests/test_v2_seeds.py` is the blind lane's, written from
the contract alone. This file is the implementer's.
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from gen import worker as worker_mod
from gen.config import REPO_ROOT
from gen.s2_implement import worker_is_bare
from gen.s6_package import MAX_ACTIONS as S6_MAX_ACTIONS
from gen.s6_package import validate_seed, validation_seeds
from gen.worker import (
    IGNORED_DIRS,
    SEEDS_SUFFIX,
    instantiate_worker,
    repair_worker,
    resync_worker,
    seeds_sidecar_path,
    verify_worker,
    write_seeds_sidecar,
)

TESTS = Path(__file__).resolve().parent
TOY = TESTS / "toy_worker"
FIXTURES = TESTS / "fixtures"
SEEDED = FIXTURES / "s6_seeded"            # wins at EVERY seed (the reference)
SEEDED_BROKEN = FIXTURES / "s6_seeded_broken"  # wins ONLY at its authored seed
TEMPLATE_SWEEP = REPO_ROOT / "worker-template/tests/test_seed_sweep.py"
HARNESS = REPO_ROOT / "worker-template/tests/_harness.py"
ORCHESTRATOR_PY = REPO_ROOT / "gen/orchestrator.py"

# The real slot the contract names: parked at the cap on 10-01 after S6 refused
# it on five seeds. Read-only here.
LANTERN = REPO_ROOT / "out/corpus/g20261001-5/lantern-path-parity-trace"
LANTERN_CONFIG = REPO_ROOT / "out/batches/g20261001-5/config.yaml"

# `fixtures/s6_seeded/game.py`'s module constant — the fixture's authored
# default, and therefore the first seed its sidecar must carry.
SEEDED_DEFAULT_SEED = 13

_CFG = {
    "batch": {"seed": 11},
    "package": {"seeds_validated": 5, "split": {"train": 0.7, "eval": 0.3}},
}


# --- rig ---------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _repo_untouched():
    """No test here writes under the real `out/`, `games/` or the template."""
    roots = (REPO_ROOT / "out", REPO_ROOT / "games")

    def listing():
        return sorted(
            str(path) for root in roots if root.exists() for path in root.rglob("*")
        )

    def template():
        return {
            path.relative_to(REPO_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((REPO_ROOT / "worker-template").rglob("*"))
            if path.is_file() and not any(part in IGNORED_DIRS for part in path.parts)
        }

    before, before_template = listing(), template()
    yield
    assert listing() == before, "an E-0 test wrote into the repo's out/ or games/"
    assert template() == before_template, "an E-0 test modified the shipped worker-template"


def _install(worker: Path, source: Path) -> Path:
    for name in ("game.py", "solver.py"):
        shutil.copy2(source / name, worker / name)
    return worker


def _worker(tmp_path: Path, name: str, source: Path | None = None) -> Path:
    """A fresh real worker under tmp, optionally carrying a fixture pair."""
    dest = (tmp_path / name).resolve()
    instantiate_worker(dest)
    if source is not None:
        _install(dest, source)
    return dest


def _validate(worker: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["make", "validate"], cwd=worker, capture_output=True, text=True, timeout=300,
        check=False,
    )


def _sweep_ids(output: str) -> set[str]:
    """The seed ids pytest printed for the sweep's parametrized cases."""
    found = set()
    for line in output.splitlines():
        marker = "test_solver_wins_every_validation_seed["
        if marker in line:
            tail = line.split(marker, 1)[1]
            found.add(tail.split("]", 1)[0])
    return found


def _hand_derived(batch_seed: int, game_id: str, authored: int | None, count: int) -> list[int]:
    """The contract's derivation, re-rolled here: authored first, then
    `sha256("<batch.seed>:<game_id>:s6:<k>")[:8]`, repeats skipped."""
    seeds: list[int] = [] if authored is None else [int(authored)]
    counter = 0
    while len(seeds) < count:
        counter += 1
        digest = hashlib.sha256(f"{batch_seed}:{game_id}:s6:{counter}".encode()).hexdigest()
        candidate = int(digest[:8], 16)
        if candidate not in seeds:
            seeds.append(candidate)
    return seeds


def _stale_template(tmp_path: Path, tag: str = "") -> Path:
    """A PREVIOUS scaffold generation: no seed sweep, an older `_harness.py`,
    and two files today's scaffold does not have."""
    drifted = tmp_path / f"template-previous-generation{tag}"
    shutil.copytree(
        worker_mod.TEMPLATE_DIR, drifted, ignore=shutil.ignore_patterns(*IGNORED_DIRS)
    )
    (drifted / "tests/test_seed_sweep.py").unlink()
    harness = drifted / "tests/_harness.py"
    harness.write_text(
        harness.read_text(encoding="utf-8").replace("S6_MAX_ACTIONS = 600", "")
        + "\n# previous generation\n",
        encoding="utf-8",
    )
    (drifted / "tests/old_helper.py").write_text("# retired helper\n", encoding="utf-8")
    (drifted / "legacy").mkdir()
    (drifted / "legacy/extra.py").write_text("# retired directory\n", encoding="utf-8")
    return drifted


def _born_stale(tmp_path: Path, name: str, source: Path | None = None) -> tuple[Path, Path]:
    """A worker instantiated from the PREVIOUS generation, as the live ones are."""
    drifted = _stale_template(tmp_path, tag=f"-{name}")
    dest = (tmp_path / name).resolve()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(worker_mod, "TEMPLATE_DIR", drifted)
        instantiate_worker(dest)
    if source is not None:
        _install(dest, source)
    return dest, drifted


# --- 1. derivation parity ----------------------------------------------------


def test_sidecar_seeds_are_validation_seeds_output(tmp_path):
    worker = _worker(tmp_path, "w-derive", SEEDED)
    payload = write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    assert payload["seeds"] == validation_seeds(_CFG, worker.name, SEEDED_DEFAULT_SEED), (
        "the sidecar must BE validation_seeds' output — one derivation, shared with the "
        "stage that enforces it"
    )
    assert payload["count"] == _CFG["package"]["seeds_validated"] == len(payload["seeds"])
    assert payload["seeds"][0] == SEEDED_DEFAULT_SEED, "the authored default comes first"
    assert len(set(payload["seeds"])) == len(payload["seeds"]), "the list is distinct"


def test_sidecar_seeds_match_a_hand_rolled_derivation(tmp_path):
    worker = _worker(tmp_path, "w-byhand", SEEDED)
    payload = write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    assert payload["seeds"] == _hand_derived(11, worker.name, SEEDED_DEFAULT_SEED, 5)


def test_the_sidecar_reproduces_the_lantern_slots_real_five_seeds(tmp_path):
    """The one pin against a REAL S6 run: the seeds S6 recorded in its shipped
    seed-reject report for the lantern slot are the seeds this sidecar writes
    for a copy of that slot."""
    assert LANTERN.is_dir(), f"fixture wall: {LANTERN} is gone (the E-0 contract names it)"
    assert LANTERN_CONFIG.is_file(), f"fixture wall: {LANTERN_CONFIG} is gone"
    report = json.loads((LANTERN / "worker.s6/s6-report.json").read_text(encoding="utf-8"))
    recorded = [row["seed"] for row in report["seeds"]["validated"]]
    # LEAD UPDATE 2026-10-06: the live slot's report was the 5-seed REJECT when
    # E-0 froze; revival #1 (2026-10-05) legitimately re-ran S6 on the same
    # derivation and PACKAGED — same five seeds, same authored default. The
    # parity claim this test exists for (sidecar == the seeds a REAL S6 run
    # recorded) is verdict-independent, so both verdicts hold the wall.
    assert report["verdict"] in ("seed-reject", "packaged") and len(recorded) == 5, (
        f"fixture wall: {LANTERN}'s s6 report no longer records the 5-seed run this pins against"
    )

    slot = tmp_path / LANTERN.name
    (slot / "worker").mkdir(parents=True)
    shutil.copy2(LANTERN / "spec.yaml", slot / "spec.yaml")
    _install(slot / "worker", LANTERN / "worker")
    cfg = yaml.safe_load(LANTERN_CONFIG.read_text(encoding="utf-8"))

    payload = write_seeds_sidecar(slot / "worker", cfg)
    assert payload["seeds"] == recorded, (
        f"the sidecar derives {payload['seeds']} but S6 validated {recorded} — the in-loop "
        "sweep would drive seeds the packager never asks about"
    )
    assert payload["game_id"] == report["game_id"] == LANTERN.name
    assert payload["authored_seed"] == report["seeds"]["authored_seed"], (
        "the authored default must be the one S6 read off the game"
    )
    assert payload["batch_seed"] == cfg["batch"]["seed"]


def test_game_id_defaults_to_the_slug_s6_would_use(tmp_path):
    """S6 names the game by its S4 metadata `game_id` or, failing that, the
    slug — and `<slot>/worker/` is named by its PARENT (architecture §2)."""
    slot = tmp_path / "some-game-slug"
    worker = slot / "worker"
    worker.mkdir(parents=True)
    _install(worker, SEEDED)
    payload = write_seeds_sidecar(worker, _CFG, authored_seed=3)
    assert payload["game_id"] == "some-game-slug"
    assert payload["seeds"] == _hand_derived(11, "some-game-slug", 3, 5)

    override = write_seeds_sidecar(worker, _CFG, game_id="other", authored_seed=3)
    assert override["game_id"] == "other"
    assert override["seeds"] == _hand_derived(11, "other", 3, 5)


def test_authored_seed_comes_from_the_spec_beside_the_worker(tmp_path):
    slot = tmp_path / "slot"
    worker = slot / "worker"
    worker.mkdir(parents=True)
    _install(worker, SEEDED)
    (slot / "spec.yaml").write_text(
        yaml.safe_dump({"game": {"slug": "slot", "layout": {"seed": 4242, "grid": [16, 16]}}}),
        encoding="utf-8",
    )
    payload = write_seeds_sidecar(worker, _CFG)
    assert payload["authored_seed"] == 4242
    assert payload["seeds"][0] == 4242


@pytest.mark.parametrize(
    ("document", "match"),
    [
        ({"game": {"slug": "slot"}}, "game.layout.seed must be an int"),
        ({"game": {"layout": {"grid": [8, 8]}}}, "game.layout.seed must be an int"),
        ({"game": {"layout": {"seed": "173"}}}, "game.layout.seed must be an int"),
        ({"game": {"layout": {"seed": True}}}, "game.layout.seed must be an int"),
    ],
    ids=["no-layout", "no-seed", "string-seed", "bool-seed"],
)
def test_an_unusable_spec_seed_is_loud(tmp_path, document, match):
    slot = tmp_path / "slot"
    worker = slot / "worker"
    worker.mkdir(parents=True)
    (slot / "spec.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        write_seeds_sidecar(worker, _CFG)
    assert not seeds_sidecar_path(worker).exists(), "a refused derivation writes nothing"


def test_a_missing_spec_is_loud_rather_than_a_guessed_seed_list(tmp_path):
    worker = tmp_path / "slot" / "worker"
    worker.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="spec.yaml"):
        write_seeds_sidecar(worker, _CFG)
    assert not seeds_sidecar_path(worker).exists()


def test_a_config_without_a_batch_seed_is_loud(tmp_path):
    worker = _worker(tmp_path, "w-nobatch", SEEDED)
    with pytest.raises(ValueError, match="batch.seed"):
        write_seeds_sidecar(worker, {"package": _CFG["package"]}, authored_seed=1)


# --- 2. sibling, never inside ------------------------------------------------


def test_the_sidecar_is_a_sibling_and_leaves_the_edit_scope_clean(tmp_path):
    worker = _worker(tmp_path, "w-scope", SEEDED)
    path = seeds_sidecar_path(worker)
    assert path == worker.with_name(worker.name + SEEDS_SUFFIX) == worker.parent / (
        worker.name + ".seeds.json"
    )
    write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    assert path.is_file() and path.parent == worker.parent
    assert worker not in path.parents, "the sidecar must never live inside the worker tree"
    assert verify_worker(worker) == [], "the sidecar must not be an edit-scope violation"
    scope = subprocess.run(
        ["make", "scope"], cwd=worker, capture_output=True, text=True, timeout=60, check=False,
    )
    assert scope.returncode == 0, scope.stdout + scope.stderr


def test_the_sidecar_is_written_atomically_and_deterministically(tmp_path):
    worker = _worker(tmp_path, "w-atomic", SEEDED)
    first = seeds_sidecar_path(worker)
    write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    bytes_first = first.read_bytes()
    write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    assert first.read_bytes() == bytes_first, "the same plan must write the same bytes"
    strays = [p.name for p in worker.parent.iterdir() if ".tmp-" in p.name]
    assert not strays, f"the atomic write left a staging file behind: {strays}"


# --- 3. one bound ------------------------------------------------------------


def test_the_scaffold_mirror_is_s6s_own_bound():
    """Work item 4. The scaffold cannot import the pipeline, so it mirrors the
    constant — and this pin is the mirror's drift test."""
    text = HARNESS.read_text(encoding="utf-8")
    module = ast.parse(text)
    mirrored = {
        target.id: node.value.value
        for node in module.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant)
    }
    assert mirrored.get("S6_MAX_ACTIONS") == S6_MAX_ACTIONS, (
        f"worker-template/tests/_harness.py mirrors S6_MAX_ACTIONS as "
        f"{mirrored.get('S6_MAX_ACTIONS')!r} but gen/s6_package.MAX_ACTIONS is "
        f"{S6_MAX_ACTIONS} — the sweep would not reproduce S6's verdict"
    )
    assert mirrored.get("MAX_ACTIONS") == 1200, (
        "the scaffold battery's own bound is unchanged (today's bytes)"
    )


def test_the_sidecar_records_the_same_bound(tmp_path):
    worker = _worker(tmp_path, "w-bound", SEEDED)
    payload = write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    assert payload["max_actions"] == S6_MAX_ACTIONS
    assert payload["stage_tag"] == "s6", "the derivation tag keeps S4's seeds disjoint"


# --- 4. the sweep catches what S6 catches ------------------------------------


def test_the_reference_pair_sweeps_green(tmp_path):
    worker = _worker(tmp_path, "w-good", SEEDED)
    payload = write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    proc = _validate(worker)
    assert proc.returncode == 0, f"expected green:\n{proc.stdout}\n{proc.stderr}"
    assert "validate: GREEN" in proc.stdout
    assert _sweep_ids(proc.stdout + proc.stderr) <= {str(s) for s in payload["seeds"]}


def test_the_seed_reject_twin_sweeps_red_on_the_seeds_s6_refuses(tmp_path):
    """The whole contract, in one test: the twin that wins ONLY at its authored
    seed is RED inside `make validate`, and the failing seed ids are exactly
    the non-authored ones."""
    worker = _worker(tmp_path, "w-broken", SEEDED_BROKEN)
    payload = write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    proc = _validate(worker)
    output = proc.stdout + proc.stderr
    assert proc.returncode != 0, f"the seed-reject twin must go RED:\n{output}"
    failed = {
        line.split("[", 1)[1].split("]", 1)[0]
        for line in output.splitlines()
        if line.startswith("FAILED") and "test_solver_wins_every_validation_seed[" in line
    }
    expected = {str(seed) for seed in payload["seeds"][1:]}
    assert failed == expected, (
        f"expected the four derived seeds {sorted(expected)} to fail and the authored seed "
        f"{payload['seeds'][0]} to pass; got {sorted(failed)}\n{output}"
    )
    assert "derive its line from the seed it is handed" in output, (
        "a red seed must tell the building agent what to fix"
    )


@pytest.mark.parametrize("fixture", [SEEDED, SEEDED_BROKEN], ids=["reference", "seed-reject-twin"])
def test_the_sweep_and_s6_agree_seed_by_seed(tmp_path, fixture):
    """Two-direction parity: S6's own `validate_seed` on the same pair, at the
    same seeds, with the same pass rule."""
    worker = _worker(tmp_path, "w-parity", fixture)
    payload = write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    levels = 6  # both fixtures author six levels (the §7 floor)
    s6_verdicts = {}
    for seed in payload["seeds"]:
        row = validate_seed(worker, seed, max_actions=S6_MAX_ACTIONS)
        s6_verdicts[str(seed)] = bool(row["win"]) and int(row["levels_completed"]) == levels

    output = _validate(worker).stdout
    swept = {
        seed_id: f"FAILED tests/test_seed_sweep.py::test_solver_wins_every_validation_seed"
        f"[{seed_id}]" not in output
        for seed_id in (str(seed) for seed in payload["seeds"])
    }
    assert swept == s6_verdicts, (
        f"the sweep and S6 disagree: sweep={swept} s6={s6_verdicts} — a sweep that does not "
        "reproduce S6's verdict is worthless\n" + output
    )


# --- 5. S6-parity semantics --------------------------------------------------


_PROBE = r'''
import json
from types import SimpleNamespace

from arcengine import GameState

import tests._harness as harness
import tests.test_seed_sweep as sweep

game_cls, solver_cls = harness.load_game_class(), harness.load_solver_class()
seen = []


class RecordingGame(game_cls):
    def __init__(self, **kwargs):
        seen.append(["game", sorted(kwargs.items())])
        super().__init__(**kwargs)


class RecordingSolver(solver_cls):
    def __init__(self, **kwargs):
        seen.append(["solver", sorted(kwargs.items())])
        super().__init__(**kwargs)


harness.run_solver(RecordingGame, RecordingSolver)
no_arg = list(seen)
seen.clear()
harness.run_solver(RecordingGame, RecordingSolver, layout_seed=SEED)
explicit = list(seen)

calls = []


def _fake(game, solver, **kwargs):
    calls.append(sorted(kwargs.items()))
    return SimpleNamespace(final_state=GameState.WIN, levels_completed=1, win_levels=1,
                           actions=[])


sweep.run_solver = _fake
sweep.test_solver_wins_every_validation_seed(SEED)

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump({"no_arg": no_arg, "explicit": explicit, "sweep_calls": calls,
               "harness_default": harness.MAX_ACTIONS, "mirror": harness.S6_MAX_ACTIONS,
               "sweep_bound": sweep._BOUND, "sweep_seeds": list(sweep._SEEDS)}, fh)
'''


def test_the_sweep_constructs_explicitly_and_binds_at_s6s_600(tmp_path):
    """Observed, not assumed: the kwargs both classes are constructed with, and
    the bound the sweep hands the drive."""
    worker = _worker(tmp_path, "w-probe", SEEDED)
    payload = write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    out = tmp_path / "probe.json"
    seed = payload["seeds"][0]
    script = f"SEED = {seed}\nOUT = {str(out)!r}\n" + _PROBE
    proc = subprocess.run(
        [sys.executable, "-c", script], cwd=worker, capture_output=True, text=True,
        timeout=300, check=False,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    observed = json.loads(out.read_text(encoding="utf-8"))

    assert observed["no_arg"] == [["game", []], ["solver", []]], (
        "run_solver() with no layout_seed must construct BOTH classes with no argument — "
        "today's bytes for the existing battery"
    )
    assert observed["explicit"] == [
        ["game", [["layout_seed", seed]]], ["solver", [["layout_seed", seed]]]
    ], "a seed must be passed EXPLICITLY as layout_seed= to both classes, as S6 does"
    assert observed["sweep_calls"] == [[["layout_seed", seed], ["max_actions", 600]]], (
        "the sweep must drive at S6's 600-action bound with an explicit seed; it called "
        f"run_solver with {observed['sweep_calls']}"
    )
    assert observed["harness_default"] == 1200 and observed["mirror"] == 600, (
        "the scaffold battery keeps its own 1200 bound; the sweep uses S6's 600"
    )
    assert observed["sweep_bound"] == 600
    assert observed["sweep_seeds"] == payload["seeds"], (
        "the sweep's cases are the sidecar's seeds, in order"
    )


def test_the_authored_seed_is_driven_explicitly_too(tmp_path):
    """THE LANTERN-173 LESSON, reproduced on a fixture.

    A game whose explicit-seed path disagrees with its no-argument path is
    GREEN under the old battery (both classes built no-arg, so both agree on
    the default) and RED in the sweep AT ITS OWN AUTHORED SEED (the game builds
    seed+1 while the solver plans the seed it was handed). That is why the
    sweep constructs explicitly even for the authored default: lantern was
    green here and a seed-reject at S6 on seed 173, its own authored seed.
    """
    worker = _worker(tmp_path, "w-authored", SEEDED)
    game = worker / "game.py"
    source = game.read_text(encoding="utf-8")
    needle = "        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)"
    assert needle in source, "fixture wall: s6_seeded/game.py's §7 constructor line moved"
    game.write_text(source.replace(needle, needle + " + 1"), encoding="utf-8")
    write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)

    output = _validate(worker).stdout
    failed = {
        line.split("::", 1)[1].strip() for line in output.splitlines() if line.startswith("FAILED")
    }
    assert "test_scaffold.py::test_solver_reaches_win_with_all_levels_credited" not in {
        f"test_scaffold.py::{name}" for name in failed
    }, f"the no-argument battery must still be GREEN — that is the whole lesson:\n{output}"
    assert f"test_solver_wins_every_validation_seed[{SEEDED_DEFAULT_SEED}]" in failed, (
        f"the sweep must catch it at the AUTHORED seed {SEEDED_DEFAULT_SEED}:\n{output}"
    )


def test_a_game_whose_authored_default_is_not_the_spec_seed_is_loud(tmp_path):
    """S6 validates the seed the GAME records; the sidecar carries the seed the
    SPEC authored. Disagreement means the sweep drives a seed S6 will not."""
    worker = _worker(tmp_path, "w-defaultdrift", SEEDED)
    write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED + 1)
    output = _validate(worker).stdout
    assert "test_authored_default_is_the_sidecar_seed" in output and "FAILED" in output, (
        "a game whose baked default is not the spec's layout.seed must be red:\n" + output
    )


# --- 6. premise-skips --------------------------------------------------------


def test_the_toy_worker_stays_green_without_a_sidecar(tmp_path):
    """test_b1_acceptance's requirement, unchanged: a worker with no
    build_layout and no sidecar validates green."""
    worker = _worker(tmp_path, "w-toy", TOY)
    proc = _validate(worker)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "3 skipped" in proc.stdout, (
        "the three sweep cases must SKIP on a worker with no sidecar:\n" + proc.stdout
    )


def test_the_toy_worker_stays_green_with_a_sidecar(tmp_path):
    """No `build_layout` is a missing PREMISE even when the seeds are known:
    the five seed cases and the authored-default check skip, the
    well-formedness check passes, and `make validate` stays green."""
    worker = _worker(tmp_path, "w-toy-seeded", TOY)
    write_seeds_sidecar(worker, _CFG, authored_seed=7)
    proc = _validate(worker)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "6 skipped" in proc.stdout, (
        "five seed cases + the authored-default check must SKIP on a worker with no "
        "build_layout:\n" + proc.stdout
    )


def test_a_fresh_placeholder_scaffold_still_fails_for_its_own_reason(tmp_path):
    """test_b1_acceptance:33-36's pin: the scaffold is red before implementation
    and the message is still about the missing game class."""
    worker = _worker(tmp_path, "w-fresh")
    proc = _validate(worker)
    assert proc.returncode != 0
    assert "ARCBaseGame subclass" in proc.stdout + proc.stderr


@pytest.mark.parametrize(
    ("payload", "note"),
    [
        ({"seeds": []}, "non-empty list"),
        ({"seeds": {}}, "non-empty list"),
        ({"schema": "e0.1"}, "non-empty list"),
        ({"seeds": [13, "x"]}, "non-int"),
        ({"seeds": [13, 13]}, "repeats"),
        ({"seeds": [13], "max_actions": 0}, "positive int"),
    ],
    ids=["empty", "not-a-list", "absent", "non-int", "repeated", "bad-bound"],
)
def test_an_unusable_sidecar_is_loud_not_a_silent_pass(tmp_path, payload, note):
    worker = _worker(tmp_path, "w-badcar", SEEDED)
    seeds_sidecar_path(worker).write_text(json.dumps(payload), encoding="utf-8")
    proc = _validate(worker)
    output = proc.stdout + proc.stderr
    assert proc.returncode != 0, f"an unusable sidecar must be RED:\n{output}"
    assert "test_seed_sidecar_is_well_formed" in output and note in output, output


def test_unparseable_sidecar_bytes_are_loud(tmp_path):
    worker = _worker(tmp_path, "w-garbage", SEEDED)
    seeds_sidecar_path(worker).write_text("{not json", encoding="utf-8")
    proc = _validate(worker)
    assert proc.returncode != 0
    assert "unreadable seed sidecar" in proc.stdout + proc.stderr


def test_a_stale_generation_sidecar_names_the_resync(tmp_path):
    """A sidecar from a pipeline whose bound differs from this scaffold's mirror
    cannot reproduce S6's verdict, and says so."""
    worker = _worker(tmp_path, "w-oldbound", SEEDED)
    payload = write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    seeds_sidecar_path(worker).write_text(
        json.dumps({**payload, "max_actions": 1200}), encoding="utf-8"
    )
    output = _validate(worker).stdout
    assert "different generations of the pipeline" in output and "resync" in output, output


# --- 7. resync ---------------------------------------------------------------


def test_absent_a_resync_an_existing_worker_is_byte_for_byte_as_today(tmp_path):
    """The pin that makes this contract safe to merge: nothing migrates on its
    own. A worker born on the previous generation keeps it, its scope check
    passes, it has no sweep and no sidecar, and its repair path raises template
    drift exactly as test_b3_green_loop pins it."""
    worker, _drifted = _born_stale(tmp_path, "w-stale", SEEDED)
    assert not (worker / "tests/test_seed_sweep.py").exists()
    assert not seeds_sidecar_path(worker).exists()
    assert (worker / "tests/old_helper.py").is_file()
    assert verify_worker(worker) == [], "the stale worker is internally consistent"
    proc = _validate(worker)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "test_seed_sweep" not in proc.stdout

    (worker / "tests/_harness.py").unlink()
    with pytest.raises(RuntimeError, match="template drift"):
        repair_worker(worker)


def test_resync_brings_a_stale_worker_to_todays_generation(tmp_path):
    worker, _drifted = _born_stale(tmp_path, "w-revive", SEEDED)
    before = {
        name: hashlib.sha256((worker / name).read_bytes()).hexdigest()
        for name in ("game.py", "solver.py")
    }

    result = resync_worker(worker, cfg=_CFG, authored_seed=SEEDED_DEFAULT_SEED)

    assert (worker / "tests/test_seed_sweep.py").read_bytes() == TEMPLATE_SWEEP.read_bytes()
    assert (worker / "tests/_harness.py").read_bytes() == HARNESS.read_bytes()
    assert not (worker / "tests/old_helper.py").exists(), "a retired scaffold file must go"
    assert not (worker / "legacy").exists(), "and its emptied directory with it"
    assert verify_worker(worker) == []
    in_worker = (worker / worker_mod.MANIFEST_NAME).read_text(encoding="utf-8")
    sibling = worker.with_name(worker.name + ".manifest.json").read_text(encoding="utf-8")
    assert in_worker == sibling, "both manifests are rebuilt from the same bytes"
    manifest = json.loads(sibling)
    assert "tests/test_seed_sweep.py" in manifest["files"]
    assert "tests/old_helper.py" not in manifest["files"]
    assert manifest["editable"] == list(worker_mod.EDITABLE)
    assert seeds_sidecar_path(worker).is_file()
    assert result["seeds"]["seeds"][0] == SEEDED_DEFAULT_SEED
    assert {
        name: hashlib.sha256((worker / name).read_bytes()).hexdigest()
        for name in ("game.py", "solver.py")
    } == before, "resync must never touch the editable pair"
    assert any("test_seed_sweep.py" in line for line in result["changes"])

    proc = _validate(worker)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert _sweep_ids(proc.stdout) <= {str(s) for s in result["seeds"]["seeds"]}


def test_resync_restores_the_repair_path(tmp_path):
    """The drift raise is a symptom of the generation gap, so closing the gap
    must make repair work again."""
    worker, _drifted = _born_stale(tmp_path, "w-repair", SEEDED)
    resync_worker(worker, cfg=_CFG, authored_seed=SEEDED_DEFAULT_SEED)
    (worker / "tests/_harness.py").unlink()
    assert repair_worker(worker) == ["restored tests/_harness.py"]
    assert verify_worker(worker) == []


def test_resync_is_a_noop_on_a_worker_already_on_todays_generation(tmp_path):
    worker = _worker(tmp_path, "w-current", SEEDED)
    write_seeds_sidecar(worker, _CFG, authored_seed=SEEDED_DEFAULT_SEED)
    result = resync_worker(worker, cfg=_CFG, authored_seed=SEEDED_DEFAULT_SEED)
    assert [line for line in result["changes"] if "seeds.json" not in line] == [], result
    assert verify_worker(worker) == []


def test_resync_keeps_the_born_with_hashes_so_a_revival_is_not_read_as_bare(tmp_path):
    """THE REVIVAL HAZARD. The manifest's editable entries are the bytes the
    worker was BORN with, and `s2_implement.worker_is_bare` reads them to pick
    the green loop's prompt: bare means "reissue the whole mission", written
    means "here is what to fix". A resync that re-hashed an implemented pair
    would report a revived worker as bare and throw away its fix path."""
    fresh, _drifted = _born_stale(tmp_path, "w-bare")
    implemented, _drifted2 = _born_stale(tmp_path, "w-written", SEEDED)
    assert worker_is_bare(fresh) and not worker_is_bare(implemented), "rig wall"

    for worker in (fresh, implemented):
        resync_worker(worker, cfg=_CFG, authored_seed=SEEDED_DEFAULT_SEED)

    assert worker_is_bare(fresh), "an untouched scaffold is still bare after a resync"
    assert not worker_is_bare(implemented), (
        "a resynced worker with an implementation must NOT read as bare — the green loop "
        "would reissue the mission instead of the fix prompt"
    )
    manifest = json.loads(
        implemented.with_name(implemented.name + ".manifest.json").read_text(encoding="utf-8")
    )
    placeholder = hashlib.sha256(
        (worker_mod.TEMPLATE_DIR / "game.py").read_bytes()
    ).hexdigest()
    assert manifest["files"]["game.py"] == placeholder, (
        "the recorded editable hash is the birth hash, not today's implementation"
    )


def test_resync_without_a_config_writes_no_sidecar(tmp_path):
    worker, _drifted = _born_stale(tmp_path, "w-nocfg", SEEDED)
    result = resync_worker(worker)
    assert result["seeds"] is None
    assert not seeds_sidecar_path(worker).exists()
    assert (worker / "tests/test_seed_sweep.py").is_file()
    proc = _validate(worker)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "3 skipped" in proc.stdout, "no sidecar, no sweep — a premise, not a pass"


def test_resync_refuses_a_tree_that_is_not_an_instantiated_worker(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    _install(bare, SEEDED)
    with pytest.raises(FileNotFoundError, match="not an instantiated worker"):
        resync_worker(bare)


def test_resync_refuses_a_tree_missing_the_editable_pair(tmp_path):
    worker = _worker(tmp_path, "w-nopair", SEEDED)
    (worker / "solver.py").unlink()
    with pytest.raises(FileNotFoundError, match="resync never writes the editable pair"):
        resync_worker(worker)


def test_resync_refuses_a_missing_worker(tmp_path):
    with pytest.raises(NotADirectoryError):
        resync_worker(tmp_path / "nothing-here")


def test_the_resync_cli_reports_what_it_changed(tmp_path):
    worker, _drifted = _born_stale(tmp_path, "w-cli", SEEDED)
    proc = subprocess.run(
        [sys.executable, "-m", "gen.worker", "--dest", str(worker), "--resync"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300, check=False,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "resynced" in proc.stdout and "tests/test_seed_sweep.py" in proc.stdout
    assert "no seed sidecar was written" in proc.stdout, (
        "a resync without --config must say the sweep will skip"
    )
    assert (worker / "tests/test_seed_sweep.py").is_file()


@pytest.mark.parametrize(
    "argv",
    [["--resync", "--verify"], ["--resync", "--force"], ["--config", "config/template.yaml"]],
    ids=["resync+verify", "resync+force", "config-without-resync"],
)
def test_the_cli_refuses_incoherent_flag_combinations(tmp_path, argv):
    proc = subprocess.run(
        [sys.executable, "-m", "gen.worker", "--dest", str(tmp_path / "x"), *argv],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300, check=False,
    )
    assert proc.returncode != 0 and "error" in proc.stderr.lower(), proc.stderr


# --- 8. the seam -------------------------------------------------------------


def _s2_runner_ast() -> ast.FunctionDef:
    tree = ast.parse(ORCHESTRATOR_PY.read_text(encoding="utf-8"), filename=str(ORCHESTRATOR_PY))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "s2_implement":
            return node
    raise AssertionError(f"no `def s2_implement` in {ORCHESTRATOR_PY}")


def test_the_orchestrator_writes_the_sidecar_where_it_instantiates():
    """Work item 1's seam, pinned on the runner's AST: the sidecar write lives
    in the SAME branch as the instantiation — the one place a worker is born."""
    runner = _s2_runner_ast()
    branches = [
        node for node in ast.walk(runner)
        if isinstance(node, ast.If)
        and any(
            isinstance(call.func, ast.Name) and call.func.id == "instantiate_worker"
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
        )
    ]
    assert branches, "the s2 runner no longer calls instantiate_worker"
    innermost = min(branches, key=lambda node: len(list(ast.walk(node))))
    body_calls = {
        call.func.id
        for statement in innermost.body
        for call in ast.walk(statement)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }
    assert {"instantiate_worker", "write_seeds_sidecar"} <= body_calls, (
        f"the instantiation branch calls {sorted(body_calls)} — E-0 writes the seed sidecar "
        "at worker instantiation, so a worker is never born without one"
    )


def test_an_existing_worker_is_not_re_sidecarred_by_the_seam():
    """The seam is inside `if not worker.exists()`, so a resumed slot keeps
    whatever it has (and a worker without a sidecar simply skips the sweep)."""
    runner = _s2_runner_ast()
    writes = [
        node for node in ast.walk(runner)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "write_seeds_sidecar"
    ]
    assert len(writes) == 1, (
        f"the s2 runner calls write_seeds_sidecar {len(writes)} time(s); E-0's seam is one call, "
        "in the instantiation branch"
    )
