"""ITERATION DYNAMICS: the standing regression layer for repeated-cycle state.

Run: .venv/bin/python -m pytest gen/tests/test_iteration_dynamics.py -v

WHY THIS FILE EXISTS. B11's fake-runner rig pins every §4 edge and every
kill/resume boundary, and it shipped green — then the R2 pilot ran the machine
for real and nine defects surfaced live, one per amendment in
`out/pilot/R1-freeze.md`. Every one of them lives in a state the b11 rig never
reaches, because its fakes are POLITE: they leave no killed spec dir behind
(a `respec` landing writes no artifacts at all), they name every corpus dir
after the SLOT id (so a re-sample can never make two dirs claim one idea),
they rewrite spec.yaml with a placeholder on the reject edges, and they
re-create `worker/` on edges the real S1 never touches (all four documented in
`test_r2_hotfix9`'s docstring). Each defect now has a targeted regression
test; what had no home is the CLASS — end-to-end scenarios that drive the
machine round its loops with fakes messy enough to reach the states real
iteration produces.

ONE SCENARIO PER AMENDMENT (the map; each test's docstring names its own):

  1. `test_a_lint_kill_archives_its_spec_dir_and_the_next_attempt_writes_a_second`
     + `test_a_killed_spec_dir_stranded_at_startup_is_swept`
     — R2 amendment 3, killed-dir archiving + the startup sweep.
  2. `test_the_second_lint_kill_blocks_at_the_default_cap_and_resamples_at_three`
     — R2 amendment 1, the `orchestrator.respec_cap` knob.
  3. `test_a_run_killed_at_respec_resumes_through_it_without_an_offledger_s1`
     — SECOND amendment, the resume-from-`respec` fix.
  4. `test_the_s2_effort_cap_is_config_plumbing_and_is_pinned_elsewhere`
     — FOURTH amendment. SKIPPED, with the reason stated in the test.
  5. `test_the_escalated_respec_is_handed_the_verifier_report_or_blocks_before_spend`
     — FIFTH amendment, the escalation's findings-feed.
  6. `test_an_escalated_respec_that_retitles_blocks_at_the_stage_that_caused_it`
     — FIFTH amendment's other half / the slug pin + same-dir assertion.
  7. `test_two_isolated_captures_of_an_edited_worker_both_succeed`
     — SEVENTH amendment, one interpreter per capture. SMOKED (see below).
  8. `test_a_declaration_only_respec_leaves_its_marker_across_the_cycle`
     + `test_a_substantive_respec_leaves_no_marker_and_sweeps_a_stale_one`
     — EIGHTH amendment, the marker's lifecycle at the LOOP level.
  9. `test_the_parked_state_resumes_to_played_without_re_verifying`
     — STATE AS PARKED, accept-latching at the loop level.

  plus `test_a_resume_from_every_truncated_ledger_prefix_completes` — the
  generalization of the night's mid-cycle resume crash: replay+resume from
  EVERY prefix of a full happy history.

4 AND 7, ADJUDICATED. 4 is SKIPPED: the S2 `effort` knob is config plumbing
(`get_session_policy` reads it, `session()` omits the flag for None) and the
rig never opens a session, so there is no iteration state to drive; it is
pinned by `test_r2_hotfix5.py` and the skip says so. 7 is SMOKED, not skipped:
`gen.frames.capture_worker_isolated` IS drivable on a tiny planted worker
(h8's fixtures, imported) and two captures with a rename between them run in
~1.4s, well inside the ~20s budget — so the loop-shaped half of defect #8
(repeated rounds in ONE process) is exercised here for real rather than
declared unreachable.

THE HARNESS IS IMPORTED, NEVER COPIED (the test_r2_hotfix2/6/9 precedent).
`test_b11_pipeline` owns the fake-runner rig and the two guards; `h6` owns the
escalation script and its verifier report; `h9` owns the decl-only marker rig;
`h8` owns the §7 mini-worker. Fixtures are RE-BOUND at module level because
pytest resolves a fixture by looking it up in the REQUESTING module. Nothing
in any of those files is modified: where the rig is too polite for a scenario
it is SUBCLASSED here (`_SpecDirRunners`, `_EvidenceRunners`, `_ParkAtCrash`)
or the tree is post-processed between steps.

Three standing rules this file keeps (the hotfix precedent):

  * NO API call, ever. Every orchestrator path runs on fake stage runners;
    b11's `_no_network_no_agent` guard is re-bound so a stray `get_driver`
    fails loudly. Scenario 9 drives the REAL S2b runner with its two expensive
    legs (`capture_worker_isolated`, `run_agent_pass`) monkeypatched to raise:
    reaching one is a failure, not a spend.
  * NO writes outside `tmp_path`. `batch_home` re-roots every repo path in the
    orchestrator; b11's `_repo_batches_untouched` guard is re-bound.
  * NOTHING IS READ OUT OF `out/` AT RUNTIME. `out/pilot/R1-freeze.md` is this
    file's SCENARIO SOURCE and was read to write it, but the suite must not
    depend on a tree the pilot run owns and rewrites — so every amendment is
    cited by name in a docstring instead, and every document below is either
    a committed fixture (through h6/h9) or written here into `tmp_path`.
    RENEGOTIABLE: if the freeze record is ever wanted as a live fixture, it
    belongs under `gen/tests/fixtures/`, not read from `out/`.

Contract readings this file encodes where the pilot's amendments left a choice
open — each one is a line to renegotiate, not a fact:

  * STAGE NAMES are read off the orchestrator's own `NEXT_STAGE` table
    (`S1_STAGE = NEXT_STAGE["ideated"]`), never typed as literals, and
    `test_the_stage_names_this_file_drives_are_the_orchestrators_own` fails
    once and by name if that table is re-keyed.
  * A DRAFT'S DIR NAME. The real S1 names the corpus dir after the SPEC's slug
    and a fresh draw retitles the game, which is what makes two dirs claim one
    idea; `_SpecDirRunners` reproduces that with `<base>-draft<n>`. The BASE
    slug is h6's committed `REQUIRED_SLUG`. The `-draft<n>` spelling is this
    file's, and nothing asserts it beyond "the second attempt's dir is not the
    first attempt's".
  * A KILLED DRAFT'S EVIDENCE is the four artifacts the real S1 declares on
    every verdict (spec.yaml, spec.md, lint-report.json, idea.json — the set
    `archive_killed_spec`'s own docstring names). `lint-report.json` carries
    `passed: false` on a kill because that is the field `_killed_by_lint`
    reads; a kill written any other way is invisible to the sweep, which is
    the defect, not the test.
  * "THE KILLED DIR IS IN `.killed/`" is asserted as: exactly one child of
    `.killed/` whose name starts with the killed draft's dir name, carrying
    that draft's spec.yaml BYTES. The timestamp suffix is not pinned.
  * THE PENDING ROW (scenario 3) is read off the report of a SINGLE
    `run_batch` leg, because `_restage` rebuilds `slot.stale` once per leg and
    `_advance`'s last leg overwrites it (the h3 finding, adopted).
  * THE LATCH'S REASON (scenario 9) is matched for the substring "latch". The
    wording is the implementation's; what is contracted is the short-circuit,
    and the two `_boom` legs are what actually pin it. RENEGOTIABLE.
  * SCENARIO 9 IS A HARD PIN, NOT AN XFAIL. The brief allowed xfail with
    "accept-latching (Phase A)" if the contract had not landed; it HAS
    (`orchestrator._latched_verify`, wired into the real S2b runner), so the
    test asserts it. If it is ever reverted, this test fails loudly — which is
    the point of the reason string.
  * THE RESUME MATRIX truncates the ledger with the full artifact tree left on
    disk. That is the honest shape of a crash between a stage's write and its
    append; prefixes deeper than one stage are more artificial, and what they
    pin is the weaker, real claim: no prefix may CRASH the resume.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from gen import frames as frames_module
from gen import orchestrator as orch
from gen import s3_verify as s3_verify_module

# The rigs, imported and re-bound (see the module docstring). Every borrowed
# piece is called through its owner's alias so the ownership stays visible.
from gen.tests import test_b11_pipeline as b11
from gen.tests import test_r2_hotfix6 as h6
from gen.tests import test_r2_hotfix8 as h8
from gen.tests import test_r2_hotfix9 as h9

_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched
batch_home = b11.batch_home
make_cfg = b11.make_cfg

# --- the stage names, READ off the orchestrator's own table ------------------

S0_STAGE = orch.NEXT_STAGE["respec"]        # the re-sample
S1_STAGE = orch.NEXT_STAGE["ideated"]       # the writer
S2_STAGE = orch.NEXT_STAGE["spec_ok"]       # the green loop
S2B_STAGE = orch.NEXT_STAGE["implemented"]  # the verifier
S5_STAGE = orch.NEXT_STAGE["baselined"]     # the battery

#: the game the pilot actually ran (h6's committed fixture slug).
BASE_SLUG = h6.REQUIRED_SLUG

#: the four artifacts the real S1 declares on EVERY verdict — the set
#: `archive_killed_spec` names as "what a kill leaves on disk".
SPEC_ARTIFACTS = ("spec.yaml", "spec.md", "lint-report.json", "idea.json")

LINT_KILL_REASON = "lint kill: neg2 schema notation is ambiguous"
KILL_EDGE = ("ideated", "respec")
RESAMPLE_EDGE = ("respec", "ideated")
REJECT_EDGE = ("implemented", "spec_ok")
IMPLEMENT_EDGE = ("spec_ok", "implemented")

#: §4's happy path end to end, including the human accept — the spine the
#: resume matrix truncates. Transcribed from b11's own spine assertion plus
#: the two review edges.
HAPPY_SPINE = (
    (b11._birth_state(), "ideated"),
    ("ideated", "spec_ok"),
    ("spec_ok", "implemented"),
    ("implemented", "verified"),
    ("verified", "gated"),
    ("gated", "baselined"),
    ("baselined", "played"),
    ("played", "reviewed"),
    ("reviewed", "packaged"),
)

#: what the real S2b writes beside `worker/`, spelled from `s3_verify`'s own
#: frozen suffixes — scenario 9's latch requires BOTH to be on disk.
VERIFIER_REPORT_NAME = orch.WORKER_DIRNAME + s3_verify_module.REPORT_SUFFIX
VERIFIER_FRAMES_NAME = orch.WORKER_DIRNAME + s3_verify_module.FRAMES_SUFFIX


# --------------------------------------------------------------------------
# helpers — readers
# --------------------------------------------------------------------------


def _only_slot(report) -> dict:
    slots = report["slots"]
    assert len(slots) == 1, f"these scenarios run one-slot batches; the report has {len(slots)}"
    return slots[0]


def _edge_lines(cfg, edge) -> list[dict]:
    return [line for line in b11._ledger_lines(cfg) if (line["from"], line["to"]) == edge]


def _corpus_dir(cfg) -> Path:
    """`out/corpus/<batch>/` under the rig's tmp root — the §2 corpus home."""
    return Path(orch.CORPUS_ROOT) / orch.batch_config(cfg)["id"]


