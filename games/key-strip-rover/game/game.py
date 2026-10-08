"""Key Strip Rover — drive a 2x2 rover onto coloured pads in the order the
key strip along the top edge spells out, then out through the gate the final
lock opens.

The whole player-facing surface is four mechanics and nothing else:

* ``move.grid``    — ACTION1..4 step the rover's 2x2 anchor one logical cell;
                     a step whose footprint would leave the walkable floor is
                     refused in place.
* ``goal.sequence``— a pad locks only when its hue equals the next unlit
                     swatch of ``rail_order``; any other pad contact is a
                     refusal (flash, free) and changes nothing.
* ``gate.remote``  — the gate segment sits in the far wall, nowhere near the
                     pads, in a colour held exclusively for it; it becomes
                     walkable floor on the step that lights the last swatch.
* ``goal.reach``   — the rover's footprint overlapping the exit strip wins.
* ``info.telegraph``— the key strip spells the whole order out from frame
                     one, and the gate's reserved colour names the aperture
                     long before it has any reason to open.

One refusal rule, and each of its two kinds sits wholly on one side of the
grammar: a pad contact that is not yet due SIGNALS (a flash held for exactly
one settled frame, cleared on the next action) and COSTS NOTHING; a step into
wall or closed gate is SILENT and costs its one step like any other.  Nothing
is ever both.  There is no hazard, no timer, no lives, no click surface.

Layout is a pure function of the seed (spec-v0.3 section 7): every wall,
distance, pad placement, gate column and per-level cap is derived from
``build_layout(seed)``.
"""

from __future__ import annotations

import hashlib
import heapq

import numpy as np
from arcengine import (
    ARCBaseGame,
    BlockingMode,
    Camera,
    GameAction,
    InteractionMode,
    Level,
    Sprite,
)

GAME_ID = "key-strip-rover"
DEFAULT_LAYOUT_SEED = 48217
LAYOUT_NAMESPACE = "key-strip-rover/layout/v1"
LEVEL_COUNT = 8

# --------------------------------------------------------------------------
# frame geometry — ONE orientation, (x, y) with y growing downward
# --------------------------------------------------------------------------
GRID = 16          # 16x16 logical cells, rendered at 4 px each => 64x64 exact
SWATCH_ROW = 0     # HUD: key-strip swatches, left to right in touch order
METER_ROW = 1      # HUD: budget strip, full board width, drains left to right
DIVIDER_ROW = 2    # chrome {kind: divider, where: top} — inert
BEZEL_ROW = 15     # chrome {kind: bezel, where: border} — inert
PLAY_TOP = 3       # first walkable row
PLAY_BOTTOM = 14   # last walkable row
ANCHOR_MIN_X = 1
ANCHOR_MAX_X = 13  # a 2x2 footprint at x=13 ends on column 14
ANCHOR_TOP = 3
ANCHOR_MAX_Y = 10  # gate occupies y+2/y+3 and the exit strip y+4 <= 14

# --------------------------------------------------------------------------
# palette — reserved [5, 2, 3, 4]; 0 stays the refusal/meter mark
#
# Every distinction the rules depend on gets its own FAMILY, never a
# neighbouring shade of one:
#   * floor (2) vs wall (4) — passability, the two structural greys;
#   * gate (12, orange) — held exclusively by the gate at every level and
#     never reused on a wall cell, a pad, the rover or the exit, so the
#     aperture reads against the grey wall line from frame one;
#   * pad hues — the seven indices left over once rover 9, exit 14, gate 12,
#     the greys 1-4 and background 5 are spoken for, so no pad can be read
#     as the rover, the exit, the gate, a wall or the floor;
#   * an unlit pad shows its hollow half in background 5, never in the
#     floor colour: a waiting socket must not read as plain floor.
# --------------------------------------------------------------------------
C_BG = 5       # background: behind the HUD rail, and an unlit pad's hollow
C_FLOOR = 2    # walkable floor
C_WALL = 4     # wall
C_GATE = 12    # gate segment while closed — this game's one reserved colour
C_CHROME = 1   # divider + bezel (inert chrome)
C_ROVER = 9    # you
C_EXIT = 14    # goal
C_FLASH = 0    # refusal mark (white), and the budget meter's remaining ink
PAD_HUES = (6, 7, 8, 10, 11, 13, 15)

