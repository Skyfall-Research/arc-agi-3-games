"""Blind pins for contract W2-A — R-10 objective-mix rebase, R-14 S0 prose checks.

Run: .venv/bin/python -m pytest gen/tests/test_w2_mixprose.py -v

Written from ``scratchpad/w2-a-contract.md`` ALONE, by a separate agent.  No
in-progress diff of ``gen/s0_ideas.py``, ``config/template.yaml`` or
``audit/comparative/scripts/m3_drawspace.py`` was read while this file was
written; every statement here about the PRE-change sampler came out of
``git show HEAD:gen/s0_ideas.py`` (HEAD = the wave-1 close), which this file
shadow-loads side by side with the live module so the "byte-identical
unconfigured run" pins are measured rather than retyped.  These tests are
EXPECTED TO FAIL against HEAD on every contract-bearing pin and to pass against
the finished change.

WHAT THE CHANGE IS FOR.  The sampler's objective mix is near-uniform
(10.1-14.9% per family, measured at HEAD below) while the officials' primaries
are 11/6/4/2/1/1/0/0 — and the D24 ``reach_cap`` never binds because reach_goal
computes 0.101.  The officials also carry a secondary objective 19/25 and S0
has never drawn one.  R-14 adds the two prose guards the audit's premise track
asked for: a stated-non-terminal-win reject, and the §1 definition of the three
interaction loci quoted into the prose prompt.

MEASURED AT HEAD (this file's baselines, all re-measured at run time from the
shadow module — nothing below is a retyped number a drifting HEAD could
falsify):

* HEAD objective mix, ``config/b003r2-simplicity.yaml``, N=6000, seed
  20260928: reach_goal .097, cover_targets .098, match_pattern .110,
  sequence .131, collect_all .137, survive .138, balance .142, connect .147.
* HEAD ``_prose_rejects`` returns ``[]`` for all 7 shipped premises, all 12
  J-3 fresh ideas and both recorded exhibits — so "no new reject" and
  "returns []" are the same pin for the precision corpora.

CONTRACT AMBIGUITIES / ERRORS, each restated at its own pin:

A. **R-10 change 1 and test-pin 2 are arithmetically incompatible.**  Change 1
   says the boost/floor/cap machinery is unchanged and "only the share it
   reads" moves.  Feeding the officials' shares into HEAD's formula
   (``max(1, floor) * (1 + max(0, 1/8 - share) * 4)``) gives reach_goal
   weight 1.0 and survive/connect weight 1.5 each -> a mix of reach .101,
   survive .152, connect .152: the cap still never binds and the two families
   the officials never use become the two LARGEST.  Pin 2's numbers (reach ==
   cap, survive+connect < 0.02) are only reachable if the officials-mode
   weight is proportional to the officials' share.  This file pins the
   NUMBERS (pin 2 is the contract's measurable statement and matches the operator's
   ruling, "RESEMBLE THE OFFICIALS"); measured mode keeps HEAD's formula
   exactly, which the byte-identity pins hold to the bit.  Under the
   share-proportional reading the officials mix computes to reach .250
   (capped from .422 raw), match_pattern .299, cover_targets .200,
   collect_all .118, sequence .067, balance .067, survive 0, connect 0 —
   the shape pins below are that vector's rank order, not its exact values.
B. **Two of the "seven shipped premises" ARE the two exhibits.**
   ``out/corpus/b002-triple/core-ward-phase-gates/idea.json`` is idea-002
   ("keep it intact for as long as possible") and
   ``out/corpus/b002-triple/convoy-in-the-fog/idea.json`` is idea-003 ("keep
   it running forever by never letting its fuel run out") — byte-identical
   prose, both shipped, both packaged.  Pin 5 as literally written ("the two
   exhibit fragments reject; seven shipped premises pass") cannot hold.
   Resolved the only way that keeps R-14's own words ("the seven shipped
   CLEAN premises"): the five non-exhibit shipped premises must stay clean,
   the two exhibits must reject.  That is what the table below encodes.
C. **``reach_cap`` is already validated at HEAD.**  R-10 change 2 says "today
   it is unvalidated; validate it" — ``_check_reach_cap`` has refused
   anything outside (0, 1) since B4, and ``check_config`` calls it.  Pin 3's
   validation half is therefore a REGRESSION pin (it passes at HEAD); only
   its binding-cap half is contract-bearing.
D. **Where the secondary is drawn is unstated.**  "After the primary draw"
   plus "the rate-0 branch short-circuits before any rng call" places it
   inside ``_draw_core``; the contract also calls ``Idea.objective.secondary``
   an existing slot.  Every secondary pin here resolves the draw through
   whichever surface exists: a ``_Core`` field whose name contains
   "secondary" if there is one, else ``sample_idea(...).objective["secondary"]``
   with an injected prose runner.  The route taken is printed in every
   failure message.
E. **"never let/until" is the least specified marker in R-14's pattern
   family.**  Bare "until" CANNOT be one: 4 of the 10 OFFICIAL-SHAPED premises
   the same contract makes a precision corpus use it terminally ("until every
   marble matches"), and so does a shipped premise.  This file pins bare
   "until" as a non-marker and pins the compound "never let … until" phrasing
   as a reject; if the implementer read the marker narrower, exactly one test
   fails and this is the sentence to reopen.
F. **Which entry point is "loud" is unstated.**  The house rule says an
   invalid knob is "a loud ValueError read before any work", and
   ``check_config`` is the function whose docstring claims exactly that
   ("Every STRICT config error, raised before a single prose token is
   spent").  Each invalid-value pin therefore comes in two: one that accepts
   ANY of check_config / objective_weights / a first draw raising, and one
   that requires ``check_config`` itself.  If only the second fails, the fix
   is one line in ``check_config``.
G. **``ideas.corpus_share: null``** (an explicit YAML null) is not pinned
   either way — the contract says nothing about it, and the wave-1 files
   split on the same question for other knobs.

HYGIENE: tmp_path / tmp_path_factory only.  ``out/`` is read and never
written (the shipped premises, the J-3 ideas and
``audit/comparative/data/j3-premise-grades.csv`` are READ-ONLY probe corpora);
no network, no driver, no API call — prose is never drawn here, the Monte
Carlo runs ``_draw_core`` and the two ``sample_idea`` pins inject a runner that
replays a shipped premise.
"""

from __future__ import annotations

import copy
import csv
import dataclasses
import importlib.util
import inspect
import itertools
import json
import math
import random
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from functools import cache
from pathlib import Path

import pytest
import yaml

from gen import s0_ideas as live
from gen.config import REPO_ROOT, load_config
from gen.tests.test_docs_template import _readers, _template_copy
from gen.tiers import tier_policy

# --- locations ----------------------------------------------------------------

ROOT = Path(REPO_ROOT)
TEMPLATE_PATH = ROOT / "config" / "template.yaml"
M3_SCRIPT = ROOT / "audit" / "comparative" / "scripts" / "m3_drawspace.py"

#: The MC config.  `config/b003r2-simplicity.yaml` is m3_drawspace's own pinned
#: CONFIG and a FROZEN batch config, so sibling wave-2 lanes editing
#: `config/template.yaml` cannot move these numbers.  Pin 7 uses the template.
MC_CONFIG = ROOT / "config" / "b003r2-simplicity.yaml"

#: m3_drawspace's headline seed.  Same recipe, smaller N.
MC_SEED = 20260928
MC_N = 6000          # pin 2 asks for >= 4000
IDENTITY_N = 500     # pin 1's number

# --- the contract's frozen surface --------------------------------------------

CORPUS_SHARE_KEY = "corpus_share"        # `ideas.corpus_share`
SECONDARY_RATE_KEY = "secondary_rate"    # `ideas.secondary_rate`
IDEAS_BLOCK = "ideas"
CORPUS_SHARES = ("measured", "officials", "blend")
DEFAULT_CORPUS_SHARE = "measured"
TEMPLATE_CORPUS_SHARE = "officials"
TEMPLATE_SECONDARY_RATE = 0.76           # = 19/25

