"""S3 — the merged gate (architecture §3 "S3 — the merged gate"; B11, agent A).

Nothing broken, degenerate, or off-intent survives to baselines/review.
In→Out (architecture §3): `worker/` + the upstream reports →
`acceptance-report.json` + `robustness-report.json` (the §2 corpus-tree
names) + the `gated` verdict. Executor: pure code, plus the S2b and S3d
verdicts it CONSUMES — this stage never re-decides them.

Four layers, short-circuiting in canon order (architecture §3):

1. **Structural acceptance** — our calibrated floors (`sprites>0, levels
   6-10, non-monotonic staircase, random-fails-L1, loc floor`), milliseconds,
   first. Layer 1 therefore does NO engine work: it reads the game source and
   the S4 metadata, nothing else.
2. **Robustness** — the seven degenerate policies, "all seven must fail every
   level".
3. **Verifier verdict** — S2b's report must be clean.
4. **Battery** — S3d's report must be complete (it exists only after S4
   supplies baselines).

The floors are ADAPTED, never imported (the B10 pattern)
-------------------------------------------------------
`GEN/tools/acceptance.py` is a READ-ONLY reference that runs in the sibling
repo against the officials corpus; its thresholds are the calibrated numbers
and they are reproduced in `FLOORS` below, each with the measurement that
produced it (`acceptance.py:44-84` THRESHOLDS + `GEN/design/calibration.md`
§A-C). Two deliberate divergences from the reference, both documented on the
check that makes them:

* the reference's WARN/FAIL/SKIP vocabulary becomes the B7 status vocabulary
  (`gen/s3_static.STATUSES`), which has no "warn". A reference WARN that the
  data does not justify turning into a rejection is reported `deferred` — an
  honest non-answer that never rejects (`gen/s3_verify.decide_verdict`), with
  the number in the note — never a silent `pass`.
* the staircase predicate is `s4_baselines.has_strict_descent` (the B11
  contract names it), which is STRICTER than the reference's
  "strictly increasing" test: it also rejects a flat curve. calibration §C:
  "Both halves matter: a flat curve and a staircase are each wrong", and
  0/25 official vectors are nondecreasing (`has_strict_descent` docstring,
  lead-verified over all 25 `metadata.json`).

The seven policies are CLEAN-ROOM (D14)
---------------------------------------
`GEN/design/decisions.md` D14: their bundle is "read-only reference
material", "no relicensing grant", "Execution of their code is NOT yet
blessed". Architecture §8 lists the robustness suite as a "clean-room
reimplementation (D14)".

The ONLY specification used here is (a) the documented list in
`GEN/provenance/reviews/re-arc-3-source.md:51-54` — `noop_like, repeat_first,
repeat_configured_single, repeat_up_or_first, cycle_moves, cycle_all,
seeded_random; 120 steps each` — "all must fail to win", and (b) the frozen
per-policy semantics in the B11 build contract, reproduced verbatim on each
policy builder below. Their `baseline_robustness.py` was never opened; no
file under `GEN/third-party/re-arc-3/` was read while writing this module.
Architecture §3 STRENGTHENS the pass condition: all seven must fail EVERY
level, not merely fail to win.

Calibration (B11, 2026-09-22, both layers over the 25 signed officials)
----------------------------------------------------------------------
Structural floors: 25/25 verdict `pass`, zero `fail` rows — they were
calibrated on this population and they still fit it. Robustness: 174 of the
175 policy runs (7 x 25) complete ZERO levels; the ONE exception is lp85
under `repeat_configured_single`, adjudicated at source and pinned in
`KNOWN_OFFICIAL_FAILS` below — the check still FAILS lp85, the pin only
records that the exception is known. Re-run with `python -m gen.s3_gate
--officials`: exit 0 means every pin reproduced and nothing else failed.
Cost measured on that run: layer 1 is 29-281 ms per game (ka59, 41k lines,
is the ceiling), layer 2 is ~0.33 s per game for 7 x 120 steps.

Determinism
-----------
Nothing written here is time-stamped or path-random; every policy runs on a
FRESH instance (`frames._fresh_game`), the seeded policy's rng is
`random.Random(seed_base + policy_index)`, and the declared action list is
read off the RESET frame (`base_game.py:259`, via
`frames._playable_action_ids`). Two runs of the same worker at the same
`seed_base` give byte-identical reports; anything that still differs is the
GAME's own rng, which `gen/frames.py` documents as the game's property.

Two checks that are NOT layers (contract B3)
--------------------------------------------
`gate.term-witness` (R-18) and `gate.refusal-persistence` (R-08) live in this
module and run outside the four layers: neither is a rule the 25 signed
officials are held to, so neither may sit in `structural_acceptance`'s row
list, and neither decides anything until a batch arms its knob. `gate_checks`
is their single entry point and the orchestrator's unified fail loop is the
seam that calls it — see the section that defines them for why the knobs live
under `verifier:` rather than under `gate:`.

CLI:
  python -m gen.s3_gate --worker gen/tests/fixtures/s6_seeded
  python -m gen.s3_gate --worker DIR --layer robustness
  python -m gen.s3_gate --officials           # the 25-official calibration
Exit 0 = gated / layer pass, 2 = rejected / layer fail, 3 = pending.
"""

from __future__ import annotations

import argparse
import ast
import importlib.metadata
import json
import platform
import random
from collections.abc import Collection, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

import yaml
from arcengine import ActionInput, GameAction, GameState

from .config import REPO_ROOT, load_config
from .frames import (
    CENTRE_CLICK,
    GRID_SIZE,
    TERMINAL_STATES,
    FrameCapture,
    _action_by_id,
    _fresh_game,
    _perform,
    _playable_action_ids,
    _reset,
    capture,
    click_cells,
    describe_action,
    mouse,
    read_trace,
    resolve_trace_frames,
    settled_grid,
    trace_path,
)
from .s3_static import (
    CheckResult,
    Evidence,
    _derived_classes,
    _result,
    _sprite_calls,
    game_source_path,
    load_worker_classes,
    refusal_palette_indices,
)
from .s4_baselines import METADATA_NAME as S4_METADATA_NAME
from .s4_baselines import OUT_SUFFIX as S4_OUT_SUFFIX
from .s4_baselines import has_strict_descent

SCHEMA_VERSION = "b11.1"
DEFAULT_CONFIG = "config/b001-pilot.yaml"
STAGE = "s3-gate"

# --- the seven degenerate policies (D14 clean-room; the documented list) ----
# `GEN/provenance/reviews/re-arc-3-source.md:51`, in the order it lists them.
POLICIES = (
    "noop_like",
    "repeat_first",
    "repeat_configured_single",
    "repeat_up_or_first",
    "cycle_moves",
    "cycle_all",
    "seeded_random",
)
# "120 steps each" — the documented budget, same source line.
ROBUSTNESS_STEPS = 120

# --- report names (architecture §2, the per-game artifact tree) -------------
ACCEPTANCE_NAME = "acceptance-report.json"   # "S3: structural gate numbers vs official floors"
ROBUSTNESS_NAME = "robustness-report.json"   # "S3: 7 degenerate policies x per-level outcomes"

# Output dir = the worker SIBLING `<worker>.gate/` (the B3/B7/B8/B9/B10 rule:
# never inside the worker — a file there trips the worker's own scope check).
GATE_SUFFIX = ".gate"

# --- vocabulary -------------------------------------------------------------
LEG = "gate"                                  # every check row's `leg`
LAYERS = ("structural", "robustness", "verifier", "battery")
LAYER_PASS, LAYER_FAIL, LAYER_PENDING, LAYER_SKIPPED = "pass", "fail", "pending", "skipped"
VERDICT_GATED, VERDICT_REJECTED, VERDICT_PENDING = "gated", "rejected", "pending"
PASS, FAIL = "pass", "fail"
# The mode in which a knobbed check does nothing at all — reads no file, writes
# no row (`gen/s3_visual.MODE_OFF`, the same word for the same thing).
MODE_OFF = "off"

# The two upstream verdicts this stage consumes, with the vocabularies they
# come from. Named here rather than imported: `gen/s3_verify` and
# `gen/s5_battery` both pull `gen/backends` (the agent drivers), and the gate
# must stay import-light for the orchestrator. `s3_verify.VERDICTS =
# ("pass", "reject")`; `s5_battery` names its four in `STATUS_COMPLETE,
# STATUS_TOKEN_CAP, STATUS_PROTOCOL, STATUS_CRASH`.
VERIFIER_VERDICT_PASS = "pass"
VERIFIER_VERDICTS = ("pass", "reject")
BATTERY_STATUS_COMPLETE = "complete"
BATTERY_STATUSES = ("complete", "token-cap", "protocol-failure", "crash")

# Engine ids. ACTION6 is the click action; `GameAction(6)` raises, so ids
# resolve by NAME through `frames._action_by_id` (frames.py §Traps).
CLICK_ACTION_ID = GameAction.ACTION6.value
MOVE_ACTION_IDS = (1, 2, 3, 4)               # ACTION1-4, the move quartet
UP_ACTION_ID = 1                             # ACTION1 = "up" in the corpus idiom

# How many described actions each policy row keeps. The full 120 x 7 line is
# reproducible from the plan + seed and would triple the report for nothing.
ACTION_SAMPLE = 8

