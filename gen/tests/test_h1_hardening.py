"""Contract H-1 (the hardening wave) — the IMPLEMENTER's pins.

Run: .venv/bin/python -m pytest gen/tests/test_h1_hardening.py -q

One section per item of `docs/v2/contracts/H-1-hardening-wave.md`. Items 5, 6,
10 and 11 carried an investigation license, so their pins hold the MEASUREMENT
true rather than a mechanism the contract named; each section says what was
measured. The blind lane's file (`gen/tests/test_v2_hardening.py`) is a
separate, independent pin of the PROMISES and is never imported here.

HERMETIC. No driver binary is started (`backends._run` / `urlopen` are
replaced wherever a driver is driven), nothing dials out, every write lands
under `tmp_path`, and a module-scoped guard fails the file if the repo's own
`out/`, `games/`, `config/`, `canon/`, `tools/play/` or `play-logs-games/`
trees changed shape. `../duckWM` is only ever READ.
"""

from __future__ import annotations

import ast
import fcntl
import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

from gen import backends, cli, s0_ideas, s1_spec, s2_implement, s3_gate, s6_package
from gen import orchestrator as orch
from gen.config import REPO_ROOT
from gen.s2_implement import REJECT_SUFFIX, green_loop, sidecar
from gen.worker import instantiate_worker

TESTS = Path(__file__).resolve().parent
PLAY_DIR = REPO_ROOT / "tools" / "play"
GUARDED = ("out", "games", "config", "canon", "tools/play", "play-logs-games")

#: A bounded wait for a thread that SHOULD finish. Generous on purpose: it only
#: ever elapses when the code under test is broken.
JOIN_S = 20.0
#: How long a thread that must be BLOCKED is watched for. Not a sleep-and-hope:
#: for correct code the event can never fire inside the window, whatever the
#: machine's speed — the window only bounds how long a broken lock takes to show.
BLOCKED_WINDOW_S = 0.5


# --------------------------------------------------------------------------- #
# the repo guard
# --------------------------------------------------------------------------- #


def _shape(root: Path) -> dict[str, object] | None:
    if not root.exists():
        return None
    return {
        str(path.relative_to(root)): "<dir>" if path.is_dir() else path.stat().st_size
        for path in sorted(root.rglob("*"))
        if "__pycache__" not in path.parts
    }


@pytest.fixture(autouse=True, scope="module")
def _repo_trees_untouched():
    before = {name: _shape(REPO_ROOT / name) for name in GUARDED}
    yield
    for name in GUARDED:
        assert _shape(REPO_ROOT / name) == before[name], (
            f"H-1 hard rule: a test in this file changed the repo's own {name}/ tree"
        )


# =========================================================================== #
# ITEM 1 — a model-not-found / 404 reply is a CONFIG error that stops the run
# =========================================================================== #

#: VERBATIM from the record (out/corpus/g20261001-2/patrol-cover-yard/
#: worker.attempts.jsonl — all 24 rows carry it): the provider half of the
#: DriverError the codex driver raised on every attempt of that batch. The
#: `turn.failed` envelope around it below is `_codex_guard`'s own reading shape.
REAL_CODEX_404 = (
    "unexpected status 404 Not Found: The model `gpt-5.4-codex` does not exist or you "
    "do not have access to it., url: https://api.openai.com/v1/responses, cf-ray: "
    "a43bcfbde974178d-MAA, request id: req_1e07737333e04c338aaec254bfa62dec"
)

#: FABRICATED (contract H-1 item 1: "a fabricated 404-shaped reply fixture") —
#: no claude 404 exists on this box. The envelope is the CAPTURED expired-OAuth
#: payload (`fixtures/localclaude-authfail-payload.json`: exit 1, `is_error`,
#: error text in `result`, `subtype: "success"` as the trap); only `result` is
#: swapped for an Anthropic-API-shaped unknown-model error.
FABRICATED_CLAUDE_404_RESULT = (
    'API Error: 404 {"type":"error","error":{"type":"not_found_error",'
    '"message":"model: claude-nonexistent-9"}}'
)


def _claude_404_stdout() -> str:
    payload = json.loads(
        (TESTS / "fixtures" / "localclaude-authfail-payload.json").read_text(encoding="utf-8")
    )
    payload["result"] = FABRICATED_CLAUDE_404_RESULT
    return json.dumps(payload)


def _codex_404_stdout() -> str:
    events = [
        {"type": "thread.started", "thread_id": "h1-fabricated-thread"},
        {"type": "turn.started"},
        {"type": "turn.failed", "error": {"message": REAL_CODEX_404}},
    ]
    return "".join(json.dumps(event) + "\n" for event in events)


def _fake_run(stdout: str, returncode: int = 1, stderr: str = ""):
    calls: list[list[str]] = []

    def run(cmd, driver, timeout_s, cwd=None):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr), 0.01

    run.calls = calls
    return run


