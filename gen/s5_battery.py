"""S5 — the smoke battery (architecture §3 "S3d — the battery"; B9).

The only play-based difficulty judgment in the pipeline. The duck plays the
gated, baselined game over OpenRouter (D12, LOCKED 2026-09-17), each level
budgeted at EXACTLY 5x its S4 baseline (D8, adopted from the public runner:
519 of 590 death-levels sit at 5.00x), `battery.passes` rollouts per game.
Pilot scale is smoke scale (D22): a tiny token cap so the pilot never blocks
on the OpenRouter budget.

In -> Out (architecture §3 S3d): a gated game + its S4 `metadata.json`
baselines -> `battery-report.json` (+ `battery-levels.csv` in the house
`agent-level.csv` dialect). The stage REFUSES to play a game S4 did not
baseline `fit`: a battery without honest baselines has no budget to spend.

What this stage does NOT do (D9, ICC(1) = -0.024 at 183 levels — the game
explains none of the play-ratio variance): it never judges one game. Per-game
numbers are recorded; scoring is fleet-level, at the batch. Crashes route to
S2 (engine bug) — the routing itself is B11's, this stage only records the
crash so the orchestrator can read it.

Conversation state: ONE TURN, ONE CONVERSATION (stated per the B9 contract).
Every turn sends exactly two messages — the fixed rules block, and the current
settled board with the level/budget line. No history accumulates. The reason
is the cap, and it is arithmetic, not taste: a 64x64 hex board is 4,160
characters, ~1.4k tokens at the 3-chars-per-token estimate this module
charges. Stateless, a turn costs ~1.8k in + a few dozen out, so the pilot's
100k cap buys ~55 turns for the WHOLE battery. With full history the k-th
turn carries k boards, so n turns cost ~1.4k * n(n+1)/2 and the same cap is
gone after ~11 turns — less than one level of one pass. The board IS the
state (spec-v0.3 §2: a mechanic that must be learnable from trajectories has
to survive into settled frames), so the honest cheap loop is the settled
frame plus what the last action did to it.

Everything here is deterministic given a deterministic `chat`: no clocks, no
wall-times, no rng — the same worker and the same replies produce
byte-identical `battery-report.json` and `battery-levels.csv`. (The two retry
backoffs are the module's only wall-times, and a `chat` that fails neither in
transport nor on a throttle never reaches either — see `TRANSPORT_ATTEMPTS`
and `RATE_LIMIT_TRIES`.)
"""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import platform
import re
import sys
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from arcengine import ActionInput, GameAction, GameState

from .backends import DriverError, OpenRouterDriver, _excerpt
from .config import load_config
from .frames import (
    TERMINAL_STATES,
    _fresh_game,
    _hex_row,
    _perform,
    _reset,
    mouse,
    settled_grid,
)
from .s2_implement import parse_token_cap
from .s3_static import load_worker_classes
from .s4_baselines import BATTERY_MARGIN, VERDICT_FIT
from .s4_baselines import METADATA_NAME as S4_METADATA_NAME
from .s4_baselines import OUT_SUFFIX as S4_OUT_SUFFIX

SCHEMA_VERSION = "b9.1"
DEFAULT_CONFIG = "config/b001-pilot.yaml"

# Outputs land in the worker SIBLING `<worker>.s5/` — the B3/B7/B8 rule:
# nothing this pipeline writes ever lands inside a worker directory.
OUT_SUFFIX = ".s5"
REPORT_NAME = "battery-report.json"
CSV_NAME = "battery-levels.csv"

STATUS_COMPLETE, STATUS_TOKEN_CAP, STATUS_PROTOCOL, STATUS_CRASH = (
    "complete", "token-cap", "protocol-failure", "crash")
# Worst-first: one bad pass colors the whole battery's status, because the
# battery is one budgeted run and the orchestrator reads one verdict.
_STATUS_ORDER = (STATUS_CRASH, STATUS_TOKEN_CAP, STATUS_PROTOCOL, STATUS_COMPLETE)

# Every value `row["end_reason"]` can take. The first four are outcomes of
# PLAY; the last three are outcomes of the HARNESS and each closes the row
# that was open when it happened.
END_REASONS = ("level-complete", "win", "budget-exhausted", "game-over",
               "protocol-failure", "token-cap", "crash")

# The house dialect's first three columns are the reference's own
# (`arc-agi-3-agents/out/agent-level.csv`: game,level,baseline_actions,…), so
# a battery CSV drops straight into the play-workstream tooling.
CSV_COLUMNS = ("game", "level", "baseline_actions", "budget_5x", "n_passes",
               "n_completed", "best_actions", "actions_ratio", "tokens", "usd")

# One retry per malformed reply, then the pass ends (B9 contract §3).
PROTOCOL_RETRIES = 1

