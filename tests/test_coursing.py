"""Geometry and multi-seed checks for the soft skyline preference."""

import unittest

from masonpy import AshlarGenerator, ConstructionFailure, Stone, Wall, vertical_seams
from masonpy.app import GenerationSession


class CoursingTests(unittest.TestCase):
    def test_plateau_joins_both_sides_into_one_ring_and_counts_ids_once(self):
        skyline = [4, 4, 0, 0, 4, 4]
        owners = [7, 7, None, None, 8, 7]
        result = AshlarGenerator._resulting_plateau(
            skyline, owners, Stone(9, 2, 0, 2, 4)
        )
        self.assertEqual(result, (6, 3))
        self.assertEqual(skyline, [4, 4, 0, 0, 4, 4])

    def test_crossing_candidate_and_rotated_geometry_have_identical_measurements(self):
        skyline = [0, 0, 4, 4, 1, 1, 4, 0]
        owners = [None, None, 3, 3, 4, 4, 8, None]
        candidate = Stone(9, 7, 0, 3, 4)
        self.assertEqual(
            AshlarGenerator._resulting_plateau(skyline, owners, candidate), (6, 3)
        )
        for shift in range(8):
            shifted_skyline = [skyline[(x - shift) % 8] for x in range(8)]
            shifted_owners = [owners[(x - shift) % 8] for x in range(8)]
            shifted = Stone(9, (7 + shift) % 8, 0, 3, 4)
            self.assertEqual(
                AshlarGenerator._resulting_plateau(
                    shifted_skyline, shifted_owners, shifted
                ),
                (6, 3),
            )

    def test_weight_accumulates_primarily_with_extent_and_remains_positive(self):
        generator = AshlarGenerator(coursing_factor=0)

        def weight(extension, count):
            return generator._style_weight(
                dict(
                    connected_extension=extension,
                    plateau_stones=count,
                    disconnected_skyline_length=0,
                    connected_joint_length=0,
                    disconnected_joint_length=0,
                ),
                24,
            )

        self.assertGreater(weight(6, 2), weight(12, 2))
        self.assertGreater(weight(12, 2), weight(12, 4))
        self.assertLess(weight(18, 2), weight(6, 8))
        self.assertGreater(weight(100, 20), 0)

    def test_only_ordinary_height_is_accepted_even_when_it_closes_a_full_plateau(self):
        wall = Wall(12, 6, wrap_x=True)
        wall.add_stone(Stone(0, 0, 0, 4, 2))
        wall.add_stone(Stone(1, 8, 0, 4, 2))
        event = next(
            AshlarGenerator(
                min_stone_width=4,
                max_stone_width=4,
                min_stone_height=2,
                max_stone_height=2,
                snecking_factor=0,
            ).generate_incrementally(wall)
        )
        self.assertEqual((event.stone.width, event.stone.height), (4, 2))
        self.assertEqual(event.stone.traits["plateau_extent"], 12)
        self.assertFalse(event.stone.traits["is_sneck"])
        self.assertFalse(event.stone.traits["height_variation_choice"])

    def test_geometry_is_independent_of_the_order_supporting_stones_were_added(self):
        stones = [Stone(0, 0, 0, 4, 3), Stone(1, 8, 0, 4, 3), Stone(2, 12, 0, 4, 2)]
        placements = []
        for sequence in (stones, list(reversed(stones))):
            wall = Wall(16, 8, wrap_x=True)
            for stone in sequence:
                wall.add_stone(stone)
            placements.append(
                next(AshlarGenerator(seed=2).generate_incrementally(wall)).to_dict()
            )
        self.assertEqual(*placements)

    def test_future_joint_pressure_can_require_a_smaller_closer(self):
        wall = Wall(12, 6, wrap_x=True)
        for stone in (
            Stone(0, 0, 0, 4, 1),
            Stone(1, 0, 1, 4, 1),
            Stone(2, 0, 2, 4, 2),
            Stone(3, 8, 0, 4, 2),
        ):
            wall.add_stone(stone)
        event = next(
            AshlarGenerator(
                min_stone_width=4,
                max_stone_width=4,
                min_stone_height=2,
                max_stone_height=4,
                enforce_stack=1,
                snecking_factor=0.01,
            ).generate_incrementally(wall)
        )
        self.assertEqual(event.stone.height, 1)
        self.assertTrue(event.stone.traits["is_sneck"])
        self.assertTrue(all(s.stack_count <= 2 for s in vertical_seams(wall)))

    def test_full_incremental_and_undo_sequences_remain_deterministic(self):
        walls = []
        for incremental in (False, True):
            wall = Wall(24, 12)
            generator = AshlarGenerator(seed=1, enforce_stack=1, snecking_factor=0.01)
            if incremental:
                for _ in generator.generate_incrementally(wall):
                    pass
            else:
                generator.generate(wall)
            walls.append(wall.to_dict())
        self.assertEqual(*walls)
        states = []
        for _ in range(2):
            session = GenerationSession(
                generator_id="ashlar",
                generator_parameters={
                    "seed": 1,
                    "enforce_stack": 1,
                    "snecking_factor": 0.01,
                },
            )
            for _ in range(8):
                session.step()
            session.undo()
            session.step()
            states.append(session.to_dict())
            self.assertTrue(
                all(s.stack_count <= 2 for s in vertical_seams(session.wall))
            )
        self.assertEqual(*states)

    def test_multiple_seeds_reduce_long_plateaus_without_breaking_joint_limits(self):
        def measure(enabled):
            extents = []
            for seed in range(40):
                wall = Wall(24, 12)
                generator = AshlarGenerator(
                    seed=seed,
                    enforce_stack=1,
                    snecking_factor=0.01,
                    coursing_factor=(0.5 if not enabled else 0),
                )
                skyline = [0] * wall.width
                try:
                    for event in generator.generate_incrementally(wall):
                        stone = event.stone
                        for dx in range(stone.width):
                            skyline[(stone.x + dx) % wall.width] = (
                                stone.y + stone.height
                            )
                        self.assertTrue(
                            all(s.stack_count <= 2 for s in vertical_seams(wall))
                        )
                        if not stone.traits["is_sneck"]:
                            self.assertTrue(
                                3 <= stone.width <= 8 and 2 <= stone.height <= 5
                            )
                        # Independently identify all columns connected to this
                        # candidate's top, excluding the unavoidable finished cap.
                        top = stone.y + stone.height
                        if top == wall.height:
                            continue
                        connected = {stone.x}
                        pending = [stone.x]
                        while pending:
                            x = pending.pop()
                            for adjacent in (
                                (x - 1) % wall.width,
                                (x + 1) % wall.width,
                            ):
                                if (
                                    adjacent not in connected
                                    and skyline[adjacent] == top
                                ):
                                    connected.add(adjacent)
                                    pending.append(adjacent)
                        extents.append(len(connected))
                except ConstructionFailure:
                    # Failure is permitted; every accepted prefix must still
                    # satisfy the hard limit in either comparison mode.
                    pass
            return sum(extents) / len(extents), sum(n >= 12 for n in extents) / len(
                extents
            )

        baseline = measure(0)
        varied = measure(1)
        self.assertLess(varied[0], baseline[0])
        self.assertLess(varied[1], baseline[1])


if __name__ == "__main__":
    unittest.main()
