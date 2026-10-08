"""R2 hotfix #9 acceptance: a DECLARATION-ONLY re-spec skips the re-implement.

Run: .venv/bin/python -m pytest gen/tests/test_r2_hotfix9.py -v

The problem the contract names: an escalated re-spec that answers the audit by
widening `game.terms` / `game.knobs.deceptions` changes spec.yaml's bytes, so
§2's cascade re-runs S2 — and a re-implement hands the next audit a NOVEL game
to find novel findings in. The game code reads neither field, so a spec change
confined to them cannot invalidate the implementation beside it. Four pieces:

  A. `s1_spec.impl_projection(spec_yaml_bytes) -> str` — the sha256 of the
     canonical-json spec document with those two fields REMOVED. Equal
     projections mean "the same game was specified".
  B. `orchestrator._maybe_respec` writes a worker-SIBLING marker
     (`DECL_ONLY_MARKER_SUFFIX`) after a successful escalated re-spec, iff the
     old and new projections are equal and the worker dir exists. It carries
     `to_spec` (sha256 of the NEW spec.yaml bytes), `from_spec` and `ts`.
  C. The S2 stage consumes that marker SINGLE-SHOT and skips the re-implement.
  D. Nothing writes a marker on a run that never escalated.

Written against the frozen R2 hotfix-9 mini-contract while `gen/s1_spec.py` and
`gen/orchestrator.py` were changed in parallel. No line of that work was read:
the only implementation text seen while locating the contract surface was the
`DECL_ONLY_MARKER_SUFFIX` doc comment that happens to sit between `STAGES` and
`VERIFIER_REJECT_CAP_ESCALATE`, and nothing here is derived from it.

Three standing rules this file keeps (the test_r2_hotfix6.py precedent):

  * NO API call, ever. Every orchestrator path is driven by b11's FAKE stage
    runners, and b11's `_no_network_no_agent` guard is re-bound here so a stray
    `get_driver` fails the test loudly. Group C drives the REAL S2 runner, with
    its three expensive legs (`instantiate_worker`, `build_payload`,
    `green_loop`) monkeypatched to raise — reaching one is a failure, not a
    spend.
  * NO writes outside `tmp_path`. `batch_home` re-roots every repo path in the
    orchestrator at `tmp_path`, and b11's `_repo_batches_untouched` guard is
    re-bound so a stray write into the repo batch root fails loudly.
  * NOTHING IS READ OUT OF `out/`. Every spec document below is the committed
    B5 fixture (`fixtures/specs/good-spec.yaml`) with ONE thing changed, and
    the planted worker is the committed `toy_worker/` pair. The only contact
    with `out/` in this file is b11's protective snapshot of the NAMES under
    `out/batches` — no artifact is ever read.

WHICH FORM GROUP C TOOK, and why (the contract left this open). `run_batch`
takes its runner table as a REPLACEMENT (`stages = default_runners() if runners
is None else dict(runners)`), so under the b11 fake rig the real S2 runner —
the one the contract modifies — is never called: the marker's consumption is
UNREACHABLE from the rig. So the two rig cases pin only what is reachable
there (the marker's creation, its absence, and the removal of a stale one:
group B), and the single-shot consume + the skip are pinned at the UNIT level
in group C, by calling `default_runners()["s2_implement"]` directly against a
tmp corpus holding a planted, green-validating worker. Group B additionally
pins the marker's presence AT THE MOMENT the next stage was entered, which is
the half of the handoff the rig can still witness.

Contract readings this file encodes where the hotfix-9 contract left a choice
open — each one is a line to renegotiate, not a fact:

  * "canonical-json" is read as the house form `_digest` already uses
    (`json.dumps(..., sort_keys=True, separators=(",", ":"))`), so a document
    whose KEY ORDER differs projects equal. That is one test, named, and it is
    the line to renegotiate if the implementation dumps in document order.
  * "with `game.terms` and `game.knobs.deceptions` REMOVED" is pinned by
    BEHAVIOUR (equal/unequal projections), never by recomputing the digest
    here. A test that re-implemented the hash would pass against a wrong
    implementation that made the same mistake twice.
  * A.4's "non-mapping document" is read as: what `yaml.safe_load` returns is
    not a Mapping (a list, a scalar, an empty document). The complement is also
    pinned — a MAPPING that simply has no `game` key must NOT raise — because
    the existing rig writes exactly such a spec.yaml (`slug:`/`revision:`), and
    `test_r2_hotfix6`'s group 3 drives `_maybe_respec` over it. If projection
    raised there, a passing suite would start crashing in another file.
  * Invalid UTF-8 counts as "malformed yaml bytes". Either route reaches
    `ValueError` (`UnicodeDecodeError` IS one), so the pin is cheap and holds
    for both implementations.
  * The marker's FILENAME is taken from the contract literally
    (`.decl-only-respec.json`), because the glob that proves "no marker
    anywhere" (D) needs a literal to search for. `DECL_ONLY_MARKER_SUFFIX` is
    pinned to that same literal in its own test, so a rename breaks one named
    test instead of silently emptying every glob.
  * "worker-SIBLING" is pinned as: the marker sits in the worker's PARENT dir,
    named `<worker dir name> + suffix` — the shape `verifier_report_path`
    already uses — and the worker dir is there beside it.
  * `from_spec`/`to_spec` are pinned as the sha256 of the OLD and NEW spec.yaml
    BYTES AS THIS TEST WROTE THEM, not as read back off disk at the end of the
    run: a later re-stage that rewrote spec.yaml would make the disk copy lie
    about what the marker recorded.
  * `ts` is pinned as a non-empty string only. No format is contracted.
  * "the worker dir exists" is pinned with a third rig case that deletes the
    worker dir on the escalated re-spec call, AFTER the fake S1 has written and
    before `_maybe_respec` decides (the verifier report is a SIBLING, so the
    escalation itself survives the deletion).
  * TWO RIG FACTS the fakes impose, both worked around in `_RespecRunners` and
    neither of them a statement about the contract. (1) b11's fake writes the
    artifact set of the state it lands, so EVERY `implemented -> spec_ok`
    verifier reject rewrites spec.yaml with the rig's placeholder — the base
    document is restored after each one, and `_assert_escalated` fails loudly
    if a placeholder ever survives into the comparison. (2) The fake's happy
    edge out of `spec_ok` is `implemented`, so the re-spec call itself lands
    `worker/` files; the third case deletes the dir after that write and
    narrows the fake's own artifact declarations to match.
  * Group C's skip is pinned as "the three expensive legs are not reached", and
    the negative control is the same drive WITHOUT a marker, which must reach
    `build_payload`. What the runner returns on the skip is pinned as §4's own
    success edge for S2 (`ok`, `to_state == "implemented"`), because
    `_work_slot` raises on any other `to_state` from a successful S2.
  * Group C does NOT pin what happens to a marker whose `to_spec` no longer
    matches the spec on disk. "Single-shot" is contracted; freshness is not.
    RECORDED GAP — if the intended behaviour is "a stale marker is ignored AND
    removed", that is a contract line to add, and this file has the harness to
    pin it in three more lines.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from gen import orchestrator as orch
from gen import s1_spec
from gen import s2_implement as s2_module
from gen import worker as worker_module

# The b11 fake-runner rig and h6's escalation rig (imported, never copied — see
# the module docstring). Fixtures have to be re-bound here, because pytest
# resolves a fixture by looking up that name in the REQUESTING module.
from gen.tests import test_b11_pipeline as b11
from gen.tests import test_r2_hotfix6 as h6

_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched
batch_home = b11.batch_home
make_cfg = b11.make_cfg

#: the contract's own spelling for the marker (see the readings above).
MARKER_SUFFIX = ".decl-only-respec.json"

#: the committed worker pair group C plants — never a live pilot worker.
TOY = Path(__file__).resolve().parent / "toy_worker"

#: an instantly-green `make validate`, so a consume path that re-validates the
#: planted worker finds it green without running the template's real gates.
GREEN_MAKEFILE = 'validate:\n\t@echo "validate: GREEN"\n'

SLUG = h6.REQUIRED_SLUG


# --------------------------------------------------------------------------
# helpers — spec documents (the B5 fixture with ONE thing changed)
# --------------------------------------------------------------------------


def _base_doc() -> dict:
    return yaml.safe_load(h6._good_text())


def _dump(doc) -> bytes:
    return yaml.safe_dump(doc, sort_keys=False).encode("utf-8")


def _mutate(change, *, sort_keys: bool = False) -> bytes:
    """The fixture spec with `change` applied to its `game` block."""
    doc = _base_doc()
    change(doc["game"])
    return yaml.safe_dump(doc, sort_keys=sort_keys).encode("utf-8")


BASE = _dump(_base_doc())


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _projection():
    """`s1_spec.impl_projection`, resolved late so this file COLLECTS before
    the implementation lands (and fails one named test, not the module)."""
    fn = getattr(s1_spec, "impl_projection", None)
    assert fn is not None, (
        "gen.s1_spec must expose `impl_projection(spec_yaml_bytes: bytes) -> str`; "
        f"it exposes {[n for n in dir(s1_spec) if 'project' in n.lower()]!r}"
    )
    return fn


def _proj(raw: bytes) -> str:
    return _projection()(raw)


# Declaration-only edits: `game.terms` and `game.knobs.deceptions`, present,
# absent, reordered, renamed. None of these may move the projection.
def _terms_reordered(game) -> None:
    game["terms"] = list(reversed(game["terms"]))


def _terms_renamed(game) -> None:
    game["terms"][1] = "terrain.teleport"


def _terms_widened(game) -> None:
    game["terms"] = [*game["terms"], "budget.cap"]


def _terms_absent(game) -> None:
    del game["terms"]


def _deceptions_declared(game) -> None:
    game["knobs"]["deceptions"] = ["false tell"]


def _deceptions_absent(game) -> None:
    del game["knobs"]["deceptions"]


def _both_changed(game) -> None:
    _terms_widened(game)
    _deceptions_declared(game)


def _both_absent(game) -> None:
    _terms_absent(game)
    _deceptions_absent(game)


DECL_ONLY_EDITS = (
    ("terms-reordered", _terms_reordered),
    ("terms-renamed", _terms_renamed),
    ("terms-widened", _terms_widened),
    ("terms-absent", _terms_absent),
    ("deceptions-declared", _deceptions_declared),
    ("deceptions-absent", _deceptions_absent),
    ("both-changed", _both_changed),
    ("both-absent", _both_absent),
)


# Implementation-visible edits: every one of these MUST move the projection.
def _level_sketch(game) -> None:
    game["levels"][0]["sketch"] = game["levels"][0]["sketch"] + " A third junction is added."


def _knobs_refusal(game) -> None:
    game["knobs"]["refusal"] = "free"


def _palette_you(game) -> None:
    game["palette"]["you"] = 5


def _actions(game) -> None:
    game["actions"]["ACTION7"] = "declared"


def _layout_seed(game) -> None:
    game["layout"]["seed"] = game["layout"]["seed"] + 1


def _terms_and_sketch(game) -> None:
    _terms_widened(game)
    _level_sketch(game)


IMPL_EDITS = (
    ("level-sketch", _level_sketch),
    ("knobs-refusal", _knobs_refusal),
    ("palette-you", _palette_you),
    ("actions", _actions),
    ("layout-seed", _layout_seed),
    ("terms-and-sketch", _terms_and_sketch),
)

#: the two re-specs the rig drives: one the marker is FOR, one it is not.
DECL_ONLY_SPEC = _mutate(_both_changed)
ALSO_A_LEVEL_SPEC = _mutate(_terms_and_sketch)

#: a leftover from an earlier decl-only round, planted to be swept.
STALE_MARKER = json.dumps(
    {"from_spec": "0" * 64, "to_spec": "1" * 64, "ts": "2026-01-01T00:00:00Z",
     "note": "stale marker planted by test_r2_hotfix9"},
    indent=2,
).encode("utf-8") + b"\n"


# --------------------------------------------------------------------------
# helpers — the marker on disk
# --------------------------------------------------------------------------


def _markers(home) -> list[Path]:
    """Every `*.decl-only-respec.json` anywhere under the rig's batch home."""
    return sorted(Path(home).rglob("*" + MARKER_SUFFIX))


