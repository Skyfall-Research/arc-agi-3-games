"""S2 — implementer (architecture §3 S2; pilot B1-B3, B6).

THE deliberate delta vs upstream re-arc-3: the validate-until-green loop is
CODED, not prose. `green_loop()` drives ONE worker to green or to
reject-to-S1, one attempt at a time:

    session (resumed) -> pipeline scope check + repair -> `make validate`
    -> static gate -> both clean? stop : feed the failing tail back as the
    next prompt

A green `make validate` is not by itself a green attempt: the same
`static.sys-click-truthful` bar the S2b audit already holds generated games to
runs here too (b002 ruling, operator 2026-09-24), beside the level-count check
that holds a build to the number of levels its spec declares (contract C-4b),
and ANY of them failing makes the attempt red with that check's own message in
the ledger and in the next fix prompt — where fixing it is free.
Capped at `implementer.max_green_attempts` (12 in b001-pilot). Every attempt
appends one JSON line to the run ledger with its own cost, so a reject is
auditable line by line.

Pipeline artifacts live BESIDE the worker, never inside it —
`<worker>.attempts.jsonl`, `<worker>.implement-report.json`,
`<worker>.reject.json` — the same rule as B1's sibling manifest copy. The
worker's own `make validate` fails on ANY file absent from the scaffold
manifest, so a ledger written into the worker root would make green
unreachable from attempt 2 on, and this module's own repair pass would
delete it as a stray.

The prompt PAYLOAD is B6, `build_payload()` below: the spec (prose + §11
machine form) plus, per term in the spec, a three-layer DOSSIER quoted from
the canon — the curated playbook pattern, the §3 notes of one official
exemplar, and the evidence base. The engine-wide contracts (8 REQUIRED gates,
4 FORBIDDEN quotes, the §7 layout-seed contract with its skeleton, the
authoring conventions, the scope clause, the visual-legibility rules and the
per-level budget headroom) ride along verbatim. So does the measured VISUAL
grammar (contract V-A, assembled in `gen/visual_canon.py`): the affordance
study's own §§1/2/(3)/5/6/9, the six pinned corpus numbers, the distilled render
craft, the two audited floor/footprint rules (W1-A1), and the corpus's six ways
of teaching level 1. Nothing in the payload is paraphrased and nothing is
timestamped: the same spec builds the same bytes.

Behind the scope clause rides the GRADING SURFACE (b002 prompt sync): the whole
71-term vocabulary with each term's signed definition, the deception catalog
with the six signed levers its keywords stand for and its normalizing matcher
(contract E-1), the birth-time sys_click algorithm and the
seven degenerate policies. The scope clause says the spec's lists are closed;
those four sections are what makes that actionable, and the blind auditor in
`gen/s3_verify.py` is handed the same definitions from the same loader, so the
two sides of the diff read one dictionary instead of two.

The ladder is deliberately lopsided. Only 43 of the 71 terms have a curated
playbook entry and only the terms an official actually ships have an exemplar,
but EVERY term has evidence — so `PayloadReport` records which layers landed
per term and a thin term is visible in the run log rather than silently thin.

B6 also wires `implementer.session_token_cap`: the attempt cap bounds how many
times we try, the token cap bounds what the trying costs. Both reject to S1,
with `reject_reason` saying which bound was hit.

CLI:  python -m gen.s2_implement --worker out/workers/w001 --prompt-file p.md
      python -m gen.s2_implement --payload out/corpus/b001-pilot/<slug>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .canon_docs import (
    VOCAB_DRAFT_MD,
    VOCAB_FINAL_MD,
    BestiaryExcerpt,
    PlaybookEntry,
    SkeletonSection,
    bestiary_excerpt,
    load_conventions,
    load_forbidden_quotes,
    load_playbook_entries,
    load_required_gates,
    load_skeleton,
    load_term_definitions,
)
from .config import load_config
from .frames import CaptureProcessError, capture_worker_isolated
from .s0_ideas import load_vocab
from .s1_spec import (
    DECEPTION_CATALOG,
    LEVEL_VARIETY_LINE,
    LEVER_GROUNDING,
    deception_lever_block,
)
from .s3_gate import POLICIES, ROBUSTNESS_STEPS
from .s3_static import (
    LEVEL_COUNT_CHECK,
    SYS_CLICK_GENERATED_CHECK,
    _check_level_count,
    _check_sys_click,
    _check_sys_click_generated,
    _parse_game,
)
from .visual_canon import (
    CHROME_IS_STRUCTURE,
    DANGER_SECTION,
    DANGER_STANDS,
    FLOOR_AND_FOOTPRINT,
    REFUSAL_NEVER_BOTH,
    TEACHING_BY_SHOWING,
    VISUAL_CRAFT,
    WIN_IS_RENDERED,
    corpus_numbers_card,
    density_section,
    spec_tier,
    visual_grammar_section,
)
from .worker import repair_worker, verify_worker

VALIDATE_CMD = ("make", "validate")
VALIDATE_TIMEOUT_S = 600.0
# A generated game CAN hang (infinite level loop). `make` never returns 124
# itself, so it is unambiguous in the ledger.
VALIDATE_TIMEOUT_EXIT = 124
# The excerpt the fix prompt (and ledger) carries: the HEAD holds the first
# failure/traceback, the TAIL holds make/pytest's summary — a pure tail on a
# 12k-char fresh-scaffold failure drops the earliest traceback entirely.
HEAD_CHARS = 1500
TAIL_CHARS = 2500

# --- the birth-time static gate (b002 ruling, operator 2026-09-24) -------------
# `static.sys-click-truthful` failed 4/4 first builds across two games and
# survived one findings-fed rebuild. `gen/s3_static.py`'s calibration header
# records 6/25 OFFICIAL games failing it, so the corpus the payload quotes as
# exemplars MODELS the defect and implementers copy it. S2b already rejects a
# generated game for it; running the SAME check here moves the fix from a
# respec round to the loop where it costs one attempt. No config knob: this is
# the audit's own bar, applied earlier.
#
# The gate now runs MORE than one check (contract C-4b), so `STATIC_GATE_CHECK`
# names the first of them, not the gate: `GATE_CHECK_IDS` is the whole list and
# `_run_static_gate` reports every one that fails. The second is
# `static.level-count-vs-spec` — the game must implement the number of levels
# its spec declares, caught in the session that built it (b003r2 slot 1 shipped
# 3 of 7). It is the one check here that reads the spec, so it is premise-
# skipped wherever no spec rides (the module CLI, the one-go fixtures).
STATIC_GATE_CHECK = "static.sys-click-truthful"
# W2-B / R-07 (lead-wired): the generated-only sys_click rule joins the birth
# gate between the truthfulness check and the level count — operator ruling,
# not a knob (see the check's own docstring for the reasoning).
GATE_CHECK_IDS = (STATIC_GATE_CHECK, SYS_CLICK_GENERATED_CHECK, LEVEL_COUNT_CHECK)
# Only `fail` is a red gate. `premise-not-met`/`deferred`/`skipped` are honest
# non-answers and never reject — the rule `s3_verify.decide_verdict` states.
STATIC_GATE_FAIL = "fail"
# The attempt's `validate_exit` when the gate is what failed. Must not collide
# with anything make, pytest or the timeout can produce: make uses 1/2, pytest
# 1-5, and VALIDATE_TIMEOUT_EXIT is 124.
STATIC_GATE_EXIT = 125

ATTEMPTS_SUFFIX = ".attempts.jsonl"
REPORT_SUFFIX = ".implement-report.json"
REJECT_SUFFIX = ".reject.json"
REJECT_VERDICT = "reject-to-S1"
# The two bounds a run can hit. The attempt cap keeps the historical verdict
# (B3's routing and its tests read it); the token cap is its own verdict
# because it routes the same way but means something different — the spec was
# expensive, not necessarily unimplementable.
TOKEN_CAP_VERDICT = "token-cap-exceeded"
ATTEMPT_CAP_REASON = "attempt-cap"

# --- infrastructure outages are not game defects (b002 contract 2, D2) ------
# The loop's except path used to convert ANY runner exception into a consumed
# attempt. An auth failure, an account usage limit, a 429 or a missing CLI
# therefore burned the cap on an outage, and two such runs route the SLOT to
# dead (`orchestrator.GREEN_CAP_DEATHS`): an account limit killing a game.
#
# So a driver-level outage (`backends.is_infrastructure_error`, which draws the
# line: a session that RAN and failed is never infrastructure) no longer writes
# an AttemptRecord at all. The SAME attempt index is tried again after a wait,
# up to `INFRASTRUCTURE_TRIES` times; when the ladder is spent the loop stops
# and says the slot is BLOCKED — the game was never judged, and nothing about
# it is known that was not known before the run.
#
# The ladder is long and short: long rungs because the outages it waits out are
# minutes-scale (a rate-limit window, a re-auth), few of them because a loop
# that waits half an hour is a loop nobody can watch.
INFRASTRUCTURE_TRIES = 3
# The gaps BETWEEN tries, so this tuple holds INFRASTRUCTURE_TRIES - 1 of them
# (3 tries = 2 waits = at most 6 minutes before the slot is called blocked).
INFRASTRUCTURE_LADDER_S = (60.0, 300.0)
# Neither `attempt-cap` nor `token-cap-exceeded`: those two are verdicts ON the
# game (it could not be built, or not affordably). This one is a verdict on US.
DRIVER_UNAVAILABLE_REASON = "driver-unavailable"
DRIVER_UNAVAILABLE_VERDICT = "blocked-driver-unavailable"
PAYLOAD_NAME = "payload.md"
SPEC_MD_NAME = "spec.md"
SPEC_YAML_NAME = "spec.yaml"
LAYER_ORDER = ("playbook", "bestiary", "skeleton")

FIX_PROMPT_TEMPLATE = """\
`make validate` is still RED in this worker (attempt {attempt} of {cap}).

