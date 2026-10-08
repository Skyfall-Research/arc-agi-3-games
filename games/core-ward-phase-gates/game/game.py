"""Core Ward: Toggle the Phase Gates.

A core block sits behind a set of straight lanes.  Each lane is a track of
cells (``terrain.track``) running from a board edge to a *phase gate* that sits
one cell short of the core and flips between closed and open on its own hidden
countdown (``gate.phase``).  Hazard tokens creep inward one cell per turn
(``hazard.timed``); a token that reaches an open gate destroys the core and
ends the run at once (lives: 1).

A gate is always drawn in its own lane colour, in both of its states, so a
gate is a gate on sight and is never rendered as any other kind of thing: what
its phase changes is whether the cell is whole.  Closed, it is a solid block
of that colour plugging the track; open, the block is broken and half of it
drops to background, so the cell reads as withdrawn with the board showing
through.  Nothing else on the board is drawn in a lane colour except that
lane's gate and its panel cluster, and no index anywhere carries two meanings.

Three verbs, one turn each:

* clicking a panel **cluster** group-toggles every gate sharing that lane
  colour (``manip.group_toggle`` / ``gate.remote``);
* clicking a **gate** probes it (``info.probe``) — no state change, but that
  gate's live remaining countdown renders as a pip row until the gate is next
  masked;
* SPACE waits (``state.wait``) — countdowns tick and hazards advance anyway.

A click that reaches neither a gate nor a cluster reaches no verb and is
refused outright: nothing moves and no turn is spent.  The rule is uniform —
an input that resolves to a verb costs one turn, an input that resolves to
none costs nothing.

``agent.patrol``: every turn resolves in two rendered frames.  The first frame
shows the player's effect and then every gate's countdown tick and any
auto-flip it caused; the second frame shows every hazard token step one cell
further along its own track under its own policy, and the resolution against
the gate it reached.  A token advances on every turn, SPACE included, and no
player action anywhere in this game pushes one forward or holds one back —
cause (the flip) is drawn before effect (the token meeting the gate).

``info.recall``: a pip row is live only until that gate is masked again.  A
gate is masked the instant it auto-flips OR the instant any group toggle
reaches it — including a toggle the player aimed at a *different* gate that
merely shares the cluster.  The row reverts to the -2 masked state and renders
as flat background — camouflage: the countdown is concealed again, and a lane
has to be judged from its period and arrival cadence as remembered across
turns rather than from any stored number.  The game's difficulty is that the
cost of a toggle that perturbs a distant, currently-safe gate is not paid on
the turn it is made but many turns later, when that gate's own hazard finally
arrives (retrospective punishment); a countdown carried forward in memory
across such a flip is a false tell.

The level is WON the moment every hazard token of every wave generation has
been blocked, and LOST either the moment one crosses an open gate or when the
turn meter on canvas row 0 fills (``budget.cap``); the win check comes first,
so the winning turn is always free.

Palette discipline: every index carries exactly one role.  0 is background and
is never painted onto the board; 1 is the probed pip and nothing else; 2 is a
lane track cell and nothing else; 3 is the row-0 turn meter and nothing else
(never painted below row 0); 8 is a hazard token and nothing else; 11 is the
selection indicator and nothing else; 14 is the core and nothing else; and a
lane colour is that lane's gate — in either phase — and that colour's panel
cluster, and nothing else.  No index carries a second, conflicting meaning
anywhere, on the board or in the HUD, and no object is ever rendered in the
livery of a different kind of object.
"""

from __future__ import annotations

import copy
import hashlib

import numpy as np
from arcengine import ARCBaseGame, BlockingMode, Camera, GameAction, Level, Sprite

GAME_ID = "core-ward-phase-gates"
DEFAULT_LAYOUT_SEED = 20260924
LAYOUT_NAMESPACE = "core-ward-phase-gates/layout/v1"
LEVEL_COUNT = 8

# ---------------------------------------------------------------------------
# Geometry — ONE render scale for every level: one logical cell = 2x2 pixels.
# The 25x21 logical board is 50x42 pixels, centred below the reserved HUD row.
# ---------------------------------------------------------------------------
GRID_W, GRID_H = 25, 21
CELL = 2
ORIGIN_X, ORIGIN_Y = 7, 11

PANEL_X = 0  # control clusters occupy logical columns 0-1
GUTTER_X = 2  # deliberately empty: the selection indicator's own column
FIELD_X_MIN, FIELD_X_MAX = 3, GRID_W - 1
FIELD_Y_MIN, FIELD_Y_MAX = 1, GRID_H - 1

METER_ROW = 0  # HUD: canvas row 0, reserved, painted last

# ---------------------------------------------------------------------------
# Palette.  ONE role per index, board and HUD alike.
# ---------------------------------------------------------------------------
C_PIP = 1  # a lit countdown pip
C_TRACK = 2  # a lane track cell
C_METER = 3  # the row-0 turn meter fill (never painted below row 0)
C_DANGER = 8  # a hazard token
C_YOU = 11  # the selection indicator
C_CORE = 14  # the core block

C_BLUE = 9
C_PURPLE = 15
C_ORANGE = 12
C_MAGENTA = 6
C_PINK = 7
C_LIGHTBLUE = 10

# The countdown pip row runs on the empty line one cell OUTSIDE the lane,
# alongside the four track cells nearest the gate, two pips per cell.  PIP_CAP
# is >= every period the layout can draw, so a probed row is the countdown
# EXACTLY: the cap is real but never truncates a value.
PIP_CELLS = 4
PIPS_PER_CELL = 2
PIP_CAP = PIP_CELLS * PIPS_PER_CELL
PERIOD_MIN, PERIOD_MAX = 3, PIP_CAP

# Explicit layer for every overlap that matters; never declaration order.
LAYER_LANES = 0
LAYER_CORE = 1
LAYER_GATE = 2
LAYER_PIPS = 3
LAYER_TOKEN = 4
LAYER_CLUSTER = 5
LAYER_MARK = 6
LAYER_METER = 7

# The two clickable roles.  Every sprite the engine advertises as clickable
# carries "sys_click" plus exactly one role tag; step() resolves a click
# through get_sprite_at(..., "sys_click") and branches on that sprite's own
# role tag and its own name — never on the raw coordinates.
TAG_CLICK = "sys_click"
TAG_GATE = "gate"
TAG_CLUSTER = "cluster"