def _worker_dir(ctx) -> Path | None:
    """`ctx.worker_dir`, or the §2 convention when the ctx has no property."""
    worker = getattr(ctx, "worker_dir", None)
    if worker is not None:
        return Path(worker)
    spec_dir = getattr(ctx, "spec_dir", None)
    return None if spec_dir is None else Path(spec_dir) / orch.WORKER_DIRNAME


def _sibling(worker: Path) -> Path:
    return worker.with_name(worker.name + MARKER_SUFFIX)


# --------------------------------------------------------------------------
# helpers — the orchestrator rig (h6's group 3, scripted to rewrite spec.yaml)
# --------------------------------------------------------------------------


class _RespecRunners(h6._WatchingRunners):
    """h6's escalation rig + the one thing it has no reason to do on its own:
    make the fake S1 write a REAL spec document, and a different one on the
    escalated re-spec.

    The rig's own fake S1 writes `# fake spec_ok artifact / slug: / revision:`,
    and on the re-spec it writes nothing at all (the ctx's state is `spec_ok`,
    so its happy edge lands `implemented` artifacts). Both halves of the
    comparison `_maybe_respec` makes are therefore written HERE: the base
    document on the call that lands `spec_ok`, the re-spec document on the call
    that carries an escalation.
    """

    def __init__(self, journal, cfg, home, *, outcomes=None, report=None,
                 respec_bytes: bytes, base_bytes: bytes = BASE,
                 stale: bytes | None = None, drop_worker: bool = False,
                 fail_respec: bool = False) -> None:
        self._home = Path(home)
        self._base_bytes = base_bytes
        self._respec_bytes = respec_bytes
        self._stale = stale
        self._drop_worker = drop_worker
        self._fail_respec = fail_respec
        #: one row per stage call: the markers on disk AS IT WAS ENTERED.
        self.entries: list[dict] = []
        self.respec_calls: list[int] = []
        self.stale_planted: list[Path] = []
        self.dropped: list[Path] = []
        #: the spec.yaml bytes on disk as the escalated re-spec began — i.e.
        #: the OLD half of the comparison `_maybe_respec` makes.
        self.old_spec: list[bytes] = []
        super().__init__(journal, cfg, outcomes=outcomes, report=report)

    def _make(self, stage: str):
        inner = super()._make(stage)

        def runner(ctx):
            escalated = h6._escalation_of(ctx) not in (None, h6._MISSING)
            self.entries.append({
                "n": len(self._journal.calls) + 1,
                "stage": stage,
                "escalated": escalated,
                "markers": [str(path) for path in _markers(self._home)],
            })
            if escalated:
                self.respec_calls.append(self.entries[-1]["n"])
                self._before_respec(ctx)
            result = inner(ctx)
            if escalated:
                # The new bytes land even when the re-spec then FAILS: the
                # real S1 writes its four artifacts on a lint kill too, so
                # "the spec changed" and "the re-spec succeeded" are two
                # different facts, and only the second licenses a marker.
                self._write_spec(ctx, self._respec_bytes)
                result = self._after_respec(ctx, result)
                if self._fail_respec:
                    result = {**result, "ok": False, "to_state": "respec",
                              "reason": "fake s1_spec: lint kill on the re-spec"}
            elif result.get("to_state") == "spec_ok":
                # EVERY call that lands `spec_ok` — S1's happy edge AND each
                # scripted verifier reject, which rides `implemented ->
                # spec_ok` — rewrites the rig's placeholder spec.yaml. The
                # base document is restored after each of them, so what
                # `_maybe_respec` reads as "the old spec" is a real one.
                self._write_spec(ctx, self._base_bytes)
            return result

        return runner

    def _before_respec(self, ctx) -> None:
        """Record the OLD spec and plant the stale marker, BEFORE S1 re-runs —
        i.e. before `_maybe_respec` can decide anything about either."""
        spec_dir = getattr(ctx, "spec_dir", None)
        if spec_dir is not None and (Path(spec_dir) / "spec.yaml").is_file():
            self.old_spec.append((Path(spec_dir) / "spec.yaml").read_bytes())
        worker = _worker_dir(ctx)
        if worker is None:
            return
        if self._stale is not None:
            marker = _sibling(worker)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(self._stale)
            self.stale_planted.append(marker)

    def _after_respec(self, ctx, result: dict) -> dict:
        """Drop the worker dir AFTER the fake S1 wrote, before `_maybe_respec`
        decides. The real S1 writes spec artifacts only; this rig's fake lands
        `implemented` artifacts on the re-spec call (its ctx state is
        `spec_ok`), which would re-create the very dir this case removes — and
        then `_check_artifacts` would fail the run for declaring a file that is
        no longer there, so the fake's own declarations are narrowed to what
        survives. Nothing the contract is about is touched by either.
        """
        worker = _worker_dir(ctx)
        if not self._drop_worker or worker is None or not worker.is_dir():
            return result
        shutil.rmtree(worker)
        self.dropped.append(worker)
        artifacts = {
            name: path
            for name, path in (result.get("artifacts") or {}).items()
            if Path(path).exists()
        }
        return {**result, "artifacts": artifacts}

    def _write_spec(self, ctx, raw: bytes) -> None:
        slug = b11._ctx_slug(ctx) or ""
        dirs = list(self._slot_dirs(ctx, slug))
        spec_dir = getattr(ctx, "spec_dir", None)
        if spec_dir is not None and Path(spec_dir) not in dirs:
            dirs.append(Path(spec_dir))
        for slot_dir in dirs:
            slot_dir.mkdir(parents=True, exist_ok=True)
            (slot_dir / "spec.yaml").write_bytes(raw)


