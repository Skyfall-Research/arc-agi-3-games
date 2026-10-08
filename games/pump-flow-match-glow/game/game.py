"""Pump Flow, Match the Glow — light a pipe network into one exact pattern.

Every term in spec §11 ``game.terms``, with the code that carries it:

``move.grid``        ACTION1-4 step the one mover a single lattice cell across
    pipe, gate and floor tiles.  A step into a wall does not move the mover: it
    still rewrites ``state.facing`` and still costs a beat, and it flashes the
    refused cell (``knobs.refusal: visible``).  ``FlowState.apply``.
``flow.pumped``      ACTION5 on a pump-capable tile floods that tile's whole
    connected pipe component with the pump's own flow colour in one frame,
    resetting every reached cell's countdown.  ``flood``.
``goal.pattern_match``  the win predicate: EVERY paintable pipe cell in the play
    field must equal the target's requirement for it — the listed flow colour
    for a listed cell, empty for every cell the panel does not list.  Lighting
    something the panel never asked for is a real failure.  ``FlowState._match``.
``state.wait``       every action advances the one global beat, so standing
    still is bought by tapping a direction into a wall; that is how a player
    (and ``search_line``) waits out a gate window.  ``bump_action``.
``budget.cap``       the pump-charge meter.  Only a SUCCESSFUL pump press
    spends a charge; a refused press is free, exactly as spec'd, so there is no
    mixed refusal semantics anywhere.  Exhaustion calls ``lose()`` — and the win
    check runs FIRST, so the winning press is always free.
``gate.phase``       one global beat counter; every valve and dual-role tile
    reads it through the same fixed 4-step loop: 2 beats closed, 1 beat
    telegraph, 1 beat open.  ``_phase``.
``hazard.timed``     an OPEN gate blocks a pulse trying to cross it, and drains
    whatever is already lit beyond it — each lit cell remembers the gates its
    own pulse crossed (``via``), so "beyond it" is exact.  ``FlowState.apply``
    step (2) and ``flood``.
``info.telegraph``   the beat before a valve opens it glows its rim in the
    danger hue (8) — a one-step warning, the only warning.  ``_paint_gates``.
``state.facing``     the mover's facing, set by every ACTION1-4 whether the move
    lands or is refused, drawn into the arrow glyph, and READ by discovery: the
    tile you are facing is the tile you learn.  ``FlowState._see``.
``info.hidden_geometry``  on the fogged levels every pipe and gate tile starts
    masked as a featureless ``-2`` stub; physics never cared, only your
    knowledge does.  ``_FOG_STUB`` + ``_read_fog``.
``terrain.dual_role``  a dual-role tile is a gate for conduction AND a pump for
    ACTION5, off the same clock: pump-capable while closed or telegraphing,
    refusing with a visible flash while open.  ``_pump_color``.
``info.deception``   the look-alike junctions.  A dual-role tile and an inert
    junction ship the identical 2x2 connector silhouette; the inert one's branch
    is permanently disconnected from every pump, so it can only ever sit empty.
    The ONLY honest tell is the purple (15) corner pulse that the real dual-role
    tile shows once discovered.  ``_paint_gates`` / ``_Plot.junction``.

Step resolution order, identical on every path (spec §Solver notes):
    (1) the global ``gate.phase`` beat advances by one
    (2) every already-lit cell's countdown decrements, and any cell whose pulse
        crossed a now-open gate drains to empty
    (3) the action resolves — move, refused move, pump, or refused pump
    (4) ``goal.pattern_match`` FIRST, then ``budget.cap`` exhaustion
A pulse fired on the beat a downstream valve flips open therefore still fails
to cross it.

Tiles.  The lattice is WALL by default; a level carves FLOOR (passable, inert,
never conducts — it is what keeps two pump components from ever merging) and
PIPE (passable, conducts, PAINTABLE and checked) through it, plus GATE tiles
(passable, conduct only while closed/telegraph, never paintable and never
checked — they are gates, not cells).  Pumps and look-alike junctions are pipe
cells drawn with the heavier 2x2 connector glyph; dual-role tiles are gates
drawn with that same glyph, which is the whole point of the deception.

Three places where this implementation resolves a spec the spec leaves in
tension, all documented rather than hidden:

* ``state.wait`` drain length.  §Global constants names 3, but every worked
  solution in the level sketches (L2's one-tile bridge, L3's P/Q pair, L7/L8's
  three-component races) needs a component to survive the walk between two
  pumps, which is 3+ beats and, for the three-component levels, far more.  A
  fixed 3 makes those levels unsolvable outright.  The countdown is therefore
  DERIVED from each level's own geometry (§7 requires exactly that of every
  other quantity): ``drain = max(3, span + 2)`` where ``span`` is the minimum
  beats between the first and last required press, measured by searching the
  level.  Level 1 and Level 5 land on the spec's literal 3.  The render grammar
  is unchanged and generalised: full saturation while the countdown is 2 or
  more, the shared dim tint (1) on its last beat, empty after.
* ``gate.phase`` telegraph is ONE beat (2 closed / 1 telegraph / 1 open), per
  §Global constants, and an open gate both blocks and drains, per §Level 4.
* Level 3's "press the deep pump FIRST" clause is not reachable under the
  spec's own win rule, and this level therefore does not claim it.  The rule
  checks the pattern after every step, so the only countdown that can ever bind
  two presses is the number of beats BETWEEN them — and with exactly two
  required pumps that is the shortest walk from one to the other, which is the
  same walk in either direction.  The sketch's arithmetic counts the walk INTO
  the deep branch, but that walk happens before the first press, so it is
  charged to no countdown at all.  No drain length separates the two orders,
  because their spans are equal, not merely close (measured over every order
  and every gate-window hold, at every seed).  Press order can only start to
  matter at THREE required pumps, where the span becomes a route and stops
  being symmetric — which is exactly where Levels 7 and 8 put it.  What Level 3
  does ship, and what is real: the contrasting hub-and-spokes geometry, the
  asymmetric branch depths (pump P at the buffer's edge, pump Q sunk ``depth``
  cells into its own spoke, so the race is genuinely longer than Level 2's),
  and the level's actual discipline test — the third spoke, a fully
  functional pump the reference panel never lists, which the exact-match rule
  turns from a harmless habit into a real, visible failure.  ``_level3``.

``layers: explicit`` — every sprite carries an explicit ``layer=``; nothing here
relies on declaration order.  ``hud.reserved: row63`` — canvas row 63 is the
pump-charge meter and nothing else, and the target panel owns the top-right
corner tiles; both paint after the board, and ``_playable`` keeps every
generator out of the panel's tiles and off lattice row 15 (the row canvas row 63
would overwrite), so neither HUD can ever hide live board state.  Both HUD masks
key on GEOMETRY, never on colour equality.

The one ``-2`` this game ships is ``_FOG_STUB``, the masked stub art for an
undiscovered pipe or gate tile, and its declared reader is ``_read_fog``, which
resolves every ``-2`` to the fog index (2) as the terrain layer is built.  The
mask is what erases the tile's true bend/junction shape — and, on a gate, its
phase tell — until the mover has stood on it or stood beside it facing it.  No
rendered frame carries a ``-2``.

Layout-from-seed (§7): ``build_layout(seed)`` is module-level, pure and
JSON-able.  The whole board is a function of the seed — a dihedral orientation
and a translation move every object and every distance between them, run and
branch lengths vary, pump and valve placement moves, gate phase offsets vary,
which junction is the real dual-role tile varies, flow colours vary, and every
level's derived ``drain`` and ``cap`` follow from the geometry that came out.
What holds invariant is the rule set and each level's relational structure.
"""