# The complete, closed set of clickable sprite NAMES this game can ever
# instantiate: one gate per lane (at most 8 lanes on the level-8 board) and one
# control cluster per lane colour.  Sprites are built from these names and
# step() branches on exactly these same literals, so the engine's click list
# and the click handler cannot drift apart.
GATE_NAMES = (
    "gate-0", "gate-1", "gate-2", "gate-3",
    "gate-4", "gate-5", "gate-6", "gate-7",
)
CLUSTER_NAMES = {
    6: "cluster-6",
    7: "cluster-7",
    9: "cluster-9",
    10: "cluster-10",
    12: "cluster-12",
    15: "cluster-15",
}

# direction -> unit step from the lane's outer end toward its gate
DIRS = {"W": (1, 0), "E": (-1, 0), "N": (0, 1), "S": (0, -1)}
SLOTS = tuple((d, off) for d in ("W", "E", "N", "S") for off in (-1, 1))

# Per-level authored structure.  Group kinds: "pair" (two lanes on one cluster)
# and "solo" (one lane, its own cluster).  Everything numeric under these —
# core position, slot choice, lane length, period, phase, wave schedule, turn
# budget — is a function of the layout seed.
#
# A coupled pair has two independent knobs, each one entry per pair in the
# level (a bare bool applies to every pair, None lets the seed decide each pair
# on its own).  "wide_pair" is the GEOMETRY: a wide pair takes the two slots
# whose lane lengths are furthest apart (a short/fast lane coupled to a
# long/slow one), a narrow pair the two closest.  "pair_sync" is the TIMING:
# a synced pair's two arrivals are placed back to back, so one well-timed
# toggle covers both; an unsynced pair's arrivals are pushed apart, so the
# toggle that rescues one member perturbs the other long before its own hazard
# is near.  The toggle RULE is identical in every case — only the timing the
# seed produced changes what grouping is worth.
#
# ``lane`` biases a SOLO lane's length choice: "medium" makes the opening
# level pick the slot closest to MEDIUM_LANE cells, so level 1's single lane is
# long enough to watch a token creep the whole way in and long enough for the
# gate to run several phase cycles while it does.  ``demo`` puts level 1's
# first token on the board already pressed up against its closed gate, so the
# very first frame SHOWS what "blocked" looks like before the player acts.
LEVEL_PLAN = (
    {"groups": (("solo", C_BLUE),),
     "gens": 2, "core": "centred", "dormant": False,
     "wide_pair": None, "pair_sync": None, "lane": "medium", "demo": True,
     "base": 4, "depth": (9, 16), "serial": False},
    {"groups": (("pair", C_BLUE), ("solo", C_PURPLE)),
     "gens": 2, "core": "centred", "dormant": False,
     "wide_pair": True, "pair_sync": False, "lane": None, "demo": False,
     "base": 4, "depth": (12, 20), "serial": False},
    {"groups": (("solo", C_PURPLE), ("solo", C_ORANGE), ("pair", C_BLUE)),
     "gens": 2, "core": "centred", "dormant": False,
     "wide_pair": True, "pair_sync": False, "lane": None, "demo": False,
     "base": 4, "depth": (14, 20), "serial": False},
    {"groups": (("pair", C_BLUE), ("solo", C_PURPLE), ("solo", C_ORANGE),
                ("solo", C_MAGENTA)),
     "gens": 2, "core": "corner", "dormant": True,
     "wide_pair": True, "pair_sync": False, "lane": None, "demo": False,
     "base": 5, "depth": (30, 38), "serial": False},
    {"groups": (("pair", C_BLUE), ("pair", C_PURPLE), ("solo", C_ORANGE),
                ("solo", C_MAGENTA)),
     "gens": 2, "core": "centred", "dormant": False,
     "wide_pair": False, "pair_sync": True, "lane": None, "demo": False,
     "base": 5, "depth": (30, 40), "serial": False},
    # L6 runs both couplings at once: one beneficial pair and one risky pair.
    {"groups": (("pair", C_BLUE), ("pair", C_PURPLE), ("solo", C_ORANGE),
                ("solo", C_MAGENTA), ("solo", C_PINK)),
     "gens": 2, "core": "centred", "dormant": True,
     "wide_pair": (False, True), "pair_sync": (True, False),
     "lane": None, "demo": False,
     "base": 5, "depth": (40, 48), "serial": False},
    # L7's one pair deliberately mixes a short/fast lane with a long/slow one.
    {"groups": (("pair", C_BLUE), ("solo", C_PURPLE), ("solo", C_ORANGE),
                ("solo", C_MAGENTA), ("solo", C_PINK), ("solo", C_LIGHTBLUE)),
     "gens": 2, "core": "corner", "dormant": True,
     "wide_pair": True, "pair_sync": True, "lane": None, "demo": False,
     "base": 5, "depth": (49, 58), "serial": False},
    {"groups": (("pair", C_BLUE), ("pair", C_PURPLE), ("solo", C_ORANGE),
                ("solo", C_MAGENTA), ("solo", C_PINK), ("solo", C_LIGHTBLUE)),
     "gens": 3, "core": "corner", "dormant": True,
     "wide_pair": None, "pair_sync": None, "lane": None, "demo": False,
     "base": 5, "depth": (59, 74), "serial": False},
)

VARIANT_TRIES = 200
# Lane count at or below which a level is also proved un-winnable by a single
# click; above it the board carries far more deadlines than one toggle could
# ever cover, and the exhaustive sweep is not worth its cost.
SPARSE_CHECK_LANES = 4
SEARCH_NODES = 1400
# budget.cap headroom: the cap must admit the pipeline's 5 x baseline replay,
# and a baseline is 2-3x the optimal line, so 16x the optimal line with a
# 30-turn floor clears it at every seed.
CAP_FACTOR = 16
CAP_FLOOR = 30