Validate output (head + tail of the full log):
--- validate output ---
{validate_tail}
--- end validate output ---
{scope_note}
Diagnose the cause and fix it in game.py and/or solver.py, then run
`make validate` yourself until it is green. Only those two files may change:
the pipeline re-checks the edit scope and re-runs `make validate` after every
attempt, and reverts anything else you touch. Do not weaken or delete the
scaffold tests.
"""

SCOPE_NOTE_TEMPLATE = """
Out-of-scope changes were reverted by the pipeline: {repairs}. Only game.py \
and solver.py may change.
"""

# --- the mission reissue (contract C-A, 2026-09-28) -------------------------
# THE DEFECT, measured on b004 slot 1: attempt 1 died on the driver's 1800s
# session timeout having written NOTHING (`game.py`/`solver.py` still scaffold
# bytes, `partial stdout: <empty>`), and because a timeout leaves no session
# record `resume_id` stayed None — so attempt 2 opened a FRESH conversation and
# was handed `FIX_PROMPT_TEMPLATE`: a red validate log and no mission, no spec,
# no payload. The worker's own AGENTS.md forbids consulting the parent
# directory where `spec.md` lives, so that session could not have recovered the
# brief even if it went looking. It was asked to fix an implementation nobody
# had written.
#
# Not a one-off: across b002/b003/b003r2, 6 of ~20 attempt-1 sessions timed out
# identically, so ~30% of first attempts can arrive at attempt 2 with an empty
# worker and an orphaned conversation.
#
# THE FIX, and its bound: when `worker_is_bare` proves the editable pair is
# still the scaffold, the retry carries the FULL MISSION again — header first
# so the session knows which attempt it is and what validate says, mission last
# so the brief is the freshest thing in the context. Every other retry is
# byte-identical to what it has always been. `scope_note`'s slot semantics are
# FIX_PROMPT_TEMPLATE's, unchanged: the empty string when nothing was repaired.
BARE_RETRY_TEMPLATE = """\
Attempt {attempt} of {cap}: the previous session left NO
implementation — game.py and solver.py are still the untouched
scaffold — so the FULL MISSION follows below. `make validate` is
currently RED:
--- validate output ---
{validate_tail}
--- end validate output ---
{scope_note}
{mission}
"""


@dataclass
class AttemptRecord:
    index: int  # 1-based
    green: bool
    validate_exit: int
    validate_tail: str
    scope_repairs: list[str]
    session: dict  # SessionResult.to_record(), or {"error": ...} if it raised
    # Running total of in+out tokens across this run, up to and including this
    # attempt: the quantity the token cap is compared against, recorded where
    # the decision was made rather than recomputed by a reader.
    tokens_cumulative: int = 0


@dataclass
class ImplementReport:
    worker: str
    green: bool
    attempts: int
    total_usd: float | None
    total_tokens_in: int | None
    total_tokens_out: int | None
    wall_s: float
    records: list[AttemptRecord] = field(default_factory=list)
    # None on green; "attempt-cap" or "token-cap-exceeded" on a reject;
    # "driver-unavailable" when the loop was BLOCKED by an outage and never
    # judged the game at all.
    reject_reason: str | None = None


def sidecar(worker_dir: Path, suffix: str) -> Path:
    """`<worker>.<suffix>` — pipeline state, outside the agent's tree."""
    worker_dir = Path(worker_dir)
    return worker_dir.with_name(worker_dir.name + suffix)


def worker_is_bare(worker_dir: Path) -> bool:
    """Is the editable pair still, byte for byte, the scaffold it was born as?

    True iff EVERY name in the sibling manifest's `editable` list exists under
    `worker_dir` AND hashes to the sha256 that manifest recorded at
    instantiation. A missing editable file or any hash mismatch -> False.

    NARROW BY DESIGN, and that is the whole safety argument for the caller.
    "Bare" here means PROVABLY untouched, not "looks unfinished": a session
    that wrote three lines into game.py and then died is NOT bare, because it
    left something to diagnose and the ordinary fix prompt is the right
    prompt for it. Only the worker that is still the scaffold takes the
    mission-reissue path, so the new branch cannot swallow a session's partial
    work however badly that session ended.

    Fails loud on a missing or malformed manifest rather than guessing: the
    sibling copy is the same authority `verify_worker`/`repair_worker` read,
    `green_loop` already refuses to start without it, and a swallowed error
    here would silently reissue the full mission on every attempt of every run.
    """
    worker_dir = Path(worker_dir)
    manifest = json.loads(
        sidecar(worker_dir, ".manifest.json").read_text(encoding="utf-8")
    )
    scaffold_hashes = manifest["files"]
    for name in manifest["editable"]:
        path = worker_dir / name
        if not path.is_file():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != scaffold_hashes[name]:
            return False
    return True


def _session_record(obj: object) -> dict:
    """Normalize what a session runner returned into a JSON-able record.

    Accepts a plain dict (fakes, replayed ledger rows) or anything with
    `.to_record()` (SessionResult). Anything else is a wiring bug and says so.
    """
    if isinstance(obj, dict):
        return dict(obj)
    to_record = getattr(obj, "to_record", None)
    if callable(to_record):
        record = to_record()
        if not isinstance(record, dict):
            raise TypeError(
                f"{type(obj).__name__}.to_record() returned "
                f"{type(record).__name__}, expected dict"
            )
        return record
    raise TypeError(
        f"session runner returned {type(obj).__name__}; expected a dict or an "
        f"object with .to_record()"
    )


def _excerpt(text: str, head: int = HEAD_CHARS, tail: int = TAIL_CHARS) -> str:
    """Head + tail of a long output; whole thing when it fits."""
    if len(text) <= head + tail + 64:
        return text
    skipped = len(text) - head - tail
    return f"{text[:head]}\n…[{skipped} chars skipped]…\n{text[-tail:]}"


def _last_line(text: str) -> str:
    """The most informative one-liner of a validate run is its LAST line
    (make's error or pytest's summary), never a mid-truncation fragment."""
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _as_text(blob: str | bytes | None) -> str:
    if blob is None:
        return ""
    return blob if isinstance(blob, str) else blob.decode("utf-8", "replace")


def _total(records: list[AttemptRecord], key: str) -> float | int | None:
    """Sum `key` across attempts that reported it; None only if none did."""
    present = [
        r.session.get(key) for r in records if isinstance(r.session.get(key), (int, float))
    ]
    return sum(present) if present else None


def _resolve_cap(cfg: dict, max_attempts: int | None) -> int:
    if max_attempts is None:
        implementer = cfg.get("implementer")
        if not isinstance(implementer, dict) or "max_green_attempts" not in implementer:
            raise KeyError(
                "config missing implementer.max_green_attempts — the green-loop cap "
                "is a signed pilot knob, never defaulted in code"
            )
        max_attempts = implementer["max_green_attempts"]
    max_attempts = int(max_attempts)
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")
    return max_attempts


_TOKEN_CAP_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([kKmM]?)$")
_TOKEN_CAP_UNITS = {"": 1, "k": 1_000, "m": 1_000_000}


def parse_token_cap(raw: object) -> int:
    """`400k` -> 400_000, `1.5M` -> 1_500_000, an int -> itself.

    Config carries the cap the way a human writes it. Anything that is not an
    int or a bare/k/M-suffixed number is a typo in a signed knob, never a
    default: uncapped is spelled by OMITTING the key, not by writing rubbish
    into it.
    """
    if isinstance(raw, bool):  # bool is an int; a boolean cap is meaningless
        raise ValueError(  # noqa: TRY004 — "anything else ValueError" by contract
            f"token cap must be a number or a string like '400k', got {raw!r}"
        )
    if isinstance(raw, int):
        if raw < 0:
            raise ValueError(f"token cap must be >= 0, got {raw}")
        return raw
    if isinstance(raw, str):
        match = _TOKEN_CAP_RE.match(raw.strip())
        if match is None:
            raise ValueError(
                f"cannot parse token cap {raw!r} — expected digits with an optional k/M suffix"
            )
        value = float(match.group(1)) * _TOKEN_CAP_UNITS[match.group(2).lower()]
        if not value.is_integer():
            raise ValueError(f"token cap {raw!r} is not a whole number of tokens ({value})")
        return int(value)
    raise ValueError(
        f"token cap must be an int or a string like '400k'/'1.5M', got {type(raw).__name__}"
    )


def _resolve_token_cap(cfg: dict) -> int | None:
    """The configured token cap, or None when the knob is absent.

    Unlike `max_green_attempts` this key is OPTIONAL: every config written
    before B6 keeps working, uncapped, exactly as it did.
    """
    implementer = cfg.get("implementer")
    if not isinstance(implementer, dict) or "session_token_cap" not in implementer:
        return None
    return parse_token_cap(implementer["session_token_cap"])


def _tokens_spent(session: dict) -> int:
    """in + out for one attempt; an unreported or non-numeric field counts 0.

    A session that died before reporting usage did still cost something, but
    guessing what would make the cap a fiction. Under-counting only ever
    spends more of the budget the operator signed for.
    """
    total = 0
    for key in ("tokens_in", "tokens_out"):
        value = session.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += int(value)
    return total


def _default_session_runner(cfg: dict, model: str | None) -> Callable[..., object]:
    """The real driver-backed runner for `green_loop`.

    `gen.backends` is imported HERE, not at module import: an injected fake
    never needs the session API to exist.
    """
    from .backends import get_driver, get_session_policy

    driver, cfg_model = get_driver(cfg, "implementer")
    policy = get_session_policy(cfg, driver.name)
    chosen = model or cfg_model

    def run(prompt: str, *, cwd: Path, resume_id: str | None):
        return driver.session(prompt, cwd=cwd, model=chosen, resume_id=resume_id, **policy)

    return run


def _is_infrastructure_outage(exc: BaseException) -> bool:
    """Is this raised session the DRIVER being unavailable, not the work failing?

    TWO conditions, both required. It must be a real `backends.DriverError` —
    the driver's own error type, raised by the one layer that knows whether a
    call reached an agent — and its text must match
    `backends.is_infrastructure_error`. An injected runner's own exception
    class is therefore never an outage however it is worded: the loop cannot
    tell a fake's auth-flavoured message from a fake's game-flavoured one, and
    the safe reading of "cannot tell" is the old one (consume the attempt).

    `gen.backends` is imported HERE, not at module import, for the reason
    `_default_session_runner` states: an injected fake must never need the
    session API to exist.
    """
    from .backends import DriverError, is_infrastructure_error

    return isinstance(exc, DriverError) and is_infrastructure_error(exc)


def _is_model_config_error(exc: BaseException) -> bool:
    """Is this raised session a CONFIG error — the requested model does not exist?

    CONTRACT H-1 item 1. The driver decides it at its own error path and raises
    `backends.DriverConfigError`; a real `DriverError` whose TEXT matches
    `backends.is_model_config_error` counts too, on exactly
    `_is_infrastructure_outage`'s two-condition terms (the driver's own type,
    then the text), so a driver path that composes its own DriverError is still
    caught. An injected runner's own exception class is never one, for that
    function's stated reason.
    """
    from .backends import DriverConfigError, DriverError, is_model_config_error

    return isinstance(exc, DriverConfigError) or (
        isinstance(exc, DriverError) and is_model_config_error(exc)
    )


def _sleep(seconds: float) -> None:
    """The loop's only wall-clock wait, behind one name.

    A function rather than a bare `time.sleep` call so a test can neutralize
    the infrastructure ladder by patching EITHER `time.sleep` or this
    attribute — no test should ever spend six real minutes proving that a
    ladder has rungs.
    """
    time.sleep(seconds)


def _ladder_step(ladder: tuple[float, ...], failures: int) -> float:
    """The gap to wait after `failures` failures (1-based).

    Indexed defensively: the tuple holds the gaps BETWEEN tries, and a
    shortened one repeats its last gap rather than raising IndexError in the
    middle of a run.
    """
    return ladder[min(failures - 1, len(ladder) - 1)]


