"""Workbench defaults, inspectable local geometry, and procedural event data."""

import unittest

from masonpy import AshlarGenerator, Stone, Wall, WallAnalysis
from masonpy.generators.catalog import get_generator_definition
from masonpy.app import GenerationSession


class InspectorTests(unittest.TestCase):
    def test_default_configuration_and_catalogue_match(self):
        session = GenerationSession()
        self.assertEqual((session.wall.width, session.wall.height), (104, 60))
        generator, values = get_generator_definition("ashlar").create()
        self.assertTrue(generator.enforce_stack)
        self.assertEqual(
            (
                generator.max_joint_stack,
                generator.coursing_factor,
                generator.snecking_factor,
            ),
            (2, 0.5, 0.2),
        )
        direct = AshlarGenerator()
        self.assertEqual(
            (direct.enforce_stack, direct.coursing_factor, direct.snecking_factor),
            (True, 0.5, 0.2),
        )
        self.assertEqual((values["min_stone_width"], values["max_stone_width"]), (3, 8))

    def test_periodic_stone_local_info_and_support(self):
        wall = Wall(10, 8, wrap_x=True)
        wall.add_stone(Stone(0, 8, 0, 4, 2))
        wall.add_stone(Stone(1, 2, 0, 6, 2))
        wall.add_stone(Stone(2, 9, 2, 4, 3))
        info = WallAnalysis(wall).stone_info(2)
        self.assertEqual(info["geometry"]["area"], 12)
        self.assertEqual(info["geometry"]["occupied_reference_cells"], 12)
        self.assertTrue(info["geometry"]["crosses_reference_boundary"])
        self.assertEqual([s["id"] for s in info["neighbours"]["below"]], [0, 1])
        self.assertEqual(info["supporting_joints"], (2,))
        self.assertEqual(
            info["adjoining_horizontal_joints"][0]["overlap_with_stone"], 4
        )
        self.assertEqual([v["x"] for v in info["surface_over_footprint"]], [9, 0, 1, 2])

    def test_finite_overhang_info_counts_only_reference_occupancy(self):
        wall = Wall(3, 4)
        wall.add_stone(Stone(0, -1, 0, 5, 2))
        info = WallAnalysis(wall).stone_info(0)
        self.assertEqual(info["geometry"]["area"], 10)
        self.assertEqual(info["geometry"]["occupied_reference_cells"], 6)

    def test_info_tracks_prefix_undo_reset_and_does_not_mutate_generation(self):
        session = GenerationSession(width=12, height=6)
        session.step()
        session.step()
        before = session.to_dict()
        info = session.inspect(visible_count=1)
        self.assertEqual(info["analysis"]["statistics"]["stone_count"], 1)
        self.assertEqual(len(info["placements"]), 1)
        self.assertEqual(info["context"]["generated_stones"], 2)
        stone = session.inspect(stone_id=0)
        self.assertEqual(stone["placement"], session.events[0].to_dict())
        self.assertEqual(session.to_dict(), before)
        session.undo()
        with self.assertRaises(ValueError):
            session.inspect(stone_id=1)
        session.reset(width=50, height=30, generator_id="ashlar")
        self.assertEqual(session.inspect()["analysis"]["statistics"]["stone_count"], 0)
        for count in (-1, 1, True, 0.5):
            with self.assertRaises(ValueError):
                session.inspect(visible_count=count)

    def test_procedural_ashlar_event_reports_options_without_extra_random_draws(self):
        session = GenerationSession(generator_id="ashlar")
        first = session.step()
        decision = first.decision
        self.assertTrue(
            first.explanation.startswith(
                f"Added at [{first.stone.x}, {first.stone.y}]:\n"
            )
        )
        for heading in ("Target:", "Width:", "Height:", "Selection:"):
            self.assertIn(heading, first.explanation)
        options = decision["selection"]["options"]
        self.assertGreater(len(options), 0)
        self.assertAlmostEqual(
            sum(o["weight"] for o in options), decision["selection"]["total_weight"]
        )
        self.assertIn(first.stone.width, decision["width"]["valid_options"])
        self.assertEqual(decision["selection"]["stack_limit"], 2)
        self.assertEqual(
            session.inspect(stone_id=first.stone.id)["placement"]["decision"], decision
        )

    def test_brick_event_explains_fixed_pattern_and_height_closure(self):
        session = GenerationSession(width=8, height=3)
        session.generate_all()
        event = session.events[-1]
        self.assertEqual(event.decision["height"]["chosen"], 1)
        self.assertIn("no randomness", event.explanation)
        self.assertIn("Height: 1", event.explanation)


if __name__ == "__main__":
    unittest.main()
