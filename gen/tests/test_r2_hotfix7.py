"""R2 hotfix #7 acceptance: an escalated re-spec survives its own lint kill.

Run: .venv/bin/python -m pytest gen/tests/test_r2_hotfix7.py -v

The incident (R2, night of 2026-09-22): the FIRST findings-fed escalation
declared every flagged lever and pinned the slug — and then lint-killed on two
one-line misses (a dropped mandatory `layers` field + one undeclared sketch
word), and because run_s1 writes in place, the KILLED rewrite evicted the
live, ledger-pinned spec beside the green worker. Two behaviors fix that:

  * ONE corrective retry on an escalated lint kill (the kill details go back
    to the writer verbatim), the same one-retry idiom as the slug and
    malformed-reply paths.
  * WRITE-THROUGH-STAGING: a rewrite whose FINAL verdict is still a kill
    lands under `.killed/<slug>-respec-<stamp>/` as evidence; the live dir's
    bytes are untouched.

Lead-authored (operator-approved direct patch), reusing test_r2_hotfix6's
planted-corpus/stub-writer scaffolding by import (the b11-rig precedent).
Renegotiable readings: the corrective prompt is pinned by SUBSTRINGS (the
kill's rule name and the dropped field), not by LINT_KILL_REMINDER's exact
text; "evidence dir" is pinned as `.killed/` + the slug + "-respec-" in the
name, not an exact stamp.
"""

from __future__ import annotations

import json
from pathlib import Path

from gen.s1_spec import KILLED_DIRNAME, run_s1
from gen.tests import test_r2_hotfix6 as h6

_cfg = h6._cfg
IDEA_PATH = h6.IDEA_PATH
BATCH_ID = h6.BATCH_ID
REQUIRED_SLUG = h6.REQUIRED_SLUG


def _killed_text() -> str:
    """h6's passing spec with the `layers` line removed — the exact schema
    kill the pilot's escalation died on ("game.layers: missing")."""
    lines = [l for l in h6._good_text().splitlines() if not l.strip().startswith("layers:")]
    text = "\n".join(lines)
    assert text != h6._good_text(), "fixture: the layers line must actually be removed"
    return text


def test_a_lint_killed_escalated_rewrite_gets_one_corrective_retry(tmp_path):
    """Kill on turn 1, clean on turn 2: the retry prompt names the kill, the
    pass lands in the live dir, the audited files survive."""
    planted = h6._plant_corpus(tmp_path)
    before = {n: planted[n].read_bytes() for n in ("game", "solver", "report")}
    log: list[str] = []

    result = run_s1(
        IDEA_PATH,
        _cfg(),
        writer_runner=h6._writer([h6._reply(_killed_text()), h6._reply(h6._good_text())], log),
        out_root=tmp_path,
        escalation=planted["report"],
    )

    assert len(log) == 2, f"one kill buys exactly one corrective turn, got {len(log)} calls"
    assert "layers" in log[1] and "schema" in log[1], (
        "the corrective turn must carry the kill verbatim (rule + the dropped field); "
        f"the retry prompt's tail was: {log[1][-300:]!r}"
    )
    assert result.report.passed, "the corrected rewrite must stand as the verdict"
    assert Path(result.out_dir).resolve() == planted["corpus"].resolve(), (
        f"the corrected pass lands IN PLACE, got {result.out_dir}"
    )
    for name in ("game", "solver", "report"):
        assert planted[name].read_bytes() == before[name], f"{name} must survive byte-identical"
    assert json.loads((planted["corpus"] / "lint-report.json").read_text())["passed"] is True


