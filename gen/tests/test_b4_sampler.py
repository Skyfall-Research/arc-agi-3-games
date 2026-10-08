"""B4 acceptance: the S0 idea sampler — tested from the spec, not from the code.

Run: .venv/bin/python -m pytest gen/tests/test_b4_sampler.py -v

Written against the B4 contract while `gen/s0_ideas.py` was implemented in
parallel; nothing here was read off the implementation. Every test loads the
REAL pilot config, so the real duckWM canon tables are exercised (read-only),
and every prose call is an INJECTED fake: no agent session, no API call, ever.
`prose_runner=` is therefore passed on EVERY sampler call — the default (None)
is the live backend, and a test that forgot it would dial out.

Two canon/config facts these tests encode on purpose:

  * `term-occurrence-final.csv` carries 72 rows but the vocabulary is 71. The
    extra row is `budget.time` — kept-but-unverified at the v2 sign-off and
    NOT a column of the signed 190x71 matrix. `test_vocab_loads_71_terms`
    pins the 71 to the matrix columns instead of to a magic number, so the
    failure message says which term is meant to go.
  * `config/b001-pilot.yaml` has no `batch.seed`. Every sample_batch call here
    passes `seed=` explicitly and no test reads that key.

Statistical tests share one fixed-seed draw per size (module-scoped), so a
share that drifts is a real bug and not seed luck: at n=2000 a +-0.05 band is
>4 sigma for every share asserted.
"""

from __future__ import annotations

import csv
import json
import random
import re
from collections.abc import Mapping
from copy import deepcopy
from itertools import combinations
from pathlib import Path

import pytest

from gen import s0_ideas
from gen.config import REPO_ROOT, load_config
from gen.s0_ideas import (
    FAILURE_FAMILIES,
    FAMILY_RECIPES,
    OBJECTIVE_FAMILIES,
    WITNESS_MAP,
    load_objective_distribution,
    load_vocab,
    sample_batch,
    sample_idea,
    validate_idea_dict,
)

PILOT = "config/b001-pilot.yaml"
TIERS = ("t1", "t2", "t3")
LOCI = ("mover", "selection", "click")
COUNT_COLUMNS = ("tufa_live", "tufa_dead", "official")

# The fake's reply and the two fields the contract says it parses into.
# The body must satisfy S0's prose gate (R2 coherence pass: >= 400 chars, no
# narration or tool fragments) — the gate runs inside sample_idea, so an
# 18-char stub here fails every draw before the term logic under test runs.
PROSE_TITLE = "Test Title"
PROSE_TEXT = (
    "A compact test arena where a lone selector sweeps across a five by five "
    "board of tiles. Some tiles hide a target glyph, and clicking a tile "
    "reveals it, while blocked cells force the sweep into detours that cost "
    "extra moves. The player must cover every target pad before the sweep "
    "counter runs out, learning board by board which routes waste turns. "
    "Later boards add a second glyph colour and a locked row that opens only "
    "when the first colour is fully covered, so plans must interleave the "
    "two colours without stranding the selector behind its own reveals."
)
PROSE_REPLY = f"{PROSE_TITLE}\n{PROSE_TEXT}"

# One seed per draw size; reused across the statistical tests on purpose.
BIG_SEED = 20260921
BIG_N = 2000
MID_SEED = 424242
MID_N = 500

HISTORY_NAME = "dedupe-history.jsonl"


# --------------------------------------------------------------------------
# fakes + accessors
# --------------------------------------------------------------------------


def _fake_prose(log: list[str] | None = None, reply: str = PROSE_REPLY):
    """Stand-in for one prose call. Takes the prompt, optionally records it,
    returns the canned two-line reply. `*args/**kwargs` so extra wiring the
    contract does not fix (a model name, the idea skeleton) cannot break it."""

    def runner(prompt: str, *args, **kwargs) -> str:
        if log is not None:
            log.append(prompt)
        return reply

    return runner


