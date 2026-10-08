"""Blind pins for FROZEN CONTRACT P-2 — canon vendoring (`./canon`).

Run: .venv/bin/python -m pytest gen/tests/test_v2_canon.py -v

Written from `docs/v2/contracts/P-2-canon-vendoring.md` ALONE (blind test
lane).  The implementation was not read: no diff, no `canon/PROVENANCE.md`,
no `gen/tools/sync_canon.py` body.  What this file WAS allowed to read, and
did, is the shipped STAGE code — `gen/*.py` — because the contract's item 1
says the file set must be DERIVED programmatically, "do not guess".  T1 does
that derivation here, independently of the implementer's: it parses the stage
modules and collects every literal relative path that is joined onto a canon
root (`_docs(cfg)` / `Path(cfg["duckwm_docs"])`).  A canon read added to
`gen/` without a vendored copy therefore turns T1 red on its own, which is the
whole value of the pin; a pin that merely echoed a hand-written list could not
do that.

`canon/PROVENANCE.md`'s LAYOUT is likewise not read but INFERRED from the
contract's own words ("source absolute path, duckWM git commit ..., copy date,
and per-file sha256 (a table)"), so T4's parser is deliberately
format-tolerant: it accepts any markdown table whose rows carry a 64-hex
digest and a cell naming a vendored file, in either column order.  It is
strict about the substance only.

duckWM is READ-ONLY here.  Nothing below writes into it; the only thing this
file does with it is read bytes for the byte-equality half of T1 and let T5's
clone tree reach it through a SYMLINK.  Every mutation happens in `tmp_path`.

EXPECTED FAILURES BEFORE THE IMPLEMENTER LANDS

`canon/`, `canon/PROVENANCE.md`, `gen/tools/sync_canon.py` and the template's
`./canon` default do not exist in a pre-merge tree.  T1–T5 are then red with
"contract P-2 creates it" messages.  That is the contract working as written:
none of these pins is skipped or softened to make a pre-merge tree green.  The
ONLY skips here are the honest environmental ones the contract itself calls
for — "skip cleanly when [duckWM is] absent".
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import gen.config as gen_config

REPO_ROOT = Path(__file__).resolve().parents[2]
GEN_DIR = REPO_ROOT / "gen"
CANON_DIR = REPO_ROOT / "canon"
PROVENANCE = CANON_DIR / "PROVENANCE.md"
TEMPLATE = REPO_ROOT / "config" / "template.yaml"
SYNC_CANON = GEN_DIR / "tools" / "sync_canon.py"
CONFIG_DIR = REPO_ROOT / "config"

# Contract item 3's frozen default, verbatim.
VENDORED_DEFAULT = "./canon"
# Contract item 2's provenance file name.
PROVENANCE_NAME = "PROVENANCE.md"

# `cfg["duckwm_docs"]` — the key every canon read is rooted at (contract's
# "grep for `_docs(`, `duckwm_docs`").
DOCS_KEY = "duckwm_docs"

# The paths contract item 1 NAMES.  Used only as an under-collection guard on
# the derivation below: if the AST walk stopped finding these, T1 would go
# quietly vacuous, and a vacuous pin is worse than no pin.  Basenames, because
# the contract writes `affordance-language.md` / `playbook.md` / `bestiary/*.md`
# without their directories — the directories come from the code.
CONTRACT_NAMED_BASENAMES = (
    "spec-v0.3.md",
    "game-term-matrix.csv",
    "objectives.csv",
    "playbook.md",
    "term-occurrence-final.csv",
    "terms-x-frontier.csv",
    "affordance-language.md",
)
CONTRACT_NAMED_DIR_BASENAME = "bestiary"

_SHA256_RE = re.compile(r"\b([0-9a-fA-F]{64})\b")
_GIT_SHA_RE = re.compile(r"\b([0-9a-fA-F]{40})\b")
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


# --- T1's derivation: every canon path the stage code can ask for ------------


def _module_constants(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    """Module-level `NAME = "lit"` / `NAME = ("a", "b")` string constants."""
    consts: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                consts[target.id] = (value.value,)
            elif isinstance(value, ast.Tuple | ast.List) and value.elts and all(
                isinstance(e, ast.Constant) and isinstance(e.value, str) for e in value.elts
            ):
                consts[target.id] = tuple(e.value for e in value.elts)  # type: ignore[misc]
    return consts


def _is_canon_root_call(node: ast.AST) -> bool:
    """`_docs(cfg)` or `Path(cfg["duckwm_docs"])` — the two canon roots in gen/."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "_docs":
        return True
    return isinstance(func, ast.Name) and func.id == "Path" and DOCS_KEY in ast.unparse(node)


def _canon_aliases(tree: ast.Module) -> set[str]:
    """Names bound to a canon root, transitively (`docs = _docs(cfg)`).

    Never un-bound: `gen/config.py` rebinds `docs = (REPO_ROOT / docs).resolve()`
    and the name is still the canon root afterwards.
    """
    aliases: set[str] = set()
    for _ in range(4):  # cheap fixpoint; the real chains are one or two deep
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            sub = list(ast.walk(node.value))
            if any(_is_canon_root_call(s) for s in sub) or any(
                isinstance(s, ast.Name) and s.id in aliases for s in sub
            ):
                aliases.add(target.id)
    return aliases