def _live_dirs(cfg) -> list[Path]:
    """Every corpus dir DISCOVERY can see: a top-level dir with an idea.json."""
    corpus = _corpus_dir(cfg)
    if not corpus.is_dir():
        return []
    return sorted(
        path for path in corpus.iterdir()
        if path.is_dir() and path.name != orch.KILLED_DIRNAME and (path / "idea.json").is_file()
    )


def _killed_dirs(cfg) -> list[Path]:
    graveyard = _corpus_dir(cfg) / orch.KILLED_DIRNAME
    return sorted(path for path in graveyard.iterdir() if path.is_dir()) if graveyard.is_dir() \
        else []


def _archived_copy_of(cfg, draft: Path) -> Path:
    """The one `.killed/` entry that is `draft`'s archive (stamp not pinned)."""
    found = [path for path in _killed_dirs(cfg) if path.name.startswith(draft.name)]
    assert len(found) == 1, (
        f"expected exactly one archived copy of {draft.name} under "
        f"{_corpus_dir(cfg) / orch.KILLED_DIRNAME}, found {[p.name for p in _killed_dirs(cfg)]}"
    )
    return found[0]


def _stage_calls(journal, stage: str) -> list:
    return [call for call in journal.calls if call.stage == stage]


def _blocked_row(report) -> dict:
    row = _only_slot(report)
    assert row["blocked"], (
        f"the slot is not blocked — state {row['state']!r}, stop_reason "
        f"{report['stop_reason']!r}"
    )
    assert report["blocked"] == [row["slug"]], (
        f"a blocked slot must be listed in the report's top-level `blocked`: {report['blocked']}"
    )
    return row["blocked"]


class _Reached(Exception):
    """Raised by a leg the machine must not reach in this scenario."""


def _boom(name: str):
    def forbidden(*args, **kwargs):
        raise _Reached(f"the run reached {name}() — this scenario must short-circuit before it")

    return forbidden


# --------------------------------------------------------------------------
# the local rig #1 — an S1 that writes a REAL spec dir, named after the draft
# --------------------------------------------------------------------------


