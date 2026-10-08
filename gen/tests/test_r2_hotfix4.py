"""R2 hotfix #4 acceptance: the writer prompt grows a per-family LINT SURFACE
section, S0 grows a pure prose gate, and the pilot's re-spec cap goes to 4 —
tested from the contract.

Run: .venv/bin/python -m pytest gen/tests/test_r2_hotfix4.py -v

Written against the frozen R2 hotfix-4 mini-contract while `gen/s1_spec.py`,
`gen/s0_ideas.py` and `config/b001-pilot.yaml` were changed in parallel; no
line of that work was read. What R2 hit, twice: (a) the writer kept tripping
§11 kill rules it had never been shown — the prompt taught the schema and the
linter kept the rules — and (b) one S0 draw came back as an agent's tool
narration ("I'll check the repo's mechanics vocabulary…" over a `grep -rn`
line), which `_parse_prose` happily split into a title and a body because it
only checks that neither is empty.

Two standing rules this file keeps (the test_r2_hotfix.py precedent):

  * NO API call, ever. `build_writer_prompt` is a pure builder and
    `_prose_rejects` is a pure function; nothing here has a runner.
  * NO writes outside `tmp_path`. In fact nothing here writes at all:
    `config/` is read via `load_config` and never written, and `out/` is
    never touched. The b11 fake-runner harness is deliberately NOT imported —
    no clause of this contract drives the §4 state machine, and a rig a file
    does not use is noise, not safety.

Contract readings this file encodes where the hotfix-4 contract left a choice
open — each one is a line to renegotiate, not a fact:

  * The family list is DISCOVERED, never hardcoded: every `gen.s1_spec`
    attribute matching `^[A-Z0-9_]+_NOTE$` minus the two the contract names as
    pre-existing (`NEG2_NOTATION_NOTE`, `CURRICULUM_NOTE`). `LINT_SURFACE_NOTES`
    is plural and so cannot match its own family pattern — the aggregate can
    never count itself as a family. A `*_NOTE` name IMPORTED into s1_spec would
    be collected too; the contract says "module attribute", and that is taken
    at its word.
  * The header constant is named `<NOTE NAME>_HEADER` — the
    `CURRICULUM_NOTE`/`CURRICULUM_NOTE_HEADER` shape the contract spells as
    `<FAMILY>_NOTE_HEADER`, NOT the older `NEG2_NOTATION_NOTE`/
    `NEG2_NOTATION_HEADER` shape. If the implementation picked the older one,
    this is the line to renegotiate, not the code.
  * "equals `"\\n\\n".join` of exactly those notes in some fixed order" is
    pinned by RECONSTRUCTION rather than by guessing the order: each note's
    first index in the aggregate, sorted, must tile it exactly — start at 0,
    two characters of gap between neighbours, last one ending at the end —
    and re-joining in that recovered order must be byte-identical. That is
    what "contains no text absent from the per-family notes beyond the joining
    newlines" means operationally, and it recovers the fixed order instead of
    assuming it.
  * "The combined length of the NEW note text is <= 6,000 characters" is read
    as the sum of the notes' own lengths. The `\\n\\n` the join inserts is not
    note text, so the aggregate string is allowed those 2*(n-1) bytes on top.
  * The contradiction family: the HARD pin is the contract's own words — the
    literal `danger_tell` and the tokens `hazard.` and `loss.` all appear
    somewhere in `LINT_SURFACE_NOTES`. The second assertion, that ONE note
    carries all three, is this file's reading of "One family MUST cover the
    contradiction rule": three tokens scattered across three families would
    satisfy the letter while teaching the writer nothing about the rule.
  * "after CURRICULUM_NOTE (which is after NEG2_NOTATION_NOTE, which is after
    SCHEMA_HEADER)" is read as four strictly increasing FIRST-occurrence
    indices in the prompt string — ordering, not adjacency (the
    test_r2_hotfix.py precedent).
  * `_prose_rejects` "pure" is read as: no disk, no cfg, no accumulated state.
    Pinned by calling it twice and by putting a good draw AFTER a bad one, so
    a module-level accumulator list shows up as a good draw that stopped
    being good.
  * "empty list = acceptable" is taken literally: a good draw returns `[]`,
    not `None` and not some other falsy sentinel.
  * "at least 2 distinct reasons" for the garbage draw is read as two distinct
    STRINGS — the same message twice is one reason reported twice.
  * The two title rules are exercised in ISOLATION so a failure names which
    one is missing: an 11-word title that is only 59 characters, and a 10-word
    title that is 92 characters. Neither case leans on the other rule.
  * The two tool-fragment cases are the SAME accepted prose plus a fragment,
    so the fragment is the only variable: an `--include=` flag, and a fenced
    ``` block. The fence is given with real newlines (the literal reading of
    "a fenced block"), although `_parse_prose` would hand this gate a
    flattened paragraph in production; a marker check reads the same either
    way.
  * THE LOOSEST LINE, and the first to renegotiate: reason strings are NOT
    pinned. Each reason is only required to contain one of seven tokens
    ("narration", "title", "short", "tool", "command", "chars", "words",
    case-insensitively). If a reason is right and simply words itself outside
    that vocabulary, widen `REASON_VOCABULARY` — do not reword the code.
  * The pilot's cap is asserted twice over: the raw value under
    `orchestrator` as `load_config` returns it, AND what `_respec_cap` reads
    back from the loaded cfg. A config key the accessor does not honour is not
    a raised cap.
"""

