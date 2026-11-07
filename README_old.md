# Historical MasonPy notes

> Archived description of an earlier iteration. Commands, dependencies, defaults,
> UI behaviour and future-work statements below may be superseded. Use
> [README.md](README.md) and [DOC.md](DOC.md) for the current implementation, and
> [ROADMAP.md](ROADMAP.md) for remaining ideas. The original notes are retained
> below for context.

MasonPy is an early-stage procedural masonry toolkit. This iteration provides a
Blender-independent Python library and a small local web workbench for inspecting
generation one placement at a time.

## Run the web workbench

MasonPy has no runtime dependencies beyond Python 3.10 or newer.

```sh
python3 -m pip install -e .
masonpy-web --open
```

Then visit <http://127.0.0.1:8000> if the browser does not open automatically.
You can also run it without installation from a checkout:

```sh
PYTHONPATH=src python3 -m masonpy.web
```

The toolbar controls the wall dimensions and builds generator-specific inputs
from the catalogue returned by Python. Generators are grouped by category, and
the Brick category contains running, stack, English, and Flemish bonds. The
Stone category currently contains a randomized ashlar generator with independent
minimum and maximum stone dimensions plus a repeatable random seed.
The workbench starts with a 52 × 30 logical grid; stone and brick size defaults
remain unchanged. Ashlar starts with joint-stack limiting enabled at 2,
coursing factor 0.5, and snecking factor 0.2.
**Place one** advances the same Python generator iterator that **Generate wall**
consumes to completion.
Resetting creates a new wall and iterator. The SVG and event log are rendered
from API state; the browser contains no masonry generation logic.
The parameter heading shows its value summary only when collapsed.

The side frame's **events** / **info** tabs share the current stone selection.
Events use logical stone IDs as their clickable numbers. Older/unselected entries
are compact; the selected entry expands into target, width, height, candidate
availability, bonding, and seeded/style selection details. The same structured
decision record is available in each Python `GenerationEvent.decision`.
Info is a lazily expandable JSON-like tree: selected-stone geometry, traits,
neighbours, supporting/adjoining joints and original placement, or (with no
selection) wall statistics, distributions, joints, exposed edges, skyline,
occupancy and placements. Local analytics describe the **current** visible
prefix, whereas the placement decision describes its original construction time.
Selecting a stone again clears selection and returns Info to wall data.

Stones and their numbered event links select each other in both directions.
**Undo last** removes the latest logical placement and causes the next step to
re-evaluate that position. The `▶` and `◀` controls provide shallow forward and
reverse playback: stones are only hidden and revealed, while the generated wall
and event data remain intact for replay.

The controls below the canvas zoom, restore the fitted view, and toggle
horizontal wrapping. You can also zoom with the mouse wheel and pan by dragging
anywhere on the wall, including stones.
Zoom-out stops at a centred fit with margin around the wall/overhangs and axes;
off-centre views progressively return toward the fit as they zoom out.
A short press selects a stone; pressing
it again deselects it. Moving more than five pixels or holding for 240 ms starts
a pan instead. When the whole wall fits, releasing a drag slides it back to
centre. When zoomed in, selection and generation steps smoothly centre the
selected stone. Wrapping is a display-only projection: with it off, whole stones
may overhang the reference wall; with it on, overhanging portions are split and
drawn at the opposite edge. Toggling it does not reset or modify the wall.

## Run the tests

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 3D presentation

