"""B6 acceptance: the canon parsers, the S2 prompt payload, and the token cap.

Run: .venv/bin/python -m pytest gen/tests/test_b6_payload.py -v

Written FROM THE B6 CONTRACT and from the REAL canon, never from the
implementation: every expectation below was ground-truthed against
`duckwm_docs` by hand before this file existed (see the module constants —
each one names the canon line it came from). The canon is read-only here;
nothing in this file writes into it.

Agent sessions are INJECTED fakes, exactly as in test_b3_green_loop.py. No
CLI is ever spawned and no driver is ever built: the token-cap tests hand
`green_loop` a closure that reports 150k in + 150k out per attempt.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from gen.canon_docs import (
    bestiary_excerpt,
    load_conventions,
    load_forbidden_quotes,
    load_playbook_entries,
    load_required_gates,
    load_skeleton,
)
from gen.config import load_config
from gen.s0_ideas import load_vocab
from gen.s2_implement import (
    ATTEMPTS_SUFFIX,
    REJECT_SUFFIX,
    REJECT_VERDICT,
    REPORT_SUFFIX,
    build_payload,
    green_loop,
    main,
    parse_token_cap,
    sidecar,
)
from gen.worker import instantiate_worker

TOY = Path(__file__).resolve().parent / "toy_worker"
FIXTURE_SPEC = Path(__file__).resolve().parent / "fixtures/specs/good-spec.yaml"
PILOT_CONFIG = "config/b001-pilot.yaml"

PLAYBOOK_REL = "design/objects/playbook.md"
SKELETON_REL = "provenance/objects-working/playbook-skeleton.md"
AFFORDANCE_REL = "design/objects/affordance-language.md"
BESTIARY_REL = "design/objects/bestiary"

# --- canon ground truth (verified by hand, 2026-09-22) -----------------------
# playbook.md carries 45 line-initial bold head tokens; exactly two are not
# vocabulary terms — `click-select` (a prose alias sharing manip.select_cycle's
# head, playbook.md:87) and the `SIGNED OFF (operator, 2026-09-18)` footer
# (playbook.md:200). 45 - 2 = the 43 covered terms.
PLAYBOOK_TERM_COUNT = 43
# Two heads WRAP across a newline; the second term of each lands on the
# continuation line, so a line-at-a-time parser loses it silently.
PLAYBOOK_WRAPPED = ("terrain.trail", "info.hidden_geometry")  # :150-151, :164-165
# One head names TWO terms (playbook.md:43) — one entry, two keys.
PLAYBOOK_SHARED_HEAD = ("phys.drift", "terrain.conveyor")
PLAYBOOK_COVERED = (
    "terrain.conveyor",
    "info.fog",
    "info.telegraph",
    "info.recall",
    "manip.select_cycle",
)
# goal.cover and gate.direct are vocabulary terms with NO playbook head;
# click-select is not a vocabulary term at all.
PLAYBOOK_UNCOVERED = ("goal.cover", "gate.direct", "click-select")

# playbook-skeleton.md carries 73 `## ` heads: the 71-term vocabulary plus the
# two legacy names dropped by vocabulary v2-final.
SKELETON_DROPPED = ("phys.weight", "manip.rotate")
# Zero officials, tufa-only evidence (verified in the skeleton's own sections).
SKELETON_ZERO_OFFICIAL = ("gate.direct", "terrain.conveyor", "info.telegraph", "info.recall")

# The five §3 head styles across the bestiary fleet. NOTE the third entry:
# the B6 brief named ("sk48", "goal.path_connect") for the bare-### style, but
# sk48 §3 has no goal.path_connect head — that term appears ONLY in sk48's
# "Terms the grids mark absent" list (sk48.md:227). The real bare-### head at
# sk48.md:144 is manip.select_cycle, which is what this suite pins.
BESTIARY_HEAD_STYLES = (
    ("cd82", "move.grid"),            # cd82.md:113  ### `move.grid` — present (agreed)
    ("sk48", "manip.select_cycle"),   # sk48.md:144  ### manip.select_cycle
    ("ar25", "state.undo"),           # ar25.md:164  **`state.undo`** — ...
    ("lf52", "move.coupled"),         # lf52.md:54   **move.coupled** (present) — ...
    ("bp35", "agent.patrol"),         # bp35.md:82   - **agent.patrol** (creep) — ...
)

# The four signed FORBIDDEN engine contracts, in the order spec §2 lists them.
# Source lines in affordance-language.md (266 lines): 200, 204, 163, 214-221.
FORBIDDEN_ANCHORS = (
    "interface paint",
    "complete_action",
    "mixed accidental",
    "-2 without a reader",
)
SOURCE_RE = re.compile(r"affordance-language\.md:L\d+")

# The ladder the fixture spec's six terms must produce. VERIFIED against the
# canon term by term:
#   goal.cover         no playbook head · skeleton officials = (sp80,)
#   terrain.conveyor   playbook head :43 · skeleton officials = ()
#   manip.select_cycle playbook head :87 · skeleton officials lead with ar25
#   info.telegraph     playbook head :164 · skeleton officials = ()
#   info.fog           playbook head :164 · skeleton officials lead with cn04
#   info.recall        playbook head :164 · skeleton officials = ()
EXPECTED_LADDER = {
    "goal.cover": ["bestiary", "skeleton"],
    "terrain.conveyor": ["playbook", "skeleton"],
    "manip.select_cycle": ["playbook", "bestiary", "skeleton"],
    "info.telegraph": ["playbook", "skeleton"],
    "info.fog": ["playbook", "bestiary", "skeleton"],
    "info.recall": ["playbook", "skeleton"],
}
SPEC_PROSE_MARKER = "MARKER-B6-PROSE-SPEC"
SPEC_MD = f"""# Fogbound Switchyard — prose spec

