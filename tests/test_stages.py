"""Applied pipeline provenance, mortar gaps and polygon-based mapped shells."""

from collections import Counter
from copy import deepcopy
import math
import unittest
import io
import json

from masonpy import Stone, Wall, WallGeometry
from masonpy.app.workbench import WorkbenchSession
from masonpy.app.server import MasonPyRequestHandler
from masonpy.processing import ShapedStone, ShapedWall, WallDescription, shape_wall
from test_geometry import area, volume


class ShapeTests(unittest.TestCase):
    def test_joint_width_is_a_gap_and_source_is_unchanged(self):
        wall = Wall(12, 4, wrap_x=True)
        wall.add_stone(Stone(0, -2, 0, 6, 4))
        wall.add_stone(Stone(1, 4, 0, 6, 4))
        before = wall.to_dict()
        shaped = shape_wall(wall, joint_width=0.4)
        self.assertEqual(shaped.stones[0].id, 0)
        self.assertEqual(shaped.stones[0].vertices[0], (-1.8, 0.2))
        self.assertAlmostEqual(
            shaped.stones[1].vertices[0][0] - shaped.stones[0].vertices[1][0], 0.4
        )
        self.assertEqual(wall.to_dict(), before)
        wall.remove_last_stone()
        self.assertEqual(len(shaped.source.stones), 2)
        self.assertEqual(len(shaped.stones), 2)

    def test_inset_rejection_and_zero_width_identity(self):
        wall = Wall(8, 4)
        wall.add_stone(Stone(8, 0, 0, 8, 1))
        for value in (-1, True, math.inf, math.nan, 1, 2):
            with self.assertRaises(ValueError):
                shape_wall(wall, joint_width=value)
        with self.assertRaisesRegex(ValueError, "stone 8.*below 1"):
            shape_wall(wall, joint_width=1)
        self.assertEqual(
            shape_wall(wall).stones[0].vertices, ((0, 0), (8, 0), (8, 1), (0, 1))
        )