def _field(obj, name):
    """The contract fixes field NAMES, not containers: an Idea's sub-objects
    may be plain dicts or small dataclasses. `to_json_dict()` output is always
    a dict and is asserted as one."""
    if isinstance(obj, Mapping):
        return obj[name]
    return getattr(obj, name)


def _primary(idea) -> str:
    return _field(_field(idea, "objective"), "primary")


def _secondary(idea):
    return _field(_field(idea, "objective"), "secondary")


def _terms(idea) -> tuple[str, ...]:
    return tuple(_field(idea, "seed_terms"))


def _locus(idea) -> str:
    return _field(_field(idea, "mix_class"), "locus")


def _hazardless(idea) -> bool:
    return _field(_field(idea, "mix_class"), "hazardless")


def _prose_field(idea, name) -> str:
    return _field(_field(idea, "prose"), name)


def _key(terms, primary: str) -> str:
    """The dedupe key, spelled exactly as the contract spells it."""
    return "|".join(sorted(terms)) + "::" + primary


def _cfg() -> dict:
    return load_config(PILOT)


def draw(n: int, *, seed: int, cfg: dict | None = None, batch_id: str = "b001", **kwargs):
    """n ideas off ONE rng — the S0 draw loop minus batch bookkeeping."""
    cfg = _cfg() if cfg is None else cfg
    runner = kwargs.pop("prose_runner", None) or _fake_prose()
    rng = random.Random(seed)
    return [
        sample_idea(cfg, rng, batch_id=batch_id, index=i + 1, prose_runner=runner, **kwargs)
        for i in range(n)
    ]


def _share(values, predicate) -> float:
    return sum(1 for v in values if predicate(v)) / len(values)


# --------------------------------------------------------------------------
# canon readers (read-only; duckWM is a read-only dependency)
# --------------------------------------------------------------------------


def _canon_rows(cfg: dict, rel: str) -> list[dict]:
    path = Path(cfg["duckwm_docs"]) / rel
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _occurrence_counts(cfg: dict) -> dict[str, dict[str, int]]:
    rows = _canon_rows(cfg, "mechanics/term-occurrence-final.csv")
    return {r["term"]: {c: int(r[c]) for c in COUNT_COLUMNS} for r in rows}


def _matrix_terms(cfg: dict) -> list[str]:
    """The term columns of the signed 190x71 matrix — the vocabulary proper."""
    path = Path(cfg["duckwm_docs"]) / "mechanics/game-term-matrix.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        header = csv.DictReader(fh).fieldnames or []
    return [col for col in header if "." in col]


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _protect_real_history(tmp_path, monkeypatch):
    """`sample_batch` appends REPO_ROOT/out/ideas/dedupe-history.jsonl. Tests
    must neither depend on nor mutate the real out/ tree, so: redirect any
    module-level Path constant that points at the history file (works whatever
    the implementer named it), and snapshot/restore the real file regardless,
    so the repo is byte-identical after the run either way."""
    real = REPO_ROOT / "out" / "ideas" / HISTORY_NAME
    before = real.read_bytes() if real.is_file() else None
    dir_existed = real.parent.is_dir()

    redirect = tmp_path / "history" / HISTORY_NAME
    redirect.parent.mkdir(parents=True, exist_ok=True)
    for name, value in list(vars(s0_ideas).items()):
        if isinstance(value, Path) and value.name == HISTORY_NAME:
            monkeypatch.setattr(s0_ideas, name, redirect, raising=False)

    yield

    if before is None:
        if real.is_file():
            real.unlink()
        if not dir_existed and real.parent.is_dir():
            try:
                real.parent.rmdir()
            except OSError:
                pass
    elif not real.is_file() or real.read_bytes() != before:
        # Restore ONLY a real change: rewriting identical bytes still moved the
        # file's mtime on every run (contract OS-2 FRONT C.2, the hermeticity fix).
        real.write_bytes(before)