#: Values that must be refused loudly.  A near-miss spelling is the whole point
#: of a closed enum: `official` is not `officials`, and a trailing space is the
#: classic yaml paste.
BAD_CORPUS_SHARES = (
    "official",
    "Officials",
    "OFFICIALS",
    "measured ",
    "",
    "blended",
    "uniform",
    1,
    True,
    ["officials"],
)
BAD_SECONDARY_RATES = (-0.1, -1, 1.5, 2, "0.76", "", [0.76])
BAD_REACH_CAPS = (0, 0.0, -0.1, 1, 1.0, 1.5, "0.25", True)

#: The officials, from `objectives.csv` corpus == official (25 rows).  Retyped
#: from R-10's own evidence paragraph and CROSS-CHECKED against the csv by
#: `test_pin2_the_officials_table_is_what_the_contract_says` — if the canon
#: moves, that test names the drift instead of every share pin failing.
OFFICIAL_PRIMARIES = {
    "reach_goal": 11,
    "match_pattern": 6,
    "cover_targets": 4,
    "collect_all": 2,
    "sequence": 1,
    "balance": 1,
    "survive": 0,
    "connect": 0,
}
OFFICIAL_SECONDARY_ROWS = 19  # non-blank objective_secondary cells, = 0.76 * 25

#: `collect_all` is the one family that is never an official SECONDARY, in any
#: row — so it can never be drawn as one, neither from a primary's own
#: co-occurrence row nor from the overall fallback distribution.
NEVER_A_SECONDARY = "collect_all"
MODAL_SECONDARY = "connect"  # 7/19 overall, and the modal draw in every mode

# --- R-14's corpora (READ-ONLY) ------------------------------------------------

CORPUS_ROOT = ROOT / "out" / "corpus"
J3_ROOT = ROOT / "out" / "audit" / "j3"
J3_GRADES = ROOT / "audit" / "comparative" / "data" / "j3-premise-grades.csv"

#: The two recorded exhibits, by the path the contract names them from.  Their
#: prose is ALSO shipped (ambiguity B), which is why the shipped-premise table
#: below is keyed by game directory and carries an expectation per row.
EXHIBITS = {
    "b002-triple-i002": ROOT / "out" / "ideas" / "b002-triple" / "idea-002.json",
    "b002-triple-i003": ROOT / "out" / "ideas" / "b002-triple" / "idea-003.json",
}

#: The load-bearing fragments, quoted from those two files:
#:   i002 "…the player's only job is to keep it intact for as long as possible
#:         while colored hazard tokens creep inward…"
#:   i003 "…the only goal is to keep it running forever by never letting its
#:         fuel run out."
EXHIBIT_FRAGMENTS = {
    "b002-triple-i002": "for as long as possible",
    "b002-triple-i003": "keep it running forever by never letting",
}

#: The 10 rows graded OFFICIAL-SHAPED in J-3 (verdict column of
#: `j3-premise-grades.csv`), mapped to the file that holds each one's prose.
#: The mapping is asserted against the csv at run time, so a re-grade shows up
#: as a named failure rather than a silently shrunken precision corpus.
OFFICIAL_SHAPED = {
    "b001-pilot-i001-respec3": ROOT / "out/ideas/b001-pilot/respec-3/idea-001.json",
    "b003-simplicity-i001": ROOT / "out/ideas/b003-simplicity/idea-001.json",
    "b003-simplicity-i002": ROOT / "out/ideas/b003-simplicity/idea-002.json",
    "b003r2-simplicity-i001": ROOT / "out/ideas/b003r2-simplicity/idea-001.json",
    "audit-j3-i003": J3_ROOT / "idea-003.json",
    "audit-j3-i005": J3_ROOT / "idea-005.json",
    "audit-j3-i006": J3_ROOT / "idea-006.json",
    "audit-j3-i008": J3_ROOT / "idea-008.json",
    "audit-j3-i011": J3_ROOT / "idea-011.json",
    "audit-j3-i012": J3_ROOT / "idea-012.json",
}

#: Words a `nonterminal-win` reason may reasonably use.  The check's NAME is
#: frozen by the contract, its reason STRING is not (it follows the existing
#: free-prose `_prose_rejects` shape), so the pin asks for a reason that is
#: about non-termination rather than for an exact sentence.
NONTERMINAL_REASON_MARKERS = (
    "termin",      # "non-terminal", "not terminal", "never terminates"
    "unbounded",
    "endless",
    "forever",
    "as long as",
    "never end",
    "no end",
    "win condition",
    "unrecoverable",
)

#: A clean, terminal, 400+ char premise body to hang synthetic sentences on.
#: Deliberately uses "until" terminally — bare "until" is not a marker
#: (ambiguity E), and 4 of the 10 OFFICIAL-SHAPED premises prove it.
CLEAN_BASE = (
    "A small grid of coloured lamps runs along the bottom of the board, and a single "
    "mover object walks the open corridor above them one tile at a time. Each lamp "
    "answers to the tile directly beneath it, so stepping onto that tile flips the "
    "lamp between its two states and leaves a visible mark the player can read from "
    "the frame alone. A quarantined reference strip in the top-right corner shows the "
    "pattern the lamps must end in, and it never changes during a level. The player "
    "walks the corridor, flipping lamps one at a time, until every lamp matches the "
    "reference strip, which ends the level immediately and opens the next one. "
    "Later levels widen the corridor and add a second reference row, so the order of "
    "the flips starts to matter as much as which lamps are lit."
)

_ABSENT = "__absent__"          # hashable sentinel: the knob is not in the config
_NO_FIELD = object()


# --- helpers ------------------------------------------------------------------


def norm_text(text: str) -> str:
    """Backtick- and wrap-insensitive text (`test_b6_payload._norm`'s rule)."""
    return re.sub(r"\s+", " ", str(text).replace("`", "")).strip()


def mc_tol(p: float, n: int) -> float:
    """~4 sigma of a binomial share, floored at 2pp — the "± MC noise" band."""
    return max(0.02, 4.0 * math.sqrt(max(p * (1.0 - p), 0.01) / n))