{SPEC_PROSE_MARKER}: belts carry coloured crates past cycleable junctions
toward pads of matching colour. A fog bank telegraphs the yard's true state
for a few beats, then renders it flat grey while the belts keep running.
"""

# One attempt's reported spend in the token-cap fakes: 300k per attempt, so
# a 400k cap is crossed on attempt 2 and never on attempt 1.
FAKE_TOKENS_IN = 150_000
FAKE_TOKENS_OUT = 150_000

# --- the §7 layout-seed contract section (R1) --------------------------------
# GROUND TRUTH is the FROZEN B10 convention, not this payload's wording:
# `gen/s6_package.py` (module docstring + load_layout_contract /
# rederive_layouts) enforces it, and `gen/tests/fixtures/s6_seeded/{game,
# solver}.py` is its reference implementation. A payload that omits this
# section produces a game with no `build_layout`, which S6 REFUSES — the
# whole point of the section.
LAYOUT_SECTION_HEAD = "## The §7 layout-seed contract"
# The canon the section must cite by name.
LAYOUT_CITATIONS = ("spec-v0.3 §7", "D13")
# The convention, rule by rule. Matched through `_norm` (backtick- and
# wrap-insensitive, lowercased), so the prompt may re-wrap freely.
LAYOUT_CONTRACT_MARKERS = (
    "build_layout(seed: int) -> list",          # the frozen signature
    "module-level and pure",                    # ... importable without the game
    "same seed -> identical result",            # determinism
    "hashlib.sha256",                           # seeded derivation
    "never hash() (salted per process)",        # the process-salt trap
    "distinct seeds -> structurally distinct",  # the D13 promise itself
    "game(layout_seed: int | none = none)",     # the game constructor
    "solver(layout_seed: int | none = none)",   # the solver constructor
    "self.layout_seed",                         # the instance records it
    "authored default",                         # spec layout.seed = the default
    "must never import game",                   # the sibling-by-path rule
)
# The enforcement warning: what S6 does to a game that ignores the above.
LAYOUT_ENFORCEMENT_MARKERS = (
    "gen/s6_package.py refuses a game without build_layout",
    "is a §7 violation, not a seed-reject",
    "drives your solver at 5 seeds",
    "must win at every one",
)
# Cosmetic-only variation is the failure mode the stale B5 pilot spec wrote
# into its prose ("layout.seed only seeds any cosmetic placement jitter").
LAYOUT_ANTI_COSMETIC = "only jitters cosmetics is a §7 violation"

# S5's conservative charge rate (gen/s5_battery.TOKEN_ESTIMATE_CHARS_PER_TOKEN
# = 3): prose tokenizes nearer 4 chars/token, so dividing by 3 over-counts the
# payload rather than under-counting it. Hardcoded rather than imported to keep
# this module's imports off `arcengine`.
PAYLOAD_CHARS_PER_TOKEN = 3


# --- fixtures ---------------------------------------------------------------
@pytest.fixture(scope="session")
def cfg() -> dict:
    return load_config(PILOT_CONFIG)


@pytest.fixture(scope="session")
def vocab(cfg: dict) -> dict:
    return load_vocab(cfg)


@pytest.fixture(scope="session")
def official_slugs(cfg: dict) -> frozenset[str]:
    slugs = frozenset(p.stem for p in (_docs(cfg) / BESTIARY_REL).glob("*.md"))
    assert len(slugs) == 25, f"the bestiary fleet is the 25 officials, found {len(slugs)}"
    return slugs


@pytest.fixture
def spec_dir(tmp_path: Path) -> Path:
    """A minimal S1 output dir: the hand-written §11 fixture spec + prose."""
    dest = tmp_path / "spec"
    dest.mkdir()
    shutil.copy2(FIXTURE_SPEC, dest / "spec.yaml")
    (dest / "spec.md").write_text(SPEC_MD, encoding="utf-8")
    return dest


# --- helpers ----------------------------------------------------------------
def _docs(cfg: dict) -> Path:
    return Path(cfg["duckwm_docs"])


def _canon_lines(cfg: dict, rel: str) -> list[str]:
    return (_docs(cfg) / rel).read_text(encoding="utf-8").splitlines()


def _norm(text: str) -> str:
    """Backtick- and wrap-insensitive comparison: the canon hard-wraps its
    prose and backticks its identifiers, neither of which is meaning."""
    return re.sub(r"\s+", " ", text.replace("`", "")).strip().lower()


def _section(payload: str, head: str) -> str:
    """One `## ` section of the payload: its head, up to the next `## ` head."""
    start = payload.index(head)
    end = payload.find("\n## ", start + len(head))
    return payload[start:] if end == -1 else payload[start:end]


def _python_blocks(text: str) -> list[str]:
    """Every ```python fenced block, in order."""
    return re.findall(r"```python\n(.*?)```", text, re.DOTALL)


def _window(lines: list[str], source_line: int, span: int = 3) -> str:
    """The 1-based `source_line` plus the next few — a head that wraps puts
    its later terms on the continuation line."""
    start = max(0, source_line - 1)
    return "\n".join(lines[start : start + span])


def _cfg(attempts: int, token_cap: object = None) -> dict:
    """Minimal config: with an injected runner these are the only keys read."""
    implementer: dict = {"max_green_attempts": attempts}
    if token_cap is not None:
        implementer["session_token_cap"] = token_cap
    return {"implementer": implementer}


def _worker(tmp_path: Path, name: str) -> Path:
    dest = tmp_path / name
    instantiate_worker(dest)
    return dest.resolve()


def _install_toy(worker: Path) -> None:
    shutil.copy2(TOY / "game.py", worker / "game.py")
    shutil.copy2(TOY / "solver.py", worker / "solver.py")


def _token_runner(log: list[dict], on_call=None):
    """One fake agent session reporting a fixed, large token spend."""

    def runner(prompt: str, *, cwd: Path, resume_id: str | None):
        log.append({"prompt": prompt, "cwd": Path(cwd), "resume_id": resume_id})
        n = len(log)
        if on_call is not None:
            on_call(n, Path(cwd))
        return {
            "session_id": f"tok-{n}",
            "usd_cost": 0.5,
            "tokens_in": FAKE_TOKENS_IN,
            "tokens_out": FAKE_TOKENS_OUT,
            "duration_s": 0.0,
            "error": None,
        }

    return runner


def _rows(worker: Path) -> list[dict]:
    text = sidecar(worker, ATTEMPTS_SUFFIX).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# --- playbook ---------------------------------------------------------------
def test_playbook_covers_exactly_43_vocabulary_terms(cfg, vocab):
    entries = load_playbook_entries(cfg)

    assert len(entries) == PLAYBOOK_TERM_COUNT, (
        f"playbook.md covers {PLAYBOOK_TERM_COUNT} vocabulary terms; "
        f"got {len(entries)}: {sorted(entries)}"
    )
    assert set(entries) <= set(vocab), (
        f"non-vocabulary keys leaked in: {sorted(set(entries) - set(vocab))}"
    )


def test_playbook_named_inclusions_and_exclusions(cfg):
    entries = load_playbook_entries(cfg)

    for term in PLAYBOOK_COVERED:
        assert term in entries, f"{term} has a playbook head and must be covered"
        assert entries[term].text.strip(), f"{term}'s playbook entry is empty"
    for term in PLAYBOOK_UNCOVERED:
        assert term not in entries, (
            f"{term} has no playbook head of its own — covering it invents canon"
        )


def test_playbook_heads_that_wrap_across_a_newline_survive(cfg):
    """`terrain.trail` (:151) and `info.hidden_geometry` (:165) are the second
    halves of heads that wrap; a line-at-a-time parser drops both silently."""
    entries = load_playbook_entries(cfg)
    lines = _canon_lines(cfg, PLAYBOOK_REL)

    for term in PLAYBOOK_WRAPPED:
        assert term in entries, f"{term} is a wrapped-head casualty"
        entry = entries[term]
        assert entry.text.strip(), f"{term} parsed to an empty entry"
        assert term in entry.terms, f"{term} missing from its own entry's terms"
        assert 0 < entry.source_line <= len(lines)
        assert term in _window(lines, entry.source_line), (
            f"{term}'s source_line {entry.source_line} does not point at its head"
        )


def test_playbook_shared_head_is_one_entry_under_both_terms(cfg):
    """playbook.md:43 heads ONE entry with two terms (`phys.drift /
    terrain.conveyor`); both keys must reach the same text."""
    entries = load_playbook_entries(cfg)
    drift, conveyor = PLAYBOOK_SHARED_HEAD

    assert drift in entries and conveyor in entries
    assert entries[drift].text == entries[conveyor].text
    assert entries[drift].source_line == entries[conveyor].source_line
    for term in PLAYBOOK_SHARED_HEAD:
        assert term in entries[conveyor].terms, (
            f"the shared head must list both terms; {term} is missing"
        )


def test_playbook_source_lines_point_into_the_real_file(cfg):
    entries = load_playbook_entries(cfg)
    lines = _canon_lines(cfg, PLAYBOOK_REL)

    for term, entry in entries.items():
        assert 0 < entry.source_line <= len(lines), (
            f"{term}: source_line {entry.source_line} outside playbook.md (1-{len(lines)})"
        )
        assert term in _window(lines, entry.source_line), (
            f"{term}: source_line {entry.source_line} is not its head line"
        )


# --- skeleton ---------------------------------------------------------------
def test_skeleton_normalizes_73_heads_onto_the_71_term_vocabulary(cfg, vocab):
    skeleton = load_skeleton(cfg)

    assert set(skeleton) == set(vocab), (
        f"missing {sorted(set(vocab) - set(skeleton))}; "
        f"extra {sorted(set(skeleton) - set(vocab))}"
    )
    assert len(skeleton) == 71
    assert "phys.balance" in skeleton, "phys.balance is the balance family's witness"
    for dropped in SKELETON_DROPPED:
        assert dropped not in skeleton, (
            f"{dropped} is a legacy skeleton head, not a v2-final vocabulary term"
        )


def test_skeleton_officials_are_slug_evidence_pairs_from_the_25(cfg, official_slugs):
    skeleton = load_skeleton(cfg)
    seen = set()

    for term, section in skeleton.items():
        for entry in section.officials:
            slug, evidence = entry
            assert slug in official_slugs, f"{term}: {slug!r} is not one of the 25 officials"
            assert isinstance(evidence, str) and evidence.strip(), (
                f"{term}/{slug}: empty evidence line"
            )
            seen.add(slug)
    assert seen, "no official evidence parsed out of the skeleton at all"


def test_skeleton_goal_cover_leads_with_sp80(cfg):
    """sp80 is goal.cover's only official; build_payload's bestiary layer is
    the FIRST official, so the head of this tuple is load-bearing."""
    section = load_skeleton(cfg)["goal.cover"]

    assert section.officials, "goal.cover has official evidence in the skeleton"
    assert section.officials[0][0] == "sp80"


def test_skeleton_zero_official_terms_still_carry_tufa_evidence(cfg):
    skeleton = load_skeleton(cfg)

    for term in SKELETON_ZERO_OFFICIAL:
        section = skeleton[term]
        assert tuple(section.officials) == (), (
            f"{term} has no official witness in the corpus; got {section.officials}"
        )
        assert len(section.tufa) >= 1, f"{term} must still offer tufa evidence"
        assert all(isinstance(line, str) and line.strip() for line in section.tufa)


def test_skeleton_source_lines_point_at_their_own_heads(cfg):
    skeleton = load_skeleton(cfg)
    lines = _canon_lines(cfg, SKELETON_REL)

    for term, section in skeleton.items():
        assert 0 < section.source_line <= len(lines)
        assert term in _window(lines, section.source_line), (
            f"{term}: source_line {section.source_line} is not its `## {term}` head"
        )
        assert section.text.strip(), f"{term}: empty skeleton section"


