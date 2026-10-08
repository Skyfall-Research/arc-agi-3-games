"""Pins for the b003 visual payload — written BLIND from the frozen contract.

Written from ``b003-va-tests-contract.md`` ALONE.  ``gen/visual_canon.py`` was
never read while this file was written, nor was any diff of
``gen/canon_docs.py`` / ``gen/s2_implement.py``; the implementation may not
have existed yet.  Everything below therefore pins the CONTRACT, not the code:
a failure here means either the implementation has not landed, or it landed
somewhere other than where the contract froze it.

House style (``test_b002_promptsync.py``): every canon phrase asserted below is
READ OUT OF THE CANON FILES at test time and compared against what the code
produced — canon is never retyped into this file.  What *is* retyped is the
contract's own frozen surface (section head lines, the three knob-echo
templates, the registry, the six frozen number groups), because the contract —
not canon — is the thing those pins exist to hold still.

What the change is for: the implementer prompt has been carrying render advice
with no canonical grounding, while the signed affordance language (GEN
``design/objects/affordance-language.md``) already fixes the visual grammar in
ten numbered sections.  The b003 change quotes six of those sections verbatim
into the payload, adds a distilled craft note and a "teaching by showing"
bestiary tour, and grounds the render targets in the measured official corpus
instead of in invented numbers.  The quarantine pin (group 7) is the sharp
edge: the vendored re-arc-3 prompt the craft note is distilled FROM carries a
``6x`` budget rule that would silently overrule spec-v0.3's own budget
contract, so that rule must never cross into the distillation.

Groups 1-10 below are the contract's ten pins, in its order.

Two contract ambiguities were resolved here; both are called out at the pin:

* Pin 9's recipe says ``native_64_count`` is the count of ``tile_scale == 1``
  rows, but the frozen value is 13 and that recipe yields 16 (``tile_scale``
  is ``64 // board_w``, so 45- and 39-wide boards and one 64x44 board also
  floor to 1).  The contract says the NUMBERS are frozen, and the key is named
  for a *native 64* board, so the recompute here is "board_w == 64 AND
  board_h == 64", which reproduces 13.  The literal ``tile_scale == 1`` count
  is computed anyway and reported in the failure message.
* Pin 1's "verbatim, trailing blank lines stripped" does not say whether the
  last content line keeps its newline.  Byte-equality is asserted over every
  byte up to that point, and the blank-line stripping is asserted separately
  (no trailing blank line survives); only the count of final newlines is free.

Constraints honoured: no network, no ``OPENROUTER_API_KEY``, GEN is opened
read-only (the doctored-canon trees in group 3 are symlink mirrors under
``tmp_path`` with exactly one real file substituted), and nothing is written
outside ``tmp_path`` — including the real corpus spec, which is copied into
``tmp_path`` before ``build_payload`` is pointed at it.
"""

from __future__ import annotations

import csv
import dataclasses
import re
import shutil
import statistics
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path

import pytest
import yaml

from gen import canon_docs
from gen.config import load_config
from gen.s2_implement import BUDGET_HEADROOM, VISUAL_LEGIBILITY, build_payload

# --- locations --------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = "config/b002-triple.yaml"  # relative, as every sibling suite loads it
VISUAL_CANON_SOURCE = REPO_ROOT / "gen" / "visual_canon.py"

# Canon, relative to the config's `duckwm_docs` root.  Canon is READ-ONLY and is
# never addressed by an absolute path from this repo.
AFFORDANCE_REL = "design/objects/affordance-language.md"
BESTIARY_REL = "design/objects/bestiary"
# The UPSTREAM visual-check prompt VISUAL_CRAFT was distilled from (Tufalabs
# re-arc-3, the same MIT bundle `canon/third-party/re-arc-3/LICENSE-MIT.md`
# covers). It sits beside the vendored pair in the duckWM checkout only — this
# repo does not ship it — so its provenance check runs where duckWM does.
VENDORED_VISUAL_PROMPT_REL = "third-party/re-arc-3/codex_check_visual_prompt.md"

# The real spec the payload pins are built from: shipped, accepted, and it
# carries hazard terms, so it exercises the §3 conditional's positive side.
CORPUS_SPEC = REPO_ROOT / "out" / "corpus" / "b002-triple" / "pump-phase-time-echo"

# The sibling data tree is derived from cfg at runtime (group 9); this is only
# the leaf layout inside it.
FEATURES_GAME_REL = "templates/features-game.csv"
FEATURES_LEVEL_REL = "templates/features-level.csv"
FEATURES_SCHEMA_REL = "features-schema.md"

# --- the contract's frozen surface ------------------------------------------

# The registry, verbatim from the contract.
REGISTRY = {1: "locus", 2: "Goals", 3: "Danger", 5: "Meters", 6: "Refusal", 9: "Palette"}
REGISTRY_NUMBERS = [1, 2, 3, 5, 6, 9]
# Real sections of the canon file that are deliberately NOT in the registry.
OFF_REGISTRY_NUMBERS = [4, 7]

# The frozen section-start lines.  These are CONTRACT strings, not canon, so
# they are retyped here on purpose — holding them still is the point.
GRAMMAR_HEAD = "## The visual affordance grammar (quoted from the signed canon)"
CARD_HEAD = "## Official-corpus visual numbers (render targets, not gates)"
CRAFT_HEAD = "## Visual craft — distilled render rules from the reference pipeline"
TEACHING_HEAD = "## Teaching by showing — the six official idioms"
# The Conventions section pre-dates this contract and the contract does not
# freeze its full head line, only that it comes first; match its stem.
CONVENTIONS_HEAD_RE = re.compile(r"^## Conventions\b", re.MULTILINE)