# ---------------------------------------------------------------------------
# deterministic draws
# ---------------------------------------------------------------------------
class _Draw:
    """A seeded byte stream.  Same (seed, tag) -> same sequence, always."""

    def __init__(self, seed: int, *tag: object) -> None:
        self._key = f"{LAYOUT_NAMESPACE}:{int(seed)}:" + ":".join(
            str(t) for t in tag
        )
        self._buf = b""
        self._block = 0

    def byte(self) -> int:
        if not self._buf:
            self._buf = hashlib.sha256(
                f"{self._key}:{self._block}".encode()
            ).digest()
            self._block += 1
        value = self._buf[0]
        self._buf = self._buf[1:]
        return value

    def below(self, n: int) -> int:
        return self.byte() % n if n > 1 else 0

    def between(self, lo: int, hi: int) -> int:
        return lo if hi <= lo else lo + self.below(hi - lo + 1)

    def shuffle(self, items) -> list:
        out = list(items)
        for i in range(len(out) - 1, 0, -1):
            j = self.below(i + 1)
            out[i], out[j] = out[j], out[i]
        return out


# ---------------------------------------------------------------------------
# lane geometry (terrain.track)
# ---------------------------------------------------------------------------
def _lane_geometry(direction: str, off: int, cx: int, cy: int) -> tuple:
    """Gate cell, outer-edge cell and track length for one (direction, offset)."""
    if direction == "W":
        gate, start = (cx - 2, cy + off), (FIELD_X_MIN, cy + off)
    elif direction == "E":
        gate, start = (cx + 2, cy + off), (FIELD_X_MAX, cy + off)
    elif direction == "N":
        gate, start = (cx + off, cy - 2), (cx + off, FIELD_Y_MIN)
    else:
        gate, start = (cx + off, cy + 2), (cx + off, FIELD_Y_MAX)
    length = abs(gate[0] - start[0]) + abs(gate[1] - start[1]) + 1
    return gate, start, length


def lane_cell(lane: dict, index: int) -> tuple:
    """The track cell a token sits on ``index`` steps in from the outer edge."""
    step = DIRS[lane["dir"]]
    sx, sy = lane["start"]
    return sx + step[0] * index, sy + step[1] * index


def cell_px(cx: int, cy: int) -> tuple:
    return ORIGIN_X + CELL * cx, ORIGIN_Y + CELL * cy


def track_pixel(lane: dict, index: int) -> tuple:
    """The single pixel that marks one track cell — a dotted lane line."""
    px, py = cell_px(*lane_cell(lane, index))
    return px, py


def token_pixels(lane: dict, index: int) -> list:
    """A hazard token fills its whole track cell: a 2x2 connected block."""
    px, py = cell_px(*lane_cell(lane, index))
    return [(px + dx, py + dy) for dy in range(CELL) for dx in range(CELL)]


def readout_cells(lane: dict) -> list:
    """The pip-row cells: one cell OUTSIDE the lane, nearest the gate first.

    The row sits on the free line one cell further out than the lane's own
    line, alongside the four track cells behind the gate.  Lanes occupy the
    core's +/-1 offsets, so this +/-2 line is empty on every board: a pip row
    can never cover a track cell, a gate, a token, the core or a cluster.
    """
    step = DIRS[lane["dir"]]
    off = lane["off"]
    shift = (0, off) if step[0] else (off, 0)
    cells = []
    for k in range(1, PIP_CELLS + 1):
        cx, cy = lane_cell(lane, lane["length"] - 1 - k)
        cells.append((cx + shift[0], cy + shift[1]))
    return cells


def readout_pixels(lane: dict) -> list:
    """Canvas pixels of the gate's pip row, pip 0 nearest the gate."""
    step = DIRS[lane["dir"]]
    out = []
    for cx, cy in readout_cells(lane):
        px, py = cell_px(cx, cy)
        if step[0]:
            cols = [px + 1, px] if step[0] > 0 else [px, px + 1]
            out.extend((col, py) for col in cols)
        else:
            rows = [py + 1, py] if step[1] > 0 else [py, py + 1]
            out.extend((px, row) for row in rows)
    return out


# ---------------------------------------------------------------------------
# hit regions (canvas pixels) — the solver reads these off the layout
# ---------------------------------------------------------------------------
def gate_box(lane: dict) -> tuple:
    px, py = cell_px(*lane["gate"])
    return px, py, CELL, CELL


def cluster_box(entry: dict, color: int) -> tuple:
    row = entry["panel_rows"][entry["colors"].index(color)]
    px, py = cell_px(PANEL_X, row)
    return px, py, 2 * CELL, 2 * CELL


def gate_click(lane: dict) -> tuple:
    box = gate_box(lane)
    return box[0], box[1]


def cluster_click(entry: dict, color: int) -> tuple:
    box = cluster_box(entry, color)
    return box[0], box[1]


# ---------------------------------------------------------------------------
# the rule layer, as a pure simulation (shared by the game and the planner)
# ---------------------------------------------------------------------------
class Sim:
    """One level's state machine, resolved in the spec's fixed turn order.

    ``step_head`` is the player's effect plus every countdown tick and any
    auto-flip it caused; ``step_tail`` is every hazard token's own one-cell
    advance along its track (``agent.patrol``) and the resolution against the
    gate each token reached.  Both halves are driven by elapsed turns alone and
    the game renders one frame between them, so a flip is always drawn before
    the token meets the gate.
    """

    def __init__(self, entry: dict) -> None:
        self.entry = entry
        self.lanes = entry["lanes"]
        self.cap = entry["cap"]
        n = len(self.lanes)
        self.closed = [True] * n
        self.countdown = [lane["countdown"] for lane in self.lanes]
        self.unmasked = [False] * n
        self.tokens = [[] for _ in range(n)]
        self.next_spawn = [0] * n
        self.turn = 0
        self.blocked = 0
        self.total = sum(len(lane["spawns"]) for lane in self.lanes)
        self.lost = False
        self._spawn_due()

    def _spawn_due(self) -> None:
        """Put on the board every token whose spawn turn has come.

        A spawn turn at or before turn 0 places its token that many cells in
        from the outer edge instead of at the edge itself, so a level can open
        with a hazard already part-way down its track.
        """
        for i, lane in enumerate(self.lanes):
            while (self.next_spawn[i] < len(lane["spawns"])
                   and lane["spawns"][self.next_spawn[i]] <= self.turn):
                start = max(0, -lane["spawns"][self.next_spawn[i]])
                self.tokens[i].append(start)
                self.next_spawn[i] += 1

    @property
    def resolved(self) -> bool:
        """Every wave generation has spawned and every token was blocked."""
        return self.blocked >= self.total and not any(self.tokens)

    @property
    def finished(self) -> bool:
        return self.lost or self.resolved or self.turn >= self.cap

    def step_head(self, action) -> None:
        kind = action[0]

        # 1 — the player's instantaneous effect
        if kind == "toggle":
            color = action[1]
            for i, lane in enumerate(self.lanes):
                if lane["color"] == color:
                    # manip.group_toggle: unconditional on every gate of this
                    # colour — flip it, restart its period, mask its readout.
                    # info.recall: the mask discards the probed value on every
                    # gate of the colour, including one the player was not
                    # aiming at, so what that gate is doing next is only
                    # knowable from its period as remembered from earlier.
                    self.closed[i] = not self.closed[i]
                    self.countdown[i] = lane["period"]
                    self.unmasked[i] = False
        elif kind == "probe":
            self.unmasked[action[1]] = True

        self.turn += 1

        # 2 — gate.phase: every countdown ticks on its own; a gate reaching 0
        # flips and re-masks, so a dormant lane the player stopped watching
        # comes back to attention with a fresh, unprobed countdown and only
        # its recalled period to judge it by (info.recall).
        for i, lane in enumerate(self.lanes):
            self.countdown[i] -= 1
            if self.countdown[i] <= 0:
                self.closed[i] = not self.closed[i]
                self.countdown[i] = lane["period"]
                self.unmasked[i] = False

    def step_tail(self) -> None:
        # 3 — agent.patrol: every hazard token runs its own policy, which is
        # "step one cell further along my terrain.track, every turn, forever".
        # No player action reaches this loop, so a token closes on its gate
        # whatever the player spent the turn on.
        for i in range(len(self.lanes)):
            self.tokens[i] = [p + 1 for p in self.tokens[i]]

        # 4 — tokens that reached the gate cell resolve against its state
        for i, lane in enumerate(self.lanes):
            gate_index = lane["length"] - 1
            remaining = []
            for pos in self.tokens[i]:
                if pos < gate_index:
                    remaining.append(pos)
                elif self.closed[i]:
                    self.blocked += 1
                else:
                    self.lost = True
                    remaining.append(pos)
            self.tokens[i] = remaining

        # 5 — scheduled spawns for this turn
        self._spawn_due()

    def step(self, action) -> None:
        self.step_head(action)
        self.step_tail()


