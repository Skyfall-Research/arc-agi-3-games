"""Blind pins for contract C-4a — confirmation audits.

Run: .venv/bin/python -m pytest gen/tests/test_b003_confirm.py -v

Written from the frozen C-4a contract ALONE (blind test writer).  The
pre-existing surfaces of `gen/s3_verify.py` and `gen/orchestrator.py` were read
BEFORE the implementer's hunks landed (the working tree at that moment carried
no `confirm_pass` / `confirmed_session` byte anywhere), and that pre-state is
what this file is built against.  What it is allowed to know, and does: the
corroboration machinery C-2/C-3 already shipped (`_lever_corroboration`,
`_term_corroboration`, `_lever_window`, `_term_window`, `read_lever_history`,
`read_term_history`, `lever_history_path`, `term_history_path`,
`compute_diff`, `assemble_report`, `validate_report`, `write_report`,
`OPTIONAL_REPORT_KEYS`, `AGENT_KEYS`, `DIFF_KEYS`, `REPORT_KEYS`), the
pre-C-4a shape of the `s3_verify` runner inside `orchestrator.default_runners()`
(capture once, one `run_agent_pass`, `compute_diff`, `assemble_report`, frames
+ report written, `_cost` off the one agent block, `_result`), the sibling
blind suites `test_b003_corrwindow.py` (planted slots through `assemble_report`)
and `test_b003_patchbaseline.py`, the runner-driving harness of
`test_r2_hotfix10.py`, the checked-in `toy_worker`, and the shipped reports
under `out/`.  These pins therefore describe the CONTRACT, not the
implementation, and are expected to fail until C-4a lands.

WHY THE CONFIRMATION ROUND EXISTS (operator ruling, restated from the contract)

"We need at least 2 audits with the same issue to take them seriously but if we
just run audit once then we'll never have 2 audits agreeing."  The
corroboration bar demotes a first sighting to a RECORDING, so a pass ends the
loop after ONE round and no second blind session ever looks at the recordings —
both b003r2 slots passed round 1 carrying them (their shipped reports still do,
and this file reads them as fixtures).  The rule: a pass whose diff carries ANY
uncorroborated recording gets ONE confirmation round; a pass with ZERO findings
stands alone, because a second round provably cannot change it (no claim to
corroborate, and its own new findings would be first sightings).  Exactly one
confirmation, never a third.

THE FIVE PINS, in the contract's order

1. `_confirm_pass(cfg)` — absent/False/True parse; non-bool => ValueError; True
   with BOTH corroboration knobs off => ValueError; True with either on =>
   accepted.  Plus `VERIFY_CONFIRM_KEY == "confirm_pass"`, read under
   `verifier:`.
2. Runner semantics, driven through `orchestrator.default_runners()["s3_verify"]`
   with a SCRIPTED `run_agent_pass` that counts invocations: knob off => always
   1 call; knob on + zero-finding round 1 => 1 call; knob on + recordings =>
   2 calls; a round-2 re-sighting (same term+direction, same lever) => the
   stage's ordinary reject shape; round-2 silence => pass, and the written
   report carries `confirmed_session` == the FIRST scripted session id; never a
   3rd call whatever round 2 contains.  Plus the contract's "same captured
   `cap` — capture once, audit twice".
3. Report: `confirmed_session` in `OPTIONAL_REPORT_KEYS`; `validate_report`
   accepts a valid one and rejects empty-string / non-string; absent on
   knob-off and on unconfirmed passes; the shipped b002 / b003r2 report
   artifacts still validate.
4. Cost: the stage result's cost equals the SUM of both scripted agents'
   usd/token numbers on a confirmed pass.
5. Sidecars: after a confirmed pass, the lever AND term histories carry TWO
   entries (append-per-`assemble_report` held).

AMBIGUITIES RESOLVED (each is quoted in the failure message that depends on it)

  a. `confirm_pass: null`.  The contract names `_lever_corroboration` as the
     pattern, and that reader raises on anything that is not a real `bool` —
     `None` included.  Pinned as ValueError in its own test
     (`test_pin1_null_is_not_the_absent_spelling`) so an adjudication the other
     way moves one line.  (C-2's `_lever_window` said "absent/null => None" out
     loud; C-4a says only "default False", and it names the BOOL reader.)
  b. "True while BOTH … are false => ValueError" is read as a rule about
     `True` ONLY: `confirm_pass: false` with both corroboration knobs off is a
     config that asks for nothing and gets nothing, not a contradiction.
     Pinned (`test_pin1_false_with_both_knobs_off_is_not_a_contradiction`).
  c. "both `_lever_corroboration(cfg)` and `_term_corroboration(cfg)` are
     false" covers an ABSENT knob as well as a `false` one — both readers
     already return False for an absent key, and a confirmation round with
     nothing recordable is the same contradiction either way.
  d. The ValueError MESSAGES are pinned only to the extent the contract's own
     precedents fix them: the type error names the key (the
     `_lever_corroboration` pattern it is told to follow) and the contradiction
     error names `confirm_pass` and at least one corroboration knob (the
     "window-knob contradiction rule, worded accordingly" it is told to copy).
     Each sits in its own test.
  e. `confirmed_session` on a CONFIRMED REJECT is not pinned either way.
     Contract §3 sets the key "before `write_report`" without distinguishing
     verdicts, while test-pin 3 lists only "knob-off and unconfirmed passes" as
     the absences.  This file asserts only the weak form — if the key is there,
     it is round 1's session id.  RECORDED GAP.
  f. `confirmed_session: null` is likewise not pinned: §2 says "a non-empty
     string", which excludes None, but the window keys it is told to be
     "validated like" DO allow null.  Its own test
     (`test_pin3_null_confirmed_session_is_rejected`) carries the strict
     reading, one line to move.
  g. Contract §1's "`diff` may be None on modes that skip it" is unreachable
     from the runner (full mode always builds a diff), so it is pinned in the
     form that IS reachable: the two `.get`-with-default halves, driven with
     one corroboration knob on and the other off, where the diff carries only
     ONE of the two `uncorroborated_*` keys.  A condition spelled `report
     ["diff"]["uncorroborated_terms"]` raises `KeyError` there.
  h. Contract §7's required splice COMMENT is the implementer's obligation and
     is not restated as a test (test-pin list 1-5 does not carry it).  Nor are
     §'s "full suite green + ruff clean" or the four-row proof table.
     RECORDED GAP, deliberately.
  i. Which agent block the WRITTEN report carries is pinned by identity
     (`session_id`, `claims`) rather than by its ledger numbers: §3 says the
     report is the confirmation round's, §4 says the STAGE's cost sums both, and
     nothing fixes whether round 2's `agent.usd` is its own or the sum.
     RECORDED GAP.

This file writes only inside `tmp_path`.  The canon, `out/`, the configs and
every other source file are read-only here.
"""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

from gen import frames as frames_module
from gen import orchestrator as orch
from gen import s3_static as static_module
from gen import s3_verify as verify_module
from gen.config import load_config

