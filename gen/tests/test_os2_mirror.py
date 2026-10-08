"""Implementer-lane pins for contract OS-2 — the public mirror.

Run: .venv/bin/python -m pytest gen/tests/test_os2_mirror.py -v

The contract's own pin list, from the implementer's side (a blind lane writes
its own file for the same contract):

1. EXPORT — the ships manifest is exactly ruling 5 (present / absent, path by
   path); a non-empty target and a target inside the source are refused; the
   source tree is untouched; a real export of THIS tree passes the gate.
2. VERIFY — every gate class trips on a planted violation, loudly, at
   `path:line`; the self-labelled fakes and the word "vanish" do not.
3. SCRUB — the runtime strings carry the neutral form; the canon's sha table
   matches the scrubbed files; the sync tool reproduces the scrubbed canon
   from an un-scrubbed upstream, byte for byte, and refuses what it cannot
   scrub; the third-party files and the generated license notice are what
   they claim to be.
4. PUBLIC CLONE — d8 skips without the smoke ledger, which stays ignored and
   untracked; the config fallback is OFF by default and re-points only the
   absent duckWM sibling; a suite run of the known leak sites leaves `out/`
   byte-identical.

A RULE THIS FILE KEEPS: it ships in the public mirror, and the mirror's gate
sweeps it. So every planted violation — a key-shaped string, a personal name,
a home-directory path — is BUILT AT RUNTIME (rot13, string halves), never
written out literally.
"""

from __future__ import annotations

import codecs
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from gen import config as gen_config
from gen.tools import export_public, public_hygiene, sync_canon

REPO_ROOT = Path(gen_config.REPO_ROOT)
CANON_ROOT = REPO_ROOT / "canon"
DUCKWM_DOCS = sync_canon.DEFAULT_SOURCE


def _given_name() -> str:
    """The operator's given name, built at runtime (see the module docstring)."""
    return codecs.decode("Navfu", "rot13")


def _family_name() -> str:
    return codecs.decode("Puunoen", "rot13")


def _home(user: str = "someone") -> str:
    return "/" + "Users" + "/" + user + "/"


def _git(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          check=False)


def _in_git_repo() -> bool:
    return _git("rev-parse", "--is-inside-work-tree").returncode == 0


requires_git = pytest.mark.skipif(not _in_git_repo(), reason="this tree is not a git checkout")


# =============================================================================
# 1. export — ruling 5, encoded once
# =============================================================================

SHIPPED = (
    "games/seamlock/game/game.py",
    "gen/cli.py",
    "gen/tests/test_os2_mirror.py",
    "gen/tools/export_public.py",
    "config/template.yaml",
    "canon/PROVENANCE.md",
    "canon/third-party/re-arc-3/LICENSE-MIT.md",
    "tools/play/server.py",
    "worker-template/game.py",
    "README.md",
    "LICENSE",
    "NOTICE",
    "CONTRIBUTING.md",
    "pyproject.toml",
    ".gitignore",
    "docs/RUNBOOK.md",
    "docs/GUIDE.md",
    "docs/OUTPUT-FORMAT.md",
    "out/.gitkeep",
    "play-logs-games/.gitkeep",
)

PRIVATE = (
    "docs/v2/TRACKER.md",
    "docs/v2/DECISIONS.md",
    "docs/v2/OPENSOURCE-AUDIT.md",
    "docs/v2/contracts/OS-2-public-mirror.md",
    "IMPLEMENTATION.md",
    "audit/comparative/data/effort.csv",
    ".claude/settings.json",
    "gen/.claude/notes.md",
    "out/smoke/smoke.jsonl",
    "out/corpus/b001-pilot/x/spec.yaml",
    "out/calibration/officials-latency.json",
    "play-logs-games/seamlock-1.json",
    "gen/__pycache__/cli.cpython-312.pyc",
    "notes-at-the-root.md",
    "docs/some-other-doc.md",
)


