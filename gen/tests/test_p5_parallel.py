"""P-5 acceptance (implementer lane): parallel slots, end to end and hermetic.

Run: .venv/bin/python -m pytest gen/tests/test_p5_parallel.py -q

THE HOUSE RULE IS THE FIRST TEST HERE and everything else is built around it:
an unarmed run — `orchestrator.parallel_slots` absent or false, or one worker —
must be today's bytes, must gain no report key and must never reach the spawn
seam. Every historical config on disk already carries a decorative
`orchestrator.workers: 4`, so that guarantee is what keeps a resume of b001..
b005r2 sequential forever.

The armed half is driven with an IN-PROCESS child injected through
`gen.orchestrator.spawn_slot` (the seam exists for exactly this: the default is
a real `sys.executable -m gen.orchestrator --slot` subprocess, which cannot be
handed injected runners). The children run in the parent's own thread pool
against the SAME ledger file, so the interleaving, the flock and the sidecar
merge are all really exercised — the only thing faked is the stage work.

HERMETIC: `batch_home` rebinds every REPO_ROOT-rooted Path on
`gen.orchestrator` into `tmp_path` (the b11 discipline), an autouse fixture
forbids the network and `gen.backends.get_driver`, and a second one fails any
test that writes into the repo's own `out/batches/`, `out/ideas/` or `out/tmp/`.

NOTE ON THE BLIND LANE: `gen/tests/test_v2_parallel.py` is written from the
contract alone by another agent and is never touched from here. This file is
the implementer's own evidence and deliberately reads the implementation.
"""

from __future__ import annotations

import copy
import inspect
import json
import os
import socket
import threading
import time
import urllib.request
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path

import pytest
import yaml

from gen import orchestrator as orch
from gen import s0_ideas, s1_spec
from gen.config import REPO_ROOT, load_config

CONFIG = "config/b001-pilot.yaml"
_CFG = load_config(CONFIG)

#: The frozen `hashes` shape a ledger line must carry (`_check_hashes`).
_HASHES = {"spec": None, "game": None, "stage_input": "fake-digest"}

#: The happy §4 walk a fake stage takes when nothing is scripted against it.
HAPPY_NEXT = {
    None: "ideated",
    "respec": "ideated",
    "ideated": "spec_ok",
    "spec_ok": "implemented",
    "implemented": "verified",
    "verified": "gated",
    "gated": "baselined",
    "baselined": "played",
    "reviewed": "packaged",
}

#: The §2 artifacts each fake stage lands BEFORE its transition is appended.
#: Paths are relative to the slot's corpus dir, which S1 creates.
STAGE_ARTIFACTS = {
    "spec_ok": ("spec.yaml", "spec.md", "lint-report.json"),
    "implemented": ("worker/game.py", "worker/solver.py"),
    "verified": ("worker.verifier-report.json",),
    "gated": ("acceptance-report.json",),
    "baselined": ("worker.s4/metadata.json",),
    "played": ("battery-report.json",),
    "packaged": ("package/manifest.json",),
}


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _no_network_no_agent(monkeypatch):
    """No test here dials out or starts a real agent session."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("a P-5 test opened a network connection or an agent session")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    from gen import backends
    monkeypatch.setattr(backends, "get_driver", _forbidden)


@pytest.fixture(autouse=True)
def _repo_is_never_the_workspace():
    """A P-5 test that wrote into one of the repo's own stage roots fails here.

    `out/ideas` is watched as closely as `out/batches` because the S0 draw-lock
    tests below run the REAL `sample_batch`, whose dedupe history is a module
    constant (`s0_ideas.DEDUPE_HISTORY_PATH`) that `batch_home` does not move —
    a test that forgot to redirect it would append to the repo's own history.
    """
    roots = [REPO_ROOT / "out" / name for name in ("batches", "ideas", "tmp")]

    def snapshot():
        return {str(root): (sorted(str(path) for path in root.rglob("*"))
                            if root.exists() else None) for root in roots}

    before = snapshot()
    yield
    after = snapshot()
    for root in roots:
        assert after[str(root)] == before[str(root)], f"a P-5 test wrote into {root}"


@pytest.fixture
def batch_home(tmp_path, monkeypatch) -> Path:
    """Point every repo-rooted path in the orchestrator at `tmp_path` (b11 §fixtures)."""
    for name, value in list(vars(orch).items()):
        if name.startswith("__") or not isinstance(value, Path):
            continue
        try:
            relative = value.resolve().relative_to(REPO_ROOT)
        except ValueError:
            continue
        monkeypatch.setattr(orch, name, tmp_path / relative)
    monkeypatch.setattr("gen.config.REPO_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def make_cfg(batch_home, tmp_path):
    """(cfg dict, config path) for a batch id nobody else uses."""

    def _make(batch_id: str, *, size: int = 2, workers: int | None = None,
              parallel: object = None, wave_size: int | None = None,
              auto_accept: bool = True) -> tuple[dict, Path]:
        cfg = copy.deepcopy(_CFG)
        cfg["batch"]["id"] = batch_id
        cfg["batch"]["size"] = size
        cfg["batch"].pop("tier_sequence", None)
        if workers is not None:
            cfg["orchestrator"]["workers"] = workers
        if wave_size is not None:
            cfg["orchestrator"]["wave_size"] = wave_size
        if parallel is not None:
            cfg["orchestrator"]["parallel_slots"] = parallel
        cfg.setdefault("review", {})["auto_accept"] = auto_accept
        path = tmp_path / f"{batch_id}.yaml"
        path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        return cfg, path

    return _make


# --------------------------------------------------------------------------- #
# the fake stage runners
# --------------------------------------------------------------------------- #


class _Lockstep:
    """Make the in-process children take turns, so the ledger really interleaves.

    A broken barrier (one child taking a different number of steps, or a single
    child running alone) degrades to "do not wait" rather than deadlocking — the
    interleaving is the point of the fixture, never the assertion's only hope.
    """

    def __init__(self, parties: int, timeout: float = 0.5) -> None:
        self._barrier = threading.Barrier(parties, timeout=timeout) if parties > 1 else None

    def wait(self) -> None:
        if self._barrier is None:
            return
        try:
            self._barrier.wait()
        except threading.BrokenBarrierError:
            pass


class _Journal:
    """Every fake stage call, in the order they really happened."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []   # (slug, stage, to_state)
        self._lock = threading.Lock()

    def record(self, slug: str, stage: str, to_state: str) -> None:
        with self._lock:
            self.calls.append((slug, stage, to_state))

    def stages(self, slug: str) -> list[str]:
        return [stage for call_slug, stage, _ in self.calls if call_slug == slug]