# b11's two standing guards (imported, never copied). pytest resolves a fixture
# by looking the name up in the REQUESTING module, so they are re-bound here.
from gen.tests import test_b11_pipeline as b11

_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"

# A real config, used ONLY as a base: it supplies `duckwm_docs`, the vocabulary
# root and `verifier.bfs_level_size_cap`. Every knob this file cares about is
# set or dropped explicitly by `_cfg`, so nothing here depends on what the
# shipped file happens to carry.
BASE_CONFIG = "config/b003r2-simplicity.yaml"
SHIPPED_CONFIGS = (
    "config/b001-pilot.yaml",
    "config/b002-triple.yaml",
    "config/b003-simplicity.yaml",
    "config/b003r2-simplicity.yaml",
)

# The shipped reports test-pin 3 names: the three b002 accepts and both b003r2
# passes — the two that carry the uncorroborated recordings this contract is
# about.
SHIPPED_REPORTS = (
    "out/corpus/b002-triple/pump-phase-time-echo/worker.verifier-report.json",
    "out/corpus/b002-triple/core-ward-phase-gates/worker.verifier-report.json",
    "out/corpus/b002-triple/convoy-in-the-fog/worker.verifier-report.json",
    "out/corpus/b003r2-simplicity/conduit-watch/worker.verifier-report.json",
    "out/corpus/b003r2-simplicity/mosaic-marble-bounce-to-match/worker.verifier-report.json",
)

# Contract wording, not code names.
VERIFIER_BLOCK = "verifier"
CONFIRM_KNOB = "confirm_pass"
CONFIRMED_KEY = "confirmed_session"
LEVER_KNOB = "lever_corroboration"
TERM_KNOB = "term_corroboration"
LEVER_WINDOW_KNOB = "lever_corroboration_window"
TERM_WINDOW_KNOB = "term_corroboration_window"

BATCH_ID = "b003-confirm-synthetic"
SLUG = "confirmation-fixture"
GAME_ID = SLUG

# The two reason strings §5 distinguishes.
REASON_PASS = "S2b clean"
REASON_CONFIRMED = "S2b clean (confirmed)"
REASON_REJECT_PREFIX = "verifier reject:"

# §4's own reject edge out of `implemented` — what the escalation counter reads
# (`orchestrator._verifier_rejects_against` matches on the EDGE, never on the
# reason text), so "an ordinary reject" means landing on exactly this state.
REJECT_STATE = "spec_ok"
VERIFIED_STATE = "verified"

# Three distinct signed terms and two distinct catalog levers.
SPEC_TERM = "move.grid"
EXTRA_TERM = "goal.sequence"
OTHER_TERM = "state.undo"
# PIN UPDATE, contract E-1 (2026-10-05): B was `"mimic"`, now a SPELLING of §7.1
# rather than a lever of its own, so it folds onto `look-alike` and is no longer
# in the catalog these fixtures check themselves against. B is that lever now —
# still the second of two DISTINCT levers, which is what the pins use it for.
LEVER_A = "decoy"
LEVER_B = "look-alike"

SYNTHETIC_NOTE = "synthetic fixture (C-4a blind pins)"

# Scripted per-round ledger numbers — distinct so a sum is not a coincidence.
ROUND_USD = (0.25, 0.75)
ROUND_TOKENS_IN = (1100, 2200)
ROUND_TOKENS_OUT = (11, 22)
SESSION_IDS = ("blind-session-round-1", "blind-session-round-2")

_ABSENT = object()


# --------------------------------------------------------------------------
# the surface under test, fetched rather than assumed
# --------------------------------------------------------------------------


def _confirm_reader():
    """`_confirm_pass` — the contract's own spelling for the reader."""
    reader = getattr(verify_module, "_confirm_pass", None)
    assert callable(reader), (
        "gen.s3_verify has no `_confirm_pass(cfg) -> bool`. C-4a §1 names it beside "
        f"`_lever_corroboration`, reading `{VERIFIER_BLOCK}.{CONFIRM_KNOB}`, default False, "
        "bool-validated ValueError"
    )
    return reader


def _confirm(cfg: Mapping) -> object:
    return _confirm_reader()(cfg)


def _confirm_key_const() -> str:
    key = getattr(verify_module, "VERIFY_CONFIRM_KEY", None)
    assert isinstance(key, str), (
        "gen.s3_verify has no module-level `VERIFY_CONFIRM_KEY` string. C-4a §1 names the "
        "constant, so the config spelling lives in one place"
    )
    return key


def _confirmed_key_const() -> str:
    key = getattr(verify_module, "CONFIRMED_SESSION_KEY", None)
    assert isinstance(key, str), (
        "gen.s3_verify has no module-level `CONFIRMED_SESSION_KEY` string. C-4a §1 names the "
        "constant, and `OPTIONAL_REPORT_KEYS` is supposed to carry it"
    )
    return key


def _cfg(
    base: Mapping,
    *,
    confirm: object = _ABSENT,
    lever: object = _ABSENT,
    term: object = _ABSENT,
    lever_window: object = _ABSENT,
    term_window: object = _ABSENT,
) -> dict:
    """A config with the three knobs (and the two windows) forced or absent.

    `verifier.exempt_terms` is DROPPED: the b002 exemption ruling is a separate
    knob with its own suite, and a diff this file reasons about must carry only
    what this contract puts in it.
    """
    cfg = copy.deepcopy(dict(base))
    verifier = dict(cfg.get(VERIFIER_BLOCK) or {})
    for key in (CONFIRM_KNOB, LEVER_KNOB, TERM_KNOB, LEVER_WINDOW_KNOB, TERM_WINDOW_KNOB,
                "exempt_terms"):
        verifier.pop(key, None)
    for key, value in (
        (CONFIRM_KNOB, confirm),
        (LEVER_KNOB, lever),
        (TERM_KNOB, term),
        (LEVER_WINDOW_KNOB, lever_window),
        (TERM_WINDOW_KNOB, term_window),
    ):
        if value is not _ABSENT:
            verifier[key] = value
    cfg[VERIFIER_BLOCK] = verifier
    return cfg


def _bare(**kwargs: object) -> dict:
    """The same, with no surrounding run config — the reader needs only the
    `verifier` block, exactly as `_lever_corroboration` needs only it."""
    return _cfg({}, **kwargs)


# --------------------------------------------------------------------------
# synthetic claims, spec and the scripted blind pass
# --------------------------------------------------------------------------


def _evidence() -> list[dict]:
    return [{"path": "game.py", "line": 10, "note": SYNTHETIC_NOTE}]


def _claims(*, terms: tuple[str, ...] = (SPEC_TERM,), levers: tuple[str, ...] = ()) -> dict:
    """One blind session's claims: every term reachable, every lever cited."""
    return {
        "terms": [
            {"term": term, "reachable": True, "evidence": _evidence()} for term in terms
        ],
        "dead_code": [],
        "deceptions": [{"lever": lever, "evidence": _evidence()} for lever in levers],
        "enforcement": [],
        "notes": SYNTHETIC_NOTE,
    }


