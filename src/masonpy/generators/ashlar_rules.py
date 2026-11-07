"""Stock and local feasibility for circular skyline masonry; no UI or randomness."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Any, Iterator, Sequence

Size = tuple[int, int]


@dataclass(frozen=True)
class AshlarStock:
    """Ordinary rectangles plus optional bounded, undersized closing stones."""

    min_width: int
    max_width: int
    min_height: int
    max_height: int
    allow_snecks: bool
    min_sneck_size: int = 1

    @property
    def lower_width(self) -> int:
        """Smallest permitted width, including closing stock when enabled."""
        return self.min_sneck_size if self.allow_snecks else self.min_width

    @property
    def lower_height(self) -> int:
        """Smallest permitted height, including closing stock when enabled."""
        return self.min_sneck_size if self.allow_snecks else self.min_height

    @staticmethod
    def can_span(length: int, minimum: int, maximum: int) -> bool:
        """Exact composition test for a contiguous range of integer lengths."""
        return length == 0 or (length + maximum - 1) // maximum <= length // minimum

    def remnants_fit(self, width: int, height: int) -> bool:
        """Necessary exact composition checks for leftover width and height."""
        return self.can_span(width, self.lower_width, self.max_width) and self.can_span(
            height, self.lower_height, self.max_height
        )

    def is_sneck(self, width: int, height: int) -> bool:
        """Classify by ordinary minima, independently of style preference."""
        return width < self.min_width or height < self.min_height

    def bands(self, width: int, height: int, sneck: bool) -> list[tuple[range, range]]:
        """Disjoint size bands, including stones below *both* ordinary minima."""
        ws = range(self.min_width, min(width, self.max_width) + 1)
        hs = range(self.min_height, min(height, self.max_height) + 1)
        if not sneck:
            return [(ws, hs)]
        if not self.allow_snecks:
            return []
        small_ws = range(self.min_sneck_size, min(width, self.min_width - 1) + 1)
        small_hs = range(self.min_sneck_size, min(height, self.min_height - 1) + 1)
        all_ws = range(self.min_sneck_size, min(width, self.max_width) + 1)
        return [(small_ws, hs), (all_ws, small_hs)]

    def sizes(self, width: int, height: int) -> Iterator[Size]:
        """Enumerate the complete permitted inventory without duplicate rectangles."""
        for sneck in (False, True):
            for ws, hs in self.bands(width, height, sneck):
                yield from product(ws, hs)

    def count(self, width: int, height: int) -> int:
        """Count inventory without allocating a list of rectangles."""
        return sum(
            len(ws) * len(hs)
            for sneck in (False, True)
            for ws, hs in self.bands(width, height, sneck)
        )


@dataclass
class BondingFrontier:
    """A read-only grid snapshot, with cached boundary runs and cheap trial overlays.

    A skyline placement can only extend completed joints at its two ends.
    Interior columns all receive the same identity and interrupt any old seam.
    The full joint analysis remains the independent final verification.
    """

    cells: Sequence[Sequence[int | None]]
    skyline: Sequence[int]
    next_id: int
    limit: int | None
    _below: dict[tuple[int, int], tuple[frozenset[int], frozenset[int]]] = field(
        default_factory=dict, init=False, repr=False
    )

    @property
    def width(self) -> int:
        """Logical circumference of the snapshot."""
        return len(self.skyline)

    @property
    def height(self) -> int:
        """Height of the snapshot."""
        return len(self.cells)

    def ids_below(self, boundary: int, y: int) -> tuple[frozenset[int], frozenset[int]]:
        """Cache distinct identities along the continuous joint below a boundary."""
        boundary %= self.width
        key = boundary, y
        if key not in self._below:
            left_ids, right_ids = set(), set()
            for row in range(y - 1, -1, -1):
                left, right = self.cells[row][boundary - 1], self.cells[row][boundary]
                if left is None or right is None or left == right:
                    break
                left_ids.add(left)
                right_ids.add(right)
            self._below[key] = frozenset(left_ids), frozenset(right_ids)
        return self._below[key]

    def target(self, boundary: int, y: int, filling_right: bool) -> int | None:
        """Height needed to level a boundary using its last available joint slot."""
        boundary %= self.width
        neighbour = (boundary - 1 if filling_right else boundary) % self.width
        top = self.skyline[neighbour]
        if self.limit is None or top <= y:
            return None
        left, right = map(set, self.ids_below(boundary, y))
        neighbour_id = self.cells[y][neighbour]
        left.add(neighbour_id if filling_right else self.next_id)
        right.add(self.next_id if filling_right else neighbour_id)
        return top - y if max(len(left), len(right)) >= self.limit else None

    def context(
        self, x: int, y: int, width: int
    ) -> tuple[set[int], int | None, int | None]:
        """Supporting seam offsets and pressured closing heights at both ends."""
        seams = set()
        if y:
            # The valley's enclosing edge is already handled by its levelling
            # target. Treating it as a new interior endpoint favours leaving a
            # unit-wide strip instead of closing the valley with an ordinary stone.
            for dx in range(1, width):
                boundary = (x + dx) % self.width
                left, right = (
                    self.cells[y - 1][boundary - 1],
                    self.cells[y - 1][boundary],
                )
                if left is not None and right is not None and left != right:
                    seams.add(dx)
        return seams, self.target(x, y, True), self.target(x + width, y, False)

    def problem(self, x: int, y: int, width: int, height: int) -> dict[str, Any] | None:
        """Check completed and inevitably continuing joints at candidate ends."""
        if self.limit is None or width == self.width:
            return None
        for boundary, filling_right in ((x, True), (x + width, False)):
            boundary %= self.width
            neighbour = (boundary - 1 if filling_right else boundary) % self.width
            neighbour_top, top = self.skyline[neighbour], y + height
            left, right = map(set, self.ids_below(boundary, y))
            candidate_ids, neighbour_ids = (
                (right, left) if filling_right else (left, right)
            )
            candidate_ids.add(self.next_id)
            for row in range(y, min(top, neighbour_top)):
                neighbour_ids.add(self.cells[row][neighbour])
            kind = "stack_limit"
            if max(len(left), len(right)) <= self.limit:
                if top == neighbour_top:
                    continue
                # A future stone on the lower side is unavoidable until these
                # tops meet. Include the taller side's identity at that height.
                if top < neighbour_top:
                    candidate_ids.add(-1)
                    neighbour_ids.add(self.cells[top][neighbour])
                else:
                    neighbour_ids.add(-1)
                if max(len(left), len(right)) <= self.limit:
                    continue
                kind = "frontier_blocked"
            return {
                "kind": kind,
                "boundary": boundary,
                "y": min(top, neighbour_top),
                "required_height": neighbour_top - y,
                "left_stones": sorted(left - {-1, self.next_id}),
                "right_stones": sorted(right - {-1, self.next_id}),
                "stack": max(len(left), len(right)),
            }
        return None

    def after(self, x: int, y: int, width: int, height: int) -> BondingFrontier:
        """Overlay only affected rows; never add speculative stones to the Wall."""
        cells = list(self.cells)
        skyline = list(self.skyline)
        columns = [(x + dx) % self.width for dx in range(width)]
        for row in range(y, y + height):
            cells[row] = list(cells[row])
            for column in columns:
                cells[row][column] = self.next_id
        for column in columns:
            skyline[column] = y + height
        return BondingFrontier(cells, skyline, self.next_id + 1, self.limit)

    def valleys_near(self, columns: Sequence[int]) -> list[tuple[int, int, int]]:
        """Find local minimum plateaus touching the supplied columns."""
        valleys = set()
        for column in columns:
            x = column % self.width
            y = self.skyline[x]
            if y == self.height:
                continue
            width = 1
            while width < self.width and self.skyline[(x - 1) % self.width] == y:
                x = (x - 1) % self.width
                width += 1
            while width < self.width and self.skyline[(x + width) % self.width] == y:
                width += 1
            if (
                width < self.width
                and min(
                    self.skyline[(x - 1) % self.width],
                    self.skyline[(x + width) % self.width],
                )
                > y
            ):
                valleys.add((x, y, width))
        return sorted(valleys)


def continuation_problem(
    frontier: BondingFrontier,
    stock: AshlarStock,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    budget: int = 64,
    depth: int = 2,
) -> dict[str, Any] | None:
    """Prove small local dead ends with bounded lookahead; unknown stays admissible.

    This is not a global packing proof. No RNG, source mutation or hidden history
    rewrite occurs. Running out of nodes never becomes a false impossibility.
    """
    if not stock.remnants_fit(width=0, height=frontier.height - y - height):
        return {
            "kind": "unavailable_closer",
            "remaining_height": frontier.height - y - height,
        }
    remaining = [budget]

    def viable(
        state: BondingFrontier, valley: tuple[int, int, int], levels: int
    ) -> bool:
        """Search a tiny valley; a node limit means unknown rather than impossible."""
        vx, vy, vw = valley
        if not stock.remnants_fit(vw, state.height - vy):
            return False
        if levels == 0 or remaining[0] <= 0:
            return True
        count = stock.count(vw, state.height - vy)
        # Enumerate only small inventories. Larger searches remain unknown.
        if count > remaining[0]:
            return True
        _, start, end = state.context(vx, vy, vw)
        sizes = sorted(
            stock.sizes(vw, state.height - vy),
            key=lambda wh: (wh[1] not in (start, end), wh[0] != vw),
        )
        for sw, sh in sizes:
            if remaining[0] <= 0:
                return True
            remaining[0] -= 1
            if not stock.remnants_fit(vw - sw, state.height - vy - sh):
                continue
            if state.problem(vx, vy, sw, sh):
                continue
            if safe_near(state.after(vx, vy, sw, sh), vx, sw, levels - 1):
                return True
        return False

    def safe_near(state: BondingFrontier, sx: int, sw: int, levels: int) -> bool:
        """Check representability and pressured narrow valleys affected by a trial."""
        for valley in state.valleys_near((sx - 1, sx, sx + sw - 1, sx + sw)):
            vx, vy, vw = valley
            if not stock.remnants_fit(vw, state.height - vy):
                return False
            if state.limit is None or vw > min(24, 2 * stock.min_width):
                continue
            _, start, end = state.context(vx, vy, vw)
            if start is None and end is None:
                continue
            if not viable(state, valley, levels):
                return False
        return True

    if not safe_near(frontier.after(x, y, width, height), x, width, depth):
        return {"kind": "lookahead_blocked", "x": x, "y": y, "depth": depth}
    return None
