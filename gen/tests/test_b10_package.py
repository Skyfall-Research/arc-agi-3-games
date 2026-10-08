"""B10 acceptance: the S6 packager + TSV emitter.

Run: .venv/bin/python -m pytest gen/tests/test_b10_package.py -q

Written FROM THE B10 CONTRACT and from canon, never from the implementation:
`gen/s6_package.py` was built in parallel with this file by another agent and
none of its source was read. Every expectation below is either a name/shape
the contract froze or a canon rule cited at its source:

  spec-v0.3 §7 — layout-from-seed is REQUIRED from birth; 6-10 levels.
  decisions.md D13 — the layout.seed mechanism the fixtures implement.
  architecture.md §2 — the corpus tree's `package/` node and the provenance
      chain (`spec_hash = sha(spec.yaml)`, `game_hash = sha(game.py +
      solver.py)`).
  architecture.md §3 "S6 — packager" + the layout-seed contract block — the
      pure `build_layout(seed)` called at `on_set_level`, layouts
      structurally distinct under seed, the solver must solve ANY seed,
      `package.seeds_validated` seeds validated at package time, and the
      failure routing "a failing validation seed → S2".
  trajectory-contract.md §1 + §6 + §7 — the 14-column TSV, the SARS +
      terminal-row convention, and the DEFAULTS-IF-UNANSWERED the package
      leans on (Q1/Q3/Q4/Q5/Q6/Q7/Q9).
  GEN/tools/capture_frames.py `_tsv_row`/`_write_tsv` — READ-ONLY reference
      for the dialect (adapted into gen/s6_package.py, never imported).
  config/b001-pilot.yaml — `package.seeds_validated: 5`,
      `package.split {train .7, eval .3}`, `batch.seed: 1`.

FIXTURES — authored for this file and proven raw against the engine by group 1
below (they import nothing from `gen.s6_package`):

  fixtures/s6_seeded/        THE §7 reference: 6 levels, pure module-level
                             `build_layout(seed)`, `Game(layout_seed=)` /
                             `Solver(layout_seed=)`, a BFS solver that derives
                             its line from the layout at ANY seed, per-level
                             budget wired exhaustion->lose() with the win check
                             FIRST, RESET never charging.
  fixtures/s6_seeded_broken/ the same game byte-for-byte except `GAME_ID`; its
                             solver replays the DEFAULT seed's line whatever
                             seed it is handed — the seed-reject path.

Both are real S4 inputs: `run_s4` is executed in-test on a tmp COPY of each
(seed 7, verdict `fit` for both), so `<worker>.s4/` — which `run_s6` has no
parameter for and must therefore find at the stage-sibling path — lands beside
the copy in `tmp_path` and never in the repo's `out/`.

PLAY-MIRROR RULE: every mirror write in this file goes to a `tmp_path` play
root. An autouse fixture snapshots `s6_package.PLAY_ROOT` (the repo's
`out/play`) around EVERY test and fails if it changed.

CONTRACT AMBIGUITIES this file had to take a position on (reported to the
lead, never invented quietly):
  A. The contract says the ten groups import "the frozen names from
     gen.s6_package", but also that group 1 "runs with no gen.s6_package
     import". A module-level `from gen.s6_package import <name>` makes a
     single missing name break COLLECTION, which would take group 1 — the
     independent fixture proof — down with it during a parallel build. So the
     module is imported as `s6` and the frozen names are reached as
     attributes; `test_every_frozen_name_exists` is the explicit check that
     each one is present. No test is skipped or guarded.
  B. `rederive_layouts` returns "per-seed serialized layouts"; the key type is
     not frozen. `_seed_keyed` accepts int or str keys and normalises.
  C. `validation_seeds`' extra seeds are frozen as
     `sha256(f"{batch.seed}:{game_id}:s6:{k}")` but `k`'s range is not, so
     group 3 asserts each extra seed is a member of the set that formula
     generates for k in 0..11 rather than pinning k's start.
  D. `validation_seeds(cfg, game_id, default_seed=None)` has no frozen
     meaning (semantics 3 collapses the LEGACY seed list to `[None]` inside
     `run_s6`), so it is not tested here.
  E. The `question` field of a `section6_flags` entry has no frozen format.
     `_question_id` reads the first `Q<n>`/`<n>` it finds; `SECTION6_DEFAULTS`
     is only checked structurally, because its element shape is not frozen.
  F. `manifest.seeds.requested` is not typed: a count and a requested-seed
     list both read naturally, so group 7 accepts either and pins
     `validated`/`authored_seed` instead.
  G. `manifest.game_id` is asserted to be the S4/engine game id, because the
     manifest carries `slug` separately and `validation_seeds` derives from a
     `game_id` exactly as `s4_baselines.derive_seed` does. The other reading
     (`<slug>-<hash8>`, the play-mirror shape) is not asserted.
  H. `write_play_mirror`'s "slug" is never defined. Group 8 never assumes
     `worker.name`: it globs the play root for the documented
     `*/*/metadata.json` and reads the slug back from the directory it finds.
     "title (the slug, title-cased)" is asserted case-insensitively and
     ignoring separators, because `"s6_seeded".title()` and
     `"s6 seeded".title()` both read as "the slug, title-cased".
  I. `run_s6(seeds=...)` is typed `int | None`, so it is read as a COUNT
     override of `package.seeds_validated`. Only one test depends on it.
  J. The CLI flag names are NOT frozen. `--worker` / `--out` / `--config`
     follow `s4_baselines.main` and `s5_battery.main` verbatim; `--spec`,
     `--seeds`, `--play-root` and `--legacy-no-layout` are the frozen
     `run_s6` keywords spelled the argparse way. `_cli` fails loudly (never
     silently) if argparse reports an unrecognized argument, so a different
     spelling surfaces as a named failure rather than as a bogus exit-2.
  K. `main()` may return its exit code or raise `SystemExit` with it; `_cli`
     accepts either (the b9 precedent).
  L. THE ONE CONTRACT-INTERNAL CONFLICT — TSV reward. Contract group 6 says
     "reward rows: exactly one 1 per level, rest 0, sum == level count", but
     the parity-proven dialect the same contract orders us to match
     (`capture_frames._tsv_row`, and trajectory-contract §7's "reward count
     incl. the terminal-row echo") writes reward 1 on the TERMINAL row too,
     making the total level_count + 1. This file follows the PROVEN DIALECT:
     the ACTION rows carry exactly one 1 per level and sum to the level count,
     and the terminal row echoes the win. Flagged for the lead.
  M. `manifest.paths` / the report's "rederivation evidence" have no frozen
     key names; they are checked by content (`level-set.tsv`,
     `manifest.json`, `PLAY_GAMES_DIR=`) rather than by key.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from arcengine import ActionInput, GameAction

from gen import s6_package as s6
from gen.config import REPO_ROOT, load_config
from gen.frames import TERMINAL_STATES, _fresh_game, _perform, _reset
from gen.s3_static import load_worker_classes
from gen.s4_baselines import METADATA_NAME, run_s4
from gen.s4_baselines import OUT_SUFFIX as S4_SUFFIX

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
SEEDED = FIXTURES / "s6_seeded"
BROKEN = FIXTURES / "s6_seeded_broken"
TOY = TESTS / "toy_worker"
PILOT_CONFIG = "config/b001-pilot.yaml"

SOURCES = {"seeded": SEEDED, "broken": BROKEN, "toy": TOY}

#: the S4 seed every in-test stage-4 run uses (all three workers: verdict `fit`).
S4_SEED = 7

# --- the fixtures' AUTHORED numbers (fixtures/s6_seeded/game.py header) ----
AUTHORED_SEED = 13
LEVEL_COUNT = 6
SEEDED_GAME_ID = "s6-seeded-gate"
BROKEN_GAME_ID = "s6-seeded-gate-broken"
#: the solver's per-level line AT THE AUTHORED SEED, and its total.
SEEDED_SOLVER = (12, 11, 8, 7, 7, 10)
SEEDED_ACTIONS = 55
#: cap_i = 32 * solver_i — the enforced per-level budget at the authored seed.
SEEDED_CAPS = (384, 352, 256, 224, 224, 320)

#: five fixed seeds (the authored one first) for the raw fixture proofs.
PROBE_SEEDS = (AUTHORED_SEED, 1, 2, 3, 99)
#: three seeds that are NOT the authored one — "solver wins on 3 seeds".
SOLVE_SEEDS = (1, 2, 3)

# --- the frozen S6 surface (B10 contract §"FROZEN interfaces") -------------
FROZEN_CONSTANTS = (
    "SCHEMA_VERSION",
    "VERDICT_PACKAGED",
    "VERDICT_SEED_REJECT",
    "TSV_COLUMNS",
    "TSV_VERBS",
    "SECTION6_DEFAULTS",
    "OUT_SUFFIX",
    "PLAY_ROOT",
)
FROZEN_CALLABLES = (
    "load_layout_contract",
    "rederive_layouts",
    "validation_seeds",
    "validate_seed",
    "emit_tsv",
    "game_hash",
    "spec_hash",
    "build_manifest",
    "write_play_mirror",
    "run_s6",
    "main",
)
EXPECTED_TSV_COLUMNS = (
    "step",
    "observation",
    "info",
    "level",
    "action_valid",
    "duration",
    "action",
    "reward",
    "terminated",
    "truncated",
    "explore_exploit",
    "world_model_path",
    "goal",
    "exploration_output",
)
# LEAD-CORRECTED PIN (C-5, freeze addendum 7): slot 6 spells CLICK. The
# original MOUSE pin was calibrated against our own capture tool's output;
# the measured ground truth (24/24 official TSVs at duckWM 31f3a8b) is
# CLICK, and the consumer gates on that literal.
EXPECTED_TSV_VERBS = {1: "UP", 2: "DOWN", 3: "LEFT", 4: "RIGHT", 5: "INTERACT", 6: "CLICK"}

# --- the frozen package layout (B10 contract §"Semantics" 5 + 7) -----------
MANIFEST_KEYS = {
    "schema_version",
    "slug",
    "game_id",
    "verdict",
    "seeds",
    "split",
    "spec_hash",
    "game_hash",
    "layout_contract",
    "section6_flags",
    "versions",
    "paths",
}
SEED_KEYS = {"requested", "validated", "authored_seed"}
SPLIT_NOTE = "applied at slug level; officials never in train"
SEED_RECORD_KEYS = {"seed", "win", "levels_completed", "actions_total", "error"}
#: trajectory-contract §6 questions the packager actually leans on.
SECTION6_QUESTIONS = {1, 3, 4, 5, 6, 7, 9}
#: the §6 questions that do NOT bind the packager (contract: "not flagged").
SECTION6_UNBOUND = {2, 8, 10}

MANIFEST_REL = Path("package") / "manifest.json"
TSV_REL = Path("package") / "tsv" / "level-set.tsv"
REPORT_NAME = "s6-report.json"

#: the play server's documented discovery glob (server.py:103, READ-ONLY).
PLAY_GLOB = "*/*/metadata.json"
PLAY_METADATA_KEYS = {"game_id", "title", "tags", "baseline_actions", "default_fps"}

_CFG = load_config(PILOT_CONFIG)

# --- test-only game.py tails (group 2) -------------------------------------

#: a build_layout that IGNORES its seed — a spec §7 violation, not a reject.
SEED_IGNORING_TAIL = '''

# --- B10 test override: build_layout that IGNORES its seed -----------------
_AUTHORED_LAYOUT = build_layout(DEFAULT_LAYOUT_SEED)


def build_layout(seed: int) -> list:  # noqa: F811
    """Returns the authored layout whatever the seed (spec §7 violation)."""
    return [dict(level) for level in _AUTHORED_LAYOUT]
'''

#: build_layout present but NOT callable — the fail-loud case.
NON_CALLABLE_TAIL = '''

# --- B10 test override: build_layout present but NOT callable --------------
build_layout = 7
'''


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Staged:
    """A tmp copy of a fixture worker with a REAL `<worker>.s4/` beside it."""

    name: str
    root: Path
    worker: Path
    s4_dir: Path
    metadata: dict


def _game_module(worker_dir: Path):
    """The worker's game module, loaded by the repo's own worker loader."""
    game_cls, _solver_cls = load_worker_classes(Path(worker_dir))
    return sys.modules[game_cls.__module__]


def _layout_bytes(module, seed: int) -> str:
    """The contract's comparison surface: `json.dumps(..., sort_keys=True)`."""
    return json.dumps(module.build_layout(seed), sort_keys=True)


