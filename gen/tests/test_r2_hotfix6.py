"""R2 hotfix #6 acceptance: an ESCALATED re-spec — the writer is handed the
verifier's own reject reasons and told to fix its spec IN PLACE — tested from
the contract.

Run: .venv/bin/python -m pytest gen/tests/test_r2_hotfix6.py -v

Written against the frozen R2 hotfix-6 mini-contract while `gen/s1_spec.py` and
`gen/orchestrator.py` were changed in parallel; no line of that work was read.
What the contract buys: today a verifier escalation re-runs S1 blind — the
writer re-drafts from the idea alone, so the undeclared deception (or the
undeclared term, or the dead mechanic) the audit found is never named to the
one agent that can fix it, and a fresh draft under a fresh slug would orphan
the `worker/` tree the audit was written about.

Three standing rules this file keeps (the test_r2_hotfix.py precedent):

  * NO API call, ever. `build_writer_prompt` is a pure builder, `run_s1` is
    driven with an INJECTED fake writer (b5's pattern), and every orchestrator
    path is driven by b11's FAKE stage runners. b11's `_no_network_no_agent`
    guard is re-bound here, so a stray `get_driver` fails the test loudly.
  * NO writes outside `tmp_path`. Every `run_s1` call passes `out_root=tmp_path`
    and asserts its result landed under it; `batch_home` re-roots every repo
    path in the orchestrator at `tmp_path`, and b11's `_repo_batches_untouched`
    guard is imported so a stray write into the repo batch root fails loudly.
  * NOTHING IS READ OUT OF `out/`. The escalation report below is hand-written
    from the shape the contract quotes, and the idea/spec it is paired with are
    the committed B5 fixtures — never a live pilot artifact.

THE HARNESS IS IMPORTED, NOT COPIED. `gen/tests/test_b11_pipeline.py` owns the
fake-runner rig (`_Runners`/`_Outcome` script a stage's failure by the state it
fires FROM; `make_cfg`/`batch_home` give each test its own batch root), and its
own escalation test (`test_two_verifier_rejects_escalate_to_respec`) is the
shape group 3 below re-uses: script `implemented -> spec_ok` rejects
`VERIFIER_REJECT_CAP_ESCALATE` times and watch the re-spec. The one thing the
rig does not do is write the S2b report on a REJECT (its `STAGE_ARTIFACTS` only
lands `verifier-report.json` on the happy `verified` edge), so group 3 plants
that file itself through a thin `_Runners` subclass.

Contract readings this file encodes where the hotfix-6 contract left a choice
open — each one is a line to renegotiate, not a fact:

  * The keyword surface is DISCOVERED, never assumed: `_slug_parameter()`
    inspects `build_writer_prompt` and passes the required slug only if a
    keyword whose name contains "slug" exists after (cfg, idea). If no such
    parameter exists, the slug can only come from the report's `game_id`, so
    the fixture sets `game_id` to the required slug and both readings are
    satisfied by one prompt.
  * "no `ESCALATION_HEADER`" and "byte-identical" are tested as two separate
    facts about `escalation=None`: the header is absent, AND the string equals
    the one built with the argument omitted. A builder that stamped a time into
    the prompt would fail the second — deliberately; the prompt is an input to
    a cached session and has to be stable.
  * `ESCALATION_HEADER` is pinned to the `NEG2_NOTATION_HEADER` /
    `CURRICULUM_NOTE_HEADER` shape the contract names: non-empty, ONE line,
    opening with `###`. Nothing about its wording is pinned.
  * "every detail appears VERBATIM" is taken at its word — matched against the
    RAW prompt, not a whitespace-flattened one. The details quote field names
    and literals (`'budget.cap'`, `'hazard.timed'`, `[]`); a builder that
    re-wraps them across lines breaks the writer's ability to find the thing it
    is being asked to fix. If the implementation wraps the block, this is the
    line to renegotiate — not the detail text.
  * "positioned AFTER the idea's prose text and BEFORE `SCHEMA_HEADER`" is read
    as ordering of FIRST occurrences, not adjacency (the test_r2_hotfix.py
    precedent), measured in the whitespace-flattened prompt because the idea's
    prose is only carried flat-equal today (b5's own reading).
  * "the required slug appears" is asserted on the escalated prompt as a plain
    substring. It is NOT asserted to be absent from the non-escalated prompt —
    the idea's title is "Fogbound Switchyard" and a builder may well slugify it
    anyway; that is not this contract's business.
  * "exactly two session calls" (B2) is pinned literally as two, and the
    correct-slug run (B1) pins ONE in the same file. So both readings the
    contract offers hold at once: two calls, and exactly one more than the
    clean escalated run. If a witness turn is ever added to `run_s1`, both
    numbers move together and the relative reading is the one to keep.
  * "a corrective line naming the slug" is pinned as: the second prompt differs
    from the first, and holds a LINE that is absent from the first prompt and
    names the required slug. The wrong slug is NOT required to appear (the
    contract says "naming the slug", singular) — although a correction that
    names both is what the RuntimeError message is separately required to do.
  * "raises RuntimeError whose message contains 'slug' and both slug spellings"
    is read with the SAME wrong slug returned twice, so "both spellings" can
    only mean {what the writer wrote, what it had to write}. The writer stub
    repeats its last reply forever and hard-stops at 6 calls, so an unbounded
    retry loop fails as a bounded AssertionError instead of hanging.
  * "the spec lands in the EXISTING dir" is pinned by SURVIVAL, not by the path
    alone: a non-escalated run of the same reply would land on the same path
    too (the slug decides it), so what is actually asserted is that the planted
    `worker/` tree and the `worker.verifier-report.json` sibling are still
    byte-identical afterwards, while `spec.yaml` DID change. That is the
    difference between editing in place and re-creating the dir.
  * The verifier report's FILENAME is not pinned. `worker.verifier-report.json`
    (the contract's own spelling, and what group 2 plants) and
    `verifier-report.json` (b11's spelling for the same §2 artifact) are both
    planted in group 3, and the assertion is on the CONTENT the escalated ctx
    points at, plus that it lives under the batch home. If the implementation
    picks a third name, only the planting list needs widening.
  * "the fake s1 runner receives a ctx" identifies the s1 runner BY DISCOVERY:
    the stage name of the call that first drove `ideated -> spec_ok`. If the
    re-spec is invoked under a different stage key than the original spec, this
    test fails naming both keys — one stage under two names is itself the bug.
  * "the s1 runner is NOT invoked" (C2) is read as: not invoked AGAIN. The slot
    already spent one s1 call writing the spec that got rejected, so the pin is
    "the s1 stage ran exactly once, and no call after the escalating reject",
    plus: no ctx anywhere carried an escalation.
  * `SlotContext` "constructible with default None" is pinned off
    `inspect.signature` (the field exists and its default IS None) rather than
    by hand-building one with invented values for its other fields; the
    behavioural half — "b11's `_context` never sets it" — is pinned on a full
    happy run, where EVERY ctx the rig sees must carry `escalation is None`
    (absent attribute fails too).
  * The block in C2 is read as test_r2_hotfix2.py reads it: the batch report's
    per-slot `blocked["reason"]`, with the slug in the report's top-level
    `blocked` list, so "blocked" cannot be satisfied by a reason string on a
    slot that actually ran on. The reason is matched case-insensitively and
    whitespace-flattened for the substring "verifier report"; wording beyond
    those two words is not pinned.
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

from gen import orchestrator as orch
from gen.config import load_config
from gen.s1_spec import (
    ESCALATION_HEADER,
    SCHEMA_HEADER,
    build_writer_prompt,
    run_s1,
)

# The b11 fake-runner rig (imported, never copied — see the module docstring).
# Its helpers are called through `b11.` so every borrowed piece names its owner;
# its fixtures have to be re-bound here, because pytest resolves a fixture by
# looking up that name in the REQUESTING module.
from gen.tests import test_b11_pipeline as b11

#: b11's own guards, adopted deliberately: no network / no agent session, and a
#: fail-loud check that nothing wrote into the repo's `out/batches/`.
_no_network_no_agent = b11._no_network_no_agent
_repo_batches_untouched = b11._repo_batches_untouched
#: `batch_home` re-roots every repo path at `tmp_path`; `make_cfg` deep-copies
#: the pilot config into a batch id nobody else uses.
batch_home = b11.batch_home
make_cfg = b11.make_cfg

PILOT = "config/b001-pilot.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "specs"
GOOD_PATH = FIXTURES / "good-spec.yaml"
IDEA_PATH = FIXTURES / "idea-001.json"

BATCH_ID = "b001-pilot"
#: the slug the committed B5 spec fixture declares — the slug an escalated
#: re-spec is required to keep.
REQUIRED_SLUG = "fogbound-switchyard"
#: what a writer that re-drafts from scratch does instead.
WRONG_SLUG = "misrouted-yard"

#: the contract's own spelling for the S2b artifact, plus b11's spelling for
#: the same §2 report. Group 3 plants both; the assertion is on the content.
VERIFIER_REPORT_NAMES = ("worker.verifier-report.json", "verifier-report.json")

#: the §2 reject the escalation carries — hand-written to the shape the contract
#: quotes (three codes, one per audit family), never read out of `out/`.
REJECT_REASONS = (
    {
        "code": "undeclared-deception",
        "detail": "the audit detected the 'false tell' lever; the spec declares []",
        "lever": "false tell",
    },
    {
        "code": "undeclared-term",
        "detail": (
            "'budget.cap' is reachable in the code but the spec does not declare it (off-intent)"
        ),
    },
    {
        "code": "unreachable-declared-mechanic",
        "detail": "spec declares 'hazard.timed' but the audit reports it unreachable in play",
    },
)

REPORT = {
    "verdict": "reject",
    "game_id": REQUIRED_SLUG,
    "reject_reasons": [dict(reason) for reason in REJECT_REASONS],
    "diff": {"missing": ["hazard.timed"], "undeclared": ["budget.cap"]},
}

DETAILS = tuple(reason["detail"] for reason in REJECT_REASONS)

#: the two spec fields the instruction surface has to name literally.
SPEC_FIELDS = ("knobs.deceptions", "game.terms")

#: "in place", hyphenated or not, case-insensitively.
IN_PLACE_RE = re.compile(r"(?i)\bin[-\s]place\b")

#: the §4 edge a verifier reject rides (b11's own reading of architecture §4).
REJECT_EDGE = ("implemented", "spec_ok")

#: what C2's block has to name, flattened + lowercased.
BLOCK_NEEDLE = "verifier report"

PROSE = "Here is the corrected specification for Fogbound Switchyard.\n"

_MISSING = object()


# --------------------------------------------------------------------------
# helpers — fixtures on disk, prompts, replies
# --------------------------------------------------------------------------


def _cfg() -> dict:
    return load_config(PILOT)


def _idea() -> dict:
    return json.loads(IDEA_PATH.read_text(encoding="utf-8"))


def _good_text() -> str:
    return GOOD_PATH.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Whitespace-normalised, so a re-wrapped prompt still matches."""
    return " ".join(text.split())


