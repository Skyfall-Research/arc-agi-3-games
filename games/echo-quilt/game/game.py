"""Echo Quilt: coupled polyomino translation on a seeded 16x16 lattice."""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Iterable
from itertools import pairwise

import numpy as np
from arcengine import ARCBaseGame, Camera, GameAction, Level, Sprite

GAME_ID = "echo-quilt"
DEFAULT_LAYOUT_SEED = 46127
LAYOUT_NAMESPACE = "echo-quilt/layout/v1"
LEVEL_COUNT = 7
GRID_SIZE = 16
CELL_PX = 4

BACKGROUND = 5
WALL = 4
REFUSAL = 2
CHROME = 1
TARGET = 11
COMPLETE = 14
SELECTED = 0
TRANSPARENT = -1

DIRECTIONS = {
    1: (0, -1),
    2: (0, 1),
    3: (-1, 0),
    4: (1, 0),
}

SHAPES = {
    "square": ((0, 0), (1, 0), (0, 1), (1, 1)),
    "wide": ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)),
    "tall": ((0, 0), (1, 0), (0, 1), (1, 1), (0, 2), (1, 2)),
    "ell": ((0, 0), (1, 0), (0, 1), (0, 2)),
}

PAIR_COLORS = ((9, 10), (6, 7), (12, 13), (15, 3))


def _cells(shape: str, origin: tuple[int, int]) -> list[list[int]]:
    ox, oy = origin
    return [[ox + dx, oy + dy] for dx, dy in SHAPES[shape]]


def _shift(cells: Iterable[Iterable[int]], dx: int, dy: int) -> list[list[int]]:
    return [[int(x) + dx, int(y) + dy] for x, y in cells]


def _transform_cell(x: int, y: int, rotation: int, reflect: bool) -> tuple[int, int]:
    if reflect:
        x = GRID_SIZE - 1 - x
    for _ in range(rotation % 4):
        x, y = GRID_SIZE - 1 - y, x
    return x, y


def _transform_cells(
    cells: Iterable[Iterable[int]], rotation: int, reflect: bool
) -> list[list[int]]:
    return [list(_transform_cell(int(x), int(y), rotation, reflect)) for x, y in cells]


def _connected(cells: set[tuple[int, int]]) -> bool:
    if not cells:
        return False
    seen = {next(iter(cells))}
    queue = deque(seen)
    while queue:
        x, y = queue.popleft()
        for dx, dy in DIRECTIONS.values():
            neighbor = (x + dx, y + dy)
            if neighbor in cells and neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return seen == cells


def _pair(
    pair_id: int,
    shape: str,
    target_block: tuple[int, int],
    target_echo: tuple[int, int],
    start_delta: tuple[int, int],
) -> dict:
    block_target = _cells(shape, target_block)
    echo_target = _cells(shape, target_echo)
    dx, dy = start_delta
    block = _shift(block_target, dx, dy)
    echo = _shift(echo_target, dx, dy)
    color, echo_color = PAIR_COLORS[pair_id]
    return {
        "id": pair_id,
        "shape": shape,
        "block_cells": block,
        "echo_cells": echo,
        "target_block": block_target,
        "target_echo": echo_target,
        "color": color,
        "echo_color": echo_color,
    }


