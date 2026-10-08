"""`arc-games` — the zero-YAML command line (contract P-4).

OPERATOR RULING (docs/v2/DECISIONS.md, 2026-09-29, verbatim): "Can we just have
a small cli or script that will just run the pipeline on anyone's machine and
they can choose openai or claude while running it."

So this module exists to make ONE sentence true:

    arc-games run --driver claude --games 2

is the whole ceremony for a stranger with a fresh clone. No YAML is authored,
no key is looked up in a doc, no stage is named. `config/` stays exactly where
it is — the power-user path, one file per batch, every knob commented — and
this CLI is a SECOND entrance to the same machine, never a second machine.

HOUSE RULE, and the reason this file composes instead of implementing
(contract P-4 §8): nothing existing changes behaviour. Every decision below is
made by code that already shipped —

  * `config/template.yaml`     the known-good starting config (READ-ONLY here;
                               this module never writes it and never will)
  * `gen.config.load_config`   canon resolution + the four-file canon check
  * `gen.s0_ideas.check_config` every STRICT config error, before any spend
  * `gen.backends`             driver preflights (codex credential, OpenRouter)
  * `gen.orchestrator.main`    the §4 state machine, the ledger, resume

The one thing it does NOT compose is `gen.tools.sync_canon`: contract P-2 §4
pins that no pipeline module imports the maintainer tool, so the canon
spot-check re-reads `canon/PROVENANCE.md`'s table here and a test pins the two
readers equal (see `read_provenance_table`).

— and this file's own work is exactly three things: it MATERIALIZES a config
from flags, it PREFLIGHTS the machine before a cent is spent, and it NARRATES
the ledger in sentences instead of state names.

THE RESOLVED CONFIG IS A FILE (contract P-4 §2). Every `run` writes the config
it built to `out/batches/<id>/config.yaml` and then invokes the orchestrator on
THAT PATH. Nothing is passed in memory. That is what makes `arc-games resume
<id>` and `arc-games status <id>` free: the batch's own config is on disk
beside its own ledger, so the run is reproducible by anyone holding the
directory — and it is the same file a power user could have written by hand.
`arc-games unpark <id> <slug> --reason TEXT` (contract E-5) is free for the same
reason: the batch's config resolves through `_config_for` like the other two,
and the lift is one ledger line and a printed `resume` command — it runs no
stage and spends nothing.

THE SEAMS, named once so nobody has to hunt for them:

  * NO SPEND. `build_config()` is pure — template + overlay + flags in, a dict
    out, nothing written, no driver contacted. `render_config()` turns it into
    the exact bytes, `write_config()` is the only thing that puts them on disk,
    and `run --dry-run` is the three of them minus the last, with every
    preflight run and printed.
  * THE ROOTS, redirectable at CALL time — the COMMAND layer as well as the
    library. Every path this module builds comes from one of four resolvers
    (`_config_dir`, `_batches_root`, `_games_root`, `batch_dir`), each of
    which reads its module constant WHEN IT IS CALLED: `gen.cli.CONFIG_DIR`,
    `gen.cli.TEMPLATE_PATH`, `gen.cli.BATCHES_ROOT` (or
    `gen.orchestrator.BATCHES_ROOT`), `gen.cli.GAMES_ROOT`,
    `gen.cli.VENDORED_CANON`. Move one and `run`, `resume`, `status` and
    `play` all follow it — there is no import-time capture to defeat. The
    library functions (`build_config`, `known_batch_ids`, `next_batch_id`,
    `next_seed`, `write_config`, `check_canon`, `LedgerNarrator`) additionally
    take the root as an argument.
  * THE PIPELINE. `orchestrator.main(["--config", path])`, reached through the
    module and never through a name bound at import, is the single call that
    hands over control.

EXIT CODES: 0 fine · 1 refused (bad usage, a failed preflight, an unknown
batch) or the orchestrator's own failure · 2 ONLY ever "the play server is
missing" — which, since L-2 vendored it into `tools/play/`, means a broken
checkout rather than an uninstalled dependency · 130 Ctrl-C. An argparse usage
error is mapped to 1 rather than argparse's own 2, the same way
`gen/orchestrator.py`'s CLI maps it, so 2 keeps meaning exactly one thing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from . import orchestrator
from .config import REPO_ROOT

PROG = "arc-games"

# --- what the CLI reads ------------------------------------------------------
#
# TEMPLATE_PATH and CONFIG_DIR are deliberately SEPARATE constants even though
# they point into the same directory today. The template is the STARTING POINT
# (one known-good file, read-only); `config/` is the SCAN DIRECTORY, read only
# to answer "which batch ids and seeds are already taken". A caller that
# repoints the scan must not thereby lose the template.
CONFIG_DIRNAME = "config"
TEMPLATE_NAME = "template.yaml"
CONFIG_DIR = REPO_ROOT / CONFIG_DIRNAME
TEMPLATE_PATH = REPO_ROOT / CONFIG_DIRNAME / TEMPLATE_NAME

# The resolved config's name inside the batch dir. `out/batches/<id>/` already
# holds `ledger.jsonl` and `batch-report.json`; this is the third member of the
# same set — everything one batch is, in one directory.
BATCH_CONFIG_NAME = "config.yaml"

# `games/` — the shared shelf (contract P-3). `play` defaults here because the
# shelf is what a teammate gets from `git pull`; `out/play` is one machine's
# scratch mirror and is gitignored.
GAMES_DIRNAME = "games"
GAMES_ROOT = REPO_ROOT / GAMES_DIRNAME

# `out/batches/` — the ledgers' home, and the CLI's own name for it.
#
# WHY THIS NAME EXISTS BESIDE `gen.orchestrator.BATCHES_ROOT` (lead ruling,
# P-4 follow-up). Every root the COMMAND layer touches has to be redirectable
# at CALL time, so a hermetic test can aim `run`/`resume`/`status` at a tmp
# tree without a flag — and a caller reaching for that seam looks for it on the
# module it is driving, `gen.cli`. Before this, the batches half of the seam
# only existed on `gen.orchestrator`, which is not where anyone looked.
#
# BOTH NAMES WORK, and `_batches_root` is the one place that decides: it
# follows `gen.cli.BATCHES_ROOT` once that has been moved away from its
# import-time value, and otherwise follows `gen.orchestrator.BATCHES_ROOT`, so
# a monkeypatch of EITHER reaches every path this module builds.
#
# THE ONE HAZARD, stated out loud: moving ONLY `gen.cli.BATCHES_ROOT` redirects
# what the CLI writes and reads, and does NOT redirect a real
# `orchestrator.main` run, which resolves its own ledger from
# `gen.orchestrator.BATCHES_ROOT`. Move both, or replace the run entry (the
# `_run_orchestrator` seam) — which is what a test that must not spend does
# anyway.
BATCHES_ROOT = orchestrator.BATCHES_ROOT
_IMPORT_TIME_BATCHES_ROOT = orchestrator.BATCHES_ROOT

# The play server IS vendored in this repo (contract L-2 — the queued P-4 §5
# decision, now made): `tools/play/` is a snapshot of the duckWM player with the
# §7 layout-seed picker added, and `tools/play/PROVENANCE.md` records the source,
# the commit and every modification. It is tracked, so a clone always has one.
#
# The duckWM sibling stays as the FALLBACK for a checkout where `tools/play/` is
# somehow missing. Its path is derived the same way `gen.s6_package.play_command`
# derives it from a config's `duckwm_docs`.
VENDORED_PLAY_SERVER = REPO_ROOT / "tools" / "play" / "server.py"
DUCKWM_SIBLING = REPO_ROOT.parent / "duckWM"
PLAY_SERVER_REL = Path("local-docs/arc-agi-3-games/tools/play/server.py")
PLAY_PYTHON_REL = Path(".venv/bin/python")

# --- the driver names a human uses ------------------------------------------
#
# The operator's ruling says "they can choose openai or claude". Those are the two
# words the flag takes; `backends.default_driver` takes the two names the
# repo's driver registry uses. This dict is the entire translation.
DRIVER_CHOICES: dict[str, str] = {
    "claude": "localclaude",
    "openai": "codex",
}

# --- THE AUTONOMY OVERLAY (contract P-4 §2) ----------------------------------
#
# `config/template.yaml` is the known-good BASE and carries every knob a batch
# has proven — but NOT the five autonomy armings, because those were written
# per batch. `config/b005r2-auto.yaml` is the live example of the full set, and
# this dict is that set, extracted, with the ruling each key implements:
#
#   verifier.reject_cap 1      one audit reject escalates to a re-spec instead
#                              of two — the loop converges without a human.
#   verifier.round_cap 4       the BOUND that makes autonomy terminate. With
#                              the operator's never-kill ruling behind it the slot
#                              PARKS at the cap (2026-09-29: "We should never
#                              kill. Even if it is not satisfied eventually
#                              let's not kill.").
#   verifier.reconcile_early 2 operator 2026-09-29: "If there's a mismatch of 1-2
#                              terms let's just go ahead with it." The spec is
#                              amended to the audited truth and re-confirmed.
#   review.auto_accept true    operator 2026-09-29: the pipeline must run WITHOUT
#                              human feedback; oversight is post-package play.
#   tiers.knob_defaults_action kill
#   tiers.goal_legible_cap obvious
#                              operator 2026-09-29: "let's only create obvious
#                              goal games instead of inferable too for now".
#                              The cap needs an enforcer, so the knob-defaults
#                              check is armed to kill beside it (gen/tiers.py
#                              refuses the cap outright when it is off).
#   verifier.deception_action  operator 2026-10-01: "We need to be lenient
#     record                   please." An undeclared-deception finding is
#                              RECORDED on the verifier report and never
#                              rejects. THE ONE KEY HERE THAT IS NOT A b005r2
#                              ARMING: the knob was written after that batch
#                              ran (contract L-1), measured on g20261001-1,
#                              where a t1 game's signed tier table allows no
#                              declared lever, so an audit lever sighting could
#                              be neither declared nor repaired and both slots
#                              were riding the ladder to park. `config/
#                              template.yaml` arms it too; the CODE default
#                              (absent key) is still `reject`.
#   orchestrator.             contract E-2, 2026-10-05. THE SECOND AND THIRD
#     stage_fail_park true    KEYS THAT ARE NOT b005r2 ARMINGS, for the same
#     respec_feasibility true reason `deception_action` is not: both knobs were
#                             written after that batch ran. Measured on
#                             g20261001-5, whose ledger rode "gate fail 1/1",
#                             "gate fail 2/1", "package fail 3/1" and "package
#                             fail 4/1" — four downstream rejects past a cap of
#                             1, because a downstream stage fail had no
#                             terminal; and whose escalated re-spec at line 7
#                             left the spec hash byte-identical, because the
#                             session was paid for without reading the findings
#                             it answered. Armed: a downstream fail past the
#                             cap PARKS (never kills — operator 2026-09-29), and a
#                             re-spec no spec amendment could answer is skipped
#                             and parked unspent. `config/template.yaml` arms
#                             both too; the CODE defaults (absent keys) are
#                             still false, which is the treadmill every shipped
#                             batch ran.
#   verifier.               contract Q-1, 2026-10-06. THE FOURTH KEY THAT IS NOT
#     term_dispute_action   a b005r2 ARMING, for the reason the three above are
#     record                not: the knob was written after that batch ran. It
#                           is `deception_action`'s own ruling one finding class
#                           over — an `undeclared-term` finding is an
#                           ATTRIBUTION DISPUTE rather than a defect when the
#                           blind audit grounded TWO signed vocabulary names on
#                           ONE observed behaviour. Measured on b005r2-auto's
#                           two-keys-one-echo, re-parked 2026-10-06 on
#                           `undeclared-term x2` where the audit's own two sites
#                           name one construct, the `pend` queue: a reject no
#                           spec amendment can durably answer, because declaring
#                           the audit's name only sends the next round back to
#                           the spec's. Armed, a DISPUTED finding rides the
#                           report's `term_disputes` instead of the verdict; an
#                           undisputed one, and one the auditor broke with a
#                           `distinguishes` clause, reject exactly as today.
#                           `config/template.yaml` arms it too; the CODE default
#                           (absent key) is still `reject`.
#
# IT IS AN EXPLICIT DICT ON PURPOSE. A stranger reading this file must be able
# to see the whole arming at once and diff it against b005r2 by eye; deriving
# it from that batch's file would make the CLI's behaviour depend on a config
# nobody promised to keep.
AUTONOMY_OVERLAY: dict[str, dict[str, object]] = {
    "verifier": {"reject_cap": 1, "round_cap": 4, "reconcile_early": 2,
                 "deception_action": "record", "term_dispute_action": "record"},
    "review": {"auto_accept": True},
    "tiers": {"knob_defaults_action": "kill", "goal_legible_cap": "obvious"},
    "orchestrator": {"stage_fail_park": True, "respec_feasibility": True},
}


class CliError(Exception):
    """A usage or environment error, reported in one plain sentence.

    Everything this CLI refuses, it refuses through this: `main` prints the
    message and returns 1. Stage errors are NOT routed here — the orchestrator
    prints its own traceback and owns its own exit code.
    """


# --- the roots, resolved at CALL time ----------------------------------------
#
# Contract P-4's library seam was already complete — `build_config`,
# `next_batch_id`, `next_seed` and `known_batch_ids` all take explicit roots.
# The COMMAND layer (`run`, `resume`, `status`, `play`) had no such seam: it
# fell through to values read at import, so nothing a caller did afterwards
# could move it off the real `config/` and `out/batches/`.
#
# These four functions are that fix (lead ruling, P-4 follow-up). Every root
# the command layer touches goes through one of them, each reads its module
# constant when it is called, and each still takes an explicit override so the
# library seam keeps working exactly as it did.


def _config_dir(config_dir: Path | None = None) -> Path:
    return Path(CONFIG_DIR if config_dir is None else config_dir)


def _batches_root(batches_root: Path | None = None) -> Path:
    """`out/batches/`, from the explicit argument, then either module constant.

    See the comment at `BATCHES_ROOT` for why two names answer here and which
    one wins.
    """
    if batches_root is not None:
        return Path(batches_root)
    if Path(BATCHES_ROOT) != Path(_IMPORT_TIME_BATCHES_ROOT):
        return Path(BATCHES_ROOT)
    return Path(orchestrator.BATCHES_ROOT)


def _games_root(games_root: Path | None = None) -> Path:
    return Path(GAMES_ROOT if games_root is None else games_root)


def batch_dir(cfg: Mapping, batches_root: Path | None = None) -> Path:
    """`<batches root>/<batch.id>/` — `orchestrator.batch_dir`, redirectable.

    The derivation is the orchestrator's and must stay the orchestrator's: the
    config this CLI writes has to land in the SAME directory the ledger will.
    It is repeated here only to take a root, and
    `test_p4_cli.test_batch_dir_is_the_orchestrators_own_derivation` pins the
    two equal whenever nothing is redirected, so they cannot drift.
    """
    return _batches_root(batches_root) / orchestrator.batch_config(cfg)["id"]


# --- the resolved config -----------------------------------------------------


def load_template(template_path: Path | None = None) -> dict:
    """`config/template.yaml`, parsed as DATA. Never modified, ever.

    Read with `yaml.safe_load` rather than `gen.config.load_config`, and the
    difference is load-bearing twice over:

    1. `load_config` REWRITES `duckwm_docs` to an absolute path on this
       machine. The materialized config is meant to travel (it is the record
       of what ran, and a teammate re-runs it from their own clone), so it has
       to keep the template's repo-relative `./canon` exactly as written.
    2. A materialized config must differ from the template ONLY where a flag or
       the overlay moved a key. Resolution would add a difference nobody asked
       for.

    Validation still happens — on the FILE that is about to be written, by
    `load_config` + `check_config`, which is the same pair the template's own
    header tells a power user to run.
    """
    path = TEMPLATE_PATH if template_path is None else Path(template_path)
    if not path.is_file():
        raise CliError(
            f"the starting config is missing: {path}\n"
            f"  Every batch starts from that file. Restore it from git "
            f"(`git checkout {CONFIG_DIRNAME}/{TEMPLATE_NAME}`) and try again."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CliError(f"{path} did not parse to a mapping — it is not a usable config")
    return data


def apply_overlay(cfg: dict, overlay: Mapping[str, Mapping[str, object]]) -> dict:
    """Merge the overlay into a COPY of cfg, one block deep.

    One block deep is the whole shape of the overlay — every key it sets lives
    directly under a top-level block — and a deeper merge would be a general
    config-merging facility nobody asked for. A block the template does not
    carry (`review:` today) is created; a block it does carry keeps every key
    the overlay does not name.
    """
    merged = {key: (dict(value) if isinstance(value, dict) else value) for key, value in cfg.items()}
    for block, keys in overlay.items():
        target = merged.get(block)
        target = dict(target) if isinstance(target, Mapping) else {}
        target.update(keys)
        merged[block] = target
    return merged


def _batch_ids_from_configs(config_dir: Path) -> set[str]:
    """Every `batch.id` written in `config/*.yaml` — the power-user path's ids.

    `template.yaml` IS SKIPPED, and only here. Its `batch.id` is the literal
    string `bNNN-topic`, marked PLACEHOLDER in its own comment: it names no
    batch, and letting it through would print `bNNN-topic` in the list of
    "batches I can see" that an unknown-id error shows a stranger. Its SEED is
    still counted (`next_seed` scans every file), because a seed written
    anywhere in `config/` is a seed this repo has committed to paper and the
    cost of skipping one number is zero.

    TOLERANT BY DESIGN otherwise: this answers "which name is taken", so a file
    that will not parse contributes nothing rather than stopping a run. A config
    that is broken enough to be unreadable here is broken enough that nobody is
    going to collide with its id by accident.
    """
    ids: set[str] = set()
    if not config_dir.is_dir():
        return ids
    for path in sorted(config_dir.glob("*.yaml")):
        if path.name == TEMPLATE_NAME:
            continue
        data = _safe_yaml(path)
        batch = data.get("batch") if isinstance(data, Mapping) else None
        value = batch.get("id") if isinstance(batch, Mapping) else None
        if isinstance(value, str) and value:
            ids.add(value)
    return ids


def _batch_ids_from_out(batches_root: Path) -> set[str]:
    """Every `out/batches/<id>/` on this machine — the ids that have RUN.

    A directory is enough: it means a ledger for that id may exist, and a
    second batch writing into it would append to someone else's history.
    """
    if not batches_root.is_dir():
        return set()
    return {path.name for path in batches_root.iterdir() if path.is_dir()}


def known_batch_ids(config_dir: Path | None = None,
                    batches_root: Path | None = None) -> set[str]:
    """Every batch id that is taken, from both homes."""
    return (_batch_ids_from_configs(_config_dir(config_dir))
            | _batch_ids_from_out(_batches_root(batches_root)))


def next_batch_id(name: str | None = None, *, today: date | None = None,
                  config_dir: Path | None = None,
                  batches_root: Path | None = None) -> str:
    """`gYYYYMMDD-<n>`, `n` the first free counter for today (contract P-4 §2).

    `--name WORD` appends `-<word>`, so a human can tell two of today's batches
    apart in `out/batches/`.

    THE COUNTER IS RESERVED WITH OR WITHOUT THE NAME. `n` is skipped when ANY
    taken id is `gYYYYMMDD-<n>` or starts with `gYYYYMMDD-<n>-`, so today's
    third batch is `-3` whether or not the first two were named. A counter that
    meant different things depending on a name would let two runs pick ids that
    look unrelated and sort as if they were the same batch.
    """
    taken = known_batch_ids(config_dir, batches_root)
    # UTC, like every `ts` the ledger writes (`orchestrator._now`): a batch id
    # and the lines inside it should agree about what day it is, whichever side
    # of midnight the operator's own clock is on.
    stamp = (today or datetime.now(tz=UTC).date()).strftime("g%Y%m%d")
    counter = 1
    while True:
        prefix = f"{stamp}-{counter}"
        if not any(other == prefix or other.startswith(prefix + "-") for other in taken):
            return prefix if not name else f"{prefix}-{name}"
        counter += 1


def _seeds_from(paths: Iterable[Path]) -> list[int]:
    seeds: list[int] = []
    for path in paths:
        data = _safe_yaml(path)
        batch = data.get("batch") if isinstance(data, Mapping) else None
        value = batch.get("seed") if isinstance(batch, Mapping) else None
        if isinstance(value, int) and not isinstance(value, bool):
            seeds.append(value)
    return seeds


def next_seed(config_dir: Path | None = None, batches_root: Path | None = None) -> int:
    """`max(every seed this repo has ever written) + 1`.

    The seed drives every S0 draw and the S6 validation seeds, so two batches
    on the same seed sample the SAME ideas — which is a tool (b003 was re-run as
    b003r2 on seed 3 deliberately) and an accident nobody wants by default. The
    scan covers both homes for the same reason `known_batch_ids` does: a seed
    used by a batch that ran from a hand-written config is used.
    """
    configs = _config_dir(config_dir)
    batches = _batches_root(batches_root)
    seeds = _seeds_from(sorted(configs.glob("*.yaml")) if configs.is_dir() else [])
    seeds += _seeds_from(sorted(batches.glob(f"*/{BATCH_CONFIG_NAME}"))
                         if batches.is_dir() else [])
    return (max(seeds) + 1) if seeds else 1


def _safe_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None


def build_config(*, driver: str, games: int, tiers: Sequence[str] | None = None,
                 name: str | None = None, seed: int | None = None,
                 workers: int | None = None,
                 batch_id: str | None = None, today: date | None = None,
                 template_path: Path | None = None,
                 config_dir: Path | None = None,
                 batches_root: Path | None = None) -> dict:
    """THE MATERIALIZATION: template + autonomy overlay + flags (contract P-4 §2).

    Pure: it reads the template and the two id/seed scans, and returns a dict.
    Nothing is written, no driver is contacted, no preflight runs — this is the
    no-spend seam, and `run --dry-run` is the same function with a printer
    attached.

    The result differs from `config/template.yaml` on exactly these keys:
      backends.default_driver   ← --driver, through DRIVER_CHOICES
      batch.id                  ← --name, else the auto counter
      batch.size                ← --games
      batch.seed                ← --seed, else max-in-repo + 1
      batch.tier_sequence       ← --tiers, and REMOVED when --tiers is absent
                                  (the template pins two tiers; absent means
                                  every slot takes the `batch.tiers` weighted
                                  draw, which is what a caller who did not ask
                                  for tiers means)
      orchestrator.parallel_slots  ← --workers N>1 ONLY, and with it
      orchestrator.workers         (contract P-5). `--workers 1` and no
                                  `--workers` at all resolve BYTE-IDENTICALLY:
                                  neither key is written, because forwarding a
                                  flag that changes nothing would claim a
                                  capability the run is not using.
    plus the ten keys of AUTONOMY_OVERLAY (six of them b005r2's arming, plus
    `verifier.deception_action: record` — contract L-1, 2026-10-01 —
    `orchestrator.stage_fail_park` + `orchestrator.respec_feasibility`, contract
    E-2, 2026-10-05, and `verifier.term_dispute_action: record`, contract Q-1,
    2026-10-06).
    """
    if driver not in DRIVER_CHOICES:
        raise CliError(
            f"unknown driver {driver!r} — choose one of {', '.join(sorted(DRIVER_CHOICES))}"
        )
    if isinstance(games, bool) or not isinstance(games, int) or games < 1:
        raise CliError(f"--games must be a whole number of games, 1 or more; got {games!r}")

    cfg = apply_overlay(load_template(template_path), AUTONOMY_OVERLAY)

    backends = dict(cfg.get("backends") or {})
    backends["default_driver"] = DRIVER_CHOICES[driver]
    cfg["backends"] = backends

    batch = dict(cfg.get("batch") or {})
    batch["id"] = batch_id or next_batch_id(
        name, today=today, config_dir=config_dir, batches_root=batches_root
    )
    batch["size"] = games
    batch["seed"] = next_seed(config_dir, batches_root) if seed is None else seed
    if tiers is None:
        # The template pins `[t1, t2]` for its own example size of 2. A caller
        # who named no tiers is asking for the weighted draw, and a leftover
        # sequence would silently pin every slot to somebody else's example.
        batch.pop("tier_sequence", None)
    else:
        batch["tier_sequence"] = list(tiers)
    cfg["batch"] = batch

    # CONTRACT P-5, and it is deliberately TWO keys. `orchestrator.workers` has
    # been written in every config since b001 and read by nothing, so the count
    # alone can never mean "run these in parallel" — a resume of an old batch
    # would fan out on a number nobody meant. `parallel_slots` is the sentence
    # that says this batch asked for it, and both keys appear together or not at
    # all. More workers than games is not an error, it is a number with nothing
    # to do, so it clamps (the command layer says so on stdout).
    if workers is not None:
        if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
            raise CliError(
                f"--workers must be a whole number of games at once, 1 or more; got {workers!r}"
            )
        if min(workers, games) > 1:
            orchestrator = dict(cfg.get("orchestrator") or {})
            orchestrator["parallel_slots"] = True
            orchestrator["workers"] = min(workers, games)
            cfg["orchestrator"] = orchestrator

    taken = known_batch_ids(config_dir, batches_root)
    if batch["id"] in taken:
        raise CliError(
            f"batch id {batch['id']!r} is already in use on this machine.\n"
            f"  Pick another name (--name WORD) — a second batch writing into "
            f"out/batches/{batch['id']}/ would append to the first one's ledger."
        )
    return cfg


def render_config(cfg: Mapping, *, source: str = "arc-games") -> str:
    """The YAML text that gets written — built ONCE and written verbatim.

    One string, two destinations: the temp copy the preflight validates and the
    real `out/batches/<id>/config.yaml`. They are byte-identical by
    construction, so "the config we checked" and "the config the orchestrator
    reads" cannot drift apart.

    The header is COMMENTS, which is the only kind of provenance a config file
    can carry without becoming a key some stage has to know about.
    """
    header = (
        f"# out/batches/{cfg['batch']['id']}/{BATCH_CONFIG_NAME} — written by "
        f"`{source}` (contract P-4).\n"
        "#\n"
        "# This is the RESOLVED config the batch ran under: config/template.yaml,\n"
        "# plus the autonomy overlay (gen/cli.py:AUTONOMY_OVERLAY), plus the flags.\n"
        "# It is the batch's own record — the orchestrator was invoked on THIS file,\n"
        "# so re-running it reproduces the run. The template itself is never modified.\n"
        "#\n"
        "# Every key below is documented in config/template.yaml, comment by comment.\n"
        "\n"
    )
    body = yaml.safe_dump(dict(cfg), sort_keys=False, default_flow_style=False,
                          allow_unicode=True)
    return header + body


def write_config(cfg: Mapping, text: str, batches_root: Path | None = None) -> Path:
    """Persist the resolved config beside the ledger it is about to write.

    `batches_root` is the explicit override (lead ruling, P-4 follow-up): a
    test that wants to prove the WRITE without touching the repo's own
    `out/batches/` passes it, rather than having to move a module constant.
    """
    path = batch_dir(cfg, batches_root) / BATCH_CONFIG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- the preflights (contract P-4 §3) ---------------------------------------
#
# ALL OF THEM RUN, AND ALL FAILURES ARE PRINTED TOGETHER. A preflight that
# stopped at the first problem would make a stranger fix one thing, wait, and
# find the next — which is exactly the experience this CLI exists to remove.


class Check:
    """One preflight result: a level, a title and the sentence a human reads."""

    __slots__ = ("detail", "level", "title")

    def __init__(self, level: str, title: str, detail: str):
        self.level = level          # "ok" | "warn" | "fail"
        self.title = title
        self.detail = detail

    @property
    def failed(self) -> bool:
        return self.level == "fail"

    def line(self) -> str:
        mark = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}[self.level]
        return f"  [{mark}] {self.title}: {self.detail}"


def check_driver(driver: str, cfg: Mapping) -> Check:
    """Is the tool that writes the games installed, and does it have a login?

    `claude` is PRESENCE ONLY, and the contract says so: this repo handles no
    Anthropic key — the localclaude lane runs on the user's own `claude login`,
    and there is nothing here that could check it without spending.

    `codex` gets `CodexDriver.preflight`, which is presence-only too and says
    so in its own docstring: the four codex failures on record are 401s from a
    STALE key, which IS present. That P-1b caveat stands; this is the strongest
    check that costs nothing.
    """
    from .backends import CodexDriver, DriverError, codex_auth_env, codex_auth_file

    if driver == "claude":
        found = shutil.which("claude")
        if not found:
            return Check("fail", "the claude CLI",
                         "not installed (nothing named `claude` on your PATH).\n"
                         "         Install it from https://claude.com/claude-code, then run "
                         "`claude` once and sign in.")
        return Check("ok", "the claude CLI",
                     f"{found} (this repo never sees your key — the CLI runs on your own "
                     "login;\n         if you have not signed in, run `claude` once first)")

    found = shutil.which("codex")
    if not found:
        return Check("fail", "the codex CLI",
                     "not installed (nothing named `codex` on your PATH).\n"
                     "         Install it, then either `codex login` or export an API key.")
    try:
        CodexDriver().preflight(auth_env=codex_auth_env(cfg))
    except DriverError as exc:
        return Check("fail", "codex sign-in", str(exc))
    except ValueError as exc:
        return Check("fail", "codex sign-in", str(exc))
    where = "the environment" if os.environ.get(codex_auth_env(cfg)) else str(codex_auth_file())
    return Check("ok", "the codex CLI",
                 f"{found}, credential found in {where}\n"
                 "         (presence only — a stale key looks exactly like a live one until "
                 "it is used)")


def check_openrouter() -> Check:
    """The battery's key — a WARNING, never a refusal (contract P-4 §3).

    S5 plays every finished game with an agent over OpenRouter, and it is the
    ONLY consumer of this key: S0-S4 and S6 never touch it. So a missing key
    does not stop a batch from starting — it stops it at S5, five stages in,
    with the games already built. The warning says exactly that, because the
    honest thing for someone with no key is to start anyway and export one
    before the first game reaches the battery.
    """
    from .backends import OPENROUTER_EXPORT_LINE, OPENROUTER_KEY_ENV

    if (os.environ.get(OPENROUTER_KEY_ENV) or "").strip():
        return Check("ok", "the play-test key", f"{OPENROUTER_KEY_ENV} is set")
    return Check(
        "warn", "the play-test key",
        f"{OPENROUTER_KEY_ENV} is not set. Everything up to the play-test runs without it; "
        "the batch\n         will then FAIL at the play-test stage (S5), which is the only "
        "thing that uses it.\n"
        f"         Fix it any time before then: {OPENROUTER_EXPORT_LINE}",
    )


# `canon/PROVENANCE.md`'s file table, read WITHOUT importing the tool that
# writes it.
#
# THE CONFLICT, resolved here and reported rather than papered over: contract
# P-4 §3 requires a canon sha spot-check before every batch, and contract P-2
# §4 pins that NO pipeline module imports `gen.tools.sync_canon`
# (`test_p2_vendoring.test_sync_canon_is_wired_into_nothing`, an AST scan of
# `gen/*.py`) — the maintainer tool that WRITES `canon/` must not become a
# runtime dependency of the pipeline that READS it. Both are right, so the CLI
# re-reads the rows itself: three lines of table parsing against a format the
# same repo owns, rather than a runtime edge from the pipeline to its own
# re-vendoring tool.
#
# The duplication is PINNED, not hoped at: `test_p4_cli` asserts this reader
# and `sync_canon.parse_provenance` return the same table for the real
# `canon/PROVENANCE.md`, so the two cannot drift apart in silence.
#
# IT IS READ OFF `canon/`, NEVER OFF `duckwm_docs`, and that is the second
# thing P-2 forced (`test_v2_canon.derive_canon_reads` AST-scans `gen/*.py` for
# every `<canon root> / <name>` chain and requires duckWM to hold the file).
# `PROVENANCE.md` is the SNAPSHOT'S OWN stamp — duckWM has no such file, and a
# config may legitimately point `duckwm_docs` at a live checkout — so the check
# is on the vendored tree by name, and a config reading a live checkout is
# reported as unstamped instead.
CANON_DIRNAME = "canon"
VENDORED_CANON = REPO_ROOT / CANON_DIRNAME
PROVENANCE_NAME = "PROVENANCE.md"
_PROVENANCE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([0-9a-f]{64})\s*\|$")


def read_provenance_table(text: str) -> dict[str, tuple[int, str]]:
    """`PROVENANCE.md` -> `{relative path: (bytes, sha256)}`."""
    rows: dict[str, tuple[int, str]] = {}
    for line in text.splitlines():
        row = _PROVENANCE_ROW.match(line.strip())
        if row:
            rows[row.group(1)] = (int(row.group(2)), row.group(3))
    return rows


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _resolved_docs(cfg: Mapping) -> Path:
    """`duckwm_docs` resolved the way `gen.config.load_config` resolves it.

    Repeated here (three lines) rather than taken from a loaded config, so the
    canon check can still run and be REPORTED when the config check above it
    has already failed — "all failures listed together" is the whole point of
    the preflight block.
    """
    docs = Path(str(cfg.get("duckwm_docs") or ""))
    if not docs.is_absolute():
        docs = REPO_ROOT / docs
    return docs.resolve()


def check_canon(cfg: Mapping, *, sample: int = 3, rng: random.Random | None = None,
                canon_root: Path | None = None) -> Check:
    """Spot-check the vendored canon against its own sha256 stamp.

    The canon is what every prompt is built from. A corrupted or half-synced
    copy does not crash — it quietly produces thinner prompts, and the damage
    shows up as a worse game a week later. So the stamp gets checked before the
    run, not after.

    A SPOT-CHECK, not a full verify: the two CSVs the sampler and the linter
    read on every single draw, plus `sample` documents drawn at random. The
    full check is `gen.tools.sync_canon.verify_provenance` and it hashes every
    stamped file; this one is the part that is worth a second at the start of every
    batch. A canon that is NOT the vendored snapshot (a live duckWM checkout,
    which `duckwm_docs` may legitimately name) carries no stamp and is reported
    as unstamped rather than failed.
    """
    vendored = (VENDORED_CANON if canon_root is None else Path(canon_root)).resolve()
    docs = _resolved_docs(cfg)
    if docs != vendored:
        return Check("ok", "the game canon",
                     f"{docs}\n         (a live checkout, not the vendored snapshot at "
                     f"{vendored} — it carries no\n         sha256 stamp, so there is "
                     "nothing to spot-check)")
    stamp = vendored / PROVENANCE_NAME
    if not stamp.is_file():
        return Check("fail", "the game canon",
                     f"{stamp} is missing — the vendored canon cannot vouch for itself.\n"
                     "         Restore it with `git checkout canon/`.")
    try:
        listed = read_provenance_table(stamp.read_text(encoding="utf-8"))
    except OSError as exc:
        return Check("fail", "the game canon", f"{stamp} is unreadable: {exc}")
    if not listed:
        return Check("fail", "the game canon",
                     f"{stamp} carries no file table — it cannot vouch for anything. "
                     "Re-stamp it with\n         `python -m gen.tools.sync_canon --force`.")

    csvs = sorted(rel for rel in listed if rel.endswith(".csv"))
    others = sorted(rel for rel in listed if not rel.endswith(".csv"))
    picker = rng or random.Random()
    picked = csvs + picker.sample(others, min(sample, len(others)))

    problems: list[str] = []
    for rel in picked:
        target = vendored / rel
        if not target.is_file():
            problems.append(f"{rel} is listed in {PROVENANCE_NAME} but missing from the tree")
            continue
        if _sha256_of(target) != listed[rel][1]:
            problems.append(f"{rel} does not match its recorded sha256")
    if problems:
        return Check(
            "fail", "the game canon",
            f"{len(problems)} of {len(picked)} spot-checked file(s) do not match "
            f"{stamp}:\n         " + "\n         ".join(problems)
            + "\n         Restore them with `git checkout canon/`, or re-stamp from a duckWM "
              "checkout with\n         `python -m gen.tools.sync_canon --force`.",
        )
    return Check("ok", "the game canon",
                 f"{len(picked)} of {len(listed)} files spot-checked against "
                 f"{stamp.name}, all match")


def check_config_file(path: Path) -> tuple[Check, dict | None]:
    """`load_config` + `check_config` — the pair the template's header names.

    Run on the file about to be handed to the orchestrator, which is the only
    version of this check worth having: it proves the BYTES are loadable, that
    the canon they point at exists, and that every STRICT sampler/backends rule
    holds — all of it before S0 spends a single prose token.
    """
    from .config import load_config
    from .s0_ideas import check_config, load_vocab

    try:
        cfg = load_config(path)
        check_config(cfg, load_vocab(cfg))
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        return Check("fail", "the batch settings",
                     f"{type(exc).__name__}: {exc}"), None
    return Check("ok", "the batch settings", "loaded and validated"), cfg


def preflight(cfg: Mapping, config_text: str, driver: str, *,
              rng: random.Random | None = None) -> list[Check]:
    """Every pre-spend check, in the order a human wants to read them.

    The config check runs against a TEMPORARY copy holding the exact bytes
    `run` is about to write, so a config that fails validation never reaches
    `out/batches/` and never burns a batch id.
    """
    import tempfile

    checks: list[Check] = []
    with tempfile.TemporaryDirectory(prefix="arc-games-preflight-") as tmp:
        probe = Path(tmp) / BATCH_CONFIG_NAME
        probe.write_text(config_text, encoding="utf-8")
        config_check, _resolved = check_config_file(probe)
    checks.append(config_check)
    checks.append(check_driver(driver, cfg))
    checks.append(check_canon(cfg, rng=rng))
    checks.append(check_openrouter())
    return checks


# --- narration (contract P-4 §4) ---------------------------------------------
#
# The orchestrator speaks §4: `implemented --> spec_ok`, `baselined`, `parked`.
# That vocabulary is correct and this CLI does not replace it — the `[b11]`
# lines still print. What follows is a SECOND voice reading the same ledger for
# somebody who has never seen the state diagram, one sentence per transition.

EDGE_NARRATION: dict[tuple[str | None, str], str] = {
    (None, "ideated"): "picked an idea to build",
    ("respec", "ideated"): "picked a fresh idea (attempt {n})",
    ("ideated", "spec_ok"): "wrote the design spec",
    ("ideated", "respec"): "the spec broke the house rules — starting over from a new idea",
    ("spec_ok", "implemented"): "built the game and it passes its own checks (build {n})",
    ("spec_ok", "dead"): "gave up building this one — too many failed attempts",
    ("implemented", "verified"): "a blind audit read the code and agreed it matches the spec",
    ("implemented", "spec_ok"): "the blind audit disagreed with the spec — rebuilding",
    ("implemented", "dead"): "stopped: the audit never converged",
    ("implemented", "parked"): "PARKED — the audit left a question nobody could answer; "
                               "nothing was deleted",
    ("verified", "gated"): "passed the structure and look checks",
    ("verified", "spec_ok"): "a structure or look check failed — rebuilding",
    ("gated", "baselined"): "worked out how hard each level is",
    ("gated", "spec_ok"): "the move budget does not fit the levels — rebuilding",
    ("baselined", "played"): "an agent played it end to end",
    ("played", "reviewed"): "accepted",
    ("played", "implemented"): "the play-test crashed the game — rebuilding",
    ("reviewed", "packaged"): "PACKAGED — on the shelf as {shelf}",
    ("reviewed", "pulled"): "pulled at review — not shipped",
    ("reviewed", "spec_ok"): "packaging found a bad level layout — rebuilding",
    # Contract E-2's four park edges. `narrate` answers None for an edge that is
    # not in here, so an un-narrated edge is SILENCE in this voice — and
    # `test_p4_cli.test_every_transition_the_state_machine_can_take_is_narrated`
    # is the invariant that says a human must never watch a slot stop without
    # being told it did.
    ("verified", "parked"): "PARKED — the same structure or look check kept failing; "
                            "nothing was deleted",
    ("gated", "parked"): "PARKED — the move budget never fit the levels; nothing was deleted",
    ("reviewed", "parked"): "PARKED — packaging kept finding a bad level layout; "
                            "nothing was deleted",
    ("spec_ok", "parked"): "PARKED — no change to the design could answer what went wrong, "
                           "so nothing was rewritten and nothing was deleted",
    # Contract E-5's five LIFT edges, in this table for exactly the reason the
    # four above are: `narrate` answers None for an un-narrated edge, and the
    # invariant test named above sweeps every edge the state machine can take.
    # They are the only rows here a stage never writes — a person did, by
    # running `arc-games unpark` — so each says so, and says what picks up next.
    ("parked", "spec_ok"): "UNPARKED by hand — building the game again from the design",
    ("parked", "implemented"): "UNPARKED by hand — sending it back to the blind audit",
    ("parked", "verified"): "UNPARKED by hand — re-running the structure and look checks",
    ("parked", "gated"): "UNPARKED by hand — working out how hard each level is again",
    ("parked", "reviewed"): "UNPARKED by hand — packaging it again",
}

# WHAT IT IS DOING NOW. A transition is only ever appended when a stage has
# FINISHED (§4: "a line is a claim that the work exists"), so a ledger read on
# its own is a list of completed things separated by twenty silent minutes. The
# second half of narration is therefore the state the slot just LANDED in, read
# through `orchestrator.NEXT_STAGE` — the machine's own answer to "what runs
# from here" — so the silence has a caption. Terminal states are absent, which
# is how they stay silent.
NEXT_STAGE_NARRATION: dict[str, str] = {
    "ideated": "writing the design spec...",
    "respec": "drawing a fresh idea...",
    "spec_ok": "building the game now — this is the long part...",
    "implemented": "a blind audit is reading it...",
    "verified": "checking how it is put together and how it looks...",
    "gated": "working out how hard each level is...",
    "baselined": "an agent is playing it...",
    "reviewed": "packaging it...",
}


# CONTRACT H-1 item 2 (2026-10-06): the ONE ledger reason that narrates against
# its edge. A declaration-only re-spec lands `spec_ok --> implemented` like a
# build does, but no session ran — S2 revalidated the game already on disk
# (`orchestrator.DECL_ONLY_REASON`) in seconds. Narrated through the edge it read
# "built the game … (build N)" right after the escalation's "— rebuilding", and
# on 10-01 operators read that pair and budgeted an hour for a hop that had
# already finished. The reason is the only thing on the ledger that tells the two
# apart (the escalation line is written BEFORE the re-spec knows it will be
# declaration-only), so it is keyed here and nowhere else, and the sentence
# deliberately carries no build vocabulary at all.
DECL_ONLY_NARRATION = (
    "checked the game already on disk against the amended spec — the change was "
    "declarations only, so it still passes and nothing was rewritten (seconds, no session)"
)


def next_stage_line(state: str) -> str | None:
    """The "now doing" caption for a state, or None when nothing runs from it.

    Keyed off `orchestrator.NEXT_STAGE` rather than off this dict alone, so a
    state that stops running work (a future terminal state) stops being
    captioned without anyone remembering to delete a sentence.
    """
    if orchestrator.NEXT_STAGE.get(state) is None:
        return None
    return NEXT_STAGE_NARRATION.get(state)


def narrate(line: Mapping, *, seen: dict[tuple[str, str | None, str], int],
            shelf: str | None = None) -> str | None:
    """One ledger line -> one sentence, or None when there is nothing to say.

    `{n}` interpolates HOW MANY TIMES this slot has taken this edge, which is
    the only honest way to say "attempt 2" from a ledger: the green loop's
    attempts under the cap append no line at all, so the number here counts
    laps of the state machine and never pretends to count sessions. A
    declaration-only revalidation (contract H-1 item 2) is narrated by its
    REASON and is not counted as a lap of the build edge — it built nothing, so
    the next real build is still "build 2", not "build 3".
    """
    if orchestrator.DECL_ONLY_REASON in str(line.get("reason", "")):
        return DECL_ONLY_NARRATION
    slug = str(line.get("slug", ""))
    edge = (line.get("from"), str(line.get("to")))
    text = EDGE_NARRATION.get(edge)
    if text is None:
        return None
    key = (slug, edge[0], edge[1])
    seen[key] = seen.get(key, 0) + 1
    return text.format(n=seen[key], shelf=shelf or "games/")


def _slot_label(slug: str, batch_id: str, size: int) -> str:
    """`b005-auto-s002` -> `game 2 of 3`, falling back to the slug itself."""
    tail = slug[len(batch_id) + 1:] if slug.startswith(batch_id + "-") else ""
    if tail.startswith("s") and tail[1:].isdigit():
        return f"game {int(tail[1:])} of {size}"
    return slug


class LedgerNarrator:
    """Tail `ledger.jsonl` in a daemon thread and print it in sentences.

    Reading the LEDGER rather than instrumenting the orchestrator is the whole
    design: the ledger is already the batch's state of record (§4 — "a line is
    a claim that the work exists"), so the narration cannot drift from what
    actually happened, and nothing in `gen/orchestrator.py` had to change to
    get it.

    Daemon, and every failure swallowed: a narrator that raised would kill a
    batch mid-spend over a print.
    """

    def __init__(self, ledger_path: Path, *, batch_id: str, size: int,
                 games_root: Path | None = None, out=None, interval: float = 0.5):
        self.ledger_path = Path(ledger_path)
        self.batch_id = batch_id
        self.size = size
        self.games_root = _games_root(games_root)
        self.out = out if out is not None else sys.stdout
        self.interval = interval
        self._offset = 0
        self._seen: dict[tuple[str, str | None, str], int] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        # Start AT THE END of whatever is already there: a resumed batch must
        # not replay three days of history as if it were happening now.
        if self.ledger_path.is_file():
            self._offset = self.ledger_path.stat().st_size
        self._thread = threading.Thread(target=self._loop, name="arc-games-narrator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2 * self.interval + 1)
        self._drain()   # whatever landed between the last poll and the stop

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self._drain()

    def _drain(self) -> None:
        try:
            if not self.ledger_path.is_file():
                return
            with self.ledger_path.open(encoding="utf-8") as fh:
                fh.seek(self._offset)
                chunk = fh.read()
                # Only whole lines: a reader that consumed a half-written line
                # would corrupt its own offset and lose the rest of the batch.
                cut = chunk.rfind("\n")
                if cut < 0:
                    return
                self._offset += len(chunk[: cut + 1].encode("utf-8"))
                for raw in chunk[: cut + 1].splitlines():
                    self._say(raw)
        except Exception:   # noqa: BLE001 — narration never interrupts a run
            return

    def _say(self, raw: str) -> None:
        if not raw.strip():
            return
        try:
            line = json.loads(raw)
        except ValueError:
            return
        if not isinstance(line, Mapping):
            return
        slug = str(line.get("slug", ""))
        shelf = self._shelf(line) if line.get("to") == "packaged" else None
        sentence = narrate(line, seen=self._seen, shelf=shelf)
        if sentence is None:
            return
        label = _slot_label(slug, self.batch_id, self.size)
        print(f">> {label}: {sentence}", file=self.out, flush=True)
        now = next_stage_line(str(line.get("to")))
        if now is not None:
            print(f"   {' ' * len(label)}  {now}", file=self.out, flush=True)

    def _shelf(self, line: Mapping) -> str:
        """`games/<game slug>/` for a packaged slot, MATCHED BY CONTENT.

        The ledger key is the SLOT (`…-s001`) and the shelf is named after the
        GAME, and the two cannot be derived from each other: S1 names the corpus
        dir after the spec's own slug, which is exactly why `_discover_spec_dir`
        links them through `idea.json` rather than by convention.

        So this links them the same way — through content. The ledger line
        carries the packaged build's `hashes.game`, and `s6_package
        .shelf_entry_hash` reads the same hash off each shelf entry's manifest;
        the entry that matches IS this slot's game. A name that cannot be
        matched degrades to the shelf root rather than guessing, because a
        confident wrong directory is worse than a vague right one.
        """
        fallback = f"{GAMES_DIRNAME}/"
        try:
            from .s6_package import shelf_entry_hash
            wanted = (line.get("hashes") or {}).get("game")
            if not wanted or not self.games_root.is_dir():
                return fallback
            for entry in sorted(self.games_root.iterdir()):
                if entry.is_dir() and shelf_entry_hash(entry.name, self.games_root) == wanted:
                    return f"{GAMES_DIRNAME}/{entry.name}/"
        except Exception:   # noqa: BLE001 — a name we cannot derive is not worth dying for
            return fallback
        return fallback


# --- the closing summary -----------------------------------------------------


def summary_lines(cfg: Mapping, report: Mapping | None) -> list[str]:
    """Games promoted, total cost, parked slots with reasons (contract P-4 §4).

    Built from `batch-report.json`, the file the run just wrote — not from a
    tally kept alongside it, which could disagree with the record.
    """
    if report is None:
        return ["(no batch report was written — nothing to summarise)"]
    batch_id = str(((cfg.get("batch") if isinstance(cfg, Mapping) else None) or {}).get("id")
                   or "this batch")
    lines = ["", f"--- {batch_id}: what happened ---"]

    slots = list(report.get("slots") or ())
    packaged = [row for row in slots if row.get("state") == "packaged"]
    if packaged:
        lines.append(f"games finished and shelved: {len(packaged)}")
        for row in packaged:
            spec_dir = (row.get("paths") or {}).get("spec_dir")
            lines.append(f"  {_shelf_entry(spec_dir)}")
    else:
        lines.append("games finished and shelved: none this run")

    # "Re-run to carry on" is TRUE ONLY of a slot that still has a stage to
    # run. A parked, pulled or dead slot is terminal (`orchestrator.TERMINAL`)
    # and re-running the batch will not touch it, so telling the operator to
    # re-run would send them to wait for something that is never going to move.
    terminal = set(orchestrator.TERMINAL)
    unfinished = [row for row in slots
                  if row.get("state") != "packaged" and row.get("state") not in terminal]
    stopped = [row for row in slots
               if row.get("state") != "packaged" and row.get("state") in terminal]
    if unfinished:
        lines.append("not finished yet (re-run the same command to carry on):")
        for row in unfinished:
            lines.append(f"  {row.get('slug')} — got as far as: {row.get('state')}")
    if stopped:
        lines.append("stopped for good this run:")
        for row in stopped:
            lines.append(f"  {row.get('slug')} — {row.get('state')}")

    for entry in report.get("parked") or ():
        lines.append(f"parked: {entry.get('slug')} — {entry.get('reason')}")
        lines.append("  nothing was deleted; the game's files are still on disk")

    total = (report.get("cost") or {}).get("total") or {}
    usd = total.get("usd")
    lines.append(f"total cost: {'not reported' if usd is None else f'${usd:.2f}'} "
                 f"({total.get('tokens_in')} tokens in / {total.get('tokens_out')} out)")
    if report.get("cost_note"):
        lines.append(f"  {report['cost_note']}")
    return lines


def _shelf_entry(spec_dir: object) -> str:
    if not isinstance(spec_dir, str) or not spec_dir:
        return f"{GAMES_DIRNAME}/ (name unavailable)"
    try:
        from .s6_package import game_slug
        return f"{GAMES_DIRNAME}/{game_slug(Path(spec_dir) / orchestrator.WORKER_DIRNAME)}/"
    except Exception:   # noqa: BLE001 — a summary must not die naming a directory
        return f"{GAMES_DIRNAME}/ (name unavailable)"


def read_report(cfg: Mapping) -> dict | None:
    """`out/batches/<id>/batch-report.json`, or None when there is nothing to read.

    Tolerant on purpose: this runs AFTER the batch, and a run that finished must
    not end in a traceback because its summary could not find a file.
    """
    try:
        path = batch_dir(cfg) / orchestrator.BATCH_REPORT_NAME
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, KeyError):
        return None
    return data if isinstance(data, dict) else None


# --- the subcommands ---------------------------------------------------------


def _resume_command(batch_id: str) -> str:
    return f"{PROG} resume {batch_id}"


def _real_run_command(args: argparse.Namespace) -> str:
    """The same `run` the caller just rehearsed, minus `--dry-run`.

    Printed at the end of a dry run so the next step is a copy-paste and not a
    reconstruction from memory. The batch NAME is deliberately not pinned into
    it: the rehearsal took no name, so the real run allocates one then.
    """
    parts = [PROG, "run", "--driver", args.driver, "--games", str(args.games)]
    for flag, value in (("--tiers", args.tiers), ("--name", args.name),
                        ("--seed", args.seed), ("--workers", args.workers),
                        ("--id", args.id)):
        if value is not None:
            parts += [flag, str(value)]
    if args.yes:
        parts.append("--yes")
    return " ".join(parts)


def _run_orchestrator(config_path: Path, *, status: bool = False) -> int:
    """The ONE place this CLI hands control to the pipeline.

    `orchestrator.main` is reached through the MODULE, not through a name bound
    at import: that keeps the single seam a caller (or a test) can replace, and
    it keeps this CLI honest about invoking the orchestrator the same way the
    documented command line does — on a config PATH, never on an in-memory dict.
    """
    argv = ["--config", str(config_path)]
    if status:
        argv.append("--status")
    return orchestrator.main(argv)


def cmd_run(args: argparse.Namespace) -> int:
    # `--games` is checked FIRST because every other flag is measured against
    # it: a `--tiers` error that says "1 tier but 0 games" sends the reader
    # after the wrong flag.
    if args.games < 1:
        raise CliError(f"--games must be 1 or more; got {args.games}")
    if args.workers is not None:
        if args.workers < 1:
            raise CliError(f"--workers must be 1 or more; got {args.workers}")
        if args.workers > args.games:
            # Not an error — a worker with no game is simply idle — but it must
            # be said, because the resolved config will carry the smaller number
            # and a silent clamp reads as the flag having been ignored.
            print(f"{PROG}: --workers {args.workers} is more games at once than there are "
                  f"games ({args.games}); building {args.games} at once.")

    tiers = None
    if args.tiers is not None:
        tiers = [part.strip() for part in args.tiers.split(",") if part.strip()]
        if len(tiers) != args.games:
            raise CliError(
                f"--tiers names {len(tiers)} tier(s) but --games asks for {args.games} game(s).\n"
                f"  Give one tier per game (for {args.games}: --tiers "
                f"{','.join(['t1'] * args.games)}), or leave --tiers out and let each game "
                "draw its own."
            )

    cfg = build_config(driver=args.driver, games=args.games, tiers=tiers,
                       name=args.name, seed=args.seed, workers=args.workers,
                       batch_id=args.id)
    batch_id = cfg["batch"]["id"]
    text = render_config(cfg)

    print(f"{PROG}: batch {batch_id} — {args.games} game(s), "
          f"{args.driver} writing them, seed {cfg['batch']['seed']}")
    orchestrator_block = cfg.get("orchestrator") or {}
    if orchestrator_block.get("parallel_slots"):
        print(f"{PROG}: {orchestrator_block['workers']} of them are built at the same "
              "time, each in its own process (contract P-5). Each game's own progress "
              f"is in out/batches/{batch_id}/<slot>.slot.log.")
    if args.dry_run:
        print()
        print("--- the settings this batch would run under ---")
        print(text.rstrip("\n"))
        print("--- end of settings ---")

    print()
    print("Checking this machine before anything is spent:")
    checks = preflight(cfg, text, args.driver)
    for check in checks:
        print(check.line())
    failures = [check for check in checks if check.failed]
    if failures:
        print()
        print(f"{PROG}: NOT starting — {len(failures)} thing(s) above need fixing first. "
              "Nothing was written and nothing was spent.", file=sys.stderr)
        return 1

    if args.dry_run:
        # A REHEARSAL TAKES NOTHING. Writing the config here would create
        # `out/batches/<id>/`, and that directory IS how an id is taken (see
        # `known_batch_ids`) — so three rehearsals would burn three batch names
        # and push the seed up by three, which is a real defect for the one
        # command a cautious stranger is most likely to run twice. The
        # materialization itself is still fully inspectable: the bytes are
        # above, and `build_config` / `render_config` / `write_config` are the
        # importable seam that produces them.
        print()
        print(f"dry run: nothing was written and nothing was spent. The name "
              f"{batch_id} and seed {cfg['batch']['seed']} are still free.")
        print(f"  Run it for real with: {_real_run_command(args)}")
        return 0

    path = write_config(cfg, text)
    print()
    print(f"settings written to {path}")

    if not args.yes and not _confirm():
        print(f"{PROG}: not started. The settings above are kept at {path}; "
              f"start them any time with `{_resume_command(batch_id)}`.")
        return 0

    return _drive(cfg, path)


def _confirm() -> bool:
    """The one prompt, skipped by `--yes` (contract P-4 §3).

    A non-interactive shell (CI, a pipe) cannot answer, so it is told to pass
    `--yes` rather than being guessed at: starting a batch that spends money
    because nobody was there to say no is not a default this CLI will take.
    """
    try:
        answer = input("Start the batch? This will spend money on model calls. [y/N] ")
    except EOFError:
        print()
        print(f"{PROG}: nothing is reading the keyboard, so I cannot ask. "
              "Re-run with --yes to start without being asked.", file=sys.stderr)
        return False
    return answer.strip().lower() in {"y", "yes"}


def _narrator_for(cfg: Mapping) -> LedgerNarrator | None:
    """A narrator for this config, or None when the config is too broken to narrate.

    NARRATION NEVER DECIDES WHETHER A RUN HAPPENS. A hand-edited
    `out/batches/<id>/config.yaml` with a missing `batch.seed` must be refused
    by the orchestrator's own validator, in the orchestrator's own words — not
    by this module crashing while working out what to call the games.
    """
    try:
        batch = cfg["batch"]
        return LedgerNarrator(batch_dir(cfg) / orchestrator.LEDGER_NAME,
                              batch_id=str(batch["id"]), size=int(batch["size"]))
    except (KeyError, TypeError, ValueError):
        return None


def _drive(cfg: Mapping, config_path: Path) -> int:
    """Run the batch with the narrator attached, and summarise it afterwards."""
    batch = cfg.get("batch") if isinstance(cfg, Mapping) else None
    batch_id = str((batch or {}).get("id") or config_path.parent.name)
    narrator = _narrator_for(cfg)
    print()
    print("Starting. This takes a while — a game is written, built, audited, gated and "
          "play-tested.")
    print("Press Ctrl-C at any time; you will not lose the work already done.")
    print()
    if narrator is not None:
        narrator.start()
    try:
        code = _run_orchestrator(config_path)
    except KeyboardInterrupt:
        # Stop the narrator FIRST (it is idempotent, and `finally` calls it
        # again) so the last transitions it is holding print above the
        # goodbye rather than after it.
        if narrator is not None:
            narrator.stop()
        print()
        print(f"{PROG}: stopped. NOTHING IS LOST — every finished stage is recorded on the "
              "batch's ledger,")
        print("  and that ledger IS the batch's state: a re-run picks every game up exactly "
              "where it stopped")
        print("  and never re-does a stage whose inputs have not changed. A half-finished "
              "stage is simply")
        print("  re-run; nothing that was already written is thrown away.")
        print(f"  Carry on with: {_resume_command(batch_id)}")
        return 130
    finally:
        if narrator is not None:
            narrator.stop()

    for line in summary_lines(cfg, read_report(cfg)):
        print(line)
    return code


def _config_for(batch_id: str) -> Path:
    """The config a known batch runs under — the PERSISTED one where there is one.

    `out/batches/<id>/config.yaml` is what this CLI writes and is the batch's
    own record. Batches that predate the CLI were driven from a hand-written
    `config/<id>.yaml`, and those must keep working: `status b001-pilot` is a
    reasonable thing to type on this repo today.
    """
    persisted = _batches_root() / batch_id / BATCH_CONFIG_NAME
    if persisted.is_file():
        return persisted
    handwritten = _config_dir() / f"{batch_id}.yaml"
    if handwritten.is_file():
        return handwritten
    known = sorted(known_batch_ids())
    listing = "\n    ".join(known) if known else "(none yet — run `arc-games run` first)"
    raise CliError(
        f"no batch called {batch_id!r} on this machine.\n"
        f"  Batches I can see:\n    {listing}"
    )


def cmd_resume(args: argparse.Namespace) -> int:
    path = _config_for(args.batch_id)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise CliError(f"{path} did not parse to a mapping — it is not a usable config")
    print(f"{PROG}: carrying on with {args.batch_id}, from {path}")
    return _drive(cfg, path)


def cmd_status(args: argparse.Namespace) -> int:
    path = _config_for(args.batch_id)
    return _run_orchestrator(path, status=True)


def cmd_unpark(args: argparse.Namespace) -> int:
    """Lift one parked slot's park — contract E-5's operator tool.

    It is `resume`'s shape on purpose: `_config_for` resolves the batch, so a
    pre-P-4 hand-written `config/<id>.yaml` keeps working and `status`, `resume`
    and `unpark` all answer to the same batch ids.

    IT RUNS NOTHING. The lift is a recorded operator act and the resume is the
    machine (the `gen.worker --resync` separation), so this prints the state the
    slot was restored to and then the `resume` line that will actually re-run
    that stage. Nothing is spent here, and nothing on disk is touched but the
    ledger's one new line.

    Every refusal the orchestrator raises — unknown slug, a slot that is not
    parked, a blank reason, a ledger that does not replay — arrives as a
    `ValueError` and is reprinted in this CLI's own voice at exit 1, with
    nothing appended. Exit 0 means a line was written.
    """
    path = _config_for(args.batch_id)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise CliError(f"{path} did not parse to a mapping — it is not a usable config")
    try:
        lifted = orchestrator.unpark_slot(cfg, slug=args.slug, reason=args.reason)
    except (ValueError, KeyError) as exc:
        # KeyError too: a config missing a `batch` block is refused by the
        # orchestrator's own validator, in its words, and must read as a refusal
        # here rather than as a traceback.
        raise CliError(f"cannot unpark {args.slug}: {exc}") from exc
    print(f"{PROG}: {lifted['slug']} is out of the park and back at "
          f"{lifted['to']} — {_runs_next(lifted['to'])}")
    print(f"  it was parked for: {lifted['park_reason']}")
    print(f"  your reason is on the ledger: {lifted['ledger']}")
    print("  NOTHING RAN. The lift is recorded; the work is the resume, and the game goes "
          "back through")
    print("  the ordinary checks with its whole history standing — it can park again.")
    print(f"  Carry on with: {_resume_command(lifted['batch_id'])}")
    return 0


def _runs_next(state: str) -> str:
    """What the next resume will do from `state`, in the narrator's own voice."""
    return next_stage_line(state) or f"nothing runs from {state!r}"


def find_play_server() -> Path | None:
    """The play server: the VENDORED copy, else a sibling duckWM checkout.

    Contract L-2 vendored the player into `tools/play/` and added the §7
    layout-seed picker there, so the file this prefers is tracked and a clone
    always has it — which is what makes `play` work with no duckWM on disk at
    all. The sibling path stays as a fallback for a checkout where `tools/play/`
    is somehow missing, and None still means "neither", so the caller can say
    exactly what it expected to find.
    """
    if VENDORED_PLAY_SERVER.is_file():
        return VENDORED_PLAY_SERVER
    server = DUCKWM_SIBLING / PLAY_SERVER_REL
    return server if server.is_file() else None


def play_player() -> dict:
    """What `arc-games play` will actually launch: `{server, interpreter}`.

    ONE resolution with TWO readers (contract H-1 item 4): `cmd_play`, which
    runs it, and `gen.s6_package.play_command`, which PRINTS it as the
    packaged-game hint. A hint naming a different player from the one the
    command starts is the defect that item is about, and two copies of this
    four-line choice is how it would come back.

    The vendored player is this repo's own code and runs on this repo's
    interpreter; only the duckWM fallback wants duckWM's venv. `server` is None
    when neither exists — `find_play_server`'s own answer, passed through.
    """
    server = find_play_server()
    interpreter = sys.executable
    if server is not None and server != VENDORED_PLAY_SERVER:
        python = DUCKWM_SIBLING / PLAY_PYTHON_REL
        if python.exists():
            interpreter = str(python)
    return {"server": server, "interpreter": interpreter}


def cmd_play(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else _games_root()
    if not root.is_dir():
        raise CliError(
            f"there are no games at {root}.\n"
            "  `{PROG} play` opens the shared shelf, which fills up as batches finish. "
            "Point it somewhere else with --root PATH.".replace("{PROG}", PROG)
        )
    entries = sorted(path.parent.parent.name for path in root.glob("*/*/metadata.json"))

    player = play_player()
    server = player["server"]
    if server is None:
        print(f"{PROG}: I cannot find the game player — and it ships with this repo, "
              "so something is missing from your checkout.", file=sys.stderr)
        print(f"  I looked for: {VENDORED_PLAY_SERVER}", file=sys.stderr)
        print(f"  and then for : {DUCKWM_SIBLING / PLAY_SERVER_REL}", file=sys.stderr)
        print("  Restore tools/play/ (`git checkout tools/play`), or put a duckWM "
              "checkout next to this one so both share a parent directory.", file=sys.stderr)
        print(f"  Your games are fine — they are at {root} "
              f"({len(entries)} of them) either way.", file=sys.stderr)
        return 2

    interpreter = player["interpreter"]
    env = dict(os.environ, PLAY_GAMES_DIR=str(root))
    print(f"{PROG}: serving {len(entries)} game(s) from {root}")
    for name in entries:
        print(f"  {name}")
    print(f"  running: PLAY_GAMES_DIR={root} {interpreter} {server}")
    print("  Press Ctrl-C to stop the player.")
    try:
        return subprocess.call([interpreter, str(server)], env=env, cwd=str(server.parent))
    except KeyboardInterrupt:
        print()
        print(f"{PROG}: player stopped.")
        return 0


# --- the parser --------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Generate ARC-AGI-3 games. `%(prog)s run --driver claude --games 2` is the "
            "whole thing: it writes the settings for you, checks your machine, and then "
            "builds, audits and play-tests each game."
        ),
        epilog=(
            "The settings each batch ran under are kept in out/batches/<batch>/config.yaml. "
            "If you want to change something the flags do not cover, copy "
            "config/template.yaml, edit it, and drive it with "
            "`python -m gen.orchestrator --config <your file>`."
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    run = sub.add_parser(
        "run", help="build new games",
        description="Build new games from scratch. Everything is chosen for you except "
                    "the two things only you can know: who writes the games, and how many.",
    )
    run.add_argument("--driver", required=True, choices=sorted(DRIVER_CHOICES),
                     help="who writes and builds the games: `claude` (the claude CLI, on "
                          "your own login) or `openai` (the codex CLI)")
    run.add_argument("--games", required=True, type=int, metavar="N",
                     help="how many games to attempt")
    run.add_argument("--tiers", default=None, metavar="t1,t2,...",
                     help="pin one difficulty tier per game (t1 simplest .. t3). "
                          "Leave it out and each game draws its own.")
    run.add_argument("--name", default=None, metavar="WORD",
                     help="a word to tack onto the batch name, so you can tell today's "
                          "batches apart")
    run.add_argument("--seed", default=None, type=int, metavar="N",
                     help="the random seed (default: one higher than any this repo has "
                          "used). The same seed draws the same ideas.")
    run.add_argument("--workers", default=None, type=int, metavar="N",
                     help="how many games to build at the same time, each in its own "
                          "process (default 1; more than --games is capped at --games)")
    run.add_argument("--id", default=None, metavar="BATCH_ID",
                     help="name the batch yourself instead of taking the automatic name; "
                          "refused if that name is already in use")
    run.add_argument("--yes", action="store_true",
                     help="do not ask for confirmation before starting")
    run.add_argument("--dry-run", action="store_true",
                     help="print the settings and check the machine, then stop without "
                          "spending anything")
    run.set_defaults(func=cmd_run)

    resume = sub.add_parser(
        "resume", help="carry on with a batch that stopped",
        description="Carry on with a batch. Nothing is repeated: every stage whose inputs "
                    "have not changed is skipped.",
    )
    resume.add_argument("batch_id", metavar="BATCH_ID")
    resume.set_defaults(func=cmd_resume)

    status = sub.add_parser(
        "status", help="show what a batch has done so far",
        description="Show a batch's progress. Reads the ledger on disk; runs nothing and "
                    "spends nothing.",
    )
    status.add_argument("batch_id", metavar="BATCH_ID")
    status.set_defaults(func=cmd_status)

    # Contract E-5. Beside `resume`/`status` because it reads a batch the same
    # way they do (`_config_for`), and spelled as a verb on one slot because
    # that is what it is: a person deciding that one parked game carries on.
    unpark = sub.add_parser(
        "unpark", help="let a parked game carry on",
        description="Lift one game's park so the next `resume` picks it up again. A park is "
                    "not a death — nothing was deleted — and this writes down that you "
                    "lifted it and why. It runs nothing and spends nothing by itself.",
    )
    unpark.add_argument("batch_id", metavar="BATCH_ID")
    unpark.add_argument("slug", metavar="SLUG",
                        help="the parked game, as `status` names it (e.g. b005r2-auto-s001)")
    unpark.add_argument("--reason", required=True, metavar="TEXT",
                        help="why you are lifting it — this goes on the batch's ledger "
                             "beside the reason it parked")
    unpark.set_defaults(func=cmd_unpark)

    play = sub.add_parser(
        "play", help="play the finished games in a browser",
        description="Open the finished games in the browser player.",
    )
    play.add_argument("--root", default=None, metavar="PATH",
                      help=f"where the games are (default: {GAMES_DIRNAME}/, the shared shelf)")
    play.set_defaults(func=cmd_play)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:   # argparse exits 2 on usage; keep one error code
        return 0 if exc.code == 0 else 1
    if getattr(args, "func", None) is None:
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except CliError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print()
        print(f"{PROG}: stopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":   # pragma: no cover - `python -m gen.cli`
    sys.exit(main())