#: Round shapes, by what they do to the diff against SPEC_YAML below.
CLEAN = _claims()                                       # nothing to record at all
TERM_FINDING = _claims(terms=(SPEC_TERM, EXTRA_TERM))   # one undeclared term
OTHER_TERM_FINDING = _claims(terms=(SPEC_TERM, OTHER_TERM))
LEVER_FINDING = _claims(levers=(LEVER_A,))              # one undeclared lever
OTHER_LEVER_FINDING = _claims(levers=(LEVER_B,))

SPEC_YAML = f"""\
game:
  terms: [{SPEC_TERM}]
  knobs:
    deceptions: []
"""


class _ScriptedPass:
    """`run_agent_pass`, replaced by a script — and an invocation counter.

    The script holds one claims block per ROUND the contract allows. A call
    past the end of the script is the "never a third" failure and is raised as
    such, so an implementation that recurses fails loudly instead of quietly
    spending a session that does not exist.
    """

    def __init__(self, *rounds: dict) -> None:
        self.rounds = list(rounds)
        self.calls: list[dict] = []

    def __call__(self, cfg, worker, cap, *, out_dir, driver=None) -> dict:
        index = len(self.calls)
        self.calls.append({"cfg": cfg, "worker": Path(worker), "cap": cap,
                           "out_dir": Path(out_dir)})
        assert index < len(self.rounds), (
            f"run_agent_pass was called {index + 1} time(s); this script has "
            f"{len(self.rounds)} round(s). C-4a §6: EXACTLY one confirmation — the "
            "confirmation round's own result is final whatever it contains, and nothing "
            "recurses"
        )
        return {
            "session_id": SESSION_IDS[index] if index < len(SESSION_IDS) else f"round-{index}",
            "model": "scripted",
            "usd": ROUND_USD[index],
            "tokens_in": ROUND_TOKENS_IN[index],
            "tokens_out": ROUND_TOKENS_OUT[index],
            "wall_s": 1.0,
            "staged_copy_verified": True,
            "claims": self.rounds[index],
        }

    @property
    def count(self) -> int:
        return len(self.calls)


class _CountedCapture:
    """`frames.capture_worker_isolated`, replaced by one shared capture.

    The contract's "same captured `cap` — capture once, audit twice" is a claim
    about BOTH the number of captures and the identity of the object handed to
    each audit, so both are recorded here.
    """

    def __init__(self, cap: object) -> None:
        self.cap = cap
        self.calls: list[Path] = []

    def __call__(self, worker_dir, *args, **kwargs) -> object:
        self.calls.append(Path(worker_dir))
        return self.cap

    @property
    def count(self) -> int:
        return len(self.calls)


class _Drive:
    """One planted slot plus the wiring to run the REAL `s3_verify` runner.

    Everything expensive is replaced: the capture (one object, counted), the
    three static legs (no checks — this contract is about the audit round, not
    the static ones) and the blind pass (scripted, counted). `compute_diff`,
    `assemble_report`, `write_report`, the corroboration machinery and the two
    sidecars are the REAL ones, because they are what the confirmation round is
    judged by.
    """

    def __init__(self, tmp_path: Path, monkeypatch, cap: object, *rounds: dict) -> None:
        self.spec_dir = tmp_path / "corpus" / BATCH_ID / SLUG
        self.worker = self.spec_dir / orch.WORKER_DIRNAME
        shutil.copytree(TOY_WORKER, self.worker,
                        ignore=shutil.ignore_patterns("__pycache__"))
        (self.spec_dir / "spec.yaml").write_text(SPEC_YAML, encoding="utf-8")
        self.tmp_path = tmp_path

        self.agent = _ScriptedPass(*rounds)
        self.capture = _CountedCapture(cap)
        monkeypatch.setattr(verify_module, "run_agent_pass", self.agent)
        monkeypatch.setattr(frames_module, "capture_worker_isolated", self.capture)
        for leg in ("run_static_checks", "run_required_rows", "run_solver_quality"):
            monkeypatch.setattr(static_module, leg, lambda *a, **k: [])

    # -- the paths the runner writes to (spelled through s3_verify's suffixes)
    @property
    def report_path(self) -> Path:
        return self.worker.with_name(self.worker.name + verify_module.REPORT_SUFFIX)

    @property
    def frames_path(self) -> Path:
        return self.worker.with_name(self.worker.name + verify_module.FRAMES_SUFFIX)

    def ctx(self, cfg: Mapping) -> orch.SlotContext:
        """The ctx §4 hands `s3_verify` at `implemented`, built under tmp_path.

        The history is EMPTY on purpose: `_latched_verify` re-serves a recorded
        accept of identical bytes, and a latched round runs no audit at all.
        """
        ideas = self.tmp_path / "ideas" / BATCH_ID
        ideas.mkdir(parents=True, exist_ok=True)
        return orch.SlotContext(
            cfg=cfg,
            batch_id=BATCH_ID,
            slug=SLUG,
            index=1,
            state="implemented",
            stage="s3_verify",
            attempt=1,
            batch_dir=self.tmp_path / "batches" / BATCH_ID,
            ideas_dir=ideas,
            idea_path=ideas / "idea-001.json",
            corpus_dir=self.spec_dir.parent,
            spec_dir=self.spec_dir,
            respec_count=0,
            verifier_rejects=0,
            green_failures=0,
            history=(),
        )

    def run(self, cfg: Mapping) -> dict:
        runners = orch.default_runners()
        assert "s3_verify" in runners, (
            f"default_runners() must key S2b as 's3_verify'; it has {sorted(runners)}"
        )
        return runners["s3_verify"](self.ctx(cfg))

    def written_report(self) -> dict:
        assert self.report_path.is_file(), (
            f"the runner wrote no report at {self.report_path} — C-4a §3 writes the "
            "CONFIRMATION round's report there"
        )
        return json.loads(self.report_path.read_text(encoding="utf-8"))

    def lever_entries(self) -> list:
        return verify_module.read_lever_history(verify_module.lever_history_path(self.worker))

    def term_entries(self) -> list:
        return verify_module.read_term_history(verify_module.term_history_path(self.worker))


def _codes(result: Mapping) -> str:
    return result.get("reason") or ""


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="session")
def cap() -> object:
    """A real FrameCapture from the checked-in toy worker (the corrwindow
    precedent) — `capture_to_json` runs on it for real in the runner."""
    game_cls, solver_cls = verify_module.load_worker_classes(TOY_WORKER)
    return verify_module.capture(game_cls, solver_cls)


