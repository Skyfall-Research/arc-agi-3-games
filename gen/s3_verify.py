"""S2b/S3 — the intent verifier: blind agent pass + diff + verdict (B7).

Canon: `design/architecture.md` §3 "S2b — the intent verifier" (D11, list
locked at D22). The stage exists because winnability != intent — it catches
co-adapted game/solver pairs, dead mechanics, undeclared deceptions and
contract violations that a green `make validate` cannot see.

This module owns three of the four legs' PLUMBING and all of the judgment:

* the BLIND agent pass (architecture §3 "Blindness ⊕": the agent sees ONLY the
  finished code; spec.yaml enters at the diff step, in code). Enforced here,
  not asked for: the session runs with `cwd` set to a STAGED COPY of the
  worker from which every `spec*.{yaml,yml,md}` file is excluded at copy time
  and then proven absent by a second walk, with tools AND allowedTools scoped
  to Read/Glob/Grep, and the copy's tree hash re-checked after the turn
  (`assert_unchanged`). A verifier that co-reads spec and game re-introduces
  the co-adaptation at the reviewer, which is the failure this stage exists to
  kill.
* the DIFF (pure code, both directions): declared-vs-detected terms and
  deceptions. Terms match by exact vocabulary id; deceptions match by catalog
  normalization on BOTH sides, through `s1_spec._deception_pattern` — the same
  matcher the §11 linter uses, so S1 and S2b cannot disagree about what the
  word "decoy" means. R-18 adds a THIRD term direction, `unimplemented_terms`:
  the blind pass is asked for the code construct that realizes each term it
  claims, and a DECLARED term that inventory does not positively ground is a
  broken promise rather than the silence `dead_spec_terms` records.
* the VERDICT and the report. Reject codes are frozen (see `REJECT_CODES`);
  solver-quality failures carry `route: "solver-only"` because architecture §3
  routes them to S2 as solver-only fixes while every other reject carries the
  diff.

The static passes, the eight REQUIRED rows (spec-v0.3 §2) and the solver-quality
leg live in `gen/s3_static.py`; frame capture lives in `gen/frames.py`. This
module consumes their frozen shapes and never re-implements them.

A WORKER's capture runs in a fresh interpreter (`frames.capture_worker_isolated`,
R2 hotfix #8): repeated verify rounds in one process could hand a freshly loaded
solver the game module an EARLIER round exec-loaded, because the generated
solver caches its sibling load under a path-derived name of its own choosing.
`gen/frames.py`'s header has the incident. Officials keep the in-process path —
they are single corpus files, not worker dirs.

Nothing in the prompt is paraphrased canon: every contract the auditor is held
to is quoted through the `gen/canon_docs.py` loaders, the vocabulary comes from
`gen/s0_ideas.py::load_vocab` with each term's definition quoted verbatim by
`gen/canon_docs.py::load_term_definitions`, the deception keywords are
`gen/s1_spec.py::DECEPTION_CATALOG` verbatim and each one arrives WITH the
signed lever it is shorthand for (`canon_docs.load_deception_levers`, affordance
§7). The prompt is deterministic — same worker, same frames, same bytes.

The definitions are the b002 prompt sync (contract 1): the auditor used to be
handed bare ids plus corpus counts and no prose at all, which is how it minted
findings the signed canon excludes in as many words. `gen/s2_implement.py`
quotes the SAME loader into the implementer payload, so "declared" and
"detected" are two readings of one dictionary rather than of two. Contract E-1
closed the deception half of that sync: bare KEYWORDS with no definitions made
the auditor's keyword choice unstable (five rounds of one game, four names for
one trait), so the levers now travel the same way the terms do.

CLI:
  python -m gen.s3_verify --worker out/workers/w001 --spec out/corpus/…/spec.yaml
  python -m gen.s3_verify --worker out/workers/w001 --dry-run
  python -m gen.s3_verify --official ls20 --dry-run     # the acceptance path
Exit 0 = verdict pass, 2 = verdict reject, 1 = crash.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import platform
import re
import shutil
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import yaml
from arcengine import ARCBaseGame

from .backends import get_driver
from .canon_docs import (
    load_conventions,
    load_deception_policy,
    load_forbidden_quotes,
    load_required_gates,
    load_term_definitions,
)
from .config import REPO_ROOT, load_config
from .frames import (
    FrameCapture,
    capture,
    capture_to_json,
    capture_worker_isolated,
    digest_text,
)
from .officials import discover_officials, load_official_class
from .s0_ideas import load_vocab
from .s1_spec import (
    _DECEPTION_PATTERNS,
    DECEPTION_CATALOG,
    LEVER_FOLD,
    LEVER_GROUNDING,
    canonical_lever,
    deception_lever_block,
)
from .s3_static import (
    DEFAULT_LOOKALIKE_MODE,
    DEFAULT_REFUSAL_HONEST_MODE,
    LOOKALIKE_MODES,
    REFUSAL_HONEST_MODES,
    CheckResult,
    lookalike_report,
    refusal_honest_report,
    run_required_rows,
    run_solver_quality,
    run_static_checks,
)
from .worker import IGNORED_DIRS, purge_worker_modules

SCHEMA_VERSION = "b7.1"
DEFAULT_CONFIG = "config/b001-pilot.yaml"

# --- output locations -------------------------------------------------------
# Pipeline runs write BESIDE the worker (the B3 rule: any file inside the
# worker trips its own scaffold scope check and makes green unreachable).
REPORT_SUFFIX = ".verifier-report.json"
FRAMES_SUFFIX = ".frames.json"
REPORT_NAME = "verifier-report.json"
FRAMES_NAME = "frames.json"
VERIFY_ROOT = REPO_ROOT / "out" / "verify"
# The blind copy, also a sibling: `<worker>.staged/`. Kept on disk after the
# run so a blindness claim can be re-checked by hand.
STAGED_SUFFIX = ".staged"
STAGED_MANIFEST_SUFFIX = ".staged-manifest.json"

# --- blindness --------------------------------------------------------------
# Files the staged copy must never contain. The agent pass is blind by
# construction, so this is a copy-time filter AND a post-copy assertion.
SPEC_PREFIX = "spec"
SPEC_SUFFIXES = (".yaml", ".yml", ".md")

# --- session policy ---------------------------------------------------------
# Read-only by construction. `tools` LIMITS the built-in tool set; `allowed_tools`
# only auto-approves within it — the B5 driver lesson encoded in backends.py is
# that allowedTools alone still lets a session roam with Bash, so a session that
# must not roam passes BOTH.
VERIFIER_TOOLS = ("Read", "Glob", "Grep")
# codex `session()` has no tool scoping; its read-only sandbox is the equivalent
# guarantee (backends.CODEX_SANDBOX_MODES). Never workspace-write here: a
# verifier that can edit the copy it audits proves nothing.
CODEX_READ_ONLY_SANDBOX = "read-only"

# --- claims -----------------------------------------------------------------
CLAIMS_KEYS = ("terms", "dead_code", "deceptions", "enforcement", "notes")
# The look-alike inventory (contract A3 / R-09), OPTIONAL on exactly the terms
# the report's optional keys are optional: a reply written before the inventory
# section existed still validates, and an auditor that found no family omits the
# key rather than shipping an empty list nobody asked for. A sixth key that is
# NOT this one is still a malformed reply — the closed key set is what keeps a
# hallucinated section from riding into the record.
#
# R-18's site inventory (contract B3) is the second, on exactly the same terms:
# a reply written before the section existed still validates, an auditor that
# grounded nothing omits the key, and the closed key set still discards a
# seventh key nobody asked for.
OPTIONAL_CLAIMS_KEYS = ("lookalikes", "term_sites")
# section -> the key naming WHAT is claimed there.
CLAIM_SUBJECT = {
    "terms": "term",
    "dead_code": "what",
    "deceptions": "lever",
    "enforcement": "claim",
}
# The inventory's subject, kept out of `CLAIM_SUBJECT` because that mapping is
# iterated as "the four required sections" by the validator below.
LOOKALIKE_CLAIM_SUBJECT = "family"
_JSON_FENCE_OPEN_RE = re.compile(r"^\s*```+\s*json\s*$", re.IGNORECASE)
_FENCE_CLOSE_RE = re.compile(r"^\s*```+\s*$")
# The canon's own spelling of a vocabulary term id (canon_docs._TERM_RE).
_TERM_RE = re.compile(r"^[a-z_]+\.[a-z_]+$")

# --- diff -------------------------------------------------------------------
DIFF_KEYS = (
    "terms_declared",
    "terms_detected_reachable",
    "dead_spec_terms",
    "undeclared_terms",
    "unreachable_declared_mechanics",
    "deceptions_declared",
    "deceptions_detected",
    "undeclared_deceptions",
    "declared_deceptions_undetected",
)

# --- verdict ----------------------------------------------------------------
REJECT_FORBIDDEN_STATIC = "forbidden-static"
REJECT_UNDECLARED_DECEPTION = "undeclared-deception"
REJECT_DEAD_SPEC_TERM = "dead-spec-term"
REJECT_UNDECLARED_TERM = "undeclared-term"
REJECT_UNREACHABLE_DECLARED = "unreachable-declared-mechanic"
REJECT_SOLVER_QUALITY = "solver-quality"
REJECT_CODES = (
    REJECT_FORBIDDEN_STATIC,
    REJECT_UNDECLARED_DECEPTION,
    REJECT_DEAD_SPEC_TERM,
    REJECT_UNDECLARED_TERM,
    REJECT_UNREACHABLE_DECLARED,
    REJECT_SOLVER_QUALITY,
)
# architecture §3: "Solver-quality failures route to S2 as solver-only fixes."
SOLVER_ONLY_ROUTE = "solver-only"

# --- R-18: the term-implementation witness (contract B3) --------------------
#
# mosaic-marble-bounce-to-match declares `gate.plate`, its spec INTRODUCES it at
# a level, and the bestiary found no implementation at all — "there is no gate,
# plate, toggle or openable cell anywhere in the 290 lines" — and the game
# passed a one-round blind audit clean (mosaic bestiary §3; findings B4 teaching
# row; J-1 escalation 2, lead-verified).
#
# The machinery that should have caught it is `dead_spec_terms`, and the reason
# it did not is what this contract answers: `dead_spec_terms` is a SILENCE. A
# declared term lands there when the auditor's `terms` list happens not to
# mention it, which is indistinguishable from an auditor that simply did not
# enumerate that far. R-18 replaces the silence with a WITNESS: the blind pass
# is asked, per term, for the code construct that REALIZES it, and a declared
# term the inventory does not positively ground is `unimplemented`.
#
# THE FALSE-POSITIVE TRAP, pinned, and the reason the witness is defined
# BEHAVIOURALLY rather than lexically: conduit-watch's `state.checkpoint` is
# realized as the LOCKED set and the word "checkpoint" appears nowhere in its
# 825 lines. A grep-shaped witness reports conduit as unimplemented and mosaic
# as fine — exactly backwards. So `TERM_SITES_HEADER` below tells the auditor,
# in the auditor's own terms, that a construct realizes a term by what it DOES,
# that a name matching the term is not a site, and that a name not matching it
# is not an absence; and the finding then rides the C-3 corroboration bar, so a
# single round's failure to ground a term records and never decides.
#
# NO NEW REJECT CODE, deliberately. `REJECT_CODES` above is frozen at six and
# this finding does not join them: R-18's own change text escalates a zero-site
# term "to a gate finding", and the A3 ruling in this file — a heuristic
# detector must not get a reject path that bypasses the corroboration bar —
# binds here for the same reason. The code below names the GATE CHECK the
# finding feeds, which is why it is spelled like a check id and not like a
# reject code.
TERM_SITES_KEY = "term_sites"
TERM_WITNESS_CODE = "term-witness"
UNIMPLEMENTED_KEY = "unimplemented_terms"

# --- exemptions (b002 ruling, operator 2026-09-24) ------------------------------
# `verifier.exempt_terms` names terms whose term findings are RECORDED and never
# reject. It exists because of one measured failure: under the mandated
# per-level budget headroom, `budget.cap` fired in BOTH audit directions on the
# SAME game in consecutive rounds — undeclared-reachable first and, once the
# respec declared it, declared-unreachable. A mandated-generous cap is
# reachable only by deliberate exhaustion, so a blind auditor can read it either
# way without either reading being wrong, and each reading respecs the game to
# the cap. A finding that flips on its own is evidence about the mandate, not
# about the game, and must not decide a verdict.
#
# The precedent is in this file: `declared_deceptions_undetected` is computed,
# reported and deliberately never read by `decide_verdict`, because a possible
# verifier false negative is a warning for the S5 human review rather than a
# reject. This knob gives the same treatment to a named term, and records what
# it suppressed so nothing the audit found is lost.
#
# R4 REVISIT: drop the knob if the headroom mandate changes, or if a measured
# `budget.cap` finding is ever shown to be actionable.
EXEMPTED_KEY = "exempted"
# The diff lists an exempt term can be suppressed out of, each with the code it
# would have produced there. Deceptions are NOT exemptable: the knob is a term
# knob.
#
# The first three carry a `REJECT_CODES` member — the verdict they would have
# decided. The FOURTH (R-18, contract B3) carries a GATE CHECK id instead,
# because `unimplemented_terms` never rejects in this stage; it reddens
# `gate.term-witness`. It belongs in this table anyway, and the reason is the
# knob's own: `verifier.exempt_terms` names terms whose findings are recorded
# and never DECISIVE, and a term exempted from deciding a verdict that could
# still stop the same game one stage later would make the exemption a
# half-measure nobody could read off the config.
EXEMPTABLE_FINDINGS = (
    ("dead_spec_terms", REJECT_DEAD_SPEC_TERM),
    ("undeclared_terms", REJECT_UNDECLARED_TERM),
    ("unreachable_declared_mechanics", REJECT_UNREACHABLE_DECLARED),
    (UNIMPLEMENTED_KEY, TERM_WITNESS_CODE),
)
EXEMPTED_ENTRY_KEYS = ("term", "would_have_been")

# --- lever corroboration (b002 ruling, operator 2026-09-24) ---------------------
# `verifier.lever_corroboration` raises the bar for ONE reject class: an
# `undeclared-deception` finding rejects only once a SECOND, independent blind
# session has named the same lever. It exists because of a measured instability
# in the instrument. Across two games' audit rounds the undeclared-lever
# findings ROTATED — a keyword almost never repeated in consecutive audits of
# near-identical code — and one meta term was reported dead in two consecutive
# rounds and reachable in the third. A human then played a game those findings
# kept rejecting and passed it, so the game was not what they said it was.
#
# The inference is about the auditor, not the game: a REAL deception is CODE,
# and code a blind pass can see once it can see every round. A finding that
# does not survive a second independent session is evidence about this pass's
# sampling, and evidence that unstable must not decide a verdict — the same
# reasoning `exempt_terms` above applies to one named term, one class over.
#
# Nothing is dropped. A first sighting moves into the diff's
# `uncorroborated_levers` record, and EVERY round's detections are appended to
# the per-slot sidecar (written whether the knob is on or off), so a later
# round has a real history to corroborate against.
#
# R4 REVISIT: this is R4's per-class reject policy pulled forward as a
# per-batch knob. Default OFF = canon behavior, byte for byte.
LEVER_CORROBORATION_KEY = "lever_corroboration"
# WINDOWED corroboration (b003 C-2, measured on b002 slot 3). "A SECOND,
# independent session" above is read as ANY prior recorded round, so as a slot's
# history accrues over eight audit rounds nearly every keyword has been named
# somewhere before and the bar saturates back toward reject-on-sight — the
# instability this knob exists to absorb comes back, silently, the longer a slot
# runs. The rotation IS the discriminator: a real deception is code a blind pass
# sees every round, so it is named in CONSECUTIVE rounds, while a phantom is
# named once and rotates out. `verifier.lever_corroboration_window: N` narrows
# the corroborating set to the LAST N recorded rounds; absent or null keeps
# today's union over every prior round, byte for byte.
LEVER_WINDOW_KEY = "lever_corroboration_window"
# The per-slot record, a sibling of the worker like every other stage artifact
# (`<worker>.lever-history.json`): a file inside the worker would trip its own
# scaffold scope check (the B3 rule REPORT_SUFFIX above records).
LEVER_HISTORY_SUFFIX = ".lever-history.json"
HISTORY_TS_KEY = "ts"
HISTORY_DETECTED_KEY = "detected"
UNCORROBORATED_KEY = "uncorroborated_levers"
UNCORROBORATED_ENTRY_KEYS = ("lever", "note")
# Which window decided this round, recorded in the report beside `mode`: `N`, or
# null for the unwindowed any-prior-round union. The report carries no record of
# the corroboration MODE today, so this is also the first place a reader can see
# that the pass ran at all — which is why the key appears only when it did. A
# run without the ruling knob writes exactly the report it wrote before this
# existed (`OPTIONAL_REPORT_KEYS` below).
LEVER_WINDOW_REPORT_KEY = "lever_window"
FIRST_SIGHTING_NOTE = "first sighting — no earlier recorded round detected this lever"

# --- deception leniency (contract L-1, operator ruling 2026-10-01) ------------
# `verifier.deception_action` decides WHERE a surviving undeclared-deception
# finding lands. `reject` (the default, and byte for byte the stage as it
# shipped) appends it to `reject_reasons`, where it decides the verdict;
# `record` puts the SAME row — same lever, same detail — in the report's
# `deception_advisories` instead, where it is evidence for the human review and
# for the record, and never a verdict.
#
# THE RULING (docs/v2/DECISIONS.md, 2026-10-01, verbatim): "Also why are
# deceptions that importatn that we're rejecting games based on that? We need to
# be lenient please." It deliberately supersedes the 2026-09-29 "verifier
# judgment never softened" stance for THIS one finding class and for nothing
# else: every other reject code, the lint-side `tier-deceptions` rule on
# DECLARED levers, the look-alike detector and the gate are all untouched.
#
# THE LIVE EXHIBIT, measured on g20261001-1 (both slots). The blind audit names
# levers in free text, and a t1 game's signed tier table allows ZERO declared
# levers — so a lever sighted at t1 can neither be DECLARED (the amended spec
# lint-kills, which is why reconcile-early silently fell through twice) nor
# repaired game-side (the respec writer edits the spec, not the game). The
# finding is un-actionable BY CONSTRUCTION, and an un-actionable finding that
# rejects rides the ladder to `verifier.round_cap` and parks a game nobody ever
# said was broken: seamlock sighted 3 levers; key-strip-rover sighted camouflage
# in rounds 1 and 3 and not in 2 — the rotation `lever_corroboration` above
# already documents, here deciding a game's fate anyway.
#
# THE CORROBORATION BAR IS UNTOUCHED AND STILL RUNS FIRST. This knob is about
# what a SURVIVING finding may decide, not about what is worth recording: a
# first sighting still demotes into `uncorroborated_levers`, and what reaches
# the advisories is what the instrument stood behind.
DECEPTION_ACTION_KEY = "deception_action"
DECEPTION_ACTION_REJECT = "reject"
DECEPTION_ACTION_RECORD = "record"
DECEPTION_ACTIONS = (DECEPTION_ACTION_REJECT, DECEPTION_ACTION_RECORD)
# The report list `record` moves those rows into. Written in BOTH modes (empty
# under `reject`), which is the one place it departs from the optional records
# above: a reader asking "what did this audit say about deception" must not have
# to know which knob the batch ran to tell an empty answer from an absent one.
# It is still an OPTIONAL key in `validate_report`, because every b7.1 report
# written before this contract carries no such key and must keep validating.
ADVISORIES_KEY = "deception_advisories"

# --- term corroboration (contract C-3, b003; measured on b003 slot 1) --------
# The lever ruling above, one class over: the three TERM findings —
# `dead-spec-term`, `undeclared-term`, `unreachable-declared-mechanic` — reject
# on ONE blind round's say-so, and they rotate exactly the way the lever
# findings do.
#
# The measurement is b003 slot 1's four audit rounds. Round 2 reported
# `info.legend` and `move.grid` reachable-but-undeclared; the respec declared
# them; round 3 audited BYTE-IDENTICAL code (that respec was declaration-only —
# "implementation revalidated, sessions skipped") and swore both were DEAD.
# Same bytes, opposite finding, consecutive rounds. Meanwhile every ×2
# escalation unions the rotated terms into the spec, so the slot was authored at
# 5 terms and escalated to 10 while the game itself never grew — the spec
# drifting toward whatever the last audit happened to name.
#
# `verifier.term_corroboration` applies the same bar the levers got: a term
# finding rejects only once a recorded round in scope reported the SAME term in
# the SAME direction. DIRECTION IS PART OF THE FINDING — a term called dead in
# one round and undeclared in the next corroborates neither, because those two
# readings contradict each other and a contradiction is evidence about the pass,
# not about the game. `verifier.term_corroboration_window: N` narrows the
# corroborating set to the last N recorded rounds, for the reason C-2 windowed
# the levers: over a long slot the any-prior-round union saturates and the bar
# quietly returns to reject-on-sight.
#
# Nothing is dropped: a first sighting moves into the diff's
# `uncorroborated_terms` record, S2's findings feed renders it as an advisory,
# and EVERY round's three direction lists are appended to the per-slot sidecar
# (written whether the knob is on or off) so a later round has real rounds to
# corroborate against.
#
# R4 REVISIT: like the lever knob, this is R4's per-class reject policy pulled
# forward as a per-batch knob. Default OFF = canon behavior, byte for byte.
TERM_CORROBORATION_KEY = "term_corroboration"
TERM_WINDOW_KEY = "term_corroboration_window"
# The per-slot record, a sibling of the worker beside the lever one
# (`<worker>.term-history.json`). Separate FILE, separate shape: the lever
# sidecar's `{ts, detected}` entries are pinned by C-2 and are not touched here.
TERM_HISTORY_SUFFIX = ".term-history.json"
HISTORY_DEAD_KEY = "dead"
HISTORY_UNDECLARED_KEY = "undeclared"
HISTORY_UNREACHABLE_KEY = "unreachable"
TERM_HISTORY_KEYS = (HISTORY_DEAD_KEY, HISTORY_UNDECLARED_KEY, HISTORY_UNREACHABLE_KEY)
# R-18's direction (contract B3) JOINS this sidecar rather than opening a second
# one: it is a per-term finding that rotates exactly the way the other three do,
# so it wants the same bar, the same window and the same file.
#
# It is OPTIONAL in a recorded entry, and that is the one place its handling
# differs from C-3's three. Those three are written by every round, so an entry
# missing one is a record this stage cannot read. This one is written only when
# the round's reply carried a site inventory at all (`term_sites` is an optional
# claims key), so an entry without it says "this round did not measure sites" —
# and treating that as an empty direction is the safe reading in the only
# direction that matters: a round that measured nothing can never CORROBORATE a
# later round's finding. It also keeps every term history already on disk
# readable, which entries written before this contract are.
HISTORY_UNIMPLEMENTED_KEY = "unimplemented"
TERM_HISTORY_READ_KEYS = (*TERM_HISTORY_KEYS, HISTORY_UNIMPLEMENTED_KEY)
# direction -> (the diff list the finding lives in, the code it would have
# produced). The direction names its list here; the CODE is looked up in
# `EXEMPTABLE_FINDINGS`, which already owns that pairing, so the exemption table
# and this one can never disagree about which list carries which code (and a
# list dropped there is a loud KeyError at import, not a silent mismatch).
TERM_DIRECTIONS = tuple(
    (direction, key, dict(EXEMPTABLE_FINDINGS)[key])
    for direction, key in (
        (HISTORY_DEAD_KEY, "dead_spec_terms"),
        (HISTORY_UNDECLARED_KEY, "undeclared_terms"),
        (HISTORY_UNREACHABLE_KEY, "unreachable_declared_mechanics"),
        (HISTORY_UNIMPLEMENTED_KEY, UNIMPLEMENTED_KEY),
    )
)
UNCORROBORATED_TERMS_KEY = "uncorroborated_terms"
# `code`, not `would_have_been`: unlike an exemption, which suppresses a finding
# for good, this record is a STANDING finding — the same sighting next round
# rejects — so the entry names the code that is waiting rather than one that
# will never fire.
UNCORROBORATED_TERM_ENTRY_KEYS = ("term", "code", "note")
TERM_WINDOW_REPORT_KEY = "term_window"
TERM_FIRST_SIGHTING_NOTE = (
    "first sighting — no earlier recorded round reported this term this way"
)

# --- term attribution disputes (contract Q-1; measured 2026-10-06) ----------
# E-1 closed the LEVER vocabulary churn — bare catalog keywords with no
# definitions made the auditor's keyword CHOICE unstable, five rounds of one game
# producing four names for one trait — and the TERM side has the same disease one
# class over. `undeclared_terms` is a bare set difference (`reachable -
# declared`), so an auditor that grounds ONE observed behaviour under a name the
# spec did not pick mints a reject no spec amendment can durably answer: the
# respec declares the audit's name, the next blind round reads the same code
# under a neighbour's name again, and the slot rides the ladder to the cap.
#
# THE MEASURED EXHIBIT is b005r2-auto's two-keys-one-echo, re-parked 2026-10-06
# on `undeclared-term ×2`. The audit reported `info.recall` reachable in a game
# that declares `agent.echo`, and the two SITES it wrote name one construct —
# the `pend` FIFO of pending presses: one queue, two signed vocabulary names,
# neither reading wrong under its own printed definition. b002's ±manip.terraform
# churn is the same signature.
#
# THE RULE. Such a finding is an ATTRIBUTION DISPUTE rather than a defect, on two
# conditions, and both are the auditor's own work rather than this code's guess:
# the auditor GROUNDED both names on one piece of observed evidence, and it has
# not said WHY the behaviour is X and not the declared neighbour Y.
# `DISTINGUISHES_KEY` below is the second half — the prompt asks for the
# definitional clause that separates them, and an auditor that cites one has
# answered the question, so its finding stands and rejects as it does today.
TERM_DISPUTES_KEY = "term_disputes"
# THE COMPARATOR, designed from the real claim shapes and MEASURED on the exhibit
# before it was written. Two surfaces ground a claim and the pairing reads both:
#
#   * CITATIONS — the `{path, line}` pairs and the `frame_refs` labels every
#     claim must carry (`_check_evidence`). One line cited by two terms is the
#     sharpest statement available that one piece of code was read twice.
#   * CONSTRUCTS — the backtick-quoted code spans inside a `term_sites` entry's
#     `site` prose. `TERM_SITES_HEADER` asks the auditor for "the field, the
#     branch, the predicate, the loop, the data structure that DOES it", and an
#     auditor answers by quoting the construct in its own spelling; two sites
#     quoting one construct are two names for one behaviour.
#
# MEASURED, and the SECOND surface is the one that carries the exhibit:
# `info.recall` cites game.py 479/539/848 and `agent.echo` cites 579/581/36 —
# ZERO shared citations — while both sites quote `pend`. A citation-only
# comparator finds nothing in the game this contract was written for.
#
# NARROW ON PURPOSE, in both directions. The spans are read only from `site`,
# never from an evidence `note`: the site field is the prompt-synced answer to
# "what construct realizes this term" and a note is free annotation. And a span
# must be substantial enough to name a construct (`_MIN_CONSTRUCT_CHARS`, and at
# least one letter), because `0` or `[]` quoted by two unrelated terms is not a
# shared mechanic. The asymmetry that governs every one of these calls: a FALSE
# dispute silences a real finding, while a MISSED dispute only costs a reject the
# ladder already knows how to carry — so where the evidence is thin this
# comparator declines to pair.
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_MIN_CONSTRUCT_CHARS = 3
# `code`, not `would_have_been`: the C-3 note above gives the reason and it binds
# here identically. This record is written in BOTH knob modes, so under the
# default the named finding IS rejecting and a `would_have_been` would be a lie
# in exactly the reports a human reads to decide whether to arm the knob.
#
# `disputed_with` and `shared` are the two facts a reader needs that `exempted`
# has no room for: WHICH declared term the behaviour was also called, and WHAT
# grounded the pairing — so the record can be argued with rather than believed.
TERM_DISPUTE_ENTRY_KEYS = ("term", "code", "disputed_with", "shared")
# The two halves of ONE misattribution. `undeclared-term` is X's finding; the
# `dead-spec-term` row is Y's, and it rides the same dispute because a declared
# term the auditor never saw under its own name is the mirror image of the same
# mistake — counting both would charge a game twice for one naming call.
TERM_DISPUTE_CODES = (REJECT_UNDECLARED_TERM, REJECT_DEAD_SPEC_TERM)
# THE AUDITOR'S OWN BREAK (Q-1 §2). An `undeclared-term` entry may carry
# `{term, clause}`: the DECLARED term the behaviour is NOT, plus the definitional
# clause that separates the two. Well-formed, it makes the finding undisputed
# whatever the evidence overlap — the dispute exists because nobody said why, and
# this is somebody saying why.
#
# OPTIONAL and ADDITIVE, on exactly the terms `lookalikes` and `term_sites` are:
# a reply written before the prompt asked for it still validates, and an auditor
# with nothing to distinguish omits the key.
DISTINGUISHES_KEY = "distinguishes"
DISTINGUISHES_ENTRY_KEYS = ("term", "clause")
# `verifier.term_dispute_action` — the L-1 knob pattern exactly, one finding
# class over. `reject` (the default, and byte for byte the stage as it shipped)
# lets a DISPUTED term finding decide the verdict; `record` moves the same row
# into `term_disputes`, where it is evidence for the human review and never a
# verdict. An UNDISPUTED finding rejects under both values — this knob changes
# nothing about what the audit found, only about what a finding the auditor
# itself double-named may decide.
TERM_DISPUTE_ACTION_KEY = "term_dispute_action"
TERM_DISPUTE_ACTION_REJECT = "reject"
TERM_DISPUTE_ACTION_RECORD = "record"
TERM_DISPUTE_ACTIONS = (TERM_DISPUTE_ACTION_REJECT, TERM_DISPUTE_ACTION_RECORD)

# --- confirmation audits (contract C-4a, b003; operator ruling 2026-09-25) ----
# Both corroboration passes above demote a FIRST sighting to a recording and let
# the round pass — and a PASS ends the verify loop, so no second blind session
# ever looks at the recording. Operator ruling, 2026-09-25: "We need at least 2 audits with
# the same issue to take them seriously but if we just run audit once then we'll
# never have 2 audits agreeing." Both b003 r2 slots passed round 1 carrying
# recordings nothing was ever going to corroborate.
#
# `verifier.confirm_pass` closes that loop at the only seam where it can be
# closed — the runner that owns the round. A pass whose diff carries ANY
# uncorroborated recording buys ONE confirmation round: a second blind session
# over the SAME capture, judged by the existing corroboration machinery (round
# 1's sidecar entries are already appended, so a re-sighting now corroborates and
# a silence leaves the pass standing). A pass with ZERO findings stands alone — a
# second round provably cannot change it, because there is no claim to
# corroborate and its own new findings would be first sightings demoted exactly
# the way round 1's would have been. Exactly one confirmation, never a third.
#
# R4 REVISIT: like the two corroboration knobs, this is a per-batch bar raise.
# Default OFF = canon behavior, byte for byte — one blind session per round.
VERIFY_CONFIRM_KEY = "confirm_pass"
# Round 1's `agent.session_id`, recorded on the CONFIRMATION round's report so
# the run log names both blind sessions. Round 1's full report is deliberately
# not kept (its findings live in the two sidecars, which is this design's
# premise), so this key is the only trace on disk that the pass was audited
# twice — and, like the window keys, it appears only when it was earned.
CONFIRMED_SESSION_KEY = "confirmed_session"

# --- R-09: deception DECLARED, verified both directions (contract A3) --------
#
# Spec §10 makes "deception is always a DECLARED property, never an accident"
# THIS stage's job, and the comparative audit (finding B4) measured it failing
# in both directions on our own shipped games — present-but-undeclared
# (pump-phase's three identical flat solids, pump-flow's four-kinds-one-
# silhouette, conduit's `deceptions: []`) and declared-but-absent (pump-flow's
# palette-overload entry naming an index the look-alike is not drawn in).
#
# Two surfaces answer it, and they are deliberately independent:
#
#   * the PROMPT — `LOOKALIKE_HEADER` asks the blind auditor for an explicit
#     inventory of the look-alike families it finds, which the optional
#     `lookalikes` claims section carries back;
#   * the CODE — `s3_static.check_lookalike_declared`, which measures the same
#     question off the engine and the AST and diffs it against the spec's own
#     `knobs.deceptions`.
#
# Both land in ONE optional report block, `lookalikes`, carrying the two
# directions as `undeclared_found` / `declared_ungrounded`. OPTIONAL is the
# whole point: every b7-era report reader is unchanged, every report written
# before this contract still validates, and nothing here is a schema bump.
#
# THE VERIFIER'S REJECT LOGIC GAINS NOTHING FROM THIS IN `record`, and that is
# a ruling, not an oversight: rejects in this stage are already governed by the
# corroboration machinery (a finding rejects only once a second independent
# blind session names it), and a heuristic detector must not get a reject path
# that bypasses that bar. The findings feed the RECORD and the S5 human review.
# `verifier.lookalike_declared: fail` is the armed gate, opted into per batch,
# and only there does the detector's result join `checks` and reach
# `decide_verdict` as an ordinary failing `static` check.
LOOKALIKES_KEY = "lookalikes"
LOOKALIKE_UNDECLARED_KEY = "undeclared_found"
LOOKALIKE_UNGROUNDED_KEY = "declared_ungrounded"
LOOKALIKES_BLOCK_KEYS = (LOOKALIKE_UNDECLARED_KEY, LOOKALIKE_UNGROUNDED_KEY)
# `verifier.lookalike_declared` — off | record (the default) | fail.
LOOKALIKE_KNOB = "lookalike_declared"

# --- R-08: §6's never-signal-and-charge rule (contract B3) ------------------
#
# `gen/s3_static.refusal_honest_report` is the detector; this is the knob that
# arms it and the seam that runs it. Both live beside the look-alike pair above
# because the two are the same shape exactly: a GENERATED-ONLY source check with
# no engine cost, run at report assembly — after the blind session has closed,
# so the auditor never sees a byte of it — and born in `record`, because a new
# rejection earns its place on measured data.
#
# `verifier.refusal_honest` — off | record (the default) | fail. Unlike the
# look-alike detector this one reads NO spec: §6:158's "charge silently or
# signal freely, never both" is a property of the code, and whether the SPEC
# promised a visible refusal is the separate question `gate.refusal-persistence`
# asks of the settled frames.
REFUSAL_HONEST_KNOB = "refusal_honest"

CHECK_LEGS = ("static", "required", "solver")
CHECK_STATUSES = ("pass", "fail", "premise-not-met", "deferred", "skipped")
STATIC_LEGS = ("static", "required")
REQUIRED_ROW_RE = re.compile(r"^required\.row([1-8])$")
REQUIRED_ROW_COUNT = 8

# --- report -----------------------------------------------------------------
REPORT_KEYS = (
    "schema_version",
    "game_id",
    "worker",
    "mode",
    "canon",
    "frames",
    "checks",
    "required_rows",
    "agent",
    "diff",
    "verdict",
    "reject_reasons",
    "versions",
)
# Present only when the run that wrote the report opted into the corroboration
# ruling — the `exempted` / `uncorroborated_levers` pattern one level up, and for
# the same reason: a data addition, not a schema-version bump, so every b7.1
# report written before the knob existed still validates unchanged.
#
# The two WINDOW keys carry the same value shape (a positive int, or null for the
# unwindowed union) and are validated in one loop; `confirmed_session` is the
# first optional key that is NOT a window, so it gets its own branch — exactly
# what the note in `validate_report` asked a later key to do.
#
# `term_sites` (R-18, contract B3) is the fourth non-window optional key and the
# third to get its own branch in `validate_report`. It is the blind pass's site
# inventory lifted out of `agent.claims` and into the report's own surface, for
# the reason A3 lifted the look-alike answer into `lookalikes`: the inventory is
# what `gate.term-witness` and the S5 review read, and a machine-read record
# does not live inside a free-form claims blob. It appears only when the reply
# carried one.
#
# `deception_advisories` (contract L-1) is the fifth non-window optional key and
# the fourth with its own branch. It is OPTIONAL for a different reason from the
# four above — `assemble_report` writes it on EVERY run, in both modes — and the
# reason is the same promise those four keep: a b7.1 report written before this
# contract carries no such key, and `validate_report` reads reports off disk
# that were written months ago. Required here would retro-invalidate every one
# of them.
#
# `term_disputes` (contract Q-1) is the sixth non-window optional key and the
# fifth with its own branch, and it is optional for the `deception_advisories`
# reason rather than the `confirmed_session` one: it is written whenever it is
# COMPUTABLE — a full run with a diff and a claims block, in both knob modes, `[]`
# when nothing paired — because a reader asking "did this audit double-name a
# behaviour" must not have to know which knob the batch ran to tell an empty
# answer from an absent one. Every report on disk predates it and must keep
# validating, which is what makes it optional here and nowhere else.
OPTIONAL_WINDOW_KEYS = (LEVER_WINDOW_REPORT_KEY, TERM_WINDOW_REPORT_KEY)
OPTIONAL_REPORT_KEYS = (
    *OPTIONAL_WINDOW_KEYS,
    CONFIRMED_SESSION_KEY,
    LOOKALIKES_KEY,
    TERM_SITES_KEY,
    ADVISORIES_KEY,
    TERM_DISPUTES_KEY,
)
AGENT_KEYS = (
    "session_id",
    "model",
    "usd",
    "tokens_in",
    "tokens_out",
    "wall_s",
    "staged_copy_verified",
    "claims",
)
MODES = ("full", "dry-run")
VERDICTS = ("pass", "reject")
FRAME_SOURCES = ("solver", "probe")


# --- fail-loud type gates ---------------------------------------------------
# Every input this module validates is a DOCUMENT — a model's reply, a parsed
# spec, a report read back off disk — so a wrong type there is bad data, not a
# caller's type error, and the package's contract for bad data is ValueError
# (`s1_spec.extract_spec_yaml` sets the precedent). These three gates keep that
# promise in one place and name the offending field in every message.


def _as_mapping(value: object, where: str) -> Mapping:
    if isinstance(value, Mapping):
        return value
    raise ValueError(f"{where} must be a mapping, got {type(value).__name__}")


def _as_list(value: object, where: str) -> list:
    if isinstance(value, list):
        return value
    raise ValueError(f"{where} must be a list, got {type(value).__name__}")


def _as_text(value: object, where: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"{where} must be a non-empty string, got {value!r}")


def _require(value: object, types: type | tuple[type, ...], where: str) -> None:
    """Type gate for a field that may legitimately be empty (unlike `_as_text`).

    A bool is never accepted for an int/float field: it IS an int in Python, and
    a `win: true` sitting in a count field must fail loudly rather than count 1.
    """
    wants_bool = types is bool or (isinstance(types, tuple) and bool in types)
    if not isinstance(value, types) or (isinstance(value, bool) and not wants_bool):
        names = types.__name__ if isinstance(types, type) else "/".join(t.__name__ for t in types)
        raise ValueError(f"{where} must be {names}, got {value!r}")


# --- staging: the blind copy ------------------------------------------------


def _is_spec_file(name: str) -> bool:
    """`spec*.{yaml,yml,md}`, case-insensitively — what blindness excludes."""
    low = name.lower()
    return low.startswith(SPEC_PREFIX) and low.endswith(SPEC_SUFFIXES)


def _stage_ignore(_dirpath: str, names: list[str]) -> set[str]:
    """`shutil.copytree` filter: caches out, spec documents out.

    Not `shutil.ignore_patterns`: fnmatch is case-SENSITIVE on posix, so a
    `SPEC.md` would slip the pattern and then trip the post-copy assertion,
    turning a legal worker into an unstageable one.
    """
    return {name for name in names if name in IGNORED_DIRS or _is_spec_file(name)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_files(root: Path) -> dict[str, str]:
    """rel-posix-path -> sha256, skipping the cache dirs nothing reads."""
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        files[rel.as_posix()] = _sha256(path)
    return files


def _tree_hash(files: Mapping[str, str]) -> str:
    """One hash over (path, content-hash) pairs — order-independent, total."""
    digest = hashlib.sha256()
    for rel in sorted(files):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[rel].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _staged_manifest_path(dest: Path) -> Path:
    return dest.with_name(dest.name + STAGED_MANIFEST_SUFFIX)


def stage_worker_copy(worker_dir: Path, dest: Path) -> str:
    """Copy `worker_dir` to `dest` minus every spec document; return a tree hash.

    THE blindness primitive (architecture §3 "Blindness ⊕"). The agent session
    runs in `dest`, never in the worker itself, so the audit cannot read the
    spec and cannot edit the code it is auditing.

    Three fail-loud guarantees:
      * spec documents are filtered at copy time AND proven absent afterwards
        by an independent walk — "excluded" is a checked fact, not a flag;
      * a symlink anywhere in the source refuses the stage, because a link can
        smuggle content past a name-based filter;
      * the returned hash covers every staged file, so `assert_unchanged` can
        prove the session left the copy alone.

    A pre-existing `dest` is REPLACED: a stale copy would make the hash a lie.
    """
    worker_dir = Path(worker_dir).resolve()
    dest = Path(dest).resolve()
    if not worker_dir.is_dir():
        raise FileNotFoundError(f"worker dir not found: {worker_dir}")
    if dest == worker_dir or worker_dir in dest.parents:
        raise ValueError(
            f"staged copy {dest} would live inside the worker {worker_dir} — the blind "
            f"copy is always a sibling, never a child"
        )
    links: list[str] = []
    for path in sorted(worker_dir.rglob("*")):
        rel = path.relative_to(worker_dir)
        if path.is_symlink() and not any(part in IGNORED_DIRS for part in rel.parts):
            links.append(rel.as_posix())
    if links:
        raise ValueError(
            f"{worker_dir}: refusing to stage a tree containing symlink(s) {links} — a link "
            f"can carry spec content past the name filter, so blindness cannot be proven"
        )

    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(worker_dir, dest, ignore=_stage_ignore)

    files = _tree_files(dest)
    leaked = sorted(rel for rel in files if _is_spec_file(Path(rel).name))
    if leaked:
        raise RuntimeError(
            f"blindness violated: spec document(s) {leaked} landed in the staged copy {dest}"
        )
    if not files:
        raise ValueError(f"{worker_dir}: staged copy is empty — nothing to audit")
    tree_hash = _tree_hash(files)
    _staged_manifest_path(dest).write_text(
        json.dumps({"tree_hash": tree_hash, "files": files}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return tree_hash


def assert_unchanged(dest: Path, tree_hash: str) -> None:
    """Raise RuntimeError unless `dest` still hashes to `tree_hash`.

    Run after the agent turn: the session is scoped to read-only tools, and
    this is the proof rather than the assumption. The drift detail comes from
    the sibling manifest written by `stage_worker_copy` when it is readable,
    and degrades to the two hashes when it is not.
    """
    dest = Path(dest)
    if not dest.is_dir():
        raise RuntimeError(f"staged copy vanished: {dest}")
    files = _tree_files(dest)
    actual = _tree_hash(files)
    if actual == tree_hash:
        return

    detail = ""
    manifest_path = _staged_manifest_path(dest)
    if manifest_path.is_file():
        try:
            before = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
        except (json.JSONDecodeError, KeyError, TypeError):
            before = None
        if isinstance(before, dict):
            added = sorted(set(files) - set(before))
            removed = sorted(set(before) - set(files))
            modified = sorted(
                rel for rel in set(files) & set(before) if files[rel] != before[rel]
            )
            detail = f" added={added} removed={removed} modified={modified}"
    raise RuntimeError(
        f"staged copy {dest} changed during the verifier session: expected tree hash "
        f"{tree_hash}, found {actual}.{detail}"
    )


# --- the blind prompt -------------------------------------------------------

MISSION = """\
## Mission