# --- the transport retry ----------------------------------------------------
#
# THE INCIDENT (R2 pilot, night of 2026-09-22): one OpenRouter call died in the
# TLS handshake ("handshake operation timed out"), `backends.chat` raised
# DriverError, `_run_pass`'s crash net caught it, and §4 routed `played -->
# implemented: crash` — S2 was asked to fix a game whose only fault was
# somebody else's network, and the slot lost its whole battery. The driver has
# no retry BY DESIGN ("stdlib urllib, no session, no retry — retries are the
# caller's policy", `backends.OpenRouterDriver.chat`). This is the caller's
# policy, and it is the narrowest one that answers the incident.
#
# ONLY transport-class failures retry. An auth error, an HTTP 4xx or a
# protocol fault is a fact about the REQUEST: repeating it three times only
# spends three times as long being wrong, and it hides a config error behind a
# 10-second pause. Those propagate unchanged, at the first attempt.
TRANSPORT_ATTEMPTS = 3
# The gaps BETWEEN attempts, so this tuple holds TRANSPORT_ATTEMPTS - 1 of
# them (3 attempts = 2 sleeps = at most 10s added to a turn).
TRANSPORT_BACKOFF_S = (2, 8)
# Matched case-insensitively against `str(DriverError)`, which carries the
# driver's own wording ("[openrouter] request to … failed: <OSError>") — the
# transport failures urllib/ssl/socket spell out.
TRANSPORT_ERROR_SUBSTRINGS = (
    "timed out",
    "timeout",
    "handshake",
    "connection reset",
    "connection refused",
    "temporary failure",
    "urlopen error",
    "eof occurred",
)

# --- the rate-limit retry (b002 contract 2, D1) ------------------------------
#
# THE DEFECT: the needles above are all connection-class, so an OpenRouter
# HTTP 429 matched none of them, propagated at the first attempt, and `_run_pass`'s
# crash net turned a throttle into a battery CRASH — which §4 routes `played -->
# implemented`, buying a full re-implement loop for somebody else's rate limiter.
#
# A 429 is neither the network nor the request: it is the same request, later.
# So it joins the retry class with its OWN ladder, an order of magnitude longer
# than transport's, because a throttle window is measured in tens of seconds
# where a TLS blip is measured in ones. Retries exhausted, nothing changes: the
# error propagates and the crash path records it exactly as before. The fix is
# not-retrying-never, not retrying-forever.
#
# RETRY-AFTER: not reachable. `backends.OpenRouterDriver.chat` builds its 429
# DriverError from the status and a BODY excerpt only (`_scrub(_excerpt(detail))`)
# and raises `from None`, so neither `exc.headers` nor the original HTTPError
# survives to this side — there is nothing here to read a `Retry-After` off.
# Hence the fixed generous ladder below. Surfacing the header in the driver's
# message is a one-line change in `backends.chat` and the only thing that would
# make honouring it possible.
RATE_LIMIT_TRIES = 3
# The gaps BETWEEN tries, so this tuple holds RATE_LIMIT_TRIES - 1 of them
# (3 tries = 2 waits = at most 150s added to a turn).
#
# NAMED `TRIES`/`LADDER` rather than `ATTEMPTS`/`BACKOFF` ON PURPOSE:
# `gen/tests/test_r2_hotfix10.py` discovers the TRANSPORT constants by name
# (`RETRY|RETRIES|BACKOFF|ATTEMPT`, alphabetically first) and pins its sleeps
# against them. A second ATTEMPTS/BACKOFF pair in this module would hand that
# test this table and pin the transport ladder to the wrong numbers.
RATE_LIMIT_LADDER_S = (30.0, 120.0)
# Matched case-insensitively against `str(DriverError)`, like the transport
# class. The shapes these cover, all from `backends.OpenRouterDriver.chat`:
# "[openrouter] HTTP 429 from …" (an HTTPError) and "[openrouter] API error
# 429: …" (a 200 carrying an `error` object — OpenRouter does that).
RATE_LIMIT_SUBSTRINGS = (
    "429",
    "too many requests",
    "rate limit",
    "rate-limit",
    "rate_limit",
)

# The None-usage fallback. A lane that reports no `usage` block must still be
# CHARGED, or a whole battery could run unbounded under a cap it never
# touches. 3 characters per token is the conservative side of the real number
# for this prompt: our payload is mostly 64-character runs of hex digits,
# which tokenize far denser than prose (prose lands near 4), so dividing by 3
# over-charges rather than under-charges. Over-charging ends a run early and
# visibly (`tokens.estimated` is true in the report); under-charging spends
# money nobody approved.
TOKEN_ESTIMATE_CHARS_PER_TOKEN = 3

# The reply is one line plus whatever the model pads around it. The driver's
# own default (1024) governs the completion; S5 passes only `model`, so a test
# fake needs nothing but the frozen `(messages, *, model, …)` signature.
REPLY_EXCERPT_CHARS = 200

_ACTION_LINE_RE = re.compile(r"^ACTION(\d+)(?:\s+(-?\d+)\s+(-?\d+))?$")
_CLICK_ID = GameAction.ACTION6.value
_RESET_ID = GameAction.RESET.value
_COORD_MIN, _COORD_MAX = 0, 63


# --- the reply protocol -----------------------------------------------------

# Fixed instruction block (B9 contract §2/§3). Frozen text: the parser below
# and this block are one contract, and a battery whose rules drifted from its
# parser would score the harness, not the game.
REPLY_PROTOCOL = """\
REPLY PROTOCOL (strict — a regex reads your reply, not a person):
- Play EXACTLY ONE action per reply.
- Put it on a line of its own, that line being exactly ACTION<k> — e.g. ACTION2.
- ACTION6 is a click and takes coordinates: ACTION6 <x> <y>, x the column and
  y the row, both integers 0-63. Every other action takes no arguments.
- The FIRST line of your reply that has this exact shape is the action played;
  anything you write around it is ignored.
- Only the actions listed as available are legal. RESET is never yours to play.
- A reply with no such line is rejected. You get ONE correction; a second
  rejected reply ends the run."""

