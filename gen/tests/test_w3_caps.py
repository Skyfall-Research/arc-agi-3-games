"""Blind pins for wave-3 sub-phase B, contract B2 — R-05 meters/caps + R-22 S4 refit.

Run: .venv/bin/python -m pytest gen/tests/test_w3_caps.py -q

WRITTEN BLIND, from the B2 contract text alone. The implementer's diff was
never read. What this file was allowed to know, and does:

  * the B2 contract paragraph (the four CHANGE items, the replay table and the
    BLIND list: basis knob matrix, no-measurable-cap loudness, cap_fit reject
    mode, template arms + readers, the 5x-margin satisfiability property);
  * the PRE-STATE tree at launch (wave-3 phase-A close): `gen/s4_baselines.py`
    and `config/template.yaml` as they stood BEFORE B2, copied into the
    writer's scratchpad at launch so that nothing here mirrors the
    implementer's file back at itself;
  * `audit/comparative/data/effort.csv`, which the contract names as the
    official-band data source (READ-ONLY, group 1 recomputes its numbers).

Nothing under `out/` is read or written: every run here drives a COPY of a
`gen/tests/fixtures/s4_workers/` worker inside `tmp_path`.

THE PRE-STATE FACTS THIS FILE STANDS ON (all measured on the phase-A-close
module before B2 began; they are the "the live module does X" pins, not HEAD
deltas, so they survive the commit that lands B2):

  P1 `capped_generous` + seed 7 under the legacy policy ships baselines
     [7, 10, 6, 18]; seed 11 ships [6, 6, 24, 7]. `capped_tight` rejects on
     both seeds (level 2's cap of 20 can never admit 5 x baseline >= 30).
  P2 The legacy `s4-report.json` carries exactly REPORT_KEYS at top level and
     `metadata.json` exactly METADATA_KEYS — the frozen b8.1 shape.
  P3 `g.cap_fit` absent == `hard`: an exhausted search rejects. `record` ships
     the last canon-shaped vector plus a `cap_fit` block. Any other value
     raises.
  P4 A worker that DOES call `lose()` but whose every level measures `cap =
     None` came back `caps.status == "measured"`, verdict `fit`, with no note
     anywhere — the silent pass CHANGE 2 abolishes. Group 3 is red against the
     pre-state module for exactly that reason.
  P5 `BATTERY_MARGIN == 5` in `gen/s4_baselines` and in `gen/s5_battery`.

CONTRACT AMBIGUITIES this file had to take a position on (reported to the
lead, never invented quietly):

  A. THE BAND/MARGIN CONFLICT IS TOTAL, NOT MARGINAL. `cap ~ b/.789` means
     `b/cap ~ .789`, while `5b <= cap` means `b/cap <= .2`; the officials'
     whole per-game band is .437-1.084, entirely above .2. So NO derived cap
     in band can satisfy the 5x margin, at any baseline. The contract
     anticipates this ("if the officials' band and the 5x margin CONFLICT,
     that is the flagged ruling ... do not silently move BATTERY_MARGIN"), so
     group 6 pins the only property both halves of the contract can share:
     BATTERY_MARGIN is unmoved, and a level whose margin is broken is never
     SILENT — its `battery_fits` is False and the run either rejects or lists
     it in the `cap_fit` block. Group 6 deliberately does NOT require
     `5b <= cap` to hold on official-band output.
  B. WHERE the basis is applied (inside `draw_baselines`, or in `run_s4`
     before it) is the implementer's call, so every official-band pin here is
     written END-TO-END through `run_s4` and reads the cap that cap-fit
     ACTUALLY USED from `result.attempts[-1].capfit[*].cap` — the frozen b8.1
     row, and the one place a derived cap cannot hide.
  C. "official-band produces caps within the stated band" is read literally
     from the contract's own transposition — `baseline/cap` inside the
     officials' per-game band — with BAND_SLACK for integer rounding. If the
     implementer instead resolves ambiguity A by deriving `cap = 5b` (the
     margin honored, the band abandoned), group 2's band pin is the one that
     reports it.
  D. "(record default unchanged)" cannot mean the ABSENT-knob default, which
     the pre-state module documents as `hard`. Nothing in the contract
     instructs a default change, so group 4 pins "absent behaves exactly as
     `hard`" — whatever the word for the default is, it did not move.
  E. `reject` vs the existing `hard`: the contract says cap_fit "gains reject
     mode" although `hard` already rejects. This file pins `reject` as a live,
     accepted mode that rejects, AND pins `hard` still working (three b002
     suites pin `hard`), without asserting the two are or are not synonyms.
  F. "LOUD recorded condition (verdict note)" freezes no key. `_loudness`
     accepts any of: a `caps.status` that is no longer "measured", a
     note/warning-shaped key whose text mentions the cap, or any string in the
     report naming the no-measurable-cap condition. The pre-state report
     produces NONE of these (P4).
  G. Config DOCS are named in the contract's Files line but not in its BLIND
     list, so nothing here pins prose in `docs/`.
"""

