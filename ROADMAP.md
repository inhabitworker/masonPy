# Future work

This is a parking place for ideas discussed during development, not a release
schedule. The current implementation is described in [README.md](README.md) and
[DOC.md](DOC.md). Choose and scope a feature before implementing it.
Advanced 3D deformation, face relief and multi-segment edge treatments remain
deferred. Proportional 2D softening, depth variation and a single 3D exposed-edge
chamfer are implemented.

## Foundation to preserve

- **Wall → Shape → 3D** remains the dependency chain. Integer occupancy is the
  source of truth; downstream contours and meshes inherit its description and
  stone IDs without rewriting generation.
- Wall generation stays explicit and bounded. Shape/3D can update existing data
  through Live or explicit Apply/Build. Navigation inspects or refreshes an
  existing source; playback only changes visibility.
- Periodic adjacency includes the first/last columns and whole stones crossing
  that seam. Shared junctions and deterministic fields must remain continuous.
- Add vertices when an operation needs them: incident source corners, projection
  scores, a requested fillet or surface detail. Avoid uniform dense geometry in
  anticipation of unrelated later features.
- Invalid processing proposals fail atomically and retain the previous result.
  Keep dependencies small and dedicated; profile before adding a numerical stack
  or native acceleration beyond the existing Pyclipper dependency.

## Shape procedures and corner treatments

- [ ] Explore further rubble/hand-dressed stone treatments behind the existing
  inherited-contour contract. Start with one reliable procedure before adding a
  procedure selector or general layer stack.
- [x] Add optional proportional 2D corner softening after mortar, using bounded
  convex-corner interpolation. Preserve unsoftened profiles, shrink/skip unsafe
  treatments without dropping stones, and support SVG/3D/STL downstream.
- [ ] Consider further corner fillets, chamfers or controlled chipping in 2D. Define how
  these interact with shared boundaries and mortar inset, especially at
  T-junctions, thin snecks and the periodic seam. Inset remains an offset operation.
- [ ] Add local contour subdivision only where a requested treatment needs it.
  Preserve simple outlines, source identity and overlap validation; establish
  vertex/tolerance budgets before exposing more detail controls.
- [ ] Add non-destructive omission of small stones by an explicitly defined
  area/short-span threshold. Preserve source stones, occupancy and IDs; record
  omitted IDs in the derived result and have downstream geometry/exports respect
  the mask. Consider omission before inset so intentionally omitted thin stones
  cannot fail the mortar pass. This differs from today's display-only Hide snecks.
  Decide whether a void exposes a recessed mortar surface, backing, or open air;
  removing a stone alone does not generate mortar. Keep source analysis distinct
  from counts/coverage of the visible derived result.
- [ ] Explore cracks in two separately scoped forms: shallow grooves confined
  to the exposed face, and true splits producing separate closed fragments.
  Begin true splits with 2D cut paths through contours before extrusion rather
  than arbitrary 3D booleans. Retain a parent stone ID and deterministic fragment
  IDs for selection, playback, evidence and exports. Define crack width and
  matching fracture surfaces; do not alter source generation occupancy.

Shared periodic noise, incident-corner subdivision, fractional distortion and
mortar inset are already implemented. This section concerns extensions to that
method, not a second implementation of those features.

## 3D mapping and surface relief

The next appearance step is bounded face sampling and coarse-to-fine noise
relief. Architectural height profiles remain useful as separately scoped work.

- [x] Add per-stone depth variation around the existing extrusion depth, keeping
  the rear mounting surface fixed. Start with Base depth, relative Variation and
  a separate advanced 3D Seed; zero variation must preserve current geometry.
  Derive one bounded value from seed and logical stone ID, independent of wall
  generation RNG, iteration order and mapping cuts. All front/cap/side/outline
  geometry must use the same stone depth; periodic copies must agree. Positive
  depth remains positive, and depth zero retains surface-only behaviour. This
  adds no triangles and should precede dense surface treatments.
- [x] Add a bounded single-band exposed-edge chamfer with geometric/float32 shell
  validation, reduced/unbeveled fallbacks, explicit diagnostics and work limits.
- [ ] Extend the generic finish with sufficient conforming face subdivision and bounded noise/function displacement
  on the exposed face only. Keep the rear fixed, preserve controlled edge
  transitions, and distinguish geometry subdivision from smoothing/shading.
  Start with broad, slightly directional broken relief and smaller roughness;
  avoid excessive whole-stone smoothing that rounds away angular masonry forms.
  Compare the results with masonry references before developing specialized
  dressing procedures. Shading-only detail does not appear in STL.
- [ ] Defer random Boolean chips/nicks as a separate optional damage treatment.
  Assign seeded low-poly cutters to individual stones or query nearby stones
  through spatial bounds; avoid all-stones-by-all-cutters testing or joining the
  wall into one solid. Evaluate cutting coarse geometry before dense face detail,
  and preserve IDs, closed shells, minimum thickness and periodic cutter copies.
  Benchmark intersection/retriangulation, output complexity and robust validation;
  general 3D Boolean machinery is a candidate for the Blender adapter.
  Compare cheaper methods first: front-face height-field dents for shallow pits,
  locally variable bevels or 2D contour notches for edge loss, and capped plane
  clips for isolated flat corner chips. Plane clipping on arbitrary concave or
  mapped stones still needs robust cap construction; none of these methods
  universally replaces undercutting Boolean geometry.

