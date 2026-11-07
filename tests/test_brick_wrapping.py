"""Course closure is a generation requirement, not a rendering workaround."""

import unittest

from masonpy import (
    ConstructionFailure,
    EnglishBondGenerator,
    FlemishBondGenerator,
    RunningBondGenerator,
    StackBondGenerator,
    Wall,
    WallGeometry,
)
from masonpy.app import GenerationSession


class BrickWrappingTests(unittest.TestCase):
    def test_incompatible_courses_fail_before_any_placement(self):
        for cls, width, period in (
            (RunningBondGenerator, 50, 4),
            (StackBondGenerator, 50, 4),
            (EnglishBondGenerator, 50, 4),
            (FlemishBondGenerator, 52, 6),
            (RunningBondGenerator, 2, 4),
        ):
            with self.subTest(generator=cls.name):
                wall = Wall(width, 6)
                before = wall.to_dict(), wall.occupancy
                with self.assertLogs("masonpy.generators.brick", "WARNING"):
                    with self.assertRaises(ConstructionFailure) as error:
                        next(cls(course_offset=1).generate_incrementally(wall))
                self.assertIn(f"divisible by {period}", str(error.exception))
                self.assertFalse(error.exception.retry_possible)
                self.assertEqual((wall.to_dict(), wall.occupancy), before)

    def test_english_validates_header_course_before_building_stretchers(self):
        wall = Wall(18, 4)
        with self.assertLogs("masonpy.generators.brick", "WARNING"):
            with self.assertRaises(ConstructionFailure) as error:
                EnglishBondGenerator(stretcher_width=6, header_width=4).generate(wall)
        self.assertEqual(error.exception.y, 2)
        self.assertIn("Course 1", str(error.exception))
        self.assertIn("divisible by 4", str(error.exception))
        self.assertEqual(wall.stones, ())

    def test_failure_is_visible_and_terminal_in_session_until_reset(self):
        session = GenerationSession(width=50, height=4)
        with self.assertLogs("masonpy.generators.brick", "WARNING"):
            session.generate_all()
        failed = session.to_dict()
        self.assertIn("cannot close", failed["failure"]["message"])
        self.assertFalse(failed["failure"]["retry_possible"])
        self.assertEqual(failed["events"], [])
        self.assertFalse(failed["complete"])
        self.assertIsNone(session.step())
        self.assertEqual(session.to_dict(), failed)
        session.reset(width=52, height=4)
        session.generate_all()
        self.assertIsNone(session.failure)
        self.assertTrue(session.complete)
        self.assertTrue(session.wall.wrap_x)

    def test_all_bonds_fill_exactly_one_circumference_at_every_phase(self):
        for cls, width in (
            (RunningBondGenerator, 52),
            (StackBondGenerator, 52),
            (EnglishBondGenerator, 52),
            (FlemishBondGenerator, 54),
        ):
            for offset in range(-7, 8):
                with self.subTest(generator=cls.name, offset=offset):
                    wall = Wall(width, 8)
                    cls(course_offset=offset).generate(wall)
                    self.assertTrue(wall.wrap_x)
                    self.assertTrue(
                        all(cell is not None for row in wall.occupancy for cell in row)
                    )
                    for y in range(0, 8, 2):
                        course = [stone for stone in wall.stones if stone.y == y]
                        self.assertEqual(sum(stone.width for stone in course), width)
                        counts = [0] * width
                        for stone in course:
                            for dx in range(stone.width):
                                counts[(stone.x + dx) % width] += 1
                        self.assertEqual(counts, [1] * width)

    def test_crossing_brick_is_one_id_in_both_ends_and_one_projected_mesh(self):
        wall = Wall(52, 4)
        RunningBondGenerator().generate(wall)
        crossing = next(stone for stone in wall.stones if stone.x < 0)
        self.assertEqual((crossing.x, crossing.width), (-2, 4))
        self.assertEqual(wall.occupancy[2][0], crossing.id)
        self.assertEqual(wall.occupancy[2][-1], crossing.id)
        self.assertEqual(sum(row.count(crossing.id) for row in wall.occupancy), 8)
        for rounding in (0, 0.5, 1):
            geometry = WallGeometry(wall, mode="projected", roundness=rounding)
            data = geometry.to_dict()
            meshes = [mesh for mesh in data["stones"] if mesh["id"] == crossing.id]
            self.assertEqual(len(meshes), 1)
            mesh = meshes[0]
            # Both halves survive mapping, including the part beyond x=0.
            self.assertIn(0.0, geometry.splits(crossing.x, crossing.width))
            for x in (-2, 2):
                expected = geometry.point(x, crossing.y)
                self.assertTrue(
                    any(
                        all(abs(a - b) < 1e-9 for a, b in zip(vertex, expected))
                        for vertex in mesh["vertices"]
                    )
                )
            self.assertEqual(len(data["stones"]), len(wall.stones))

    def test_undo_resumes_periodic_brick_occupancy(self):
        session = GenerationSession(width=52, height=4)
        for _ in range(14):
            session.step()
        crossing = session.events[-1]
        self.assertEqual(crossing.stone.x, -2)
        session.undo()
        self.assertIsNone(session.wall.occupancy[2][-1])
        self.assertIsNone(session.wall.occupancy[2][0])
        self.assertEqual(session.step().to_dict(), crossing.to_dict())
        self.assertEqual(session.wall.occupancy[2][-1], crossing.stone.id)


if __name__ == "__main__":
    unittest.main()