class _SpecDirRunners(h6._WatchingRunners):
    """b11's rig with the ONE politeness that hides amendments 3 and 5 removed.

    What the rig does: every stage's artifacts land in `<corpus>/<SLOT id>/`,
    a name that never changes, so a re-sample overwrites the killed draft in
    place and two dirs can never claim one idea. What the REAL S1 does: names
    the dir after the SPEC's slug, copies `idea.json` into it, and writes
    `lint-report.json` beside the spec on every verdict — so a fresh draw,
    which retitles the game, writes a SECOND dir carrying the same idea id.
    That second dir is what ended pilot run 1.

    So this subclass:
      * gives each S1 attempt its own `<base>-draft<n>` dir under the corpus
        root, and points every LATER stage at whatever dir the idea currently
        resolves to (`ctx.spec_dir`) — never at a dir that was archived, which
        `mkdir(exist_ok=True)` would silently resurrect;
      * writes the four artifacts the real S1 declares, with
        `lint-report.json: {"passed": false}` on a kill, and declares exactly
        those four — which is what `_killed_spec_dir` derives the dir to
        archive from;
      * with `respec_drift=`, makes an ESCALATED re-spec write a NEW dir
        instead of editing in place — the blind-re-spec defect of the fifth
        amendment, reproduced in both of its shapes: `"move"` retitles and
        takes the old dir with it (one dir, the wrong one), `"second-dir"` is
        the pilot's literal shape (the old dir stays live beside it).
    """

    def __init__(self, journal, cfg, *, outcomes=None, report=None,
                 respec_drift: str | None = None) -> None:
        assert respec_drift in (None, "move", "second-dir"), respec_drift
        self._respec_drift = respec_drift
        self._attempts: dict[str, int] = {}
        self._creating: Path | None = None
        #: every draft dir this rig created, in creation order.
        self.drafts: list[Path] = []
        super().__init__(journal, cfg, outcomes=outcomes, report=report)

    # -- where artifacts land ---------------------------------------------
    def _slot_dirs(self, ctx, slug: str) -> list[Path]:
        """The batch dir, plus the §2 spec dir this call may legitimately use.

        NEVER a dir chosen by convention: the S0 call that re-samples after a
        kill has no spec dir at all (the killed one is archived, the next one
        is not written yet), and re-creating the archived path there would
        plant a second idea.json and re-arm the very LedgerError the archive
        exists to prevent.
        """
        dirs = [Path(orch.batch_dir(self._cfg)) / slug]
        live = self._creating
        if live is None:
            spec_dir = getattr(ctx, "spec_dir", None)
            live = None if spec_dir is None else Path(spec_dir)
        if live is not None and live not in dirs:
            dirs.append(live)
        for path in dirs:
            path.mkdir(parents=True, exist_ok=True)
        return dirs

    # -- the fake itself ---------------------------------------------------
    def _make(self, stage: str):
        inner = super()._make(stage)
        if stage != S1_STAGE:
            return inner

        def runner(ctx):
            escalated = h6._escalation_of(ctx) not in (None, h6._MISSING)
            drifting = escalated and self._respec_drift is not None
            in_place = escalated and not drifting and ctx.spec_dir is not None
            self._creating = Path(ctx.spec_dir) if in_place else self._new_draft(ctx)
            try:
                result = inner(ctx)
                written = self._write_spec_dir(ctx, self._creating, result)
            finally:
                self._creating = None
            if drifting and self._respec_drift == "move" and ctx.spec_dir is not None:
                # The retitle took the draft WITH it: one dir claims the idea
                # and it is not the dir `_maybe_respec` started from.
                shutil.rmtree(ctx.spec_dir)
            return written

        return runner

    def _new_draft(self, ctx) -> Path:
        key = b11._ctx_slug(ctx) or ""
        attempt = self._attempts.get(key, 0) + 1
        self._attempts[key] = attempt
        draft = Path(ctx.corpus_dir) / f"{BASE_SLUG}-draft{attempt}"
        self.drafts.append(draft)
        return draft

    def _write_spec_dir(self, ctx, live: Path, result: dict) -> dict:
        """Land S1's four artifacts in `live` and DECLARE exactly those four."""
        killed = not result["ok"]
        live.mkdir(parents=True, exist_ok=True)
        # The idea copy is the link `_discover_spec_dir` follows: content, not
        # convention. Copied, not re-authored, so the ids cannot drift.
        shutil.copyfile(ctx.idea_path, live / "idea.json")
        (live / "spec.yaml").write_text(
            f"game:\n  slug: {live.name}\n  revision: {len(self._journal.calls)}\n",
            encoding="utf-8",
        )
        (live / "spec.md").write_text(f"# {live.name}\n\nfake S1 prose.\n", encoding="utf-8")
        (live / "lint-report.json").write_text(
            json.dumps({"passed": not killed, "verdict": result["reason"]}, indent=2) + "\n",
            encoding="utf-8",
        )
        artifacts = {name: str(live / name) for name in SPEC_ARTIFACTS}
        return {**result, "artifacts": artifacts}


def _drive_drafts(make_cfg, batch_id: str, *, kills: int = 0, cap: int | None = None,
                  respec_drift: str | None = None, report: dict | None = None,
                  rejects: int = 0, kill_after_lint: bool = False, advance: bool = True):
    """One size-1 batch on the draft-writing rig, scripted for one scenario."""
    cfg, _path = make_cfg(batch_id)
    cfg["orchestrator"].pop("respec_cap", None)
    if cap is not None:
        # The R2 ruling made the cap per-batch config. `make_cfg` predates it,
        # so the key is set on the dict `run_batch` actually reads (the yaml
        # copy beside it is never loaded by these tests).
        cfg["orchestrator"]["respec_cap"] = cap
    outcomes = {}
    if kills:
        outcomes["ideated"] = b11._Outcome("respec", LINT_KILL_REASON, times=kills)
    if rejects:
        outcomes["implemented"] = b11._Outcome(
            "spec_ok", "verifier reject: undeclared deception", times=rejects
        )
    journal = b11._Journal()
    runners = _SpecDirRunners(
        journal, cfg, outcomes=outcomes or None, report=report, respec_drift=respec_drift
    )
    if kill_after_lint:
        # A ^C at the worst moment: the kill's line is on the ledger and its
        # dir is archived, and the re-sample never starts.
        journal.kill_after = 2   # call 1 = S0, call 2 = the killed S1
        with pytest.raises(KeyboardInterrupt):
            orch.run_batch(cfg, runners=runners)
        return cfg, journal, runners, None
    if not advance:
        return cfg, journal, runners, None
    return cfg, journal, runners, b11._advance(cfg, runners)


def _spy_on_blocks(monkeypatch) -> list[dict]:
    """Record every `_block_slot` call and let it through.

    The batch report is the normal way to read a block, but one scenario
    below cannot reach it: report assembly re-resolves the slot's context and
    a double-claimed idea raises there, so the run never returns a report.
    The block still HAPPENED, at the stage that caused it, and that is what
    this spy witnesses.
    """
    seen: list[dict] = []
    real = orch._block_slot

    def spy(slot, *, stage, reason, note):
        seen.append({"slug": slot.slug, "state": slot.state, "stage": stage,
                     "reason": reason, "note": note})
        return real(slot, stage=stage, reason=reason, note=note)

    monkeypatch.setattr(orch, "_block_slot", spy)
    return seen


# --------------------------------------------------------------------------
# the local rig #2 — the S2b evidence siblings, and a ^C at the crash edge
# --------------------------------------------------------------------------


class _EvidenceRunners(b11._Runners):
    """b11's rig + the two files S2b leaves beside `worker/`.

    The rig writes `verifier-report.json` INSIDE the slot dir on the happy
    `verified` edge; the real S2b runner writes `worker.verifier-report.json`
    and `worker.frames.json` as SIBLINGS of the worker dir, and the accept
    latch re-serves a recorded verdict only while BOTH are still on disk
    ("the verdict's evidence is gone: re-verify for real"). Planting them is
    what lets scenario 9 hand the real runner a parked slot that is honestly
    parked — artifacts and all.
    """

    def _make(self, stage: str):
        inner = super()._make(stage)

        def runner(ctx):
            result = inner(ctx)
            self._plant_evidence(ctx)
            return result

        return runner

    def _plant_evidence(self, ctx) -> None:
        spec_dir = getattr(ctx, "spec_dir", None)
        if spec_dir is None or not (Path(spec_dir) / orch.WORKER_DIRNAME).is_dir():
            return
        spec_dir = Path(spec_dir)
        (spec_dir / VERIFIER_REPORT_NAME).write_text(
            json.dumps({"verdict": "pass", "reject_reasons": []}, indent=2) + "\n",
            encoding="utf-8",
        )
        (spec_dir / VERIFIER_FRAMES_NAME).write_text(
            json.dumps({"records": [], "note": "fake S2b frames"}, indent=2) + "\n",
            encoding="utf-8",
        )


class _ParkAtCrash(_EvidenceRunners):
    """…and stops the run the moment the battery's crash pair lands.

    Two things the rig will not do on its own:

    1. A CRASHED BATTERY DOES NOT REWRITE THE GAME. The rig writes the
       artifact set of the state a call LANDS, and a scripted battery crash
       lands `implemented` — so its fake re-writes `worker/game.py` with a
       fresh revision and the game hash moves. That is the politeness that
       hides this whole scenario: the parked state's premise is that the
       bytes S2b accepted are still the bytes on disk. The worker files are
       snapshotted before the crash call and restored after it.
    2. The ^C is fired from inside the rig rather than counted by the test, so
       the park point stays correct if §4's spine ever grows a stage.
    """

    WORKER_FILES = ("game.py", "solver.py")

    def _make(self, stage: str):
        inner = super()._make(stage)
        if stage != S5_STAGE:
            return inner

        def runner(ctx):
            before = self._worker_bytes(ctx)
            result = inner(ctx)
            for path, raw in before.items():
                path.write_bytes(raw)
            if not result["ok"]:
                self._journal.kill_after = len(self._journal.calls)
            return result

        return runner

    def _worker_bytes(self, ctx) -> dict[Path, bytes]:
        found: dict[Path, bytes] = {}
        for slot_dir in self._slot_dirs(ctx, b11._ctx_slug(ctx) or ""):
            for name in self.WORKER_FILES:
                path = slot_dir / orch.WORKER_DIRNAME / name
                if path.is_file():
                    found[path] = path.read_bytes()
        return found