from __future__ import annotations

import re

import pytest

from gen import s1_spec
from gen.config import load_config
from gen.orchestrator import RESPEC_CAP, _respec_cap
from gen.s0_ideas import _prose_rejects
from gen.s1_spec import (
    CURRICULUM_NOTE,
    LINT_SURFACE_NOTES,
    NEG2_NOTATION_NOTE,
    SCHEMA_HEADER,
    build_writer_prompt,
)

PILOT = "config/b001-pilot.yaml"

#: the contract's own discovery pattern for a per-family note constant.
NOTE_NAME_RE = re.compile(r"^[A-Z0-9_]+_NOTE$")

#: the two notes that already existed — excluded from "the NEW notes" by name.
PRE_EXISTING_NOTES = ("NEG2_NOTATION_NOTE", "CURRICULUM_NOTE")

#: what `"\n\n".join` puts between two notes.
JOINER = "\n\n"

#: the budget for the new note text (the notes themselves, not the joiners).
NOTE_BUDGET = 6000

#: the R2 contradiction kill, in the three tokens that make it teachable:
#: "knobs.danger_tell is 'unique-hue' but game.terms holds no hazard.* or
#: loss.* term".
CONTRADICTION_TOKENS = ("danger_tell", "hazard.", "loss.")

#: the pilot's raised re-spec cap, and the `orchestrator` keys it sits beside.
PILOT_RESPEC_CAP = 4
PILOT_ORCHESTRATOR = {"workers": 4, "wave_size": 5, "max_attrition": 0.30}

# A hand-written idea carrying exactly what `build_writer_prompt` requires
# (id, seed_terms, prose) — the test_r2_hotfix.py / test_r2_hotfix2.py pattern,
# and the right one here too: the lint-surface notes are static prompt text, so
# no artifact under `out/` needs to exist for this file to run.
MINIMAL_IDEA = {
    "id": "b001-pilot-i001",
    "seed_terms": ["info.fog", "goal.cover"],
    "prose": {
        "title": "Fogbound Switchyard",
        "text": "Belts carry coloured crates past cycleable junctions toward matching pads.",
    },
}


# --------------------------------------------------------------------------
# S0 prose fixtures
# --------------------------------------------------------------------------