def _spec_with_slug(slug: str) -> str:
    """The committed good spec with ONE thing changed: `game.slug`.

    Round-tripped through yaml rather than text-substituted, so the mutation
    cannot depend on the fixture's layout.
    """
    spec = yaml.safe_load(_good_text())
    assert spec["game"]["slug"] == REQUIRED_SLUG, (
        f"fixture drift: {GOOD_PATH.name} no longer declares slug {REQUIRED_SLUG!r}"
    )
    spec["game"]["slug"] = slug
    return yaml.safe_dump(spec, sort_keys=False)


def _reply(spec_text: str) -> str:
    """One writer reply: prose, then EXACTLY ONE fenced yaml block (b5's shape)."""
    return f"{PROSE}\n```yaml\n{spec_text.rstrip()}\n```\n"


def _writer(replies: list[str], log: list[str], *, limit: int = 6):
    """Returns each reply in turn, REPEATING the last one forever.

    Repeating (rather than b5's `_scripted_writer`, which raises when it runs
    dry) is what makes "wrong twice raises RuntimeError" a statement about
    run_s1 and not about the stub. `limit` keeps an unbounded retry loop from
    hanging the suite: it surfaces as an AssertionError naming the count.
    """

    def runner(prompt: str, *args, **kwargs) -> str:
        log.append(prompt)
        if len(log) > limit:
            raise AssertionError(
                f"run_s1 called the writer {len(log)} times; the slug retry must be bounded"
            )
        return replies[min(len(log) - 1, len(replies) - 1)]

    return runner


