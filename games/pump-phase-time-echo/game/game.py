"""Pump the Phase, Time the Echo.

One click is the whole interaction.  Clicking the pump cell raises a
pressure level; clicking anything else lets it drain.  Every step the one
shared phase counter ``P`` advances by whatever pressure is being held, and
every pad's iris valve opens and closes on a window defined against that
same ``P``.  A click on the armed pad only advances the track's sequence if
that pad's valve was open in this step's snapshot.  Echo-wired pads
schedule a delayed twin of the click that re-checks the same valve ``D``
steps later against whatever ``P`` has drifted into: open resolves quietly,
closed is a ``hazard.crush`` that resets that track and the pressure.

Terms: goal.sequence, gate.phase, flow.pumped, agent.echo, hazard.crush,
budget.cap, hazard.timed, info.telegraph, info.deception, state.wait.
"""

from __future__ import annotations

import hashlib
import heapq
from functools import cache

import numpy as np
from arcengine import (
    ARCBaseGame,
    Camera,
    GameAction,
    InteractionMode,
    Level,
    RenderableUserDisplay,
    Sprite,
)

GAME_ID = "pump-phase-time-echo"

# EXACTLY the spec's layout.seed.
DEFAULT_LAYOUT_SEED = 7
LAYOUT_NAMESPACE = "pump-phase-time-echo/layout/v1"

# ---------------------------------------------------------------- geometry
# ONE render scale for every level: a 32x32 camera upscaled 2x fills 64x64
# exactly, so one logical cell is always a 2x2 pixel block and every pad,
# the pump and the filler tile are always 4x4 cells.
BOARD = 32
SLOT = 4  # a pad (or the pump cell, or the filler tile) occupies a 4x4 slot
PITCH = 6  # slot pitch: 4 cells of object + 2 cells of gutter
COLS = 5
ROWS = 5
SLOT_X0 = 1
SLOT_Y0 = 3  # board row 0 is the reserved HUD; rows 1-2 carry the pip trail

PMAX = 4  # budget.cap: the ceiling on held pressure (flow.pumped)
# The countdown trail sits in the gutter above a pad, one pip per free cell
# with a blank cell between each, so the pips read as dots rather than a bar.
PIP_CELLS = ((-2, 0), (-2, 2), (-2, 4), (-1, 0), (-1, 2), (-1, 4))
MAX_PIPS = len(PIP_CELLS)  # so an echo delay D is at most 6

# The three clickable sprite names.  Every sprite this game tags
# ``sys_click`` carries one of them, and ``_target()`` below branches on
# exactly these three literals, so the engine's advertised click list and
# the handler agree pad for pad and level for level.
CLICK_PUMP = "pump"
CLICK_PAD = "pad"
CLICK_FILL = "filler"

# ------------------------------------------------------------------ colors
C_CANVAS = 5  # negative space: background and letter box, never an object
C_BLOCK = 0  # reserved-structure: the level-8 structural block, and nothing else
C_FILL = 1  # reserved-filler: the inert state.wait tile, and nothing else
C_SHUT = 2  # reserved: an iris core whose valve is closed
C_OPEN = 11  # palette.goal: an iris core whose valve is open
C_DANGER = 8  # palette.danger: hazard.crush ONLY — the unique-hue tell
C_YOU = 9  # palette.you: the pump cell, and the pressure notches it holds
C_ECHO = 15  # agent.echo furniture: the wiring marker and the countdown pips
C_FLASH = 13  # the one-frame refusal flash, and nothing else
C_PULSE_HI = 10  # armed-pointer pulse, bright phase
C_PULSE_LO = 12  # armed-pointer pulse, dim phase
C_METER = 4  # meter furniture: the reserved HUD row only, never on the board

# info.deception — palette overload / camouflage.  A pad's rim hue is drawn
# from this deliberately small shared set and REUSED across pads that carry
# different offsets, cycles and echo wiring, so rim colour groups pads that
# behave nothing alike.  Nothing in the rule ever reads a rim hue; the only
# reliable "which pad matters now" signal is the armed-pointer pulse.
RIM_HUES = (3, 6, 7)


