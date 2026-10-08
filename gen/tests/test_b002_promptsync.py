"""Pins for the b002 prompt-sync change: ONE dictionary, both prompts.

Written from the frozen b002 prompt-sync contract ALONE — without reading
``gen/canon_docs.py``, ``gen/s2_implement.py``, ``gen/s3_verify.py``, any diff
of them, or the implementer's report — so these pins are an independent check
that the signed definitions really reach both agents.  The edited modules are
imported and introspected at runtime; every canon phrase asserted below is read
out of the canon files themselves at test time, never retyped from the
contract.  The sibling ``test_b002_payload_notes.py`` supplies the fixture
recipe and the normalizer; everything else comes from the contract.

What the change is for:

Across both batches ~80% of all reject reasons trace to two closed lists the
implementer is never shown — the 71-term vocabulary (an id outside
``game.terms`` is one reject each) and the 11-keyword deception catalog with
its normalizing matcher.  The auditor is starved the other way round: its
prompt shipped bare ids plus corpus counts and no definitions, so it has minted
findings the signed canon explicitly excludes — ``state.wait``'s signed entry
carries a ``*Not:*`` clause that rules one of them out in as many words.  The
fix is one loader over the two signed vocabulary files (the draft under
``provenance/mechanics-audit/`` and the FINAL under ``mechanics/``, final
winning on collision) feeding BOTH prompts, so builder and auditor grade
against the same dictionary.

The five pins below are the contract's Agent-B section, in order:

1. the loader — coverage of the closed vocabulary, verbatim entries,
   final-wins, real source lines, determinism;
2. the implementer payload — the dictionary sections land between the scope
   clause and the spec prose, carry all 71 ids with their definitions, the 11
   catalog keywords, the seven degenerate policies and the reachability bar,
   the existing section order still holds, the build is byte-identical and the
   prompt still leaves a wide margin under the session token cap;
3. the budget-headroom note keeps its six pinned markers and gains the
   record-mode truth;
4. the verifier prompt ships the same definitions, no longer ships corpus
   counts, and tells the auditor to judge terms by those definitions;
5. a hygiene self-check on this file: no live-run strings (canon quotes are
   expected and fine).

Pins that assert wording assert the OPERATIVE content only — the contract
leaves the wording of the new operative rules, the constant names and the
grouping of the definitions renegotiable at lead review, so heads are located
by content (the section that carries the sentinel canon clause) rather than by
their titles, and prose is checked on stems and normalized fragments.
"""

from __future__ import annotations

import dataclasses
import re
import shutil
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path

import pytest

from gen import canon_docs
from gen.canon_docs import load_vocab
from gen.config import load_config
from gen.s1_spec import DECEPTION_CATALOG, LEVER_SPELLINGS
from gen.s2_implement import build_payload, parse_token_cap
from gen.s3_gate import POLICIES
from gen.s3_verify import build_verifier_prompt, capture, load_worker_classes, stage_worker_copy

TESTS_DIR = Path(__file__).resolve().parent
GOOD_SPEC = TESTS_DIR / "fixtures" / "specs" / "good-spec.yaml"
TOY_WORKER = TESTS_DIR / "toy_worker"
CONFIG_PATH = "config/b001-pilot.yaml"

# The two signed sources, relative to the config's `duckwm_docs` root (canon is
# READ-ONLY and is never addressed by an absolute path from this repo).
VOCAB_DRAFT_REL = "provenance/mechanics-audit/vocabulary-v2.md"
VOCAB_FINAL_REL = "mechanics/vocabulary-v2-final.md"

# The sentinel entry: the one the audit actually got wrong.  Its `*Not:*`
# clause is sliced out of the FINAL file at test time; SENTINEL_NOT_MARK is a
# word from that clause (read off `mechanics/vocabulary-v2-final.md`) and only
# guards the slice against a parser that silently grabs the wrong span.
SENTINEL_TERM = "state.wait"
SENTINEL_NOT_MARK = "engine default"

# The FINAL file's own rename ruling (`phys.weight` -> `phys.balance`): the
# promoted name must resolve to the FINAL file, and the superseded draft name
# must not reach the returned mapping at all.
RENAMED_TERM = "phys.balance"
SUPERSEDED_TERM = "phys.weight"

# Payload anchors.  These are the sibling suites' anchors, reused so that this
# suite's order pin cannot contradict theirs; the dictionary's own head is
# located by content instead, because its title is renegotiable.
SCOPE_HEAD = "declared surface is the whole surface"
VISUAL_HEAD = "visual legibility"
BUDGET_HEAD = "per-level action budgets"
SPEC_PROSE_HEAD = "## The spec (prose)"
DOSSIERS_HEAD = "## Term dossiers"

# Pin 3: the six markers test_b002_budget_note pins, re-pinned here because the
# contract makes their survival a condition of the budget note's edit.
BUDGET_MARKERS = (
    "five times that baseline",
    "never fewer than 6 actions",
    "two to three times",
    "cap bug",
    "five of eight levels",
    "difficulty comes from the structure",
)
# ... and the record-mode truth the edit adds: under `g.cap_fit: record` the
# violation ships loudly on the record instead of blocking.
CAP_FIT_RE = re.compile(r"cap[_\s-]?fit")

