"""b002 hotfix #2 — the S2 re-implement must be SHOWN the blind audit's findings.

THE GAP THIS PINS. When the S2b blind audit rejects a build, §4 sends the slot
back around: a re-implement of the same spec, and (once the reject cap trips) a
re-spec. The S1 respec has carried the audit's findings since the R2 amendment —
it is handed the very report it has to answer. The S2 re-implement was not. It
rebuilt from `build_payload(spec_dir, cfg)` and nothing else, so round N+1 began
from exactly the knowledge round N had; and because the worker's own
`make validate` cannot run the verifier's own static checks, a verifier-side
finding is invisible from inside the green loop. With no feed, the same finding
class can survive re-implement after re-implement until a cap ends the slot.

THE FIX. On a reject — and only on a reject — the S2 runner appends a
deterministic findings section, rendered by `gen.s2_implement.findings_section`
from the verifier report on disk, AFTER the whole payload. Every other case (no
report path, no file, a non-reject verdict) leaves the prompt byte-identical to
what it is today, and `payload.md` keeps recording the prompt actually sent.

INDEPENDENCE. Written from the frozen contract alone — against
`findings_section`'s declared behaviour and the runner's observable effect, not
against the implementation. Everything here is SYNTHETIC: the spec is the
checked-in hand-written §11 fixture, the reject report is invented in this file,
and `green_loop` is replaced by a recorder, so no session runs, nothing is spent,
and no text from any real run appears anywhere below (pinned by test 5).

Run: .venv/bin/python -m pytest gen/tests/test_b002_hotfix2.py -v
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import gen.s2_implement as s2
from gen.config import load_config
from gen.orchestrator import SlotContext, default_runners
from gen.worker import instantiate_worker

PILOT_CONFIG = "config/b001-pilot.yaml"
FIXTURE_SPEC = Path(__file__).resolve().parent / "fixtures/specs/good-spec.yaml"

# Invented names for the planted slot. They exist so the corpus layout below has
# the shape `_require_spec_dir` / `SlotContext.verifier_report_path` expect; they
# name nothing that has ever been sampled.
BATCH_ID = "b-hotfix2-fixture"
SLOT_SLUG = f"{BATCH_ID}-s001"
SPEC_SLUG = "fogbound-switchyard"   # the fixture spec's own slug (fixtures/specs/)

# A short prose spec, written here, so the planted dir is a complete S1 output.
SPEC_MD = """# Fogbound Switchyard — prose spec (fixture)

