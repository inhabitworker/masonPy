"""Projection is testable without JavaScript, Three.js or a browser."""

import math
import unittest
from collections import Counter

from masonpy import Stone, Wall, WallGeometry
from masonpy.app import GenerationSession


def normal(a, b, c):
    u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
    return (
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    )


def area(mesh):
    return sum(
        math.sqrt(sum(n * n for n in normal(*(mesh.vertices[i] for i in triangle)))) / 2
        for triangle in mesh.triangles
    )


def volume(mesh):
    result = 0
    for triangle in mesh.triangles:
        a, b, c = (mesh.vertices[i] for i in triangle)
        n = normal((0, 0, 0), b, c)
        result += sum(a[i] * n[i] for i in range(3)) / 6
    return result


class GeometryTests(unittest.TestCase):
    def assertClean(self, mesh):
        signatures = set()
        for indices in mesh.triangles:
            points = [mesh.vertices[i] for i in indices]
            self.assertGreater(sum(n * n for n in normal(*points)), 1e-18)
            key = tuple(sorted(tuple(round(v, 9) for v in point) for point in points))
            self.assertNotIn(key, signatures)
            signatures.add(key)
        self.assertTrue(all(math.isfinite(v) for point in mesh.vertices for v in point))

    def test_square_and_flat_known_points(self):
        wall = Wall(40, 10)
        flat = WallGeometry(wall)
        self.assertEqual(flat.point(4, 3), (-16, 3, 0))
        self.assertEqual(flat.splits(-2, 5), [-2, 3])
        square = WallGeometry(wall, mode="projected")
        for s, expected in (
            (0, (5, 3, 5)),
            (10, (5, 3, -5)),
            (20, (-5, 3, -5)),
            (30, (-5, 3, 5)),
        ):
            for actual, target in zip(square.point(s, 3), expected):
                self.assertAlmostEqual(actual, target)
        self.assertEqual(square.splits(8, 5), [8, 10, 13])

    def test_polygon_perimeter_and_arc_length_mapping_at_every_resolution(self):
        for rounding in (0, 0.01, 0.3, 0.9, 1):
            for resolution in (1, 3, 8, 32):
                geometry = WallGeometry(
                    Wall(50, 30),
                    mode="projected",
                    roundness=rounding,
                    resolution=resolution,
                )
                section = geometry.section
                perimeter = sum(
                    math.dist(a, b) for a, b in zip(section, section[1:] + section[:1])
                )
                self.assertAlmostEqual(perimeter, 50)
                for a, b in zip(geometry.distances, geometry.distances[1:]):
                    self.assertAlmostEqual(
                        math.dist(geometry.point(a, 0), geometry.point(b, 0)), b - a
                    )
                if rounding == 1:
                    radii = [math.hypot(x, z) for x, z in section]
                    self.assertLess(max(radii) - min(radii), 1e-10)

    def test_periodic_and_negative_spans_split_once_with_no_missing_area(self):
        for rounding in (0, 0.4, 1):
            geometry = WallGeometry(
                Wall(40, 10, wrap_x=True),
                mode="projected",
                roundness=rounding,
                resolution=5,
            )
            for start, width in ((38, 5), (-2, 5), (8, 25), (3, 40)):
                cuts = geometry.splits(start, width)
                self.assertEqual((cuts[0], cuts[-1]), (start, start + width))
                self.assertEqual(len(cuts), len(set(cuts)))
                self.assertAlmostEqual(
                    sum(b - a for a, b in zip(cuts, cuts[1:])), width
                )
                mesh = geometry.stone_mesh(Stone(0, start, 1, width, 3))
                self.assertAlmostEqual(area(mesh), width * 3)
                self.assertClean(mesh)
                for triangle in mesh.triangles:
                    points = [mesh.vertices[i] for i in triangle]
                    n = normal(*points)
                    center = [sum(p[i] for p in points) / 3 for i in range(3)]
                    self.assertGreater(n[0] * center[0] + n[2] * center[2], 0)
            for a, b in zip(geometry.point(-2, 4), geometry.point(38, 4)):
                self.assertAlmostEqual(a, b)

    def test_periodic_closed_ring_has_no_end_caps_and_positive_shell_volume(self):
        geometry = WallGeometry(Wall(40, 10, wrap_x=True), mode="projected", depth=0.5)
        mesh = geometry.stone_mesh(Stone(0, 0, 0, 40, 3))
        self.assertEqual(len(mesh.triangles), 4 * 8)
        self.assertAlmostEqual(volume(mesh), (11**2 - 10**2) * 3)
        self.assertClean(mesh)

    def test_flat_optional_depth_is_closed_and_default_remains_surface(self):
        wall, stone = Wall(40, 10), Stone(0, 2, 1, 5, 3)
        surface = WallGeometry(wall).stone_mesh(stone)
        self.assertEqual(len(surface.triangles), 2)
        self.assertTrue(all(v[2] == 0 for v in surface.vertices))
        shell = WallGeometry(wall, depth=0.5).stone_mesh(stone)
        self.assertEqual(len(shell.triangles), 12)
        self.assertAlmostEqual(volume(shell), 7.5)
        self.assertClean(shell)

    def test_core_and_tube_winding_and_safe_small_fillets(self):
        for rounding in (0, 0.001, 0.5, 1):
            geometry = WallGeometry(Wall(40, 10), mode="projected", roundness=rounding)
            solid = geometry.primitive_mesh("solid")
            tube = geometry.primitive_mesh("tube", 0.5)
            self.assertGreater(volume(solid), volume(tube))
            self.assertGreater(volume(tube), 0)
            self.assertClean(solid)
            self.assertClean(tube)
            with self.assertRaises(ValueError):
                geometry.primitive_mesh("tube", geometry.inradius)

    def test_generated_bricks_project_as_whole_periodic_stones(self):
        session = GenerationSession(width=52, height=4)
        session.generate_all()
        before = session.to_dict()
        geometry = WallGeometry(session.wall, mode="projected")
        meshes = [geometry.stone_mesh(stone) for stone in session.wall.stones]
        self.assertAlmostEqual(sum(area(mesh) for mesh in meshes), 52 * 4)
        self.assertTrue(any(stone.x < 0 for stone in session.wall.stones))
        for mode in ("flat", "projected"):
            data = WallGeometry(
                session.wall, mode=mode, roundness=0.6, depth=0.2
            ).to_dict(primitive="tube")
            self.assertEqual(
                [s["id"] for s in data["stones"]], [s.id for s in session.wall.stones]
            )
        self.assertEqual(session.to_dict(), before)

    def test_finite_projection_never_clips_away_a_conflicting_overhang(self):
        wall = Wall(6, 2)
        wall.add_stone(Stone(0, -2, 0, 4, 2))
        wall.add_stone(Stone(1, 2, 0, 4, 2))
        # Finite occupancy is valid, but modulo coverage would overlap.
        with self.assertRaisesRegex(ValueError, "overlaps"):
            WallGeometry(wall, mode="projected").to_dict()

    def test_compatible_finite_source_also_folds_the_whole_stone(self):
        wall = Wall(8, 2)
        stone = Stone(0, -2, 0, 4, 2)
        wall.add_stone(stone)
        wall.add_stone(Stone(1, 2, 0, 4, 2))
        geometry = WallGeometry(wall, mode="projected")
        self.assertAlmostEqual(area(geometry.stone_mesh(stone)), 8)
        self.assertEqual(len(geometry.to_dict()["stones"]), 2)

    def test_rebuild_after_undo_reset_and_incremental_placements(self):
        session = GenerationSession(width=12, height=6)
        geometry = WallGeometry(session.wall, mode="projected")
        self.assertEqual(len(geometry.to_dict()["stones"]), 0)
        session.step()
        self.assertEqual(len(geometry.to_dict()["stones"]), 1)
        session.undo()
        self.assertEqual(len(geometry.to_dict()["stones"]), 0)
        session.reset(width=20, height=8)
        self.assertEqual(WallGeometry(session.wall).to_dict()["perimeter"], 20)

    def test_view_changes_do_not_consume_ashlar_randomness(self):
        inspected = GenerationSession(generator_id="ashlar")
        control = GenerationSession(generator_id="ashlar")
        for _ in range(4):
            self.assertEqual(inspected.step().to_dict(), control.step().to_dict())
        before = inspected.to_dict()
        for mode, rounding in (
            ("flat", 0),
            ("projected", 0),
            ("projected", 0.5),
            ("projected", 1),
        ):
            WallGeometry(
                inspected.wall, mode=mode, roundness=rounding, depth=0.3
            ).to_dict(primitive="tube")
        self.assertEqual(inspected.to_dict(), before)
        self.assertEqual(inspected.step().to_dict(), control.step().to_dict())
        inspected.undo()
        control.undo()
        self.assertEqual(inspected.step().to_dict(), control.step().to_dict())

    def test_closed_shells_have_exactly_two_faces_per_welded_edge(self):
        for rounding in (0, 0.5, 1):
            geometry = WallGeometry(
                Wall(40, 10, wrap_x=True),
                mode="projected",
                roundness=rounding,
                depth=0.4,
            )
            meshes = [
                geometry.stone_mesh(Stone(0, x, 0, width, 3))
                for x, width in ((38, 5), (3, 40))
            ]
            meshes += [geometry.primitive_mesh(kind) for kind in ("solid", "tube")]
            for mesh in meshes:
                edges = Counter()
                for indices in mesh.triangles:
                    points = [
                        tuple(round(v, 8) for v in mesh.vertices[i]) for i in indices
                    ]
                    for a, b in zip(points, points[1:] + points[:1]):
                        edges[tuple(sorted((a, b)))] += 1
                self.assertEqual(set(edges.values()), {2})

    def test_validation(self):
        for kwargs in (
            {"roundness": -1},
            {"roundness": math.nan},
            {"resolution": 0},
            {"resolution": 65},
            {"resolution": True},
            {"depth": -1},
            {"mode": "other"},
        ):
            with self.assertRaises(ValueError):
                WallGeometry(Wall(40, 10), **kwargs)


if __name__ == "__main__":
    unittest.main()
