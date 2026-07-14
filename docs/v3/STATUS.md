# openRetop V3 migration status

## Current task

Task 76 - Extract Remaining Workflow Controllers

Implementation status: complete. All Task 76 implementation and focused
verification checks pass. Complete-suite certification remains blocked by the
same workstation interpreter split recorded for Task 75; details are in
Verification below. Task 77 was not started.

## Completed work

- Added UI-agnostic `SceneController`, `SelectionController`,
  `VisibilityController`, `TransformController`, `SectionController`,
  non-manual `CurveController`, `RegionController`, `SurfaceController`,
  `BrepController`, and `AnalysisController`.
- Moved authoritative transform and region workflow/session state into the
  application layer. Existing `app` state modules now re-export the application
  types so legacy imports and MainWindow compatibility properties continue to
  work without independent shadow state.
- Added shared controller support for callback undo payloads, state snapshots,
  selection snapshots, scene IDs, model-sync requests, and feature dependency
  planning/pruning. Controllers return Task 75 `CommandResult` values and
  publish typed scene, selection, status, and dirty events without owning the
  global undo stack.
- Preserved dependency invalidation for section planes/results, source curves,
  preview surfaces, editable lofts, four-boundary features, BREP records, mesh
  replacement/deletion, source edits, and direct scene deletion. Undo/redo
  snapshots include affected dependent records, selection, and BREP runtime
  objects where applicable.
- Kept the accelerated shared `MeshQueryService` as the only projection query
  cache. Transform, region, curve, and surface controllers receive explicit
  mesh/query inputs or the existing shared service; no brute-force projection
  path or second cache was introduced.
- Refactored MainWindow workflow methods into compatibility adapters that read
  Tk values or resolve screen-space input, call a controller, apply structured
  status/dirty/undo/selection/viewport/UI requests, and refresh widgets. Public
  names used by menus and tests remain available.
- Moved surface patch validation and general BREP/editable-loft build policy out
  of MainWindow. Removed the superseded surface validation, BREP build, delete,
  and undo helper chains. MainWindow changed from the Task 75 baseline of
  14,703 physical lines and 547 methods to 12,578 physical lines and 519
  methods.
- Registered all current non-file-dialog actions in the central registry: 141
  unique action definitions now cover scene, selection, visibility, transform,
  section, curve, manual-curve, region, surface/BREP, and analysis workflows.
  MainWindow binds these definitions through one dispatcher and uses their
  centralized conditions for menu/button state, including manual session phase,
  selected control-point state, paused Add Point flow, and region-boundary
  availability.
- Kept Task 74 manual-curve controller/session ownership and Task 73 accelerated
  projection behavior intact. No modeling feature, geometry algorithm,
  project-format field, serializer version, CAD dependency, or actor-construction
  path was added or rewritten.
- Added headless controller coverage for success/failure, validation atomicity,
  undo/redo payloads, dirty flags, typed events, selection changes, missing and
  duplicate dependencies, transformed analysis bounds, source edits, direct
  deletion, and dependent-feature invalidation. Architecture tests assert that
  the controllers do not import Tk, MainWindow, dialogs, or VTK actor APIs.

## Documented exception

The specialized region-to-planar-BREP adapter still obtains the current
transformed mesh, manages its progress UI, and composes the existing region
plane-fit/reprojection functions in MainWindow. `BrepController` owns adoption
of the resulting record/runtime object, rebuild state, dependency invalidation,
events, dirty state, and undo payload. This narrow exception avoids moving
viewport/presentation access into the application controller and avoids
rewriting the established region geometry path. General planar-face, loft,
editable-loft, export-to-an-explicit-path, rebuild, source-edit, display, and
delete workflows are controller-owned.

## Files created

Application state and controller support:

- `src/application/state.py`
- `src/application/controller_support.py`
- `src/application/scene_ids.py`
- `src/application/feature_dependencies.py`
- `src/application/transform_math.py`
- `src/application/region_session.py`

Controllers:

- `src/application/scene_controller.py`
- `src/application/selection_controller.py`
- `src/application/visibility_controller.py`
- `src/application/transform_controller.py`
- `src/application/section_controller.py`
- `src/application/curve_controller.py`
- `src/application/region_controller.py`
- `src/application/surface_controller.py`
- `src/application/brep_controller.py`
- `src/application/analysis_controller.py`

Tests:

- `tests/test_scene_controllers.py`
- `tests/test_transform_controller.py`
- `tests/test_section_controller.py`
- `tests/test_curve_controller.py`
- `tests/test_region_controller.py`
- `tests/test_surface_brep_controllers.py`
- `tests/test_analysis_controller.py`

## Files modified

- `src/app/app_state.py`
- `src/app/main_window.py`
- `src/app/object_state.py`
- `src/app/scene_browser.py`
- `src/app/transform_state.py`
- `src/app/transforms.py`
- `src/application/__init__.py`
- `src/application/actions.py`
- `tests/test_application_core.py`
- `tests/test_architecture.py`
- `docs/v3/STATUS.md`