# A canon entry bullet: `- **family.term** (a/b/c) — definition… *Not:* … *Ex:* …`
ENTRY_RE = re.compile(r"^- \*\*([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)\*\*")
# The auditor's OLD per-id corpus count, `(a/b)`.  No canon entry carries a
# two-number parenthesis (the signed entries carry three, `(20/0/0)`), so this
# pattern cannot fire on a verbatim definition.
COUNT_PAIR_RE = re.compile(r"\(\d+/\d+\)")
COUNT_LEGEND = "(a/b)"

# Pin 5: every line carrying this token is skipped by the hygiene scanner, so
# the banned patterns below can be written down without matching themselves.
SCAN_SKIP_MARK = "b002-hygiene-exempt"
LIVE_RUN_PATTERNS = (
    (r"out/(corpus|play|pilot|ideas|batch)", "a live-run output path"),  # b002-hygiene-exempt
    (r"\$\s?\d", "a live-run cost figure"),  # b002-hygiene-exempt
    (r"(?i)fogbound|switchyard", "a live game slug"),  # b002-hygiene-exempt
    (r"(?i)\bledger\b", "a ledger line"),  # b002-hygiene-exempt
)


# --- normalizers and markdown helpers (the sibling suites' recipe) ----------


def normalize(text: str) -> str:
    """Wrap-, backtick-, bold- and escape-insensitive form of prompt prose.

    Canon entries carry ``**bold**`` markers, code spans and hard wraps, and
    the contract lets A re-wrap what it quotes, so every prose pin compares
    normalized text on both sides.  Backslashes go too: a markdown-escaped
    ``\\*`` must not unpin a ``*Not:*`` clause.
    """
    stripped = text.replace("`", "").replace("*", "").replace("\\", "")
    return re.sub(r"\s+", " ", stripped).strip().lower()


def markdown_heads(payload: str, marker: str) -> list[tuple[int, str]]:
    """Every ``## `` head whose normalized text contains ``marker``."""
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
        f"expected exactly one '## ' head containing {marker!r} in the prompt, found "
        f"{len(hits)}: {[line for _, line in hits]} — the b002 dictionary is an "
        "insertion and must not drop, duplicate or reword an existing section head"
    )
    return hits[0][0]


def locate(payload: str, needle: str, why: str) -> int:
    """Raw ``payload.index(needle)`` with a failure message naming the anchor."""
    assert needle in payload, (
        f"prompt is missing the anchor {needle!r} ({why}) — the b002 dictionary is a "
        "set of insertions and must not move or drop any existing section"
    )
    return payload.index(needle)


def split_sections(text: str) -> list[tuple[int, str]]:
    """``(offset, text)`` for the preamble and each ``## `` section."""
    starts: list[int] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("## "):
            starts.append(offset)
        offset += len(line)
    if not starts:
        return [(0, text)]
    out: list[tuple[int, str]] = []
    if starts[0] > 0:
        out.append((0, text[: starts[0]]))
    for start, end in pairwise([*starts, len(text)]):
        out.append((start, text[start:end]))
    return out


def section_carrying(text: str, needle: str, what: str) -> tuple[int, str]:
    """The FIRST ``## `` section whose normalized body contains ``needle``.

    The dictionary's heading wording is renegotiable, so its section is located
    by the canon clause it must carry rather than by its title.
    """
    hits = [(offset, body) for offset, body in split_sections(text) if needle in normalize(body)]
    assert hits, (
        f"no '## ' section of the prompt carries {what} — the b002 dictionary section "
        "is missing altogether (searched for the normalized canon text "
        f"{needle[:60]!r}…)"
    )
    return hits[0]


# --- the canon parser (this suite's own, so the pins stay independent) ------


@dataclasses.dataclass(frozen=True)
class CanonEntry:
    """One signed vocabulary bullet, wraps collapsed."""

    term: str
    source: Path
    line: int
    raw: str  # the whole bullet, `- **term** (a/b/c) — …`
    body: str  # everything after the bullet's first em dash

    @property
    def definition(self) -> str:
        """The definition proper: the body up to its first ``*Not:*``/``*Ex:*``."""
        cuts = [index for index in (self.body.find("*Not:*"), self.body.find("*Ex:*")) if index > 0]
        return self.body[: min(cuts)] if cuts else self.body

    @property
    def not_clause(self) -> str:
        """The ``*Not:*`` clause, verbatim, or ``""`` when the entry has none."""
        start = self.body.find("*Not:*")
        if start < 0:
            return ""
        end = self.body.find("*Ex:*", start)
        return (self.body[start:end] if end > 0 else self.body[start:]).strip()


