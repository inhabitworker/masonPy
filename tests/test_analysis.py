import unittest

from masonpy import (
    AshlarGenerator,
    Stone,
    Wall,
    WallAnalysis,
    horizontal_joints,
    vertical_seams,
)
from masonpy.app import GenerationSession


class WallAnalysisTests(unittest.TestCase):
    def test_global_statistics_and_distributions(self):
        wall = Wall(8, 4)
        for stone in (
            Stone(0, 0, 0, 4, 2),
            Stone(1, 4, 0, 4, 2, {"is_sneck": True}),
            Stone(2, 0, 2, 2, 2),
            Stone(3, 2, 2, 6, 2),
        ):
            wall.add_stone(stone)
        stats = WallAnalysis(wall).statistics()
        self.assertEqual(
            (stats["stone_count"], stats["average_width"], stats["average_height"]),
            (4, 4, 2),
        )
        self.assertEqual((stats["sneck_count"], stats["sneck_proportion"]), (1, 0.25))
        self.assertEqual(
            stats["width_distribution"],
            [
                {"width": 2, "count": 1},
                {"width": 4, "count": 2},
                {"width": 6, "count": 1},
            ],
        )
        self.assertEqual(
            stats["dimension_distribution"][1], {"width": 4, "height": 2, "count": 2}
        )
        self.assertEqual(
            stats["aspect_ratio_distribution"],
            [
                {"ratio": 1, "exact_ratio": "1", "count": 1},
                {"ratio": 2, "exact_ratio": "2", "count": 2},
                {"ratio": 3, "exact_ratio": "3", "count": 1},
            ],
        )
        self.assertEqual(stats["max_vertical_stack"], 1)
        self.assertEqual(
            stats["horizontal_length_distribution"], [{"length": 8, "count": 1}]
        )
        self.assertEqual(
            stats["horizontal_by_elevation"],
            [{"y": 2, "run_count": 1, "total_length": 8, "lengths": [8]}],
        )

    def test_analysis_is_live_after_placements_undo_failure_and_reset(self):
        session = GenerationSession(
            width=5,
            height=2,
            generator_id="ashlar",
            generator_parameters={
                "min_stone_width": 4,
                "max_stone_width": 4,
                "allow_snecks": 0,
                "min_stone_height": 2,
                "max_stone_height": 2,
            },
        )
        analysis = WallAnalysis(session.wall)
        self.assertEqual(analysis.statistics()["stone_count"], 0)
        self.assertEqual(analysis.statistics()["sneck_proportion"], 0)
        self.assertEqual(analysis.horizontal_joints(), ())
        session.generate_all()
        self.assertIsNotNone(session.failure)
        self.assertEqual(analysis.statistics()["stone_count"], 0)
        self.assertEqual(session.to_dict()["analysis"], analysis.to_dict())
        session.undo()
        self.assertEqual(analysis.statistics()["stone_count"], 0)
        session.reset(width=8, height=4)
        self.assertEqual(session.to_dict()["analysis"]["statistics"]["stone_count"], 0)

    def test_partial_runs_remain_distinct_then_merge_and_split_after_undo(self):
        wall = Wall(8, 4)
        wall.add_stone(Stone(0, 0, 0, 8, 2))
        wall.add_stone(Stone(1, 1, 2, 2, 2))
        wall.add_stone(Stone(2, 5, 2, 2, 2))
        analysis = WallAnalysis(wall)
        snapshot = analysis.horizontal_joints()
        self.assertEqual(
            [(r.x, r.y, r.length) for r in snapshot], [(1, 2, 2), (5, 2, 2)]
        )
        self.assertEqual(
            analysis.statistics()["horizontal_by_elevation"][0]["total_length"], 4
        )
        self.assertEqual(analysis.statistics()["max_horizontal_joint_length"], 2)
        wall.add_stone(Stone(3, 3, 2, 2, 2))
        self.assertEqual(
            [(r.x, r.length) for r in analysis.horizontal_joints(2)], [(1, 6)]
        )
        wall.remove_last_stone()
        self.assertEqual(analysis.horizontal_joints(), snapshot)

    def test_irregular_heights_interrupt_joints_and_periodic_runs_join_once(self):
        wall = Wall(8, 6)
        for stone in (
            Stone(0, 0, 0, 3, 4),
            Stone(1, 3, 0, 5, 2),
            Stone(2, 3, 2, 2, 4),
            Stone(3, 5, 2, 3, 2),
            Stone(4, 0, 4, 3, 2),
            Stone(5, 5, 4, 3, 2),
        ):
            wall.add_stone(stone)
        finite = WallAnalysis(wall)
        self.assertEqual(
            [(r.x, r.length) for r in finite.horizontal_joints(4)], [(0, 3), (5, 3)]
        )
        circular = WallAnalysis(wall, wrap_x=True)
        self.assertEqual(
            [(r.x, r.length) for r in circular.horizontal_joints(4)], [(5, 6)]
        )
        self.assertEqual(
            [(r.x, r.length) for r in circular.horizontal_joints(2)], [(3, 5)]
        )
        self.assertEqual(circular.statistics()["horizontal_joint_count"], 2)

    def test_whole_ring_is_canonical_and_crossing_stone_is_not_a_joint(self):
        wall = Wall(8, 4, wrap_x=True)
        wall.add_stone(Stone(0, 6, 0, 4, 4))
        wall.add_stone(Stone(1, 2, 0, 4, 2))
        wall.add_stone(Stone(2, 2, 2, 4, 2))
        self.assertEqual(
            [(r.x, r.y, r.length) for r in horizontal_joints(wall)], [(2, 2, 4)]
        )
        ring = Wall(8, 4, wrap_x=True)
        ring.add_stone(Stone(0, 0, 0, 8, 2))
        ring.add_stone(Stone(1, 0, 2, 8, 2))
        self.assertEqual([(r.x, r.length) for r in horizontal_joints(ring)], [(0, 8)])

    def test_local_periodic_queries_describe_neighbours_support_and_exposure(self):
        wall = Wall(12, 6, wrap_x=True)
        for stone in (
            Stone(0, 10, 0, 4, 2),
            Stone(1, 2, 0, 4, 2),
            Stone(2, 6, 0, 4, 4),
        ):
            wall.add_stone(stone)
        analysis = WallAnalysis(wall)
        self.assertEqual(analysis.stone_at(-1, 0).id, 0)
        self.assertEqual(analysis.joints_below(10, 2, 8), (2,))
        self.assertEqual(
            analysis.adjoining_ids_below(10, 2), (frozenset({2}), frozenset({0}))
        )
        neighbours = analysis.neighbours(10, 2, 8, 2)
        self.assertEqual([s.id for s in neighbours["below"]], [0, 1])
        self.assertEqual([s.id for s in neighbours["left"]], [2])
        self.assertEqual([s.id for s in neighbours["right"]], [2])
        self.assertEqual(neighbours["above"], ())
        self.assertEqual(analysis.neighbours(0, 4, 12)["left"], ())
        exposed = analysis.exposed_edges()
        self.assertIn(
            (10, 2, 8, "top"), [(e.x, e.y, e.length, e.side) for e in exposed]
        )
        self.assertFalse(any(e.x == 0 and e.side in ("left", "right") for e in exposed))
        self.assertEqual(analysis.plateau_after(Stone(3, 10, 2, 8, 2)), (12, 2))

    def test_smaller_stones_can_stop_inside_one_supporting_stone_at_pressured_valley(
        self,
    ):
        selected_widths = []
        for seed in range(20):
            wall = Wall(16, 10, wrap_x=True)
            wall.add_stone(Stone(0, 0, 0, 8, 2))
            wall.add_stone(Stone(1, 8, 0, 8, 6))
            steps = AshlarGenerator(
                seed=seed, min_stone_width=2, max_stone_width=8, enforce_stack=1
            ).generate_incrementally(wall)
            event = next(steps)
            self.assertEqual(event.stone.height, 4)
            self.assertFalse(event.stone.traits["crosses_joint_below"])
            self.assertTrue(all(s.stack_count <= 2 for s in vertical_seams(wall)))
            selected_widths.append(event.stone.width)
            if event.stone.width < 8:
                second = next(steps).stone
                self.assertEqual((second.x, second.y), (event.stone.width, 2))
                self.assertLessEqual(second.x + second.width, 8)
                self.assertEqual(wall.occupancy[1][second.x], 0)
        self.assertGreater(sum(width < 8 for width in selected_widths), 10)
        self.assertGreater(len(set(selected_widths)), 2)


if __name__ == "__main__":
    unittest.main()
