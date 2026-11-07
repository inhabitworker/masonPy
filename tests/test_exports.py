"""Physical scale, full-result SVG and closed-shell binary STL contracts."""

from copy import deepcopy
import json
import math
import struct
import unittest
from xml.etree import ElementTree as ET

from masonpy import Stone, Wall, WallGeometry, shape_wall
from masonpy.app.workbench import WorkbenchSession
from masonpy.exporting import mesh_stl, wall_svg

NS = {"svg": "http://www.w3.org/2000/svg"}


class ExportTests(unittest.TestCase):
    def test_periodic_svg_preserves_identity_contours_and_scale(self):
        wall = Wall(8, 4, wrap_x=True)
        wall.add_stone(Stone(7, -2, 0, 4, 2))
        wall.add_stone(Stone(9, 2, 0, 4, 2))
        for source in (wall, shape_wall(wall, joint_width=0.2)):
            root = ET.fromstring(wall_svg(source, scale=2))
            self.assertEqual(root.attrib["viewBox"], "0 0 8 4")
            self.assertEqual(root.attrib["width"], "16mm")
            self.assertEqual(root.attrib["height"], "8mm")
            groups = root.findall(".//svg:g[@data-stone-id]", NS)
            self.assertEqual([g.attrib["data-stone-id"] for g in groups], ["7", "9"])
            self.assertEqual(len(groups[0].findall("svg:polygon", NS)), 2)
            metadata = json.loads(root.find("svg:metadata", NS).text)
            self.assertEqual(metadata["millimetres_per_unit"], 2)
            self.assertFalse(root.findall(".//svg:text", NS))
            self.assertIsNotNone(root.find(".//svg:clipPath", NS))
        self.assertEqual(len(wall.stones), 2)

    def test_finite_svg_retains_whole_overhang_and_applied_inset(self):
        wall = Wall(8, 4)
        wall.add_stone(Stone(0, -2, 0, 4, 2))
        root = ET.fromstring(wall_svg(wall))
        self.assertEqual(root.attrib["viewBox"], "-2 0 10 4")
        self.assertIsNone(root.find(".//svg:clipPath", NS))
        shaped = ET.fromstring(wall_svg(shape_wall(wall, joint_width=0.4)))
        points = shaped.find(".//svg:polygon", NS).attrib["points"]
        self.assertIn("-1.8,3.8", points)
        self.assertIn("1.8,2.2", points)

    def test_binary_stl_count_float32_vertices_normals_and_scale(self):
        wall = Wall(8, 4)
        wall.add_stone(Stone(1, 0, 0, 4, 2))
        geometry = WallGeometry(shape_wall(wall, joint_width=0.2), depth=0.5).to_dict()
        before = deepcopy(geometry)
        data = mesh_stl(geometry, scale=3)
        count = struct.unpack("<I", data[80:84])[0]
        self.assertEqual(len(data), 84 + 50 * count)
        self.assertEqual(count, len(geometry["stones"][0]["triangles"]))
        points = []
        for i in range(count):
            values = struct.unpack_from("<12fH", data, 84 + i * 50)
            self.assertAlmostEqual(sum(v * v for v in values[:3]), 1, places=6)
            points.extend(tuple(values[j : j + 3]) for j in (3, 6, 9))
        self.assertAlmostEqual(max(p[2] for p in points), 1.5)
        self.assertAlmostEqual(
            max(p[0] for p in points) - min(p[0] for p in points), 11.4, places=5
        )
        self.assertEqual(geometry, before)

    def test_projected_seam_crossing_and_full_ring_stl(self):
        for x, width in ((-2, 6), (38, 5), (0, 40), (3, 40)):
            wall = Wall(40, 8, wrap_x=True)
            wall.add_stone(Stone(0, x, 1, width, 3))
            for joint in (0, 0.2):
                for roundness in (0, 0.5, 1):
                    geometry = WallGeometry(
                        shape_wall(wall, joint_width=joint),
                        mode="projected",
                        roundness=roundness,
                        depth=0.4,
                    ).to_dict()
                    self.assertGreater(len(mesh_stl(geometry)), 84)

    def test_surface_open_reversed_and_collapsed_shells_are_rejected(self):
        wall = Wall(8, 4)
        wall.add_stone(Stone(0, 0, 0, 4, 2))
        with self.assertRaisesRegex(ValueError, "closed shells"):
            mesh_stl(WallGeometry(shape_wall(wall), depth=0).to_dict())
        geometry = WallGeometry(shape_wall(wall), depth=0.4).to_dict()
        opened = deepcopy(geometry)
        opened["stones"][0]["triangles"].pop()
        with self.assertRaises(ValueError):
            mesh_stl(opened)
        reverse = deepcopy(geometry)
        reverse["stones"][0]["triangles"] = [
            tuple(reversed(t)) for t in reverse["stones"][0]["triangles"]
        ]
        with self.assertRaisesRegex(ValueError, "positive volume"):
            mesh_stl(reverse)
        with self.assertRaisesRegex(ValueError, "precision"):
            mesh_stl(geometry, scale=1e-300)

    def test_invalid_scales_and_empty_svg_are_rejected(self):
        wall = Wall(8, 4)
        with self.assertRaisesRegex(ValueError, "no stones"):
            wall_svg(wall)
        wall.add_stone(Stone(0, 0, 0, 4, 2))
        for value in (0, -1, True, math.inf, math.nan, "2"):
            with self.assertRaises(ValueError):
                wall_svg(wall, scale=value)
            with self.assertRaises(ValueError):
                mesh_stl({}, scale=value)

    def test_stage_exports_reject_stale_or_mismatched_revisions(self):
        session = WorkbenchSession(width=12, height=4)
        session.generate_all()
        before = session.to_dict()
        content, mime, filename = session.export_stage(
            "wall", revision=session.wall_revision
        )
        self.assertEqual(mime, "image/svg+xml")
        self.assertTrue(filename.endswith(".svg"))
        self.assertEqual(
            len(ET.fromstring(content).findall(".//svg:g[@data-stone-id]", NS)),
            len(session.wall.stones),
        )
        self.assertEqual(session.to_dict(), before)
        with self.assertRaises(ValueError):
            session.export_stage("wall", revision=session.wall_revision - 1)
        session.apply_shape(0.2)
        with self.assertRaises(ValueError):
            session.export_stage("3d")
        session.build_3d({"depth": 0})
        with self.assertRaisesRegex(ValueError, "positive stone depth"):
            session.export_stage("3d")
        session.build_3d({"mode": "projected", "depth": 0.4, "primitive": "solid"})
        self.assertEqual(session.export_stage("3d")[1], "model/stl")
        session.build_3d({"mode": "projected", "depth": 0.4})
        self.assertEqual(session.export_stage("3d")[1], "model/stl")
        session.undo()
        for stage in ("shape", "3d"):
            with self.assertRaises(ValueError):
                session.export_stage(stage)