def _slot_dir(ctx) -> Path:
    """This slot's corpus dir — the one S1 creates and everything after it uses."""
    return ctx.spec_dir if ctx.spec_dir is not None else ctx.corpus_dir / f"spec-{ctx.slug}"


def _write_artifacts(ctx, to_state: str) -> dict:
    """Land the §2 artifacts for `to_state` and return them as `artifacts`."""
    written: dict[str, str] = {}
    root = _slot_dir(ctx)
    if to_state == "ideated":
        ctx.idea_path.parent.mkdir(parents=True, exist_ok=True)
        ctx.idea_path.write_text(json.dumps({"id": f"{ctx.batch_id}-i{ctx.index:03d}"}) + "\n",
                                 encoding="utf-8")
        return {"idea": str(ctx.idea_path)}
    if to_state == "spec_ok":
        # S1's own shape: the dir is named by the spec and carries the idea copy,
        # which is how `_discover_spec_dir` links a slot to it.
        root.mkdir(parents=True, exist_ok=True)
        (root / "idea.json").write_bytes(ctx.idea_path.read_bytes())
        written["idea"] = str(root / "idea.json")
    for rel in STAGE_ARTIFACTS.get(to_state, ()):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        body = (f'"""fake {to_state} for {ctx.slug}."""\n' if path.suffix == ".py"
                else json.dumps({"slug": ctx.slug, "state": to_state}) + "\n"
                if path.suffix == ".json"
                else f"# fake {to_state}\nslug: {ctx.slug}\n")
        path.write_text(body, encoding="utf-8")
        written[Path(rel).name] = str(path)
    return written


def fake_runners(journal: _Journal, *, lockstep: _Lockstep | None = None,
                 green_fail_once: bool = False) -> dict:
    """A full S0..S6 runner table that walks the happy path with no spend.

    `green_fail_once` makes each slug's FIRST `s2_implement` call fail below the
    green-attempts cap — an attempt that spends and appends no ledger line,
    which is exactly the off-ledger cost the sidecar merge has to carry.
    """
    failed: set[str] = set()
    lock = threading.Lock()

    def _make(stage: str):
        def runner(ctx) -> dict:
            if lockstep is not None:
                lockstep.wait()
            if stage == "s2_implement" and green_fail_once:
                with lock:
                    first = ctx.slug not in failed
                    failed.add(ctx.slug)
                if first:
                    journal.record(ctx.slug, stage, "spec_ok")
                    return {"ok": False, "to_state": "spec_ok",
                            "reason": "fake green loop: red validate",
                            "cost": {"usd": 0.25, "tokens_in": 10, "tokens_out": 1}}
            to_state = HAPPY_NEXT[ctx.state]
            artifacts = _write_artifacts(ctx, to_state)
            journal.record(ctx.slug, stage, to_state)
            return {"ok": True, "to_state": to_state, "reason": f"fake {stage}: green",
                    "cost": {"usd": 0.5, "tokens_in": 20, "tokens_out": 2},
                    "artifacts": artifacts}

        return runner

    return {stage: _make(stage) for stage in orch.STAGES}


def in_process_seam(cfg: Mapping, runners: Mapping, *, started: list,
                    fail: set[str] = frozenset()):
    """A child that runs `run_slot` HERE instead of spawning a subprocess.

    The seam's whole purpose (contract P-5 §6): the real default cannot be
    handed injected runners, so a test substitutes this and gets the same slot
    code path against the same ledger file.
    """
    lock = threading.Lock()

    def seam(*, config_path, slug, batch_dir):
        with lock:
            started.append(slug)
        if slug in fail:
            raise RuntimeError(f"injected child failure for {slug}")
        return orch.run_slot(cfg, slug, runners=runners)["exit_code"]

    return seam


def _booby_trap(*, config_path, slug, batch_dir):
    raise AssertionError(
        f"an UNARMED run reached the spawn seam for {slug} — contract P-5's house rule is "
        "that `orchestrator.parallel_slots` absent/false spawns nothing at all"
    )


def _ledger_lines(cfg) -> list[dict]:
    path = Path(orch.batch_dir(cfg)) / orch.LEDGER_NAME
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# --------------------------------------------------------------------------- #
# 1. the arming knob
# --------------------------------------------------------------------------- #


def test_parallel_slots_defaults_to_false():
    """Absent block, absent key and `false` are all today (contract P-5 §1)."""
    assert orch._parallel_slots({}) is False
    assert orch._parallel_slots({"orchestrator": {}}) is False
    assert orch._parallel_slots({"orchestrator": {"parallel_slots": False}}) is False
    assert orch._parallel_slots({"orchestrator": {"parallel_slots": True}}) is True