from __future__ import annotations

import functools
import hashlib
import json
from collections import deque
from itertools import permutations

import numpy as np
from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

GAME_ID = "pump-flow-match-glow"
DEFAULT_LAYOUT_SEED = 4177  # EXACTLY the spec's layout.seed
LAYOUT_NAMESPACE = "pump-flow-match-glow/layout/v1"
LEVEL_COUNT = 8

# --------------------------------------------------------------------------
# geometry — ONE orientation everywhere: a cell is (x, y) = (column, row)
# --------------------------------------------------------------------------

GRID = 16  # layout.grid = [16, 16]
CELL = 4  # rendered pixels per lattice cell -> 64x64 exactly

# hud.reserved: row63 — the pump-charge meter owns canvas row 63 alone, which
# is the bottom pixel row of lattice row 15; the play field stops at row 14.
METER_ROW = 63
PLAY_ROWS = GRID - 1

# The target panel owns the top-right corner tiles, spatially separate from the
# play field at all times (spec §Visual grammar).
PANEL_TILES = 4
PANEL_X0 = GRID - PANEL_TILES
PANEL_Y1 = PANEL_TILES - 1
PANEL_PX = PANEL_TILES * CELL
PANEL_SLOTS = 16  # 4x4 swatches of 2x2 px at pitch 3 inside the green ring

UP, DOWN, LEFT, RIGHT = 0, 1, 2, 3
DELTAS = ((0, -1), (0, 1), (-1, 0), (1, 0))
SPACE = 4  # ACTION5 — flow.pumped on a pump-capable tile, refused elsewhere

# gate.phase — the spec's fixed 4-step loop, identical on every gate tile.
GATE_PERIOD = 4
PHASE_TELEGRAPH = 2
PHASE_OPEN = 3

DRAIN_BASE = 3  # spec §Global constants: a fresh pulse's countdown
DRAIN_SLACK = 2  # beats of margin the derived countdown keeps over the span

# --------------------------------------------------------------------------
# palette — you=11, goal=14, danger=8, reserved [0, 1]
# --------------------------------------------------------------------------

C_BG = 0  # canvas background and letter-box; reserved, and nothing else uses it
C_DIM = 1  # the shared one-step dim-drain tint; reserved
C_FOG = 2  # fogged pipe or gate: the masked -2 stub resolves to this
C_PIPE = 3  # discovered but empty pipe
C_FLOOR = 4  # neutral floor — passable, inert, never carries colour
C_CUE = 5  # knobs.refusal: visible — the one-frame refusal rim, nothing else
C_METER = 13  # the pump-charge meter's fill; an index the BOARD never uses
C_DANGER = 8  # palette.danger — valve telegraph rim and open fill, nothing else
C_YOU = 11  # palette.you — the mover arrow, nothing else
C_GOAL = 14  # palette.goal — the reference panel's ring, nothing else
C_TELL = 15  # purple — the dual-role phase-pulse identity tell, nothing else

# Flow colours.  Purple (15) is deliberately NOT among them: the spec reserves
# it exclusively as the dual-role tell from Level 7 onward.
FLOW_COLORS = (9, 6, 12)

# layers: explicit values for every overlap that matters, never declaration z
LAYER_TERRAIN = 0
LAYER_GLOW = 10
LAYER_GATE = 15
LAYER_MOVER = 20
LAYER_CUE = 25  # above the mover: a refused SPACE rims the tile you stand on
LAYER_METER = 30
LAYER_PANEL = 40

# planner rails
PROBE_DRAIN = 999  # a countdown so long that pass 1 measures pure geometry
PROBE_CAP = 99
HOLD_MAX = 5  # beats the planner will stand on a pump waiting for its window
DRAW_ATTEMPTS = 24


class _Reject(Exception):
    """This draw cannot be placed; take the next attempt."""


# --------------------------------------------------------------------------
# seeded generation primitives — every draw descends from sha256(seed)
# --------------------------------------------------------------------------


class _Rng:
    """A deterministic byte stream namespaced by (seed, level, attempt)."""

    def __init__(self, seed: int, index: int, attempt: int) -> None:
        self._tag = f"{LAYOUT_NAMESPACE}:{int(seed)}:{index}:{attempt}"
        self._round = 0
        self._buf = hashlib.sha256(f"{self._tag}:0".encode()).digest()
        self._at = 0

    def byte(self) -> int:
        if self._at >= len(self._buf):
            self._round += 1
            self._buf = hashlib.sha256(
                f"{self._tag}:{self._round}".encode()
            ).digest()
            self._at = 0
        value = self._buf[self._at]
        self._at += 1
        return value

    def below(self, n: int) -> int:
        return self.byte() % max(1, n)

    def span(self, lo: int, hi: int) -> int:
        """An integer in [lo, hi], inclusive."""
        return lo + self.below(hi - lo + 1)

    def pick(self, seq):
        items = list(seq)
        return items[self.below(len(items))]

    def shuffled(self, seq) -> list:
        items = list(seq)
        for i in range(len(items) - 1, 0, -1):
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]
        return items


def _phase(offset: int, beat: int) -> int:
    """gate.phase: 0-1 closed, 2 telegraph (still safe), 3 open (hazard)."""
    return (beat + offset) % GATE_PERIOD


def _in_panel(cell) -> bool:
    x, y = cell
    return x >= PANEL_X0 and y <= PANEL_Y1


def _playable(cell) -> bool:
    """Inside the lattice, clear of the panel tiles and of meter row 15."""
    x, y = cell
    return 0 <= x < GRID and 0 <= y < PLAY_ROWS and not _in_panel(cell)


def _walk_line(origin, direction, count: int) -> list:
    """``count`` cells stepping from ``origin`` (exclusive) along ``direction``."""
    dx, dy = direction
    x, y = origin
    return [(x + dx * i, y + dy * i) for i in range(1, count + 1)]


# --------------------------------------------------------------------------
# the rules layer — pure functions over a prepared level config
# --------------------------------------------------------------------------


