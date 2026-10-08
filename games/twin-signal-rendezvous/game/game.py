"""Twin Signal Rendezvous — walk two lanterns onto the same cell, one at a time.

Two lanterns (cyan, amber) stand on a 16x16 logical board rendered at 4
display pixels per cell (16 * 4 = 64, the whole canvas).  A white ring marks
exactly one of them; ACTION5 hops the ring to the other
(`manip.select_cycle`).  ACTION1-4 step the marked lantern one cell
(`move.grid`); a step into a wall or off-board leaves it exactly where it
was.  The level is banked the moment both anchors coincide
(`goal.rendezvous`): a yellow pulse blooms out of the shared cell and the
level ends.

From level 2 on, a red sentinel patrols a one-cell-wide corridor
(`agent.patrol`).  It is an autonomous mover carrying its own state — the
cell it stands on and the heading it is walking — and its own policy, which
is the whole of `patrol_step`: every step it walks one cell along its lane,
and when the next cell would leave the lane it reverses its heading and
walks the other way instead.  It runs that policy once per player action
whatever the player did, and it never reads the board, never sees a lantern,
never chases and never reacts: a lane, a heading and a reversal rule are all
the state it has.  Where it lands matters, though — if the **currently
marked** lantern is the thing under it when it lands, that lantern is
flattened and the run ends (`hazard.crush`).  An unmarked lantern is never
compared against it and is never touched, and that fixed rule is what makes
parking one lantern in a patrolled lane while fetching the other a plan
rather than a mistake (levels 3, 4, 6, 7).

Per-step resolution order, unchanged in every level:

  1. ACTION1-4 move the marked lantern (or are refused); ACTION5 hops the
     mark and moves nothing.
  2. every sentinel advances one cell under its own policy.
  3. crush check — the marked lantern only, against every sentinel's new cell.
  4. win check — both anchors equal.
  5. budget check — the win is banked first, so the winning move is free.

Geometry / reserved space (declared, not incidental):

- one grid orientation throughout: logical (x, y), x right, y down; cell
  (x, y) is painted at display rows 4y..4y+3, columns 4x..4x+3.  No flips.
- 64x64 camera, one scale (4 px/cell everywhere).  The game paints the whole
  canvas into a single full-canvas sprite at layer 0, so there is no
  declaration-order z anywhere: the paint order in `_paint` IS the layer
  order (board, pulse, sentinels, lanterns, meter).
- row 0 of the grid is the top chrome panel: a wall-coloured banner slab
  closed by one inert rule in index 2, drawn once per level load and never
  updated.  The floor never includes row 0.  On LEVEL 1 ONLY the banner
  boxes a two-frame reference icon — the lanterns apart, then the merged
  token on a margin of the goal index — so the finished win state is on
  screen before the first press.  It is inert: it never moves, never
  updates, and reads no state.
- x=0, x=15 and y=15 are the bezel that frames the play area; the playfield
  is the inset block x 1..14, y 1..14.
- display row 63 is the reserved budget strip (`hud.reserved: row63`): spent
  budget drains from the left in index 5, remaining budget is index 14.
  Neither index appears anywhere on the board.
- palette: 1 floor (the painted field) · 3 wall/bezel/panel · 0 selection
  ring, used for nothing else · 9 cyan lantern · 12 amber lantern ·
  8 crusher · 11 goal (the win bloom, and the level-1 reference icon's
  rendering of that same win state — nowhere else) · 2 the chrome rule,
  which never touches the playfield.

Deliberate deviations from the spec prose, each forced by another clause of
the same spec, and each flagged in the hand-off note:

- a lantern occupies ONE logical cell, not a 2x2 block of them.  The spec
  asks for 2x2 lanterns AND one-cell-wide corridors they must walk down;
  only one of those can be true on a 16x16 grid.  Cells win: the corridors
  are the puzzle.  The 2x2 silhouette survives as the 2x2-pixel core inside
  the selected lantern's white ring, and "anchor" and "footprint" coincide,
  so `goal.rendezvous` is unchanged (anchors equal == footprints equal).
- the crusher fills its whole cell instead of being a 2x1 bar: a hazard is
  load-bearing state and must be at least one full logical cell of paint.
- no telegraph outline is drawn.  `game.terms` is a closed set and does not
  declare `info.telegraph`; an outline marking a hazard's next cell is that
  term by definition, so it would be an undeclared mechanic.  The sentinel's
  next cell stays fully derivable — a patrol's heading is visible in the
  motion itself.
- contact is fatal, not a slide back to the level start.  `hazard.crush` is
  lethality-on-co-occupancy by definition ("a moving/displaced object
  occupying the avatar's cell is lethal"); a mover whose touch merely
  inconveniences you is a nuisance NPC and lands on a different id
  altogether, which `game.terms` does not declare.  So the sentinel kills and
  there is no knockback and no slide animation.
- there is no pass-time verb: no idle action, no declared idle, nothing the
  game offers whose purpose is to let the clock run.  A lantern held at a
  corridor mouth is held by pressing into the wall beside it, and the wall
  refuses the step exactly as `move.grid`'s passability test refuses every
  other blocked step — charged, silent, and leaving the lantern where it
  stood.  The planner uses that and nothing else to wait, because it has to:
  the tick a lantern can reach a cell on is otherwise pinned to that cell's
  grid parity, and a corridor whose safe beat falls on the other parity
  would be uncrossable rather than merely hard.
- a refused move is charged and draws nothing: "charge silently or signal
  freely, never both", and the budget's own declaration counts every
  UP/DOWN/LEFT/RIGHT step.
- level 1 is two rooms joined by one bent doorway, not a single open room, and
  its line runs about twenty actions rather than under ten.  A plain open room
  with the lanterns a handful of cells apart is closed by the pipeline's own
  undirected-random policy 12-20% of the time, which the spec's level-1
  anti-degenerate clause explicitly forbids; the doorway takes that to about
  0.1%, and it introduces nothing (walls are `move.grid`).  See `_level1`.

One honest limit of `goal.rendezvous` as specified: because winning only
needs the two anchors to coincide and lanterns do not block each other, one
lantern walking all the way onto its partner also wins, so the selection hop
is the cheap route rather than a strictly forced one.  Every authored layout
puts the partner behind a swept lane, so the handoff is what a player who
does not want to hold a marked lantern inside a corridor will reach for, and
it is the line the reference solver takes on every level.
"""