@pytest.mark.parametrize("value", [1, 0, "true", "yes", 2.0, None, []])
def test_a_non_bool_parallel_slots_is_loud(value):
    """`1` is not a `true` — the house style for every knob in this module."""
    with pytest.raises(ValueError, match="orchestrator.parallel_slots must be a bool"):
        orch._parallel_slots({"orchestrator": {"parallel_slots": value}})


def test_orchestrator_config_validates_the_knob_but_does_not_report_it():
    """Validated beside `workers`; absent from the dict the report embeds (§1)."""
    cfg = {"orchestrator": {"workers": 2, "wave_size": 5, "max_attrition": 0.3}}
    assert set(orch.orchestrator_config(cfg)) == {"workers", "wave_size", "max_attrition"}, (
        "the report's `config.orchestrator` block must gain no key on an unarmed run"
    )
    cfg["orchestrator"]["parallel_slots"] = "sure"
    with pytest.raises(ValueError, match="parallel_slots"):
        orch.orchestrator_config(cfg)


# --------------------------------------------------------------------------- #
# 2. byte-identity: an unarmed run never spawns and gains no key
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        ("a historical config: workers 4, no parallel_slots", {"workers": 4}),
        ("explicitly disarmed", {"workers": 4, "parallel": False}),
        ("armed at ONE worker — nothing to spawn", {"workers": 1, "parallel": True}),
    ],
)
def test_an_unarmed_run_never_spawns_and_gains_no_report_key(
    make_cfg, monkeypatch, label, kwargs
):
    """Contract P-5's house rule, at both layers it can be measured on."""
    monkeypatch.setattr(orch, "spawn_slot", _booby_trap)
    cfg, _path = make_cfg("p5-unarmed", size=2, **kwargs)
    journal = _Journal()
    report = orch.run_batch(cfg, runners=fake_runners(journal))

    assert "parallel" not in report, (
        f"{label}: the sequential report must gain NO new key. Got {sorted(report)}"
    )
    assert set(report["config"]["orchestrator"]) == {"workers", "wave_size", "max_attrition"}
    assert [row["state"] for row in report["slots"]] == ["packaged", "packaged"]
    assert journal.stages("p5-unarmed-s001")[0] == "s0_ideas"


def test_the_unarmed_report_is_identical_whether_the_key_is_absent_or_false(make_cfg,
                                                                            monkeypatch):
    """Absent and `false` are the same run, key for key and value for value."""
    monkeypatch.setattr(orch, "spawn_slot", _booby_trap)
    reports = []
    for index, parallel in enumerate((None, False)):
        cfg, _path = make_cfg(f"p5-same-{index}", size=2, workers=4, parallel=parallel)
        reports.append(orch.run_batch(cfg, runners=fake_runners(_Journal())))

    def _scrub(report: dict) -> dict:
        """Everything but the batch's own name, clock and paths."""
        body = json.dumps(report, indent=2)
        body = body.replace("p5-same-0", "<batch>").replace("p5-same-1", "<batch>")
        scrubbed = json.loads(body)
        scrubbed["timestamps"] = scrubbed["paths"] = None
        for row in scrubbed["slots"]:
            row["first_ts"] = row["last_ts"] = row["paths"] = None
        return scrubbed

    assert _scrub(reports[0]) == _scrub(reports[1])


# --------------------------------------------------------------------------- #
# 3. the ledger lock
# --------------------------------------------------------------------------- #


def test_append_lines_holds_an_exclusive_flock_around_the_write(tmp_path, monkeypatch):
    """Contract P-5 §3: the lock is TAKEN, and it is taken before the bytes."""
    import fcntl

    seen: list[tuple[int, bool]] = []
    ledger = tmp_path / "ledger.jsonl"
    real_flock = fcntl.flock

    def spy(fileno, operation):
        seen.append((operation, ledger.exists() and ledger.stat().st_size > 0))
        return real_flock(fileno, operation)

    monkeypatch.setattr(orch.fcntl, "flock", spy)
    line = orch._line(slug="b-s001", from_state=None, to_state="ideated",
                      reason="first", hashes=_HASHES, cost=None)
    orch._append_lines(ledger, [line])

    assert seen, "no flock was taken during _append_lines"
    assert seen[0][0] == fcntl.LOCK_EX, f"the lock must be exclusive, got {seen[0][0]}"
    assert seen[0][1] is False, "the lock must be taken BEFORE the write, not after"


def test_a_two_line_pair_stays_adjacent_under_the_lock(tmp_path):
    """The battery-crash / review pairs are one blob, so one lock holds both."""
    ledger = tmp_path / "ledger.jsonl"
    pair = [
        orch._line(slug="b-s001", from_state="baselined", to_state="played",
                   reason="battery done", hashes=_HASHES, cost=None),
        orch._line(slug="b-s001", from_state="played", to_state="implemented",
                   reason=orch.CRASH_REASON, hashes=_HASHES, cost=None),
    ]
    orch._append_lines(ledger, pair)
    lines = [json.loads(raw) for raw in ledger.read_text(encoding="utf-8").splitlines()]
    assert [(row["from"], row["to"]) for row in lines] == [
        ("baselined", "played"), ("played", "implemented")]


# --------------------------------------------------------------------------- #
# 4. child mode: --slot
# --------------------------------------------------------------------------- #


