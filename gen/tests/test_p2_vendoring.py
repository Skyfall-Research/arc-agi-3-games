"""Implementer-lane pins for contract P-2 — the vendored canon (`canon/`).

Run: .venv/bin/python -m pytest gen/tests/test_p2_vendoring.py -v

P-2 ships `canon/`: a tracked, byte-identical, provenance-stamped snapshot of
exactly the canon files the pipeline reads, so the generator runs on a clone
with no duckWM sibling (operator ruling of 2026-09-29, docs/v2/DECISIONS.md).
A blind lane writes its own pins for the same contract in
`gen/tests/test_v2_canon.py`; this file is the IMPLEMENTER's, and the overlap
is deliberate — the implementer has to be able to run the contract's own
verification gates (the derivation pin and the clone simulation) without the
blind file existing.

The five things pinned here, and why each one is a pin rather than a comment:

1. THE DERIVATION. The vendoring set is computed from the readers
   (`gen.tools.sync_canon.derive_canon_paths`), never hand-listed. Two pins
   guard it: the derived set must cover every canon constant the four reader
   modules actually declare (an independent cross-check that imports them),
   and every derived path must exist under `canon/`. A new canon read with no
   vendored copy fails here instead of failing on a stranger's laptop.
2. BYTE-EQUALITY against the duckWM source — skipped cleanly when the sibling
   checkout is absent, because that absence is the entire point of the
   contract.
3. THE PROVENANCE STAMP is self-checking: every sha256 row matches the bytes
   in the tree, and nothing in the tree is missing from the table.
4. THE HOUSE RULE — an explicit `../duckWM` config still loads, and the S2
   payload it builds is BYTE-IDENTICAL to the one the vendored snapshot
   builds. Only the DEFAULT moved.
5. THE CLONE SIMULATION, in a subprocess, in a tmp tree with no `../duckWM`
   sibling and with `PYTHONPATH` pointing at the copied repo (the editable
   install's finder is appended to `sys.meta_path`, so the real `PathFinder`
   wins and the clone's own `gen/` is what gets imported — asserted inside the
   child). Config load, the S0 weight builders, a real seeded S0 draw and a
   real `build_payload` all run there, with a stub prose runner: NO API SPEND.

HYGIENE: nothing here writes into the repo. The sync-refusal pins copy into
`tmp_path` and use the repo's own `canon/` only as a read-only SOURCE; the
clone simulation copies the repo into `tmp_path`. duckWM is only ever read.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from gen import canon_docs, s0_ideas, s1_spec
from gen import config as gen_config
from gen.tools import sync_canon

REPO_ROOT = Path(gen_config.REPO_ROOT)
CANON_ROOT = REPO_ROOT / "canon"
TEMPLATE_PATH = REPO_ROOT / "config" / "template.yaml"
DUCKWM_DOCS = sync_canon.DEFAULT_SOURCE

# Contract §3: the template's default. Written as the contract writes it.
TEMPLATE_DEFAULT = "./canon"

# A shipped spec dir, used ONLY as a read-only input to `build_payload` (it is
# the cheapest real spec there is). Under `out/`, which is gitignored — so a
# genuine fresh clone would not have it, and the clone simulation copies it in
# the way a user's own first spec would arrive.
SPEC_DIR = REPO_ROOT / "out" / "corpus" / "b003r2-simplicity" / "conduit-watch"

requires_duckwm = pytest.mark.skipif(
    not DUCKWM_DOCS.is_dir(),
    reason=f"no duckWM sibling checkout at {DUCKWM_DOCS} — the snapshot is what makes that OK",
)


# --- helpers ------------------------------------------------------------------


def _template_tree() -> dict:
    return yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))


def _cfg_at(tmp_path: Path, docs: str) -> dict:
    """The template, loaded from a tmp copy with `duckwm_docs` set to `docs`.

    `load_config` resolves `duckwm_docs` against the REPO root, never against
    the config's own directory, so a tmp copy loads exactly like the real file.
    """
    tree = _template_tree()
    tree["duckwm_docs"] = docs
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(tree, sort_keys=False), encoding="utf-8")
    return gen_config.load_config(path)


# --- pin 1: the derivation ----------------------------------------------------


def test_derived_set_covers_every_declared_reader_constant() -> None:
    """Cross-check: the AST sweep finds every canon constant the modules declare.

    The sweep in `sync_canon` reads source text; this reads the IMPORTED
    modules' attributes. Two independent routes to the same set is what makes
    "derived, not guessed" checkable — if the sweep's regex or its module list
    ever stops seeing one of these, this test names the constant.
    """
    derived = set(sync_canon.derive_canon_files())
    declared = {
        "config.CANON_FILES": set(gen_config.CANON_FILES),
        "s0_ideas": {
            s0_ideas.VOCAB_CSV,
            s0_ideas.MATRIX_CSV,
            s0_ideas.OBJECTIVES_CSV,
            s0_ideas.FRONTIER_CSV,
            s0_ideas.DOCTRINE_MD,
        },
        "s1_spec": {s1_spec.DOCTRINE_MD, s1_spec.CROSSWALK_MD, s1_spec.SPEC_MD},
        "canon_docs": {
            canon_docs.PLAYBOOK_MD,
            canon_docs.SKELETON_MD,
            canon_docs.AFFORDANCE_MD,
            canon_docs.SPEC_MD,
            canon_docs.VOCAB_DRAFT_MD,
            canon_docs.VOCAB_FINAL_MD,
        },
    }
    missing = {
        source: sorted(paths - derived) for source, paths in declared.items() if paths - derived
    }
    assert not missing, (
        f"canon paths declared by the readers and NOT derived by "
        f"gen.tools.sync_canon.derive_canon_files: {missing}"
    )
    assert canon_docs.BESTIARY_DIR in sync_canon.derive_canon_dirs(), (
        f"the bestiary directory {canon_docs.BESTIARY_DIR!r} is not derived — its entries are "
        f"reached by a runtime slug, so the whole directory has to be vendored"
    )


def test_every_derived_path_is_vendored() -> None:
    """`canon/` covers every path the code can ask for. THE contract pin."""
    assert CANON_ROOT.is_dir(), f"the vendored canon is missing: {CANON_ROOT}"
    paths = sync_canon.derive_canon_paths(CANON_ROOT)
    missing = [rel for rel in paths if not (CANON_ROOT / rel).is_file()]
    assert not missing, (
        f"{len(missing)} canon path(s) a reader can ask for are not vendored under {CANON_ROOT}: "
        f"{missing} — re-run `python -m gen.tools.sync_canon`"
    )
    # A non-trivial floor, so a derivation that collapsed to nothing (or to the
    # four CANON_FILES alone) cannot pass by being empty.
    assert len(paths) > len(gen_config.CANON_FILES), f"derived only {len(paths)} canon paths"
    assert any(rel.startswith(canon_docs.BESTIARY_DIR) for rel in paths)


def test_canon_files_check_passes_against_the_vendored_tree() -> None:
    """`gen/config.py`'s own load-time gate is satisfied by the snapshot."""
    missing = [rel for rel in gen_config.CANON_FILES if not (CANON_ROOT / rel).is_file()]
    assert not missing, f"vendored canon is missing CANON_FILES {missing}"