from __future__ import annotations

import copy
import hashlib
from functools import lru_cache
from math import gcd

import numpy as np
from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

GAME_ID = "twin-signal-rendezvous"
DEFAULT_LAYOUT_SEED = 4231          # EXACTLY the spec's layout.seed
LAYOUT_NAMESPACE = "twin-signal-rendezvous/layout/v1"
LEVEL_COUNT = 8

GRID = 16
CELL = 4                            # display pixels per logical cell
CANVAS = GRID * CELL                # 64
METER_ROW = CANVAS - 1              # hud.reserved: row63
PANEL_ROW = 0                       # top chrome panel (never floor)
XI0, XI1 = 1, 14                    # playfield x range, inside the bezel
YI0, YI1 = 1, 14                    # playfield y range, inside the bezel
CANVAS_SPRITE = "board"

C_FLOOR = 1                         # palette.background, the painted field
C_WALL = 3                          # walls, bezel, panel slab
C_RULE = 2                          # the chrome banner's rule — inert, off-board
C_RING = 0                          # palette.you — selection, nothing else
C_SENTINEL = 8                      # palette.danger
C_CYAN = 9                          # the spec's index for the cyan lantern
C_AMBER = 12
C_GOAL = 11                         # palette.goal — win bloom + panel icon
C_METER_LEFT = 14                   # budget remaining (off-board index)
C_METER_SPENT = 5                   # budget spent (off-board index)

LANTERN_COLORS = (C_CYAN, C_AMBER)
PULSE_RADIUS = 5                    # Manhattan radius of the win bloom

# The level-1 reference icon, in display pixels inside the top chrome panel.
# Rows 1..2 of the canvas: below the banner's top edge, above its rule.
ICON_X = 2
ICON_TOP = 1
ICON_HEIGHT = 2
ICON_FRAME_GAP = 8                  # left edge of frame B, relative to frame A

MOVE_DELTAS = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}
MOVE_ORDER = (1, 2, 3, 4)
TOGGLE_ID = 5
AVAILABLE_ACTIONS = [1, 2, 3, 4, 5]  # ACTION6/ACTION7 absent, nothing tagged

MOVES = {
    GameAction.ACTION1: MOVE_DELTAS[1],
    GameAction.ACTION2: MOVE_DELTAS[2],
    GameAction.ACTION3: MOVE_DELTAS[3],
    GameAction.ACTION4: MOVE_DELTAS[4],
}
TOGGLE = GameAction.ACTION5

BUDGET_FACTOR = 15                  # cap >= max(30, 15 * optimal)
BUDGET_FLOOR = 30

# Independent redraws a level gets before a seed is given up on.  A draw is
# only ever shipped once the planner has verified a winning line through it,
# so the redraw loop is what makes "this seed has no winning line" unreachable
# rather than merely unlikely.  See _draw_level.
REDRAW_LIMIT = 64

# The planner explores at most this many distinct sentinel phases for the
# second leg of a plan; the lower-bound ordering means the first few already
# carry the good lines, and the bound keeps build_layout fast.
PLAN_PHASE_BUDGET = 64


# --------------------------------------------------------------------------
# the patrol — a sentinel's lane is (axis, fixed, lo, hi, start, direction)
# and its whole policy is patrol_step()
# --------------------------------------------------------------------------


def lane_cell(lane, pos):
    """The board cell a sentinel at `pos` on `lane` occupies."""
    return (lane[1], pos) if lane[0] == "v" else (pos, lane[1])


def patrol_step(lane, pos, direction):
    """One tick of a sentinel's OWN policy: walk on, reverse at an endpoint.

    This is the entire policy of every sentinel in the game, and the only
    thing any of them ever consults: its own lane, its own cell, its own
    heading.  Walk one cell the way you are facing; if that cell is off the
    end of your lane, turn around and walk the other way instead.  A lane
    one cell long has nowhere to walk, so the sentinel holds it.

    Nothing about the board, the lanterns or the player's action enters
    here — the patrol is autonomous, not reactive.
    """
    _axis, _fixed, lo, hi, _start, _dir0 = lane
    ahead = pos + direction
    if ahead < lo or ahead > hi:
        direction = -direction
        ahead = pos + direction
        if ahead < lo or ahead > hi:
            ahead = pos
    return ahead, direction


