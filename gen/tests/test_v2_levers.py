"""Blind pins for FROZEN CONTRACT E-1 — lever semantics sync (Q-1 reframed).

Run: .venv/bin/python -m pytest gen/tests/test_v2_levers.py -v

Written from `docs/v2/contracts/E-1-lever-semantics-sync.md` ALONE, Addendum 1
included — this is the BLIND lane, and the implementer's own battery
(`gen/tests/test_e1_levers.py`) was not read.  Every assertion message below
cites the contract sentence it is holding, so a red test says which clause of
the contract stopped being true rather than which line of code moved.

WHAT THIS FILE WAS ALLOWED TO READ, AND DID.  The contract's blind brief names
the surfaces it creates (`canon_docs.load_deception_levers`,
`s1_spec.DECEPTION_CATALOG`, the `_LEVER_ALIASES` alias machinery,
`s3_verify.detect_levers` / `validate_claims` / `DECEPTION_HEADER` /
`_validate_uncorroborated`, `orchestrator.RECONCILED_DECEPTION`), so the
shipped stage modules were read to find those seams and to learn how to DRIVE
them.  The EXPECTATIONS are the contract's: the six levers and their names come
from §The reframe, the fold from §Work 2, the counts from §Blind K2 as
Addendum 1 corrects them, and the two defect fixes from §Work 4/5.  Where the
contract names a lever but not a keyword the pin is on the lever NUMBER and on
the equivalence CLASS of spellings, never on the implementer's choice of short
keyword (Addendum 1 ratifies D4 short-form keywords as the implementer's call).

READ-ONLY FIXTURES.  §Blind K2 says to compute the re-fold "from the real
lever-history sidecars read-only — they are the fixtures", and §Work 2 says the
shipped corpus reports must keep validating.  This file therefore reads, and
only reads, `out/corpus/*/*/worker.lever-history.json`,
`out/corpus/*/*/worker.verifier-report.json` and `out/corpus/*/*/spec.yaml`,
plus the vendored canon.  `test_zz_*` re-hashes every one of those files at the
end of the module and fails if any byte moved.  Every mutation this file makes
happens in `tmp_path`; nothing is ever written under `out/`, `games/` or
`canon/`, no driver runs and nothing touches the network.

A PROMISED SURFACE THAT IS MISSING IS A FAILURE, NEVER A SKIP (`_surface`
below): a contract that promises a loader and ships none must turn this file
red, not green-with-a-skip.  There are no skips in this module at all.

AMBIGUITIES RESOLVED, REPORTED RATHER THAN PAPERED OVER

  a. §Blind K3 "all three prompts".  Read as the three REAL prompts a session
     is handed — `s1_spec.build_writer_prompt`, `s2_implement.build_payload`
     and `s3_verify.build_verifier_prompt` — not as three section helpers.  A
     section builder nothing interpolates would satisfy the weaker reading and
     leave a prompt un-synced, which is the whole defect E-1 exists to close.
  b. §Work 1's "the §10 policy sentence rides along WHERE THE HEADER ALREADY
     QUOTES IT".  That clause scopes the policy to the one prompt that quoted
     it before E-1, so `test_k1_policy_*` pins it in the verifier prompt and
     does NOT demand it of the writer prompt or the implementer payload.
  c. §Work 3's "S1's UNDECLARED_DECEPTION_NOTE consumes the SAME loader".
     Addendum 1 ratifies D6 — a NEW S1 section carries the quoted levers and
     the note keeps its keyword list — so the pin is on the WRITER PROMPT
     carrying every definition (a) plus the note still naming exactly the
     catalog's keywords, not on the note itself quoting canon prose.
  d. §Blind K2's "the echo game's four distinct round-names" / "seamlock's
     six".  Taken as the distinct names across the WHOLE sidecar (the union of
     every round's `detected`), which is the reading that reproduces the
     contract's own 4-and-6 census; the round counts are pinned beside them so
     a fixture that gains a round cannot quietly change the measurement.
  e. §Work 2's "or accept the alias set; your call, say which".  The call is
     the implementer's, so these pins hold the INVARIANT both calls share
     (every historic spelling keeps validating) AND the stricter property
     Addendum 1 ratified for the alias set (prose merely CONTAINING a keyword
     is still refused) — see `test_k4_recorded_lever_*`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
import yaml

from gen import canon_docs, s1_spec, s2_implement, s3_verify
from gen import orchestrator as orch
from gen.config import load_config

# The b005 autonomy rig's DATA fixtures are borrowed rather than copied (the
# house idiom): `SPEC_TEXT` is the lint-clean spec every reconciliation test in
# this repo amends, and `IDEA`/`KILL_BUDGETS` are its tier carriers.  No logic
# is imported — the `SlotContext` below is built here, from the orchestrator's
# own public dataclass.
from gen.tests import test_b005_autonomy as b005

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"
SPEC_FIXTURE = TESTS_DIR / "fixtures" / "specs" / "good-spec.yaml"

CONTRACT = "docs/v2/contracts/E-1-lever-semantics-sync.md"
#: The vendored canon snapshot (contract P-2) is the hermetic docs root: it is
#: tracked in this repo, so these pins do not need a duckWM sibling.  §Hard
#: rules: "canon/ is READ-ONLY (the loader reads it; nothing edits it)".
CONFIG_PATH = "config/template.yaml"
#: The historical batch config, for the stages whose prompts read run metadata.
BATCH_CONFIG = "config/b001-pilot.yaml"
AFFORDANCE_REL = "design/objects/affordance-language.md"

# --- the contract's own ground truth ----------------------------------------
#
# §The reframe, "The canon's six": the levers as the contract numbers and names
# them.  §7.5 is in the list because the catalog EXCLUDES it, which is the fact
# Addendum 1's SHAPE ruling turns on.
CANON_SIX: dict[int, str] = {
    1: "look-alike splits",
    2: "palette overloading",
    3: "decoy/dead actions",
    4: "lying/desynced displays",
    5: "invisible load-bearing state",
    6: "retrospective punishment",
}
#: The part of each contract name that the canon's own bold head must still
#: carry.  The canon head wraps alternative spellings around it ("Lying/desynced
#: displays"), so the needle is the stem rather than the whole phrase.
TITLE_NEEDLES: dict[int, str] = {
    1: "look-alike",
    2: "palette overload",
    3: "decoy",
    4: "lying",
    5: "invisible load-bearing",
    6: "retrospective punishment",
}
#: §Addendum 1 THE SHAPE: "six levers, FIVE keywords — §7.5 … stays
#: deliberately keywordless".
LEVER_COUNT = 6
KEYWORD_COUNT = 5
KEYWORDLESS_LEVER = 5

#: §The reframe, "Observed on disk (union of every sighting ever)".
SIGHTED: tuple[str, ...] = (
    "camouflage",
    "decoy",
    "false tell",
    "look-alike",
    "lying display",
    "palette overload",
    "retrospective punishment",
)
#: §The reframe, "never sighted: lookalike, mimic, disguise, fake tell".
NEVER_SIGHTED: tuple[str, ...] = ("lookalike", "mimic", "disguise", "fake tell")
#: §The reframe: the pre-E-1 catalog was "a closed 11-keyword tuple", and the
#: sighted seven are "7 of the 11 keywords" — so these two lists ARE that tuple.
PRE_E1_KEYWORDS: tuple[str, ...] = SIGHTED + NEVER_SIGHTED
PRE_E1_KEYWORD_COUNT = 11

#: §Work 2's fold, expressed as the canon LEVER NUMBER each name lands on:
#: "lookalike->look-alike; camouflage + palette overload->palette overloading's
#: key; false tell + fake tell + lying display->lying displays' key; mimic +
#: disguise->look-alike's key; decoy + retrospective punishment keep their
#: lever."
FOLD_TO_LEVER: dict[str, int] = {
    "look-alike": 1,
    "lookalike": 1,
    "mimic": 1,
    "disguise": 1,
    "palette overload": 2,
    "camouflage": 2,
    "decoy": 3,
    "lying display": 4,
    "false tell": 4,
    "fake tell": 4,
    "retrospective punishment": 6,
}

#: §Blind K2 as Addendum 1 corrects it: (batch, slug, rounds, distinct names,
#: distinct levers).  "echo game 4 names -> 3 levers (as written); seamlock
#: 6 names -> **5** levers, NOT <=4".
SIDECAR_REL = "worker.lever-history.json"
# LEAD REPOINT + PIN UPDATE 2026-10-06 (post-wave, documented): the echo slot
# is parked-but-LIFTABLE (contract E-5) and revival #3's lifted rounds grew the
# live sidecar 5 rounds/4 names → 9/5 (the new name `retrospective punishment`
# is itself a signed lever, so the fold lands on 4). The exhibit bytes are
# frozen in gen/tests/fixtures/ — a live out/ path cannot serve a pin on a
# pipeline whose slots resume. The K2 CLAIM (every real recorded name folds,
# churn shrinks) is unchanged; only the measured figures moved with the file.
ECHO_SIDECAR = ("b005r2-auto", "two-keys-one-echo", 9, 5, 4)
ECHO_FROZEN = (
    Path(__file__).resolve().parent
    / "fixtures" / "two-keys-one-echo-lever-history-frozen-2026-10-06.json"
)
SEAMLOCK_SIDECAR = ("g20261001-1", "seamlock", 8, 6, 5)

#: §Work 5: "the entry should name the path that wrote it (template gains a
#: {via} or two constants)".  The two paths the contract names.
VIA_SLOT = "{via}"
EARLY_PATH_WORDS = ("early", "reconcile_early")
CAP_PATH_WORDS = ("round_cap", "round cap")

#: §Work 4's truthfulness test, as word classes rather than as one sentence a
#: correct rewrite might phrase differently.
_DROP_VERB_RE = re.compile(
    r"\b(?:discard(?:ed|s)?|dropp?(?:ed|s)?|ignor(?:ed|es))\b", re.IGNORECASE
)
_NEGATOR_RE = re.compile(r"\b(?:not|never|no)\b", re.IGNORECASE)
_FAILURE_RE = re.compile(
    r"\b(?:fails?|failure|reject(?:s|ed)?|invalid(?:ates?|ated)?)\b", re.IGNORECASE
)
_REPLY_RE = re.compile(r"\breply\b", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_CORRECTIVE_TURN_RE = re.compile(r"corrective turn", re.IGNORECASE)


def _squash(text: str) -> str:
    """Lowercase, separator-free form — the contract's "case and punctuation are
    stripped" declaration rule, written here so the pins do not borrow it."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _surface(module: Any, name: str, what: str) -> Any:
    """The named attribute, or a LOUD failure naming the contract clause.

    §Hard rules give the blind lane one file and no handback, so a promised
    surface that never landed has to be a red test with the promise quoted in
    it — never a skip, which would read as "nothing to measure here".
    """
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(
            f"{module.__name__} exposes no {name!r} — {CONTRACT} {what}. Every pin that "
            f"depends on it is therefore unmeasurable, which is a contract failure and "
            f"not a reason to skip"
        )
    return value


