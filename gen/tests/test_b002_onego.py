"""b002 one-go pass — the three rulings the b002 batch runs under.

Written from the frozen b002 one-go contract ALONE (Agent B, independent test
writer): nothing here quotes a live run. Every slug, claim, spec, ledger line
and worker below is synthetic or a copy of a checked-in fixture, and no test
writes into `gen/tests/fixtures/`.

THE THREE RULINGS PINNED HERE

1. `verifier.exempt_terms` — a config knob, default OFF (operator, 2026-09-24).
   Under the mandated budget headroom a cap is reachable only by deliberate
   exhaustion, so a `budget.cap` finding carries no information — and it was
   measured firing in BOTH audit directions on one game in consecutive rounds,
   which can ping-pong respecs into the cap. An exempt term may therefore not
   produce `undeclared-term`, `unreachable-declared-mechanic` or
   `dead-spec-term`. It is SUPPRESSED, never dropped: the diff's `exempted`
   list keeps the finding together with what it would have been, and a typo in
   the knob raises rather than silently exempting nothing.

2. `g.cap_fit: hard | record` — a config knob, default `hard` (same ruling).
   S4's hard cap-fit reject permanently blocks an otherwise-accepted game; the
   ruling is that budget calibration is a later optimisation pass. In `record`
   mode the check still runs per attempt, the last canon-shaped draw stands as
   the baseline vector, and both the report and `metadata.json` carry the truth
   in a `cap_fit` block instead of the run rejecting.

3. The green loop's birth-time static gate — NO knob, because it is not a
   deviation. `static.sys-click-truthful` is a bar the blind audit already
   enforces on generated games; the gate applies the SAME bar inside the green
   loop, where fixing it is free. Green-with-gate-pass is the only green: a
   failing gate is a red attempt with a distinct sentinel exit whose message
   rides the ledger row into the next fix prompt. The capture behind the gate
   runs in a fresh interpreter, so nothing a previous round left in this
   process can be served to it.

ONE-GO RATIONALE. The batch is approved to "just work in one go", and the
design principle that buys that is: canon behavior stays the DEFAULT, each
deviation is an explicit config knob the b002 config opts into, and no
existing pin changes. These tests are written as knob-off/knob-on pairs for
exactly that reason — the first pin exists only to prove that a run which does
not opt in is the old run, so the rulings cannot leak into any other batch.

WHAT IS DELIBERATELY NOT PINNED BY SPELLING. Helper names, the sentinel's
exact value and the exemption parameter's name are renegotiable at lead
review, so they are discovered by runtime introspection instead of hard-coded.
The semantics around them are frozen and are pinned literally.
"""

from __future__ import annotations

import copy
import inspect
import json
import shutil
import sys
import types
from pathlib import Path

import pytest
import yaml
from arcengine import ARCBaseGame, Camera, Level, Sprite

from gen import frames, s2_implement, s3_static, s3_verify, s4_baselines
from gen.config import REPO_ROOT, load_config
from gen.worker import instantiate_worker

B002_CONFIG = "config/b002-triple.yaml"
FIXTURE_WORKERS = Path(__file__).resolve().parent / "fixtures" / "s4_workers"

# The term the b002 ruling exempts, plus two controls that are never exempt:
# one clean (declared and reachable) and one that must keep rejecting while
# the exemption is active — an exemption is per term, not an amnesty.
EXEMPT_TERM = "budget.cap"
CLEAN_TERM = "move.grid"
CONTROL_TERM = "info.fog"

VERDICT_PASS, VERDICT_REJECT = "pass", "reject"
EXEMPTED_KEY = "exempted"  # contract wording, not a code name
SYNTHETIC_PROMPT = "SYNTHETIC SEED PROMPT — no live-run content"


# --------------------------------------------------------------------------
# synthetic verifier inputs
# --------------------------------------------------------------------------


