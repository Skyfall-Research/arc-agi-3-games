"""Blind pins for contract C-1 — S2 patch-baseline rebuilds.

Run: .venv/bin/python -m pytest gen/tests/test_b003_patchbaseline.py -v

Written from the frozen C-1 contract ALONE (blind test writer).  No in-progress
C-1 diff of `gen/s2_implement.py` or `gen/orchestrator.py` was read; both
modules' PRE-EXISTING surfaces were taken from `git show HEAD:<path>` so that
nothing here pins the landed-but-unrelated V-A (s2_implement) and V-C
(orchestrator) work that also sits in the working tree.  What this file is
allowed to know, and does: `build_payload`, `findings_section`,
`FINDINGS_HEADER`, `FINDINGS_INSTRUCTIONS` and `_resolve_cap`'s
`implementer`-block reading convention as they stand at HEAD; the HEAD shape of
the `s2_implement` runner inside `default_runners()` (payload built, findings
appended on a disk reject, `payload.md` written, `green_loop` run); the sibling
blind suite `test_b003_corrwindow.py`, whose file shape this one follows; and
the shipped corpus under `out/`.  These pins therefore describe the CONTRACT,
not the implementation, and are expected to fail until C-1 lands.

WHY THE BASELINE SECTION EXISTS (the measured failure, stated from the contract)

A re-implement after an S2b reject rebuilds from the SAME payload plus the
findings feed, and the session FRESH-TRANSLATES the spec each lap: b002 slot 3
lost two laps to the term seesaw — a term implemented one way in lap N vanishes
in lap N+1's retranslation and the blind audit flags the flip.  The previous,
validate-green `game.py` is ALREADY on disk in the worker dir when the rebuild
session starts (the runner re-instantiates nothing when the worker exists).  The
fix is S1's escalation-baseline pattern applied to S2: tell the session the file
is its baseline and to MODIFY it.

THE FIVE PINS, in the contract's order

1. `patch_baseline_enabled(cfg)` — `implementer.patch_baseline` absent => False;
   True/False parse; `"yes"` => ValueError (and every other non-bool with it,
   because the contract says bool-validated fail-loud).
2. `PATCH_BASELINE_SECTION` starts with the frozen heading and contains
   "make validate"; plus the contract's "transcribe exactly" instruction, pinned
   on the words rather than on the re-wrapping.
3. `baseline_sha(worker)` — sha256 of `worker/game.py` BYTES, None when absent.
4. Runner-source pin, `gen/orchestrator.py` read as TEXT (never imported, never
   executed): the s2 runner references `patch_baseline_enabled`,
   `PATCH_BASELINE_SECTION` and `"patch_baseline_sha"`, and the section is
   appended AFTER the findings section in source order.
5. Knob-off byte-identity at the composition level: `build_payload` +
   `findings_section` on a tmp copy of a shipped spec dir with a fabricated
   reject report carries none of the C-1 bytes, and the knob-on prompt is
   exactly those bytes plus `"\\n"` plus the section.  Pieces called directly;
   no driver, no session, no `green_loop`.

AMBIGUITIES RESOLVED (each is quoted in the failure message that depends on it)

  a. "default False" is read as: no `implementer` block at all, an
     `implementer` block without the key, and the shipped configs (neither
     b001-pilot nor b002-triple carries the key) all read False.  The reader
     must therefore not require the block to exist — `_resolve_cap`'s
     "config missing implementer.X" fail-loud is the wrong precedent for an
     opt-in knob, and `s3_verify._lever_corroboration` is the right one.
  b. `patch_baseline: null` is NOT pinned either way.  The sibling C-2 contract
     said "absent/null => None" out loud; C-1 says only "absent ⇒ False", and a
     null is equally readable as the absent spelling or as a non-bool.  Left
     open deliberately rather than guessed at.
  c. The ValueError MESSAGE is not pinned.  C-2 said "ValueError naming the
     key"; C-1 says only "bool-validated fail-loud", so only the type is frozen.
  d. `baseline_sha` returns the BARE hex digest, not a `sha256:`-prefixed one:
     `orchestrator._sha256_file` and `_game_hash` are the house precedent and
     the contract says "sha256 of worker/game.py bytes".  It hashes game.py
     ALONE — a worker with a solver.py beside it must not slide into
     `_game_hash`'s `game.py + solver.py` concatenation, which is a DIFFERENT
     digest under the same intuition.
  e. "None when absent" covers both a worker dir with no game.py and a worker
     dir that does not exist; a missing worker is the commonest absence (first
     lap, nothing built yet) and it cannot be an error, or the knob would crash
     the first build of every slot.
  f. The section's lack of a trailing newline is pinned in its own test
     (`test_pin2_section_carries_no_trailing_newline`) so an adjudication moves
     one line.  It follows from the contract's transcription, whose closing
     quotes sit immediately after `usual.`, but it is in real tension with
     `findings_section`'s documented reason for ending
     in "\\n" ("so an appended section still leaves `payload.md`
     newline-terminated"): with the knob on, `payload.md` ends at "usual." with
     no newline.  FLAGGED, not silently resolved.
  g. Where `"patch_baseline_sha"` lands inside the runner's artifacts is not
     pinned (the contract says "the runner's artifacts" and the runner has three
     returns); pin 4 pins the literal's PRESENCE in the runner, never its
     position.  Pin 4 also compares source ORDER using the last non-import
     mention of the constant, because the runner imports every name it uses at
     its top and an `from .s2_implement import (PATCH_BASELINE_SECTION, ...)`
     line would otherwise sit "before" the findings call by construction.
  h. The contract's own §3 checks (full suite, ruff, the grep proof that only
     the runner and `_run_payload` compose the S2 prompt) are the implementer's
     to run and are NOT restated here as tests.

This file writes only inside `tmp_path`.  The canon, `out/`, the configs and
every other source file are read-only here.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

from gen import s2_implement
from gen.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_PY = REPO_ROOT / "gen" / "orchestrator.py"

# A shipped spec dir with a reject history (the contract names this one).  Read
# only; every test works on a tmp copy of the three files `build_payload` and
# `baseline_sha` actually touch.
SHIPPED_SPEC = REPO_ROOT / "out" / "corpus" / "b002-triple" / "core-ward-phase-gates"
BASE_CONFIG = "config/b002-triple.yaml"
SHIPPED_CONFIGS = ("config/b001-pilot.yaml", "config/b002-triple.yaml")

# Contract wording, not code names.
KNOB_BLOCK = "implementer"
KNOB = "patch_baseline"
ARTIFACT_KEY = "patch_baseline_sha"
RUNNER_NAME = "s2_implement"

SECTION_HEADING = "## YOUR BASELINE — modify, do not re-translate"
# Transcribed from the contract's §1 code block, verbatim.
SECTION_TEXT = """\
## YOUR BASELINE — modify, do not re-translate