# The three knob-echo templates, exact, `{v}` = the spec's declared value.
GOAL_ECHO = (
    "This spec declares `goal_legible: {v}` — render the goal with §2's idioms at that "
    "legibility; do not make it harder or easier to read than declared."
)
DANGER_ECHO = (
    "This spec declares `danger_tell: {v}` — §3's catalog entry for that tell is the "
    "render rule."
)
REFUSAL_ECHO = (
    "This spec declares `refusal: {v}` — §6's rule for that mode is binding: charge "
    "silently or signal freely, never both."
)
# The stem that identifies a danger echo whatever value it carries.
DANGER_ECHO_STEM = "This spec declares `danger_tell:"

# Group 2: the §9 sentence is SLICED OUT OF CANON at test time; only its opening
# marker is written here, and the slice runs to the next `**`.
REQUIRED_STEM = "**REQUIRED for generated games"

# Group 7: the quarantine.  `internal grid lines` must survive the distillation;
# the vendored `6x` budget rule must not.
CRAFT_KEEP = "internal grid lines"
CRAFT_FORBIDDEN = ("6x", "overrides any budget")
# Canon-drift anchors in the vendored prompt the craft note is distilled FROM.
VENDORED_ANCHORS = (
    "Do not draw visible internal grid lines",
    "at most one intermediate frame",
)

# Group 8: the six idioms, slug -> the keyword its bestiary card must carry.
TEACHING_IDIOMS = {
    "ft09": "worked",
    "su15": "legend",
    "sc25": "demo",
    "sb26": "wire",
    "lf52": "pulse",
    "ar25": "hint",
}

# Groups 9 + 10: the frozen numbers, verbatim from the contract.  Every one of
# them is independently recomputed from the official CSVs in group 9.
FROZEN_CONSTANTS: dict[str, tuple[float, ...]] = {
    "tile_scale_menu": (1, 2, 3, 4, 5, 8),
    "native_64_count": (13,),
    "l1_colors": (4, 7, 11),
    "board_colors_median": (4.5, 9.0, 12.5),
    "objects_median": (9.5, 53.5, 219.0),
    "default_fps": (3, 30),
}


# --- helpers ----------------------------------------------------------------


def read_lines(path: Path) -> list[str]:
    """The file's lines, newline terminators kept — the slicer works on these."""
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def slice_canon_section(lines: list[str], number: int) -> tuple[str, str, int]:
    """This suite's OWN independent scan of the canon file.

    Returns ``(text, heading_line, heading_lineno)`` where ``text`` runs from the
    ``## <n>. `` heading line to the line before the next ``^## `` heading, with
    trailing blank lines dropped and the heading kept.  ``heading_lineno`` is
    1-based.  The loader under test must reproduce this without ever being shown
    it.
    """
    prefix = f"## {number}. "
    hits = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    assert len(hits) == 1, (
        f"this suite's own scan of the canon file found {len(hits)} lines starting "
        f"{prefix!r} — the pins below assume exactly one, so canon has moved and the "
        "b003 section registry must be re-adjudicated before these pins mean anything"
    )
    start = hits[0]
    end = next(
        (k for k in range(start + 1, len(lines)) if lines[k].startswith("## ")),
        len(lines),
    )
    body = lines[start:end]
    while body and not body[-1].strip():
        body.pop()
    return "".join(body), lines[start].rstrip("\n"), start + 1


def required_sentence(section_text: str) -> str:
    """The §9 REQUIRED sentence, sliced out of canon: stem through its closing ``**``."""
    start = section_text.index(REQUIRED_STEM)
    end = section_text.index("**", start + len(REQUIRED_STEM)) + 2
    return section_text[start:end]


def locate(haystack: str, needle: str, what: str) -> int:
    """``str.index`` with a failure message that names the missing anchor."""
    index = haystack.find(needle)
    assert index >= 0, (
        f"the built payload carries no {what} — expected the line {needle!r}.  The "
        "b003 ordering pin locates every visual section by its frozen start line, so "
        "either the section is missing or its head line was renegotiated without the "
        "contract being reopened"
    )
    return index


def head_line(constant: str) -> str:
    """The first non-blank line of a pre-existing payload constant."""
    for line in constant.splitlines():
        if line.strip():
            return line.rstrip()
    raise AssertionError("a payload constant this suite anchors on is empty")


def constant_numbers(entry: object) -> tuple[float, ...]:
    """Every number carried by an OFFICIAL_VISUAL_CONSTANTS entry, in order.

    The contract allows the values to be "wrapped in a small structure" and only
    freezes the numbers, so plain scalars, tuples, lists, sets, mappings
    (``value``/``values``/``numbers`` preferred) and dataclasses are all unwrapped.
    """
    if isinstance(entry, bool):
        return ()
    if isinstance(entry, (int, float)):
        return (entry,)
    if isinstance(entry, (str, bytes)):
        return ()
    if dataclasses.is_dataclass(entry) and not isinstance(entry, type):
        entry = dataclasses.asdict(entry)
    if isinstance(entry, Mapping):
        for key in ("value", "values", "numbers", "number"):
            if key in entry:
                return constant_numbers(entry[key])
        out: list[float] = []
        for value in entry.values():
            out.extend(constant_numbers(value))
        return tuple(out)
    if isinstance(entry, (Sequence, set, frozenset)):
        out = []
        for value in entry:
            out.extend(constant_numbers(value))
        return tuple(out)
    for attr in ("value", "values", "numbers"):
        if hasattr(entry, attr):
            return constant_numbers(getattr(entry, attr))
    return ()


def number_forms(number: float) -> tuple[str, ...]:
    """The renderings of a frozen number a card is allowed to use."""
    if isinstance(number, float) and number.is_integer():
        return (f"{number:g}", f"{number:.1f}")
    if isinstance(number, float):
        return (f"{number:g}",)
    return (str(number),)