@pytest.mark.parametrize("rel", SHIPPED)
def test_the_manifest_ships_the_public_tree(rel: str) -> None:
    assert export_public.ships(rel), f"{rel} belongs in the public mirror (ruling 5)"


@pytest.mark.parametrize("rel", PRIVATE)
def test_the_manifest_keeps_the_private_tree_private(rel: str) -> None:
    assert not export_public.ships(rel), f"{rel} must never reach the public mirror"


def _fake_source(root: Path) -> Path:
    """A tiny git repo laid out like this one: shipped, private and ignored files."""
    src = root / "src"
    files = {
        "README.md": "# public\n",
        "LICENSE": "license\n",
        "NOTICE": "notice\n",
        "CONTRIBUTING.md": "contribute\n",
        "pyproject.toml": "[project]\nname='x'\n",
        ".gitignore": "out/*\n!out/.gitkeep\n/play-logs-games/*\n!/play-logs-games/.gitkeep\n",
        "gen/a.py": "A = 1\n",
        "games/g/game/game.py": "G = 1\n",
        "docs/GUIDE.md": "guide\n",
        "docs/v2/TRACKER.md": "private board\n",
        "IMPLEMENTATION.md": "private history\n",
        "audit/data.csv": "a,b\n",
        "out/.gitkeep": "",
        "play-logs-games/.gitkeep": "",
    }
    for rel, text in files.items():
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text(text, encoding="utf-8")
    (src / "out" / "run.log").write_text("ignored\n", encoding="utf-8")
    assert _git("init", "-q", cwd=src).returncode == 0
    _git("add", "-A", cwd=src)
    _git("-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "x", cwd=src)
    (src / "gen" / "new_untracked.py").write_text("B = 2\n", encoding="utf-8")
    return src


def _snapshot(root: Path) -> dict[str, tuple[int, int, bytes]]:
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            stat = path.stat()
            out[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns,
                                                      path.read_bytes())
    return out


def test_export_writes_exactly_the_shipped_set_and_never_touches_the_source(tmp_path) -> None:
    src = _fake_source(tmp_path)
    before = _snapshot(src)
    result = export_public.export(tmp_path / "mirror", source=src)
    assert _snapshot(src) == before, "the export wrote into its source tree"
    written = sorted(p.relative_to(result.target).as_posix()
                     for p in result.target.rglob("*") if p.is_file())
    assert written == sorted([
        ".gitignore", "CONTRIBUTING.md", "LICENSE", "NOTICE", "README.md", "docs/GUIDE.md",
        "games/g/game/game.py", "gen/a.py", "gen/new_untracked.py", "out/.gitkeep",
        "play-logs-games/.gitkeep", "pyproject.toml",
    ])
    assert result.untracked == ["gen/new_untracked.py"], "an uncommitted file must be NAMED"
    assert {"docs/v2/TRACKER.md", "IMPLEMENTATION.md", "audit/data.csv"} <= set(result.dropped)


def test_export_refuses_a_non_empty_target(tmp_path) -> None:
    src = _fake_source(tmp_path)
    target = tmp_path / "busy"
    target.mkdir()
    (target / "already-here.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_public.export(target, source=src)
    assert sorted(p.name for p in target.iterdir()) == ["already-here.txt"]
    assert export_public.main([str(target), "--source", str(src)]) == 2


def test_export_refuses_a_target_inside_the_source(tmp_path) -> None:
    src = _fake_source(tmp_path)
    with pytest.raises(ValueError):
        export_public.export(src / "mirror", source=src)
    assert not (src / "mirror").exists()


def test_export_refuses_a_source_missing_the_public_face(tmp_path) -> None:
    src = _fake_source(tmp_path)
    (src / "NOTICE").unlink()
    with pytest.raises(FileNotFoundError, match="NOTICE"):
        export_public.export(tmp_path / "mirror", source=src)


@requires_git
def test_a_real_export_of_this_tree_passes_the_gate(tmp_path) -> None:
    """THE acceptance, classes 1-5: this working tree, exported, verifies clean."""
    tracked = _git("ls-files", "-z").stdout.split("\0")
    watched = [rel for rel in tracked if rel and (REPO_ROOT / rel).is_file()]
    before = {rel: (REPO_ROOT / rel).stat().st_mtime_ns for rel in watched}
    status_before = _git("status", "--porcelain").stdout

    result = export_public.export(tmp_path / "arc-agi-games")
    hits = export_public.verify(result.target)
    assert not hits, "the assembled mirror fails the gate:\n" + "\n".join(
        hit.render() for hit in hits[:40])

    assert {rel: (REPO_ROOT / rel).stat().st_mtime_ns for rel in watched} == before
    assert _git("status", "--porcelain").stdout == status_before, "the export changed the source"


# =============================================================================
# 2. verify — every class trips on a planted violation
# =============================================================================


def _clean_mirror(root: Path) -> Path:
    mirror = root / "mirror"
    for rel in export_public.SHIPS.required + ("gen/a.py", "out/.gitkeep",
                                               "play-logs-games/.gitkeep"):
        (mirror / rel).parent.mkdir(parents=True, exist_ok=True)
        (mirror / rel).write_text("clean\n", encoding="utf-8")
    return mirror


def test_a_clean_mirror_is_green(tmp_path, capsys) -> None:
    mirror = _clean_mirror(tmp_path)
    assert export_public.verify(mirror) == []
    assert export_public.main(["--verify", str(mirror)]) == 0
    assert "class 6" in capsys.readouterr().out, "the suite command must be printed"


PLANTED = {
    # gate -> the line planted into gen/a.py (built at runtime)
    "secret": lambda: "KEY = '" + "sk-" + "proj-" + "Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7" + "'",
    "secret-github": lambda: "token " + "ghp" + "_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
    "secret-aws": lambda: "AKIA" + "ABCDEFGHIJKLMNOP",
    "name": lambda: f"# signed off by {_given_name()}",
    "name-possessive": lambda: f"# {_given_name()}'s ruling",
    "name-family": lambda: f"# {_family_name()}",
    "name-camel": lambda: f"handle = '{_given_name()}{_family_name()}2'",
    "path": lambda: f"cd {_home()}code",
    "path-cache": lambda: "~/" + ".cache/uv/x",
    "path-tmp": lambda: "/private" + "/tmp/x",
    "link": lambda: "https://claude.ai/" + "artifact/abc",
}


@pytest.mark.parametrize("label", sorted(PLANTED))
def test_each_gate_class_trips_on_a_planted_violation(label: str, tmp_path, capsys) -> None:
    mirror = _clean_mirror(tmp_path)
    (mirror / "gen" / "a.py").write_text("clean\n" + PLANTED[label]() + "\n", encoding="utf-8")
    hits = export_public.verify(mirror)
    gate = label.split("-")[0]
    assert [(hit.path, hit.line, hit.gate) for hit in hits] == [("gen/a.py", 2, gate)], hits
    assert export_public.main(["--verify", str(mirror)]) == 1
    assert f"gen/a.py:2: [{gate}]" in capsys.readouterr().out


@pytest.mark.parametrize("rel", (
    "IMPLEMENTATION.md", "docs/v2/TRACKER.md", "audit/x.csv", ".claude/settings.json",
    "gen/.claude/x.md", "out/smoke/smoke.jsonl", "out/corpus/x/spec.yaml",
    "play-logs-games/log.json", "docs/OPENSOURCE-AUDIT.md",
))
def test_the_layout_class_trips_on_a_private_file(rel: str, tmp_path) -> None:
    mirror = _clean_mirror(tmp_path)
    (mirror / rel).parent.mkdir(parents=True, exist_ok=True)
    (mirror / rel).write_text("x\n", encoding="utf-8")
    hits = export_public.verify(mirror)
    assert any(hit.path == rel and hit.gate == "layout" for hit in hits), hits


@pytest.mark.parametrize("rel", export_public.SHIPS.required)
def test_the_layout_class_trips_on_a_missing_required_file(rel: str, tmp_path) -> None:
    mirror = _clean_mirror(tmp_path)
    (mirror / rel).unlink()
    hits = export_public.verify(mirror)
    assert [(hit.path, hit.gate) for hit in hits] == [(rel, "layout")]


def test_the_gate_is_word_prefix_bounded_and_spares_the_labelled_fakes(tmp_path) -> None:
    mirror = _clean_mirror(tmp_path)
    benign = [
        "the bug made the tile vanish",  # carries a name's letters, not at a word start
        "KEY = 'sk-or-v1-FAKE-KEY-DO-NOT-USE-0000000000000000'",  # the audit's labelled fake
        "PRESENT = 'sk-fixture-presence-only'",
        "OPENROUTER_API_KEY = $OPENROUTER_API_KEY",  # an env reference, not a value
        "cd arc-agi-games && ls ~/code",
    ]
    (mirror / "gen" / "a.py").write_text("\n".join(benign) + "\n", encoding="utf-8")
    assert export_public.verify(mirror) == []


def test_the_shipped_hygiene_modules_never_spell_what_they_hunt() -> None:
    """The gate sweeps its own source in the mirror; it must not trip on itself."""
    for module in (public_hygiene, export_public, sync_canon):
        path = Path(module.__file__)
        text = path.read_text(encoding="utf-8")
        assert public_hygiene.scan_text(path.name, text) == [], path.name


# =============================================================================
# 3. scrub — runtime strings, canon, sync round trip
# =============================================================================

RUNTIME_STRINGS = {
    "gen/backends.py": "refused (operator ruling 2026-09-21: scoped tools, no permission bypass)",
    "gen/orchestrator.py": "oversight is post-package (operator ruling, 2026-09-29)",
    "gen/s1_spec.py": "(tiers.goal_legible_cap — the operator's ",
    "gen/s3_static.py": "games must tag the cells a click acts on (operator ruling, 2026-09-28)",
    "gen/s6_package.py": "games enter games/ (operator ruling, docs/v2/DECISIONS.md 2026-09-29)",
    "gen/tools/sync_canon.py": "(operator ruling, 2026-09-29; contract P-2)",
}


@pytest.mark.parametrize("rel", sorted(RUNTIME_STRINGS))
def test_the_runtime_strings_carry_the_neutral_form(rel: str) -> None:
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert RUNTIME_STRINGS[rel] in text, f"{rel}: the neutral ruling form is gone"
    assert not public_hygiene.has_person_name(text), f"{rel} still names a person"


def test_the_backend_refusal_prints_the_neutral_form() -> None:
    """The one runtime string a user can hit without a batch: the bypass refusal."""
    from gen import backends

    driver = backends.LocalClaudeDriver()
    mode = min(backends.BYPASS_PERMISSION_MODES)
    with pytest.raises(backends.DriverError) as excinfo:
        driver.session("x", cwd=REPO_ROOT, permission_mode=mode)
    message = str(excinfo.value)
    assert "operator ruling 2026-09-21" in message
    assert not public_hygiene.has_person_name(message)


def test_the_canon_stamp_matches_the_scrubbed_files() -> None:
    assert sync_canon.verify_provenance(CANON_ROOT) == []
    record = sync_canon.parse_provenance((CANON_ROOT / "PROVENANCE.md").read_text("utf-8"))
    assert record["source"] == "../duckWM/local-docs/arc-agi-3-generator"
    assert sync_canon.RE_ARC_3_LICENSE in record["files"]


def test_the_vendored_canon_is_already_neutral() -> None:
    """Idempotence: the sync's scrub changes nothing it has already scrubbed."""
    for rel in sync_canon.derive_canon_paths(CANON_ROOT):
        data = (CANON_ROOT / rel).read_bytes()
        assert sync_canon.neutralize_canon(rel, data) == data, rel
        assert sync_canon.neutralization_residue(rel, data) == [], rel


# (upstream line, as duckWM writes it) -> (the vendored line it must become)
_UPSTREAM_TO_PUBLIC = (
    (lambda: f"Source: `{_home('x')}Documents/GitHub/arc-agi/duckWM/games/cd82/fb555c5d/cd82.py`",
     "Source: `duckWM/games/cd82/fb555c5d/cd82.py`"),
    (lambda: f"Frames: {_home('x')}w/duckWM/local-docs/arc-agi-3-generator/out/frames/lf52/ (10)",
     "Frames: duckWM/local-docs/arc-agi-3-generator/out/frames/lf52/ (10)"),
    (lambda: f"engine `{_home('x')}.cache/uv/archive-v0/K/arcengine`): done",
     "engine `$UV_CACHE_DIR/archive-v0/K/arcengine`): done"),
    (lambda: f"# **SIGNED OFF ({_given_name()}, 2026-09-18)**",
     "# **SIGNED OFF (operator, 2026-09-18)**"),
    (lambda: f"(source: x; header corrected, {_given_name()}'s R1 ruling 2026-09-22)",
     "(source: x; header corrected, operator R1 ruling 2026-09-22)"),
    (lambda: f"flagged unverified** ({_given_name()}'s ruling —",
     "flagged unverified** (operator ruling —"),
    (lambda: f"read).\n  {_given_name()}'s ruling: keep the term",
     "read).\n  Operator ruling: keep the term"),
    (lambda: f"from the closed vocabulary {_given_name()}'s manual-play workstream validated",
     "from the closed vocabulary the operator's manual-play workstream validated"),
    (lambda: f"adjudicated **absent** by {_given_name().lower()}-tiebreak.",
     "adjudicated **absent** by operator-tiebreak."),
    (lambda: f'is recorded in the cell notes for {_given_name()}"',
     'is recorded in the cell notes for the operator"'),
    (lambda: "an operator ruling that already says operator stays as it is",
     "an operator ruling that already says operator stays as it is"),
)


@pytest.mark.parametrize("index", range(len(_UPSTREAM_TO_PUBLIC)))
def test_the_neutralization_maps_each_upstream_form(index: int) -> None:
    upstream, public = _UPSTREAM_TO_PUBLIC[index]
    out = sync_canon.neutralize_canon("design/objects/x.md", upstream().encode("utf-8"))
    assert out.decode("utf-8") == public


def test_a_sync_from_an_unscrubbed_upstream_reproduces_the_public_canon(tmp_path) -> None:
    """The round trip, hermetic: re-dirty the vendored canon, sync, get it back."""
    upstream = tmp_path / "upstream"
    for rel in sync_canon.derive_canon_paths(CANON_ROOT):
        if rel in sync_canon.GENERATED_FILES:
            continue  # a generated file has no upstream copy
        text = (CANON_ROOT / rel).read_bytes().decode("utf-8")  # bytes: the CSVs are CRLF
        text = text.replace("`duckWM/games/", f"`{_home('m')}Documents/GitHub/arc-agi/duckWM/games/")
        text = text.replace("SIGNED OFF (operator,", f"SIGNED OFF ({_given_name()},")
        (upstream / rel).parent.mkdir(parents=True, exist_ok=True)
        (upstream / rel).write_bytes(text.encode("utf-8"))
    dirty = [rel for rel in sync_canon.derive_canon_paths(CANON_ROOT)
             if rel not in sync_canon.GENERATED_FILES
             and (upstream / rel).read_bytes() != (CANON_ROOT / rel).read_bytes()]
    assert len(dirty) >= 10, f"the round trip must re-dirty real files, did {dirty}"

    dest = tmp_path / "dest"
    assert sync_canon.main(["--source", str(upstream), "--dest", str(dest)]) == 0
    for rel in sync_canon.derive_canon_paths(CANON_ROOT):
        assert (dest / rel).read_bytes() == (CANON_ROOT / rel).read_bytes(), rel
    assert sync_canon.verify_provenance(dest) == []

    plan = sync_canon.plan_sync(upstream, CANON_ROOT)
    assert not plan.changed and not plan.new and not plan.orphans, (
        "the vendored canon is not what a sync from this upstream writes"
    )


def test_a_sync_refuses_what_it_cannot_scrub(tmp_path, capsys) -> None:
    upstream = tmp_path / "upstream"
    for rel in sync_canon.derive_canon_paths(CANON_ROOT):
        if rel in sync_canon.GENERATED_FILES:
            continue
        (upstream / rel).parent.mkdir(parents=True, exist_ok=True)
        (upstream / rel).write_bytes((CANON_ROOT / rel).read_bytes())
    victim = upstream / "spec-v0.3.md"
    victim.write_bytes(victim.read_bytes() + f"\nby {_given_name()}{_family_name()}\n".encode())
    dest = tmp_path / "dest"
    assert sync_canon.main(["--source", str(upstream), "--dest", str(dest)]) == 2
    assert "spec-v0.3.md" in capsys.readouterr().err
    assert not dest.exists(), "a refused sync wrote something"


@pytest.mark.skipif(not DUCKWM_DOCS.is_dir(), reason="no duckWM checkout beside this repo")
def test_a_sync_from_the_real_duckwm_changes_nothing() -> None:
    plan = sync_canon.plan_sync(DUCKWM_DOCS, CANON_ROOT)
    assert (plan.new, plan.changed, plan.orphans) == ([], [], [])


def test_third_party_files_are_never_rewritten() -> None:
    for rel in ("third-party/re-arc-3/game_generation_prompt.md",
                "third-party/re-arc-3/spec_prompt.md"):
        planted = (CANON_ROOT / rel).read_bytes() + f"\n{_home('q')}x\n".encode()
        assert sync_canon.neutralize_canon(rel, planted) == planted, rel
        assert sync_canon.neutralization_residue(rel, planted), "residue must still see it"


def test_the_license_notice_is_generated_and_complete() -> None:
    text = (CANON_ROOT / sync_canon.RE_ARC_3_LICENSE).read_text(encoding="utf-8")
    assert text == sync_canon.render_re_arc_3_license()
    for needle in ("Tufalabs re-arc-3 v0.1.2", "jeroencottaar/taaf-kaggle-source",
                   "vendored 2026-09-21", "Harold Bessis", "Stefano Viel", "MIT License",
                   "THE SOFTWARE IS PROVIDED \"AS IS\"", "dataset-level license field".upper()):
        assert needle.lower() in text.lower(), needle


# =============================================================================
# 4. the public clone
# =============================================================================


def test_d8_skips_rather_than_fails_without_the_smoke_ledger(tmp_path, monkeypatch) -> None:
    import test_v2_codex

    monkeypatch.setattr(test_v2_codex, "SMOKE_LOG", tmp_path / "no-smoke.jsonl")
    with pytest.raises(pytest.skip.Exception):
        test_v2_codex.test_d8_the_live_401_records_still_parse_as_codex_auth_failures()


@requires_git
def test_the_smoke_ledger_stays_ignored_and_untracked() -> None:
    rel = "out/smoke/smoke.jsonl"
    assert _git("check-ignore", "-q", "--no-index", rel).returncode == 0, f"{rel} is not ignored"
    assert _git("ls-files", "--error-unmatch", rel).returncode != 0, f"{rel} is TRACKED"
    assert not export_public.ships(rel)


def _fallback_config(tmp_path: Path, monkeypatch, *, armed: bool) -> Path:
    sibling = tmp_path / "duckWM"  # never created: the absent sibling
    monkeypatch.setattr(gen_config, "DUCKWM_SIBLING", sibling)
    if armed:
        monkeypatch.setenv(gen_config.CANON_FALLBACK_ENV, "1")
    else:
        monkeypatch.delenv(gen_config.CANON_FALLBACK_ENV, raising=False)
    cfg = yaml.safe_load((REPO_ROOT / "config" / "b001-pilot.yaml").read_text("utf-8"))
    cfg["duckwm_docs"] = str(sibling / "local-docs" / "arc-agi-3-generator")
    cfg["duckwm_games"] = str(sibling / "games" / "official")
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


def test_the_clone_fallback_is_off_by_default(tmp_path, monkeypatch) -> None:
    path = _fallback_config(tmp_path, monkeypatch, armed=False)
    with pytest.raises(FileNotFoundError):
        gen_config.load_config(path)


def test_the_armed_fallback_reads_the_vendored_canon_and_drops_the_corpus(
    tmp_path, monkeypatch
) -> None:
    cfg = gen_config.load_config(_fallback_config(tmp_path, monkeypatch, armed=True))
    assert Path(cfg["duckwm_docs"]) == CANON_ROOT.resolve()
    assert "duckwm_games" not in cfg


def test_the_armed_fallback_never_masks_any_other_missing_path(tmp_path, monkeypatch) -> None:
    path = _fallback_config(tmp_path, monkeypatch, armed=True)
    cfg = yaml.safe_load(path.read_text("utf-8"))
    cfg["duckwm_docs"] = str(tmp_path / "elsewhere" / "canon")
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        gen_config.load_config(path)


def test_a_suite_run_of_the_leak_sites_leaves_out_byte_identical(tmp_path) -> None:
    """The known leaks, re-run: the officials latency JSON, and the dedupe-history
    mtime that THREE snapshot/restore fixtures moved by rewriting identical bytes."""
    out = REPO_ROOT / "out"

    def sweep() -> dict[str, tuple[int, int]]:
        if not out.is_dir():
            return {}
        return {p.relative_to(out).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in out.rglob("*") if p.is_file()}

    before = sweep()
    env = {k: v for k, v in os.environ.items() if k != "OFFICIALS_LATENCY_JSON"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "gen/tests/test_b4_sampler.py", "gen/tests/test_b003_tiers_s0.py",
         "gen/tests/test_v2_hardening.py", "gen/tests/test_officials_conformance.py",
         "--basetemp", str(tmp_path / "pt")],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=600, check=False,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    after = sweep()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    assert not changed, f"a suite run wrote under out/: {changed}"


def test_every_private_evidence_entry_names_a_real_test() -> None:
    """The clone manifest cannot go stale: each entry names a test that exists."""
    import conftest

    stale = []
    for evidence in conftest.PRIVATE_EVIDENCE:
        assert evidence.paths and evidence.tests, evidence
        for entry in evidence.tests:
            module, _, name = entry.partition("::")
            source = Path(__file__).with_name(module)
            stem = name.rstrip("*")
            if not source.is_file() or f"def {stem}" not in source.read_text("utf-8"):
                stale.append(entry)
    assert not stale, f"conftest.PRIVATE_EVIDENCE names tests that do not exist: {stale}"


def test_the_clone_manifest_is_inert_beside_duckwm() -> None:
    """In the maintainers' checkout nothing is armed and nothing is skipped."""
    import conftest

    if conftest.PUBLIC_CLONE:
        pytest.skip("this is a public clone: the manifest is meant to act here")
    assert os.environ.get(gen_config.CANON_FALLBACK_ENV) != "1"
    from gen import officials

    assert officials.discover_officials.__name__ == "discover_officials"
