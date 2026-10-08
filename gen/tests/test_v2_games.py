"""P-3 blind lane — the `games/` shelf: T1-T6, FROM THE FROZEN CONTRACT ALONE.

Run: .venv/bin/python -m pytest gen/tests/test_v2_games.py -q

BLIND PROVENANCE. `docs/v2/contracts/P-3-games-promotion.md` is the only
statement of intent this file was written from. The promoter's body was never
read; neither was any diff. The surfaces this file DID read are all public and
are named at the assertion that leans on them:

  P-3 §Work 1-3 + §"Blind lane"   — every pin below traces to one of T1-T6.
  gen/s6_package.py PUBLIC NAMES  — `OUT_SUFFIX`, `PACKAGE_DIRNAME`,
      `TSV_DIRNAME`/`TSV_NAME`, `MANIFEST_NAME`, `DUCK_INTAKE_DIRNAME`,
      `duck_intake_rel()`, `PLAY_TAGS`, `PLAY_DEFAULT_FPS`,
      `PREVIEW_TITLE_SUFFIX`, `run_s6`'s signature. Names and signatures only.
  gen/tests/fixtures/s6_seeded   — the reference worker P-3 T6 names.
  gen/tests/test_b10_package.py  — the synthetic-worker pattern (stage a tmp
      copy, run the REAL run_s4 then run_s6 beside it, never the repo's out/).
  duckWM local-docs/arc-agi-3-games/tools/play/server.py `discover_games`
      (READ-ONLY third-party consumer, cited by P-3's own Evidence block):
      `glob(GAMES_DIR / "*" / "*" / "metadata.json")`, and then
      `glob(dirname(meta_path) + "/*.py")` with `if not py: continue` — a
      metadata.json with NO .py beside it is silently dropped from the menu.
      That second line is why T5 asserts a .py sibling.

HOUSE RULE, enforced by the autouse guard below: no test may write into the
repo's real `games/`, `out/play/` or `out/corpus/`. Every promoted tree, every
corpus scanned and every play mirror in this file is a tmp root.

CONTRACT AMBIGUITIES this file had to take a position on. Reported loudly,
never resolved quietly:

  A. THE ROOT SEAM. `promote_game(worker_dir, cfg, ...)`, `withdraw_game(slug)`
     and the backfill are all specified WITHOUT a parameter for the shelf or
     for the corpus root, yet the house rule forbids this file from touching
     the real ones. `_seam` therefore finds the keyword (or, for the CLI, the
     flag) that aims each call at a tmp root, taking the first name in the
     candidate list the signature actually offers; a call with NO such seam
     FAILS LOUDLY, naming everything probed, and is never run. A seamless
     promoter is a REPORTED FAILURE of this file, not a licence to write into
     the repo.
  B. WHICH SURFACE THE BACKFILL IS. §Work 3 says "`python -m
     gen.tools.promote_games --backfill` or an s6 __main__ flag — pick one,
     document". Both are accepted: a `backfill`-ish callable on the promoter
     module or on `gen.s6_package`, else `main(["--backfill"])` on either.
  C. WHERE THE FOUR ENTRIES SIT. §Work 1 lists FOUR entries under
     `games/<slug>/`, and in the SAME bullet requires the
     `<root>/*/*/metadata.json` glob to find metadata.json with
     PLAY_GAMES_DIR=games — which needs it one level DEEPER, spelled there as
     "`games/<slug>/<hash8-or-"game">/…`" with the layout left to the
     implementer ("pick the layout that keeps ONE canonical copy of game.py").
     `_build_dir` therefore locates THE BUILD DIR by structure — the directory
     holding `game.py`, which is `games/<slug>/` itself or the single licensed
     level below it — and T1 counts the four entries THERE. When the build dir
     is nested, T1 additionally pins that `games/<slug>/` holds nothing but it,
     which is what "ONE canonical copy of game.py" means. T5 then insists on
     the glob, which only the nested layout can satisfy.
  D. `paths_note`'s HOME, and WHAT `paths` IS RELATIVE TO. "with a `paths_note`
     field naming the rule" does not say whether it is a top-level manifest key
     or a member of `paths`; either is accepted, its ABSENCE is a failure. And
     "rewritten RELATIVE to `games/<slug>/`" cannot be taken literally once
     ambiguity C moves the tree into a build dir, so T2 pins the invariant that
     survives either layout: every entry resolves, against ONE consistent base
     that is the build dir or `games/<slug>/`, to something actually promoted.
  E. THE "pulled" MANIFEST (T4). No manifest on disk ever carries verdict
     "pulled" today — a pull happens at review, AFTER S6 wrote `packaged`, and
     `pulled` is an orchestrator slot state, not an S6 verdict. T4 nonetheless
     asks for "one pulled" manifest, so the only coherent reading of
     "pulled/seed-rejected games excluded by verdict" is ONLY `verdict ==
     "packaged"` promotes. The two excluded slots are real packaged slots whose
     manifest `verdict` was overwritten with "pulled" / "seed-reject"; nothing
     else in them was touched.
  F. THE PROMOTED `game_id`. §Work 1 says "at the play-server shape", whose
     existing mirror writes `<slug>-<hash8>`; but a shelf that keeps ONE
     canonical entry per slug could reasonably use the bare slug. T5 accepts
     either and says so in the failure message.
  G. T6's "pre-contract behavior" cannot be a git delta ("Pin live behavior,
     not git deltas"), so the two path-free S6 artifacts were MEASURED on this
     file's own reference slot BEFORE the promoter existed and are hard-pinned
     below as `PRE_CONTRACT_*_SHA256`. Those bytes are a function of
     fixtures/s6_seeded + config/b001-pilot.yaml + S4 seed 7 + arcengine 0.9.3
     + python 3.12.8; if any of those move the pin must be RE-MEASURED, and the
     failure message says so. Its job is to catch promotion-induced drift.
  H. NOT COVERED by T1-T6, and so not tested here (flagged to the lead):
     §Work 1's "a DIFFERENT game_hash for an existing slug replaces the entry
     and says so in the return value", and §Work 2's orchestrator call sites
     (the `reviewed -> packaged` transition and the pull path). T4's
     double-backfill covers only the SAME-hash idempotent half.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from gen import s6_package as s6
from gen.config import REPO_ROOT, load_config
from gen.s4_baselines import METADATA_NAME, run_s4
from gen.s4_baselines import OUT_SUFFIX as S4_SUFFIX

TESTS = Path(__file__).resolve().parent
SEEDED = TESTS / "fixtures" / "s6_seeded"
PILOT_CONFIG = "config/b001-pilot.yaml"
_CFG = load_config(PILOT_CONFIG)

#: the S4 seed every staged slot uses (verdict `fit` on the reference fixture).
S4_SEED = 7
#: fixtures/s6_seeded sits on the spec §7 floor.
LEVEL_COUNT = 6

# --- the repo surfaces no test may write into (P-3 §Hard rules + the brief) --
SHELF_DIRNAME = "games"
REPO_SHELF = REPO_ROOT / SHELF_DIRNAME
REPO_OUT = REPO_ROOT / "out"
REPO_CORPUS = REPO_OUT / "corpus"

# --- the corpus this file builds in tmp (§Work 3's scan shape) --------------
#: `out/corpus/*/*/worker.s6/package/manifest.json` — one batch level, one slug.
BATCH = "p3-blind"
WORKER_DIRNAME = "worker"
SPEC_NAME = "spec.yaml"
SPEC_YAML = "game:\n  slug: {slug}\n"
PACKAGED_SLUGS = ("alpha-game", "beta-game")
#: ambiguity E — real packaged slots with an overwritten manifest verdict.
EXCLUDED_SLUGS = {"pulled-game": "pulled", "reject-game": "seed-reject"}
ALL_SLUGS = (*PACKAGED_SLUGS, *EXCLUDED_SLUGS)

# --- the promoted tree (§Work 1) --------------------------------------------
GAME_PY = "game.py"
PACKAGE = s6.PACKAGE_DIRNAME
MANIFEST_NAME = s6.MANIFEST_NAME
METADATA_JSON = "metadata.json"
TSV_REL = Path(PACKAGE) / s6.TSV_DIRNAME / s6.TSV_NAME
MANIFEST_REL = Path(PACKAGE) / MANIFEST_NAME
REPORT_NAME = "s6-report.json"
#: server.py:103 — `<root>/*/*/metadata.json`, with PLAY_GAMES_DIR at games/.
PLAY_GLOB = "*/*/metadata.json"
PLAY_METADATA_KEYS = {"game_id", "title", "tags", "baseline_actions", "default_fps"}
#: the sprite_lib intake glob, relative to a `--sample-dir` (C-5 / §Work 1).
SPRITE_LIB_GLOB = "*_perfect/human_policy/unprocessed_game.tsv"

#: the b10-frozen operator-manifest top-level keys. T6: out/ stays AS-IS.
OUT_MANIFEST_KEYS = {
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
#: Evidence: `manifest.paths` embeds ABSOLUTE machine paths EXCEPT duck_intake.
OUT_ABSOLUTE_PATH_KEYS = (
    "worker",
    "out_dir",
    "s4_metadata",
    "tsv",
    "manifest",
    "play_mirror",
    "report",
)

# --- T6: MEASURED PRE-MERGE on the reference slot (ambiguity G) -------------
#: sha256 of `worker.s6/package/tsv/level-set.tsv` for slug "alpha-game".
PRE_CONTRACT_TSV_SHA256 = "f2ee2f9200f1e23f8fc6a237fbef0c84bb758a5e1a122bff9e2a47e6fd7e0a37"
#: sha256 of `out/play/alpha-game/<hash8>/metadata.json` for the same run.
PRE_CONTRACT_PLAY_METADATA_SHA256 = (
    "16516beb0ab1b0b8442d611cbece2f778f43b2d197523e998ceecea7274b0778"
)
#: game_hash[:8] of fixtures/s6_seeded (sha(game.py + solver.py)).
PRE_CONTRACT_HASH8 = "f4d25704"
#: S4's baseline_actions at seed 7 on the reference fixture.
PRE_CONTRACT_BASELINE_ACTIONS = [14, 32, 11, 11, 12, 38]
RE_MEASURE = (
    " — this sha was MEASURED PRE-MERGE on fixtures/s6_seeded at S4 seed 7 with "
    "config/b001-pilot.yaml, arcengine 0.9.3, python 3.12.8. If one of those "
    "moved, RE-MEASURE the pin; otherwise the promoter changed out/ bytes, "
    "which P-3 §Work 5 forbids."
)

# --- the promoter's surface (§Work 1-3) -------------------------------------
PROMOTER_MODULE = "gen.tools.promote_games"
PROMOTE_NAME = "promote_game"
WITHDRAW_NAME = "withdraw_game"
BACKFILL_NAMES = ("backfill", "run_backfill", "backfill_games", "promote_backfill", "promote_all")
BACKFILL_FLAG = "--backfill"

#: ambiguity A — keyword candidates for the shelf root.
SHELF_KWARGS = (
    "games_root",
    "games_dir",
    "shelf_root",
    "shelf",
    "games",
    "dest_root",
    "target_root",
    "dest",
    "root",
)
#: ambiguity A — keyword candidates for the corpus root.
CORPUS_KWARGS = ("corpus_root", "corpus", "out_root", "out_dir", "repo_root", "root")
#: ambiguity A — the same two roots, spelled the argparse way.
SHELF_FLAGS = ("games-root", "games-dir", "games", "shelf", "dest")
CORPUS_FLAGS = ("corpus-root", "corpus")


# --------------------------------------------------------------------------- #
# helpers — trees, json, loud failures
# --------------------------------------------------------------------------- #


def _tree(root: Path | None) -> dict[str, str] | None:
    """`{relative path: sha256 | "<dir>"}` for everything under `root`."""
    if root is None or not Path(root).exists():
        return None
    root = Path(root)
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(root))
        if path.is_dir():
            snapshot[rel] = "<dir>"
        else:
            snapshot[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def _shape(root: Path | None) -> dict[str, object] | None:
    """`{relative path: <dir> | size}` — the cheap guard for a big tree: it
    catches every addition, removal and length change without hashing 110MB."""
    if root is None or not Path(root).exists():
        return None
    root = Path(root)
    return {
        str(path.relative_to(root)): "<dir>" if path.is_dir() else path.stat().st_size
        for path in sorted(root.rglob("*"))
        if "__pycache__" not in path.parts
    }


def _files(root: Path) -> list[str]:
    """Relative paths of the FILES under `root`, sorted, posix-spelled."""
    return sorted(
        str(path.relative_to(root).as_posix())
        for path in Path(root).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def _entries(root: Path) -> list[str]:
    return sorted(path.name for path in Path(root).iterdir() if path.name != "__pycache__")


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _string_values(node) -> list[str]:
    """Every string VALUE reachable in a parsed json document (keys excluded)."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [item for value in node.values() for item in _string_values(value)]
    if isinstance(node, (list, tuple)):
        return [item for value in node for item in _string_values(value)]
    return []


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _promoter_module():
    """`gen.tools.promote_games`, or None if §Work 3 chose the s6 flag."""
    try:
        return importlib.import_module(PROMOTER_MODULE)
    except ModuleNotFoundError:
        return None