def _claims(*terms: tuple[str, bool]) -> dict:
    """A minimal valid claims block: (term, reachable) pairs, each cited."""
    return {
        "terms": [
            {
                "term": term,
                "reachable": reachable,
                "evidence": [{"path": "game.py", "line": 10, "note": "synthetic"}],
            }
            for term, reachable in terms
        ],
        "dead_code": [],
        "deceptions": [],
        "enforcement": [],
        "notes": "synthetic fixture",
    }


def _spec(*terms: str) -> dict:
    return {"game": {"terms": list(terms), "knobs": {"deceptions": []}}}


def _directions(*extra: str) -> tuple[tuple[str, dict, dict], ...]:
    """(reject code, claims, spec) for each direction an exemption covers.

    `extra` terms carry the SAME finding as `EXEMPT_TERM` in each direction,
    so a scenario can hold an exempt finding and a non-exempt one at once.
    """
    findings = (EXEMPT_TERM, *extra)
    return (
        (
            s3_verify.REJECT_UNDECLARED_TERM,
            _claims((CLEAN_TERM, True), *((t, True) for t in findings)),
            _spec(CLEAN_TERM),
        ),
        (
            s3_verify.REJECT_UNREACHABLE_DECLARED,
            _claims((CLEAN_TERM, True), *((t, False) for t in findings)),
            _spec(CLEAN_TERM, *findings),
        ),
        (
            s3_verify.REJECT_DEAD_SPEC_TERM,
            _claims((CLEAN_TERM, True)),
            _spec(CLEAN_TERM, *findings),
        ),
    )


def _exempt_param() -> str:
    """The name of `compute_diff`'s exemption parameter (renegotiable)."""
    extra = [
        p
        for p in inspect.signature(s3_verify.compute_diff).parameters.values()
        if p.name not in ("claims", "spec")
    ]
    named = [p.name for p in extra if "exempt" in p.name.lower()]
    if named:
        return named[0]
    assert len(extra) == 1, (
        "compute_diff(claims, spec) gained no single exemption parameter — the "
        f"contract threads the frozen exemption collection through it; saw {extra}"
    )
    return extra[0].name


def _diff(claims: dict, spec: dict, exempt: tuple[str, ...] | None = None) -> dict:
    if exempt is None:  # knob off: the default must be the empty collection
        return s3_verify.compute_diff(claims, spec)
    return s3_verify.compute_diff(claims, spec, **{_exempt_param(): tuple(exempt)})


def _knob_readers() -> list[tuple[str, object, object]]:
    """(name, fn, wrap) for every helper that READS the exemption knob.

    Discovered, not named: the contract freezes the knob's semantics and
    leaves the helper's spelling renegotiable. A candidate qualifies only if
    some cfg-shaped argument carrying `exempt_terms: [budget.cap]` makes it
    return a collection containing that term; `wrap` rebuilds that same
    argument shape around any other value, so the invalid-knob cases below hit
    the helper exactly where the valid one did.
    """
    base = load_config(B002_CONFIG)

    def whole_cfg(value: object) -> object:
        cfg = copy.deepcopy(base)
        cfg.setdefault("verifier", {})["exempt_terms"] = value
        return cfg

    def verifier_block(value: object) -> object:
        block = copy.deepcopy(base.get("verifier", {}))
        block["exempt_terms"] = value
        return block

    def bare(value: object) -> object:
        return value

    found: list[tuple[str, object, object]] = []
    for name, obj in sorted(vars(s3_verify).items()):
        if not inspect.isfunction(obj) or "exempt" not in name.lower():
            continue
        for wrap in (whole_cfg, verifier_block, bare):
            try:
                value = obj(wrap([EXEMPT_TERM]))
            except Exception:  # noqa: BLE001 — a wrong argument shape disqualifies it
                value = None
            if isinstance(value, (list, tuple, set, frozenset)) and EXEMPT_TERM in value:
                found.append((name, obj, wrap))
                break
    return found


# --------------------------------------------------------------------------
# synthetic workers for the green-loop gate
# --------------------------------------------------------------------------

