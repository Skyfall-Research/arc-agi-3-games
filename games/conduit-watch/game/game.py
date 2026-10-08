"""Conduit Watch — thread one unbroken line of light between fixed points.

The board is a sparse lattice of dark track tiles running between SOURCE
tiles and BEACON tiles.  There is no avatar: every action names a tile.
Clicking an unlit tile on the frontier makes it the one ACTIVE tile
(`manip.select_cycle` — a persistent selection every later action applies
to); ACTION5 holds that tile until its charge completes (`state.wait`);
a plain track tile then joins the single open run, and a beacon instead
LOCKS the whole run behind it, permanently, and marks itself covered
(`state.checkpoint` — the lock point every later drop reverts to).

Only one run is ever open.  Clicking a frontier tile that is not the
continuation of the open run starts a fresh run off some other LOCKED
tile and, in the same step, reverts the entire open run to unlit.  That
is the only place progress is lost, and nothing hostile causes it.

The level is banked when every beacon is covered (`goal.cover`) AND the
LOCKED-or-SOURCE tiles form one orthogonally connected component holding
every source and every beacon (`goal.path_connect`).

Geometry / reserved space (declared, not incidental):

- logical lattice: 16x16 (spec layout.grid).  Row 0 is the reserved HUD
  strip (one coverage pip per beacon, beacon-index order, left to right);
  row 15 is the reserved budget strip; the lattice itself only ever uses
  rows 1..14.  Both strips are ordinary sprites on a higher explicit
  layer, never camera interfaces, so nothing paints over them.
- render: one scale everywhere.  Each logical cell is a connected 2x2
  block of camera cells on a 32x32 camera, which the engine upscales x2:
  4 display pixels per logical cell (spec render.cell_px), no grid lines.
- palette: 5 background · 3 unlit · 12 charging (palette.you) · 10 lit
  but still droppable · 9 locked/source · 11 uncovered beacon
  (palette.goal) · 14 covered beacon.  The HUD keeps its indices off the
  board: 1 for a dark pip and for spent budget, 0 for remaining budget
  and for the one-frame refusal flash.  No -2 pixel ships anywhere.
- refusal is free and visible (knobs.refusal), never charged-and-silent:
  a refused click changes nothing, flashes white for exactly one frame,
  and costs no budget.  Every action that changes nothing is free; every
  action that changes state costs 1.
"""

from __future__ import annotations

import hashlib
import itertools

from arcengine import (
    ARCBaseGame,
    Camera,
    GameAction,
    InteractionMode,
    Level,
    Sprite,
)

GAME_ID = "conduit-watch"
DEFAULT_LAYOUT_SEED = 42
LAYOUT_NAMESPACE = "conduit-watch/layout/v1"
LEVEL_COUNT = 8

GRID_W = 16
GRID_H = 16
HUD_ROW = 0
METER_ROW = GRID_H - 1
LATTICE_TOP = HUD_ROW + 2        # one blank row of gutter under the pips
LATTICE_BOTTOM = METER_ROW - 2   # and one above the budget strip

CELL = 2                    # camera cells per logical lattice cell
CAM = GRID_W * CELL         # 32x32 camera -> x2 upscale -> 64x64
PIP_STRIDE = 3              # pip is 2 wide with a 1-cell gap

CHARGE_STEPS = 2            # every tile, every level, every seed
BUDGET_FACTOR = 15
BUDGET_FLOOR = 30

# tile kinds
SOURCE = "S"
TRACK = "T"
BEACON = "B"

# tile states
UNLIT = 0
CHARGING = 1
LIT_OPEN = 2
LOCKED = 3

C_BACKGROUND = 5
C_UNLIT = 3
C_CHARGING = 12
C_LIT_OPEN = 10
C_LOCKED = 9
C_BEACON = 11
C_COVERED = 14
C_HUD_DARK = 1
C_HUD_LIT = 0

DIRS = ((0, -1), (1, 0), (0, 1), (-1, 0))


def _neg(direction: tuple[int, int]) -> tuple[int, int]:
    return (-direction[0], -direction[1])