def _surface_modules():
    """Where a P-3 name may live: `gen.s6_package` (§Work 2 gives it ownership)
    and the §Work 3 promoter CLI module."""
    modules = [s6]
    promoter = _promoter_module()
    if promoter is not None:
        modules.append(promoter)
    return modules


def _lookup(name: str):
    """A promoter callable, on `gen.s6_package` (§Work 2: s6 owns both) or the
    promoter module. Returns None when it does not exist yet."""
    for module in _surface_modules():
        found = getattr(module, name, None)
        if callable(found):
            return found
    return None


def _require(name: str):
    found = _lookup(name)
    if found is None:
        looked = ", ".join(module.__name__ for module in _surface_modules())
        pytest.fail(
            f"P-3 freezes `{name}` and it does not exist on any of [{looked}]. "
            "Pre-merge this is the EXPECTED failure; post-merge it means the "
            "promoter shipped a different name than the contract froze."
        )
    return found


def _first_kwarg(fn, candidates) -> str | None:
    params = inspect.signature(fn).parameters
    return next((name for name in candidates if name in params), None)


def _missing_required(fn, *, positional: int, supplied) -> list[str]:
    """Required parameters this file has not supplied — a loud report, not a
    TypeError from deep inside the promoter."""
    kinds = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    )
    params = [p for p in inspect.signature(fn).parameters.values() if p.kind in kinds]
    known = {p.name for p in params[:positional]} | set(supplied)
    return [
        p.name
        for p in params
        if p.default is inspect.Parameter.empty and p.name not in known
    ]