@pytest.fixture(scope="session")
def head(tmp_path_factory: pytest.TempPathFactory):
    """`git show HEAD:gen/s0_ideas.py`, loaded as a sibling module.

    Named `gen._w2a_head_s0_ideas` so its own relative imports (`.config`,
    `.tiers`) resolve to the LANDED modules — this contract touches neither, and
    a shadow copy of them would be the thing under test's own dependency, not
    HEAD's.  The W1-B shadow-tree pattern, one file wide.
    """
    try:
        source = subprocess.run(
            ["git", "show", "HEAD:gen/s0_ideas.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover
        pytest.fail(
            f"cannot read the pre-change sampler with `git show HEAD:gen/s0_ideas.py` "
            f"in {ROOT}: {exc}. Every byte-identity pin in this file is measured "
            f"against HEAD, so this is a stop, not a skip."
        )
    path = tmp_path_factory.mktemp("w2a-head") / "head_s0_ideas.py"
    path.write_text(source, encoding="utf-8")
    name = "gen._w2a_head_s0_ideas"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@cache
def _base_cfg() -> dict:
    return load_config(MC_CONFIG)


def cfg_with(
    *, corpus_share=_ABSENT, secondary_rate=_ABSENT, reach_cap=_ABSENT
) -> dict:
    """The frozen MC config with this contract's knobs set (or removed).

    `_ABSENT` is the UNCONFIGURED state the house rule pins byte-identity on, so
    it strips the keys rather than trusting the file not to carry them.
    """
    cfg = copy.deepcopy(_base_cfg())
    ideas = cfg.setdefault(IDEAS_BLOCK, {})
    for key in (CORPUS_SHARE_KEY, SECONDARY_RATE_KEY):
        ideas.pop(key, None)
    if corpus_share is not _ABSENT:
        ideas[CORPUS_SHARE_KEY] = corpus_share
    if secondary_rate is not _ABSENT:
        ideas[SECONDARY_RATE_KEY] = secondary_rate
    if reach_cap is not _ABSENT:
        cfg["batch"]["mix"]["objective"]["reach_cap"] = reach_cap
    return cfg


def draw_args(module, cfg: Mapping, vocab: Mapping) -> dict:
    """m3_drawspace's pinned `_draw_core` recipe, adapted to THIS signature.

    Every keyword `_draw_core` declares is filled from the same four readers the
    audit script uses; a keyword this contract did not foresee is left to its
    default (an unconfigured run is canon), and a REQUIRED one that cannot be
    filled fails loudly with its name instead of guessing a value.
    """
    known = {
        "quotas": lambda: module._check_quotas(cfg, vocab),
        "objective_w": lambda: module.objective_weights(cfg),
        "family_w": lambda: module.failure_family_weights(cfg),
        "seed_counts": lambda: module._seed_term_counts(cfg),
        "policy": lambda: tier_policy(cfg),
    }
    args = {}
    unfillable = []
    for name, param in inspect.signature(module._draw_core).parameters.items():
        if name in ("cfg", "rng", "vocab", "tier_override"):
            continue
        if name in known:
            args[name] = known[name]()
        elif param.default is inspect.Parameter.empty:
            unfillable.append(name)
    if unfillable:
        pytest.fail(
            f"{module.__name__}._draw_core declares required keyword(s) {unfillable} this "
            f"contract does not describe. The MC recipe is pinned (m3_drawspace.draw_args: "
            f"quotas / objective_w / family_w / seed_counts / policy); a new REQUIRED "
            f"argument breaks every caller of the audit script too. Give it a default, or "
            f"tell the lead what reader fills it."
        )
    return args


def core_row(core) -> tuple:
    """HEAD's six `_Core` fields — the comparable part of a draw."""
    return (
        core.hazardless,
        core.locus,
        core.tier,
        core.failure_family,
        core.primary,
        tuple(core.seed_terms),
    )


@cache
def _secondary_field(cls) -> str | None:
    names = [f.name for f in dataclasses.fields(cls) if "secondary" in f.name.lower()]
    return names[0] if names else None


def core_secondary(core):
    """This core's secondary objective, or `_NO_FIELD` when `_Core` has none."""
    name = _secondary_field(type(core))
    if name is None:
        return _NO_FIELD
    return getattr(core, name)


@cache
def mc(module, corpus_share=_ABSENT, secondary_rate=_ABSENT, reach_cap=_ABSENT, n=MC_N,
       seed=MC_SEED):
    """`n` seeded `_draw_core` draws — rows, secondaries and the final rng state.

    The rng state is the byte-identity instrument the contract asks for: a
    rate-0 secondary branch that touches `rng` at all moves it, even when the
    drawn cores happen to match.
    """
    cfg = cfg_with(
        corpus_share=corpus_share, secondary_rate=secondary_rate, reach_cap=reach_cap
    )
    vocab = module.load_vocab(cfg)
    args = draw_args(module, cfg, vocab)
    rng = random.Random(seed)
    rows, secondaries = [], []
    for _ in range(n):
        core = module._draw_core(cfg, rng, vocab, **args)
        rows.append(core_row(core))
        secondaries.append(core_secondary(core))
    return tuple(rows), tuple(secondaries), rng.getstate()


def primary_mix(rows) -> dict[str, float]:
    counts = Counter(row[4] for row in rows)
    return {family: counts[family] / len(rows) for family in live.OBJECTIVE_FAMILIES}


def _clean_prose_runner():
    """A prose runner that replays a SHIPPED premise — no driver, no API call."""
    idea = json.loads(
        (
            CORPUS_ROOT / "b003-simplicity/facing-sentinel-match-the-signal-row/idea.json"
        ).read_text(encoding="utf-8")
    )

    def run(_prompt: str) -> str:
        return f"{idea['prose']['title']}\n\n{idea['prose']['text']}"

    return run


def secondary_pairs(corpus_share, secondary_rate, n=MC_N, seed=MC_SEED):
    """(primary, secondary) for `n` draws, whichever surface carries it.

    Route 1 is `_Core` (the rng contract's own home for a draw that must
    short-circuit at rate 0); route 2 is `sample_idea().objective["secondary"]`,
    the slot the contract calls existing.  The route is reported so a failure
    says WHERE it was measured (ambiguity D).
    """
    rows, secondaries, _state = mc(
        live, corpus_share=corpus_share, secondary_rate=secondary_rate, n=n, seed=seed
    )
    if secondaries and secondaries[0] is not _NO_FIELD:
        return [(row[4], sec) for row, sec in zip(rows, secondaries)], "_Core"

    cfg = cfg_with(corpus_share=corpus_share, secondary_rate=secondary_rate)
    rng = random.Random(seed)
    runner = _clean_prose_runner()
    pairs = []
    for index in range(1, min(n, 1500) + 1):
        idea = live.sample_idea(
            cfg, rng, batch_id="w2a-mc", index=index, prose_runner=runner
        )
        objective = idea.objective
        pairs.append((objective.get("primary"), objective.get("secondary")))
    return pairs, "sample_idea"


def assert_loud(build_cfg, label: str) -> None:
    """The knob is refused by SOMETHING before a draw happens (ambiguity F)."""
    raised = {}
    for name in ("check_config", "objective_weights", "draw"):
        cfg = build_cfg()
        try:
            if name == "check_config":
                live.check_config(cfg, live.load_vocab(cfg))
            elif name == "objective_weights":
                live.objective_weights(cfg)
            else:
                vocab = live.load_vocab(cfg)
                live._draw_core(
                    cfg, random.Random(1), vocab, **draw_args(live, cfg, vocab)
                )
        except ValueError as exc:
            raised[name] = f"ValueError: {exc}"
        except Exception as exc:  # noqa: BLE001 — collected: a non-ValueError is a finding
            raised[name] = f"{type(exc).__name__}: {exc}"
    valueerrors = [k for k, v in raised.items() if v.startswith("ValueError")]
    assert valueerrors, (
        f"{label} was accepted silently — no ValueError from check_config, "
        f"objective_weights or a first _draw_core. HOUSE RULE: 'A knob set to an "
        f"invalid value is a loud ValueError read before any work.' What happened "
        f"instead: {raised or 'nothing raised at all'}"
    )


def assert_loud_in_check_config(build_cfg, label: str) -> None:
    """…and `check_config` is where (its docstring promises exactly that)."""
    cfg = build_cfg()
    vocab = live.load_vocab(cfg)
    try:
        live.check_config(cfg, vocab)
    except ValueError:
        return
    except Exception as exc:  # noqa: BLE001 — the TYPE is the pin
        pytest.fail(
            f"{label}: check_config raised {type(exc).__name__}: {exc}. Every STRICT S0 "
            f"config error is a ValueError (s0_ideas.py's own noqa on `_check_tier_sequence` "
            f"says so in one line)"
        )
    pytest.fail(
        f"{label} passed check_config — 'Every STRICT config error, raised before a single "
        f"prose token is spent' is that function's docstring, and a batch that reads a "
        f"mistyped knob discovers it after the driver spend. AMBIGUITY F: if the value IS "
        f"refused elsewhere (the companion test passes), this is a one-line move."
    )


# --- pin 1: corpus_share parses, defaults to measured, and changes nothing ----


def test_pin1_the_three_modes_are_accepted() -> None:
    """`measured | officials | blend` all parse. One call each, no draw."""
    failures = []
    for value in CORPUS_SHARES:
        cfg = cfg_with(corpus_share=value)
        try:
            live.check_config(cfg, live.load_vocab(cfg))
            live.objective_weights(cfg)
        except Exception as exc:  # noqa: BLE001 — collected, not swallowed
            failures.append(f"  ideas.{CORPUS_SHARE_KEY}={value!r}: {type(exc).__name__}: {exc}")
    assert not failures, (
        f"{len(failures)}/{len(CORPUS_SHARES)} of the contract's corpus_share values were "
        f"refused:\n" + "\n".join(failures)
    )


def test_pin1_unconfigured_draws_are_byte_identical_to_head(head) -> None:
    """THE house rule: an unconfigured run == pre-W2-A, draw for draw.

    N=500 seeded `_draw_core` draws plus the final rng state, which is what
    catches a new knob that consumes rng even when its result is discarded.
    """
    live_rows, live_secondaries, live_state = mc(live, n=IDENTITY_N)
    head_rows, _head_secondaries, head_state = mc(head, n=IDENTITY_N)
    first = next(
        (i for i, (a, b) in enumerate(zip(live_rows, head_rows)) if a != b), None
    )
    assert live_rows == head_rows, (
        f"draw {first} diverges from HEAD with no knob configured:\n"
        f"  now:  {live_rows[first] if first is not None else '-'}\n"
        f"  HEAD: {head_rows[first] if first is not None else '-'}\n"
        f"HOUSE RULE: 'every new knob DEFAULTS to today's behavior — an unconfigured run "
        f"is byte-identical (same RNG consumption, same outputs) to pre-W2-A'. Every "
        f"signed pilot seed (b001/b002/b003/b003r2) is downstream of this."
    )
    assert live_state == head_state, (
        "the 500 unconfigured draws match HEAD's but the rng ENDED SOMEWHERE ELSE — "
        "something consumed a draw it did not use (the `secondary_rate: 0.0` branch is "
        "the suspect: R-10 change 3 requires it to short-circuit BEFORE any rng call)"
    )
    assert all(sec in (None, _NO_FIELD) for sec in live_secondaries), (
        "an unconfigured run drew a secondary objective; `ideas.secondary_rate` DEFAULTS "
        "to 0.0 and 0.0 means never"
    )


def test_pin1_explicit_measured_equals_the_unconfigured_run(head) -> None:
    """`corpus_share: measured` is the default SPELLED OUT, not a third path."""
    rows, _sec, state = mc(live, corpus_share=DEFAULT_CORPUS_SHARE, n=IDENTITY_N)
    head_rows, _hsec, head_state = mc(head, n=IDENTITY_N)
    assert rows == head_rows and state == head_state, (
        f"ideas.{CORPUS_SHARE_KEY}: {DEFAULT_CORPUS_SHARE!r} must reproduce the "
        f"pre-W2-A draw exactly — it is the DEFAULT, and the 190-row measured corpus "
        f"share is what HEAD already reads"
    )


def test_pin1_unconfigured_objective_weights_equal_heads(head) -> None:
    """Float-for-float, not just 'the same mix' — the weights ARE the contract."""
    cfg = cfg_with()
    assert live.objective_weights(cfg) == head.objective_weights(cfg), (
        f"objective_weights moved with no knob set:\n  now:  {live.objective_weights(cfg)}\n"
        f"  HEAD: {head.objective_weights(cfg)}"
    )


def test_pin1_officials_actually_moves_the_draw(head) -> None:
    """The knob is not decoration: `officials` produces a different sampler."""
    rows, _sec, _state = mc(live, corpus_share="officials", n=IDENTITY_N)
    head_rows, _hsec, _hstate = mc(head, n=IDENTITY_N)
    assert rows != head_rows, (
        "ideas.corpus_share: officials draws exactly what HEAD draws — the knob reads "
        "nothing. R-10: the deficit boost's corpus-share input becomes the 25 officials' "
        "primary distribution from objectives.csv"
    )


def test_pin1_blend_is_its_own_mode() -> None:
    """`blend` = 50/50 of the two shares, so it matches NEITHER end."""
    blend, _s1, _t1 = mc(live, corpus_share="blend", n=IDENTITY_N)
    measured, _s2, _t2 = mc(live, corpus_share="measured", n=IDENTITY_N)
    officials, _s3, _t3 = mc(live, corpus_share="officials", n=IDENTITY_N)
    assert blend != measured, "ideas.corpus_share: blend draws the measured mix — it is an alias"
    assert blend != officials, (
        "ideas.corpus_share: blend draws the officials mix — it is an alias, not the "
        "50/50 of the two shares R-10 change 1 specifies"
    )


@pytest.mark.parametrize("value", BAD_CORPUS_SHARES, ids=[repr(v) for v in BAD_CORPUS_SHARES])
def test_pin1_an_invalid_corpus_share_is_loud(value) -> None:
    assert_loud(lambda: cfg_with(corpus_share=value), f"ideas.{CORPUS_SHARE_KEY}={value!r}")


@pytest.mark.parametrize("value", BAD_CORPUS_SHARES, ids=[repr(v) for v in BAD_CORPUS_SHARES])
def test_pin1_an_invalid_corpus_share_is_refused_by_check_config(value) -> None:
    """Ambiguity F: `check_config` is the 'before any work' gate."""
    assert_loud_in_check_config(
        lambda: cfg_with(corpus_share=value), f"ideas.{CORPUS_SHARE_KEY}={value!r}"
    )


# --- pin 2: officials mode reproduces the officials' shape ---------------------


def test_pin2_the_officials_table_is_what_the_contract_says() -> None:
    """Guard rail: the 11/6/4/2/1/1/0/0 this file's shape pins assume.

    Read from the canon (`objectives.csv`, corpus == official) through the
    module's own docs resolver — never from the implementer's new loader.
    """
    cfg = cfg_with()
    path = Path(cfg["duckwm_docs"]) / live.OBJECTIVES_CSV
    with path.open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("corpus") or "").strip() == "official"]
    counts = Counter((r.get("objective_primary") or "").strip() for r in rows)
    measured = {family: counts.get(family, 0) for family in live.OBJECTIVE_FAMILIES}
    assert len(rows) == 25 and measured == OFFICIAL_PRIMARIES, (
        f"{path} no longer holds R-10's evidence: {len(rows)} official rows, primaries "
        f"{measured}, expected 25 rows and {OFFICIAL_PRIMARIES}. Every officials-mode "
        f"share pin below is derived from that table."
    )
    secondaries = sum(1 for r in rows if (r.get("objective_secondary") or "").strip())
    assert secondaries == OFFICIAL_SECONDARY_ROWS, (
        f"{path}: {secondaries}/25 rows carry a secondary, not {OFFICIAL_SECONDARY_ROWS} — "
        f"`secondary_rate: 0.76` is that ratio"
    )


