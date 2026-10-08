"""Seamlock — fuse keyed tiles into the shape an outline wants.

Every level ships outlined target clusters and the loose tiles that can
cover them. A click resolves in exactly three mutually exclusive branches,
in this fixed order:

1. the clicked cell holds no tile -> free, visible refusal;
2. otherwise test STAMP-ELIGIBILITY: the clicked tile's own cell-shape is
   compared against the shape of each still-uncovered cluster.  An exact
   match covers that cluster and consumes the tile.  Shape is the only
   key: no distance, no axis, no sweep, no line of sight;
3. otherwise test MERGE-ELIGIBILITY: scan the clicked tile's boundary
   edges in canonical order (cells top-to-bottom then left-to-right, each
   cell's edges UP, RIGHT, DOWN, LEFT) and fuse with the neighbouring tile
   whose facing edge carries the keyed complement.  The fusion is refused
   when the fused footprint would land on another tile or a cluster.  No
   keyed edge, or a refused fusion -> free, visible refusal.

A fusion is permanent, and the fused footprint is the union of the two
tiles' pool-relative cells, so what a composite ends up looking like is
decided by WHICH keyed edges were spent, never by the order they were
spent in.  Every tile in every level is needed by exactly one cluster and
every keyed edge names a real, correctly keyed partner on the board.

Declared surface: goal.cover, manip.interlock, manip.attribute,
goal.keyed, manip.merge.  Click-only (ACTION6).  No hazards, no timers,
no undo, no deceptions: a refused click never costs anything and never
moves anything.
"""

from __future__ import annotations

import hashlib

import numpy as np
from arcengine import (
    ARCBaseGame,
    Camera,
    GameAction,
    InteractionMode,
    Level,
    Sprite,
)

GAME_ID = "seamlock"
DEFAULT_LAYOUT_SEED = 73
LAYOUT_NAMESPACE = "g20261001-1/seamlock/layout/v4"
LEVEL_COUNT = 7

GRID = 16
CELL = 4  # render.cell_px — 16 logical cells x 4px exactly fills 64x64
PITCH = 2  # loose tiles of one pool sit two cells apart: the odd cells
# between them are where that pool's keyed-edge glyphs are drawn, which is
# why no glyph is ever painted inside a tile.

# --- palette roles (one index, one role) ---------------------------------
C_FIELD = 5  # the painted field (canon background default)
C_PANEL = 2  # inert chrome: the top panel band and the bottom bezel band
C_GOAL = 11  # palette.goal — an uncovered cell of a target cluster
C_YOU = 9  # palette.you — an unfused, loose single-cell tile
C_LOCKED = 3  # the covered/locked hue, from palette.reserved
C_INK = 13  # keyed-edge glyph ink
C_HI = 0  # selection/highlight: the budget meter and the refusal flash
POOL_HUES = (14, 12, 6, 10)  # one flat hue per pool, for fused composites

# --- geometry ------------------------------------------------------------
HUD_ROW = 0  # hud.reserved: row0 — the budget meter lives here
BEZEL_Y0, BEZEL_Y1 = 14, 15  # inert bottom bezel band
PLAY_X0, PLAY_X1 = 0, 15
PLAY_Y0, PLAY_Y1 = 1, 13

# Explicit layer values for every overlap that matters.
LAYER_CHROME = 0
LAYER_GOAL = 1
LAYER_TILE = 2
LAYER_MARK = 4
LAYER_FLASH = 6
LAYER_HUD = 8

# Canonical boundary-edge scan order: UP, RIGHT, DOWN, LEFT.
DIRS = (("U", 0, -1), ("R", 1, 0), ("D", 0, 1), ("L", -1, 0))
DELTA = {name: (dx, dy) for name, dx, dy in DIRS}

CLICK_TAG = "piece"  # every clickable sprite carries this tag
BUDGET_FACTOR = 15  # cap >= 15 x the optimal line, and never under 30