class _TopHud(RenderableUserDisplay):
    """Reserved row-0 HUD, left-to-right, keyed on geometry only.

    Two one-pixel strips inside the reserved board row: the pump's
    fill-level indicator (held pressure against ``budget.cap``'s notched
    ceiling) and the click allowance still left.
    """

    def __init__(self, hud: dict) -> None:
        self._hud = hud

    def render_interface(self, frame: np.ndarray) -> np.ndarray:
        frame[0, :] = C_CANVAS
        frame[1, :] = C_CANVAS

        # budget.cap's ceiling, one notch per unit of pressure it allows.
        # The line never needs the last notches, so the headroom is visible
        # as unfilled notches the player can freely over-pump into.
        pressure = int(self._hud.get("pressure", 0))
        notch = 64 // PMAX
        for k in range(PMAX):
            left = k * notch
            frame[0, left : left + notch - 1] = C_YOU if k < pressure else C_METER

        cap = max(1, int(self._hud.get("cap", 1)))
        remaining = max(0, cap - int(self._hud.get("used", 0)))
        filled = (remaining * 64) // cap
        if filled > 0:
            frame[1, :filled] = C_METER
        return frame


# ---------------------------------------------------------------- the rule
# Reachable sums of the pressure held over the next k steps, given the
# pressure currently held.  Used to prove that a pending echo can still be
# landed before committing to a step.
def _build_reach(kmax: int) -> list[list[frozenset]]:
    table: list[list[frozenset]] = [[frozenset({0}) for _ in range(PMAX + 1)]]
    for k in range(1, kmax + 1):
        row = []
        for p in range(PMAX + 1):
            sums: set[int] = set()
            for q in (min(PMAX, p + 1), max(0, p - 1)):
                for v in table[k - 1][q]:
                    sums.add(q + v)
            row.append(frozenset(sums))
        table.append(row)
    return table


_REACH = _build_reach(MAX_PIPS + 2)


def _open_at(pad: tuple, phase: int) -> bool:
    """gate.phase: a pad's iris valve is open at a snapshot of P."""
    return (phase - pad[0]) % pad[1] < pad[2]


def _advance(pads: tuple, tracks: tuple, state: tuple, action: tuple):
    """One step of the shared rule; ``None`` when it crushes or strands an echo.

    ``state`` is ``(P, pressure, armed, pending)``.  The resolution order is
    the spec's: snapshot, pressure update, click resolution, echo
    resolution, phase advance.
    """
    phase, pressure, armed, pending = state

    due: list[int] = []
    nxt: list[tuple[int, int]] = []
    for pad_i, rem in pending:
        left = rem - 1
        if left <= 0:
            due.append(pad_i)
        else:
            nxt.append((pad_i, left))

    held = min(PMAX, pressure + 1) if action[0] == "pump" else max(0, pressure - 1)

    armed2 = list(armed)
    if action[0] == "click":
        track = action[1]
        idx = armed2[track]
        seq = tracks[track]
        if idx < len(seq):
            pad_i = seq[idx]
            if _open_at(pads[pad_i], phase):
                armed2[track] = idx + 1
                delay = pads[pad_i][3]
                if delay:
                    nxt.append((pad_i, delay))

    for pad_i in due:
        if not _open_at(pads[pad_i], phase):
            return None  # hazard.crush — never part of a planned line

    phase2 = phase + held
    for pad_i, rem in nxt:
        pad = pads[pad_i]
        reachable = _REACH[rem - 1][held]
        if not any(_open_at(pad, phase2 + s) for s in reachable):
            return None  # this echo can no longer be landed

    return (phase2, held, tuple(armed2), tuple(sorted(nxt)))


def _won(tracks: tuple, state: tuple) -> bool:
    _, _, armed, pending = state
    if pending:
        return False
    return all(a == len(seq) for a, seq in zip(armed, tracks))


def _heuristic(pads: tuple, tracks: tuple, state: tuple) -> int:
    phase, _, armed, pending = state
    score = 30 * sum(len(seq) - a for seq, a in zip(tracks, armed))
    score += 6 * len(pending)
    gaps = []
    for seq, a in zip(tracks, armed):
        if a < len(seq):
            pad = pads[seq[a]]
            gaps.append(min((pad[0] + w - phase) % pad[1] for w in range(pad[2])))
    if gaps:
        score += min(gaps)
    return score


