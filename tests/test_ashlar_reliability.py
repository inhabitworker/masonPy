"""Regression walls and independent checks for stock, exposed joints and lookahead."""

import unittest
from itertools import islice

from masonpy import AshlarGenerator, ConstructionFailure, Stone, Wall, vertical_seams
from masonpy.generators.ashlar_rules import (
    AshlarStock,
    BondingFrontier,
    continuation_problem,
)
from masonpy.generators.catalog import get_generator_definition


class AshlarReliabilityTests(unittest.TestCase):
    def assert_valid_complete(self, wall, generator):
        self.assertTrue(all(cell is not None for row in wall.occupancy for cell in row))
        self.assertTrue(
            all(
                s.width <= generator.max_stone_width
                and s.height <= generator.max_stone_height
                for s in wall.stones
            )
        )
        self.assertLessEqual(
            max((s.stack_count for s in vertical_seams(wall)), default=0),
            generator.max_joint_stack,
        )

    def test_default_strip_and_reported_seed_four_regressions(self):
        for width, height, parameters in (
            (52, 30, {}),
            (
                104,
                60,
                dict(
                    min_stone_width=3,
                    max_stone_width=10,
                    min_stone_height=3,
                    max_stone_height=7,
                    seed=4,
                ),
            ),
            (
                104,
                60,
                dict(
                    min_stone_width=3,
                    max_stone_width=10,
                    min_stone_height=3,
                    max_stone_height=7,
                    seed=1,
                    snecking_factor=1,
                ),
            ),
        ):
            with self.subTest(parameters=parameters):
                wall = Wall(width, height)
                generator = AshlarGenerator(**parameters)
                generator.generate(wall)
                self.assert_valid_complete(wall, generator)

    def test_refined_stock_includes_intermediate_closers(self):
        for scale in (2, 3):
            wall = Wall(52 * scale, 30 * scale)
            generator = AshlarGenerator(
                min_stone_width=3 * scale,
                max_stone_width=8 * scale,
                min_stone_height=2 * scale,
                max_stone_height=5 * scale,
                snecking_factor=0,
                seed=0,
            )
            generator.generate(wall)
            self.assert_valid_complete(wall, generator)
            self.assertFalse(any(s.traits["sneck_deliberate"] for s in wall.stones))

    def test_zero_preference_keeps_necessary_both_small_closers(self):
        wall = Wall(5, 3)
        generator = AshlarGenerator(
            min_stone_width=4,
            max_stone_width=4,
            min_stone_height=2,
            max_stone_height=2,
            snecking_factor=0,
        )
        generator.generate(wall)
        self.assert_valid_complete(wall, generator)
        self.assertTrue(any(s.width < 4 and s.height < 2 for s in wall.stones))
        self.assertFalse(any(s.traits["sneck_deliberate"] for s in wall.stones))

    def test_permission_is_independent_of_preference_and_in_catalogue(self):
        generator, values = get_generator_definition("ashlar").create(
            {"allow_snecks": 0, "snecking_factor": 1}
        )
        self.assertEqual(values["allow_snecks"], 0)
        wall = Wall(24, 12)
        try:
            generator.generate(wall)
        except ConstructionFailure:
            pass
        self.assertFalse(any(s.traits["is_sneck"] for s in wall.stones))
        fields = {p.id: p for p in get_generator_definition("ashlar").parameters}
        self.assertTrue(fields["allow_snecks"].toggle)
        self.assertFalse(fields["allow_snecks"].advanced)
        self.assertTrue(fields["min_sneck_size"].advanced)

    def test_impossible_configurations_fail_before_mutation(self):
        for w, h, parameters in (
            (
                5,
                2,
                dict(
                    min_stone_width=4,
                    max_stone_width=4,
                    min_stone_height=2,
                    max_stone_height=2,
                    allow_snecks=0,
                ),
            ),
            (
                12,
                5,
                dict(
                    min_stone_width=4,
                    max_stone_width=4,
                    min_stone_height=2,
                    max_stone_height=2,
                    allow_snecks=0,
                ),
            ),
            (
                24,
                12,
                dict(
                    min_stone_width=1,
                    max_stone_width=1,
                    min_stone_height=1,
                    max_stone_height=1,
                ),
            ),
        ):
            wall = Wall(w, h)
            original = wall.to_dict()
            with self.assertRaises(ConstructionFailure) as error:
                AshlarGenerator(**parameters).generate(wall)
            self.assertEqual(error.exception.kind, "incompatible_configuration")
            self.assertFalse(error.exception.retry_possible)
            self.assertEqual(wall.to_dict(), original)
        single = Wall(1, 1)
        AshlarGenerator().generate(single)
        self.assertEqual(len(single.stones), 1)

    def test_minimum_closing_size_is_respected_and_validated(self):
        generator = AshlarGenerator(min_sneck_size=2)
        wall = Wall(24, 12)
        try:
            generator.generate(wall)
        except ConstructionFailure:
            pass
        self.assertTrue(all(min(s.width, s.height) >= 2 for s in wall.stones))
        for invalid in (0, 3, True, 1.5):
            with self.assertRaises(ValueError):
                AshlarGenerator(min_sneck_size=invalid)

    def test_integer_composition_preflight_matches_exhaustive_sums(self):
        for minimum in range(1, 6):
            for maximum in range(minimum, 8):
                reachable = {0}
                for length in range(1, 30):
                    if any(
                        length - size in reachable
                        for size in range(minimum, maximum + 1)
                    ):
                        reachable.add(length)
                    self.assertEqual(
                        AshlarStock.can_span(length, minimum, maximum),
                        length in reachable,
                    )

    def test_enclosing_edge_does_not_encourage_leaving_a_thin_strip(self):
        wall = Wall(12, 12, wrap_x=True)
        for stone in (Stone(0, 0, 0, 4, 2), Stone(1, 4, 0, 4, 2), Stone(2, 8, 0, 4, 6)):
            wall.add_stone(stone)
        frontier = BondingFrontier(
            wall.occupancy, [2] * 8 + [6] * 4, wall.next_stone_id, 2
        )
        seams, start, end = frontier.context(0, 2, 8)
        self.assertEqual(seams, {4})
        self.assertEqual((start, end), (4, 4))
        generator = AshlarGenerator(
            enforce_stack=0,
            seed=4,
            min_stone_width=3,
            max_stone_width=10,
            min_stone_height=3,
            max_stone_height=7,
        )
        control = Wall(104, 60)
        generator.generate(control)
        area = sum(s.width * s.height for s in control.stones if s.traits["is_sneck"])
        self.assertLess(area / (104 * 60), 0.04)

    def test_lookahead_catches_conflicting_ends_without_mutation_or_rng(self):
        wall = Wall(10, 10, wrap_x=True)
        for stone in (
            Stone(0, 0, 0, 2, 2),
            Stone(1, 2, 0, 1, 2),
            Stone(2, 3, 0, 1, 2),
            Stone(3, 4, 0, 2, 2),
            Stone(4, 4, 2, 2, 3),
            Stone(5, 6, 0, 4, 8),
        ):
            wall.add_stone(stone)
        original = wall.to_dict()
        frontier = BondingFrontier(
            wall.occupancy,
            AshlarGenerator._skyline_from_wall(wall),
            wall.next_stone_id,
            2,
        )
        stock = AshlarStock(3, 4, 3, 6, True)
        # This trial is safe at each immediate edge, but leaves a two-wide
        # valley requiring incompatible six- and three-unit closing heights.
        self.assertIsNone(frontier.problem(0, 2, 2, 6))
        self.assertIsNone(continuation_problem(frontier, stock, 0, 2, 2, 6, budget=0))
        problem = continuation_problem(frontier, stock, 0, 2, 2, 6)
        self.assertEqual(problem["kind"], "lookahead_blocked")
        self.assertEqual(wall.to_dict(), original)

    @staticmethod
    def reference_blocked(wall, limit):
        cells = wall.occupancy
        skyline = AshlarGenerator._skyline_from_wall(wall)
        for x in range(wall.width):
            left_top, right_top = skyline[x - 1], skyline[x]
            if left_top == right_top:
                continue
            y = min(left_top, right_top)
            left_ids, right_ids = set(), set()
            for row in range(y - 1, -1, -1):
                a, b = cells[row][x - 1], cells[row][x]
                if a is None or b is None or a == b:
                    break
                left_ids.add(a)
                right_ids.add(b)
            if left_top < right_top:
                left_ids.add(-1)
                right_ids.add(cells[y][x])
            else:
                left_ids.add(cells[y][x - 1])
                right_ids.add(-1)
            if max(len(left_ids), len(right_ids)) > limit:
                return True
        return False

    def test_local_boundary_checks_match_independent_full_grid_analysis(self):
        tested = 0
        for seed in range(3):
            wall = Wall(16, 10)
            generator = AshlarGenerator(seed=seed)
            steps = generator.generate_incrementally(wall)
            for event in islice(steps, 12):
                self.assertFalse(self.reference_blocked(wall, 2))
                skyline = generator._skyline_from_wall(wall)
                x, width = generator._lowest_valley(skyline)
                y = min(skyline)
                frontier = BondingFrontier(
                    wall.occupancy, skyline, wall.next_stone_id, 2
                )
                before = wall.to_dict()
                for sw in range(1, min(width, 8) + 1):
                    for sh in range(1, min(wall.height - y, 5) + 1):
                        predicted = frontier.problem(x, y, sw, sh)
                        wall.add_stone(Stone(wall.next_stone_id, x, y, sw, sh))
                        actual = any(
                            s.stack_count > 2 for s in vertical_seams(wall)
                        ) or self.reference_blocked(wall, 2)
                        wall.remove_last_stone()
                        self.assertEqual(
                            bool(predicted), actual, (seed, event.stone.id, sw, sh)
                        )
                        tested += 1
                self.assertEqual(wall.to_dict(), before)
        self.assertGreater(tested, 300)
