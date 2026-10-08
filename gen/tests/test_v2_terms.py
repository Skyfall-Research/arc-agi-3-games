"""Blind pins for FROZEN CONTRACT Q-1 — term attribution disputes.

Run: .venv/bin/python -m pytest gen/tests/test_v2_terms.py -v

Written from `docs/v2/contracts/Q-1-term-attribution.md` ALONE, section "Blind
lane" (T1-T5).  This is the BLIND lane: the implementer's own battery
(`gen/tests/test_q1_terms.py`) was never read, and neither was any uncommitted
change to `gen/s3_verify.py`, `gen/cli.py` or `config/template.yaml` — every
shipped file this module consulted was read out of HEAD (the E-5 close commit)
with `git show`, for IDIOM only.  Every assertion message cites the contract
clause it holds, so a red test says which sentence of Q-1 stopped being true
rather than which line of code moved.

WHAT THIS FILE WAS ALLOWED TO READ, AND DID.  The committed claims/diff/report
shapes in `s3_verify` (`claims.terms[]`, `claims.term_sites[]`, `compute_diff`,
`assemble_report`, `validate_report`, `DIFF_KEYS`, `REPORT_KEYS`), the L-1
`deception_action` knob precedent in the same file, the CLI overlay and
`build_config` in `gen/cli.py`, and the existing verifier test rigs for their
fixture pattern.  The EXPECTATIONS are the contract's alone.

HERMETIC.  Every fixture below is built in `tmp_path` from the contract's own
description of the exhibit.  Nothing under `out/`, `games/` or `../duckWM` is
read or written by any pin — the vendored, in-repo `canon/` snapshot (contract
P-2) is the only on-disk root any of them names, read-only, plus the real
`config/template.yaml` for the two arming pins that are ABOUT that file.  No
driver runs, no network, no spend, and `cli.build_config` is handed tmp roots so
the batch-id and seed scans never touch `out/batches/`.
  The contract's §1 asks the IMPLEMENTER to measure the b005r2 round-7 report
under `out/corpus/`; the blind brief forbids this lane from reading the real
`out/`, so that measurement is the implementer's and is not attempted here.

A PROMISED SURFACE THAT IS MISSING IS A FAILURE, NEVER A SKIP (`_surface`,
`_disputes`): a contract that promises a report key and ships none must turn
this file red, not green-with-a-skip.  There are no skips in this module.

WHICH PINS ARE SUPPOSED TO BE RED BEFORE Q-1 LANDS.  T1, T2, T3, T4's schema
half and T5's arming are ABSENCE reds on the pre-Q-1 tree: the feature is not
there, so the dispute never pairs and the knob never arms.  T4's byte-identity
pins are GREEN ON BOTH SIDES by construction — `load_config` and the verifier
stage both tolerate an unknown `verifier.*` key, so on the pre-Q-1 tree all
three knob values resolve to the one behaviour there is.
  Three pins would otherwise have been TRIVIALLY green while the feature was
missing — T2's whole premise is that a break can be observed, and "`record`
moved nothing else" is free when `record` moves nothing.  Each of them
therefore asserts the baseline first (`_require_live_dispute`, and `test_t1d`'s
own guard) and says in its message that T1 is where the real finding is.

AMBIGUITIES RESOLVED, REPORTED RATHER THAN PAPERED OVER

  a. §1 names the pairing site `_build_diff`, s3_verify.py:2231.  HEAD has no
     `_build_diff`; line 2231 is the `undeclared_terms` entry of the dict
     literal inside `compute_diff`, whose body is exactly the bare set
     difference the contract quotes.  Read as `compute_diff`, and every pin
     drives it through the REAL caller's shape (`compute_diff` for the diff,
     `assemble_report` for the config-bearing seam) so the pairing is found
     wherever between the two it was implemented.
  b. §1 "a NEW report key `term_disputes`".  The `deception_advisories`
     precedent it cites is a TOP-LEVEL optional report key, so that is the
     reading `_disputes` prefers — but it also accepts the key inside
     `report["diff"]`, because a diff key is equally "in the report" and
     `_validate_diff` has its own optional set.  The pins hold the CONTENT
     either way and the locator reports which place answered.
  c. §1 leaves the comparator and §2 leaves the `distinguishes` entry shape to
     the implementer.  So the exhibit fixture makes the overlap unmistakable
     under every candidate §1 lists at once — X's `claims.terms[]` entry and
     Y's `claims.term_sites[]` witness share one `path:line` evidence item,
     one frame label and one site prose string — and T2 PROBES the candidate
     `distinguishes` shapes at runtime, failing loudly with all of them named
     if none breaks the dispute.  No private name is guessed anywhere.
  d. Evidence sites deliberately share ONE path (`game.py`) and differ by LINE,
     which is the shape a real one-file generated game has.  A comparator that
     pairs on `path` alone would pair every finding in such a game with every
     other, and T3 is where that surfaces — the contract's "an undeclared term
     with NO declared neighbor sharing evidence" has no meaning if a shared
     filename is enough.
  e. §3's second half ("`dead-spec-term` findings whose term is the Y of a live
     dispute") is pinned in the one construction where it is coherent: Y
     witnessed in `claims.term_sites[]` (so there IS a grounding to share) and
     absent from `claims.terms[]` (so the diff calls it dead).  The contract
     asks the implementer to "measure whether the exhibit exercises this and
     say", so `test_t1e_*` is kept as its own pin, readable on its own.
  f. T5 "`gen run --dry-run`'s resolved config".  `cmd_run`'s dry-run branch
     reads the real `config/` and `out/batches/` for the next id and seed and
     then runs `preflight`, which probes this machine — none of which is
     hermetic.  Pinned instead at the importable seam `cmd_run` itself uses and
     `build_config`'s own docstring names: `build_config` (tmp roots) plus
     `render_config`, which IS the text the dry run prints and the bytes a real
     run writes.
  g. T5 "an explicit `reject` survives materialization".  Read as the config of
     record being honoured: a resolved config pinned back to `reject` keeps
     that value through `render_config` -> `load_config` AND still rejects the
     disputed finding end to end under the materialized template, while the
     unmodified materialized config records it.  No CLI flag sets this knob, so
     after-the-overlay is the only way an explicit value can exist.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from gen import cli, s3_verify
from gen.config import REPO_ROOT, load_config

CONTRACT = "docs/v2/contracts/Q-1-term-attribution.md"
TESTS_DIR = Path(__file__).resolve().parent
TOY_WORKER = TESTS_DIR / "toy_worker"
TEMPLATE_PATH = REPO_ROOT / "config" / "template.yaml"
#: The vendored canon snapshot (contract P-2) — tracked in THIS repo, so no
#: duckWM sibling is read. Nothing here writes to it.
CANON_ROOT = REPO_ROOT / "canon"

# --- the contract's own vocabulary ------------------------------------------

#: §3 THE ACTION KNOB: "`verifier.term_dispute_action: reject (default, today's
#: bytes) | record`".
BLOCK = "verifier"
KNOB = "term_dispute_action"
REJECT, RECORD = "reject", "record"
#: §1: "Pairs land in a NEW report key `term_disputes`".
DISPUTES_KEY = "term_disputes"
#: §2: "must carry a `distinguishes` field".
DISTINGUISHES = "distinguishes"

#: §The measured class, the four signed 71-vocab terms of the exhibit, as "two
#: ADJACENT pairs, one game" — the undeclared name the auditor reported, and the
#: declared neighbour whose behaviour it is claiming.
RECALL = "info.recall"  # "required state was shown but is no longer displayed"
ECHO = "agent.echo"  # "an entity's behavior replays the player's own action history"
KEYED = "terrain.keyed"  # "passability conditioned on an avatar-carried attribute"
GATE = "gate.key"  # "collectible unlocks barrier"
#: A declared term with a grounding of its own that nothing disputes.
CLEAN = "move.grid"
#: T3's undeclared term with no declared neighbour anywhere near its evidence.
LONE = "info.legend"
EXHIBIT_TERMS = (RECALL, ECHO, KEYED, GATE)
ALL_TERMS = (*EXHIBIT_TERMS, CLEAN, LONE)

VERDICT_PASS, VERDICT_REJECT = "pass", "reject"
MODE_FULL = "full"
GAME_ID = "q1-term-attribution-synthetic"
SYNTHETIC = "synthetic Q-1 blind fixture"

#: One observed site per behaviour.  THE SAME `path` throughout and a distinct
#: `line`, `frame` and `prose` each — see ambiguity (d).  The frame labels are
#: the checked-in toy worker's own captured labels (`_fixture_wall` holds that).
SITES: dict[str, dict[str, Any]] = {
    CLEAN: {"line": 12, "frame": "reset",
            "prose": "the four-way step in Avatar.move (game.py:12)"},
    ECHO: {"line": 184, "frame": "step-10:ACTION2",
           "prose": "the trail buffer replayed in Entity.advance (game.py:184)"},
    GATE: {"line": 211, "frame": "step-20:ACTION4",
           "prose": "the carried-token test in Avatar.can_enter (game.py:211)"},
    LONE: {"line": 303, "frame": "final",
           "prose": "the standalone key-colour strip in render (game.py:303)"},
}
SITE_PATH = "game.py"


def _surface(module: Any, name: str, what: str) -> Any:
    """The named attribute, or a LOUD failure quoting the contract clause.

    The blind lane has one file and no handback inside pytest, so a promised
    surface that never landed has to be a red test with the promise in it —
    never a skip, which would read as "nothing to measure here".
    """
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(
            f"{module.__name__} exposes no {name!r} — {CONTRACT} {what}. Every pin that "
            f"depends on it is therefore unmeasurable, which is a contract failure and "
            f"not a reason to skip"
        )
    return value


# --- the exhibit, built hermetically ----------------------------------------


@dataclass(frozen=True)
class Pair:
    """One misattribution: the undeclared name X, and the declared neighbour Y.

    §The rule: "an undeclared term X is DISPUTED by declared term Y when X's
    claim entry and Y's witness grounding share observed evidence".  `site`
    names the ONE behaviour both of them are grounded on.
    """

    undeclared: str
    declared: str
    site: str
    #: §2's field, as it would arrive on X's claim entry.  `None` = absent.
    distinguishes: Any = None
    #: Arbitrary extra keys on X's entry — T2's control for a comparator that
    #: pairs on whole-entry identity rather than on evidence.
    extra: Mapping[str, Any] = field(default_factory=dict)
    #: §3's second half: Y grounded ONLY in the site inventory, so the diff
    #: calls it a `dead-spec-term` while the dispute is live (ambiguity (e)).
    witness_only: bool = False


def _evidence(site: str) -> list[dict]:
    """One `path:line` item — the shape `_check_evidence` takes."""
    spot = SITES[site]
    return [{"path": SITE_PATH, "line": spot["line"], "note": spot["prose"]}]


def _grounding(site: str) -> dict:
    """Everything one observed site offers a comparator, in one place.

    §1 lists "shared frame labels and/or shared site text" as the candidates
    beside the evidence items, so a claim grounded here carries all three and a
    pairing built on any one of them finds the overlap (ambiguity (c)).
    """
    return {"evidence": _evidence(site), "frame_refs": [SITES[site]["frame"]]}


def _term_entry(term: str, site: str, **extra: Any) -> dict:
    return {"term": term, "reachable": True, **_grounding(site), **extra}


def _site_entry(term: str, site: str) -> dict:
    return {"term": term, "site": SITES[site]["prose"], **_grounding(site)}


def _build(pairs: tuple[Pair, ...] = (), lone: tuple[str, ...] = ()) -> tuple[dict, dict]:
    """(claims, spec) for one audit round — the contract's exhibit, in tmp.

    The spec declares `move.grid` plus every pair's Y; the reply reports every
    pair's X as reachable on Y's own site, and every `lone` term on a site of
    its own that no declared term is anywhere near.
    """
    declared = [CLEAN, *(pair.declared for pair in pairs)]
    terms = [_term_entry(CLEAN, CLEAN)]
    sites = [_site_entry(CLEAN, CLEAN)]
    for pair in pairs:
        if not pair.witness_only:
            # Y, seen and reachable, grounded on the shared behaviour.
            terms.append(_term_entry(pair.declared, pair.site))
        # Y's witness grounding — "`claims.term_sites[]` carries one site per
        # declared term" — on that same behaviour.
        sites.append(_site_entry(pair.declared, pair.site))
        extra = dict(pair.extra)
        if pair.distinguishes is not None:
            extra[DISTINGUISHES] = pair.distinguishes
        terms.append(_term_entry(pair.undeclared, pair.site, **extra))
    for term in lone:
        terms.append(_term_entry(term, term))
    claims = {
        "terms": terms,
        "dead_code": [],
        "deceptions": [],
        "enforcement": [],
        "notes": SYNTHETIC,
        s3_verify.TERM_SITES_KEY: sites,
    }
    spec = {"game": {"terms": declared, "knobs": {"deceptions": []}}}
    return claims, spec


#: The contract's exhibit exactly: "`info.recall` … and `terrain.keyed` …
#: REACHABLE in a game whose spec declares `agent.echo` … and `gate.key`".
EXHIBIT = (Pair(RECALL, ECHO, ECHO), Pair(KEYED, GATE, GATE))
#: The blind brief's "one shared behavior site" in its narrowest form.
ONE_SITE = (Pair(RECALL, ECHO, ECHO),)


def _agent(claims: dict) -> dict:
    return {
        "session_id": "synthetic-1",
        "model": "synthetic",
        "usd": 0.0,
        "tokens_in": 1,
        "tokens_out": 1,
        "wall_s": 0.0,
        "staged_copy_verified": True,
        "claims": claims,
    }


def _cfg(action: object = None, **verifier: object) -> dict:
    """The minimum `assemble_report` reads, with Q-1's knob set or absent."""
    cfg: dict = {"duckwm_docs": str(CANON_ROOT), BLOCK: dict(verifier)}
    if action is not None:
        cfg[BLOCK][KNOB] = action
    return cfg


