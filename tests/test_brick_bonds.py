import unittest

from masonpy import EnglishBondGenerator, FlemishBondGenerator, StackBondGenerator, Wall


class BrickBondTests(unittest.TestCase):
    def test_english_bond_alternates_stretcher_and_header_courses(self):
        wall = Wall(12, 4)
        events = EnglishBondGenerator(
            stretcher_width=4, header_width=2, brick_height=2
        ).generate(wall)

        first_course = [event.stone for event in events if event.stone.y == 0]
        second_course = [event.stone for event in events if event.stone.y == 2]
        self.assertEqual([stone.width for stone in first_course], [4, 4, 4])
        self.assertEqual(
            [stone.traits["face"] for stone in first_course], ["stretcher"] * 3
        )
        self.assertEqual([stone.width for stone in second_course], [2, 2, 2, 2, 2, 2])
        self.assertEqual(second_course[0].x, -1)
        self.assertTrue(
            all(stone.traits["face"] == "header" for stone in second_course)
        )
        self.assertTrue(all(cell is not None for cell in wall.occupancy[0]))

    def test_flemish_bond_alternates_faces_within_each_course(self):
        wall = Wall(12, 4)
        FlemishBondGenerator(
            stretcher_width=4, header_width=2, brick_height=2
        ).generate(wall)

        first_course = [stone for stone in wall.stones if stone.y == 0]
        second_course = [stone for stone in wall.stones if stone.y == 2]
        self.assertEqual([stone.width for stone in first_course], [4, 2, 4, 2])
        self.assertEqual(
            [stone.traits["face"] for stone in first_course],
            ["stretcher", "header", "stretcher", "header"],
        )
        self.assertEqual([stone.width for stone in second_course], [4, 2, 4, 2])
        self.assertEqual(
            [stone.traits["face"] for stone in second_course],
            ["stretcher", "header", "stretcher", "header"],
        )
        self.assertEqual(second_course[0].x, -3)

    def test_face_widths_are_validated(self):
        with self.assertRaisesRegex(ValueError, "greater than"):
            EnglishBondGenerator(stretcher_width=2, header_width=2)
        with self.assertRaisesRegex(ValueError, "even integer"):
            FlemishBondGenerator(stretcher_width=4, header_width=3)

    def test_stack_bond_keeps_joints_aligned(self):
        wall = Wall(12, 4)
        StackBondGenerator(stretcher_width=4, brick_height=2).generate(wall)

        first = [(stone.x, stone.width) for stone in wall.stones if stone.y == 0]
        second = [(stone.x, stone.width) for stone in wall.stones if stone.y == 2]
        self.assertEqual(first, [(0, 4), (4, 4), (8, 4)])
        self.assertEqual(second, first)

    def test_flemish_headers_are_centered_over_previous_stretchers(self):
        wall = Wall(12, 4)
        FlemishBondGenerator(stretcher_width=4, header_width=2).generate(wall)
        headers = [
            stone
            for stone in wall.stones
            if stone.y == 2 and stone.traits["face"] == "header"
        ]
        self.assertEqual([stone.x + stone.width / 2 for stone in headers], [2, 8])


if __name__ == "__main__":
    unittest.main()