def _run_validate(worker_dir: Path) -> tuple[int, str]:
    """`make validate` in the worker -> (exit code, tail of stdout+stderr)."""
    try:
        proc = subprocess.run(
            list(VALIDATE_CMD),
            cwd=worker_dir,
            capture_output=True,
            text=True,
            timeout=VALIDATE_TIMEOUT_S,
            check=False,  # red IS the signal here; the exit code is the record
        )
    except subprocess.TimeoutExpired as exc:
        # A hung validate is THIS attempt's failure, not the pipeline's:
        # record it and let the loop spend another attempt or reject at cap.
        partial = _as_text(exc.stdout) + _as_text(exc.stderr)
        return VALIDATE_TIMEOUT_EXIT, _excerpt(
            f"{partial}\n[green-loop] `make validate` exceeded "
            f"{VALIDATE_TIMEOUT_S:.0f}s and was killed."
        )
    return proc.returncode, _excerpt(proc.stdout + proc.stderr)


def _evidence_line(item: object) -> str:
    """One `s3_static.Evidence` as a prompt line: where, then what."""
    path = getattr(item, "path", None)
    line = getattr(item, "line", None)
    where = f"{path}:{line}" if path and line else (
        path or getattr(item, "frame_label", None) or getattr(item, "kind", "")
    )
    note = getattr(item, "note", "")
    return f"  - {where}: {note}" if where else f"  - {note}"


def _run_static_gate(worker_dir: Path, spec_path: Path | None = None) -> tuple[bool, str]:
    """Run the birth-time checks against the worker -> (ok, message).

    Two of them (`GATE_CHECK_IDS`), over ONE capture and ONE parse: every check
    that fails is reported, so a build that is wrong in two ways is told both
    at once instead of learning the second after paying an attempt for the
    first. `spec_path` is the spec the worker was built from, or None when no
    spec rides (the module CLI, the one-go fixtures) — the level-count check
    then premise-skips and the rest decide alone.

    The checks are IMPORTED from `gen.s3_static`, never re-implemented: S2's
    gate and S2b's audit must be the same bar, so there is one implementation
    and a drift in it moves both at once.

    The frames it reads come from `frames.capture_worker_isolated` — a FRESH
    interpreter, always, never an in-process load. The generated solver caches
    its sibling game module under a path-derived name of its own choosing, so
    an in-process capture inside a loop that REWRITES `game.py` every attempt
    is exactly the stale-module defect R2 hotfix #8 and b002 hotfix 3 both fixed
    elsewhere; here it would hand attempt N's gate attempt N-1's game.

    A capture that does not come back (`CaptureProcessError`) is a RED attempt
    with the error in the message, never a crash of the loop: the loop still
    owes the run a ledger row and another attempt.
    """
    worker_dir = Path(worker_dir)
    try:
        cap = capture_worker_isolated(worker_dir)
    except CaptureProcessError as exc:
        return False, (
            f"[green-loop] `make validate` is GREEN but the birth-time static gate "
            f"({', '.join(GATE_CHECK_IDS)}) could not be run: the isolated frame capture "
            f"it reads did not come back — {exc}"
        )
    source = _parse_game(worker_dir)
    checks = [
        _check_sys_click(source, cap, worker_dir),
        _check_sys_click_generated(source, cap, worker_dir),
        _check_level_count(cap, spec_path),
    ]
    failed = [check for check in checks if check.status == STATIC_GATE_FAIL]
    if not failed:
        return True, ""
    blocks = []
    for check in failed:
        blocks.append(
            "\n".join(
                [
                    (
                        f"[green-loop] `make validate` is GREEN but the birth-time static "
                        f"gate FAILED: {check.check_id}."
                    ),
                    check.note,
                    *[_evidence_line(item) for item in check.evidence],
                ]
            )
        )
    return False, "\n\n".join(blocks)


def _append_attempt(path: Path, record: AttemptRecord) -> None:
    """One line per attempt, opened and closed per attempt: a run killed
    mid-flight keeps every attempt it finished."""
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), default=str) + "\n")


def _summarize(record: AttemptRecord) -> dict:
    return {
        "index": record.index,
        "green": record.green,
        "validate_exit": record.validate_exit,
        "validate_last_line": _last_line(record.validate_tail),
        "scope_repairs": record.scope_repairs,
        "session_id": record.session.get("session_id"),
        "usd_cost": record.session.get("usd_cost"),
        "tokens_cumulative": record.tokens_cumulative,
        "error": record.session.get("error"),
    }


def green_loop(
    worker_dir: Path,
    prompt: str,
    cfg: dict,
    *,
    session_runner: Callable[..., object] | None = None,
    model: str | None = None,
    max_attempts: int | None = None,
    on_attempt: Callable[[AttemptRecord], None] | None = None,
    spec_path: Path | None = None,
) -> ImplementReport:
    """Drive one worker to green, or to reject-to-S1 at the cap.

    `session_runner(prompt, *, cwd, resume_id)` returns a SessionResult-like
    object or a plain dict; None builds the configured implementer driver.
    `model` overrides the configured model and belongs to that default runner
    only. `on_attempt` (optional) receives each AttemptRecord as it lands, so
    a CLI can stream progress during a multi-hour run. `spec_path` is the spec
    this worker is being built from; it reaches the birth-time gate's
    spec-reading check and nothing else, and None (the default — the module
    CLI, the one-go fixtures) premise-skips that check rather than guessing
    where a spec might be.

    Attempt 1 is handed `prompt` verbatim. A retry is handed the fix prompt —
    unless `worker_is_bare` proves the previous session wrote nothing at all,
    in which case it is handed the fix header AND the full mission again
    (`BARE_RETRY_TEMPLATE`), because there is no implementation to fix.

    A runner exception is normally THIS attempt's failure — the agent may have
    edited files before dying, so the worker is still scoped and validated and
    the attempt is recorded red. The one exception is a driver-level outage
    (`_is_infrastructure_outage`): that consumes nothing, retries the same
    attempt index up the `INFRASTRUCTURE_LADDER_S` ladder, and if the ladder
    runs out stops the loop with `reject_reason` `driver-unavailable` — a
    BLOCKED slot, not a verdict on the game.
    """
    worker_dir = Path(worker_dir).resolve()
    if not worker_dir.is_dir():
        raise FileNotFoundError(f"worker dir not found: {worker_dir}")
    if not sidecar(worker_dir, ".manifest.json").is_file():
        raise FileNotFoundError(
            f"not an instantiated worker (no sibling manifest): {worker_dir}"
        )
    cap = _resolve_cap(cfg, max_attempts)
    token_cap = _resolve_token_cap(cfg)
    if session_runner is not None and model is not None:
        raise ValueError(
            "model= applies to the default driver-backed runner; an injected "
            "session_runner owns its own model"
        )
    runner = session_runner or _default_session_runner(cfg, model)

    attempts_path = sidecar(worker_dir, ATTEMPTS_SUFFIX)
    report_path = sidecar(worker_dir, REPORT_SUFFIX)
    reject_path = sidecar(worker_dir, REJECT_SUFFIX)
    # A verdict file must describe THIS run: clear stale ones up front so
    # "reject.json exists" can never report a previous run's verdict. The
    # attempts ledger is append-only and keeps the whole history.
    for stale in (report_path, reject_path):
        if stale.exists():
            stale.unlink()

    started = time.monotonic()
    records: list[AttemptRecord] = []
    resume_id: str | None = None
    previous_tail = ""
    previous_repairs: list[str] = []
    green = False
    reject_reason: str | None = None
    # The last outage seen, so a `driver-unavailable` verdict can quote what
    # blocked it verbatim instead of asking the operator to guess.
    infrastructure_error: str | None = None
    cumulative_tokens = 0

    for index in range(1, cap + 1):
        if index == 1:
            attempt_prompt = prompt
        else:
            scope_note = (
                SCOPE_NOTE_TEMPLATE.format(repairs="; ".join(previous_repairs))
                if previous_repairs
                else ""
            )
            # A worker still at its scaffold bytes has nothing to fix, so the
            # fix prompt is the wrong prompt: reissue the mission (C-A). The
            # question is asked per attempt because a session can go bare-then-
            # written at any index, and it is asked AFTER the scope repair of
            # the previous attempt, which never touches the editable pair.
            if worker_is_bare(worker_dir):
                attempt_prompt = BARE_RETRY_TEMPLATE.format(
                    attempt=index,
                    cap=cap,
                    validate_tail=previous_tail,
                    scope_note=scope_note,
                    mission=prompt,
                )
            else:
                attempt_prompt = FIX_PROMPT_TEMPLATE.format(
                    attempt=index,
                    cap=cap,
                    validate_tail=previous_tail,
                    scope_note=scope_note,
                )

        # The infrastructure ladder retries THIS attempt index: same prompt,
        # same resume handle, no ledger row, nothing consumed. Only a session
        # that ran — or died of something that is not an outage — leaves this
        # loop with a `session` to record.
        session: dict | None = None
        for try_index in range(1, INFRASTRUCTURE_TRIES + 1):
            try:
                returned = runner(attempt_prompt, cwd=worker_dir, resume_id=resume_id)
            except Exception as exc:  # broad on purpose; BLE001 is satisfied by the re-raise
                # Broad on purpose: the agent may have edited files before
                # dying, so the attempt still gets scoped and validated.
                # Keeping the previous resume_id preserves the last handle we
                # actually saw.
                #
                # EXCEPT a config error (contract H-1 item 1): the provider
                # said the model does not exist, so no agent ran, nothing was
                # edited, and neither a recorded attempt nor the outage ladder
                # can change the answer. It propagates — out of the loop, out
                # of the S2 runner, and out of the run — at its FIRST sighting,
                # with no AttemptRecord, no reject verdict and no wait.
                if _is_model_config_error(exc):
                    raise
                if not _is_infrastructure_outage(exc):
                    session = {"error": f"{type(exc).__name__}: {exc}"}
                    break
                # An outage says nothing about the game, so it buys nothing:
                # no AttemptRecord, no ledger line, no cap spent. Wait and ask
                # the same question again.
                infrastructure_error = f"{type(exc).__name__}: {exc}"
                if try_index >= INFRASTRUCTURE_TRIES:
                    break
                _sleep(_ladder_step(INFRASTRUCTURE_LADDER_S, try_index))
            else:
                # Outside the except: a runner that returns the wrong SHAPE is
                # a wiring bug, and must raise here rather than burn the whole
                # cap recording itself as a session error.
                session = _session_record(returned)
                # None is honest: the CLI reported no handle, so the next
                # attempt starts a fresh conversation rather than resuming a
                # guess.
                resume_id = session.get("session_id") or getattr(returned, "session_id", None)
                break
        if session is None:
            # Every try was an outage and the ladder is spent. Stop the loop
            # WITHOUT a record for this index: the game has not been judged,
            # and a verdict that said otherwise would be a lie about a game
            # nobody played.
            reject_reason = DRIVER_UNAVAILABLE_REASON
            break

        violations = verify_worker(worker_dir)
        repairs: list[str] = []
        if violations:
            repairs = repair_worker(worker_dir)
            # repair_worker already raises if it cannot restore; re-checking
            # keeps the loop's contract independent of that detail.
            leftover = verify_worker(worker_dir)
            if leftover:
                raise RuntimeError(
                    f"scope repair left {len(leftover)} violation(s) in {worker_dir}: {leftover}"
                )

        exit_code, tail = _run_validate(worker_dir)
        if exit_code == 0:
            # Green-with-gate-pass is the ONLY green. The gate runs only here,
            # because a RED validate already carries a fix message and the
            # capture would be measuring a game its own tests reject. The tail
            # becomes the gate's message alone: a green validate log says
            # nothing the next attempt needs, and this way the finding reaches
            # the fix prompt verbatim instead of competing with it for room.
            gate_ok, gate_message = _run_static_gate(worker_dir, spec_path)
            if not gate_ok:
                exit_code = STATIC_GATE_EXIT
                tail = _excerpt(gate_message)
        cumulative_tokens += _tokens_spent(session)
        record = AttemptRecord(
            index=index,
            green=exit_code == 0,
            validate_exit=exit_code,
            validate_tail=tail,
            scope_repairs=repairs,
            session=session,
            tokens_cumulative=cumulative_tokens,
        )
        records.append(record)
        _append_attempt(attempts_path, record)
        if on_attempt is not None:
            on_attempt(record)
        if record.green:
            # A green attempt is never rejected for tokens: the game is built,
            # and the spend that built it is exactly what the budget is for.
            green = True
            break
        if token_cap is not None and cumulative_tokens >= token_cap:
            reject_reason = TOKEN_CAP_VERDICT
            break
        previous_tail = tail
        previous_repairs = repairs

    if not green and reject_reason is None:
        reject_reason = ATTEMPT_CAP_REASON
    report = ImplementReport(
        worker=str(worker_dir),
        green=green,
        attempts=len(records),
        total_usd=_total(records, "usd_cost"),
        total_tokens_in=_total(records, "tokens_in"),
        total_tokens_out=_total(records, "tokens_out"),
        wall_s=round(time.monotonic() - started, 3),
        records=records,
        reject_reason=reject_reason,
    )
    if green:
        report_path.write_text(
            json.dumps(asdict(report), indent=2, default=str) + "\n", encoding="utf-8"
        )
    else:
        if reject_reason == DRIVER_UNAVAILABLE_REASON:
            verdict_name = DRIVER_UNAVAILABLE_VERDICT
        elif reject_reason == TOKEN_CAP_VERDICT:
            verdict_name = TOKEN_CAP_VERDICT
        else:
            verdict_name = REJECT_VERDICT
        verdict = {
            "verdict": verdict_name,
            "reject_reason": reject_reason,
            "worker": report.worker,
            "attempts": report.attempts,
            "last_validate_tail": records[-1].validate_tail if records else "",
            "total_usd": report.total_usd,
        }
        if reject_reason == DRIVER_UNAVAILABLE_REASON:
            # Said in the file, in words, because this verdict is the one a
            # reader is most likely to misread as a reject: it is NOT
            # reject-to-S1, the spec is not implicated, and re-running the slot
            # against a working driver is the whole remedy.
            verdict["blocked_by"] = "infrastructure"
            verdict["infrastructure_error"] = infrastructure_error
            verdict["infrastructure_tries"] = INFRASTRUCTURE_TRIES
            verdict["note"] = (
                "the agent driver was unavailable (auth, usage/rate limit, or a missing CLI) "
                f"on {INFRASTRUCTURE_TRIES} consecutive tries of the SAME attempt. No attempt "
                "was consumed and no judgment was made about this game: it is BLOCKED, not "
                "rejected. Fix the driver and re-run this slot."
            )
        if reject_reason == TOKEN_CAP_VERDICT:
            verdict["token_cap"] = token_cap
            verdict["tokens_cumulative"] = cumulative_tokens
        verdict["records"] = [_summarize(r) for r in records]
        reject_path.write_text(
            json.dumps(verdict, indent=2, default=str) + "\n", encoding="utf-8"
        )
    return report