# --- the calibrated floors (ADAPTED from GEN/tools/acceptance.py) -----------
# One block, as the reference keeps them: "Every threshold in THRESHOLDS is
# derived from the official 25 and carries its provenance. They are
# deliberately in one block: when the manual-play corpus is complete these
# numbers move, and that should be a one-place edit." (acceptance.py:13-15).
FLOORS: dict[str, dict] = {
    "sprite_calls_fail_at": {
        "value": 0,
        "reference": "GEN/tools/acceptance.py:55 THRESHOLDS['sprite_calls_fail_at']",
        "citation": (
            "official min 1, median 43; no game has zero — bp35 and lf52 build their "
            "sprites procedurally, which is what puts the hard line at 0 rather than "
            "higher (calibration.md §A)"
        ),
    },
    "levels_min": {
        "value": 3,
        "reference": "GEN/tools/acceptance.py:70 THRESHOLDS['levels_min']",
        "citation": (
            "official range 6-10; below 3 there is no progression to measure and the "
            "game vacuously clears every baseline-curve check (calibration.md §A)"
        ),
    },
    "levels_max": {
        "value": 12,
        "reference": "GEN/tools/acceptance.py:71 THRESHOLDS['levels_max']",
        "citation": "official max 10; the reference WARNs above 12, never FAILs",
    },
    "levels_spec_band": {
        "value": [6, 10],
        "reference": "GEN/design/calibration.md §A + spec-v0.3.md §7",
        "citation": (
            "levels per game 6-10, median 7 over the complete population (n=25); "
            "architecture §3 names 'levels 6-10' as the structural floor, so a game "
            "built under the §7 contract is held to the band itself"
        ),
    },
    "baseline_monotonic_fails": {
        "value": True,
        "reference": "GEN/tools/acceptance.py:46 THRESHOLDS['baseline_monotonic_fails']",
        "citation": (
            "0 of 25 official games are strictly monotonic — 'the clearest tell of an "
            "authored curve'; calibration.md §C adds that a FLAT curve is equally "
            "wrong, which is why the predicate here is s4_baselines.has_strict_descent"
        ),
    },
    "random_beats_l1_fails": {
        "value": True,
        "reference": "GEN/tools/acceptance.py:83 THRESHOLDS['random_beats_l1_fails']",
        "citation": (
            "0 of 25 official games fall to a uniform-random policy, measured at 400 "
            "random actions (probe_games.RANDOM_SCREEN_BUDGET); this gate consumes the "
            "120-step seeded_random row, a strictly smaller budget, so the 0/25 "
            "calibration transfers a fortiori (calibration.md §A)"
        ),
    },
    "loc_warn_below": {
        "value": 200,
        "reference": "GEN/tools/acceptance.py:68 THRESHOLDS['loc_warn_below']",
        "citation": (
            "official min 722 non-blank non-comment lines, median 2052; the number is "
            "kept far below the population ON PURPOSE — 'a stub detector, not a "
            "measure'. A floor at 777 warns on an official game and at 500 fires on "
            "64% of the tufa corpus, so the reference never FAILs it and neither does "
            "this gate (calibration.md §A + §E)"
        ),
    },
}

# --- check ids (the acceptance report's rows, in architecture §3 order) -----
CHECK_SPRITES = "gate.sprite-density"
CHECK_LEVELS = "gate.level-count"
CHECK_DESCENT = "gate.baseline-descent"
CHECK_RANDOM = "gate.random-fails-l1"
CHECK_LOC = "gate.source-size"

# The adjudicated corpus exceptions (the `s3_static.KNOWN_OFFICIAL_FAILS`
# pattern, B7). Calibration result over the 25 signed officials (B11,
# 2026-09-22): structural floors 25/25 clean — every verdict `pass`, zero
# `fail` rows — and 174 of the 175 policy runs (7 x 25) complete ZERO levels.
# The ONE exception is pinned below with source evidence. It is NOT a
# suppression: `robustness()` still fails lp85, exactly as it would fail a
# generated game that behaved the same way; the calibration battery asserts
# this set and nothing else, and no threshold or policy was weakened.
KNOWN_OFFICIAL_FAILS: dict[str, dict] = {
    "lp85": {
        "policy": "repeat_configured_single",
        "level": 1,
        "step": 5,
        "bucket": "verified",
        "citation": (
            "calibration.md §A calibrates ONE play floor — `random_beats_L1` 0/25, "
            "measured with a UNIFORM-RANDOM policy (acceptance.py:83 + "
            "probe_games.random_beats_level_one, 400 random actions). Nothing in the "
            "canon measures the officials against a policy that repeats the ENGINE'S "
            "FIRST CLICK CELL, which is what the B11 contract operationalizes "
            "`repeat_configured_single` as for a click-declaring game. lp85's "
            "seeded_random row completes zero levels, so the calibrated floor itself "
            "still holds on all 25."
        ),
        "evidence_note": (
            "lp85 declares ACTION6 ONLY. Level 1 (lp85.py:1092-1124) places exactly two "
            "sys_click buttons: 'ahdesifykt', tagged button_A_L (placed lp85.py:1095, "
            "sprite lp85.py:36-47), and 'zpxgvxwdex', tagged button_A_R (placed "
            "lp85.py:1117, sprite lp85.py:1054-1065). step() (lp85.py:21394-21437) "
            "splits the tag's <row>_<L|R> suffix and shifts that row; the goal test "
            "khartslnwa (lp85.py:21441) is satisfied after FIVE presses of button_A_L. "
            "The engine reports that button as the first clickable cell (screen (4,29)), "
            "so the policy completes level 1 at step 5 — against the corpus's own "
            "baseline of 17 actions for that level (metadata.json baseline_actions[0]). "
            "Verified by replay from a fresh instance: 5 clicks on (4,29) complete level "
            "1; the same 120 clicks on the other cell (56,29) end in GAME_OVER on the "
            "level's StepCounter budget of 13 (lp85.py:1121); 120 clicks on the centre "
            "(32,32) complete nothing. Deterministic — no rng is involved."
        ),
    },
}


def is_pinned_official_fail(slug: str, failure: Mapping) -> bool:
    """Is this policy failure the adjudicated `KNOWN_OFFICIAL_FAILS` entry?

    Exact match on policy, level and step — a pin covers ONE verified defect,
    never a slug wholesale. The calibration battery (`--officials`) and the
    B11 test battery both read the pins through here.
    """
    entry = KNOWN_OFFICIAL_FAILS.get(slug)
    if entry is None:
        return False
    return (
        failure.get("policy") == entry["policy"]
        and failure.get("level") == entry["level"]
        and failure.get("step") == entry["step"]
    )


# --- small helpers ----------------------------------------------------------


def _versions() -> dict:
    return {
        "arcengine": importlib.metadata.version("arcengine"),
        "python": platform.python_version(),
    }


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _check_to_dict(check: CheckResult) -> dict:
    """A CheckResult as the B7 report dict (`s3_verify._check_to_dict`).

    `asdict`, not field-by-field: the CheckResult/Evidence shapes belong to
    `gen/s3_static`, so a drift there surfaces here as a changed key instead
    of a silently dropped field.
    """
    if not isinstance(check, CheckResult):
        raise TypeError(f"expected a CheckResult, got {type(check).__name__}")
    record = asdict(check)
    record["evidence"] = [dict(item) for item in record["evidence"]]
    return record


def _loc(text: str) -> int:
    """Non-blank, non-comment lines — THIS gate's counter (acceptance.py:172).

    calibration §A: two LOC definitions exist and are easily conflated (the
    sibling's counts blank and comment lines too and reports min 778). The
    floor below is quoted against THIS one, whose official minimum is 722.
    """
    return len([line for line in text.splitlines() if line.strip() and not line.strip().startswith("#")])


def _parse_source(worker_dir: Path) -> tuple[Path, str, ast.AST]:
    """(path, text, tree) for the worker's game file — the layer-1 material.

    Deliberately NOT `s3_static._parse_game`: that one also derives pixel
    bindings, int constants and display classes for the B7 checks, which
    costs ~0.7s on the largest official (ka59, 41k lines) and none of it
    feeds a floor. Architecture §3 wants layer 1 in milliseconds.
    """
    path = game_source_path(worker_dir)
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:  # a file that does not parse is a hard stop
        raise ValueError(f"{path}:{exc.lineno or 0}: does not parse: {exc.msg}") from exc
    if not _derived_classes(tree, "ARCBaseGame"):
        raise AssertionError(f"{path}: no ARCBaseGame subclass found in the source")
    return path, text, tree


def _has_layout_contract(tree: ast.AST) -> bool:
    """Does the source define a module-level `build_layout`? (spec §7, D13.)

    A STATIC presence test — it picks which level band the game is held to,
    nothing more. S6 is where `build_layout` is imported and validated for
    purity, seed-sensitivity and solver coverage (`gen/s6_package.py`);
    repeating that here would make layer 1 import the game.
    """
    return any(
        isinstance(node, ast.FunctionDef) and node.name == "build_layout"
        for node in getattr(tree, "body", [])
    )


def _metadata_candidates(worker_dir: Path, metadata_dir: Path | None) -> list[Path]:
    """Where S4's `metadata.json` can be, most specific first.

    An OFFICIAL ships it beside the game file (`gen/officials.py`); a worker's
    is written to the S4 sibling `<worker>.s4/` (`gen/s4_baselines.run_s4`).
    """
    if metadata_dir is not None:
        return [Path(metadata_dir) / S4_METADATA_NAME]
    return [
        worker_dir / S4_METADATA_NAME,
        worker_dir.parent / (worker_dir.name + S4_OUT_SUFFIX) / S4_METADATA_NAME,
    ]


def _load_metadata(worker_dir: Path, metadata_dir: Path | None) -> tuple[Path | None, dict | None]:
    for path in _metadata_candidates(worker_dir, metadata_dir):
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as fh:
            metadata = json.load(fh)
        if not isinstance(metadata, dict):
            raise TypeError(f"{path}: metadata did not parse to a mapping")
        return path, metadata
    return None, None


def _baselines(metadata: Mapping | None, path: Path | None) -> list[int] | None:
    """`baseline_actions` as the officials ship it: a plain list of ints > 0.

    A malformed vector is an ARTIFACT bug, not a game defect, so it raises
    rather than failing the gate.
    """
    if metadata is None:
        return None
    values = metadata.get("baseline_actions")
    if values is None or values == []:
        return None
    if not isinstance(values, Sequence) or isinstance(values, str):
        raise TypeError(f"{path}: baseline_actions must be a list, got {type(values).__name__}")
    out: list[int] = []
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{path}: baseline_actions[{index}] must be an int > 0, got {value!r}")
        out.append(int(value))
    return out


# --- layer 1: structural acceptance -----------------------------------------


def _check_sprites(path: Path, calls: Sequence) -> CheckResult:
    floor = FLOORS["sprite_calls_fail_at"]
    lines = sorted({int(getattr(node, "lineno", 0)) for node in calls})
    evidence = [
        Evidence(kind="code", path=path.name, line=line, note="Sprite() construction")
        for line in lines[:3]
    ] or [Evidence(kind="code", path=path.name, note="no Sprite() call anywhere in the file")]
    if len(calls) <= floor["value"]:
        return _result(
            CHECK_SPRITES,
            LEG,
            FAIL,
            evidence,
            f"{len(calls)} Sprite() call(s) — the floor is > {floor['value']}: {floor['citation']}",
        )
    return _result(
        CHECK_SPRITES,
        LEG,
        PASS,
        evidence,
        f"{len(calls)} Sprite() call(s); {floor['citation']}",
    )