# The draw R2 actually got back, verbatim: an agent narrating a repo lookup.
# `_parse_prose` accepted it because the first line is non-empty and the rest
# is non-empty — which is the whole reason this gate exists.
GARBAGE_TITLE = (
    "I'll check the repo's mechanics vocabulary and spec conventions to make sure "
    "the terms align with how this pipeline defines them."
)
GARBAGE_TEXT = (
    "--- Let me check how these terms are used elsewhere in the pipeline. "
    r'grep -rn "state.checkpoint\|goal.survive\|interaction locus\|legibility tier'
    r'\|hazardless" --include=*.py --include=*.yaml --include=*.md -l .'
)

GOOD_TITLE_1 = "Fogbound Switchyard Night Relay"
GOOD_TEXT_1 = (
    "A dim rail yard fills most of the grid, and four coloured crates ride belts that "
    "advance one cell every turn. The player moves a small signal sprite along the "
    "platform and presses the action key to flip a junction, which sends the next crate "
    "down a different spur. Fog hides the far half of the yard until a crate rolls "
    "through it, so the early turns are about learning the layout rather than solving "
    "it outright. Each level asks the player to cover every delivery pad with a crate of "
    "the matching hue before the belt cycle runs out. Later levels add a second signal "
    "sprite, and the player must select which of the two is under control, because only "
    "the selected one answers the arrow keys. The grid grows from eight cells across to "
    "sixteen, and the number of junctions rises with it. A level is won the moment the "
    "last pad is covered, and lost when a crate leaves the yard by the wrong spur. The "
    "sprites are flat blocks of colour with a one cell border, so the board reads from a "
    "single frame, and belt direction is drawn as a short tail behind each crate."
)

GOOD_TITLE_2 = "The Lantern Tide Ledger"
GOOD_TEXT_2 = (
    "The board is a shallow harbour drawn as a grid of stone tiles, and the water line "
    "climbs one row every few turns. A lantern keeper sprite walks the quay and can lift "
    "one lantern at a time onto a mooring post, where it holds back the tide for the "
    "tiles around it. The player has to cover the three chart marks on the far side of "
    "the harbour before the water reaches them, which means deciding early which posts "
    "are worth a lantern and which are a waste of one. On later levels there are two "
    "keepers with different walking speeds, and the player must select the one to move "
    "before an arrow key does anything, so a wrong choice costs a full tide step. Each "
    "level is a fixed harbour layout with its own post positions, and the tide rate "
    "rises as the levels go on. Colour carries the whole state: a lit post glows warm, a "
    "drowned tile turns flat grey, and a chart mark still waiting is outlined in white. "
    "Nothing is hidden from the player except the next tide step, and a run ends when "
    "the last mark is covered or the whole quay has gone under."
)

GOOD_DRAWS = (
    ("fogbound-switchyard", GOOD_TITLE_1, GOOD_TEXT_1),
    ("lantern-tide", GOOD_TITLE_2, GOOD_TEXT_2),
)

#: a title that narrates the ASSISTANT's intent instead of naming a game.
NARRATION_TITLE = "Let me design a fog game"

#: real game prose, 387 characters — under the 400 the contract names, and
#: close enough to the line to catch a threshold set far below it.
SHORT_TEXT = (
    "A quiet grid of nine tiles holds one sprite and three pads. The player walks the "
    "sprite onto a pad to light it, and the level ends when all three are lit. Later "
    "levels widen the grid and add a second pad colour, so the order of the walk starts "
    "to matter more than the speed of it. The sprite moves one tile per key press and "
    "there is no clock, so a level can be read before it is played."
)

#: the accepted prose plus ONE tool fragment — the fragment is the only change.
INCLUDE_FLAG_TEXT = (
    GOOD_TEXT_1 + " The level layouts are pulled with grep -rn --include=*.yaml over "
    "the levels folder."
)
FENCED_BLOCK_TEXT = GOOD_TEXT_1 + "\n\n```\nlevels: 8\ngrid: 16\n```"

#: 11 words in 59 characters — trips the word rule, nowhere near the char rule.
ELEVEN_WORD_TITLE = "Fog Belt Crate Yard Switch Puzzle Game With Colour Pads Now"
#: 10 words in 92 characters — trips the char rule, inside the word rule.
OVERLONG_CHAR_TITLE = (
    "Fogbound Switchyard Crateworks Terminal Conveyor Junction Palette Matching "
    "Sorting Warehouse"
)