# --- bestiary ---------------------------------------------------------------
@pytest.mark.parametrize(("slug", "term"), BESTIARY_HEAD_STYLES)
def test_bestiary_excerpt_reads_all_five_section_3_head_styles(cfg, slug, term):
    excerpt = bestiary_excerpt(cfg, slug, term)
    lines = _canon_lines(cfg, f"{BESTIARY_REL}/{slug}.md")

    assert excerpt.slug == slug
    assert excerpt.term == term
    assert excerpt.text.strip(), f"{slug} §3 {term} parsed to an empty excerpt"
    assert 0 < excerpt.source_line <= len(lines)
    assert term in _window(lines, excerpt.source_line), (
        f"{slug}/{term}: source_line {excerpt.source_line} is not the head line"
    )


def test_bestiary_excerpt_reads_a_qualified_head(cfg):
    """sp80's head is `**goal.cover \\`no-waste\\`** (present, partB)` — the term
    plus a backticked qualifier. goal.cover's whole bestiary layer rides on
    matching it."""
    excerpt = bestiary_excerpt(cfg, "sp80", "goal.cover")

    assert excerpt.slug == "sp80" and excerpt.term == "goal.cover"
    assert excerpt.text.strip()


def test_bestiary_excerpt_rejects_a_slug_with_no_bestiary(cfg):
    with pytest.raises(ValueError, match="zzzz"):
        bestiary_excerpt(cfg, "zzzz", "move.grid")


