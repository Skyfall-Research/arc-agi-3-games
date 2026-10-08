"""Contract E-1 — lever semantics sync: the IMPLEMENTER's pins.

The blind lane writes `gen/tests/test_v2_levers.py` from the contract alone and
this file never touches it. These are the pins the implementation is answerable
for, in the order the contract states the work:

1. THE LOADER. `canon_docs.load_deception_levers` parses affordance §7 into the
   six signed levers VERBATIM and is total over them — a missing, renamed,
   renumbered or unregistered lever is a stop, never a thinner prompt. Same for
   §10's one-sentence policy (`load_deception_policy`).
2. THE FOLD. Every spelling the pre-E-1 catalog matched — including the four it
   admitted were not canon-attested — still detects, and folds onto exactly one
   of the six. Nothing previously matchable became unmatchable.
3. THE MEASURED DEMONSTRATION. The real lever-history sidecars of the two games
   whose naming churn is what this contract exists for, re-folded. READ-ONLY:
   the corpus is evidence, and nothing here writes outside tmp_path.
4. PROMPT SYNC. The writer's prompt, the implementer's payload and the blind
   audit prompt each carry every lever's canon text VERBATIM, and a sentinel
   planted in a MIRRORED canon reaches all three — one source, three prompts.
5. COMPATIBILITY. Every shipped verifier report still validates and every
   shipped spec still declares exactly the levers it declared.
6. THE TWO DEFECT FIXES. The audit prompt's enforcement sentence matches what
   `validate_claims` really does, and a reconciled deception entry names the
   path that wrote it.

Pure and hermetic: no drivers, no network, no spend. The canon is read through
the loaders and MIRRORED with symlinks when a pin needs it doctored, so nothing
is ever written into `canon/`, `out/` or `games/`.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from gen import canon_docs, s1_spec, s3_verify
from gen import orchestrator as orch
from gen.config import load_config
from gen.frames import capture
from gen.s2_implement import build_payload
from gen.s3_verify import (
    build_verifier_prompt,
    detect_levers,
    stage_worker_copy,
    validate_report,
)

REPO = Path(__file__).resolve().parents[2]
PILOT_CONFIG = REPO / "config" / "b001-pilot.yaml"
TOY = REPO / "gen" / "tests" / "toy_worker"
CORPUS = REPO / "out" / "corpus"
# A shipped spec the payload can be built from: six levels, declared deceptions,
# and it linted when it shipped. Copied into tmp_path, never built in place.
PAYLOAD_SPEC = CORPUS / "b002-triple" / "convoy-in-the-fog"

# --- the two naming-churn exhibits (the contract's own fixtures) -------------
# Read-only sidecars. `names` is what the rounds RECORDED (the instability this
# contract measures) and `levers` is what those names fold onto now.
# LEAD REPOINT 2026-10-06: the echo slot is PARKED-BUT-LIFTABLE (contract E-5),
# and its live sidecar legitimately GREW when revival #3's lifted rounds ran
# (5 rounds/4 names at E-1's measurement → 9 rounds/5 names, the new name
# `retrospective punishment` — itself a signed lever). A live out/ path cannot
# serve an exhibit pin on a pipeline whose slots resume; the bytes as they
# stood at 2026-10-06 are frozen in gen/tests/fixtures/.
ECHO_HISTORY = (
    Path(__file__).resolve().parent
    / "fixtures" / "two-keys-one-echo-lever-history-frozen-2026-10-06.json"
)
SEAMLOCK_HISTORY = CORPUS / "g20261001-1" / "seamlock" / "worker.lever-history.json"
ROVER_HISTORY = CORPUS / "g20261001-1" / "key-strip-rover" / "worker.lever-history.json"

# --- the frozen pre-E-1 surface ---------------------------------------------
# The 11-keyword tuple `DECEPTION_CATALOG` held before this contract, written
# out here because the point of the pin is that the OLD list still matches: a
# derived copy would move with the code it is supposed to hold still.
PRE_E1_CATALOG = (
    "camouflage",
    "decoy",
    "look-alike",
    "lookalike",
    "mimic",
    "disguise",
    "palette overload",
    "false tell",
    "fake tell",
    "lying display",
    "retrospective punishment",
)
# Every lever name ever written to disk by a real run (the union over every
# shipped spec, report and lever-history sidecar — the sweep's own count: 7 of
# the 11, with lookalike/mimic/disguise/fake tell never sighted).
OBSERVED_ON_DISK = (
    "camouflage",
    "decoy",
    "false tell",
    "look-alike",
    "lying display",
    "palette overload",
    "retrospective punishment",
)
# The fold this contract signs, lever by lever.
EXPECTED_FOLD = {
    "look-alike": "look-alike",
    "lookalike": "look-alike",
    "mimic": "look-alike",
    "disguise": "look-alike",
    "palette overload": "palette overload",
    "camouflage": "palette overload",
    "decoy": "decoy",
    "lying display": "lying display",
    "false tell": "lying display",
    "fake tell": "lying display",
    "retrospective punishment": "retrospective punishment",
}


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def cfg() -> dict:
    return load_config(PILOT_CONFIG)


@pytest.fixture(scope="session")
def docs_root(cfg: dict) -> Path:
    root = Path(cfg["duckwm_docs"]).resolve()
    assert root.is_dir(), f"the config's duckwm_docs is not a directory: {root}"
    return root


@pytest.fixture(scope="session")
def affordance_text(docs_root: Path) -> str:
    return (docs_root / canon_docs.AFFORDANCE_MD).read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def levers(cfg: dict) -> dict[int, canon_docs.DeceptionLever]:
    return canon_docs.load_deception_levers(cfg)


def mirror_canon(source: Path, dest: Path, doctored: str) -> Path:
    """A canon root under tmp: symlinks everywhere, affordance §7 a real file.

    The `test_b003_visual` pattern, re-stated here so this file depends on no
    other contract's module. CANON STAYS READ-ONLY — nothing is copied out of
    it and nothing is written into it.
    """
    parts = canon_docs.AFFORDANCE_MD.split("/")
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


def doctored_cfg(cfg: dict, root: Path) -> dict:
    out = dict(cfg)
    out["duckwm_docs"] = str(root)
    return out


SENTINEL = "PLANTED BY THE E-1 PINS: this clause is not in the signed canon."


@pytest.fixture(scope="session")
def sentinel_cfg(cfg: dict, affordance_text: str, docs_root: Path, tmp_path_factory) -> dict:
    """A config whose canon carries `SENTINEL` inside §7's third lever.

    The drift pin's instrument: if a prompt quotes the loader, the sentinel
    reaches it; if a prompt carries a hand-copied list, it does not.
    """
    lines = affordance_text.splitlines(keepends=True)
    head = next(i for i, line in enumerate(lines) if line.startswith("3. **Decoy"))
    lines.insert(head + 1, f"   {SENTINEL}\n")
    root = tmp_path_factory.mktemp("e1-canon-sentinel") / "canon"
    return doctored_cfg(cfg, mirror_canon(docs_root, root, "".join(lines)))


def _game_class(path: Path) -> type:
    """Exec-load a fixture game file and return its one ARCBaseGame subclass."""
    import importlib.util
    import sys

    from arcengine import ARCBaseGame

    name = f"e1_fixture_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot import {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    found = [
        value
        for value in vars(module).values()
        if isinstance(value, type) and issubclass(value, ARCBaseGame) and value is not ARCBaseGame
    ]
    assert len(found) == 1, f"{path} defines {len(found)} ARCBaseGame subclasses, expected 1"
    return found[0]


def _spec_copy(dest: Path) -> Path:
    """The payload fixture spec, copied out of the corpus into tmp_path."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("spec.yaml", "spec.md"):
        shutil.copyfile(PAYLOAD_SPEC / name, dest / name)
    return dest