@pytest.fixture(scope="session")
def base_cfg() -> dict:
    cfg = load_config(BASE_CONFIG)
    assert isinstance(cfg.get(VERIFIER_BLOCK), Mapping), (
        f"fixture wall: {BASE_CONFIG} no longer carries a `{VERIFIER_BLOCK}` block"
    )
    assert CONFIRM_KNOB not in cfg[VERIFIER_BLOCK], (
        f"fixture wall: {BASE_CONFIG} now sets `{VERIFIER_BLOCK}.{CONFIRM_KNOB}` — every pin "
        "here assumes the shipped configs opt into nothing"
    )
    for term in (SPEC_TERM, EXTRA_TERM, OTHER_TERM):
        assert term in verify_module.signed_vocab(), (
            f"fixture wall: {term!r} left the signed vocabulary"
        )
    for lever in (LEVER_A, LEVER_B):
        assert lever in verify_module.DECEPTION_CATALOG, (
            f"fixture wall: {lever!r} left the signed deception catalog"
        )
    return cfg


@pytest.fixture(scope="session")
def shipped_report() -> dict:
    """One shipped, valid b7.1 report to hang the `validate_report` pins on."""
    path = REPO_ROOT / SHIPPED_REPORTS[0]
    assert path.is_file(), f"fixture wall: {path} is gone"
    report = json.loads(path.read_text(encoding="utf-8"))
    verify_module.validate_report(copy.deepcopy(report))
    return report


def _with_key(report: Mapping, value: object) -> dict:
    out = copy.deepcopy(dict(report))
    out[CONFIRMED_KEY] = value
    return out


# ==========================================================================
# PIN 1 — `_confirm_pass`, the knob
# ==========================================================================


def test_pin1_key_constant_is_confirm_pass_under_verifier() -> None:
    """C-4a §1: `VERIFY_CONFIRM_KEY = "confirm_pass"` under `verifier:`."""
    assert _confirm_key_const() == CONFIRM_KNOB, (
        f"VERIFY_CONFIRM_KEY is {_confirm_key_const()!r}; C-4a §1 freezes the config spelling "
        f"as {CONFIRM_KNOB!r}"
    )


def test_pin1_absent_knob_is_false() -> None:
    """Knob absent ⇒ byte-identical behavior, and that starts with the reader
    saying False rather than raising."""
    assert _confirm({}) is False, (
        "a config with no `verifier` block at all must read False — an opt-in knob cannot "
        "require a block older batch configs never wrote"
    )
    assert _confirm(_bare()) is False
    assert _confirm({VERIFIER_BLOCK: {"reject_cap": 2}}) is False


def test_pin1_shipped_configs_read_false() -> None:
    """The real, frozen batch configs opt into nothing: the pilot and b002 are
    pre-corroboration, b003r2 runs BOTH corroboration passes — and none of them
    asks for a second blind session."""
    for name in SHIPPED_CONFIGS:
        path = REPO_ROOT / name
        if not path.is_file():   # a config that was never committed is not a pin
            continue
        cfg = load_config(name)
        assert _confirm(cfg) is False, (
            f"{name} reads the confirmation knob as ON without setting it — 'knob absent ⇒ "
            "byte-identical behavior' is the whole default, and a silent second blind "
            "session doubles every accepted slot's audit bill"
        )


def test_pin1_false_parses_with_either_corroboration_knob() -> None:
    assert _confirm(_bare(confirm=False, lever=True)) is False
    assert _confirm(_bare(confirm=False, term=True)) is False


@pytest.mark.parametrize(
    ("lever", "term"),
    [(True, _ABSENT), (_ABSENT, True), (True, True), (True, False), (False, True)],
    ids=["lever-only", "term-only", "both", "lever-on-term-off", "lever-off-term-on"],
)
def test_pin1_true_is_accepted_while_either_pass_runs(lever: object, term: object) -> None:
    """C-4a §1: "True with either on ⇒ accepted" — one recordable pass is
    enough, because one uncorroborated recording is all the confirmation round
    needs to have something to confirm."""
    assert _confirm(_bare(confirm=True, lever=lever, term=term)) is True


@pytest.mark.parametrize(
    "value", ["true", "false", "yes", "no", "", 1, 0, 1.0, [], {}, ["x"], "1"]
)
def test_pin1_every_non_bool_is_a_loud_valueerror(value: object) -> None:
    """"bool-validated ValueError (the `_lever_corroboration` pattern)" — and
    that pattern refuses exactly these: a truthy string or a 1 would silently
    buy a second paid blind session per accepted slot.

    Driven with `lever_corroboration` ON, so the TYPE rule is isolated from the
    contradiction rule below.
    """
    with pytest.raises(ValueError):
        _confirm(_bare(confirm=value, lever=True))


def test_pin1_null_is_not_the_absent_spelling() -> None:
    """Ambiguity a, on its own line.

    C-4a §1 names `_lever_corroboration` as the pattern, and that reader raises
    on anything that is not a real `bool` — `None` included. C-2's WINDOW
    reader said "absent/null => None" out loud; this contract says only
    "default False" and points at the bool reader. If the lead adjudicates null
    as the absent spelling, this is the one line to change.
    """
    with pytest.raises(ValueError):
        _confirm(_bare(confirm=None, lever=True))


def test_pin1_type_error_names_the_key() -> None:
    """Ambiguity d: the named pattern's message names the key it read, so a bad
    batch config is fixable from the failure alone."""
    with pytest.raises(ValueError) as caught:
        _confirm(_bare(confirm="true", lever=True))
    assert CONFIRM_KNOB in str(caught.value), (
        f"the type error does not name `{VERIFIER_BLOCK}.{CONFIRM_KNOB}`: {caught.value!r}. "
        "C-4a §1 says to follow the `_lever_corroboration` pattern, whose message names the "
        "knob it refuses"
    )


@pytest.mark.parametrize(
    ("lever", "term"),
    [(_ABSENT, _ABSENT), (False, False), (False, _ABSENT), (_ABSENT, False)],
    ids=["both-absent", "both-false", "lever-false-term-absent", "lever-absent-term-false"],
)
def test_pin1_true_with_both_corroboration_passes_off_is_a_contradiction(
    lever: object, term: object
) -> None:
    """C-4a §1: nothing can be RECORDED, so there is nothing to confirm.

    Ambiguity c: an absent corroboration knob is a false one — both readers
    already say so, and a confirmation round with no recordings is the same
    contradiction either way.
    """
    with pytest.raises(ValueError):
        _confirm(_bare(confirm=True, lever=lever, term=term))


def test_pin1_contradiction_error_names_the_knobs_it_is_about() -> None:
    """Ambiguity d: "the window-knob contradiction rule, worded accordingly".
    That rule's message names both halves — the knob that was set and the pass
    it has nothing to narrow — so this one names `confirm_pass` and at least
    one corroboration knob."""
    with pytest.raises(ValueError) as caught:
        _confirm(_bare(confirm=True))
    message = str(caught.value)
    assert CONFIRM_KNOB in message, (
        f"the contradiction error does not name {CONFIRM_KNOB!r}: {message!r}"
    )
    assert LEVER_KNOB in message or TERM_KNOB in message, (
        f"the contradiction error names neither {LEVER_KNOB!r} nor {TERM_KNOB!r}: {message!r}. "
        "The `_lever_window` contradiction message names the pass it has nothing to narrow, "
        "and C-4a §1 says to word this one accordingly"
    )


