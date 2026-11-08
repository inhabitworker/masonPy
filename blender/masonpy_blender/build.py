"""Generate and index labelled masonry without importing Blender APIs."""

from collections import Counter
from dataclasses import dataclass, field
import math
import struct

from masonpy import Wall, WallGeometry, shape_wall
from masonpy.configuration import configuration
from masonpy.generators.catalog import get_generator_definition

FACE_ROLES = {"front": 1, "back": 2, "side": 3, "bevel": 4, "core": 5}
GROUP_NAMES = {
    "front": "Front",
    "back": "Back",
    "side": "Sides",
    "bevel": "Bevel",
    "core": "Core",
}


@dataclass
class IndexedMesh:
    """Connected triangles per stone, with disjoint IDs and semantic selections."""

    vertices: list = field(default_factory=list)
    faces: list = field(default_factory=list)
    stone_ids: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    snecks: list = field(default_factory=list)
    groups: dict = field(default_factory=dict)

    def append(self, surface, stone_id, scale, *, closed, sneck=False):
        """Weld only this island at float32 host precision; validate its edge incidence."""
        raw = surface["vertices"]
        if not raw:
            return
        extent = max(max(p[i] for p in raw) - min(p[i] for p in raw) for i in range(3))
        tolerance = max(extent * 1e-9, 1e-12)
        canonical, indices, seen = {}, [], {}
        for point in raw:
            if not all(math.isfinite(value) for value in point):
                raise ValueError(f"Stone {stone_id}: non-finite vertex")
            key = tuple(round(v / tolerance) for v in point)
            if key not in canonical:
                x, y, z = point
                canonical[key] = struct.unpack(
                    "<3f", struct.pack("<3f", x * scale, -z * scale, y * scale)
                )
            converted = canonical[key]
            if converted not in seen:
                seen[converted] = len(self.vertices)
                self.vertices.append(converted)
            indices.append(seen[converted])
        edges = Counter()
        first = len(self.faces)
        for triangle, role in zip(
            surface["triangles"], surface["face_roles"], strict=True
        ):
            face = tuple(indices[i] for i in triangle)
            if len(set(face)) < 3:
                continue
            a, b, c = (self.vertices[i] for i in face)
            u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
            normal = (
                u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0],
            )
            if sum(n * n for n in normal) == 0:
                raise ValueError(
                    f"Stone {stone_id}: triangle collapses at Blender precision"
                )
            for p, q in zip(face, face[1:] + face[:1]):
                edges[p, q] += 1
            self.faces.append(face)
            self.stone_ids.append(stone_id)
            self.roles.append(FACE_ROLES[role])
            self.snecks.append(bool(sneck))
            self.groups.setdefault(GROUP_NAMES[role], set()).update(face)
            self.groups.setdefault(
                f"Stone {stone_id:05d}" if stone_id >= 0 else "Core", set()
            ).update(face)
        if len(self.faces) == first:
            raise ValueError(f"Stone {stone_id}: empty mesh after precision conversion")
        for (p, q), count in edges.items():
            if count != 1 or (closed and edges[q, p] != 1):
                raise ValueError(
                    f"Stone {stone_id}: disconnected or inconsistently oriented shell at Blender precision"
                )
        # A surface may have boundary edges, but never more than two incident faces.
        self.groups.setdefault("Masonry" if stone_id >= 0 else "Core", set()).update(
            seen.values()
        )


def build_masonry(recipe, *, output="SOLID", use_shape=True, unit_scale=0.1):
    """Build a complete recipe off-scene; construction failures leave scene state untouched."""
    recipe = configuration(recipe)
    if output not in {"SURFACE", "SOLID"}:
        raise ValueError("Unknown masonry output")
    if not math.isfinite(unit_scale) or unit_scale <= 0:
        raise ValueError("Grid unit scale must be finite and positive")
    wall = Wall(recipe["width"], recipe["height"])
    generator, _ = get_generator_definition(recipe["generator"]).create(
        recipe["parameters"]
    )
    generator.generate(wall)
    source = shape_wall(wall, **recipe["shape"]) if use_shape else wall
    settings = dict(recipe["build"])
    primitive = settings.pop("primitive")
    thickness = settings.pop("tube_thickness")
    if output == "SURFACE":
        settings.update(depth=0, depth_variation=0, bevel=0)
        primitive = "none"
    geometry = WallGeometry(source, **settings).to_dict(
        primitive=primitive,
        tube_thickness=thickness,
        include_roles=True,
    )
    stones, core = IndexedMesh(), IndexedMesh()
    sources = {s.id: s for s in wall.stones}
    for surface in geometry["stones"]:
        stone_id = surface["id"]
        stones.append(
            surface,
            stone_id,
            unit_scale,
            closed=settings["depth"] > 0,
            sneck=sources[stone_id].traits.get("is_sneck", False),
        )
    core.append(geometry["primitive"], -1, unit_scale, closed=True)
    return (
        recipe,
        stones,
        core,
        {
            "stone_count": len(wall.stones),
            "shape": source.statistics.to_dict() if use_shape else None,
            "geometry": geometry.get("statistics"),
        },
    )
