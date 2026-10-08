"""The officials corpus: discovery + class loading (B2).

The 25 signed officials live in the sister repo duckWM under
`games/<slug>/<variant>/`, each directory holding `<slug>.py` and
`metadata.json` (metadata `game_id` is "<slug>-<variant>"). The corpus is a
READ-ONLY dependency — nothing here writes into it.

Loading an official is deliberate, for three reasons verified against the
corpus: the files PRINT on import and on instantiation (so exec runs under
quieted streams), some are enormous (ka59 is 41k lines, so callers cache the
returned class and reuse cheap instances), and the module MUST be registered
in `sys.modules` BEFORE exec or dataclass field resolution inside the game
files fails.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path

from arcengine import ARCBaseGame

from gen.config import REPO_ROOT

# Signed corpus size. This is canon, not a sanity bound: a different count
# means the corpus moved under us and the calibration is not comparable.
OFFICIALS_COUNT = 25

# Written by the worker-contracts workstream; loaded at RUNTIME, never imported
# at module scope, so gen/ stays importable while that file is in flight.
CONTRACTS_PATH = REPO_ROOT / "worker-template/tests/_contracts.py"


@dataclass
class Official:
    """One signed official game: `<slug>/<variant>/<slug>.py` + its metadata."""

    slug: str
    variant: str
    game_id: str
    py_path: Path
    metadata: dict


def discover_officials(cfg: dict) -> list[Official]:
    """Enumerate the corpus from `cfg['duckwm_games']`, sorted by slug.

    Fail-loud on every deviation from the signed shape: a stray `.py`, a
    misnamed game file, missing/empty metadata `game_id`, a duplicate slug
    (the caches downstream are keyed by slug), or a total != OFFICIALS_COUNT.
    """
    if "duckwm_games" not in cfg:
        raise KeyError("config missing 'duckwm_games' — required for the B2 officials corpus")
    root = Path(cfg["duckwm_games"])
    if not root.is_dir():
        raise NotADirectoryError(f"duckwm_games is not a directory: {root}")

    officials: list[Official] = []
    for variant_dir in sorted(root.glob("*/*")):
        if not variant_dir.is_dir() or variant_dir.name == "__pycache__":
            continue
        slug = variant_dir.parent.name
        if slug == "__pycache__":
            continue

        py_files = sorted(p for p in variant_dir.glob("*.py") if p.is_file())
        if len(py_files) != 1:
            raise AssertionError(
                f"{variant_dir}: expected exactly one game .py, found "
                f"{[p.name for p in py_files]!r}"
            )
        py_path = py_files[0]
        if py_path.name != f"{slug}.py":
            raise AssertionError(
                f"{variant_dir}: game file is {py_path.name!r}, expected {slug}.py "
                "(file name must match the slug directory)"
            )

        meta_path = variant_dir / "metadata.json"
        if not meta_path.is_file():
            raise FileNotFoundError(f"{variant_dir}: missing metadata.json")
        with meta_path.open(encoding="utf-8") as fh:
            metadata = json.load(fh)
        if not isinstance(metadata, dict):
            raise TypeError(f"{meta_path}: metadata did not parse to a mapping")
        game_id = metadata.get("game_id")
        if not isinstance(game_id, str) or not game_id:
            raise AssertionError(f"{meta_path}: metadata 'game_id' missing or empty ({game_id!r})")

        officials.append(
            Official(
                slug=slug,
                variant=variant_dir.name,
                game_id=game_id,
                py_path=py_path,
                metadata=metadata,
            )
        )

    slugs = [o.slug for o in officials]
    duplicates = sorted({s for s in slugs if slugs.count(s) > 1})
    if duplicates:
        raise AssertionError(
            f"{root}: expected exactly one variant per slug, duplicated slugs {duplicates!r}"
        )
    if len(officials) != OFFICIALS_COUNT:
        raise AssertionError(
            f"expected {OFFICIALS_COUNT} officials under {root}, found {len(officials)}: "
            f"{sorted(o.game_id for o in officials)!r}"
        )
    return sorted(officials, key=lambda o: o.slug)


def load_official_class(py_path: Path) -> type:
    """Exec-load one official and return its single ARCBaseGame subclass.

    Expensive (ka59 takes seconds) — callers cache the result per slug.
    """
    if not py_path.is_file():
        raise FileNotFoundError(f"official game file not found: {py_path}")

    unique_name = f"official_{py_path.stem}"
    module = types.ModuleType(unique_name)
    module.__file__ = str(py_path)
    source = py_path.read_text(encoding="utf-8")
    code = compile(source, str(py_path), "exec")

    # Registration BEFORE exec: dataclasses in the game files resolve their
    # field types via sys.modules[__name__] and blow up if it is not there.
    sys.modules[unique_name] = module
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exec(code, module.__dict__)  # noqa: S102 - exec-load is the contract here
    except Exception:
        sys.modules.pop(unique_name, None)
        raise

    candidates: dict[int, type] = {}
    for obj in vars(module).values():
        if isinstance(obj, type) and issubclass(obj, ARCBaseGame) and obj is not ARCBaseGame:
            candidates.setdefault(id(obj), obj)
    found = list(candidates.values())
    if len(found) > 1:
        # Imported subclasses can ride along; prefer the ones defined here.
        owned = [c for c in found if c.__module__ == unique_name]
        if owned:
            found = owned
    if len(found) != 1:
        raise AssertionError(
            f"{py_path}: expected exactly ONE ARCBaseGame subclass, found "
            f"{sorted(c.__name__ for c in found)!r}"
        )
    return found[0]


def load_contracts() -> types.ModuleType:
    """Load the worker conformance contracts as a module (runtime, fail-loud)."""
    if not CONTRACTS_PATH.is_file():
        raise FileNotFoundError(
            f"worker contracts module not found: {CONTRACTS_PATH} — B2 conformance "
            "cannot run without it"
        )
    spec = importlib.util.spec_from_file_location("worker_contracts", CONTRACTS_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build an import spec for {CONTRACTS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["worker_contracts"] = module
    spec.loader.exec_module(module)
    return module