def _check_signature(fn, *, positional: int, supplied) -> None:
    missing = _missing_required(fn, positional=positional, supplied=supplied)
    if missing:
        pytest.fail(
            f"`{fn.__qualname__}{inspect.signature(fn)}` requires {missing}, which this "
            "blind file cannot guess. P-3 froze the call as "
            "`promote_game(worker_dir, cfg, ...)` / `withdraw_game(slug)`; a further "
            "REQUIRED parameter is a deviation to report, not to paper over."
        )


_NO_SEAM = (
    "P-3's house rule forbids this file from writing into {real}, and {what} offers no "
    "way to aim it elsewhere: no keyword in {kwargs}. NOT WEAKENED and NOT run against "
    "the repo — the promoter needs a test seam, the b10 precedent being a keyword "
    "(`run_s6(..., play_root=...)`)."
)


def _seam(fn, candidates, target: Path, *, real: Path) -> dict:
    """The keyword that aims `fn` at a tmp root, or a loud refusal to run it."""
    name = _first_kwarg(fn, candidates)
    if name is None:
        pytest.fail(
            _NO_SEAM.format(
                real=real, what=f"`{fn.__qualname__}{inspect.signature(fn)}`",
                kwargs=list(candidates),
            )
        )
    return {name: target}


def _promote(slot, shelf: Path):
    fn = _require(PROMOTE_NAME)
    kwargs = _seam(fn, SHELF_KWARGS, shelf, real=REPO_SHELF)
    _check_signature(fn, positional=2, supplied=kwargs)
    return fn(slot.worker, _CFG, **kwargs)


def _withdraw(slug: str, shelf: Path):
    fn = _require(WITHDRAW_NAME)
    kwargs = _seam(fn, SHELF_KWARGS, shelf, real=REPO_SHELF)
    _check_signature(fn, positional=1, supplied=kwargs)
    return fn(slug, **kwargs)


def _cli_flags(main_fn, capsys) -> set[str]:
    """The long flags `main`'s argparse advertises (ambiguity B, CLI branch)."""
    try:
        main_fn(["--help"])
    except SystemExit:
        pass
    except Exception:  # noqa: BLE001 — a main() with no --help is not a failure
        return set()
    text = capsys.readouterr().out
    return set(re.findall(r"--[a-z0-9][a-z0-9-]*", text))


