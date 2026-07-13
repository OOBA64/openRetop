---

## Task 73: Accelerated Mesh Query Engine and Performance Verification

Purpose:
Task 72 introduced manual-curve projection, Keep Curve On Mesh behavior, mesh-conforming loft previews, future deviation-analysis contracts, and additional surface workflows.

The current nearest-mesh projection implementation performs a Python loop over every mesh triangle for every query point. This is not viable for realistic scan meshes and will prevent future curve fitting, surface fitting, deviation analysis, and primitive recognition from performing acceptably.

Replace the brute-force nearest-surface implementation with a reusable, cached, accelerated mesh spatial-query engine.

This is a foundation and stabilization task.

Do not add primitives.
Do not add surface trimming or intersection.
Do not add new surfacing tools.
Do not redesign the UI.
Do not perform the full Tasks 78–80 refactor.
Do not change normal user workflows unless required to fix correctness or responsiveness.
Do not rewrite the viewport.
Do not introduce duplicate mesh-state systems.

Use the VTK stack already required by the application. Prefer `vtkStaticCellLocator` for immutable loaded scan meshes, with `vtkCellLocator` only if there is a concrete compatibility reason.

---

## Part A — Establish a correctness baseline

Before replacing the current projection implementation:

1. Preserve the existing brute-force closest-point behavior as a test-only reference implementation.
2. Add correctness tests comparing the accelerated implementation against the reference on small known meshes.
3. Cover:

   * point above triangle interior
   * point nearest triangle edge
   * point nearest triangle vertex
   * multiple disconnected triangles
   * degenerate/invalid triangles
   * empty mesh
   * finite and non-finite query points
   * maximum-distance rejection
   * normal calculation
   * source triangle index reporting

The brute-force implementation must not remain in the normal runtime path after this task.

Acceptance:

* accelerated and reference results agree within a defined tolerance
* expected triangle IDs agree
* expected distances agree
* invalid inputs fail safely
* tests exist before runtime replacement

---

## Part B — Create a reusable spatial index

Create:

src/mesh/spatial_index.py

Add dataclass:

MeshClosestPointResult

Fields:

* source_points: np.ndarray
* closest_points: np.ndarray
* distances: np.ndarray
* hit_mask: np.ndarray
* triangle_indices: np.ndarray
* normals: np.ndarray
* queried_point_count: int
* hit_count: int
* missed_count: int
* build_time_seconds: float
* query_time_seconds: float
* backend: str
* metadata: dict[str, object]

Add class:

MeshSpatialIndex

Responsibilities:

* accept a validated `TriangleMeshData`
* convert the mesh once to VTK polydata
* build a `vtkStaticCellLocator`
* retain the source mesh identity/revision information
* answer repeated closest-point queries without rebuilding the locator
* return closest surface point, triangle ID, distance, and triangle normal
* support one query point or a batch of query points
* support an optional maximum search distance
* preserve or reject missed source points according to caller preference
* never scan all mesh triangles in Python

Suggested public API:

MeshSpatialIndex.from_mesh(mesh)

MeshSpatialIndex.query_closest_points(
points,
*,
max_distance: float | None = None,
preserve_missed_points: bool = True,
) -> MeshClosestPointResult

Properties:

* triangle_count
* vertex_count
* build_time_seconds
* valid
* source_signature

Rules:

* locator construction may perform preprocessing once
* query execution may loop over query points if required by VTK
* query execution must not loop over all triangles
* return NumPy arrays with stable shapes and dtypes
* invalid triangles must be excluded during index construction
* output triangle indices must map back to original `TriangleMeshData.triangles`
* normal calculation must use the matched source triangle
* no NaN/inf output
* duplicate query points must work
* empty query sets must work

Acceptance:

* one spatial index can serve repeated queries
* no per-query mesh rebuild
* no Python triangle scan
* original source triangle indices are preserved

---

## Part C — Add a cached mesh-query service

Create:

src/mesh/query_service.py

Add class:

MeshQueryService

Responsibilities:

