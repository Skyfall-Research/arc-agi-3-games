"""b002 hotfix 1 — pins for the ONE corrective retry in the blind verifier pass.

The defect
----------
`run_agent_pass` ran exactly one blind session and then parsed that session's
reply with checks that raise `ValueError` by design — a missing fenced ```json
block, an unparsable block, or a `frame_refs` entry that does not copy a
captured frame label exactly is never a verdict, always an error. With no retry
at that layer and no catch below `main()`, ONE malformed reply killed the whole
orchestrator run mid-batch. The margin is a click-locus game: a click step's
capture label carries the action and its coordinates after the `step-<n>`
prefix (`gen/frames.py`), so a reply citing the bare prefix is rejected, and
mover-only rounds never reach that shape.

The fix is the established house idiom (S1 slug retry, S1 escalation lint
retry, S5 reply retry): on the first parse failure, resume THE SAME session
once with the validator's error verbatim plus a corrective instruction; a
second failure raises exactly as before. No validator loosening, no schema
change, no second retry.

Independence
------------
Written from the frozen contract, not from the implementation. Every fixture
here is synthetic — a stub worker, a hand-built `FrameCapture`, hand-written
replies — and no content from any live run appears in this file. The pins stay
on the contract's frozen points (one retry max, same session resumed, error
text verbatim, blindness held across both turns, key set unchanged, totals
summed) and deliberately not on the prompt wording the contract leaves
renegotiable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gen.config import load_config
from gen.frames import ClickCell, FrameCapture, FrameRecord
from gen.s3_verify import run_agent_pass

# --- synthetic worker -------------------------------------------------------

GAME_PY = '''"""Synthetic fixture game — never played, only staged and cited."""


class FixtureGame:
    def __init__(self):
        self.level_index = 0
'''

SOLVER_PY = '''"""Synthetic fixture solver — never played, only staged and cited."""


class FixtureSolver:
    def next_action(self, frame_data):
        return None
'''

# --- synthetic capture ------------------------------------------------------

# A click step's label as `gen/frames.py` writes it: the `step-<n>` prefix plus
# the described action. Citing only the prefix is the malformed case.
CLICK_LABEL = "step-3:ACTION6{'x': 4, 'y': 8}"
BAD_FRAME_REF = "step-3"

GRID_SIZE = 64


def _grid(offset: int) -> tuple[tuple[int, ...], ...]:
    """A deterministic 64x64 board inside the 0-15 palette."""
    return tuple(
        tuple((x + y + offset) % 16 for x in range(GRID_SIZE)) for y in range(GRID_SIZE)
    )


def _capture() -> FrameCapture:
    """Three records: `reset`, one click-form label, `final`."""
    return FrameCapture(
        game_id="synthetic-b002-hotfix1",
        source="solver",
        records=(
            FrameRecord(
                label="reset", seq=0, levels_completed=0, state="NOT_FINISHED", grid=_grid(0)
            ),
            FrameRecord(
                label=CLICK_LABEL,
                seq=1,
                levels_completed=1,
                state="NOT_FINISHED",
                grid=_grid(3),
            ),
            FrameRecord(label="final", seq=2, levels_completed=1, state="WIN", grid=_grid(7)),
        ),
        click_cells=(ClickCell(level_index=0, x=4, y=8, sprite_name="fixture_switch"),),
        available_action_ids=(1, 2, 3, 4, 5, 6),
        solver_actions=("ACTION1", "ACTION6{'x': 4, 'y': 8}", "ACTION1"),
        levels_completed=1,
        win=True,
    )


# --- synthetic replies ------------------------------------------------------


def _reply(frame_ref: str) -> str:
    """Prose plus ONE fenced json block; one claim is carried by `frame_ref`."""
    block = {
        "terms": [
            {
                "term": "move.grid",
                "reachable": True,
                "evidence": [{"path": "game.py", "line": 4, "note": "synthetic fixture"}],
                "frame_refs": ["reset"],
            },
            {
                "term": "goal.reach",
                "reachable": True,
                "evidence": [],
                "frame_refs": [frame_ref],
            },
        ],
        "dead_code": [],
        "deceptions": [],
        "enforcement": [],
        "notes": "synthetic fixture reply",
    }
    return "Fixture prose.\n\n```json\n" + json.dumps(block, indent=2) + "\n```\n"


CLEAN_REPLY = _reply(CLICK_LABEL)
MALFORMED_REPLY = _reply(BAD_FRAME_REF)

# --- per-turn accounting ----------------------------------------------------
# Deliberately DIFFERENT numbers per turn, so "sum" and "last turn wins" cannot
# be confused with each other by a coincidence of equal values.

TURN_ONE = {
    "session_id": "sess-fixture-first",
    "usd_cost": 0.50,
    "tokens_in": 11,
    "tokens_out": 23,
    "duration_s": 3.5,
}
TURN_TWO = {
    "session_id": "sess-fixture-second",
    "usd_cost": 1.25,
    "tokens_in": 7,
    "tokens_out": 13,
    "duration_s": 2.25,
}
TURN_ONE_NO_SESSION = dict(TURN_ONE, session_id=None)


# --- fake driver seam -------------------------------------------------------


class RecordingDriver:
    """The contract's driver seam: `.name` plus `.session(prompt, **kwargs)`.

    Records every call (prompt, kwargs) and snapshots the staged working copy
    it was pointed at, so a test can ask what the second turn was sent and
    whether anything under the staged copy moved between turns.
    """

    name = "localclaude"

    def __init__(self, replies, turns):
        assert len(replies) == len(turns), (
            "fixture error: RecordingDriver needs one accounting dict per reply, "
            f"got {len(replies)} replies and {len(turns)} turns"
        )
        self._replies = list(replies)
        self._turns = list(turns)
        self.calls: list[dict] = []

    def session(self, prompt, **kwargs):
        index = len(self.calls)
        if index >= len(self._replies):
            raise RuntimeError(
                f"driver.session called {index + 1} times: the blind pass is capped at "
                "ONE corrective retry, so it must never open a third turn"
            )
        staged = kwargs.get("cwd")
        self.calls.append(
            {
                "prompt": prompt,
                "kwargs": dict(kwargs),
                "staged": None if staged is None else Path(staged),
                "staged_tree": None if staged is None else _tree_snapshot(Path(staged)),
            }
        )
        turn = self._turns[index]
        return {
            "session_id": turn["session_id"],
            "usd_cost": turn["usd_cost"],
            "tokens_in": turn["tokens_in"],
            "tokens_out": turn["tokens_out"],
            "duration_s": turn["duration_s"],
            "text": self._replies[index],
        }


def _tree_snapshot(root: Path) -> dict[str, tuple[int, str, int]]:
    """Every file under `root` as (size, sha256, mtime_ns) — a blindness probe."""
    snapshot: dict[str, tuple[int, str, int]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        snapshot[str(path.relative_to(root))] = (
            len(data),
            hashlib.sha256(data).hexdigest(),
            path.stat().st_mtime_ns,
        )
    return snapshot


# --- harness ----------------------------------------------------------------


@pytest.fixture(scope="module")
def cfg() -> dict:
    return load_config("config/b001-pilot.yaml")


def _call(cfg: dict, root: Path, driver: RecordingDriver):
    """Stage a synthetic worker under `root` and run the real blind pass."""
    worker = root / "worker"
    worker.mkdir(parents=True)
    (worker / "game.py").write_text(GAME_PY, encoding="utf-8")
    (worker / "solver.py").write_text(SOLVER_PY, encoding="utf-8")
    out_dir = root / "out"
    out_dir.mkdir(parents=True)
    return run_agent_pass(cfg, worker, _capture(), out_dir=out_dir, driver=driver)


def _validator_message(cfg: dict, root: Path) -> str:
    """The validator's own text for MALFORMED_REPLY, captured — never hardcoded.

    Uses the no-session-id path, which the contract pins as "raise immediately":
    one turn, no retry, so what comes back is exactly the first turn's error.
    """
    driver = RecordingDriver([MALFORMED_REPLY], [TURN_ONE_NO_SESSION])
    with pytest.raises(ValueError) as excinfo:
        _call(cfg, root, driver)
    return str(excinfo.value)


# --- 1. malformed then clean ------------------------------------------------


def test_malformed_then_clean_retries_once_in_the_same_session(cfg, tmp_path):
    """One corrective retry: same session resumed, error verbatim, totals summed."""
    validator_message = _validator_message(cfg, tmp_path / "probe")

    driver = RecordingDriver([MALFORMED_REPLY, CLEAN_REPLY], [TURN_ONE, TURN_TWO])
    result = _call(cfg, tmp_path / "retry", driver)

    assert len(driver.calls) == 2, (
        "a malformed first reply must cost exactly ONE corrective retry: the blind pass "
        f"opened {len(driver.calls)} turn(s), expected 2"
    )

    first, second = driver.calls
    assert second["kwargs"].get("resume_id") == TURN_ONE["session_id"], (
        "the retry must RESUME the first session (the corrective prompt references a reply "
        f"only that conversation made): call 2 resume_id={second['kwargs'].get('resume_id')!r}, "
        f"expected {TURN_ONE['session_id']!r}"
    )
    resumed_kwargs = {k: v for k, v in second["kwargs"].items() if k != "resume_id"}
    assert resumed_kwargs == first["kwargs"], (
        "the retry must reuse the first turn's kwargs unchanged (same staged cwd, same model, "
        f"same tool scope) plus resume_id: call 1 {first['kwargs']!r} vs call 2 {resumed_kwargs!r}"
    )

    retry_prompt = second["prompt"]
    assert validator_message in retry_prompt, (
        "the retry prompt must carry the validator's message VERBATIM — the session cannot fix "
        f"a failure it is not told about. missing: {validator_message!r}"
    )
    assert BAD_FRAME_REF in retry_prompt, (
        f"the retry prompt must name the rejected frame_ref {BAD_FRAME_REF!r} so the session "
        "knows which citation was discarded"
    )
    assert "frame label" in retry_prompt, (
        "the retry prompt must carry the validator's phrase naming a frame label, so the "
        "session knows the failure is about a citation and not about its findings"
    )

    # The corrective INSTRUCTION, judged with the echoed error removed, so the
    # error text cannot satisfy this pin on the template's behalf.
    instruction = retry_prompt.replace(validator_message, "")
    assert "frame_refs" in instruction, (
        "the retry prompt's own instruction must name `frame_refs` as the field to correct; "
        "only the echoed validator message mentions it"
    )
    assert "exact" in instruction.lower() and "label" in instruction.lower(), (
        "the retry prompt must instruct the session to copy a frame LABEL EXACTLY as the digest "
        "prints it — that instruction is missing from the prompt's own text"
    )
    assert "json" in instruction.lower(), (
        "the retry prompt must ask for the corrected claims as one fenced json block; its own "
        "text never mentions json"
    )

    assert result["usd"] == pytest.approx(TURN_ONE["usd_cost"] + TURN_TWO["usd_cost"]), (
        "usd must SUM both turns (the retry really was paid for): got "
        f"{result['usd']!r}, expected {TURN_ONE['usd_cost'] + TURN_TWO['usd_cost']!r}"
    )
    assert result["tokens_in"] == TURN_ONE["tokens_in"] + TURN_TWO["tokens_in"], (
        f"tokens_in must SUM both turns: got {result['tokens_in']!r}, expected "
        f"{TURN_ONE['tokens_in'] + TURN_TWO['tokens_in']!r}"
    )
    assert result["tokens_out"] == TURN_ONE["tokens_out"] + TURN_TWO["tokens_out"], (
        f"tokens_out must SUM both turns: got {result['tokens_out']!r}, expected "
        f"{TURN_ONE['tokens_out'] + TURN_TWO['tokens_out']!r}"
    )
    assert result["wall_s"] == pytest.approx(TURN_ONE["duration_s"] + TURN_TWO["duration_s"]), (
        "wall_s must SUM both turns' durations: got "
        f"{result['wall_s']!r}, expected {TURN_ONE['duration_s'] + TURN_TWO['duration_s']!r}"
    )
    assert result["session_id"] == TURN_TWO["session_id"], (
        "session_id must come from the LAST turn that reported one: got "
        f"{result['session_id']!r}, expected {TURN_TWO['session_id']!r}"
    )

    clean_driver = RecordingDriver([CLEAN_REPLY], [TURN_ONE])
    clean_result = _call(cfg, tmp_path / "keys", clean_driver)
    assert set(result) == set(clean_result), (
        "the retry must not change the agent block's SCHEMA (validate_report pins it exactly): "
        f"retried run keys {sorted(result)} vs clean run keys {sorted(clean_result)}"
    )


# --- 2. clean first reply ---------------------------------------------------


def test_clean_first_reply_costs_exactly_one_turn(cfg, tmp_path):
    """Regression: zero behavior change on the happy path."""
    driver = RecordingDriver([CLEAN_REPLY], [TURN_ONE])
    result = _call(cfg, tmp_path / "clean", driver)

    assert len(driver.calls) == 1, (
        "a well-formed first reply must cost exactly ONE turn — the retry fired on a reply "
        f"that validated: {len(driver.calls)} turn(s) opened"
    )
    assert "resume_id" not in driver.calls[0]["kwargs"], (
        "the first turn must open a FRESH blind session, never resume one: kwargs carried "
        f"resume_id={driver.calls[0]['kwargs'].get('resume_id')!r}"
    )
    assert result["usd"] == pytest.approx(TURN_ONE["usd_cost"]), (
        f"usd on the happy path must be that one turn's cost: got {result['usd']!r}, "
        f"expected {TURN_ONE['usd_cost']!r}"
    )
    assert result["tokens_in"] == TURN_ONE["tokens_in"], (
        f"tokens_in on the happy path must be that one turn's: got {result['tokens_in']!r}, "
        f"expected {TURN_ONE['tokens_in']!r}"
    )
    assert result["tokens_out"] == TURN_ONE["tokens_out"], (
        f"tokens_out on the happy path must be that one turn's: got {result['tokens_out']!r}, "
        f"expected {TURN_ONE['tokens_out']!r}"
    )
    assert result["wall_s"] == pytest.approx(TURN_ONE["duration_s"]), (
        f"wall_s on the happy path must be that one turn's duration: got {result['wall_s']!r}, "
        f"expected {TURN_ONE['duration_s']!r}"
    )
    assert result["session_id"] == TURN_ONE["session_id"], (
        f"session_id on the happy path must be that turn's: got {result['session_id']!r}, "
        f"expected {TURN_ONE['session_id']!r}"
    )


# --- 3. malformed twice -----------------------------------------------------


def test_malformed_twice_raises_after_one_retry(cfg, tmp_path):
    """The retry is ONE retry: a second malformed reply raises, as before the fix."""
    driver = RecordingDriver([MALFORMED_REPLY, MALFORMED_REPLY], [TURN_ONE, TURN_TWO])
    with pytest.raises(ValueError) as excinfo:
        _call(cfg, tmp_path / "twice", driver)

    assert len(driver.calls) == 2, (
        "two malformed replies must cost exactly two turns — one corrective retry and no "
        f"more: {len(driver.calls)} turn(s) opened"
    )
    assert BAD_FRAME_REF in str(excinfo.value), (
        "the propagated error must still be the validator's own (the citation contract is not "
        f"loosened by the retry): got {str(excinfo.value)!r}"
    )


# --- 4. no session id on the first turn -------------------------------------


def test_missing_session_id_raises_without_a_fresh_retry(cfg, tmp_path):
    """No session to resume means no retry: a fresh session never made that reply."""
    driver = RecordingDriver([MALFORMED_REPLY], [TURN_ONE_NO_SESSION])
    with pytest.raises(ValueError):
        _call(cfg, tmp_path / "nosid", driver)

    assert len(driver.calls) == 1, (
        "with no session_id to resume there is nothing to correct, so the pass must raise on "
        f"the first turn instead of opening a blind-fresh one: {len(driver.calls)} turn(s) opened"
    )


# --- 5. blindness held across both turns ------------------------------------


def test_blindness_holds_across_the_retry_turn(cfg, tmp_path):
    """The staged copy is byte- and mtime-identical at both turns and after the run.

    Chosen probe (the contract offers two): snapshot every file under the staged
    working copy — size, sha256 and mtime_ns — inside each driver call and once
    the run returns, and require all three snapshots to match. `assert_unchanged`
    is the pipeline's own check; this one is independent of it.
    """
    driver = RecordingDriver([MALFORMED_REPLY, CLEAN_REPLY], [TURN_ONE, TURN_TWO])
    result = _call(cfg, tmp_path / "blind", driver)

    assert len(driver.calls) == 2, (
        f"this pin needs the retry path: {len(driver.calls)} turn(s) opened, expected 2"
    )
    first, second = driver.calls
    assert first["staged"] is not None, (
        "the blind session must be run inside the staged working copy (kwargs['cwd']); no cwd "
        "was passed, so blindness cannot be checked at all"
    )
    assert set(first["staged_tree"]) >= {"game.py", "solver.py"}, (
        "the staged copy must hold the worker's sources at the first turn; snapshot was "
        f"{sorted(first['staged_tree'])}"
    )
    assert second["staged"] == first["staged"], (
        "the retry must run in the SAME staged copy: "
        f"{second['staged']} vs {first['staged']}"
    )
    assert second["staged_tree"] == first["staged_tree"], (
        "the staged working copy changed between the first turn and the retry — the second "
        "turn must be as blind as the first (bytes and mtimes must match)"
    )
    after_run = _tree_snapshot(first["staged"])
    assert after_run == first["staged_tree"], (
        "the staged working copy changed by the end of the run — the verifier must leave the "
        "copy it audits untouched across BOTH turns"
    )
    assert result["staged_copy_verified"] is True, (
        "the pass must still report its own staged-copy verification after a retry: "
        f"staged_copy_verified={result['staged_copy_verified']!r}"
    )
