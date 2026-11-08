"""Run inside Blender: saved recipes, connected islands, semantic labels and rebuild safety."""

import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import bpy
import bmesh

# --source is a development-only bootstrap. Release tests use the installed ZIP.
arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
if "--source" in arguments:
    root = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(root / "src"), str(root / "blender")]
    import zipfile

    dependency = Path(arguments[arguments.index("--pyclipper-wheel") + 1])
    extracted = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(dependency) as archive:
        archive.extractall(extracted.name)
    sys.path.insert(0, extracted.name)
    addon = importlib.import_module("masonpy_blender")
    addon.register()
else:
    import addon_utils

    module_name = "bl_ext.masonry_test.masonpy_blender"
    addon_utils.enable(module_name, default_set=False)
    addon = importlib.import_module(module_name)

from masonpy.configuration import (
    DEFAULT_BUILD_SETTINGS,
    DEFAULT_SHAPE_SETTINGS,
    DEFAULT_WALL_SETTINGS,
)


def add(**kwargs):
    result = bpy.ops.mesh.add_masonry(**kwargs)
    assert result == {"FINISHED"}, result
    return bpy.context.object


def signature(obj):
    return (
        [tuple(v.co) for v in obj.data.vertices],
        [tuple(p.vertices) for p in obj.data.polygons],
    )


def attr(obj, name):
    return [value.value for value in obj.data.attributes[name].data]


