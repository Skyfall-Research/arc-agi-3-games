"""Convoy in the Fog.

A supply convoy patrols a rail network on its own.  The player never drives
it: it keeps the heading it has, it follows the rail it is on, and at a
turnout node it leaves by whichever branch that turnout's pointer is lying
on.  Two actions exist and nothing else does.

  ACTION5 - wait, letting the convoy take its next patrol step;
  ACTION6 - click a cell, which changes something only when that cell is a
            turnout node currently inside the convoy's halo, in which case
            that turnout's pointer swings to its other branch.

The clicked cell IS the turnout, so the control and the barrier are the same
object, and the convoy's route is delegated entirely: the player sets
pointers and the convoy's own policy does the rest.

The convoy is a container and its range is real freight.  Fuel is a pile of
drums, each drum an object that stands on a board cell, and a drum may stand
in only two kinds of place - on a pad, or in the convoy's bed.  No rail cell
of the network will hold one.  Every advance force-moves every drum riding
in the bed onto the convoy's new cell, so the only way a drum ever crosses
the network is as the convoy's cargo; rolling one cell burns the drum the
roll was made on, and pulling onto a pad lifts drums off that pad's pile
until the bed is full again.  How many drums are still aboard is the whole
of the convoy's range, and the level's finishing check reads it directly.

Fog covers the board except a small halo around the convoy: outside the halo
every rail cell, turnout and pad collapses to one flat fog tile - only the
home pad's ring stays drawn, so the destination is a fixed landmark while
everything else has to be remembered.  A turnout that is visible draws both of
the legs its rule names - a notch on its fixed trunk leg and a pointer running
out into the branch it routes that trunk into - and the convoy broadcasts the
next few cells of its own upcoming route onto the rail ahead of it, as far as
the halo reaches.  That broadcast is computed by the same routing policy that
then moves the convoy, so it always says what is about to happen, and swinging
a pointer re-aims it the instant the click lands.

A turnout node has one fixed trunk leg and two branch legs.  Entered from
the trunk the convoy leaves by the branch the pointer names; entered from
either branch it always leaves by the trunk, with no click involved.  A pad
with exactly one rail neighbour refuels the convoy and turns it around; a
stub with no pad on it strands it.

Each level hands the convoy a standing haul: a counter of circuits it has to
outlast.  Every time the convoy rolls back onto the home pad one circuit
comes off that counter, and the counter reaching zero is what wins the level
- the convoy has survived its whole duty.  The run ends when the load empties
or when the network can no longer put the convoy on a refuelling pad before
it does: that solvability test runs after every step and a configuration
that fails it is dead wherever the convoy happens to be standing.
"""

from __future__ import annotations

import copy
import hashlib
import random
from collections import deque

import numpy as np
from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

GAME_ID = "convoy-in-the-fog"
DEFAULT_LAYOUT_SEED = 20260924
LAYOUT_NAMESPACE = "convoy-in-the-fog/layout/v1"

LEVEL_COUNT = 8
GRID = 16
CELL = 4
CANVAS = GRID * CELL
HUD_ROW = CANVAS - 1

# One bed size for every level; only the geometry changes level to level.
FUEL_MAX = 22
# The halo is a fixed Chebyshev window around the convoy's current cell.
HALO = 2

# Palette.  0/2/3 are the structural roles (background, fog, rail); 9 is the
# convoy and 11 the pad ring, and there is no danger colour because nothing on
# the board is lethal.
VOID = 0
FOG = 2
TRACK = 3
REFUSAL = 6
# The freight: the drums riding in the convoy's bed and stacked on the pads.
DRUM = 8
CONVOY = 9
# The one meter colour, used nowhere on the board.
METER_LIT = 10
# The warm pad ring, worn by the home pad and by every turnaround pad alike.
PAD_RING = 11
# The turnout pointer, and the route mark the convoy's own policy broadcasts
# onto the cells it is about to roll through: one saturated hue, reused by
# nothing else, so a routing statement always reads as a routing statement.
POINTER = 12
# Structural framing: the notch that marks which leg of a turnout is its fixed
# trunk, so the pointer is readable as "trunk in, this branch out" rather than
# as a claim about a convoy arriving from anywhere else.
FRAME = 13
PAD_FILL = 14
# The cap on the end of a stub: the rail stops here and no click will change
# that, so it is drawn in an index no control on the board ever uses.
CAP_MARK = 15

# Rail cells live inside this box: row 15 is left clear so the fuel meter on
# pixel row 63 only ever paints over background.
X_MIN, X_MAX = 1, 14
Y_MIN, Y_MAX = 1, 13

# The movement lattice.  The convoy occupies one whole board cell and every
# move it ever makes is one of these four unit steps - no diagonal, no partial
# and no free coordinate - so its position is always a lattice cell.
_STEPS = ((0, -1), (0, 1), (-1, 0), (1, 0))