def _backfill(capsys, *, corpus_root: Path, shelf: Path) -> str:
    """Run the backfill through whichever §Work 3 surface shipped. Returns stdout.

    The CLI is tried FIRST because §Work 3 spells the backfill as a command
    (`--backfill`) and requires it to "Print a table" — printing is a CLI job. A
    library callable is the documented fallback (ambiguity B). Both roots are
    aimed at tmp BEFORE anything is invoked; a missing seam fails loudly and
    nothing runs.
    """
    # §Work 3's two surfaces are `python -m gen.tools.promote_games --backfill`
    # and "an s6 __main__ flag", so EVERY module's `main` is asked whether it
    # carries --backfill — the promoter module first.
    main_fn, seen = None, {}
    for module in reversed(_surface_modules()):
        candidate = getattr(module, "main", None)
        if not callable(candidate):
            continue
        seen[module.__name__] = sorted(_cli_flags(candidate, capsys))
        if BACKFILL_FLAG in seen[module.__name__]:
            main_fn = candidate
            flags = set(seen[module.__name__])
            break
    if main_fn is None:
        fn = next((found for name in BACKFILL_NAMES if (found := _lookup(name))), None)
        if fn is None:
            pytest.fail(
                f"P-3 §Work 3 freezes a backfill; no `main` carrying {BACKFILL_FLAG} "
                f"(the CLIs advertise {seen}) and no callable in {list(BACKFILL_NAMES)} on "
                f"[{', '.join(m.__name__ for m in _surface_modules())}]."
            )
        kwargs = {}
        kwargs.update(_seam(fn, CORPUS_KWARGS, corpus_root, real=REPO_CORPUS))
        kwargs.update(_seam(fn, SHELF_KWARGS, shelf, real=REPO_SHELF))
        _check_signature(fn, positional=0, supplied=kwargs)
        capsys.readouterr()
        fn(**kwargs)
        return capsys.readouterr().out
    # Only ROOT-NAMING flags are trusted here: `--out` already means the S6 out
    # dir on s6.main, so guessing it would be a DIFFERENT instruction.
    argv = [BACKFILL_FLAG]
    for names, target, real in (
        (CORPUS_FLAGS, corpus_root, REPO_CORPUS),
        (SHELF_FLAGS, shelf, REPO_SHELF),
    ):
        flag = next((f"--{name}" for name in names if f"--{name}" in flags), None)
        if flag is None:
            pytest.fail(
                _NO_SEAM.format(
                    real=real,
                    what=f"`{main_fn.__module__} {BACKFILL_FLAG}`",
                    kwargs=[f"--{name}" for name in names],
                )
            )
        argv += [flag, str(target)]
    capsys.readouterr()
    try:
        code = main_fn(list(argv))
    except SystemExit as exc:
        code = exc.code
    captured = capsys.readouterr()
    assert "unrecognized arguments" not in captured.err, (
        f"the backfill CLI rejected {argv}: {captured.err.strip()}"
    )
    assert (0 if code is None else int(code)) == 0, f"{argv} exited {code}: {captured.out}"
    return captured.out


# --------------------------------------------------------------------------- #
# the promoted layout (ambiguity C)
# --------------------------------------------------------------------------- #


def _metadata_path(promoted: Path) -> Path:
    """The one metadata.json inside a promoted game dir, at either depth."""
    found = sorted(Path(promoted).rglob(METADATA_JSON))
    assert len(found) == 1, (
        f"a promoted game must carry exactly ONE metadata.json (§Work 1); {promoted.name} "
        f"has {[str(p.relative_to(promoted)) for p in found]}"
    )
    return found[0]


def _build_dir(game_dir: Path) -> Path:
    """The directory holding §Work 1's four entries (ambiguity C).

    Resolved by STRUCTURE, never by a constant: it is `games/<slug>/` when
    game.py sits there, else the single `<hash8-or-"game">/` level below it.
    """
    if (game_dir / GAME_PY).is_file():
        return game_dir
    nested = sorted(
        path for path in game_dir.iterdir() if path.is_dir() and (path / GAME_PY).is_file()
    )
    assert len(nested) == 1, (
        f"§Work 1: the promoted build lives at games/<slug>/ or at ONE "
        f'games/<slug>/<hash8-or-"game">/ below it; {game_dir} holds {_entries(game_dir)} and '
        f"{len(nested)} of its subdirectories carry a {GAME_PY}"
    )
    return nested[0]


# --------------------------------------------------------------------------- #
# staging — a corpus-shaped slot with a REAL packaged S6 tree, all in tmp
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Slot:
    """`<tmp>/out/corpus/<batch>/<slug>/` with worker + worker.s4 + worker.s6."""

    slug: str
    slot: Path
    worker: Path
    spec: Path
    out_dir: Path
    s4_dir: Path
    play_root: Path
    manifest: dict
    s4_metadata: dict

    @property
    def hash8(self) -> str:
        return self.manifest["game_hash"][:8]


def _stage_slot(corpus_root: Path, slug: str) -> Slot:
    """Stage `fixtures/s6_seeded` as `<corpus>/<batch>/<slug>/worker` and run the
    REAL S4 + S6 beside it (the b10 pattern), so `worker.s6/package/` is a
    genuine packaged tree. Every path is under `corpus_root`'s tmp tree."""
    slot = corpus_root / BATCH / slug
    worker = slot / WORKER_DIRNAME
    slot.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SEEDED, worker, ignore=shutil.ignore_patterns("__pycache__"))
    spec = slot / SPEC_NAME
    spec.write_text(SPEC_YAML.format(slug=slug), encoding="utf-8")

    s4_report = run_s4(worker, _CFG, seed=S4_SEED)
    assert s4_report["verdict"] == "fit", f"{slug}: S4 verdict {s4_report['verdict']}"
    s4_dir = worker.parent / (worker.name + S4_SUFFIX)

    play_root = corpus_root.parent / "play"
    s6_report = s6.run_s6(worker, _CFG, spec_path=spec, play_root=play_root)
    assert s6_report["verdict"] == s6.VERDICT_PACKAGED, s6_report["verdict"]
    out_dir = worker.parent / (worker.name + s6.OUT_SUFFIX)

    return Slot(
        slug=slug,
        slot=slot,
        worker=worker,
        spec=spec,
        out_dir=out_dir,
        s4_dir=s4_dir,
        play_root=play_root,
        manifest=_load_json(out_dir / MANIFEST_REL),
        s4_metadata=_load_json(s4_dir / METADATA_NAME),
    )