def test_bestiary_excerpt_rejects_a_term_absent_from_that_files_section_3(cfg):
    """sk48 names info.fog exactly once — in its "Terms the grids mark absent"
    roll-up (sk48.md:228), with no §3 head and no implementation notes. A
    whole-file search finds the string and returns prose about a mechanic the
    game does not have; only a §3-head slice raises."""
    with pytest.raises(ValueError):
        bestiary_excerpt(cfg, "sk48", "info.fog")


def test_bestiary_excerpt_does_not_mistake_the_absent_list_for_a_head(cfg):
    """Same trap, second term: goal.path_connect is listed absent at
    sk48.md:227 and has no §3 head either."""
    with pytest.raises(ValueError):
        bestiary_excerpt(cfg, "sk48", "goal.path_connect")


# --- forbidden quotes, conventions, gates -----------------------------------
def test_forbidden_quotes_are_the_signed_four_in_order(cfg):
    quotes = load_forbidden_quotes(cfg)
    lines = _canon_lines(cfg, AFFORDANCE_REL)

    assert len(quotes) == 4, f"spec §2 signs exactly 4 engine contracts, got {len(quotes)}"
    # Identity by containment, not exact-anchor equality: the anchor STRING is
    # an extraction detail (the implementation may anchor on a longer unique
    # span); the contract is the four signed rules, in spec §2's order.
    # (Lead adjudication 2026-09-22 — the two B6 briefs diverged here.)
    for quote, marker in zip(quotes, FORBIDDEN_ANCHORS, strict=True):
        haystack = f"{quote.anchor} {quote.text}"
        assert marker.lower() in haystack.lower(), (
            f"quote {quote.anchor!r} does not carry the signed rule marker {marker!r}"
        )
    for quote in quotes:
        cite = SOURCE_RE.search(quote.source)
        assert cite, (
            f"{quote.anchor}: source {quote.source!r} is not affordance-language.md:L<n>"
        )
        line_no = int(cite.group(0).rsplit("L", 1)[1])
        assert 100 < line_no <= len(lines), (
            f"{quote.anchor}: line {line_no} is not a real §6/§8 line "
            f"(the four contracts live at :163, :200, :204 and :214-221)"
        )
        assert "FORBIDDEN" in quote.text, f"{quote.anchor}: the quote lost its verdict word"
        assert _norm(quote.anchor) in _norm(quote.text), (
            f"{quote.anchor}: the quoted text does not contain its own anchor"
        )
    assert len({q.text for q in quotes}) == 4, "the four contracts must be four distinct quotes"


