# masonPy

A procedural masonry library on an integer grid, with a lightweight local browser
workbench. The logical core has no Blender or GUI dependencies. Shape uses the small
Pyclipper polygon-offset library; there are no numerical-array or UI-framework
dependencies.
The [Blender extension](blender/README.md) adds labelled mapped surfaces or
extruded stones through Add → Mesh → Masonry, with saved settings and explicit
regeneration. Its self-contained ZIP bundles Pyclipper for Blender 5.1 on macOS
Apple Silicon; no dependency installation is performed at startup.

## Run

Python 3.10 or newer; install the project dependencies once and run from a checkout:

```sh
python3 -m pip install -e .
PYTHONPATH=src python3 -m masonpy.app --open
```

The installation also provides a launcher (reinstall after moving a checkout):

```sh
masonpy-web --open
```

The workbench runs at <http://127.0.0.1:8000>. It provides generator-specific
parameters, step/generate/reset/undo, shallow forward/reverse playback,
shared stone selection, procedural events and an expandable data inspector.
Advanced parameters are hidden by default; the checkbox at the right of the
Parameters heading reveals them without changing their values.
New sessions start at 104 × 60 grid units. The 3D workbench defaults to projected
mapping with roundness 0.25, stone depth 0.25 and a tube core of thickness 1.
The action bar owns operation feedback; background overlay warnings stay beside
their diagnostics. Events follow the final message after generation. Scrolling
up pauses following, and reaching the bottom or starting another placement action
resumes it.

The header follows **Wall → Shape → 3D**. Wall describes integer occupancy;
Shape applies shared fractional distortion and then mortar inset to independent
2D contours; 3D builds meshes from the
applied contours. Each stage retains its own parameters, log and result. Entering
Shape refreshes missing or stale contours. Entering 3D first refreshes Shape when
needed, then builds the mesh. Current results are reused; navigation never
generates more stones. Wall parameters remain drafts until Apply & reset
is pressed. Shape and 3D have
default-enabled Live checkboxes: editing valid parameters updates existing sources
after a short delay, with one processing request at a time. Turn Live off to use
Apply Shape / Build 3D explicitly for parameter changes. With Live off, automatic
source refresh uses applied settings (defaults on first entry) and preserves
unapplied drafts. Invalid live drafts also fall back to applied settings. The
Advanced checkbox only changes inspection. Playback in every stage replays
existing stones without processing.
Upstream changes mark downstream previews stale; failed operations retain the
last successful result with a stale label. Source revisions guard processing
requests and mesh responses against late results for another wall. A nonempty
partial or stopped wall can be shaped, and 3D requires
a current applied Shape (joint width zero is supported).

The Wall and Shape SVG viewers work offline. The 3D stage needs WebGL2 and
CDN access for pinned Three.js 0.180.0 imports; there is no npm or build step.
It supports flat walls and perimeter-preserving square/rounded/cylindrical
projections, with optional visual stone depth and a solid/tube core.

The 3D **Depth variation** slider adds deterministic per-stone variation around
Stone depth: 15% at depth 0.25 gives a range of 0.2125–0.2875 units. The rear
mounting surface and core stay fixed. **Detail seed** under Advanced controls
these values independently of generation and Shape. Variation ranges from 0 to
90%; zero disables it, and depth zero still creates surfaces only. Variation
does not add triangles or change with playback, iteration order or mapping cuts.

**Edge bevel** adds one exposed-front chamfer band, with its width in grid units.
Try 0.03–0.05 with depth 0.25. It works on the applied Shape, including softened
corners; it is a chamfer, not a multi-segment fillet. Both new effects default to
zero, preserving existing geometry. They participate in Live/Build, config
load/export and STL; 2D Shape/SVG and wall generation remain unchanged.

Bevels are limited per stone by depth and contour span, then reduced or skipped
if their geometry cannot be validated. Full projected rings retain their original
edge treatment to avoid artificial seam cuts. Each retained stone's **Info** shows
actual depth, applied bevel and fallback reason; Events summarize reductions and
list fallback IDs. A rare precision failure in varied extrusion falls back to
base depth. No stones are silently omitted. An invalid base shell fails the build
atomically and retains the previous preview.

Active details have work limits: bevels skip contours above 256 vertices, retry at
most six widths and limit individual chamfers to 12,000 scored triangles. Detail
builds stop above one million stone triangles; reduce mapping resolution or bevel
if that limit is reached. Closed-shell/float32 checks run before accepting treated
shells, and export validates again at the requested physical scale.

## Configurations and session history

Header **Export config** downloads a compact JSON recipe: generator, wall size,
generator parameters, and Shape/3D parameters currently in the controls, including
unapplied edits. It contains no stones, event logs, analysis or RNG snapshots.
Exporting a config is available before generation and does not apply the edits.