@cache
def _search(pads: tuple, tracks: tuple, depth: int):
    """Best-first search for a crush-free winning line; ``None`` if none found."""
    actions = [("pump",), ("wait",)] + [("click", t) for t in range(len(tracks))]
    start = (0, 0, tuple(0 for _ in tracks), ())
    if _won(tracks, start):
        return ()

    best = {start: 0}
    came: dict = {}
    heap = [(_heuristic(pads, tracks, start), 0, 0, start)]
    counter = 0
    expanded = 0
    while heap:
        _, g, _, state = heapq.heappop(heap)
        if g > best.get(state, 1 << 30):
            continue
        if _won(tracks, state):
            line = []
            cur = state
            while cur in came:
                cur, act = came[cur]
                line.append(act)
            line.reverse()
            return tuple(line)
        if g >= depth:
            continue
        expanded += 1
        if expanded > 40000:
            return None
        for action in actions:
            nxt = _advance(pads, tracks, state, action)
            if nxt is None:
                continue
            ng = g + 1
            if ng < best.get(nxt, 1 << 30):
                best[nxt] = ng
                came[nxt] = (state, action)
                counter += 1
                heapq.heappush(
                    heap, (ng + _heuristic(pads, tracks, nxt), ng, counter, nxt)
                )
    return None


def _core(entry: dict) -> tuple:
    pads = tuple((p["offset"], p["cycle"], p["open"], p["echo"]) for p in entry["pads"])
    tracks = tuple(tuple(t) for t in entry["tracks"])
    return pads, tracks, int(entry["depth"])


def plan_level(entry: dict) -> list[str]:
    """The winning line for one layout entry, as abstract step choices."""
    pads, tracks, depth = _core(entry)
    line = _search(pads, tracks, depth)
    return [] if line is None else ["|".join(str(part) for part in a) for a in line]


def plan_clicks(entry: dict) -> list[list[int]]:
    """The winning line as concrete 64x64 click coordinates."""
    pads, tracks, depth = _core(entry)
    line = _search(pads, tracks, depth)
    if line is None:
        return []
    state = (0, 0, tuple(0 for _ in tracks), ())
    clicks: list[list[int]] = []
    pump_x, pump_y = entry["pump"]
    for action in line:
        if action[0] == "pump":
            cell = (pump_x + 1, pump_y + 1)
        elif action[0] == "click":
            pad_i = tracks[action[1]][state[2][action[1]]]
            cell = (entry["pads"][pad_i]["x"] + 1, entry["pads"][pad_i]["y"] + 1)
        elif entry["filler"] is not None:
            # state.wait: spend the step on the inert filler tile so pressure
            # drains and P's drift slows without disturbing any armed pointer.
            cell = (entry["filler"][0] + 1, entry["filler"][1] + 1)
        else:
            # before the filler tile exists, the same brake is a decoy click
            # on a pad that is not armed — a free, visibly-flashed refusal.
            armed_now = {seq[a] for seq, a in zip(tracks, state[2]) if a < len(seq)}
            pad_i = next(i for i in range(len(pads)) if i not in armed_now)
            cell = (entry["pads"][pad_i]["x"] + 1, entry["pads"][pad_i]["y"] + 1)
        clicks.append([cell[0] * 2, cell[1] * 2])
        state = _advance(pads, tracks, state, action)
    return clicks


# ------------------------------------------------------------- layout seed
class _Draw:
    """A deterministic byte stream derived from (seed, level, salt)."""

    def __init__(self, seed: int, index: int, salt: int) -> None:
        self._key = f"{LAYOUT_NAMESPACE}:{seed}:{index}:{salt}"
        self._buf = b""
        self._n = 0

    def byte(self) -> int:
        if not self._buf:
            self._buf = hashlib.sha256(f"{self._key}:{self._n}".encode()).digest()
            self._n += 1
        value, self._buf = self._buf[0], self._buf[1:]
        return value

    def below(self, n: int) -> int:
        return self.byte() % n

    def pick(self, seq):
        seq = list(seq)
        return seq[self.below(len(seq))]


# The curriculum: fixed level to level, only the numbers and the geometry
# move with the seed.  ``waits`` is the number of state.wait steps the level
# must actually force out of the line before the layout is accepted.
LEVEL_PLANS = [
    {"tracks": [3], "style": "shared", "echo": [], "narrow": [], "wide": [],
     "path": "row", "block": False, "filler": False, "waits": 0},
    {"tracks": [4], "style": "shared", "echo": [(0, 1)], "narrow": [], "wide": [],
     "path": "row", "block": False, "filler": False, "waits": 0},
    {"tracks": [3], "style": "mixed", "echo": [], "narrow": [], "wide": [],
     "path": "row", "block": False, "filler": False, "waits": 0},
    {"tracks": [5], "style": "mixed", "echo": [(0, 1), (0, 3)], "narrow": [],
     "wide": [], "path": "row", "block": False, "filler": False, "waits": 0},
    {"tracks": [4], "style": "narrow", "echo": [], "narrow": [], "wide": [],
     "path": "row", "block": False, "filler": True, "waits": 2},
    {"tracks": [5, 5], "style": "mixed", "echo": [(0, 1), (1, 1), (1, 3)],
     "narrow": [], "wide": [], "path": "row", "block": False, "filler": True,
     "waits": 1},
    {"tracks": [7], "style": "mixed", "echo": [(0, 1)], "narrow": [(0, 1)],
     "wide": [(0, 3), (0, 4), (0, 5)], "path": "L", "block": False,
     "filler": True, "waits": 3},
    {"tracks": [8], "style": "mixed", "echo": [(0, 1), (0, 3), (0, 5), (0, 7)],
     "narrow": [(0, 4)], "wide": [], "path": "L", "block": True, "filler": True,
     "waits": 1},
]
LEVEL_COUNT = len(LEVEL_PLANS)