def test_a_slot_run_writes_a_sidecar_and_no_batch_report(make_cfg):
    """Contract P-5 §2: its own ledger lines, its own sidecar, nothing batch-wide."""
    cfg, _path = make_cfg("p5-child", size=2, workers=1)
    journal = _Journal()
    runners = fake_runners(journal)
    # The parent's job, done by hand: the idea has to exist before a child runs.
    slots = orch._slots(cfg, orch.batch_config(cfg), {})
    bdir = orch.batch_dir(cfg)
    orch._force_s0(slots, cfg=cfg, batch_id="p5-child", bdir=bdir,
                   ledger_path=bdir / orch.LEDGER_NAME, stages=runners)

    report = orch.run_slot(cfg, "p5-child-s001", runners=runners)

    assert report["exit_code"] == 0 and report["slug"] == "p5-child-s001"
    assert report["slot"]["state"] == "packaged"
    assert not (bdir / orch.BATCH_REPORT_NAME).exists(), (
        "a child must never write the batch report — the merge does"
    )
    sidecar = orch.slot_report_path(bdir, "p5-child-s001")
    assert sidecar.is_file() and sidecar.name.endswith(orch.SLOT_REPORT_SUFFIX)
    assert json.loads(sidecar.read_text(encoding="utf-8"))["slot"]["slug"] == "p5-child-s001"
    assert {row["slug"] for row in _ledger_lines(cfg)} == {"p5-child-s001", "p5-child-s002"}, (
        "only the parent's S0 lines for the sibling, never a child's work on it"
    )
    assert journal.stages("p5-child-s002") == ["s0_ideas"], (
        "the child touched the sibling's stages"
    )


def test_an_unknown_slug_is_loud_and_names_the_batch_slots(make_cfg):
    cfg, _path = make_cfg("p5-unknown", size=2)
    with pytest.raises(ValueError, match=r"not a slot of batch 'p5-unknown' at size 2"):
        orch.run_slot(cfg, "p5-unknown-s009", runners=fake_runners(_Journal()))


def test_slot_refuses_to_combine_with_status_or_review(make_cfg, capsys):
    _cfg, path = make_cfg("p5-refuse", size=1)
    for extra in (["--status"], ["--review", "p5-refuse-s001:accept"]):
        code = orch.main(["--config", str(path), "--slot", "p5-refuse-s001", *extra])
        err = capsys.readouterr().err
        assert code == 1, f"{extra} with --slot must be refused"
        assert "--slot is the parallel CHILD mode" in err, err


def test_the_slot_flag_drives_the_child_through_main(make_cfg, capsys):
    """The whole argv path a spawned child really takes, on a TERMINAL slot.

    Terminal on purpose: `_work_slot` returns before a single runner is asked
    for, so this exercises `main` -> `run_slot` -> sidecar -> exit code with no
    injected runners at all — which is the one thing the in-process seam cannot
    prove, since a real child is `python -m gen.orchestrator --slot`.
    """
    cfg, path = make_cfg("p5-argv", size=1, workers=1)
    orch.run_batch(cfg, runners=fake_runners(_Journal()))
    bdir = Path(orch.batch_dir(cfg))
    (bdir / orch.BATCH_REPORT_NAME).unlink()

    assert orch.main(["--config", str(path), "--slot", "p5-argv-s001"]) == 0
    out = capsys.readouterr().out
    assert "[b11] p5-argv-s001 | packaged |" in out, out
    assert "[b11] SLOT COMPLETE (terminal)" in out, out
    assert orch.slot_report_path(bdir, "p5-argv-s001").is_file()
    assert not (bdir / orch.BATCH_REPORT_NAME).exists(), (
        "the child mode must never write a batch report"
    )

    assert orch.main(["--config", str(path), "--slot", "p5-argv-s404"]) == 1
    assert "not a slot of batch" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# 5. the parent: S0 once, before anything forks
# --------------------------------------------------------------------------- #


def test_every_idea_exists_before_any_child_starts(make_cfg, monkeypatch):
    """Contract P-5 §4: the batch-wide draw happens once, in the parent."""
    cfg, path = make_cfg("p5-s0", size=3, workers=3)
    cfg["orchestrator"]["parallel_slots"] = True
    journal = _Journal()
    runners = fake_runners(journal)
    started: list[str] = []
    ideas_at_first_start: list[list[str]] = []
    bdir = orch.batch_dir(cfg)

    inner = in_process_seam(cfg, runners, started=started)

    def seam(*, config_path, slug, batch_dir):
        if not ideas_at_first_start:
            ideas_at_first_start.append(
                sorted(p.name for p in (orch.IDEAS_ROOT / "p5-s0").glob("idea-*.json")))
        return inner(config_path=config_path, slug=slug, batch_dir=batch_dir)

    monkeypatch.setattr(orch, "spawn_slot", seam)
    orch.run_batch(cfg, runners=runners, config_path=path)

    assert ideas_at_first_start[0] == ["idea-001.json", "idea-002.json", "idea-003.json"], (
        "every idea file must be on disk before the first child exists"
    )
    s0_calls = [call for call in journal.calls if call[1] == "s0_ideas"]
    assert len(s0_calls) == 3, f"S0 must run exactly once per slot, in the parent: {s0_calls}"
    assert all(row["to"] == "ideated" for row in _ledger_lines(cfg)[:3])
    assert str(bdir).startswith(str(orch.BATCHES_ROOT))


def test_the_parents_own_s0_invocation_survives_the_merge(make_cfg, monkeypatch):
    """The merged row must not lose the stage the parent ran (§5, `invocations`)."""
    cfg, path = make_cfg("p5-inv", size=2, workers=2, parallel=True)
    runners = fake_runners(_Journal())
    monkeypatch.setattr(orch, "spawn_slot", in_process_seam(cfg, runners, started=[]))
    report = orch.run_batch(cfg, runners=runners, config_path=path)
    for row in report["slots"]:
        assert row["invocations"].get("s0_ideas") == 1, row["invocations"]
        assert row["invocations"].get("s6_package") == 1, row["invocations"]