**Load config** validates all parameters before applying them, resets to an empty
Wall and restores the Shape/3D controls. Choose Generate wall explicitly to
reproduce the combination. A minimal recipe needs only `generator`, `width`,
`height` and `parameters`; omitted Shape/3D settings use defaults. Previously
exported full specimens are accepted by extracting their parameter recipe.
Imports are limited to 32 MiB and four million grid cells. There is no format
version/migration layer.

The history dropdown retains exact completed, partial and stopped walls for the
server session. A generation attempt creates an entry; subsequent placements and
repeat Generate update it. Reset or loading a config preserves the departing
entry. Selecting one restores its geometry and applied Wall controls, with the
current session's Shape/3D settings. An active downstream stage refreshes against
the restored source. History lives in memory; config files reproduce settings,
while SVG/STL preserve computed output geometry.

## Workbench analysis

The Wall inspector shows full-specimen coverage, stone/sneck counts and area,
deliberate snecks, maximum sneck aspect, vertical joint stack/length and layout
checks. Its final Events entry describes these in English, including the stopping
reason for a failed attempt. **Analysis colours** uses the battery gallery's
palette: ordinary stones grey, closing/fallback snecks blue, deliberate snecks
purple. Hide snecks and seam overlays can be combined with it.

`analysis/report.py` supplies these measurements to both the workbench and the
diagnostic battery. Sneck classification comes from dimensions against applied
Ashlar minima. Metrics always describe the full stored specimen, even during
playback; the final summary appears when all placements are visible. These are
face-layout checks, not structural engineering assessments.
Each battery gallery example also has a compact **Config JSON** download. Load
it and Generate wall to reproduce the parameters and seed. The full batch report
continues to retain geometry, outcomes and analysis for comparison.

## Export

Header **SVG** and **STL** export the full computed result, independent of viewer
overlays, zoom and playback position. SVG uses Wall contours on the Wall tab and
current Shape contours on Shape/3D. STL uses the current 3D build from any tab.
Buttons are disabled until their computed source is available and current. Wall and Shape export clean SVG
with stone IDs and logical coordinates. Periodic walls use one reference
circumference; finite walls retain whole overhanging stones. The mm/unit field
sets physical SVG dimensions and scales 3D coordinates for binary STL.

3D STL exports stones and any selected solid/tube core together as separate
closed shells, with topology/winding and float32 precision checks for each shell.
Build with positive stone depth. No boolean union or core fusion is performed;
contact surfaces remain in the file, so this is not one fused manifold.
Stale downstream results cannot be exported. Unapplied drafts are excluded, and
an export request is rejected if its applied revision changed in the meantime.

## Library

```python
from masonpy import AshlarGenerator, Wall, WallAnalysis, WallGeometry

wall = Wall(52, 30)
generator = AshlarGenerator(seed=1)

# One accepted placement at a time; generate(wall) consumes this same mechanism.
steps = generator.generate_incrementally(wall)
event = next(steps)
print(event.stone, event.explanation)

stats = WallAnalysis(wall).statistics()
mesh = WallGeometry(wall, mode="projected", roundness=0.5).stone_mesh(event.stone)
```

For non-destructive processing:

```python
from masonpy import shape_wall, WallGeometry

shaped = shape_wall(wall, joint_width=0.2)
# Each stone moves inward by 0.1 units on each boundary; source occupancy is intact.
meshes = WallGeometry(shaped, mode="flat", depth=0.5).to_dict()
```

Shape's **Distortion** slider ranges from 0 to 1 and defaults to zero, preserving
the original rectangle inset exactly. Seed and Variation scale appear with
Advanced. Seed controls a separate deterministic field; variation scale is in
grid units (default 6). Displacements are floating point, bounded to one quarter
of the thinnest incident stone dimension times the distortion factor. The base
and top retain their height. Shared T-junctions include corners across the
periodic seam, and each whole stone retains its source ID.

Shape also offers **Corner softening**, from 0 (off, the default) to 1. It acts
after distortion and mortar, cutting convex corners with short quadratic curves.
The nominal radius is one quarter of each post-mortar contour's short bounding
span, multiplied by the slider value. Individual corners are limited by their
adjacent edges; concave and nearly straight junctions stay intact. Try 0.5 first
for a gently worn silhouette, then increase toward 1 for rounder stones.

Small stones receive proportionally smaller treatment. Unsafe proposals retry at
smaller radii, then retain the original stone if necessary; no stone is removed.
Full-circumference stones are left unchanged to avoid rounding artificial seam
corners. Events/Info report softened, reduced and unchanged counts. Original
post-mortar profiles are retained alongside softened contours for future 3D edge
treatments. Wall occupancy and generation RNG are unchanged. The setting follows
Live/Apply, config load/export, SVG contours and the polygon-based 3D/STL path.
Existing errors from mortar consuming a stone remain explicit.

```python
shaped = shape_wall(wall, joint_width=0.2, distortion=0.6,
                    seed=1, variation_scale=6, corner_softening=0.5)
print(shaped.statistics.max_displacement)  # pre-inset movement in grid units
```