# --- fixtures ---------------------------------------------------------------


@pytest.fixture(scope="session")
def cfg() -> dict:
    """The vendored-canon config every loader pin reads (§Hard rules: READ-ONLY)."""
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="session")
def batch_cfg() -> dict:
    """A shipped batch config, for the prompt builders that read run metadata."""
    return load_config(BATCH_CONFIG)


@pytest.fixture(scope="session")
def canon_path(cfg: dict) -> Path:
    """`affordance-language.md` itself — the file §Work 1 quotes VERBATIM."""
    path = Path(cfg["duckwm_docs"]) / AFFORDANCE_REL
    assert path.is_file(), (
        f"{CONTRACT} §Work 1 parses {AFFORDANCE_REL} §7, and the config's canon root "
        f"does not carry it: {path}"
    )
    return path


@pytest.fixture(scope="session")
def canon_text(canon_path: Path) -> str:
    return canon_path.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def load_levers():
    """`canon_docs.load_deception_levers` — §Work 1's loader."""
    return _surface(
        canon_docs,
        "load_deception_levers",
        "§Work 1 promises `canon_docs.load_deception_levers(cfg)`, which parses "
        "affordance-language.md §7 into the six signed levers",
    )


@pytest.fixture(scope="session")
def levers(load_levers, cfg: dict) -> dict:
    """The loader's mapping. §Blind K1: "the loader: six levers"."""
    return load_levers(cfg)


@pytest.fixture(scope="session")
def catalog() -> tuple[str, ...]:
    """`s1_spec.DECEPTION_CATALOG` — §Work 2's re-grounded catalog."""
    return tuple(
        _surface(
            s1_spec,
            "DECEPTION_CATALOG",
            "§Work 2 re-grounds DECEPTION_CATALOG on the six levers' keywords",
        )
    )


@pytest.fixture(scope="session")
def detect():
    """`s3_verify.detect_levers` — the matcher §The reframe names (:1194-1212)."""
    return _surface(
        s3_verify,
        "detect_levers",
        "§The reframe names `s3_verify.detect_levers` as the matcher on the "
        "detect side, and §Blind K2 pins that every observed name still detects",
    )


@pytest.fixture(scope="session")
def writer_prompt(batch_cfg: dict) -> str:
    """Prompt 1 of 3: the spec writer's, built for real (§Blind K3)."""
    return s1_spec.build_writer_prompt(batch_cfg, b005.IDEA)


@pytest.fixture(scope="session")
def payload(batch_cfg: dict, tmp_path_factory: pytest.TempPathFactory) -> str:
    """Prompt 2 of 3: the implementer payload, over a throwaway spec dir."""
    spec_dir = tmp_path_factory.mktemp("e1-blind-spec")
    shutil.copyfile(SPEC_FIXTURE, spec_dir / "spec.yaml")
    (spec_dir / "spec.md").write_text(
        "# Fixture Game\n\nShort non-empty prose for the E-1 blind prompt pins.\n",
        encoding="utf-8",
    )
    text, _report = s2_implement.build_payload(spec_dir, batch_cfg)
    return text


@pytest.fixture(scope="session")
def verifier_prompt(batch_cfg: dict, tmp_path_factory: pytest.TempPathFactory) -> str:
    """Prompt 3 of 3: the blind auditor's, over a staged copy of the toy worker."""
    game_cls, solver_cls = s3_verify.load_worker_classes(TOY_WORKER)
    cap = s3_verify.capture(game_cls, solver_cls)
    staged = tmp_path_factory.mktemp("e1-blind-staged") / "worker"
    s3_verify.stage_worker_copy(TOY_WORKER, staged)
    return s3_verify.build_verifier_prompt(batch_cfg, cap, staged)


@pytest.fixture(scope="session")
def prompts(writer_prompt: str, payload: str, verifier_prompt: str) -> dict[str, str]:
    """The three prompts §Blind K3 says must carry each definition verbatim."""
    return {"writer": writer_prompt, "payload": payload, "verifier": verifier_prompt}


@pytest.fixture
def canon_clone(cfg: dict, tmp_path: Path) -> tuple[dict, Path]:
    """A WRITABLE copy of the canon root, and the affordance file inside it.

    The drift pin needs the canon text to move, and §Hard rules forbid touching
    the real one; the loader takes a `cfg` mapping, so a copied root is all it
    takes to ask "does the prompt follow the canon?".
    """
    root = tmp_path / "canon"
    shutil.copytree(Path(cfg["duckwm_docs"]), root)
    return {"duckwm_docs": root}, root / AFFORDANCE_REL


# --- the read-only fixture ledger -------------------------------------------
#
# Captured at IMPORT time, i.e. before any test in this module runs, so the
# final guard compares against bytes this file cannot have touched.