def _drive(make_cfg, home, batch_id: str, **kwargs):
    """h6's escalation script: verifier rejects to the cap, then the re-spec."""
    cfg, _path = make_cfg(batch_id)
    journal = b11._Journal()
    runners = _RespecRunners(
        journal,
        cfg,
        home,
        outcomes={
            "implemented": b11._Outcome(
                "spec_ok",
                "verifier reject: undeclared deception",
                times=orch.VERIFIER_REJECT_CAP_ESCALATE,
            )
        },
        report=h6.REPORT,
        **kwargs,
    )
    report = b11._advance(cfg, runners)
    return cfg, journal, runners, report


def _assert_escalated(runners) -> int:
    assert runners.respec_calls, (
        "the rig never escalated, so no re-spec ran and nothing in this test is about the "
        f"marker: {[(e['n'], e['stage'], e['escalated']) for e in runners.entries]}"
    )
    assert len(runners.respec_calls) == 1, (
        f"exactly one re-spec is escalated here, got calls {runners.respec_calls}"
    )
    # The rig rewrites spec.yaml on EVERY `spec_ok` landing (S1's happy edge
    # and each verifier reject alike). If one of those placeholders survives
    # into the re-spec, `_maybe_respec` compares against a document this test
    # never chose, and every assertion below would be about the wrong thing.
    assert runners.old_spec == [runners._base_bytes], (
        "the spec.yaml the re-spec started from is not the planted base document — the rig "
        f"clobbered it (read {len(runners.old_spec[0]) if runners.old_spec else 0} bytes)"
    )
    return runners.respec_calls[0]