def flood(cfg: dict, source, beat: int, *, ignore_phase: bool = False) -> dict:
    """Every pipe cell one pulse from ``source`` reaches, and the gates it crossed.

    flow.pumped: conduction is 4-adjacency through pipe cells and through gate
    tiles that are currently closed or telegraphing.  An OPEN gate stops the
    pulse dead (hazard.timed).  Gate tiles are never painted themselves; each
    reached cell records the gates its own path crossed so a gate that opens
    later can drain exactly what lies beyond it, and nothing else.  The source
    tile is never counted as a gate on its own path.
    """
    paint = cfg["pipe"]
    gates = cfg["gates"]
    reached: dict = {}
    if source in paint:
        reached[source] = frozenset()
    seen = {source}
    queue = deque([(source, frozenset())])
    while queue:
        cell, via = queue.popleft()
        for dx, dy in DELTAS:
            nxt = (cell[0] + dx, cell[1] + dy)
            if nxt in seen:
                continue
            if nxt in paint:
                seen.add(nxt)
                reached[nxt] = via
                queue.append((nxt, via))
            elif nxt in gates:
                if not ignore_phase and _phase(gates[nxt][0], beat) == PHASE_OPEN:
                    continue
                seen.add(nxt)
                queue.append((nxt, via | frozenset({nxt})))
    return reached


def _pump_color(cfg: dict, cell, beat: int):
    """The flow colour ACTION5 would fire here, or None if the press is refused.

    terrain.dual_role: a plain pump always fires; a dual-role tile fires only
    while its own gate.phase is closed or telegraphing, and refuses while open.
    """
    if cell in cfg["pumps"]:
        return cfg["pumps"][cell]
    gate = cfg["gates"].get(cell)
    if gate is not None and gate[1] and _phase(gate[0], beat) != PHASE_OPEN:
        return gate[2]
    return None


def route(cfg: dict, start, goal):
    """The shortest walk between two tiles as a list of direction actions.

    Movement never reads gate.phase — a valve is walkable in every phase — so
    this is a plain breadth-first search over the traversable lattice.
    """
    if start == goal:
        return []
    walk = cfg["walk"]
    prev = {start: None}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        for action, (dx, dy) in enumerate(DELTAS):
            nxt = (cell[0] + dx, cell[1] + dy)
            if nxt not in walk or nxt in prev:
                continue
            prev[nxt] = (cell, action)
            if nxt == goal:
                return _unwind(prev, goal)
            queue.append(nxt)
    return None


def _unwind(prev: dict, goal) -> list:
    actions = []
    cell = goal
    while prev[cell] is not None:
        cell, action = prev[cell]
        actions.append(action)
    actions.reverse()
    return actions


def bump_action(cfg: dict, cell):
    """state.wait: a direction that is blocked here, so a beat passes in place."""
    for action, (dx, dy) in enumerate(DELTAS):
        if (cell[0] + dx, cell[1] + dy) not in cfg["walk"]:
            return action
    return None


def required_pumps(cfg: dict) -> list:
    """Pump-capable tiles whose reach touches a cell the panel wants lit.

    Anything else is a decoy: pressing it lights cells the panel never listed,
    which the exact-match rule turns into a real failure.
    """
    candidates = list(cfg["pumps"])
    candidates += [cell for cell, gate in cfg["gates"].items() if gate[1]]
    wanted = set(cfg["targets"])
    out = []
    for cell in sorted(candidates):
        if wanted & set(flood(cfg, cell, 0, ignore_phase=True)):
            out.append(cell)
    return out


class FlowState:
    """The whole rules engine for one level, independent of any rendering."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.pos = cfg["start"]
        self.facing = cfg["facing"]
        self.beat = 0
        self.charge = cfg["cap"]
        self.lit: dict = {}  # cell -> (colour, countdown, via)
        self.known = set(cfg["known"])
        self.presses: list = []
        self.won = False
        self.lost = False
        self._see()

    def clone(self) -> FlowState:
        twin = FlowState.__new__(FlowState)
        twin.cfg = self.cfg
        twin.pos = self.pos
        twin.facing = self.facing
        twin.beat = self.beat
        twin.charge = self.charge
        twin.lit = dict(self.lit)
        twin.known = set(self.known)
        twin.presses = list(self.presses)
        twin.won = self.won
        twin.lost = self.lost
        return twin

    def _see(self) -> None:
        """info.hidden_geometry + state.facing: stand on it, or face it."""
        self.known.add(self.pos)
        dx, dy = DELTAS[self.facing]
        self.known.add((self.pos[0] + dx, self.pos[1] + dy))

    def color_at(self, cell):
        record = self.lit.get(cell)
        return None if record is None else record[0]

    def wait_at(self, cell) -> int:
        record = self.lit.get(cell)
        return 0 if record is None else record[1]

    def apply(self, action: int) -> dict:
        """One step(), in the spec's resolution order."""
        cfg = self.cfg
        gates = cfg["gates"]

        # (1) gate.phase advances globally, before anything else.
        self.beat += 1

        # (2) state.wait decays, and hazard.timed drains past any open gate.
        surviving: dict = {}
        drained = []
        for cell, (color, wait, via) in self.lit.items():
            wait -= 1
            if any(_phase(gates[gate][0], self.beat) == PHASE_OPEN for gate in via):
                wait = 0
            if wait > 0:
                surviving[cell] = (color, wait, via)
            else:
                drained.append(cell)
        self.lit = surviving

        # (3) the action resolves.
        cue = None
        fired = False
        if action == SPACE:
            color = _pump_color(cfg, self.pos, self.beat)
            if color is None:
                cue = self.pos  # knobs.refusal: visible — and free of charge
            else:
                for cell, via in flood(cfg, self.pos, self.beat).items():
                    self.lit[cell] = (color, cfg["drain"], via)
                self.charge -= 1
                self.presses.append(self.beat)
                fired = True
        else:
            self.facing = action  # state.facing updates even on a blocked move
            dx, dy = DELTAS[action]
            target = (self.pos[0] + dx, self.pos[1] + dy)
            if target in cfg["walk"]:
                self.pos = target
            else:
                cue = target
        self._see()

        # (4) goal.pattern_match FIRST, then budget.cap exhaustion.
        self.won = self._match()
        if not self.won and self.charge <= 0:
            self.lost = True
        return {"cue": cue, "fired": fired, "drained": drained}

    def _match(self) -> bool:
        """goal.pattern_match, exactly: listed colour here, empty everywhere else."""
        targets = self.cfg["targets"]
        for cell in self.cfg["pipe"]:
            if self.color_at(cell) != targets.get(cell):
                return False
        return True


# --------------------------------------------------------------------------
# the planner — the same search the solver runs, derived from the layout
# --------------------------------------------------------------------------


def _search_order(cfg: dict, order, hold_max: int, collect: bool) -> list:
    """Every winning line that presses ``order`` in that sequence."""
    found: list = []

    def visit(depth: int, sim: FlowState, actions: list) -> None:
        if found and not collect:
            return
        pump = order[depth]
        legs = route(cfg, sim.pos, pump)
        if legs is None:
            return
        base = sim.clone()
        prefix = list(actions)
        for action in legs:
            base.apply(action)
            prefix.append(action)
            if base.lost:
                return
        bump = bump_action(cfg, pump)
        for hold in range(hold_max + 1):
            if found and not collect:
                return
            if hold and bump is None:
                break
            trial = base.clone()
            line = list(prefix)
            for _ in range(hold):
                trial.apply(bump)
                line.append(bump)
            if trial.lost:
                continue
            event = trial.apply(SPACE)
            line.append(SPACE)
            if not event["fired"] or trial.lost:
                continue
            if depth + 1 == len(order):
                if trial.won:
                    span = trial.presses[-1] - trial.presses[0]
                    found.append((span, line))
            else:
                visit(depth + 1, trial, line)

    visit(0, FlowState(cfg), [])
    return found