def patrol_start(lane):
    """The cell and heading a sentinel opens its level on."""
    return lane[4], lane[5]


@lru_cache(maxsize=256)
def patrol_track(lane):
    """Every cell one sentinel's policy walks, in order, over its full period.

    Run `patrol_step` from the lane's declared start and record where the
    sentinel stands after 0, 1, 2, ... ticks.  A ping-pong along a span of n
    repeats its cell sequence every 2(n-1) ticks, so that many entries
    describe the patrol forever: the planner below indexes this track instead
    of re-walking the policy inside its search, and the two agree by
    construction because the track IS the policy, run ahead of time.
    """
    span = lane[3] - lane[2] + 1
    period = 2 * (span - 1) if span > 1 else 1
    pos, direction = patrol_start(lane)
    cells = []
    for _ in range(period):
        cells.append(lane_cell(lane, pos))
        pos, direction = patrol_step(lane, pos, direction)
    return tuple(cells)


def sentinel_cells_at(lanes, t):
    """Cells the sentinels stand on after their policies have run t times."""
    return {patrol_track(lane)[t % len(patrol_track(lane))] for lane in lanes}


def sentinel_timeline(lanes):
    """Occupied cells at tick t, for t in 0..P-1 (periodic in P)."""
    if not lanes:
        return (frozenset(),)
    period = 1
    for lane in lanes:
        step = len(patrol_track(lane))
        period = period * step // gcd(period, step)
    return tuple(frozenset(sentinel_cells_at(lanes, t)) for t in range(period))


def floor_cells(rects):
    cells = set()
    for x0, y0, x1, y1 in rects:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                cells.add((x, y))
    return cells


# --------------------------------------------------------------------------
# layout from seed (§7): pure, module-level, JSON-able
# --------------------------------------------------------------------------


def _digest(seed, index, attempt=0):
    """The draw bytes for one level of one seed, on its `attempt`-th redraw.

    Attempt 0 is the level's first draw.  Every later attempt is a fresh,
    independent draw of the SAME level shape from a differently-tagged
    digest, so a redraw moves every wall, every start and every patrol
    endpoint the builder derives — it is another draw of the level, never a
    nudge of the failed one.
    """
    tag = f"{LAYOUT_NAMESPACE}:{seed}:{index}"
    if attempt:
        tag = f"{tag}:redraw:{attempt}"
    return hashlib.sha256(tag.encode()).digest()


def _clip(value, low, high):
    return max(low, min(high, value))


def _level1(d):
    """Two rooms, one doorway, NO hazard: hand the mark over and finish the walk.

    The spec's own anti-degenerate clause for this level asks that "only a
    directed plan (not undirected wandering) reaches the overlap"; measured
    against the pipeline's `seeded_random` policy, a plain open room with the
    lanterns a handful of cells apart is closed by undirected wandering
    between 12% and 20% of the time, and no gap or cap inside the spec's
    "under ten actions" band gets that under 2%.  A doorway between the two
    starting rooms is the cheapest structure that honours the clause: it adds
    no mechanic (walls are `move.grid`'s passability, which this level is
    already meant to teach through the wall bump), leaves the level
    hazard-free and timing-free, and drops undirected wandering to a few
    tenths of a percent.
    """
    by = 6 + d[0] % 2
    entry = 3 + d[1] % 3
    exit_ = entry + 4 + d[2] % 3
    jog = by + 1 + d[3] % 2
    return {
        "name": "First Contact",
        "floor": [
            [XI0, YI0, XI1, by - 1],
            [entry, by, entry, jog],
            [entry, jog, exit_, jog],
            [exit_, jog, exit_, by + 3],
            [XI0, by + 4, XI1, YI1],
        ],
        "cyan": [entry - 2 + d[4] % 2, YI0 + d[5] % 2],
        "amber": [exit_ + 1 + d[6] % 3, YI1 - d[7] % 2],
        "lanes": [],
    }


def _level2(d):
    """Two regions, one corridor, one sentinel: time a crossing."""
    thick = 3 + d[0] % 2
    bx = 6 + d[1] % 2
    ly = 4 + d[2] % 8
    return {
        "name": "The Corridor",
        "floor": [
            [XI0, YI0, bx - 1, YI1],
            [bx, ly, bx + thick - 1, ly],
            [bx + thick, YI0, XI1, YI1],
        ],
        "cyan": [XI0 + d[3] % 2, _clip(ly + (3 if d[4] % 2 else -3), YI0, YI1)],
        "amber": [bx + thick + 1 + d[5] % 2, _clip(ly + (3 if d[6] % 2 else -3), YI0, YI1)],
        "lanes": [["h", ly, bx, bx + thick - 1, bx + d[7] % thick, 1 if d[8] % 2 else -1]],
    }


def _level3(d):
    """Asymmetric routes: one lantern's way crosses the lane, the other's does not."""
    thick = 5 + d[0] % 2
    by = 4 + d[1] % 2
    rx = 9 + d[2] % 2
    lx = 3 + d[3] % 4
    return {
        "name": "Park It",
        "floor": [
            [XI0, YI0, XI1, by - 1],
            [XI0, by + thick, XI1, YI1],
            [rx + 1, by, XI1, by + thick - 1],
            [lx, by, lx, by + thick - 1],
        ],
        "cyan": [XI0 + d[4] % 2, YI0 + d[5] % 2],
        "amber": [12 + d[6] % 3, 12 + d[7] % 3],
        "lanes": [["v", lx, by, by + thick - 1, by + d[8] % thick, 1 if d[9] % 2 else -1]],
    }


