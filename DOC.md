# How masonPy works

This is a map of the current implementation, not a promise of a general masonry
solver. Coordinates and sizes are integer grid units. Rendering is a separate
interpretation of that logical construction.
See [README.md](README.md) for setup and usage, [ROADMAP.md](ROADMAP.md) for
unimplemented ideas, and [README_old.md](README_old.md) for historical context.

## Boundaries and ownership

`models/stone.py` defines one whole `Stone`: ID, x/y, width/height and extensible
traits. A wrap-crossing stone is never replaced by two logical sub-stones.
`models/wall.py` owns placement order and `occupancy[y][x]`, whose cells hold
stone IDs or `None`. The origin is bottom-left.

`Wall.add_stone()` validates before writing any cell: IDs, dimensions, vertical
bounds, horizontal intersection, then overlap. A finite wall clips occupancy to
the reference rectangle. A periodic wall visits columns modulo width and rejects
stones wider than the circumference. Removing the last stone clears its cells.
Both current generator families explicitly enable logical wrapping on an empty
wall; arbitrary library-created finite walls remain useful for other analyses.

The browser's wrap toggle is presentation-only. It does not turn logical
periodicity on/off, regenerate a wall, or change diagnostics' default topology.

## One generation mechanism

`generators/interface.py` defines `generate_incrementally(wall)`. Each iteration
places one stone and yields a `GenerationEvent` with the stone, explanation and
structured decision snapshot. `generate(wall)` simply consumes that iterator.

`generators/catalog.py` describes each generator's fields, defaults, numeric
bounds, grouping and advanced/toggle flags. It validates configuration for the
library and also supplies the browser's controls. There is no second placement
algorithm in JavaScript.

`ConstructionFailure` means a bounded continuation has failed, distinct from an
individual `PlacementError`. The last accepted prefix remains inspectable.
The session treats failure as terminal until explicit undo/reset. Configuration
failures, such as incompatible brick circumferences, cannot be fixed by a seed.

## Brick courses

All bonds in `generators/brick.py` share one course planner. The subclasses provide
only the conventional course phase and repeating `(width, face)` sequence:

| Bond | Repeated faces | Conventional phase |
| --- | --- | --- |
| Stack | stretchers | zero |
| Running | stretchers | alternate courses: half a stretcher |
| English | alternate stretcher/header courses | header courses: half a header |
| Flemish | stretcher, header | alternate courses: half the full repeat |

Each course adds `course_index * course_offset` to that phase, modulo its repeat
width. Before placement, every planned course's repeat must divide the wall
width. English can therefore require compatibility with two face widths;
Flemish requires a multiple of their sum. The preflight fails before adding any
brick if a course cannot close.

The cursor traverses a complete circumference, keeping a crossing brick whole.
Fully preceding faces are skipped and accounted for at the far end of the
repeat. Occupancy wraps both visible portions under the same ID. Heights use the
configured course height, shortened only at the wall's final vertical boundary.
Resuming verifies that existing stones are the exact deterministic prefix.

## Ashlar: valley, candidates, validity, preference

`generators/ashlar.py` reconstructs the circular skyline from occupancy when an
iterator starts, including after undo. This avoids retaining a stale placement
counter or skyline. A generation step has these responsibilities:

1. **Target geometry.** Find a lowest contiguous skyline valley. Prefix/suffix
   runs join across x=0. Ties use the earliest circular start. The first stone can
   have a seeded random origin (default on). A fully level later skyline starts
   over a supporting stone's interior, if available, rather than perpetuating an
   arbitrary origin joint.
2. **Bonding context.** Inspect supporting joints inside the valley and the tall
   stones enclosing its ends. If a prospective boundary would consume the last
   allowed joint-stack position, prefer a height levelling with the neighbour:
   a later stone can then bridge the boundary and terminate that stack.
3. **Geometric possibilities.** Enumerate ordinary width/height pairs in range
   and within the remaining valley/wall height. Large spaces are seeded samples,
   not exhaustive searches. Exact pressured plateau heights are included.
4. **Priorities and hard validity.** Group sizes by missed levelling targets,
   landing an end on a supporting joint, and tiny width/top remainders. Stock
   composition and the two affected boundary runs decide immediate feasibility.
   Exposed edges are checked for the identity of the unavoidable next stone too.
   There is no temporary mutation of the source wall.