# The cell the blind cycling policies click when they aim at the screen's
# centre; no turnout is ever allowed to sit there.
CENTRE_CELL = (GRID // 2, GRID // 2)

# Per level: ring width range, ring height range, stub turnouts, turnaround
# turnouts, plain pads, circuits to outlast, and whether the two loops of a
# figure-eight share a corridor (which costs a turnout at each of its ends).
_RECIPES = (
    (7, 8, 4, 5, 2, 0, 1, 1, False),
    (8, 9, 5, 6, 2, 0, 1, 1, False),
    (9, 10, 5, 6, 2, 1, 1, 1, False),
    (10, 11, 6, 7, 2, 2, 1, 1, False),
    (10, 11, 7, 8, 1, 1, 1, 2, False),
    (11, 12, 7, 8, 2, 0, 2, 2, True),
    (11, 12, 8, 9, 1, 1, 1, 1, False),
    (11, 12, 8, 9, 1, 1, 2, 2, True),
)

# Candidate selection.  A level's shortest winning line must contain at least
# one click and run between _MIN_PLAN and _PLAN_LIMIT actions; _MIN_CLICKS is
# the click count worth searching FOR, and the search stops early once it has
# both that many clicks and _CANDIDATES valid candidates to choose the best of.
_MIN_CLICKS = (2, 2, 2, 2, 2, 3, 2, 3)
_MIN_PLAN = (18, 24, 26, 30, 44, 52, 34, 52)
_PLAN_LIMIT = 130
_CANDIDATES = 8
_RANDOM_STREAMS = 40
_MAX_NONCE = 400
_BFS_NODE_LIMIT = 400000
_POLICY_STEPS = 130


# ---------------------------------------------------------------------------
# layout from seed (pure, module level)
# ---------------------------------------------------------------------------


def _draw(seed: int, index: int, nonce: int, tag: str, lo: int, hi: int) -> int:
    """One seed-derived integer in [lo, hi]."""
    key = f"{LAYOUT_NAMESPACE}:{seed}:{index}:{nonce}:{tag}"
    digest = hashlib.sha256(key.encode()).digest()
    return lo + int.from_bytes(digest[:8], "big") % (hi - lo + 1)


def _ring_cells(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """The rectangle's perimeter as one cyclic list, clockwise from (x0, y0)."""
    cells: list[tuple[int, int]] = []
    for x in range(x0, x1):
        cells.append((x, y0))
    for y in range(y0, y1):
        cells.append((x1, y))
    for x in range(x1, x0, -1):
        cells.append((x, y1))
    for y in range(y1, y0, -1):
        cells.append((x0, y))
    return cells


def _candidate(seed: int, index: int, nonce: int) -> dict | None:
    """One geometrically valid network for this level, or None to try again."""
    w_lo, w_hi, h_lo, h_hi, n_stub, n_turn, n_pad, circuits, chorded = _RECIPES[index]
    n_columns = n_stub + n_turn + (1 if chorded else 0)

    width = _draw(seed, index, nonce, "w", w_lo, w_hi)
    height = _draw(seed, index, nonce, "h", h_lo, h_hi)
    if X_MAX - width < X_MIN or Y_MAX - height < Y_MIN:
        return None
    x0 = _draw(seed, index, nonce, "x0", X_MIN, X_MAX - width)
    y0 = _draw(seed, index, nonce, "y0", Y_MIN, Y_MAX - height)
    x1, y1 = x0 + width, y0 + height

    # Turnout columns: inside the corners, and never closer than two columns to
    # each other so no two spurs and no corridor ever touch.
    room = (width - 4) - 2 * (n_columns - 1)
    if room < 0:
        return None
    columns: list[int] = []
    cursor = x0 + 2
    for k in range(n_columns):
        extra = _draw(seed, index, nonce, f"col{k}", 0, room)
        room -= extra
        cursor += extra
        columns.append(cursor)
        cursor += 2

    spur_max = min(4, height - 2)
    if spur_max < 2:
        return None

    ring = _ring_cells(x0, y0, x1, y1)
    length = len(ring)

    # Which column carries which kind of turnout moves with the seed.
    kinds = ["cap"] * n_stub + ["turn"] * n_turn + (["chord"] if chorded else [])
    random.Random(f"{LAYOUT_NAMESPACE}:{seed}:{index}:{nonce}:kinds").shuffle(kinds)

    gates: list[dict] = []
    chord_column: int | None = None
    for k, (column, kind) in enumerate(zip(columns, kinds)):
        if kind == "chord":
            chord_column = column
            if (column, y0) == CENTRE_CELL or (column, y1) == CENTRE_CELL:
                return None
            for half, ring_index in (
                ("chordtop", column - x0),
                ("chordbot", width + height + (x1 - column)),
            ):
                gates.append(
                    {
                        "ring": ring_index,
                        "len": 0,
                        "kind": half,
                        "pointer": "A",
                        "facing": _draw(seed, index, nonce, f"face{k}{half}", 0, 1),
                    }
                )
            continue
        on_top = _draw(seed, index, nonce, f"edge{k}", 0, 1) == 0
        cell = (column, y0 if on_top else y1)
        if cell == CENTRE_CELL:
            return None
        ring_index = column - x0 if on_top else width + height + (x1 - column)
        gates.append(
            {
                "ring": ring_index,
                "len": _draw(seed, index, nonce, f"spur{k}", 2, spur_max),
                "kind": kind,
                # A stub turnout starts pointed down its own dead end; a
                # turnaround turnout starts pointed along the loop, so the
                # detour it offers has to be chosen deliberately.
                "pointer": "B" if kind == "cap" else "A",
                # Which of the node's two ring legs is the fixed trunk: the
                # turnout routes only when it is entered from that side, so
                # this decides which direction of travel it governs.
                "facing": _draw(seed, index, nonce, f"face{k}", 0, 1),
            }
        )

    # Home sits on the left edge, so the convoy's outbound direction always
    # runs up that edge and then along the top: turnouts are met in ring order.
    taken = {g["ring"] for g in gates}
    home = _draw(seed, index, nonce, "home", 2 * width + height, length - 1)
    if home in taken:
        return None
    taken.add(home)

    # Plain pads are spread around the ring; how far apart they leave the
    # longest unfuelled stretch is what decides whether a spur has to be used.
    pads: list[int] = []
    for k in range(n_pad):
        base = length * (k + 1) // (n_pad + 1)
        for attempt in range(9):
            jitter = _draw(seed, index, nonce, f"pad{k}:{attempt}", -3, 3)
            spot = (home + max(3, min(length - 3, base + jitter))) % length
            if spot not in taken:
                pads.append(spot)
                taken.add(spot)
                break
        else:
            return None

    return {
        "level": index + 1,
        "rect": [x0, y0, x1, y1],
        "home": home,
        "pads": sorted(pads),
        "gates": sorted(gates, key=lambda g: g["ring"]),
        "chord": chord_column,
        "survive_circuits": circuits,
        "fuel": FUEL_MAX,
    }


def _compile(entry: dict) -> dict:
    """Turn a layout entry into the network the rules are evaluated against."""
    x0, y0, x1, y1 = entry["rect"]
    width = x1 - x0
    ring = _ring_cells(x0, y0, x1, y1)
    length = len(ring)

    neigh: dict[tuple[int, int], list[tuple[int, int]]] = {}
    kind: dict[tuple[int, int], str] = {}
    for i, cell in enumerate(ring):
        neigh[cell] = [ring[(i - 1) % length], ring[(i + 1) % length]]
        kind[cell] = "rail"

    # Every turnout in one fixed order, so a bit index always means one node.
    nodes: list[dict] = sorted((dict(g) for g in entry["gates"]), key=lambda g: g["ring"])
    column = entry["chord"]

    pads: set[tuple[int, int]] = set()
    for i in entry["pads"]:
        pads.add(ring[i])
        kind[ring[i]] = "pad"
    home = ring[entry["home"]]
    pads.add(home)
    kind[home] = "home"

    gate_at: dict[
        tuple[int, int], tuple[int, tuple[int, int], tuple[int, int], tuple[int, int]]
    ] = {}
    gate_cell: list[tuple[int, int]] = []
    init_arms = 0
    corridor: list[tuple[int, int]] = []
    if column is not None:
        corridor = [(column, y) for y in range(y0 + 1, y1)]

    for gi, node in enumerate(nodes):
        ring_index = node["ring"]
        cell = ring[ring_index]
        # The trunk is one fixed ring leg of the node; the other ring leg is
        # branch A.  Which way round decides the direction of travel this
        # turnout governs, because a branch-side entry never consults it.
        back, ahead = (ring_index - 1) % length, (ring_index + 1) % length
        if node["facing"]:
            back, ahead = ahead, back
        trunk, leg_a = ring[back], ring[ahead]
        if node["kind"] == "chordtop":
            leg_b = corridor[0]
        elif node["kind"] == "chordbot":
            leg_b = corridor[-1]
        else:
            step = (0, 1) if ring_index < width else (0, -1)
            spur = [
                (cell[0] + step[0] * k, cell[1] + step[1] * k) for k in range(1, node["len"] + 1)
            ]
            leg_b = spur[0]
            chain = [cell] + spur
            for k, scell in enumerate(spur, start=1):
                links = [chain[k - 1]]
                if k < len(spur):
                    links.append(chain[k + 1])
                neigh[scell] = links
                kind[scell] = "rail"
            tail = spur[-1]
            if node["kind"] == "turn":
                pads.add(tail)
                kind[tail] = "pad"
            else:
                kind[tail] = "cap"
        neigh[cell] = [trunk, leg_a, leg_b]
        kind[cell] = "gate"
        gate_at[cell] = (gi, trunk, leg_a, leg_b)
        gate_cell.append(cell)
        # Bit set: the pointer lies on branch B.
        if node["pointer"] == "B":
            init_arms |= 1 << gi

    if corridor:
        # The corridor is the segment the two loops of a figure-eight share.
        # Its two ends are turnout nodes, so a convoy that runs the corridor
        # arrives at the far turnout from a branch leg and is put back onto
        # that turnout's trunk with no click of its own.
        chain = [(column, y0), *corridor, (column, y1)]
        for k, ccell in enumerate(corridor, start=1):
            neigh[ccell] = [chain[k - 1], chain[k + 1]]
            kind[ccell] = "rail"

    halo: dict[tuple[int, int], tuple[int, ...]] = {}
    for cell in neigh:
        halo[cell] = tuple(
            gi
            for gi, gcell in enumerate(gate_cell)
            if max(abs(gcell[0] - cell[0]), abs(gcell[1] - cell[1])) <= HALO
        )

    return {
        # The lattice the convoy moves on: every cell of the rail network and
        # nothing else.  A step onto any board cell outside this set collides.
        "track": frozenset(neigh),
        # Two memo tables for the two rules that get asked the same question
        # over and over: where one step out of a cell lands, and how far the
        # nearest reachable pad is from it.
        "moves": {},
        "oracle": {},
        "neigh": neigh,
        "kind": kind,
        "pads": frozenset(pads),
        "gate_at": gate_at,
        "gate_cell": gate_cell,
        "halo": halo,
        "home": home,
        "start_prev": ring[(entry["home"] - 1) % length],
        "init_arms": init_arms,
        "survive_circuits": entry["survive_circuits"],
        "fuel_max": entry["fuel"],
    }


def _grid_step(net: dict, cell: tuple[int, int], delta: tuple[int, int]):
    """One discrete one-cell move on the lattice, or None when it collides.

    The convoy's whole movement vocabulary.  A step offsets the convoy's cell
    by one unit delta and is refused - the convoy simply does not move - when
    the destination leaves the board or is not a rail cell: nothing off the
    rail network is enterable, so the rail IS the collision map.
    """
    dest = (cell[0] + delta[0], cell[1] + delta[1])
    if not (0 <= dest[0] < GRID and 0 <= dest[1] < GRID):
        return None
    if dest not in net["track"]:
        return None
    return dest


def _open_steps(net: dict, cell: tuple[int, int]) -> list[tuple[int, int]]:
    """Every one of the four unit steps that this cell does not collide on."""
    return [delta for delta in _STEPS if _grid_step(net, cell, delta) is not None]


def _patrol_next(net: dict, cur: tuple[int, int], prev: tuple[int, int], arms: int):
    """The convoy's own routing policy: the one grid step it patrols by next.

    No player input reaches this function.  The convoy holds a heading - the
    unit delta of its last move - and picks this move's delta by four standing
    rules before handing it to `_grid_step`: at a turnout entered from the
    trunk it aims at the branch the pointer names, at a turnout entered from a
    branch it aims back at the trunk, on plain rail it carries straight on and
    turns only where carrying straight on would collide, and at a
    single-neighbour pad it reverses.  A stub with no pad on it leaves every
    delta but the one it came in on colliding, so the policy has no move.
    """
    gate = net["gate_at"].get(cur)
    # The move depends on the cell, the heading it was entered with and - at a
    # turnout only - that turnout's own pointer bit, so the answer is memoised
    # against exactly those three things.
    key = (cur, prev, (arms >> gate[0]) & 1 if gate is not None else 0)
    memo = net["moves"]
    if key in memo:
        return memo[key]

    delta = (cur[0] - prev[0], cur[1] - prev[1])
    if gate is not None:
        gi, trunk, leg_a, leg_b = gate
        if prev == trunk:
            aim = leg_b if (arms >> gi) & 1 else leg_a
        else:
            aim = trunk
        nxt = _grid_step(net, cur, (aim[0] - cur[0], aim[1] - cur[1]))
    else:
        back = (-delta[0], -delta[1])
        forward = [d for d in _open_steps(net, cur) if d != back]
        if delta in forward:
            nxt = _grid_step(net, cur, delta)
        elif len(forward) == 1:
            # The rail turns a corner: carrying straight on would collide, and
            # exactly one other unit step does not.
            nxt = _grid_step(net, cur, forward[0])
        elif not forward and cur in net["pads"]:
            # A pad at the end of a spur: the convoy reverses its heading.
            nxt = _grid_step(net, cur, back)
        else:
            nxt = None
    memo[key] = nxt
    return nxt


def _steps_to_pad(net: dict, cur: tuple[int, int], prev: tuple[int, int], arms: int):
    """The fewest steps that can put the convoy on a refuelling pad.

    A forward sweep over every route in front of the convoy, taking into
    account every turnout the player could still swing along the way, out to
    the furthest a full bed could ever carry it.  None when no route reaches a
    pad at all.  The answer depends on nothing but the convoy's cell, heading
    and the pointers, so it is memoised on those three.
    """
    key = (cur, prev, arms)
    memo = net["oracle"]
    if key in memo:
        return memo[key]
    result: int | None = None
    frontier = [(cur, prev, arms)]
    seen = {(cur, prev, arms)}
    for depth in range(1, net["fuel_max"] + 1):
        following: list[tuple] = []
        for cell, back, bars in frontier:
            for click in (None, *net["halo"][cell]):
                swung = bars if click is None else bars ^ (1 << click)
                nxt = _patrol_next(net, cell, back, swung)
                if nxt is None:
                    continue
                if nxt in net["pads"]:
                    result = depth
                    break
                node = (nxt, cell, swung)
                if node in seen:
                    continue
                seen.add(node)
                following.append(node)
            if result is not None:
                break
        if result is not None or not following:
            break
        frontier = following
    memo[key] = result
    return result


def _reachable_pad(net: dict, state: tuple) -> bool:
    """Solvability oracle: can the convoy still be put on a refuelling pad?

    Every winning line ends on the home pad and every pad refuels, so a state
    whose nearest reachable pad is further away than the load still aboard can
    pay for is a state no play can win from: the configuration is dead
    wherever the convoy is standing.
    """
    cur, prev, fuel, _survive_left, arms, _departed = state
    if cur in net["pads"]:
        return True
    depth = _steps_to_pad(net, cur, prev, arms)
    return depth is not None and depth <= max(fuel, 0)


def _resolve(net: dict, state: tuple, click: int | None) -> tuple[tuple | None, str]:
    """One whole step: click, roll, burn, refuel, then win before loss."""
    cur, prev, fuel, survive_left, arms, departed = state
    if click is not None and click in net["halo"][cur]:
        arms ^= 1 << click
    nxt = _patrol_next(net, cur, prev, arms)
    if nxt is None:
        return None, "dead"
    prev, cur = cur, nxt
    fuel -= 1
    if cur in net["pads"]:
        fuel = net["fuel_max"]
    if cur != net["home"]:
        departed = True
    elif departed:
        # One circuit of the standing haul outlasted: it comes off the counter.
        survive_left = max(survive_left - 1, 0)
    nxt_state = (cur, prev, fuel, survive_left, arms, departed)
    # The haul counter EMPTYING is the win - the convoy has outlasted its whole
    # duty - and it is settled before the load and the dead-configuration
    # oracle can end the run, so the surviving move is always free.
    if survive_left == 0 and fuel > 0:
        return nxt_state, "win"
    if fuel <= 0:
        return nxt_state, "dead"
    return nxt_state, "on"


def _start_state(net: dict) -> tuple:
    """The opening state; the haul counter starts at the level's circuit duty."""
    return (
        net["home"],
        net["start_prev"],
        net["fuel_max"],
        net["survive_circuits"],
        net["init_arms"],
        False,
    )


def _plan(net: dict) -> list[int | None] | None:
    """The shortest winning line: one entry per action, None meaning no click."""
    start = _start_state(net)
    parent: dict[tuple, tuple | None] = {start: None}
    queue = deque([start])
    seen = 1
    while queue:
        state = queue.popleft()
        for click in (None, *net["halo"][state[0]]):
            nxt, outcome = _resolve(net, state, click)
            if outcome == "dead":
                continue
            if outcome == "win":
                line = [click]
                node = state
                while parent[node] is not None:
                    node, took = parent[node]
                    line.append(took)
                line.reverse()
                return line if len(line) <= _PLAN_LIMIT else None
            if nxt in parent:
                continue
            seen += 1
            if seen > _BFS_NODE_LIMIT:
                return None
            parent[nxt] = (state, click)
            queue.append(nxt)
    return None


def _policy_wins(net: dict, mode: tuple, steps: int = _POLICY_STEPS) -> bool:
    """Replay one brainless policy; True when it manages to finish the level.

    A policy that kills the convoy is restarted from the level's opening
    state and keeps spending its step allowance, because that is what a
    replay harness does: a level a blind policy finishes on its fourth lucky
    attempt is just as lost as one it finishes first time.
    """
    state = _start_state(net)
    rng = random.Random(f"{LAYOUT_NAMESPACE}/policy:{mode}")
    for tick in range(steps):
        click: int | None = None
        if mode[0] == "repeat" or (mode[0] == "alternate" and tick % 2 == mode[2]):
            click = mode[1]
        elif mode[0] == "random" and rng.random() < 0.5:
            # A uniform click anywhere on the board, exactly as the random
            # policy throws it: only the turnout cells can ever matter.
            cell = (rng.randrange(GRID), rng.randrange(GRID))
            gate = net["gate_at"].get(cell)
            click = None if gate is None else gate[0]
        if click is not None and click not in net["halo"][state[0]]:
            click = None
        nxt, outcome = _resolve(net, state, click)
        if outcome == "win":
            return True
        if outcome == "on" and not _reachable_pad(net, nxt):
            outcome = "dead"
        state = _start_state(net) if outcome == "dead" else nxt
    return False


def _brainless_policies(net: dict) -> list[tuple]:
    """Every fixed-cell and random policy the level has to survive.

    A click on any cell that is not a turnout can never change anything, so
    the fixed-cell family is covered exactly by repeating (or alternating) a
    click on each turnout plus the do-nothing line; the random family is
    sampled over many independent streams, since a level has to hold up
    against the luck of any one of them.
    """
    modes: list[tuple] = [("wait", 0, 0)]
    for gi in range(len(net["gate_cell"])):
        modes.append(("repeat", gi, 0))
        modes.append(("alternate", gi, 0))
        modes.append(("alternate", gi, 1))
    modes.extend(("random", k, 0) for k in range(_RANDOM_STREAMS))
    return modes


def _level_layout(seed: int, index: int) -> dict:
    """The best of the first few valid candidates for one level."""
    best: dict | None = None
    best_score = (-1, -1)
    found = 0
    for nonce in range(_MAX_NONCE):
        entry = _candidate(seed, index, nonce)
        if entry is None:
            continue
        net = _compile(entry)
        line = _plan(net)
        if line is None or not _MIN_PLAN[index] <= len(line) <= _PLAN_LIMIT:
            continue
        clicks = sum(1 for step in line if step is not None)
        if clicks < 1:
            continue
        if any(_policy_wins(net, mode) for mode in _brainless_policies(net)):
            continue
        found += 1
        score = (clicks, len(line))
        if score > best_score:
            best, best_score = entry, score
            best["optimal"] = len(line)
        if best_score[0] >= _MIN_CLICKS[index] and found >= _CANDIDATES:
            break
    if best is None:
        raise ValueError(f"no playable layout for level {index + 1} at seed {seed}")
    return best


_LAYOUT_CACHE: dict[int, list] = {}


def build_layout(seed: int) -> list:
    """One JSON-able entry per level, a pure function of the seed alone."""
    seed = int(seed)
    cached = _LAYOUT_CACHE.get(seed)
    if cached is None:
        cached = [_level_layout(seed, index) for index in range(LEVEL_COUNT)]
        _LAYOUT_CACHE[seed] = cached
    return copy.deepcopy(cached)


def solve_plan(entry: dict) -> list[tuple[str, int, int]]:
    """The winning line as replayable actions: a wait, or a click at (x, y)."""
    net = _compile(entry)
    line = _plan(net)
    if line is None:
        return []
    actions: list[tuple[str, int, int]] = []
    for step in line:
        if step is None:
            actions.append(("wait", 0, 0))
        else:
            gx, gy = net["gate_cell"][step]
            actions.append(("click", gx * CELL + CELL // 2, gy * CELL + CELL // 2))
    return actions


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

# A pad's warm ring: the border of the tile.  The home pad and every
# turnaround pad wear exactly this ring in exactly this colour, so which of
# the two a half-seen pad is cannot be read off its hue - only off how many
# rail legs touch it.
_PAD_RING_PIXELS = tuple(
    (row, col)
    for row in range(CELL)
    for col in range(CELL)
    if row in (0, CELL - 1) or col in (0, CELL - 1)
)
# A pad's own pile of drums: the stock a convoy pulling in loads its bed from.
_PILE = ((1, 1), (2, 2))
# The pointer arm: a wedge on the side of the branch the turnout is lying on.
_POINTER_ARM = {
    (0, -1): ((0, 1), (0, 2), (1, 1), (1, 2)),
    (0, 1): ((2, 1), (2, 2), (3, 1), (3, 2)),
    (-1, 0): ((1, 0), (1, 1), (2, 0), (2, 1)),
    (1, 0): ((1, 2), (1, 3), (2, 2), (2, 3)),
}
# The stem of the pointer: the middle of a turnout tile, so the pointer reads
# as one unbroken line running out of the node and into the chosen branch.
_POINTER_STEM = ((1, 1), (1, 2), (2, 1), (2, 2))
# The trunk notch: the tile edge on the turnout's fixed trunk leg.
_TRUNK_EDGE = {
    (0, -1): tuple((0, col) for col in range(CELL)),
    (0, 1): tuple((CELL - 1, col) for col in range(CELL)),
    (-1, 0): tuple((row, 0) for row in range(CELL)),
    (1, 0): tuple((row, CELL - 1) for row in range(CELL)),
}
# How many steps of the convoy's own upcoming route are broadcast ahead of it.
ROUTE_AHEAD = 6
# The route mark a broadcast rail cell wears.
_ROUTE_MARK = _POINTER_STEM
# The cap across the closed end of a stub.
_CAP_EDGE = {
    (0, -1): tuple((0, col) for col in range(CELL)),
    (0, 1): tuple((CELL - 1, col) for col in range(CELL)),
    (-1, 0): tuple((row, 0) for row in range(CELL)),
    (1, 0): tuple((row, CELL - 1) for row in range(CELL)),
}
# The convoy's open bed: the hold the carried drums ride in, and the offset of
# that hold inside the convoy's own token.  Nothing else on the board can hold
# a drum, so the bed is the only way freight ever travels.
_BED = (1, 1)
_BED_SIDE = 2
_BED_SLOTS = ((0, 0), (0, 1), (1, 0), (1, 1))
# The convoy's open tail: the cell edge BEHIND it is left clear, so the pad or
# rail the convoy is standing on always reads through, and which edge is open
# is the facing indicator - it swings to the other side of the token the moment
# a turnaround reverses the stored heading.
_TAIL = {
    (1, 0): tuple((row, 0) for row in range(CELL)),
    (-1, 0): tuple((row, CELL - 1) for row in range(CELL)),
    (0, 1): tuple((0, col) for col in range(CELL)),
    (0, -1): tuple((CELL - 1, col) for col in range(CELL)),
}


def _tile(colour: int) -> list[list[int]]:
    return [[colour] * CELL for _ in range(CELL)]


def _make_level(entry: dict) -> Level:
    board = Sprite(
        pixels=[[VOID] * CANVAS for _ in range(CANVAS)],
        name="board",
        x=0,
        y=0,
        layer=0,
    )
    convoy = Sprite(pixels=_tile(CONVOY), name="convoy", x=0, y=0, layer=1)
    # The carried load rides one layer above the container that transports it.
    cargo = Sprite(
        pixels=[[-1] * _BED_SIDE for _ in range(_BED_SIDE)],
        name="cargo",
        x=_BED[0],
        y=_BED[1],
        layer=2,
    )
    refusal = Sprite(pixels=_tile(-1), name="refusal", x=0, y=0, layer=3)
    meter = Sprite(
        pixels=[[VOID] * CANVAS],
        name="fuelmeter",
        x=0,
        y=HUD_ROW,
        layer=4,
    )
    return Level(
        name=f"convoy-{entry['level']}",
        sprites=[board, convoy, cargo, refusal, meter],
        grid_size=(CANVAS, CANVAS),
        data={"entry": copy.deepcopy(entry)},
    )


class ConvoyInTheFog(ARCBaseGame):
    """A convoy that patrols on its own; the player only ever swings turnouts."""

    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed
        self._layout = build_layout(seed)
        super().__init__(
            game_id=GAME_ID,
            levels=[_make_level(entry) for entry in self._layout],
            camera=Camera(width=CANVAS, height=CANVAS, background=VOID, letter_box=VOID),
            available_actions=[5, 6],
        )

    # -- level setup --------------------------------------------------------

    def on_set_level(self, level: Level) -> None:
        """Fresh level, or a RESET-restored one: convoy home with a full bed."""
        entry = level.get_data("entry")
        self._net = _compile(entry)
        self._cur = self._net["home"]
        self._prev = self._net["start_prev"]
        # The load: one entry per drum, each holding the board cell that drum
        # is standing on.  They start stacked on the home pad, which is where
        # the convoy is standing, so they start in the convoy's bed.
        self._cargo: list[dict[str, int]] = []
        self._load_drums_from_pad(self._cur)
        # One bit per turnout: which of its two branch legs the pointer names.
        self._arms = self._net["init_arms"]
        # The standing haul: the circuits this level's convoy has to outlast.
        self._survive_left = self._net["survive_circuits"]
        self._departed = False
        self._refused_at: tuple[int, int] | None = None
        self._repaint(level)

    # -- game logic ---------------------------------------------------------

    def step(self) -> None:
        action = self.action.id
        if action not in (GameAction.ACTION5, GameAction.ACTION6):
            self.complete_action()
            return

        clicked = self._clicked_cell() if action == GameAction.ACTION6 else None
        self._refused_at = None
        if clicked is not None:
            gate = self._net["gate_at"].get(clicked)
            if gate is not None and gate[0] in self._net["halo"][self._cur]:
                # The clicked cell IS the turnout: its pointer swings off the
                # branch it was naming and onto the other one.
                self._arms ^= 1 << gate[0]
            else:
                # Visible refusal: the step still burns a drum exactly as an
                # ACTION5 advance would.
                self._refused_at = clicked

        outcome = self._roll_one_cell()
        self._repaint(self.current_level)
        if outcome == "win":
            self.next_level()
        elif outcome == "dead":
            self.lose()
        self.complete_action()

    def _roll_one_cell(self) -> str:
        """The convoy takes its patrol step, hauling its load along with it.

        The step is one discrete unit move on the rail lattice - the convoy's
        cell offset by one of the four unit deltas, refused where it would
        collide - and then the same fixed order every time: carry the drums
        aboard onto the new cell, burn the drum the move was made on, top the
        bed back up if the new cell is a pad, count the circuit off the
        standing haul, then settle the haul counter before the load and the
        dead-configuration oracle can end the run.
        """
        net = self._net
        nxt = _patrol_next(net, self._cur, self._prev, self._arms)
        if nxt is None:
            # Every unit step out of this cell collides, so the convoy cannot
            # move at all: stranded on a capped stub, where it stands.
            return "dead"
        self._prev, self._cur = self._cur, nxt
        self._haul_cargo(self._cur)
        self._burn_one_drum()
        self._load_drums_from_pad(self._cur)
        if self._cur != net["home"]:
            self._departed = True
        elif self._departed:
            # One circuit of the standing haul outlasted: it comes off.
            self._survive_left = max(self._survive_left - 1, 0)
        if self._survive_left == 0 and self._cargo:
            return "win"
        if not self._cargo:
            return "dead"
        state = (
            self._cur,
            self._prev,
            len(self._cargo),
            self._survive_left,
            self._arms,
            self._departed,
        )
        if not _reachable_pad(net, state):
            # The solvability oracle: no route the drums still aboard can pay
            # for ends on a pad any more, so this configuration is dead.
            return "dead"
        return "on"

    # -- the carried load ---------------------------------------------------

    def _drum_may_rest(self, cell: tuple[int, int]) -> bool:
        """Where a drum is allowed to stand when it is not aboard.

        Only a pad.  Every plain rail cell, every turnout node and every stub
        of the network refuses a drum, which is why the convoy's bed is the
        only thing that can move one across the board.
        """
        return cell in self._net["pads"]

    def _haul_cargo(self, cell: tuple[int, int]) -> None:
        """Force-move every drum riding in the bed onto the convoy's new cell."""
        for drum in self._cargo:
            drum["x"], drum["y"] = cell

    def _burn_one_drum(self) -> None:
        """One cell of rail costs the convoy one drum out of its own bed."""
        if self._cargo:
            self._cargo.pop()

    def _load_drums_from_pad(self, cell: tuple[int, int]) -> None:
        """Lift drums off a pad's pile into the bed until the bed is full."""
        if not self._drum_may_rest(cell):
            return
        while len(self._cargo) < self._net["fuel_max"]:
            self._cargo.append({"x": cell[0], "y": cell[1]})

    def _drums_aboard(self) -> int:
        """How many drums are standing on the convoy's own cell right now."""
        return sum(1 for drum in self._cargo if (drum["x"], drum["y"]) == self._cur)

    def _clicked_cell(self) -> tuple[int, int] | None:
        """The logical cell under an ACTION6, read off the action's own data."""
        data = self.action.data or {}
        px, py = data.get("x"), data.get("y")
        if px is None or py is None:
            return None
        cx = min(max(int(px), 0), CANVAS - 1) // CELL
        cy = min(max(int(py), 0), CANVAS - 1) // CELL
        return (cx, cy)

    # -- rendering ----------------------------------------------------------

    def _broadcast_route(self) -> list[tuple[int, int]]:
        """The cells the convoy is about to roll through, in order.

        Read straight out of the convoy's own routing policy with the pointers
        as they stand this instant, so what is broadcast and what then happens
        are the same computation and cannot disagree.  Swinging a pointer moves
        the broadcast the moment the click lands, which is how a turnout says
        out loud which branch it is about to send the convoy down.
        """
        net = self._net
        route: list[tuple[int, int]] = []
        cur, prev = self._cur, self._prev
        for _ in range(ROUTE_AHEAD):
            nxt = _patrol_next(net, cur, prev, self._arms)
            if nxt is None:
                break
            route.append(nxt)
            prev, cur = cur, nxt
        return route

    def _repaint(self, level: Level) -> None:
        net = self._net
        board = level.get_sprites_by_name("board")[0]
        pixels = board.pixels
        pixels[:, :] = VOID
        cx, cy = self._cur
        home = net["home"]
        # The broadcast is clipped to the halo like everything else: the convoy
        # announces its upcoming route only as far as the fog lets it be seen.
        ahead = set(self._broadcast_route())
        for cell, role in net["kind"].items():
            left, top = cell[0] * CELL, cell[1] * CELL
            lit = max(abs(cell[0] - cx), abs(cell[1] - cy)) <= HALO
            if lit:
                tile = self._livery(cell, role)
                if role == "rail" and cell in ahead:
                    for row, col in _ROUTE_MARK:
                        tile[row][col] = POINTER
            elif cell == home:
                # The one fog exemption in the game: the home pad's ring stays
                # drawn wherever the convoy is, so the destination is a fixed
                # landmark while its surrounding rail fogs over like the rest.
                tile = _tile(FOG)
                for row, col in _PAD_RING_PIXELS:
                    tile[row][col] = PAD_RING
            else:
                # Everything else masks down to one flat fog tile.
                pixels[top : top + CELL, left : left + CELL] = FOG
                continue
            for row, line in enumerate(tile):
                for col, colour in enumerate(line):
                    pixels[top + row][left + col] = colour

        convoy = level.get_sprites_by_name("convoy")[0]
        convoy.set_position(cx * CELL, cy * CELL)
        convoy.pixels = _as_pixels(self._convoy_token())
        self._carry_load_with_convoy(level)

        refusal = level.get_sprites_by_name("refusal")[0]
        if self._refused_at is None:
            refusal.pixels = _as_pixels(_tile(-1))
        else:
            refusal.set_position(self._refused_at[0] * CELL, self._refused_at[1] * CELL)
            refusal.pixels = _as_pixels(_tile(REFUSAL))

        meter = level.get_sprites_by_name("fuelmeter")[0]
        lit_columns = len(self._cargo) * CANVAS // net["fuel_max"]
        meter.pixels = _as_pixels(
            [[METER_LIT if col < lit_columns else VOID for col in range(CANVAS)]]
        )

    def _carry_load_with_convoy(self, level: Level) -> None:
        """Draw the drums where the drums actually are: in the convoy's bed.

        The cargo sprite is re-anchored onto the convoy's own token, at the
        fixed bed offset, after every advance, and how much of the bed it
        fills is read off the drums whose own positions sit on the convoy's
        cell.  Because a drum may rest nowhere but a pad or the bed, that is
        the whole of the game's freight: the convoy is the only thing on the
        board that can carry one from one pad to the next.
        """
        convoy = level.get_sprites_by_name("convoy")[0]
        cargo = level.get_sprites_by_name("cargo")[0]
        cargo.set_position(convoy.x + _BED[0], convoy.y + _BED[1])
        capacity = len(_BED_SLOTS)
        aboard = -(-self._drums_aboard() * capacity // self._net["fuel_max"])
        bed = [[-1] * _BED_SIDE for _ in range(_BED_SIDE)]
        for row, col in _BED_SLOTS[: min(aboard, capacity)]:
            bed[row][col] = DRUM
        cargo.pixels = _as_pixels(bed)

    def _livery(self, cell: tuple[int, int], role: str) -> list[list[int]]:
        """One revealed cell's own true colours."""
        if role == "gate":
            # A turnout states its whole rule on its own tile: the notch marks
            # the fixed trunk leg it routes FROM, and the pointer runs from the
            # middle of the node out into the branch it routes TO.  Both legs
            # being drawn is what keeps the pointer from reading as a promise
            # about a convoy arriving off a branch - such a convoy rejoins the
            # notched leg, and the broadcast route on the cells around the node
            # shows exactly that whenever it is the convoy's actual next move.
            tile = _tile(TRACK)
            gi, trunk, leg_a, leg_b = self._net["gate_at"][cell]
            notch = (trunk[0] - cell[0], trunk[1] - cell[1])
            for row, col in _TRUNK_EDGE[notch]:
                tile[row][col] = FRAME
            chosen = leg_b if (self._arms >> gi) & 1 else leg_a
            heading = (chosen[0] - cell[0], chosen[1] - cell[1])
            for row, col in _POINTER_STEM + _POINTER_ARM[heading]:
                tile[row][col] = POINTER
            return tile
        if role in ("home", "pad"):
            tile = _tile(PAD_FILL)
            if len(self._net["neigh"][cell]) < 2 or cell == self._net["home"]:
                # The warm ring: worn by the home pad and by every turnaround
                # pad alike, so hue alone never says which of the two it is.
                for row, col in _PAD_RING_PIXELS:
                    tile[row][col] = PAD_RING
            for row, col in _PILE:
                tile[row][col] = DRUM
            return tile
        if role == "cap":
            # The rail simply stops: a cap across the closed end, in an index
            # no control on this board uses, so it never reads as a turnout.
            tile = _tile(TRACK)
            back = self._net["neigh"][cell][0]
            away = (cell[0] - back[0], cell[1] - back[1])
            for row, col in _CAP_EDGE[away]:
                tile[row][col] = CAP_MARK
            return tile
        return _tile(TRACK)

    def _convoy_token(self) -> list[list[int]]:
        """The convoy: an open bed for the load it carries, and an open tail."""
        tile = _tile(CONVOY)
        for row in range(_BED[1], _BED[1] + _BED_SIDE):
            for col in range(_BED[0], _BED[0] + _BED_SIDE):
                tile[row][col] = -1
        heading = (self._cur[0] - self._prev[0], self._cur[1] - self._prev[1])
        for row, col in _TAIL.get(heading, ()):
            tile[row][col] = -1
        return tile


def _as_pixels(rows: list[list[int]]) -> np.ndarray:
    return np.array(rows, dtype=np.int8)