# --- the prompt payload (B6) ------------------------------------------------

MISSION = """\
## Mission

Implement EXACTLY the game specified below, in this isolated worker.

Write `game.py` (the game) and `solver.py` (the reference solution that wins
every level) — those two files and no others — and drive `make validate` to
green. The spec is the contract: every term it lists must be implemented and
readable in the shipped code, and nothing it forbids may appear."""

GATES_SELF_CHECK = (
    "Before you call it done, re-read `game.py` against each of the eight "
    "gates above, one at a time, and fix what does not hold."
)

# The pilot measured its own failure mode: of b001's 13 blind-verify runs, 12
# rejected, and of the ~44 individual reject reasons exactly 2 were omissive —
# every other one was ADDITIVE, surface the spec never declared. Phase-C audit
# finding #5 says why: the implementer is never told that reachability is the
# auditor's test, nor that the declared lists are CLOSED. Both are said here.
SCOPE_CLAUSE = """\
## Scope — the declared surface is the whole surface (HARD RULE)

Implement every term, mechanic, lever and level the spec declares, and add
**nothing a player could observe** beyond it. The spec's `game.terms` and
`knobs.deceptions` are **closed sets, not minimums**: no extra mechanic, no
extra action effect, no hidden state, no decoy, no telegraph, no tell, no
reactive ornament, and no "small flourish" the spec does not name. If you
believe the game needs something the spec omits, implement the spec as
written and say so in your final message — do not add it.

Your work is audited **blind**: an independent verifier plays the shipped
game without ever reading this spec, writes down every mechanic and
deception it can reach, and **any behaviour it reaches that the spec does
not declare is a rejection — exactly as severe as a declared mechanic you
failed to build**. `make validate` cannot see this; it is green for an
over-built game. Shipping the declared surface and nothing more is the only
defence."""

# --- the grading surface (prompt sync, b002 contract 1) ---------------------
# Audited across both batches: ~80% of all reject reasons trace to two CLOSED
# lists the implementer was never shown — the 71-term vocabulary (an id the
# audit reaches that `game.terms` does not declare is one reject each) and the
# deception catalog with its normalizing matcher. The blind auditor is held to
# the SAME two lists, so from here both sides read one dictionary:
# `canon_docs.load_term_definitions` for the terms and
# `canon_docs.load_deception_levers` for the levers (contract E-1), both quoted
# verbatim from the signed files. Nothing below is retyped — the vocabulary comes
# from the loaders, the catalog from `gen.s1_spec.DECEPTION_CATALOG` and the
# policies from `gen.s3_gate.POLICIES`, so a list that moves moves here too.

VOCABULARY_HEADER = """\
## The closed mechanics vocabulary — the {count} signed terms and what they mean

Every observable behaviour in the shipped game lands on one of these ids. The
blind audit re-derives this game's id set FROM THE CODE ALONE and diffs it
against the spec's `game.terms` in both directions: every id it reaches that
`game.terms` does not declare is one reject, and every id `game.terms` declares
that it cannot reach is one reject too.

Judge by the DEFINITIONS, never by the name you would have given it. The
`*Not:*` clauses are binding in both directions — behaviour a `*Not:*` clause
excludes is not that term, and behaviour a definition covers IS that term
however your own code spells it. A mechanic added because it felt natural
still lands on an id, and an id outside `game.terms` is a rejection.

The bar is REACHABILITY, and it applies to this first build exactly as it
applies to a rebuild: a term the spec declares must be reachable by a player in
ordinary play, and behaviour the spec does not declare must not be observable
at all — so remove it, or redesign it inside what the spec declares.

Quoted verbatim from the signed canon (`{draft}`, superseded on every term it
signs by `{final}`). An `(a/b/c)` after an id is that term's recorded corpus
frequency (live tufa / dead tufa / official) where the canon records one:
frequency, not permission."""

DECEPTION_CATALOG_RULE = """\
## Deception levers — the catalog is closed too ({count} keywords)

`knobs.deceptions` is drawn from exactly these keywords, and nothing else is a
lever the pipeline can name:

{keywords}

Each keyword is the SHORTHAND for one of the {levers} signed levers below,
quoted verbatim from the canon with the official games each was measured on.
The lever is the thing; the keyword is how the diff writes it down.

{block}

The audit reports every lever it finds in these words, and free prose on both
sides is normalized back onto them before the diff: the matcher is separator-
and inflection-tolerant, so "look alike", "look-alikes" and "lookalike" are all
the one keyword `look-alike`, and "decoys" is `decoy`. Renaming a lever does
not hide it — a detected lever that `knobs.deceptions` does not declare is one
reject each, exactly like a term.

Before you call the game done, self-audit it against all {count}: for each
keyword, ask whether anything the player can see does that to them, and if it
does and the spec does not declare it, take it out. A sprite that looks like
another, an inert twin of a real control, a highlight that says yes on a wrong
answer, a palette that hides a distinction the rules depend on, a tell that
only pays off after the loss — each of those is one of these keywords wearing a
different word."""

# The birth-time gate's own rule, stated as something an implementer can BUILD
# to. `gen/s3_static.py::_check_sys_click` is the source of every clause below
# (tag/declare premise, the click-consumer spellings `_click_facts` recognizes,
# and the all-levels name-or-tag comparison against `_handler_targets`); the
# 6/25 figure is that module's calibration header, item 4.
SYS_CLICK_ALGORITHM = """\
## Clickable sprites have to be truthful (checked at birth AND at audit)

`static.sys-click-truthful` runs against this worker after every GREEN
`make validate`: a failure makes the attempt red, with the check's own message
handed back to you, and the blind audit runs the same check again later. It is
mechanical, so build to it rather than around it.

1. **Tag and declare together.** If any sprite anywhere in the file carries the
   tag `sys_click` or `sys_place`, then `ACTION6` must be in
   `available_actions`. Tags without the declared action FAIL: they advertise a
   click the game never offers.
2. **Something must consume the click.** If the engine reports any clickable
   cell at reset, the source must contain a click path, and the check
   recognizes exactly three spellings: a reference to an `ACTION6` / `ACTION7`
   attribute (`GameAction.ACTION6`), a `["x"]` / `["y"]` subscript on a
   `self.action…` expression, or any `.get("x")` / `.get("y")` call. A click
   list nothing reads FAILS — and note that a bare local `action.data["x"]`
   subscript is not one of the three, so read the coordinate with `.get("x")`
   or compare the action id.
3. **Handle every tagged sprite, on EVERY level.** The check walks all levels,
   collects every `sys_click`/`sys_place` sprite the engine would accept
   (`_is_sprite_clickable_now` is honoured), and compares them against the set
   of STRING LITERALS the source discriminates on: literals in comparisons,
   the arguments of `get_sprites_by_*` / `get_sprite_at` / `set_level_by_name`,
   and subscript keys. A clickable sprite whose own name is not in that set and
   none of whose tags is in that set is handled nowhere, and the check FAILS.

So, while you write: every sprite you tag on every level must reach the click
handler under a name or a tag the handler branches on as a literal string. A
handler that discriminates on no literal at all (every tagged sprite reaches
it) passes trivially and is honest. What fails is the middle: tags no branch
ever names. Tag nothing you do not handle, and re-read the levels you wrote
last — a tag copied into level 4 and never wired is the way this check is
usually failed.

4. **If you declare `ACTION6`, TAG your click targets** (`sys_click` on each
   clickable sprite). `static.sys-click-generated` runs at the same birth
   gate and FAILS a game that declares `ACTION6` while tagging nothing: the
   machine consumers of these games enumerate the engine's click list, and a
   raw-coordinate click nothing tags is a click they cannot discover. (Six of
   the 25 official games ship the untagged idiom; it is legal for THEM and
   not for you — a generated game is held to the stricter bar by ruling.)"""