def _level4(d):
    """Two lanes in series into a shared room that no patrol reaches."""
    by = 3 + d[0] % 2
    ax = 3 + d[1] % 5
    cxr = 8 + d[2] % 2
    vx0 = cxr + 1
    bry = by + 4 + d[3] % 3
    return {
        "name": "Two Corridors",
        "floor": [
            [XI0, YI0, XI1, by - 1],
            [ax, by, ax, by + 2],
            [XI0, by + 3, cxr, YI1],
            [vx0, bry, vx0 + 2, bry],
            [vx0 + 3, by + 3, XI1, YI1],
        ],
        "cyan": [XI0 + d[4] % 3, YI0 + d[5] % (by - 1)],
        "amber": [vx0 + 3 + d[6] % 2, 12 + d[7] % 3],
        "lanes": [
            ["v", ax, by, by + 2, by + d[8] % 3, 1 if d[9] % 2 else -1],
            ["h", bry, vx0, vx0 + 2, vx0 + d[10] % 3, 1 if d[11] % 2 else -1],
        ],
    }


def _level5(d):
    """A chokepoint whose patrol is two cells wide: the window is one beat."""
    thick = 4
    bx = 9 + d[0] % 2
    ly = 4 + d[1] % 8
    p0 = bx + d[2] % 3
    return {
        "name": "The Narrow Window",
        "floor": [
            [XI0, YI0, bx - 1, YI1],
            [bx, ly, bx + thick - 1, ly],
            [bx + thick, YI0, XI1, YI1],
        ],
        "cyan": [XI0 + d[3] % 3, _clip(ly + (5 if d[4] % 2 else -5), YI0, YI1)],
        "amber": [min(XI1, bx + thick + d[5] % 2), _clip(ly + (4 if d[6] % 2 else -4), YI0, YI1)],
        "lanes": [["h", ly, p0, p0 + 1, p0 + d[7] % 2, 1 if d[8] % 2 else -1]],
    }


def _level6(d):
    """The patrol covers both mouths: no safe cell touches the corridor."""
    thick = 3 + d[0] % 2
    bx = 6 + d[1] % 2
    ly = 5 + d[2] % 6
    return {
        "name": "Meet In The Danger",
        "floor": [
            [XI0, YI0, bx - 1, YI1],
            [bx, ly, bx + thick - 1, ly],
            [bx + thick, YI0, XI1, YI1],
        ],
        "cyan": [XI0 + d[3] % 2, _clip(ly + (4 if d[4] % 2 else -4), YI0, YI1)],
        "amber": [XI1 - d[5] % 2, _clip(ly - (4 if d[4] % 2 else -4), YI0, YI1)],
        "lanes": [
            ["h", ly, bx - 1, bx + thick, bx - 1 + d[5] % (thick + 2), 1 if d[6] % 2 else -1]
        ],
    }


def _level7(d):
    """Two lanes whose patrols spill into the rooms; one alcove is clear of both."""
    by = 3 + d[0] % 2
    ax = 5 + d[1] % 3
    alx = 2 + d[2] % 2
    cxr = 8 + d[3] % 2
    vx0 = cxr + 1
    bry = by + 5 + d[4] % 2
    return {
        "name": "The Alcove",
        "floor": [
            [XI0, YI0, XI1, by - 1],
            [ax, by, ax, by + 2],
            [alx, by, alx, by + 1],
            [XI0, by + 3, cxr, YI1],
            [vx0, bry, vx0 + 2, bry],
            [vx0 + 3, by + 3, XI1, YI1],
        ],
        "cyan": [XI0 + d[5] % 2, YI0 + d[6] % (by - 1)],
        "amber": [vx0 + 3 + d[7] % 2, 12 + d[8] % 3],
        "lanes": [
            ["v", ax, by - 1, by + 3, by - 1 + d[9] % 5, 1 if d[10] % 2 else -1],
            ["h", bry, vx0 - 1, vx0 + 3, vx0 - 1 + d[11] % 5, 1 if d[12] % 2 else -1],
        ],
    }


def _level8(d):
    """Two patrols share one junction cell; their periods do not match."""
    hb0 = 4 + d[0] % 2
    ty = hb0 + 2
    jx = 6 + d[1] % 4
    bxl = jx - 3 + d[2] % 2
    return {
        "name": "Phase Lock",
        "floor": [
            [XI0, YI0, XI1, hb0 - 1],
            [XI0, ty, XI1, ty],
            [jx, hb0, jx, hb0 + 4],
            [XI0, hb0 + 5, XI1, YI1],
        ],
        "cyan": [XI0 + d[3] % 4, YI0 + d[4] % 2],
        "amber": [11 + d[5] % 4, hb0 + 7 + d[6] % 2],
        "lanes": [
            ["v", jx, hb0, hb0 + 4, hb0 + d[7] % 5, 1 if d[8] % 2 else -1],
            ["h", ty, bxl, bxl + 5, bxl + d[9] % 6, 1 if d[10] % 2 else -1],
        ],
    }


_LEVEL_BUILDERS = (_level1, _level2, _level3, _level4, _level5, _level6, _level7, _level8)