GAME_BRIEF = """\
You are playing a puzzle game through a text interface.

The board is a 64x64 grid printed as 64 rows of 64 hex digits, top row first:
0-9 are colors 0-9, a-f are colors 10-15. Coordinates are (x, y) with x the
column (0 left) and y the row (0 top).

Nobody will tell you the rules. You infer them from the boards you see and
from what your actions do to them. Complete a level by reaching its goal
state; the game is won when every level is complete. Each level gives you a
limited number of actions — when they run out, the run stops there."""


def parse_reply(text: str, action_ids: Sequence[int]) -> ActionInput:
    """The frozen reply protocol, as a parser.

    Scans the reply for the FIRST line that has the action shape (models pad
    with prose, and the padding is not an error). That line is then the
    candidate and it must be legal: a declared id, never RESET, with
    coordinates 0-63 if and only if it is the click action. A candidate that
    is not legal is a ValueError — never a silent fall-through to a later
    line, because the first choice a model states is the choice it made.

    Raises ValueError for any malformed reply. The caller turns the first one
    into a correction and the second into `protocol-failure` (B9 contract §3).
    """
    if not isinstance(text, str):
        raise TypeError(f"reply must be a string, got {type(text).__name__}")
    declared = sorted({int(a) for a in action_ids} - {_RESET_ID})
    if not declared:
        raise ValueError(
            "the game declares no playable action besides RESET — nothing to parse a reply into"
        )
    for raw_line in text.splitlines():
        match = _ACTION_LINE_RE.match(raw_line.strip())
        if match is None:
            continue
        ident = int(match.group(1))
        coords = (match.group(2), match.group(3))
        if ident == _RESET_ID:
            raise ValueError(
                f"reply plays ACTION{_RESET_ID} (RESET) — RESET is never the battery's to "
                f"play (it would refill the level budget); reply line: {raw_line.strip()!r}"
            )
        if ident not in declared:
            raise ValueError(
                f"reply plays ACTION{ident}, which this game does not declare "
                f"(available: {declared})"
            )
        if ident == _CLICK_ID:
            if coords[0] is None:
                raise ValueError(
                    f"ACTION{_CLICK_ID} is a click and needs coordinates: "
                    f"`ACTION{_CLICK_ID} <x> <y>`; got {raw_line.strip()!r}"
                )
            x, y = int(coords[0]), int(coords[1])
            if not (_COORD_MIN <= x <= _COORD_MAX and _COORD_MIN <= y <= _COORD_MAX):
                raise ValueError(
                    f"click coordinates ({x}, {y}) are outside "
                    f"{_COORD_MIN}-{_COORD_MAX} — the board is 64x64"
                )
            return mouse(x, y)
        if coords[0] is not None:
            raise ValueError(
                f"ACTION{ident} takes no arguments (only ACTION{_CLICK_ID} does); "
                f"got {raw_line.strip()!r}"
            )
        return ActionInput(id=GameAction[f"ACTION{ident}"])
    raise ValueError(
        "no action line in the reply — expected a line that is exactly `ACTION<k>` "
        f"(or `ACTION{_CLICK_ID} <x> <y>`); got: {_excerpt(text, REPLY_EXCERPT_CHARS)!r}"
    )


# --- the observation --------------------------------------------------------


def build_system_message(action_ids: Sequence[int]) -> str:
    """The fixed block: what the board is, which actions exist, the protocol."""
    declared = sorted({int(a) for a in action_ids} - {_RESET_ID})
    listed = ", ".join(f"ACTION{ident}" for ident in declared) or "none"
    return f"{GAME_BRIEF}\n\nAvailable actions: {listed}.\n\n{REPLY_PROTOCOL}\n"


def build_observation(
    grid: Sequence[Sequence[int]],
    *,
    action_ids: Sequence[int],
    pass_index: int,
    passes: int,
    level: int,
    levels_total: int,
    used: int,
    budget: int,
    state: str,
    levels_completed: int,
    last: str | None = None,
    note: str | None = None,
) -> str:
    """One turn's user message: where you are, what you may spend, the board.

    The board is the SETTLED frame (spec-v0.3 §2: `fd.frame[-1]`), rendered as
    64 hex rows by the same `frames._hex_row` the verifier digest uses — one
    encoding for every prompt this pipeline writes.
    """
    declared = sorted({int(a) for a in action_ids} - {_RESET_ID})
    lines = [
        (f"pass {pass_index}/{passes} | level {level}/{levels_total} | "
         f"actions used {used} of {budget} | remaining {budget - used}"),
        (f"engine state: {state} | levels completed: {levels_completed} | "
         f"available actions: {declared}"),
        f"last action: {last}" if last else "last action: none — this is the opening board",
    ]
    if note:
        lines.append(note)
    lines.append("")
    lines.append("board (settled frame, 64 rows x 64 hex digits):")
    lines.extend(_hex_row(tuple(int(v) for v in row)) for row in grid)
    return "\n".join(lines) + "\n"


# --- inputs -----------------------------------------------------------------