def _idea(idea_id: str) -> dict:
    """The three keys `build_writer_prompt` requires, in the real idea shape."""
    return {
        "id": idea_id,
        "seed_terms": ["move.grid", "goal.cover"],
        "prose": {
            "title": "E-1 Fixture Yard",
            "text": "A short fixture idea for the E-1 prompt-sync pins: one mover, one "
            "covered goal, nothing deceptive declared.",
        },
    }


def _three_prompts(cfg: dict, root: Path) -> dict[str, str]:
    """The three prompts that have to agree about the levers, all three built.

    `root` is the caller's tmp dir and is reused deliberately by the determinism
    pin: the audit prompt names the staged copy's path, so two builds under two
    different tmp dirs differ for a reason that is not the levers.
    """
    idea = _idea("e1-0001")
    payload, _report = build_payload(_spec_copy(root / "spec"), cfg)
    staged = root / "toy.staged"
    if not staged.is_dir():
        stage_worker_copy(TOY, staged)  # returns the tree hash; the dir is the copy
    return {
        "s1 writer prompt": s1_spec.build_writer_prompt(cfg, idea),
        "s2 implementer payload": payload,
        "s3 blind audit prompt": build_verifier_prompt(
            cfg, capture(_game_class(TOY / "game.py")), staged
        ),
    }


