"""S6 — the packager (architecture §3 "S6 — packager"; B10).

Turns an accepted game into consumable corpus surface. In→Out (architecture
§3 S6): `worker/` + S4 `metadata.json` → `package/` (`tsv/level-set.tsv` +
`manifest.json`, the §2 corpus-tree node) + the play mirror. Executor: pure
code + the engine (seed-validation replays). Failure routing: a failing
validation seed → **S2 (the layout function is buggy)**.

Four things this stage owns:

1. **The layout-seed contract ⊕** (architecture §3 S6; spec-v0.3 §7; D13):
   `build_layout(seed) -> list` is a PURE function, layouts are structurally
   distinct under seed, and the solver must solve ANY seed (it receives the
   same seed). `package.seeds_validated` seeds are validated at package time —
   the authored default first, the rest derived from `batch.seed`. Layout-
   from-seed is REQUIRED FROM BIRTH; a game that ships without it is refused
   unless the caller passes `legacy_no_layout` (the toy/fixtures predate D13).
   A `build_layout` that IGNORES its seed is a §7 violation, not a
   seed-reject: it fails the re-derivation, loudly, before any seed is played.

2. **The TSV** — the team dialect, ADAPTED (never imported, never executed)
   from the parity-proven reference emitter
   `arc-agi-3-generator/tools/capture_frames.py` (`_tsv_row` / `_write_tsv`):
   14 columns, SARS rows (observation = the PRE-action settled board, reward /
   terminated = the result of that action) plus the blank-action terminal row.
   That shape is 8/8 structural parity against the reference
   `sprite_lib_v2` file with a byte-identical first observation
   (trajectory-contract.md §4 + §7 appendix). ACTION6 spells **CLICK** — the
   measured spelling in all 24 official TSVs and the literal five sprite_lib
   sites gate on (see `TSV_VERBS`; b003 freeze addendum 7). The same bytes are
   ALSO written to `package/duck-intake/<slug>_perfect/human_policy/
   unprocessed_game.tsv`, the path the consumer's own `--sample-dir` glob
   finds, so intake needs zero renaming; `tsv/level-set.tsv` stays the
   canonical corpus artifact and the mirror is a copy of it, never a re-emission.

3. **The §6 flag table** — every default from trajectory-contract.md §6
   ("Defaults if unanswered (we proceed on these, flagged as assumptions)")
   that this package actually leans on is named in the manifest with
   `pending_contract_answer: true`. Q1/Q3/Q4/Q5/Q6/Q7/Q9 bind the packager;
   Q2 (lf52's exclusion), Q8 (the SFT lane) and Q10 (licensing) do not, so
   they are not flagged. **Q4 diverges on purpose**: the default text says
   `duration` omitted, the proven dialect writes the constant `"0.0000"` in
   every action row — we follow the PROVEN DIALECT and flag it.

4. **The play mirror** — `out/play/<slug>/<game_hash8>/` in the officials'
   layout, which is exactly what the play server's discovery glob
   (`<root>/*/*/metadata.json`, `tools/play/server.py`) and its loader
   consume. Printed as a ready `arc-games play --root …` one-liner (contract
   H-1 item 4; it was a `PLAY_GAMES_DIR=…` line naming duckWM's checkout until
   L-2 vendored the player and P-4 gave it a command);
   never executed from here. Contract D-2 adds the same layout ONE EDGE
   EARLIER: `write_play_preview` mirrors a `" (review pending)"`-titled build
   at `baselined --> played`, so the human verdict §4 halts for is cast on a
   playable game; this stage's own pass then overwrites it with the clean
   title, and `withdraw_play_preview` pulls it when the review says no.

5. **The shared shelf** (contract P-3) — `games/<slug>/game/`, the TRACKED copy
   of a packaged game, so sharing a game is `git pull` rather than a tarball
   (operator ruling, docs/v2/DECISIONS.md 2026-09-29). `promote_game` copies an
   already-packaged tree there with the manifest's absolute `paths` rewritten
   relative to the entry; `withdraw_game` takes one off. Only promoted games
   enter it, the orchestrator holds the two call sites and this module owns the
   behavior. Nothing in `run_s6` writes to `games/`: packaging and promotion are
   separate acts, so the `out/` tree stays byte-identical to its pre-P-3 shape.

Provenance (architecture §2 ⊕): `spec_hash = sha(spec.yaml)`,
`game_hash = sha(game.py + solver.py)`.

Nothing written here is time-stamped or path-random: the same worker and the
same config give a byte-identical TSV, manifest and report on a re-run.

CLI:
  python -m gen.s6_package --worker out/workers/w001
  python -m gen.s6_package --worker gen/tests/toy_worker --legacy-no-layout
Exit 0 = packaged, 2 = seed-reject, 1 = usage/refusal.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
from arcengine import ARCBaseGame, GameState

from .config import REPO_ROOT, load_config
from .frames import TERMINAL_STATES, _fresh_game, _perform, _reset, quiet, settled_grid
from .s3_static import game_source_path, load_worker_classes, solver_source_path
from .s4_baselines import ACTIONS_DIRNAME, VERDICT_FIT, _action_from_record
from .s4_baselines import METADATA_NAME as S4_METADATA_NAME
from .s4_baselines import OUT_SUFFIX as S4_OUT_SUFFIX
from .s5_battery import load_battery_metadata
from .worker import purge_worker_modules

SCHEMA_VERSION = "b10.1"
DEFAULT_CONFIG = "config/b001-pilot.yaml"

# --- vocabulary -------------------------------------------------------------
VERDICT_PACKAGED = "packaged"
VERDICT_SEED_REJECT = "seed-reject"

# architecture §3 S6 failure routing, verbatim.
ROUTE_SEED_REJECT = "S2 (the layout function is buggy)"

# --- worker-code containment (contract P-1) ---------------------------------
#
# WHY THIS EXISTS. b004 (2026-09-28): `run_s6` called the worker's own
# `build_layout(seed)` in-process with no containment and the game raised
# `ValueError: no winning line for level 4` at seed 3 (it accepts seeds 0-2 and
# 4-11) — which CRASHED the orchestrator instead of judging the game, and the
# slot was then left with no §4 edge to travel anyway. The precedent for the fix
# is `gen/s3_static.run_solver_quality` (the b004 finding #3 fix, same batch,
# same class of defect): wrap the call, extract the crash site inside the WORKER
# dir, and return a VERDICT.
#
# OPERATOR RULING (2026-09-29, on the record): "the pipeline must run WITHOUT
# human feedback — scalable autonomy". A stage that kills the run on worker code
# is the opposite of that: nothing in this file may raise a worker's exception
# at the orchestrator.
#
# Scope, stated: this contains the calls S6 makes into worker code while
# VALIDATING (the exec-load, the authored-seed probe, `build_layout` under
# re-derivation, and the per-seed solve drive). The emission half (`emit_tsv`,
# the play mirror) is deliberately NOT contained — it runs only after every seed
# has already WON, so a crash there is not a seed verdict and must stay loud.
SEED_CRASH_REJECT = "worker code crashed during seed validation"


class WorkerCodeError(RuntimeError):
    """An exception raised BY the worker's own code, caught at the call site.

    It carries the three things a verdict row needs and a raw exception does
    not: which SEED was being validated (None = the authored default layout),
    the crash SITE inside the worker's own files, and a note that already reads
    as a finding. `run_s6` turns it into a failing seed row; nothing else in
    this module lets it escape.
    """

    def __init__(self, note: str, *, seed: int | None, site: str,
                 cause: BaseException) -> None:
        super().__init__(note)
        self.note = note
        self.seed = seed
        self.site = site
        self.cause = cause


def _worker_site(exc: BaseException, worker_dir: Path) -> str:
    """`game.py:214` — the last traceback frame inside the worker's own dir.

    Same extraction as `s3_static.run_solver_quality`'s (b004 finding #3): the
    LAST frame under `worker_dir` is the line the game itself died on, and the
    last frame overall is the honest fallback when the crash happened before any
    worker file was on the stack.
    """
    frames = traceback.extract_tb(exc.__traceback__)
    ours = [frame for frame in frames if str(worker_dir) in (frame.filename or "")]
    site = ours[-1] if ours else (frames[-1] if frames else None)
    return f"{Path(site.filename).name}:{site.lineno}" if site else "unknown site"


def _run_worker_code(call, *, worker_dir: Path, seed: int | None, what: str):
    """Call worker code; ANY exception out of it becomes a `WorkerCodeError`.

    `what` names the call in the verdict ("re-deriving build_layout", "loading
    the worker's game module"), so the seed row says what the pipeline was doing
    when the game died rather than only that something did.
    """
    try:
        return call()
    except WorkerCodeError:
        raise                      # already contained one level down
    except Exception as exc:       # any worker-code crash is a verdict, not ours
        site = _worker_site(exc, Path(worker_dir))
        where = "the authored default layout" if seed is None else f"seed {seed}"
        raise WorkerCodeError(
            f"{what} crashed at {where}: {type(exc).__name__}: {exc} (at {site}) — "
            "a layout the worker cannot build cannot be validated",
            seed=seed, site=site, cause=exc,
        ) from exc

# --- output layout (the B3/B7/B8/B9 sibling rule) ---------------------------
# Never inside the worker: any file there trips the worker's own scaffold
# scope check and makes `make validate` green unreachable.
OUT_SUFFIX = ".s6"
PACKAGE_DIRNAME = "package"          # architecture §2 corpus tree: package/
TSV_DIRNAME = "tsv"                  #   package/tsv/level-set.tsv
TSV_NAME = "level-set.tsv"
MANIFEST_NAME = "manifest.json"      #   package/manifest.json
REPORT_NAME = "s6-report.json"

# The duck-intake mirror (C-5). Every element below is a LITERAL the consumer
# globs on, not a naming preference: `sprite_lib/tools/evaluate_sprite_library.py
# :460` discovers games with `--sample-dir`.glob("*_perfect/human_policy/
# unprocessed_game.tsv") and takes the game id from the directory name minus
# the `_perfect` suffix (:459); `tools/sprite_viewer.py:1066-1069` and
# `tools/eval_gold_standard.py:94-97` join the same three components. So a
# package that carries this shape is pointed at with zero renaming.
DUCK_INTAKE_DIRNAME = "duck-intake"     # package/duck-intake/
DUCK_INTAKE_QUALIFIER = "_perfect"      #   <slug>_perfect/
DUCK_INTAKE_POLICY = "human_policy"     #     human_policy/
DUCK_INTAKE_NAME = "unprocessed_game.tsv"  #       unprocessed_game.tsv

# The play mirror root. Writes go HERE or to a caller-supplied `play_root`,
# and nowhere else — out/ is this repo's runtime surface (.gitignore).
PLAY_ROOT = REPO_ROOT / "out" / "play"
PLAY_TAGS = ("generated",)
PLAY_DEFAULT_FPS = 30

# Contract H-1 item 4 (2026-10-06): the two `duckwm_docs`-relative play-server
# paths that used to live here are GONE with the one-liner that needed them.
# `play_command` prints `arc-games play --root …` and resolves the player
# through `cli.play_player`, which prefers the L-2 vendored copy in
# `tools/play/`; `gen/cli.py` still keeps its own (differently rooted)
# `PLAY_SERVER_REL`/`PLAY_PYTHON_REL` for the sibling-duckWM fallback, and
# those two are the only ones left.

# --- the TSV dialect (frozen; adapted from capture_frames.py) ---------------

# The parity-proven 14, in order (`capture_frames._write_tsv`; header matched
# byte-for-byte against the sprite_lib_v2 reference — trajectory-contract §7).
TSV_COLUMNS = (
    "step", "observation", "info", "level", "action_valid", "duration", "action",
    "reward", "terminated", "truncated", "explore_exploit", "world_model_path",
    "goal", "exploration_output",
)

# trajectory-contract.md §3's mapping table. ACTION7/undo is unmapped there
# ("— (absent)"), so an id outside this map falls back to `ACTION<id>`, which
# is what the reference emitter does.
#
# ACTION6 spells CLICK, not MOUSE (b003 freeze addendum 7, C-5). MEASURED, not
# inferred: all 24 official trajectory TSVs under duckWM sha 31f3a8b
# (`src/ARC3-Inference/inference/sprite_lib/sample_trajectories/<slug>_perfect/
# human_policy/unprocessed_game.tsv`) contain ZERO `MOUSE` cells and 1575
# `CLICK` cells across the 17 of 24 games that use a mouse verb at all. The
# consumer gates on that literal in four modules — `operation_tracking.py:33`
# (`name != 'CLICK' or set(params) != {'x','y'}`), `selection.py:238/246/322/325`,
# `selection_markers.py:74`, `heuristic_sprite_bootstrap.py:5304` — plus two
# `budget_actions` lists (`heuristic_rule_bootstrap.py:972`,
# `starter_code/priors/decrement_action_budget_rule.py:62`). So a MOUSE
# spelling is not a synonym the consumer tolerates: it silently discards 100%
# of those rows (smoke-measured: 116/348 actions invisible in conduit-watch;
# under CLICK duck learns button semantics, DarkGrayRect -> DarkGrayButton).
# b002's contrary "falsified" ruling used our OWN capture tool's output as
# ground truth and is corrected on the record in addendum 7.
#
# RESET=0 and ACTION7/undo keep the fallback spelling. Recorded, not changed:
# the officials do show a literal `RESET` verb (g50t 6 rows, lp85 1 row), which
# ACTION0 would reach only through the `ACTION<id>` fallback, and no official
# file contains an UNDO row at all — neither is in the §3 table, and neither is
# in this contract's scope.
TSV_VERBS = {1: "UP", 2: "DOWN", 3: "LEFT", 4: "RIGHT", 5: "INTERACT", 6: "CLICK"}

# §6 Q4, resolved against the measurement: see SECTION6_DEFAULTS["Q4"].
TSV_DURATION = "0.0000"

# `capture_frames._tsv_row` writes `local-demo-<slug>`; ours are generated, so
# the qualifier is `gen`. The guid is a producer tag, not an identity the
# consumer joins on (trajectory-contract §1 frame_data keys).
GUID_PREFIX = "local-gen-"

# Solver-drive bound, same default as `s4_baselines.solver_lines`.
MAX_ACTIONS = 600

# --- the §6 flag table ------------------------------------------------------
# `default_applied` is VERBATIM from trajectory-contract.md §6's closing line:
#   "Defaults if unanswered (we proceed on these, flagged as assumptions): TSV
#    canonical; solver as policy; verbs in TSV dialect; duration omitted;
#    sparse reward; no baked augmentation; empty WM columns left empty;
#    volume = 1 near-optimal per level-set per game."
# "solver as policy" is not one of the ten numbered questions; it rides in
# Q9's note, which is where the packager actually leans on it.
SECTION6_DEFAULTS = (
    {
        "question": "Q1",
        "default_applied": "TSV canonical",
        "pending_contract_answer": True,
        "note": (
            "package/tsv/level-set.tsv is the CANONICAL trajectory surface this stage "
            "ships; §1 names the ingest path "
            "<slug>_<qualifier>/<policy>/unprocessed_game.tsv, so a generated game is "
            "meant to be a path addition, and C-5 makes that concrete: "
            "package/duck-intake/<slug>_perfect/human_policy/unprocessed_game.tsv is a "
            "byte-identical copy of the same file at the consumer's own literals "
            "(sprite_lib --sample-dir globs *_perfect/human_policy/unprocessed_game.tsv)."
        ),
    },
    {
        "question": "Q3",
        "default_applied": "verbs in TSV dialect",
        "pending_contract_answer": True,
        "note": (
            "§3 mapping table: ACTION1-4 -> UP/DOWN/LEFT/RIGHT, ACTION5 -> INTERACT, "
            "ACTION6 -> CLICK with {x,y}. CLICK is the MEASURED spelling — 24/24 official "
            "TSVs at duckWM sha 31f3a8b carry CLICK and none carries MOUSE, and five "
            "sprite_lib sites gate on the literal (b003 freeze addendum 7). Any other id "
            "(incl. RESET=0 and ACTION7/undo, both unmapped there) falls back to "
            "ACTION<id>, as the reference emitter does."
        ),
    },
    {
        "question": "Q4",
        "default_applied": "duration omitted",
        "pending_contract_answer": True,
        "note": (
            'DIVERGENCE, deliberate: the §6 default text says omitted, but the dialect we '
            'proved parity against writes the constant "0.0000" in every action row (§1 '
            'duration row: "0.0000 in ALL rows of their own human file"; §6 Q4 "largely '
            'self-answers (emit 0.0000)"). This emitter follows the PROVEN DIALECT — '
            '"0.0000" on action rows, "" on the terminal row — and flags the divergence here.'
        ),
    },
    {
        "question": "Q5",
        "default_applied": "sparse reward",
        "pending_contract_answer": True,
        "note": (
            "0/1 per row: 1 on a levels_completed increment or WIN, and the terminal row "
            "echoes the win reward, so a winning file carries levels+1 ones (§1 measured on "
            'ar25: "9 ones = 8 levels_completed increments + 1 on the final WIN step"; §4 '
            'parity check "reward count incl. the terminal-row echo"). The EnvSampler\'s '
            "transition reward (§5) is NOT emitted."
        ),
    },
    {
        "question": "Q6",
        "default_applied": "no baked augmentation",
        "pending_contract_answer": True,
        "note": (
            "one TSV, at the authored layout seed. Layout variants stay a sampler call "
            "(D13; architecture §3 S6: per-seed emission on demand rather than pre-baked), "
            "and no colour/rot/flip copies are written."
        ),
    },
    {
        "question": "Q7",
        "default_applied": "empty WM columns left empty",
        "pending_contract_answer": True,
        "note": (
            "explore_exploit / world_model_path / goal / exploration_output are written "
            "empty in every row, terminal included (§1: empty in all 260 ar25 rows)."
        ),
    },
    {
        "question": "Q9",
        "default_applied": "volume = 1 near-optimal per level-set per game",
        "pending_contract_answer": True,
        "note": (
            "exactly one line is replayed — S4's winning solver line "
            "(actions/level-*.json), which is §6's 'solver as policy' default made "
            "concrete by D11 (solver-first). No noisy or failed trajectories."
        ),
    },
)


# --- worker loading ---------------------------------------------------------

# One module per worker per (path, mtime, size). `s3_static.load_worker_classes`
# re-execs the game file on every call; S6 calls it from four entry points and
# needs `build_layout` and the game class to come from the SAME module object
# (the §7 convention makes them one unit). Keying on mtime+size keeps an edited
# file from being served stale.
_WORKER_CACHE: dict[tuple, tuple] = {}


def _stat_key(path: Path) -> tuple:
    st = path.stat()
    return (str(path), st.st_mtime_ns, st.st_size)


def _load_worker(worker_dir: Path) -> tuple[Path, object, type, type | None]:
    """`(game_path, module, game_cls, solver_cls)` for one worker dir.

    Contract E-4: the worker's OWN `sys.modules` entries are evicted on every
    call, before the cache lookup below. The shared loader evicts them too, so
    a cache MISS is covered either way; doing it here as well is what makes a
    cache HIT — this stage's four entry points and five validation seeds per
    game all hit — re-read `game.py` from disk through the solver's sibling
    loader instead of whatever a previous cycle left in the module table. The
    stat-keyed cache below is OURS and stays: it holds the module object
    directly and is keyed on the bytes' mtime+size.
    """
    worker_dir = Path(worker_dir)
    purge_worker_modules(worker_dir)
    game_path = game_source_path(worker_dir).resolve()
    solver_path = solver_source_path(worker_dir)
    key = (
        _stat_key(game_path),
        _stat_key(solver_path.resolve()) if solver_path is not None else None,
    )
    cached = _WORKER_CACHE.get(key)
    if cached is not None:
        return cached
    # THE EXEC-LOAD (contract P-1). `load_worker_classes` imports and executes
    # the worker's `game.py`/`solver.py`: module-level code we did not write. A
    # game whose import dies takes the whole run with it unless the crash is
    # contained here, at the one place this module loads it.
    game_cls, solver_cls = _run_worker_code(
        lambda: load_worker_classes(worker_dir),
        worker_dir=worker_dir, seed=None,
        what="loading the worker's game and solver modules",
    )
    module = sys.modules.get(game_cls.__module__)
    if module is None:
        raise ValueError(
            f"{game_path}: the game class {game_cls.__name__} does not belong to a loaded "
            f"module ({game_cls.__module__!r}) — S6 reads build_layout from the game's own "
            "module (spec §7)"
        )
    loaded = (game_path, module, game_cls, solver_cls)
    _WORKER_CACHE[key] = loaded
    return loaded


def _slug(worker_dir: Path) -> str:
    """The corpus slug for a worker dir.

    architecture §2's tree is `corpus/<batch-id>/<slug>/worker/`, so a dir
    literally named `worker` names its parent; anything else names itself
    (that is how the B3+ workers and the test fixtures sit on disk).
    """
    worker_dir = Path(worker_dir)
    name = worker_dir.name
    if name == "worker":
        name = worker_dir.parent.name
    if not name or name in (".", ".."):
        raise ValueError(
            f"cannot derive a slug from {worker_dir} — S6 names the package, the play "
            "mirror and the TSV frame_data after it (architecture §2 corpus tree)"
        )
    return name


def _fresh_seeded(game_cls, layout_seed: int | None):
    """`frames._fresh_game`, able to pass the §7 `layout_seed` keyword.

    `layout_seed=None` means "the authored default" (the §7 convention), which
    is exactly a no-argument construction, so that case delegates verbatim.
    """
    if layout_seed is None:
        return _fresh_game(game_cls)
    os.environ.pop("ONLY_RESET_LEVELS", None)  # same reason as frames._fresh_game
    with quiet():
        game = game_cls(layout_seed=int(layout_seed))
    if not isinstance(game, ARCBaseGame):
        raise TypeError(
            f"{game_cls!r}(layout_seed={layout_seed!r}) did not construct an ARCBaseGame "
            f"(got {type(game).__name__})"
        )
    return game


# --- the layout-seed contract (spec §7 / D13) -------------------------------


def load_layout_contract(worker_dir: Path) -> dict:
    """What the worker implements of the §7 layout-seed contract.

    `{has_build_layout, default_seed, module_path}`. `default_seed` is read off
    a no-argument instance's `self.layout_seed` — the frozen convention is
    `Game(layout_seed: int | None = None)` where None IS the authored default
    and the instance records it. A `build_layout` that is present but not
    callable, or a game that claims the contract without recording its seed,
    fails here: both would make the seed validation below meaningless.
    """
    worker_dir = Path(worker_dir)
    game_path, module, game_cls, _solver_cls = _load_worker(worker_dir)
    build = getattr(module, "build_layout", None)
    if build is None:
        return {
            "has_build_layout": False,
            "default_seed": None,
            "module_path": str(game_path),
        }
    if not callable(build):
        raise ValueError(  # noqa: TRY004 — a §7 refusal, not a type error (B9 contract §1)
            f"{game_path}: build_layout is not callable (got {type(build).__name__}) — spec §7 "
            "requires `build_layout(seed) -> list[LevelLayout]`, a pure function (D13)"
        )
    # The authored-default probe CONSTRUCTS the game (contract P-1): worker
    # `__init__` code, which builds the opening layout in every game we have
    # shipped. Contained for the same reason the exec-load above is.
    probe = _run_worker_code(
        lambda: _fresh_seeded(game_cls, None),
        worker_dir=worker_dir, seed=None,
        what="constructing the game at its authored default seed",
    )
    seed = getattr(probe, "layout_seed", None)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError(  # noqa: TRY004 — an unimplemented convention, not a type error
            f"{game_path}: {game_cls.__name__}() records layout_seed={seed!r} — the §7 "
            "convention is `Game(layout_seed: int | None = None)` where None is the "
            "AUTHORED default seed and the instance records it as an int"
        )
    return {"has_build_layout": True, "default_seed": int(seed), "module_path": str(game_path)}


def _serialize_layout(build, seed: int, game_path: Path) -> str:
    """`json.dumps(build_layout(seed), sort_keys=True)` — the comparison bytes.

    THE b004 CRASH SITE (contract P-1). `build(seed)` is the worker's own pure
    function and it is the call that raised `ValueError: no winning line for
    level 4` at seed 3 and killed the b004 run. It is contained; the json
    refusal below is NOT, because a layout that will not serialize is a spec §7
    violation this stage is supposed to refuse loudly (see `rederive_layouts`).
    """
    layout = _run_worker_code(
        lambda: build(seed),
        worker_dir=Path(game_path).parent, seed=seed,
        what="re-deriving the worker's build_layout(seed)",
    )
    try:
        return json.dumps(layout, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{game_path}: build_layout({seed}) returned a structure json cannot serialize "
            f"({exc}) — spec §7 layouts are JSON-able (lists/dicts/ints/strs), which is how "
            "distinctness under seed is checked"
        ) from None


def rederive_layouts(worker_dir: Path, seeds: Sequence[int], *,
                     crashes: list | None = None) -> dict:
    """Re-derive every seed's layout and prove the §7 contract holds.

    Two assertions, both structural and both made BEFORE a single seed is
    played, because each names a different bug:

    * **same-seed determinism** — `build_layout(s)` is called twice and the
      serialized bytes must match. A layout that moves under a fixed seed is
      not a pure function and nothing downstream (the TSV, the sampler, the
      solver's own plan) replays.
    * **pairwise distinctness** — two seeds that serialize identically mean
      the seed is being ignored, which is the D13 promise unkept. This is a
      spec §7 VIOLATION, not a seed-reject: the routing differs, so the
      refusal differs.

    Returns `{seed: serialized_layout}`.

    `crashes` (contract P-1) is the CONTAINMENT seam, and it defaults to
    today's behaviour: None means a worker crash propagates (as a typed
    `WorkerCodeError` rather than the raw exception, which is the only change on
    that path). Hand it a list and a seed whose `build_layout` crashes is
    APPENDED to it as `{seed, error, site}` and left out of the returned map,
    so the other seeds are still re-derived and still proved — the run comes
    home with EVERY failing seed named instead of dying on the first. The seeds
    that did derive are still held to both assertions above; a seed with no
    layout has nothing to be distinct from and is not counted against the rest.
    """
    worker_dir = Path(worker_dir)
    game_path, module, _game_cls, _solver_cls = _load_worker(worker_dir)
    build = getattr(module, "build_layout", None)
    if build is None or not callable(build):
        raise ValueError(
            f"{game_path}: no callable build_layout — spec §7 requires layout-from-seed "
            "from birth (D13), so there is nothing to re-derive"
        )
    seed_list = list(seeds)
    if not seed_list:
        raise ValueError("rederive_layouts needs at least one seed")
    for seed in seed_list:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError(f"validation seeds must be ints, got {seed!r}")
    if len(set(seed_list)) != len(seed_list):
        raise ValueError(f"validation seeds must be distinct, got {seed_list!r}")

    layouts: dict[int, str] = {}
    for seed in seed_list:
        try:
            first = _serialize_layout(build, seed, game_path)
            second = _serialize_layout(build, seed, game_path)
        except WorkerCodeError as exc:
            if crashes is None:
                raise
            crashes.append({"seed": seed, "error": exc.note, "site": exc.site})
            continue
        if first != second:
            raise ValueError(
                f"{game_path}: build_layout({seed}) is not deterministic — two calls with "
                f"the SAME seed serialized differently ({first[:120]!r} vs {second[:120]!r}). "
                "spec §7 requires a PURE function (D13)"
            )
        layouts[seed] = first

    # Only the seeds that DERIVED (see `crashes` above): a seed whose layout
    # the worker could not build has no bytes to collide with, and claiming it
    # distinct would be a claim about a layout that does not exist.
    derived = [seed for seed in seed_list if seed in layouts]
    for index, seed in enumerate(derived):
        for other in derived[index + 1:]:
            if layouts[seed] == layouts[other]:
                raise ValueError(
                    f"{game_path}: build_layout ignores its seed — seeds {seed} and {other} "
                    "produce an IDENTICAL layout. spec §7 requires layouts structurally "
                    "distinct under seed (D13); this is a §7 violation, not a seed-reject"
                )
    return layouts


def validation_seeds(cfg: Mapping, game_id: str, default_seed: int | None) -> list[int]:
    """The seeds this game is validated at: authored default first, then derived.

    `package.seeds_validated` long (pilot ⊕ 5, architecture §3 S6). The extras
    are `sha256("<batch.seed>:<game_id>:s6:<k>")[:8]` — the same derivation
    `s4_baselines.derive_seed` uses, with the stage tag `s6` so S4's rng seed
    and S6's validation seeds never collide. Derived seeds that repeat an
    earlier one are skipped, so the list is always distinct.

    `default_seed=None` (a game with no authored seed) yields a fully derived
    list; the caller decides whether that is legal (it is not, under §7).
    """
    package = _package_config(cfg)
    wanted = package["seeds_validated"]
    batch = cfg.get("batch") if isinstance(cfg, Mapping) else None
    if not isinstance(batch, Mapping) or "seed" not in batch:
        raise ValueError("config has no 'batch.seed' — S6 cannot derive validation seeds")
    batch_seed = batch["seed"]
    if isinstance(batch_seed, bool) or not isinstance(batch_seed, int):
        raise TypeError(f"batch.seed must be an int, got {batch_seed!r}")
    if not isinstance(game_id, str) or not game_id:
        raise ValueError("game_id must be a non-empty string — the seeds are derived from it")
    if default_seed is not None and (isinstance(default_seed, bool) or
                                     not isinstance(default_seed, int)):
        raise TypeError(f"default_seed must be an int or None, got {default_seed!r}")

    seeds: list[int] = []
    if default_seed is not None:
        seeds.append(int(default_seed))
    counter = 0
    # Bounded search: every skip is a sha256 collision in 32 bits, so the
    # bound is never reached in practice and its absence would be a hang.
    while len(seeds) < wanted and counter < 10_000:
        counter += 1
        digest = hashlib.sha256(f"{batch_seed}:{game_id}:s6:{counter}".encode()).hexdigest()
        candidate = int(digest[:8], 16)
        if candidate not in seeds:
            seeds.append(candidate)
    if len(seeds) != wanted:
        raise ValueError(
            f"could not derive {wanted} distinct validation seeds for {game_id!r} in "
            f"{counter} draws — got {seeds!r}"
        )
    return seeds


# --- per-seed validation ----------------------------------------------------


def validate_seed(worker_dir: Path, seed: int | None, *, max_actions: int = MAX_ACTIONS) -> dict:
    """Drive `Game(layout_seed=seed)` with `Solver(layout_seed=seed)`.

    The §7 contract's real claim — "the solver must solve ANY seed (it
    receives the same seed)" (architecture §3 S6) — is only provable by
    playing. The drive mirrors `s4_baselines.solver_lines` (RESET, then
    `solver.next_action(fd)` until terminal / None / `max_actions`);
    it is re-derived rather than imported because S4's version takes no seed,
    refuses a non-winning line with a ValueError, and keeps per-level action
    records this stage does not need.

    Frame validity comes free: every frame is pushed through
    `frames.settled_grid`, which refuses a ragged, non-integer or
    out-of-palette board.

    Returns `{seed, win, levels_completed, actions_total, error}`. `error` is
    None exactly when the drive reached WIN; otherwise it names the cause —
    an exception, the action bound, or the terminal state it did reach. A
    losing drive is DATA here (it becomes the seed-reject verdict), not a
    crash: only a broken call (bad seed type, no solver) raises.
    """
    worker_dir = Path(worker_dir)
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise TypeError(f"seed must be an int or None, got {seed!r}")
    if max_actions < 1:
        raise ValueError(f"max_actions must be >= 1, got {max_actions}")
    # The exec-load is contained (contract P-1) and becomes THIS seed's error
    # row; the no-solver refusal below stays a raise, because it is the caller's
    # wiring and not the game's behaviour (S4 gating already required a solver,
    # so S6 never reaches it on a real slot).
    try:
        _game_path, _module, game_cls, solver_cls = _load_worker(worker_dir)
    except WorkerCodeError as exc:
        return {"seed": seed, "win": False, "levels_completed": 0,
                "actions_total": 0, "error": exc.note}
    if solver_cls is None:
        raise ValueError(
            f"{worker_dir}: S6 validates a seed by SOLVING it and this worker ships no "
            "solver.py (architecture §3 S6: the solver must solve ANY seed)"
        )

    result = {
        "seed": seed,
        "win": False,
        "levels_completed": 0,
        "actions_total": 0,
        "error": None,
    }
    try:
        game = _fresh_seeded(game_cls, seed)
        solver = solver_cls() if seed is None else solver_cls(layout_seed=int(seed))
        reset_fn = getattr(solver, "reset", None)
        if callable(reset_fn):
            reset_fn()
        if not callable(getattr(solver, "next_action", None)):
            raise TypeError(f"{solver_cls.__name__} has no callable next_action(frame_data)")

        fd = _reset(game)
        settled_grid(fd)
        performed = 0
        bounded = True
        for _ in range(max_actions):
            if fd.state in TERMINAL_STATES:
                bounded = False
                break
            action = solver.next_action(fd)
            if action is None:
                bounded = False
                break
            fd = _perform(game, action)
            performed += 1
            settled_grid(fd)
        else:
            bounded = fd.state not in TERMINAL_STATES

        result["actions_total"] = performed
        result["levels_completed"] = int(fd.levels_completed)
        result["win"] = fd.state is GameState.WIN
        if not result["win"]:
            if bounded:
                result["error"] = (
                    f"the solver line hit the max_actions={max_actions} bound after "
                    f"{performed} action(s) with {result['levels_completed']} level(s) "
                    "completed"
                )
            else:
                result["error"] = (
                    f"the solver line ended {fd.state.name} after {performed} action(s) "
                    f"with {result['levels_completed']} level(s) completed"
                )
    except WorkerCodeError as exc:   # the construction leg, already contained
        result["error"] = exc.note
    except Exception as exc:  # noqa: BLE001 — a crash under a seed IS the finding
        # Contract P-1 adds the SITE to a record that already named the class
        # and the message: the b004 lesson is that "ValueError: no winning line
        # for level 4" sends nobody to a line of the game's own file.
        result["error"] = (
            f"{type(exc).__name__}: {exc} (at {_worker_site(exc, worker_dir)})"
        )
    return result


# --- provenance hashes (architecture §2 ⊕) ----------------------------------


def game_hash(worker_dir: Path) -> str:
    """`sha(game.py + solver.py)` — the provenance chain's game hash.

    Literal concatenation of the two files' bytes, in that order. A worker
    without `solver.py` hashes the game alone (officials ship no solver);
    S6 itself never reaches that case, since S4 gating already required one.
    """
    worker_dir = Path(worker_dir)
    digest = hashlib.sha256()
    digest.update(game_source_path(worker_dir).read_bytes())
    solver_path = solver_source_path(worker_dir)
    if solver_path is not None:
        digest.update(solver_path.read_bytes())
    return digest.hexdigest()


def spec_hash(spec_path: Path | None) -> str | None:
    """`sha(spec.yaml)`, or None when no spec is supplied (flagged in the manifest)."""
    if spec_path is None:
        return None
    path = Path(spec_path)
    if not path.is_file():
        raise ValueError(f"spec not found: {path} — spec_hash is a provenance fact (§2 ⊕)")
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- the TSV emitter (adapted from capture_frames.py) -----------------------


def _observation(settled) -> str:
    """`str(settled.tolist())` in the reference; ours is a tuple-of-tuples."""
    return str([list(row) for row in settled])


def _tsv_row(*, step, settled, fd, level, action, reward, terminated, game_id, slug, t) -> dict:
    """One row in the sprite_lib_v2 dialect (adapted `capture_frames._tsv_row`).

    `action` is `(action_id, data)` for an action row, None for the terminal
    row. `settled`/`fd` are the PRE-action state (the SARS convention);
    `reward`/`terminated` are the RESULT of that action.
    """
    state = getattr(fd.state, "name", str(fd.state))
    frame_data = {
        "game_id": game_id,
        "guid": f"{GUID_PREFIX}{slug}",
        "frame": [np.asarray(f).tolist() for f in fd.frame] if fd.frame else [],
        "state": state,
        "levels_completed": int(fd.levels_completed),
        "win_levels": int(getattr(fd, "win_levels", 0) or 0),
        "full_reset": bool(getattr(fd, "full_reset", False)),
        "available_actions": [int(a) for a in (getattr(fd, "available_actions", []) or [])],
    }
    inner = {
        "frame": [list(row) for row in settled] if settled is not None else [],
        "frame_data": json.dumps(frame_data, separators=(",", ":")),
        "timestep": t,
        "trajectory_step": t,
    }
    terminal = action is None
    if terminal:
        action_cell = ""
    else:
        action_id, data = action
        verb = TSV_VERBS.get(action_id, f"ACTION{action_id}")
        # Only the mouse verb carries coordinates, and `operation_tracking.py:33`
        # accepts them under exactly this spelling + exactly these two keys.
        payload = {"x": data.get("x"), "y": data.get("y")} if verb == "CLICK" else {}
        action_cell = json.dumps([verb, payload])
    return {
        "step": step,
        "observation": _observation(settled) if settled is not None else "",
        "info": json.dumps({"arc_frame": json.dumps(inner, separators=(",", ":"))}),
        "level": level,
        "action_valid": "" if terminal else True,
        "duration": "" if terminal else TSV_DURATION,
        "action": action_cell,
        "reward": reward,
        "terminated": terminated,
        "truncated": False,
        "explore_exploit": "", "world_model_path": "", "goal": "", "exploration_output": "",
    }


def _write_tsv(path: Path, rows: Sequence[Mapping]) -> None:
    """Header + rows, tab-separated, `\\n` endings, UTF-8 (adapted `_write_tsv`)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("\t".join(TSV_COLUMNS) + "\n")
        for row in rows:
            fh.write("\t".join(str(row[column]) for column in TSV_COLUMNS) + "\n")


