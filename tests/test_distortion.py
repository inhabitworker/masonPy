"""Shared periodic distortion, non-destructive processing and mapped-shell regressions."""

from copy import deepcopy
import math
import subprocess
import sys
import unittest

from masonpy import Stone, Wall, WallGeometry, shape_wall
from masonpy.app import WorkbenchSession
from masonpy.exporting import mesh_stl
from masonpy.processing import (
    ShapeSettings,
    ShapedStone,
    ShapedWall,
    WallDescription,
    build_topology,
)
from masonpy.processing.field import distort_boundaries
from masonpy.processing.inset import inset_stone
from masonpy.processing.validation import validate_arrangement


def junction_wall():
    """Construct both a seam-crossing horizontal T and a vertical T without filling the wall."""
    wall = Wall(12, 8, wrap_x=True)
    for stone in (
        Stone(0, 10, 0, 6, 4),
        Stone(1, 4, 0, 6, 2),
        Stone(2, 4, 2, 6, 2),
        Stone(3, 1, 4, 3, 2),
    ):
        wall.add_stone(stone)
    return wall


class SharedTopologyTests(unittest.TestCase):
    def test_junctions_are_inserted_on_both_axes_across_the_seam(self):
        topology = build_topology(WallDescription.from_wall(junction_wall()))
        nodes = {(v.x, v.y): i for i, v in enumerate(topology.vertices)}
        by_id = {s.id: s for s in topology.stones}
        seam_node, vertical_node = nodes[(1, 4)], nodes[(10, 2)]
        self.assertIn(seam_node, [r.vertex for r in by_id[0].vertices])
        self.assertIn(seam_node, [r.vertex for r in by_id[3].vertices])
        self.assertIn(vertical_node, [r.vertex for r in by_id[0].vertices])
        self.assertEqual(
            next(r.period for r in by_id[0].vertices if r.vertex == seam_node), 1
        )
        self.assertEqual(
            next(r.period for r in by_id[3].vertices if r.vertex == seam_node), 0
        )
        self.assertGreater(topology.inserted_vertices, 0)
        moved, stats = distort_boundaries(topology, ShapeSettings(distortion=1))
        points = {}
        for source, result in zip(topology.stones, moved):
            for ref, point in zip(source.vertices, result.vertices):
                if ref.vertex == seam_node:
                    points[source.id] = point
        self.assertAlmostEqual(points[0][0] - points[3][0], 12)
        self.assertEqual(points[0][1], points[3][1])
        self.assertGreater(stats.max_displacement, 0)

    def test_finite_ends_are_not_merged_and_periodic_occurrences_keep_their_period(
        self,
    ):
        finite = Wall(12, 8)
        finite.add_stone(Stone(0, 0, 0, 12, 8))
        topology = build_topology(WallDescription.from_wall(finite))
        self.assertEqual(len(topology.vertices), 4)
        periodic = Wall(12, 8, wrap_x=True)
        periodic.add_stone(Stone(0, 0, 0, 12, 8))
        topology = build_topology(WallDescription.from_wall(periodic))
        self.assertEqual(len(topology.vertices), 2)
        self.assertEqual({r.period for r in topology.stones[0].vertices}, {0, 1})

    def test_translated_whole_stones_get_identical_periodic_distortion(self):
        outputs = []
        for x in (-2, 10):
            wall = Wall(12, 8, wrap_x=True)
            wall.add_stone(Stone(0, x, 2, 4, 3))
            outputs.append(
                shape_wall(wall, distortion=0.8, joint_width=0.2).stones[0].vertices
            )
        for a, b in zip(*outputs):
            self.assertAlmostEqual(b[0] - a[0], 12)
            self.assertEqual(a[1], b[1])