def _slug_parameter() -> str | None:
    """The explicit slug keyword, if the final signature grew one (contract A)."""
    params = list(inspect.signature(build_writer_prompt).parameters.values())
    for param in params[2:]:  # (cfg, idea) are positional — b5 calls them so
        if param.kind is param.VAR_KEYWORD or param.kind is param.VAR_POSITIONAL:
            continue
        if "slug" in param.name.lower():
            return param.name
    return None


def _build(cfg, idea, *, escalation, slug: str = REQUIRED_SLUG) -> str:
    """`build_writer_prompt` with the escalation, adapting to the slug keyword."""
    kwargs: dict = {"escalation": escalation}
    name = _slug_parameter()
    if name is not None:
        kwargs[name] = slug
    return build_writer_prompt(cfg, idea, **kwargs)


def _plant_corpus(tmp_path: Path) -> dict[str, Path]:
    """The corpus dir an escalation edits IN PLACE, as S1/S2/S2b left it.

    Returns the paths whose survival is the whole point of group 2.
    """
    corpus = tmp_path / BATCH_ID / REQUIRED_SLUG
    (corpus / "worker").mkdir(parents=True)
    planted = {
        "corpus": corpus,
        "game": corpus / "worker" / "game.py",
        "solver": corpus / "worker" / "solver.py",
        "report": corpus / VERIFIER_REPORT_NAMES[0],
        "spec": corpus / "spec.yaml",
    }
    planted["game"].write_text('"""the implemented worker the audit read."""\n', encoding="utf-8")
    planted["solver"].write_text('"""the solver the audit replayed."""\n', encoding="utf-8")
    planted["report"].write_text(json.dumps(REPORT, indent=2) + "\n", encoding="utf-8")
    planted["spec"].write_text("game:\n  slug: fogbound-switchyard  # the REJECTED draft\n")
    return planted