class StageSessionTests(unittest.TestCase):
    def test_processing_rejects_a_replaced_source_before_changing_results(self):
        session = WorkbenchSession(width=40, height=8)
        session.generate_all()
        old_wall_revision = session.wall_revision
        session.apply_shape(0.2, source_revision=old_wall_revision)
        old_shape_revision = session.shape_revision
        session.build_3d({}, source_revision=old_shape_revision)
        snapshot = session.geometry_snapshot()
        self.assertEqual(snapshot["revision"], session.build_revision)
        self.assertEqual(snapshot["source_revision"], old_shape_revision)
        self.assertEqual(snapshot["wall_revision"], old_wall_revision)
        session.reset(width=44, height=8)
        session.step()
        before = session.to_dict()
        with self.assertRaisesRegex(ValueError, "Wall changed"):
            session.apply_shape(0.2, source_revision=old_wall_revision)
        self.assertEqual(session.to_dict(), before)
        session.apply_shape(0.1, source_revision=session.wall_revision)
        before = session.to_dict()
        with self.assertRaisesRegex(ValueError, "Shape changed"):
            session.build_3d({}, source_revision=old_shape_revision)
        self.assertEqual(session.to_dict(), before)
        self.assertEqual(session.geometry_snapshot(), snapshot)
        for invalid in (True, -1, "1", 1.5):
            with self.assertRaisesRegex(ValueError, "source_revision"):
                session.apply_shape(source_revision=invalid)

    def test_nonempty_failed_generation_can_refresh_both_downstream_stages(self):
        session = WorkbenchSession(
            width=24,
            height=12,
            generator_id="ashlar",
            generator_parameters={"min_sneck_size": 2},
        )
        session.generate_all()
        self.assertIsNotNone(session.failure)
        self.assertTrue(session.wall.stones)
        source = session.wall.to_dict()
        failure = session.failure
        session.apply_shape(0.2, source_revision=session.wall_revision)
        session.build_3d({}, source_revision=session.shape_revision)
        self.assertTrue(session.build_current)
        self.assertEqual(session.wall.to_dict(), source)
        self.assertIs(session.failure, failure)

    def test_failed_source_refresh_retains_previous_results_as_stale(self):
        session = WorkbenchSession(width=40, height=8)
        session.generate_all()
        session.apply_shape(1.2)
        session.build_3d({})
        old_shape, old_mesh = session.shape_result, session.geometry_snapshot()
        session.reset(width=40, height=8, generator_parameters={"brick_height": 1})
        session.generate_all()
        with self.assertRaises(ValueError):
            session.apply_shape(1.2, source_revision=session.wall_revision)
        self.assertIs(session.shape_result, old_shape)
        self.assertEqual(session.geometry_snapshot(), old_mesh)
        self.assertFalse(session.shape_current)
        self.assertFalse(session.build_current)
        self.assertIn("failed", session.shape_events[-1])

    def test_http_processing_dispatch_enforces_source_provenance(self):
        session = WorkbenchSession(width=40, height=8)
        session.generate_all()

        def request(path, payload):
            handler = object.__new__(MasonPyRequestHandler)
            handler.path, handler.session = path, session
            body = json.dumps(payload).encode()
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = io.BytesIO(body)
            replies = []
            handler._send_json = lambda data, **kwargs: replies.append(
                (data, kwargs.get("status", 200))
            )
            handler.do_POST()
            return replies[0]

        rejected, status = request(
            "/api/shape", {"source_revision": session.wall_revision - 1}
        )
        self.assertEqual(status, 400)
        self.assertIn("Wall changed", rejected["error"])
        shaped, status = request(
            "/api/shape", {"joint_width": 0.2, "source_revision": session.wall_revision}
        )
        self.assertEqual(status, 200)
        self.assertEqual(shaped["shape"]["source_revision"], shaped["wall_revision"])
        built, status = request(
            "/api/build", {"source_revision": shaped["shape"]["revision"]}
        )
        self.assertEqual(status, 200)
        self.assertTrue(built["build"]["current"])
        self.assertNotIn("source_revision", built["build"]["settings"])

    def test_http_snapshots_cannot_be_reused_from_a_browser_cache(self):
        handler = object.__new__(MasonPyRequestHandler)
        headers = {}
        handler.send_response = lambda status: None
        handler.send_header = lambda key, value: headers.update({key: value})
        handler.end_headers = lambda: None
        handler.wfile = io.BytesIO()
        handler._send_json({"wall_revision": 12})
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(handler.wfile.getvalue()), {"wall_revision": 12})

    def test_workbench_defaults_are_shared_and_build_a_rounded_tube(self):
        defaults = WorkbenchSession()
        self.assertEqual((defaults.wall.width, defaults.wall.height), (104, 60))
        expected = dict(
            mode="projected",
            roundness=0.25,
            resolution=8,
            depth=0.25,
            primitive="tube",
            tube_thickness=1,
            depth_variation=0,
            detail_seed=1,
            bevel=0,
        )
        self.assertEqual(defaults.to_dict()["build"]["defaults"], expected)
        session = WorkbenchSession(width=40, height=8)
        session.generate_all()
        session.apply_shape(0.2)
        session.build_3d({})
        self.assertEqual(session.build_settings, expected)
        self.assertTrue(session.build_current)
        self.assertEqual(session.export_stage("3d")[1], "model/stl")

    def test_prerequisites_and_non_destructive_failure(self):
        session = WorkbenchSession(width=12, height=4)
        with self.assertRaises(ValueError):
            session.apply_shape()
        with self.assertRaises(ValueError):
            session.build_3d({})
        session.step()  # Explicit partial walls are valid sources.
        session.apply_shape(0.2)
        session.build_3d({"depth": 0.4})
        applied = session.shape_result
        mesh = deepcopy(session.geometry_snapshot())
        with self.assertRaises(ValueError):
            session.apply_shape(10)
        with self.assertRaises(ValueError):
            session.build_3d({"depth": -1})
        self.assertIs(session.shape_result, applied)
        self.assertEqual(session.geometry_snapshot(), mesh)
        self.assertTrue(session.build_current)
        self.assertIn("failed", session.to_dict()["shape"]["events"][-1])

    def test_downstream_invalidation_and_inherited_snapshots(self):
        session = WorkbenchSession(width=12, height=4)
        session.generate_all()
        session.apply_shape(0)
        session.build_3d({"depth": 0.3})
        snapshot = session.geometry_snapshot()
        source = session.shape_result.source.to_dict()
        session.undo()
        self.assertFalse(session.shape_current)
        self.assertFalse(session.build_current)
        self.assertEqual(session.shape_result.source.to_dict(), source)
        self.assertEqual(session.geometry_snapshot(), snapshot)
        with self.assertRaisesRegex(ValueError, "Apply Shape"):
            session.build_3d({})
        session.apply_shape(0.1)
        self.assertTrue(session.shape_current)
        self.assertFalse(session.build_current)
        self.assertEqual(session.geometry_snapshot(), snapshot)
        session.build_3d({"mode": "projected", "roundness": 0.4, "depth": 0.3})
        self.assertTrue(session.build_current)
        session.reset(width=20, height=8)
        self.assertFalse(session.shape_current)
        self.assertFalse(session.build_current)
        self.assertEqual(
            len(session.geometry_snapshot()["shape"]["source"]["stones"]),
            len(source["stones"]) - 1,
        )

    def test_reuse_does_not_invalidate_and_snapshots_are_read_only(self):
        session = WorkbenchSession(width=12, height=4)
        session.generate_all()
        session.apply_shape(0.2)
        session.build_3d({})
        revisions = (
            session.wall_revision,
            session.shape_revision,
            session.build_revision,
        )
        session.generate_all()
        session.apply_shape(0.2)
        session.build_3d({})
        self.assertEqual(
            revisions,
            (session.wall_revision, session.shape_revision, session.build_revision),
        )
        for _ in range(3):
            session.to_dict()
            snapshot = session.geometry_snapshot()
            snapshot["shape"]["source"]["stones"].clear()
        self.assertEqual(
            revisions,
            (session.wall_revision, session.shape_revision, session.build_revision),
        )
        self.assertTrue(session.geometry_snapshot()["shape"]["source"]["stones"])

    def test_invalid_reset_preserves_source_and_applied_stages(self):
        session = WorkbenchSession(width=12, height=4)
        session.step()
        session.apply_shape(0.1)
        before = session.to_dict()
        with self.assertRaises(ValueError):
            session.reset(width=20, height=4, generator_id="missing")
        self.assertEqual(session.to_dict(), before)