* lazily build and cache a `MeshSpatialIndex`
* return the cached index for the current source mesh
* invalidate the index when source mesh geometry changes
* avoid invalidation for display-only changes such as color, opacity, or selection
* expose cache/build diagnostics
* centralize mesh-query ownership instead of building locators independently in multiple tools

Suggested API:

get_index(mesh, *, mesh_revision=None) -> MeshSpatialIndex

invalidate()

query_closest_points(
mesh,
points,
*,
mesh_revision=None,
max_distance=None,
preserve_missed_points=True,
) -> MeshClosestPointResult

Diagnostics:

* cache_hit
* index_build_count
* last_build_time
* last_query_time
* triangle_count
* queried_point_count
* backend

Rules:

* do not hash every vertex/triangle on every request
* use stable mesh identity plus an explicit revision or replacement event
* document coordinate-space assumptions
* curve points and mesh geometry must be queried in the same coordinate system
* if mesh transforms are applied outside source geometry, preserve the current projection semantics exactly

Acceptance:

* repeated curve/surface queries reuse one index
* loading or replacing a mesh invalidates the index
* visual preference changes do not invalidate it
* cache behavior is testable

---

## Part D — Replace curve projection internals

Update:

src/curves/projection.py

Keep the public contracts compatible where practical:

* `CurveProjectionResult`
* `project_curve_points_to_mesh`
* `project_stored_curve_to_mesh`

Replace the brute-force internals with the spatial query service/index.

Requirements:

* preserve projected points
* preserve triangle indices
* preserve normals
* preserve distance calculations
* preserve maximum-distance behavior
* preserve missed-point behavior
* preserve existing metadata names where possible

Improve warning behavior:

* do not create thousands of individual warning strings for large batches
* retain detailed warnings for small requests
* aggregate large failures, for example:

  * "238 of 4096 points exceeded the projection threshold."
* store failed indices separately when useful

Remove the old runtime `_closest_mesh_point` triangle loop after correctness tests are established.

Acceptance:

* existing callers continue working
* projection output remains compatible
* large projection requests no longer scale linearly with every mesh triangle
* existing project and curve metadata remain readable

---

## Part E — Route all scan-conforming tools through the service

Audit every current nearest-mesh or projection path.

At minimum, update:

1. Manual curve projection
2. Keep Curve On Mesh fitted-curve projection
3. Project Selected Curve to Mesh
4. Mesh-Conforming Loft Preview
5. Any region-boundary projection using the same nearest-surface logic
6. Future deviation-analysis computation helpers added in this task

Do not create separate spatial locators for each feature.

Mesh-Conforming Loft Preview:

* build the loft grid as it does currently
* send the full point batch through MeshQueryService
* reuse the cached locator
* preserve projection threshold behavior
* preserve projection mean/max diagnostics
* preserve failed projection count
* preserve smooth shaded display
* preserve non-BREP labeling

Acceptance:

* all nearest-surface tools use the same query engine
* locator is not rebuilt for each curve or surface
* mesh-conforming loft performance is suitable for interactive use on realistic scans

---

## Part F — Add foundational deviation computation

Extend:

src/analysis/deviation.py

The existing dataclasses may remain, but add a computation function using the new mesh query service:

compute_point_deviation_to_mesh(
source_points,
mesh_or_index,
*,
max_distance: float | None = None,
signed: bool = False,
) -> DeviationResult

Requirements:

* no viewport/UI heatmap yet
* no continuous real-time mode yet
* use accelerated nearest-surface queries
* calculate:

  * mean absolute distance
  * maximum absolute distance
  * RMS distance
  * failed sample count
* optionally calculate signed distance only when a reliable normal/sign convention is available
* if signed distance is not reliable, leave it `None` rather than inventing a sign
* include query/build timing and backend information in metadata

Purpose:
This establishes the real computational foundation for the later color-coded deviation tool without adding that UI yet.

Acceptance:

* deviation computation uses the spatial index
* results are numerically tested
* no duplicated closest-point code exists in the analysis module

---

## Part G — Add performance instrumentation

Add timing diagnostics around:

* index construction
* batch query
* curve projection
* mesh-conforming loft projection