@pytest.fixture(scope="module")
def vocab_terms() -> set[str]:
    return set(load_vocab(_cfg()))


@pytest.fixture(scope="module")
def big_draw():
    """n=2000 off one fixed seed: shared by the share/coverage tests."""
    return draw(BIG_N, seed=BIG_SEED)


@pytest.fixture(scope="module")
def mid_draw():
    """n=500 off one fixed seed: shared by the per-idea invariant tests."""
    return draw(MID_N, seed=MID_SEED)


# --------------------------------------------------------------------------
# 1 + extra: the canon tables behind the sampler
# --------------------------------------------------------------------------


def test_vocab_loads_71_terms():
    cfg = _cfg()
    vocab = load_vocab(cfg)
    matrix = _matrix_terms(cfg)
    occurrence = _occurrence_counts(cfg)

    assert len(matrix) == 71, "canon drift: game-term-matrix.csv no longer has 71 term columns"
    assert len(occurrence) == 72, "canon drift: term-occurrence-final.csv no longer has 72 rows"
    assert len(vocab) == 71, (
        "the vocabulary is 71 terms, but term-occurrence-final.csv carries 72 rows: "
        "budget.time is the extra (kept-unverified at v2 sign-off, and not a column of "
        f"the signed 190x71 matrix). Got {len(vocab)}."
    )
    assert set(vocab) == set(matrix), "the vocabulary must be exactly the matrix's term columns"
    assert "budget.time" not in vocab, "budget.time is outside the 190x71 matrix"

    for term in vocab:
        entry = vocab[term]
        got = {col: int(_field(entry, col)) for col in COUNT_COLUMNS}
        assert got == occurrence[term], f"{term}: counts must come from term-occurrence-final.csv"


def test_objective_distribution_matches_canon():
    """Not on the numbered list, but `load_objective_distribution` is public
    surface and otherwise untested; it is also what makes the reach cap mean
    something. Assumption: it counts every objectives.csv row (190: 165 tufa +
    25 officials) — if the sampler is meant to weight one corpus only, this
    sum is the line to renegotiate."""
    cfg = _cfg()
    dist = load_objective_distribution(cfg)
    rows = _canon_rows(cfg, "mechanics/objectives.csv")

    assert set(dist) == set(OBJECTIVE_FAMILIES), "every objective family must carry a count"
    assert all(isinstance(v, int) and v > 0 for v in dist.values()), dist
    top = max(dist, key=lambda fam: dist[fam])
    assert top == "reach_goal", "reach_goal dominates the corpus — that is why it is capped"
    assert dist["reach_goal"] / sum(dist.values()) > 0.25, (
        "the raw corpus share of reach_goal must exceed reach_cap, or the cap is a no-op"
    )
    assert sum(dist.values()) == len(rows) == 190


# --------------------------------------------------------------------------
# 2: shape + validator round-trip
# --------------------------------------------------------------------------


def test_idea_shape_and_validator_roundtrip(vocab_terms):
    idea = draw(1, seed=11)[0]

    assert idea.id == "b001-i001"
    terms = _terms(idea)
    assert 2 <= len(terms) <= 4 and len(set(terms)) == len(terms)
    assert set(terms) <= vocab_terms
    assert _primary(idea) in OBJECTIVE_FAMILIES
    assert _secondary(idea) is None, "the contract pins secondary to None"
    assert idea.failure_family is None or idea.failure_family in FAILURE_FAMILIES
    assert idea.tier in TIERS
    assert isinstance(_hazardless(idea), bool)
    assert _locus(idea) in LOCI
    assert _prose_field(idea, "title") == PROSE_TITLE
    assert _prose_field(idea, "text") == PROSE_TEXT
    assert idea.dedupe_key == _key(terms, _primary(idea))

    payload = idea.to_json_dict()
    assert isinstance(payload, dict)
    assert set(payload) >= {
        "id",
        "seed_terms",
        "objective",
        "failure_family",
        "tier",
        "mix_class",
        "prose",
        "dedupe_key",
    }
    assert payload["id"] == idea.id and payload["dedupe_key"] == idea.dedupe_key
    assert list(payload["seed_terms"]) == list(terms)
    assert payload["prose"]["title"] == PROSE_TITLE

    assert validate_idea_dict(payload, vocab_terms) == []
    reloaded = json.loads(json.dumps(payload))
    assert validate_idea_dict(reloaded, vocab_terms) == [], "must survive a JSON round-trip"


