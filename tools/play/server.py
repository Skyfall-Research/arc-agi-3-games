#!/usr/bin/env python
"""Instrumented local player for the games on this repo's shelf (``games/``).

Runs the real ``arcengine`` in-process (no WASM), holds the game server-side,
and logs every action so per-level counts are exact. Each level is scored with
``compute_level_score`` below — the same per-level formula agent runs are
scored with — so a human playthrough and an agent playthrough compare directly.

    arc-games play
    .venv/bin/python tools/play/server.py
    open http://127.0.0.1:8009/

The catalog is the shelf (``PLAY_GAMES_DIR`` points the player at another
collection, e.g. an ``out/play`` mirror of your own runs), re-read on every
``/api/games`` request, so a newly packaged game appears without a restart.
Each game offers a LAYOUT-SEED PICKER: the canonical build as packaged, any
seed the packager validated (labelled with the win and level count it
measured), or a seed typed in. The seed in play stays on screen for the whole
session and is recorded in the play log.

VENDORED — ``PROVENANCE.md`` beside this file records where the player was
copied from and every modification made to it since.

Every level is explicitly gated. Loading a game *stages* level 1 but counts
nothing; you press **Start level** to begin recording, and the level closes the
moment you beat it. Nothing is ever counted by accident, and a session left open
overnight cannot silently absorb your next sitting.

Three constraints are deliberate, and exist so counts stay comparable to
``baseline_actions`` and to agent runs:

* **No undo.** ACTION7 is rejected. The agents' action vocabulary omits it
  entirely, so a human who undoes is not playing the same game.
* **RESET is an action and is counted**, as the per-level scoring charges it.
* **Only actions the live frame declares are accepted**, re-read every turn.

Set the mode when you load a game:

* ``discovery`` -- blind first playthrough. Never replay a game in this mode.
* ``replay``    -- second run, rules already known.

``discovery_cost = discovery actions - replay actions`` is the variable that
separates the cost of *learning* a game from the cost of *executing* it.
"""

from __future__ import annotations

import contextlib
import glob
import inspect
import io
import json
import os
import sys
import time
import types
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# MUST precede the arcengine import: without it, handle_reset full-resets to
# level 0 whenever _action_count == 0, so a RESET taken on a fresh level snaps
# the player back to level 1. TAAF sets the same flag (taaf/game_api.py:215).
os.environ["ONLY_RESET_LEVELS"] = "true"

import numpy as np  # noqa: E402
from arcengine import ARCBaseGame, ActionInput, GameAction  # noqa: E402

HERE = Path(__file__).resolve().parent

# VENDORING (L-2). Upstream reads these two roots from its own `tools/paths.py`,
# which describes duckWM's layout (`REPO/games` = the 25 officials,
# `REPO/src/ARC3-Inference` = the scorer). This repo has neither, so they are
# derived from where this file sits in it: `tools/play/server.py` -> repo root.
# The log directory keeps upstream's rule — DERIVED from the games root, never
# settable on its own — and the `PLAY_GAMES_DIR` override below is unchanged.
REPO = HERE.parents[1]                   # arc-agi-games, the repo root
GAMES_DIR = REPO / "games"               # the shared shelf (contract P-3)
LOG_DIR = GAMES_DIR.parent / f"play-logs-{GAMES_DIR.name}"

# --- which catalog is live, and where its logs go -------------------------
#
# ``PLAY_GAMES_DIR`` points the player at another collection -- the tufa corpus
# under ``arc-agi-3-generator/out/corpus/``, say. Matches the ``PLAY_PORT``
# idiom already used below.
#
# **The log directory is DERIVED from the games root and is deliberately not
# settable on its own.** ``arc-agi-3-games/play-logs/`` is the manual-play
# calibration corpus: ``logs.py`` globs it and all four play tools read through
# that helper (variance_report, summarize_play, sync_sheets, make_game_card), so
# a log from some other collection landing there would enter every calibration
# number we have. ``suggest_mode`` below scans the same directory, so it would
# corrupt discovery-vs-replay suggestion too. Two independent settings could be
# made inconsistent; a derived path cannot be.
_games_override = os.environ.get("PLAY_GAMES_DIR")
if _games_override:
    GAMES_DIR = Path(_games_override).resolve()
    LOG_DIR = GAMES_DIR.parent / f"play-logs-{GAMES_DIR.name}"