from __future__ import annotations

import csv
import json
import shutil
import statistics
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
import yaml

from gen import s4_baselines as s4
from gen import s5_battery
from gen.config import REPO_ROOT, load_config
from gen.s4_baselines import (
    BATTERY_MARGIN,
    CAPS_MEASURED,
    METADATA_NAME,
    REPORT_NAME,
    VERDICT_FIT,
    VERDICT_REJECT,
    cap_fit_block,
    draw_baselines,
    run_s4,
)

TESTS = Path(__file__).resolve().parent
S4_WORKERS = TESTS / "fixtures/s4_workers"
TEMPLATE = REPO_ROOT / "config/template.yaml"
EFFORT_CSV = REPO_ROOT / "audit/comparative/data/effort.csv"

# The contract's own numbers for the officials' effort distribution. Group 1
# recomputes every one of them from effort.csv, so a silent data change under
# the band is caught here rather than inside a derived cap.
BAND_MEDIAN = 0.789
BAND_LO, BAND_HI = 0.437, 1.084
OURS_MEDIAN = 0.493
# Integer-rounding allowance on a band membership test. Both b and cap are
# ints and b >= g.floor = 6, so the coarsest honest choices at the floor are
# 6/6 = 1.000 and 6/7 = 0.857 (both inside the band); one step tighter, 6/5 =
# 1.200, is still refused at this slack. The slack buys rounding, not policy.
BAND_SLACK = 0.05

# The B2 basis vocabulary, frozen by the contract's `caps.basis` line.
BASIS_LEGACY = "legacy"
BASIS_OFFICIAL = "official-band"

# P1 — the phase-A-close legacy draw, measured before B2 began.
LEGACY_GOLD = {7: [7, 10, 6, 18], 11: [6, 6, 24, 7]}

# P2 — the frozen b8.1 output shapes.
REPORT_KEYS = {
    "schema_version", "stage", "game_id", "worker", "out_dir", "rng_seed",
    "seed_source", "verdict", "solver", "caps", "g_fit", "result", "band",
    "config", "paths", "versions",
}
METADATA_KEYS = {
    "schema_version", "game_id", "baseline_actions", "g", "solver_actions",
    "caps", "rng_seed", "verdict", "provenance",
}
CAPFIT_ROW_KEYS = {"level", "solver", "baseline", "cap", "fits", "battery_fits"}
# Path-valued keys: two runs of the same worker into different out dirs differ
# in exactly these, and in nothing else.
PATH_KEYS = ("worker", "out_dir", "paths")

# The synthetic cap-fit violation used by group 4, straight off the tight
# fixture's authored table: level 2's cap of 20 admits baseline_2 (<= 6 x 3 =
# 18, g is clipped at 6.0) but never 5 x baseline_2 (>= 5 x 6 = 30).
SYNTH_SOLVER = [2, 3, 4, 5]
SYNTH_CAPS_TIGHT = [120, 20, 240, 300]
SYNTH_CAPS_GENEROUS = [120, 180, 240, 300]

# Group 3's loudness vocabulary (ambiguity F).
LOUD_KEY_WORDS = ("measurable", "uncapped", "all_none", "all-none", "no_cap", "nocap")
LOUD_PHRASES = (
    "no measurable cap",
    "no-measurable-cap",
    "no_measurable_cap",
    "not measurable",
    "unmeasurable",
    "uncapped",
)

_ABSENT = object()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _cfg(*, basis: object = _ABSENT, cap_fit: object = _ABSENT, **g_over) -> dict:
    """A minimal S4 config. `basis`/`cap_fit` omitted = the knob is ABSENT."""
    g: dict = {
        "median": 2.0,
        "iqr": [1.54, 2.96],
        "floor": 6,
        "span_target": 9,
        "trend": 0.65,
        "redraw_cap": 3,
    }
    g.update(g_over)
    if cap_fit is not _ABSENT:
        g["cap_fit"] = cap_fit
    cfg: dict = {"g": g}
    if basis is not _ABSENT:
        cfg["caps"] = {"basis": basis}
    return cfg