class _Slot:
    """One planted slot: a copied worker dir, and as many FULL rounds as wanted.

    A round goes through `compute_diff` (the pure declared-vs-detected seam the
    contract's §1 points at) and then `assemble_report`, which is where the
    run's CONFIG, its diff and the reply's claims are all in hand — the seam the
    L-1 knob already uses.  Driving the real pair is what lets these pins find
    the pairing wherever between the two it landed (ambiguity (a)).
    """

    def __init__(self, root: Path, cap: object) -> None:
        import shutil

        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.worker = root / "slot-1"
        shutil.copytree(TOY_WORKER, self.worker, ignore=shutil.ignore_patterns("__pycache__"))
        self.frames_path = root / s3_verify.FRAMES_NAME
        self.frames_path.write_text("{}", encoding="utf-8")
        self._cap = cap

    def run(self, cfg: dict, pairs: tuple[Pair, ...] = (),
            lone: tuple[str, ...] = ()) -> dict:
        claims, spec = _build(pairs, lone)
        diff = s3_verify.compute_diff(claims, spec)
        try:
            return s3_verify.assemble_report(
                game_id=GAME_ID,
                worker=self.worker,
                mode=MODE_FULL,
                cfg=cfg,
                cap=self._cap,
                checks=[],
                frames_path=self.frames_path,
                agent=_agent(claims),
                diff=diff,
                spec_hash=None,
            )
        except TypeError as exc:  # pragma: no cover - a signature deviation
            pytest.fail(
                f"{CONTRACT} §1 computes the pairing from the claims a real round already "
                f"carries, and `assemble_report` would not take this run: {exc}. A new "
                f"REQUIRED argument at this seam is a deviation the contract does not "
                f"license — the config, the diff and `agent.claims` are all already here"
            )