No files were moved or removed.

## Verification

Passing checks:

- Blender Python 3.11 with `PYTHONPATH=src;.venv/Lib/site-packages`:
  `python -m compileall -q src` - passed.
- Focused Task 75/76 application, architecture, and controller suites - 78
  tests passed.
- `python scripts/report_architecture_metrics.py --largest 5 --fail-on-new` -
  passed with the six existing presentation allowlist entries, zero new
  dependency violations, zero package cycles, and zero module cycles.
- Central registry audit - all 141 IDs are unique; all handlers resolve and
  non-payload handler signatures bind.
- `git diff --check` - passed.

Complete-suite result and environment blocker:

- The exact required `python -m compileall -q src` and full unittest commands
  were attempted. The workspace `python` launcher points to a removed Python
  3.11 installation and exits before execution.
- Blender's bundled Python 3.11 plus the checked-in site-packages supplies
  NumPy, VTK, CadQuery/OCP, and the other modeling dependencies. Full discovery
  ran 419 tests: 414 completed successfully and five errored only because that
  interpreter has no `tkinter`.
- The affected imports are `test_curve_surface_prep`,
  `test_embedded_viewport_scene`, `test_main_window_ui`, the MainWindow
  compatibility case in `test_manual_curve_controller`, and
  `test_scene_browser_labels`.
- The available system Python has Tk but lacks the scientific/CAD dependency
  stack. No available interpreter has both sets of requirements. No test was
  skipped, weakened, deleted, or rewritten to hide this blocker, and the full
  run reported no behavioral assertion failures.

## Compatibility and risks

- `.openretop` version, serializer/deserializer, field names, permissive future
  metadata, and reconstruction defaults are unchanged. Existing project files
  continue through the same load/save code paths.
- Existing public MainWindow method names and legacy `app` state import paths
  are retained as forwarding compatibility boundaries until Task 81.
- Controller undo payloads restore coherent deep state snapshots. Code holding
  private references to replaced collection instances across undo/redo would be
  stale; supported callers access collections through `AppState`, and the
  MainWindow/controllers do so.
- BREP CAD runtime objects remain process-local infrastructure state. They are
  restored by in-memory undo payloads where available but are still rebuilt
  after project load, matching prior persistence semantics.
- The region-plane exception above remains coupled to transformed mesh access
  in MainWindow and should be revisited only when Task 77 supplies declarative
  scene/viewport inputs; moving it prematurely risks changing established
  geometry behavior.
- Complete Tk integration certification is an environment risk, not a known
  product assertion failure, but remains unverified until the external runner
  uses the supported application environment.

## Known remaining issues

- The Task 75 framing regressions remain intentionally unchanged: Frame All is
  mesh-centric, several Frame Selected categories are approximate, and project
  load may frame before restored transforms/derived geometry are complete.
- VTK scene synchronization, actor caching, picking, camera fitting, and
  declarative scene snapshots remain concentrated in viewport/MainWindow code.
  These are Task 77 responsibilities.
- Project/settings/import/export orchestration remains primarily in MainWindow
  by design for Task 78. BREP export is split correctly: MainWindow chooses a
  path, while the controller validates and performs export through its backend.
- MainWindow is materially smaller and controller-oriented but is still a large
  compatibility adapter pending Tasks 77-81.
- There are still no checked-in representative real-world `.openretop` fixture
  files for end-to-end backward-compatibility loading.

## Acceptance assessment

All ten required controllers exist and are UI-agnostic. They use explicit
state, Task 75 results/events, controller-owned workflow snapshots, and the
shared query service. MainWindow is materially smaller and delegates the listed
workflows; current non-file-dialog actions are centrally registered; dependency
invalidation, selection, dirty state, and undo payload behavior have headless
coverage. Task 74 manual curves, Task 73 projection, project schema, CAD stack,
and actor ownership were preserved.

Every implementation acceptance criterion is satisfied, including the
documented region-plane presentation exception. The requirement to certify the
complete unittest suite as passing cannot be satisfied on this workstation due
to the incompatible runtime split above. Therefore not every acceptance
criterion can be reported as fully verified until the external runner completes
the suite in an environment containing both Tk and the scientific/CAD stack.

## Exact next-task starting point

Start Task 77 - Viewport, Scene Snapshot, Picking, Camera, and Framing Rework.
Begin from the controller-owned `AppState` and structured viewport requests
created by Tasks 75-76: define stable toolkit-neutral scene snapshot/render-item
types and a UI-independent scene builder, then split VTK synchronization,
actors, picking, style conversion, and camera fitting behind the existing
`EmbeddedVTKViewport` compatibility facade. Add the Task 77 scene/camera tests
before correcting Frame All, Frame Selected, transformed/restored project
framing, and unnecessary actor rebuilds. Do not begin Task 78 project/settings
work as part of that task.