# =========================================================================
# §7 layout-from-seed — pure, module level, JSON-able
# =========================================================================


class _Draw:
    """A tiny deterministic draw stream, namespaced per (seed, index)."""

    def __init__(self, seed: int, index: int) -> None:
        self._seed = int(seed)
        self._index = int(index)
        self._pos = 0
        self._buf = b""

    def byte(self) -> int:
        if self._pos >= len(self._buf):
            key = f"{LAYOUT_NAMESPACE}:{self._seed}:{self._index}:{self._pos}"
            self._buf += hashlib.sha256(key.encode()).digest()
        value = self._buf[self._pos]
        self._pos += 1
        return value

    def below(self, n: int) -> int:
        return 0 if n <= 1 else self.byte() % n

    def pick(self, seq):
        items = list(seq)
        return items[self.below(len(items))]

    def shuffled(self, seq) -> list:
        items = list(seq)
        for i in range(len(items) - 1, 0, -1):
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]
        return items


def _normal(cells) -> tuple:
    """A cell set's translation-free silhouette — the stamp key."""
    x0 = min(c[0] for c in cells)
    y0 = min(c[1] for c in cells)
    return tuple(sorted((c[0] - x0, c[1] - y0) for c in cells))


def _reading(cells) -> list:
    return sorted(cells, key=lambda c: (c[1], c[0]))


def _extent(cells):
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


# The eight dihedral maps on pool coordinates. The seed picks one per pool,
# so a bar lies across or down, a bent tromino points any of four ways and
# a 2x3 block stands either way, in every seed instance.
def _xformed(cells, code) -> list:
    """Apply dihedral map `code`, with no re-anchoring."""
    out = []
    for x, y in cells:
        if code & 4:
            x, y = y, x
        if code & 1:
            x = -x
        if code & 2:
            y = -y
        out.append((x, y))
    return out


# Each level is a tuple of pools; each pool is a tuple of parts; each part
# is the group of pool cells that covers exactly one target cluster. A
# pool's own shape is the union of its parts, so no pool ever holds a tile
# that no cluster needs, and no cluster lacks a tile.
_P_SQUARE = ((0, 0), (1, 0), (0, 1), (1, 1))
_RECIPES = (
    # 1 — one shared pool teaches all three branches: a single cell, a
    #     two-cell bar and a bent three-cell notch out of one 3x2 block.
    ((((0, 0),), ((2, 0), (2, 1)), ((1, 0), (0, 1), (1, 1))),),
    # 2 — the square's pool is its only pool, and one independent tile
    #     feeds the lone single-cell target.
    ((_P_SQUARE,), (((0, 0),),)),
    # 3 — reuse in a low-stakes frame: three independent pools, the
    #     straight four-bar that was the wrong shape before, a mirrored
    #     bent notch, and a plain pair.
    (
        (((0, 0), (1, 0), (2, 0), (3, 0)),),
        (((0, 0), (0, 1), (1, 1)),),
        (((0, 0), (1, 0)),),
    ),
    # 4 — one six-tile pool splits into the square and the bar.
    ((_P_SQUARE, ((0, 2), (1, 2))),),
    # 5 — the same split doubled: one eight-tile pool feeds two squares,
    #     and a three-bar keeps its own untouched pool.
    (
        (_P_SQUARE, ((2, 0), (3, 0), (2, 1), (3, 1))),
        (((0, 0), (1, 0), (2, 0)),),
    ),
    # 6 — a dependency network: an independent square, an independent
    #     bar, and one ten-tile pool contested by a square and a 3x2.
    (
        (_P_SQUARE,),
        (((0, 0), (1, 0), (2, 0)),),
        (
            _P_SQUARE,
            ((2, 0), (3, 0), (4, 0), (2, 1), (3, 1), (4, 1)),
        ),
    ),
    # 7 — the finale adds two single-cell clusters whose only material is
    #     a pair of isolated tiles that must be spent unfused.
    (
        (_P_SQUARE,),
        (((0, 0), (1, 0), (2, 0)),),
        (
            _P_SQUARE,
            ((2, 0), (3, 0), (4, 0), (2, 1), (3, 1), (4, 1)),
        ),
        (((0, 0),),),
        (((0, 0),),),
    ),
)


