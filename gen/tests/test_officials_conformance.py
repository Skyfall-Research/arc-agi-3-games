"""B2 acceptance: every signed official passes the worker conformance contracts.

Run: .venv/bin/python -m pytest gen/tests/test_officials_conformance.py -q

The 25 officials are the calibration corpus. A contract that a real official
violates is a contract the generator has no business imposing on its own
workers — so this suite runs the WORKER-side checks
(worker-template/tests/_contracts.py, loaded at runtime) against the officials
unchanged, and every failure is evidence about the contract, not just the game.

Runtime checks are slow by design on the big officials (ka59 is 41k lines);
there are deliberately no timeouts. Each game class is loaded at most once per
session and cached — instances are cheap after that.

Side effect: the action probe's latency samples are summarised to a JSON
file at session end — under the session's pytest tmp dir by default, so a
suite run leaves the repo's `out/` byte-identical (contract OS-2 FRONT C.2,
the hermeticity fix). Set `OFFICIALS_LATENCY_JSON=<path>` to write the
calibration artifact somewhere real (its historical home was
out/calibration/officials-latency.json).
"""

from __future__ import annotations

import json
import os
import statistics
from pathlib import Path

import pytest

from gen.config import REPO_ROOT, load_config
from gen.officials import Official, discover_officials, load_contracts, load_official_class

CONFIG = "config/b001-pilot.yaml"
# OS-2 FRONT C.2: no default write into the repo — unset env = the session tmp dir.
LATENCY_JSON_ENV = "OFFICIALS_LATENCY_JSON"
LATENCY_JSON_NAME = "officials-latency.json"

# perform_action latency, seconds, per slug — filled by test_action_probe and
# summarised by the session finaliser below.
LATENCY: dict[str, list[float]] = {}

# Collection-time discovery: the parametrisation needs the slugs before any
# fixture runs. Discovery is fail-loud, so a broken corpus errors at collection
# rather than 25 times over.
_CFG = load_config(CONFIG)
_OFFICIALS = discover_officials(_CFG)