# One 8x8 level, one declared action (ACTION6 = click). `switch` is tagged
# `sys_click` and the click handler branches on it BY NAME. The untruthful
# build adds `inert_panel`: also tagged, so the engine advertises a click on
# it and every RL consumer reads that list — but no code path handles it.
# That is precisely the `static.sys-click-truthful` failure the gate exists to
# catch at birth, and the truthful build is the same game without it.
_GATE_GAME = '''\
"""SYNTHETIC gate fixture — authored in gen/tests/test_b002_onego.py."""

from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

BACKDROP, SWITCH, PANEL = 4, 11, 6


def _level() -> Level:
    sprites = [
        Sprite([[BACKDROP] * 8 for _ in range(8)], name="backdrop", x=0, y=0,
               collidable=False),
        Sprite([[SWITCH, SWITCH], [SWITCH, SWITCH]], name="switch", x=1, y=3,
               layer=1, tags=["sys_click"]),
    ]
{panel}
    return Level(sprites=sprites)


class GateFixtureGame(ARCBaseGame):
    def __init__(self) -> None:
        super().__init__(
            game_id="{game_id}",
            levels=[_level()],
            camera=Camera(width=8, height=8),
            available_actions=[6],
        )

    def step(self) -> None:
        if self.action.id is GameAction.ACTION6:
            cell = self.camera.display_to_grid(
                int(self.action.data.get("x", 0)), int(self.action.data.get("y", 0))
            )
            if cell is not None:
                hit = self.current_level.get_sprite_at(cell[0], cell[1])
                if hit is not None and hit.name == "switch":
                    self.complete_action()
                    self.next_level()
                    return
        self.complete_action()
'''

_GATE_PANEL = """    sprites.append(
        Sprite([[PANEL, PANEL], [PANEL, PANEL]], name="inert_panel", x=5, y=3,
               layer=1, tags=["sys_click"])
    )"""

_GATE_SOLVER = '''\
"""SYNTHETIC deterministic solver — one click on the switch wins the level."""

from arcengine import ActionInput, GameAction

SWITCH_DISPLAY_XY = (12, 28)  # centre of the 2x2 switch at grid (1, 3), scale 8


class Solver:
    def reset(self) -> None:
        self._clicked = False

    def next_action(self, frame):
        if self._clicked:
            return None
        self._clicked = True
        x, y = SWITCH_DISPLAY_XY
        return ActionInput(id=GameAction.ACTION6, data={"x": x, "y": y})
'''


class _DecoyGame(ARCBaseGame):
    """A CLEAN game: no click tags at all, so the static check would PASS.

    Planted in this process under the name an IN-PROCESS capture of the worker
    would bind. Any loader that honours the module cache would serve this
    instead of the worker's real game.py and the gate would go green on a game
    that is not the one under test.
    """

    def __init__(self) -> None:
        super().__init__(
            game_id="b002-onego-decoy",
            levels=[Level(sprites=[Sprite([[4]], name="only", x=0, y=0)])],
            camera=Camera(width=8, height=8),
            available_actions=[1],
        )

    def step(self) -> None:
        self.complete_action()


def _build_gate_worker(dest: Path, *, truthful: bool) -> Path:
    instantiate_worker(dest)
    dest = Path(dest).resolve()
    source = _GATE_GAME.format(
        panel="" if truthful else _GATE_PANEL,
        game_id="gate-fixture-truthful" if truthful else "gate-fixture-untruthful",
    )
    (dest / "game.py").write_text(source, encoding="utf-8")
    (dest / "solver.py").write_text(_GATE_SOLVER, encoding="utf-8")
    return dest


def _static_verdict(worker_dir: Path):
    """The gate's own check, recomputed here from the same two public parts."""
    cap = frames.capture_worker_isolated(worker_dir)
    return s3_static._check_sys_click(s3_static._parse_game(worker_dir), cap, worker_dir)