def carries_number(text: str, number: float) -> bool:
    """True if ``text`` shows ``number`` as a standalone token in any allowed form.

    The boundaries stop ``3`` from matching inside ``30`` or ``9`` inside ``9.0``
    without also rejecting a number that ends a sentence (``... 3 to 30.``), so a
    following ``.`` only disqualifies the match when a digit follows it.
    """
    for form in number_forms(number):
        if re.search(r"(?<![\d.])" + re.escape(form) + r"(?!\.?\d)", text):
            return True
    return False


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def column(rows: list[dict[str, str]], name: str) -> list[float]:
    """Every non-blank value of ``name``, as floats."""
    return [float(row[name]) for row in rows if (row.get(name) or "").strip()]


def documented_columns(schema_text: str, table: str) -> set[str]:
    """The column names ``features-schema.md`` documents under one ``## <table>``.

    The contract says to read the column names from the schema FIRST and use what
    it documents, so the schema — not this file — is the authority that a column
    exists and which CSV it belongs to.
    """
    section = None
    for block in schema_text.split("\n## "):
        head = block.splitlines()[0].strip() if block.strip() else ""
        if head == table or block.startswith(f"# {table}"):
            section = block
            break
    assert section is not None, (
        f"features-schema.md documents no '## {table}' table — the b003 constants "
        "recompute reads its column names from that schema, so the recompute cannot "
        "be grounded until the schema is fixed"
    )
    return set(re.findall(r"^\|\s*`([^`]+)`\s*\|", section, re.MULTILINE))


def mirror_canon_with_doctored_affordance(source: Path, dest: Path, doctored: str) -> Path:
    """A canon root under tmp_path: symlinks everywhere, one real doctored file.

    GEN stays read-only — nothing is copied out of it and nothing is written into
    it.  Only ``design/objects/affordance-language.md`` becomes a real file.
    """
    parts = AFFORDANCE_REL.split("/")
    dest.mkdir(parents=True, exist_ok=True)
    src_dir, dst_dir = source, dest
    for part in parts[:-1]:
        for child in src_dir.iterdir():
            if child.name != part:
                (dst_dir / child.name).symlink_to(child)
        src_dir, dst_dir = src_dir / part, dst_dir / part
        dst_dir.mkdir()
    for child in src_dir.iterdir():
        if child.name != parts[-1]:
            (dst_dir / child.name).symlink_to(child)
    (dst_dir / parts[-1]).write_text(doctored, encoding="utf-8")
    return dest


def spec_copy(source: Path, dest: Path, mutate=None) -> Path:
    """``spec.yaml`` + ``spec.md`` copied into tmp_path, optionally mutated.

    Nothing is ever built against the shipped corpus directory itself: the
    contract forbids writing outside tmp_path and ``build_payload``'s CLI writes
    ``payload.md`` beside the spec.
    """
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / "spec.md", dest / "spec.md")
    spec = yaml.safe_load((source / "spec.yaml").read_text(encoding="utf-8"))
    if mutate is not None:
        spec = mutate(spec)
    (dest / "spec.yaml").write_text(
        yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=4096),
        encoding="utf-8",
    )
    return dest


def strip_hazards(spec: dict, *, danger_tell: str) -> dict:
    """Remove every ``hazard.``/``loss.`` term and set the tell — the §3 negative side."""
    game = spec["game"]
    hazardish = ("hazard.", "loss.")
    game["terms"] = [t for t in game["terms"] if not str(t).startswith(hazardish)]
    game.setdefault("knobs", {})["danger_tell"] = danger_tell
    for level in game.get("levels") or []:
        introduced = level.get("terms_introduced")
        if isinstance(introduced, list):
            level["terms_introduced"] = [
                t for t in introduced if not str(t).startswith(hazardish)
            ]
    if danger_tell == "none" and isinstance(game.get("palette"), dict):
        game["palette"]["danger"] = None  # a tell-less game declares no danger hue
    return spec


# --- fixtures ---------------------------------------------------------------


@pytest.fixture(scope="session")
def cfg() -> dict:
    """The b002 config — the batch these pins' real spec was produced under."""
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="session")
def docs_root(cfg: dict) -> Path:
    root = Path(cfg["duckwm_docs"]).resolve()
    assert root.is_dir(), (
        f"the config's duckwm_docs resolves to {root}, which is not a directory — run "
        "pytest from the repo root (every sibling suite loads the config by its "
        "relative path)"
    )
    return root


@pytest.fixture(scope="session")
def affordance_path(docs_root: Path) -> Path:
    path = docs_root / AFFORDANCE_REL
    assert path.is_file(), f"the signed affordance language is missing at {path}"
    return path


@pytest.fixture(scope="session")
def affordance_lines(affordance_path: Path) -> list[str]:
    return read_lines(affordance_path)


@pytest.fixture(scope="session")
def load_sections():
    """``gen.canon_docs.load_affordance_sections`` — the contract's new loader."""
    loader = getattr(canon_docs, "load_affordance_sections", None)
    if loader is None:
        pytest.fail(
            "gen.canon_docs exposes no load_affordance_sections(cfg, numbers) — the "
            "b003 contract's canon loader has not landed; every grammar pin below "
            "depends on it"
        )
    return loader


@pytest.fixture(scope="session")
def sections(load_sections, cfg: dict) -> dict:
    """The six registry sections, loaded against the real canon."""
    return load_sections(cfg, REGISTRY_NUMBERS)


@pytest.fixture(scope="session")
def visual_canon():
    """The ``gen.visual_canon`` module — imported, never read, while this was written."""
    try:
        import gen.visual_canon as module
    except ImportError as exc:  # pragma: no cover - the pre-implementation state
        pytest.fail(
            f"gen.visual_canon does not import ({exc}) — the b003 contract freezes it "
            "as the home of the visual constants, the craft note, the teaching tour "
            "and the corpus card"
        )
    return module


