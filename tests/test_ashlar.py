import unittest

from masonpy import AshlarGenerator, Wall, ConstructionFailure, Stone, vertical_seams


class AshlarGeneratorTests(unittest.TestCase):
    @staticmethod
    def bounded_valley(neighbour_height=6, shift=0):
        wall = Wall(12, 12, wrap_x=True)
        for stone in (
            Stone(0, shift % 12, 0, 4, 2),
            Stone(1, (shift + 4) % 12, 0, 4, 2),
            Stone(2, (shift + 8) % 12, 0, 4, neighbour_height),
        ):
            wall.add_stone(stone)
        return wall

    def test_widths_dodge_joints_below_including_wrapped_valleys(self):
        for shift in (0, 7):
            wall = self.bounded_valley(shift=shift)
            event = next(
                AshlarGenerator(
                    min_stone_width=3, max_stone_width=5, seed=1
                ).generate_incrementally(wall)
            )
            self.assertEqual(event.stone.x, shift)
            self.assertIn(event.stone.width, (3, 5))
            self.assertFalse(event.stone.traits["ends_on_joint_below"])
            self.assertIn("joint", event.explanation)

    def test_pressure_levels_both_valley_ends_before_another_stone_is_stacked(self):
        for shift in (0, 7):
            wall = self.bounded_valley(shift=shift)
            steps = AshlarGenerator(
                min_stone_width=3, max_stone_width=5, enforce_stack=1, seed=1
            ).generate_incrementally(wall)
            first, second = next(steps), next(steps)
            self.assertEqual(first.stone.height, 4)
            self.assertEqual(first.stone.traits["start_plateau_target"], 4)
            self.assertEqual(second.stone.height, 4)
            self.assertEqual(second.stone.traits["end_plateau_target"], 4)
            self.assertEqual(first.stone.width + second.stone.width, 8)
            self.assertTrue(all(s.stack_count <= 2 for s in vertical_seams(wall)))

    def test_repairs_cannot_exceed_maximum_height_to_rescue_a_bad_prefix(self):
        wall = self.bounded_valley(neighbour_height=10)
        original = wall.to_dict()
        with self.assertRaises(ConstructionFailure) as failure:
            next(
                AshlarGenerator(
                    min_stone_width=3,
                    max_stone_width=5,
                    enforce_stack=1,
                    snecking_factor=0.01,
                ).generate_incrementally(wall)
            )
        self.assertEqual(wall.to_dict(), original)
        self.assertEqual(failure.exception.kind, "local_dead_end")

    def test_flat_sneck_levels_a_shallow_pressured_valley(self):
        wall = self.bounded_valley(neighbour_height=3)
        event = next(
            AshlarGenerator(
                min_stone_width=3,
                max_stone_width=5,
                enforce_stack=1,
                snecking_factor=0.01,
            ).generate_incrementally(wall)
        )
        self.assertTrue(event.stone.traits["is_sneck"])
        self.assertEqual(event.stone.height, 1)
        self.assertTrue(3 <= event.stone.width <= 8)
        self.assertIn("levels with enclosing start", event.explanation)

    def test_plateau_repairs_do_not_silently_enable_snecks(self):
        wall = self.bounded_valley(neighbour_height=3)
        event = next(
            AshlarGenerator(
                min_stone_width=3, max_stone_width=5, enforce_stack=1, allow_snecks=0
            ).generate_incrementally(wall)
        )
        self.assertFalse(event.stone.traits["is_sneck"])

    def test_level_skyline_starts_over_a_stone_instead_of_a_joint(self):
        wall = Wall(12, 6, wrap_x=True)
        for index in range(3):
            wall.add_stone(Stone(index, index * 4, 0, 4, 2))
        below = wall.occupancy[1]
        event = next(
            AshlarGenerator(
                min_stone_width=3, max_stone_width=5
            ).generate_incrementally(wall)
        )
        x = event.stone.x
        end = (x + event.stone.width) % wall.width
        self.assertEqual(below[x - 1], below[x])
        self.assertEqual(below[end - 1], below[end])

    def test_bonding_constructs_a_taller_seeded_wall_with_limit_two(self):
        walls = []
        for _ in range(2):
            wall = Wall(24, 12)
            for event in AshlarGenerator(
                seed=1, enforce_stack=1, snecking_factor=0.01
            ).generate_incrementally(wall):
                self.assertTrue(all(s.stack_count <= 2 for s in vertical_seams(wall)))
            self.assertTrue(
                all(cell is not None for row in wall.occupancy for cell in row)
            )
            walls.append(wall.to_dict())
        self.assertEqual(*walls)

    def test_seeded_generation_is_repeatable_and_fills_wall(self):
        def generate(seed):
            wall = Wall(24, 12)
            events = AshlarGenerator(seed=seed).generate(wall)
            shapes = [
                (stone.x, stone.y, stone.width, stone.height) for stone in wall.stones
            ]
            return wall, events, shapes

        wall_a, events_a, shapes_a = generate(7)
        wall_b, _events_b, shapes_b = generate(7)
        _wall_c, _events_c, shapes_c = generate(8)

        self.assertEqual(shapes_a, shapes_b)
        self.assertNotEqual(shapes_a, shapes_c)
        self.assertEqual(len(events_a), len(wall_a.stones))
        self.assertTrue(
            all(cell is not None for row in wall_a.occupancy for cell in row)
        )

    def test_incremental_generation_places_one_lowest_valley_stone(self):
        wall = Wall(12, 8)
        steps = AshlarGenerator(
            min_stone_width=3,
            max_stone_width=5,
            min_stone_height=2,
            max_stone_height=4,
            seed=2,
        ).generate_incrementally(wall)

        first = next(steps)
        self.assertEqual(len(wall.stones), 1)
        self.assertEqual(first.stone, wall.stones[0])
        self.assertEqual(first.stone.traits["valley_y"], 0)
        self.assertIn("Lowest valley", first.explanation)

        second = next(steps)
        self.assertEqual(len(wall.stones), 2)
        self.assertEqual(
            second.stone.x, (first.stone.x + first.stone.width) % wall.width
        )

    def test_jitter_is_enabled_by_default_and_can_be_disabled(self):
        wall = Wall(24, 12)
        first = next(AshlarGenerator(seed=1).generate_incrementally(wall))
        self.assertNotEqual(first.stone.x, 0)
        plain = Wall(24, 12)
        first_plain = next(
            AshlarGenerator(seed=1, jitter_start=0).generate_incrementally(plain)
        )
        self.assertEqual(first_plain.stone.x, 0)

    def test_valley_continues_across_boundary_and_resume_restores_skyline(self):
        wall = Wall(12, 6, wrap_x=True)
        from masonpy import Stone

        wall.add_stone(Stone(0, 3, 0, 6, 2))
        generator = AshlarGenerator(
            min_stone_width=6, max_stone_width=6, min_stone_height=2, max_stone_height=2
        )
        event = next(generator.generate_incrementally(wall))
        self.assertEqual((event.stone.x, event.stone.width), (9, 6))
        self.assertEqual(event.stone.traits["valley_width"], 6)
        self.assertEqual(wall.occupancy[0][:3], (1, 1, 1))
        self.assertEqual(wall.occupancy[0][9:], (1, 1, 1))
        wall.remove_last_stone()
        self.assertEqual(wall.occupancy[0][:3], (None, None, None))
        generator.generate(wall)
        self.assertTrue(all(cell is not None for row in wall.occupancy for cell in row))

    def test_undersized_closure_requires_explicit_snecking(self):
        parameters = dict(
            min_stone_width=4,
            max_stone_width=4,
            min_stone_height=2,
            max_stone_height=2,
            seed=1,
        )
        wall = Wall(5, 2)
        with self.assertRaises(ConstructionFailure):
            AshlarGenerator(**parameters, allow_snecks=0).generate(wall)
        self.assertFalse(any(s.traits["is_sneck"] for s in wall.stones))
        filled = Wall(5, 2)
        events = AshlarGenerator(**parameters, snecking_factor=0.01).generate(filled)
        self.assertTrue(any(s.traits["is_sneck"] for s in filled.stones))
        self.assertTrue(any("fallback sneck" in e.explanation for e in events))
        self.assertTrue(
            all(cell is not None for row in filled.occupancy for cell in row)
        )

    def test_stack_rejection_rolls_back_trial_and_reports_failure(self):
        wall = Wall(8, 6, wrap_x=True)
        for stone in (Stone(0, 0, 0, 4, 6), Stone(1, 4, 0, 4, 2), Stone(2, 4, 2, 4, 2)):
            wall.add_stone(stone)
        original = wall.to_dict(), wall.occupancy
        generator = AshlarGenerator(
            min_stone_width=4,
            max_stone_width=4,
            min_stone_height=2,
            max_stone_height=2,
            enforce_stack=1,
            allow_snecks=0,
        )
        with self.assertRaises(ConstructionFailure) as failure:
            generator.generate(wall)
        self.assertGreaterEqual(failure.exception.rejected, 1)
        self.assertEqual((failure.exception.x, failure.exception.y), (4, 4))
        self.assertEqual((wall.to_dict(), wall.occupancy), original)
        self.assertEqual(
            max(s.stack_count for s in vertical_seams(wall, wrap_x=True)), 2
        )

    def test_constrained_incremental_success_and_repeatability(self):
        walls = []
        for _ in range(2):
            wall = Wall(12, 6)
            generator = AshlarGenerator(seed=0, enforce_stack=1, snecking_factor=0.01)
            for event in generator.generate_incrementally(wall):
                self.assertLessEqual(
                    max(
                        (s.stack_count for s in vertical_seams(wall, wrap_x=True)),
                        default=0,
                    ),
                    2,
                )
                if not event.stone.traits["is_sneck"]:
                    self.assertTrue(3 <= event.stone.width <= 8)
                    self.assertTrue(2 <= event.stone.height <= 5)
            self.assertTrue(all(c is not None for row in wall.occupancy for c in row))
            walls.append(wall.to_dict())
        self.assertEqual(*walls)

    def test_snecks_do_not_relax_joint_constraint(self):
        wall = Wall(8, 6, wrap_x=True)
        for stone in (Stone(0, 0, 0, 4, 6), Stone(1, 4, 0, 4, 2), Stone(2, 4, 2, 4, 2)):
            wall.add_stone(stone)
        before = wall.occupancy
        with self.assertRaises(ConstructionFailure):
            AshlarGenerator(
                min_stone_width=4,
                max_stone_width=4,
                min_stone_height=2,
                max_stone_height=2,
                enforce_stack=1,
                snecking_factor=0.01,
            ).generate(wall)
        self.assertEqual(wall.occupancy, before)

    def test_top_sneck_is_identified_and_preserves_periodicity(self):
        wall = Wall(8, 3)
        AshlarGenerator(
            min_stone_width=4,
            max_stone_width=4,
            min_stone_height=2,
            max_stone_height=2,
            snecking_factor=0.01,
            enforce_stack=1,
        ).generate(wall)
        self.assertTrue(
            any(s.height == 1 and s.traits["is_sneck"] for s in wall.stones)
        )
        self.assertTrue(all(c is not None for row in wall.occupancy for c in row))

    def test_rejections_are_summarized_when_an_alternative_is_accepted(self):
        wall = Wall(12, 6)
        wall.wrap_x = True
        for stone in (
            Stone(0, 0, 0, 4, 6),
            Stone(1, 4, 0, 4, 4),
            Stone(2, 8, 0, 4, 2),
            Stone(3, 8, 2, 4, 2),
        ):
            wall.add_stone(stone)
        with self.assertLogs("masonpy.generators.ashlar", level="INFO"):
            event = next(
                AshlarGenerator(
                    enforce_stack=1, min_stone_height=2, max_stone_height=2
                ).generate_incrementally(wall)
            )
        self.assertIn("rejected", event.explanation)
        self.assertIn("rejection_counts", event.decision["selection"])
        self.assertTrue(all(seam.stack_count <= 2 for seam in vertical_seams(wall)))

    def test_previous_corner_failure_now_completes_deterministically(self):
        outcomes = []
        for _ in range(2):
            wall = Wall(11, 5)
            events = AshlarGenerator(
                seed=6,
                min_stone_width=5,
                max_stone_width=5,
                min_stone_height=2,
                max_stone_height=2,
                enforce_stack=1,
                snecking_factor=0.01,
                coursing_factor=0.5,
            ).generate(wall)
            outcomes.append((wall.to_dict(), [e.to_dict() for e in events]))
            self.assertTrue(all(c is not None for row in wall.occupancy for c in row))
            self.assertTrue(any(s.width < 5 and s.height < 2 for s in wall.stones))
            self.assertTrue(all(s.stack_count <= 2 for s in vertical_seams(wall)))
        self.assertEqual(*outcomes)

    def test_parameter_ranges_are_validated(self):
        with self.assertRaisesRegex(ValueError, "minimum stone width"):
            AshlarGenerator(min_stone_width=5, max_stone_width=4)
        with self.assertRaisesRegex(ValueError, "positive integers"):
            AshlarGenerator(min_stone_height=0)
        with self.assertRaisesRegex(ValueError, "seed"):
            AshlarGenerator(seed=-1)


if __name__ == "__main__":
    unittest.main()