def search_line(cfg: dict, *, hold_max: int = HOLD_MAX, collect: bool = False):
    """Derive a winning action line for this level by searching its own board.

    The plan is a circulation ORDER over the pumps the panel actually needs,
    plus how long to stand on each one waiting for its gate.phase window.  No
    coordinate and no move is ever hardcoded: ``required_pumps`` reads the
    panel, ``route`` reads the lattice, and every candidate is proved by
    simulating the real rules before it is returned.  ``collect`` makes the
    search exhaustive and return the minimum-span line, which is what the
    layout calibration measures; otherwise the first winning line wins.
    """
    best = None
    for order in permutations(required_pumps(cfg)):
        for span, actions in _search_order(cfg, order, hold_max, collect):
            if best is None or (span, actions) < best:
                best = (span, actions)
            if not collect:
                break
        if best is not None and not collect:
            break
    if best is None:
        return None
    return {"span": best[0], "actions": best[1]}


# --------------------------------------------------------------------------
# layout generation — one canonical plot per level, then oriented and placed
# --------------------------------------------------------------------------


class _Plot:
    """A level under construction, in free (possibly negative) coordinates."""

    def __init__(self) -> None:
        self.floor: set = set()
        self.pipe: set = set()
        self.pumps: dict = {}
        self.gates: dict = {}  # cell -> (offset, dual, colour)
        self.junctions: set = set()
        self.targets: dict = {}
        self.parts: list = []  # every conducting component the design intends
        self.start = None
        self.look = None
        self.fog = False

    def add_floor(self, cells) -> None:
        self.floor.update(tuple(cell) for cell in cells)

    def add_pipe(self, cells) -> None:
        self.pipe.update(tuple(cell) for cell in cells)

    def pump(self, cell, color: int) -> None:
        cell = tuple(cell)
        self.pipe.add(cell)
        self.pumps[cell] = int(color)

    def junction(self, cell) -> None:
        """info.deception: inert pipe wearing the dual-role tile's silhouette."""
        cell = tuple(cell)
        self.pipe.add(cell)
        self.junctions.add(cell)

    def gate(self, cell, offset: int, *, dual: bool = False, color: int = -1) -> None:
        self.gates[tuple(cell)] = (offset % GATE_PERIOD, bool(dual), int(color))

    def part(self, cells) -> None:
        self.parts.append(frozenset(tuple(cell) for cell in cells))

    def want(self, cells, color: int) -> None:
        for cell in cells:
            self.targets[tuple(cell)] = int(color)

    def begin(self, start, look) -> None:
        self.start = tuple(start)
        self.look = tuple(look)


def _oriented(cell, mode: int, width: int, height: int):
    x, y = cell
    if mode & 4:
        x, y = y, x
        width, height = height, width
    if mode & 1:
        x = width - 1 - x
    if mode & 2:
        y = height - 1 - y
    return (x, y)


def _place(plot: _Plot, rng: _Rng) -> _Plot:
    """Normalise, apply one of 8 dihedral orientations, then translate.

    This is the §7 workhorse: it is what makes distinct seeds structurally
    distinct rather than merely recoloured — every object and every distance
    between objects lands somewhere else on the lattice.
    """
    cells = plot.floor | plot.pipe | set(plot.gates)
    min_x = min(x for x, _ in cells)
    min_y = min(y for _, y in cells)
    width = max(x for x, _ in cells) - min_x + 1
    height = max(y for _, y in cells) - min_y + 1
    mode = rng.below(8)
    base = {
        cell: _oriented((cell[0] - min_x, cell[1] - min_y), mode, width, height)
        for cell in cells
    }
    out_w, out_h = (height, width) if mode & 4 else (width, height)
    spots = []
    for off_x in range(GRID - out_w + 1):
        for off_y in range(PLAY_ROWS - out_h + 1):
            if all(
                _playable((bx + off_x, by + off_y)) for bx, by in base.values()
            ):
                spots.append((off_x, off_y))
    if not spots:
        raise _Reject
    off_x, off_y = spots[rng.below(len(spots))]

    def shift(cell):
        bx, by = base[tuple(cell)]
        return (bx + off_x, by + off_y)

    moved = _Plot()
    moved.fog = plot.fog
    moved.add_floor(shift(cell) for cell in plot.floor)
    moved.add_pipe(shift(cell) for cell in plot.pipe)
    moved.pumps = {shift(cell): color for cell, color in plot.pumps.items()}
    moved.gates = {shift(cell): gate for cell, gate in plot.gates.items()}
    moved.junctions = {shift(cell) for cell in plot.junctions}
    moved.targets = {shift(cell): color for cell, color in plot.targets.items()}
    moved.parts = [frozenset(shift(cell) for cell in part) for part in plot.parts]
    moved.begin(shift(plot.start), shift(plot.look))
    return moved


def _components(cells: set) -> set:
    """Connected components of the conducting lattice, as frozensets."""
    seen: set = set()
    out = set()
    for cell in sorted(cells):
        if cell in seen:
            continue
        group = {cell}
        queue = deque([cell])
        seen.add(cell)
        while queue:
            here = queue.popleft()
            for dx, dy in DELTAS:
                nxt = (here[0] + dx, here[1] + dy)
                if nxt in cells and nxt not in seen:
                    seen.add(nxt)
                    group.add(nxt)
                    queue.append(nxt)
        out.add(frozenset(group))
    return out


def _check(plot: _Plot) -> None:
    """Reject any draw whose geometry does not say what the design says."""
    if plot.start is None or plot.look is None:
        raise _Reject
    conducting = plot.pipe | set(plot.gates)
    if plot.pipe & set(plot.gates):
        raise _Reject  # a tile is a cell or a gate, never both
    if _components(conducting) != set(plot.parts):
        raise _Reject  # two components touched, or one split in two
    if set(plot.targets) - plot.pipe:
        raise _Reject  # gates are never checked against the panel
    if len(plot.targets) > PANEL_SLOTS:
        raise _Reject  # the reference panel must show every listed cell
    walk = plot.floor | conducting
    if plot.start not in walk or plot.look not in walk:
        raise _Reject
    if abs(plot.start[0] - plot.look[0]) + abs(plot.start[1] - plot.look[1]) != 1:
        raise _Reject


def _facing_between(start, look) -> int:
    delta = (look[0] - start[0], look[1] - start[1])
    return DELTAS.index(delta)