#: every draw the contract says must be rejected, for the shared shape checks.
REJECTING_DRAWS = (
    ("real-garbage-draw", GARBAGE_TITLE, GARBAGE_TEXT),
    ("narration-title", NARRATION_TITLE, GOOD_TEXT_1),
    ("text-under-400-chars", GOOD_TITLE_1, SHORT_TEXT),
    ("tool-fragment-include-flag", GOOD_TITLE_1, INCLUDE_FLAG_TEXT),
    ("tool-fragment-fenced-block", GOOD_TITLE_1, FENCED_BLOCK_TEXT),
    ("title-eleven-words", ELEVEN_WORD_TITLE, GOOD_TEXT_1),
    ("title-over-ninety-chars", OVERLONG_CHAR_TITLE, GOOD_TEXT_1),
)

#: THE LOOSEST LINE IN THIS FILE (see the module docstring). A reason has to
#: name what it objected to in one of these words; the wording is otherwise
#: the implementation's business.
REASON_VOCABULARY = ("narration", "title", "short", "tool", "command", "chars", "words")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _cfg() -> dict:
    return load_config(PILOT)


def _new_note_names() -> list[str]:
    """Every per-family note constant the hotfix added, discovered, sorted.

    Sorted only so the parametrised ids are stable — the contract's "fixed
    order" is the order inside `LINT_SURFACE_NOTES`, which
    `_ordered_new_notes` recovers from the aggregate itself.
    """
    return sorted(
        name
        for name in vars(s1_spec)
        if NOTE_NAME_RE.match(name) and name not in PRE_EXISTING_NOTES
    )


def _new_notes() -> dict[str, str]:
    return {name: getattr(s1_spec, name) for name in _new_note_names()}


def _ordered_new_notes() -> list[tuple[str, str]]:
    """The new notes in the order `LINT_SURFACE_NOTES` lays them out."""
    notes = _new_notes()
    for name, note in notes.items():
        assert isinstance(note, str), f"{name} must be a str, got {type(note).__name__}"
        assert note in LINT_SURFACE_NOTES, (
            f"{name} does not appear VERBATIM inside LINT_SURFACE_NOTES — the aggregate is "
            f"supposed to BE the per-family notes joined, not a re-worded copy of them. "
            f"{name} starts: {note[:120]!r}"
        )
    return sorted(notes.items(), key=lambda item: LINT_SURFACE_NOTES.index(item[1]))


def _reject_reasons(title: str, text: str) -> list[str]:
    """`_prose_rejects` output, with the shape every caller may rely on."""
    reasons = _prose_rejects(title, text)
    assert isinstance(reasons, list), (
        f"_prose_rejects must return a list (`[]` = acceptable), got {type(reasons).__name__}"
    )
    for reason in reasons:
        assert isinstance(reason, str) and reason.strip(), (
            f"every reject reason must be a non-empty string, got {reason!r}"
        )
    return reasons


def _names_a_fault(reason: str) -> bool:
    lowered = reason.lower()
    return any(token in lowered for token in REASON_VOCABULARY)


# --------------------------------------------------------------------------
# 0: the fixtures this file's conclusions rest on
# --------------------------------------------------------------------------