# --------------------------------------------------------------------------
# 0 — the names this file drives (one named failure, not ten confusing ones)
# --------------------------------------------------------------------------


def test_the_stage_names_this_file_drives_are_the_orchestrators_own():
    """Read, never guessed: every stage key comes off `NEXT_STAGE`."""
    named = {"S0": S0_STAGE, "S1": S1_STAGE, "S2": S2_STAGE, "S2b": S2B_STAGE, "S5": S5_STAGE}
    unknown = {label: stage for label, stage in named.items() if stage not in orch.STAGES}
    assert not unknown, (
        f"`NEXT_STAGE` names stage(s) {unknown} that are not in STAGES {list(orch.STAGES)} — "
        "the rig injects fakes by stage key, so this has to agree"
    )
    assert len(set(named.values())) == len(named), f"two states share one stage: {named}"


def test_the_happy_spine_is_still_the_one_the_resume_matrix_truncates():
    """Every edge the matrix replays is an edge architecture §4 draws.

    The birth edge is checked apart from the rest: `b11._edge_set` stringifies
    both ends, so the birth sentinel comes back as its `str()` and would not
    compare equal to the value `_birth_state()` reads off TRANSITIONS.
    """
    assert HAPPY_SPINE[0] == (b11._birth_state(), "ideated"), HAPPY_SPINE[0]
    missing = [edge for edge in HAPPY_SPINE[1:] if edge not in set(b11.SECTION4_EDGES)]
    assert not missing, f"HAPPY_SPINE names edge(s) §4 no longer draws: {missing}"


# --------------------------------------------------------------------------
# 1 — R2 AMENDMENT 3: the killed-spec archive, and the startup sweep
# --------------------------------------------------------------------------


def test_a_lint_kill_archives_its_spec_dir_and_the_next_attempt_writes_a_second(make_cfg):
    """R2 AMENDMENT 3 — "Killed-dir archiving (crash fix, run 1)".

    Pilot run 1 died here: S1's kill left `spec.yaml`/`spec.md`/
    `lint-report.json`/`idea.json` in the corpus, the re-sample's draft wrote
    a SECOND dir carrying the same idea id, and `_discover_spec_dir` raised
    `LedgerError` ("a slot has exactly one spec dir") three stages later. The
    b11 rig cannot see this: its fakes write every draft into one dir named
    after the SLOT, so the second attempt overwrites the first.

    Here the kill and the re-draft write DIFFERENT dirs, as the real writer
    does. The pin is the whole loop: no LedgerError, the killed draft is in
    `.killed/` with its bytes intact, exactly one dir is left for discovery to
    find, and the slot runs on to `packaged`.
    """
    cfg, journal, runners, report = _drive_drafts(make_cfg, "idyn-kill-archive", kills=1)

    assert len(runners.drafts) == 2, (
        f"one kill + one re-draft must write two DIFFERENT dirs: "
        f"{[d.name for d in runners.drafts]}"
    )
    killed_draft, live_draft = runners.drafts
    assert killed_draft != live_draft, "a re-sample retitles the game — that is the whole defect"

    assert len(_edge_lines(cfg, KILL_EDGE)) == 1, b11._spine(b11._ledger_lines(cfg))
    assert len(_edge_lines(cfg, RESAMPLE_EDGE)) == 1, b11._spine(b11._ledger_lines(cfg))

    # The archive: the kill is EVIDENCE, moved aside, not deleted.
    archived = _archived_copy_of(cfg, killed_draft)
    assert not killed_draft.exists(), (
        f"{killed_draft} is still in the corpus after its kill — the next draft's idea.json "
        "now has a rival and discovery is double-valued again"
    )
    for name in SPEC_ARTIFACTS:
        assert (archived / name).is_file(), (
            f"the archived kill must keep S1's {name} (evidence, not rubbish): "
            f"{sorted(p.name for p in archived.iterdir())}"
        )
    assert json.loads((archived / "lint-report.json").read_text(encoding="utf-8"))["passed"] \
        is False, "the archived dir must be the KILL, not a passing draft"

    # …and discovery is single-valued: one live dir, and it is the re-draft.
    assert _live_dirs(cfg) == [live_draft], (
        f"exactly one corpus dir may claim the slot's idea: {[p.name for p in _live_dirs(cfg)]}"
    )
    assert orch._discover_spec_dir(_corpus_dir(cfg), journal.contexts[-1].idea_path) == live_draft

    assert report["stop_reason"] is None, report["stop_reason"]
    assert b11._table(cfg) == {_only_slot(report)["slug"]: "packaged"}, b11._table(cfg)


def test_a_killed_spec_dir_stranded_at_startup_is_swept(make_cfg, capsys):
    """R2 AMENDMENT 3, second half — "a startup sweep self-heals strands".

    A crash BETWEEN the kill's ledger line and its archiving leaves the dir
    behind, and so does any run from before archiving existed. The strand is
    planted here by copying the archived kill back into the corpus — the exact
    shape the crash leaves — and the control proves the trap is armed:
    `_discover_spec_dir` raises `LedgerError` while it stands. The next plain
    run must sweep it before any stage runs.
    """
    cfg, journal, runners, _report = _drive_drafts(make_cfg, "idyn-sweep-strand", kills=1)
    killed_draft, live_draft = runners.drafts
    idea_path = journal.contexts[-1].idea_path

    strand = _corpus_dir(cfg) / killed_draft.name
    shutil.copytree(_archived_copy_of(cfg, killed_draft), strand)
    assert (strand / "idea.json").is_file(), "the strand must be visible to discovery"

    # CONTROL: with the strand in place the idea is double-claimed.
    with pytest.raises(orch.LedgerError) as caught:
        orch._discover_spec_dir(_corpus_dir(cfg), idea_path)
    assert strand.name in str(caught.value) and live_draft.name in str(caught.value), caught.value

    capsys.readouterr()
    report = orch.run_batch(cfg, runners=_SpecDirRunners(b11._Journal(), cfg))
    swept = capsys.readouterr().out

    assert not strand.exists(), (
        f"the startup sweep left {strand} in the corpus — the next S1 attempt would make two "
        "dirs claim one idea again"
    )
    assert "swept" in swept.lower(), f"a sweep that moved a dir must say so on stdout: {swept!r}"
    assert len(_killed_dirs(cfg)) == 2, (
        f"the strand is archived BESIDE the original kill, not over it: "
        f"{[p.name for p in _killed_dirs(cfg)]}"
    )
    assert _live_dirs(cfg) == [live_draft], [p.name for p in _live_dirs(cfg)]
    assert report["slots"][0]["state"] == "packaged", report["slots"][0]["state"]
    assert report["slots"][0]["blocked"] is None, report["slots"][0]["blocked"]


# --------------------------------------------------------------------------
# 2 — R2 AMENDMENT 1: `orchestrator.respec_cap`
# --------------------------------------------------------------------------


