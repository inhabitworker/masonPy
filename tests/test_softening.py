"""Inward-only corner wear, proportional tiny-stone handling and mapped export."""

import math
import unittest

from masonpy import Stone, Wall, WallGeometry, shape_wall
from masonpy.app.workbench import WorkbenchSession
from masonpy.exporting import mesh_stl, wall_svg
from masonpy.processing import ShapedStone
from masonpy.processing.softening import soften_stone
from masonpy.processing.validation import area2, clipper, fixed_path, polygon_operation


class SofteningTests(unittest.TestCase):
    def rectangle(self):
        wall = Wall(12, 6)
        wall.add_stone(Stone(0, 1, 1, 8, 4))
        return wall

    def test_zero_is_exact_identity_and_active_rounding_is_bounded(self):
        wall = self.rectangle()
        original = wall.to_dict()
        raw = shape_wall(wall, joint_width=0.2)
        zero = shape_wall(wall, joint_width=0.2, corner_softening=0)
        self.assertEqual(raw.to_dict(), zero.to_dict())
        self.assertIsNone(zero.unsoftened_stones)
        rounded = shape_wall(wall, joint_width=0.2, corner_softening=0.8)
        self.assertEqual(rounded.unsoftened_stones, raw.stones)
        self.assertIn("unsoftened_stones", rounded.to_dict())
        self.assertEqual(wall.to_dict(), original)
        before, after = fixed_path(raw.stones[0]), fixed_path(rounded.stones[0])
        self.assertGreater(len(after), 4)
        self.assertLess(area2(after), area2(before))
        self.assertFalse(polygon_operation(after, before, clipper().CT_DIFFERENCE))
        self.assertAlmostEqual(rounded.statistics.max_softening_radius, 0.76)
        for axis in (0, 1):
            self.assertLessEqual(
                abs(min(p[axis] for p in before) - min(p[axis] for p in after)), 1000
            )
            self.assertLessEqual(
                abs(max(p[axis] for p in before) - max(p[axis] for p in after)), 1000
            )

    def test_proportional_rounding_keeps_small_stones(self):
        wall = Wall(12, 6)
        wall.add_stone(Stone(0, 0, 0, 4, 4))
        wall.add_stone(Stone(1, 5, 0, 1, 1))
        rounded = shape_wall(wall, joint_width=0.2, corner_softening=1)
        self.assertEqual([s.id for s in rounded.stones], [0, 1])
        self.assertEqual(rounded.statistics.softened_stones, 2)
        self.assertEqual(rounded.statistics.softening_skipped, 0)
        small = shape_wall(wall, joint_width=0.999999, corner_softening=1)
        self.assertEqual(len(small.stones), 2)
        self.assertEqual(small.statistics.softening_skipped, 1)
        self.assertEqual(small.stones[1], small.unsoftened_stones[1])

    def test_narrow_neck_is_not_erased_by_corner_rounding(self):
        stone = ShapedStone(
            0,
            (
                (0, 0),
                (2, 0),
                (2, 0.95),
                (4, 0.95),
                (4, 0),
                (6, 0),
                (6, 2),
                (4, 2),
                (4, 1.05),
                (2, 1.05),
                (2, 2),
                (0, 2),
            ),
        )
        rounded, radius, reduced = soften_stone(stone, 1)
        self.assertGreater(radius, 0)
        self.assertLessEqual(radius, 0.5)
        self.assertEqual(rounded.id, stone.id)
        self.assertFalse(
            polygon_operation(
                fixed_path(rounded), fixed_path(stone), clipper().CT_DIFFERENCE
            )
        )

    def test_period_translation_and_full_ring_seam(self):
        contours = []
        for x in (-2, 10):
            wall = Wall(12, 6, wrap_x=True)
            wall.add_stone(Stone(0, x, 0, 6, 4))
            rounded = shape_wall(
                wall, joint_width=0.2, distortion=0.7, corner_softening=0.8
            )
            contours.append(
                sorted(
                    (round(px - x, 7), round(py, 7))
                    for px, py in rounded.stones[0].vertices
                )
            )
        self.assertEqual(contours[0], contours[1])
        wall = Wall(12, 4, wrap_x=True)
        wall.add_stone(Stone(0, -2, 0, 12, 4))
        rounded = shape_wall(wall, corner_softening=1)
        self.assertEqual(rounded.statistics.softening_skipped, 1)
        self.assertEqual(rounded.stones, rounded.unsoftened_stones)
        self.assertTrue(
            mesh_stl(
                WallGeometry(
                    rounded, mode="projected", roundness=0.25, depth=0.4
                ).to_dict()
            )
        )

    def test_seeded_distorted_walls_keep_ids_and_export_as_closed_shells(self):
        for seed in range(4):
            session = WorkbenchSession(
                width=24,
                height=12,
                generator_id="ashlar",
                generator_parameters={"seed": seed},
            )
            session.generate_all()
            before = session.wall.to_dict()
            rng = session.generator._random.getstate()
            for distortion in (0, 0.7):
                session.apply_shape(0.2, distortion, corner_softening=1)
                shaped = session.shape_result
                self.assertEqual(
                    [s.id for s in shaped.stones], [s.id for s in session.wall.stones]
                )
                for mode, roundness in (
                    ("flat", 0),
                    ("projected", 0),
                    ("projected", 0.25),
                    ("projected", 1),
                ):
                    with self.subTest(
                        seed=seed, distortion=distortion, mode=mode, roundness=roundness
                    ):
                        data = WallGeometry(
                            shaped, mode=mode, roundness=roundness, depth=0.4
                        ).to_dict(primitive="tube", tube_thickness=0.5)
                        self.assertTrue(mesh_stl(data))
                self.assertTrue(wall_svg(shaped))
            self.assertEqual(session.wall.to_dict(), before)
            self.assertEqual(session.generator._random.getstate(), rng)

    def test_large_distorted_wall_has_no_micro_slivers_in_mapped_stl(self):
        session = WorkbenchSession(
            width=104,
            height=60,
            generator_id="ashlar",
            generator_parameters={"seed": 4},
        )
        session.generate_all()
        for strength in (0.5, 1):
            shaped = shape_wall(
                session.wall, joint_width=0.2, distortion=0.7, corner_softening=strength
            )
            self.assertEqual(
                shaped.statistics.softened_stones, len(session.wall.stones)
            )
            mesh = WallGeometry(
                shaped, mode="projected", roundness=0.25, depth=0.25
            ).to_dict(primitive="tube", tube_thickness=1)
            self.assertTrue(mesh_stl(mesh))

    def test_strength_validation_config_round_trip_and_existing_mortar_errors(self):
        wall = self.rectangle()
        for value in (-1, 1.1, True, math.nan, math.inf):
            with self.assertRaises(ValueError):
                shape_wall(wall, corner_softening=value)
        with self.assertRaisesRegex(ValueError, "consumes"):
            shape_wall(wall, joint_width=4, corner_softening=1)
        session = WorkbenchSession(width=24, height=12, generator_id="ashlar")
        import json

        recipe = json.loads(session.export_config()[0])
        recipe["shape"]["corner_softening"] = 0.6
        session.load_config(recipe)
        self.assertEqual(
            session.to_dict()["shape"]["defaults"]["corner_softening"], 0.6
        )