# --------------------------------------------------------------------------
# helpers — group C's unit drive (a real corpus slot in tmp_path)
# --------------------------------------------------------------------------


class _Reached(Exception):
    """Raised by a leg of S2 that a consumed marker must skip."""


def _boom(name: str):
    def forbidden(*args, **kwargs):
        raise _Reached(f"S2 reached {name}() — a consumed decl-only marker skips it")

    return forbidden


def _plant_worker(spec_dir: Path) -> Path:
    """A green-validating worker beside the spec, as S2 and S2b left it.

    The manifest is BUILT from the planted tree (not hand-written), so a
    consume path that calls `verify_worker` finds it clean; `make validate` is
    an echo, so a consume path that re-validates finds it green.
    """
    worker = spec_dir / orch.WORKER_DIRNAME
    worker.mkdir(parents=True)
    shutil.copy2(TOY / "game.py", worker / "game.py")
    shutil.copy2(TOY / "solver.py", worker / "solver.py")
    (worker / "Makefile").write_text(GREEN_MAKEFILE, encoding="utf-8")
    manifest = json.dumps(worker_module.build_manifest(worker), indent=2, sort_keys=True) + "\n"
    (worker / worker_module.MANIFEST_NAME).write_text(manifest, encoding="utf-8")
    worker.with_name(worker.name + ".manifest.json").write_text(manifest, encoding="utf-8")
    # the previous green implementation's report — S2's own sidecar
    worker.with_name(worker.name + s2_module.REPORT_SUFFIX).write_text(
        json.dumps({"green": True, "attempts": 1}, indent=2) + "\n", encoding="utf-8"
    )
    assert worker_module.verify_worker(worker) == [], (
        "the planted worker must be scope-clean to start with"
    )
    if shutil.which("make") is not None:
        exit_code, tail = s2_module._run_validate(worker)
        assert exit_code == 0, f"the planted worker must validate green, got {exit_code}: {tail}"
    return worker


