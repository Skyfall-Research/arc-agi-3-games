"""R2 hotfix acceptance: lint-killed spec dirs are ARCHIVED out of the corpus,
and the writer prompt carries the `neg2_readers` notation note — tested from
the contract.

Run: .venv/bin/python -m pytest gen/tests/test_r2_hotfix.py -v

Written against the frozen R2 mini-contract while `gen/orchestrator.py` and
`gen/s1_spec.py` were changed in parallel; nothing below was read off that
implementation. The bug being pinned is the one R2 hit: a lint-killed spec dir
kept its `idea.json`, so the NEXT attempt's slot discovery found two dirs
claiming one idea and died on `LedgerError`.

Two standing rules this file keeps:

  * NO API call, ever. `build_writer_prompt` is a pure builder; every
    orchestrator helper under test is filesystem-only.
  * NO writes outside `tmp_path`. `out/` is never touched, and `config/` is
    read (`load_config`) and never written.

Contract readings this file encodes where the R2 contract left a choice open —
each one is a line to renegotiate, not a fact:

  * "UTC YYYYMMDD-HHMMSS" is pinned by PARSING the stamp out of the archived
    dir name and demanding it sit within 5 minutes of
    `datetime.now(timezone.utc)`. That is what makes "UTC" testable: a stamp
    taken in local time fails on any machine not on UTC, which is the bug
    worth catching. The 5-minute window is slack, not contract.
  * "on collision appends -2, -3, …" is tested primarily as NEVER CLOBBERS:
    three archives of the same dir name must yield three distinct destinations
    that all still exist, each with its own contents. The literal `-2` / `-3`
    suffix is asserted only when the archives actually landed in the same
    second — across a second boundary there is no collision to resolve, and
    demanding the suffix anyway would make this test a clock flake.
  * "Raises on failure (never swallows)" names no exception type. Read as: a
    spec dir that is not there must raise something the caller can see —
    `OSError` (what `shutil.move` raises) or `ValueError` (what a validating
    implementation raises) — and must not quietly return a path.
  * The sweep's iteration order is pinned by naming the fixture dirs so that
    `sorted()` order is unambiguous; the test asserts that order on the
    fixture itself before sweeping, so a surprise there reads as a fixture
    fault rather than a contract failure.
  * A dir holding a FAILED lint report but NO `idea.json` is read as "not a
    spec dir" and must be KEPT — "skips … dirs without idea.json" is taken as
    a skip of the whole dir, not merely of the id check.
  * The neg2 note's correct example is read as the FLOW form the contract
    spells — `[{<class>: "<mask text>"}]` — and its single key must not be the
    literal `sprite-class`: a note whose only example is `{sprite-class: mask}`
    restates the very ambiguity it exists to kill.
  * "positioned AFTER the schema section header" is read as ordering inside
    the prompt string (`index(note) > index(SCHEMA_HEADER)`), not adjacency.
  * `SCHEMA_HEADER` is pinned to the text the contract quotes. A hotfix that
    also reworded the header would satisfy an ordering check while moving the
    anchor it is measured against, so the anchor is pinned too.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gen.config import load_config
from gen.orchestrator import (
    KILLED_DIRNAME,
    RESPEC_CAP,
    LedgerError,
    _discover_spec_dir,
    archive_killed_spec,
    sweep_killed_specs,
)
from gen.s1_spec import NEG2_NOTATION_NOTE, SCHEMA_HEADER, build_writer_prompt

PILOT = "config/b001-pilot.yaml"

# The unchanged tail of the discovery error — the sentence the hotfix must not
# touch, because the whole point is that it stops firing, not that it moves.
LEDGER_TAIL = "a slot has exactly one spec dir"

SCHEMA_HEADER_TEXT = "### Required output schema (spec-v0.3 §11 — the linter checks exactly this)"

# "<original dirname>-<UTC YYYYMMDD-HHMMSS>" plus the optional collision bump.
SUFFIX_RE = re.compile(r"^(?P<stamp>\d{8}-\d{6})(?:-(?P<bump>\d+))?$")
STAMP_SLACK = timedelta(minutes=5)

# A hand-written idea carrying exactly what `build_writer_prompt` requires
# (id, seed_terms, prose) — the cheapest input in gen/tests, and the right one
# here: the notation note is static prompt text, so no artifact under `out/`
# needs to exist for this file to run.
MINIMAL_IDEA = {
    "id": "b001-pilot-i001",
    "seed_terms": ["info.fog", "goal.cover"],
    "prose": {
        "title": "Fogbound Switchyard",
        "text": "Belts carry coloured crates past cycleable junctions toward matching pads.",
    },
}

# Every flow-style `{...}` literal, and the "there is a second key" tell: a
# comma followed by another `key:`. Counting commas beats counting colons — a
# quoted mask text may legitimately contain a colon.
BRACE_RE = re.compile(r"\{[^{}]*\}")
LISTED_BRACE_RE = re.compile(r"\[\s*\{[^{}\[\]]*\}\s*\]")
SECOND_KEY_RE = re.compile(r",\s*[A-Za-z_<][\w<>.\-]*\s*:")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _cfg() -> dict:
    return load_config(PILOT)


def _flat(text: str) -> str:
    """Whitespace-normalised, so a re-wrapped note still matches."""
    return " ".join(text.split())


def _near(flat: str, anchor: str, other: str, window: int = 200) -> bool:
    """True when `other` occurs within `window` characters of `anchor`."""
    forward = rf"{re.escape(anchor)}.{{0,{window}}}{re.escape(other)}"
    reverse = rf"{re.escape(other)}.{{0,{window}}}{re.escape(anchor)}"
    return bool(
        re.search(forward, flat, re.IGNORECASE) or re.search(reverse, flat, re.IGNORECASE)
    )


def _spec_dir(parent: Path, name: str, *, idea_id: str, passed: bool | None) -> Path:
    """One minimal S1 corpus dir.

    `passed=None` builds the rubble a crashed or half-written lint leaves
    behind: the spec files and the copied idea, but no `lint-report.json`.
    """
    spec = parent / name
    spec.mkdir(parents=True)
    (spec / "idea.json").write_text(json.dumps({"id": idea_id}), encoding="utf-8")
    (spec / "spec.yaml").write_text(f"game:\n  slug: {name}\n", encoding="utf-8")
    (spec / "spec.md").write_text(f"# {name}\n", encoding="utf-8")
    if passed is not None:
        (spec / "lint-report.json").write_text(
            json.dumps({"passed": passed, "kills": [], "warns": [], "idea_ref": idea_id}),
            encoding="utf-8",
        )
    return spec


def _idea_file(tmp_path: Path, idea_id: str) -> Path:
    """The slot's idea, where S0 would have written it."""
    ideas = tmp_path / "ideas" / "b001-pilot"
    ideas.mkdir(parents=True, exist_ok=True)
    path = ideas / "idea-001.json"
    path.write_text(json.dumps({"id": idea_id, "seed_terms": []}), encoding="utf-8")
    return path


