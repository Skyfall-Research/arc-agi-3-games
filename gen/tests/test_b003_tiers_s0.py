"""Blind pins for the b003 tier engine (`gen.tiers`) and its S0 knobs.

Run: .venv/bin/python -m pytest gen/tests/test_b003_tiers_s0.py -v

Written from the frozen T-A-tests contract ALONE. `gen/tiers.py` was never
read (it did not exist when this file was written) and neither was any
in-progress tier diff of `gen/s0_ideas.py`; only that module's PRE-EXISTING
public surface (`sample_batch`, `build_prose_prompt`, `check_config`, `TIERS`,
`IDEA_STRUCTURAL_FIELDS`, `load_vocab`) is used here. These pins therefore
describe the contract, not the implementation, and are expected to fail until
the implementation lands.

House style follows `test_b002_promptsync.py`: every canon fact is READ OUT OF
THE CANON FILES at test time (never retyped), the canon tree is opened
read-only, and nothing is written outside `tmp_path`.

What is pinned, in contract order:

  * the frozen public surface — the three ordinal maps, the frozen `TierRow`
    dataclass and its ten fields, the three `TIER_TABLE` rows, the default
    term budgets, the `COMPLEXITY_OVERRIDE` prefix, and every accept/reject
    rule of `tier_policy(cfg)`;
  1. canon drift — the §3.3 tier table in `design/difficulty-model.md` is
     parsed and every cell is matched against the frozen row;
  2. the officials anchor — `DEFAULT_TERM_BUDGETS` is the 25 officials'
     n_terms order statistics, read out of `mechanics/game-term-matrix.csv`;
  3. knob-off replay — the b002 config draws bit-identically with the tier
     work in the tree, and a `policy=None` prompt is today's prompt;
  4. `batch.tier_sequence` — honored per slot, and rejected loudly;
  5. per-tier seed counts;
  6. the `common-official` term bias;
  7. per-tier quota-boost restriction;
  8. the prompt-guidance block;
  9. import hygiene — `gen.tiers` is a leaf.

Three readings this file had to resolve (the contract is quoted in each
failure message that depends on one):

  a. `TIER_TABLE` rows are addressed through `tier_row()`, which accepts
     either a mapping keyed by tier name or any iterable of `TierRow`s: the
     contract writes `TIER_TABLE[tier].guidance` but freezes only the ROWS,
     so the container shape is left to the implementer.
  b. Pin 7's "strictly greater in at least one aggregate count" is measured
     over TWO aggregates (total occurrences of the quota term across every
     drawn seed set, and the number of ideas carrying it) and over a WIDENED
     seed range. `state.action_lag` carries an inverse-occurrence weight of
     1/17 against a free-slot population summing to ~10.9, i.e. p≈0.005 per
     free slot against p≈0.016 boosted; at the contract's 20 seeds the
     expected difference is ~1 draw, which is not a measurement. The
     suppression half (the exact-equality one) runs at the contract's seeds
     0..19; the "the boost is real" half runs at 0..199, under the same
     widen-until-it-measures licence pin 5 grants in as many words.
  c. "bad action enum" is exercised with a value no plausible enum contains
     rather than with a guess at the enum's members, which the contract does
     not freeze (it freezes only the defaults `warn` / `off` / `off`).

`gen.tiers` is imported lazily inside a fixture so that a missing module
fails those tests with the contract's own words instead of erroring the whole
file at collection — the s0-only pins (the replay above all) stay runnable.
"""

from __future__ import annotations

import csv
import dataclasses
import importlib
import json
import re
import subprocess
import sys
import warnings
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

import pytest

from gen import s0_ideas
from gen.config import REPO_ROOT, load_config
from gen.s0_ideas import IDEA_STRUCTURAL_FIELDS, build_prose_prompt, check_config, load_vocab

CONFIG_PATH = "config/b002-triple.yaml"

# Canon, relative to the config's `duckwm_docs` root (READ-ONLY; never an
# absolute path from this repo).
DIFFICULTY_MODEL_REL = "design/difficulty-model.md"
MATRIX_REL = "mechanics/game-term-matrix.csv"
TIER_TABLE_HEAD = "3.3 the tier table"  # matched case-insensitively on a '###' line

TIER_NAMES = ("t1", "t2", "t3")

# The b002 batch, replayed in pin 3.  `out/` is gitignored, so the artifacts
# are local run output: their absence skips the replay rather than failing it.
B002_BATCH_ID = "b002-triple"
B002_SEED = 2
B002_IDEAS_DIR = REPO_ROOT / "out" / "ideas" / B002_BATCH_ID
HISTORY_NAME = "dedupe-history.jsonl"
REAL_HISTORY = REPO_ROOT / "out" / "ideas" / HISTORY_NAME

# Frozen surface, as the contract spells it.  These are quoted FROM THE
# CONTRACT (they are the thing under test), never read off the implementation.
EXPECTED_REFUSAL_ORDINAL = {"visible": 0, "free": 1, "silent-charged": 2}
EXPECTED_GOAL_LEGIBLE_ORDINAL = {"obvious": 0, "inferable": 1, "opaque": 2}
EXPECTED_DANGER_TELL_ORDINAL = {
    "unique-hue": 0,
    "texture": 1,
    "absence": 1,
    "camouflage": 2,
    "none": 2,
}
TIER_ROW_FIELDS = (
    "tier",
    "label",
    "refusal_max",
    "goal_legible_max",
    "danger_tell_max",
    "lever_max",
    "core_terms",
    "seed_range",
    "intro_cap",
    "guidance",
)
# tier -> (label, refusal_max, goal_legible_max, danger_tell_max, lever_max,
#          core_terms, seed_range, intro_cap)
EXPECTED_ROWS = {
    "t1": ("entry", 0, 0, 0, 0, (2, 3), (2, 3), 1),
    "t2": ("core", 1, 1, 1, 1, (3, 5), (2, 4), None),
    "t3": ("official-grade", 2, 2, 2, 3, (4, 6), (3, 4), None),
}
EXPECTED_TERM_BUDGETS = {"t1": 6, "t2": 8, "t3": 10}
OVERRIDE_PREFIX = "COMPLEXITY OVERRIDE (arc-agi-games tier workstream;"
OVERRIDE_MARK = "COMPLEXITY OVERRIDE"
POLICY_DEFAULTS = {
    "prompt_guidance": False,
    "term_budget": None,
    "term_budget_action": "warn",
    "knob_defaults_action": "off",
    "intro_pacing_action": "off",
    "seed_terms": None,
    "term_bias": None,
    "quota_boost_tiers": None,
}

# The canon rows pin 1 reads, keyed by their first table cell.
CANON_ROW_KEYS = ("refusal", "goal_legible", "danger_tell", "deceptions", "terms", "g draw")
LEADING_RANGE_RE = re.compile(r"^\s*(\d+)\s*[-–]\s*(\d+)")

# Pin 5/6/7 measurement sizes.  See reading (b) in the module docstring for
# why pin 7's "boost is real" half runs wider than the contract's 20 seeds.
SEED_TERMS_SEEDS = 10
BIAS_SEEDS = 20
QUOTA_SUPPRESSED_SEEDS = 20
QUOTA_BOOST_SEEDS = 200
QUOTA_TERM = "state.action_lag"