You are an INDEPENDENT auditor. Re-derive, from scratch, what the game in this
directory actually does, and report it as evidence-backed claims.

You are blind by construction: no design spec, no intent document and no author
notes exist in your working copy. Nothing tells you what this game was meant to
be, and that is deliberate — the pipeline compares your independent reading
against the intent afterwards, in code. Do not speculate about intent. Report
only what the code makes reachable in play, and cite where you read it.

Work read-only: you have Read, Glob and Grep and nothing else. Do not attempt
to run, edit or create anything."""

VOCAB_HEADER = """\
## The closed mechanics vocabulary ({count} terms)

These ids are the ONLY term names you may use, and you must write each one in
full (`move.grid`, never `grid`) — a claim outside this list is rejected by the
pipeline. They are grouped by family, and each id carries its DEFINITION quoted
verbatim from the signed canon: read the definition before you claim the term,
because the name is the shorthand and the definition is the term. An `(a/b/c)`
inside a definition is that term's recorded corpus frequency (live tufa / dead
tufa / official) where the canon records one: frequency, not permission.
Claim a term only where this game's code implements it AND play can reach it; a
mechanic that exists in the source but no action sequence can trigger is NOT
present — report it under `dead_code` instead."""

# The attribution requirement (contract Q-1), quoted into the SAME prompt
# section as the definitions by `_vocab_section` rather than standing alone.
# That placement is the point: the clause this field must cite is printed
# directly above it, so the auditor reads the requirement beside the material
# that answers it.
#
# A CONSTANT OF ITS OWN, not more text inside `VOCAB_HEADER`, for one mechanical
# reason: `VOCAB_HEADER` is a `.format()` template, and a json example's braces
# inside it would have to be written doubled — a snippet nobody can copy and a
# trap for the next editor. `TERM_SITES_HEADER` above is the same shape for the
# same reason.
#
# Prompt-synced with `term_disputes`: this section is the ONLY source of the
# `distinguishes` field, so the shape it asks for IS the shape
# `validate_claims` enforces and `_attribution_break` reads.
DISTINGUISH_HEADER = """\
SOME OF THESE TERMS ARE NEIGHBOURS, and where two of them could be read onto
one behaviour the definitions above are the only thing that settles it. So:
when you claim a term and the behaviour you are claiming it for is the SAME
behaviour another term in this list would also describe, say which one it is
not and why, in an OPTIONAL `distinguishes` field on that claim:

```json
  {"term": "info.recall", "reachable": true,
   "evidence": [{"path": "game.py", "line": 479}],
   "distinguishes": {"term": "agent.echo",
                     "clause": "the queue is never drawn, so the demand is on
                                the player's memory; agent.echo is about an
                                entity replaying the action history, which is
                                a separate property of the same queue"}}
```

`term` is the neighbouring vocabulary id you are NOT claiming; `clause` is the
part of the two printed definitions that separates them — quote it. Omit the
whole field when no neighbour is in play.

This is not bookkeeping. One construct can satisfy two definitions at once, and
when it does, the reader of your report needs to know you looked at both and
chose. A claim that names the clause it turns on is a claim that can be checked;
one that just names a term is a coin landing."""

DECEPTION_HEADER = """\
## Deception levers — the signed catalog

Report a deception ONLY under one of these {count} keywords:

{keywords}

Each one is the SHORTHAND for one of the {levers} signed levers below, quoted
verbatim from the canon with the officials it was measured on. Read the lever,
then report it under its keyword — the keyword is how the pipeline writes the
finding down, and the definition is what you are actually claiming.

{block}

The normalizer reads free prose too, and is separator- and inflection-tolerant:
"look alike", "look-alikes" and "lookalike" all fold onto `look-alike`, and
"decoys" onto `decoy`. A word it CANNOT fold onto one of the keywords above is
not quietly dropped: your whole reply fails the pipeline's mechanical
validation and is discarded, and you get exactly ONE corrective turn to send it
again. Write the keyword itself rather than a synonym of your own.

A deception here is a lever the FRAMES support: something the rendered board
invites a player to believe that the code then contradicts. Cite the frame."""

# Prompt-synced: the same question `gen/s3_static.check_lookalike_declared`
# asks the ENGINE and the AST is asked here of the auditor, in the auditor's
# own terms. The two answers are independent by construction — this session
# never sees the spec, and the detector never sees this reply — which is what
# makes agreement between them evidence rather than an echo.
#
# The adjacency paragraph is not politeness: it is the detector's own pinned
# false-positive exclusion, stated to the auditor so both surfaces draw the
# same line. conduit-watch paints one sprite per lattice cell and every tile
# touches the next; a tiling is a render consequence, not an authored
# look-alike, and an inventory full of tilings is an inventory nobody reads.
#
# The policy sentence that opens it is QUOTED, not retyped (contract E-1):
# `canon_docs.load_deception_policy` reads it out of affordance §10, where it was
# signed, so the sentence this prompt states as canon is the canon's. The slot is
# filled by REPLACE and not by `.format()` — this constant carries a literal json
# example further down, whose braces a format call would read as fields.
LOOKALIKE_POLICY_SLOT = "{policy}"
LOOKALIKE_HEADER = """\
## Look-alike inventory

{policy}

You cannot see what this game declares — that comparison happens in
code, after you — so your job is the INVENTORY: what look-alikes does this
code actually ship?

A LOOK-ALIKE FAMILY is two or more objects a player cannot tell apart from the
board alone — same footprint, same fill, often the same palette index — whose
BEHAVIOUR differs: one is clickable and the other is not, one is handled by
the step handler and the other falls through, one moves and the other is
scenery. List every family you find, name the objects in it, and say what
separates them in code.

Two exclusions, so the inventory stays worth reading:

* objects that render ADJACENT (their cells touch, so they fuse into one
  component on the board) are a tiling, not a look-alike — a lattice of
  identical tiles is one shape, not many mistakable ones;
* objects that differ by a mark a player can see on a settled frame — a rim, a
  core, a pip, a distinct hue that the frames show side by side — are
  distinguishable, and you should say so rather than list them.

Report the inventory as an OPTIONAL sixth key in the json block below:

```json
  "lookalikes": [{"family": "pump / filler / block",
                  "index": 9,
                  "differs_by": "only `pump` and `filler` are sys_click-tagged",
                  "evidence": [{"path": "game.py", "line": 625}]}]
```

`family` is required and free prose (name the objects); `index` is optional
and is the palette index they share when they share one; `differs_by` is
optional prose; the evidence rule below applies to it exactly as to every
other claim. Omit the key entirely when you found no family — an empty
inventory and an absent one read the same, and neither is a defect.

THE OTHER DIRECTION, and it matters as much. A deception this game's author
DECLARED that the code does not actually deliver is the same defect read
backwards: a look-alike the board seems to promise and the source never draws,
a tell described in one palette index and drawn in another, a refusal flash
nothing paints. You cannot see what was declared — but you can say what you
could not GROUND. So for every lever you report under `deceptions`, the
evidence you cite IS your grounding, and it must point at the code or the
frame that carries it; and where you looked for a lever this board seems to
invite and found nothing in the source to ground it, say so in `notes` in one
sentence. An ungrounded deception reported as grounded is the one error this
section cannot recover from."""

# Prompt-synced with `compute_diff`'s `unimplemented_terms`: this section is the
# ONLY source of that finding, so the definition of "site" it gives the auditor
# IS the definition the pipeline acts on. Two paragraphs earn their place.
#
# The BEHAVIOURAL definition is the pinned false-positive exclusion (R-18's own
# stated risk: "a grep-style heuristic misses implicit realizations"). The
# measured case is conduit-watch's `state.checkpoint`, realized as the LOCKED
# set with the word "checkpoint" nowhere in 825 lines; an auditor that answers
# lexically reports the honest game as hollow. The example is given generically
# rather than by name — this session must not be told what any particular game
# does — but it is the case the paragraph is written from.
#
# The "absent is a real answer" paragraph is the other half. Without it an
# auditor under a "name a site per term" instruction will always find SOMETHING
# to point at, which is exactly how mosaic-marble-bounce-to-match passed a round
# clean while implementing none of its three declared mechanics.
TERM_SITES_HEADER = """\
## Implementation sites — one per term you claim

For every term you list under `terms`, name the IMPLEMENTATION SITE: the
construct in this code whose behaviour actually realizes that term's printed
definition. Not a paraphrase of the definition — the field, the branch, the
predicate, the loop, the data structure that DOES it.

A SITE IS BEHAVIOURAL, NEVER LEXICAL, and this is the rule that matters most
here:

* a construct realizes a term by what it does, not by what it is called. A set
  the code adds to and never removes from can be a persistent-progress
  mechanic whether or not anything is named for one; a per-cell state table can
  be a gate whether or not the word "gate" appears anywhere in the file.
* the converse binds just as hard. An identifier that happens to match a
  term's name is NOT a site. If the only thing you can point at is a name,
  you have not found a site.

So: read the term's definition, ask what behaviour would satisfy it, and find
the code that produces that behaviour.

`"site": null` IS A REAL ANSWER, and reporting it honestly is the whole point
of this section. If you looked for the behaviour and this code does not produce
it anywhere, say null. Do not reach for the nearest plausible line to fill the
field — an invented site is worse than an absent one, because an absent one is
a question someone will go and answer.

Report the inventory as an OPTIONAL key in the json block below:

```json
  "term_sites": [{"term": "state.checkpoint",
                  "site": "the set of permanently-committed cells that `_commit`
                           adds to and nothing ever removes from; every later
                           revert walks back to its nearest member",
                  "evidence": [{"path": "game.py", "line": 579}]},
                 {"term": "gate.plate", "site": null}]
```

`term` is a vocabulary id from the list above; `site` is your prose, or null;
`evidence` is REQUIRED for a named site (the evidence rule below applies to it
exactly as to every other claim) and is not asked for on a null site, because
an absence has nothing to cite. Omit the whole key if you are not answering
this section."""

FORBIDDEN_HEADER = """\
## The four FORBIDDEN engine contracts

Quoted from the signed canon. If the code violates one, say so under
`enforcement` with the exact `path:line`."""

GATES_HEADER = """\
## The eight REQUIRED gates

The contract every game in this corpus must satisfy. Use it as your audit
checklist for the `enforcement` section: for each gate, is it actually wired in
this code, and where?"""

CONVENTIONS_HEADER = "## Conventions (one orientation, settled frames)"

FRAMES_HEADER = """\
## The frames this game produced

Captured from the REAL engine before you were called. Each frame is 64 rows of
64 hex digits (palette index 0-15). These are ground truth about what the game
renders: a claim contradicted by the frames is wrong, however the code reads."""

CLAIMS_CONTRACT = """\
## What to report

End your reply with EXACTLY ONE fenced ```json block — the LAST fenced block in
the reply — in this shape:

```json
{
  "terms": [{"term": "<vocabulary id>", "reachable": true,
             "evidence": [{"path": "game.py", "line": 120, "note": "…"}],
             "frame_refs": ["reset"]}],
  "dead_code": [{"what": "…", "evidence": [{"path": "game.py", "line": 12}]}],
  "deceptions": [{"lever": "<catalog keyword>",
                  "evidence": [{"path": "game.py", "line": 44}]}],
  "enforcement": [{"claim": "…", "evidence": [{"path": "game.py", "line": 8}]}],
  "notes": "…"
}
```

Rules the pipeline enforces mechanically — a reply that breaks one is discarded:

* those five top-level keys, exactly, plus the OPTIONAL `lookalikes` list the
  look-alike inventory section above describes and the OPTIONAL `term_sites`
  list the implementation-sites section describes; `notes` is free prose, the
  other four are lists (use `[]` when you found nothing). A key that is neither
  of those two is still a discarded reply.
* every `term` is a vocabulary id from the list above; `reachable` is a bool.
  Judge a term by the DEFINITION printed beside it, never by its name: the
  `*Not:*` clauses are binding, and behaviour a `*Not:*` clause excludes is not
  that term. A `terms` entry may also carry the OPTIONAL `distinguishes`
  object the vocabulary section above describes — `{"term": …, "clause": …}`,
  the neighbouring term this behaviour is NOT and the definitional clause that
  separates them.
* every `lever` is a catalog keyword from the list above.
* EVERY claim carries evidence: at least one `{"path": …, "line": …}` pair
  (both fields, line = the line you actually read) or at least one `frame_refs`
  entry naming a frame label from the digest above. A claim you cannot cite is
  a claim you should not make.

Be exhaustive about `terms` and honest about `reachable`: a term whose code
exists but cannot be reached in play belongs in the list with
`"reachable": false` AND in `dead_code`. Everything before the json block is
your working prose; keep it short."""

# One corrective turn on a malformed reply — the house idiom (`s1_spec`'s
# RETRY_REMINDER/SLUG_REMINDER, `s5_battery._turn_action`). Sent as a new turn in
# the SAME session, so the claims contract above is still in context and this
# only has to name what broke. The frame-label rule is spelled out because
# `frames.digest_text` prints the label inside the square brackets of a
# `--- frame <n> [<label>]` line and a click step's label carries the action
# after `step-<n>` (gen/frames.py:406), so a bare prefix is not a citation.
REPLY_RETRY_PROMPT = """\
YOUR LAST REPLY WAS DISCARDED — its claims block failed the pipeline's
mechanical validation, which reported:

{error}

That is a FORMAT failure, not a verdict on your audit: do not re-audit the game
and do not change what you found. Reply once more with minimal prose and the
corrected claims as EXACTLY ONE fenced ```json block — the LAST fenced block in
the reply — carrying the same five top-level keys the claims contract pins.

The rule easiest to miss: every `frame_refs` entry must copy a frame label
EXACTLY as the digest prints it between the square brackets of its
`--- frame <n> [<label>]` line — the WHOLE label, including everything that
follows `step-<n>` on a click frame. A label you cannot copy exactly is not a
citation: cite a `path`+`line` evidence entry instead.

This is your only correction."""
# The retry's stdout line quotes the head of the failure, not all of it.
RETRY_EXCERPT_CHARS = 120


def _vocab_section(cfg: Mapping) -> str:
    """The signed vocabulary WITH its definitions, grouped by family.

    `load_vocab` is the vocabulary of record (occurrence rows ∩ matrix columns)
    and `canon_docs.load_term_definitions` is the dictionary: the union of the
    two signed vocabulary files, final-wins, quoted verbatim and total over the
    71. Shipping the ids with their corpus counts alone — which is what this
    section did until b002 — starved the auditor of the only text that settles
    a boundary call, and it minted findings the canon explicitly excludes
    (`state.wait`'s own entry rules out claiming the per-action world clock).
    The SAME loader feeds the implementer payload, so both sides of the diff
    read one dictionary.
    """
    vocab = load_vocab(cfg)
    definitions = load_term_definitions(cfg)
    groups: dict[str, list[str]] = {}
    for term in sorted(vocab):
        # The entry is the canon's own bullet, FULL id first: the claims
        # contract takes `move.grid`, so a family-shorthand listing would be
        # teaching the wrong answer.
        groups.setdefault(term.partition(".")[0], []).append(definitions[term].text)
    body = "\n\n".join(
        f"### {family}\n" + "\n".join(groups[family]) for family in sorted(groups)
    )
    # Q-1's requirement closes the section, AFTER the definitions: "the clause
    # that separates them" is a reference to text the auditor has just read.
    return (
        VOCAB_HEADER.format(count=len(vocab))
        + "\n\n"
        + body
        + "\n\n"
        + DISTINGUISH_HEADER
    )


def _policy_quote(cfg: Mapping) -> str:
    """§10's deception policy as a quote with its canon line, the FORBIDDEN shape."""
    policy = load_deception_policy(cfg)
    return f"> {policy.text}\n> — ({policy.source})"


def _deception_section(cfg: Mapping) -> str:
    """The catalog keywords WITH the six signed levers they stand for.

    The deception half of the prompt sync (contract E-1), and the same shape
    `_vocab_section` above is: the keywords are `s1_spec.DECEPTION_CATALOG` and
    every lever is the verbatim canon entry `canon_docs.load_deception_levers`
    reads out of affordance §7, rendered by the ONE block builder the implementer
    payload and the writer prompt also quote. Handing the auditor bare keywords —
    which is what this section did until E-1 — is what made its keyword CHOICE
    unstable: five rounds of one game produced four different names for one
    trait, all of them defensible, because nothing said what the words meant.
    """
    return DECEPTION_HEADER.format(
        count=len(DECEPTION_CATALOG),
        keywords=" · ".join(f"`{keyword}`" for keyword in DECEPTION_CATALOG),
        levers=len(LEVER_GROUNDING),
        block=deception_lever_block(cfg),
    )


def build_verifier_prompt(cfg: Mapping, cap: FrameCapture, staged_dir: Path) -> str:
    """The blind audit prompt: role + canon contracts + frames + claims contract.

    Every canon section is QUOTED through an existing loader — the four
    FORBIDDEN contracts, the eight REQUIRED gates, the conventions, affordance
    §7's six deception levers and §10's deception policy come from
    `gen/canon_docs.py`, the vocabulary from `gen/s0_ideas.py::load_vocab`, the
    deception keywords from `gen/s1_spec.py::DECEPTION_CATALOG` verbatim, and
    the frames from `gen/frames.py::digest_text`. Nothing is hand-copied and
    nothing is timestamped: the same worker and frames build the same bytes.
    """
    staged_dir = Path(staged_dir)
    if not staged_dir.is_dir():
        raise FileNotFoundError(f"staged copy not found: {staged_dir}")
    inventory = sorted(_tree_files(staged_dir))
    if not inventory:
        raise ValueError(f"staged copy {staged_dir} holds no files to audit")

    quotes = "\n\n".join(
        f"> {quote.text}\n> — ({quote.source})" for quote in load_forbidden_quotes(cfg)
    )
    sections = [
        MISSION,
        "## Your working copy\n\n"
        + f"Everything below `{staged_dir}` (your current directory):\n\n"
        + "\n".join(f"- `{rel}`" for rel in inventory),
        _vocab_section(cfg),
        _deception_section(cfg),
        LOOKALIKE_HEADER.replace(LOOKALIKE_POLICY_SLOT, _policy_quote(cfg)),
        TERM_SITES_HEADER,
        FORBIDDEN_HEADER + "\n\n" + quotes,
        GATES_HEADER + "\n\n" + load_required_gates(cfg),
        CONVENTIONS_HEADER + "\n\n" + load_conventions(cfg),
        FRAMES_HEADER + "\n\n```\n" + digest_text(cap) + "\n```",
        CLAIMS_CONTRACT,
    ]
    return "\n\n".join(sections) + "\n"


# --- claims -----------------------------------------------------------------


def extract_claims(reply: str) -> dict:
    """The LAST fenced ```json block of `reply`, parsed.

    Same extraction contract as `s1_spec.extract_spec_yaml`: no block, an empty
    block, unparseable JSON and a non-mapping payload are the SAME mechanical
    failure (a malformed reply), all ValueError, never a verdict.
    """
    if not isinstance(reply, str):
        raise TypeError(f"reply must be a str, got {type(reply).__name__}")
    lines = reply.splitlines()
    blocks: list[str] = []
    opening: int | None = None
    for position, line in enumerate(lines):
        if opening is None:
            if _JSON_FENCE_OPEN_RE.match(line):
                opening = position
            continue
        if _FENCE_CLOSE_RE.match(line):
            blocks.append("\n".join(lines[opening + 1 : position]))
            opening = None
    if opening is not None:
        # Unterminated final fence: take the rest of the reply. A truncated
        # reply is common and the json either parses or it does not.
        blocks.append("\n".join(lines[opening + 1 :]))
    if not blocks:
        raise ValueError("reply contains no fenced ```json block")
    raw = blocks[-1].strip()
    if not raw:
        raise ValueError("the last fenced ```json block is empty")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"the last fenced ```json block does not parse: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(  # noqa: TRY004 — a malformed reply is one failure mode
            f"the last fenced ```json block parsed to {type(parsed).__name__}, expected an object"
        )
    return parsed


def _lever_aliases() -> dict[str, str]:
    """squashed spelling -> the catalog keyword the lever is reported under.

    "look-alike" and "lookalike" are two spellings of ONE §7.1 lever; s1's
    linter folds them with the same squash ("same lever, another spelling").
    Without the fold, a spec that declares "look-alike splits" and an auditor
    that answers "lookalike" would diff as an undeclared deception.

    Contract E-1 re-grounded WHAT folds: the table is `s1_spec.LEVER_FOLD`, so
    "camouflage" folds onto `palette overload` and "false tell" onto `lying
    display` — one entry per spelling of each of the canon's six signed levers,
    built in the one place that holds the grounding instead of re-derived here.
    """
    return dict(LEVER_FOLD)