# --------------------------------------------------------------------------- #
# 6. THE TWO-CHILD BATCH — the contract's own acceptance
# --------------------------------------------------------------------------- #


@pytest.fixture
def two_child_batch(make_cfg, monkeypatch):
    """One armed 2-slot batch, driven to completion by two in-process children."""
    cfg, path = make_cfg("p5-duo", size=2, workers=2, parallel=True)
    journal = _Journal()
    runners = fake_runners(journal, lockstep=_Lockstep(2), green_fail_once=True)
    started: list[str] = []
    monkeypatch.setattr(orch, "spawn_slot", in_process_seam(cfg, runners, started=started))
    report = orch.run_batch(cfg, runners=runners, config_path=path)
    return cfg, report, journal, started


def test_two_children_drive_one_ledger_to_two_packaged_games(two_child_batch):
    _cfg, report, _journal, started = two_child_batch
    assert sorted(started) == ["p5-duo-s001", "p5-duo-s002"]
    assert [row["state"] for row in report["slots"]] == ["packaged", "packaged"]
    assert report["status"] == "complete" and report["exit_code"] == 0
    assert report["parallel"] == {
        "workers": 2,
        "children": [{"slug": "p5-duo-s001", "exit_code": 0, "error": None},
                     {"slug": "p5-duo-s002", "exit_code": 0, "error": None}],
    }


def test_the_interleaved_ledger_replays_clean_and_is_really_interleaved(two_child_batch):
    cfg, _report, _journal, _started = two_child_batch
    lines = _ledger_lines(cfg)
    table = orch.replay_ledger(Path(orch.batch_dir(cfg)) / orch.LEDGER_NAME)
    assert {slug: entry["state"] for slug, entry in table.items()} == {
        "p5-duo-s001": "packaged", "p5-duo-s002": "packaged"}

    # The parent's two S0 lines come first, in slot order; everything after them
    # is a child's, and the two children must have written into each other.
    assert [row["slug"] for row in lines[:2]] == ["p5-duo-s001", "p5-duo-s002"]
    child_slugs = [row["slug"] for row in lines[2:]]
    switches = sum(1 for before, after in pairwise(child_slugs) if before != after)
    assert switches >= 2, (
        "the two children's lines never interleaved, so this ledger proves nothing about "
        f"concurrency: {child_slugs}"
    )


def test_each_child_wrote_only_its_own_slugs_lines(two_child_batch):
    cfg, _report, journal, _started = two_child_batch
    # Every stage call is attributable to its own slot, and each slug's walk is
    # the whole §4 ladder exactly once (bar the scripted green-loop retry).
    for slug in ("p5-duo-s001", "p5-duo-s002"):
        stages = journal.stages(slug)
        assert stages == ["s0_ideas", "s1_spec", "s2_implement", "s2_implement",
                          "s3_verify", "s3_gate", "s4_baselines", "s5_battery",
                          "s6_package"], stages
    edges = {(row["slug"], row["from"], row["to"]) for row in _ledger_lines(cfg)}
    assert ("p5-duo-s001", "reviewed", "packaged") in edges
    assert ("p5-duo-s002", "reviewed", "packaged") in edges


def test_the_merged_report_carries_the_in_memory_only_fields_from_the_sidecars(
    two_child_batch
):
    """Contract P-5 §5: off-ledger spend, invocations and the re-spec counter.

    These exist ONLY in a child's memory — no §4 edge can carry them — so a
    merge that forgot the sidecars would silently under-report the batch's real
    spend, which is the defect the sidecar exists to prevent.
    """
    cfg, report, _journal, _started = two_child_batch
    bdir = Path(orch.batch_dir(cfg))
    for slug in ("p5-duo-s001", "p5-duo-s002"):
        assert orch.slot_report_path(bdir, slug).is_file()

    for row in report["slots"]:
        assert row["off_ledger_cost"] == {"usd": 0.25, "tokens_in": 10,
                                          "tokens_out": 1, "runs": 1}, row
        assert row["green_failures"] == 1, row
        assert row["blocked"] is None and row["review_pending"] is False
    off = report["cost"]["off_ledger"]
    assert off["runs"] == 2 and off["usd"] == pytest.approx(0.5), off
    assert report["cost"]["total"]["usd"] == pytest.approx(0.5 * 16), report["cost"]["total"]


def test_a_slot_with_no_sidecar_falls_back_to_the_ledger_row(two_child_batch, make_cfg):
    """A child that died before writing one: the row stands, the fields are empty."""
    cfg, _report, _journal, _started = two_child_batch
    bdir = Path(orch.batch_dir(cfg))
    orch.slot_report_path(bdir, "p5-duo-s002").unlink()
    slots = orch._slots(cfg, orch.batch_config(cfg),
                        orch.replay_ledger(bdir / orch.LEDGER_NAME))
    orch._merge_sidecars(slots, bdir)
    by_slug = {slot.slug: slot for slot in slots}
    assert by_slug["p5-duo-s001"].offledger_cost["runs"] == 1
    assert by_slug["p5-duo-s002"].offledger_cost["runs"] == 0, (
        "no sidecar means the ledger-derived row, exactly as today's resume reports it"
    )
    assert by_slug["p5-duo-s002"].state == "packaged", "the ledger state still stands"


# --------------------------------------------------------------------------- #
# 7. never-kill
# --------------------------------------------------------------------------- #