@pytest.fixture(scope="session")
def prompts(cfg: dict, tmp_path_factory) -> dict[str, str]:
    return _three_prompts(cfg, tmp_path_factory.mktemp("e1-prompts-signed"))


@pytest.fixture(scope="session")
def sentinel_prompts(sentinel_cfg: dict, tmp_path_factory) -> dict[str, str]:
    return _three_prompts(sentinel_cfg, tmp_path_factory.mktemp("e1-prompts-sentinel"))


def _history(path: Path) -> list[dict]:
    assert path.is_file(), (
        f"the contract's fixture sidecar is missing: {path} — the before/after fold is "
        f"measured on the real audit rounds, not on an invented history"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _recorded_names(history: list[dict]) -> list[str]:
    return sorted({name for entry in history for name in entry["detected"]})


def _folded(names: list[str]) -> list[str]:
    return sorted({lever for name in names for lever in detect_levers(name)})


# --------------------------------------------------------------------------- #
# 1 — the loader
# --------------------------------------------------------------------------- #


def test_the_loader_returns_the_six_signed_levers(levers: dict) -> None:
    assert sorted(levers) == sorted(canon_docs.LEVER_HEAD_KEYWORDS) == [1, 2, 3, 4, 5, 6], (
        f"affordance §7 is the catalog's six signed levers; the loader returned "
        f"{sorted(levers)}"
    )
    for number, lever in levers.items():
        assert canon_docs.LEVER_HEAD_KEYWORDS[number] in lever.title, (
            f"lever {number} is headed {lever.title!r}, which does not carry its registered "
            f"keyword {canon_docs.LEVER_HEAD_KEYWORDS[number]!r}"
        )


def test_every_lever_is_a_verbatim_substring_of_the_canon(
    levers: dict, affordance_text: str
) -> None:
    """Quoted, never paraphrased — the `load_term_definitions` contract."""
    for number, lever in levers.items():
        assert lever.text in affordance_text, (
            f"lever {number}'s text is not a verbatim slice of "
            f"{canon_docs.AFFORDANCE_MD} — a prompt that reflows or trims the canon teaches "
            f"a lever that was never signed"
        )
        assert lever.text.startswith(f"{number}. **"), (
            f"lever {number}'s slice does not start at its own numbered head: {lever.text[:40]!r}"
        )


def test_the_exhibits_ride_along(levers: dict) -> None:
    """The per-official exhibits are PART of the lever, not a decoration.

    One frame-verified citation per lever, named in the contract's own reframe:
    they are how an implementer tells the lever apart from the next one.
    """
    exhibits = {1: "r11l", 2: "cd82", 3: "m0r0", 4: "lf52", 5: "g50t", 6: "lf52"}
    for number, slug in exhibits.items():
        assert slug in levers[number].flowed, (
            f"lever {number}'s quote no longer carries its {slug} exhibit — the exhibit list "
            f"is what makes the definition measurable"
        )


def test_a_renamed_lever_head_is_a_stop(
    cfg: dict, affordance_text: str, docs_root: Path, tmp_path
) -> None:
    doctored = affordance_text.replace("**Palette overloading**", "**Index reuse**")
    assert doctored != affordance_text, "fixture: the §7.2 head was not rewritten"
    bad = doctored_cfg(cfg, mirror_canon(docs_root, tmp_path / "renamed", doctored))
    with pytest.raises(ValueError, match="Palette overloading"):
        canon_docs.load_deception_levers(bad)


def test_a_missing_lever_is_a_stop(
    cfg: dict, affordance_text: str, docs_root: Path, tmp_path
) -> None:
    """Drop §7.6 entirely: the loader names what it wanted rather than quoting five."""
    lines = affordance_text.splitlines(keepends=True)
    head = next(i for i, line in enumerate(lines) if line.startswith("6. **Retrospective"))
    end = next(i for i, line in enumerate(lines[head:], head) if line.startswith("## 8"))
    doctored = "".join(lines[:head] + lines[end:])
    bad = doctored_cfg(cfg, mirror_canon(docs_root, tmp_path / "missing", doctored))
    with pytest.raises(ValueError, match=r"\[6\]"):
        canon_docs.load_deception_levers(bad)


def test_an_unregistered_seventh_lever_is_a_stop(
    cfg: dict, affordance_text: str, docs_root: Path, tmp_path
) -> None:
    """A catalog that grew is a re-adjudication, not a quote of the six it knows."""
    doctored = affordance_text.replace(
        "\n## 8. ", "\n7. **Something new** — planted by the E-1 pins.\n\n## 8. "
    )
    assert doctored != affordance_text, "fixture: the seventh lever was not planted"
    bad = doctored_cfg(cfg, mirror_canon(docs_root, tmp_path / "seventh", doctored))
    with pytest.raises(ValueError, match="LEVER_HEAD_KEYWORDS"):
        canon_docs.load_deception_levers(bad)


def test_a_missing_section_7_is_a_stop(
    cfg: dict, affordance_text: str, docs_root: Path, tmp_path
) -> None:
    doctored = affordance_text.replace("## 7. The deception catalog", "## 7x. Gone")
    bad = doctored_cfg(cfg, mirror_canon(docs_root, tmp_path / "nosection", doctored))
    with pytest.raises(ValueError, match="## 7"):
        canon_docs.load_deception_levers(bad)


def test_the_policy_sentence_is_quoted_from_section_10(cfg: dict, affordance_text: str) -> None:
    policy = canon_docs.load_deception_policy(cfg)
    assert "declared" in policy.text and "never an accident" in policy.text, (
        f"§10's deception policy came back as {policy.text!r}"
    )
    flowed = " ".join(affordance_text.split())
    assert policy.text in flowed, (
        "the policy sentence is not a verbatim (whitespace-normalized) slice of the canon — "
        "the prompts state it AS canon, so it is quoted or nothing"
    )
    assert policy.source.startswith(f"{Path(canon_docs.AFFORDANCE_MD).name}:L"), (
        f"the quote must carry its canon line: {policy.source!r}"
    )


# --------------------------------------------------------------------------- #
# 2 — the fold
# --------------------------------------------------------------------------- #


def test_the_catalog_is_the_levers_keywords() -> None:
    keyworded = [lever for lever in s1_spec.LEVER_GROUNDING if lever.keyword is not None]
    assert s1_spec.DECEPTION_CATALOG == tuple(lever.keyword for lever in keyworded)
    assert len(s1_spec.LEVER_GROUNDING) == 6, (
        "the grounding table must carry all six signed levers, keywordless one included"
    )
    assert len(s1_spec.DECEPTION_CATALOG) == 5, (
        f"five of the six levers have a keyword; §7.5 has none BY DESIGN (a bare 'hidden' "
        f"keyword would kill honest specs — s1_spec's catalog header). Got "
        f"{s1_spec.DECEPTION_CATALOG}"
    )
    keywordless = [lever for lever in s1_spec.LEVER_GROUNDING if lever.keyword is None]
    assert [lever.number for lever in keywordless] == [5], (
        f"§7.5 is the one uncatalogued lever; the keywordless ones are "
        f"{[lever.number for lever in keywordless]}"
    )


@pytest.mark.parametrize("name", PRE_E1_CATALOG)
def test_every_pre_e1_keyword_still_detects(name: str) -> None:
    """NOTHING previously matchable became unmatchable."""
    assert detect_levers(name) == [EXPECTED_FOLD[name]], (
        f"{name!r} detected {detect_levers(name)} — it used to detect a lever, and the "
        f"re-grounding may change WHICH lever it names, never WHETHER it is seen"
    )


@pytest.mark.parametrize("name", OBSERVED_ON_DISK)
def test_every_observed_name_folds_to_exactly_one_lever(name: str) -> None:
    folded = detect_levers(name)
    assert len(folded) == 1 and folded[0] in s1_spec.DECEPTION_CATALOG, (
        f"the on-disk name {name!r} folds to {folded}, not to exactly one catalog lever"
    )
    assert s1_spec.canonical_lever(name) == folded[0], (
        f"the registry and the reader disagree about {name!r}: "
        f"{s1_spec.canonical_lever(name)!r} vs {folded[0]!r}"
    )


def test_inflections_and_separators_still_fold() -> None:
    for text, expected in (
        ("look alike", "look-alike"),
        ("look-alikes", "look-alike"),
        ("lookalike", "look-alike"),
        ("decoys", "decoy"),
        ("disguised", "look-alike"),
        ("CAMOUFLAGE", "palette overload"),
        ("palette  overloading", "palette overload"),
    ):
        assert detect_levers(text) == [expected], (
            f"{text!r} folded to {detect_levers(text)}, expected [{expected!r}]"
        )


def test_an_off_catalog_word_folds_to_nothing() -> None:
    assert detect_levers("an ornamental inert twin") == []
    assert s1_spec.canonical_lever("ornamental") is None


def test_canonical_lever_is_exact_membership_not_a_substring_search() -> None:
    """The alias-set gate `_validate_uncorroborated` uses, and why it is not a fold."""
    assert s1_spec.canonical_lever("the decoy thing is fine") is None, (
        "canonical_lever answers 'is this one of the catalog's spellings?' — prose that "
        "merely CONTAINS a keyword is not a lever name, and accepting it would loosen the "
        "exact-membership bar the record check has always applied"
    )
    assert detect_levers("the decoy thing is fine") == ["decoy"], (
        "detect_levers is the substring reader and must still see the keyword in prose"
    )


def test_the_fold_table_and_the_matcher_cover_the_same_spellings() -> None:
    assert set(s1_spec.LEVER_SPELLINGS) == set(PRE_E1_CATALOG), (
        f"the matchable surface moved: {sorted(set(s1_spec.LEVER_SPELLINGS) ^ set(PRE_E1_CATALOG))}"
        f" differ between the pre-E-1 catalog and today's spellings. Adding one is a "
        f"vocabulary decision; dropping one breaks a shipped spec's declaration"
    )
    assert {spelling for _lever, spelling, _p in s1_spec._DECEPTION_PATTERNS} == set(
        s1_spec.LEVER_SPELLINGS
    ), "a spelling with no pattern cannot be detected, and the two tables must agree"


def test_declaring_any_spelling_declares_the_lever() -> None:
    """K4's substring rule: "camouflage" declares the palette-overloading lever."""
    levels = [{"sketch": "two pads share one index under a palette overload"}]
    assert s1_spec._deception_rule(levels, ["camouflage: the grey wall reads as letterbox"]) == [], (
        "a spec declaring 'camouflage' must count as declaring §7.2 — the sketch's "
        "'palette overload' sighting is the same lever under the other name"
    )
    kills = s1_spec._deception_rule(levels, [])
    assert [kill["rule"] for kill in kills] == ["undeclared-deception"], (
        f"with nothing declared the same sketch must still kill: {kills}"
    )
    assert "palette overload" in kills[0]["detail"], (
        f"the kill must name the lever to declare, not only the word found: {kills[0]['detail']!r}"
    )


def test_one_lever_under_two_names_in_one_sketch_is_one_kill() -> None:
    levels = [{"sketch": "a camouflage grey wall AND a palette overload on the same index"}]
    kills = s1_spec._deception_rule(levels, [])
    assert len(kills) == 1, (
        f"two spellings of §7.2 in one sketch is ONE undeclared lever; got {len(kills)} kills: "
        f"{[kill['detail'] for kill in kills]}"
    )


def test_two_spellings_of_one_lever_declare_one_lever_for_the_tier_count() -> None:
    assert s1_spec._declared_levers(["camouflage", "palette overload"]) == ["palette overload"], (
        "the tier ceiling counts LEVERS: 'camouflage' and 'palette overload' are one lever "
        f"twice, and got {s1_spec._declared_levers(['camouflage', 'palette overload'])}"
    )
    assert s1_spec._declared_levers(["decoy", "false tell"]) == ["decoy", "lying display"], (
        "two different levers still count two"
    )
    assert s1_spec._declared_levers(["a schedule the player has to learn"]) == [
        "a schedule the player has to learn"
    ], "an uncatalogued entry still counts as a lever of its own (§7.5 has no keyword)"


# --------------------------------------------------------------------------- #
# 3 — the measured before/after demonstration (read-only corpus)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("path", "names", "levers_after"),
    [
        # PIN UPDATE 2026-10-06 (with the frozen repoint above): the echo
        # exhibit now carries revival #3's rounds too — 5 names, and only
        # `false tell` renames (onto lying display), so the fold lands on 4.
        (ECHO_HISTORY, 5, 4),
        (SEAMLOCK_HISTORY, 6, 5),
        (ROVER_HISTORY, 2, 2),
    ],
    ids=["echo-game", "seamlock", "key-strip-rover"],
)
def test_the_real_lever_histories_refold(path: Path, names: int, levers_after: int) -> None:
    """The contract's own exhibits, re-folded under the re-grounded catalog.

    MEASURED, and one of them corrects the contract: seamlock's six names fold to
    FIVE levers, not the "≤4" the blind-lane sketch predicts — only camouflage
    merges into palette overload, and `false tell` renames onto a `lying display`
    that game never named. The echo game's four fold to three, as predicted.
    """
    history = _history(path)
    recorded = _recorded_names(history)
    assert len(recorded) == names, (
        f"{path.parent.name} recorded {len(recorded)} distinct names {recorded}, not the "
        f"{names} this pin measures"
    )
    for name in recorded:
        assert s1_spec.canonical_lever(name) is not None, (
            f"{name!r} was written to disk by a real audit round and no longer folds — every "
            f"recorded name must stay readable"
        )
    folded = _folded(recorded)
    assert len(folded) == levers_after, (
        f"{path.parent.name}: {recorded} folds to {folded} ({len(folded)} levers), not "
        f"{levers_after}"
    )
    assert set(folded) <= set(s1_spec.DECEPTION_CATALOG), (
        f"the fold left {sorted(set(folded) - set(s1_spec.DECEPTION_CATALOG))} outside the "
        f"catalog"
    )


