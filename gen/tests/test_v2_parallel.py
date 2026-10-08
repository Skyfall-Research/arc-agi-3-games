"""Contract P-5 (parallel slots) — the BLIND lane.

Run: .venv/bin/python -m pytest gen/tests/test_v2_parallel.py -q

WRITTEN FROM `docs/v2/contracts/P-5-parallel-slots.md` AND ITS TWO ADDENDA,
never from the implementer's own test file (`gen/tests/test_p5_parallel.py` was
not opened) and never from the implementer's handback (not read). The
implementation modules WERE read, but for ONE purpose only: to discover the
NAMES and CALL SHAPES of the surfaces the contract promises (the spawn seam,
the sidecar, `--slot`, the arming keys, the draw lock) so this file can aim its
calls at them. Every EXPECTATION below traces to a sentence of the contract,
and every assertion message cites the section it is pinning.

WHAT IS PINNED (the contract's "Blind lane", B1-B7, plus the addenda):

  B1  a hermetic two-child armed batch through an injected in-process spawn
      seam against ONE ledger — interleaved replay clean, per-slug write
      isolation, and a merged report carrying the in-memory-only fields off the
      sidecars with the off-ledger dollars in the total.
  B2  the flock is actually taken inside `_append_lines`, and a call's lines
      stay adjacent (the §3 two-line pairs).
  B3  `--slot` isolation and its loud refusals.
  B4  byte-identity at both layers: CLI `--workers 1` == no flag, and an
      UNARMED `run_batch` never touches a booby-trapped seam and gains no
      `parallel` report key.
  B5  parent-forced S0: every idea on disk before any child starts, children
      draw nothing, and the dedupe history is appended exactly once.
  B6  two same-second S1 writer scratches are distinct, and a collision is
      loud instead of shared.
  B7  never-kill: one failing child, the sibling completes, both reported,
      nothing destroyed.
  A1/A2  the `sample_batch` draw lock is held across the WHOLE call.

CORRECTED CLAIMS, pinned as CORRECTED (never as the contract first wrote them):

  * Addendum 1: the contract twice called the S0 draw "local + free / zero
    spend". It is NOT free — `sample_idea` makes one `spec_writer` completion
    per idea. Nothing here asserts the draw is free; the parent pre-pass is
    pinned on its ORDERING guarantee ("every idea file exists on disk first"),
    which is the design's actual promise.
  * Addendum 2: the serialization mechanism is NOT "the second drawer's dedupe
    window sees the first's keys" (within one batch `load_recent_keys` excludes
    the batch itself). The pinned guarantee is the corrected one: the second
    drawer finds the first's ideas on disk and KEEPS them, and the history is
    appended EXACTLY once.
  * Addendum 2's two RESIDUALS (a hand-run `python -m gen.s0_ideas` during a
    live batch; two DIFFERENT batches racing on the shared dedupe history) are
    out of scope by the addendum's own words and are deliberately NOT pinned.

HERMETICITY. Every test runs under `batch_home`, which rebinds every
REPO_ROOT-rooted `Path` constant on `gen.orchestrator`, `gen.s0_ideas` AND
`gen.s1_spec` (the ideas root, the corpus root, the batches root, the dedupe
history and the S1 scratch root all live on different modules) into `tmp_path`,
plus `gen.config.REPO_ROOT`. An autouse guard fails any test that changes the
repo's own `out/`, `config/`, `games/` or `canon/` trees. A second autouse
guard forbids `urlopen`, `socket.create_connection` and
`gen.backends.get_driver`, so nothing here can dial out or start a session.

IN-PROCESS CHILDREN, DELIBERATELY. The contract's B-lane says to stay
in-process "UNLESS the child is `sys.executable -m gen.orchestrator` against a
tmp tree with fake-runner injection impossible — in that case stay in-process
via the seam (the seam exists for exactly this)". Fake-runner injection into a
real subprocess IS impossible here (a child re-imports `gen.orchestrator` fresh
and would call `default_runners()`, i.e. real drivers and real spend), so every
"child" below is an in-process substitution through the seam that drives the
SAME `run_slot` code path against the SAME ledger file. §6's real-subprocess
default is pinned separately, by observing the argv it would launch with
`subprocess.Popen` stubbed — no process is ever started.

POST-WAVE FIXTURE EDIT (contract H-1 item 6, 2026-10-06, licensed; the only
edit made to this file after the P-5 blind lane closed). The fake runners now
land their artifacts through `_rig_write` (write-then-rename) instead of
`Path.write_text`. Fixture code only — no assertion was touched. See
`_rig_write` for the measured race it closes: the two thread-children shared one
corpus dir, and `_discover_spec_dir` could read a sibling's truncated
`idea.json`, killing a child and leaving its sidecar unwritten.
"""

from __future__ import annotations

import fcntl
import importlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import types
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from gen import cli, s0_ideas, s1_spec
from gen import orchestrator as orch
from gen.config import REPO_ROOT, load_config

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #

#: The repo trees the hard rules put off limits ("Never edit stage artifacts
#: under out/"; template.yaml read-only; the blind lane touches only its file).
GUARDED = ("out", "config", "games", "canon")

#: The vendored canon (P-2), used as `duckwm_docs` by the one test that needs a
#: real `load_config`-able config. READ-ONLY, and the repo guard proves it.
CANON_DIR = REPO_ROOT / "canon"
TEMPLATE_PATH = REPO_ROOT / "config" / "template.yaml"

#: A prose body that satisfies S0's coherence gate (>= 400 chars, no narration).
#: Only the one test that drives the REAL sampler uses it; it never reaches a
#: driver — it is handed in through `sample_batch(prose_runner=...)`.
PROSE_REPLY = (
    "Blind Lane Probe\n"
    "A compact test arena where a lone selector sweeps across a five by five "
    "board of tiles. Some tiles hide a target glyph, and clicking a tile "
    "reveals it, while blocked cells force the sweep into detours that cost "
    "extra moves. The player must cover every target pad before the sweep "
    "counter runs out, learning board by board which routes waste turns. "
    "Later boards add a second glyph colour and a locked row that opens only "
    "when the first colour is fully covered, so plans must interleave the two "
    "colours without stranding the selector behind its own reveals."
)

#: The §2 artifacts a fake stage must land so the resume hash chain and
#: `_discover_spec_dir` stay live. Relative to the slot's corpus (spec) dir.
FAKE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "implemented": ("worker/game.py", "worker/solver.py"),
    "verified": ("worker.verifier-report.json",),
    "baselined": ("worker.s4/metadata.json",),
}

GATE_TIMEOUT_S = 30.0


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _shape(root: Path) -> dict[str, object] | None:
    """`{relative path: <dir> | size}` — the cheap repo-guard snapshot."""
    root = Path(root)
    if not root.exists():
        return None
    return {
        str(path.relative_to(root)): "<dir>" if path.is_dir() else path.stat().st_size
        for path in sorted(root.rglob("*"))
        if "__pycache__" not in path.parts
    }


def _ledger_lines(bdir: Path) -> list[dict]:
    path = Path(bdir) / orch.LEDGER_NAME
    if not path.is_file():
        return []
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines() if raw.strip()]


def _row(report: Mapping, slug: str) -> dict:
    rows = [row for row in report["slots"] if row["slug"] == slug]
    assert len(rows) == 1, (
        f"P-5 §5: the merged report must carry exactly one row per slot; "
        f"{slug} appears {len(rows)} time(s)"
    )
    return rows[0]