def parse_canon(path: Path) -> dict[str, CanonEntry]:
    """Parse one signed vocabulary file into ``term -> CanonEntry``.

    An entry runs from its ``- **family.term**`` bullet until the next bullet,
    the next markdown head or a blank line (the files hard-wrap continuation
    lines with two spaces of indent).
    """
    entries: dict[str, CanonEntry] = {}
    term: str | None = None
    start = 0
    buffer: list[str] = []

    def flush() -> None:
        nonlocal term, buffer
        if term is None:
            return
        raw = " ".join(part.strip() for part in buffer).strip()
        head, dash, body = raw.partition("—")
        assert dash and body.strip(), (
            f"canon entry {term!r} in {path} has no '— definition' after its bullet "
            f"head ({head[:80]!r}) — the entry format this suite parses is the one the "
            "contract quotes; if canon changed shape both the loader and this parser "
            "have to be re-derived"
        )
        entries[term] = CanonEntry(term=term, source=path, line=start, raw=raw, body=body.strip())
        term, buffer = None, []

    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = ENTRY_RE.match(line)
        if match:
            flush()
            term, start, buffer = match.group(1), number, [line]
            continue
        if term is None:
            continue
        if not line.strip() or line.startswith(("#", "- ", "|", ">")):
            flush()
            continue
        buffer.append(line)
    flush()
    return entries


# --- runtime introspection of the loader's entries -------------------------


def entry_values(entry: object) -> list:
    """Every stored value of one loader entry, whatever type it is.

    The contract fixes what an entry CARRIES (term id, verbatim text, source
    file, source line) but leaves the field names to A, so the pins read the
    values by shape rather than by name.
    """
    if isinstance(entry, Mapping):
        return list(entry.values())
    if dataclasses.is_dataclass(entry) and not isinstance(entry, type):
        return [getattr(entry, field.name) for field in dataclasses.fields(entry)]
    values = []
    for name in dir(entry):
        if name.startswith("_"):
            continue
        value = getattr(entry, name)
        if not callable(value):
            values.append(value)
    return values


def entry_text(term: str, entry: object) -> str:
    """The entry's definition text: its longest non-path string value."""
    strings: list[str] = []
    for value in entry_values(entry):
        if isinstance(value, str) and ".md" not in value:
            strings.append(value)
        elif isinstance(value, (list, tuple)) and value and all(isinstance(v, str) for v in value):
            strings.append("\n".join(value))
    assert strings, (
        f"the loader's entry for {term!r} carries no definition string ({entry!r}) — the "
        "contract requires the VERBATIM entry text, never a paraphrase or a bare id"
    )
    return max(strings, key=len)


def entry_source_raw(term: str, entry: object) -> str:
    """The entry's recorded source file, as stored."""
    for value in entry_values(entry):
        if isinstance(value, (str, Path)) and ".md" in str(value):
            return str(value)
    raise AssertionError(
        f"the loader's entry for {term!r} records no '.md' source file ({entry!r}) — the "
        "contract requires source-file + line attribution in the house style, so a "
        "reviewer can walk any definition back to the signed doc"
    )


def entry_line(term: str, entry: object) -> int:
    """The entry's recorded source line, from an int field or a `file.md:L12`."""
    for value in entry_values(entry):
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    tail = re.search(r":L?(\d+)\s*$", entry_source_raw(term, entry))
    assert tail, (
        f"the loader's entry for {term!r} records no source line ({entry!r}) — the "
        "contract requires source-file + line attribution"
    )
    return int(tail.group(1))


def entry_triple(term: str, entry: object) -> tuple[str, str, int]:
    """A canonical, comparable form of one entry — used for the determinism pin."""
    return (entry_text(term, entry), entry_source_raw(term, entry), entry_line(term, entry))


def resolve_source(term: str, raw: str, docs_root: Path) -> Path:
    """Resolve a recorded source (absolute, canon-relative, or a citation)."""
    text = re.sub(r":L?\d+\s*$", "", str(raw)).strip()
    path = Path(text)
    if path.is_absolute() and path.exists():
        return path.resolve()
    if (docs_root / path).exists():
        return (docs_root / path).resolve()
    for known in (docs_root / VOCAB_DRAFT_REL, docs_root / VOCAB_FINAL_REL):
        if known.name == path.name:
            return known.resolve()
    raise AssertionError(
        f"the loader's entry for {term!r} cites a source {raw!r} that resolves to no "
        f"file under the canon root {docs_root} — entries must cite one of the two "
        "signed vocabulary files"
    )


# --- fixtures ---------------------------------------------------------------


@pytest.fixture(scope="session")
def cfg() -> dict:
    """The pilot config both prompt builders are exercised with."""
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="session")
def docs_root(cfg: dict) -> Path:
    """The READ-ONLY canon root the config resolves."""
    assert "duckwm_docs" in cfg, "config has no 'duckwm_docs' root to resolve canon against"
    return Path(cfg["duckwm_docs"]).resolve()


@pytest.fixture(scope="session")
def canon_draft(docs_root: Path) -> dict[str, CanonEntry]:
    """The draft file's 51 signed entries."""
    return parse_canon(docs_root / VOCAB_DRAFT_REL)


@pytest.fixture(scope="session")
def canon_final(docs_root: Path) -> dict[str, CanonEntry]:
    """The FINAL file's entries — these supersede the draft on collision."""
    return parse_canon(docs_root / VOCAB_FINAL_REL)


