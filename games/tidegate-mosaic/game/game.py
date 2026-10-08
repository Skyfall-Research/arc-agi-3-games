"""Tidegate Mosaic.

Five declared mechanics and nothing else a player can see:

* ``move.grid`` -- the token walks its lane one logical cell at a time and
  every single-cell step is tested for passability against the cell it
  would enter.
* ``move.slide`` -- that walk is not one step per action: a single click
  keeps repeating the step, one animation frame per cell, until a stop rule
  fires (the socket, or a bar standing shut), and the whole descent resolves
  inside the one triggering action.
* ``gate.phase`` -- a bar in a lane flips between passable and impassable on
  its own period, with no player-side control and no lethality.
* ``state.undo`` -- ACTION7 retracts the single most recently launched
  token, stalled or socketed, back to its rack slot; once retracted there is
  nothing left to retract.
* ``goal.pattern_match`` -- the level is won when the strip of colours
  painted across the socket row equals the strip painted across the
  reference swatch row.

There is no hazard, no decoy, no hidden state, no tell and no pass-time
verb: an action that resolves nothing costs nothing and moves no clock, so
waiting is only ever bought with a launch or a retraction that really
happened.

The one further thing the player can see is the declared header meter: a
needle in the reserved top-right rect that is nudged by each placement but
is a LYING DISPLAY -- read-only flavour that never gates, blocks or
contributes to the win check, and that never retreats when a placement is
retracted, so its reading and the mosaic's real state drift apart.
"""

from __future__ import annotations

import hashlib

from arcengine import (
    ARCBaseGame,
    Camera,
    GameAction,
    InteractionMode,
    Level,
    Sprite,
)

GAME_ID = "tidegate-mosaic"
DEFAULT_LAYOUT_SEED = 1337
LAYOUT_NAMESPACE = "tidegate-mosaic/layout/v1"
LEVEL_COUNT = 7

# ---------------------------------------------------------------- geometry
# One logical cell renders at CELL_PX x CELL_PX pixels: the camera is 32x32
# and the engine scales it to the mandatory 64x64 frame.  One scale, every
# level, every element.
GRID = 32
CELL_PX = 2

ROW_SWATCH = 0  # the reference chip: goal-coloured rail, hue, hue, rail
ROW_SWATCH_CHIP = 1  # the hue rows of that chip are 1-2
ROW_PANEL = 4  # chrome: the rule between the instrument header and the floor
ROW_RACK = 5  # a racked token occupies rows 5-6
SHAFT_TOP = 7  # the lane corridor is painted rows 7-24
SHAFT_ROWS = 18
ROW_SOCKET = 27  # a socket occupies rows 27-28
ROW_BEZEL = 30  # chrome: the board's bottom edge (rows 30-31)

LANE_W = 2
COL_MIN = 1  # lanes live strictly inside the bezel columns...
COL_MAX = 25  # ...and leave column 27 blank between the floor and the HUD

# A token walks the lane on the two-row lattice ROW_RACK, ROW_RACK+2, ...,
# ROW_SOCKET, so a bar sits on that same lattice: a shut bar is exactly the
# cell the next step would enter, and a refused step leaves the token in the
# cell above it.
STEP = 2
GATE_ROW_MIN = 11
GATE_ROW_MAX = 23
GATE_EARLY_ROWS = (11, 13, 15)
GATE_LATE_ROWS = (19, 21, 23)

# Reserved HUD rect (hud.reserved: custom-rect) -- nothing else paints here.
HUD_X = 28
HUD_W = 4
HUD_ROWS = 2

# ----------------------------------------------------------------- palette
C_BACKGROUND = 5  # the field
C_SHAFT = 1  # the open lane corridor, and the meter track's fill
C_SOCKET = 2  # an empty socket slot, and the meter track's rule
C_HATCH = 3  # the crosshatch that marks a bar standing OPEN
C_CHROME = 4  # inert framing, and a bar standing SHUT: solid, impassable
C_NEEDLE = 11  # palette.you -- the header meter's needle
C_GOAL = 14  # palette.goal -- the rails that frame a reference chip
C_MARK = 0  # selection/highlight index: the transient refusal flash
TOKEN_HUES = (6, 7, 8, 9, 10, 12, 13, 15)
HUES_PER_LEVEL = 4