def test_pin2_officials_mode_caps_reach_goal_at_the_reach_cap() -> None:
    """The raw officials share is 0.44; the D24 cap finally binds at 0.25."""
    rows, _sec, _state = mc(live, corpus_share="officials")
    mix = primary_mix(rows)
    cap = live._check_reach_cap(cfg_with())
    tol = mc_tol(cap, len(rows))
    assert abs(mix["reach_goal"] - cap) <= tol, (
        f"officials mode drew reach_goal at {mix['reach_goal']:.4f}; the contract's pin is "
        f"the cap {cap} ± {tol:.4f} ('the raw share can exceed 0.25, so the existing "
        f"rescale branch finally binds'). Full mix: "
        f"{ {k: round(v, 4) for k, v in mix.items()} }.\n"
        f"AMBIGUITY A: swapping ONLY the share into HEAD's `max(1, floor) * (1 + deficit)` "
        f"formula leaves reach at 0.101 and the cap unbound; pin 2's numbers need the "
        f"officials-mode weight to be proportional to the officials' share."
    )


def test_pin2_officials_mode_starves_survive_and_connect() -> None:
    """0/25 officials use them as a primary; the mix must say so."""
    rows, _sec, _state = mc(live, corpus_share="officials")
    mix = primary_mix(rows)
    combined = mix["survive"] + mix["connect"]
    assert combined < 0.02, (
        f"officials mode drew survive+connect at {combined:.4f} (survive "
        f"{mix['survive']:.4f}, connect {mix['connect']:.4f}); pin 2's bound is 0.02 "
        f"combined, because the officials' primaries are 0 and 0. At HEAD these two are "
        f"the LARGEST families (.138 / .147) — the deficit boost's whole failure mode."
    )


def test_pin2_officials_mode_keeps_the_officials_rank_order() -> None:
    """~11/6/4/2/1/1/0/0, minus reach_goal, which the cap pins at 0.25."""
    rows, _sec, _state = mc(live, corpus_share="officials")
    mix = primary_mix(rows)
    chain = ("match_pattern", "cover_targets", "collect_all")
    ordered = [*chain, max(("sequence", "balance"), key=lambda f: mix[f])]
    for higher, lower in itertools.pairwise(ordered):
        assert mix[higher] > mix[lower] + 0.01, (
            f"officials mode put {lower} ({mix[lower]:.4f}) at or above {higher} "
            f"({mix[higher]:.4f}); the officials' own counts are 6 / 4 / 2 / 1, so the "
            f"rank order is the shape this mode exists to reproduce. Full mix: "
            f"{ {k: round(v, 4) for k, v in mix.items()} }"
        )
    for small in ("sequence", "balance"):
        assert mix[small] > mix["survive"] + mix["connect"], (
            f"{small} ({mix[small]:.4f}) drew no more than survive+connect "
            f"({mix['survive'] + mix['connect']:.4f}); the officials use it once and them "
            f"never"
        )


