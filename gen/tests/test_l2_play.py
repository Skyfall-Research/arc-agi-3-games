"""L-2 — the vendored play server and its §7 layout-seed picker.

Run: .venv/bin/python -m pytest gen/tests/test_l2_play.py -q

Scope, from `docs/v2/contracts/L-2-play-server-vendored-seed-picker.md` §6:
discovery still finds the shelf · seed parsing (valid / invalid / absent) ·
manifest seed extraction including the no-manifest degrade ·
`find_play_server` prefers the vendored copy.

NO SOCKETS. Every test here is a direct function call — a play server is
routinely running on this machine and the contract forbids binding a port. The
one HTTP-shaped test drives `Handler.do_POST` on a hand-built instance with
`_send` captured, which exercises the real dispatch and the real status code
without a listener.

READ-ONLY on the repo: the tests read `games/` and `tools/play/`, and every
test that can write (a `Session` fixes its log path at load time) is pointed at
tmp first.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAY_DIR = REPO_ROOT / "tools" / "play"
SHELF = REPO_ROOT / "games"


def _load_server():
    """Import the vendored server by path — `tools/` is not an importable package.

    The module sets `ONLY_RESET_LEVELS` at import time (it must precede the
    arcengine import), and that is a process-wide environment change this file
    has no business leaking into the rest of the suite. `gen.frames._fresh_game`
    and `gen.s6_package` both pop the same variable before building a game, so
    nothing downstream depends on it either way — it is put back regardless.
    """
    prior = os.environ.get("ONLY_RESET_LEVELS")
    try:
        spec = importlib.util.spec_from_file_location("l2_play_server", PLAY_DIR / "server.py")
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


# --- 1. the vendoring itself -------------------------------------------------


def test_the_player_is_vendored_beside_its_provenance():
    """`tools/play/` is the player, and it says where it came from.

    index.html is not optional: server.py serves it out of its own directory,
    so vendoring the .py alone would ship a 500 instead of a UI.
    """
    for name in ("server.py", "index.html", "PROVENANCE.md"):
        assert (PLAY_DIR / name).is_file(), f"tools/play/{name} is missing"
    stamp = (PLAY_DIR / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "duckWM commit" in stamp
    # the sha256 of each file AS COPIED, before this contract's modifications
    assert "4ae2bf0f53184348219c1e543fc7ca5b929dd3890984ab65fad82fc374bb8e48" in stamp
    assert "1140369966e24010addd37060c5b16035d532a85fb8d6db09a758e006ee32b08" in stamp


def test_the_vendored_server_needs_no_duckwm():
    """It imports and resolves its roots with nothing but this repo on disk."""
    assert server.GAMES_DIR == SHELF
    # upstream's rule, kept: the log dir is DERIVED from the games root and is
    # deliberately not settable on its own
    assert server.LOG_DIR == REPO_ROOT / "play-logs-games"
    assert "paths" not in sys.modules or getattr(sys.modules["paths"], "__file__", "") is None
    assert "inference.tools.traces" not in sys.modules
    assert callable(server.compute_level_score)
    # the formula is RHAE's: min((baseline / steps) ** 2 * 100, 115)
    assert server.compute_level_score(
        baseline_actions=10, agent_steps=10, agent_status="COMPLETED") == 100.0
    assert server.compute_level_score(
        baseline_actions=10, agent_steps=1, agent_status="COMPLETED") == 115.0
    assert server.compute_level_score(
        baseline_actions=10, agent_steps=10, agent_status="ABANDONED") == 0.0


# --- 2. discovery still finds the shelf --------------------------------------


def test_discovery_finds_the_shelf():
    games = server.discover_games()
    assert games, "the discovery glob found nothing under games/"
    shelf_slugs = {p.parent.parent.name for p in SHELF.glob("*/*/metadata.json")}
    assert len(games) == len(shelf_slugs)
    for entry in games:
        assert entry["game_id"]
        assert entry["title"]
        assert Path(entry["py"]).is_file()
        assert entry["levels"] == len(entry["baseline_actions"])


def test_discovery_carries_the_validated_seeds():
    """The picker's options ride on the entry `/api/games` already returns."""
    games = {g["game_id"]: g for g in server.discover_games()}
    rover = next(g for gid, g in games.items() if gid.startswith("key-strip-rover"))
    assert [s["seed"] for s in rover["seeds"]] == [
        48217, 3674058157, 669296615, 3795656437, 3771961059]
    assert all(s["win"] and s["levels_completed"] == 8 for s in rover["seeds"])