@pytest.fixture(scope="session")
def cap() -> object:
    """A real FrameCapture off the checked-in toy worker (the b7 harness shape)."""
    game_cls, solver_cls = s3_verify.load_worker_classes(TOY_WORKER)
    return s3_verify.capture(game_cls, solver_cls)


@pytest.fixture
def slot(tmp_path: Path, cap: object) -> _Slot:
    return _Slot(tmp_path / "slot", cap)


# --- reading the new key, without guessing a private name -------------------


def _disputes(report: Mapping) -> tuple[Any, str]:
    """(`term_disputes`, where it was found) — or a loud contract failure.

    Ambiguity (b): top level is the `deception_advisories` precedent §1 cites
    and is preferred; inside `report["diff"]` is accepted, because a diff key is
    equally "a NEW report key" and `_validate_diff` keeps its own optional set.
    """
    if DISPUTES_KEY in report:
        return report[DISPUTES_KEY], f"report.{DISPUTES_KEY}"
    diff = report.get("diff")
    if isinstance(diff, Mapping) and DISPUTES_KEY in diff:
        return diff[DISPUTES_KEY], f"report.diff.{DISPUTES_KEY}"
    pytest.fail(
        f"{CONTRACT} §1: the pairs 'land in a NEW report key {DISPUTES_KEY!r} (additive; "
        f"ALWAYS WRITTEN WHEN COMPUTABLE)'. This report carries no such key at the top "
        f"level and none inside its diff. Top-level keys: {sorted(report)}; diff keys: "
        f"{sorted(diff) if isinstance(diff, Mapping) else diff!r}"
    )


def _pairs_named(value: object, where: str) -> list[frozenset[str]]:
    """Each dispute entry as the set of fixture terms it names.

    §1 leaves "the dispute key's entry shape" to the implementer, so the entries
    are read for their CONTENT: one entry per pair, naming both the undeclared
    term and the declared one it is disputed by.  A list of records and a
    mapping keyed by term both read correctly here.
    """
    if isinstance(value, Mapping):
        entries: list[object] = [{"key": key, "value": item} for key, item in value.items()]
    elif isinstance(value, list):
        entries = list(value)
    else:
        pytest.fail(
            f"{CONTRACT} §1 has the pairs land in {where} as records a reader can act on; "
            f"it holds a {type(value).__name__}: {value!r}"
        )
    found: list[frozenset[str]] = []
    for entry in entries:
        text = json.dumps(entry, sort_keys=True, default=str)
        found.append(frozenset(term for term in ALL_TERMS if term in text))
    return found


def _codes(rows: list[dict]) -> list[str]:
    return [row["code"] for row in rows]


def _rejected_terms(report: Mapping) -> list[str]:
    """Every term the verdict rejects on, under either term code."""
    term_codes = (s3_verify.REJECT_UNDECLARED_TERM, s3_verify.REJECT_DEAD_SPEC_TERM)
    return [row.get("term") for row in report["reject_reasons"] if row["code"] in term_codes]


def _undeclared_rejects(report: Mapping) -> list[str]:
    return [
        row.get("term")
        for row in report["reject_reasons"]
        if row["code"] == s3_verify.REJECT_UNDECLARED_TERM
    ]


def _comparable(report: dict) -> dict:
    """A report with the one per-run value that is never equal stripped."""
    out = copy.deepcopy(report)
    out.pop("worker", None)
    return out


# --- the fixture wall -------------------------------------------------------


def test_fixture_wall_the_exhibits_four_terms_are_signed_vocabulary() -> None:
    """§The measured class calls them "four signed 71-vocab terms".

    The fixture stands on that: a term outside the closed vocabulary would be
    refused by `validate_claims` long before any dispute could be computed, so
    a red here means this file's transcription of the exhibit is wrong and
    every other pin in it is unmeasurable.
    """
    vocab = s3_verify.signed_vocab()
    missing = [term for term in ALL_TERMS if term not in vocab]
    assert not missing, (
        f"fixture wall: {CONTRACT} §The measured class names {list(EXHIBIT_TERMS)} as signed "
        f"vocabulary terms, and {missing} are not in the {len(vocab)}-term set"
    )


def test_fixture_wall_the_claims_this_file_fabricates_are_legal_claims(cap: object) -> None:
    """The exhibit must be a reply the stage would really accept.

    `validate_claims` is the gate a live round passes before any diff is built,
    so a fixture it refuses would pin nothing about the real path.  The frame
    labels are checked against the REAL capture for the same reason: §1 names
    "shared frame labels" as a comparator candidate, and a label no capture
    carries could never be the thing two claims shared.
    """
    labels = {record.label for record in cap.records}
    used = {spot["frame"] for spot in SITES.values()}
    assert used <= labels, (
        f"fixture wall: {CONTRACT} §1 names 'shared frame labels' as a pairing candidate, so "
        f"this file grounds its claims on real captured labels; {sorted(used - labels)} are "
        f"not in the toy worker's capture ({sorted(labels)})"
    )
    assert len(used) == len(SITES), (
        "fixture wall: each site must carry a DISTINCT frame label, or T3's undisputed term "
        f"shares a label with a declared one by accident: {sorted(used)}"
    )
    claims, _spec = _build(EXHIBIT, lone=(LONE,))
    s3_verify.validate_claims(claims, s3_verify.signed_vocab(), labels)