def _corpus_files(pattern: str) -> list[Path]:
    return sorted((REPO_ROOT / "out" / "corpus").glob(pattern))


READ_ONLY_FILES: tuple[Path, ...] = (
    *_corpus_files(f"*/*/{SIDECAR_REL}"),
    *_corpus_files("*/*/worker.verifier-report.json"),
    *_corpus_files("*/*/spec.yaml"),
    REPO_ROOT / "canon" / AFFORDANCE_REL,
)
READ_ONLY_DIGESTS: dict[Path, str] = {
    path: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in READ_ONLY_FILES
    if path.is_file()
}


def _sidecar(batch: str, slug: str) -> list[dict]:
    """One real lever-history sidecar, read-only (§Blind K2: "the fixtures")."""
    path = REPO_ROOT / "out" / "corpus" / batch / slug / SIDECAR_REL
    # The one liftable exhibit reads its FROZEN bytes (see ECHO_SIDECAR's note).
    if (batch, slug) == ("b005r2-auto", "two-keys-one-echo"):
        path = ECHO_FROZEN
    if not path.is_file():
        pytest.fail(
            f"{CONTRACT} §Blind K2 computes its bounds "
            f"'from the real lever-history sidecars read-only — they are the fixtures', "
            f"and this one is not on disk: {path}"
        )
    history = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(history, list) and history, (
        f"{path} is not a non-empty list of audit rounds, so §Blind K2's "
        f"'the echo game's four distinct round-names' cannot be computed from it"
    )
    return history


def _names(history: list[dict]) -> list[str]:
    """Every distinct lever name the sidecar ever recorded, sorted."""
    found: set[str] = set()
    for position, round_ in enumerate(history):
        detected = round_.get("detected")
        assert isinstance(detected, list), (
            f"lever-history round {position} has no 'detected' list ({round_!r}) — "
            f"{CONTRACT} §Blind K2 reads the recorded names off these rounds"
        )
        found.update(detected)
    return sorted(found)


# --- K1: the loader ---------------------------------------------------------


def test_k1_the_loader_quotes_the_canons_six_signed_levers(levers: dict) -> None:
    """§Blind K1 "six levers"; §The reframe "the canon's SIX signed levers"."""
    assert isinstance(levers, dict), (
        f"{CONTRACT} §Work 1's loader parses §7 'into the six signed levers'; it "
        f"returned a {type(levers).__name__}"
    )
    assert sorted(levers) == sorted(CANON_SIX), (
        f"{CONTRACT} §The reframe lists the canon's six by number: {CANON_SIX}. The "
        f"loader returned {sorted(levers)}"
    )
    for number, needle in TITLE_NEEDLES.items():
        entry = levers[number]
        title = getattr(entry, "title", "") or ""
        head = (getattr(entry, "text", "") or "").splitlines()[0]
        assert needle in title.lower() or needle in head.lower(), (
            f"{CONTRACT} §The reframe names lever {number} "
            f"{CANON_SIX[number]!r}, so its canon head must still carry {needle!r}. "
            f"The loader quotes title={title!r} / head={head!r} — a renamed or "
            f"renumbered lever quoted under the old number grounds every prompt and "
            f"the catalog keyword on the wrong definition"
        )


def test_k1_every_lever_is_a_verbatim_slice_of_the_canon_file(
    levers: dict, canon_text: str, canon_path: Path
) -> None:
    """§Blind K1 "definitions verbatim substrings of the canon file"; §Work 1
    "VERBATIM from the canon file (… parse, total-or-raise, never paraphrase)"."""
    for number, entry in sorted(levers.items()):
        text = getattr(entry, "text", None)
        assert isinstance(text, str) and text.strip(), (
            f"{CONTRACT} §Work 1: lever {number} must carry its one-paragraph "
            f"definition and exhibit list; got {text!r}"
        )
        assert canon_text.count(text) == 1, (
            f"{CONTRACT} §Blind K1: lever {number}'s definition must be a VERBATIM "
            f"substring of {canon_path.name} (found {canon_text.count(text)} times). "
            f"Anything else is the paraphrase §Work 1 forbids:\n{text!r}"
        )


def test_k1_the_quoted_levers_drop_nothing_between_them(
    levers: dict, canon_text: str
) -> None:
    """§Work 1 "never paraphrase" read as coverage: §7's own prose between two
    levers cannot be silently left out of what the prompts quote."""
    offsets = {n: canon_text.index(e.text) for n, e in levers.items()}
    assert sorted(offsets, key=offsets.get) == sorted(levers), (  # type: ignore[arg-type]
        f"{CONTRACT} §The reframe numbers the levers in the canon's own order; the "
        f"quoted entries appear in a different order on disk: {offsets}"
    )
    ordered = sorted(levers)
    for first, second in pairwise(ordered):
        gap = canon_text[offsets[first] + len(levers[first].text) : offsets[second]]
        assert not gap.strip(), (
            f"{CONTRACT} §Work 1 quotes §7 'VERBATIM from the canon file', and canon "
            f"prose sits between lever {first} and lever {second} that no quoted entry "
            f"carries: {gap!r}"
        )


def test_k1_each_lever_cites_the_canon_line_it_came_from(
    levers: dict, canon_text: str, canon_path: Path
) -> None:
    """§Work 1 copies `load_term_definitions` "exactly", and that loader's
    entries carry the signed file and the line they were sliced from."""
    lines = canon_text.splitlines()
    for number, entry in sorted(levers.items()):
        line = getattr(entry, "source_line", None)
        source = getattr(entry, "source", None)
        assert isinstance(line, int) and 1 <= line <= len(lines), (
            f"{CONTRACT} §Work 1's `load_term_definitions` pattern attributes every "
            f"quote; lever {number} cites line {line!r} of a {len(lines)}-line file"
        )
        assert lines[line - 1] == entry.text.splitlines()[0], (
            f"{CONTRACT} §Work 1: lever {number} cites {source!r}, but line {line} of "
            f"{canon_path.name} reads {lines[line - 1]!r} and the quoted entry opens "
            f"{entry.text.splitlines()[0]!r} — the citation does not point at the quote"
        )
        assert isinstance(source, str) and canon_path.name in source, (
            f"{CONTRACT} §Work 1 quotes the SIGNED file; lever {number} attributes "
            f"itself to {source!r}, which does not name {canon_path.name}"
        )


def test_k1_a_missing_lever_raises_naming_what_it_wanted(
    load_levers, levers: dict, canon_clone: tuple[dict, Path]
) -> None:
    """§Blind K1 "missing-section raises naming what it wanted"; §Work 1
    "total-or-raise"."""
    clone_cfg, path = canon_clone
    original = path.read_text(encoding="utf-8")
    victim = levers[3]
    path.write_text(original.replace(victim.text + "\n", "", 1), encoding="utf-8")
    # The exception CLASS is the implementer's call; the contract pins the message.
    with pytest.raises(Exception) as caught:
        load_levers(clone_cfg)
    message = str(caught.value)
    assert "3" in message or TITLE_NEEDLES[3] in message.lower(), (
        f"{CONTRACT} §Blind K1: a hole in the six must raise 'naming what it wanted'. "
        f"Lever 3 ({CANON_SIX[3]!r}) was removed from the canon copy and the raise says "
        f"{message!r}, which names neither the number nor the lever"
    )


def test_k1_a_missing_section_raises_naming_what_it_wanted(
    load_levers, canon_clone: tuple[dict, Path]
) -> None:
    """§Blind K1, the literal case: §7 itself is gone."""
    clone_cfg, path = canon_clone
    original = path.read_text(encoding="utf-8")
    heads = [line for line in original.splitlines() if line.startswith("## 7. ")]
    assert len(heads) == 1, (
        f"{CONTRACT} §The reframe addresses the catalog as affordance §7; the canon "
        f"copy carries {len(heads)} '## 7. ' headings, so this pin has nothing to remove"
    )
    path.write_text(original.replace(heads[0], "## 7x. moved away", 1), encoding="utf-8")
    # The exception CLASS is the implementer's call; the contract pins the message.
    with pytest.raises(Exception) as caught:
        load_levers(clone_cfg)
    message = str(caught.value)
    assert "7" in message, (
        f"{CONTRACT} §Blind K1: 'missing-section raises naming what it wanted'. §7's "
        f"heading was removed from the canon copy and the raise says {message!r}, which "
        f"does not name the section it wanted"
    )