def test_the_echo_games_round_to_round_churn_shrinks() -> None:
    """The instability this contract exists for, counted per round.

    Five rounds of one game produced four names for three levers. The fold cannot
    make an audit see the same thing twice, but it does stop two readings of one
    lever from diffing as two findings.
    """
    history = _history(ECHO_HISTORY)
    per_round = [_folded(sorted(set(entry["detected"]))) for entry in history]
    # PIN UPDATE 2026-10-06: the frozen exhibit carries revival #3's lifted
    # rounds (6-9) after E-1's measured five; the round-indexed claims below
    # are about rounds 3 and 4 and stand unchanged.
    assert len(per_round) == 9, f"the frozen echo history is 9 rounds, got {len(per_round)}"
    assert per_round[2] == ["look-alike", "lying display"], (
        f"round 3 recorded ['false tell', 'look-alike'] and must now read as look-alike + "
        f"lying display; got {per_round[2]}"
    )
    assert per_round[3] == ["lying display", "palette overload"], (
        f"round 4 recorded false tell AND lying display — one lever twice — and must fold to "
        f"two levers, not three; got {per_round[3]}"
    )


# --------------------------------------------------------------------------- #
# 4 — prompt sync (one source, three prompts)
# --------------------------------------------------------------------------- #


def test_all_three_prompts_carry_every_lever_verbatim(prompts: dict, levers: dict) -> None:
    for name, prompt in prompts.items():
        for number, lever in levers.items():
            assert lever.text in prompt, (
                f"the {name} does not carry lever {number} ({lever.title!r}) verbatim — the "
                f"three prompts quote ONE loader precisely so the writer, the implementer and "
                f"the blind audit cannot mean three different things by one keyword"
            )


