"""W1-R15 pins: a markdown-decorated title must not reach `idea.json`.

Run: .venv/bin/python -m pytest gen/tests/test_r15_titleparse.py -v

The defect (audit R-15, the highest-frequency one): `_parse_prose` lstrips `#`
and then strips a leading `title:` prefix, and markdown bold defeats BOTH — the
line no longer STARTS with `title:`, so `**Fulcrum Pull**`,
`**Silent Beacon Relay**`, `**Coupled Conduit**` and
`**TITLE:** Keyholder's Circuit: Cover Every Marked Tile` reached idea.json
verbatim (4 of 12 fresh draws in the audit, plus the shipped conduit-watch's
historical draw).

Written BLIND against the frozen W1-R15 contract while `gen/s0_ideas.py` was
being changed: no line of that work was read. The pre-change `_parse_prose`
(HEAD) was the only source consulted, so every seam below is one that already
exists at HEAD and is re-resolved at CALL time through the module object — this
file therefore COLLECTS cleanly before the fix lands and fails named pins
rather than the import.

Standing rules this file keeps:

  * NO API call, ever. The two end-to-end pins drive the real `sample_idea`
    with its `prose_runner=` injection point, which is the seam that exists
    precisely so a draw can be exercised without buying a completion.
  * NO writes anywhere. These are pure-function pins plus two `sample_idea`
    calls, and `sample_idea` returns an `Idea` without touching disk — nothing
    here writes to `out/`, to the repo, or to a temp directory.
  * The four decorated titles are COPIES of the strings quoted in the contract
    (exhibits `out/audit/j3/idea-002.json`, `-004`, `-005`, `-007`). The
    exhibit files themselves are read-only evidence and are never opened here.

What is deliberately NOT pinned: INTERIOR emphasis. The contract leaves
`Push the *red* block` to the implementer ("decide and document"), so
`test_interior_emphasis_keeps_its_words` asserts only what holds under EITHER
decision — the words survive and the ends are clean.
"""

from __future__ import annotations

import random

import pytest

from gen import s0_ideas
from gen.config import load_config
from gen.s0_ideas import PROSE_TITLE_MAX_WORDS

PILOT = "config/b001-pilot.yaml"

# A body that clears every R2 prose gate on its own (>= 400 chars, no narration
# marker, no tool/shell fragment, no `ls`/`cat` in command position), so a
# failure below is always ABOUT THE TITLE.
BODY = (
    "The board holds a conveyor spine that carries one block between two docks, "
    "and every press rotates the spine a quarter turn. A dock accepts the block "
    "only while its indicator matches the block's colour, so finishing a level is "
    "a routing problem rather than a reflex test. The level ends once every dock "
    "has accepted its block, and the board returns to its starting arrangement if "
    "a block ever leaves the spine. Each further level adds one dock and shortens "
    "the window in which an indicator stays lit."
)

# contract pin 1 — the four recorded draws, decorated form -> undecorated form.
EXHIBITS = (
    ("**Fulcrum Pull**", "Fulcrum Pull"),
    ("**Silent Beacon Relay**", "Silent Beacon Relay"),
    ("**Coupled Conduit**", "Coupled Conduit"),
    (
        "**TITLE:** Keyholder's Circuit: Cover Every Marked Tile",
        "Keyholder's Circuit: Cover Every Marked Tile",
    ),
)

# contract pin 3 — every wrapper in emph, over titles with no interior emphasis.
EMPHASIS = ("**", "*", "__", "_")
BARE_TITLES = (
    "Fulcrum Pull",
    "Silent Beacon Relay",
    "Coupled Conduit",
    "Keyholder's Circuit: Cover Every Marked Tile",
    "Foo Bar",
)

TEN_WORDS = "Alpha Beta Gamma Delta Echo Foxtrot Golf Hotel India Juliet"
ELEVEN_WORDS = TEN_WORDS + " Kilo"


def parse(title_line: str, body: str = BODY) -> dict:
    """One prose reply, parsed. Resolved through the module so the fix is
    picked up wherever the implementer put it."""
    return s0_ideas._parse_prose(f"{title_line}\n\n{body}")


def rejects(title: str, body: str = BODY) -> list[str]:
    return s0_ideas._prose_rejects(title, body)


def prose_of(idea) -> dict:
    """An `Idea`'s prose is a dict today; tolerate a small dataclass."""
    prose = idea.prose if hasattr(idea, "prose") else idea["prose"]
    if hasattr(prose, "title"):
        return {"title": prose.title, "text": prose.text}
    return prose


def runner_returning(reply: str):
    """A prose runner that answers the same reply to the first prompt and to
    the corrective retry. Takes/ignores any extra wiring."""

    def runner(prompt: str, *args, **kwargs) -> str:
        return reply

    return runner


def draw_one(title_line: str, body: str = BODY):
    return s0_ideas.sample_idea(
        load_config(PILOT),
        random.Random(1315),
        batch_id="r15",
        index=1,
        prose_runner=runner_returning(f"{title_line}\n\n{body}"),
    )


# --------------------------------------------------------------------------
# fixture sanity — the body is not what fails anything below
# --------------------------------------------------------------------------


def test_the_probe_body_clears_every_prose_gate_on_its_own():
    assert rejects("Fulcrum Pull") == []
    assert len(TEN_WORDS.split()) == PROSE_TITLE_MAX_WORDS
    assert len(ELEVEN_WORDS.split()) == PROSE_TITLE_MAX_WORDS + 1