def test_k1_two_loads_are_byte_identical(load_levers, cfg: dict) -> None:
    """§Work 1 copies the `load_term_definitions` precedent, and §Work 3 wants
    "One source, three prompts, zero drift" — a loader that drifts run to run
    makes the three prompts disagree with each other on the same canon."""
    first = load_levers(cfg)
    second = load_levers(cfg)
    assert {n: e.text for n, e in first.items()} == {n: e.text for n, e in second.items()}, (
        f"{CONTRACT} §Work 3: 'One source, three prompts, zero drift'. Two loads of the "
        f"same canon returned different lever text"
    )


def test_k1_the_policy_sentence_rides_along_with_the_levers(
    cfg: dict, canon_text: str, verifier_prompt: str
) -> None:
    """§Work 1: "The §10 policy sentence ("deception is always a DECLARED
    property") rides along where the header already quotes it"."""
    loader = _surface(
        canon_docs,
        "load_deception_policy",
        "§Work 1 has the §10 policy sentence ride along with the levers",
    )
    policy = loader(cfg)
    text = getattr(policy, "text", "") or ""
    assert "declared" in text.lower() and "deception" in text.lower(), (
        f"{CONTRACT} §Work 1 quotes §10's 'deception is always a DECLARED property' "
        f"sentence; the loader returned {text!r}"
    )
    flowed = " ".join(canon_text.split())
    assert " ".join(text.split()) in flowed, (
        f"{CONTRACT} §Work 1 quotes the policy from the canon rather than retyping it, "
        f"and this sentence is not in affordance-language.md: {text!r}"
    )
    assert text in verifier_prompt, (
        f"{CONTRACT} §Work 1: the policy sentence 'rides along where the header already "
        f"quotes it' — the blind auditor's prompt does not carry it verbatim"
    )


# --- Addendum 1: THE SHAPE --------------------------------------------------


def test_shape_six_levers_five_keywords_and_7_5_tagged_keywordless(
    levers: dict, catalog: tuple[str, ...], prompts: dict[str, str], detect
) -> None:
    """§Addendum 1 THE SHAPE: "six levers, FIVE keywords — §7.5 … stays
    deliberately keywordless … pin "six levers quoted, five keywords, §7.5
    tagged keywordless""."""
    assert len(levers) == LEVER_COUNT, (
        f"{CONTRACT} §Addendum 1: six levers are quoted; the loader has {len(levers)}"
    )
    assert len(catalog) == KEYWORD_COUNT, (
        f"{CONTRACT} §Addendum 1 THE SHAPE: 'six levers, FIVE keywords' — and 'a blind "
        f"pin of len(DECEPTION_CATALOG) == 6 would be wrong'. The catalog holds "
        f"{len(catalog)}: {list(catalog)}"
    )
    assert len(set(catalog)) == len(catalog), (
        f"{CONTRACT} §Work 2 makes the catalog's canonical keys 'the six levers' "
        f"keywords', one per lever; this one repeats itself: {list(catalog)}"
    )
    for name, prompt in prompts.items():
        for number, entry in sorted(levers.items()):
            assert prompt.count(entry.text) == 1, (
                f"{CONTRACT} §Addendum 1: all six levers are QUOTED. The {name} prompt "
                f"carries lever {number} ({CANON_SIX[number]!r}) "
                f"{prompt.count(entry.text)} times"
            )
        tagged = detect(_tag_region(prompt, levers[KEYWORDLESS_LEVER].text))
        assert tagged == [], (
            f"{CONTRACT} §Addendum 1: §7.{KEYWORDLESS_LEVER} 'stays deliberately "
            f"keywordless', and 'giving it one would be the scope-guard-6 policy "
            f"change'. In the {name} prompt it is tagged with {tagged}"
        )


def _tag_region(prompt: str, entry_text: str) -> str:
    """Whatever the prompt adds to ONE quoted lever, before the next lever.

    §Work 3 has the prompts quote the six "with their verbatim definitions +
    exhibits from the loader", and Addendum 1 says §7.5 is "TAGGED keywordless",
    so each quoted entry carries a tag of the prompt's own.  That tag is the only
    place a prompt binds a keyword to a lever NUMBER, which is what makes it the
    bridge these pins read.
    """
    start = prompt.index(entry_text) + len(entry_text)
    return prompt[start:].split("\n\n", 1)[0]


# --- K2: the fold -----------------------------------------------------------


def test_k2_every_pre_e1_keyword_still_detects_and_folds_to_one_lever(
    detect, catalog: tuple[str, ...]
) -> None:
    """§Work 2: "NOTHING previously matchable becomes unmatchable (pin: every
    name in the on-disk union still detects, folding to its lever)"; §Blind K2:
    "every historically observed name (the 7 above) and every current catalog
    keyword detects and folds to exactly one of the six"."""
    assert len(PRE_E1_KEYWORDS) == PRE_E1_KEYWORD_COUNT, (
        "fixture wall: §The reframe calls the pre-E-1 catalog a 'closed 11-keyword "
        f"tuple' and this file's transcription of it holds {len(PRE_E1_KEYWORDS)}"
    )
    for name in (*PRE_E1_KEYWORDS, *catalog):
        found = detect(name)
        assert len(found) == 1, (
            f"{CONTRACT} §Blind K2: {name!r} must detect 'and fold to exactly one of "
            f"the six'; it detected {found}. §Work 2: nothing previously matchable may "
            f"become unmatchable"
        )
        assert found[0] in catalog, (
            f"{CONTRACT} §Work 2 folds every spelling onto a CATALOG keyword; {name!r} "
            f"folded onto {found[0]!r}, which is not in {list(catalog)}"
        )


def test_k2_the_fold_partitions_the_eleven_names_as_the_contract_writes_it(
    detect, catalog: tuple[str, ...]
) -> None:
    """§Work 2's fold, class by class: "lookalike->look-alike; camouflage +
    palette overload->palette overloading's key; false tell + fake tell + lying
    display->lying displays' key; mimic + disguise->look-alike's key; decoy +
    retrospective punishment keep their lever".

    Pinned as the PARTITION rather than as five keyword strings: Addendum 1
    ratifies "D4 short-form canonical keywords" as the implementer's call, so
    what the contract fixes is which names mean the same lever.
    """
    expected: dict[int, set[str]] = {}
    for name, number in FOLD_TO_LEVER.items():
        expected.setdefault(number, set()).add(name)

    measured: dict[str, set[str]] = {}
    for name in FOLD_TO_LEVER:
        measured.setdefault(detect(name)[0], set()).add(name)

    assert sorted(measured.values(), key=sorted) == sorted(expected.values(), key=sorted), (
        f"{CONTRACT} §Work 2's fold groups the eleven spellings into these classes "
        f"{sorted(expected.values(), key=sorted)}; the alias machinery groups them "
        f"{sorted(measured.values(), key=sorted)}"
    )
    assert set(measured) == set(catalog), (
        f"{CONTRACT} §Work 2: the catalog's canonical keys ARE the levers' keywords, so "
        f"the fold's targets and the catalog are one list. Targets {sorted(measured)} vs "
        f"catalog {sorted(catalog)}"
    )
    assert len(expected) == KEYWORD_COUNT, (
        "fixture wall: §Addendum 1 says five keywords, and this file's transcription of "
        f"§Work 2's fold describes {len(expected)} classes"
    )