def _worker(tmp_path: Path, name: str) -> Path:
    """A tmp COPY of a shipped S4 fixture worker. The repo tree is never driven."""
    target = tmp_path / f"worker-{name}"
    shutil.copytree(
        S4_WORKERS / name, target, ignore=shutil.ignore_patterns("__pycache__")
    )
    return target


def _run(worker: Path, cfg: Mapping, seed: int, out: Path) -> dict:
    return run_s4(worker, cfg, seed=seed, out_dir=out)


def _rows(report: Mapping) -> list[dict]:
    """The cap-fit rows of the attempt that shipped — where the USED cap lives."""
    return report["result"]["attempts"][-1]["capfit"]


def _strip_paths(report: Mapping) -> dict:
    return {key: value for key, value in report.items() if key not in PATH_KEYS}


def _walk(node, path: str = "") -> Iterator[tuple[str, object]]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            yield here, value
            yield from _walk(value, here)
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            here = f"{path}[{index}]"
            yield here, value
            yield from _walk(value, here)


def _loudness(report: Mapping) -> list[str]:
    """Every signal in the report that an all-`None` caps vector was RECORDED.

    The path-valued subtrees are skipped, and so is any absolute path: pytest
    names its `tmp_path` after the running TEST, so `out_dir` and friends carry
    this test's own name — which spells the condition being searched for, and
    would make this helper answer yes on any module at all. (Measured: without
    the skip, the pre-state module "passed" group 3.)
    """
    signals: list[str] = []
    caps = report.get("caps")
    if isinstance(caps, Mapping):
        status = caps.get("status")
        if isinstance(status, str) and status != CAPS_MEASURED:
            signals.append(f"caps.status={status}")
    for path, value in _walk(report):
        if path.split(".", 1)[0].split("[", 1)[0] in PATH_KEYS:
            continue
        if isinstance(value, str) and value.startswith("/"):
            continue
        leaf = path.rsplit(".", 1)[-1].lower()
        if isinstance(value, bool):
            if value and any(word in leaf for word in LOUD_KEY_WORDS):
                signals.append(f"{path}=True")
            continue
        if not isinstance(value, str):
            continue
        text = value.lower()
        noted = ("note" in leaf or "warn" in leaf) and "cap" in text
        if noted or any(phrase in text for phrase in LOUD_PHRASES):
            signals.append(f"{path}={value}")
    return signals


def _ratios(rows: list[dict]) -> list[tuple[int, float]]:
    """(level, baseline/cap) for every row whose cap is a real number."""
    out: list[tuple[int, float]] = []
    for row in rows:
        cap = row["cap"]
        if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
            continue
        out.append((row["level"], row["baseline"] / cap))
    return out


def _row_for_level(rows: list[dict], level: int) -> dict:
    for row in rows:
        if row["level"] == level:
            return row
    raise AssertionError(f"no cap-fit row for level {level}: {rows}")


def _effort_rows() -> list[dict]:
    with EFFORT_CSV.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# --------------------------------------------------------------------------- #
# group 1 — the band the contract derives official-band from (data, READ-ONLY)
# --------------------------------------------------------------------------- #


def test_g1_effort_csv_carries_the_officials_distribution() -> None:
    """The contract's `.789` / `.437-1.084` are recomputed, never taken on trust."""
    rows = _effort_rows()
    official = [float(row["ratio"]) for row in rows if row["corpus"] == "official" and row["ratio"]]
    assert len(official) == 183, f"expected the 183 official levels, got {len(official)}"
    assert statistics.median(official) == pytest.approx(BAND_MEDIAN, abs=5e-4)


def test_g1_per_game_band_is_the_contracts_span() -> None:
    per_game: dict[str, list[float]] = {}
    for row in _effort_rows():
        if row["corpus"] == "official" and row["ratio"]:
            per_game.setdefault(row["slug"], []).append(float(row["ratio"]))
    assert len(per_game) == 25, f"expected the 25 signed officials, got {len(per_game)}"
    medians = [statistics.median(values) for values in per_game.values()]
    assert min(medians) == pytest.approx(BAND_LO, abs=5e-4)
    assert max(medians) == pytest.approx(BAND_HI, abs=5e-4)