def _adjacent(a, b) -> str | None:
    for name, dx, dy in DIRS:
        if (a[0] + dx, a[1] + dy) == b:
            return name
    return None


def _part_tree(draw, cells) -> list:
    """A spanning tree over one part's cells: the keyed edges inside it."""
    cells = list(cells)
    if len(cells) < 2:
        return []
    seen = {cells[0]}
    edges = []
    while len(seen) < len(cells):
        options = []
        for a in _reading(seen):
            for b in draw.shuffled(cells):
                if b in seen:
                    continue
                if _adjacent(a, b):
                    options.append((a, b))
        if not options:
            break
        a, b = options[draw.below(len(options))]
        seen.add(b)
        edges.append((a, b))
    return edges


def _link_parts(draw, parts) -> list:
    """The keyed edges BETWEEN parts — one per join, never more.

    These are the edges that make a pool a shared pool: a real, correctly
    keyed fusion that grows a composite across the boundary between two
    clusters' material and so spends a tile the other cluster needs.
    """
    joined = set(parts[0])
    edges = []
    for _ in range(len(parts) - 1):
        options = []
        for part in parts:
            if part[0] in joined:
                continue
            for a in _reading(joined):
                for b in _reading(part):
                    if _adjacent(a, b):
                        options.append((a, b, part))
        if not options:
            break
        a, b, part = options[draw.below(len(options))]
        joined.update(part)
        edges.append((a, b))
    return edges


def _assign_icons(draw, edges) -> list:
    """Give each keyed edge one of the two icon shapes.

    Two edges on the same tile take different icons wherever that is
    possible, so a tile carrying two live keys shows two distinguishable
    glyphs rather than the same glyph twice.
    """
    used: dict = {}
    icons = []
    for a, b in edges:
        taken = used.get(a, set()) | used.get(b, set())
        free = [i for i in (0, 1) if i not in taken]
        icon = free[0] if free else draw.below(2)
        icons.append(icon)
        used.setdefault(a, set()).add(icon)
        used.setdefault(b, set()).add(icon)
    return icons


def _pool_plan(draw, recipe):
    """One pool: its tiles in pool coordinates, its parts, its keyed edges."""
    code = draw.below(8)
    parts = [_xformed(part, code) for part in recipe]
    # Re-anchor the whole pool, keeping the parts' relative placement.
    whole = [cell for part in parts for cell in part]
    x0 = min(c[0] for c in whole)
    y0 = min(c[1] for c in whole)
    parts = [[(x - x0, y - y0) for x, y in part] for part in parts]

    edges = []
    for part in parts:
        edges.extend(_part_tree(draw, part))
    edges.extend(_link_parts(draw, parts))
    icons = _assign_icons(draw, edges)
    cells = [cell for part in parts for cell in part]
    return parts, cells, edges, icons


def _pack(draw, boxes):
    """Shelf-pack the pools' footprints and the clusters into the field.

    Order, shelf origin and inter-box gap all move with the seed, so every
    seed lands the same structure at different board coordinates.
    """
    for attempt in range(8):
        order = (
            draw.shuffled(range(len(boxes)))
            if attempt
            else sorted(range(len(boxes)), key=lambda i: -boxes[i][1])
        )
        gap = 2 if attempt % 3 == 2 else 1
        x_start = 1 if attempt % 2 else 0
        spots: dict = {}
        x, y, shelf = x_start, PLAY_Y0, 0
        ok = True
        for i in order:
            width, height = boxes[i]
            if x + width - 1 > PLAY_X1:
                y += shelf + gap
                x, shelf = x_start, 0
            if y + height - 1 > PLAY_Y1:
                ok = False
                break
            spots[i] = (x, y)
            x += width + gap
            shelf = max(shelf, height)
        if ok:
            return spots
    return None