`game.py` and `solver.py` in this worker are YOUR OWN previous
implementation of this same spec: it passed `make validate` and was
rejected by the blind audit only for the findings listed above. Treat it
as the baseline. Fix EXACTLY what the findings name and keep everything
else byte-stable: every gratuitous re-translation re-rolls the blind
audit and has cost this pipeline whole laps. Do not restructure, rename,
or rewrite working mechanics; run `make validate` after your edits as
usual."""

_ABSENT = object()


# --------------------------------------------------------------------------
# the surface under test, fetched rather than assumed
# --------------------------------------------------------------------------


def _reader():
    """`patch_baseline_enabled` — the contract's own spelling for the reader."""
    reader = getattr(s2_implement, "patch_baseline_enabled", None)
    assert callable(reader), (
        "gen.s2_implement has no `patch_baseline_enabled(cfg) -> bool`. C-1 §1 names it, "
        f"reading `{KNOB_BLOCK}.{KNOB}`, default False, bool-validated fail-loud"
    )
    return reader


def _enabled(cfg: Mapping) -> object:
    return _reader()(cfg)


def _section() -> str:
    section = getattr(s2_implement, "PATCH_BASELINE_SECTION", None)
    assert isinstance(section, str), (
        "gen.s2_implement has no module-level `PATCH_BASELINE_SECTION` string. C-1 §1: "
        "transcribe it exactly, beside FINDINGS_INSTRUCTIONS"
    )
    return section


def _baseline_sha(worker: Path) -> object:
    fn = getattr(s2_implement, "baseline_sha", None)
    assert callable(fn), (
        "gen.s2_implement has no `baseline_sha(worker) -> str | None`. C-1 §1: sha256 of "
        "worker/game.py bytes, None when absent"
    )
    return fn(worker)