def _geometry(module, seed: int) -> list:
    """Just the structure — what "structurally distinct under seed" means."""
    return [
        (level["gate_x"], level["gap_y"], level["player"][1], level["goal"][1])
        for level in module.build_layout(seed)
    ]


def _drive(worker_dir: Path, layout_seed: int | None, *, max_actions: int = 600):
    """Drive `Game(layout_seed=)` with `Solver(layout_seed=)`. Raw, no S6."""
    game_cls, solver_cls = load_worker_classes(Path(worker_dir))
    game = game_cls(layout_seed=layout_seed)
    solver = solver_cls(layout_seed=layout_seed)
    solver.reset()
    frame = _reset(game)
    actions = 0
    for _ in range(max_actions):
        if frame.state in TERMINAL_STATES:
            break
        action = solver.next_action(frame)
        if action is None:
            break
        frame = _perform(game, action)
        actions += 1
    return frame, actions


def _write_worker(dest: Path, source: Path, *, tail: str = "") -> Path:
    """Copy a fixture worker to `dest`, optionally appending to its game.py."""
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__"))
    if tail:
        game = dest / "game.py"
        game.write_text(game.read_text(encoding="utf-8") + tail, encoding="utf-8")
    return dest


def _clone(staged: Staged, dest_root: Path) -> tuple[Path, Path]:
    """A private copy of a staged worker AND its `<worker>.s4/` sibling."""
    dest_root.mkdir(parents=True, exist_ok=True)
    worker = dest_root / staged.worker.name
    shutil.copytree(staged.worker, worker, ignore=shutil.ignore_patterns("__pycache__"))
    s4_dir = dest_root / staged.s4_dir.name
    shutil.copytree(staged.s4_dir, s4_dir)
    return worker, s4_dir


def _read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    """Header + raw cell lists. `\\n` endings, tab separated, no trailing blank."""
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n"), "the TSV must end with a newline"
    assert "\r" not in text, "the dialect writes \\n endings, never \\r\\n"
    lines = text.split("\n")[:-1]
    return lines[0].split("\t"), [line.split("\t") for line in lines[1:]]


def _rows(path: Path) -> list[dict]:
    header, cells = _read_tsv(path)
    return [dict(zip(header, row, strict=True)) for row in cells]


def _arc_frame(row: dict) -> tuple[dict, dict]:
    """`info` -> the arc_frame dict -> its nested `frame_data` dict."""
    inner = json.loads(json.loads(row["info"])["arc_frame"])
    return inner, json.loads(inner["frame_data"])


def _seed_keyed(mapping) -> dict:
    """`rederive_layouts`' result, with seed keys normalised to ints."""
    assert isinstance(mapping, dict), f"expected a dict, got {type(mapping).__name__}"
    out = {}
    for key, value in mapping.items():
        out[int(key)] = value
    return out


def _layout_value(value) -> str:
    """One `rederive_layouts` entry, normalised to the contract's compare bytes.

    "per-seed SERIALIZED layouts" leaves open whether the entry is already the
    `json.dumps(..., sort_keys=True)` string or the structure itself
    (ambiguity B); both normalise to the same bytes here.
    """
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


def _question_id(flag) -> int:
    raw = flag.get("question") if isinstance(flag, dict) else flag
    match = re.search(r"Q?(\d+)", str(raw))
    assert match is not None, f"section6 flag {flag!r} names no §6 question number"
    return int(match.group(1))


def _flags_by_question(manifest: dict) -> dict:
    flags = manifest["section6_flags"]
    assert isinstance(flags, list), f"section6_flags must be a list, got {type(flags).__name__}"
    by_id = {}
    for flag in flags:
        by_id[_question_id(flag)] = flag
    assert len(by_id) == len(flags), "two section6 flags name the same §6 question"
    return by_id


def _cli(argv, capsys) -> tuple[int, str, str]:
    """`main(argv)`, tolerating a returned code or a raised SystemExit."""
    try:
        code = s6.main(list(argv))
    except SystemExit as exc:  # argparse, or a main() that exits
        code = exc.code
    captured = capsys.readouterr()
    assert "unrecognized arguments" not in captured.err, (
        "the CLI rejected a flag name inferred from the frozen run_s6 keywords "
        f"(ambiguity J): {captured.err.strip()}"
    )
    return (0 if code is None else int(code)), captured.out, captured.err


def _mirror_dirs(play_root: Path) -> list[Path]:
    """Every mirror the play server's own discovery glob would find."""
    return sorted(path.parent for path in Path(play_root).glob(PLAY_GLOB))


