"""b002 hotfix #3 — a drawn idea is immutable, and solver drives are isolated.

TWO DEFECTS, ONE FILE.

**D1 — flavor prose moves the bytes §2 content-addresses.** `s1_spec`'s stage
input is the idea file, so `idea-<NNN>.json`'s bytes ARE the provenance of
everything downstream of it. The sampler's `prose` block comes from a live
language-model call, so a second process re-drawing the same slot produces a
structurally identical idea wrapped in different words — and rewriting the file
with it changes the hash. The resume check then reads S1 as stale, re-runs it,
and the re-run names its output dir from the new spec's slug: two live dirs end
up claiming one idea and the batch cannot start. Nothing semantic moved; only
the prose did. So an idea file that already exists is never rewritten, a
STRUCTURAL divergence (a real change of draw) raises instead of silently
overwriting, and the dedupe history records only ideas actually written.

**D2 — an in-process solver drive can be served a stale game.** A generated
solver looks its sibling game module up in `sys.modules` under a name derived
from the game's PATH, and that path does not change when the file is rewritten.
So a long-lived process that re-implements `game.py` and then drives the solver
in-process pairs a FRESH game with the solver's CACHED one: the plan the solver
derives does not fit the board it is played on, and the line dies early for
reasons that have nothing to do with the game. No rule about how generated code
caches its own imports can be relied on, so the fix is the one that holds for
code we did not write — a fresh interpreter, whose empty `sys.modules` has
nothing stale to serve. Both stages that DRIVE A SOLVER (S4's baselines and the
gate's frame capture) go out of process.

INDEPENDENCE. Written from the frozen contract alone, against the declared
public behaviour of `sample_batch` / `run_s4_isolated` / the `s3_gate` runner —
never against their code. Every fixture below is either invented in this file
or one of the checked-in fixtures under `gen/tests/fixtures/`, copied to tmp
before anything runs it; the sampler's dedupe history is redirected off the
live tree and the redirect is checked on teardown. No text, name, number or
path from any real run appears anywhere here (pinned by the last test).

Run: .venv/bin/python -m pytest gen/tests/test_b002_hotfix3.py -v
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import gen.s0_ideas as s0
import gen.s4_baselines as s4
from gen import frames
from gen.config import REPO_ROOT, load_config
from gen.orchestrator import SlotContext, default_runners
from gen.worker import instantiate_worker

PILOT_CONFIG = "config/b001-pilot.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
S4_WORKERS = FIXTURES / "s4_workers"
GENEROUS = "capped_generous"   # the checked-in worker whose cap-fit FITS
TIGHT = "capped_tight"         # the checked-in worker whose cap-fit REJECTS
FIXTURE_SPEC = FIXTURES / "specs/good-spec.yaml"

# Invented names. They give the planted trees the shape the state machine walks
# and name nothing that has ever been sampled or built.
BATCH_ID = "b-hotfix3-fixture"
SLOT_SLUG = f"{BATCH_ID}-s001"
SPEC_SLUG = "fogbound-switchyard"   # the checked-in fixture spec's own slug
DRAW_SEED = 7
S4_SEED = 11

# The contract's structural field list, frozen. Anything outside it (today:
# `prose`) is flavor, and flavor must not move an artifact's bytes.
STRUCTURAL_FIELDS = (
    "id", "objective", "seed_terms", "tier", "mix_class", "failure_family", "dedupe_key",
)


# --- helpers -----------------------------------------------------------------


class _ProseRunner:
    """A stand-in for the sampler's prose call: no session, no spend, no network.

    Two runners built with different tags return different words for the same
    prompt — which is precisely the difference a resume sees between two live
    draws of one structurally identical idea. The reply is shaped from the
    sampler's own published prose constants so it cannot drift out of spec.
    """

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.prompts: list[str] = []

    @property
    def title(self) -> str:
        return f"Synthetic Fixture Yard {self.tag}"

    @property
    def text(self) -> str:
        sentence = f"Synthetic fixture sentence for the {self.tag} draw. "
        repeats = (s0.PROSE_TEXT_MIN_CHARS // len(sentence)) + 2
        return (sentence * repeats).strip()

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return f"{self.title}\n\n{self.text}\n"


def _ideas_cfg(cfg: dict, *, size: int) -> dict:
    """The pilot config with the batch resized — a deep copy, never the shared one."""
    out = copy.deepcopy(dict(cfg))
    out["batch"] = dict(out["batch"], id=BATCH_ID, size=size)
    return out


def _idea_paths(out_dir: Path) -> list[Path]:
    return sorted(s0.batch_out_dir(BATCH_ID, out_dir).glob("idea-*.json"))


def _snapshot(paths: list[Path]) -> dict[str, tuple[bytes, int]]:
    """Bytes AND mtime_ns per file: bytes catch a changed rewrite, mtime catches
    an identical one (a write that happens to reproduce the same content is
    still a write, and still churns anything watching the file)."""
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}


def _history_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _copy_worker(name: str, dest: Path) -> Path:
    """A checked-in S4 worker fixture, copied to tmp. Nothing ever runs inside
    `gen/tests/fixtures/` — S4 writes reports and action files beside its worker."""
    source = S4_WORKERS / name
    assert source.is_dir(), f"missing checked-in fixture worker: {source}"
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def _cached_module_names(worker: Path) -> tuple[str, ...]:
    """The `sys.modules` key(s) a generated solver would cache its game under.

    The scaffold's own sibling-loader idiom: `"game_"` plus the first 12 hex
    digits of the sha256 of the game file's PATH STRING. Both the literal and
    the resolved spelling are produced, because on a platform whose temp root is
    a symlink the two differ and a generated solver may have computed either.
    """
    game_py = worker / "game.py"
    spellings = {str(game_py), str(game_py.resolve())}
    return tuple(sorted(
        "game_" + hashlib.sha256(spelling.encode("utf-8")).hexdigest()[:12]
        for spelling in spellings
    ))


# --- fixtures ----------------------------------------------------------------


@pytest.fixture(scope="module")
def cfg() -> dict:
    return load_config(PILOT_CONFIG)


@pytest.fixture
def ideas_history(tmp_path, monkeypatch) -> Path:
    """Redirect the sampler's dedupe history off the live tree — and prove it.

    `DEDUPE_HISTORY_PATH` is a module constant pointing at this repo's run
    outputs, which the contract forbids either agent to write. The teardown
    re-reads the live file's bytes and mtime, so a draw that ever reached it
    fails HERE, in the test that caused it, instead of surfacing later as a
    dirty tree nobody can attribute.
    """
    live = s0.DEDUPE_HISTORY_PATH
    before = (live.read_bytes(), live.stat().st_mtime_ns) if live.exists() else None
    redirected = tmp_path / "dedupe-history.jsonl"
    monkeypatch.setattr(s0, "DEDUPE_HISTORY_PATH", redirected)

    yield redirected

    after = (live.read_bytes(), live.stat().st_mtime_ns) if live.exists() else None
    assert after == before, (
        f"the live dedupe history at {live} was written during this test — every draw here "
        "must land in the redirected tmp copy"
    )


# --- 1. a second draw never rewrites an idea file ----------------------------


def test_1_a_second_draw_leaves_every_idea_file_byte_identical(tmp_path, cfg, ideas_history):
    """THE D1 PIN. Draw the same batch twice into one dir with prose that
    differs on the second pass: the files must not move — not their bytes, not
    their mtimes — and the history must not grow for ideas nobody wrote."""
    out = tmp_path / "ideas"
    batch_cfg = _ideas_cfg(cfg, size=2)
    alpha, beta = _ProseRunner("alpha"), _ProseRunner("beta")
    assert alpha.text != beta.text, "fixture: the two runners must disagree, or this pins nothing"

    s0.sample_batch(batch_cfg, batch_id=BATCH_ID, seed=DRAW_SEED,
                    prose_runner=alpha, out_dir=out)
    paths = _idea_paths(out)
    assert len(paths) == batch_cfg["batch"]["size"], f"fixture: first draw wrote {paths}"
    before = _snapshot(paths)
    history_before = _history_lines(ideas_history)

    second = s0.sample_batch(batch_cfg, batch_id=BATCH_ID, seed=DRAW_SEED,
                             prose_runner=beta, out_dir=out)

    assert beta.prompts, (
        "fixture liveness: the second pass must actually re-draw (and so produce the differing "
        "prose this pin is about). If a future sampler skips the draw entirely, THIS assertion "
        "is the one to renegotiate — never the byte-identity below"
    )
    after_paths = _idea_paths(out)
    assert [p.name for p in after_paths] == [p.name for p in paths], (
        f"the second pass must not add or remove idea files; {[p.name for p in after_paths]}"
    )
    assert _snapshot(after_paths) == before, (
        "a re-drawn idea file must be KEPT byte-for-byte. Its bytes are what §2 "
        "content-addresses, so rewriting flavor prose restages every stage downstream of it and "
        "the resume splits one idea across two live corpus dirs"
    )
    for path in after_paths:
        text = path.read_text(encoding="utf-8")
        assert alpha.title in text, f"{path.name} must still hold the prose it was written with"
        assert beta.title not in text, (
            f"the second draw's prose reached {path.name} — that rewrite IS the defect"
        )

    on_disk = [json.loads(p.read_text(encoding="utf-8")) for p in after_paths]
    assert len(second) == len(on_disk), (
        f"the returned list must describe what is on disk; got {len(second)} for {len(on_disk)} "
        "files"
    )
    for idea, kept in zip(second, on_disk, strict=True):
        drawn = idea.to_json_dict()
        for field in STRUCTURAL_FIELDS:
            assert drawn[field] == kept[field], (
                f"the returned idea's {field!r} disagrees with the kept file — the structural "
                "check is what makes keeping the file safe, so a mismatch here means the caller "
                "is being handed something the pipeline will not find on disk"
            )

    assert _history_lines(ideas_history) == history_before, (
        "nothing was drawn-and-kept, so nothing new belongs in the dedupe history; re-appending "
        "on every resume inflates it until the window stops meaning anything"
    )


# --- 2. a structural divergence is loud --------------------------------------


def test_2_a_structural_divergence_raises_and_keeps_the_file(tmp_path, cfg, ideas_history):
    """A changed STRUCTURAL field is a real change of draw — a moved seed or a
    moved config — never something to overwrite in silence. It raises, it names
    the file and the field and both values, and the file survives untouched."""
    out = tmp_path / "ideas"
    batch_cfg = _ideas_cfg(cfg, size=1)
    s0.sample_batch(batch_cfg, batch_id=BATCH_ID, seed=DRAW_SEED,
                    prose_runner=_ProseRunner("alpha"), out_dir=out)
    (path,) = _idea_paths(out)

    planted = json.loads(path.read_text(encoding="utf-8"))
    drawn_tier = planted["tier"]
    other_tier = next(t for t in s0.TIERS if t != drawn_tier)
    assert "tier" in STRUCTURAL_FIELDS and other_tier != drawn_tier, "fixture: pick a real change"
    planted["tier"] = other_tier
    path.write_text(json.dumps(planted, indent=2) + "\n", encoding="utf-8")
    before = _snapshot([path])

    with pytest.raises(ValueError) as excinfo:
        s0.sample_batch(batch_cfg, batch_id=BATCH_ID, seed=DRAW_SEED,
                        prose_runner=_ProseRunner("beta"), out_dir=out)

    message = str(excinfo.value)
    assert path.name in message, (
        f"the error must name the file it refuses to overwrite; got {message!r}"
    )
    assert "tier" in message, (
        f"the error must name the field that diverged, or it cannot be acted on; got {message!r}"
    )
    for value in (drawn_tier, other_tier):
        assert value in message, (
            f"both values belong in the message — {value!r} is missing from {message!r}. (These "
            "two are short enough that no truncation can excuse their absence.)"
        )
    assert _snapshot([path]) == before, (
        "the refused file must survive byte-for-byte: refusing to overwrite is the whole point, "
        "and a half-applied write would leave the divergence undiagnosable"
    )


# --- 3. the happy path is unchanged ------------------------------------------


def test_3_a_first_draw_still_writes_every_idea(tmp_path, cfg, ideas_history):
    """Regression guard: into an EMPTY dir nothing about the sampler changed —
    `batch.size` files, numbered from one, each holding its drawn idea."""
    out = tmp_path / "ideas"
    size = 3
    batch_cfg = _ideas_cfg(cfg, size=size)
    runner = _ProseRunner("alpha")

    ideas = s0.sample_batch(batch_cfg, batch_id=BATCH_ID, seed=DRAW_SEED,
                            prose_runner=runner, out_dir=out)

    paths = _idea_paths(out)
    assert [p.name for p in paths] == [f"idea-{i:03d}.json" for i in range(1, size + 1)], (
        f"a first draw writes batch.size ({size}) numbered idea files; got {[p.name for p in paths]}"
    )
    assert len(ideas) == size
    for idea, path in zip(ideas, paths, strict=True):
        written = json.loads(path.read_text(encoding="utf-8"))
        assert written == idea.to_json_dict(), (
            f"{path.name} must hold exactly the idea that was drawn for it"
        )
        assert sorted(written) == sorted(s0.IDEA_KEYS), (
            f"{path.name} must carry the full idea schema; got {sorted(written)}"
        )
        assert written["prose"]["title"] == runner.title, (
            "the drawn prose must reach a file that did not exist before"
        )
    assert len(_history_lines(ideas_history)) == size, (
        f"every newly written idea belongs in the dedupe history; got "
        f"{len(_history_lines(ideas_history))} line(s) for {size} new files"
    )


# --- 4. the isolated S4 agrees with the in-process one -----------------------


def test_4_isolated_s4_returns_what_in_process_s4_returns(tmp_path, cfg):
    """Isolation must change WHERE S4 runs and nothing else. Same worker, same
    seed, two out dirs: the verdict and the result must be the same object."""
    worker = _copy_worker(GENEROUS, tmp_path / GENEROUS)

    isolated = s4.run_s4_isolated(worker, cfg, seed=S4_SEED)
    in_process = s4.run_s4(worker, cfg, seed=S4_SEED, out_dir=tmp_path / "in-process")

    assert isolated["verdict"] == s4.VERDICT_FIT, (
        f"fixture: {GENEROUS} is the worker that FITS; got {isolated['verdict']!r}"
    )
    assert isolated["verdict"] == in_process["verdict"], (
        f"isolated verdict {isolated['verdict']!r} != in-process {in_process['verdict']!r} — a "
        "subprocess that reaches a different verdict is not the same stage"
    )
    assert isolated["result"] == in_process["result"], (
        "the whole measured result (baselines, g, invariants, redraws, attempts) must survive "
        "the JSON round trip through the child unchanged"
    )

    sibling = worker.with_name(worker.name + s4.OUT_SUFFIX)
    assert (sibling / s4.REPORT_NAME).is_file(), (
        f"with no --out the isolated runner must default to the worker sibling {sibling.name}/, "
        "exactly as the in-process runner does, or a resume looks for the report in the wrong "
        "place"
    )
    assert json.loads((sibling / s4.REPORT_NAME).read_text(encoding="utf-8")) == isolated, (
        "the returned dict must be the report the child left on disk, read back — not a summary "
        "of it"
    )


# --- 5. a poisoned parent cannot reach the child -----------------------------


def test_5_a_poisoned_parent_module_cache_cannot_reach_the_child(tmp_path, cfg):
    """THE D2 PIN. Plant a decoy in THIS process under the exact name a generated
    solver caches its game under. The child starts from an empty `sys.modules`,
    so the run must still fit — a stale parent cache is unreachable from it."""
    worker = _copy_worker(GENEROUS, tmp_path / GENEROUS)
    names = _cached_module_names(worker)
    assert names, "fixture: the cache key derivation produced no name"

    decoys = {}
    try:
        for name in names:
            assert name not in sys.modules, f"fixture: {name} must be ours to plant"
            decoy = ModuleType(name)
            decoy.POISONED_BY_THE_TEST = True
            sys.modules[name] = decoy
            decoys[name] = decoy
        for name, decoy in decoys.items():
            assert sys.modules[name] is decoy, f"fixture: {name} was not planted"

        report = s4.run_s4_isolated(worker, cfg, seed=S4_SEED)

        assert report["verdict"] == s4.VERDICT_FIT, (
            f"a decoy in the PARENT's module cache changed the child's verdict to "
            f"{report['verdict']!r}. The child is a fresh interpreter: if what this process has "
            "cached can reach it at all, the isolation buys nothing and a re-implemented game "
            "can still be driven against a solver's stale sibling"
        )
        for name, decoy in decoys.items():
            assert sys.modules.get(name) is decoy, (
                f"the child must not reach back into the parent's module cache, but {name} is no "
                "longer the decoy this test planted"
            )
    finally:
        for name in decoys:
            sys.modules.pop(name, None)


# --- 6. a cap-fit reject is a verdict, not a crash ---------------------------


def test_6_a_cap_fit_reject_comes_back_as_a_report(tmp_path, cfg):
    """A cap-fit reject is a legitimate verdict with a report on disk; the child
    exits nonzero to say so. The parent must RETURN that report, not raise: the
    caller routes on the verdict, and an exception here would turn a measured
    reject into an unhandled failure of the stage."""
    worker = _copy_worker(TIGHT, tmp_path / TIGHT)

    report = s4.run_s4_isolated(worker, cfg, seed=S4_SEED)

    assert report["verdict"] == s4.VERDICT_REJECT, (
        f"fixture: {TIGHT} is the worker whose cap-fit REJECTS; got {report['verdict']!r}"
    )
    assert report["result"]["verdict"] == s4.VERDICT_REJECT, (
        "the measured result must carry the reject too, or the routing verdict and the evidence "
        "disagree"
    )
    sibling = worker.with_name(worker.name + s4.OUT_SUFFIX)
    assert json.loads((sibling / s4.REPORT_NAME).read_text(encoding="utf-8")) == report, (
        "a reject leaves a full report on disk and the parent returns exactly it — the child's "
        "nonzero exit is the verdict, not an error"
    )


# --- 7. the gate runner takes its frames out of process ----------------------


def _plant_gate_slot(root: Path, cfg: dict) -> SimpleNamespace:
    """A slot at `verified`, in architecture §2's shape, ready for the gate.

    `corpus/<batch>/<slug>/{spec.yaml,spec.md,worker/}` plus the S2b report
    sibling the gate's stage inputs name. The worker is a real instantiated
    scaffold whose two editable files are the checked-in S4 fixture's, so the
    gate has an actual playable game to take frames from. A REAL `SlotContext`
    is built (not a duck) so every field the runner may touch is present.
    """
    corpus_dir = root / "corpus" / BATCH_ID
    spec_dir = corpus_dir / SPEC_SLUG
    spec_dir.mkdir(parents=True)
    shutil.copy2(FIXTURE_SPEC, spec_dir / "spec.yaml")
    (spec_dir / "spec.md").write_text(
        "# Fixture prose spec\n\nSynthetic text, written here, so the planted slot is a "
        "complete S1 output.\n",
        encoding="utf-8",
    )
    worker = spec_dir / "worker"
    instantiate_worker(worker)
    for editable in ("game.py", "solver.py"):
        shutil.copy2(S4_WORKERS / GENEROUS / editable, worker / editable)

    ideas_dir = root / "ideas" / BATCH_ID
    ideas_dir.mkdir(parents=True)
    ctx = SlotContext(
        cfg=cfg,
        batch_id=BATCH_ID,
        slug=SLOT_SLUG,
        index=1,
        state="verified",
        stage="s3_gate",
        attempt=1,
        batch_dir=root / "batch",
        ideas_dir=ideas_dir,
        idea_path=ideas_dir / "idea-001.json",
        corpus_dir=corpus_dir,
        spec_dir=spec_dir,
        respec_count=0,
        verifier_rejects=0,
        green_failures=0,
    )
    assert ctx.verifier_report_path is not None, "fixture: the gate's S2b input must resolve"
    ctx.verifier_report_path.write_text(
        json.dumps({"verdict": "pass", "reject_reasons": []}, indent=2) + "\n", encoding="utf-8"
    )
    return SimpleNamespace(root=root, spec_dir=spec_dir, worker=worker, ctx=ctx)


def test_7_the_gate_runner_captures_frames_out_of_process(tmp_path, cfg, monkeypatch):
    """The gate DRIVES the solver, so it carries D2 exactly as S4 does. Its
    frames must come from the isolated helper, over this slot's own worker."""
    slot = _plant_gate_slot(tmp_path, cfg)
    real_isolated = frames.capture_worker_isolated
    calls: list[Path] = []

    def recorder(worker_dir, **kwargs):
        calls.append(Path(worker_dir))
        return real_isolated(worker_dir, **kwargs)

    monkeypatch.setattr(frames, "capture_worker_isolated", recorder)
    if hasattr(sys.modules["gen.orchestrator"], "capture_worker_isolated"):
        # Covers the other import style; the attribute is only patched if it
        # exists, so nothing is invented on the module either way.
        monkeypatch.setattr(sys.modules["gen.orchestrator"], "capture_worker_isolated", recorder)

    result = default_runners()["s3_gate"](slot.ctx)

    assert isinstance(result, dict) and "ok" in result, (
        f"the runner must come back with a result dict whatever the gate decides; got {result!r}"
    )
    assert len(calls) == 1, (
        f"the gate must take its frames through the isolated helper exactly once per run; it "
        f"called it {len(calls)} time(s). Zero means the frames still come from an in-process "
        "load, which is the defect: a solver that cached a sibling game earlier in this "
        "interpreter is handed that stale module and plays a board it was not planned against"
    )
    assert calls[0].resolve() == slot.ctx.worker_dir.resolve(), (
        f"the isolated capture must be pointed at THIS slot's worker "
        f"({slot.ctx.worker_dir}); it was handed {calls[0]}"
    )


