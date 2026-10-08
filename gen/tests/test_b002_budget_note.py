"""Pins for the b002 budget-headroom note in the S2 implementer payload.

Written from the frozen b002 contract ALONE — without reading
``gen/s2_implement.py``, any diff of it, or the B6 payload suite — so these
pins are an independent check that the contracted prose really reaches the
implementer prompt, and reaches it in the contracted position.  The sibling
``test_b002_payload_notes.py`` supplies the fixture recipe and the normalizer;
everything asserted below comes from the contract.

What the note is for:

The S2 payload never stated the per-level action-budget rule the pipeline
grades against, so the implementer was free to write caps that the pipeline
then rejected it for.  Downstream, S4 assigns every level a BASELINE of
roughly two to three times its optimal line and never fewer than 6 actions,
and the battery replays the whole game at FIVE TIMES that baseline.  A cap
that cannot admit ``5 x baseline`` is a hard reject, routed back to S2 as a
cap bug, and the whole game is re-implemented.  Multiplying those two margins
out is where the note's threshold comes from: ``5 * 3 * optimal`` is
``15 * optimal``, and ``5 * 6`` is the floor of 30, hence

    cap >= max(30, 15 * <the optimal number of actions for that level>)

The consequence is measured, not theoretical: caps set at about 1.5x the
optimal line failed the fit on five of eight levels of one game, and no redraw
could rescue it — the game was unshippable the moment it was written.  Nothing
``make validate`` checks can see this; only S4 can, which is why the rule has
to travel in the prompt.  This is the third rule of this kind (after the scope
clause and the findings feed) where the implementer was graded on something
nobody told it.

The note is a PROMPT-ONLY addition, so this suite also re-pins the two
standing payload invariants the insertion must not break: the payload stays
byte-for-byte deterministic, and one prompt still leaves a wide margin under
the implementer's session token cap.
"""

from __future__ import annotations

import re
import shutil
from itertools import pairwise
from pathlib import Path

import pytest

from gen.config import load_config
from gen.s2_implement import build_payload, parse_token_cap

GOOD_SPEC = Path(__file__).resolve().parent / "fixtures" / "specs" / "good-spec.yaml"
CONFIG_PATH = "config/b001-pilot.yaml"

# Heads are matched on a normalized fragment so a re-wrap or a stray backtick
# cannot silently unpin them; the contract lets A re-wrap the frozen texts.
BUDGET_HEAD = "per-level action budgets"
VISUAL_HEAD = "visual legibility"
SCOPE_HEAD = "declared surface is the whole surface"
DOSSIERS_HEAD = "## Term dossiers"

# Pin 3: the load-bearing sentences of the frozen budget note.  A may re-wrap,
# so every marker is checked against the normalized section.
BUDGET_MARKERS = (
    "five times that baseline",
    "never fewer than 6 actions",
    "two to three times",
    "cap bug",
    "five of eight levels",
    "difficulty comes from the structure",
)

# Pin 3, the formula itself.  Checked against `collapse` rather than
# `normalize` because the bold-insensitive normalizer strips ``*`` — and the
# multiplication sign is exactly the character this pin exists to protect.
# The pattern is wrap-insensitive (any whitespace run may fall anywhere the
# frozen text has a space) and tolerates a markdown-escaped asterisk.
BUDGET_FORMULA = re.compile(r"cap\s*>=\s*max\(\s*30\s*,\s*15\s*\\?\*")
BUDGET_FORMULA_HUMAN = "cap >= max(30, 15 * <optimal actions for that level>)"


def normalize(text: str) -> str:
    """Wrap-, backtick- and bold-insensitive form of payload prose.

    The frozen texts carry ``**bold**`` markers and code spans, and A is free
    to re-wrap them at ~79 cols, so prose pins must survive all three.
    """
    return re.sub(r"\s+", " ", text.replace("`", "").replace("*", "")).strip().lower()


def collapse(text: str) -> str:
    """Like ``normalize`` but keeps ``*``, for the ``15 *`` in the formula."""
    return re.sub(r"\s+", " ", text.replace("`", "")).strip().lower()


def markdown_heads(payload: str, marker: str) -> list[tuple[int, str]]:
    """Every ``## `` head whose normalized text contains ``marker``.

    Returns ``(character offset, head line)`` pairs; the offset is the raw
    ``payload`` index of the head, which is what the position pins compare.
    """
    hits: list[tuple[int, str]] = []
    offset = 0
    for line in payload.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("## ") and marker in normalize(stripped):
            hits.append((offset, stripped))
        offset += len(line)
    return hits