def test_i1_the_codex_404_on_record_raises_a_config_error_from_the_driver(tmp_path, monkeypatch):
    run = _fake_run(_codex_404_stdout())
    monkeypatch.setattr(backends, "_run", run)
    with pytest.raises(backends.DriverConfigError) as exc:
        backends.CodexDriver().session("build it", cwd=tmp_path, model="gpt-5.4-codex")
    assert len(run.calls) == 1
    assert "gpt-5.4-codex" in str(exc.value)
    assert backends.MODEL_CONFIG_HINT in str(exc.value)
    assert isinstance(exc.value, backends.DriverError), "a subclass: every old catch still holds"
    assert not backends.is_infrastructure_error(exc.value), "a config error is not an outage"


def test_i1_an_agents_own_words_never_decide_the_config_class(tmp_path, monkeypatch):
    """No `turn.failed`: the stdout is the event stream, agent text included. An
    agent that WROTE "404 Not Found" (debugging, quoting) is the work failing."""
    events = [{"type": "item.completed",
               "item": {"type": "agent_message", "text": "the fetch said 404 Not Found"}}]
    stdout = "".join(json.dumps(event) + "\n" for event in events)
    monkeypatch.setattr(backends, "_run", _fake_run(stdout, returncode=1, stderr=""))
    with pytest.raises(backends.DriverError) as exc:
        backends.CodexDriver().session("build it", cwd=tmp_path)
    assert type(exc.value) is backends.DriverError


def test_i1_the_codex_complete_path_raises_the_same_class(tmp_path, monkeypatch):
    monkeypatch.setattr(backends, "_run", _fake_run(_codex_404_stdout()))
    with pytest.raises(backends.DriverConfigError):
        backends.CodexDriver().complete("say hi", model="gpt-5.4-codex")


def test_i1_a_claude_404_shaped_reply_raises_a_config_error_from_the_driver(
        tmp_path, monkeypatch):
    run = _fake_run(_claude_404_stdout())
    monkeypatch.setattr(backends, "_run", run)
    with pytest.raises(backends.DriverConfigError) as exc:
        backends.LocalClaudeDriver().session(
            "build it", cwd=tmp_path, model="claude-nonexistent-9")
    assert len(run.calls) == 1
    assert "not_found_error" in str(exc.value)
    assert backends.MODEL_CONFIG_HINT in str(exc.value)
    with pytest.raises(backends.DriverConfigError):
        backends.LocalClaudeDriver().complete("say hi", model="claude-nonexistent-9")


def test_i1_an_openrouter_http_404_raises_a_config_error(monkeypatch):
    def urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 404, "Not Found", {},
            io.BytesIO(b'{"error":{"message":"No such model: no/such-model","code":404}}'))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(backends.OpenRouterDriver, "_api_key", lambda self: "h1-placeholder")
    with pytest.raises(backends.DriverConfigError):
        backends.OpenRouterDriver(url="http://127.0.0.1:9/h1-never-dialled").chat(
            [{"role": "user", "content": "play"}], model="no/such-model")


def test_i1_an_auth_failure_keeps_its_exact_class_and_bytes(tmp_path, monkeypatch):
    """The 401 family is still an OUTAGE (b002 contract 2), never a config error."""
    stdout = (TESTS / "fixtures" / "localclaude-authfail-payload.json").read_text(
        encoding="utf-8")
    monkeypatch.setattr(backends, "_run", _fake_run(stdout))
    with pytest.raises(backends.DriverError) as exc:
        backends.LocalClaudeDriver().session("x", cwd=tmp_path)
    assert type(exc.value) is backends.DriverError
    assert backends.is_infrastructure_error(exc.value)
    assert backends.MODEL_CONFIG_HINT not in str(exc.value)


@pytest.mark.parametrize("text", [
    "[codex] exit 1, turn.failed: make validate is red",
    "processed 404 tokens before the session ended",            # a bare number is no 404
    "[localclaude] timed out after 1800s with no output captured",
    "HTTP 429 from https://openrouter.ai: rate limited",
])
def test_i1_the_classifier_does_not_fire_on_the_work_or_on_an_outage(text):
    assert not backends.is_model_config_error(text)


@pytest.mark.parametrize("text", [
    REAL_CODEX_404,
    FABRICATED_CLAUDE_404_RESULT,
    "[openrouter] HTTP 404 from https://example.invalid: no endpoint",
    '{"error": {"code": "model_not_found"}}',
])
def test_i1_the_classifier_fires_on_every_shape_it_names(text):
    assert backends.is_model_config_error(text)
    assert backends.is_model_config_error(RuntimeError(text))
    assert not backends.is_model_config_error(None)


def _worker(tmp_path: Path) -> Path:
    worker = tmp_path / "worker"
    instantiate_worker(worker)
    return worker.resolve()