def _level_entry(draw, index, recipe):
    plans = [_pool_plan(draw, pool) for pool in recipe]

    boxes = []
    pool_box = []
    for parts, cells, _edges, _icons in plans:
        width, height = _extent(cells)
        pool_box.append(len(boxes))
        boxes.append((PITCH * (width - 1) + 1, PITCH * (height - 1) + 1))
    cluster_box = []
    for parts, _cells, _edges, _icons in plans:
        for part in parts:
            cluster_box.append(len(boxes))
            boxes.append(_extent(part))

    spots = _pack(draw, boxes)
    if spots is None:  # pragma: no cover — every recipe fits every seed
        raise RuntimeError("seamlock: layout does not fit the field")

    tiles = []
    marks = []
    parts_out = []
    clusters = []
    slot = 0
    for pool, (parts, cells, edges, icons) in enumerate(plans):
        base = spots[pool_box[pool]]
        index_of = {}
        for cell in _reading(cells):
            index_of[cell] = len(tiles)
            tiles.append(
                {
                    "p": [cell[0], cell[1]],
                    "cell": [
                        base[0] + PITCH * cell[0],
                        base[1] + PITCH * cell[1],
                    ],
                    "pool": pool,
                    "hue": POOL_HUES[pool % len(POOL_HUES)],
                }
            )
        for (a, b), icon in zip(edges, icons):
            ia, ib = index_of[a], index_of[b]
            # The tab rides on the tile that comes first in reading order
            # and the hollow notch on its partner, so one glyph tells both
            # halves of the key apart.
            marks.append([ia, ib, int(icon)])
        for part in parts:
            parts_out.append(sorted(index_of[cell] for cell in part))
            origin = spots[cluster_box[slot]]
            slot += 1
            px = min(c[0] for c in part)
            py = min(c[1] for c in part)
            clusters.append(
                [
                    [origin[0] + c[0] - px, origin[1] + c[1] - py]
                    for c in _reading(part)
                ]
            )

    optimal = len(tiles)  # one click per tile: every fusion, every stamp
    return {
        "level": index + 1,
        "tiles": tiles,
        "marks": marks,
        "parts": parts_out,
        "clusters": clusters,
        "cap": max(30, BUDGET_FACTOR * optimal),
        "optimal": optimal,
    }


def build_layout(seed: int) -> list:
    """PURE, module-level, JSON-able: one entry per level."""
    seed = int(seed)
    return [
        _level_entry(_Draw(seed, index), index, recipe)
        for index, recipe in enumerate(_RECIPES)
    ]


# =========================================================================
# the operational rule — one three-branch click resolution, all seven levels
# =========================================================================


def init_state(entry: dict) -> dict:
    tiles = [
        {
            "p": (t["p"][0], t["p"][1]),
            "pool": t["pool"],
            "hue": t["hue"],
        }
        for t in entry["tiles"]
    ]
    pieces = []
    for index, tile in enumerate(entry["tiles"]):
        px, py = tile["p"]
        pieces.append(
            {
                "tiles": [index],
                "off": (tile["cell"][0] - px, tile["cell"][1] - py),
            }
        )
    marks = [
        {"a": a, "b": b, "icon": icon, "live": True} for a, b, icon in entry["marks"]
    ]
    clusters = [
        {
            "cells": tuple((c[0], c[1]) for c in cells),
            "shape": _normal([(c[0], c[1]) for c in cells]),
            "covered": False,
        }
        for cells in entry["clusters"]
    ]
    return {
        "tiles": tiles,
        "pieces": pieces,
        "marks": marks,
        "clusters": clusters,
        "cap": entry["cap"],
    }


def piece_cells(state: dict, piece: dict) -> list:
    ox, oy = piece["off"]
    return [
        (ox + state["tiles"][i]["p"][0], oy + state["tiles"][i]["p"][1])
        for i in piece["tiles"]
    ]