# A fake prose reply that clears S0's prose gate (title <= 90 chars / 10
# words, body >= 400 chars, no process narration, no tool fragments).  No
# sampler call in this file ever reaches a driver.
FAKE_PROSE = "Fixture Yard\n\n" + (
    "A small square yard holds a handful of coloured blocks and one moving "
    "marker, and every level asks the player to bring the marker to the lit "
    "pad without disturbing the blocks that share its colour. "
) * 4


# --------------------------------------------------------------------------
# lazy access to the module under test
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def tiers():
    """`gen.tiers`, or a loud skip-free failure naming the contract."""
    try:
        return importlib.import_module("gen.tiers")
    except ModuleNotFoundError as exc:  # pragma: no cover - the pre-landing state
        pytest.fail(
            f"gen.tiers does not import ({exc}) — the b003 contract freezes this module's "
            "public surface (REFUSAL_ORDINAL, GOAL_LEGIBLE_ORDINAL, DANGER_TELL_ORDINAL, "
            "TierRow, TIER_TABLE, DEFAULT_TERM_BUDGETS, COMPLEXITY_OVERRIDE, TierPolicy, "
            "tier_policy); every pin below reads it"
        )


def attr(module, name: str):
    """`getattr` whose failure message names the frozen surface."""
    value = getattr(module, name, None)
    if value is None and not hasattr(module, name):
        pytest.fail(
            f"gen.tiers exposes no {name!r} — it is part of the frozen public surface the "
            "b003 contract pins; renaming it is a contract change, not an implementation "
            "detail"
        )
    return value


def tier_row(module, tier: str):
    """One `TIER_TABLE` row, whatever container the implementer chose.

    Reading (a): the contract writes ``TIER_TABLE[tier].guidance`` but freezes
    only the ROWS, so a mapping keyed by tier name and a sequence of rows are
    both honoured here.
    """
    table = attr(module, "TIER_TABLE")
    if isinstance(table, Mapping):
        assert tier in table, (
            f"TIER_TABLE has no row for {tier!r} (keys {sorted(table)}) — the contract "
            f"freezes exactly three rows, {list(TIER_NAMES)}"
        )
        return table[tier]
    rows = [row for row in table if getattr(row, "tier", None) == tier]
    assert len(rows) == 1, (
        f"TIER_TABLE carries {len(rows)} rows whose .tier is {tier!r} — the contract "
        f"freezes exactly one row per tier and exactly three rows, {list(TIER_NAMES)}"
    )
    return rows[0]


def as_pair(value) -> tuple:
    """`(lo, hi)` from a tuple, list or range-like — shape is not frozen."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (value[0], value[1])
    return value


# --------------------------------------------------------------------------
# config / canon fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_cfg() -> dict:
    """The b002 config: the one every knob-off pin replays."""
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="session")
def docs_root(base_cfg: dict) -> Path:
    return Path(base_cfg["duckwm_docs"]).resolve()


@pytest.fixture(scope="session")
def vocab(base_cfg: dict) -> dict[str, dict]:
    """The closed 71-term vocabulary with its corpus counts."""
    return load_vocab(base_cfg)


@pytest.fixture(scope="session")
def canon_tiers(docs_root: Path) -> dict:
    """The parsed §3.3 tier table: `{'header': [...], 'rows': {key: [t1, t2, t3]}}`."""
    return parse_canon_tier_table(docs_root / DIFFICULTY_MODEL_REL)


def parse_canon_tier_table(path: Path) -> dict:
    """Parse the markdown table under the `### … 3.3 The tier table` head.

    Rows are keyed by their FIRST cell (refusal / goal_legible / … / g draw)
    and carry the three tier cells in order.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line.lstrip().startswith("#") and TIER_TABLE_HEAD in line.lower()
    ]
    assert len(starts) == 1, (
        f"{path} carries {len(starts)} headings containing {TIER_TABLE_HEAD!r}, expected "
        "exactly one — pin 1 locates the signed tier table by that heading, so canon "
        "moving it has to be re-adjudicated before the frozen rows mean anything"
    )

    header: list[str] | None = None
    rows: dict[str, list[str]] = {}
    for line in lines[starts[0] + 1 :]:
        stripped = line.strip()
        if stripped.startswith("#"):
            break
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue  # the |---|---| separator
        if header is None:
            header = cells
            continue
        rows[cells[0].strip().lower()] = cells[1:]

    assert header is not None and rows, (
        f"no markdown table found under the §3.3 head in {path} — pin 1 parses that "
        "table; if canon changed shape the parser and the frozen rows both have to be "
        "re-derived"
    )
    missing = [key for key in CANON_ROW_KEYS if key not in rows]
    assert not missing, (
        f"the §3.3 tier table in {path} has no rows {missing} (found {sorted(rows)}) — "
        f"pin 1 reads the knobs by their first cell, {list(CANON_ROW_KEYS)}"
    )
    for key, cells in rows.items():
        assert len(cells) == 3, (
            f"the §3.3 row {key!r} carries {len(cells)} tier cells, not three — the table "
            "is t1 | t2 | t3 and the frozen rows are read off it positionally"
        )
    return {"header": header, "rows": rows, "path": path}


@pytest.fixture(scope="session")
def official_n_terms(docs_root: Path) -> list[int]:
    """The 25 officials' `n_terms`, sorted ascending, read off the matrix."""
    path = docs_root / MATRIX_REL
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    for column in ("slug", "corpus", "n_terms"):
        assert column in fieldnames, (
            f"{path} has no {column!r} column (header starts {fieldnames[:6]}) — pin 2 "
            "reads the officials' term counts out of this header"
        )
    labels = sorted({(row.get("corpus") or "").strip() for row in rows})
    assert "official" in labels, (
        f"{path} carries no rows whose corpus is 'official' (labels found: {labels}) — "
        "pin 2 anchors the default term budgets on the officials' own term counts"
    )
    officials = [row for row in rows if (row.get("corpus") or "").strip() == "official"]
    assert len(officials) == 25, (
        f"{path} carries {len(officials)} 'official' rows, not the 25 signed officials — "
        "the whole budget anchor is those 25 games' measured term counts"
    )
    return sorted(int(row["n_terms"]) for row in officials)


# --------------------------------------------------------------------------
# sampler fixtures: no driver, no writes outside tmp_path
# --------------------------------------------------------------------------


def _history_attrs() -> list[str]:
    """Every module-level Path constant that points at the dedupe history."""
    return [
        name
        for name, value in vars(s0_ideas).items()
        if isinstance(value, Path) and value.name == HISTORY_NAME
    ]