@pytest.fixture(scope="session")
def constants(visual_canon) -> Mapping:
    entry = getattr(visual_canon, "OFFICIAL_VISUAL_CONSTANTS", None)
    if entry is None:
        pytest.fail("gen.visual_canon exposes no OFFICIAL_VISUAL_CONSTANTS mapping")
    assert isinstance(entry, Mapping), (
        f"OFFICIAL_VISUAL_CONSTANTS is a {type(entry).__name__}, not a mapping — the "
        "contract freezes it as a keyed carrier so the card and the drift guard can "
        "both address the same numbers by name"
    )
    return entry


@pytest.fixture(scope="session")
def pump_spec_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The shipped hazard-carrying spec, copied into tmp_path (never built in place)."""
    assert CORPUS_SPEC.is_dir(), f"the shipped b002 spec is missing at {CORPUS_SPEC}"
    return spec_copy(CORPUS_SPEC, tmp_path_factory.mktemp("b003-pump"))


@pytest.fixture(scope="session")
def pump_knobs(pump_spec_dir: Path) -> dict:
    """The spec's DECLARED knob values, read off the file at test time."""
    spec = yaml.safe_load((pump_spec_dir / "spec.yaml").read_text(encoding="utf-8"))
    return spec["game"]["knobs"]


@pytest.fixture(scope="session")
def pump_build(pump_spec_dir: Path, cfg: dict) -> tuple[str, object]:
    return build_payload(pump_spec_dir, cfg)


@pytest.fixture(scope="session")
def payload(pump_build: tuple[str, object]) -> str:
    return pump_build[0]


@pytest.fixture(scope="session")
def report(pump_build: tuple[str, object]) -> object:
    return pump_build[1]


def visual_sections_of(report_obj: object) -> list[int]:
    value = getattr(report_obj, "visual_sections", None)
    if value is None:
        pytest.fail(
            "the PayloadReport build_payload returns carries no visual_sections — the "
            "b003 contract freezes it as the list of grammar sections the payload "
            "actually included"
        )
    return list(value)


# --- 1. the loader reproduces canon verbatim --------------------------------


def test_the_section_registry_is_the_contracts_six_keywords():
    registry = getattr(canon_docs, "AFFORDANCE_SECTION_KEYWORDS", None)
    if registry is None:
        pytest.fail("gen.canon_docs exposes no AFFORDANCE_SECTION_KEYWORDS registry")
    assert dict(registry) == REGISTRY, (
        "the affordance section registry is not the contract's six sections.  The "
        "keyword is the guard that a section number still points at the section it "
        "pointed at when the grammar was adjudicated, so a change here silently "
        "re-aims every quoted section in the implementer prompt"
    )


@pytest.mark.parametrize("number", REGISTRY_NUMBERS)
def test_each_loaded_section_is_the_canon_file_byte_for_byte(
    number: int, sections: dict, affordance_lines: list[str], affordance_path: Path
):
    assert number in sections, (
        f"section {number} was requested but is absent from the loader's result — the "
        f"registry promises {REGISTRY[number]!r}"
    )
    section = sections[number]
    expected_text, heading, lineno = slice_canon_section(affordance_lines, number)

    assert getattr(section, "number", None) == number
    assert section.text.rstrip("\n") == expected_text.rstrip("\n"), (
        f"section {number}'s text is not the canon file's bytes.  It must run from "
        f"{heading!r} to the line before the next '## ' heading, verbatim, heading "
        "included — a re-wrapped or re-indented quote is not a quote"
    )
    assert not section.text.endswith("\n\n"), (
        f"section {number}'s text keeps a trailing blank line; the contract strips them"
    )
    assert section.source == f"{affordance_path.name}:L{lineno}", (
        f"section {number} cites {section.source!r}; the heading it was sliced from is "
        f"line {lineno} of {affordance_path.name}"
    )
    assert REGISTRY[number] in section.title, (
        f"section {number}'s title {section.title!r} does not carry the registry "
        f"keyword {REGISTRY[number]!r}"
    )
    assert section.title in heading, (
        f"section {number}'s title {section.title!r} is not part of its canon heading "
        f"{heading!r}"
    )


def test_the_loader_returns_affordance_section_records(sections: dict):
    record_cls = getattr(canon_docs, "AffordanceSection", None)
    if record_cls is None:
        pytest.fail("gen.canon_docs exposes no AffordanceSection record type")
    for number, section in sections.items():
        assert isinstance(section, record_cls), (
            f"section {number} came back as a {type(section).__name__}, not an "
            "AffordanceSection"
        )
    fields = {"number", "title", "text", "source"}
    for number, section in sections.items():
        missing = {name for name in fields if not hasattr(section, name)}
        assert not missing, f"section {number}'s record is missing {sorted(missing)}"


def test_the_loader_is_deterministic(load_sections, cfg: dict, sections: dict):
    again = load_sections(cfg, REGISTRY_NUMBERS)
    assert {n: s.text for n, s in again.items()} == {n: s.text for n, s in sections.items()}
    assert {n: s.source for n, s in again.items()} == {n: s.source for n, s in sections.items()}


# --- 2. the §9 REQUIRED sentence survives into the prompt -------------------


@pytest.fixture(scope="session")
def required_rule(affordance_lines: list[str]) -> str:
    """§9's REQUIRED palette rule, sliced out of the canon file at test time."""
    text, _heading, _lineno = slice_canon_section(affordance_lines, 9)
    rule = required_sentence(text)
    assert rule.endswith("**") and len(rule) > len(REQUIRED_STEM) + 2, (
        f"the §9 REQUIRED sentence sliced out of canon looks wrong ({rule!r}) — this "
        "suite's slice, not the code, is what has drifted"
    )
    return rule


def test_the_palette_required_rule_is_quoted_in_section_nine(required_rule: str, sections: dict):
    assert required_rule in sections[9].text, (
        "§9's REQUIRED palette rule is not inside the loaded section 9.  That rule "
        "(reserve 0 for selection, meter indices off the board, unique on-board "
        "indices for you/goal/danger) is the whole reason §9 is quoted at all"
    )