@pytest.fixture(scope="session")
def canon(canon_draft: dict, canon_final: dict) -> dict[str, CanonEntry]:
    """Draft ∪ final with FINAL WINS — the union the loader must reproduce."""
    merged = dict(canon_draft)
    merged.update(canon_final)
    return merged


@pytest.fixture(scope="session")
def vocab(cfg: dict) -> dict[str, dict]:
    """The closed vocabulary: the 71 ids every entry set is measured against."""
    return load_vocab(cfg)


@pytest.fixture(scope="session")
def load_definitions():
    """``gen.canon_docs.load_term_definitions`` — the contract's new loader."""
    loader = getattr(canon_docs, "load_term_definitions", None)
    if loader is None:
        pytest.fail(
            "gen.canon_docs exposes no load_term_definitions(cfg) — the b002 contract's "
            "loader (the one dictionary both prompts quote) has not landed; every pin "
            "below depends on it"
        )
    return loader


@pytest.fixture(scope="session")
def definitions(load_definitions, cfg: dict) -> dict:
    """The loader's mapping, term id -> entry."""
    return load_definitions(cfg)


@pytest.fixture(scope="session")
def sentinel_not_clause(canon: dict[str, CanonEntry]) -> str:
    """``state.wait``'s ``*Not:*`` clause, sliced out of the signed file."""
    entry = canon[SENTINEL_TERM]
    clause = entry.not_clause
    assert SENTINEL_NOT_MARK in clause, (
        f"the {SENTINEL_TERM!r} entry parsed out of {entry.source} carries no "
        f"'*Not:*' clause containing {SENTINEL_NOT_MARK!r} (got {clause!r}) — that "
        "clause is the sentinel this suite pins, so canon or this parser has moved"
    )
    return clause


@pytest.fixture(scope="session")
def spec_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A throwaway spec dir: the good §11 fixture spec plus short prose."""
    path = tmp_path_factory.mktemp("b002-promptsync-spec")
    shutil.copyfile(GOOD_SPEC, path / "spec.yaml")
    (path / "spec.md").write_text(
        "# Fixture Game\n\nShort non-empty prose for the b002 prompt-sync pins.\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture(scope="session")
def payload(spec_dir: Path, cfg: dict) -> str:
    """The built implementer payload — the string the pin-2 checks read."""
    text, _report = build_payload(spec_dir, cfg)
    return text


@pytest.fixture(scope="session")
def dictionary_region(payload: str) -> str:
    """The payload between the scope clause's head and the spec prose.

    The contract places every new section there, so the region — not a title —
    is what the content pins are scoped to.
    """
    start = head_offset(payload, SCOPE_HEAD)
    end = locate(payload, SPEC_PROSE_HEAD, "the spec-prose section head")
    assert start < end, (
        "the scope clause no longer precedes '## The spec (prose)' — the b002 "
        "dictionary is inserted between them, so there is nowhere for it to go"
    )
    return payload[start:end]


@pytest.fixture(scope="session")
def verifier_prompt(cfg: dict, tmp_path_factory: pytest.TempPathFactory) -> str:
    """The blind auditor's prompt, built over a staged copy of the toy worker.

    b7-style staging: load the fixture worker's classes, capture its frames,
    stage a copy outside the worker, then build the prompt the auditor reads.
    """
    game_cls, solver_cls = load_worker_classes(TOY_WORKER)
    cap = capture(game_cls, solver_cls)
    staged = tmp_path_factory.mktemp("b002-promptsync-staged") / "worker"
    stage_worker_copy(TOY_WORKER, staged)
    return build_verifier_prompt(cfg, cap, staged)


# --- Pin 1: the loader ------------------------------------------------------


def test_loader_covers_exactly_the_closed_vocabulary(definitions: dict, vocab: dict) -> None:
    """Every vocabulary term has an entry; nothing outside the vocabulary does."""
    missing = sorted(set(vocab) - set(definitions))
    extra = sorted(set(definitions) - set(vocab))

    assert not missing, (
        f"the loader has no definition for {missing} — the contract's coverage rule is "
        f"that all {len(vocab)} terms of the closed vocabulary carry one, because a "
        "term shipped to either agent as a bare id is exactly the starvation this "
        "change exists to end"
    )
    assert not extra, (
        f"the loader returns {extra} on top of the closed vocabulary — entries the "
        "vocabulary does not contain (the kept-flagged budget.time, superseded draft "
        "names such as phys.weight) are tolerated in the files but must be excluded "
        "from the mapping, or both prompts start teaching ids no spec may declare"
    )


def test_loader_ships_the_signed_definitions_verbatim(
    definitions: dict, canon: dict[str, CanonEntry]
) -> None:
    """Each entry carries its signed text, wraps aside, and nothing else's."""
    paraphrased = []
    for term, entry in sorted(definitions.items()):
        signed = canon.get(term)
        assert signed is not None, (
            f"the loader returns an entry for {term!r} that this suite cannot find in "
            "either signed file — every definition must come from canon"
        )
        if normalize(signed.body) not in normalize(entry_text(term, entry)):
            paraphrased.append(term)

    assert not paraphrased, (
        f"the loader's text for {paraphrased} is not the signed entry verbatim "
        "(definition + *Not:* + *Ex:* clauses as written) — the verbatim rule is "
        "frozen: the *Not:* clauses are what the audit is supposed to be bound by, "
        "and a paraphrase is a second, unsigned vocabulary"
    )