def _install_history(path: Path) -> None:
    """Point the sampler's history at `path` (created empty if absent)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for name in _history_attrs():
        setattr(s0_ideas, name, path)


@pytest.fixture(autouse=True)
def _isolate_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`sample_batch` appends to `out/ideas/dedupe-history.jsonl`.

    Nothing here may write outside `tmp_path`, so every module-level Path
    constant naming that file is redirected under the test's own tmp dir
    (whatever the implementer called it), and the real file is snapshotted and
    restored either way so the repo is byte-identical after the run.
    """
    names = _history_attrs()
    assert names, (
        "gen.s0_ideas exposes no module-level Path constant pointing at "
        f"{HISTORY_NAME!r} — this suite redirects it so that no test writes into the "
        "repo's real out/ tree; if the history moved, this fixture has to move with it"
    )
    before = REAL_HISTORY.read_bytes() if REAL_HISTORY.is_file() else None
    parent_existed = REAL_HISTORY.parent.is_dir()

    redirect = tmp_path / "history" / HISTORY_NAME
    redirect.parent.mkdir(parents=True, exist_ok=True)
    for name in names:
        monkeypatch.setattr(s0_ideas, name, redirect, raising=False)

    yield

    if before is None:
        if REAL_HISTORY.is_file():
            REAL_HISTORY.unlink()
        if not parent_existed and REAL_HISTORY.parent.is_dir():
            try:
                REAL_HISTORY.parent.rmdir()
            except OSError:
                pass
    elif not REAL_HISTORY.is_file() or REAL_HISTORY.read_bytes() != before:
        # Restore ONLY a real change: rewriting identical bytes still moved the
        # file's mtime on every run (contract OS-2 FRONT C.2, the hermeticity fix).
        REAL_HISTORY.write_bytes(before)


@pytest.fixture
def draw(tmp_path: Path):
    """Run `sample_batch` with a fake runner, a tmp out dir and a FRESH history.

    Each call gets its own empty dedupe history, so the paired runs the
    statistical pins compare are independent draws rather than a sequence that
    can desync on a cross-batch collision. Returns the written idea dicts, in
    filename order — the pins read what landed ON DISK.
    """
    seen: set[str] = set()

    def run(cfg: Mapping, *, batch_id: str, seed: int) -> list[dict]:
        assert batch_id not in seen, f"batch id {batch_id!r} reused inside one test"
        seen.add(batch_id)
        out_dir = tmp_path / "ideas" / batch_id
        _install_history(tmp_path / "history" / batch_id / HISTORY_NAME)
        with warnings.catch_warnings():
            # b002 floors (8) exceed batch.size (3) and the config carries
            # quotas, so S0 warns once per batch by design — pin 7 says so in
            # as many words. Warnings are not what any pin here measures.
            warnings.simplefilter("ignore")
            s0_ideas.sample_batch(
                cfg,
                batch_id=batch_id,
                seed=seed,
                prose_runner=lambda _prompt: FAKE_PROSE,
                out_dir=out_dir,
            )
        return read_ideas(out_dir)

    return run


def read_ideas(out_dir: Path) -> list[dict]:
    """Every `idea-NNN.json` under `out_dir`, in filename order."""
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(out_dir.glob("idea-*.json"))
    ]


def with_tiers(cfg: Mapping, block: Mapping | None, *, sequence: list[str] | None = None) -> dict:
    """A config copy carrying a `tiers` policy block and/or a tier sequence."""
    out = deepcopy(dict(cfg))
    if block is None:
        out.pop("tiers", None)
    else:
        out["tiers"] = deepcopy(dict(block))
    if sequence is not None:
        out["batch"]["tier_sequence"] = list(sequence)
        out["batch"]["size"] = len(sequence)
    return out


def all_t1(cfg: Mapping) -> list[str]:
    """`['t1', …]`, one per configured batch slot."""
    return ["t1"] * int(cfg["batch"]["size"])


def seed_term_lists(ideas: list[dict]) -> list[list[str]]:
    return [list(idea["seed_terms"]) for idea in ideas]


# --------------------------------------------------------------------------
# Frozen public surface
# --------------------------------------------------------------------------


def test_ordinal_maps_are_the_frozen_ceilings(tiers) -> None:
    """The three knob orderings, including the two ties the contract fixes."""
    assert dict(attr(tiers, "REFUSAL_ORDINAL")) == EXPECTED_REFUSAL_ORDINAL, (
        "REFUSAL_ORDINAL is not the frozen ordering — the ordinals are what a tier's "
        "refusal_max CEILING means, so a renumbering silently re-tiers every game"
    )
    assert dict(attr(tiers, "GOAL_LEGIBLE_ORDINAL")) == EXPECTED_GOAL_LEGIBLE_ORDINAL, (
        "GOAL_LEGIBLE_ORDINAL is not the frozen ordering (obvious < inferable < opaque)"
    )
    assert dict(attr(tiers, "DANGER_TELL_ORDINAL")) == EXPECTED_DANGER_TELL_ORDINAL, (
        "DANGER_TELL_ORDINAL is not the frozen ordering — note the two deliberate TIES: "
        "texture and absence both sit at 1, camouflage and none both at 2, because canon "
        "§3.3 lists them as alternatives inside one tier cell"
    )


def test_tier_row_is_a_frozen_dataclass_with_the_signed_fields(tiers) -> None:
    """`TierRow` is frozen and carries exactly the ten contracted fields."""
    row_cls = attr(tiers, "TierRow")
    assert dataclasses.is_dataclass(row_cls), (
        f"TierRow is {row_cls!r}, not a dataclass — the contract freezes it as a frozen "
        "dataclass so a row cannot be mutated after import"
    )
    params = getattr(row_cls, "__dataclass_params__", None)
    assert params is not None and params.frozen, (
        "TierRow is a dataclass but not frozen — TIER_TABLE is module-level canon shared "
        "by every worker in a batch; a mutable row is a cross-slot data race"
    )
    names = tuple(field.name for field in dataclasses.fields(row_cls))
    assert names == TIER_ROW_FIELDS, (
        f"TierRow's fields are {names}, not the frozen {TIER_ROW_FIELDS} — the field set "
        "and its order are the contract's, and downstream stages read them by name"
    )


def test_tier_table_carries_the_three_frozen_rows(tiers) -> None:
    """Every frozen cell of t1/t2/t3, including the intro cap asymmetry."""
    wrong: list[str] = []
    for tier, expected in EXPECTED_ROWS.items():
        row = tier_row(tiers, tier)
        actual = (
            row.label,
            row.refusal_max,
            row.goal_legible_max,
            row.danger_tell_max,
            row.lever_max,
            as_pair(row.core_terms),
            as_pair(row.seed_range),
            row.intro_cap,
        )
        if actual != expected:
            wrong.append(f"{tier}: {actual!r} != {expected!r}")
        assert row.tier == tier, f"TIER_TABLE row for {tier!r} reports .tier {row.tier!r}"
        assert isinstance(row.guidance, str) and row.guidance.strip(), (
            f"TIER_TABLE[{tier!r}].guidance is {row.guidance!r} — pin 8 ships this string "
            "into the prose prompt, so it has to be real non-empty text"
        )

    assert not wrong, (
        f"TIER_TABLE diverges from the frozen rows: {wrong} — each tuple is (label, "
        "refusal_max, goal_legible_max, danger_tell_max, lever_max, core_terms, "
        "seed_range, intro_cap); note t1 alone caps introductions (intro_cap 1) and t3's "
        "lever_max is 3, not 2"
    )