Belts carry coloured crates past cycleable junctions toward pads of matching
colour. A fog bank telegraphs the yard's true state for a few beats and then
renders that half flat grey while the belts keep running underneath it.
"""

# --- the synthetic reject report --------------------------------------------
# Three entries covering the three optional-field shapes the renderer must
# handle: detail only, term + detail, lever only. The codes and details are made
# up in this file; the one `term` is a term the checked-in fixture spec declares
# (test 5 proves that provenance), because a term has to be a real vocabulary
# string to be worth rendering.
SYNTHETIC_TERM = "info.fog"
SYNTHETIC_LEVER = "synthetic-lever"
SYNTHETIC_REASONS = (
    {"code": "synthetic-static", "detail": "synthetic detail alpha"},
    {"code": "undeclared-term", "term": SYNTHETIC_TERM, "detail": "synthetic detail beta"},
    {"code": "undeclared-deception", "lever": SYNTHETIC_LEVER},
)
SYNTHETIC_CODES = tuple(reason["code"] for reason in SYNTHETIC_REASONS)
# Everything the section must interpolate verbatim, in one list for the pins.
SYNTHETIC_FIELDS = (
    *SYNTHETIC_CODES, SYNTHETIC_TERM, SYNTHETIC_LEVER,
    "synthetic detail alpha", "synthetic detail beta",
)


def _reject_report() -> dict:
    """A fresh reject report (deep-ish copy: the renderer must not mutate it)."""
    return {"verdict": "reject", "reject_reasons": [dict(r) for r in SYNTHETIC_REASONS]}


def _pass_report() -> dict:
    return {"verdict": "pass", "reject_reasons": []}


# --- fixtures ----------------------------------------------------------------


@pytest.fixture(scope="module")
def cfg() -> dict:
    return load_config(PILOT_CONFIG)


def _plant(root: Path, cfg: dict) -> SimpleNamespace:
    """A slot on disk in architecture §2's shape, plus the ctx that points at it.

    `corpus/<batch>/<slug>/{spec.yaml,spec.md,worker/}` — the layout
    `_require_spec_dir`'s caller walks and `SlotContext.verifier_report_path`
    derives the S2b report sibling from. A REAL `SlotContext` is built (not a
    duck) so every field the runner may touch is present and typed.
    """
    corpus_dir = root / "corpus" / BATCH_ID
    spec_dir = corpus_dir / SPEC_SLUG
    spec_dir.mkdir(parents=True)
    shutil.copy2(FIXTURE_SPEC, spec_dir / "spec.yaml")
    (spec_dir / "spec.md").write_text(SPEC_MD, encoding="utf-8")
    instantiate_worker(spec_dir / "worker")

    ideas_dir = root / "ideas" / BATCH_ID
    ideas_dir.mkdir(parents=True)
    ctx = SlotContext(
        cfg=cfg,
        batch_id=BATCH_ID,
        slug=SLOT_SLUG,
        index=1,
        state="spec_ok",
        stage="s2_implement",
        attempt=1,
        batch_dir=root / "batch",
        ideas_dir=ideas_dir,
        idea_path=ideas_dir / "idea-001.json",
        corpus_dir=corpus_dir,
        spec_dir=spec_dir,
        respec_count=0,
        verifier_rejects=1,
        green_failures=0,
    )
    assert ctx.verifier_report_path is not None, (
        "fixture: the planted ctx must resolve an S2b report path — that path IS the "
        "hotfix's trigger input"
    )
    return SimpleNamespace(root=root, spec_dir=spec_dir, ctx=ctx)


class _GreenLoopRecorder:
    """Stands in for the real green loop: records the call, spends nothing.

    The runner imports `green_loop` from `.s2_implement` at call time, so
    replacing the module attribute intercepts it. The positional shape mirrors
    the public signature, so a keyword call binds just as well.
    """

    def __init__(self) -> None:
        self.calls: list[SimpleNamespace] = []

    def __call__(self, worker_dir, prompt, cfg, **kwargs):
        self.calls.append(
            SimpleNamespace(worker_dir=Path(worker_dir), prompt=prompt, cfg=cfg, kwargs=kwargs)
        )
        return s2.ImplementReport(
            worker=str(worker_dir), green=True, attempts=1, total_usd=0.0,
            total_tokens_in=0, total_tokens_out=0, wall_s=0.0, records=[], reject_reason=None,
        )


def _drive(slot: SimpleNamespace, monkeypatch) -> SimpleNamespace:
    """Run the real S2 runner over the planted slot; return the recorded call."""
    recorder = _GreenLoopRecorder()
    monkeypatch.setattr(s2, "green_loop", recorder)
    result = default_runners()["s2_implement"](slot.ctx)
    assert len(recorder.calls) == 1, (
        f"the S2 runner must reach the green loop exactly once per invocation; it called it "
        f"{len(recorder.calls)} time(s) (result: {result})"
    )
    return recorder.calls[0]


def _payload_md(slot: SimpleNamespace) -> Path:
    """The `payload.md` the runner wrote, found by content-free search.

    Its exact home is the runner's business, not this test's — but there must be
    exactly one under the planted slot, because it is the record of what was
    sent.
    """
    found = sorted(slot.root.rglob("payload.md"))
    assert len(found) == 1, (
        f"the runner must write exactly one payload.md under the slot; found {found}"
    )
    return found[0]


def _write_report(slot: SimpleNamespace, report: dict) -> Path:
    path = slot.ctx.verifier_report_path
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


# --- 1. the renderer, called directly ----------------------------------------


def test_1_findings_section_renders_every_finding_and_is_deterministic():
    """The pure renderer: every code, every present optional field, same bytes
    twice, the blind-re-audit instruction, the scope reminder, and a loud
    ValueError on the two malformed inputs it must never be handed."""
    from gen.s2_implement import findings_section

    section = findings_section(_reject_report())
    assert isinstance(section, str) and section.strip(), "the section must be non-empty text"

    head = section.strip().splitlines()[0]
    assert head.startswith("## "), (
        f"the section must open with a `## ` head so it reads as a section of the payload it "
        f"is appended to; got {head!r}"
    )
    lowered_head = head.lower()
    assert "previous" in lowered_head, (
        "the head must say these findings are about the PREVIOUS build — an implementer that "
        f"reads them as findings about code it has not written yet will be lost; got {head!r}"
    )
    assert "finding" in lowered_head or "audit" in lowered_head, (
        f"the head must name what the section is (the failed audit's findings); got {head!r}"
    )

    for field in SYNTHETIC_FIELDS:
        assert field in section, (
            f"{field!r} is in the reject report and must be interpolated verbatim — a finding "
            "the implementer cannot read is a finding it cannot fix"
        )

    lowered = section.lower()
    assert "blind" in lowered, (
        "the section must say the re-audit is BLIND: the fix has to live in the shipped code, "
        "because the auditor re-derives everything from the code alone and never sees this text"
    )
    assert "scope" in lowered or "declare" in lowered, (
        "the section must carry the scope reminder — a finding is never a licence to add "
        "surface the spec does not declare"
    )

    assert findings_section(_reject_report()) == section, (
        "the renderer must be deterministic: the same report must produce the same bytes, or "
        "the payload stops being content-addressable and §2's resume hashing churns"
    )

    code_only = findings_section({"verdict": "reject", "reject_reasons": [{"code": "synth-bare"}]})
    assert "synth-bare" in code_only, (
        "an entry carrying nothing but a code must still render that code (missing optional "
        "keys are omitted, not fatal)"
    )

    with pytest.raises(ValueError) as passing:
        findings_section(_pass_report())
    assert "pass" in str(passing.value), (
        "the ValueError must name the verdict it was handed — the caller only invokes this on "
        f"rejects, so anything else is a wiring bug and must say so; got {passing.value!r}"
    )

    with pytest.raises(ValueError):
        findings_section({"verdict": "reject", "reject_reasons": []})

    with pytest.raises(ValueError):
        findings_section({"reject_reasons": list(SYNTHETIC_REASONS)})


# --- 2. the feed: a reject report rides, after the whole payload --------------


def test_2_a_reject_report_rides_after_the_whole_payload(tmp_path, cfg, monkeypatch):
    """THE HOTFIX ITSELF. With a reject report on disk, the prompt the green loop
    is handed is the payload plus the findings — payload first, byte-identical,
    findings appended at the end."""
    from gen.s2_implement import build_payload, findings_section

    slot = _plant(tmp_path, cfg)
    payload, _report = build_payload(slot.spec_dir, cfg)
    for code in SYNTHETIC_CODES:
        assert code not in payload, (
            f"fixture: {code!r} must be invented, not something build_payload already emits, "
            "or this test would pass without the feed"
        )
    _write_report(slot, _reject_report())

    call = _drive(slot, monkeypatch)

    assert call.prompt.startswith(payload), (
        "the findings are APPENDED: the payload must still be the prompt's opening bytes, "
        "unchanged — the fix adds a section, it does not rebuild the brief"
    )
    tail = call.prompt[len(payload):]
    for field in SYNTHETIC_FIELDS:
        assert field in tail, (
            f"{field!r} never reached the implementer — this is the whole gap: the re-implement "
            "rebuilt from the payload alone and never saw what the audit found"
        )
    assert tail.lstrip("\n") == findings_section(_reject_report()), (
        "the appended tail must be exactly the rendered findings section (and nothing else), "
        "sitting after the payload's closing section"
    )
    assert call.worker_dir == slot.spec_dir / "worker", (
        f"the loop must still be pointed at the slot's worker; got {call.worker_dir}"
    )


# --- 3. every other case is byte-identical to today ---------------------------


def test_3_no_report_and_a_pass_verdict_leave_the_prompt_byte_identical(tmp_path, cfg,
                                                                        monkeypatch):
    """The trigger is narrow: an existing report whose verdict is reject. With no
    report file, or with a pass, the prompt must be the payload and nothing
    else — a first implement must not be told about findings that do not exist."""
    from gen.s2_implement import build_payload

    unfed = _plant(tmp_path / "unfed", cfg)
    payload, _ = build_payload(unfed.spec_dir, cfg)
    assert not unfed.ctx.verifier_report_path.exists(), "fixture: no report may be planted here"
    call = _drive(unfed, monkeypatch)
    assert call.prompt == payload, (
        "with no verifier report on disk the prompt must be the payload byte-for-byte — the "
        "first implement of a spec has no findings to answer"
    )

    passed = _plant(tmp_path / "passed", cfg)
    _write_report(passed, _pass_report())
    call = _drive(passed, monkeypatch)
    assert call.prompt == payload, (
        "a PASS verdict must leave the prompt byte-identical too: the feed exists to answer a "
        "reject, and appending anything here would churn a prompt that has nothing to fix"
    )


# --- 4. payload.md records the prompt actually sent ---------------------------


def test_4_payload_md_is_the_prompt_actually_sent(tmp_path, cfg, monkeypatch):
    """`payload.md` is the on-disk evidence of the brief. If the findings ride in
    the prompt but not in the file, the record lies about what was sent and the
    next round's diagnosis starts from the wrong text."""
    fed = _plant(tmp_path / "fed", cfg)
    _write_report(fed, _reject_report())
    call = _drive(fed, monkeypatch)
    written = _payload_md(fed).read_text(encoding="utf-8")
    assert written == call.prompt, (
        "payload.md must record the prompt ACTUALLY sent, findings included — it is the "
        "record of the brief, not of the brief's first half"
    )
    for code in SYNTHETIC_CODES:
        assert code in written, f"{code!r} rode in the prompt but is missing from payload.md"

    unfed = _plant(tmp_path / "unfed", cfg)
    call = _drive(unfed, monkeypatch)
    assert _payload_md(unfed).read_text(encoding="utf-8") == call.prompt, (
        "the unfed case must keep recording its prompt exactly as before"
    )