def _cfg(base: Mapping, value: object = _ABSENT) -> dict:
    """A config with `implementer.patch_baseline` forced on, off or absent."""
    cfg = copy.deepcopy(dict(base))
    block = dict(cfg.get(KNOB_BLOCK) or {})
    block.pop(KNOB, None)
    if value is not _ABSENT:
        block[KNOB] = value
    cfg[KNOB_BLOCK] = block
    return cfg


def _bare(value: object = _ABSENT) -> dict:
    """The same, with no surrounding run config — the reader needs only the
    `implementer` block, exactly as `_resolve_token_cap` needs only it."""
    return _cfg({}, value)


def _words(text: str) -> str:
    """Whitespace-normalized text: pins the WORDS of a transcribed prompt
    section without pinning the column its author wrapped it at."""
    return " ".join(text.split())


# --------------------------------------------------------------------------
# gen/orchestrator.py as TEXT — never imported, never executed (pin 4)
# --------------------------------------------------------------------------


def _orchestrator_text() -> str:
    assert ORCHESTRATOR_PY.is_file(), f"{ORCHESTRATOR_PY} is missing"
    return ORCHESTRATOR_PY.read_text(encoding="utf-8")


def _runner_source() -> str:
    """The `def s2_implement(ctx)` runner's source, sliced out by indentation.

    The runner is a closure inside `default_runners()`, so it is located by its
    `def` line and ended at the first later line whose indent is no deeper.
    """
    text = _orchestrator_text()
    lines = text.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if line.strip().startswith(f"def {RUNNER_NAME}("):
            start = index
            break
    assert start is not None, (
        f"{ORCHESTRATOR_PY} has no `def {RUNNER_NAME}(` — this file pins the s2 runner by "
        "name, and the name moved"
    )
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            end = index
            break
    return "".join(lines[start:end])


def _runner_ast() -> ast.FunctionDef:
    for node in ast.walk(ast.parse(_orchestrator_text(), filename=str(ORCHESTRATOR_PY))):
        if isinstance(node, ast.FunctionDef) and node.name == RUNNER_NAME:
            return node
    raise AssertionError(f"no `def {RUNNER_NAME}` FunctionDef in {ORCHESTRATOR_PY}")


def _name_linenos(func: ast.FunctionDef, name: str) -> list[int]:
    """Lines where `name` is USED as a name — import aliases are not `ast.Name`
    nodes, so the runner's own `from .s2_implement import (...)` block is
    excluded for free (ambiguity g)."""
    return sorted(
        node.lineno
        for node in ast.walk(func)
        if isinstance(node, ast.Name) and node.id == name
    )


def _call_linenos(func: ast.FunctionDef, name: str) -> list[int]:
    return sorted(
        node.lineno
        for node in ast.walk(func)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    )


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_cfg() -> dict:
    cfg = load_config(BASE_CONFIG)
    assert isinstance(cfg.get(KNOB_BLOCK), Mapping), (
        f"fixture wall: {BASE_CONFIG} no longer carries an `{KNOB_BLOCK}` block"
    )
    assert KNOB not in cfg[KNOB_BLOCK], (
        f"fixture wall: {BASE_CONFIG} now sets `{KNOB_BLOCK}.{KNOB}` — this suite assumes the "
        "shipped configs opt into nothing (ambiguity a)"
    )
    return cfg


@pytest.fixture
def spec_copy(tmp_path: Path) -> Path:
    """A tmp copy of the shipped spec dir — only the files the composition
    seam reads: spec.md, spec.yaml, and the worker's previous game.py/solver.py
    (the baseline the knob points the session at)."""
    assert SHIPPED_SPEC.is_dir(), (
        f"fixture wall: {SHIPPED_SPEC} is gone — C-1 §3 names this shipped spec dir (it has a "
        "reject history) as the composition proof's input"
    )
    dest = tmp_path / "spec"
    (dest / "worker").mkdir(parents=True)
    for name in ("spec.md", "spec.yaml"):
        shutil.copy2(SHIPPED_SPEC / name, dest / name)
    for name in ("game.py", "solver.py"):
        source = SHIPPED_SPEC / "worker" / name
        assert source.is_file(), f"fixture wall: {source} is gone"
        shutil.copy2(source, dest / "worker" / name)
    return dest


