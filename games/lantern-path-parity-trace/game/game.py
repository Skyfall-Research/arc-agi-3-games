"""Lantern Path: trace the pictured target without lighting dark floor."""

from __future__ import annotations

import hashlib

import numpy as np
from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

GAME_ID = "lantern-path-parity-trace"
DEFAULT_LAYOUT_SEED = 173
LAYOUT_NAMESPACE = f"{GAME_ID}/layout/v2"
LEVEL_COUNT = 8

LOGICAL_WIDTH = 16
LOGICAL_HEIGHT = 14
BOARD_WIDTH = 10
BOARD_HEIGHT = 13
CELL_PX = 4
HUD_Y = 52

WHITE = 0
ILLEGAL_DULL = 1
FLOOR = 2
PANEL = 3
WALL = 4
BLACK = 5
MAGENTA = 6
BALANCE_MARK = 7
BALANCE_FILL = 8
TARGET_BLUE = 10
YELLOW = 11
WARM = 12

Coord = tuple[int, int]


def _perimeter(x0: int, x1: int, y0: int, y1: int) -> set[Coord]:
    cells = {(x, y0) for x in range(x0, x1 + 1)}
    cells.update((x, y1) for x in range(x0, x1 + 1))
    cells.update((x0, y) for y in range(y0, y1 + 1))
    cells.update((x1, y) for y in range(y0, y1 + 1))
    return cells


def _mirror(cells: set[Coord]) -> set[Coord]:
    return {(BOARD_WIDTH - 1 - x, y) for x, y in cells}


def _neighbors(cell: Coord) -> tuple[Coord, Coord, Coord, Coord]:
    x, y = cell
    return ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y))


def _open_floor(target: set[Coord], extras: set[Coord] | None = None) -> set[Coord]:
    walk = set(target)
    for cell in target:
        walk.update(_neighbors(cell))
    if extras is not None:
        walk.update(extras)
    return {
        (x, y)
        for x, y in walk
        if 0 <= x < BOARD_WIDTH and 0 <= y < BOARD_HEIGHT
    }


def _cover_walk(start: Coord, target: set[Coord]) -> list[Coord]:
    visited: set[Coord] = set()
    route: list[Coord] = []

    def visit(cell: Coord) -> None:
        visited.add(cell)
        for nxt in sorted(_neighbors(cell), key=lambda point: (point[1], point[0])):
            if nxt in target and nxt not in visited:
                route.append(nxt)
                visit(nxt)
                route.append(cell)

    visit(start)
    if visited != target:
        raise ValueError("generated target is disconnected")
    return route


def _target_degrees(target: set[Coord]) -> dict[Coord, int]:
    return {
        cell: sum(neighbor in target for neighbor in _neighbors(cell))
        for cell in target
    }


def _cycle_rank(target: set[Coord]) -> int:
    edge_count = sum(_target_degrees(target).values()) // 2
    return edge_count - len(target) + 1


def _component_count(cells: set[Coord]) -> int:
    remaining = set(cells)
    count = 0
    while remaining:
        count += 1
        stack = [remaining.pop()]
        while stack:
            cell = stack.pop()
            adjacent = remaining.intersection(_neighbors(cell))
            remaining.difference_update(adjacent)
            stack.extend(adjacent)
    return count


def _has_balanced_articulation(target: set[Coord], minimum_side: int) -> bool:
    for cell in target:
        remainder = target - {cell}
        if _component_count(remainder) != 2:
            continue
        first = next(iter(remainder))
        reached = {first}
        stack = [first]
        while stack:
            current = stack.pop()
            for neighbor in _neighbors(current):
                if neighbor in remainder and neighbor not in reached:
                    reached.add(neighbor)
                    stack.append(neighbor)
        if min(len(reached), len(remainder) - len(reached)) >= minimum_side:
            return True
    return False


def _level_one(variant: int) -> tuple[set[Coord], set[Coord], Coord]:
    y0 = 2 + ((variant >> 1) & 1)
    elbow_x = 5 + ((variant >> 2) & 1)
    target = {(x, y0) for x in range(1, elbow_x + 1)}
    target.update({(elbow_x, y0 + 1), (elbow_x, y0 + 2)})
    target.update({(elbow_x - 1, y0 + 2), (elbow_x - 2, y0 + 2)})
    start = (1, y0)
    if variant & 1:
        target = _mirror(target)
        start = (BOARD_WIDTH - 1 - start[0], start[1])
    return target, _open_floor(target), start


def _level_two(variant: int) -> tuple[set[Coord], set[Coord], Coord]:
    y = 7 + ((variant >> 2) & 1)
    short_x, long_x = ((4, 7) if not (variant & 2) else (6, 3))
    target = {(x, y) for x in range(1, 8)}
    target.update((short_x, y - depth) for depth in range(1, 3))
    target.update((long_x, y - depth) for depth in range(1, 4))
    start = (1, y)
    if variant & 1:
        target = _mirror(target)
        start = (BOARD_WIDTH - 1 - start[0], start[1])
    return target, _open_floor(target), start