_LEVER_ALIASES = _lever_aliases()
# (lever, spelling, pattern) — s1's own table, imported rather than rebuilt, so
# S1 and S2b cannot disagree about what the word "camouflage" means.
_LEVER_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = _DECEPTION_PATTERNS


def detect_levers(text: str) -> list[str]:
    """The catalog LEVERS `text` names, one entry per lever.

    The matcher is `s1_spec._deception_pattern` — separator- and
    inflection-tolerant — applied identically to a spec's declared entry and to
    an auditor's claimed lever, so the two sides of the diff cannot drift.
    Negation is NOT considered: s1 scans prose sketches where "not a decoy" is
    a real sentence, while both inputs here are short declarative fields.

    Every spelling folds onto its lever (contract E-1), so an auditor that says
    "camouflage" and a spec that says "palette overload" land on the same lever
    and the diff reads as agreement — which is what it always was on the board.
    """
    if not isinstance(text, str):
        raise TypeError(f"deception entry must be a str, got {type(text).__name__}")
    found: list[str] = []
    for keyword, _spelling, pattern in _LEVER_PATTERNS:
        if not pattern.search(text):
            continue
        if keyword not in found:
            found.append(keyword)
    return sorted(found)


@functools.cache
def signed_vocab() -> frozenset[str]:
    """The closed term set, loaded once from the default config.

    `validate_claims` is specified to take the claims ALONE, so it has to be
    able to reach the vocabulary itself rather than silently skip the check.
    The term set is canon (signed D20, adjudicated D28), not a per-run knob:
    every config resolves the same `duckwm_docs` tables, so the default pilot
    config is a faithful source. Callers that need a different set pass `vocab`
    explicitly — `run_agent_pass` does, from the config actually in play.
    """
    return frozenset(load_vocab(load_config(DEFAULT_CONFIG)))


def _claim_entries(claims: Mapping, section: str) -> list[Mapping]:
    entries = _as_list(claims.get(section), f"claims.{section}")
    for position, entry in enumerate(entries):
        _as_mapping(entry, f"claims.{section}[{position}]")
    return list(entries)


def _check_evidence(where: str, entry: Mapping, frame_labels: Collection[str] | None) -> None:
    """One claim must cite `path:line` or a frame label that really exists."""
    evidence = _as_list(entry.get("evidence", []), f"{where}.evidence")
    for position, item in enumerate(evidence):
        spot = f"{where}.evidence[{position}]"
        _as_mapping(item, spot)
        _as_text(item.get("path"), f"{spot}.path")
        line = item.get("line")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise ValueError(f"{spot}.line must be a positive int, got {line!r}")

    refs = _as_list(entry.get("frame_refs", []), f"{where}.frame_refs")
    for position, ref in enumerate(refs):
        _as_text(ref, f"{where}.frame_refs[{position}]")
        if frame_labels is not None and ref not in frame_labels:
            raise ValueError(
                f"{where}.frame_refs[{position}] is {ref!r}, which is not a captured frame "
                f"label ({sorted(frame_labels)})"
            )
    if not evidence and not refs:
        raise ValueError(
            f"{where} cites nothing — every claim needs a path+line evidence entry or a "
            f"frame_refs label"
        )


def validate_claims(
    claims: dict,
    vocab: Collection[str] | None = None,
    frame_labels: Collection[str] | None = None,
) -> None:
    """Fail loud unless `claims` satisfies the frozen claims contract.

    Checked always: the five top-level keys exactly, the type of every section,
    a non-empty subject per entry (`term`/`what`/`lever`/`claim`), the dotted
    shape of every term id AND its membership in the closed vocabulary, that
    every lever normalizes to a catalog keyword, and that every claim cites a
    path+line pair or a frame label.

    `vocab` defaults to `signed_vocab()` so the one-argument call still catches
    an unknown term; pass it to validate against the config actually in play
    (`run_agent_pass` does). `frame_labels` is the only OPTIONAL fact: without
    a capture there is nothing to check a frame reference against, so the refs
    are then only checked for shape.
    """
    if not isinstance(claims, Mapping):
        raise TypeError(f"claims must be a mapping, got {type(claims).__name__}")
    if vocab is None:
        vocab = signed_vocab()
    missing = [key for key in CLAIMS_KEYS if key not in claims]
    extra = sorted(set(claims) - set(CLAIMS_KEYS) - set(OPTIONAL_CLAIMS_KEYS))
    if missing or extra:
        raise ValueError(
            f"claims must have exactly the keys {list(CLAIMS_KEYS)} (plus the optional "
            f"{list(OPTIONAL_CLAIMS_KEYS)}) — missing {missing}, unexpected {extra}"
        )
    _require(claims["notes"], str, "claims.notes")

    # The look-alike inventory, when the reply carries one: same evidence rule
    # as every other claim (a family nobody can point at is not a finding), and
    # `index` is checked against the rendered palette because the whole value of
    # the field is that it names an index the code-side detector can be held to.
    inventory = _claim_entries(claims, LOOKALIKES_KEY) if LOOKALIKES_KEY in claims else []
    for position, entry in enumerate(inventory):
        where = f"claims.{LOOKALIKES_KEY}[{position}]"
        _as_text(entry.get(LOOKALIKE_CLAIM_SUBJECT), f"{where}.{LOOKALIKE_CLAIM_SUBJECT}")
        index = entry.get("index")
        if index is not None and (
            isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 15
        ):
            raise ValueError(
                f"{where}.index must be null or a palette index 0-15, got {index!r}"
            )
        if entry.get("differs_by") is not None:
            _as_text(entry["differs_by"], f"{where}.differs_by")
        _check_evidence(where, entry, frame_labels)

    # R-18's site inventory, when the reply carries one. `term` is held to the
    # closed vocabulary exactly as `claims.terms` is — an inventory that grounds
    # a term nobody may claim grounds nothing — and `site` is prose or null.
    #
    # The evidence rule is asymmetric ON PURPOSE, and it is the only place in
    # this validator that it is: a NAMED site cites, because it is a positive
    # claim about the code and this pipeline does not take uncited ones; a NULL
    # site does not, because it asserts that nothing is there and there is no
    # line at which nothing lives. Demanding a citation for an absence would
    # teach the auditor to point at something rather than say null, which is the
    # one answer this section exists to make sayable.
    sites = _claim_entries(claims, TERM_SITES_KEY) if TERM_SITES_KEY in claims else []
    seen_sites: set[str] = set()
    for position, entry in enumerate(sites):
        where = f"claims.{TERM_SITES_KEY}[{position}]"
        term = _as_text(entry.get("term"), f"{where}.term")
        if not _TERM_RE.match(term):
            raise ValueError(
                f"{where}.term {term!r} is not a vocabulary id (expected group.leaf)"
            )
        if term not in vocab:
            raise ValueError(
                f"{where}.term {term!r} is not in the {len(vocab)}-term signed vocabulary"
            )
        if term in seen_sites:
            raise ValueError(
                f"{where}.term {term!r} is inventoried twice — one term has one site, and "
                f"two entries for it cannot both be the answer"
            )
        seen_sites.add(term)
        site = entry.get("site")
        if site is None:
            continue
        _as_text(site, f"{where}.site")
        _check_evidence(where, entry, frame_labels)

    for section, subject in CLAIM_SUBJECT.items():
        for position, entry in enumerate(_claim_entries(claims, section)):
            where = f"claims.{section}[{position}]"
            value = _as_text(entry.get(subject), f"{where}.{subject}")
            if section == "terms":
                if not _TERM_RE.match(value):
                    raise ValueError(
                        f"{where}.term {value!r} is not a vocabulary id (expected group.leaf)"
                    )
                if value not in vocab:
                    raise ValueError(
                        f"{where}.term {value!r} is not in the {len(vocab)}-term signed vocabulary"
                    )
                reachable = entry.get("reachable")
                if not isinstance(reachable, bool):
                    raise ValueError(
                        f"{where}.reachable must be a bool, got {reachable!r}"
                    )
                # Q-1's attribution break, when the entry carries one. ADDITIVE:
                # the key is optional, a reply written before the prompt asked
                # for it validates unchanged, and a `terms` entry is not a closed
                # key set (it already carries `evidence` and `frame_refs`), so
                # nothing about an old reply moves.
                #
                # SHAPE ONLY, and that boundary is the point: this validator
                # knows the closed VOCABULARY and not the spec, so it checks that
                # the named term is a real vocabulary id with a real clause
                # beside it. Whether that id is one the SPEC DECLARES — the other
                # half of "well-formed" — is decided in `term_disputes`, the one
                # place that has the declared side in hand, and it is decided
                # WITHOUT raising: see the note there.
                if DISTINGUISHES_KEY in entry:
                    spot = f"{where}.{DISTINGUISHES_KEY}"
                    broken = _as_mapping(entry[DISTINGUISHES_KEY], spot)
                    if set(broken) != set(DISTINGUISHES_ENTRY_KEYS):
                        raise ValueError(
                            f"{spot} must have exactly the keys "
                            f"{list(DISTINGUISHES_ENTRY_KEYS)} — the neighbouring term this "
                            f"behaviour is NOT and the definitional clause separating them; "
                            f"got {sorted(broken)}"
                        )
                    other = _as_text(broken["term"], f"{spot}.term")
                    if not _TERM_RE.match(other):
                        raise ValueError(
                            f"{spot}.term {other!r} is not a vocabulary id (expected "
                            f"group.leaf)"
                        )
                    if other not in vocab:
                        raise ValueError(
                            f"{spot}.term {other!r} is not in the {len(vocab)}-term signed "
                            f"vocabulary — a term nobody may claim cannot be the term this "
                            f"behaviour is distinguished FROM"
                        )
                    if other == value:
                        raise ValueError(
                            f"{spot}.term is {other!r}, the term the entry itself claims — "
                            f"a claim cannot be distinguished from itself"
                        )
                    _as_text(broken["clause"], f"{spot}.clause")
            if section == "deceptions" and not detect_levers(value):
                raise ValueError(
                    f"{where}.lever {value!r} matches no catalog keyword "
                    f"({list(DECEPTION_CATALOG)})"
                )
            _check_evidence(where, entry, frame_labels)


# --- the diff ---------------------------------------------------------------


def _spec_game(spec: Mapping) -> Mapping:
    if not isinstance(spec, Mapping):
        raise TypeError(f"spec must be a mapping, got {type(spec).__name__}")
    game = spec.get("game")
    if not isinstance(game, Mapping):
        raise ValueError(  # noqa: TRY004 — a malformed spec is bad data, not a caller type error
            f"spec has no top-level 'game' mapping (top-level keys: {sorted(spec)})"
        )
    return game


def _declared_terms(game: Mapping) -> list[str]:
    terms = game.get("terms")
    if not isinstance(terms, list) or not terms:
        raise ValueError(f"spec game.terms must be a non-empty list, got {terms!r}")
    declared: list[str] = []
    for term in terms:
        if not isinstance(term, str) or not term.strip():
            raise ValueError(f"spec game.terms must be a list of strings, got {terms!r}")
        if term not in declared:  # a repeated term is one declaration
            declared.append(term)
    return declared


def _declared_deceptions(game: Mapping) -> list[str]:
    """Declared entries normalized to catalog keywords, unmatched ones kept raw.

    An entry that matches no keyword (affordance §7.5's invisible load-bearing
    state has no catalog word by design — see s1_spec's catalog notes) is kept
    verbatim rather than dropped: it then surfaces under
    `declared_deceptions_undetected`, which is the warning the human review at
    S5 exists to read, instead of silently disappearing from the diff.
    """
    knobs = game.get("knobs")
    if knobs is None:
        return []
    _as_mapping(knobs, "spec game.knobs")
    entries = knobs.get("deceptions", [])
    if entries is None:
        return []
    _as_list(entries, "spec game.knobs.deceptions")
    declared: list[str] = []
    for position, entry in enumerate(entries):
        _as_text(entry, f"spec game.knobs.deceptions[{position}]")
        levers = detect_levers(entry)
        for lever in levers or [entry.strip().lower()]:
            if lever not in declared:
                declared.append(lever)
    return declared


def _exempt_terms(cfg: Mapping) -> tuple[str, ...]:
    """`verifier.exempt_terms` from the config, validated at READ time.

    Absent knob -> `()`, and every default path stays byte-for-byte what it was
    (canon behavior is the default; the deviation is opted into per batch). A
    present one is checked before a diff is computed: a non-list, a non-string
    entry or a term outside the signed vocabulary raises, because a typo like
    `budget_cap` would exempt nothing while the config claims the ping-pong is
    fixed. Same shape as `_bfs_cell_cap` — a signed knob read in one place.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or "exempt_terms" not in verifier:
        return ()
    terms = _as_list(verifier["exempt_terms"], "verifier.exempt_terms")
    for position, term in enumerate(terms):
        _as_text(term, f"verifier.exempt_terms[{position}]")
    vocab = load_vocab(cfg)
    unknown = sorted(term for term in terms if term not in vocab)
    if unknown:
        raise ValueError(
            f"verifier.exempt_terms names {unknown}, which the {len(vocab)}-term signed "
            f"vocabulary does not carry — an exemption matching no term suppresses nothing "
            f"and hides that it suppresses nothing"
        )
    return tuple(terms)


def _apply_exemptions(diff: dict, exempt_terms: Collection[str]) -> dict:
    """Move each exempt term's finding out of the three reject-bearing lists.

    Nothing exempt -> the diff itself, untouched. Otherwise a COPY whose
    `exempted` list records every suppressed finding as
    `{term, would_have_been}`: the audit's data survives in the report, only
    its power to reject is removed. The three lists are mutually exclusive by
    construction (declared-and-unseen, declared-and-unreachable, reachable-and-
    undeclared), so one term yields at most one entry.

    Idempotent: a second application finds the terms already moved and leaves
    the record alone, so the report builder can re-assert the config's
    exemptions over a diff whose caller already applied them. A malformed diff
    is left to `_validate_diff` rather than pre-empted here.
    """
    exempt = frozenset(exempt_terms)
    if not exempt:
        return diff
    out = dict(diff)
    exempted = [dict(entry) for entry in out.get(EXEMPTED_KEY, [])]
    for key, code in EXEMPTABLE_FINDINGS:
        values = out.get(key)
        if not isinstance(values, list):
            continue
        suppressed = [term for term in values if term in exempt]
        if not suppressed:
            continue
        out[key] = [term for term in values if term not in exempt]
        exempted.extend({"term": term, "would_have_been": code} for term in suppressed)
    out[EXEMPTED_KEY] = sorted(
        exempted, key=lambda entry: (entry["term"], entry["would_have_been"])
    )
    return out


def _lever_corroboration(cfg: Mapping) -> bool:
    """`verifier.lever_corroboration` from the config, validated at READ time.

    Absent knob -> False, and every default path stays byte-for-byte what it
    was (canon behavior is the default; the deviation is opted into per batch).
    A present one must be a REAL bool: `"true"`, `1` and `"no"` are all truthy
    strings-or-ints that would silently change which findings can reject, and
    this knob decides rejects. Same shape as `_exempt_terms` above — a signed
    knob read in one place.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or LEVER_CORROBORATION_KEY not in verifier:
        return False
    value = verifier[LEVER_CORROBORATION_KEY]
    if not isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 — a bad config value is bad data, like `exempt_terms`
            f"verifier.{LEVER_CORROBORATION_KEY} must be a bool, got {value!r} — this knob "
            f"decides which findings may reject, so a truthy string is never read as 'on'"
        )
    return value


def _lever_window(cfg: Mapping) -> int | None:
    """`verifier.lever_corroboration_window` from the config, validated at READ time.

    Absent or null -> `None`, which is today's any-prior-round union, byte for
    byte. A present one is a POSITIVE int: how many of the most recently
    recorded rounds may corroborate a finding. Every other value is loud rather
    than coerced, because each would silently mean something the config does not
    say: `0` is not "no window" but "nothing corroborates", which rejects every
    lever on sight while the config claims a raised bar; a negative is a slice
    that reads backwards (`history[-(-1):]` is every round but the first); `True`
    is `1` wearing a bool; `"1"` is a string this stage would compare against
    ints. Read at the same seam as `_lever_corroboration`, so a bad one fails
    before any file is touched.

    The window is meaningful ONLY while `lever_corroboration` is on, so setting
    it against a corroboration pass that is not running raises instead of being
    ignored: a window with nothing to window is a config contradiction, and it
    would read to anyone auditing the batch as a bar that is not there.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or LEVER_WINDOW_KEY not in verifier:
        return None
    value = verifier[LEVER_WINDOW_KEY]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        # ValueError, not TypeError, for the reason `_lever_corroboration` above
        # gives: a bad config value is bad DATA, like `exempt_terms`.
        raise ValueError(
            f"verifier.{LEVER_WINDOW_KEY} must be a positive int — the number of most "
            f"recent recorded rounds that may corroborate a lever — or null for every "
            f"prior round; got {value!r}"
        )
    if not _lever_corroboration(cfg):
        raise ValueError(
            f"verifier.{LEVER_WINDOW_KEY} is {value!r} while "
            f"verifier.{LEVER_CORROBORATION_KEY} is off — the window narrows the "
            f"corroboration pass, so a window with no pass to narrow suppresses nothing "
            f"while the config reads as a raised reject bar"
        )
    return value


def _deception_action(cfg: Mapping) -> str:
    """`verifier.deception_action` from the config, validated at READ time.

    Absent knob -> `"reject"`, and every default path stays byte-for-byte what
    it was (canon behavior is the default; the deviation is opted into per
    batch). A present one must be one of the two signed words, and anything else
    is loud rather than coerced for this knob's own reason: a config writing
    `lenient` reads to the human who wrote it as "be lenient", while a stage
    that fell back to the default would go on rejecting exactly the games the
    knob was set to let through — the one failure mode a leniency knob must not
    have. Same shape as `_lever_corroboration` above — a signed knob read in one
    place, before anything is computed or written.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or DECEPTION_ACTION_KEY not in verifier:
        return DECEPTION_ACTION_REJECT
    value = verifier[DECEPTION_ACTION_KEY]
    if not isinstance(value, str) or value not in DECEPTION_ACTIONS:
        # ValueError, not TypeError, for the reason `_lever_window` above gives:
        # a bad config value is bad DATA, like `exempt_terms`.
        raise ValueError(
            f"verifier.{DECEPTION_ACTION_KEY} must be one of {list(DECEPTION_ACTIONS)} — "
            f"{DECEPTION_ACTION_REJECT!r} lets an undeclared-deception finding decide the "
            f"verdict (the default), {DECEPTION_ACTION_RECORD!r} records it as an advisory "
            f"on the report instead; got {value!r}"
        )
    return value