def _check_levels(
    baselines: list[int] | None, metadata_path: Path | None, spec_contract: bool,
    cap: FrameCapture,
) -> CheckResult:
    """Level count vs the official band.

    Two bands, because two populations exist. A game built under the §7
    contract (it defines `build_layout`, D13) is held to the measured band
    itself — 6-10, calibration §A, architecture §3's "levels 6-10". A LEGACY
    game (the 25 officials, which predate our contract, and the pre-D13
    fixtures) is held to the reference's own calibrated bounds, which fail
    below 3 and only WARN above 12 — recorded, never failed, the B7
    premise-honest style.
    """
    band = FLOORS["levels_spec_band"]["value"]
    lo, hi = int(band[0]), int(band[1])
    if baselines is None:
        return _result(
            CHECK_LEVELS,
            LEG,
            "premise-not-met",
            [
                Evidence(
                    kind="artifact",
                    path=str(metadata_path) if metadata_path else None,
                    note="no S4 metadata.json with baseline_actions beside the worker or "
                    f"in its `{S4_OUT_SUFFIX}` sibling",
                )
            ],
            "the level count is read off S4's baseline_actions (one baseline per level, "
            "as the 25 officials ship it) and S4 has not run for this worker — the "
            "premise of the floor is not met, so it is recorded, not failed.",
        )
    count = len(baselines)
    evidence = [
        Evidence(
            kind="artifact",
            path=str(metadata_path) if metadata_path else None,
            note=f"baseline_actions has {count} entr{'y' if count == 1 else 'ies'}: {baselines}",
        )
    ]
    if cap.source == "solver" and cap.win:
        evidence.append(
            Evidence(
                kind="frame",
                frame_label=cap.records[-1].label if cap.records else None,
                note=f"the solver capture won after completing {cap.levels_completed} level(s)",
            )
        )
    if spec_contract:
        status = PASS if lo <= count <= hi else FAIL
        return _result(
            CHECK_LEVELS,
            LEG,
            status,
            evidence,
            f"{count} level(s); the §7-contract band is {lo}-{hi} "
            f"({FLOORS['levels_spec_band']['citation']}). The game defines a module-level "
            "build_layout (spec-v0.3 §7 / D13), so it is held to the band itself.",
        )
    minimum, maximum = FLOORS["levels_min"]["value"], FLOORS["levels_max"]["value"]
    in_band = lo <= count <= hi
    note = (
        f"{count} level(s); legacy game (no module-level build_layout, so it predates the "
        f"§7 layout-from-seed contract) — held to the reference's calibrated bounds: FAIL "
        f"below {minimum} ({FLOORS['levels_min']['citation']}), WARN above {maximum} "
        f"({FLOORS['levels_max']['citation']}). Official band {lo}-{hi}: "
        f"{'inside' if in_band else 'OUTSIDE — recorded, not failed'}."
    )
    if count < minimum:
        return _result(CHECK_LEVELS, LEG, FAIL, evidence, note)
    return _result(CHECK_LEVELS, LEG, PASS, evidence, note)


def _check_descent(baselines: list[int] | None, metadata_path: Path | None) -> CheckResult:
    """The staircase floor: the baseline vector must contain a strict descent."""
    floor = FLOORS["baseline_monotonic_fails"]
    if baselines is None:
        return _result(
            CHECK_DESCENT,
            LEG,
            "premise-not-met",
            [Evidence(kind="artifact", note="no S4 metadata.json with baseline_actions")],
            "the staircase is a property of S4's baseline vector and S4 has not run for "
            "this worker — recorded, not failed.",
        )
    evidence = [
        Evidence(
            kind="artifact",
            path=str(metadata_path) if metadata_path else None,
            note=f"baseline_actions = {baselines}",
        )
    ]
    if len(baselines) < 3:
        # S4 itself only enforces the predicate at >= 3 levels and reports
        # "vacuous" below that (`s4_baselines._invariants`); gating harder than
        # the producer would reject vectors S4 deliberately let through.
        return _result(
            CHECK_DESCENT,
            LEG,
            "skipped",
            evidence,
            f"{len(baselines)} baseline(s) — vacuous below 3 levels, exactly as "
            "s4_baselines._invariants reports it.",
        )
    if has_strict_descent(baselines):
        return _result(
            CHECK_DESCENT,
            LEG,
            PASS,
            evidence,
            f"non-monotonic, as official vectors are; {floor['citation']}",
        )
    return _result(
        CHECK_DESCENT,
        LEG,
        FAIL,
        evidence,
        f"no strict descent in {baselines} — a rising (or flat) staircase; "
        f"{floor['citation']}",
    )


def _check_random(robustness_report: Mapping | None) -> CheckResult:
    """random-fails-L1, CONSUMED from the robustness layer's seeded_random row.

    Layer 1 runs FIRST and this floor is a play fact, so a standalone
    structural pass reports it `deferred` (an honest non-answer that never
    rejects, `s3_verify.decide_verdict`) and `merged_gate` re-resolves the
    row once layer 2 has run.
    """
    floor = FLOORS["random_beats_l1_fails"]
    if robustness_report is None:
        return _result(
            CHECK_RANDOM,
            LEG,
            "deferred",
            [Evidence(kind="engine", note="no robustness report supplied to this pass")],
            "the uniform-random policy is layer 2's seeded_random row (architecture §3 "
            "orders structural acceptance BEFORE robustness), so this floor is decided "
            f"there and consumed here; see {ROBUSTNESS_NAME}. {floor['citation']}",
        )
    row = _policy_row(robustness_report, "seeded_random")
    completions = row["completions"]
    evidence = [
        Evidence(
            kind="engine",
            note=f"seeded_random: {row['plan']} — {row['steps_played']} step(s), "
            f"{row['levels_completed']} level(s) completed, state {row['state']}",
        )
    ]
    if completions:
        first = completions[0]
        return _result(
            CHECK_RANDOM,
            LEG,
            FAIL,
            evidence,
            f"a uniform-random policy completed level {first['level']} at step "
            f"{first['step']} of {row['steps']}; {floor['citation']}",
        )
    return _result(
        CHECK_RANDOM,
        LEG,
        PASS,
        evidence,
        f"survives {row['steps_played']} uniform-random action(s) without completing a "
        f"level; {floor['citation']}",
    )


def _check_loc(path: Path, loc: int) -> CheckResult:
    """The stub detector. Below the line it is `deferred`, never `fail`.

    The reference emits WARN here and says why (acceptance.py:58-69): the
    official floor is 722 by this counter, a gate at 777 WARNS ON AN OFFICIAL
    GAME, and at 500 it fires on 64% of the tufa corpus — so no rejection
    threshold is calibrated anywhere in this range. Failing on 200 would be a
    number we invented; passing silently would hide a stub. `deferred` is the
    honest third answer: the count is on the record and the judgement goes to
    the S5 human review bundle with the rest of the legibility evidence.
    """
    floor = FLOORS["loc_warn_below"]
    evidence = [
        Evidence(kind="code", path=path.name, note=f"{loc} non-blank non-comment line(s)")
    ]
    if loc >= floor["value"]:
        return _result(
            CHECK_LOC, LEG, PASS, evidence, f"{loc} LOC, at or above the stub line "
            f"{floor['value']}; {floor['citation']}",
        )
    return _result(
        CHECK_LOC,
        LEG,
        "deferred",
        evidence,
        f"{loc} LOC is below the stub line {floor['value']} — the reference emits a WARN "
        "and never a FAIL here, and no rejection threshold is calibrated in this range, "
        f"so the gate records the number and defers to S5 review. {floor['citation']}",
    )


def structural_acceptance(
    worker_dir: Path,
    cap: FrameCapture,
    *,
    robustness_report: Mapping | None = None,
    metadata_dir: Path | None = None,
) -> dict:
    """Layer 1 — the calibrated floors, in architecture §3 order.

    `sprites>0 · levels 6-10 · non-monotonic staircase · random-fails-L1 · loc
    floor`. Pure static work plus S4's metadata: no engine instantiation, so
    the layer costs milliseconds on every game in the corpus.

    `cap` is the B7 `FrameCapture` the verifier legs argued over; it names the
    game and supplies the solver-line evidence on the level-count row.
    `robustness_report` (additive, keyword-only) is layer 2's report when it
    exists — without it the random-fails-L1 row is `deferred`, never guessed.
    `metadata_dir` (additive, keyword-only) points at an S4 output directory
    that is not the worker's `<worker>.s4/` sibling.

    The verdict is `fail` iff some row is `fail`. `premise-not-met`,
    `deferred` and `skipped` are honest non-answers and never reject
    (`gen/s3_verify.decide_verdict`).
    """
    worker_dir = Path(worker_dir).resolve()
    if not worker_dir.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker_dir}")
    if not isinstance(cap, FrameCapture):
        raise TypeError(f"cap must be a FrameCapture, got {type(cap).__name__}")
    if robustness_report is not None and not isinstance(robustness_report, Mapping):
        raise TypeError(
            f"robustness_report must be a mapping or None, got {type(robustness_report).__name__}"
        )

    path, text, tree = _parse_source(worker_dir)
    metadata_path, metadata = _load_metadata(worker_dir, metadata_dir)
    baselines = _baselines(metadata, metadata_path)
    spec_contract = _has_layout_contract(tree)
    sprite_calls = _sprite_calls(tree)
    loc = _loc(text)

    checks = [
        _check_sprites(path, sprite_calls),
        _check_levels(baselines, metadata_path, spec_contract, cap),
        _check_descent(baselines, metadata_path),
        _check_random(robustness_report),
        _check_loc(path, loc),
    ]
    records = [_check_to_dict(check) for check in checks]
    statuses: dict[str, int] = {}
    for record in records:
        statuses[record["status"]] = statuses.get(record["status"], 0) + 1

    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "layer": "structural",
        "game_id": cap.game_id,
        "worker": str(worker_dir),
        "verdict": FAIL if statuses.get(FAIL) else PASS,
        "checks": records,
        "statuses": statuses,
        "measured": {
            "game_source": str(path),
            "sprite_calls": len(sprite_calls),
            "loc": loc,
            "levels": len(baselines) if baselines is not None else None,
            "baseline_actions": baselines,
            "layout_seed_contract": spec_contract,
            "metadata": str(metadata_path) if metadata_path else None,
            "metadata_game_id": metadata.get("game_id") if metadata else None,
            "random_source": None if robustness_report is None else ROBUSTNESS_NAME,
        },
        "floors": FLOORS,
        "versions": _versions(),
    }