def _level_three(variant: int) -> tuple[set[Coord], set[Coord], Coord]:
    y = 6 + ((variant >> 1) & 1)
    left = {(1, y), (2, y), (3, y), (2, y - 1), (2, y - 2), (3, y + 1)}
    right = {(5, y), (6, y), (7, y), (6, y - 1), (6, y - 2), (7, y + 1)}
    target = left | {(4, y)} | right
    start = (1, y)
    if variant & 1:
        target = _mirror(target)
        start = (BOARD_WIDTH - 1 - start[0], start[1])
    return target, _open_floor(target), start


def _level_four(variant: int) -> tuple[set[Coord], set[Coord], Coord]:
    top = 2 + ((variant >> 2) & 1)
    bottom = top + 6
    target = _perimeter(2, 7, top, bottom)
    left_y, right_y = ((top + 2, top + 4) if not (variant & 2) else (top + 3, top + 2))
    target.update({(1, left_y), (0, left_y)})
    target.update({(8, right_y), (9, right_y)})
    start = (2, top)
    if variant & 1:
        target = _mirror(target)
        start = (BOARD_WIDTH - 1 - start[0], start[1])
    return target, _open_floor(target), start


def _level_five(variant: int) -> tuple[set[Coord], set[Coord], Coord]:
    target = _perimeter(1, 8, 1, 8)
    stem_x = 4 if not (variant & 2) else 5
    target.update({(stem_x, 9), (stem_x, 10), (stem_x, 11)})
    target.update({(stem_x - 1, 10), (stem_x - 2, 10)})
    target.update({(stem_x + 1, 11), (stem_x + 2, 11), (stem_x + 3, 11)})
    bay_y = 3 if not (variant & 4) else 5
    target.add((0, bay_y))
    start = (stem_x, 8)
    if variant & 1:
        target = _mirror(target)
        start = (BOARD_WIDTH - 1 - start[0], start[1])
    return target, _open_floor(target), start


def _level_six(variant: int) -> tuple[set[Coord], set[Coord], Coord]:
    upper_top = 0 if variant & 4 else 1
    lower_bottom = 10 if variant & 2 else 9
    upper = _perimeter(1, 5, upper_top, 5)
    lower = _perimeter(5, 9, 5, lower_bottom)
    target = upper | lower
    target.add((0, upper_top + 2))
    target.update({(3, 6), (3, 7)})
    target.update({(7, 4), (7, 3)})
    target.update({(8, lower_bottom + 1), (8, lower_bottom + 2)})
    start = (1, upper_top)
    if variant & 1:
        target = _mirror(target)
        start = (BOARD_WIDTH - 1 - start[0], start[1])
    return target, _open_floor(target), start


def _level_seven(variant: int) -> tuple[set[Coord], set[Coord], Coord]:
    outer_y = 1 + ((variant >> 1) & 1)
    shortcut_y = 6 + ((variant >> 2) & 1)
    left = {(1, shortcut_y), (2, shortcut_y), (2, shortcut_y - 1), (1, shortcut_y + 1)}
    right = {(7, shortcut_y), (8, shortcut_y), (7, shortcut_y - 1), (8, shortcut_y + 1)}
    outer = {(2, y) for y in range(outer_y, shortcut_y)}
    outer.update((x, outer_y) for x in range(2, 8))
    outer.update((7, y) for y in range(outer_y + 1, shortcut_y))
    target = left | outer | right
    shortcut = {(x, shortcut_y) for x in range(3, 7)}
    start = (1, shortcut_y + 1)
    if variant & 1:
        target = _mirror(target)
        shortcut = _mirror(shortcut)
        start = (BOARD_WIDTH - 1 - start[0], start[1])
    return target, _open_floor(target, shortcut), start


def _level_eight(variant: int) -> tuple[set[Coord], set[Coord], Coord]:
    upper_top = 0 if variant & 4 else 1
    lower_bottom = 10 if variant & 2 else 9
    upper = _perimeter(2, 6, upper_top, 5)
    lower = _perimeter(6, 9, 5, lower_bottom)
    detour = {(0, y) for y in range(upper_top + 2, lower_bottom)}
    detour.add((1, upper_top + 2))
    detour.update((x, lower_bottom - 1) for x in range(1, 7))
    upper_bay = {(7, upper_top + 2), (8, upper_top + 2)}
    lower_bay_x = 7 if variant & 2 else 8
    lower_bay = {(lower_bay_x, lower_bottom + 1), (lower_bay_x, lower_bottom + 2)}
    target = upper | lower | detour | upper_bay | lower_bay
    shortcut = {(4, 6), (4, 7), (4, 8)} - target
    start = max(lower_bay, key=lambda cell: cell[1])
    if variant & 1:
        target = _mirror(target)
        shortcut = _mirror(shortcut)
        start = (BOARD_WIDTH - 1 - start[0], start[1])
    return target, _open_floor(target, shortcut), start