def load_action_line(s4_dir: Path, levels: int) -> list[dict]:
    """S4's `actions/level-<i>.json`, flattened into one replayable line.

    Every baselined level must have a file and every file must be a non-empty
    list of action records: a package whose TSV covers four of six levels is
    not the game's level-set (architecture §2 tree: `package/tsv/level-set.tsv`).
    """
    actions_dir = Path(s4_dir) / ACTIONS_DIRNAME
    line: list[dict] = []
    for index in range(1, levels + 1):
        path = actions_dir / f"level-{index}.json"
        if not path.is_file():
            raise ValueError(
                f"missing {path} — S4 baselined {levels} level(s), so the packager needs "
                f"level-1..{levels}.json to replay the whole level-set (architecture §2)"
            )
        records = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(records, list) or not records:
            raise ValueError(f"{path}: expected a non-empty list of action records")
        for record in records:
            if not isinstance(record, Mapping) or "id" not in record:
                raise ValueError(f"{path}: bad action record {record!r} (needs an 'id')")
            line.append(dict(record))
    return line


def emit_tsv(worker_dir: Path, s4_dir: Path, out_path: Path, *, layout_seed: int | None) -> Path:
    """Replay the solver line and write the level-set TSV.

    `layout_seed` is the layout the line was recorded against — `run_s6`
    passes the AUTHORED seed, which is the one S4 drove, and None means the
    game's own default (§7). Replaying at any other seed would be a lie
    dressed as a trajectory, so the replay is refused unless it WINs on
    exactly the recorded actions.

    One row per replayed action (SARS: observation/info are the PRE-action
    state, reward/terminated the result) plus the blank-action terminal row —
    the shape that scored 8/8 structural parity against the sprite_lib_v2 reference file
    (trajectory-contract §4). Byte-stable: no clocks, no paths, no rng.
    """
    worker_dir = Path(worker_dir)
    s4_dir = Path(s4_dir)
    out_path = Path(out_path)
    metadata = load_battery_metadata(s4_dir / S4_METADATA_NAME)
    levels = len(metadata["baseline_actions"])
    line = load_action_line(s4_dir, levels)

    slug = _slug(worker_dir)
    game_id = f"{slug}-{game_hash(worker_dir)[:8]}"
    _game_path, _module, game_cls, _solver_cls = _load_worker(worker_dir)
    game = _fresh_seeded(game_cls, layout_seed)

    fd = _reset(game)
    previous = {"settled": settled_grid(fd), "fd": fd, "levels": int(fd.levels_completed)}
    rows: list[dict] = []
    won_at = None
    last_step = 0
    for step, record in enumerate(line, start=1):
        if fd.state in TERMINAL_STATES:
            raise ValueError(
                f"{worker_dir}: the game was already {fd.state.name} at action #{step} of "
                f"{len(line)} — actions/level-*.json does not describe this replay"
            )
        action = _action_from_record(record)
        fd = _perform(game, action)
        if not fd.frame:
            raise ValueError(
                f"{worker_dir}: action #{step} returned no frame — the line kept playing "
                "past a terminal state"
            )
        settled = settled_grid(fd)
        completed = int(fd.levels_completed)
        state = getattr(fd.state, "name", str(fd.state))
        reward = 1 if (completed > previous["levels"] or state == "WIN") else 0
        rows.append(_tsv_row(
            step=step, settled=previous["settled"], fd=previous["fd"],
            level=previous["levels"] + 1,
            action=(int(action.id.value), dict(action.data or {})),
            reward=reward, terminated=(state == "WIN"),
            game_id=game_id, slug=slug, t=step - 1,
        ))
        last_step = step
        previous = {"settled": settled, "fd": fd, "levels": completed}
        if state == "WIN":
            won_at = step
            break

    if won_at is None:
        raise ValueError(
            f"{worker_dir}: replaying {len(line)} action(s) at layout_seed={layout_seed!r} "
            f"ended {getattr(fd.state, 'name', fd.state)} with {previous['levels']} level(s) "
            "completed, not WIN — the TSV would record a line that does not win"
        )
    if won_at != len(line):
        raise ValueError(
            f"{worker_dir}: the replay won at action #{won_at} with {len(line) - won_at} "
            "action(s) left over — actions/level-*.json is not this game's winning line"
        )

    # Terminal row: final state, blank action, the step number repeated, win
    # reward echoed (`capture_frames.capture`, the emit_tsv tail). reward/
    # terminated are literal 1/True because the two guards above already
    # proved this replay reached WIN.
    rows.append(_tsv_row(
        step=last_step, settled=previous["settled"], fd=previous["fd"],
        level=previous["levels"] + 1, action=None, reward=1, terminated=True,
        game_id=game_id, slug=slug, t=last_step,
    ))
    _write_tsv(out_path, rows)
    return out_path