def _dirs_under(parent: Path) -> set[str]:
    return {path.name for path in parent.iterdir() if path.is_dir()}


# --------------------------------------------------------------------------
# helpers — the orchestrator side (r2_hotfix2's readers)
# --------------------------------------------------------------------------


def _escalation_of(ctx):
    """`ctx.escalation`, by attribute or key; `_MISSING` when there is none."""
    if isinstance(ctx, Mapping):
        return ctx.get("escalation", _MISSING)
    return getattr(ctx, "escalation", _MISSING)


def _only_slot(report) -> dict:
    slots = report["slots"]
    assert len(slots) == 1, f"these tests run a one-slot batch; the report has {len(slots)}"
    return slots[0]


def _block_reason(report) -> str:
    row = _only_slot(report)
    blocked = row["blocked"]
    assert blocked, (
        f"the slot is not blocked at all — state {row['state']!r}, "
        f"stop_reason {report['stop_reason']!r}"
    )
    reason = blocked.get("reason")
    assert isinstance(reason, str) and reason.strip(), (
        f"a blocked slot must carry a non-empty reason, got {reason!r}"
    )
    return reason


def _spec_stage(journal) -> str:
    """The stage name that drove `ideated -> spec_ok` — i.e. S1, discovered."""
    for call in journal.calls:
        if (call.from_state, call.to_state) == ("ideated", "spec_ok"):
            return call.stage
    raise AssertionError(
        f"no stage drove `ideated -> spec_ok`, so there is no S1 to observe: "
        f"{[(c.stage, c.from_state, c.to_state) for c in journal.calls]}"
    )


class _Receipt:
    """One stage call, with the escalation as it was AT RECEIPT."""

    def __init__(self, stage: str, n: int, value) -> None:
        self.stage = stage
        self.n = n
        self.value = value
        self.payload = None
        if isinstance(value, (str, Path)) and Path(value).is_file():
            self.payload = json.loads(Path(value).read_text(encoding="utf-8"))

    def __repr__(self) -> str:  # pragma: no cover - assertion messages only
        return f"_Receipt(stage={self.stage!r}, n={self.n}, value={self.value!r})"


class _WatchingRunners(b11._Runners):
    """b11's rig + two things it has no reason to do on its own.

    1. Every ctx's `escalation` is snapshotted BEFORE the fake runs, so the
       payload read back is the one the stage was handed (later fakes rewrite
       artifacts under the same names).
    2. With `report=`, the S2b artifact is landed on every call — the rig only
       writes `verifier-report.json` on the happy `verified` edge, and an
       escalation is by definition a path the happy edge never took.
    """

    def __init__(self, journal, cfg, *, outcomes=None, report=None) -> None:
        self.receipts: list[_Receipt] = []
        self.planted: list[Path] = []
        self._report = report
        super().__init__(journal, cfg, outcomes=outcomes)

    def _make(self, stage: str):
        inner = super()._make(stage)

        def runner(ctx):
            value = _escalation_of(ctx)
            self.receipts.append(_Receipt(stage, len(self.receipts) + 1, value))
            result = inner(ctx)
            self._plant(ctx)
            return result

        return runner

    def _plant(self, ctx) -> None:
        if self._report is None:
            return
        slug = b11._ctx_slug(ctx)
        if not slug:
            return
        body = json.dumps(self._report, indent=2) + "\n"
        for slot_dir in self._slot_dirs(ctx, slug):
            for name in VERIFIER_REPORT_NAMES:
                path = slot_dir / name
                path.write_text(body, encoding="utf-8")
                if path not in self.planted:
                    self.planted.append(path)

    def escalated(self) -> list[_Receipt]:
        return [r for r in self.receipts if r.value not in (None, _MISSING)]