def _duckwm_paths(cfg) -> tuple[Path, Path]:
    """(the duckWM venv python, the play server) — "resolved from the config's
    `duckwm_docs` parent" (B10 contract §Semantics 7)."""
    docs = Path(cfg["duckwm_docs"])
    return (
        docs.parent.parent / ".venv" / "bin" / "python",
        docs.parent / "arc-agi-3-games" / "tools" / "play" / "server.py",
    )


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _repo_play_root_untouched():
    """B10 rule: play-mirror writes in tests ALWAYS use a tmp play root."""
    root = Path(getattr(s6, "PLAY_ROOT", REPO_ROOT / "out" / "play"))

    def snapshot():
        if not root.exists():
            return None
        return sorted(str(path) for path in root.rglob("*"))

    before = snapshot()
    yield
    assert snapshot() == before, f"a test wrote into the repo play root {root}"


@pytest.fixture(scope="session")
def cfg() -> dict:
    return _CFG


@pytest.fixture(scope="session")
def staged(tmp_path_factory):
    """Cached tmp worker copy + real stage-4 output, per fixture name."""
    cache: dict[str, Staged] = {}

    def _get(name: str) -> Staged:
        if name not in cache:
            root = tmp_path_factory.mktemp("b10stage")
            worker = _write_worker(root / SOURCES[name].name, SOURCES[name])
            report = run_s4(worker, _CFG, seed=S4_SEED)
            assert report["verdict"] == "fit", f"{name}: S4 verdict {report['verdict']}"
            s4_dir = worker.parent / (worker.name + S4_SUFFIX)
            metadata = json.loads((s4_dir / METADATA_NAME).read_text(encoding="utf-8"))
            cache[name] = Staged(
                name=name, root=root, worker=worker, s4_dir=s4_dir, metadata=metadata
            )
        return cache[name]

    return _get


@pytest.fixture(scope="session")
def packaged(staged, tmp_path_factory):
    """ONE real `run_s6` on the §7 reference: (report, out_dir, play_root)."""
    entry = staged("seeded")
    play_root = tmp_path_factory.mktemp("b10play")
    report = s6.run_s6(entry.worker, _CFG, play_root=play_root)
    out_dir = entry.worker.parent / (entry.worker.name + s6.OUT_SUFFIX)
    return report, out_dir, play_root