# ---------------------------------------------------------------------------
# planner — a gate's phase under a chosen set of toggle turns
# ---------------------------------------------------------------------------
def _gate_states(lane: dict, toggles, horizon: int) -> list:
    """closed/open of one gate after each turn 1..horizon, given its toggles.

    Exactly the order Sim.step_head uses: the toggle lands first, then the tick.
    """
    period = lane["period"]
    countdown = lane["countdown"]
    closed = True
    hits = set(toggles)
    out = [True] * (horizon + 1)
    for turn in range(1, horizon + 1):
        if turn in hits:
            closed = not closed
            countdown = period
        countdown -= 1
        if countdown <= 0:
            closed = not closed
            countdown = period
        out[turn] = closed
    return out


def _deadlines(lane: dict) -> list:
    """The turns on which this lane's gate must be closed, one per wave."""
    return [s + lane["length"] - 1 for s in lane["spawns"]]


def _schedule_colour(lanes, indices, used, window) -> list | None:
    """Toggle turns for one colour that satisfy every deadline it owns."""
    duties = sorted((d, i) for i in indices for d in _deadlines(lanes[i]))
    if not duties:
        return []
    nodes = [SEARCH_NODES]

    def satisfied(toggles, upto):
        horizon = duties[upto][0]
        cache = {}
        for deadline, lane_index in duties[:upto + 1]:
            states = cache.get(lane_index)
            if states is None:
                states = _gate_states(lanes[lane_index], toggles, horizon)
                cache[lane_index] = states
            if not states[deadline]:
                return False
        return True

    def recurse(k: int, toggles: list):
        if nodes[0] <= 0:
            return None
        nodes[0] -= 1
        if k == len(duties):
            return toggles
        turn = duties[k][0]
        if satisfied(toggles, k):
            found = recurse(k + 1, toggles)
            if found is not None:
                return found
        low = max(toggles[-1] if toggles else 0, turn - window, 0)
        for t in range(turn, low, -1):
            if t in used:
                continue
            candidate = toggles + [t]
            if satisfied(candidate, k):
                found = recurse(k + 1, candidate)
                if found is not None:
                    return found
        return None

    return recurse(0, [])