def build_layout(seed: int) -> list:
    """One JSON-able entry per level, a pure function of `seed`."""
    return copy.deepcopy(list(_layout_cached(int(seed))))


@lru_cache(maxsize=32)
def _layout_cached(seed: int) -> tuple:
    return tuple(_draw_level(seed, index) for index in range(LEVEL_COUNT))


def _draw_level(seed: int, index: int) -> dict:
    """One level's layout: draw it, and REJECT AND REDRAW an unwinnable draw.

    A seeded draw is only shipped once the planner has found and verified a
    winning line through it, so "this seed has no winning line" is not a
    state this function can return.  A draw the planner cannot solve — a
    corridor mouth that opens onto a pocket the other lantern cannot reach,
    a patrol whose phase seals its own lane, a start the walls have cut off —
    is discarded whole and the level is drawn again from an independently
    tagged digest, up to `REDRAW_LIMIT` times.  The draws are independent, so
    the chance of exhausting the limit is the per-draw reject rate raised to
    the limit; measured over 3000 seeds the per-draw rate is under 1/3000 on
    every level, and the loop has never gone past its first draw.
    """
    builder = _LEVEL_BUILDERS[index]
    for attempt in range(REDRAW_LIMIT):
        entry = builder(_digest(seed, index, attempt))
        entry["level"] = index + 1
        entry["draw"] = attempt
        plan = plan_level(entry)
        if plan is None:
            continue                # unwinnable draw: throw it away, draw again
        entry["plan"] = plan
        entry["cap"] = max(BUDGET_FLOOR, BUDGET_FACTOR * len(plan))
        return entry
    raise ValueError(
        f"level {index + 1}: {REDRAW_LIMIT} independent draws for seed {seed} "
        "were all unwinnable"
    )


# --------------------------------------------------------------------------
# the planner — the winning line is SEARCHED out of the layout
# --------------------------------------------------------------------------


def _hold_action(floor, cell):
    """A direction the wall refuses from `cell`, or None if every side is open.

    Holding position is not a verb of its own in this game — there is no idle
    action and no pass-time action, and none is declared.  What there is, is
    `move.grid`'s passability test: a step whose destination is a wall or off
    the board leaves the lantern exactly where it was.  The action is still
    charged and still advances the world, so pressing into a wall is how a
    player standing at a corridor mouth lets a patrol go by, and this returns
    the direction that does it from a given cell.  A cell with open floor on
    all four sides cannot refuse anything and so cannot be held on.
    """
    for action in MOVE_ORDER:
        dx, dy = MOVE_DELTAS[action]
        if (cell[0] + dx, cell[1] + dy) not in floor:
            return action
    return None


def _timed_bfs(floor, timeline, start, t0, blocked=frozenset()):
    """Earliest safe arrival time per (cell, crusher phase) for one lantern.

    Breadth-first over (cell, crusher phase).  Two kinds of edge, both of them
    an ordinary `move.grid` press that costs one action and advances every
    patrol by one tick: a step onto adjacent open floor, and a step into a
    wall, which the passability test refuses and which therefore leaves the
    lantern where it stands.  The second is what lets a route wait — and it
    has to exist, because without it the tick a lantern can reach a cell on is
    pinned to that cell's grid parity, and a corridor whose only safe beat
    falls on the other parity could not be crossed at all.  Either way the
    destination must be clear of every crusher once the clock has advanced.
    """
    period = len(timeline)
    src = (start, t0 % period)
    dist = {src: t0}
    parent = {src: None}
    frontier = [src]
    holds: dict = {}
    while frontier:
        nxt = []
        for node in frontier:
            cell, phase = node
            time = dist[node]
            nphase = (phase + 1) % period
            occupied = timeline[nphase]
            moves = [(action, MOVE_DELTAS[action]) for action in MOVE_ORDER]
            if cell not in holds:
                holds[cell] = _hold_action(floor, cell)
            if holds[cell] is not None:
                moves.append((holds[cell], (0, 0)))
            for action, (dx, dy) in moves:
                target = (cell[0] + dx, cell[1] + dy)
                if target not in floor:
                    continue
                if target in occupied or target in blocked:
                    continue
                step = (target, nphase)
                if step in dist:
                    continue
                dist[step] = time + 1
                parent[step] = (node, action)
                nxt.append(step)
        frontier = nxt
    return dist, parent


def _arrivals(dist, cell, period):
    """Every (cell, phase) node the search reached at `cell`, earliest first."""
    nodes = [(cell, phase) for phase in range(period) if (cell, phase) in dist]
    return sorted(nodes, key=lambda node: dist[node])


def _path_to(parent, node):
    actions = []
    while parent[node] is not None:
        node, action = parent[node]
        actions.append(action)
    actions.reverse()
    return actions


def _plain_bfs(floor, start):
    """Sentinel-blind step distance — the planner's lower bound."""
    dist = {start: 0}
    frontier = [start]
    while frontier:
        nxt = []
        for cell in frontier:
            for action in MOVE_ORDER:
                dx, dy = MOVE_DELTAS[action]
                target = (cell[0] + dx, cell[1] + dy)
                if target in floor and target not in dist:
                    dist[target] = dist[cell] + 1
                    nxt.append(target)
        frontier = nxt
    return dist