def test_g1_our_own_ratio_is_the_gap_the_contract_names() -> None:
    """Our shipped games sit at .493 — the defect official-band is aimed at."""
    ours = [
        float(row["ratio"])
        for row in _effort_rows()
        if row["corpus"] != "official" and row["ratio"]
    ]
    assert ours, "effort.csv carries no rows for our corpus"
    assert statistics.median(ours) == pytest.approx(OURS_MEDIAN, abs=5e-4)


# --------------------------------------------------------------------------- #
# group 2 — the `caps.basis` knob matrix
# --------------------------------------------------------------------------- #


def test_g2_absent_caps_block_is_the_legacy_basis_byte_for_byte(tmp_path: Path) -> None:
    """CHANGE 1: `DEFAULT legacy = byte-identical`. Absent == explicit `legacy`."""
    worker = _worker(tmp_path, "capped_generous")
    absent = _run(worker, _cfg(), 7, tmp_path / "absent")
    explicit = _run(worker, _cfg(basis=BASIS_LEGACY), 7, tmp_path / "legacy")

    left = (tmp_path / "absent" / METADATA_NAME).read_bytes()
    right = (tmp_path / "legacy" / METADATA_NAME).read_bytes()
    assert left == right, "caps.basis: legacy changed metadata.json against the absent knob"
    assert _strip_paths(absent) == _strip_paths(explicit)


@pytest.mark.parametrize("seed", sorted(LEGACY_GOLD))
def test_g2_legacy_reproduces_the_phase_a_draw(tmp_path: Path, seed: int) -> None:
    """P1 standing pin: the default policy still ships the pre-B2 vector."""
    worker = _worker(tmp_path, "capped_generous")
    report = _run(worker, _cfg(), seed, tmp_path / f"out-{seed}")
    assert report["verdict"] == VERDICT_FIT
    assert report["result"]["baseline_actions"] == LEGACY_GOLD[seed]
    assert report["caps"]["values"] == SYNTH_CAPS_GENEROUS
    assert set(report) == REPORT_KEYS, "the legacy report gained or lost a top-level key"
    metadata = json.loads((tmp_path / f"out-{seed}" / METADATA_NAME).read_text(encoding="utf-8"))
    assert set(metadata) == METADATA_KEYS, "the legacy metadata gained or lost a key"


def test_g2_legacy_still_rejects_the_tight_fixture(tmp_path: Path) -> None:
    worker = _worker(tmp_path, "capped_tight")
    report = _run(worker, _cfg(basis=BASIS_LEGACY), 7, tmp_path / "out")
    assert report["verdict"] == VERDICT_REJECT
    assert not (tmp_path / "out" / METADATA_NAME).is_file()


@pytest.mark.parametrize("seed", sorted(LEGACY_GOLD))
def test_g2_official_band_derives_caps_inside_the_officials_band(
    tmp_path: Path, seed: int
) -> None:
    """CHANGE 1: under official-band the cap cap-fit uses is derived, and in band."""
    worker = _worker(tmp_path, "capped_generous")
    report = _run(
        worker, _cfg(basis=BASIS_OFFICIAL, cap_fit=s4.CAP_FIT_RECORD), seed, tmp_path / "band"
    )
    rows = _rows(report)
    assert {key for row in rows for key in row} >= CAPFIT_ROW_KEYS
    used = [row["cap"] for row in rows]
    # LEAD ADJUDICATION (B2 close), part 1: cap-fit KEEPS the measured
    # burn-probe caps — the measurement is a fact and stays one; the derived
    # official-convention cap is recorded BESIDE it (metadata.caps_required),
    # never substituted into the fit (substitution was the literal reading,
    # measured mutually destructive with `cap_fit: reject`).
    assert used == SYNTH_CAPS_GENEROUS, (
        "official-band replaced cap-fit's measured caps — the adjudicated design "
        "records the derived cap beside the measurement, never over it"
    )
    meta = json.loads((tmp_path / "band" / "metadata.json").read_text())
    assert meta.get("caps_basis") == BASIS_OFFICIAL
    required = meta.get("caps_required")
    baselines = meta["baseline_actions"]
    assert required == [5 * b for b in baselines], (
        f"caps_required {required} is not BATTERY_MARGIN x baseline for {baselines}"
    )
    ratios = _ratios(rows)
    assert len(ratios) == len(rows), f"a derived cap is missing or non-positive: {used}"
    # LEAD ADJUDICATION (B2 close): the contract's LITERAL target
    # ("baseline/cap ~ .789") is arithmetically incompatible with the 5x
    # battery margin (5b <= cap forces b/cap <= 0.2; the whole band sits
    # above it — measured mutually destructive, 0/1079 levels satisfiable),
    # and effort.csv's own column is actions/baseline, not baseline/cap.
    # RULED: the band applies where the CSV measures it (the implied-g box
    # narrowing the DRAW) and the derived cap goes through the officials'
    # own 5x convention (D8: 519/590 death-levels at exactly 5.00x). This
    # pin therefore asserts the SHIPPED semantics: every derived cap is the
    # margin-consistent 5x of its baseline, so 5b <= cap holds everywhere —
    # the exact property the literal reading destroyed. The launch-time flag
    # served; both handbacks record it.
    off_margin = [
        (level, row["cap"], row["baseline"])
        for level, (row) in zip((lvl for lvl, _ in ratios), rows, strict=False)
        if row["cap"] < 5 * row["baseline"]
    ]
    assert not off_margin, (
        f"official-band derived a cap below the 5x battery margin: {off_margin} — "
        "the adjudicated rule is cap = BATTERY_MARGIN * baseline"
    )


