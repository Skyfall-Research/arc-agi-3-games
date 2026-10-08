"""B9 acceptance: the S5/S3d smoke battery + the OpenRouter driver.

Run: .venv/bin/python -m pytest gen/tests/test_b9_battery.py -q

Written FROM THE B9 CONTRACT and from canon, never from the implementation:
`gen/s5_battery.py` and the scoped `gen/backends.py` addition were built in
parallel with this file by another agent and none of their source was read.
Every expectation below is either a name/shape the contract froze or a canon
rule cited at its source:

  architecture.md §3 "S3d — the battery" — executor = the duck via
      OpenRouter, each level budgeted at EXACTLY 5x baseline, `battery.passes`
      rollouts per game, crashes route to S2, smoke mode at pilot scale.
  decisions.md D8  — the 5x-baseline per-level budget convention (519 of 590
      public death-levels at exactly 5.00x); `BATTERY_MARGIN` is its one home.
  decisions.md D9  — calibration is FLEET-level only: per-game numbers are
      recorded, never a gate. Nothing here asserts a difficulty target.
  decisions.md D12 — the battery player is our own agent over OpenRouter.
  decisions.md D22 — pilot ruling: smoke-scale battery with a tiny cap, so
      the pilot never blocks on the OpenRouter budget.

NO NETWORK ANYWHERE. An autouse fixture replaces `urllib.request.urlopen` and
`socket.create_connection` with raisers for every test in this file; the
driver group installs its own fake `urlopen` on top. The same fixture DELETES
`OPENROUTER_API_KEY` from the environment before every test, so a real key
present in the runner's shell can never reach a test; the tests that need the
variable present set an obviously fake value through monkeypatch and then
assert that value never appears in an exception, a log record, or stdout.

FIXTURE — gen/tests/fixtures/s5_crash/, authored for this file and
engine-verified by group 0 below (driven raw: RESET ok, actions 1-3 ok, level
1 completed at action 2, action 4 raises RuntimeError inside `step()`).
S4 is never run on it — the cap probe would trip the fault — so its
`metadata.json` is hand-built here in S4's own frozen shape.

The two S4 workers are real stage-4 outputs: `run_s4` is executed in-test on
`fixtures/s4_workers/capped_generous` and `toy_worker` at seed 7 (both
verdict `fit`), and the perfect policy replays their `actions/level-*.json`.

CONTRACT AMBIGUITIES this file had to take a position on (reported to the
lead, never invented quietly):
  A. Group 10 says the CLI's fake driver is installed "by monkeypatching the
     resolver A exposes" — the contract never names that resolver.
     `_install_fake_driver` therefore patches EVERY name the frozen interface
     makes visible (`gen.s5_battery.OpenRouterDriver` when the module imported
     it, `gen.backends.OpenRouterDriver`, and `DRIVERS["openrouter"]`), asserts
     at least one real attribute was replaced, and relies on the autouse
     network guard to fail loudly rather than silently dial out if a future
     resolver bypasses all three.
  B. Row/level/pass indexing is not frozen. Levels are asserted 1-INDEXED,
     because the contract requires the CSV's first three columns to be the
     house dialect's own (`agent-level.csv`, whose `level` column starts at 1)
     and S4's `actions/level-<i>.json` is 1-indexed too. The `pass` index is
     NOT pinned to 0 or 1: only that the pass keys are consecutive ints and
     that `crash.pass` matches a row's.
  C. `aggregate.per_level` is not said to cover unplayed levels, so group 4
     asserts only the level-1 entry plus `levels_total` / the CSV's own
     row count.
  D. Whether a crash or a token-cap abort stops the remaining passes is not
     frozen; these tests assert `passes.completed <= passes.requested` and
     the surviving rows, never a pass count.
  E. `ChatResult.raw` is typed `dict` with no layout, so the driver group
     accepts either the parsed response itself or a dict carrying it as a
     value.
  F. The exact OpenRouter usage field names are explicitly NOT frozen ("the
     fakes freeze OUR ChatResult shape, not OpenRouter's"). So the driver
     group asserts the frozen half only: a response with NO usage block gives
     `tokens_in/tokens_out/usd_cost is None`, a partial usage block leaves the
     absent fields None, and present counts are ints. It never asserts that a
     particular OpenRouter field maps to a particular number.
  G. `None` in the CSV is read as the empty string (what `csv.writer` emits);
     `battery-levels.csv`'s `tokens`/`usd` columns are battery-level totals
     with no frozen per-row meaning, so they are only type-checked.
  H. "ACTION9\\nACTION2" (a malformed ACTION line followed by a legal one) is
     not decidable from "the FIRST such line in the reply wins" and is NOT
     tested. Neither is a lowercase reply, nor an ACTION token embedded in
     prose.
  I. Group 3's prose "aggregate ratios == g under budget" inverts the frozen
     formula (`actions_ratio = best_actions/baseline`, i.e. 1/g). The FROZEN
     formula is what is asserted.
  J. `load_battery_metadata` on an absent file may raise FileNotFoundError or
     ValueError (both are "refuse"); a `verdict != "fit"` must be ValueError.
  K. `main()` may return its exit code or raise SystemExit with it; `_cli`
     accepts either.
  L. The `game-over` end reason has no fixture that reaches GAME_OVER inside
     a 5x budget, so it is checked only as a member of the frozen vocabulary.
  M. `actions_ratio`'s PRECISION is not frozen — only its formula. The shipped
     stage rounds it, so the tolerance here is abs=1e-4, which still rejects
     the inverse reading (every true ratio is < 1, every inverse is > 1).
  N. `passes.completed` has no frozen meaning. The shipped stage reports 0 for
     a battery whose three passes all ended `protocol-failure` (i.e. "ran to a
     clean finish", not "was attempted"). Nothing here depends on either
     reading: the protocol group counts passes through the rows instead.
"""

from __future__ import annotations

import csv
import dataclasses
import email.message
import io
import json
import logging
import shutil
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Self

import pytest
from arcengine import ActionInput, GameAction

from gen import backends, s5_battery
from gen.backends import (
    OPENROUTER_KEY_ENV,
    OPENROUTER_URL,
    ChatResult,
    DriverError,
    OpenRouterDriver,
)
from gen.config import load_config
from gen.frames import _fresh_game, _hex_row, _perform, _reset, settled_grid
from gen.s2_implement import parse_token_cap
from gen.s3_static import load_worker_classes
from gen.s4_baselines import BATTERY_MARGIN, run_s4
from gen.s5_battery import (
    CSV_COLUMNS,
    END_REASONS,
    SCHEMA_VERSION,
    STATUS_COMPLETE,
    STATUS_CRASH,
    STATUS_PROTOCOL,
    STATUS_TOKEN_CAP,
    load_battery_metadata,
    main,
    parse_reply,
    run_battery,
    write_levels_csv,
)

