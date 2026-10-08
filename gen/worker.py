"""Worker instantiation (B1) — fresh scaffold copies + edit-scope manifests.

`instantiate_worker(dest)` copies `worker-template/` to `dest`, writes
`worker.mk` (pins PY to this repo's venv python) and
`.scaffold-manifest.json` (SHA-256 of every scaffold file; `game.py` and
`solver.py` are listed as editable). A sibling copy `<dest>.manifest.json`
stays OUTSIDE the worker — `verify_worker()` checks against that copy, so
an agent tampering with the in-worker manifest or checker is still caught
pipeline-side (the in-worker `make validate` scope check is the agent's
convenience loop).

`repair_worker(dest)` (B3) is the write-side counterpart the S2 green loop
runs after every session: it restores each non-editable file that drifted
(from the template, or by regenerating `worker.mk`), restores the in-worker
manifest copy from the sibling, and deletes out-of-scope additions — never
touching `game.py`/`solver.py`. A scope violation then costs one repair and
a line in the next prompt instead of the whole run.

`write_seeds_sidecar(dest, cfg)` (E-0) writes `<dest>.seeds.json`: the exact
seed list S6 will validate this game at, as a SIBLING of the worker, so the
scaffold's own seed sweep can drive S6's seeds inside the build loop instead
of learning the verdict at packaging time. The list is never re-derived here
— `s6_package.validation_seeds` computes it, once, for both stages.

`resync_worker(dest)` (E-0) brings an EXISTING worker to today's scaffold
generation: scaffold files from today's template, both manifests rebuilt, the
seeds sidecar written, `game.py`/`solver.py` byte-untouched. It is
OPERATOR-INVOKED and nothing calls it automatically: absent a resync an
existing worker behaves exactly as it did before, template drift included.

`purge_worker_modules(worker_dir)` (E-4) evicts the `sys.modules` entries the
worker's OWN §7 sibling-loader planted under a PATH-derived name, so a stage
that re-drives a rewritten pair in one long-lived process cannot be handed a
fresh game and a stale solver plan. See "The §7 module-cache eviction" below.

THE SECONDARY STALENESS LAYER, recorded and NOT fixed here: CPython validates
a cached `__pycache__/*.pyc` against the source's mtime in SECONDS plus its
SIZE — `SourceLoader.get_code` takes `int(st['mtime'])` and
`_validate_timestamp_pyc` compares that and `st.st_size` against the pyc
header (`importlib/_bootstrap_external.py:1089,703-728`). A rewrite that
lands in the same wall-clock second AND keeps the byte count identical can
therefore serve stale BYTECODE even to a genuinely fresh load, because the
module-table eviction only decides which module object is reused, not which
bytes the loader compiles. Real S2 fixes change the length, so this has never
been observed in a run. THE BELT, added at the same seam: `purge_worker_modules`
also removes the worker's own `__pycache__` (the one the worker's `make
validate` writes), so no stale pyc survives an eviction — and the
fresh-interpreter legs (`frames.capture_worker_isolated`, `run_s4_isolated`)
plus `sys.dont_write_bytecode` in `gen/s3_verify._load_module` remain the
other guarantees.

CLI:  python -m gen.worker --dest out/workers/w001 [--force]
      python -m gen.worker --dest <worker> --resync [--config <batch config>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

from .config import REPO_ROOT

TEMPLATE_DIR = REPO_ROOT / "worker-template"
EDITABLE = ("game.py", "solver.py")
MANIFEST_NAME = ".scaffold-manifest.json"
IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache"}
DEFAULT_PYTHON = REPO_ROOT / ".venv/bin/python"
# The one generated scaffold file: it is not in the template, so repair
# regenerates it instead of copying.
GENERATED = "worker.mk"

# --- the seed sidecar (contract E-0) ----------------------------------------
# A SIBLING of the worker, never a file inside it: `check_edit_scope` fails on
# any new file in the tree, and this is pipeline state the implementing agent
# must not be able to rewrite. Same `<worker>.<suffix>` convention as
# `<worker>.manifest.json`.
SEEDS_SUFFIX = ".seeds.json"
SEEDS_SCHEMA = "e0.1"
# The spec document the authored default seed is read from, beside the worker.
SPEC_YAML_NAME = "spec.yaml"
# How to re-derive the list by hand, in words, for a reader holding only the
# sidecar. The MECHANISM is never re-implemented here or in the worker:
# `s6_package.validation_seeds` is the one source of truth, and this string is
# a description of what it did, not a second copy of it.
SEEDS_DERIVATION = (
    "seeds[0] = the authored default (the spec's game.layout.seed); every extra = "
    'int(sha256(f"{batch_seed}:{game_id}:s6:{k}").hexdigest()[:8], 16) for k = 1, 2, 3, ..., '
    "skipping any repeat; count = package.seeds_validated"
)

# `authored_seed` sentinel: "read it from the spec beside the worker", which is
# a different instruction from `None` ("this game has no authored default", the
# fully-derived list S6 only ever builds for a game without build_layout).
_UNSET = object()

# --- the §7 module-cache eviction (contract E-4) ----------------------------
# THE DEFECT (lead-measured 2026-10-05). The §7 solver skeleton the S2 payload
# teaches — and every shipped solver carries — loads its sibling game BY PATH
# and caches the module in `sys.modules` under a name derived from that PATH
# ALONE: `"game_" + sha256(str(<game.py path>)).hexdigest()[:12]`. The path is
# the ONE thing an S2 rewrite does not change. So in a single long-lived batch
# process a stage that re-drives the pair after a rewrite gets a FRESH game
# (both pipeline loaders re-exec every call) and a STALE solver plan (the
# skeleton's cache hit) — the solver plans against a layout the game no longer
# has. Measured consequence: lantern-path-parity-trace's seed-INDEPENDENT 5/5
# seed-reject (7 actions, 0 levels at every seed) whose same bytes pass 5/5 in
# a fresh interpreter; by signature, b005-auto's triple same-seed S6 reject.
#
# Generated code is not ours to constrain — a solver may name and cache its
# sibling however it likes — so the pipeline EVICTS instead: before any stage
# exec-loads a worker pair in process, every `sys.modules` entry that belongs
# to THIS worker's sibling-loader goes, and the next `_game_module()` call has
# to read the bytes on disk. `gen/frames.py`'s `capture_worker_isolated`
# fresh-interpreter answer (R2 hotfix #8) is unchanged and still stronger where
# a subprocess is affordable; this is the in-process legs' equivalent.
#
#: `sys.modules` name prefixes belonging to THIS pipeline's own loaders
#: (`s3_static._load_module`, `s3_verify._load_module`). Never evicted: both
#: re-exec on every call, and S6's stat-keyed cache holds the module OBJECT, so
#: there is nothing here for eviction to fix — the contract's rule is that
#: eviction clears the skeleton's FOREIGN entries only.
PIPELINE_MODULE_PREFIXES = ("s3_game_", "s3_solver_")

#: The two worker files a §7 sibling-loader can key its cache on.
MODULE_KEYED_FILES = ("game.py", "solver.py")

#: The skeleton's own prefix, for the name it derives: `game_<tag>`.
SKELETON_MODULE_PREFIX = "game_"

#: How many hex characters of the path digest the skeleton keeps.
MODULE_TAG_CHARS = 12

#: The bytecode cache CPython writes beside a worker's `game.py`/`solver.py`.
BYTECODE_CACHE_DIR = "__pycache__"


def worker_module_tags(worker_dir: Path | str) -> tuple[str, ...]:
    """The path TAGS a §7 sibling-loader in this worker can have keyed on.

    THE DERIVATION, mirrored exactly from the skeleton in
    `gen/s2_implement.LAYOUT_SEED_CONTRACT`: the sha256 of the path STRING,
    hexdigest, first `MODULE_TAG_CHARS` characters. The skeleton's own name is
    `SKELETON_MODULE_PREFIX + tag` (`skeleton_module_names` builds it).

    Several SPELLINGS of the same file hash differently and generated code may
    hold any of them, so every one is produced, deduplicated, sorted:

    * `Path(__file__).resolve().with_name("game.py")` — the skeleton's own
      expression, which is the SOLVER's resolved directory and differs from the
      game file's own `resolve()` only through a symlink (a tmp root on macOS
      is exactly that);
    * `<worker>/game.py` and `<worker>/solver.py` resolved, for a loader keyed
      on either file;
    * both as the caller SPELLED them: a stage handed a relative worker dir
      stamps that relative path into the module's `__file__`.

    No existence check: eviction is a precondition cleanup that must not change
    which error a loader raises for a missing worker, and a tag is computable
    from a path alone. The loader that calls this owns the existence verdict.
    """
    if isinstance(worker_dir, bool) or not isinstance(worker_dir, (str, Path)):
        raise TypeError(f"worker_dir must be a path, got {worker_dir!r}")
    base = Path(worker_dir)
    spellings: set[str] = set()
    for name in MODULE_KEYED_FILES:
        spelled = base / name
        spellings.add(str(spelled))
        spellings.add(str(spelled.resolve()))
    # The skeleton's literal expression, from the solver's side.
    spellings.add(str((base / "solver.py").resolve().with_name("game.py")))
    return tuple(sorted(
        hashlib.sha256(spelling.encode("utf-8")).hexdigest()[:MODULE_TAG_CHARS]
        for spelling in spellings
    ))


def skeleton_module_names(worker_dir: Path | str) -> tuple[str, ...]:
    """The exact `sys.modules` names the §7 skeleton's loader derives here.

    The parity surface: `gen/tests/test_e4_modcache.py` executes the skeleton's
    own code and asserts the name it plants is in this tuple, so the derivation
    above and the taught code cannot drift apart unnoticed.
    """
    return tuple(SKELETON_MODULE_PREFIX + tag for tag in worker_module_tags(worker_dir))


def worker_module_names(worker_dir: Path | str) -> tuple[str, ...]:
    """The `sys.modules` keys REGISTERED RIGHT NOW for this worker's own loader.

    Prefix-agnostic by design: the skeleton's `game_<tag>` is one spelling and
    the checked-in fixtures already use others (`s6_seeded_game_<tag>`,
    `s6_seeded_broken_game_<tag>`), so what is matched is the TAG anywhere in
    the name. A 12-hex path digest does not occur in an unrelated module name
    by accident, and this pipeline's own prefixes are excluded explicitly.

    The known limit, stated so nobody reads more into the fix than it gives: a
    solver that caches its sibling under a name carrying NO path tag (plain
    `"game"`, say) is not covered — such a name also collides between two
    workers in one process, which is why the skeleton has always hashed the
    path. `frames.capture_worker_isolated` remains the total answer.
    """
    tags = worker_module_tags(worker_dir)
    return tuple(sorted(
        name
        for name in list(sys.modules)
        if any(tag in name for tag in tags) and not name.startswith(PIPELINE_MODULE_PREFIXES)
    ))


def purge_worker_bytecode(worker_dir: Path | str) -> tuple[Path, ...]:
    """THE PYC BELT: remove the worker's own `__pycache__`. Returns what went.

    The module-table eviction forces the next load to go through the LOADER
    again; this forces that loader to go through the SOURCE. Without it the two
    staleness layers are not the same fix: CPython validates a cached `.pyc` on
    mtime-SECONDS + size (see the module header), so a same-size rewrite inside
    one second is served stale bytecode even by a brand-new module name — and
    real workers do carry a `__pycache__`, because the worker's own `make
    validate` imports `game.py` in its own interpreter and writes one.

    ONLY the worker's ROOT cache dir, and only when it is a real directory: a
    symlink is refused rather than followed, so nothing outside the worker tree
    can be reached from here. `<worker>/tests/__pycache__` is left alone — it
    belongs to the scaffold's own pytest, not to the pair this pipeline loads.
    A missing dir is simply nothing to do, and a `FileNotFoundError` from a
    concurrent reader losing a file mid-walk means the dir is gone, which is
    the goal; any other `OSError` (a permission problem, say) is a real defect
    and propagates.

    The cost is one cold compile per load — measured at 6.9 ms for the largest
    shipped `game.py` (17.1 kB) against 0.1 ms warm — paid by a stage that then
    drives thousands of engine actions.
    """
    cache = Path(worker_dir) / BYTECODE_CACHE_DIR
    if cache.is_symlink() or not cache.is_dir():
        return ()
    try:
        shutil.rmtree(cache)
    except FileNotFoundError:
        return ()
    return (cache,)


def purge_worker_modules(worker_dir: Path | str) -> tuple[str, ...]:
    """Evict them. Returns the names dropped (sorted) — () when there was none.

    Called at the top of every pipeline path that exec-loads a worker pair in
    process, BEFORE any of the worker's code runs:
    `s3_static.load_worker_classes` (S3-static's checks, S3's structural gate,
    S4's baselines, S5's battery, S6 through `_load_worker`),
    `s3_verify.load_worker_classes` (the verifier's own loads and
    `frames.capture_worker`, the in-process capture leg) and
    `s6_package._load_worker` itself, which keeps its own stat-keyed cache in
    front of the shared loader.

    Two layers, one seam: the module table first, then `purge_worker_bytecode`
    for the worker's `__pycache__` (the pyc belt — see its docstring and the
    module header). The return value names the MODULES only; the bytecode dirs
    are `purge_worker_bytecode`'s own return value for a caller that wants it.

    Idempotent: the name derivation resolves the two worker paths (one realpath
    syscall each, no file opened), the module eviction is a scan of the module
    table, and the belt's `rmtree` costs the next load one cold compile (~7 ms
    on the largest shipped game). Dropping a name does not invalidate module
    objects anything still holds (a live `Solver` keeps its own), so this never
    breaks a load already in flight — it only forces the NEXT one to read disk.
    """
    evicted = worker_module_names(worker_dir)
    for name in evicted:
        sys.modules.pop(name, None)
    purge_worker_bytecode(worker_dir)
    return evicted


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.name == MANIFEST_NAME or any(part in IGNORED_DIRS for part in rel.parts):
            continue
        files[rel.as_posix()] = path
    return files


def _write_worker_mk(dest: Path, python: Path) -> None:
    """Write the venv pin that `Makefile` includes.

    ONE copy of this content: instantiation and repair must produce
    byte-identical bytes or a repaired worker would not match the manifest
    hashed at instantiation.
    """
    python = Path(python)
    if not python.is_file():
        raise FileNotFoundError(f"pinned python not found: {python}")
    (dest / GENERATED).write_text(f"PY := {python}\n", encoding="utf-8")


def build_manifest(worker_dir: Path) -> dict:
    files = {rel: _sha256(path) for rel, path in _walk(worker_dir).items()}
    for name in EDITABLE:
        if name not in files:
            raise FileNotFoundError(f"scaffold is missing editable file {name!r} in {worker_dir}")
    return {"editable": list(EDITABLE), "files": files}


def instantiate_worker(dest: Path, *, python_bin: Path | None = None, force: bool = False) -> dict:
    dest = Path(dest).resolve()
    if not TEMPLATE_DIR.is_dir():
        raise FileNotFoundError(f"worker template missing: {TEMPLATE_DIR}")
    if dest.exists():
        if not force:
            raise FileExistsError(f"worker dir exists (pass force=True to replace): {dest}")
        shutil.rmtree(dest)
    shutil.copytree(TEMPLATE_DIR, dest, ignore=shutil.ignore_patterns(*IGNORED_DIRS))

    _write_worker_mk(dest, Path(python_bin) if python_bin else DEFAULT_PYTHON)

    manifest = build_manifest(dest)
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (dest / MANIFEST_NAME).write_text(manifest_json, encoding="utf-8")
    dest.with_name(dest.name + ".manifest.json").write_text(manifest_json, encoding="utf-8")
    return manifest


def verify_worker(worker_dir: Path) -> list[str]:
    """Pipeline-side scope check against the SIBLING manifest copy.

    Returns violation strings (empty = clean). The editable files may
    differ freely; everything else must match the instantiation hashes.
    """
    worker_dir = Path(worker_dir).resolve()
    sibling = worker_dir.with_name(worker_dir.name + ".manifest.json")
    if not sibling.is_file():
        raise FileNotFoundError(f"pipeline manifest copy missing: {sibling}")
    manifest = json.loads(sibling.read_text(encoding="utf-8"))
    editable = set(manifest["editable"])
    expected: dict[str, str] = manifest["files"]

    present = _walk(worker_dir)
    violations: list[str] = []
    for rel, expected_hash in sorted(expected.items()):
        if rel in editable:
            continue
        path = present.get(rel)
        if path is None:
            violations.append(f"deleted non-editable file: {rel}")
        elif _sha256(path) != expected_hash:
            violations.append(f"modified non-editable file: {rel}")
    for rel in sorted(present):
        if rel not in expected and rel not in editable:
            violations.append(f"new file outside the edit scope: {rel}")
    return violations


def repair_worker(worker_dir: Path) -> list[str]:
    """Restore a worker to scaffold-clean WITHOUT touching the editable files.

    The SIBLING manifest copy is the authority — the in-worker copy is
    within the agent's reach, so it is itself a repair target. Every
    non-editable file that is missing or hash-mismatched is restored
    (`worker.mk` by regeneration, everything else from TEMPLATE_DIR) and
    every file that is neither in the manifest nor editable is deleted.
    Nothing under IGNORED_DIRS is ever read or deleted.

    Restoring from the template is only sound while the template still
    hashes to what the manifest recorded: a template that drifted since
    instantiation would yield a worker that passes `make validate` yet does
    NOT match its own manifest, so drift raises instead of faking a repair.

    Returns one human-readable line per repair (empty = nothing to do);
    `verify_worker()` is clean afterwards or this raises.
    """
    worker_dir = Path(worker_dir).resolve()
    sibling = worker_dir.with_name(worker_dir.name + ".manifest.json")
    if not sibling.is_file():
        raise FileNotFoundError(f"pipeline manifest copy missing: {sibling}")
    manifest_json = sibling.read_text(encoding="utf-8")
    manifest = json.loads(manifest_json)
    editable = set(manifest["editable"])
    expected: dict[str, str] = manifest["files"]
    repairs: list[str] = []

    in_worker = worker_dir / MANIFEST_NAME
    if not in_worker.is_file() or in_worker.read_text(encoding="utf-8") != manifest_json:
        in_worker.write_text(manifest_json, encoding="utf-8")
        repairs.append(f"restored {MANIFEST_NAME}")

    present = _walk(worker_dir)
    for rel, expected_hash in sorted(expected.items()):
        if rel in editable:
            continue
        path = present.get(rel)
        if path is not None and _sha256(path) == expected_hash:
            continue
        target = worker_dir / rel
        if rel == GENERATED:
            _write_worker_mk(worker_dir, DEFAULT_PYTHON)
            actual = _sha256(target)
            if actual != expected_hash:
                raise RuntimeError(
                    f"regenerated {GENERATED} hashes {actual} but the manifest expects "
                    f"{expected_hash} — was this worker instantiated with a non-default "
                    f"python_bin? (default: {DEFAULT_PYTHON})"
                )
        else:
            source = TEMPLATE_DIR / rel
            if not source.is_file():
                raise FileNotFoundError(
                    f"cannot restore {rel}: absent from the template ({source}) and not generated"
                )
            source_hash = _sha256(source)
            if source_hash != expected_hash:
                raise RuntimeError(
                    f"template drift: {source} hashes {source_hash} but the manifest expects "
                    f"{expected_hash} for {rel} — repairing from it would not restore the "
                    f"instantiated scaffold; re-instantiate the worker instead"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        repairs.append(f"restored {rel}")

    emptied: set[Path] = set()
    for rel in sorted(present):
        if rel in expected or rel in editable:
            continue
        present[rel].unlink()
        emptied.add(present[rel].parent)
        repairs.append(f"deleted stray {rel}")
    # Directories the deletions emptied go too — otherwise a `helpers/`
    # husk survives every repair. `any(iterdir())` stops at anything left,
    # so an IGNORED_DIRS child (e.g. __pycache__) keeps its parent alive.
    for parent in sorted(emptied, key=lambda p: len(p.parts), reverse=True):
        while parent != worker_dir and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            repairs.append(f"removed empty directory {parent.relative_to(worker_dir).as_posix()}/")
            parent = parent.parent

    violations = verify_worker(worker_dir)
    if violations:
        raise RuntimeError(
            f"repair did not restore the edit scope of {worker_dir}: {violations}"
        )
    return repairs


# --- the seed sidecar + resync (contract E-0) -------------------------------


def seeds_sidecar_path(worker_dir: Path) -> Path:
    """`<worker>.seeds.json` — the seed sidecar, OUTSIDE the worker tree."""
    worker_dir = Path(worker_dir)
    return worker_dir.with_name(worker_dir.name + SEEDS_SUFFIX)


def spec_layout_seed(worker_dir: Path) -> int:
    """`game.layout.seed` from the `spec.yaml` beside the worker.

    That integer is the AUTHORED DEFAULT: the seed the game bakes in and the
    first seed S6 validates (`s6_package.run_s6` reads it back off a
    no-argument instance; §11 makes it a mandatory spec field, so S1's linter
    has already killed a spec that lacks it).

    Loud on absence or a non-int rather than falling back to a derived list: a
    guessed authored seed would make the whole sidecar a list of seeds this
    game is never validated at, which is worse than no sidecar at all (no
    sidecar is an honest premise-skip in the sweep).
    """
    import yaml  # deferred: worker.py is also the scaffold CLI, imported bare

    spec_path = Path(worker_dir).parent / SPEC_YAML_NAME
    if not spec_path.is_file():
        raise FileNotFoundError(
            f"no {SPEC_YAML_NAME} beside {worker_dir} ({spec_path}) — the authored default "
            "seed is a spec fact (§11 game.layout.seed); pass authored_seed= explicitly for "
            "a worker that has no spec"
        )
    document = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    game = document.get("game") if isinstance(document, dict) else None
    layout = game.get("layout") if isinstance(game, dict) else None
    seed = layout.get("seed") if isinstance(layout, dict) else None
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError(  # noqa: TRY004 — a malformed spec is bad DATA, not a caller type error
            f"{spec_path}: game.layout.seed must be an int (§11 mandatory field, §7: layouts "
            f"are functions of it), got {seed!r}"
        )
    return int(seed)


def seed_plan(
    worker_dir: Path,
    cfg: Mapping,
    *,
    game_id: str | None = None,
    authored_seed: int | None | object = _UNSET,
) -> dict:
    """What `write_seeds_sidecar` writes: S6's seed list plus its provenance.

    ONE derivation, shared with the stage that enforces it —
    `s6_package.validation_seeds(cfg, game_id, authored_seed)` computes the
    list, `s6_package._slug` resolves the default `game_id` (S6 itself falls
    back to the slug when the S4 metadata carries none), and the recorded
    `max_actions` is `s6_package.MAX_ACTIONS`. Nothing here re-implements any
    of the three: two copies of this arithmetic is how a sweep comes to
    disagree with the stage it is mirroring.
    """
    from .s6_package import MAX_ACTIONS, _slug, validation_seeds

    worker_dir = Path(worker_dir)
    resolved_id = _slug(worker_dir) if game_id is None else str(game_id)
    seed = spec_layout_seed(worker_dir) if authored_seed is _UNSET else authored_seed
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise TypeError(f"authored_seed must be an int or None, got {seed!r}")
    seeds = validation_seeds(cfg, resolved_id, None if seed is None else int(seed))
    # validation_seeds has already refused a config without an int batch.seed,
    # so this read cannot be the thing that fails.
    batch_seed = int(cfg["batch"]["seed"])
    return {
        "schema": SEEDS_SCHEMA,
        "game_id": resolved_id,
        "batch_seed": batch_seed,
        "authored_seed": None if seed is None else int(seed),
        "count": len(seeds),
        "max_actions": int(MAX_ACTIONS),
        "stage_tag": "s6",
        "derivation": SEEDS_DERIVATION,
        "seeds": [int(value) for value in seeds],
    }


def write_seeds_sidecar(
    worker_dir: Path,
    cfg: Mapping,
    *,
    game_id: str | None = None,
    authored_seed: int | None | object = _UNSET,
) -> dict:
    """Write `<worker>.seeds.json` atomically; return the payload written.

    Atomic (tmp + `os.replace`) for the reason S1's `idea.json` copy is: the
    worker's own test run reads this file, and a reader must never see half of
    one. The bytes are deterministic (`sort_keys`), so re-writing an unchanged
    plan is a no-op the operator can diff.
    """
    payload = seed_plan(worker_dir, cfg, game_id=game_id, authored_seed=authored_seed)
    return _write_seeds_payload(worker_dir, payload)


def _write_seeds_payload(worker_dir: Path, payload: Mapping) -> dict:
    """The sidecar's one writer — `resync_worker` derives its plan EARLY (before
    it touches the tree) and hands the payload here at the end."""
    path = seeds_sidecar_path(worker_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return dict(payload)


def resync_worker(
    worker_dir: Path,
    *,
    cfg: Mapping | None = None,
    game_id: str | None = None,
    authored_seed: int | None | object = _UNSET,
    python_bin: Path | None = None,
) -> dict:
    """Bring an EXISTING worker to today's scaffold generation. Operator-invoked.

    Scaffolds are instantiated once and never migrate (`orchestrator`'s S2
    runner copies the template only when the worker dir is absent), so a worker
    born before a template change keeps its old `tests/` forever and its REPAIR
    path raises `template drift` instead of repairing. That is deliberate — a
    scaffold change must not reach a worker behind the operator's back — and it
    is also why reviving a parked slot needs an explicit step. This is it:

      * every non-editable file is replaced with today's template copy, and any
        file that is no longer part of the scaffold is deleted (left behind, it
        would be hashed into the new manifest as a scaffold file and then make
        every later `repair_worker` raise "absent from the template");
      * `worker.mk` is regenerated, both manifests are rebuilt from the
        resulting tree, and the scope check must come back clean. The EDITABLE
        pair's recorded hashes are carried forward from the old manifest
        unchanged: those entries mean "the bytes this worker was BORN with",
        `s2_implement.worker_is_bare` reads them to decide whether a green-loop
        attempt gets the fix prompt or the whole mission re-issued, and
        re-hashing an implemented pair into the manifest would tell that check
        the implementation is still the scaffold;
      * with a `cfg`, the E-0 seed sidecar is written, which is what arms the
        scaffold's seed sweep for the revived slot. WITHOUT one, the worker
        comes forward but its sweep premise-skips;
      * `game.py` and `solver.py` are never read for anything but their
        digests, which are compared before and after — the whole point is to
        bring the harness forward UNDER an implementation, not to touch it.

    Returns `{"changes": [human lines], "manifest": {...}, "seeds": {...}|None}`;
    an empty `changes` means the worker was already on today's generation.
    """
    worker_dir = Path(worker_dir).resolve()
    if not worker_dir.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker_dir}")
    if not TEMPLATE_DIR.is_dir():
        raise FileNotFoundError(f"worker template missing: {TEMPLATE_DIR}")
    sibling = worker_dir.with_name(worker_dir.name + ".manifest.json")
    if not sibling.is_file():
        raise FileNotFoundError(
            f"pipeline manifest copy missing: {sibling} — {worker_dir} is not an instantiated "
            "worker, so it has no scaffold generation to bring forward; instantiate it instead"
        )
    born_with = json.loads(sibling.read_text(encoding="utf-8")).get("files") or {}
    editable_before = {}
    for name in EDITABLE:
        path = worker_dir / name
        if not path.is_file():
            raise FileNotFoundError(
                f"{worker_dir} has no {name} — resync never writes the editable pair, so a "
                "tree missing it cannot be brought forward; instantiate it instead"
            )
        editable_before[name] = _sha256(path)
    # Derived BEFORE anything is written: a seed plan that cannot be resolved
    # (no spec beside the worker, a non-int layout.seed, a config without
    # batch.seed) must refuse the resync with the tree untouched, not leave a
    # half-migrated worker behind.
    plan = None if cfg is None else seed_plan(
        worker_dir, cfg, game_id=game_id, authored_seed=authored_seed
    )

    template = _walk(TEMPLATE_DIR)
    scaffold = {rel for rel in template if rel not in EDITABLE} | {GENERATED}
    changes: list[str] = []

    present = _walk(worker_dir)
    emptied: set[Path] = set()
    for rel in sorted(present):
        if rel in EDITABLE or rel in scaffold:
            continue
        present[rel].unlink()
        emptied.add(present[rel].parent)
        changes.append(f"removed {rel} (not in today's scaffold)")
    # Same empty-directory sweep `repair_worker` does, for the same reason: a
    # `helpers/` husk would otherwise survive every later repair.
    for parent in sorted(emptied, key=lambda p: len(p.parts), reverse=True):
        while parent != worker_dir and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            changes.append(f"removed empty directory {parent.relative_to(worker_dir).as_posix()}/")
            parent = parent.parent

    for rel, source in sorted(template.items()):
        if rel in EDITABLE:
            continue
        target = worker_dir / rel
        if target.is_file() and _sha256(target) == _sha256(source):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        changes.append(f"synced {rel}")

    generated = worker_dir / GENERATED
    before = generated.read_bytes() if generated.is_file() else None
    _write_worker_mk(worker_dir, Path(python_bin) if python_bin else DEFAULT_PYTHON)
    if generated.read_bytes() != before:
        changes.append(f"regenerated {GENERATED}")

    manifest = build_manifest(worker_dir)
    # The born-with hashes, carried forward (see the docstring): an editable
    # entry the old manifest already recorded is NOT re-hashed. A pair the old
    # manifest somehow did not record keeps today's hash, which is the only
    # answer available.
    for name in EDITABLE:
        if name in born_with:
            manifest["files"][name] = born_with[name]
    manifest_json = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    for path in (worker_dir / MANIFEST_NAME, sibling):
        changed = not path.is_file() or path.read_text(encoding="utf-8") != manifest_json
        path.write_text(manifest_json, encoding="utf-8")
        if changed:
            changes.append(f"rebuilt {path.name}")

    seeds: dict | None = None
    if plan is not None:
        seeds = _write_seeds_payload(worker_dir, plan)
        changes.append(
            f"wrote {seeds_sidecar_path(worker_dir).name} — {len(seeds['seeds'])} seed(s) "
            f"for game_id {seeds['game_id']!r}"
        )

    for name, digest in editable_before.items():
        if _sha256(worker_dir / name) != digest:
            raise RuntimeError(
                f"resync changed {name} in {worker_dir} — the editable pair is the one thing "
                "it must never touch"
            )
    violations = verify_worker(worker_dir)
    if violations:
        raise RuntimeError(
            f"resync did not leave {worker_dir} scope-clean: {violations}"
        )
    return {"changes": changes, "manifest": manifest, "seeds": seeds}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Instantiate, verify or resync a worker scaffold")
    parser.add_argument("--dest", required=True, help="worker directory (e.g. out/workers/w001)")
    parser.add_argument("--force", action="store_true", help="replace an existing worker dir")
    parser.add_argument("--verify", action="store_true", help="verify edit scope instead of instantiating")
    parser.add_argument("--resync", action="store_true",
                        help="bring an EXISTING worker to today's scaffold generation (E-0)")
    parser.add_argument("--config",
                        help="batch config (--resync only): also write the S6 seed sidecar")
    parser.add_argument("--game-id",
                        help="--resync only: game_id the seeds derive from (default: the slug)")
    parser.add_argument("--authored-seed", type=int,
                        help="--resync only: the authored default seed (default: the spec's "
                             "game.layout.seed)")
    args = parser.parse_args(argv)

    if args.resync and args.verify:
        parser.error("--resync and --verify are different jobs; pick one")
    if args.resync and args.force:
        parser.error("--force REPLACES a worker (losing game.py/solver.py); --resync brings the "
                     "existing one forward and never touches them")
    for flag, value in (("--config", args.config), ("--game-id", args.game_id),
                        ("--authored-seed", args.authored_seed)):
        if value is not None and not args.resync:
            parser.error(f"{flag} is a --resync option")

    dest = Path(args.dest)
    if args.resync:
        cfg = None
        if args.config is not None:
            from .config import load_config
            cfg = load_config(args.config)
        result = resync_worker(
            dest, cfg=cfg, game_id=args.game_id,
            authored_seed=_UNSET if args.authored_seed is None else args.authored_seed,
        )
        print(f"[worker] resynced {dest.resolve()} — {len(result['changes'])} change(s)")
        for line in result["changes"]:
            print(f"[worker]   {line}")
        if cfg is None:
            print("[worker] NOTE: no --config, so no seed sidecar was written — this worker's "
                  "seed sweep will SKIP until one is")
        return 0

    if args.verify:
        violations = verify_worker(dest)
        if violations:
            print(f"[worker] SCOPE FAIL ({len(violations)}):")
            for line in violations:
                print(f"[worker]   {line}")
            return 1
        print("[worker] scope OK")
        return 0

    manifest = instantiate_worker(dest, force=args.force)
    print(f"[worker] instantiated {dest.resolve()} — {len(manifest['files'])} files "
          f"hashed, editable: {manifest['editable']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