Processing validates simple outlines and positive-area overlaps, including
periodic copies, before and after inset. A consumed or split stone rejects the
whole application; it never silently drops snecks, repairs overlaps or changes
generation rules. Reduce joint width/distortion when a thin stone fails. Failed
applications retain the previous successful Shape/3D snapshots. Arbitrary polygon
insets use Pyclipper at 1e-7 grid-unit precision; redundant offset noise is cleaned
within two such steps. Source descriptions and occupancy remain integer-based.

Generators include running, stack, English and Flemish brick bonds, plus
skyline-based random ashlar. Stones retain one ID across the periodic boundary.
Brick courses must close exactly; default Flemish needs a multiple of 6
(e.g. width 54). Ashlar has hard joint-stack validation and soft coursing/snecking
preferences. A bounded attempt can raise `ConstructionFailure`; no rule is
silently relaxed to force completion.

Ashlar's **Allow snecks** checkbox controls undersized closing stock separately
from **Sneck preference**. Preference zero permits necessary repairs only;
`allow_snecks=0` prohibits them. All stones now obey the maximum dimensions,
including plateau repairs. Small corner closers can be below both ordinary
minima. Advanced **Minimum sneck size** sets their smallest dimension (default 1).
Refining the integer grid also expands the closing inventory; changing export
mm/unit alone scales the print without changing the layout.

## Source map

- `models/`: whole stones, occupancy, placement errors and geometric records.
- `generators/`: incremental interface, events, catalogue, `brick.py`, `ashlar.py`.
- `analysis/`: skyline, joint runs, local queries and descriptive statistics.
- `processing/`: inherited descriptions, periodic shared topology, fields, validation and inset.
- `geometry/`: projection, extrusion, detail settings, surface buffers and float32 shell validation.
- `configuration.py`: shared recipe validation and defaults for application adapters.
- `records.py`: isolated exact snapshots and continuation state for session history.
- `exporting.py`: clean SVG and validated binary STL attachments.
- `app/`: optional session, stdlib HTTP server and component-based browser UI.
- `diagnostics.py`: reproducible Ashlar quality battery and HTML/SVG/JSON reports.
- `blender/masonpy_blender/`: Blender operators, saved recipes, labelled mesh conversion and UI.
- `tools/`: self-contained Blender extension packaging and isolated installation tests.

Surface buffers use grid units with Y up and may repeat vertices between faces.
They retain separate stone IDs and optionally expose semantic triangle roles.
The Blender adapter converts them to connected per-stone mesh islands; shared
geometry does not depend on file exporters or a host API.

Public library imports remain available from `masonpy`. The local launcher is
now `python -m masonpy.app`; browser modules start in `app/static/startup.js`.

## Verify and understand

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

If Node is present, that suite also runs dependency-free browser-module unit
tests. Node is not needed to run the library or workbench.
The component tests can also run independently, and Ruff can check the source
and tests when installed as a development tool:

```sh
node --test tests/browser_modules.test.mjs
ruff check src tests
```

For a qualitative batch across dimensions, stock, style and bonding constraints:

```sh
PYTHONPATH=src python3 -m masonpy.diagnostics --output /tmp/masonpy-battery
open /tmp/masonpy-battery/report.html
```

The default `standard` suite runs 19 cases × 12 seeds (0–11, including the
reported seed 4). `--suite quick` uses six cases; `--suite stress` adds tripled
dimensions, broad stock and unusual wall proportions. `--seeds 4 --seed-start 12`
selects a different sample. Reports contain completion/fill, sneck count and area,
proportions, joint limits, failure categories, timing, full accepted walls and a
representative colour-coded SVG gallery. Case quality averages use complete
walls; incomplete-prefix measurements remain separate in JSON.

Legitimate construction failures do **not** fail the command. Size, occupancy or
joint-limit violations and unexpected errors produce a nonzero exit status.
Some cases intentionally have incompatible stock. This is a face-layout
diagnostic, not a structural assessment or guarantee of arbitrary-case completion.
Use `--compare /path/to/previous/report.json` to compare matching settings/seeds;
keep separate output directories for successive snapshots. The JSON records
effective settings, generator and shared-analysis source hashes, and compact
config JSON recipes alongside the representative SVGs. See [DOC.md](DOC.md) for the stock
rules, bounded lookahead and failure semantics.

## Project notes and future work

[DOC.md](DOC.md) explains the current algorithms, data contracts and code ownership.
[ROADMAP.md](ROADMAP.md) collects the remaining ideas and their design constraints,
including corner treatments, selective surface detail, richer mapping and Blender
integration. They are candidates for later work, not implemented features.
[README_old.md](README_old.md) preserves historical notes and superseded behaviour.

SVG, JSON and STL exports are implemented. STL validates each shell separately;
separate/contacting shells and practical printing constraints still need review
in the slicer. Config JSON stores parameter combinations; exact wall history remains
server-session state.