def test_one_childs_failure_never_destroys_its_siblings_work(make_cfg, monkeypatch):
    """Operator ruling at process scale (contract P-5 §4)."""
    cfg, path = make_cfg("p5-nokill", size=2, workers=2, parallel=True)
    journal = _Journal()
    runners = fake_runners(journal)
    started: list[str] = []
    monkeypatch.setattr(orch, "spawn_slot", in_process_seam(
        cfg, runners, started=started, fail={"p5-nokill-s001"}))
    report = orch.run_batch(cfg, runners=runners, config_path=path)

    assert sorted(started) == ["p5-nokill-s001", "p5-nokill-s002"], (
        "a failing child must not stop its sibling from being started"
    )
    states = {row["slug"]: row["state"] for row in report["slots"]}
    assert states["p5-nokill-s002"] == "packaged", "the sibling must finish"
    assert states["p5-nokill-s001"] == "ideated", (
        "the failed slot keeps the ledger state the parent's S0 left it at"
    )
    rows = {row["slug"]: row for row in report["parallel"]["children"]}
    assert rows["p5-nokill-s001"]["exit_code"] is None
    assert "injected child failure" in rows["p5-nokill-s001"]["error"]
    assert rows["p5-nokill-s002"]["exit_code"] == 0
    assert report["exit_code"] == 2 and report["status"] == "stopped"
    # And a resume re-runs exactly it: the sibling's artifacts are untouched.
    monkeypatch.setattr(orch, "spawn_slot", in_process_seam(cfg, runners, started=[]))
    resumed = orch.run_batch(cfg, runners=runners, config_path=path)
    assert [row["state"] for row in resumed["slots"]] == ["packaged", "packaged"]
    assert resumed["exit_code"] == 0


# --------------------------------------------------------------------------- #
# 8. the seam itself
# --------------------------------------------------------------------------- #


def test_the_default_seam_is_loud_when_it_has_no_config_path(tmp_path):
    """A real subprocess needs a PATH; misuse says which three ways out there are."""
    with pytest.raises(ValueError, match="needs the config PATH"):
        orch.spawn_slot(config_path=None, slug="b-s001", batch_dir=tmp_path)


def test_the_default_seam_builds_the_documented_argv(tmp_path, monkeypatch):
    """Contract P-5 §6's command line, verbatim, with the child's own log file."""
    captured: dict = {}

    class _Fake:
        def wait(self):
            return 0

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["stdout"] = kwargs["stdout"]
        captured["stderr"] = kwargs["stderr"]
        return _Fake()

    monkeypatch.setattr(orch.subprocess, "Popen", fake_popen)
    assert orch.spawn_slot(config_path="config/x.yaml", slug="b-s001",
                           batch_dir=tmp_path) == 0
    import sys as _sys
    assert captured["argv"] == [_sys.executable, "-m", "gen.orchestrator",
                                "--config", "config/x.yaml", "--slot", "b-s001"]
    assert captured["stderr"] is orch.subprocess.STDOUT
    assert Path(captured["stdout"].name) == orch.slot_log_path(tmp_path, "b-s001")


# --------------------------------------------------------------------------- #
# 9. the two write-atomicity fixes
# --------------------------------------------------------------------------- #


def test_the_spec_dir_idea_copy_is_written_through_a_rename(tmp_path, monkeypatch):
    """Contract P-5 §7: `_discover_spec_dir` must never read half an idea.json."""
    target = tmp_path / "idea.json"
    seen: list[tuple[str, bool]] = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append((Path(dst).name, Path(dst).exists()))
        return real_replace(src, dst)

    monkeypatch.setattr(s1_spec.os, "replace", spy)
    s1_spec._write_bytes_atomic(target, b'{"id": "x"}\n')

    assert target.read_bytes() == b'{"id": "x"}\n'
    assert seen == [("idea.json", False)], (
        "the target must appear only as the destination of a rename, never be written "
        f"into directly: {seen}"
    )


def test_run_s1_writes_the_idea_copy_atomically():
    """The fix has to be AT the write site, not merely available beside it."""
    source = inspect.getsource(s1_spec.run_s1)
    assert '_write_bytes_atomic(out_dir / "idea.json"' in source, (
        "contract P-5 §7: S1's spec-dir idea.json copy is the file the orchestrator's "
        "`_discover_spec_dir` bare-json.loads()es out of a SHARED directory"
    )
    assert '(out_dir / "idea.json").write_bytes' not in source