def _anchor_level(index: int) -> dict:
    """Return the authored anchor for one curriculum step.

    The seven anchors keep the declared pair counts and silhouettes. Later
    levels compose more independently movable pairs into one connected quilt.
    """
    anchors = [
        {
            "title": "First Stitch",
            "relation": "new",
            "pairs": [_pair(0, "square", (6, 5), (6, 7), (-4, 0))],
            "walls": [[4, 5]],
        },
        {
            "title": "Choose The Thread",
            "relation": "reuse",
            "pairs": [
                _pair(0, "square", (5, 6), (5, 8), (-3, 0)),
                _pair(1, "wide", (7, 6), (7, 8), (0, -4)),
            ],
            "walls": [],
        },
        {
            "title": "Cross-Stitch Junction",
            "relation": "compose",
            "pairs": [
                _pair(0, "square", (4, 5), (4, 7), (-3, 0)),
                _pair(1, "tall", (6, 5), (8, 5), (0, -4)),
                _pair(2, "ell", (6, 8), (8, 8), (3, 0)),
            ],
            "walls": [],
        },
        {
            "title": "Borrowed Seam",
            "relation": "invert",
            "pairs": [
                _pair(0, "square", (5, 6), (5, 8), (-3, 0)),
                _pair(1, "wide", (7, 6), (7, 8), (0, -4)),
            ],
            "walls": [],
        },
        {
            "title": "Pinwheel Reserve",
            "relation": "reuse",
            "pairs": [
                _pair(0, "square", (4, 5), (4, 7), (-3, 0)),
                _pair(1, "tall", (6, 5), (8, 5), (0, -4)),
                _pair(2, "ell", (6, 8), (8, 8), (3, 0)),
                _pair(3, "wide", (4, 11), (7, 11), (0, 2)),
            ],
            "walls": [],
        },
        {
            "title": "Split Binding",
            "relation": "compose",
            "pairs": [
                _pair(0, "square", (4, 5), (4, 7), (-3, 0)),
                _pair(1, "square", (6, 5), (8, 5), (0, -4)),
                _pair(2, "wide", (6, 8), (9, 8), (3, 0)),
            ],
            "walls": [],
        },
        {
            "title": "Closed Quilt",
            "relation": "compose",
            "pairs": [
                _pair(0, "square", (4, 5), (4, 7), (-3, 0)),
                _pair(1, "tall", (6, 5), (8, 5), (0, -4)),
                _pair(2, "ell", (6, 8), (8, 8), (3, 0)),
                _pair(3, "wide", (4, 11), (7, 11), (0, 2)),
            ],
            "walls": [],
        },
    ]
    return anchors[index]


def build_layout(seed: int) -> list:
    """Build seven pure, JSON-able structural variants from ``seed``."""
    seed = int(seed)
    layout = []
    for index in range(LEVEL_COUNT):
        digest = hashlib.sha256(
            f"{LAYOUT_NAMESPACE}:{seed}:{index}".encode()
        ).digest()
        anchor = _anchor_level(index)
        rotation = digest[0] % 4
        reflect = bool(digest[1] & 1)
        pairs = []
        for pair in anchor["pairs"]:
            transformed = dict(pair)
            for key in ("block_cells", "echo_cells", "target_block", "target_echo"):
                transformed[key] = _transform_cells(pair[key], rotation, reflect)
            pairs.append(transformed)

        walls = _transform_cells(anchor["walls"], rotation, reflect)
        occupied = {
            tuple(cell)
            for pair in pairs
            for key in ("block_cells", "echo_cells", "target_block", "target_echo")
            for cell in pair[key]
        }
        swept = set(occupied)
        for pair in pairs:
            for start_key, target_key in (
                ("block_cells", "target_block"),
                ("echo_cells", "target_echo"),
            ):
                start = pair[start_key]
                target = pair[target_key]
                min_x = min(x for x, _ in start + target)
                max_x = max(x for x, _ in start + target)
                min_y = min(y for _, y in start + target)
                max_y = max(y for _, y in start + target)
                swept.update(
                    (x, y)
                    for y in range(min_y, max_y + 1)
                    for x in range(min_x, max_x + 1)
                )
        # Seeded wall teeth make layouts bytewise and structurally distinct.
        candidates = [
            (x, y)
            for y in range(1, 15)
            for x in range(1, 15)
            if (x, y) not in swept
        ]
        for offset in range(8):
            choice = candidates[(digest[2 + offset] + 17 * offset) % len(candidates)]
            if list(choice) not in walls:
                walls.append(list(choice))

        targets = {
            tuple(cell)
            for pair in pairs
            for key in ("target_block", "target_echo")
            for cell in pair[key]
        }
        if not _connected(targets):
            raise ValueError(f"authored target seam is disconnected at level {index + 1}")

        optimal_hint = sum(
            abs(pair["target_block"][0][0] - pair["block_cells"][0][0])
            + abs(pair["target_block"][0][1] - pair["block_cells"][0][1])
            for pair in pairs
        ) + max(0, len(pairs) - 1)
        layout.append(
            {
                "level": index + 1,
                "title": anchor["title"],
                "relation": anchor["relation"],
                "rotation": rotation,
                "reflected": reflect,
                "walls": sorted(walls),
                "pairs": pairs,
                "selected": 0,
                "cap": max(30, 15 * (optimal_hint + 8)),
            }
        )
    return layout


