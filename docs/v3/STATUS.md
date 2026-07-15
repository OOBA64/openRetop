# openRetop V3 migration status

## Current task

Task 77 - Viewport, Scene Snapshot, Picking, Camera, and Framing Rework

Implementation status: complete, with the complete-suite acceptance check
blocked by existing MainWindow compatibility failures described under
Verification. Task 78 was not started.

## Completed work

- Added immutable, toolkit-neutral scene-description contracts for
  `SceneSnapshot`, mesh/curve/surface/region/section render items,
  `ToolPreviewState`, `SelectionRenderState`, `DisplayStyleSnapshot`, and
  declarative `CameraRequest` values. Geometry uses stable object IDs and
  deterministic revisions; style, visibility, and transforms are tracked
  independently.
- Added a UI-independent `SceneBuilder` that reads controller-owned `AppState`
  and prepared surface/manual geometry. It emits visible and hidden persistent
  items, scene-node/group selection keys, display options, world-space bounds,
  and camera requests without importing Tk or VTK.
- Changed the real MainWindow viewport path to build and submit one
  `SceneSnapshot`. The old `set_scene(...)` argument facade remains available
  for older adapters/tests until Task 81.
- Split viewport infrastructure into focused host, scene synchronization,
  actor cache/factory, mesh, curve, surface, region, section, tool-preview,
  picking, camera, style-conversion, and low-level VTK conversion modules.
  Actor construction and mutation remain in `viewer` presentation modules.
- Added stable-ID incremental synchronization. New actors are created on
  appearance; geometry changes only on geometry-revision changes; transform,
  style, and visibility changes are separate; disappeared actors are removed;
  unchanged actors and polydata are reused. `ActorUpdateDiagnostics` exposes
  created, geometry/style/transform/visibility updated, removed, and reused
  counts. Compatibility actor groups are invalidated only for the affected
  geometry family.
- Added structured pick results and services for mesh triangles, scene objects,
  manual control points, curve segments, and loft overbuild handles. Existing
  integer/string compatibility hit-test methods remain. Tool callbacks still
  consume only their established left-button interactions; VTK camera orbit,
  pan, and wheel navigation paths were not changed.
- Added a tested camera controller with finite framing math, safe degenerate and
  flat bounds, finite orthogonal camera vectors, clipping-range repair,
  frame-all/frame-selected/frame-bounds/reset requests, and named front/back/
  left/right/top/bottom/isometric orthographic views.
- Frame All now uses the union of visible world-space scene geometry instead of
  mesh-only metrics. It includes transformed mesh, curves, regions, section
  geometry, manual/tool previews, preview surfaces, and BREP visual previews;
  the world origin is not included merely because an origin marker exists.
- Frame Selected continues to resolve object and group selection, now includes
  generated preview/BREP vertices and overbuild handles, and uses selected mesh
  bounds when other visible categories exist instead of framing the entire
  scene.
- Model/project loading now performs its final camera request after restored
  transforms, records, and actors have synchronized. Model-less projects frame
  restored curve geometry when present. Ordinary refresh emits no camera
  request and preserves position/focal point.
- Corrected the manual first-control-point presentation to use the existing
  dedicated first-point color constant; no curve geometry or modeling behavior
  changed.
- Preserved the `.openretop` schema and all existing project restoration code,
  the shared accelerated `MeshQueryService`, public VTK/CadQuery/OCP stack, and
  existing MainWindow/viewport compatibility entry points.

## Files created

Viewport scene and synchronization:

- `src/viewer/scene_types.py`
- `src/viewer/scene_builder.py`
- `src/viewer/scene_synchronizer.py`
- `src/viewer/actor_cache.py`
- `src/viewer/actor_factories.py`

Focused VTK infrastructure:

- `src/viewer/host_adapter.py`
- `src/viewer/camera_controller.py`
- `src/viewer/picking_service.py`
- `src/viewer/style_conversion.py`
- `src/viewer/vtk_actor_utils.py`
- `src/viewer/mesh_actors.py`
- `src/viewer/curve_actors.py`
- `src/viewer/surface_actors.py`
- `src/viewer/region_actors.py`
- `src/viewer/section_actors.py`
- `src/viewer/tool_preview_actors.py`

Tests:

- `tests/test_task77_viewport.py`

## Files modified

- `src/app/main_window.py`
- `src/viewer/__init__.py`
- `src/viewer/embedded_viewport.py`
- `docs/v3/STATUS.md`

No files were moved or removed.

## Verification

Passing checks:

- `python -m compileall -q src` - passed.
- `tests.test_task77_viewport` - 11 tests passed. Coverage includes scene
  building/revisions, transformed and category bounds, degenerate camera math,
  clipping/named views, structured picking, headless public-VTK actor sync,
  no-unnecessary-rebuild behavior, independent transform/style/visibility
  updates, camera-after-actor ordering, and ordinary-refresh camera
  preservation.
- Full existing `tests.test_embedded_viewport_scene` plus focused project-load,
  transformed-surface, curve/source/region framing, model selection, and mesh
  deletion integration cases - 73 tests passed with the Task 77 suite included.
- `tests.test_architecture` plus Task 77 tests - 23 tests passed; six existing
  presentation allowlist imports, zero new dependency violations, zero package
  cycles, and zero module cycles.
- `git diff --check` - passed.

Required complete-suite result:

- Command: `PYTHONPATH=src python -m unittest discover -s tests -v`.
- Result: 649 tests ran; 617 passed, 31 failed, and 1 errored.
- All Task 77 tests and all `test_embedded_viewport_scene` tests passed. The 32
  non-passing cases are in the pre-existing `test_main_window_ui` compatibility
  suite. They cover Task 74-76 workflow/status/selection expectations such as
  manual-curve default snap state, controller status wording, scene-browser
  refresh after a direct private restore helper, visibility undo labels, and
  surface/section command labels. The lone error is
  `test_manual_curve_project_restore_upgrades_legacy_manual_curve`, where the
  test calls `_restore_project_curve_collection` directly and then expects a
  scene-browser node that the helper does not refresh.
- These failures reproduce individually and are outside Task 77 rendering,
  picking, camera, framing, project-format, or actor synchronization. They were
  not skipped, weakened, deleted, or rewritten because doing so would violate
  the numbered-task scope and test rules.

## Compatibility and risks

- Project format/version, serializers, metadata fields, and permissive legacy
  manual-curve upgrade paths are unchanged. Existing `.openretop` files still
  enter through the same project loader and restoration helpers.
- MainWindow uses snapshots with the real viewport, while non-snapshot
  third-party/fake adapters use the retained `set_scene` facade. This temporary
  dual path is intentional through Task 81.
- The compatibility facade still delegates final presentation to the
  established grouped overlay builders to preserve exact visuals. The new
  per-object actor factories and synchronizer are public-VTK-only and fully
  tested, while compatibility group invalidation is family-level for curves,
  surfaces, and manual previews. Task 81 can remove the legacy argument facade
  after all external callers migrate.
- Deterministic revisions hash prepared NumPy geometry. This prioritizes correct
  invalidation and no stale actors; very large future non-mesh preview arrays
  may warrant controller-owned monotonic revisions, but current preview sizes
  are bounded and mesh geometry is reused.
- Named views now enable parallel projection. This is an intentional
  presentation change required by Task 77; modeling coordinates and stored
  geometry are unaffected.

## Known remaining issues

- Complete-suite certification remains blocked by the 32 existing MainWindow
  compatibility failures above. No Task 77-specific failure is known.
- `EmbeddedVTKViewport.set_scene(...)` remains a large compatibility method and
  the established overlay actor builders remain in that module. Removal of the
  facade is explicitly deferred until Task 81.
- Project/settings/import/export orchestration remains primarily in MainWindow;
  that is Task 78 scope and was not changed here.
- There are still no representative real-world `.openretop` fixtures checked
  into the repository for end-to-end compatibility certification.

## Acceptance assessment

The Task 77 implementation criteria are satisfied: rendering consumes
`SceneSnapshot`; VTK operations live in viewport presentation modules;
structured picking exists; camera commands and post-restore framing operate on
world-space visible geometry; ordinary refresh preserves the camera; and actor
updates are revision-driven and diagnostic.

The mandatory complete-suite criterion is not satisfied because the repository
currently has 31 failing and 1 erroring pre-existing MainWindow compatibility
tests. Therefore not every acceptance criterion can be reported as satisfied.
This is recorded as a blocker rather than bypassed with out-of-scope workflow
changes or test modifications.

## Exact next-task starting point

Before starting Task 78, reconcile the existing MainWindow compatibility-suite
baseline (31 failures and one direct-private-helper scene-browser error) with
the Task 74-76 controller behavior, or obtain an external-runner baseline that
establishes those failures as expected. Once the required full suite is green,
start Task 78 at project/settings/import/export orchestration. Do not remove the
Task 77 `EmbeddedVTKViewport.set_scene(...)` compatibility facade before Task
81.