def test_the_second_lint_kill_blocks_at_the_default_cap_and_resamples_at_three(make_cfg):
    """R2 AMENDMENT 1 — "`orchestrator.respec_cap: 3` (R2 ruling)".

    Kill #1 landed under the ambiguous `neg2_readers` notation the writer
    prompt has since fixed, so counting it against the writer would have ended
    the slot on our own bug. The cap became per-batch config, default 2 = the
    shipped behaviour. Both readings are driven here on the same scripted
    kills: at the default the second kill is the end of the line, and at 3 it
    buys one more draw — which then passes and runs the pipeline out.
    """
    at_default = _drive_drafts(make_cfg, "idyn-cap-default", kills=2)
    cfg, _journal, runners, report = at_default

    blocked = _blocked_row(report)
    assert report["stop_reason"] == "blocked", report["stop_reason"]
    assert blocked["stage"] == S0_STAGE and blocked["state"] == "respec", blocked
    assert f"cap {orch.RESPEC_CAP}" in blocked["reason"], (
        f"the block must name the cap it hit (the provenance for raising it): {blocked['reason']}"
    )
    assert b11._table(cfg) == {_only_slot(report)["slug"]: "respec"}, b11._table(cfg)
    assert len(_edge_lines(cfg, KILL_EDGE)) == 2, b11._spine(b11._ledger_lines(cfg))
    assert len(_edge_lines(cfg, RESAMPLE_EDGE)) == 1, (
        "the second kill must not buy a third draw at the default cap: "
        f"{b11._spine(b11._ledger_lines(cfg))}"
    )
    assert len(runners.drafts) == 2, [d.name for d in runners.drafts]

    # …and the same two kills under the R2 ruling's cap.
    cfg3, _j3, runners3, report3 = _drive_drafts(make_cfg, "idyn-cap-three", kills=2, cap=3)

    assert _only_slot(report3)["blocked"] is None, _only_slot(report3)["blocked"]
    assert b11._table(cfg3) == {_only_slot(report3)["slug"]: "packaged"}, b11._table(cfg3)
    assert len(_edge_lines(cfg3, KILL_EDGE)) == 2, b11._spine(b11._ledger_lines(cfg3))
    assert len(_edge_lines(cfg3, RESAMPLE_EDGE)) == 2, (
        f"the raised cap must spend its allowance on a second re-sample: "
        f"{b11._spine(b11._ledger_lines(cfg3))}"
    )
    assert len(runners3.drafts) == 3, [d.name for d in runners3.drafts]
    assert len(_killed_dirs(cfg3)) == 2, (
        f"each kill is archived on its own: {[p.name for p in _killed_dirs(cfg3)]}"
    )
    assert _live_dirs(cfg3) == [runners3.drafts[-1]], [p.name for p in _live_dirs(cfg3)]


# --------------------------------------------------------------------------
# 3 — SECOND AMENDMENT: resume from `respec`
# --------------------------------------------------------------------------


def test_a_run_killed_at_respec_resumes_through_it_without_an_offledger_s1(make_cfg):
    """SECOND AMENDMENT — "Resume-from-`respec` fix (from the crash before
    this pass)": `_restage` skips recorded stages at/after the next scheduled
    stage ("pending", no off-ledger pre-run).

    `test_r2_hotfix3` reaches `respec` by BLOCKING at the cap — a clean
    shutdown with a report. This reaches it the way the pilot did: a ^C
    straight after the kill line lands, so run 1 never writes a report and the
    corpus is left mid-cycle with the kill already archived. The resume must
    (a) not pre-run the recorded S1 against the idea the NEXT re-sample has
    not drawn yet, (b) report that line as PENDING rather than stale, and
    (c) carry the slot out to `packaged` on a raised cap.
    """
    cfg, journal, _runners, killed_report = _drive_drafts(
        make_cfg, "idyn-resume-respec", kills=1, kill_after_lint=True
    )
    assert killed_report is None, "the ^C leg writes no batch report"
    assert len(journal.calls) == 2, [call.stage for call in journal.calls]
    slug = orch.slot_id(orch.batch_config(cfg)["id"], 1)
    assert b11._table(cfg) == {slug: "respec"}, (
        f"the ^C must leave the slot parked at `respec`: {b11._table(cfg)}"
    )
    assert _live_dirs(cfg) == [], (
        "the kill was archived before the ^C, so nothing claims the idea yet: "
        f"{[p.name for p in _live_dirs(cfg)]}"
    )

    # The adjudication between the runs, exactly as the pilot made it.
    cfg["orchestrator"]["respec_cap"] = 3

    resumed = b11._Journal()
    # ONE leg, so `slot.stale` is the list THIS resume built (`_restage` runs
    # once per leg and the last leg overwrites it — the h3 finding).
    first_leg = orch.run_batch(cfg, runners=_SpecDirRunners(resumed, cfg))

    assert resumed.calls, "the resume invoked no stage at all"
    assert resumed.calls[0].stage == S0_STAGE, (
        "the first thing a resume at `respec` may do is DRAW: an S1 call here is the "
        f"off-ledger re-spend the fix killed. Calls: {[c.stage for c in resumed.calls]}"
    )
    assert len(_stage_calls(resumed, S1_STAGE)) == 1, (
        f"S1 runs exactly once on the resume, on-ledger, after the re-sample: "
        f"{[c.stage for c in resumed.calls]}"
    )

    row = _only_slot(first_leg)
    s1_rows = [entry for entry in (row["stale"] or []) if entry["stage"] == S1_STAGE]
    assert s1_rows, (
        f"the recorded S1 line must be REPORTED (as pending), not silently dropped: "
        f"{row['stale']!r}"
    )
    for entry in s1_rows:
        assert entry["rerun"] is False and entry["current"] is None, entry
        assert entry.get("pending"), f"a pending row has to say why it is pending: {entry!r}"
    assert row["off_ledger_cost"]["runs"] == 0, (
        f"a clean resume spends nothing off-ledger; it charged {row['off_ledger_cost']}"
    )
    assert row["state"] == "played", f"one leg reaches the review stop: {row['state']}"

    final = orch.run_batch(cfg, runners=_SpecDirRunners(b11._Journal(), cfg),
                           review=(slug, "accept"))
    assert b11._table(cfg) == {slug: "packaged"}, b11._table(cfg)
    assert _only_slot(final)["blocked"] is None, _only_slot(final)["blocked"]
    assert len(_edge_lines(cfg, KILL_EDGE)) == 1, b11._spine(b11._ledger_lines(cfg))
    assert len(_edge_lines(cfg, RESAMPLE_EDGE)) == 1, b11._spine(b11._ledger_lines(cfg))


# --------------------------------------------------------------------------
# 4 — FOURTH AMENDMENT: the S2 effort cap (SKIPPED, with the reason)
# --------------------------------------------------------------------------


def test_the_s2_effort_cap_is_config_plumbing_and_is_pinned_elsewhere():
    """FOURTH AMENDMENT — "S2 effort cap (the silent-timeout diagnosis)".

    Every S2 session of that day produced ZERO output and died on the 1800s
    timeout with empty stdout: S2 ran at DEFAULT effort and an uncapped
    session can sit >30 minutes in silent extended thinking. The fix threads
    an `effort` key through the session policy (None = byte-identical old
    behaviour) and the pilot's S2 runs at `medium`.

    NOT AN ITERATION-DYNAMICS SCENARIO, and skipped deliberately rather than
    faked: the knob is read by `get_session_policy` and consumed by
    `session()`, neither of which any state of the machine can reach through
    the fake-runner rig — the rig exists precisely so no test opens a session.
    A test here could only re-assert the config, which
    `gen/tests/test_r2_hotfix5.py` already does at the right level (policy
    defaults, back-compat for configs without the key, and the pilot config's
    `effort: medium`). The loop-shaped part of that night — a stage that
    silently produced nothing — has no state to leave behind: the run died,
    the ledger recorded nothing, and resume re-ran S2 from the spec.
    """
    pytest.skip(
        "S2's `effort` knob is session-policy config, not iteration state: it is unreachable "
        "through the fake-runner rig (no test here opens a session) and is pinned at the right "
        "level by gen/tests/test_r2_hotfix5.py — "
        "test_the_localclaude_policy_defaults_carry_effort_none, "
        "test_a_config_without_the_key_gets_effort_none, "
        "test_the_pilot_config_caps_s2_effort_at_medium."
    )