def _term_dispute_action(cfg: Mapping) -> str:
    """`verifier.term_dispute_action` from the config, validated at READ time.

    Absent knob -> `"reject"`, and every default path stays byte-for-byte what it
    was (canon behavior is the default; the deviation is opted into per batch).
    `_deception_action` above is the pattern and its reason binds here word for
    word: a config writing `lenient` reads to the human who wrote it as "be
    lenient", while a stage that fell back to the default would go on rejecting
    exactly the games the knob was set to let through — the one failure mode a
    leniency knob must not have. A signed knob read in one place, before anything
    is computed or written.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or TERM_DISPUTE_ACTION_KEY not in verifier:
        return TERM_DISPUTE_ACTION_REJECT
    value = verifier[TERM_DISPUTE_ACTION_KEY]
    if not isinstance(value, str) or value not in TERM_DISPUTE_ACTIONS:
        # ValueError, not TypeError, for the reason `_lever_window` above gives:
        # a bad config value is bad DATA, like `exempt_terms`.
        raise ValueError(
            f"verifier.{TERM_DISPUTE_ACTION_KEY} must be one of "
            f"{list(TERM_DISPUTE_ACTIONS)} — {TERM_DISPUTE_ACTION_REJECT!r} lets a DISPUTED "
            f"term finding decide the verdict (the default), "
            f"{TERM_DISPUTE_ACTION_RECORD!r} records it in the report's "
            f"{TERM_DISPUTES_KEY!r} instead; got {value!r}"
        )
    return value


def lever_history_path(worker: Path) -> Path:
    """`<worker>.lever-history.json` — the per-slot round record, beside it."""
    worker = Path(worker)
    return worker.with_name(worker.name + LEVER_HISTORY_SUFFIX)


def _validate_history_entry(entry: object, where: str) -> Mapping:
    """One recorded round: a stamp and the levers that round detected.

    Checked, not assumed: this file is pipeline state a LATER round reads to
    decide a verdict. Extra keys are tolerated on purpose — the record is
    append-only, so a field some later round adds must not make an earlier
    round unreadable — but the two it is read for are not optional.
    """
    _as_mapping(entry, where)
    _as_text(entry.get(HISTORY_TS_KEY), f"{where}.{HISTORY_TS_KEY}")
    _require_str_list(entry.get(HISTORY_DETECTED_KEY), f"{where}.{HISTORY_DETECTED_KEY}")
    return entry


def read_lever_history(path: Path) -> list[Mapping]:
    """The rounds already recorded beside this worker, oldest first.

    No file yet -> `[]`: a cold start is deliberately a history of nothing, so
    every lever this round finds is a first sighting.

    A file that does not parse RAISES rather than starting over. The precedent
    is the findings feed (`gen/orchestrator.py`: a verifier report that will
    not parse stops the slot and asks for a human), and the reason is sharper
    here — a silently reset history corroborates nothing while reporting
    nothing, which is exactly the failure this record exists to prevent.
    """
    path = Path(path)
    if not path.is_file():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} is not valid JSON ({exc}) — the lever history is pipeline state a "
            f"later round reads to decide a verdict, and this stage never records a round "
            f"over a file it cannot read; read the file and repair or remove it"
        ) from exc
    _as_list(entries, f"{path}: the lever history")
    for position, entry in enumerate(entries):
        _validate_history_entry(entry, f"{path}[{position}]")
    return list(entries)


def append_lever_history(path: Path, detected: Sequence[str]) -> list[Mapping]:
    """Record one audit round's detections; return the history as it now stands.

    APPEND-ONLY: every existing entry is rewritten verbatim and this round's
    goes last. `detected` is what the audit saw this round, declared or not
    (`diff["deceptions_detected"]`) — the record is of DETECTION, never of
    verdicts, so a declared lever lands here exactly like an undeclared one and
    the history stays readable whatever the knob was set to when it was
    written.
    """
    path = Path(path)
    history = read_lever_history(path)
    levers = [
        _as_text(lever, f"{path}: this round's {HISTORY_DETECTED_KEY}[{position}]")
        for position, lever in enumerate(detected)
    ]
    history.append({HISTORY_TS_KEY: datetime.now(UTC).isoformat(), HISTORY_DETECTED_KEY: levers})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    return history


def corroborated_levers(history: Sequence[Mapping], window: int | None = None) -> frozenset[str]:
    """Every lever a recorded round in scope detected — the corroboration set.

    Callers pass the history read BEFORE this round was appended: a lever
    corroborates itself only across two independent sessions, so a round may
    never vouch for its own finding. That append-after-read order is frozen.

    `window=None` is the union over EVERY prior round — what this function has
    always computed, unchanged. `window=N` is the union over the last N recorded
    rounds only (`history[-N:]`), which is the b003 C-2 ruling: over a long slot
    the unwindowed union saturates, so a lever corroborates only if a RECENT
    round also named it.

    Every entry is validated whatever the window is. The history is pipeline
    state a verdict is read out of, and a malformed round outside the window is
    still a file this stage refuses to reason over — narrowing which rounds
    COUNT must not quietly narrow which rounds are CHECKED.
    """
    entries = list(history)
    for position, entry in enumerate(entries):
        _validate_history_entry(entry, f"lever history[{position}]")
    if window is not None:
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            raise ValueError(  # bad data, the same gate `_lever_window` applies
                f"corroboration window must be a positive int or None, got {window!r}"
            )
        entries = entries[-window:]
    levers: set[str] = set()
    for entry in entries:
        levers.update(entry[HISTORY_DETECTED_KEY])
    return frozenset(levers)


def _apply_corroboration(diff: dict, corroborated: Collection[str] | None = None) -> dict:
    """Move each first-sighting lever out of the reject-bearing list.

    `None` means the knob is OFF and returns the diff itself, untouched — the
    default everywhere, so a batch that does not opt in gets today's bytes.
    With a collection (EMPTY on a cold start, which is not the same as `None`)
    the result is a COPY whose `uncorroborated_levers` list records every
    demoted finding as `{lever, note}`: the `exempted` pattern above exactly,
    one class over — the audit's data survives in the report, only its power to
    reject is removed, and `decide_verdict` reads what remains.

    Idempotent for the same reason `_apply_exemptions` is: a second application
    finds the levers already moved and leaves the record alone. A malformed
    diff is left to `_validate_diff` rather than pre-empted here.
    """
    if corroborated is None:
        return diff
    corroborated = frozenset(corroborated)
    out = dict(diff)
    recorded = [dict(entry) for entry in out.get(UNCORROBORATED_KEY, [])]
    levers = out.get("undeclared_deceptions")
    if isinstance(levers, list):
        first_sightings = [lever for lever in levers if lever not in corroborated]
        out["undeclared_deceptions"] = [lever for lever in levers if lever in corroborated]
        recorded.extend(
            {"lever": lever, "note": FIRST_SIGHTING_NOTE} for lever in first_sightings
        )
    out[UNCORROBORATED_KEY] = sorted(
        recorded, key=lambda entry: (entry["lever"], entry["note"])
    )
    return out


def _term_corroboration(cfg: Mapping) -> bool:
    """`verifier.term_corroboration` from the config, validated at READ time.

    Absent knob -> False, and every default path stays byte-for-byte what it
    was (canon behavior is the default; the deviation is opted into per batch).
    A present one must be a REAL bool for the reason `_lever_corroboration`
    above gives: `"true"`, `1` and `"no"` are all truthy values that would
    silently change which findings can reject, and this knob decides rejects.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or TERM_CORROBORATION_KEY not in verifier:
        return False
    value = verifier[TERM_CORROBORATION_KEY]
    if not isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 — a bad config value is bad data, like `exempt_terms`
            f"verifier.{TERM_CORROBORATION_KEY} must be a bool, got {value!r} — this knob "
            f"decides which findings may reject, so a truthy string is never read as 'on'"
        )
    return value


def _term_window(cfg: Mapping) -> int | None:
    """`verifier.term_corroboration_window` from the config, validated at READ time.

    Absent or null -> `None`, the union over every prior recorded round. A
    present one is a POSITIVE int: how many of the most recently recorded rounds
    may corroborate a term finding. Every other value is loud rather than
    coerced, for the reasons `_lever_window` sets out value by value — `0` is
    not "no window" but "nothing corroborates", a negative is a slice that reads
    backwards, `True` is `1` wearing a bool, and `"1"` is a string this stage
    would compare against ints.

    The window is meaningful ONLY while `term_corroboration` is on, so setting
    it against a corroboration pass that is not running raises instead of being
    ignored: a window with nothing to window is a config contradiction, and it
    would read to anyone auditing the batch as a bar that is not there.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or TERM_WINDOW_KEY not in verifier:
        return None
    value = verifier[TERM_WINDOW_KEY]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        # ValueError, not TypeError: a bad config value is bad DATA, the rule
        # `_exempt_terms` set and `_lever_window` follows.
        raise ValueError(
            f"verifier.{TERM_WINDOW_KEY} must be a positive int — the number of most "
            f"recent recorded rounds that may corroborate a term finding — or null for "
            f"every prior round; got {value!r}"
        )
    if not _term_corroboration(cfg):
        raise ValueError(
            f"verifier.{TERM_WINDOW_KEY} is {value!r} while "
            f"verifier.{TERM_CORROBORATION_KEY} is off — the window narrows the "
            f"corroboration pass, so a window with no pass to narrow suppresses nothing "
            f"while the config reads as a raised reject bar"
        )
    return value


def _confirm_pass(cfg: Mapping) -> bool:
    """`verifier.confirm_pass` from the config, validated at READ time.

    Absent knob -> False, and every default path stays byte-for-byte what it was:
    one blind session per verify round, a pass ending the loop. A present one
    must be a REAL bool for the reason `_lever_corroboration` gives — `"true"`,
    `1` and `"no"` are all truthy values, and this knob decides whether a slot
    buys a second session.

    True while BOTH `_lever_corroboration` and `_term_corroboration` are off
    RAISES. A confirmation round is bought by an uncorroborated RECORDING, and
    with neither corroboration pass running nothing is ever recorded — so the
    knob would buy nothing, ever, while the config reads as a doubled audit.
    That is `_lever_window`'s contradiction rule read from the other end: there a
    window narrows a pass that is not running, here a confirmation waits on
    records that can never be written. Read at the same seam as the knobs it
    depends on, so a contradictory config fails before any session is spent.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or VERIFY_CONFIRM_KEY not in verifier:
        return False
    value = verifier[VERIFY_CONFIRM_KEY]
    if not isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 — a bad config value is bad data, like `exempt_terms`
            f"verifier.{VERIFY_CONFIRM_KEY} must be a bool, got {value!r} — this knob "
            f"decides whether a passing round buys a second blind session, so a truthy "
            f"string is never read as 'on'"
        )
    if value and not (_lever_corroboration(cfg) or _term_corroboration(cfg)):
        raise ValueError(
            f"verifier.{VERIFY_CONFIRM_KEY} is on while both "
            f"verifier.{LEVER_CORROBORATION_KEY} and verifier.{TERM_CORROBORATION_KEY} are "
            f"off — a confirmation round is triggered by an uncorroborated recording, and "
            f"with neither corroboration pass running nothing is ever recorded, so this "
            f"would never buy a second session while the config reads as a doubled audit"
        )
    return value