def test_pin1_false_with_both_knobs_off_is_not_a_contradiction() -> None:
    """Ambiguity b, on its own line: the contradiction rule is about TRUE only.
    `confirm_pass: false` with neither corroboration pass running is a config
    that asks for nothing — which is also the canon default, spelled out."""
    assert _confirm(_bare(confirm=False)) is False
    assert _confirm(_bare(confirm=False, lever=False, term=False)) is False


def test_pin1_the_knob_is_read_under_verifier_only() -> None:
    """C-4a §1 puts it under `verifier:`. A top-level `confirm_pass` is a
    config that did not set this knob."""
    assert _confirm({CONFIRM_KNOB: True}) is False, (
        f"a top-level {CONFIRM_KNOB!r} turned the confirmation round on; C-4a §1 reads it "
        f"under `{VERIFIER_BLOCK}:` beside the two corroboration knobs"
    )


def test_pin1_reader_works_on_a_real_config(base_cfg: dict) -> None:
    """Set on a real config, on a real `verifier` block beside the corroboration
    knobs the b003r2 batch already runs."""
    cfg = _cfg(base_cfg, confirm=True, lever=True, term=True,
               lever_window=1, term_window=1)
    assert cfg[VERIFIER_BLOCK]["reject_cap"] == base_cfg[VERIFIER_BLOCK]["reject_cap"]
    assert _confirm(cfg) is True
    assert _confirm(_cfg(base_cfg, confirm=False, lever=True, term=True)) is False


# ==========================================================================
# PIN 2 — runner semantics, through the REAL s3_verify runner
# ==========================================================================


def _on(base: Mapping) -> dict:
    """Knob ON, both corroboration passes on, both windows at 1 (b003r2's own
    setting, and the window the contract reasons with: "window 1 sees exactly
    round 1")."""
    return _cfg(base, confirm=True, lever=True, term=True, lever_window=1, term_window=1)


def _off(base: Mapping) -> dict:
    """Knob absent, corroboration unchanged — the canon default this contract
    promises to leave byte-identical."""
    return _cfg(base, lever=True, term=True, lever_window=1, term_window=1)


@pytest.mark.parametrize(
    "rounds",
    [(CLEAN,), (TERM_FINDING,), (LEVER_FINDING,)],
    ids=["clean", "term-recording", "lever-recording"],
)
def test_pin2_knob_off_is_always_exactly_one_blind_session(
    tmp_path, monkeypatch, cap, base_cfg, rounds
) -> None:
    """(a) knob off ⇒ 1 pass call, whatever round 1 recorded.

    The script holds ONE round, so a second call fails loudly rather than
    silently reading a round that does not exist.
    """
    drive = _Drive(tmp_path, monkeypatch, cap, *rounds)
    result = drive.run(_off(base_cfg))

    assert drive.agent.count == 1, (
        f"the knob is absent and run_agent_pass ran {drive.agent.count} times — 'knob absent "
        "⇒ byte-identical behavior' (C-4a header) means one blind session per round"
    )
    assert result["ok"] is True and result["to_state"] == VERIFIED_STATE
    assert result["reason"] == REASON_PASS, (
        f"a knob-off pass keeps today's reason {REASON_PASS!r}; got {result['reason']!r}"
    )