TESTS = Path(__file__).resolve().parent
TOY = TESTS / "toy_worker"
GENEROUS = TESTS / "fixtures/s4_workers/capped_generous"
CRASH = TESTS / "fixtures/s5_crash"
PILOT_CONFIG = "config/b001-pilot.yaml"

#: the S4 seed every in-test stage-4 run uses (both workers: verdict `fit`).
S4_SEED = 7

#: never a real key — set through monkeypatch, asserted absent from output.
FAKE_KEY = "sk-or-v1-FAKE-KEY-DO-NOT-USE-0000000000000000"

#: the s5_crash fixture's authored numbers (fixtures/s5_crash/game.py header).
CRASH_GAME_ID = "s5-crash-board"
CRASH_SOLVER = (2, 2, 2)
CRASH_BASELINES = (6, 6, 6)
CRASH_AFTER = 4
CRASH_MARKER = "s5-crash"

# Frozen report layout (B9 contract §"Semantics" step 7).
REPORT_KEYS = {
    "schema_version",
    "stage",
    "game_id",
    "worker",
    "model",
    "passes",
    "rows",
    "aggregate",
    "tokens",
    "usd_total",
    "status",
    "crash",
    "config",
    "versions",
    "paths",
}
ROW_KEYS = {"pass", "level", "baseline", "budget_5x", "actions_used", "completed", "end_reason"}
AGGREGATE_KEYS = {"per_level", "levels_total", "best_levels_completed"}
PER_LEVEL_KEYS = {"level", "baseline", "n_passes", "n_completed", "best_actions", "actions_ratio"}
TOKENS_KEYS = {"tokens_in", "tokens_out", "total", "cap", "estimated"}
PASSES_KEYS = {"requested", "completed"}
# LEAD-CORRECTED PIN (contract D-3): "smoke" removed — an inert stamp that
# only printed itself back (the readiness audit's finding, ruled by the operator).
CONFIG_KEYS = {"passes", "token_cap", "model_config"}

REPORT_NAME = "battery-report.json"
CSV_NAME = "battery-levels.csv"

_CFG = load_config(PILOT_CONFIG)


# --------------------------------------------------------------------------- #
# fakes — every chat in this file is injected; nothing dials out
# --------------------------------------------------------------------------- #


class _FakeChat:
    """A deterministic stand-in for `OpenRouterDriver.chat`.

    `prefix` replies are emitted once (protocol-retry scripting), then
    `replies` cycles forever — a perfect policy replays the same per-pass plan
    on every pass, so cycling is exactly right and needs no pass signal.
    Every call is recorded for the observation-content assertions.
    """

    def __init__(
        self,
        replies,
        *,
        prefix=(),
        tokens_in: int | None = 10,
        tokens_out: int | None = 5,
        usd: float | None = 0.001,
        model_reported: str | None = "fake/duck-v0",
    ) -> None:
        self.replies = list(replies)
        assert self.replies, "a fake chat needs at least one reply"
        self.prefix = list(prefix)
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.usd = usd
        self.model_reported = model_reported
        self.calls: list[dict] = []

    def __call__(self, *args, **kwargs) -> ChatResult:
        messages = args[0] if args else kwargs.get("messages")
        model = kwargs.get("model")
        self.calls.append({"messages": messages, "kwargs": dict(kwargs)})
        index = len(self.calls) - 1
        if index < len(self.prefix):
            text = self.prefix[index]
        else:
            text = self.replies[(index - len(self.prefix)) % len(self.replies)]
        return ChatResult(
            driver="openrouter",
            model_requested=model if isinstance(model, str) else "fake-model",
            model_reported=self.model_reported,
            text=text,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            usd_cost=self.usd,
            raw={"fake": True, "text": text},
        )


class _FakeResponse:
    """What a fake `urlopen` hands back: body + status, usable as a CM."""

    def __init__(self, payload: dict, status: int = 200) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.status = status
        self.headers = email.message.Message()

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status

    def info(self):
        return self.headers

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _install_urlopen(monkeypatch, handler):
    """Put `handler` wherever the driver could have bound `urlopen`.

    The contract says the driver tests "monkeypatch `urllib.request.urlopen`";
    the `from urllib.request import urlopen` spelling would bind a module-level
    name in `gen.backends` instead, so both are patched (ambiguity A's sibling).
    """
    monkeypatch.setattr(urllib.request, "urlopen", handler)
    monkeypatch.setattr(backends, "urlopen", handler, raising=False)


def _install_fake_driver(monkeypatch, chat) -> list[str]:
    """Install a fake OpenRouter driver at every name the contract exposes."""

    class _Fake:
        name = "openrouter"

        def __init__(self, *args, **kwargs) -> None:
            pass

        def preflight(self, *args, **kwargs) -> None:
            """The shipped resolver key-checks the driver before playing; the
            fake satisfies that call without touching the environment."""

        def chat(self, *args, **kwargs) -> ChatResult:
            return chat(*args, **kwargs)

    patched: list[str] = []
    if hasattr(s5_battery, "OpenRouterDriver"):
        monkeypatch.setattr(s5_battery, "OpenRouterDriver", _Fake)
        patched.append("gen.s5_battery.OpenRouterDriver")
    if hasattr(backends, "OpenRouterDriver"):
        monkeypatch.setattr(backends, "OpenRouterDriver", _Fake)
        patched.append("gen.backends.OpenRouterDriver")
    drivers = getattr(backends, "DRIVERS", None)
    if isinstance(drivers, dict) and "openrouter" in drivers:
        monkeypatch.setitem(drivers, "openrouter", _Fake)
        patched.append("gen.backends.DRIVERS['openrouter']")
    assert patched, "no OpenRouterDriver name to patch — the CLI injection seam moved"
    return patched


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _reply_for(record: dict) -> str:
    """One `actions/level-<i>.json` record as its frozen reply line."""
    action_id = int(record["id"])
    data = record.get("data") or {}
    if action_id == 6:
        return f"ACTION6 {int(data['x'])} {int(data['y'])}"
    return f"ACTION{action_id}"


def _replay_plan(out_dir: Path) -> list[str]:
    """The whole solver line as reply lines, levels in order (contract §3)."""
    actions_dir = Path(out_dir) / "actions"
    plan: list[str] = []
    index = 1
    while (actions_dir / f"level-{index}.json").is_file():
        records = json.loads((actions_dir / f"level-{index}.json").read_text(encoding="utf-8"))
        plan.extend(_reply_for(record) for record in records)
        index += 1
    assert plan, f"no actions/level-*.json under {actions_dir}"
    return plan