def _plant_slot(tmp_path: Path, spec_bytes: bytes) -> tuple[Path, Path]:
    spec_dir = tmp_path / "corpus" / h6.BATCH_ID / SLUG
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.yaml").write_bytes(spec_bytes)
    (spec_dir / "idea.json").write_text(
        json.dumps({"id": "b001-pilot-i001", "slug": SLUG}, indent=2) + "\n", encoding="utf-8"
    )
    return spec_dir, _plant_worker(spec_dir)


def _unit_ctx(tmp_path: Path, spec_dir: Path):
    """The ctx §4 hands S2 at `spec_ok`, built entirely under `tmp_path`."""
    ideas = tmp_path / "ideas" / h6.BATCH_ID
    ideas.mkdir(parents=True, exist_ok=True)
    idea_path = ideas / "idea-001.json"
    idea_path.write_text(
        json.dumps({"id": "b001-pilot-i001", "slug": SLUG}, indent=2) + "\n", encoding="utf-8"
    )
    return orch.SlotContext(
        cfg=h6._cfg(),
        batch_id=h6.BATCH_ID,
        slug=SLUG,
        index=1,
        state="spec_ok",
        stage="s2_implement",
        attempt=1,
        batch_dir=tmp_path / "batches" / h6.BATCH_ID,
        ideas_dir=ideas,
        idea_path=idea_path,
        corpus_dir=spec_dir.parent,
        spec_dir=spec_dir,
        respec_count=0,
        verifier_rejects=orch.VERIFIER_REJECT_CAP_ESCALATE,
        green_failures=0,
        history=(),
    )


def _s2_runner():
    runners = orch.default_runners()
    assert "s2_implement" in runners, (
        f"default_runners() must key S2 as 's2_implement'; it has {sorted(runners)}"
    )
    return runners["s2_implement"]


def _forbid_the_expensive_legs(monkeypatch) -> None:
    """The three legs an honoured marker skips. Every one is imported INSIDE
    the runner, so patching the module attribute is what the runner sees."""
    monkeypatch.setattr(s2_module, "build_payload", _boom("build_payload"))
    monkeypatch.setattr(s2_module, "green_loop", _boom("green_loop"))
    monkeypatch.setattr(worker_module, "instantiate_worker", _boom("instantiate_worker"))


# --------------------------------------------------------------------------
# A: `impl_projection` — the same game, whatever it declares
# --------------------------------------------------------------------------


def test_s1_spec_exposes_impl_projection():
    fn = _projection()
    assert callable(fn), f"`impl_projection` must be callable, got {type(fn).__name__}"


@pytest.mark.parametrize(
    "edit", [e[1] for e in DECL_ONLY_EDITS], ids=[e[0] for e in DECL_ONLY_EDITS]
)
def test_a_declaration_only_edit_does_not_move_the_projection(edit):
    """A.1/A.3: terms and deceptions — present, absent, reordered, renamed."""
    changed = _mutate(edit)
    assert changed != BASE, "fixture drift: this edit changed nothing in the document"
    assert _proj(changed) == _proj(BASE), (
        "the projection must not see `game.terms` / `game.knobs.deceptions`: this edit touched "
        "only those, and the two documents project differently"
    )


@pytest.mark.parametrize("edit", [e[1] for e in IMPL_EDITS], ids=[e[0] for e in IMPL_EDITS])
def test_any_other_edit_moves_the_projection(edit):
    """A.2: a level sketch, knobs.refusal, palette.you, actions, layout.seed."""
    changed = _mutate(edit)
    assert changed != BASE, "fixture drift: this edit changed nothing in the document"
    assert _proj(changed) != _proj(BASE), (
        "this edit changes what the implementation has to be, so the projection must move — "
        "an equal projection here would let a real re-spec skip its re-implement"
    )