def test_all_three_prompts_name_every_catalog_keyword(prompts: dict) -> None:
    for name, prompt in prompts.items():
        for keyword in s1_spec.DECEPTION_CATALOG:
            assert keyword in prompt, f"the {name} never names the {keyword!r} lever"


def test_all_three_prompts_still_carry_the_historic_spellings(prompts: dict) -> None:
    """A writer who knows the word "camouflage" must be able to find its lever."""
    for name, prompt in prompts.items():
        for spelling in PRE_E1_CATALOG:
            assert spelling in prompt, (
                f"the {name} never mentions {spelling!r} — it is a spelling the matcher still "
                f"folds, so a reader who reaches for it has to be told which lever it is"
            )


def test_a_sentinel_in_the_canon_reaches_all_three_prompts(sentinel_prompts: dict) -> None:
    """The drift pin: mutate the canon, all three prompts move (or one is hand-copied)."""
    for name, prompt in sentinel_prompts.items():
        assert SENTINEL in prompt, (
            f"the {name} did not change when the canon did — it is carrying a hand-copied "
            f"lever list, which is exactly the drift PROMPT-SYNC exists to prevent"
        )


def test_the_audit_prompt_quotes_the_section_10_policy(cfg: dict, prompts: dict) -> None:
    policy = canon_docs.load_deception_policy(cfg)
    prompt = prompts["s3 blind audit prompt"]
    assert policy.text in prompt, (
        "the look-alike inventory states §10's policy as canon; it must be the canon's own "
        "sentence, not a retyped paraphrase"
    )
    assert s3_verify.LOOKALIKE_POLICY_SLOT not in prompt, (
        "the policy slot reached the prompt unfilled — the constant carries a literal json "
        "example, so the slot is filled by replace and a missed call fails silently"
    )