def test_default_term_budgets_and_the_override_header(tiers) -> None:
    """The budgets map and the COMPLEXITY OVERRIDE prefix."""
    assert dict(attr(tiers, "DEFAULT_TERM_BUDGETS")) == EXPECTED_TERM_BUDGETS, (
        "DEFAULT_TERM_BUDGETS is not the frozen map — pin 2 shows these three numbers are "
        "the 25 officials' own n_terms order statistics, so changing them detaches the "
        "budgets from the corpus they were measured on"
    )
    override = attr(tiers, "COMPLEXITY_OVERRIDE")
    assert isinstance(override, str) and override.startswith(OVERRIDE_PREFIX), (
        f"COMPLEXITY_OVERRIDE is {override!r:.120} — the contract freezes its opening as "
        f"{OVERRIDE_PREFIX!r}: the prose prompt's override block has to announce which "
        "workstream is overriding the vendored doctrine"
    )


def test_tier_policy_is_none_without_a_tiers_block(base_cfg: dict, tiers) -> None:
    """No `tiers` key ⇒ no policy: the knobs are off by construction."""
    policy = attr(tiers, "tier_policy")
    assert "tiers" not in base_cfg, (
        f"{CONFIG_PATH} grew a top-level 'tiers' block — the knob-off pins all rest on "
        "this config having none (batch.tiers, the mix weights, is a different key)"
    )
    assert policy(base_cfg) is None, (
        "tier_policy(cfg) returned a policy for a config with no 'tiers' block — absent "
        "means OFF, and every b001/b002 config on disk is in exactly that state"
    )


def test_empty_tiers_block_yields_the_documented_defaults(base_cfg: dict, tiers) -> None:
    """`tiers: {}` ⇒ a real policy, every knob at its contracted default."""
    policy = attr(tiers, "tier_policy")(with_tiers(base_cfg, {}))
    assert policy is not None, (
        "tier_policy(cfg) returned None for an explicit empty 'tiers: {}' block — an "
        "empty block is an opt-in with defaults, which is not the same as the key being "
        "absent"
    )
    assert dataclasses.is_dataclass(policy), (
        f"tier_policy returned {policy!r}, not a TierPolicy dataclass instance"
    )
    wrong = {
        name: getattr(policy, name, "<missing>")
        for name, expected in POLICY_DEFAULTS.items()
        if getattr(policy, name, "<missing>") != expected
    }
    assert not wrong, (
        f"the default policy's knobs are {wrong}, expected {POLICY_DEFAULTS} — the "
        "defaults are the contract's: guidance off, no budget, budget action 'warn', the "
        "other two actions 'off', and the three per-tier knobs unset"
    )


def test_term_budget_true_expands_to_the_officials_anchored_defaults(
    base_cfg: dict, tiers
) -> None:
    """`term_budget: true` is sugar for DEFAULT_TERM_BUDGETS; a full map passes."""
    policy_fn = attr(tiers, "tier_policy")

    shorthand = policy_fn(with_tiers(base_cfg, {"term_budget": True}))
    assert shorthand.term_budget == dict(attr(tiers, "DEFAULT_TERM_BUDGETS")), (
        f"term_budget: true resolved to {shorthand.term_budget!r} — the contract makes it "
        "shorthand for DEFAULT_TERM_BUDGETS, so downstream never has to special-case a "
        "bool"
    )

    explicit = {"t1": 4, "t2": 7, "t3": 9}
    accepted = policy_fn(with_tiers(base_cfg, {"term_budget": dict(explicit)}))
    assert accepted.term_budget == explicit, (
        f"an explicit full budget map resolved to {accepted.term_budget!r}, not "
        f"{explicit!r} — a complete map of ints >= 4 is accepted as written"
    )


@pytest.mark.parametrize(
    ("budget", "why"),
    [
        ({"t1": 6, "t2": 8}, "a PARTIAL map (t3 unset) leaves one tier silently unbudgeted"),
        ({"t1": 3, "t2": 8, "t3": 10}, "a budget of 3 sits under the officials' own minimum of 4"),
    ],
)
def test_term_budget_rejects_partial_maps_and_under_four(
    base_cfg: dict, tiers, budget: dict, why: str
) -> None:
    """Partial maps and values below 4 are ValueErrors, not quiet defaults."""
    with pytest.raises(ValueError):
        attr(tiers, "tier_policy")(with_tiers(base_cfg, {"term_budget": budget}))
        pytest.fail(f"tier_policy accepted term_budget {budget!r} — {why}")


@pytest.mark.parametrize(
    ("block", "why"),
    [
        (
            {"prompt_guidanse": True},
            "an unknown key in the block (here a typo) must not be silently ignored",
        ),
        ({"term_budget_action": "detonate"}, "an action outside the enum"),
        ({"knob_defaults_action": "detonate"}, "an action outside the enum"),
        ({"intro_pacing_action": "detonate"}, "an action outside the enum"),
        ({"seed_terms": {"t1": [1, 3]}}, "a seed range below the sampler's floor of 2"),
        ({"seed_terms": {"t1": [2, 5]}}, "a seed range above the sampler's ceiling of 4"),
        ({"seed_terms": {"t1": [4, 2]}}, "a seed range with lo > hi"),
        ({"term_bias": {"t1": "vibes"}}, "a bias outside {'rare', 'common-official'}"),
        ({"quota_boost_tiers": ["t1", "t4"]}, "a tier name outside {t1, t2, t3}"),
        ({"g_central": True}, "the v2 g-central knob, which this version does not ship"),
    ],
)
def test_tier_policy_rejects_the_contracted_bad_blocks(
    base_cfg: dict, tiers, block: dict, why: str
) -> None:
    """Every reject the contract enumerates raises ValueError, loudly.

    Reading (c): the action enum's MEMBERS are not frozen (only the defaults
    'warn'/'off'/'off' are), so the bad-enum cases use a value no plausible
    enum contains rather than guessing at the members.
    """
    with pytest.raises(ValueError):
        attr(tiers, "tier_policy")(with_tiers(base_cfg, block))
        pytest.fail(
            f"tier_policy accepted the block {block!r} — {why}; every knob here changes "
            "what a batch DRAWS, so a typo that reads as 'off' is a silently wrong batch"
        )


def test_g_central_true_is_refused_by_name_and_false_is_accepted(base_cfg: dict, tiers) -> None:
    """`g_central: true` names v2 in its message; `false` is a legal no-op."""
    policy_fn = attr(tiers, "tier_policy")
    with pytest.raises(ValueError) as excinfo:
        policy_fn(with_tiers(base_cfg, {"g_central": True}))
    assert "v2" in str(excinfo.value).lower(), (
        f"g_central: true raised {str(excinfo.value)!r} without naming v2 — the contract "
        "requires the message to point at the version that ships the central-g draw, "
        "because otherwise the operator's only signal is that a signed knob 'failed'"
    )

    policy = policy_fn(with_tiers(base_cfg, {"g_central": False}))
    assert policy is not None, (
        "g_central: false was refused — it is the knob written down and turned OFF, which "
        "is exactly how a config records a decision it is not yet acting on"
    )