def test_fixture_wall_the_exhibit_is_the_bare_set_difference_the_contract_quotes() -> None:
    """§The measured class: "the diff is a bare set difference (`_build_diff`,
    s3_verify.py:2231 — `undeclared_terms = reachable - declared`)".

    The pre-Q-1 behaviour, stated as the baseline every other pin moves from:
    both exhibit terms come back undeclared and the two declared neighbours are
    not in that list at all.  Green on both sides of the contract — Q-1 §3 says
    the knob moves a ROW, it does not edit the audit.
    """
    claims, spec = _build(EXHIBIT)
    diff = s3_verify.compute_diff(claims, spec)
    assert diff["undeclared_terms"] == sorted([RECALL, KEYED]), (
        f"fixture wall: {CONTRACT} §The measured class reports {RECALL!r} and {KEYED!r} "
        f"reachable-but-undeclared; the diff says {diff['undeclared_terms']}"
    )
    assert diff["dead_spec_terms"] == [], diff["dead_spec_terms"]
    assert sorted(diff["terms_declared"]) == sorted([CLEAN, ECHO, GATE])


# --- T1 — the pairing, and what `record` does with it -----------------------


@pytest.mark.parametrize("pairs,label", [(EXHIBIT, "both adjacent pairs"),
                                         (ONE_SITE, "one shared behavior site")])
def test_t1a_one_behavior_under_two_names_yields_a_term_disputes_pair(
    slot: _Slot, pairs: tuple[Pair, ...], label: str
) -> None:
    """T1: "a fixture audit reply grounding one behavior under two names
    (undeclared X evidence == declared Y site) yields a `term_disputes` pair".

    §1: the pairs are written "always … when computable", so this reads them off
    a DEFAULT-knob report: the record of the dispute does not depend on the
    action taken about it.
    """
    report = slot.run(_cfg(), pairs)
    value, where = _disputes(report)
    named = _pairs_named(value, where)
    for pair in pairs:
        wanted = {pair.undeclared, pair.declared}
        assert any(wanted <= entry for entry in named), (
            f"{CONTRACT} T1 ({label}): {pair.undeclared!r}'s claim entry and "
            f"{pair.declared!r}'s witness grounding share one site — the same path+line "
            f"evidence item, the same frame label and the same site prose — so §1 pairs "
            f"them. {where} holds {named}: no entry names both"
        )
    assert len(named) == len(pairs), (
        f"{CONTRACT} §1 pairs an undeclared term with the declared term it is disputed by, "
        f"one entry per dispute; this fixture has {len(pairs)} and {where} holds "
        f"{len(named)}: {named}"
    )


def test_t1b_under_record_a_disputed_undeclared_term_leaves_the_reject_path(
    tmp_path: Path, cap: object
) -> None:
    """T1: "under `record` the slot's verdict carries no undeclared-term reject
    for X"; §3: "DISPUTED undeclared-term findings leave the reject path and
    ride `term_disputes` as advisories"."""
    recorded = _Slot(tmp_path / "record", cap).run(_cfg(RECORD), EXHIBIT)
    assert _undeclared_rejects(recorded) == [], (
        f"{CONTRACT} T1: under {RECORD!r} the verdict carries NO undeclared-term reject for a "
        f"disputed term; it rejects on {recorded['reject_reasons']!r}"
    )
    assert recorded["verdict"] == VERDICT_PASS, (
        f"{CONTRACT} §3: both of this fixture's findings are disputes, so nothing is left to "
        f"reject on — the verdict is {recorded['verdict']!r} because of "
        f"{recorded['reject_reasons']!r}"
    )
    # §3 "ride `term_disputes` as advisories": the finding is RECORDED, not dropped.
    value, where = _disputes(recorded)
    named = _pairs_named(value, where)
    for pair in EXHIBIT:
        assert any({pair.undeclared, pair.declared} <= entry for entry in named), (
            f"{CONTRACT} §3: a disputed finding 'rides {DISPUTES_KEY}' rather than vanishing; "
            f"{pair.undeclared!r} is not in {where} ({named})"
        )
    # …and the audit itself is untouched: §3 moves a row, it does not edit the diff.
    assert recorded["diff"]["undeclared_terms"] == sorted([RECALL, KEYED]), (
        f"{CONTRACT} §The rule: the finding is 'an ATTRIBUTION DISPUTE, not a defect' — a "
        f"policy about where it LANDS. The diff still names what the audit found: "
        f"{recorded['diff']['undeclared_terms']}"
    )


def test_t1c_under_the_default_the_same_dispute_rejects_as_today(
    tmp_path: Path, cap: object
) -> None:
    """T1: "under default it rejects as today"; §3: "`reject (default, today's
    bytes)`"; §4: "Config default absent = byte-identical today, pinned"."""
    absent = _Slot(tmp_path / "absent", cap).run(_cfg(), EXHIBIT)
    explicit = _Slot(tmp_path / "explicit", cap).run(_cfg(REJECT), EXHIBIT)
    for name, report in (("absent", absent), (f"{KNOB}: {REJECT}", explicit)):
        assert report["verdict"] == VERDICT_REJECT, (
            f"{CONTRACT} §3: with the knob {name} the dispute 'rejects exactly as today'; "
            f"this report is a {report['verdict']!r}"
        )
        assert sorted(_undeclared_rejects(report)) == sorted([RECALL, KEYED]), (
            f"{CONTRACT} T1 (knob {name}): today's bytes reject on BOTH undeclared terms; "
            f"got {report['reject_reasons']!r}"
        )
    assert _comparable(absent) == _comparable(explicit), (
        f"{CONTRACT} §3: `{KNOB}: {REJECT}` IS the absent key — 'today's bytes' — and these "
        f"two reports differ"
    )


def test_t1d_the_record_mode_report_is_the_default_report_with_the_rows_moved(
    tmp_path: Path, cap: object
) -> None:
    """§3 read against its own L-1 precedent: `record` "leave[s] the reject
    path" and nothing else moves.

    The two reports are compared key by key, so a `record` run that also
    rewrote the diff, the checks or the agent block is a red here rather than a
    surprise at the S5 review.
    """
    default = _Slot(tmp_path / "default", cap).run(_cfg(), EXHIBIT)
    recorded = _Slot(tmp_path / "record", cap).run(_cfg(RECORD), EXHIBIT)
    # The false-green guard: "nothing else moved" is trivially true of a tree
    # where nothing moved at all, so the move itself is asserted first.
    assert recorded["verdict"] == VERDICT_PASS and recorded["reject_reasons"] == [], (
        f"{CONTRACT} §3: under {RECORD!r} this all-disputes round has nothing left to reject "
        f"on, so there is a move for this pin to bound. It rejects on "
        f"{recorded['reject_reasons']!r} — T1 is where that is the finding"
    )
    moved = {"verdict", "reject_reasons", DISPUTES_KEY}
    for key in sorted(set(default) | set(recorded)):
        if key in moved or key == "worker":
            continue
        assert default.get(key) == recorded.get(key), (
            f"{CONTRACT} §3 moves DISPUTED undeclared-term findings off the reject path and "
            f"changes nothing else; report[{key!r}] differs between the two modes:\n"
            f"  {REJECT}: {default.get(key)!r}\n  {RECORD}: {recorded.get(key)!r}"
        )
    # The rows the default rejected on are the ones `record` now carries.
    assert _codes(default["reject_reasons"]) == [s3_verify.REJECT_UNDECLARED_TERM] * 2, (
        f"fixture wall: the default report should reject on two undeclared terms, got "
        f"{default['reject_reasons']!r}"
    )