# --------------------------------------------------------------------------
# pin 1 — the four recorded decorated titles parse to their bare form
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("decorated", "expected"), EXHIBITS, ids=[e[1] for e in EXHIBITS])
def test_recorded_decorated_title_parses_to_its_undecorated_form(decorated, expected):
    assert parse(decorated)["title"] == expected


@pytest.mark.parametrize(("decorated", "expected"), EXHIBITS, ids=[e[1] for e in EXHIBITS])
def test_cleaning_the_title_leaves_the_body_alone(decorated, expected):
    assert parse(decorated)["text"] == BODY


# --------------------------------------------------------------------------
# pin 2 — every pre-existing title shape still parses the way it did
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("title: Foo Bar", "Foo Bar"),
        ("# Foo Bar", "Foo Bar"),
        ("Foo Bar", "Foo Bar"),
        ("## TITLE: Foo Bar", "Foo Bar"),
    ],
)
def test_undecorated_title_shapes_are_unchanged(line, expected):
    assert parse(line)["title"] == expected


# --------------------------------------------------------------------------
# pin 3 — no parsed title ever begins or ends with an emphasis marker
# --------------------------------------------------------------------------


@pytest.mark.parametrize("emph", EMPHASIS)
@pytest.mark.parametrize("bare", BARE_TITLES)
def test_wrapped_title_never_keeps_an_emphasis_marker_at_either_end(emph, bare):
    title = parse(f"{emph}{bare}{emph}")["title"]
    assert not title.startswith(("*", "_")), title
    assert not title.endswith(("*", "_")), title


@pytest.mark.parametrize("emph", EMPHASIS)
@pytest.mark.parametrize("bare", BARE_TITLES)
def test_wrapped_title_parses_to_exactly_the_bare_title(emph, bare):
    # The contract's own worked example: `**X**` -> `X`. None of these titles
    # carries interior emphasis, so stripping the wrapper is the whole job.
    assert parse(f"{emph}{bare}{emph}")["title"] == bare


@pytest.mark.parametrize("emph", EMPHASIS)
def test_wrapped_title_prefix_form_drops_both_the_wrapper_and_the_label(emph):
    assert parse(f"{emph}TITLE:{emph} Coupled Conduit")["title"] == "Coupled Conduit"


def test_interior_emphasis_keeps_its_words():
    # Decision-agnostic: the contract leaves interior emphasis to the
    # implementer, so this pins only that no CONTENT is lost and the ends are
    # clean — true whether `*red*` is kept or flattened to `red`.
    title = parse("Push the *red* block")["title"]
    assert title.startswith("Push the ")
    assert title.endswith(" block")
    assert "red" in title
    assert not title.startswith(("*", "_"))
    assert not title.endswith(("*", "_"))


# --------------------------------------------------------------------------
# pin 4 — the R2 prose gates read the CLEANED title, in both directions
# --------------------------------------------------------------------------


def test_decorated_title_over_the_word_cap_is_still_rejected():
    title = parse(f"**{ELEVEN_WORDS}**")["title"]
    reasons = rejects(title)
    assert any(f"{PROSE_TITLE_MAX_WORDS + 1} words" in reason for reason in reasons), reasons


def test_decoration_alone_never_pushes_a_title_over_the_word_cap():
    # Exactly at the cap once cleaned: the `**TITLE:** ` wrapper must not count
    # as an eleventh word.
    title = parse(f"**TITLE:** {TEN_WORDS}")["title"]
    assert title == TEN_WORDS
    assert rejects(title) == []


def test_a_decorated_title_over_the_char_cap_is_still_rejected():
    long_title = "Ward " * 18  # 90 chars of title, 18 words, before decoration
    title = parse(f"**{long_title.strip()}**")["title"]
    assert rejects(title) != []


# --------------------------------------------------------------------------
# the symptom itself — what reaches the Idea from a real draw (no API)
# --------------------------------------------------------------------------


def test_a_bolded_title_does_not_reach_the_idea():
    idea = draw_one("**Fulcrum Pull**")
    assert prose_of(idea)["title"] == "Fulcrum Pull"


def test_the_gate_does_not_fire_on_the_decoration_end_to_end():
    # At HEAD the `**TITLE:** ` wrapper counts as an eleventh word, the gate
    # rejects, the corrective retry rejects again and the draw dies with a
    # RuntimeError. After the fix the draw simply succeeds.
    idea = draw_one(f"**TITLE:** {TEN_WORDS}")
    assert prose_of(idea)["title"] == TEN_WORDS


# --------------------------------------------------------------------------
# lead-authored on review (W1-R15 close): the interleaved form. The wrap
# strip alone leaves `**TITLE**: X` as `TITLE**: X`; the prefix strip is
# emphasis-tolerant so the decoration CLASS is closed, not its instances.
# --------------------------------------------------------------------------


def test_lead_interleaved_title_prefix_is_stripped():
    from gen.s0_ideas import _parse_prose

    assert _parse_prose("**TITLE**: Interleaved Form\n\nbody")["title"] == "Interleaved Form"
    # a title that merely BEGINS with the word Title keeps it
    assert _parse_prose("Title of the Tower\n\nbody")["title"] == "Title of the Tower"
    assert _parse_prose("Titles: A Game About Naming\n\nbody")["title"] == "Titles: A Game About Naming"