def test_a_twice_killed_escalated_rewrite_never_evicts_the_live_spec(tmp_path):
    """THE TRAP PIN: both turns killed -> the live spec's bytes are untouched
    and the killed rewrite lands under .killed/ as evidence."""
    planted = h6._plant_corpus(tmp_path)
    live_spec_before = planted["spec"].read_bytes()
    log: list[str] = []

    result = run_s1(
        IDEA_PATH,
        _cfg(),
        writer_runner=h6._writer([h6._reply(_killed_text()), h6._reply(_killed_text())], log),
        out_root=tmp_path,
        escalation=planted["report"],
    )

    assert len(log) == 2, f"a second kill stands — no third turn; got {len(log)} calls"
    assert not result.report.passed, "the final verdict is the kill"

    assert planted["spec"].read_bytes() == live_spec_before, (
        "a killed escalated rewrite must NEVER replace the live spec — the ledger pins its "
        "hash and the worker implements it (the pilot lost exactly this spec once)"
    )
    out_dir = Path(result.out_dir)
    assert out_dir.parent.name == KILLED_DIRNAME and out_dir.parent.parent == planted[
        "corpus"
    ].parent, f"the killed rewrite is EVIDENCE under .killed/, got {out_dir}"
    assert out_dir.name.startswith(f"{REQUIRED_SLUG}-respec-"), out_dir.name
    assert json.loads((out_dir / "lint-report.json").read_text())["passed"] is False
    assert (out_dir / "spec.yaml").is_file(), "the killed rewrite itself is preserved"
    assert h6._dirs_under(tmp_path / BATCH_ID) == {REQUIRED_SLUG, KILLED_DIRNAME}, (
        "no second LIVE slot dir may appear: " f"{h6._dirs_under(tmp_path / BATCH_ID)}"
    )


def test_the_escalated_prompt_carries_the_terms_floor(tmp_path):
    """The union rule (oscillation fix): the existing spec's declared terms
    reach the rewrite prompt with the superset instruction — rounds 3-5
    oscillated because each rewrite evicted the standing declarations."""
    planted = h6._plant_corpus(tmp_path)
    planted["spec"].write_text(
        "game:\n  slug: fogbound-switchyard\n  terms: [goal.cover, info.fog, state.wait]\n",
        encoding="utf-8",
    )
    log: list[str] = []
    run_s1(
        IDEA_PATH,
        _cfg(),
        writer_runner=h6._writer([h6._reply(h6._good_text())], log),
        out_root=tmp_path,
        escalation=planted["report"],
    )
    prompt = log[0]
    for term in ("`goal.cover`", "`info.fog`", "`state.wait`"):
        assert term in prompt, f"the terms floor must name {term} verbatim; it is the memory " \
            "the oscillating rewrites were missing"
    assert "SUPERSET" in prompt, "the union rule must be stated as a superset requirement"
    assert "dead or unreachable" in prompt, (
        "the one legitimate removal (a finding saying the term is dead/unreachable) must be "
        "stated, or the floor would forbid the dead-spec-term fix"
    )


def test_the_escalated_prompt_carries_the_deceptions_floor_and_the_baseline(tmp_path):
    """Round 9's lessons: (a) the eviction disease has a deceptions axis — the
    floor must cover both; (b) a generative rewrite never holds the impl
    projection, so the prompt hands the writer the CURRENT spec.yaml verbatim
    as a byte-for-byte patch baseline."""
    planted = h6._plant_corpus(tmp_path)
    baseline_text = (
        "game:\n  slug: fogbound-switchyard\n  terms: [goal.cover]\n"
        "  knobs:\n    deceptions: ['look-alike junction pairs', 'false tell lamps']\n"
    )
    planted["spec"].write_text(baseline_text, encoding="utf-8")
    log: list[str] = []
    run_s1(
        IDEA_PATH,
        _cfg(),
        writer_runner=h6._writer([h6._reply(h6._good_text())], log),
        out_root=tmp_path,
        escalation=planted["report"],
    )
    prompt = log[0]
    assert "`look-alike junction pairs`" in prompt and "`false tell lamps`" in prompt, (
        "the deceptions floor must name the current levers verbatim"
    )
    assert "NEVER remove" in prompt, "the deceptions rule is additive-only"
    assert "byte-for-byte" in prompt, "the baseline directive must demand exact reproduction"
    assert baseline_text.strip() in prompt, (
        "the CURRENT spec.yaml must ride in the prompt verbatim as the patch baseline — "
        "without it the writer regenerates and the impl projection can never hold"
    )