def _raising_runner(error: BaseException, calls: list):
    def runner(prompt, *, cwd, resume_id):
        calls.append(prompt)
        raise error
    return runner


@pytest.mark.parametrize("error", [
    backends.DriverConfigError(f"[codex] exit 1, turn.failed: {REAL_CODEX_404}"),
    # A plain DriverError whose TEXT says so: the driver's own type + the text,
    # `_is_infrastructure_outage`'s two-condition rule.
    backends.DriverError(f"[localclaude] exit 1, is_error=True: {FABRICATED_CLAUDE_404_RESULT}"),
], ids=["typed", "by-text"])
def test_i1_the_green_loop_stops_at_the_first_sighting_and_consumes_nothing(
        error, tmp_path, monkeypatch):
    worker = _worker(tmp_path)
    sleeps: list[float] = []
    monkeypatch.setattr(s2_implement, "_sleep", sleeps.append)
    calls: list[str] = []

    with pytest.raises(backends.DriverError) as exc:
        green_loop(worker, "implement the spec", {"implementer": {"max_green_attempts": 12}},
                   session_runner=_raising_runner(error, calls))

    assert exc.value is error, "the run fails loudly with the driver's own exception"
    assert len(calls) == 1, "no second attempt, and no infrastructure-ladder retry"
    assert sleeps == [], "no outage wait"
    attempts = sidecar(worker, s2_implement.ATTEMPTS_SUFFIX)
    assert not attempts.exists() or not attempts.read_text(encoding="utf-8").strip(), (
        "no AttemptRecord: nothing about the game was judged"
    )
    assert not sidecar(worker, REJECT_SUFFIX).exists(), "no reject verdict either"


def test_i1_an_injected_runners_own_exception_still_consumes_an_attempt(tmp_path, monkeypatch):
    """The fail-fast keys on the DRIVER'S type: a fake's 404-worded RuntimeError
    is indistinguishable from a game failure and keeps today's handling."""
    worker = _worker(tmp_path)
    monkeypatch.setattr(s2_implement, "_sleep", lambda seconds: None)
    calls: list[str] = []
    report = green_loop(worker, "implement the spec", {"implementer": {"max_green_attempts": 1}},
                        session_runner=_raising_runner(RuntimeError(REAL_CODEX_404), calls))
    assert report.attempts == 1 and report.reject_reason == s2_implement.ATTEMPT_CAP_REASON


# =========================================================================== #
# ITEM 2 — a declaration-only re-spec hop narrates as revalidation
# =========================================================================== #

REBUILD_WORDS = ("rebuild", "built", "building")


def _ledger_line(frm, to, reason, slug="h1-narr-s001"):
    return {"slug": slug, "from": frm, "to": to, "reason": reason,
            "hashes": {"spec": None, "game": None, "stage_input": "x"}, "cost": None,
            "ts": "2026-10-06T00:00:00+00:00"}


def test_i2_the_decl_only_line_narrates_as_revalidation_with_no_build_vocabulary():
    text = cli.narrate(_ledger_line("spec_ok", "implemented", orch.DECL_ONLY_REASON), seen={})
    assert text == cli.DECL_ONLY_NARRATION
    low = text.lower()
    assert "amended spec" in low and "nothing was rewritten" in low
    assert not [word for word in REBUILD_WORDS if word in low], text


def test_i2_an_ordinary_build_still_narrates_as_a_build_and_the_revalidation_is_not_counted():
    seen: dict = {}
    first = cli.narrate(_ledger_line("spec_ok", "implemented", "green after 1 attempt(s)"),
                        seen=seen)
    cli.narrate(_ledger_line("spec_ok", "implemented", orch.DECL_ONLY_REASON), seen=seen)
    second = cli.narrate(_ledger_line("spec_ok", "implemented", "green after 2 attempt(s)"),
                         seen=seen)
    assert first.endswith("(build 1)") and second.endswith("(build 2)"), (first, second)