class ContourGeometryTests(unittest.TestCase):
    def assertClosed(self, mesh):
        edges = Counter()
        for indices in mesh.triangles:
            points = [tuple(round(v, 8) for v in mesh.vertices[i]) for i in indices]
            self.assertEqual(len(set(points)), 3)
            for a, b in zip(points, points[1:] + points[:1]):
                edges[tuple(sorted((a, b)))] += 1
        self.assertEqual(set(edges.values()), {2})
        self.assertGreater(volume(mesh), 0)

    def test_non_rectangular_concave_contours_and_boundary_subdivisions(self):
        wall = Wall(40, 10, wrap_x=True)
        # A concave outline crossing a square corner at x=10.
        polygon = ShapedStone(0, ((8, 1), (11, 1), (13, 1), (13, 5), (11, 3), (8, 5)))
        shaped = ShapedWall(WallDescription.from_wall(wall), 0, (polygon,))
        for mode in ("flat", "projected"):
            for rounding in (0, 0.4, 1):
                geometry = WallGeometry(
                    shaped, mode=mode, roundness=rounding, depth=0.5
                )
                self.assertClosed(geometry.contour_mesh(polygon))
        mesh = WallGeometry(shaped, depth=0.5).contour_mesh(polygon)
        self.assertAlmostEqual(volume(mesh), 7.5)

    def test_inset_and_periodic_full_ring_shells_are_closed(self):
        for x, width in ((-2, 6), (38, 5), (0, 40), (3, 40)):
            wall = Wall(40, 8, wrap_x=True)
            wall.add_stone(Stone(0, x, 1, width, 3))
            for joint in (0, 0.2):
                shaped = shape_wall(wall, joint_width=joint)
                for rounding in (0, 0.4, 1):
                    geometry = WallGeometry(
                        shaped, mode="projected", roundness=rounding, depth=0.4
                    )
                    self.assertClosed(geometry.contour_mesh(shaped.stones[0]))
                    surface = WallGeometry(shaped, mode="projected", roundness=rounding)
                    self.assertAlmostEqual(
                        area(surface.contour_mesh(shaped.stones[0])),
                        (width - joint) * (3 - joint),
                        places=7,
                    )


if __name__ == "__main__":
    unittest.main()