class Corpus:
    """A tmp `out/corpus` holding the four T4 slots."""

    def __init__(self, root: Path):
        self.root = root
        self.slots = {slug: _stage_slot(root, slug) for slug in ALL_SLUGS}
        for slug, verdict in EXCLUDED_SLUGS.items():
            self._set_verdict(self.slots[slug], verdict)

    @staticmethod
    def _set_verdict(slot: Slot, verdict: str) -> None:
        """Ambiguity E: the ONLY synthetic edit — the manifest's verdict field."""
        path = slot.out_dir / MANIFEST_REL
        manifest = _load_json(path)
        manifest["verdict"] = verdict
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def slot(self, slug: str) -> Slot:
        return self.slots[slug]


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _repo_is_never_the_shelf():
    """P-3 §Hard rules + the brief: tmp roots only, never the repo's own trees.

    `out/play/` is small, so it is checked byte-for-byte. The real shelf and the
    real corpus are both ~100MB and both GROW as the programme runs, so they are
    checked by SHAPE — names plus sizes, which catches any entry a stray call
    would add, remove or resize, at no hashing cost per test.
    """
    play_root = Path(s6.PLAY_ROOT)
    watched = {
        f"the repo shelf {REPO_SHELF}": (_shape, REPO_SHELF),
        f"the repo play mirror {play_root}": (_tree, play_root),
        f"the repo corpus {REPO_CORPUS}": (_shape, REPO_CORPUS),
    }
    before = {what: snap(root) for what, (snap, root) in watched.items()}
    yield
    for what, (snap, root) in watched.items():
        assert snap(root) == before[what], f"a test wrote into {what}"


@pytest.fixture(scope="session")
def corpus(tmp_path_factory) -> Corpus:
    """ONE tmp corpus, four real packaged slots (two with an edited verdict)."""
    return Corpus(tmp_path_factory.mktemp("p3corpus") / "out" / "corpus")


@pytest.fixture
def reference(corpus) -> Slot:
    return corpus.slot(PACKAGED_SLUGS[0])


@pytest.fixture
def shelf(tmp_path) -> Path:
    """A tmp stand-in for the tracked top-level `games/`."""
    root = tmp_path / SHELF_DIRNAME
    root.mkdir()
    return root


@dataclass(frozen=True)
class Promoted:
    shelf: Path
    slot: Slot
    slug: str
    dir: Path          # games/<slug>/
    build: Path        # where the four §Work 1 entries live (ambiguity C)
    result: object
    manifest: dict


@pytest.fixture
def promoted(reference, shelf) -> Promoted:
    """`promote_game` on the reference slot, into a tmp shelf."""
    result = _promote(reference, shelf)
    slug = reference.manifest["slug"]
    game_dir = shelf / slug
    assert game_dir.is_dir(), (
        f"§Work 1: promote_game must write `games/<slug>/`; {shelf} holds {_entries(shelf)} "
        f"and the manifest's slug is {slug!r}"
    )
    build = _build_dir(game_dir)
    return Promoted(
        shelf=shelf,
        slot=reference,
        slug=slug,
        dir=game_dir,
        build=build,
        result=result,
        manifest=_load_json(build / MANIFEST_REL),
    )


# --------------------------------------------------------------------------- #
# surface — one named failure pre-merge instead of many confusing ones
# --------------------------------------------------------------------------- #


def test_the_promoter_surface_exists(capsys):
    """P-3 §Work 1-3: promote_game, withdraw_game, and a backfill entry point.

    One named failure pre-merge, instead of fourteen confusing ones.
    """
    missing = [name for name in (PROMOTE_NAME, WITHDRAW_NAME) if _lookup(name) is None]
    cli = {
        module.__name__: sorted(_cli_flags(module.main, capsys))
        for module in _surface_modules()
        if callable(getattr(module, "main", None))
    }
    has_backfill = any(_lookup(name) for name in BACKFILL_NAMES) or any(
        BACKFILL_FLAG in flags for flags in cli.values()
    )
    if not has_backfill:
        missing.append(f"one of {list(BACKFILL_NAMES)} or a `main` carrying {BACKFILL_FLAG}")
    assert not missing, (
        f"P-3 freezes {missing}; nothing on "
        f"[{', '.join(m.__name__ for m in _surface_modules())}] provides it. CLIs seen: {cli}"
    )


# --------------------------------------------------------------------------- #
# T1 — tree shape
# --------------------------------------------------------------------------- #


def test_t1_the_promoted_tree_is_exactly_the_four_entries(promoted):
    """T1: "exactly the four entries" — game.py, spec.yaml, package/,
    metadata.json — in the build dir (ambiguity C), and nothing else beside it."""
    entries = _entries(promoted.build)
    assert set(entries) == {GAME_PY, SPEC_NAME, PACKAGE, METADATA_JSON}, (
        f"§Work 1 lists FOUR entries (game.py, spec.yaml, package/, metadata.json); "
        f"{promoted.build} holds {entries}"
    )
    assert (promoted.build / GAME_PY).is_file()
    assert (promoted.build / SPEC_NAME).is_file()
    assert (promoted.build / PACKAGE).is_dir()
    assert (promoted.build / METADATA_JSON).is_file()
    if promoted.build != promoted.dir:
        assert _entries(promoted.dir) == [promoted.build.name], (
            '§Work 1: "ONE canonical copy of game.py" — games/<slug>/ carries the build dir '
            f"and nothing else; it holds {_entries(promoted.dir)}"
        )
        assert _metadata_path(promoted.dir) == promoted.build / METADATA_JSON


def test_t1_the_promoted_game_py_is_the_workers_bytes(promoted):
    """T1: "game.py bytes == the worker's" — and §Work 1's "ONE canonical copy",
    so no second copy of those bytes anywhere under games/<slug>/."""
    build_bytes = (promoted.slot.worker / GAME_PY).read_bytes()
    assert (promoted.build / GAME_PY).read_bytes() == build_bytes
    copies = sorted(path for path in promoted.dir.rglob("*.py") if path.read_bytes() == build_bytes)
    assert copies == [promoted.build / GAME_PY], [str(p.relative_to(promoted.dir)) for p in copies]