def compute_level_score(*, baseline_actions: int, agent_steps: int | None,
                        agent_status: str) -> float:
    """RHAE's per-level score: ``min((baseline / steps) ** 2 * 100, 115)``.

    VENDORING (L-2). Upstream imports this from duckWM's
    ``inference/tools/traces.py`` after putting ``src/ARC3-Inference`` on
    sys.path. The body below is that function's, verbatim, with its two module
    constants inlined; PROVENANCE.md names the commit it was taken at. Eight
    copied lines are what let this file stand alone with no duckWM on disk, and
    they keep a human playthrough scored by the same formula as an agent run.
    """
    if (
        agent_status != "COMPLETED"           # traces.COMPLETED_LEVEL_STATUS
        or agent_steps is None
        or agent_steps <= 0
        or baseline_actions <= 0
    ):
        return 0.0
    return min(float((baseline_actions / agent_steps) ** 2) * 100.0, 115.0)  # PER_LEVEL_SCORE_CAP


# GameAction(int) raises in arcengine 0.1.0 despite GameAction.ACTION3.value == 3.
ACT = {i: getattr(GameAction, f"ACTION{i}") for i in range(1, 8)}
COMPLETED = "COMPLETED"
ABANDONED = "ABANDONED"
PORT = int(os.environ.get("PLAY_PORT", "8009"))

# Phases. Actions are only accepted in PLAYING.
NO_GAME, READY, PLAYING, LEVEL_DONE, FINISHED = (
    "no_game", "ready", "playing", "level_done", "finished"
)


# --- the §7 layout seed (contract L-2) ---------------------------------------
#
# The frozen convention is ``Game(layout_seed: int | None = None)`` where None
# IS the authored canonical build and the instance records it
# (gen/s6_package.load_layout_contract). So the player's default is NO ARGUMENT
# AT ALL — upstream's instantiation, unchanged — and a seed reaches the game
# only when the operator picked one. A seed they typed is their mistake to fix,
# which is why it is answered with a sentence and a 400 rather than a traceback.
_SEED_HELP = "type a whole number, or leave the picker on the canonical build"


class SeedError(ValueError):
    """A layout seed that cannot be played. The handler answers it with a 400."""


def _not_a_seed(raw) -> SeedError:
    return SeedError(f"{raw!r} is not a layout seed — {_SEED_HELP}.")