5. **Local lookahead.** Check pressured narrow valleys touching a candidate's
   ends using read-only grid overlays: at most two future levels and 64 trial
   nodes per candidate. A budget limit means unknown, never proven impossible.
   This checks combined closing requirements; it is not a global packing solver.
6. **Soft selection.** `_choose_candidate()` applies geometry-based weights
   within the first bonding group containing hard-valid choices. It makes one
   seeded choice. Snecks with aspect above 3:1 receive a smooth proportion penalty,
   not a hard ban. Width alone earns no reward.
7. **Commit and explain.** Add the chosen stone, advance its skyline columns,
   and emit `_placement_event()`. Explanation formatting makes no RNG draws.
   Events retain size/weight options, exhausted groups and rejection categories.
   The completed wall is independently checked with the full seam analysis.

`generators/ashlar_rules.py` owns bounded ordinary/closing stock, exact one-axis
integer composition, cached boundary runs and speculative overlays. An empty wall
is checked for provable width/height incompatibility before placing anything.
Unit-width stock that cannot bridge the required vertical joints is also rejected
up front. These are necessary feasibility checks, not a full construction proof.

### Sneck permission and preference are separate

**API change:** `snecking_factor=0` now means necessary repairs only. Use
`allow_snecks=0` to prohibit sub-minimum stones. The UI exposes Allow snecks and
Sneck preference; Minimum sneck size remains advanced.

Ordinary stones obey both configured ranges. All repairs obey the same hard
maximum width and height. Closing dimensions range from `min_sneck_size` (default
1, no larger than either ordinary minimum) to those maxima. Small corner closers
may be below both ordinary minima. The closing inventory therefore expands with
refined ordinary dimensions instead of staying fixed at one or two units.

The search order is ordinary priority groups with useful deliberate snecks,
exact targeted repairs, remaining ordinary groups, then filler fallbacks. Within
repairs/fallbacks, try a stone with at least one ordinary dimension before using a
both-small corner closer. Both-small stones are not decorative alternatives to
ordinary stock. This avoids needlessly stacking tiny pieces up a narrow space.

Ordinary and filler tiers sample at most 128 dimensions each, with exact closing
heights included. If those fail, an exhaustive stock fallback tests previously
untried pairs, capped at 4096. A large unexhausted inventory produces a distinct
`search_budget` failure. The finite local lookahead cannot guarantee completion.

Deliberate snecks need a local purpose: reach an enclosing top, close a narrow
valley, or offset the next ordinary stone across a supporting joint. They compete
at the best ordinary bonding rank. Their multiplier when ordinary alternatives
are present remains:

`4 * snecking_factor**3 / (1 + 8*sneck_proportion + 2*touching_sneck_count)`

Global frequency and actual touching neighbours temper repetition. This is
neither a direct probability nor a quota. Necessary closers remain available at
preference zero. No size or joint constraint is silently relaxed to finish.

Failures retain the accepted prefix and include a machine-readable `kind` and
`details`: incompatible configuration, unavailable closer, local dead end, or
unexhausted search budget. Rejection counts distinguish completed joints, exposed
frontiers, stock remnants and bounded lookahead. Boundary diagnostics include
involved stone IDs where known. Configuration failures have `retry_possible=False`.

### Coursing preference uses actual geometry

`WallAnalysis.alignment_after()` separately measures connected skyline extension,
adjoining completed joints, disconnected exposed tops at the same elevation, and
remote completed joints. A circular plateau counts each column/stone once.
The generator uses one pre-placement surface/joint snapshot for all candidates.

The alignment signal combines connected extent (normalised by the midpoint of
ordinary width limits), a smaller adjoining-stone count influence, and remote
same-elevation extent normalised by wall width. The exact modest formula lives
in `_style_weight()`; its directional weight is:

`exp((2*coursing_factor - 1) * alignment_signal)`

Zero discourages unnecessary alignment, 0.5 is neutral, and one encourages it.
Weights stay positive. Necessary bonding priorities and hard validity precede
style; no perfectly coursed or irregular outcome is guaranteed.

### Determinism and limitations

Each ashlar instance owns its seeded RNG. Fresh instances with identical inputs
and action sequences are repeatable. Undo removes a stone but does not rewind the
RNG, so re-placement can differ. Projection and analysis never consume that RNG.
The algorithm is greedy and bounded: no backtracking, alternate-valley rescue,
exhaustive feasibility proof or automatic relaxation occurs after failure.