@pytest.fixture
def reject_report() -> dict:
    """A fabricated S2b reject, minimal and valid for `findings_section`: two
    findings, one carrying a lever and a detail, one a bare term."""
    return {
        "verdict": "reject",
        "reject_reasons": [
            {
                "code": "undeclared-deception",
                "lever": "decoy",
                "detail": "synthetic fixture finding (C-1 blind pins)",
            },
            {"code": "declared-unreachable", "term": "move.grid"},
        ],
    }


# --------------------------------------------------------------------------
# PIN 1 — patch_baseline_enabled
# --------------------------------------------------------------------------


def test_pin1_absent_knob_is_false() -> None:
    """Knob absent ⇒ byte-identical behavior, and that starts with the reader
    saying False rather than raising (ambiguity a)."""
    assert _enabled({}) is False, (
        "a config with no `implementer` block at all must read False: C-1's opt-in knob "
        "cannot require a block that older batch configs never wrote"
    )
    assert _enabled(_bare()) is False
    assert _enabled({KNOB_BLOCK: {"max_green_attempts": 12, "session_token_cap": "400k"}}) is False


def test_pin1_shipped_configs_read_false() -> None:
    """The real, frozen batch configs opt into nothing (ambiguity a)."""
    for name in SHIPPED_CONFIGS:
        cfg = load_config(name)
        assert _enabled(cfg) is False, (
            f"{name} reads the knob as on without setting it — 'knob absent ⇒ byte-identical "
            "behavior' is the whole default"
        )


def test_pin1_true_and_false_parse() -> None:
    assert _enabled(_bare(True)) is True
    assert _enabled(_bare(False)) is False


def test_pin1_yes_string_is_a_loud_valueerror() -> None:
    """The contract's own example: `"yes"` is a truthy string that would
    silently turn the knob on. Type only — the message is not pinned
    (ambiguity c)."""
    with pytest.raises(ValueError):
        _enabled(_bare("yes"))


@pytest.mark.parametrize("value", ["true", "false", "no", "", 1, 0, 1.0, [], {}, ["x"]])
def test_pin1_every_other_non_bool_is_loud(value: object) -> None:
    """"bool-validated fail-loud" (C-1 §1) — `1` and `"true"` are exactly the
    values `s3_verify._lever_corroboration` refuses for the same reason."""
    with pytest.raises(ValueError):
        _enabled(_bare(value))


def test_pin1_reading_a_real_config_with_the_knob_on(base_cfg: dict) -> None:
    """Set on a real config, on a real `implementer` block beside the caps the
    green loop already reads."""
    cfg = _cfg(base_cfg, True)
    assert cfg[KNOB_BLOCK]["max_green_attempts"] == base_cfg[KNOB_BLOCK]["max_green_attempts"]
    assert _enabled(cfg) is True
    assert _enabled(_cfg(base_cfg, False)) is False


# --------------------------------------------------------------------------
# PIN 2 — PATCH_BASELINE_SECTION
# --------------------------------------------------------------------------


def test_pin2_section_heading_and_make_validate() -> None:
    section = _section()
    assert section.startswith(SECTION_HEADING), (
        f"PATCH_BASELINE_SECTION must START with {SECTION_HEADING!r} (C-1 test pin 2) — it is "
        f"spliced into a 135k-char payload and the heading is how the session finds it; got "
        f"{section[: len(SECTION_HEADING) + 10]!r}"
    )
    assert "make validate" in section, (
        "PATCH_BASELINE_SECTION must contain 'make validate' (C-1 test pin 2): the section "
        "tells the session to modify the baseline, and the green loop still gates on validate"
    )


def test_pin2_section_is_the_contract_transcription() -> None:
    """"Transcribe exactly" (C-1 §1), pinned on the words rather than on the
    column the author wrapped them at."""
    assert _words(_section()) == _words(SECTION_TEXT), (
        "PATCH_BASELINE_SECTION is not the contract's text. C-1 §1 says transcribe exactly; "
        "this pin normalizes whitespace only, so the diff is in the WORDS"
    )


def test_pin2_section_shape_is_heading_blank_line_body() -> None:
    """A markdown section, not a paragraph: the heading owns its own line and a
    blank line follows it, or the body renders into the heading."""
    lines = _section().splitlines()
    assert lines[0] == SECTION_HEADING, f"first line is {lines[0]!r}"
    assert lines[1] == "", (
        f"no blank line under the heading (line 2 is {lines[1]!r}) — the payload is markdown "
        "and every other section in build_payload separates heading from body"
    )
    assert "`game.py`" in _section() and "`solver.py`" in _section(), (
        "the section names the two baseline files the session is to modify"
    )