def test_t1_the_promoted_package_is_the_tsv_and_duck_intake_copies(promoted):
    """§Work 1: `package/` is "tsv + duck-intake + manifest COPIES"."""
    out_dir = promoted.slot.out_dir
    assert (promoted.build / TSV_REL).read_bytes() == (out_dir / TSV_REL).read_bytes()
    duck = s6.duck_intake_rel(promoted.slug)
    assert (promoted.build / duck).is_file(), _files(promoted.build / PACKAGE)
    assert (promoted.build / duck).read_bytes() == (out_dir / duck).read_bytes()


def test_t1_the_promoted_manifest_parses(promoted):
    """T1: "manifest parses" — and it is the same game's manifest."""
    manifest = promoted.manifest
    assert isinstance(manifest, dict) and manifest
    assert manifest["slug"] == promoted.slug
    assert manifest["verdict"] == s6.VERDICT_PACKAGED
    assert manifest["game_hash"] == promoted.slot.manifest["game_hash"]
    assert isinstance(manifest["paths"], dict) and manifest["paths"]


def test_t1_the_promoted_spec_is_the_slots_spec(promoted):
    """§Work 1 lists `spec.yaml` among the four entries."""
    assert (promoted.build / SPEC_NAME).read_bytes() == promoted.slot.spec.read_bytes()


# --------------------------------------------------------------------------- #
# T2 — relative paths
# --------------------------------------------------------------------------- #


def test_t2_no_promoted_json_value_is_an_absolute_or_repo_path(promoted):
    """T2: NO value in any promoted json starts with "/" or carries an absolute
    prefix — not the repo's, and not this test's tmp root either."""
    prefixes = {
        str(REPO_ROOT): "the repo root",
        str(promoted.slot.slot): "the corpus slot",
        str(promoted.shelf): "the shelf root",
    }
    offenders: list[str] = []
    for path in sorted(promoted.dir.rglob("*.json")):
        rel = path.relative_to(promoted.dir)
        for value in _string_values(_load_json(path)):
            if value.startswith("/"):
                offenders.append(f"{rel}: absolute value {value!r}")
                continue
            for prefix, what in prefixes.items():
                if prefix in value:
                    offenders.append(f"{rel}: {what} leaked into {value!r}")
    banner = "T2 (§Work 1: `paths` rewritten RELATIVE to games/<slug>/):\n"
    assert not offenders, banner + "\n".join(offenders)


def test_t2_every_promoted_path_entry_resolves_against_one_base(promoted):
    """T2's substance (ambiguity D): every surviving `paths` entry names something
    actually promoted, and they all share ONE base — the build dir or
    `games/<slug>/`, the two §Work 1 licenses."""
    paths = promoted.manifest["paths"]
    entries = {
        key: value
        for key, value in paths.items()
        if isinstance(value, str) and key != "paths_note"
    }
    assert entries, f"the promoted manifest's `paths` block is empty: {paths}"
    bases = {"the build dir": promoted.build, "games/<slug>/": promoted.dir}
    resolved = {
        label: [key for key, value in entries.items() if not (base / value).exists()]
        for label, base in bases.items()
    }
    assert any(not dangling for dangling in resolved.values()), (
        "§Work 1: entries whose referent is not part of the promoted tree are DROPPED or "
        f"relativized. Against the build dir {promoted.build} these resolve to nothing: "
        f"{resolved['the build dir']}; against games/<slug>/: {resolved['games/<slug>/']}. "
        f"Entries: {entries}"
    )
    assert any(TSV_REL.as_posix() in value for value in entries.values()), entries
    assert any(MANIFEST_NAME in value for value in entries.values()), entries


def test_t2_the_promoted_manifest_names_the_relativization_rule(promoted):
    """§Work 1 (ambiguity D): "with a `paths_note` field naming the rule"."""
    note = promoted.manifest.get("paths_note") or promoted.manifest["paths"].get("paths_note")
    assert isinstance(note, str) and note.strip(), (
        "the promoted manifest carries no `paths_note` (top level or inside `paths`); "
        f"top-level keys are {sorted(promoted.manifest)}"
    )


def test_t2_promotion_rewrites_nothing_but_paths(promoted):
    """§Work 1: the promoted manifest is a COPY with `paths` rewritten. Every
    other field the operator manifest carries must survive untouched."""
    operator = promoted.slot.manifest
    drifted = [
        key
        for key in sorted(set(operator) - {"paths"})
        if promoted.manifest.get(key) != operator[key]
    ]
    assert not drifted, f"promotion rewrote more than `paths`: {drifted}"
    assert set(operator) - {"paths"} <= set(promoted.manifest), (
        f"the promoted copy DROPPED {sorted(set(operator) - set(promoted.manifest))}"
    )


def test_t2_the_promoted_manifest_adds_only_the_licensed_fields(promoted):
    """§Work 1 as widened by LEAD CORRECTION 1 (2026-09-30, at merge): the
    promoted manifest is a COPY plus exactly THREE additions — `paths`
    rewritten, `paths_note`, and the `promotion` provenance block
    `{contract, shelf_entry, source_batch}`. This pin originally licensed
    `paths_note` only and went red on `promotion`; the lead ruled the
    provenance block IN (the canon/PROVENANCE.md house pattern) and widened
    the contract rather than the judgment. Anything beyond these three is
    still an unlicensed addition."""
    added = set(promoted.manifest) - set(promoted.slot.manifest)
    unlicensed = sorted(added - {"paths_note", "promotion"})
    assert not unlicensed, (
        f"the promoted manifest grew un-contracted top-level field(s) {unlicensed}; "
        "LEAD CORRECTION 1 licenses `paths_note` and `promotion` only."
    )
    block = promoted.manifest.get("promotion")
    assert isinstance(block, dict) and set(block) == {
        "contract", "shelf_entry", "source_batch"
    }, (
        f"the `promotion` block must carry exactly contract/shelf_entry/"
        f"source_batch, got {block!r}"
    )