def _worker_module_names(worker_dir: Path) -> list[str]:
    """Names an IN-PROCESS capture load of this worker binds in sys.modules."""
    before = set(sys.modules)
    s3_verify.load_worker_classes(worker_dir)
    new = set(sys.modules) - before
    return sorted(
        name
        for name in new
        if str(getattr(sys.modules[name], "__file__", "")).startswith(str(worker_dir))
    )


class _Recorder:
    """A session runner that runs no session and records what it was asked."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(self, prompt: str, **_kwargs: object) -> dict:
        self.prompts.append(prompt)
        return {
            "session_id": f"synthetic-{len(self.prompts)}",
            "usd": 0.0,
            "tokens_in": 1,
            "tokens_out": 1,
            "wall_s": 0.0,
            "exit_code": 0,
            "text": "synthetic session",
        }


def _green_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    """`make validate` GREEN, so only the gate can turn the attempt red."""
    monkeypatch.setattr(s2_implement, "_run_validate", lambda worker_dir: (0, "validate: GREEN"))


def _loop_cfg(attempts: int) -> dict:
    return {"implementer": {"max_green_attempts": attempts, "session_token_cap": "400k"}}


def _named_int_constants(module: object, value: int) -> list[str]:
    return sorted(
        name
        for name, found in vars(module).items()
        if name.isupper()
        and isinstance(found, int)
        and not isinstance(found, bool)
        and found == value
    )


# --------------------------------------------------------------------------
# S4 helpers
# --------------------------------------------------------------------------


def _s4_cfg(cap_fit: str | None) -> dict:
    """The b002 config with the cap-fit knob forced on or removed."""
    cfg = copy.deepcopy(load_config(B002_CONFIG))
    if cap_fit is None:
        cfg["g"].pop("cap_fit", None)
    else:
        cfg["g"]["cap_fit"] = cap_fit
    return cfg


def _copy_fixture_worker(name: str, tmp_path: Path) -> Path:
    """A COPY of a checked-in S4 worker — fixtures are never written to."""
    dest = tmp_path / name
    shutil.copytree(FIXTURE_WORKERS / name, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def _cap_fit_block(report: dict) -> dict:
    """The report's cap_fit block, wherever the report carries it."""
    for holder in (report, report.get("result") or {}):
        if isinstance(holder, dict) and isinstance(holder.get("cap_fit"), dict):
            return holder["cap_fit"]
    raise AssertionError(
        "the S4 report carries no cap_fit block — the contract puts it in BOTH "
        f"the report and metadata.json; report keys: {sorted(report)}"
    )


# --------------------------------------------------------------------------
# PIN 1 — knob off is the old behavior, for both knobs
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code, claims, spec",
    _directions(),
    ids=[code for code, _claims_, _spec_ in _directions()],
)
def test_pin1_verifier_without_exemptions_still_rejects(code: str, claims: dict, spec: dict) -> None:
    """No `exempt_terms`: every direction rejects exactly as it did before."""
    diff = _diff(claims, spec)
    verdict, reasons = s3_verify.decide_verdict([], diff)

    assert verdict == VERDICT_REJECT
    assert [reason["code"] for reason in reasons] == [code]
    assert reasons[0].get("term") == EXEMPT_TERM
    # The default is the EMPTY collection: a run that does not opt in records
    # no exemption either.
    assert list(diff.get(EXEMPTED_KEY, [])) == []


def test_pin1_s4_without_cap_fit_still_rejects(tmp_path: Path) -> None:
    """No `g.cap_fit`: the tight-cap fixture is still a hard reject.

    The checked-in fixture's level 2 cannot fit the 5x battery margin under any
    redraw, so `hard` mode must exhaust the redraws and reject — and a reject
    writes no metadata, which is what keeps a cap-bug game out of S5/S6.
    """
    out_dir = tmp_path / "s4-out"
    result = s4_baselines.run_s4(
        _copy_fixture_worker("capped_tight", tmp_path), _s4_cfg(None), out_dir=out_dir
    )

    assert result["verdict"] == s4_baselines.VERDICT_REJECT
    assert result["result"]["verdict"] == s4_baselines.VERDICT_REJECT
    assert result["paths"]["metadata"] is None
    assert not (out_dir / s4_baselines.METADATA_NAME).exists()