def plan_level(entry: dict) -> list | None:
    """A winning action line for one level, derived from the layout itself.

    Toggle turns are searched per lane colour (a cluster always moves every
    gate of its colour at once); the turns left over carry probes and waits.
    The line ends on the turn the last wave is blocked, which is the turn the
    level is won.
    """
    lanes = entry["lanes"]
    horizon = entry["depth"]
    window = 2 * PERIOD_MAX + 2
    used = set()
    toggle_turns = {}

    def first_duty(color):
        return min(d for i, lane in enumerate(lanes) if lane["color"] == color
                   for d in _deadlines(lane))

    for color in sorted(entry["colors"], key=first_duty):
        indices = [i for i, lane in enumerate(lanes) if lane["color"] == color]
        chosen = _schedule_colour(lanes, indices, used, window)
        if chosen is None:
            return None
        toggle_turns[color] = chosen
        used.update(chosen)

    per_turn = {}
    for color, turns in toggle_turns.items():
        for t in turns:
            per_turn[t] = ("toggle", color)

    actions = []
    lane_count = len(lanes)
    for t in range(1, horizon + 1):
        if t in per_turn:
            actions.append(per_turn[t])
        elif t % 3 == 1:
            # info.probe on a rotating gate: free information, no state change.
            actions.append(("probe", (t // 3) % lane_count))
        else:
            # state.wait: let the countdowns and the hazards run on their own.
            actions.append(("wait",))
    return actions


def run_plan(entry: dict, actions) -> Sim:
    sim = Sim(entry)
    for action in actions:
        if sim.finished:
            break
        sim.step(action)
    return sim


def _line_fails(entry: dict, action) -> bool:
    """A one-note line (always wait, or always the same toggle) must lose."""
    sim = Sim(entry)
    while not sim.finished:
        sim.step(action)
    return sim.lost or not sim.resolved


def _sparse_line_wins(entry: dict, toggles: dict) -> bool:
    """Does waiting every turn except the given toggle turns win the level?"""
    sim = Sim(entry)
    while not sim.finished:
        sim.step(toggles.get(sim.turn + 1, ("wait",)))
    return sim.resolved and not sim.lost


def _one_toggle_wins(entry: dict) -> bool:
    """Can a single well-placed click — or none at all — carry the level?

    On a board with few lanes there is a real danger that the whole level
    collapses to "find the one turn to hit the one cluster", which a policy
    clicking at random can stumble into.  A level that answers True here is
    thrown away: the levels that ship need at least two separately-timed
    toggles, which is what makes reading the gate before acting the only way
    through rather than a nicety.
    """
    horizon = min(entry["cap"], entry["depth"] + PERIOD_MAX)
    for color in entry["colors"]:
        for turn in range(1, horizon + 1):
            if _sparse_line_wins(entry, {turn: ("toggle", color)}):
                return True
    return False


# ---------------------------------------------------------------------------
# §7 layout from seed — PURE, module level, JSON-able
# ---------------------------------------------------------------------------
# Core placement keeps every lane long enough for its pip row to render the
# countdown in full: PIP_CELLS cells behind the gate plus the gate's own cell.
CORE_X_LO = FIELD_X_MIN + PIP_CELLS + 2
CORE_X_HI = FIELD_X_MAX - PIP_CELLS - 2
CORE_Y_LO = FIELD_Y_MIN + PIP_CELLS + 2
CORE_Y_HI = FIELD_Y_MAX - PIP_CELLS - 2
CENTRE_X_LO, CENTRE_X_HI = 11, 16
CENTRE_Y_LO, CENTRE_Y_HI = 9, 12
# The opening level's lane length target: long enough that a token's whole
# creep inward is watchable and the gate runs several phase cycles on the way.
MEDIUM_LANE = 8


def _core_position(draw: _Draw, kind: str) -> tuple:
    """Where the core block sits — a structural draw, not a cosmetic nudge."""
    if kind == "corner":
        # Offset hard toward one of the four corners of the legal box, so some
        # lanes are barely 5 cells long and their opposites stretch across it.
        quadrant = draw.below(4)
        near_x, near_y = draw.below(2), draw.below(2)
        cx = (CORE_X_LO + near_x if quadrant in (0, 2)
              else CORE_X_HI - near_x)
        cy = (CORE_Y_LO + near_y if quadrant in (0, 1)
              else CORE_Y_HI - near_y)
        return cx, cy
    if kind == "short":
        # The opening level wants one genuinely short lane: push the core to
        # one end of ONE axis (which axis, and which end, is the seed's) and
        # leave the other axis mid-board.
        axis, side, near = draw.below(2), draw.below(2), draw.below(2)
        if axis == 0:
            cx = CORE_X_LO + near if side == 0 else CORE_X_HI - near
            return cx, draw.between(CENTRE_Y_LO, CENTRE_Y_HI)
        cy = CORE_Y_LO + near if side == 0 else CORE_Y_HI - near
        return draw.between(CENTRE_X_LO, CENTRE_X_HI), cy
    return (draw.between(CENTRE_X_LO, CENTRE_X_HI),
            draw.between(CENTRE_Y_LO, CENTRE_Y_HI))


def _pair_flags(draw: _Draw, groups, declared) -> list:
    """One verdict per coupled pair in the level, for one of the pair knobs."""
    count = sum(1 for kind, _color in groups if kind == "pair")
    if isinstance(declared, (tuple, list)):
        return [bool(declared[k % len(declared)]) for k in range(count)]
    if declared is None:
        return [draw.below(2) == 0 for _ in range(count)]
    return [bool(declared)] * count


def _pick_slots(draw: _Draw, groups, cx: int, cy: int, wides,
                lane_bias: str | None = None) -> list:
    """Give every lane a (direction, offset) slot.

    A coupled pair takes the two slots whose lane lengths are furthest apart
    (wide) or closest together — a contrast that exists only because the seed
    moved the core, so it really is structural.  ``lane_bias`` of "medium"
    front-loads the pool with the slot whose run is closest to MEDIUM_LANE,
    which is how the opening level gets one lane a player can actually watch.
    """
    pool = draw.shuffle(SLOTS)
    lengths = {
        slot: _lane_geometry(slot[0], slot[1], cx, cy)[2] for slot in SLOTS
    }
    if lane_bias == "medium":
        # Prefer a run of at least MEDIUM_LANE cells and then the closest to
        # it: a token has to be watchable creeping the whole way in for the
        # opening level to teach anything, so erring long beats erring short.
        # The seeded shuffle stays the tie-break, so which of two equally good
        # slots wins is still the seed's decision.
        shuffled = {slot: k for k, slot in enumerate(pool)}
        pool.sort(key=lambda s: (lengths[s] < MEDIUM_LANE,
                                 abs(lengths[s] - MEDIUM_LANE), shuffled[s]))
    assigned = []
    pair_index = 0
    for kind, _color in groups:
        if kind != "pair":
            continue
        wide = wides[pair_index]
        pair_index += 1
        best = None
        for a in range(len(pool)):
            for b in range(a + 1, len(pool)):
                gap = abs(lengths[pool[a]] - lengths[pool[b]])
                score = gap if wide else -gap
                if best is None or score > best[0]:
                    best = (score, a, b)
        _, a, b = best
        assigned.append((pool[a], pool[b]))
        pool = [s for k, s in enumerate(pool) if k not in (a, b)]
    out = []
    pair_index = 0
    for kind, _color in groups:
        if kind == "pair":
            out.append(assigned[pair_index])
            pair_index += 1
        else:
            out.append((pool.pop(0),))
    return out


def _couple_order(wave: list, couples) -> list:
    """Place each pair's two arrivals back to back, or push them apart.

    The cluster rule is untouched — a toggle always moves every gate of its
    colour.  What moves here is only WHEN the pair's two hazards arrive, which
    is what makes one pair a two-for-one rescue and another a liability.
    """
    out = list(wave)
    for a, b, synced in couples:
        if a not in out or b not in out:
            continue
        out.remove(b)
        if synced:
            out.insert(out.index(a) + 1, b)
        else:
            out.append(b)
    return out


def _schedule_arrivals(draw: _Draw, lanes, order, plan) -> list:
    """One arrival turn per (lane, generation), spread across the level.

    Arrivals walk from ``base`` out to a seeded target depth; the level's
    dormant lane keeps the final slot behind a long quiet gap, so it revives
    many turns after its earlier wave looked finished.
    """
    n = len(order)
    lo, hi = plan["depth"]
    target = draw.between(lo, hi)
    gap = draw.between(6, 10) if plan["dormant"] else 1
    base = plan["base"]
    spread_hi = max(base, target - gap)
    arrivals = [0] * n
    lane_last: dict[int, int] = {}

    def earliest(index: int) -> int:
        lane = lanes[index]
        need = lane["length"] - 1
        prev = lane_last.get(index)
        if prev is not None:
            step = lane["length"] - 1 if plan["serial"] else 2
            need = max(need, prev + step)
        return need

    for p in range(n - 1):
        index = order[p][0]
        if p == 0:
            # The first wave spawns on turn 0, so the level's opening frame
            # already shows a hazard token standing on its track.
            arrivals[p] = earliest(index)
        else:
            want = (base + ((spread_hi - base) * p) // max(1, n - 1)
                    + draw.below(2))
            arrivals[p] = max(want, earliest(index))
        lane_last[index] = arrivals[p]

    index = order[n - 1][0]
    others = max(arrivals[:n - 1]) if n > 1 else 0
    arrivals[n - 1] = max(target, earliest(index), others + gap)
    return arrivals


def _build_entry(seed: int, index: int, variant: int) -> dict:
    plan = LEVEL_PLAN[index]
    structure = _Draw(seed, index, "structure")
    cx, cy = _core_position(structure, plan["core"])
    wides = _pair_flags(structure, plan["groups"], plan["wide_pair"])
    syncs = _pair_flags(structure, plan["groups"], plan["pair_sync"])
    slot_groups = _pick_slots(structure, plan["groups"], cx, cy, wides,
                              plan["lane"])

    timing = _Draw(seed, index, "timing", variant)
    lanes = []
    colors = []
    couples = []  # (lane_a, lane_b, arrivals_synced) for every coupled pair
    pair_index = 0
    for (kind, color), slots in zip(plan["groups"], slot_groups):
        colors.append(color)
        if kind == "pair":
            couples.append((len(lanes), len(lanes) + 1, syncs[pair_index]))
            pair_index += 1
        for direction, off in slots:
            gate, start, length = _lane_geometry(direction, off, cx, cy)
            period = timing.between(PERIOD_MIN, PERIOD_MAX)
            # The demo level's gate must still be shut when its opening token
            # reaches it on turn 1, so its countdown starts at 2 or more; the
            # seed still picks the value, and the period behind it, freely.
            first_tick = 2 if plan["demo"] else 1
            lanes.append({
                "color": color,
                "dir": direction,
                "off": off,
                "gate": [gate[0], gate[1]],
                "start": [start[0], start[1]],
                "length": length,
                "period": period,
                "countdown": timing.between(first_tick, period),
                "spawns": [],
            })

    # Wave order: one generation at a time in a seeded lane order, with each
    # coupled pair's two members placed together or pushed apart, and the
    # dormant lane's final generation moved to the very end of the sequence.
    gens = plan["gens"]
    lane_count = len(lanes)
    dormant = (timing.below(lane_count)
               if plan["dormant"] and gens > 1 else -1)
    order = []
    for generation in range(gens):
        wave = _couple_order(timing.shuffle(range(lane_count)), couples)
        for i in wave:
            if i == dormant and generation == gens - 1:
                continue
            order.append((i, generation))
    if dormant >= 0:
        order.append((dormant, gens - 1))

    arrivals = _schedule_arrivals(timing, lanes, order, plan)
    for (i, _generation), arrival in zip(order, arrivals):
        lanes[i]["spawns"].append(arrival - (lanes[i]["length"] - 1))
    if plan["demo"]:
        # The teaching token: already on the board at reset, one cell short of
        # its gate, so the opening FRAME shows the win condition holding — a
        # hazard stopped dead at a shut gate with the core whole behind it —
        # and turn 1 shows that hold resolve, before the player has had to
        # work anything out.  It arrives on the gate's starting closed state,
        # so it costs no toggle and leaves both real waves to be timed.
        lanes[0]["spawns"].append(2 - lanes[0]["length"])
    for lane in lanes:
        lane["spawns"].sort()

    panel = _Draw(seed, index, "panel")
    span = 3 * len(colors) - 1
    first_row = panel.between(
        FIELD_Y_MIN, max(FIELD_Y_MIN, FIELD_Y_MAX - span)
    )
    panel_rows = [first_row + 3 * k for k in range(len(colors))]

    # depth: the turn the last wave is blocked, which is the turn the level is
    # won.  budget.cap is sized off it with generous headroom — the meter is a
    # backstop bound on run length, never the thing the player is racing.
    depth = max(arrivals)
    cap = max(CAP_FLOOR, CAP_FACTOR * depth)

    return {
        "level": index + 1,
        "grid": [GRID_W, GRID_H],
        "core": [cx, cy],
        "colors": colors,
        "panel_rows": panel_rows,
        "lanes": lanes,
        "depth": depth,
        "cap": cap,
        "variant": variant,
    }


def _entry_quality(entry: dict, plan: dict) -> int:
    """Is this entry a usable level, and how well does it hit its target?

    The one-note lines are checked FIRST and are mandatory on every level, not
    a preference: a level no brainless policy can beat is the whole point, and
    these are the brainless policies.  Doing the same thing every single turn
    — waiting, which is also all that repeatedly probing one gate amounts to,
    or toggling one cluster over and over — must never finish a level.  Only
    entries that survive all of them are handed to the (much more expensive)
    winning-line search.  ``-1`` means unusable; higher is better.
    """
    if not _line_fails(entry, ("wait",)):
        return -1
    for color in entry["colors"]:
        if not _line_fails(entry, ("toggle", color)):
            return -1
    if len(entry["lanes"]) <= SPARSE_CHECK_LANES and _one_toggle_wins(entry):
        return -1
    actions = plan_level(entry)
    if actions is None:
        return -1
    sim = run_plan(entry, actions)
    if sim.lost or not sim.resolved:
        return -1
    lo, hi = plan["depth"]
    return 1 if lo <= entry["depth"] <= hi else 0


_LAYOUT_CACHE: dict[int, list] = {}


def build_layout(seed: int) -> list:
    """One JSON-able entry per level; every structure below is seed-derived."""
    seed = int(seed)
    cached = _LAYOUT_CACHE.get(seed)
    if cached is None:
        cached = _compute_layout(seed)
        _LAYOUT_CACHE[seed] = cached
    return copy.deepcopy(cached)


def _compute_layout(seed: int) -> list:
    layout = []
    for index in range(LEVEL_COUNT):
        plan = LEVEL_PLAN[index]
        best = None
        for variant in range(VARIANT_TRIES):
            entry = _build_entry(seed, index, variant)
            score = _entry_quality(entry, plan)
            if score < 0:
                continue
            if best is None or score > best[0]:
                best = (score, entry)
            if score == 1:
                break
        if best is None:
            raise ValueError(
                f"no playable variant for level {index + 1} at seed {seed}"
            )
        layout.append(best[1])
    return layout


# ---------------------------------------------------------------------------
# the game
# ---------------------------------------------------------------------------
def _blank(width: int, height: int) -> np.ndarray:
    return np.full((height, width), -1, dtype=np.int8)


class CoreWardPhaseGates(ARCBaseGame):
    """Keep the core intact: probe a gate, or group-toggle a colour, or wait."""

    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed
        self._layout = build_layout(seed)
        self._entry = self._layout[0]
        self._sim = None
        self._pending = None
        self._selected = None
        self._gate_of = {}
        self._color_of = {}
        levels = [
            Level(sprites=[], data={"entry": entry},
                  name=f"level-{entry['level']}")
            for entry in self._layout
        ]
        super().__init__(
            game_id=GAME_ID,
            levels=levels,
            camera=Camera(width=64, height=64, background=0, letter_box=0),
            available_actions=[5, 6],
        )

    # -- level setup -------------------------------------------------------
    def on_set_level(self, level: Level) -> None:
        entry = level.get_data("entry")
        self._entry = entry
        self._sim = Sim(entry)
        self._pending = None
        self._selected = None
        self._gate_of = {}
        self._color_of = {}
        level.remove_all_sprites()

        # terrain.track: one pixel per track cell, from the board edge to the
        # gate, so the whole route a hazard walks is visible before it walks it.
        board = _blank(64, 64)
        for lane in entry["lanes"]:
            for i in range(lane["length"] - 1):
                px, py = track_pixel(lane, i)
                board[py, px] = C_TRACK
        self._spr_board = Sprite(board, name="lanes", x=0, y=0,
                                 layer=LAYER_LANES, tags=[])
        level.add_sprite(self._spr_board)

        cx, cy = entry["core"]
        px, py = cell_px(cx - 1, cy - 1)
        self._spr_core = Sprite(
            np.full((3 * CELL, 3 * CELL), C_CORE, dtype=np.int8),
            name="core", x=px, y=py, layer=LAYER_CORE, tags=[],
        )
        level.add_sprite(self._spr_core)

        # Gates and clusters are the only clickable sprites; each carries
        # TAG_CLICK plus its role tag, and the lookups below are what step()
        # dispatches on, so every advertised click lands on a handled verb.
        # BOUNDING_BOX keeps the whole cell live even while a gate renders
        # open, so a gate's hit region never depends on its phase.
        self._spr_gates = []
        for i, lane in enumerate(entry["lanes"]):
            gx, gy, _, _ = gate_box(lane)
            name = GATE_NAMES[i]
            sprite = Sprite(
                np.full((CELL, CELL), lane["color"], dtype=np.int8),
                name=name, x=gx, y=gy, layer=LAYER_GATE,
                blocking=BlockingMode.BOUNDING_BOX,
                tags=[TAG_CLICK, TAG_GATE],
            )
            self._gate_of[name] = i
            self._spr_gates.append(sprite)
            level.add_sprite(sprite)

        # gate.remote: a cluster sits in the side panel, columns apart from
        # every gate it controls, and reaches all of them in one step.
        self._spr_clusters = []
        for color in entry["colors"]:
            bx, by, bw, bh = cluster_box(entry, color)
            name = CLUSTER_NAMES[color]
            sprite = Sprite(
                np.full((bh, bw), color, dtype=np.int8),
                name=name, x=bx, y=by, layer=LAYER_CLUSTER,
                blocking=BlockingMode.BOUNDING_BOX,
                tags=[TAG_CLICK, TAG_CLUSTER],
            )
            self._color_of[name] = color
            self._spr_clusters.append(sprite)
            level.add_sprite(sprite)

        self._spr_pips = Sprite(_blank(64, 64), name="gate-readout", x=0, y=0,
                                layer=LAYER_PIPS, tags=[])
        self._spr_tokens = Sprite(_blank(64, 64), name="hazards", x=0, y=0,
                                  layer=LAYER_TOKEN, tags=[])
        self._spr_mark = Sprite(
            _blank(CELL, GRID_H * CELL), name="selection",
            x=cell_px(GUTTER_X, 0)[0], y=cell_px(0, 0)[1],
            layer=LAYER_MARK, tags=[],
        )
        self._spr_meter = Sprite(_blank(64, 1), name="meter", x=0,
                                 y=METER_ROW, layer=LAYER_METER, tags=[])
        for sprite in (self._spr_pips, self._spr_tokens, self._spr_mark,
                       self._spr_meter):
            level.add_sprite(sprite)

        self._paint()

    # -- the engine's one entry point -------------------------------------
    def step(self) -> None:
        if self._pending is not None:
            # Second half of the turn already begun: every hazard token takes
            # its own step now, on the frame after the one that showed the
            # flips (agent.patrol along terrain.track).
            self._pending = None
            self._sim.step_tail()
            self._paint()
            self._settle()
            return

        action = self.action

        if action.id is GameAction.ACTION5:
            # state.wait — the turn passes and nothing else happens.  Nothing
            # was selected, so the selection indicator clears.
            self._selected = None
            self._begin(("wait",))
            return

        if action.id is GameAction.ACTION6:
            x = int(action.data.get("x") or 0)
            y = int(action.data.get("y") or 0)
            # Resolve the click to the engine's own clickable sprite, then
            # branch on that sprite's own role tag and its own name — never on
            # the raw coordinates.  The two literal name sets below are the
            # WHOLE click list the engine can ever advertise (every control
            # cluster and every phase gate on every level), so no sys_click
            # sprite is left wired to a name this handler does not act on.
            target = self.current_level.get_sprite_at(x, y, TAG_CLICK)
            name = target.name if target is not None else ""
            tags = list(target.tags) if target is not None else []
            if TAG_CLUSTER in tags and name in (
                "cluster-6", "cluster-7", "cluster-9",
                "cluster-10", "cluster-12", "cluster-15",
            ):
                # manip.group_toggle / gate.remote, keyed by the cluster's own
                # lane-colour id.  Retrospective punishment: this reaches every
                # gate of the colour at once, so a toggle that rescues the lane
                # whose token is closest can leave a distant partner gate open,
                # and that bill is only presented many turns later, when the
                # partner's own token finally walks onto it.
                color = self._color_of[name]
                self._selected = color
                self._begin(("toggle", color))
                return
            if TAG_GATE in tags and name in (
                "gate-0", "gate-1", "gate-2", "gate-3",
                "gate-4", "gate-5", "gate-6", "gate-7",
            ):
                # info.probe, keyed by that gate's own id.
                index = self._gate_of[name]
                self._selected = self._entry["lanes"][index]["color"]
                self._begin(("probe", index))
                return
            # A click that reaches neither a gate nor a cluster reaches no
            # verb, so it is refused: the indicator goes empty and the board
            # is left exactly as it stood — no turn, no tick, no advance.  One
            # rule, no exceptions: an input that resolves to a verb spends a
            # turn, an input that resolves to none spends nothing.
            self._selected = None
            self._paint()
            self.complete_action()
            return

        # ACTION1-4 and ACTION7 are absent from this game.  They still reach
        # step(), and they do nothing at all: no turn, no state, no repaint —
        # the frame an absent action renders is pixel-identical to the one
        # before it, so nothing about the board can be learned by sending one.
        self.complete_action()

    def _begin(self, verb) -> None:
        """First half of the turn: the verb, then every countdown tick."""
        self._sim.step_head(verb)
        self._paint()
        # Deliberately no complete_action(): the engine renders this frame and
        # calls step() again, which runs the hazard advance and completes.
        self._pending = verb

    def _settle(self) -> None:
        sim = self._sim
        if sim.lost:
            # A hazard crossed an open gate: the core is destroyed, lives: 1.
            self.lose()
        elif sim.resolved:
            # goal.survive: every wave generation blocked, core intact.  The
            # win check runs before the budget check, so the winning turn is
            # free even on the turn the meter would fill.
            self.next_level()
        elif sim.turn >= self._entry["cap"]:
            # budget.cap exhausted with hazards still unresolved.
            self.lose()
        self.complete_action()

    # -- rendering ---------------------------------------------------------
    def _paint(self) -> None:
        sim = self._sim
        entry = self._entry
        lanes = entry["lanes"]

        # The core.  Intact it is the goal block; the turn a hazard crosses an
        # open gate the block is gone in that same frame — one state change,
        # not a process — leaving the breaching token in danger red on the
        # gate cell it came through.
        self._spr_core.pixels[:, :] = -1 if sim.lost else C_CORE

        # gate.phase.  A gate is ALWAYS drawn in its own lane colour and in no
        # other index, so a gate is a gate on sight whatever phase it is in;
        # what the phase changes is whether that cell is whole.  Closed, the
        # gate is a solid block of the lane's colour, plugging the track.
        # Open, the block is broken: half its pixels drop to background, so
        # the cell reads as withdrawn with the dark board showing through it.
        # An open gate is never drawn in the track index and never drawn as
        # anything but a gate.
        for i, lane in enumerate(lanes):
            pixels = self._spr_gates[i].pixels
            pixels[:, :] = lane["color"]
            if not sim.closed[i]:
                for k in range(CELL):
                    pixels[k, (k + 1) % CELL] = -1

        # Countdown pip rows.  The `gate-readout` mask is the declared reader
        # of this sprite's -2 pixels: a masked gate (never probed, or re-masked
        # by its last flip or by a group toggle that reached it) writes -2
        # across its whole row, which renders as flat background — camouflage:
        # the countdown is concealed again, leaving the period recalled from an
        # earlier observation as the only thing left to judge that gate by
        # (info.recall).  A probed gate shows its live countdown,
        # one lit pip per turn left, never truncated; the fixed period behind
        # that countdown is never drawn at all.  The row is true for exactly as
        # long as it is drawn, and the number a player carried away from it
        # becomes a false tell the moment that gate flips and the row goes
        # back to flat background without announcing it.
        pips = self._spr_pips.pixels
        pips[:, :] = -1
        for i, lane in enumerate(lanes):
            row = readout_pixels(lane)
            if not sim.unmasked[i]:
                for px, py in row:
                    pips[py, px] = -2
                continue
            for k, (px, py) in enumerate(row):
                if k < sim.countdown[i]:
                    pips[py, px] = C_PIP

        # hazard.timed: each token fills its own track cell in danger red.
        tokens = self._spr_tokens.pixels
        tokens[:, :] = -1
        for i, lane in enumerate(lanes):
            for pos in sim.tokens[i]:
                for px, py in token_pixels(lane, pos):
                    tokens[py, px] = C_DANGER

        # The selection indicator — the locus of control.  Both verbs are
        # lane-colour verbs (a cluster IS a colour; a gate BELONGS to one), so
        # the indicator states the one thing it can always state truthfully:
        # which colour the last input concerned.  It sits in the empty gutter
        # column immediately beside that colour's panel cluster, so the player
        # reads the correspondence straight off the board with nothing to
        # learn, and it covers no lane, gate, token, core or cluster.  One
        # colour, one slot, no two inputs sharing a slot they do not share a
        # colour for; an input that concerned no colour leaves it empty.
        mark = self._spr_mark.pixels
        mark[:, :] = -1
        if self._selected is not None:
            row = entry["panel_rows"][entry["colors"].index(self._selected)]
            top = CELL * row
            mark[top:top + 2 * CELL, :] = C_YOU

        # budget.cap on the reserved HUD row 0, painted last: the whole row is
        # the level's cap and elapsed turns fill it left to right.  C_METER is
        # painted here and nowhere else, so no board entity can be mistaken for
        # the meter or the meter for board state.
        meter = self._spr_meter.pixels
        meter[0, :] = -1
        cap = max(1, entry["cap"])
        filled = min(64, (64 * sim.turn) // cap)
        if sim.turn:
            # A turn that has elapsed always shows, so the row reads as a
            # meter from the first turn rather than as a dead strip; the cap
            # has to be many times the winning line's length, so without this
            # an entire honest run would round down to nothing.
            filled = max(1, filled)
        if filled:
            meter[0, :filled] = C_METER
