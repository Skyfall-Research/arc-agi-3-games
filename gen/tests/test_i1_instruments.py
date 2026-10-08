"""Implementer pins for frozen contract I-1 — the two S4 instrument reworks.

Run: .venv/bin/python -m pytest gen/tests/test_i1_instruments.py -q

Contract: `docs/v2/contracts/I-1-instrument-rework.md` (operator 2026-10-06, "Fix
both (one small contract)"). The blind lane's file is
`gen/tests/test_v2_instruments.py`; this one is the implementer's and was
written against `gen/s4_baselines.py` as shipped.

WHAT IS PINNED, group by group

1. THE HOUSE RULE (byte identity). Sixteen S4 runs were captured from the
   PRE-I-1 module (sha256 of `gen/s4_baselines.py` at capture:
   HEAD_S4_SHA256) into `fixtures/i1-s4-head-frozen-2026-10-06/` — six
   workers x the four config shapes in use (bare, `g.cap_fit: record`,
   `caps.basis: official-band`, the template's armed shape). Every one is
   re-run here and must come back byte-for-byte (after the documented path /
   interpreter-version normalisation). An unconfigured batch's S4 output is
   today's output.
2. THE ADJUDICATED INSTRUMENT, derived. Both officials-instruments are
   recomputed from FROZEN copies of their own files
   (`fixtures/i1-instruments-frozen-2026-10-06/`: duckWM's
   `local-docs/arc-agi-3-agents/out/replay-ratios.csv` = D7, and
   `audit/comparative/data/effort.csv`) and the module's constants must be
   those derivations — the re-centred g statistic comes from the instrument
   the I-1 memo names (D7, `d7-replay`), and the old centering stays as the
   named alternative `effort-blind`.
3. THE CENTERING KNOB (`g.centering`). Under `d7-replay` the DRAW is
   bit-identical to an unconfigured run (the adjudicated centre IS the
   historical centre — the comparability statement, pinned), and the
   official-band box + band record re-centre on D7's own per-game band.
   Under `effort-blind` the draw re-centres on 1/0.789.
4. THE ALLOWANCE PROBE (`caps.probe: allowance`) on four constructed workers
   where death-by-repetition and budget.cap DIVERGE (`fixtures/i1_workers/`):
   a lava row three presses up (hazard_budget), free blocked moves
   (free_refusal), a literal same-action streak rule (repeat_rule) and an
   allowance only the hidden-state witness can attribute (toggle_only). The
   burn probe reports the lava / the streak / nothing; the allowance probe
   reports the authored cap — and moving the cap moves only the allowance,
   moving the lava moves only the burn.
5. THE OLD FIGURE STAYS, LABELLED, beside the new one (report + metadata).

HYGIENE: every run drives a tmp_path COPY of a fixture worker; nothing under
`out/` or `games/` is read or written; duckWM is not read at test time (its
file is frozen into the fixture dir, and pin 2a proves the copy is the D7
file by its row count and its published statistics).
"""

from __future__ import annotations

import csv
import json
import math
import re
import shutil
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest

from gen import s4_baselines as s4

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
HEAD_DIR = FIXTURES / "i1-s4-head-frozen-2026-10-06"
DATA_DIR = FIXTURES / "i1-instruments-frozen-2026-10-06"
WORKER_DIRS = {
    "capped_generous": FIXTURES / "s4_workers/capped_generous",
    "capped_tight": FIXTURES / "s4_workers/capped_tight",
    "hazard_budget": FIXTURES / "i1_workers/hazard_budget",
    "free_refusal": FIXTURES / "i1_workers/free_refusal",
    "repeat_rule": FIXTURES / "i1_workers/repeat_rule",
    "toggle_only": FIXTURES / "i1_workers/toggle_only",
}

# sha256 of gen/s4_baselines.py as it stood when the HEAD captures were taken
# (== `git show 23e7392:gen/s4_baselines.py`, before any I-1 edit). Recorded,
# not re-checked: the module has moved on by design; the captures are the fact.
HEAD_S4_SHA256 = "be7450c3e9ab008795e85adafe724bd29c5d6f1a3c9062c2a9b346484e1b17ba"

G_CANON = {"median": 2.0, "iqr": [1.54, 2.96], "floor": 6, "span_target": 9,
           "trend": 0.65, "redraw_cap": 3}


# --- helpers ----------------------------------------------------------------


def _worker(tmp_path: Path, name: str, tag: str = "") -> Path:
    target = tmp_path / f"worker-{name}{tag}"
    shutil.copytree(WORKER_DIRS[name], target, ignore=shutil.ignore_patterns("__pycache__"))
    return target.resolve()


