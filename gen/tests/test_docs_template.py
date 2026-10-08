"""Blind pins for contract D-1 — researcher runbook, format doc, config template.

Run: .venv/bin/python -m pytest gen/tests/test_docs_template.py -v

Written from the frozen D-1 contract ALONE (blind test writer).  The three
deliverables this file pins — `docs/RUNBOOK.md`, `docs/OUTPUT-FORMAT.md`,
`config/template.yaml` — were NOT read while writing it; none of the three
existed in the working tree at that moment, and `config/b003r2-simplicity.yaml`
(the template's stated source) was deliberately left unread too, so that no pin
here mirrors the implementer's file back at itself.

What this file was allowed to know, and does: the *readers* the contract names,
read from the shipped pipeline (`gen/config.py`, `gen/s0_ideas.py`,
`gen/tiers.py`, `gen/s1_spec.py`, `gen/s2_implement.py`, `gen/s3_verify.py`,
`gen/s3_visual.py`, `gen/s5_battery.py`, `gen/orchestrator.py`) for their real
names and call shapes, plus HEAD's `README.md` for the stale markers pin 4
requires.  The template's KEY SET is contract-frozen, not read: b003r2's keys,
PLUS `verifier.confirm_pass: true`, MINUS `lint.strict` and `battery.smoke`.
That is why pin 2 asserts exactly those three facts and nothing about the rest
of the key set — a fuller key pin could only have been written by peeking.

EXPECTED FAILURES BEFORE THE SIBLING CONTRACTS LAND (the contract's own NOTE)

Pin 1 calls every config reader the contract lists, including
`s5_battery._battery_config`, which TODAY hard-requires `battery.smoke`
(`config battery block missing ['smoke']`) and `gen/s1_spec.py`'s sibling
`_lint_strict`, which hard-requires `lint.strict`.  Contract D-3 removes those
requirements; contract D-1 writes the template WITHOUT those keys.  So a red
`test_pin1_every_reader_accepts_the_template[s5_battery._battery_config]` while
D-3 is outstanding is the contract working as written, not a defect in the
template.  `_lint_strict` is deliberately NOT in the reader table: the contract
names `_lint_require_render` only.  Pins 3 and 4 fail until D-1's own files
land.  The aggregate reader test reports EVERY failing reader in one message so
the lead can sequence the close from one run.

THE FOUR PINS, in the contract's order

1. `config/template.yaml` loads via `gen.config.load_config` and every reader
   the contract names accepts it without raising.
2. The template carries `verifier.confirm_pass: true`, and carries NO
   `lint.strict` and NO `battery.smoke` (yaml-level, so a commented-out key
   cannot trip it).
3. `docs/RUNBOOK.md` and `docs/OUTPUT-FORMAT.md` exist, are non-trivial
   (>2k chars each), and name the real entrypoints — the six contract anchors,
   each asserted in the file the contract assigns it to.
4. `README.md` no longer claims the B0-era state: three stale markers taken
   verbatim from HEAD's README are pinned ABSENT.

HYGIENE: tmp_path only.  Nothing here writes into the repo; pin 1 loads the
template from a per-test `tmp_path` COPY so no stage reader could ever write
next to the real config, and every other pin is a read.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from gen import (
    config as gen_config,
)
from gen import (
    orchestrator,
    s0_ideas,
    s1_spec,
    s2_implement,
    s3_verify,
    s3_visual,
    s5_battery,
    tiers,
)

REPO_ROOT = Path(gen_config.REPO_ROOT)

TEMPLATE_PATH = REPO_ROOT / "config" / "template.yaml"
RUNBOOK_PATH = REPO_ROOT / "docs" / "RUNBOOK.md"
FORMAT_PATH = REPO_ROOT / "docs" / "OUTPUT-FORMAT.md"
README_PATH = REPO_ROOT / "README.md"

# Contract: "non-trivial (>2k chars each)".
MIN_DOC_CHARS = 2_000

# Contract pin 3's source-text anchors, split by the file that owns them.
# RUNBOOK.md is the operator phase (the orchestrator CLI); OUTPUT-FORMAT.md is
# the consumer phase (the package tree and the duck-intake mirror).  Presence in
# the right file is what is pinned — an anchor may legitimately also appear in
# the other doc.
RUNBOOK_ANCHORS = ("gen.orchestrator", "--review", "--status")
FORMAT_ANCHORS = ("duck-intake", "level-set.tsv", "unprocessed_game.tsv")

# Contract pin 4: stale markers copied verbatim from HEAD's README.md, each one
# a claim about the B0-era state that a researcher-facing README cannot carry.
#   1. the smoke-record heading — the "smoke-instructions marker" the contract
#      names;
#   2. the smoke command's own lead-in line;
#   3. the B0-era next-step claim.
README_STALE_MARKERS = (
    "### Backend smoke record (B0 acceptance)",
    "Smoke command (the acceptance check, re-runnable any time)",
    "Next: plan B1.",
)


# --- helpers ------------------------------------------------------------------


def _read_text(path: Path, label: str) -> str:
    """Read a deliverable, failing with the path when it is not there yet."""
    if not path.is_file():
        pytest.fail(f"{label} missing: {path} (contract D-1 creates it)")
    return path.read_text(encoding="utf-8")


def _template_copy(tmp_path: Path) -> Path:
    """The template, copied into tmp_path — the only file any reader is handed.

    `load_config` resolves `duckwm_docs` against THIS repo's root, never against
    the config's own location (gen/config.py's one rule), so a tmp copy loads
    exactly like the real file while keeping every reader's hands out of
    `config/`.
    """
    if not TEMPLATE_PATH.is_file():
        pytest.fail(f"config/template.yaml missing: {TEMPLATE_PATH} (contract D-1 creates it)")
    dest = tmp_path / "template.yaml"
    shutil.copyfile(TEMPLATE_PATH, dest)
    return dest


@pytest.fixture
def template_cfg(tmp_path: Path) -> dict:
    """`load_config(<tmp copy of config/template.yaml>)` — pin 1's first half."""
    return gen_config.load_config(_template_copy(tmp_path))