official_param = pytest.mark.parametrize(
    "official", _OFFICIALS, ids=[o.slug for o in _OFFICIALS]
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def cfg() -> dict:
    return _CFG


@pytest.fixture(scope="session")
def officials() -> list[Official]:
    return _OFFICIALS


@pytest.fixture(scope="session")
def contracts():
    """The worker conformance contracts, loaded from the worker template."""
    return load_contracts()


@pytest.fixture(scope="session")
def game_class():
    """Slug-keyed class cache: exec-load each official at most once per session."""
    cache: dict[str, type] = {}

    def _get(official: Official) -> type:
        if official.slug not in cache:
            cache[official.slug] = load_official_class(official.py_path)
        return cache[official.slug]

    return _get


@pytest.fixture(scope="session")
def game_source():
    """Slug-keyed source cache for the static (text-level) contracts."""
    cache: dict[str, str] = {}

    def _get(official: Official) -> str:
        if official.slug not in cache:
            cache[official.slug] = official.py_path.read_text(encoding="utf-8")
        return cache[official.slug]

    return _get


def _detail(official: Official, kind: str, violations: list[str]) -> str:
    """Assertion body: the violations, verbatim, one per line."""
    joined = "\n  - ".join(violations)
    return (
        f"{official.game_id} ({official.py_path}): {len(violations)} {kind} "
        f"violation(s):\n  - {joined}"
    )


# --------------------------------------------------------------------------- #
# static contracts — source text only, no import
# --------------------------------------------------------------------------- #


@official_param
def test_static_score_ban(contracts, game_source, official: Official):
    violations = contracts.score_mutation_violations(game_source(official), official.py_path.name)
    assert violations == [], _detail(official, "score-mutation", violations)


@official_param
def test_static_lifecycle_ban(contracts, game_source, official: Official):
    violations = contracts.lifecycle_override_violations(
        game_source(official), official.py_path.name
    )
    assert violations == [], _detail(official, "lifecycle-override", violations)


@official_param
def test_static_env_ban(contracts, game_source, official: Official):
    violations = contracts.env_tampering_violations(game_source(official), official.py_path.name)
    assert violations == [], _detail(official, "env-tampering", violations)


# --------------------------------------------------------------------------- #
# runtime contracts — the game class is loaded and driven
# --------------------------------------------------------------------------- #


@official_param
def test_loads(contracts, game_class, official: Official):
    cls = game_class(official)
    with contracts.quiet():  # officials print on instantiation
        game = cls()
    class_game_id = getattr(game, "game_id", None)
    assert isinstance(class_game_id, str) and class_game_id, (
        f"{official.slug}: instantiated {cls.__name__} has no usable game_id "
        f"({class_game_id!r})"
    )
    # ADJUDICATED (D8, 2026-09-21): all 25 officials pass the BARE SLUG to
    # ARCBaseGame.__init__ while metadata.json carries "<slug>-<variant>" —
    # a uniform corpus convention, so equality-with-metadata was a wrong
    # test. The contract: class game_id == slug; metadata game_id stays the
    # reporting identity. (Recorded in GEN design/calibration.md, B2 section.)
    assert class_game_id == official.slug, (
        f"{official.slug}: class game_id {class_game_id!r} != slug {official.slug!r} "
        f"(metadata game_id {official.game_id!r})"
    )


@official_param
def test_reset_validity(contracts, game_class, official: Official):
    violations = contracts.reset_violations(game_class(official))
    assert violations == [], _detail(official, "reset-validity", violations)


@official_param
def test_action_probe(contracts, game_class, official: Official):
    violations, latencies = contracts.action_probe_violations(game_class(official))
    # Record before asserting: a failing probe still contributes its samples.
    LATENCY.setdefault(official.slug, []).extend(float(x) for x in latencies)
    assert violations == [], _detail(official, "action-probe", violations)


@official_param
def test_reset_restores(contracts, game_class, official: Official):
    violations = contracts.reset_restore_violations(game_class(official))
    assert violations == [], _detail(official, "reset-restore", violations)


@official_param
def test_double_reset(contracts, game_class, official: Official):
    violations = contracts.double_reset_violations(game_class(official))
    assert violations == [], _detail(official, "double-reset", violations)


# --------------------------------------------------------------------------- #
# session finaliser — latency artefact + table
# --------------------------------------------------------------------------- #


def _print_uncaptured(config, text: str) -> None:
    """Print so the table survives pytest's capture, with or without -s."""
    capman = config.pluginmanager.getplugin("capturemanager")
    if capman is None:
        print(text)
        return
    with capman.global_and_fixture_disabled():
        print(text)


def _latency_json(session_tmp: Path) -> Path:
    """Where the summary goes: the env override, else the session tmp dir."""
    override = os.environ.get(LATENCY_JSON_ENV)
    if override:
        path = Path(override)
        return path if path.is_absolute() else REPO_ROOT / path
    return session_tmp / LATENCY_JSON_NAME


def _write_latency_report(config, session_tmp: Path) -> None:
    summary = {
        slug: {
            "n": len(samples),
            "max_s": max(samples),
            "median_s": statistics.median(samples),
        }
        for slug, samples in sorted(LATENCY.items())
        if samples
    }
    if not summary:
        return

    latency_json = _latency_json(session_tmp)
    latency_json.parent.mkdir(parents=True, exist_ok=True)
    with latency_json.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
        fh.write("\n")

    lines = [
        "",
        f"officials perform_action latency ({len(summary)} game(s)) -> {latency_json}",
        f"  {'slug':<6} {'n':>4} {'max ms':>10} {'median ms':>11}",
    ]
    for slug, row in summary.items():
        lines.append(
            f"  {slug:<6} {row['n']:>4} {row['max_s'] * 1e3:>10.2f} "
            f"{row['median_s'] * 1e3:>11.2f}"
        )
    worst_slug, worst = max(summary.items(), key=lambda kv: kv[1]["max_s"])
    lines.append(f"  global max: {worst['max_s'] * 1e3:.2f} ms ({worst_slug})")
    _print_uncaptured(config, "\n".join(lines))


@pytest.fixture(scope="session", autouse=True)
def _latency_report(request, tmp_path_factory):
    yield
    _write_latency_report(request.config, tmp_path_factory.getbasetemp())