# --------------------------------------------------------------------------
# 5 — FIFTH AMENDMENT: the escalation gets its findings
# --------------------------------------------------------------------------


def test_the_escalated_respec_is_handed_the_verifier_report_or_blocks_before_spend(make_cfg):
    """FIFTH AMENDMENT — "the escalation gets its findings".

    S2b rejected twice; §4's ×2 escalation fired and `_maybe_respec` invoked
    the PLAIN S1 stage, so the re-spec writer never saw the findings and
    blind-rewrote the same spec. The fix carries the report on the escalated
    ctx and blocks BEFORE the spend when it is missing.

    Driven as a full cycle, not as a unit: reject, re-implement, reject again,
    escalate, re-spec, and out through the rest of the pipeline. Exactly ONE
    ctx in that whole loop may carry an escalation, it must be an S1 ctx, and
    what it carries must be the report S2b left beside the worker.
    """
    cfg, _journal, runners, report = h6._drive_escalation(
        make_cfg, "idyn-escalation-findings", report=h6.REPORT
    )
    escalated = runners.escalated()

    assert len(escalated) == 1, (
        f"the ×2 escalation fires once per rejected spec: "
        f"{[(r.stage, r.n) for r in escalated]}"
    )
    receipt = escalated[0]
    assert receipt.stage == S1_STAGE, (
        f"the findings go to the WRITER; {receipt.stage!r} is not the S1 stage key"
    )
    assert isinstance(receipt.value, (str, Path)) and Path(receipt.value).is_file(), (
        f"the escalated ctx must point at a report on disk, got {receipt.value!r}"
    )
    assert receipt.payload == h6.REPORT, (
        "the escalated writer must be handed S2b's OWN findings — a blind re-spec is the "
        f"defect this amendment fixed. Got: {receipt.payload!r}"
    )
    assert Path(receipt.value).name in h6.VERIFIER_REPORT_NAMES, Path(receipt.value).name

    # …and the cycle really did go round: two rejects, two implementations.
    assert len(_edge_lines(cfg, REJECT_EDGE)) == orch.VERIFIER_REJECT_CAP_ESCALATE, \
        b11._spine(b11._ledger_lines(cfg))
    assert len(_edge_lines(cfg, IMPLEMENT_EDGE)) >= 2, b11._spine(b11._ledger_lines(cfg))
    assert b11._table(cfg) == {_only_slot(report)["slug"]: "packaged"}, b11._table(cfg)

    # The other half: no report, no re-spec — and no spend to find out.
    _cfg2, journal2, runners2, report2 = h6._drive_escalation(
        make_cfg, "idyn-escalation-blind", report=None
    )
    blocked = _blocked_row(report2)
    assert blocked["stage"] == S1_STAGE, blocked
    assert "verifier report" in " ".join(blocked["reason"].split()).lower(), (
        f"the block must name what is missing: {blocked['reason']!r}"
    )
    assert runners2.escalated() == [], "nothing may be escalated without findings to escalate"
    assert len(_stage_calls(journal2, S1_STAGE)) == 1, (
        "the blind re-spec must be stopped BEFORE the writer runs a second time: "
        f"{[c.stage for c in journal2.calls]}"
    )
    assert _only_slot(report2)["off_ledger_cost"]["runs"] == 0, (
        f"blocking before the spend means no off-ledger run at all: "
        f"{_only_slot(report2)['off_ledger_cost']}"
    )


# --------------------------------------------------------------------------
# 6 — FIFTH AMENDMENT, the slug pin: a re-spec that retitles
# --------------------------------------------------------------------------


def test_an_escalated_respec_that_retitles_blocks_at_the_stage_that_caused_it(make_cfg):
    """FIFTH AMENDMENT — the second defect the escalation exposed: the blind
    re-spec, "retitling nondeterministically, wrote a SECOND live corpus dir
    ('pump-flow-match-the-glow') that crashed discovery".

    The fix is a post-respec same-dir assertion that names the drift AT THE
    CAUSING STAGE. Driven here in the shape the machine can report on: the
    escalated S1 retitles and takes the draft with it, so exactly one dir
    claims the idea and it is not the dir the re-spec started from. The pin is
    WHERE the failure surfaces — a named block on the S1 stage, the ledger
    untouched, the slot still at `spec_ok` — rather than a `LedgerError` three
    stages later. (The other shape, a second LIVE dir, is the residual pinned
    by the test below.)
    """
    cfg, journal, runners, report = _drive_drafts(
        make_cfg, "idyn-respec-retitle", rejects=orch.VERIFIER_REJECT_CAP_ESCALATE,
        report=h6.REPORT, respec_drift="move",
    )
    lines_at_block = b11._ledger_lines(cfg)

    assert len(runners.drafts) == 2, (
        f"the scripted drift writes a second draft dir: {[d.name for d in runners.drafts]}"
    )
    first_draft, drifted = runners.drafts
    assert _live_dirs(cfg) == [drifted], (
        f"this shape leaves ONE dir, the retitled one: {[p.name for p in _live_dirs(cfg)]}"
    )

    blocked = _blocked_row(report)
    assert blocked["stage"] == S1_STAGE, (
        f"the drift must be named at the stage that caused it, not three stages later: {blocked}"
    )
    assert blocked["state"] == "spec_ok", blocked
    reason = " ".join(blocked["reason"].split())
    assert first_draft.name in reason and drifted.name in reason, (
        f"the block has to name BOTH dirs for the operator: {reason!r}"
    )
    assert "resolves to" in reason, (
        f"the same-dir assertion names where the idea went, not just that it moved: {reason!r}"
    )

    # …and nothing moved after the escalating reject: no half-advanced slot.
    assert (lines_at_block[-1]["from"], lines_at_block[-1]["to"]) == REJECT_EDGE, \
        b11._spine(lines_at_block)
    assert orch.ESCALATE_PREFIX in lines_at_block[-1]["reason"], lines_at_block[-1]["reason"]
    assert b11._table(cfg) == {_only_slot(report)["slug"]: "spec_ok"}, b11._table(cfg)
    assert report["stop_reason"] == "blocked", report["stop_reason"]
    assert len(_stage_calls(journal, S2_STAGE)) == 2, (
        "the blocked slot must not be re-implemented off the back of a drifted spec: "
        f"{[c.stage for c in journal.calls]}"
    )