LEVEL_BUILDERS = (
    _level_one,
    _level_two,
    _level_three,
    _level_four,
    _level_five,
    _level_six,
    _level_seven,
    _level_eight,
)


def _verify_layout(level_number: int, target: set[Coord], walk: set[Coord], start: Coord) -> None:
    if start not in target or not target <= walk:
        raise ValueError(f"invalid masks in level {level_number}")
    if not walk - target:
        raise ValueError(f"level {level_number} needs visible non-target floor")
    if any(not (0 <= x < BOARD_WIDTH and 0 <= y < BOARD_HEIGHT) for x, y in walk):
        raise ValueError(f"out-of-bounds cell in level {level_number}")
    _cover_walk(start, target)

    degrees = _target_degrees(target)
    leaf_count = sum(degree == 1 for degree in degrees.values())
    cycle_rank = _cycle_rank(target)
    if level_number == 1 and not (
        cycle_rank == 0 and leaf_count == 2 and max(degrees.values()) == 2
    ):
        raise ValueError("level 1 must remain a single hook path")
    if level_number == 2 and not (
        cycle_rank == 0 and leaf_count in (3, 4) and max(degrees.values()) == 3
    ):
        raise ValueError("level 2 must remain a two-tooth comb")
    if level_number == 3 and not (
        cycle_rank == 0 and _has_balanced_articulation(target, minimum_side=5)
    ):
        raise ValueError("level 3 must retain one-cell access between two lobes")
    if level_number == 4 and not (cycle_rank == 1 and leaf_count == 2):
        raise ValueError("level 4 must retain one ring and two bays")
    if level_number == 5 and not (cycle_rank == 1 and leaf_count == 3):
        raise ValueError("level 5 must retain its ring, comb, and bay")
    if level_number == 6 and not (cycle_rank == 2 and leaf_count == 4):
        raise ValueError("level 6 must retain two loops and four bays")
    if level_number == 7 and not (
        cycle_rank == 0 and leaf_count == 2
    ):
        raise ValueError("level 7 must retain its legal outer route and shortcut")
    if level_number == 8 and not (cycle_rank == 3 and leaf_count == 2):
        raise ValueError("level 8 must retain its mural loops, detour, and bays")


def build_layout(seed: int) -> list[dict[str, object]]:
    """Build all seeded structural variants as pure JSON-able data."""
    seed = int(seed)
    layout: list[dict[str, object]] = []
    for index, builder in enumerate(LEVEL_BUILDERS):
        digest = hashlib.sha256(f"{LAYOUT_NAMESPACE}:{seed}:{index}".encode()).digest()
        variant = digest[0] & 7
        target, walk, start = builder(variant)
        level_number = index + 1
        _verify_layout(level_number, target, walk, start)
        solver_route = _cover_walk(start, target)
        cap = max(30, 15 * len(solver_route))
        layout.append(
            {
                "level": level_number,
                "variant": variant,
                "start": list(start),
                "target": [list(cell) for cell in sorted(target)],
                "walk": [list(cell) for cell in sorted(walk)],
                "cap": cap,
            }
        )
    return layout


def _level(entry: dict[str, object]) -> Level:
    pixels = np.full((64, 64), BLACK, dtype=np.int8)
    display = Sprite(pixels, name="display", x=0, y=0, layer=10, collidable=False)
    return Level(
        sprites=[display],
        grid_size=(64, 64),
        data=dict(entry),
        name=f"Level {entry['level']}",
    )