BUDGET_FACTOR = 15
BUDGET_FLOOR = 30

UP, DOWN, LEFT, RIGHT = 1, 2, 3, 4
MOVES = (UP, DOWN, LEFT, RIGHT)
DELTAS = {UP: (0, -1), DOWN: (0, 1), LEFT: (-1, 0), RIGHT: (1, 0)}


# --------------------------------------------------------------------------
# deterministic draws — sha256 only (no random, no hash(), no clock)
# --------------------------------------------------------------------------


class _Draw:
    """A reproducible stream of small integers keyed by (seed, level, salt)."""

    def __init__(self, seed: int, index: int, salt: str) -> None:
        self._base = f"{LAYOUT_NAMESPACE}:{int(seed)}:{int(index)}:{salt}"
        self._step = 0

    def _word(self) -> int:
        digest = hashlib.sha256(f"{self._base}:{self._step}".encode()).digest()
        self._step += 1
        return digest[0] | (digest[1] << 8) | (digest[2] << 16)

    def below(self, bound: int) -> int:
        return self._word() % bound if bound > 1 else 0

    def between(self, low: int, high: int) -> int:
        """Inclusive range; a collapsed range yields its only value."""
        if high <= low:
            return low
        return low + self.below(high - low + 1)

    def pick(self, items):
        items = list(items)
        return items[self.below(len(items))]

    def shuffled(self, items) -> list:
        arr = list(items)
        for i in range(len(arr) - 1, 0, -1):
            j = self.below(i + 1)
            arr[i], arr[j] = arr[j], arr[i]
        return arr


# --------------------------------------------------------------------------
# anchor/floor helpers
# --------------------------------------------------------------------------


def _hrun(x_from: int, x_to: int, y: int) -> list:
    step = 1 if x_to >= x_from else -1
    return [(x, y) for x in range(x_from, x_to + step, step)]


def _vrun(x: int, y_from: int, y_to: int) -> list:
    step = 1 if y_to >= y_from else -1
    return [(x, y) for y in range(y_from, y_to + step, step)]


def _footprint(anchor) -> list:
    x, y = anchor
    return [(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)]


def _floor_cells(anchors) -> set:
    cells = set()
    for anchor in anchors:
        cells.update(_footprint(anchor))
    return cells