def test_pin2_section_carries_no_trailing_newline() -> None:
    """Ambiguity f, pinned on its own line so an adjudication moves one line.

    The contract's transcription closes its quotes immediately after `usual.`,
    so there is no trailing newline. That is in real tension with
    `findings_section`, which ends in "\\n" precisely "so
    an appended section still leaves `payload.md` newline-terminated": with the
    knob on, the recorded payload.md now ends at "usual." with no newline.
    """
    section = _section()
    assert section.endswith("usual."), f"section ends {section[-20:]!r}"
    assert not section.endswith("\n"), (
        "PATCH_BASELINE_SECTION ends with a newline; the contract's transcription does not. "
        "If the lead adjudicates the other way (payload.md newline-termination), this is the "
        "one line to change"
    )


def test_pin2_section_does_not_disturb_the_findings_feed() -> None:
    """The two prompt constants are siblings, not substrings of one another."""
    section = _section()
    assert section != s2_implement.FINDINGS_INSTRUCTIONS
    assert s2_implement.FINDINGS_HEADER not in section
    assert s2_implement.FINDINGS_INSTRUCTIONS not in section
    assert SECTION_HEADING not in s2_implement.FINDINGS_INSTRUCTIONS
    assert SECTION_HEADING not in s2_implement.FINDINGS_HEADER


# --------------------------------------------------------------------------
# PIN 3 — baseline_sha
# --------------------------------------------------------------------------


def test_pin3_baseline_sha_is_sha256_of_game_py_bytes(tmp_path: Path) -> None:
    worker = tmp_path / "worker"
    worker.mkdir()
    # Non-ASCII on purpose: the digest is over BYTES, not over decoded text.
    blob = "class Game:\n    tell = '↑ core-ward'\n".encode()
    (worker / "game.py").write_bytes(blob)

    assert _baseline_sha(worker) == hashlib.sha256(blob).hexdigest(), (
        "baseline_sha must be the bare hex sha256 of worker/game.py's bytes (C-1 §1; "
        "`orchestrator._sha256_file` is the house precedent for the bare digest — ambiguity d)"
    )


def test_pin3_baseline_sha_hashes_game_py_alone(tmp_path: Path) -> None:
    """Ambiguity d: NOT `_game_hash`'s `game.py + solver.py` concatenation — a
    solver-only edit must leave the recorded baseline sha unchanged, or the
    ledger stops answering 'which game.py did this lap patch?'."""
    worker = tmp_path / "worker"
    worker.mkdir()
    game = b"# game\n"
    (worker / "game.py").write_bytes(game)
    (worker / "solver.py").write_bytes(b"# solver v1\n")
    first = _baseline_sha(worker)

    (worker / "solver.py").write_bytes(b"# solver v2 - a different file entirely\n")
    assert _baseline_sha(worker) == first == hashlib.sha256(game).hexdigest()


def test_pin3_baseline_sha_is_none_without_game_py(tmp_path: Path) -> None:
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / "solver.py").write_bytes(b"# solver only\n")
    assert _baseline_sha(worker) is None, (
        "a worker with no game.py has no baseline — C-1 §1: None when absent"
    )


def test_pin3_baseline_sha_is_none_for_a_missing_worker(tmp_path: Path) -> None:
    """Ambiguity e: the commonest absence is the first lap, where the worker dir
    does not exist yet. It cannot raise, or the knob breaks every fresh slot."""
    assert _baseline_sha(tmp_path / "never-instantiated") is None


def test_pin3_baseline_sha_follows_the_file(tmp_path: Path) -> None:
    """Two laps, two baselines: the sha the ledger records identifies WHICH
    bytes a lap patched."""
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / "game.py").write_bytes(b"lap 1\n")
    lap1 = _baseline_sha(worker)
    (worker / "game.py").write_bytes(b"lap 2\n")
    lap2 = _baseline_sha(worker)

    assert lap1 != lap2
    assert {lap1, lap2} == {hashlib.sha256(b"lap 1\n").hexdigest(),
                            hashlib.sha256(b"lap 2\n").hexdigest()}


