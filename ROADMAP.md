# Future work

This is a parking place for ideas discussed during development, not a release
schedule. The current implementation is described in [README.md](README.md) and
[DOC.md](DOC.md). Choose and scope a feature before implementing it.

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
- [ ] Consider corner fillets, chamfers or controlled chipping in 2D. Define how
  these interact with shared boundaries and mortar inset, especially at
  T-junctions, thin snecks and the periodic seam. Inset remains an offset operation.
- [ ] Add local contour subdivision only where a requested treatment needs it.
  Preserve simple outlines, source identity and overlap validation; establish
  vertex/tolerance budgets before exposing more detail controls.

Shared periodic noise, incident-corner subdivision, fractional distortion and
mortar inset are already implemented. This section concerns extensions to that
method, not a second implementation of those features.

## 3D mapping and surface relief

- [ ] Explore mapping profiles that vary with height: inflate/deflate or follow
  a defined cross-section function. Add scores where the mapping requires them
  while preserving wall circumference/closure and clean polygon extrusion.
- [ ] Prototype shallow, seeded stone-face relief from noise or a displacement
  map. Decide amplitude units, periodicity, face/edge treatment and required
  local subdivisions before implementation. Measure generation time, mesh size,
  browser responsiveness and STL validity on representative walls.
- [ ] Keep expensive detail as intentional processing, with progress feedback
  and explicit vertex/triangle limits. Prefer local/adaptive detail to globally
  subdividing every stone. Benchmark whether any native helper is justified.

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

- [ ] Design a thin Blender adapter over the independent Python core. Preserve
  stone IDs, source settings and stage boundaries. Where appropriate, translate
  depth, bevels, subdivision and displacement into Blender modifiers instead of
  duplicating a full modifier system in the browser.
- [ ] Consider saving complete workbench projects, including Shape/3D settings,
  once a concrete workflow needs it. Current JSON saves exact source specimens;
  history and processing settings remain session-global. Add format migration
  only when evolving saved data actually requires it.
- [ ] Evaluate optional fused-mesh/export repair workflows against actual slicer
  and printing needs. Keep separate closed-shell export available.