def _cheb(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _legal_anchors(passable: set) -> set:
    legal = set()
    for y in range(GRID - 1):
        for x in range(GRID - 1):
            if all(cell in passable for cell in _footprint((x, y))):
                legal.add((x, y))
    return legal


def _pad_region(legal: set, pad_anchor) -> set:
    """Anchors whose 2x2 footprint overlaps the pad's 2x2 footprint."""
    px, py = pad_anchor
    return {a for a in legal if abs(a[0] - px) <= 1 and abs(a[1] - py) <= 1}


# --------------------------------------------------------------------------
# route search — exact optimum over (pads locked so far, anchor)
# --------------------------------------------------------------------------


def _dijkstra(legal: set, starts: dict, stop: set):
    """Uniform-cost search from labelled sources; nodes in ``stop`` absorb.

    Absorbing the target set matters: the rover cannot walk THROUGH the due
    pad to reach a cheaper cell of it — the first overlap is the lock.
    """
    best = dict(starts)
    parent = {anchor: None for anchor in starts}
    queue = [(cost, anchor) for anchor, cost in sorted(starts.items())]
    heapq.heapify(queue)
    settled: dict = {}
    while queue:
        cost, anchor = heapq.heappop(queue)
        if anchor in settled:
            continue
        settled[anchor] = cost
        if anchor in stop:
            continue
        x, y = anchor
        for move in MOVES:
            dx, dy = DELTAS[move]
            step = (x + dx, y + dy)
            if step not in legal or step in settled:
                continue
            nxt = cost + 1
            if step not in best or nxt < best[step]:
                best[step] = nxt
                parent[step] = anchor
                heapq.heappush(queue, (nxt, step))
    return settled, parent


def _move_between(a, b) -> int:
    delta = (b[0] - a[0], b[1] - a[1])
    for move in MOVES:
        if DELTAS[move] == delta:
            return move
    raise ValueError(f"{a} -> {b} is not one grid step")


def plan_moves(entry: dict) -> list:
    """The shortest winning action line for one layout entry.

    Derived entirely from the entry's own geometry: no coordinate, corridor
    length or pad colour is assumed.  Returns a list of action ids.
    """
    floor = {tuple(cell) for cell in entry["floor"]}
    gate = {tuple(cell) for cell in entry["gate"]}
    goal = {tuple(cell) for cell in entry["exit"]}
    legal_closed = _legal_anchors(floor | goal)
    legal_open = _legal_anchors(floor | goal | gate)

    frontier = {tuple(entry["start"]): 0}
    legs = []
    for pad in entry["pads"]:
        region = _pad_region(legal_closed, tuple(pad["anchor"]))
        settled, parent = _dijkstra(legal_closed, frontier, region)
        reached = {a: settled[a] for a in region if a in settled}
        if not reached:
            return []
        legs.append(parent)
        frontier = reached

    exit_region = {a for a in legal_open if goal.intersection(_footprint(a))}
    settled, parent = _dijkstra(legal_open, frontier, exit_region)
    reached = {a: settled[a] for a in exit_region if a in settled}
    if not reached:
        return []
    legs.append(parent)

    node = min(sorted(reached), key=lambda a: reached[a])
    hops = []
    for parent in reversed(legs):
        while parent.get(node) is not None:
            previous = parent[node]
            hops.append((previous, node))
            node = previous
    hops.reverse()
    return [_move_between(a, b) for a, b in hops]


# --------------------------------------------------------------------------
# per-level structure generators
#
# Each returns (shape, anchors, start, pad_anchors_in_rail_order, gate_x,
# last_floor_anchor_row).  The gate then occupies rows ye+2 .. ye+1+depth at
# columns gate_x..gate_x+1 and the exit strip the row below it, where depth
# is whatever the geometry leaves spare (GATE_MAX_DEPTH at most) — the
# one-column aperture plus its committed descent is what keeps even the
# openest level out of reach of an undirected walk.
# --------------------------------------------------------------------------

GATE_MAX_DEPTH = 5


def _spine_pad_rows(draw: _Draw, count: int, low: int, high: int, start_y: int) -> list:
    """``count`` spine rows, pairwise >= 3 apart and clear of the start.

    Spacing >= 3 keeps every pad's contact region disjoint from every other
    pad's, so no single anchor can ever overlap two pads at once.
    """
    candidates = [y for y in range(low, high + 1) if abs(y - start_y) >= 2]
    for _ in range(32):
        chosen: list = []
        for row in draw.shuffled(candidates):
            if all(abs(row - other) >= 3 for other in chosen):
                chosen.append(row)
            if len(chosen) == count:
                return sorted(chosen)
    chosen = []
    for row in candidates:
        if all(abs(row - other) >= 3 for other in chosen):
            chosen.append(row)
    return sorted(chosen[:count])


def _branch(side: int, spine_x: int, row: int, depth: int) -> list:
    return _hrun(spine_x, spine_x + side * depth, row)


def _level_open_room(draw: _Draw):
    """One open rectangle, no branches, two pads.

    The two rail colours sit at opposite ends of the room and the gate
    column sits back on the FIRST pad's side, so winning needs a directed
    there-and-back-again walk: an undirected walk that happens to brush the
    pads in the right order still has the whole room to re-cross before the
    one-column aperture, which is what keeps the open shape out of reach of
    the brainless policies.
    """
    right = draw.between(12, 13)          # last anchor column of the room
    ye = draw.between(6, 7)               # last anchor row of the room
    anchors = [(x, y) for y in range(ANCHOR_TOP, ye + 1)
               for x in range(ANCHOR_MIN_X, right + 1)]

    west_first = draw.below(2) == 0
    top_first = draw.below(2) == 0
    near_x = ANCHOR_MIN_X if west_first else right
    far_x = right if west_first else ANCHOR_MIN_X
    near_y = ANCHOR_TOP if top_first else ye
    far_y = ye if top_first else ANCHOR_TOP

    pad_a = (near_x, near_y)
    pad_b = (far_x, far_y)
    reach = draw.between(3, 4)
    if west_first:
        gate_x = ANCHOR_MIN_X + draw.below(2)
        start = (ANCHOR_MIN_X + reach, ANCHOR_TOP)
    else:
        gate_x = right - draw.below(2)
        start = (right - reach, ANCHOR_TOP)
    return "open-room", anchors, start, [pad_a, pad_b], gate_x, ye


def _level_corridor_alcoves(draw: _Draw):
    spine_x = draw.between(6, 8)
    ye = draw.between(8, 9)
    junction_a = draw.between(4, 5)
    junction_b = junction_a + draw.between(4, 5)
    junction_b = min(junction_b, ye - 1)
    side_a = draw.pick((-1, 1))
    side_b = -side_a
    depth_a = draw.between(3, 3 + min(2, (spine_x - ANCHOR_MIN_X - 3) if side_a < 0
                                      else (ANCHOR_MAX_X - spine_x - 3)))
    depth_b = draw.between(3, 3 + min(2, (spine_x - ANCHOR_MIN_X - 3) if side_b < 0
                                      else (ANCHOR_MAX_X - spine_x - 3)))

    anchors = _vrun(spine_x, ANCHOR_TOP, ye)
    anchors += _branch(side_a, spine_x, junction_a, depth_a)
    anchors += _branch(side_b, spine_x, junction_b, depth_b)

    start = (spine_x, ANCHOR_TOP)
    spine_row = _spine_pad_rows(
        draw, 1, max(junction_a + 2, ANCHOR_TOP), ye, ANCHOR_TOP
    )[0]
    pad_a = (spine_x + side_a * depth_a, junction_a)
    pad_c = (spine_x + side_b * depth_b, junction_b)
    pads = [pad_a, (spine_x, spine_row), pad_c]
    return "corridor-alcoves", anchors, start, pads, spine_x, ye


def _level_one_branch(draw: _Draw):
    side = draw.pick((-1, 1))
    far = draw.between(6, 7)
    near = far - 3
    spine_x = (far + 1) if side < 0 else (ANCHOR_MAX_X - far)
    junction = draw.between(5, 6)
    ye = draw.between(junction + 2, 9)

    anchors = _vrun(spine_x, ANCHOR_TOP, ye)
    anchors += _branch(side, spine_x, junction, far)

    start = (spine_x, ANCHOR_TOP)
    spine_row = _spine_pad_rows(draw, 1, ANCHOR_TOP, ye, ANCHOR_TOP)[0]
    pads = [
        (spine_x, spine_row),
        (spine_x + side * near, junction),
        (spine_x + side * far, junction),
    ]
    return "one-branch", anchors, start, pads, spine_x, ye


def _level_two_branches(draw: _Draw):
    spine_x = 7
    far = 6
    near = 3
    junction_a = draw.between(3, 5)
    junction_b = min(junction_a + draw.between(3, 4), 8)
    ye = draw.between(junction_b + 1, 9)
    side_a = draw.pick((-1, 1))
    side_b = -side_a

    anchors = _vrun(spine_x, ANCHOR_TOP, ye)
    anchors += _branch(side_a, spine_x, junction_a, far)
    anchors += _branch(side_b, spine_x, junction_b, far)

    start = (spine_x, ANCHOR_TOP)
    pads = [
        (spine_x + side_a * near, junction_a),   # near, branch A
        (spine_x + side_b * near, junction_b),   # near, branch B
        (spine_x + side_a * far, junction_a),    # far, branch A
        (spine_x + side_b * far, junction_b),    # far, branch B
    ]
    return "two-branches", anchors, start, pads, spine_x, ye


def _level_winding(draw: _Draw):
    """One folded path, no branch and no dead end: each lane is entered at
    one end and left at the other, so the only decision is reading the rail
    before committing to the walk."""
    lanes = (3, 6, 9)
    west_a = draw.between(ANCHOR_MIN_X, ANCHOR_MIN_X + 1)
    east = draw.between(ANCHOR_MAX_X - 2, ANCHOR_MAX_X)
    west_b = draw.between(ANCHOR_MIN_X, ANCHOR_MIN_X + 1)
    gate_x = draw.between(ANCHOR_MAX_X - 1, ANCHOR_MAX_X)

    path = _hrun(west_a, east, lanes[0])
    path += _vrun(east, lanes[0] + 1, lanes[1])
    path += _hrun(east, west_b, lanes[1])[1:]
    path += _vrun(west_b, lanes[1] + 1, lanes[2])
    path += _hrun(west_b, gate_x, lanes[2])[1:]

    if draw.below(2):
        flip = ANCHOR_MIN_X + ANCHOR_MAX_X
        path = [(flip - x, y) for x, y in path]
        gate_x = flip - gate_x

    anchors = list(dict.fromkeys(path))
    start = path[0]
    pads = _pads_along_path(draw, path, 5)
    return "winding-line", anchors, start, pads, gate_x, lanes[2]


def _pads_along_path(draw: _Draw, path: list, count: int) -> list:
    """``count`` pads spaced along a non-branching path, in path order."""
    span = len(path)
    for slack in (3, 2, 1, 0):
        picks: list = []
        for index in range(count):
            base = 2 + (span - 2) * index // count
            base = min(span - 1, base + draw.below(slack + 1))
            anchor = path[base]
            if any(_cheb(anchor, other) < 3 for other in picks):
                continue
            if _cheb(anchor, path[0]) < 3:
                continue
            picks.append(anchor)
        if len(picks) == count:
            return picks
    # Deterministic fallback: walk the path and take every pad that fits.
    picks = []
    for anchor in path[2:]:
        if all(_cheb(anchor, other) >= 3 for other in picks) and \
                _cheb(anchor, path[0]) >= 3:
            picks.append(anchor)
        if len(picks) == count:
            break
    return picks


# Fallback touch orders (slot indices) when the search below comes up dry.
_L6_FALLBACK = {1: (3, 0, 2, 4, 1), 2: (0, 3, 1, 4, 2), 3: (1, 4, 2, 0, 3)}


def _out_of_order_sequence(draw: _Draw, slot_count: int, entry_slot: int) -> list:
    """A touch order whose physical slots are never walked in near-first
    greed: every consecutive call is at least two slots away, the first call
    is away from the slot the rover lands on, and the entry slot is last."""
    others = [slot for slot in range(slot_count) if slot != entry_slot]
    for _ in range(64):
        order = draw.shuffled(others) + [entry_slot]
        if abs(order[0] - entry_slot) < 2:
            continue
        if any(abs(order[i] - order[i + 1]) < 2 for i in range(len(order) - 1)):
            continue
        return order
    return list(_L6_FALLBACK[entry_slot])


def _level_out_of_order(draw: _Draw):
    slots = [ANCHOR_MIN_X + 3 * i for i in range(5)]   # 1, 4, 7, 10, 13
    corridor = draw.between(5, 7)
    ye = draw.between(corridor + 2, 9)
    entry_slot = draw.pick((1, 2, 3))
    entry_x = slots[entry_slot]

    anchors = _hrun(slots[0], slots[-1], corridor)
    anchors += _vrun(entry_x, ANCHOR_TOP, ye)
    anchors = list(dict.fromkeys(anchors))

    order = _out_of_order_sequence(draw, len(slots), entry_slot)
    pads = [(slots[slot], corridor) for slot in order]
    start = (entry_x, ANCHOR_TOP)
    return "out-of-order-line", anchors, start, pads, entry_x, ye


def _level_far_before_near(draw: _Draw):
    spine_x = 7
    far = 6
    near = 3
    junction_a = draw.between(3, 4)
    junction_b = junction_a + 4
    ye = 10
    side_a = draw.pick((-1, 1))
    side_b = -side_a

    anchors = _vrun(spine_x, ANCHOR_TOP, ye)
    anchors += _branch(side_a, spine_x, junction_a, far)
    anchors += _branch(side_b, spine_x, junction_b, far)

    start = (spine_x, ANCHOR_TOP)
    rows = _spine_pad_rows(draw, 2, ANCHOR_TOP, ye, ANCHOR_TOP)
    pads = [
        (spine_x, rows[0]),                      # spine 1
        (spine_x + side_b * near, junction_b),   # near, far branch
        (spine_x + side_a * far, junction_a),    # far, near branch
        (spine_x, rows[1]),                      # spine 2
        (spine_x + side_a * near, junction_a),   # near, near branch
        (spine_x + side_b * far, junction_b),    # far, far branch
    ]
    return "far-before-near", anchors, start, pads, spine_x, ye


def _level_branch_ring(draw: _Draw):
    spine_x = 7
    far = 6
    near = 3
    junction_a = draw.between(3, 4)
    junction_b = junction_a + 3
    ring_row = junction_b + 3
    ye = ring_row
    side_a = draw.pick((-1, 1))
    side_b = -side_a

    ring_x = spine_x + side_a * far
    anchors = _vrun(spine_x, ANCHOR_TOP, ye)
    anchors += _branch(side_a, spine_x, junction_a, far)
    anchors += _branch(side_b, spine_x, junction_b, far)
    anchors += _vrun(ring_x, junction_a, ring_row)
    anchors += _hrun(ring_x, spine_x, ring_row)
    anchors = list(dict.fromkeys(anchors))

    # The seventh pad rides the ring near its far corner, so the call that
    # asks for it is strictly cheaper around the ring than back via the
    # spine — the one direction of travel where the ring pays.
    ring_pad_x = ring_x - side_a * 2
    start = (spine_x, ANCHOR_TOP)
    rows = _spine_pad_rows(draw, 2, ANCHOR_TOP, ring_row - 1, ANCHOR_TOP)
    pads = [
        (spine_x, rows[0]),                      # spine 1
        (spine_x + side_b * near, junction_b),   # near, far branch
        (spine_x + side_a * far, junction_a),    # far, ring branch
        (spine_x, rows[1]),                      # spine 2
        (spine_x + side_a * near, junction_a),   # near, ring branch
        (ring_pad_x, ring_row),                  # ring pad
        (spine_x + side_b * far, junction_b),    # far, far branch
    ]
    return "branch-ring", anchors, start, pads, spine_x, ye


_GENERATORS = (
    _level_open_room,
    _level_corridor_alcoves,
    _level_one_branch,
    _level_two_branches,
    _level_winding,
    _level_out_of_order,
    _level_far_before_near,
    _level_branch_ring,
)


# --------------------------------------------------------------------------
# the section 7 surface: build_layout(seed) is module level, pure, JSON-able
# --------------------------------------------------------------------------


def build_layout(seed: int) -> list:
    seed = int(seed)
    layout = []
    for index in range(LEVEL_COUNT):
        draw = _Draw(seed, index, "structure")
        shape, anchors, start, pad_anchors, gate_x, ye = _GENERATORS[index](draw)
        hues = _Draw(seed, index, "hues").shuffled(PAD_HUES)[: len(pad_anchors)]

        floor = _floor_cells(anchors)
        depth = min(GATE_MAX_DEPTH, PLAY_BOTTOM - 2 - ye)
        gate = [(gate_x + dx, ye + 2 + row)
                for row in range(depth) for dx in (0, 1)]
        goal = [(gate_x, ye + 2 + depth), (gate_x + 1, ye + 2 + depth)]
        floor -= set(gate)
        floor -= set(goal)

        entry = {
            "level": index + 1,
            "shape": shape,
            "floor": sorted([x, y] for x, y in floor),
            "start": [start[0], start[1]],
            "pads": [{"color": hue, "anchor": [a[0], a[1]]}
                     for hue, a in zip(hues, pad_anchors)],
            "gate": [[x, y] for x, y in gate],
            "exit": [[x, y] for x, y in goal],
            "cap": BUDGET_FLOOR,
        }
        optimal = len(plan_moves(entry))
        entry["optimal"] = optimal
        entry["cap"] = max(BUDGET_FLOOR, BUDGET_FACTOR * optimal)
        layout.append(entry)
    return layout


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def _pixels(rows) -> np.ndarray:
    return np.array(rows, dtype=np.int8)


def _pad_pixels(hue: int, state: str) -> np.ndarray:
    """The hollow-that-fills idiom, in the pad's own hue throughout.

    A waiting pad is half its hue over a background-coloured hollow, so it
    can never be mistaken for the floor it sits on; a locked pad is solid;
    a refused touch brightens the hollow to the white refusal mark for
    exactly one settled frame.
    """
    if state == "locked":
        return _pixels([[hue, hue], [hue, hue]])
    hollow = C_FLASH if state == "flash" else C_BG
    return _pixels([[hue, hue], [hollow, hollow]])


def _swatch_pixels(hue: int, filled: bool) -> np.ndarray:
    return _pixels([[hue, hue]] if filled else [[hue, C_BG]])


def _meter_pixels(remaining: int, cap: int) -> np.ndarray:
    if remaining <= 0:
        lit = 0
    else:
        lit = max(1, min(GRID, -(-GRID * remaining // cap)))
    return _pixels([[C_FLASH] * lit + [-1] * (GRID - lit)])


def _gate_pixels(depth: int, is_open: bool) -> np.ndarray:
    shade = C_FLOOR if is_open else C_GATE
    return _pixels([[shade, shade] for _ in range(depth)])


def _rover_pixels() -> np.ndarray:
    return _pixels([[C_ROVER, C_ROVER], [C_ROVER, C_ROVER]])


def _blank_pad() -> np.ndarray:
    return _pixels([[-1, -1], [-1, -1]])


def _scenery(entry: dict) -> list:
    floor = {tuple(cell) for cell in entry["floor"]}
    gate = {tuple(cell) for cell in entry["gate"]}
    board = [[-1] * GRID for _ in range(GRID)]
    for y in range(PLAY_TOP, PLAY_BOTTOM + 1):
        for x in range(GRID):
            board[y][x] = C_FLOOR if (x, y) in floor else C_WALL
    for x, y in (tuple(cell) for cell in entry["exit"]):
        board[y][x] = C_EXIT
    for x, y in gate:
        board[y][x] = -1          # painted by the gate sprite instead

    chrome = [[-1] * GRID for _ in range(GRID)]
    for x in range(GRID):
        chrome[DIVIDER_ROW][x] = C_CHROME
        chrome[BEZEL_ROW][x] = C_CHROME
    for y in range(PLAY_TOP, BEZEL_ROW + 1):
        chrome[y][0] = C_CHROME
        chrome[y][GRID - 1] = C_CHROME

    inert = {
        "blocking": BlockingMode.NOT_BLOCKED,
        "interaction": InteractionMode.INTANGIBLE,
    }
    return [
        Sprite(pixels=board, name="floor_walls", x=0, y=0, layer=0, **inert),
        Sprite(pixels=chrome, name="chrome_frame", x=0, y=0, layer=1, **inert),
    ]


def _level_from(entry: dict) -> Level:
    inert = {
        "blocking": BlockingMode.NOT_BLOCKED,
        "interaction": InteractionMode.INTANGIBLE,
    }
    sprites = _scenery(entry)

    gate_cells = [tuple(cell) for cell in entry["gate"]]
    gate_x = min(x for x, _ in gate_cells)
    gate_y = min(y for _, y in gate_cells)
    sprites.append(Sprite(pixels=_gate_pixels(len(gate_cells) // 2, False),
                          name="gate", x=gate_x, y=gate_y, layer=2, **inert))

    pads = entry["pads"]
    for index, pad in enumerate(pads):
        anchor = pad["anchor"]
        sprites.append(Sprite(pixels=_pad_pixels(pad["color"], "unlocked"),
                              name=f"pad_{index}", x=anchor[0], y=anchor[1],
                              layer=2, **inert))

    strip_x = (GRID - 2 * len(pads)) // 2
    for index, pad in enumerate(pads):
        sprites.append(Sprite(pixels=_swatch_pixels(pad["color"], False),
                              name=f"swatch_{index}", x=strip_x + 2 * index,
                              y=SWATCH_ROW, layer=2, **inert))

    sprites.append(Sprite(pixels=_meter_pixels(entry["cap"], entry["cap"]),
                          name="meter", x=0, y=METER_ROW, layer=2, **inert))

    start = entry["start"]
    sprites.append(Sprite(pixels=_rover_pixels(), name="rover",
                          x=start[0], y=start[1], layer=3, **inert))

    # The refusal flash rides layer 4 — ABOVE the rover, deliberately. A pad
    # only ever flashes with the rover standing on it, and the rover's own
    # 2x2 footprint would otherwise cover the pad's 2x2 block completely and
    # swallow the signal before the settled frame. Blank (-1) when idle.
    sprites.append(Sprite(pixels=_blank_pad(), name="flash",
                          x=0, y=0, layer=4, **inert))

    return Level(sprites=sprites, grid_size=(GRID, GRID),
                 data={"index": entry["level"] - 1},
                 name=f"level-{entry['level']}")


# --------------------------------------------------------------------------
# the game
# --------------------------------------------------------------------------


class Game(ARCBaseGame):
    """Visit the pads in key-strip order, then drive out through the gate."""

    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed
        self._layout = build_layout(seed)
        super().__init__(
            game_id=GAME_ID,
            levels=[_level_from(entry) for entry in self._layout],
            camera=Camera(width=GRID, height=GRID,
                          background=C_BG, letter_box=C_BG),
            available_actions=[UP, DOWN, LEFT, RIGHT],
        )

    # -- per-level state -------------------------------------------------

    def on_set_level(self, level: Level) -> None:
        entry = self._layout[level.get_data("index")]
        self._entry = entry
        self._pads = entry["pads"]
        self._rail = [pad["color"] for pad in self._pads]
        self._locked = [False] * len(self._pads)
        self._progress = 0
        self._flash = None
        self._cap = entry["cap"]
        self._budget = entry["cap"]
        self._rover = (entry["start"][0], entry["start"][1])

        self._floor = {tuple(cell) for cell in entry["floor"]}
        self._gate_cells = {tuple(cell) for cell in entry["gate"]}
        self._exit_cells = {tuple(cell) for cell in entry["exit"]}
        self._legal_closed = _legal_anchors(self._floor | self._exit_cells)
        self._legal_open = _legal_anchors(
            self._floor | self._exit_cells | self._gate_cells
        )

        self._parts = {sprite.name: sprite for sprite in level.get_sprites()}
        self._repaint()

    # -- helpers ---------------------------------------------------------

    @property
    def _gate_open(self) -> bool:
        return self._progress >= len(self._rail)

    def _legal(self, anchor) -> bool:
        reachable = self._legal_open if self._gate_open else self._legal_closed
        return anchor in reachable

    def _pad_under(self, anchor):
        for index, pad in enumerate(self._pads):
            spot = pad["anchor"]
            if abs(anchor[0] - spot[0]) <= 1 and abs(anchor[1] - spot[1]) <= 1:
                return index
        return None

    def _on_exit(self, anchor) -> bool:
        return bool(self._exit_cells.intersection(_footprint(anchor)))

    def _repaint(self) -> None:
        self._parts["rover"].set_position(*self._rover)

        for index, pad in enumerate(self._pads):
            state = "locked" if self._locked[index] else "unlocked"
            self._parts[f"pad_{index}"].pixels = _pad_pixels(pad["color"], state)
            self._parts[f"swatch_{index}"].pixels = _swatch_pixels(
                pad["color"], self._locked[index]
            )

        flash = self._parts["flash"]
        if self._flash is None:
            flash.set_position(0, 0)
            flash.pixels = _blank_pad()
        else:
            pad = self._pads[self._flash]
            flash.set_position(*pad["anchor"])
            flash.pixels = _pad_pixels(pad["color"], "flash")

        self._parts["gate"].pixels = _gate_pixels(
            len(self._gate_cells) // 2, self._gate_open
        )
        self._parts["meter"].pixels = _meter_pixels(self._budget, self._cap)

    # -- the one handler -------------------------------------------------

    def _spend(self) -> None:
        """Charge one unit of the budget; exhaustion ends the attempt.

        Only ever reached on a step the player was NOT refused a signal
        for — see step() for the single refusal rule.
        """
        self._budget -= 1
        self._repaint()
        if self._budget <= 0:
            self.lose()

    def step(self) -> None:
        # One refusal rule, two refusal kinds, each wholly on one side of
        # the grammar: a pad contact that is not due SIGNALS (the flash
        # holds for exactly one settled frame, then clears on the next
        # action) and COSTS NOTHING; a step into wall or closed gate is
        # SILENT and costs its step like any other.  Nothing is ever both.
        self._flash = None
        delta = DELTAS.get(self.action.id.value) \
            if self.action.id != GameAction.RESET else None
        if delta is None:
            self._repaint()
            self.complete_action()
            return

        target = (self._rover[0] + delta[0], self._rover[1] + delta[1])
        if not self._legal(target):
            # Wall / closed-gate refusal: silent, charged.
            self._spend()
            self.complete_action()
            return

        self._rover = target
        charged = True
        index = self._pad_under(target)
        if index is not None:
            due = (not self._locked[index]
                   and self._progress < len(self._rail)
                   and self._pads[index]["color"] == self._rail[self._progress])
            if due:
                self._locked[index] = True
                self._progress += 1
            else:
                # Pad refusal: signals, free.
                self._flash = index
                charged = False

        if self._gate_open and self._on_exit(target):
            self._repaint()
            self.next_level()          # the winning move is free
            self.complete_action()
            return

        if charged:
            self._spend()
        else:
            self._repaint()
        self.complete_action()
