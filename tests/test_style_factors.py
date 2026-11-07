"""Context, coefficients, and representative fixed-seed style comparisons."""

import logging
import math
import unittest
from unittest.mock import patch

from masonpy import AshlarGenerator, ConstructionFailure, Stone, Wall, WallAnalysis
from masonpy.generators.catalog import get_generator_definition
from masonpy.app import GenerationSession


class StyleFactorTests(unittest.TestCase):
    def test_decimal_catalogue_validation(self):
        definition = get_generator_definition("ashlar")
        generator, values = definition.create(
            {"coursing_factor": 0.37, "snecking_factor": 0.62}
        )
        self.assertEqual(generator.coursing_factor, 0.37)
        self.assertEqual(values["snecking_factor"], 0.62)
        fields = {p["id"]: p for p in definition.to_dict()["parameters"]}
        for name in ("coursing_factor", "snecking_factor"):
            self.assertEqual(fields[name]["type"], "number")
            self.assertEqual((fields[name]["minimum"], fields[name]["maximum"]), (0, 1))
            self.assertEqual(fields[name]["advanced"], name == "coursing_factor")
            for invalid in (-0.1, 1.1, True, "0.5", math.nan, math.inf):
                with self.subTest(name=name, invalid=invalid):
                    with self.assertRaises(ValueError):
                        definition.create({name: invalid})
                    with self.assertRaises(ValueError):
                        AshlarGenerator(**{name: invalid})
        with self.assertRaises(ValueError):
            definition.create({"min_stone_width": 2.5})

    def test_connected_remote_and_completed_alignments_are_separate_and_periodic(self):
        measurements = []
        for shift in range(12):
            wall = Wall(12, 8, wrap_x=True)
            for stone in (
                Stone(0, 0, 0, 2, 3),
                Stone(1, 4, 0, 2, 3),
                Stone(2, 8, 0, 2, 3),
                Stone(3, 8, 3, 2, 2),
            ):
                wall.add_stone(
                    Stone(
                        stone.id,
                        (stone.x + shift) % 12,
                        stone.y,
                        stone.width,
                        stone.height,
                    )
                )
            candidate = Stone(4, (2 + shift) % 12, 0, 2, 3)
            before = wall.to_dict()
            context = WallAnalysis(wall).alignment_after(candidate)
            measurements.append(context)
            self.assertEqual(wall.to_dict(), before)
        self.assertTrue(all(value == measurements[0] for value in measurements))
        self.assertEqual(
            measurements[0],
            dict(
                plateau_extent=6,
                plateau_stones=3,
                connected_extension=4,
                disconnected_skyline_length=0,
                existing_joint_length=2,
                connected_joint_length=0,
                disconnected_joint_length=2,
            ),
        )
        # A candidate at another location aligns with two disconnected tops.
        wall = Wall(12, 8, wrap_x=True)
        wall.add_stone(Stone(0, 0, 0, 2, 3))
        context = WallAnalysis(wall).alignment_after(Stone(1, 5, 0, 2, 3))
        self.assertEqual(context["connected_extension"], 0)
        self.assertEqual(context["disconnected_skyline_length"], 2)

    def test_completed_joint_extension_beside_taller_neighbour_wraps(self):
        for shift in range(8):
            wall = Wall(8, 8, wrap_x=True)
            wall.add_stone(Stone(0, (6 + shift) % 8, 0, 2, 3))
            wall.add_stone(Stone(1, (6 + shift) % 8, 3, 2, 2))
            context = WallAnalysis(wall).alignment_after(Stone(2, shift, 0, 2, 3))
            self.assertEqual(context["connected_extension"], 0)
            self.assertEqual(context["connected_joint_length"], 2)
            self.assertEqual(context["disconnected_joint_length"], 0)

    def test_coursing_weights_interpolate_and_do_not_reward_width_alone(self):
        context = dict(
            connected_extension=8,
            plateau_stones=3,
            disconnected_skyline_length=4,
            connected_joint_length=2,
            disconnected_joint_length=4,
        )
        weights = [
            AshlarGenerator(coursing_factor=c)._style_weight(context, 24)
            for c in (0, 0.25, 0.5, 0.75, 1)
        ]
        self.assertEqual(weights, sorted(weights))
        self.assertEqual(weights[2], 1)
        self.assertAlmostEqual(weights[0] * weights[-1], 1)
        for width in (3, 8):
            wall = Wall(24, 8, wrap_x=True)
            context = WallAnalysis(wall).alignment_after(Stone(0, 0, 0, width, 3))
            self.assertEqual(
                AshlarGenerator(coursing_factor=1)._style_weight(context, 24), 1
            )

    def test_snecks_disabled_and_empty_wall_has_no_deliberate_sneck_opportunity(self):
        for seed in range(12):
            wall = Wall(24, 12)
            first = next(
                AshlarGenerator(seed=seed, snecking_factor=1).generate_incrementally(
                    wall
                )
            )
            self.assertFalse(first.stone.traits["is_sneck"])
            wall = Wall(24, 12)
            try:
                AshlarGenerator(seed=seed, allow_snecks=0).generate(wall)
            except ConstructionFailure:
                pass
            self.assertFalse(any(s.traits["is_sneck"] for s in wall.stones))

    def test_bonding_plateau_and_geometric_fallback_override_style(self):
        for coursing in (0, 0.5, 1):
            for snecking in (0.001, 0.5, 1):
                for enclosing_height in (3, 6):
                    wall = Wall(12, 12, wrap_x=True)
                    for stone in (
                        Stone(0, 0, 0, 4, 2),
                        Stone(1, 4, 0, 4, 2),
                        Stone(2, 8, 0, 4, enclosing_height),
                    ):
                        wall.add_stone(stone)
                    event = next(
                        AshlarGenerator(
                            min_stone_width=3,
                            max_stone_width=5,
                            coursing_factor=coursing,
                            snecking_factor=snecking,
                            enforce_stack=1,
                        ).generate_incrementally(wall)
                    )
                    self.assertEqual(
                        event.stone.y + event.stone.height, enclosing_height
                    )
                    if enclosing_height == 3:
                        self.assertTrue(event.stone.traits["is_sneck"])
                    self.assertLessEqual(
                        WallAnalysis(wall).statistics()["max_vertical_stack"], 2
                    )

    def test_coefficients_preserve_hard_constraints_and_seeded_action_sequences(self):
        for c, s in ((0, 0), (0.4, 0.6), (1, 1)):
            parameters = dict(
                coursing_factor=c, snecking_factor=s, enforce_stack=1, seed=13
            )
            states = []
            for _ in range(2):
                session = GenerationSession(
                    width=24,
                    height=12,
                    generator_id="ashlar",
                    generator_parameters=parameters,
                )
                for _ in range(8):
                    session.step()
                session.undo()
                session.step()
                session.generate_all()
                states.append(session.to_dict())
            self.assertEqual(*states)
            wall = Wall(24, 12)
            try:
                for event in AshlarGenerator(**parameters).generate_incrementally(wall):
                    self.assertLessEqual(
                        WallAnalysis(wall).statistics()["max_vertical_stack"], 2
                    )
                    stone = event.stone
                    if not stone.traits["is_sneck"]:
                        self.assertTrue(
                            3 <= stone.width <= 8 and 2 <= stone.height <= 5
                        )
            except ConstructionFailure:
                pass
            # Whole and incremental consumption produce exactly the same prefix,
            # including any strict terminal failure (not a relaxed completion).
            whole = Wall(24, 12)
            try:
                AshlarGenerator(**parameters).generate(whole)
            except ConstructionFailure:
                pass
            self.assertEqual(wall.to_dict(), whole.to_dict())

    def test_fixed_seed_geometry_and_distribution_tendencies(self):
        def measure(coursing, snecking):
            results = []
            for seed in range(24):
                wall = Wall(36, 20)
                try:
                    AshlarGenerator(
                        seed=seed,
                        coursing_factor=coursing,
                        enforce_stack=0,
                        snecking_factor=snecking,
                    ).generate(wall)
                except ConstructionFailure:
                    # Compare accepted geometry, never recover by relaxing rules.
                    pass
                analysis = WallAnalysis(wall)
                stats = analysis.statistics()
                joints = analysis.horizontal_joints()
                total = max(1, sum(j.length for j in joints))
                continuity = sum(j.length**2 for j in joints) / total
                alignment = (
                    sum(
                        e["total_length"] ** 2 for e in stats["horizontal_by_elevation"]
                    )
                    / total
                )
                deliberate = sum(
                    bool(s.traits["sneck_deliberate"]) for s in wall.stones
                )
                for stone in wall.stones:
                    if stone.traits["sneck_deliberate"]:
                        self.assertIsNotNone(stone.traits["sneck_purpose"])
                self.assertEqual(
                    sum(d["count"] for d in stats["dimension_distribution"]),
                    len(wall.stones),
                )
                results.append(
                    (
                        continuity,
                        alignment,
                        stats["sneck_proportion"],
                        deliberate,
                        stats["average_width"],
                        stats["average_height"],
                    )
                )
            return tuple(
                sum(row[i] for row in results) / len(results) for i in range(6)
            )

        # Capturing warnings allows strictly failed prefixes without noisy logs.
        with patch.object(logging.getLogger("masonpy.generators.ashlar"), "warning"):
            low = measure(0, 0.01)
            middle = measure(0.5, 0.01)
            high = measure(1, 0.01)
            medium_snecks = measure(0.5, 0.5)
            many_snecks = measure(0.5, 1)
        for metric in (0, 1):
            self.assertLess(low[metric], middle[metric])
            self.assertLess(middle[metric], high[metric])
        self.assertLess(middle[2], medium_snecks[2])
        self.assertLess(medium_snecks[2], many_snecks[2])
        self.assertLess(middle[3], medium_snecks[3])
        self.assertLess(medium_snecks[3], many_snecks[3])
        self.assertLess(many_snecks[4], middle[4])


if __name__ == "__main__":
    unittest.main()