def test_t2_duck_intake_stays_sprite_lib_globbable(promoted):
    """T2: "duck-intake stays at its sprite_lib-globbable relative location
    within the promoted package" — `*_perfect/human_policy/unprocessed_game.tsv`
    under `package/duck-intake/` (the consumer's `--sample-dir`)."""
    sample_dir = promoted.build / PACKAGE / s6.DUCK_INTAKE_DIRNAME
    assert sample_dir.is_dir(), _files(promoted.dir)
    found = sorted(sample_dir.glob(SPRITE_LIB_GLOB))
    assert len(found) == 1, (
        f"sprite_lib globs {SPRITE_LIB_GLOB!r} under --sample-dir; {sample_dir} matched "
        f"{[str(p.relative_to(sample_dir)) for p in found]}"
    )
    assert found[0] == promoted.build / s6.duck_intake_rel(promoted.slug)


# --------------------------------------------------------------------------- #
# T3 — withdraw
# --------------------------------------------------------------------------- #


def test_t3_withdraw_removes_the_promoted_tree_and_nothing_else(promoted):
    """T3: "promote then withdraw -> games/<slug>/ gone; nothing else under
    games/ touched"."""
    neighbour = promoted.shelf / "a-neighbouring-game"
    (neighbour / PACKAGE).mkdir(parents=True)
    (neighbour / GAME_PY).write_text("# not ours\n", encoding="utf-8")
    (neighbour / PACKAGE / MANIFEST_NAME).write_text('{"slug": "a-neighbouring-game"}\n',
                                                     encoding="utf-8")
    before = _tree(neighbour)

    _withdraw(promoted.slug, promoted.shelf)

    assert not promoted.dir.exists(), f"{promoted.dir} survived withdraw_game"
    assert _tree(neighbour) == before, "withdraw_game touched another game on the shelf"
    assert _entries(promoted.shelf) == [neighbour.name]


def test_t3_withdraw_of_an_unknown_slug_is_a_quiet_no_op(promoted):
    """T3: "withdraw of a non-existent slug is a quiet no-op" — tolerant of
    absence, and the shelf is byte-identical afterwards."""
    before = _tree(promoted.shelf)
    _withdraw("no-such-game-was-ever-promoted", promoted.shelf)
    assert _tree(promoted.shelf) == before, "withdrawing an absent slug changed the shelf"
    assert promoted.dir.is_dir()


# --------------------------------------------------------------------------- #
# T4 — backfill
# --------------------------------------------------------------------------- #


def test_t4_backfill_promotes_only_the_packaged_manifests(capsys, corpus, shelf):
    """T4: two packaged + one pulled + one seed-reject under a tmp out/corpus ->
    exactly the two promote, and the table counts what was DISCOVERED on disk."""
    discovered = sorted(corpus.root.glob(f"*/*/{WORKER_DIRNAME}{s6.OUT_SUFFIX}/"
                                        f"{PACKAGE}/{MANIFEST_NAME}"))
    assert len(discovered) == len(ALL_SLUGS), [str(p) for p in discovered]

    out = _backfill(capsys, corpus_root=corpus.root, shelf=shelf)

    assert _entries(shelf) == sorted(PACKAGED_SLUGS), (
        f"§Work 3: pulled/seed-rejected games are excluded BY VERDICT; the shelf holds "
        f"{_entries(shelf)}"
    )
    for slug in PACKAGED_SLUGS:
        build = _build_dir(shelf / slug)
        assert (build / MANIFEST_REL).is_file(), _files(shelf)
        assert _load_json(build / MANIFEST_REL)["slug"] == slug
        assert slug in out, f"the backfill table never names {slug}:\n{out}"
    # Format-tolerant pin of the SUBSTANCE ("count DISCOVERED from disk"): the
    # table either reports the count 4 or shows a row per discovered slot. The
    # table's layout is not frozen, so only one of the two must hold.
    numbers = {int(token) for token in re.findall(r"\d+", out)}
    reported = len(ALL_SLUGS) in numbers
    rowed = all(slug in out for slug in ALL_SLUGS)
    assert reported or rowed, (
        f"§Work 3 counts DISCOVERED from disk: the table names neither the count "
        f"{len(ALL_SLUGS)} nor all four discovered slots {list(ALL_SLUGS)}. Its numbers were "
        f"{sorted(numbers)}:\n{out}"
    )


def test_t4_running_backfill_twice_is_byte_idempotent(capsys, corpus, shelf):
    """T4: "running backfill twice is byte-idempotent"."""
    _backfill(capsys, corpus_root=corpus.root, shelf=shelf)
    first = _tree(shelf)
    assert first, "the first backfill promoted nothing"
    _backfill(capsys, corpus_root=corpus.root, shelf=shelf)
    second = _tree(shelf)
    assert second == first, (
        "the second backfill changed the shelf; differing entries: "
        f"{sorted(set(first.items()) ^ set(second.items()))}"
    )


# --------------------------------------------------------------------------- #
# T5 — play-server shape
# --------------------------------------------------------------------------- #


def test_t5_the_promoted_metadata_satisfies_the_play_server_glob(promoted):
    """T5: the promoted metadata.json satisfies `<root>/*/*/metadata.json`
    relative to games/ — and carries a .py sibling, because server.py's
    `discover_games` does `if not py: continue` right after the glob."""
    found = sorted(promoted.shelf.glob(PLAY_GLOB))
    assert len(found) == 1, (
        f"PLAY_GAMES_DIR={promoted.shelf} globbed {PLAY_GLOB!r} and matched "
        f"{[str(p.relative_to(promoted.shelf)) for p in found]}; §Work 1 requires the promoted "
        "metadata.json to sit at games/<slug>/<hash8-or-'game'>/metadata.json"
    )
    meta_path = found[0]
    #: `<root>/*/*/metadata.json` — exactly two levels below the shelf, the
    #: first of them the slug, and the second the build dir T1 counted.
    assert meta_path.parent.parent.parent == promoted.shelf, meta_path
    assert meta_path.parts[-3] == promoted.slug, meta_path
    assert meta_path.parent == promoted.build, meta_path
    siblings = sorted(path.name for path in meta_path.parent.glob("*.py"))
    assert siblings, (
        f"server.py drops a metadata.json with no *.py beside it; {meta_path.parent} holds "
        f"{_entries(meta_path.parent)}"
    )
    assert (meta_path.parent / siblings[0]).read_bytes() == (
        promoted.slot.worker / GAME_PY
    ).read_bytes(), "the play-visible .py is not the packaged build's bytes"