def test_conventions_carry_the_orientation_and_settled_frame_rules(cfg):
    conventions = load_conventions(cfg)

    assert "one grid orientation" in conventions
    assert "frame[-1]" in conventions or "fd.frame[-1]" in conventions


def test_required_gates_carry_the_spot_words_and_stop_before_the_forbidden_block(cfg):
    gates = load_required_gates(cfg)

    assert "locus of control" in gates, "gate 1"
    assert "sys_click" in gates, "gate 2"
    assert "budget triple" in gates, "gate 3"
    assert "FORBIDDEN (engine contracts" not in gates, (
        "the REQUIRED slice must stop at spec §2's FORBIDDEN block — the "
        "forbidden contracts are quoted separately, with attributions"
    )


# --- payload: the per-term ladder -------------------------------------------
def test_payload_report_ladder_matches_the_canon(spec_dir, cfg):
    _, report = build_payload(spec_dir, cfg)

    ladder = {term: list(layers) for term, layers in report.terms.items()}
    assert ladder == EXPECTED_LADDER


def test_payload_has_every_section_header_in_order(spec_dir, cfg):
    payload, _ = build_payload(spec_dir, cfg)

    first_line = next(line for line in payload.splitlines() if line.strip())
    assert first_line.startswith("#"), f"the payload opens on its mission head, got {first_line!r}"

    anchors = [
        "## The spec (prose)",
        "## The spec (machine",
        "budget triple",                # the REQUIRED-gates self-check section
        # ANCHOR UPDATE, contract E-1 (2026-10-05): this row located the FORBIDDEN
        # section by its quotes' attribution, and the deception section now cites
        # the same canon file EARLIER in the payload (it quotes affordance §7's
        # six levers with their line numbers). The section's own header is what
        # this anchor always meant; the attribution count below still holds.
        "## The four FORBIDDEN engine contracts",
        LAYOUT_SECTION_HEAD,            # the §7 layout-seed contract (R1)
        "one grid orientation",         # the conventions section
        "## Term dossiers",
    ]
    positions = []
    for anchor in anchors:
        assert anchor in payload, f"payload is missing the {anchor!r} section"
        positions.append(payload.index(anchor))
    assert positions == sorted(positions), (
        f"sections out of contract order: {list(zip(anchors, positions, strict=True))}"
    )

    assert payload.count("affordance-language.md:L") >= 4, "all 4 contracts need attributions"
    for anchor in FORBIDDEN_ANCHORS:
        assert _norm(anchor) in _norm(payload), f"FORBIDDEN contract {anchor!r} did not make it"
    assert "make validate" in payload
    assert payload.rindex("make validate") > payload.index("## Term dossiers"), (
        "the make-validate block closes the payload, after the dossiers"
    )