def test_terms_introduced_is_declaration_class_for_the_projection():
    """The pilot's one live projection break: declaring a term forces it into
    a level's terms_introduced (§11 unknown-terms), so that row must be
    pruned too or the decl-only marker can never fire for a term addition."""
    from gen.s1_spec import impl_projection

    base = (
        "game:\n  slug: x\n  terms: [a.b]\n"
        "  levels:\n    - sketch: s1\n      terms_introduced: [a.b]\n"
        "    - sketch: s2\n      terms_introduced: []\n"
    )
    widened = (
        "game:\n  slug: x\n  terms: [a.b, c.d]\n"
        "  levels:\n    - sketch: s1\n      terms_introduced: [a.b]\n"
        "    - sketch: s2\n      terms_introduced: [c.d]\n"
    )
    sketch_moved = base.replace("sketch: s2", "sketch: s2-reworded")
    assert impl_projection(base.encode()) == impl_projection(widened.encode()), (
        "declaring a term + introducing it on a level is declaration-only and must hold "
        "the projection — this exact shape broke it live on 2026-09-23 ~06:27Z"
    )
    assert impl_projection(base.encode()) != impl_projection(sketch_moved.encode()), (
        "a reworded sketch is a REAL change and must still move the projection"
    )


def test_the_gate_report_defers_to_a_ledger_accept_of_identical_bytes(tmp_path):
    """The Phase-D block: verify overwrites the report file per round, so a
    latched accept can sit beside a stale later reject on disk — the gate
    must consume the ledger-senior verdict, with provenance recorded."""
    import types

    from gen.orchestrator import WORKER_DIRNAME, _game_hash, _gate_verifier_report

    spec_dir = tmp_path / "slot"
    worker = spec_dir / WORKER_DIRNAME
    worker.mkdir(parents=True)
    (worker / "game.py").write_text("G = 1\n", encoding="utf-8")
    (worker / "solver.py").write_text("S = 1\n", encoding="utf-8")
    current = _game_hash(worker)

    def ctx_with(history):
        return types.SimpleNamespace(spec_dir=spec_dir, history=tuple(history))

    accept = {"from": "implemented", "to": "verified",
              "hashes": {"game": current, "spec": "s" * 64, "stage_input": None},
              "ts": "2026-09-23T07:03:40+00:00"}
    stale_reject = {"verdict": "reject", "reject_reasons": [{"code": "undeclared-term"}]}

    out = _gate_verifier_report(ctx_with([accept]), dict(stale_reject))
    assert out["verdict"] == "pass" and out["ledger_latch"]["overridden_disk_verdict"] == "reject"
    assert "senior" in out["ledger_latch"]["note"]

    foreign = dict(accept, hashes={"game": "0" * 64, "spec": None, "stage_input": None})
    assert _gate_verifier_report(ctx_with([foreign]), dict(stale_reject))["verdict"] == "reject", (
        "an accept of DIFFERENT bytes must not override a reject"
    )
    assert _gate_verifier_report(ctx_with([]), dict(stale_reject))["verdict"] == "reject", (
        "no recorded accept -> the on-disk reject stands"
    )
    clean = {"verdict": "pass"}
    assert _gate_verifier_report(ctx_with([]), dict(clean)) == clean, (
        "an on-disk accept passes through untouched"
    )


def test_a_non_escalated_kill_still_writes_in_place(tmp_path):
    """The staging is escalation-ONLY: a first-draft lint kill keeps today's
    behavior (artifacts in the slug dir; the orchestrator archives them at the
    ideated->respec edge, which depends on them being there)."""
    log: list[str] = []
    result = run_s1(
        IDEA_PATH,
        _cfg(),
        writer_runner=h6._writer([h6._reply(_killed_text())], log),
        out_root=tmp_path,
    )
    assert len(log) == 1, "no lint retry outside escalation"
    assert not result.report.passed
    out_dir = Path(result.out_dir)
    assert out_dir.parent.name != KILLED_DIRNAME, (
        f"a non-escalated kill writes to the slug dir as before, got {out_dir}"
    )
    assert (out_dir / "spec.yaml").is_file() and (out_dir / "lint-report.json").is_file()