# --------------------------------------------------------------------------
# 3-5: per-idea invariants over 500 draws
# --------------------------------------------------------------------------


def test_witnessed_by_construction(mid_draw):
    for idea in mid_draw:
        primary = _primary(idea)
        witnesses = set(WITNESS_MAP[primary])
        assert witnesses & set(_terms(idea)), (
            f"{idea.id}: primary={primary} needs one of {sorted(witnesses)} "
            f"in seed_terms {sorted(_terms(idea))}"
        )


def test_recipe_term_present_when_family_set(mid_draw):
    seeded = [idea for idea in mid_draw if idea.failure_family is not None]
    assert len(seeded) > 50, f"only {len(seeded)}/{len(mid_draw)} ideas carry a failure family"
    for idea in seeded:
        recipe = set(FAMILY_RECIPES[idea.failure_family])
        assert recipe & set(_terms(idea)), (
            f"{idea.id}: failure_family={idea.failure_family} needs one of {sorted(recipe)} "
            f"in seed_terms {sorted(_terms(idea))}"
        )


def test_terms_unique_in_vocab_and_n_in_range(mid_draw, vocab_terms):
    lo, hi = _cfg()["ideas"]["seed_terms_per_idea"]
    sizes = set()
    for idea in mid_draw:
        terms = _terms(idea)
        assert len(set(terms)) == len(terms), f"{idea.id}: repeated seed term in {terms}"
        assert set(terms) <= vocab_terms, f"{idea.id}: off-vocabulary term in {terms}"
        assert lo <= len(terms) <= hi, f"{idea.id}: {len(terms)} terms, config allows [{lo},{hi}]"
        sizes.add(len(terms))
    assert {lo, hi} <= sizes, (
        f"both ends of seed_terms_per_idea=[{lo},{hi}] must occur in {MID_N} draws; saw {sizes}"
    )


# --------------------------------------------------------------------------
# 6-9: distributional guarantees over 2000 draws
# --------------------------------------------------------------------------


def test_reach_cap(big_draw):
    """The cap is a CEILING, not a target (lead adjudication 2026-09-21).

    Coverage steering legitimately holds reach_goal LOW while the measured
    corpus is reach-saturated (98/190): the deficit boost lifts the other
    seven families, so reach's weight sits well under the cap today. The
    cap exists for the day the generated corpus erodes those deficits and
    reach's weight climbs — binding is unit-tested in
    test_reach_cap_binds_when_weights_exceed_it. Here: capped above,
    drawable below.
    """
    share = _share(big_draw, lambda idea: _primary(idea) == "reach_goal")
    assert share <= 0.28, f"reach_goal share {share:.3f} breaks the 0.25 cap"
    assert share > 0.04, f"reach_goal share {share:.3f}: the cap must not become a ban"


def test_reach_cap_binds_when_weights_exceed_it():
    """Force reach's pre-cap weight over the cap via its FLOOR (floors are
    config): the capped probability must be exactly reach_cap."""
    import copy

    from gen.s0_ideas import objective_weights

    cfg = copy.deepcopy(_cfg())
    cfg["batch"]["mix"]["objective"]["floors"]["reach_goal"] = 50
    weights = objective_weights(cfg)
    share = weights["reach_goal"] / sum(weights.values())
    assert share == pytest.approx(0.25, abs=1e-9), (
        f"reach_goal floored at 50 must be capped to exactly 0.25, got {share:.4f}"
    )