def test_the_prose_fixtures_are_what_the_contract_describes():
    """Asserted on the FIXTURES, so a surprise here reads as a fixture fault
    rather than a contract failure."""
    for label, title, text in GOOD_DRAWS:
        assert len(text) >= 1000, f"{label}: a good draw carries >=1000 chars, got {len(text)}"
        assert len(title) <= 90, f"{label}: title is {len(title)} chars"
        assert len(title.split()) <= 10, f"{label}: title is {len(title.split())} words"
        for word in ("select", "cover"):
            assert word in text, (
                f"{label}: the good prose must contain {word!r} — the contract requires that "
                "an ordinary game word does not trip the gate"
            )
        assert "```" not in text and "--include=" not in text, f"{label}: fixture is not clean"

    assert 300 <= len(SHORT_TEXT) < 400, (
        f"SHORT_TEXT must sit just under 400 chars to be discriminating, it is {len(SHORT_TEXT)}"
    )
    assert len(ELEVEN_WORD_TITLE.split()) == 11 and len(ELEVEN_WORD_TITLE) <= 90, (
        "the word-rule title must trip ONLY the word rule: "
        f"{len(ELEVEN_WORD_TITLE.split())} words, {len(ELEVEN_WORD_TITLE)} chars"
    )
    assert len(OVERLONG_CHAR_TITLE) > 90 and len(OVERLONG_CHAR_TITLE.split()) <= 10, (
        "the char-rule title must trip ONLY the char rule: "
        f"{len(OVERLONG_CHAR_TITLE.split())} words, {len(OVERLONG_CHAR_TITLE)} chars"
    )
    assert "--include=" in INCLUDE_FLAG_TEXT and "```" in FENCED_BLOCK_TEXT
    for label, spliced in (("include-flag", INCLUDE_FLAG_TEXT), ("fence", FENCED_BLOCK_TEXT)):
        assert spliced.startswith(GOOD_TEXT_1), (
            f"the {label} case must be the ACCEPTED prose plus a fragment, so the fragment is "
            "the only variable between accept and reject"
        )


# --------------------------------------------------------------------------
# 1: the per-family lint-surface notes (A)
# --------------------------------------------------------------------------


def test_s1_spec_exposes_at_least_one_new_lint_surface_note():
    """The family list is discovered, so this is the test that stops an empty
    discovery from silently passing every parametrised test below."""
    found = _new_note_names()
    assert found, (
        "no new per-family note constant was found. The contract asks for a "
        "`<FAMILY>_NOTE_HEADER` / `<FAMILY>_NOTE` pair per §11 kill-rule family beyond neg2 "
        "and curriculum; the only `*_NOTE` attributes on gen.s1_spec are "
        f"{sorted(n for n in vars(s1_spec) if NOTE_NAME_RE.match(n))}"
    )


@pytest.mark.parametrize("name", _new_note_names())
def test_every_new_note_pairs_with_a_one_line_hash_header(name):
    """The CURRICULUM_NOTE_HEADER / CURRICULUM_NOTE shape, per family."""
    note = getattr(s1_spec, name)
    header_name = f"{name}_HEADER"

    assert hasattr(s1_spec, header_name), (
        f"{name} has no matching {header_name}. The pair is the contract's unit: a note with "
        "no header is not navigable in the prompt, and the header is what the note opens with"
    )
    header = getattr(s1_spec, header_name)

    assert isinstance(header, str) and header.strip(), f"{header_name} must be non-empty text"
    assert isinstance(note, str) and note.strip(), f"{name} must be non-empty text"
    assert "\n" not in header, f"{header_name} is ONE line, like NEG2_NOTATION_HEADER: {header!r}"
    assert header.startswith("###"), (
        f"{header_name} must be a `###` markdown heading so the prompt's sections stay "
        f"navigable; got {header!r}"
    )
    assert note.startswith(header), (
        f"{name} must OPEN with {header_name} — a header nobody reads is a second source of "
        f"truth. Note starts: {note[:120]!r}"
    )