def _two_leg_plan(floor, timeline, homes, first, patrolled=frozenset()):
    """Walk one lantern to a meeting cell, hop the mark, walk the other to it.

    Among the meeting cells that tie for the shortest line, one that a
    sentinel walks over is preferred.  The lead lantern is unmarked for the
    whole of leg two, so it stands there while the patrol passes through it
    untouched: that is the standing rule of `hazard.crush` — only the marked
    lantern is ever compared against a sentinel — and picking such a cell
    when it costs nothing puts the rule in front of the player instead of
    leaving it to be taken on trust.
    """
    period = len(timeline)
    lead, rest = homes[first], homes[1 - first]
    prefix = [TOGGLE_ID] if first == 1 else []
    start_time = len(prefix)
    if start_time and lead in timeline[start_time % period]:
        return None

    dist, parent = _timed_bfs(floor, timeline, lead, start_time, blocked=frozenset({rest}))
    lower = _plain_bfs(floor, rest)
    # Every (cell, phase) the lead can stand on, not merely the earliest
    # arrival at each cell: the phase it arrives ON decides where the second
    # lantern can walk afterwards, so two arrivals at one meeting cell on
    # different beats are genuinely different candidates.
    candidates = sorted(
        (dist[node] + 1 + lower[node[0]], node)
        for node in dist
        if node[0] in lower
    )

    best = None
    legs = {}
    for bound, node in candidates:
        # `>` not `>=`: a candidate that only TIES the best length so far is
        # still worth costing out, because it may be the one on a patrol lane.
        if best is not None and bound > best[0]:
            break
        meet = node[0]
        arrival = dist[node]
        phase = (arrival + 1) % period
        if rest in timeline[phase]:
            # The hop itself would hand the mark to a lantern a sentinel is
            # standing on, and the crush check takes the marked one.
            continue
        if phase not in legs:
            if len(legs) >= PLAN_PHASE_BUDGET:
                continue
            legs[phase] = _timed_bfs(floor, timeline, rest, phase)
        dist2, parent2 = legs[phase]
        second = _arrivals(dist2, meet, period)
        if not second:
            continue
        total = arrival + 1 + (dist2[second[0]] - phase)
        rank = (total, 0 if meet in patrolled else 1)
        if best is None or rank < best[:2]:
            plan = (
                prefix
                + _path_to(parent, node)
                + [TOGGLE_ID]
                + _path_to(parent2, second[0])
            )
            best = (*rank, plan)
    return None if best is None else best[-1]


def _one_leg_plan(floor, timeline, homes, first):
    """The blunt line: walk one lantern the whole way onto its partner."""
    period = len(timeline)
    lead, rest = homes[first], homes[1 - first]
    prefix = [TOGGLE_ID] if first == 1 else []
    start_time = len(prefix)
    if start_time and lead in timeline[start_time % period]:
        return None
    dist, parent = _timed_bfs(floor, timeline, lead, start_time)
    arrivals = _arrivals(dist, rest, period)
    if not arrivals:
        return None
    return prefix + _path_to(parent, arrivals[0])


def simulate(entry, plan):
    """Replay a plan through the game's own rules; True iff it banks the level.

    The sentinels here are the same autonomous movers the game runs: live
    (cell, heading) state advanced one tick per action by `patrol_step`, in
    the same phase order `step()` uses.  Nothing is read off a table, so a
    plan that verifies here is a plan the game accepts.
    """
    floor = floor_cells(entry["floor"])
    patrols = [[tuple(lane), *patrol_start(tuple(lane))] for lane in entry["lanes"]]
    pos = [tuple(entry["cyan"]), tuple(entry["amber"])]
    selected = 0
    for action in plan:
        if action == TOGGLE_ID:
            selected = 1 - selected
        else:
            dx, dy = MOVE_DELTAS[action]
            target = (pos[selected][0] + dx, pos[selected][1] + dy)
            if target in floor:
                pos[selected] = target
        for patrol in patrols:
            patrol[1], patrol[2] = patrol_step(patrol[0], patrol[1], patrol[2])
        occupied = {lane_cell(lane, at) for lane, at, _dir in patrols}
        if pos[selected] in occupied:
            return False        # crushed: the run is over, the level is not won
        if pos[0] == pos[1]:
            return True
    return False


def plan_level(entry):
    """The shortest verified winning line for one level entry, or None.

    The handoff line (walk, hop the mark, walk) is preferred over the blunt
    one-lantern line even when the blunt line is shorter: it is the authored
    solution and the one that exercises `manip.select_cycle`.

    None means this DRAW is unwinnable, not that the seed is: the caller
    (`_draw_level`) rejects the draw and draws the level again.
    """
    lanes = [tuple(lane) for lane in entry["lanes"]]
    floor = floor_cells(entry["floor"])
    timeline = sentinel_timeline(lanes)
    homes = (tuple(entry["cyan"]), tuple(entry["amber"]))
    # Every cell any sentinel walks over — the cells where leaving an unmarked
    # lantern parked demonstrates that only the marked one is ever checked.
    patrolled = frozenset(cell for lane in lanes for cell in patrol_track(lane))

    two_leg = [_two_leg_plan(floor, timeline, homes, first, patrolled) for first in (0, 1)]
    one_leg = [_one_leg_plan(floor, timeline, homes, first) for first in (0, 1)]
    for group in (two_leg, one_leg):
        found = [plan for plan in group if plan is not None and simulate(entry, plan)]
        if found:
            # Shortest first; between equally short lines, the one that parks
            # an unmarked lantern where a sentinel walks.
            return min(found, key=lambda plan: (len(plan), 0 if _parks(entry, plan) else 1))
    return None