class MasonryTests(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for collection in list(bpy.data.collections):
            if collection.name.startswith("Masonry"):
                bpy.data.collections.remove(collection)

    def assert_islands(self, obj, closed):
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            self.assertFalse(
                any(not edge.is_manifold for edge in bm.edges)
                if closed
                else any(len(edge.link_faces) > 2 for edge in bm.edges)
            )
        finally:
            bm.free()
        ownership = {}
        for face, stone_id in zip(obj.data.polygons, attr(obj, "masonry_stone_id")):
            for vertex in face.vertices:
                self.assertEqual(ownership.setdefault(vertex, stone_id), stone_id)

    def test_shared_defaults_and_grouped_solid_geometry(self):
        obj = add()
        config = json.loads(obj["masonry_config"])
        for group, defaults in (
            ("shape", DEFAULT_SHAPE_SETTINGS),
            ("build", DEFAULT_BUILD_SETTINGS),
        ):
            for name, expected in defaults.items():
                if isinstance(expected, float):
                    self.assertAlmostEqual(config[group][name], expected, places=6)
                else:
                    self.assertEqual(config[group][name], expected)
        self.assertEqual(config["width"], DEFAULT_WALL_SETTINGS["width"])
        self.assertEqual(obj["masonry_stone_count"], 780)
        self.assertEqual(set(attr(obj, "masonry_face_role")), {1, 2, 3})
        self.assertIn("Stone 00000", obj.vertex_groups)
        self.assertIn("Front", obj.vertex_groups)
        self.assertTrue(obj.masonry.core_object)
        self.assertEqual(obj.masonry.core_object.parent, obj)
        self.assertEqual(set(attr(obj.masonry.core_object, "masonry_face_role")), {5})
        self.assert_islands(obj, closed=True)
        self.assert_islands(obj.masonry.core_object, closed=True)
        self.assertFalse(obj.modifiers)

    def test_mapped_surfaces_have_no_thickness_or_core(self):
        obj = add(
            width=24, height=12, output="SURFACE", roundness=1, depth=2, bevel=0.2
        )
        self.assertFalse(obj.masonry.core_object)
        self.assertEqual(set(attr(obj, "masonry_face_role")), {1})
        self.assertNotIn("Back", obj.vertex_groups)
        self.assertGreater(max(abs(v.co.y) for v in obj.data.vertices), 0.1)
        self.assertAlmostEqual(max(v.co.z for v in obj.data.vertices), 1.19, places=5)
        self.assert_islands(obj, closed=False)

    def test_raw_touching_stones_remain_separate_and_styling_is_optional(self):
        obj = add(width=24, height=12, mode="flat", use_shape=False, primitive="none")
        self.assert_islands(obj, closed=True)
        self.assertAlmostEqual(min(v.co.z for v in obj.data.vertices), 0)
        self.assertAlmostEqual(max(v.co.z for v in obj.data.vertices), 1.2, places=5)
        self.assertFalse(json.loads(obj["masonry_diagnostics"])["shape"])

    def test_styling_and_depth_details_retain_labels(self):
        obj = add(
            width=24,
            height=12,
            generator="ashlar",
            gen_seed=4,
            distortion=0.3,
            corner_softening=0.6,
            joint_width=0.1,
            depth_variation=0.15,
            bevel=0.03,
        )
        self.assert_islands(obj, closed=True)
        self.assertEqual(set(attr(obj, "masonry_face_role")), {1, 2, 3, 4})
        self.assertIn("Bevel", obj.vertex_groups)
        self.assertTrue(
            json.loads(obj["masonry_diagnostics"])["shape"]["softened_stones"]
        )

    def test_rebuild_preserves_object_placement_materials_and_recipe(self):
        obj = add(width=24, height=12)
        obj.location = (4, 5, 6)
        obj.rotation_euler = (0.1, 0.2, 0.3)
        obj.scale = (1.1, 1.2, 1.3)
        bpy.context.view_layer.update()
        matrix = obj.matrix_world.copy()
        material = bpy.data.materials.new("Test material")
        obj.data.materials.append(material)
        modifier = obj.modifiers.new("Retained user modifier", "BEVEL")
        name, pointer = obj.name, obj.as_pointer()
        before = signature(obj)
        obj.masonry.corner_softening = 0.6
        self.assertEqual(bpy.ops.mesh.regenerate_masonry(), {"FINISHED"})
        self.assertEqual(obj.as_pointer(), pointer)
        self.assertEqual(obj.name, name)
        self.assertEqual(obj.matrix_world, matrix)
        self.assertEqual(obj.data.materials[0], material)
        self.assertEqual(obj.modifiers[0], modifier)
        self.assertNotEqual(signature(obj), before)
        self.assertEqual(
            addon.properties.snapshot(obj.masonry), obj.masonry.applied_recipe
        )
        before = signature(obj)
        self.assertEqual(bpy.ops.mesh.regenerate_masonry(), {"FINISHED"})
        self.assertEqual(signature(obj), before)
        self.assert_islands(obj, closed=True)

    def test_failed_rebuild_and_failed_add_preserve_scene(self):
        obj = add(width=24, height=12)
        before, mesh, applied, core = (
            signature(obj),
            obj.data,
            obj.masonry.applied_recipe,
            obj.masonry.core_object,
        )
        obj.masonry.joint_width = 100
        with self.assertRaises(RuntimeError):
            bpy.ops.mesh.regenerate_masonry()
        self.assertEqual(signature(obj), before)
        self.assertEqual(obj.data, mesh)
        self.assertEqual(obj.masonry.applied_recipe, applied)
        self.assertEqual(obj.masonry.core_object, core)
        counts = len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.collections)
        with self.assertRaises(RuntimeError):
            bpy.ops.mesh.add_masonry(width=25, height=12)
        self.assertEqual(
            (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.collections)),
            counts,
        )

    def test_backing_selection_surface_switch_and_duplicate_ownership(self):
        obj = add(width=24, height=12)
        original_core = obj.masonry.core_object
        clone = obj.copy()
        obj.users_collection[0].objects.link(clone)
        bpy.context.view_layer.objects.active = clone
        clone.masonry.output = "SURFACE"
        self.assertEqual(bpy.ops.mesh.regenerate_masonry(), {"FINISHED"})
        self.assertFalse(clone.masonry.core_object)
        self.assertIn(original_core.name, bpy.data.objects)
        bpy.context.view_layer.objects.active = original_core
        obj.masonry.output = "SURFACE"
        self.assertEqual(bpy.ops.mesh.regenerate_masonry(), {"FINISHED"})
        self.assertFalse(obj.masonry.core_object)
        bpy.context.view_layer.objects.active = obj
        obj.masonry.output = "SOLID"
        self.assertEqual(bpy.ops.mesh.regenerate_masonry(), {"FINISHED"})
        self.assertTrue(obj.masonry.core_object)
        self.assertEqual(obj.masonry.core_object.masonry_owner, obj)

    def test_undo_redo_restores_added_mesh_and_persistent_settings(self):
        bpy.context.preferences.edit.use_global_undo = True
        bpy.ops.ed.undo_push(message="Before Add Masonry")
        obj = add(width=24, height=12, output="SURFACE")
        name, before = obj.name, signature(obj)
        bpy.ops.ed.undo_push(message="After Add Masonry")
        self.assertEqual(bpy.ops.ed.undo(), {"FINISHED"})
        self.assertNotIn(name, bpy.data.objects)
        self.assertEqual(bpy.ops.ed.redo(), {"FINISHED"})
        obj = bpy.data.objects[name]
        self.assertEqual(signature(obj), before)
        self.assertTrue(obj.masonry.is_masonry)
        self.assertEqual(obj.masonry.output, "SURFACE")
        self.assertEqual(
            addon.properties.snapshot(obj.masonry), obj.masonry.applied_recipe
        )

    def test_adapter_reload_preserves_saved_object_settings(self):
        obj = add(width=24, height=12, output="SURFACE", corner_softening=0.5)
        name, before = obj.name, signature(obj)
        addon.unregister()
        importlib.reload(addon)
        addon.register()
        obj = bpy.data.objects[name]
        self.assertTrue(obj.masonry.is_masonry)
        self.assertAlmostEqual(obj.masonry.corner_softening, 0.5)
        self.assertEqual(signature(obj), before)
        bpy.context.view_layer.objects.active = obj
        self.assertEqual(bpy.ops.mesh.regenerate_masonry(), {"FINISHED"})
        self.assertEqual(signature(obj), before)

    def test_saved_recipe_survives_reopening_and_rebuild(self):
        obj = add(width=24, height=12, output="SURFACE", distortion=0.3)
        name, before = obj.name, signature(obj)
        obj.masonry.corner_softening = 0.7  # Unapplied drafts persist independently.
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "persistence.blend")
            bpy.ops.wm.save_as_mainfile(filepath=path)
            bpy.ops.wm.open_mainfile(filepath=path)
            obj = bpy.data.objects[name]
            bpy.context.view_layer.objects.active = obj
            self.assertTrue(obj.masonry.is_masonry)
            self.assertAlmostEqual(obj.masonry.corner_softening, 0.7)
            self.assertEqual(signature(obj), before)
            self.assertNotEqual(
                addon.properties.snapshot(obj.masonry), obj.masonry.applied_recipe
            )
            self.assertEqual(bpy.ops.mesh.regenerate_masonry(), {"FINISHED"})
            self.assertNotEqual(signature(obj), before)


if "--source" not in arguments:
    import masonpy
    import pyclipper

    assert "/src/masonpy/" not in masonpy.__file__, masonpy.__file__
    print("INSTALLED_DEPENDENCIES", masonpy.__file__, pyclipper.__file__)

suite = unittest.defaultTestLoader.loadTestsFromTestCase(MasonryTests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    sys.exit(1)
print("MASONRY_BLENDER_TESTS_OK")
