"""IMPLEMENTER's suite for frozen contract T-1 — the t1 density band.

Run: .venv/bin/python -m pytest gen/tests/test_t1_density.py -q

The blind lane for this contract is `gen/tests/test_v2_density.py` and is NOT
this file: nothing here was written with it in view, and nothing here may be
read as covering it.

WHAT T-1 CLOSED (operator ruling 2026-10-06, "Close it: guidance + band check").
The parity re-measure found our five post-b004 t1 games drawing boards at
0.26x-0.67x the officials' per-level object density, on both driver lanes, while
the t2 game held the band. Two halves, one constant
(`visual_canon.OFFICIAL_DENSITY`):

  A  THE BAND'S DERIVATION — the floor (p25) and median re-measured off the
     comparative audit's pinned table, interpolation-invariance included.
  B  CALIBRATION — the check's own decision run over the 25 officials (20/25
     at or above the floor; the five below pinned by name), plus an end-to-end
     replay through `build_visual_card` on the officials' real level-start
     boards when the read-only canon frames are on this machine.
  C  THE RULER — `s3_visual.objects_pcc` is `audit_common.pcc_stats`'s count,
     and it is not `objects_cc`.
  D  THE EXHIBIT — echo-quilt (t1, codex lane) from a FROZEN fixture
     (`fixtures/t1-density-echo-quilt-frozen-2026-10-06/`, copied 2026-10-06
     from the shipped sidecar; never the live `out/` path — the STANDING LAW).
  E  THE KNOB MATRIX — absent = record = always-recorded block; fail arms the
     rejection; off removes it; anything else is refused loudly. Plus the gate
     runner's wiring.
  F  THE CARD ROW'S SHAPE — json block and markdown section, scoped and not.
  G  BYTE IDENTITY — a config without the knob gets exactly the `off` card plus
     the always-recorded block (json, markdown and contact sheet), the R-06
     precedent.
  H  TIER SCOPE — explicit: t1 only, `game.tier` (a promotion) beats idea.json,
     anything else or nothing is `not-scoped`.
  I  PAYLOAD PROMPT-SYNC — the tier-aware section rides the S2 payload, every
     figure in it interpolated from the constant the band is cut from.

HERMETIC. tmp_path only. Nothing is read from or written under the repo's real
`out/` or `games/`; duckWM is read (never written) for the S2 payload's canon
and, when present, the officials' frames.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml

from gen import s3_visual, visual_canon
from gen.config import REPO_ROOT, load_config

ROOT = Path(REPO_ROOT)
LEVEL_METRICS = ROOT / "audit" / "comparative" / "data" / "level-metrics.csv"
AUDIT_SCRIPTS = ROOT / "audit" / "comparative" / "scripts"
TEMPLATE = ROOT / "config" / "template.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXHIBIT = FIXTURES / "t1-density-echo-quilt-frozen-2026-10-06"
GOOD_SPEC = FIXTURES / "specs" / "good-spec.yaml"
PAYLOAD_CONFIG = "config/b001-pilot.yaml"      # test_b6_payload's own payload config

SPEC_NAME = "spec.yaml"
IDEA_NAME = "idea.json"
FRAMES_NAME = "worker.frames.json"
CARD_JSON = Path("worker.gate") / "visual-report.json"
CARD_MD = Path("worker.gate") / "visual-report.md"
CONTACT_SHEET = Path("worker.gate") / "visual-contact-sheet.png"

# Every other mode-knobbed card check forced off, so a card built here carries
# the density block and nothing a sibling check decided.
OTHERS_OFF = {"visual_card": "record", "field_index": "off", "role_footprint": "off",
              "win_render": "off", "declared_vs_painted": "off", "chrome_extent": "off",
              "danger_visible": "off"}

# The frozen exhibit's provenance (measured 2026-10-06 when it was copied).
EXHIBIT_FRAMES_SHA256 = "2c29817c438bf9e6e6f423b43bc8e3e3cf7dfc25282a6843c95be8fefd45ce34"
EXHIBIT_SOURCE_SHA256 = "a157664bcfa609aa9ffa2ab0213f4613ba4e7e0ba227929eec6f106be10adc5f"
EXHIBIT_PER_LEVEL = [13, 17, 19, 17, 20, 18, 21]     # = the CSV's echo-quilt rows that day


# --- helpers ----------------------------------------------------------------------


def _official_rows() -> list[dict]:
    with LEVEL_METRICS.open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row["corpus"] == "official"]


def _official_per_game() -> dict[str, list[int]]:
    per_game: dict[str, list[int]] = defaultdict(list)
    for row in _official_rows():
        per_game[row["slug"]].append(int(row["objects_pcc"]))
    return dict(per_game)


def _audit_common():
    if str(AUDIT_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(AUDIT_SCRIPTS))
    import audit_common  # the audit tree is a script dir, not a package

    return audit_common


def board(objects: int, *, background: int = 5, dot: int = 9) -> list[list[int]]:
    """A 64x64 board whose `objects_pcc` is exactly `objects` (>= 1).

    One background component plus `objects - 1` isolated single-cell dots on a
    4-cell lattice — no dot touches another or splits the background.
    """
    assert 1 <= objects <= 1 + 15 * 15
    grid = [[background] * 64 for _ in range(64)]
    placed = 0
    for y in range(2, 62, 4):
        for x in range(2, 62, 4):
            if placed == objects - 1:
                return grid
            grid[y][x] = dot
            placed += 1
    return grid


def frames_document(grids: Sequence[list[list[int]]], game_id: str = "density-fixture") -> dict:
    """reset -> one record per completed level -> a WIN record: one level per grid."""
    records = []
    for index, grid in enumerate(grids):
        records.append({"label": "reset" if index == 0 else f"step-{index}:ACTION1",
                        "seq": index, "levels_completed": index, "state": "NOT_FINISHED",
                        "grid": grid})
    records.append({"label": "final", "seq": len(grids), "levels_completed": len(grids),
                    "state": "WIN", "grid": grids[-1]})
    return {"game_id": game_id, "source": "solver", "records": records}


def stage(directory: Path, grids: Sequence[list[list[int]]], *, idea_tier: str | None = "t1",
          spec_tier: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    game: dict = {"slug": directory.name}
    if spec_tier is not None:
        game["tier"] = spec_tier
    (directory / SPEC_NAME).write_text(yaml.safe_dump({"game": game}), encoding="utf-8")
    (directory / FRAMES_NAME).write_text(json.dumps(frames_document(grids)) + "\n",
                                         encoding="utf-8")
    if idea_tier is not None:
        (directory / IDEA_NAME).write_text(json.dumps({"id": "x", "tier": idea_tier}),
                                           encoding="utf-8")
    return directory


def card(directory: Path, **gate) -> dict:
    return s3_visual.build_visual_card(directory, {"gate": {**OTHERS_OFF, **gate}})


def stage_exhibit(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name in (SPEC_NAME, IDEA_NAME):
        (directory / name).write_bytes((EXHIBIT / name).read_bytes())
    (directory / FRAMES_NAME).write_bytes(gzip.decompress(
        (EXHIBIT / f"{FRAMES_NAME}.gz").read_bytes()))
    return directory


# =============================================================================
# A — the band's derivation from the measured csv
# =============================================================================


def test_a1_the_table_is_the_183_official_level_starts_over_25_games():
    per_game = _official_per_game()
    assert sum(len(values) for values in per_game.values()) == 183 \
        == visual_canon.OFFICIAL_DENSITY["levels"]
    assert len(per_game) == 25 == visual_canon.OFFICIAL_DENSITY["games"]


def test_a2_median_and_p25_are_re_measured_and_equal_the_constants():
    values = sorted(int(row["objects_pcc"]) for row in _official_rows())
    assert statistics.median(values) == visual_canon.OFFICIAL_DENSITY["median"] \
        == visual_canon.DENSITY_MEDIAN_OBJECTS == 47
    for method in ("exclusive", "inclusive"):
        assert statistics.quantiles(values, n=4, method=method)[0] \
            == visual_canon.OFFICIAL_DENSITY["p25"] == visual_canon.DENSITY_FLOOR_OBJECTS == 25
    assert values[0] == visual_canon.OFFICIAL_DENSITY["min"]
    assert values[-1] == visual_canon.OFFICIAL_DENSITY["max"]
    assert sum(value < 25 for value in values) == visual_canon.OFFICIAL_DENSITY["levels_below_p25"]
    level_one = [int(row["objects_pcc"]) for row in _official_rows() if row["level"] == "1"]
    assert statistics.median(level_one) == visual_canon.OFFICIAL_DENSITY["l1_median"]


def test_a3_p25_is_interpolation_invariant_and_p75_is_not():
    """Why the floor is p25 and the band has no ceiling: numpy's nine percentile
    methods all return 25 and 47, while p75 moves with the method."""
    numpy = pytest.importorskip("numpy")
    values = sorted(int(row["objects_pcc"]) for row in _official_rows())
    methods = ("linear", "lower", "higher", "nearest", "midpoint", "inverted_cdf", "hazen",
               "weibull", "median_unbiased")
    assert {float(numpy.percentile(values, 25, method=m)) for m in methods} == {25.0}
    assert {float(numpy.percentile(values, 50, method=m)) for m in methods} == {47.0}
    assert len({float(numpy.percentile(values, 75, method=m)) for m in methods}) > 1


def test_a4_the_card_reads_the_same_constant_the_payload_does():
    assert s3_visual.DENSITY_FLOOR_OBJECTS is visual_canon.DENSITY_FLOOR_OBJECTS
    assert s3_visual.DENSITY_MEDIAN_OBJECTS is visual_canon.DENSITY_MEDIAN_OBJECTS
    assert visual_canon.DENSITY_FLOOR_OBJECTS == int(visual_canon.OFFICIAL_DENSITY["p25"])


def test_a5_ours_figures_are_the_parity_re_measure():
    """The payload quotes our t1/t2 figures; they are the csv's per-level medians."""
    with LEVEL_METRICS.open(encoding="utf-8", newline="") as handle:
        ours: dict[str, list[int]] = defaultdict(list)
        for row in csv.DictReader(handle):
            if row["corpus"] == "ours":
                ours[row["slug"]].append(int(row["objects_pcc"]))
    for block in ("ours_t1", "ours_t2"):
        for game, value in visual_canon.OFFICIAL_DENSITY[block].items():
            assert statistics.median(ours[game]) == value, (block, game)