def test_pin3_baseline_sha_on_the_shipped_worker(spec_copy: Path) -> None:
    """Against a real, shipped, previously-green worker — the exact state the
    knob fires in."""
    worker = spec_copy / "worker"
    expected = hashlib.sha256((worker / "game.py").read_bytes()).hexdigest()
    assert _baseline_sha(worker) == expected
    assert len(expected) == 64


# --------------------------------------------------------------------------
# PIN 4 — the runner splice, gen/orchestrator.py read as TEXT
# --------------------------------------------------------------------------


def test_pin4_runner_is_locatable_and_still_composes_the_prompt() -> None:
    """Fixture wall for the three pins below: the surface C-1 splices into."""
    source = _runner_source()
    for anchor in ("build_payload", "findings_section(", "payload.md", "green_loop"):
        assert anchor in source, (
            f"the {RUNNER_NAME} runner no longer mentions {anchor!r}; this file pins the C-1 "
            "splice against the HEAD shape of that runner"
        )


def test_pin4_runner_references_the_knob_the_section_and_the_artifact_key() -> None:
    source = _runner_source()
    missing = [
        name
        for name in ("patch_baseline_enabled", "PATCH_BASELINE_SECTION", ARTIFACT_KEY)
        if name not in source
    ]
    assert not missing, (
        f"the {RUNNER_NAME} runner in {ORCHESTRATOR_PY} does not mention {missing} — C-1 §2: "
        "the reject-feed branch gates on `patch_baseline_enabled(ctx.cfg)` and worker/game.py, "
        f"appends PATCH_BASELINE_SECTION, and records {ARTIFACT_KEY!r} in the runner's artifacts"
    )


def test_pin4_section_is_appended_after_the_findings_section() -> None:
    """C-1 §2: AFTER the findings section. Order is read off the AST so the
    runner's own import block does not count as a mention (ambiguity g)."""
    func = _runner_ast()
    findings_calls = _call_linenos(func, "findings_section")
    section_uses = _name_linenos(func, "PATCH_BASELINE_SECTION")

    assert findings_calls, "the runner no longer calls findings_section()"
    assert section_uses, (
        "PATCH_BASELINE_SECTION is never USED in the runner (only imported, if that): C-1 §2 "
        "appends it to the prompt"
    )
    assert min(section_uses) > max(findings_calls), (
        f"PATCH_BASELINE_SECTION is used at line(s) {section_uses} but findings_section() is "
        f"called at {findings_calls} — the baseline section rides AFTER the findings, so the "
        "rebuild reads what it must fix before it is told what to treat as baseline"
    )


def test_pin4_section_is_appended_with_the_contract_separator() -> None:
    r"""C-1 §2 spells the append `"\n" + PATCH_BASELINE_SECTION`, matching the
    findings splice one line above it. Pinned on its own line (ambiguity f/g):
    if the lead adjudicates a different separator, one line moves."""
    source = _runner_source()
    assert '"\\n" + PATCH_BASELINE_SECTION' in source, (
        "no `\"\\n\" + PATCH_BASELINE_SECTION` in the s2 runner. C-1 §2 appends exactly that, "
        "so the section is separated from the findings by one blank-line join, as "
        "`findings_section` already is from the payload"
    )


def test_pin4_artifact_key_is_a_string_literal_in_the_runner() -> None:
    """C-1 §2: `"patch_baseline_sha": <sha>` in the runner's artifacts, so the
    ledger shows which baseline a lap patched. Position not pinned (ambiguity g)."""
    func = _runner_ast()
    literals = [
        node.value
        for node in ast.walk(func)
        if isinstance(node, ast.Constant) and node.value == ARTIFACT_KEY
    ]
    assert literals, (
        f"the {RUNNER_NAME} runner carries no {ARTIFACT_KEY!r} string literal — the sha has to "
        "reach the ledger as an artifact key, not only the prompt"
    )


def test_pin4_baseline_sha_is_what_the_runner_records() -> None:
    """The recorded sha comes from the C-1 helper, not a re-rolled digest: the
    runner must reference `baseline_sha` beside the artifact key."""
    source = _runner_source()
    assert "baseline_sha" in source, (
        f"the {RUNNER_NAME} runner records {ARTIFACT_KEY!r} without mentioning `baseline_sha` — "
        "C-1 §1 defines the digest once, in s2_implement, so prompt and ledger agree"
    )


# --------------------------------------------------------------------------
# PIN 5 — knob-off byte-identity at the composition level (no driver)
# --------------------------------------------------------------------------