def _drive_escalation(make_cfg, batch_id: str, *, report: dict | None):
    """b11's own escalation script: verifier rejects up to the cap, then watch.

    `report=None` means the S2b artifact is NOT on disk — C2's case.
    """
    cfg, _path = make_cfg(batch_id)
    journal = b11._Journal()
    runners = _WatchingRunners(
        journal,
        cfg,
        outcomes={
            "implemented": b11._Outcome(
                "spec_ok",
                "verifier reject: undeclared deception",
                times=orch.VERIFIER_REJECT_CAP_ESCALATE,
            )
        },
        report=report,
    )
    batch_report = b11._advance(cfg, runners)
    return cfg, journal, runners, batch_report


# --------------------------------------------------------------------------
# 1: build_writer_prompt — the escalation block
# --------------------------------------------------------------------------


def test_the_escalation_header_is_a_one_line_hash_heading():
    """The NEG2_NOTATION_HEADER / CURRICULUM_NOTE_HEADER shape, nothing more."""
    assert isinstance(ESCALATION_HEADER, str) and ESCALATION_HEADER.strip(), (
        "ESCALATION_HEADER must be non-empty text"
    )
    assert "\n" not in ESCALATION_HEADER, (
        f"the header is ONE line, like its siblings: {ESCALATION_HEADER!r}"
    )
    assert ESCALATION_HEADER.startswith("###"), (
        "the prompt's sections are `###` markdown headings, so the escalation block stays "
        f"navigable; got {ESCALATION_HEADER!r}"
    )


def test_build_writer_prompt_takes_escalation_as_a_keyword():
    params = inspect.signature(build_writer_prompt).parameters
    assert "escalation" in params, (
        f"build_writer_prompt must accept `escalation`; signature is "
        f"{inspect.signature(build_writer_prompt)}"
    )
    param = params["escalation"]
    assert param.default is None, (
        f"`escalation` must default to None (no escalation is the normal case), "
        f"got {param.default!r}"
    )
    assert param.kind is param.KEYWORD_ONLY, (
        f"`escalation` is contracted keyword-only (`*, escalation=None`), got {param.kind}"
    )


def test_escalation_none_is_byte_identical_to_omitting_it():
    cfg, idea = _cfg(), _idea()
    omitted = build_writer_prompt(cfg, idea)
    explicit = build_writer_prompt(cfg, idea, escalation=None)
    assert explicit == omitted, (
        "passing escalation=None must build the SAME prompt as omitting it — every "
        "non-escalated S1 call in the pilot goes through this path"
    )


def test_a_prompt_with_no_escalation_carries_no_escalation_header():
    for prompt in (
        build_writer_prompt(_cfg(), _idea()),
        build_writer_prompt(_cfg(), _idea(), escalation=None),
    ):
        assert ESCALATION_HEADER not in prompt, (
            "a first-draft prompt must not carry the escalation header — there is nothing "
            "to escalate, and the section would be empty doctrine"
        )


def test_the_escalated_prompt_carries_the_header_exactly_once():
    prompt = _build(_cfg(), _idea(), escalation=REPORT)
    count = prompt.count(ESCALATION_HEADER)
    assert count == 1, f"the escalation section must appear exactly once, found {count}"