def _archived_suffix(dest: Path, original: str) -> re.Match[str]:
    """The `<stamp>[-<bump>]` tail of an archived dir name, parsed."""
    assert dest.name.startswith(f"{original}-"), (
        f"the archived dir {dest.name!r} must keep {original!r} as its prefix"
    )
    tail = dest.name[len(original) + 1:]
    match = SUFFIX_RE.match(tail)
    assert match, (
        f"{dest.name!r} must be '<original>-<UTC YYYYMMDD-HHMMSS>' (plus a collision "
        f"bump); the part after {original!r} was {tail!r}"
    )
    return match


def _stamp_is_utc_now(match: re.Match[str], taken_before: datetime) -> None:
    stamp = datetime.strptime(match.group("stamp"), "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    drift = abs(stamp - taken_before)
    assert drift <= STAMP_SLACK, (
        f"the archive stamp {match.group('stamp')} is {drift} from UTC now "
        f"({taken_before:%Y%m%d-%H%M%S}) — the contract says UTC, and a local-time "
        "stamp is off by the machine's offset"
    )


def _single_key(mapping: str) -> bool:
    return ":" in mapping and not SECOND_KEY_RE.search(mapping)


# --------------------------------------------------------------------------
# 1: the constants that must not move
# --------------------------------------------------------------------------


def test_killed_dirname_is_dot_killed():
    assert KILLED_DIRNAME == ".killed"


def test_respec_cap_is_unchanged():
    """The hotfix archives the kill; it does not buy the slot more attempts."""
    assert RESPEC_CAP == 2


def test_schema_header_is_unchanged():
    """The anchor the notation note is positioned against."""
    assert SCHEMA_HEADER == SCHEMA_HEADER_TEXT


# --------------------------------------------------------------------------
# 2: archive_killed_spec
# --------------------------------------------------------------------------


def test_archive_killed_spec_moves_the_dir_under_killed(tmp_path):
    corpus = tmp_path / "corpus" / "b001-pilot"
    corpus.mkdir(parents=True)
    spec = _spec_dir(corpus, "fogbound-switchyard", idea_id="b001-pilot-i001", passed=False)

    taken_before = datetime.now(UTC)
    dest = archive_killed_spec(spec)

    assert isinstance(dest, Path), f"archive_killed_spec must return a Path, got {type(dest)}"
    assert dest.is_dir(), f"the returned destination {dest} must exist as a directory"
    assert not spec.exists(), "the killed dir must be MOVED out of the corpus, not copied"
    assert dest.parent == corpus / KILLED_DIRNAME, (
        f"the archive belongs in <parent>/{KILLED_DIRNAME}/, got {dest.parent}"
    )
    _stamp_is_utc_now(_archived_suffix(dest, spec.name), taken_before)

    # the whole dir travelled, not just its name
    assert json.loads((dest / "idea.json").read_text(encoding="utf-8"))["id"] == "b001-pilot-i001"
    assert (dest / "spec.yaml").read_text(encoding="utf-8") == "game:\n  slug: fogbound-switchyard\n"
    assert (dest / "spec.md").is_file()
    report = json.loads((dest / "lint-report.json").read_text(encoding="utf-8"))
    assert report["passed"] is False, "the evidence of the kill is archived with it"


def test_archive_killed_spec_creates_the_killed_dir_when_absent(tmp_path):
    corpus = tmp_path / "corpus" / "b001-pilot"
    corpus.mkdir(parents=True)
    spec = _spec_dir(corpus, "fogbound-switchyard", idea_id="b001-pilot-i001", passed=False)
    assert not (corpus / KILLED_DIRNAME).exists(), "fixture: nothing archived yet"

    dest = archive_killed_spec(spec)

    assert (corpus / KILLED_DIRNAME).is_dir(), f"{KILLED_DIRNAME}/ must be created as needed"
    assert dest.parent == corpus / KILLED_DIRNAME


def test_archive_killed_spec_never_clobbers_a_repeated_name(tmp_path):
    """Three kills of the same slug must leave three archives, not one.

    The slug comes from the SPEC, so a re-spec of the same idea can hand the
    archiver the same dir name twice inside one second — which is exactly the
    collision the `-2`, `-3` rule exists for.
    """
    corpus = tmp_path / "corpus" / "b001-pilot"
    corpus.mkdir(parents=True)

    dests = []
    for generation in range(3):
        spec = _spec_dir(corpus, "fogbound-switchyard", idea_id="b001-pilot-i001", passed=False)
        (spec / "spec.md").write_text(f"generation {generation}\n", encoding="utf-8")
        dests.append(archive_killed_spec(spec))

    assert len(set(dests)) == 3, f"archives collided onto the same path: {dests}"
    for generation, dest in enumerate(dests):
        assert dest.is_dir(), f"archive {generation} ({dest}) is gone — it was overwritten"
        assert (dest / "spec.md").read_text(encoding="utf-8") == f"generation {generation}\n", (
            f"archive {generation} does not hold its own contents"
        )
        _archived_suffix(dest, "fogbound-switchyard")

    # When two archives DID land in the same second, the bump is the contract's.
    # Across a second boundary there is no collision, and nothing to assert.
    if dests[1].name.startswith(dests[0].name):
        assert dests[1].name == f"{dests[0].name}-2"
    if dests[2].name.startswith(dests[0].name):
        assert dests[2].name == f"{dests[0].name}-3"


def test_archive_killed_spec_raises_on_a_missing_dir(tmp_path):
    """Raises on failure, never swallows — a bad archive must not look like a
    good one, because the caller appends a ledger line on the strength of it."""
    corpus = tmp_path / "corpus" / "b001-pilot"
    corpus.mkdir(parents=True)
    missing = corpus / "never-written"

    with pytest.raises((OSError, ValueError)):
        archive_killed_spec(missing)

    killed = corpus / KILLED_DIRNAME
    landed = sorted(p.name for p in killed.iterdir()) if killed.is_dir() else []
    assert landed == [], f"a failed archive must leave no destination behind, found {landed}"


# --------------------------------------------------------------------------
# 3: sweep_killed_specs
# --------------------------------------------------------------------------


def test_sweep_archives_the_killed_and_the_rubble_and_keeps_the_rest(tmp_path):
    corpus = tmp_path / "corpus" / "b001-pilot"
    corpus.mkdir(parents=True)

    killed = _spec_dir(corpus, "a-killed", idea_id="b001-pilot-i001", passed=False)
    rubble = _spec_dir(corpus, "b-rubble", idea_id="b001-pilot-i002", passed=None)
    passing = _spec_dir(corpus, "c-passing", idea_id="b001-pilot-i003", passed=True)

    # A dir with a FAILED report but no idea.json is not a spec dir at all.
    decoy = corpus / "a0-not-a-spec"
    decoy.mkdir()
    (decoy / "lint-report.json").write_text(json.dumps({"passed": False}), encoding="utf-8")

    stray = corpus / "b2-notes.txt"
    stray.write_text("not a spec dir\n", encoding="utf-8")

    prior = corpus / KILLED_DIRNAME / "d-earlier-20250101-000000"
    prior.mkdir(parents=True)
    (prior / "keep.txt").write_text("an earlier sweep's work\n", encoding="utf-8")

    # The order the expected return depends on — asserted on the FIXTURE, so a
    # surprise here reads as a fixture fault, not a contract failure.
    assert [p.name for p in sorted(corpus.iterdir())] == [
        ".killed", "a-killed", "a0-not-a-spec", "b-rubble", "b2-notes.txt", "c-passing",
    ]

    taken_before = datetime.now(UTC)
    moved = sweep_killed_specs(corpus)

    # exactly the two, in iteration order
    assert len(moved) == 2, f"expected the killed dir and the rubble, got {moved}"
    assert moved[0].name.startswith("a-killed-"), f"first destination is {moved[0].name}"
    assert moved[1].name.startswith("b-rubble-"), f"second destination is {moved[1].name}"
    for dest, original in zip(moved, ("a-killed", "b-rubble"), strict=True):
        assert dest.is_dir(), f"{dest} is not on disk"
        assert dest.parent == corpus / KILLED_DIRNAME
        _stamp_is_utc_now(_archived_suffix(dest, original), taken_before)

    # the corpus the next attempt will discover against
    assert {p.name for p in corpus.iterdir()} == {".killed", "a0-not-a-spec", "b2-notes.txt",
                                                  "c-passing"}
    assert not killed.exists(), "the lint-killed dir must be gone from the corpus"
    assert not rubble.exists(), "the report-less rubble must be gone from the corpus"

    # what was kept was kept INTACT
    assert passing.is_dir()
    kept = json.loads((passing / "lint-report.json").read_text(encoding="utf-8"))
    assert kept["passed"] is True
    assert (passing / "spec.yaml").read_text(encoding="utf-8") == "game:\n  slug: c-passing\n"
    assert (passing / "idea.json").is_file()
    assert stray.read_text(encoding="utf-8") == "not a spec dir\n", "a stray FILE is not swept"
    assert (decoy / "lint-report.json").is_file(), "a dir without idea.json is not a spec dir"
    assert (prior / "keep.txt").read_text(encoding="utf-8") == "an earlier sweep's work\n", (
        f"{KILLED_DIRNAME}/ is skipped, so an earlier sweep's archives survive"
    )

    # what moved, moved whole
    assert json.loads((moved[0] / "idea.json").read_text(encoding="utf-8"))["id"] == (
        "b001-pilot-i001"
    )
    assert json.loads((moved[0] / "lint-report.json").read_text(encoding="utf-8"))["passed"] is False
    assert (moved[1] / "idea.json").is_file()
    assert not (moved[1] / "lint-report.json").exists(), "the rubble never had a report"
    archived = {p.name for p in (corpus / KILLED_DIRNAME).iterdir()}
    assert archived >= {prior.name, moved[0].name, moved[1].name}, (
        f"{KILLED_DIRNAME}/ must hold the earlier archive and both new ones, found {archived}"
    )


def test_sweep_keeps_every_passing_dir_and_returns_empty(tmp_path):
    """The sweep is not a blunt cleaner: a corpus of green specs is untouched."""
    corpus = tmp_path / "corpus" / "b001-pilot"
    corpus.mkdir(parents=True)
    specs = [
        _spec_dir(corpus, name, idea_id=f"b001-pilot-i00{n}", passed=True)
        for n, name in enumerate(("one-spec", "two-spec"), start=1)
    ]

    moved = sweep_killed_specs(corpus)
    assert moved == [], f"nothing was lint-killed, so nothing may be archived; got {moved}"

    for spec in specs:
        assert spec.is_dir(), f"{spec.name} was swept out of a corpus with no kills in it"
        assert (spec / "idea.json").is_file(), f"{spec.name} lost its idea.json"
        report = json.loads((spec / "lint-report.json").read_text(encoding="utf-8"))
        assert report["passed"] is True, f"{spec.name}'s report was rewritten"


# --------------------------------------------------------------------------
# 4: the interplay with slot discovery — the bug R2 actually hit
# --------------------------------------------------------------------------


def test_discovery_raises_on_a_killed_twin_and_resolves_after_the_sweep(tmp_path):
    corpus = tmp_path / "corpus" / "b001-pilot"
    corpus.mkdir(parents=True)
    idea_path = _idea_file(tmp_path, "b001-pilot-i001")
    _spec_dir(corpus, "fogbound-switchyard", idea_id="b001-pilot-i001", passed=False)
    live = _spec_dir(corpus, "misty-switchyard", idea_id="b001-pilot-i001", passed=True)

    # BEFORE: two dirs claim the idea — the crash the hotfix exists to stop.
    with pytest.raises(LedgerError) as excinfo:
        _discover_spec_dir(corpus, idea_path)
    assert str(excinfo.value).endswith(LEDGER_TAIL), (
        f"the discovery message tail is unchanged; got {str(excinfo.value)!r}"
    )

    moved = sweep_killed_specs(corpus)
    assert len(moved) == 1, f"only the lint-killed dir is swept, got {moved}"
    assert moved[0].name.startswith("fogbound-switchyard-")

    # AFTER: one dir claims the idea, and it is the live one.
    assert _discover_spec_dir(corpus, idea_path) == live


def test_discovery_still_raises_for_two_live_dirs(tmp_path):
    """The sweep resolves lint kills, not ambiguity. Two GREEN dirs claiming
    one idea is still a ledger fault, with the same message."""
    corpus = tmp_path / "corpus" / "b001-pilot"
    corpus.mkdir(parents=True)
    idea_path = _idea_file(tmp_path, "b001-pilot-i001")
    _spec_dir(corpus, "fogbound-switchyard", idea_id="b001-pilot-i001", passed=True)
    _spec_dir(corpus, "misty-switchyard", idea_id="b001-pilot-i001", passed=True)

    assert sweep_killed_specs(corpus) == [], "a passing dir is never swept"

    with pytest.raises(LedgerError) as excinfo:
        _discover_spec_dir(corpus, idea_path)
    message = str(excinfo.value)
    assert message.endswith(LEDGER_TAIL), f"unchanged message tail expected; got {message!r}"
    assert "b001-pilot-i001" in message, "the message still names the idea it refuses"


# --------------------------------------------------------------------------
# 5: the neg2 notation note
# --------------------------------------------------------------------------


def test_neg2_note_shows_the_single_key_shape_and_kills_the_two_key_one():
    note = NEG2_NOTATION_NOTE
    assert isinstance(note, str) and note.strip(), "NEG2_NOTATION_NOTE must be non-empty text"
    assert "single-key" in note, "the note must use the words 'single-key' literally"

    listed = [m.group(0) for m in LISTED_BRACE_RE.finditer(note)]
    good = [block for block in listed if _single_key(BRACE_RE.search(block).group(0))]
    assert good, (
        "the note needs a CORRECT example of the shape [{<class>: \"<mask text>\"}] — "
        f"the bracketed mappings found were {listed}"
    )
    for block in good:
        inner = BRACE_RE.search(block).group(0)
        key = inner[1:].split(":", 1)[0].strip()
        assert key != "sprite-class", (
            f"the correct example's single key is {key!r} — writing `{{sprite-class: mask}}` "
            "as the good example restates the ambiguity the note exists to kill"
        )

    wrong = [
        mapping
        for mapping in BRACE_RE.findall(note)
        if "sprite-class" in mapping and "mask" in mapping and SECOND_KEY_RE.search(mapping)
    ]
    assert wrong, (
        "the note must SHOW the wrong two-key shape, with the literal keys "
        f"`sprite-class` and `mask`; mappings found were {BRACE_RE.findall(note)}"
    )

    flat = _flat(note)
    assert re.search(r"(?i)kill", flat), "the wrong shape must be labelled a kill"
    for mapping in wrong:
        assert _near(flat, _flat(mapping), "kill"), (
            f"the two-key example {mapping!r} is not labelled as a kill anywhere near it"
        )


def test_writer_prompt_carries_the_neg2_note_after_the_schema_header():
    prompt = build_writer_prompt(_cfg(), MINIMAL_IDEA)

    assert SCHEMA_HEADER in prompt, "the schema section header is the anchor; it must be present"
    assert NEG2_NOTATION_NOTE in prompt, (
        "the prompt must carry NEG2_NOTATION_NOTE VERBATIM — a paraphrase in the prompt "
        "and a constant nobody reads is two sources of truth"
    )
    assert prompt.index(NEG2_NOTATION_NOTE) > prompt.index(SCHEMA_HEADER), (
        "the note belongs AFTER the schema section header — it corrects how the schema's "
        "`neg2_readers` line is read, so it cannot precede it"
    )
