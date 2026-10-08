"""Canon document extraction for the S2 payload (B6).

Everything the implementer session is told about HOW to build a mechanic is
quoted from the signed canon under `cfg["duckwm_docs"]` — never paraphrased
here. This module is the read side of that contract: six extractors, each
anchored on a stable marker and each failing LOUD when the marker moves, so a
canon edit surfaces as a stop rather than as a silently thinner prompt.

The five layers, thinnest to thickest:

* the VOCABULARY's own two files — what each of the 71 term ids MEANS, with the
  `*Not:*` clauses that bound it. The dictionary both sides of the pipeline are
  graded against (`load_term_definitions`); total over the vocabulary, unlike
  every layer below it.
* `playbook.md` — the CURATED per-term engine pattern (24 entries covering 43
  of the 71 vocabulary terms). Entries are bold-lead PARAGRAPHS at column 0,
  not headings, one head may name several slash-separated terms, and two heads
  wrap their bold span across a newline — parse the raw text, never the lines.
* `bestiary/<slug>.md` §3 — the per-term notes of ONE official exemplar, with
  path:line citations into the real game. Five different head styles appear
  across the 25 files (the fleet wrote them in parallel); §3 is sliced
  STRICTLY between its own heading and `## 4. Render notes`, because the
  negative "confirmed absent" verdicts live in the neighbouring sections and
  would otherwise read as implementation advice.
* `playbook-skeleton.md` — the EVIDENCE base: every official and tufa grid
  line per term, total over the vocabulary. Two normalizations (both signed
  drift, not bugs in this file): the stale `phys.weight` section is dropped in
  favour of `phys.balance`, and `manip.rotate` is not a v2 term.
* `affordance-language.md` §7 — the SIX signed deception levers, each with its
  per-official exhibits, plus §10's one-sentence policy (`load_deception_levers`
  / `load_deception_policy`, contract E-1). Total over the six, like the
  vocabulary and unlike the layers above it: the catalog keyword is a shorthand
  for one of these entries, so a hole here is a keyword grounded on nothing.
* `affordance-language.md` §8 + `spec-v0.3.md` §2 — the engine-wide contracts
  (4 FORBIDDEN quotes, the 8 REQUIRED gates, the authoring conventions) — plus
  that same study's OTHER sections, the measured render grammar, quoted whole
  by `load_affordance_sections` (contract V-A; assembled in `visual_canon.py`).

Quotes are whitespace-NORMALIZED: the canon is hard-wrapped at ~72 columns, so
the -2 rule's own anchor ("-2 without a reader is FORBIDDEN") straddles a line
break in the source. A quote is a flowing sentence with the real line number it
starts on, which is what an attribution has to be.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .s0_ideas import load_vocab

# --- canon inputs (READ-ONLY, resolved under cfg["duckwm_docs"]) -------------

PLAYBOOK_MD = "design/objects/playbook.md"
SKELETON_MD = "provenance/objects-working/playbook-skeleton.md"
BESTIARY_DIR = "design/objects/bestiary"
AFFORDANCE_MD = "design/objects/affordance-language.md"
SPEC_MD = "spec-v0.3.md"
# The signed definitions live in TWO files and the FINAL one wins: the draft
# defines 51 terms, the final signs 22 more (21 promotions + the phys.weight ->
# phys.balance rename) and supersedes the draft wherever both name a term.
VOCAB_DRAFT_MD = "provenance/mechanics-audit/vocabulary-v2.md"
VOCAB_FINAL_MD = "mechanics/vocabulary-v2-final.md"

# --- vocabulary definitions -------------------------------------------------

# In both files an entry is a bullet whose BOLD head is the bare term id:
#     - **family.term** (a/b/c) — definition… *Not:* … *Ex:* …
# A bullet head can also be something else entirely — the final file's rulings
# open `- **`budget.time`: recommended retirement OVERRIDDEN…**`, whose bold
# span WRAPS across a newline exactly as two playbook heads do. So the head is
# matched with the playbook parser's wrap tolerance and then TESTED against the
# term spelling: a head that is not a bare term id is not an entry.
_DEFINITION_HEAD_RE = re.compile(r"^- \*\*([^*\n]*(?:\n[^*\n]*){0,2})\*\*", re.MULTILINE)
# An entry runs to the next bullet head or the next markdown heading, whichever
# comes first. The files hard-wrap at ~72 columns, so most of an entry — the
# `*Not:*` and `*Ex:*` clauses above all — lives on INDENTED continuation lines
# that a line-at-a-time parse would drop without saying so.
_DEFINITION_BOUNDARY_RE = re.compile(r"^(?:- \*\*|#{1,6} )", re.MULTILINE)

# --- playbook ---------------------------------------------------------------

# A term entry opens with a bold span at column 0. The span may WRAP: two of
# the 24 heads (terrain.* and info.*) break across a newline mid-name, and a
# line-by-line parse loses 11 terms without saying so. Bounded to a few lines
# so a stray `**` can never swallow the rest of the document.
_PLAYBOOK_HEAD_RE = re.compile(r"^\*\*([^*\n]*(?:\n[^*\n]*){0,2})\*\*", re.MULTILINE)
# Markdown headings end an entry just as the next entry head does.
_HEADING_RE = re.compile(r"^#{1,6} ", re.MULTILINE)
# A vocabulary term as it is written everywhere in the canon.
_TERM_RE = re.compile(r"^[a-z_]+\.[a-z_]+$")

# --- skeleton ---------------------------------------------------------------

_SKELETON_SECTION_RE = re.compile(r"^## (\S+)\s*$")
_OFFICIALS_RE = re.compile(r"^\*\*Officials \((\d+)\):\*\*")
_TUFA_RE = re.compile(r"^\*\*Tufa \((\d+)\):\*\*")
_BLOCK_END_RE = re.compile(r"^\*\*")
_OFFICIAL_LINE_RE = re.compile(r"^-\s+o:([A-Za-z0-9_]+)")
_TUFA_LINE_RE = re.compile(r"^-\s+t:([A-Za-z0-9_]+)")
_NONE_LINE_RE = re.compile(r"^-\s+\(none\)\s*$")
# The skeleton generator truncates long evidence blocks with a count, e.g.
# "- … +27 more". That count is how this parser proves it saw every line.
_MORE_LINE_RE = re.compile(r"^-\s+(?:…|\.\.\.)\s*\+(\d+)\s+more\s*$")

# Signed vocabulary drift in the skeleton (D20/D28), not parse failures:
SKELETON_RENAME = {"phys.weight": "phys.balance"}
SKELETON_IGNORE = ("manip.rotate",)

# --- bestiary ---------------------------------------------------------------

BESTIARY_S3 = "## 3. Per-term implementation notes"
BESTIARY_S4 = "## 4. Render notes"
# Five head styles across the 25 files: "### `term` — …", "### term",
# "**`term`** — …", "**term** — …", "- **term** — …". Everything before the
# name is a marker; the name itself may carry a suffix ("`no-waste`",
# "[which:rotation]") before the close.
_BESTIARY_HEAD_RE = re.compile(r"^(?:###+\s+|-\s+\*\*|\*\*)\s*`?\s*([A-Za-z_][A-Za-z0-9_]*\.\S*)")
# Any h3+ line is a boundary even when it names no term (one such subheading
# exists corpus-wide: sk48's "Terms the grids mark absent").
_BESTIARY_BOUNDARY_RE = re.compile(r"^###+\s+")

# --- affordance / spec ------------------------------------------------------

# Each FORBIDDEN contract is anchored on a unique substring of its own rule.
# The order is the canon's own (spec-v0.3 §2 lists the four the same way).
FORBIDDEN_ANCHORS = (
    "FORBIDDEN: interface paint conditions keyed to palette equality",
    "FORBIDDEN: leaving a handler without",
    "FORBIDDEN: mixed accidental semantics",
    "-2 without a reader is FORBIDDEN",
)

# The §8 FORBIDDEN quotes above are one section of a study whose OTHER sections
# are the measured render grammar. Those ship verbatim too (contract V-A), and
# each one is registered here with a keyword its own heading must still carry:
# the numbering is the canon's, so a restructure that renumbers or renames a
# section has to be seen rather than quietly quoted as the wrong grammar.
AFFORDANCE_SECTION_KEYWORDS: dict[int, str] = {
    1: "locus",
    2: "Goals",
    3: "Danger",
    5: "Meters",
    6: "Refusal",
    9: "Palette",
}
AFFORDANCE_HEADING = "## "

# --- deception levers (contract E-1) ----------------------------------------

# §7 "The deception catalog (levers, all frame-verified)" — the SIX signed
# levers, each a numbered entry with its own per-official frame-verified
# exhibits. Addressed by the canon's own numbering, and each number registered
# with a keyword its BOLD head must still carry: the `AFFORDANCE_SECTION_KEYWORDS`
# discipline one level down, so a renamed or renumbered lever is a stop rather
# than a prompt that quotes the wrong lever under the right number.
AFFORDANCE_LEVER_SECTION = 7
LEVER_HEAD_KEYWORDS: dict[int, str] = {
    1: "Look-alike",
    2: "Palette overloading",
    3: "Decoy",
    4: "Lying",
    5: "Invisible load-bearing",
    6: "Retrospective punishment",
}
# A lever is a numbered entry whose BOLD head opens it, at column 0. The entry's
# definition and exhibits live on INDENTED continuation lines (the file wraps at
# ~72 columns), so an entry is sliced head-to-head over the raw text exactly as
# a vocabulary definition is.
_LEVER_HEAD_RE = re.compile(r"^(\d+)\. \*\*([^*\n]+)\*\*", re.MULTILINE)
# §10's standing policy sentence, anchored on a unique substring of its own
# clause. The prompts quote it beside the levers, so it travels with them.
DECEPTION_POLICY_ANCHOR = "deception is always a *declared* property"

SPEC_SECTION_2 = "## §2 Engine & authoring contract"
REQUIRED_MARKER = "**REQUIRED (hard gates, the 8):**"
REQUIRED_END = "**FORBIDDEN"
CONVENTIONS_MARKER = "**Conventions:**"
# Sanity anchors: the four conventions the payload promises to carry.
CONVENTIONS_MUST_CONTAIN = ("one grid orientation", "render-side", "pre-fuses", "settled frame")

_SENTENCE_END_RE = re.compile(r"[.!?][*`\"')\]]*\s")


@dataclass
class TermDefinition:
    """One term's signed definition, VERBATIM — bullet marker, wrap and all.

    `text` is the raw slice of the canon file from the `- **term**` head to the
    start of the next entry, with trailing whitespace stripped and nothing else
    touched. The `*Not:*` and `*Ex:*` clauses are PART of the definition: a
    prompt that trims them teaches a different term than the one that was
    signed, and it is a `*Not:*` clause that decides most boundary calls.
    `source` is the canon-relative path the slice came from.
    """

    term: str
    text: str
    source: str
    source_line: int


@dataclass
class PlaybookEntry:
    """One bold-lead paragraph of `playbook.md`, shared by every term it names."""

    terms: tuple[str, ...]
    text: str
    source_line: int


@dataclass
class SkeletonSection:
    """One `## <term>` section of the evidence skeleton.

    `officials` pairs each official's slug with its EVIDENCE LINE as written
    (the bullet marker stripped): the line carries the variant annotation and
    the file:line citation, and the slug is split out because the payload picks
    the first official as the term's bestiary exemplar. `tufa` is slugs only —
    no bestiary entry exists for a tufa game, so its evidence stays in `text`.
    """

    term: str
    text: str
    officials: tuple[tuple[str, str], ...]
    tufa: tuple[str, ...]
    source_line: int


@dataclass
class BestiaryExcerpt:
    """One term's §3 entry from one official's bestiary file."""

    slug: str
    term: str
    text: str
    source_line: int


@dataclass
class Quote:
    """A verbatim engine contract, whitespace-normalized, with attribution."""

    anchor: str
    text: str
    source: str


@dataclass(frozen=True)
class DeceptionLever:
    """One numbered lever of `affordance-language.md` §7, VERBATIM.

    `text` is the raw slice of the section from the lever's own `N. **Title**`
    head to the start of the next lever (trailing whitespace stripped, nothing
    else touched), so the definition AND its per-official exhibits ride along
    — the `TermDefinition` contract exactly, where the `*Not:*` clause is part
    of the definition rather than a decoration on it.

    There is no split between "definition" and "exhibit list" here because the
    canon does not write one: §7.3's exhibits are a parenthesis, §7.4's entry is
    exhibits only, and the two levers that do read definition-then-colon-then
    -exhibits are the minority. A parser that guessed the boundary would be
    paraphrasing the canon, which this module never does. `flowed` is the same
    text unwrapped, for callers that need to search it as one sentence.
    """

    number: int
    title: str
    text: str
    source: str
    source_line: int

    @property
    def flowed(self) -> str:
        """The entry as one flowing line — the hard wrap collapsed, nothing else."""
        return " ".join(self.text.split())


@dataclass(frozen=True)
class AffordanceSection:
    """One `## <n>. …` section of the corpus study, quoted whole.

    Unlike a `Quote`, this is NOT normalized: the study's own hard wrap, bullet
    nesting and bolding are how it reads, and the heading line rides along so
    the payload shows which section it is looking at. `source` is the file name
    plus the 1-based line the heading sits on, the same attribution shape the
    FORBIDDEN quotes carry.
    """

    number: int
    title: str
    text: str
    source: str


def _docs(cfg: Mapping) -> Path:
    if "duckwm_docs" not in cfg:
        raise KeyError("config missing 'duckwm_docs' — B6 reads the canon, never guesses it")
    return Path(cfg["duckwm_docs"])


def _read(path: Path, what: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"{what} not found: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"{path}: {what} is empty")
    return text


def _line_of(text: str, offset: int) -> int:
    """1-based line number of `offset` in `text`."""
    return text.count("\n", 0, offset) + 1


# --- vocabulary definitions -------------------------------------------------


def _parse_definitions(path: Path, rel: str) -> dict[str, TermDefinition]:
    """Every `- **term** — …` entry of ONE vocabulary file, quoted verbatim."""
    text = _read(path, f"vocabulary file {rel}")
    boundaries = sorted({m.start() for m in _DEFINITION_BOUNDARY_RE.finditer(text)})

    entries: dict[str, TermDefinition] = {}
    for head in _DEFINITION_HEAD_RE.finditer(text):
        name = " ".join(head.group(1).split()).strip("`")
        if not _TERM_RE.match(name):
            continue  # a ruling, a checklist row, a prose head — not an entry
        index = bisect.bisect_right(boundaries, head.start())
        end = boundaries[index] if index < len(boundaries) else len(text)
        body = text[head.start() : end].rstrip()
        if not body:
            raise ValueError(f"{path}: empty definition body for {name!r}")
        line = _line_of(text, head.start())
        if name in entries:
            raise ValueError(
                f"{path}: term {name!r} has two definition entries "
                f"(lines {entries[name].source_line} and {line})"
            )
        entries[name] = TermDefinition(term=name, text=body, source=rel, source_line=line)
    if not entries:
        raise ValueError(
            f"{path}: no '- **term** — …' entries found — vocabulary file restructured?"
        )
    return entries


def load_term_definitions(cfg: Mapping) -> dict[str, TermDefinition]:
    """term -> its signed definition. TOTAL over `load_vocab` (all 71).

    The union of the two signed files, FINAL-WINS: the draft
    (`vocabulary-v2.md`) defines 51 terms and the sign-off document
    (`vocabulary-v2-final.md`) defines 22 more, and where both name a term the
    final file's text is the one that ships — it is the document the rename and
    promotion rulings were signed into.

    Coverage is a CONTRACT, not a best effort: every term `load_vocab` returns
    must have an entry and a missing one raises, naming the term. Both the S2
    payload and the blind S2b audit quote this mapping as the dictionary they
    are graded against, so a hole in it would silently hand one side of the
    pipeline a term the other side can define and it cannot.

    The two entries that are NOT vocabulary terms are tolerated and dropped:
    `budget.time` (kept-flagged at sign-off, outside the 71 the matrix and the
    occurrence table agree on) and `phys.weight` (the draft name of
    `phys.balance`, which carries its own final-file entry).
    """
    docs = _docs(cfg)
    merged: dict[str, TermDefinition] = {}
    for rel in (VOCAB_DRAFT_MD, VOCAB_FINAL_MD):  # FINAL last: it wins collisions
        merged.update(_parse_definitions(docs / rel, rel))

    vocab = load_vocab(cfg)
    missing = sorted(set(vocab) - set(merged))
    if missing:
        raise ValueError(
            f"{docs}: signed vocabulary terms with no definition entry in "
            f"{VOCAB_DRAFT_MD} or {VOCAB_FINAL_MD}: {missing} — the implementer payload "
            f"and the blind audit both quote this mapping, so a hole in it is a stop"
        )
    return {term: merged[term] for term in sorted(vocab)}


# --- playbook ---------------------------------------------------------------


def load_playbook_entries(cfg: Mapping) -> dict[str, PlaybookEntry]:
    """term -> its curated playbook entry (43 of the 71 terms on the real canon).

    One entry may cover several terms (`gate.plate / gate.remote / gate.key /
    gate.phase` is one paragraph); every term it names maps to the SAME
    `PlaybookEntry`. Names that are not vocabulary terms — the `click-select`
    alias, the trailing `SIGNED OFF` line — are dropped, so a head with no
    vocabulary term at all is not an entry.
    """
    path = _docs(cfg) / PLAYBOOK_MD
    text = _read(path, "playbook")
    vocab = set(load_vocab(cfg))

    heads = list(_PLAYBOOK_HEAD_RE.finditer(text))
    if not heads:
        raise ValueError(f"{path}: no bold-lead term entries found — playbook restructured?")
    # An entry ends at whichever comes first: the next bold head, or the next
    # markdown heading (the group headings that split the document).
    boundaries = sorted(
        {m.start() for m in heads} | {m.start() for m in _HEADING_RE.finditer(text)}
    )

    entries: dict[str, PlaybookEntry] = {}
    for head in heads:
        names = [part.strip().strip("`") for part in head.group(1).replace("\n", " ").split("/")]
        terms = tuple(name for name in names if _TERM_RE.match(name) and name in vocab)
        if not terms:
            continue
        index = bisect.bisect_right(boundaries, head.start())
        end = boundaries[index] if index < len(boundaries) else len(text)
        body = text[head.start() : end].strip()
        if not body:
            raise ValueError(f"{path}: empty entry body for {terms}")
        entry = PlaybookEntry(terms=terms, text=body, source_line=_line_of(text, head.start()))
        for term in terms:
            if term in entries:
                raise ValueError(
                    f"{path}: term {term!r} has two playbook entries "
                    f"(lines {entries[term].source_line} and {entry.source_line})"
                )
            entries[term] = entry
    if not entries:
        raise ValueError(f"{path}: no entry named a vocabulary term — vocabulary drift?")
    return entries


# --- skeleton ---------------------------------------------------------------


def _skeleton_evidence(
    path: Path, term: str, lines: list[str], start: int, end: int
) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    """Parse the Officials / Tufa blocks of one section body."""
    officials: list[tuple[str, str]] = []
    tufa: list[str] = []
    counts: dict[str, tuple[int, int, int]] = {}  # block -> (declared, parsed, truncated)
    block: str | None = None
    declared = parsed = truncated = 0

    def close() -> None:
        if block is not None:
            counts[block] = (declared, parsed, truncated)

    for raw in lines[start:end]:
        line = raw.rstrip()
        official_head = _OFFICIALS_RE.match(line)
        tufa_head = _TUFA_RE.match(line)
        if official_head or tufa_head:
            close()
            block = "officials" if official_head else "tufa"
            declared = int((official_head or tufa_head).group(1))
            parsed = truncated = 0
            continue
        if _BLOCK_END_RE.match(line):  # e.g. "**Knobs / traps / min-viable:**"
            close()
            block = None
            continue
        if block is None or not line.startswith("-"):
            continue
        if _NONE_LINE_RE.match(line):
            continue
        more = _MORE_LINE_RE.match(line)
        if more:
            truncated += int(more.group(1))
            continue
        if block == "officials":
            match = _OFFICIAL_LINE_RE.match(line)
            if match is None:
                raise ValueError(f"{path}: {term}: unparseable officials line {line[:60]!r}")
            officials.append((match.group(1), line.lstrip("- ").strip()))
        else:
            match = _TUFA_LINE_RE.match(line)
            if match is None:
                raise ValueError(f"{path}: {term}: unparseable tufa line {line[:60]!r}")
            tufa.append(match.group(1))
        parsed += 1
    close()

    for name, seen in (("officials", len(officials)), ("tufa", len(tufa))):
        if name not in counts:
            raise ValueError(
                f"{path}: {term}: no '{name.title()} (N):' block — file restructured?"
            )
        block_declared, block_parsed, block_truncated = counts[name]
        if block_parsed != seen:
            raise ValueError(f"{path}: {term}: {name} block accounting is inconsistent")
        if block_parsed + block_truncated != block_declared:
            raise ValueError(
                f"{path}: {term}: {name} block declares {block_declared} but this parser "
                f"read {block_parsed} (+{block_truncated} truncated) — evidence lost"
            )
    return tuple(officials), tuple(tufa)


def load_skeleton(cfg: Mapping) -> dict[str, SkeletonSection]:
    """term -> its evidence section. TOTAL over the vocabulary: every term has one.

    Two normalizations against the signed vocabulary: `phys.weight` is the
    stale name of `phys.balance` (the `phys.balance` section wins when both
    exist, as they do today) and `manip.rotate` is not a v2 term.
    """
    path = _docs(cfg) / SKELETON_MD
    text = _read(path, "playbook skeleton")
    lines = text.splitlines()
    vocab = set(load_vocab(cfg))

    starts = [
        (i, match.group(1))
        for i, line in enumerate(lines)
        if (match := _SKELETON_SECTION_RE.match(line))
    ]
    if not starts:
        raise ValueError(f"{path}: no '## <term>' sections found — file restructured?")

    sections: dict[str, SkeletonSection] = {}
    for position, (index, name) in enumerate(starts):
        if name in SKELETON_IGNORE:
            continue
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        term = SKELETON_RENAME.get(name, name)
        if term != name and term in {n for _, n in starts}:
            continue  # the canonical section exists in its own right; drop the stale duplicate
        officials, tufa = _skeleton_evidence(path, term, lines, index + 1, end)
        body = "\n".join(lines[index + 1 : end]).strip()
        if not body:
            raise ValueError(f"{path}: section {name!r} has no body")
        if term in sections:
            raise ValueError(f"{path}: duplicate section for {term!r} after normalization")
        sections[term] = SkeletonSection(
            term=term,
            text=body,
            officials=officials,
            tufa=tufa,
            source_line=index + 1,
        )

    missing = sorted(vocab - set(sections))
    if missing:
        raise ValueError(f"{path}: vocabulary terms with no skeleton section: {missing}")
    extra = sorted(set(sections) - vocab)
    if extra:
        raise ValueError(
            f"{path}: skeleton sections outside the signed vocabulary: {extra} — "
            f"add them to SKELETON_IGNORE/SKELETON_RENAME only with a signed decision"
        )
    return sections


# --- bestiary ---------------------------------------------------------------


def _bestiary_section3(path: Path, slug: str) -> tuple[list[str], int]:
    """The lines of §3 and the file line number of the first of them."""
    text = _read(path, f"bestiary entry {slug}")
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == BESTIARY_S3), None)
    if start is None:
        raise ValueError(f"{path}: no {BESTIARY_S3!r} heading — bestiary entry restructured?")
    end = next(
        (i for i, line in enumerate(lines[start + 1 :], start + 1) if line.strip() == BESTIARY_S4),
        None,
    )
    if end is None:
        raise ValueError(f"{path}: no {BESTIARY_S4!r} heading after §3 — cannot bound the slice")
    return lines[start + 1 : end], start + 2


def _joined_head_re(term: str) -> re.Pattern[str]:
    """`### goal.path_connect (+ program.compose, …)` — the canon's JOINT-entry
    idiom, where one §3 entry is the implementation note for two terms.

    Only the `+` join counts. Two other heads name a second term in prose
    ("and `manip.group_shift` as its degenerate case"; "emergent of
    manip.group_shift") — those are cross-references to an entry that lives
    elsewhere, and quoting them as that term's pattern would misattribute it.
    """
    return re.compile(r"\+\s*`?" + re.escape(term) + r"(?![A-Za-z0-9_.])")


def _is_head_for(line: str, term: str) -> bool:
    """Does this §3 head name `term`? The name may carry a suffix."""
    match = _BESTIARY_HEAD_RE.match(line)
    if match is None:
        return False
    name = match.group(1)
    if not name.startswith(term):
        return bool(_joined_head_re(term).search(line))
    rest = name[len(term) :]
    # A longer dotted name (goal.cover_all) is a DIFFERENT term, not this one.
    return not rest[:1].isalnum() and not rest.startswith(("_", "."))


def bestiary_excerpt(cfg: Mapping, slug: str, term: str) -> BestiaryExcerpt:
    """One term's §3 entry from `bestiary/<slug>.md`.

    Raises ValueError when the file does not exist or §3 has no entry for the
    term. Matching NEVER leaves §3: the absent-term verdicts in §1/§2/§5 name
    terms the game does not implement, and quoting one as an implementation
    pattern would be worse than quoting nothing.
    """
    path = _docs(cfg) / BESTIARY_DIR / f"{slug}.md"
    if not path.is_file():
        raise ValueError(f"no bestiary entry for slug {slug!r}: {path}")
    lines, first_line = _bestiary_section3(path, slug)

    index = next((i for i, line in enumerate(lines) if _is_head_for(line, term)), None)
    if index is None:
        raise ValueError(f"{path}: §3 has no entry for term {term!r}")
    end = next(
        (
            i
            for i, line in enumerate(lines[index + 1 :], index + 1)
            if _BESTIARY_BOUNDARY_RE.match(line) or _BESTIARY_HEAD_RE.match(line)
        ),
        len(lines),
    )
    body = "\n".join(lines[index:end]).strip()
    if not body:
        raise ValueError(f"{path}: §3 entry for {term!r} is empty")
    return BestiaryExcerpt(slug=slug, term=term, text=body, source_line=first_line + index)


# --- engine contracts -------------------------------------------------------


def _flatten(lines: list[str]) -> tuple[str, list[int]]:
    """Hard-wrapped markdown -> one flowing string + each line's start offset.

    The canon wraps at ~72 columns, so a rule's own sentence is split across
    lines mid-phrase. Searching the flat text is the only way to anchor on a
    phrase; the offset table maps a hit back to the line it starts on.
    """
    parts: list[str] = []
    starts: list[int] = []
    position = 0
    for line in lines:
        collapsed = " ".join(line.split())
        starts.append(position)
        if collapsed:
            parts.append(collapsed)
            parts.append(" ")
            position += len(collapsed) + 1
    return "".join(parts), starts


def _bullet_bounds(lines: list[str], index: int) -> tuple[int, int]:
    """The markdown bullet containing line `index`, as [start, end)."""
    start = index
    while start > 0 and not lines[start].startswith("- "):
        previous = lines[start - 1]
        if not previous.strip() or previous.startswith("#"):
            break
        start -= 1
    end = index + 1
    while end < len(lines):
        line = lines[end]
        if not line.strip() or line.startswith(("- ", "#")):
            break
        end += 1
    return start, end


def load_forbidden_quotes(cfg: Mapping) -> list[Quote]:
    """The four FORBIDDEN engine contracts of `affordance-language.md` §8.

    Each quote runs from the start of the sentence that states the rule to the
    end of its bullet, whitespace-normalized, and carries the real line number
    that sentence begins on. Three of the four ARE their bullet; the -2 rule
    lives in the last sentence of the `-2` semantics bullet.
    """
    path = _docs(cfg) / AFFORDANCE_MD
    text = _read(path, "affordance language")
    lines = text.splitlines()
    flat, starts = _flatten(lines)

    quotes: list[Quote] = []
    for anchor in FORBIDDEN_ANCHORS:
        needle = " ".join(anchor.split())
        hits = [m.start() for m in re.finditer(re.escape(needle), flat)]
        if not hits:
            raise ValueError(f"{path}: FORBIDDEN anchor not found: {anchor!r} — §8 rewritten?")
        if len(hits) > 1:
            raise ValueError(
                f"{path}: FORBIDDEN anchor {anchor!r} is not unique ({len(hits)} hits) — "
                f"a quote must attribute exactly one rule"
            )
        line_index = bisect.bisect_right(starts, hits[0]) - 1
        bullet_start, bullet_end = _bullet_bounds(lines, line_index)
        span_start = starts[bullet_start]
        span_end = starts[bullet_end] if bullet_end < len(starts) else len(flat)
        bullet = flat[span_start:span_end].strip()
        offset = span_start + flat[span_start:span_end].index(bullet)  # drop leading blanks
        if bullet.startswith("- "):
            bullet, offset = bullet[2:], offset + 2
        # The rule starts where its own SENTENCE starts, not where the bullet
        # does: three of the four ARE their bullet, but the -2 rule is the last
        # sentence of the `-2` semantics bullet.
        relative = hits[0] - offset
        ends = [m.end() for m in _SENTENCE_END_RE.finditer(bullet) if m.end() <= relative]
        sentence = max(ends) if ends else 0
        tail = bullet[sentence:]
        quote_offset = offset + sentence + (len(tail) - len(tail.lstrip()))
        line_index = bisect.bisect_right(starts, quote_offset) - 1
        quotes.append(
            Quote(anchor=anchor, text=tail.strip(), source=f"{path.name}:L{line_index + 1}")
        )
    return quotes


def load_affordance_sections(
    cfg: Mapping, numbers: Iterable[int]
) -> dict[int, AffordanceSection]:
    """`affordance-language.md` §§<numbers>, VERBATIM, heading line included.

    A section runs from its own `## <n>. ` heading to the line before the next
    `## ` heading (or EOF) — the document's only structural marker, and the one
    the §8 slicer above already trusts. Nothing is reflowed: §1's REQUIRED
    bullets, §6's 17/6/2 measurement and §9's closing bolded REQUIRED sentence
    are the grammar, and a normalizer would flatten exactly the emphasis the
    study uses to grade its own rules.

    Loud on every way the canon could move under us: an unregistered number, a
    heading that is missing or duplicated, a heading whose registered keyword is
    gone (renumbered or renamed), an empty body. Same house rule as the other
    loaders — a canon edit is a stop, never a thinner prompt.
    """
    path = _docs(cfg) / AFFORDANCE_MD
    text = _read(path, "affordance language")

    wanted: list[int] = []
    for number in numbers:
        if number not in AFFORDANCE_SECTION_KEYWORDS:
            raise ValueError(
                f"{path}: section {number} is not registered in AFFORDANCE_SECTION_KEYWORDS "
                f"({sorted(AFFORDANCE_SECTION_KEYWORDS)}) — quoting an unregistered section "
                f"would ship grammar nothing checks the heading of"
            )
        if number not in wanted:  # a repeat is one quote, in first-asked order
            wanted.append(number)

    sections: dict[int, AffordanceSection] = {}
    for number in wanted:
        index, section = _affordance_section_lines(path, text, number)
        title = section[0][len(AFFORDANCE_HEADING) :].strip()
        keyword = AFFORDANCE_SECTION_KEYWORDS[number]
        if keyword not in title:
            raise ValueError(
                f"{path}:L{index + 1}: §{number} is titled {title!r}, which no longer contains "
                f"{keyword!r} — the sections were renumbered or renamed, and quoting this one "
                f"as §{number} would teach the wrong grammar"
            )
        if not "\n".join(section[1:]).strip():
            raise ValueError(f"{path}: §{number} ({title!r}) has an empty body")
        sections[number] = AffordanceSection(
            number=number,
            title=title,
            text="\n".join(section).rstrip(),
            source=f"{path.name}:L{index + 1}",
        )
    return sections


def _affordance_section_lines(path: Path, text: str, number: int) -> tuple[int, list[str]]:
    """(0-based heading index, the section's lines) for `## <number>. …`.

    The slicer `load_affordance_sections` uses, factored out so §7's lever parse
    and the whole-section quote cannot disagree about where §7 ends.
    """
    lines = text.splitlines()
    heads = [i for i, line in enumerate(lines) if line.startswith(AFFORDANCE_HEADING)]
    marker = f"{AFFORDANCE_HEADING}{number}. "
    hits = [i for i in heads if lines[i].startswith(marker)]
    if not hits:
        raise ValueError(f"{path}: no {marker!r} heading — the corpus study was restructured?")
    if len(hits) > 1:
        raise ValueError(
            f"{path}: {marker!r} appears {len(hits)} times (lines "
            f"{[i + 1 for i in hits]}) — a quote must attribute exactly one section"
        )
    index = hits[0]
    end = next((i for i in heads if i > index), len(lines))
    return index, lines[index:end]


def load_deception_levers(cfg: Mapping) -> dict[int, DeceptionLever]:
    """lever number -> its signed §7 entry, VERBATIM. TOTAL over the six.

    The deception vocabulary's dictionary, and the reason contract E-1 exists:
    the catalog keyword is the shorthand and THIS is the lever. Three prompts
    quote this one mapping (`s1_spec.deception_section`,
    `s2_implement._deception_section`, `s3_verify._deception_section`), so a
    writer, an implementer and a blind auditor read the same six definitions and
    the keyword they each reach for is a reading of one text rather than of
    three. The `load_term_definitions` contract, one vocabulary over:

    * coverage is a CONTRACT — every number in `LEVER_HEAD_KEYWORDS` must have
      an entry and a missing one raises, naming what it wanted;
    * a lever the registry does NOT know is a stop too (a seventh lever is a
      canon edit, and quoting six of seven would ship a catalog that is quietly
      no longer closed);
    * each head must still carry its registered keyword, so a renamed lever
      cannot be quoted under the old number.

    Nothing is paraphrased and nothing is reflowed: §7.2's RECOMMENDED sentence
    and every per-official exhibit are the lever as it was signed.
    """
    path = _docs(cfg) / AFFORDANCE_MD
    text = _read(path, "affordance language")
    index, section = _affordance_section_lines(path, text, AFFORDANCE_LEVER_SECTION)
    body = "\n".join(section)

    heads = list(_LEVER_HEAD_RE.finditer(body))
    if not heads:
        raise ValueError(
            f"{path}: §{AFFORDANCE_LEVER_SECTION} carries no 'N. **Lever** — …' entries "
            f"— the deception catalog was restructured?"
        )
    levers: dict[int, DeceptionLever] = {}
    for position, head in enumerate(heads):
        number = int(head.group(1))
        title = " ".join(head.group(2).split())
        end = heads[position + 1].start() if position + 1 < len(heads) else len(body)
        entry = body[head.start() : end].rstrip()
        line = index + _line_of(body, head.start())
        if number in levers:
            raise ValueError(
                f"{path}: §{AFFORDANCE_LEVER_SECTION} numbers lever {number} twice "
                f"(lines {levers[number].source_line} and {line})"
            )
        if number not in LEVER_HEAD_KEYWORDS:
            raise ValueError(
                f"{path}:L{line}: §{AFFORDANCE_LEVER_SECTION} carries a lever {number} "
                f"({title!r}) that is not registered in LEVER_HEAD_KEYWORDS "
                f"({sorted(LEVER_HEAD_KEYWORDS)}) — the catalog the pipeline grounds on is "
                f"CLOSED, and silently quoting the six it knows would ship a seventh lever "
                f"no prompt names and no matcher folds"
            )
        keyword = LEVER_HEAD_KEYWORDS[number]
        if keyword not in title:
            raise ValueError(
                f"{path}:L{line}: §{AFFORDANCE_LEVER_SECTION}.{number} is headed {title!r}, "
                f"which no longer contains {keyword!r} — the levers were renumbered or "
                f"renamed, and quoting this one as lever {number} would ground the catalog "
                f"keyword on the wrong lever"
            )
        levers[number] = DeceptionLever(
            number=number,
            title=title,
            text=entry,
            source=f"{path.name}:L{line}",
            source_line=line,
        )
    missing = sorted(set(LEVER_HEAD_KEYWORDS) - set(levers))
    if missing:
        raise ValueError(
            f"{path}: §{AFFORDANCE_LEVER_SECTION} has no entry for lever(s) {missing} "
            f"({[LEVER_HEAD_KEYWORDS[number] for number in missing]}) — three prompts and "
            f"the catalog's own keyword table quote this mapping, so a hole in it is a stop"
        )
    return {number: levers[number] for number in sorted(levers)}


def load_deception_policy(cfg: Mapping) -> Quote:
    """§10's standing deception policy, one sentence, whitespace-normalized.

    "The intent-verifier checks the REQUIRED rows and flags every lever it
    detects, so deception is always a *declared* property of a generated game,
    never an accident." The sentence every deception prompt opens on, quoted
    rather than retyped for the reason the four FORBIDDEN contracts are.
    """
    path = _docs(cfg) / AFFORDANCE_MD
    text = _read(path, "affordance language")
    flat, starts = _flatten(text.splitlines())
    needle = " ".join(DECEPTION_POLICY_ANCHOR.split())
    hits = [m.start() for m in re.finditer(re.escape(needle), flat)]
    if not hits:
        raise ValueError(
            f"{path}: deception policy anchor not found: {DECEPTION_POLICY_ANCHOR!r} — §10 "
            f"rewritten? The prompts state this policy as canon, so it is quoted or nothing"
        )
    if len(hits) > 1:
        raise ValueError(
            f"{path}: deception policy anchor {DECEPTION_POLICY_ANCHOR!r} is not unique "
            f"({len(hits)} hits) — a quote must attribute exactly one sentence"
        )
    ends = [m.end() for m in _SENTENCE_END_RE.finditer(flat) if m.end() <= hits[0]]
    start = max(ends) if ends else 0
    tail = flat[start:]
    stop = next((m.end() for m in _SENTENCE_END_RE.finditer(tail)), None)
    sentence = (tail if stop is None else tail[:stop]).strip()
    line_index = bisect.bisect_right(starts, start + (len(tail) - len(tail.lstrip()))) - 1
    return Quote(
        anchor=DECEPTION_POLICY_ANCHOR,
        text=sentence,
        source=f"{path.name}:L{line_index + 1}",
    )


def _spec_section2(cfg: Mapping) -> tuple[Path, list[str]]:
    path = _docs(cfg) / SPEC_MD
    text = _read(path, "spec-v0.3")
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(SPEC_SECTION_2)), None)
    if start is None:
        raise ValueError(f"{path}: no {SPEC_SECTION_2!r} heading — spec restructured?")
    end = next(
        (i for i, line in enumerate(lines[start + 1 :], start + 1) if line.startswith("## ")),
        len(lines),
    )
    return path, lines[start:end]


def load_required_gates(cfg: Mapping) -> str:
    """spec-v0.3 §2's REQUIRED block — the 8 hard gates, verbatim."""
    path, section = _spec_section2(cfg)
    start = next((i for i, line in enumerate(section) if REQUIRED_MARKER in line), None)
    if start is None:
        raise ValueError(f"{path}: §2 has no line containing {REQUIRED_MARKER!r}")
    end = next(
        (
            i
            for i, line in enumerate(section[start + 1 :], start + 1)
            if line.startswith(REQUIRED_END)
        ),
        None,
    )
    if end is None:
        raise ValueError(f"{path}: §2 REQUIRED block is not closed by a {REQUIRED_END!r} line")
    block = "\n".join(section[start:end]).strip()
    if "8." not in block:
        raise ValueError(f"{path}: the REQUIRED block does not run to gate 8 — spec edited?")
    return block


def load_conventions(cfg: Mapping) -> str:
    """spec-v0.3 §2's authoring conventions paragraph, verbatim."""
    path, section = _spec_section2(cfg)
    start = next((i for i, line in enumerate(section) if line.startswith(CONVENTIONS_MARKER)), None)
    if start is None:
        raise ValueError(f"{path}: §2 has no paragraph starting {CONVENTIONS_MARKER!r}")
    end = next(
        (i for i, line in enumerate(section[start + 1 :], start + 1) if not line.strip()),
        len(section),
    )
    block = "\n".join(section[start:end]).strip()
    missing = [phrase for phrase in CONVENTIONS_MUST_CONTAIN if phrase not in block]
    if missing:
        raise ValueError(f"{path}: the conventions paragraph no longer states {missing}")
    return block