@requires_duckwm
def test_vendored_bytes_are_identical_to_duckwm() -> None:
    """Byte-equality `canon/<p>` vs `../duckWM/.../<p>`, for every derived path.

    LICENSED EDIT (contract OS-2 FRONT A): "byte-equal" now means equal to the
    source AFTER the documented post-copy neutralization (`neutralize_canon`),
    and the generated license notice — which has no duckWM source — is held to
    its renderer instead.
    """
    differ = []
    for rel in sync_canon.derive_canon_paths(DUCKWM_DOCS):
        vendored, source = CANON_ROOT / rel, DUCKWM_DOCS / rel
        if rel in sync_canon.GENERATED_FILES:
            expected = sync_canon.GENERATED_FILES[rel]().encode("utf-8")
        else:
            expected = sync_canon.neutralize_canon(rel, source.read_bytes())
        if not vendored.is_file():
            differ.append(f"{rel}: not vendored")
        elif vendored.read_bytes() != expected:
            differ.append(f"{rel}: bytes differ from the (neutralized) source")
    assert not differ, f"the snapshot has drifted from duckWM: {differ}"


@requires_duckwm
def test_the_derivation_is_the_same_set_from_either_root() -> None:
    """Expanding the canon directories against either tree yields one set."""
    assert sync_canon.derive_canon_paths(CANON_ROOT) == sync_canon.derive_canon_paths(DUCKWM_DOCS)