# --- 3. manifest seed extraction, and the degrade ----------------------------


def test_manifest_seeds_reads_win_and_levels():
    meta = SHELF / "key-strip-rover" / "game" / "metadata.json"
    seeds = server.manifest_seeds(meta)
    manifest = json.loads((meta.parent / "package" / "manifest.json").read_text())
    assert len(seeds) == len(manifest["seeds"]["validated"])
    assert seeds[0] == {"seed": 48217, "win": True, "levels_completed": 8}


def test_manifest_seeds_degrades_when_there_is_no_manifest(tmp_path):
    """An `out/play` mirror entry has metadata and no `package/` — not an error."""
    meta = tmp_path / "slug" / "mirror" / "metadata.json"
    meta.parent.mkdir(parents=True)
    meta.write_text(json.dumps({"game_id": "x", "title": "X", "baseline_actions": [3]}))
    assert server.manifest_seeds(meta) == []


@pytest.mark.parametrize("payload", [
    "not json at all",
    "[]",                                       # a list, not a mapping
    '{"seeds": null}',
    '{"seeds": {"validated": null}}',
    '{"seeds": {"validated": [{"seed": "48217"}, {"win": true}, 7]}}',  # no usable int seed
])
def test_manifest_seeds_degrades_on_an_unusable_manifest(tmp_path, payload):
    meta = tmp_path / "slug" / "game" / "metadata.json"
    (meta.parent / "package").mkdir(parents=True)
    meta.write_text("{}")
    (meta.parent / "package" / "manifest.json").write_text(payload)
    assert server.manifest_seeds(meta) == []


# --- 4. seed parsing: valid / invalid / absent -------------------------------


@pytest.mark.parametrize("raw", [None, "", "   ", "canonical", "CANONICAL"])
def test_absent_means_the_canonical_build(raw):
    assert server.parse_seed(raw) is None


@pytest.mark.parametrize(("raw", "want"), [
    (48217, 48217),
    ("48217", 48217),
    ("  3771961059  ", 3771961059),
    (0, 0),
    ("-1", -1),
])
def test_a_valid_seed_parses_to_an_int(raw, want):
    assert server.parse_seed(raw) == want


@pytest.mark.parametrize("raw", ["abc", "4.5", "48217x", "0x10", True, False, [], {}, 1.5])
def test_an_invalid_seed_is_a_plain_sentence(raw):
    with pytest.raises(server.SeedError) as exc:
        server.parse_seed(raw)
    message = str(exc.value)
    assert "is not a layout seed" in message
    assert message.endswith(".")
    assert "Traceback" not in message and "Error" not in message


def test_an_invalid_seed_is_answered_with_a_400_and_no_traceback():
    """The real dispatch, the real status code — with no socket bound.

    `Handler._send` is captured on the instance, so nothing is written and
    nothing is listening; this is the contract's "plain-sentence 400" proved
    through `do_POST` rather than through `parse_seed` alone.
    """
    body = json.dumps({"game_id": "whatever", "layout_seed": "banana"}).encode()
    handler = server.Handler.__new__(server.Handler)
    handler.path = "/api/load"
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = io.BytesIO(body)
    sent: dict = {}
    handler._send = lambda payload, code=200, ctype="application/json": sent.update(
        payload=payload, code=code)

    handler.do_POST()

    assert sent["code"] == 400
    assert "is not a layout seed" in sent["payload"]["error"]
    assert "Traceback" not in sent["payload"]["error"]
    # the bad seed never reached the session
    assert server.SESSION.phase == server.NO_GAME