def test_the_keywordless_lever_is_quoted_and_labelled(prompts: dict, levers: dict) -> None:
    """§7.5 ships WITH the reason it has no keyword, in all three prompts."""
    for name, prompt in prompts.items():
        assert levers[5].text in prompt, f"the {name} drops §7.5, which is canon"
        at = prompt.index(levers[5].text)
        tail = prompt[at : at + len(levers[5].text) + 400]
        assert "NO catalog keyword" in tail, (
            f"the {name} quotes §7.5 without saying it has no keyword — a reader cannot tell "
            f"a deliberate omission from an oversight"
        )


def test_the_prompts_are_byte_identical_across_builds(cfg: dict, tmp_path) -> None:
    """Deterministic: the lever block is generated from canon on every build."""
    first = _three_prompts(cfg, tmp_path)
    second = _three_prompts(cfg, tmp_path)
    for name in first:
        assert first[name] == second[name], f"two builds of the {name} differ"


def test_the_writer_prompt_section_follows_the_lint_surface(cfg: dict) -> None:
    """The deception section documents the words the lint note's rule matches."""
    prompt = s1_spec.build_writer_prompt(cfg, _idea("e1-0002"))
    note = prompt.index(s1_spec.UNDECLARED_DECEPTION_NOTE_HEADER)
    section = prompt.index(s1_spec.DECEPTION_SECTION_HEADER)
    assert note < section, (
        "the `undeclared-deception` note states the scanner's MECHANICS and this section "
        "defines the levers it matches, so the definitions follow the rule"
    )