# =============================================================================
# B — calibration over the 25 officials
# =============================================================================


def test_b1_the_officials_pass_20_of_25_and_the_five_below_are_named():
    per_game = _official_per_game()
    verdicts = {slug: s3_visual.density_verdict(values, "t1") for slug, values in per_game.items()}
    failing = sorted(slug for slug, verdict in verdicts.items() if not verdict["passed"])
    assert len(verdicts) - len(failing) == 20
    assert failing == sorted(visual_canon.OFFICIAL_DENSITY["games_below_floor"])
    for slug, expected in zip(visual_canon.OFFICIAL_DENSITY["games_below_floor"],
                              visual_canon.OFFICIAL_DENSITY["games_below_floor_medians"],
                              strict=True):
        assert verdicts[slug]["objects_pcc_median"] == expected
        assert verdicts[slug]["status"] == "below-floor"
    for slug in visual_canon.OFFICIAL_DENSITY["games_on_floor"]:
        assert verdicts[slug]["objects_pcc_median"] == visual_canon.DENSITY_FLOOR_OBJECTS
        assert verdicts[slug]["passed"] is True       # ON the floor passes
    officials = s3_visual.DENSITY_CALIBRATION["officials"]
    assert officials["games_at_or_above_floor"] == 20
    assert [row["game"] for row in officials["below_floor"]] \
        == visual_canon.OFFICIAL_DENSITY["games_below_floor"]


