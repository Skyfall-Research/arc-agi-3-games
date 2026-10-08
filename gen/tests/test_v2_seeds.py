"""E-0 BLIND LANE — in-loop seed validation, written from the contract alone.

Run: .venv/bin/python -m pytest gen/tests/test_v2_seeds.py -q

THE LANE'S RULE: every expectation here comes from
`docs/v2/contracts/E-0-inloop-seed-validation.md` (including Addendum 1) and
every assertion message cites the sentence it is pinning. The implementation
was read only to DISCOVER the surfaces the contract promises — which function,
which file, which flag — never to borrow an expectation from it. The
implementer's own battery (`gen/tests/test_e0_seeds.py`) was not opened.

A promised surface that is missing or undriveable is a LOUD failure carrying
the contract sentence, never a silent skip.

WHAT THE CONTRACT ASKS THIS FILE TO PIN (§Blind lane V1-V6, as corrected by
Addendum 1):

  V1  the sidecar equals `validation_seeds`' output exactly, with one list
      re-derived by hand from the sha construction the Evidence quotes;
  V2  the sweep catches what S6 catches — the `s6_seeded` reference pair goes
      GREEN under `make validate`, the `s6_seeded_broken` twin goes RED
      ("the V2 red fixture exists in-repo ... pin the class not the slot");
  V3  S6-parity semantics — EXPLICIT construction (observed, by recording the
      kwargs both classes are handed) and S6's 600 bound (a solver needing
      601-1200 actions passes the old harness bound and FAILS the sweep);
  V4  premise-skips — no `build_layout` green, sidecar absent skips, an empty
      seed list is a loud config error and not a silent pass;
  V5  resync — a PLANTED stale worker keeps today's behaviour absent resync
      (drift still raises) and comes forward with it;
  V6  instantiation — a fresh pipeline worker gets the sidecar automatically,
      and every path without a sidecar is today's bytes.

It also pins the Work items the blind lane can measure from outside: §4 (the
600 bound as shared truth), §5 (the sweep rides `make validate`, so the
building agent runs it on every attempt; the count stays honest against
`package.seeds_validated`) and §6 (the two doc sentences).

HERMETIC (§Blind lane "Hermetic" + §Hard rules): tmp roots only; autouse
fixtures forbid the network and every driver, fail any test that writes under
the repo's own `out/` or `games/`, and fail any test that leaves a byte of
`worker-template/` changed (this file plants its stale worker from a drifted
COPY of the template, so that guard is load-bearing).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from gen import orchestrator as orch
from gen import s6_package
from gen import worker as worker_mod
from gen.config import REPO_ROOT, load_config
from gen.s2_implement import LAYOUT_SEED_CONTRACT, _run_validate, worker_is_bare
from gen.worker import (
    EDITABLE,
    GENERATED,
    MANIFEST_NAME,
    build_manifest,
    instantiate_worker,
    repair_worker,
    resync_worker,
    seeds_sidecar_path,
    verify_worker,
    write_seeds_sidecar,
)

# --------------------------------------------------------------------------- #
# the contract's own constants, quoted
# --------------------------------------------------------------------------- #

#: §Evidence "SEED DERIVATION IS PURE + DETERMINISTIC ... REPRODUCED by hand
#: for lantern (batch_seed 11 -> 3350830609, 492724337, 3671545037,
#: 2989172056)". The slot name is the lantern slug the contract names
#: ("stopped lantern-path-parity-trace at the cap on 10-01").
LANTERN_BATCH_SEED = 11
LANTERN_GAME_ID = "lantern-path-parity-trace"
LANTERN_EXTRAS = [3350830609, 492724337, 3671545037, 2989172056]

#: §Evidence "S6 drives EVERY seed ... under MAX_ACTIONS = 600 (:267)".
S6_BOUND = 600
#: §Evidence "The harness today constructs NO-ARG ... under MAX_ACTIONS = 1200".
OLD_HARNESS_BOUND = 1200

#: §Evidence "The reference pair that must PASS a sweep:
#: gen/tests/fixtures/s6_seeded/{game,solver}.py"; Addendum 1 "the V2 red
#: fixture exists in-repo (gen/tests/fixtures/s6_seeded_broken)".
FIXTURES = Path(__file__).resolve().parent / "fixtures"
GREEN_PAIR = FIXTURES / "s6_seeded"
RED_PAIR = FIXTURES / "s6_seeded_broken"
#: Both fixtures bake `DEFAULT_LAYOUT_SEED = 13` as their authored default.
PAIR_AUTHORED_SEED = 13

#: §Evidence "FIXTURE BLAST RADIUS: gen/tests/toy_worker ... have NO
#: build_layout and test_b1_acceptance.py:44-50 requires `make validate` green
#: on them."
TOY_PAIR = Path(__file__).resolve().parent / "toy_worker"

CONFIG = "config/b001-pilot.yaml"

# --------------------------------------------------------------------------- #
# guards
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _no_network_no_driver(monkeypatch):
    """§Hard rules: "no live drivers; no network"."""

    def _forbidden(*args, **kwargs):
        raise AssertionError(
            "E-0 §Hard rules: 'no API spend; no live drivers; no network' — a blind-lane "
            "test opened a socket or asked for a driver"
        )

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    from gen import backends

    monkeypatch.setattr(backends, "get_driver", _forbidden)


@pytest.fixture(autouse=True)
def _repo_is_never_the_workspace():
    """§Hard rules: "never write under the real out/ or games/ (copies in tmp only)"."""
    roots = [REPO_ROOT / "out", REPO_ROOT / "games"]

    def snapshot():
        return {
            str(root): (sorted(str(p) for p in root.rglob("*")) if root.exists() else None)
            for root in roots
        }

    before = snapshot()
    yield
    after = snapshot()
    for root in roots:
        assert after[str(root)] == before[str(root)], (
            f"E-0 §Hard rules: 'never write under the real out/ or games/ (copies in tmp "
            f"only)' — a blind-lane test changed {root}"
        )


@pytest.fixture(autouse=True)
def _template_is_never_written():
    """The stale-worker plant works from a COPY; the real template must not move.

    §Evidence "TEMPLATE-REACH HAZARD": a template edit makes every existing
    worker's REPAIR path raise "template drift". A blind-lane test that edited
    `worker-template/` in place would break the whole suite, so it fails here.
    """
    template = worker_mod.TEMPLATE_DIR

    def snapshot():
        return {
            path.relative_to(template).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(template.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts
        }

    before = snapshot()
    yield
    assert snapshot() == before, (
        "E-0 §Evidence TEMPLATE-REACH HAZARD: 'a template edit makes their REPAIR path raise "
        '"template drift"\' — a blind-lane test modified the real worker-template/'
    )


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _cfg() -> dict:
    return load_config(CONFIG)


def _hand_cfg(batch_seed: int, wanted: int = 5) -> dict:
    """The smallest config `validation_seeds` accepts, for the by-hand pins."""
    return {
        "batch": {"seed": batch_seed},
        "package": {"seeds_validated": wanted, "split": {"train": 0.7, "eval": 0.3}},
    }


def _hand_derive(batch_seed: int, game_id: str, authored: int | None, count: int) -> list[int]:
    """§Evidence, re-implemented by hand: `[authored] + int(sha256(
    f"{batch_seed}:{game_id}:s6:{counter}").hexdigest()[:8], 16)` extras."""
    seeds: list[int] = [] if authored is None else [int(authored)]
    counter = 0
    while len(seeds) < count:
        counter += 1
        digest = hashlib.sha256(f"{batch_seed}:{game_id}:s6:{counter}".encode()).hexdigest()
        candidate = int(digest[:8], 16)
        if candidate not in seeds:
            seeds.append(candidate)
    return seeds


def _slot(tmp_path: Path, name: str) -> Path:
    """`<tmp>/<slot>/` — Addendum 1: "game_id defaults to the slot DIRECTORY name"."""
    slot = tmp_path / name
    slot.mkdir(parents=True, exist_ok=True)
    return slot


def _install(worker: Path, source: Path) -> None:
    for name in EDITABLE:
        shutil.copy2(source / name, worker / name)


def _write_spec(slot: Path, seed: int) -> Path:
    """The `spec.yaml` beside the worker — §Work 1 "authored seed from the
    spec's layout.seed"."""
    path = slot / "spec.yaml"
    path.write_text(f"game:\n  layout:\n    seed: {seed}\n", encoding="utf-8")
    return path