def load_battery_metadata(path: Path) -> dict:
    """S4's `metadata.json`, refused unless it can budget a battery.

    Architecture §3 S3d In->Out: the battery plays a game S4 BASELINED. A
    missing file, an unreadable one, or a verdict other than `fit` is a
    ValueError and not a default: playing at a guessed budget would produce a
    number that looks like a difficulty measurement and is not one.
    """
    path = Path(path)
    if not path.is_file():
        raise ValueError(
            f"no S4 metadata at {path} — the battery plays only games S4 baselined "
            f"`{VERDICT_FIT}` (architecture §3 S3d In->Out). Run gen/s4_baselines.py first."
        )
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON ({exc})") from None
    if not isinstance(metadata, Mapping):
        raise ValueError(  # noqa: TRY004 — one refusal type for one input (B9 contract §1)
            f"{path}: expected an object, got {type(metadata).__name__}"
        )
    verdict = metadata.get("verdict")
    if verdict != VERDICT_FIT:
        raise ValueError(
            f"{path}: verdict is {verdict!r}, not {VERDICT_FIT!r} — S4 did not baseline this "
            "game fit, so it has no 5x budget to play at (D8)"
        )
    baselines = metadata.get("baseline_actions")
    if not isinstance(baselines, list) or not baselines:
        raise ValueError(f"{path}: baseline_actions must be a non-empty list, got {baselines!r}")
    for index, value in enumerate(baselines):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(
                f"{path}: baseline_actions[{index}] must be a positive int, got {value!r}"
            )
    return dict(metadata)


def _battery_config(cfg: Mapping) -> dict:
    """The `battery:` block — the stage's ONLY tunables (B9 contract).

    `{model, passes, token_cap}`, every one signed: D12 names the player, D8
    the budget. No key here is optional and no key is invented: a typo in a
    signed knob fails here, loudly.

    `battery.smoke` is GONE (contract D-3 §3). D22's smoke ruling is
    IMPLEMENTED by `battery.token_cap` — the tiny cap IS the smoke scale — and
    the flag it set was required of every config, stamped into every
    battery-report.json, and read by nothing but the report line that printed
    it back. A config that still carries the key parses exactly as before: the
    block's extra keys were never rejected, only its missing ones.
    """
    block = cfg.get("battery") if isinstance(cfg, Mapping) else None
    if not isinstance(block, Mapping):
        raise KeyError(
            "config missing the `battery:` block "
            "{model, passes, token_cap} (architecture §3 S3d Config)"
        )
    missing = [key for key in ("model", "passes", "token_cap") if key not in block]
    if missing:
        raise KeyError(f"config battery block missing {missing}")
    model = block["model"]
    if not isinstance(model, str) or not model.strip():
        raise ValueError(f"battery.model must be a non-empty string, got {model!r}")
    passes = block["passes"]
    if isinstance(passes, bool) or not isinstance(passes, int) or passes < 1:
        raise ValueError(f"battery.passes must be a positive int, got {passes!r}")
    return {
        "model": model,
        "passes": passes,
        "token_cap": parse_token_cap(block["token_cap"]),
    }


def resolve_chat() -> Callable[..., object]:
    """The default `chat` callable: the OpenRouter driver's, key-checked.

    THE injection seam. `run_battery(chat=…)` is the direct one; tests that go
    through `main()` monkeypatch this function (or the `OpenRouterDriver` name
    this module holds). The key is presence-checked HERE, before a single
    engine action is performed, so a missing key is a usage error at second
    zero — never a crash halfway through a pass.
    """
    driver = OpenRouterDriver()
    driver.preflight()
    return driver.chat


# --- the pass ---------------------------------------------------------------


class _TokenCapReached(Exception):
    """The whole-battery token cap was crossed. Control flow, not a failure."""


class _ProtocolFailure(Exception):
    """Two consecutive malformed replies. Ends the pass, not the battery."""


@dataclass
class _Ledger:
    """Cumulative spend for the WHOLE battery, checked after every chat call."""

    cap: int
    tokens_in: int = 0
    tokens_out: int = 0
    estimated: bool = False
    usd: list[float] = field(default_factory=list)
    # Transport-class retries this battery has spent (`_chat_with_transport_retry`).
    # Not spend, but the ledger is the one per-battery object every turn
    # already holds, so the count rides along instead of threading a new
    # parameter through `_turn_action`. Nothing is CHARGED for a retried call:
    # `charge` runs on a result, and a call that raised produced no usage.
    transport_retries: int = 0
    # Rate-limit retries, counted separately for the same reason and next to
    # the same crash record: a crash beside a non-zero count here says "the
    # throttle outlived the ladder", which is a different night's problem from
    # "the wire was down" and neither is an S2 bug report.
    rate_limit_retries: int = 0

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out

    def charge(self, result: object, prompt_chars: int) -> None:
        """Charge one chat result; estimate any field the lane did not report."""
        text = getattr(result, "text", None)
        if not isinstance(text, str):
            raise TypeError(
                f"chat returned {type(result).__name__} with text="
                f"{type(text).__name__} — expected a ChatResult-shaped object"
            )
        tokens_in = getattr(result, "tokens_in", None)
        tokens_out = getattr(result, "tokens_out", None)
        if not isinstance(tokens_in, int) or isinstance(tokens_in, bool):
            tokens_in = prompt_chars // TOKEN_ESTIMATE_CHARS_PER_TOKEN
            self.estimated = True
        if not isinstance(tokens_out, int) or isinstance(tokens_out, bool):
            tokens_out = len(text) // TOKEN_ESTIMATE_CHARS_PER_TOKEN
            self.estimated = True
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        usd = getattr(result, "usd_cost", None)
        if isinstance(usd, (int, float)) and not isinstance(usd, bool):
            self.usd.append(float(usd))
        if self.total >= self.cap:
            raise _TokenCapReached(
                f"{self.total} tokens spent against a {self.cap}-token cap"
            )

    def usd_total(self) -> float | None:
        """Summed where reported, None where nothing was — never estimated."""
        return round(sum(self.usd), 6) if self.usd else None