def test_lint_surface_notes_is_exactly_the_new_notes_joined():
    """`"\\n\\n".join(<the new notes>)` and nothing else — order recovered
    from the aggregate, not guessed."""
    assert isinstance(LINT_SURFACE_NOTES, str) and LINT_SURFACE_NOTES.strip(), (
        f"LINT_SURFACE_NOTES must be non-empty text, got {LINT_SURFACE_NOTES!r}"
    )

    notes = _new_notes()
    assert len(set(notes.values())) == len(notes), (
        f"two families share one note body: {sorted(notes)}"
    )

    ordered = _ordered_new_notes()
    cursor = 0
    for position, (name, note) in enumerate(ordered):
        at = LINT_SURFACE_NOTES.index(note)
        assert at == cursor, (
            f"LINT_SURFACE_NOTES carries text that belongs to no family note: {name} was "
            f"expected at index {cursor} and starts at {at}. The gap holds "
            f"{LINT_SURFACE_NOTES[cursor:at]!r}"
        )
        cursor = at + len(note)
        if position < len(ordered) - 1:
            gap = LINT_SURFACE_NOTES[cursor:cursor + len(JOINER)]
            assert gap == JOINER, (
                f"the notes must be joined by exactly {JOINER!r}; after {name} the aggregate "
                f"holds {gap!r}"
            )
            cursor += len(JOINER)
    assert cursor == len(LINT_SURFACE_NOTES), (
        "LINT_SURFACE_NOTES has a tail after the last family note: "
        f"{LINT_SURFACE_NOTES[cursor:]!r}"
    )

    assert JOINER.join(note for _name, note in ordered) == LINT_SURFACE_NOTES, (
        f"LINT_SURFACE_NOTES is not the join of {[name for name, _ in ordered]}"
    )

    pre_existing = (
        ("NEG2_NOTATION_NOTE", NEG2_NOTATION_NOTE),
        ("CURRICULUM_NOTE", CURRICULUM_NOTE),
    )
    for name, note in pre_existing:
        assert note not in LINT_SURFACE_NOTES, (
            f"{name} is a prompt section of its own and must NOT be folded into "
            "LINT_SURFACE_NOTES — the prompt would then carry it twice"
        )


def test_the_new_note_text_fits_the_six_thousand_character_budget():
    """The budget is on the NOTES; the joiners are not note text."""
    notes = _new_notes()
    total = sum(len(note) for note in notes.values())
    by_size = sorted(((len(note), name) for name, note in notes.items()), reverse=True)
    assert total <= NOTE_BUDGET, (
        f"the new note text is {total} characters, over the {NOTE_BUDGET} the contract "
        f"budgets. Largest first: {by_size}"
    )


def test_one_family_covers_the_danger_tell_contradiction_kill():
    """The R2 kill: `knobs.danger_tell` says 'unique-hue' while `game.terms`
    holds no `hazard.*` or `loss.*` term."""
    missing = [token for token in CONTRADICTION_TOKENS if token not in LINT_SURFACE_NOTES]
    assert not missing, (
        f"LINT_SURFACE_NOTES never mentions {missing} — the writer cannot avoid the "
        "contradiction kill without being told the field AND both term families that make "
        "the claim true"
    )

    covering = [
        name
        for name, note in _new_notes().items()
        if all(token in note for token in CONTRADICTION_TOKENS)
    ]
    assert covering, (
        f"all of {list(CONTRADICTION_TOKENS)} appear in LINT_SURFACE_NOTES, but no SINGLE "
        "family note carries all three — the rule is one kill, and split across notes it "
        "teaches the writer nothing. (This is the reading of 'one family MUST cover the "
        f"contradiction rule'.) Families: {sorted(_new_notes())}"
    )


def test_the_writer_prompt_carries_the_lint_surface_notes_after_the_curriculum_note():
    prompt = build_writer_prompt(_cfg(), MINIMAL_IDEA)

    assert SCHEMA_HEADER in prompt, "the schema section header is the anchor; it must be present"
    assert NEG2_NOTATION_NOTE in prompt, "the neg2 note must still be in the prompt, verbatim"
    assert CURRICULUM_NOTE in prompt, "the curriculum note must still be in the prompt, verbatim"
    assert LINT_SURFACE_NOTES in prompt, (
        "the prompt must carry LINT_SURFACE_NOTES VERBATIM — a paraphrase in the prompt and a "
        "constant nobody reads is two sources of truth"
    )

    schema_at = prompt.index(SCHEMA_HEADER)
    neg2_at = prompt.index(NEG2_NOTATION_NOTE)
    curriculum_at = prompt.index(CURRICULUM_NOTE)
    surface_at = prompt.index(LINT_SURFACE_NOTES)

    assert schema_at < neg2_at < curriculum_at < surface_at, (
        "the whole chain is the contract's: schema header, then the neg2 note, then the "
        "curriculum note, then the lint-surface notes. Indices were "
        f"schema={schema_at}, neg2={neg2_at}, curriculum={curriculum_at}, surface={surface_at}"
    )