def _config(plot: _Plot, level: int, drain: int, cap: int) -> dict:
    conducting = plot.pipe | set(plot.gates)
    known = (
        set(conducting)
        if not plot.fog
        else {plot.start, plot.look} & conducting
    )
    return {
        "level": level,
        "floor": frozenset(plot.floor),
        "pipe": frozenset(plot.pipe),
        "pumps": dict(plot.pumps),
        "gates": dict(plot.gates),
        "junctions": frozenset(plot.junctions),
        "targets": dict(plot.targets),
        "start": plot.start,
        "facing": _facing_between(plot.start, plot.look),
        "fog": plot.fog,
        "known": frozenset(known),
        "walk": frozenset(plot.floor | conducting),
        "drain": drain,
        "cap": cap,
    }


def _calibrate(plot: _Plot, level: int) -> dict:
    """Derive this level's countdown and pump-charge cap from its own geometry.

    Pass 1 measures pure geometry with a countdown long enough never to bite,
    and takes the MINIMUM span between the first and last required press over
    every order and every gate-window hold.  Pass 2 re-runs the real search
    against the derived countdown and proves a winning line exists.
    """
    probe = _config(plot, level, PROBE_DRAIN, PROBE_CAP)
    presses = required_pumps(probe)
    if not presses:
        raise _Reject
    for cell in presses:
        if bump_action(probe, cell) is None:
            raise _Reject  # nowhere to spend a beat waiting out a gate window
    measured = search_line(probe, collect=True)
    if measured is None:
        raise _Reject
    drain = max(DRAIN_BASE, measured["span"] + DRAIN_SLACK)
    cap = 3 * len(presses) + 4
    cfg = _config(plot, level, drain, cap)
    proved = search_line(cfg)
    if proved is None or len(proved["actions"]) > cap * 40:
        raise _Reject
    return {"cfg": cfg, "drain": drain, "cap": cap, "span": measured["span"]}


# --------------------------------------------------------------------------
# the eight levels — each a canonical plot whose parameters come from the seed
# --------------------------------------------------------------------------


def _level1(rng: _Rng) -> _Plot:
    """First Pulse: one bent run, one pump, one colour, no clock at all."""
    plot = _Plot()
    legs = (rng.span(3, 5), rng.span(3, 5), rng.span(2, 3))
    cells = [(0, 0)]
    for direction, length in zip(((0, 1), (1, 0), (0, -1)), legs, strict=True):
        cells += _walk_line(cells[-1], direction, length)
    color = rng.pick(FLOW_COLORS)
    pump_at = len(cells) - 1 - rng.span(2, 3)
    plot.add_pipe(cells)
    plot.pump(cells[pump_at], color)
    plot.part(cells)
    plot.want(cells, color)
    plot.begin(cells[0], cells[1])
    return plot


def _level2(rng: _Rng) -> _Plot:
    """Two Pumps, One Beat: the obvious bridge is the long one."""
    plot = _Plot()
    hue_a, hue_b = rng.shuffled(FLOW_COLORS)[:2]
    reach = rng.span(1, 2)  # how far east the trap corridor swings
    tail = rng.span(2, 3)  # branch length on each side of the short bridge

    branch_a = [(0, 0)] + _walk_line((0, 0), (1, 0), tail - 1)
    plot.add_pipe(branch_a)
    plot.pump((0, 0), hue_a)
    plot.part(branch_a)
    plot.want(branch_a, hue_a)

    plot.add_floor([(0, -1)])  # the short bridge: one inert tile, easy to miss
    branch_b = [(0, -2)] + _walk_line((0, -2), (0, -1), tail - 1)
    plot.add_pipe(branch_b)
    plot.pump((0, -2), hue_b)
    plot.part(branch_b)
    plot.want(branch_b, hue_b)

    far = -2 - tail  # one row clear of branch B's dead end
    corridor = [(tail - 1, 1)]
    corridor += _walk_line(corridor[-1], (1, 0), reach)
    corridor += _walk_line(corridor[-1], (0, -1), 1 - far)
    corridor += _walk_line(corridor[-1], (-1, 0), tail - 1 + reach)
    plot.add_floor(corridor)
    plot.begin(corridor[0], (tail - 1, 0))
    return plot


def _level3(rng: _Rng) -> _Plot:
    """Loop of Three: raw distance lies, and one spoke is never on the panel."""
    plot = _Plot()
    hue_p, hue_q = rng.shuffled(FLOW_COLORS)[:2]
    depth = rng.span(2, 3)  # how deep pump Q sits inside its own branch
    shallow = rng.span(1, 2)  # pipe beyond pump P, which sits at the buffer edge

    plot.add_floor([(0, 0)])  # the shared hub every spoke touches

    spoke_p = [(0, -1)] + _walk_line((0, -1), (0, -1), shallow)
    plot.add_pipe(spoke_p)
    plot.pump((0, -1), hue_p)
    plot.part(spoke_p)
    plot.want(spoke_p, hue_p)

    spoke_q = _walk_line((0, 0), (1, 0), depth + 1)
    plot.add_pipe(spoke_q)
    plot.pump(spoke_q[-1], hue_q)
    plot.part(spoke_q)
    plot.want(spoke_q, hue_q)

    plot.add_floor([(0, 1)])
    plot.add_pipe([(0, 2)])
    plot.pump((0, 2), rng.pick(FLOW_COLORS))  # the spoke the panel never lists
    plot.part([(0, 2)])

    plot.begin((0, 0), (0, -1))
    return plot


def _level4(rng: _Rng) -> _Plot:
    """The Valve Between: a gate embedded mid-run, plus the Level 2 race."""
    plot = _Plot()
    hue_main, hue_side = rng.shuffled(FLOW_COLORS)[:2]
    near = rng.span(1, 2)  # pipe between the pump and the valve
    far = rng.span(2, 3)  # pipe beyond the valve
    lead = rng.span(2, 3)  # floor approach south of the pump
    link = rng.span(1, 2)  # floor bridge out to the second pump

    run = [(0, 0)] + _walk_line((0, 0), (1, 0), near)
    valve = (near + 1, 0)
    beyond = _walk_line(valve, (1, 0), far)
    plot.add_pipe(run + beyond)
    plot.pump((0, 0), hue_main)
    plot.gate(valve, rng.below(GATE_PERIOD))
    plot.part(run + [valve] + beyond)
    plot.want(run + beyond, hue_main)

    bridge = _walk_line(beyond[-1], (1, 0), link)
    plot.add_floor(bridge)
    side = [(bridge[-1][0], 1)] + _walk_line((bridge[-1][0], 1), (0, 1), 1)
    plot.add_pipe(side)
    plot.pump(side[0], hue_side)
    plot.part(side)
    plot.want(side, hue_side)

    approach = _walk_line((0, 0), (0, 1), lead)
    plot.add_floor(approach)
    plot.begin(approach[-1], approach[-2] if lead > 1 else (0, 0))
    return plot