def _readers() -> dict[str, object]:
    """Every config reader contract pin 1 names, keyed by its dotted name.

    `s0_ideas.check_config` takes the vocab as its second argument, so the entry
    loads it (`+load_vocab`, as the contract writes it); every other reader is a
    one-argument `cfg` read.  `s5_battery._battery_config` is that stage's
    config parser — the block-level `{model, passes, token_cap, smoke}` check.
    The orchestrator's importable validators are its batch/orchestrator block
    readers plus the optional respec cap; nothing here starts a run.
    """
    return {
        "s0_ideas.load_vocab": s0_ideas.load_vocab,
        "s0_ideas.check_config": lambda cfg: s0_ideas.check_config(cfg, s0_ideas.load_vocab(cfg)),
        "tiers.tier_policy": tiers.tier_policy,
        "s1_spec._lint_require_render": s1_spec._lint_require_render,
        "s2_implement.patch_baseline_enabled": s2_implement.patch_baseline_enabled,
        "s3_verify._lever_corroboration": s3_verify._lever_corroboration,
        "s3_verify._lever_window": s3_verify._lever_window,
        "s3_verify._term_corroboration": s3_verify._term_corroboration,
        "s3_verify._term_window": s3_verify._term_window,
        "s3_verify._confirm_pass": s3_verify._confirm_pass,
        "s3_verify._exempt_terms": s3_verify._exempt_terms,
        "s3_visual.visual_card_mode": s3_visual.visual_card_mode,
        "s3_visual.l1_floor_mode": s3_visual.l1_floor_mode,
        "s5_battery._battery_config": s5_battery._battery_config,
        "orchestrator.batch_config": orchestrator.batch_config,
        "orchestrator.orchestrator_config": orchestrator.orchestrator_config,
        "orchestrator._respec_cap": orchestrator._respec_cap,
    }


READER_NAMES = tuple(sorted(_readers()))