def test_a_second_live_spec_dir_blocks_at_s1_and_still_trips_report_assembly(
    make_cfg, monkeypatch
):
    """FIFTH AMENDMENT, the residual it flagged in its own words: "the two-dir
    case still raises LedgerError at report-assembly time (unreachable by
    construction now)".

    The pilot's literal shape — the re-spec writes a second dir and the first
    one stays live. Two facts, and they are different facts:

      * `_maybe_respec` DOES block, at the S1 stage, naming both dirs. It is
        read off a spy on `_block_slot` because the report that would normally
        carry it never gets built.
      * `_slot_report` then re-resolves the slot's context and `LedgerError`
        escapes `run_batch`, so the run ends with no batch report at all.

    "Unreachable by construction" is a statement about the REAL S1 (which pins
    and enforces the slug); it is not a property of the state machine, and a
    fake writer walks straight into it. THIS TEST PINS THE RESIDUAL AS IT IS.
    When report assembly is made drift-tolerant, this test fails HERE — swap
    the `pytest.raises` for the report assertions the sibling test above uses
    and delete this paragraph.
    """
    blocks = _spy_on_blocks(monkeypatch)
    cfg, _journal, runners, _none = _drive_drafts(
        make_cfg, "idyn-respec-second-dir", rejects=orch.VERIFIER_REJECT_CAP_ESCALATE,
        report=h6.REPORT, respec_drift="second-dir", advance=False,
    )

    with pytest.raises(orch.LedgerError) as caught:
        orch.run_batch(cfg, runners=runners)

    first_draft, drifted = runners.drafts
    assert sorted(_live_dirs(cfg)) == sorted([first_draft, drifted]), (
        f"this shape leaves BOTH dirs live: {[p.name for p in _live_dirs(cfg)]}"
    )
    assert first_draft.name in str(caught.value) and drifted.name in str(caught.value), caught.value

    assert len(blocks) == 1, f"exactly one block, at the causing stage: {blocks}"
    block = blocks[0]
    assert block["stage"] == S1_STAGE and block["state"] == "spec_ok", block
    reason = " ".join(block["reason"].split())
    assert first_draft.name in reason and drifted.name in reason, (
        f"the block has to name BOTH dirs for the operator: {reason!r}"
    )
    assert "spec dir" in reason.lower(), reason

    # The slot did not advance on a drifted spec, report or no report.
    lines = b11._ledger_lines(cfg)
    assert (lines[-1]["from"], lines[-1]["to"]) == REJECT_EDGE, b11._spine(lines)
    assert orch.ESCALATE_PREFIX in lines[-1]["reason"], lines[-1]["reason"]
    assert b11._table(cfg) == {orch.slot_id(orch.batch_config(cfg)["id"], 1): "spec_ok"}, \
        b11._table(cfg)


# --------------------------------------------------------------------------
# 7 — SEVENTH AMENDMENT: one interpreter per capture (the SMOKE)
# --------------------------------------------------------------------------


def test_two_isolated_captures_of_an_edited_worker_both_succeed(tmp_path):
    """SEVENTH AMENDMENT — "one interpreter per capture (defect #8)".

    The convergence run's round-5 verify crashed with `module 'game_…' has no
    attribute 'route'` from the LIVE solver against a game that defines it:
    five verifier rounds in ONE orchestrator process, and the generated
    solver's §7 sibling-load caches in `sys.modules` under a path-derived key,
    so round 5's fresh solver was served round 4's game module.

    The loop-shaped half of that defect is what this file is for, and it is
    reachable without the rig: two captures in THIS process, with the worker
    edited in place between them — the shape repeated verifier rounds have.
    `test_r2_hotfix8` owns the eleven isolation pins (pids, timeouts, parity,
    the in-process negative control); this is the standing smoke that the
    repeated-round path stays clean, driven against
    `gen.frames.capture_worker_isolated` by name. Measured at ~1.4s for both
    captures, against the ~20s budget this layer allows itself.
    """
    worker = h8._write_worker(tmp_path / "worker", route=h8.ROUTE_V1)
    first = frames_module.capture_worker_isolated(worker)
    assert first.win is True and first.levels_completed == 2, (
        f"round 1 must be a clean win; got win={first.win} levels={first.levels_completed}"
    )

    h8._rename_round_two(worker)   # a CONSISTENT pair: nothing on disk names the old helper
    second = frames_module.capture_worker_isolated(worker)
    assert second.win is True and second.levels_completed == 2, (
        "round 2 failed although the pair on disk is consistent — that is the pilot's stale "
        f"sibling-module bug back in a repeated round: win={second.win} "
        f"levels={second.levels_completed}"
    )
    assert second.records, "round 2 must produce frames, not an empty capture"
    import sys

    assert sys.modules.get(h8.FIXED_CACHE_KEY) is None, (
        f"a capture must leave no {h8.FIXED_CACHE_KEY!r} in the PARENT interpreter — that "
        "residue is exactly what poisoned round 5"
    )


# --------------------------------------------------------------------------
# 8 — EIGHTH AMENDMENT: the decl-only marker's lifecycle across a cycle
# --------------------------------------------------------------------------


def test_a_declaration_only_respec_leaves_its_marker_across_the_cycle(batch_home, make_cfg):
    """EIGHTH AMENDMENT — "declaration-only re-specs skip the re-implement".

    Rounds 5-7 proved the second oscillation axis: every declaration-driven
    re-spec re-triggered S2 through §2's byte-hash cascade, and every
    re-implement handed the audit NOVEL surface (3-for-3). The marker is the
    carrier of the one decision that freezes it.

    `test_r2_hotfix9` pins the marker's creation, its single-shot consumption
    and its projection at the UNIT level. What that file cannot reach is the
    loop: `run_batch` takes the runner table as a REPLACEMENT, so the real S2
    runner — the marker's consumer — is never called under fakes. This drives
    the whole escalation cycle and pins the two halves the rig CAN witness:
    the marker is on disk at the moment the next stage is entered, and the
    machine goes round to `implemented` again and out to the review stop.
    """
    cfg, _journal, runners, report = h9._drive(
        make_cfg, batch_home, "idyn-marker-decl", respec_bytes=h9.DECL_ONLY_SPEC
    )
    respec_call = h9._assert_escalated(runners)

    after = [entry for entry in runners.entries if entry["n"] > respec_call]
    assert after, (
        "the re-spec was the last stage call of the run — there is no next stage to hand the "
        f"marker to: {[(e['n'], e['stage']) for e in runners.entries]}"
    )
    assert after[0]["markers"], (
        "a declaration-only re-spec must leave its marker for the stage that follows it; the "
        f"next stage was entered with none. Entries: {after[0]}"
    )
    assert len(h9._markers(batch_home)) >= 1, "…and it is still on disk at the end of the run"

    # …and the loop closed: the slot re-implemented and reached the review stop.
    implemented = _edge_lines(cfg, IMPLEMENT_EDGE)
    assert len(implemented) >= 2, (
        f"the machine must reach `implemented` again after the re-spec: "
        f"{b11._spine(b11._ledger_lines(cfg))}"
    )
    assert b11._table(cfg) == {_only_slot(report)["slug"]: "packaged"}, b11._table(cfg)
    assert _only_slot(report)["blocked"] is None, _only_slot(report)["blocked"]


def test_a_substantive_respec_leaves_no_marker_and_sweeps_a_stale_one(batch_home, make_cfg):
    """EIGHTH AMENDMENT, the other direction — "stale markers are swept on any
    real change".

    The same cycle, with a re-spec that also edits a level sketch: the
    implementation projection MOVES, so nothing may authorize skipping the
    re-implement — and a marker left by an earlier decl-only round must be
    GONE, not merely ignored. A marker that survived a real change would skip
    a re-implement the spec genuinely needs.
    """
    cfg, _journal, runners, report = h9._drive(
        make_cfg, batch_home, "idyn-marker-substantive",
        respec_bytes=h9.ALSO_A_LEVEL_SPEC, stale=h9.STALE_MARKER,
    )
    respec_call = h9._assert_escalated(runners)

    assert runners.stale_planted, "the stale marker was never planted; this test proves nothing"
    after = [entry for entry in runners.entries if entry["n"] > respec_call]
    assert after, [(e["n"], e["stage"]) for e in runners.entries]
    assert after[0]["markers"] == [], (
        "a substantive re-spec must leave NO marker — and must clear the stale one it found: "
        f"{after[0]}"
    )
    assert h9._markers(batch_home) == [], (
        f"no marker may survive the run: {[str(p) for p in h9._markers(batch_home)]}"
    )
    for marker in runners.stale_planted:
        assert not marker.exists(), f"the stale marker outlived a real change: {marker}"

    assert len(_edge_lines(cfg, IMPLEMENT_EDGE)) >= 2, b11._spine(b11._ledger_lines(cfg))
    assert b11._table(cfg) == {_only_slot(report)["slug"]: "packaged"}, b11._table(cfg)