def test_seed_defaults_to_config_batch_seed(tmp_path):
    """seed=None must fall back to cfg batch.seed deterministically — a
    sampler that silently used entropy there would break reproducibility."""
    from gen.s0_ideas import sample_batch

    runner = _fake_prose()
    a = sample_batch(_cfg(), batch_id="b-seedcfg", seed=None, prose_runner=runner,
                     out_dir=tmp_path / "a")
    b = sample_batch(_cfg(), batch_id="b-seedcfg", seed=None, prose_runner=runner,
                     out_dir=tmp_path / "b")
    assert [i.to_json_dict() for i in a] == [i.to_json_dict() for i in b]
    assert (tmp_path / "a/idea-001.json").read_bytes() == (
        tmp_path / "b/idea-001.json"
    ).read_bytes()


def test_all_families_reachable(big_draw):
    seen = {_primary(idea) for idea in big_draw}
    assert seen == set(OBJECTIVE_FAMILIES), f"unreachable families: {set(OBJECTIVE_FAMILIES) - seen}"

    families = {idea.failure_family for idea in big_draw if idea.failure_family is not None}
    assert families == set(FAILURE_FAMILIES), (
        f"unreachable failure families: {set(FAILURE_FAMILIES) - families}"
    )


def test_failure_family_share(big_draw):
    want = _cfg()["ideas"]["failure_family_share"]
    assert want == 0.4, "pilot config drifted from failure_family_share=0.4"
    share = _share(big_draw, lambda idea: idea.failure_family is not None)
    assert share == pytest.approx(want, abs=0.05), f"failure-family share {share:.3f} != ~{want}"


def test_mix_shares(big_draw):
    mix = _cfg()["batch"]["mix"]
    assert mix["hazardless"] == 0.5 and mix["locus"]["click"] == 0.24
    tiers = _cfg()["batch"]["tiers"]
    assert tiers["t3"] == 0.2

    hazardless = _share(big_draw, _hazardless)
    click = _share(big_draw, lambda idea: _locus(idea) == "click")
    t3 = _share(big_draw, lambda idea: idea.tier == "t3")

    assert hazardless == pytest.approx(0.5, abs=0.05), f"hazardless share {hazardless:.3f}"
    assert click == pytest.approx(0.24, abs=0.05), f"locus=click share {click:.3f}"
    assert t3 == pytest.approx(0.2, abs=0.05), f"tier t3 share {t3:.3f}"


# --------------------------------------------------------------------------
# 10: determinism
# --------------------------------------------------------------------------


def test_determinism_same_seed_byte_identical(tmp_path):
    """Batch of 12 rather than the pilot's 1, so 'a different seed differs' is
    a statement about twelve draws and not a coin flip."""
    cfg = _cfg()
    cfg["batch"]["size"] = 12
    runs: dict[str, list] = {}
    dirs: dict[str, Path] = {}
    for label, seed in (("a", 7), ("b", 7), ("c", 8)):
        out = tmp_path / label
        out.mkdir(parents=True, exist_ok=True)
        runs[label] = sample_batch(
            cfg, batch_id="b001", seed=seed, prose_runner=_fake_prose(), out_dir=out
        )
        dirs[label] = out

    names = sorted(p.name for p in dirs["a"].glob("idea-*.json"))
    assert len(names) == 12, f"sample_batch must write one file per idea; wrote {names}"
    assert names == sorted(p.name for p in dirs["b"].glob("idea-*.json"))
    for name in names:
        assert (dirs["a"] / name).read_bytes() == (dirs["b"] / name).read_bytes(), (
            f"{name} differs between two runs at the same seed"
        )

    ids = [idea.id for idea in runs["a"]]
    assert len(set(ids)) == 12
    assert all(re.fullmatch(r"b001-i\d{3}", i) for i in ids), ids
    assert {f"idea-{i.split('-i')[1]}.json" for i in ids} == set(names), (
        "each idea's file must be named for its own index"
    )

    keys = {label: [idea.dedupe_key for idea in ideas] for label, ideas in runs.items()}
    assert keys["a"] == keys["b"]
    assert keys["a"] != keys["c"], "a different seed must produce a different batch"