# --------------------------------------------------------------------------
# 2: the S0 prose gate (B)
# --------------------------------------------------------------------------


def test_the_real_garbage_draw_is_rejected_with_two_distinct_reasons():
    """The draw R2 actually got back. Two reasons, because it is wrong in at
    least two independent ways and a gate that reports one of them teaches the
    next reader half the fault."""
    reasons = _reject_reasons(GARBAGE_TITLE, GARBAGE_TEXT)

    assert reasons, (
        "the R2 garbage draw — an agent narrating a `grep -rn` over the repo — must be "
        "REJECTED. `_parse_prose` already accepts it, which is why this gate exists"
    )
    assert len(set(reasons)) >= 2, (
        f"the garbage draw must draw at least 2 DISTINCT reasons; got {reasons!r}"
    )


def test_a_first_person_narration_title_is_rejected():
    """Good prose cannot rescue a title that narrates the assistant."""
    reasons = _reject_reasons(NARRATION_TITLE, GOOD_TEXT_1)
    assert reasons, (
        f"{NARRATION_TITLE!r} is the assistant talking about its own next move, not a game "
        "name — it must be rejected even though the body below it is a real idea"
    )


def test_text_under_four_hundred_characters_is_rejected():
    """A good title over a stub is still a stub."""
    reasons = _reject_reasons(GOOD_TITLE_1, SHORT_TEXT)
    assert reasons, (
        f"a body of {len(SHORT_TEXT)} characters is under the 400 the contract requires and "
        "must be rejected, however well-formed the prose reads"
    )


@pytest.mark.parametrize(
    ("label", "text"),
    [("include-flag", INCLUDE_FLAG_TEXT), ("fenced-block", FENCED_BLOCK_TEXT)],
    ids=["include-flag", "fenced-block"],
)
def test_tool_fragments_in_the_text_are_rejected(label, text):
    """Same accepted prose, one fragment added — the fragment must flip it."""
    assert _reject_reasons(GOOD_TITLE_1, GOOD_TEXT_1) == [], (
        "fixture: the base prose must be accepted, or this test proves nothing"
    )
    reasons = _reject_reasons(GOOD_TITLE_1, text)
    assert reasons, (
        f"the {label} fragment is a transcript leaking into the idea body and must be "
        f"rejected; the only difference from the accepted draw is {text[len(GOOD_TEXT_1):]!r}"
    )


@pytest.mark.parametrize(
    ("label", "title"),
    [("eleven-words", ELEVEN_WORD_TITLE), ("over-ninety-chars", OVERLONG_CHAR_TITLE)],
    ids=["eleven-words", "over-ninety-chars"],
)
def test_an_overlong_title_is_rejected(label, title):
    """Each title rule on its own, so a failure names which one is missing."""
    reasons = _reject_reasons(title, GOOD_TEXT_1)
    assert reasons, (
        f"the {label} title ({len(title.split())} words, {len(title)} chars) must be "
        f"rejected: {title!r}"
    )


@pytest.mark.parametrize(("label", "title", "text"), GOOD_DRAWS, ids=[d[0] for d in GOOD_DRAWS])
def test_a_realistic_good_draw_is_accepted(label, title, text):
    """The gate is a filter, not a wall. `select` and `cover` are ordinary game
    words and must not read as tool or narration tells."""
    reasons = _reject_reasons(title, text)
    assert reasons == [], (
        f"the {label} draw is exactly what S0 is supposed to produce — a {len(title.split())}-"
        f"word title over {len(text)} characters of game concept — and must be ACCEPTED "
        f"(empty list). Got {reasons!r}"
    )