def test_pin2_measured_mode_is_untouched(head) -> None:
    """N=6000, not 500: 'measured mode unchanged' at MC resolution."""
    rows, _sec, state = mc(live, corpus_share="measured")
    head_rows, _hsec, head_state = mc(head)
    assert rows == head_rows and state == head_state, (
        "the measured mode's 6000 draws are not HEAD's. Whatever `officials` needed, it "
        "reached into the default path: measured is the 190-row corpus share HEAD already "
        "boosts against, and every signed batch seed depends on it"
    )


def test_pin2_blend_sits_between_the_two_corpora() -> None:
    """The 50/50 share halves the officials' two empty families, never zeroes them."""
    blend = primary_mix(mc(live, corpus_share="blend")[0])
    measured = primary_mix(mc(live, corpus_share="measured")[0])
    officials = primary_mix(mc(live, corpus_share="officials")[0])
    b = blend["survive"] + blend["connect"]
    m = measured["survive"] + measured["connect"]
    o = officials["survive"] + officials["connect"]
    assert o <= b <= m and b > o, (
        f"survive+connect is {o:.4f} under officials, {b:.4f} under blend and {m:.4f} "
        f"under measured — blend must sit BETWEEN (R-10 change 1: '50/50 of the two "
        f"shares'; the two families are 0/25 in the officials and 10/190 in the measured "
        f"corpus, so they are the discriminating families).\n"
        f"blend mix: { {k: round(v, 4) for k, v in blend.items()} }"
    )


# --- pin 3: reach_cap is validated, and a binding cap binds --------------------


@pytest.mark.parametrize("value", BAD_REACH_CAPS, ids=[repr(v) for v in BAD_REACH_CAPS])
def test_pin3_an_out_of_range_reach_cap_is_loud(value) -> None:
    """AMBIGUITY C: this already holds at HEAD — a regression pin, not a new one."""
    assert_loud(lambda: cfg_with(reach_cap=value), f"batch.mix.objective.reach_cap={value!r}")


@pytest.mark.parametrize("cap", (0.35, 0.15))
def test_pin3_a_binding_cap_lands_reach_goal_on_it(cap: float) -> None:
    rows, _sec, _state = mc(live, corpus_share="officials", reach_cap=cap)
    mix = primary_mix(rows)
    tol = mc_tol(cap, len(rows))
    assert abs(mix["reach_goal"] - cap) <= tol, (
        f"with reach_cap={cap} under officials, reach_goal drew {mix['reach_goal']:.4f}, "
        f"outside {cap} ± {tol:.4f}. A cap that binds IS the share (s0_ideas.py:621-629 "
        f"assigns `reach_cap` as the weight and rescales the rest)"
    )


def test_pin3_a_non_binding_cap_changes_nothing() -> None:
    """'a cap is a cap; do NOT add noise' — two loose caps must draw identically."""
    loose, _s1, state_loose = mc(live, corpus_share="officials", reach_cap=0.9, n=1500)
    looser, _s2, state_looser = mc(live, corpus_share="officials", reach_cap=0.95, n=1500)
    assert loose == looser and state_loose == state_looser, (
        "reach_cap 0.9 and 0.95 drew different batches under officials mode, where the "
        "raw reach share is ~0.44 and NEITHER cap binds. R-10 change 2: 'if reach_cap is "
        "configured but CANNOT bind under the active corpus_share, that is fine (a cap is "
        "a cap); do NOT add noise'"
    )
    mix = primary_mix(loose)
    assert mix["reach_goal"] > 0.25, (
        f"with a non-binding cap the officials' own 0.44 reach share must survive; drew "
        f"{mix['reach_goal']:.4f}. (If this fails while the 0.25 pin passes, the cap is "
        f"being applied unconditionally rather than as a ceiling.)"
    )


# --- pin 4: secondary objectives ----------------------------------------------


@pytest.mark.parametrize("value", BAD_SECONDARY_RATES, ids=[repr(v) for v in BAD_SECONDARY_RATES])
def test_pin4_an_invalid_secondary_rate_is_loud(value) -> None:
    assert_loud(
        lambda: cfg_with(secondary_rate=value), f"ideas.{SECONDARY_RATE_KEY}={value!r}"
    )


def test_pin4_rate_zero_is_the_default_and_draws_nothing(head) -> None:
    """Explicit 0.0 == absent == HEAD, rng state included."""
    rows, secondaries, state = mc(live, secondary_rate=0.0, n=IDENTITY_N)
    head_rows, _hsec, head_state = mc(head, n=IDENTITY_N)
    assert rows == head_rows and state == head_state, (
        "`ideas.secondary_rate: 0.0` did not reproduce HEAD's draw. R-10 change 3: 'with "
        "rate 0 the draw path must consume NO extra RNG — structure the draw so the "
        "rate-0 branch short-circuits before any rng call'"
    )
    assert all(sec in (None, _NO_FIELD) for sec in secondaries), (
        "rate 0.0 still produced secondaries"
    )


def test_pin4_rate_one_gives_every_idea_a_secondary() -> None:
    pairs, route = secondary_pairs("officials", 1.0)
    missing = [p for p in pairs if not p[1]]
    assert not missing, (
        f"{len(missing)}/{len(pairs)} draws had no secondary at `secondary_rate: 1.0` "
        f"(measured via {route}); rate 1 means every idea. First offenders: {missing[:3]}"
    )
    same = [p for p in pairs if p[0] == p[1]]
    assert not same, (
        f"{len(same)}/{len(pairs)} draws made the secondary EQUAL the primary (via "
        f"{route}); R-10 change 3: 'draw a secondary != primary'. First: {same[:3]}"
    )


def test_pin4_rate_076_matches_the_officials_19_of_25() -> None:
    rate = TEMPLATE_SECONDARY_RATE
    pairs, route = secondary_pairs("officials", rate)
    share = sum(1 for p in pairs if p[1]) / len(pairs)
    tol = mc_tol(rate, len(pairs))
    assert abs(share - rate) <= tol, (
        f"`secondary_rate: {rate}` produced a secondary on {share:.4f} of "
        f"{len(pairs)} draws (via {route}), outside {rate} ± {tol:.4f}. The officials "
        f"carry one on 19/25 = 0.76 of games."
    )


def test_pin4_the_secondary_distribution_resembles_the_officials_table() -> None:
    """Coarse shape only, as pin 4 says — modal family, and the impossible one."""
    pairs, route = secondary_pairs("officials", 1.0)
    counts = Counter(sec for _primary, sec in pairs)
    total = sum(counts.values())
    shares = {family: counts.get(family, 0) / total for family in live.OBJECTIVE_FAMILIES}
    assert counts.get(NEVER_A_SECONDARY, 0) == 0, (
        f"{NEVER_A_SECONDARY!r} was drawn as a secondary {counts[NEVER_A_SECONDARY]} times "
        f"(via {route}); it appears as an official secondary in ZERO of the 19 rows, so "
        f"neither a primary's co-occurrence row nor the overall fallback distribution can "
        f"produce it. Shares: { {k: round(v, 4) for k, v in shares.items()} }"
    )
    modal = max(shares, key=lambda f: shares[f])
    assert modal == MODAL_SECONDARY and shares[MODAL_SECONDARY] > 0.20, (
        f"the modal secondary is {modal!r} at {shares[modal]:.4f} (via {route}); the "
        f"officials' own secondary column is connect 7 / balance 4 / survive 3 / "
        f"match_pattern 2 / cover_targets 1 / reach_goal 1 / sequence 1, and `connect` "
        f"stays modal under every primary mix. Shares: "
        f"{ {k: round(v, 4) for k, v in shares.items()} }"
    )
    unseen = [f for f in ("survive", "balance") if shares[f] <= 0.0]
    assert not unseen, (
        f"{unseen} never appeared as a secondary (via {route}) although the officials use "
        f"them 3 and 4 times — a co-occurrence table that drops families is not the "
        f"measured one"
    )