def _lookalike_mode(cfg: Mapping) -> str:
    """`verifier.lookalike_declared` — off | record (the default) | fail.

    Absent knob -> `record`, and that default is the ONE place this contract
    departs from "unconfigured runs are byte-identical". The departure is W2-B's
    ruling, read the same way: the house rule binds on the OFFICIALS' path, and
    there it holds exactly — the detector is generated-only, is not in
    `run_static_checks`, and returns `premise-not-met` on all 25 signed officials
    (measured), so no official's result set, count or report moves by a byte. For
    a GENERATED game the report gains the optional `lookalikes` block, and that
    is the point of a measurement pass: an evidence detector that has to be armed
    to measure anything measures nothing on the batch that would have needed it.
    `off` reproduces a pre-A3 report exactly, for a run that wants one.

    Validated at READ time, before the detector touches a worker, and loud on
    anything outside the enum — a typo'd mode must never read as "on" or "off"
    by accident, because this knob decides whether a finding can reject.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or LOOKALIKE_KNOB not in verifier:
        return DEFAULT_LOOKALIKE_MODE
    value = verifier[LOOKALIKE_KNOB]
    if value not in LOOKALIKE_MODES:
        raise ValueError(
            f"verifier.{LOOKALIKE_KNOB} must be one of {list(LOOKALIKE_MODES)}, got "
            f"{value!r} — `fail` is the armed gate and `record` is the evidence default, "
            f"so a value outside the enum is never guessed at"
        )
    return value


def _refusal_honest_mode(cfg: Mapping) -> str:
    """`verifier.refusal_honest` — off | record (the default) | fail.

    Absent knob -> `record`, the same departure `_lookalike_mode` above makes
    and for the same W2-B reason: the house rule binds on the OFFICIALS' path,
    and there it holds exactly — the detector is generated-only, is not in
    `run_static_checks`, and answers `premise-not-met` on an official source by
    construction, so no official's result set, count or report moves by a byte.
    For a GENERATED game the report gains the check row, which is the point of a
    measurement pass. `off` reproduces a pre-B3 report exactly.

    Validated at READ time, before the detector touches a worker, and loud on
    anything outside the enum: this knob decides whether a finding can reject,
    so a typo must never read as `on` or `off` by accident.
    """
    verifier = cfg.get("verifier") if isinstance(cfg, Mapping) else None
    if not isinstance(verifier, Mapping) or REFUSAL_HONEST_KNOB not in verifier:
        return DEFAULT_REFUSAL_HONEST_MODE
    value = verifier[REFUSAL_HONEST_KNOB]
    if value not in REFUSAL_HONEST_MODES:
        raise ValueError(
            f"verifier.{REFUSAL_HONEST_KNOB} must be one of "
            f"{list(REFUSAL_HONEST_MODES)}, got {value!r} — `fail` is the armed gate and "
            f"`record` is the evidence default, so a value outside the enum is never "
            f"guessed at"
        )
    return value


def term_sites_block(claims: Mapping | None) -> dict | None:
    """The reply's site inventory as `{term: site|null}`, or None when absent.

    The report's optional `term_sites` block, lifted out of `agent.claims` at
    the one seam that holds both (the A3 `lookalikes` pattern). None — no key at
    all — whenever the reply carried no inventory, so a report written from a
    pre-B3 reply is byte for byte the report it was.
    """
    if not isinstance(claims, Mapping) or TERM_SITES_KEY not in claims:
        return None
    entries = _as_list(claims[TERM_SITES_KEY], f"claims.{TERM_SITES_KEY}")
    block: dict[str, str | None] = {}
    for position, entry in enumerate(entries):
        where = f"claims.{TERM_SITES_KEY}[{position}]"
        _as_mapping(entry, where)
        term = _as_text(entry.get("term"), f"{where}.term")
        site = entry.get("site")
        block[term] = None if site is None else _as_text(site, f"{where}.site")
    return block


def term_history_path(worker: Path) -> Path:
    """`<worker>.term-history.json` — the per-slot round record, beside it."""
    worker = Path(worker)
    return worker.with_name(worker.name + TERM_HISTORY_SUFFIX)


def _validate_term_history_entry(entry: object, where: str) -> Mapping:
    """One recorded round: a stamp and the round's three DIRECTION lists.

    `_validate_history_entry`'s rules, one key per direction: checked rather
    than assumed because this file is pipeline state a later round reads to
    decide a verdict, and extra keys are tolerated on purpose so a field some
    later round adds cannot make an earlier round unreadable. The four it is
    read for are not optional — a round missing a direction is not a round that
    found nothing there, it is a record this stage cannot tell those two apart
    from.
    """
    _as_mapping(entry, where)
    _as_text(entry.get(HISTORY_TS_KEY), f"{where}.{HISTORY_TS_KEY}")
    for key in TERM_HISTORY_KEYS:
        _require_str_list(entry.get(key), f"{where}.{key}")
    # R-18's direction is checked WHEN PRESENT and never required: see
    # `HISTORY_UNIMPLEMENTED_KEY` for why absence is a readable answer here and
    # not for the three above.
    if HISTORY_UNIMPLEMENTED_KEY in entry:
        _require_str_list(
            entry[HISTORY_UNIMPLEMENTED_KEY], f"{where}.{HISTORY_UNIMPLEMENTED_KEY}"
        )
    return entry


def read_term_history(path: Path) -> list[Mapping]:
    """The term rounds already recorded beside this worker, oldest first.

    No file yet -> `[]`: a cold start is deliberately a history of nothing, so
    every finding this round makes is a first sighting.

    A file that does not parse RAISES rather than starting over, for the reason
    `read_lever_history` gives — a silently reset history corroborates nothing
    while reporting nothing, which is exactly the failure this record exists to
    prevent.
    """
    path = Path(path)
    if not path.is_file():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} is not valid JSON ({exc}) — the term history is pipeline state a "
            f"later round reads to decide a verdict, and this stage never records a round "
            f"over a file it cannot read; read the file and repair or remove it"
        ) from exc
    _as_list(entries, f"{path}: the term history")
    for position, entry in enumerate(entries):
        _validate_term_history_entry(entry, f"{path}[{position}]")
    return list(entries)


def append_term_history(
    path: Path,
    dead: Sequence[str],
    undeclared: Sequence[str],
    unreachable: Sequence[str],
    unimplemented: Sequence[str] | None = None,
) -> list[Mapping]:
    """Record one audit round's direction lists; return the history.

    APPEND-ONLY, like `append_lever_history`: every existing entry is rewritten
    verbatim and this round's goes last. The arguments are the round's diff
    lists as they stand AFTER exemptions and BEFORE corroboration — what this
    round's audit actually found, never what it was allowed to reject on, so the
    record stays readable whatever the knobs were set to when it was written.

    Each list is stored sorted: the record is a SET of findings per direction,
    and a stable spelling on disk keeps two rounds that found the same things
    byte-comparable by eye.

    `unimplemented` (R-18) defaults to None, which writes NO key — the record a
    round that did not measure implementation sites leaves, byte for byte the
    entry this function wrote before the direction existed. An empty LIST is a
    different statement, and the caller makes it deliberately: this round asked
    for sites, got an inventory, and every declared term was grounded.
    """
    path = Path(path)
    history = read_term_history(path)
    entry = {HISTORY_TS_KEY: datetime.now(UTC).isoformat()}
    for key, terms in zip(TERM_HISTORY_KEYS, (dead, undeclared, unreachable), strict=True):
        entry[key] = sorted(
            _as_text(term, f"{path}: this round's {key}[{position}]")
            for position, term in enumerate(terms)
        )
    if unimplemented is not None:
        entry[HISTORY_UNIMPLEMENTED_KEY] = sorted(
            _as_text(
                term, f"{path}: this round's {HISTORY_UNIMPLEMENTED_KEY}[{position}]"
            )
            for position, term in enumerate(unimplemented)
        )
    history.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    return history


def corroborated_terms(
    history: Sequence[Mapping], window: int | None = None
) -> frozenset[tuple[str, str]]:
    """Every (direction, term) a recorded round in scope reported.

    The corroboration set for the term pass, keyed by DIRECTION as well as by
    term: `("dead", "move.grid")` and `("undeclared", "move.grid")` are two
    different findings, and a term reported dead in one round and undeclared in
    the next corroborates NEITHER. That is the b003 slot-1 measurement made
    operational — those two readings of the same bytes contradict each other,
    so a pair of them is evidence the pass is unstable, not evidence about the
    game.

    Callers pass the history read BEFORE this round was appended: a round may
    never vouch for its own finding. That append-after-read order is frozen,
    exactly as it is for `corroborated_levers`.

    `window=None` is the union over every prior round; `window=N` is the union
    over the last N recorded rounds only (`history[-N:]`). Every entry is
    validated whatever the window is — narrowing which rounds COUNT must not
    quietly narrow which rounds are CHECKED.
    """
    entries = list(history)
    for position, entry in enumerate(entries):
        _validate_term_history_entry(entry, f"term history[{position}]")
    if window is not None:
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            raise ValueError(  # bad data, the same gate `_term_window` applies
                f"corroboration window must be a positive int or None, got {window!r}"
            )
        entries = entries[-window:]
    pairs: set[tuple[str, str]] = set()
    for entry in entries:
        for direction in TERM_HISTORY_READ_KEYS:
            # `.get`, not `[]`, for the OPTIONAL fourth direction only: an entry
            # that never recorded it contributes nothing to the corroborating
            # set, which is the reading that can only ever make the bar harder
            # to clear.
            pairs.update((direction, term) for term in entry.get(direction, ()))
    return frozenset(pairs)


def _apply_term_corroboration(
    diff: dict, corroborated: Collection[tuple[str, str]] | None = None
) -> dict:
    """Move each first-sighting term finding out of its reject-bearing list.

    `None` means the knob is OFF and returns the diff itself, untouched — the
    default everywhere, so a batch that does not opt in gets today's bytes.
    With a collection of `(direction, term)` pairs (EMPTY on a cold start, which
    is not the same as `None`) the result is a COPY whose `uncorroborated_terms`
    list records every demoted finding as `{term, code, note}`: the `exempted` /
    `uncorroborated_levers` pattern exactly — the audit's data survives in the
    report, only its power to reject is removed, and `decide_verdict` reads what
    remains.

    A term is kept in its list only if the SAME direction corroborates it, so
    the three lists are judged independently and a rotation between them
    demotes both halves.

    Idempotent for the same reason `_apply_corroboration` is: a second
    application finds the terms already moved and leaves the record alone. A
    malformed diff is left to `_validate_diff` rather than pre-empted here.
    """
    if corroborated is None:
        return diff
    corroborated = frozenset(corroborated)
    out = dict(diff)
    recorded = [dict(entry) for entry in out.get(UNCORROBORATED_TERMS_KEY, [])]
    for direction, key, code in TERM_DIRECTIONS:
        terms = out.get(key)
        if not isinstance(terms, list):
            continue
        first_sightings = [term for term in terms if (direction, term) not in corroborated]
        out[key] = [term for term in terms if (direction, term) in corroborated]
        recorded.extend(
            {"term": term, "code": code, "note": TERM_FIRST_SIGHTING_NOTE}
            for term in first_sightings
        )
    out[UNCORROBORATED_TERMS_KEY] = sorted(
        recorded, key=lambda entry: (entry["term"], entry["code"], entry["note"])
    )
    return out


def compute_diff(claims: dict, spec: dict, exempt_terms: Collection[str] = ()) -> dict:
    """Declared (spec) vs detected (blind audit), both directions.

    Terms match by exact vocabulary id. Deceptions match by catalog
    normalization on BOTH sides (`detect_levers`), so spelling never decides a
    verdict. The two negative term findings are deliberately distinct:

      * `dead_spec_terms` — declared, and the auditor never saw it at all: the
        mechanic is not in the shipped code.
      * `unreachable_declared_mechanics` — declared, and the auditor DID see it
        but reports `reachable: false`: the code is there and play cannot get
        to it.

    `declared_deceptions_undetected` is a WARNING (a possible verifier false
    negative, human-reviewed at S5) and never rejects on its own —
    `decide_verdict` does not read it.

    `unimplemented_terms` (R-18, contract B3) is the THIRD negative term finding
    and the only one computed from the optional site inventory: a declared term
    the reply's `term_sites` does not positively ground. It is distinct from
    `dead_spec_terms` in the way a witness is distinct from a silence — a term
    can be claimed reachable and still be grounded in nothing — and the key is
    absent entirely when the reply carried no inventory.

    `exempt_terms` (default `()`, so the canon diff is unchanged) applies the
    b002 exemption ruling to those negative findings and to `undeclared_terms`:
    the named terms are moved into an `exempted` list instead, keyed to the code
    each would have produced. The function stays PURE — the config is read by
    `_exempt_terms` at the run's edge and handed in here.
    """
    game = _spec_game(spec)
    declared_terms = _declared_terms(game)
    declared_deceptions = _declared_deceptions(game)

    reachable: list[str] = []
    seen: list[str] = []
    for entry in _claim_entries(claims, "terms"):
        term = entry.get("term")
        if not isinstance(term, str) or not term.strip():
            raise ValueError(f"claims.terms entry has no usable 'term': {entry!r}")
        if term not in seen:
            seen.append(term)
        if entry.get("reachable") is True and term not in reachable:
            reachable.append(term)

    detected_deceptions: list[str] = []
    for entry in _claim_entries(claims, "deceptions"):
        lever = entry.get("lever")
        if not isinstance(lever, str) or not lever.strip():
            raise ValueError(f"claims.deceptions entry has no usable 'lever': {entry!r}")
        for keyword in detect_levers(lever):
            if keyword not in detected_deceptions:
                detected_deceptions.append(keyword)

    unreachable_declared = [
        term for term in declared_terms if term in seen and term not in reachable
    ]
    # R-18: the site inventory, diffed against `game.terms`. A declared term the
    # inventory does not POSITIVELY ground is `unimplemented`.
    #
    # The population is the DECLARED terms and nothing else, because the finding
    # is a broken promise: the spec says this game has the mechanic and the
    # blind pass can name no construct that realizes it. A term the auditor
    # could not ground and the spec never claimed is not a promise at all.
    #
    # The key is written only when the reply carried an inventory. An auditor
    # that answered the section grounds what it can and reports `site: null` for
    # the rest, so ABSENT-key and EMPTY-list mean two different things here and
    # the diff keeps them apart: no key at all means the sites were never
    # measured, which is every reply written before this section existed.
    grounded = {
        entry.get("term")
        for entry in _claim_entries(claims, TERM_SITES_KEY)
        if entry.get("site") is not None
    } if TERM_SITES_KEY in claims else None
    diff = {
        "terms_declared": list(declared_terms),
        "terms_detected_reachable": sorted(reachable),
        "dead_spec_terms": sorted(term for term in declared_terms if term not in seen),
        "undeclared_terms": sorted(
            term for term in reachable if term not in declared_terms
        ),
        "unreachable_declared_mechanics": sorted(unreachable_declared),
        "deceptions_declared": list(declared_deceptions),
        "deceptions_detected": sorted(detected_deceptions),
        "undeclared_deceptions": sorted(
            lever for lever in detected_deceptions if lever not in declared_deceptions
        ),
        "declared_deceptions_undetected": sorted(
            lever for lever in declared_deceptions if lever not in detected_deceptions
        ),
    }
    if grounded is not None:
        diff[UNIMPLEMENTED_KEY] = sorted(
            term for term in declared_terms if term not in grounded
        )
    return _apply_exemptions(diff, exempt_terms)


# --- the attribution dispute (contract Q-1) ---------------------------------


def _constructs(site: str) -> frozenset[str]:
    """The backtick-quoted code spans of one `site`, normalized for comparison.

    Whitespace is collapsed because the auditor's prose wraps mid-span, and case
    is folded because an identifier quoted at the start of a sentence is the same
    identifier. The two guards are the `_MIN_CONSTRUCT_CHARS` note's: a span must
    be long enough and lettered enough to be a construct's name, so `0` and `[]`
    never pair two unrelated terms.
    """
    spans = set()
    for raw in _CODE_SPAN_RE.findall(site):
        span = " ".join(raw.split()).casefold()
        if len(span) >= _MIN_CONSTRUCT_CHARS and any(ch.isalpha() for ch in span):
            spans.add(span)
    return frozenset(spans)


def _dispute_grounding(claims: Mapping, term: str) -> tuple[frozenset[str], frozenset[str]]:
    """(citations, constructs) — everything this audit grounded `term` in.

    BOTH claim surfaces, unioned, and the same two for either side of a pair. The
    contract's own wording is "X's claim entry and Y's witness grounding", and
    the union is the honest reading of it: a term's evidence is wherever the
    auditor put it, and which of its two entries carried a line is a fact about
    the reply's layout rather than about the code.

    Malformed evidence ITEMS are skipped rather than raised on — `validate_claims`
    is the gate for a reply's shape and it has already run by the time a report is
    assembled, so a guard here would be a second, quieter copy of that contract.
    A malformed SECTION still raises, through `_claim_entries`, exactly as
    `compute_diff` lets it.
    """
    citations: set[str] = set()
    constructs: set[str] = set()
    sections = ["terms", TERM_SITES_KEY] if TERM_SITES_KEY in claims else ["terms"]
    for section in sections:
        for entry in _claim_entries(claims, section):
            if entry.get("term") != term:
                continue
            for item in entry.get("evidence") or ():
                if not isinstance(item, Mapping):
                    continue
                path, line = item.get("path"), item.get("line")
                if isinstance(path, str) and isinstance(line, int) and not isinstance(line, bool):
                    citations.add(f"{path}:{line}")
            for ref in entry.get("frame_refs") or ():
                if isinstance(ref, str) and ref.strip():
                    citations.add(f"frame:{ref}")
            site = entry.get("site")
            if isinstance(site, str):
                constructs |= _constructs(site)
    return frozenset(citations), frozenset(constructs)


def _shared_ground(citations: Collection[str], constructs: Collection[str]) -> str | None:
    """What paired two terms, as the prose the record carries — or None.

    None IS the answer "these two are not the same behaviour", and it is the only
    thing standing between a real finding and a silenced one, so it is returned
    from exactly one place.
    """
    parts = []
    if citations:
        parts.append("both cite " + ", ".join(sorted(citations)))
    if constructs:
        parts.append("both sites name " + ", ".join(f"`{span}`" for span in sorted(constructs)))
    return "; ".join(parts) if parts else None


def _attribution_break(claims: Mapping, term: str, declared: Collection[str]) -> bool:
    """Did the auditor say WHY this term is not a declared neighbour? (Q-1 §2)

    True only for a `distinguishes` that is well-formed in BOTH halves: the shape
    `validate_claims` already enforced, AND a `term` the spec actually declares,
    which only this side of the pipeline can know.

    A `distinguishes` naming a term the spec never declared is NOT a break and is
    NOT an error either — it is silently no answer to the question that was
    asked. Raising was considered and rejected: it would discard a whole paid
    blind audit over an auditor naming a vocabulary term the spec happens not to
    carry, and the contract's rule is that a well-formed break makes a finding
    undisputed, not that a malformed one invalidates the pass. The dispute simply
    stands, and `term_disputes` records what paired it.

    FINDING-LEVEL, not pair-level: the contract reads "makes the FINDING
    undisputed regardless of evidence overlap", so one well-formed break clears X
    against every neighbour rather than against the one it names. The auditor
    that cites a separating clause has done the work the requirement asks for,
    and the live acceptance's outcome (b) — "the findings are REAL per the
    definitions, the park stands with the citations on the record" — is written
    for exactly that reply.
    """
    for entry in _claim_entries(claims, "terms"):
        if entry.get("term") != term:
            continue
        broken = entry.get(DISTINGUISHES_KEY)
        if not isinstance(broken, Mapping):
            continue
        named, clause = broken.get("term"), broken.get("clause")
        if (
            isinstance(named, str)
            and named in declared
            and isinstance(clause, str)
            and clause.strip()
        ):
            return True
    return False


def term_disputes(claims: Mapping, diff: Mapping) -> list[dict]:
    """The Q-1 pairs: one observed behaviour the audit gave two signed names.

    PURE, and a pure function of what the audit SAID — the claims and the diff
    built from them, never the config. `_term_dispute_action` reads the knob at
    the run's edge and `_apply_term_dispute_action` decides what a pair may do,
    which is the `compute_diff`/`_exempt_terms` split this module already keeps.

    Read off the diff LAST, after exemptions and both corroboration passes: a
    finding those bars already demoted has nothing left to dispute, and pairing
    it would record a dispute over a reject that was never going to happen.

    Each entry is one FINDING — `{term, code, disputed_with, shared}` — so the two
    halves of one misattribution appear as two rows of one dispute: X's
    `undeclared-term`, and Y's `dead-spec-term` when the declared neighbour is
    also one the auditor never saw under its own name. That second row exists
    because the halves must not count twice, and it is written only when a LIVE
    dispute names it: an X cleared by `_attribution_break` leaves Y's finding
    rejecting exactly as today.
    """
    declared = [term for term in _as_list(diff.get("terms_declared", []), "diff.terms_declared")
                if isinstance(term, str)]
    undeclared = [
        term for term in _as_list(diff.get("undeclared_terms", []), "diff.undeclared_terms")
        if isinstance(term, str)
    ]
    dead = frozenset(
        term for term in _as_list(diff.get("dead_spec_terms", []), "diff.dead_spec_terms")
        if isinstance(term, str)
    )
    entries: list[dict] = []
    for term in undeclared:
        if _attribution_break(claims, term, declared):
            continue
        citations, constructs = _dispute_grounding(claims, term)
        for neighbour in declared:
            if neighbour == term:
                continue
            other_citations, other_constructs = _dispute_grounding(claims, neighbour)
            shared = _shared_ground(
                citations & other_citations, constructs & other_constructs
            )
            if shared is None:
                continue
            entries.append({
                "term": term,
                "code": REJECT_UNDECLARED_TERM,
                "disputed_with": neighbour,
                "shared": shared,
            })
            if neighbour in dead:
                entries.append({
                    "term": neighbour,
                    "code": REJECT_DEAD_SPEC_TERM,
                    "disputed_with": term,
                    "shared": shared,
                })
    return sorted(entries, key=lambda entry: (entry["term"], entry["code"], entry["disputed_with"]))


# --- the verdict ------------------------------------------------------------


def _check_to_dict(check: object) -> dict:
    """A CheckResult (or an already-serialized one) as a JSON-able dict."""
    if isinstance(check, CheckResult):
        # asdict, not field-by-field: the CheckResult/Evidence shapes belong to
        # s3_static, and serializing them whole means a drift there surfaces as
        # a loud `_validate_check` key mismatch instead of a silently dropped
        # field. Evidence arrives as a tuple of dicts; the report holds lists.
        record = asdict(check)
        record["evidence"] = [dict(item) for item in record["evidence"]]
        return record
    if isinstance(check, Mapping):
        expected = ("check_id", "leg", "status", "evidence", "note")
        missing = [key for key in ("check_id", "leg", "status") if key not in check]
        extra = sorted(set(check) - set(expected))
        if missing or extra:
            raise ValueError(
                f"a check dict holds exactly {list(expected)} (evidence/note optional) — "
                f"missing {missing}, unexpected {extra}"
            )
        return {
            "check_id": check["check_id"],
            "leg": check["leg"],
            "status": check["status"],
            "evidence": [dict(item) for item in check.get("evidence", [])],
            "note": check.get("note", ""),
        }
    raise TypeError(f"expected a CheckResult or dict, got {type(check).__name__}")


def _reason(code: str, detail: str, **extra: object) -> dict:
    if code not in REJECT_CODES:
        raise ValueError(f"unknown reject code {code!r} — expected one of {list(REJECT_CODES)}")
    return {"code": code, "detail": detail, **extra}


def decide_verdict(checks: list[CheckResult], diff: dict | None) -> tuple[str, list[dict]]:
    """(verdict, reject_reasons) from the check legs and the diff.

    Reject on any of the six frozen codes; everything else passes. A check
    status of `premise-not-met`, `deferred` or `skipped` is an honest
    non-answer and NEVER rejects — only `fail` does.

    `diff=None` (dry runs, and officials, which have no spec) skips the four
    diff codes: absence of a spec is not evidence against the game.
    """
    records = [_check_to_dict(check) for check in checks]
    reasons: list[dict] = []

    for record in records:
        if record["leg"] in STATIC_LEGS and record["status"] == "fail":
            reasons.append(
                _reason(
                    REJECT_FORBIDDEN_STATIC,
                    f"{record['check_id']} failed: {record.get('note') or 'no note'}",
                    check_id=record["check_id"],
                    leg=record["leg"],
                )
            )

    if diff is not None:
        _validate_diff(diff)
        for lever in diff["undeclared_deceptions"]:
            reasons.append(
                _reason(
                    REJECT_UNDECLARED_DECEPTION,
                    f"the audit detected the {lever!r} lever; the spec declares "
                    f"{diff['deceptions_declared']}",
                    lever=lever,
                )
            )
        for term in diff["dead_spec_terms"]:
            reasons.append(
                _reason(
                    REJECT_DEAD_SPEC_TERM,
                    f"spec declares {term!r} and the blind audit found no trace of it",
                    term=term,
                )
            )
        for term in diff["undeclared_terms"]:
            reasons.append(
                _reason(
                    REJECT_UNDECLARED_TERM,
                    f"{term!r} is reachable in the code but the spec does not declare it "
                    f"(off-intent)",
                    term=term,
                )
            )
        for term in diff["unreachable_declared_mechanics"]:
            reasons.append(
                _reason(
                    REJECT_UNREACHABLE_DECLARED,
                    f"spec declares {term!r} but the audit reports it unreachable in play",
                    term=term,
                )
            )

    for record in records:
        if record["leg"] == "solver" and record["status"] == "fail":
            reasons.append(
                _reason(
                    REJECT_SOLVER_QUALITY,
                    f"{record['check_id']} failed: {record.get('note') or 'no note'}",
                    check_id=record["check_id"],
                    # architecture §3: solver-quality failures are solver-only fixes.
                    route=SOLVER_ONLY_ROUTE,
                )
            )
    return ("reject" if reasons else "pass"), reasons


def _apply_deception_action(
    verdict: str, reasons: list[dict], action: str
) -> tuple[str, list[dict], list[dict]]:
    """(verdict, reject_reasons, deception_advisories) under the L-1 ruling.

    The ONE place a lever row moves. Under `reject` this hands back its own
    inputs and an empty advisory list, so an unconfigured run's verdict and
    reasons are the bytes they always were. Under `record` every
    `undeclared-deception` row moves — the same row object, with its lever and
    its detail intact, in the order `decide_verdict` produced it — and the
    verdict is re-decided from what is LEFT: a report whose only findings are
    levers is a PASS, and a report that also carries a term finding is still a
    reject that names only the term. Nothing is dropped and nothing is rewritten.

    `decide_verdict` is deliberately NOT given this knob. It is the frozen
    `(verdict, reject_reasons)` seam this file's pins and the b002 one-go pins
    read directly, and the ruling is a policy about where a decided finding
    LANDS rather than about what the audit found — so it applies after the
    decision, at the one seam that has the run's config in hand.
    """
    if action not in DECEPTION_ACTIONS:
        raise ValueError(
            f"deception action must be one of {list(DECEPTION_ACTIONS)}, got {action!r}"
        )
    if action == DECEPTION_ACTION_REJECT:
        return verdict, reasons, []
    advisories = [row for row in reasons if row["code"] == REJECT_UNDECLARED_DECEPTION]
    kept = [row for row in reasons if row["code"] != REJECT_UNDECLARED_DECEPTION]
    return ("reject" if kept else "pass"), kept, advisories


def _apply_term_dispute_action(
    verdict: str, reasons: list[dict], disputes: Sequence[Mapping], action: str
) -> tuple[str, list[dict]]:
    """(verdict, reject_reasons) under the Q-1 ruling — `_apply_deception_action`'s shape.

    The ONE place a disputed term row leaves the reject path. Under `reject` this
    hands back its own inputs, so an unconfigured run's verdict and reasons are
    the bytes they always were. Under `record` the rows a DISPUTE names move out
    and the verdict is re-decided from what is LEFT: a report whose only findings
    are disputed attributions is a PASS, and one that also carries an undisputed
    term finding, a lever, a static fail or a solver fail is still a reject that
    names only those.

    It returns no advisory list, and that is the one place it departs from L-1's
    function: the moved rows' evidence is ALREADY in `term_disputes`, which is
    written in both modes and carries strictly more than a reason row does (the
    neighbour, and what grounded the pairing). A second copy of the same finding
    under a second key would be two records to keep in agreement.

    Only the two codes a dispute can name are eligible, matched BY TERM: an
    `undeclared-term` row whose term is a dispute's X, and a `dead-spec-term` row
    whose term is a live dispute's Y. Every other row, including a term finding on
    a term nothing disputed, is untouched — which is `decide_verdict`'s decision
    standing exactly as it was made.
    """
    if action not in TERM_DISPUTE_ACTIONS:
        raise ValueError(
            f"term dispute action must be one of {list(TERM_DISPUTE_ACTIONS)}, got {action!r}"
        )
    if action == TERM_DISPUTE_ACTION_REJECT:
        return verdict, reasons
    disputed = {(entry["term"], entry["code"]) for entry in disputes}
    kept = [
        row for row in reasons
        if row["code"] not in TERM_DISPUTE_CODES
        or (row.get("term"), row["code"]) not in disputed
    ]
    return ("reject" if kept else "pass"), kept


# --- the report -------------------------------------------------------------


def _versions() -> dict:
    return {
        "arcengine": importlib.metadata.version("arcengine"),
        "python": platform.python_version(),
    }


def _required_rows(records: Sequence[Mapping]) -> list[dict]:
    """The eight `required.rowN` results, as {row, check_id, status}, in order."""
    rows: list[dict] = []
    seen: set[int] = set()
    for record in records:
        match = REQUIRED_ROW_RE.match(record["check_id"])
        if match is None:
            continue
        row = int(match.group(1))
        if row in seen:
            raise ValueError(f"two results for required.row{row} — the rows are one-per-row")
        seen.add(row)
        rows.append({"row": row, "check_id": record["check_id"], "status": record["status"]})
    return sorted(rows, key=lambda entry: entry["row"])


def assemble_report(
    *,
    game_id: str,
    worker: Path,
    mode: str,
    cfg: Mapping,
    cap: FrameCapture,
    checks: Sequence,
    frames_path: Path,
    agent: dict | None = None,
    diff: dict | None = None,
    spec_hash: str | None = None,
    spec_path: Path | None = None,
) -> dict:
    """Build the frozen `b7.1` report. The verdict is decided HERE, once.

    `frames_path` is recorded as its file name: the frames file is always
    written next to the report, so a bare name is unambiguous and survives the
    directory being moved.

    `spec_path` is the R-09 look-alike detector's declared side and defaults to
    `spec.yaml` beside the worker — architecture §2's tree, and the path both
    callers already use (`s3_verify.main`'s `--spec`, the orchestrator's
    `spec_dir / "spec.yaml"`). Absent or unreadable is an honest
    `premise-not-met` in the detector, never a refusal.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {list(MODES)}, got {mode!r}")
    checks = list(checks)
    records = [_check_to_dict(check) for check in checks]
    # Contract L-1's knob, read HERE and unconditionally — before a diff is
    # validated, before the history files are touched, and on a dry run too.
    # The other verifier knobs are read inside the `diff is not None` block
    # because each of them reads or writes something only a full run has; this
    # one governs a list this stage writes on EVERY report, and a malformed
    # value must stop the stage rather than quietly reject the game it was set
    # to be lenient with.
    deception_action = _deception_action(cfg)
    # Contract Q-1's knob, read at the SAME seam and unconditionally, for every
    # reason the line above gives: a malformed value must stop the stage rather
    # than quietly reject the game it was set to be lenient with, and it must do
    # so before a history file is touched.
    term_dispute_action = _term_dispute_action(cfg)
    # Set by the corroboration pass below and recorded in the report only when
    # that pass actually ran (`OPTIONAL_REPORT_KEYS`).
    corroborate = False
    lever_window: int | None = None
    term_corroborate = False
    term_window: int | None = None
    # The one place the run's CONFIG and its diff are both in hand, so the b002
    # exemption ruling is asserted here rather than at each caller: this
    # module's CLI and the orchestrator's S2b leg both build their diff with
    # `compute_diff` and both land here, and `_apply_exemptions` is idempotent,
    # so a caller that already passed the terms to `compute_diff` gets the same
    # bytes. An absent knob returns the diff object itself, unchanged.
    if diff is not None:
        diff = _apply_exemptions(diff, _exempt_terms(cfg))
        # …and the same seam carries the corroboration ruling, for the same
        # reason: this is where the run's CONFIG, its diff and the WORKER the
        # history belongs to are all in hand. A diff exists only for a full
        # worker run — a dry run and an official (no spec, hence no diff) never
        # reach this block, which is also what keeps the sidecar out of the
        # read-only officials corpus (D25).
        #
        # Order is load-bearing and frozen: validate, read the history, THEN
        # append this round. A round may not corroborate its own finding, and a
        # diff that does not validate never records a round it would then be
        # judged against. The knob is read first so a bad one fails before any
        # file is touched; the history is recorded either way, so a later
        # knob-on run has real rounds behind it. The WINDOW is read at the same
        # seam and for the same reason, and unconditionally: a window set
        # against a corroboration pass that is not running is a contradiction
        # this stage refuses to run past, knob on or off.
        _validate_diff(diff)
        corroborate = _lever_corroboration(cfg)
        lever_window = _lever_window(cfg)
        # Both corroboration passes' knobs are read HERE, before either pass
        # touches a file: "the knob is read first so a bad one fails before any
        # file is touched" is a promise about the RUN, not about one pass, and a
        # bad term knob must not leave a lever round already recorded on disk.
        term_corroborate = _term_corroboration(cfg)
        term_window = _term_window(cfg)
        history_path = lever_history_path(Path(worker))
        earlier = (
            corroborated_levers(read_lever_history(history_path), lever_window)
            if corroborate
            else None
        )
        append_lever_history(history_path, diff["deceptions_detected"])
        diff = _apply_corroboration(diff, earlier)
        # …and the TERM pass (contract C-3) beside it, the same frozen order for
        # the same reasons: read the history, append THIS round's three
        # direction lists, then apply. The lists are read off the diff after
        # exemptions and before this demotion — an exempt term never reaches the
        # record at all, and a round may not corroborate its own finding.
        # `_apply_corroboration` above only ever touches
        # `undeclared_deceptions`, so what is recorded here is what the audit
        # found either way.
        term_path = term_history_path(Path(worker))
        earlier_terms = (
            corroborated_terms(read_term_history(term_path), term_window)
            if term_corroborate
            else None
        )
        append_term_history(
            term_path,
            diff["dead_spec_terms"],
            diff["undeclared_terms"],
            diff["unreachable_declared_mechanics"],
            # R-18's direction, recorded only when this round measured it. The
            # `.get` is what keeps a round whose reply carried no site inventory
            # writing the entry it wrote before this contract, byte for byte.
            diff.get(UNIMPLEMENTED_KEY),
        )
        diff = _apply_term_corroboration(diff, earlier_terms)
    # …and R-09 at the SAME seam, for the same reason the two passes above give:
    # this is where the run's CONFIG and the WORKER are both in hand. Gated on
    # `diff is not None` exactly as they are, which is what keeps it off the
    # read-only officials corpus and out of dry runs by construction — an
    # official has no spec, so it has no declared side to be verified against.
    #
    # The detector is BEST-EFFORT about its worker: `lookalike_report`
    # answers `premise-not-met` for anything that is not a generated worker dir
    # or whose engine probe will not run, so a caller that passes a path with no
    # game.py beside it (every fabricated report in the suite) gets no block and
    # no exception. `fail` is the only mode that reaches `decide_verdict`, and it
    # does so as an ordinary failing `static` check — no new reject code.
    lookalikes: dict | None = None
    if diff is not None:
        mode_lookalike = _lookalike_mode(cfg)
        spec_for_lookalikes = (
            Path(spec_path) if spec_path is not None else Path(worker).parent / "spec.yaml"
        )
        found = lookalike_report(Path(worker), spec_for_lookalikes, mode=mode_lookalike)
        if found is not None and found.result.status != "premise-not-met":
            lookalikes = {
                LOOKALIKE_UNDECLARED_KEY: list(found.undeclared_found),
                LOOKALIKE_UNGROUNDED_KEY: list(found.declared_ungrounded),
            }
            if mode_lookalike == "fail":
                checks.append(found.result)
                records.append(_check_to_dict(found.result))
    # …and R-08's §6 check at the SAME seam, gated on `diff is not None` for the
    # same three reasons: the run's CONFIG and the WORKER are both in hand here,
    # the officials' read-only corpus is kept out by construction, and the blind
    # session has already closed so nothing this reads can reach it.
    #
    # Unlike the look-alike block this one is recorded as an ordinary CHECK ROW
    # rather than a new optional report key, and the difference is in what each
    # answer is: A3's is a two-directional inventory that a findings feed reads
    # field by field, while §6's is one verdict with its evidence attached —
    # which is exactly what a `CheckResult` is, and `deferred` is already this
    # pipeline's word for "measured, recorded, never rejects"
    # (`s3_gate._check_loc` sets the precedent). A `premise-not-met` answer adds
    # NO row at all, which is what keeps every fabricated report in the suite —
    # no game.py, so not a generated worker — byte-identical.
    if diff is not None:
        honest = refusal_honest_report(Path(worker), mode=_refusal_honest_mode(cfg))
        if honest is not None and honest.result.status != "premise-not-met":
            checks.append(honest.result)
            records.append(_check_to_dict(honest.result))
    # R-18's inventory, lifted out of the claims onto the report's own surface.
    # Read from `agent` rather than recomputed: the claims ARE the inventory,
    # and a second derivation could disagree with the one `compute_diff` used.
    sites = term_sites_block(agent.get("claims") if isinstance(agent, Mapping) else None)
    # Contract Q-1's pairing, read from the same `agent` the inventory above is
    # and from the FINAL diff — after exemptions and after both corroboration
    # passes, which is the order `term_disputes` documents: a finding those bars
    # already demoted has nothing left to dispute.
    #
    # `None` is "not computable" and is the only thing that keeps the key off a
    # report: a dry run (no agent, no diff) and an official (no spec, hence no
    # diff) have no declared side for a dispute to be about. Everything else
    # writes the key in BOTH knob modes, `[]` included — the
    # `deception_advisories` promise, for the same reason.
    claims_for_disputes = agent.get("claims") if isinstance(agent, Mapping) else None
    disputes: list[dict] | None = None
    if diff is not None and isinstance(claims_for_disputes, Mapping):
        disputes = term_disputes(claims_for_disputes, diff)
    verdict, reasons = decide_verdict(list(checks), diff)
    # …and the L-1 ruling applied to that decision, at the one seam that has the
    # run's config in hand. Under the default this returns the verdict and the
    # reasons it was handed, so the report below is byte for byte the one this
    # stage wrote before the contract — plus an empty advisory list.
    verdict, reasons, advisories = _apply_deception_action(verdict, reasons, deception_action)
    # …and Q-1's ruling after it, at the same seam and in this order deliberately:
    # the two knobs govern disjoint reject codes, so neither can hide the other's
    # finding, and running the term pass second means the PASS it may produce is
    # decided from what both rulings left standing. Under the default this is the
    # identity on both values it is handed.
    verdict, reasons = _apply_term_dispute_action(
        verdict, reasons, disputes or (), term_dispute_action
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "game_id": game_id,
        "worker": str(Path(worker).resolve()),
        "mode": mode,
        # Which corroboration window decided this round's lever findings, beside
        # the run's mode because it is run metadata, not diff data (the diff's
        # `uncorroborated_levers` bookkeeping keeps its exact shape). Written
        # ONLY when the corroboration pass ran: `N` for a windowed run, null for
        # the unwindowed any-prior-round union, and no key at all for a run on
        # the canon default — that run's report is byte for byte the one it was.
        **({LEVER_WINDOW_REPORT_KEY: lever_window} if corroborate else {}),
        # The term pass's own window, on exactly the same terms: `N`, null for
        # the unwindowed union, and no key at all when the pass did not run.
        **({TERM_WINDOW_REPORT_KEY: term_window} if term_corroborate else {}),
        # R-09's both-direction record, written ONLY when the detector actually
        # reached a verdict on this worker — the `confirmed_session` rule ("it
        # appears only when it was earned"), and for the same reason: a report
        # whose detector could not run must not carry a block that reads as
        # "looked, found nothing". A clean generated game DOES carry the block
        # with two empty lists, which is the positive record an evidence pass
        # exists to leave.
        **({LOOKALIKES_KEY: lookalikes} if lookalikes is not None else {}),
        # R-18's site inventory, on exactly the same terms: written ONLY when
        # the blind reply carried one, so a report written from a pre-B3 reply
        # carries no key and reads as the report it always was.
        **({TERM_SITES_KEY: sites} if sites is not None else {}),
        # Q-1's pairs, written whenever they were COMPUTABLE rather than whenever
        # they were found: an EMPTY list is the positive record "this audit named
        # one behaviour once", which is the answer a reader of a reject most
        # needs and the one an absent key cannot give.
        **({TERM_DISPUTES_KEY: disputes} if disputes is not None else {}),
        "canon": {"docs_root": str(cfg["duckwm_docs"]), "spec_hash": spec_hash},
        "frames": {
            "source": cap.source,
            "count": len(cap.records),
            "levels_completed": cap.levels_completed,
            "win": bool(cap.win),
            "path": Path(frames_path).name,
        },
        "checks": records,
        "required_rows": _required_rows(records),
        "agent": agent,
        "diff": diff,
        "verdict": verdict,
        "reject_reasons": reasons,
        # Contract L-1, beside the reasons because it is the same evidence under
        # a different policy. Written in BOTH modes — `[]` under the default —
        # so a reader never has to know the batch's knob to read the answer.
        ADVISORIES_KEY: advisories,
        "versions": _versions(),
    }
    validate_report(report)
    return report