def test_g2_official_band_records_the_band_it_used(tmp_path: Path) -> None:
    """Reading-neutral: whatever official-band derives, it SHOWS the officials' numbers.

    Both readings of the band (ambiguity A/C) have to write the distribution
    they worked from into the report, or the refit numbers R-22 asks for cannot
    be read back off a run.
    """
    worker = _worker(tmp_path, "capped_generous")
    report = _run(
        worker, _cfg(basis=BASIS_OFFICIAL, cap_fit=s4.CAP_FIT_RECORD), 7, tmp_path / "band"
    )
    numbers = [value for _path, value in _walk(report) if isinstance(value, float)]
    missing = [
        number
        for number in (BAND_MEDIAN, BAND_LO, BAND_HI)
        if not any(abs(value - number) <= 5e-4 for value in numbers)
    ]
    assert not missing, (
        f"official-band ran without recording the band it used: {missing} appear nowhere "
        "in s4-report.json"
    )


def test_g2_official_band_keeps_the_burn_probe_measurements(tmp_path: Path) -> None:
    """R-22's refit needs BOTH numbers: a derived cap never erases the measured one."""
    worker = _worker(tmp_path, "capped_generous")
    report = _run(
        worker, _cfg(basis=BASIS_OFFICIAL, cap_fit=s4.CAP_FIT_RECORD), 7, tmp_path / "band"
    )
    measured = [level["cap"] for level in report["caps"]["levels"]]
    assert measured == SYNTH_CAPS_GENEROUS, (
        f"the burn probe's own per-level record was rewritten: {measured}"
    )


@pytest.mark.parametrize("bad", ["bogus", "official_band", "Legacy", "", 5, [], None])
def test_g2_a_bad_basis_is_loud(tmp_path: Path, bad: object) -> None:
    """CHANGE 1: `bad value loud` — never a silent fallback to legacy."""
    worker = _worker(tmp_path, "capped_generous")
    with pytest.raises((ValueError, TypeError, KeyError)):
        _run(worker, _cfg(basis=bad), 7, tmp_path / "bad")


# --------------------------------------------------------------------------- #
# group 3 — CHANGE 2: an all-`None` caps vector is LOUD, never a silent pass
# --------------------------------------------------------------------------- #