def test_b2_end_to_end_replay_of_the_officials_through_the_card(tmp_path: Path):
    """The same 20/25 through `build_visual_card` on the officials' REAL level-start
    boards, and the card's ruler reproducing all 183 csv values. Reads the
    read-only canon frames; skipped where they are not on this machine."""
    common = _audit_common()
    if not common.OFFICIAL_FRAMES.is_dir():
        pytest.skip(f"{common.OFFICIAL_FRAMES} is not on this machine")
    expected = {(row["slug"], int(row["level"])): int(row["objects_pcc"])
                for row in _official_rows()}
    passed, measured, matched = 0, 0, 0
    for slug in common.OFFICIAL_SLUGS:
        records = list(common.iter_official_records(slug))
        keep = [index for _level, index in common.level_starts(records)]
        win = next((i for i, record in enumerate(records) if record["state"] == "WIN"), None)
        keep += [] if win is None else [win]
        sidecar = {"game_id": slug, "source": "official-trace", "records": [
            {"label": f"rec-{i}", "seq": i, "levels_completed": records[i]["levels_completed"],
             "state": records[i]["state"], "grid": records[i]["grid"]} for i in keep]}
        directory = tmp_path / slug
        directory.mkdir()
        (directory / FRAMES_NAME).write_text(json.dumps(sidecar), encoding="utf-8")
        (directory / SPEC_NAME).write_text("game:\n  tier: t1\n", encoding="utf-8")
        block = card(directory, density="record")["density"]
        passed += block["passed"]
        for row in block["per_level"]:
            measured += 1
            matched += row["objects_pcc"] == expected[(slug, row["level"])]
    assert (passed, measured, matched) == (20, 183, 183)