def _slot_origin(col: int, row: int) -> tuple[int, int]:
    return SLOT_X0 + PITCH * col, SLOT_Y0 + PITCH * row


def _row_path(draw: _Draw, n: int, taken_rows: set) -> list[tuple[int, int]]:
    row = draw.pick([r for r in range(ROWS) if r not in taken_rows])
    taken_rows.add(row)
    start = draw.below(COLS - n + 1)
    cols = list(range(start, start + n))
    if draw.below(2):
        cols.reverse()
    return [(c, row) for c in cols]


def _l_path(draw: _Draw, n: int) -> list[tuple[int, int]]:
    options = [h for h in range(3, COLS + 1) if h <= n - 1 and (n - h) <= ROWS - 1]
    across = draw.pick(options)
    down = n - across
    col0 = draw.below(COLS - across + 1)
    row0 = draw.below(ROWS - down)
    cells = [(col0 + k, row0) for k in range(across)]
    cells += [(col0 + across - 1, row0 + 1 + k) for k in range(down)]
    if draw.below(2):
        cells = [(COLS - 1 - c, r) for c, r in cells]
    if draw.below(2):
        cells = [(c, ROWS - 1 - r) for c, r in cells]
    return cells


def _crook(cells: list[tuple[int, int]], used: set) -> list[tuple[int, int]]:
    """The slots inside the L's elbow — where a structural block belongs."""
    cols = sorted({c for c, _ in cells})
    rows = sorted({r for _, r in cells})
    return [(c, r) for c in cols for r in rows if (c, r) not in used]


def _pick_near(draw: _Draw, anchor: tuple[int, int], used: set) -> tuple[int, int]:
    col, row = anchor
    near = [
        (c, r)
        for c, r in ((col - 1, row), (col + 1, row), (col, row - 1), (col, row + 1))
        if 0 <= c < COLS and 0 <= r < ROWS and (c, r) not in used
    ]
    if near:
        return draw.pick(near)
    free = [(c, r) for r in range(ROWS) for c in range(COLS) if (c, r) not in used]
    return draw.pick(free)


def _rhythms(draw: _Draw, plan: dict, sizes: list[int]) -> list[tuple[int, int, int]]:
    """(offset, cycle, open_duration) per pad, in pad order."""
    total = sum(sizes)
    style = plan["style"]
    out: list[tuple[int, int, int]] = []
    if style == "shared":
        cycle = draw.pick([11, 12, 13])
        width = draw.pick([3, 4])
        # One shared rhythm shape, every pad offset into a different arc of it.
        band = cycle // total
        offsets = [0] + [i * band + draw.below(band) for i in range(1, total)]
        out = [(o % cycle, cycle, width) for o in offsets]
    elif style == "narrow":
        cycle = draw.pick([13, 14, 15])
        first = draw.pick([5, 6, 7])
        # The third window opens only a couple of phase-units after the
        # second one shuts — the tight pair that forces a state.wait brake.
        offsets = [0, first, (first + draw.pick([2, 3])) % cycle]
        spare = [v for v in range(cycle) if v not in offsets]
        while len(offsets) < total and spare:
            offsets.append(spare.pop(draw.below(len(spare))))
        out = [(o, cycle, 1) for o in offsets[:total]]
    else:
        cycles: list[int] = []
        pool = [9, 10, 11, 12, 13, 14, 15, 16]
        for _ in range(total):
            choices = [c for c in pool if c not in cycles] or pool
            cycles.append(draw.pick(choices))
        for cycle in cycles:
            width = draw.pick([2, 3, 4])
            out.append((draw.below(cycle), cycle, min(width, cycle - 4)))

    # per-level overrides, then force each track's first pad open at P = 0
    flat: list[list[int]] = [list(v) for v in out]
    starts = []
    base = 0
    for size in sizes:
        starts.append(base)
        base += size
    for track, idx in plan["narrow"]:
        flat[starts[track] + idx][2] = 1
    for track, idx in plan["wide"]:
        pad = flat[starts[track] + idx]
        pad[2] = min(draw.pick([4, 5]), pad[1] - 3)
    for start in starts:
        flat[start][0] = 0
        flat[start][2] = max(flat[start][2], 1)
    return [tuple(v) for v in flat]