def _fork(plot: _Plot, rng: _Rng, hub, pump_color: int) -> None:
    """The Level 5 fork: one pump, two valves, opposite states wanted at once.

    ``hub`` is the pump tile.  Valve A gates the branch the panel wants LIT,
    valve B gates the branch the panel wants DARK, and B runs a half-period
    behind A, so exactly one beat in four satisfies both.
    """
    lit_len = rng.span(2, 3)
    dark_len = rng.span(2, 3)
    offset = rng.below(GATE_PERIOD)
    axis, other = rng.pick((((0, -1), (1, 0)), ((1, 0), (0, -1))))

    valve_a = (hub[0] + axis[0], hub[1] + axis[1])
    lit = _walk_line(valve_a, axis, lit_len)
    valve_b = (hub[0] + other[0], hub[1] + other[1])
    dark = _walk_line(valve_b, other, dark_len)

    plot.add_pipe([hub] + lit + dark)
    plot.pump(hub, pump_color)
    plot.gate(valve_a, offset)
    plot.gate(valve_b, offset + 2)
    plot.part([hub, valve_a, valve_b] + lit + dark)
    plot.want([hub] + lit, pump_color)


def _level5(rng: _Rng) -> _Plot:
    """Split Decision: the same valve rule, wanted in opposite states."""
    plot = _Plot()
    hue = rng.pick(FLOW_COLORS)
    _fork(plot, rng, (0, 0), hue)
    tip = max(plot.targets, key=lambda cell: abs(cell[0]) + abs(cell[1]))
    step = (
        (0, -1) if tip[1] < 0 else (0, 1) if tip[1] > 0 else
        ((-1, 0) if tip[0] < 0 else (1, 0))
    )
    plot.begin(tip, (tip[0] - step[0], tip[1] - step[1]))
    return plot


def _level6(rng: _Rng) -> _Plot:
    """Under the Fog: Level 5's read, reachable only after scouting it."""
    plot = _Plot()
    hue = rng.pick(FLOW_COLORS)
    _fork(plot, rng, (0, 0), hue)
    lead = rng.span(3, 5)
    approach = _walk_line((0, 0), (0, 1), lead)
    if set(approach) & (plot.pipe | set(plot.gates)):
        raise _Reject
    plot.add_floor(approach)
    plot.fog = True
    plot.begin(approach[-1], approach[-2])
    return plot


def _level7(rng: _Rng) -> _Plot:
    """Two of a Shape: identical silhouettes, one honest purple tell."""
    plot = _Plot()
    hue_dual, hue_fork, hue_side = rng.shuffled(FLOW_COLORS)[:3]
    dual_west = rng.below(2) == 0  # which look-alike is the real dual-role tile
    arm = rng.span(2, 3)
    lead = rng.span(2, 3)
    spur = rng.span(2, 3)

    plot.add_floor([(0, 0)])  # the hub the two look-alikes flank
    west, east = (-1, 0), (1, 0)
    dual_at, inert_at = (west, east) if dual_west else (east, west)
    dual_step = (-1, 0) if dual_at == west else (1, 0)
    inert_step = (1, 0) if dual_at == west else (-1, 0)

    dual_branch = _walk_line(dual_at, dual_step, arm)
    plot.add_pipe(dual_branch)
    plot.gate(dual_at, rng.below(GATE_PERIOD), dual=True, color=hue_dual)
    plot.part([dual_at] + dual_branch)
    plot.want(dual_branch, hue_dual)

    inert_branch = _walk_line(inert_at, inert_step, arm)
    plot.junction(inert_at)
    plot.add_pipe(inert_branch)
    plot.part([inert_at] + inert_branch)

    plot.add_floor([(0, -1)])
    _fork(plot, rng, (0, -2), hue_fork)

    approach = _walk_line((0, 0), (0, 1), lead)
    plot.add_floor(approach)
    tap = approach[-1]
    spur_floor = _walk_line(tap, (-1, 0), spur)
    plot.add_floor(spur_floor)
    far = spur_floor[-1]
    side = [(far[0], far[1] - 1), (far[0] - 1, far[1] - 1)]
    plot.add_pipe(side)
    plot.pump(side[0], hue_side)
    plot.part(side)
    plot.want(side, hue_side)

    plot.fog = True
    plot.begin(approach[-1], approach[-2] if lead > 1 else (0, 0))
    return plot


def _level8(rng: _Rng) -> _Plot:
    """The Whole Network: three look-alikes, two opposed valves, one bridge."""
    plot = _Plot()
    hue_dual, hue_fork, hue_side = rng.shuffled(FLOW_COLORS)[:3]
    arm = rng.span(2, 3)
    lead = rng.span(4, 5)
    spur = rng.span(2, 3)

    plot.add_floor([(0, 0)])
    ring = [((-1, 0), (-1, 0)), ((0, -1), (0, -1)), ((1, 0), (1, 0))]
    real = rng.below(len(ring))
    for index, (seat, step) in enumerate(ring):
        branch = _walk_line(seat, step, arm)
        plot.add_pipe(branch)
        if index == real:
            plot.gate(seat, rng.below(GATE_PERIOD), dual=True, color=hue_dual)
            plot.want(branch, hue_dual)
        else:
            plot.junction(seat)
        plot.part([seat] + branch)

    approach = _walk_line((0, 0), (0, 1), lead)
    plot.add_floor(approach)

    fork_tap = approach[-1]
    fork_floor = _walk_line(fork_tap, (1, 0), 2)
    plot.add_floor(fork_floor)
    _fork(plot, rng, (fork_floor[-1][0] + 1, fork_floor[-1][1]), hue_fork)

    spur_tap = approach[-2]
    spur_floor = _walk_line(spur_tap, (-1, 0), spur)
    plot.add_floor(spur_floor)
    far = spur_floor[-1]
    side = [(far[0], far[1] - 1), (far[0] - 1, far[1] - 1)]
    plot.add_pipe(side)
    plot.pump(side[0], hue_side)
    plot.part(side)
    plot.want(side, hue_side)

    plot.fog = True
    plot.begin(approach[-1], approach[-2])
    return plot


_BUILDERS = (
    _level1,
    _level2,
    _level3,
    _level4,
    _level5,
    _level6,
    _level7,
    _level8,
)


def _entry(seed: int, index: int) -> dict:
    """One level's JSON-able layout record, redrawn until the geometry holds."""
    last: Exception | None = None
    for attempt in range(DRAW_ATTEMPTS):
        rng = _Rng(seed, index, attempt)
        try:
            plot = _place(_BUILDERS[index](rng), rng)
            _check(plot)
            tuned = _calibrate(plot, index + 1)
        except _Reject as exc:
            last = exc
            continue
        return {
            "level": index + 1,
            "floor": sorted([x, y] for x, y in plot.floor),
            "pipe": sorted([x, y] for x, y in plot.pipe),
            "pumps": sorted([x, y, c] for (x, y), c in plot.pumps.items()),
            "gates": sorted(
                [x, y, off, int(dual), color]
                for (x, y), (off, dual, color) in plot.gates.items()
            ),
            "junctions": sorted([x, y] for x, y in plot.junctions),
            "targets": sorted([x, y, c] for (x, y), c in plot.targets.items()),
            "start": list(plot.start),
            "facing": _facing_between(plot.start, plot.look),
            "fog": bool(plot.fog),
            "known": sorted([x, y] for x, y in tuned["cfg"]["known"]),
            "drain": tuned["drain"],
            "cap": tuned["cap"],
            "span": tuned["span"],
        }
    raise RuntimeError(f"level {index + 1} could not be drawn at seed {seed}: {last}")