def _resolve(node: ast.AST, names: dict[str, set[str]]) -> set[str]:
    """The literal string(s) a path segment can be, or empty when unknowable."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Name):
        return set(names.get(node.id, ()))
    if isinstance(node, ast.Tuple | ast.List):
        out: set[str] = set()
        for elt in node.elts:
            got = _resolve(elt, names)
            if not got:
                return set()
            out |= got
        return out
    return set()


def _loop_bindings(tree: ast.Module, consts: dict[str, tuple[str, ...]]) -> dict[str, set[str]]:
    """`for rel in (A, B)` / `[... for rel in CANON_FILES]` -> rel's literals."""
    names: dict[str, set[str]] = {k: set(v) for k, v in consts.items()}
    bound: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.For | ast.AsyncFor | ast.comprehension):
            continue
        target, iterable = node.target, node.iter
        if not isinstance(target, ast.Name):
            continue
        values = _resolve(iterable, names)
        if values:
            bound.setdefault(target.id, set()).update(values)
    return bound


def _div_chain(node: ast.BinOp) -> tuple[ast.AST, list[ast.AST]]:
    """Flatten `a / b / c` into (a, [b, c])."""
    segments: list[ast.AST] = []
    current: ast.AST = node
    while isinstance(current, ast.BinOp) and isinstance(current.op, ast.Div):
        segments.append(current.right)
        current = current.left
    segments.reverse()
    return current, segments