def tile_cell(state: dict, piece: dict, tile: int):
    ox, oy = piece["off"]
    px, py = state["tiles"][tile]["p"]
    return (ox + px, oy + py)


def piece_at(state: dict, cell):
    for index, piece in enumerate(state["pieces"]):
        if cell in piece_cells(state, piece):
            return index
    return -1


def piece_of_tile(state: dict, tile: int) -> int:
    for index, piece in enumerate(state["pieces"]):
        if tile in piece["tiles"]:
            return index
    return -1


def blocked_cells(state: dict, skip) -> set:
    """Everything a fused footprint may not land on."""
    taken = set()
    for index, piece in enumerate(state["pieces"]):
        if index in skip:
            continue
        taken.update(piece_cells(state, piece))
    for cluster in state["clusters"]:
        taken.update(cluster["cells"])
    return taken


def first_keyed_edge(state: dict, index: int):
    """The canonical scan: cells in reading order, edges UP/RIGHT/DOWN/LEFT."""
    piece = state["pieces"][index]
    order = sorted(piece["tiles"], key=lambda t: tile_cell(state, piece, t)[::-1])
    for tile in order:
        px, py = state["tiles"][tile]["p"]
        for side, dx, dy in DIRS:
            want = (px + dx, py + dy)
            for mark in state["marks"]:
                if not mark["live"]:
                    continue
                if mark["a"] == tile:
                    other = mark["b"]
                elif mark["b"] == tile:
                    other = mark["a"]
                else:
                    continue
                if state["tiles"][other]["p"] != want:
                    continue
                if other in piece["tiles"]:
                    continue
                return mark, tile, other, side
    return None


def stamp_target(state: dict, index: int) -> int:
    shape = _normal(piece_cells(state, state["pieces"][index]))
    for number, cluster in enumerate(state["clusters"]):
        if not cluster["covered"] and cluster["shape"] == shape:
            return number
    return -1


def resolve_click(state: dict, cell, index: int | None = None) -> dict:
    """The whole game: branch 1 refusal, branch 2 stamp, branch 3 fusion.

    `index` is the piece the caller already identified (the game routes it
    off the clicked sprite); when it is None the piece is looked up from
    the cell instead, which is the same answer either way.
    """
    if index is None:
        index = piece_at(state, cell)
    if index < 0:
        return {"kind": "refuse", "why": "empty", "cell": cell}

    target = stamp_target(state, index)
    if target >= 0:
        state["clusters"][target]["covered"] = True
        for mark in state["marks"]:
            if mark["a"] in state["pieces"][index]["tiles"]:
                mark["live"] = False
            if mark["b"] in state["pieces"][index]["tiles"]:
                mark["live"] = False
        state["pieces"].pop(index)
        return {"kind": "stamp", "cluster": target, "cell": cell}

    found = first_keyed_edge(state, index)
    if found is None:
        return {"kind": "refuse", "why": "unkeyed", "cell": cell}

    mark, _tile, other, _side = found
    partner = piece_of_tile(state, other)
    piece = state["pieces"][index]
    fused = sorted(piece["tiles"] + state["pieces"][partner]["tiles"])
    ox, oy = piece["off"]
    cells = [
        (ox + state["tiles"][t]["p"][0], oy + state["tiles"][t]["p"][1])
        for t in fused
    ]
    taken = blocked_cells(state, {index, partner})
    off_field = any(
        not (PLAY_X0 <= cx <= PLAY_X1 and PLAY_Y0 <= cy <= PLAY_Y1)
        for cx, cy in cells
    )
    if off_field or any(c in taken for c in cells):
        # manip.interlock: the mechanism refuses a fusion whose own fused
        # footprint would land on another tile or on a cluster.
        return {"kind": "refuse", "why": "interlock", "cell": cell}

    mark["live"] = False
    piece["tiles"] = fused
    state["pieces"].pop(partner)
    return {"kind": "merge", "cell": cell}