# One line each for the seven, in `POLICIES` order. The NAMES are imported,
# never retyped; each line describes what `gen/s3_gate.py::_build_policy`
# actually drives, branch by branch.
POLICY_SUMMARIES = {
    "noop_like": (
        "the declared action that changes the board least, probed at reset "
        "(ties broken to the lowest id), repeated every step"
    ),
    "repeat_first": "the first declared action id, repeated every step",
    "repeat_configured_single": (
        "the game's primary input, repeated every step: `ACTION6` on the "
        "engine's FIRST clickable cell when click is declared, else the first "
        "declared id"
    ),
    "repeat_up_or_first": (
        "`ACTION1` when it is declared, else the first declared id, repeated "
        "every step"
    ),
    "cycle_moves": (
        "`ACTION1`-`ACTION4` in order, round and round (all declared ids when "
        "the game declares no move quartet)"
    ),
    "cycle_all": (
        "every declared id in order, round and round (a click goes to the "
        "centre cell)"
    ),
    "seeded_random": (
        "a uniform-random declared id each step, with a uniform-random cell "
        "for a click"
    ),
}

DEGENERATE_POLICIES = """\
## The seven degenerate policies the finished game must survive

The pipeline replays the finished game under seven brainless policies, {steps}
steps each, and the gate passes only if all seven complete ZERO levels — not
"fail to win", zero levels. A game a dumb policy beats is gate-rejected however
clever its mechanics are.

{policies}

This is not hypothetical. One of the 25 official games (lp85) FAILS
`repeat_configured_single`: five repeats of a click on the cell the engine
happens to list first complete its level 1, against that level's own baseline
of 17 actions. Its mechanics are fine; the level is not.

So as you lay out each level, ask the seven questions. Can holding one button
win it? Can cycling the four moves win it? Can clicking one cell over and over
win it? If yes, that level needs a reason a direction has to be CHOSEN — an
order to work out, a keyed target, a state that has to be read first — and not
a tighter budget."""


def _policy_lines() -> str:
    """The seven, in `gen.s3_gate.POLICIES` order — a drift raises here."""
    missing = [name for name in POLICIES if name not in POLICY_SUMMARIES]
    stale = [name for name in POLICY_SUMMARIES if name not in POLICIES]
    if missing or stale:
        raise ValueError(
            f"the degenerate-policy list moved: gen.s3_gate.POLICIES is {list(POLICIES)} "
            f"but this section describes {sorted(POLICY_SUMMARIES)} (missing {missing}, "
            f"stale {stale}) — the prompt must name the policies the gate really runs"
        )
    return "\n".join(f"- `{name}` — {POLICY_SUMMARIES[name]}" for name in POLICIES)


def _vocabulary_section(cfg: Mapping) -> str:
    """The 71 ids WITH their signed definitions, grouped by family.

    Generated, never hand-typed: the ids come from `load_vocab` (the vocabulary
    of record) and every definition is the verbatim canon entry
    `canon_docs.load_term_definitions` read out of the two signed files. The
    loader is total over the vocabulary, so a term with no definition raises
    there rather than shipping a prompt that is quietly short a word.
    """
    vocab = load_vocab(cfg)
    definitions = load_term_definitions(cfg)
    groups: dict[str, list[str]] = {}
    for term in sorted(vocab):
        groups.setdefault(term.partition(".")[0], []).append(definitions[term].text)
    body = "\n\n".join(
        f"### {family}\n" + "\n".join(groups[family]) for family in sorted(groups)
    )
    header = VOCABULARY_HEADER.format(
        count=len(vocab), draft=VOCAB_DRAFT_MD, final=VOCAB_FINAL_MD
    )
    return f"{header}\n\n{body}"


def _deception_section(cfg: Mapping) -> str:
    """The closed catalog WITH the six signed levers its keywords stand for.

    Generated, never hand-typed, for the same reason `_vocabulary_section` is:
    the keywords come from `s1_spec.DECEPTION_CATALOG` and every lever is the
    verbatim affordance §7 entry `canon_docs.load_deception_levers` reads, both
    rendered by the ONE block builder the blind auditor's prompt also quotes
    (contract E-1). An implementer self-auditing against bare words and an
    auditor reporting bare words were two guesses at the same list; they now read
    one definition each.
    """
    return DECEPTION_CATALOG_RULE.format(
        count=len(DECEPTION_CATALOG),
        keywords="\n".join(f"- `{keyword}`" for keyword in DECEPTION_CATALOG),
        levers=len(LEVER_GROUNDING),
        block=deception_lever_block(cfg),
    )


# Two defects a human reviewer found in the shipped pilot game, neither of them
# visible to `make validate`: the render scale changed between levels (1-pixel
# lines in L1, 4-pixel tiles in L2) and a corner reference panel nothing in the
# game taught. Standing rules for every game, not per-spec knobs.
VISUAL_LEGIBILITY = """\
## Visual legibility (HARD RULES — pilot review findings)

1. **ONE RENDER SCALE.** Choose one logical cell size in pixels and use it
   for every level. If level 1 draws its board at 4x4-pixel cells, every
   later level draws at 4x4-pixel cells: layouts, counts and geometry may
   change with the level; the scale of a cell may not. (The pilot game
   shipped 1-pixel lines in one level and 4-pixel tiles in another; a human
   reviewer could not read it.)
2. **LEVEL 1 TEACHES BY SHOWING.** Level 1's INITIAL frame must contain at
   least one already-satisfied instance of the win condition — what
   "matched" / "solved" / "correct" looks like must be visible on screen
   before the player acts, so the goal can be inferred by looking. If the
   game uses any legend or reference panel, level 1's initial state must
   make its meaning readable the same way: demonstrated, not encoded."""

# The third hard rule the implementer was graded on without being told (after
# the scope clause and the findings feed). S4 assigns each level a baseline of
# roughly 2-3x its optimal line and never below 6 actions, and the battery
# replays the game at 5x that baseline, so the cap has to clear 5 x baseline:
# `max(30, 15 * optimal)` is 5 x 6 and 5 x (3 x optimal). `make validate` is
# green for a cap that cannot fit — only S4 sees it, a whole build later.
BUDGET_HEADROOM = """\
## Per-level action budgets (HARD RULE — the pipeline measures this)

If a level ends when an action budget runs out, that budget must leave room
for the calibration this pipeline runs downstream. Every level's cap must
satisfy:

    cap >= max(30, 15 * <the optimal number of actions for that level>)

Why that number: the pipeline assigns each level a BASELINE of roughly two
to three times its optimal line, never fewer than 6 actions, and then
replays the whole game at FIVE TIMES that baseline. A cap that cannot admit
`5 x baseline` is rejected as a cap bug and the entire game is sent back to
be re-implemented. (Under `g.cap_fit: record` that reject is downgraded, not
lifted: the fit is still measured on every draw, the violation is written
loudly into the baselines report and `metadata.json`, and the game ships
carrying it as a recorded defect. The number you have to hit is the same
either way.) Measured on a real game: caps set at about 1.5x the
optimal line failed this on five of eight levels, and no redraw could
rescue it.

Budget pressure is NOT where this game's difficulty comes from. Difficulty
comes from the structure a player has to read and the mechanics they have to
work out. Set the cap generously and put the challenge in the mechanics."""