def _parks(entry, plan):
    """True iff the plan ever leaves the UNMARKED lantern under a sentinel.

    Replays the plan exactly as `simulate` does, but watches the lantern the
    mark is NOT on: if a sentinel walks onto that lantern's cell and the run
    carries on regardless, the plan has shown the player the rule that makes
    parking safe.
    """
    floor = floor_cells(entry["floor"])
    patrols = [[tuple(lane), *patrol_start(tuple(lane))] for lane in entry["lanes"]]
    pos = [tuple(entry["cyan"]), tuple(entry["amber"])]
    selected = 0
    for action in plan:
        if action == TOGGLE_ID:
            selected = 1 - selected
        else:
            dx, dy = MOVE_DELTAS[action]
            target = (pos[selected][0] + dx, pos[selected][1] + dy)
            if target in floor:
                pos[selected] = target
        for patrol in patrols:
            patrol[1], patrol[2] = patrol_step(patrol[0], patrol[1], patrol[2])
        occupied = {lane_cell(lane, at) for lane, at, _dir in patrols}
        if pos[selected] in occupied or pos[0] == pos[1]:
            return False
        if pos[1 - selected] in occupied:
            return True
    return False


# --------------------------------------------------------------------------
# painting helpers — one orientation, one scale
# --------------------------------------------------------------------------


def _fill_cell(buf, cell, color):
    x, y = cell
    buf[y * CELL:(y + 1) * CELL, x * CELL:(x + 1) * CELL] = color


def _fill_core(buf, cell, color):
    """The inner 2x2 pixels of a cell — a lantern's body inside its border."""
    x, y = cell
    buf[y * CELL + 1:y * CELL + CELL - 1, x * CELL + 1:x * CELL + CELL - 1] = color


def _outline_cell(buf, cell, color):
    x, y = cell
    px, py = x * CELL, y * CELL
    buf[py, px:px + CELL] = color
    buf[py + CELL - 1, px:px + CELL] = color
    buf[py:py + CELL, px] = color
    buf[py:py + CELL, px + CELL - 1] = color


def _merged_token(buf, cell):
    """The two lanterns sharing one cell: half cyan, half amber."""
    x, y = cell
    px, py = x * CELL, y * CELL
    buf[py:py + CELL, px:px + 2] = C_CYAN
    buf[py:py + CELL, px + 2:px + CELL] = C_AMBER


def _panel(buf):
    """The top chrome panel: a banner slab closed by one inert rule.

    The band that says where the board stops, drawn once per level load and
    never touched again.  On level 1 the banner boxes the reference icon
    below; on every other level it is bare slab.
    """
    buf[PANEL_ROW * CELL:(PANEL_ROW + 1) * CELL, :] = C_WALL
    buf[(PANEL_ROW + 1) * CELL - 1, :] = C_RULE


def _reference_icon(buf):
    """Two frames in the level-1 banner: the pair apart, then the pair merged.

    The worked example level 1 opens on.  Frame A is two lanterns standing on
    two cells; frame B is the same pair sharing one — the half-cyan/half-amber
    merged token the board itself draws on a win, sitting on a margin of the
    goal index, which is the only other place that index is ever used.  So
    what "both lanterns on one cell" looks like when it is finished is on
    screen before the player presses anything.

    It is chrome, and inert in every sense the chrome rule asks for: it never
    moves, never updates, reads no state, is drawn on level 1 only, and lives
    above the banner's rule in rows the playfield never reaches.  It is half a
    logical cell tall and sits off the cell lattice, so no part of it can be
    read as a lantern standing on the board.
    """
    top, bottom = ICON_TOP, ICON_TOP + ICON_HEIGHT
    x = ICON_X
    buf[top:bottom, x:x + 2] = C_CYAN                   # frame A — apart
    buf[top:bottom, x + 3:x + 5] = C_AMBER
    x += ICON_FRAME_GAP
    buf[top:bottom, x:x + 6] = C_GOAL                   # frame B — merged
    buf[top:bottom, x + 1:x + 3] = C_CYAN
    buf[top:bottom, x + 3:x + 5] = C_AMBER


def _static_board(cells, icon: bool = False):
    """Bezel, panel slab and playfield — everything that never moves."""
    buf = np.full((CANVAS, CANVAS), C_WALL, dtype=np.int8)
    for cell in cells:
        _fill_cell(buf, cell, C_FLOOR)
    _panel(buf)
    if icon:
        _reference_icon(buf)
    return buf


# --------------------------------------------------------------------------
# the game
# --------------------------------------------------------------------------