def is_won(state: dict) -> bool:
    return all(cluster["covered"] for cluster in state["clusters"])


def live_marks(state: dict):
    """Where each unspent key is drawn, and which way its glyph reads."""
    out = []
    occupied = set()
    for piece in state["pieces"]:
        occupied.update(piece_cells(state, piece))
    for cluster in state["clusters"]:
        occupied.update(cluster["cells"])
    for mark in state["marks"]:
        if not mark["live"]:
            continue
        pa = piece_of_tile(state, mark["a"])
        pb = piece_of_tile(state, mark["b"])
        if pa < 0 or pb < 0 or pa == pb:
            continue
        ca = tile_cell(state, state["pieces"][pa], mark["a"])
        cb = tile_cell(state, state["pieces"][pb], mark["b"])
        dx, dy = cb[0] - ca[0], cb[1] - ca[1]
        if dx and dy:
            continue
        step = (1 if dx > 0 else -1 if dx < 0 else 0,
                1 if dy > 0 else -1 if dy < 0 else 0)
        gap = (ca[0] + step[0], ca[1] + step[1])
        if gap == cb:
            out.append(("seam", ca, cb, step, mark["icon"]))
        elif gap not in occupied:
            out.append(("glyph", ca, cb, step, mark["icon"]))
    return out


# =========================================================================
# rendering
# =========================================================================


def _sprite(pixels, name, x, y, layer, *, clickable=False):
    """Build a sprite with a FRESH tag list (Sprite's default is shared)."""
    return Sprite(
        pixels,
        name=name,
        x=x,
        y=y,
        layer=layer,
        interaction=(
            InteractionMode.TANGIBLE if clickable else InteractionMode.INTANGIBLE
        ),
        tags=["sys_click", CLICK_TAG] if clickable else [],
    )


def _panel_sprite():
    pixels = np.full((CELL, GRID * CELL), C_PANEL, dtype=np.int8)
    return _sprite(pixels, "panel", 0, HUD_ROW * CELL, LAYER_CHROME)


def _bezel_sprite():
    rows = (BEZEL_Y1 - BEZEL_Y0 + 1) * CELL
    pixels = np.full((rows, GRID * CELL), C_PANEL, dtype=np.int8)
    pixels[0, :] = C_FIELD  # a hairline seam where the field ends
    return _sprite(pixels, "bezel", 0, BEZEL_Y0 * CELL, LAYER_CHROME)


def _block_sprite(cells, color, name, layer, *, clickable=False):
    """One connected block of WHOLE logical cells in a single hue.

    Both role indices are painted through here and through nothing else,
    and nothing is ever drawn over a role cell, so the smallest painted
    component of `you` or `goal` is one full CELLxCELL logical cell.
    """
    x0 = min(c[0] for c in cells)
    y0 = min(c[1] for c in cells)
    width, height = _extent(cells)
    pixels = np.full((height * CELL, width * CELL), -1, dtype=np.int8)
    for cx, cy in cells:
        bx, by = (cx - x0) * CELL, (cy - y0) * CELL
        pixels[by : by + CELL, bx : bx + CELL] = color
    return _sprite(pixels, name, x0 * CELL, y0 * CELL, layer, clickable=clickable)


def _glyph_pixels(icon, step):
    """The keyed-edge glyph: a filled tab half against a hollow notch half.

    The icon shape (the glyph's thickness across the seam) is the key, and
    which half is filled says which side carries the tab.
    """
    thick = CELL if icon == 0 else CELL - 2
    pad = (CELL - thick) // 2
    half = CELL // 2
    # Canonical form: the partner lies to the RIGHT, so the near (left)
    # half is the filled tab and the far (right) half is its hollow twin.
    block = np.full((CELL, CELL), -1, dtype=np.int8)
    block[pad : pad + thick, 0:half] = C_INK
    block[pad : pad + thick, half:CELL] = C_INK
    if thick > 2:
        block[pad + 1 : pad + thick - 1, half : CELL - 1] = -1
    if step[0]:
        return np.ascontiguousarray(block if step[0] > 0 else block[:, ::-1])
    turned = block.T
    return np.ascontiguousarray(turned if step[1] > 0 else turned[::-1, :])