def test_i2_the_live_narrator_prints_it_for_the_ledger_line(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    lines = [
        _ledger_line("implemented", "spec_ok", "verifier reject 1/2 -> respec (architecture §4)"),
        _ledger_line("spec_ok", "implemented", orch.DECL_ONLY_REASON),
    ]
    ledger.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    out = io.StringIO()
    narrator = cli.LedgerNarrator(ledger, batch_id="h1-narr", size=1, out=out)
    narrator._drain()   # from offset 0: both lines, as a live tail would print them
    printed = out.getvalue().splitlines()
    index = next(i for i, row in enumerate(printed) if cli.DECL_ONLY_NARRATION in row)
    assert cli.next_stage_line("implemented") in printed[index + 1]


# =========================================================================== #
# ITEM 3 — the vendored play server re-scans its catalog per /api/games
# =========================================================================== #


def _load_server():
    """The vendored server, imported by path (the test_l2_play idiom, ONLY_RESET_LEVELS
    restored), under a module name of this file's own."""
    prior = os.environ.get("ONLY_RESET_LEVELS")
    try:
        spec = importlib.util.spec_from_file_location("h1_play_server", PLAY_DIR / "server.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if prior is None:
            os.environ.pop("ONLY_RESET_LEVELS", None)
        else:
            os.environ["ONLY_RESET_LEVELS"] = prior


server = _load_server()


def _plant_game(root: Path, slug: str, game_id: str) -> None:
    entry = root / slug / "game"
    entry.mkdir(parents=True)
    (entry / "metadata.json").write_text(json.dumps(
        {"game_id": game_id, "title": slug, "baseline_actions": [3, 4], "default_fps": 30}))
    (entry / f"{slug}.py").write_text("# never executed by this test\n")


def _api_games() -> list[dict]:
    handler = server.Handler.__new__(server.Handler)
    handler.path = "/api/games"
    sent: dict = {}
    handler._send = lambda payload, code=200, ctype="application/json": sent.update(
        payload=payload, code=code)
    handler.do_GET()
    assert sent["code"] == 200
    return sent["payload"]


def test_i3_a_game_added_to_a_served_catalog_appears_without_a_restart(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    monkeypatch.setattr(server, "GAMES_DIR", catalog)
    monkeypatch.setattr(server, "LOG_DIR", tmp_path / "logs")
    live = server.GAMES
    _plant_game(catalog, "first-game", "first-game-0001")
    assert [g["game_id"] for g in _api_games()] == ["first-game-0001"]

    _plant_game(catalog, "second-game", "second-game-0002")     # while "serving"
    ids = sorted(g["game_id"] for g in _api_games())
    assert ids == ["first-game-0001", "second-game-0002"]
    assert server.GAMES is live, "rebuilt IN PLACE: Session.load's GAMES[...] sees it too"
    assert "second-game-0002" in server.GAMES
    assert all("py" not in g for g in _api_games()), "the listing still strips the loader path"


def test_i3_a_removed_game_leaves_the_listing(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog"
    monkeypatch.setattr(server, "GAMES_DIR", catalog)
    _plant_game(catalog, "gone-game", "gone-game-0001")
    assert [g["game_id"] for g in _api_games()] == ["gone-game-0001"]
    for path in sorted((catalog / "gone-game").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    assert _api_games() == []


# =========================================================================== #
# ITEM 4 — the packaged-game hint is `arc-games play`
# =========================================================================== #


def test_i4_the_hint_is_the_command_this_repo_ships(tmp_path):
    root = tmp_path / "play"
    play = s6_package.play_command({}, root)    # no duckwm_docs needed any more
    assert play["command"] == f"{cli.PROG} play --root {root}"
    assert "PLAY_GAMES_DIR" not in play["command"]
    assert "duckWM" not in play["command"]
    assert play["server"] == str(cli.VENDORED_PLAY_SERVER) and play["server_exists"]
    assert play["python"] == sys.executable and play["python_exists"]


def test_i4_the_hint_and_the_command_resolve_the_same_player(tmp_path, monkeypatch):
    """ONE resolution (`cli.play_player`), two readers: with the vendored copy gone,
    the hint names the duckWM fallback AND its venv, exactly as `cmd_play` would run."""
    sibling = tmp_path / "duckWM"
    fallback = sibling / cli.PLAY_SERVER_REL
    fallback.parent.mkdir(parents=True)
    fallback.write_text("# stand-in\n")
    venv_python = sibling / cli.PLAY_PYTHON_REL
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("")
    monkeypatch.setattr(cli, "VENDORED_PLAY_SERVER", tmp_path / "gone" / "server.py")
    monkeypatch.setattr(cli, "DUCKWM_SIBLING", sibling)

    play = s6_package.play_command({}, tmp_path / "play")
    assert play["server"] == str(fallback) and play["python"] == str(venv_python)

    games = tmp_path / "games"
    games.mkdir()
    launched: list = []
    monkeypatch.setattr(cli.subprocess, "call",
                        lambda argv, env=None, cwd=None: launched.append(argv) or 0)
    assert cli.cmd_play(types.SimpleNamespace(root=str(games))) == 0
    assert launched == [[play["python"], play["server"]]]


# =========================================================================== #
# ITEM 5 — THE 19TH SKIP (measured: a defect, fixed)
# =========================================================================== #
#
# MEASURED 2026-10-06: `gen/tests/test_w2_sysclick.py::
# test_pin4_real_official_cd82_still_passes` skipped with "the read-only officials
# corpus is not beside this repo (…/duckWM/games)" — while duckWM WAS beside it.
# The officials moved to `duckWM/games/official/` on 2026-09-29 and every config
# was repointed (`duckwm_games: ../duckWM/games/official`); that test's
# `DUCKWM_GAMES` constant was not, so its cd82 glob matched nothing and the
# D8-calibration control silently stopped running. Fixed at the constant (a
# PIN UPDATE in that file); on this machine the test now runs and passes.


def _sysclick_module():
    spec = importlib.util.spec_from_file_location(
        "h1_w2_sysclick_probe", TESTS / "test_w2_sysclick.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_i5_the_officials_path_matches_every_config_that_names_one():
    declared = set()
    for path in sorted((REPO_ROOT / "config").glob("*.yaml")):
        value = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("duckwm_games")
        if value:
            declared.add((REPO_ROOT / value).resolve())
    assert len(declared) == 1, f"the configs disagree about the officials root: {declared}"
    assert _sysclick_module().DUCKWM_GAMES.resolve() == declared.pop()


def test_i5_where_the_officials_are_on_disk_the_cd82_control_finds_its_game():
    root = _sysclick_module().DUCKWM_GAMES
    if not (REPO_ROOT.parent / "duckWM").is_dir():
        pytest.skip("no duckWM checkout beside this repo — the env guard is honest here")
    assert sorted(root.glob("cd82/*/cd82.py")), (
        f"duckWM is beside the repo but {root} holds no cd82 — the officials path drifted "
        "again, and test_pin4_real_official_cd82_still_passes is silently skipping"
    )


# =========================================================================== #
# ITEM 6 — the test_v2_parallel rig writes the way production writes
# =========================================================================== #
#
# MEASURED 2026-10-06: the flake reproduced IN ISOLATION (2/5, then once in 27)
# as `test_b4b_the_armed_report_adds_the_parallel_key_and_nothing_else` with
# `[b11] …-s002 exited None (JSONDecodeError: Expecting value: line 1 column 1
# (char 0))`. Mechanism: `orchestrator._discover_spec_dir` (run by every
# `_context()`) json-loads every sibling corpus dir's `idea.json`; the rig's fake
# S1 wrote it with `Path.write_text` (truncate-then-write) while the in-process
# children are threads sharing one corpus dir. Production writes that file
# atomically. A two-thread drive of exactly that pair: 5262/12059 torn reads with
# `write_text`, 0/12750 with write-then-rename. This pin keeps the rig honest.


def _parallel_tree() -> ast.Module:
    return ast.parse((TESTS / "test_v2_parallel.py").read_text(encoding="utf-8"))


def test_i6_the_fake_runners_never_write_with_a_bare_write_text():
    tree = _parallel_tree()
    fakes = next(node for node in tree.body
                 if isinstance(node, ast.ClassDef) and node.name == "_Fakes")
    bare = [node.lineno for node in ast.walk(fakes)
            if isinstance(node, ast.Attribute) and node.attr == "write_text"]
    assert bare == [], f"test_v2_parallel._Fakes writes non-atomically at line(s) {bare}"


def test_i6_the_rig_writer_is_write_then_rename():
    tree = _parallel_tree()
    writer = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_rig_write")
    calls = {ast.unparse(node.func) for node in ast.walk(writer) if isinstance(node, ast.Call)}
    assert "os.replace" in calls, calls


# =========================================================================== #
# ITEMS 7 + 8 — the maintainer drawer and the shared dedupe append take a flock
# =========================================================================== #


def _held(path: Path) -> bool:
    """Is an exclusive flock held on `path` right now (by any OTHER open file)?"""
    with path.open("a", encoding="utf-8") as probe:
        try:
            fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
        return False


@pytest.fixture
def drawer_home(tmp_path, monkeypatch):
    ideas = tmp_path / "out" / "ideas"
    monkeypatch.setattr(orch, "IDEAS_ROOT", ideas)
    monkeypatch.setattr(s0_ideas, "IDEAS_ROOT", ideas)
    monkeypatch.setattr(s0_ideas, "DEDUPE_HISTORY_PATH", ideas / "dedupe-history.jsonl")
    monkeypatch.setattr(s0_ideas, "load_config",
                        lambda path: {"batch": {"id": "h1-cli", "seed": 3, "size": 1}})
    return ideas


def test_i7_the_drawer_holds_the_pipeline_draw_lock_across_the_whole_call(
        drawer_home, monkeypatch):
    lock = orch.s0_draw_lock_path("h1-cli")
    seen: dict = {}

    def sample(cfg, *, batch_id, seed=None, **kwargs):
        seen["batch_id"] = batch_id
        seen["held"] = _held(lock)
        return []

    monkeypatch.setattr(s0_ideas, "sample_batch", sample)
    assert s0_ideas.main(["--config", "unused.yaml"]) == 0
    assert seen == {"batch_id": "h1-cli", "held": True}, (
        "the hand-run drawer must hold the SAME `.sample-batch.lock` the pipeline takes, "
        "across the whole sample_batch call"
    )
    assert lock == drawer_home / "h1-cli" / orch.S0_DRAW_LOCK_NAME
    assert not _held(lock), "released when the draw returns"


def test_i7_the_drawer_waits_for_a_pipeline_drawer_that_holds_the_lock(
        drawer_home, monkeypatch):
    lock = orch.s0_draw_lock_path("h1-cli")
    lock.parent.mkdir(parents=True, exist_ok=True)
    entered = threading.Event()
    monkeypatch.setattr(s0_ideas, "sample_batch",
                        lambda cfg, **kwargs: entered.set() or [])
    with lock.open("a", encoding="utf-8") as pipeline:
        fcntl.flock(pipeline.fileno(), fcntl.LOCK_EX)
        thread = threading.Thread(target=s0_ideas.main, args=(["--config", "x.yaml"],),
                                  daemon=True)
        thread.start()
        assert not entered.wait(BLOCKED_WINDOW_S), "the drawer drew while the lock was held"
    thread.join(JOIN_S)
    assert entered.is_set() and not thread.is_alive()


def _ideas(*keys: str) -> list:
    return [types.SimpleNamespace(dedupe_key=key) for key in keys]


def test_i8_the_shared_history_append_takes_an_exclusive_flock_before_it_writes(
        drawer_home, monkeypatch):
    history = s0_ideas.DEDUPE_HISTORY_PATH
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(json.dumps({"batch_id": "older", "key": "k0", "ts": "t"}) + "\n")
    size_before = history.stat().st_size
    real = fcntl.flock
    events: list[tuple] = []

    def spy(fd, operation):
        events.append((os.fstat(fd).st_ino, operation, history.stat().st_size))
        return real(fd, operation)

    monkeypatch.setattr(fcntl, "flock", spy)
    s0_ideas._append_history("h1-batch", _ideas("k1", "k2"))
    monkeypatch.setattr(fcntl, "flock", real)

    assert (history.stat().st_ino, fcntl.LOCK_EX, size_before) in events, (
        f"no LOCK_EX on the history file before its write: {events}"
    )
    rows = [json.loads(raw) for raw in history.read_text().splitlines()]
    assert [(row["batch_id"], row["key"]) for row in rows] == [
        ("older", "k0"), ("h1-batch", "k1"), ("h1-batch", "k2")]


def test_i8_a_second_batch_appending_waits_for_the_first(drawer_home):
    history = s0_ideas.DEDUPE_HISTORY_PATH
    history.parent.mkdir(parents=True, exist_ok=True)
    done = threading.Event()

    def append() -> None:
        s0_ideas._append_history("batch-b", _ideas("kb"))
        done.set()

    with history.open("a", encoding="utf-8") as batch_a:
        fcntl.flock(batch_a.fileno(), fcntl.LOCK_EX)
        thread = threading.Thread(target=append, daemon=True)
        thread.start()
        assert not done.wait(BLOCKED_WINDOW_S), "batch B appended inside batch A's lock"
        batch_a.write(json.dumps({"batch_id": "batch-a", "key": "ka", "ts": "t"}) + "\n")
    thread.join(JOIN_S)
    assert done.is_set()
    keys = [json.loads(raw)["key"] for raw in history.read_text().splitlines()]
    assert keys == ["ka", "kb"], "whole rows, in lock order"


# =========================================================================== #
# ITEM 9 — no `gate.gate.` code is produced; the reader stays tolerant
# =========================================================================== #


@pytest.mark.parametrize("check_id,code", [
    ("role-footprint", "gate.role-footprint"),          # the visual card's bare ids
    ("l1-color-floor", "gate.l1-color-floor"),
    (s3_gate.TERM_WITNESS_CHECK, "gate.term-witness"),  # B3's ids carry the prefix
    (s3_gate.REFUSAL_PERSISTENCE_CHECK, "gate.refusal-persistence"),
])
def test_i9_a_gate_code_is_prefixed_exactly_once(check_id, code):
    assert orch._gate_code(check_id) == code


def _gate_ctx(tmp_path: Path, cfg: dict) -> orch.SlotContext:
    spec_dir = tmp_path / "corpus" / "h1-gate" / "the-game"
    (spec_dir / "worker").mkdir(parents=True)
    report = spec_dir / f"worker{orch.VERIFIER_REPORT_SUFFIX}"
    report.write_text(json.dumps({
        "verdict": "pass",
        # a CORROBORATED ungrounded term: the real `term_witness` goes red on it
        "diff": {"unimplemented_terms": ["state.wait"]},
        "term_window": 2,
    }))
    return orch.SlotContext(
        cfg=cfg, batch_id="h1-gate", slug="h1-gate-s001", index=1, state="verified",
        stage="s3_gate", attempt=1, batch_dir=tmp_path / "batches", ideas_dir=tmp_path,
        idea_path=tmp_path / "idea-001.json", corpus_dir=spec_dir.parent, spec_dir=spec_dir,
        respec_count=0, verifier_rejects=0, green_failures=0)


def test_i9_the_gate_runner_files_a_failing_term_witness_under_one_prefix(
        tmp_path, monkeypatch):
    """The REAL producer chain from the check down: `s3_gate.term_witness` (fail mode)
    -> the real `gate_checks` -> the orchestrator's gate runner's fail loop. Only the
    engine-driving legs ahead of it are stood in."""
    import gen.frames
    import gen.s3_visual

    monkeypatch.setattr(orch, "frames_provenance",
                        lambda worker: {"status": "provenance:match",
                                        "record": "provenance:match", "note": ""})
    monkeypatch.setattr(orch, "_gate_verifier_report", lambda ctx, report: report)
    monkeypatch.setattr(gen.frames, "trace_enabled", lambda cfg: False)
    monkeypatch.setattr(gen.frames, "capture_worker_isolated", lambda worker, trace=False: None)
    monkeypatch.setattr(s3_gate, "merged_gate", lambda *a, **k: {"verdict": "gated"})
    monkeypatch.setattr(gen.s3_visual, "visual_card_mode", lambda cfg: "off")

    cfg = {"verifier": {"term_witness": "fail", "refusal_persistence": "off"}}
    result = orch.default_runners()["s3_gate"](_gate_ctx(tmp_path, cfg))

    assert result["ok"] is False and result["to_state"] == "verified"
    assert [row["code"] for row in result["findings"]] == ["gate.term-witness"]
    assert result["reason"] == "gate term-witness"
    assert "gate.gate" not in json.dumps(result, default=str)
    assert "gate gate" not in result["reason"]


@pytest.mark.parametrize("check", ["term-witness", "refusal-persistence"])
def test_i9_the_historic_doubled_code_still_reads_exactly_as_it_did(check):
    """Shipped reports are immutable: the futility reader answers the doubled form
    the way it answers the fixed one (both spec-answerable)."""
    assert orch._spec_answerable(f"gate.gate.{check}") is True
    assert orch._spec_answerable(f"gate.{check}") is True


# =========================================================================== #
# ITEM 10 — `_restage` never re-runs a stage on a TERMINAL slot
# =========================================================================== #
#
# MEASURED 2026-10-06 (before the guard): a `packaged` slot whose spec bytes
# changed re-invoked s2_implement, s3_verify and s6_package from `_restage`
# (both callers run it on every slot before `_work_slot`, terminal or not, and
# the scheduled-stage skip keys off NEXT_STAGE, which terminal states lack),
# billed 3 runs off-ledger, then `_work_slot` returned "terminal".

WALKS = {
    "packaged": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
                 ("implemented", "verified"), ("verified", "gated"), ("gated", "baselined"),
                 ("baselined", "played"), ("played", "reviewed"), ("reviewed", "packaged")],
    "pulled": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
               ("implemented", "verified"), ("verified", "gated"), ("gated", "baselined"),
               ("baselined", "played"), ("played", "reviewed"), ("reviewed", "pulled")],
    "parked": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented"),
               ("implemented", "parked")],
    "dead": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "dead")],
    # the control: NOT terminal, and its recorded S2 is before the next stage
    "implemented": [(None, "ideated"), ("ideated", "spec_ok"), ("spec_ok", "implemented")],
}


@pytest.fixture
def restage_home(tmp_path, monkeypatch):
    for module in (orch, s0_ideas, s1_spec):
        for name, value in list(vars(module).items()):
            if name.startswith("__") or not isinstance(value, Path):
                continue
            try:
                relative = value.resolve().relative_to(REPO_ROOT)
            except ValueError:
                continue
            monkeypatch.setattr(module, name, tmp_path / relative)
    return tmp_path


def _planted_slot(state: str):
    batch_id = f"h1-rest-{state}"
    cfg = {"batch": {"id": batch_id, "size": 1, "seed": 7},
           "orchestrator": {"workers": 1, "wave_size": 8, "max_attrition": 0.9}}
    batch = orch.batch_config(cfg)
    bdir = orch.batch_dir(cfg)
    bdir.mkdir(parents=True, exist_ok=True)
    ledger = bdir / orch.LEDGER_NAME
    slug = orch.slot_id(batch_id, 1)
    spec_dir = orch.CORPUS_ROOT / batch_id / "the-game"
    for rel, text in (("idea.json", json.dumps({"id": "idea-001"})), ("spec.yaml", "slug: x\n"),
                      ("spec.md", "# x\n"), ("worker/game.py", "x\n"),
                      ("worker/solver.py", "x\n"), ("worker.verifier-report.json", "{}\n")):
        path = spec_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    ideas = orch.IDEAS_ROOT / batch_id
    ideas.mkdir(parents=True, exist_ok=True)
    (ideas / "idea-001.json").write_text(json.dumps({"id": "idea-001"}), encoding="utf-8")
    for from_state, to_state in WALKS[state]:
        stage = orch.EDGE_STAGE[(from_state, to_state)]
        slot = orch._slots(cfg, batch, orch.replay_ledger(ledger))[0]
        hashes = {"spec": None, "game": None, "stage_input": "x"}
        if stage is not None:
            hashes = orch.input_hashes(
                orch._context(cfg, slot, batch_id=batch_id, stage=stage, bdir=bdir))
        orch.append_transition(ledger, slug=slug, from_state=from_state, to_state=to_state,
                               reason=f"planted {stage}", hashes=hashes, cost=None)
    slot = orch._slots(cfg, batch, orch.replay_ledger(ledger))[0]
    (spec_dir / "spec.yaml").write_text("slug: x\n# edited after the fact\n", encoding="utf-8")
    return cfg, batch_id, bdir, slot


def _recording(calls: list) -> dict:
    def make(stage):
        def runner(ctx):
            calls.append(stage)
            return {"ok": True, "to_state": orch.STAGE_SUCCESS[stage], "reason": "re-ran",
                    "cost": {"usd": 1.0, "tokens_in": 1, "tokens_out": 1}}
        return runner
    return {stage: make(stage) for stage in orch.STAGES}


@pytest.mark.parametrize("state", ["packaged", "pulled", "parked", "dead"])
def test_i10_a_terminal_slot_reports_its_stale_inputs_and_runs_nothing(restage_home, state):
    cfg, batch_id, bdir, slot = _planted_slot(state)
    assert slot.terminal and slot.state == state
    calls: list = []
    outcome = orch._restage(slot, cfg=cfg, batch_id=batch_id, bdir=bdir,
                            stages=_recording(calls))
    assert outcome is None and calls == [], f"{state}: re-ran {calls} on a terminal slot"
    assert slot.offledger_cost["runs"] == 0
    stale = [row for row in slot.stale if row["stage"] != "s0_ideas"]
    assert stale, "the changed input must still be REPORTED"
    for row in stale:
        assert row["rerun"] is False
        assert row["note"] == orch.RESTAGE_TERMINAL_NOTE.format(state=state)


def test_i10_a_non_terminal_slot_still_reruns_its_completed_stages(restage_home):
    cfg, batch_id, bdir, slot = _planted_slot("implemented")
    assert not slot.terminal
    calls: list = []
    orch._restage(slot, cfg=cfg, batch_id=batch_id, bdir=bdir, stages=_recording(calls))
    assert calls == ["s2_implement"], "§2's cascade is untouched for a slot still running"


# =========================================================================== #
# ITEM 11 — `finished_modes` is per layout
# =========================================================================== #
#
# MEASURED 2026-10-06: the only `finished_modes` surface is the play server's
# load-time mode warning (no packaging warning reads it), and it collapsed every
# layout into one answer — a finished canonical discovery run warned on a load
# of a validated seed, a different board that supersedes nothing.


def _log(root: Path, name: str, game_id: str, mode: str, seed=..., finished=True) -> None:
    body = {"game_id": game_id, "mode": mode, "levels": [],
            "actions": [{"state": "WIN" if finished else "PLAYING"}]}
    if seed is not ...:
        body["layout_seed"] = seed
    (root / name).write_text(json.dumps(body))


def test_i11_finished_modes_answers_per_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "LOG_DIR", tmp_path)
    _log(tmp_path, "a.json", "g", "discovery")                  # pre-picker = canonical
    _log(tmp_path, "b.json", "g", "replay", seed=48217)
    _log(tmp_path, "c.json", "g", "discovery", seed=7, finished=False)
    assert server.finished_modes("g") == {"discovery"}
    assert server.finished_modes("g", None) == {"discovery"}
    assert server.finished_modes("g", 48217) == {"replay"}
    assert server.finished_modes("g", 7) == set(), "an unfinished run finishes nothing"


def test_i11_the_load_warning_fires_only_for_the_same_layout(tmp_path, monkeypatch):
    """Through the REAL load path on a real shelf game (read-only), logs in tmp."""
    monkeypatch.setattr(server, "LOG_DIR", tmp_path)
    rover = next(gid for gid in server.refresh_games() if gid.startswith("key-strip-rover"))
    _log(tmp_path, "done.json", rover, "discovery")              # canonical, finished
    session = server.Session()

    session.load(rover, "discovery", 669296615)
    assert session.warning == "", "a seeded board is not superseded by a canonical log"

    session.load(rover, "discovery")
    assert "already has a finished discovery run on the canonical build" in session.warning