def test_loader_stops_each_entry_at_the_next_bullet(
    definitions: dict, canon: dict[str, CanonEntry]
) -> None:
    """Wrapped entries end at the next bullet — no bleed into the neighbour."""
    order: dict[Path, list[CanonEntry]] = {}
    for entry in canon.values():
        order.setdefault(entry.source, []).append(entry)
    for entries in order.values():
        entries.sort(key=lambda item: item.line)

    bleeding = []
    for entries in order.values():
        for signed, following in pairwise(entries):
            entry = definitions.get(signed.term)
            if entry is None:
                continue
            if normalize(following.raw)[:40] in normalize(entry_text(signed.term, entry)):
                bleeding.append((signed.term, following.term))

    assert not bleeding, (
        f"the loader's entries swallow the NEXT entry: {bleeding} — the signed files "
        "hard-wrap, so an entry runs until the next '- **' bullet or '###' head; a "
        "parser that keeps reading ships one term's definition under another's id"
    )


def test_sentinel_not_clause_survives_into_the_loader(
    definitions: dict, sentinel_not_clause: str
) -> None:
    """``state.wait``'s ``*Not:*`` clause reaches the loader word for word."""
    entry = definitions.get(SENTINEL_TERM)
    assert entry is not None, (
        f"the loader has no entry for {SENTINEL_TERM!r} — this is the term whose signed "
        "'*Not:*' clause rules out a finding a live audit produced, so it is the one "
        "entry the whole change was motivated by"
    )
    assert normalize(sentinel_not_clause) in normalize(entry_text(SENTINEL_TERM, entry)), (
        f"the loader's {SENTINEL_TERM!r} entry does not carry its signed '*Not:*' "
        f"clause ({sentinel_not_clause!r}) — the clause is the binding half of the "
        "definition; without it the auditor can re-mint the finding the signed "
        "vocabulary already excludes"
    )


def test_renamed_terms_resolve_to_the_final_file(
    definitions: dict,
    canon_draft: dict[str, CanonEntry],
    canon_final: dict[str, CanonEntry],
    docs_root: Path,
) -> None:
    """FINAL wins: the promoted name's text and source are the FINAL file's."""
    final_path = (docs_root / VOCAB_FINAL_REL).resolve()

    entry = definitions.get(RENAMED_TERM)
    assert entry is not None, (
        f"the loader has no entry for {RENAMED_TERM!r} — the FINAL file's rename ruling "
        "promotes the draft's phys.weight to this id, so it must resolve from the FINAL "
        "file"
    )
    text = normalize(entry_text(RENAMED_TERM, entry))
    assert normalize(canon_final[RENAMED_TERM].body) in text, (
        f"the loader's {RENAMED_TERM!r} text is not the FINAL file's entry — on a "
        "rename or promotion the FINAL file supersedes the draft, which is the whole "
        "point of the two-source union"
    )
    assert resolve_source(RENAMED_TERM, entry_source_raw(RENAMED_TERM, entry), docs_root) == (
        final_path
    ), (
        f"the loader attributes {RENAMED_TERM!r} to "
        f"{entry_source_raw(RENAMED_TERM, entry)!r} rather than {VOCAB_FINAL_REL} — a "
        "promoted term must cite the file that promoted it"
    )
    assert SUPERSEDED_TERM not in definitions, (
        f"the loader still returns the superseded draft name {SUPERSEDED_TERM!r} — it "
        "was renamed at sign-off and is not in the closed vocabulary, so shipping it "
        "hands both agents an id no spec may declare"
    )

    # Belt and braces for a future canon edit: today the two files' bullets do
    # not collide, so this loop is empty; if one ever does, FINAL still wins.
    for term in sorted(set(canon_draft) & set(canon_final)):
        entry = definitions.get(term)
        if entry is None:
            continue
        assert normalize(canon_final[term].body) in normalize(entry_text(term, entry)), (
            f"{term!r} is defined in both signed files and the loader shipped the "
            "DRAFT text — the union is final-wins on collision"
        )


def test_entries_cite_a_real_line_of_a_signed_file(
    definitions: dict, canon: dict[str, CanonEntry], docs_root: Path
) -> None:
    """Every entry's file:line lands on that entry's own bullet."""
    known = {(docs_root / VOCAB_DRAFT_REL).resolve(), (docs_root / VOCAB_FINAL_REL).resolve()}
    wrong = []
    for term, entry in sorted(definitions.items()):
        source = resolve_source(term, entry_source_raw(term, entry), docs_root)
        assert source in known, (
            f"the loader attributes {term!r} to {source} — the only signed sources are "
            f"{VOCAB_DRAFT_REL} and {VOCAB_FINAL_REL}"
        )
        line = entry_line(term, entry)
        lines = source.read_text(encoding="utf-8").splitlines()
        cited = lines[line - 1] if 1 <= line <= len(lines) else ""
        if not cited.startswith(f"- **{term}**"):
            wrong.append((term, f"{source.name}:{line}", cited[:60], canon[term].line))

    assert not wrong, (
        f"these entries cite a line that is not their own bullet: {wrong} (each tuple "
        "is term, citation, the line found there, and the line this suite parsed it "
        "from) — attribution is 1-based and load-bearing: it is how a reviewer walks "
        "a rejected claim back to the signed doc"
    )