def test_payload_embeds_both_spec_faces(spec_dir, cfg):
    payload, _ = build_payload(spec_dir, cfg)

    assert SPEC_PROSE_MARKER in payload, "the prose spec must be carried verbatim"
    assert "fogbound-switchyard" in payload, "the machine spec must be carried too"


def test_payload_dossiers_carry_every_term_and_its_layer_labels(spec_dir, cfg):
    payload, report = build_payload(spec_dir, cfg)
    dossiers_at = payload.index("## Term dossiers")

    for term in EXPECTED_LADDER:
        head = f"### {term}"
        assert head in payload, f"no dossier head for {term}"
        assert payload.index(head) > dossiers_at, f"{term}'s dossier precedes the section head"

    assert "**Playbook**" in payload
    assert "**Official exemplar" in payload
    assert "**Evidence base**" in payload
    assert set(report.terms) == set(EXPECTED_LADDER)


def test_payload_attributes_all_three_evidence_layers(spec_dir, cfg):
    payload, _ = build_payload(spec_dir, cfg)

    assert "(playbook.md:L" in payload, "playbook entries need path:line attribution"
    assert "bestiary/" in payload, "official exemplars need their bestiary path"
    assert "(playbook-skeleton.md:L" in payload, "evidence bases need path:line attribution"


# --- payload: the §7 layout-seed contract (R1) -------------------------------
def test_payload_states_the_section_7_layout_seed_contract(spec_dir, cfg):
    """The hard rules an implementer cannot guess.

    Every marker below is the FROZEN B10 convention (s6_package's
    load_layout_contract / rederive_layouts + the s6_seeded reference
    fixture), not a paraphrase of it. Without them the implementer ships a
    game with no `build_layout` and S6 refuses the worker outright.
    """
    payload, _ = build_payload(spec_dir, cfg)
    section = _section(payload, LAYOUT_SECTION_HEAD)
    normalized = _norm(section)

    for citation in LAYOUT_CITATIONS:
        assert citation in section, f"the §7 section must cite {citation!r}"
    for marker in LAYOUT_CONTRACT_MARKERS:
        assert _norm(marker) in normalized, f"the §7 section does not state: {marker!r}"
    assert _norm(LAYOUT_ANTI_COSMETIC) in normalized, (
        "cosmetic-only variation must be named a §7 violation — that is exactly "
        "what the stale B5 pilot spec promised and what S6 rejects"
    )
    for marker in LAYOUT_ENFORCEMENT_MARKERS:
        assert _norm(marker) in normalized, f"the enforcement warning is missing: {marker!r}"
    assert _norm("that integer is the authored default") in normalized, (
        "the spec's layout.seed is the default the game BAKES IN; a section that "
        "leaves that implicit invites a game whose default seed is invented"
    )


def test_payload_seed_count_matches_the_signed_package_knob(spec_dir, cfg):
    """The section tells the implementer how many seeds its solver is driven
    at. S6 reads that count from `package.seeds_validated` (architecture §3 S6,
    pilot ⊕ 5); this pin fails if the knob moves, instead of letting the prompt
    quietly promise the wrong number."""
    payload, _ = build_payload(spec_dir, cfg)
    section = _section(payload, LAYOUT_SECTION_HEAD)

    seeds = cfg["package"]["seeds_validated"]
    assert seeds == 5, f"the pilot validates 5 seeds (architecture §3 S6), config says {seeds}"
    assert f"at {seeds} seeds" in section, (
        f"the §7 section must name the real validation count ({seeds})"
    )


