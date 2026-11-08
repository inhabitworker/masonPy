"""Semantic face labels survive extrusion, mapping and bevel treatment."""

import unittest

from masonpy import Stone, Wall, WallGeometry, shape_wall


class MeshRoleTests(unittest.TestCase):
    def test_opt_in_roles_preserve_the_existing_geometry_payload(self):
        wall = Wall(24, 8, wrap_x=True)
        wall.add_stone(Stone(7, 20, 1, 8, 4))
        shape = shape_wall(wall, joint_width=0.1, distortion=0.3, corner_softening=0.5)
        for mode in ("flat", "projected"):
            for depth in (0, 0.4):
                for bevel in (0, 0.03):
                    geometry = WallGeometry(
                        shape, mode=mode, roundness=0.6, depth=depth, bevel=bevel
                    )
                    original = geometry.to_dict(primitive="tube")
                    labelled = geometry.to_dict(primitive="tube", include_roles=True)
                    for surface in labelled["stones"] + [labelled["primitive"]]:
                        roles = surface.pop("face_roles")
                        self.assertEqual(len(roles), len(surface["triangles"]))
                        if surface.get("id") == 7:
                            self.assertEqual(
                                set(roles),
                                {"front"}
                                if not depth
                                else {"front", "back", "side", "bevel"}
                                if bevel
                                else {"front", "back", "side"},
                            )
                        else:
                            self.assertTrue(set(roles) <= {"core"})
                    self.assertEqual(labelled, original)

    def test_front_and_back_are_labelled_at_construction_not_by_global_axis(self):
        wall = Wall(24, 8)
        wall.add_stone(Stone(0, 2, 1, 4, 4))
        geometry = WallGeometry(wall, depth=0.4)
        mesh = geometry.stone_mesh(wall.stones[0])
        for face, role in zip(mesh.triangles, mesh.face_roles):
            depths = {mesh.vertices[i][2] for i in face}
            if role == "front":
                self.assertEqual(depths, {0.4})
            elif role == "back":
                self.assertEqual(depths, {0})
            else:
                self.assertEqual(role, "side")
                self.assertEqual(depths, {0, 0.4})