def test_the_escalation_block_sits_after_the_idea_and_before_the_schema():
    """Ordering of first occurrences, not adjacency (the hotfix-1 precedent)."""
    idea = _idea()
    prompt = _build(_cfg(), idea, escalation=REPORT)
    flat = _flat(prompt)

    prose = _flat(idea["prose"]["text"])
    assert prose in flat, "the idea's prose must still be carried — the anchor for `after`"
    assert _flat(SCHEMA_HEADER) in flat, "the schema header must still be present — the `before`"

    prose_at = flat.index(prose)
    header_at = flat.index(_flat(ESCALATION_HEADER))
    schema_at = flat.index(_flat(SCHEMA_HEADER))

    assert prose_at < header_at, (
        "the escalation block belongs AFTER the idea it corrects: the writer reads what the "
        f"game is, then what was wrong with its spec ({header_at} vs {prose_at})"
    )
    assert header_at < schema_at, (
        "the escalation block belongs BEFORE the schema section, which is the answer format "
        f"the correction has to be written in ({header_at} vs {schema_at})"
    )


@pytest.mark.parametrize("detail", DETAILS, ids=[r["code"] for r in REJECT_REASONS])
def test_the_escalated_prompt_quotes_every_reject_detail_verbatim(detail):
    """A reason the writer is not shown is a reason it re-commits next round."""
    prompt = _build(_cfg(), _idea(), escalation=REPORT)
    assert detail in prompt, (
        f"the audit's own words must reach the writer unaltered: {detail!r} is not in the "
        "prompt (a paraphrase, or a re-wrapped line, is not the detail)"
    )


def test_the_escalated_prompt_orders_an_in_place_edit_and_names_the_slug():
    prompt = _build(_cfg(), _idea(), escalation=REPORT)
    flat = _flat(prompt)

    assert IN_PLACE_RE.search(flat), (
        "the instruction must say the fix is made IN PLACE (or in-place) — without it the "
        "writer re-drafts, the slug moves, and the audited worker/ tree is orphaned"
    )
    assert REQUIRED_SLUG in prompt, (
        f"the prompt must name the slug the re-spec has to keep ({REQUIRED_SLUG!r}); it is the "
        "identity of the corpus dir being edited"
    )


@pytest.mark.parametrize("field", SPEC_FIELDS)
def test_the_escalated_prompt_names_the_spec_fields_literally(field):
    """`knobs.deceptions` and `game.terms` are where an undeclared lever and an
    undeclared term get declared; naming the rule without naming the field is
    what made the first escalation a blind re-draft."""
    prompt = _build(_cfg(), _idea(), escalation=REPORT)
    assert field in prompt, f"the instruction surface must name `{field}` literally"


# --------------------------------------------------------------------------
# 2: run_s1 — the escalated re-spec, in place
# --------------------------------------------------------------------------


def test_run_s1_takes_escalation_as_an_optional_path():
    params = inspect.signature(run_s1).parameters
    assert "escalation" in params, (
        f"run_s1 must accept `escalation`; signature is {inspect.signature(run_s1)}"
    )
    assert params["escalation"].default is None, (
        f"`escalation` must default to None, got {params['escalation'].default!r}"
    )


def test_an_escalated_run_rewrites_the_spec_in_place(tmp_path):
    """The spec is replaced; the audited worker tree and its report are not."""
    planted = _plant_corpus(tmp_path)
    before = {
        name: planted[name].read_bytes() for name in ("game", "solver", "report")
    }
    log: list[str] = []

    result = run_s1(
        IDEA_PATH,
        _cfg(),
        writer_runner=_writer([_reply(_good_text())], log),
        out_root=tmp_path,
        escalation=planted["report"],
    )

    assert len(log) == 1, f"a correct, well-formed reply must not be retried, got {len(log)} calls"

    out_dir = Path(result.out_dir).resolve()
    assert out_dir == planted["corpus"].resolve(), (
        f"the re-spec must land in the EXISTING corpus dir {planted['corpus']}, not {out_dir}"
    )
    assert out_dir.is_relative_to(tmp_path.resolve()), "run_s1 wrote outside tmp_path"
    assert _dirs_under(tmp_path / BATCH_ID) == {REQUIRED_SLUG}, (
        "an escalated re-spec must not create a second slot dir: "
        f"{_dirs_under(tmp_path / BATCH_ID)}"
    )

    for name in ("game", "solver", "report"):
        assert planted[name].is_file(), f"the escalated run deleted {planted[name]}"
        assert planted[name].read_bytes() == before[name], (
            f"{planted[name].name} changed — S1 rewrites the SPEC, and nothing else in the "
            "dir the audit was written about"
        )

    spec_text = planted["spec"].read_text(encoding="utf-8")
    assert "the REJECTED draft" not in spec_text, "the rejected spec.yaml must be replaced"
    assert yaml.safe_load(spec_text) == yaml.safe_load(_good_text()), (
        "spec.yaml must hold the corrected spec the writer returned"
    )

    # the prompt the writer actually got is the escalated one (group 1's block)
    assert ESCALATION_HEADER in log[0], "run_s1 must build the ESCALATED prompt"
    for detail in DETAILS:
        assert detail in log[0], f"the escalated prompt lost a reject detail: {detail!r}"