# --- the contract's absolute rule, self-checked ------------------------------


def test_every_fixture_in_this_file_is_synthetic_or_checked_in():
    """Nothing here comes from a live run: no batch output is read, named or
    quoted, and every worker/spec fixture is one checked into this repo."""
    source = Path(__file__).read_text(encoding="utf-8")

    # Built at runtime so the markers are not literals in the source they check.
    out = "out"
    for marker in (f"{out}/{name}" for name in
                   ("corpus", "batches", "ideas", "play", "pilot", "workers", "verify")):
        assert marker not in source, (
            f"this file must never reach into the live tree ({marker}) — every fixture it uses "
            "is synthetic or checked in"
        )
    for artifact in ("ledger." + "jsonl", "batch-" + "report.json"):
        assert artifact not in source, f"no real batch artifact ({artifact}) may be read here"

    for fixture in (S4_WORKERS / GENEROUS, S4_WORKERS / TIGHT, FIXTURE_SPEC):
        assert fixture.exists(), f"missing checked-in fixture: {fixture}"
        assert FIXTURES in fixture.parents, (
            f"{fixture} is outside gen/tests/fixtures/ — a test fixture must be checked in, not "
            "borrowed from a run"
        )
    assert SPEC_SLUG in FIXTURE_SPEC.read_text(encoding="utf-8"), (
        "the planted slot's dir name must be the checked-in fixture spec's own slug, not a name "
        "taken from anywhere else"
    )
    assert BATCH_ID.startswith("b-") and "fixture" in BATCH_ID, (
        f"the invented batch id must declare itself a fixture; got {BATCH_ID!r}"
    )
    assert not (REPO_ROOT / out / "corpus" / BATCH_ID).exists(), (
        f"{BATCH_ID!r} must name no batch that has ever been run"
    )