# =============================================================================
# C — the ruler
# =============================================================================


def test_c1_objects_pcc_is_the_audits_pcc_stats_count():
    common = _audit_common()
    grids = [board(1), board(47), [[i % 3 for i in range(64)] for _ in range(64)],
             [[(x + y) % 2 for x in range(64)] for y in range(64)]]
    walled = [[5] * 64 for _ in range(64)]
    for row in walled:
        row[32] = 9
    grids.append(walled)
    for grid in grids:
        assert s3_visual.objects_pcc(grid) == common.pcc_stats(grid)[0]
    assert s3_visual.objects_pcc(board(47)) == 47


def test_c2_objects_pcc_counts_the_background_and_objects_cc_does_not():
    """A wall splitting the field: the officials count three regions (two field
    halves and the wall), `objects_cc` counts the one non-modal blob."""
    walled = [[5] * 64 for _ in range(64)]
    for row in walled:
        row[32] = 9
    assert s3_visual.objects_pcc(walled) == 3
    assert s3_visual.objects_cc(walled) == 1


# =============================================================================
# D — the frozen exhibit (echo-quilt, t1, codex lane)
# =============================================================================


def test_d1_the_fixture_is_the_shipped_sidecar_byte_for_byte():
    raw = gzip.decompress((EXHIBIT / f"{FRAMES_NAME}.gz").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == EXHIBIT_FRAMES_SHA256
    assert json.loads(raw)["source_sha256"] == EXHIBIT_SOURCE_SHA256
    assert json.loads((EXHIBIT / IDEA_NAME).read_text(encoding="utf-8"))["tier"] == "t1"


def test_d2_the_exhibit_flags_under_the_band_at_its_measured_value(tmp_path: Path):
    directory = stage_exhibit(tmp_path / "echo-quilt")
    block = s3_visual.build_visual_card(directory, {"gate": {"visual_card": "record"}})["density"]
    assert [row["objects_pcc"] for row in block["per_level"]] == EXHIBIT_PER_LEVEL
    assert block["objects_pcc_median"] == 18 \
        == visual_canon.OFFICIAL_DENSITY["ours_t1"]["echo-quilt"]
    assert (block["tier"], block["tier_source"]) == ("t1", "idea.json tier")
    assert (block["mode"], block["status"], block["passed"]) == ("record", "below-floor", False)


def test_d3_the_exhibit_through_the_audit_ruler_record_for_record(tmp_path: Path):
    common = _audit_common()
    directory = stage_exhibit(tmp_path / "echo-quilt")
    for record in json.loads((directory / FRAMES_NAME).read_text(encoding="utf-8"))["records"]:
        assert s3_visual.objects_pcc(record["grid"]) == common.pcc_stats(record["grid"])[0]


# =============================================================================
# E — the knob matrix, and the gate runner's wiring
# =============================================================================


@pytest.mark.parametrize(("gate", "expected"), [
    ({}, "record"), ({"density": "record"}, "record"), ({"density": "fail"}, "fail"),
    ({"density": "off"}, "off"),
])
def test_e1_density_mode_reads_the_knob(gate: dict, expected: str):
    assert s3_visual.DEFAULT_DENSITY == "record"
    assert s3_visual.density_mode({"gate": gate} if gate else {}) == expected


@pytest.mark.parametrize("bad", ["warn", "Fail", "", None, True])
def test_e2_an_unknown_mode_is_refused_loudly(bad):
    with pytest.raises(ValueError, match=r"gate\.density"):
        s3_visual.density_mode({"gate": {"density": bad}})


@pytest.mark.parametrize("mode", [None, "record", "fail"])
def test_e3_every_armed_mode_measures_and_computes_the_same_verdict(tmp_path: Path, mode):
    """`passed` is decided by the measurement in every mode (the l1 floor's
    pattern); the mode only says who may act on it."""
    directory = stage(tmp_path / "sparse", [board(10), board(12), board(9)])
    gate = {} if mode is None else {"density": mode}
    block = card(directory, **gate)["density"]
    assert block["mode"] == (mode or "record")
    assert (block["status"], block["passed"]) == ("below-floor", False)


def test_e4_off_adds_no_block(tmp_path: Path):
    directory = stage(tmp_path / "sparse", [board(10)])
    assert "density" not in card(directory, density="off")


def test_e5_the_gate_runner_rejects_on_density_only_through_the_fail_loop():
    from gen import orchestrator

    assert "density" in orchestrator.GATE_VISUAL_CHECKS
    assert s3_visual.DENSITY_CHECK in s3_visual.CARD_CHECKS
    source = Path(orchestrator.__file__).read_text(encoding="utf-8")
    loop = source[source.index("for check_key, mode in ((FIELD_INDEX_CHECK"):]
    loop = loop[:loop.index('f"visual {check_key}"')]
    assert "(DENSITY_CHECK, density_mode(ctx.cfg))" in loop
    assert 'mode == "fail" and not check["passed"]' in loop


def test_e6_a_rebuild_finding_quotes_the_note_and_no_calibration_row(tmp_path: Path):
    """The orchestrator splices failing card nodes into the rebuild prompt; the
    calibration block carries no `passed`/`status` so it can never read as this
    game failing."""
    from gen import orchestrator

    block = card(stage(tmp_path / "sparse", [board(10)]), density="fail")["density"]
    finding = orchestrator._visual_finding(s3_visual.DENSITY_CHECK, block)
    assert finding["code"] == "gate.density"
    assert block["note"] in finding["detail"]
    assert orchestrator._failing_card_rows(block) == []


def test_e7_the_template_arms_record_explicitly_with_its_evidence():
    assert load_config(TEMPLATE)["gate"]["density"] == "record"
    text = TEMPLATE.read_text(encoding="utf-8")
    comment = text[text.index("#   density (contract T-1"):text.index("\ngate:")]
    for needle in ("objects_pcc", "25", "47", "t1", "5 of the 25", "record"):
        assert needle in comment, needle


def test_e8_m1_keeps_comparing_like_with_like():
    """The audit's shipped-card determinism pin forces every record-default
    check off by name; T-1's joins the list (the W1-A2/B1 precedent)."""
    source = (AUDIT_SCRIPTS / "m1_metrics.py").read_text(encoding="utf-8")
    assert '"density": "off"' in source


# =============================================================================
# F — the card row's shape
# =============================================================================

BLOCK_KEYS = {
    "check", "mode", "metric", "band", "band_source", "tier", "tier_source", "tier_scope",
    "applies", "levels_measured", "per_level", "objects_pcc_median", "ratio_to_official_median",
    "below_floor", "below_official_median", "status", "passed", "calibration",
    "official_source", "note",
}


def test_f1_the_block_shape(tmp_path: Path):
    block = card(stage(tmp_path / "g", [board(30), board(40)]))["density"]
    assert set(block) == BLOCK_KEYS
    assert block["check"] == "density" and block["metric"] == "objects_pcc"
    assert block["band"] == {"floor": 25, "official_median": 47, "ceiling": None}
    assert block["tier_scope"] == list(visual_canon.DENSITY_TIERS) == ["t1"]
    assert block["levels_measured"] == 2
    assert [set(row) for row in block["per_level"]] == [
        {"level", "record", "objects_pcc", "below_floor"}] * 2
    assert block["objects_pcc_median"] == 35
    assert block["ratio_to_official_median"] == round(35 / 47, 2)
    assert (block["status"], block["passed"]) == ("under-median", True)


@pytest.mark.parametrize(("objects", "status", "passed"), [
    (10, "below-floor", False), (24, "below-floor", False), (25, "under-median", True),
    (46, "under-median", True), (47, "in-band", True), (400, "in-band", True),
])
def test_f2_the_band_edges(tmp_path: Path, objects: int, status: str, passed: bool):
    if objects > 226:
        grid = [[(x + y) % 2 for x in range(64)] for y in range(64)]   # 4096 objects
    else:
        grid = board(objects)
    block = card(stage(tmp_path / "g", [grid]), density="fail")["density"]
    assert (block["status"], block["passed"]) == (status, passed)


def test_f3_the_markdown_prints_the_value_beside_the_band_scoped_or_not(tmp_path: Path):
    for name, idea_tier in (("scoped", "t1"), ("unscoped", "t2"), ("tierless", None)):
        directory = stage(tmp_path / name, [board(12)], idea_tier=idea_tier)
        card(directory)
        md = (directory / CARD_MD).read_text(encoding="utf-8")
        section = md[md.index("## Board density (`density`)"):]
        section = section[:section.index("## Per-record measurements")]
        assert "**12**" in section and "floor **25**" in section, name
        assert "| 1 | `reset` | 12 | YES |" in section
        assert "20 of 25" in section
        assert ("it APPLIES" in section) == (idea_tier == "t1"), name


def test_f4_the_reject_block_names_density_in_its_mode(tmp_path: Path):
    directory = stage(tmp_path / "g", [board(12)])
    card(directory, density="fail")
    assert "- `density` — `fail`" in (directory / CARD_MD).read_text(encoding="utf-8")


def test_f5_density_verdict_with_nothing_measured_is_not_checked():
    assert s3_visual.density_verdict([], "t1") == {
        "objects_pcc_median": None, "ratio_to_official_median": None, "applies": True,
        "below_floor": False, "below_official_median": False, "status": "not-checked",
        "passed": True,
    }


# =============================================================================
# G — byte identity beyond the always-recorded block (the R-06 precedent)
# =============================================================================


def test_g1_absent_knob_is_the_off_card_plus_the_density_block(tmp_path: Path):
    grids = [board(12), board(30), board(60)]
    base = {"visual_card": "record"}       # every OTHER check at its own default
    absent_dir = stage(tmp_path / "absent", grids)
    off_dir = stage(tmp_path / "off", grids)
    absent = s3_visual.build_visual_card(absent_dir, {"gate": base})
    s3_visual.build_visual_card(off_dir, {"gate": {**base, "density": "off"}})

    absent_json = json.loads((absent_dir / CARD_JSON).read_text(encoding="utf-8"))
    off_bytes = (off_dir / CARD_JSON).read_bytes()
    assert "density" in absent_json
    stripped = {key: value for key, value in absent_json.items() if key != "density"}
    assert (json.dumps(stripped, indent=2, sort_keys=True) + "\n").encode("utf-8") == off_bytes
    assert (absent_dir / CONTACT_SHEET).read_bytes() == (off_dir / CONTACT_SHEET).read_bytes()

    report = {key: value for key, value in absent.items() if key not in ("density", "paths")}
    assert s3_visual.render_markdown(report).encode("utf-8") \
        == (off_dir / CARD_MD).read_bytes()


def test_g2_absent_and_record_are_the_same_bytes(tmp_path: Path):
    grids = [board(12), board(30)]
    absent_dir = stage(tmp_path / "absent", grids)
    record_dir = stage(tmp_path / "record", grids)
    s3_visual.build_visual_card(absent_dir, {"gate": {"visual_card": "record"}})
    s3_visual.build_visual_card(record_dir, {"gate": {"visual_card": "record",
                                                      "density": "record"}})
    for name in (CARD_JSON, CARD_MD, CONTACT_SHEET):
        assert (absent_dir / name).read_bytes() == (record_dir / name).read_bytes(), name


def test_g3_the_per_record_cards_never_change(tmp_path: Path):
    """The density block is top-level only: no per-record field is added."""
    directory = stage(tmp_path / "g", [board(12)])
    on = card(directory)["per_record"]
    off = card(directory, density="off")["per_record"]
    assert on == off


def test_g4_two_builds_are_byte_identical(tmp_path: Path):
    directory = stage(tmp_path / "g", [board(12), board(30)])
    card(directory)
    first = [(directory / name).read_bytes() for name in (CARD_JSON, CARD_MD)]
    card(directory)
    assert [(directory / name).read_bytes() for name in (CARD_JSON, CARD_MD)] == first


# =============================================================================
# H — tier scope, explicit
# =============================================================================


def test_h1_the_scope_is_t1_only():
    assert visual_canon.DENSITY_TIERS == ("t1",)


@pytest.mark.parametrize(("idea_tier", "spec_tier", "tier", "source"), [
    ("t1", None, "t1", "idea.json tier"),
    ("t2", None, "t2", "idea.json tier"),
    ("t3", None, "t3", "idea.json tier"),
    (None, None, None, None),
    ("t2", "t1", "t1", "spec.yaml game.tier"),       # a promotion's durable record wins
    ("t1", "t2", "t2", "spec.yaml game.tier"),
    ("t9", None, None, None),                        # not a signed tier
])
def test_h2_tier_reading_and_precedence(tmp_path: Path, idea_tier, spec_tier, tier, source):
    directory = stage(tmp_path / "g", [board(10)], idea_tier=idea_tier, spec_tier=spec_tier)
    assert visual_canon.spec_tier(directory) == (tier, source)
    block = card(directory, density="fail")["density"]
    assert (block["tier"], block["tier_source"]) == (tier, source)
    in_scope = tier in visual_canon.DENSITY_TIERS
    assert block["applies"] is in_scope
    assert block["status"] == ("below-floor" if in_scope else "not-scoped")
    assert block["passed"] is (not in_scope)
    assert block["objects_pcc_median"] == 10        # measured and printed either way


def test_h3_a_malformed_idea_is_a_missing_tier_not_a_crash(tmp_path: Path):
    directory = stage(tmp_path / "g", [board(10)], idea_tier=None)
    (directory / IDEA_NAME).write_text("{not json", encoding="utf-8")
    assert visual_canon.spec_tier(directory) == (None, None)
    assert card(directory, density="fail")["density"]["status"] == "not-scoped"


# =============================================================================
# I — payload prompt-sync
# =============================================================================


@pytest.fixture(scope="module")
def payloads(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """The real S2 payload for the §11 fixture spec at t1, at t2, and tierless."""
    from gen.s2_implement import build_payload

    cfg = load_config(PAYLOAD_CONFIG)
    out = {}
    for name, idea_tier in (("t1", "t1"), ("t2", "t2"), ("none", None)):
        spec_dir = tmp_path_factory.mktemp(f"t1density-{name}") / "spec"
        spec_dir.mkdir()
        (spec_dir / SPEC_NAME).write_bytes(GOOD_SPEC.read_bytes())
        (spec_dir / "spec.md").write_text("# Fogbound Switchyard\n\nProse face.\n",
                                          encoding="utf-8")
        if idea_tier is not None:
            (spec_dir / IDEA_NAME).write_text(json.dumps({"tier": idea_tier}), encoding="utf-8")
        out[name] = build_payload(spec_dir, cfg)[0]
    return out


def test_i1_each_payload_carries_its_tiers_section_verbatim(payloads: dict):
    assert visual_canon.density_section("t1") in payloads["t1"]
    assert visual_canon.density_section("t2") in payloads["t2"]
    assert visual_canon.density_section(None) in payloads["none"]
    assert "SIMPLICITY IS MECHANICAL, NOT VISUAL" in payloads["t1"]
    for name in ("t2", "none"):
        assert "SIMPLICITY IS MECHANICAL" not in payloads[name]


def test_i2_the_figures_in_the_prompt_are_the_constants(payloads: dict):
    floor, median = visual_canon.DENSITY_FLOOR_OBJECTS, visual_canon.DENSITY_MEDIAN_OBJECTS
    for name, payload in payloads.items():
        assert f"median is **{median}**" in payload, name
        assert f"25th percentile is **{floor}**" in payload, name
    assert f"per-level median is under **{floor}**" in payloads["t1"]


def test_i3_every_figure_is_interpolated_never_typed(monkeypatch: pytest.MonkeyPatch):
    """Move the constants to sentinels: the section moves with them."""
    monkeypatch.setattr(visual_canon, "DENSITY_FLOOR_OBJECTS", 913)
    monkeypatch.setattr(visual_canon, "DENSITY_MEDIAN_OBJECTS", 917)
    text = visual_canon.density_section("t1")
    assert "**913**" in text and "**917**" in text
    assert "**25**" not in text and "**47**" not in text


def test_i4_the_section_rides_under_the_numbers_card(payloads: dict):
    payload = payloads["t1"]
    numbers = payload.index(visual_canon.corpus_numbers_card())
    density = payload.index("## Board density")
    assert numbers < density < payload.index("## Visual craft")