def derive_canon_reads() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Contract item 1's derivation: (files, dirs) -> the code sites asking.

    Scans the STAGE modules (`gen/*.py`).  `gen/tests/` is not pipeline code
    and `gen/tools/` is the maintainer tool the contract explicitly keeps out
    of the orchestrator — neither is a reader the vendored tree must satisfy.

    A chain whose LAST segment is not a literal (`_docs(cfg) / BESTIARY_DIR /
    f"{slug}.md"`) yields a DIRECTORY requirement on the literal prefix: the
    code can ask for any member, so the whole directory has to ship.
    """
    files: dict[str, set[str]] = {}
    dirs: dict[str, set[str]] = {}
    for path in sorted(GEN_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        consts = _module_constants(tree)
        names: dict[str, set[str]] = {k: set(v) for k, v in consts.items()}
        names.update(_loop_bindings(tree, consts))
        aliases = _canon_aliases(tree)

        divs = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)]
        nested = {id(n.left) for n in divs if isinstance(n.left, ast.BinOp)}
        for node in divs:
            if id(node) in nested:  # only the outermost node of each chain
                continue
            root, segments = _div_chain(node)
            rooted = _is_canon_root_call(root) or (
                isinstance(root, ast.Name) and root.id in aliases
            )
            if not rooted:
                continue
            site = f"{path.name}:{node.lineno}"
            prefixes = [""]
            for segment in segments:
                values = _resolve(segment, names)
                if not values:  # unknowable tail -> the prefix is a directory
                    for prefix in prefixes:
                        if prefix:
                            dirs.setdefault(prefix, set()).add(site)
                    prefixes = []
                    break
                prefixes = [
                    f"{prefix}/{value}" if prefix else value
                    for prefix in prefixes
                    for value in sorted(values)
                ]
            for prefix in prefixes:
                if prefix:
                    files.setdefault(prefix, set()).add(site)
    return files, dirs


DERIVED_FILES, DERIVED_DIRS = derive_canon_reads()


# --- shared helpers ----------------------------------------------------------


def _historical_duckwm_value() -> str | None:
    """The `../duckWM/...` spelling the untouched batch configs still carry."""
    for path in sorted(CONFIG_DIR.glob("b*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        value = raw.get(DOCS_KEY) if isinstance(raw, dict) else None
        if isinstance(value, str) and value.startswith("../duckWM"):
            return value
    return None


def _duckwm_docs() -> Path | None:
    """The real duckWM canon root, or None when it is not beside this repo."""
    value = _historical_duckwm_value() or "../duckWM/local-docs/arc-agi-3-generator"
    root = (REPO_ROOT / value).resolve()
    return root if root.is_dir() else None


DUCKWM_DOCS = _duckwm_docs()
DUCKWM_REPO = REPO_ROOT.parent / "duckWM"


def _require_canon() -> None:
    if not CANON_DIR.is_dir():
        pytest.fail(
            f"vendored canon missing: {CANON_DIR} — contract P-2 item 2 creates it "
            f"(tracked, top level, byte-identical copies at the reader paths)"
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- LICENSED EDIT (contract OS-2 FRONT A, the canon special case) -----------
# The snapshot is no longer the duckWM bytes verbatim: the sync tool applies ONE
# documented post-copy neutralization (home-directory paths -> portable, the
# personal name -> "operator"), so the byte-equality pins below compare the
# vendored bytes against `neutralize_canon(source)` — and, so that this is not
# "equal to whatever the tool says", `_assert_confined` also proves the scrub
# touched NOTHING but lines that carried a path or a name.


def _neutralized(rel: str, source: bytes) -> bytes:
    from gen.tools.sync_canon import neutralize_canon

    return neutralize_canon(rel, source)


def _assert_confined(rel: str, vendored: bytes, source: bytes) -> None:
    """Same line count; every line that differs carried a path or a name."""
    from gen.tools import public_hygiene

    ours = vendored.decode("utf-8").splitlines()
    theirs = source.decode("utf-8").splitlines()
    assert len(ours) == len(theirs), (
        f"{rel}: the neutralization changed the line count ({len(theirs)} -> {len(ours)})"
    )
    for number, (mine, upstream) in enumerate(zip(ours, theirs, strict=True), start=1):
        if mine == upstream:
            continue
        assert public_hygiene.HOME_DIR_RE.search(upstream) or public_hygiene.has_person_name(
            upstream
        ), f"{rel}:{number}: rewritten although it carried no path and no name: {upstream!r}"


def _vendored_files(root: Path) -> set[str]:
    """Every vendored file under `root`, PROVENANCE.md and dotfiles aside."""
    out: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == PROVENANCE_NAME or any(part.startswith(".") for part in path.parts):
            continue
        out.add(rel)
    return out


def _parse_provenance(text: str, root: Path) -> tuple[dict[str, str], list[str]]:
    """(rel path -> sha256) from any markdown table, plus the unmatched rows.

    Deliberately layout-blind: a row is any line carrying a 64-hex digest; the
    path is whichever other cell names a file that exists under `root`.  Cells
    may be written bare, backticked, or prefixed with the directory name.
    """
    rows: dict[str, str] = {}
    unmatched: list[str] = []
    for line in text.splitlines():
        match = _SHA256_RE.search(line)
        if match is None:
            continue
        digest = match.group(1).lower()
        cells = [cell.strip().strip("`").strip() for cell in line.split("|")]
        rel: str | None = None
        for cell in cells:
            if not cell or _SHA256_RE.fullmatch(cell):
                continue
            for candidate in (cell, cell.removeprefix(f"{root.name}/")):
                probe = root / candidate
                if probe.is_file():
                    rel = probe.relative_to(root).as_posix()
                    break
            if rel is not None:
                break
        if rel is None:
            unmatched.append(line.strip())
        else:
            rows[rel] = digest
    return rows, unmatched


def _build_clone(dest: Path, *, with_tools: bool) -> Path:
    """A standalone checkout of this repo: gen/ + config/ + canon/, no tests.

    `gen/tests/` (11 MB of fixtures) is left out — it is not what the pipeline
    imports.  The clone's PARENT is a fresh tmp dir, so `../duckWM` does not
    exist unless a test plants it.
    """
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "gen").mkdir(exist_ok=True)
    for module in sorted(GEN_DIR.glob("*.py")):
        shutil.copy2(module, dest / "gen" / module.name)
    if with_tools and (GEN_DIR / "tools").is_dir():
        shutil.copytree(
            GEN_DIR / "tools",
            dest / "gen" / "tools",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    shutil.copytree(CONFIG_DIR, dest / "config", dirs_exist_ok=True)
    if CANON_DIR.is_dir():
        shutil.copytree(CANON_DIR, dest / "canon", dirs_exist_ok=True)
    if (REPO_ROOT / "pyproject.toml").is_file():
        shutil.copy2(REPO_ROOT / "pyproject.toml", dest / "pyproject.toml")
    return dest


def _write_clone_config(clone: Path, name: str = "_clone.yaml") -> Path:
    """`config/template.yaml`, re-pointed at `./canon`, with no duckWM sibling.

    `duckwm_games` is dropped: the officials corpus is a SEPARATE read-only
    dependency this contract does not vendor, and a clone has no duckWM at all.
    """
    if not TEMPLATE.is_file():
        pytest.fail(f"config/template.yaml missing: {TEMPLATE}")
    cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    assert isinstance(cfg, dict), "template.yaml did not parse to a mapping"
    cfg[DOCS_KEY] = VENDORED_DEFAULT
    cfg.pop("duckwm_games", None)
    path = clone / "config" / name
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


def _run_in_clone(clone: Path, script: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run `script` against the CLONE's `gen`, from an unrelated CWD.

    The editable install of this repo puts an `_EditableFinder` on
    `sys.meta_path` that maps `gen` to the REAL checkout and outranks
    `sys.path`.  Without scrubbing it the "clone" would silently import the
    original tree and T2 would pass for the wrong reason.
    """
    bootstrap = (
        "import sys\n"
        "sys.meta_path = [f for f in sys.meta_path\n"
        "    if 'editable' not in (getattr(f, '__module__', '') or '').lower()\n"
        "    and 'editable' not in (getattr(f, '__name__', '') or '').lower()]\n"
        f"sys.path.insert(0, {str(clone)!r})\n"
    )
    path = clone.parent / "_probe.py"
    path.write_text(bootstrap + script, encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(clone)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(path)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


# --- T1: the derived-file-set pin -------------------------------------------


def test_t1_derivation_is_not_vacuous() -> None:
    """The AST walk finds the canon reads contract item 1 names.

    Guards the pin itself: a derivation that silently stopped collecting would
    make every other T1 assertion pass over an empty set.
    """
    assert DERIVED_FILES, (
        "derived NO canon reads from gen/*.py — the walk is broken, not the vendoring"
    )
    basenames = {Path(rel).name for rel in DERIVED_FILES}
    missing = [name for name in CONTRACT_NAMED_BASENAMES if name not in basenames]
    assert not missing, (
        f"derivation under-collected: contract item 1 names {missing} but the walk "
        f"over gen/*.py did not find them (found {sorted(DERIVED_FILES)})"
    )
    dir_basenames = {Path(rel).name for rel in DERIVED_DIRS}
    assert CONTRACT_NAMED_DIR_BASENAME in dir_basenames, (
        f"derivation found no {CONTRACT_NAMED_DIR_BASENAME!r} directory read "
        f"(dirs: {sorted(DERIVED_DIRS)}) — contract item 1 names bestiary/*.md"
    )


@pytest.mark.parametrize("rel", sorted(DERIVED_FILES))
def test_t1_every_reader_path_is_vendored(rel: str) -> None:
    """Contract item 1's pin: the vendored tree covers every path gen/ can ask for."""
    _require_canon()
    sites = ", ".join(sorted(DERIVED_FILES[rel]))
    vendored = CANON_DIR / rel
    assert vendored.is_file(), (
        f"canon read {rel!r} (from {sites}) has NO vendored copy at {vendored} — "
        f"contract P-2 item 1: a new canon read without a vendored copy fails this pin"
    )
    assert vendored.stat().st_size > 0, f"vendored {rel!r} is empty: {vendored}"


@pytest.mark.parametrize("rel", sorted(DERIVED_DIRS))
def test_t1_every_reader_directory_is_vendored(rel: str) -> None:
    """A per-slug read (`bestiary/<slug>.md`) needs the WHOLE directory vendored."""
    _require_canon()
    sites = ", ".join(sorted(DERIVED_DIRS[rel]))
    vendored = CANON_DIR / rel
    assert vendored.is_dir(), (
        f"canon directory read {rel!r} (from {sites}) is not vendored at {vendored} — "
        f"the code can ask for any member, so the directory ships whole"
    )
    members = [p for p in vendored.iterdir() if p.is_file()]
    assert members, f"vendored directory {rel!r} is empty: {vendored}"


@pytest.mark.parametrize("rel", sorted(DERIVED_FILES))
def test_t1_vendored_bytes_match_duckwm(rel: str) -> None:
    """Byte-equality canon/<p> vs ../duckWM/.../<p>, skipped cleanly when absent."""
    if DUCKWM_DOCS is None:
        pytest.skip(f"duckWM is not beside this repo ({REPO_ROOT.parent / 'duckWM'})")
    _require_canon()
    source = DUCKWM_DOCS / rel
    if not source.is_file():
        pytest.fail(
            f"the code reads {rel!r} but duckWM has no such file ({source}) — "
            f"the derivation or the canon moved"
        )
    vendored = CANON_DIR / rel
    assert vendored.is_file(), f"not vendored: {vendored}"
    assert vendored.read_bytes() == _neutralized(rel, source.read_bytes()), (
        f"vendored {rel!r} is NOT the neutralized duckWM bytes "
        f"({_sha256(vendored)} vs {_sha256(source)} upstream) — re-run the sync tool"
    )
    _assert_confined(rel, vendored.read_bytes(), source.read_bytes())


@pytest.mark.parametrize("rel", sorted(DERIVED_DIRS))
def test_t1_vendored_directory_matches_duckwm(rel: str) -> None:
    """Every member duckWM offers is vendored, byte-identical, and vice versa."""
    if DUCKWM_DOCS is None:
        pytest.skip(f"duckWM is not beside this repo ({REPO_ROOT.parent / 'duckWM'})")
    _require_canon()
    source = DUCKWM_DOCS / rel
    if not source.is_dir():
        pytest.fail(f"the code reads {rel}/ but duckWM has no such directory ({source})")
    vendored = CANON_DIR / rel
    assert vendored.is_dir(), f"not vendored: {vendored}"
    source_names = {p.name for p in source.iterdir() if p.is_file()}
    vendored_names = {p.name for p in vendored.iterdir() if p.is_file()}
    assert vendored_names == source_names, (
        f"{rel}/ membership differs from duckWM — missing {sorted(source_names - vendored_names)}, "
        f"extra {sorted(vendored_names - source_names)}"
    )
    differing = [
        name
        for name in sorted(source_names)
        if (vendored / name).read_bytes()
        != _neutralized(f"{rel}/{name}", (source / name).read_bytes())
    ]
    assert not differing, f"{rel}/ members are not the neutralized duckWM bytes: {differing}"
    for name in sorted(source_names):
        _assert_confined(
            f"{rel}/{name}", (vendored / name).read_bytes(), (source / name).read_bytes()
        )


# --- T2: clone simulation (no ../duckWM sibling) -----------------------------


_CLONE_SCRIPT = """
import json
from pathlib import Path

ROOT = Path({root!r})
result = {{"ok": [], "fail": []}}


def step(name, fn):
    try:
        fn()
        result["ok"].append(name)
    except Exception as exc:
        result["fail"].append("%s: %s: %s" % (name, type(exc).__name__, exc))


import gen

result["gen_file"] = gen.__file__
from gen import canon_docs, config, s0_ideas, s1_spec

result["repo_root"] = str(config.REPO_ROOT)
result["duckwm_sibling_exists"] = (ROOT.parent / "duckWM").exists()

cfg = config.load_config({cfg_rel!r})
result["docs"] = cfg["duckwm_docs"]

step("config.matrix_row_count", lambda: config.matrix_row_count(cfg))
step("s0_ideas.load_vocab", lambda: s0_ideas.load_vocab(cfg))
step("s0_ideas.load_objective_distribution", lambda: s0_ideas.load_objective_distribution(cfg))
step("s0_ideas.load_secondary_distribution", lambda: s0_ideas.load_secondary_distribution(cfg))
step("s0_ideas.load_frontier_shares", lambda: s0_ideas.load_frontier_shares(cfg))
step("s0_ideas.load_doctrine", lambda: s0_ideas.load_doctrine(cfg))
step("canon_docs.load_term_definitions", lambda: canon_docs.load_term_definitions(cfg))
step("canon_docs.load_playbook_entries", lambda: canon_docs.load_playbook_entries(cfg))
step("canon_docs.load_skeleton", lambda: canon_docs.load_skeleton(cfg))
step("canon_docs.load_forbidden_quotes", lambda: canon_docs.load_forbidden_quotes(cfg))
step("canon_docs.load_affordance_sections", lambda: canon_docs.load_affordance_sections(cfg, [1]))
step("canon_docs.load_required_gates", lambda: canon_docs.load_required_gates(cfg))
step("canon_docs.load_conventions", lambda: canon_docs.load_conventions(cfg))
step("s1_spec.load_spec_doctrine", lambda: s1_spec.load_spec_doctrine(cfg))
step("s1_spec.load_crosswalk", lambda: s1_spec.load_crosswalk(cfg))
step("s1_spec.load_spec_schema", lambda: s1_spec.load_spec_schema(cfg))


def bestiary():
    from gen.canon_docs import BESTIARY_DIR

    slugs = sorted(p.stem for p in (ROOT / "canon" / BESTIARY_DIR).glob("*.md"))
    if not slugs:
        raise AssertionError("no vendored bestiary entries under canon/" + BESTIARY_DIR)
    vocab = sorted(s0_ideas.load_vocab(cfg))
    for slug in slugs:
        for term in vocab:
            try:
                excerpt = canon_docs.bestiary_excerpt(cfg, slug, term)
            except ValueError:
                continue
            if excerpt.text.strip():
                return
    raise AssertionError("no vendored bestiary file yielded a section-3 excerpt")


step("canon_docs.bestiary_excerpt", bestiary)


def payload_module():
    from gen import s2_implement

    assert callable(s2_implement.build_payload)


step("import gen.s2_implement (build_payload)", payload_module)
print(json.dumps(result))
"""


@pytest.fixture(scope="module")
def clone_run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """T2: load + read the whole canon from a tree with NO duckWM sibling."""
    _require_canon()
    base = tmp_path_factory.mktemp("p2clone")
    clone = _build_clone(base / "repo", with_tools=False)
    elsewhere = base / "elsewhere"
    elsewhere.mkdir()
    assert not (clone.parent / "duckWM").exists(), "the clone tree must have no duckWM sibling"
    cfg_path = _write_clone_config(clone)
    script = _CLONE_SCRIPT.format(
        root=str(clone), cfg_rel=str(cfg_path.relative_to(clone).as_posix())
    )
    proc = _run_in_clone(clone, script, cwd=elsewhere)
    if proc.returncode != 0:
        pytest.fail(
            "clone simulation crashed before reporting.\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):  # pragma: no cover - diagnostic path
        pytest.fail(f"clone simulation printed no JSON.\nstdout:\n{proc.stdout}\n{proc.stderr}")


def test_t2_clone_really_is_the_clone(clone_run: dict) -> None:
    """The subprocess imported the COPY, not this checkout, and saw no duckWM."""
    assert clone_run["gen_file"].startswith(clone_run["repo_root"]), (
        f"the simulation imported {clone_run['gen_file']} — not the clone at "
        f"{clone_run['repo_root']} (the editable-install finder was not scrubbed)"
    )
    assert not Path(clone_run["repo_root"]).is_relative_to(REPO_ROOT), (
        f"the simulation ran inside this checkout ({clone_run['repo_root']})"
    )
    assert clone_run["duckwm_sibling_exists"] is False, (
        "the clone tree has a ../duckWM sibling — the simulation proves nothing"
    )


def test_t2_load_config_passes_canon_files_without_duckwm(clone_run: dict) -> None:
    """`./canon` satisfies `gen.config.CANON_FILES` in a duckWM-less tree."""
    expected = str(Path(clone_run["repo_root"]) / "canon")
    assert clone_run["docs"] == expected, (
        f"load_config resolved duckwm_docs to {clone_run['docs']!r}, expected {expected!r} — "
        f"`./canon` must resolve against the REPO ROOT (contract item 5)"
    )


def test_t2_every_canon_reader_succeeds_on_the_vendored_snapshot(clone_run: dict) -> None:
    """load_vocab + the S0 weight builders + build_payload's canon loads, all green."""
    assert not clone_run["fail"], "canon readers failed in the clone:\n  " + "\n  ".join(
        clone_run["fail"]
    )
    assert len(clone_run["ok"]) >= 16, f"too few readers exercised: {clone_run['ok']}"


# --- T3: template default + explicit ../duckWM still loads -------------------


def test_t3_template_default_is_the_vendored_canon() -> None:
    """Contract item 3: the template's default flips to `./canon`, verbatim."""
    if not TEMPLATE.is_file():
        pytest.fail(f"config/template.yaml missing: {TEMPLATE}")
    cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    assert isinstance(cfg, dict), "template.yaml did not parse to a mapping"
    assert cfg.get(DOCS_KEY) == VENDORED_DEFAULT, (
        f"template default duckwm_docs is {cfg.get(DOCS_KEY)!r}, contract item 3 freezes "
        f"{VENDORED_DEFAULT!r}"
    )


def test_t3_template_comment_explains_the_vendoring_and_the_way_back() -> None:
    """The default carries its explanation: why vendored, how to point back at duckWM."""
    if not TEMPLATE.is_file():
        pytest.fail(f"config/template.yaml missing: {TEMPLATE}")
    comments = [
        line for line in TEMPLATE.read_text(encoding="utf-8").splitlines() if "#" in line
    ]
    blob = "\n".join(comments).lower()
    assert "vendor" in blob, "template comments never explain the vendoring (contract item 3)"
    assert "duckwm" in blob, "template comments never say how to point back at a duckWM checkout"


def test_t3_template_loads_and_resolves_against_the_repo_root(tmp_path: Path) -> None:
    """The shipped template loads here, from a tmp CWD, and lands on REPO_ROOT/canon."""
    _require_canon()
    if not TEMPLATE.is_file():
        pytest.fail(f"config/template.yaml missing: {TEMPLATE}")
    dest = tmp_path / "template.yaml"  # a COPY: no reader may write the real one
    shutil.copy2(TEMPLATE, dest)
    cwd = os.getcwd()
    os.chdir(tmp_path)  # contract item 5: resolution is repo-root, never CWD
    try:
        cfg = gen_config.load_config(dest)
    except FileNotFoundError as exc:
        pytest.fail(f"the shipped template no longer loads: {exc}")
    finally:
        os.chdir(cwd)
    assert Path(cfg[DOCS_KEY]) == CANON_DIR, (
        f"template resolved duckwm_docs to {cfg[DOCS_KEY]} — expected {CANON_DIR}"
    )
    assert gen_config.REPO_ROOT == REPO_ROOT, (
        f"gen.config.REPO_ROOT is {gen_config.REPO_ROOT}, expected {REPO_ROOT}"
    )


def test_t3_historical_batch_configs_still_point_at_duckwm() -> None:
    """Contract item 3: HISTORICAL batch configs (b001..b005r2) untouched."""
    batch_configs = sorted(CONFIG_DIR.glob("b*.yaml"))
    assert batch_configs, f"no historical batch configs found under {CONFIG_DIR}"
    moved = []
    for path in batch_configs:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        value = raw.get(DOCS_KEY) if isinstance(raw, dict) else None
        if not (isinstance(value, str) and value.startswith("../duckWM")):
            moved.append(f"{path.name}: {value!r}")
    assert not moved, f"historical batch configs were re-pointed (contract says untouched): {moved}"


def test_t3_explicit_duckwm_config_still_loads(tmp_path: Path) -> None:
    """An explicit `../duckWM` path keeps byte-identical behaviour (house rule)."""
    if DUCKWM_DOCS is None:
        pytest.skip(f"duckWM is not beside this repo ({REPO_ROOT.parent / 'duckWM'})")
    explicit = _historical_duckwm_value()
    assert explicit, "no historical config carries the explicit ../duckWM spelling"
    if not TEMPLATE.is_file():
        pytest.fail(f"config/template.yaml missing: {TEMPLATE}")
    cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    cfg[DOCS_KEY] = explicit
    dest = tmp_path / "explicit.yaml"
    dest.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    loaded = gen_config.load_config(dest)
    assert Path(loaded[DOCS_KEY]) == DUCKWM_DOCS, (
        f"explicit {explicit!r} resolved to {loaded[DOCS_KEY]}, expected {DUCKWM_DOCS} — "
        f"the explicit form must behave exactly as it does today"
    )


def test_t3_both_forms_deliver_the_same_canon_bytes(tmp_path: Path) -> None:
    """`./canon` and `../duckWM/...` hand the readers identical bytes — modulo the
    documented post-copy neutralization (LICENSED EDIT, contract OS-2)."""
    if DUCKWM_DOCS is None:
        pytest.skip(f"duckWM is not beside this repo ({REPO_ROOT.parent / 'duckWM'})")
    _require_canon()
    differing = [
        rel
        for rel in sorted(DERIVED_FILES)
        if (CANON_DIR / rel).is_file()
        and (DUCKWM_DOCS / rel).is_file()
        and (CANON_DIR / rel).read_bytes()
        != _neutralized(rel, (DUCKWM_DOCS / rel).read_bytes())
    ]
    assert not differing, f"the two duckwm_docs forms would read DIFFERENT bytes for: {differing}"


# --- T4: PROVENANCE.md self-integrity ---------------------------------------


def test_t4_provenance_exists_and_records_its_source() -> None:
    """Contract item 2: source absolute path, duckWM commit, copy date."""
    _require_canon()
    if not PROVENANCE.is_file():
        pytest.fail(f"canon/PROVENANCE.md missing: {PROVENANCE} — contract P-2 item 2 creates it")
    text = PROVENANCE.read_text(encoding="utf-8")
    source_lines = [
        line
        for line in text.splitlines()
        if "duckWM" in line and "arc-agi-3-generator" in line and "/" in line
    ]
    assert source_lines, (
        "PROVENANCE.md records no source absolute path "
        "(a line naming .../duckWM/local-docs/arc-agi-3-generator)"
    )
    # LICENSED EDIT (contract OS-2 FRONT A, canon item 4): the stamp used to
    # record the maintainer's ABSOLUTE source path; OS-2 makes it PORTABLE —
    # relative to the repo root, the spelling the historical configs use for
    # `duckwm_docs`. The pin now holds the new form: a `../duckWM/...` source,
    # and no absolute or home-directory path on any source line.
    assert any(": ../duckWM/" in line for line in source_lines), (
        f"PROVENANCE.md's source path is not the portable ../duckWM/... form: {source_lines[:3]}"
    )
    # (the home-directory root is spelled in two halves so this shipped file
    # passes the public mirror's own path gate)
    absolute = [line for line in source_lines
                if line.lstrip("- ").startswith("/") or ": /" in line or "/User" + "s/" in line]
    assert not absolute, f"PROVENANCE.md still records an absolute source path: {absolute[:3]}"
    commits = [sha for sha in _GIT_SHA_RE.findall(text) if not _SHA256_RE.fullmatch(sha)]
    assert commits, "PROVENANCE.md records no duckWM git commit (40-hex `git rev-parse HEAD`)"
    assert _DATE_RE.search(text), "PROVENANCE.md records no copy date (YYYY-MM-DD)"


def test_t4_provenance_covers_every_vendored_file() -> None:
    """The sha256 table is per-FILE: one row for each vendored byte-copy."""
    _require_canon()
    if not PROVENANCE.is_file():
        pytest.fail(f"canon/PROVENANCE.md missing: {PROVENANCE} — contract P-2 item 2 creates it")
    rows, unmatched = _parse_provenance(PROVENANCE.read_text(encoding="utf-8"), CANON_DIR)
    assert rows, (
        "PROVENANCE.md has no parseable per-file sha256 table "
        f"(rows carrying a 64-hex digest and a path under {CANON_DIR}); "
        f"unmatched digest lines: {unmatched[:3]}"
    )
    vendored = _vendored_files(CANON_DIR)
    missing = sorted(vendored - set(rows))
    assert not missing, f"vendored files with no sha256 row in PROVENANCE.md: {missing}"
    assert not unmatched, (
        f"PROVENANCE.md rows carry a sha256 but name no existing vendored file: {unmatched[:5]}"
    )


def test_t4_provenance_sha256_rows_match_the_vendored_bytes() -> None:
    """Self-integrity: every recorded digest is the digest of the file on disk."""
    _require_canon()
    if not PROVENANCE.is_file():
        pytest.fail(f"canon/PROVENANCE.md missing: {PROVENANCE} — contract P-2 item 2 creates it")
    rows, _ = _parse_provenance(PROVENANCE.read_text(encoding="utf-8"), CANON_DIR)
    assert rows, "PROVENANCE.md has no parseable per-file sha256 table"
    wrong = {
        rel: (recorded, _sha256(CANON_DIR / rel))
        for rel, recorded in sorted(rows.items())
        if _sha256(CANON_DIR / rel) != recorded
    }
    assert not wrong, f"PROVENANCE.md digests do not match the vendored bytes: {wrong}"


# --- T5: sync_canon refuses on divergence unless --force --------------------


# The contract fixes only `--force`.  How the tool is pointed at a duckWM
# checkout is not frozen, so T5 DISCOVERS it against a pristine clone (where a
# correct invocation has nothing to refuse and exits 0) instead of guessing.
_SOURCE_FLAGS = ("--source", "--src", "--from", "--duckwm", "--duckwm-docs", "--docs", "--canon")


def _sync_argv(clone: Path, extra: list[str]) -> list[list[str]]:
    """`-m` first (relative imports keep working), then the plain script path."""
    forms = [[sys.executable, "-m", "gen.tools.sync_canon", *extra]]
    forms.append([sys.executable, str(clone / "gen" / "tools" / "sync_canon.py"), *extra])
    return forms


def _run_sync(clone: Path, argv: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(clone)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        argv, cwd=str(clone), env=env, capture_output=True, text=True, timeout=300, check=False
    )


def _clone_with_duckwm(base: Path, name: str) -> tuple[Path, Path]:
    """A clone whose `../duckWM` is a SYMLINK to the real, read-only checkout."""
    root = base / name
    root.mkdir(parents=True)
    clone = _build_clone(root / "repo", with_tools=True)
    (root / "duckWM").symlink_to(DUCKWM_REPO, target_is_directory=True)
    source = (clone / (_historical_duckwm_value() or "")).resolve()
    return clone, source


@pytest.fixture(scope="module")
def sync_invocation(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    """The argv that drives sync_canon against a duckWM checkout, discovered."""
    if DUCKWM_DOCS is None:
        pytest.skip(f"duckWM is not beside this repo ({DUCKWM_REPO})")
    if not SYNC_CANON.is_file():
        pytest.fail(f"gen/tools/sync_canon.py missing: {SYNC_CANON} — contract P-2 item 4")
    _require_canon()
    base = tmp_path_factory.mktemp("p2sync_probe")
    clone, source = _clone_with_duckwm(base, "probe")

    help_text = ""
    for form in _sync_argv(clone, ["--help"]):
        proc = _run_sync(clone, form)
        if proc.returncode == 0 and ("usage" in proc.stdout.lower() or proc.stdout.strip()):
            help_text = proc.stdout
            break
    assert "--force" in help_text, (
        f"sync_canon --help does not offer --force (contract item 4). Help was:\n{help_text}"
    )

    tried: list[str] = []
    candidates: list[list[str]] = [[]]
    candidates += [[flag, str(source)] for flag in _SOURCE_FLAGS]
    candidates.append([str(source)])
    for extra in candidates:
        for form in _sync_argv(clone, extra):
            proc = _run_sync(clone, form)
            if proc.returncode == 0 and "unrecognized" not in proc.stderr:
                return form
            tried.append(f"{' '.join(form[1:])} -> rc={proc.returncode} {proc.stderr.strip()[:160]}")
    pytest.fail(
        "could not drive gen/tools/sync_canon.py against a pristine clone — no invocation "
        "exited 0 with nothing to sync. Tried:\n  " + "\n  ".join(tried) + f"\nHelp:\n{help_text}"
    )


def test_t5_sync_canon_exists() -> None:
    """Contract item 4: the maintainer CLI ships."""
    assert SYNC_CANON.is_file(), (
        f"gen/tools/sync_canon.py missing: {SYNC_CANON} — contract P-2 item 4 creates it"
    )


def test_t5_refuses_a_planted_divergence_without_force(
    sync_invocation: list[str], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A locally edited vendored file is NOT silently clobbered."""
    base = tmp_path_factory.mktemp("p2sync_refuse")
    clone, _ = _clone_with_duckwm(base, "refuse")
    target = min(DERIVED_FILES)
    planted_path = clone / "canon" / target
    planted = planted_path.read_bytes() + b"\n<!-- planted local canon edit -->\n"
    planted_path.write_bytes(planted)
    provenance_before = (clone / "canon" / PROVENANCE_NAME).read_bytes()

    argv = [sync_invocation[0], *sync_invocation[1:]]
    proc = _run_sync(clone, argv)

    assert proc.returncode != 0, (
        f"sync_canon exited 0 on a planted divergence in {target!r} — contract item 4 says it "
        f"REFUSES without --force.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert planted_path.read_bytes() == planted, (
        f"sync_canon clobbered the locally edited {target!r} without --force"
    )
    assert (clone / "canon" / PROVENANCE_NAME).read_bytes() == provenance_before, (
        "sync_canon re-stamped PROVENANCE.md while refusing"
    )
    said = (proc.stdout + proc.stderr).lower()
    assert "--force" in said or "force" in said, (
        f"the refusal never mentions --force, so a maintainer cannot act on it:\n"
        f"{proc.stdout}\n{proc.stderr}"
    )


def test_t5_force_recopies_and_restamps(
    sync_invocation: list[str], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """`--force` re-copies from the source and leaves PROVENANCE self-consistent."""
    base = tmp_path_factory.mktemp("p2sync_force")
    clone, _ = _clone_with_duckwm(base, "force")
    target = min(DERIVED_FILES)
    planted_path = clone / "canon" / target
    planted_path.write_bytes(planted_path.read_bytes() + b"\n<!-- planted local canon edit -->\n")

    proc = _run_sync(clone, [*sync_invocation, "--force"])
    assert proc.returncode == 0, (
        f"sync_canon --force failed.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    # LICENSED EDIT (contract OS-2): --force re-copies the NEUTRALIZED source.
    source_bytes = _neutralized(target, (DUCKWM_DOCS / target).read_bytes())
    assert planted_path.read_bytes() == source_bytes, (
        f"--force did not re-copy {target!r} from the duckWM source"
    )
    provenance = clone / "canon" / PROVENANCE_NAME
    assert provenance.is_file(), "--force removed canon/PROVENANCE.md"
    rows, unmatched = _parse_provenance(provenance.read_text(encoding="utf-8"), clone / "canon")
    assert rows, f"PROVENANCE.md is unparseable after --force (unmatched: {unmatched[:3]})"
    wrong = {
        rel: (recorded, _sha256(clone / "canon" / rel))
        for rel, recorded in sorted(rows.items())
        if _sha256(clone / "canon" / rel) != recorded
    }
    assert not wrong, f"--force left PROVENANCE.md out of step with the bytes it copied: {wrong}"
    assert target in rows, f"--force left {target!r} without a sha256 row"


def test_t5_prints_a_diff_summary(
    sync_invocation: list[str], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Contract item 4: the tool prints a diff summary, naming what moved."""
    base = tmp_path_factory.mktemp("p2sync_diff")
    clone, _ = _clone_with_duckwm(base, "diff")
    target = min(DERIVED_FILES)
    planted_path = clone / "canon" / target
    planted_path.write_bytes(planted_path.read_bytes() + b"\n<!-- planted local canon edit -->\n")
    proc = _run_sync(clone, [*sync_invocation])
    said = proc.stdout + proc.stderr
    assert Path(target).name in said, (
        f"the diff summary never names the diverged file {target!r}:\n{said}"
    )
