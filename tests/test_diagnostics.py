import unittest

from masonpy import Stone, Wall, vertical_seams, report_vertical_seams
from masonpy.generators import (
    StackBondGenerator,
    RunningBondGenerator,
    FlemishBondGenerator,
)


class SeamTests(unittest.TestCase):
    def test_continuous_joint_across_different_heights_and_ids(self):
        wall = Wall(4, 6)
        for stone in (
            Stone(0, 0, 0, 2, 6),
            Stone(1, 2, 0, 2, 2),
            Stone(2, 2, 2, 2, 4),
        ):
            wall.add_stone(stone)
        self.assertEqual(
            [(s.x, s.y, s.length) for s in vertical_seams(wall)], [(2, 0, 6)]
        )
        seam = vertical_seams(wall)[0]
        self.assertEqual(
            (seam.left_count, seam.right_count, seam.stack_count), (1, 2, 2)
        )

    def test_tall_stone_against_three_small_stones_at_periodic_boundary(self):
        wall = Wall(8, 6, wrap_x=True)
        wall.add_stone(Stone(0, 4, 0, 4, 6))
        for index in range(3):
            wall.add_stone(Stone(index + 1, 0, index * 2, 4, 2))
        seams = vertical_seams(wall, wrap_x=True)
        self.assertEqual([s.x for s in seams], [0, 4])
        self.assertTrue(all(s.stack_count == 3 and s.length == 6 for s in seams))
        self.assertEqual((seams[0].left_count, seams[0].right_count), (1, 3))

    def test_uniform_stack_counts_and_partial_joint_counts(self):
        wall = Wall(8, 6, wrap_x=True)
        for index, y in enumerate((0, 2, 4)):
            wall.add_stone(Stone(index * 2, 0, y, 4, 2))
            if y < 4:
                wall.add_stone(Stone(index * 2 + 1, 4, y, 4, 2))
        self.assertTrue(
            all(
                s.stack_count == 2 and s.length == 4
                for s in vertical_seams(wall, wrap_x=True)
            )
        )

    def test_spanning_stone_interrupts_joint(self):
        wall = Wall(4, 5)
        for stone in (
            Stone(0, 0, 0, 2, 2),
            Stone(1, 2, 0, 2, 2),
            Stone(2, 0, 2, 4, 1),
            Stone(3, 0, 3, 2, 2),
            Stone(4, 2, 3, 2, 2),
        ):
            wall.add_stone(stone)
        self.assertEqual(
            [(s.y, s.length) for s in vertical_seams(wall)], [(0, 2), (3, 2)]
        )

    def test_partial_wall_excludes_exposed_edges(self):
        wall = Wall(4, 6)
        wall.add_stone(Stone(0, 0, 0, 2, 5))
        self.assertEqual(vertical_seams(wall), ())
        wall.add_stone(Stone(1, 2, 0, 2, 2))
        self.assertEqual(vertical_seams(wall)[0].length, 2)

    def test_logical_boundary_joint_and_crossing_stone(self):
        wall = Wall(8, 2)
        wall.add_stone(Stone(0, -2, 0, 4, 2))
        wall.add_stone(Stone(1, 2, 0, 4, 2))
        seams = vertical_seams(wall, wrap_x=True)
        self.assertEqual([s.x for s in seams], [2, 6])
        flat = Wall(8, 2)
        flat.add_stone(Stone(0, 0, 0, 4, 2))
        flat.add_stone(Stone(1, 4, 0, 4, 2))
        self.assertEqual([s.x for s in vertical_seams(flat, wrap_x=True)], [0, 4])
        self.assertEqual([s.x for s in vertical_seams(flat)], [4])

    def test_conflicting_periodic_projection_is_rejected(self):
        wall = Wall(6, 2)
        wall.add_stone(Stone(0, -2, 0, 4, 2))
        wall.add_stone(Stone(1, 2, 0, 4, 2))
        with self.assertRaisesRegex(ValueError, "overlaps"):
            vertical_seams(wall, wrap_x=True)

    def test_report_is_explicit(self):
        wall = Wall(8, 4)
        StackBondGenerator().generate(wall)
        with self.assertLogs("masonpy.analysis.joints", level="INFO") as logs:
            report_vertical_seams(wall)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("longest 4", logs.output[0])

    def test_cumulative_phase_preserves_normal_stagger(self):
        for cls, expected in (
            (StackBondGenerator, [0, -1, -2, -3, 0]),
            (RunningBondGenerator, [0, -3, -2, -1, 0]),
        ):
            wall = Wall(12, 10)
            cls(course_offset=1).generate(wall)
            self.assertEqual(
                [min(s.x for s in wall.stones if s.y == y) for y in range(0, 10, 2)],
                expected,
            )
            self.assertTrue(all(s.width > 0 for s in wall.stones))

    def test_flemish_phase_can_pass_a_whole_face_without_losing_coverage(self):
        wall = Wall(12, 12)
        FlemishBondGenerator(course_offset=2).generate(wall)
        # Compatible circumference remains a valid periodic projection at every phase.
        vertical_seams(wall, wrap_x=True)
        for y in range(wall.height):
            covered = {
                (stone.x + dx) % wall.width
                for stone in wall.stones
                if stone.y <= y < stone.y + stone.height
                for dx in range(stone.width)
            }
            self.assertEqual(covered, set(range(wall.width)))


if __name__ == "__main__":
    unittest.main()