# The §7 layout-seed contract in prompt form. The mechanical convention is
# FROZEN by B10 — `gen/s6_package.py` (`load_layout_contract` /
# `rederive_layouts`) enforces it and `gen/tests/fixtures/s6_seeded/` is its
# reference implementation; the skeleton below is adapted from that fixture,
# our own code. Without this section an implementer ships a game with no
# `build_layout` and S6 refuses it, which is a whole worker burned on a rule
# nobody told them. The seed count quoted in the enforcement line is
# `package.seeds_validated` (pilot ⊕ 5, architecture §3 S6);
# test_b6_payload.py pins the two together, so a knob change fails in the
# suite instead of drifting into the prompt.
#
# THE SOLVER SKELETON'S CACHE (contract E-4, 2026-10-05). It used to key
# `sys.modules` on the game PATH alone, which is the one thing an S2 rewrite
# does not change: in a long-lived batch process a cache hit then served the
# PREVIOUS round's game to a freshly exec'd solver. It now keys on the file's
# `stat()` mtime_ns+size, in a module-local dict, which makes a NEW solver
# staleness-proof without any help from the pipeline. The module NAME keeps
# the path tag as its prefix and appends the stat, so `gen/worker.py`'s
# tag sweep still recognises the entries as this worker's. (Shipped solvers keep
# the old pattern forever — `gen/worker.purge_worker_modules` is what protects
# THEM, and `gen/worker.py`'s header carries the pyc-validation caveat that
# sits under both.)
# The alternative the contract asks about — drop the cache, exec per call —
# was MEASURED here and rejected: exec-loading lantern's 17.1 kB game.py costs
# 6.92 ms cold / 0.115 ms with a warm pyc, against 1.6 us for the `stat()`
# this cache spends (365x-4258x; fixture s6_seeded's 8.7 kB game.py: 0.61 ms /
# 0.064 ms). Where `_game_module()` is called is the solver's choice, and a
# solver that calls it inside `next_action` would pay that per ACTION — S5's
# battery burns up to 100k — so the cache stays and only its KEY changes.
LAYOUT_SEED_CONTRACT = """\
## The §7 layout-seed contract (HARD RULES — spec-v0.3 §7, D13)

Layout-from-seed is REQUIRED FROM BIRTH (spec-v0.3 §7, D13). This game's level
layouts are FUNCTIONS OF the seed: structure — walls, object placement,
distances — varies under it while the spec (terms, knobs, curriculum, win
condition) holds. It cannot be retrofitted, so build it this way from the
first line.

1. **`build_layout(seed: int) -> list` is module-level and PURE.** Importable
   and callable without constructing the game; no I/O, no clock, no globals
   mutated. It returns one JSON-able entry per level (lists/dicts/ints/strs),
   because `json.dumps(build_layout(s), sort_keys=True)` is the comparison
   surface the pipeline uses.
2. **Same seed -> identical result.** Derive every draw from the seed with
   `hashlib.sha256(f"<namespace>:{seed}:{index}")`. Never `random` without
   seeding it from that seed, never `hash()` (salted per process), never a
   clock and never a path.
3. **Distinct seeds -> STRUCTURALLY distinct layouts.** Walls, object
   placement and the distances between things must move. Recolouring,
   ornament or a decorative nudge is NOT structural variation: a
   `build_layout` whose seed only jitters cosmetics is a §7 violation,
   whatever any prose says. Enforcement is MECHANICAL: every seed's layout is
   re-derived and compared as BYTES (`json.dumps(…, sort_keys=True)`), twice
   for the same seed and pairwise across seeds, so two seeds that serialize
   identically ARE the violation — nothing reads an argument that the
   variation was structural enough.
4. **`Game(layout_seed: int | None = None)`.** `None` means the spec's
   `layout.seed` — that integer is the AUTHORED DEFAULT this game bakes in,
   as a module constant (`DEFAULT_LAYOUT_SEED`). Every instance records the
   resolved value as `self.layout_seed`, assigned BEFORE `super().__init__`,
   which builds and enters level 0.
5. **`Solver(layout_seed: int | None = None)`** takes the SAME seed with the
   same default, records `self.layout_seed`, and DERIVES its winning line
   from the layout (search it) — never a hardcoded move list. It must win at
   ANY seed.
6. **`solver.py` must NEVER `import game`.** The pipeline exec-loads game
   files under synthetic module names, so a plain import finds the wrong
   module or none at all. Load the sibling BY PATH, as the skeleton does —
   and key any cache of that load on the FILE'S BYTES (its `stat()`
   mtime+size, as the skeleton does), never on the path alone: `game.py` is
   rewritten IN PLACE between rounds while its path stays the same, so a
   path-keyed `sys.modules` lookup can hand your solver the PREVIOUS
   round's module and make it plan against a layout the game no longer has.
7. **Whatever the geometry decides, derive from the layout** — the per-level
   budget cap first of all. A cap hardcoded for one seed breaks the
   acceptance floors at the next one.

Enforcement: `gen/s6_package.py` refuses a game without `build_layout`; a
seed-ignoring `build_layout` is a §7 violation, not a seed-reject (every
layout is re-derived and compared before a single seed is played); and
validation drives your solver at 5 seeds (`package.seeds_validated`) — it
must WIN at every one.

The shape — adapt the geometry, keep the contract:

```python
# game.py
import hashlib

DEFAULT_LAYOUT_SEED = 20260921            # EXACTLY the spec's layout.seed
LAYOUT_NAMESPACE = "<game-id>/layout/v1"  # namespaced: no cross-stage collisions


def build_layout(seed: int) -> list:      # PURE, module-level, JSON-able
    seed = int(seed)
    layout = []
    for index in range(LEVEL_COUNT):      # LEVEL_COUNT = the spec's level count
        digest = hashlib.sha256(f"{LAYOUT_NAMESPACE}:{seed}:{index}".encode()).digest()
        wall_x = WALL_X_MIN + digest[0] % WALL_X_SPAN    # a wall MOVES
        gap_y = STRIP_Y_MIN + digest[1] % STRIP_ROWS     # its gap MOVES
        start_y = STRIP_Y_MIN + digest[2] % STRIP_ROWS   # placement MOVES
        dist = (GOAL_X - START_X) + abs(start_y - gap_y) + abs(gap_y - GOAL_Y)
        layout.append({"level": index + 1, "wall_x": wall_x, "gap_y": gap_y,
                       "start": [START_X, start_y], "cap": BUDGET_FACTOR * dist})
    return layout


class Game(ARCBaseGame):
    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed           # BEFORE super(): __init__ enters level 0
        self._layout = build_layout(seed)
        super().__init__(game_id=GAME_ID, levels=[_level(e) for e in self._layout],
                         camera=Camera(width=64, height=64), available_actions=[1, 2, 3, 4])
```

```python
# solver.py — NEVER `import game`: the pipeline exec-loads game.py under a
# synthetic module name, so load the sibling BY PATH.
import hashlib
import importlib.util
import sys
from pathlib import Path

_GAME_PATH = Path(__file__).resolve().with_name("game.py")
_GAME_TAG = hashlib.sha256(str(_GAME_PATH).encode()).hexdigest()[:12]
_GAME_CACHE = {}                          # (mtime_ns, size) -> module


def _game_module():
    st = _GAME_PATH.stat()                # KEY ON THE BYTES, never the path alone:
    key = (st.st_mtime_ns, st.st_size)    # game.py is rewritten IN PLACE between
    module = _GAME_CACHE.get(key)         # rounds, and its path never changes
    if module is None:
        name = f"game_{_GAME_TAG}_{key[0]}_{key[1]}"
        spec = importlib.util.spec_from_file_location(name, _GAME_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module        # BEFORE exec: dataclass fields read sys.modules
        spec.loader.exec_module(module)
        _GAME_CACHE[key] = module
    return module


class Solver:
    def __init__(self, layout_seed: int | None = None) -> None:
        mod = _game_module()
        self.layout_seed = mod.DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        # DERIVE the line from the layout (search it) — never a hardcoded move list.
        self.plans = [_plan(entry, mod) for entry in mod.build_layout(self.layout_seed)]
```"""

CLOSING = """\
## Working rules

Work inside this worker directory; `AGENTS.md` is the edit-scope contract and
applies in full. Only `game.py` and `solver.py` may change — the pipeline
re-checks the scope and re-runs `make validate` after every attempt, and
reverts anything else you touch. Do not weaken or delete the scaffold tests.
Run `make validate` yourself until it is green."""

DOSSIER_INTRO = (
    "One dossier per term in the spec, quoted from the signed canon: the "
    "curated engine pattern, the official exemplar that ships it (with "
    "path:line citations into that game), and the evidence base. Build each "
    "term the way the corpus builds it."
)


@dataclass
class TermDossier:
    """Everything the canon says about one term, thickest layer first."""

    term: str
    playbook: PlaybookEntry | None
    bestiary: BestiaryExcerpt | None
    skeleton: SkeletonSection


@dataclass
class PayloadReport:
    """term -> the layers that landed, in `LAYER_ORDER`.

    `visual_sections` is the other half of the same idea for the affordance
    grammar: which `affordance-language.md` sections this payload quoted, so a
    run log says which grammar the game was built against. §3 (Danger) rides
    only for a spec with danger, which is the one section that varies.
    """

    terms: dict[str, list[str]] = field(default_factory=dict)
    visual_sections: list[int] = field(default_factory=list)


