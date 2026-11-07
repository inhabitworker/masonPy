"""Simple randomized ashlar generation using a lowest-valley skyline."""

from __future__ import annotations

import logging
import math
import random
from collections.abc import Iterator
from itertools import chain, groupby, islice
from typing import Any, Sequence

from masonpy.analysis import WallAnalysis, resulting_plateau
from masonpy.analysis.joints import vertical_seams
from masonpy.generators.ashlar_rules import (
    AshlarStock,
    BondingFrontier,
    continuation_problem,
)
from masonpy.generators.errors import ConstructionFailure
from masonpy.generators.events import GenerationEvent
from masonpy.generators.interface import WallGenerator
from masonpy.models import HorizontalJoint, Stone, Wall

logger = logging.getLogger(__name__)


class AshlarGenerator(WallGenerator):
    """Fill the lowest contiguous skyline valley with one random stone at a time."""

    name = "ashlar"

    def __init__(
        self,
        *,
        min_stone_width: int = 3,
        max_stone_width: int = 8,
        min_stone_height: int = 2,
        max_stone_height: int = 5,
        seed: int = 1,
        jitter_start: int = 1,
        enforce_stack: int = 1,
        max_joint_stack: int = 2,
        allow_snecks: int = 1,
        min_sneck_size: int = 1,
        snecking_factor: float = 0.2,
        coursing_factor: float = 0.5,
    ) -> None:
        """Configure ordinary ranges, hard stack checks and seeded soft style preferences.

        Coefficients are 0–1. Snecking zero permits necessary closers only;
        coursing 0.5 is neutral. Undo reuses, rather than rewinds, the RNG stream."""
        self._validate_range("stone width", min_stone_width, max_stone_width)
        self._validate_range("stone height", min_stone_height, max_stone_height)
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            raise ValueError("seed must be a non-negative integer")

        self.min_stone_width = min_stone_width
        self.max_stone_width = max_stone_width
        self.min_stone_height = min_stone_height
        self.max_stone_height = max_stone_height
        self.seed = seed
        if jitter_start not in (0, 1):
            raise ValueError("jitter_start must be 0 or 1")
        self.jitter_start = bool(jitter_start)
        for name, value in (
            ("enforce_stack", enforce_stack),
            ("allow_snecks", allow_snecks),
        ):
            if value not in (0, 1):
                raise ValueError(f"{name} must be 0 or 1")
        if (
            not isinstance(max_joint_stack, int)
            or isinstance(max_joint_stack, bool)
            or max_joint_stack < 1
        ):
            raise ValueError("max_joint_stack must be a positive integer")
        self.enforce_stack = bool(enforce_stack)
        self.allow_snecks = bool(allow_snecks)
        if (
            isinstance(min_sneck_size, bool)
            or not isinstance(min_sneck_size, int)
            or not 1 <= min_sneck_size <= min(min_stone_width, min_stone_height)
        ):
            raise ValueError(
                "minimum sneck size must be a positive integer no larger than the ordinary minima"
            )
        self.min_sneck_size = min_sneck_size
        self.stock = AshlarStock(
            min_stone_width,
            max_stone_width,
            min_stone_height,
            max_stone_height,
            self.allow_snecks,
            min_sneck_size,
        )
        self.max_joint_stack = max_joint_stack
        for name, value in (
            ("snecking_factor", snecking_factor),
            ("coursing_factor", coursing_factor),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError(f"{name} must be a finite number between 0 and 1")
        self.snecking_factor = float(snecking_factor)
        self.coursing_factor = float(coursing_factor)
        self._random = random.Random(seed)

    @staticmethod
    def _validate_range(label: str, minimum: int, maximum: int) -> None:
        """Require positive integer dimension limits in ascending order."""
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in (minimum, maximum)
        ):
            raise ValueError(f"{label} limits must be positive integers")
        if minimum > maximum:
            raise ValueError(f"minimum {label} cannot exceed maximum {label}")

    def generate_incrementally(self, wall: Wall) -> Iterator[GenerationEvent]:
        # Ashlar packs a circular skyline; display wrapping remains independent.
        """Resume from a valid prefix and yield each accepted whole stone with its decision record."""
        if not wall.stones:
            self._preflight(wall)
            wall.wrap_x = True
        elif not wall.wrap_x:
            raise ValueError("ashlar requires a wall with logical horizontal wrapping")
        skyline = self._skyline_from_wall(wall)
        if self.enforce_stack and any(
            s.stack_count > self.max_joint_stack
            for s in vertical_seams(wall, wrap_x=True)
        ):
            raise ConstructionFailure(
                0,
                min(skyline),
                "Existing wall already exceeds the maximum joint stack.",
            )

        while min(skyline) < wall.height:
            y = min(skyline)
            x, valley_width = self._lowest_valley(skyline)
            target_reason = "Lowest valley; earliest x among circular valley starts"
            if not wall.stones and self.jitter_start:
                x = self._random.randrange(wall.width)
                target_reason = "Lowest valley; seeded random first-stone origin on the circular base"
            elif y > 0 and valley_width == wall.width:
                # A level skyline has no enclosing ends. Start over a stone,
                # rather than perpetuating an arbitrary origin joint.
                below = wall.occupancy[y - 1]
                interiors = [
                    column
                    for column in range(wall.width)
                    if below[column - 1] == below[column]
                ]
                if interiors:
                    x = self._random.choice(interiors)
                    target_reason = "Lowest valley; level skyline, seeded choice of an interior supporting-stone column"

            frontier = BondingFrontier(
                wall.occupancy,
                skyline,
                wall.next_stone_id,
                self.max_joint_stack if self.enforce_stack else None,
            )
            below_seams, start_target, end_target = frontier.context(x, y, valley_width)
            targets = tuple(
                target for target in (start_target, end_target) if target is not None
            )
            ordinary = self._candidates(valley_width, wall.height - y, False, targets)

            def rank(size: tuple[int, int]) -> tuple[int, bool, bool, bool]:
                """Order boundary levelling, seam endpoints and tiny remnants before style weighting."""
                return self._bonding_rank(
                    size,
                    valley_width,
                    wall.height - y,
                    below_seams,
                    start_target,
                    end_target,
                )

            ordinary.sort(key=rank)
            # Levelling at a pressured boundary comes before an ordinary stone
            # that would strand a further joint beside the same tall neighbour.
            preferred = [size for size in ordinary if rank(size)[0] == 0]
            remaining = [size for size in ordinary if rank(size)[0] != 0]
            # Geometry creates possibilities; style never makes arbitrary thin
            # stones. Deliberate snecks need a boundary or joint-offset purpose.
            fillers = (
                self._candidates(valley_width, wall.height - y, True, targets)
                if self.allow_snecks
                else []
            )
            opportunities = {
                size: self._sneck_opportunity(
                    size, skyline, x, y, valley_width, below_seams
                )
                for size in fillers
            }

            def corner(size: tuple[int, int]) -> bool:
                """Reserve stones below both minima for genuine small closures."""
                return (
                    size[0] < self.min_stone_width and size[1] < self.min_stone_height
                )

            deliberate = [
                (True, size)
                for size in fillers
                if self.snecking_factor
                and opportunities[size]
                and not corner(size)
                and preferred
                and rank(size) == rank(preferred[0])
            ]
            tiers = [
                (
                    "ordinary and useful deliberate snecks",
                    sorted(
                        [(False, size) for size in preferred] + deliberate,
                        key=lambda item: rank(item[1]),
                    ),
                )
            ]
            if self.allow_snecks and targets:
                targeted = self._plateau_snecks(valley_width, targets)
                targeted.sort(key=rank)
                for small in (False, True):
                    tiers.append(
                        (
                            "targeted corner closers"
                            if small
                            else "targeted plateau repairs",
                            [
                                (True, size)
                                for size in targeted
                                if rank(size)[0] == 0 and corner(size) == small
                            ],
                        )
                    )
            tiers.append(
                ("remaining ordinary sizes", [(False, size) for size in remaining])
            )
            if self.allow_snecks:
                fillers.sort(key=rank)
                for small in (False, True):
                    tiers.append(
                        (
                            "small corner fallback"
                            if small
                            else "thin filler fallback",
                            [(True, size) for size in fillers if corner(size) == small],
                        )
                    )

            # A sampled tier is not evidence that stock is impossible. Exhaust
            # small inventories on failure; keep large searches explicitly bounded.
            inventory_count = self.stock.count(valley_width, wall.height - y)
            search_tier = (
                (
                    "stock search fallback",
                    sorted(
                        [
                            (self.stock.is_sneck(*size), size)
                            for size in islice(
                                self.stock.sizes(valley_width, wall.height - y), 4096
                            )
                        ],
                        key=lambda item: rank(item[1]),
                    ),
                )
                for _ in (0,)
            )

            rejected = 0
            rejection_counts: dict[str, int] = {}
            last_problem: dict[str, Any] = {}
            examined = 0
            stone = None
            tried = set()
            plateau_choice = False
            groups_examined = []
            decision = {}
            analysis = WallAnalysis(wall)
            surface = analysis.surface()
            _, top_ids = surface
            joints = analysis.horizontal_joints()
            sneck_share = sum(
                bool(s.traits.get("is_sneck")) for s in wall.stones
            ) / max(1, len(wall.stones))
            for tier_name, sizes in chain(tiers, search_tier):
                for priority, group in groupby(sizes, key=lambda item: rank(item[1])):
                    valid_candidates = []
                    group_start = examined
                    rejected_start = rejected
                    for sneck, (width, height) in group:
                        if (width, height) in tried:
                            continue
                        tried.add((width, height))
                        examined += 1
                        candidate = Stone(
                            id=wall.next_stone_id,
                            x=x,
                            y=y,
                            width=width,
                            height=height,
                            traits={
                                "generator": self.name,
                                "valley_x": x,
                                "valley_y": y,
                                "valley_width": valley_width,
                                "is_sneck": sneck,
                                "crosses_joint_below": any(
                                    seam < width for seam in below_seams
                                ),
                                "ends_on_joint_below": width in below_seams,
                                "start_plateau_target": start_target,
                                "end_plateau_target": end_target
                                if width == valley_width
                                else None,
                                "sneck_purpose": opportunities.get((width, height))
                                if sneck
                                else None,
                            },
                        )
                        problem = None
                        if not self.stock.remnants_fit(
                            valley_width - width, wall.height - y - height
                        ):
                            problem = {
                                "kind": "unavailable_closer",
                                "remaining_width": valley_width - width,
                                "remaining_height": wall.height - y - height,
                            }
                        if problem is None:
                            problem = frontier.problem(x, y, width, height)
                        if problem is None:
                            problem = continuation_problem(
                                frontier, self.stock, x, y, width, height
                            )
                        if problem is None:
                            valid_candidates.append(candidate)
                        else:
                            rejected += 1
                            kind = problem["kind"]
                            rejection_counts[kind] = rejection_counts.get(kind, 0) + 1
                            last_problem = problem
                    if examined > group_start:
                        groups_examined.append(
                            {
                                "tier": tier_name,
                                "bonding_rank": priority,
                                "examined": examined - group_start,
                                "rejected": rejected - rejected_start,
                                "valid": len(valid_candidates),
                                "exhausted": not valid_candidates,
                            }
                        )
                    if valid_candidates:
                        stone, weights, plateau_choice = self._choose_candidate(
                            wall,
                            analysis,
                            surface,
                            joints,
                            valid_candidates,
                            sneck_share,
                        )
                        decision = {
                            "target": {
                                "reason": target_reason,
                                "x": x,
                                "y": y,
                                "valley_width": valley_width,
                            },
                            "width": {
                                "ordinary_range": [
                                    self.min_stone_width,
                                    self.max_stone_width,
                                ],
                                "valid_options": sorted(
                                    {s.width for s in valid_candidates}
                                ),
                                "supporting_joint_offsets": sorted(below_seams),
                                "chosen": stone.width,
                            },
                            "height": {
                                "ordinary_range": [
                                    self.min_stone_height,
                                    self.max_stone_height,
                                ],
                                "valid_options": sorted(
                                    {s.height for s in valid_candidates}
                                ),
                                "start_plateau_target": start_target,
                                "end_plateau_target": end_target,
                                "chosen": stone.height,
                            },
                            "selection": {
                                "seed": self.seed,
                                "coursing_factor": self.coursing_factor,
                                "snecking_factor": self.snecking_factor,
                                "allow_snecks": self.allow_snecks,
                                "examined": examined,
                                "stack_limit": self.max_joint_stack
                                if self.enforce_stack
                                else None,
                                "stack_rejected": rejection_counts.get(
                                    "stack_limit", 0
                                ),
                                "rejected": rejected,
                                "rejection_counts": dict(rejection_counts),
                                "last_problem": last_problem,
                                "groups": groups_examined,
                                "chosen_weight": weights[valid_candidates.index(stone)],
                                "total_weight": sum(weights),
                                "options": [
                                    {
                                        "width": s.width,
                                        "height": s.height,
                                        "is_sneck": s.traits["is_sneck"],
                                        "weight": weight,
                                    }
                                    for s, weight in zip(valid_candidates, weights)
                                ],
                            },
                        }
                        break
                if stone is not None:
                    break
            if stone is None:
                if inventory_count > 4096:
                    kind = "search_budget"
                    explanation = (
                        "The bounded stock search was exhausted; untested sizes remain."
                    )
                elif not inventory_count or not self.stock.remnants_fit(
                    valley_width, wall.height - y
                ):
                    kind = "unavailable_closer"
                    explanation = (
                        "The gap cannot be closed with the permitted stone sizes."
                    )
                else:
                    kind = "local_dead_end"
                    explanation = "Earlier choices left no safe continuation with the permitted stock and joint limit."
                reason = (
                    f"{explanation} Lowest valley is {valley_width} units wide, "
                    f"{wall.height - y} units of height remaining; "
                    f"examined {examined} candidates, rejected {rejected}; maximum joint stack "
                    f"{self.max_joint_stack if self.enforce_stack else 'disabled'}; "
                    f"snecks {'allowed' if self.allow_snecks else 'disabled'}, minimum closing size {self.min_sneck_size}."
                )
                failure = ConstructionFailure(
                    x,
                    y,
                    reason,
                    rejected,
                    kind=kind,
                    details={
                        "valley_width": valley_width,
                        "remaining_height": wall.height - y,
                        "rejection_counts": rejection_counts,
                        "last_problem": last_problem,
                        "start_target": start_target,
                        "end_target": end_target,
                        "last_stone_id": wall.stones[-1].id if wall.stones else None,
                        "examined": examined,
                        "inventory_exhausted": inventory_count <= 4096,
                    },
                )
                logger.warning(str(failure))
                raise failure

            width, height = stone.width, stone.height
            extent, count = self._resulting_plateau(skyline, top_ids, stone)
            stone.traits.update(
                plateau_extent=extent,
                plateau_stones=count,
                height_variation_choice=plateau_choice,
            )
            wall.add_stone(stone)
            for dx in range(width):
                skyline[(x + dx) % wall.width] = y + height

            yield self._placement_event(stone, decision)

        if self.enforce_stack and any(
            s.stack_count > self.max_joint_stack for s in vertical_seams(wall)
        ):
            raise RuntimeError(
                "Ashlar local bonding checks disagree with final joint analysis"
            )

    def _preflight(self, wall: Wall) -> None:
        """Reject only provable stock/configuration conflicts, before any placement."""
        for axis, length, minimum, maximum in (
            ("width", wall.width, self.stock.lower_width, self.max_stone_width),
            ("height", wall.height, self.stock.lower_height, self.max_stone_height),
        ):
            if not self.stock.can_span(length, minimum, maximum):
                raise ConstructionFailure(
                    0,
                    0,
                    f"Wall {axis} {length} cannot be composed from permitted {axis}s {minimum}–{maximum}.",
                    retry_possible=False,
                    kind="incompatible_configuration",
                    details={
                        "axis": axis,
                        "length": length,
                        "minimum": minimum,
                        "maximum": maximum,
                    },
                )
        if (
            self.enforce_stack
            and wall.width > 1
            and self.max_stone_width == 1
            and wall.height > self.max_joint_stack * self.max_stone_height
        ):
            raise ConstructionFailure(
                0,
                0,
                "Unit-width stock cannot bridge vertical joints and needs more stones than the joint-stack limit permits.",
                retry_possible=False,
                kind="incompatible_configuration",
            )

    def _choose_candidate(
        self,
        wall: Wall,
        analysis: WallAnalysis,
        surface: tuple[Sequence[int], Sequence[int | None]],
        joints: Sequence[HorizontalJoint],
        valid_candidates: list[Stone],
        sneck_share: float,
    ) -> tuple[Stone, list[float], bool]:
        """Weight only hard-valid candidates in the selected bonding group.

        The caller fixes the group first. Keep enumeration and random draw order
        stable: a style coefficient never skips a necessary bonding priority.
        """
        weights = []
        has_ordinary = any(not s.traits["is_sneck"] for s in valid_candidates)
        for candidate in valid_candidates:
            context = analysis.alignment_after(
                candidate, surface=surface, joints=joints
            )
            candidate.traits.update(context)
            weight = self._style_weight(context, wall.width)
            if candidate.traits["is_sneck"]:
                aspect = max(
                    candidate.width / candidate.height,
                    candidate.height / candidate.width,
                )
                weight *= min(1.0, 3 / aspect) ** 2
            if candidate.traits["is_sneck"] and has_ordinary:
                neighbours = analysis.neighbours(
                    candidate.x, candidate.y, candidate.width, candidate.height
                )
                nearby_snecks = len(
                    {
                        s.id
                        for side in neighbours.values()
                        for s in side
                        if s.traits.get("is_sneck")
                    }
                )
                # Aggregate frequency and touching snecks temper
                # repetition, without a quota or a hard ban.
                weight *= (
                    4
                    * self.snecking_factor**3
                    / (1 + 8 * sneck_share + 2 * nearby_snecks)
                )
            weights.append(weight)
        stone = self._random.choices(valid_candidates, weights=weights, k=1)[0]
        plateau_choice = len({s.height for s in valid_candidates}) > 1
        stone.traits["sneck_deliberate"] = bool(
            stone.traits["is_sneck"] and has_ordinary
        )
        return stone, weights, plateau_choice

    def _placement_event(
        self, stone: Stone, decision: dict[str, Any]
    ) -> GenerationEvent:
        """Explain the already accepted placement; this function makes no choices."""
        x, y, width, height = stone.x, stone.y, stone.width, stone.height
        valley_width = decision["target"]["valley_width"]
        target_reason = decision["target"]["reason"]
        start_target = decision["height"]["start_plateau_target"]
        end_target = decision["height"]["end_plateau_target"]
        below_seams = set(decision["width"]["supporting_joint_offsets"])
        rejected = decision["selection"]["rejected"]
        examined = decision["selection"]["examined"]
        groups_examined = decision["selection"]["groups"]
        valid_candidates = decision["selection"]["options"]
        weights = [option["weight"] for option in valid_candidates]
        plateau_choice = stone.traits["height_variation_choice"]
        extent, count = stone.traits["plateau_extent"], stone.traits["plateau_stones"]
        choices = f"chose {width} × {height}"
        notes = []
        if plateau_choice:
            notes.append(
                f"coursing preference {self.coursing_factor:g}; plateau {extent} units / {count} stones, "
                f"remote skyline {stone.traits['disconnected_skyline_length']}, "
                f"joint extension {stone.traits['connected_joint_length']}, "
                f"remote joints {stone.traits['disconnected_joint_length']}"
            )
        if stone.traits["crosses_joint_below"]:
            notes.append("crosses joints below")
        elif below_seams and width < min(below_seams):
            notes.append("ends before the next joint below")
        if start_target is not None and height == start_target:
            notes.append("levels with enclosing start stone to end the stack")
        if end_target is not None and width == valley_width and height == end_target:
            notes.append("levels with enclosing end stone to end the stack")
        if rejected:
            notes.append(
                f"rejected {rejected} candidates by stock/bonding checks (stack limit {self.max_joint_stack})"
            )
        if stone.traits["is_sneck"]:
            purpose = stone.traits["sneck_purpose"] or "plateau or placement fallback"
            notes.append(
                f"{'deliberate' if stone.traits['sneck_deliberate'] else 'fallback'} sneck: {purpose}"
            )
        suffix = f"; {'; '.join(notes)}" if notes else ""
        if notes:
            logger.info("Placement at (%s, %s)%s", x, y, suffix)
        return GenerationEvent(
            stone,
            f"Added at [{x}, {y}]:\n"
            f"Target: {target_reason}; valley width {valley_width}.\n"
            f"Width: {width}; valid options {decision['width']['valid_options']}; "
            f"ordinary range {self.min_stone_width}–{self.max_stone_width}; "
            f"supporting joint offsets {sorted(below_seams)}.\n"
            f"Height: {height}; valid options {decision['height']['valid_options']}; "
            f"ordinary range {self.min_stone_height}–{self.max_stone_height}; "
            f"plateau targets start={start_target}, end={end_target}; coursing={self.coursing_factor:g}.\n"
            f"Selection: {len(valid_candidates)} hard-valid options in the best available bonding group; "
            f"{'seeded weighted choice' if len(valid_candidates) > 1 else 'only accepted option'}; "
            f"seed {self.seed}, weight {decision['selection']['chosen_weight']:.4g}/{sum(weights):.4g}; "
            f"snecking={self.snecking_factor:g}, stack limit={decision['selection']['stack_limit']}; "
            f"examined {examined}, rejected {rejected} {decision['selection']['rejection_counts']}; "
            f"{sum(g['exhausted'] for g in groups_examined)} earlier groups exhausted.\n"
            f"Result: {choices}{suffix}.",
            decision,
        )

    @staticmethod
    def _resulting_plateau(
        skyline: list[int], top_ids: list[int | None], stone: Stone
    ) -> tuple[int, int]:
        """Delegate hypothetical circular skyline extent/count measurement to the analysis layer."""
        return resulting_plateau(skyline, top_ids, stone)

    def _style_weight(self, context: dict[str, Any], circumference: int) -> float:
        # No reward for width alone: only extension/alignment with existing work.
        """Return a positive coursing preference; zero influence at factor 0.5 never changes hard validity."""
        typical = (self.min_stone_width + self.max_stone_width) / 2
        continuity = (
            math.log1p(
                (context["connected_extension"] + context["connected_joint_length"])
                / typical
            )
            * 2
        )
        aligned = (
            1.5 * context["disconnected_skyline_length"]
            + context["disconnected_joint_length"]
        ) / circumference
        count = 0.15 * math.log1p(context["plateau_stones"] - 1)
        return math.exp((2 * self.coursing_factor - 1) * (continuity + aligned + count))

    def _sneck_opportunity(
        self,
        size: tuple[int, int],
        skyline: Sequence[int],
        x: int,
        y: int,
        valley_width: Any,
        seams: set[int],
    ) -> str | None:
        """Identify a useful local thin-stone role, or None; this is not a probability."""
        width, height = size
        if height == skyline[(x - 1) % len(skyline)] - y:
            return "reach enclosing start plateau"
        if (
            width == valley_width
            and height == skyline[(x + valley_width) % len(skyline)] - y
        ):
            return "reach enclosing end plateau"
        if width == valley_width:
            return "close narrow valley"
        if width < self.min_stone_width and any(
            0 < seam - width < self.min_stone_width for seam in seams
        ):
            return "offset next ordinary stone across supporting joint"
        return None

    def _candidates(
        self,
        available_width: int,
        available_height: int,
        sneck: bool,
        target_heights: tuple[int, ...] = (),
    ) -> list[tuple[int, int]]:
        """Bounded random stock sample, always including small exact closures."""
        bands = self.stock.bands(available_width, available_height, sneck)
        total = sum(len(ws) * len(hs) for ws, hs in bands)
        candidates = []
        for height in dict.fromkeys((*target_heights, available_height)):
            for ws, hs in bands:
                if height in hs:
                    essential = (available_width, ws.start, ws.stop - 1)
                    candidates.extend(
                        (width, height) for width in essential if width in ws
                    )
                    candidates.extend(
                        (width, height)
                        for width in self._random.sample(ws, min(len(ws), 16))
                    )
        for index in self._random.sample(range(total), min(total, 128)):
            for ws, hs in bands:
                size = len(ws) * len(hs)
                if index < size:
                    candidates.append((ws[index // len(hs)], hs[index % len(hs)]))
                    break
                index -= size
        return list(dict.fromkeys(candidates))[:128]

    def _bonding_context(
        self, wall: Wall, skyline: list[int], x: int, y: int, width: int
    ) -> tuple[set[int], int | None, int | None]:
        """Inspect a circular valley using the same cached boundary rules as validation."""
        return BondingFrontier(
            wall.occupancy,
            skyline,
            wall.next_stone_id,
            self.max_joint_stack if self.enforce_stack else None,
        ).context(x, y, width)

    def _bonding_rank(
        self,
        size: tuple[int, int],
        available_width: int,
        available_height: int,
        seams: set[int],
        start_target: int | None,
        end_target: int | None,
    ) -> tuple[int, bool, bool, bool]:
        """Stable priorities; random candidate order breaks ties without scoring."""
        width, height = size
        targets = [start_target]
        if width == available_width:
            targets.append(end_target)
        misses = sum(target is not None and height != target for target in targets)
        # A closing stone should level when needed, but spanning the entire
        # valley earns no extra reward over a smaller legitimate placement.
        return (
            misses,
            width in seams,
            0 < available_width - width < self.min_stone_width,
            0 < available_height - height < self.min_stone_height,
        )

    def _plateau_snecks(
        self, available_width: int, target_heights: tuple[int, ...]
    ) -> list[tuple[int, int]]:
        """Exact levellers use the same bounded closing stock as every other tier."""
        return self._candidates(
            available_width, max(target_heights, default=0), True, target_heights
        )

    @staticmethod
    def _lowest_valley(skyline: list[int]) -> tuple[int, int]:
        """Return a minimum run, joining the last and first columns if needed."""
        lowest = min(skyline)
        if all(value == lowest for value in skyline):
            return 0, len(skyline)
        start = next(
            x
            for x, value in enumerate(skyline)
            if value == lowest and skyline[x - 1] != lowest
        )
        width = 1
        while (
            width < len(skyline) and skyline[(start + width) % len(skyline)] == lowest
        ):
            width += 1
        return start, width

    @staticmethod
    def _skyline_from_wall(wall: Wall) -> list[int]:
        """Reconstruct current elevations after placement or undo instead of trusting historical state."""
        return list(WallAnalysis(wall).skyline())