def test_absent_declarations_project_as_the_document_without_them():
    """A.3 stated as an identity, not as tolerance alone."""
    stripped = _mutate(_both_absent)
    doc = _base_doc()
    assert "terms" in doc["game"] and "deceptions" in doc["game"]["knobs"], "fixture drift"
    assert _proj(stripped) == _proj(BASE)
    assert _proj(stripped) == _proj(_mutate(_terms_absent)) == _proj(_mutate(_deceptions_absent))


def test_key_order_does_not_move_the_projection():
    """Canonical json sorts keys (the house `_digest` shape). RENEGOTIABLE."""
    sorted_dump = _mutate(lambda game: None, sort_keys=True)
    assert sorted_dump != BASE, "fixture drift: sorting the keys changed no bytes"
    assert _proj(sorted_dump) == _proj(BASE), (
        "the same document dumped in a different key order projects differently — if the "
        "implementation deliberately digests in document order, THIS is the line to renegotiate"
    )


def test_a_mapping_without_a_game_block_still_projects():
    """The rig's own spec.yaml has no `game` key, and h6's group 3 drives
    `_maybe_respec` over it. Only a NON-mapping is contracted to raise."""
    raw = b"# fake spec_ok artifact\nslug: fogbound-switchyard\nrevision: 1\n"
    digest = _proj(raw)
    assert re.fullmatch(r"[0-9a-f]{64}", digest), digest


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"game: {unclosed\n", id="unclosed-flow-mapping"),
        pytest.param(b"game:\n\tterms: [a]\n", id="tab-indent"),
        pytest.param(b"a: 1\n- b\n", id="mixed-node-kinds"),
        pytest.param(b"\xff\xfe\x00game\n", id="not-utf8"),
        pytest.param(b"- one\n- two\n", id="sequence-document"),
        pytest.param(b"42\n", id="scalar-document"),
        pytest.param(b"just some prose\n", id="string-document"),
        pytest.param(b"", id="empty-document"),
    ],
)
def test_malformed_or_non_mapping_bytes_raise_value_error(raw):
    """A.4. `yaml.YAMLError` is NOT a ValueError, so this has to be wrapped."""
    with pytest.raises(ValueError):
        _proj(raw)


def test_the_projection_is_a_deterministic_lowercase_hex_digest():
    """A.5."""
    first, second = _proj(BASE), _proj(BASE)
    assert first == second, f"same bytes, two digests: {first} != {second}"
    assert isinstance(first, str), f"a digest is a str, got {type(first).__name__}"
    assert re.fullmatch(r"[0-9a-f]{64}", first), (
        f"contracted as a 64-char lowercase sha256 hex string, got {first!r}"
    )


# --------------------------------------------------------------------------
# B: `_maybe_respec` — the marker, written only for a declaration-only re-spec
# --------------------------------------------------------------------------


def test_the_orchestrator_names_the_marker_suffix():
    suffix = getattr(orch, "DECL_ONLY_MARKER_SUFFIX", None)
    assert suffix == MARKER_SUFFIX, (
        f"`orchestrator.DECL_ONLY_MARKER_SUFFIX` must be {MARKER_SUFFIX!r}, got {suffix!r} — "
        "every glob in this file searches for that literal"
    )


def test_a_declaration_only_respec_writes_the_worker_sibling_marker(make_cfg, batch_home):
    """B, case 1: the re-spec changed the bytes but not the game."""
    assert DECL_ONLY_SPEC != BASE, "fixture drift: the re-spec must change spec.yaml's bytes"
    assert _proj(DECL_ONLY_SPEC) == _proj(BASE), "fixture drift: this case IS declaration-only"

    _cfg, _journal, runners, _report = _drive(
        make_cfg, batch_home, "r2h9-declonly", respec_bytes=DECL_ONLY_SPEC
    )
    respec_at = _assert_escalated(runners)

    markers = _markers(batch_home)
    assert len(markers) == 1, (
        f"a declaration-only re-spec writes exactly one marker; found {[str(m) for m in markers]}"
    )
    marker = markers[0]

    # worker-SIBLING: the worker's parent, named after the worker dir.
    worker = marker.with_name(marker.name[: -len(MARKER_SUFFIX)])
    assert worker.name == orch.WORKER_DIRNAME, (
        f"the marker must be named `{orch.WORKER_DIRNAME}{MARKER_SUFFIX}` beside the worker, "
        f"got {marker.name!r}"
    )
    assert worker.is_dir(), f"the marker's worker sibling is not a dir: {worker}"
    assert (marker.parent / "spec.yaml").read_bytes() == DECL_ONLY_SPEC, (
        "the marker must sit beside the spec the re-spec just wrote"
    )

    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload.get("to_spec") == _sha(DECL_ONLY_SPEC), (
        "`to_spec` is the sha256 of the NEW spec.yaml bytes — that is what makes the marker "
        f"answerable to one spec; got {payload.get('to_spec')!r}"
    )
    assert payload.get("from_spec") == _sha(BASE), (
        f"`from_spec` is the sha256 of the spec that was replaced; got {payload.get('from_spec')!r}"
    )
    ts = payload.get("ts")
    assert isinstance(ts, str) and ts.strip(), f"the marker must carry a `ts`, got {ts!r}"

    # ordering: nothing before the re-spec wrote it, and S2 was entered with it.
    before = [e for e in runners.entries if e["n"] <= respec_at]
    assert all(not e["markers"] for e in before), (
        f"a marker existed before the re-spec ran: {[(e['n'], e['markers']) for e in before]}"
    )
    after = [e for e in runners.entries if e["n"] > respec_at]
    assert after, "no stage ran after the re-spec, so nothing could consume the marker"
    assert str(marker) in after[0]["markers"], (
        f"the marker must be on disk when the next stage ({after[0]['stage']!r}) is entered — "
        f"it saw {after[0]['markers']}"
    )