# --------------------------------------------------------------------------- #
# 5 — compatibility with everything already on disk
# --------------------------------------------------------------------------- #


def _corpus_reports() -> list[Path]:
    return sorted(CORPUS.glob("*/*/worker.verifier-report.json"))


def test_every_shipped_verifier_report_still_validates() -> None:
    reports = _corpus_reports()
    assert len(reports) >= 14, f"only {len(reports)} shipped reports found under {CORPUS}"
    for path in reports:
        validate_report(json.loads(path.read_text(encoding="utf-8")))


def test_the_shipped_reports_really_do_carry_historic_lever_names() -> None:
    """The compatibility pin above is only worth having if the risk is real."""
    historic = {
        name
        for path in _corpus_reports()
        for name in re.findall(r'"lever":\s*"([^"]+)"', path.read_text(encoding="utf-8"))
        if name not in s1_spec.DECEPTION_CATALOG
    }
    assert historic, (
        "no shipped report names a pre-E-1 spelling any more — if that is true the "
        "alias-set acceptance in `_validate_uncorroborated` is dead code and should be "
        "re-adjudicated rather than left in"
    )
    for name in historic:
        assert s1_spec.canonical_lever(name) is not None, (
            f"a shipped report records the lever {name!r} and the validator can no longer "
            f"read it — that report would stop validating"
        )


def test_an_uncorroborated_record_takes_a_historic_spelling() -> None:
    diff = {
        s3_verify.UNCORROBORATED_KEY: [
            {"lever": "camouflage", "note": s3_verify.FIRST_SIGHTING_NOTE},
            {"lever": "false tell", "note": s3_verify.FIRST_SIGHTING_NOTE},
            {"lever": "palette overload", "note": s3_verify.FIRST_SIGHTING_NOTE},
        ]
    }
    s3_verify._validate_uncorroborated(diff[s3_verify.UNCORROBORATED_KEY], "report.diff.rec")
    with pytest.raises(ValueError, match="catalog keyword"):
        s3_verify._validate_uncorroborated(
            [{"lever": "a word nobody signed", "note": "x"}], "report.diff.rec"
        )