def test_two_loads_are_byte_identical(load_definitions, cfg: dict) -> None:
    """The dictionary is static canon: same bytes every call."""
    first = {term: entry_triple(term, entry) for term, entry in load_definitions(cfg).items()}
    second = {term: entry_triple(term, entry) for term, entry in load_definitions(cfg).items()}

    assert first == second, (
        "two load_term_definitions calls returned different entries — both prompts "
        "quote this loader, so any run-to-run drift here makes the payload and the "
        "verifier prompt nondeterministic too"
    )


# --- Pin 2: the implementer payload ----------------------------------------


def test_dictionary_sits_between_the_scope_clause_and_the_spec_prose(
    payload: str, sentinel_not_clause: str
) -> None:
    """The dictionary is read after the scope clause and before any spec text."""
    scope = head_offset(payload, SCOPE_HEAD)
    prose = locate(payload, SPEC_PROSE_HEAD, "the spec-prose section head")
    offset, _body = section_carrying(
        payload, normalize(sentinel_not_clause), "the signed vocabulary definitions"
    )

    assert scope < offset < prose, (
        f"the vocabulary section starts at {offset}, outside the window between the "
        f"scope clause ({scope}) and '## The spec (prose)' ({prose}) — the dictionary "
        "is what makes the scope clause actionable, so the implementer has to read it "
        "before it reads what the spec declares"
    )


def test_payload_carries_every_term_with_its_signed_definition(
    dictionary_region: str, vocab: dict, canon: dict[str, CanonEntry]
) -> None:
    """All 71 ids reach the implementer, each with its definition."""
    body = normalize(dictionary_region)
    missing_ids = sorted(term for term in vocab if term not in body)
    missing_definitions = sorted(
        term
        for term in vocab
        if term in canon and normalize(canon[term].definition) not in body
    )

    assert not missing_ids, (
        f"the implementer's dictionary is missing {len(missing_ids)} of {len(vocab)} "
        f"term ids: {missing_ids} — the vocabulary is a CLOSED list and an id outside "
        "game.terms is one reject each, so a term the implementer never saw is a "
        "reject it cannot avoid"
    )
    assert not missing_definitions, (
        f"the implementer's dictionary carries {missing_definitions} as bare ids "
        "without their signed definitions — the contract builds this section from "
        "load_vocab AND load_term_definitions precisely because ids alone are what "
        "starved the implementer in the first place"
    )


def test_payload_carries_the_sentinel_not_clause(
    dictionary_region: str, sentinel_not_clause: str
) -> None:
    """The ``*Not:*`` clauses travel to the builder, not just the auditor."""
    assert normalize(sentinel_not_clause) in normalize(dictionary_region), (
        f"the implementer's dictionary does not carry {SENTINEL_TERM}'s signed "
        f"'*Not:*' clause ({sentinel_not_clause!r}) — the *Not:* clauses are binding in "
        "BOTH directions, so the builder must know which behaviour a term excludes"
    )


def test_payload_carries_the_deception_catalog(dictionary_region: str) -> None:
    """Every signed keyword and spelling, and that prose is normalized to them.

    PIN UPDATE, contract E-1 (2026-10-05) — the re-adjudication this pin's own
    message asks for. The catalog was a flat 11 keywords in which "camouflage"
    and "palette overload" were two levers and "false tell" and "lying display"
    two more; it is now the FIVE keywords of the canon's six signed levers (§7.5
    has none by design), with the other six spellings folding onto their lever.
    The pin's intent is unchanged and is checked harder: the implementer cannot
    self-audit against a list it was never given, so the dictionary must still
    carry every spelling the matcher can fire on — all ELEVEN — and now the
    lever definitions too.
    """
    body = normalize(dictionary_region)
    spellings = sorted(LEVER_SPELLINGS)
    missing = [keyword for keyword in spellings if normalize(keyword) not in body]

    assert len(DECEPTION_CATALOG) == 5 and len(spellings) == 11, (
        f"gen.s1_spec.DECEPTION_CATALOG holds {len(DECEPTION_CATALOG)} keywords over "
        f"{len(spellings)} spellings, not the 5-over-11 contract E-1 freezes — the catalog "
        "is imported, never retyped, so a change here has to be re-adjudicated before the "
        "prompt can quote it"
    )
    assert not missing, (
        f"the implementer's dictionary is missing the deception keywords {missing} — a "
        "detected keyword outside knobs.deceptions is one reject each, and the "
        "implementer cannot self-audit against a list it was never given"
    )
    assert "normaliz" in body, (
        "the implementer's dictionary never says the matcher normalizes free prose "
        "against the catalog (separator- and inflection-tolerant) — without that the "
        "implementer thinks avoiding the exact word is enough"
    )