def _prompt_text(messages) -> str:
    """Every text chunk of a chat message list, joined."""
    assert isinstance(messages, list), f"messages must be a list, got {type(messages).__name__}"
    assert messages, "the observation must carry at least one message"
    parts: list[str] = []
    for message in messages:
        assert isinstance(message, dict), f"each message must be a dict, got {message!r}"
        assert "role" in message, f"each message needs a role: {sorted(message)}"
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for chunk in content:
                if isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                    parts.append(chunk["text"])
    return "\n".join(parts)


def _rows_by_pass(report: dict) -> dict:
    grouped: dict = {}
    for row in report["rows"]:
        assert set(row) == ROW_KEYS, f"row keys {sorted(row)} != frozen {sorted(ROW_KEYS)}"
        grouped.setdefault(row["pass"], []).append(row)
    return grouped


def _cfg_with(cfg: dict, **battery) -> dict:
    """A config copy with `battery.*` overrides — no new keys, ever."""
    out = dict(cfg)
    block = dict(cfg["battery"])
    for key, value in battery.items():
        assert key in block, f"{key!r} is not an existing battery key: {sorted(block)}"
        block[key] = value
    out["battery"] = block
    return out


def _opt_int(text: str):
    return None if text == "" else int(text)


def _opt_float(text: str):
    return None if text == "" else float(text)


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _reference_header(cfg: dict) -> list[str]:
    """The house CSV dialect's header — READ-ONLY, via `duckwm_docs`'s parent."""
    reference = Path(cfg["duckwm_docs"]).parent / "arc-agi-3-agents/out/agent-level.csv"
    assert reference.is_file(), f"dialect reference missing: {reference}"
    with reference.open(encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh))