def test_a_wrong_slug_costs_one_corrective_retry(tmp_path):
    """The writer that re-drafts under a new slug is told, once, to put it back."""
    planted = _plant_corpus(tmp_path)
    log: list[str] = []

    result = run_s1(
        IDEA_PATH,
        _cfg(),
        writer_runner=_writer([_reply(_spec_with_slug(WRONG_SLUG)), _reply(_good_text())], log),
        out_root=tmp_path,
        escalation=planted["report"],
    )

    assert len(log) == 2, (
        f"a wrong slug costs exactly one corrective retry (1 call + 1), got {len(log)}"
    )
    assert log[1] != log[0], "the retry must SAY something new — re-sending the prompt is not a fix"

    new_lines = [line for line in log[1].splitlines() if line not in set(log[0].splitlines())]
    corrective = [line for line in new_lines if REQUIRED_SLUG in line]
    assert corrective, (
        "the second prompt must carry a corrective line naming the required slug "
        f"{REQUIRED_SLUG!r}. New lines were: {new_lines[:12]}"
    )

    out_dir = Path(result.out_dir).resolve()
    assert out_dir == planted["corpus"].resolve(), (
        f"after the correction the spec must land in the existing dir, not {out_dir}"
    )
    assert _dirs_under(tmp_path / BATCH_ID) == {REQUIRED_SLUG}, (
        f"the rejected first draft must not leave a dir behind: {_dirs_under(tmp_path / BATCH_ID)}"
    )
    assert planted["report"].is_file() and planted["game"].is_file(), (
        "the audited artifacts must survive the corrective round too"
    )


def test_two_wrong_slugs_raise_and_leave_no_second_corpus_dir(tmp_path):
    """Never a silent new game: the run dies loudly, naming both spellings."""
    planted = _plant_corpus(tmp_path)
    log: list[str] = []

    with pytest.raises(RuntimeError) as excinfo:
        run_s1(
            IDEA_PATH,
            _cfg(),
            writer_runner=_writer([_reply(_spec_with_slug(WRONG_SLUG))], log),
            out_root=tmp_path,
            escalation=planted["report"],
        )

    message = str(excinfo.value)
    assert "slug" in message.lower(), f"the error must say what went wrong: {message!r}"
    assert WRONG_SLUG in message, f"the error must name the slug the writer returned: {message!r}"
    assert REQUIRED_SLUG in message, f"the error must name the slug it had to return: {message!r}"

    assert len(log) == 2, f"the corrective retry is spent once, then it is fatal; got {len(log)}"
    assert _dirs_under(tmp_path / BATCH_ID) == {REQUIRED_SLUG}, (
        "a failed escalation must leave NO second corpus dir — an orphan dir under the wrong "
        f"slug is exactly what breaks slot discovery: {_dirs_under(tmp_path / BATCH_ID)}"
    )
    assert planted["report"].read_bytes() == json.dumps(REPORT, indent=2).encode() + b"\n", (
        "the verifier report must survive a failed escalation — it is the evidence"
    )


# --------------------------------------------------------------------------
# 3: the orchestrator — SlotContext.escalation and _maybe_respec
# --------------------------------------------------------------------------


def test_slot_context_gains_an_optional_escalation_field():
    slot_context = getattr(orch, "SlotContext", None)
    assert slot_context is not None, "gen.orchestrator must expose SlotContext"
    params = inspect.signature(slot_context).parameters
    assert "escalation" in params, (
        f"SlotContext must carry `escalation`; fields are {list(params)}"
    )
    param = params["escalation"]
    assert param.default is None, (
        f"`escalation` must default to None so every existing construction still works, "
        f"got {param.default!r}"
    )
    annotation = param.annotation
    if annotation is not inspect.Parameter.empty:
        assert "Path" in str(annotation), (
            f"`escalation` is contracted as `Path | None`, annotated {annotation!r}"
        )