RACKED, STALLED, PLACED = "racked", "stalled", "placed"

# Per-level authored shape; the seed moves everything inside it.
_LEVEL_SHAPE = (
    # level 1 -- no bars at all: click, walk the lane, socket.
    {"lanes": 9, "gated": 0, "doubles": 0, "periods": (), "presolve": True},
    # level 2 -- one bar in each of two lanes, both shut on the first tick.
    {"lanes": 4, "gated": 2, "doubles": 0, "periods": (4, 5, 6, 7, 8),
     "shut_first": True, "teach_undo": True},
    # level 3 -- every lane barred, every period different.
    {"lanes": 5, "gated": 5, "doubles": 0, "periods": (4, 5, 6, 7, 8, 9)},
    # level 4 -- two lanes carry two well-separated bars in series.
    {"lanes": 4, "gated": 4, "doubles": 2, "periods": (4, 5, 6, 7, 8, 9)},
    # level 5 -- six lanes, every period shortened, windows narrow.
    {"lanes": 6, "gated": 5, "doubles": 2, "periods": (3, 4, 5)},
    # level 6 -- three lanes: one that stalls a naive first click, two free.
    {"lanes": 3, "gated": 1, "doubles": 0, "periods": (4, 5, 6, 7),
     "shut_first": True, "teach_undo": True},
    # level 7 -- the full floor: unbarred, single-barred and doubled together.
    {"lanes": 8, "gated": 5, "doubles": 2, "periods": (3, 4, 5, 6)},
)


# ------------------------------------------------------------ seeded draws
class _Draw:
    """A pure, reproducible byte stream derived from (seed, level)."""

    def __init__(self, seed: int, index: int) -> None:
        self._seed = int(seed)
        self._index = int(index)
        self._block = 0
        self._buf = b""

    def byte(self) -> int:
        if not self._buf:
            key = f"{LAYOUT_NAMESPACE}:{self._seed}:{self._index}:{self._block}"
            self._buf = hashlib.sha256(key.encode()).digest()
            self._block += 1
        value, self._buf = self._buf[0], self._buf[1:]
        return int(value)

    def below(self, n: int) -> int:
        return self.byte() % max(1, int(n))

    def pick(self, seq):
        return seq[self.below(len(seq))]

    def sample(self, seq, count: int) -> list:
        pool = list(seq)
        out = []
        for _ in range(min(count, len(pool))):
            out.append(pool.pop(self.below(len(pool))))
        return out


# --------------------------------------------------------- gate arithmetic
def gate_is_open(gate: dict, tick: int) -> bool:
    """A bar stands open for the first half (rounded up) of its own period.

    This formula, against the single global tick, is the ONLY rule that
    decides a bar's state -- no player action touches it.  It is evaluated
    at the tick the board is painted at, so the bar a settled frame shows
    standing open is the bar a launch made from that frame really walks
    through: the clock advances only once the descent has resolved.
    """
    period = int(gate["period"])
    return (int(tick) + int(gate["offset"])) % period < (period + 1) // 2


def _lane_gates(entry: dict, lane: int) -> list:
    return [gate for gate in entry["gates"] if gate["lane"] == lane]


def lane_is_clear(entry: dict, lane: int, tick: int) -> bool:
    """True when every bar standing in ``lane`` is open at ``tick``."""
    return all(gate_is_open(gate, tick) for gate in _lane_gates(entry, lane))


def cell_is_passable(entry: dict, lane: int, row: int, tick: int) -> bool:
    """Passability of ONE cell of one lane -- the move.grid step test."""
    for gate in _lane_gates(entry, lane):
        if gate["row"] == row:
            return gate_is_open(gate, tick)
    return True


def slide_rest_row(entry: dict, lane: int, row: int, tick: int) -> int:
    """Where a slide starting at ``row`` comes to rest at ``tick``.

    The single-cell step of ``move.grid`` repeated until a stop rule fires:
    the socket at the bottom, or the first bar standing shut.
    """
    while row < ROW_SOCKET and cell_is_passable(entry, lane, row + STEP, tick):
        row += STEP
    return row