def test_k2_the_alias_machinery_itself_carries_every_pre_e1_spelling(detect) -> None:
    """§Work 2: every spelling folds "via the existing alias machinery
    (`_LEVER_ALIASES` / `_lever_aliases` :1173)" — so the fold is a table lookup
    in the one named place, not an accident of the regex."""
    aliases = _surface(
        s3_verify,
        "_LEVER_ALIASES",
        "§Work 2 folds every observed spelling 'via the existing alias machinery "
        "(_LEVER_ALIASES / _lever_aliases :1173)'",
    )
    keys = {_squash(str(key)) for key in aliases}
    for name in PRE_E1_KEYWORDS:
        assert _squash(name) in keys, (
            f"{CONTRACT} §Work 2 folds {name!r} through the alias machinery, and the "
            f"table does not carry it ({sorted(keys)})"
        )
        assert _squash(str(aliases[_squash(name)])) == _squash(detect(name)[0]), (
            f"{CONTRACT} §The reframe says the catalog is 'regex-matched on BOTH sides'; "
            f"the alias table folds {name!r} onto "
            f"{aliases[_squash(name)]!r} while the matcher folds it onto {detect(name)[0]!r}"
        )


def test_k2_each_class_is_tagged_on_its_own_canon_lever_in_all_three_prompts(
    levers: dict, prompts: dict[str, str], detect
) -> None:
    """§Work 2 binds each fold class to ONE canon lever ("palette overloading's
    key", "lying displays' key"), and §Work 3 has all three prompts quote the
    levers from one loader. The prompts' own per-lever tag is where the keyword
    meets the lever NUMBER, so it is read here as the binding under test.
    """
    for prompt_name, prompt in prompts.items():
        for number, entry in sorted(levers.items()):
            if number == KEYWORDLESS_LEVER:
                continue
            tagged = detect(_tag_region(prompt, entry.text))
            assert len(tagged) == 1, (
                f"{CONTRACT} §Work 2 gives every lever but §7.5 exactly one catalog "
                f"keyword; the {prompt_name} prompt tags lever {number} "
                f"({CANON_SIX[number]!r}) with {tagged}"
            )
            for name, expected in FOLD_TO_LEVER.items():
                if expected != number:
                    continue
                assert detect(name)[0] == tagged[0], (
                    f"{CONTRACT} §Work 2 folds {name!r} onto lever {number} "
                    f"({CANON_SIX[number]!r}), which the {prompt_name} prompt reports "
                    f"under {tagged[0]!r} — but the matcher folds {name!r} onto "
                    f"{detect(name)[0]!r}. The prompt and the matcher name two "
                    f"different levers for one word, which is the drift E-1 closes"
                )


def test_k2_the_echo_games_four_round_names_fold_to_three_levers(detect) -> None:
    """§Blind K2 + §Addendum 1: "echo game 4 names -> 3 levers (as written)"."""
    batch, slug, rounds, name_count, lever_count = ECHO_SIDECAR
    history = _sidecar(batch, slug)
    names = _names(history)
    assert len(history) == rounds and len(names) == name_count, (
        f"{CONTRACT} §The reframe measured 'the echo game's {rounds} rounds used "
        f"{name_count} distinct names'; the sidecar on disk has {len(history)} rounds "
        f"and {len(names)} names ({names})"
    )
    folded = {detect(name)[0] for name in names}
    assert len(folded) == lever_count, (
        f"{CONTRACT} §Blind K2 and §Addendum 1: 'the echo game's four distinct "
        f"round-names fold to <={lever_count} levers' ('4 names -> 3 levers, as "
        f"written'). They fold to {len(folded)}: {sorted(folded)}"
    )


def test_k2_seamlocks_six_round_names_fold_to_five_levers(detect) -> None:
    """§Addendum 1, K2's BOUNDS CORRECTED: "seamlock 6 names -> **5** levers,
    NOT <=4 — only camouflage merges; false tell renames onto a lever that game
    never named separately. The blind lane pins <=5 (or the measured 5)"."""
    batch, slug, rounds, name_count, lever_count = SEAMLOCK_SIDECAR
    history = _sidecar(batch, slug)
    names = _names(history)
    assert len(history) == rounds and len(names) == name_count, (
        f"{CONTRACT} §The reframe measured \"seamlock's {rounds} rounds used "
        f"{name_count}\" distinct names; the sidecar has {len(history)} rounds and "
        f"{len(names)} names ({names})"
    )
    folded = {detect(name)[0] for name in names}
    assert len(folded) <= lever_count, (
        f"{CONTRACT} §Addendum 1 pins seamlock's six names at <={lever_count} levers; "
        f"they fold to {len(folded)}: {sorted(folded)}"
    )
    assert len(folded) == lever_count, (
        f"{CONTRACT} §Addendum 1: the measured fold is exactly {lever_count} levers "
        f"('only camouflage merges'). This run folds the same six names to "
        f"{len(folded)}: {sorted(folded)}"
    )
    merged = [name for name in names if detect(name)[0] != name]
    assert "camouflage" in merged, (
        f"{CONTRACT} §Addendum 1: 'only camouflage merges' in seamlock's history, so "
        f"camouflage must fold onto another name's lever. The names that fold onto a "
        f"different keyword are {merged}"
    )


def test_k2_the_sidecars_on_disk_are_the_contracts_own_census(detect) -> None:
    """§The reframe: "Observed on disk (union of every sighting ever): camouflage,
    decoy, false tell, look-alike, lying display, palette overload,
    retrospective punishment — 7 of the 11 keywords; never sighted: lookalike,
    mimic, disguise, fake tell"."""
    sidecars = _corpus_files(f"*/*/{SIDECAR_REL}")
    assert sidecars, (
        f"{CONTRACT} §Blind K2 computes its bounds from 'the real lever-history "
        f"sidecars'; none are on disk under out/corpus"
    )
    union: set[str] = set()
    for path in sidecars:
        union.update(_names(json.loads(path.read_text(encoding="utf-8"))))
    assert union == set(SIGHTED), (
        f"{CONTRACT} §The reframe's on-disk union is {sorted(SIGHTED)}; the sidecars now "
        f"hold {sorted(union)}. The never-sighted four are {list(NEVER_SIGHTED)}, and a "
        f"name that has appeared since is a census this contract did not measure"
    )
    for name in sorted(union):
        assert len(detect(name)) == 1, (
            f"{CONTRACT} §Work 2: 'every name in the on-disk union still detects, "
            f"folding to its lever'. {name!r} detects as {detect(name)}"
        )


# --- K3: prompt sync --------------------------------------------------------


def test_k3_all_three_prompts_carry_every_definition_verbatim(
    levers: dict, prompts: dict[str, str]
) -> None:
    """§Blind K3: "all three prompts carry each definition verbatim"; §Work 3:
    "the S2 payload's deception text and S1's UNDECLARED_DECEPTION_NOTE consume
    the SAME loader. One source, three prompts, zero drift"."""
    assert sorted(prompts) == ["payload", "verifier", "writer"], "three prompts, exactly"
    for prompt_name, prompt in prompts.items():
        missing = [number for number, entry in levers.items() if entry.text not in prompt]
        assert not missing, (
            f"{CONTRACT} §Blind K3: the {prompt_name} prompt must carry each of the six "
            f"definitions verbatim; levers {missing} "
            f"({[CANON_SIX[n] for n in missing]}) are absent. §Work 3: 'no more bare "
            f"keyword list'"
        )


def test_k3_all_three_prompts_name_the_same_catalog(
    catalog: tuple[str, ...], prompts: dict[str, str]
) -> None:
    """§Work 3: "One source, three prompts, zero drift" — a keyword one prompt
    offers and another does not is the drift the contract closes."""
    for prompt_name, prompt in prompts.items():
        missing = [keyword for keyword in catalog if keyword not in prompt]
        assert not missing, (
            f"{CONTRACT} §Work 3: the {prompt_name} prompt does not name the catalog "
            f"keyword(s) {missing}, so the three sessions are not reading one list"
        )