def test_g3_no_measurable_cap_is_recorded_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A game that DOES call `lose()` and still measures no cap anywhere.

    The burn bound is dropped so every level times out unmeasured — the
    condition CHANGE 2 names, reached without a 2000-action probe. The
    pre-state module answered this with `caps.status == "measured"`, verdict
    `fit` and no note at all (P4).
    """
    monkeypatch.setattr(s4, "BURN_BOUND", 10)
    worker = _worker(tmp_path, "capped_generous")
    report = _run(worker, _cfg(), 7, tmp_path / "out")

    assert all(cap is None for cap in report["caps"]["values"]), (
        "probe assumption broke: the shortened burn bound still measured a cap"
    )
    assert report["caps"]["has_lose_call"] is True
    signals = _loudness(report)
    assert signals, (
        "all caps None passed silently: no status change, no note, nothing in the "
        f"report names the condition (caps.status={report['caps']['status']!r})"
    )


def test_g3_a_measured_run_is_not_made_loud(tmp_path: Path) -> None:
    """The loud condition is the all-`None` one; a measured run stays quiet."""
    worker = _worker(tmp_path, "capped_generous")
    report = _run(worker, _cfg(), 7, tmp_path / "out")
    assert report["caps"]["status"] == CAPS_MEASURED
    assert not _loudness(report), f"a fully measured run was flagged: {_loudness(report)}"


# --------------------------------------------------------------------------- #
# group 4 — R-22: `g.cap_fit` gains `reject`
# --------------------------------------------------------------------------- #


def test_g4_reject_mode_fires_on_a_synthetic_violation() -> None:
    result = draw_baselines(SYNTH_SOLVER, SYNTH_CAPS_TIGHT, _cfg(cap_fit="reject"), 7)
    assert result["verdict"] == VERDICT_REJECT
    assert result["baseline_actions"] is None
    row = _row_for_level(result["attempts"][-1]["capfit"], 2)
    assert row["fits"] is True and row["battery_fits"] is False


def test_g4_reject_mode_changes_nothing_when_the_caps_fit() -> None:
    """`reject` touches ONLY the end of an exhausted search."""
    hard = draw_baselines(SYNTH_SOLVER, SYNTH_CAPS_GENEROUS, _cfg(cap_fit=s4.CAP_FIT_HARD), 7)
    reject = draw_baselines(SYNTH_SOLVER, SYNTH_CAPS_GENEROUS, _cfg(cap_fit="reject"), 7)
    assert reject["verdict"] == VERDICT_FIT
    assert reject["baseline_actions"] == hard["baseline_actions"]
    assert reject["attempts"] == hard["attempts"]


def test_g4_record_mode_is_unchanged() -> None:
    """`record` still ships the last canon-shaped vector and carries the block."""
    result = draw_baselines(
        SYNTH_SOLVER, SYNTH_CAPS_TIGHT, _cfg(cap_fit=s4.CAP_FIT_RECORD), 7
    )
    assert result["verdict"] == VERDICT_FIT
    assert result["baseline_actions"] is not None
    block = cap_fit_block(result, s4.CAP_FIT_RECORD)
    assert block["ok"] is False and block["mode"] == s4.CAP_FIT_RECORD
    assert [violation["level"] for violation in block["violations"]] == [2]
    violation = block["violations"][0]
    assert violation["margin_needed"] == BATTERY_MARGIN * violation["baseline"] - violation["cap"]


def test_g4_the_absent_knob_default_did_not_move() -> None:
    """Ambiguity D: whatever the default is called, it is still what it was."""
    absent = draw_baselines(SYNTH_SOLVER, SYNTH_CAPS_TIGHT, _cfg(), 7)
    hard = draw_baselines(SYNTH_SOLVER, SYNTH_CAPS_TIGHT, _cfg(cap_fit=s4.CAP_FIT_HARD), 7)
    assert absent["verdict"] == hard["verdict"] == VERDICT_REJECT
    assert absent["attempts"] == hard["attempts"]


@pytest.mark.parametrize("bad", ["soft", "Reject", "", 1, None])
def test_g4_a_bad_cap_fit_value_is_still_loud(bad: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        draw_baselines(SYNTH_SOLVER, SYNTH_CAPS_TIGHT, _cfg(cap_fit=bad), 7)


def test_g4_reject_end_to_end_writes_no_metadata(tmp_path: Path) -> None:
    worker = _worker(tmp_path, "capped_tight")
    report = _run(worker, _cfg(cap_fit="reject"), 7, tmp_path / "out")
    assert report["verdict"] == VERDICT_REJECT
    assert report["paths"]["metadata"] is None
    assert not (tmp_path / "out" / METADATA_NAME).is_file()
    assert (tmp_path / "out" / REPORT_NAME).is_file()


# --------------------------------------------------------------------------- #
# group 5 — the template arms both knobs, and the readers accept it
# --------------------------------------------------------------------------- #


def test_g5_template_arms_official_band_and_reject() -> None:
    """Yaml-level, so a commented-out key cannot buy the pin (the D-1 pattern)."""
    cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    assert isinstance(cfg.get("caps"), Mapping), "config/template.yaml has no caps: block"
    assert cfg["caps"]["basis"] == BASIS_OFFICIAL
    assert cfg["g"]["cap_fit"] == "reject"


def test_g5_the_armed_template_is_accepted_by_the_s4_reader(tmp_path: Path) -> None:
    """The reader half: S4 runs the shipped template without raising.

    The VERDICT is deliberately not pinned — under the band/margin conflict
    (ambiguity A) an armed template may legitimately reject — but it must be a
    verdict from the frozen vocabulary, with metadata written iff it is `fit`.
    """
    copy = tmp_path / "template.yaml"
    copy.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    cfg = load_config(copy)
    worker = _worker(tmp_path, "capped_generous")
    report = _run(worker, cfg, 7, tmp_path / "out")
    assert report["verdict"] in (VERDICT_FIT, VERDICT_REJECT)
    assert (tmp_path / "out" / METADATA_NAME).is_file() == (report["verdict"] == VERDICT_FIT)
    assert set(report) >= REPORT_KEYS, "the armed template lost a frozen report key"


# --------------------------------------------------------------------------- #
# group 6 — the 5x margin under official-band (the flagged ruling)
# --------------------------------------------------------------------------- #


def test_g6_battery_margin_is_unmoved() -> None:
    """`do not silently move BATTERY_MARGIN` — in S4 and in the battery that reads it."""
    assert BATTERY_MARGIN == 5
    assert s5_battery.BATTERY_MARGIN == 5


@pytest.mark.parametrize("seed", sorted(LEGACY_GOLD))
def test_g6_official_band_never_breaks_the_margin_silently(tmp_path: Path, seed: int) -> None:
    """Either `5b <= cap`, or the level is visibly a violation. Never silent."""
    worker = _worker(tmp_path, "capped_generous")
    report = _run(
        worker, _cfg(basis=BASIS_OFFICIAL, cap_fit=s4.CAP_FIT_RECORD), seed, tmp_path / "band"
    )
    rows = _rows(report)
    block = report.get("cap_fit") or {}
    listed = {violation["level"] for violation in block.get("violations", [])}
    silent = []
    for row in rows:
        cap = row["cap"]
        if cap is None or BATTERY_MARGIN * row["baseline"] <= cap:
            continue
        visible = row["battery_fits"] is False and (
            report["verdict"] == VERDICT_REJECT or row["level"] in listed
        )
        if not visible:
            silent.append(row)
    assert not silent, f"margin broken with no record of it: {silent}"


@pytest.mark.parametrize("basis", [BASIS_LEGACY, BASIS_OFFICIAL])
def test_g6_capfit_flags_match_their_own_arithmetic(tmp_path: Path, basis: str) -> None:
    """The flags are measurements, not decoration — under either basis."""
    worker = _worker(tmp_path, "capped_generous")
    report = _run(
        worker, _cfg(basis=basis, cap_fit=s4.CAP_FIT_RECORD), 7, tmp_path / f"out-{basis}"
    )
    for row in _rows(report):
        cap = row["cap"]
        if cap is None:
            assert row["fits"] is True and row["battery_fits"] is True
            continue
        assert row["fits"] is (row["baseline"] <= cap)
        assert row["battery_fits"] is (BATTERY_MARGIN * row["baseline"] <= cap)


# --------------------------------------------------------------------------- #
# group 7 — downstream compatibility: S5/S6 still read what they read
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("basis", [BASIS_LEGACY, BASIS_OFFICIAL])
def test_g7_a_fit_under_either_basis_still_ships_the_frozen_metadata(
    tmp_path: Path, basis: str
) -> None:
    worker = _worker(tmp_path, "capped_generous")
    report = _run(
        worker, _cfg(basis=basis, cap_fit=s4.CAP_FIT_RECORD), 7, tmp_path / f"out-{basis}"
    )
    if report["verdict"] != VERDICT_FIT:
        pytest.skip(f"basis {basis} rejected this fixture — the fit shape is not under test")
    metadata = json.loads(
        (tmp_path / f"out-{basis}" / METADATA_NAME).read_text(encoding="utf-8")
    )
    assert set(metadata) >= METADATA_KEYS
    assert metadata["verdict"] == VERDICT_FIT
    assert metadata["baseline_actions"] == report["result"]["baseline_actions"]
    assert len(metadata["baseline_actions"]) == len(metadata["solver_actions"])