# ------------------------------------------------------------- the solution
def plan_level(entry: dict) -> list:
    """Derive a winning action line for one level layout by searching it.

    The verbs are only the two the game declares -- launch/resume a token by
    clicking it, and retract the single most recent launch.  Both always
    move the clock on by exactly one, so any bar's open window is always
    reachable from wherever the line currently stands; nothing here waits
    for free, because nothing in this game waits for free.
    """
    count = len(entry["lanes"])
    rows = [ROW_RACK] * count
    state = [RACKED] * count
    if entry["presolved"] >= 0:
        state[entry["presolved"]] = PLACED
        rows[entry["presolved"]] = ROW_SOCKET
    actions: list = []
    clock = [0, None]  # tick, most-recent launch

    def launch(lane: int, rest: int) -> None:
        verb = "launch" if state[lane] == RACKED else "retry"
        actions.append((verb, lane, rows[lane]))
        rows[lane] = rest
        state[lane] = PLACED if rest >= ROW_SOCKET else STALLED
        clock[0] += 1
        clock[1] = lane

    def retract(lane: int) -> None:
        actions.append(("undo", lane, rows[lane]))
        rows[lane] = ROW_RACK
        state[lane] = RACKED
        clock[0] += 1
        clock[1] = None

    # Levels 2 and 6 open on the halt-and-retract pair, so the retraction is
    # taught at the moment it is first needed.
    if entry["teach_undo"]:
        for lane in sorted({gate["lane"] for gate in entry["gates"]}):
            rest = slide_rest_row(entry, lane, ROW_RACK, clock[0])
            if ROW_RACK < rest < ROW_SOCKET:
                launch(lane, rest)
                retract(lane)
                break

    for _ in range(600):
        pending = [lane for lane in range(count) if state[lane] != PLACED]
        if not pending:
            return actions
        rests = [slide_rest_row(entry, lane, rows[lane], clock[0]) for lane in pending]
        # Finish a lane if any lane can be finished from where it stands.
        done = [lane for lane, rest in zip(pending, rests) if rest >= ROW_SOCKET]
        if done:
            launch(done[0], ROW_SOCKET)
            continue
        # Otherwise take whatever ground the current tick does offer: a
        # token that can descend at all descends, which is progress kept.
        ahead = [
            (lane, rest)
            for lane, rest in zip(pending, rests)
            if rest > rows[lane]
        ]
        if ahead:
            launch(*ahead[0])
            continue
        # Nothing can move: retract the last launch to re-arm a lane, which
        # is also the only way this game has of spending a tick.
        if clock[1] is not None:
            retract(clock[1])
            continue
        raise ValueError("layout offers no action that resolves")
    raise ValueError("layout has an unreachable lane")


# ------------------------------------------------------------ layout build
def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def _lane_columns(draw: _Draw, count: int) -> list:
    span = COL_MAX - COL_MIN + LANE_W
    gaps = [g for g in (1, 2, 3, 4) if count * LANE_W + (count - 1) * g <= span]
    gap = draw.pick(gaps) if gaps else 1
    width = count * LANE_W + (count - 1) * gap
    left = COL_MIN + draw.below(span - width + 1)
    return [left + i * (LANE_W + gap) for i in range(count)]