class TwinSignalRendezvous(ARCBaseGame):
    """Two lanterns, one selection ring, patrolled corridors in between."""

    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed
        self._layout = build_layout(seed)
        # Built before super().__init__(), which calls set_level(0) and so
        # reaches on_set_level() before any of its own state exists.
        self._floors = [floor_cells(entry["floor"]) for entry in self._layout]
        self._boards = [
            _static_board(cells, icon=(index == 0))
            for index, cells in enumerate(self._floors)
        ]
        self._entry = self._layout[0]
        self._cells = self._floors[0]
        self._board = self._boards[0]
        self._canvas: Sprite | None = None
        self._pos = [tuple(self._entry["cyan"]), tuple(self._entry["amber"])]
        self._selected = 0
        # One entry per sentinel: [lane, the cell index it stands on, heading].
        # This is the mover's whole state, and it is the only thing its policy
        # reads or writes.
        self._patrols: list[list] = []
        self._spent = 0
        super().__init__(
            game_id=GAME_ID,
            levels=[
                Level(
                    name=entry["name"],
                    sprites=[
                        Sprite(
                            pixels=self._boards[index].tolist(),
                            name=CANVAS_SPRITE,
                            layer=0,
                        )
                    ],
                )
                for index, entry in enumerate(self._layout)
            ],
            camera=Camera(width=CANVAS, height=CANVAS, background=C_FLOOR,
                          letter_box=C_FLOOR),
            available_actions=list(AVAILABLE_ACTIONS),
            seed=seed,
        )

    # ------------------------------------------------------------------
    # level lifecycle
    # ------------------------------------------------------------------

    def on_set_level(self, level: Level) -> None:
        index = self.level_index
        entry = self._layout[index]
        self._entry = entry
        self._cells = self._floors[index]
        self._board = self._boards[index]
        self._pos = [tuple(entry["cyan"]), tuple(entry["amber"])]
        self._selected = 0
        # Each sentinel is posted at its lane's declared cell and heading;
        # from here on it walks its own policy and nothing else.
        self._patrols = [
            [tuple(lane), *patrol_start(tuple(lane))] for lane in entry["lanes"]
        ]
        self._spent = 0
        # full_reset() re-clones every level, so the sprite object changes.
        found = level.get_sprites_by_name(CANVAS_SPRITE)
        self._canvas = found[0] if found else None
        self._paint()

    # ------------------------------------------------------------------
    # game logic
    # ------------------------------------------------------------------

    def step(self) -> None:
        action = self.action.id

        if action == GameAction.RESET:
            # handle_reset() already rebuilt the level through on_set_level().
            self.complete_action()
            return

        if action is not TOGGLE and action not in MOVES:
            # Nothing else is declared; an undeclared action must still
            # complete, and must change nothing.
            self.complete_action()
            return

        self._spent += 1
        if action is TOGGLE:
            self._selected = 1 - self._selected
        else:
            dx, dy = MOVES[action]
            x, y = self._pos[self._selected]
            if (x + dx, y + dy) in self._cells:
                self._pos[self._selected] = (x + dx, y + dy)

        # Phase 2: every sentinel now takes its own step, whatever the player
        # did and wherever the lanterns are.
        self._advance_patrols()

        if self._pos[self._selected] in self._sentinel_cells():
            # A sentinel came down on the marked lantern: the run is over.
            # An UNMARKED lantern sharing a sentinel's cell is never compared
            # here and is never touched — that is the standing rule parking
            # a lantern in a lane relies on.
            self._paint(crushed=self._selected)
            self.lose()
            self.complete_action()
            return

        if self._pos[0] == self._pos[1]:
            self._paint(pulse=self._pos[0])
            self.next_level()
            self.complete_action()
            return

        self._paint()
        self._check_budget()
        self.complete_action()

    def _check_budget(self) -> None:
        if self._spent >= self._entry["cap"]:
            self.lose()

    def _advance_patrols(self) -> None:
        """Run every sentinel's own policy for one tick."""
        for patrol in self._patrols:
            lane, pos, direction = patrol
            patrol[1], patrol[2] = patrol_step(lane, pos, direction)

    def _sentinel_cells(self) -> set[tuple[int, int]]:
        """Where the sentinels are standing right now."""
        return {lane_cell(lane, pos) for lane, pos, _direction in self._patrols}

    # ------------------------------------------------------------------
    # rendering — one full-canvas sprite; paint order IS the layer order
    # ------------------------------------------------------------------

    def _paint(self, pulse=None, crushed=None) -> None:
        if self._canvas is None:
            return
        buf = self._board.copy()

        if pulse is not None:
            self._paint_pulse(buf, pulse)

        sentinels = self._sentinel_cells()
        for cell in sentinels:
            _fill_cell(buf, cell, C_SENTINEL)

        if pulse is not None:
            # Both anchors coincide: one merged token, half cyan half amber,
            # standing in the bloom where the two lanterns used to be two.
            _merged_token(buf, pulse)
        else:
            for index in (0, 1):
                if index == crushed:
                    # Flattened: the crusher's own cell is all that is left
                    # where this lantern stood.
                    continue
                cell = self._pos[index]
                if index == self._selected:
                    _outline_cell(buf, cell, C_RING)
                elif cell not in sentinels:
                    _fill_cell(buf, cell, LANTERN_COLORS[index])
                _fill_core(buf, cell, LANTERN_COLORS[index])

        cap = self._entry["cap"]
        used = min(self._spent, cap) * CANVAS // cap
        buf[METER_ROW, :used] = C_METER_SPENT
        buf[METER_ROW, used:] = C_METER_LEFT

        self._canvas.pixels = buf

    @staticmethod
    def _paint_pulse(buf, center) -> None:
        cx, cy = center
        for y in range(YI0, YI1 + 1):
            span = PULSE_RADIUS - abs(y - cy)
            if span < 0:
                continue
            for x in range(max(XI0, cx - span), min(XI1, cx + span) + 1):
                _fill_cell(buf, (x, y), C_GOAL)