def _step(cell: tuple[int, int], direction: tuple[int, int]) -> tuple[int, int]:
    return (cell[0] + direction[0], cell[1] + direction[1])


def _adjacent(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


# --------------------------------------------------------------------------
# layout from seed (spec-v0.3 section 7): pure, module level, JSON-able
# --------------------------------------------------------------------------


class _Stream:
    """Deterministic byte stream derived from (seed, level, salt)."""

    def __init__(self, seed: int, index: int, salt: str) -> None:
        self._prefix = f"{LAYOUT_NAMESPACE}:{int(seed)}:{int(index)}:{salt}"
        self._block = 0
        self._buf = b""
        self._pos = 0

    def byte(self) -> int:
        if self._pos >= len(self._buf):
            self._buf = hashlib.sha256(f"{self._prefix}:{self._block}".encode()).digest()
            self._block += 1
            self._pos = 0
        value = self._buf[self._pos]
        self._pos += 1
        return value

    def below(self, bound: int) -> int:
        return self.byte() % bound if bound > 1 else 0

    def span(self, low: int, high: int) -> int:
        return low + self.below(high - low + 1)

    def pick(self, items):
        items = list(items)
        return items[self.below(len(items))]

    def shuffled(self, items):
        out = list(items)
        for i in range(len(out) - 1, 0, -1):
            j = self.below(i + 1)
            out[i], out[j] = out[j], out[i]
        return out

    def chance(self, percent: int) -> bool:
        return self.below(100) < percent


class _Plot:
    """Cells placed so far, refusing any accidental adjacency.

    A cell may only touch its own predecessor, so the lattice the player
    sees induces exactly the graph the level intends — no stray shortcut,
    no accidental fork.  The one exception is an explicitly allowed pair:
    a seam, where two beacons from two different networks are meant to be
    orthogonally adjacent so their locked stretches can meet.
    """

    def __init__(self) -> None:
        self.kind: dict[tuple[int, int], str] = {}
        self.allowed: set[frozenset] = set()

    def free(self, cell, pred) -> bool:
        x, y = cell
        if not 0 <= x < GRID_W or not LATTICE_TOP <= y <= LATTICE_BOTTOM:
            return False
        if cell in self.kind:
            return False
        for direction in DIRS:
            neighbour = _step(cell, direction)
            if neighbour not in self.kind or neighbour == pred:
                continue
            if frozenset((cell, neighbour)) not in self.allowed:
                return False
        return True

    def place(self, cell, kind, pred) -> bool:
        if not self.free(cell, pred):
            return False
        self.kind[cell] = kind
        return True

    def allow_seam(self, a, b) -> None:
        self.allowed.add(frozenset((a, b)))

    def snapshot(self) -> dict:
        return dict(self.kind)

    def restore(self, snapshot: dict) -> None:
        self.kind = snapshot


def _dir_options(rng: _Stream, prev, straight_percent: int):
    if prev is None:
        return rng.shuffled(DIRS)
    back = _neg(prev)
    turns = rng.shuffled([d for d in DIRS if d != back and d != prev])
    if rng.chance(straight_percent):
        return [prev] + turns
    return turns + [prev]


def _grow(plot, start, kinds, rng, first_dir=None, straight_percent=72):
    """Extend a clean, non-touching chain of `kinds` cells from `start`.

    Depth-first over the seeded direction order, undoing a cell whose
    subtree has nowhere left to go, so a chain only fails when the space
    genuinely cannot hold it.
    """
    budget = [6000]
    added: list[tuple[int, int]] = []

    def walk(cur, prev, depth) -> bool:
        if depth == len(kinds):
            return True
        if budget[0] <= 0:
            return False
        if depth == 0 and first_dir is not None:
            options = [first_dir]
        else:
            options = _dir_options(rng, prev, straight_percent)
        for direction in options:
            cell = _step(cur, direction)
            budget[0] -= 1
            if not plot.place(cell, kinds[depth], cur):
                continue
            added.append(cell)
            if walk(cell, direction, depth + 1):
                return True
            added.pop()
            del plot.kind[cell]
        return False

    if walk(start, first_dir, 0):
        return list(added)
    return None


def _branch_kinds(length: int) -> list[str]:
    """A branch is `length - 1` track cells and one terminal beacon."""
    return [TRACK] * (length - 1) + [BEACON]


def _hub_skirt(plot, hub, used_dir, rng, short_lengths=(2, 3)) -> bool:
    """A hub beacon's remaining three sides: source corridor + 2 branches.

    Which side carries which is tried in every order, because a corridor
    that grabs the only roomy side would otherwise strand a branch.
    """
    free_dirs = rng.shuffled([d for d in DIRS if d != used_dir])
    lengths = rng.shuffled(short_lengths)
    for order in itertools.permutations(free_dirs):
        snapshot = plot.snapshot()
        if _try_skirt(plot, hub, order, lengths, rng):
            return True
        plot.restore(snapshot)
    return False


def _try_skirt(plot, hub, order, lengths, rng) -> bool:
    if _grow(plot, hub, [TRACK, SOURCE], rng, first_dir=order[0]) is None:
        return False
    for direction, length in zip(order[1:3], lengths):
        if _grow(plot, hub, _branch_kinds(length), rng, first_dir=direction) is None:
            return False
    return True


def _level1(plot, rng) -> bool:
    """Chain: one source, a corridor of two track cells, one beacon."""
    source = (rng.span(2, 13), rng.span(3, 12))
    if not plot.place(source, SOURCE, None):
        return False
    return _grow(plot, source, [TRACK, TRACK, BEACON], rng) is not None


def _level2(plot, rng) -> bool:
    """Fork: source, a common beacon cell, two branches of unequal length.

    The common cell is itself a beacon so that it can LOCK: only a locked
    tile opens two frontiers at once, which is what makes the silent drop
    (start one branch, click into the other) reachable at all.
    """
    source = (rng.span(2, 13), rng.span(3, 12))
    if not plot.place(source, SOURCE, None):
        return False
    grown = _grow(plot, source, [BEACON], rng)
    if grown is None:
        return False
    fork = grown[0]
    inward = (fork[0] - source[0], fork[1] - source[1])
    dirs = rng.shuffled([d for d in DIRS if d != _neg(inward)])
    for direction, length in zip(dirs[:2], rng.shuffled([2, 3])):
        if _grow(plot, fork, _branch_kinds(length), rng, first_dir=direction) is None:
            return False
    return True


def _level3(plot, rng) -> bool:
    """Seam: two sources, four beacons in two pairs, the far pair adjacent."""
    seam_dir = rng.pick(DIRS)
    near = (rng.span(3, 12), rng.span(4, 11))
    far = _step(near, seam_dir)
    plot.allow_seam(near, far)
    if not plot.place(near, BEACON, None):
        return False
    if not plot.place(far, BEACON, None):
        return False
    first = rng.span(1, 2)
    second = first + rng.span(1, 2)
    legs = ((near, first, _neg(seam_dir)), (far, second, seam_dir))
    for anchor, length, outward in legs:
        partner = 0 if length == 1 else rng.pick((0, length - 1))
        kinds = [BEACON if i == partner else TRACK for i in range(length)]
        if _grow(plot, anchor, kinds + [SOURCE], rng, first_dir=outward) is None:
            return False
    return True


def _level4(plot, rng) -> bool:
    """Hub: a source corridor to one hub beacon with three unequal branches."""
    hub = (rng.span(3, 12), rng.span(4, 11))
    if not plot.place(hub, BEACON, None):
        return False
    corridor = _grow(plot, hub, [TRACK, TRACK, SOURCE], rng)
    if corridor is None:
        return False
    used = (corridor[0][0] - hub[0], corridor[0][1] - hub[1])
    dirs = rng.shuffled([d for d in DIRS if d != used])
    for direction, length in zip(dirs, rng.shuffled([2, 3, 4])):
        if _grow(plot, hub, _branch_kinds(length), rng, first_dir=direction) is None:
            return False
    return True


def _level5(plot, rng) -> bool:
    """Twin hubs: two three-way hubs whose seam branches meet, asymmetric."""
    seam_dir = rng.pick(DIRS)
    near = (rng.span(4, 11), rng.span(5, 10))
    far = _step(near, seam_dir)
    plot.allow_seam(near, far)
    if not plot.place(near, BEACON, None):
        return False
    if not plot.place(far, BEACON, None):
        return False
    short_seam = rng.span(3, 4)
    long_seam = short_seam + rng.span(3, 4)
    sides = ((near, short_seam, _neg(seam_dir)), (far, long_seam, seam_dir))
    for anchor, length, outward in sides:
        kinds = [TRACK] * (length - 1) + [BEACON]
        if not _seam_side(plot, anchor, kinds, outward, rng):
            return False
    return True


def _seam_side(plot, anchor, kinds, outward, rng) -> bool:
    """Grow a seam branch out to its hub, then dress that hub's three sides."""
    for _ in range(12):
        snapshot = plot.snapshot()
        grown = _grow(plot, anchor, kinds, rng, first_dir=outward, straight_percent=60)
        if grown is not None:
            hub = grown[-1]
            before = grown[-2] if len(grown) > 1 else anchor
            approach = (hub[0] - before[0], hub[1] - before[1])
            if _hub_skirt(plot, hub, _neg(approach), rng):
                return True
        plot.restore(snapshot)
    return False


def _level6(plot, rng) -> bool:
    """Long haul: one source, one unbranched corridor, three beacons on it."""
    source = (rng.pick((0, 1, 2, 13, 14, 15)), rng.pick((2, 3, 4, 11, 12, 13)))
    if not plot.place(source, SOURCE, None):
        return False
    first = rng.span(3, 5)
    second = rng.span(3, 6)
    third = 14 - first - second
    if not 3 <= third <= 6:
        return False
    kinds = []
    for run in (first, second, third):
        kinds.extend([TRACK] * run)
        kinds.append(BEACON)
    return _grow(plot, source, kinds, rng, straight_percent=84) is not None


def _level7(plot, rng) -> bool:
    """Nested hubs: one hub's branch is the only way to reach the second."""
    hub = (rng.span(4, 11), rng.span(4, 11))
    if not plot.place(hub, BEACON, None):
        return False
    corridor = _grow(plot, hub, [TRACK, SOURCE], rng)
    if corridor is None:
        return False
    used = (corridor[0][0] - hub[0], corridor[0][1] - hub[1])
    dirs = rng.shuffled([d for d in DIRS if d != used])
    deep = _grow(plot, hub, [TRACK, TRACK, BEACON], rng, first_dir=dirs[0])
    if deep is None:
        return False
    for direction, length in zip(dirs[1:3], rng.shuffled([2, 3])):
        if _grow(plot, hub, _branch_kinds(length), rng, first_dir=direction) is None:
            return False
    inner = deep[-1]
    approach = (inner[0] - deep[-2][0], inner[1] - deep[-2][1])
    inner_dirs = rng.shuffled([d for d in DIRS if d != _neg(approach)])
    for direction, length in zip(inner_dirs[:2], rng.shuffled([2, 3])):
        if _grow(plot, inner, _branch_kinds(length), rng, first_dir=direction) is None:
            return False
    return True


def _level8(plot, rng) -> bool:
    """Hinge: three sources, two hubs, two independent seam pairs."""
    hinge_source = (rng.span(6, 9), rng.span(7, 8))
    if not plot.place(hinge_source, SOURCE, None):
        return False
    legs = []
    for outward in ((-1, 0), (1, 0)):
        grown = _grow(
            plot,
            hinge_source,
            [TRACK, TRACK, BEACON],
            rng,
            first_dir=outward,
            straight_percent=100,
        )
        if grown is None:
            return False
        legs.append(grown[-1])
    # One network hangs above the hinge row, the other below, so the two
    # hubs never crowd each other out.
    for hinge, seam_dir in zip(legs, rng.shuffled(((0, -1), (0, 1)))):
        partner = _step(hinge, seam_dir)
        plot.allow_seam(hinge, partner)
        if not plot.place(partner, BEACON, hinge):
            return False
        length = rng.span(4, 5)
        kinds = [TRACK] * length + [BEACON]
        if not _seam_side(plot, partner, kinds, seam_dir, rng):
            return False
    return True


_GENERATORS = (
    _level1,
    _level2,
    _level3,
    _level4,
    _level5,
    _level6,
    _level7,
    _level8,
)


def _entry(index: int, plot: _Plot) -> dict:
    sources = sorted(c for c, k in plot.kind.items() if k == SOURCE)
    tracks = sorted(c for c, k in plot.kind.items() if k == TRACK)
    beacons = sorted(
        (c for c, k in plot.kind.items() if k == BEACON), key=lambda c: (c[1], c[0])
    )
    optimal = 3 * (len(tracks) + len(beacons))
    return {
        "level": index + 1,
        "sources": [list(c) for c in sources],
        "tracks": [list(c) for c in tracks],
        "beacons": [list(c) for c in beacons],
        "optimal": optimal,
        "cap": max(BUDGET_FLOOR, BUDGET_FACTOR * optimal),
    }


def build_layout(seed: int) -> list:
    """Every level's lattice as a pure function of the seed."""
    seed = int(seed)
    layout = []
    for index in range(LEVEL_COUNT):
        generate = _GENERATORS[index]
        entry = None
        for attempt in range(4096):
            rng = _Stream(seed, index, f"draw{attempt}")
            plot = _Plot()
            if generate(plot, rng):
                entry = _entry(index, plot)
                break
        if entry is None:  # pragma: no cover - 512 independent draws
            raise RuntimeError(f"no layout for level {index + 1} at seed {seed}")
        layout.append(entry)
    return layout


# --------------------------------------------------------------------------
# sprites
# --------------------------------------------------------------------------


def _block(width: int, height: int, colour: int) -> list[list[int]]:
    return [[colour] * width for _ in range(height)]


def _level_sprites(entry: dict) -> Level:
    sprites = []
    for kind, cells in (
        (SOURCE, entry["sources"]),
        (TRACK, entry["tracks"]),
        (BEACON, entry["beacons"]),
    ):
        for x, y in cells:
            if kind == SOURCE:
                colour, tags = C_LOCKED, ["conduit"]
            elif kind == TRACK:
                colour, tags = C_UNLIT, ["conduit", "sys_click"]
            else:
                colour, tags = C_BEACON, ["conduit", "sys_click"]
            sprites.append(
                Sprite(
                    pixels=_block(CELL, CELL, colour),
                    name=f"tile-{x}-{y}",
                    x=x * CELL,
                    y=y * CELL,
                    layer=2,
                    tags=tags,
                )
            )
    for index in range(len(entry["beacons"])):
        sprites.append(
            Sprite(
                pixels=_block(CELL, CELL, C_HUD_DARK),
                name=f"pip-{index}",
                x=index * PIP_STRIDE,
                y=HUD_ROW * CELL,
                layer=6,
                tags=["hud_pip"],
            )
        )
    sprites.append(
        Sprite(
            pixels=_block(CAM, CELL, C_HUD_LIT),
            name="budget",
            x=0,
            y=METER_ROW * CELL,
            layer=6,
            tags=["hud_meter"],
        )
    )
    sprites.append(
        Sprite(
            pixels=_block(CELL, CELL, C_HUD_LIT),
            name="refusal",
            x=0,
            y=LATTICE_TOP * CELL,
            layer=8,
            interaction=InteractionMode.REMOVED,
            tags=["refusal_flash"],
        )
    )
    return Level(
        sprites=sprites,
        grid_size=(CAM, CAM),
        name=f"conduit-{entry['level']}",
        data={"cap": entry["cap"]},
    )


# --------------------------------------------------------------------------
# the game
# --------------------------------------------------------------------------


class ConduitWatch(ARCBaseGame):
    """Charge tiles into one locked, connected conduit — and remember which."""

    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed
        self._layout = build_layout(seed)
        self._kind: dict[tuple[int, int], str] = {}
        self._tile_state: dict[tuple[int, int], int] = {}
        self._covered: dict[tuple[int, int], bool] = {}
        self._beacon_order: list[tuple[int, int]] = []
        self._sources: list[tuple[int, int]] = []
        self._run: list[tuple[int, int]] = []
        self._active: tuple[int, int] | None = None
        self._charge = 0
        self._cap = BUDGET_FLOOR
        self._budget = BUDGET_FLOOR
        self._flash_on = False
        self._tiles: dict[tuple[int, int], Sprite] = {}
        self._pips: list[Sprite] = []
        self._meter: Sprite | None = None
        self._flash: Sprite | None = None
        super().__init__(
            game_id=GAME_ID,
            levels=[_level_sprites(entry) for entry in self._layout],
            camera=Camera(
                width=CAM,
                height=CAM,
                background=C_BACKGROUND,
                letter_box=C_BACKGROUND,
            ),
            available_actions=[5, 6, 7],
        )

    # ---- level bring-up ------------------------------------------------

    def on_set_level(self, level: Level) -> None:
        entry = self._layout[self.level_index]
        self._kind = {}
        self._tile_state = {}
        for kind, cells in (
            (SOURCE, entry["sources"]),
            (TRACK, entry["tracks"]),
            (BEACON, entry["beacons"]),
        ):
            for x, y in cells:
                self._kind[(x, y)] = kind
                self._tile_state[(x, y)] = LOCKED if kind == SOURCE else UNLIT
        self._sources = [tuple(c) for c in entry["sources"]]
        self._beacon_order = [tuple(c) for c in entry["beacons"]]
        self._covered = {cell: False for cell in self._beacon_order}
        self._run = []
        self._active = None
        self._charge = 0
        self._cap = int(entry["cap"])
        self._budget = self._cap
        self._flash_on = False

        self._tiles = {}
        for sprite in level.get_sprites_by_tag("conduit"):
            self._tiles[(sprite.x // CELL, sprite.y // CELL)] = sprite
        self._pips = sorted(level.get_sprites_by_tag("hud_pip"), key=lambda s: s.x)
        self._meter = level.get_sprites_by_tag("hud_meter")[0]
        self._flash = level.get_sprites_by_tag("refusal_flash")[0]
        self._flash.set_interaction(InteractionMode.REMOVED)
        self._paint()

    # ---- rules ---------------------------------------------------------

    def _locked_cells(self) -> list[tuple[int, int]]:
        return [cell for cell, state in self._tile_state.items() if state == LOCKED]

    def _touches_locked(self, cell) -> bool:
        return any(self._tile_state.get(_step(cell, d)) == LOCKED for d in DIRS)

    def _continues_open_run(self, cell) -> bool:
        """The open run extends only from its own leading edge."""
        if self._active is not None or not self._run:
            return False
        return _adjacent(cell, self._run[-1])

    def _is_legal_target(self, cell) -> bool:
        if self._kind.get(cell) not in (TRACK, BEACON):
            return False
        if self._tile_state.get(cell) != UNLIT:
            return False
        return self._continues_open_run(cell) or self._touches_locked(cell)

    def _is_sprite_clickable_now(self, sprite: Sprite) -> bool:
        if "conduit" not in sprite.tags:
            return False
        return self._is_legal_target((sprite.x // CELL, sprite.y // CELL))

    def _drop_open_run(self) -> None:
        """Every uncommitted tile falls back to the last lock point."""
        for cell in self._run:
            self._tile_state[cell] = UNLIT
        self._run = []
        if self._active is not None:
            self._tile_state[self._active] = UNLIT
            self._active = None
            self._charge = 0

    def _select(self, cell) -> None:
        self._active = cell
        self._charge = 0
        self._tile_state[cell] = CHARGING

    def _click(self) -> bool:
        data = self.action.data or {}
        raw_x, raw_y = data.get("x"), data.get("y")
        grid = None
        if raw_x is not None and raw_y is not None:
            grid = self.camera.display_to_grid(int(raw_x), int(raw_y))
        if grid is None:
            self._refuse(0, LATTICE_TOP * CELL)
            return False
        sprite = self.current_level.get_sprite_at(grid[0], grid[1], "conduit")
        cell = None if sprite is None else (sprite.x // CELL, sprite.y // CELL)
        if cell is None or not self._is_legal_target(cell):
            self._refuse(grid[0], grid[1])
            return False
        if self._continues_open_run(cell):
            self._select(cell)
        else:
            self._drop_open_run()
            self._select(cell)
        return True

    def _hold(self) -> bool:
        """ACTION5: hold the selected tile while it charges."""
        if self._active is None:
            return False
        self._charge += 1
        if self._charge < CHARGE_STEPS:
            return True
        cell = self._active
        self._active = None
        self._charge = 0
        if self._kind[cell] == BEACON:
            for done in self._run:
                self._tile_state[done] = LOCKED
            self._run = []
            self._tile_state[cell] = LOCKED
            self._covered[cell] = True
        else:
            self._tile_state[cell] = LIT_OPEN
            self._run.append(cell)
        return True

    def _release(self) -> bool:
        """ACTION7: let the selection go.

        The tile it held never finished charging, so it returns to unlit;
        nothing that was ever committed is touched.
        """
        if self._active is None:
            return False
        self._tile_state[self._active] = UNLIT
        self._active = None
        self._charge = 0
        return True

    def _refuse(self, grid_x: int, grid_y: int) -> None:
        cell_x = max(0, min(GRID_W - 1, grid_x // CELL))
        cell_y = max(LATTICE_TOP, min(LATTICE_BOTTOM, grid_y // CELL))
        self._flash.set_position(cell_x * CELL, cell_y * CELL)
        self._flash.set_interaction(InteractionMode.INTANGIBLE)
        self._flash_on = True

    def _is_won(self) -> bool:
        if not all(self._covered.values()):
            return False
        locked = set(self._locked_cells())
        if not locked:
            return False
        start = min(locked)
        seen = {start}
        stack = [start]
        while stack:
            cell = stack.pop()
            for direction in DIRS:
                neighbour = _step(cell, direction)
                if neighbour in locked and neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        return all(cell in seen for cell in self._sources + self._beacon_order)

    # ---- rendering -----------------------------------------------------

    def _tile_colour(self, cell) -> int:
        state = self._tile_state[cell]
        beacon = self._kind[cell] == BEACON
        if state == CHARGING:
            return C_CHARGING
        if state == LIT_OPEN:
            return C_LIT_OPEN
        if state == LOCKED:
            return C_COVERED if beacon else C_LOCKED
        return C_BEACON if beacon else C_UNLIT

    def _paint_meter(self) -> None:
        left = max(0, min(CAM, (self._budget * CAM + self._cap - 1) // self._cap))
        self._meter.pixels[:, :left] = C_HUD_LIT
        self._meter.pixels[:, left:] = C_HUD_DARK

    def _paint(self) -> None:
        for cell, sprite in self._tiles.items():
            sprite.pixels[:, :] = self._tile_colour(cell)
        for index, cell in enumerate(self._beacon_order):
            self._pips[index].pixels[:, :] = (
                C_COVERED if self._covered[cell] else C_HUD_DARK
            )
        self._paint_meter()

    # ---- the engine's one entry point ----------------------------------

    def step(self) -> None:
        if self._flash_on:
            # Second pass of a refused click: the flash lasted one frame.
            self._flash_on = False
            self._flash.set_interaction(InteractionMode.REMOVED)
            self.complete_action()
            return

        action = self.action.id
        changed = False
        if action == GameAction.ACTION6:
            changed = self._click()
        elif action == GameAction.ACTION5:
            changed = self._hold()
        elif action == GameAction.ACTION7:
            changed = self._release()
        self._paint()

        if changed:
            if self._is_won():
                self.next_level()
                self.complete_action()
                return
            self._budget -= 1
            self._paint_meter()
            if self._budget <= 0:
                self.lose()

        if self._flash_on:
            return  # render the flash frame; the next pass clears it
        self.complete_action()