def tsv_stats(path: Path, rows_written: int) -> dict:
    """What the CLI prints and the report records about the emitted file."""
    data = Path(path).read_bytes()
    return {
        "rows": rows_written,
        "action_rows": rows_written - 1,
        "terminal_rows": 1,
        "columns": len(TSV_COLUMNS),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


# --- the duck-intake mirror (C-5) -------------------------------------------


def duck_intake_rel(slug: str) -> Path:
    """`package/duck-intake/<slug>_perfect/human_policy/unprocessed_game.tsv`.

    Relative to the S6 OUT DIR, which is the frame the contract spells the
    mirror in (`worker.s6/package/duck-intake/…`) and the frame that composes
    with `manifest.paths.out_dir`, the one absolute anchor in the same dict. So
    `manifest.paths.duck_intake` stays free of a machine-specific absolute path
    while still being resolvable from the manifest alone.
    """
    if not isinstance(slug, str) or not slug:
        raise ValueError(f"slug must be a non-empty string, got {slug!r}")
    return (
        Path(PACKAGE_DIRNAME)
        / DUCK_INTAKE_DIRNAME
        / f"{slug}{DUCK_INTAKE_QUALIFIER}"
        / DUCK_INTAKE_POLICY
        / DUCK_INTAKE_NAME
    )


def write_duck_intake(tsv_path: Path, out_dir: Path, slug: str) -> Path:
    """Copy the emitted level-set TSV to the consumer's own intake path.

    A BYTE-IDENTICAL second copy, never a re-emission: the bytes are read back
    from the file `emit_tsv` just wrote, so the two locations cannot drift and
    determinism is inherited rather than re-argued (no clocks, no paths, no rng
    enter here). `tsv/level-set.tsv` remains the canonical corpus artifact; this
    is the zero-renaming intake surface described at DUCK_INTAKE_DIRNAME.
    """
    data = Path(tsv_path).read_bytes()
    target = Path(out_dir) / duck_intake_rel(slug)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def _clear_duck_intake(out_dir: Path, slug: str) -> list[str]:
    """Remove a stale mirror file on a reject. Never creates, never rmtree."""
    target = Path(out_dir) / duck_intake_rel(slug)
    if target.is_file():
        target.unlink()
        return [str(target)]
    return []


def _reward_ones(path: Path) -> int:
    """The number of 1-reward rows in an emitted TSV (§6 Q5 evidence)."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    column = TSV_COLUMNS.index("reward")
    return sum(1 for line in lines[1:] if line.split("\t")[column] == "1")


# --- the play mirror --------------------------------------------------------


def play_metadata(
    slug: str,
    game_hash8: str,
    baselines: Sequence,
    *,
    title_suffix: str = "",
) -> dict:
    """The play server's `metadata.json` payload — the ONE place its shape lives.

    The server reads `game_id`, `title`, `baseline_actions` (its level count) and
    `default_fps` (`arc-agi-3-games/tools/play/server.py:101-116`); `tags` is
    ours, naming where the game came from. Separators become spaces in the title
    first: the title is what the play menu shows, and "S6 Seeded" reads as a name
    where "S6_Seeded" reads as a filename.

    EXTRACTED, not added (contract P-3): `_write_play_dir` built this dict inline
    until the shelf needed the same one. Two writers of one consumer's shape is
    exactly the drift `_write_play_dir`'s own docstring refuses for the preview,
    so the promoted `games/<slug>/game/metadata.json` and the `out/play/` mirror
    come from this function or from neither. The out/ bytes are unchanged: same
    dict, same key order, same `_write_json`.
    """
    if not isinstance(slug, str) or not slug:
        raise ValueError(f"slug must be a non-empty string, got {slug!r}")
    if not isinstance(game_hash8, str) or len(game_hash8) != 8:
        raise ValueError(f"game_hash8 must be an 8-char digest prefix, got {game_hash8!r}")
    if not isinstance(baselines, Sequence) or isinstance(baselines, (str, bytes)) or not baselines:
        raise ValueError(f"baseline_actions must be a non-empty sequence, got {baselines!r}")
    if not isinstance(title_suffix, str):
        raise TypeError(f"title_suffix must be a string, got {type(title_suffix).__name__}")
    return {
        "game_id": f"{slug}-{game_hash8}",
        "title": slug.replace("_", " ").replace("-", " ").title() + title_suffix,
        "tags": list(PLAY_TAGS),
        "baseline_actions": [int(value) for value in baselines],
        "default_fps": PLAY_DEFAULT_FPS,
    }


def _write_play_dir(
    worker_dir: Path,
    metadata: Mapping,
    *,
    game_hash8: str,
    play_root: Path | None,
    title_suffix: str = "",
) -> Path:
    """The ONE writer of a `<root>/<slug>/<hash8>/` play dir.

    Shared, never duplicated, by the packaging mirror (`write_play_mirror`, no
    suffix) and the review preview (`write_play_preview`, contract D-2): both
    builds must land in the SAME layout with the SAME keys, or the preview would
    be a second dialect of the thing the play server consumes. `title_suffix` is
    the only difference the two are allowed to have, and it is PRIVATE on
    purpose — the packaged mirror must never be able to ask for one.
    """
    worker_dir = Path(worker_dir)
    if not isinstance(metadata, Mapping):
        raise TypeError(f"metadata must be a mapping, got {type(metadata).__name__}")
    baselines = metadata.get("baseline_actions")
    if not isinstance(baselines, list) or not baselines:
        raise ValueError(f"metadata.baseline_actions must be a non-empty list, got {baselines!r}")
    if not isinstance(game_hash8, str) or len(game_hash8) != 8:
        raise ValueError(f"game_hash8 must be an 8-char digest prefix, got {game_hash8!r}")

    slug = _slug(worker_dir)
    root = Path(play_root) if play_root is not None else PLAY_ROOT
    target = root / slug / game_hash8
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{slug}.py").write_bytes(game_source_path(worker_dir).read_bytes())
    _write_json(
        target / S4_METADATA_NAME,
        play_metadata(slug, game_hash8, baselines, title_suffix=title_suffix),
    )
    return target


def write_play_mirror(
    worker_dir: Path,
    metadata: Mapping,
    *,
    game_hash8: str,
    play_root: Path | None = None,
) -> Path:
    """Mirror the game into the officials' `<root>/<slug>/<hash>/` layout.

    That layout is not decoration: the play server discovers games with
    `glob(<root>/*/*/metadata.json)` and loads the first `*.py` beside the
    metadata it finds (`arc-agi-3-games/tools/play/server.py:101-116`), reading
    `game_id`, `title`, `baseline_actions` (its level count) and `default_fps`
    from it. Writes land under `out/play/` or the caller's `play_root`, and
    nowhere else. A mirror for the same slug+hash is overwritten — same bytes.

    That overwrite is also how contract D-2's preview is retired: this pass
    writes the same two files, at the same `<slug>/<hash8>/`, with the title
    UNSUFFIXED, so an accepted game's menu entry stops saying "review pending"
    without anything having to delete it first.
    """
    return _write_play_dir(worker_dir, metadata, game_hash8=game_hash8, play_root=play_root)


# --- the review preview (contract D-2) --------------------------------------

# What the reviewer's build is called in the play menu. §4 halts every slot at
# `played` for a human verdict, and until D-2 the mirror was written one edge
# LATER (`reviewed --> packaged`), so the reviewer never had a playable build
# from the machine. The suffix is not decoration: the menu title is the only
# field that can tell a reviewer WHICH build they are looking at, and a preview
# of a game that may yet be pulled must not read as a packaged one.
PREVIEW_TITLE_SUFFIX = " (review pending)"


def write_play_preview(
    worker_dir: Path,
    s4_dir: Path,
    cfg: Mapping,
    play_root: Path | None = None,
) -> Path:
    """The reviewer's playable build, written at `baselined --> played`.

    Same machinery, same layout, same metadata keys as the packaging mirror
    (`_write_play_dir` is literally the same writer) — the one difference is the
    title suffix. STANDING behavior: there is no knob, so nothing here consults
    `cfg`; it rides the signature for parity with `run_s6(worker_dir, cfg, …)`
    and is type-checked rather than ignored.

    The S4 metadata is loaded through `load_battery_metadata`, the same gate
    `run_s6` step 1 applies, so a preview exists only for a game S4 baselined
    `fit` — the reviewer is never handed a build the machine would refuse to
    package.

    VERIFIED, not re-argued: the packaging pass overwrites this exact dir. Both
    passes derive `<slug>` from the same worker dir and `<hash8>` from the same
    `sha(game.py + solver.py)`, which no edge between `played` and `packaged`
    touches (the review is a human decision, not a build), and
    `_write_play_dir` truncates both files under `mkdir(exist_ok=True)`. So an
    accept leaves ONE dir carrying the clean title, and only a pull has to
    withdraw anything.
    """
    if not isinstance(cfg, Mapping):
        raise TypeError(f"cfg must be a mapping, got {type(cfg).__name__}")
    worker_dir = Path(worker_dir)
    metadata = load_battery_metadata(Path(s4_dir) / S4_METADATA_NAME)
    return _write_play_dir(
        worker_dir, metadata, game_hash8=game_hash(worker_dir)[:8],
        play_root=play_root, title_suffix=PREVIEW_TITLE_SUFFIX,
    )


def _clear_play_mirror(worker_dir: Path, game_hash8: str, play_root: Path | None) -> list[str]:
    """Remove a stale mirror's two files on a reject. Never creates, never rmtree."""
    slug = _slug(Path(worker_dir))
    root = Path(play_root) if play_root is not None else PLAY_ROOT
    target = root / slug / game_hash8
    removed = []
    for name in (f"{slug}.py", S4_METADATA_NAME):
        path = target / name
        if path.is_file():
            path.unlink()
            removed.append(str(path))
    return removed


def withdraw_play_preview(
    worker_dir: Path,
    game_hash8: str,
    play_root: Path | None = None,
) -> list[str]:
    """Pull a review preview when the review says no (`reviewed --> pulled`).

    `_clear_play_mirror` under the name the pull path calls it by — the SAME
    removal semantics the seed-reject path already relies on, deliberately
    reused rather than re-implemented: the two files are unlinked if they are
    there, the directory itself is never removed and nothing is ever created.
    Returns the paths actually removed, which is what the pull records.

    A preview that was never written (the note-artifact path, a hand-cleaned
    tree) withdraws as an empty list, not as an error: there is nothing to
    withdraw, and saying otherwise would be a claim about a file that is not
    there.
    """
    return _clear_play_mirror(Path(worker_dir), game_hash8, play_root)


def play_command(cfg: Mapping, play_root: Path) -> dict:
    """The operator's one-liner: `arc-games play --root <play_root>`.

    PIN UPDATE / BEHAVIOUR CHANGE, contract H-1 item 4 (2026-10-06). This was
    `PLAY_GAMES_DIR=<root> <duckWM python> <.../arc-agi-3-games/tools/play/
    server.py>`, resolved from the config's `duckwm_docs`. It named a checkout
    this repo no longer needs and a command no operator has typed since
    contract P-4: L-2 vendored the player to `tools/play/` and P-4 gave it a
    subcommand, so the hint a packaged game prints is now the command that
    exists. PRINTED, NEVER EXECUTED — nothing here starts a server.

    THE KEYS ARE UNCHANGED (`main`'s missing-player note and the S6 report's
    `play` block both read them) and every one of them now describes the player
    `arc-games play` would actually start, because `cli.play_player` is the ONE
    place that choice is made (vendored copy on this interpreter; duckWM's venv
    only for the sibling fallback). Imported inside the function for this
    module's standing reason — the import must not run when it is not needed —
    and because `gen.cli` imports `gen.orchestrator` at module scope.

    `cfg` is kept in the signature (two call sites and the D-2 pins pass it)
    and is now unread: the recipe is a fact about this repo and the play root,
    not about the batch.
    """
    from .cli import PROG, play_player

    player = play_player()
    server = player["server"]
    interpreter = player["interpreter"]
    return {
        "command": f"{PROG} play --root {Path(play_root)}",
        "server": str(server) if server is not None else None,
        "python": interpreter,
        "server_exists": server is not None and Path(server).is_file(),
        "python_exists": Path(interpreter).exists(),
    }


# --- the shared shelf: games/ (contract P-3) ---------------------------------
#
# WHY A SECOND TREE EXISTS. `out/` is this repo's RUNTIME surface and .gitignore
# ignores `out/*`, so nothing a run writes is shareable: a teammate who clones
# gets the pipeline and none of the games. OPERATOR RULING (docs/v2/DECISIONS.md,
# 2026-09-29, "Games home: games/ tracked in git"): approved games live in a
# tracked top-level `games/<slug>/`, sharing IS `git pull`, local runs keep
# writing `out/`, and ONLY promoted games enter `games/`.
#
# WHAT PROMOTION IS, exactly: a COPY of an already-packaged tree plus one
# rewritten manifest. Nothing here emits a TSV, drives worker code, validates a
# seed or decides a verdict — `run_s6` did all of that, and a promoter that
# re-derived any of it could disagree with the package it claims to be. So the
# shelf can only ever hold bytes `out/` already holds, and a package whose
# verdict is not `packaged` is refused rather than filtered.
#
# THE LAYOUT, and why it is one level deeper than `games/<slug>/`. The play
# server discovers games with `glob(<root>/*/*/metadata.json)` and loads the
# FIRST `*.py` beside the metadata it finds (`arc-agi-3-games/tools/play/
# server.py:102-106`). A `metadata.json` sitting directly in `games/<slug>/` is
# one level too shallow for that glob, so a shelf entry that is playable with
# `PLAY_GAMES_DIR=games` needs a build dir between them. The contract (P-3 §1)
# offers `<hash8>` or the literal `"game"`; this picks the LITERAL, for two
# reasons that are not aesthetic:
#   1. ONE canonical copy of `game.py`. It has to sit beside `metadata.json` for
#      the server's loader, so putting the WHOLE entry in the build dir leaves
#      nothing duplicated — no second copy under `games/<slug>/` that can drift.
#   2. `games/` is TRACKED. A hash-named dir turns every re-promotion of an
#      edited game into a delete+add of the whole entry in git history; the
#      literal makes it an in-place content change, which is what a `git pull`
#      should show a teammate.
# The hash is not lost: it is `game_hash` in the promoted manifest and the
# `<hash8>` tail of `metadata.game_id`, exactly as in the `out/play` mirror.
GAMES_DIRNAME = "games"
GAMES_ROOT = REPO_ROOT / GAMES_DIRNAME
GAMES_BUILD_DIRNAME = "game"          # games/<slug>/game/ — see above
GAME_MODULE_NAME = "game.py"          #   game.py        (the packaged build's bytes)
SPEC_NAME = "spec.yaml"               #   spec.yaml      (the spec it was built from)
PROMOTION_CONTRACT = "P-3"

# The `paths` rewrite, stated as a rule and CARRIED IN THE FILE. The out/
# manifest embeds absolute machine paths on purpose (it is an operator record of
# one machine's run); a shared shelf entry cannot, or a teammate's `git pull`
# lands a manifest pointing into someone else's home directory. So every entry is
# either relativized to the build dir or nulled, and the promoted manifest says
# which rule applied to what in its own `paths_note` — a reader never has to
# infer the rule from the values.
PROMOTED_PATHS_NOTE = (
    "contract P-3: every path is RELATIVE to the build dir holding this "
    "manifest's own package/ (games/<slug>/game/). Entries whose referent is not "
    "part of the promoted tree are null: `worker` (the local build tree), "
    "`s4_metadata` (S4's baseline record), `play_mirror` (the out/play mirror) "
    "and `report` (the operator's s6-report.json) all stay in out/, which is "
    "gitignored. `game` and `metadata` name the two promoted files the out/ "
    "manifest has no key for. The out/ manifest itself is untouched and keeps "
    "its absolute paths."
)


def _shelf_slug(slug: str) -> str:
    """A slug safe to name a directory this module will `rmtree`.

    Promotion and withdrawal both remove `games/<slug>/` whole, so the slug has
    to be ONE path component. Every caller today goes through `game_slug`, which
    derives it from a directory NAME and so cannot hold a separator — which is
    exactly why the check is cheap and belongs here, at the boundary that does
    the removing, rather than in a review of whoever calls next.
    """
    if not isinstance(slug, str) or not slug:
        raise ValueError(f"slug must be a non-empty string, got {slug!r}")
    if slug != Path(slug).name or slug in (".", ".."):
        raise ValueError(
            f"slug {slug!r} is not a single path component — games/<slug>/ is a directory this "
            "module removes whole, so a separator or a traversal in the slug is refused"
        )
    return slug


def _shelf_dirs(slug: str, games_root: Path | None) -> tuple[Path, Path, Path]:
    """`(shelf_root, games/<slug>/, games/<slug>/game/)`."""
    root = Path(games_root) if games_root is not None else GAMES_ROOT
    slug_dir = root / _shelf_slug(slug)
    return root, slug_dir, slug_dir / GAMES_BUILD_DIRNAME


def game_slug(worker_dir: Path) -> str:
    """The shelf slug for a worker dir — the promoter's own derivation, EXPORTED.

    WHY THIS IS PUBLIC. The orchestrator's pull path carries the LEDGER slot key
    (`b003r2-simplicity-s001`), not the game slug (`conduit-watch`), and
    `withdraw_game` is named after the game — architecture §2's
    `corpus/<batch>/<slug>/`. A caller that guessed at that name would withdraw
    NOTHING and report success, which is the one failure mode a withdrawal must
    not have. So the derivation `promote_game` writes under is the derivation
    callers get, rather than a second copy of the convention. Pure naming: it
    reads no files, so it still answers for a tree that has already been removed.
    """
    return _shelf_slug(_slug(Path(worker_dir)))


def shelf_entry_hash(slug: str, games_root: Path | None = None) -> str | None:
    """The `game_hash` of the build currently on the shelf, or None if there is none.

    Read off the promoted manifest, which is the only record of WHICH build an
    entry holds. A shelf dir with no manifest, or one that will not parse, answers
    None: something is there but it does not identify itself, and the caller's
    business is whether the incoming hash matches, not repairing rubble.
    """
    _root, slug_dir, _game_dir = _shelf_dirs(slug, games_root)
    manifest = slug_dir / GAMES_BUILD_DIRNAME / PACKAGE_DIRNAME / MANIFEST_NAME
    if not manifest.is_file():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    digest = payload.get("game_hash")
    return digest if isinstance(digest, str) else None


def _promoted_paths(slug: str) -> dict:
    """The out/ manifest's `paths` block, rewritten for the shelf.

    Every key the out/ manifest can carry is named here — relativized to the
    build dir, or None when its referent is not promoted (PROMOTED_PATHS_NOTE
    spells which and why). Derived from the same constants the writer uses, so
    the values cannot drift from the tree `promote_game` actually lays down.
    """
    return {
        "worker": None,
        "out_dir": ".",
        "s4_metadata": None,
        "spec": SPEC_NAME,
        "tsv": (Path(PACKAGE_DIRNAME) / TSV_DIRNAME / TSV_NAME).as_posix(),
        "manifest": (Path(PACKAGE_DIRNAME) / MANIFEST_NAME).as_posix(),
        "duck_intake": duck_intake_rel(slug).as_posix(),
        "play_mirror": None,
        "report": None,
        "game": GAME_MODULE_NAME,
        "metadata": S4_METADATA_NAME,
    }


def _rewrite_paths(paths: Mapping, slug: str) -> dict:
    """`_promoted_paths`, with two refusals that keep the shelf machine-free.

    An UNKNOWN key in the source manifest is a refusal, not a pass-through: the
    out/ manifest's values are absolute machine paths, so a `paths` key this
    function has not been taught to classify would be copied onto the shelf
    verbatim and ship someone's home directory to the whole team. A new key is a
    one-line addition to `_promoted_paths`; forgetting is loud.

    The second refusal is the promoter checking its OWN output: no produced value
    may be absolute or contain the repo root. That is the contract's acceptance
    (P-3 §Blind T2) asserted at the write, so a bad rule cannot reach disk and
    wait for a test to find it.
    """
    if not isinstance(paths, Mapping):
        raise TypeError(f"manifest 'paths' must be a mapping, got {type(paths).__name__}")
    promoted = _promoted_paths(slug)
    unknown = sorted(set(paths) - set(promoted))
    if unknown:
        raise ValueError(
            f"manifest 'paths' carries key(s) {unknown} with no P-3 rewrite rule — the out/ "
            "manifest's values are ABSOLUTE machine paths, so an unclassified key would be "
            "copied onto the shared shelf as-is. Add it to s6_package._promoted_paths."
        )
    for key, value in promoted.items():
        if value is None:
            continue
        if value.startswith("/") or str(REPO_ROOT) in value:
            raise AssertionError(
                f"P-3 rewrite produced a machine path for {key!r}: {value!r} — a promoted "
                "manifest must be resolvable on any clone (contract P-3 §1)"
            )
    return promoted


def _clear_shelf_entry(slug_dir: Path, game_digest: str, games_root: Path | None) -> dict | None:
    """Remove an existing `games/<slug>/` and report what was there.

    IDEMPOTENCE IS A REPLACE, stated: promotion always removes the slug dir
    before writing, so the entry that lands depends only on the worker and its
    package — never on what happened to be on the shelf. Re-promoting the same
    `game_hash` therefore rewrites byte-identically, and a DIFFERENT hash cannot
    leave half of the old build behind (contract P-3 §1's two idempotence
    clauses are the same mechanism).

    None means there was nothing to replace. A slug dir that is not a directory
    is a refusal: this function removes trees, and a file sitting where the shelf
    expects a directory is a defect to be looked at, not cleaned up silently.
    """
    if not slug_dir.exists():
        return None
    if not slug_dir.is_dir():
        raise NotADirectoryError(
            f"{slug_dir} exists and is not a directory — the shelf holds one directory per "
            "slug (contract P-3 §1); nothing was removed"
        )
    previous = shelf_entry_hash(slug_dir.name, games_root)
    removed = sorted(str(path) for path in slug_dir.rglob("*") if path.is_file())
    shutil.rmtree(slug_dir)
    return {
        "game_hash": previous,
        "same_game_hash": previous == game_digest,
        "removed": removed,
    }


def promote_game(
    worker_dir: Path,
    cfg: Mapping,
    *,
    spec_path: Path | None = None,
    out_dir: Path | None = None,
    games_root: Path | None = None,
) -> dict:
    """Put one PACKAGED game on the shared shelf: `games/<slug>/game/`.

    Four entries, and no fifth (contract P-3 §1):

        games/<slug>/game/
        ├── game.py                    the packaged build's bytes (worker/game.py)
        ├── spec.yaml                  the spec those bytes were built from
        ├── metadata.json              the play server's record (`play_metadata`)
        └── package/                   manifest + tsv + duck-intake COPIES
            ├── manifest.json          the out/ manifest with `paths` RELATIVIZED
            ├── tsv/level-set.tsv
            └── duck-intake/<slug>_perfect/human_policy/unprocessed_game.tsv

    Everything is COPIED from `<worker>.s6/package/`; the only file whose bytes
    differ from `out/` is `manifest.json`, whose absolute `paths` are rewritten
    (`_rewrite_paths`) and annotated (`paths_note`). The out/ manifest is NOT
    touched — it is one machine's operator record and stays that way.

    REFUSALS, all loud, all about provenance rather than taste: no package, a
    verdict other than `packaged`, a manifest whose `slug` disagrees with the
    dir, a `game_hash` that no longer matches the worker's bytes (the build moved
    after packaging, so the shelf would carry a manifest describing other bytes),
    a missing `spec.yaml`, a `spec_hash` that disagrees with it, and a
    duck-intake copy whose bytes are not the canonical TSV's.

    `cfg` rides the signature for parity with `run_s6(worker_dir, cfg, …)` and is
    type-checked rather than ignored; NOTHING here reads it, exactly as
    `write_play_preview` documents for itself. Promotion has no tunables: the
    shelf's shape is the play server's and the contract's, not a config's.

    IDEMPOTENT (`_clear_shelf_entry`): the slug dir is replaced wholesale, so a
    re-promotion of the same `game_hash` rewrites identically and a different one
    replaces the entry and says so in `replaced`.
    """
    if not isinstance(cfg, Mapping):
        raise TypeError(f"cfg must be a mapping, got {type(cfg).__name__}")
    worker_dir = Path(worker_dir).resolve()
    if not worker_dir.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker_dir}")

    target = (Path(out_dir) if out_dir is not None
              else worker_dir.parent / (worker_dir.name + OUT_SUFFIX)).resolve()
    package_dir = target / PACKAGE_DIRNAME
    manifest_path = package_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(
            f"no packaged manifest at {manifest_path} — promotion COPIES an S6 package onto the "
            f"shelf and never builds one; run gen/s6_package.py over {worker_dir} first "
            "(contract P-3 §1)"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping):
        raise ValueError(  # noqa: TRY004 — a provenance refusal, not a type error (B9 §1)
            f"{manifest_path}: expected a manifest object, got {type(manifest).__name__}"
        )
    verdict = manifest.get("verdict")
    if verdict != VERDICT_PACKAGED:
        raise ValueError(
            f"{manifest_path}: verdict is {verdict!r}, not {VERDICT_PACKAGED!r} — only promoted "
            "games enter games/ (operator ruling, docs/v2/DECISIONS.md 2026-09-29)"
        )

    slug = _shelf_slug(_slug(worker_dir))
    if manifest.get("slug") != slug:
        raise ValueError(
            f"{manifest_path}: manifest slug {manifest.get('slug')!r} is not the worker's slug "
            f"{slug!r} — the shelf entry is named after the game, and a mismatch means this "
            "package is not this worker's (architecture §2 corpus tree)"
        )
    game_digest = game_hash(worker_dir)
    if manifest.get("game_hash") != game_digest:
        raise ValueError(
            f"{manifest_path}: manifest game_hash {str(manifest.get('game_hash'))[:8]}… is not "
            f"the worker's {game_digest[:8]}… — the build moved after it was packaged, so "
            "promoting now would shelve a manifest that describes other bytes. Re-run S6."
        )

    spec = Path(spec_path) if spec_path is not None else worker_dir.parent / SPEC_NAME
    if not spec.is_file():
        raise ValueError(
            f"no {SPEC_NAME} at {spec} — a shelf entry carries the spec its bytes were built "
            "from (contract P-3 §1); pass spec_path= when the spec lives elsewhere"
        )
    spec_digest = spec_hash(spec)
    recorded_spec = manifest.get("spec_hash")
    if recorded_spec is not None and recorded_spec != spec_digest:
        raise ValueError(
            f"{spec}: sha {spec_digest[:8]}… is not the packaged spec_hash "
            f"{str(recorded_spec)[:8]}… — the spec changed after packaging, so the shelf would "
            "pair these bytes with a spec they were not built from (architecture §2 ⊕)"
        )

    s4_dir = worker_dir.parent / (worker_dir.name + S4_OUT_SUFFIX)
    s4_metadata = load_battery_metadata(s4_dir / S4_METADATA_NAME)
    baselines = [int(value) for value in s4_metadata["baseline_actions"]]
    metadata = play_metadata(slug, game_digest[:8], baselines)

    tsv_src = package_dir / TSV_DIRNAME / TSV_NAME
    intake_rel = duck_intake_rel(slug)
    intake_src = target / intake_rel
    for src in (tsv_src, intake_src):
        if not src.is_file():
            raise ValueError(
                f"packaged manifest says {VERDICT_PACKAGED} but {src} is missing — the shelf "
                "copies the package's own files and cannot invent one (contract P-3 §1)"
            )
    tsv_bytes = tsv_src.read_bytes()
    if intake_src.read_bytes() != tsv_bytes:
        raise ValueError(
            f"{intake_src} is not a byte-identical copy of {tsv_src} — S6 writes the mirror FROM "
            "the canonical file's bytes (C-5), so a difference means the package was edited by "
            "hand and neither copy can be trusted onto the shelf"
        )

    promoted_manifest = {
        **dict(manifest),
        "paths": _rewrite_paths(manifest.get("paths") or {}, slug),
        "paths_note": PROMOTED_PATHS_NOTE,
        "promotion": {
            "contract": PROMOTION_CONTRACT,
            # Relative to the SHELF ROOT, never to a machine: `games/` is the
            # default root and a test's tmp root is still `<slug>/game` inside it.
            "shelf_entry": f"{slug}/{GAMES_BUILD_DIRNAME}",
            # A directory NAME, not a path — the batch the slot sat in, which is
            # the only breadcrumb back to `out/corpus/` that costs no machine path.
            "source_batch": worker_dir.parent.parent.name,
        },
    }

    _root, slug_dir, game_dir = _shelf_dirs(slug, games_root)
    replaced = _clear_shelf_entry(slug_dir, game_digest, games_root)
    game_dir.mkdir(parents=True, exist_ok=True)
    (game_dir / GAME_MODULE_NAME).write_bytes(game_source_path(worker_dir).read_bytes())
    (game_dir / SPEC_NAME).write_bytes(spec.read_bytes())
    _write_json(game_dir / S4_METADATA_NAME, metadata)
    _write_json(game_dir / PACKAGE_DIRNAME / MANIFEST_NAME, promoted_manifest)
    tsv_dst = game_dir / PACKAGE_DIRNAME / TSV_DIRNAME / TSV_NAME
    tsv_dst.parent.mkdir(parents=True, exist_ok=True)
    tsv_dst.write_bytes(tsv_bytes)
    intake_dst = game_dir / intake_rel
    intake_dst.parent.mkdir(parents=True, exist_ok=True)
    intake_dst.write_bytes(tsv_bytes)

    return {
        "slug": slug,
        "game_id": metadata["game_id"],
        "title": metadata["title"],
        "game_hash": game_digest,
        "spec_hash": spec_digest,
        "levels": len(baselines),
        "slug_dir": str(slug_dir),
        "game_dir": str(game_dir),
        # The four entries, and the files under them — what a reviewer checks
        # without re-globbing the tree themselves.
        "entries": sorted(path.name for path in game_dir.iterdir()),
        "files": sorted(path.relative_to(game_dir).as_posix()
                        for path in game_dir.rglob("*") if path.is_file()),
        "replaced": replaced,
        "paths_note": PROMOTED_PATHS_NOTE,
    }