# --------------------------------------------------------------------------
# PIN 2 — the exemption suppresses the reject and records the finding
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code, claims, spec",
    _directions(),
    ids=[code for code, _claims_, _spec_ in _directions()],
)
def test_pin2_exemption_suppresses_and_records(code: str, claims: dict, spec: dict) -> None:
    """All three directions: no reject reason, and the finding is kept."""
    diff = _diff(claims, spec, exempt=(EXEMPT_TERM,))
    verdict, reasons = s3_verify.decide_verdict([], diff)

    assert verdict == VERDICT_PASS, f"exempt term still rejected: {reasons}"
    assert not [r for r in reasons if EXEMPT_TERM in json.dumps(r, sort_keys=True)]

    # Suppressed is not dropped: the diff keeps the finding and what it would
    # have been, so the report still carries the data a later pass needs.
    recorded = [e for e in diff[EXEMPTED_KEY] if e.get("term") == EXEMPT_TERM]
    assert len(recorded) == 1, f"{EXEMPT_TERM!r} not recorded once in {diff[EXEMPTED_KEY]}"
    assert code in str(recorded[0]["would_have_been"])

    # b7.1: the diff block carrying `exempted` must still pass the report's own
    # shape validation, or the recorded finding could never be written out.
    s3_verify._validate_diff(diff)


@pytest.mark.parametrize(
    "code, claims, spec",
    _directions(CONTROL_TERM),
    ids=[code for code, _claims_, _spec_ in _directions(CONTROL_TERM)],
)
def test_pin2_exemption_is_per_term(code: str, claims: dict, spec: dict) -> None:
    """An exemption covers its own term only — the same finding on another
    term in the same direction still rejects."""
    diff = _diff(claims, spec, exempt=(EXEMPT_TERM,))
    verdict, reasons = s3_verify.decide_verdict([], diff)

    assert verdict == VERDICT_REJECT
    assert [(r["code"], r.get("term")) for r in reasons] == [(code, CONTROL_TERM)]


def test_pin2_invalid_knob_raises() -> None:
    """A typo must not silently exempt nothing: the read raises ValueError."""
    readers = _knob_readers()
    assert readers, (
        "found no helper in gen.s3_verify that reads `verifier.exempt_terms` off a "
        "cfg and returns the exemption collection — the contract validates the knob "
        "AT READ TIME, so a typo cannot reach compute_diff as an empty exemption"
    )
    invalid = (
        EXEMPT_TERM,  # a bare string, not a list
        {"term": EXEMPT_TERM},  # a mapping, not a list
        [123],  # a non-string entry
        ["not.a_term"],  # well-formed id, outside the signed vocabulary
    )
    for name, reader, wrap in readers:
        for value in invalid:
            try:
                reader(wrap(value))
            except ValueError:
                continue
            except Exception as exc:  # noqa: BLE001 — the contract names ValueError
                pytest.fail(f"{name}({value!r}) raised {type(exc).__name__}, expected ValueError")
            pytest.fail(f"{name}({value!r}) did not raise — that typo exempts nothing, silently")


# --------------------------------------------------------------------------
# PIN 3 — record mode fits, and tells the truth about why it should not
# --------------------------------------------------------------------------