def test_t1e_a_dead_spec_term_that_is_the_y_of_a_live_dispute_is_treated_the_same(
    tmp_path: Path, cap: object
) -> None:
    """§3: "`dead-spec-term` findings whose term is the Y of a live dispute are
    treated the same way (the two halves of one misattribution must not count
    twice)".

    Built in the one construction where that clause is coherent (ambiguity (e)):
    `agent.echo` is grounded in the reply's SITE INVENTORY — so there is a
    witness grounding for X to share — and absent from `claims.terms`, which is
    what makes the diff call it dead.  One behaviour, two names, two findings,
    and §3 says they are one misattribution.
    """
    pairs = (Pair(RECALL, ECHO, ECHO, witness_only=True),)
    claims, spec = _build(pairs)
    baseline = s3_verify.compute_diff(claims, spec)
    assert baseline["dead_spec_terms"] == [ECHO] and baseline["undeclared_terms"] == [RECALL], (
        f"fixture wall: this fixture must produce BOTH halves of one misattribution — "
        f"dead {ECHO!r} and undeclared {RECALL!r}; the diff says "
        f"dead={baseline['dead_spec_terms']} undeclared={baseline['undeclared_terms']}"
    )
    default = _Slot(tmp_path / "default", cap).run(_cfg(), pairs)
    assert sorted(_rejected_terms(default)) == sorted([ECHO, RECALL]), (
        f"fixture wall: today's bytes reject on both halves; got {default['reject_reasons']!r}"
    )
    recorded = _Slot(tmp_path / "record", cap).run(_cfg(RECORD), pairs)
    assert _rejected_terms(recorded) == [], (
        f"{CONTRACT} §3: the dead-spec half of a live dispute 'is treated the same way' — "
        f"'the two halves of one misattribution must not count twice'. Under {RECORD!r} this "
        f"report still rejects on {recorded['reject_reasons']!r}"
    )
    value, where = _disputes(recorded)
    assert any({RECALL, ECHO} <= entry for entry in _pairs_named(value, where)), (
        f"{CONTRACT} §3: the misattribution must be ON THE RECORD once — {where} names no "
        f"entry carrying both {RECALL!r} and {ECHO!r}"
    )


# --- T2 — the auditor can break a dispute -----------------------------------

#: §2: "a `distinguishes` field: the declared term it is NOT, plus the
#: definitional clause separating them".  The ENTRY SHAPE is open (ambiguity
#: (c)), so these are the candidates, probed in order; the clause itself is the
#: contract's own reason the two terms are not the same mechanic.
CLAUSE = (
    "agent.echo replays the player's own action history; this entity shows state "
    "that was displayed and no longer is, which is info.recall's clause"
)


def _distinguishes_candidates(declared: str) -> list[tuple[str, Any]]:
    return [
        ("{term, clause}", {"term": declared, "clause": CLAUSE}),
        ("{term, because}", {"term": declared, "because": CLAUSE}),
        ("{not, clause}", {"not": declared, "clause": CLAUSE}),
        ("{declared_term, clause}", {"declared_term": declared, "clause": CLAUSE}),
        ("{term, detail}", {"term": declared, "detail": CLAUSE}),
        ("{term, note}", {"term": declared, "note": CLAUSE}),
        ("one string", f"{declared}: {CLAUSE}"),
    ]


def _require_live_dispute(root: Path, cap: object) -> None:
    """Refuse to measure §2 until §1's dispute is actually holding.

    THE FALSE-GREEN GUARD, and the reason every T2 pin opens with it: §2's field
    is a BREAK, and a break can only be observed against something unbroken. On
    a tree where the pairing does not exist, every finding rejects under
    `record` for the trivial reason, which would read as "the `distinguishes`
    citation worked" when nothing did. So the baseline — the SAME exhibit, no
    `distinguishes` anywhere — is measured first, and a red here points at T1.
    """
    pairs = (Pair(RECALL, ECHO, ECHO),)
    report = _Slot(root, cap).run(_cfg(RECORD), pairs)
    assert _undeclared_rejects(report) == [], (
        f"{CONTRACT} §2's {DISTINGUISHES!r} field is a BREAK of the §1 dispute, and on this "
        f"tree the dispute is not holding in the first place: with NO {DISTINGUISHES!r} on "
        f"the entry at all, {RECALL!r} still rejects under {RECORD!r} "
        f"({report['reject_reasons']!r}). T1 is where that is the finding — this pin has no "
        f"subject until the pairing lands, and it must not read as §2 working"
    )


def _breaks_the_dispute(root: Path, cap: object, value: Any) -> tuple[bool, str]:
    """Does X reject under `record` when its entry carries this `distinguishes`?

    Any refusal of the shape — in `validate_claims` or in the stage — means it
    is not the implementer's shape, which is information, not a failure: the
    probe moves on and `test_t2a_*` fails only if NO candidate breaks anything.
    """
    pairs = (Pair(RECALL, ECHO, ECHO, distinguishes=value),)
    claims, _spec = _build(pairs)
    try:
        s3_verify.validate_claims(claims, s3_verify.signed_vocab(),
                                  {record.label for record in cap.records})
    except Exception as exc:  # noqa: BLE001 — a refused shape is a probe result
        return False, f"validate_claims refused it: {type(exc).__name__}: {exc}"
    try:
        report = _Slot(root, cap).run(_cfg(RECORD), pairs)
    except Exception as exc:  # noqa: BLE001 — same
        return False, f"the stage refused it: {type(exc).__name__}: {exc}"
    rejects = _undeclared_rejects(report)
    return (RECALL in rejects), f"undeclared-term rejects under record: {rejects}"


def test_t2a_a_wellformed_distinguishes_makes_the_finding_undisputed(
    tmp_path: Path, cap: object
) -> None:
    """T2: "a `distinguishes` field naming the declared term + a clause makes X
    undisputed: it rejects even under `record`"; §2: "A present, well-formed
    `distinguishes` (validated: names a DECLARED term, non-empty text) makes
    the finding UNDISPUTED regardless of evidence overlap"."""
    _require_live_dispute(tmp_path / "baseline", cap)
    tried: list[str] = []
    for index, (name, value) in enumerate(_distinguishes_candidates(ECHO)):
        broke, detail = _breaks_the_dispute(tmp_path / f"probe-{index}", cap, value)
        tried.append(f"  {name}: {detail}")
        if broke:
            return
    pytest.fail(
        f"{CONTRACT} T2 / §2: a present, well-formed {DISTINGUISHES!r} naming the DECLARED "
        f"term and carrying the clause that separates them 'makes the finding UNDISPUTED "
        f"regardless of evidence overlap' — so {RECALL!r} must reject even under {RECORD!r}. "
        f"None of the candidate entry shapes did (§2 leaves the shape open, so all of them "
        f"were probed):\n" + "\n".join(tried)
    )