The default **2d** tab is unchanged. **3d** lazy-loads Three.js **0.180.0**
and the matching OrbitControls from a pinned jsDelivr import map: no npm,
bundler, build step, or additional Python packages. CDN access and WebGL2 are
needed only for 3D; loading failures leave the 2D workbench usable.
This follows the [Three.js CDN/import-map setup](https://threejs.org/manual/pages/installation.html)
and uses standard [OrbitControls](https://threejs.org/docs/pages/OrbitControls.html).
Drag to orbit, wheel/pinch to zoom, right-drag to pan, and use **Fit** to reframe.
Short clicks ray-cast stones and share selection with Events/Info; clicking a
selected stone again deselects it. Stone colours match the 2D view, and outlines
show logical joints, not triangle diagonals.

3D controls select a flat wall or a projected column, roundness (0 = square,
1 = faceted cylinder), and faces per rounded corner (1–64). Projection settings
never reset generation or draw random numbers. Placement, undo, reset and
regeneration rebuild geometry; shallow playback only changes mesh visibility.
Camera navigation is retained during placement; switching mapping or dimensions
fits the new scene. Old GPU geometries/materials are disposed on rebuild.

`masonpy.geometry.WallGeometry` owns the reusable projection mathematics and
triangle/outline data, with no renderer or GUI imports. For example:

```python
from masonpy import WallGeometry

view = WallGeometry(wall, mode="projected", roundness=0.6, resolution=8)
surface = view.stone_mesh(wall.stones[0])
scene = view.to_dict(primitive="tube", tube_thickness=0.5)
```

Coordinates use Y-up, with logical x interpreted as clockwise arc distance
along an XZ cross-section. Rounded-square samples are scaled so their **actual
polygonal perimeter** equals `wall.width`, including low resolutions. Each stone
is split at every intervening face boundary and perimeter crossing. Surface
triangles are outward-wound; matching top/bottom strips fold across corners.
The cylindrical endpoint is a polygonal cylinder, converging as resolution rises;
no renderer-dependent curve tessellation changes the perimeter.

Both brick and ashlar generators construct logically periodic walls, independent
of the viewer tabs. Projected stones fold once as whole logical objects, with
no clone meshes or boundary clipping. A brick spanning x=0 owns cells on both
ends of the occupancy grid under the **same ID**, and all of its face strips
belong to one projected mesh. Flat 3D shows the same whole brick overhanging.
Library-created finite walls may also be projected if their whole modulo
coverage is valid; conflicting overhangs cause an explicit error rather than
being silently clipped away.

Default stone depth is **zero**: only surfaces are emitted. Positive **Stone
depth** builds visual shells outward from the target, with mitered offsets at
corners and no internal caps at fold lines. An optional independent solid core
or tube is actual scene geometry, not just a projection guide. Flat mode has no
core. The tube uses a similar scaled inner section, with the configured thickness
as its minimum face separation; it is not a uniform-offset fillet. This avoids
inverted tiny fillets. Tube thickness must be below the section's inradius.

These are visual meshes, not an automatic printable union: zero-depth stones
have no volume, adjoining positive-depth stones remain separate shells, vertices
may be duplicated for hard normals, and no welding, boolean union, export or
manufacturability checks are provided yet. Neither view changes grid occupancy,
stone dimensions, generator state or seam analysis. Projection tests run entirely
in Python, without a browser or Three.js.

## Architecture

- `masonpy.geometry` derives renderer-independent 3D surfaces and optional visual
  shells/cores from the wall. `/api/geometry` passes those arrays to the small
  Three.js viewer; projection never feeds back into placement or occupancy.
- `masonpy.models` contains `Stone` and `Wall`. All dimensions and coordinates
  are integer grid units, with positive dimensions. A wall owns its stones and an
  occupancy grid containing stone IDs. `Wall.add_stone()` rejects duplicate IDs,
  invalid dimensions, overlaps, and out-of-bounds placements before mutation.
  Stones may extend horizontally beyond the finite reference grid, while
  finite occupancy records only the cells intersecting that grid; logically
  periodic walls record cells modulo their width. This preserves each
  boundary stone as one logical object for either flat or wrapped presentation.
- `masonpy.generators` defines the small `WallGenerator` interface, structured
  `GenerationEvent` result, and a data-driven catalogue of categories and
  parameter schemas. All four brick bonds use a common course planner. Running
  bond offsets alternate stretcher courses, stack bond aligns them, English bond
  alternates stretcher and header courses, and Flemish bond alternates faces
  within each course with headers centred over stretchers. Ashlar generation
  repeatedly selects the lowest contiguous skyline valley and chooses a random
  fitting width and height. It prefers to avoid undersized remnants, checks
  optional joint constraints, and explicitly fails when it finds no continuation.
  Incremental generators resume from current wall state, allowing an undone
  ashlar position to be randomly reconsidered.
- `masonpy.web` owns a generation session and exposes a tiny JSON API using
  Python's standard-library HTTP server. The bundled HTML, CSS, JavaScript, and
  SVG frontend only visualise and control that server-side state.

The logical origin is the wall's bottom-left, and occupancy is addressed as
`occupancy[y][x]`. Stretcher width must be even so half-repeat offsets
stay integral. Horizontal boundary bricks remain whole and may overhang; only
the top course is shortened when wall height is not divisible by brick height.
Events explain seam crossings and stone traits retain machine-readable course
metadata. Brick generation first checks every planned course: its horizontal
repeat must divide the circumference exactly. Running and stack bond require a
multiple of stretcher width; English requires compatibility with each face width
used; Flemish requires a multiple of stretcher width plus header width (6 with
the defaults, e.g. a circumference of 54). The default circumference of 52 fits
default running, stack and English bonds. Phase offsets cannot repair a mismatch.
An incompatible configuration raises `ConstructionFailure` before any brick is
added, and the workbench records the failing course, required repeat and remainder
in the event log. Such failures require a configuration change, not another seed.
The existing vertical top-course shortening is unchanged.

## Library example

```python
from masonpy import RunningBondGenerator, Wall

wall = Wall(width=24, height=12)
generator = RunningBondGenerator(stretcher_width=4, brick_height=2)

for event in generator.generate_incrementally(wall):
    print(event.stone, event.explanation)
```

`generator.generate(wall)` is a convenience that consumes this same iterator
and returns all events.

## Scope and future work

### Wall analysis

`WallAnalysis(wall)` is a live, computed view of one wall, independent of the
generator and UI. Queries read current geometry without persistent caching, so
the same object remains useful after additions, undo, or a failed construction.
Reset creates a new wall; construct a new analysis view for that new object.
An optional `wrap_x` override uses the same validated projection as diagnostics.

```python
from masonpy import WallAnalysis

analysis = WallAnalysis(wall)
stats = analysis.statistics()
runs = analysis.horizontal_joints(elevation=4)
neighbours = analysis.neighbours(x=10, y=2, width=6, height=2)
support_joints = analysis.joints_below(x=10, y=2, width=6)
```

`statistics()` returns logical stone counts, average dimensions and aspect
ratio, dimension/aspect-ratio frequency distributions, sneck count/proportion,
maximum vertical stack/length, and horizontal run-length distributions overall
and per elevation. Exact rational aspect ratios group equivalent shapes.
Dimensions count each whole logical stone once, including overhangs and hidden
snecks; averages are per stone, not weighted by area. Empty-wall averages and
proportions are zero. `to_dict()` adds the individual joint records for JSON use.

`horizontal_joints()` and the standalone `horizontal_joints(wall)` return
immutable `HorizontalJoint(x, y, length)` records over `[x, x + length)` at y.
A joint requires distinct occupied stones above and below. Exposed tops and
bottoms are excluded, as are wall boundaries. Runs at one elevation remain
separate across gaps or spanning stones. Periodic runs crossing x=0 are a single
record whose endpoint may exceed wall width; a full ring uses x=0. Per-elevation
totals describe alignment but never merge disconnected runs into one joint.
The horizontal overlay draws a crossing record as two pieces in the reference
grid, regardless of how stone overhangs are displayed.

Local queries include `stone_at(x, y)`, `neighbours(x, y, width, height=1)`
(deduplicated stones touching each side), `joints_below(x, y, width)` (positions
strictly inside a support span), and `adjoining_ids_below(x, y)` (IDs on each side
of the uninterrupted completed joint ending there). `exposed_edges()` describes
maximal occupied/empty boundaries with position, length, and outward side.
`surface()` supplies skyline heights and top stone IDs; `skyline()` supplies
heights alone. `plateau_after(stone)` describes a hypothetical periodic skyline
run without modifying the wall or judging placement validity. Ashlar consults
these descriptions, while its boundary pressure, hard constraints and weighted
preferences remain generator decisions.

The wall header shows actual statistics rather than repeating input parameters.
During playback it uses backend analysis of the visible placement prefix;
hiding snecks does not remove them from analysis. Parameters remain in their
separate collapsible controls.

These analyses currently describe grid-aligned, axis-aligned geometry only.
Joint runs are distinct from exposed skyline plateaus. Local queries do not
rank candidates or predict construction success, and hypothetical plateau queries
currently require horizontal periodicity. Statistics and overlays are computed
directly; large grids may eventually warrant revision-aware caching.

The Parameters panel and its nested advanced controls collapse independently.
Ashlar's enabled-by-default **Jitter first stone** option randomizes its initial
horizontal position. Its skyline and occupancy are logically periodic: a valley
may continue across the last and first columns, and a crossing stone remains one
object. Disabling jitter restores an initial x=0 while retaining circular valley
detection. `Wall(..., wrap_x=True)` supports this occupancy explicitly; both
ashlar and valid brick generators enable it on an empty wall. Display wrapping still only changes how
the same stones are drawn. Undo and resumed generation reconstruct the circular
skyline from the remaining stones.
Brick generators expose `course_offset` in advanced controls: the course index
times this value is added to the conventional bond phase, modulo that course's
horizontal repeat width. Zero retains the standard bond. Ashlar exposes its seed
under advanced controls.

`vertical_seams(wall)` returns immutable `VerticalSeam(x, y, length, left_count,
right_count)` records for maximal uninterrupted vertical joints, in logical units.
Its `stack_count` property is `max(left_count, right_count)`: the number of
distinct adjoining stones on the more subdivided side. A tall stone adjoining
three smaller stacked stones therefore gives stack count 3. This is the chosen
computational definition, not a universal masonry standard.
Every unit must have occupied cells with distinct stone IDs on both sides.
Changing IDs at a horizontal course boundary does not interrupt the joint;
vacancies and a spanning stone do. Exposed wall edges are excluded.

Logical wrapping follows `wall.wrap_x` by default; pass `wrap_x=True` or `False`
to explicitly override it for analysis. It is independent of the viewer's
Wrapping projection. It projects whole stones modulo wall width, includes the
boundary joint at x=0 exactly once, and excludes a boundary crossed by one stone.
Overlapping projections or stones wider than the circumference raise ValueError.
The viewer draws a boundary diagnostic at both edges for clarity. The Seams
checkbox updates the overlay, including during playback using only visible
placements. Report seams writes one snapshot summary to the event console;
`report_vertical_seams(wall, wrap_x=None, logger=None)` also supports Python
logging. Reports do not become placement events or affect undo.

Diagnostics currently measure grid-aligned vertical runs only. They do not model
mortar thickness, judge structural quality, or analyse
diagonal joints. Periodic gaps in a partial wall remain gaps, and incompatible
brick circumferences can make the periodic projection invalid. The records are
also used by the ashlar hard constraint.

### Ashlar constraints and construction failure

Advanced controls provide **Limit vertical joint stacks** (on by default),
**Maximum vertical joint stack** (2), **Coursing factor** (0.5), and
**Snecking factor** (0.2). Both coefficients accept decimals from 0 through 1;
they replace the previous coursing and snecking switches.
With the limit enabled, every accepted placement must keep all completed joints,
including the periodic boundary, at or below that stack count. There is no
absolute-height constraint. Exposed boundaries against empty space do not count.

For each lowest valley, the generator detects joints in the supporting row,
including across the periodic boundary. It ranks ordinary widths to end between
those joints, crossing or stopping short of them rather than extending a joint
upwards. Crossing is not compulsory: multiple small stones may lie entirely
within one supporting stone. Spanning a whole valley earns no bonus; an end
plateau preference applies when a candidate actually reaches that end. A fully
level skyline starts over the interior of a supporting stone.
At enclosing valley ends it estimates the stack after adding the proposed stone.
When this reaches the enabled limit, the neighbour's top becomes a preferred
plateau height so later stones can bridge the boundary.

Up to 128 ordinary width/height candidates are considered, with exact plateau
heights included explicitly. Ordinary stones always obey both size ranges. When
ordinary sizes cannot satisfy pressured plateau targets, enabled snecking tries
up to 64 targeted repairs before the remaining ordinary candidates. These can
be thin tall stones reaching the neighbour's top, or long flat stones closing a
shallow valley. The thin dimension is at most 2 units; the long dimension may
exceed its usual maximum only for these exact plateau repairs. Up to 128 ordinary
thin filler candidates remain available as a final fallback. Tiny fillers with
both dimensions below the normal ranges are not introduced.

Snecks have `traits['is_sneck'] == True` and obey the same hard stack limit.
Metadata also records whether a placement crosses/ends on joints below and its
pressured plateau targets. Events explain bonding and levelling decisions.
Width and plateau priorities are local heuristics, not additional hard
constraints: the final seam check still decides whether a candidate is valid.

### Context-aware style coefficients

Candidate enumeration stays bounded. Occupancy and the enabled joint-stack
limit are checked before any style weight is used. Within the best valid bonding
rank, seeded weighted selection considers all candidate sizes: there is no bonus
for filling a valley, crossing more joints, or choosing the widest stone.
Pressured plateau targets and avoiding supporting seam endpoints retain priority.

`WallAnalysis.alignment_after(stone)` describes the hypothetical top elevation:

- `plateau_extent` and `plateau_stones`: the connected circular skyline run.
- `connected_extension`: existing skyline length joined by the candidate.
- `disconnected_skyline_length`: other exposed tops at that elevation.
- `existing_joint_length`: total completed horizontal joints at that elevation,
  including disconnected runs. This is separate from exposed skyline geometry.
- `connected_joint_length` and `disconnected_joint_length`: completed joints
  touching either end of the candidate's top versus remote runs. A neighbour
  taller than the candidate can expose this kind of internal alignment.

The generator takes one surface/joint snapshot per placement, not one analysis
per candidate. Its modest alignment signal is
`2*log1p((connected_extension+connected_joint_length)/typical_width)
+ 0.15*log1p(plateau_stones-1)
+ (1.5*disconnected_skyline_length + disconnected_joint_length)/wall_width`.
The weight is `exp((2*coursing_factor-1)*signal)`. Thus 0 discourages existing
alignments, 0.5 is neutral, and 1 encourages them; intermediate values change
smoothly. An isolated new elevation gets weight 1, regardless of stone width.
Necessary levelling remains possible at every value. This does not promise
perfect courses, maximum run lengths, or completion.

`snecking_factor=0` prohibits all snecks, including fallbacks. Any positive value
enables the existing thin-stone and exact plateau-repair fallback tiers. For
deliberate snecks competing with ordinary stones, there must first be a useful
opportunity: reaching an enclosing top, closing a narrow valley, or offsetting a
following ordinary stone across a supporting joint. Arbitrary thin stones are
not introduced to break up a plateau. Deliberate candidates compete only at the
best ordinary bonding rank; they cannot bypass bonding priorities for style.
Their weight multiplier is `4*snecking_factor**3 /
(1 + 8*existing_sneck_proportion + 2*touching_sneck_count)`. This makes low
nonzero settings mainly fallback-oriented, while high settings admit useful
deliberate choices and temper repeated neighbouring snecks. It is not a direct
sneck probability or a target sneck percentage. With no valid ordinary candidate
in a fallback group, this multiplier is unnecessary: a repair remains available
even at a tiny positive coefficient.

Traits retain all alignment measurements plus `sneck_purpose`,
`sneck_deliberate`, and `height_variation_choice`. Events explain weighted height
choices and distinguish deliberate and fallback snecks. Undo recomputes context
from remaining geometry and continues the seeded random stream. Shallow playback
only reveals existing placements, so it does not make new style decisions.

Tests compare continuous joint lengths, same-elevation joint totals, sneck
frequency/purpose and size distributions over 24 fixed seeds, as well as hard
constraints and repeatability. Results are tendencies, not per-seed guarantees;
strictly failed attempts are measured as accepted prefixes. The analysis is
grid-aligned, and hypothetical alignment currently requires logical periodicity.
There is no look-ahead, rescue of prior choices, or general style optimiser.

**Hide snecks** affects drawing only: fillers remain in occupancy, events, and
seam analysis. The overlay and reports expose current stack counts and limit.
Rejected candidate counts and sneck decisions are summarised per placement,
with Python logging available under `masonpy.generators.ashlar`.

The library raises `ConstructionFailure` with `x`, `y`, `reason`, and `rejected`
when its bounded attempt cannot continue. The last valid partial wall remains
intact. The web session exposes this as `failure`, distinct from `complete`, and
logs a single failure entry. Step and Generate do not retry a failed session.
Playback can replay its accepted placements. Explicit Undo removes the last
placement and clears failure (or just clears it if empty); Reset starts afresh.
Undo continues the random stream, so a replacement can differ. Fresh generators
with identical seeds, parameters, and actions give identical results.

This is a local greedy algorithm with immediate boundary awareness: it neither
backtracks, considers alternate valleys after failure, nor automatically regenerates.
Earlier valid stones can leave a narrow valley or make a later completed joint
exceed the limit. A failure proves only that this bounded continuation attempt
stopped, not that the wall is mathematically impossible. Tall walls with a low
stack limit can fail frequently; snecking is an additional constrained capability,
not a guarantee of success.

This version keeps the four brick generators deterministic and geometrically
simple. The initial ashlar generator provides random dimensional variation and
skyline packing, optional seam-stack constraints, and optional sneck fillers,
with context-aware coursing/snecking preferences, but no look-ahead or openings. Persistence, Blender
integration, and concurrent editing are also unimplemented. English and Flemish
patterns remain simplified rather than exhaustive historical quoin and
queen-closer rules.

The separate presentation geometry layer now derives surfaces from the unchanged
logical grid. Later post-processing can add mortar gaps, varying joint widths, displaced
stones, distorted vertices, and similar naturalising effects belong there rather
than in `Wall`. Generator implementations can likewise grow independently while
continuing to emit stones and events into the same model.

The `_junk` implementations were consulted for their useful skyline, valley,
socket, and seam concepts, but remain reference material and are not imported by
this implementation.