# --- layer 2: the seven degenerate policies (clean-room, D14) ---------------


def _input_for(action_id: int, cell: tuple[int, int] | None = None) -> ActionInput:
    """One declared id as an `ActionInput`; the click action needs `data=`."""
    action = _action_by_id(action_id)
    if action is None:
        raise ValueError(f"declared action id {action_id} has no GameAction — not driveable")
    if action is GameAction.ACTION6:
        x, y = CENTRE_CLICK if cell is None else cell
        return mouse(x, y)
    return ActionInput(id=action)


def _grid_distance(left, right) -> int:
    """Cells that differ between two settled 64x64 boards."""
    return sum(
        1
        for row_left, row_right in zip(left, right)
        for value_left, value_right in zip(row_left, row_right)
        if value_left != value_right
    )


def _noop_like(game_cls, ids: Sequence[int]) -> tuple[int, dict]:
    """The declared id whose single probe changes the settled frame LEAST.

    Contract semantics, verbatim: "the id whose single probe (fresh instance,
    one action) changes the settled frame LEAST (ties -> lowest id), played
    every step — the closest thing to a no-op the game declares". Probes run
    on FRESH instances so no probe can see what another left behind
    (`gen/frames.py`, the determinism section).
    """
    game = _fresh_game(game_cls)
    base = settled_grid(_reset(game))
    del game
    distances: dict[int, int | None] = {}
    for action_id in ids:
        probe = _fresh_game(game_cls)
        _reset(probe)
        probe_fd = _perform(probe, _input_for(action_id))
        del probe
        # A finished game answers with `frame=[]` (base_game.py:207-216), so a
        # one-action win leaves nothing to compare: unmeasurable, not zero.
        distances[action_id] = None if not probe_fd.frame else _grid_distance(
            base, settled_grid(probe_fd)
        )
    measured = {key: value for key, value in distances.items() if value is not None}
    if not measured:
        chosen = int(ids[0])
        detail = "no probe settled a frame (every declared action finished the game)"
    else:
        best = min(measured.values())
        chosen = min(key for key, value in measured.items() if value == best)
        detail = f"min change {best} cell(s), ties -> lowest id"
    return chosen, {
        "probe_distances": {str(key): value for key, value in distances.items()},
        "chosen": chosen,
        "rule": detail,
    }


def _build_policy(
    name: str, index: int, *, game_cls, ids: list[int], cells: Sequence
) -> tuple[object, str, dict]:
    """(callable(fd, step_index, rng) -> ActionInput, plan text, row detail).

    The semantics below are the B11 contract's frozen text, one branch per
    documented policy name (`re-arc-3-source.md:51`). Nothing else specifies
    them and nothing of theirs was read.
    """
    detail: dict = {"declared_ids": list(ids)}

    if name == "noop_like":
        chosen, probe_detail = _noop_like(game_cls, ids)
        detail.update(probe_detail)
        plan = f"ACTION{chosen} every step ({probe_detail['rule']})"
        return (lambda fd, step, rng: _input_for(chosen)), plan, detail

    if name == "repeat_first":
        chosen = int(ids[0])
        plan = f"ACTION{chosen} (ids[0]) every step"
        return (lambda fd, step, rng: _input_for(chosen)), plan, detail

    if name == "repeat_configured_single":
        # "the single id configured as the game's primary — operationalized as
        # the id the engine's click list suggests (ACTION6 with the first
        # engine click cell) when click is declared, else ids[0]".
        if CLICK_ACTION_ID in ids:
            cell = (int(cells[0].x), int(cells[0].y)) if cells else None
            where = (
                f"the engine's first click cell {cell} of {len(cells)}"
                if cells
                else f"centre {CENTRE_CLICK} (the engine reports no clickable sprite)"
            )
            detail["cell"] = list(cell) if cell is not None else list(CENTRE_CLICK)
            detail["click_cells"] = len(cells)
            plan = f"ACTION{CLICK_ACTION_ID} at {where}, every step"
            return (lambda fd, step, rng: _input_for(CLICK_ACTION_ID, cell)), plan, detail
        chosen = int(ids[0])
        plan = f"ACTION{chosen} (ids[0]; the click action is not declared) every step"
        return (lambda fd, step, rng: _input_for(chosen)), plan, detail

    if name == "repeat_up_or_first":
        chosen = UP_ACTION_ID if UP_ACTION_ID in ids else int(ids[0])
        why = "ACTION1 declared" if UP_ACTION_ID in ids else "ACTION1 not declared -> ids[0]"
        plan = f"ACTION{chosen} every step ({why})"
        return (lambda fd, step, rng: _input_for(chosen)), plan, detail

    if name == "cycle_moves":
        moves = [a for a in MOVE_ACTION_IDS if a in ids]
        fallback = not moves
        cycle = moves or list(ids)
        detail["cycle"] = list(cycle)
        plan = (
            f"cycle {cycle} in order"
            + (" (no ACTION1-4 declared -> all declared ids)" if fallback else "")
        )
        return (lambda fd, step, rng: _input_for(cycle[step % len(cycle)])), plan, detail

    if name == "cycle_all":
        cycle = list(ids)
        detail["cycle"] = list(cycle)
        plan = f"cycle all declared ids {cycle} in order (click = centre {CENTRE_CLICK})"
        return (lambda fd, step, rng: _input_for(cycle[step % len(cycle)])), plan, detail

    if name == "seeded_random":
        detail["rng_seed_rule"] = f"random.Random(seed_base + {index})"
        plan = (
            f"uniform over declared ids {list(ids)}; click = rng-uniform cell in "
            f"0..{GRID_SIZE - 1}"
        )

        def play(fd, step, rng):
            action_id = rng.choice(ids)
            if action_id == CLICK_ACTION_ID:
                return _input_for(action_id, (rng.randrange(GRID_SIZE), rng.randrange(GRID_SIZE)))
            return _input_for(action_id)

        return play, plan, detail

    raise ValueError(f"unknown policy {name!r} — the seven are {list(POLICIES)}")


def _run_policy(game_cls, name: str, index: int, *, steps: int, seed_base: int) -> dict:
    """One policy on a FRESH game: drive `steps` actions or until it ends."""
    game = _fresh_game(game_cls)
    fd = _reset(game)
    declared = _playable_action_ids(fd)
    ids = [a for a in declared if _action_by_id(a) is not None]
    # A declared id outside 1-7 is not driveable; `gen/frames.py` skips the
    # same ids in its probe plan and the worker conformance battery (R3) is
    # where declaring one becomes a violation.
    undriveable = [a for a in declared if _action_by_id(a) is None]
    if not ids:
        raise ValueError(
            f"{name}: the game declares no driveable non-RESET action (available_actions="
            f"{declared!r}) — a degenerate policy has nothing to play"
        )
    cells = click_cells(game)
    rng = random.Random(seed_base + index)
    policy, plan, detail = _build_policy(name, index, game_cls=game_cls, ids=ids, cells=cells)
    detail["undriveable_declared"] = undriveable

    completed = int(fd.levels_completed)
    levels = [
        {
            "level": completed + 1,
            "level_index": completed,
            "completed": False,
            "entered_at_step": 0,
            "completed_at_step": None,
        }
    ]
    completions: list[dict] = []
    played: list[str] = []
    for step_index in range(steps):
        if fd.state in TERMINAL_STATES:
            break
        action = policy(fd, step_index, rng)
        if not isinstance(action, ActionInput):
            raise TypeError(
                f"{name} returned {type(action).__name__} at step {step_index + 1}, "
                "expected ActionInput"
            )
        played.append(describe_action(action))
        fd = _perform(game, action)
        step = len(played)
        while int(fd.levels_completed) > completed:
            completed += 1
            levels[-1].update(completed=True, completed_at_step=step)
            completions.append(
                {"level": levels[-1]["level"], "level_index": levels[-1]["level_index"], "step": step}
            )
            levels.append(
                {
                    "level": completed + 1,
                    "level_index": completed,
                    "completed": False,
                    "entered_at_step": step,
                    "completed_at_step": None,
                }
            )

    win = fd.state is GameState.WIN
    if win:
        # A WIN arrives in two shapes and `gen/s5_battery` handles both: the
        # engine may bump `levels_completed` on the winning action, or it may
        # not. When it DID bump, the loop above already recorded that
        # completion and then opened a row for a level that does not exist —
        # the game is over — so that phantom row is dropped. When it did not,
        # the WIN itself completed the level the run was playing.
        # `len(levels) > 1` keeps the table non-empty in the pathological case
        # of a game that is already WIN at RESET: there the single row is
        # marked below, so `completed_any` is True and the gate fails it.
        if len(levels) > 1 and levels[-1]["entered_at_step"] >= len(played):
            levels.pop()
        elif not levels[-1]["completed"]:
            levels[-1].update(completed=True, completed_at_step=len(played))
            completions.append(
                {"level": levels[-1]["level"], "level_index": levels[-1]["level_index"],
                 "step": len(played), "via": "win"}
            )
    return {
        "policy": name,
        "index": index,
        "plan": plan,
        "detail": detail,
        "steps": steps,
        "steps_played": len(played),
        "levels_completed": len(completions),
        "engine_levels_completed": int(fd.levels_completed),
        "completed_any": bool(completions),
        "state": fd.state.name,
        "win": win,
        "levels": levels,
        "completions": completions,
        "actions_sample": played[:ACTION_SAMPLE],
    }


def _policy_row(report: Mapping, name: str) -> dict:
    """One named row out of a robustness report, fail-loud."""
    rows = report.get("policies")
    if rows is None:
        raise ValueError("robustness report has no 'policies' list")
    if not isinstance(rows, Sequence):
        raise TypeError(
            f"robustness report 'policies' must be a sequence, got {type(rows).__name__}"
        )
    found = [row for row in rows if row.get("policy") == name]
    if len(found) != 1:
        raise ValueError(
            f"robustness report holds {len(found)} row(s) for policy {name!r} — expected 1"
        )
    return dict(found[0])