def test_the_palette_required_rule_reaches_the_built_payload(required_rule: str, payload: str):
    assert required_rule in payload, (
        "the built implementer payload does not carry §9's REQUIRED palette rule "
        "verbatim — the grammar section is supposed to quote the signed canon, not "
        "paraphrase it"
    )


# --- 3. the loader fails loudly on doctored canon ---------------------------


@pytest.fixture(scope="session")
def canon_missing_heading(
    docs_root: Path, affordance_lines: list[str], tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """A canon root whose §5 heading line has been deleted."""
    lines = list(affordance_lines)
    index = next(i for i, line in enumerate(lines) if line.startswith("## 5. "))
    del lines[index]
    root = tmp_path_factory.mktemp("b003-canon-missing") / "canon"
    return mirror_canon_with_doctored_affordance(docs_root, root, "".join(lines))


@pytest.fixture(scope="session")
def canon_duplicate_heading(
    docs_root: Path, affordance_lines: list[str], tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """A canon root where §2's heading line appears a second time."""
    lines = list(affordance_lines)
    heading = next(line for line in lines if line.startswith("## 2. "))
    lines.extend(["\n", heading, "\nA second §2 heading, planted by the b003 pins.\n"])
    root = tmp_path_factory.mktemp("b003-canon-duplicate") / "canon"
    return mirror_canon_with_doctored_affordance(docs_root, root, "".join(lines))


def doctored_cfg(cfg: dict, root: Path) -> dict:
    doctored = dict(cfg)
    doctored["duckwm_docs"] = str(root)
    return doctored


def test_a_missing_heading_is_a_valueerror(load_sections, cfg: dict, canon_missing_heading: Path):
    bad = doctored_cfg(cfg, canon_missing_heading)
    with pytest.raises(ValueError):
        load_sections(bad, [5])
    with pytest.raises(ValueError):
        load_sections(bad, REGISTRY_NUMBERS)


def test_a_duplicated_heading_is_a_valueerror(
    load_sections, cfg: dict, canon_duplicate_heading: Path
):
    bad = doctored_cfg(cfg, canon_duplicate_heading)
    with pytest.raises(ValueError):
        load_sections(bad, [2])
    with pytest.raises(ValueError):
        load_sections(bad, REGISTRY_NUMBERS)


# LEAD-AUTHORED ADDITION (not part of the blind suite): the contract's fourth
# failure mode — a heading that keeps its number but loses its registered
# keyword (a rename-in-place) — was absent from the blind pin list, so the
# loader's keyword guard had no pin. Same doctoring machinery as the two above.
def test_a_renamed_heading_is_a_valueerror(
    load_sections,
    cfg: dict,
    docs_root: Path,
    affordance_lines: list[str],
    tmp_path_factory: pytest.TempPathFactory,
):
    lines = list(affordance_lines)
    index = next(i for i, line in enumerate(lines) if line.startswith("## 9. "))
    lines[index] = "## 9. Renamed section\n"
    root = tmp_path_factory.mktemp("b003-canon-renamed") / "canon"
    mirror_canon_with_doctored_affordance(docs_root, root, "".join(lines))
    with pytest.raises(ValueError):
        load_sections(doctored_cfg(cfg, root), [9])


@pytest.mark.parametrize("number", OFF_REGISTRY_NUMBERS)
def test_a_real_section_outside_the_registry_is_a_valueerror(
    number: int, load_sections, cfg: dict, affordance_lines: list[str]
):
    # These sections really do exist in canon — the point is that existing is not
    # the same as being adjudicated into the grammar.
    assert any(line.startswith(f"## {number}. ") for line in affordance_lines), (
        f"§{number} is no longer a real canon section, so it no longer tests the "
        "registry's closedness"
    )
    with pytest.raises(ValueError):
        load_sections(cfg, [number])


# --- 4. payload assembly on a real, hazard-carrying spec --------------------


def test_the_visual_sections_land_in_the_frozen_order(payload: str):
    conventions = CONVENTIONS_HEAD_RE.search(payload)
    assert conventions is not None, (
        "the built payload has no '## Conventions' section — the b003 order is "
        "anchored on it (Conventions first, then the visual block)"
    )
    order = [
        ("the Conventions section", conventions.start()),
        ("the visual grammar section", locate(payload, GRAMMAR_HEAD, "visual grammar head")),
        ("the corpus numbers card", locate(payload, CARD_HEAD, "corpus numbers card head")),
        ("VISUAL_CRAFT", locate(payload, CRAFT_HEAD, "visual craft head")),
        (
            "VISUAL_LEGIBILITY",
            locate(payload, head_line(VISUAL_LEGIBILITY), "visual legibility head"),
        ),
        ("TEACHING_BY_SHOWING", locate(payload, TEACHING_HEAD, "teaching-by-showing head")),
        ("BUDGET_HEADROOM", locate(payload, head_line(BUDGET_HEADROOM), "budget headroom head")),
    ]
    for (first_name, first_at), (second_name, second_at) in pairwise(order):
        assert first_at < second_at, (
            f"{second_name} is placed before {first_name} in the implementer payload.  "
            "The frozen order is Conventions, grammar, corpus card, VISUAL_CRAFT, "
            "VISUAL_LEGIBILITY, TEACHING_BY_SHOWING, BUDGET_HEADROOM: canon first, "
            "then the measured targets, then the distilled craft, then the budget"
        )


def test_the_hazard_spec_includes_section_three(payload: str, affordance_lines: list[str]):
    _text, heading, _lineno = slice_canon_section(affordance_lines, 3)
    assert heading in payload, (
        f"the payload for a spec carrying hazard.* terms does not quote {heading!r}.  "
        "§3 is conditional, and this spec satisfies the condition twice over "
        "(hazard.crush/hazard.timed, and a declared danger_tell)"
    )


def test_the_report_names_the_six_included_sections(report: object):
    assert visual_sections_of(report) == REGISTRY_NUMBERS, (
        "PayloadReport.visual_sections must be exactly the grammar sections the "
        "payload included; this spec carries hazard terms, so §3 is in"
    )


def test_the_grammar_helper_agrees_with_the_payload(visual_canon, cfg: dict, pump_spec_dir: Path):
    helper = getattr(visual_canon, "visual_grammar_section", None)
    if helper is None:
        pytest.fail("gen.visual_canon exposes no visual_grammar_section(cfg, spec_yaml_path)")
    text, numbers = helper(cfg, pump_spec_dir / "spec.yaml")
    assert text.startswith(GRAMMAR_HEAD), (
        f"the grammar section must start with {GRAMMAR_HEAD!r}; it starts "
        f"{text.splitlines()[0]!r}"
    )
    assert list(numbers) == REGISTRY_NUMBERS


@pytest.mark.parametrize(
    ("knob", "template"),
    [("goal_legible", GOAL_ECHO), ("danger_tell", DANGER_ECHO), ("refusal", REFUSAL_ECHO)],
)
def test_each_knob_echo_is_filled_with_the_specs_declared_value(
    knob: str, template: str, payload: str, pump_knobs: dict
):
    expected = template.format(v=pump_knobs[knob])
    assert expected in payload, (
        f"the payload does not carry the {knob} echo line for this spec's declared "
        f"value {pump_knobs[knob]!r}.  Expected verbatim:\n  {expected}\nThe echo is "
        "what ties the spec's declared knob to the canon section that rules on it; "
        "without it the implementer reads the grammar with no idea which row applies"
    )


# --- 5. the §3 conditional, both arms of the negative side ------------------


@pytest.fixture(scope="session")
def hazardless_build(
    cfg: dict, tmp_path_factory: pytest.TempPathFactory
) -> tuple[str, object]:
    """The same real spec with every hazard term gone and ``danger_tell: none``."""
    spec_dir = spec_copy(
        CORPUS_SPEC,
        tmp_path_factory.mktemp("b003-hazardless"),
        mutate=lambda spec: strip_hazards(spec, danger_tell="none"),
    )
    return build_payload(spec_dir, cfg)


def test_a_hazardless_spec_drops_section_three(
    hazardless_build: tuple[str, object], affordance_lines: list[str]
):
    text = hazardless_build[0]
    _section, heading, _lineno = slice_canon_section(affordance_lines, 3)
    assert heading not in text, (
        f"a spec with no hazard.*/loss.* term and 'danger_tell: none' still gets "
        f"{heading!r} quoted at it.  §3 is conditional precisely so a hazardless game "
        "is not taught to render a danger it does not have"
    )


def test_a_hazardless_spec_reports_five_sections(hazardless_build: tuple[str, object]):
    assert visual_sections_of(hazardless_build[1]) == [1, 2, 5, 6, 9]


def test_a_hazardless_spec_carries_no_danger_echo(hazardless_build: tuple[str, object]):
    text = hazardless_build[0]
    assert DANGER_ECHO_STEM not in text, (
        "the danger_tell echo line is emitted for a spec that declares no danger — the "
        "contract makes that line conditional on §3 being included"
    )


def test_a_hazardless_spec_keeps_the_other_two_echoes(
    hazardless_build: tuple[str, object], pump_knobs: dict
):
    # goal_legible and refusal are untouched by the hazard strip, so the spec's own
    # declared values still apply — only the danger echo is conditional.
    text, _report = hazardless_build
    assert GOAL_ECHO.format(v=pump_knobs["goal_legible"]) in text
    assert REFUSAL_ECHO.format(v=pump_knobs["refusal"]) in text


def test_a_declared_tell_alone_pulls_section_three_back_in(
    cfg: dict, tmp_path_factory: pytest.TempPathFactory, affordance_lines: list[str]
):
    """The OR's second arm: no hazard term, but a tell is declared."""
    spec_dir = spec_copy(
        CORPUS_SPEC,
        tmp_path_factory.mktemp("b003-tell-only"),
        mutate=lambda spec: strip_hazards(spec, danger_tell="unique-hue"),
    )
    text, built = build_payload(spec_dir, cfg)
    _section, heading, _lineno = slice_canon_section(affordance_lines, 3)
    assert heading in text, (
        f"a spec with no hazard.* term but 'danger_tell: unique-hue' does not get "
        f"{heading!r}.  The contract's condition is an OR: a declared tell is a "
        "declared danger, whatever the term list says"
    )
    assert visual_sections_of(built) == REGISTRY_NUMBERS
    assert DANGER_ECHO.format(v="unique-hue") in text


# --- 6. determinism ---------------------------------------------------------


def test_two_builds_of_one_spec_are_byte_identical(pump_spec_dir: Path, cfg: dict):
    first, first_report = build_payload(pump_spec_dir, cfg)
    second, second_report = build_payload(pump_spec_dir, cfg)
    assert first == second, (
        "two builds of the same spec dir differ.  The visual block quotes canon, "
        "renders frozen constants and walks a fixed section registry — every one of "
        "those is ordered, so any difference is an unordered set or a clock leaking "
        "into the implementer prompt"
    )
    assert visual_sections_of(first_report) == visual_sections_of(second_report)


# --- 7. the craft note's quarantine ----------------------------------------


@pytest.fixture(scope="session")
def visual_craft(visual_canon) -> str:
    text = getattr(visual_canon, "VISUAL_CRAFT", None)
    if text is None:
        pytest.fail("gen.visual_canon exposes no VISUAL_CRAFT")
    return text


def test_visual_craft_starts_with_its_frozen_head(visual_craft: str):
    assert visual_craft.startswith(CRAFT_HEAD), (
        f"VISUAL_CRAFT must start with {CRAFT_HEAD!r}; it starts "
        f"{visual_craft.splitlines()[0]!r}"
    )


def test_visual_craft_keeps_the_grid_line_rule(visual_craft: str):
    assert CRAFT_KEEP in visual_craft, (
        "the distilled craft note has lost the internal-grid-lines rule, which is the "
        "single most load-bearing render rule in the reference pipeline: logical cells "
        "are implementation structure, not decoration"
    )


@pytest.mark.parametrize("forbidden", CRAFT_FORBIDDEN)
def test_the_vendored_budget_rule_never_enters_the_craft_note(forbidden: str, visual_craft: str):
    assert forbidden not in visual_craft, (
        f"VISUAL_CRAFT carries {forbidden!r}.  The vendored re-arc-3 prompt sets every "
        "level's budget to 6x the verified winning path and declares that it overrides "
        "the spec; spec-v0.3's budget contract (g.median/iqr/floor, the headroom note) "
        "is this pipeline's law.  The craft note is a distillation of the RENDER rules "
        "only — the budget rule must stay quarantined on the vendored side"
    )


def test_the_vendored_prompt_still_says_what_the_distillation_assumed(docs_root: Path):
    vendored = docs_root / VENDORED_VISUAL_PROMPT_REL
    assert vendored.is_file(), (
        f"the vendored reference prompt is gone from {vendored} — VISUAL_CRAFT is "
        "distilled from it, so its provenance can no longer be checked"
    )
    text = vendored.read_text(encoding="utf-8")
    for anchor in VENDORED_ANCHORS:
        assert anchor in text, (
            f"the vendored prompt no longer contains {anchor!r}.  VISUAL_CRAFT was "
            "distilled from the version that did: re-read the vendored file and "
            "re-check the distillation before touching this pin"
        )


# --- 8. the teaching tour cites real bestiary cards -------------------------


def test_teaching_by_showing_starts_with_its_frozen_head(visual_canon):
    text = getattr(visual_canon, "TEACHING_BY_SHOWING", None)
    if text is None:
        pytest.fail("gen.visual_canon exposes no TEACHING_BY_SHOWING")
    assert text.startswith(TEACHING_HEAD), (
        f"TEACHING_BY_SHOWING must start with {TEACHING_HEAD!r}; it starts "
        f"{text.splitlines()[0]!r}"
    )


def test_the_module_source_names_all_six_bestiary_slugs():
    assert VISUAL_CANON_SOURCE.is_file(), (
        f"gen/visual_canon.py does not exist at {VISUAL_CANON_SOURCE} — the b003 "
        "contract freezes it as the module that carries the visual canon"
    )
    source = VISUAL_CANON_SOURCE.read_text(encoding="utf-8")
    missing = sorted(slug for slug in TEACHING_IDIOMS if slug not in source)
    assert not missing, (
        f"gen/visual_canon.py never names {missing}.  Teaching by showing means each "
        "idiom is attributed to the official that demonstrates it; an unattributed "
        "idiom is an invented one"
    )


@pytest.mark.parametrize(("slug", "keyword"), sorted(TEACHING_IDIOMS.items()))
def test_each_cited_official_has_a_bestiary_card_carrying_its_idiom(
    slug: str, keyword: str, docs_root: Path
):
    card = docs_root / BESTIARY_REL / f"{slug}.md"
    assert card.is_file(), (
        f"the teaching tour cites {slug}, but {card} does not exist — the citation has "
        "nothing behind it"
    )
    assert keyword.lower() in card.read_text(encoding="utf-8").lower(), (
        f"{slug}'s bestiary card no longer mentions {keyword!r}, the idiom the b003 "
        f"teaching tour attributes to it.  Either the card was rewritten or {slug} is "
        "the wrong exemplar for that idiom"
    )


# --- 9. the constants are recomputable from the official corpus -------------


@pytest.mark.parametrize("key", sorted(FROZEN_CONSTANTS))
def test_the_frozen_numbers_are_present_and_unchanged(key: str, constants: Mapping):
    assert key in constants, (
        f"OFFICIAL_VISUAL_CONSTANTS carries no {key!r} key — the corpus card and the "
        "drift guard both address the constants by name"
    )
    got = constant_numbers(constants[key])
    want = FROZEN_CONSTANTS[key]
    if key == "tile_scale_menu":
        got, want = tuple(sorted(got)), tuple(sorted(want))
    assert got == pytest.approx(want), (
        f"OFFICIAL_VISUAL_CONSTANTS[{key!r}] carries {got}, not the frozen {want}"
    )


@pytest.fixture(scope="session")
def games_tree(cfg: dict) -> Path:
    """The sibling measured-corpus tree, derived from the canon root."""
    return Path(cfg["duckwm_docs"]).resolve().parent / "arc-agi-3-games"


@pytest.fixture(scope="session")
def features(games_tree: Path) -> dict:
    """The official feature CSVs, with their columns confirmed against the schema."""
    game_csv = games_tree / FEATURES_GAME_REL
    if not game_csv.is_file():
        pytest.skip(
            f"the measured official-corpus features are not on this machine: "
            f"{game_csv} is missing, so the b003 constants CANNOT be re-derived and "
            "the drift guard is not running.  The sibling tree is derived from the "
            f"config's duckwm_docs as {games_tree}"
        )
    level_csv = games_tree / FEATURES_LEVEL_REL
    assert level_csv.is_file(), f"features-game.csv is present but {level_csv} is not"

    schema_path = games_tree / FEATURES_SCHEMA_REL
    assert schema_path.is_file(), (
        f"{schema_path} is missing — the contract says to read the column names out of "
        "the schema before recomputing anything, never to guess them"
    )
    schema = schema_path.read_text(encoding="utf-8")
    game_columns = documented_columns(schema, "features-game.csv")
    level_columns = documented_columns(schema, "features-level.csv")

    needed_game = {"tile_scale", "board_w", "board_h", "default_fps", "colors_median",
                   "objects_median"}
    needed_level = {"level", "colors"}
    assert needed_game <= game_columns, (
        f"features-schema.md no longer documents {sorted(needed_game - game_columns)} on "
        "features-game.csv — the b003 constants are derived from those columns"
    )
    assert needed_level <= level_columns, (
        f"features-schema.md no longer documents {sorted(needed_level - level_columns)} "
        "on features-level.csv"
    )

    game_rows = read_rows(game_csv)
    level_rows = read_rows(level_csv)
    assert needed_game <= set(game_rows[0]), "features-game.csv's header lost a column"
    assert needed_level <= set(level_rows[0]), "features-level.csv's header lost a column"
    return {"game": game_rows, "level": level_rows, "tree": games_tree}


def test_the_tile_scale_menu_is_the_corpus_menu(features: dict, constants: Mapping):
    menu = sorted({int(value) for value in column(features["game"], "tile_scale")})
    assert sorted(constant_numbers(constants["tile_scale_menu"])) == pytest.approx(menu), (
        f"the frozen tile-scale menu no longer matches the officials, which use {menu}"
    )


def test_the_native_64_count_is_the_corpus_count(features: dict, constants: Mapping):
    # AMBIGUITY RESOLVED: the contract's recipe says "count of tile_scale == 1
    # rows", but tile_scale is `64 // board_w`, so 45- and 39-wide boards and a
    # 64x44 board floor to 1 too, giving a different number than the frozen 13.
    # The contract freezes the NUMBER and names the key for a *native 64* board,
    # so the recompute is a full 64x64 camera.  The literal recipe's count is
    # computed alongside and reported, so a future reader sees both.
    rows = features["game"]
    native = sum(
        1
        for row in rows
        if (row["board_w"] or "").strip() == "64" and (row["board_h"] or "").strip() == "64"
    )
    tile_scale_ones = sum(1 for value in column(rows, "tile_scale") if value == 1)
    assert constant_numbers(constants["native_64_count"]) == pytest.approx((native,)), (
        f"the frozen native-64 count no longer matches the officials: {native} games "
        f"render on a full 64x64 camera ({tile_scale_ones} rows have tile_scale == 1, "
        "which is the wider 'no upscale' set the contract's recipe line describes)"
    )


def test_the_level_one_colour_span_is_the_corpus_span(features: dict, constants: Mapping):
    values = [
        float(row["colors"])
        for row in features["level"]
        if (row.get("level") or "").strip() == "1" and (row.get("colors") or "").strip()
    ]
    assert values, "features-level.csv has no level-1 rows with a colours count"
    span = (min(values), statistics.median(values), max(values))
    assert constant_numbers(constants["l1_colors"]) == pytest.approx(span), (
        f"the frozen level-1 colour span no longer matches the officials, which span "
        f"{span} (min, median, max) over {len(values)} games"
    )


def test_the_board_colour_median_span_is_the_corpus_span(features: dict, constants: Mapping):
    values = column(features["game"], "colors_median")
    span = (min(values), statistics.median(values), max(values))
    assert constant_numbers(constants["board_colors_median"]) == pytest.approx(span), (
        f"the frozen board-colour span no longer matches the officials: {span}"
    )


def test_the_object_count_span_is_the_corpus_span(features: dict, constants: Mapping):
    values = column(features["game"], "objects_median")
    span = (min(values), statistics.median(values), max(values))
    assert constant_numbers(constants["objects_median"]) == pytest.approx(span), (
        f"the frozen object-count span no longer matches the officials: {span}"
    )


def test_the_fps_range_is_the_corpus_range(features: dict, constants: Mapping):
    values = column(features["game"], "default_fps")
    bounds = (min(values), max(values))
    assert constant_numbers(constants["default_fps"]) == pytest.approx(bounds), (
        f"the frozen fps range no longer matches the officials: {bounds}"
    )


# --- 10. the corpus card renders from the constants -------------------------


@pytest.fixture(scope="session")
def corpus_card(visual_canon) -> str:
    builder = getattr(visual_canon, "corpus_numbers_card", None)
    if builder is None:
        pytest.fail("gen.visual_canon exposes no corpus_numbers_card()")
    return builder()


def test_the_card_starts_with_its_frozen_head(corpus_card: str):
    assert corpus_card.startswith(CARD_HEAD), (
        f"the corpus card must start with {CARD_HEAD!r}; it starts "
        f"{corpus_card.splitlines()[0]!r}.  'render targets, not gates' is the whole "
        "claim of the section — these numbers describe the officials, they do not "
        "gate a generated game"
    )


@pytest.mark.parametrize("key", sorted(FROZEN_CONSTANTS))
def test_every_card_number_comes_from_the_constants(key: str, corpus_card: str, constants: Mapping):
    numbers = constant_numbers(constants[key])
    assert numbers, f"OFFICIAL_VISUAL_CONSTANTS[{key!r}] carries no numbers to render"
    missing = [number for number in numbers if not carries_number(corpus_card, number)]
    assert not missing, (
        f"the corpus card does not show {missing} from OFFICIAL_VISUAL_CONSTANTS"
        f"[{key!r}].  The card must RENDER the constants — a number typed into the "
        "card's prose is a number that can drift away from the corpus it claims to "
        "describe without any test noticing"
    )


def test_the_card_renders_the_tile_scale_menu_as_a_list(corpus_card: str, constants: Mapping):
    menu = sorted(int(n) for n in constant_numbers(constants["tile_scale_menu"]))
    spaced = ", ".join(str(n) for n in menu)
    tight = ",".join(str(n) for n in menu)
    candidates = [f"{{{spaced}}}", f"({spaced})", f"[{spaced}]", spaced, tight]
    assert any(candidate in corpus_card for candidate in candidates), (
        f"the corpus card never shows the tile-scale menu as a list built from "
        f"OFFICIAL_VISUAL_CONSTANTS['tile_scale_menu'] — tried {candidates}"
    )