def _gate_rows(draw: _Draw, doubled: bool) -> list:
    if not doubled:
        low, high = GATE_ROW_MIN, GATE_ROW_MAX
        return [low + STEP * draw.below((high - low) // STEP + 1)]
    return [draw.pick(GATE_EARLY_ROWS), draw.pick(GATE_LATE_ROWS)]


def _reachable(gates: list) -> bool:
    """Is there any tick at which every bar of the lane stands open?

    Every action this game offers moves the clock on by exactly one, so a
    single such tick is enough: the player can always walk the clock to it.
    """
    span = 1
    for gate in gates:
        period = int(gate["period"])
        span = span * period // _gcd(span, period)
    return any(
        all(gate_is_open(gate, tick) for gate in gates) for tick in range(span)
    )


def _lane_ok(gates: list, shut_first: bool, distinct: bool, used: set) -> bool:
    """Does this candidate bar set meet the lane's authored demands?"""
    if shut_first and all(gate_is_open(gate, 0) for gate in gates):
        return False
    if distinct:
        keys = [(gate["period"], gate["offset"]) for gate in gates]
        if len(set(keys)) != len(keys) or any(key in used for key in keys):
            return False
    return _reachable(gates)


def _offsets_for(draw, periods, rows, lane, shut_first, used):
    """Pick one offset per bar by walking a seeded rotation of the choices.

    Enumerating (rather than resampling) makes the demands a guarantee: the
    all-bars-at-offset-zero combination is always in the walk and is always
    reachable, so the last, demandless pass can never come up empty and a
    lane is never left stranded.
    """
    starts = [draw.below(period) for period in periods]
    total = 1
    for period in periods:
        total *= period

    def candidate(step: int) -> list:
        offsets = []
        rest = step
        for axis, period in enumerate(periods):
            offsets.append((starts[axis] + rest % period) % period)
            rest //= period
        return [
            {"lane": lane, "row": row, "period": period, "offset": offset}
            for period, row, offset in zip(periods, rows, offsets)
        ]

    demands = [(True, True), (True, False)] if shut_first else []
    demands += [(False, True), (False, False)]
    for shut, distinct in demands:
        for step in range(total):
            gates = candidate(step)
            if _lane_ok(gates, shut, distinct, used):
                return gates
    return candidate(0)


def _sweep_beats(entry: dict, order: list) -> bool:
    """Would clicking the rack straight across in this order take every lane?"""
    return all(
        lane_is_clear(entry, lane, tick) for tick, lane in enumerate(order)
    )


def _blind_orders(count: int) -> list:
    """The two orders a player who never reads the bars would click in."""
    forward = list(range(count))
    return [forward, forward[::-1]]


def _break_sweeps(entry: dict, gated: list, pinned: set) -> None:
    """No barred level may be won by clicking the rack straight across.

    One lane standing shut on the tick a sweep would reach it breaks that
    sweep, so this re-picks a single lane's offsets -- walking a rotation
    that starts from the seeded ones -- keeping that lane's authored tick
    demand and its reachability intact.  A level whose bars admit no such
    choice keeps the offsets the seed drew.
    """
    orders = _blind_orders(len(entry["lanes"]))
    if not gated or not any(_sweep_beats(entry, order) for order in orders):
        return
    for lane in sorted(gated, key=lambda ln: ln in pinned):
        bars = _lane_gates(entry, lane)
        drawn = [gate["offset"] for gate in bars]
        total = 1
        for gate in bars:
            total *= gate["period"]
        for step in range(total):
            rest = step
            for gate, offset in zip(bars, drawn):
                period = gate["period"]
                gate["offset"] = (offset + rest % period) % period
                rest //= period
            if not _lane_ok(bars, lane in pinned, False, set()):
                continue
            if not any(_sweep_beats(entry, order) for order in orders):
                return
        for gate, offset in zip(bars, drawn):
            gate["offset"] = offset


def _build_entry(seed: int, index: int) -> dict:
    shape = _LEVEL_SHAPE[index]
    draw = _Draw(seed, index)
    count = shape["lanes"]

    hues = draw.sample(TOKEN_HUES, HUES_PER_LEVEL)
    lanes = [
        {"col": col, "hue": draw.pick(hues)}
        for col in _lane_columns(draw, count)
    ]
    presolved = draw.below(count) if shape.get("presolve") else -1

    order = draw.sample(range(count), count)
    gated = sorted(order[: shape["gated"]])
    doubled = set(gated[: shape["doubles"]])
    shut_all = bool(shape.get("shut_first"))
    # Periods are dealt from a pool, so lanes stay mutually desynced for as
    # long as the level's authored range can supply distinct values.
    pool = list(shape["periods"])

    gates: list = []
    pinned: set = set()
    used: set = set()
    for lane in gated:
        rows = _gate_rows(draw, lane in doubled)
        periods = []
        for _ in rows:
            if pool:
                periods.append(pool.pop(draw.below(len(pool))))
            else:
                periods.append(draw.pick(shape["periods"]))
        if shut_all:
            pinned.add(lane)
        bars = _offsets_for(draw, periods, rows, lane, shut_all, used)
        used.update((gate["period"], gate["offset"]) for gate in bars)
        gates.extend(bars)

    gates.sort(key=lambda gate: (gate["lane"], gate["row"]))
    entry = {
        "level": index + 1,
        "lanes": lanes,
        "gates": gates,
        "presolved": presolved,
        "teach_undo": bool(shape.get("teach_undo")),
        "cap": 0,
    }
    _break_sweeps(entry, gated, pinned)
    entry["cap"] = max(30, 15 * len(plan_level(entry)))
    return entry


def build_layout(seed: int) -> list:
    """Every level's structure as a function of the seed (pure, JSON-able)."""
    seed = int(seed)
    return [_build_entry(seed, index) for index in range(LEVEL_COUNT)]


# ------------------------------------------------------------------ sprite
def _block(color: int, width: int, height: int) -> list:
    return [[color] * width for _ in range(height)]


def _inert(sprite: Sprite) -> Sprite:
    sprite.set_interaction(InteractionMode.INTANGIBLE)
    return sprite


class TidegateMosaic(ARCBaseGame):
    """Click a token down its lane; the bar decides how far it gets."""

    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed
        self._layout = build_layout(seed)
        levels = [
            Level(
                sprites=None,
                grid_size=(GRID, GRID),
                data={"entry": entry},
                name=f"tide-{entry['level']}",
            )
            for entry in self._layout
        ]
        super().__init__(
            game_id=GAME_ID,
            levels=levels,
            camera=Camera(
                width=GRID,
                height=GRID,
                background=C_BACKGROUND,
                letter_box=C_BACKGROUND,
            ),
            available_actions=[6, 7],
        )

    # ------------------------------------------------------------- level
    def on_set_level(self, level: Level) -> None:
        entry = level.get_data("entry")
        self._entry = entry
        self._tick = 0
        self._spent = 0
        self._last_launch: int | None = None
        self._needle = HUD_W // 2
        self._walking = False
        self._walk_lane = 0
        self._flash: Sprite | None = None
        count = len(entry["lanes"])
        self._token_state = [RACKED] * count
        self._token_row = [ROW_RACK] * count
        self._tokens: list = []
        self._swatches: list = []
        self._sockets: list = []
        self._gate_sprites: list = []
        self._needle_sprite: Sprite | None = None
        self._draw_level(level, entry)

    def _draw_level(self, level: Level, entry: dict) -> None:
        level.remove_all_sprites()
        self._draw_chrome(level)
        self._draw_hud(level)
        for lane, spec in enumerate(entry["lanes"]):
            self._draw_lane(level, lane, spec)
        for gate in entry["gates"]:
            col = entry["lanes"][gate["lane"]]["col"]
            sprite = _inert(
                Sprite(
                    _block(C_CHROME, LANE_W, STEP),
                    name=f"gate_{gate['lane']}_{gate['row']}",
                    x=col,
                    y=gate["row"],
                    layer=3,
                    tags=[],
                )
            )
            level.add_sprite(sprite)
            self._gate_sprites.append(sprite)
        if entry["presolved"] >= 0:
            self._token_state[entry["presolved"]] = PLACED
            self._token_row[entry["presolved"]] = ROW_SOCKET
        self._sync_board()

    def _draw_chrome(self, level: Level) -> None:
        """Inert framing: it marks where the floor ends and nothing else."""
        side = _block(C_CHROME, 1, ROW_BEZEL - ROW_PANEL - 1)
        pieces = [
            ("chrome_panel", _block(C_CHROME, GRID, 1), 0, ROW_PANEL),
            (
                "chrome_bezel_bottom",
                _block(C_CHROME, GRID, GRID - ROW_BEZEL),
                0,
                ROW_BEZEL,
            ),
            ("chrome_bezel_left", side, 0, ROW_PANEL + 1),
            ("chrome_bezel_right", side, GRID - 1, ROW_PANEL + 1),
        ]
        for name, pixels, x, y in pieces:
            level.add_sprite(
                _inert(Sprite(pixels, name=name, x=x, y=y, layer=0, tags=[]))
            )

    def _draw_hud(self, level: Level) -> None:
        """The declared meter rect: a 4-cell track and one needle cell."""
        track = [[C_SOCKET] * HUD_W, [C_SHAFT] * HUD_W]
        level.add_sprite(
            _inert(
                Sprite(track, name="hud_track", x=HUD_X, y=0, layer=6, tags=[])
            )
        )
        self._needle_sprite = _inert(
            Sprite(
                _block(C_NEEDLE, 1, 1),
                name="hud_needle",
                x=HUD_X + self._needle,
                y=HUD_ROWS - 1,
                layer=7,
                tags=[],
            )
        )
        level.add_sprite(self._needle_sprite)

    def _draw_lane(self, level: Level, lane: int, spec: dict) -> None:
        col, hue = spec["col"], spec["hue"]
        chip = _inert(
            Sprite(
                [
                    [C_GOAL] * LANE_W,
                    [hue] * LANE_W,
                    [hue] * LANE_W,
                    [C_GOAL] * LANE_W,
                ],
                name=f"swatch_{lane}",
                x=col,
                y=ROW_SWATCH,
                layer=2,
                tags=[],
            )
        )
        level.add_sprite(chip)
        self._swatches.append(chip)
        level.add_sprite(
            _inert(
                Sprite(
                    _block(C_SHAFT, LANE_W, SHAFT_ROWS),
                    name=f"shaft_{lane}",
                    x=col,
                    y=SHAFT_TOP,
                    layer=1,
                    tags=[],
                )
            )
        )
        socket = _inert(
            Sprite(
                _block(C_SOCKET, LANE_W, STEP),
                name=f"socket_{lane}",
                x=col,
                y=ROW_SOCKET,
                layer=2,
                tags=[],
            )
        )
        level.add_sprite(socket)
        self._sockets.append(socket)
        token = Sprite(
            _block(hue, LANE_W, STEP),
            name=f"token_{lane}",
            x=col,
            y=ROW_RACK,
            layer=4,
            tags=["sys_click", "token"],
        )
        level.add_sprite(token)
        self._tokens.append(token)

    # -------------------------------------------------------------- render
    def _sync_board(self) -> None:
        self._sync_gates()
        for lane, token in enumerate(self._tokens):
            token.set_position(token.x, self._token_row[lane])
        if self._needle_sprite is not None:
            self._needle_sprite.set_position(
                HUD_X + self._needle, HUD_ROWS - 1
            )

    def _sync_gates(self) -> None:
        """Repaint every bar for the current tick.

        A shut bar is the solid wall block that fills the lane cell; an open
        one keeps the corridor's own fill under a crosshatch, so the
        load-bearing read differs in pattern as well as in colour and never
        depends on telling two neighbouring greys apart.
        """
        for sprite, gate in zip(self._gate_sprites, self._entry["gates"]):
            if gate_is_open(gate, self._tick):
                sprite.pixels[:, :] = C_SHAFT
                sprite.pixels[0, 0] = C_HATCH
                sprite.pixels[STEP - 1, LANE_W - 1] = C_HATCH
            else:
                sprite.pixels[:, :] = C_CHROME

    # ------------------------------------------------------------ the loop
    def step(self) -> None:
        if self._walking:
            self._advance_walk()
            return
        if self._flash is not None:
            self.current_level.remove_sprite(self._flash)
            self._flash = None
            self.complete_action()
            return
        if self.action.id == GameAction.ACTION6:
            self._handle_click()
        elif self.action.id == GameAction.ACTION7:
            self._handle_undo()
        else:
            self.complete_action()

    def _handle_click(self) -> None:
        data = self.action.data or {}
        raw_x, raw_y = data.get("x"), data.get("y")
        if raw_x is None or raw_y is None:
            self._refuse(GRID // 2, ROW_BEZEL)
            return
        cell = self.camera.display_to_grid(int(raw_x), int(raw_y))
        if cell is None:
            self._refuse(GRID // 2, ROW_BEZEL)
            return
        grid_x, grid_y = cell
        sprite = self.current_level.get_sprite_at(grid_x, grid_y, "token")
        lane = self._lane_of(sprite)
        if lane is not None and self._token_state[lane] != PLACED:
            self._begin_walk(lane, grid_x, grid_y)
            return
        self._refuse(grid_x, grid_y)

    def _handle_undo(self) -> None:
        """state.undo: the single most recent launch, and nothing else.

        The retracted token goes all the way back to its rack slot however
        far down the lane it had got, and once it is back there is nothing
        left to retract until something is launched again.
        """
        lane = self._last_launch
        if lane is None:
            self._refuse(GRID // 2, ROW_BEZEL)
            return
        self._last_launch = None
        self._token_state[lane] = RACKED
        self._token_row[lane] = ROW_RACK
        self._tick += 1
        self._spent += 1
        self._sync_board()
        self._settle()

    def _lane_of(self, sprite) -> int | None:
        if sprite is None or "token" not in sprite.tags:
            return None
        return int(sprite.name.rsplit("_", 1)[1])

    def _is_sprite_clickable_now(self, sprite) -> bool:
        """A token answers a click until it is sitting in its socket."""
        states = getattr(self, "_token_state", None)
        if states is None or "token" not in sprite.tags:
            return True
        lane = self._lane_of(sprite)
        return lane is not None and states[lane] != PLACED

    # -------------------------------------------------------- grid stepping
    def _begin_walk(self, lane: int, grid_x: int, grid_y: int) -> None:
        """Start the slide -- unless its very first step is blocked."""
        row = self._token_row[lane]
        if not cell_is_passable(self._entry, lane, row + STEP, self._tick):
            self._refuse(grid_x, grid_y)
            return
        self._walk_lane = lane
        self._walking = True

    def _advance_walk(self) -> None:
        """One grid step per animation frame: enter the next cell, or stop."""
        lane = self._walk_lane
        token = self._tokens[lane]
        row = token.y + STEP
        if not cell_is_passable(self._entry, lane, row, self._tick):
            self._finish_walk(lane, token.y)
            return
        token.set_position(token.x, row)
        if row >= ROW_SOCKET:
            self._finish_walk(lane, row)

    def _finish_walk(self, lane: int, row: int) -> None:
        self._walking = False
        self._token_row[lane] = row
        self._token_state[lane] = PLACED if row >= ROW_SOCKET else STALLED
        if row >= ROW_SOCKET:
            self._nudge_needle(lane)
        self._last_launch = lane
        self._tick += 1
        self._spent += 1
        self._sync_board()
        self._settle()

    def _nudge_needle(self, lane: int) -> None:
        """The declared header meter, and the one thing on screen that lies.

        A placement slides the needle one cell of the 4-cell track toward
        the half of the floor that socket sits in, and nothing ever slides
        it back -- a retraction leaves the reading where it was.  Nothing
        reads the needle: it does not gate a click, does not bound the
        budget and takes no part in the win check, which is the socket strip
        against the swatch strip and nothing else.  A player who reads it as
        a progress bar is reading a number the board does not owe them.
        """
        col = self._entry["lanes"][lane]["col"]
        left_half = 2 * col + LANE_W < COL_MIN + COL_MAX + LANE_W
        step = -1 if left_half else 1
        self._needle = min(HUD_W - 1, max(0, self._needle + step))

    # ------------------------------------------------------------- refusal
    def _refuse(self, grid_x: int, grid_y: int) -> None:
        """Visible, transient and FREE.

        An action that resolves nothing changes nothing: it spends no budget
        and moves no clock, so it is never a way to pass time.  Every
        refusal path in the game goes through here, so the semantics is one
        rule with no exceptions.
        """
        x = min(max(0, grid_x), GRID - STEP)
        y = min(max(0, grid_y), GRID - STEP)
        if x + STEP > HUD_X and y < HUD_ROWS:
            y = HUD_ROWS  # never paint over the reserved meter rect
        self._flash = _inert(
            Sprite(
                _block(C_MARK, STEP, STEP),
                name="refusal_flash",
                x=x,
                y=y,
                layer=9,
                tags=[],
            )
        )
        self.current_level.add_sprite(self._flash)

    # ---------------------------------------------------------- resolution
    def _strip(self, sprites: list, row: int) -> list:
        """The strip of colours actually painted across one row of the board."""
        strip = [C_BACKGROUND] * GRID
        for sprite in sorted(sprites, key=lambda item: item.layer):
            height = int(sprite.pixels.shape[0])
            if not (sprite.y <= row < sprite.y + height):
                continue
            for offset, color in enumerate(sprite.pixels[row - sprite.y]):
                if int(color) >= 0:
                    strip[sprite.x + offset] = int(color)
        return strip

    def _mosaic_matches(self) -> bool:
        """goal.pattern_match: the floor strip equals the reference strip."""
        floor = self._strip(self._sockets + self._tokens, ROW_SOCKET)
        return floor == self._strip(self._swatches, ROW_SWATCH_CHIP)

    def _settle(self) -> None:
        if self._mosaic_matches():
            self.next_level()
        elif self._spent >= self._entry["cap"]:
            self.lose()
        self.complete_action()


def _self_check() -> None:
    """Cheap import-time guard that every shipped level stays solvable."""
    for entry in build_layout(DEFAULT_LAYOUT_SEED):
        plan_level(entry)


_self_check()