def withdraw_game(slug: str, games_root: Path | None = None) -> list[str]:
    """Take a game OFF the shelf: `games/<slug>/` removed. Returns the files removed.

    The unship half of promotion, and the same semantics `withdraw_play_preview`
    already established for the play root: a slug that is not there withdraws as
    an empty list, not an error — there is nothing to withdraw, and saying
    otherwise would be a claim about a directory that does not exist. Nothing
    outside `games/<slug>/` is read or touched.
    """
    _root, slug_dir, _game_dir = _shelf_dirs(slug, games_root)
    if not slug_dir.exists():
        return []
    if not slug_dir.is_dir():
        raise NotADirectoryError(
            f"{slug_dir} exists and is not a directory — the shelf holds one directory per "
            "slug (contract P-3 §2); nothing was removed"
        )
    removed = sorted(str(path) for path in slug_dir.rglob("*") if path.is_file())
    shutil.rmtree(slug_dir)
    return removed


# --- config -----------------------------------------------------------------


def _package_config(cfg: Mapping) -> dict:
    """The `package:` block — this stage's ONLY tunables (architecture §3 S6 Config)."""
    block = cfg.get("package") if isinstance(cfg, Mapping) else None
    if not isinstance(block, Mapping):
        raise KeyError(
            "config missing the `package:` block {seeds_validated, split{train, eval}} "
            "(architecture §3 S6 Config)"
        )
    seeds_validated = block.get("seeds_validated")
    if (isinstance(seeds_validated, bool) or not isinstance(seeds_validated, int)
            or seeds_validated < 1):
        raise ValueError(
            f"package.seeds_validated must be a positive int, got {seeds_validated!r} "
            "(architecture §3 S6: pilot ⊕ 5)"
        )
    split = block.get("split")
    if not isinstance(split, Mapping) or "train" not in split or "eval" not in split:
        raise KeyError("config missing `package.split` {train, eval} (architecture §3 S6)")
    values = {}
    for key in ("train", "eval"):
        value = split[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"package.split.{key} must be a number, got {value!r}")
        if not 0.0 < float(value) < 1.0:
            raise ValueError(f"package.split.{key} must be in (0, 1), got {value!r}")
        values[key] = float(value)
    total = values["train"] + values["eval"]
    if abs(total - 1.0) > 1e-9:
        raise ValueError(
            f"package.split must sum to 1.0, got {total!r} — the 70/30 convention is "
            "architecture §3 S6's sampler API ⊕"
        )
    return {"seeds_validated": int(seeds_validated), "split": values}