def _require_str_list(value: object, where: str) -> None:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return
    raise ValueError(f"{where} must be a list of strings, got {value!r}")


def _validate_diff(diff: object, where: str = "diff") -> None:
    """The frozen diff shape, plus the OPTIONAL knob records.

    `exempted`, `uncorroborated_levers` and `uncorroborated_terms` are data
    additions inside the diff, not a schema-version bump: each appears only when
    its knob is set, so a diff built with the canon defaults still carries
    exactly `DIFF_KEYS` and every b7.1 report written before these knobs existed
    still validates.
    """
    _as_mapping(diff, where)
    # `unimplemented_terms` (R-18) joins the optional set rather than `DIFF_KEYS`
    # for the reason the three records above are optional: it appears only when
    # the round's reply carried a site inventory, so a diff built from a reply
    # without one still carries exactly `DIFF_KEYS` and every b7.1 report written
    # before this contract still validates. It is a list of terms, not a record
    # of suppressions, so it is checked as one.
    optional = {
        EXEMPTED_KEY, UNCORROBORATED_KEY, UNCORROBORATED_TERMS_KEY, UNIMPLEMENTED_KEY,
    }
    missing = [key for key in DIFF_KEYS if key not in diff]
    extra = sorted(set(diff) - set(DIFF_KEYS) - optional)
    if missing or extra:
        raise ValueError(
            f"{where} must have exactly the keys {list(DIFF_KEYS)} (plus the optional "
            f"{sorted(optional)} records) — missing {missing}, unexpected {extra}"
        )
    for key in DIFF_KEYS:
        _require_str_list(diff[key], f"{where}.{key}")
    if UNIMPLEMENTED_KEY in diff:
        _require_str_list(diff[UNIMPLEMENTED_KEY], f"{where}.{UNIMPLEMENTED_KEY}")
    if EXEMPTED_KEY in diff:
        _validate_exempted(diff[EXEMPTED_KEY], f"{where}.{EXEMPTED_KEY}")
    if UNCORROBORATED_KEY in diff:
        _validate_uncorroborated(diff[UNCORROBORATED_KEY], f"{where}.{UNCORROBORATED_KEY}")
    if UNCORROBORATED_TERMS_KEY in diff:
        _validate_uncorroborated_terms(
            diff[UNCORROBORATED_TERMS_KEY], f"{where}.{UNCORROBORATED_TERMS_KEY}"
        )


def _validate_exempted(entries: object, where: str) -> None:
    """Each suppressed finding: exactly {term, would_have_been}, both known.

    `would_have_been` is pinned to the three exemptable reject codes — a record
    naming a code the knob cannot suppress would misreport what was dropped,
    and the whole point of the list is that nothing is dropped silently.
    """
    codes = [code for _key, code in EXEMPTABLE_FINDINGS]
    for position, entry in enumerate(_as_list(entries, where)):
        spot = f"{where}[{position}]"
        _as_mapping(entry, spot)
        if set(entry) != set(EXEMPTED_ENTRY_KEYS):
            raise ValueError(
                f"{spot} must have exactly the keys {list(EXEMPTED_ENTRY_KEYS)}, got "
                f"{sorted(entry)}"
            )
        _as_text(entry["term"], f"{spot}.term")
        if entry["would_have_been"] not in codes:
            raise ValueError(
                f"{spot}.would_have_been must be one of {codes}, got "
                f"{entry['would_have_been']!r}"
            )


def _validate_uncorroborated(entries: object, where: str) -> None:
    """Each demoted finding: exactly {lever, note}, the lever a catalog spelling.

    The lever is pinned to the catalog for the reason `_validate_exempted` pins
    its reject code — the whole point of the list is that nothing is dropped, and
    a record naming a lever the diff never carried would misreport what stopped
    rejecting.

    E-1's COMPATIBILITY CALL, and it is ALIAS-SET ACCEPTANCE rather than
    fold-then-check: the gate is `s1_spec.canonical_lever`, which is exact
    membership of the catalog's own spellings modulo case and separators. Every
    shipped report keeps validating — 2 of the 5 shipped uncorroborated
    records name a pre-E-1 spelling (both "false tell"; LEAD CORRECTION
    2026-10-05: the earlier "7 of 12" figure was the SPEC-side count — 7
    knobs.deceptions entries across the corpus use historic spellings —
    with an irreproducible denominator, per the blind lane's census), and
    a validator that only took today's five keywords would retroactively
    invalidate them. Folding the
    name first and checking the result would have accepted those too, but it
    would also have accepted any prose CONTAINING a keyword ("the decoy thing
    is fine"), which is looser than the exact-membership bar this check has
    always applied. New records carry canonical keywords, because `detect_levers`
    only ever returns those.
    """
    for position, entry in enumerate(_as_list(entries, where)):
        spot = f"{where}[{position}]"
        _as_mapping(entry, spot)
        if set(entry) != set(UNCORROBORATED_ENTRY_KEYS):
            raise ValueError(
                f"{spot} must have exactly the keys {list(UNCORROBORATED_ENTRY_KEYS)}, got "
                f"{sorted(entry)}"
            )
        _as_text(entry["note"], f"{spot}.note")
        if canonical_lever(_as_text(entry["lever"], f"{spot}.lever")) is None:
            raise ValueError(
                f"{spot}.lever must be one of the catalog keywords "
                f"{list(DECEPTION_CATALOG)} or a spelling that folds onto one "
                f"({sorted(_LEVER_ALIASES)}), got {entry['lever']!r}"
            )


def _validate_uncorroborated_terms(entries: object, where: str) -> None:
    """Each demoted term finding: exactly {term, code, note}, the code known.

    `code` is pinned to the three TERM reject codes for the reason
    `_validate_exempted` pins `would_have_been` — the whole point of the list is
    that nothing is dropped silently, and a record naming a code this pass
    cannot demote would misreport what stopped rejecting. The term itself is
    only required to be non-empty text, the same bar `exempted` sets: the
    vocabulary is checked where terms enter the diff, not again here.
    """
    codes = [code for _direction, _key, code in TERM_DIRECTIONS]
    for position, entry in enumerate(_as_list(entries, where)):
        spot = f"{where}[{position}]"
        _as_mapping(entry, spot)
        if set(entry) != set(UNCORROBORATED_TERM_ENTRY_KEYS):
            raise ValueError(
                f"{spot} must have exactly the keys {list(UNCORROBORATED_TERM_ENTRY_KEYS)}, "
                f"got {sorted(entry)}"
            )
        _as_text(entry["term"], f"{spot}.term")
        _as_text(entry["note"], f"{spot}.note")
        if entry["code"] not in codes:
            raise ValueError(f"{spot}.code must be one of {codes}, got {entry['code']!r}")


def _validate_agent(agent: object) -> None:
    _as_mapping(agent, "report.agent (null or a mapping)")
    missing = [key for key in AGENT_KEYS if key not in agent]
    extra = sorted(set(agent) - set(AGENT_KEYS))
    if missing or extra:
        raise ValueError(
            f"report.agent must have exactly the keys {list(AGENT_KEYS)} — missing {missing}, "
            f"unexpected {extra}"
        )
    # session_id and model stay nullable on purpose: `backends._codex_session_id`
    # returns None rather than inventing a resume handle, and `model_reported` is
    # None whenever the CLI did not name exactly one model. A fabricated string
    # would be worse than a null.
    for key in ("session_id", "model"):
        if agent[key] is not None and not isinstance(agent[key], str):
            raise ValueError(f"report.agent.{key} must be null or a string, got {agent[key]!r}")
    # Same rule for the ledger fields: None is the CLI's honest "not reported",
    # never estimated (backends.SessionResult).
    if agent["usd"] is not None:
        _require(agent["usd"], (int, float), "report.agent.usd")
    for key in ("tokens_in", "tokens_out"):
        if agent[key] is not None:
            _require(agent[key], int, f"report.agent.{key}")
    _require(agent["wall_s"], (int, float), "report.agent.wall_s")
    if agent["staged_copy_verified"] is not True:
        raise ValueError(
            "report.agent.staged_copy_verified must be true — a report is only written "
            "after `assert_unchanged` proved the blind copy intact"
        )
    validate_claims(agent["claims"])


def validate_report(report: dict) -> None:
    """Fail loud unless `report` is the frozen `b7.1` shape (hand-rolled).

    Enforces the exact top-level key set (plus `OPTIONAL_REPORT_KEYS`, present
    only when the run opted into the knob that writes them), the type and enum
    of every field, the nested shapes of canon/frames/checks/required_rows/
    agent/diff/versions, and three invariants the schema alone cannot state: a
    dry run carries no agent, no diff and no spec hash; a `reject` has reasons
    and a `pass` has none; every reason's code is one of the six frozen ones.
    """
    if not isinstance(report, Mapping):
        raise TypeError(f"report must be a mapping, got {type(report).__name__}")
    missing = [key for key in REPORT_KEYS if key not in report]
    extra = sorted(set(report) - set(REPORT_KEYS) - set(OPTIONAL_REPORT_KEYS))
    if missing or extra:
        raise ValueError(
            f"report must have exactly the keys {list(REPORT_KEYS)} (plus the optional "
            f"{list(OPTIONAL_REPORT_KEYS)} records) — missing {missing}, "
            f"unexpected {extra}"
        )
    # Two of the optional keys are corroboration windows (`lever_window`,
    # `term_window`) and carry the same values for the same reason, so they are
    # checked in one loop — over `OPTIONAL_WINDOW_KEYS`, never over every
    # optional key, because an optional key that is NOT a window gets its own
    # branch (as `confirmed_session` does just below).
    for key in OPTIONAL_WINDOW_KEYS:
        if key not in report:
            continue
        window = report[key]
        if window is not None and (
            isinstance(window, bool) or not isinstance(window, int) or window < 1
        ):
            raise ValueError(
                f"report.{key} must be a positive int or null (the "
                f"unwindowed union over every prior round), got {window!r}"
            )
    # The confirmation round's record of round 1 (contract C-4a): a session id,
    # so a non-empty string. NOT nullable, unlike `agent.session_id` — there a
    # null is the CLI's honest "no resume handle", here the key exists only
    # because a first round was confirmed, and a confirmation whose first
    # session cannot be named is a record of nothing.
    if CONFIRMED_SESSION_KEY in report:
        _as_text(report[CONFIRMED_SESSION_KEY], f"report.{CONFIRMED_SESSION_KEY}")
    # R-09's block: exactly the two direction lists, both lists of strings. The
    # second optional key that is not a window, and it gets its own branch for
    # the reason the note above states.
    if LOOKALIKES_KEY in report:
        where = f"report.{LOOKALIKES_KEY}"
        block = _as_mapping(report[LOOKALIKES_KEY], where)
        if set(block) != set(LOOKALIKES_BLOCK_KEYS):
            raise ValueError(
                f"{where} must have exactly the keys {list(LOOKALIKES_BLOCK_KEYS)} — the "
                f"two directions spec §10 requires deception to be verified in; got "
                f"{sorted(block)}"
            )
        for key in LOOKALIKES_BLOCK_KEYS:
            _require_str_list(block[key], f"{where}.{key}")
    # R-18's inventory: term -> the site prose, or null for an absence. A
    # MAPPING, not the claims' list of entries, because that is what every
    # reader of it asks ("what did the audit ground `gate.plate` in?") and
    # because a mapping cannot carry the same term twice — `validate_claims`
    # refuses a duplicate on the way in and the shape refuses it again here.
    if TERM_SITES_KEY in report:
        where = f"report.{TERM_SITES_KEY}"
        block = _as_mapping(report[TERM_SITES_KEY], where)
        for term in sorted(block):
            _as_text(term, f"{where} key")
            site = block[term]
            if site is not None:
                _as_text(site, f"{where}[{term!r}]")
    # L-1's advisories: the SAME rows `reject_reasons` carries, so the same
    # shape — and pinned to the ONE code the ruling moves. A row here under any
    # other code would be a reject that went missing, which is the only way this
    # key could ever be worse than the behaviour it replaced.
    if ADVISORIES_KEY in report:
        advisories = _as_list(report[ADVISORIES_KEY], f"report.{ADVISORIES_KEY}")
        for position, advisory in enumerate(advisories):
            where = f"report.{ADVISORIES_KEY}[{position}]"
            _as_mapping(advisory, where)
            if advisory.get("code") != REJECT_UNDECLARED_DECEPTION:
                raise ValueError(
                    f"{where}.code must be {REJECT_UNDECLARED_DECEPTION!r} — contract L-1 "
                    f"records that one finding class as an advisory and every other code "
                    f"still rejects; got {advisory.get('code')!r}"
                )
            _require(advisory.get("detail"), str, f"{where}.detail")
    # Q-1's pairs: exactly `{term, code, disputed_with, shared}`, the code one of
    # the two a dispute can name. The sixth optional key and the fifth with its
    # own branch, pinned the way `_validate_exempted` and
    # `_validate_uncorroborated_terms` pin theirs — a row naming a code this
    # ruling cannot move would misreport what stopped rejecting, and the whole
    # point of the record is that nothing is dropped silently.
    if TERM_DISPUTES_KEY in report:
        for position, entry in enumerate(
            _as_list(report[TERM_DISPUTES_KEY], f"report.{TERM_DISPUTES_KEY}")
        ):
            where = f"report.{TERM_DISPUTES_KEY}[{position}]"
            _as_mapping(entry, where)
            if set(entry) != set(TERM_DISPUTE_ENTRY_KEYS):
                raise ValueError(
                    f"{where} must have exactly the keys {list(TERM_DISPUTE_ENTRY_KEYS)}, "
                    f"got {sorted(entry)}"
                )
            for key in ("term", "disputed_with", "shared"):
                _as_text(entry[key], f"{where}.{key}")
            if entry["code"] not in TERM_DISPUTE_CODES:
                raise ValueError(
                    f"{where}.code must be one of {list(TERM_DISPUTE_CODES)} — contract Q-1 "
                    f"records the two halves of ONE misattribution and every other code "
                    f"still rejects; got {entry['code']!r}"
                )
            if entry["term"] == entry["disputed_with"]:
                raise ValueError(
                    f"{where} disputes {entry['term']!r} with itself — a dispute is two "
                    f"names for one behaviour, so the two names must differ"
                )
    if report["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            f"report.schema_version must be {SCHEMA_VERSION!r}, got {report['schema_version']!r}"
        )
    for key in ("game_id", "worker"):
        _as_text(report[key], f"report.{key}")
    if report["mode"] not in MODES:
        raise ValueError(f"report.mode must be one of {list(MODES)}, got {report['mode']!r}")

    canon = report["canon"]
    if not isinstance(canon, Mapping) or set(canon) != {"docs_root", "spec_hash"}:
        raise ValueError(f"report.canon must be {{docs_root, spec_hash}}, got {canon!r}")
    _require(canon["docs_root"], str, "report.canon.docs_root")
    if canon["spec_hash"] is not None and not isinstance(canon["spec_hash"], str):
        raise ValueError(f"report.canon.spec_hash must be null or a string, got {canon!r}")

    frames = report["frames"]
    expected_frames = {"source", "count", "levels_completed", "win", "path"}
    if not isinstance(frames, Mapping) or set(frames) != expected_frames:
        raise ValueError(f"report.frames must be {sorted(expected_frames)}, got {frames!r}")
    if frames["source"] not in FRAME_SOURCES:
        raise ValueError(
            f"report.frames.source must be one of {list(FRAME_SOURCES)}, got {frames['source']!r}"
        )
    for key in ("count", "levels_completed"):
        _require(frames[key], int, f"report.frames.{key}")
        if frames[key] < 0:
            raise ValueError(f"report.frames.{key} must be >= 0, got {frames[key]}")
    _require(frames["win"], bool, "report.frames.win")
    _require(frames["path"], str, "report.frames.path")

    for position, check in enumerate(_as_list(report["checks"], "report.checks")):
        _validate_check(check, f"report.checks[{position}]")

    rows = _as_list(report["required_rows"], "report.required_rows")
    if len(rows) > REQUIRED_ROW_COUNT:
        raise ValueError(
            f"report.required_rows holds {len(rows)} entries; spec §2 has "
            f"{REQUIRED_ROW_COUNT} REQUIRED rows"
        )
    for position, row in enumerate(rows):
        _validate_required_row(row, f"report.required_rows[{position}]")

    if report["agent"] is not None:
        _validate_agent(report["agent"])
    if report["diff"] is not None:
        _validate_diff(report["diff"], "report.diff")

    if report["verdict"] not in VERDICTS:
        raise ValueError(
            f"report.verdict must be one of {list(VERDICTS)}, got {report['verdict']!r}"
        )
    reasons = _as_list(report["reject_reasons"], "report.reject_reasons")
    for position, reason in enumerate(reasons):
        where = f"report.reject_reasons[{position}]"
        _as_mapping(reason, where)
        if reason.get("code") not in REJECT_CODES:
            raise ValueError(
                f"{where}.code must be one of {list(REJECT_CODES)}, got {reason.get('code')!r}"
            )
        _require(reason.get("detail"), str, f"{where}.detail")
        if reason["code"] == REJECT_SOLVER_QUALITY and reason.get("route") != SOLVER_ONLY_ROUTE:
            raise ValueError(
                f"{where} is a {REJECT_SOLVER_QUALITY} reason and must carry "
                f"route={SOLVER_ONLY_ROUTE!r} (architecture §3 failure routing)"
            )
    if (report["verdict"] == "reject") != bool(reasons):
        raise ValueError(
            f"report.verdict {report['verdict']!r} disagrees with {len(reasons)} reject "
            f"reason(s) — a reject states why and a pass states nothing"
        )

    versions = report["versions"]
    if not isinstance(versions, Mapping) or set(versions) != {"arcengine", "python"}:
        raise ValueError(f"report.versions must be {{arcengine, python}}, got {versions!r}")
    for key in ("arcengine", "python"):
        _require(versions[key], str, f"report.versions.{key}")

    if report["mode"] == "dry-run":
        for key, value in (
            ("agent", report["agent"]),
            ("diff", report["diff"]),
            ("canon.spec_hash", canon["spec_hash"]),
        ):
            if value is not None:
                raise ValueError(f"report.{key} must be null in dry-run mode, got {value!r}")