def _mappings(node: object):
    """Every mapping in a parsed yaml tree, the root included."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _mappings(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _mappings(value)


def _subkey_sightings(tree: object, block: str, key: str) -> list[str]:
    """Where `<block>.<key>` is written anywhere in the tree, as dotted paths."""
    sightings = []
    for mapping in _mappings(tree):
        inner = mapping.get(block)
        if isinstance(inner, dict) and key in inner:
            sightings.append(f"{block}.{key} = {inner[key]!r}")
    return sightings


# --- pin 1: the template loads, and every reader accepts it -------------------


def test_pin1_template_loads_through_load_config(template_cfg: dict) -> None:
    """`gen.config.load_config` accepts the template and resolves the canon."""
    assert isinstance(template_cfg, dict) and template_cfg, "template parsed to an empty config"
    docs = Path(template_cfg["duckwm_docs"])
    assert docs.is_absolute(), f"load_config left duckwm_docs unresolved: {docs}"
    assert docs.is_dir(), f"template duckwm_docs does not resolve to a directory: {docs}"


@pytest.mark.parametrize("reader_name", READER_NAMES)
def test_pin1_every_reader_accepts_the_template(reader_name: str, template_cfg: dict) -> None:
    """Each reader the contract names is CALLED on the template and must not raise.

    One test per reader so a single stale requirement (see this module's
    EXPECTED FAILURES note on `battery.smoke`) names itself in the report
    instead of hiding behind the first failure.
    """
    reader = _readers()[reader_name]
    try:
        reader(template_cfg)
    except Exception as exc:  # noqa: BLE001 — the pin IS "nothing raises"
        pytest.fail(f"{reader_name}(template.yaml) raised {type(exc).__name__}: {exc}")


def test_pin1_reader_sweep_reports_every_failure_at_once(template_cfg: dict) -> None:
    """The whole reader table in one pass — the close-sequencing view.

    Redundant with the parametrized test by design: this one's failure message
    lists EVERY reader the template currently trips, which is what the lead
    needs to decide whether the remainder is D-3's to clear.
    """
    failures = []
    for name, reader in sorted(_readers().items()):
        try:
            reader(template_cfg)
        except Exception as exc:  # noqa: BLE001 — collected, not swallowed
            failures.append(f"  {name}: {type(exc).__name__}: {exc}")
    assert not failures, (
        f"{len(failures)}/{len(READER_NAMES)} config readers rejected config/template.yaml:\n"
        + "\n".join(failures)
    )


# --- pin 2: confirm_pass on, the two removed keys absent ----------------------


def test_pin2_template_carries_confirm_pass_true() -> None:
    """`verifier.confirm_pass: true` — a real yaml bool, not a truthy string."""
    tree = yaml.safe_load(_read_text(TEMPLATE_PATH, "config/template.yaml"))
    assert isinstance(tree, dict), f"template did not parse to a mapping: {type(tree).__name__}"
    verifier = tree.get("verifier")
    assert isinstance(verifier, dict), f"template has no `verifier:` block, got {verifier!r}"
    assert "confirm_pass" in verifier, "template missing verifier.confirm_pass (contract: true)"
    assert verifier["confirm_pass"] is True, (
        f"verifier.confirm_pass must be the yaml bool true, got {verifier['confirm_pass']!r}"
    )


def test_pin2_template_carries_no_lint_strict_and_no_battery_smoke() -> None:
    """The two keys contract D-3 removes are absent from the template's yaml.

    Asserted on the PARSED tree, at any depth, so a key left behind as a comment
    is correctly not a violation and a key nested in an unexpected block still
    is.
    """
    tree = yaml.safe_load(_read_text(TEMPLATE_PATH, "config/template.yaml"))
    assert isinstance(tree, dict), f"template did not parse to a mapping: {type(tree).__name__}"
    sightings = _subkey_sightings(tree, "lint", "strict") + _subkey_sightings(
        tree, "battery", "smoke"
    )
    assert not sightings, (
        "config/template.yaml must carry neither lint.strict nor battery.smoke "
        f"(contract D-3 removes them), found: {sightings}"
    )


# --- pin 3: the two docs exist, are non-trivial, and name the entrypoints -----


@pytest.mark.parametrize(
    ("path", "label"),
    [(RUNBOOK_PATH, "docs/RUNBOOK.md"), (FORMAT_PATH, "docs/OUTPUT-FORMAT.md")],
    ids=["RUNBOOK", "OUTPUT-FORMAT"],
)
def test_pin3_doc_exists_and_is_non_trivial(path: Path, label: str) -> None:
    text = _read_text(path, label)
    assert len(text) > MIN_DOC_CHARS, (
        f"{label} is {len(text)} chars; the contract pins >{MIN_DOC_CHARS}"
    )


@pytest.mark.parametrize("anchor", RUNBOOK_ANCHORS)
def test_pin3_runbook_names_the_operator_entrypoints(anchor: str) -> None:
    """The orchestrator CLI anchors belong to the operator doc."""
    text = _read_text(RUNBOOK_PATH, "docs/RUNBOOK.md")
    assert anchor in text, f"docs/RUNBOOK.md never names {anchor!r}"


@pytest.mark.parametrize("anchor", FORMAT_ANCHORS)
def test_pin3_output_format_names_the_package_anchors(anchor: str) -> None:
    """The package-tree / duck-intake anchors belong to the consumer doc."""
    text = _read_text(FORMAT_PATH, "docs/OUTPUT-FORMAT.md")
    assert anchor in text, f"docs/OUTPUT-FORMAT.md never names {anchor!r}"


# --- pin 4: the README no longer claims the B0-era state ----------------------


@pytest.mark.parametrize("marker", README_STALE_MARKERS)
def test_pin4_readme_dropped_the_b0_era_markers(marker: str) -> None:
    """Each stale marker, verbatim from HEAD's README, is gone."""
    text = _read_text(README_PATH, "README.md")
    assert marker not in text, (
        f"README.md still carries the B0-era marker {marker!r} — contract D-1 replaces "
        f"the stale B0-era content"
    )