@dataclass
class _PassState:
    """Where a pass is, so a row can be closed from inside an exception handler."""

    index: int
    level: int = 0  # 0-based index of the level being played
    used: int = 0
    budget: int = 0


def _row(state: _PassState, baseline: int, *, completed: bool, end_reason: str) -> dict:
    if end_reason not in END_REASONS:
        raise ValueError(f"unknown end_reason {end_reason!r} — expected one of {END_REASONS}")
    return {
        "pass": state.index,
        "level": state.level + 1,  # 1-indexed, like actions/level-<i>.json and the CSV dialect
        "baseline": baseline,
        "budget_5x": state.budget,
        "actions_used": state.used,
        "completed": completed,
        "end_reason": end_reason,
    }


def _is_transport_error(exc: DriverError) -> bool:
    """Is this DriverError the NETWORK, rather than the request we sent?

    Substring matching on the message, because that is all a `DriverError`
    carries: `backends.chat` folds urllib's `OSError` family (URLError,
    TimeoutError, DNS, TLS) into one error type, and the only thing that
    survives is its text.
    """
    text = str(exc).lower()
    return any(needle in text for needle in TRANSPORT_ERROR_SUBSTRINGS)


def _is_rate_limit_error(exc: DriverError) -> bool:
    """Is this DriverError a THROTTLE — the same request, allowed later?"""
    text = str(exc).lower()
    return any(needle in text for needle in RATE_LIMIT_SUBSTRINGS)


def _sleep(seconds: float) -> None:
    """The module's only wall-clock wait, behind one name.

    A function rather than a bare `time.sleep` call so a test can neutralize
    the waits by patching EITHER `time.sleep` or this attribute — no test
    should ever spend 150 real seconds proving that a ladder has rungs.
    """
    time.sleep(seconds)


def _ladder_step(ladder: Sequence[float], failures: int) -> float:
    """The gap to wait after `failures` failures (1-based).

    Indexed defensively: the tuple holds the gaps BETWEEN attempts, and a
    shortened one repeats its last gap rather than raising IndexError in the
    middle of a paid pass.
    """
    return ladder[min(failures - 1, len(ladder) - 1)]


def _chat_with_transport_retry(
    chat: Callable,
    messages: list[dict],
    *,
    model: str,
    ledger: _Ledger | None = None,
) -> object:
    """One `chat` call, retried on transport- and rate-limit-class DriverErrors.

    The NARROWEST seam: exactly the call, inside the protocol loop. The retry
    above this one is about what the model SAID; this one is about whether the
    call reached it at all — so a retry here never consumes a protocol
    attempt, and each protocol attempt gets its own transport/rate-limit
    budgets.

    TWO classes, TWO ladders, counted separately (`TRANSPORT_ATTEMPTS` /
    `RATE_LIMIT_TRIES`), because a TLS blip and a throttle window are different
    lengths of wait. The rate-limit test runs FIRST: an error that reads as
    both waits on the longer ladder, which is the safe direction — a throttle
    retried after 2 seconds is a throttle hit again.

    Anything else — auth, any other HTTP 4xx, a malformed response —
    propagates unchanged and immediately, and a failure of either class that
    outlives its budget propagates too: the crash net still catches a network
    that is genuinely down and a rate limiter that is genuinely closed, it
    just no longer catches a blip or a pause.
    """
    transport_failures = 0
    rate_limit_failures = 0
    while True:
        try:
            return chat(messages, model=model)
        except DriverError as exc:
            if _is_rate_limit_error(exc):
                rate_limit_failures += 1
                if rate_limit_failures >= RATE_LIMIT_TRIES:
                    raise
                if ledger is not None:
                    ledger.rate_limit_retries += 1
                _sleep(_ladder_step(RATE_LIMIT_LADDER_S, rate_limit_failures))
                continue
            if _is_transport_error(exc):
                transport_failures += 1
                if transport_failures >= TRANSPORT_ATTEMPTS:
                    raise
                if ledger is not None:
                    ledger.transport_retries += 1
                _sleep(_ladder_step(TRANSPORT_BACKOFF_S, transport_failures))
                continue
            raise


def _turn_action(
    chat: Callable,
    model: str,
    ledger: _Ledger,
    *,
    system: str,
    observation: str,
    action_ids: Sequence[int],
) -> ActionInput:
    """One turn: ask, parse, and on a malformed reply ask once more.

    The correction re-sends the SAME observation with a note naming what was
    wrong — the board has not changed, so re-rendering it is the whole cost of
    a retry (and it is charged like any other turn).
    """
    note: str | None = None
    for attempt in range(PROTOCOL_RETRIES + 1):
        message = observation if note is None else f"{observation}\n{note}\n"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ]
        result = _chat_with_transport_retry(chat, messages, model=model, ledger=ledger)
        ledger.charge(result, len(system) + len(message))
        try:
            return parse_reply(result.text, action_ids)
        except ValueError as exc:
            if attempt >= PROTOCOL_RETRIES:
                raise _ProtocolFailure(
                    f"two consecutive malformed replies; last: {exc}"
                ) from None
            note = (
                f"YOUR LAST REPLY WAS REJECTED: {exc}\n"
                f"It was: {_excerpt(result.text, REPLY_EXCERPT_CHARS)!r}\n"
                "Reply again with the action line alone. This is your only correction."
            )
    raise AssertionError("unreachable: the retry loop returns or raises")  # pragma: no cover