def _level(entry: dict) -> Level:
    sprites = [
        Sprite(
            np.full((64, 64), BACKGROUND, dtype=np.int8),
            name="terrain_layer",
            layer=0,
            collidable=False,
        )
    ]
    for layer, name in enumerate(
        ("target_layer", "piece_layer", "marker_layer", "hud_layer"), start=1
    ):
        sprites.append(
            Sprite(
                np.full((64, 64), TRANSPARENT, dtype=np.int8),
                name=name,
                layer=layer,
                collidable=False,
            )
        )
    return Level(
        sprites=sprites,
        grid_size=(64, 64),
        data={"layout": entry},
        name=entry["title"],
    )


class Game(ARCBaseGame):
    """The single Echo Quilt game implementation."""

    def __init__(self, layout_seed: int | None = None) -> None:
        seed = DEFAULT_LAYOUT_SEED if layout_seed is None else int(layout_seed)
        self.layout_seed = seed
        self._layout = build_layout(seed)
        self._pairs: list[dict] = []
        self._terrain: set[tuple[int, int]] = set()
        self._targets: set[tuple[int, int]] = set()
        self._selected = 0
        self._refusal: set[tuple[int, int]] = set()
        self._counted_actions = 0
        self._budget_cap = 0
        self._solved = False
        super().__init__(
            game_id=GAME_ID,
            levels=[_level(entry) for entry in self._layout],
            camera=Camera(width=64, height=64, background=BACKGROUND),
            available_actions=[1, 2, 3, 4, 5],
        )

    def on_set_level(self, level: Level) -> None:
        entry = level.get_data("layout")
        self._pairs = [
            {
                **pair,
                "block_cells": {tuple(cell) for cell in pair["block_cells"]},
                "echo_cells": {tuple(cell) for cell in pair["echo_cells"]},
            }
            for pair in entry["pairs"]
        ]
        self._terrain = {tuple(cell) for cell in entry["walls"]}
        self._targets = {
            tuple(cell)
            for pair in entry["pairs"]
            for key in ("target_block", "target_echo")
            for cell in pair[key]
        }
        self._selected = int(entry["selected"])
        self._refusal = set()
        self._counted_actions = 0
        self._budget_cap = int(entry["cap"])
        self._solved = False
        self._render_board()

    def _all_piece_cells(self, except_pair: int | None = None) -> set[tuple[int, int]]:
        return {
            cell
            for index, pair in enumerate(self._pairs)
            if index != except_pair
            for key in ("block_cells", "echo_cells")
            for cell in pair[key]
        }

    def _try_translate(self, dx: int, dy: int) -> bool:
        pair = self._pairs[self._selected]
        moved_block = {(x + dx, y + dy) for x, y in pair["block_cells"]}
        moved_echo = {(x + dx, y + dy) for x, y in pair["echo_cells"]}
        destinations = moved_block | moved_echo
        blockers = self._terrain | self._all_piece_cells(self._selected)
        invalid = {
            cell
            for cell in destinations
            if not (0 <= cell[0] < GRID_SIZE and 0 <= cell[1] < GRID_SIZE)
            or cell in blockers
        }
        if moved_block & moved_echo:
            invalid |= moved_block & moved_echo
        if invalid:
            self._refusal = {
                (min(15, max(0, x)), min(15, max(0, y))) for x, y in invalid
            }
            return False
        pair["block_cells"] = moved_block
        pair["echo_cells"] = moved_echo
        self._refusal = set()
        return True

    def _is_complete(self) -> bool:
        occupied = self._all_piece_cells()
        covered_targets = occupied & self._targets
        return covered_targets == self._targets and _connected(self._targets)

    @staticmethod
    def _paint_cells(frame: np.ndarray, cells: Iterable[tuple[int, int]], color: int) -> None:
        for x, y in cells:
            x0, y0 = x * CELL_PX, y * CELL_PX
            frame[y0 : y0 + CELL_PX, x0 : x0 + CELL_PX] = color

    @staticmethod
    def _paint_piece(
        frame: np.ndarray,
        cells: set[tuple[int, int]],
        color: int,
        target_cells: set[tuple[int, int]],
        rim_color: int,
    ) -> None:
        for x, y in cells:
            x0, y0 = x * CELL_PX, y * CELL_PX
            frame[y0 : y0 + CELL_PX, x0 : x0 + CELL_PX] = color
        for x, y in cells & target_cells:
            x0, y0 = x * CELL_PX, y * CELL_PX
            if (x - 1, y) not in cells:
                frame[y0 : y0 + CELL_PX, x0] = rim_color
            if (x + 1, y) not in cells:
                frame[y0 : y0 + CELL_PX, x0 + CELL_PX - 1] = rim_color
            if (x, y - 1) not in cells:
                frame[y0, x0 : x0 + CELL_PX] = rim_color
            if (x, y + 1) not in cells:
                frame[y0 + CELL_PX - 1, x0 : x0 + CELL_PX] = rim_color

    def _selection_band(self) -> set[tuple[int, int]]:
        cells = self._pairs[self._selected]["block_cells"]
        for y in sorted({cell[1] for cell in cells}):
            xs = sorted(x for x, cy in cells if cy == y)
            for left, right in pairwise(xs):
                if right == left + 1:
                    return {(left, y), (right, y)}
        return set(sorted(cells)[:2])

    def _render_board(self) -> None:
        terrain = np.full((64, 64), BACKGROUND, dtype=np.int8)
        targets = np.full((64, 64), TRANSPARENT, dtype=np.int8)
        pieces = np.full((64, 64), TRANSPARENT, dtype=np.int8)
        markers = np.full((64, 64), TRANSPARENT, dtype=np.int8)
        hud = np.full((64, 64), TRANSPARENT, dtype=np.int8)
        self._paint_cells(terrain, self._terrain, WALL)
        self._paint_cells(targets, self._targets, COMPLETE if self._solved else TARGET)
        rim = COMPLETE if self._solved else TARGET
        for pair in self._pairs:
            self._paint_piece(
                pieces, pair["block_cells"], pair["color"], self._targets, rim
            )
            self._paint_piece(
                pieces, pair["echo_cells"], pair["echo_color"], self._targets, rim
            )
        self._paint_cells(markers, self._selection_band(), SELECTED)

        for x, y in self._refusal:
            x0, y0 = x * CELL_PX, y * CELL_PX
            markers[y0, x0 : x0 + CELL_PX] = REFUSAL
            markers[y0 + CELL_PX - 1, x0 : x0 + CELL_PX] = REFUSAL
            markers[y0 : y0 + CELL_PX, x0] = REFUSAL
            markers[y0 : y0 + CELL_PX, x0 + CELL_PX - 1] = REFUSAL

        hud[0, :] = CHROME
        hud[:, 0] = CHROME
        hud[:, 63] = CHROME
        hud[62, :] = CHROME
        hud[63, :] = BACKGROUND
        hud[63, : min(63, self._counted_actions)] = SELECTED
        for name, pixels in (
            ("terrain_layer", terrain),
            ("target_layer", targets),
            ("piece_layer", pieces),
            ("marker_layer", markers),
            ("hud_layer", hud),
        ):
            self.current_level.get_sprites_by_name(name)[0].pixels = pixels

    def step(self) -> None:
        action_id = self.action.id.value
        changed = False
        if action_id in DIRECTIONS:
            changed = self._try_translate(*DIRECTIONS[action_id])
        elif action_id == GameAction.ACTION5.value:
            self._selected = (self._selected + 1) % len(self._pairs)
            self._refusal = set()
            changed = True

        if changed and self._is_complete():
            self._solved = True
            self._render_board()
            self.next_level()
            self.complete_action()
            return

        if changed:
            self._counted_actions += 1
        self._render_board()
        if self._counted_actions >= self._budget_cap:
            self.lose()
        self.complete_action()