def test_every_shipped_spec_still_declares_what_it_declared() -> None:
    specs = sorted(CORPUS.glob("*/*/spec.yaml"))
    assert len(specs) >= 15, f"only {len(specs)} shipped specs found under {CORPUS}"
    declaring = 0
    for path in specs:
        game = yaml.safe_load(path.read_text(encoding="utf-8"))["game"]
        deceptions = (game.get("knobs") or {}).get("deceptions")
        entries = deceptions if isinstance(deceptions, list) else None
        assert s1_spec._deception_rule(game.get("levels") or [], entries) == [], (
            f"{path} now lints with an undeclared-deception kill it did not have — a shipped "
            f"spec's free-text declaration must keep declaring under the containment rule"
        )
        if entries:
            declared = s3_verify._declared_deceptions(game)
            assert declared, f"{path} declares {entries} and the diff now reads it as nothing"
            assert set(declared) <= set(s1_spec.DECEPTION_CATALOG), (
                f"{path}'s declaration folded to {declared}, which is not all catalog levers"
            )
            declaring += 1
    assert declaring >= 6, (
        f"only {declaring} shipped specs declare a deception at all — the compatibility pin "
        f"needs real declarations to be about"
    )


def test_the_lever_history_sidecars_still_read() -> None:
    for path in sorted(CORPUS.glob("*/*/worker.lever-history.json")):
        history = s3_verify.read_lever_history(path)
        assert history, f"{path} read back empty"
        # Pre-E-1 rounds recorded pre-E-1 spellings; the corroboration set is the
        # union of what the rounds SAID, verbatim, and this contract does not
        # rewrite it (scope guard 6: the corroboration machinery is untouched).
        assert s3_verify.corroborated_levers(history) == frozenset(
            name for entry in history for name in entry["detected"]
        )


# --------------------------------------------------------------------------- #
# 6 — the two defect fixes
# --------------------------------------------------------------------------- #


def test_the_audit_prompt_tells_the_truth_about_enforcement(prompts: dict) -> None:
    """Defect #1: the header promised "discarded" while validate_claims RAISES."""
    prompt = prompts["s3 blind audit prompt"]
    assert "an off-list word is discarded" not in prompt, (
        "the prompt still promises an off-list keyword is quietly discarded; the pipeline "
        "rejects the whole reply (`validate_claims` raises) and spends the one corrective turn"
    )
    paragraph = next(
        block
        for block in prompt.split("\n\n")
        if "CANNOT fold" in block or "cannot fold" in block
    )
    for phrase in ("discarded", "corrective turn"):
        assert phrase in paragraph, (
            f"the enforcement paragraph does not say {phrase!r}: {paragraph!r}"
        )


def test_an_off_catalog_lever_really_does_reject_the_reply() -> None:
    """…and the behaviour the sentence now describes is the behaviour."""
    claims = {
        "terms": [],
        "dead_code": [],
        "deceptions": [{"lever": "vibe-based misdirection", "evidence": [{"path": "g.py",
                                                                          "line": 4}]}],
        "enforcement": [],
        "notes": "",
    }
    with pytest.raises(ValueError, match="matches no catalog keyword"):
        s3_verify.validate_claims(claims, {"move.grid"}, ("reset",))
    claims["deceptions"][0]["lever"] = "camouflage"
    s3_verify.validate_claims(claims, {"move.grid"}, ("reset",))


def test_the_reconciled_entry_names_the_path_that_wrote_it() -> None:
    """Defect #2: "(round_cap)" was hardcoded onto entries the early path wrote."""
    assert "{via}" in orch.RECONCILED_DECEPTION, (
        "the reconciled-deception template still hardcodes its provenance"
    )
    early = orch.RECONCILED_DECEPTION.format(lever="decoy", via=orch.RECONCILED_VIA_EARLY)
    capped = orch.RECONCILED_DECEPTION.format(lever="decoy", via=orch.RECONCILED_VIA_ROUND_CAP)
    assert early != capped and orch.RECONCILED_VIA_EARLY in early, (
        f"the two paths must be distinguishable on the record: {early!r} vs {capped!r}"
    )
    # The declaration still has to HOLD: the lever's own name leads the entry, so
    # squashed containment finds it whichever path wrote it.
    for entry in (early, capped):
        assert detect_levers(entry) == ["decoy"], (
            f"the reconciled entry {entry!r} does not declare the lever it names"
        )


def test_both_reconciliation_paths_pass_their_own_provenance() -> None:
    """Read off the call sites: a path that does not name itself is the defect."""
    import inspect

    source = inspect.getsource(orch)
    calls = {
        match.strip()
        for match in re.findall(r"_reconcile_declarations\(ctx, reasons,?\s*([^)]*)\)", source)
    }
    assert calls == {"via=RECONCILED_VIA_ROUND_CAP", "via=RECONCILED_VIA_EARLY"}, (
        f"both reconciliation call sites must name their own path (the round cap's and "
        f"P-A.1's early one); the call sites pass {sorted(calls)}"
    )