def robustness(
    worker_dir: Path, *, steps: int = ROBUSTNESS_STEPS, seed_base: int = 0
) -> dict:
    """Layer 2 — the seven degenerate policies, each on a fresh game.

    Pass condition (architecture §3, stronger than the documented "all must
    fail to win"): ALL SEVEN MUST FAIL EVERY LEVEL. A policy run that
    completes ANY level — `levels_completed` rises at any point, or the run
    WINs — fails the gate for that level, and the report names policy, level
    and step.
    """
    worker_dir = Path(worker_dir).resolve()
    if not worker_dir.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker_dir}")
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
        raise ValueError(f"steps must be an int >= 1, got {steps!r}")
    if isinstance(seed_base, bool) or not isinstance(seed_base, int):
        raise TypeError(f"seed_base must be an int, got {seed_base!r}")

    game_cls, _solver_cls = load_worker_classes(worker_dir)
    rows = [
        _run_policy(game_cls, name, index, steps=steps, seed_base=seed_base)
        for index, name in enumerate(POLICIES)
    ]
    failures = [
        {"policy": row["policy"], **completion}
        for row in rows
        for completion in row["completions"]
    ]
    probe = _fresh_game(game_cls)
    game_id = str(_reset(probe).game_id)
    del probe
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "layer": "robustness",
        "game_id": game_id,
        "worker": str(worker_dir),
        "policies_spec": list(POLICIES),
        "steps": steps,
        "seed_base": seed_base,
        "verdict": FAIL if failures else PASS,
        "policies": rows,
        "failures": failures,
        "declared_actions": rows[0]["detail"]["declared_ids"] if rows else [],
        "source": (
            "clean-room (D14): the documented policy list in "
            "GEN/provenance/reviews/re-arc-3-source.md:51 plus the B11 contract's frozen "
            "semantics; their implementation was never read"
        ),
        "versions": _versions(),
    }


# --- the two B3 checks: term-witness (R-18) + refusal-persistence (R-08) ----
#
# NOT layers, and not rows of `structural_acceptance`. Both facts are load-
# bearing:
#
#   * a row inside `structural_acceptance` is asserted against all 25 signed
#     officials by `--officials` and by the B11 battery, and neither of these
#     rules is one the officials are held to — `term-witness` reads a spec's
#     declared terms (an official has no spec) and `refusal-persistence` reads
#     §6's promise (the officials ARE the population §6 was measured on, and
#     6/25 of them ship a swallowed transient legally). A new row in that list
#     would move their counts; a check outside it cannot move them at all.
#   * a new LAYER would change the `layers` mapping every consumer of the
#     merged report reads, for two checks that are born in `record` and decide
#     nothing until a batch arms them.
#
# So they are standalone, and the SEAM that runs them is the orchestrator's
# unified fail loop — `gen/orchestrator.py`'s `s3_gate` runner, where the visual
# card's four mode-knobbed checks already reject. That is the W1-A2 lesson: this
# module has no visual wiring either, and a check whose knob lives in the config
# belongs where the other knobbed checks are read, not bolted into a verdict
# function that four callers share. `gate_checks` below is the single entry
# point the runner calls, and it does all the reading, so the loop stays three
# lines.
#
# THEIR KNOBS LIVE UNDER `verifier:`, NOT UNDER `gate:`, and that is deliberate
# rather than convenient. The `gate:` block's key set is `gen/s3_visual.GATE_KEYS`
# — a closed list, in a module this contract does not edit — and every member of
# it is a VISUAL CARD check. These two are not: `term-witness` reads the S2b
# verifier report's own diff, and `refusal-persistence` reads the trace the S2b
# capture wrote against the spec that capture was built from. They sit beside
# `lookalike_declared` and `refusal_honest`, which is where their evidence
# comes from.
CHECK_MODES = ("off", "record", "fail")

TERM_WITNESS_CHECK = "gate.term-witness"
TERM_WITNESS_KNOB = "term_witness"
DEFAULT_TERM_WITNESS = "record"

REFUSAL_PERSISTENCE_CHECK = "gate.refusal-persistence"
REFUSAL_PERSISTENCE_KNOB = "refusal_persistence"
DEFAULT_REFUSAL_PERSISTENCE = "record"

# The diff key and the report key `term-witness` reads, named here rather than
# imported for this module's stated reason: `gen/s3_verify` pulls `gen/backends`
# (the agent drivers) and the gate must stay import-light for the orchestrator.
VERIFY_UNIMPLEMENTED_KEY = "unimplemented_terms"   # s3_verify.UNIMPLEMENTED_KEY
VERIFY_TERM_WINDOW_KEY = "term_window"             # s3_verify.TERM_WINDOW_REPORT_KEY

# Where the two rows are written, beside the gate's own two reports.
EXTRA_CHECKS_NAME = "s3-checks-report.json"

# The spec file the promise is read from, beside the worker (architecture §2).
SPEC_NAME = "spec.yaml"