# --------------------------------------------------------------------------
# Pin 1 — canon drift
# --------------------------------------------------------------------------


def test_canon_term_ranges_match_the_frozen_core_terms(canon_tiers: dict, tiers) -> None:
    """The §3.3 `terms` cell's leading range IS `TierRow.core_terms`."""
    cells = canon_tiers["rows"]["terms"]
    wrong = []
    for index, tier in enumerate(TIER_NAMES):
        match = LEADING_RANGE_RE.match(cells[index])
        assert match, (
            f"the §3.3 'terms' cell for {tier} reads {cells[index]!r} and does not open "
            "with a 'lo-hi' range — pin 1 reads the frozen core_terms straight off canon"
        )
        canon_range = (int(match.group(1)), int(match.group(2)))
        actual = as_pair(tier_row(tiers, tier).core_terms)
        if actual != canon_range:
            wrong.append(f"{tier}: TierRow {actual!r} != canon {canon_range!r} ({cells[index]!r})")

    assert not wrong, (
        f"TIER_TABLE.core_terms has drifted from design/difficulty-model.md §3.3: {wrong} "
        "— canon is the signed source for the tier table and the engine is a transcription "
        "of it; a drift here means the engine is enforcing an unsigned difficulty model"
    )


def test_canon_deception_cells_match_the_frozen_lever_max(canon_tiers: dict, tiers) -> None:
    """t1 none/0, t2 '1…'/1, t3 '2-3…'/3 — the one row where canon and code differ."""
    cells = canon_tiers["rows"]["deceptions"]
    t1_cell, t2_cell, t3_cell = (cell.strip() for cell in cells)

    assert "none" in t1_cell.lower(), (
        f"the §3.3 deceptions cell for t1 reads {t1_cell!r}, no longer 'none' — t1's "
        "lever_max of 0 is a transcription of that word"
    )
    assert tier_row(tiers, "t1").lever_max == 0, (
        f"t1.lever_max is {tier_row(tiers, 't1').lever_max}, not 0, while canon declares "
        "no deceptions at entry tier"
    )
    assert t2_cell.startswith("1"), (
        f"the §3.3 deceptions cell for t2 reads {t2_cell!r} and no longer opens with '1'"
    )
    assert tier_row(tiers, "t2").lever_max == 1, (
        f"t2.lever_max is {tier_row(tiers, 't2').lever_max}, not 1, while canon declares "
        "one declared deception at core tier"
    )
    assert t3_cell.startswith("2-3"), (
        f"the §3.3 deceptions cell for t3 reads {t3_cell!r} and no longer opens with '2-3'"
    )
    assert tier_row(tiers, "t3").lever_max == 3, (
        f"t3.lever_max is {tier_row(tiers, 't3').lever_max}, not 3 — canon's t3 cell is a "
        "RANGE ('2-3 declared'), and lever_max is its ceiling, not its floor"
    )


@pytest.mark.parametrize(
    ("row_key", "ordinal_name", "field", "keywords"),
    [
        ("refusal", "REFUSAL_ORDINAL", "refusal_max", ("visible", "free", "silent-charged")),
        (
            "goal_legible",
            "GOAL_LEGIBLE_ORDINAL",
            "goal_legible_max",
            ("obvious", "inferable", "opaque"),
        ),
        (
            "danger_tell",
            "DANGER_TELL_ORDINAL",
            "danger_tell_max",
            ("unique-hue", "texture", "camouflage"),
        ),
    ],
)
def test_canon_knob_cells_match_the_frozen_ceilings(
    canon_tiers: dict, tiers, row_key: str, ordinal_name: str, field: str, keywords: tuple
) -> None:
    """Each §3.3 knob cell names the value whose ordinal IS that tier's ceiling.

    The per-tier keyword is the one the contract nominates for that cell:
    t1's own value, t2's permitted maximum ('free', 'inferable', 'texture')
    and t3's headline ('silent-charged', 'opaque', 'camouflage' — the last
    tied with 'none' at the same ordinal).
    """
    ordinal = dict(attr(tiers, ordinal_name))
    cells = canon_tiers["rows"][row_key]
    wrong = []
    for index, tier in enumerate(TIER_NAMES):
        cell = cells[index].lower()
        keyword = keywords[index]
        assert keyword in cell, (
            f"the §3.3 {row_key} cell for {tier} reads {cells[index]!r} and no longer "
            f"names {keyword!r} — pin 1 derives the frozen ceiling from that word"
        )
        assert keyword in ordinal, (
            f"{ordinal_name} has no entry for {keyword!r}, which canon's {row_key} cell "
            f"for {tier} names — the ordinal map has to cover every value canon uses"
        )
        actual = getattr(tier_row(tiers, tier), field)
        if actual != ordinal[keyword]:
            wrong.append(f"{tier}: {field}={actual!r} != {ordinal_name}[{keyword!r}]="
                         f"{ordinal[keyword]!r}")

    assert not wrong, (
        f"the frozen {field} ceilings disagree with design/difficulty-model.md §3.3: "
        f"{wrong} — the tier table in the engine is a transcription of the signed one, and "
        "the ordinals are how a prose cell becomes a comparable ceiling"
    )


def test_canon_tier_header_names_the_frozen_labels(canon_tiers: dict, tiers) -> None:
    """t1 (entry) / t2 (core) / t3 (official-grade), straight off the header."""
    header = canon_tiers["header"]
    wrong = []
    for index, tier in enumerate(TIER_NAMES, start=1):
        cell = header[index].lower()
        label = tier_row(tiers, tier).label
        if label.lower() not in cell:
            wrong.append(f"{tier}: TierRow.label {label!r} not in canon header cell {cell!r}")

    assert not wrong, (
        f"TIER_TABLE labels have drifted from the §3.3 header: {wrong} — the header names "
        "the three tiers (entry / core / official-grade) and the labels are its "
        "transcription"
    )


# --------------------------------------------------------------------------
# Pin 2 — the officials anchor
# --------------------------------------------------------------------------


def test_default_term_budgets_are_the_officials_order_statistics(
    official_n_terms: list[int], tiers
) -> None:
    """4 / 6 / 8 / 10 over the 25 officials, and the budgets sit on three of them."""
    counts = official_n_terms
    assert (counts[0], counts[6], counts[12], counts[-1]) == (4, 6, 8, 10), (
        f"the 25 officials' sorted n_terms are {counts} — pin 2 freezes min=4, "
        "sorted[6]=6, sorted[12]=8 (the median) and max=10; if the matrix moved, the "
        "budgets stop being a measurement and become a preference"
    )
    assert dict(attr(tiers, "DEFAULT_TERM_BUDGETS")) == {
        "t1": counts[6],
        "t2": counts[12],
        "t3": counts[-1],
    }, (
        "DEFAULT_TERM_BUDGETS is not {t1: sorted[6], t2: sorted[12], t3: max} over the "
        f"officials' n_terms {counts} — the three budgets are lower-quartile-ish, median "
        "and maximum of the corpus the generated games are graded against, which is the "
        "whole justification for the numbers"
    )


# --------------------------------------------------------------------------
# Pin 3 — knob-off replay (the hardest pin)
# --------------------------------------------------------------------------