def test_payload_layout_skeleton_is_parseable_python(spec_dir, cfg):
    """Two skeletons — game.py and solver.py — and both must PARSE: a prompt
    that ships a syntax error teaches one."""
    payload, _ = build_payload(spec_dir, cfg)
    blocks = _python_blocks(_section(payload, LAYOUT_SECTION_HEAD))

    assert len(blocks) == 2, f"expected the game.py + solver.py skeletons, found {len(blocks)}"
    game_block, solver_block = blocks
    game_tree, solver_tree = (ast.parse(block) for block in blocks)

    assert "# game.py" in game_block and "# solver.py" in solver_block, (
        "each skeleton must say which file it is"
    )
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "build_layout"
        for node in game_tree.body
    ), "build_layout must be MODULE-LEVEL — S6 calls it without constructing the game"
    for marker in (
        "DEFAULT_LAYOUT_SEED",                  # the authored default, baked in
        "hashlib.sha256",                       # seeded derivation, never random
        "layout_seed: int | None = None",       # the constructor convention
        "self.layout_seed = seed",              # the instance records it
        "self._layout = build_layout(seed)",    # ... and consumes the layout
    ):
        assert marker in game_block, f"the game.py skeleton is missing {marker!r}"
    for marker in (
        "spec_from_file_location",              # load the sibling BY PATH
        "layout_seed: int | None = None",       # the same constructor convention
        "mod.build_layout(self.layout_seed)",   # the line is DERIVED from the layout
    ):
        assert marker in solver_block, f"the solver.py skeleton is missing {marker!r}"

    imported = set()
    for node in ast.walk(solver_tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert "game" not in imported, (
        "the solver skeleton must never `import game` — the pipeline exec-loads "
        "game files under synthetic module names"
    )


def test_payload_still_clears_the_session_token_cap(spec_dir, cfg):
    """The payload is charged against `implementer.session_token_cap` on
    attempt 1. The §7 section added ~5.1k chars (the real pilot spec dir went
    85,346 -> 90,431 chars, 7.5% of the 400k cap at 3 chars/token), so the
    margin is checked here rather than discovered in a run."""
    payload, _ = build_payload(spec_dir, cfg)
    cap = parse_token_cap(cfg["implementer"]["session_token_cap"])
    estimated = len(payload) // PAYLOAD_CHARS_PER_TOKEN

    assert estimated < cap // 4, (
        f"the payload estimates {estimated} tokens ({len(payload)} chars at "
        f"{PAYLOAD_CHARS_PER_TOKEN} chars/token) against a {cap}-token session cap — "
        "one prompt must not eat a quarter of the budget the loop runs on"
    )


def test_payload_is_byte_identical_on_a_second_build(spec_dir, cfg):
    first, first_report = build_payload(spec_dir, cfg)
    second, second_report = build_payload(spec_dir, cfg)

    assert first == second, "the payload must be deterministic byte for byte"
    assert {t: list(v) for t, v in first_report.terms.items()} == {
        t: list(v) for t, v in second_report.terms.items()
    }


def test_build_payload_rejects_a_term_outside_the_71_vocabulary(spec_dir, cfg):
    spec = yaml.safe_load((spec_dir / "spec.yaml").read_text(encoding="utf-8"))
    spec["game"]["terms"].append("goal.teleport")
    (spec_dir / "spec.yaml").write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="goal.teleport"):
        build_payload(spec_dir, cfg)


def test_build_payload_requires_the_prose_spec(spec_dir, cfg):
    (spec_dir / "spec.md").unlink()

    with pytest.raises(FileNotFoundError):
        build_payload(spec_dir, cfg)


def test_build_payload_requires_the_machine_spec(spec_dir, cfg):
    (spec_dir / "spec.yaml").unlink()

    with pytest.raises(FileNotFoundError):
        build_payload(spec_dir, cfg)


def test_payload_cli_writes_payload_md_beside_the_spec(spec_dir):
    """`--payload` never runs a session, so this is safe in-process."""
    rc = main(["--payload", str(spec_dir), "--config", PILOT_CONFIG])

    assert rc == 0
    written = spec_dir / "payload.md"
    assert written.is_file(), "the default output is <spec-dir>/payload.md"
    assert "## Term dossiers" in written.read_text(encoding="utf-8")


def test_payload_cli_honors_out(spec_dir, tmp_path):
    out = tmp_path / "elsewhere" / "prompt.md"
    out.parent.mkdir()

    rc = main(["--payload", str(spec_dir), "--out", str(out), "--config", PILOT_CONFIG])

    assert rc == 0
    assert out.is_file()
    assert not (spec_dir / "payload.md").exists(), "--out replaces the default, never adds to it"
    assert "## Term dossiers" in out.read_text(encoding="utf-8")


