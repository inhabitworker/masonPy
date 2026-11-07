import unittest

from masonpy import RunningBondGenerator, Wall


class RunningBondTests(unittest.TestCase):
    def test_generation_is_deterministic_and_fills_wall(self):
        def generate():
            wall = Wall(12, 5)
            events = RunningBondGenerator(stretcher_width=4, brick_height=2).generate(
                wall
            )
            shapes = [
                (
                    event.stone.id,
                    event.stone.x,
                    event.stone.y,
                    event.stone.width,
                    event.stone.height,
                )
                for event in events
            ]
            return wall, shapes

        wall_a, shapes_a = generate()
        wall_b, shapes_b = generate()

        self.assertEqual(shapes_a, shapes_b)
        self.assertTrue(all(cell is not None for cell in wall_a.occupancy[0]))
        self.assertEqual(wall_a.occupancy, wall_b.occupancy)

    def test_alternate_course_starts_with_half_brick(self):
        wall = Wall(12, 4)
        RunningBondGenerator(stretcher_width=4, brick_height=2).generate(wall)

        second_course = [stone for stone in wall.stones if stone.y == 2]
        self.assertEqual((second_course[0].x, second_course[0].width), (-2, 4))
        self.assertEqual((second_course[1].x, second_course[1].width), (2, 4))
        self.assertTrue(second_course[0].traits["overhangs_wall"])

    def test_incremental_execution_places_exactly_one_stone(self):
        wall = Wall(8, 4)
        steps = RunningBondGenerator(
            stretcher_width=4, brick_height=2
        ).generate_incrementally(wall)

        self.assertEqual(wall.stones, ())
        first = next(steps)
        self.assertEqual(len(wall.stones), 1)
        self.assertEqual(first.stone, wall.stones[0])
        self.assertIn("course 0", first.explanation)

        second = next(steps)
        self.assertEqual(len(wall.stones), 2)
        self.assertEqual(second.stone.id, 1)

    def test_generation_resumes_from_an_existing_valid_prefix(self):
        wall = Wall(8, 4)
        generator = RunningBondGenerator(stretcher_width=4, brick_height=2)
        steps = generator.generate_incrementally(wall)
        first = next(steps)
        self.assertEqual(first.stone.id, 0)

        resumed = generator.generate_incrementally(wall)
        second = next(resumed)
        self.assertEqual((second.stone.id, second.stone.x), (1, 4))
        self.assertEqual(len(wall.stones), 2)

    def test_generator_parameters_are_validated(self):
        for width in (0, 1, 3, 5):
            with self.subTest(width=width), self.assertRaises(ValueError):
                RunningBondGenerator(stretcher_width=width)
        with self.assertRaises(ValueError):
            RunningBondGenerator(brick_height=0)


if __name__ == "__main__":
    unittest.main()