def _run_pass(
    game_cls: type,
    baselines: Sequence[int],
    *,
    index: int,
    passes: int,
    chat: Callable,
    model: str,
    ledger: _Ledger,
) -> tuple[list[dict], str | None, dict | None]:
    """One rollout. Returns (rows, terminal_status, crash).

    `terminal_status` is None when the pass played itself out (win, game over
    or an exhausted budget — all VALID battery outcomes), otherwise the status
    that closed it. A crash or a crossed cap ends the battery; a protocol
    failure ends only this pass.
    """
    state = _PassState(index=index)
    rows: list[dict] = []
    levels_total = len(baselines)
    try:
        game = _fresh_game(game_cls)
        fd = _reset(game)
        state.budget = BATTERY_MARGIN * baselines[state.level]
        last: str | None = None
        while True:
            if fd.state in TERMINAL_STATES:
                # Only reachable straight off RESET (every in-play terminal
                # returns below). A game that is over before it is played is
                # recorded, not crashed on.
                won = fd.state is GameState.WIN
                rows.append(_row(state, baselines[state.level], completed=won,
                                 end_reason="win" if won else "game-over"))
                return rows, None, None
            action_ids = tuple(int(a) for a in fd.available_actions)
            observation = build_observation(
                settled_grid(fd),
                action_ids=action_ids,
                pass_index=index,
                passes=passes,
                level=state.level + 1,
                levels_total=levels_total,
                used=state.used,
                budget=state.budget,
                state=fd.state.name,
                levels_completed=int(fd.levels_completed),
                last=last,
            )
            action = _turn_action(
                chat, model, ledger,
                system=build_system_message(action_ids),
                observation=observation,
                action_ids=action_ids,
            )
            before = int(fd.levels_completed)
            fd = _perform(game, action)
            state.used += 1
            after = int(fd.levels_completed)
            played = _describe(action)

            if after > before:
                # The engine credits the level the action was performed ON
                # (architecture §3 S4 step 1: the transition action belongs to
                # the level it completes) — so this row closes here, and the
                # next level starts with its own fresh 5x budget (D8).
                # `win` is the B9 contract's spelling for the FINAL level; the
                # engine sets WIN there itself (`_win_score` defaults to the
                # level count), and the second clause keeps the spelling right
                # for a game that credits the last level without the state.
                won = fd.state is GameState.WIN or after >= levels_total
                rows.append(_row(state, baselines[state.level], completed=True,
                                 end_reason="win" if won else "level-complete"))
                state.level = after
                if won or state.level >= levels_total:
                    return rows, None, None
                state.used = 0
                state.budget = BATTERY_MARGIN * baselines[state.level]
                last = f"{played} -> completed level {after}; a new budget starts now"
                continue
            if fd.state is GameState.WIN:
                # A win the engine did not credit as a level transition: kept
                # truthful rather than normalized away.
                rows.append(_row(state, baselines[state.level], completed=True, end_reason="win"))
                return rows, None, None
            if fd.state is GameState.GAME_OVER:
                rows.append(_row(state, baselines[state.level], completed=False,
                                 end_reason="game-over"))
                return rows, None, None
            if state.used >= state.budget:
                # The engine cannot skip a level, so an exhausted budget ends
                # the pass here (B9 contract §4).
                rows.append(_row(state, baselines[state.level], completed=False,
                                 end_reason="budget-exhausted"))
                return rows, None, None
            last = f"{played} -> still on level {after + 1}, state {fd.state.name}"
    except _TokenCapReached:
        rows.append(_row(state, baselines[state.level], completed=False,
                         end_reason=STATUS_TOKEN_CAP))
        return rows, STATUS_TOKEN_CAP, None
    except _ProtocolFailure:
        # The model, not the game: the row carries it and the battery goes on
        # to the next pass. `crash` stays None — it routes to S2 and this
        # does not.
        rows.append(_row(state, baselines[state.level], completed=False,
                         end_reason=STATUS_PROTOCOL))
        return rows, STATUS_PROTOCOL, None
    except Exception as exc:  # noqa: BLE001 — the engine/driver crash net (§6)
        rows.append(_row(state, baselines[state.level], completed=False, end_reason=STATUS_CRASH))
        return rows, STATUS_CRASH, {
            "pass": index,
            "level": state.level + 1,
            "error_tail": _error_tail(exc),
            # Transport retries spent before this crash — the whole battery's
            # count, not this pass's: one ledger, one budget, and a crash ends
            # the battery anyway. A non-zero count beside a crash says "the
            # wire, not the game", which is the difference between an S2 bug
            # report and a bad night on the network. It lives HERE because the
            # b9.1 report's top-level keys and its row keys are frozen (B9
            # §"the report schema"); the crash record is the one place a new
            # field does not break that contract.
            "transport_retries": ledger.transport_retries,
            # Its sibling, for the same reason and read the same way: a crash
            # with rate-limit retries behind it is a throttle that outlived the
            # ladder, not a game that is broken.
            "rate_limit_retries": ledger.rate_limit_retries,
        }