def test_a_respec_that_also_changes_a_level_writes_no_marker_and_sweeps_a_stale_one(
    make_cfg, batch_home
):
    """B, case 2: the game changed, so the implementation must be redone."""
    assert _proj(ALSO_A_LEVEL_SPEC) != _proj(BASE), (
        "fixture drift: this case is NOT declaration-only"
    )

    _cfg, _journal, runners, _report = _drive(
        make_cfg, batch_home, "r2h9-level", respec_bytes=ALSO_A_LEVEL_SPEC, stale=STALE_MARKER
    )
    _assert_escalated(runners)
    assert runners.stale_planted, "the test planted no stale marker, so it proves nothing"

    markers = _markers(batch_home)
    assert markers == [], (
        "a re-spec that changed a level must leave NO marker behind — a stale one would skip "
        f"the re-implement of a game that really did change: {[str(m) for m in markers]}"
    )
    for stale in runners.stale_planted:
        assert not stale.exists(), f"the stale marker was left on disk: {stale}"


def test_no_marker_when_the_respec_itself_failed(make_cfg, batch_home):
    """B's first word: the marker follows a SUCCESSFUL re-spec. A killed
    rewrite has changed the bytes too, and must license nothing."""
    assert _proj(DECL_ONLY_SPEC) == _proj(BASE), "fixture drift: this case IS declaration-only"

    _cfg, _journal, runners, report = _drive(
        make_cfg, batch_home, "r2h9-failed", respec_bytes=DECL_ONLY_SPEC, fail_respec=True
    )
    _assert_escalated(runners)
    assert h6._only_slot(report)["blocked"], (
        "a failed re-spec blocks the slot (§4 draws no edge from spec_ok to respec); this run "
        f"ended at {h6._only_slot(report)['state']!r} instead"
    )

    markers = _markers(batch_home)
    assert markers == [], (
        "the re-spec failed, so there is no new spec to vouch for and no marker may exist: "
        f"{[str(m) for m in markers]}"
    )


def test_no_marker_when_the_worker_dir_is_gone(make_cfg, batch_home):
    """B's second conjunct: no implementation to keep, no marker."""
    assert _proj(DECL_ONLY_SPEC) == _proj(BASE), "fixture drift: this case IS declaration-only"

    _cfg, _journal, runners, _report = _drive(
        make_cfg, batch_home, "r2h9-noworker", respec_bytes=DECL_ONLY_SPEC, drop_worker=True
    )
    _assert_escalated(runners)
    assert runners.dropped, "the test never removed a worker dir, so it proves nothing"

    respec_at = runners.respec_calls[0]
    after = [e for e in runners.entries if e["n"] > respec_at]
    assert after, "no stage ran after the re-spec"
    assert not after[0]["markers"], (
        "the worker dir was gone when the re-spec ran, so there was no implementation to keep "
        f"and no marker to write: {after[0]['markers']}"
    )


# --------------------------------------------------------------------------
# C: the S2 stage — single-shot consume, and the skip it buys
# --------------------------------------------------------------------------
# UNIT form (see the module docstring): `run_batch` REPLACES its runner table,
# so the rig above can never reach the real S2 runner. These two drive it.