class _Turnstile:
    """Force child ledger appends to ALTERNATE, so B1's interleaving is a fact.

    Without it "the ledger is interleaved" is a race, and a test that only
    sometimes exercises the thing it claims to pin is not a pin. Each child
    takes its turn immediately before its append and gives it up immediately
    after; a child that has finished retires and stops being dealt in.
    """

    def __init__(self, order):
        self._active = list(order)
        self._turn = self._active[0] if self._active else None
        self._cv = threading.Condition()

    def _advance(self) -> None:
        if not self._active:
            self._turn = None
        elif self._turn in self._active:
            index = (self._active.index(self._turn) + 1) % len(self._active)
            self._turn = self._active[index]
        else:
            self._turn = self._active[0]

    def take(self, who: str | None) -> None:
        if who is None:
            return
        deadline = time.monotonic() + GATE_TIMEOUT_S
        with self._cv:
            while who in self._active and self._turn != who:
                left = deadline - time.monotonic()
                if left <= 0 or not self._cv.wait(left):
                    raise AssertionError(
                        f"the blind lane's append turnstile deadlocked waiting for {who} "
                        f"(turn={self._turn}, active={self._active}) — the test harness, "
                        "not the contract"
                    )

    def give(self, who: str | None) -> None:
        if who is None:
            return
        with self._cv:
            if self._turn == who:
                self._advance()
            self._cv.notify_all()

    def retire(self, who: str | None) -> None:
        if who is None:
            return
        with self._cv:
            if who in self._active:
                self._active.remove(who)
            if self._turn == who:
                self._turn = self._active[0] if self._active else None
            self._cv.notify_all()