def _cli(argv: list[str]) -> int:
    """`main(argv)`'s exit code, whether returned or raised (ambiguity K)."""
    try:
        code = main(argv)
    except SystemExit as exc:  # argparse-style exits carry the code
        code = exc.code
    assert isinstance(code, int), f"exit code must be an int, got {code!r}"
    return code


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _no_network_no_key(monkeypatch):
    """B9 SECRETS rule: no test in this file dials out or sees the real key."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("B9 tests must never open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.delenv(OPENROUTER_KEY_ENV, raising=False)


@pytest.fixture(scope="session")
def cfg() -> dict:
    return _CFG


@pytest.fixture(scope="session")
def s4(tmp_path_factory):
    """Cached real stage-4 output per worker: (worker, metadata, path, plan)."""
    workers = {"generous": GENEROUS, "toy": TOY}
    cache: dict[str, tuple[Path, dict, Path, list[str]]] = {}

    def _get(name: str):
        if name not in cache:
            worker = workers[name]
            out_dir = tmp_path_factory.mktemp("s4") / worker.name
            report = run_s4(worker, _CFG, seed=S4_SEED, out_dir=out_dir)
            assert report["verdict"] == "fit", f"{name}: S4 verdict {report['verdict']}"
            metadata_path = out_dir / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            cache[name] = (worker, metadata, metadata_path, _replay_plan(out_dir))
        return cache[name]

    return _get


@pytest.fixture
def crash_metadata(tmp_path, s4) -> Path:
    """Hand-built `metadata.json` for the crash fixture, in S4's frozen shape.

    Built from a REAL S4 metadata so every key S4 writes is present with the
    right type, then overridden with the fixture's authored numbers. S4 itself
    is never run on `s5_crash` — its cap probe would trip the fault.
    """
    template = dict(s4("generous")[1])
    template.update(
        {
            "game_id": CRASH_GAME_ID,
            "baseline_actions": list(CRASH_BASELINES),
            "g": [b / s for b, s in zip(CRASH_BASELINES, CRASH_SOLVER)],
            "solver_actions": list(CRASH_SOLVER),
            "caps": [None] * len(CRASH_BASELINES),
            "verdict": "fit",
        }
    )
    path = tmp_path / "crash.s4" / "metadata.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def perfect(s4, tmp_path_factory):
    """Cached perfect-policy battery per worker: (report, out_dir, chat)."""
    cache: dict[str, tuple[dict, Path, _FakeChat]] = {}

    def _run(name: str):
        if name not in cache:
            worker, _meta, metadata_path, plan = s4(name)
            out_dir = tmp_path_factory.mktemp("s5") / name
            chat = _FakeChat(plan)
            report = run_battery(
                worker,
                _CFG,
                chat=chat,
                metadata_path=metadata_path,
                out_dir=out_dir,
            )
            cache[name] = (report, out_dir, chat)
        return cache[name]

    return _run


# --------------------------------------------------------------------------- #
# group 0 — the s5_crash fixture, proven against the engine
# --------------------------------------------------------------------------- #


def test_crash_fixture_is_worker_shaped():
    assert (CRASH / "game.py").is_file()
    assert (CRASH / "solver.py").is_file()
    game_cls, solver_cls = load_worker_classes(CRASH)
    assert solver_cls is not None
    game = _fresh_game(game_cls)
    assert game.game_id == CRASH_GAME_ID
    # `_levels` is the engine's own list; gen/s3_static.py counts levels the
    # same way (there is no public accessor on ARCBaseGame).
    assert len(game._levels) == len(CRASH_SOLVER) >= 2


def test_crash_fixture_raises_inside_step_at_the_authored_action():
    """Drive it raw: RESET ok, actions 1..CRASH_AFTER-1 ok, then RuntimeError."""
    game_cls, _ = load_worker_classes(CRASH)
    game = _fresh_game(game_cls)
    fd = _reset(game)
    assert fd.levels_completed == 0
    assert len(settled_grid(fd)) == 64

    right = ActionInput(id=GameAction.ACTION4)
    completed_after = []
    for step in range(1, CRASH_AFTER):
        fd = _perform(game, right)  # must NOT raise
        completed_after.append(int(fd.levels_completed))
    assert completed_after == [0, 1, 1], completed_after  # level 1 done at action 2

    with pytest.raises(RuntimeError) as excinfo:
        _perform(game, right)
    assert CRASH_MARKER in str(excinfo.value)


def test_crash_fixture_charges_nothing_on_reset():
    """A counting game must not charge on RESET (fixtures/s4_workers lesson)."""
    game_cls, _ = load_worker_classes(CRASH)
    game = _fresh_game(game_cls)
    _reset(game)
    _reset(game)
    _reset(game)
    right = ActionInput(id=GameAction.ACTION4)
    for _ in range(CRASH_AFTER - 1):
        _perform(game, right)  # still fine: the three RESETs cost nothing
    with pytest.raises(RuntimeError):
        _perform(game, right)


# --------------------------------------------------------------------------- #
# frozen surface
# --------------------------------------------------------------------------- #


def test_module_constants_are_the_frozen_values():
    assert SCHEMA_VERSION == "b9.1"
    assert (STATUS_COMPLETE, STATUS_TOKEN_CAP, STATUS_PROTOCOL, STATUS_CRASH) == (
        "complete",
        "token-cap",
        "protocol-failure",
        "crash",
    )
    assert END_REASONS == (
        "level-complete",
        "win",
        "budget-exhausted",
        "game-over",
        "protocol-failure",
        "token-cap",
        "crash",
    )
    assert CSV_COLUMNS == (
        "game",
        "level",
        "baseline_actions",
        "budget_5x",
        "n_passes",
        "n_completed",
        "best_actions",
        "actions_ratio",
        "tokens",
        "usd",
    )
    assert BATTERY_MARGIN == 5  # D8, imported from its one home (s4_baselines)


def test_frozen_callables_exist():
    for fn in (parse_reply, load_battery_metadata, run_battery, write_levels_csv, main):
        assert callable(fn), fn


# --------------------------------------------------------------------------- #
# group 1 — the OpenRouter driver (no network; the key never leaks)
# --------------------------------------------------------------------------- #


def _response_payload(text: str = "ACTION4", **extra) -> dict:
    payload = {
        "id": "gen-fake-0001",
        "model": "duck/fake-model-0.1",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
    }
    payload.update(extra)
    return payload


def test_driver_names_are_the_frozen_values():
    assert OPENROUTER_KEY_ENV == "OPENROUTER_API_KEY"
    assert OPENROUTER_URL == "https://openrouter.ai/api/v1/chat/completions"
    assert OpenRouterDriver.name == "openrouter"


def test_driver_is_registered_in_the_drivers_registry():
    assert backends.DRIVERS["openrouter"] is OpenRouterDriver
    assert {"localclaude", "codex"} <= set(backends.DRIVERS)  # registered ALONGSIDE


def test_chat_result_is_the_frozen_dataclass():
    assert dataclasses.is_dataclass(ChatResult)
    assert ChatResult.__dataclass_params__.frozen is True
    assert [f.name for f in dataclasses.fields(ChatResult)] == [
        "driver",
        "model_requested",
        "model_reported",
        "text",
        "tokens_in",
        "tokens_out",
        "usd_cost",
        "raw",
    ]


def test_missing_key_raises_driver_error_naming_the_env_var(monkeypatch, caplog):
    monkeypatch.delenv(OPENROUTER_KEY_ENV, raising=False)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(DriverError) as excinfo:
        OpenRouterDriver().chat([{"role": "user", "content": "hi"}], model="duck/fake-model")
    message = str(excinfo.value)
    assert OPENROUTER_KEY_ENV in message
    assert f"export {OPENROUTER_KEY_ENV}=<your key>" in message  # verbatim, per contract
    assert FAKE_KEY not in message
    assert FAKE_KEY not in caplog.text


def test_the_posted_request_is_the_frozen_shape(monkeypatch):
    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    captured: dict = {}

    def _urlopen(request, *args, **kwargs):
        captured["request"] = request
        return _FakeResponse(_response_payload())

    _install_urlopen(monkeypatch, _urlopen)
    messages = [{"role": "user", "content": "the board"}]
    OpenRouterDriver().chat(messages, model="duck/fake-model")

    request = captured["request"]
    assert request.full_url == OPENROUTER_URL
    assert request.get_method() == "POST"
    headers = {key.lower(): value for key, value in request.header_items()}
    auth = headers.get("authorization")
    assert auth is not None, f"no Authorization header: {sorted(headers)}"
    assert auth.startswith("Bearer ") and auth.endswith(FAKE_KEY)
    assert isinstance(request.data, bytes)
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["model"] == "duck/fake-model"
    assert payload["messages"] == messages
    assert payload["usage"] == {"include": True}  # OpenRouter usage accounting


def test_chat_maps_the_response_onto_chat_result(monkeypatch):
    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    payload = _response_payload(
        "ACTION6 12 40",
        usage={"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18, "cost": 0.0004},
    )
    _install_urlopen(monkeypatch, lambda *a, **k: _FakeResponse(payload))
    result = OpenRouterDriver().chat([{"role": "user", "content": "b"}], model="duck/fake-model")

    assert isinstance(result, ChatResult)
    assert result.driver == "openrouter"
    assert result.model_requested == "duck/fake-model"
    assert result.model_reported == payload["model"]
    assert result.text == "ACTION6 12 40"
    # Ambiguity F: the live usage field names are NOT frozen here.
    assert result.tokens_in is None or isinstance(result.tokens_in, int)
    assert result.tokens_out is None or isinstance(result.tokens_out, int)
    assert result.usd_cost is None or isinstance(result.usd_cost, (int, float))
    # Ambiguity E: `raw` is the parsed response, or a dict carrying it.
    assert isinstance(result.raw, dict)
    assert result.raw == payload or payload in list(result.raw.values())


def test_absent_usage_fields_become_none_and_are_never_invented(monkeypatch):
    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    _install_urlopen(monkeypatch, lambda *a, **k: _FakeResponse(_response_payload()))
    bare = OpenRouterDriver().chat([{"role": "user", "content": "b"}], model="m")
    assert (bare.tokens_in, bare.tokens_out, bare.usd_cost) == (None, None, None)

    partial = _response_payload(usage={"prompt_tokens": 11})
    _install_urlopen(monkeypatch, lambda *a, **k: _FakeResponse(partial))
    half = OpenRouterDriver().chat([{"role": "user", "content": "b"}], model="m")
    assert half.tokens_out is None
    assert half.usd_cost is None


def test_http_error_becomes_a_driver_error_carrying_the_status(monkeypatch, caplog, capsys):
    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    caplog.set_level(logging.DEBUG)

    def _raise(*args, **kwargs):
        raise urllib.error.HTTPError(
            OPENROUTER_URL,
            429,
            "Too Many Requests",
            email.message.Message(),
            io.BytesIO(b'{"error": {"message": "rate limited"}}'),
        )

    _install_urlopen(monkeypatch, _raise)
    with pytest.raises(DriverError) as excinfo:
        OpenRouterDriver().chat([{"role": "user", "content": "b"}], model="duck/fake-model")
    message = str(excinfo.value)
    assert "429" in message
    assert FAKE_KEY not in message
    assert FAKE_KEY not in repr(excinfo.value)
    assert FAKE_KEY not in caplog.text
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out and FAKE_KEY not in captured.err


def test_the_key_never_leaks_on_a_successful_call(monkeypatch, caplog, capsys):
    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    caplog.set_level(logging.DEBUG)
    _install_urlopen(monkeypatch, lambda *a, **k: _FakeResponse(_response_payload()))
    result = OpenRouterDriver().chat([{"role": "user", "content": "b"}], model="m")
    assert FAKE_KEY not in json.dumps(result.raw)
    assert FAKE_KEY not in repr(result)
    assert FAKE_KEY not in caplog.text
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out and FAKE_KEY not in captured.err


# --------------------------------------------------------------------------- #
# group 2 — parse_reply: the frozen reply protocol
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("action_id", [1, 2, 3, 4, 5])
def test_parse_reply_accepts_every_declared_simple_action(action_id):
    action = parse_reply(f"ACTION{action_id}", [action_id])
    assert isinstance(action, ActionInput)
    assert action.id is GameAction[f"ACTION{action_id}"]
    assert not action.data


@pytest.mark.parametrize("x,y", [(0, 0), (12, 40), (63, 63)])
def test_parse_reply_accepts_action6_with_coordinates(x, y):
    action = parse_reply(f"ACTION6 {x} {y}", [1, 6])
    assert action.id is GameAction.ACTION6
    assert action.data == {"x": x, "y": y}  # frames.mouse's frozen key names


def test_parse_reply_takes_the_first_matching_line():
    assert parse_reply("ACTION2\nACTION4", [1, 2, 3, 4]).id is GameAction.ACTION2


def test_parse_reply_tolerates_padding_around_the_action_line():
    text = "Let me think about this.\n\nACTION3\n\nThat should move me left.\n"
    assert parse_reply(text, [1, 2, 3, 4]).id is GameAction.ACTION3


@pytest.mark.parametrize(
    "text,ids",
    [
        ("", [1, 2]),
        ("   \n\n", [1, 2]),
        ("I will move the player left.", [1, 2, 3, 4]),
        ("ACTION8", [1, 2, 3, 4]),  # not an engine action
        ("ACTION0", [1, 2, 3, 4]),  # RESET's id, spelled as an action
        ("RESET", [1, 2, 3, 4]),  # RESET is never a reply (contract §3)
        ("ACTION5", [1, 2, 3, 4]),  # legal action, NOT declared
        ("ACTION6", [1, 6]),  # click without coordinates
        ("ACTION6 5", [1, 6]),  # one coordinate
        ("ACTION6 12 40", [1, 2, 3, 4]),  # click not declared
        ("ACTION6 64 0", [1, 6]),  # x out of the 0-63 range
        ("ACTION6 0 64", [1, 6]),  # y out of the 0-63 range
        ("ACTION6 -1 0", [1, 6]),  # negative coordinate
        ("ACTION6 1.5 2", [1, 6]),  # not ints
        ("ACTION6 a b", [1, 6]),  # not numbers
    ],
)
def test_parse_reply_refuses_malformed_replies(text, ids):
    with pytest.raises(ValueError):
        parse_reply(text, ids)


# --------------------------------------------------------------------------- #
# group 3 — the perfect policy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", ["generous", "toy"])
def test_perfect_policy_completes_every_level(perfect, s4, name):
    report, _out_dir, chat = perfect(name)
    _worker, metadata, _path, plan = s4(name)
    baselines = metadata["baseline_actions"]
    solver = metadata["solver_actions"]
    levels = len(baselines)

    assert report["status"] == STATUS_COMPLETE
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["stage"] == "s5"
    assert report["game_id"] == metadata["game_id"]
    assert report["crash"] is None
    assert report["passes"] == {"requested": 3, "completed": 3}

    grouped = _rows_by_pass(report)
    assert len(grouped) == 3, sorted(grouped)
    keys = sorted(grouped)
    assert keys == list(range(keys[0], keys[0] + 3))  # consecutive (ambiguity B)
    assert len(report["rows"]) == 3 * levels

    for rows in grouped.values():
        assert [row["level"] for row in rows] == list(range(1, levels + 1))
        for index, row in enumerate(rows):
            assert row["baseline"] == baselines[index]
            assert row["budget_5x"] == BATTERY_MARGIN * baselines[index]  # D8
            assert row["actions_used"] == solver[index]
            assert row["completed"] is True
            expected = "win" if index == levels - 1 else "level-complete"
            assert row["end_reason"] == expected

    assert len(chat.calls) == 3 * len(plan)  # one chat call per performed action


@pytest.mark.parametrize("name", ["generous", "toy"])
def test_perfect_policy_aggregate_is_the_frozen_ratio(perfect, s4, name):
    report, _out_dir, _chat = perfect(name)
    _worker, metadata, _path, _plan = s4(name)
    baselines = metadata["baseline_actions"]
    solver = metadata["solver_actions"]

    aggregate = report["aggregate"]
    assert set(aggregate) == AGGREGATE_KEYS
    assert aggregate["levels_total"] == len(baselines)
    assert aggregate["best_levels_completed"] == len(baselines)
    per_level = aggregate["per_level"]
    assert [entry["level"] for entry in per_level] == list(range(1, len(baselines) + 1))
    for index, entry in enumerate(per_level):
        assert set(entry) == PER_LEVEL_KEYS
        assert entry["baseline"] == baselines[index]
        assert entry["n_passes"] == 3
        assert entry["n_completed"] == 3
        assert entry["best_actions"] == solver[index]
        # frozen FORMULA: best_actions / baseline (ambiguity I). The PRECISION
        # is not frozen and the shipped stage rounds (ambiguity M), so the
        # tolerance is 1e-4 — still far tighter than the inverse reading,
        # which g >= 1.2 keeps above 1 while every true ratio is below it.
        assert entry["actions_ratio"] == pytest.approx(
            solver[index] / baselines[index], abs=1e-4
        )
        assert entry["actions_ratio"] < 1.0
        assert entry["best_actions"] <= BATTERY_MARGIN * baselines[index]


def test_perfect_policy_tokens_and_cost_are_counted_not_estimated(perfect):
    report, _out_dir, chat = perfect("generous")
    tokens = report["tokens"]
    assert set(tokens) == TOKENS_KEYS
    assert tokens["estimated"] is False
    assert tokens["cap"] == parse_token_cap(_CFG["battery"]["token_cap"])
    assert tokens["total"] == tokens["tokens_in"] + tokens["tokens_out"]
    assert tokens["total"] == len(chat.calls) * (chat.tokens_in + chat.tokens_out)
    assert report["usd_total"] == pytest.approx(len(chat.calls) * chat.usd)


def test_the_config_block_echoes_the_signed_battery_knobs(perfect):
    report, _out_dir, _chat = perfect("generous")
    config = report["config"]
    assert set(config) == CONFIG_KEYS
    assert config["passes"] == 3
    assert config["model_config"] == _CFG["battery"]["model"]
    assert parse_token_cap(config["token_cap"]) == parse_token_cap(_CFG["battery"]["token_cap"])
    assert report["model"] == _CFG["battery"]["model"]  # no --model override


def test_model_argument_overrides_the_config_model(s4, tmp_path):
    worker, _metadata, metadata_path, plan = s4("generous")
    report = run_battery(
        worker,
        _CFG,
        chat=_FakeChat(plan),
        model="duck/override-id",
        metadata_path=metadata_path,
        out_dir=tmp_path,
    )
    assert report["model"] == "duck/override-id"
    assert report["config"]["model_config"] == _CFG["battery"]["model"]


def test_the_observation_carries_the_settled_frame_and_the_budget(perfect, s4):
    """architecture §3 S3d + contract §2: 64 hex rows, remaining actions."""
    report, _out_dir, chat = perfect("generous")
    _worker, metadata, _path, _plan = s4("generous")
    game_cls, _ = load_worker_classes(GENEROUS)
    fd = _reset(_fresh_game(game_cls))
    expected = [_hex_row(row) for row in settled_grid(fd)]
    assert len(expected) == 64

    prompt = _prompt_text(chat.calls[0]["messages"])
    missing = [row for row in expected if row not in prompt]
    assert not missing, f"{len(missing)} of 64 settled hex rows absent from the observation"
    budget = BATTERY_MARGIN * metadata["baseline_actions"][0]
    assert str(budget) in prompt, "the level's remaining action budget is not in the observation"
    assert report["status"] == STATUS_COMPLETE


def test_default_metadata_path_is_the_worker_s4_sibling(s4, tmp_path):
    worker, _metadata, metadata_path, plan = s4("generous")
    copy = tmp_path / "capped_generous"
    shutil.copytree(worker, copy, ignore=shutil.ignore_patterns("__pycache__"))
    sibling = tmp_path / "capped_generous.s4"
    sibling.mkdir()
    shutil.copyfile(metadata_path, sibling / "metadata.json")

    report = run_battery(copy, _CFG, chat=_FakeChat(plan), out_dir=tmp_path / "out")
    assert report["status"] == STATUS_COMPLETE


def test_default_out_dir_is_the_worker_s5_sibling(s4, tmp_path):
    worker, _metadata, metadata_path, plan = s4("generous")
    copy = tmp_path / "capped_generous"
    shutil.copytree(worker, copy, ignore=shutil.ignore_patterns("__pycache__"))
    run_battery(copy, _CFG, chat=_FakeChat(plan), metadata_path=metadata_path)
    sibling = tmp_path / "capped_generous.s5"
    assert (sibling / REPORT_NAME).is_file()
    assert (sibling / CSV_NAME).is_file()


def test_metadata_must_exist_and_be_fit(s4, tmp_path):
    worker, metadata, _path, plan = s4("generous")
    missing = tmp_path / "nope" / "metadata.json"
    with pytest.raises((FileNotFoundError, ValueError)):  # ambiguity J
        load_battery_metadata(missing)
    with pytest.raises((FileNotFoundError, ValueError)):
        run_battery(worker, _CFG, chat=_FakeChat(plan), metadata_path=missing, out_dir=tmp_path)

    rejected = dict(metadata)
    rejected["verdict"] = "cap-fit-reject"
    path = tmp_path / "rejected.json"
    path.write_text(json.dumps(rejected), encoding="utf-8")
    with pytest.raises(ValueError):
        load_battery_metadata(path)
    with pytest.raises(ValueError):
        run_battery(worker, _CFG, chat=_FakeChat(plan), metadata_path=path, out_dir=tmp_path)


def test_load_battery_metadata_returns_a_fit_metadata(s4):
    _worker, metadata, metadata_path, _plan = s4("generous")
    loaded = load_battery_metadata(metadata_path)
    assert isinstance(loaded, dict)
    assert loaded["verdict"] == "fit"
    assert loaded["baseline_actions"] == metadata["baseline_actions"]


def test_level_count_must_match_the_baseline_vector(s4, tmp_path):
    worker, metadata, _path, plan = s4("generous")
    short = dict(metadata)
    short["baseline_actions"] = metadata["baseline_actions"][:-1]
    path = tmp_path / "short.json"
    path.write_text(json.dumps(short), encoding="utf-8")
    with pytest.raises(ValueError):
        run_battery(worker, _CFG, chat=_FakeChat(plan), metadata_path=path, out_dir=tmp_path)


# --------------------------------------------------------------------------- #
# group 4 — the null policy (a failed level is a VALID outcome, D9)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def null_policy(s4, tmp_path_factory):
    """ACTION1 on capped_generous is a charged wall-bump that never progresses."""
    worker, metadata, metadata_path, _plan = s4("generous")
    out_dir = tmp_path_factory.mktemp("s5-null")
    chat = _FakeChat(["ACTION1"])
    report = run_battery(
        worker, _CFG, chat=chat, metadata_path=metadata_path, out_dir=out_dir
    )
    return report, metadata, chat


def test_null_policy_exhausts_exactly_the_five_times_baseline_budget(null_policy):
    report, metadata, chat = null_policy
    budget = BATTERY_MARGIN * metadata["baseline_actions"][0]  # D8

    assert report["status"] == STATUS_COMPLETE  # a failed level is not an error
    assert report["crash"] is None
    rows = report["rows"]
    assert len(rows) == 3, [row["level"] for row in rows]
    for row in rows:
        assert set(row) == ROW_KEYS
        assert row["level"] == 1  # the engine cannot skip levels
        assert row["end_reason"] == "budget-exhausted"
        assert row["actions_used"] == budget
        assert row["budget_5x"] == budget
        assert row["completed"] is False
    assert len({row["pass"] for row in rows}) == 3
    assert len(chat.calls) == 3 * budget


def test_null_policy_aggregate_reports_no_completion(null_policy):
    report, metadata, _chat = null_policy
    aggregate = report["aggregate"]
    assert aggregate["levels_total"] == len(metadata["baseline_actions"])
    assert aggregate["best_levels_completed"] == 0
    first = [e for e in aggregate["per_level"] if e["level"] == 1]
    assert len(first) == 1, aggregate["per_level"]
    entry = first[0]
    assert entry["n_passes"] == 3
    assert entry["n_completed"] == 0
    assert entry["best_actions"] is None
    assert entry["actions_ratio"] is None  # no completed pass -> None


# --------------------------------------------------------------------------- #
# group 5 — the protocol failure and its one retry
# --------------------------------------------------------------------------- #


def test_two_consecutive_malformed_replies_end_the_pass(s4, tmp_path):
    worker, _metadata, metadata_path, _plan = s4("generous")
    chat = _FakeChat(["I am not going to follow the protocol."])
    report = run_battery(
        worker, _CFG, chat=chat, metadata_path=metadata_path, out_dir=tmp_path
    )
    assert report["status"] == STATUS_PROTOCOL
    rows = report["rows"]
    assert rows, "a protocol failure must still record its row"
    assert {row["end_reason"] for row in rows} == {"protocol-failure"}
    assert all(row["completed"] is False for row in rows)
    assert all(row["actions_used"] == 0 for row in rows)
    assert report["passes"]["requested"] == 3
    assert report["passes"]["completed"] <= 3  # ambiguity N: "completed" is undefined
    # One row per failed pass, and exactly two chat calls per pass: the try
    # plus THE one retry (contract §3). Stated without leaning on `completed`.
    passes_seen = {row["pass"] for row in rows}
    assert len(rows) == len(passes_seen)
    assert len(chat.calls) == 2 * len(passes_seen)


def test_one_malformed_reply_is_retried_and_the_pass_survives(s4, tmp_path):
    worker, metadata, metadata_path, plan = s4("generous")
    chat = _FakeChat(plan, prefix=["I think I will wander off protocol here."])
    report = run_battery(
        worker, _CFG, chat=chat, metadata_path=metadata_path, out_dir=tmp_path
    )
    assert report["status"] == STATUS_COMPLETE
    assert report["aggregate"]["best_levels_completed"] == len(metadata["baseline_actions"])
    assert len(chat.calls) == 1 + 3 * len(plan)  # the retry costs one extra call


# --------------------------------------------------------------------------- #
# group 6 — the token cap (D22: the pilot never blocks on budget)
# --------------------------------------------------------------------------- #


def test_token_cap_aborts_cleanly_and_keeps_partial_rows(s4, tmp_path):
    worker, metadata, metadata_path, plan = s4("generous")
    cap = parse_token_cap(_CFG["battery"]["token_cap"])
    chat = _FakeChat(plan, tokens_in=cap // 5, tokens_out=cap // 5)
    report = run_battery(
        worker, _CFG, chat=chat, metadata_path=metadata_path, out_dir=tmp_path
    )

    assert report["status"] == STATUS_TOKEN_CAP
    assert report["crash"] is None
    tokens = report["tokens"]
    assert tokens["cap"] == cap
    assert tokens["total"] > cap
    assert tokens["estimated"] is False
    rows = report["rows"]
    assert rows, "the levels finished before the cap must survive the abort"
    assert rows[0]["level"] == 1
    assert rows[0]["end_reason"] == "level-complete"
    assert rows[0]["actions_used"] == metadata["solver_actions"][0]
    assert {row["end_reason"] for row in rows} <= set(END_REASONS)
    assert report["passes"]["completed"] <= report["passes"]["requested"]


def test_a_usage_less_lane_charges_a_conservative_estimate(s4, tmp_path):
    worker, _metadata, metadata_path, plan = s4("generous")
    roomy = _cfg_with(_CFG, token_cap="10M")
    chat = _FakeChat(plan, tokens_in=None, tokens_out=None, usd=None)
    report = run_battery(
        worker, roomy, chat=chat, metadata_path=metadata_path, out_dir=tmp_path
    )
    assert report["status"] == STATUS_COMPLETE
    tokens = report["tokens"]
    assert tokens["estimated"] is True
    assert tokens["total"] > 0  # a usage-less lane cannot spend unboundedly
    assert tokens["cap"] == 10_000_000
    assert report["usd_total"] is None  # summed where reported, else None


# --------------------------------------------------------------------------- #
# group 7 — the crash fixture (architecture §3: crashes route to S2)
# --------------------------------------------------------------------------- #


@pytest.fixture
def crash_report(crash_metadata, tmp_path):
    out_dir = tmp_path / "s5-crash-out"
    report = run_battery(
        CRASH,
        _CFG,
        chat=_FakeChat(["ACTION4"]),
        metadata_path=crash_metadata,
        out_dir=out_dir,
    )
    return report, out_dir


def test_an_engine_fault_is_recorded_as_a_crash(crash_report):
    report, _out_dir = crash_report
    assert report["status"] == STATUS_CRASH
    assert report["game_id"] == CRASH_GAME_ID
    crash = report["crash"]
    assert isinstance(crash, dict), f"crash must be a dict, got {crash!r}"
    assert {"pass", "level", "error_tail"} <= set(crash), sorted(crash)
    assert isinstance(crash["error_tail"], str)
    assert crash["error_tail"].strip()
    assert CRASH_MARKER in crash["error_tail"]
    assert crash["level"] == 2  # level 1 finishes at action 2, action 4 raises
    assert report["passes"]["completed"] <= report["passes"]["requested"]


def test_rows_up_to_the_crash_are_kept(crash_report):
    report, out_dir = crash_report
    rows = report["rows"]
    assert rows, "the level finished before the fault must survive"
    first = rows[0]
    assert first["level"] == 1
    assert first["end_reason"] == "level-complete"
    assert first["actions_used"] == CRASH_SOLVER[0]
    assert first["baseline"] == CRASH_BASELINES[0]
    assert first["budget_5x"] == BATTERY_MARGIN * CRASH_BASELINES[0]
    assert {row["end_reason"] for row in rows} <= set(END_REASONS)
    assert report["crash"]["pass"] in {row["pass"] for row in rows}
    assert (out_dir / REPORT_NAME).is_file()
    assert (out_dir / CSV_NAME).is_file()


# --------------------------------------------------------------------------- #
# group 8 — the report schema and the CSV dialect
# --------------------------------------------------------------------------- #


def test_report_top_level_keys_are_frozen(perfect):
    report, out_dir, _chat = perfect("generous")
    assert set(report) == REPORT_KEYS, sorted(set(report) ^ REPORT_KEYS)
    assert set(report["passes"]) == PASSES_KEYS
    assert isinstance(report["versions"], dict) and report["versions"]
    assert isinstance(report["paths"], dict) and report["paths"]
    assert report["worker"] == str(GENEROUS) or Path(report["worker"]) == GENEROUS
    written = {str(value) for value in report["paths"].values() if isinstance(value, str)}
    assert str(out_dir / REPORT_NAME) in written
    assert str(out_dir / CSV_NAME) in written


def test_the_report_is_valid_json_on_disk(perfect):
    report, out_dir, _chat = perfect("generous")
    on_disk = json.loads((out_dir / REPORT_NAME).read_text(encoding="utf-8"))
    assert on_disk == report


def test_csv_header_is_the_frozen_column_tuple(perfect):
    _report, out_dir, _chat = perfect("generous")
    with (out_dir / CSV_NAME).open(encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    assert header == list(CSV_COLUMNS)


def test_csv_first_three_columns_are_the_house_dialect(cfg, perfect):
    _report, out_dir, _chat = perfect("generous")
    reference = _reference_header(cfg)
    assert reference[:3] == ["game", "level", "baseline_actions"]
    with (out_dir / CSV_NAME).open(encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    assert header[:3] == reference[:3]
    assert list(CSV_COLUMNS[:3]) == reference[:3]


def test_csv_uses_newline_endings_only(perfect):
    _report, out_dir, _chat = perfect("generous")
    assert b"\r" not in (out_dir / CSV_NAME).read_bytes()


def test_csv_rows_round_trip_against_the_aggregate(perfect):
    report, out_dir, _chat = perfect("generous")
    rows = _read_csv(out_dir / CSV_NAME)
    per_level = report["aggregate"]["per_level"]
    assert len(rows) == len(per_level)
    for row, entry in zip(rows, per_level):
        assert row["game"] == report["game_id"]
        assert int(row["level"]) == entry["level"]
        assert int(row["baseline_actions"]) == entry["baseline"]
        assert int(row["budget_5x"]) == BATTERY_MARGIN * entry["baseline"]  # D8
        assert int(row["n_passes"]) == entry["n_passes"]
        assert int(row["n_completed"]) == entry["n_completed"]
        assert _opt_int(row["best_actions"]) == entry["best_actions"]
        ratio = _opt_float(row["actions_ratio"])
        if entry["actions_ratio"] is None:
            assert ratio is None
        else:
            assert ratio == pytest.approx(entry["actions_ratio"], rel=1e-6)
        assert _opt_int(row["tokens"]) is not None  # ambiguity G: totals, typed only
        _opt_float(row["usd"])


def test_write_levels_csv_reproduces_the_file_run_battery_wrote(perfect, tmp_path):
    report, out_dir, _chat = perfect("generous")
    again = tmp_path / "again.csv"
    write_levels_csv(report, again)
    assert again.read_bytes() == (out_dir / CSV_NAME).read_bytes()


def test_every_end_reason_is_in_the_frozen_vocabulary(perfect, null_policy):
    for report in (perfect("generous")[0], perfect("toy")[0], null_policy[0]):
        assert {row["end_reason"] for row in report["rows"]} <= set(END_REASONS)
        assert report["status"] in {
            STATUS_COMPLETE,
            STATUS_TOKEN_CAP,
            STATUS_PROTOCOL,
            STATUS_CRASH,
        }


# --------------------------------------------------------------------------- #
# group 9 — determinism
# --------------------------------------------------------------------------- #


def test_the_same_fake_chat_and_worker_give_byte_identical_outputs(s4, tmp_path):
    worker, _metadata, metadata_path, plan = s4("generous")
    out_dir = tmp_path / "s5"

    run_battery(worker, _CFG, chat=_FakeChat(plan), metadata_path=metadata_path, out_dir=out_dir)
    first_report = (out_dir / REPORT_NAME).read_bytes()
    first_csv = (out_dir / CSV_NAME).read_bytes()

    run_battery(worker, _CFG, chat=_FakeChat(plan), metadata_path=metadata_path, out_dir=out_dir)
    assert (out_dir / REPORT_NAME).read_bytes() == first_report
    assert (out_dir / CSV_NAME).read_bytes() == first_csv


# --------------------------------------------------------------------------- #
# group 10 — the CLI and its exit codes
# --------------------------------------------------------------------------- #


def _battery_argv(worker: Path, metadata: Path, out: Path) -> list[str]:
    return [
        "--worker",
        str(worker),
        "--metadata",
        str(metadata),
        "--out",
        str(out),
        "--config",
        PILOT_CONFIG,
    ]


def test_cli_exits_zero_on_a_clean_battery(monkeypatch, capsys, s4, tmp_path):
    worker, _metadata, metadata_path, plan = s4("generous")
    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    _install_fake_driver(monkeypatch, _FakeChat(plan))
    out = tmp_path / "out"
    assert _cli(_battery_argv(worker, metadata_path, out)) == 0
    captured = capsys.readouterr()
    assert "[s5]" in captured.out + captured.err  # house summary line
    assert FAKE_KEY not in captured.out and FAKE_KEY not in captured.err
    assert (out / REPORT_NAME).is_file()
    report = json.loads((out / REPORT_NAME).read_text(encoding="utf-8"))
    assert report["status"] == STATUS_COMPLETE


def test_cli_exits_two_on_a_token_cap_abort(monkeypatch, s4, tmp_path):
    worker, _metadata, metadata_path, plan = s4("generous")
    cap = parse_token_cap(_CFG["battery"]["token_cap"])
    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    _install_fake_driver(monkeypatch, _FakeChat(plan, tokens_in=cap // 5, tokens_out=cap // 5))
    out = tmp_path / "out"
    assert _cli(_battery_argv(worker, metadata_path, out)) == 2
    report = json.loads((out / REPORT_NAME).read_text(encoding="utf-8"))
    assert report["status"] == STATUS_TOKEN_CAP


def test_cli_exits_two_on_a_protocol_failure(monkeypatch, s4, tmp_path):
    worker, _metadata, metadata_path, _plan = s4("generous")
    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    _install_fake_driver(monkeypatch, _FakeChat(["no protocol here"]))
    out = tmp_path / "out"
    assert _cli(_battery_argv(worker, metadata_path, out)) == 2
    report = json.loads((out / REPORT_NAME).read_text(encoding="utf-8"))
    assert report["status"] == STATUS_PROTOCOL


def test_cli_exits_three_on_a_crash(monkeypatch, crash_metadata, tmp_path):
    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    _install_fake_driver(monkeypatch, _FakeChat(["ACTION4"]))
    out = tmp_path / "out"
    assert _cli(_battery_argv(CRASH, crash_metadata, out)) == 3
    report = json.loads((out / REPORT_NAME).read_text(encoding="utf-8"))
    assert report["status"] == STATUS_CRASH


def test_cli_exits_one_when_the_metadata_is_missing(monkeypatch, s4, tmp_path):
    worker, _metadata, _metadata_path, plan = s4("generous")
    copy = tmp_path / "capped_generous"
    shutil.copytree(worker, copy, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    _install_fake_driver(monkeypatch, _FakeChat(plan))
    assert _cli(
        ["--worker", str(copy), "--out", str(tmp_path / "out"), "--config", PILOT_CONFIG]
    ) == 1


def test_cli_exits_one_on_a_bad_worker(monkeypatch, s4, tmp_path):
    _worker, _metadata, metadata_path, plan = s4("generous")
    monkeypatch.setenv(OPENROUTER_KEY_ENV, FAKE_KEY)
    _install_fake_driver(monkeypatch, _FakeChat(plan))
    assert _cli(_battery_argv(tmp_path / "not-a-worker", metadata_path, tmp_path / "out")) == 1
