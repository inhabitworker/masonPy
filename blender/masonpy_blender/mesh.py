"""Translate prepared islands to Blender meshes and replace owned scene data."""

import json

import bpy

from .build import FACE_ROLES
from .properties import copy_options, snapshot


def make_mesh(name, indexed):
    """Create an unlinked mesh with face attributes, preserving prepared triangle order."""
    mesh = bpy.data.meshes.new(name)
    try:
        mesh.from_pydata(indexed.vertices, [], indexed.faces)
        mesh.update()
        if mesh.validate(verbose=False):
            raise ValueError("Blender rejected generated mesh topology")
        for name, data_type, values in (
            ("masonry_stone_id", "INT", indexed.stone_ids),
            ("masonry_face_role", "INT", indexed.roles),
            ("masonry_is_sneck", "BOOLEAN", indexed.snecks),
        ):
            attribute = mesh.attributes.new(name, data_type, "FACE")
            attribute.data.foreach_set("value", values)
        mesh["masonry_role_labels"] = json.dumps(FACE_ROLES, sort_keys=True)
        return mesh
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise


def assign_groups(obj, indexed):
    """Recreate generated selection groups on the newly replaced geometry."""
    obj.vertex_groups.clear()
    for name, indices in indexed.groups.items():
        group = obj.vertex_groups.new(name=name)
        if indices:
            group.add(sorted(indices), 1.0, "REPLACE")


def remove_unused(mesh):
    """Release replaced mesh datablocks only when no other object still uses them."""
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def apply_result(context, options, result, *, obj=None, matrix=None):
    """Prepare meshes before touching the scene; preserve the root object on rebuild."""
    recipe, stones, core, diagnostics = result
    stone_mesh = make_mesh("Masonry · Stones", stones)
    try:
        core_mesh = make_mesh("Masonry · Core", core) if core.faces else None
    except Exception:
        remove_unused(stone_mesh)
        raise
    if obj is None:
        collection = bpy.data.collections.new("Masonry")
        context.collection.children.link(collection)
        obj = bpy.data.objects.new("Masonry", stone_mesh)
        collection.objects.link(obj)
        obj.matrix_world = matrix
        old_mesh = None
    else:
        collection = (
            obj.users_collection[0] if obj.users_collection else context.collection
        )
        old_mesh = obj.data
        # Retain material slots while replacing all generated topology and weights.
        for material in old_mesh.materials:
            stone_mesh.materials.append(material)
        obj.data = stone_mesh
    assign_groups(obj, stones)
    old_core = obj.masonry.core_object
    if old_core and old_core.masonry_owner != obj:
        old_core = None  # A duplicated root must not replace the original's backing.
    if core_mesh:
        if old_core:
            previous = old_core.data
            for material in previous.materials:
                core_mesh.materials.append(material)
            old_core.data = core_mesh
            remove_unused(previous)
            core_obj = old_core
        else:
            core_obj = bpy.data.objects.new("Masonry · Core", core_mesh)
            collection.objects.link(core_obj)
            core_obj.parent = obj
            core_obj.masonry_owner = obj
        assign_groups(core_obj, core)
    else:
        core_obj = None
        if old_core:
            previous = old_core.data
            bpy.data.objects.remove(old_core, do_unlink=True)
            remove_unused(previous)
    # Copy only after successful geometry preparation; settings survive save/reopen.
    copy_options(options, obj.masonry)
    obj.masonry.is_masonry = True
    obj.masonry.core_object = core_obj
    obj.masonry.applied_recipe = snapshot(obj.masonry)
    obj["masonry_config"] = json.dumps(recipe, sort_keys=True)
    obj["masonry_diagnostics"] = json.dumps(diagnostics, sort_keys=True)
    obj["masonry_stone_count"] = diagnostics["stone_count"]
    obj["masonry_output"] = options.output
    remove_unused(old_mesh)
    return obj