def _mark_sprite(cell, step, icon, name):
    pixels = _glyph_pixels(icon, step)
    return _sprite(pixels, name, cell[0] * CELL, cell[1] * CELL, LAYER_MARK)


def _seam_sprite(cell, step, icon, name):
    """A key whose two tiles already abut: a hairline on their shared edge.

    It is drawn inside the tile that is NOT painted in a role index, so a
    role cell is never carved.
    """
    length = CELL if icon == 0 else CELL - 2
    pad = (CELL - length) // 2
    if step[0]:
        pixels = np.full((length, 1), C_INK, dtype=np.int8)
        x = (cell[0] + 1) * CELL - 1 if step[0] > 0 else cell[0] * CELL
        return _sprite(pixels, name, x, cell[1] * CELL + pad, LAYER_MARK)
    pixels = np.full((1, length), C_INK, dtype=np.int8)
    y = (cell[1] + 1) * CELL - 1 if step[1] > 0 else cell[1] * CELL
    return _sprite(pixels, name, cell[0] * CELL + pad, y, LAYER_MARK)


def _flash_sprite(cell, role_cells, name):
    """knobs.refusal: visible — a ring AROUND the cell the refused click hit.

    The ring is drawn in the ring of cells surrounding the clicked one,
    never inside it, and it is dropped wherever it would land on a cell
    painted in a role hue.
    """
    span = 3 * CELL
    pixels = np.full((span, span), -1, dtype=np.int8)
    for index in (CELL - 1, 2 * CELL):
        pixels[index, CELL - 1 : 2 * CELL + 1] = C_HI
        pixels[CELL - 1 : 2 * CELL + 1, index] = C_HI
    ox, oy = cell[0] - 1, cell[1] - 1
    for py in range(span):
        for px in range(span):
            if pixels[py, px] == -1:
                continue
            if (ox + px // CELL, oy + py // CELL) in role_cells:
                pixels[py, px] = -1
    edge = GRID * CELL
    left, top = max(0, -ox * CELL), max(0, -oy * CELL)
    right = span - max(0, (ox + 3) * CELL - edge)
    bottom = span - max(0, (oy + 3) * CELL - edge)
    return _sprite(
        pixels[top:bottom, left:right],
        name,
        max(0, ox * CELL),
        max(0, oy * CELL),
        LAYER_FLASH,
    )


# =========================================================================
# the game
# =========================================================================


class SeamlockGame(ARCBaseGame):
    """Click-only keyed fusion: cover every outline with the shape it wants."""

    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed
        self._layout = build_layout(seed)
        self._board: dict = {}
        self._spent = 0
        self._flash = None
        super().__init__(
            game_id=GAME_ID,
            levels=[
                Level(name=f"seamlock-{entry['level']}", grid_size=(64, 64))
                for entry in self._layout
            ],
            camera=Camera(
                width=64, height=64, background=C_FIELD, letter_box=C_FIELD
            ),
            available_actions=[6],
        )

    # --- level lifecycle -------------------------------------------------

    def on_set_level(self, level: Level) -> None:
        self._board = init_state(self._layout[self.level_index])
        self._spent = 0
        self._flash = None
        self._paint(level)

    # --- the single operational rule -------------------------------------

    def step(self) -> None:
        level = self.current_level
        self._flash = None

        clicked = self._clicked_cell()
        if clicked is None:
            self._paint(level)
            self.complete_action()
            return

        cell, index = clicked
        outcome = resolve_click(self._board, cell, index)
        if outcome["kind"] == "refuse":
            # knobs.refusal: visible — every refusal rings the cell it
            # landed on, in this action's own settled frame, and every
            # refusal is FREE. Only a fusion or a stamp is ever charged.
            self._flash = cell
            self._paint(level)
            self.complete_action()
            return

        self._spent += 1
        self._paint(level)
        if is_won(self._board):
            self.next_level()
        elif self._spent >= self._board["cap"]:
            self.lose()
        self.complete_action()

    def _clicked_cell(self):
        if self.action.id is not GameAction.ACTION6:
            return None
        data = self.action.data or {}
        sx, sy = data.get("x"), data.get("y")
        if sx is None or sy is None:
            return None
        spot = self.camera.display_to_grid(int(sx), int(sy))
        if spot is None:
            return None
        # Route the click through the tagged sprite the engine advertises,
        # so the click list and the handler read the same object. Every
        # clickable sprite carries the "piece" tag and nothing else does, so
        # a hit here IS a tile; a miss still resolves, as the first refusal
        # branch, which is free.
        hit = self.current_level.get_sprite_at(spot[0], spot[1], "piece")
        return (spot[0] // CELL, spot[1] // CELL), self._piece_of_sprite(hit)

    def _piece_of_sprite(self, hit) -> int:
        """Which piece a clicked sprite IS — the engine's object, not a box.

        Every sprite the engine advertises carries the "piece" tag and is
        named piece<N> for its index on the board, so the handler acts on
        exactly the object the click list named. No tagged sprite under the
        pixel -> -1, which is branch 1's empty-cell refusal.
        """
        if hit is None or "piece" not in (getattr(hit, "tags", None) or []):
            return -1
        name = getattr(hit, "name", "") or ""
        digits = name[len("piece"):]
        if not name.startswith("piece") or not digits.isdigit():
            return -1
        index = int(digits)
        return index if index < len(self._board["pieces"]) else -1

    # --- rendering -------------------------------------------------------

    def _paint(self, level: Level) -> None:
        level.remove_all_sprites()
        level.add_sprite(_panel_sprite())
        level.add_sprite(_bezel_sprite())

        role_cells = set()
        for number, cluster in enumerate(self._board["clusters"]):
            hue = C_LOCKED if cluster["covered"] else C_GOAL
            if not cluster["covered"]:
                role_cells.update(cluster["cells"])
            level.add_sprite(
                _block_sprite(cluster["cells"], hue, f"cluster{number}", LAYER_GOAL)
            )

        for number, piece in enumerate(self._board["pieces"]):
            cells = piece_cells(self._board, piece)
            single = len(piece["tiles"]) == 1
            hue = C_YOU if single else self._board["tiles"][piece["tiles"][0]]["hue"]
            if single:
                role_cells.update(cells)
            level.add_sprite(
                _block_sprite(
                    cells, hue, f"piece{number}", LAYER_TILE, clickable=True
                )
            )

        for number, (kind, ca, cb, step, icon) in enumerate(
            live_marks(self._board)
        ):
            name = f"key{number}"
            if kind == "glyph":
                spot = (ca[0] + step[0], ca[1] + step[1])
                level.add_sprite(_mark_sprite(spot, step, icon, name))
            elif ca not in role_cells:
                level.add_sprite(_seam_sprite(ca, step, icon, name))
            elif cb not in role_cells:
                back = (-step[0], -step[1])
                level.add_sprite(_seam_sprite(cb, back, icon, name))

        if self._flash is not None:
            level.add_sprite(_flash_sprite(self._flash, role_cells, "refusal"))

        self._paint_meter(level)

    def _paint_meter(self, level: Level) -> None:
        """Edge-anchored linear budget strip across the reserved top row."""
        cap = max(1, self._board["cap"])
        left = max(0, cap - self._spent)
        width = GRID * CELL - 2
        filled = (left * width + cap - 1) // cap
        strip = np.full((2, width), C_PANEL, dtype=np.int8)
        if filled:
            strip[:, :filled] = C_HI
        level.add_sprite(_sprite(strip, "meter", 1, 1, LAYER_HUD))
