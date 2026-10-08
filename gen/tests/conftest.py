"""Suite-wide setup for a PUBLIC CLONE (contract OS-2 FRONT C.3).

The suite was written beside things a public clone of this repo does not have:

1. the duckWM sibling checkout (`../duckWM`) — the historical batch configs
   name its canon (`duckwm_docs`) and its official-games corpus
   (`duckwm_games`), and a few pins read duckWM-only documents;
2. the maintainers' private evidence — `out/` (gitignored: run ledgers,
   worker repos, the specs and reports of shipped runs) and `audit/` (the
   comparative-audit data, not published).

IN THE MAINTAINERS' CHECKOUT — duckWM beside the repo — THIS FILE DOES NOTHING.
Every fixture wall stays a wall: a vanished piece of evidence still fails
loudly there, exactly as before.

On a public clone (no `../duckWM`) it does three things and no more:

a. arms `gen.config`'s clone fallback (`ARC_GAMES_CANON_FALLBACK=1`, inherited
   by every subprocess a test spawns): a config naming the absent duckWM canon
   reads the vendored `canon/` snapshot — the P-2 clone simulation, applied to
   the whole suite — and the absent officials corpus is dropped from it;
b. makes `gen.officials.discover_officials` answer `[]` for a config whose
   corpus was dropped, so an officials-parametrized test collects as pytest's
   honest "got empty parameter set" skip instead of erroring the module;
c. skips the tests listed in `PRIVATE_EVIDENCE` below — each one measures
   evidence the public tree does not carry — and ONLY while that evidence is
   absent, with the missing path in the skip reason.

Nothing here edits a test, loosens an assertion or touches the pipeline's
defaults; it decides, per test, whether the thing being measured exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DUCKWM_SIBLING = REPO_ROOT.parent / "duckWM"

#: True on a clone with no duckWM sibling — the only case this file acts in.
PUBLIC_CLONE = not DUCKWM_SIBLING.is_dir()

if PUBLIC_CLONE:
    from gen import config as _gen_config
    from gen import officials as _officials

    os.environ[_gen_config.CANON_FALLBACK_ENV] = "1"

    _discover_officials = _officials.discover_officials

    def _discover_or_nothing(cfg):
        """`[]` when the clone fallback dropped the corpus; the real call otherwise."""
        if "duckwm_games" not in cfg:
            return []
        return _discover_officials(cfg)

    _officials.discover_officials = _discover_or_nothing


@dataclass(frozen=True)
class Evidence:
    """Tests that measure `paths` (repo-relative); skipped on a clone without them.

    `tests` are node ids under `gen/tests/`: `file.py::test_name` names one test
    (every parametrization of it); a trailing `*` makes the entry a prefix.
    """

    what: str
    paths: tuple[str, ...]
    tests: tuple[str, ...]


# The shipped runs the corpus-wide pins sweep — named slots, not `out/corpus`
# itself, so a clone that has run batches of its own still skips these: its
# corpus is not the one they measure.
_SHIPPED_CORPUS = (
    "out/corpus/b002-triple/pump-phase-time-echo",
    "out/corpus/b002-triple/core-ward-phase-gates",
    "out/corpus/b002-triple/convoy-in-the-fog",
    "out/corpus/b003r2-simplicity/conduit-watch",
    "out/corpus/b003r2-simplicity/mosaic-marble-bounce-to-match",
    "out/corpus/g20261001-1/seamlock",
    "out/corpus/g20261001-1/key-strip-rover",
)

#: The private evidence, one entry per thing a public clone lacks — measured:
#: the exact set a duckWM-less mirror of this repo failed on (contract OS-2).
PRIVATE_EVIDENCE: tuple[Evidence, ...] = (
    Evidence(
        "the maintainers' shipped run corpus (out/ is gitignored)",
        _SHIPPED_CORPUS,
        (
            "test_b003_visual_card.py::test_the_shipped_corpus_offers_enough_games_to_measure",
            "test_e1_levers.py::test_every_shipped_spec_still_declares_what_it_declared",
            "test_e1_levers.py::test_every_shipped_verifier_report_still_validates",
            "test_e1_levers.py::test_the_shipped_reports_really_do_carry_historic_lever_names",
            "test_q1_terms.py::test_pin11_every_shipped_verifier_report_still_validates",
            "test_v2_levers.py::test_k2_*",
            "test_v2_levers.py::test_k4_*",
            "test_w2_mixprose.py::test_pin5_the_shipped_corpus_is_the_seven_games_the_contract_counts",
            "test_w3_witness.py::test_pin1e_every_shipped_report_still_validates",
            "test_w3_witness.py::test_pin2e_a_pre_b3_history_still_reads",
        ),
    ),
    Evidence(
        "the shipped b003r2 slots (C-4b's birth-check matrix)",
        ("out/corpus/b003r2-simplicity/conduit-watch",
         "out/corpus/b003r2-simplicity/mosaic-marble-bounce-to-match"),
        ("test_b003_levelcount.py::test_pin1_*", "test_b003_levelcount.py::test_pin4_*"),
    ),
    Evidence(
        "the shipped b002 game pump-phase-time-echo (spec + verifier report)",
        ("out/corpus/b002-triple/pump-phase-time-echo",),
        (
            "test_b003_confirm.py::test_pin3_*",
            "test_b003_visual.py::test_a_declared_tell_alone_pulls_section_three_back_in",
            "test_b003_visual.py::test_a_hazardless_spec_*",
            "test_b003_visual.py::test_each_knob_echo_is_filled_with_the_specs_declared_value",
            "test_b003_visual.py::test_the_grammar_helper_agrees_with_the_payload",
            "test_b003_visual.py::test_the_hazard_spec_includes_section_three",
            "test_b003_visual.py::test_the_palette_required_rule_reaches_the_built_payload",
            "test_b003_visual.py::test_the_report_names_the_six_included_sections",
            "test_b003_visual.py::test_the_visual_sections_land_in_the_frozen_order",
            "test_b003_visual.py::test_two_builds_of_one_spec_are_byte_identical",
        ),
    ),
    Evidence(
        "the shipped b002 game core-ward-phase-gates (C-1's composition input)",
        ("out/corpus/b002-triple/core-ward-phase-gates",),
        ("test_b003_patchbaseline.py::test_pin3_baseline_sha_on_the_shipped_worker",
         "test_b003_patchbaseline.py::test_pin5_*"),
    ),
    Evidence(
        "the shipped b002 game convoy-in-the-fog (E-1's prompt input)",
        ("out/corpus/b002-triple/convoy-in-the-fog",),
        (
            "test_e1_levers.py::test_a_sentinel_in_the_canon_reaches_all_three_prompts",
            "test_e1_levers.py::test_all_three_prompts_*",
            "test_e1_levers.py::test_the_audit_prompt_*",
            "test_e1_levers.py::test_the_keywordless_lever_is_quoted_and_labelled",
            "test_e1_levers.py::test_the_prompts_are_byte_identical_across_builds",
        ),
    ),
    Evidence(
        "the real audit-round lever histories of two shipped games",
        ("out/corpus/g20261001-1/seamlock/worker.lever-history.json",
         "out/corpus/g20261001-1/key-strip-rover/worker.lever-history.json"),
        ("test_e1_levers.py::test_the_real_lever_histories_refold",),
    ),
    Evidence(
        "the shipped lantern slot's real seeds",
        ("out/corpus/g20261001-5/lantern-path-parity-trace",),
        ("test_e0_seeds.py::test_the_sidecar_reproduces_the_lantern_slots_real_five_seeds",),
    ),
    Evidence(
        "a shipped b003 idea with a secondary objective",
        ("out/corpus/b003-simplicity/facing-sentinel-match-the-signal-row",),
        ("test_w2_mixprose.py::test_pin4_the_dedupe_key_still_ignores_the_secondary",
         "test_w2_mixprose.py::test_pin4_the_secondary_reaches_the_idea_json"),
    ),
    Evidence(
        "the recorded ideas of past batches and the J-3 audit draws",
        ("out/ideas/b002-triple", "out/ideas/b003-simplicity", "out/audit/j3"),
        ("test_w2_mixprose.py::test_pin5_a_new_reason_survives_the_retry_line",
         "test_w2_mixprose.py::test_pin5_the_official_shaped_ideas_still_pass",
         "test_w2_mixprose.py::test_pin5_the_recorded_exhibits_are_rejected"),
    ),
    Evidence(
        "the comparative-audit data and scripts (audit/ is not published)",
        ("audit/comparative",),
        (
            "test_t1_density.py::test_a1_*", "test_t1_density.py::test_a2_*",
            "test_t1_density.py::test_a3_*", "test_t1_density.py::test_a5_*",
            "test_t1_density.py::test_b1_*", "test_t1_density.py::test_b2_*",
            "test_t1_density.py::test_c1_*", "test_t1_density.py::test_d3_*",
            "test_t1_density.py::test_e8_*",
            "test_v2_density.py::test_b1_*", "test_v2_density.py::test_b2_*",
            "test_v2_density.py::test_b4_*",
            "test_v2_instruments.py::test_n2_*",
            "test_w3_caps.py::test_g1_*",
            "test_w2_mixprose.py::test_pin5_the_official_shaped_corpus_is_the_one_j3_graded",
            "test_w2_mixprose.py::test_r10_change5_m3_drawspace_takes_a_config_override",
        ),
    ),
    Evidence(
        "duckWM-only documents (the tier table, the upstream visual prompt, the agent dialect)",
        ("../duckWM",),
        (
            "test_b003_tiers_s0.py::test_canon_*",
            "test_b003_visual.py::test_the_vendored_prompt_still_says_what_the_distillation_assumed",
            "test_b9_battery.py::test_csv_first_three_columns_are_the_house_dialect",
        ),
    ),
    Evidence(
        "the official-games corpus (arcprize's games, never redistributed here)",
        ("../duckWM/games/official",),
        (
            "test_b7_verify.py::test_cli_dry_run_on_one_official",
            "test_b8_baselines.py::test_the_corpus_minimum_baseline_is_the_configured_floor",
            "test_b11_pipeline.py::test_an_official_is_never_gated_into_the_sister_repo",
            "test_b11_pipeline.py::test_every_pinned_official_exception_replays_raw",
            "test_b11_pipeline.py::test_pinned_official_exceptions_are_named_officials_and_policies",
        ),
    ),
)


def _missing(evidence: Evidence) -> list[str]:
    return [rel for rel in evidence.paths if not (REPO_ROOT / rel).exists()]


def _matches(nodeid: str, entry: str) -> bool:
    if entry.endswith("*"):
        return nodeid.startswith(entry[:-1])
    return nodeid == entry or nodeid.startswith(entry + "[")


def pytest_collection_modifyitems(config, items):
    if not PUBLIC_CLONE:
        return
    for evidence in PRIVATE_EVIDENCE:
        missing = _missing(evidence)
        if not missing:
            continue
        reason = (
            f"public clone: needs {evidence.what}, which this tree does not carry "
            f"(missing: {', '.join(missing)})"
        )
        for item in items:
            nodeid = item.nodeid.removeprefix("gen/tests/")
            if any(_matches(nodeid, entry) for entry in evidence.tests):
                item.add_marker(pytest.mark.skip(reason=reason))