def _worker_with(
    tmp_path: Path,
    name: str,
    source: Path,
    *,
    sidecar: bool = True,
    authored_seed: int | None = PAIR_AUTHORED_SEED,
    cfg: dict | None = None,
) -> Path:
    slot = _slot(tmp_path, name)
    worker = slot / "worker"
    instantiate_worker(worker)
    _install(worker, source)
    if sidecar:
        write_seeds_sidecar(worker, cfg or _cfg(), authored_seed=authored_seed)
    return worker


def _validate(worker: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    """§Evidence "THE WORKER VALIDATE = worker-template/Makefile"."""
    return subprocess.run(
        ["make", "validate"], cwd=worker, capture_output=True, text=True,
        timeout=900, check=False, env=env,
    )


def _pytest(worker: Path, target: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rs", target], cwd=worker,
        capture_output=True, text=True, timeout=900, check=False, env=env,
    )


def _tail(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def _import_harness(worker: Path):
    """Import `tests._harness` OUT of a worker tree, then unload it again.

    The scaffold's harness is standalone by design ("this tree is standalone
    and cannot import the pipeline"), so the only way to read its surfaces is
    to import it as the worker's own `make validate` does.
    """

    def _unload():
        for name in [n for n in list(sys.modules) if n == "tests" or n.startswith("tests.")]:
            del sys.modules[name]

    sys.path.insert(0, str(worker))
    try:
        _unload()
        import tests._harness as harness  # type: ignore[import-not-found]

        return harness
    finally:
        sys.path.remove(str(worker))
        _unload()


def _read_sidecar(worker: Path) -> dict:
    path = seeds_sidecar_path(worker)
    assert path.is_file(), (
        f"E-0 §Work 1: the pipeline 'writes it to a SIBLING file beside the worker' — "
        f"{path} is absent"
    )
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# the V3 synthetic pair: a winnable game whose only line needs 601-1200 actions
# --------------------------------------------------------------------------- #

#: §Blind V3 "a solver needing 601-1200 actions passes the old harness bound
#: but FAILS the sweep". 700 is strictly inside that window.
PACING_LINE = 700

_PACING_GAME_SOURCE = '''\
"""Blind-lane synthetic (E-0 §Blind V3): winnable, but only after 700 actions.

Also RECORDS every construction it is handed (args + kwargs) so the blind lane
can observe that the sweep constructs EXPLICITLY rather than no-arg.
"""

import json
import os

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

DEFAULT_LAYOUT_SEED = 7
LINE_LENGTH = __PACING_LINE__
WALL, PLAYER, GOAL = 4, 9, 12
CTOR_LOG = os.environ.get("E0_BLIND_CTOR_LOG")


def build_layout(seed: int) -> list:
    return [{"level": 1, "seed": int(seed), "line": LINE_LENGTH}]


def record_ctor(kind, args, kwargs):
    if not CTOR_LOG:
        return
    row = {"kind": kind, "args": list(args), "kwargs": dict(sorted(kwargs.items()))}
    with open(CTOR_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\\n")


def _level():
    return Level(sprites=[
        Sprite([[WALL] * 8], name="wall_top", x=0, y=0),
        Sprite([[WALL] * 8], name="wall_bottom", x=0, y=7),
        Sprite([[WALL]] * 6, name="wall_left", x=0, y=1),
        Sprite([[WALL]] * 6, name="wall_right", x=7, y=1),
        Sprite([[GOAL]], name="goal", x=6, y=6, layer=1, collidable=False),
        Sprite([[PLAYER]], name="player", x=1, y=1, layer=2),
    ])


class PacingBoard(ARCBaseGame):
    def __init__(self, *args, **kwargs) -> None:
        record_ctor("game", args, kwargs)
        seed = kwargs.get("layout_seed", args[0] if args else None)
        self.layout_seed = DEFAULT_LAYOUT_SEED if seed is None else int(seed)
        self._layout = build_layout(self.layout_seed)
        self._presses = 0
        super().__init__(
            game_id="e0-blind-pacing",
            levels=[_level()],
            camera=Camera(width=8, height=8),
            available_actions=[1, 2, 3, 4],
        )

    def step(self) -> None:
        if self.action.id == GameAction.RESET:
            self._presses = 0
            self.complete_action()
            return
        self._presses += 1
        self.complete_action()
        if self._presses >= LINE_LENGTH:
            self.next_level()
'''

_PACING_GAME = _PACING_GAME_SOURCE.replace("__PACING_LINE__", str(PACING_LINE))

_PACING_SOLVER = '''\
"""Blind-lane synthetic solver (E-0 §Blind V3): presses until the level lands."""

import hashlib
import importlib.util
import sys
from pathlib import Path

from arcengine import ActionInput, GameAction

_GAME_PATH = Path(__file__).resolve().with_name("game.py")


def _game_module():
    tag = hashlib.sha256(str(_GAME_PATH).encode()).hexdigest()[:12]
    name = f"e0_blind_pacing_game_{tag}"
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, _GAME_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Solver:
    def __init__(self, *args, **kwargs) -> None:
        mod = _game_module()
        mod.record_ctor("solver", args, kwargs)
        seed = kwargs.get("layout_seed", args[0] if args else None)
        self.layout_seed = mod.DEFAULT_LAYOUT_SEED if seed is None else int(seed)
        self.reset()

    def reset(self) -> None:
        self._pressed = 0

    def next_action(self, frame) -> "ActionInput | None":
        if int(frame.levels_completed) >= 1:
            return None
        self._pressed += 1
        return ActionInput(id=GameAction.ACTION1)
'''

PACING_AUTHORED_SEED = 7


def _pacing_worker(tmp_path: Path, name: str = "pacing-slot") -> Path:
    slot = _slot(tmp_path, name)
    worker = slot / "worker"
    instantiate_worker(worker)
    (worker / "game.py").write_text(_PACING_GAME, encoding="utf-8")
    (worker / "solver.py").write_text(_PACING_SOLVER, encoding="utf-8")
    write_seeds_sidecar(worker, _cfg(), authored_seed=PACING_AUTHORED_SEED)
    return worker


# --------------------------------------------------------------------------- #
# V1 — derivation parity
# --------------------------------------------------------------------------- #


def test_v1_sidecar_equals_validation_seeds_exactly(tmp_path):
    """§Blind V1: "the sidecar for a fresh hermetic worker equals
    validation_seeds' output exactly"."""
    cfg = _cfg()
    worker = _worker_with(tmp_path, "parity-slot", GREEN_PAIR)
    payload = _read_sidecar(worker)

    expected = s6_package.validation_seeds(cfg, "parity-slot", PAIR_AUTHORED_SEED)
    assert payload["seeds"] == expected, (
        "E-0 §Blind V1: 'the sidecar for a fresh hermetic worker equals validation_seeds' "
        f"output exactly' — sidecar {payload['seeds']} vs validation_seeds {expected}"
    )


def test_v1_one_list_re_derived_by_hand(tmp_path):
    """§Blind V1: "re-derive one list by hand (the sha construction above) and pin it"."""
    worker = _worker_with(tmp_path, "byhand-slot", GREEN_PAIR)
    payload = _read_sidecar(worker)

    by_hand = _hand_derive(
        payload["batch_seed"], payload["game_id"], payload["authored_seed"], payload["count"]
    )
    assert payload["seeds"] == by_hand, (
        "E-0 §Blind V1 + §Evidence: 'seeds = [authored default] + int(sha256(f\"{batch_seed}:"
        '{game_id}:s6:{counter}").hexdigest()[:8], 16) extras\' — the sidecar does not match '
        f"the by-hand derivation: {payload['seeds']} vs {by_hand}"
    )
    assert payload["seeds"][0] == PAIR_AUTHORED_SEED, (
        "E-0 §Evidence: the list is '[authored default] + ... extras', so seeds[0] is the "
        f"spec's layout.seed ({PAIR_AUTHORED_SEED}), got {payload['seeds'][0]}"
    )


def test_v1_the_contracts_quoted_lantern_list_is_reproduced():
    """§Evidence: "REPRODUCED by hand for lantern (batch_seed 11 -> 3350830609,
    492724337, 3671545037, 2989172056)".

    The one number the contract hands this lane that it did not compute itself.
    If the stage's derivation ever moves, this is the pin that says so.
    """
    cfg = _hand_cfg(LANTERN_BATCH_SEED)
    authored = 173  # §Evidence: lantern's own authored seed ("its own authored seed 173")

    produced = s6_package.validation_seeds(cfg, LANTERN_GAME_ID, authored)
    assert produced == [authored, *LANTERN_EXTRAS], (
        "E-0 §Evidence: 'REPRODUCED by hand for lantern (batch_seed 11 -> 3350830609, "
        f"492724337, 3671545037, 2989172056)' — got {produced}"
    )
    assert _hand_derive(LANTERN_BATCH_SEED, LANTERN_GAME_ID, authored, 5) == produced, (
        "E-0 §Evidence: the sha construction quoted in the contract must be the one the "
        "stage runs"
    )


def test_v1_sidecar_carries_the_provenance_the_contract_names(tmp_path):
    """§Work 1: "Contents: the ordered seed list + enough provenance to
    re-derive (batch_seed, game_id, count)"."""
    cfg = _cfg()
    worker = _worker_with(tmp_path, "provenance-slot", GREEN_PAIR)
    payload = _read_sidecar(worker)

    for key in ("seeds", "batch_seed", "game_id", "count"):
        assert key in payload, (
            "E-0 §Work 1: 'Contents: the ordered seed list + enough provenance to re-derive "
            f"(batch_seed, game_id, count)' — the sidecar has no {key!r}"
        )
    assert payload["batch_seed"] == cfg["batch"]["seed"], (
        "E-0 §Work 1: the recorded batch_seed must be the config's"
    )
    assert payload["count"] == len(payload["seeds"]), (
        "E-0 §Work 1: 'count' must describe the list it ships with"
    )


def test_v1_the_writer_never_re_implements_the_derivation(tmp_path, monkeypatch):
    """§Work 1: "Keep a single source of truth: the sidecar writer calls the SAME
    validation_seeds — never a re-implementation".

    Observed the only way it can be: bend `validation_seeds` and watch the
    sidecar bend with it. A second copy of the arithmetic would not.
    """
    marker = [111, 222, 333]
    monkeypatch.setattr(s6_package, "validation_seeds", lambda *a, **k: list(marker))

    worker = _worker_with(tmp_path, "sot-slot", GREEN_PAIR)
    payload = _read_sidecar(worker)
    assert payload["seeds"] == marker, (
        "E-0 §Work 1: 'the sidecar writer calls the SAME validation_seeds — never a "
        f"re-implementation' — bending validation_seeds left the sidecar at {payload['seeds']}, "
        "so the writer holds a second copy of the derivation"
    )


def test_v1_the_sidecar_is_a_sibling_and_never_inside_the_worker(tmp_path):
    """§Work 1: "a SIBLING file beside the worker ... NEVER inside the worker
    tree"; §Evidence EDIT-SCOPE: "no new files inside the worker tree ...
    SIBLING files beside the worker ... are pipeline-owned and legal"."""
    worker = _worker_with(tmp_path, "sibling-slot", GREEN_PAIR)
    path = seeds_sidecar_path(worker)

    assert path.parent == worker.parent, (
        "E-0 §Work 1: the sidecar is 'a SIBLING file beside the worker', not a child of it — "
        f"{path} sits under {path.parent}"
    )
    assert worker not in path.parents, (
        f"E-0 §Work 1: 'NEVER inside the worker tree' — {path} is inside {worker}"
    )
    assert verify_worker(worker) == [], (
        "E-0 §Evidence EDIT-SCOPE: 'no new files inside the worker tree' — writing the sidecar "
        "left an edit-scope violation"
    )
    assert _validate(worker).returncode == 0, (
        "E-0 §Evidence EDIT-SCOPE: a sibling sidecar is 'pipeline-owned and legal', so the "
        "worker's own scope check must stay green"
    )


# --------------------------------------------------------------------------- #
# V2 — the sweep catches what S6 catches
# --------------------------------------------------------------------------- #


def test_v2_the_reference_pair_goes_green(tmp_path):
    """§Blind V2: "the s6_seeded reference pair goes GREEN"; §Evidence: "The
    reference pair that must PASS a sweep: gen/tests/fixtures/s6_seeded"."""
    worker = _worker_with(tmp_path, "green-slot", GREEN_PAIR)
    payload = _read_sidecar(worker)
    assert len(payload["seeds"]) == 5, "the b001 config asks for 5 validation seeds"

    proc = _validate(worker)
    assert proc.returncode == 0, (
        "E-0 §Blind V2: 'the s6_seeded reference pair goes GREEN' — `make validate` returned "
        f"{proc.returncode}:\n{_tail(proc)[-4000:]}"
    )
    assert "validate: GREEN" in proc.stdout


def test_v2_the_seed_reject_class_goes_red(tmp_path):
    """§Blind V2: "a fixture game whose build_layout breaks on any non-authored
    seed ... goes RED under `make validate` with the sidecar present";
    Addendum 1: "the V2 red fixture exists in-repo
    (gen/tests/fixtures/s6_seeded_broken) ... pin the class not the slot"."""
    worker = _worker_with(tmp_path, "red-slot", RED_PAIR)
    payload = _read_sidecar(worker)

    proc = _validate(worker)
    tail = _tail(proc)
    assert proc.returncode != 0, (
        "E-0 §Blind V2: the seed-reject twin must go 'RED under `make validate` with the "
        f"sidecar present' — it returned 0:\n{tail[-4000:]}"
    )

    assert str(S6_BOUND) in tail, (
        "E-0 §Evidence: the verdict is reached 'under MAX_ACTIONS = 600', so the red output "
        f"must say which bound it applied:\n{tail[-4000:]}"
    )
    # THE CLASS, not the slot (Addendum 1): the solver wins its AUTHORED seed
    # and loses every derived one — which is exactly why this defect used to
    # survive the build loop. Read off the FAILED summary, so the set is exact.
    failed = {line.split("[", 1)[1].rstrip("]")
              for line in tail.splitlines() if line.startswith("FAILED") and "[" in line}
    assert failed == {str(seed) for seed in payload["seeds"][1:]}, (
        "E-0 §Blind V2 + Addendum 1 ('pin the class not the slot'): the defect class is a "
        "solver that wins its AUTHORED seed and loses the derived ones, so the red seeds must "
        f"be exactly {payload['seeds'][1:]} — the run failed {sorted(failed)}:\n{tail[-4000:]}"
    )


def test_v2_the_same_red_pair_is_green_without_a_sidecar(tmp_path):
    """§Blind V2 + §Work 2: the verdict comes from the sidecar being PRESENT —
    "PREMISE-SKIP (not fail) when: the sidecar is absent".

    Same bytes, two verdicts: that difference IS the in-loop property.
    """
    worker = _worker_with(tmp_path, "red-nosidecar", RED_PAIR, sidecar=False)
    proc = _validate(worker)
    assert proc.returncode == 0, (
        "E-0 §Work 2: 'PREMISE-SKIP (not fail) when: the sidecar is absent' — the seed-reject "
        f"twin went red with no sidecar:\n{_tail(proc)[-4000:]}"
    )


# --------------------------------------------------------------------------- #
# V3 — S6-parity semantics
# --------------------------------------------------------------------------- #


def test_v3_the_sweep_constructs_both_classes_explicitly(tmp_path):
    """§Blind V3: "the sweep constructs EXPLICITLY (observe construction
    kwargs)"; §Evidence S6-PARITY TRAP: "S6 drives EVERY seed — authored
    included — through EXPLICIT `Game(layout_seed=s)` / `Solver(layout_seed=s)`
    ... A sweep that does not mirror S6's construction + bound does not
    reproduce S6's verdict and is worthless"."""
    worker = _pacing_worker(tmp_path, "ctor-slot")
    seeds = _read_sidecar(worker)["seeds"]
    log = tmp_path / "ctor.jsonl"
    env = {**os.environ, "E0_BLIND_CTOR_LOG": str(log)}

    _pytest(worker, "tests/test_seed_sweep.py", env=env)
    assert log.is_file(), (
        "E-0 §Blind V3: the sweep never constructed the game or the solver — nothing to "
        "observe, so S6's construction cannot be mirrored"
    )
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]

    for kind in ("game", "solver"):
        explicit = [r["kwargs"].get("layout_seed") for r in rows
                    if r["kind"] == kind and r["args"] == [] and set(r["kwargs"]) == {"layout_seed"}]
        assert explicit == seeds, (
            f"E-0 §Blind V3: S6 drives 'EVERY seed — authored included — through EXPLICIT "
            f"`Game(layout_seed=s)` / `Solver(layout_seed=s)`'. The {kind} was constructed "
            f"explicitly at {explicit}, but the sidecar's seeds are {seeds}"
        )
    assert not [r for r in rows if r["args"]], (
        "E-0 §Blind V3: the seed is passed as the KEYWORD `layout_seed=`, exactly as S6 "
        f"passes it — a positional construction was observed: {[r for r in rows if r['args']]}"
    )
    # The solver is constructed by the sweep alone, so a no-arg solver here
    # would be the old (hiding) code path leaking into the sweep.
    assert not [r for r in rows if r["kind"] == "solver" and not r["kwargs"]], (
        "E-0 §Evidence S6-PARITY TRAP: 'a solver that plans from a module constant instead of "
        "the seed it was handed is green under no-arg construction' — the sweep constructed "
        "the solver with NO argument"
    )


def test_v3_a_601_to_1200_action_solver_passes_the_old_bound_and_fails_the_sweep(tmp_path):
    """§Blind V3: "binds at S6's 600 (a solver needing 601-1200 actions passes
    the old harness bound but FAILS the sweep)"."""
    assert S6_BOUND < PACING_LINE < OLD_HARNESS_BOUND, (
        "E-0 §Blind V3 asks for a solver 'needing 601-1200 actions'; this synthetic pair's "
        f"line is {PACING_LINE}"
    )
    worker = _pacing_worker(tmp_path, "bound-slot")

    old = _pytest(worker, "tests/test_scaffold.py")
    assert old.returncode == 0, (
        "E-0 §Blind V3: a solver needing 601-1200 actions 'passes the old harness bound' — "
        f"the pre-existing scaffold battery went red:\n{_tail(old)[-4000:]}"
    )
    assert "passed" in _tail(old)

    sweep = _pytest(worker, "tests/test_seed_sweep.py")
    tail = _tail(sweep)
    assert sweep.returncode != 0, (
        "E-0 §Blind V3: the same solver 'but FAILS the sweep' — the sweep went green at "
        f"{PACING_LINE} actions, so it is not binding at S6's {S6_BOUND}:\n{tail[-4000:]}"
    )
    assert str(S6_BOUND) in tail, (
        f"E-0 §Blind V3: the sweep 'binds at S6's 600' — its failure never names {S6_BOUND}:"
        f"\n{tail[-4000:]}"
    )
    assert str(OLD_HARNESS_BOUND) not in tail, (
        "E-0 §Evidence: 'two diverging bounds is how this class was born' — the sweep's "
        f"failure cites the old {OLD_HARNESS_BOUND} bound:\n{tail[-4000:]}"
    )


def test_v3_the_existing_no_arg_scaffold_tests_stay_as_they_are(tmp_path):
    """§Work 2: "The existing no-arg scaffold tests stay as they are (they test
    the authored default path; the sweep is additive)"; §Evidence: "The harness
    today constructs NO-ARG (_harness.py:113-116) under MAX_ACTIONS = 1200".

    V3's whole discrimination rests on this half not having moved.
    """
    worker = _pacing_worker(tmp_path, "additive-slot")
    harness = _import_harness(worker)
    assert harness.MAX_ACTIONS == OLD_HARNESS_BOUND, (
        "E-0 §Evidence: the scaffold battery binds at 1200 and the sweep is 'additive'; the "
        f"old bound now reads {harness.MAX_ACTIONS}"
    )
    # §Work 2: "_harness gains an explicit-seed construction helper".
    import inspect

    assert "layout_seed" in inspect.signature(harness.run_solver).parameters, (
        "E-0 §Work 2: '_harness gains an explicit-seed construction helper' — `run_solver` "
        "takes no layout_seed"
    )
    assert callable(getattr(harness, "read_seed_plan", None)), (
        "E-0 §Work 2: the sweep runs 'for each sidecar seed', so the harness must be able to "
        "read the sidecar"
    )

    log = tmp_path / "scaffold-ctor.jsonl"
    env = {**os.environ, "E0_BLIND_CTOR_LOG": str(log)}
    proc = _pytest(worker, "tests/test_scaffold.py", env=env)
    assert proc.returncode == 0, _tail(proc)[-4000:]
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
    assert rows, "the scaffold battery constructed nothing"
    assert all(not row["args"] and not row["kwargs"] for row in rows), (
        "E-0 §Work 2: 'The existing no-arg scaffold tests stay as they are (they test the "
        f"authored default path)' — a scaffold-battery construction took arguments: "
        f"{[r for r in rows if r['args'] or r['kwargs']]}"
    )


def test_v3_the_pass_rule_is_win_with_every_level_credited(tmp_path):
    """§Evidence: "pass = win AND levels_completed == len(S4 baselines)";
    §Work 2: "pass = win with all levels completed"."""
    worker = _worker_with(tmp_path, "passrule-slot", GREEN_PAIR)
    source = (worker / "tests/test_seed_sweep.py").read_text(encoding="utf-8")

    assert "levels_completed" in source and "WIN" in source, (
        "E-0 §Work 2: the sweep's pass rule is 'win with all levels completed' — its source "
        "never mentions one of the two halves, so the rule cannot be the one S6 applies"
    )
    proc = _validate(worker)
    assert proc.returncode == 0, (
        "E-0 §Work 2: the reference pair wins all 6 of its levels and must pass the rule:\n"
        f"{_tail(proc)[-4000:]}"
    )


# --------------------------------------------------------------------------- #
# V4 — premise-skips
# --------------------------------------------------------------------------- #


def test_v4_a_game_without_build_layout_is_green_with_a_sidecar(tmp_path):
    """§Blind V4: "toy worker (no build_layout) green"; §Work 2: "PREMISE-SKIP
    (not fail) when ... the game lacks build_layout/layout_seed support — the
    toy-worker fixtures and test_b1 stay green untouched"."""
    assert "build_layout" not in (TOY_PAIR / "game.py").read_text(encoding="utf-8"), (
        "E-0 §Evidence FIXTURE BLAST RADIUS names gen/tests/toy_worker as the pair with 'NO "
        "build_layout'; it now has one, so this premise-skip case is no longer modelled"
    )
    worker = _worker_with(tmp_path, "toy-slot", TOY_PAIR, authored_seed=1)

    proc = _validate(worker)
    assert proc.returncode == 0, (
        "E-0 §Blind V4: 'toy worker (no build_layout) green' — `make validate` returned "
        f"{proc.returncode} with a sidecar present:\n{_tail(proc)[-4000:]}"
    )
    assert "skipped" in proc.stdout, (
        "E-0 §Work 2: a game that 'lacks build_layout/layout_seed support' must PREMISE-SKIP, "
        f"which is a reported skip and not an invisible pass:\n{proc.stdout[-4000:]}"
    )


def test_v4_the_toy_fixture_stays_green_untouched(tmp_path):
    """§Work 2: "the toy-worker fixtures and test_b1 stay green untouched" —
    the same assertion `test_b1_acceptance.py:44-50` makes."""
    worker = _worker_with(tmp_path, "toy-b1", TOY_PAIR, sidecar=False)
    proc = _validate(worker)
    assert proc.returncode == 0, (
        "E-0 §Evidence FIXTURE BLAST RADIUS: 'test_b1_acceptance.py:44-50 requires `make "
        f"validate` green on them':\n{_tail(proc)[-4000:]}"
    )
    assert "validate: GREEN" in proc.stdout
    assert "[scope] OK" in proc.stdout


def test_v4_absent_sidecar_skips_rather_than_fails(tmp_path):
    """§Blind V4: "sidecar absent -> skip not fail"."""
    worker = _worker_with(tmp_path, "nosidecar-slot", GREEN_PAIR, sidecar=False)
    assert not seeds_sidecar_path(worker).exists()

    proc = _pytest(worker, "tests/test_seed_sweep.py")
    tail = _tail(proc)
    assert proc.returncode == 0, (
        f"E-0 §Blind V4: 'sidecar absent -> skip not fail' — the sweep went red:\n{tail[-4000:]}"
    )
    assert "skipped" in tail, (
        "E-0 §Blind V4: an absent sidecar is a SKIP, which must be reported; the run shows no "
        f"skip at all:\n{tail[-4000:]}"
    )
    assert seeds_sidecar_path(worker).name in tail, (
        "E-0 §Blind V4: 'skip not fail' must still say WHY — the skip reason names no sidecar "
        f"path, so an unsynced worker is silent about its missing premise:\n{tail[-4000:]}"
    )


def test_v4_an_authored_default_the_game_does_not_bake_is_loud(tmp_path):
    """Addendum 1 (ratified): "the authored-default parity test (spec
    layout.seed == S6's recorded authored_seed, 9/9 measured)".

    S6 validates the seed the GAME bakes in; the sidecar's first seed is the
    one the SPEC authored. If they disagree, the sweep is driving a list the
    packager will not use — a premise failure, so it must be loud.
    """
    worker = _worker_with(tmp_path, "authored-parity-slot", GREEN_PAIR)
    payload = _read_sidecar(worker)
    assert payload["authored_seed"] == PAIR_AUTHORED_SEED
    payload["authored_seed"] = PAIR_AUTHORED_SEED + 1
    payload["seeds"] = [PAIR_AUTHORED_SEED + 1, *payload["seeds"][1:]]
    seeds_sidecar_path(worker).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    proc = _validate(worker)
    tail = _tail(proc)
    assert proc.returncode != 0, (
        "E-0 Addendum 1: the ratified 'authored-default parity test' must refuse a sidecar "
        "whose authored default is not the seed the game bakes in — `make validate` was "
        f"green:\n{tail[-4000:]}"
    )
    assert str(PAIR_AUTHORED_SEED) in tail and str(PAIR_AUTHORED_SEED + 1) in tail, (
        "E-0 Addendum 1: the refusal must name both the recorded default and the game's own, "
        f"or the operator cannot tell which is wrong:\n{tail[-4000:]}"
    )


def test_v4_an_empty_seed_list_is_loud_not_a_silent_pass(tmp_path):
    """§Blind V4: "empty sidecar list -> loud config error, not silent pass"."""
    worker = _worker_with(tmp_path, "emptylist-slot", GREEN_PAIR)
    payload = _read_sidecar(worker)
    payload["seeds"] = []
    payload["count"] = 0
    seeds_sidecar_path(worker).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    proc = _validate(worker)
    tail = _tail(proc)
    assert proc.returncode != 0, (
        "E-0 §Blind V4: an 'empty sidecar list -> loud config error, not silent pass' — "
        f"`make validate` was green on a sidecar carrying no seeds:\n{tail[-4000:]}"
    )
    assert "seeds" in tail, (
        "E-0 §Blind V4: the loud error must say what is wrong with the sidecar:\n"
        f"{tail[-4000:]}"
    )


def test_v4_an_unreadable_sidecar_is_loud_not_a_silent_pass(tmp_path):
    """§Blind V4, same sentence: a sidecar that EXISTS and cannot be used is a
    "loud config error, not silent pass" — an absent one is the only premise."""
    worker = _worker_with(tmp_path, "garbage-slot", GREEN_PAIR)
    seeds_sidecar_path(worker).write_text("{ this is not json", encoding="utf-8")

    proc = _validate(worker)
    assert proc.returncode != 0, (
        "E-0 §Blind V4: a sidecar that exists but cannot be used must be a 'loud config "
        f"error, not silent pass':\n{_tail(proc)[-4000:]}"
    )


# --------------------------------------------------------------------------- #
# V5 — resync
# --------------------------------------------------------------------------- #


def _drifted_template(tmp_path: Path, tag: str) -> Path:
    """A COPY of today's template, aged backwards, for planting a stale worker.

    §Evidence TEMPLATE-REACH HAZARD: "scaffolds instantiate ONLY when the
    worker dir is absent ...; existing workers keep their old tests/ forever,
    and a template edit makes their REPAIR path raise 'template drift'". This
    copy reproduces that state: one scaffold file's bytes differ, the seed
    sweep is absent from `tests/` (a pre-E-0 generation), and one file that
    today's template does not have is present.
    """
    drifted = tmp_path / f"template-of-yesterday-{tag}"
    shutil.copytree(
        worker_mod.TEMPLATE_DIR, drifted,
        ignore=shutil.ignore_patterns(*worker_mod.IGNORED_DIRS),
    )
    aged = drifted / "tests/test_scaffold.py"
    aged.write_text(aged.read_text(encoding="utf-8") + "\n# yesterday\n", encoding="utf-8")
    sweep = drifted / "tests/test_seed_sweep.py"
    if sweep.is_file():
        sweep.unlink()
    (drifted / "tests/legacy_shim.py").write_text("# retired helper\n", encoding="utf-8")
    return drifted


def _plant_stale(tmp_path: Path, name: str, source: Path, monkeypatch,
                 *, spec_seed: int = PAIR_AUTHORED_SEED) -> Path:
    drifted = _drifted_template(tmp_path, name)
    slot = _slot(tmp_path, name)
    _write_spec(slot, spec_seed)
    worker = slot / "worker"
    with monkeypatch.context() as patch:
        patch.setattr(worker_mod, "TEMPLATE_DIR", drifted)
        instantiate_worker(worker)
    _install(worker, source)
    return worker


def test_v5_a_stale_worker_has_todays_behaviour_absent_resync(tmp_path, monkeypatch):
    """§Blind V5: "an existing worker on a stale manifest (plant one) has
    today's behavior absent resync (drift raise preserved, pinned)"; §Work 3:
    "Absent an explicit resync, existing workers behave byte-for-byte as today
    (drift still raises; nothing auto-migrates)"."""
    worker = _plant_stale(tmp_path, "stale-slot", GREEN_PAIR, monkeypatch)

    assert not seeds_sidecar_path(worker).exists(), (
        "E-0 §Work 3: 'nothing auto-migrates' — instantiating against an older template must "
        "not leave an E-0 sidecar behind"
    )
    assert not (worker / "tests/test_seed_sweep.py").exists(), (
        "the planted worker is meant to BE a pre-E-0 generation; it already carries today's "
        "sweep, so V5's premise is not set up"
    )
    assert verify_worker(worker) == [], "a freshly planted worker is scope-clean"

    (worker / "tests/test_scaffold.py").unlink()
    with pytest.raises(RuntimeError, match="template drift"):
        repair_worker(worker)


def test_v5_resync_brings_the_scaffold_forward(tmp_path, monkeypatch):
    """§Blind V5: "after resync — current scaffold, both manifests regenerated,
    sidecar present, editable pair byte-untouched, repair works again";
    §Work 3: "regenerate scaffold files from today's template, regenerate BOTH
    manifests, write the seeds sidecar, NEVER touch the editable pair"."""
    worker = _plant_stale(tmp_path, "resync-slot", GREEN_PAIR, monkeypatch)
    pair_before = {name: hashlib.sha256((worker / name).read_bytes()).hexdigest()
                   for name in EDITABLE}
    sibling = worker.with_name(worker.name + ".manifest.json")
    manifest_before = sibling.read_text(encoding="utf-8")
    # NON-VACUITY: the plant must really be behind today's template.
    aged = worker / "tests/test_scaffold.py"
    assert aged.read_bytes() != (worker_mod.TEMPLATE_DIR / "tests/test_scaffold.py").read_bytes(), (
        "the planted worker is supposed to sit on a STALE scaffold; its bytes already match "
        "today's template, so 'brings it forward' is untestable here"
    )

    result = resync_worker(worker, cfg=_cfg())
    assert result["changes"], (
        "E-0 §Blind V5: a stale worker must actually move — resync reported no change"
    )

    # current scaffold
    today = _hashes(worker_mod.TEMPLATE_DIR)
    present = _hashes(worker)
    for rel, digest in today.items():
        if rel in EDITABLE:
            continue
        assert present.get(rel) == digest, (
            "E-0 §Work 3: resync must 'regenerate scaffold files from today's template' — "
            f"{rel} is missing or stale after resync"
        )
    assert "tests/legacy_shim.py" not in present, (
        "E-0 §Work 3: a file that is no longer part of today's scaffold must not survive the "
        "resync — it would be hashed in as a scaffold file"
    )
    assert (worker / "tests/test_seed_sweep.py").is_file(), (
        "E-0 §Blind V5: 'after resync — current scaffold'; the sweep is part of today's "
        "scaffold and is what arms the revived slot"
    )

    # both manifests regenerated, and identical
    in_worker = (worker / MANIFEST_NAME).read_text(encoding="utf-8")
    sibling_now = sibling.read_text(encoding="utf-8")
    assert sibling_now != manifest_before, (
        "E-0 §Work 3: 'regenerate BOTH manifests' — the sibling copy still records yesterday's "
        "scaffold"
    )
    assert in_worker == sibling_now, (
        "E-0 §Work 3: 'regenerate BOTH manifests' — the in-worker copy and the sibling "
        "disagree after resync"
    )
    assert (worker / GENERATED).is_file(), f"{GENERATED} must survive the resync"

    # sidecar present
    payload = _read_sidecar(worker)
    assert payload["seeds"] == s6_package.validation_seeds(
        _cfg(), "resync-slot", PAIR_AUTHORED_SEED
    ), "E-0 §Work 3: 'write the seeds sidecar' — the resynced list is not S6's list"

    # editable pair byte-untouched
    for name in EDITABLE:
        assert hashlib.sha256((worker / name).read_bytes()).hexdigest() == pair_before[name], (
            f"E-0 §Work 3: resync must 'NEVER touch the editable pair' — {name} changed"
        )
    assert verify_worker(worker) == [], (
        "E-0 §Blind V5: a resynced worker must be scope-clean"
    )


def test_v5_resync_carries_the_born_with_hashes_forward(tmp_path, monkeypatch):
    """Addendum 1 (ratified): "born-with hashes carried forward on resync
    (re-hashing would misread a revived worker as bare — pinned)"."""
    worker = _plant_stale(tmp_path, "bornwith-slot", GREEN_PAIR, monkeypatch)
    sibling = worker.with_name(worker.name + ".manifest.json")
    born_with = json.loads(sibling.read_text(encoding="utf-8"))["files"]

    assert worker_is_bare(worker) is False, (
        "the planted worker already carries an implementation, so it is not bare — V5's "
        "premise is not set up"
    )
    # NON-VACUITY: the born-with hashes must actually differ from today's bytes,
    # or "carried forward" and "re-hashed" would be the same manifest.
    for name in EDITABLE:
        current = hashlib.sha256((worker / name).read_bytes()).hexdigest()
        assert born_with[name] != current, (
            f"this test can only tell 'carried forward' from 're-hashed' when the implemented "
            f"{name} differs from the bytes the worker was born with; it does not"
        )

    resync_worker(worker, cfg=_cfg())
    after = json.loads(sibling.read_text(encoding="utf-8"))["files"]
    for name in EDITABLE:
        assert after[name] == born_with[name], (
            "E-0 Addendum 1: 'born-with hashes carried forward on resync' — the manifest now "
            f"records today's {name} instead of the bytes the worker was born with"
        )
    assert worker_is_bare(worker) is False, (
        "E-0 Addendum 1: 're-hashing would misread a revived worker as bare — pinned'; after "
        "resync this implemented worker reads as BARE"
    )
    # And the scaffold half of the manifest really did move forward.
    assert after != born_with, (
        "E-0 §Work 3: the scaffold entries must be rebuilt even while the editable pair's are "
        "carried forward"
    )


def test_v5_repair_works_again_after_resync(tmp_path, monkeypatch):
    """§Blind V5: "after resync — ... repair works again"."""
    worker = _plant_stale(tmp_path, "repair-slot", GREEN_PAIR, monkeypatch)
    resync_worker(worker, cfg=_cfg())

    (worker / "tests/test_scaffold.py").unlink()
    repairs = repair_worker(worker)
    assert repairs, (
        "E-0 §Blind V5: 'repair works again' — repair_worker reported nothing to do for a "
        "deleted scaffold file"
    )
    assert verify_worker(worker) == [], (
        "E-0 §Blind V5: 'repair works again' — the repaired tree is still out of scope"
    )
    assert _validate(worker).returncode == 0, (
        "E-0 §Blind V5: a resynced, repaired reference worker must validate green"
    )


def test_v5_resync_without_a_config_leaves_the_sweep_premise_skipping(tmp_path, monkeypatch):
    """§Work 3: "with a `cfg`, the E-0 seed sidecar is written ... WITHOUT one,
    the worker comes forward but its sweep premise-skips"."""
    worker = _plant_stale(tmp_path, "nocfg-slot", GREEN_PAIR, monkeypatch)
    result = resync_worker(worker)

    assert result["seeds"] is None, (
        "E-0 §Work 3: 'WITHOUT one, the worker comes forward but its sweep premise-skips' — "
        "a config-less resync wrote a seed plan anyway"
    )
    assert not seeds_sidecar_path(worker).exists(), (
        "E-0 §Work 3: a config-less resync must leave no sidecar"
    )
    assert (worker / "tests/test_seed_sweep.py").is_file(), (
        "E-0 §Work 3: the worker still 'comes forward' — the scaffold is today's"
    )
    proc = _validate(worker)
    assert proc.returncode == 0 and "skipped" in proc.stdout, (
        "E-0 §Work 3: 'its sweep premise-skips' — expected a green validate with a reported "
        f"skip:\n{_tail(proc)[-4000:]}"
    )


def test_v5_game_id_defaults_to_the_slot_directory_name(tmp_path, monkeypatch):
    """Addendum 1 (ratified): "game_id defaults to the slot DIRECTORY name
    (S6's own rule; runbook note: resync in place or pass --game-id)"."""
    worker = _plant_stale(tmp_path, "slot-named-this", GREEN_PAIR, monkeypatch)
    resync_worker(worker, cfg=_cfg())
    assert _read_sidecar(worker)["game_id"] == "slot-named-this", (
        "E-0 Addendum 1: 'game_id defaults to the slot DIRECTORY name' — got "
        f"{_read_sidecar(worker)['game_id']!r} for a slot dir named 'slot-named-this'"
    )

    other = _plant_stale(tmp_path, "override-slot", GREEN_PAIR, monkeypatch)
    resync_worker(other, cfg=_cfg(), game_id="chosen-by-the-operator")
    payload = _read_sidecar(other)
    assert payload["game_id"] == "chosen-by-the-operator", (
        "E-0 Addendum 1: 'resync in place or pass --game-id' — the override was ignored"
    )
    assert payload["seeds"][1:] == _hand_derive(
        payload["batch_seed"], "chosen-by-the-operator", PAIR_AUTHORED_SEED, 5
    )[1:], "E-0 §Evidence: the seeds are derived FROM the game_id"


def test_v5_a_resynced_worker_reproduces_the_seed_reject_in_loop(tmp_path, monkeypatch):
    """§Verification gates, as corrected by Addendum 1: a revived worker, once
    resynced, shows "`make validate` goes RED ... with the real five seeds in
    the sidecar (the live defect reproduced in-loop for the first time)" —
    pinned on the defect CLASS, which is what the red fixture models.

    THE DEBT this contract pays: "the builder 'fixed' seeds it could not run,
    twice". After resync it can run them.
    """
    worker = _plant_stale(tmp_path, "revival-slot", RED_PAIR, monkeypatch)

    before = _validate(worker)
    assert before.returncode == 0, (
        "E-0 §Work 3: absent a resync the worker 'behave[s] byte-for-byte as today' — a "
        f"pre-E-0 scaffold cannot run S6's seeds at all:\n{_tail(before)[-4000:]}"
    )

    resync_worker(worker, cfg=_cfg())
    after = _validate(worker)
    tail = _tail(after)
    assert after.returncode != 0, (
        "E-0 §Verification gates: after resync `make validate` must go RED on the seed-reject "
        f"class 'with the real five seeds in the sidecar':\n{tail[-4000:]}"
    )
    for seed in _read_sidecar(worker)["seeds"][1:]:
        assert str(seed) in tail, (
            f"E-0 §Verification gates: the in-loop reproduction must name seed {seed}"
        )


# --------------------------------------------------------------------------- #
# V6 — instantiation + byte-identity
# --------------------------------------------------------------------------- #


def test_v6_a_fresh_pipeline_worker_gets_the_sidecar_automatically(tmp_path, monkeypatch):
    """§Blind V6: "fresh workers get the sidecar automatically"; §Work 1: "at
    worker instantiation the pipeline computes the slot's exact S6 seed list
    ... and writes it to a SIBLING file beside the worker".

    Driven through the real S2 stage runner, stopped at the payload (no agent
    session, no spend) — by then the worker and its sidecar must both exist.
    """
    cfg = _cfg()
    corpus = tmp_path / "corpus" / cfg["batch"]["id"]
    spec_dir = corpus / "fresh-born-slot"
    spec_dir.mkdir(parents=True)
    _write_spec(spec_dir, 4242)
    ideas = tmp_path / "ideas"
    ideas.mkdir()
    idea = ideas / "idea-001.json"
    idea.write_text("{}", encoding="utf-8")

    class _StopAtPayload(Exception):
        pass

    from gen import s2_implement

    def _stop(*args, **kwargs):
        raise _StopAtPayload("payload reached — the worker is already instantiated")

    monkeypatch.setattr(s2_implement, "build_payload", _stop)

    ctx = orch.SlotContext(
        cfg=cfg, batch_id=cfg["batch"]["id"], slug="fresh-born-slot", index=1,
        state="spec_ok", stage="s2_implement", attempt=1,
        batch_dir=tmp_path / "batches" / cfg["batch"]["id"], ideas_dir=ideas,
        idea_path=idea, corpus_dir=corpus, spec_dir=spec_dir,
        respec_count=0, verifier_rejects=0, green_failures=0,
    )
    runners = orch.default_runners()
    assert "s2_implement" in runners, (
        "E-0 §Work 1 puts the sidecar write 'at worker instantiation' in the pipeline; the S2 "
        "stage runner is not reachable, so the seam cannot be driven"
    )
    with pytest.raises(_StopAtPayload):
        runners["s2_implement"](ctx)

    worker = spec_dir / "worker"
    assert worker.is_dir(), "the S2 runner must have instantiated the worker"
    payload = _read_sidecar(worker)
    assert payload["seeds"] == s6_package.validation_seeds(cfg, "fresh-born-slot", 4242), (
        "E-0 §Blind V6: 'fresh workers get the sidecar automatically' — the sidecar the "
        f"pipeline wrote is not S6's list: {payload['seeds']}"
    )
    assert payload["authored_seed"] == 4242, (
        "E-0 §Work 1: 'authored seed from the spec's layout.seed'"
    )
    assert payload["game_id"] == "fresh-born-slot", (
        "E-0 Addendum 1: 'game_id defaults to the slot DIRECTORY name'"
    )


def test_v6_nothing_but_the_pipeline_and_resync_writes_a_sidecar(tmp_path):
    """§Blind V6: "byte-identity everywhere the sidecar is absent (no knob
    armed, no behavior drift for any existing path — today's-bytes pins)";
    §Work 3: "nothing auto-migrates"."""
    slot = _slot(tmp_path, "bare-slot")
    worker = slot / "worker"
    instantiate_worker(worker)
    assert not seeds_sidecar_path(worker).exists(), (
        "E-0 §Blind V6: `instantiate_worker` on its own is an existing path and must stay "
        "today's bytes — it wrote a sidecar"
    )

    _install(worker, GREEN_PAIR)
    (worker / "tests/test_scaffold.py").unlink()
    repair_worker(worker)
    assert not seeds_sidecar_path(worker).exists(), (
        "E-0 §Work 3: 'nothing auto-migrates' — repair_worker wrote a sidecar"
    )


def test_v6_two_instantiations_stay_byte_identical(tmp_path):
    """§Blind V6: "today's-bytes pins" — the B1 determinism guarantee is
    untouched by E-0."""
    a = instantiate_worker(_slot(tmp_path, "twin-a") / "worker")
    b = instantiate_worker(_slot(tmp_path, "twin-b") / "worker")
    assert a == b, (
        "E-0 §Blind V6: 'no behavior drift for any existing path' — template instantiation is "
        "no longer deterministic"
    )


def test_v6_the_sidecar_changes_neither_the_manifest_nor_the_scope(tmp_path):
    """§Blind V6: "byte-identity everywhere the sidecar is absent"; §Evidence
    EDIT-SCOPE: a sibling is "pipeline-owned and legal"."""
    worker = _worker_with(tmp_path, "manifest-slot", GREEN_PAIR, sidecar=False)
    before = build_manifest(worker)
    scope_before = verify_worker(worker)

    write_seeds_sidecar(worker, _cfg(), authored_seed=PAIR_AUTHORED_SEED)
    assert build_manifest(worker) == before, (
        "E-0 §Work 1: the sidecar is 'NEVER inside the worker tree', so it cannot appear in "
        "the worker's manifest"
    )
    assert verify_worker(worker) == scope_before == [], (
        "E-0 §Evidence EDIT-SCOPE: writing the sidecar must not change the edit-scope verdict"
    )


def test_v6_no_knob_is_armed_every_shipped_config_derives_a_plan(tmp_path):
    """§Blind V6: "no knob armed"; §House rule: "defaults = today's bytes".

    Every config on disk must already answer the sidecar's question with the
    keys it has today — a required new knob would fail here.
    """
    configs = sorted((REPO_ROOT / "config").glob("*.yaml"))
    assert configs, "no configs found to check"
    slot = _slot(tmp_path, "knob-slot")
    _write_spec(slot, PAIR_AUTHORED_SEED)
    worker = slot / "worker"
    instantiate_worker(worker)

    for path in configs:
        cfg = load_config(path)
        payload = worker_mod.seed_plan(worker, cfg)
        assert payload["seeds"] == s6_package.validation_seeds(
            cfg, "knob-slot", PAIR_AUTHORED_SEED
        ), (
            f"E-0 §Blind V6: 'no knob armed' — {path.name} needs something it does not carry "
            "today for the seed plan to come out right"
        )
        assert payload["count"] == cfg["package"]["seeds_validated"], (
            f"E-0 §Work 5: 'The count stays honest against package.seeds_validated through "
            f"the sidecar' — {path.name} asks for "
            f"{cfg['package']['seeds_validated']} and the plan carries {payload['count']}"
        )


# --------------------------------------------------------------------------- #
# §4 — the S6 bound as shared truth
# --------------------------------------------------------------------------- #


def test_work4_the_sweep_bound_is_s6s_own_constant(tmp_path):
    """§Work 4: "the sweep's 600 bound must reference S6's constant (import or a
    pinned mirror with a drift test) — two diverging bounds is how this class
    was born"."""
    assert s6_package.MAX_ACTIONS == S6_BOUND, (
        f"E-0 §Evidence: S6 drives 'under MAX_ACTIONS = 600'; the stage now says "
        f"{s6_package.MAX_ACTIONS}"
    )
    worker = _worker_with(tmp_path, "bound-truth-slot", GREEN_PAIR)
    harness = _import_harness(worker)
    S6_MAX_ACTIONS = getattr(harness, "S6_MAX_ACTIONS", None)
    assert isinstance(S6_MAX_ACTIONS, int), (
        "E-0 §Work 4: 'the sweep's 600 bound must reference S6's constant (import or a pinned "
        "mirror with a drift test)' — the scaffold harness exposes no such mirror to drift-test"
    )

    assert S6_MAX_ACTIONS == s6_package.MAX_ACTIONS, (
        "E-0 §Work 4: 'the sweep's 600 bound must reference S6's constant (import or a pinned "
        f"mirror with a drift test)' — the scaffold mirrors {S6_MAX_ACTIONS} while S6 drives "
        f"at {s6_package.MAX_ACTIONS}. Two diverging bounds is how this class was born."
    )
    assert _read_sidecar(worker)["max_actions"] == s6_package.MAX_ACTIONS, (
        "E-0 §Work 4: the sidecar's recorded bound must be S6's own, so a sidecar from an "
        "older generation cannot silently change the verdict"
    )


def test_work4_a_sidecar_carrying_a_different_bound_is_loud(tmp_path):
    """§Work 4: "(import or a pinned mirror with a drift test) — two diverging
    bounds is how this class was born".

    The sweep reads its bound from the sidecar, so the sidecar is the second
    place the two could diverge. A sidecar written by a different generation of
    the pipeline must be refused out loud, not quietly obeyed: obeying 1200
    here is precisely the old, worthless sweep.
    """
    worker = _worker_with(tmp_path, "bound-drift-slot", GREEN_PAIR)
    payload = _read_sidecar(worker)
    payload["max_actions"] = OLD_HARNESS_BOUND
    seeds_sidecar_path(worker).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    proc = _validate(worker)
    tail = _tail(proc)
    assert proc.returncode != 0, (
        "E-0 §Work 4: 'two diverging bounds is how this class was born' — the scaffold "
        f"accepted a sidecar claiming a {OLD_HARNESS_BOUND}-action bound without a word:\n"
        f"{tail[-4000:]}"
    )
    assert str(S6_BOUND) in tail and str(OLD_HARNESS_BOUND) in tail, (
        "E-0 §Work 4: the refusal must name BOTH bounds, or the operator cannot see which "
        f"generation disagreed:\n{tail[-4000:]}"
    )


# --------------------------------------------------------------------------- #
# §5 — the green loop; §6 — the docs
# --------------------------------------------------------------------------- #


def test_work5_the_sweep_rides_the_green_loops_own_validate(tmp_path):
    """§Work 5: "the sweep rides `pytest tests/` inside `make validate`, so the
    building agent runs it on every attempt (that IS the in-loop property)".

    Driven through `s2_implement`'s own validate leg — "the green loop's own
    validate leg, the one whose exit code every attempt record carries".
    """
    red = _worker_with(tmp_path, "inloop-red", RED_PAIR)
    code, tail = _run_validate(red)
    assert code != 0, (
        "E-0 §Work 5: 'the sweep rides `pytest tests/` inside `make validate`, so the building "
        f"agent runs it on every attempt' — the green loop's validate leg was green on a "
        f"seed-reject:\n{tail[-4000:]}"
    )

    green = _worker_with(tmp_path, "inloop-green", GREEN_PAIR)
    code, tail = _run_validate(green)
    assert code == 0, (
        "E-0 §Work 5: the same leg must stay green on the reference pair:\n" + tail[-4000:]
    )


def test_work5_the_prompt_side_count_still_agrees_with_the_sidecar(tmp_path):
    """§Work 5: "The count stays honest against package.seeds_validated through
    the sidecar"; §Evidence: "Prompt-side count: LAYOUT_SEED_CONTRACT 'at 5
    seeds' (s2_implement.py:1223), pinned by test_b6_payload.py:618-630"."""
    cfg = _cfg()
    wanted = cfg["package"]["seeds_validated"]
    assert f"at {wanted} seeds" in LAYOUT_SEED_CONTRACT, (
        "E-0 §Evidence: the prompt's 'at 5 seeds' and `package.seeds_validated` are the same "
        f"number; the prompt no longer says 'at {wanted} seeds'"
    )
    worker = _worker_with(tmp_path, "count-slot", GREEN_PAIR)
    payload = _read_sidecar(worker)
    assert payload["count"] == len(payload["seeds"]) == wanted, (
        "E-0 §Work 5: 'The count stays honest against package.seeds_validated through the "
        f"sidecar' — config asks {wanted}, sidecar carries {payload['count']}"
    )


def test_work6_the_two_doc_sentences_gained_the_seed_sweep():
    """§Work 6: "Docs: RUNBOOK's validate description + GUIDE's pipeline stage
    3 sentence gain the seed sweep (one line each)"."""
    runbook = (REPO_ROOT / "docs/RUNBOOK.md").read_text(encoding="utf-8").lower()
    assert "seed sweep" in runbook, (
        "E-0 §Work 6: \"RUNBOOK's validate description ... gain[s] the seed sweep\" — the "
        "RUNBOOK never mentions it"
    )
    assert "seeds.json" in runbook, (
        "E-0 §Work 1 + §6: the RUNBOOK describes the worker tree, so the sidecar the sweep "
        "reads must be in it"
    )

    guide = (REPO_ROOT / "docs/GUIDE.md").read_text(encoding="utf-8").lower()
    assert "seed" in guide, (
        "E-0 §Work 6: \"GUIDE's pipeline stage 3 sentence gain[s] the seed sweep\" — the GUIDE "
        "never mentions seeds at all"
    )
    # The sentence must sit in the Build stage's own paragraph, not anywhere.
    build = guide.split("**build**", 1)
    assert len(build) == 2, (
        "E-0 §Work 6 names 'GUIDE's pipeline stage 3 sentence'; the GUIDE no longer has a "
        "Build stage to carry it"
    )
    stage_three = build[1].split("**blind audit**", 1)[0]
    assert "seed" in stage_three, (
        "E-0 §Work 6: \"GUIDE's pipeline stage 3 sentence gain[s] the seed sweep (one line "
        "each)\" — the Build stage paragraph says nothing about seeds:\n" + stage_three[:800]
    )


def test_work6_the_scaffold_docs_tell_the_building_agent_about_the_sweep(tmp_path):
    """Addendum 1 (ratified): "AGENTS/README scaffold docs in the blast radius".

    The sweep is only in-loop if the agent inside the worker knows what went
    red and that editing the test is not the fix.
    """
    worker = _worker_with(tmp_path, "scaffold-docs-slot", GREEN_PAIR, sidecar=False)
    for name in ("AGENTS.md", "README.md"):
        text = (worker / name).read_text(encoding="utf-8").lower()
        assert "seed sweep" in text, (
            f"E-0 Addendum 1: 'AGENTS/README scaffold docs in the blast radius' — the "
            f"worker's {name} never names the seed sweep, so the building agent meets a red "
            "test it was never told about"
        )
    agents = (worker / "AGENTS.md").read_text(encoding="utf-8").lower()
    assert "layout_seed" in agents and "build_layout" in agents, (
        "E-0 §Work 2 / the scaffold's own guidance: a red seed means `build_layout(seed)` or "
        "`Solver(layout_seed=s)` is wrong; AGENTS.md must say which knobs to look at"
    )