@pytest.mark.parametrize(
    ("label", "title", "text"), REJECTING_DRAWS, ids=[d[0] for d in REJECTING_DRAWS]
)
def test_every_reject_reason_is_a_non_empty_string_that_names_the_fault(label, title, text):
    """The reason strings themselves are NOT pinned — only that a human can
    tell from each one what was objected to.

    This is the loosest line in the file. If it fires on a reason that is
    plainly correct, widen REASON_VOCABULARY; do not reword the code.
    """
    reasons = _reject_reasons(title, text)  # shape asserted inside the helper
    assert reasons, f"the {label} draw must be rejected"
    unrecognised = [reason for reason in reasons if not _names_a_fault(reason)]
    assert not unrecognised, (
        f"{label}: these reasons name no recognisable fault — a caller printing them cannot "
        f"tell what was wrong: {unrecognised!r}. Expected one of {list(REASON_VOCABULARY)} "
        "(case-insensitive) somewhere in each. RENEGOTIABLE: this vocabulary is this file's "
        "reading, not the contract's wording"
    )


def test_prose_rejects_is_pure():
    """No disk, no cfg, no accumulated state — and a fresh list every call."""
    first = _prose_rejects(GARBAGE_TITLE, GARBAGE_TEXT)
    second = _prose_rejects(GARBAGE_TITLE, GARBAGE_TEXT)
    assert first == second, f"the same draw judged twice gave {first!r} then {second!r}"
    assert first is not second, (
        "each call must return its OWN list; a shared list lets one caller's mutation reach "
        "the next draw"
    )

    first.append("a caller mutated the result")
    assert _prose_rejects(GARBAGE_TITLE, GARBAGE_TEXT) == second, (
        "mutating a returned list changed a later verdict — the gate is holding module state"
    )

    # A good draw AFTER bad ones: an accumulator would have kept their reasons.
    assert _prose_rejects(GOOD_TITLE_2, GOOD_TEXT_2) == [], (
        "a good draw evaluated after three bad ones must still be accepted — reasons from an "
        "earlier call must not accumulate"
    )


# --------------------------------------------------------------------------
# 3: the pilot's re-spec cap (C)
# --------------------------------------------------------------------------


def test_the_pilot_config_now_caps_respec_at_four():
    """Asserted through BOTH surfaces: the loaded value, and what the
    orchestrator's accessor reads back from it."""
    cfg = _cfg()
    block = cfg["orchestrator"]
    assert block.get("respec_cap") == PILOT_RESPEC_CAP, (
        f"{PILOT} must carry orchestrator.respec_cap: {PILOT_RESPEC_CAP}, got "
        f"{block.get('respec_cap')!r}"
    )
    assert _respec_cap(cfg) == PILOT_RESPEC_CAP, (
        f"the loaded pilot config must read back as a cap of {PILOT_RESPEC_CAP} — a key the "
        f"accessor does not honour is not a raised cap; got {_respec_cap(cfg)!r}"
    )


def test_the_pilot_orchestrator_block_is_otherwise_unchanged():
    """The hotfix moves ONE number. §5's own surface is not renegotiated."""
    block = _cfg()["orchestrator"]
    missing = sorted(set(PILOT_ORCHESTRATOR) - set(block))
    assert not missing, f"{PILOT} dropped pre-existing orchestrator key(s) {missing}"
    for key, expected in PILOT_ORCHESTRATOR.items():
        assert block[key] == expected, (
            f"orchestrator.{key} moved: expected {expected!r}, found {block[key]!r}"
        )


def test_the_respec_cap_constant_stays_at_two():
    """The PILOT goes to 4; the default does not move. A hotfix that raised
    the module constant instead would raise the cap for every batch that never
    asked for it."""
    assert RESPEC_CAP == 2, (
        f"RESPEC_CAP is the default for a config with no respec_cap key; got {RESPEC_CAP!r}"
    )