def test_a_new_canon_read_with_no_vendored_copy_has_teeth(tmp_path: Path) -> None:
    """The pin's NEGATIVE half, contract §1: a new canon read must turn it red.

    A pin that only ever passes proves nothing, so this plants one — a reader
    module copied into `tmp_path` with one extra canon literal — and asserts
    the derivation picks it up and the vendored tree does not cover it. The
    repo's own `gen/` is never touched.
    """
    planted = "design/objects/not-vendored-yet.md"
    fake_gen = tmp_path / "gen"
    fake_gen.mkdir()
    for name in sync_canon.CANON_READER_MODULES:
        shutil.copyfile(REPO_ROOT / "gen" / name, fake_gen / name)
    victim = fake_gen / "canon_docs.py"
    victim.write_text(
        victim.read_text(encoding="utf-8") + f'\nNEW_CANON_MD = "{planted}"\n', encoding="utf-8"
    )

    derived = sync_canon.derive_canon_files(fake_gen)
    assert planted in derived, "the derivation did not see a newly declared canon path"
    assert not (CANON_ROOT / planted).is_file(), "the planted path must not exist in canon/"
    missing = [rel for rel in derived if not (CANON_ROOT / rel).is_file()]
    assert missing == [planted], (
        f"the vendoring pin would not have reddened on the planted read; missing={missing}"
    )


def test_no_canon_looking_literal_escapes_the_derivation() -> None:
    """Every `.md`/`.csv` literal in the reader modules is vendored or declared.

    The escape hatch is `sync_canon.NON_CANON_LITERALS`, one commented entry
    per false positive. The point is the direction of the default: a new canon
    read is caught unless someone says otherwise, in writing.
    """
    derived = set(sync_canon.derive_canon_files())
    stray = []
    for name in sync_canon.CANON_READER_MODULES:
        _constants, literals = sync_canon._module_constants(REPO_ROOT / "gen" / name)
        for literal in literals:
            if not sync_canon._CANON_RELPATH_RE.match(literal):
                continue
            if literal in derived or literal in sync_canon.NON_CANON_LITERALS:
                continue
            stray.append(f"{name}: {literal!r}")
    assert not stray, (
        f"canon-looking path literals in the reader modules that are neither vendored nor "
        f"declared non-canon: {stray} — vendor it, or add it to NON_CANON_LITERALS with a reason"
    )


# --- pin 2: the provenance stamp ---------------------------------------------


def test_provenance_exists_and_parses() -> None:
    stamp = CANON_ROOT / sync_canon.PROVENANCE_NAME
    assert stamp.is_file(), f"contract P-2 §2 requires {stamp}"
    record = sync_canon.parse_provenance(stamp.read_text(encoding="utf-8"))
    # LICENSED EDIT (contract OS-2 FRONT A): the source is stamped PORTABLE now —
    # relative to the repo root, never a maintainer's absolute path — and it
    # still names the duckWM canon this snapshot came from.
    assert not Path(record["source"]).is_absolute(), f"source is an absolute path: {record}"
    assert (REPO_ROOT / record["source"]).resolve() == DUCKWM_DOCS.resolve(), (
        f"the portable source does not resolve to the duckWM canon: {record['source']!r}"
    )
    assert record["copied"], "PROVENANCE.md records no copy date"
    commit = record["commit"]
    assert len(commit) == 40 and all(c in "0123456789abcdef" for c in commit), (
        f"PROVENANCE.md's duckWM commit is not a sha1: {commit!r}"
    )


def test_provenance_sha256_rows_match_the_vendored_bytes() -> None:
    """Self-integrity: the stamp describes the tree it sits in, exactly."""
    problems = sync_canon.verify_provenance(CANON_ROOT)
    assert not problems, "canon/PROVENANCE.md does not match the tree:\n  " + "\n  ".join(problems)


def test_provenance_table_covers_the_derived_set() -> None:
    record = sync_canon.parse_provenance(
        (CANON_ROOT / sync_canon.PROVENANCE_NAME).read_text(encoding="utf-8")
    )
    assert set(record["files"]) == set(sync_canon.derive_canon_paths(CANON_ROOT))


# --- pin 3: the template default + path resolution ---------------------------


def test_template_default_is_the_vendored_canon() -> None:
    """Contract §3: the DEFAULT flips to `./canon`."""
    assert _template_tree()["duckwm_docs"] == TEMPLATE_DEFAULT


def test_template_comment_says_how_to_point_back_at_duckwm() -> None:
    """Contract §3: the comment explains the vendoring AND the way back."""
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    for marker in ("canon/PROVENANCE.md", "../duckWM/local-docs/arc-agi-3-generator"):
        assert marker in text, f"config/template.yaml never mentions {marker!r}"