def _normalize(text: str, worker: Path, out: Path) -> dict:
    """The capture script's normalisation, verbatim: paths and interpreter
    versions are environment facts, everything else is the stage's bytes."""
    text = text.replace(str(out), "<OUT>").replace(str(worker), "<WORKER>")
    payload = json.loads(text)
    if "versions" in payload:
        payload["versions"] = "<VERSIONS>"
    prov = payload.get("provenance")
    if isinstance(prov, dict):
        prov["arcengine"] = "<ARCENGINE>"
        prov["python"] = "<PYTHON>"
    return payload


def _run(tmp_path: Path, worker_name: str, cfg: Mapping, seed: int, tag: str = "") -> dict:
    worker = _worker(tmp_path, worker_name, tag)
    out = (tmp_path / f"s4-{worker_name}{tag}").resolve()
    s4.run_s4(worker, json.loads(json.dumps(cfg)), seed=seed, out_dir=out)
    metadata_path = out / s4.METADATA_NAME
    return {
        "report": _normalize((out / s4.REPORT_NAME).read_text(encoding="utf-8"), worker, out),
        "metadata": (
            _normalize(metadata_path.read_text(encoding="utf-8"), worker, out)
            if metadata_path.is_file()
            else None
        ),
        "actions": {
            p.name: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((out / s4.ACTIONS_DIRNAME).glob("level-*.json"))
        },
    }


def _cfg(*, centering=None, probe=None, basis=None, cap_fit=None) -> dict:
    g = dict(G_CANON)
    if cap_fit is not None:
        g["cap_fit"] = cap_fit
    if centering is not None:
        g[s4.G_CENTERING_KEY] = centering
    cfg: dict = {"g": g}
    caps: dict = {}
    if basis is not None:
        caps["basis"] = basis
    if probe is not None:
        caps[s4.CAPS_PROBE_KEY] = probe
    if caps:
        cfg["caps"] = caps
    return cfg