class _Journal:
    """What the parent did, what each child did, and who wrote each ledger line."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.calls: list[tuple] = []       # (writer, slug, stage, to_state)
        self.appends: list[tuple] = []     # (writer, slug) in ledger-file order
        self.spawns: list[dict] = []       # one row per seam call
        self._local = threading.local()

    @property
    def writer(self) -> str | None:
        """The slug of the in-process child running on THIS thread (None = parent)."""
        return getattr(self._local, "child", None)

    @writer.setter
    def writer(self, value: str | None) -> None:
        self._local.child = value

    def record_call(self, slug: str, stage: str, to_state: str) -> None:
        with self.lock:
            self.calls.append((self.writer, slug, stage, to_state))

    def stages_by(self, writer: str | None) -> list[tuple[str, str]]:
        with self.lock:
            return [(slug, stage) for who, slug, stage, _ in self.calls if who == writer]

    def child_appends(self) -> list[tuple]:
        with self.lock:
            return [row for row in self.appends if row[0] is not None]


def _rig_write(path: Path, text: str) -> None:
    """Land a fake artifact with WRITE-THEN-RENAME, the production idiom.

    POST-WAVE LICENSED FIXTURE EDIT, 2026-10-06 (contract H-1 item 6). Fixture
    code only: no assertion in this file changed, and none changed meaning.

    THE FLAKE, measured. `test_b4b_the_armed_report_adds_the_parallel_key_and_
    nothing_else` (and any B1/B5 pin reading a child's sidecar) failed about one
    run in fifteen, in isolation and under the full suite alike, with
    `[b11] <slug>-s002 exited None (JSONDecodeError: Expecting value: line 1
    column 1 (char 0))` — a child that died, wrote no sidecar, and left the
    batch `stopped`. The mechanism: every `_context()` runs
    `orchestrator._discover_spec_dir`, which `json.loads` EVERY sibling corpus
    dir's `idea.json`. Production writes that copy with write-then-rename
    (`orchestrator._write_json_atomic`, whose docstring names this exact
    reader), but these fakes wrote it with a plain `Path.write_text`, which
    TRUNCATES before it writes — and the in-process seam runs both children as
    threads over one corpus dir, so one child's `_context` could read the
    other's file in that empty instant. A two-thread drive of exactly that pair
    tore 5262 of 12059 reads with `write_text` and 0 of 12750 with
    write-then-rename.

    So the rig now writes the way production writes, and the read can only ever
    see a whole file — the old bytes or the new ones. No sleep, no poll, no
    retry. The temp name is keyed on the THREAD, not the pid, because this rig's
    "processes" are threads of one pid.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.rig-tmp-{threading.get_ident()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class _Fakes(dict):
    """Fake stage runners: they land the §2 artifacts and report a §4 verdict.

    `script` maps `(slug, stage)` to a queue of scripted FAILURES; each call
    consumes one, and a stage with an empty queue succeeds. Nothing here calls a
    driver, opens a socket or imports arcengine.
    """

    def __init__(self, cfg: Mapping, journal: _Journal, *, script: Mapping | None = None) -> None:
        super().__init__()
        self.cfg = cfg
        self.journal = journal
        self.script = {key: list(value) for key, value in (script or {}).items()}
        for stage in orch.STAGES:
            self[stage] = self._make(stage)

    def _make(self, stage: str):
        def runner(ctx) -> dict:
            self.journal.record_call(ctx.slug, stage, orch.STAGE_SUCCESS[stage])
            queued = self.script.get((ctx.slug, stage))
            if queued:
                return queued.pop(0)
            # H-1 item 6: every fake artifact lands through `_rig_write`
            # (write-then-rename) — see its docstring for the measured race.
            if stage == "s0_ideas":
                _rig_write(
                    ctx.idea_path,
                    json.dumps({"id": f"idea-{ctx.slug}", "slug": ctx.slug}) + "\n",
                )
                return _ok("ideated", f"fake S0 draw for {ctx.slug}", cost=None)
            if stage == "s1_spec":
                out = orch.CORPUS_ROOT / ctx.batch_id / f"{ctx.slug}-game"
                _rig_write(out / "idea.json", ctx.idea_path.read_text(encoding="utf-8"))
                _rig_write(out / "spec.yaml", f"slug: {ctx.slug}\n")
                _rig_write(out / "spec.md", f"# {ctx.slug}\n")
                return _ok("spec_ok", "fake S1 lint pass", cost=None)
            to_state = orch.STAGE_SUCCESS[stage]
            for rel in FAKE_ARTIFACTS.get(to_state, ()):
                _rig_write(ctx.spec_dir / rel, f"{to_state} {ctx.slug}\n")
            return _ok(to_state, f"fake {stage}", cost=_cost(0.01))

        return runner


def _ok(to_state: str, reason: str, *, cost: dict | None) -> dict:
    return {"ok": True, "to_state": to_state, "reason": reason, "cost": cost}


def _fail(to_state: str, reason: str, *, cost: dict | None) -> dict:
    return {"ok": False, "to_state": to_state, "reason": reason, "cost": cost}


def _cost(usd: float) -> dict:
    return {"usd": usd, "tokens_in": 100, "tokens_out": 10}


def _cfg(batch_id: str, *, size: int, armed: bool, workers: int = 2,
         wave_size: int = 8, auto_accept: bool | None = None) -> dict:
    cfg: dict = {
        "batch": {"id": batch_id, "size": size, "seed": 4242},
        "orchestrator": {"workers": workers, "wave_size": wave_size, "max_attrition": 0.9},
    }
    if armed:
        cfg["orchestrator"]["parallel_slots"] = True
    if auto_accept is not None:
        cfg["review"] = {"auto_accept": auto_accept}
    return cfg


def _slugs(cfg: Mapping) -> list[str]:
    return [orch.slot_id(cfg["batch"]["id"], i) for i in range(1, cfg["batch"]["size"] + 1)]


def _install_recording_ledger(monkeypatch, journal: _Journal, turnstile=None) -> None:
    """Record WHO appended each ledger line, in file order.

    The journal lock is held across the real append so the recorded order IS the
    file order. That serialization is the harness's, not the contract's — B2
    exercises the real `_append_lines` with no wrapper at all.
    """
    real = orch._append_lines

    def wrapper(ledger_path, lines):
        writer = journal.writer
        if turnstile is not None:
            turnstile.take(writer)
        try:
            with journal.lock:
                written = real(ledger_path, lines)
                journal.appends.extend((writer, line["slug"]) for line in written)
            return written
        finally:
            if turnstile is not None:
                turnstile.give(writer)

    monkeypatch.setattr(orch, "_append_lines", wrapper)


def _install_inprocess_seam(monkeypatch, cfg: Mapping, runners: Mapping, journal: _Journal,
                            *, turnstile=None, behaviour: Mapping | None = None):
    """Substitute an in-process child through the P-5 §6 spawn seam.

    `behaviour[slug]` may be `"raise"` (the launcher blows up before a child
    exists) or an int (the child runs, then reports that exit code).
    """
    if not hasattr(orch, "spawn_slot"):
        pytest.fail(
            "P-5 §6 promises an INJECTABLE child launcher ('a parameter or patchable "
            "module attribute') and the blind lane is told a missing/unusable seam is a "
            "loud finding — gen.orchestrator exposes no `spawn_slot`"
        )
    behaviour = dict(behaviour or {})

    def fake_spawn(*, config_path, slug, batch_dir):
        ideas_root = orch.IDEAS_ROOT / cfg["batch"]["id"]
        with journal.lock:
            journal.spawns.append({
                "slug": slug,
                "config_path": config_path,
                "batch_dir": Path(batch_dir),
                "ideas_on_disk": sorted(p.name for p in ideas_root.glob("idea-*.json")),
                "order": len(journal.spawns),
            })
        how = behaviour.get(slug)
        if how == "raise":
            raise RuntimeError(f"injected launcher failure for {slug}")
        journal.writer = slug
        try:
            report = orch.run_slot(cfg, slug, runners=runners)
            return report["exit_code"] if how is None else int(how)
        finally:
            journal.writer = None
            if turnstile is not None:
                turnstile.retire(slug)

    monkeypatch.setattr(orch, "spawn_slot", fake_spawn)
    return fake_spawn


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _no_network_no_agent(monkeypatch):
    """P-5 §Blind lane: 'no network, no real driver binaries, no real API calls'."""

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "P-5 blind lane: no test here opens a network connection or starts an agent"
        )

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(importlib.import_module("gen.backends"), "get_driver", forbidden)


@pytest.fixture(autouse=True)
def _repo_is_never_the_workspace():
    """P-5 §Hard rules: tmp roots only — the repo's own trees are never written."""
    before = {name: _shape(REPO_ROOT / name) for name in GUARDED}
    yield
    for name in GUARDED:
        assert _shape(REPO_ROOT / name) == before[name], (
            f"P-5 §Hard rules: a blind-lane test wrote into the repo's own {name}/ tree"
        )


@pytest.fixture
def batch_home(tmp_path, monkeypatch) -> Path:
    """Rebind every REPO_ROOT-rooted Path constant into `tmp_path`.

    Across THREE modules on purpose: the batches/corpus/ideas roots and the S0
    draw lock live on `gen.orchestrator`, the dedupe history on `gen.s0_ideas`,
    and the S1 writer scratch root (P-5 §8) on `gen.s1_spec`.
    """
    for module in (orch, s0_ideas, s1_spec):
        for name, value in list(vars(module).items()):
            if name.startswith("__") or not isinstance(value, Path):
                continue
            try:
                relative = value.resolve().relative_to(REPO_ROOT)
            except ValueError:
                continue
            monkeypatch.setattr(module, name, tmp_path / relative)
    monkeypatch.setattr("gen.config.REPO_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def armed_two_child_batch(batch_home, monkeypatch):
    """B1's subject: ONE armed 2-slot batch, two in-process children, one ledger.

    Slot 1 walks to `played` and stops there for a human (`review_pending`, an
    in-memory-only field). Slot 2 burns one green attempt (off-ledger spend, no
    §4 edge) and then hits the driver-outage route (more off-ledger spend, and
    `blocked`). Between them they exercise every in-memory-only field P-5 §2
    names: off_ledger, blocked, review_pending, invocations, green_failures.
    """
    cfg = _cfg("p5blind-b1", size=2, armed=True, workers=2)
    slug_a, slug_b = _slugs(cfg)
    from gen.s2_implement import DRIVER_UNAVAILABLE_REASON

    script = {
        (slug_b, "s2_implement"): [
            _fail("spec_ok", "injected green-loop failure", cost=_cost(0.05)),
            _fail("spec_ok", f"injected outage: {DRIVER_UNAVAILABLE_REASON}", cost=_cost(0.07)),
        ],
    }
    journal = _Journal()
    turnstile = _Turnstile([slug_a, slug_b])
    runners = _Fakes(cfg, journal, script=script)
    _install_recording_ledger(monkeypatch, journal, turnstile)
    _install_inprocess_seam(monkeypatch, cfg, runners, journal, turnstile=turnstile)

    report = orch.run_batch(cfg, runners=runners, config_path=batch_home / "unused.yaml")
    return types.SimpleNamespace(
        cfg=cfg, report=report, journal=journal, slug_a=slug_a, slug_b=slug_b,
        bdir=orch.batch_dir(cfg), home=batch_home,
    )


# --------------------------------------------------------------------------- #
# B1 — a hermetic two-child armed batch against ONE ledger
# --------------------------------------------------------------------------- #


def test_b1_spawn_seam_is_an_injectable_module_attribute(batch_home):
    """P-5 §6: 'the child launcher is injectable … a patchable module attribute'."""
    seam = getattr(orch, "spawn_slot", None)
    assert callable(seam), (
        "P-5 §6: the spawn seam must exist and be callable — 'A missing/unusable seam "
        "is a loud finding (the P-4 precedent)' (§Blind B1)"
    )
    import inspect

    params = inspect.signature(seam).parameters
    for name in ("config_path", "slug", "batch_dir"):
        assert name in params, (
            f"P-5 §6: the seam is documented as taking the config PATH, the slug and the "
            f"batch dir; {name!r} is missing from {sorted(params)}"
        )


def test_b1_two_children_drive_one_ledger_and_it_replays_clean(armed_two_child_batch):
    """P-5 §Blind B1: 'replay_ledger replays the interleaved ledger clean'."""
    run = armed_two_child_batch
    ledger = run.bdir / orch.LEDGER_NAME
    assert ledger.is_file(), "P-5 §4: both children append to the batch's ONE ledger"

    child_lines = run.journal.child_appends()
    writers = [writer for writer, _ in child_lines]
    assert len(set(writers)) == 2, (
        f"P-5 §Blind B1: a two-child batch must have TWO children writing the ledger; "
        f"saw {sorted(set(writers))}"
    )
    interleaved = any(
        writers[i] != writers[j] and writers[j] != writers[k] and writers[i] == writers[k]
        for i in range(len(writers))
        for j in range(i + 1, len(writers))
        for k in range(j + 1, len(writers))
    )
    assert interleaved, (
        f"P-5 §Blind B1 pins the INTERLEAVED ledger; the children's lines arrived in "
        f"blocks, so nothing was interleaved: {writers}"
    )

    table = orch.replay_ledger(ledger)
    assert set(table) == {run.slug_a, run.slug_b}, (
        "P-5 §Evidence: replay_ledger keys per slug and 'interleaved lines from different "
        f"slugs replay clean'; replay gave {sorted(table)}"
    )
    assert table[run.slug_a]["state"] == "played", (
        "P-5 §Blind B1: the interleaved ledger must replay to each slot's true state"
    )
    assert table[run.slug_b]["state"] == "spec_ok", (
        "P-5 §Blind B1: the interleaved ledger must replay to each slot's true state"
    )


def test_b1_each_child_wrote_only_its_own_slugs_lines(armed_two_child_batch):
    """P-5 §2: 'A child writes ledger lines ONLY for its own slug.'"""
    run = armed_two_child_batch
    offenders = [(writer, slug) for writer, slug in run.journal.child_appends() if writer != slug]
    assert not offenders, (
        f"P-5 §2: 'A child writes ledger lines ONLY for its own slug' — these lines were "
        f"written by the wrong child: {offenders}"
    )


def test_b1_merged_report_carries_both_rows_from_the_sidecars(armed_two_child_batch):
    """P-5 §5: the merge overlays 'each slot's sidecar for the in-memory-only fields'."""
    run = armed_two_child_batch
    report = run.report
    assert {row["slug"] for row in report["slots"]} == {run.slug_a, run.slug_b}, (
        "P-5 §Blind B1: 'the merged report.json carries BOTH slots' rows'"
    )

    for slug in (run.slug_a, run.slug_b):
        sidecar = orch.slot_report_path(run.bdir, slug)
        assert sidecar.is_file(), (
            f"P-5 §2: a slot run 'writes a per-slot SIDECAR report under out/batches/<id>/' — "
            f"nothing at {sidecar}"
        )
        assert sidecar.name != orch.BATCH_REPORT_NAME, (
            "P-5 §2: the sidecar is 'your naming; NEVER report.json'"
        )
        carried = json.loads(sidecar.read_text(encoding="utf-8"))["slot"]
        merged = _row(report, slug)
        for field in ("off_ledger_cost", "blocked", "stale", "review_pending",
                      "invocations", "respec_runs_this_run", "green_failures"):
            assert field in carried, (
                f"P-5 §2: the sidecar carries the slot row 'INCLUDING the in-memory-only "
                f"fields'; {field!r} is missing from {sidecar.name}"
            )
        assert merged["blocked"] == carried["blocked"], (
            "P-5 §5: `blocked` exists ONLY in memory (§Evidence) and must reach the merged "
            "report from the sidecar"
        )
        assert merged["review_pending"] == carried["review_pending"], (
            "P-5 §5: `review_pending` exists ONLY in memory and must reach the merged report"
        )
        assert merged["off_ledger_cost"] == carried["off_ledger_cost"], (
            "P-5 §5: off-ledger spend exists ONLY in memory and must reach the merged report"
        )
        for stage, count in (carried["invocations"] or {}).items():
            assert merged["invocations"].get(stage, 0) >= count, (
                f"P-5 §5: the child's `invocations` must survive the merge; {stage} went "
                f"{count} -> {merged['invocations'].get(stage)}"
            )

    assert _row(report, run.slug_a)["review_pending"] is True, (
        "P-5 §Blind B1: the in-memory-only fields must be POPULATED from the sidecars — "
        "slot 1 stopped at `played` for a human and the merged row must say so"
    )
    blocked = _row(report, run.slug_b)["blocked"]
    assert blocked and blocked.get("stage") == "s2_implement", (
        "P-5 §Blind B1 / §Evidence: `blocked` is an in-memory-only diagnostic and a "
        f"ledger-only close would lose it; merged row carries {blocked!r}"
    )


def test_b1_off_ledger_dollars_land_in_the_batch_total(armed_two_child_batch):
    """P-5 §5: 'off_ledger totals sum across sidecars.'"""
    run = armed_two_child_batch
    total = run.report["cost"]["off_ledger"]
    expected = 0.0
    runs = 0
    for slug in (run.slug_a, run.slug_b):
        sidecar = json.loads(
            orch.slot_report_path(run.bdir, slug).read_text(encoding="utf-8")
        )["slot"]["off_ledger_cost"]
        expected += sidecar["usd"] or 0.0
        runs += sidecar["runs"]
    assert runs > 0, (
        "the blind lane's own fixture must actually spend off-ledger money, or this pin "
        "proves nothing (P-5 §Blind B1: 'off_ledger dollars land in the total')"
    )
    assert total["runs"] == runs, (
        f"P-5 §5: 'off_ledger totals sum across sidecars'; runs {total['runs']} != {runs}"
    )
    assert total["usd"] == pytest.approx(expected), (
        f"P-5 §Blind B1: 'off_ledger dollars land in the total'; report says "
        f"{total['usd']}, the sidecars say {expected}"
    )
    assert total["usd"] > 0, (
        "P-5 §Evidence: 'A ledger-only close silently under-reports spend' — the merged "
        "total must carry the children's off-ledger dollars"
    )


def test_b1_armed_report_may_add_only_the_additive_parallel_block(armed_two_child_batch):
    """P-5 §5: 'when armed it MAY add one additive `parallel` block'."""
    run = armed_two_child_batch
    block = run.report.get("parallel")
    assert block is not None, (
        "P-5 §5/§Blind B4: the armed report is the ONLY one that may carry `parallel`; "
        "this armed run carried none, so B4's negative pin would be vacuous"
    )
    assert "workers" in block, "P-5 §5: the `parallel` block records the workers used"
    children = block["children"]
    assert [child["slug"] for child in children] == [run.slug_a, run.slug_b], (
        f"P-5 §5: the `parallel` block carries 'per-child exit codes'; got {children}"
    )
    assert all("exit_code" in child for child in children), (
        "P-5 §5: the `parallel` block carries 'per-child exit codes'"
    )


# --------------------------------------------------------------------------- #
# B2 — the ledger lock
# --------------------------------------------------------------------------- #


def test_b2_append_lines_takes_an_exclusive_flock_before_it_writes(batch_home, monkeypatch):
    """P-5 §3: '_append_lines takes fcntl.flock(LOCK_EX) around open-write-flush-fsync'."""
    ledger = batch_home / "b2" / orch.LEDGER_NAME
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("", encoding="utf-8")

    events: list[tuple] = []
    real_flock = fcntl.flock

    def spy(fd, operation):
        events.append(("flock", operation, ledger.stat().st_size))
        return real_flock(fd, operation)

    monkeypatch.setattr(fcntl, "flock", spy)
    line = orch._line(slug="b2-s001", from_state=None, to_state="ideated", reason="pin",
                      hashes={"spec": None, "game": None, "stage_input": "x"}, cost=None)
    orch._append_lines(ledger, [line])
    monkeypatch.setattr(fcntl, "flock", real_flock)

    exclusive = [event for event in events if event[1] & fcntl.LOCK_EX]
    assert exclusive, (
        f"P-5 §3: `_append_lines` must take fcntl.flock(LOCK_EX); observed flock calls "
        f"{events} (today's evidence says there was 'NO lock')"
    )
    assert exclusive[0][2] == 0, (
        "P-5 §3: the lock is held 'around open-write-flush-fsync' — it was taken only "
        f"AFTER {exclusive[0][2]} byte(s) had already been written"
    )
    assert ledger.read_text(encoding="utf-8").strip(), "the append must actually have landed"

    with ledger.open("a", encoding="utf-8") as probe:
        try:
            real_flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pytest.fail(
                "P-5 §3: the lock is released 'on close' — it was still held after "
                "`_append_lines` returned"
            )
        real_flock(probe.fileno(), fcntl.LOCK_UN)


def test_b2_two_line_pairs_stay_adjacent_under_concurrent_appends(batch_home):
    """P-5 §3: the lock 'keeps the two-line pairs (:2680, :3724) adjacent'.

    MEASUREMENT HONESTY, recorded rather than hidden: this pins the OUTCOME, not
    the mechanism. Between THREADS, a single pre-joined `write` of a small blob
    is already effectively atomic under CPython, so this test stays green with
    the flock removed (measured). Between PROCESSES — which is what P-5 §4
    actually creates — it is the flock that keeps the pair whole, and the
    mechanism is pinned by the test above, which DOES fail with the lock
    removed. A real two-process contention test is the one thing this lane
    could not measure hermetically (see the handback).
    """
    ledger = batch_home / "b2pairs" / orch.LEDGER_NAME
    ledger.parent.mkdir(parents=True, exist_ok=True)
    hashes = {"spec": None, "game": None, "stage_input": "x"}
    pairs = 24
    threads = 4

    def pair(slug: str, index: int) -> list[dict]:
        return [
            orch._line(slug=slug, from_state="baselined", to_state="played",
                       reason=f"battery {index}", hashes=hashes, cost=None),
            orch._line(slug=slug, from_state="played", to_state="implemented",
                       reason=f"crash {index}", hashes=hashes, cost=None),
        ]

    def worker(n: int) -> None:
        slug = f"b2pairs-s{n:03d}"
        for index in range(pairs):
            orch._append_lines(ledger, pair(slug, index))

    workers = [threading.Thread(target=worker, args=(n,)) for n in range(1, threads + 1)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in workers), "a ledger appender hung"

    lines = [json.loads(raw) for raw in ledger.read_text(encoding="utf-8").splitlines() if raw]
    assert len(lines) == pairs * threads * 2, (
        f"P-5 §3: every line of every pair must survive; {len(lines)} of "
        f"{pairs * threads * 2} landed"
    )
    for first, second in zip(lines[0::2], lines[1::2], strict=True):
        assert first["to"] == "played" and second["to"] == "implemented", (
            "P-5 §3: the two-line pair must stay ADJACENT — a pair was split by another "
            f"writer's line ({first['reason']!r} then {second['reason']!r})"
        )
        assert first["slug"] == second["slug"], (
            "P-5 §3: the two-line pair must stay adjacent; a foreign slug landed between "
            f"{first['slug']}'s two halves"
        )


# --------------------------------------------------------------------------- #
# B3 — `--slot` isolation and its loud refusals
# --------------------------------------------------------------------------- #


def _write_loadable_config(home: Path, cfg: Mapping) -> Path:
    """A config `gen.config.load_config` accepts (it requires `duckwm_docs`)."""
    payload = dict(cfg)
    payload["duckwm_docs"] = str(CANON_DIR)
    path = home / f"{cfg['batch']['id']}.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_b3_unknown_slug_is_loud_and_names_the_batchs_slots(batch_home, capsys):
    """P-5 §Blind B3: 'unknown slug -> loud, names the batch's slugs or size'."""
    cfg = _cfg("p5blind-b3bad", size=2, armed=False, workers=1)
    path = _write_loadable_config(batch_home, cfg)
    code = orch.main(["--config", str(path), "--slot", "p5blind-b3bad-s999"])
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert code != 0, (
        "P-5 §Blind B3: an unknown --slot slug must be LOUD; main() exited 0"
    )
    assert "p5blind-b3bad-s999" in text, (
        f"P-5 §Blind B3: the refusal must name the slug it refused; said {text!r}"
    )
    assert _slugs(cfg)[0] in text or "2" in text, (
        "P-5 §Blind B3: the refusal must name 'the batch's slugs or size'; it named "
        f"neither: {text!r}"
    )
    assert not (orch.batch_dir(cfg) / orch.BATCH_REPORT_NAME).exists(), (
        "P-5 §2: a --slot run 'writes no report.json' — not even a refused one"
    )


@pytest.mark.parametrize("extra", [["--status"], ["--review", "p5blind-b3flag-s001:accept"]])
def test_b3_slot_cannot_be_combined_with_status_or_review(batch_home, capsys, extra):
    """P-5 §2: '--slot SLUG (refuse combining with --status/--review, loudly)'."""
    cfg = _cfg("p5blind-b3flag", size=1, armed=False, workers=1)
    path = _write_loadable_config(batch_home, cfg)
    code = orch.main(["--config", str(path), "--slot", _slugs(cfg)[0], *extra])
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert code != 0, (
        f"P-5 §2: `--slot` combined with {extra[0]} must be refused LOUDLY; main() exited 0 "
        "(and, worse, may have run a real stage)"
    )
    assert "--slot" in text and extra[0] in text, (
        f"P-5 §2: the refusal must name both flags it is refusing; said {text!r}"
    )
    assert not (orch.batch_dir(cfg) / orch.BATCH_REPORT_NAME).exists(), (
        "P-5 §2: a refused child must write no batch report"
    )


def test_b3_a_slot_run_touches_no_other_slots_state_and_writes_no_report(batch_home, monkeypatch):
    """P-5 §2/§Blind B3: 'a slot run touches no other slot's state and writes no report.json'."""
    cfg = _cfg("p5blind-b3iso", size=2, armed=False, workers=1)
    slug_a, slug_b = _slugs(cfg)
    journal = _Journal()
    runners = _Fakes(cfg, journal)
    bdir = orch.batch_dir(cfg)

    orch.run_slot(cfg, slug_b, runners=runners)
    before_lines = [line for line in _ledger_lines(bdir) if line["slug"] == slug_b]
    before_sidecar = orch.slot_report_path(bdir, slug_b).read_bytes()
    before_corpus = _shape(orch.CORPUS_ROOT / cfg["batch"]["id"] / f"{slug_b}-game")
    assert before_lines and before_corpus, "the blind lane's own setup must have run slot 2"

    orch.run_slot(cfg, slug_a, runners=runners)

    after_lines = [line for line in _ledger_lines(bdir) if line["slug"] == slug_b]
    assert after_lines == before_lines, (
        "P-5 §Blind B3: 'a slot run touches no other slot's state' — the sibling's ledger "
        "lines changed"
    )
    assert orch.slot_report_path(bdir, slug_b).read_bytes() == before_sidecar, (
        "P-5 §Blind B3: a slot run must not rewrite a sibling's sidecar"
    )
    assert _shape(orch.CORPUS_ROOT / cfg["batch"]["id"] / f"{slug_b}-game") == before_corpus, (
        "P-5 §Blind B3: a slot run must not touch a sibling's corpus dir"
    )
    assert not (bdir / orch.BATCH_REPORT_NAME).exists(), (
        f"P-5 §2: a child 'SKIPS … report.json' — {orch.BATCH_REPORT_NAME} was written"
    )
    assert orch.slot_report_path(bdir, slug_a).is_file(), (
        "P-5 §2: the child writes its own per-slot sidecar"
    )
    assert {line["slug"] for line in _ledger_lines(bdir)} == {slug_a, slug_b}, (
        "P-5 §2: 'A child writes ledger lines ONLY for its own slug'"
    )


def test_b3_the_default_seam_launches_the_documented_child_argv(batch_home, monkeypatch):
    """P-5 §6: the default child is `[sys.executable, -m gen.orchestrator, --config, --slot]`.

    Pinned WITHOUT starting a process: `subprocess.Popen` is stubbed, so the argv
    the seam would launch is observed and nothing is spawned.
    """
    cfg = _cfg("p5blind-argv", size=1, armed=False, workers=1)
    path = _write_loadable_config(batch_home, cfg)
    bdir = orch.batch_dir(cfg)
    bdir.mkdir(parents=True, exist_ok=True)
    seen: dict = {}

    class _FakePopen:
        def __init__(self, argv, **kwargs):
            seen["argv"] = list(argv)
            seen["kwargs"] = kwargs

        def wait(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
    code = orch.spawn_slot(config_path=path, slug=_slugs(cfg)[0], batch_dir=bdir)

    assert code == 0, "P-5 §6: the seam returns the child's exit code"
    assert seen["argv"] == [
        sys.executable, "-m", "gen.orchestrator", "--config", str(path), "--slot", _slugs(cfg)[0]
    ], (
        "P-5 §6: the default seam is documented as "
        "'[sys.executable, \"-m\", \"gen.orchestrator\", \"--config\", <path>, \"--slot\", "
        f"<slug>]'; it launched {seen['argv']}"
    )
    logs = [p for p in bdir.iterdir() if p.is_file() and p.name != orch.LEDGER_NAME]
    assert logs, (
        "P-5 §6: the child's 'stdout/stderr to per-slot log files under out/batches/<id>/' — "
        "no log file was opened"
    )


# --------------------------------------------------------------------------- #
# B4 — byte-identity, both layers
# --------------------------------------------------------------------------- #


def _resolved(home: Path, **kwargs) -> str:
    cfg = cli.build_config(
        driver="claude", batch_id="p5blind-bytes", seed=4242,
        config_dir=home / "cfgdir", batches_root=home / "batchroot", **kwargs
    )
    return cli.render_config(cfg)


def test_b4a_cli_workers_one_is_byte_identical_to_no_workers_flag(batch_home):
    """P-5 §9: '`--workers 1` and no flag resolve BYTE-IDENTICAL to today (no new keys)'."""
    plain = _resolved(batch_home, games=2)
    one = _resolved(batch_home, games=2, workers=1)
    assert one == plain, (
        "P-5 §9/§Blind B4(a): '--workers 1 and no flag resolve BYTE-IDENTICAL to today "
        "(no new keys)' — the two resolved configs differ"
    )
    assert "parallel_slots" not in plain, (
        "P-5 §9: neither `--workers 1` nor no flag may write `orchestrator.parallel_slots`"
    )


def test_b4a_workers_above_one_writes_both_arming_keys_and_clamps_to_batch_size(batch_home):
    """P-5 §9: '--workers N>1 writes BOTH keys'; 'Workers capped at batch size'."""
    cfg = cli.build_config(
        driver="claude", games=2, workers=2, batch_id="p5blind-arm", seed=1,
        config_dir=batch_home / "c1", batches_root=batch_home / "b1",
    )
    orchestrator = cfg["orchestrator"]
    assert orchestrator.get("parallel_slots") is True, (
        "P-5 §9: `--workers N>1` writes `orchestrator.parallel_slots: true`"
    )
    assert orchestrator.get("workers") == 2, (
        "P-5 §9: `--workers N>1` writes `orchestrator.workers: N` beside the arming"
    )

    clamped = cli.build_config(
        driver="claude", games=2, workers=9, batch_id="p5blind-clamp", seed=1,
        config_dir=batch_home / "c2", batches_root=batch_home / "b2",
    )
    assert clamped["orchestrator"]["workers"] == 2, (
        "P-5 §9: 'Workers capped at batch size (larger N clamps)'; got "
        f"{clamped['orchestrator']['workers']} for 2 games"
    )

    one_game = _resolved(batch_home, games=1, workers=4)
    assert one_game == _resolved(batch_home, games=1), (
        "P-5 §9: clamped to a batch of 1 there is nothing to fan out over, so the resolved "
        "config must stay byte-identical to today's (the §9 no-new-keys rule at N==1)"
    )


def test_b4b_unarmed_run_batch_never_calls_the_spawn_seam(batch_home, monkeypatch):
    """P-5 §Blind B4(b): 'an UNARMED run_batch never calls the spawn seam (booby-trap it)'."""

    def booby_trap(**kwargs):
        raise AssertionError(
            "P-5 §1: 'Absent/false = today's sequential bytes, exactly' — an UNARMED "
            f"run_batch reached the spawn seam with {kwargs}"
        )

    monkeypatch.setattr(orch, "spawn_slot", booby_trap)
    # `workers: 4` with NO `parallel_slots` is the historical config P-5 §1 says
    # must "stay sequential forever" (template.yaml already ships workers: 4).
    cfg = _cfg("p5blind-b4unarmed", size=2, armed=False, workers=4)
    journal = _Journal()
    report = orch.run_batch(cfg, runners=_Fakes(cfg, journal))

    assert "parallel" not in report, (
        "P-5 §5/§Blind B4(b): 'the sequential report gains NO new keys, byte-level' — the "
        "unarmed report carried a `parallel` key"
    )
    assert journal.spawns == [], "the seam must not have been reached at all"
    assert {row["slug"] for row in report["slots"]} == set(_slugs(cfg)), (
        "P-5 §1: the unarmed path is still today's batch, end to end"
    )


def test_b4b_parallel_slots_false_is_also_sequential(batch_home, monkeypatch):
    """P-5 §1: 'Absent block, absent key and false all mean TODAY.'"""

    def booby_trap(**kwargs):
        raise AssertionError("P-5 §1: `parallel_slots: false` must not spawn")

    monkeypatch.setattr(orch, "spawn_slot", booby_trap)
    cfg = _cfg("p5blind-b4false", size=2, armed=False, workers=4)
    cfg["orchestrator"]["parallel_slots"] = False
    report = orch.run_batch(cfg, runners=_Fakes(cfg, _Journal()))
    assert "parallel" not in report, (
        "P-5 §1: `parallel_slots: false` is today's bytes, so no `parallel` report key"
    )


def test_b4b_armed_at_one_worker_stays_sequential(batch_home, monkeypatch):
    """P-5 §1: 'The parallel path activates IFF parallel_slots is true AND workers > 1.'"""

    def booby_trap(**kwargs):
        raise AssertionError(
            "P-5 §1: armed at ONE worker 'there is nothing to spawn' — the seam was called"
        )

    monkeypatch.setattr(orch, "spawn_slot", booby_trap)
    cfg = _cfg("p5blind-b4one", size=2, armed=True, workers=1)
    report = orch.run_batch(cfg, runners=_Fakes(cfg, _Journal()))
    assert "parallel" not in report, (
        "P-5 §1: armed at workers=1 the parallel path does not activate, so the report "
        "gains no `parallel` key"
    )


def test_b4b_the_armed_report_adds_the_parallel_key_and_nothing_else(batch_home, monkeypatch):
    """P-5 §5: 'The merged report.json keeps TODAY'S SCHEMA; when armed it MAY add one
    additive `parallel` block … the sequential report gains NO new keys, byte-level.'"""
    plain_cfg = _cfg("p5blind-schemaseq", size=2, armed=False, workers=1, auto_accept=True)
    plain = orch.run_batch(plain_cfg, runners=_Fakes(plain_cfg, _Journal()))

    armed_cfg = _cfg("p5blind-schemapar", size=2, armed=True, workers=2, auto_accept=True)
    journal = _Journal()
    runners = _Fakes(armed_cfg, journal)
    _install_inprocess_seam(monkeypatch, armed_cfg, runners, journal)
    armed = orch.run_batch(armed_cfg, runners=runners, config_path=batch_home / "unused.yaml")

    assert journal.spawns, "the armed half of this pin must actually have spawned children"
    assert set(armed) - set(plain) == {"parallel"}, (
        "P-5 §5: armed, the report 'MAY add ONE additive `parallel` block' and nothing "
        f"else; it added {sorted(set(armed) - set(plain))}"
    )
    assert set(plain) - set(armed) == set(), (
        "P-5 §5: 'The merged report.json keeps TODAY'S SCHEMA'; the armed report DROPPED "
        f"{sorted(set(plain) - set(armed))}"
    )
    plain_row = {key for row in plain["slots"] for key in row}
    armed_row = {key for row in armed["slots"] for key in row}
    assert plain_row == armed_row, (
        "P-5 §5: the merged slot rows keep today's schema; armed/sequential differ by "
        f"{sorted(plain_row ^ armed_row)}"
    )
    assert plain["status"] == armed["status"] == "complete", (
        "both halves of this pin must reach the same verdict, or the schemas are being "
        "compared across different outcomes"
    )


@pytest.mark.parametrize("auto_accept,terminal", [(True, True), (False, False)])
def test_b3_child_exits_with_its_own_slots_semantics(batch_home, auto_accept, terminal):
    """P-5 §2: a child 'exits with that slot's exit semantics'."""
    cfg = _cfg(f"p5blind-exit{int(auto_accept)}", size=1, armed=False, workers=1,
               auto_accept=auto_accept)
    report = orch.run_slot(cfg, _slugs(cfg)[0], runners=_Fakes(cfg, _Journal()))
    if terminal:
        assert report["exit_code"] == 0, (
            "P-5 §2: a child 'exits with that slot's exit semantics' — a slot with nothing "
            f"left to run exits 0, not {report['exit_code']}"
        )
    else:
        assert report["exit_code"] != 0, (
            "P-5 §2: a child 'exits with that slot's exit semantics' — a slot that stopped "
            "with work outstanding (here: waiting for a human at `played`) must not exit 0"
        )


@pytest.mark.parametrize("value", [1, 0, "true", "yes", None, 1.0])
def test_b4_a_non_bool_parallel_slots_is_loud(batch_home, value):
    """P-5 §1: 'validated in orchestrator_config beside :778 — non-bool loud'."""
    cfg = _cfg("p5blind-b4bad", size=1, armed=False, workers=2)
    cfg["orchestrator"]["parallel_slots"] = value
    with pytest.raises(ValueError, match="parallel_slots"):
        orch.orchestrator_config(cfg)


def test_b4_arming_key_is_absent_from_the_reports_orchestrator_block(batch_home):
    """P-5 §1 house rule: 'every new knob DEFAULTS to today's bytes'."""
    cfg = _cfg("p5blind-b4keys", size=1, armed=False, workers=1)
    report = orch.run_batch(cfg, runners=_Fakes(cfg, _Journal()))
    assert "parallel_slots" not in report["config"]["orchestrator"], (
        "P-5 §1/§5: an unarmed run's report 'gains NO new keys, byte-level'; the report's "
        f"orchestrator block was {report['config']['orchestrator']}"
    )


# --------------------------------------------------------------------------- #
# B5 — the parent-forced S0 pre-pass
# --------------------------------------------------------------------------- #


def test_b5_every_idea_is_on_disk_before_any_child_starts(armed_two_child_batch):
    """P-5 §4: '… BEFORE spawning anything … so every idea file exists on disk first'."""
    run = armed_two_child_batch
    assert run.journal.spawns, "P-5 §4: the armed parent must have spawned children"
    expected = {f"idea-{index:03d}.json" for index in (1, 2)}
    for spawn in run.journal.spawns:
        assert set(spawn["ideas_on_disk"]) >= expected, (
            "P-5 §4/§Blind B5: 'every idea file exists on disk first' — when child "
            f"{spawn['slug']} started, the ideas dir held {spawn['ideas_on_disk']}"
        )


def test_b5_children_draw_nothing(armed_two_child_batch):
    """P-5 §4: 'children's sample_batch then finds everything kept and writes nothing'."""
    run = armed_two_child_batch
    parent_s0 = [row for row in run.journal.stages_by(None) if row[1] == "s0_ideas"]
    assert {slug for slug, _ in parent_s0} == {run.slug_a, run.slug_b}, (
        "P-5 §4: the PARENT advances every not-yet-past-s0 slot through exactly the S0 "
        f"edge; the parent ran S0 for {sorted({slug for slug, _ in parent_s0})}"
    )
    for child in (run.slug_a, run.slug_b):
        drew = [row for row in run.journal.stages_by(child) if row[1] == "s0_ideas"]
        assert drew == [], (
            f"P-5 §Blind B5: 'children draw nothing' — child {child} invoked S0 {drew}"
        )
    for slug in (run.slug_a, run.slug_b):
        carried = json.loads(
            orch.slot_report_path(run.bdir, slug).read_text(encoding="utf-8")
        )["slot"]
        assert "s0_ideas" not in (carried["invocations"] or {}), (
            f"P-5 §Blind B5: the child's own sidecar must record no S0 invocation; "
            f"{slug} recorded {carried['invocations']}"
        )


def test_b5_s0_is_recorded_once_per_slot_in_the_ledger(armed_two_child_batch):
    """P-5 §4: the parent takes 'the FIRST draw out of the race entirely'."""
    run = armed_two_child_batch
    births = [line for line in _ledger_lines(run.bdir) if line["from"] is None]
    assert sorted(line["slug"] for line in births) == sorted([run.slug_a, run.slug_b]), (
        f"P-5 §4: exactly one S0 birth line per slot, written by the parent; got {births}"
    )
    parent_written = [row for row in run.journal.appends if row[0] is None]
    assert {slug for _, slug in parent_written} == {run.slug_a, run.slug_b}, (
        "P-5 §4: the parent's pre-pass is what appends the S0 lines, before any child runs"
    )


def test_b5_a_second_draw_keeps_the_ideas_and_appends_the_history_exactly_once(batch_home):
    """P-5 addendum 2 (CORRECTED mechanism), verbatim: 'the second drawer finds the
    first's ideas on disk and KEEPS them, and the history is appended EXACTLY once'.

    Addendum 1's "the dedupe window now SEES the first's just-appended keys" is
    explicitly WITHDRAWN by addendum 2 ('that was never the mechanism'), so it is
    not pinned. The real sampler is driven here with its own `prose_runner` seam:
    roots redirected into tmp, no driver, no spend.
    """
    raw = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    raw["duckwm_docs"] = str(CANON_DIR)
    raw["batch"]["id"] = "p5blind-draw"
    raw["batch"]["size"] = 2
    raw["batch"]["seed"] = 4242
    path = batch_home / "draw.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    cfg = load_config(path)

    def prose(prompt, *args, **kwargs):
        return PROSE_REPLY

    out_dir = orch.IDEAS_ROOT / "p5blind-draw"
    history = Path(s0_ideas.DEDUPE_HISTORY_PATH)
    assert batch_home in history.parents, (
        "hermeticity: the dedupe history must be redirected into tmp before this runs"
    )

    with pytest.warns(RuntimeWarning):
        first = s0_ideas.sample_batch(cfg, batch_id="p5blind-draw", seed=4242,
                                      prose_runner=prose, out_dir=out_dir)
    after_first = history.read_text(encoding="utf-8").splitlines()
    bytes_first = {p.name: p.read_bytes() for p in sorted(out_dir.glob("idea-*.json"))}
    assert len(bytes_first) == 2 and after_first, "the first draw must write ideas and history"

    with pytest.warns(RuntimeWarning):
        second = s0_ideas.sample_batch(cfg, batch_id="p5blind-draw", seed=4242,
                                       prose_runner=prose, out_dir=out_dir)
    after_second = history.read_text(encoding="utf-8").splitlines()
    bytes_second = {p.name: p.read_bytes() for p in sorted(out_dir.glob("idea-*.json"))}

    assert bytes_second == bytes_first, (
        "P-5 addendum 2: 'the second drawer finds the first's ideas on disk and KEEPS "
        "them' — an idea file was rewritten"
    )
    assert [idea.id for idea in second] == [idea.id for idea in first], (
        "P-5 addendum 2: the kept ideas are what the second drawer returns"
    )
    assert after_second == after_first, (
        f"P-5 addendum 2: 'the history is appended EXACTLY once'; it went from "
        f"{len(after_first)} to {len(after_second)} entries"
    )


# --------------------------------------------------------------------------- #
# addendum 1/2 — the sample_batch draw lock
# --------------------------------------------------------------------------- #


def test_addendum1_the_whole_sample_batch_call_runs_under_an_exclusive_lock(
    batch_home, monkeypatch
):
    """P-5 addendum 1: 'one exclusive fcntl.flock held across the ENTIRE sample_batch
    call inside the s0 runner closure … Pin the lock is taken.'"""
    cfg = _cfg("p5blind-lock", size=2, armed=False, workers=1)
    batch_id = cfg["batch"]["id"]
    lock_path = orch.s0_draw_lock_path(batch_id)
    events: list[tuple] = []
    real_flock = fcntl.flock

    def held() -> bool:
        """Is the draw lock held right now? (flock conflicts across fds, same process.)"""
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a", encoding="utf-8") as probe:
            try:
                real_flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            real_flock(probe.fileno(), fcntl.LOCK_UN)
            return False

    inside: dict = {}

    def fake_sample_batch(cfg_arg, *, batch_id, seed, out_dir, prose_runner=None):
        events.append(("sample_batch", batch_id))
        inside["held"] = held()
        return [types.SimpleNamespace(id=f"idea-{n}") for n in (1, 2)]

    def spy(fd, operation):
        events.append(("flock", operation))
        return real_flock(fd, operation)

    monkeypatch.setattr(s0_ideas, "sample_batch", fake_sample_batch)
    monkeypatch.setattr(fcntl, "flock", spy)

    ideas_dir = orch.IDEAS_ROOT / batch_id
    ctx = orch.SlotContext(
        cfg=cfg, batch_id=batch_id, slug=orch.slot_id(batch_id, 1), index=1, state=None,
        stage="s0_ideas", attempt=1, batch_dir=orch.BATCHES_ROOT / batch_id,
        ideas_dir=ideas_dir, idea_path=ideas_dir / "idea-001.json",
        corpus_dir=orch.CORPUS_ROOT / batch_id, spec_dir=None, respec_count=0,
        verifier_rejects=0, green_failures=0,
    )
    result = orch.default_runners()["s0_ideas"](ctx)
    monkeypatch.setattr(fcntl, "flock", real_flock)

    assert result["ok"] and result["to_state"] == "ideated", (
        "the pipeline's own S0 runner must still land the §4 edge"
    )
    names = [event[0] for event in events]
    assert "sample_batch" in names, "the S0 runner must have reached sample_batch"
    called_at = names.index("sample_batch")
    locks = [op for kind, op in events[:called_at] if kind == "flock"]
    assert any(op & fcntl.LOCK_EX for op in locks), (
        "P-5 addendum 1: 'one exclusive fcntl.flock held across the ENTIRE sample_batch "
        f"call' — no LOCK_EX was taken before the call; flock ops before it: {locks}"
    )
    assert inside.get("held") is True, (
        "P-5 addendum 1: the lock is held across the WHOLE call — it was NOT held while "
        "sample_batch was executing, so a sibling drawer could enter it"
    )
    assert held() is False, (
        "P-5 addendum 2: 'the OS releases it if a holder dies' and the close releases it — "
        "the draw lock was still held after the S0 runner returned"
    )


# --------------------------------------------------------------------------- #
# B6 — the S1 writer scratch
# --------------------------------------------------------------------------- #


class _ScratchDriver:
    """A 'driver' that only writes the two files the writer session must leave."""

    name = "p5-blind-fake-driver"

    def __init__(self) -> None:
        self.cwds: list[Path] = []

    def session(self, prompt, **kwargs):
        cwd = Path(kwargs["cwd"])
        self.cwds.append(cwd)
        (cwd / "spec.md").write_text("# blind lane\n", encoding="utf-8")
        (cwd / "spec.yaml").write_text("slug: blind-lane\n", encoding="utf-8")
        return "DONE"


@pytest.fixture
def frozen_writer(batch_home, monkeypatch):
    """The S1 writer runner with the wall clock frozen (B6: 'monkeypatching the clock is fair')."""
    frozen = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)

    class _FrozenClock:
        @staticmethod
        def now(tz=None):
            return frozen

    monkeypatch.setattr(s1_spec, "datetime", _FrozenClock)
    driver = _ScratchDriver()
    backends = importlib.import_module("gen.backends")
    monkeypatch.setattr(backends, "get_driver", lambda cfg, role: (driver, "fake-model"))
    return types.SimpleNamespace(driver=driver, run=s1_spec._default_writer_runner({}))


def test_b6_two_same_second_writer_scratches_are_distinct(frozen_writer, batch_home):
    """P-5 §Blind B6: 'two writer scratch creations in the same wall-clock second yield
    distinct paths'; §8: the name 'gains slug+pid (… pid at minimum)'."""
    frozen_writer.run("first prompt")
    frozen_writer.run("second prompt")
    first, second = frozen_writer.driver.cwds
    assert first != second, (
        "P-5 §8/§Blind B6: two writer scratches created in the SAME wall-clock second "
        f"must be distinct paths; both were {first}"
    )
    assert first.is_dir() and second.is_dir(), "both scratch dirs must really exist"
    assert first.parent == second.parent == Path(s1_spec.S1_SCRATCH_ROOT), (
        "hermeticity: the writer scratch must live under the (redirected) scratch root"
    )
    assert str(first.parent).startswith(str(batch_home)), (
        "hermeticity: the writer scratch must be inside tmp, never the repo's out/tmp"
    )
    assert str(os.getpid()) in first.name, (
        "P-5 §8: the scratch name 'gains slug+pid (slug if reachable at the call site, pid "
        f"at minimum)'; {first.name!r} carries no pid"
    )


def test_b6_a_scratch_collision_is_loud_instead_of_silently_shared(frozen_writer, monkeypatch):
    """P-5 §8: 'exist_ok dropped (a collision now FAILS loudly instead of silently sharing)'."""
    real_mkdir = Path.mkdir
    sabotaged: list[Path] = []

    def sabotage(self, *args, **kwargs):
        # Make the exact path the writer is about to create already exist, so a
        # surviving `exist_ok=True` would silently SHARE it (the §Evidence defect)
        # and a dropped one raises.
        if self.name.startswith("s1-writer-") and not sabotaged:
            sabotaged.append(self)
            real_mkdir(self, parents=True, exist_ok=True)
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", sabotage)
    with pytest.raises(FileExistsError):
        frozen_writer.run("colliding prompt")
    monkeypatch.setattr(Path, "mkdir", real_mkdir)
    assert sabotaged, "the blind lane's sabotage never fired — the pin proved nothing"


# --------------------------------------------------------------------------- #
# B7 — never-kill
# --------------------------------------------------------------------------- #


def _run_never_kill(batch_home, monkeypatch, batch_id: str, behaviour: Mapping):
    cfg = _cfg(batch_id, size=2, armed=True, workers=2, auto_accept=True)
    slug_a, slug_b = _slugs(cfg)
    journal = _Journal()
    runners = _Fakes(cfg, journal)
    _install_recording_ledger(monkeypatch, journal)
    _install_inprocess_seam(monkeypatch, cfg, runners, journal, behaviour=behaviour)
    report = orch.run_batch(cfg, runners=runners, config_path=batch_home / "unused.yaml")
    return types.SimpleNamespace(cfg=cfg, report=report, journal=journal, slug_a=slug_a,
                                 slug_b=slug_b, bdir=orch.batch_dir(cfg))


def test_b7_a_child_that_raises_never_stops_its_sibling(batch_home, monkeypatch):
    """P-5 §4: 'A child's nonzero exit NEVER interrupts a running wave (never-kill)';
    §Blind B7: 'the sibling completes, the batch report carries both'."""
    cfg = _cfg("p5blind-b7raise", size=2, armed=True, workers=2, auto_accept=True)
    slug_a = _slugs(cfg)[0]
    run = _run_never_kill(batch_home, monkeypatch, "p5blind-b7raise", {slug_a: "raise"})

    sibling = _row(run.report, run.slug_b)
    assert sibling["state"] == "packaged", (
        "P-5 §Blind B7: 'the sibling completes' — one child's failure took the other down "
        f"({sibling['state']})"
    )
    dead = _row(run.report, run.slug_a)
    assert dead["state"] == "ideated", (
        "P-5 §4: 'its ledger state stands' — the failed child's slot must still hold the "
        f"parent's S0 line and nothing more; it reads {dead['state']}"
    )
    idea = Path(dead["paths"]["idea"])
    assert idea.is_file(), (
        "P-5 §4/§Blind B7: 'nothing destroyed' — the failed slot's idea file is gone"
    )
    children = run.report["parallel"]["children"]
    assert {child["slug"] for child in children} == {run.slug_a, run.slug_b}, (
        f"P-5 §Blind B7: 'the batch report carries both'; it carried {children}"
    )
    failed = next(child for child in children if child["slug"] == run.slug_a)
    assert failed["exit_code"] != 0 or failed.get("error"), (
        "P-5 §5: the `parallel` block records per-child exit codes — a launcher that blew "
        f"up must be visible, not silent: {failed}"
    )
    assert run.report["exit_code"] != 0 and run.report["status"] != "complete", (
        "P-5 §Blind B7: 'exit code reflects the failure'"
    )


def test_b7_a_child_with_no_sidecar_is_reported_from_the_ledger_alone(batch_home, monkeypatch):
    """P-5 §5: 'a slot with no sidecar — child crashed pre-write — gets the ledger-derived
    row; its in-memory-only fields stay null'."""
    cfg = _cfg("p5blind-b7nosidecar", size=2, armed=True, workers=2, auto_accept=True)
    slug_a = _slugs(cfg)[0]
    run = _run_never_kill(batch_home, monkeypatch, "p5blind-b7nosidecar", {slug_a: "raise"})

    assert not orch.slot_report_path(run.bdir, run.slug_a).exists(), (
        "the blind lane's own setup must leave the crashed child sidecar-less"
    )
    row = _row(run.report, run.slug_a)
    assert row["blocked"] is None, (
        "P-5 §5: with no sidecar the in-memory-only fields 'stay null'; blocked was "
        f"{row['blocked']!r}"
    )
    assert row["review_pending"] is False and row["off_ledger_cost"]["runs"] == 0, (
        "P-5 §5: with no sidecar the in-memory-only fields stay at their empty values"
    )
    assert row["state"] == "ideated" and row["transitions"] == 1, (
        "P-5 §5: the ledger-derived row still stands — 'exactly what today's resume path "
        "reports'"
    )
    assert orch.slot_report_path(run.bdir, run.slug_b).is_file(), (
        "P-5 §Blind B7: the sibling still wrote its own sidecar"
    )


def test_b7_a_nonzero_child_exit_is_reported_and_destroys_nothing(batch_home, monkeypatch):
    """P-5 §4: 'A child's nonzero exit NEVER interrupts a running wave … the parent
    reports it, resume re-runs it.'"""
    cfg = _cfg("p5blind-b7exit", size=2, armed=True, workers=2, auto_accept=True)
    slug_a = _slugs(cfg)[0]
    run = _run_never_kill(batch_home, monkeypatch, "p5blind-b7exit", {slug_a: 7})

    children = {child["slug"]: child for child in run.report["parallel"]["children"]}
    assert children[run.slug_a]["exit_code"] == 7, (
        "P-5 §5: 'every child's exit code is here because a nonzero one names a slot to "
        f"resume'; got {children[run.slug_a]}"
    )
    assert _row(run.report, run.slug_b)["state"] == "packaged", (
        "P-5 §Blind B7: the sibling completes regardless of the other child's exit code"
    )
    assert run.report["status"] != "complete" and run.report["exit_code"] != 0, (
        "P-5 §Blind B7: 'exit code reflects the failure without destroying anything'"
    )
    # Nothing destroyed: the failing child's own work is all still on the ledger.
    assert _row(run.report, run.slug_a)["state"] == "packaged", (
        "P-5 §4: 'its ledger state stands' — a nonzero exit must not roll back the work "
        "the child actually recorded"
    )
    table = orch.replay_ledger(run.bdir / orch.LEDGER_NAME)
    assert set(table) == {run.slug_a, run.slug_b}, (
        "P-5 §4: 'the ledger is the truth' and it must still replay after a child failure"
    )
