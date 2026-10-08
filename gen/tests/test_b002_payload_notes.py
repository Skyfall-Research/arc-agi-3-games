"""Pins for the two b002 notes in the S2 implementer payload.

Written from the frozen b002 contract ALONE — without reading
``gen/s2_implement.py`` or the B6 payload suite — so that these pins are an
independent check that the contracted prose really reaches the implementer
prompt, and reaches it in the contracted position.

What the notes are for:

* **The scope clause.** The b001 pilot measured its own failure mode: 13
  blind-verify runs, 12 rejects, and all 12 cite at least one
  ``undeclared-term`` or ``undeclared-deception``; of ~44 individual reject
  reasons exactly 2 are omissive — every other one is ADDITIVE, i.e. the
  implementer built observable surface the spec never declared.  The Phase-C
  audit's finding #5 names the cause: the implementer is never told that
  reachability is the auditor's test, nor that the spec's declared lists are
  CLOSED sets rather than minimums.  The clause says both, and it has to be
  read before any spec text, hence its position immediately after MISSION.

* **The visual-legibility rules.** The operator's human review of the shipped pilot
  game found two defects a standing rule prevents: the render scale changed
  between levels (1-pixel lines in level 1 versus 4-pixel tiles in level 2),
  and a corner reference panel that nothing in the game teaches.  The rules
  answer both — one render scale for every level, and level 1 teaches by
  showing — and sit with the other drawing guidance, between the authoring
  conventions and the term dossiers.

These are PROMPT-ONLY additions, so the suite also re-pins the two standing
payload invariants the insertions must not break: the payload stays
byte-for-byte deterministic (no timestamps), and one prompt still leaves a
wide margin under the implementer's session token cap.
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
SCOPE_HEAD = "declared surface is the whole surface"
VISUAL_HEAD = "visual legibility"

# Pin 2 / pin 4: the load-bearing sentences of each frozen text.  A may
# re-wrap, so every marker is checked against the normalized section.
SCOPE_MARKERS = (
    "closed sets, not minimums",
    "nothing a player could observe",
    "audited blind",
    "without ever reading this spec",
    "exactly as severe as a declared mechanic you failed to build",
    "make validate cannot see this",
    "do not add it",
)
VISUAL_MARKERS = (
    "one render scale",
    "the scale of a cell may not",
    "initial frame",
    "already-satisfied",
    "before the player acts",
    "demonstrated, not encoded",
)


def normalize(text: str) -> str:
    """Wrap-, backtick- and bold-insensitive form of payload prose.

    The frozen texts carry ``**bold**`` markers and code spans, and A is free
    to re-wrap them at ~79 cols, so prose pins must survive all three.
    """
    return re.sub(r"\s+", " ", text.replace("`", "").replace("*", "")).strip().lower()


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
        f"payload, found {len(hits)}: {[line for _, line in hits]} — the b002 section "
        "is missing, duplicated, or its heading was reworded (the heading is frozen)"
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
        "insertions must not move or drop any existing payload section"
    )
    return payload.index(needle)


@pytest.fixture(scope="session")
def cfg() -> dict:
    """The pilot config the payload builder is exercised with."""
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="session")
def spec_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A throwaway spec dir: the good §11 fixture spec plus short prose."""
    path = tmp_path_factory.mktemp("b002-spec")
    shutil.copyfile(GOOD_SPEC, path / "spec.yaml")
    (path / "spec.md").write_text(
        "# Fogbound Switchyard\n\nShort non-empty prose for the b002 payload pins.\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture(scope="session")
def payload(spec_dir: Path, cfg: dict) -> str:
    """The built implementer payload — the string every pin below reads."""
    text, _report = build_payload(spec_dir, cfg)
    return text


# --- Pin 1 -----------------------------------------------------------------


def test_scope_head_sits_between_mission_and_spec_prose(payload: str) -> None:
    """The scope clause is read before any spec text, right after MISSION."""
    scope = head_offset(payload, SCOPE_HEAD)
    first_line_end = locate(payload, "\n", "the payload must be more than one line")
    prose = locate(payload, "## The spec (prose)", "the spec-prose section head")

    assert scope > first_line_end, (
        "the scope clause head is the payload's first line — it must follow MISSION, "
        "not replace it; MISSION still has to open the prompt"
    )
    assert scope < prose, (
        "the scope clause lands at or after '## The spec (prose)' — it must precede "
        "the spec text, because the implementer has to know the declared lists are "
        "closed BEFORE it reads what they contain (12 of 13 pilot rejects were "
        "additive surface)"
    )


# --- Pin 2 -----------------------------------------------------------------


def test_scope_section_states_the_closed_set_and_blind_audit_rules(payload: str) -> None:
    """Every load-bearing sentence of the frozen scope clause survives."""
    body = normalize(section_text(payload, SCOPE_HEAD))
    missing = [marker for marker in SCOPE_MARKERS if marker not in body]

    assert not missing, (
        f"the scope-clause section lost {missing} — that wording is frozen by the "
        "b002 contract: it is what tells the implementer the spec's terms and "
        "deceptions are closed sets, that a blind verifier plays the shipped game, "
        "and that unreachable-from-the-spec behaviour is as fatal as a missing "
        "mechanic (the Phase-C audit's finding #5)"
    )


# --- Pin 3 -----------------------------------------------------------------


def test_visual_head_sits_between_conventions_and_term_dossiers(payload: str) -> None:
    """The visual rules sit with the drawing guidance, before the dossiers."""
    visual = head_offset(payload, VISUAL_HEAD)
    conventions = locate(payload, "one grid orientation", "the authoring-conventions anchor")
    dossiers = locate(payload, "## Term dossiers", "the term-dossiers section head")

    assert visual > conventions, (
        "the visual-legibility section lands before the authoring conventions — the "
        "contract puts it after them, so the render-scale and level-1 rules read as "
        "hard rules on top of the conventions"
    )
    assert visual < dossiers, (
        "the visual-legibility section lands at or after '## Term dossiers' — it must "
        "sit between the conventions and the dossiers, not inside or after the "
        "per-term material"
    )


# --- Pin 4 -----------------------------------------------------------------


def test_visual_section_states_the_render_scale_and_level_one_rules(payload: str) -> None:
    """Both pilot review findings are answered in the frozen wording."""
    body = normalize(section_text(payload, VISUAL_HEAD))
    missing = [marker for marker in VISUAL_MARKERS if marker not in body]

    assert not missing, (
        f"the visual-legibility section lost {missing} — that wording is frozen by "
        "the b002 contract: rule 1 is the one-render-scale fix for the pilot's "
        "1-pixel lines in level 1 versus 4-pixel tiles in level 2, and rule 2 is the "
        "level-1-teaches-by-showing fix for the untaught corner reference panel"
    )


# --- Pin 5 -----------------------------------------------------------------


def test_payload_section_order_end_to_end(payload: str) -> None:
    """Two insertions, nothing else moves: the whole order still holds."""
    nonblank = [line for line in payload.splitlines() if line.strip()]
    assert nonblank, "the implementer payload is empty"
    assert nonblank[0].lstrip().startswith("#"), (
        f"the payload's first non-blank line is {nonblank[0]!r}, not a markdown head — "
        "MISSION must still open the payload ahead of the scope clause"
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
        ("## Term dossiers", locate(payload, "## Term dossiers", "the term dossiers")),
    ]

    for (prev_name, prev_index), (name, index) in pairwise(anchors):
        assert prev_index < index, (
            f"payload sections are out of order: {name!r} (index {index}) does not "
            f"follow {prev_name!r} (index {prev_index}) — the b002 notes are two "
            "insertions and must move nothing else"
        )

    closing = payload.rindex("make validate")
    dossiers = locate(payload, "## Term dossiers", "the term dossiers")
    assert closing > dossiers, (
        "the last 'make validate' in the payload is at or before '## Term dossiers' — "
        "the CLOSING block must still close the payload (note the scope clause also "
        "mentions 'make validate', which is why this pin uses the LAST occurrence)"
    )


# --- Pin 6 -----------------------------------------------------------------


def test_payload_is_byte_identical_across_builds(spec_dir: Path, cfg: dict) -> None:
    """Prompt-only change: no timestamps, no nondeterministic ordering."""
    first, _first_report = build_payload(spec_dir, cfg)
    second, _second_report = build_payload(spec_dir, cfg)

    assert first == second, (
        "two build_payload calls on the same spec produced different bytes — the "
        "b002 notes are static prose and must not make the payload depend on time, "
        "set ordering, or any other run-to-run state"
    )


# --- Pin 7 -----------------------------------------------------------------


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
        f"{cap} — one prompt now eats a quarter or more of the session budget, so "
        "the b002 additions have to be trimmed or the cap raised"
    )