def test_pin3_record_mode_fits_and_records_violations(tmp_path: Path) -> None:
    """`g.cap_fit: record` on the tight fixture: a fit verdict that still
    carries the per-level violation, in the report AND in metadata.json."""
    cfg = _s4_cfg("record")
    out_dir = tmp_path / "s4-out"
    report = s4_baselines.run_s4(
        _copy_fixture_worker("capped_tight", tmp_path), cfg, out_dir=out_dir
    )

    assert report["verdict"] == s4_baselines.VERDICT_FIT
    assert report["result"]["verdict"] == s4_baselines.VERDICT_FIT

    metadata_path = out_dir / s4_baselines.METADATA_NAME
    assert metadata_path.is_file(), "record mode must write metadata.json — the game ships"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    for where, block in (("metadata", metadata["cap_fit"]), ("report", _cap_fit_block(report))):
        assert block["ok"] is False, f"{where}: the cap does NOT fit; ok must be false"
        assert block["mode"] == "record", where
        assert block["violations"], f"{where}: a false ok with no violation records nothing"
        for entry in block["violations"]:
            assert {"level", "baseline", "cap", "margin_needed"} <= set(entry), where
            assert entry["margin_needed"] > 0, where
    assert metadata["cap_fit"] == _cap_fit_block(report), "report and metadata must agree"

    # The violation must name the level the fixture seeded, in the file's own
    # level numbering — read off the last attempt's own cap-fit rows rather
    # than assumed, so the pin cannot drift from that convention.
    last_attempt = report["result"]["attempts"][-1]
    failed = [row for row in last_attempt["capfit"] if not row["battery_fits"]]
    assert len(failed) == 1, f"fixture drift: expected one binding level, got {failed}"
    violations = metadata["cap_fit"]["violations"]
    assert [v["level"] for v in violations] == [failed[0]["level"]]
    assert violations[0]["cap"] == failed[0]["cap"]
    assert violations[0]["baseline"] == failed[0]["baseline"]

    # The LAST canon-shaped draw stands as the baseline vector, floor intact.
    assert metadata["baseline_actions"] == last_attempt["baselines"]
    assert report["result"]["baseline_actions"] == last_attempt["baselines"]
    floor = cfg["g"]["floor"]
    assert all(value >= floor for value in metadata["baseline_actions"])
    assert len(metadata["baseline_actions"]) == len(metadata["solver_actions"])


def test_pin3_record_mode_reports_a_real_fit(tmp_path: Path) -> None:
    """The generous fixture in record mode: the block says ok, truthfully."""
    out_dir = tmp_path / "s4-out"
    report = s4_baselines.run_s4(
        _copy_fixture_worker("capped_generous", tmp_path), _s4_cfg("record"), out_dir=out_dir
    )

    assert report["verdict"] == s4_baselines.VERDICT_FIT
    metadata = json.loads((out_dir / s4_baselines.METADATA_NAME).read_text(encoding="utf-8"))
    block = metadata["cap_fit"]
    assert block["ok"] is True
    assert block["mode"] == "record"
    assert list(block["violations"]) == []


def test_pin3_unknown_cap_fit_mode_raises(tmp_path: Path) -> None:
    """Any value other than the two modes raises — never a silent default."""
    with pytest.raises(ValueError):
        s4_baselines.run_s4(
            _copy_fixture_worker("capped_generous", tmp_path),
            _s4_cfg("sometimes"),
            out_dir=tmp_path / "s4-out",
        )


# --------------------------------------------------------------------------
# PIN 4 — the green loop's birth-time static gate
# --------------------------------------------------------------------------