def test_t2b_a_distinguishes_naming_a_term_the_spec_never_declared_is_not_a_break(
    tmp_path: Path, cap: object
) -> None:
    """§2: the break is "validated: names a DECLARED term, non-empty text".

    `info.legend` is in the signed vocabulary and is NOT declared by this spec,
    so citing it separates the finding from nothing the game promised.  Either
    outcome closes the clause — the stage refuses the reply loudly, or the
    dispute stands — and a red here means a malformed citation bought the
    auditor a reject it had not earned.
    """
    _require_live_dispute(tmp_path / "baseline", cap)
    for name, value in _distinguishes_candidates(LONE):
        pairs = (Pair(RECALL, ECHO, ECHO, distinguishes=value),)
        try:
            report = _Slot(tmp_path / f"undeclared-{abs(hash(name))}", cap).run(
                _cfg(RECORD), pairs
            )
        except Exception:  # noqa: BLE001, S112 — a loud refusal is one of two legal answers
            continue
        assert _undeclared_rejects(report) == [], (
            f"{CONTRACT} §2 validates the break: {DISTINGUISHES!r} must name a DECLARED term. "
            f"This one ({name}) names {LONE!r}, which the spec never declared, and the "
            f"finding was treated as UNDISPUTED anyway: {report['reject_reasons']!r}"
        )


def test_t2c_a_distinguishes_with_no_clause_is_not_a_break(
    tmp_path: Path, cap: object
) -> None:
    """§2: "validated: names a DECLARED term, NON-EMPTY TEXT".

    The declared term is right and the clause is missing or blank, which is the
    bare contradiction ("it is not Y") the contract's whole point is to refuse:
    "no future finding can claim a neighbor's behavior without saying why".
    """
    empties: list[tuple[str, Any]] = [
        ("{term} alone", {"term": ECHO}),
        ("{term, clause: ''}", {"term": ECHO, "clause": ""}),
        ("{term, clause: '   '}", {"term": ECHO, "clause": "   "}),
        ("{not, clause: ''}", {"not": ECHO, "clause": ""}),
        ("bare term string", ECHO),
    ]
    _require_live_dispute(tmp_path / "baseline", cap)
    for index, (name, value) in enumerate(empties):
        pairs = (Pair(RECALL, ECHO, ECHO, distinguishes=value),)
        try:
            report = _Slot(tmp_path / f"empty-{index}", cap).run(_cfg(RECORD), pairs)
        except Exception:  # noqa: BLE001, S112 — a loud refusal is one of two legal answers
            continue
        assert _undeclared_rejects(report) == [], (
            f"{CONTRACT} §2: the break is well-formed only with 'non-empty text' — the "
            f"'definitional clause separating them'. {name} carries none and the finding was "
            f"treated as UNDISPUTED: {report['reject_reasons']!r}. §Live acceptance: 'no "
            f"future finding can claim a neighbor's behavior without saying why'"
        )


def test_t2d_an_unrelated_extra_field_does_not_break_the_dispute(
    tmp_path: Path, cap: object
) -> None:
    """§2's control: the BREAK is `distinguishes`, nothing else.

    A comparator that pairs on whole-entry identity would be broken by any new
    key at all, which would make §2's field look like it worked while anything
    else worked too.  This entry carries a plausible-looking neighbour field
    and no `distinguishes`, so the dispute must stand.
    """
    _require_live_dispute(tmp_path / "baseline", cap)
    pairs = (Pair(RECALL, ECHO, ECHO,
                  extra={"confidence": "high", "note": CLAUSE, "adjacent_to": ECHO}),)
    report = _Slot(tmp_path / "extra", cap).run(_cfg(RECORD), pairs)
    assert _undeclared_rejects(report) == [], (
        f"{CONTRACT} §2: only a present, well-formed {DISTINGUISHES!r} makes a finding "
        f"undisputed. This entry carries other fields instead and the dispute stopped "
        f"holding: {report['reject_reasons']!r} — a comparator that keys on the whole claim "
        f"entry rather than on its shared EVIDENCE will also pass T2 for the wrong reason"
    )
    value, where = _disputes(report)
    assert any({RECALL, ECHO} <= entry for entry in _pairs_named(value, where)), (
        f"{CONTRACT} §1: the evidence overlap is unchanged by an unrelated field, so the pair "
        f"is still in {where}; it holds {_pairs_named(value, where)}"
    )


# --- T3 — no neighbour, no dispute ------------------------------------------


@pytest.mark.parametrize("action", [None, REJECT, RECORD])
def test_t3a_an_undeclared_term_with_no_sharing_neighbour_rejects_under_both_knobs(
    tmp_path: Path, cap: object, action: object
) -> None:
    """T3: "an undeclared term with NO declared neighbor sharing evidence is
    undisputed and rejects under both knob values"; §3: "UNDISPUTED findings
    reject exactly as today"."""
    report = _Slot(tmp_path / f"lone-{action}", cap).run(_cfg(action), lone=(LONE,))
    assert report["verdict"] == VERDICT_REJECT, (
        f"{CONTRACT} T3: with the knob {action!r} an undisputed undeclared term still "
        f"rejects; this report is a {report['verdict']!r}"
    )
    assert _undeclared_rejects(report) == [LONE], (
        f"{CONTRACT} §3: 'UNDISPUTED findings reject exactly as today' — with the knob "
        f"{action!r} the reasons are {report['reject_reasons']!r}"
    )
    if action == RECORD:
        value, where = _disputes(report)
        assert _pairs_named(value, where) == [], (
            f"{CONTRACT} T3: {LONE!r} shares its site with no declared term, so there is no "
            f"dispute to record; {where} holds {value!r}"
        )


def test_t3b_a_lone_finding_beside_a_dispute_is_the_only_one_left(
    slot: _Slot
) -> None:
    """T3 + §3 together: `record` is per-FINDING, not per-report.

    One disputed term and one undisputed one in a single round: the dispute
    leaves the reject path and the lone finding still decides the verdict,
    alone — the L-1 shape ("a lever + a term is still a reject that names only
    the term") applied to Q-1's own two classes.
    """
    report = slot.run(_cfg(RECORD), EXHIBIT, lone=(LONE,))
    assert report["verdict"] == VERDICT_REJECT, (
        f"{CONTRACT} §3: an UNDISPUTED finding rejects, whatever rode beside it; this report "
        f"is a {report['verdict']!r}"
    )
    assert _undeclared_rejects(report) == [LONE], (
        f"{CONTRACT} T3: the reject must name ONLY {LONE!r} — the two disputed terms left the "
        f"reject path and this one never entered it. Got {report['reject_reasons']!r}"
    )
    value, where = _disputes(report)
    named = _pairs_named(value, where)
    assert not any(LONE in entry for entry in named), (
        f"{CONTRACT} T3: {LONE!r} is undisputed, so no dispute entry may name it; {where} "
        f"holds {named}"
    )
    assert len(named) == len(EXHIBIT), (
        f"{CONTRACT} §1: one entry per real dispute — {len(EXHIBIT)} here, and {where} holds "
        f"{len(named)}: {named}"
    )


# --- T4 — byte identity, and the additive schema ----------------------------
#
# t4a/t4b/t4c are GREEN ON BOTH SIDES OF THE CONTRACT, by construction:
# `load_config` and the verifier stage both tolerate an unknown `verifier.*`
# key, so on the pre-Q-1 tree all three knob values resolve to the one
# behaviour there is, and these pins measure that they still do afterwards.
# t4d is the exception and the one ABSENCE red in T4 — it holds §1's schema
# half, and a key that does not exist yet cannot be in an optional set.