@pytest.fixture(scope="session")
def manifest(packaged) -> dict:
    _report, out_dir, _play_root = packaged
    return json.loads((out_dir / MANIFEST_REL).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def tsv_path(packaged) -> Path:
    _report, out_dir, _play_root = packaged
    return out_dir / TSV_REL


@pytest.fixture(scope="session")
def rejected(staged, tmp_path_factory):
    """ONE real `run_s6` on the seed-reject twin: (report, out_dir, play_root)."""
    entry = staged("broken")
    play_root = tmp_path_factory.mktemp("b10playreject")
    report = s6.run_s6(entry.worker, _CFG, play_root=play_root)
    out_dir = entry.worker.parent / (entry.worker.name + s6.OUT_SUFFIX)
    return report, out_dir, play_root


@pytest.fixture(scope="session")
def legacy(staged, tmp_path_factory):
    """ONE real `run_s6` on the layout-less toy: (report, out_dir, play_root)."""
    entry = staged("toy")
    play_root = tmp_path_factory.mktemp("b10playlegacy")
    report = s6.run_s6(entry.worker, _CFG, legacy_no_layout=True, play_root=play_root)
    out_dir = entry.worker.parent / (entry.worker.name + s6.OUT_SUFFIX)
    return report, out_dir, play_root


# --------------------------------------------------------------------------- #
# group 1 — the fixtures, proven RAW against the engine (no gen.s6_package)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("worker", [SEEDED, BROKEN], ids=["seeded", "broken"])
def test_fixture_is_worker_shaped(worker):
    assert (worker / "game.py").is_file()
    assert (worker / "solver.py").is_file()
    game_cls, solver_cls = load_worker_classes(worker)
    assert solver_cls is not None
    game = _fresh_game(game_cls)
    # `_levels` is the engine's own list; gen/s3_static.py counts levels the
    # same way (there is no public accessor on ARCBaseGame).
    assert len(game._levels) == LEVEL_COUNT, "spec §7: 6-10 levels; the fixture sits on the floor"
    assert game.game_id == (SEEDED_GAME_ID if worker is SEEDED else BROKEN_GAME_ID)


def test_build_layout_is_importable_without_instantiating_the_game():
    """The §7 contract: a module-level pure function, callable on its own."""
    module = _game_module(SEEDED)
    assert callable(module.build_layout)
    layout = module.build_layout(AUTHORED_SEED)
    assert isinstance(layout, list) and len(layout) == LEVEL_COUNT


@pytest.mark.parametrize("seed", PROBE_SEEDS)
def test_build_layout_is_pure(seed):
    """Same seed -> equal bytes, three calls (no `hash()` salt, no rng state)."""
    module = _game_module(SEEDED)
    calls = [_layout_bytes(module, seed) for _ in range(3)]
    assert calls[0] == calls[1] == calls[2]


def test_build_layout_is_pairwise_distinct_across_five_seeds():
    module = _game_module(SEEDED)
    serialized = {seed: _layout_bytes(module, seed) for seed in PROBE_SEEDS}
    assert len(set(serialized.values())) == len(PROBE_SEEDS), serialized


def test_build_layout_varies_structurally_not_just_in_bytes():
    """Wall/goal GEOMETRY moves under seed — the §7 requirement, not a stamp."""
    module = _game_module(SEEDED)
    geometries = {seed: _geometry(module, seed) for seed in PROBE_SEEDS}
    assert len({tuple(geom) for geom in geometries.values()}) == len(PROBE_SEEDS)
    for seed, geom in geometries.items():
        assert len(geom) == LEVEL_COUNT, seed
    baseline = geometries[AUTHORED_SEED]
    for seed in PROBE_SEEDS[1:]:
        differing = [i for i, pair in enumerate(zip(baseline, geometries[seed])) if pair[0] != pair[1]]
        assert differing, f"seed {seed} reproduces the authored geometry level for level"


def test_layouts_are_json_able_structures():
    """The contract's comparison surface must round-trip through JSON."""
    module = _game_module(SEEDED)
    layout = module.build_layout(AUTHORED_SEED)
    assert json.loads(json.dumps(layout, sort_keys=True)) == layout
    for level in layout:
        assert isinstance(level, dict)
        for key, value in level.items():
            assert isinstance(key, str)
            assert isinstance(value, (int, str, list)), (key, value)


def test_none_means_the_authored_default_seed():
    """`Game(layout_seed=None)` == `Game(layout_seed=DEFAULT_LAYOUT_SEED)`."""
    module = _game_module(SEEDED)
    assert module.DEFAULT_LAYOUT_SEED == AUTHORED_SEED
    game_cls, solver_cls = load_worker_classes(SEEDED)
    assert _fresh_game(game_cls).layout_seed == AUTHORED_SEED
    assert game_cls(layout_seed=None).layout_seed == AUTHORED_SEED
    assert game_cls(layout_seed=AUTHORED_SEED).layout_seed == AUTHORED_SEED
    assert solver_cls().layout_seed == AUTHORED_SEED
    assert solver_cls(layout_seed=None).layout_seed == AUTHORED_SEED


@pytest.mark.parametrize("seed", (AUTHORED_SEED, *SOLVE_SEEDS))
def test_the_solver_wins_at_any_seed(seed):
    """architecture §3 S6: "the solver must solve ANY seed"."""
    frame, actions = _drive(SEEDED, seed)
    assert frame.state.name == "WIN", (seed, frame.state.name, actions)
    assert int(frame.levels_completed) == LEVEL_COUNT
    assert actions > 0


def test_the_solver_line_at_the_authored_seed_is_the_authored_line():
    frame, actions = _drive(SEEDED, AUTHORED_SEED)
    assert frame.state.name == "WIN"
    assert actions == SEEDED_ACTIONS == sum(SEEDED_SOLVER)


def test_the_solver_derives_a_different_line_per_seed():
    """A hardcoded line could not do this — the lines differ with the layout."""
    game_cls, solver_cls = load_worker_classes(SEEDED)
    assert game_cls is not None
    plans = {seed: [list(plan) for plan in solver_cls(layout_seed=seed).plans] for seed in PROBE_SEEDS}
    assert len({json.dumps(plan) for plan in plans.values()}) == len(PROBE_SEEDS)


def test_reset_never_charges_the_budget():
    """The fixtures/s4_workers lesson: a cap counts GAME actions (D8)."""
    game_cls, _solver_cls = load_worker_classes(SEEDED)
    game = _fresh_game(game_cls)
    for _ in range(5):
        _reset(game)
    assert game._budget_used == 0
    frame = _perform(game, ActionInput(id=GameAction.ACTION3))
    assert game._budget_used == 1
    assert frame.state.name == "NOT_FINISHED"


def test_budget_exhaustion_loses_at_exactly_the_authored_cap():
    """ACTION3 (left) from the start cell is always a CHARGED wall refusal."""
    module = _game_module(SEEDED)
    cap = module.build_layout(AUTHORED_SEED)[0]["cap"]
    assert cap == SEEDED_CAPS[0]
    game_cls, _solver_cls = load_worker_classes(SEEDED)
    game = _fresh_game(game_cls)
    _reset(game)
    left = ActionInput(id=GameAction.ACTION3)
    for index in range(1, cap):
        frame = _perform(game, left)
        assert frame.state.name == "NOT_FINISHED", f"died early at action {index}"
    frame = _perform(game, left)
    assert frame.state.name == "GAME_OVER"
    assert int(frame.levels_completed) == 0


def test_the_winning_move_is_free_at_the_cap_boundary():
    """Win check FIRST: the action that empties the meter AND lands on the
    goal transitions the level; it never calls lose()."""
    module = _game_module(SEEDED)
    spec = module.build_layout(AUTHORED_SEED)[0]
    game_cls, solver_cls = load_worker_classes(SEEDED)
    plan = solver_cls(layout_seed=AUTHORED_SEED).plans[0]
    game = _fresh_game(game_cls)
    _reset(game)
    left = ActionInput(id=GameAction.ACTION3)
    for _ in range(spec["cap"] - len(plan)):
        frame = _perform(game, left)  # refused by wall_left; player never moves
        assert frame.state.name == "NOT_FINISHED"
    for name in plan:
        frame = _perform(game, ActionInput(id=GameAction[name]))
    assert game._budget_used == 0, "the transition resets the per-level budget"
    assert frame.state.name == "NOT_FINISHED"
    assert int(frame.levels_completed) == 1


def test_the_broken_twin_wins_at_the_default_seed_only():
    """The seed-reject path, proven raw before any S6 code sees it."""
    frame, actions = _drive(BROKEN, AUTHORED_SEED)
    assert frame.state.name == "WIN"
    assert actions == SEEDED_ACTIONS
    for seed in SOLVE_SEEDS:
        frame, _actions = _drive(BROKEN, seed)
        assert frame.state.name != "WIN", f"seed {seed} unexpectedly solved"
        assert int(frame.levels_completed) < LEVEL_COUNT


def test_the_broken_twins_game_half_is_seed_honouring():
    """The defect is solver-only: both fixtures draw the SAME geometry, so
    re-derivation must PASS on the twin (a §7 violation would be louder)."""
    good, bad = _game_module(SEEDED), _game_module(BROKEN)
    for seed in PROBE_SEEDS:
        assert _layout_bytes(good, seed) == _layout_bytes(bad, seed)
    assert len({_layout_bytes(bad, seed) for seed in PROBE_SEEDS}) == len(PROBE_SEEDS)


# --------------------------------------------------------------------------- #
# frozen surface (additive — the b9 precedent)
# --------------------------------------------------------------------------- #


def test_every_frozen_name_exists():
    missing = [
        name
        for name in (*FROZEN_CONSTANTS, *FROZEN_CALLABLES)
        if not hasattr(s6, name)
    ]
    assert not missing, f"gen/s6_package.py is missing frozen name(s): {missing}"
    for name in FROZEN_CALLABLES:
        assert callable(getattr(s6, name)), f"{name} is not callable"


def test_module_constants_are_the_frozen_values():
    assert s6.SCHEMA_VERSION == "b10.1"
    assert (s6.VERDICT_PACKAGED, s6.VERDICT_SEED_REJECT) == ("packaged", "seed-reject")
    assert s6.OUT_SUFFIX == ".s6"


def test_tsv_columns_are_the_parity_proven_fourteen_in_order():
    assert tuple(s6.TSV_COLUMNS) == EXPECTED_TSV_COLUMNS
    assert len(s6.TSV_COLUMNS) == 14


def test_tsv_verbs_are_the_frozen_six():
    """The contract's table stops at MOUSE — ACTION7/UNDO is not in it."""
    assert dict(s6.TSV_VERBS) == EXPECTED_TSV_VERBS
    assert 7 not in dict(s6.TSV_VERBS)


def test_play_root_is_the_repo_out_play_directory():
    assert Path(s6.PLAY_ROOT) == REPO_ROOT / "out" / "play"


def test_section6_defaults_is_a_seven_entry_table():
    defaults = s6.SECTION6_DEFAULTS
    assert not isinstance(defaults, str)
    assert len(defaults) == len(SECTION6_QUESTIONS)


# --------------------------------------------------------------------------- #
# group 2 — load_layout_contract / rederive_layouts
# --------------------------------------------------------------------------- #


def test_load_layout_contract_finds_the_reference_fixtures_contract():
    contract = s6.load_layout_contract(SEEDED)
    assert contract["has_build_layout"] is True
    assert contract["default_seed"] == AUTHORED_SEED
    assert Path(contract["module_path"]).name == "game.py"
    assert Path(contract["module_path"]).resolve() == (SEEDED / "game.py").resolve()


def test_load_layout_contract_reports_a_layout_less_worker():
    """toy_worker predates §7 — no build_layout, no authored seed."""
    contract = s6.load_layout_contract(TOY)
    assert contract["has_build_layout"] is False
    assert contract["default_seed"] is None


def test_load_layout_contract_fails_loud_on_a_non_callable_build_layout(tmp_path):
    worker = _write_worker(tmp_path / "noncallable", SEEDED, tail=NON_CALLABLE_TAIL)
    with pytest.raises((TypeError, ValueError)) as excinfo:
        s6.load_layout_contract(worker)
    message = str(excinfo.value).lower()
    assert "build_layout" in message or "callable" in message, str(excinfo.value)


def test_rederive_layouts_returns_one_serialized_layout_per_seed():
    seeds = list(PROBE_SEEDS)
    result = _seed_keyed(s6.rederive_layouts(SEEDED, seeds))
    assert sorted(result) == sorted(seeds)
    module = _game_module(SEEDED)
    rendered = {seed: _layout_value(value) for seed, value in result.items()}
    assert len(set(rendered.values())) == len(seeds), "the per-seed entries collided"
    for seed in seeds:
        assert rendered[seed] == _layout_bytes(module, seed), f"seed {seed}'s entry is not its own"


def test_rederive_layouts_is_deterministic():
    seeds = list(PROBE_SEEDS)
    first = _seed_keyed(s6.rederive_layouts(SEEDED, seeds))
    second = _seed_keyed(s6.rederive_layouts(SEEDED, seeds))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_rederive_layouts_accepts_a_single_seed():
    result = _seed_keyed(s6.rederive_layouts(SEEDED, [AUTHORED_SEED]))
    assert list(result) == [AUTHORED_SEED]


def test_rederive_layouts_refuses_a_seed_ignoring_build_layout(tmp_path):
    """A layout that ignores its seed is a spec §7 violation — ValueError
    naming the colliding pair, never a seed-reject (contract §Semantics 2)."""
    worker = _write_worker(tmp_path / "seedignoring", SEEDED, tail=SEED_IGNORING_TAIL)
    module = _game_module(worker)
    assert _layout_bytes(module, 1) == _layout_bytes(module, 2), "the override did not take"
    with pytest.raises(ValueError) as excinfo:
        s6.rederive_layouts(worker, [AUTHORED_SEED, 1, 2])
    message = str(excinfo.value)
    pair = [seed for seed in (AUTHORED_SEED, 1, 2) if str(seed) in message]
    assert len(pair) >= 2, f"the error names no colliding pair: {message}"


# --------------------------------------------------------------------------- #
# group 3 — validation_seeds
# --------------------------------------------------------------------------- #


def _derived_pool(batch_seed, game_id, span=12) -> set[int]:
    """Every seed `sha256(f"{batch.seed}:{game_id}:s6:{k}")` can make (k<span)."""
    return {
        int(hashlib.sha256(f"{batch_seed}:{game_id}:s6:{k}".encode()).hexdigest()[:8], 16)
        for k in range(span)
    }


def test_validation_seeds_has_the_configured_length(cfg):
    seeds = s6.validation_seeds(cfg, SEEDED_GAME_ID, AUTHORED_SEED)
    assert len(seeds) == cfg["package"]["seeds_validated"] == 5


def test_validation_seeds_puts_the_authored_seed_first(cfg):
    seeds = s6.validation_seeds(cfg, SEEDED_GAME_ID, AUTHORED_SEED)
    assert seeds[0] == AUTHORED_SEED


def test_validation_seeds_are_all_distinct(cfg):
    seeds = s6.validation_seeds(cfg, SEEDED_GAME_ID, AUTHORED_SEED)
    assert len(set(seeds)) == len(seeds), seeds


def test_validation_seeds_is_deterministic(cfg):
    first = s6.validation_seeds(cfg, SEEDED_GAME_ID, AUTHORED_SEED)
    second = s6.validation_seeds(cfg, SEEDED_GAME_ID, AUTHORED_SEED)
    assert first == second


def test_validation_seeds_extras_follow_the_frozen_derivation(cfg):
    seeds = s6.validation_seeds(cfg, SEEDED_GAME_ID, AUTHORED_SEED)
    pool = _derived_pool(cfg["batch"]["seed"], SEEDED_GAME_ID)
    stray = [seed for seed in seeds[1:] if seed not in pool]
    assert not stray, f"extra seed(s) {stray} are not sha256(batch:game:s6:k) values"


def test_validation_seeds_differ_per_game(cfg):
    mine = s6.validation_seeds(cfg, SEEDED_GAME_ID, AUTHORED_SEED)
    theirs = s6.validation_seeds(cfg, BROKEN_GAME_ID, AUTHORED_SEED)
    assert mine[0] == theirs[0] == AUTHORED_SEED
    assert mine[1:] != theirs[1:]


def test_validation_seeds_follow_the_batch_seed(cfg):
    other = dict(cfg)
    other["batch"] = dict(cfg["batch"])
    other["batch"]["seed"] = cfg["batch"]["seed"] + 1
    assert (
        s6.validation_seeds(other, SEEDED_GAME_ID, AUTHORED_SEED)[1:]
        != s6.validation_seeds(cfg, SEEDED_GAME_ID, AUTHORED_SEED)[1:]
    )


# --------------------------------------------------------------------------- #
# group 4 — validate_seed + the end-to-end packaged run
# --------------------------------------------------------------------------- #


def test_validate_seed_reports_the_frozen_record(staged):
    record = s6.validate_seed(staged("seeded").worker, AUTHORED_SEED)
    assert SEED_RECORD_KEYS <= set(record), sorted(record)
    assert record["seed"] == AUTHORED_SEED
    assert record["win"] is True
    assert record["levels_completed"] == LEVEL_COUNT
    assert record["actions_total"] == SEEDED_ACTIONS
    assert record["error"] is None


@pytest.mark.parametrize("seed", SOLVE_SEEDS)
def test_validate_seed_wins_at_every_seed_on_the_reference(staged, seed):
    record = s6.validate_seed(staged("seeded").worker, seed)
    assert record["win"] is True, record
    assert record["levels_completed"] == LEVEL_COUNT


@pytest.mark.parametrize("seed", SOLVE_SEEDS)
def test_validate_seed_fails_off_the_default_on_the_broken_twin(staged, seed):
    record = s6.validate_seed(staged("broken").worker, seed)
    assert record["win"] is False, record
    assert record["levels_completed"] < LEVEL_COUNT


def test_run_s6_packages_the_reference_fixture(packaged):
    report, _out_dir, _play_root = packaged
    assert report["verdict"] == s6.VERDICT_PACKAGED


def test_run_s6_validates_five_seeds_and_all_of_them_win(packaged, cfg):
    report, _out_dir, _play_root = packaged
    validated = report["seeds"]["validated"]
    assert len(validated) == cfg["package"]["seeds_validated"]
    assert validated[0]["seed"] == AUTHORED_SEED
    assert all(record["win"] is True for record in validated), validated
    assert all(record["levels_completed"] == LEVEL_COUNT for record in validated)


def test_the_package_tree_is_complete_at_the_frozen_paths(packaged):
    _report, out_dir, _play_root = packaged
    assert (out_dir / TSV_REL).is_file()
    assert (out_dir / MANIFEST_REL).is_file()
    assert (out_dir / REPORT_NAME).is_file()


def test_the_default_out_dir_is_the_worker_s6_sibling(packaged, staged):
    _report, out_dir, _play_root = packaged
    entry = staged("seeded")
    assert out_dir == entry.worker.parent / (entry.worker.name + s6.OUT_SUFFIX)
    assert out_dir.is_dir()


def test_the_report_is_a_manifest_superset(packaged, manifest):
    report, _out_dir, _play_root = packaged
    assert MANIFEST_KEYS <= set(report), sorted(set(MANIFEST_KEYS) - set(report))
    for key in ("schema_version", "slug", "verdict", "game_hash", "layout_contract"):
        assert report[key] == manifest[key]


def test_the_report_carries_the_play_command_line(packaged):
    """PIN UPDATE, 2026-10-06 (contract H-1 item 4), deliberate and justified.

    This asserted `"PLAY_GAMES_DIR=" in …`, the head of the duckWM one-liner
    `play_command` used to build. L-2 vendored the player into `tools/play/`
    and P-4 gave it `arc-games play`, so that line named a command nobody can
    run from a clone; H-1 item 4 replaced it. What the pin is ABOUT is
    unchanged — the report must carry the recipe — so it now names the recipe
    that exists, and says the stale head is gone.
    """
    report, _out_dir, _play_root = packaged
    blob = json.dumps(report, default=str)
    assert "arc-games play" in blob
    assert "PLAY_GAMES_DIR=" not in blob


def test_rerunning_is_byte_identical(staged, tmp_path):
    """Semantics 8: same worker + same config -> identical tsv, manifest, report."""
    entry = staged("seeded")
    worker, _s4_dir = _clone(entry, tmp_path / "determinism")
    out_dir = tmp_path / "determinism" / "out"
    play_root = tmp_path / "determinism" / "play"
    s6.run_s6(worker, _CFG, out_dir=out_dir, play_root=play_root)
    first = {
        rel: (out_dir / rel).read_bytes() for rel in (TSV_REL, MANIFEST_REL, Path(REPORT_NAME))
    }
    s6.run_s6(worker, _CFG, out_dir=out_dir, play_root=play_root)
    for rel, blob in first.items():
        assert (out_dir / rel).read_bytes() == blob, f"{rel} is not byte-stable"


def test_the_tsv_is_byte_identical_across_out_dirs(staged, tmp_path, tsv_path):
    """The TSV carries no paths, so it cannot drift with where it is written."""
    entry = staged("seeded")
    worker, _s4_dir = _clone(entry, tmp_path / "elsewhere")
    out_dir = tmp_path / "elsewhere" / "out"
    s6.run_s6(worker, _CFG, out_dir=out_dir, play_root=tmp_path / "elsewhere" / "play")
    assert (out_dir / TSV_REL).read_bytes() == tsv_path.read_bytes()


def test_run_s6_refuses_a_worker_with_no_s4_metadata(tmp_path):
    """Semantics 1: the S4 gate — absent metadata is a ValueError (exit 1)."""
    worker = _write_worker(tmp_path / "ungated" / "s6_seeded", SEEDED)
    with pytest.raises(ValueError):
        s6.run_s6(worker, _CFG, out_dir=tmp_path / "ungated" / "out",
                  play_root=tmp_path / "ungated" / "play")


def test_run_s6_refuses_an_s4_verdict_that_is_not_fit(staged, tmp_path):
    entry = staged("seeded")
    worker, s4_dir = _clone(entry, tmp_path / "notfit")
    metadata = json.loads((s4_dir / METADATA_NAME).read_text(encoding="utf-8"))
    metadata["verdict"] = "cap-fit-reject"
    (s4_dir / METADATA_NAME).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        s6.run_s6(worker, _CFG, out_dir=tmp_path / "notfit" / "out",
                  play_root=tmp_path / "notfit" / "play")


def test_run_s6_refuses_missing_action_files(staged, tmp_path):
    """"`actions/level-*.json` must cover every baselined level" (semantics 1)."""
    entry = staged("seeded")
    worker, s4_dir = _clone(entry, tmp_path / "noactions")
    (s4_dir / "actions" / f"level-{LEVEL_COUNT}.json").unlink()
    with pytest.raises(ValueError):
        s6.run_s6(worker, _CFG, out_dir=tmp_path / "noactions" / "out",
                  play_root=tmp_path / "noactions" / "play")


def test_run_s6_refuses_a_layout_less_worker_without_the_legacy_flag(staged, tmp_path):
    """Semantics 2: no build_layout and no opt-out -> REFUSED, naming §7/D13."""
    entry = staged("toy")
    worker, _s4_dir = _clone(entry, tmp_path / "nolayout")
    with pytest.raises(ValueError) as excinfo:
        s6.run_s6(worker, _CFG, out_dir=tmp_path / "nolayout" / "out",
                  play_root=tmp_path / "nolayout" / "play")
    message = str(excinfo.value)
    assert "§7" in message or "D13" in message.upper(), message


def test_seeds_override_shrinks_the_validated_set(staged, tmp_path):
    """`seeds: int | None` reads as a count override (ambiguity I)."""
    entry = staged("seeded")
    worker, _s4_dir = _clone(entry, tmp_path / "threeseeds")
    report = s6.run_s6(
        worker,
        _CFG,
        seeds=3,
        out_dir=tmp_path / "threeseeds" / "out",
        play_root=tmp_path / "threeseeds" / "play",
    )
    assert report["verdict"] == s6.VERDICT_PACKAGED
    assert len(report["seeds"]["validated"]) == 3


# --------------------------------------------------------------------------- #
# group 5 — the seed-reject path
# --------------------------------------------------------------------------- #


def test_a_seed_ignoring_solver_is_a_seed_reject(rejected):
    report, _out_dir, _play_root = rejected
    assert report["verdict"] == s6.VERDICT_SEED_REJECT


def test_the_reject_report_names_the_failing_seeds(rejected):
    report, _out_dir, _play_root = rejected
    validated = report["seeds"]["validated"]
    assert len(validated) == 5
    assert validated[0]["seed"] == AUTHORED_SEED
    assert validated[0]["win"] is True, "the authored seed is the one that DOES solve"
    failing = [record for record in validated[1:] if record["win"] is not True]
    assert len(failing) == 4, validated
    assert all(isinstance(record["seed"], int) for record in failing)


def test_the_reject_writes_a_report_but_no_corpus_surface(rejected):
    """"a rejected game must not become corpus surface" (semantics 3)."""
    _report, out_dir, _play_root = rejected
    assert (out_dir / REPORT_NAME).is_file()
    assert not (out_dir / TSV_REL).exists()
    assert not (out_dir / MANIFEST_REL).exists()


def test_the_reject_writes_no_play_mirror(rejected):
    _report, _out_dir, play_root = rejected
    assert _mirror_dirs(play_root) == []


def test_the_reject_cli_exits_two_and_routes_to_s2(staged, tmp_path, capsys):
    entry = staged("broken")
    worker, _s4_dir = _clone(entry, tmp_path / "rejectcli")
    code, out, _err = _cli(
        [
            "--worker", str(worker),
            "--config", PILOT_CONFIG,
            "--out", str(tmp_path / "rejectcli" / "out"),
            "--play-root", str(tmp_path / "rejectcli" / "play"),
        ],
        capsys,
    )
    assert code == 2, out
    assert "S2" in out
    assert "layout" in out.lower()


# --------------------------------------------------------------------------- #
# group 6 — the TSV dialect
# --------------------------------------------------------------------------- #


def test_the_tsv_header_is_the_frozen_column_list(tsv_path):
    header, _cells = _read_tsv(tsv_path)
    assert header == list(EXPECTED_TSV_COLUMNS)
    assert header == list(s6.TSV_COLUMNS)


def test_every_tsv_row_has_fourteen_cells(tsv_path):
    _header, cells = _read_tsv(tsv_path)
    widths = {len(row) for row in cells}
    assert widths == {14}, widths


def test_the_tsv_has_one_row_per_action_plus_the_terminal_row(tsv_path, staged):
    entry = staged("seeded")
    actions = sum(
        len(json.loads((entry.s4_dir / "actions" / f"level-{index}.json").read_text()))
        for index in range(1, LEVEL_COUNT + 1)
    )
    assert actions == SEEDED_ACTIONS
    _header, cells = _read_tsv(tsv_path)
    assert len(cells) == actions + 1


def test_the_terminal_row_is_the_blank_action_row(tsv_path):
    rows = _rows(tsv_path)
    terminal = rows[-1]
    assert terminal["action"] == ""
    assert terminal["action_valid"] == ""
    assert terminal["duration"] == ""
    assert terminal["terminated"] == "True"
    assert terminal["truncated"] == "False"


def test_action_rows_carry_the_constant_duration_and_valid_flag(tsv_path):
    """§6 Q4: the default text says "omitted"; the PROVEN dialect writes the
    constant 0.0000, which is what B10 emits (see the manifest's flag)."""
    rows = _rows(tsv_path)
    for row in rows[:-1]:
        assert row["action_valid"] == "True"
        assert row["duration"] == "0.0000"


def test_action_cells_are_tsv_dialect_verb_pairs(tsv_path):
    rows = _rows(tsv_path)
    verbs = set()
    for row in rows[:-1]:
        pair = json.loads(row["action"])
        assert isinstance(pair, list) and len(pair) == 2
        verb, payload = pair
        assert verb in set(s6.TSV_VERBS.values()), verb
        assert payload == {}, "only CLICK carries a payload"
        verbs.add(verb)
    assert verbs <= {"UP", "DOWN", "LEFT", "RIGHT"}
    assert len(verbs) > 1, "the fixture's line should use more than one direction"


def test_a_mouse_action_carries_an_xy_payload(staged, tmp_path):
    """ACTION6 is a charged no-op on this board, so one can be spliced into
    the replayed line without breaking the win — the only way to see the
    mouse verb (CLICK — lead-corrected with EXPECTED_TSV_VERBS above)."""
    entry = staged("seeded")
    s4_dir = tmp_path / "mouse.s4"
    shutil.copytree(entry.s4_dir, s4_dir)
    level_one = s4_dir / "actions" / "level-1.json"
    records = json.loads(level_one.read_text(encoding="utf-8"))
    records.insert(0, {"id": 6, "data": {"x": 11, "y": 29}})
    level_one.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")

    out_path = tmp_path / "mouse.tsv"
    s6.emit_tsv(entry.worker, s4_dir, out_path, layout_seed=AUTHORED_SEED)
    rows = _rows(out_path)
    assert len(rows) == SEEDED_ACTIONS + 1 + 1
    pair = json.loads(rows[0]["action"])
    assert pair == ["CLICK", {"x": 11, "y": 29}]


def test_reward_is_sparse_one_per_level_with_the_terminal_echo(tsv_path):
    """Ambiguity L: the action rows sum to the level count; the terminal row
    echoes the win, exactly as the parity-proven dialect does."""
    rows = _rows(tsv_path)
    action_rows, terminal = rows[:-1], rows[-1]
    rewards = [int(row["reward"]) for row in action_rows]
    assert set(rewards) <= {0, 1}
    assert sum(rewards) == LEVEL_COUNT
    per_level = {}
    for row in action_rows:
        per_level.setdefault(int(row["level"]), []).append(int(row["reward"]))
    assert sorted(per_level) == list(range(1, LEVEL_COUNT + 1))
    for level, values in per_level.items():
        assert sum(values) == 1, f"level {level} has {sum(values)} reward rows"
        assert values[-1] == 1, f"level {level}'s 1 is not on its transition action"
    assert int(terminal["reward"]) == 1


def test_only_the_final_row_is_terminated(tsv_path):
    rows = _rows(tsv_path)
    assert [row["terminated"] for row in rows[:-2]] == ["False"] * (len(rows) - 2)
    assert rows[-1]["terminated"] == "True"
    assert all(row["truncated"] == "False" for row in rows)


def test_the_level_column_is_one_indexed_and_runs_past_the_last_level(tsv_path):
    rows = _rows(tsv_path)
    levels = [int(row["level"]) for row in rows]
    assert levels == sorted(levels), "levels must be non-decreasing"
    assert levels[0] == 1
    assert levels[-1] == LEVEL_COUNT + 1, "the terminal row sits after the last level"
    counts = [levels.count(index) for index in range(1, LEVEL_COUNT + 1)]
    assert counts == list(SEEDED_SOLVER)


def test_the_step_column_counts_from_one_and_the_terminal_row_repeats_it(tsv_path):
    rows = _rows(tsv_path)
    steps = [int(row["step"]) for row in rows]
    assert steps[:-1] == list(range(1, len(rows)))
    assert steps[-1] == steps[-2]


def test_the_observation_is_a_sixty_four_square_int_grid(tsv_path):
    rows = _rows(tsv_path)
    for row in (rows[0], rows[len(rows) // 2], rows[-1]):
        grid = ast.literal_eval(row["observation"])
        assert len(grid) == 64
        for line in grid:
            assert len(line) == 64
            assert all(isinstance(value, int) and 0 <= value <= 15 for value in line)


def test_info_round_trips_through_arc_frame_to_frame_data(tsv_path, manifest):
    rows = _rows(tsv_path)
    for row in (rows[0], rows[-1]):
        inner, frame_data = _arc_frame(row)
        assert set(inner) == {"frame", "frame_data", "timestep", "trajectory_step"}
        assert set(frame_data) == {
            "game_id",
            "guid",
            "frame",
            "state",
            "levels_completed",
            "win_levels",
            "full_reset",
            "available_actions",
        }
        assert frame_data["guid"] == f"local-gen-{manifest['slug']}"
        assert isinstance(frame_data["game_id"], str) and frame_data["game_id"]
        assert frame_data["win_levels"] == LEVEL_COUNT
        assert isinstance(frame_data["full_reset"], bool)
        assert frame_data["available_actions"] == [1, 2, 3, 4]
    # SARS: row 1's observation is s_0, the POST-RESET frame (the engine flags
    # `full_reset` there and nowhere else); the terminal row is s_T at the WIN.
    _inner, first = _arc_frame(rows[0])
    assert first["levels_completed"] == 0
    assert first["state"] == "NOT_FINISHED"
    assert first["full_reset"] is True
    _inner, last = _arc_frame(rows[-1])
    assert last["levels_completed"] == LEVEL_COUNT
    assert last["state"] == "WIN"
    assert last["full_reset"] is False


def test_the_four_world_model_columns_are_empty_in_every_row(tsv_path):
    """§6 Q7's default: the WM slots are left for arc_wm to fill."""
    rows = _rows(tsv_path)
    for row in rows:
        for column in ("explore_exploit", "world_model_path", "goal", "exploration_output"):
            assert row[column] == "", column


def test_emit_tsv_is_byte_identical_across_runs(staged, tmp_path):
    entry = staged("seeded")
    first = tmp_path / "a.tsv"
    second = tmp_path / "b.tsv"
    s6.emit_tsv(entry.worker, entry.s4_dir, first, layout_seed=AUTHORED_SEED)
    s6.emit_tsv(entry.worker, entry.s4_dir, second, layout_seed=AUTHORED_SEED)
    assert first.read_bytes() == second.read_bytes()


def test_emit_tsv_at_none_matches_the_authored_seed(staged, tmp_path, tsv_path):
    """None = the authored default seed, so the bytes cannot differ."""
    entry = staged("seeded")
    out_path = tmp_path / "none.tsv"
    s6.emit_tsv(entry.worker, entry.s4_dir, out_path, layout_seed=None)
    assert out_path.read_bytes() == tsv_path.read_bytes()


# --------------------------------------------------------------------------- #
# group 7 — the manifest
# --------------------------------------------------------------------------- #


def test_the_manifest_has_exactly_the_frozen_top_level_keys(manifest):
    assert set(manifest) == MANIFEST_KEYS


def test_the_manifest_identifies_the_game(manifest, staged):
    assert manifest["schema_version"] == s6.SCHEMA_VERSION
    assert manifest["verdict"] == s6.VERDICT_PACKAGED
    assert isinstance(manifest["slug"], str) and manifest["slug"]
    assert manifest["game_id"] == staged("seeded").metadata["game_id"] == SEEDED_GAME_ID


def test_the_manifest_seed_block_is_the_validated_table(manifest):
    seeds = manifest["seeds"]
    assert set(seeds) == SEED_KEYS
    assert seeds["authored_seed"] == AUTHORED_SEED
    assert len(seeds["validated"]) == 5
    for record in seeds["validated"]:
        assert SEED_RECORD_KEYS <= set(record), sorted(record)
    requested = seeds["requested"]
    assert requested == 5 or (isinstance(requested, list) and len(requested) == 5), requested


def test_the_manifest_split_is_the_configured_slug_level_split(manifest, cfg):
    split = manifest["split"]
    assert set(split) == {"train", "eval", "note"}
    assert split["train"] == cfg["package"]["split"]["train"] == 0.7
    assert split["eval"] == cfg["package"]["split"]["eval"] == 0.3
    assert split["note"] == SPLIT_NOTE


def test_the_manifest_records_the_layout_contract(manifest):
    assert manifest["layout_contract"] == {"present": True, "legacy_no_layout": False}


def test_game_hash_is_the_provenance_chains_sha(staged):
    """architecture §2: `game_hash = sha(game.py + solver.py)`."""
    entry = staged("seeded")
    expected = hashlib.sha256(
        (entry.worker / "game.py").read_bytes() + (entry.worker / "solver.py").read_bytes()
    ).hexdigest()
    assert s6.game_hash(entry.worker) == expected


def test_the_manifest_carries_that_game_hash(manifest, staged):
    assert manifest["game_hash"] == s6.game_hash(staged("seeded").worker)
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["game_hash"])


def test_game_hash_moves_when_game_py_moves(tmp_path):
    worker = _write_worker(tmp_path / "hash_game", SEEDED)
    before = s6.game_hash(worker)
    game = worker / "game.py"
    game.write_text(game.read_text(encoding="utf-8") + "# one more byte\n", encoding="utf-8")
    assert s6.game_hash(worker) != before


def test_game_hash_moves_when_solver_py_moves(tmp_path):
    worker = _write_worker(tmp_path / "hash_solver", SEEDED)
    before = s6.game_hash(worker)
    solver = worker / "solver.py"
    solver.write_text(solver.read_text(encoding="utf-8") + "# one more byte\n", encoding="utf-8")
    assert s6.game_hash(worker) != before


def test_spec_hash_is_none_without_a_spec(manifest):
    assert s6.spec_hash(None) is None
    assert manifest["spec_hash"] is None


def test_spec_hash_is_the_files_sha(tmp_path):
    """architecture §2: `spec_hash = sha(spec.yaml)`."""
    spec = tmp_path / "spec.yaml"
    spec.write_text("game:\n  slug: s6-seeded-gate\n", encoding="utf-8")
    assert s6.spec_hash(spec) == hashlib.sha256(spec.read_bytes()).hexdigest()
    other = tmp_path / "other.yaml"
    other.write_text("game:\n  slug: something-else\n", encoding="utf-8")
    assert s6.spec_hash(other) != s6.spec_hash(spec)


def test_the_manifest_carries_the_spec_hash_when_a_spec_is_given(staged, tmp_path):
    entry = staged("seeded")
    worker, _s4_dir = _clone(entry, tmp_path / "withspec")
    spec = tmp_path / "withspec" / "spec.yaml"
    spec.write_text("game:\n  slug: s6-seeded-gate\n", encoding="utf-8")
    out_dir = tmp_path / "withspec" / "out"
    s6.run_s6(
        worker,
        _CFG,
        spec_path=spec,
        out_dir=out_dir,
        play_root=tmp_path / "withspec" / "play",
    )
    written = json.loads((out_dir / MANIFEST_REL).read_text(encoding="utf-8"))
    assert written["spec_hash"] == s6.spec_hash(spec)


def test_the_section6_flags_name_every_binding_default(manifest):
    by_id = _flags_by_question(manifest)
    assert set(by_id) == SECTION6_QUESTIONS
    assert not (set(by_id) & SECTION6_UNBOUND), "Q2/Q8/Q10 do not bind the packager"
    for question, flag in by_id.items():
        assert flag["pending_contract_answer"] is True, question
        assert str(flag.get("default_applied") or "").strip(), question


def test_the_q4_flag_records_the_duration_divergence(manifest):
    """The §6 default says "duration omitted"; the proven dialect writes
    0.0000. The contract freezes: we emit 0.0000 and FLAG the divergence."""
    flag = _flags_by_question(manifest)[4]
    blob = json.dumps(flag, default=str)
    assert "0.0000" in blob, flag
    assert flag.get("note"), "the Q4 divergence must carry a note"


def test_the_manifest_records_versions_and_paths(manifest):
    assert isinstance(manifest["versions"], dict) and manifest["versions"]
    paths = json.dumps(manifest["paths"], default=str)
    assert "level-set.tsv" in paths
    assert "manifest.json" in paths


# --------------------------------------------------------------------------- #
# group 8 — the play mirror
# --------------------------------------------------------------------------- #


def test_write_play_mirror_lands_where_the_play_server_looks(staged, tmp_path):
    """server.py:103 globs `<root>/*/*/metadata.json` (READ-ONLY reference)."""
    entry = staged("seeded")
    play_root = tmp_path / "mirror"
    hash8 = s6.game_hash(entry.worker)[:8]
    result = s6.write_play_mirror(
        entry.worker, entry.metadata, game_hash8=hash8, play_root=play_root
    )
    mirrors = _mirror_dirs(play_root)
    assert len(mirrors) == 1, mirrors
    mirror = mirrors[0]
    assert mirror.name == hash8
    assert mirror.parent.parent == play_root
    assert Path(result).exists()
    assert Path(result) in (mirror, mirror / "metadata.json")


def test_the_mirror_carries_the_game_file_byte_for_byte(staged, tmp_path):
    entry = staged("seeded")
    play_root = tmp_path / "mirror_bytes"
    hash8 = s6.game_hash(entry.worker)[:8]
    s6.write_play_mirror(entry.worker, entry.metadata, game_hash8=hash8, play_root=play_root)
    mirror = _mirror_dirs(play_root)[0]
    slug = mirror.parent.name
    assert (mirror / f"{slug}.py").read_bytes() == (entry.worker / "game.py").read_bytes()
    assert sorted(path.name for path in mirror.glob("*.py")) == [f"{slug}.py"]


def test_the_mirror_metadata_is_the_officials_shape(staged, tmp_path):
    entry = staged("seeded")
    play_root = tmp_path / "mirror_meta"
    hash8 = s6.game_hash(entry.worker)[:8]
    s6.write_play_mirror(entry.worker, entry.metadata, game_hash8=hash8, play_root=play_root)
    mirror = _mirror_dirs(play_root)[0]
    slug = mirror.parent.name
    meta = json.loads((mirror / "metadata.json").read_text(encoding="utf-8"))
    assert PLAY_METADATA_KEYS <= set(meta), sorted(meta)
    assert meta["game_id"] == f"{slug}-{hash8}"
    assert meta["tags"] == ["generated"]
    assert meta["default_fps"] == 30
    assert meta["baseline_actions"] == entry.metadata["baseline_actions"]
    assert len(meta["baseline_actions"]) == LEVEL_COUNT
    squashed = re.sub(r"[^a-z0-9]", "", str(meta["title"]).lower())
    assert squashed == re.sub(r"[^a-z0-9]", "", slug.lower()), meta["title"]


def test_write_play_mirror_overwrites_an_existing_mirror(staged, tmp_path):
    entry = staged("seeded")
    play_root = tmp_path / "mirror_twice"
    hash8 = s6.game_hash(entry.worker)[:8]
    for _ in range(2):
        s6.write_play_mirror(entry.worker, entry.metadata, game_hash8=hash8, play_root=play_root)
    mirrors = _mirror_dirs(play_root)
    assert len(mirrors) == 1, mirrors


def test_the_packaged_run_mirrors_under_the_given_play_root(packaged, manifest, staged):
    _report, _out_dir, play_root = packaged
    mirrors = _mirror_dirs(play_root)
    assert len(mirrors) == 1, mirrors
    mirror = mirrors[0]
    assert mirror.name == manifest["game_hash"][:8]
    assert mirror.parent.name == manifest["slug"]
    meta = json.loads((mirror / "metadata.json").read_text(encoding="utf-8"))
    assert meta["game_id"] == f"{manifest['slug']}-{manifest['game_hash'][:8]}"
    assert meta["baseline_actions"] == staged("seeded").metadata["baseline_actions"]


# --------------------------------------------------------------------------- #
# group 9 — legacy_no_layout (the pre-§7 toy)
# --------------------------------------------------------------------------- #


def test_a_layout_less_worker_packages_under_the_legacy_opt_out(legacy):
    report, _out_dir, _play_root = legacy
    assert report["verdict"] == s6.VERDICT_PACKAGED


def test_the_legacy_manifest_says_the_contract_is_absent(legacy):
    _report, out_dir, _play_root = legacy
    written = json.loads((out_dir / MANIFEST_REL).read_text(encoding="utf-8"))
    assert written["layout_contract"] == {"present": False, "legacy_no_layout": True}
    assert set(written) == MANIFEST_KEYS


def test_the_legacy_seed_list_collapses_to_one_drive(legacy):
    """Semantics 3: "the seed list collapsed to [None]"."""
    report, _out_dir, _play_root = legacy
    validated = report["seeds"]["validated"]
    assert len(validated) == 1
    assert validated[0]["seed"] is None
    assert validated[0]["win"] is True
    assert report["seeds"]["authored_seed"] is None


def test_the_legacy_package_still_ships_a_tsv_and_a_mirror(legacy):
    _report, out_dir, play_root = legacy
    assert (out_dir / TSV_REL).is_file()
    assert len(_mirror_dirs(play_root)) == 1


def test_the_legacy_cli_says_so_loudly(staged, tmp_path, capsys):
    entry = staged("toy")
    worker, _s4_dir = _clone(entry, tmp_path / "legacycli")
    code, out, _err = _cli(
        [
            "--worker", str(worker),
            "--config", PILOT_CONFIG,
            "--out", str(tmp_path / "legacycli" / "out"),
            "--play-root", str(tmp_path / "legacycli" / "play"),
            "--legacy-no-layout",
        ],
        capsys,
    )
    assert code == 0, out
    assert "legacy" in out.lower() or "no layout" in out.lower(), out


# --------------------------------------------------------------------------- #
# group 10 — the CLI
# --------------------------------------------------------------------------- #


def test_the_cli_exits_zero_on_packaged(staged, tmp_path, capsys):
    entry = staged("seeded")
    worker, _s4_dir = _clone(entry, tmp_path / "okcli")
    code, out, _err = _cli(
        [
            "--worker", str(worker),
            "--config", PILOT_CONFIG,
            "--out", str(tmp_path / "okcli" / "out"),
            "--play-root", str(tmp_path / "okcli" / "play"),
        ],
        capsys,
    )
    assert code == 0, out
    assert "[s6]" in out, out
    assert s6.VERDICT_PACKAGED in out.lower()


def test_the_cli_prints_the_operators_play_one_liner_last(staged, tmp_path, capsys, cfg):
    """PIN UPDATE, 2026-10-06 (contract H-1 item 4), deliberate and justified.

    The SHAPE of the pin is untouched: the last line the packager prints is the
    play recipe, and it names the play root this run mirrored into. Only the
    recipe moved. It asserted `PLAY_GAMES_DIR=<root> <duckWM .venv python>
    <.../arc-agi-3-games/tools/play/server.py>`; since L-2 vendored the player
    and P-4 gave it a subcommand, the line is `arc-games play --root <root>`,
    and the duckWM paths it used to require must NOT be in it — which is what
    `_duckwm_paths` now proves, instead of being what the line was made of.
    """
    entry = staged("seeded")
    worker, _s4_dir = _clone(entry, tmp_path / "playline")
    play_root = tmp_path / "playline" / "play"
    code, out, _err = _cli(
        [
            "--worker", str(worker),
            "--config", PILOT_CONFIG,
            "--out", str(tmp_path / "playline" / "out"),
            "--play-root", str(play_root),
        ],
        capsys,
    )
    assert code == 0, out
    last = out.rstrip("\n").split("\n")[-1]
    assert last.startswith("arc-games play "), last
    assert "PLAY_GAMES_DIR=" not in last, last
    assert str(play_root.resolve()) in last, last
    python, server = _duckwm_paths(cfg)
    assert str(python) not in last, last
    assert str(server) not in last, last


def test_the_cli_exits_one_when_the_s4_gate_is_not_met(tmp_path, capsys):
    worker = _write_worker(tmp_path / "gatecli" / "s6_seeded", SEEDED)
    code, _out, _err = _cli(
        [
            "--worker", str(worker),
            "--config", PILOT_CONFIG,
            "--out", str(tmp_path / "gatecli" / "out"),
            "--play-root", str(tmp_path / "gatecli" / "play"),
        ],
        capsys,
    )
    assert code == 1


def test_the_cli_writes_the_package_it_reports(staged, tmp_path, capsys):
    entry = staged("seeded")
    worker, _s4_dir = _clone(entry, tmp_path / "clipaths")
    out_dir = tmp_path / "clipaths" / "out"
    code, out, _err = _cli(
        [
            "--worker", str(worker),
            "--config", PILOT_CONFIG,
            "--out", str(out_dir),
            "--play-root", str(tmp_path / "clipaths" / "play"),
        ],
        capsys,
    )
    assert code == 0, out
    assert (out_dir / TSV_REL).is_file()
    assert (out_dir / MANIFEST_REL).is_file()
    assert (out_dir / REPORT_NAME).is_file()