def _rim_hues(draw: _Draw, total: int) -> list[int]:
    """info.deception: rim hues drawn from RIM_HUES and deliberately reused.

    With three or fewer pads every rim is the SAME hue (level 1's pure
    camouflage); beyond that the pads are cycled across two or three hues so
    that pads with unrelated offsets, cycles and echo wiring still land in
    matching colour groups.
    """
    groups = 1 if total <= 3 else draw.pick([2, 3])
    shift = draw.below(len(RIM_HUES))
    return [RIM_HUES[(shift + (i % groups)) % len(RIM_HUES)] for i in range(total)]


def _compose(seed: int, index: int, salt: int) -> dict:
    plan = LEVEL_PLANS[index]
    draw = _Draw(seed, index, salt)
    sizes = plan["tracks"]

    cells: list[tuple[int, int]] = []
    tracks: list[list[int]] = []
    if plan["path"] == "row":
        taken: set = set()
        for size in sizes:
            path = _row_path(draw, size, taken)
            tracks.append([len(cells) + k for k in range(size)])
            cells.extend(path)
    else:
        path = _l_path(draw, sizes[0])
        tracks.append(list(range(sizes[0])))
        cells.extend(path)

    used = set(cells)
    block = None
    if plan["block"]:
        inner = _crook(cells, used)
        if inner:
            spot = draw.pick(inner)
            used.add(spot)
            block = list(_slot_origin(*spot))
    pump = _pick_near(draw, cells[0], used)
    used.add(pump)
    filler = None
    if plan["filler"]:
        spot = _pick_near(draw, cells[len(cells) // 2], used)
        used.add(spot)
        filler = list(_slot_origin(*spot))

    rhythms = _rhythms(draw, plan, sizes)
    rims = _rim_hues(draw, len(cells))
    starts = []
    base = 0
    for size in sizes:
        starts.append(base)
        base += size
    echo_of = {}
    delay0 = draw.below(MAX_PIPS - 2)
    for n, (track, idx) in enumerate(plan["echo"]):
        # staggered delays: each wired pad gets its own D, so two echoes in
        # flight at once are never the same countdown.
        echo_of[starts[track] + idx] = 3 + (delay0 + n) % (MAX_PIPS - 2)

    pads = []
    for i, (col, row) in enumerate(cells):
        x, y = _slot_origin(col, row)
        offset, cycle, width = rhythms[i]
        track = next(t for t, seq in enumerate(tracks) if i in seq)
        pads.append(
            {
                "x": x,
                "y": y,
                "offset": int(offset),
                "cycle": int(cycle),
                "open": int(width),
                "echo": int(echo_of.get(i, 0)),
                "rim": int(rims[i]),
                "track": track,
            }
        )

    px, py = _slot_origin(*pump)
    return {
        "level": index + 1,
        "grid": [BOARD, BOARD],
        "pump": [px, py],
        "filler": filler,
        "pads": pads,
        "tracks": tracks,
        "block": block,
        "depth": 24 + 14 * sum(sizes),
        "cap": 0,
    }


def _teaches_by_showing(entry: dict) -> bool:
    """Level 1's opening frame must already show a satisfied armed target.

    Pad 1 is armed and its iris open at P = 0, with at least one other pad
    shut, so "armed + open = click it" and "shut = wait" are both on screen
    before the player acts.
    """
    pads = [(p["offset"], p["cycle"], p["open"]) for p in entry["pads"]]
    return _open_at(pads[0], 0) and any(not _open_at(p, 0) for p in pads[1:])


@cache
def _layout_cached(seed: int) -> tuple:
    entries = []
    for index in range(LEVEL_COUNT):
        plan = LEVEL_PLANS[index]
        # A layout is only kept once the shared rule is provably winnable on
        # it without a single crush, only when landing it takes real rhythm
        # work rather than a couple of lucky clicks, and only when it forces
        # out at least the state.wait braking the level is built around.
        floor = 2 * sum(plan["tracks"]) + 2
        chosen = None
        best = None
        for salt in range(24):
            entry = _compose(seed, index, salt)
            if index == 0 and not _teaches_by_showing(entry):
                continue
            line = plan_level(entry)
            if not line:
                continue
            waits = sum(1 for a in line if a == "wait")
            if best is None or len(line) > best[0]:
                best = (len(line), entry)
            if len(line) >= floor and waits >= plan["waits"]:
                chosen = (len(line), entry)
                break
        if chosen is None:
            chosen = best
        if chosen is None:  # pragma: no cover - the retries always land one
            entry = _compose(seed, index, 0)
            entry["cap"] = entry["depth"]
            entries.append(entry)
            continue
        length, entry = chosen
        entry["cap"] = length + max(10, length // 2)
        entries.append(entry)
    return tuple(entries)


def build_layout(seed: int) -> list:
    """One JSON-able entry per level; pure, and a function of the seed alone."""
    seed = int(seed)
    out = []
    for entry in _layout_cached(seed):
        copy = dict(entry)
        copy["pads"] = [dict(p) for p in entry["pads"]]
        copy["tracks"] = [list(t) for t in entry["tracks"]]
        copy["grid"] = list(entry["grid"])
        copy["pump"] = list(entry["pump"])
        copy["block"] = None if entry["block"] is None else list(entry["block"])
        copy["filler"] = None if entry["filler"] is None else list(entry["filler"])
        out.append(copy)
    return out


# ----------------------------------------------------------------- scenery
def _blank(width: int, height: int) -> np.ndarray:
    return np.full((height, width), -1, dtype=np.int8)


def _build_level(entry: dict) -> Level:
    """Explicit layers: block 1, pip trail 2, pads 3, filler 4, pump 5."""
    sprites: list[Sprite] = []
    if entry["block"]:
        block = _blank(BOARD, BOARD)
        bx, by = entry["block"]
        # A plain solid slot in the reserved structure hue, with no rim, no
        # core and no markings: the one shape on the board that is not a pad
        # and never changes, so the L-bend reads as a detour around it.
        block[by : by + SLOT, bx : bx + SLOT] = C_BLOCK
        sprites.append(
            Sprite(
                block,
                name="block",
                layer=1,
                interaction=InteractionMode.INTANGIBLE,
                tags=[],
            )
        )
    sprites.append(
        Sprite(
            _blank(BOARD, BOARD),
            name="trail",
            layer=2,
            interaction=InteractionMode.INTANGIBLE,
            tags=[],
        )
    )
    # Every pad, the filler tile and the pump cell are ``sys_click`` sprites
    # named CLICK_PAD / CLICK_FILL / CLICK_PUMP; _target() resolves a click
    # through that very tag and branches on those three names, so nothing the
    # engine advertises as clickable goes unhandled.
    for pad in entry["pads"]:
        sprites.append(
            Sprite(
                _blank(SLOT, SLOT),
                name=CLICK_PAD,
                x=pad["x"],
                y=pad["y"],
                layer=3,
                interaction=InteractionMode.INTANGIBLE,
                tags=["sys_click", "sys_every_pixel"],
            )
        )
    if entry["filler"]:
        fx, fy = entry["filler"]
        sprites.append(
            Sprite(
                _blank(SLOT, SLOT),
                name=CLICK_FILL,
                x=fx,
                y=fy,
                layer=4,
                interaction=InteractionMode.INTANGIBLE,
                tags=["sys_click", "sys_every_pixel"],
            )
        )
    px, py = entry["pump"]
    sprites.append(
        Sprite(
            _blank(SLOT, SLOT),
            name=CLICK_PUMP,
            x=px,
            y=py,
            layer=5,
            interaction=InteractionMode.INTANGIBLE,
            tags=["sys_click", "sys_every_pixel"],
        )
    )
    return Level(
        sprites=sprites, grid_size=(BOARD, BOARD), name=f"yard{entry['level']}"
    )


# -------------------------------------------------------------------- game
class PumpPhaseTimeEcho(ARCBaseGame):
    """The pipe-yard: one pump, one shared phase, tracks of iris-valved pads."""

    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed
        self._layout = build_layout(seed)
        self._hud = {"used": 0, "cap": 1, "pressure": 0}
        self._fx_queue: list[dict] = []
        camera = Camera(
            width=BOARD,
            height=BOARD,
            background=C_CANVAS,
            letter_box=C_CANVAS,
            interfaces=[_TopHud(self._hud)],
        )
        super().__init__(
            game_id=GAME_ID,
            levels=[_build_level(entry) for entry in self._layout],
            camera=camera,
            available_actions=[6],
        )

    # ------------------------------------------------------------ lifecycle
    def on_set_level(self, level: Level) -> None:
        entry = self._layout[self.level_index]
        self._entry = entry
        self._pads = entry["pads"]
        self._tracks = entry["tracks"]
        self._phase = 0
        self._pressure = 0
        self._armed = [0 for _ in self._tracks]
        self._pending: list[tuple[int, int]] = []
        self._used = 0
        self._hud["cap"] = entry["cap"]
        self._hud["used"] = 0
        self._hud["pressure"] = 0
        self._fx_queue = []
        self._outcome = None
        # The clickable sprites, looked up through the very tag the engine
        # advertises them with, in board order: pads, filler tile, pump.
        self._pad_sprites = level.get_sprites_by_name(CLICK_PAD)
        self._pump_sprite = level.get_sprites_by_name(CLICK_PUMP)[0]
        fillers = level.get_sprites_by_name(CLICK_FILL)
        self._fill_sprite = fillers[0] if fillers else None
        self._trail_sprite = level.get_sprites_by_name("trail")[0]
        self._paint({})

    def step(self) -> None:
        if self.action.id != GameAction.ACTION6:
            # ACTION1-5 and ACTION7 are absent from this game: a click is the
            # whole interaction.  They still have to leave through
            # complete_action() (the engine re-runs an unfinished handler),
            # but they cost no step, move no pressure and advance no phase.
            self._fx_queue = []
            self._paint({})
            self.complete_action()
            return
        if not self._fx_queue:
            self._fx_queue = self._resolve()
        self._paint(self._fx_queue.pop(0))
        if not self._fx_queue:
            # The outcome lands only once every frame of this click has been
            # rendered: next_level() takes effect inside the engine's own
            # render loop, which would otherwise cut the animation short.
            outcome, self._outcome = self._outcome, None
            if outcome == "win":
                self.next_level()
            elif outcome == "lose":
                self.lose()
            self.complete_action()

    # ------------------------------------------------------------ the rule
    def _valve_open(self, index: int, phase: int) -> bool:
        pad = self._pads[index]
        return (phase - pad["offset"]) % pad["cycle"] < pad["open"]

    def _target(self) -> tuple | None:
        """Resolve this click through the engine's own ``sys_click`` list.

        Exactly three sprite names carry that tag and all three are handled
        here: ``"pump"`` raises pressure, ``"pad"`` drains it and then
        resolves as an advance or as a free, visibly-flashed refusal, and
        ``"filler"`` drains it and does nothing else (state.wait).
        """
        data = self.action.data or {}
        cell = self.camera.display_to_grid(
            int(data.get("x", -1)), int(data.get("y", -1))
        )
        if cell is None:
            return None
        sprite = self.current_level.get_sprite_at(
            cell[0], cell[1], tag="sys_click", ignore_collidable=True
        )
        if sprite is None:
            return None
        if sprite.name == CLICK_PUMP:
            return ("pump",)
        if sprite.name == CLICK_FILL:
            return ("filler",)
        if sprite.name == CLICK_PAD:
            return ("pad", self._pad_sprites.index(sprite))
        return None

    def _resolve(self) -> list[dict]:
        target = self._target()
        self._used += 1
        self._hud["used"] = self._used

        # 1. snapshot — every open/closed read this step uses P as it stood
        snapshot = self._phase
        was_armed = list(self._armed)
        was_pressure = self._pressure

        due: list[int] = []
        pending: list[tuple[int, int]] = []
        for pad_i, rem in self._pending:
            left = rem - 1
            if left <= 0:
                due.append(pad_i)
            else:
                pending.append((pad_i, left))

        # 2. pressure update (flow.pumped), capped by budget.cap
        if target == ("pump",):
            held = min(PMAX, self._pressure + 1)
        else:
            held = max(0, self._pressure - 1)
        self._pressure = held

        # 3. click resolution (goal.sequence / agent.echo)
        refused = None
        if target is not None and target[0] == "filler":
            # state.wait: the inert tile takes the step, drains the pressure
            # above, flashes, and touches nothing else on the board.
            refused = ("filler",)
        elif target is not None and target[0] == "pad":
            index = target[1]
            track = self._pads[index]["track"]
            seq = self._tracks[track]
            at = self._armed[track]
            if at < len(seq) and seq[at] == index and self._valve_open(index, snapshot):
                self._armed[track] = at + 1
                delay = self._pads[index]["echo"]
                if delay:
                    pending.append((index, delay))
            else:
                refused = ("pad", index)

        # 4. echo resolution (hazard.timed — hazard.crush on a closed valve)
        crushed = [i for i in due if not self._valve_open(i, snapshot)]
        if crushed:
            # retrospective punishment: the progress the crushed pad's track
            # had already earned, and the pressure, both go back to zero.
            # P is deliberately NOT reset.
            for track in {self._pads[i]["track"] for i in crushed}:
                self._armed[track] = 0
            held = 0
            self._pressure = 0

        # 5. phase advance, using the pressure this step ends up holding
        self._phase = snapshot + held
        self._pending = sorted(pending)
        self._hud["pressure"] = self._pressure

        if crushed:
            # The 2-frame hazard.crush animation: frame 1 is the red flash
            # over the crushed iris, rendered against the armed pointer and
            # the pressure meter AS THEY STOOD; frame 2 is the same board
            # with both resets committed and visible.
            frames = [
                {
                    "crush": crushed,
                    "armed": was_armed,
                    "pressure": was_pressure,
                    "phase": snapshot,
                },
                {},
            ]
        elif refused is not None:
            frames = [{"refuse": refused}, {}]
        else:
            frames = [{}]

        solved = not self._pending and all(
            a == len(seq) for a, seq in zip(self._armed, self._tracks)
        )
        if solved:
            self._outcome = "win"
        elif self._used >= self._entry["cap"]:
            self._outcome = "lose"
        return frames

    # ----------------------------------------------------------- rendering
    def _paint(self, fx: dict) -> None:
        crushed = set(fx.get("crush", ()))
        armed = fx.get("armed", self._armed)
        pressure = fx.get("pressure", self._pressure)
        phase = fx.get("phase", self._phase)
        refused = fx.get("refuse")
        self._hud["pressure"] = pressure

        armed_pads = {seq[a] for seq, a in zip(self._tracks, armed) if a < len(seq)}
        # the armed-pointer pulse alternates between its two brightness
        # levels once per step, so the one pad that matters right now is
        # identifiable in every frame no matter how the rim hues group.
        pulse = C_PULSE_HI if self._used % 2 else C_PULSE_LO

        for i, pad in enumerate(self._pads):
            cells = self._pad_sprites[i].pixels
            if i in crushed:
                # hazard.crush: the iris snaps shut over the echo token in
                # the unique danger hue, for this one frame.
                cells[:, :] = C_DANGER
                continue
            # rim: a hue from the small shared set, reused across pads that
            # behave nothing alike (info.deception).  The armed pad wears the
            # pulse instead, which is the only trustworthy pointer.
            cells[:, :] = pulse if i in armed_pads else pad["rim"]
            # core: the iris itself, always honest about this pad's valve.
            core = C_OPEN if self._valve_open(i, phase) else C_SHUT
            cells[1 : SLOT - 1, 1 : SLOT - 1] = core
            if pad["echo"]:
                # static wiring marker: this pad owes a delayed twin whenever
                # it is live-clicked, whether or not one is pending right now
                cells[0, 0] = C_ECHO
                cells[0, SLOT - 1] = C_ECHO
                cells[SLOT - 1, 0] = C_ECHO
                cells[SLOT - 1, SLOT - 1] = C_ECHO
            if refused == ("pad", i):
                # visible refusal: the clicked pad's rim flashes for this one
                # frame and nothing else changes.  C_FLASH is worn by nothing
                # else, so a refusal can never be mistaken for an armed, shut,
                # wired, blocked or crushed cell.
                cells[0, :] = C_FLASH
                cells[SLOT - 1, :] = C_FLASH
                cells[:, 0] = C_FLASH
                cells[:, SLOT - 1] = C_FLASH

        if self._fill_sprite is not None:
            # the inert state.wait tile: flat reserved-filler colour, no rim,
            # no core, no markings — it flashes when clicked and does nothing.
            tile = self._fill_sprite.pixels
            tile[:, :] = C_FLASH if refused == ("filler",) else C_FILL

        # info.telegraph: one pip per step of delay still to run, adjacent to
        # the pad that owes the echo, one pip removed each step.  Counting the
        # pips IS the projection the hazard.timed race is played on.
        trail = self._trail_sprite.pixels
        trail[:, :] = -1
        for pad_i, rem in self._pending:
            pad = self._pads[pad_i]
            for dy, dx in PIP_CELLS[:rem]:
                trail[pad["y"] + dy, pad["x"] + dx] = C_ECHO

        # the pump cell: one flat block in palette.you.  Its fill-level
        # indicator lives in the reserved row-0 HUD directly above the board.
        self._pump_sprite.pixels[:, :] = C_YOU