def test_b002_config_carries_no_tier_policy(base_cfg: dict, tiers) -> None:
    """Pin 3(a): the shipped batch config resolves to no policy at all."""
    assert attr(tiers, "tier_policy")(base_cfg) is None, (
        f"tier_policy({CONFIG_PATH}) is not None — the tier work is opt-in, and the two "
        "configs already on disk must keep resolving to 'no policy' or every shipped "
        "batch changes meaning retroactively"
    )


def test_knob_off_b002_replay_is_bit_identical(base_cfg: dict, tmp_path: Path) -> None:
    """Pin 3(b): seed 2 redraws b002's ideas, structurally, field for field.

    The strongest available proof that the tier work changed no draw: the
    ideas on disk were produced by the pre-tier sampler, and the same config
    and seed must still reproduce their `IDEA_STRUCTURAL_FIELDS`. Prose is
    excluded by that constant's own definition — it is the live field.
    """
    shipped = sorted(B002_IDEAS_DIR.glob("idea-*.json"))
    if not shipped:
        pytest.skip(
            f"no shipped b002 idea files under {B002_IDEAS_DIR} (out/ is gitignored, so "
            "they are local run output) — the replay pin needs the artifacts it replays"
        )

    # The window the original draw saw: the real history, minus this batch's
    # own rows, which `load_recent_keys` excludes by contract. Copied, never
    # written through.
    history = tmp_path / "replay-history" / HISTORY_NAME
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_bytes(REAL_HISTORY.read_bytes() if REAL_HISTORY.is_file() else b"")
    _install_history(history)

    out_dir = tmp_path / "replay"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s0_ideas.sample_batch(
            base_cfg,
            batch_id=B002_BATCH_ID,
            seed=B002_SEED,
            prose_runner=lambda _prompt: FAKE_PROSE,
            out_dir=out_dir,
        )
    replayed = sorted(out_dir.glob("idea-*.json"))

    assert [path.name for path in replayed] == [path.name for path in shipped], (
        f"the replay wrote {[p.name for p in replayed]} against the shipped "
        f"{[p.name for p in shipped]} — the batch is paired by filename, so a different "
        "slot count is already a changed draw"
    )
    diverged = []
    for fresh_path, shipped_path in zip(replayed, shipped, strict=True):
        fresh = json.loads(fresh_path.read_text(encoding="utf-8"))
        original = json.loads(shipped_path.read_text(encoding="utf-8"))
        for field in IDEA_STRUCTURAL_FIELDS:
            if fresh.get(field) != original.get(field):
                diverged.append(
                    f"{shipped_path.name}.{field}: replay {fresh.get(field)!r} != shipped "
                    f"{original.get(field)!r}"
                )

    assert not diverged, (
        f"the b002 replay diverges structurally from the shipped batch: {diverged} — with "
        "no 'tiers' block the tier work must consume no rng and change no weight, so "
        f"{CONFIG_PATH} at seed {B002_SEED} has to redraw the batch that is already on "
        "disk, term for term"
    )


def test_policy_none_prompt_is_todays_prompt(base_cfg: dict, tiers) -> None:
    """Pin 3(c): `policy=None` and an omitted `policy` build the same bytes."""
    kwargs = {
        "seed_terms": ["goal.reach", "gate.phase"],
        "primary": "reach_goal",
        "failure_family": None,
        "tier": "t1",
        "hazardless": True,
        "locus": "mover",
    }
    omitted = build_prose_prompt(base_cfg, **kwargs)
    explicit = build_prose_prompt(base_cfg, policy=None, **kwargs)

    assert explicit == omitted, (
        "build_prose_prompt(policy=None) does not produce the same bytes as the call with "
        "the argument omitted — the contract makes None the default AND today's "
        "behaviour, so the two spellings are the same prompt"
    )
    guidance = [tier_row(tiers, tier).guidance for tier in TIER_NAMES]
    for prompt, label in ((omitted, "omitted"), (explicit, "policy=None")):
        assert OVERRIDE_MARK not in prompt, (
            f"the {label} prompt carries {OVERRIDE_MARK!r} — with no policy the prose "
            "prompt is byte-for-byte the pre-tier one; the override block is the opt-in"
        )
        leaked = [text for text in guidance if text in prompt]
        assert not leaked, (
            f"the {label} prompt carries tier guidance {leaked!r:.200} — guidance ships "
            "only under prompt_guidance, never by default"
        )


# --------------------------------------------------------------------------
# Pin 4 — batch.tier_sequence
# --------------------------------------------------------------------------


def test_tier_sequence_pins_each_slot(base_cfg: dict, draw) -> None:
    """`[t1, t2]` ⇒ slot 1 is t1 and slot 2 is t2, in filename order."""
    cfg = with_tiers(base_cfg, None, sequence=["t1", "t2"])
    cfg["batch"]["id"] = "b003-seq"
    ideas = draw(cfg, batch_id="b003-seq", seed=7)

    assert [idea["tier"] for idea in ideas] == ["t1", "t2"], (
        f"batch.tier_sequence [t1, t2] produced tiers {[i['tier'] for i in ideas]} — the "
        "sequence pins the tier PER SLOT, which is how a batch buys a deliberate spread "
        "instead of a weighted draw that can hand back three t1s"
    )


@pytest.mark.parametrize(
    ("sequence", "size", "why"),
    [
        (["t1", "t2", "t3"], 2, "a sequence longer than batch.size leaves a slot unaccounted"),
        (["t1"], 2, "a sequence shorter than batch.size leaves a slot undecided"),
        (["t1", "tX"], 2, "an unknown tier name is a typo that must not read as a default"),
    ],
)
def test_tier_sequence_is_rejected_before_any_spend(
    base_cfg: dict, vocab: dict, tmp_path: Path, sequence: list[str], size: int, why: str
) -> None:
    """A bad sequence raises from check_config, with nothing written."""
    cfg = deepcopy(base_cfg)
    cfg["batch"]["id"] = "b003-badseq"
    cfg["batch"]["size"] = size
    cfg["batch"]["tier_sequence"] = list(sequence)

    with pytest.raises(ValueError):
        check_config(cfg, vocab)
        pytest.fail(
            f"check_config accepted batch.tier_sequence {sequence!r} at batch.size {size} "
            f"— {why}, and check_config is the stage that exists to raise EVERY strict "
            "config error before a single prose token is spent"
        )

    out_dir = tmp_path / "rejected"
    _install_history(tmp_path / "rejected-history" / HISTORY_NAME)
    with pytest.raises(ValueError), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s0_ideas.sample_batch(
            cfg,
            batch_id="b003-badseq",
            seed=3,
            prose_runner=lambda _prompt: FAKE_PROSE,
            out_dir=out_dir,
        )
    written = sorted(out_dir.glob("*")) if out_dir.exists() else []
    assert not written, (
        f"sample_batch wrote {[p.name for p in written]} before rejecting the bad "
        f"tier_sequence {sequence!r} — a half-written batch directory is worse than none, "
        "and the config check runs ahead of every draw for exactly this reason"
    )


# --------------------------------------------------------------------------
# Pin 5 — per-tier seed counts
# --------------------------------------------------------------------------