def test_k3_mutating_the_canon_moves_all_three_prompts(
    levers: dict, canon_clone: tuple[dict, Path], batch_cfg: dict, tmp_path: Path
) -> None:
    """§Blind K3: "mutating the canon text changes all three (the
    term-definitions drift-pin pattern)". A prompt that does not follow the
    canon file is quoting a copy, which is exactly what E-1 removes."""
    clone_cfg, path = canon_clone
    sentinel = "ZZ-E1-BLIND-SENTINEL-ZZ"
    entry = levers[4]
    words = sorted((w for w in re.findall(r"[A-Za-z]{6,}", entry.text)), key=len, reverse=True)
    assert words, f"lever 4's canon entry has no word long enough to swap: {entry.text!r}"
    mutated_entry = entry.text.replace(words[0], sentinel)
    original = path.read_text(encoding="utf-8")
    assert entry.text in original, "the canon copy does not carry lever 4's entry"
    path.write_text(original.replace(entry.text, mutated_entry, 1), encoding="utf-8")

    merged = dict(batch_cfg)
    merged["duckwm_docs"] = clone_cfg["duckwm_docs"]
    spec_dir = tmp_path / "drift-spec"
    spec_dir.mkdir()
    shutil.copyfile(SPEC_FIXTURE, spec_dir / "spec.yaml")
    (spec_dir / "spec.md").write_text("# Drift\n\nprose.\n", encoding="utf-8")
    game_cls, solver_cls = s3_verify.load_worker_classes(TOY_WORKER)
    staged = tmp_path / "drift-staged" / "worker"
    s3_verify.stage_worker_copy(TOY_WORKER, staged)
    moved = {
        "writer": s1_spec.build_writer_prompt(merged, b005.IDEA),
        "payload": s2_implement.build_payload(spec_dir, merged)[0],
        "verifier": s3_verify.build_verifier_prompt(
            merged, s3_verify.capture(game_cls, solver_cls), staged
        ),
    }
    for prompt_name, prompt in moved.items():
        assert sentinel in prompt, (
            f"{CONTRACT} §Blind K3: 'mutating the canon text changes all three'. "
            f"Lever 4's canon entry was edited and the {prompt_name} prompt does not "
            f"carry the edit — it is quoting something other than the canon file"
        )
        assert entry.text not in prompt, (
            f"{CONTRACT} §Blind K3 / §Work 3 'zero drift': the {prompt_name} prompt "
            f"still carries lever 4's PRE-EDIT canon text after the canon moved"
        )


def test_k3_the_s1_scan_note_still_names_exactly_the_catalog(
    catalog: tuple[str, ...]
) -> None:
    """§Work 3 names `s1_spec.UNDECLARED_DECEPTION_NOTE` as one of the surfaces
    that must consume the one source; §Addendum 1 ratifies D6 (a NEW S1 section
    carries the quoted levers), so what the note itself owes is the keyword list
    — interpolated, so a catalog change moves it."""
    note = _surface(
        s1_spec,
        "UNDECLARED_DECEPTION_NOTE",
        "§Work 3 has S1's UNDECLARED_DECEPTION_NOTE consume the same loader",
    )
    text = note if isinstance(note, str) else "\n".join(note)
    missing = [keyword for keyword in catalog if keyword not in text]
    assert not missing, (
        f"{CONTRACT} §Work 3: the scanner note the writer is judged by must name the "
        f"catalog it scans for; {missing} are not in it. A hand-typed list here drifts "
        f"from the catalog the linter actually uses"
    )
    assert str(len(catalog)) in text, (
        f"{CONTRACT} §Work 3 (PROMPT-SYNC): the note states how many levers the scanner "
        f"reads for, and the catalog now holds {len(catalog)}; the note's own count does "
        f"not say so"
    )


# --- K4: compatibility ------------------------------------------------------


def test_k4_every_shipped_corpus_report_still_validates(cfg: dict) -> None:
    """§Work 2: "the shipped corpus reports keep validating"; §Blind K4:
    "shipped corpus verifier reports still validate"."""
    validate = _surface(
        s3_verify,
        "validate_report",
        "§Work 2 requires the shipped corpus reports to keep validating",
    )
    reports = _corpus_files("*/*/worker.verifier-report.json")
    assert reports, (
        f"{CONTRACT} §Blind K4 validates the SHIPPED corpus reports and none are on "
        f"disk under out/corpus — the compatibility half is then unmeasured"
    )
    broken: list[str] = []
    for path in reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        try:
            validate(report)
        except Exception as exc:  # noqa: BLE001 — every failure class is a finding here
            broken.append(f"{path.relative_to(REPO_ROOT)}: {type(exc).__name__}: {exc}")
    assert not broken, (
        f"{CONTRACT} §Work 2: 'the shipped corpus reports keep validating' — "
        f"{len(broken)} of {len(reports)} no longer do:\n" + "\n".join(broken)
    )


def test_k4_shipped_specs_keep_declaring_through_the_substring_rule(detect) -> None:
    """§Work 2: "shipped specs' knobs.deceptions entries keep declaring
    (substring/regex containment unchanged)"."""
    specs = _corpus_files("*/*/spec.yaml")
    assert specs, f"{CONTRACT} §Work 2 is about SHIPPED specs and none are on disk"
    silent: list[str] = []
    checked = 0
    for path in specs:
        spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        knobs = ((spec.get("game") or {}).get("knobs") or {})
        for entry in knobs.get("deceptions") or []:
            if not isinstance(entry, str):
                continue
            named = [name for name in PRE_E1_KEYWORDS if _squash(name) in _squash(entry)]
            if not named:
                continue
            checked += 1
            if not detect(entry):
                silent.append(f"{path.relative_to(REPO_ROOT)}: {entry!r} names {named}")
    assert checked, (
        f"{CONTRACT} §Work 2 pins that shipped `knobs.deceptions` entries keep "
        f"declaring, and no shipped entry names any of the eleven pre-E-1 keywords "
        f"{list(PRE_E1_KEYWORDS)} — the compatibility half has no subject"
    )
    assert not silent, (
        f"{CONTRACT} §Work 2: 'NOTHING previously matchable becomes unmatchable'. "
        f"{len(silent)} of {checked} shipped declarations stopped declaring:\n"
        + "\n".join(silent)
    )


def test_k4_a_spec_declaring_camouflage_declares_the_palette_overloading_lever(
    detect, catalog: tuple[str, ...]
) -> None:
    """§Blind K4: "a spec declaring "camouflage" still counts as declaring the
    palette-overloading lever (substring rule holds)". Driven through the REAL
    diff, in both directions, because the diff is what turns agreement into a
    verdict."""
    target = detect("palette overload")[0]
    assert detect("camouflage") == [target], (
        f"{CONTRACT} §Work 2: camouflage folds onto 'palette overloading's key'; it "
        f"folds onto {detect('camouflage')}"
    )
    pairs = (
        ("camouflage: the wall and the letterbox share an index", "palette overload"),
        ("palette overload: one index, two roles", "camouflage over the letterbox"),
        ("mimic: the inert twin of the real control", "look-alike"),
    )
    for declared, claimed in pairs:
        spec = {"game": {"terms": ["move.grid"], "knobs": {"deceptions": [declared]}}}
        claims = {
            "terms": [{"term": "move.grid", "reachable": True}],
            "dead_code": [],
            "deceptions": [{"lever": claimed}],
            "enforcement": [],
            "notes": "",
        }
        diff = s3_verify.compute_diff(claims, spec)
        assert diff["undeclared_deceptions"] == [], (
            f"{CONTRACT} §Blind K4: a spec declaring {declared!r} declares the lever an "
            f"auditor reports as {claimed!r}; the diff calls it undeclared "
            f"({diff['undeclared_deceptions']})"
        )
        assert diff["declared_deceptions_undetected"] == [], (
            f"{CONTRACT} §Work 2: the two spellings are ONE lever, so the declaration "
            f"cannot come back undetected either ({diff['declared_deceptions_undetected']})"
        )
        assert diff["deceptions_declared"] == diff["deceptions_detected"], (
            f"{CONTRACT} §Work 2 normalizes both sides onto the catalog: declaring "
            f"{declared!r} and claiming {claimed!r} must read as agreement, got "
            f"{diff['deceptions_declared']} vs {diff['deceptions_detected']}"
        )
        assert set(diff["deceptions_declared"]) <= set(catalog), (
            f"{CONTRACT} §Work 2: the diff speaks in catalog keywords; it carried "
            f"{diff['deceptions_declared']}"
        )