@functools.lru_cache(maxsize=16)
def _layout_json(seed: int) -> str:
    return json.dumps(
        [_entry(seed, index) for index in range(LEVEL_COUNT)], sort_keys=True
    )


def build_layout(seed: int) -> list:
    """PURE, module-level, JSON-able: the whole board as a function of the seed."""
    return json.loads(_layout_json(int(seed)))


def prepare(entry: dict) -> dict:
    """Turn one JSON layout record back into the runtime config the rules read."""
    pipe = frozenset((x, y) for x, y in entry["pipe"])
    gates = {(x, y): (off, bool(dual), color) for x, y, off, dual, color in entry["gates"]}
    floor = frozenset((x, y) for x, y in entry["floor"])
    return {
        "level": entry["level"],
        "floor": floor,
        "pipe": pipe,
        "pumps": {(x, y): c for x, y, c in entry["pumps"]},
        "gates": gates,
        "junctions": frozenset((x, y) for x, y in entry["junctions"]),
        "targets": {(x, y): c for x, y, c in entry["targets"]},
        "start": tuple(entry["start"]),
        "facing": int(entry["facing"]),
        "fog": bool(entry["fog"]),
        "known": frozenset((x, y) for x, y in entry["known"]),
        "walk": floor | pipe | frozenset(gates),
        "drain": int(entry["drain"]),
        "cap": int(entry["cap"]),
    }


# --------------------------------------------------------------------------
# rendering — 16x16 lattice at 4 px, HUD painted after the board by geometry
# --------------------------------------------------------------------------

# The single -2 this game ships: an undiscovered pipe or gate tile, its true
# bend/junction shape (and, on a gate, its phase tell) masked down to a blank
# 2x2 stub.  Its declared reader is `_read_fog`, which resolves every -2 to the
# fog index as the terrain layer is built, so no rendered frame carries a -2.
_FOG_STUB = np.full((CELL, CELL), -1, dtype=np.int16)
_FOG_STUB[1:3, 1:3] = -2


def _read_fog(stub: np.ndarray) -> np.ndarray:
    """info.hidden_geometry's reader: every -2 in the mask becomes fog colour."""
    return np.where(stub == -2, C_FOG, stub)


def _canvas(height: int = 64, width: int = 64, fill: int = -1) -> np.ndarray:
    return np.full((height, width), fill, dtype=np.int16)


def _origin(cell) -> tuple:
    return cell[0] * CELL, cell[1] * CELL


def _draw_tile(canvas, cell, color: int, arms, *, device: bool) -> None:
    """One tile's connector art: 1-wide arms, and a heavier 2x2 core on devices."""
    left, top = _origin(cell)
    canvas[top + 1, left + 1] = color
    if device:
        canvas[top + 1 : top + 3, left + 1 : left + 3] = color
    if UP in arms:
        canvas[top : top + 2, left + 1] = color
    if DOWN in arms:
        canvas[top + 2 : top + CELL, left + 1] = color
    if LEFT in arms:
        canvas[top + 1, left : left + 2] = color
    if RIGHT in arms:
        canvas[top + 1, left + 2 : left + CELL] = color


def _dim_core(canvas, cell, device: bool) -> None:
    """state.wait's last beat: the shared dim tint over the cell's own core."""
    left, top = _origin(cell)
    if device:
        canvas[top + 2, left + 2] = C_DIM
    else:
        canvas[top + 1, left + 1] = C_DIM


def _rim(canvas, cell, color: int) -> None:
    left, top = _origin(cell)
    canvas[top, left : left + CELL] = color
    canvas[top + CELL - 1, left : left + CELL] = color
    canvas[top : top + CELL, left] = color
    canvas[top : top + CELL, left + CELL - 1] = color


_ARROW_UP = np.array(
    [
        [0, 1, 1, 0],
        [1, 1, 1, 1],
        [0, 1, 1, 0],
        [0, 1, 1, 0],
    ],
    dtype=np.int16,
)


def _arrow(facing: int) -> np.ndarray:
    art = np.rot90(_ARROW_UP, {UP: 0, LEFT: 1, DOWN: 2, RIGHT: 3}[facing])
    return np.where(art > 0, C_YOU, -1).astype(np.int16)


_ARROWS = {facing: _arrow(facing) for facing in range(4)}

_ACTION_INDEX = {
    GameAction.ACTION1: UP,
    GameAction.ACTION2: DOWN,
    GameAction.ACTION3: LEFT,
    GameAction.ACTION4: RIGHT,
    GameAction.ACTION5: SPACE,
}