def test_t4a_on_a_no_dispute_fixture_all_three_knob_values_are_one_report(
    tmp_path: Path, cap: object
) -> None:
    """T4: "byte-identity: knob absent == today's diff, verdicts, and report
    bytes on a no-dispute fixture"; §4: "Config default absent = byte-identical
    today, pinned"; §3: "`reject (default, today's bytes)`".

    Three plantings of one round, three spellings of the knob.  With nothing
    disputed there is nothing for the knob to decide, so `record` is in here
    beside the other two: a run that changes bytes when it changed no outcome
    would make every shipped report's reader ask what the batch's knob was.
    """
    reports = {
        "absent": _Slot(tmp_path / "absent", cap).run(_cfg(), lone=(LONE,)),
        REJECT: _Slot(tmp_path / "reject", cap).run(_cfg(REJECT), lone=(LONE,)),
        RECORD: _Slot(tmp_path / "record", cap).run(_cfg(RECORD), lone=(LONE,)),
    }
    first = _comparable(reports["absent"])
    for name, report in reports.items():
        assert _comparable(report) == first, (
            f"{CONTRACT} T4: on a no-dispute fixture the knob changes NOTHING — 'today's "
            f"diff, verdicts, and report bytes'. The {name!r} report differs from the "
            f"absent-knob one"
        )
    # …and what they all say is today's answer.
    assert reports["absent"]["verdict"] == VERDICT_REJECT
    assert _undeclared_rejects(reports["absent"]) == [LONE]


def test_t4b_the_no_dispute_round_adds_no_key_but_the_contracts_own(
    slot: _Slot
) -> None:
    """T4 "today's … report bytes", in the form the blind lane can measure.

    "Today's bytes" cannot be re-run from here, so it is pinned as the shape:
    with Q-1's own key set aside, the report carries exactly the frozen
    `REPORT_KEYS` plus the optional keys THIS fixture earns, and the diff
    exactly `DIFF_KEYS` plus R-18's inventory key.  A Q-1 that quietly added a
    second key, or dropped one, is red here.
    """
    report = slot.run(_cfg(), lone=(LONE,))
    expected = set(s3_verify.REPORT_KEYS) | {
        s3_verify.TERM_SITES_KEY,  # the reply carried a site inventory
        s3_verify.ADVISORIES_KEY,  # L-1 writes it on every report
    }
    assert set(report) - {DISPUTES_KEY} == expected, (
        f"{CONTRACT} §1 is 'additive' and §4 pins the default to 'byte-identical today'. With "
        f"{DISPUTES_KEY!r} set aside this report's top-level keys should be exactly "
        f"{sorted(expected)}; they are {sorted(report)}"
    )
    diff_expected = set(s3_verify.DIFF_KEYS) | {s3_verify.UNIMPLEMENTED_KEY}
    assert set(report["diff"]) - {DISPUTES_KEY} == diff_expected, (
        f"{CONTRACT} §4: an unconfigured run's diff is the diff it always was; with "
        f"{DISPUTES_KEY!r} set aside it should hold exactly {sorted(diff_expected)} and holds "
        f"{sorted(report['diff'])}"
    )
    assert s3_verify.SCHEMA_VERSION == "b7.1", (
        f"{CONTRACT} §1: an additive, optional key 'so every shipped report keeps validating' "
        f"is NOT a schema bump — the `deception_advisories` precedent it cites "
        f"(got {s3_verify.SCHEMA_VERSION!r})"
    )


def test_t4c_report_validation_accepts_a_report_without_the_new_key(
    slot: _Slot, tmp_path: Path
) -> None:
    """T4: "shipped-report validation accepts reports lacking the new key"; §1:
    "OPTIONAL in report validation so every shipped report keeps validating —
    the deception_advisories precedent".

    A shipped report is reconstructed hermetically rather than read off disk
    (the blind brief's `out/` rule): this round's report with the Q-1 key
    removed, and then with L-1's key removed too, which is the shape of every
    report written before either contract existed.
    """
    report = slot.run(_cfg(), EXHIBIT)
    s3_verify.validate_report(report)

    shipped = copy.deepcopy(report)
    shipped.pop(DISPUTES_KEY, None)
    if isinstance(shipped.get("diff"), Mapping):
        shipped["diff"].pop(DISPUTES_KEY, None)
    s3_verify.validate_report(shipped)

    pre_l1 = copy.deepcopy(shipped)
    pre_l1.pop(s3_verify.ADVISORIES_KEY, None)
    pre_l1.pop(s3_verify.TERM_SITES_KEY, None)
    s3_verify.validate_report(pre_l1)

    # …and off a FILE, which is what S6 and the review actually read.
    path = tmp_path / "shipped.verifier-report.json"
    s3_verify.write_report(shipped, path)
    s3_verify.validate_report(json.loads(path.read_text(encoding="utf-8")))


def test_t4d_the_new_key_is_optional_in_the_schema_never_required(
    slot: _Slot
) -> None:
    """§1: "`term_disputes` (additive; always written when computable; OPTIONAL
    in report validation so every shipped report keeps validating)".

    Where the key landed decides which optional set has to carry it
    (ambiguity (b)), so the pin follows the key.  Green before Q-1: there is no
    key, so there is nothing that could be required.
    """
    report = slot.run(_cfg(), EXHIBIT)
    if DISPUTES_KEY in report:
        assert DISPUTES_KEY in s3_verify.OPTIONAL_REPORT_KEYS, (
            f"{CONTRACT} §1: {DISPUTES_KEY!r} is OPTIONAL in report validation — "
            f"`validate_report` reads reports off disk that were written before this "
            f"contract existed. OPTIONAL_REPORT_KEYS: {list(s3_verify.OPTIONAL_REPORT_KEYS)}"
        )
        assert DISPUTES_KEY not in s3_verify.REPORT_KEYS, (
            f"{CONTRACT} §1: a REQUIRED key would retro-invalidate every shipped b7.1 report"
        )
    elif isinstance(report.get("diff"), Mapping) and DISPUTES_KEY in report["diff"]:
        assert DISPUTES_KEY not in s3_verify.DIFF_KEYS, (
            f"{CONTRACT} §1: {DISPUTES_KEY!r} inside the diff must join the OPTIONAL records, "
            f"not DIFF_KEYS — a required diff key retro-invalidates every shipped report"
        )
    else:
        _disputes(report)  # loud: the key the contract promises is nowhere


# --- T5 — the arming -------------------------------------------------------


def test_t5a_the_cli_overlay_arms_record() -> None:
    """T5: "the CLI overlay arms `record`"; §4: "template.yaml + the CLI
    AUTONOMY_OVERLAY arm `record` (the L-1 pattern …)"."""
    overlay = _surface(cli, "AUTONOMY_OVERLAY", "§4 arms the knob in the CLI AUTONOMY_OVERLAY")
    block = overlay.get(BLOCK)
    assert isinstance(block, Mapping) and block.get(KNOB) == RECORD, (
        f"{CONTRACT} §4: AUTONOMY_OVERLAY gains {BLOCK}.{KNOB}: {RECORD!r} (the L-1 pattern). "
        f"Its {BLOCK!r} block is {block!r}"
    )