def _describe(action: ActionInput) -> str:
    """What the model just played, in the protocol's own spelling."""
    if action.id is GameAction.ACTION6 and action.data:
        return f"ACTION{action.id.value} {action.data.get('x')} {action.data.get('y')}"
    return f"ACTION{action.id.value}"


def _error_tail(exc: BaseException, limit: int = 1200) -> str:
    """The TAIL of the traceback — where a crash actually happened (S2's input)."""
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
    return text if len(text) <= limit else "…" + text[-limit:]


# --- the stage --------------------------------------------------------------


def _versions() -> dict:
    return {
        "arcengine": importlib.metadata.version("arcengine"),
        "python": platform.python_version(),
    }


def _aggregate(rows: Sequence[Mapping], baselines: Sequence[int], passes: int) -> dict:
    """Per-level fleet numbers (D9: recorded, never a per-game gate).

    Every level of the game gets a row, including levels no pass reached
    (`n_passes` 0) — the CSV is a level table in the `agent-level.csv`
    dialect, and a level missing from it would read as a level that does not
    exist. `actions_ratio` is best_actions/baseline over COMPLETED passes: the
    duck's line against the baseline the fleet is calibrated on.
    """
    per_level = []
    for index, baseline in enumerate(baselines):
        level = index + 1
        level_rows = [row for row in rows if row["level"] == level]
        completed = [row for row in level_rows if row["completed"]]
        best = min((row["actions_used"] for row in completed), default=None)
        per_level.append({
            "level": level,
            "baseline": baseline,
            "n_passes": len(level_rows),
            "n_completed": len(completed),
            "best_actions": best,
            "actions_ratio": None if best is None else round(best / baseline, 4),
        })
    best_completed = 0
    for index in range(1, passes + 1):
        done = sum(1 for row in rows if row["pass"] == index and row["completed"])
        best_completed = max(best_completed, done)
    return {
        "per_level": per_level,
        "levels_total": len(baselines),
        "best_levels_completed": best_completed,
    }


def run_battery(
    worker_dir: Path,
    cfg: Mapping,
    *,
    chat: Callable | None = None,
    model: str | None = None,
    metadata_path: Path | None = None,
    out_dir: Path | None = None,
) -> dict:
    """Play `battery.passes` rollouts and write the b9.1 report + level CSV.

    `chat` is the injection seam (None resolves the OpenRouter driver through
    `resolve_chat`); `model` overrides `battery.model`; `metadata_path`
    overrides the sibling `<worker>.s4/metadata.json`; `out_dir` overrides the
    sibling `<worker>.s5/`.

    Failure is NOT an error here: a pass that exhausts a level's budget, or a
    game that ends GAME_OVER, is a valid battery outcome and lands as a row.
    What ends the battery early is the token cap (status `token-cap`) and a
    crash (status `crash`, routed to S2 by the orchestrator); a protocol
    failure ends the pass it happened in and colors the status.
    """
    worker_dir = Path(worker_dir).resolve()
    if not worker_dir.is_dir():
        raise NotADirectoryError(f"worker dir not found: {worker_dir}")
    battery = _battery_config(cfg)  # fail on a bad config before anything is spent
    model_used = model if model is not None else battery["model"]
    if not isinstance(model_used, str) or not model_used.strip():
        raise ValueError(f"model must be a non-empty string, got {model_used!r}")

    meta_path = (
        Path(metadata_path)
        if metadata_path is not None
        else worker_dir.parent / (worker_dir.name + S4_OUT_SUFFIX) / S4_METADATA_NAME
    ).resolve()
    metadata = load_battery_metadata(meta_path)
    baselines = [int(value) for value in metadata["baseline_actions"]]

    target = (Path(out_dir) if out_dir is not None else
              worker_dir.parent / (worker_dir.name + OUT_SUFFIX)).resolve()

    game_cls, _solver_cls = load_worker_classes(worker_dir)
    probe = _fresh_game(game_cls)
    fd = _reset(probe)
    game_id = str(fd.game_id)
    levels_total = int(fd.win_levels)
    del probe
    if levels_total != len(baselines):
        raise ValueError(
            f"{worker_dir}: the game needs {levels_total} level(s) to win but "
            f"{meta_path} baselines {len(baselines)} — the battery would budget the wrong "
            "levels (architecture §3 S3d In->Out: gated game + ITS metadata)"
        )

    if chat is None:
        chat = resolve_chat()
    elif not callable(chat):
        raise TypeError(f"chat must be callable, got {type(chat).__name__}")

    ledger = _Ledger(cap=battery["token_cap"])
    rows: list[dict] = []
    status = STATUS_COMPLETE
    crash: dict | None = None
    passes_completed = 0
    for index in range(1, battery["passes"] + 1):
        pass_rows, terminal, detail = _run_pass(
            game_cls, baselines, index=index, passes=battery["passes"],
            chat=chat, model=model_used, ledger=ledger,
        )
        rows.extend(pass_rows)
        if terminal is None:
            passes_completed += 1
            continue
        status = _worst(status, terminal)
        if terminal == STATUS_CRASH:
            crash = detail
            break  # the game is broken: stop the battery, route to S2
        if terminal == STATUS_TOKEN_CAP:
            break  # the budget is gone: stop cleanly, keep what was played

    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": "s5",
        "game_id": game_id,
        "worker": str(worker_dir),
        "model": model_used,
        "passes": {"requested": battery["passes"], "completed": passes_completed},
        "rows": rows,
        "aggregate": _aggregate(rows, baselines, battery["passes"]),
        "tokens": {
            "tokens_in": ledger.tokens_in,
            "tokens_out": ledger.tokens_out,
            "total": ledger.total,
            "cap": ledger.cap,
            "estimated": ledger.estimated,
        },
        "usd_total": ledger.usd_total(),
        "status": status,
        "crash": crash,
        "config": {
            # No `smoke` field: contract D-3 §3 removed the flag. The smoke
            # scale is `token_cap`, which is right here.
            "passes": battery["passes"],
            "token_cap": battery["token_cap"],
            "model_config": battery["model"],
        },
        "versions": _versions(),
        "paths": {
            "out_dir": str(target),
            "report": str(target / REPORT_NAME),
            "csv": str(target / CSV_NAME),
            "metadata": str(meta_path),
        },
    }
    target.mkdir(parents=True, exist_ok=True)
    (target / REPORT_NAME).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_levels_csv(report, target / CSV_NAME)
    return report