def test_per_tier_seed_terms_knob_narrows_t1(base_cfg: dict, draw) -> None:
    """t1 pinned + seed_terms {t1: [2,3]} ⇒ no 4-term idea; baseline has one."""
    sequence = all_t1(base_cfg)
    knob = with_tiers(
        base_cfg,
        {"seed_terms": {"t1": [2, 3], "t2": [2, 4], "t3": [3, 4]}},
        sequence=sequence,
    )
    baseline = with_tiers(base_cfg, None, sequence=sequence)

    knob_lengths: list[int] = []
    baseline_lengths: list[int] = []
    for seed in range(SEED_TERMS_SEEDS):
        for idea in draw(knob, batch_id=f"b003-seedknob-{seed}", seed=seed):
            assert idea["tier"] == "t1", f"slot drew {idea['tier']!r} under an all-t1 sequence"
            knob_lengths.append(len(idea["seed_terms"]))
        for idea in draw(baseline, batch_id=f"b003-seedbase-{seed}", seed=seed):
            baseline_lengths.append(len(idea["seed_terms"]))

    assert set(knob_lengths) <= {2, 3}, (
        f"with tiers.seed_terms {{t1: [2, 3]}} and every slot pinned to t1 the drawn "
        f"lengths were {sorted(set(knob_lengths))} — the per-tier range REPLACES "
        "ideas.seed_terms_per_idea for that tier; an entry-tier game with four seed terms "
        "is the thing the knob exists to prevent"
    )
    assert set(baseline_lengths) <= {2, 3, 4}, (
        f"the knob-off baseline drew lengths {sorted(set(baseline_lengths))}, outside the "
        "sampler's own [2, 4] range"
    )
    assert 4 in baseline_lengths, (
        f"the knob-off baseline over seeds 0..{SEED_TERMS_SEEDS - 1} never drew a 4-term "
        f"idea (lengths {sorted(set(baseline_lengths))}), so the knob assertion above "
        "would pass on luck rather than on the knob — widen the seed range until a 4 "
        "occurs and the control is real again"
    )


# --------------------------------------------------------------------------
# Pin 6 — the common-official term bias
# --------------------------------------------------------------------------


def mean_official_count(term_lists: list[list[str]], vocab: Mapping[str, dict]) -> float:
    """Mean `official` corpus count over every drawn seed term."""
    counts = [vocab[term]["official"] for terms in term_lists for term in terms]
    assert counts, "no seed terms were drawn at all"
    return sum(counts) / len(counts)


def test_common_official_bias_draws_commoner_terms(
    base_cfg: dict, vocab: dict, draw
) -> None:
    """`term_bias {t1: common-official}` lifts the drawn terms' official counts."""
    sequence = all_t1(base_cfg)
    biased = with_tiers(base_cfg, {"term_bias": {"t1": "common-official"}}, sequence=sequence)
    baseline = with_tiers(base_cfg, None, sequence=sequence)

    biased_terms: list[list[str]] = []
    baseline_terms: list[list[str]] = []
    control_terms: list[list[str]] = []
    for seed in range(BIAS_SEEDS):
        biased_terms += seed_term_lists(draw(biased, batch_id=f"b003-bias-{seed}", seed=seed))
        baseline_terms += seed_term_lists(draw(baseline, batch_id=f"b003-flat-{seed}", seed=seed))
        control_terms += seed_term_lists(draw(baseline, batch_id=f"b003-ctrl-{seed}", seed=seed))

    assert baseline_terms == control_terms, (
        "two knob-off runs at the same seeds drew different terms — the determinism "
        "control failed, so nothing measured against this baseline means anything "
        "(sample_batch's contract is same cfg + same seed => byte-identical files)"
    )
    assert biased_terms != baseline_terms, (
        "term_bias {t1: common-official} changed no drawn term list over "
        f"{BIAS_SEEDS} seeds — the knob is inert, which no amount of mean-shifting "
        "arithmetic can make up for"
    )

    biased_mean = mean_official_count(biased_terms, vocab)
    baseline_mean = mean_official_count(baseline_terms, vocab)
    assert biased_mean > baseline_mean, (
        f"the biased draw's mean official count is {biased_mean:.3f} against the "
        f"baseline's {baseline_mean:.3f} — 'common-official' has to pull the WHOLE seed "
        "set toward terms the 25 officials actually use (the witness term cannot be "
        "identified from outside, so the comparison is over every drawn term); the "
        "sampler's default weight is INVERSE occurrence, i.e. it pulls the other way"
    )


# --------------------------------------------------------------------------
# Pin 7 — per-tier quota-boost restriction
# --------------------------------------------------------------------------


def quota_aggregates(term_lists: list[list[str]], term: str) -> tuple[int, int]:
    """`(total occurrences, ideas carrying the term)` over the drawn seed sets."""
    return (
        sum(terms.count(term) for terms in term_lists),
        sum(1 for terms in term_lists if term in terms),
    )


def test_quota_boost_is_suppressed_for_tiers_outside_the_boost_list(
    base_cfg: dict, vocab: dict, draw
) -> None:
    """quota_boost_tiers [t2, t3] + all-t1 slots ⇒ the quota changes nothing."""
    assert QUOTA_TERM in vocab, (
        f"{QUOTA_TERM!r} is not in the closed vocabulary, so it cannot be a quota term"
    )
    sequence = all_t1(base_cfg)
    restricted = with_tiers(base_cfg, {"quota_boost_tiers": ["t2", "t3"]}, sequence=sequence)
    restricted["batch"]["quotas"] = {QUOTA_TERM: 2}
    baseline = with_tiers(base_cfg, {"quota_boost_tiers": ["t2", "t3"]}, sequence=sequence)
    baseline["batch"]["quotas"] = {}

    restricted_terms: list[list[str]] = []
    baseline_terms: list[list[str]] = []
    for seed in range(QUOTA_SUPPRESSED_SEEDS):
        restricted_terms += seed_term_lists(
            draw(restricted, batch_id=f"b003-quota-off-{seed}", seed=seed)
        )
        baseline_terms += seed_term_lists(
            draw(baseline, batch_id=f"b003-quota-none-{seed}", seed=seed)
        )

    restricted_counts = quota_aggregates(restricted_terms, QUOTA_TERM)
    baseline_counts = quota_aggregates(baseline_terms, QUOTA_TERM)
    assert restricted_counts == baseline_counts, (
        f"with quota_boost_tiers [t2, t3] and every slot pinned to t1, {QUOTA_TERM!r} was "
        f"drawn {restricted_counts} times against a no-quota {baseline_counts} — the "
        "boost is restricted to the listed tiers, so for a t1 slot the free-slot weights "
        "are identical to the no-quota ones and the two runs must agree exactly"
    )