# --- 5. the §7 instantiation -------------------------------------------------


class _Seeded:
    def __init__(self, layout_seed: int | None = None) -> None:
        self.layout_seed = layout_seed


class _Unseeded:
    def __init__(self) -> None:
        pass


def test_accepts_layout_seed_reads_the_signature():
    assert server.accepts_layout_seed(_Seeded) is True
    assert server.accepts_layout_seed(_Unseeded) is False
    assert server.accepts_layout_seed(object()) is False


@pytest.fixture
def session(tmp_path, monkeypatch):
    """A Session whose log path is tmp — never the repo's play-logs."""
    monkeypatch.setattr(server, "LOG_DIR", tmp_path / "logs")
    return server.Session()


def _rover_id() -> str:
    return next(gid for gid in server.GAMES if gid.startswith("key-strip-rover"))


def test_canonical_load_passes_no_seed_at_all(session):
    """None = the authored build. §7's `Game()` with no argument, unchanged."""
    snap = session.load(_rover_id(), "discovery")
    manifest = json.loads(
        (SHELF / "key-strip-rover" / "game" / "package" / "manifest.json").read_text())
    assert session.layout_seed is None
    assert snap["layout_seed"] is None
    assert session.log()["layout_seed"] is None
    # the game built itself at its own authored seed, which is what "canonical" means
    assert session.game.layout_seed == manifest["seeds"]["authored_seed"]


def test_a_picked_seed_reaches_the_game_and_every_record(session):
    seed = 669296615
    snap = session.load(_rover_id(), "discovery", seed)
    assert session.game.layout_seed == seed
    assert snap["layout_seed"] == seed
    assert session.log()["layout_seed"] == seed


def test_a_seed_a_game_cannot_take_is_refused_before_the_session_is_discarded(
        session, monkeypatch):
    """A typo must not cost you the session you are already in."""
    session.load(_rover_id(), "discovery")
    session.start_level()
    monkeypatch.setattr(server, "accepts_layout_seed", lambda cls: False)

    with pytest.raises(server.SeedError) as exc:
        session.load(_rover_id(), "discovery", 42)

    assert "does not take a layout seed" in str(exc.value)
    assert session.phase == server.PLAYING          # the live session survived
    assert session.layout_seed is None


def test_saved_sessions_report_the_seed(tmp_path, monkeypatch):
    """A log written before the picker existed reads as canonical, which it was."""
    monkeypatch.setattr(server, "LOG_DIR", tmp_path)
    (tmp_path / "a.json").write_text(json.dumps(
        {"game_id": "g", "mode": "discovery", "layout_seed": 99, "actions": [], "levels": []}))
    (tmp_path / "b.json").write_text(json.dumps(
        {"game_id": "g", "mode": "replay", "actions": [], "levels": []}))
    by_mode = {s["mode"]: s for s in server.saved_sessions()}
    assert by_mode["discovery"]["layout_seed"] == 99
    assert by_mode["replay"]["layout_seed"] is None


# --- 6. the CLI prefers the vendored copy ------------------------------------


def test_find_play_server_prefers_the_vendored_copy():
    from gen import cli

    assert cli.VENDORED_PLAY_SERVER == PLAY_DIR / "server.py"
    assert cli.find_play_server() == cli.VENDORED_PLAY_SERVER


def test_find_play_server_falls_back_to_duckwm_then_to_none(tmp_path, monkeypatch):
    from gen import cli

    monkeypatch.setattr(cli, "VENDORED_PLAY_SERVER", tmp_path / "gone" / "server.py")
    sibling = tmp_path / "duckWM"
    monkeypatch.setattr(cli, "DUCKWM_SIBLING", sibling)
    assert cli.find_play_server() is None

    fallback = sibling / cli.PLAY_SERVER_REL
    fallback.parent.mkdir(parents=True)
    fallback.write_text("# a duckWM checkout\n")
    assert cli.find_play_server() == fallback