# --------------------------------------------------------------------------
# 9 — STATE AS PARKED: the accept latch, at the loop level
# --------------------------------------------------------------------------


def test_the_parked_state_resumes_to_played_without_re_verifying(make_cfg, monkeypatch):
    """STATE AS PARKED (2026-09-23 ~07:20Z) — "DO NOT plain-resume".

    The game passed everything once: verified clean, gated, baselined — then
    the battery crashed on a transient network error, §4's crash edge
    re-walked the chain, and the verifier REJECTED the identical bytes it had
    just accepted. Phase A's contract: "a `verified` ledger line memoizes on
    its game hash — a re-verify of a game hash the ledger already accepted
    short-circuits to the recorded verdict, no session".

    Driven as the parked shape itself. Run 1 walks
    `implemented -> verified -> gated -> baselined -> played(crash) ->
    implemented` and is ^C'd the instant the crash pair lands. Run 2 resumes
    with the REAL S2b runner wired in at its own stage key and its two
    expensive legs monkeypatched to raise: `capture_worker_isolated` and
    `run_agent_pass`. Reaching either is the spurious re-roll, and it fails
    the test by name.

    (The brief allowed an xfail reading "accept-latching (Phase A)" if the
    contract had not landed. It has — `orchestrator._latched_verify` — so this
    is a hard pin: a revert fails here loudly.)
    """
    cfg, _path = make_cfg("idyn-parked")
    slug = orch.slot_id(orch.batch_config(cfg)["id"], 1)
    journal = b11._Journal()
    parked = _ParkAtCrash(
        journal, cfg,
        outcomes={"baselined": b11._Outcome(
            "implemented", "battery crash: OpenRouter SSL handshake timeout", times=1
        )},
    )
    with pytest.raises(KeyboardInterrupt):
        orch.run_batch(cfg, runners=parked)

    # The parked SHAPE, asserted before anything is resumed.
    spine = b11._spine(b11._ledger_lines(cfg), slug)
    assert spine[-6:] == [
        ("spec_ok", "implemented"),
        ("implemented", "verified"),
        ("verified", "gated"),
        ("gated", "baselined"),
        ("baselined", "played"),
        ("played", "implemented"),
    ], f"this is not the parked state the amendment describes: {spine}"
    assert b11._table(cfg) == {slug: "implemented"}, b11._table(cfg)

    accepted = [
        line for line in b11._ledger_lines(cfg)
        if (line["from"], line["to"]) == ("implemented", "verified")
    ]
    assert len(accepted) == 1, b11._spine(b11._ledger_lines(cfg))
    spec_dir = orch._discover_spec_dir(
        _corpus_dir(cfg), journal.contexts[-1].idea_path
    )
    assert spec_dir is not None, "the parked slot must still have its corpus dir"
    worker = spec_dir / orch.WORKER_DIRNAME
    assert accepted[0]["hashes"]["game"] == orch._game_hash(worker), (
        "the parked worker's bytes must still hash to the G the accept recorded — otherwise "
        "this test is about a different game and proves nothing"
    )
    for name in (VERIFIER_REPORT_NAME, VERIFIER_FRAMES_NAME):
        assert (spec_dir / name).is_file(), (
            f"the accept's evidence must still be beside the worker ({name}); without it the "
            "latch un-latches by design and this scenario cannot be driven"
        )

    # Resume: real S2b, forbidden expensive legs.
    monkeypatch.setattr(
        frames_module, "capture_worker_isolated", _boom("frames.capture_worker_isolated")
    )
    monkeypatch.setattr(s3_verify_module, "run_agent_pass", _boom("s3_verify.run_agent_pass"))
    resumed = b11._Journal()
    runners = _EvidenceRunners(resumed, cfg)
    runners[S2B_STAGE] = orch.default_runners()[S2B_STAGE]

    report = orch.run_batch(cfg, runners=runners)

    assert b11._table(cfg) == {slug: "played"}, (
        f"the resume must re-walk the chain to `played` for the human: {b11._table(cfg)}"
    )
    assert _stage_calls(resumed, S2B_STAGE) == [], (
        "the REAL S2b runner is wired in at that key, so a fake call here means the wiring "
        f"broke: {[c.stage for c in resumed.calls]}"
    )
    latched = [
        line for line in b11._ledger_lines(cfg)
        if (line["from"], line["to"]) == ("implemented", "verified")
    ]
    assert len(latched) == 2, (
        f"the re-walk must record its own `verified` line: {b11._spine(b11._ledger_lines(cfg))}"
    )
    assert "latch" in latched[-1]["reason"].lower(), (
        "RENEGOTIABLE (the wording is the implementation's): the second accept must read as a "
        f"latched verdict, not a fresh audit — {latched[-1]['reason']!r}"
    )
    assert latched[-1]["cost"] is None, (
        f"a latched verdict costs nothing — no session ran: {latched[-1]['cost']}"
    )
    assert _only_slot(report)["blocked"] is None, _only_slot(report)["blocked"]


# --------------------------------------------------------------------------
# the resume matrix — every truncated prefix of a full happy history
# --------------------------------------------------------------------------


@pytest.mark.parametrize("prefix", range(len(HAPPY_SPINE) + 1))
def test_a_resume_from_every_truncated_ledger_prefix_completes(make_cfg, prefix):
    """THE GENERALIZATION of the night's mid-cycle resume crash.

    B11's kill sweep kills at stage BOUNDARIES, which only ever leaves the
    ledger and the artifact tree in step. The pilot's crashes did not: a ^C
    between a stage's write and its append, a line lost, a cycle half-walked.
    The implementation-independent form of "resume is safe at any point" is
    this: truncate a COMPLETE happy history to every prefix length, leave the
    full artifact tree on disk, and require the machine to replay that prefix
    and run the slot out to `packaged` — from every one of them, with no
    exception at all.
    """
    cfg, _path = make_cfg(f"idyn-prefix-{prefix:02d}")
    slug = orch.slot_id(orch.batch_config(cfg)["id"], 1)
    b11._advance(cfg, b11._Runners(b11._Journal(), cfg))
    assert b11._table(cfg) == {slug: "packaged"}, b11._table(cfg)

    lines = b11._ledger_lines(cfg)
    assert b11._spine(lines, slug) == list(HAPPY_SPINE), (
        f"the happy path this matrix truncates has moved: {b11._spine(lines, slug)}"
    )

    ledger = b11._ledger_path(cfg)
    ledger.write_text(
        "".join(json.dumps(line) + "\n" for line in lines[:prefix]), encoding="utf-8"
    )
    replayed = orch.replay_ledger(ledger)
    expected_state = HAPPY_SPINE[prefix - 1][1] if prefix else None
    assert (replayed[slug]["state"] if prefix else None) == expected_state, replayed

    report = b11._advance(cfg, b11._Runners(b11._Journal(), cfg))
    assert b11._table(cfg) == {slug: "packaged"}, (
        f"a resume from the {prefix}-line prefix (state {expected_state!r}) did not finish: "
        f"{b11._table(cfg)}"
    )
    assert _only_slot(report)["blocked"] is None, _only_slot(report)["blocked"]
    assert b11._spine(b11._ledger_lines(cfg), slug)[:prefix] == list(HAPPY_SPINE[:prefix]), (
        "the resume rewrote history it had already recorded"
    )
