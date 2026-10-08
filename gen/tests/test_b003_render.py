"""Blind pins for the §11 render fields — `game.render.cell_px` and
`game.palette.background` (contract V-B, test-writer half).

Written from the frozen V-B contract ALONE. No render-related diff of
`gen/s1_spec.py` was read — not the module, not a patch, not an implementer
report — so every expectation below is the contract's own words turned into an
assertion, and a pin that fails is a disagreement between the contract and the
landed code rather than a test fitted to it. What WAS read: the landed
`gen/tiers.py` and `gen/visual_canon.py`, `s1_spec`'s PRE-EXISTING surface
(`lint_spec`, `LintReport`, `build_writer_prompt`, `KILL_RULES`, `GAME_FIELDS`,
the spec fixtures) as it stands at HEAD, the shipped corpus under `out/`, and
the sibling suites' house style.

The frozen surface, as this file reads it:

  * `game.render: {cell_px: int}` and `game.palette.background: int 0-15` are
    OPTIONAL. Absent, they produce zero new findings anywhere — the
    back-compat bar, pinned against the four shipped specs and the hand-written
    §11 fixture.
  * Findings ride EXISTING ids, because `KILL_RULES` is closed: malformed
    render / cell_px / background is `schema`; a canvas overflow
    (`cell_px * grid_w > 64` or `* grid_h > 64`) is `contradiction`; a
    background equal to `you` / `goal` / `danger` is `palette-collision`,
    downgraded to the existing `palette-overload-declared` WARN when a declared
    deception entry carries the overload keyword; `cell_px` in {6, 7} is the
    new WARN id `render-scale-off-menu`.
  * `cell_px * grid == 64` exactly PASSES.
  * `lint_spec(..., require_render=True)` with no usable render is a `schema`
    kill whose detail names `lint.require_render`.
  * The writer prompt documents both fields and carries the corpus tile-scale
    menu and L1-colors band — STANDING text, not knob-gated, so it is pinned
    under three tier-policy states.

Contract readings this file encodes where V-B left a choice open — each one is
a line to renegotiate, not a fact:

  * "a corpus line carries the tile-scale menu ... and the L1-colors band" is
    read as "both bands reach the prompt, each rendered on ONE line", not as
    "both sit on the same physical line": `visual_canon`'s own card spends a
    line on each, and the contract does not forbid that shape.
  * The tile-scale menu is pinned IN ORDER (a menu rendered from an ordered
    tuple keeps its order); the L1 band is pinned order-insensitively, because
    `(4, 7, 11)` is legitimately written as "min 4, median 7, max 11" or as
    "4-11, median 7". Both number groups are BUILT from
    `visual_canon.OFFICIAL_VISUAL_CONSTANTS` at test time, never retyped.
  * "a documentation line for render.cell_px / palette.background" is read as
    a line naming both halves of the path, in either spelling
    (`game.render.cell_px` or `render` + `cell_px` on one line).
  * Pin 1 globs `out/`, which is gitignored and owned by the live runs. The
    corpus pins SKIP when that tree is absent (a fresh clone) rather than
    failing for a reason that is not about the code; on a machine that has run
    the batches they are live. The four dir names frozen at contract time are
    asserted present whenever the tree exists at all.
  * DELIBERATELY NOT PINNED, both genuinely ambiguous in the contract:
    (a) whether `render: {}` — present but carrying no `cell_px` — is a
    `schema` kill or merely "no usable render" (the `require_render` wording
    implies an unusable render that is not itself a kill); (b) whether the
    `render.cellpx` typo of pin 5 ALSO produces a schema kill for the missing
    `cell_px`. Pin 5 asserts only what the contract states: the scoped
    unknown-field warn.
  * `spec.yaml` mutations are built from `fixtures/specs/good-spec.yaml`, the
    hand-written §11 spec the b5 suite pins as passing, so every kill below is
    a ONE-CHANGE mutation and "no other rule fired" is a fair assertion.

Run: .venv/bin/python -m pytest gen/tests/test_b003_render.py -v

No driver, no network, no writes: every test reads fixtures and lints in
memory.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from gen import s1_spec
from gen.config import REPO_ROOT, load_config
from gen.s0_ideas import load_vocab
from gen.tiers import TierPolicy
from gen.visual_canon import OFFICIAL_VISUAL_CONSTANTS

PILOT = "config/b001-pilot.yaml"
B002 = "config/b002-triple.yaml"

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "specs"
GOOD_PATH = FIXTURES / "good-spec.yaml"
CORPUS_ROOT = REPO_ROOT / "out" / "corpus"
B002_IDEA_PATH = REPO_ROOT / "out" / "ideas" / "b002-triple" / "idea-001.json"

# The shipped spec dirs at contract time (b001's pilot + b002's triple). The
# glob is the contract's rule; this tuple only guards against a glob that
# quietly matches nothing on a tree that HAS been run.
FROZEN_SHIPPED = (
    "pump-flow-match-glow",
    "pump-phase-time-echo",
    "core-ward-phase-gates",
    "convoy-in-the-fog",
)

# The words a render finding cannot avoid. Pin 1 asserts NONE of them shows up
# on a spec that declares neither field.
RENDER_MARKS = ("render", "cell_px", "background")

# The new WARN id and the require_render marker are contract-frozen strings —
# the two things in this file that are quoted rather than derived.
SCALE_WARN = "render-scale-off-menu"
REQUIRE_RENDER_MARK = "lint.require_render"
OVERLOAD_WARN = "palette-overload-declared"  # the EXISTING exemption warn id

# The camera, read off the module rather than retyped: `GRID_MAX` is the 64
# the canvas bound multiplies against.
CANVAS = s1_spec.GRID_MAX

# The scales the contract warns on, and the menu they are off — the menu comes
# from the pinned corpus constant, never from this file.
OFF_MENU_WARNED = (6, 7)
TILE_MENU = tuple(int(scale) for scale in OFFICIAL_VISUAL_CONSTANTS["tile_scale_menu"])
L1_COLORS = tuple(int(value) for value in OFFICIAL_VISUAL_CONSTANTS["l1_colors"])

# The reference pipeline's derived budget rule — every level's budget set to six
# times the verified winning path, declared to take precedence over the spec —
# contradicts BUDGET_HEADROOM and must never be quoted into a prompt. Detected
# by its signature multiplier rather than by quoting the upstream sentence
# (contract OS-2 FRONT B.4: no upstream quote in a shipped test).
VENDORED_6X_MARK = re.compile(r"\b6\s*[x\u00d7]\b")

# Tier-policy states the STANDING prompt text must survive unchanged.
POLICY_STATES = ("no-policy", "neutral", "guidance")

_OMITTED = object()
_INT_RE = re.compile(r"\d+")


# --------------------------------------------------------------------------
# the surface under test, reached through shims that fail in the contract's
# own words when the frozen keyword is missing
# --------------------------------------------------------------------------


def lint(spec, vocab, idea=None, *, require_render=_OMITTED):
    """`lint_spec`, with `require_render` passed only when this call supplies one."""
    if require_render is _OMITTED:
        return s1_spec.lint_spec(spec, vocab, idea)
    try:
        return s1_spec.lint_spec(spec, vocab, idea, require_render=require_render)
    except TypeError as exc:
        if "require_render" not in str(exc):
            raise
        pytest.fail(
            f"gen.s1_spec.lint_spec does not accept require_render=... ({exc}) — the V-B "
            "contract freezes it as a keyword-only flag defaulting to False, and a flag the "
            "linter cannot be handed is a rule that can never fire"
        )


def writer_prompt(cfg, idea, policy=_OMITTED):
    """`build_writer_prompt`, with `tier_policy` passed only when supplied."""
    if policy is _OMITTED:
        return s1_spec.build_writer_prompt(cfg, idea)
    try:
        return s1_spec.build_writer_prompt(cfg, idea, tier_policy=policy)
    except TypeError as exc:
        if "tier_policy" not in str(exc):
            raise
        pytest.fail(
            f"gen.s1_spec.build_writer_prompt does not accept tier_policy=... ({exc}) — the "
            "landed T-B signature carries it, and V-B pins the render text as STANDING under "
            "every policy state"
        )


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _findings(report) -> list[dict]:
    return [*report.kills, *report.warns]


def _rules(findings: Iterable[Mapping]) -> set[str]:
    return {finding["rule"] for finding in findings}


def _with_rule(findings: Iterable[Mapping], rule: str) -> list[dict]:
    return [finding for finding in findings if finding["rule"] == rule]


def _mentioning(findings: Iterable[Mapping], *marks: str) -> list[dict]:
    """Findings whose rule OR detail carries any of `marks` (case-insensitive)."""
    hits = []
    for finding in findings:
        text = f"{finding.get('rule', '')} {finding.get('detail', '')}".lower()
        if any(mark.lower() in text for mark in marks):
            hits.append(finding)
    return hits


def _why(report) -> str:
    return f"kills={report.kills} warns={report.warns}"


def _good_spec() -> dict:
    """A fresh parse of the hand-written §11 fixture (never a shared dict)."""
    return yaml.safe_load(GOOD_PATH.read_text(encoding="utf-8"))


def build_spec(
    *,
    render=_OMITTED,
    cell_px=_OMITTED,
    grid: Sequence[int] | None = None,
    background=_OMITTED,
    danger=_OMITTED,
    deceptions: Sequence[str] | None = None,
) -> dict:
    """`good-spec.yaml` with ONE render/palette/layout thing changed.

    `render=` sets the whole block (for the malformed and typo cases);
    `cell_px=` is the shorthand for the well-shaped `{cell_px: N}` block.
    """
    spec = _good_spec()
    game = spec["game"]
    if grid is not None:
        game["layout"]["grid"] = list(grid)
    if render is not _OMITTED:
        game["render"] = render
    elif cell_px is not _OMITTED:
        game["render"] = {"cell_px": cell_px}
    if background is not _OMITTED:
        game["palette"]["background"] = background
    if danger is not _OMITTED:
        game["palette"]["danger"] = danger
    if deceptions is not None:
        game["knobs"]["deceptions"] = list(deceptions)
    return spec


def _numbers(line: str) -> list[int]:
    return [int(token) for token in _INT_RE.findall(line)]


def _in_order(needles: Sequence[int], haystack: Sequence[int]) -> bool:
    """`needles` appear in `haystack` in order (not necessarily adjacent)."""
    remaining = iter(haystack)
    return all(any(needle == found for found in remaining) for needle in needles)


def _lines_in_order(text: str, values: Sequence[int]) -> list[str]:
    """Every line whose integers carry `values` in order (gaps allowed)."""
    return [line for line in text.splitlines() if _in_order(values, _numbers(line))]


def _lines_with_all(text: str, values: Sequence[int]) -> list[str]:
    """Every line carrying all of `values`, in any order."""
    wanted = Counter(values)
    lines = []
    for line in text.splitlines():
        found = Counter(_numbers(line))
        if all(found[value] >= count for value, count in wanted.items()):
            lines.append(line)
    return lines


def _lines_with(text: str, *marks: str) -> list[str]:
    """Lines carrying every mark (case-insensitive) — the doc-line locator."""
    return [
        line
        for line in text.splitlines()
        if all(mark.lower() in line.lower() for mark in marks)
    ]


def _shipped_dirs() -> list[Path]:
    """Every shipped spec dir: a `spec.yaml` with a `spec.md` sibling.

    `.killed/` archives sit one level deeper than this glob reaches, so they
    are out by construction as well as by the spec.md rule.
    """
    if not CORPUS_ROOT.is_dir():
        return []
    # LEAD FIX (C-3 close): the back-compat pins are about the PRE-render
    # corpus — specs authored before game.render existed must lint unchanged.
    # A b003+ spec is authored UNDER lint.require_render and legitimately
    # declares the field, so an open glob turns every new batch into fixture
    # drift. Pin the discovery to the frozen four.
    return sorted(
        path.parent
        for path in CORPUS_ROOT.glob("*/*/spec.yaml")
        if (path.parent / "spec.md").is_file() and path.parent.name in FROZEN_SHIPPED
    )


SHIPPED_DIRS = _shipped_dirs()
SHIPPED_IDS = [f"{path.parent.name}/{path.name}" for path in SHIPPED_DIRS]
needs_corpus = pytest.mark.skipif(
    not SHIPPED_DIRS,
    reason=(
        "no shipped spec dir under out/corpus — the live-run tree is gitignored, so the "
        "back-compat pin has nothing to read on this checkout"
    ),
)
needs_b002_idea = pytest.mark.skipif(
    not B002_IDEA_PATH.is_file(),
    reason=(
        "out/ideas/b002-triple/idea-001.json is absent — the writer-prompt pin needs a REAL "
        "b002 idea and the live-run tree is gitignored"
    ),
)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def vocab() -> set[str]:
    return set(load_vocab(load_config(PILOT)))


@pytest.fixture(scope="module")
def prompts() -> dict[str, str]:
    """The writer prompt for a real b002 idea, in three tier-policy states."""
    cfg = load_config(B002)
    idea = json.loads(B002_IDEA_PATH.read_text(encoding="utf-8"))
    return {
        "no-policy": writer_prompt(cfg, idea),
        "neutral": writer_prompt(cfg, idea, TierPolicy()),
        "guidance": writer_prompt(cfg, idea, TierPolicy(prompt_guidance=True)),
    }


# --------------------------------------------------------------------------
# pin 1 — back-compat: a spec that declares neither field is untouched
# --------------------------------------------------------------------------


@needs_corpus
def test_the_glob_sees_the_shipped_specs():
    """The corpus pin must not pass by testing nothing."""
    names = {path.name for path in SHIPPED_DIRS}
    missing = sorted(set(FROZEN_SHIPPED) - names)
    assert not missing, (
        f"out/corpus is populated but the specs shipped at V-B time are missing {missing} "
        f"(found {sorted(names)}) — re-freeze FROZEN_SHIPPED if the tree legitimately moved"
    )
    for path in SHIPPED_DIRS:
        assert (path / "spec.yaml").is_file()
        assert (path / "spec.md").is_file()


@needs_corpus
@pytest.mark.parametrize("spec_dir", SHIPPED_DIRS, ids=SHIPPED_IDS)
def test_shipped_specs_gain_no_render_finding(vocab, spec_dir: Path):
    """Neither field is declared by any shipped spec, so the render rules must
    be completely silent on all four — the back-compat bar."""
    spec = yaml.safe_load((spec_dir / "spec.yaml").read_text(encoding="utf-8"))
    idea_path = spec_dir / "idea.json"
    idea = json.loads(idea_path.read_text(encoding="utf-8")) if idea_path.is_file() else None
    game = spec["game"]
    assert "render" not in game, "fixture drift: a shipped spec now declares game.render"
    assert "background" not in game["palette"], "fixture drift: shipped palette has background"

    report = lint(spec, vocab, idea)

    intruders = _mentioning(_findings(report), *RENDER_MARKS, SCALE_WARN)
    assert not intruders, (
        f"{spec_dir.name}: a spec declaring no render fields gained render findings "
        f"{intruders} — absent means zero new findings anywhere"
    )


@needs_corpus
@pytest.mark.parametrize("spec_dir", SHIPPED_DIRS, ids=SHIPPED_IDS)
def test_shipped_specs_match_their_shipped_lint_report(vocab, spec_dir: Path):
    """Passed-unchanged, pinned directly: the rule multisets the linter
    produces today must equal the ones in the dir's own lint-report.json, and
    no rule may fire that the shipped report did not."""
    report_path = spec_dir / "lint-report.json"
    if not report_path.is_file():
        pytest.skip(f"{spec_dir.name} ships no lint-report.json to compare against")
    shipped = json.loads(report_path.read_text(encoding="utf-8"))
    spec = yaml.safe_load((spec_dir / "spec.yaml").read_text(encoding="utf-8"))
    idea_path = spec_dir / "idea.json"
    idea = json.loads(idea_path.read_text(encoding="utf-8")) if idea_path.is_file() else None

    report = lint(spec, vocab, idea)

    for label, now, then in (
        ("kills", report.kills, shipped["kills"]),
        ("warns", report.warns, shipped["warns"]),
    ):
        assert Counter(f["rule"] for f in now) == Counter(f["rule"] for f in then), (
            f"{spec_dir.name}: {label} changed against the shipped report — "
            f"now {sorted(f['rule'] for f in now)}, shipped {sorted(f['rule'] for f in then)}"
        )
    fired = _rules(_findings(report))
    shipped_fired = {f["rule"] for f in [*shipped["kills"], *shipped["warns"]]}
    assert fired <= shipped_fired, (
        f"{spec_dir.name}: rules fired that the shipped report never fired: "
        f"{sorted(fired - shipped_fired)}"
    )
    assert report.passed == shipped["passed"]


def test_render_free_fixture_is_untouched(vocab):
    """The hand-written §11 fixture declares neither field and must still pass
    clean — every mutation pin below reads its kills as one-change deltas."""
    spec = _good_spec()
    report = lint(spec, vocab)

    assert report.passed, f"good-spec.yaml no longer passes — {_why(report)}"
    assert report.kills == []
    assert not _mentioning(_findings(report), *RENDER_MARKS, SCALE_WARN), _why(report)


def test_default_require_render_is_false(vocab):
    """Omitting the flag and passing False are the same call."""
    omitted = lint(_good_spec(), vocab)
    explicit = lint(_good_spec(), vocab, require_render=False)
    assert omitted.to_json_dict() == explicit.to_json_dict(), (
        "lint_spec(...) and lint_spec(..., require_render=False) disagree — the contract "
        "freezes False as the default"
    )


# --------------------------------------------------------------------------
# pin 2 — the boundary matrix
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cell_px", "grid"),
    [(4, (16, 16)), (1, (64, 64)), (8, (8, 8)), (2, (16, 8))],
    ids=["4x16=64", "1x64=64", "8x8=64", "2x16-and-2x8-under"],
)
def test_cell_px_inside_the_canvas_is_silent(vocab, cell_px: int, grid: tuple[int, int]):
    """`cell_px * grid == 64` exactly PASSES, and anything under it too."""
    assert max(cell_px * grid[0], cell_px * grid[1]) <= CANVAS, "fixture arithmetic"
    report = lint(build_spec(cell_px=cell_px, grid=grid), vocab)

    assert not _mentioning(_findings(report), *RENDER_MARKS, SCALE_WARN), (
        f"cell_px {cell_px} on grid {list(grid)} fits the {CANVAS}-canvas and sits on the "
        f"menu, so it must produce no render finding — {_why(report)}"
    )
    assert report.passed, _why(report)


@pytest.mark.parametrize(
    ("cell_px", "grid"),
    [(5, (13, 13)), (5, (13, 4)), (5, (4, 13)), (2, (33, 33))],
    ids=["5x13-both", "5x13-width", "5x13-height", "2x33-both"],
)
def test_canvas_overflow_is_a_contradiction_kill(vocab, cell_px: int, grid: tuple[int, int]):
    """Over 64 on EITHER axis is the existing `contradiction` id, and the kill
    names the canvas it blew."""
    assert max(cell_px * grid[0], cell_px * grid[1]) > CANVAS, "fixture arithmetic"
    report = lint(build_spec(cell_px=cell_px, grid=grid), vocab)

    kills = _with_rule(report.kills, "contradiction")
    assert kills, (
        f"cell_px {cell_px} on grid {list(grid)} renders past the {CANVAS}-canvas and must be "
        f"a contradiction kill — {_why(report)}"
    )
    assert _rules(report.kills) == {"contradiction"}, (
        f"this spec is good-spec.yaml with ONE change (render + grid); a rule beyond "
        f"contradiction fired — {_why(report)}"
    )
    named = [kill for kill in kills if str(CANVAS) in kill["detail"]]
    assert named, f"the overflow kill must name the {CANVAS}-canvas it measured against: {kills}"
    assert _mentioning(named, "cell_px", "render"), (
        f"the overflow kill must name the field the writer has to change: {named}"
    )


@pytest.mark.parametrize("cell_px", OFF_MENU_WARNED)
def test_off_menu_scale_warns_exactly_once(vocab, cell_px: int):
    """6 and 7 are off the official tile-scale menu: one WARN, never a kill."""
    report = lint(build_spec(cell_px=cell_px, grid=(8, 8)), vocab)

    warns = _with_rule(report.warns, SCALE_WARN)
    assert len(warns) == 1, (
        f"cell_px {cell_px} is off the official menu {list(TILE_MENU)} and must raise exactly "
        f"one {SCALE_WARN!r} warn — {_why(report)}"
    )
    assert report.kills == [], f"an off-menu scale is a warn, never a kill — {_why(report)}"
    assert report.passed


@pytest.mark.parametrize("cell_px", TILE_MENU)
def test_menu_scales_never_warn(vocab, cell_px: int):
    """Every scale on the corpus menu is silent (grid 8x8 keeps all six inside
    the canvas, with 8 landing on the ==64 boundary)."""
    report = lint(build_spec(cell_px=cell_px, grid=(8, 8)), vocab)

    assert _with_rule(report.warns, SCALE_WARN) == [], (
        f"cell_px {cell_px} IS on the measured menu {list(TILE_MENU)} — {_why(report)}"
    )
    assert report.passed, _why(report)


@pytest.mark.parametrize(
    "cell_px",
    [0, 9, "2"],
    ids=["zero", "nine", "string-2"],
)
def test_malformed_cell_px_is_a_schema_kill(vocab, cell_px):
    """Off the int range, or not an int at all: the `schema` id, and the
    derived canvas rule stays quiet (grid 4x4 leaves it nothing to say)."""
    report = lint(build_spec(cell_px=cell_px, grid=(4, 4)), vocab)

    kills = _with_rule(report.kills, "schema")
    assert kills, f"cell_px {cell_px!r} must be a schema kill — {_why(report)}"
    assert _mentioning(kills, "cell_px"), f"the kill must name cell_px: {kills}"
    assert _rules(report.kills) == {"schema"}, (
        f"a malformed cell_px is named ONCE, by schema; a derived rule piled on — {_why(report)}"
    )


def test_malformed_render_block_is_a_schema_kill(vocab):
    """`render` that is not a mapping is malformed render, not a silent field."""
    report = lint(build_spec(render=4, grid=(4, 4)), vocab)

    kills = _mentioning(_with_rule(report.kills, "schema"), "render")
    assert kills, f"a non-mapping game.render must be a schema kill — {_why(report)}"


# --------------------------------------------------------------------------
# pin 3 — palette.background
# --------------------------------------------------------------------------


def test_background_off_the_semantic_indices_passes(vocab):
    """5 collides with nothing in the fixture palette (you 4, goal 3)."""
    report = lint(build_spec(background=5), vocab)

    assert report.passed, f"background 5 collides with nothing — {_why(report)}"
    assert not _mentioning(_findings(report), "background"), _why(report)


@pytest.mark.parametrize(
    ("slot", "index", "danger"),
    [("you", 4, _OMITTED), ("goal", 3, _OMITTED), ("danger", 6, 6)],
    ids=["background==you", "background==goal", "background==danger"],
)
def test_background_colliding_with_a_semantic_index_kills(vocab, slot, index, danger):
    """`background` joins the you/goal/danger collision check on the EXISTING
    `palette-collision` id."""
    spec = build_spec(background=index, danger=danger)
    assert spec["game"]["palette"][slot] == index, "fixture arithmetic"

    report = lint(spec, vocab)

    kills = _with_rule(report.kills, "palette-collision")
    assert kills, (
        f"palette.background {index} equals palette.{slot} and must be a palette-collision "
        f"kill — {_why(report)}"
    )
    assert _mentioning(kills, "background"), f"the kill must name background: {kills}"
    assert _rules(report.kills) == {"palette-collision"}, (
        f"one-change mutation, one rule expected — {_why(report)}"
    )


def test_declared_overload_downgrades_the_background_collision(vocab):
    """The existing §2.8 exemption: an overload-keyword deception entry turns
    the kill into the existing `palette-overload-declared` warn."""
    spec = build_spec(
        background=4,  # == palette.you in the fixture
        deceptions=["palette overload — the background index doubles as the selection marker"],
    )

    report = lint(spec, vocab)

    assert _with_rule(report.kills, "palette-collision") == [], (
        f"a declared palette-overload lever exempts the background collision — {_why(report)}"
    )
    assert report.passed, _why(report)
    warns = _with_rule(report.warns, OVERLOAD_WARN)
    assert len(warns) == 1, (
        f"the exempted collision must ship as exactly one {OVERLOAD_WARN!r} warn — "
        f"{_why(report)}"
    )
    assert _mentioning(warns, "background"), (
        f"the exemption warn must still name the overloaded slot: {warns}"
    )


@pytest.mark.parametrize("background", [16, -1])
def test_background_out_of_range_is_a_schema_kill(vocab, background: int):
    """0-15, strictly — the palette range the module already pins."""
    report = lint(build_spec(background=background), vocab)

    kills = _with_rule(report.kills, "schema")
    assert kills, f"background {background} is outside 0-15 — {_why(report)}"
    assert _mentioning(kills, "background"), f"the kill must name background: {kills}"
    assert _rules(report.kills) == {"schema"}, f"one-change mutation — {_why(report)}"


def test_background_absent_says_nothing(vocab):
    """The optional half of the back-compat bar, stated on the fixture."""
    report = lint(_good_spec(), vocab)
    assert not _mentioning(_findings(report), "background"), _why(report)


# --------------------------------------------------------------------------
# pin 4 — require_render
# --------------------------------------------------------------------------


def test_require_render_true_without_render_kills(vocab):
    report = lint(_good_spec(), vocab, require_render=True)

    kills = _mentioning(_with_rule(report.kills, "schema"), REQUIRE_RENDER_MARK)
    assert kills, (
        f"require_render=True with no game.render must be a schema kill whose detail names "
        f"{REQUIRE_RENDER_MARK!r} — {_why(report)}"
    )
    assert not report.passed


def test_require_render_true_with_a_valid_render_does_not_kill(vocab):
    report = lint(build_spec(cell_px=4, grid=(16, 16)), vocab, require_render=True)

    assert not _mentioning(report.kills, REQUIRE_RENDER_MARK), (
        f"a usable game.render satisfies require_render — {_why(report)}"
    )
    assert report.passed, _why(report)


@pytest.mark.parametrize("with_render", [False, True], ids=["no-render", "with-render"])
def test_require_render_false_never_fires(vocab, with_render: bool):
    spec = build_spec(cell_px=4, grid=(16, 16)) if with_render else _good_spec()

    for report in (lint(spec, vocab), lint(spec, vocab, require_render=False)):
        assert not _mentioning(_findings(report), REQUIRE_RENDER_MARK), (
            f"require_render is False here, so the rule must not fire — {_why(report)}"
        )
        assert report.passed, _why(report)


# --------------------------------------------------------------------------
# pin 5 — unknown-key hygiene
# --------------------------------------------------------------------------


def test_render_block_is_a_known_field(vocab):
    """`game.render` is a §11 field now: it must not read as an extra key."""
    report = lint(build_spec(cell_px=4, grid=(16, 16), background=5), vocab)

    flagged = [
        warn
        for warn in _with_rule(report.warns, "unknown-field")
        if re.search(r"game\.render\s*[:,]", warn["detail"])
        or re.search(r"palette\.background\s*[:,]", warn["detail"])
    ]
    assert not flagged, (
        f"game.render / palette.background are declared §11 fields, not unknown keys: {flagged}"
    )


def test_render_key_typo_warns_inside_render(vocab):
    """`cellpx` is the typo the writer will make; it must be named, scoped to
    the render block, and it must be a WARN (unknown keys never kill)."""
    report = lint(build_spec(render={"cellpx": 2}, grid=(8, 8)), vocab)

    warns = [
        warn
        for warn in _with_rule(report.warns, "unknown-field")
        if "cellpx" in warn["detail"] and "render" in warn["detail"]
    ]
    assert warns, (
        f"game.render.cellpx must trip an unknown-field warn scoped inside render — "
        f"{_why(report)}"
    )


# --------------------------------------------------------------------------
# pin 6 — the writer prompt (STANDING text, every policy state)
# --------------------------------------------------------------------------


@needs_b002_idea
@pytest.mark.parametrize("state", POLICY_STATES)
def test_writer_prompt_documents_both_render_fields(prompts, state: str):
    prompt = prompts[state]

    cell_px_lines = _lines_with(prompt, "render", "cell_px")
    assert cell_px_lines, (
        f"[{state}] the schema notes carry no documentation line for render.cell_px — the "
        "writer cannot declare a field the prompt never mentions"
    )
    background_lines = _lines_with(prompt, "palette", "background")
    assert background_lines, (
        f"[{state}] the schema notes carry no documentation line for palette.background"
    )


@needs_b002_idea
@pytest.mark.parametrize("state", POLICY_STATES)
def test_writer_prompt_carries_the_corpus_bands(prompts, state: str):
    """Both bands are BUILT from `OFFICIAL_VISUAL_CONSTANTS` here — a number
    typed into this file could not catch the number drifting there."""
    prompt = prompts[state]
    assert len(TILE_MENU) >= 2 and len(L1_COLORS) == 3, "corpus constants changed shape"

    menu_lines = _lines_in_order(prompt, TILE_MENU)
    assert menu_lines, (
        f"[{state}] no prompt line carries the tile-scale menu {list(TILE_MENU)} in order"
    )
    assert any(re.search(r"scale|tile|px|cell", line, re.IGNORECASE) for line in menu_lines), (
        f"[{state}] the lines carrying {list(TILE_MENU)} do not read as the tile-scale menu: "
        f"{menu_lines}"
    )

    l1_lines = _lines_with_all(prompt, L1_COLORS)
    assert l1_lines, (
        f"[{state}] no prompt line carries the L1-colors band {list(L1_COLORS)}"
    )
    assert any(re.search(r"colou?r", line, re.IGNORECASE) for line in l1_lines), (
        f"[{state}] the lines carrying {list(L1_COLORS)} do not read as the colors band: "
        f"{l1_lines}"
    )


@needs_b002_idea
@pytest.mark.parametrize("state", POLICY_STATES)
def test_writer_prompt_never_quotes_the_vendored_6x_rule(prompts, state: str):
    """The reference pipeline's derived 6x budget rule contradicts
    BUDGET_HEADROOM; carrying the render craft must not drag it in."""
    assert not VENDORED_6X_MARK.search(prompts[state].lower()), (
        f"[{state}] the writer prompt quotes the vendored 6x budget rule "
        f"({VENDORED_6X_MARK.pattern!r}) — the visual material is distilled, never quoted "
        f"wholesale"
    )


# --------------------------------------------------------------------------
# pin 7 — KILL_RULES is closed
# --------------------------------------------------------------------------


def test_kill_rules_gained_no_render_or_tier_id():
    """The eight are pinned by b5; V-B's pin is the two EXCLUSIONS — every
    render finding rides an existing id."""
    rules = tuple(s1_spec.KILL_RULES)

    assert len(rules) == 8, f"KILL_RULES is closed at 8 ids, got {list(rules)}"
    assert "tier-terms" not in rules, "the tier workstream must not have opened KILL_RULES"
    assert SCALE_WARN not in rules, f"{SCALE_WARN} is a WARN id, never a kill rule"
    render_ids = [
        rule for rule in rules if re.search(r"render|cell_px|background|scale", rule)
    ]
    assert not render_ids, f"KILL_RULES gained render ids {render_ids} — it is a closed list"
    # ...and the ids this suite asserts on are all members of it.
    assert {"schema", "contradiction", "palette-collision"} <= set(rules)


# --------------------------------------------------------------------------
# pin 8 — purity and determinism
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        {"cell_px": 4, "grid": (16, 16)},
        {"cell_px": 6, "grid": (8, 8)},
        {"cell_px": 5, "grid": (13, 13)},
        {"background": 4},
        {"cell_px": "2", "grid": (4, 4)},
        {"render": {"cellpx": 2}, "grid": (8, 8)},
    ],
    ids=["valid", "off-menu", "overflow", "collision", "malformed", "typo"],
)
@pytest.mark.parametrize("require", [False, True], ids=["lenient", "required"])
def test_lint_is_pure_and_deterministic(vocab, case: dict, require: bool):
    spec = build_spec(**case)
    untouched = deepcopy(spec)
    idea = json.loads((FIXTURES / "idea-001.json").read_text(encoding="utf-8"))
    idea_untouched = deepcopy(idea)

    first = lint(spec, vocab, idea, require_render=require)
    second = lint(spec, vocab, idea, require_render=require)

    assert spec == untouched, "lint_spec mutated the spec dict it was handed"
    assert idea == idea_untouched, "lint_spec mutated the idea dict it was handed"
    assert first.to_json_dict() == second.to_json_dict(), (
        f"two identical calls disagreed — {_why(first)} vs {_why(second)}"
    )
    assert first.passed == (first.kills == [])