class Game(ARCBaseGame):
    """Pump Flow, Match the Glow."""

    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed  # BEFORE super(): __init__ enters level 0
        self._layout = build_layout(seed)
        self._queued: list = []
        super().__init__(
            game_id=GAME_ID,
            levels=[
                Level(sprites=[], grid_size=(64, 64), name=f"level-{entry['level']}")
                for entry in self._layout
            ],
            camera=Camera(width=64, height=64, background=C_BG, letter_box=C_BG),
            # ACTION6 (click) and ACTION7 (undo) are absent, as the spec declares;
            # no sprite is clickable, so no sys_click tag is shipped either.
            available_actions=[1, 2, 3, 4, 5],
        )

    # -- level setup -------------------------------------------------------

    def on_set_level(self, level: Level) -> None:
        # NOTE: never name a game attribute `_state` — the engine owns that name.
        self._cfg = prepare(self._layout[self.level_index])
        self._sim = FlowState(self._cfg)
        self._queued = []
        self._arms = {
            cell: {
                action
                for action, (dx, dy) in enumerate(DELTAS)
                if (cell[0] + dx, cell[1] + dy) in self._cfg["walk"]
                and (cell[0] + dx, cell[1] + dy) not in self._cfg["floor"]
            }
            for cell in self._cfg["pipe"] | set(self._cfg["gates"])
        }

        level.remove_all_sprites()
        self._terrain_px = _canvas()
        self._glow_px = _canvas()
        self._gate_px = _canvas()
        self._cue_px = _canvas()
        self._meter_px = _canvas(1, 64, C_BG)
        self._terrain = Sprite(self._terrain_px, name="terrain", layer=LAYER_TERRAIN)
        self._glow = Sprite(self._glow_px, name="glow", layer=LAYER_GLOW)
        self._gates = Sprite(self._gate_px, name="gates", layer=LAYER_GATE)
        self._cue = Sprite(self._cue_px, name="refusal", layer=LAYER_CUE)
        self._mover = Sprite(_ARROWS[self._sim.facing], name="mover", layer=LAYER_MOVER)
        self._meter = Sprite(
            self._meter_px, name="meter", x=0, y=METER_ROW, layer=LAYER_METER
        )

        level.add_sprite(self._terrain)
        level.add_sprite(self._glow)
        level.add_sprite(self._gates)
        # locus: unique-mover — exactly ONE avatar, an arrow whose point reads
        # state.facing, and the only sprite ACTION1-4 ever answer.
        level.add_sprite(self._mover)
        level.add_sprite(self._cue)
        # hud.reserved: row63 — both HUD sprites paint after the board, over
        # geometry `_playable` keeps every generator out of, and both masks key
        # on geometry alone (a rect and a row), never on colour equality.
        level.add_sprite(self._meter)
        level.add_sprite(
            Sprite(
                self._build_panel(),
                name="panel",
                x=PANEL_X0 * CELL,
                y=0,
                layer=LAYER_PANEL,
            )
        )
        self._paint(None)

    def _build_panel(self) -> np.ndarray:
        """goal_legible: obvious — the exact win pattern, in its true colours.

        One 2x2 swatch per listed target cell, in the play field's own reading
        order, inside the goal-coloured ring.  A level whose panel is a solid
        block of one colour (Level 1) is therefore already showing the player a
        pre-lit demonstration of what "solved" looks like before they act.
        Cells the panel does not list must be DARK at the win check, which is
        what makes pumping an unlisted component a real failure.
        """
        canvas = _canvas(PANEL_PX, PANEL_PX, C_GOAL)
        canvas[1 : PANEL_PX - 1, 1 : PANEL_PX - 1] = C_BG
        order = sorted(self._cfg["targets"], key=lambda cell: (cell[1], cell[0]))
        for slot, cell in enumerate(order[:PANEL_SLOTS]):
            row, col = divmod(slot, 4)
            top, left = 1 + row * 3, 1 + col * 3
            canvas[top : top + 2, left : left + 2] = self._cfg["targets"][cell]
        return canvas

    # -- painting ----------------------------------------------------------

    def _paint(self, overlay) -> None:
        overlay = overlay or {}
        self._paint_terrain()
        self._paint_glow()
        self._paint_gates()
        self._paint_cue(overlay)
        self._mover.pixels = _ARROWS[self._sim.facing]
        left, top = _origin(self._sim.pos)
        self._mover.set_position(left, top)
        self._paint_meter()

    def _paint_terrain(self) -> None:
        """Floor, and pipe in its discovered-but-empty index — or fogged."""
        canvas = self._terrain_px
        canvas[:] = -1
        cfg = self._cfg
        for cell in sorted(cfg["floor"]):
            left, top = _origin(cell)
            canvas[top : top + CELL, left : left + CELL] = C_FLOOR
        for cell in sorted(cfg["pipe"] | set(cfg["gates"])):
            left, top = _origin(cell)
            if cell not in self._sim.known:
                canvas[top : top + CELL, left : left + CELL] = _read_fog(_FOG_STUB)
                continue
            device = cell in cfg["pumps"] or cell in cfg["junctions"] or cell in cfg["gates"]
            _draw_tile(canvas, cell, C_PIPE, self._arms[cell], device=device)
        self._terrain.pixels = canvas

    def _paint_glow(self) -> None:
        """Lit pipe at full saturation, and its one-beat dim drain warning."""
        canvas = self._glow_px
        canvas[:] = -1
        cfg = self._cfg
        for cell in sorted(self._sim.lit):
            if cell not in self._sim.known:
                continue  # fog masks colour too: physics ignores it, sight does not
            color, wait, _ = self._sim.lit[cell]
            device = cell in cfg["pumps"] or cell in cfg["junctions"]
            _draw_tile(canvas, cell, color, self._arms[cell], device=device)
            if wait <= 1:
                _dim_core(canvas, cell, device)
        self._glow.pixels = canvas

    def _paint_gates(self) -> None:
        """info.telegraph, hazard.timed, and the dual-role identity tell.

        A plain valve wears the danger hue and nothing else: a rim on its one
        telegraph beat, a solid snap to red while open.  A dual-role tile wears
        NO danger hue — its silhouette stays identical to an inert look-alike
        junction, and its only tell is the purple corner pulse, which appears
        the moment the tile is discovered and then reads out its live phase.
        """
        canvas = self._gate_px
        canvas[:] = -1
        beat = self._sim.beat
        for cell, (offset, dual, _) in sorted(self._cfg["gates"].items()):
            if cell not in self._sim.known:
                continue
            phase = _phase(offset, beat)
            left, top = _origin(cell)
            if dual:
                if phase != PHASE_OPEN:
                    canvas[top, left] = C_TELL
                if phase == PHASE_TELEGRAPH:
                    canvas[top, left + CELL - 1] = C_TELL
            elif phase == PHASE_OPEN:
                canvas[top : top + CELL, left : left + CELL] = C_DANGER
            elif phase == PHASE_TELEGRAPH:
                _rim(canvas, cell, C_DANGER)
        self._gates.pixels = canvas

    def _paint_cue(self, overlay) -> None:
        """refusal: visible — one frame of rim on the tile the action was refused on.

        Geometry decides what is paintable here, never colour equality: the cue
        keys on the refused CELL, and the same rim answers a blocked move and a
        wrong-phase SPACE press alike.  A refusal off the play field — a bump at
        the lattice edge, which is exactly how ``state.wait`` is bought — rims
        the mover's own tile instead, so that EVERY refusal shows, and so the
        cue can never paint into the panel's tiles or the meter's row.  The rim
        hue is this game's alone: nothing else on the board is ever drawn in it.
        """
        canvas = self._cue_px
        canvas[:] = -1
        cell = overlay.get("cue")
        if cell is not None:
            _rim(canvas, cell if _playable(cell) else self._sim.pos, C_CUE)
        self._cue.pixels = canvas

    def _paint_meter(self) -> None:
        """hud.meter: canvas row 63, depleting left-to-right as charges are spent.

        The fill index is HUD-only — the board never draws in it — so no meter
        pixel can ever be mistaken for live board state, or the reverse.
        """
        cap = max(1, self._cfg["cap"])
        left = max(0, min(cap, self._sim.charge))
        filled = round(64 * left / cap)
        self._meter_px[:] = C_BG
        if filled:
            self._meter_px[0, 64 - filled :] = C_METER
        self._meter.pixels = self._meter_px

    # -- the step loop -----------------------------------------------------

    def step(self) -> None:
        if self._queued:
            self._advance()
            return
        action = _ACTION_INDEX.get(self.action.id)
        if action is None:
            self._queued = [None]  # RESET, and anything else the engine hands us
            self._advance()
            return
        event = self._sim.apply(action)
        if event["cue"] is not None:
            self._queued = [{"cue": event["cue"]}, None]
        else:
            self._queued = [None]
        self._advance()

    def _advance(self) -> None:
        overlay = self._queued.pop(0)
        self._paint(overlay)
        if not self._queued:
            # budget.cap: the win check runs FIRST, so the winning press is free.
            if self._sim.won:
                self.next_level()
            elif self._sim.lost:
                self.lose()
            self.complete_action()