def _check_mode(cfg: Mapping | None, key: str, default: str) -> str:
    """One `verifier.<key>` mode, validated at READ time and loud on a typo.

    The `_lookalike_mode`/`_refusal_honest_mode` gate in `gen/s3_verify`, and
    for its reason: these knobs decide whether a finding can reject, so a value
    outside the enum is never guessed at.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or key not in verifier:
        return default
    value = verifier[key]
    if value not in CHECK_MODES:
        raise ValueError(
            f"verifier.{key} must be one of {list(CHECK_MODES)}, got {value!r} — `fail` is "
            f"the armed gate and `record` is the evidence default"
        )
    return value


def term_witness_mode(cfg: Mapping | None) -> str:
    """`verifier.term_witness` — off | record (the default) | fail (R-18)."""
    return _check_mode(cfg, TERM_WITNESS_KNOB, DEFAULT_TERM_WITNESS)


def refusal_persistence_mode(cfg: Mapping | None) -> str:
    """`verifier.refusal_persistence` — off | record (default) | fail (R-08)."""
    return _check_mode(cfg, REFUSAL_PERSISTENCE_KNOB, DEFAULT_REFUSAL_PERSISTENCE)


def _red(check_id: str, mode: str, evidence, note: str) -> CheckResult:
    """A finding, as the mode asks for it: `fail` rejects, `record` records."""
    if mode == "fail":
        return _result(check_id, LEG, FAIL, evidence, note)
    return _result(
        check_id, LEG, "deferred", evidence, f"RECORDED, NOT FAILED (`record` mode). {note}"
    )


def term_witness(
    verifier_report: Mapping | None, *, mode: str = DEFAULT_TERM_WITNESS
) -> CheckResult | None:
    """R-18: a DECLARED term the blind audit could ground in no code construct.

    The finding is computed upstream — `s3_verify.compute_diff` diffs the blind
    reply's `term_sites` inventory against the spec's `game.terms` — and this
    check only READS it, which is the same relationship layer 3 has to the S2b
    verdict: this stage consumes an upstream answer and never re-decides it.

    RED ONLY ON A CORROBORATED FINDING, and that is the contract's own bar
    ("red when the verifier report carries an absent-site term that
    corroboration confirmed"), not a softening of it. `_apply_term_corroboration`
    leaves a CORROBORATED finding in `unimplemented_terms` and moves a first
    sighting into `uncorroborated_terms`, so what survives in the list already
    IS the corroborated set — but only when the pass ran at all. The report says
    whether it ran by carrying `term_window` (C-2/C-3's "it appears only when it
    was earned"), and with the pass OFF this check records and never fails:
    "implementation site" is a judgement, R-18 says so in its own risk line, and
    a heuristic must not get a reject path that bypasses the corroboration bar —
    the ruling this file's sibling already wrote for the look-alike detector.

    `premise-not-met` is the honest answer in three different situations and the
    note tells them apart: no report, no diff (a dry run, or an official — which
    has no spec and therefore no declared terms), and a diff with no inventory
    (a blind reply that did not answer the sites section, which is every reply
    written before it existed).
    """
    if mode not in CHECK_MODES:
        raise ValueError(f"term-witness mode must be one of {list(CHECK_MODES)}, got {mode!r}")
    if mode == MODE_OFF:
        return None
    if verifier_report is None:
        return _result(
            TERM_WITNESS_CHECK, LEG, "premise-not-met",
            [Evidence(kind="artifact", note="no verifier report supplied to this pass")],
            "R-18's finding is computed at S2b and consumed here; without S2b's report "
            "there is no inventory to read.",
        )
    if not isinstance(verifier_report, Mapping):
        raise TypeError(
            f"verifier_report must be a mapping or None, got {type(verifier_report).__name__}"
        )
    diff = verifier_report.get("diff")
    if not isinstance(diff, Mapping):
        return _result(
            TERM_WITNESS_CHECK, LEG, "premise-not-met",
            [Evidence(kind="artifact", note="the verifier report carries no diff")],
            "A report with no diff is a dry run or an official: neither has a spec, so "
            "neither declares the terms this check holds a game to.",
        )
    if VERIFY_UNIMPLEMENTED_KEY not in diff:
        return _result(
            TERM_WITNESS_CHECK, LEG, "premise-not-met",
            [Evidence(kind="artifact",
                      note=f"the diff carries no `{VERIFY_UNIMPLEMENTED_KEY}` list")],
            "The blind reply carried no implementation-site inventory, so no term was "
            "grounded OR ungrounded and there is nothing to judge. Recorded, not passed: "
            "an unanswered question is not a clean answer.",
        )
    unimplemented = list(diff[VERIFY_UNIMPLEMENTED_KEY])
    corroborated = VERIFY_TERM_WINDOW_KEY in verifier_report
    window = verifier_report.get(VERIFY_TERM_WINDOW_KEY)
    recorded = [
        entry.get("term")
        for entry in diff.get("uncorroborated_terms", [])
        if isinstance(entry, Mapping) and entry.get("code") == "term-witness"
    ]
    evidence = [
        Evidence(
            kind="artifact",
            note=f"{VERIFY_UNIMPLEMENTED_KEY}={unimplemented}; term corroboration "
            + (f"ran (window={window})" if corroborated else "did NOT run")
            + (f"; demoted first sighting(s) {sorted(recorded)}" if recorded else ""),
        )
    ]
    if not unimplemented:
        return _result(
            TERM_WITNESS_CHECK, LEG, PASS, evidence,
            "Every term this spec declares was grounded in a named code construct by the "
            "blind audit"
            + (
                f" — and {len(recorded)} ungrounded term(s) {sorted(recorded)} were demoted "
                "to a recording as first sightings, standing until a second round sees them "
                "the same way."
                if recorded
                else "."
            ),
        )
    if not corroborated:
        return _red(
            TERM_WITNESS_CHECK, "record", evidence,
            f"The blind audit could ground {len(unimplemented)} DECLARED term(s) "
            f"{unimplemented} in no code construct — but `verifier.term_corroboration` was "
            f"off this round, so this is ONE session's say-so and nothing corroborated it. "
            f"An implementation site is a judgement (R-18 names the risk), and a single "
            f"round's judgement records here rather than deciding: arm the corroboration "
            f"pass to let this check reject.",
        )
    return _red(
        TERM_WITNESS_CHECK, mode, evidence,
        f"The spec declares {len(unimplemented)} term(s) {unimplemented} that the blind "
        f"audit could ground in NO code construct, and the finding is corroborated — a "
        f"recorded round in scope (window={window}) reported the same term the same way, "
        f"so this is not one session's rotation. A declared mechanic with no implementation "
        f"is the mosaic defect (R-18): the spec introduces it at a level, the game never "
        f"ships it, and the audit passes because a silence reads like an omission. Implement "
        f"the mechanic, or stop declaring it.",
    )


def _refusal_promise(spec_path: Path | None) -> tuple[bool, str]:
    """Does this spec PROMISE a settled-frame-persistent refusal signal?

    B1's §11 rule, read at the only place B3 can read it — off the spec
    document. `game.knobs.refusal: visible` makes the promise; the optional
    `game.knobs.refusal_transient: true` is the declared exception that
    withdraws it. Every other answer is a non-answer with its reason, never a
    defect (`s3_static._declared_deception_entries` sets the precedent).

    The two field names come from `gen/s1_spec`, imported INSIDE the function:
    the module holds the §11 authoring rules and nothing here needs them
    otherwise, and re-spelling the keys locally would let the spec that MAKES
    the promise and the check that READS it drift apart silently — which is the
    exact failure class this check exists to catch.
    """
    from .s1_spec import REFUSAL_TRANSIENT_FIELD, REFUSAL_VISIBLE

    if spec_path is None:
        return False, "no spec path was passed to the check"
    spec_path = Path(spec_path)
    if not spec_path.is_file():
        return False, f"no spec file at {spec_path}"
    try:
        document = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return False, f"{spec_path} could not be read as YAML ({exc})"
    game = document.get("game") if isinstance(document, Mapping) else None
    knobs = game.get("knobs") if isinstance(game, Mapping) else None
    if not isinstance(knobs, Mapping):
        return False, f"{spec_path.name} declares no `game.knobs` mapping"
    declared = knobs.get("refusal")
    if declared != REFUSAL_VISIBLE:
        return False, (
            f"{spec_path.name} declares `knobs.refusal: {declared!r}`, and only "
            f"{REFUSAL_VISIBLE!r} promises a signal a settled frame must carry"
        )
    if knobs.get(REFUSAL_TRANSIENT_FIELD) is True:
        return False, (
            f"{spec_path.name} declares `knobs.{REFUSAL_TRANSIENT_FIELD}: true` — the §11 "
            f"exception: this refusal signal is deliberately transient and is not something "
            f"a player has to learn, so no settled frame is asked to carry it"
        )
    return True, (
        f"{spec_path.name} declares `knobs.refusal: {REFUSAL_VISIBLE}` and no "
        f"`{REFUSAL_TRANSIENT_FIELD}`, so it promises a refusal signal that survives into a "
        f"settled frame (§6:160's bar: a signal persisting >= 1 settled frame)"
    )


def _declared_action_ids(spec_path: Path) -> set[int] | None:
    """The ids `game.actions` marks `declared`, or None when it cannot be read.

    §5's action table, read off the spec exactly as the promise above is. The
    ids are the `ACTION<n>` suffixes, which are the engine's own `GameAction`
    values (`gen/s1_spec.ACTION_KEYS`, `gen/frames._action_by_id`).
    """
    try:
        document = yaml.safe_load(Path(spec_path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    game = document.get("game") if isinstance(document, Mapping) else None
    actions = game.get("actions") if isinstance(game, Mapping) else None
    if not isinstance(actions, Mapping):
        return None
    declared: set[int] = set()
    for key, state in actions.items():
        name = str(key)
        if name.startswith("ACTION") and name[6:].isdigit() and state == "declared":
            declared.add(int(name[6:]))
    return declared


def _swallowed_signal_steps(
    records: Sequence[Mapping], declared_ids: Collection[int] | None
) -> dict:
    """Steps that RENDERED something and settled onto the board they started on.

    Read off A1's trace: one record per engine action, each carrying `n_anim` —
    how many frames that action rendered — and the LAST of those frames, deduped
    against its predecessor.

    A step with `n_anim > 1` whose settled frame is byte-identical to the
    previous settled frame drew something and kept none of it: the signal exists
    in a frame the engine threw away. That is §6's measured "transient-only
    feedback, swallowed before the settled frame" (6/25 officials), and it is
    exactly what conduit-watch's one-frame flash does — the flash renders on the
    first pass and the second pass clears it, so `frame[-1]` never carries it.

    TWO EXCLUSIONS, both measured rather than assumed:

    * an UNDECLARED action's step never counts. A game whose §5 table marks an
      action `absent` still receives it from the engine, and a two-pass render
      idiom then produces exactly this signature with no refusal anywhere near
      it — measured on facing-sentinel-match-the-signal-row, which declares
      ACTION6 absent and answers 7 of 7 probe clicks that way. An action the
      game never advertised is not a refusal of anything.
    * a step with `n_anim == 1` and no change is counted separately and never
      reported as a finding: nothing distinguishes it from an action the game
      legitimately ignores, and this check does not guess.

    `declared_ids=None` (no readable action table) keeps every step in scope and
    says so in the returned `scope`, because narrowing on a table this could not
    read would silently drop real findings.
    """
    resolved = resolve_trace_frames(list(records))
    swallowed: list[int] = []
    undeclared = 0
    silent = 0
    previous: list[str] | None = None
    for index, (record, rows) in enumerate(zip(records, resolved, strict=True)):
        if index == 0:
            previous = rows
            continue
        if rows is not None and rows == previous:
            # `action` is the trace's `[id, data]` pair. Read defensively: this
            # file is read off disk, and a record this cannot parse must land
            # OUT of scope rather than raise — a malformed line is not evidence
            # about the game.
            action = record.get("action")
            action_id = (
                int(action[0])
                if isinstance(action, list)
                and action
                and isinstance(action[0], int)
                and not isinstance(action[0], bool)
                else -1
            )
            if int(record.get("n_anim", 0)) <= 1:
                silent += 1
            elif declared_ids is not None and action_id not in declared_ids:
                undeclared += 1
            else:
                swallowed.append(int(record.get("t", index)))
        if rows is not None:
            previous = rows
    return {
        "swallowed": swallowed,
        "undeclared": undeclared,
        "silent": silent,
        "scope": (
            f"declared action ids {sorted(declared_ids)}"
            if declared_ids is not None
            else "every action (the spec's §5 action table could not be read)"
        ),
    }


def _hex_digit(index: int) -> str:
    """The trace's encoding of one palette index (`frames.trace_hex_rows`)."""
    return format(int(index) & 0xF, "x")


def _colour_in_trace(frames: Sequence[object], index: int) -> int:
    """How many traced boards carry this palette index."""
    digit = _hex_digit(index)
    return sum(1 for rows in frames if rows and any(digit in str(row) for row in rows))


def _colour_in_settled(cap: FrameCapture | None, index: int) -> list[str]:
    """The sidecar records that carry this palette index, by label."""
    if cap is None:
        return []
    found: list[str] = []
    for record in cap.records:
        grid = getattr(record, "grid", None)
        if grid is not None and any(int(index) in row for row in grid):
            found.append(str(getattr(record, "label", "?")))
    return found


def refusal_persistence(
    worker_dir: Path,
    cap: FrameCapture | None = None,
    spec_path: Path | None = None,
    *,
    mode: str = DEFAULT_REFUSAL_PERSISTENCE,
) -> CheckResult | None:
    """R-08: a refusal signal the spec promised and no settled frame carries.

    Reads A1's step trace (`frames.trace`, OFF by default), so a worker with no
    trace beside it is `premise-not-met` — NOT-CHECKED, never a clean bill. The
    settled sidecar cannot answer this question alone: it keeps the reset, one
    frame per level transition and the final frame, so every transient between
    them is invisible to it by construction. The trace is the artifact that made
    the question askable, which is why this check is the one that reads it.

    TWO SHAPES OF "the signal is in no settled frame", because the audit found
    two and they need different evidence:

    * DRAWN AND WIPED. The source names a refusal colour, some traced step
      paints it, and NO sidecar record carries it — the signal lived for one
      action and the next action took it back down. This is the audit's
      "refusal is code-only in 6 of 7": the colour is real, reachable and
      invisible to anything reading settled frames, which is every downstream
      consumer we have. It needs BOTH artifacts — the trace to prove the paint
      happened, the sidecar to prove it did not last — which is why `cap` is
      read here beside the trace.
    * SWALLOWED BEFORE THE FRAME. A step on a DECLARED action rendered more than
      one frame and settled onto the board it started from, so the engine threw
      the drawn frame away. conduit-watch is this one exactly: its flash renders
      on the first pass and the second pass clears it, so it lands in
      `frame[-2]` and nothing — not even the trace — keeps it.

    Either is a finding, and the note says which fired.

    KNOWN SCOPE, stated on every card it writes: the capture drives the worker's
    own SOLVER, which plays a clean line and may refuse rarely or never. A clean
    answer here means "nothing in the line that was captured", which is weaker
    than "this game's refusal persists".
    """
    if mode not in CHECK_MODES:
        raise ValueError(
            f"refusal-persistence mode must be one of {list(CHECK_MODES)}, got {mode!r}"
        )
    if mode == MODE_OFF:
        return None

    worker_dir = Path(worker_dir)
    if spec_path is None:
        spec_path = worker_dir.parent / SPEC_NAME
    promised, why = _refusal_promise(spec_path)
    trace_file = trace_path(worker_dir)
    evidence = [
        Evidence(kind="artifact", path=str(spec_path), note=why),
        Evidence(kind="artifact", path=str(trace_file),
                 note="the R-20 step trace" if trace_file.is_file() else "no step trace"),
    ]
    if not promised:
        return _result(
            REFUSAL_PERSISTENCE_CHECK, LEG, "premise-not-met", evidence,
            f"This spec makes no settled-frame promise about its refusal: {why}. There is a "
            f"rule to enforce only where one was made.",
        )
    if not trace_file.is_file():
        return _result(
            REFUSAL_PERSISTENCE_CHECK, LEG, "premise-not-met", evidence,
            f"NOT CHECKED: no step trace at {trace_file}. The settled frames sidecar keeps "
            "the reset, the level transitions and the final board only, so a signal that "
            "lives between them is invisible to it by construction — this question is only "
            "askable with `frames.trace: on` (R-20, OFF by default), and a capture that "
            "never traced is not evidence that the promise was kept.",
        )
    try:
        _header, records = read_trace(trace_file)
    except (OSError, ValueError) as exc:
        return _result(
            REFUSAL_PERSISTENCE_CHECK, LEG, "premise-not-met", evidence,
            f"NOT CHECKED: {trace_file} could not be read ({type(exc).__name__}: {exc}).",
        )
    measured = _swallowed_signal_steps(records, _declared_action_ids(spec_path))
    steps = measured["swallowed"]
    evidence.append(
        Evidence(
            kind="engine",
            note=f"{len(records)} traced step(s) over {measured['scope']}; {len(steps)} "
            f"rendered more than one frame and settled onto an unchanged board "
            f"(t={steps[:6]}); {measured['undeclared']} more did the same on an UNDECLARED "
            f"action and are out of scope; {measured['silent']} single-frame step(s) changed "
            f"nothing at all",
        )
    )

    # Shape 1: the refusal colour the source names, painted in the trace and in
    # no settled record. Measurable only with BOTH artifacts in hand.
    indices = refusal_palette_indices(worker_dir)
    frames = resolve_trace_frames(list(records))
    wiped: list[str] = []
    for index in indices:
        painted = _colour_in_trace(frames, index)
        settled = _colour_in_settled(cap, index)
        evidence.append(
            Evidence(
                kind="frame",
                note=f"refusal colour {index}: painted in {painted} traced board(s); "
                + (f"carried by settled record(s) {settled}" if settled else "carried by NO "
                   "settled record")
                + ("" if cap is not None else " (no capture was supplied to compare against)"),
            )
        )
        if cap is not None and painted and not settled:
            wiped.append(
                f"palette index {index} is the source's own refusal colour, {painted} traced "
                f"board(s) paint it, and none of the {len(cap.records)} settled record(s) "
                f"carries it"
            )

    if not steps and not wiped:
        return _result(
            REFUSAL_PERSISTENCE_CHECK, LEG, PASS, evidence,
            "The promised refusal signal is not measurably lost: no declared action in the "
            "captured line rendered a frame the engine threw away, and "
            + (
                "this source names no refusal colour to follow into the settled frames."
                if not indices
                else f"the refusal colour(s) {list(indices)} reach a settled record."
                if cap is not None
                else f"the refusal colour(s) {list(indices)} were NOT followed into the "
                "settled frames — no capture was supplied to compare the trace against."
            )
            + f" SCOPE: the capture drives this worker's own solver, which plays a clean line "
            f"and may never refuse, so this is a pass on the {len(records)} step(s) that were "
            f"traced and not a proof that every refusal persists.",
        )
    reasons = [
        *wiped,
        *(
            [
                (
                    f"{len(steps)} traced step(s) on a DECLARED action rendered more than "
                    f"one frame and ended on a board byte-identical to the one they started "
                    f"from (t={steps[:6]}), so whatever they drew was swallowed before the "
                    f"settled frame"
                )
            ]
            if steps
            else []
        ),
    ]
    return _red(
        REFUSAL_PERSISTENCE_CHECK, mode, evidence,
        f"This game's refusal signal does not survive into a settled frame, while {why}. "
        + " Also: ".join(reasons)
        + ". §6:160's bar for a visible refusal is a signal persisting into at least one "
        "settled frame; a flash the next action wipes, and a flash that renders into "
        "`frame[-2]`, both fail it — and every downstream consumer of this pipeline reads "
        "settled frames. Paint the refusal into the SETTLED board the engine keeps, or "
        "declare `knobs.refusal_transient: true` and say the signal is deliberately "
        "transient.",
    )


def gate_checks(
    worker_dir: Path,
    verifier_report: Mapping | None,
    *,
    cap: FrameCapture | None = None,
    cfg: Mapping | None = None,
    out_dir: Path | None = None,
    spec_path: Path | None = None,
) -> dict:
    """Both B3 checks, their knobs read once, their rows written once.

    The single entry point the orchestrator's unified fail loop calls. Returns
    `{checks, path, verdict}`: the `CheckResult`s in canon order, where the rows
    were written (None when neither check ran), and `fail` iff some row failed.

    `cap` is the gate's own capture, handed through so `refusal-persistence` can
    ask whether a colour the trace paints ever reaches a SETTLED record. Without
    it that half is not measured and the check says so.

    The knobs are read FIRST, before either check touches a file, so a typo is a
    loud ValueError rather than a gate that quietly ran without the check it was
    configured to run — the wave's common rule, and the order `assemble_report`
    already keeps for the corroboration knobs.
    """
    modes = (
        (TERM_WITNESS_CHECK, term_witness_mode(cfg)),
        (REFUSAL_PERSISTENCE_CHECK, refusal_persistence_mode(cfg)),
    )
    worker_dir = Path(worker_dir)
    checks = [
        term_witness(verifier_report, mode=dict(modes)[TERM_WITNESS_CHECK]),
        refusal_persistence(
            worker_dir, cap, spec_path, mode=dict(modes)[REFUSAL_PERSISTENCE_CHECK]
        ),
    ]
    rows = [check for check in checks if check is not None]
    path: Path | None = None
    if rows and out_dir is not None:
        path = Path(out_dir) / EXTRA_CHECKS_NAME
        _write_json(
            path,
            {
                "schema_version": SCHEMA_VERSION,
                "stage": STAGE,
                "worker": str(worker_dir),
                "modes": {check_id: mode for check_id, mode in modes},
                "checks": [_check_to_dict(row) for row in rows],
                "verdict": FAIL if any(row.status == FAIL for row in rows) else PASS,
                "versions": _versions(),
            },
        )
    return {
        "checks": rows,
        "path": path,
        "verdict": FAIL if any(row.status == FAIL for row in rows) else PASS,
    }


# --- the merged gate --------------------------------------------------------


def _layer(status: str, detail: str, **extra) -> dict:
    return {"status": status, "detail": detail, **extra}


def _verifier_layer(report: Mapping | None) -> dict:
    if report is None:
        return _layer(
            LAYER_PENDING,
            "no verifier report yet — S2b's verdict is CONSUMED here, never re-decided "
            "(architecture §3 layer 3)",
            verdict=None,
        )
    if not isinstance(report, Mapping):
        raise TypeError(f"verifier_report must be a mapping or None, got {type(report).__name__}")
    if "verdict" not in report:
        raise ValueError("verifier report has no 'verdict' key — see gen/s3_verify.VERDICTS")
    verdict = report["verdict"]
    if verdict == VERIFIER_VERDICT_PASS:
        return _layer(LAYER_PASS, "S2b verdict is clean", verdict=verdict)
    reasons = report.get("reject_reasons") or []
    codes = sorted({str(reason.get("code")) for reason in reasons if isinstance(reason, Mapping)})
    return _layer(
        LAYER_FAIL,
        f"S2b verdict is {verdict!r}"
        + (f" — reject code(s) {codes}" if codes else "")
        + (
            ""
            if verdict in VERIFIER_VERDICTS
            else f" — and {verdict!r} is OUTSIDE gen/s3_verify.VERDICTS {list(VERIFIER_VERDICTS)}: "
            "the report is malformed, so the gate refuses to read it as a pass"
        ),
        verdict=verdict,
        reject_codes=codes,
    )


def _battery_layer(report: Mapping | None) -> dict:
    if report is None:
        return _layer(
            LAYER_PENDING,
            "no battery report yet — S3d runs after S4 supplies baselines "
            "(architecture §3 layer 4)",
            battery_status=None,
        )
    if not isinstance(report, Mapping):
        raise TypeError(f"battery_report must be a mapping or None, got {type(report).__name__}")
    if "status" not in report:
        raise ValueError("battery report has no 'status' key — see gen/s5_battery.STATUS_*")
    status = report["status"]
    if status == BATTERY_STATUS_COMPLETE:
        return _layer(LAYER_PASS, "battery completed", battery_status=status)
    return _layer(
        LAYER_FAIL,
        f"battery status is {status!r}, not {BATTERY_STATUS_COMPLETE!r}"
        + (
            ""
            if status in BATTERY_STATUSES
            else f" — and {status!r} is OUTSIDE gen/s5_battery's statuses "
            f"{list(BATTERY_STATUSES)}: the report is malformed"
        ),
        battery_status=status,
    )


def merged_gate(
    worker_dir: Path,
    cap: FrameCapture,
    *,
    verifier_report: Mapping | None,
    battery_report: Mapping | None,
    seed_base: int = 0,
    out_dir: Path | None = None,
    steps: int = ROBUSTNESS_STEPS,
    metadata_dir: Path | None = None,
) -> dict:
    """All four layers, short-circuiting in architecture §3 order.

    1 structural → 2 robustness → 3 verifier (`verdict == "pass"` required;
    `None` = `pending`) → 4 battery (`status == "complete"` required; `None` =
    `pending`). A layer that is never reached is `skipped`.

    `verdict` is `gated` only when all four are green; `rejected` when a layer
    fails; `pending` when the first non-green layer is only waiting for an
    upstream report. `short_circuited_at` is the FIRST layer in canon order
    that is not `pass` — which is why a random-beaten game is attributed to
    `structural` even though layer 2 measured it: that floor is consumed by
    layer 1's row (see `_check_random`).

    Writes `acceptance-report.json` and (when layer 2 ran)
    `robustness-report.json` under `<worker>.gate/`, or under `out_dir`.
    Deterministic: same worker + same `seed_base` → byte-identical reports.
    """
    worker_dir = Path(worker_dir).resolve()
    if not worker_dir.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker_dir}")
    if out_dir is not None:
        target = Path(out_dir).resolve()
    else:
        target = (worker_dir.parent / (worker_dir.name + GATE_SUFFIX)).resolve()
        if REPO_ROOT not in target.parents:
            # The default sibling would land outside this repo — e.g. beside an
            # OFFICIAL, which lives in duckWM. gen/ never writes into a sister
            # repo (D25 repo boundary; the officials corpus is READ-ONLY).
            raise ValueError(
                f"the default report sibling {target} is outside {REPO_ROOT} — gen/ never "
                "writes into a sister repo (D25; the officials corpus is READ-ONLY). Pass "
                "out_dir explicitly for a worker that lives outside this repo."
            )

    layers: dict[str, dict] = {
        name: _layer(LAYER_SKIPPED, "not reached — an earlier layer stopped the gate")
        for name in LAYERS
    }
    paths = {"out_dir": str(target), "acceptance": str(target / ACCEPTANCE_NAME), "robustness": None}

    structural = structural_acceptance(worker_dir, cap, metadata_dir=metadata_dir)
    _write_json(target / ACCEPTANCE_NAME, structural)
    if structural["verdict"] != PASS:
        fails = [row["check_id"] for row in structural["checks"] if row["status"] == FAIL]
        layers["structural"] = _layer(
            LAYER_FAIL, f"structural floor(s) failed: {fails}", report=structural
        )
        return _merged(worker_dir, cap, layers, paths, seed_base, steps)

    robustness_report = robustness(worker_dir, steps=steps, seed_base=seed_base)
    _write_json(target / ROBUSTNESS_NAME, robustness_report)
    paths["robustness"] = str(target / ROBUSTNESS_NAME)

    # The random-fails-L1 row is consumed from layer 2, so layer 1's report is
    # re-resolved and rewritten now that the seeded_random row exists.
    structural = structural_acceptance(
        worker_dir, cap, robustness_report=robustness_report, metadata_dir=metadata_dir
    )
    _write_json(target / ACCEPTANCE_NAME, structural)
    fails = [row["check_id"] for row in structural["checks"] if row["status"] == FAIL]
    layers["structural"] = (
        _layer(LAYER_PASS, "all structural floors clear", report=structural)
        if not fails
        else _layer(LAYER_FAIL, f"structural floor(s) failed: {fails}", report=structural)
    )
    layers["robustness"] = (
        _layer(
            LAYER_PASS,
            f"all {len(POLICIES)} degenerate policies completed zero levels in "
            f"{robustness_report['steps']} steps each",
            report=robustness_report,
        )
        if robustness_report["verdict"] == PASS
        else _layer(
            LAYER_FAIL,
            "degenerate policies completed levels: "
            + "; ".join(
                f"{failure['policy']} -> level {failure['level']} at step {failure['step']}"
                for failure in robustness_report["failures"]
            ),
            report=robustness_report,
        )
    )
    if fails or robustness_report["verdict"] != PASS:
        return _merged(worker_dir, cap, layers, paths, seed_base, steps)

    layers["verifier"] = _verifier_layer(verifier_report)
    if layers["verifier"]["status"] != LAYER_PASS:
        return _merged(worker_dir, cap, layers, paths, seed_base, steps)
    layers["battery"] = _battery_layer(battery_report)
    return _merged(worker_dir, cap, layers, paths, seed_base, steps)


def _merged(
    worker_dir: Path, cap: FrameCapture, layers: dict, paths: dict, seed_base: int, steps: int
) -> dict:
    short_circuit = next(
        (name for name in LAYERS if layers[name]["status"] != LAYER_PASS), None
    )
    if short_circuit is None:
        verdict = VERDICT_GATED
    elif layers[short_circuit]["status"] == LAYER_PENDING:
        verdict = VERDICT_PENDING
    else:
        verdict = VERDICT_REJECTED
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "game_id": cap.game_id,
        "worker": str(worker_dir),
        "seed_base": seed_base,
        "steps": steps,
        "layers": layers,
        "verdict": verdict,
        "short_circuited_at": short_circuit,
        "paths": paths,
        "versions": _versions(),
    }