# --------------------------------------------------------------------------
# 11-12: dedupe
# --------------------------------------------------------------------------


def test_dedupe_key_format_and_rejection():
    cfg = _cfg()
    seed = 99
    base = draw(1, seed=seed, cfg=cfg)[0]
    terms, primary = _terms(base), _primary(base)

    assert base.dedupe_key == _key(terms, primary)
    head, sep, tail = base.dedupe_key.partition("::")
    assert sep == "::" and base.dedupe_key.count("::") == 1
    assert head.split("|") == sorted(terms)
    assert tail == primary

    control = draw(1, seed=seed, cfg=cfg)[0]
    assert control.dedupe_key == base.dedupe_key, "same seed must reproduce the same draw"

    for kwarg in ("known_keys", "exclude_keys"):
        rng = random.Random(seed)
        fresh = sample_idea(
            cfg,
            rng,
            batch_id="b001",
            index=1,
            prose_runner=_fake_prose(),
            **{kwarg: frozenset({base.dedupe_key})},
        )
        assert fresh.dedupe_key != base.dedupe_key, f"{kwarg} was not honoured"
        assert fresh.dedupe_key == _key(_terms(fresh), _primary(fresh))


def test_dedupe_exhaustion_raises():
    """Honest exhaustion without stubbing canon: pin seed_terms_per_idea to
    [2,2] via config, then hand the sampler EVERY key it could possibly draw
    (all C(71,2) sorted pairs x the 8 families = 19,880 keys, built from the
    sampler's own vocabulary). Every resample collides, so the 50-try bound
    must surface as RuntimeError. The exception's wording is not fixed by the
    contract, so only the type is asserted."""
    cfg = _cfg()
    cfg["ideas"]["seed_terms_per_idea"] = [2, 2]
    vocab = sorted(load_vocab(cfg))

    probe = sample_idea(
        cfg, random.Random(5), batch_id="b001", index=1, prose_runner=_fake_prose()
    )
    assert len(_terms(probe)) == 2, (
        "sampler ignored ideas.seed_terms_per_idea=[2,2]; exhaustion cannot be constructed "
        "cheaply without it (the 2-4 key space is ~8M keys)"
    )

    everything = frozenset(
        f"{a}|{b}::{family}"
        for a, b in combinations(vocab, 2)
        for family in OBJECTIVE_FAMILIES
    )
    assert probe.dedupe_key in everything, "the exhaustive key set must cover a real draw"

    with pytest.raises(RuntimeError):
        sample_idea(
            cfg,
            random.Random(6),
            batch_id="b001",
            index=2,
            known_keys=everything,
            prose_runner=_fake_prose(),
        )


# --------------------------------------------------------------------------
# 13-14: batch-level config handling
# --------------------------------------------------------------------------


def test_floors_and_quotas_degrade_warnings(tmp_path):
    """The pilot batch is size 1 against 8 objective floors and 5 quota slots:
    both must degrade loudly rather than silently."""
    cfg = _cfg()
    assert cfg["batch"]["size"] == 1, "pilot config drifted from batch.size=1"
    assert sum(cfg["batch"]["mix"]["objective"]["floors"].values()) == 8

    out = tmp_path / "degraded"
    out.mkdir(parents=True, exist_ok=True)
    with pytest.warns(RuntimeWarning) as record:
        ideas = sample_batch(
            cfg, batch_id="b001", seed=3, prose_runner=_fake_prose(), out_dir=out
        )

    messages = [str(w.message).lower() for w in record]
    assert any("floor" in m for m in messages), f"no floors warning in {messages}"
    assert any("quota" in m for m in messages), f"no quotas warning in {messages}"
    assert len(ideas) == 1
    assert len(list(out.glob("idea-*.json"))) == 1


