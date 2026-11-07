import unittest

from masonpy import PlacementError, Stone, Wall


class WallPlacementTests(unittest.TestCase):
    def test_add_stone_updates_occupancy(self):
        wall = Wall(5, 4)
        wall.add_stone(Stone(id=0, x=1, y=1, width=2, height=2))

        self.assertEqual(wall.occupancy[1][1:3], (0, 0))
        self.assertEqual(wall.occupancy[2][1:3], (0, 0))
        self.assertEqual(len(wall.stones), 1)

    def test_rejects_overlap_without_mutating_wall(self):
        wall = Wall(5, 4)
        first = Stone(id=0, x=1, y=1, width=2, height=2)
        wall.add_stone(first)

        with self.assertRaisesRegex(PlacementError, "overlaps"):
            wall.add_stone(Stone(id=1, x=2, y=2, width=2, height=1))

        self.assertEqual(wall.stones, (first,))
        self.assertIsNone(wall.occupancy[2][3])

    def test_rejects_out_of_bounds_and_invalid_dimensions(self):
        wall = Wall(5, 4)
        invalid = (
            Stone(id=0, x=-1, y=0, width=1, height=1),
            Stone(id=1, x=5, y=0, width=2, height=1),
            Stone(id=2, x=0, y=4, width=1, height=1),
            Stone(id=3, x=0, y=0, width=0, height=1),
        )
        for stone in invalid:
            with self.subTest(stone=stone), self.assertRaises(PlacementError):
                wall.add_stone(stone)

        self.assertEqual(wall.stones, ())

    def test_rejects_duplicate_ids(self):
        wall = Wall(4, 2)
        wall.add_stone(Stone(id=3, x=0, y=0, width=1, height=1))
        with self.assertRaisesRegex(PlacementError, "already in use"):
            wall.add_stone(Stone(id=3, x=2, y=0, width=1, height=1))

    def test_remove_last_stone_restores_occupancy(self):
        wall = Wall(4, 2)
        first = Stone(id=0, x=0, y=0, width=2, height=1)
        second = Stone(id=1, x=2, y=0, width=2, height=1)
        wall.add_stone(first)
        wall.add_stone(second)

        self.assertEqual(wall.remove_last_stone(), second)
        self.assertEqual(wall.stones, (first,))
        self.assertEqual(wall.occupancy[0], (0, 0, None, None))
        self.assertEqual(wall.next_stone_id, 1)
        self.assertEqual(wall.remove_last_stone(), first)
        self.assertIsNone(wall.remove_last_stone())

    def test_overhanging_stone_remains_whole_and_only_occupies_reference_grid(self):
        wall = Wall(8, 2)
        stone = Stone(id=0, x=-2, y=0, width=4, height=1)
        wall.add_stone(stone)

        self.assertEqual(wall.stones, (stone,))
        self.assertEqual(wall.occupancy[0], (0, 0, None, None, None, None, None, None))
        with self.assertRaisesRegex(PlacementError, "overlaps"):
            wall.add_stone(Stone(id=1, x=1, y=0, width=1, height=1))
        self.assertEqual(wall.remove_last_stone(), stone)
        self.assertTrue(all(cell is None for cell in wall.occupancy[0]))

    def test_stone_entirely_outside_horizontal_reference_grid_is_rejected(self):
        wall = Wall(4, 2)
        with self.assertRaisesRegex(PlacementError, "does not intersect"):
            wall.add_stone(Stone(id=0, x=-5, y=0, width=2, height=1))


if __name__ == "__main__":
    unittest.main()
