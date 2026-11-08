# MasonPy Blender extension

**Add → Mesh → Masonry** generates a wall directly in the scene, with saved
settings and explicit regeneration. No modifiers are added. The extension
package is GPL-3.0-or-later.

## Install and use

Build the ZIP as described below, then use Blender Preferences → Get Extensions
→ menu → Install from Disk and select `dist/blender/masonpy_blender-0.1.0.zip`.
Enable **MasonPy Masonry**. The first package targets **Blender 5.1 on macOS Apple
Silicon**, including its Python 3.13 Pyclipper wheel; other platforms/Python
versions need matching wheels and testing before being advertised as supported.

1. In Object Mode choose Add → Mesh → Masonry (or search for Add Masonry).
2. Adjust the new object through Adjust Last Operation / F9.
3. Later, select the masonry or its backing and open the viewport sidebar's
   **Masonry** tab. Edit the saved settings and choose **Rebuild Masonry**.

The width, height, generator catalogue, Shape settings and 3D settings use the
same defaults as the browser workbench: running bond, 104 × 60, mortar 0.2,
projected mapping, roundness 0.25, depth 0.25 and a tube core. Grid unit defaults
to 0.1 Blender units; with metric scene scale 1 this gives 0.1 metres per unit.
Object placement starts at the 3D cursor and follows Blender's Add alignment
controls. Mesh coordinates are converted from core Y-up to Blender Z-up by a
rotation, preserving winding.

**2D surfaces** emits mapped stone fronts with no extrusion, bevel or backing.
Flat and column mapping both work. Solid settings are retained so switching back
to **Extruded stones** restores the chosen depth/detail/backing parameters.
**Apply Shape styling** independently enables the shared mortar, distortion and
corner softening pass. Turn it off to use the original rectangular contours.
Flat mapping does not produce a column core.

Recipes, applied settings and unapplied drafts survive saving/reopening a
`.blend`. The mesh remains ordinary Blender geometry even without the extension.
Rebuild preserves the object, placement, material slots and modifier stack, but
replaces its generated mesh, vertex weights and any direct mesh edits/shape keys.
It does not preserve topology-dependent modifier bindings. Rebuild is explicit;
loading a file or editing a field does not trigger generation. Undo/redo applies
normally. Invalid generation/geometry leaves the previous applied result intact;
partial failed construction is not silently inserted.

## Scene structure and labels

Each addition creates a **Masonry** collection containing one masonry mesh and,
when enabled, a separate **Masonry · Core** mesh parented to it. Stones are
separate connected islands in the masonry mesh, not individual objects. Touching
stones retain separate vertices. Copied roots rebuild independently of their
original backing object.

| Selection / attribute | Meaning |
| --- | --- |
| `Stone 00000`, etc. vertex groups | Logical stone ID |
| `Masonry` vertex group | All stone vertices |
| `Front`, `Back`, `Sides`, `Bevel` vertex groups | Vertices incident to those face roles |
| `Core` vertex group on the backing | All backing vertices |
| `masonry_stone_id` face integer | Logical stone ID; -1 on the core |
| `masonry_face_role` face integer | Front 1, back 2, side 3, bevel 4, core 5 |
| `masonry_is_sneck` face boolean | Source stone's sneck classification |

Role groups intentionally overlap at shared boundaries. Face attributes identify
roles precisely, including on mapped and chamfered stones. The mesh's
`masonry_role_labels` custom property records the integer legend. The root's
`masonry_config`, `masonry_diagnostics`, and `masonry_stone_count` custom properties
retain the applied shared recipe, treatment reductions/fallbacks, and count.
These are triangle meshes, not subdivision-ready quad topology.

## Build and test

No packages are downloaded or installed at extension startup. The ZIP bundles
the MasonPy wheel built from this checkout and an unmodified Pyclipper wheel.
Use Python 3.10 or newer with pip and prepare the build environment, then acquire
the dependency once:

```sh
python3 -m pip install 'setuptools>=68' wheel
python3 -m pip download --only-binary=:all: --no-deps \
  --platform macosx_11_0_arm64 --python-version 313 --implementation cp --abi cp313 \
  --dest /tmp/masonpy-blender-deps pyclipper==1.4.0
```

From the project root:

```sh
python3 tools/build_blender_extension.py \
  --pyclipper-wheel /tmp/masonpy-blender-deps/pyclipper-1.4.0-cp313-cp313-macosx_10_13_universal2.whl
python3 tools/test_blender_extension.py
```

Both tools accept `--blender /absolute/path/to/Blender`. Building uses the existing
setuptools/wheel development environment and Blender's extension validate/build
commands. The test tool creates and verifies a temporary Blender profile before
saving any preferences, installs the ZIP there, and tests actual Blender mesh
connectivity, labels, defaults, styling, regeneration, failure isolation,
backing ownership, undo/redo and saved settings. It does not install into the
normal Blender profile.

For development, `build/blender/masonpy_blender/` is the prepared extension root,
including its wheels. A dedicated Blender local repository may link to this
staging folder. Keep editing `blender/masonpy_blender/` and `src/masonpy/`, rebuild
to refresh staging, then restart Blender after core/wheel changes. Reload Scripts
supports adapter module reloading. Source alone has no bundled wheels; installing
it directly does not establish a self-contained development setup.

## Boundaries

- `src/masonpy/configuration.py` owns shared defaults and recipe validation.
- `generators/` and `processing/` own logical generation and derived contours.
- `geometry/` owns projection, extrusion, semantic face roles and shell checks;
  `include_roles=True` opts into metadata without changing browser/export payloads.
- `blender/masonpy_blender/build.py` prepares independent indexed stone islands
  at Blender float32 precision, preserving labels and checking edge incidence.
- The other adapter modules own Blender meshes, properties, operators and UI.
  They do not import browser sessions or start a server.

Pyclipper remains the clipping/offset backend. No replacement geometry backend,
Geometry Nodes system, modifiers, cages, shrinkwrap or arbitrary target fitting
is introduced. Future modifiers can consume the saved stone IDs and face groups.