def test_pin4_the_secondary_reaches_the_idea_json() -> None:
    """`Idea.objective.secondary` is the existing slot the contract names."""
    runner = _clean_prose_runner()
    off = live.sample_idea(
        cfg_with(corpus_share="officials"),
        random.Random(11),
        batch_id="w2a",
        index=1,
        prose_runner=runner,
    )
    assert off.objective["secondary"] is None, (
        f"an UNCONFIGURED sampler wrote objective.secondary={off.objective['secondary']!r}; "
        f"the default rate is 0.0"
    )
    ideas = [
        live.sample_idea(
            cfg_with(corpus_share="officials", secondary_rate=1.0),
            random.Random(11),
            batch_id="w2a",
            index=i,
            prose_runner=runner,
        )
        for i in range(1, 9)
    ]
    bad = [
        (i.id, i.objective)
        for i in ideas
        if not i.objective.get("secondary")
        or i.objective["secondary"] == i.objective["primary"]
        or i.objective["secondary"] not in live.OBJECTIVE_FAMILIES
    ]
    assert not bad, (
        f"at `secondary_rate: 1.0` these ideas carried no usable secondary: {bad}. The "
        f"slot is `Idea.objective['secondary']` and the value is one of "
        f"{list(live.OBJECTIVE_FAMILIES)}, never the primary"
    )
    assert set(ideas[0].to_json_dict()["objective"]) == {"primary", "secondary"}, (
        f"idea.json's objective block grew keys: {ideas[0].to_json_dict()['objective']}"
    )


def test_pin4_the_dedupe_key_still_ignores_the_secondary() -> None:
    """'dedupe_key is UNCHANGED (seed_terms+primary)' — stated so nobody widens it."""
    runner = _clean_prose_runner()
    idea = live.sample_idea(
        cfg_with(corpus_share="officials", secondary_rate=1.0),
        random.Random(5),
        batch_id="w2a",
        index=1,
        prose_runner=runner,
    )
    expected = "|".join(sorted(idea.seed_terms)) + "::" + idea.objective["primary"]
    assert idea.dedupe_key == expected, (
        f"dedupe_key is {idea.dedupe_key!r}, expected {expected!r} — R-10 change 3 keeps "
        f"it at seed_terms+primary, and `out/ideas/dedupe-history.jsonl` is written in "
        f"that shape"
    )
    assert live.make_dedupe_key(idea.seed_terms, idea.objective["primary"]) == expected


# --- pin 5: the nonterminal-win prose reject -----------------------------------


@cache
def _prose_of(path: Path) -> tuple[str, str]:
    idea = json.loads(Path(path).read_text(encoding="utf-8"))
    return idea["prose"]["title"], idea["prose"]["text"]


def new_reasons(head_module, title: str, text: str) -> tuple[list[str], list[str]]:
    """(reasons now, reasons at HEAD) — the delta IS the new check."""
    return list(live._prose_rejects(title, text)), list(head_module._prose_rejects(title, text))


def assert_nonterminal(head_module, title: str, text: str, label: str) -> None:
    now, before = new_reasons(head_module, title, text)
    # LEAD FIX (post-wave-2 push): the HEAD shadow was a LAUNCH-TIME
    # discrimination proof — HEAD then predated R-14 and had to ACCEPT the
    # exhibit. Once the wave-2 commit landed, `git show HEAD:` carries the
    # check too, so the delta is empty by construction and the STANDING
    # regression is simply "the live module rejects with the marker". The
    # launch-time proof is on the record in the blind handback.
    head_has_check = any(
        marker in " ".join(before).lower() for marker in NONTERMINAL_REASON_MARKERS
    )
    added = now if head_has_check else [r for r in now if r not in before]
    assert added, (
        f"{label} was accepted. R-14 change 2: `_prose_rejects` gains a `nonterminal-win` "
        f"check rejecting prose whose stated objective is unbounded. Reasons now: {now}; "
        f"at HEAD: {before}"
    )
    lowered = " ".join(added).lower()
    assert any(marker in lowered for marker in NONTERMINAL_REASON_MARKERS), (
        f"{label} was rejected, but for something else: {added}. The reason has to say "
        f"WHAT is wrong (one of {list(NONTERMINAL_REASON_MARKERS)}) — it is joined into "
        f"PROSE_RETRY_LINE and handed back to the writer as the correction."
    )
    assert all(isinstance(r, str) and r.strip() for r in added), (
        f"{label}: non-string / empty reason in {added}; `'; '.join(rejects)` is how "
        f"sample_idea builds the retry line"
    )


@pytest.mark.parametrize("idea_id", sorted(EXHIBITS))
def test_pin5_the_recorded_exhibits_are_rejected(head, idea_id: str) -> None:
    """R-14 change 3's two fixtures, read from the batch that produced them."""
    path = EXHIBITS[idea_id]
    assert path.is_file(), f"exhibit corpus missing: {path}"
    title, text = _prose_of(path)
    fragment = EXHIBIT_FRAGMENTS[idea_id]
    assert fragment in text, (
        f"{path} no longer contains {fragment!r} — the exhibit moved, and this pin is "
        f"quoting a premise that no longer exists"
    )
    assert_nonterminal(head, title, text, f"{idea_id} ({fragment!r})")


# The R-14 contract counted the premises of THESE four batches (7 games at
# contract time). Later batches are not part of the pin: an in-flight batch
# writing into out/corpus must not move this file's ground truth (b004
# lead fix, 2026-09-28).
CONTRACT_BATCHES = (
    "b001-pilot",
    "b002-triple",
    "b003-simplicity",
    "b003r2-simplicity",
)


def _shipped_premises() -> dict[str, Path]:
    return {
        f"{batch}/{path.parent.name}": path
        for batch in CONTRACT_BATCHES
        for path in sorted((CORPUS_ROOT / batch).glob("*/idea.json"))
    }


SHIPPED = _shipped_premises()
#: AMBIGUITY B: two shipped games carry the exhibits' prose verbatim.
SHIPPED_EXHIBITS = ("b002-triple/core-ward-phase-gates", "b002-triple/convoy-in-the-fog")


def test_pin5_the_shipped_corpus_is_the_seven_games_the_contract_counts() -> None:
    assert len(SHIPPED) == 7, (
        f"out/corpus holds {len(SHIPPED)} shipped premises, not the 7 pin 5 names: "
        f"{sorted(SHIPPED)}"
    )
    missing = [name for name in SHIPPED_EXHIBITS if name not in SHIPPED]
    assert not missing, f"the exhibit games are not where this file expects them: {missing}"
    for name in SHIPPED_EXHIBITS:
        idea_id = json.loads(SHIPPED[name].read_text(encoding="utf-8"))["id"]
        exhibit_title, exhibit_text = _prose_of(EXHIBITS[idea_id])
        assert _prose_of(SHIPPED[name]) == (exhibit_title, exhibit_text), (
            f"{SHIPPED[name]} and {EXHIBITS[idea_id]} no longer carry the same prose — "
            f"ambiguity B (two of the seven shipped premises ARE the two exhibits) may "
            f"have been resolved by an edit to a READ-ONLY corpus"
        )


@pytest.mark.parametrize("name", sorted(n for n in SHIPPED if n not in SHIPPED_EXHIBITS))
def test_pin5_the_clean_shipped_premises_still_pass(head, name: str) -> None:
    """Five of the seven. The other two are the exhibits (ambiguity B)."""
    title, text = _prose_of(SHIPPED[name])
    now, before = new_reasons(head, title, text)
    assert now == before, (
        f"{name} picked up new rejects {sorted(set(now) - set(before))}. R-14 change 2: "
        f"'the seven shipped CLEAN premises ... must NOT trip it'; this premise passed "
        f"unchanged at HEAD (all 7 return [] there). Precision is the pin."
    )


def test_pin5_the_official_shaped_corpus_is_the_one_j3_graded() -> None:
    """The precision corpus is the csv's, not this file's memory of it."""
    assert J3_GRADES.is_file(), f"J-3 grades missing: {J3_GRADES}"
    with J3_GRADES.open(encoding="utf-8", newline="") as fh:
        graded = {
            row["idea_id"]
            for row in csv.DictReader(fh)
            if (row.get("verdict") or "").strip() == "OFFICIAL-SHAPED"
        }
    assert graded == set(OFFICIAL_SHAPED), (
        f"J-3's OFFICIAL-SHAPED set moved: csv says {sorted(graded)}, this file maps "
        f"{sorted(OFFICIAL_SHAPED)}. R-14 makes these 10 the precision corpus."
    )
    for idea_id, path in OFFICIAL_SHAPED.items():
        assert path.is_file(), f"{idea_id}: {path} is not on disk"