def test_t5b_the_template_arms_record_and_nothing_else_was_retro_armed() -> None:
    """§4: "template.yaml + the CLI AUTONOMY_OVERLAY arm `record` … Config
    default absent = byte-identical today, pinned".

    The template is the armed-recommended file; a BATCH config of record is not,
    unless its own text carries the dated recorded amendment §Live acceptance
    describes ("Unpark two-keys-one-echo under a dated recorded amendment").
    """
    tree = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert (tree.get(BLOCK) or {}).get(KNOB) == RECORD, (
        f"{CONTRACT} §4: `config/template.yaml` arms {KNOB}: {RECORD!r}; its {BLOCK!r} block "
        f"is {tree.get(BLOCK)!r}"
    )
    armed = []
    for path in sorted((REPO_ROOT / "config").glob("*.yaml")):
        if path.name == TEMPLATE_PATH.name:
            continue
        raw = path.read_text(encoding="utf-8")
        block = (yaml.safe_load(raw) or {}).get(BLOCK)
        if (isinstance(block, Mapping) and KNOB in block
                and "RECORDED OPERATOR AMENDMENT" not in raw):
            armed.append(path.name)
    assert not armed, (
        f"{CONTRACT} §4 arms the TEMPLATE; these batch configs gained {KNOB!r} with no "
        f"recorded-amendment marker beside it: {armed}. §Live acceptance arms the exhibit "
        f"'under a dated recorded amendment', which is the one sanctioned other path"
    )


def test_t5c_the_materialized_config_a_dry_run_prints_carries_record(
    tmp_path: Path
) -> None:
    """T5: "`gen run --dry-run`'s resolved config carries it".

    Driven at the importable seam `cmd_run` uses and `build_config`'s own
    docstring names — `build_config` plus `render_config`, which IS the text the
    dry run prints — with tmp roots, so the id and seed scans never read
    `out/batches/` (ambiguity (f)).
    """
    configs, batches = tmp_path / "config", tmp_path / "batches"
    configs.mkdir()
    batches.mkdir()
    cfg = cli.build_config(driver="claude", games=1, seed=99,
                           config_dir=configs, batches_root=batches)
    assert (cfg.get(BLOCK) or {}).get(KNOB) == RECORD, (
        f"{CONTRACT} T5: the resolved config a dry run prints carries {KNOB}: {RECORD!r}; its "
        f"{BLOCK!r} block is {cfg.get(BLOCK)!r}"
    )
    text = cli.render_config(cfg)
    assert KNOB in text and RECORD in text, (
        f"{CONTRACT} T5: the dry run prints these bytes and a real run writes them, so the "
        f"knob has to be IN them; {KNOB!r} is not"
    )
    reloaded = yaml.safe_load(text)
    assert reloaded[BLOCK][KNOB] == RECORD, (
        f"{CONTRACT} T5: the rendered config of record must read back as {RECORD!r}, got "
        f"{reloaded[BLOCK].get(KNOB)!r}"
    )
    # A rehearsal takes nothing: `build_config` is the no-spend seam.
    assert not list(configs.iterdir()) and not list(batches.iterdir())


def test_t5d_an_explicit_reject_survives_materialization(tmp_path: Path) -> None:
    """T5: "an explicit `reject` survives materialization".

    Read as the config of record being honoured (ambiguity (g)): no flag sets
    this knob, so an explicit value can only be written after the overlay, and
    what must survive is the write-and-reload — `render_config` out,
    `load_config` back in, with the value intact and the canon still resolving.
    """
    configs, batches = tmp_path / "config", tmp_path / "batches"
    configs.mkdir()
    batches.mkdir()
    cfg = cli.build_config(driver="claude", games=1, seed=99,
                           config_dir=configs, batches_root=batches)
    cfg[BLOCK] = {**cfg[BLOCK], KNOB: REJECT}
    path = tmp_path / "pinned.yaml"
    path.write_text(cli.render_config(cfg), encoding="utf-8")
    back = load_config(path)
    assert back[BLOCK][KNOB] == REJECT, (
        f"{CONTRACT} T5: 'an explicit `reject` survives materialization' — this config pinned "
        f"the default and came back as {back[BLOCK].get(KNOB)!r}. §3: {REJECT!r} is 'today's "
        f"bytes', and a config of record that asks for them must get them"
    )
    assert back[BLOCK].get("deception_action") == RECORD, (
        "fixture wall: the rest of the materialized verifier block should be the armed "
        f"template, so this pin is measuring the ONE key it pinned: {back[BLOCK]!r}"
    )


def test_t5e_the_materialized_config_decides_the_exhibit_end_to_end(
    tmp_path: Path, cap: object
) -> None:
    """T5, both halves against the REAL resolved config.

    The armed materialization records the dispute and the pinned-`reject` one
    rejects it, with every other template knob in play.  Two rounds per slot
    because the template also arms `term_corroboration` with a window of 1: a
    first sighting is demoted upstream of this ruling, so the SECOND round is
    the one where a surviving finding has a verdict to decide — which is what
    the live acceptance in §Live acceptance will meet at round 8.
    """
    configs, batches = tmp_path / "config", tmp_path / "batches"
    configs.mkdir()
    batches.mkdir()
    built = cli.build_config(driver="claude", games=1, seed=99,
                             config_dir=configs, batches_root=batches)
    armed_path = tmp_path / "armed.yaml"
    armed_path.write_text(cli.render_config(built), encoding="utf-8")
    pinned = {**built, BLOCK: {**built[BLOCK], KNOB: REJECT}}
    pinned_path = tmp_path / "pinned.yaml"
    pinned_path.write_text(cli.render_config(pinned), encoding="utf-8")

    outcomes: dict[str, dict] = {}
    for name, cfg_path in (("armed", armed_path), ("pinned", pinned_path)):
        plot = _Slot(tmp_path / name, cap)
        cfg = load_config(cfg_path)
        plot.run(cfg, EXHIBIT)  # round 1: the corroboration bar, upstream of Q-1
        outcomes[name] = plot.run(cfg, EXHIBIT)  # round 2: the finding stands

    assert sorted(_undeclared_rejects(outcomes["pinned"])) == sorted([RECALL, KEYED]), (
        f"fixture wall / {CONTRACT} §3: under the materialized config pinned to {REJECT!r} the "
        f"exhibit's two findings reject exactly as today; got "
        f"{outcomes['pinned']['reject_reasons']!r}. If this is empty, the round the "
        f"corroboration bar demotes moved and this pin's two-round rig needs re-reading"
    )
    assert _undeclared_rejects(outcomes["armed"]) == [], (
        f"{CONTRACT} T5: under the config the CLI materializes — {KNOB}: {RECORD!r} — the "
        f"disputed findings leave the reject path. This report rejects on "
        f"{outcomes['armed']['reject_reasons']!r}"
    )
    value, where = _disputes(outcomes["armed"])
    assert len(_pairs_named(value, where)) == len(EXHIBIT), (
        f"{CONTRACT} §1: both pairs are on the record under the armed config; {where} holds "
        f"{_pairs_named(value, where)}"
    )