def test_t5_the_promoted_metadata_is_the_play_server_shape(promoted):
    """T5: "carries the required keys with a NON-preview title"."""
    meta = _load_json(_metadata_path(promoted.dir))
    assert PLAY_METADATA_KEYS <= set(meta), sorted(meta)
    assert meta["tags"] == list(s6.PLAY_TAGS) == ["generated"], meta["tags"]
    assert meta["default_fps"] == s6.PLAY_DEFAULT_FPS
    assert meta["baseline_actions"] == promoted.slot.s4_metadata["baseline_actions"], (
        "§Work 1: baseline_actions come from the packaged S4 metadata"
    )
    assert len(meta["baseline_actions"]) == LEVEL_COUNT

    title = str(meta["title"])
    assert s6.PREVIEW_TITLE_SUFFIX.strip() not in title, f"a PREVIEW title was promoted: {title!r}"
    assert "pending" not in title.lower(), f"a PREVIEW title was promoted: {title!r}"
    squashed = re.sub(r"[^a-z0-9]", "", title.lower())
    assert squashed == re.sub(r"[^a-z0-9]", "", promoted.slug.lower()), (
        f"the clean title {title!r} is not the slug {promoted.slug!r} title-cased"
    )

    # Ambiguity F: the existing mirror writes `<slug>-<hash8>`; a one-entry
    # shelf could reasonably use the bare slug. Either is accepted.
    accepted = (promoted.slug, f"{promoted.slug}-{promoted.slot.hash8}")
    assert meta["game_id"] in accepted, (
        f"game_id {meta['game_id']!r} is neither the slug nor the play-mirror shape "
        f"`<slug>-<hash8>`; §Work 1 says 'at the play-server shape'. Accepted: {list(accepted)}"
    )


# --------------------------------------------------------------------------- #
# T6 — byte-identity of out/, with promotion never invoked
# --------------------------------------------------------------------------- #


def test_t6_an_unpromoted_packaging_run_is_byte_identical_to_pre_contract(tmp_path):
    """T6: promotion never invoked -> byte-identical out/ artifacts.

    Ambiguity G: the two path-free S6 artifacts are hard-pinned from a PRE-MERGE
    measurement of this same slot. Everything else is pinned structurally,
    because the operator manifest and report legitimately embed the machine's
    own absolute paths (P-3 Evidence).
    """
    slot = _stage_slot(tmp_path / "out" / "corpus", PACKAGED_SLUGS[0])

    assert slot.hash8 == PRE_CONTRACT_HASH8, (
        f"fixtures/s6_seeded's game_hash moved ({slot.hash8})" + RE_MEASURE
    )
    assert slot.s4_metadata["baseline_actions"] == PRE_CONTRACT_BASELINE_ACTIONS
    assert _sha(slot.out_dir / TSV_REL) == PRE_CONTRACT_TSV_SHA256, (
        f"{TSV_REL.as_posix()} bytes moved" + RE_MEASURE
    )
    mirror = slot.play_root / slot.slug / slot.hash8
    assert _sha(mirror / METADATA_JSON) == PRE_CONTRACT_PLAY_METADATA_SHA256, (
        "the play mirror's metadata.json bytes moved" + RE_MEASURE
    )

    # The out/ tree gains nothing: the frozen four files and no more.
    duck = s6.duck_intake_rel(slot.slug).as_posix()
    assert _files(slot.out_dir) == sorted(
        [MANIFEST_REL.as_posix(), TSV_REL.as_posix(), duck, REPORT_NAME]
    ), _files(slot.out_dir)
    assert _files(slot.play_root) == sorted(
        [f"{slot.slug}/{slot.hash8}/{slot.slug}.py", f"{slot.slug}/{slot.hash8}/{METADATA_JSON}"]
    )

    # The out/ OPERATOR manifest stays AS-IS: b10's key set, absolute paths,
    # duck_intake deliberately relative, and no promotion residue.
    assert set(slot.manifest) == OUT_MANIFEST_KEYS, sorted(set(slot.manifest) ^ OUT_MANIFEST_KEYS)
    paths = slot.manifest["paths"]
    for key in OUT_ABSOLUTE_PATH_KEYS:
        assert Path(paths[key]).is_absolute(), f"out/ manifest paths.{key} is no longer absolute"
    assert not Path(paths["duck_intake"]).is_absolute(), paths["duck_intake"]
    assert paths["duck_intake"] == duck
    assert "paths_note" not in slot.manifest and "paths_note" not in paths, (
        "the PROMOTED copy's paths_note leaked into the out/ operator manifest"
    )


def test_t6_packaging_creates_no_shelf_anywhere(tmp_path):
    """T6's premise: an S6 run does not promote. Nothing named `games` appears
    under the run's own tmp tree, and the repo shelf is untouched (the autouse
    guard proves the second half for every test in this file)."""
    shelf_existed = REPO_SHELF.exists()
    slot = _stage_slot(tmp_path / "out" / "corpus", PACKAGED_SLUGS[1])
    strays = [
        str(path.relative_to(tmp_path))
        for path in tmp_path.rglob(SHELF_DIRNAME)
        if path.is_dir()
    ]
    assert not strays, f"an S6 packaging run created a shelf on its own: {strays}"
    assert REPO_SHELF.exists() is shelf_existed
    assert slot.manifest["verdict"] == s6.VERDICT_PACKAGED
