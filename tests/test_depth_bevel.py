"""Deterministic extrusion variation, bounded chamfers and atomic fallback behaviour."""

import json
import math
import unittest
from unittest.mock import patch

from masonpy import Stone, Wall, WallGeometry, shape_wall
from masonpy.app.workbench import WorkbenchSession
from masonpy.exporting import mesh_stl, shell_triangles
from masonpy.processing import ShapedStone, ShapedWall, WallDescription
from test_geometry import volume


class DepthBevelTests(unittest.TestCase):
    def source(self):
        wall = Wall(24, 12, wrap_x=True)
        wall.add_stone(Stone(7, 1, 1, 4, 3))
        wall.add_stone(Stone(19, 8, 1, 3, 4))
        return wall

    def test_disabled_details_preserve_exact_buffers_and_seed_is_inert(self):
        wall = self.source()
        for source in (wall, shape_wall(wall, joint_width=0.2, corner_softening=0.8)):
            baseline = WallGeometry(
                source, mode="projected", roundness=0.25, depth=0.4
            ).to_dict()
            explicit = WallGeometry(
                source,
                mode="projected",
                roundness=0.25,
                depth=0.4,
                depth_variation=0,
                bevel=0,
                detail_seed=99,
            ).to_dict()
            self.assertEqual(explicit, baseline)

    def test_random_depth_is_bounded_id_based_and_preserves_rear_and_triangle_count(
        self,
    ):
        wall = self.source()
        before = wall.to_dict()
        geometry = WallGeometry(wall, depth=0.4, depth_variation=0.2, detail_seed=12)
        other = WallGeometry(wall, depth=0.4, depth_variation=0.2, detail_seed=12)
        expected = {
            stone.id: other.depth_for(stone.id) for stone in reversed(wall.stones)
        }
        for stone in wall.stones:
            depth = geometry.depth_for(stone.id)
            self.assertEqual(depth, expected[stone.id])
            self.assertGreaterEqual(depth, 0.32)
            self.assertLessEqual(depth, 0.48)
            mesh = geometry.stone_mesh(stone)
            base = WallGeometry(wall, depth=0.4).stone_mesh(stone)
            self.assertEqual(len(mesh.triangles), len(base.triangles))
            self.assertEqual(
                {p for p in mesh.vertices if p[2] == 0},
                {p for p in base.vertices if p[2] == 0},
            )
            self.assertAlmostEqual(volume(mesh), stone.width * stone.height * depth)
        self.assertNotEqual(expected[7], expected[19])
        self.assertNotEqual(
            geometry.depth_for(7),
            WallGeometry(
                wall, depth=0.4, depth_variation=0.2, detail_seed=13
            ).depth_for(7),
        )
        self.assertEqual(wall.to_dict(), before)
        geometry.to_dict()
        geometry.to_dict()
        self.assertEqual(geometry.depth_for(7), expected[7])

    def test_chamfer_has_expected_volume_and_keeps_the_rear_fixed(self):
        wall = self.source()
        geometry = WallGeometry(wall, depth=0.4, bevel=0.05)
        stone = wall.stones[0]
        mesh = geometry.stone_mesh(stone)
        expected = 4 * 3 * 0.4 - (4 + 3) * 0.05**2 + 4 / 3 * 0.05**3
        self.assertAlmostEqual(volume(mesh), expected)
        self.assertEqual(min(p[2] for p in mesh.vertices), 0)
        self.assertEqual(max(p[2] for p in mesh.vertices), 0.4)
        self.assertTrue(shell_triangles(mesh.to_dict(), 1))
        self.assertEqual(geometry._treatments[7]["bevel"], 0.05)

    def test_tiny_stone_and_large_bevel_are_limited_without_omission(self):
        wall = Wall(12, 6)
        wall.add_stone(Stone(0, 0, 0, 1, 1))
        shape = shape_wall(wall, joint_width=0.95, corner_softening=1)
        data = WallGeometry(
            shape, depth=0.02, depth_variation=0.8, bevel=1000
        ).to_dict()
        self.assertEqual(len(data["stones"]), 1)
        treatment = data["stones"][0]["treatment"]
        self.assertLessEqual(treatment["bevel"], treatment["depth"] * 0.45)
        self.assertTrue(treatment["bevel_reduced"] or treatment["bevel_skipped"])
        self.assertEqual(data["statistics"]["omitted_stones"], 0)
        self.assertTrue(mesh_stl(data))

    def test_pointy_contour_and_complexity_limit_keep_valid_unbeveled_shells(self):
        wall = Wall(12, 6)
        wall.add_stone(Stone(0, 0, 0, 4, 1))
        source = WallDescription.from_wall(wall)
        pointed = ShapedWall(
            source, stones=(ShapedStone(0, ((0, 0), (4, 0), (0.02, 0.05))),)
        )
        data = WallGeometry(pointed, depth=0.4, bevel=0.05).to_dict()
        self.assertEqual(data["statistics"]["skipped_bevel_ids"], [0])
        self.assertTrue(mesh_stl(data))
        shape = shape_wall(wall, joint_width=0.2, corner_softening=1)
        with patch("masonpy.geometry.projection.MAX_BEVEL_VERTICES", 4):
            data = WallGeometry(shape, depth=0.4, bevel=0.05).to_dict()
        self.assertEqual(data["statistics"]["skipped_bevel_ids"], [0])
        self.assertIn("complexity", data["stones"][0]["treatment"]["bevel_note"])
        self.assertTrue(mesh_stl(data))

    def test_periodic_crossing_and_full_ring_keep_whole_stones(self):
        results = []
        for x in (-2, 22):
            wall = Wall(24, 12, wrap_x=True)
            wall.add_stone(Stone(7, x, 1, 6, 4))
            shape = shape_wall(
                wall, joint_width=0.2, distortion=0.5, corner_softening=0.8
            )
            data = WallGeometry(
                shape,
                mode="projected",
                roundness=0.25,
                depth=0.4,
                depth_variation=0.2,
                detail_seed=3,
                bevel=0.05,
            ).to_dict()
            results.append(data["stones"][0]["treatment"])
            self.assertEqual(data["statistics"]["beveled_stones"], 1)
            self.assertTrue(mesh_stl(data))
        self.assertEqual(results[0], results[1])
        wall = Wall(24, 4, wrap_x=True)
        wall.add_stone(Stone(7, -2, 0, 24, 4))
        data = WallGeometry(
            shape_wall(wall),
            mode="projected",
            depth=0.4,
            bevel=0.05,
            depth_variation=0.2,
        ).to_dict()
        self.assertEqual(data["statistics"]["skipped_bevel_ids"], [7])
        self.assertEqual(data["stones"][0]["treatment"]["bevel_note"], "Full-ring seam")
        self.assertTrue(mesh_stl(data))

    def test_zero_depth_stays_surface_only_and_does_not_attempt_bevel(self):
        data = WallGeometry(
            self.source(), depth=0, bevel=1, depth_variation=0.9
        ).to_dict()
        self.assertEqual(data["statistics"]["beveled_stones"], 0)
        self.assertEqual(data["statistics"]["skipped_bevel_ids"], [7, 19])
        self.assertEqual(
            {p[2] for stone in data["stones"] for p in stone["vertices"]}, {0}
        )

    def test_failed_varied_depth_falls_back_and_bad_base_is_an_identified_error(self):
        wall = self.source()
        geometry = WallGeometry(wall, depth=0.4, depth_variation=0.2)
        with patch(
            "masonpy.exporting.shell_triangles",
            side_effect=[ValueError("precision"), None],
        ):
            geometry.stone_mesh(wall.stones[0])
        self.assertTrue(geometry._treatments[7]["depth_fallback"])
        self.assertEqual(geometry._treatments[7]["depth"], 0.4)
        with self.assertRaisesRegex(ValueError, "Stone 7: invalid base geometry"):
            geometry.contour_mesh(ShapedStone(7, ((0, 0), (0, 1), (1, 0))))

    def test_compound_sources_map_and_export_without_changing_upstream_rng(self):
        for seed in (1, 4):
            session = WorkbenchSession(
                width=24,
                height=12,
                generator_id="ashlar",
                generator_parameters={"seed": seed},
            )
            session.generate_all()
            before, rng = session.wall.to_dict(), session.generator._random.getstate()
            session.apply_shape(0.2, 0.7, corner_softening=0.8)
            shape = session.shape_result.to_dict()
            for mode, roundness in (
                ("flat", 0),
                ("projected", 0),
                ("projected", 0.25),
                ("projected", 1),
            ):
                with self.subTest(seed=seed, mode=mode, roundness=roundness):
                    session.build_3d(
                        dict(
                            mode=mode,
                            roundness=roundness,
                            depth=0.25,
                            depth_variation=0.2,
                            bevel=0.05,
                            detail_seed=17,
                        )
                    )
                    self.assertEqual(
                        len(session.build_result["stones"]), len(session.wall.stones)
                    )
                    self.assertTrue(mesh_stl(session.build_result))
                    self.assertTrue(mesh_stl(session.build_result, scale=0.25))
            self.assertEqual(session.wall.to_dict(), before)
            self.assertEqual(session.shape_result.to_dict(), shape)
            self.assertEqual(session.generator._random.getstate(), rng)

    def test_build_failure_is_atomic_and_configuration_round_trips_new_controls(self):
        session = WorkbenchSession(width=24, height=12, generator_id="ashlar")
        session.generate_all()
        session.apply_shape(0.2, 0.7, corner_softening=0.8)
        session.build_3d(dict(depth_variation=0.2, bevel=0.05, detail_seed=9))
        previous, revision = session.build_result, session.build_revision
        config = json.loads(session.export_config()[0])
        self.assertEqual(config["build"]["detail_seed"], 9)
        other = WorkbenchSession()
        other.load_config(config)
        self.assertEqual(other.to_dict()["build"]["defaults"]["bevel"], 0.05)
        with patch("masonpy.geometry.projection.MAX_BUILD_TRIANGLES", 1):
            with self.assertRaisesRegex(ValueError, "million triangles"):
                session.build_3d(dict(bevel=0.06))
        self.assertIs(session.build_result, previous)
        self.assertEqual(session.build_revision, revision)
        self.assertIn("Build failed", session.build_events[-1])

    def test_large_wall_bevels_successfully_with_bounded_offset_cache(self):
        session = WorkbenchSession(
            width=104,
            height=60,
            generator_id="ashlar",
            generator_parameters={"seed": 4},
        )
        session.generate_all()
        session.apply_shape(0.2, 0.7, corner_softening=0.8)
        geometry = WallGeometry(
            session.shape_result,
            mode="projected",
            roundness=0.25,
            depth=0.25,
            depth_variation=0.15,
            bevel=0.05,
        )
        data = geometry.to_dict(primitive="tube", tube_thickness=1)
        self.assertEqual(data["statistics"]["beveled_stones"], len(session.wall.stones))
        self.assertEqual(len(geometry._offsets), 2)
        self.assertLess(sum(len(s["triangles"]) for s in data["stones"]), 120000)
        self.assertTrue(mesh_stl(data))

    def test_invalid_detail_settings_do_not_mutate_active_state(self):
        session = WorkbenchSession()
        config = json.loads(session.export_config()[0])
        before = session.to_dict()
        for key, value in (
            ("depth_variation", -1),
            ("depth_variation", 1),
            ("depth_variation", True),
            ("detail_seed", 1.5),
            ("detail_seed", False),
            ("bevel", math.inf),
            ("bevel", -1),
        ):
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    WallGeometry(self.source(), **{key: value})
                bad = json.loads(json.dumps(config))
                bad["build"][key] = value
                with self.assertRaises(ValueError):
                    session.load_config(bad)
                self.assertEqual(session.to_dict(), before)