def test_two_writer_scratches_in_one_second_are_different_directories(tmp_path,
                                                                     monkeypatch):
    """Contract P-5 §8: the stamp is a SECOND, so it cannot be the whole name."""
    from gen import backends

    class _Driver:
        name = "localclaude"

        def session(self, prompt, **kwargs):
            Path(kwargs["cwd"]).mkdir(parents=True, exist_ok=True)
            (Path(kwargs["cwd"]) / "spec.md").write_text("# fake\n", encoding="utf-8")
            (Path(kwargs["cwd"]) / "spec.yaml").write_text("title: fake\n", encoding="utf-8")
            scratches.append(Path(kwargs["cwd"]))
            return {"session_id": "s", "usd_cost": 0.0, "tokens_in": 0,
                    "tokens_out": 0, "duration_s": 0.0}

    scratches: list[Path] = []
    monkeypatch.setattr(backends, "get_driver", lambda cfg, role=None: (_Driver(), "m"))
    monkeypatch.setattr(s1_spec, "S1_SCRATCH_ROOT", tmp_path / "tmp")

    class _FrozenClock:
        @staticmethod
        def now(tz=None):
            from datetime import datetime as _dt
            return _dt(2026, 9, 30, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(s1_spec, "datetime", _FrozenClock)
    runner = s1_spec._default_writer_runner({})
    runner("WRITE ONE")
    runner("WRITE TWO")

    assert len(scratches) == 2 and scratches[0] != scratches[1], (
        f"two writers in the same wall-clock second shared a directory: {scratches}"
    )
    assert all(path.is_dir() for path in scratches)


def test_a_colliding_writer_scratch_now_fails_loudly(tmp_path, monkeypatch):
    """`exist_ok` is gone: sharing a scratch silently is what corrupted specs."""
    from gen import backends

    class _Driver:
        name = "localclaude"

        def session(self, prompt, **kwargs):  # pragma: no cover - never reached
            raise AssertionError("the collision must raise before any session starts")

    monkeypatch.setattr(backends, "get_driver", lambda cfg, role=None: (_Driver(), "m"))
    monkeypatch.setattr(s1_spec, "S1_SCRATCH_ROOT", tmp_path / "tmp")
    runner = s1_spec._default_writer_runner({})
    real_mkdir = Path.mkdir

    def taken(self, *args, **kwargs):
        if self.name.startswith("s1-writer-"):
            real_mkdir(self, parents=True, exist_ok=True)
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", taken)
    with pytest.raises(FileExistsError):
        runner("WRITE")


# --------------------------------------------------------------------------- #
# 10. the S0 draw lock (contract P-5 addendum 1)
# --------------------------------------------------------------------------- #
#
# THE HOLE THE PRE-PASS DOES NOT COVER. `_force_s0` takes the FIRST draw out of
# the race, but a slot that lint-kills mid-wave re-samples INSIDE its own child
# (`respec --> ideated`), and b002 respec'd three times per slot — so two
# children drawing at once is a production event. ONE exclusive flock held
# across the WHOLE `sample_batch` call is the fix, and it covers the pre-pass
# and every re-draw from the one site.


def _prose(_prompt: str) -> str:
    """Prose the S0 validator accepts, drawn from nothing and costing nothing."""
    body = (
        "The player walks a narrow yard between two gates. One gate opens when the "
        "marker beside it is carried onto the pale tile, and the other stays shut "
        "until the first has opened and the marker has been set down again. Walls "
        "close the yard on every side, so the only route is the one the gates "
        "allow, and a marker left on the wrong tile has to be carried back before "
        "anything moves. Each level widens the yard and moves the pale tile, so the "
        "same rule has to be read again on a board that looks new. Nothing in the "
        "yard is hidden from view and nothing is lost by trying a tile twice. "
    )
    return f"Quiet Gate Yard\n{body}"


def _slot_for(index: int, slug: str):
    return orch._Slot(slug=slug, index=index, state=None, history=[],
                      rejects=orch._empty_rejects(), cost=orch._empty_cost())


def _s0_ctx(cfg, batch_id: str, index: int):
    return orch._context(cfg, _slot_for(index, f"{batch_id}-s{index:03d}"),
                         batch_id=batch_id, stage="s0_ideas", bdir=orch.batch_dir(cfg))


@pytest.fixture
def real_s0(make_cfg, monkeypatch):
    """The REAL `default_runners()['s0_ideas']`, aimed entirely at tmp.

    Three module constants `batch_home` cannot reach have to move together or
    the draw writes into the repo: `s0_ideas.IDEAS_ROOT` (which the runner
    itself asserts equal to the orchestrator's), the dedupe history path, and
    the prose runner, which is the only part of S0 that would otherwise dial a
    driver — one completion per idea, so the draw is neither local nor free.
    """

    def _make(batch_id: str, *, size: int = 2):
        cfg, path = make_cfg(batch_id, size=size)
        monkeypatch.setattr(s0_ideas, "IDEAS_ROOT", orch.IDEAS_ROOT)
        monkeypatch.setattr(s0_ideas, "DEDUPE_HISTORY_PATH",
                            orch.IDEAS_ROOT / "dedupe-history.jsonl")
        monkeypatch.setattr(s0_ideas, "_default_prose_runner", lambda cfg_: _prose)
        return cfg, path

    return _make


def test_the_lock_lives_beside_the_ideas_it_guards(batch_home):
    """One per batch, dot-prefixed, inside the directory the draw writes into."""
    path = orch.s0_draw_lock_path("p5-lockpath")
    assert path == orch.IDEAS_ROOT / "p5-lockpath" / orch.S0_DRAW_LOCK_NAME
    assert path.name.startswith("."), "the lock must not look like an idea file"
    assert not path.name.startswith("idea-")


def test_the_whole_sample_batch_call_runs_under_an_exclusive_flock(real_s0, monkeypatch):
    """Contract P-5 addendum 1: the lock is TAKEN, and taken BEFORE the draw."""
    import fcntl

    cfg, _path = real_s0("p5-lockobs", size=2)
    events: list[tuple] = []
    real_flock = fcntl.flock
    real_sample = s0_ideas.sample_batch

    def flock_spy(fileno, operation):
        events.append(("flock", operation))
        return real_flock(fileno, operation)

    def sample_spy(*args, **kwargs):
        events.append(("sample_batch", kwargs.get("batch_id")))
        try:
            return real_sample(*args, **kwargs)
        finally:
            events.append(("sample_batch-done", kwargs.get("batch_id")))

    monkeypatch.setattr(orch.fcntl, "flock", flock_spy)
    monkeypatch.setattr(s0_ideas, "sample_batch", sample_spy)

    orch.default_runners()["s0_ideas"](_s0_ctx(cfg, "p5-lockobs", 1))

    kinds = [kind for kind, _ in events]
    assert "sample_batch" in kinds, f"the draw never ran: {events}"
    start = kinds.index("sample_batch")
    assert start > 0 and events[start - 1] == ("flock", fcntl.LOCK_EX), (
        "the exclusive lock must be taken immediately BEFORE `sample_batch`, not "
        f"around some inner part of it: {events}"
    )
    assert orch.s0_draw_lock_path("p5-lockobs").is_file(), "the lock file was never created"
    assert (orch.IDEAS_ROOT / "p5-lockobs" / "idea-001.json").is_file()


def test_two_concurrent_drawers_never_overlap(real_s0, monkeypatch):
    """Two 'processes' — two independent runner tables — take turns, not halves.

    flock is held on the open file DESCRIPTION, so two separate `open()` calls
    conflict even inside one interpreter; that is what makes this measurable
    in-process and what makes it true across the real children.
    """
    cfg, _path = real_s0("p5-lockrace", size=2)
    order: list[str] = []
    guard = threading.Lock()
    real_sample = s0_ideas.sample_batch

    def slow_sample(*args, **kwargs):
        with guard:
            order.append("enter")
        time.sleep(0.05)   # long enough that an unlocked second drawer would land inside
        try:
            return real_sample(*args, **kwargs)
        finally:
            with guard:
                order.append("exit")

    monkeypatch.setattr(s0_ideas, "sample_batch", slow_sample)

    def draw(index: int) -> None:
        # A FRESH runner table per thread: the per-run memo is what a second
        # PROCESS would not have, and the lock is the only thing left holding
        # them apart.
        orch.default_runners()["s0_ideas"](_s0_ctx(cfg, "p5-lockrace", index))

    threads = [threading.Thread(target=draw, args=(index,)) for index in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads), "a drawer deadlocked on the lock"

    assert order == ["enter", "exit", "enter", "exit"], (
        f"the two draws interleaved, so the lock is not held across the call: {order}"
    )


def test_the_second_drawer_keeps_the_firsts_ideas_and_adds_no_history(real_s0):
    """Serialization restores the SEQUENTIAL semantics, which is the whole point.

    Unserialized, both drawers read an empty directory, both draw, both write
    every idea file (non-atomically, so a sibling can read half of one) and both
    append the full dedupe history. Serialized, the second finds the first's
    files on disk, keeps them byte-for-byte, and appends nothing.
    """
    cfg, _path = real_s0("p5-lockseq", size=2)
    ideas_dir = orch.IDEAS_ROOT / "p5-lockseq"
    history = s0_ideas.DEDUPE_HISTORY_PATH

    orch.default_runners()["s0_ideas"](_s0_ctx(cfg, "p5-lockseq", 1))
    first = {path.name: path.read_bytes() for path in sorted(ideas_dir.glob("idea-*.json"))}
    rows_after_first = history.read_text(encoding="utf-8").splitlines()

    orch.default_runners()["s0_ideas"](_s0_ctx(cfg, "p5-lockseq", 2))
    second = {path.name: path.read_bytes() for path in sorted(ideas_dir.glob("idea-*.json"))}

    assert list(first) == ["idea-001.json", "idea-002.json"]
    assert second == first, "the second drawer rewrote the first's idea files"
    assert history.read_text(encoding="utf-8").splitlines() == rows_after_first, (
        "the second drawer appended to the dedupe history again"
    )
    keys = [json.loads(row)["key"] for row in rows_after_first]
    assert len(keys) == len(set(keys)) == 2, f"one history row per idea, once: {keys}"


def test_the_same_holds_when_the_two_drawers_are_really_concurrent(real_s0, monkeypatch):
    """The test above's invariants, with the two draws genuinely overlapping.

    The window is widened from INSIDE the draw (the prose runner, which S0 calls
    once per idea) and never around `sample_batch`, because a barrier there would
    deadlock against the very lock this is measuring. The second drawer is on the
    lock before the first has written a byte.
    """
    cfg, _path = real_s0("p5-lockonce", size=2)
    drawing = threading.Event()

    def slow_prose(prompt: str) -> str:
        drawing.set()
        time.sleep(0.05)
        return _prose(prompt)

    monkeypatch.setattr(s0_ideas, "_default_prose_runner", lambda cfg_: slow_prose)
    errors: list[BaseException] = []

    def draw(index: int) -> None:
        try:
            orch.default_runners()["s0_ideas"](_s0_ctx(cfg, "p5-lockonce", index))
        except BaseException as exc:      # noqa: BLE001 - reported, never swallowed
            errors.append(exc)

    first = threading.Thread(target=draw, args=(1,))
    first.start()
    assert drawing.wait(timeout=30), "the first drawer never entered the draw"
    second = threading.Thread(target=draw, args=(2,))
    second.start()
    for thread in (first, second):
        thread.join(timeout=60)
    assert not errors, f"a concurrent drawer raised: {errors}"
    assert not (first.is_alive() or second.is_alive()), "a drawer deadlocked"

    ideas = sorted((orch.IDEAS_ROOT / "p5-lockonce").glob("idea-*.json"))
    assert [path.name for path in ideas] == ["idea-001.json", "idea-002.json"]
    ids = [json.loads(path.read_text(encoding="utf-8"))["id"] for path in ideas]
    assert ids == ["p5-lockonce-i001", "p5-lockonce-i002"], ids
    rows = s0_ideas.DEDUPE_HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2, (
        "each idea belongs in the dedupe history ONCE — two drawers that both "
        f"wrote would put it there twice: {rows}"
    )