## Descriptive analysis

`analysis/grid.py` supplies validated occupancy projection and maximal circular
runs. `analysis/joints.py` measures completed joints. A vertical run continues
while both sides are occupied by different IDs, even when those IDs change with
height. Empty cells or the same stone on both sides interrupt it. Stack count is
the maximum number of distinct IDs seen on either side, not the joint's height.
At x=0, periodic analysis compares last/first columns exactly once.

Horizontal runs likewise require distinct occupied stones above/below. A
periodic run may extend beyond x=width in its record rather than becoming two
records. Small immutable records live alongside the other models.
`analysis/wall.py` adds live local queries, exposed edges, dimension/aspect-ratio
distributions, joint statistics and selected-stone inspection. These are
descriptive queries without placement policy or persistent caches. Current local
geometry and an event's original placement context are intentionally distinct.

## Visual geometry is downstream

`geometry/projection.py` maps a logical horizontal distance onto a clockwise XZ
cross-section; Y is up. Rounded-square vertices are scaled so the actual faceted
perimeter equals wall width at every rounding/resolution. Stones split at each
face/perimeter boundary and fold as one mesh/ID, with outward triangle winding.
Incompatible modulo coverage is rejected, never hidden by clipping.

Depth zero emits surfaces. Optional outward depth adds closed individual shells,
without internal caps at folds or a duplicate closing cap for a full ring.
The optional core/tube is separate geometry; its tube uses a similar scaled inner
section so tiny fillets cannot invert. Buffers live in `geometry/mesh.py`.
There is no boolean union or core fusion; individual stone shells can be
validated and exported as STL as described below.

## Shape and 3D stages

`processing/models.py` separates `WallDescription`, `ShapeSettings`,
`ShapeStatistics` and applied `ShapedWall`/`ShapedStone` contours. The result keeps
one settings object, source ID/order, the original description and deterministic
diagnostics. The original `(source, joint_width, stones)` result constructor and
`joint_width` accessor remain supported. Boundaries use counter-clockwise,
floating-point, unwrapped coordinates. The logical `Stone` and occupancy model
and all generator algorithms are unchanged.

`processing/topology.py` indexes source corners by row and column, then inserts
every corner incident to each boundary, on both axes. Periodic vertex identity
is `(x modulo width, y)`, with a period offset retained on each occurrence.
Consequently a corner near x=0 can split an edge crossing the far end without
splitting the stone identity. Finite descriptions do not merge their ends.
Movement allowance is a quarter of the thinnest incident stone dimension.
The workbench caches this immutable sparse topology by wall revision; changing
Shape settings does not rebuild it. No unit-by-unit edge densification is used.

`processing/field.py` evaluates seeded smooth value noise at each unique source
junction once, using a stateless integer hash and two displacement channels. Its
horizontal lattice wraps exactly for periodic walls; the approximate requested
variation scale adjusts to a whole number of cells around the circumference.
Local allowance times Distortion bounds vector length. Vertical movement tapers
to zero at y=0 and y=wall height. Coordinates are quantized to 1e-7 grid units
for clipping consistency and returned as fractional floats. Every occurrence
gets its exact period translation. Generation RNG state is never consulted.

`processing/validation.py` checks positive area, nonzero/nonfolding boundaries,
self-intersection and positive-area overlap. An X sweep and relative-period pair
keys cull repeated or distant overlap checks, including each stone's periodic
copies. Shared coincident edges are permitted before mortar. Pyclipper performs
polygon intersections at fixed precision; failed proposals are rejected rather
than repaired, scaled back or committed partially.

`processing/inset.py` offsets each distorted contour inward by half the joint
width, with a fixed mitre limit. It requires one nonempty, hole-free result and
checks containment in the original distorted polygon. Microscopic redundant
offset vertices are cleaned within 2e-7 units. Consumed or split stones are
explicit errors. The final arrangement is validated again. `shape_wall()` in
`processing/shape.py` orchestrates the pipeline; at Distortion zero it bypasses
all of this and retains the original rectangle-inset arithmetic exactly.
Pyclipper is lazy-loaded only for distorted processing, not for core imports,
generation, or zero-distortion shape applications.