- [ ] Explore mapping profiles that vary with height: inflate/deflate or follow
  a defined cross-section function. Add scores where the mapping requires them
  while preserving source perimeter coordinates, periodic closure and clean
  polygon extrusion.
- [ ] Start profile deformation with an analytic shared field: bottom scale,
  top scale and signed middle bulge/hollow, with positive scale throughout.
  Apply it consistently to stones, core, outlines and bounds, and introduce
  conforming horizontal scores at profile changes or by an approximation-error
  tolerance. Reference circumference stays attached to the source; actual
  circumference varies with height. A whole-assembly warp also scales depth,
  mortar and tube thickness locally. Constant physical depth or true normal
  extrusion is a separate later policy, not an implicit promise of cage-like
  deformation. A general bound mesh cage/shrinkwrap target is not needed for
  these first profiles.
- [ ] Prototype shallow, seeded stone-face relief from noise or a displacement
  map. Decide amplitude units, periodicity, face/edge treatment and required
  local subdivisions before implementation. Measure generation time, mesh size,
  browser responsiveness and STL validity on representative walls.
- [ ] Keep expensive detail as intentional processing, with progress feedback
  and explicit vertex/triangle limits. Prefer local/adaptive detail to globally
  subdividing every stone. Benchmark whether any native helper is justified.
- [ ] Develop an exposed-face finish beginning with rock/pitch-faced masonry:
  bounded broad projections and broken facets with controlled edge dressing,
  followed by smaller seeded roughness. Distinguish split-faced, pitched and
  weathered/rounded treatments rather than treating all stone as smooth noise.
  Use per-stone seed variation and a separate face-detail seed; maintain periodic
  consistency for each wrap-crossing stone. Keep the rear surface free of relief
  and define an edge transition, minimum remaining thickness and side-wall joins.
  A height field cannot represent undercuts or fully model fractured rock.
- [ ] Add a conforming, indexed intermediate stone mesh or equivalent parametric
  sampling structure before topological operations. Retain source coordinates
  and front/rear/side/arris roles; today's triangle buffers alone do not provide
  these semantics. Share cut vertices, handle mapping seams and avoid T-junction
  cracks. Cache tessellation independently from seed/amplitude edits where valid.
- [ ] Separate three controls/concepts: 2D silhouette corner treatment in Shape,
  3D exposed arris bevels, and sampling density for displacement/deformation.
  The single chamfer/front transition ring is implemented; consider several
  fillet bands next if justified. Concave contours and narrow necks can invalidate offset
  rings. Full Catmull-Clark subdivision is not required to soften stone edges.
- [ ] Defer general remeshing/decimation to Blender unless measurements justify
  it here. Whole-wall remeshing can merge stones, close mortar and erase IDs;
  per-stone processing still needs boundary/thickness preservation. Prefer
  purpose-built faceted relief to depending on simplification artifacts.

Flat/perimeter mapping, mapping-dependent vertical scoring, polygon extrusion,
rounded-square/cylindrical cross-sections and solid/tube cores already exist.
Core and stone shells already export together; boolean union is optional future
work, not required for the current disjoint-shell STL convention.

## Generation and diagnostics

- [ ] Turn useful real-world failures and JSON specimens into focused regression
  cases. Keep qualitative multi-seed coverage across ordinary sizes, refined
  grids, thin closers, strict bonding and incompatible stock.
- [ ] Investigate bounded alternative placements or limited backtracking only
  when diagnostics show a worthwhile improvement. Distinguish proven stock
  incompatibility, local dead ends and search-budget exhaustion; never silently
  relax stock or joint rules to claim completion.
- [ ] Consider additional masonry procedures or intentional openings/voids as
  separately scoped work. Openings need an explicit occupancy/support model
  rather than treating their empty cells as unfinished construction.
- [ ] Profile large grids and shaped walls. Extend revision-aware caches and
  spatial indexing where measurement identifies a bottleneck.

These are face-layout diagnostics, not structural masonry calculations.

## Blender and longer-term workflow

- [x] Extract shared recipe validation/defaults from the browser app, move shell
  checks into geometry, and reserve Blender adapter source. See
  [the adapter boundary](blender/README.md) for topology and dependency constraints.
- [x] Add a thin Blender adapter over the independent Python core: Add Masonry,
  saved recipes, explicit regeneration, mapped 2D or extruded output, connected
  stone islands, semantic face attributes/groups and optional separate backing.
  Package a self-contained Blender 5.1/macOS Apple Silicon ZIP with Pyclipper.
- [ ] Add Blender modifier integration using preserved stone IDs and face roles.
  Consider native bevels, subdivision and displacement before duplicating a full
  modifier system in the browser.
- [ ] Consider complete project snapshots, including generated geometry and
  placement evidence, once a concrete workflow needs them. Current config JSON
  stores Wall/Shape/3D parameters; exact
  geometry, placement evidence and continuation history remain session-only. Add format migration
  only when evolving saved data actually requires it.
- [ ] Evaluate optional fused-mesh/export repair workflows against actual slicer
  and printing needs. Keep separate closed-shell export available.