def test_k4_a_recorded_historic_spelling_still_validates_and_prose_still_does_not(
    catalog: tuple[str, ...]
) -> None:
    """§Work 2: "the _validate_uncorroborated :2666 and advisory-row checks must
    accept HISTORIC keywords"; §Addendum 1 ratifies "the alias-set acceptance in
    _validate_uncorroborated with its dead-code-guard pin".

    Both halves are pinned, because acceptance alone could be had by deleting
    the check: a historic spelling validates AND an off-catalog word, including
    prose that merely CONTAINS a keyword, still does not.
    """
    validate = _surface(
        s3_verify,
        "_validate_uncorroborated",
        "§Work 2 requires the _validate_uncorroborated check to accept historic keywords",
    )
    for name in PRE_E1_KEYWORDS:
        validate([{"lever": name, "note": "first sighting"}], "diff.uncorroborated_levers")
    # The dead-code guard: the check still REFUSES. "the decoy thing is fine" is
    # Addendum 1's own example of what fold-then-check would have let through and
    # the alias set does not, so it is the control that separates the two calls.
    for refused in ("smoke and mirrors", "the decoy thing is fine", ""):
        # The exception CLASS is the implementer's call; the contract pins the message.
        with pytest.raises(Exception) as caught:
            validate([{"lever": refused, "note": "n"}], "diff.uncorroborated_levers")
        message = str(caught.value)
        assert any(keyword in message for keyword in catalog) or "lever" in message, (
            f"{CONTRACT} §Work 2 keeps the catalog bar on recorded levers, and the "
            f"refusal of {refused!r} names neither the catalog nor the field: {message!r}"
        )