def _spec_terms(spec_yaml: Path, cfg: Mapping) -> list[str]:
    """The spec's term list, validated against the signed vocabulary.

    S1's linter already kills an unknown term, so a failure here means a spec
    reached S2 without passing S1 — defense in depth, and it names the term
    rather than assembling a payload that quotes nothing for it.
    """
    document = yaml.safe_load(spec_yaml.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(  # noqa: TRY004 — a malformed spec is bad data, not a caller type error
            f"{spec_yaml}: spec did not parse to a mapping"
        )
    game = document.get("game")
    if not isinstance(game, Mapping):
        raise ValueError(f"{spec_yaml}: spec has no 'game' mapping")  # noqa: TRY004 — as above
    terms = game.get("terms")
    if not isinstance(terms, list) or not terms:
        raise ValueError(f"{spec_yaml}: game.terms must be a non-empty list, got {terms!r}")
    if not all(isinstance(term, str) and term.strip() for term in terms):
        raise ValueError(f"{spec_yaml}: game.terms must be a list of strings, got {terms!r}")
    vocab = load_vocab(cfg)
    unknown = [term for term in terms if term not in vocab]
    if unknown:
        raise ValueError(
            f"{spec_yaml}: game.terms outside the {len(vocab)}-term signed vocabulary: {unknown}"
        )
    seen: list[str] = []
    for term in terms:  # a repeated term is one dossier, in first-seen order
        if term not in seen:
            seen.append(term)
    return seen


def _dossier(
    cfg: Mapping,
    term: str,
    playbook: Mapping[str, PlaybookEntry],
    skeleton: Mapping[str, SkeletonSection],
) -> TermDossier:
    section = skeleton[term]
    exemplar: BestiaryExcerpt | None = None
    if section.officials:
        slug = section.officials[0][0]
        try:
            exemplar = bestiary_excerpt(cfg, slug, term)
        except ValueError as exc:
            # The skeleton is the evidence of record: if it says this official
            # ships the term, a bestiary entry without it is canon drift, not
            # a thin term to shrug at.
            raise ValueError(
                f"skeleton names o:{slug} as the first official for {term!r} "
                f"(playbook-skeleton.md:L{section.source_line}) but {exc}"
            ) from exc
    return TermDossier(
        term=term, playbook=playbook.get(term), bestiary=exemplar, skeleton=section
    )


def _render_dossier(dossier: TermDossier) -> str:
    parts = [f"### {dossier.term}"]
    if dossier.playbook is not None:
        parts.append(f"**Playbook** (playbook.md:L{dossier.playbook.source_line})")
        parts.append(dossier.playbook.text)
    if dossier.bestiary is not None:
        slug = dossier.bestiary.slug
        parts.append(
            f"**Official exemplar {slug}** "
            f"(bestiary/{slug}.md §3, L{dossier.bestiary.source_line})"
        )
        parts.append(dossier.bestiary.text)
    parts.append(f"**Evidence base** (playbook-skeleton.md:L{dossier.skeleton.source_line})")
    parts.append(dossier.skeleton.text)
    return "\n\n".join(parts)


def build_payload(spec_dir: Path, cfg: Mapping) -> tuple[str, PayloadReport]:
    """One linted spec -> the implementer prompt + what the canon could give it.

    Deterministic by construction: terms in spec order, every section quoted
    from a file, no timestamps. The same spec_dir builds byte-identical text.
    """
    spec_dir = Path(spec_dir)
    spec_md = spec_dir / SPEC_MD_NAME
    spec_yaml = spec_dir / SPEC_YAML_NAME
    for path in (spec_md, spec_yaml):
        if not path.is_file():
            raise FileNotFoundError(f"spec dir {spec_dir} has no {path.name}")

    terms = _spec_terms(spec_yaml, cfg)
    playbook = load_playbook_entries(cfg)
    skeleton = load_skeleton(cfg)

    report = PayloadReport()
    dossiers: list[TermDossier] = []
    for term in terms:
        dossier = _dossier(cfg, term, playbook, skeleton)
        layers = [
            name
            for name, present in zip(
                LAYER_ORDER,
                (dossier.playbook is not None, dossier.bestiary is not None, True),
                strict=True,
            )
            if present
        ]
        # Impossible by construction (load_skeleton is total over the
        # vocabulary), and worth saying out loud if it ever stops being.
        assert layers, f"term {term!r} resolved to no canon layer at all"
        report.terms[term] = layers
        dossiers.append(dossier)

    quotes = "\n\n".join(
        f"> {quote.text}\n> — ({quote.source})" for quote in load_forbidden_quotes(cfg)
    )
    grammar, visual_sections = visual_grammar_section(cfg, spec_yaml)
    report.visual_sections = visual_sections
    sections = [
        MISSION,
        # Before either face of the spec: the closed-set rule has to be in hand
        # while the implementer first reads what it is allowed to build.
        SCOPE_CLAUSE,
        # ... and with it the dictionary that makes the closed-set rule
        # actionable. The scope clause says the declared lists are closed; these
        # four sections say what the entries of those lists MEAN, in the same
        # words the blind audit is judged against, so "declared" and "detected"
        # can be the same reading of the same game.
        _vocabulary_section(cfg),
        _deception_section(cfg),
        SYS_CLICK_ALGORITHM,
        DEGENERATE_POLICIES.format(steps=ROBUSTNESS_STEPS, policies=_policy_lines()),
        "## The spec (prose)\n\n" + spec_md.read_text(encoding="utf-8").strip(),
        "## The spec (machine, §11)\n\n```yaml\n"
        + spec_yaml.read_text(encoding="utf-8").strip("\n")
        + "\n```",
        "## Self-check before you finish — the 8 REQUIRED gates\n\n"
        + load_required_gates(cfg)
        + "\n\n"
        + GATES_SELF_CHECK,
        "## The four FORBIDDEN engine contracts (never violate)\n\n" + quotes,
        LAYOUT_SEED_CONTRACT,
        "## Conventions (one orientation, settled frames)\n\n" + load_conventions(cfg),
        # The measured render grammar, straight after the engine's own
        # conventions: the conventions say how the engine draws, these say what
        # the corpus draws. Quoted first because everything after it — the
        # numbers, the craft rules, the two standing hard rules — is either a
        # measurement of this grammar or a rule on top of it.
        grammar,
        # The three wave-3 B1 standing rules ride HERE, named by the module
        # that assembles the payload (lead-wired at the B1 close; the blind
        # pin's prompt-sync reading). DANGER_STANDS rides only when the
        # grammar quoted §3 — the same spec-has-danger condition, carried by
        # the returned section numbers.
        CHROME_IS_STRUCTURE,
        *([DANGER_STANDS] if DANGER_SECTION in visual_sections else []),
        REFUSAL_NEVER_BOTH,
        # Then what those idioms measure OUT to, so "looks like an official" is
        # a band to land in rather than a feeling.
        corpus_numbers_card(),
        # ... and directly under the numbers card, the one of those numbers our
        # own corpus measurably misses BY TIER (contract T-1): the officials'
        # per-level `objects_pcc` figures plus the tier-aware line — t1
        # simplicity is mechanical, not visual. The tier is read by the SAME
        # `spec_tier` the visual card's `density` band is scoped with, and every
        # number is interpolated from the constant that band is cut from.
        density_section(spec_tier(spec_dir)[0]),
        # ... and the render craft the corpus study never states, because a
        # study of 25 finished games cannot say "do not draw grid lines".
        VISUAL_CRAFT,
        # Directly under the craft rules it sharpens: the two things the
        # comparative audit measured our seven shipped games failing (a white,
        # unpainted field; load-bearing state drawn as lone pixels), as REQUIRED
        # rows with §9 anchors and a measurable floor. The craft block says
        # "multi-tile shapes" as advice; this says how big, whose exception it
        # is, and which gate check reads the frames afterwards.
        FLOOR_AND_FOOTPRINT,
        # ... and directly under it the third thing the same audit measured on
        # the same frames (R-04): the WINNING board. The block above says what
        # the board and the things on it are made of; this one says what the
        # board has to say when the game is over, and it carries the same
        # integer the gate's `win-render` check rejects on.
        WIN_IS_RENDERED,
        # Next to the canon's own rendering conventions, before the per-term
        # dossiers turn the reading into code.
        VISUAL_LEGIBILITY,
        # Directly under it: rule 2 says level 1 teaches by showing, and this is
        # the corpus's six ways of doing that. It reads as that rule's catalog.
        TEACHING_BY_SHOWING,
        # The spec writer was held to this same sentence (s1_spec renders it
        # beside the level count — one string, both consumers, the prompt-sync
        # discipline). The implementer re-reads it because the curriculum's
        # variety lives or dies in the LAYOUTS this stage builds
        # (lead-authored, C-4 round: the accepted b003r2 game's levels were
        # "essentially the same").
        "## Level variety (the curriculum's own rule)\n\n" + LEVEL_VARIETY_LINE,
        # With the other standing hard rule, and still ahead of the dossiers:
        # a cap is written with the level's geometry, never bolted on after.
        BUDGET_HEADROOM,
        "## Term dossiers — the signed implementation patterns\n\n"
        + DOSSIER_INTRO
        + "\n\n"
        + "\n\n".join(_render_dossier(dossier) for dossier in dossiers),
        CLOSING,
    ]
    return "\n\n".join(sections) + "\n", report


# --- the re-implement findings feed (b002 hotfix) ---------------------------

# A rebuild after a blind-audit reject is otherwise IDENTICAL to the build that
# earned the reject: same spec, same canon, same payload bytes. The worker's own
# `make validate` cannot see a verifier-side finding, so the habit that earned
# the reject comes back build after build until the re-spec cap kills the slot.
# The S1 re-spec has been handed the findings since the R2 amendment
# (`s1_spec._escalation_note`); this is S2's half of that feed. It is APPENDED
# to the payload rather than woven into it: the scope clause the instructions
# below lean on is already in hand by the time the findings are read, and every
# non-reject path keeps building byte-identical payload bytes.
FINDINGS_HEADER = (
    "## The blind audit REJECTED the previous build of this game — its findings"
)
FINDINGS_INSTRUCTIONS = """\
Fix EVERY finding above in this rebuild — all of them, not the cheapest ones.

The audit that wrote them re-runs BLIND on whatever you ship: it never reads
the spec, this prompt, your commit message or your final reply, and it
re-derives every mechanic and lever it reports FROM THE CODE ALONE. So each fix
has to change what `game.py` / `solver.py` actually do. Prose cannot answer a
finding — a comment, a docstring or an explanation of why the code is fine
changes nothing the audit can see.

The spec is still the whole surface, and the scope clause above applies
unchanged. A finding is NEVER licence to add surface the spec does not declare:

- reachable-but-undeclared (an extra term, lever, effect or tell the audit
  read off the game) is fixed by REMOVING that behaviour, or by redesigning it
  INSIDE what the spec declares — never by keeping it;
- declared-but-unreachable (the spec names it and the audit could not reach it)
  is fixed by BUILDING it, reachable by a player in ordinary play."""

# The advisory half of the feed (contract C-3, b003). With
# `verifier.term_corroboration` on, a term finding the audit made for the FIRST
# time does not reject — the blind pass's term findings rotate, so one round's
# say-so is not evidence about the game — and it lands in the report's
# `diff.uncorroborated_terms` record instead. The rebuild is still told, because
# the same sighting next round DOES reject, and a rebuild that never hears about
# a standing finding can only answer it by luck.
#
# Rendered AFTER `FINDINGS_INSTRUCTIONS`, not before: those instructions say
# "Fix EVERY finding above — all of them", and a recorded warning listed above
# that sentence would be read as mandatory, which is exactly the "the finding
# rejects on one round's say-so" behavior the knob exists to remove. Below it,
# the block is what it is — a heads-up with its own one-sentence rule.
UNCORROBORATED_TERMS_KEY = "uncorroborated_terms"   # gen/s3_verify writes it
UNCORROBORATED_TERMS_HEADER = """\
The audit ALSO recorded these first-sighting term findings — not yet
corroborated by a consecutive round, so they do not reject, but a repeat
next round will:"""

# --- contract P-B: the SEED SELF-CHECK --------------------------------------
#
# The b004 seed-3 failure and the s6 crash containment that followed it both say
# the same thing: a rebuild answering an S6 seed reject can make the named seed
# build and still ship a layout with no winning line at some level, because
# `make validate` drives the AUTHORED seed only. The findings feed is the one
# channel that reaches the session, so the demand rides with the rows that
# caused it — and ONLY with them. A findings section carrying no seed row
# renders byte-identical to what this function rendered before this contract.
SEED_SELFCHECK_INSTRUCTION = (
    "Before finishing: reproduce {calls} for EVERY seed named above and verify a winning "
    "line exists for every level (the §7 check); state in one line that you did."
)
# What counts as "a seed row", and how its seed is read. The S6 runner writes
# `{"code": "s6.seed-reject", "detail": "seed 3: <why>"}` per failing seed, and
# the orchestrator's fallback row for a stage that declared no findings carries
# the stage reason (`s6 seed-reject at seed(s) [3] (route: ...)`). Both name the
# seed in prose, so the number is read from the text rather than from a field
# that only one of them has — and a row carrying an int `seed` key is honoured
# first, because a field beats a regex whenever there is one.
_SEED_NAMED = re.compile(r"\bseeds?\b[^0-9\n]{0,6}(-?\d+(?:\s*,\s*-?\d+)*)")

# --- the patch baseline (contract C-1; measured, b002 slot 3) ---------------
# The findings feed above tells a rebuild WHAT to fix; it never told the session
# what it was fixing. A re-implement after an S2b reject runs against the SAME
# payload bytes in a worker whose `game.py` is already the previous,
# validate-green build (the S2 runner re-instantiates nothing when the worker
# exists), and the session FRESH-TRANSLATES the spec every lap. Measured on
# b002 slot 3: two laps lost to the term SEESAW — a term implemented one way in
# lap N vanishes from lap N+1's retranslation and the blind audit flags the
# flip, so a rebuild that answered every finding still earned a reject for
# surface the previous lap had right.
#
# The fix is S1's escalation-BASELINE pattern applied to S2: say that the file
# on disk is this session's own previous answer and that the job is to MODIFY
# it. Appended AFTER the findings (the findings name what must change; this
# names what must not), and only when there is a baseline to point at — the
# knob off, a first build, or a worker with no `game.py` all keep the prompt
# byte-identical to what it was before this contract.
PATCH_BASELINE_SECTION = """\
## YOUR BASELINE — modify, do not re-translate

`game.py` and `solver.py` in this worker are YOUR OWN previous
implementation of this same spec: it passed `make validate` and was
rejected by the blind audit only for the findings listed above. Treat it
as the baseline. Fix EXACTLY what the findings name and keep everything
else byte-stable: every gratuitous re-translation re-rolls the blind
audit and has cost this pipeline whole laps. Do not restructure, rename,
or rewrite working mechanics; run `make validate` after your edits as
usual."""


def patch_baseline_enabled(cfg: Mapping) -> bool:
    """`implementer.patch_baseline` — is the baseline section armed?

    DEFAULTS to False, like `s1_spec._lint_require_render` and unlike
    `implementer.max_green_attempts`: every config written before this contract
    (and every future one that does not want it) assembles byte-identical
    prompts, which is what makes the knob optional rather than a flag day. A
    non-bool is a loud ValueError read at assembly time — `"yes"` is a typo in
    a signed knob, never a truthy string, and a knob silently misread as ON
    would change the bytes of every rebuild in the batch.
    """
    implementer = cfg.get("implementer")
    value = implementer.get("patch_baseline", False) if isinstance(implementer, Mapping) else False
    if not isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 — contract C-1 pins ValueError for this knob
            f"implementer.patch_baseline must be a bool, got {value!r} — it decides whether a "
            f"rebuild is told to patch its own previous build"
        )
    return value