def test_quota_boost_is_real_when_no_tier_restriction_applies(base_cfg: dict, draw) -> None:
    """quota_boost_tiers absent ⇒ the x3 free-slot boost is measurable.

    Reading (b): measured over QUOTA_BOOST_SEEDS seeds rather than the
    contract's twenty. `state.action_lag` draws at p≈0.005 per free slot and
    p≈0.016 boosted, so twenty seeds separate the two by about one draw — the
    same "widen until it measures, and note it" licence pin 5 grants.
    """
    sequence = all_t1(base_cfg)
    boosted = with_tiers(base_cfg, {}, sequence=sequence)
    boosted["batch"]["quotas"] = {QUOTA_TERM: 2}
    baseline = with_tiers(base_cfg, {}, sequence=sequence)
    baseline["batch"]["quotas"] = {}

    boosted_terms: list[list[str]] = []
    baseline_terms: list[list[str]] = []
    for seed in range(QUOTA_BOOST_SEEDS):
        boosted_terms += seed_term_lists(draw(boosted, batch_id=f"b003-boost-{seed}", seed=seed))
        baseline_terms += seed_term_lists(draw(baseline, batch_id=f"b003-flat-{seed}", seed=seed))

    boosted_counts = quota_aggregates(boosted_terms, QUOTA_TERM)
    baseline_counts = quota_aggregates(baseline_terms, QUOTA_TERM)
    labels = ("total occurrences", "ideas carrying it")

    behind = [
        f"{label}: boosted {got} < baseline {want}"
        for label, got, want in zip(labels, boosted_counts, baseline_counts, strict=True)
        if got < want
    ]
    assert not behind, (
        f"the unrestricted quota boost drew {QUOTA_TERM!r} LESS often than the no-quota "
        f"baseline ({behind}) — batch.quotas raises a term's free-slot weight, it can "
        "never lower it"
    )
    assert any(
        got > want for got, want in zip(boosted_counts, baseline_counts, strict=True)
    ), (
        f"with no quota_boost_tiers restriction, {QUOTA_TERM!r} was drawn "
        f"{boosted_counts} times against the no-quota baseline's {baseline_counts} over "
        f"{QUOTA_BOOST_SEEDS} seeds (aggregates: {labels}) — nothing moved, so either the "
        "boost never fires or the tier restriction is suppressing it everywhere; the "
        "suppressed case is pinned separately and must NOT be the behaviour here"
    )


# --------------------------------------------------------------------------
# Pin 8 — the prompt-guidance block
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tier", TIER_NAMES)
def test_prompt_guidance_ships_the_override_then_that_tier_s_guidance(
    base_cfg: dict, tiers, tier: str
) -> None:
    """Override once, that tier's guidance immediately after, both after the tier line."""
    policy = attr(tiers, "tier_policy")(with_tiers(base_cfg, {"prompt_guidance": True}))
    # LEAD ADJUDICATION (wave 3, R-11): the prompt now renders the TIER-GATED
    # override — complexity_override(tier) — so the pin follows the effective
    # text; the bare constant remains t1's exact line.
    override = attr(tiers, "complexity_override")(tier)
    guidance = tier_row(tiers, tier).guidance
    prompt = build_prose_prompt(
        base_cfg,
        seed_terms=["goal.reach", "gate.phase"],
        primary="reach_goal",
        failure_family=None,
        tier=tier,
        hazardless=True,
        locus="mover",
        policy=policy,
    )

    assert prompt.count(override) == 1, (
        f"COMPLEXITY_OVERRIDE appears {prompt.count(override)} times in the {tier} prompt, "
        "not once — it is the single block that tells the writer our tier rules beat the "
        "vendored doctrine, and a repeat is a prompt that argues with itself"
    )
    tier_line = prompt.find("Legibility tier:")
    assert tier_line >= 0, (
        "the prose prompt no longer carries a 'Legibility tier:' line — pin 8 anchors the "
        "guidance block after it, because the guidance is the elaboration of that line"
    )
    start = prompt.index(override)
    assert start > tier_line, (
        f"COMPLEXITY_OVERRIDE sits at {start}, ahead of the 'Legibility tier:' line at "
        f"{tier_line} — the override elaborates the tier, so it must follow it"
    )

    end = start + len(override)
    assert guidance in prompt[end:], (
        f"the {tier} prompt carries COMPLEXITY_OVERRIDE but not TIER_TABLE[{tier!r}]"
        ".guidance after it — the override announces the rules and the guidance IS the "
        "rules; shipping the header alone tells the writer nothing"
    )
    gap = prompt[end : prompt.index(guidance, end)]
    assert not gap.strip(), (
        f"COMPLEXITY_OVERRIDE and the {tier} guidance are separated by {gap!r:.160} — the "
        "contract says immediately followed by, so only whitespace may sit between them"
    )

    other = [
        name for name in TIER_NAMES if name != tier and tier_row(tiers, name).guidance in prompt
    ]
    assert not other, (
        f"the {tier} prompt also carries the guidance for {other} — one prompt is one "
        "idea at one tier, and handing the writer another tier's rules is a contradiction "
        "it has no way to resolve"
    )


@pytest.mark.parametrize("block", [{}, {"prompt_guidance": False}])
def test_no_guidance_without_the_knob(base_cfg: dict, tiers, block: dict) -> None:
    """prompt_guidance false or absent ⇒ neither the override nor any guidance."""
    policy = attr(tiers, "tier_policy")(with_tiers(base_cfg, block))
    prompt = build_prose_prompt(
        base_cfg,
        seed_terms=["goal.reach", "gate.phase"],
        primary="reach_goal",
        failure_family=None,
        tier="t2",
        hazardless=False,
        locus="click",
        policy=policy,
    )

    assert attr(tiers, "COMPLEXITY_OVERRIDE") not in prompt, (
        f"a policy with prompt_guidance {block.get('prompt_guidance')!r} still shipped "
        "COMPLEXITY_OVERRIDE — a tier policy that is only steering the DRAW must leave "
        "the prompt's bytes alone, or every other knob's effect is confounded by a "
        "prompt change"
    )
    leaked = [name for name in TIER_NAMES if tier_row(tiers, name).guidance in prompt]
    assert not leaked, (
        f"a policy with prompt_guidance {block.get('prompt_guidance')!r} shipped the "
        f"guidance for {leaked} — guidance travels only under its own knob"
    )


# --------------------------------------------------------------------------
# Pin 9 — import hygiene
# --------------------------------------------------------------------------


def test_gen_tiers_is_a_leaf_module() -> None:
    """Importing `gen.tiers` pulls in neither S0 nor S1.

    Resolution: the subprocess reading of the contract's either/or — a FRESH
    interpreter imports the module and reports `sys.modules`, which catches a
    transitive import that a source scan would miss.
    """
    code = (
        "import json, sys;"
        "import gen.tiers;"
        "print(json.dumps(sorted(m for m in sys.modules if m.startswith('gen'))))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"a fresh interpreter could not import gen.tiers (rc={result.returncode}):\n"
        f"{result.stderr[-2000:]}"
    )
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    forbidden = [name for name in ("gen.s0_ideas", "gen.s1_spec") if name in loaded]

    assert not forbidden, (
        f"importing gen.tiers also imported {forbidden} (gen modules loaded: {loaded}) — "
        "the tier table is canon that S0, S1 and the packager all read; a back-import "
        "makes it a cycle and drags the sampler's csv/driver surface into anything that "
        "only wanted to know what t2 means"
    )