def test_k4_the_alias_acceptance_is_load_bearing_for_records_already_on_disk() -> None:
    """§Addendum 1's dead-code guard, measured on the corpus: at least one
    SHIPPED record names a pre-E-1 spelling, so §Work 2's "must accept HISTORIC
    keywords" is a live compatibility requirement rather than a precaution."""
    key = _surface(
        s3_verify,
        "UNCORROBORATED_KEY",
        "§Work 2 names the _validate_uncorroborated records that must keep validating",
    )
    catalog = set(s1_spec.DECEPTION_CATALOG)
    historic: list[str] = []
    total = 0
    for path in _corpus_files("*/*/worker.verifier-report.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        for entry in (report.get("diff") or {}).get(key) or []:
            total += 1
            if entry.get("lever") not in catalog:
                historic.append(f"{path.relative_to(REPO_ROOT)}: {entry['lever']!r}")
    assert historic, (
        f"{CONTRACT} §Work 2: the validator 'must accept HISTORIC keywords' because "
        f"shipped records name pre-E-1 spellings. None of the {total} records on disk "
        f"does, so either the corpus was rewritten (§Hard rules: it is immutable) or "
        f"this compatibility clause now guards nothing"
    )


def test_k4_an_off_catalog_claim_still_raises_rather_than_being_dropped(
    catalog: tuple[str, ...]
) -> None:
    """§Work 4: "validate_claims RAISES … keep the raise — it is the stricter,
    measured behavior"; §The reframe: "an off-catalog claim RAISES through
    validate_claims"."""
    validate = _surface(
        s3_verify,
        "validate_claims",
        "§Work 4 keeps validate_claims' raise on an off-catalog claim",
    )
    evidence = [{"path": "game.py", "line": 12}]
    base = {"terms": [], "dead_code": [], "enforcement": [], "notes": ""}
    with pytest.raises(ValueError) as caught:
        validate(
            dict(base, deceptions=[{"lever": "smoke and mirrors", "evidence": evidence}]),
            frozenset(),
            None,
        )
    message = str(caught.value)
    assert "smoke and mirrors" in message, (
        f"{CONTRACT} §Work 4 keeps the raise; it must say which word failed. Got "
        f"{message!r}"
    )
    assert any(keyword in message for keyword in catalog), (
        f"{CONTRACT} §Work 4: the raise names the catalog the word missed; got {message!r}"
    )
    for accepted in (*catalog, *PRE_E1_KEYWORDS):
        validate(
            dict(base, deceptions=[{"lever": accepted, "evidence": evidence}]),
            frozenset(),
            None,
        )


# --- K5: the two defect fixes -----------------------------------------------


def test_k5_the_header_states_the_enforcement_validate_claims_actually_applies(
    verifier_prompt: str, levers: dict
) -> None:
    """§Work 4 (sweep find #1): "DECEPTION_HEADER promises an off-list word is
    "discarded" but validate_claims RAISES and burns the corrective turn. Make
    the prompt tell the truth about the enforcement"; §Blind K5: "the header's
    enforcement sentence matches validate_claims' actual behavior"."""
    header = _surface(
        s3_verify,
        "DECEPTION_HEADER",
        "§Work 4 fixes DECEPTION_HEADER's enforcement sentence",
    )
    assert isinstance(header, str) and header, f"{CONTRACT} §Work 4: the header is {header!r}"
    # The section as the auditor really reads it: the header filled in, inside
    # the prompt, so a truthful constant that nothing renders cannot pass.
    start = verifier_prompt.index(levers[1].text)
    section = verifier_prompt[max(0, start - 4000) : start + 8000]

    failure_sentences = [
        sentence
        for sentence in _SENTENCE_SPLIT_RE.split(section)
        if _FAILURE_RE.search(sentence) and _REPLY_RE.search(sentence)
    ]
    assert failure_sentences, (
        f"{CONTRACT} §Work 4: validate_claims RAISES, so the prompt must say the REPLY "
        f"fails rather than that the word is quietly handled. No sentence in the "
        f"deception section says so"
    )
    assert _CORRECTIVE_TURN_RE.search(section), (
        f"{CONTRACT} §Work 4: the raise 'burns the corrective turn', and the prompt owes "
        f"the auditor that consequence; the section never mentions a corrective turn"
    )
    for sentence in _SENTENCE_SPLIT_RE.split(section):
        if not _DROP_VERB_RE.search(sentence):
            continue
        assert _NEGATOR_RE.search(sentence) or _FAILURE_RE.search(sentence), (
            f"{CONTRACT} §Work 4 (sweep find #1): the header may no longer promise an "
            f"off-list word is simply discarded — validate_claims raises. This sentence "
            f"promises it with neither a negation nor the failure beside it: {sentence!r}"
        )


def _plant_reconcilable_slot(cfg: dict, root: Path, *, lever: str) -> orch.SlotContext:
    """A slot whose only residual is one undeclared-deception, at t2.

    t2 because the tier table allows ONE declared lever there, which is what
    makes the amendment lint and the provenance observable; §Work 5 is about the
    string a successful reconciliation writes, not about the tier guards.
    """
    spec_dir = root / "corpus" / "slug"
    (spec_dir / orch.WORKER_DIRNAME).mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.yaml").write_text(b005.SPEC_TEXT, encoding="utf-8")
    ideas = root / "ideas"
    ideas.mkdir(parents=True, exist_ok=True)
    idea = dict(b005.IDEA)
    idea["tier"] = "t2"
    (ideas / "idea-001.json").write_text(json.dumps(idea, indent=2), encoding="utf-8")
    ctx = orch.SlotContext(
        cfg=cfg, batch_id="e1blind", slug="slug", index=1, state="implemented",
        stage="s3_verify", attempt=1, batch_dir=root / "batch", ideas_dir=ideas,
        idea_path=ideas / "idea-001.json", corpus_dir=root / "corpus", spec_dir=spec_dir,
        respec_count=0, verifier_rejects=1, green_failures=0,
    )
    ctx.verifier_report_path.write_text(
        json.dumps(
            {
                "verdict": "reject",
                "reject_reasons": [
                    {
                        "code": "undeclared-deception",
                        "lever": lever,
                        "detail": f"the audit detected the {lever!r} lever; the spec declares []",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return ctx


def _reconcile_cfg(batch_cfg: dict) -> dict:
    cfg = copy.deepcopy(dict(batch_cfg))
    cfg["tiers"] = {
        "term_budget": dict(b005.KILL_BUDGETS),
        "term_budget_action": "kill",
        "knob_defaults_action": "kill",
    }
    return cfg


def _declared(ctx: orch.SlotContext) -> list[str]:
    spec = yaml.safe_load((ctx.spec_dir / "spec.yaml").read_text(encoding="utf-8"))
    return list(((spec.get("game") or {}).get("knobs") or {}).get("deceptions") or [])


def test_k5_the_reconciled_entry_template_carries_the_path_that_wrote_it() -> None:
    """§Work 5 (sweep find #2): "RECONCILED_DECEPTION … hardcodes "(round_cap)"
    provenance even when the EARLY path writes it — the entry should name the
    path that wrote it (template gains a {via} or two constants)"."""
    template = _surface(
        orch,
        "RECONCILED_DECEPTION",
        "§Work 5 makes the reconciled deception entry name the path that wrote it",
    )
    assert VIA_SLOT in template or "{" in template, (
        f"{CONTRACT} §Work 5: the template must stop hardcoding its provenance; it reads "
        f"{template!r}"
    )
    assert "round_cap" not in template.replace(VIA_SLOT, ""), (
        f"{CONTRACT} §Work 5: '(round_cap)' may no longer be baked into the template, "
        f"because the early path writes the same entry. It reads {template!r}"
    )


def test_k5_a_reconciliation_through_the_early_path_names_the_early_path(
    batch_cfg: dict, tmp_path: Path
) -> None:
    """§Blind K5: "a reconciled deception entry written through the early path
    names the early path". Driven through the REAL early-verdict path, not by
    handing the writer a provenance string, so the pin is that the PATH labels
    itself."""
    cfg = _reconcile_cfg(batch_cfg)
    ctx = _plant_reconcilable_slot(cfg, tmp_path / "early", lever="decoy")
    slot = orch._Slot(
        slug="slug", index=1, state="implemented", history=[],
        rejects=orch._empty_rejects(), cost=orch._empty_cost(),
    )
    result = {
        "cost": {"usd": 0.0, "tokens_in": 0, "tokens_out": 0},
        "reason": "verifier reject: undeclared-deception",
    }
    reconciled = orch._reconcile_early_verdict(
        slot, ctx=ctx, cfg=cfg, result=result, cap=2,
        ledger_path=tmp_path / "ledger.jsonl", batch_id="e1blind", bdir=tmp_path / "bdir",
    )
    assert reconciled is True, (
        f"{CONTRACT} §Work 5 is about the entry the EARLY path writes, and the early "
        f"path refused this one-finding residual, so the provenance is unmeasured here"
    )
    entries = _declared(ctx)
    assert len(entries) == 1 and entries[0].lower().startswith("decoy"), (
        f"{CONTRACT} §Work 5: the reconciliation declares the lever it answered; the "
        f"spec now declares {entries}"
    )
    entry = entries[0].lower()
    assert any(word in entry for word in EARLY_PATH_WORDS), (
        f"{CONTRACT} §Blind K5: 'a reconciled deception entry written through the early "
        f"path names the early path'. The early path wrote {entries[0]!r}"
    )
    assert not any(word in entry for word in CAP_PATH_WORDS), (
        f"{CONTRACT} §Work 5: the b005r2 echo spec is 'the mislabeled exhibit' — an "
        f"entry the early path wrote naming the round cap. It wrote {entries[0]!r}"
    )


def test_k5_a_reconciliation_at_the_round_cap_still_names_the_round_cap(
    batch_cfg: dict, tmp_path: Path
) -> None:
    """§Work 5's other half: the fix names the path that wrote it, so the
    round-cap path must still say round_cap. Without this the defect could be
    "fixed" by relabelling both paths the same way again."""
    cfg = _reconcile_cfg(batch_cfg)
    ctx = _plant_reconcilable_slot(cfg, tmp_path / "cap", lever="decoy")
    slot = orch._Slot(
        slug="slug", index=1, state="implemented", history=[],
        rejects=orch._empty_rejects(), cost=orch._empty_cost(),
    )
    result = {
        "cost": {"usd": 0.0, "tokens_in": 0, "tokens_out": 0},
        "reason": "verifier reject: undeclared-deception",
    }
    outcome = orch._round_cap_verdict(
        slot, ctx=ctx, cfg=cfg, result=result, round_cap=3,
        ledger_path=tmp_path / "ledger.jsonl", batch_id="e1blind", bdir=tmp_path / "bdir",
    )
    assert outcome == "continue", (
        f"{CONTRACT} §Work 5: the round-cap path reconciles this residual; it returned "
        f"{outcome!r} and wrote {_declared(ctx)}"
    )
    entries = _declared(ctx)
    assert len(entries) == 1, (
        f"{CONTRACT} §Work 5: one lever answered, one declaration; got {entries}"
    )
    entry = entries[0].lower()
    assert any(word in entry for word in CAP_PATH_WORDS), (
        f"{CONTRACT} §Work 5: 'the entry should name the path that wrote it', and the "
        f"round-cap path wrote {entries[0]!r}"
    )
    assert "reconcile_early" not in entry, (
        f"{CONTRACT} §Work 5: the two paths must be distinguishable in the record; the "
        f"round cap wrote {entries[0]!r}"
    )


# --- scope guard + hermeticity ----------------------------------------------


def test_scope_guard_the_keywordless_lever_stays_out_of_the_catalog(
    catalog: tuple[str, ...], detect
) -> None:
    """§Scope guards 6: "No knob changes; the catalog re-grounding is vocabulary
    semantics, not policy" — and §Addendum 1: giving §7.5 a keyword "would be
    the scope-guard-6 policy change". A bare word for invisible state would make
    every honest spec declare it, so no catalog keyword may be one."""
    for keyword in catalog:
        assert _squash(keyword) not in {"hidden", "invisible", "invisibleloadbearingstate"}, (
            f"{CONTRACT} §Addendum 1: §7.5 'stays deliberately keywordless'; the catalog "
            f"now carries {keyword!r}"
        )
    for word in ("hidden geometry", "invisible load-bearing state", "hidden state"):
        assert detect(word) == [], (
            f"{CONTRACT} §Addendum 1 / §Scope guards: §7.5 has no catalog word, so "
            f"{word!r} must fold onto nothing. It detected {detect(word)}"
        )


def test_zz_the_read_only_fixtures_were_not_written() -> None:
    """§Hard rules: "never write under out/ or games/; canon/ is READ-ONLY";
    §Blind K2/K4 read the real sidecars, specs and reports as FIXTURES.

    The digests were taken at module import, before any test here ran.
    """
    assert READ_ONLY_DIGESTS, (
        f"{CONTRACT} §Blind K2 reads the real corpus sidecars as fixtures and this "
        f"module found none to hash — the measurement had no subject"
    )
    moved = [
        str(path.relative_to(REPO_ROOT))
        for path, digest in READ_ONLY_DIGESTS.items()
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest
    ]
    assert not moved, (
        f"{CONTRACT} §Hard rules: the corpus and the canon are READ-ONLY here. These "
        f"files moved while this module ran: {moved}"
    )