def parse_seed(raw) -> int | None:
    """``None`` for the canonical build, otherwise the integer seed.

    Absent, null and empty all mean canonical: the UI's free-entry field hands
    over whatever is in it, and an empty field is the default rather than a
    fault. Everything else that is not an integer raises ``SeedError``.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):            # bool is an int in Python; a flag is not a seed
        raise _not_a_seed(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text.lower() == "canonical":
            return None
        try:
            return int(text)
        except ValueError:
            raise _not_a_seed(raw) from None
    raise _not_a_seed(raw)


def accepts_layout_seed(game_cls) -> bool:
    """Whether this game implements §7 and can therefore be handed a seed.

    Games built before the layout contract take no argument at all, and calling
    them with one raises a TypeError from inside somebody else's code. Asking
    the signature first turns that into a sentence the operator can act on.
    """
    try:
        return "layout_seed" in inspect.signature(game_cls).parameters
    except (TypeError, ValueError):
        return False


def manifest_seeds(meta_path) -> list[dict]:
    """The seeds S6 validated for a game, or ``[]`` when there is no manifest.

    A shelf entry is ``games/<slug>/game/`` and its ``package/manifest.json``
    sits beside the metadata the discovery glob finds (contract P-3), listing
    every seed S6 actually drove with the win and level count it measured. An
    ``out/play`` mirror entry has the metadata and no ``package/`` at all — a
    plain "canonical only", not an error — so every failure here degrades to
    ``[]`` and the picker falls back to canonical plus a typed seed.
    """
    path = Path(meta_path).parent / "package" / "manifest.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    validated = (data.get("seeds") or {}).get("validated") or []
    out = []
    for entry in validated:
        if not isinstance(entry, dict) or not isinstance(entry.get("seed"), int):
            continue
        out.append({
            "seed": entry["seed"],
            "win": bool(entry.get("win")),
            "levels_completed": entry.get("levels_completed"),
        })
    return out


@contextlib.contextmanager
def quiet():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


def discover_games() -> list[dict]:
    out = []
    for meta_path in sorted(glob.glob(str(GAMES_DIR / "*" / "*" / "metadata.json"))):
        meta = json.load(open(meta_path))
        py = sorted(glob.glob(os.path.join(os.path.dirname(meta_path), "*.py")))
        if not py:
            continue
        out.append({
            "game_id": meta.get("game_id", ""),
            "title": meta.get("title", ""),
            "levels": len(meta.get("baseline_actions") or []),
            "default_fps": meta.get("default_fps"),
            "baseline_actions": meta.get("baseline_actions") or [],
            # L-2: what the seed picker offers for this game, [] where there is
            # no manifest beside the metadata.
            "seeds": manifest_seeds(meta_path),
            "py": py[0],
        })
    return out


#: The live catalog, `{game_id: entry}`. Rebuilt IN PLACE by `refresh_games`.
GAMES: dict[str, dict] = {}


def refresh_games() -> dict[str, dict]:
    """Re-scan the catalog dir and rebuild `GAMES` in place.

    VENDORED MODIFICATION (contract H-1 item 3). Upstream snapshots the catalog
    ONCE at import, so every freshly packaged game needed a server restart to
    become playable — which bit three times in one week while batches were
    landing games beside a running player.

    REBUILT IN PLACE, not rebound, because `Session.load` reads `GAMES[game_id]`
    and the per-game play flow is deliberately untouched: the same dict object
    the module exposes gains the new entries, so a game the refreshed
    `/api/games` listed can be loaded by the id it was listed under.

    THE COST, measured on this repo's own shelf (11 entries, 2026-10-06): one
    `glob` of `<root>/*/*/metadata.json` plus two small reads per entry (the
    metadata and the seed manifest) — 1.8 ms for the whole catalog, against a
    request the browser makes on page load and on a manual refresh. That is
    cheaper than the mtime check it replaces would be to get right: a top-level
    mtime moves when an entry dir is ADDED but not when an entry's own metadata
    is rewritten in place, which is exactly what a re-packaged game does.
    """
    fresh = {g["game_id"]: g for g in discover_games()}
    GAMES.clear()
    GAMES.update(fresh)
    return GAMES


refresh_games()


# Animation frames are worth showing, not just skipping to the end: in some
# games the whole signal of "that action was rejected" lives in the intermediate
# frames (see current-architecture/11-games-catalog.md). sb26 returns 42 per
# action and sc25 22, so cap what goes over the wire — always keeping the last.
MAX_FRAMES = 24


def frames_of(frame_data) -> list:
    """Every frame of an action, settled frame last, capped at MAX_FRAMES."""
    arr = np.array(frame_data.frame)
    if arr.ndim <= 2:
        return [arr.astype(int).tolist()]
    while arr.ndim > 3:
        arr = arr[-1]
    if len(arr) > MAX_FRAMES:
        step = len(arr) / (MAX_FRAMES - 1)
        keep = sorted({int(i * step) for i in range(MAX_FRAMES - 1)} | {len(arr) - 1})
        arr = arr[keep]
    return [f.astype(int).tolist() for f in arr]


def frame_of(frame_data) -> np.ndarray:
    """The **settled** board after an action, not the first animation frame.

    An action can return several frames: a bp35 click returns five, with the
    green count running 135 -> 127 -> 126 -> 126 -> 126. Taking ``arr[0]`` shows
    the board mid-animation, so the click looks like it did nothing and the
    player clicks again -- which is exactly how "green blocks take two clicks"
    was reported. ``arr[0]`` reads just as naturally as ``arr[-1]``, which is why
    this is spelled out.

    Reset frames are single-frame in all 25 official games, so perception
    measurements taken on them were never affected.
    """
    arr = np.array(frame_data.frame)
    while arr.ndim > 2:
        arr = arr[-1]
    return arr


class Session:
    """One playthrough. Single-user tool, so one global session is enough."""

    def __init__(self) -> None:
        self.reset_state()

    def reset_state(self) -> None:
        self.game = None
        self.meta = None
        self.mode = "discovery"
        self.layout_seed = None         # L-2: None = the canonical build
        self.frame_data = None
        self.phase = NO_GAME
        self.current_level = 0          # 0-indexed; tracks game.level_index
        self.level_actions = 0
        self.level_started = None
        self.started_at = None
        self.last_action_at = None
        self.levels: list[dict] = []
        self.actions: list[dict] = []
        self.log_path: Path | None = None
        self._saved_once = False
        self.warning = ""

    # ---------- persistence ----------

    def save(self) -> None:
        """Flush to disk. Called after every action and before a game switch.

        Write-then-replace so an interrupted write cannot corrupt a good file.
        The path is fixed at load time, so a session is one file that grows.
        """
        if self.log_path is None or not self.actions:
            return  # nothing played — do not leave an empty file behind
        # A log that vanished *after we wrote it* was retired deliberately
        # (relabel_log.py moves the file and the mode field together); writing it
        # back resurrects a duplicate under the old label. But a path that has
        # never been written is simply a new session, and must be allowed to
        # save. Keying this on "does any log exist for this game" instead of
        # "did WE write this file" silently stopped every new session for a game
        # that already had a log — a replay would have recorded nothing at all.
        if self._saved_once and not self.log_path.exists():
            return
        tmp = self.log_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.log(), indent=2))
        os.replace(tmp, self.log_path)
        self._saved_once = True

    # ---------- loading ----------

    def load(self, game_id: str, mode: str, layout_seed: int | None = None) -> dict:
        entry = GAMES[game_id]
        module = types.ModuleType("played_game")
        # `@dataclass` resolves its own module through ``sys.modules[__module__]``;
        # an unregistered module makes that lookup return None and the game dies
        # with ``AttributeError: 'NoneType' object has no attribute '__dict__'``,
        # which reads like a broken game and is not. No official game uses
        # @dataclass so this never showed here, but 71 of 190 tufa games do.
        # Same fix, same reason, as probe_games.load_game_class.
        sys.modules["played_game"] = module
        with quiet():
            exec(compile(open(entry["py"]).read(), entry["py"], "exec"), module.__dict__)
        classes = [
            v for v in module.__dict__.values()
            if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame
        ]
        if not classes:
            raise RuntimeError(f"no ARCBaseGame subclass in {entry['py']}")
        game_cls = classes[-1]
        # L-2: refuse an unplayable seed BEFORE the outgoing session is closed,
        # so a typo in the free-entry field costs the session you are in nothing.
        if layout_seed is not None and not accepts_layout_seed(game_cls):
            raise SeedError(
                f"{entry['title']} does not take a layout seed — it was built before the "
                "§7 layout contract, so the canonical build is the only build it has."
            )

        self.close_open_attempt()
        self.save()          # flush the outgoing session before it is discarded
        self.reset_state()

        self.meta = entry
        self.layout_seed = layout_seed
        self.mode = mode if mode in ("discovery", "replay") else "discovery"
        with quiet():
            # §7: None is the authored canonical build and takes NO argument at
            # all — the no-seed branch is upstream's instantiation, untouched.
            self.game = game_cls() if layout_seed is None else game_cls(layout_seed=layout_seed)
            self.frame_data = self.game.perform_action(
                ActionInput(id=GameAction.RESET, data={}), raw=True
            )
        now = time.time()
        self.started_at = now
        self.current_level = int(self.game.level_index)
        self.phase = READY          # staged, counting nothing until you press Start
        # The mode is stamped at load and cannot be changed mid-session, so a
        # selector left on the wrong value silently produces a second log of the
        # same mode — and summarize_play keeps only the latest, which would drop
        # the real run. Say so loudly at the moment it can still be fixed.
        # H-1 item 11: per LAYOUT, because a seeded run is a different board and
        # supersedes no canonical log (and vice versa).
        done = finished_modes(entry["game_id"], self.layout_seed)
        if self.mode in done:
            other = "replay" if self.mode == "discovery" else "discovery"
            layout = "the canonical build" if self.layout_seed is None \
                else f"layout seed {self.layout_seed}"
            self.warning = (
                f"{entry['title']} already has a finished {self.mode} run on {layout}. "
                f"Did you mean {other}? Reload the game with the mode switched — "
                f"a second {self.mode} log of {layout} supersedes the first."
            )
        stamp = datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%d-%H%M%S")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = LOG_DIR / f"{entry['game_id']}__{self.mode}__{stamp}.json"
        return self.snapshot()

    # ---------- level gating ----------

    def start_level(self) -> dict:
        if self.game is None:
            raise RuntimeError("load a game first")
        if self.phase == PLAYING:
            raise PermissionError("this level is already recording")
        if self.phase == FINISHED:
            raise PermissionError("the game is finished — pick another game")
        self.phase = PLAYING
        self.level_actions = 0
        self.level_started = time.time()
        return self.snapshot()

    def goto_level(self, level_1indexed: int) -> dict:
        """Jump to a level. Any attempt in progress is closed as ABANDONED.

        Navigation is not completion: arcengine's ``levels_completed`` stays put
        across ``set_level``, which is exactly why completion is detected from
        that counter and never from ``level_index``.
        """
        if self.game is None:
            raise RuntimeError("load a game first")
        total = len(self.meta["baseline_actions"]) or 1
        target = max(1, min(total, int(level_1indexed))) - 1
        self.close_open_attempt()
        with quiet():
            self.game.set_level(target)
            self.frame_data = self.game.perform_action(
                ActionInput(id=GameAction.RESET, data={}), raw=True
            )
        self.current_level = int(self.game.level_index)
        self.phase = READY
        self.level_actions = 0
        self.save()
        return self.snapshot()

    def refresh_frame(self) -> None:
        """Show the staged level's real starting board.

        The action that clears a level returns a *transitional* frame, not the
        next level's board — so with levels gated behind Start, the staged level
        would render the previous level's last frame until the first action
        landed, and you would play every opening move blind.

        A RESET on the freshly-entered level is a state no-op that re-renders it:
        verified to reproduce the level's ground-truth start frame exactly and to
        leave levels_completed, level_index and available_actions untouched. It
        is never counted and never logged.

        ONLY call this when the game is unfinished. ``handle_reset`` branches to
        ``full_reset()`` when the state is WIN, which would restart the whole
        game (arcengine base_game.handle_reset).
        """
        if self.game is None or self.phase == FINISHED:
            return
        if "WIN" in str(getattr(self.frame_data, "state", "") or "").upper():
            return
        with quiet():
            self.frame_data = self.game.perform_action(
                ActionInput(id=GameAction.RESET, data={}), raw=True
            )

    def close_open_attempt(self) -> None:
        """Record a part-played level you are navigating away from."""
        if self.phase == PLAYING and self.level_actions > 0:
            self.levels.append({
                "level": self.current_level + 1,
                "actions": self.level_actions,
                "status": ABANDONED,
                "wallclock_s": round(time.time() - (self.level_started or time.time()), 1),
                "baseline_actions": self.baseline_for(self.current_level + 1),
            })
        self.level_actions = 0

    # ---------- play ----------

    def baseline_for(self, level_1indexed: int):
        baselines = self.meta["baseline_actions"] if self.meta else []
        if 1 <= level_1indexed <= len(baselines):
            return baselines[level_1indexed - 1]
        return None

    def levels_completed(self) -> int:
        """The authoritative win counter.

        TAAF detects a level win with exactly this field (taaf/game.py:540-547),
        *not* ``game.level_index``: ``next_level()`` is deferred so
        ``level_index`` lags a call behind, and ``set_level()`` moves
        ``level_index`` without completing anything.
        """
        return int(getattr(self.frame_data, "levels_completed", 0) or 0)

    def act(self, action_id: int, x=None, y=None) -> dict:
        if self.game is None:
            raise RuntimeError("load a game first")
        if self.phase != PLAYING:
            raise PermissionError({
                READY: "press Start level — nothing is being counted yet",
                LEVEL_DONE: "level cleared — press Start level for the next one",
                FINISHED: "game finished — pick another game",
            }.get(self.phase, "load a game first"))
        if action_id == 7:
            raise PermissionError(
                "undo is disabled on purpose — the agent has no ACTION7, so using "
                "it would make your action counts incomparable"
            )

        live = [int(a) for a in (getattr(self.frame_data, "available_actions", None) or [])]
        if action_id != 0 and action_id not in live:
            # Not a fault — a fact about the game. Say what it *does* expose, so
            # the refusal teaches rather than just blocking.
            names = {1: "UP", 2: "DOWN", 3: "LEFT", 4: "RIGHT", 5: "ACTION5", 6: "click"}
            have = ", ".join(names.get(a, f"ACTION{a}") for a in live if a != 7) or "nothing"
            raise PermissionError(
                f"{self.meta['title']} does not use {names.get(action_id, f'ACTION{action_id}')}"
                f" — it exposes {have}."
            )

        wins_before = self.levels_completed()
        idx_before = int(self.game.level_index)

        if action_id == 0:
            ai = ActionInput(id=GameAction.RESET, data={})
        elif action_id == 6:
            # ActionInput is a pydantic model with fields (id, data, reasoning):
            # passing x=/y= as kwargs DISCARDS them and the click arrives blank.
            # Games read action.data["x"]; TAAF builds actions the same way
            # (inference/framework/solver.py:1000).
            if x is None or y is None:
                raise PermissionError("a click needs both x and y")
            ai = ActionInput(id=ACT[6], data={"x": int(x), "y": int(y)})
        else:
            ai = ActionInput(id=ACT[action_id], data={})

        with quiet():
            self.frame_data = self.game.perform_action(ai, raw=True)

        # Every action counts, RESET included — taaf/game.py:571 charges it too.
        self.level_actions += 1
        now = time.time()
        self.last_action_at = now
        # arcengine stringifies the enum as "GameState.NOT_FINISHED"; keep the name.
        state = str(getattr(self.frame_data, "state", "") or "").split(".")[-1]
        wins_after = self.levels_completed()
        idx_after = int(self.game.level_index)

        self.actions.append({
            "t": round(now - self.started_at, 3),
            "level": self.current_level + 1,
            "action": "RESET" if action_id == 0 else f"ACTION{action_id}",
            "x": None if action_id != 6 else int(x or 0),
            "y": None if action_id != 6 else int(y or 0),
            "state": state,
            # both counters recorded so any attribution can be audited later
            "levels_completed": wins_after,
            "level_index": idx_after,
        })

        won = wins_after > wins_before or idx_after > idx_before
        if won:
            self.close_level(self.current_level + 1, now)
            # Take whichever counter is further along. `level_index` can lag,
            # because `next_level()` is deferred; `levels_completed` can lag
            # after a `set_level` jump, since navigating completes nothing.
            # Neither is reliable alone; the larger of the two always is.
            total = len(self.meta["baseline_actions"]) or 1
            self.current_level = min(total - 1, max(idx_after, wins_after))
            self.phase = FINISHED if "WIN" in state.upper() else LEVEL_DONE
            if self.phase == LEVEL_DONE:
                self.refresh_frame()
        self.save()
        return self.snapshot()

    def close_level(self, level_1indexed: int, now: float) -> None:
        baseline = self.baseline_for(level_1indexed)
        record = {
            "level": level_1indexed,
            "actions": self.level_actions,
            "status": COMPLETED,
            "wallclock_s": round(now - (self.level_started or now), 1),
        }
        if baseline:
            record["baseline_actions"] = baseline
            record["level_score"] = round(
                compute_level_score(
                    baseline_actions=baseline,
                    agent_steps=self.level_actions,
                    agent_status=COMPLETED,
                ), 2,
            )
            record["ratio"] = round(self.level_actions / baseline, 3)
        self.levels.append(record)
        self.level_actions = 0

    # ---------- reporting ----------

    def snapshot(self) -> dict:
        if self.game is None:
            return {"phase": NO_GAME}
        total = len(self.meta["baseline_actions"]) or 1
        cleared = sorted({lv["level"] for lv in self.levels if lv["status"] == COMPLETED})
        state = str(getattr(self.frame_data, "state", "") or "").split(".")[-1]
        return {
            "phase": self.phase,
            "game_id": self.meta["game_id"],
            "title": self.meta["title"],
            "mode": self.mode,
            "layout_seed": self.layout_seed,     # L-2: null = the canonical build
            "frame": frame_of(self.frame_data).astype(int).tolist(),
            "frames": frames_of(self.frame_data),
            "state": state,
            "level": self.current_level + 1,
            "win_levels": total,
            "levels_cleared": cleared,
            "available_actions": [
                int(a) for a in (getattr(self.frame_data, "available_actions", None) or [])
                if int(a) != 7
            ],
            "level_actions": self.level_actions,
            "baseline_actions": self.baseline_for(self.current_level + 1),
            "levels_done": self.levels,
            "log_file": self.log_path.name if self.log_path else None,
            "warning": self.warning,
            "session_started": self.started_at,
            "session_age_s": round(time.time() - self.started_at) if self.started_at else 0,
            "idle_s": round(time.time() - self.last_action_at) if self.last_action_at else None,
            "server_now": time.time(),
        }

    def log(self) -> dict:
        return {
            "game_id": self.meta["game_id"] if self.meta else None,
            "mode": self.mode,
            # L-2: which layout was played, null = the canonical build. Without
            # it a log of a seeded run is indistinguishable from the packaged one.
            "layout_seed": self.layout_seed,
            "started_at": datetime.fromtimestamp(
                self.started_at or time.time(), timezone.utc
            ).isoformat(),
            "total_actions": len(self.actions),
            "levels": self.levels,
            "actions": self.actions,
        }


def saved_sessions() -> list[dict]:
    """What has already been recorded — drives the progress ticks in the UI."""
    out = []
    for path in sorted(LOG_DIR.glob("*.json")):
        try:
            d = json.loads(path.read_text())
        except Exception:
            continue
        acts = d.get("actions") or []
        out.append({
            "game_id": d.get("game_id"),
            "mode": d.get("mode"),
            # L-2: absent in logs written before the picker existed, which is
            # the same thing it means now — the canonical build.
            "layout_seed": d.get("layout_seed"),
            "levels_completed": sum(
                1 for lv in (d.get("levels") or []) if lv.get("status") == COMPLETED
            ),
            "total_actions": d.get("total_actions", 0),
            # a run that reached WIN is a finished playthrough of that mode
            "finished": bool(acts) and "WIN" in str(acts[-1].get("state", "")).upper(),
            "file": path.name,
        })
    return out


def finished_modes(game_id: str, layout_seed: int | None = None) -> set[str]:
    """Modes already played through to WIN for this game ON THIS LAYOUT.

    VENDORED MODIFICATION (contract H-1 item 11). MEASURED: upstream collapses
    every layout into one answer, and the L-2 seed picker made that wrong — a
    finished canonical `discovery` run raised "already has a finished discovery
    run … a second discovery log supersedes the first" on a load of seed 48217,
    which is a different board and supersedes nothing. The warning's own reason
    is that two logs of the same game AND mode shadow each other, and after L-2
    the layout is part of that identity: `saved_sessions` already reports each
    log's `layout_seed` (absent/null = the canonical build, which is what a
    pre-picker log means too), so the filter reads it.

    `layout_seed=None` therefore means THE CANONICAL BUILD, not "any layout" —
    the same thing it means everywhere else in this file (§7: None is the
    authored build and takes no argument at all).
    """
    return {s["mode"] for s in saved_sessions()
            if s["game_id"] == game_id and s["finished"]
            and s["layout_seed"] == layout_seed}


SESSION = Session()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silence per-request logging
        pass

    def _send(self, payload, code=200, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send((HERE / "index.html").read_bytes(), ctype="text/html")
        if self.path == "/api/games":
            # H-1 item 3: re-scanned per request, so a game packaged while the
            # player is running appears without a restart.
            return self._send([
                {k: v for k, v in g.items() if k != "py"} for g in refresh_games().values()
            ])
        if self.path == "/api/state":
            return self._send(SESSION.snapshot())
        if self.path == "/api/log":
            return self._send(SESSION.log())
        if self.path == "/api/sessions":
            return self._send(saved_sessions())
        return self._send({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        try:
            if self.path == "/api/load":
                return self._send(SESSION.load(
                    body["game_id"], body.get("mode", "discovery"),
                    parse_seed(body.get("layout_seed")),
                ))
            if self.path == "/api/start":
                return self._send(SESSION.start_level())
            if self.path == "/api/level":
                return self._send(SESSION.goto_level(int(body["level"])))
            if self.path == "/api/action":
                return self._send(SESSION.act(int(body["id"]), body.get("x"), body.get("y")))
        except SeedError as exc:
            # L-2: a seed the operator typed. Their input, their fix — a 400 and
            # one plain sentence, never a traceback.
            return self._send({"error": str(exc)}, 400)
        except PermissionError as exc:
            return self._send({"error": str(exc)}, 403)
        except Exception as exc:  # surface the real reason in the UI
            return self._send({"error": f"{type(exc).__name__}: {exc}"}, 500)
        return self._send({"error": "not found"}, 404)


def main() -> int:
    # Say which corpus is live. With two collections playable, "which games am I
    # looking at, and where is this being recorded" must never be a guess.
    official = not os.environ.get("PLAY_GAMES_DIR")
    label = "official" if official else GAMES_DIR.name
    print(f"{len(GAMES)} games — http://127.0.0.1:{PORT}/")
    print(f"  catalog : {GAMES_DIR}  [{label}]")
    print(f"  logs to : {LOG_DIR}")
    if not official:
        print("  (not the calibration corpus — these logs are ignored by the "
              "arc-agi-3-games tools)")
    print("every level is gated: load stages it, Start level begins recording")
    print("undo disabled; RESET counted; discovery/replay set at load time")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