def test_historical_batch_configs_are_untouched() -> None:
    """Contract §3: b001..b005r2 keep pointing at the duckWM checkout."""
    for path in sorted((REPO_ROOT / "config").glob("b*.yaml")):
        tree = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert tree["duckwm_docs"] == "../duckWM/local-docs/arc-agi-3-generator", (
            f"{path.name} was re-pointed; historical configs are untouched by P-2"
        )


def test_dot_canon_resolves_against_the_repo_root_from_any_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract §5: `./canon` resolves like `../duckWM` does — off the REPO root."""
    monkeypatch.chdir(tmp_path)
    cfg = _cfg_at(tmp_path, TEMPLATE_DEFAULT)
    assert Path(cfg["duckwm_docs"]) == CANON_ROOT.resolve()


def test_template_loads_with_no_duckwm_games_key() -> None:
    """The officials corpus is optional and is NOT vendored: the key is absent.

    `load_config` raises `NotADirectoryError` for a `duckwm_games` that does
    not resolve, so an uncommented path would fail this template at load on
    every machine without the duckWM sibling — which is the machine the whole
    contract is about.
    """
    assert "duckwm_games" not in _template_tree()


# --- pin 4: the house rule — explicit configs behave identically -------------


@requires_duckwm
def test_an_explicit_duckwm_config_still_loads(tmp_path: Path) -> None:
    cfg = _cfg_at(tmp_path, "../duckWM/local-docs/arc-agi-3-generator")
    assert Path(cfg["duckwm_docs"]) == DUCKWM_DOCS.resolve()


@requires_duckwm
def test_payload_is_byte_identical_from_either_canon_root(tmp_path: Path) -> None:
    """THE house-rule pin: same spec, two canon roots, one payload.

    Everything the S2 prompt quotes is quoted by content and attributed by FILE
    NAME, so a payload built off the snapshot and a payload built off duckWM
    have to be the same string. If they ever are not, the snapshot is not a
    snapshot.
    """
    if not SPEC_DIR.is_dir():
        pytest.skip(f"no shipped spec dir to build a payload from: {SPEC_DIR}")
    from gen.s2_implement import build_payload

    vendored, _ = build_payload(SPEC_DIR, _cfg_at(tmp_path / "a", TEMPLATE_DEFAULT))
    upstream, _ = build_payload(
        SPEC_DIR, _cfg_at(tmp_path / "b", "../duckWM/local-docs/arc-agi-3-generator")
    )
    assert vendored == upstream, (
        "the S2 payload differs between the vendored canon and the duckWM checkout"
    )


# --- pin 5: sync_canon's refusal ---------------------------------------------


def test_sync_canon_bootstraps_an_empty_dest(tmp_path: Path, capsys) -> None:
    """A dest with nothing in it is all `new`: copied and stamped, no --force."""
    dest = tmp_path / "vendored"
    assert sync_canon.main(["--source", str(CANON_ROOT), "--dest", str(dest)]) == 0
    capsys.readouterr()
    assert not sync_canon.verify_provenance(dest)
    for rel in sync_canon.derive_canon_paths(CANON_ROOT):
        assert (dest / rel).read_bytes() == (CANON_ROOT / rel).read_bytes()


def test_sync_canon_refuses_a_planted_divergence_and_force_restamps(
    tmp_path: Path, capsys
) -> None:
    """Contract §4: refuse on divergence, `--force` overwrites and re-stamps."""
    dest = tmp_path / "vendored"
    argv = ["--source", str(CANON_ROOT), "--dest", str(dest)]
    assert sync_canon.main(argv) == 0
    capsys.readouterr()

    victim = dest / "spec-v0.3.md"
    planted = victim.read_text(encoding="utf-8") + "\nLOCAL EDIT\n"
    victim.write_text(planted, encoding="utf-8")
    stamp_before = (dest / sync_canon.PROVENANCE_NAME).read_text(encoding="utf-8")

    assert sync_canon.main(argv) == 1, "sync_canon did not refuse a divergent vendored file"
    out = capsys.readouterr()
    assert "REFUSED" in out.err and "spec-v0.3.md" in out.out
    assert victim.read_text(encoding="utf-8") == planted, "the refusal still wrote the file"
    assert (dest / sync_canon.PROVENANCE_NAME).read_text(encoding="utf-8") == stamp_before

    assert sync_canon.main([*argv, "--force"]) == 0
    capsys.readouterr()
    assert victim.read_bytes() == (CANON_ROOT / "spec-v0.3.md").read_bytes()
    assert not sync_canon.verify_provenance(dest)


def test_sync_canon_refuses_an_orphan_without_force(tmp_path: Path, capsys) -> None:
    """A vendored file no reader can ask for is a deletion, so it needs --force."""
    dest = tmp_path / "vendored"
    argv = ["--source", str(CANON_ROOT), "--dest", str(dest)]
    assert sync_canon.main(argv) == 0
    orphan = dest / "mechanics" / "not-derived.csv"
    orphan.write_text("a,b\n1,2\n", encoding="utf-8")
    capsys.readouterr()
    assert sync_canon.main(argv) == 1
    assert orphan.is_file(), "the refusal deleted the orphan anyway"
    capsys.readouterr()
    assert sync_canon.main([*argv, "--force"]) == 0
    assert not orphan.exists()


def test_sync_canon_reports_a_bad_source_without_writing(tmp_path: Path, capsys) -> None:
    dest = tmp_path / "vendored"
    code = sync_canon.main(["--source", str(tmp_path / "nope"), "--dest", str(dest)])
    assert code == 2
    assert not dest.exists()


def test_sync_canon_is_wired_into_nothing() -> None:
    """Contract §4: "No orchestrator wiring — a maintainer tool".

    IMPORTS, not mentions: `gen/config.py`'s docstring names the tool on
    purpose (it is where a reader of the knob asks "how do I re-stamp this?"),
    and a docstring is not wiring. An `import` is.
    """
    importers = []
    for path in sorted((REPO_ROOT / "gen").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            plain = isinstance(node, ast.Import) and any(
                alias.name.startswith("gen.tools") for alias in node.names
            )
            relative = isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                ("gen.tools", "tools")
            )
            if plain or relative:
                importers.append(path.name)
    assert not importers, (
        f"pipeline modules importing the maintainer tool: {sorted(set(importers))}"
    )


# --- pin 6: the clone simulation ---------------------------------------------

_CLONE_CHECK = '''\
"""Run INSIDE the simulated clone. Prints one JSON line; raises on any failure."""
import json
import pathlib
import sys

CLONE = pathlib.Path(__file__).resolve().parent

import gen.config as gen_config

# The clone's own gen/ must be what got imported — not the editable install
# pointing back at the real repo (its finder is appended to sys.meta_path, so
# PYTHONPATH wins, and this is where that stops being an assumption).
assert gen_config.REPO_ROOT == CLONE, f"imported {gen_config.REPO_ROOT}, expected {CLONE}"
assert not (CLONE.parent / "duckWM").exists(), "the simulated clone has a duckWM sibling"

from gen import canon_docs, s0_ideas
from gen.s2_implement import build_payload

cfg = gen_config.load_config("config/clone.yaml")
docs = pathlib.Path(cfg["duckwm_docs"])
assert docs == CLONE / "canon", docs

vocab = s0_ideas.load_vocab(cfg)
s0_ideas.check_config(cfg, vocab)
weights = {
    "objective": s0_ideas.objective_weights(cfg),
    "failure_family": s0_ideas.failure_family_weights(cfg),
    "secondary": s0_ideas.secondary_weights(cfg),
    "frontier": s0_ideas.load_frontier_shares(cfg),
}
assert all(weights.values()), "an S0 weight builder returned nothing"
assert s0_ideas.load_doctrine(cfg).strip(), "S0 doctrine is empty"
assert s0_ideas.load_objective_distribution(cfg), "objective distribution is empty"

definitions = canon_docs.load_term_definitions(cfg)
playbook = canon_docs.load_playbook_entries(cfg)
skeleton = canon_docs.load_skeleton(cfg)
forbidden = canon_docs.load_forbidden_quotes(cfg)
sections = canon_docs.load_affordance_sections(cfg, canon_docs.AFFORDANCE_SECTION_KEYWORDS)
gates = canon_docs.load_required_gates(cfg)
conventions = canon_docs.load_conventions(cfg)
slug = skeleton[sorted(skeleton)[0]].officials[0][0]
excerpt = canon_docs.bestiary_excerpt(cfg, slug, sorted(skeleton)[0])

PROSE = (
    "A compact test arena where a lone selector sweeps across a five by five "
    "board of tiles. Some tiles hide a target glyph, and clicking a tile "
    "reveals it, while blocked cells force the sweep into detours that cost "
    "extra moves. The player must cover every target pad before the sweep "
    "counter runs out, learning board by board which routes waste turns. "
    "Later boards add a second glyph colour and a locked row that opens only "
    "when the first colour is fully covered, so plans must interleave the "
    "two colours without stranding the selector behind its own reveals."
)


def prose_runner(prompt, *args, **kwargs):
    # No driver, no network, no spend: the S0 draw under test is the CANON
    # read and the weighted sampling, not the prose call.
    return "Clone Simulation\\n" + PROSE


ideas = s0_ideas.sample_batch(
    cfg,
    batch_id="p2-clone",
    seed=7,
    prose_runner=prose_runner,
    out_dir=CLONE / "out" / "ideas" / "p2-clone",
)
assert ideas, "the S0 draw produced no ideas"

payload = None
spec_dir = CLONE / "spec"
if spec_dir.is_dir():
    payload, _report = build_payload(spec_dir, cfg)
    assert len(payload) > 10_000, f"payload is only {len(payload)} chars"

print(json.dumps({
    "repo_root": str(gen_config.REPO_ROOT),
    "docs": str(docs),
    "vocab": len(vocab),
    "definitions": len(definitions),
    "playbook": len(playbook),
    "skeleton": len(skeleton),
    "forbidden": len(forbidden),
    "affordance_sections": sorted(sections),
    "required_gates_chars": len(gates),
    "conventions_chars": len(conventions),
    "bestiary": [slug, excerpt.term, len(excerpt.text)],
    "ideas": len(ideas),
    "payload_chars": len(payload) if payload is not None else None,
}))
'''


def _build_clone(tmp_path: Path) -> Path:
    """The repo's tracked essentials, copied into a tree with no duckWM sibling."""
    clone = tmp_path / "clone"
    clone.mkdir()
    shutil.copytree(
        REPO_ROOT / "gen",
        clone / "gen",
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    shutil.copytree(CANON_ROOT, clone / "canon")
    (clone / "config").mkdir()
    # The template as the default ships it — `duckwm_docs: ./canon`, no
    # `duckwm_games` — with only the placeholder batch id filled in.
    tree = _template_tree()
    tree["batch"]["id"] = "p2-clone"
    (clone / "config" / "clone.yaml").write_text(
        yaml.safe_dump(tree, sort_keys=False), encoding="utf-8"
    )
    shutil.copyfile(REPO_ROOT / "pyproject.toml", clone / "pyproject.toml")
    if SPEC_DIR.is_dir():
        shutil.copytree(SPEC_DIR, clone / "spec")
    (clone / "clone_check.py").write_text(_CLONE_CHECK, encoding="utf-8")
    return clone


def test_clone_simulation_without_a_duckwm_sibling(tmp_path: Path) -> None:
    """Contract T2 / the P-2 acceptance: the whole canon path works standalone.

    A subprocess, because the point is an import graph and a filesystem
    neighbourhood this process does not have. No network, no driver, no spend.
    """
    clone = _build_clone(tmp_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(clone)
    env.pop("PYTHONHOME", None)
    done = subprocess.run(
        [sys.executable, "clone_check.py"],
        cwd=clone,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,  # the assert below reports the child's own output
    )
    assert done.returncode == 0, (
        "the fresh-clone simulation failed:\n"
        + textwrap.indent(done.stdout[-4000:] + "\n" + done.stderr[-4000:], "    ")
    )
    result = json.loads(done.stdout.strip().splitlines()[-1])
    assert result["repo_root"] == str(clone)
    assert result["docs"] == str(clone / "canon")
    assert result["vocab"] == s0_ideas.VOCAB_SIZE
    assert result["definitions"] == s0_ideas.VOCAB_SIZE
    assert result["skeleton"] == s0_ideas.VOCAB_SIZE
    assert result["forbidden"] == len(canon_docs.FORBIDDEN_ANCHORS)
    assert result["affordance_sections"] == sorted(canon_docs.AFFORDANCE_SECTION_KEYWORDS)
    assert result["playbook"] > 0 and result["required_gates_chars"] > 0
    assert result["conventions_chars"] > 0 and result["bestiary"][2] > 0
    assert result["ideas"] >= 1
    if SPEC_DIR.is_dir():
        assert result["payload_chars"] and result["payload_chars"] > 10_000