def test_pin4_failing_static_is_a_red_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Green validate + failing static = a RED attempt whose ledger row tells
    the whole story, and whose message reaches the next fix prompt."""
    worker = _build_gate_worker(tmp_path / "w-untruthful", truthful=False)
    expected = _static_verdict(worker)
    assert expected.status == "fail", (
        f"fixture wall: the untruthful worker was expected to fail "
        f"{expected.check_id}, got {expected.status} — {expected.note}"
    )

    _green_validate(monkeypatch)
    runner = _Recorder()
    report = s2_implement.green_loop(worker, SYNTHETIC_PROMPT, _loop_cfg(2), session_runner=runner)

    assert report.green is False, "green-with-gate-pass is the ONLY green"
    assert report.attempts == 2
    assert report.reject_reason == s2_implement.ATTEMPT_CAP_REASON

    first = report.records[0]
    assert first.green is False
    # A sentinel that cannot be confused with success, make/pytest failure or
    # the validate timeout — and a NAMED constant, not a literal.
    assert first.validate_exit not in (0, 1, 2, s2_implement.VALIDATE_TIMEOUT_EXIT)
    assert _named_int_constants(s2_implement, first.validate_exit), (
        f"validate_exit {first.validate_exit} is not a named constant of gen.s2_implement"
    )
    # The check's message rides the tail verbatim, so the ledger row carries it.
    assert expected.check_id in first.validate_tail
    assert expected.note in first.validate_tail
    # ... and therefore the NEXT prompt carries it too.
    assert len(runner.prompts) == 2
    assert runner.prompts[0] == SYNTHETIC_PROMPT
    assert expected.note in runner.prompts[1]


def test_pin4_passing_static_stays_green(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same worker without the untruthful tag: green on attempt one."""
    worker = _build_gate_worker(tmp_path / "w-truthful", truthful=True)
    expected = _static_verdict(worker)
    assert expected.status == "pass", (
        f"fixture wall: the truthful worker was expected to pass "
        f"{expected.check_id}, got {expected.status} — {expected.note}"
    )

    _green_validate(monkeypatch)
    runner = _Recorder()
    report = s2_implement.green_loop(worker, SYNTHETIC_PROMPT, _loop_cfg(2), session_runner=runner)

    assert report.green is True
    assert report.attempts == 1
    assert report.reject_reason is None
    assert report.records[-1].green is True
    assert report.records[-1].validate_exit == 0
    assert runner.prompts == [SYNTHETIC_PROMPT]


def test_pin4_gate_capture_is_process_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A decoy planted under the worker's path-derived module name changes
    nothing: the gate's capture runs in a fresh interpreter."""
    worker = _build_gate_worker(tmp_path / "w-isolated", truthful=False)
    expected = _static_verdict(worker)
    assert expected.status == "fail", f"fixture wall: {expected.status} — {expected.note}"

    names = _worker_module_names(worker)
    assert names, "could not learn the module names an in-process capture load binds"
    decoys: dict[str, types.ModuleType] = {}
    for name in names:
        decoy = types.ModuleType(name)
        decoy.__file__ = "<b002-onego decoy>"
        decoy.DecoyGame = _DecoyGame
        decoys[name] = decoy

    _green_validate(monkeypatch)
    runner = _Recorder()
    try:
        for name, decoy in decoys.items():
            sys.modules[name] = decoy
        report = s2_implement.green_loop(
            worker, SYNTHETIC_PROMPT, _loop_cfg(1), session_runner=runner
        )

        # The verdict is the worker's, not the decoy's.
        assert report.green is False
        assert expected.note in report.records[0].validate_tail
        # And this process never exec-loaded the worker: an in-process capture
        # would have replaced the decoy with the real game module.
        for name, decoy in decoys.items():
            assert sys.modules.get(name) is decoy, (
                f"{name} was rebound during the gate — the capture ran IN THIS "
                "PROCESS; the contract requires capture_worker_isolated"
            )
    finally:
        for name in names:
            sys.modules.pop(name, None)


# --------------------------------------------------------------------------
# PIN 5 — the b002 config opts into both rulings
# --------------------------------------------------------------------------


def test_pin5_b002_config_carries_the_rulings() -> None:
    raw = yaml.safe_load((REPO_ROOT / B002_CONFIG).read_text(encoding="utf-8"))
    # MEMBERSHIP, not list equality (lead correction, 2026-09-24): the
    # exemption list grows by ruling — info.deception joined budget.cap the
    # same day under the same evidence bar — and this pin's job is that THIS
    # ruling stays in the config, not that no later ruling may exist.
    assert EXEMPT_TERM in raw["verifier"]["exempt_terms"]
    assert raw["g"]["cap_fit"] == "record"