def _validate_check(check: object, where: str) -> None:
    expected = {"check_id", "leg", "status", "evidence", "note"}
    if not isinstance(check, Mapping) or set(check) != expected:
        raise ValueError(f"{where} must have exactly the keys {sorted(expected)}, got {check!r}")
    _require(check["check_id"], str, f"{where}.check_id")
    if check["leg"] not in CHECK_LEGS:
        raise ValueError(f"{where}.leg must be one of {list(CHECK_LEGS)}, got {check['leg']!r}")
    if check["status"] not in CHECK_STATUSES:
        raise ValueError(
            f"{where}.status must be one of {list(CHECK_STATUSES)}, got {check['status']!r}"
        )
    _require(check["note"], str, f"{where}.note")
    for position, item in enumerate(_as_list(check["evidence"], f"{where}.evidence")):
        _as_mapping(item, f"{where}.evidence[{position}]")


def _validate_required_row(row: object, where: str) -> None:
    expected = {"row", "check_id", "status"}
    if not isinstance(row, Mapping) or set(row) != expected:
        raise ValueError(f"{where} must have exactly the keys {sorted(expected)}, got {row!r}")
    _require(row["row"], int, f"{where}.row")
    if not 1 <= row["row"] <= REQUIRED_ROW_COUNT:
        raise ValueError(f"{where}.row must be 1-{REQUIRED_ROW_COUNT}, got {row['row']}")
    if row["check_id"] != f"required.row{row['row']}":
        raise ValueError(
            f"{where}.check_id {row['check_id']!r} does not match row {row['row']}"
        )
    if row["status"] not in CHECK_STATUSES:
        raise ValueError(
            f"{where}.status must be one of {list(CHECK_STATUSES)}, got {row['status']!r}"
        )


def write_report(report: dict, path: Path) -> None:
    """Validate, then write. An invalid report is never persisted."""
    validate_report(report)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


# --- the blind agent pass ---------------------------------------------------


def _session_record(returned: object) -> dict:
    """What a session returned, as a dict (SessionResult, a fake, or a record)."""
    if isinstance(returned, Mapping):
        return dict(returned)
    to_record = getattr(returned, "to_record", None)
    if callable(to_record):
        record = to_record()
        if not isinstance(record, dict):
            raise TypeError(
                f"{type(returned).__name__}.to_record() returned "
                f"{type(record).__name__}, expected dict"
            )
        return record
    raise TypeError(
        f"verifier session returned {type(returned).__name__}; expected a dict or an "
        f"object with .to_record()"
    )


def _number_or_none(value: object) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _summed(records: Sequence[Mapping], key: str) -> float | int | None:
    """`key` totalled over the turns that reported a number; None when none did.

    A pass can cost more than one turn (the corrective retry below), and the
    report's `agent` block is the bill for the pass. Same None-tolerance as
    `_number_or_none`: a turn that reported nothing usable is not a zero.
    """
    reported = [
        value for value in (_number_or_none(record.get(key)) for record in records)
        if value is not None
    ]
    return sum(reported) if reported else None


def _last_reported(records: Sequence[Mapping], *keys: str) -> object | None:
    """The newest turn's value for the first of `keys` it actually carries."""
    for record in reversed(records):
        for key in keys:
            value = record.get(key)
            if value:
                return value
    return None


def run_agent_pass(
    cfg: Mapping,
    worker_dir: Path,
    cap: FrameCapture,
    *,
    out_dir: Path,
    driver: object | None = None,
) -> dict:
    """One blind session over a staged copy -> the report's `agent` block.

    The policy, in one line and in this order — stage the copy, build the
    prompt from it, then:

        driver.session(prompt, cwd=<staged copy>, model=<backends.<driver>.
                       models.verifier>, tools=("Read","Glob","Grep"),
                       allowed_tools=("Read","Glob","Grep"))

    and afterwards `assert_unchanged` on the copy. `driver` is an injection
    seam for tests; None resolves the configured `verifier` driver and model
    through `backends.get_driver`.

    A reply that fails the mechanical gates (no text, no parsable json block,
    claims that break the contract) buys ONE corrective turn — `REPLY_RETRY_PROMPT`
    resumed on the SAME session, the copy re-proven unchanged afterwards, and a
    second failure raises as the first would have. The returned block bills the
    pass, not the turn: the numbers are summed over every turn that reported
    them, and the key set is the frozen `AGENT_KEYS`.
    """
    worker_dir = Path(worker_dir).resolve()
    out_dir = Path(out_dir)
    staged = out_dir / (worker_dir.name + STAGED_SUFFIX)
    tree_hash = stage_worker_copy(worker_dir, staged)
    prompt = build_verifier_prompt(cfg, cap, staged)

    model: str | None = None
    if driver is None:
        driver, model = get_driver(cfg, "verifier")
    else:
        backends = cfg.get("backends")
        if isinstance(backends, Mapping):
            block = backends.get(getattr(driver, "name", ""), {})
            models = block.get("models", {}) if isinstance(block, Mapping) else {}
            model = models.get("verifier") if isinstance(models, Mapping) else None

    kwargs: dict = {"cwd": staged, "model": model}
    # The session ceiling is the DRIVER policy's, not the code default: the
    # first live verifier round under the wave-3 brief outgrew the hardcoded
    # 1800s and crashed the orchestrator (b004 finding #2, 2026-09-28). Only
    # timeout_s is taken from the policy — the verifier keeps its OWN read-only
    # tool scoping below and must never inherit S2's edit-mode policy keys.
    from .backends import get_session_policy

    driver_name = getattr(driver, "name", None)
    if driver_name in ("localclaude", "codex"):
        kwargs["timeout_s"] = get_session_policy(cfg, driver_name)["timeout_s"]
    if getattr(driver, "name", None) == "codex":
        # codex `session()` takes no tool list; read-only is its equivalent of
        # the Read/Glob/Grep scoping below, and is never taken from config.
        kwargs["sandbox"] = CODEX_READ_ONLY_SANDBOX
    else:
        kwargs["tools"] = VERIFIER_TOOLS
        kwargs["allowed_tools"] = VERIFIER_TOOLS
    returned = driver.session(prompt, **kwargs)
    records: list[Mapping] = [_session_record(returned)]

    # The proof, not the assumption: read-only tools are a request, the hash is
    # a fact. Raises RuntimeError on any drift.
    assert_unchanged(staged, tree_hash)

    vocab = set(load_vocab(cfg))
    frame_labels = tuple(frame.label for frame in cap.records)

    def parse_claims(record: Mapping) -> dict:
        """The three mechanical gates on one reply. Every failure is a ValueError."""
        text = record.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(
                f"verifier session returned no text (session_id={record.get('session_id')!r})"
            )
        claims = extract_claims(text)
        validate_claims(claims, vocab, frame_labels)
        return claims

    try:
        claims = parse_claims(records[0])
    except ValueError as first:
        resume = records[0].get("session_id")
        if not resume:
            # No handle, no retry: a corrective prompt opening a FRESH
            # conversation would name a reply that session never made.
            raise
        print(
            f"[s3] malformed reply; one corrective retry "
            f"({' '.join(str(first).split())[:RETRY_EXCERPT_CHARS]})"
        )
        records.append(
            _session_record(
                driver.session(
                    REPLY_RETRY_PROMPT.format(error=first), **kwargs, resume_id=resume
                )
            )
        )
        # Blindness is a claim about the whole pass, so the copy is re-proven
        # after the second turn too.
        assert_unchanged(staged, tree_hash)
        claims = parse_claims(records[-1])

    return {
        "session_id": _last_reported(records, "session_id"),
        "model": _last_reported(records, "model_reported", "model_requested") or model,
        "usd": _summed(records, "usd_cost"),
        "tokens_in": _summed(records, "tokens_in"),
        "tokens_out": _summed(records, "tokens_out"),
        "wall_s": _summed(records, "duration_s") or 0.0,
        "staged_copy_verified": True,
        "claims": claims,
    }


# --- loading the thing under audit ------------------------------------------


def _load_module(path: Path, name: str):
    """Exec-load one file under a unique module name, with streams quieted.

    The officials (and generated games) PRINT on import, and dataclass field
    resolution inside them reads `sys.modules[__name__]`, so the module is
    registered BEFORE exec — the same two facts `gen/officials.py` records.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # Bytecode OFF for the duration: the loader would drop a `__pycache__` into
    # the very tree this stage is auditing. Harmless to the scaffold scope check
    # (B1 ignores cache dirs) but the verifier writes nothing into the worker.
    bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    finally:
        sys.dont_write_bytecode = bytecode
    return module


def _module_tag(path: Path) -> str:
    """A per-path module name: two workers in one process must not collide."""
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]


def load_worker_classes(worker_dir: Path) -> tuple[type, type | None]:
    """(game class, solver class or None) from a worker's game.py / solver.py.

    Deliberately NOT imported from `worker-template/tests/_harness.py`: that
    file is a scaffold artifact copied into every worker, not a library this
    pipeline may depend on.

    THE STRICT loader (exactly one ARCBaseGame subclass DEFINED in game.py),
    and the one `frames.capture_worker` — the IN-PROCESS capture leg — uses.
    Contract E-4: the worker's own `sys.modules` entries are evicted first, for
    the same reason `s3_static.load_worker_classes` evicts them. The
    fresh-interpreter answer this module prefers for a full verify
    (`capture_worker_isolated`, R2 hotfix #8) is untouched and still stronger;
    eviction is what the in-process callers get.
    """
    worker_dir = Path(worker_dir).resolve()
    purge_worker_modules(worker_dir)
    game_path = worker_dir / "game.py"
    if not game_path.is_file():
        raise FileNotFoundError(f"{worker_dir}: no game.py to audit")
    tag = _module_tag(worker_dir)
    module = _load_module(game_path, f"s3_game_{tag}")
    candidates = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and issubclass(obj, ARCBaseGame)
        and obj is not ARCBaseGame
        and obj.__module__ == module.__name__
    ]
    if len(candidates) != 1:
        raise AssertionError(
            f"{game_path}: expected exactly ONE ARCBaseGame subclass, found "
            f"{sorted(c.__name__ for c in candidates)!r}"
        )
    game_cls = candidates[0]

    solver_path = worker_dir / "solver.py"
    if not solver_path.is_file():
        return game_cls, None
    solver_module = _load_module(solver_path, f"s3_solver_{tag}")
    solver_cls = getattr(solver_module, "Solver", None)
    if not isinstance(solver_cls, type):
        raise AssertionError(  # noqa: TRY004 — a worker contract breach, not a caller type error
            f"{solver_path}: solver.py must define a class named Solver"
        )
    return game_cls, solver_cls


def _official(cfg: Mapping, slug: str):
    officials = discover_officials(dict(cfg))
    found = next((official for official in officials if official.slug == slug), None)
    if found is None:
        raise ValueError(
            f"no official with slug {slug!r} — corpus holds {[o.slug for o in officials]}"
        )
    return found


def _bfs_cell_cap(cfg: Mapping) -> int:
    """`verifier.bfs_level_size_cap` — a signed knob, never defaulted in code."""
    verifier = cfg.get("verifier")
    if not isinstance(verifier, Mapping) or "bfs_level_size_cap" not in verifier:
        raise KeyError(
            "config missing verifier.bfs_level_size_cap — the BFS spot-check bound is a "
            "signed pilot knob (architecture §3 S2b config)"
        )
    cap = verifier["bfs_level_size_cap"]
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise ValueError(f"verifier.bfs_level_size_cap must be a positive int, got {cap!r}")
    return cap


def _load_spec(spec_path: Path) -> tuple[dict, str]:
    """(parsed spec, sha256 of its TEXT) — the same hash identity S1 records."""
    spec_path = Path(spec_path)
    if not spec_path.is_file():
        raise FileNotFoundError(f"spec not found: {spec_path}")
    text = spec_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    _as_mapping(parsed, f"{spec_path}: the spec document")
    _spec_game(parsed)
    return parsed, hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- CLI --------------------------------------------------------------------


def _paths(args: argparse.Namespace, target_dir: Path, slug: str) -> tuple[Path, Path, Path]:
    """(report path, frames path, working dir for the staged copy).

    Pipeline runs (a worker, full mode, no --out) write siblings of the worker;
    every other run writes `out/verify/<slug>/`.
    """
    if args.out:
        out_dir = Path(args.out)
        return out_dir / REPORT_NAME, out_dir / FRAMES_NAME, out_dir
    if args.worker and not args.dry_run:
        parent = target_dir.parent
        return (
            parent / (target_dir.name + REPORT_SUFFIX),
            parent / (target_dir.name + FRAMES_SUFFIX),
            parent,
        )
    out_dir = VERIFY_ROOT / slug
    return out_dir / REPORT_NAME, out_dir / FRAMES_NAME, out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S2b/S3 intent verifier")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--worker", help="worker dir holding game.py (+ solver.py)")
    mode.add_argument("--official", help="official slug (the acceptance/smoke path)")
    parser.add_argument("--spec", default=None, help="spec.yaml for the diff (worker full mode)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="static passes + REQUIRED rows only: no agent session, no diff",
    )
    parser.add_argument("--out", default=None, help="write the report/frames here instead")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)

    if args.spec and args.dry_run:
        parser.error("--spec is the diff input; a --dry-run runs no diff")
    if args.spec and args.official:
        parser.error("--spec belongs to --worker mode; officials have no spec")
    if args.worker and not args.dry_run and not args.spec:
        parser.error(
            "--worker without --dry-run runs the full verifier: pass --spec so the diff "
            "can run (a full run with no diff is the --official smoke path)"
        )

    cfg = load_config(args.config)
    bfs_cell_cap = _bfs_cell_cap(cfg)  # fail before loading a game or spending a session
    run_mode = "dry-run" if args.dry_run else "full"

    if args.official:
        official = _official(cfg, args.official)
        target_dir = official.py_path.parent
        game_id = official.game_id
        # Officials stay IN-PROCESS. An official is one signed corpus .py, not a
        # worker dir, so the isolated entry (which takes a worker) does not fit
        # it — and it does not need to: the corpus is read-only, one official is
        # loaded per run here, and the calibration batteries
        # (`gen/s3_gate.py --officials`, the B7 suite) drive `capture` directly.
        cap = capture(load_official_class(official.py_path))
    else:
        target_dir = Path(args.worker).resolve()
        if not target_dir.is_dir():
            raise FileNotFoundError(f"worker dir not found: {target_dir}")
        game_id = target_dir.name
        # Workers go through a FRESH interpreter (R2 hotfix #8). The worker is
        # GENERATED code: its solver loads game.py by path under a name it
        # chooses and may cache in `sys.modules`, so a second verify in one
        # process can hand a fresh solver a stale game module. Only an empty
        # `sys.modules` rules that out for code we did not write — see
        # `gen/frames.py`, "Process isolation".
        cap = capture_worker_isolated(target_dir)

    report_path, frames_path, work_dir = _paths(args, target_dir, game_id)
    checks: list[CheckResult] = [
        *run_static_checks(target_dir, cap),
        *run_required_rows(target_dir, cap),
        *run_solver_quality(target_dir, cap, bfs_cell_cap=bfs_cell_cap),
    ]

    agent = None
    diff = None
    spec_hash = None
    if not args.dry_run:
        agent = run_agent_pass(cfg, target_dir, cap, out_dir=work_dir)
        if args.spec:
            spec, spec_hash = _load_spec(Path(args.spec))
            diff = compute_diff(agent["claims"], spec)

    report = assemble_report(
        game_id=game_id,
        worker=target_dir,
        mode=run_mode,
        cfg=cfg,
        cap=cap,
        checks=checks,
        frames_path=frames_path,
        agent=agent,
        diff=diff,
        spec_hash=spec_hash,
        spec_path=Path(args.spec) if args.spec else None,
    )
    frames_path.parent.mkdir(parents=True, exist_ok=True)
    frames_path.write_text(json.dumps(capture_to_json(cap), indent=2) + "\n", encoding="utf-8")
    write_report(report, report_path)

    fails = [c for c in report["checks"] if c["status"] == "fail"]
    print(
        f"[s3] {report['verdict'].upper()} {game_id} | {len(report['checks'])} check(s), "
        f"{len(fails)} fail | frames {report['frames']['count']} "
        f"({report['frames']['source']}) | mode {run_mode}"
    )
    for reason in report["reject_reasons"]:
        route = f" [route: {reason['route']}]" if "route" in reason else ""
        print(f"[s3] reject {reason['code']}: {reason['detail']}{route}")
    # Contract L-1: what `deception_action: record` kept out of the rejects is
    # printed where the rejects are, in the same loop's shape. The ruling trades
    # a reject for a RECORD, and a record nobody is shown is not a record.
    advisories = report.get(ADVISORIES_KEY) or []
    if advisories:
        print(
            "[s3] deception advisories (recorded, not rejecting): "
            + "; ".join(advisory["detail"] for advisory in advisories)
        )
    # Contract Q-1, printed in the same loop's shape and for the same reason: the
    # pairs are recorded in both knob modes, so this line says which way the
    # record went — under `record` the named findings are no longer above, and
    # under the default they are, with the dispute standing beside them as the
    # evidence a human needs to decide whether to arm the knob.
    disputes = report.get(TERM_DISPUTES_KEY) or []
    for entry in disputes:
        print(
            f"[s3] term dispute {entry['code']}: {entry['term']} vs the declared "
            f"{entry['disputed_with']} — {entry['shared']}"
        )
    if agent is not None:
        usd = f"${agent['usd']:.4f}" if agent["usd"] is not None else "$unreported"
        print(
            f"[s3] agent: {agent['model']} | {usd} | tokens "
            f"{agent['tokens_in']}/{agent['tokens_out']} | {agent['wall_s']:.1f}s | "
            f"blind copy verified"
        )
    print(f"[s3] frames: {frames_path}")
    print(f"[s3] report: {report_path}")
    return 0 if report["verdict"] == "pass" else 2


if __name__ == "__main__":
    sys.exit(main())