# --- CLI --------------------------------------------------------------------


def _load_json(path: str | None) -> dict | None:
    if path is None:
        return None
    with Path(path).open(encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise TypeError(f"{path}: expected a JSON object, got {type(payload).__name__}")
    return payload


def _capture_for(worker_dir: Path) -> FrameCapture:
    """A probe capture — the B7 material layer 1 quotes as evidence."""
    game_cls, _solver_cls = load_worker_classes(worker_dir)
    return capture(game_cls)


def _print_structural(report: Mapping) -> None:
    print(
        f"[gate] structural {report['verdict'].upper()} {report['game_id']} | "
        f"levels {report['measured']['levels']} | sprites {report['measured']['sprite_calls']} "
        f"| loc {report['measured']['loc']} | §7 layout {report['measured']['layout_seed_contract']}"
    )
    for row in report["checks"]:
        print(f"       {row['status']:>15}  {row['check_id']:24} {row['note'][:96]}")


def _print_robustness(report: Mapping) -> None:
    print(
        f"[gate] robustness {report['verdict'].upper()} {report['game_id']} | "
        f"{len(report['policies'])} policies x {report['steps']} steps | "
        f"declared {report['declared_actions']}"
    )
    for row in report["policies"]:
        flag = "COMPLETED" if row["completed_any"] else "zero"
        print(
            f"       {flag:>9} levels  {row['policy']:26} {row['steps_played']:>4} step(s) "
            f"{row['state']:<13} {row['plan'][:60]}"
        )


def _officials_battery(cfg: Mapping, *, steps: int, seed_base: int) -> int:
    """The calibration run: both layers over the 25 signed officials.

    Clean means: zero structural `fail` rows anywhere, and every robustness
    failure is exactly a `KNOWN_OFFICIAL_FAILS` pin. A pin that stops
    reproducing is ALSO a miscalibration — a stale pin hides a live check.
    """
    from .officials import discover_officials, load_official_class

    officials = discover_officials(dict(cfg))
    print(f"CALIBRATION — both gate layers over the {len(officials)} signed officials\n")
    structural_bad: list[tuple[str, list]] = []
    unexpected: list[tuple[str, dict]] = []
    reproduced: set[str] = set()
    for official in officials:
        worker_dir = official.py_path.parent
        game_cls = load_official_class(official.py_path)
        cap = capture(game_cls)
        report = structural_acceptance(worker_dir, cap)
        rob = robustness(worker_dir, steps=steps, seed_base=seed_base)
        fails = [row["check_id"] for row in report["checks"] if row["status"] == FAIL]
        if fails:
            structural_bad.append((official.slug, fails))
        for failure in rob["failures"]:
            if is_pinned_official_fail(official.slug, failure):
                reproduced.add(official.slug)
            else:
                unexpected.append((official.slug, failure))
        other = {
            row["status"] for row in report["checks"] if row["status"] not in (PASS, FAIL)
        }
        print(
            f"  {'FAIL' if fails else 'ok  '} {official.slug:6} levels "
            f"{report['measured']['levels']:>2} sprites {report['measured']['sprite_calls']:>3} "
            f"loc {report['measured']['loc']:>5} | policies completed "
            f"{sum(row['levels_completed'] for row in rob['policies'])} level(s)"
            + (f" | PINNED {KNOWN_OFFICIAL_FAILS[official.slug]['policy']}"
               if official.slug in reproduced else "")
            + (f" | {sorted(other)}" if other else "")
        )
    stale = sorted(set(KNOWN_OFFICIAL_FAILS) - reproduced)
    bad = bool(structural_bad or unexpected or stale)
    print(
        f"\n{'MISCALIBRATED' if bad else 'CALIBRATED'}: {len(structural_bad)} structural "
        f"failure(s), {len(unexpected)} unexpected robustness failure(s), "
        f"{len(stale)} stale pin(s) over {len(officials)} officials "
        f"({len(reproduced)} adjudicated exception(s) reproduced)."
    )
    for slug, fails in structural_bad:
        print(f"  structural {slug}: {fails}")
    for slug, failure in unexpected:
        print(f"  robustness {slug}: {failure}")
    for slug in stale:
        print(f"  stale pin {slug}: {KNOWN_OFFICIAL_FAILS[slug]['policy']} no longer fails")
    return 2 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S3 — the merged gate (structural + robustness)")
    parser.add_argument("--worker", default=None, help="worker dir holding game.py")
    parser.add_argument(
        "--layer",
        default="merged",
        choices=("structural", "robustness", "merged"),
        help="run one layer or the merged gate (default: merged)",
    )
    parser.add_argument("--out", default=None, help=f"write reports here instead of <worker>{GATE_SUFFIX}/")
    parser.add_argument("--steps", type=int, default=ROBUSTNESS_STEPS)
    parser.add_argument("--seed-base", type=int, default=0)
    parser.add_argument("--metadata-dir", default=None, help="S4 output dir, when not the sibling")
    parser.add_argument("--verifier-report", default=None, help="S2b verifier-report.json")
    parser.add_argument("--battery-report", default=None, help="S3d battery-report.json")
    parser.add_argument("--officials", action="store_true", help="the 25-official calibration run")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)

    if args.officials:
        return _officials_battery(
            load_config(args.config), steps=args.steps, seed_base=args.seed_base
        )
    if not args.worker:
        parser.error("--worker is required (or --officials)")

    worker = Path(args.worker).resolve()
    if not worker.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker}")
    metadata_dir = Path(args.metadata_dir).resolve() if args.metadata_dir else None

    if args.layer == "robustness":
        report = robustness(worker, steps=args.steps, seed_base=args.seed_base)
        _print_robustness(report)
        return 0 if report["verdict"] == PASS else 2
    if args.layer == "structural":
        report = structural_acceptance(worker, _capture_for(worker), metadata_dir=metadata_dir)
        _print_structural(report)
        return 0 if report["verdict"] == PASS else 2

    report = merged_gate(
        worker,
        _capture_for(worker),
        verifier_report=_load_json(args.verifier_report),
        battery_report=_load_json(args.battery_report),
        seed_base=args.seed_base,
        out_dir=Path(args.out) if args.out else None,
        steps=args.steps,
        metadata_dir=metadata_dir,
    )
    _print_structural(report["layers"]["structural"]["report"])
    if "report" in report["layers"]["robustness"]:
        _print_robustness(report["layers"]["robustness"]["report"])
    print(
        f"[gate] {report['verdict'].upper()} {report['game_id']} | "
        + " · ".join(f"{name}={report['layers'][name]['status']}" for name in LAYERS)
        + (f" | stopped at {report['short_circuited_at']}" if report["short_circuited_at"] else "")
    )
    print(f"[gate] reports -> {report['paths']['out_dir']}")
    return {VERDICT_GATED: 0, VERDICT_REJECTED: 2, VERDICT_PENDING: 3}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