def _compose(spec_dir: Path, cfg: Mapping, report: Mapping) -> str:
    """The runner's prompt assembly at HEAD, reproduced from the pieces: the
    payload, then the findings on a disk reject. No driver, no green_loop."""
    payload, _report = s2_implement.build_payload(spec_dir, cfg)
    return payload + "\n" + s2_implement.findings_section(report)


def test_pin5_knob_off_prompt_carries_none_of_the_c1_bytes(
    spec_copy: Path, base_cfg: dict, reject_report: dict
) -> None:
    """The reject lap with the knob off is byte-identical to today's, which
    means: not one byte of the baseline section anywhere in it."""
    prompt = _compose(spec_copy, _cfg(base_cfg), reject_report)

    assert s2_implement.FINDINGS_HEADER in prompt, "fixture wall: the findings feed did not ride"
    assert SECTION_HEADING not in prompt, (
        "the knob-off reject prompt contains the C-1 heading — 'Knob off, no reject, or no "
        "game.py ⇒ prompt byte-identical to today' (C-1 §2)"
    )
    assert "YOUR BASELINE" not in prompt
    assert _words(SECTION_TEXT) not in _words(prompt)
    assert prompt.endswith("\n"), (
        "fixture wall: findings_section ends in a newline so payload.md stays "
        "newline-terminated (see ambiguity f)"
    )


def test_pin5_the_knob_does_not_reach_build_payload_or_findings_section(
    spec_copy: Path, base_cfg: dict, reject_report: dict
) -> None:
    """The section rides in at the SPLICE, never woven into the composers: with
    the knob on, both pure functions return the same bytes they did with it off.
    That is what makes `payload.md` an honest record either way."""
    off, on = _cfg(base_cfg, False), _cfg(base_cfg, True)
    payload_off, _ = s2_implement.build_payload(spec_copy, off)
    payload_on, _ = s2_implement.build_payload(spec_copy, on)

    assert payload_on == payload_off, (
        "build_payload's bytes changed when `implementer.patch_baseline` flipped; C-1 §2 puts "
        "the section in the runner's splice, after the findings, not inside the payload"
    )
    assert SECTION_HEADING not in payload_off
    assert s2_implement.findings_section(reject_report) == s2_implement.findings_section(
        reject_report
    )
    again, _ = s2_implement.build_payload(spec_copy, off)
    assert again == payload_off, "fixture wall: build_payload is deterministic"


def test_pin5_knob_on_prompt_is_the_knob_off_bytes_plus_the_section(
    spec_copy: Path, base_cfg: dict, reject_report: dict
) -> None:
    """The splice proof, byte level: knob-on == knob-off + "\\n" + section, and
    nothing else moves."""
    off = _compose(spec_copy, _cfg(base_cfg), reject_report)
    on = off + "\n" + _section()

    assert on.startswith(off), "the baseline section is APPENDED; it rewrites nothing before it"
    assert on[len(off):] == "\n" + _section()
    assert on.index(SECTION_HEADING) > on.index(s2_implement.FINDINGS_HEADER), (
        "the baseline section must sit after the findings (C-1 §2)"
    )
    assert len(on) - len(off) == len(_section()) + 1


def test_pin5_no_reject_lap_is_untouched(spec_copy: Path, base_cfg: dict) -> None:
    """'no reject ⇒ prompt byte-identical to today': the payload on its own
    carries neither feed, knob on or off."""
    for cfg in (_cfg(base_cfg), _cfg(base_cfg, True), _cfg(base_cfg, False)):
        payload, _ = s2_implement.build_payload(spec_copy, cfg)
        assert s2_implement.FINDINGS_HEADER not in payload
        assert SECTION_HEADING not in payload


def test_pin5_no_game_py_means_no_baseline_to_point_at(spec_copy: Path, base_cfg: dict) -> None:
    """'or no game.py ⇒ prompt byte-identical to today' — the gate the runner
    uses, exercised through the helper the runner computes it from."""
    worker = spec_copy / "worker"
    assert _baseline_sha(worker) is not None, "fixture wall: the shipped worker has a game.py"

    (worker / "game.py").unlink()
    assert _baseline_sha(worker) is None, (
        "with no game.py there is no baseline: C-1 §2 leaves the prompt exactly as it was, and "
        "the sha is what the runner tests before it appends"
    )