def head_offset(payload: str, marker: str) -> int:
    """Offset of the one ``## `` head matching ``marker`` (fails if not unique)."""
    hits = markdown_heads(payload, marker)
    assert len(hits) == 1, (
        f"expected exactly one '## ' head containing {marker!r} in the implementer "
        f"payload, found {len(hits)}: {[line for _, line in hits]} — the b002 budget "
        "section is missing, duplicated, or its heading was reworded (the heading is "
        "part of the frozen text)"
    )
    return hits[0][0]


def section_text(payload: str, marker: str) -> str:
    """The matching head plus its body, up to the next ``## `` head or EOF."""
    start = head_offset(payload, marker)
    nxt = payload.find("\n## ", start + 1)
    return payload[start:] if nxt == -1 else payload[start:nxt]


def locate(payload: str, needle: str, why: str) -> int:
    """Raw ``payload.index(needle)`` with a failure message naming the anchor."""
    assert needle in payload, (
        f"implementer payload is missing the anchor {needle!r} ({why}) — the b002 "
        "budget note is one insertion and must not move or drop any existing section"
    )
    return payload.index(needle)


@pytest.fixture(scope="session")
def cfg() -> dict:
    """The pilot config the payload builder is exercised with."""
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="session")
def spec_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A throwaway spec dir: the good §11 fixture spec plus short prose."""
    path = tmp_path_factory.mktemp("b002-budget-spec")
    shutil.copyfile(GOOD_SPEC, path / "spec.yaml")
    (path / "spec.md").write_text(
        "# Fogbound Switchyard\n\nShort non-empty prose for the b002 budget pins.\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture(scope="session")
def payload(spec_dir: Path, cfg: dict) -> str:
    """The built implementer payload — the string every pin below reads."""
    text, _report = build_payload(spec_dir, cfg)
    return text


# --- Pin 1 -----------------------------------------------------------------


def test_budget_head_exists_exactly_once(payload: str) -> None:
    """The budget rule reaches the implementer, and reaches it once."""
    hits = markdown_heads(payload, BUDGET_HEAD)

    assert len(hits) == 1, (
        f"expected exactly one '## ' head containing {BUDGET_HEAD!r}, found "
        f"{len(hits)}: {[line for _, line in hits]} — zero means the implementer is "
        "still never told the budget rule the pipeline grades it against (S4's "
        "cap-fit reject is a whole-game re-implementation), and more than one means "
        "the note was duplicated instead of inserted once"
    )


# --- Pin 2 -----------------------------------------------------------------


def test_budget_head_sits_between_visual_legibility_and_term_dossiers(payload: str) -> None:
    """The note sits with the other standing hard rule, before the dossiers."""
    budget = head_offset(payload, BUDGET_HEAD)
    visual = head_offset(payload, VISUAL_HEAD)
    dossiers = locate(payload, DOSSIERS_HEAD, "the term-dossiers section head")

    assert budget > visual, (
        "the budget note lands at or before the visual-legibility head — the contract "
        "puts it immediately AFTER that section, so the two standing hard rules read "
        "together as hard rules rather than the budget rule pre-empting them"
    )
    assert budget < dossiers, (
        f"the budget note lands at or after {DOSSIERS_HEAD!r} — it must sit between "
        "visual legibility and the dossiers, not inside or after the per-term "
        "material, where a rule that governs every level would read as term trivia"
    )


# --- Pin 3 -----------------------------------------------------------------


def test_budget_section_states_the_formula_and_its_arithmetic(payload: str) -> None:
    """The threshold AND the reason for it survive into the prompt."""
    section = section_text(payload, BUDGET_HEAD)
    body = normalize(section)
    missing = [marker for marker in BUDGET_MARKERS if marker not in body]

    assert BUDGET_FORMULA.search(collapse(section)), (
        f"the budget section does not carry the formula {BUDGET_FORMULA_HUMAN!r} — "
        "that single line is the whole operative rule (5x battery margin times a ~3x "
        "baseline gives 15x the optimal line, 5x the floor of 6 gives 30); without "
        "the number the implementer is back to guessing caps"
    )
    assert not missing, (
        f"the budget section lost {missing} — that wording is frozen by the b002 "
        "contract: it is what tells the implementer WHY the threshold is what it is "
        "(a baseline of two to three times the optimal line, never fewer than 6 "
        "actions, replayed at five times that baseline, rejected as a cap bug when it "
        "does not fit — measured at five of eight levels on one game), and that "
        "difficulty is supposed to come from the structure and mechanics, not from "
        "budget pressure.  An implementer given the number without the reason rounds "
        "it down"
    )


# --- Pin 4 -----------------------------------------------------------------


def test_payload_section_order_end_to_end(payload: str) -> None:
    """One insertion, nothing else moves: the whole order still holds."""
    nonblank = [line for line in payload.splitlines() if line.strip()]
    assert nonblank, "the implementer payload is empty"
    assert nonblank[0].lstrip().startswith("#"), (
        f"the payload's first non-blank line is {nonblank[0]!r}, not a markdown head — "
        "MISSION must still open the payload"
    )

    anchors = [
        ("MISSION (first non-blank line)", payload.index(nonblank[0])),
        ("the scope clause head", head_offset(payload, SCOPE_HEAD)),
        ("## The spec (prose)", locate(payload, "## The spec (prose)", "spec prose")),
        ("## The spec (machine", locate(payload, "## The spec (machine", "spec yaml")),
        ("budget triple", locate(payload, "budget triple", "the REQUIRED gates")),
        (
            # ANCHOR UPDATE, contract E-1 (2026-10-05): this row located the
            # FORBIDDEN section by its quotes' attribution, and the deception
            # section now cites the same canon file EARLIER in the payload (it
            # quotes affordance §7's six levers with their line numbers). The
            # section's own header is what this row always meant.
            "## The four FORBIDDEN engine contracts",
            locate(payload, "## The four FORBIDDEN engine contracts", "the FORBIDDEN quotes"),
        ),
        (
            "## The §7 layout-seed contract",
            locate(payload, "## The §7 layout-seed contract", "the layout-seed contract"),
        ),
        ("one grid orientation", locate(payload, "one grid orientation", "the conventions")),
        ("the visual-legibility head", head_offset(payload, VISUAL_HEAD)),
        ("the budget-headroom head", head_offset(payload, BUDGET_HEAD)),
        (DOSSIERS_HEAD, locate(payload, DOSSIERS_HEAD, "the term dossiers")),
    ]

    for (prev_name, prev_index), (name, index) in pairwise(anchors):
        assert prev_index < index, (
            f"payload sections are out of order: {name!r} (index {index}) does not "
            f"follow {prev_name!r} (index {prev_index}) — the b002 budget note is a "
            "single insertion after visual legibility and must move nothing else"
        )

    closing = payload.rindex("make validate")
    dossiers = locate(payload, DOSSIERS_HEAD, "the term dossiers")
    assert closing > dossiers, (
        f"the last 'make validate' in the payload is at or before {DOSSIERS_HEAD!r} — "
        "the CLOSING block must still close the payload (the scope clause and the "
        "budget note's own comment neighbourhood also mention 'make validate', which "
        "is why this pin uses the LAST occurrence)"
    )


# --- Pin 5 -----------------------------------------------------------------


def test_payload_is_byte_identical_across_builds(spec_dir: Path, cfg: dict) -> None:
    """Prompt-only change: no timestamps, no nondeterministic ordering."""
    first, _first_report = build_payload(spec_dir, cfg)
    second, _second_report = build_payload(spec_dir, cfg)

    assert first == second, (
        "two build_payload calls on the same spec produced different bytes — the "
        "budget note is static prose and must not make the payload depend on time, "
        "set ordering, or any other run-to-run state"
    )


# --- Pin 6 -----------------------------------------------------------------


def test_payload_leaves_room_under_the_session_token_cap(payload: str, cfg: dict) -> None:
    """One prompt must not eat a quarter of the implementer's session budget."""
    assert "implementer" in cfg, "config has no 'implementer' block to read the cap from"
    assert "session_token_cap" in cfg["implementer"], (
        "config's implementer block has no 'session_token_cap' — the payload margin "
        "cannot be checked"
    )

    cap = parse_token_cap(cfg["implementer"]["session_token_cap"])
    estimate = len(payload) // 3  # 3 chars/token: the battery's conservative estimate

    assert estimate < cap // 4, (
        f"the implementer payload is ~{estimate} tokens against a session cap of "
        f"{cap} — one prompt now eats a quarter or more of the session budget, so the "
        "budget note has to be trimmed or the cap raised"
    )