class CoreExportTests(unittest.TestCase):
    def test_core_and_stones_share_one_scaled_stl_without_changing_geometry(self):
        session = WorkbenchSession(width=40, height=8)
        session.generate_all()
        session.apply_shape(0.2)
        for kind in ("solid", "tube"):
            for rounding in (0, 0.5, 1):
                session.build_3d(
                    {
                        "mode": "projected",
                        "roundness": rounding,
                        "depth": 0.4,
                        "primitive": kind,
                        "tube_thickness": 0.5,
                    }
                )
                before = session.geometry_snapshot()
                data, mime, _ = session.export_stage("3d", scale=2)
                stone_count = sum(
                    len(s["triangles"]) for s in before["geometry"]["stones"]
                )
                core_count = len(before["geometry"]["primitive"]["triangles"])
                self.assertGreater(core_count, 0)
                count = struct.unpack_from("<I", data, 80)[0]
                self.assertEqual(count, stone_count + core_count)
                self.assertEqual(len(data), 84 + count * 50)
                self.assertEqual(mime, "model/stl")
                # Core triangles follow the stones and use the same physical scale.
                core_points = []
                for i in range(stone_count, count):
                    values = struct.unpack_from("<12fH", data, 84 + i * 50)
                    core_points.extend(tuple(values[j : j + 3]) for j in (3, 6, 9))
                self.assertAlmostEqual(max(p[1] for p in core_points), 16)
                self.assertEqual(session.geometry_snapshot(), before)

    def test_invalid_core_is_validated_independently(self):
        session = WorkbenchSession(width=40, height=8)
        session.step()
        session.apply_shape(0.2)
        session.build_3d({"mode": "projected", "depth": 0.4, "primitive": "solid"})
        mesh = session.geometry_snapshot()["geometry"]
        mesh["primitive"]["triangles"].pop()
        with self.assertRaisesRegex(ValueError, "Core:.*closed shells"):
            mesh_stl(mesh)