def test_the_real_s2_runner_consumes_the_marker_and_skips_the_re_implement(tmp_path, monkeypatch):
    """C: the marker is taken (once) and the three expensive legs never run."""
    spec_dir, worker = _plant_slot(tmp_path, DECL_ONLY_SPEC)
    marker = _sibling(worker)
    marker.write_text(
        json.dumps(
            {
                "from_spec": _sha(BASE),
                "to_spec": _sha(DECL_ONLY_SPEC),
                "ts": "2026-09-23T00:00:00Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _forbid_the_expensive_legs(monkeypatch)

    result = _s2_runner()(_unit_ctx(tmp_path, spec_dir))

    assert not marker.exists(), (
        "the marker is SINGLE-SHOT: S2 must consume it, or the next escalated round would skip "
        f"a re-implement it never decided about — {marker} is still on disk"
    )
    assert result["ok"] is True, f"a consumed marker means S2 succeeded, got {result!r}"
    assert result["to_state"] == "implemented", (
        "`_work_slot` raises on any other to_state out of a successful S2 "
        f"(STAGE_SUCCESS), got {result['to_state']!r}"
    )
    assert isinstance(result.get("reason"), str) and result["reason"].strip(), (
        f"every runner result carries a non-empty reason, got {result.get('reason')!r}"
    )
    assert (worker / "game.py").read_bytes() == (TOY / "game.py").read_bytes(), (
        "the skipped re-implement must leave the audited game byte-identical"
    )
    assert (worker / "solver.py").read_bytes() == (TOY / "solver.py").read_bytes(), (
        "the skipped re-implement must leave the audited solver byte-identical"
    )
    assert not (spec_dir / "payload.md").exists(), (
        "a skipped re-implement builds no payload, so it writes none beside the spec"
    )


def test_a_consumed_marker_survives_a_cleared_implement_report(tmp_path, monkeypatch):
    """C: the report is a per-run verdict file — `green_loop` unlinks stale
    ones up front — so a loop interrupted between that clear and its first
    green legally leaves NONE behind. The decl-only hop runs no loop to
    rewrite one, so it must not cite the report as a §4 artifact then; doing
    so crashed g20261001-5's live resume (2026-10-05) at `_check_artifacts`."""
    spec_dir, worker = _plant_slot(tmp_path, DECL_ONLY_SPEC)
    report = worker.with_name(worker.name + s2_module.REPORT_SUFFIX)
    report.unlink()  # the interrupted prior loop's exact on-disk state
    marker = _sibling(worker)
    marker.write_text(
        json.dumps(
            {
                "from_spec": _sha(BASE),
                "to_spec": _sha(DECL_ONLY_SPEC),
                "ts": "2026-09-23T00:00:00Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _forbid_the_expensive_legs(monkeypatch)

    result = _s2_runner()(_unit_ctx(tmp_path, spec_dir))

    assert result["ok"] is True and result["to_state"] == "implemented", (
        f"a consumed marker over a green worker means S2 succeeded, got {result!r}"
    )
    assert "implement_report" not in result["artifacts"], (
        "no loop ran and no report exists — citing one here is the crash this test pins: "
        f"{result['artifacts']}"
    )
    # the §4 gate itself, the exact call the live resume died in
    orch._check_artifacts("s2_implement", result)


def test_a_consumed_marker_still_cites_a_surviving_implement_report(tmp_path, monkeypatch):
    """C's counterpart: when the previous loop's report IS on disk it rides the
    artifact map as before — the fix narrows the claim, it does not drop it."""
    spec_dir, worker = _plant_slot(tmp_path, DECL_ONLY_SPEC)
    report = worker.with_name(worker.name + s2_module.REPORT_SUFFIX)
    assert report.is_file(), "_plant_worker leaves the previous green report in place"
    marker = _sibling(worker)
    marker.write_text(
        json.dumps(
            {
                "from_spec": _sha(BASE),
                "to_spec": _sha(DECL_ONLY_SPEC),
                "ts": "2026-09-23T00:00:00Z",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _forbid_the_expensive_legs(monkeypatch)

    result = _s2_runner()(_unit_ctx(tmp_path, spec_dir))

    assert result["ok"] is True and result["to_state"] == "implemented"
    assert result["artifacts"].get("implement_report") == report, (
        f"the surviving report is still the cited artifact, got {result['artifacts']}"
    )
    orch._check_artifacts("s2_implement", result)


def test_without_a_marker_the_real_s2_runner_still_does_the_work(tmp_path, monkeypatch):
    """C's negative control: the skip is marker-gated, not unconditional."""
    spec_dir, worker = _plant_slot(tmp_path, DECL_ONLY_SPEC)
    assert not _sibling(worker).exists(), "this drive plants no marker"
    _forbid_the_expensive_legs(monkeypatch)

    with pytest.raises(_Reached) as excinfo:
        _s2_runner()(_unit_ctx(tmp_path, spec_dir))
    assert "build_payload" in str(excinfo.value), (
        f"S2 with no marker must go build its payload and implement; it stopped at {excinfo.value}"
    )


def test_the_marker_is_single_shot_across_two_s2_drives(tmp_path, monkeypatch):
    """C, restated as the invariant that matters on a re-run: drive S2 TWICE
    over one planted marker — the second drive must do the work."""
    spec_dir, worker = _plant_slot(tmp_path, DECL_ONLY_SPEC)
    _sibling(worker).write_text(
        json.dumps({"from_spec": _sha(BASE), "to_spec": _sha(DECL_ONLY_SPEC), "ts": "t"}) + "\n",
        encoding="utf-8",
    )
    _forbid_the_expensive_legs(monkeypatch)
    ctx = _unit_ctx(tmp_path, spec_dir)

    first = _s2_runner()(ctx)
    assert first["ok"] is True and first["to_state"] == "implemented", first
    with pytest.raises(_Reached):
        _s2_runner()(ctx)


# --------------------------------------------------------------------------
# D: the no-op — a run that never escalated writes no marker at all
# --------------------------------------------------------------------------


def test_a_plain_happy_run_writes_no_marker_anywhere(make_cfg, batch_home):
    cfg, _path = make_cfg("r2h9-happy")
    journal = b11._Journal()
    runners = b11._Runners(journal, cfg)
    b11._advance(cfg, runners)

    assert journal.calls, "the happy run invoked no stage at all"
    markers = _markers(batch_home)
    assert markers == [], (
        "nothing escalated in this run, so no re-spec happened and no marker may exist: "
        f"{[str(m) for m in markers]}"
    )