def _worst(current: str, candidate: str) -> str:
    """The more serious of two statuses (crash > token-cap > protocol > complete)."""
    for status in _STATUS_ORDER:
        if status in (current, candidate):
            return status
    raise ValueError(f"unknown status in {(current, candidate)!r}")


def write_levels_csv(report: Mapping, path: Path) -> None:
    """The per-level table, in the house `agent-level.csv` dialect.

    `CSV_COLUMNS` exactly, stdlib csv, `\\n` line endings, an EMPTY field for
    an unknown number (the reference file's own convention: `bp35,1,21,15,,0,,0,,`).

    `tokens` and `usd` are the WHOLE battery's totals repeated on every row,
    not per-level spend: the b9.1 report attributes tokens to the run, not to
    a level (one budget, one cap, D9 fleet-level scoring), and this file is
    derived from that report and never from anything else.
    """
    rows = report["aggregate"]["per_level"]
    tokens = report["tokens"]["total"]
    usd = report["usd_total"]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for entry in rows:
            writer.writerow([
                report["game_id"],
                entry["level"],
                entry["baseline"],
                BATTERY_MARGIN * entry["baseline"],
                entry["n_passes"],
                entry["n_completed"],
                "" if entry["best_actions"] is None else entry["best_actions"],
                "" if entry["actions_ratio"] is None else entry["actions_ratio"],
                tokens,
                "" if usd is None else usd,
            ])


# --- CLI --------------------------------------------------------------------

EXIT_CODES = {STATUS_COMPLETE: 0, STATUS_TOKEN_CAP: 2, STATUS_PROTOCOL: 2, STATUS_CRASH: 3}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S5 smoke battery — the duck plays at 5x baseline (D8/D12/D22)"
    )
    parser.add_argument("--worker", required=True, help="worker dir holding game.py")
    parser.add_argument("--model", default=None, help="override battery.model")
    parser.add_argument(
        "--metadata", default=None, help="S4 metadata.json (default: <worker>.s4/metadata.json)"
    )
    parser.add_argument("--out", default=None, help="write outputs here instead of <worker>.s5/")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        report = run_battery(
            Path(args.worker),
            cfg,
            model=args.model,
            metadata_path=Path(args.metadata) if args.metadata else None,
            out_dir=Path(args.out) if args.out else None,
        )
    except (OSError, ValueError, TypeError, KeyError, DriverError) as exc:
        # Usage/config errors: a missing metadata, a bad worker dir, a missing
        # key. Nothing was played, so there is no report to write.
        print(f"[s5] ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    aggregate = report["aggregate"]
    tokens = report["tokens"]
    usd = report["usd_total"]
    print(
        f"[s5] {report['status'].upper()} {report['game_id']} | "
        f"{report['passes']['completed']}/{report['passes']['requested']} pass(es) | "
        f"{len(report['rows'])} row(s) | best {aggregate['best_levels_completed']}/"
        f"{aggregate['levels_total']} level(s) | model {report['model']}"
    )
    print(
        f"[s5] tokens {tokens['total']}/{tokens['cap']} (in {tokens['tokens_in']}, out "
        f"{tokens['tokens_out']}, estimated {tokens['estimated']}) | "
        f"usd {'unreported' if usd is None else f'${usd:.4f}'} | "
        # (no `smoke` here: contract D-3 §3 removed the flag, and the cap this
        # line already prints IS D22's smoke scale)
        f"{BATTERY_MARGIN}x baseline budgets (D8)"
    )
    for entry in aggregate["per_level"]:
        ratio = entry["actions_ratio"]
        best = entry["best_actions"]
        print(
            f"[s5] L{entry['level']} baseline {entry['baseline']} budget "
            f"{BATTERY_MARGIN * entry['baseline']} | completed {entry['n_completed']}/"
            f"{entry['n_passes']} | best {'none' if best is None else best} | ratio "
            f"{'n/a' if ratio is None else format(ratio, '.2f')}"
        )
    if report["crash"] is not None:
        crash = report["crash"]
        print(f"[s5] crash: pass {crash['pass']} level {crash['level']}")
        print(f"[s5] {crash['error_tail'].splitlines()[-1]}")
        print("[s5] route: S2 (engine bug) — architecture §3 S3d failure routing")
    print(f"[s5] report: {report['paths']['report']}")
    print(f"[s5] csv: {report['paths']['csv']}")
    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