def test_a_run_with_no_escalation_never_sets_the_field(make_cfg):
    """b11's context factory sets nothing; every ctx reads back None."""
    cfg, _path = make_cfg("r2h6-happy")
    journal = b11._Journal()
    runners = b11._Runners(journal, cfg)
    b11._advance(cfg, runners)

    assert journal.contexts, "the happy run invoked no stage at all"
    for index, ctx in enumerate(journal.contexts):
        value = _escalation_of(ctx)
        assert value is not _MISSING, (
            f"ctx #{index} has no `escalation` attribute at all: {ctx!r}"
        )
        assert value is None, (
            f"nothing escalated in this run, but ctx #{index} carries escalation={value!r}"
        )


def test_the_escalated_respec_hands_s1_the_verifier_report(make_cfg, batch_home):
    """C1: at the reject cap, S1 is re-invoked with a Path to the S2b report."""
    cfg, journal, runners, _report = _drive_escalation(make_cfg, "r2h6-escalate", report=REPORT)

    rejects = [
        line for line in b11._ledger_lines(cfg) if (line["from"], line["to"]) == REJECT_EDGE
    ]
    assert len(rejects) == orch.VERIFIER_REJECT_CAP_ESCALATE, (
        f"the rig must reach the escalation cap first: {b11._spine(b11._ledger_lines(cfg))}"
    )
    assert runners.planted, "the test planted no verifier report"

    escalated = runners.escalated()
    assert escalated, (
        "no stage was handed an escalation. Every ctx read back None, so the re-spec ran "
        f"blind: {[(r.stage, r.n) for r in runners.receipts]}"
    )
    assert len(escalated) == 1, (
        f"exactly one re-spec was escalated here, but {len(escalated)} calls carried one: "
        f"{escalated}"
    )

    receipt = escalated[0]
    assert receipt.stage == _spec_stage(journal), (
        f"the escalation belongs to the S1 stage ({_spec_stage(journal)!r}), but it was handed "
        f"to {receipt.stage!r}"
    )
    assert isinstance(receipt.value, Path), (
        f"`ctx.escalation` is contracted as a Path, got {type(receipt.value).__name__} "
        f"({receipt.value!r})"
    )
    assert receipt.payload == REPORT, (
        "`ctx.escalation` must point at the verifier report that rejected this slot; the file "
        f"at {receipt.value} held {receipt.payload!r}"
    )
    assert receipt.value.resolve().is_relative_to(Path(batch_home).resolve()), (
        f"the escalation path must live under the batch home, got {receipt.value}"
    )
    assert receipt.value.name in VERIFIER_REPORT_NAMES, (
        f"unexpected report filename {receipt.value.name!r} — widen VERIFIER_REPORT_NAMES if "
        "the artifact was renamed"
    )


def test_a_missing_verifier_report_blocks_the_slot(make_cfg):
    """C2: no report, no blind re-spec — the slot blocks and says why."""
    cfg, journal, runners, report = _drive_escalation(make_cfg, "r2h6-noreport", report=None)

    rejects = [
        line for line in b11._ledger_lines(cfg) if (line["from"], line["to"]) == REJECT_EDGE
    ]
    assert len(rejects) == orch.VERIFIER_REJECT_CAP_ESCALATE, (
        "the block must fire AT the escalation cap, not before it: "
        f"{b11._spine(b11._ledger_lines(cfg))}"
    )

    reason = _block_reason(report)
    assert BLOCK_NEEDLE in _flat(reason).lower(), (
        f"the block must name the missing verifier report, got {reason!r}"
    )
    row = _only_slot(report)
    assert row["slug"] in report["blocked"], (
        f"the batch report must name the blocked slot: {report['blocked']}"
    )

    assert not runners.escalated(), (
        f"no escalation may be handed out when the report is absent: {runners.escalated()}"
    )
    stage = _spec_stage(journal)
    s1_calls = [call for call in journal.calls if call.stage == stage]
    assert len(s1_calls) == 1, (
        f"S1 ran {len(s1_calls)} times: the blocked escalation must NOT re-invoke it "
        f"(calls: {[(c.n, c.stage, c.from_state, c.to_state) for c in journal.calls]})"
    )
    last_reject = max(
        call.n for call in journal.calls if (call.from_state, call.to_state) == REJECT_EDGE
    )
    assert s1_calls[0].n < last_reject, (
        "the only S1 call must be the original spec, before the escalating reject "
        f"(S1 at #{s1_calls[0].n}, reject at #{last_reject})"
    )