def baseline_sha(worker: Path) -> str | None:
    """sha256 of `<worker>/game.py`'s bytes, or None when there is no baseline.

    The identity of the file the baseline section points at, recorded by the
    caller so a lap's row says WHICH bytes it was handed to patch. None is the
    honest answer for a first build (no worker content yet) and is what the
    caller reads as "no baseline to claim", so the two questions — is there a
    baseline, and which one — have one answer.
    """
    game = Path(worker) / "game.py"
    if not game.is_file():
        return None
    return hashlib.sha256(game.read_bytes()).hexdigest()


def findings_section(report: Mapping) -> str:
    """The S2b reject this rebuild must answer, as one prompt section.

    `report` is the LOADED `worker.verifier-report.json`, and only ever a
    REJECT: a pass (or a report with no verdict at all) reaching here is a
    wiring bug in the caller, not an empty section to render. Every
    `reject_reasons` entry is quoted VERBATIM, in the report's order — the
    implementer's job is to answer those exact strings — with `term` / `lever`
    and `detail` rendered only when the entry carries them, since the six
    reject codes do not all carry the same fields. A reject with no reasons is
    malformed state and raises: an empty findings list is the blind rebuild
    this feed exists to prevent.

    A report whose diff carries a non-empty `uncorroborated_terms` (contract
    C-3: term findings the corroboration pass demoted to warnings) appends one
    advisory block naming each of them. A report without the key — every run on
    the canon default — renders byte-identical bytes to what this function
    rendered before the knob existed.

    Pure and deterministic, like `build_payload`: the same mapping renders the
    same bytes, and the text ends with a newline so an appended section still
    leaves `payload.md` newline-terminated.
    """
    verdict = report.get("verdict")
    if verdict != "reject":
        raise ValueError(
            f"findings_section renders a verifier REJECT, and this report's verdict is "
            f"{verdict!r} — S2 is only ever handed a reject to answer"
        )
    reasons = report.get("reject_reasons")
    if not isinstance(reasons, list) or not reasons:
        raise ValueError(
            f"a reject carrying no `reject_reasons` is malformed — there would be nothing "
            f"for the rebuild to fix (got {reasons!r})"
        )
    findings = []
    for index, reason in enumerate(reasons):
        code = reason.get("code") if isinstance(reason, Mapping) else None
        if not isinstance(code, str) or not code.strip():
            raise ValueError(
                f"reject_reasons[{index}] has no `code` — a finding is identified by its "
                f"code, and there is nothing to quote to the rebuild without one: {reason!r}"
            )
        # code first, then whichever of term/lever this code carries, then the
        # detail: missing fields are omitted, so a bare code renders alone.
        parts = [f"`{code}`", *(f"`{reason[key]}`" for key in ("term", "lever") if reason.get(key))]
        bullet = " ".join(parts)
        if reason.get("detail"):
            bullet += f" — {reason['detail']}"
        findings.append(f"- {bullet}")
    sections = [FINDINGS_HEADER, "\n".join(findings), FINDINGS_INSTRUCTIONS]
    # Contract P-B, rendered here because this is where the findings render —
    # the S2 runner feeds BOTH the verifier report and the gate/S4/S6
    # stage-findings payload through this one function, and the demand belongs
    # with the seed rows wherever they came from.
    selfcheck = _seed_selfcheck_block(reasons)
    if selfcheck:
        sections.append(selfcheck)
    advisory = _uncorroborated_terms_block(report)
    if advisory:
        sections.append(advisory)
    return "\n\n".join(sections) + "\n"


def _named_seeds(reasons: Sequence[Mapping]) -> list[int]:
    """Every seed the findings rows NAME, in the rows' own order, deduped.

    A row contributes when it carries an int `seed`, or when its `code` or
    `detail` names one in prose (`seed 3: …`, `seed(s) [3, 11] …` — the two
    shapes the S6 runner and the orchestrator's fallback row actually write).
    A row that mentions seeds but names no number contributes nothing: contract
    P-B's paragraph has to name the seeds it demands, and a demand with a hole
    in it is worse than none.
    """
    seeds: list[int] = []

    def keep(value: int) -> None:
        if value not in seeds:
            seeds.append(value)

    for reason in reasons:
        if not isinstance(reason, Mapping):
            continue
        field = reason.get("seed")
        if isinstance(field, int) and not isinstance(field, bool):
            keep(field)
            continue
        text = " ".join(
            str(reason.get(key) or "") for key in ("code", "detail", "note")
        )
        for match in _SEED_NAMED.finditer(text):
            for number in match.group(1).split(","):
                keep(int(number.strip()))
    return seeds


def _seed_selfcheck_block(reasons: Sequence[Mapping]) -> str:
    """Contract P-B's one instruction paragraph, or `""` when no row names a seed.

    `""` is the byte-identity guarantee: every findings section that carries no
    S6 seed failure renders exactly the bytes it rendered before this contract.
    """
    seeds = _named_seeds(reasons)
    if not seeds:
        return ""
    calls = ", ".join(f"build_layout({seed})" for seed in seeds)
    return SEED_SELFCHECK_INSTRUCTION.format(calls=calls)


def _named(value: object) -> bool:
    """Non-empty text — what a bullet needs to say anything at all."""
    return isinstance(value, str) and bool(value.strip())


def _uncorroborated_terms_block(report: Mapping) -> str:
    """The C-3 advisory, or `""` when the report carries no such record.

    Reads `report["diff"]["uncorroborated_terms"]` defensively — a dry run's
    report has no diff at all and a canon-default run's diff has no such key —
    and renders each entry in the same `- \\`code\\` \\`term\\`` bullet style the
    reject findings use, so the two lists read as one document. An entry that
    does not carry both fields raises rather than rendering a bullet with a
    hole in it: this block exists to name what is waiting, and a nameless
    warning is worse than none.
    """
    diff = report.get("diff")
    entries = diff.get(UNCORROBORATED_TERMS_KEY) if isinstance(diff, Mapping) else None
    if not entries:
        return ""
    if not isinstance(entries, list):
        raise ValueError(  # noqa: TRY004 — a loaded report is bad DATA, not a caller's type slip
            f"diff.{UNCORROBORATED_TERMS_KEY} must be a list of "
            f"{{term, code, note}} records, got {entries!r}"
        )
    bullets = []
    for index, entry in enumerate(entries):
        code = entry.get("code") if isinstance(entry, Mapping) else None
        term = entry.get("term") if isinstance(entry, Mapping) else None
        if not _named(code) or not _named(term):
            raise ValueError(
                f"diff.{UNCORROBORATED_TERMS_KEY}[{index}] needs both a `code` and a "
                f"`term` — the rebuild is told which finding is one round from "
                f"rejecting, and there is nothing to name without them: {entry!r}"
            )
        bullets.append(f"- `{code}` `{term}`")
    return "\n\n".join([UNCORROBORATED_TERMS_HEADER, "\n".join(bullets)])


def _print_attempt(record: AttemptRecord) -> None:
    cost = record.session.get("usd_cost")
    cost_text = f"${cost:.4f}" if isinstance(cost, (int, float)) else "$unreported"
    line = (
        f"[s2] attempt {record.index}: {'green' if record.green else 'red  '}"
        f" | {cost_text} | exit {record.validate_exit} | {_last_line(record.validate_tail)}"
    )
    if record.scope_repairs:
        line += f" | repaired: {'; '.join(record.scope_repairs)}"
    if record.session.get("error"):
        line += f" | session error: {record.session['error']}"
    print(line, flush=True)


def _run_payload(args: argparse.Namespace, cfg: dict) -> int:
    """`--payload <spec-dir>`: assemble the prompt, report the resolution, write it."""
    spec_dir = Path(args.payload)
    payload, report = build_payload(spec_dir, cfg)
    width = max((len(term) for term in report.terms), default=4)
    print(f"[s2] payload for {spec_dir}")
    print(f"[s2]   {'term'.ljust(width)} | layers")
    for term, layers in report.terms.items():
        print(f"[s2]   {term.ljust(width)} | {', '.join(layers)}")
    # Which affordance-language sections this spec pulled in — §3 is the one
    # that varies, so this line says at a glance whether the game has danger.
    print(f"[s2]   affordance grammar | §§{', '.join(str(n) for n in report.visual_sections)}")
    out_path = Path(args.out) if args.out else spec_dir / PAYLOAD_NAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")
    print(f"[s2] {len(report.terms)} term(s) | {len(payload)} chars -> {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S2 coded validate-until-green loop")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--worker", help="instantiated worker dir (green-loop mode)")
    mode.add_argument("--payload", help="linted spec dir (payload-assembly mode)")
    parser.add_argument("--prompt-file", default=None, help="file holding the S2 prompt")
    parser.add_argument(
        "--out", default=None, help="payload mode: write here (default <spec>/payload.md)"
    )
    parser.add_argument("--model", default=None, help="override the configured implementer model")
    parser.add_argument(
        "--max-attempts", type=int, default=None,
        help="override implementer.max_green_attempts",
    )
    parser.add_argument("--config", default="config/b001-pilot.yaml")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.payload:
        if args.prompt_file:
            parser.error("--prompt-file belongs to --worker mode; --payload builds the prompt")
        return _run_payload(args, cfg)
    if not args.prompt_file:
        parser.error("--worker mode requires --prompt-file")
    prompt_path = Path(args.prompt_file)
    if not prompt_path.is_file():
        raise FileNotFoundError(f"prompt file not found: {prompt_path}")
    prompt = prompt_path.read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError(f"prompt file is empty: {prompt_path}")

    worker_dir = Path(args.worker)
    report = green_loop(
        worker_dir,
        prompt,
        cfg,
        model=args.model,
        max_attempts=args.max_attempts,
        on_attempt=_print_attempt,
    )

    total = f"${report.total_usd:.4f}" if report.total_usd is not None else "$unreported"
    if report.green:
        outcome = "GREEN"
    elif report.reject_reason == DRIVER_UNAVAILABLE_REASON:
        # Never printed as a reject: this run judged nothing.
        outcome = DRIVER_UNAVAILABLE_VERDICT.upper()
    else:
        outcome = REJECT_VERDICT.upper()
    print(
        f"[s2] {outcome} after "
        f"{report.attempts} attempt(s) | {total} | tokens "
        f"{report.total_tokens_in}/{report.total_tokens_out} | {report.wall_s:.1f}s"
    )
    print(f"[s2] ledger:  {sidecar(Path(report.worker), ATTEMPTS_SUFFIX)}")
    verdict_suffix = REPORT_SUFFIX if report.green else REJECT_SUFFIX
    print(f"[s2] verdict: {sidecar(Path(report.worker), verdict_suffix)}")
    return 0 if report.green else 1


if __name__ == "__main__":
    sys.exit(main())