class Game(ARCBaseGame):
    """The single-mover Lantern Path implementation."""

    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed
        self._layout = build_layout(seed)
        self.lantern_xy: Coord = (0, 0)
        self.walk_mask: set[Coord] = set()
        self.target_mask: set[Coord] = set()
        self.lit_mask: set[Coord] = set()
        self.budget_cap = 0
        self.budget_remaining = 0
        self.refusal_edge: str | None = None
        self._display: Sprite | None = None
        super().__init__(
            game_id=GAME_ID,
            levels=[_level(entry) for entry in self._layout],
            camera=Camera(width=64, height=64, background=BLACK, letter_box=BLACK),
            available_actions=[1, 2, 3, 4],
        )

    def on_set_level(self, level: Level) -> None:
        self.lantern_xy = tuple(level.get_data("start"))
        self.walk_mask = {tuple(cell) for cell in level.get_data("walk")}
        self.target_mask = {tuple(cell) for cell in level.get_data("target")}
        self.lit_mask = {self.lantern_xy}
        self.budget_cap = int(level.get_data("cap"))
        self.budget_remaining = self.budget_cap
        self.refusal_edge = None
        self._display = level.get_sprites_by_name("display")[0]
        self._refresh_frame()

    @staticmethod
    def _paint_cell(frame: np.ndarray, cell: Coord, color: int) -> None:
        x, y = cell
        x0 = x * CELL_PX
        y0 = y * CELL_PX
        frame[y0 : y0 + CELL_PX, x0 : x0 + CELL_PX] = color

    def _paint_lantern(self, frame: np.ndarray) -> None:
        x, y = self.lantern_xy
        x0 = x * CELL_PX
        y0 = y * CELL_PX
        bx0 = max(0, x0 - 2)
        by0 = max(0, y0 - 2)
        bx1 = min(BOARD_WIDTH * CELL_PX, x0 + 6)
        by1 = min(HUD_Y, y0 + 6)
        frame[by0:by1, bx0:bx1] = WALL
        frame[y0 : y0 + CELL_PX, x0 : x0 + CELL_PX] = YELLOW

    def _paint_refusal(self, frame: np.ndarray) -> None:
        if self.refusal_edge is None:
            return
        x, y = self.lantern_xy
        x0 = x * CELL_PX
        y0 = y * CELL_PX
        if self.refusal_edge == "up":
            frame[max(0, y0 - 2) : y0, x0 : x0 + CELL_PX] = MAGENTA
        elif self.refusal_edge == "down":
            frame[y0 + CELL_PX : min(HUD_Y, y0 + 6), x0 : x0 + CELL_PX] = MAGENTA
        elif self.refusal_edge == "left":
            frame[y0 : y0 + CELL_PX, max(0, x0 - 2) : x0] = MAGENTA
        else:
            frame[y0 : y0 + CELL_PX, x0 + CELL_PX : min(40, x0 + 6)] = MAGENTA

    def _refresh_frame(self) -> None:
        frame = np.full((64, 64), BLACK, dtype=np.int8)
        frame[:HUD_Y, :40] = WALL
        frame[:HUD_Y, 40:44] = BLACK
        frame[:HUD_Y, 44:64] = PANEL

        for cell in self.walk_mask:
            self._paint_cell(frame, cell, FLOOR)
        for cell in self.target_mask:
            self._paint_cell(frame, cell, TARGET_BLUE)
        for cell in self.lit_mask:
            color = WARM if cell in self.target_mask else ILLEGAL_DULL
            self._paint_cell(frame, cell, color)

        for x, y in self.target_mask:
            px = 44 + x * 2
            py = 13 + y * 2
            frame[py : py + 2, px : px + 2] = TARGET_BLUE

        self._paint_lantern(frame)
        self._paint_refusal(frame)

        frame[52:56, :] = WALL
        frame[53:55, 1:40] = FLOOR
        budget_width = round(39 * self.budget_remaining / max(1, self.budget_cap))
        frame[53:55, 1 : 1 + budget_width] = WHITE

        left_lit = sum(x < BOARD_WIDTH // 2 for x, _ in self.lit_mask & self.target_mask)
        right_lit = sum(x >= BOARD_WIDTH // 2 for x, _ in self.lit_mask & self.target_mask)
        frame[53:55, 44:63] = FLOOR
        frame[53:55, 53:55] = BALANCE_MARK
        difference = min(8, abs(left_lit - right_lit))
        if left_lit > right_lit:
            frame[53:55, 53 - difference : 53] = BALANCE_FILL
        elif right_lit > left_lit:
            frame[53:55, 55 : 55 + difference] = BALANCE_FILL

        frame[56:58, :] = WALL
        if self._display is not None:
            self._display.pixels = frame

    def step(self) -> None:
        directions = {
            GameAction.ACTION1: (0, -1, "up"),
            GameAction.ACTION2: (0, 1, "down"),
            GameAction.ACTION3: (-1, 0, "left"),
            GameAction.ACTION4: (1, 0, "right"),
        }
        direction = directions.get(self.action.id)
        if direction is None:
            self.complete_action()
            return

        dx, dy, edge = direction
        destination = (self.lantern_xy[0] + dx, self.lantern_xy[1] + dy)
        self.refusal_edge = None
        if destination not in self.walk_mask:
            self.refusal_edge = edge
            self._refresh_frame()
            self.complete_action()
            return

        self.lantern_xy = destination
        self.lit_mask.add(destination)
        solved = self.lit_mask == self.target_mask
        if not solved:
            self.budget_remaining -= 1
        self._refresh_frame()

        if solved:
            self.next_level()
        elif self.budget_remaining <= 0:
            self.lose()
        self.complete_action()