def test_payload_carries_the_seven_degenerate_policies(dictionary_region: str) -> None:
    """The gate's seven policies, by name, with the measured lp85 warning."""
    body = normalize(dictionary_region)
    missing = [policy for policy in POLICIES if policy not in body]

    assert len(POLICIES) == 7, (
        f"gen.s3_gate.POLICIES holds {len(POLICIES)} policies, not the seven the "
        "contract freezes — the list is imported, never retyped"
    )
    assert not missing, (
        f"the implementer's dictionary is missing the degenerate policies {missing} — "
        "a game a dumb policy beats is gate-rejected however clever its mechanics, so "
        "the seven have to be named where the implementer can design against them"
    )
    assert "repeat_configured_single" in body, (
        "the dictionary does not name repeat_configured_single — it is the policy an "
        "OFFICIAL game (lp85) measurably fails, which is the warning that makes the "
        "rest of the list credible"
    )
    assert "lp85" in body, (
        "the dictionary names the seven policies but not the measured lp85 failure — "
        "the contract ships the measurement with the list, because 'an official fails "
        "this one' is what stops the implementer reading the policies as theory"
    )


def test_payload_states_the_reachability_bar_in_the_dictionary(
    payload: str, sentinel_not_clause: str
) -> None:
    """The findings' reachability sentence family reaches the FIRST build."""
    _offset, section = section_carrying(
        payload, normalize(sentinel_not_clause), "the signed vocabulary definitions"
    )
    body = normalize(section)
    missing = [stem for stem in ("reachab", "declar") if stem not in body]

    assert not missing, (
        f"the vocabulary section never states the reachability bar (missing {missing}) "
        "— the rule that a declared term must be reachable by a player in ordinary "
        "play is today only in FINDINGS_INSTRUCTIONS, i.e. only on RETRY; the first "
        "build is graded on it too"
    )
    assert "remove" in body or "redesign" in body, (
        "the vocabulary section states reachability but not its other half — "
        "undeclared-but-observable surface must be removed or redesigned, which is the "
        "half that answers the 12-of-13 additive rejects"
    )


def test_payload_section_order_end_to_end(payload: str, sentinel_not_clause: str) -> None:
    """The dictionary interleaves; every existing section keeps its place."""
    nonblank = [line for line in payload.splitlines() if line.strip()]
    assert nonblank, "the implementer payload is empty"
    assert nonblank[0].lstrip().startswith("#"), (
        f"the payload's first non-blank line is {nonblank[0]!r}, not a markdown head — "
        "MISSION must still open the payload ahead of the scope clause"
    )

    vocab_head, _body = section_carrying(
        payload, normalize(sentinel_not_clause), "the signed vocabulary definitions"
    )
    anchors = [
        ("MISSION (first non-blank line)", payload.index(nonblank[0])),
        ("the scope clause head", head_offset(payload, SCOPE_HEAD)),
        ("the vocabulary head", vocab_head),
        (SPEC_PROSE_HEAD, locate(payload, SPEC_PROSE_HEAD, "spec prose")),
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
            f"follow {prev_name!r} (index {prev_index}) — the b002 dictionary is an "
            "insertion between the scope clause and the spec prose and must move "
            "nothing else"
        )

    closing = payload.rindex("make validate")
    assert closing > locate(payload, DOSSIERS_HEAD, "the term dossiers"), (
        f"the last 'make validate' in the payload is at or before {DOSSIERS_HEAD!r} — "
        "the CLOSING block must still close the payload"
    )


def test_payload_is_byte_identical_across_builds(spec_dir: Path, cfg: dict) -> None:
    """Prompt-only change: no timestamps, no set-ordered definitions."""
    first, _first_report = build_payload(spec_dir, cfg)
    second, _second_report = build_payload(spec_dir, cfg)

    assert first == second, (
        "two build_payload calls on the same spec produced different bytes — the "
        "dictionary is generated from canon on every build, so it must be emitted in a "
        "stable order (canon order or sorted), never from a set"
    )


def test_payload_leaves_room_under_the_session_token_cap(payload: str, cfg: dict) -> None:
    """~20-25k chars of definitions still has to fit the b6 margin."""
    assert "implementer" in cfg, "config has no 'implementer' block to read the cap from"
    assert "session_token_cap" in cfg["implementer"], (
        "config's implementer block has no 'session_token_cap' — the payload margin "
        "cannot be checked"
    )

    cap = parse_token_cap(cfg["implementer"]["session_token_cap"])
    estimate = len(payload) // 3  # 3 chars/token: the battery's conservative estimate

    assert estimate < cap // 4, (
        f"the implementer payload is ~{estimate} tokens against a session cap of "
        f"{cap} — the definitions are the size budget's biggest single line item, so "
        "either the section is trimmed (grouping, dropped *Ex:* tails) or the cap rises"
    )


# --- Pin 3: the budget-headroom note ---------------------------------------