def test_pin2_knob_off_report_carries_no_confirmed_session(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """(a), on disk: the knob-off report is exactly the report it was — the
    optional key that records a second session is not in it."""
    drive = _Drive(tmp_path, monkeypatch, cap, TERM_FINDING)
    drive.run(_off(base_cfg))
    report = drive.written_report()

    assert CONFIRMED_KEY not in report, (
        f"a knob-off round recorded {CONFIRMED_KEY!r}; that key is the trace of a SECOND blind "
        "session, and this round bought one"
    )
    assert report["agent"]["session_id"] == SESSION_IDS[0]
    assert report["verdict"] == "pass"


def test_pin2_knob_off_is_deterministic_across_two_identical_runs(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """(a) restated as the property a byte-identity claim can actually be
    tested as here: two identical knob-off rounds, in two planted slots, write
    the same report — path fields aside."""
    def once(root: Path) -> dict:
        drive = _Drive(root, monkeypatch, cap, TERM_FINDING)
        drive.run(_off(base_cfg))
        report = drive.written_report()
        report.pop("worker")
        return report

    first = once(tmp_path / "a")
    second = once(tmp_path / "b")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert set(first) <= set(verify_module.REPORT_KEYS) | set(
        verify_module.OPTIONAL_REPORT_KEYS
    )


def test_pin2_knob_on_with_a_zero_finding_round_one_stands_alone(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """(b) knob on + round 1 clean (its claims match the spec exactly) ⇒ 1 call,
    no `confirmed_session`.

    C-4a header: "a pass with ZERO findings stands alone (a second round
    provably cannot change it — no claim to corroborate, and its own new
    findings would be first sightings)".
    """
    drive = _Drive(tmp_path, monkeypatch, cap, CLEAN)
    result = drive.run(_on(base_cfg))

    assert drive.agent.count == 1, (
        f"a zero-finding pass bought {drive.agent.count} blind sessions; C-4a spends the "
        "second one ONLY on a pass carrying an uncorroborated recording"
    )
    assert result["ok"] is True and result["to_state"] == VERIFIED_STATE
    assert result["reason"] == REASON_PASS, (
        f"an UNCONFIRMED pass keeps the existing reason {REASON_PASS!r} — {REASON_CONFIRMED!r} "
        f"is §5's reason for a pass AFTER confirmation; got {result['reason']!r}"
    )
    report = drive.written_report()
    assert CONFIRMED_KEY not in report, (
        f"a pass that stands alone recorded {CONFIRMED_KEY!r} — there was no second session "
        "to name"
    )
    assert report["diff"]["uncorroborated_terms"] == []
    assert report["diff"]["uncorroborated_levers"] == []


@pytest.mark.parametrize(
    "recording",
    [TERM_FINDING, LEVER_FINDING],
    ids=["uncorroborated-term", "uncorroborated-lever"],
)
def test_pin2_a_recording_buys_exactly_one_confirmation(
    tmp_path, monkeypatch, cap, base_cfg, recording
) -> None:
    """(c)/(d) first half: knob on + round-1 recordings ⇒ 2 calls.

    Either list is enough — §1's condition is `uncorroborated_levers` OR
    `uncorroborated_terms` non-empty.
    """
    drive = _Drive(tmp_path, monkeypatch, cap, recording, CLEAN)
    drive.run(_on(base_cfg))

    assert drive.agent.count == 2, (
        f"round 1 passed carrying an uncorroborated recording and run_agent_pass ran "
        f"{drive.agent.count} time(s) — C-4a: that pass buys ONE confirmation round"
    )


def test_pin2_the_confirmation_round_reuses_round_ones_capture(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """C-4a §2: "same captured `cap` — capture once, audit twice".

    The capture spawns a fresh interpreter and drives the solver (R2 hotfix #8);
    re-capturing would also re-roll the frames the second audit cites.
    """
    drive = _Drive(tmp_path, monkeypatch, cap, TERM_FINDING, CLEAN)
    drive.run(_on(base_cfg))

    assert drive.agent.count == 2
    assert drive.capture.count == 1, (
        f"the worker was captured {drive.capture.count} times for one round; C-4a §2 captures "
        "ONCE and audits twice"
    )
    first, second = drive.agent.calls
    assert first["cap"] is second["cap"], (
        "the confirmation round was handed a different capture object than round 1"
    )
    assert first["worker"] == second["worker"]
    assert first["out_dir"] == second["out_dir"] == drive.worker.parent, (
        "C-4a §2 spells the second call `run_agent_pass(ctx.cfg, worker, cap, "
        "out_dir=worker.parent)` — the same arguments round 1 was given"
    )


def test_pin2_a_round_two_term_resighting_rejects(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """(c) round 2 re-sights the same term in the same direction ⇒ 2 calls and
    the stage's ORDINARY reject.

    Round 1's sidecar entry is already appended when round 2 reads the history,
    so window 1 sees exactly round 1 and the re-sighting corroborates — the
    existing machinery does the work, unchanged (§2).
    """
    drive = _Drive(tmp_path, monkeypatch, cap, TERM_FINDING, TERM_FINDING)
    result = drive.run(_on(base_cfg))

    assert drive.agent.count == 2
    assert result["ok"] is False, "a corroborated undeclared term is a reject"
    assert result["to_state"] == REJECT_STATE, (
        f"the confirmation round's reject must travel §4's ordinary "
        f"`implemented --> {REJECT_STATE}` edge — that edge IS the ×2 escalation counter "
        f"(`_verifier_rejects_against`); got {result['to_state']!r}"
    )
    assert _codes(result).startswith(REASON_REJECT_PREFIX), (
        f"C-4a §5: the reject path's reason PREFIX is unchanged, so the reject loop reads it "
        f"as an ordinary reject; got {_codes(result)!r}"
    )
    assert verify_module.REJECT_UNDECLARED_TERM in _codes(result), (
        f"the reject does not name {verify_module.REJECT_UNDECLARED_TERM!r}: {_codes(result)!r}"
    )
    report = drive.written_report()
    assert report["verdict"] == "reject"
    assert EXTRA_TERM in report["diff"]["undeclared_terms"], (
        f"{EXTRA_TERM!r} was corroborated by round 1 and must be back in the reject-bearing "
        "list, not in the uncorroborated record"
    )


def test_pin2_a_round_two_lever_resighting_rejects(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """(c), the lever half — the class the corroboration bar was built for."""
    drive = _Drive(tmp_path, monkeypatch, cap, LEVER_FINDING, LEVER_FINDING)
    result = drive.run(_on(base_cfg))

    assert drive.agent.count == 2
    assert result["ok"] is False and result["to_state"] == REJECT_STATE
    assert verify_module.REJECT_UNDECLARED_DECEPTION in _codes(result), (
        f"the reject does not name {verify_module.REJECT_UNDECLARED_DECEPTION!r}: "
        f"{_codes(result)!r}"
    )
    assert LEVER_A in drive.written_report()["diff"]["undeclared_deceptions"]


def test_pin2_round_two_silence_leaves_the_pass_standing(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """(d) round 2 clean ⇒ 2 calls, PASS, and §5's confirmed reason."""
    drive = _Drive(tmp_path, monkeypatch, cap, TERM_FINDING, CLEAN)
    result = drive.run(_on(base_cfg))

    assert drive.agent.count == 2
    assert result["ok"] is True and result["to_state"] == VERIFIED_STATE
    assert result["reason"] == REASON_CONFIRMED, (
        f"C-4a §5 distinguishes the paths: a pass AFTER confirmation reads "
        f"{REASON_CONFIRMED!r}; got {result['reason']!r}"
    )


def test_pin2_the_written_report_is_the_confirmation_rounds(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """(d) §3: the report on disk is ROUND 2's, carrying `confirmed_session` ==
    round 1's session id.

    Round 1's full report is deliberately not kept — its findings live in the
    sidecars, which is the design's premise — so the two rounds are told apart
    by identity: round 2's session id and round 2's claims.
    """
    drive = _Drive(tmp_path, monkeypatch, cap, TERM_FINDING, CLEAN)
    drive.run(_on(base_cfg))
    report = drive.written_report()

    assert report["agent"]["session_id"] == SESSION_IDS[1], (
        "the report on disk is round 1's — C-4a §3 writes the CONFIRMATION round's report"
    )
    assert report["agent"]["claims"] == CLEAN, (
        "the report carries round 1's claims; §3 writes the confirmation round's"
    )
    assert report[CONFIRMED_KEY] == SESSION_IDS[0], (
        f"report.{CONFIRMED_KEY} must be ROUND 1's session id, so the run log names BOTH "
        f"blind sessions; got {report.get(CONFIRMED_KEY)!r}"
    )
    assert report["verdict"] == "pass" and report["reject_reasons"] == []
    assert report["diff"]["undeclared_terms"] == [], (
        f"{EXTRA_TERM!r} was never re-sighted, so it stays demoted"
    )
    on_disk = sorted(path.name for path in drive.spec_dir.rglob("*verifier-report.json"))
    assert on_disk == [drive.report_path.name], (
        f"the slot carries {on_disk} — §3 keeps ONLY the confirmation round's report; round "
        "1's findings live in the two sidecars, which is the design's premise"
    )


def test_pin2_never_a_third_session_when_round_two_finds_something_new(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """C-4a §6: EXACTLY one confirmation — the confirmation round's own result
    is final whatever it contains; no recursion.

    Round 2 names a DIFFERENT lever, so its own finding is a first sighting and
    is demoted exactly as round 1's was: the pass now carries an uncorroborated
    recording again, which is precisely the state that bought round 2. A
    recursive implementation asks for round 3 and the script raises.
    """
    drive = _Drive(tmp_path, monkeypatch, cap, LEVER_FINDING, OTHER_LEVER_FINDING)
    result = drive.run(_on(base_cfg))

    assert drive.agent.count == 2, (
        f"run_agent_pass ran {drive.agent.count} times; §6 allows exactly two"
    )
    assert result["ok"] is True and result["reason"] == REASON_CONFIRMED
    report = drive.written_report()
    assert report[CONFIRMED_KEY] == SESSION_IDS[0]
    assert [entry["lever"] for entry in report["diff"]["uncorroborated_levers"]] == [LEVER_B], (
        "round 2's own new lever is a first sighting and is recorded, not rejected on — and "
        "recording it does NOT buy a third round"
    )


def test_pin2_never_a_third_session_when_round_two_finds_a_new_term(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """§6 again, the term half: round 2 rotates to a different term."""
    drive = _Drive(tmp_path, monkeypatch, cap, TERM_FINDING, OTHER_TERM_FINDING)
    result = drive.run(_on(base_cfg))

    assert drive.agent.count == 2
    assert result["ok"] is True and result["reason"] == REASON_CONFIRMED
    assert [entry["term"] for entry in
            drive.written_report()["diff"]["uncorroborated_terms"]] == [OTHER_TERM]


def test_pin2_lever_pass_only_reads_the_lever_list(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """Ambiguity g / §1: "The diff keys are OPTIONAL — use .get with a default."

    With `term_corroboration` OFF the diff carries NO `uncorroborated_terms`
    key at all, so a condition that subscripts it raises `KeyError` here.
    """
    cfg = _cfg(base_cfg, confirm=True, lever=True, term=False, lever_window=1)
    drive = _Drive(tmp_path, monkeypatch, cap, LEVER_FINDING, CLEAN)
    result = drive.run(cfg)

    assert "uncorroborated_terms" not in drive.written_report()["diff"], (
        "fixture wall: with term_corroboration off the diff must not carry the term record"
    )
    assert drive.agent.count == 2, (
        "an uncorroborated LEVER on its own buys the confirmation round — §1's condition is "
        "an OR over two optional keys"
    )
    assert result["reason"] == REASON_CONFIRMED


def test_pin2_term_pass_only_reads_the_term_list(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """The mirror of the test above: `lever_corroboration` off, so
    `uncorroborated_levers` is the missing key."""
    cfg = _cfg(base_cfg, confirm=True, lever=False, term=True, term_window=1)
    drive = _Drive(tmp_path, monkeypatch, cap, TERM_FINDING, CLEAN)
    result = drive.run(cfg)

    assert "uncorroborated_levers" not in drive.written_report()["diff"], (
        "fixture wall: with lever_corroboration off the diff must not carry the lever record"
    )
    assert drive.agent.count == 2
    assert result["reason"] == REASON_CONFIRMED


def test_pin2_a_round_one_reject_never_buys_a_confirmation(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """§1's condition is `report["verdict"] == "pass"`.

    Round 1 here names a lever while `lever_corroboration` is OFF, so the
    finding rejects on sight: a reject already re-runs the whole stage through
    the reject loop, and confirming one would pay for a round the loop is about
    to buy anyway.
    """
    cfg = _cfg(base_cfg, confirm=True, lever=False, term=True, term_window=1)
    drive = _Drive(tmp_path, monkeypatch, cap, LEVER_FINDING)
    result = drive.run(cfg)

    assert drive.agent.count == 1, (
        f"a round-1 REJECT bought {drive.agent.count} blind sessions; C-4a confirms PASSES"
    )
    assert result["ok"] is False and result["to_state"] == REJECT_STATE
    assert _codes(result).startswith(REASON_REJECT_PREFIX)


# ==========================================================================
# PIN 3 — `confirmed_session` in the report schema
# ==========================================================================


def test_pin3_constant_is_confirmed_session_and_joins_the_optional_keys() -> None:
    """C-4a §1: `CONFIRMED_SESSION_KEY = "confirmed_session"` joins
    `OPTIONAL_REPORT_KEYS`."""
    assert _confirmed_key_const() == CONFIRMED_KEY, (
        f"CONFIRMED_SESSION_KEY is {_confirmed_key_const()!r}; C-4a §1 freezes it as "
        f"{CONFIRMED_KEY!r}"
    )
    assert CONFIRMED_KEY in verify_module.OPTIONAL_REPORT_KEYS, (
        f"{CONFIRMED_KEY!r} is not in OPTIONAL_REPORT_KEYS "
        f"{list(verify_module.OPTIONAL_REPORT_KEYS)} — `validate_report` builds the allowed "
        "extra-key set from that tuple, so a report carrying the key would be rejected"
    )
    assert CONFIRMED_KEY not in verify_module.REPORT_KEYS, (
        "an OPTIONAL key must not also be REQUIRED — every report written before C-4a, and "
        "every unconfirmed pass after it, carries no such key"
    )


def test_pin3_validate_report_accepts_a_session_id(shipped_report: dict) -> None:
    verify_module.validate_report(_with_key(shipped_report, "sess-01JABCDEF"))
    verify_module.validate_report(_with_key(shipped_report, SESSION_IDS[0]))


def test_pin3_empty_string_is_rejected(shipped_report: dict) -> None:
    """C-4a §1: "a non-empty string". An empty id names no session, and the key
    exists precisely so the run log can name the other one."""
    with pytest.raises(ValueError):
        verify_module.validate_report(_with_key(shipped_report, ""))


def test_pin3_whitespace_only_is_rejected(shipped_report: dict) -> None:
    """The module's own "non-empty string" gate (`_as_text`) refuses a blank
    run of spaces too. Its own line: the contract says "non-empty", and whether
    that means `len` or `strip` is the house gate's reading, not the
    contract's."""
    with pytest.raises(ValueError):
        verify_module.validate_report(_with_key(shipped_report, "   "))


@pytest.mark.parametrize("value", [1, 1.5, True, [], {}, ["sess"], {"id": "sess"}])
def test_pin3_non_strings_are_rejected(shipped_report: dict, value: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        verify_module.validate_report(_with_key(shipped_report, value))


def test_pin3_null_confirmed_session_is_rejected(shipped_report: dict) -> None:
    """Ambiguity f, on its own line: §1 says "a non-empty string", which
    excludes None — but the window keys it is "validated like" DO allow null.
    Strict reading pinned; one line to move if the lead adjudicates the other
    way."""
    with pytest.raises((ValueError, TypeError)):
        verify_module.validate_report(_with_key(shipped_report, None))


def test_pin3_the_window_keys_still_validate_beside_it(shipped_report: dict) -> None:
    """The optional-key loop in `validate_report` treated every optional key as
    a corroboration WINDOW; `confirmed_session` is not one. Both window
    readings — an int and the unwindowed null — must survive the split."""
    for window in (1, 3, None):
        report = copy.deepcopy(shipped_report)
        report["lever_window"] = window
        report["term_window"] = window
        report[CONFIRMED_KEY] = SESSION_IDS[0]
        verify_module.validate_report(report)

    bad = copy.deepcopy(shipped_report)
    bad["lever_window"] = 0
    bad[CONFIRMED_KEY] = SESSION_IDS[0]
    with pytest.raises(ValueError):
        verify_module.validate_report(bad)


def test_pin3_a_session_id_is_not_read_as_a_window(shipped_report: dict) -> None:
    """The complement: the window keys keep refusing a string, so the split did
    not loosen them into "any optional value"."""
    bad = copy.deepcopy(shipped_report)
    bad["lever_window"] = SESSION_IDS[0]
    with pytest.raises(ValueError):
        verify_module.validate_report(bad)


@pytest.mark.parametrize("relative", SHIPPED_REPORTS)
def test_pin3_shipped_reports_still_validate_unchanged(relative: str) -> None:
    """The three shipped b002 reports and both b003r2 reports still validate —
    and none of them carries the new key, because none was confirmed.

    The b003r2 pair is this contract's own evidence: both PASSED round 1 while
    carrying uncorroborated recordings, and no second session ever looked.
    """
    path = REPO_ROOT / relative
    assert path.is_file(), f"fixture wall: {path} is gone"
    report = json.loads(path.read_text(encoding="utf-8"))
    verify_module.validate_report(copy.deepcopy(report))
    assert CONFIRMED_KEY not in report, (
        f"{relative} already carries {CONFIRMED_KEY!r}; these are the PRE-C-4a artifacts"
    )


def test_pin3_write_report_round_trips_the_key(tmp_path, shipped_report: dict) -> None:
    """`write_report` validates then writes, so the key has to survive both."""
    path = tmp_path / "confirmed.verifier-report.json"
    verify_module.write_report(_with_key(shipped_report, SESSION_IDS[0]), path)
    assert json.loads(path.read_text(encoding="utf-8"))[CONFIRMED_KEY] == SESSION_IDS[0]

    with pytest.raises(ValueError):
        verify_module.write_report(_with_key(shipped_report, ""), tmp_path / "never.json")
    assert not (tmp_path / "never.json").exists(), (
        "an invalid report was persisted — `write_report` validates BEFORE it writes"
    )


def test_pin3_a_confirmed_reject_records_nothing_it_cannot_justify(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """Ambiguity e, RECORDED GAP: §3 sets the key "before `write_report`"
    without distinguishing verdicts, while test-pin 3 lists only knob-off and
    unconfirmed passes as the absences. Only the weak form is pinned — if the
    confirmed REJECT carries the key, it is round 1's session id."""
    drive = _Drive(tmp_path, monkeypatch, cap, TERM_FINDING, TERM_FINDING)
    result = drive.run(_on(base_cfg))
    report = drive.written_report()

    assert result["ok"] is False
    if CONFIRMED_KEY in report:
        assert report[CONFIRMED_KEY] == SESSION_IDS[0], (
            f"the confirmed reject records {report[CONFIRMED_KEY]!r} as the other session; "
            f"round 1's id is {SESSION_IDS[0]!r}"
        )


# ==========================================================================
# PIN 4 — the stage's cost bills BOTH sessions
# ==========================================================================


def test_pin4_a_confirmed_pass_bills_both_agents(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """C-4a §4: the stage's `_cost` sums BOTH agent blocks' usd/tokens.

    Today it reads one. A confirmation round that billed only round 2 would
    under-report every confirmed slot on the ledger — and this pipeline's
    spend is reported at every close.
    """
    drive = _Drive(tmp_path, monkeypatch, cap, TERM_FINDING, CLEAN)
    result = drive.run(_on(base_cfg))

    assert drive.agent.count == 2
    assert result["cost"] == {
        "usd": ROUND_USD[0] + ROUND_USD[1],
        "tokens_in": ROUND_TOKENS_IN[0] + ROUND_TOKENS_IN[1],
        "tokens_out": ROUND_TOKENS_OUT[0] + ROUND_TOKENS_OUT[1],
    }, (
        f"the confirmed pass reported {result['cost']!r}; C-4a §4 sums both blind sessions "
        f"(round 1 {ROUND_USD[0]} + round 2 {ROUND_USD[1]} USD)"
    )


def test_pin4_a_confirmed_reject_bills_both_agents(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """The reject path spent the same two sessions, so it owes the same bill."""
    drive = _Drive(tmp_path, monkeypatch, cap, LEVER_FINDING, LEVER_FINDING)
    result = drive.run(_on(base_cfg))

    assert result["ok"] is False
    assert result["cost"]["usd"] == ROUND_USD[0] + ROUND_USD[1]
    assert result["cost"]["tokens_in"] == ROUND_TOKENS_IN[0] + ROUND_TOKENS_IN[1]
    assert result["cost"]["tokens_out"] == ROUND_TOKENS_OUT[0] + ROUND_TOKENS_OUT[1]


def test_pin4_an_unconfirmed_pass_bills_one_agent(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """The other half of §4: a single-session round still reports exactly what
    it spent, knob on or off."""
    drive = _Drive(tmp_path, monkeypatch, cap, CLEAN)
    result = drive.run(_on(base_cfg))

    assert drive.agent.count == 1
    assert result["cost"] == {
        "usd": ROUND_USD[0],
        "tokens_in": ROUND_TOKENS_IN[0],
        "tokens_out": ROUND_TOKENS_OUT[0],
    }


# ==========================================================================
# PIN 5 — the sidecars record BOTH rounds
# ==========================================================================


def test_pin5_a_confirmed_pass_leaves_two_entries_in_each_sidecar(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """C-4a §2/§5: round 1's sidecar entries are ALREADY appended when round 2
    reads the history — that append-after-read order is what makes round 2's
    re-sighting corroborate. Two rounds, two entries, in both records.
    """
    drive = _Drive(tmp_path, monkeypatch, cap, TERM_FINDING, CLEAN)
    drive.run(_on(base_cfg))

    levers, terms = drive.lever_entries(), drive.term_entries()
    assert len(levers) == 2, (
        f"the lever history holds {len(levers)} entr(ies) after a confirmed pass; "
        "append-per-assemble_report means one per audit round"
    )
    assert len(terms) == 2, (
        f"the term history holds {len(terms)} entr(ies) after a confirmed pass"
    )
    assert terms[0]["undeclared"] == [EXTRA_TERM], (
        "round 1's record must hold what round 1 FOUND — the record is of detection, never "
        "of verdicts, which is what lets round 2 corroborate it"
    )
    assert terms[1]["undeclared"] == [], "round 2 was silent"


def test_pin5_a_confirmed_reject_also_records_both_rounds(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """The reject path ran the same two `assemble_report` calls."""
    drive = _Drive(tmp_path, monkeypatch, cap, LEVER_FINDING, LEVER_FINDING)
    drive.run(_on(base_cfg))

    levers = drive.lever_entries()
    assert len(levers) == 2
    assert [entry["detected"] for entry in levers] == [[LEVER_A], [LEVER_A]], (
        "both rounds detected the lever, and BOTH are recorded — the second sighting is what "
        "made it a reject"
    )
    assert len(drive.term_entries()) == 2


def test_pin5_an_unconfirmed_round_records_exactly_one_entry(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """The control: one audit round, one entry per sidecar — a confirmation
    that did not happen must not leave a phantom round behind for the NEXT
    lap to corroborate against."""
    drive = _Drive(tmp_path, monkeypatch, cap, CLEAN)
    drive.run(_on(base_cfg))

    assert len(drive.lever_entries()) == 1
    assert len(drive.term_entries()) == 1


def test_pin5_knob_off_records_exactly_one_entry(
    tmp_path, monkeypatch, cap, base_cfg
) -> None:
    """…and with the knob absent, a round that DID carry recordings still
    leaves exactly one entry: byte-identical behavior includes the sidecars."""
    drive = _Drive(tmp_path, monkeypatch, cap, TERM_FINDING)
    drive.run(_off(base_cfg))

    assert len(drive.lever_entries()) == 1
    assert len(drive.term_entries()) == 1