# --- token cap --------------------------------------------------------------
def test_parse_token_cap_accepts_ints_and_suffixes():
    assert parse_token_cap("400k") == 400_000
    assert parse_token_cap(400_000) == 400_000
    assert parse_token_cap("400k") == parse_token_cap(400_000)
    assert parse_token_cap("1.5M") == 1_500_000


@pytest.mark.parametrize("bad", ["abc", "", None, "-5k"])
def test_parse_token_cap_rejects_junk(bad):
    with pytest.raises(ValueError):
        parse_token_cap(bad)


def test_pilot_config_still_carries_the_400k_session_cap(cfg):
    assert parse_token_cap(cfg["implementer"]["session_token_cap"]) == 400_000, (
        "the pilot session token cap drifted from 400k"
    )


def test_token_cap_stops_a_red_loop_and_rejects(tmp_path):
    """300k per attempt against a 400k cap: attempt 1 is under, attempt 2
    crosses it, and the loop stops there instead of burning 10 more."""
    worker = _worker(tmp_path, "w-tokcap")
    log: list[dict] = []

    report = green_loop(
        worker, "implement the spec", _cfg(12, "400k"), session_runner=_token_runner(log)
    )

    assert report.green is False
    assert report.attempts == 2, "the cap must stop the loop, not the 12-attempt ceiling"
    assert len(log) == 2
    assert report.reject_reason == "token-cap-exceeded"

    rows = _rows(worker)
    assert [row["tokens_cumulative"] for row in rows] == [300_000, 600_000]

    reject = json.loads(sidecar(worker, REJECT_SUFFIX).read_text(encoding="utf-8"))
    assert reject["verdict"] == "token-cap-exceeded"
    assert reject["token_cap"] == 400_000
    assert reject["tokens_cumulative"] == 600_000
    assert not sidecar(worker, REPORT_SUFFIX).exists()


def test_a_green_attempt_is_never_token_rejected(tmp_path):
    """Same 600k spend, but attempt 2 goes green: green wins outright."""
    worker = _worker(tmp_path, "w-tokgreen")
    log: list[dict] = []

    report = green_loop(
        worker,
        "implement the spec",
        _cfg(12, "400k"),
        session_runner=_token_runner(log, lambda n, cwd: _install_toy(cwd) if n == 2 else None),
    )

    assert report.green is True
    assert report.attempts == 2
    assert report.reject_reason is None
    assert sidecar(worker, REPORT_SUFFIX).is_file()
    assert not sidecar(worker, REJECT_SUFFIX).exists(), "a green run never writes a reject"
    assert [row["tokens_cumulative"] for row in _rows(worker)] == [300_000, 600_000]


def test_no_configured_cap_runs_to_the_attempt_ceiling(tmp_path):
    """A config without implementer.session_token_cap is uncapped: the same
    600k-by-attempt-2 spend runs the full 12 and rejects to S1 as in B3."""
    worker = _worker(tmp_path, "w-nocap")
    log: list[dict] = []

    report = green_loop(worker, "implement the spec", _cfg(12), session_runner=_token_runner(log))

    assert report.green is False
    assert report.attempts == 12 and len(log) == 12
    assert report.reject_reason == "attempt-cap"

    reject = json.loads(sidecar(worker, REJECT_SUFFIX).read_text(encoding="utf-8"))
    assert reject["verdict"] == REJECT_VERDICT == "reject-to-S1"
    assert reject["attempts"] == 12


def test_green_loop_regression_green_at_attempt_2(tmp_path):
    """B3's contract, re-run here: the B6 ledger/reject additions must not
    change what the loop DOES. (test_b3_green_loop.py covers the rest.)"""
    worker = _worker(tmp_path, "w-regress")
    log: list[dict] = []

    report = green_loop(
        worker,
        "implement the spec",
        _cfg(12),
        session_runner=_token_runner(log, lambda n, cwd: _install_toy(cwd) if n == 2 else None),
    )

    assert report.green is True
    assert report.attempts == 2
    assert [r.green for r in report.records] == [False, True]
    assert report.reject_reason is None
    assert log[0]["prompt"] == "implement the spec"
    assert log[1]["resume_id"] == "tok-1", "the loop still threads the resume id"
    assert "make validate" in log[1]["prompt"], "the fix prompt still carries the validate tail"
    written = json.loads(sidecar(worker, REPORT_SUFFIX).read_text(encoding="utf-8"))
    assert written["green"] is True and written["attempts"] == 2