@pytest.mark.parametrize("idea_id", sorted(OFFICIAL_SHAPED))
def test_pin5_the_official_shaped_ideas_still_pass(head, idea_id: str) -> None:
    title, text = _prose_of(OFFICIAL_SHAPED[idea_id])
    now, before = new_reasons(head, title, text)
    assert now == before, (
        f"{idea_id} picked up new rejects {sorted(set(now) - set(before))}. These are "
        f"J-3's 10 OFFICIAL-SHAPED premises — the best prose the pipeline has produced, "
        f"and R-14 requires all of them to survive the new check. "
        f"({OFFICIAL_SHAPED[idea_id]})"
    )


NONTERMINAL_SENTENCES = {
    "as-long-as-possible": "The only goal is to keep the core intact for as long as possible.",
    "forever": "The only goal is to keep the convoy rolling forever.",
    "endlessly": "The lanes refill endlessly and the run simply continues.",
    "never-let-until": (
        "Never let the shield drop, and the level runs until the player finally slips."
    ),
}


@pytest.mark.parametrize("marker", sorted(NONTERMINAL_SENTENCES))
def test_pin5_the_pattern_family_rejects(head, marker: str) -> None:
    """R-14's named family: 'as long as possible', 'forever', 'endless(ly)',
    'never let/until' + survive-flavored unbounded phrasing.

    AMBIGUITY E: `never-let-until` is the loosest of the four. If ONLY that id
    fails, the marker was read narrower than the contract's slash — reopen the
    sentence rather than widening a check that has to keep 15 real premises clean.
    """
    text = f"{NONTERMINAL_SENTENCES[marker]} {CLEAN_BASE}"
    assert_nonterminal(head, "Holding Pattern", text, f"the {marker!r} premise")


TERMINAL_SENTENCES = {
    "until-terminal": "The level ends the moment the last lamp matches, and the next one opens.",
    "bounded-survive": (
        "The player must survive three timed waves; clearing the third wins the level."
    ),
    "base-only": "",
}


@pytest.mark.parametrize("label", sorted(TERMINAL_SENTENCES))
def test_pin5_terminal_prose_is_untouched(head, label: str) -> None:
    """Precision. Bare 'until' and bounded survival are NOT the pattern family —
    4 of the 10 OFFICIAL-SHAPED premises use 'until' terminally."""
    text = f"{TERMINAL_SENTENCES[label]} {CLEAN_BASE}".strip()
    now, before = new_reasons(head, "Signal Row", text)
    assert now == before, (
        f"the {label!r} premise picked up {sorted(set(now) - set(before))}. It states a "
        f"BOUNDED objective; the check 'catches STATED non-terminality only'. Text: "
        f"{text[:160]!r}…"
    )


def test_pin5_a_new_reason_survives_the_retry_line(head) -> None:
    """The reasons feed PROSE_RETRY_LINE — the existing reject shape, unchanged."""
    title, text = _prose_of(EXHIBITS["b002-triple-i002"])
    reasons = live._prose_rejects(title, text)
    line = live.PROSE_RETRY_LINE.format(reasons="; ".join(reasons))
    assert reasons and all(isinstance(r, str) for r in reasons)
    assert "; ".join(reasons) in line, (
        f"PROSE_RETRY_LINE no longer carries the joined reasons: {line!r}"
    )


# --- pin 6: the three loci, defined once and quoted into the prompt -----------


CONSTANT_NAME_RE = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
SECTION_ONE_RE = re.compile(r"§\s*1(?![0-9])")
LINE_CITE_RE = re.compile(r"(?::|\bL)\s?\d{1,4}(?:\s*[-–]\s*L?\d{1,4})?")


def _string_constants(module) -> dict[str, str]:
    return {
        name: value
        for name, value in vars(module).items()
        if CONSTANT_NAME_RE.match(name) and isinstance(value, str)
    }


def fresh_constants(head_module) -> dict[str, str]:
    """Module-level string constants that are NEW since HEAD.

    LEAD FIX (post-wave-2 push): "new since HEAD" was the LAUNCH-TIME
    discrimination frame — once the wave-2 commit landed, `git show HEAD:`
    carries the same constants and the delta is empty by construction. When
    that is the case the standing pins run over ALL live constants (the
    launch-time proof is on the record in the blind handback).
    """
    before = _string_constants(head_module)
    live_constants = _string_constants(live)
    fresh = {name: value for name, value in live_constants.items() if name not in before}
    return fresh if fresh else dict(live_constants)


@cache
def locus_prompt(locus: str) -> str:
    """A built prose prompt for one locus, normalised. No rng, no driver."""
    return norm_text(
        live.build_prose_prompt(
            cfg_with(),
            seed_terms=["goal.reach", "move.grid"],
            primary="reach_goal",
            failure_family=None,
            tier="t2",
            hazardless=True,
            locus=locus,
        )
    )


def locus_block(head_module) -> dict[str, str]:
    """The NEW constants that reach a prose prompt — the locus block, whatever
    it was named and however many constants it was written in.

    Shape-independent by design: the contract freezes the block's MEANING (three
    loci, §1-cited, selection defined against click) and its destination (the
    prompt), not its python identifiers, and a "short block" is as easily one
    constant as a header plus a citation line.
    """
    found = {}
    for name, value in fresh_constants(head_module).items():
        lines = [norm_text(part) for part in value.splitlines()]
        lines = [line for line in lines if line]
        if lines and any(
            all(line in locus_prompt(locus) for line in lines) for locus in live.LOCI
        ):
            found[name] = value
    return found


def locus_text(head_module) -> str:
    return "\n".join(locus_block(head_module).values())


def test_pin6_a_named_locus_definition_constant_reaches_the_prompt(head) -> None:
    """R-14 change 1: 'a named, canon-cited constant (PROMPT SYNC pattern) …
    quoted into build_prose_prompt where the locus facet is rendered'."""
    found = locus_block(head)
    assert found, (
        f"no NEW module-level string constant of gen/s0_ideas.py appears in a built prose "
        f"prompt. New string constants since HEAD: "
        f"{sorted(fresh_constants(head))}; none of them is quoted into the prompt, so the "
        f"locus facet is still the bare label J-3 measured the cost of."
    )


def test_pin6_the_block_names_all_three_loci(head) -> None:
    found = locus_block(head)
    if not found:
        pytest.fail(
            "no locus block reaches the prompt — see "
            "test_pin6_a_named_locus_definition_constant_reaches_the_prompt"
        )
    lowered = locus_text(head).lower()
    missing = [locus for locus in live.LOCI if locus not in lowered]
    assert not missing, (
        f"the prompt-borne block {sorted(found)} never names {missing}; R-14 change 1 asks "
        f"for 'the THREE loci in one short block (mover / selection / click)'. What it "
        f"says: {locus_text(head)!r}"
    )


def test_pin6_the_block_says_what_selection_means(head) -> None:
    """§1's own distinction: a persistent marker naming a controlled object."""
    if not locus_block(head):
        pytest.fail("no locus block reaches the prompt — see the existence pin")
    text = locus_text(head)
    lowered = text.lower()
    assert "persistent" in lowered and ("marker" in lowered or "mark" in lowered), (
        f"the block never says a selection locus is a PERSISTENT MARKER naming the "
        f"controlled object — affordance-language.md §1's 'selection-marker — a persistent "
        f"mark names the controlled object'. That sentence is the point: J-3 measured 4/23 "
        f"locus drifts, ALL on selection draws. Block: {text!r}"
    )
    assert re.search(r"(later|subsequent|then|next|further)\b", lowered) or "apply" in lowered, (
        f"the block never says later actions APPLY TO the selected object — that is the "
        f"half of the definition a writer needs to keep selection from reading as click. "
        f"Block: {text!r}"
    )
    distinguishers = ("only", "surface", "no ", "not ", "never", "nothing", "without")
    assert "click" in lowered and any(word in lowered for word in distinguishers), (
        f"the block does not distinguish selection from CLICK (§1's other idiom is a pure "
        f"click surface, which carries NO persistent marker — 'what distinguishes it from "
        f"click' is R-14 change 1's own requirement). Block: {text!r}"
    )