def _rows(name: str) -> list[dict]:
    with (DATA_DIR / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _d7_pairs() -> list[tuple[str, float]]:
    return [
        (r["game"], int(r["baseline_actions"]) / int(r["replay_actions"]))
        for r in _rows("replay-ratios.csv")
    ]


def _effort_pairs() -> list[tuple[str, float]]:
    return [
        (r["slug"], int(r["baseline"]) / int(r["actions"]))
        for r in _rows("effort.csv")
        if r["corpus"] == "official" and r["actions"]
    ]


def _game_class(worker: Path):
    game_cls, _solver = s4.load_worker_classes(worker)
    return game_cls


def _patched_worker(tmp_path: Path, name: str, plan: tuple, tag: str) -> Path:
    """A tmp copy of a divergence worker with its LEVEL_PLAN rewritten."""
    worker = _worker(tmp_path, name, tag)
    game = worker / "game.py"
    text = game.read_text(encoding="utf-8")
    new, count = re.subn(
        r"^LEVEL_PLAN = .*$", f"LEVEL_PLAN = {plan!r}", text, flags=re.MULTILINE
    )
    assert count == 1, "fixture drifted: LEVEL_PLAN line not found exactly once"
    game.write_text(new, encoding="utf-8")
    return worker


# =============================================================================
# 1 — THE HOUSE RULE: unconfigured (and today's configured shapes) unchanged
# =============================================================================

HEAD_CASES = sorted(p.name for p in HEAD_DIR.glob("*.json"))


def test_1a_the_head_capture_set_is_the_frozen_sixteen() -> None:
    assert len(HEAD_CASES) == 16, HEAD_CASES
    workers = {json.loads((HEAD_DIR / n).read_text())["worker"] for n in HEAD_CASES}
    assert workers == set(WORKER_DIRS)


@pytest.mark.parametrize("case", HEAD_CASES)
def test_1b_s4_output_is_byte_identical_to_the_pre_i1_module(tmp_path: Path, case: str) -> None:
    """HOUSE RULE: no I-1 knob set -> the stage writes exactly what it wrote
    before I-1 — report, metadata (or its absence on a reject) and actions."""
    frozen = json.loads((HEAD_DIR / case).read_text(encoding="utf-8"))
    got = _run(tmp_path, frozen["worker"], frozen["config"], frozen["seed"])
    assert got["report"] == frozen["report"], f"{case}: s4-report.json moved"
    assert got["metadata"] == frozen["metadata"], f"{case}: metadata.json moved"
    assert got["actions"] == frozen["actions"], f"{case}: actions/ moved"


def test_1c_explicit_burn_probe_writes_the_absent_knobs_bytes(tmp_path: Path) -> None:
    """`caps.probe: burn` names today's probe and therefore writes no new key."""
    frozen = json.loads((HEAD_DIR / "hazard_budget__bare__seed7.json").read_text())
    got = _run(tmp_path, "hazard_budget", _cfg(probe=s4.CAPS_PROBE_BURN), 7)
    assert got["report"] == frozen["report"]
    assert got["metadata"] == frozen["metadata"]


def test_1d_no_new_key_leaks_into_an_unconfigured_report(tmp_path: Path) -> None:
    got = _run(tmp_path, "capped_generous", _cfg(), 7)
    caps = got["report"]["caps"]
    for key in (s4.CAPS_PROBE_KEY, s4.LEGACY_BURN_KEY):
        assert key not in caps
    assert s4.G_CENTERING_KEY not in got["report"]["config"]["g"]
    for key in ("caps_probe", "caps_legacy_burn"):
        assert key not in got["metadata"]


# =============================================================================
# 2 — the two officials-instruments, derived from their own frozen files
# =============================================================================


def test_2a_the_frozen_d7_file_is_the_published_d7_instrument() -> None:
    """agent-difficulty.md §8's own figures: per-level median 2.00x, IQR
    1.54-2.96, p05 1.15, p95 6.71, n=183; per-game (pooled) median 2.36x,
    min 1.71 lf52, max 4.91 lp85, n=25."""
    pairs = _d7_pairs()
    values = np.asarray([g for _, g in pairs])
    assert len(pairs) == 183
    assert round(float(np.percentile(values, 50)), 2) == 2.00
    assert round(float(np.percentile(values, 25)), 2) == 1.54
    assert round(float(np.percentile(values, 75)), 2) == 2.96
    assert round(float(np.percentile(values, 5)), 2) == 1.15
    assert round(float(np.percentile(values, 95)), 2) == 6.71
    pooled: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in _rows("replay-ratios.csv"):
        pooled[row["game"]][0] += int(row["baseline_actions"])
        pooled[row["game"]][1] += int(row["replay_actions"])
    per_game = {g: b / r for g, (b, r) in pooled.items()}
    assert len(per_game) == 25
    assert round(float(np.median(list(per_game.values()))), 2) == 2.36
    assert min(per_game, key=per_game.get) == "lf52"
    assert max(per_game, key=per_game.get) == "lp85"


def test_2b_the_d7_instrument_constants_derive_from_the_d7_rows() -> None:
    stats = s4.g_statistics(_d7_pairs())
    inst = s4.G_INSTRUMENTS[s4.G_CENTERING_D7]
    assert stats["levels"] == inst.levels == 183
    assert stats["games"] == inst.games == 25
    assert inst.median == round(stats["median"], 2) == s4.D7_G_MEDIAN == 2.00
    assert inst.iqr == (round(stats["q1"], 2), round(stats["q3"], 2)) == s4.D7_G_IQR
    assert inst.g_box == tuple(round(v, 4) for v in stats["game_band"]) == s4.D7_GAME_G_BAND
    assert s4.D7_GAME_G_BAND == (1.4375, 3.9778)
    # The ratio view is the same instrument, inverted — never a second source.
    assert inst.ratio_median == 1.0 / inst.median
    assert inst.ratio_band == (1.0 / inst.g_box[1], 1.0 / inst.g_box[0])


def test_2c_the_effort_instrument_constants_derive_from_effort_csv() -> None:
    stats = s4.g_statistics(_effort_pairs())
    inst = s4.G_INSTRUMENTS[s4.G_CENTERING_EFFORT]
    assert stats["levels"] == inst.levels == 183
    assert stats["games"] == inst.games == 25
    assert inst.median == round(stats["median"], 3) == s4.EFFORT_G_MEDIAN == 1.267
    assert inst.iqr == (round(stats["q1"], 3), round(stats["q3"], 3)) == s4.EFFORT_G_IQR
    # Its band and box ARE the R-05/R-22 constants — the same objects, so the
    # alternative is today's official-band surface byte for byte.
    assert inst.ratio_median is s4.OFFICIAL_RATIO_MEDIAN
    assert inst.ratio_band is s4.OFFICIAL_RATIO_BAND
    assert inst.g_box is s4.OFFICIAL_G_BOX
    ratios = {g: [] for g, _ in _effort_pairs()}
    for game, g in _effort_pairs():
        ratios[game].append(1.0 / g)
    medians = [float(np.median(v)) for v in ratios.values()]
    assert (round(min(medians), 3), round(max(medians), 3)) == s4.OFFICIAL_RATIO_BAND


def test_2d_the_two_instruments_measure_the_same_183_levels_against_the_same_baselines() -> None:
    """The disagreement is not a data error: same games, same levels, same
    published baselines — only the play in the denominator differs."""
    d7 = {(r["game"], int(r["level"])): int(r["baseline_actions"])
          for r in _rows("replay-ratios.csv")}
    effort = {(r["slug"], int(r["level"])): int(r["baseline"])
              for r in _rows("effort.csv") if r["corpus"] == "official"}
    assert d7 == effort
    assert len(d7) == 183


def test_2e_the_instruments_differ_by_the_discovery_premium() -> None:
    """blind / replay per level, over the full 183-level join: median 1.4375
    (IQR 1.124-2.081) — a first-contact human play costs ~1.44x a
    solution-known one. That factor is what separates effort.csv from D7, and
    an S4 solver line is solution-known: it carries none of it."""
    replay = {(r["game"], int(r["level"])): int(r["replay_actions"])
              for r in _rows("replay-ratios.csv")}
    premium = [
        int(r["actions"]) / replay[(r["slug"], int(r["level"]))]
        for r in _rows("effort.csv")
        if r["corpus"] == "official" and r["actions"]
    ]
    assert len(premium) == 183
    assert float(np.median(premium)) == 1.4375
    assert round(float(np.percentile(premium, 25)), 3) == 1.124
    assert round(float(np.percentile(premium, 75)), 3) == 2.081
    # And the centres order as the premium says they must.
    assert s4.EFFORT_G_MEDIAN < s4.D7_G_MEDIAN


def test_2f_the_adjudication_is_recorded_on_the_registry() -> None:
    assert s4.G_CENTERING_ADJUDICATED == s4.G_CENTERING_D7
    assert set(s4.G_INSTRUMENTS) == set(s4.G_CENTERINGS) == {
        s4.G_CENTERING_D7, s4.G_CENTERING_EFFORT}
    d7 = s4.G_INSTRUMENTS[s4.G_CENTERING_D7]
    effort = s4.G_INSTRUMENTS[s4.G_CENTERING_EFFORT]
    assert d7.adjudicated is True and effort.adjudicated is False
    assert "replay-ratios.csv" in d7.source
    assert "effort.csv" in effort.source
    assert "alternative" in effort.label.lower()
    assert "adjudicated" in d7.label.lower()
    # The historical centre every batch to date was drawn at IS the D7 one.
    assert (d7.median, d7.iqr) == (G_CANON["median"], tuple(G_CANON["iqr"]))


# =============================================================================
# 3 — the `g.centering` knob
# =============================================================================


def test_3a_absent_centering_reads_the_config_literally() -> None:
    params = s4._g_params(_cfg())
    assert (params.median, params.q1, params.q3) == (2.0, 1.54, 2.96)
    assert s4._g_centering(_cfg()) is None


def test_3b_effort_centering_recentres_the_draw_parameters() -> None:
    cfg = _cfg(centering=s4.G_CENTERING_EFFORT)
    params = s4._g_params(cfg)
    assert (params.median, params.q1, params.q3) == (1.267, 0.948, 1.858)
    mu, _sigma = s4.fit_g(cfg)
    assert mu == math.log(1.267)


@pytest.mark.parametrize("bad", ["d7", "effort", "D7-replay", 2.0, True, ""])
def test_3c_a_bad_centering_is_loud(bad: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        s4._g_params(_cfg(centering=bad))


@pytest.mark.parametrize("basis", [None, s4.CAPS_BASIS_LEGACY])
def test_3d_d7_centering_draws_bit_identically_to_the_historical_runs(
    tmp_path: Path, basis
) -> None:
    """The comparability statement, pinned: centring on the adjudicated
    instrument moves no draw under the legacy box, so every historical batch
    is directly comparable with a d7-centred one."""
    plain = _run(tmp_path, "capped_generous", _cfg(basis=basis), 11, tag="-plain")
    d7 = _run(tmp_path, "capped_generous",
              _cfg(basis=basis, centering=s4.G_CENTERING_D7), 11, tag="-d7")
    assert d7["report"]["result"] == plain["report"]["result"]
    assert d7["metadata"]["baseline_actions"] == plain["metadata"]["baseline_actions"]
    assert d7["report"]["g_fit"] == plain["report"]["g_fit"]


def test_3e_the_centering_record_names_instrument_and_replaced_literals(
    tmp_path: Path,
) -> None:
    got = _run(tmp_path, "capped_generous", _cfg(centering=s4.G_CENTERING_EFFORT), 7)
    block = got["report"]["config"]["g"][s4.G_CENTERING_KEY]
    assert block["instrument"] == s4.G_CENTERING_EFFORT
    assert block["adjudicated"] is False
    assert block["configured"] == {"median": 2.0, "iqr": [1.54, 2.96]}
    assert got["report"]["config"]["g"]["median"] == 1.267
    # metadata provenance carries the same record (it IS report config.g)
    assert got["metadata"]["provenance"]["g_config"][s4.G_CENTERING_KEY] == block


def test_3f_effort_centering_moves_the_shipped_g_down(tmp_path: Path) -> None:
    plain = _run(tmp_path, "capped_generous", _cfg(), 7, tag="-plain")
    effort = _run(tmp_path, "capped_generous",
                  _cfg(centering=s4.G_CENTERING_EFFORT), 7, tag="-effort")
    assert np.median(effort["report"]["result"]["g"]) < np.median(plain["report"]["result"]["g"])


def test_3g_official_band_box_recentres_on_d7(tmp_path: Path) -> None:
    cfg = _cfg(basis=s4.CAPS_BASIS_OFFICIAL_BAND, centering=s4.G_CENTERING_D7,
               cap_fit=s4.CAP_FIT_RECORD)
    got = _run(tmp_path, "capped_generous", cfg, 7)
    assert got["report"]["g_fit"]["clip"] == list(s4.D7_GAME_G_BAND)
    band = got["report"]["caps"]["band"]
    inst = s4.G_INSTRUMENTS[s4.G_CENTERING_D7]
    assert band["source"] == inst.source
    assert band["ratio"] == {"median": inst.ratio_median, "band": list(inst.ratio_band)}
    assert band["g_box"] == list(s4.D7_GAME_G_BAND)
    lo, hi = inst.ratio_band
    assert band["in_band"] == (lo <= band["ratio_median_achieved"] <= hi)


def test_3h_official_band_under_effort_centering_is_todays_band_block(tmp_path: Path) -> None:
    frozen = json.loads((HEAD_DIR / "capped_generous__band-record__seed7.json").read_text())
    cfg = dict(frozen["config"])
    cfg["g"] = dict(cfg["g"], **{s4.G_CENTERING_KEY: s4.G_CENTERING_EFFORT})
    got = _run(tmp_path, "capped_generous", cfg, 7)
    # Same box, same band record — the old centering preserved as named.
    assert got["report"]["caps"]["band"]["source"] == frozen["report"]["caps"]["band"]["source"]
    assert got["report"]["caps"]["band"]["ratio"] == frozen["report"]["caps"]["band"]["ratio"]
    assert got["report"]["g_fit"]["clip"] == frozen["report"]["g_fit"]["clip"]


# =============================================================================
# 4 — the allowance probe: repetition-death and budget.cap DIVERGE
# =============================================================================

# The fixtures' authored numbers (their own docstrings).
HAZARD_CAPS, HAZARD_LAVA, HAZARD_SOLVER = (60, 90), (3, 4), (2, 3)
FREE_CAPS, FREE_SOLVER = (40, 70), (2, 3)
STREAK_CAPS, STREAK_LIMIT, STREAK_SOLVER = (50, 80), (6, 6), (2, 3)
TOGGLE_CAPS, TOGGLE_SOLVER = (40, 60), (2, 2)


def _deaths(detail: dict, cls: str) -> list[dict]:
    return [p for p in detail["plays"] if p["death"] and p["death"]["class"] == cls]


@pytest.fixture(scope="module")
def probed(tmp_path_factory) -> dict:
    """Both probes on both divergence workers, measured once."""
    root = tmp_path_factory.mktemp("i1-probe")
    out = {}
    for name in ("hazard_budget", "free_refusal", "repeat_rule", "toggle_only"):
        worker = root / name
        shutil.copytree(WORKER_DIRS[name], worker, ignore=shutil.ignore_patterns("__pycache__"))
        lines = s4.solver_lines(worker)
        burn, _burn_detail = s4._measure_caps_detail(worker, lines)
        allowance, allowance_detail = s4._measure_allowance_detail(worker, lines)
        out[name] = {
            "solver": tuple(len(level) for level in lines.per_level),
            "burn": tuple(burn),
            "allowance": tuple(allowance),
            "allowance_detail": allowance_detail,
        }
    return out


def test_4a_hazard_worker_burn_measures_the_lava_allowance_measures_the_cap(probed) -> None:
    row = probed["hazard_budget"]
    assert row["solver"] == HAZARD_SOLVER
    assert row["burn"] == HAZARD_LAVA, "burn probe no longer finds the repetition death"
    assert row["allowance"] == HAZARD_CAPS
    assert all(a != b for a, b in zip(row["allowance"], row["burn"], strict=True))


def test_4b_free_refusal_worker_burn_finds_nothing_allowance_finds_the_cap(probed) -> None:
    row = probed["free_refusal"]
    assert row["solver"] == FREE_SOLVER
    assert row["burn"] == (None, None)
    assert row["allowance"] == FREE_CAPS


def test_4c_the_repetition_death_is_classified_not_counted(probed) -> None:
    """Every ACTION1-repeat death in the hazard worker is recorded, and recorded
    as caused by the action played (every substitute survived) — never as an
    allowance."""
    for level, detail in enumerate(probed["hazard_budget"]["allowance_detail"]):
        repeats = [p for p in detail["plays"]
                   if p["kind"] == s4.PLAY_REPEAT and p["actions"] == ["ACTION1"]]
        assert len(repeats) == 1
        play = repeats[0]
        assert play["outcome"] == s4.BURN_GAME_OVER
        assert play["calls"] == HAZARD_LAVA[level]
        assert play["death"]["class"] == s4.DEATH_ACTION_BOUND
        certified = [p for p in detail["plays"]
                     if p["death"] and p["death"]["class"] == s4.DEATH_ALLOWANCE]
        assert certified and min(p["calls"] for p in certified) == HAZARD_CAPS[level]
        for play in certified:
            assert play["death"]["substitute"] != play["actions"][
                (play["calls"] - 1) % len(play["actions"])]


def test_4c2_a_same_action_streak_rule_is_never_the_cap(probed) -> None:
    """Death-by-repetition in its purest form: every single repeated action
    dies at the streak limit (so the burn probe reports 6, 6). The allowance
    probe records those deaths as caused by what was played — a different
    action from the same state survives AND moves the board — and never lets
    the hidden-state witness (which a streak counter would satisfy) speak
    over an informative substitution."""
    row = probed["repeat_rule"]
    assert row["solver"] == STREAK_SOLVER
    assert row["burn"] == STREAK_LIMIT
    assert row["allowance"] == STREAK_CAPS
    for level, detail in enumerate(row["allowance_detail"]):
        repeats = [p for p in detail["plays"] if p["kind"] == s4.PLAY_REPEAT
                   and p["outcome"] == s4.BURN_GAME_OVER]
        assert repeats, "the streak rule no longer fires on a repeated action"
        for play in repeats:
            assert play["calls"] == STREAK_LIMIT[level]
            assert play["death"]["class"] == s4.DEATH_ACTION_BOUND
            results = {s["result"] for s in play["death"]["substitutes_survived"]}
            assert s4.SUBSTITUTE_CHANGED in results
        certified = _deaths(detail, s4.DEATH_ALLOWANCE)
        assert min(p["calls"] for p in certified) == STREAK_CAPS[level]
        assert all(p["kind"] == s4.PLAY_ALTERNATE for p in certified)


def test_4c3_the_hidden_state_witness_attributes_a_noop_only_allowance(probed) -> None:
    """conduit-watch's shape: at exhaustion the only effective action is the
    one being played, so every substitute is a no-op (or the win) and the
    substitution test cannot speak. The same action met a pixel-identical
    board a period earlier and survived — only hidden state ended it."""
    row = probed["toggle_only"]
    assert row["solver"] == TOGGLE_SOLVER
    assert row["burn"] == (None, None)
    assert row["allowance"] == TOGGLE_CAPS
    for level, detail in enumerate(row["allowance_detail"]):
        certified = _deaths(detail, s4.DEATH_ALLOWANCE)
        best = [p for p in certified if p["calls"] == TOGGLE_CAPS[level]]
        assert best and all(p["death"]["rule"] == "hidden-state" for p in best)
        for play in best:
            witness = play["death"]["witness_step"]
            assert witness < play["calls"]
            assert (play["calls"] - witness) % len(play["actions"]) == 0
            assert all(s["result"] != s4.SUBSTITUTE_CHANGED
                       for s in play["death"]["substitutes_survived"])


def test_4c4_the_witness_needs_an_identical_board_at_the_same_phase() -> None:
    a, b, c, d = b"a", b"b", b"c", b"d"
    # period 2: the lethal action met board `a` at step 5 (boards[4]); it also
    # met `a` at step 3 (boards[2], same phase) and survived -> witness step 3.
    assert s4._hidden_state_witness([a, b, a, b, a], 5, 2) == 3
    # same board but at the OTHER phase (a different action met it) -> none.
    assert s4._hidden_state_witness([c, a, b, a, a], 5, 2) is None
    # a strictly changing board (a step counter on screen) -> never a witness.
    assert s4._hidden_state_witness([a, b, c, d], 4, 1) is None
    # period 1: the very previous board, identical -> witness.
    assert s4._hidden_state_witness([a, b, b], 3, 1) == 2


@pytest.mark.parametrize(
    "plan, caps, lava",
    [
        (((3, 45, 3), (4, 75, 4)), (45, 75), (3, 4)),   # move the cap only
        (((3, 60, 2), (4, 90, 3)), (60, 90), (2, 3)),   # move the lava only
        (((3, 33, 4), (4, 51, 2)), (33, 51), (4, 2)),   # move both
    ],
)
def test_4d_allowance_tracks_the_cap_and_burn_tracks_the_lava(
    tmp_path: Path, plan, caps, lava
) -> None:
    """N3's shape, as the implementer pins it: the reworked probe's output is a
    function of budget.cap's bounded quantity and NOT of the repetition death,
    and the old probe's output is the reverse."""
    worker = _patched_worker(tmp_path, "hazard_budget", plan, tag="-" + "-".join(map(str, caps)))
    lines = s4.solver_lines(worker)
    assert tuple(s4.measure_caps(worker, lines)) == lava
    assert tuple(s4.measure_allowance(worker, lines)) == caps


def test_4e_a_death_below_the_solvers_own_line_is_never_an_allowance(tmp_path: Path) -> None:
    """The second attribution rule, on a constructed case: the hazard worker's
    real 60-action allowance, judged against a (counterfactual) solver that
    lived 100 actions in that level, cannot be the cap — the solver would
    have died first."""
    worker = _worker(tmp_path, "hazard_budget")
    game_cls = _game_class(worker)
    record = s4._level_allowance(game_cls, [], 0, survived=100)
    assert record["cap"] is None
    classes = {p["death"]["class"] for p in record["plays"] if p["death"]}
    assert s4.DEATH_BELOW_LINE in classes
    assert s4.DEATH_ALLOWANCE not in classes
    assert s4._level_allowance(game_cls, [], 0, survived=60)["cap"] == 60


def test_4f_the_allowance_probe_is_deterministic(tmp_path: Path) -> None:
    worker = _worker(tmp_path, "hazard_budget")
    game_cls = _game_class(worker)
    first = s4._level_allowance(game_cls, [], 0, survived=2)
    second = s4._level_allowance(game_cls, [], 0, survived=2)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_4f2_untagged_click_games_get_distinct_game_blind_click_points() -> None:
    """The raw-coordinate idiom tags no sprite; the probe then clicks the burn
    probe's own fallback first and two more fixed points, so even a click-only
    untagged game has different actions to alternate and to substitute."""
    from gen.frames import CENTRE_CLICK

    points = s4.RAW_CLICK_POINTS
    assert points[0] == CENTRE_CLICK
    assert len(set(points)) == len(points) >= s4.ALLOWANCE_CLICK_CELLS >= 2
    assert all(0 <= x < 64 and 0 <= y < 64 for x, y in points)


@pytest.mark.parametrize("bad", ["allow", "Allowance", 1, True, ""])
def test_4g_a_bad_probe_is_loud(bad: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        s4._caps_probe(_cfg(probe=bad))


def test_4h_the_caps_block_still_refuses_unknown_keys() -> None:
    with pytest.raises(ValueError):
        s4._caps_basis({"g": dict(G_CANON), "caps": {"basis": "legacy", "probes": "burn"}})
    assert s4._caps_basis(_cfg(probe=s4.CAPS_PROBE_ALLOWANCE)) == s4.CAPS_BASIS_LEGACY


# =============================================================================
# 5 — end to end: the cap-fit reference moves, the old figure stays labelled
# =============================================================================


def test_5a_hazard_worker_verdict_before_and_after(tmp_path: Path) -> None:
    """Before: the lava (3, 4) is taken for the cap and no baseline at floor 6
    fits it — a cap-fit reject routed to S2 as a 'cap bug' that is not one.
    After: the real allowance (60, 90) holds the 5x battery margin."""
    frozen = json.loads((HEAD_DIR / "hazard_budget__bare__seed7.json").read_text())
    assert frozen["report"]["verdict"] == s4.VERDICT_REJECT
    got = _run(tmp_path, "hazard_budget", _cfg(probe=s4.CAPS_PROBE_ALLOWANCE), 7)
    report = got["report"]
    assert report["verdict"] == s4.VERDICT_FIT
    assert report["caps"]["values"] == list(HAZARD_CAPS)
    assert got["metadata"]["caps"] == list(HAZARD_CAPS)
    for row in report["result"]["attempts"][-1]["capfit"]:
        assert row["cap"] == HAZARD_CAPS[row["level"] - 1]
        assert row["fits"] and row["battery_fits"]
    # The draw itself is the unconfigured draw; only the cap reference moved.
    assert report["result"]["attempts"][0]["baselines"] == \
        frozen["report"]["result"]["attempts"][0]["baselines"]


def test_5b_the_old_burn_figure_stays_beside_the_new_one_labelled(tmp_path: Path) -> None:
    got = _run(tmp_path, "hazard_budget", _cfg(probe=s4.CAPS_PROBE_ALLOWANCE), 7)
    caps = got["report"]["caps"]
    assert caps[s4.CAPS_PROBE_KEY] == s4.CAPS_PROBE_ALLOWANCE
    legacy = caps[s4.LEGACY_BURN_KEY]
    assert legacy["label"] == s4.LEGACY_BURN_LABEL
    assert "death-by-repetition" in legacy["label"]
    assert "one release" in legacy["label"].lower()
    assert legacy["values"] == list(HAZARD_LAVA)
    # byte-for-byte the pre-I-1 probe's own per-level records
    frozen = json.loads((HEAD_DIR / "hazard_budget__bare__seed7.json").read_text())
    assert legacy["levels"] == frozen["report"]["caps"]["levels"]
    assert legacy["status"] == frozen["report"]["caps"]["status"]
    meta = got["metadata"]
    assert meta["caps_probe"] == s4.CAPS_PROBE_ALLOWANCE
    assert meta["caps_legacy_burn"] == {"label": s4.LEGACY_BURN_LABEL,
                                        "values": list(HAZARD_LAVA)}


def test_5c_free_refusal_is_no_longer_unmeasured(tmp_path: Path) -> None:
    frozen = json.loads((HEAD_DIR / "free_refusal__bare__seed7.json").read_text())
    assert frozen["report"]["caps"]["status"] == s4.CAPS_UNMEASURED
    got = _run(tmp_path, "free_refusal", _cfg(probe=s4.CAPS_PROBE_ALLOWANCE), 7)
    assert got["report"]["caps"]["status"] == s4.CAPS_MEASURED
    assert "note" not in got["report"]["caps"]
    assert got["report"]["caps"]["values"] == list(FREE_CAPS)
    assert got["report"]["caps"][s4.LEGACY_BURN_KEY]["values"] == [None, None]


def test_5d_both_knobs_compose(tmp_path: Path) -> None:
    cfg = _cfg(probe=s4.CAPS_PROBE_ALLOWANCE, centering=s4.G_CENTERING_D7,
               basis=s4.CAPS_BASIS_OFFICIAL_BAND, cap_fit=s4.CAP_FIT_REJECT)
    got = _run(tmp_path, "hazard_budget", cfg, 7)
    report = got["report"]
    assert [row["measured_cap"] for row in report["caps"]["band"]["levels"]] == list(HAZARD_CAPS)
    assert report["g_fit"]["clip"] == list(s4.D7_GAME_G_BAND)
    assert report["config"]["g"][s4.G_CENTERING_KEY]["instrument"] == s4.G_CENTERING_D7


def test_5e_the_isolated_stage_carries_both_knobs(tmp_path: Path) -> None:
    """`run_s4_isolated` ships the cfg to a fresh interpreter as JSON; both
    I-1 knobs must survive the trip."""
    worker = _worker(tmp_path, "hazard_budget")
    out = (tmp_path / "iso").resolve()
    cfg = _cfg(probe=s4.CAPS_PROBE_ALLOWANCE, centering=s4.G_CENTERING_D7)
    report = s4.run_s4_isolated(worker, cfg, seed=7, out_dir=out, timeout_s=300)
    assert report["caps"]["values"] == list(HAZARD_CAPS)
    assert report["caps"][s4.LEGACY_BURN_KEY]["values"] == list(HAZARD_LAVA)
    assert report["config"]["g"][s4.G_CENTERING_KEY]["instrument"] == s4.G_CENTERING_D7