def test_budget_note_keeps_its_markers_and_gains_the_record_mode_truth(payload: str) -> None:
    """Six pinned markers survive; the record-mode escape hatch is stated."""
    start = head_offset(payload, BUDGET_HEAD)
    nxt = payload.find("\n## ", start + 1)
    section = payload[start:] if nxt == -1 else payload[start:nxt]
    body = normalize(section)
    missing = [marker for marker in BUDGET_MARKERS if marker not in body]

    assert not missing, (
        f"the budget-headroom note lost {missing} — the contract's edit ADDS the "
        "record-mode truth after the 'rejected as a cap bug' sentence and changes "
        "nothing else; these six markers are pinned by test_b002_budget_note and must "
        "survive verbatim"
    )
    assert CAP_FIT_RE.search(body), (
        "the budget-headroom note never mentions cap_fit — under 'g.cap_fit: record' "
        "the violation ships loudly on the record instead of blocking, and a note that "
        "says only 'hard reject' is now false for half the runs"
    )
    assert "record" in body, (
        "the budget-headroom note mentions cap_fit but not the record mode it names — "
        "the implementer has to know the violation is RECORDED rather than blocking "
        "there, while the target number is unchanged"
    )


# --- Pin 4: the verifier prompt ---------------------------------------------


def test_verifier_prompt_ships_the_signed_definitions(
    verifier_prompt: str, vocab: dict, canon: dict[str, CanonEntry], sentinel_not_clause: str
) -> None:
    """The auditor reads the same dictionary the implementer builds against."""
    body = normalize(verifier_prompt)
    missing = sorted(
        term
        for term in vocab
        if term in canon and normalize(canon[term].definition) not in body
    )

    assert not missing, (
        f"the verifier prompt carries {len(missing)} of {len(vocab)} terms without "
        f"their signed definitions: {missing} — shipping bare ids is the B7 parked "
        "flag, and it is how the audit minted findings the signed canon excludes"
    )
    assert normalize(sentinel_not_clause) in body, (
        f"the verifier prompt does not carry {SENTINEL_TERM}'s signed '*Not:*' clause "
        f"({sentinel_not_clause!r}) — this exact clause rules out a finding a live "
        "audit produced, so it is the one sentence the auditor most needs"
    )


def test_verifier_vocab_section_drops_the_corpus_counts(
    verifier_prompt: str, sentinel_not_clause: str
) -> None:
    """Frequency counts gave the auditor no rule; the definitions replace them."""
    _offset, section = section_carrying(
        verifier_prompt, normalize(sentinel_not_clause), "the signed vocabulary definitions"
    )
    counts = COUNT_PAIR_RE.findall(section)

    assert not counts, (
        f"the verifier's vocabulary section still ships per-id corpus counts {counts} — "
        "the contract replaces id + count with id + the VERBATIM definition; counts are "
        "frequency, not permission, and they are what the auditor had instead of a rule "
        "(signed entries carry three-number counts such as '(20/0/0)', which this "
        "pattern deliberately does not match)"
    )
    assert COUNT_LEGEND not in section, (
        f"the verifier's vocabulary section still explains the {COUNT_LEGEND} count "
        "legend — with the counts gone that sentence describes something the prompt no "
        "longer ships"
    )


def test_verifier_prompt_binds_the_audit_to_the_definitions(verifier_prompt: str) -> None:
    """One sentence in the claims contract: judge terms by the definitions."""
    body = normalize(verifier_prompt)
    hits = [match.start() for match in re.finditer(r"\bbind", body)]

    assert hits, (
        "the verifier prompt never says the definitions are BINDING — the contract adds "
        "one sentence to the claims contract ('judge terms by the definitions above; "
        "the *Not:* clauses are binding'), and without it the dictionary is decoration"
    )
    windows = [body[max(0, start - 320) : start + 320] for start in hits]
    assert any("not:" in window and ("definition" in window or "term" in window) for window in
               windows), (
        "the verifier prompt says something is 'binding' but never ties it to the terms' "
        "definitions and their *Not:* clauses — the operative rule is that behaviour a "
        "*Not:* clause excludes is NOT that term, which is the half that stops the "
        "audit re-minting excluded findings"
    )


# --- Pin 5: hygiene ---------------------------------------------------------


def test_this_suite_carries_no_live_run_strings() -> None:
    """No run output in the test file — canon quotes are fine and expected.

    Signed canon is quoted freely (that is the point of the change), and the
    pilot CONFIG path is repo configuration rather than run output; what must
    not appear is anything produced BY a run: output-tree paths, game slugs,
    spend lines, accounting rows.  Lines carrying the skip mark are where the
    patterns themselves are written down, so the scanner steps over them.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    scanned = "\n".join(
        line for line in source.splitlines() if SCAN_SKIP_MARK not in line
    )
    found = [
        (why, match.group(0))
        for pattern, why in LIVE_RUN_PATTERNS
        for match in re.finditer(pattern, scanned)
    ]

    assert not found, (
        f"this test file contains live-run content: {found} — the b002 contract bars "
        "run output (slugs, accounting rows, report text, spend) from both agents' "
        "work; canon quotes are the only quoted material allowed here"
    )