def test_pin6_the_block_cites_affordance_section_1_by_line(head) -> None:
    if not locus_block(head):
        pytest.fail("no locus block reaches the prompt — see the existence pin")
    text = locus_text(head)
    assert "affordance-language.md" in text, (
        f"the block quotes the canon without naming it — the PROMPT SYNC pattern cites "
        f"`affordance-language.md` the way visual_canon quotes §9. Block: {text!r}"
    )
    assert SECTION_ONE_RE.search(text), (
        f"the block cites no §1 (the locus-of-control section). Block: {text!r}"
    )
    assert LINE_CITE_RE.search(text), (
        f"the block carries no line reference; visual_canon's shape is "
        f"'(affordance-language.md:L239-240, §9)', and R-14 change 1 asks for §1 'by line'. "
        f"A citation with no line cannot be re-verified when the canon moves. "
        f"Block: {text!r}"
    )


@pytest.mark.parametrize("locus", live.LOCI)
def test_pin6_every_locus_prompt_carries_the_definition(head, locus: str) -> None:
    """Pin 6's own words: 'present in a built prose prompt for each locus value'.

    Behavioural, so it stands whether or not the block turned out to be a named
    constant: the prompt a selection draw gets must define selection, not label
    it.
    """
    prompt = locus_prompt(locus)
    found = locus_block(head)
    if found:
        missing = {}
        for name, value in found.items():
            absent = [
                line
                for line in (norm_text(part) for part in value.splitlines())
                if line and line not in prompt
            ]
            if absent:
                missing[name] = absent[0]
        assert not missing, (
            f"the prose prompt for `interaction locus: {locus}` drops part of the locus "
            f"block: {missing}. The block defines all three loci and goes in on every "
            f"draw — a selection-specific prompt would leave two thirds of J-3's drift "
            f"cases unaddressed."
        )
        return
    lowered = prompt.lower()
    assert all(name in lowered for name in live.LOCI) and "persistent" in lowered, (
        f"the prose prompt for `interaction locus: {locus}` still passes the locus as a "
        f"bare label: it names {[n for n in live.LOCI if n in lowered]} and never says "
        f"what a persistent selection marker is. Cost measured in J-3 §5: 27% "
        f"official-shaped on selection draws vs 75% on mover."
    )


# --- pin 7: the template arms both knobs, and every reader still reads it ------


@cache
def _template_tree() -> dict:
    tree = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    assert isinstance(tree, dict), f"template did not parse to a mapping: {type(tree).__name__}"
    return tree


@pytest.fixture
def template_cfg(tmp_path: Path) -> dict:
    """`load_config` over a tmp COPY — test_docs_template's own hygiene rule."""
    return load_config(_template_copy(tmp_path))


def test_pin7_the_template_arms_corpus_share_officials() -> None:
    ideas = _template_tree().get(IDEAS_BLOCK)
    assert isinstance(ideas, dict), f"config/template.yaml has no `ideas:` block: {ideas!r}"
    assert ideas.get(CORPUS_SHARE_KEY) == TEMPLATE_CORPUS_SHARE, (
        f"config/template.yaml has ideas.{CORPUS_SHARE_KEY} = "
        f"{ideas.get(CORPUS_SHARE_KEY)!r}; R-10 change 4 arms it as "
        f"{TEMPLATE_CORPUS_SHARE!r} (born `measured` in CODE, armed in the TEMPLATE — the "
        f"house split)"
    )


def test_pin7_the_template_arms_secondary_rate_076() -> None:
    ideas = _template_tree().get(IDEAS_BLOCK) or {}
    value = ideas.get(SECONDARY_RATE_KEY)
    assert isinstance(value, (int, float)) and not isinstance(value, bool), (
        f"config/template.yaml has ideas.{SECONDARY_RATE_KEY} = {value!r}; R-10 change 4 "
        f"arms it at {TEMPLATE_SECONDARY_RATE} (= 19/25, the officials' own rate)"
    )
    assert abs(float(value) - TEMPLATE_SECONDARY_RATE) < 1e-9, (
        f"ideas.{SECONDARY_RATE_KEY} = {value!r}, expected {TEMPLATE_SECONDARY_RATE} = 19/25"
    )


def test_pin7_the_template_documents_both_knobs() -> None:
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    comments = "\n".join(line for line in text.splitlines() if line.lstrip().startswith("#"))
    for knob in (CORPUS_SHARE_KEY, SECONDARY_RATE_KEY):
        assert knob in comments, (
            f"config/template.yaml arms ideas.{knob} without explaining it — R-10 change 4 "
            f"asks for it 'commented with the audit anchors and operator ruling', and every "
            f"other knob in that file carries the measurement that justifies it"
        )


def test_pin7_every_knob_reader_accepts_the_armed_template(template_cfg: dict) -> None:
    """test_docs_template's roster, imported (never copied), run in one pass."""
    failures = []
    for name, reader in sorted(_readers().items()):
        try:
            reader(template_cfg)
        except Exception as exc:  # noqa: BLE001 — collected, not swallowed
            failures.append(f"  {name}: {type(exc).__name__}: {exc}")
    assert not failures, (
        f"{len(failures)}/{len(_readers())} config readers rejected the armed "
        f"config/template.yaml:\n" + "\n".join(failures)
    )


def test_pin7_the_roster_still_covers_this_contracts_readers(template_cfg: dict) -> None:
    """The roster GROWS by W2-A's readers; the count is coordinated locally.

    This contract adds no new reader FUNCTION name of its own (`corpus_share`
    and `secondary_rate` are read through `check_config` / `objective_weights`,
    both already on the roster).  If the implementer exported a dedicated
    reader, add it to `test_docs_template._readers` — this pin is the reminder,
    and it fails the moment the roster stops covering both knobs.
    """
    roster = _readers()
    assert "s0_ideas.check_config" in roster, (
        f"test_docs_template's roster lost s0_ideas.check_config: {sorted(roster)}"
    )
    armed = copy.deepcopy(template_cfg)
    ideas = armed.setdefault(IDEAS_BLOCK, {})
    assert ideas.get(CORPUS_SHARE_KEY) == TEMPLATE_CORPUS_SHARE
    ideas[CORPUS_SHARE_KEY] = "not-a-corpus"
    with pytest.raises(ValueError):
        roster["s0_ideas.check_config"](armed)


def test_pin7_the_armed_template_draws_the_officials_mix(template_cfg: dict) -> None:
    """End to end: what the template arms is the mix R-10 asked for."""
    weights = live.objective_weights(template_cfg)
    total = sum(weights.values())
    shares = {family: weights[family] / total for family in live.OBJECTIVE_FAMILIES}
    cap = live._check_reach_cap(template_cfg)
    assert abs(shares["reach_goal"] - cap) < 1e-6, (
        f"the armed template's reach_goal weight share is {shares['reach_goal']:.4f}, not "
        f"the cap {cap} — arming `corpus_share: officials` is what makes the cap bind. "
        f"Shares: { {k: round(v, 4) for k, v in shares.items()} }"
    )
    assert shares["survive"] + shares["connect"] < 0.02, (
        f"the armed template still gives survive+connect "
        f"{shares['survive'] + shares['connect']:.4f} of the objective weight; the "
        f"officials use neither. Shares: { {k: round(v, 4) for k, v in shares.items()} }"
    )


# --- beyond the seven: R-10 change 5, checked at SOURCE level only -------------
# The audit script writes into `out/audit/m3/` and `audit/comparative/data/`, so
# running it is the implementer's job, not a test's. This reads the file.


def test_r10_change5_m3_drawspace_takes_a_config_override() -> None:
    assert M3_SCRIPT.is_file(), f"audit script missing: {M3_SCRIPT}"
    source = M3_SCRIPT.read_text(encoding="utf-8")
    assert "argparse" in source, (
        "m3_drawspace.py grew no argparse import; R-10 change 5: 'add `--config <path>` "
        "(argparse, default the pinned CONFIG constant)'"
    )
    call = re.search(r"add_argument\(\s*[\"']--config[\"'][^)]*\)", source, re.DOTALL)
    assert call, "m3_drawspace.py declares no `--config` argument"
    assert "CONFIG" in call.group(0), (
        f"`--config` does not default to the pinned CONFIG constant, so a no-arg run is no "
        f"longer the audit's reproducible one: {call.group(0)!r}"
    )
    assert 'CONFIG = "config/b003r2-simplicity.yaml"' in source, (
        "the pinned CONFIG constant moved; R-10 change 5 keeps the no-arg run "
        "byte-identical (the lead re-runs it)"
    )