def _break_floors(cfg: dict) -> None:
    cfg["batch"]["mix"]["objective"]["floors"]["reach_gaol"] = 1


def _break_quotas(cfg: dict) -> None:
    cfg["batch"]["quotas"]["goal.nonesuch"] = 1


def _break_locus(cfg: dict) -> None:
    cfg["batch"]["mix"]["locus"] = {"mover": 0.5, "selection": 0.36, "click": 0.24}


def _break_tiers(cfg: dict) -> None:
    cfg["batch"]["tiers"] = {"t1": 0.5, "t2": 0.4, "t3": 0.2}


def _reach_cap_high(cfg: dict) -> None:
    cfg["batch"]["mix"]["objective"]["reach_cap"] = 1.5


def _reach_cap_zero(cfg: dict) -> None:
    cfg["batch"]["mix"]["objective"]["reach_cap"] = 0.0


def test_strict_config_errors(tmp_path):
    """Strict config errors are ValueError, and they land BEFORE any prose
    call — a bad config must never cost a token. Assumption: sample_batch is
    the validating entry point (the contract says 'before any prose call',
    which is all sample_batch does with the config)."""
    base = _cfg()
    control_log: list[str] = []
    control_out = tmp_path / "control"
    control_out.mkdir(parents=True, exist_ok=True)
    control = sample_batch(
        deepcopy(base),
        batch_id="b001",
        seed=1,
        prose_runner=_fake_prose(control_log),
        out_dir=control_out,
    )
    assert len(control) == 1 and control_log, "control: the untouched pilot config must sample"

    cases = (
        ("unknown family in floors", _break_floors),
        ("unknown term in quotas", _break_quotas),
        ("locus weights not summing to 1", _break_locus),
        ("tier weights not summing to 1", _break_tiers),
        ("reach_cap above 1", _reach_cap_high),
        ("reach_cap at 0 (the interval is open)", _reach_cap_zero),
    )
    prose_log: list[str] = []
    for index, (label, mutate) in enumerate(cases):
        broken = deepcopy(base)
        mutate(broken)
        out = tmp_path / f"broken-{index}"
        out.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError):
            sample_batch(
                broken,
                batch_id="b001",
                seed=1,
                prose_runner=_fake_prose(prose_log),
                out_dir=out,
            )
        assert prose_log == [], f"{label}: prose was called before the config was rejected"


# --------------------------------------------------------------------------
# 15: the validator's teeth
# --------------------------------------------------------------------------


def _valid_payload() -> dict:
    return draw(1, seed=2024)[0].to_json_dict()