`processing/contours.py` supplies ear triangulation and vertical clipping for
simple polygons. Ear selection favours well-conditioned triangles and checks the
final pair, avoiding microscopic triangles at almost-collinear T-junctions while
retaining the boundary vertices. `WallGeometry` accepts either a live logical
`Wall` or a `ShapedWall`. Contour triangles split at projection facet/period cuts;
only the original boundary gets extrusion sides. A distorted full ring may have
an X bounding span greater than one circumference, so shaped spans are not
rejected by the old rectangle-width restriction. Opposite periodic edges join
without caps. Projection cuts affect meshes, never Shape's stored contours. Scored corner
pieces use an area-scaled tolerance so tiny valid pieces do not leave holes. Sloping side
quads use a deterministic diagonal based on the source edge, so reversed/shared
edges of zero-mortar neighbours produce coincident triangulated side surfaces.

STL conversion can collapse sub-float32-resolution edges at scoring intersections.
Only faces whose stored vertices become identical are omitted; the complete
remaining shell must still pass oriented edge-incidence and positive-volume
checks. Collinear noncollapsed faces and open/nonmanifold results remain errors.
No boolean union or general Blender modifier behaviour is implied.

## Workbench composition

`app/session.py` owns the incremental generator, placement history, inspection
and terminal state under an RLock. Reset commits only after configuration
validation. `app/workbench.py` extends that session with explicit applied stages:
wall/Shape/build revisions, source configuration, independent logs and retained
results. Accepted placements, undo, reset and restored specimens advance the wall revision.
An unchanged Apply/Build reuses the existing result/revision. Failures append to
the corresponding stage log while retaining the previous successful output.

Shape may consume any nonempty accepted wall prefix. Build requires Shape's
source wall revision to be current. Wall changes invalidate Shape and 3D;
applying a changed Shape invalidates 3D. Draft parameters do not invalidate an
applied result until an operation succeeds. Previous results remain inspectable
with explicit stale notices and their own source description, dimensions and IDs.

`app/server.py` is the stdlib HTTP/resource adapter. POST `/api/shape` applies
`joint_width`, `distortion`, `seed` and `variation_scale`; POST `/api/build` applies the 3D configuration. GET `/api/state`
returns source and stage metadata; GET `/api/geometry` reads the stored mesh and
its inherited Shape snapshot without building anything. Shape/build requests may
include `source_revision` for their expected Wall/Shape revision; a mismatch is
rejected before processing. Mutation responses are captured under the session
lock. Mesh snapshots carry build, Shape and inherited Wall revisions so the
browser can reject mismatched or late responses. Mesh buffers are fetched
when a build revision changes or its cached buffers are missing. Generation endpoints still use
the original shared incremental path. `app/__main__.py` is the local launcher.
The core package never imports the optional app.

`analysis/report.py` is the common measurement path for `diagnostics.run_case`
and `WorkbenchSession.wall_report()`. It classifies actual stock dimensions,
measures occupancy, sneck count/area/aspect, deliberate choices and vertical
joint runs, aggregates available rejection evidence, and reports configured
size/sneck/joint violations independently of completion. Failed accepted prefixes
remain valid diagnostic outcomes. Reports include shared colour roles and an
English summary. Workbench caches by source revision and terminal outcome;
playback and processing parameters do not recalculate the report.
Gallery examples include standalone `.wall.json` attachments with geometry,
recipe, outcome and RNG state; original placement evidence is omitted explicitly.
The gallery uses the same colour roles as the viewer. Batch metadata fingerprints
generator and analysis code separately.

`records.py` stores isolated `WallRecord` snapshots with exact source geometry,
resolved generator recipe, available events, terminal state and standard-library
random state expressed as JSON arrays (no pickle or executable input). Loading
checks finite JSON data, integer coordinates, model placement/overlap rules,
recipe validity, completion consistency and event/geometry correspondence before
committing. Old stock outside today's policy is reported, not rewritten. Absent
placement evidence receives explicitly marked placeholders. Original measured
analysis is exported for inspection; imports recompute measurements from geometry.
There is no file-format version or migration layer. Input limits are 32 MiB and
four million occupancy cells.

History entries begin with the first attempted placement, including preflight
failure. The active entry remains live; snapshots are copied only when saving or
departing, avoiding per-placement copies of the entire specimen. Repeated Generate
updates one entry. Reset archives the old entry without adding an empty one.
Selecting/importing commits a fresh Wall revision and restores the generator/RNG
without replaying generation. Partial continuation is reproducible with the same
algorithm and saved RNG; future generator changes may produce a different continuation.
History is server-session memory shared by its browser clients. Downstream
settings/results remain session-global and become stale on source replacement.
POST `/api/save` returns JSON with an attachment filename and optional `revision`
guard. POST `/api/load` takes `record`; `/api/history` takes `record_id`. Both may
include expected `source_revision`. Mutation/state responses remain atomic.

