"""B5 acceptance: the S1 spec writer + the §11 linter — tested from the contract.

Run: .venv/bin/python -m pytest gen/tests/test_b5_spec.py -v

Written against the B5 contract while `gen/s1_spec.py` was implemented in
parallel; nothing here — and nothing in `fixtures/specs/` — was read off the
implementation. The GOOD fixture is itself the independence probe: a §11 spec
written by hand from `spec-v0.3.md` §11 that must survive a strict linter it
has never seen.

Two standing rules this file keeps:

  * NO API call, ever. `run_s1`'s default `writer_runner=None` is the live
    backend, so every run_s1 call below passes an INJECTED fake — a closure
    that returns canned text and logs the prompt it was handed.
  * NO writes to the repo's real `out/` tree. Every run_s1 call passes
    `out_root=tmp_path`, and an autouse guard fails the test if the real tree
    gained, lost or changed a file anyway.

Fixtures (`gen/tests/fixtures/specs/`): `good-spec.yaml` is a complete spec for
a small game that tracks the REAL pilot idea (same idea_ref, same objective
family, same locus, all four seed terms, hazardless). Each `bad/*.yaml` is that
file with ONE thing changed, so the kill it trips is unambiguous; the change is
stated in a comment at the top of each fixture.

Contract readings this file encodes where B5 left a choice open — each one is
a line to renegotiate, not a fact:

  * `strict` was removed from lint-report.json by contract D-3 (an inert
    stamp: required of every config, read by no rule).
  * `spec_hash` is "sha256 hex of the spec.yaml TEXT": hashed here against the
    bytes of the written spec.yaml, allowing only a single trailing newline of
    slack between "the text" and "the file".
  * `S1Result.spec_text` is asserted to CONTAIN the yaml block, not to equal
    it — the contract does not say whether it holds the block or the whole
    writer reply. `spec.yaml` (the artifact of record) is pinned exactly.
  * "the §3b witness lines" is read as the crosswalk (plural), so the prompt
    is required to carry at least two distinct witness terms.
  * `batch_of_idea_id` "raises" on malformed ids is read as ValueError.
  * `spec.md` is read as the writer's REPLY (prose included), so the test looks
    for the prose in it — not only the yaml.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from gen.config import REPO_ROOT, load_config
from gen.s0_ideas import WITNESS_MAP, load_vocab
from gen.s1_spec import (
    DANGER_TELLS,
    DECEPTION_CATALOG,
    GOAL_LEGIBLE,
    HUD_RESERVED,
    KILL_RULES,
    LEVELS_MAX,
    LEVELS_MIN,
    LOCI,
    REFUSALS,
    RELATIONS,
    batch_of_idea_id,
    build_writer_prompt,
    extract_spec_yaml,
    lint_spec,
    run_s1,
)
from gen.s3_verify import detect_levers

PILOT = "config/b001-pilot.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "specs"
GOOD_PATH = FIXTURES / "good-spec.yaml"
BAD_DIR = FIXTURES / "bad"

# The real S0 output the spec writer is fed (the B4 smoke's idea, promoted to
# a fixture at R1: tests never depend on out/, which the pilot run owns).
IDEA_PATH = FIXTURES / "idea-001.json"
IDEA_ID = "b001-pilot-i001"
BATCH_ID = "b001-pilot"
GOOD_SLUG = "fogbound-switchyard"

CORPUS_FILES = ("idea.json", "spec.md", "spec.yaml", "lint-report.json")
# LEAD-CORRECTED PIN (contract D-3): the "strict" stamp is gone — it was
# hard-required of every config and read by no linter rule (the readiness
# audit's inert-knob finding, ruled by the operator).
REPORT_FIELDS = ("passed", "kills", "warns", "spec_hash", "idea_ref", "ts")
KILL_RULES_SET = set(KILL_RULES)

# The bogus term planted in bad/unknown-term.yaml (detail must name it).
BOGUS_TERM = "info.mirage"

# fixture -> (rule it must trip, rules it may ALSO trip, why that coupling is
# accepted). An empty allowance means: this fixture must produce that rule and
# nothing else.
BAD_CASES = (
    ("unknown-term.yaml", "unknown-terms", frozenset(), ""),
    ("unwitnessed-objective.yaml", "objective-unwitnessed", frozenset(), ""),
    (
        "missing-knob.yaml",
        "missing-knobs",
        frozenset({"contradiction"}),
        (
            "danger_tell is GONE, so a C1 check written as `knobs.get(...) != 'none'` "
            "reads None != 'none' and fires too. Accepted: the knob kill is the point."
        ),
    ),
    ("missing-layout-seed.yaml", "schema", frozenset(), ""),
    ("level-count-5.yaml", "curriculum", frozenset(), ""),
    ("three-consecutive-new.yaml", "curriculum", frozenset(), ""),
    ("nothing-reused.yaml", "curriculum", frozenset(), ""),
    ("palette-reserved-collision.yaml", "palette-collision", frozenset(), ""),
    ("sketch-undeclared-decoy.yaml", "undeclared-deception", frozenset(), ""),
    ("refusal-visible-silent-decoy.yaml", "contradiction", frozenset(), ""),
    ("survive-budget-same-counter.yaml", "contradiction", frozenset(), ""),
)

PROSE = (
    "Here is the specification for Fogbound Switchyard.\n\n"
    "## Design notes\n\n"
    "The yard is legible from the first frame: belts, crates, pads, junctions.\n"
)

# A hand-written idea carrying exactly what `build_writer_prompt` requires
# (id, seed_terms, prose). The §7 layout-seed block is static prompt text, so
# the test that pins it needs no artifact under `out/` to be present.
MINIMAL_IDEA = {
    "id": IDEA_ID,
    "seed_terms": ["info.fog", "goal.cover"],
    "prose": {
        "title": "Fogbound Switchyard",
        "text": "Belts carry coloured crates past cycleable junctions toward matching pads.",
    },
}


# --------------------------------------------------------------------------
# helpers + fakes
# --------------------------------------------------------------------------


def _cfg() -> dict:
    return load_config(PILOT)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _idea() -> dict:
    return json.loads(IDEA_PATH.read_text(encoding="utf-8"))


def _flat(text: str) -> str:
    """Whitespace-normalised, so a re-wrapped prompt still matches."""
    return " ".join(text.split())


def _field(obj, name):
    """Kills/warns are contracted as {"rule", "detail"} dicts; tolerate small
    record objects with the same field names."""
    if isinstance(obj, Mapping):
        return obj[name]
    return getattr(obj, name)


def _rules(report) -> set[str]:
    return {_field(k, "rule") for k in report.kills}


def _details(report, rule: str) -> list[str]:
    return [str(_field(k, "detail")) for k in report.kills if _field(k, "rule") == rule]


def _why(report) -> str:
    """Readable assertion message: every kill, rule and detail."""
    return "; ".join(f"{_field(k, 'rule')}: {_field(k, 'detail')}" for k in report.kills)


def _stable(payload: dict) -> dict:
    """A report payload minus any wall-clock field — `ts` is run_s1's, not the
    pure validator's, and a timestamp inside `to_json_dict()` would make the
    purity comparison meaningless rather than false."""
    return {k: v for k, v in payload.items() if k not in ("ts", "timestamp")}


def _reply(spec_text: str, *, prose: str = PROSE) -> str:
    """One writer reply: prose, then EXACTLY ONE fenced yaml block."""
    return f"{prose}\n```yaml\n{spec_text.rstrip()}\n```\n"


def _fake_writer(reply: str, log: list[str] | None = None):
    """Stand-in for one spec-writer call. `*args/**kwargs` so wiring the
    contract does not fix (a model name, the idea, a stage label) cannot break
    it."""

    def runner(prompt: str, *args, **kwargs) -> str:
        if log is not None:
            log.append(prompt)
        return reply

    return runner


def _scripted_writer(replies: list[str], log: list[str] | None = None):
    """Returns each reply in turn; raises if called more often than scripted."""

    def runner(prompt: str, *args, **kwargs) -> str:
        if log is not None:
            log.append(prompt)
        if not replies:
            raise AssertionError("writer called more times than the contract allows")
        return replies.pop(0)

    return runner


def _hash_candidates(raw: bytes) -> set[str]:
    """sha256 of the spec.yaml text, allowing one trailing newline of slack
    between "the text that was extracted" and "the bytes on disk"."""
    variants = {raw, raw.rstrip(b"\n"), raw + b"\n"}
    return {hashlib.sha256(v).hexdigest() for v in variants}


def _near(flat: str, anchor: str, other: str, window: int = 60) -> bool:
    """True when `other` occurs within `window` characters of `anchor`."""
    pattern = rf"{re.escape(anchor)}.{{0,{window}}}{re.escape(other)}"
    reverse = rf"{re.escape(other)}.{{0,{window}}}{re.escape(anchor)}"
    return bool(
        re.search(pattern, flat, re.IGNORECASE) or re.search(reverse, flat, re.IGNORECASE)
    )


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def vocab() -> dict:
    """The signed 71-term vocabulary, straight off the read-only canon."""
    return load_vocab(_cfg())


@pytest.fixture(scope="module")
def good_spec_text() -> str:
    return _text(GOOD_PATH)


@pytest.fixture(autouse=True)
def _real_out_tree_untouched():
    """S1 writes a corpus tree. Every test here redirects it to tmp_path; this
    guard proves it, so a default `out_root` can never quietly publish a test
    spec into the repo."""
    out = REPO_ROOT / "out"

    def snapshot() -> dict[str, int]:
        if not out.is_dir():
            return {}
        return {
            str(p.relative_to(out)): p.stat().st_size
            for p in out.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }

    before = snapshot()
    yield
    assert snapshot() == before, "a test wrote into the repo's real out/ tree"


# --------------------------------------------------------------------------
# 0: the contract's own constants
# --------------------------------------------------------------------------


def test_contract_constants():
    assert KILL_RULES == (
        "schema",
        "unknown-terms",
        "objective-unwitnessed",
        "missing-knobs",
        "curriculum",
        "palette-collision",
        "undeclared-deception",
        "contradiction",
    )
    assert tuple(LOCI) == ("unique-mover", "selection", "click-only")
    assert tuple(REFUSALS) == ("visible", "free", "silent-charged")
    assert tuple(GOAL_LEGIBLE) == ("obvious", "inferable", "opaque")
    assert tuple(DANGER_TELLS) == ("unique-hue", "texture", "absence", "camouflage", "none")
    assert tuple(HUD_RESERVED) == ("row63", "row0", "col0", "custom-rect")
    # LEAD ADJUDICATION (wave 3, R-11): the tuple GROWS by `invert` — the
    # frozen head stays pinned exactly (the W2-D registry-growth precedent).
    assert tuple(RELATIONS)[:3] == ("new", "reuse", "compose")
    assert set(RELATIONS) >= {"new", "reuse", "compose", "invert"}
    assert (LEVELS_MIN, LEVELS_MAX) == (6, 10)

    # PIN UPDATE, contract E-1 (2026-10-05): `"camouflage"` is no longer a
    # catalog keyword of its own — it is a SPELLING of affordance §7.2 and folds
    # onto `palette overload`. The pin's intent (the two levers this file's
    # fixtures lean on are in the signed catalog, and the catalog is matched
    # lowercase) is kept by asking the question one level down: camouflage must
    # still DETECT, which is what the fixtures actually need of it.
    catalog = set(DECEPTION_CATALOG)
    assert {"decoy", "palette overload"} <= catalog
    assert detect_levers("camouflage") == ["palette overload"], (
        "the pre-E-1 keyword 'camouflage' must still detect, folding onto §7.2's lever"
    )
    assert all(w == w.lower() for w in catalog), "catalog keywords are matched lowercase"


def test_good_fixture_uses_only_contract_enums(good_spec_text):
    """The fixture is hand-written; this pins its enum choices to the module's
    own constants so a fixture typo shows up here and not as a mystery kill."""
    game = yaml.safe_load(good_spec_text)["game"]
    assert game["locus"] in LOCI
    assert game["knobs"]["refusal"] in REFUSALS
    assert game["knobs"]["goal_legible"] in GOAL_LEGIBLE
    assert game["knobs"]["danger_tell"] in DANGER_TELLS
    assert game["hud"]["reserved"] in HUD_RESERVED
    assert LEVELS_MIN <= len(game["levels"]) <= LEVELS_MAX
    assert all(lv["relation_to_prev"] in RELATIONS for lv in game["levels"])
    assert "reuse" in [lv["relation_to_prev"] for lv in game["levels"]]


# --------------------------------------------------------------------------
# 1: the good spec passes strict
# --------------------------------------------------------------------------


def test_good_spec_passes_strict(vocab, good_spec_text):
    spec = yaml.safe_load(good_spec_text)
    report = lint_spec(spec, vocab)

    assert _rules(report) == set(), f"hand-written §11 spec was killed — {_why(report)}"
    assert list(report.kills) == []
    assert report.passed, "passed must be True exactly when kills is empty"
    assert report.spec_hash == "", "lint_spec leaves spec_hash empty; run_s1 fills it"

    payload = report.to_json_dict()
    assert isinstance(payload, dict)
    assert set(payload) >= {"passed", "kills", "warns", "spec_hash"}
    assert payload["passed"] is True
    assert payload["kills"] == []
    assert isinstance(payload["warns"], list)


def test_good_spec_passes_strict_against_its_idea(vocab, good_spec_text):
    """The fixture tracks the real pilot idea on purpose — same idea_ref, same
    objective family, every seed term present — so passing the idea in must not
    change the verdict."""
    spec = yaml.safe_load(good_spec_text)
    idea = _idea()
    game = spec["game"]

    assert game["idea_ref"] == idea["id"]
    assert set(idea["seed_terms"]) <= set(game["terms"])
    assert game["objective"]["primary"] == idea["objective"]["primary"]

    report = lint_spec(spec, vocab, idea)
    assert _rules(report) == set(), f"good spec + its own idea was killed — {_why(report)}"
    assert report.passed


def test_good_spec_terms_are_vocabulary(vocab, good_spec_text):
    game = yaml.safe_load(good_spec_text)["game"]
    assert set(game["terms"]) <= set(vocab), "fixture terms must be the signed 71"
    for level in game["levels"]:
        assert set(level["terms_introduced"]) <= set(game["terms"])
    witnesses = WITNESS_MAP[game["objective"]["primary"]]
    assert set(witnesses) & set(game["terms"]), "the declared family must be witnessed"


# --------------------------------------------------------------------------
# 2: one bad fixture per kill rule
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "rule", "also_allowed", "coupling"),
    BAD_CASES,
    ids=[case[0].removesuffix(".yaml") for case in BAD_CASES],
)
def test_each_bad_fixture_killed_by_its_rule(vocab, name, rule, also_allowed, coupling):
    """Each fixture is the good spec with ONE change, so a second rule firing
    means the linter over-reaches (or the fixture drifted). The one documented
    exception is spelled out in BAD_CASES."""
    assert rule in KILL_RULES
    report = lint_spec(_load(BAD_DIR / name), vocab)

    assert not report.passed, f"{name} must not pass"
    fired = _rules(report)
    assert rule in fired, f"{name} must trip {rule!r}, got {sorted(fired)} — {_why(report)}"
    assert fired <= KILL_RULES_SET, f"{name} reported a rule outside KILL_RULES: {sorted(fired)}"
    extra = fired - {rule} - set(also_allowed)
    assert not extra, (
        f"{name} is a one-change mutation of good-spec.yaml but also tripped "
        f"{sorted(extra)} — {_why(report)}"
        + (f" (accepted coupling: {coupling})" if coupling else "")
    )


def test_every_kill_rule_has_a_fixture():
    """`schema` through `contradiction`: the suite must exercise all eight."""
    covered = {rule for _, rule, _, _ in BAD_CASES}
    assert covered == KILL_RULES_SET, f"kill rules with no fixture: {KILL_RULES_SET - covered}"


def test_kill_details_name_offenders(vocab):
    """A kill that does not say WHICH field is a kill the writer cannot fix."""
    unknown = lint_spec(_load(BAD_DIR / "unknown-term.yaml"), vocab)
    details = _details(unknown, "unknown-terms")
    assert details, "unknown-terms kill carries no detail"
    assert any(BOGUS_TERM in d for d in details), (
        f"the detail must name the offending term {BOGUS_TERM!r}: {details}"
    )
    assert not any("goal.cover" in d for d in details), "valid terms must not be reported"

    short = lint_spec(_load(BAD_DIR / "level-count-5.yaml"), vocab)
    details = _details(short, "curriculum")
    assert details, "curriculum kill carries no detail"
    assert any(re.search(r"\b5\b", d) for d in details), (
        f"the detail must name the level count it measured: {details}"
    )

    decoy = lint_spec(_load(BAD_DIR / "sketch-undeclared-decoy.yaml"), vocab)
    details = _details(decoy, "undeclared-deception")
    assert details and any("decoy" in d.lower() for d in details), (
        f"the detail must name the catalog keyword it found: {details}"
    )


# --------------------------------------------------------------------------
# 3: the validator is pure
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["good-spec.yaml", "bad/unknown-term.yaml"])
def test_validator_pure(vocab, name):
    spec = _load(FIXTURES / name)
    untouched = deepcopy(spec)

    first = lint_spec(spec, vocab)
    second = lint_spec(spec, vocab)

    assert spec == untouched, "lint_spec mutated the spec dict it was handed"
    assert first.passed == second.passed
    assert list(first.kills) == list(second.kills)
    assert list(first.warns) == list(second.warns)
    assert first.spec_hash == second.spec_hash
    assert _stable(first.to_json_dict()) == _stable(second.to_json_dict())


# --------------------------------------------------------------------------
# 4: id + reply parsing
# --------------------------------------------------------------------------


def test_batch_of_idea_id():
    assert batch_of_idea_id(IDEA_ID) == BATCH_ID
    assert batch_of_idea_id("b002-alpha-beta-i042") == "b002-alpha-beta"

    for malformed in ("", "b001-pilot", "b001-pilot-001", "-i001", "i001"):
        with pytest.raises(ValueError):
            batch_of_idea_id(malformed)


def test_extract_spec_yaml_last_block_wins():
    first = "game:\n  slug: first-draft\n"
    second = "game:\n  slug: second-draft\n  title: Second\n"
    reply = (
        "Here is a first pass.\n\n"
        f"```yaml\n{first}```\n\n"
        "On reflection the slug was wrong, so here is the final spec.\n\n"
        f"```yaml\n{second}```\n"
    )

    raw, spec = extract_spec_yaml(reply)

    assert spec == {"game": {"slug": "second-draft", "title": "Second"}}
    assert raw.strip() == second.strip()
    assert "first-draft" not in raw, "the LAST block is the spec; earlier ones are drafts"


def test_extract_spec_yaml_round_trips_the_good_fixture(good_spec_text):
    raw, spec = extract_spec_yaml(_reply(good_spec_text))
    assert spec == yaml.safe_load(good_spec_text)
    assert _flat(raw) == _flat(good_spec_text)


@pytest.mark.parametrize(
    ("reply", "why"),
    [
        ("No yaml here at all, just an apology and a plan.\n", "no fenced yaml block"),
        ("```yaml\ngame: [unclosed\n```\n", "unparseable yaml"),
        ("```yaml\nspec:\n  slug: wrong-root\n```\n", "no top-level `game` key"),
    ],
    ids=["no-block", "unparseable", "no-game-key"],
)
def test_extract_spec_yaml_rejects(reply, why):
    with pytest.raises(ValueError) as excinfo:
        extract_spec_yaml(reply)
    assert str(excinfo.value).strip(), f"the ValueError for {why} must say what was wrong"


# --------------------------------------------------------------------------
# 5: the writer prompt
# --------------------------------------------------------------------------


def test_writer_prompt_contents():
    cfg = _cfg()
    idea = _idea()
    prompt = build_writer_prompt(cfg, idea)
    flat = _flat(prompt)

    # doctrine verbatim, FIRST
    assert prompt.lstrip().splitlines()[0].startswith("You are designing"), (
        "the vendored spec doctrine must come first, verbatim"
    )

    # the idea: prose + every seed term
    assert idea["prose"]["title"] in prompt
    assert _flat(idea["prose"]["text"]) in flat, "the idea's prose must be carried verbatim"
    for term in idea["seed_terms"]:
        assert term in prompt, f"seed term {term} missing from the prompt"
    assert re.search(r"(?i)must (?:include|contain|list)[^.]{0,80}seed term", flat), (
        "the prompt must say the terms list MUST include every seed term"
    )

    # the action mapping (UP=ACTION1 ... click=ACTION6, ACTION7=undo)
    assert _near(flat, "ACTION1", "UP", window=30)
    assert _near(flat, "ACTION6", "click", window=30)
    assert _near(flat, "ACTION7", "undo", window=30)

    # the level-count line
    levels = re.search(r"6\s*(?:-|–|—|to)\s*10", flat)
    assert levels, "the 6-10 levels line is missing"
    assert "level" in flat[max(0, levels.start() - 60):levels.end() + 60].lower()

    # no numeric budgets — asserted by CONTENT, not by verb: some sentence must
    # forbid (never / do not) numeric (numeric / number / exact) budgets. The
    # implementer's choice of verb is not the contract.
    sentences = re.split(r"(?<=[.!?])\s+", flat)
    forbids_budgets = [
        s
        for s in sentences
        if re.search(r"(?i)\b(?:never|do not|don't|no)\b", s)
        and re.search(r"(?i)budget", s)
        and re.search(r"(?i)numeric|number|exact", s)
    ]
    assert forbids_budgets, "the no-numeric-budgets instruction is missing"

    # the §3b witness lines (read as the crosswalk, plural)
    assert re.search(r"(?i)witness", flat), "the §3b witness obligation is missing"
    assert idea["objective"]["primary"] in prompt
    witness_terms = {t for terms in WITNESS_MAP.values() for t in terms}
    present = {t for t in witness_terms if t in prompt}
    assert len(present) >= 2, f"expected the §3b crosswalk, found only {sorted(present)}"

    # the D28 crosswalk + the schema fence
    assert "Common mechanic names" in prompt
    assert "```yaml" in prompt, "the §11 schema must be shown as a fenced yaml block"
    for key in (
        "relation_to_prev",
        "terms_introduced",
        "neg2_readers",
        "solver_notes",
        "danger_tell",
        "idea_ref",
    ):
        assert key in prompt, f"the schema block is missing {key}"

    # the closing instruction
    closing = list(re.finditer(r"(?i)exactly one", flat))
    assert closing, "the reply must be told to end with EXACTLY ONE fenced yaml block"
    tail = flat[closing[-1].start():closing[-1].start() + 160].lower()
    assert "yaml" in tail, f"'exactly one' must be about the yaml block: {tail!r}"


def test_writer_prompt_demands_structural_layout_variation():
    """spec-v0.3 §7 / D13 bind the SPEC, not only the implementer.

    §7 makes level layouts functions of `layout.seed` — structure varies,
    the spec holds — so the writer has to ask for that in the `layout:` block
    and in the prose around it. The failure mode is not hypothetical: the B5
    pilot spec's own prose scoped `layout.seed` to "cosmetic placement
    jitter", which is the promise Tufa's generator left unkept, and a game
    built to it is one `gen/s6_package.py` refuses.

    Self-contained on purpose: the §7 block is static prompt text, so this
    builds a minimal idea rather than reading one out of `out/`.
    """
    prompt = build_writer_prompt(_cfg(), MINIMAL_IDEA)
    flat = _flat(prompt)

    # the block exists and cites its authority
    assert "layout.seed" in prompt, "the §7 block must name the field it governs"
    start = flat.index("layout.seed")
    following = flat.find("###", start)
    block = flat[start:following] if following != -1 else flat[start:]
    assert "§7" in block and "D13" in block, "spec-v0.3 §7 + D13 are the authority"

    # STRUCTURAL variation, named by its three canon nouns (spec §7: "walls,
    # object placement, distances")
    assert re.search(r"(?i)structural", block), "the block must demand STRUCTURAL variation"
    for noun in ("wall", "placement", "distance"):
        assert re.search(rf"(?i){noun}", block), f"§7 names {noun}s as what must vary"

    # the anti-cosmetic language + the failure mode, named
    assert _near(block, "cosmetic", "never", window=90), (
        "the prompt must FORBID scoping layout.seed to cosmetics, not merely "
        "prefer structure"
    )
    assert re.search(r"(?i)cosmetic jitter", block), (
        "the stale pilot spec's own words are the failure mode to name"
    )
    assert re.search(r"(?i)tufa", block) and re.search(r"(?i)structural variants", block), (
        "the block must say whose promise this was and what it cost"
    )


# --------------------------------------------------------------------------
# 6: run_s1 — the corpus tree
# --------------------------------------------------------------------------


def test_run_s1_writes_corpus_tree(tmp_path, good_spec_text):
    cfg = _cfg()
    log: list[str] = []
    result = run_s1(
        IDEA_PATH,
        cfg,
        writer_runner=_fake_writer(_reply(good_spec_text), log),
        out_root=tmp_path,
    )

    assert len(log) == 1, "a well-formatted reply must not be retried"
    assert result.prompt == log[0], "S1Result.prompt must be the prompt the writer got"
    assert result.report.passed, f"the hand-written spec was killed — {_why(result.report)}"
    assert list(result.report.kills) == []

    # <out_root>/<batch>/<slug>/
    out_dir = Path(result.out_dir).resolve()
    assert out_dir.name == GOOD_SLUG
    assert out_dir.parent.name == BATCH_ID
    assert out_dir.parent.parent == tmp_path.resolve()
    for name in CORPUS_FILES:
        assert (out_dir / name).is_file(), f"{name} was not written"

    # spec.yaml is the block, byte for byte modulo trailing whitespace
    spec_yaml = out_dir / "spec.yaml"
    assert _text(spec_yaml).strip() == good_spec_text.strip()
    assert yaml.safe_load(_text(spec_yaml)) == yaml.safe_load(good_spec_text)
    assert result.spec == yaml.safe_load(good_spec_text)
    assert _flat(good_spec_text) in _flat(result.spec_text)

    # spec.md keeps the writer's reply around
    assert PROSE.splitlines()[0] in _text(out_dir / "spec.md")

    # spec_hash = sha256 of the spec.yaml text
    digests = _hash_candidates(spec_yaml.read_bytes())
    assert result.report.spec_hash in digests, "spec_hash must be sha256 of the spec.yaml text"
    assert len(result.report.spec_hash) == 64

    # idea.json is a copy of the input, not a re-serialisation
    copied = out_dir / "idea.json"
    assert json.loads(_text(copied)) == _idea()
    assert copied.read_bytes() == IDEA_PATH.read_bytes(), (
        "idea.json must be a byte-equal copy of the S0 idea"
    )

    # lint-report.json
    payload = json.loads(_text(out_dir / "lint-report.json"))
    assert set(payload) >= set(REPORT_FIELDS), f"missing {set(REPORT_FIELDS) - set(payload)}"
    assert payload["passed"] is True
    assert payload["kills"] == []
    assert isinstance(payload["warns"], list)
    assert payload["spec_hash"] == result.report.spec_hash
    assert payload["idea_ref"] == IDEA_ID
    ts = payload["ts"]
    assert (isinstance(ts, str) and ts.strip()) or (isinstance(ts, (int, float)) and ts > 1.7e9)


def test_run_s1_kill_persists_artifacts(tmp_path):
    """A killed spec is still evidence: the corpus entry must exist so the
    failure can be read, diffed and re-run."""
    cfg = _cfg()
    bad_text = _text(BAD_DIR / "palette-reserved-collision.yaml")
    result = run_s1(
        IDEA_PATH,
        cfg,
        writer_runner=_fake_writer(_reply(bad_text)),
        out_root=tmp_path,
    )

    assert not result.report.passed, "a palette collision must not pass"
    assert "palette-collision" in _rules(result.report)

    out_dir = Path(result.out_dir).resolve()
    for name in CORPUS_FILES:
        assert (out_dir / name).is_file(), f"{name} missing after a kill"
    assert _text(out_dir / "spec.yaml").strip() == bad_text.strip()

    payload = json.loads(_text(out_dir / "lint-report.json"))
    assert payload["passed"] is False
    assert payload["kills"], "the report must carry the kill that stopped the spec"
    assert {_field(k, "rule") for k in payload["kills"]} <= KILL_RULES_SET
    assert payload["spec_hash"] == result.report.spec_hash
    digests = _hash_candidates((out_dir / "spec.yaml").read_bytes())
    assert result.report.spec_hash in digests


def test_format_retry_then_raise(tmp_path):
    """A reply with no yaml block buys exactly ONE retry, then it is a hard
    error — never a silent pass and never an unbounded loop."""
    cfg = _cfg()
    log: list[str] = []
    runner = _fake_writer("I could not fit this into yaml, sorry.\n", log)

    with pytest.raises(RuntimeError):
        run_s1(IDEA_PATH, cfg, writer_runner=runner, out_root=tmp_path)

    assert len(log) == 2, f"expected one call + one retry, got {len(log)}"


def test_format_retry_then_success(tmp_path, good_spec_text):
    """The other half of the same rule: the retry is a real second chance."""
    cfg = _cfg()
    log: list[str] = []
    runner = _scripted_writer(["No yaml block here.\n", _reply(good_spec_text)], log)

    result = run_s1(IDEA_PATH, cfg, writer_runner=runner, out_root=tmp_path)

    assert len(log) == 2, "the malformed reply must cost exactly one retry"
    assert result.report.passed, _why(result.report)
    assert (Path(result.out_dir) / "spec.yaml").is_file()


def test_negated_deception_mention_is_not_a_kill():
    """Adjudicated 2026-09-21 (first live kill was this false positive): a
    sketch DENYING fake depth — 'load-bearing, not a decoy' — must not fire
    undeclared-deception; a positive mention still must."""
    import copy

    import yaml as _yaml

    from gen.s0_ideas import load_vocab
    from gen.s1_spec import lint_spec

    good = _yaml.safe_load(FIXTURES.joinpath("good-spec.yaml").read_text(encoding="utf-8"))
    vocab = set(load_vocab(_cfg()))

    negated = copy.deepcopy(good)
    negated["game"]["levels"][2]["sketch"] += " The discard branch is load-bearing, not a decoy."
    report = lint_spec(negated, vocab)
    assert report.passed, [k["detail"] for k in report.kills]

    positive = copy.deepcopy(good)
    positive["game"]["levels"][2]["sketch"] += " A decoy switch blinks near the exit."
    report = lint_spec(positive, vocab)
    assert any(k["rule"] == "undeclared-deception" for k in report.kills)