Do not print timing information continuously to stdout.

Store timing in result metadata and expose it through existing diagnostics/status systems where appropriate.

Add:

benchmarks/benchmark_mesh_queries.py

The benchmark should:

* generate or load a representative triangulated mesh
* query several point counts
* report:

  * triangle count
  * query point count
  * index build time
  * first query time
  * repeated cached query time
  * hit/miss count
* optionally compare against brute force only on a small mesh
* never run the brute-force reference on a production-sized benchmark

Suggested benchmark cases:

* 10,000 triangles / 100 points
* 100,000 triangles / 1,000 points
* larger case when memory permits

Do not add fragile microsecond-level timing assertions to normal CI.

Acceptance:

* benchmark can be run directly
* cached queries are visibly faster than rebuilding
* performance characteristics are measurable

---

## Part H — Add meaningful automated tests

Add tests for:

Spatial index:

* correct closest points
* correct triangle IDs
* correct distances
* correct normals
* empty mesh
* invalid triangles
* empty point batch
* maximum-distance rejection
* duplicate points
* missed-point preservation

Cache:

* first query builds one index
* repeated query reuses it
* mesh replacement invalidates it
* display setting change does not invalidate it

Projection:

* existing `CurveProjectionResult` behavior remains compatible
* projected stored curves retain lineage
* large batches produce aggregated warnings
* no brute-force runtime triangle loop is called

Mesh-conforming loft:

* uses MeshQueryService
* reuses cached locator
* retains projection diagnostics
* remains non-BREP
* remains wireframe-off by default

Deviation:

* mean/max/RMS are correct
* failed samples are counted
* timing/backend metadata exists

Performance structure:

* patch or instrument locator construction to prove it is built once
* patch the old brute-force helper to prove production code does not call it
* avoid unreliable strict wall-clock assertions in CI

Regression:

* manual curve tests pass
* Task 72 tests pass
* region selection tests pass
* surface preview tests pass
* BREP tests pass
* project IO tests pass
* settings tests pass
* app imports and launches

---

## Part I — Add continuous integration

The repository currently lacks automated commit checks.

Add a GitHub Actions workflow appropriate to the existing project:

.github/workflows/tests.yml

Requirements:

* run on push and pull request
* use the project’s supported Python version
* install project requirements
* run the complete test suite
* use a Linux virtual display for Tk/VTK tests if required
* cache pip downloads where straightforward
* fail on test failures
* do not silently skip the core geometry tests

If full GUI tests cannot run reliably in CI:

* run all headless geometry/state/project tests
* clearly separate GUI-dependent tests
* document the local command for the complete suite

Acceptance:

* future commits receive an automated pass/fail result
* geometry-query tests run in CI
* no dependency on proprietary software

---

## Part J — Limited cleanup only

While replacing the projection engine:

Remove or consolidate only code directly made redundant by this task:

* brute-force runtime nearest-triangle loops
* duplicate closest-point result conversions
* duplicate warning generation
* duplicate mesh-query preparation
* unused imports/helpers caused by the replacement

Do not start the full application refactor here.
Do not broadly move UI panels.
Do not rewrite MainWindow.
Do not rename unrelated systems.
Do not combine this with primitive recognition or trim tools.

It is acceptable to give MainWindow one `MeshQueryService` instance and pass it into projection/surface commands.

Acceptance:

* one authoritative nearest-surface implementation
* no duplicated production projection engines
* unrelated behavior remains unchanged

---

## Final acceptance

Task 73 is complete when:

* closest-point projection no longer loops through every triangle in Python
* a cached VTK spatial locator is used
* curve projection uses the locator
* Keep Curve On Mesh uses the locator
* mesh-conforming loft uses the locator
* deviation computation uses the locator
* repeated queries reuse the same index
* mesh replacement invalidates the index
* correctness matches the reference implementation
* benchmarks demonstrate the new scaling behavior
* Task 72 behavior remains intact
* the complete test suite passes
* CI is added and passes
* app launches
* no primitives, trimming, or new surfacing features were added

## Stop after this task.