`exporting.py` provides clean SVG and validated binary STL without app imports.
SVG keeps stone groups/IDs, flips logical Y for the document, and wraps/clips
periodic walls to one reference circumference. Physical dimensions use mm/unit.
STL is scaled to millimetres, welds numeric seam noise, and validates oriented
closed edges, nondegenerate triangles and positive volume at float32 precision.
It includes every stone shell and the optional solid/tube core in the same STL,
validating the core independently. Contact surfaces remain separate; no boolean
union, core fusion or inter-shell intersection solver is implied. POST `/api/export` is read-only and
checks stage source currency and the requested applied revision; its binary
attachment headers do not encode STL as text. Playback prefixes, draft controls
and overlays never enter exports.

`app/static/startup.js` constructs `WorkbenchApp`. `app.js` coordinates accepted
snapshots, shared selection and the active inspection stage. `stages.js` owns
header navigation, Shape/3D drafts, Live toggles, prerequisite/export gating and
action feedback. One unchecked Advanced checkbox in the Parameters heading
appends the active stage's advanced fields directly into the normal form flow,
without a separate disclosure or full-width subsection; hiding them preserves
draft values.
Shape uses it for its independent Seed and Variation scale.
`parameters.js` retains generation drafts and explicit Apply & reset.
`library.js` owns header Load/Save/history controls and JSON file selection.
Successful restoration explicitly restores Wall form values, leaves downstream
drafts intact, and invokes the existing stage-refresh coordinator. Invalid loads
preserve active geometry, history and drafts. State responses carry lightweight
history labels rather than every saved wall. Save and SVG/STL share attachment
download handling but remain distinct source and geometry exports.
`viewer2d.js` draws rectangles or applied contours, with independent Wall/Shape
navigation and periodic display clipping. Fits include actual contour extents;
live changes retain user pan/zoom when the source dimensions are unchanged. `projection.js` displays stored meshes
and lazy-loads the Three.js adapter. `pipeline.js` ensures current results on
downstream tab entry: Shape first, then 3D, against one captured Wall revision.
It reuses matching current snapshots, coalesces duplicate visits, stops at failed
processing and cancels the remainder of a chain if its source changes. Empty
walls do no processing; accepted partial and stopped prefixes are valid sources.
`live.js` coalesces
parameter edits after a short debounce and serializes downstream requests. Live
is on by default for Shape/3D; it only acts on user edits/toggle changes with
valid existing sources. Disabling Live or switching stages cancels queued work;
an already running operation completes safely. Parameter inputs remain usable
during live processing, and only the latest pending edit is retained. Exports
and playback wait until pending live updates finish. With Live off, Apply/Build
commits drafts explicitly. Automatic tab-entry refresh remains enabled with Live
off, using applied settings or first-use defaults. Valid live drafts may be used
on entry; invalid drafts use applied settings instead. Draft fields are preserved
by automatic refresh, and stale retained previews are labelled in the viewer.
Wall has no live generation path.
`details.js` shows stage-local Events/Info, including inherited source data;
occupancy/joint analytics are offered only in Wall. `diagnostics.js` guards stale
responses and never interprets processed contours as logical occupancy.

Playback in all stages only reveals accepted placements in inherited source
order; it never completes generation, applies drafts or builds geometry. A stale
preview replays its own stored source, even if the live wall now differs. SVG
visibility and existing Three.js object visibility change in place. Switching
stages restores full visibility. Generate/Place one continue the applied generator settings and
explicitly report when drafts were ignored or no new stones were generated.
The bar separates apply/reset and placement actions on the left, feedback in the
middle, and replay/export actions on the right, with internal vertical dividers.
Busy actions disable conflicting controls and show an accessible activity/status
line, with reduced-motion support. Stage switches cancel playback without
changing source data. Failed operations retain previews and provide an error.

Run the Python suite for generation, source provenance, inset and polygon-shell
checks, plus the optional Node browser-component tests. Exercise SVG/WebGL
navigation and stage transitions in a real browser. No testing/build tool is a
runtime dependency. The `_junk` tree remains reference material, not live code.