# --- manifest + report ------------------------------------------------------


def _versions() -> dict:
    return {
        "arcengine": importlib.metadata.version("arcengine"),
        "python": platform.python_version(),
    }


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_manifest(
    *,
    slug: str,
    game_id: str,
    verdict: str,
    seed_rows: Sequence[Mapping],
    requested: int,
    authored_seed: int | None,
    split: Mapping,
    spec_digest: str | None,
    game_digest: str,
    layout_present: bool,
    legacy_no_layout: bool,
    paths: Mapping,
) -> dict:
    """The b10.1 `package/manifest.json` — the sampler's registration record.

    architecture §2 names it `{slug, seeds_validated[], split}`; the frozen
    b10.1 shape adds the provenance chain (§2 ⊕), the layout-contract state
    (§7/D13) and the §6 flag table, so a consumer can tell from the manifest
    alone which unanswered questions this file leans on.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "slug": slug,
        "game_id": game_id,
        "verdict": verdict,
        "seeds": {
            "requested": int(requested),
            "validated": [dict(row) for row in seed_rows],
            "authored_seed": authored_seed,
        },
        "split": {
            "train": float(split["train"]),
            "eval": float(split["eval"]),
            "note": "applied at slug level; officials never in train",
        },
        "spec_hash": spec_digest,
        "game_hash": game_digest,
        "layout_contract": {
            "present": bool(layout_present),
            "legacy_no_layout": bool(legacy_no_layout),
        },
        "section6_flags": [dict(flag) for flag in SECTION6_DEFAULTS],
        "versions": _versions(),
        "paths": dict(paths),
    }


# --- the stage --------------------------------------------------------------


def run_s6(
    worker_dir: Path,
    cfg: Mapping,
    *,
    spec_path: Path | None = None,
    seeds: int | None = None,
    out_dir: Path | None = None,
    legacy_no_layout: bool = False,
    play_root: Path | None = None,
) -> dict:
    """Package one worker and write its outputs.

    Order is the law here, because each step gates the next:

    1. **S4 gating** — `<worker>.s4/metadata.json` must exist with verdict
       `fit` (the `s5_battery.load_battery_metadata` precedent, reused) and
       `actions/level-*.json` must cover every baselined level. S6 packages
       what S4 baselined; anything else is a ValueError → exit 1.
    2. **The layout contract** — no `build_layout` and no `legacy_no_layout`
       is a REFUSAL (spec §7 / D13). With it, layouts are re-derived at every
       validation seed and proven deterministic + pairwise distinct; a
       violation raises, because it routes differently from a seed-reject.
    3. **Seed validation** — the solver must WIN at every seed and complete
       the authored level count. Any failure → verdict `seed-reject`, route
       S2, exit 2, and NO tsv/manifest/play mirror: a rejected game must not
       become corpus surface. A stale one from an earlier run is removed.
    4. **Emission** — TSV, its duck-intake copy, manifest, play mirror, then
       the report (always).

    CONTRACT P-1 (the b004 seed-3 crash). Steps 2 and 3 drive WORKER CODE, and
    a crash in it is now a VERDICT, never a raise: every such crash becomes a
    failing seed row naming the seed, the exception class + message and the
    crash site inside the worker's own file, the verdict is `seed-reject` with
    the §3 route S2, and NOTHING is emitted — no tsv, no manifest, no duck
    intake, no play mirror. What stays loud is what was always S6's own refusal:
    the S4 gating above, the §7 violations (no `build_layout`, a layout that
    ignores its seed or will not serialize) and a config defect.

    `out_dir` defaults to the worker SIBLING `<worker>.s6/`; `seeds` overrides
    `package.seeds_validated`; `play_root` overrides `out/play/`.
    """
    worker_dir = Path(worker_dir).resolve()
    if not worker_dir.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker_dir}")
    package = _package_config(cfg)  # fail on a bad config before driving anything
    if seeds is not None:
        if isinstance(seeds, bool) or not isinstance(seeds, int) or seeds < 1:
            raise ValueError(f"seeds must be a positive int, got {seeds!r}")
        package = {**package, "seeds_validated": int(seeds)}
    seed_cfg = {**dict(cfg), "package": {**dict(cfg.get("package") or {}),
                                         "seeds_validated": package["seeds_validated"]}}

    target = (Path(out_dir) if out_dir is not None
              else worker_dir.parent / (worker_dir.name + OUT_SUFFIX)).resolve()
    s4_dir = worker_dir.parent / (worker_dir.name + S4_OUT_SUFFIX)
    s4_metadata_path = (s4_dir / S4_METADATA_NAME).resolve()

    # 1. gating
    try:
        s4_metadata = load_battery_metadata(s4_metadata_path)
    except ValueError as exc:
        raise ValueError(
            f"{worker_dir}: S6 packages only games S4 baselined `{VERDICT_FIT}` "
            f"(architecture §3 S6 In→Out: worker/ + metadata → package/) — {exc}"
        ) from None
    baselines = [int(value) for value in s4_metadata["baseline_actions"]]
    levels = len(baselines)
    load_action_line(s4_dir, levels)  # every baselined level must have its line

    slug = _slug(worker_dir)
    game_digest = game_hash(worker_dir)
    game_hash8 = game_digest[:8]
    spec_digest = spec_hash(spec_path)

    # 2. the layout contract
    #
    # Contract P-1: the contract load EXECUTES the worker (import + a
    # no-argument construction). A crash there leaves no seed list to report
    # against, so it becomes the one row §3's legacy path already uses — the
    # authored default, `seed: None` — and the stage goes straight to the
    # seed-reject report below with nothing emitted.
    layout_crash: WorkerCodeError | None = None
    try:
        layout = load_layout_contract(worker_dir)
    except WorkerCodeError as exc:
        layout_crash = exc
        layout = {"has_build_layout": False, "default_seed": None,
                  "module_path": str(worker_dir / "game.py"), "crashed": exc.note}
    present = bool(layout["has_build_layout"])
    if layout_crash is None and not present and not legacy_no_layout:
        raise ValueError(
            f"{worker_dir}: no build_layout(seed) — spec-v0.3 §7 requires layout-from-seed "
            "FROM BIRTH and D13 makes it non-retrofittable, so this game cannot be packaged. "
            "Pass legacy_no_layout=True (CLI --legacy-no-layout) only for games that predate "
            "the contract (the toy worker and the B1-B9 fixtures)."
        )
    # The escape hatch excuses ABSENCE, nothing else: a game that ships
    # build_layout is always validated under §7, flag or no flag, and the
    # manifest field records whether the hatch was actually APPLIED.
    legacy_applied = (not present) and bool(legacy_no_layout)
    authored_seed = layout["default_seed"]

    rederivation = None
    # seed -> the contained crash that makes it unvalidatable (contract P-1).
    crashed_seeds: dict[int | None, dict] = {}
    if layout_crash is not None:
        seed_list: list[int | None] = [None]
        crashed_seeds[None] = {"seed": None, "error": layout_crash.note,
                               "site": layout_crash.site}
    elif present:
        seed_list = list(
            validation_seeds(seed_cfg, s4_metadata.get("game_id") or slug, authored_seed)
        )
        # The crash list is HANDED IN (contract P-1): a seed whose build_layout
        # dies is recorded and the remaining seeds are still re-derived, so one
        # bad seed reports as one bad seed instead of ending the stage.
        layout_crashes: list[dict] = []
        layouts = rederive_layouts(worker_dir, [s for s in seed_list if s is not None],
                                   crashes=layout_crashes)
        crashed_seeds.update({row["seed"]: row for row in layout_crashes})
        rederivation = {
            # The two claims below are about the seeds that DERIVED; the ones
            # that crashed are named separately and never silently pass.
            "checked": True,
            "same_seed_determinism": True,
            "pairwise_distinct": True,
            "seeds": [
                {
                    "seed": seed,
                    "chars": len(layouts[seed]),
                    "sha256": hashlib.sha256(layouts[seed].encode()).hexdigest(),
                }
                for seed in seed_list if seed is not None and seed in layouts
            ],
            "crashed": layout_crashes,
        }
    else:
        # architecture §3 S6 still validates: one drive at the authored layout.
        seed_list = [None]

    # 3. seed validation
    seed_rows: list[dict] = []
    seed_detail: list[dict] = []
    for seed in seed_list:
        crash = crashed_seeds.get(seed)
        if crash is not None:
            # No layout, no drive: the crash IS this seed's verdict (P-1).
            row = {"seed": seed, "win": False, "levels_completed": 0,
                   "actions_total": 0, "error": crash["error"]}
        else:
            row = validate_seed(worker_dir, seed)
        passed = bool(row["win"]) and int(row["levels_completed"]) == levels
        reason = None
        if not passed:
            reason = row["error"] or (
                f"the solver completed {row['levels_completed']} of {levels} authored level(s)"
            )
        seed_rows.append(row)
        seed_detail.append({**row, "passed": passed, "reason": reason,
                            "levels_expected": levels})
    verdict = (VERDICT_PACKAGED if all(detail["passed"] for detail in seed_detail)
               else VERDICT_SEED_REJECT)

    package_dir = target / PACKAGE_DIRNAME
    tsv_path = package_dir / TSV_DIRNAME / TSV_NAME
    manifest_path = package_dir / MANIFEST_NAME
    intake_rel = duck_intake_rel(slug)
    report_path = target / REPORT_NAME
    play = play_command(cfg, Path(play_root) if play_root is not None else PLAY_ROOT)

    # 4. emission
    tsv_detail = None
    play_dir = None
    intake_path = None
    withdrawn: list[str] = []
    if verdict == VERDICT_PACKAGED:
        emit_tsv(worker_dir, s4_dir, tsv_path, layout_seed=authored_seed)
        rows_written = sum(1 for _ in tsv_path.read_text(encoding="utf-8").splitlines()) - 1
        # The mirror is written from the canonical file's bytes, so the two are
        # identical by construction, not by a second emission.
        intake_path = write_duck_intake(tsv_path, target, slug)
        tsv_detail = {**tsv_stats(tsv_path, rows_written),
                      "reward_ones": _reward_ones(tsv_path),
                      "levels": levels,
                      "layout_seed": authored_seed,
                      "duck_intake": intake_rel.as_posix()}
        play_dir = write_play_mirror(
            worker_dir, s4_metadata, game_hash8=game_hash8, play_root=play_root
        )
    else:
        # A rejected game must not leave corpus surface behind from an earlier run.
        for stale in (tsv_path, manifest_path):
            if stale.is_file():
                stale.unlink()
                withdrawn.append(str(stale))
        withdrawn.extend(_clear_duck_intake(target, slug))
        withdrawn.extend(_clear_play_mirror(worker_dir, game_hash8, play_root))

    paths = {
        "worker": str(worker_dir),
        "out_dir": str(target),
        "s4_metadata": str(s4_metadata_path),
        "spec": str(Path(spec_path)) if spec_path is not None else None,
        "tsv": str(tsv_path) if verdict == VERDICT_PACKAGED else None,
        "manifest": str(manifest_path) if verdict == VERDICT_PACKAGED else None,
        # Relative to `out_dir` above (see duck_intake_rel), so the manifest
        # resolves its own mirror without carrying a second absolute path.
        "duck_intake": intake_rel.as_posix() if verdict == VERDICT_PACKAGED else None,
        "play_mirror": str(play_dir) if play_dir is not None else None,
        "report": str(report_path),
    }
    manifest = build_manifest(
        slug=slug,
        game_id=str(s4_metadata.get("game_id") or slug),
        verdict=verdict,
        seed_rows=seed_rows,
        requested=len(seed_list),
        authored_seed=authored_seed,
        split=package["split"],
        spec_digest=spec_digest,
        game_digest=game_digest,
        layout_present=present,
        legacy_no_layout=legacy_applied,
        paths=paths,
    )
    if verdict == VERDICT_PACKAGED:
        _write_json(manifest_path, manifest)

    report = {
        **manifest,
        "stage": "s6",
        "levels": levels,
        "baseline_actions": baselines,
        "layout_contract_detail": dict(layout),
        "rederivation": rederivation,
        "seed_detail": seed_detail,
        "seeds_failed": [detail["seed"] for detail in seed_detail if not detail["passed"]],
        # Contract P-1's reject block: every seed the WORKER's own code crashed
        # on, with the site inside its own file. Empty on every clean run and on
        # an ordinary losing-line seed-reject, which is not a crash.
        "worker_crashes": [dict(crashed_seeds[seed]) for seed in seed_list
                           if seed in crashed_seeds],
        "tsv": tsv_detail,
        # The manifest carries the mirror out_dir-relative; the report is the
        # operator-facing record, so it also resolves it and names the directory
        # sprite_lib's --sample-dir is pointed at (the `*_perfect/…` glob root).
        "duck_intake": {
            "relative": intake_rel.as_posix(),
            "path": str(intake_path) if intake_path is not None else None,
            "sample_dir": (str(package_dir / DUCK_INTAKE_DIRNAME)
                           if intake_path is not None else None),
        },
        "play": {**play, "dir": str(play_dir) if play_dir is not None else None,
                 "root": str(Path(play_root) if play_root is not None else PLAY_ROOT)},
        "withdrawn": withdrawn,
        "route": ROUTE_SEED_REJECT if verdict == VERDICT_SEED_REJECT else None,
        "config": {
            "seeds_validated": package["seeds_validated"],
            "split": package["split"],
            "batch_seed": (cfg.get("batch") or {}).get("seed"),
        },
    }
    _write_json(report_path, report)
    return report


# --- CLI --------------------------------------------------------------------


def _flags_line() -> str:
    parts = [f"{flag['question']} {flag['default_applied']}" for flag in SECTION6_DEFAULTS]
    return " · ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S6 packager — layout-seed validation, gym-TSV emission, manifest"
    )
    parser.add_argument("--worker", required=True, help="worker dir holding game.py + solver.py")
    parser.add_argument("--spec", default=None, help="spec.yaml for the provenance spec_hash")
    parser.add_argument(
        "--seeds", type=int, default=None, help="override package.seeds_validated"
    )
    parser.add_argument("--out", default=None, help="write outputs here instead of <worker>.s6/")
    parser.add_argument(
        "--play-root", default=None, help=f"mirror games here instead of {PLAY_ROOT}"
    )
    parser.add_argument(
        "--legacy-no-layout",
        action="store_true",
        help="package a game with no build_layout(seed) (pre-D13 toys/fixtures ONLY)",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        report = run_s6(
            Path(args.worker),
            cfg,
            spec_path=Path(args.spec) if args.spec else None,
            seeds=args.seeds,
            out_dir=Path(args.out) if args.out else None,
            legacy_no_layout=args.legacy_no_layout,
            play_root=Path(args.play_root) if args.play_root else None,
        )
    except (OSError, ValueError, TypeError, KeyError, AssertionError) as exc:
        print(f"[s6] ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    verdict = report["verdict"]
    seeds = report["seeds"]
    passed = sum(1 for detail in report["seed_detail"] if detail["passed"])
    authored = seeds["authored_seed"]
    print(
        f"[s6] {verdict.upper()} {report['game_id']} | slug {report['slug']} | "
        f"{report['levels']} level(s) | seeds {passed}/{seeds['requested']} ok "
        f"(authored {'none' if authored is None else authored}) | "
        f"game_hash {report['game_hash'][:8]} | spec_hash "
        f"{'none' if report['spec_hash'] is None else report['spec_hash'][:8]}"
    )
    if report["layout_contract"]["present"]:
        derived = len(report["rederivation"]["seeds"])
        # One seed has no pair, so claiming distinctness there would overclaim.
        print(
            f"[s6] layout: build_layout present, {derived} seed(s) re-derived — same-seed "
            f"determinate{', pairwise distinct' if derived > 1 else ''} (spec §7 / D13)"
        )
    else:
        print(
            "[s6] layout: NO build_layout(seed) — packaged under --legacy-no-layout. "
            "spec §7 / D13 require layout-from-seed FROM BIRTH; this game predates the "
            "contract and its manifest says so (layout_contract.present false)."
        )
    for detail in report["seed_detail"]:
        if detail["passed"]:
            continue
        print(
            f"[s6] seed {detail['seed']}: win {detail['win']} levels "
            f"{detail['levels_completed']}/{detail['levels_expected']} actions "
            f"{detail['actions_total']} — {detail['reason']}"
        )
    if verdict == VERDICT_PACKAGED:
        tsv = report["tsv"]
        print(
            f"[s6] tsv: {tsv['rows']} row(s) ({tsv['action_rows']} action + 1 terminal), "
            f"{tsv['columns']} cols, {tsv['reward_ones']} reward-1 row(s) "
            f"({tsv['levels']} level(s) + terminal echo), {tsv['bytes']} bytes"
        )
        print(f"[s6] §6 defaults applied AND flagged: {_flags_line()}")
        print(
            f'[s6] §6 Q4 divergence: default text "duration omitted", proven dialect emits '
            f'"{TSV_DURATION}" — we emit the constant (manifest.section6_flags)'
        )
        split = report["split"]
        print(
            f"[s6] split: train {split['train']:g} / eval {split['eval']:g} — {split['note']}"
        )
        print(f"[s6] manifest: {report['paths']['manifest']}")
        intake = report["duck_intake"]
        print(
            f"[s6] duck intake: {intake['path']} (byte-identical copy of "
            f"{TSV_DIRNAME}/{TSV_NAME}; point sprite_lib --sample-dir at "
            f"{intake['sample_dir']})"
        )
        print(f"[s6] play mirror: {report['paths']['play_mirror']}")
    else:
        print(f"[s6] route: {ROUTE_SEED_REJECT} — architecture §3 S6 failure routing")
        print(
            "[s6] no package written: tsv, manifest and play mirror withheld — a rejected "
            "game must not become corpus surface"
        )
        for path in report["withdrawn"]:
            print(f"[s6] withdrawn: {path}")
    print(f"[s6] report: {report['paths']['report']}")
    if verdict == VERDICT_PACKAGED:
        play = report["play"]
        if not (play["server_exists"] and play["python_exists"]):
            print(
                f"[s6] note: play server {play['server']} exists={play['server_exists']}, "
                f"python {play['python']} exists={play['python_exists']}"
            )
        print(play["command"])
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