def test_validator_kills(vocab_terms):
    """One defect per case, each isolated (the dedupe key is recomputed where
    the break would otherwise also invalidate it) so the reported violation
    can be required to name the field it is about."""
    base = _valid_payload()
    assert validate_idea_dict(deepcopy(base), vocab_terms) == [], "the control must be clean"

    primary = base["objective"]["primary"]
    witness = WITNESS_MAP[primary][0]
    every_witness = {term for terms in WITNESS_MAP.values() for term in terms}
    neutral = sorted(vocab_terms - every_witness)
    fillers = [t for t in sorted(vocab_terms) if t != witness]

    def missing_key(d):
        d.pop("tier")

    def five_terms(d):
        d["seed_terms"] = [witness, *fillers[:4]]
        d["dedupe_key"] = _key(d["seed_terms"], primary)

    def unknown_term(d):
        d["seed_terms"] = [witness, "not.a.term"]
        d["dedupe_key"] = _key(d["seed_terms"], primary)

    def bad_primary(d):
        d["objective"]["primary"] = "reach_goals"
        d["dedupe_key"] = _key(d["seed_terms"], "reach_goals")

    def witness_removed(d):
        d["failure_family"] = None
        d["seed_terms"] = neutral[:2]
        d["dedupe_key"] = _key(d["seed_terms"], primary)

    def secondary_set(d):
        d["objective"]["secondary"] = "survive"

    def bad_tier(d):
        d["tier"] = "t4"

    def bad_locus(d):
        d["mix_class"]["locus"] = "swipe"

    def empty_title(d):
        d["prose"]["title"] = ""

    def wrong_dedupe_key(d):
        d["dedupe_key"] = "nope::nope"

    cases = (
        ("missing key", missing_key, ("tier",)),
        ("five seed terms", five_terms, ("term",)),
        ("off-vocabulary term", unknown_term, ("not.a.term", "term", "vocab")),
        ("unknown primary", bad_primary, ("primary", "objective", "reach_goals")),
        ("witness removed", witness_removed, ("witness",)),
        ("secondary set", secondary_set, ("secondary",)),
        ("bad tier", bad_tier, ("tier",)),
        ("bad locus", bad_locus, ("locus",)),
        ("empty title", empty_title, ("title", "prose")),
        ("wrong dedupe key", wrong_dedupe_key, ("dedupe",)),
    )

    for label, mutate, expected in cases:
        payload = deepcopy(base)
        mutate(payload)
        violations = validate_idea_dict(payload, vocab_terms)
        assert violations, f"{label}: validator accepted a broken idea"
        blob = " ".join(str(v) for v in violations).lower()
        assert any(word.lower() in blob for word in expected), (
            f"{label}: no violation names {expected} — got {violations}"
        )


# --------------------------------------------------------------------------
# 16-17: prose prompt + id format
# --------------------------------------------------------------------------

# "the line about ignoring fixed level counts": the contract fixes the intent,
# not the wording, so a level-bearing line must carry an ignore-ish clause.
_IGNORE_CLAUSE = re.compile(
    r"(?i)(ignor\w*|disregard\w*|do not\b|don't\b|not fixed|no fixed|any number of)"
)


def test_prose_prompt_contents():
    prompts: list[str] = []
    ideas = draw(20, seed=1234, prose_runner=_fake_prose(prompts))
    assert len(prompts) == len(ideas) == 20, "one prose call per idea"

    seeded = 0
    for idea, prompt in zip(ideas, prompts, strict=True):
        assert "Generate a single game idea" in prompt, (
            "the tufa doctrine must open the prompt"
        )
        for term in _terms(idea):
            assert term in prompt, f"{idea.id}: seed term {term} missing from its prompt"
        assert _primary(idea) in prompt, f"{idea.id}: primary family missing from its prompt"
        if idea.failure_family is not None:
            seeded += 1
            assert idea.failure_family in prompt, f"{idea.id}: failure family missing"

        level_lines = [ln for ln in prompt.splitlines() if "level" in ln.lower()]
        assert level_lines, f"{idea.id}: prompt never mentions levels"
        assert any(_IGNORE_CLAUSE.search(ln) for ln in level_lines), (
            f"{idea.id}: no line telling the writer to ignore fixed level counts: {level_lines}"
        )

    assert seeded, "no failure-family prompt in 20 draws — that branch went untested"
    assert _prose_field(ideas[0], "title") == PROSE_TITLE
    assert _prose_field(ideas[0], "text") == PROSE_TEXT


def test_id_format():
    cfg = _cfg()
    for index, expected in ((1, "b001-i001"), (7, "b001-i007"), (42, "b001-i042")):
        idea = sample_idea(
            cfg,
            random.Random(index),
            batch_id="b001",
            index=index,
            prose_runner=_fake_prose(),
        )
        assert idea.id == expected