# --- 5. hygiene --------------------------------------------------------------


def test_5_every_fixture_string_in_this_file_is_synthetic():
    """Self-check (contract rule): nothing in this file comes from a real run.

    The fixtures are invented here or copied from checked-in fixtures; no batch
    output is read, named, or quoted.
    """
    source = Path(__file__).read_text(encoding="utf-8")

    # Built at runtime so the markers themselves are not literals in the source.
    out = "out"
    live_roots = tuple(f"{out}/{name}" for name in ("corpus", "batches", "ideas", "play", "pilot"))
    for marker in live_roots:
        assert marker not in source, (
            f"this file must never reach into the live tree ({marker}) — its whole premise is "
            "that the fixtures are synthetic"
        )
    for artifact in ("ledger." + "jsonl", "batch-" + "report.json"):
        assert artifact not in source, (
            f"no real batch artifact ({artifact}) may be read or quoted here"
        )

    for reason in SYNTHETIC_REASONS:
        for key in ("detail", "lever"):
            if key in reason:
                assert "synthetic" in reason[key], (
                    f"every invented {key} must declare itself synthetic, so no reader can "
                    f"mistake it for real finding text; got {reason[key]!r}"
                )

    spec_text = FIXTURE_SPEC.read_text(encoding="utf-8")
    assert SYNTHETIC_TERM in spec_text, (
        f"the one vocabulary string used here ({SYNTHETIC_TERM}) must come from the checked-in "
        "fixture spec, not from any run"
    )
    assert SPEC_SLUG in spec_text, (
        "the planted slot's dir name must be the checked-in fixture spec's own slug"
    )