class DistortionTests(unittest.TestCase):
    def test_fractional_deterministic_movement_and_unchanged_source(self):
        wall = junction_wall()
        before, occupancy = deepcopy(wall.to_dict()), wall.occupancy
        kwargs = dict(joint_width=0.2, distortion=0.7, seed=31, variation_scale=3)
        first = shape_wall(wall, **kwargs)
        second = shape_wall(wall, **kwargs)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.source.to_dict(), before)
        self.assertEqual(wall.to_dict(), before)
        self.assertEqual(wall.occupancy, occupancy)
        self.assertTrue(
            any(
                value != int(value)
                for s in first.stones
                for p in s.vertices
                for value in p
            )
        )
        changed = shape_wall(wall, **{**kwargs, "seed": 32})
        self.assertNotEqual(first.stones, changed.stones)
        self.assertEqual([s.id for s in first.stones], [s.id for s in wall.stones])

    def test_movement_bounds_and_base_top_constraints(self):
        topology = build_topology(WallDescription.from_wall(junction_wall()))
        settings = ShapeSettings(distortion=1, variation_scale=0.25)
        stones, _ = distort_boundaries(topology, settings)
        for source, result in zip(topology.stones, stones):
            for ref, (x, y) in zip(source.vertices, result.vertices):
                vertex = topology.vertices[ref.vertex]
                origin = vertex.x + ref.period * topology.width, vertex.y
                self.assertLessEqual(math.dist(origin, (x, y)), vertex.allowance + 1e-7)
                if vertex.y in (0, topology.height):
                    self.assertEqual(y, vertex.y)

    def test_zero_distortion_retains_exact_rectangle_path_and_settings(self):
        wall = junction_wall()
        shaped = shape_wall(
            wall, joint_width=0.2, distortion=0, seed=200, variation_scale=0.25
        )
        for source, result in zip(wall.stones, shaped.stones):
            self.assertEqual(
                result.vertices,
                (
                    (source.x + 0.1, source.y + 0.1),
                    (source.x + source.width - 0.1, source.y + 0.1),
                    (source.x + source.width - 0.1, source.y + source.height - 0.1),
                    (source.x + 0.1, source.y + source.height - 0.1),
                ),
            )
        self.assertEqual(shaped.settings.seed, 200)
        self.assertEqual(shaped.statistics.max_displacement, 0)

    def test_invalid_settings_and_foreign_topology_are_rejected(self):
        for values in (
            {"distortion": -1},
            {"distortion": 1.1},
            {"distortion": math.nan},
            {"seed": True},
            {"seed": 1.5},
            {"seed": -1},
            {"variation_scale": 0},
            {"variation_scale": math.inf},
        ):
            with self.assertRaises(ValueError):
                shape_wall(junction_wall(), **values)
        source = WallDescription.from_wall(junction_wall())
        topology = build_topology(source)
        wall = Wall(12, 8, wrap_x=True)
        wall.add_stone(Stone(0, 0, 0, 4, 2))
        with self.assertRaisesRegex(ValueError, "does not match"):
            shape_wall(wall, distortion=0.5, topology=topology)

    def test_overlap_containment_self_intersection_and_periodic_overlap_are_rejected(
        self,
    ):
        square = ShapedStone(0, ((0, 0), (4, 0), (4, 4), (0, 4)))
        contained = ShapedStone(1, ((1, 1), (2, 1), (2, 2), (1, 2)))
        with self.assertRaisesRegex(ValueError, "overlaps"):
            validate_arrangement((square, contained), 12, False)
        crossing = ShapedStone(2, ((10, 0), (14, 0), (14, 2), (10, 2)))
        with self.assertRaisesRegex(ValueError, "periodic"):
            validate_arrangement((square, crossing), 12, True)
        bow = ShapedStone(3, ((0, 0), (3, 3), (0, 3), (3, 0)))
        with self.assertRaises(ValueError):
            validate_arrangement((bow,), 12, False)

    def test_split_and_consumed_insets_are_errors_not_silent_fragments(self):
        neck = ShapedStone(
            12,
            (
                (0, 0),
                (3, 0),
                (3, 1.8),
                (5, 1.8),
                (5, 0),
                (8, 0),
                (8, 4),
                (5, 4),
                (5, 2.2),
                (3, 2.2),
                (3, 4),
                (0, 4),
            ),
        )
        with self.assertRaisesRegex(ValueError, "splits stone 12"):
            inset_stone(neck, 0.8)
        tiny = ShapedStone(5, ((0, 0), (1, 0), (1, 1), (0, 1)))
        with self.assertRaisesRegex(ValueError, "consumes stone 5"):
            inset_stone(tiny, 2)

    def test_core_import_does_not_load_clipper_or_app(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import masonpy,sys; assert 'pyclipper' not in sys.modules; assert 'masonpy.app' not in sys.modules",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class DistortionSessionTests(unittest.TestCase):
    def test_failed_shape_preserves_all_applied_results_and_source_revisions(self):
        session = WorkbenchSession(width=24, height=12)
        session.generate_all()
        session.apply_shape(0.2, distortion=0.6)
        session.build_3d({"mode": "projected", "roundness": 0.5, "depth": 0.4})
        before = session.to_dict()
        mesh = session.geometry_snapshot()
        result = session.shape_result
        with self.assertRaisesRegex(ValueError, "consumes"):
            session.apply_shape(20, distortion=1)
        self.assertIs(session.shape_result, result)
        self.assertEqual(session.geometry_snapshot(), mesh)
        self.assertTrue(session.build_current)
        after = session.to_dict()
        for key in ("wall", "events", "generator", "wall_revision", "build"):
            self.assertEqual(after[key], before[key])
        self.assertIn("Apply failed", after["shape"]["events"][-1])

    def test_topology_is_reused_until_the_logical_source_changes(self):
        session = WorkbenchSession(width=24, height=12)
        session.generate_all()
        session.apply_shape(0.2, distortion=0.5)
        topology = session._shape_topology
        revision = session.shape_revision
        session.apply_shape(0.2, distortion=0.5)
        self.assertEqual(session.shape_revision, revision)
        session.apply_shape(0.2, distortion=0.7, seed=2)
        self.assertIs(session._shape_topology, topology)
        session.undo()
        session.apply_shape(0.2, distortion=0.7)
        self.assertIsNot(session._shape_topology, topology)
        self.assertEqual(session.shape_result.source.to_dict(), session.wall.to_dict())

    def test_processing_and_failed_processing_do_not_consume_generator_randomness(self):
        inspected = WorkbenchSession(
            width=24, height=12, generator_id="ashlar", generator_parameters={"seed": 1}
        )
        control = WorkbenchSession(
            width=24, height=12, generator_id="ashlar", generator_parameters={"seed": 1}
        )
        for _ in range(4):
            self.assertEqual(inspected.step(), control.step())
        before = inspected.wall.to_dict()
        inspected.apply_shape(0.2, distortion=0.6)
        with self.assertRaises(ValueError):
            inspected.apply_shape(20, distortion=0.7)
        self.assertEqual(inspected.wall.to_dict(), before)
        for _ in range(4):
            self.assertEqual(inspected.step(), control.step())


class DistortedMappingTests(unittest.TestCase):
    def test_zero_mortar_neighbours_share_the_same_extrusion_diagonal(self):
        source = WallDescription.from_wall(Wall(40, 10, wrap_x=True))
        left = ShapedStone(0, ((1, 1), (4, 1), (5, 4), (1, 4)))
        right = ShapedStone(1, ((4, 1), (8, 1), (8, 4), (5, 4)))
        shaped = ShapedWall(source, 0, (left, right))
        geometry = WallGeometry(shaped, mode="projected", depth=0.5)
        signatures = []
        for stone in (left, right):
            mesh = geometry.contour_mesh(stone)
            signatures.append(
                {
                    tuple(
                        sorted(
                            tuple(round(v, 9) for v in mesh.vertices[i])
                            for i in triangle
                        )
                    )
                    for triangle in mesh.triangles
                }
            )
        self.assertEqual(len(signatures[0] & signatures[1]), 2)

    def test_tiny_scored_corners_at_low_strength_remain_closed(self):
        for generator, gap in (("ashlar", 0), ("english_bond", 0.2)):
            session = WorkbenchSession(width=48, height=16, generator_id=generator)
            session.generate_all()
            shaped = shape_wall(
                session.wall, distortion=0.01, joint_width=gap, variation_scale=6
            )
            geometry = WallGeometry(
                shaped, mode="projected", roundness=1, depth=0.4
            ).to_dict()
            self.assertGreater(len(mesh_stl(geometry)), 84)

    def test_full_ring_can_have_a_span_greater_than_one_circumference(self):
        wall = Wall(40, 12, wrap_x=True)
        wall.add_stone(Stone(0, 0, 2, 40, 4))
        shaped = shape_wall(wall, distortion=1)
        xs = [p[0] for p in shaped.stones[0].vertices]
        self.assertGreater(max(xs) - min(xs), 40)
        for rounding in (0, 0.5, 1):
            self.assertGreater(
                len(
                    mesh_stl(
                        WallGeometry(
                            shaped, mode="projected", roundness=rounding, depth=0.4
                        ).to_dict()
                    )
                ),
                84,
            )

    def test_seeded_distorted_bonds_map_and_export_with_consistent_shells(self):
        for generator in (
            "running_bond",
            "stack_bond",
            "english_bond",
            "flemish_bond",
            "ashlar",
        ):
            session = WorkbenchSession(width=48, height=12, generator_id=generator)
            session.generate_all()
            for gap in (0, 0.2):
                shaped = shape_wall(
                    session.wall, distortion=0.7, variation_scale=3.5, joint_width=gap
                )
                for mode, rounding in (
                    ("flat", 0),
                    ("projected", 0),
                    ("projected", 0.5),
                    ("projected", 1),
                ):
                    geometry = WallGeometry(
                        shaped, mode=mode, roundness=rounding, depth=0.4
                    ).to_dict()
                    self.assertEqual(
                        [s["id"] for s in geometry["stones"]],
                        [s.id for s in session.wall.stones],
                    )
                    self.assertGreater(len(mesh_stl(geometry)), 84)
