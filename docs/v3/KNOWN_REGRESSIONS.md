# openRetop V3 known regressions

## Scope

This Task 75 baseline records known behavior; it does not implement the camera
rewrite. The framing fix belongs to Task 77, **Viewport, Scene Snapshot,
Picking, Camera, and Framing Rework**. The observations below come from the
current call paths and tests. They are intended to prevent an architectural move
from accidentally declaring the existing behavior correct.

## FRAMING-001: Frame All is mesh-centric rather than scene-centric

### Current behavior

`OpenRetopWindow.frame_all()` dispatches the representative action and produces
a `frame_all` viewport request. The compatibility adapter handles that request
by calling `EmbeddedVTKViewport.frame_model()`, which is only an alias for
`reset_view()`.

`reset_view()` does not inspect the renderer's current visible actors. It uses
cached `_view_center` and `_view_extent` values. `_update_view_metrics()` updates
those values only from the mesh and its transform/source bounds. Consequently:

- visible section results, curves, surface previews, BREP representations,
  regions, and manual/tool geometry do not contribute to Frame All bounds;
- a visible curve or surface outside the mesh bounds can be clipped or remain
  off-screen after Frame All;
- if the mesh is hidden or absent, `_update_view_metrics()` clears mesh-local
  bookkeeping but leaves the previous/default view center and extent in place;
  Frame All can therefore use stale bounds from an earlier scene;
- scene visibility is not the framing authority: hidden mesh-derived metrics may
  continue to determine the camera while visible non-mesh geometry is ignored;
  and
- the fixed minimum extent of `1.0` gives small/degenerate geometry potentially
  excessive padding.

This is why the command can report `View framed` even when the visible scene was
not fitted.

### Architectural cause

The action contract is now UI-agnostic, but its compatibility handler still
targets a viewport method whose framing data is private mesh cache state. There
is no declarative scene snapshot or authoritative visible-world-bounds query in
Task 75.

## FRAMING-002: Frame Selected is only partially category-correct

### Current behavior

The MainWindow adapter expands scene-browser group selection and assembles point
sets in `_bounds_for_node_ids()`. A selected ordinary curve has a useful
characterization test: `test_frame_selected_curve_uses_curve_bounds` verifies
that its fitted-point minimum and maximum are sent to `frame_bounds()`.

That working slice does not generalize to every category:

- selecting the mesh deliberately converts the request back to Frame All, so it
  inherits FRAMING-001 rather than sending the already available transformed
  mesh bounds;
- selected BREP bounds are approximated from source-curve points, not from the
  rebuilt/tessellated CAD actor actually shown;
- surface bounds depend on rebuilding a preview at command time; unavailable
  previews contribute no bounds;
- region framing handles the active region and falls back to Frame All when
  region bounds cannot be produced, again inheriting the mesh-centric behavior;
- section-plane framing creates a synthetic box using mesh extent and
  `origin +/- half_extent`, rather than deriving actor-equivalent oriented plane
  bounds;
- curve/section/surface coordinate assumptions are distributed through
  MainWindow rather than normalized as world-space render-item bounds; and
- an unavailable selected object's geometry yields a status message but no
  camera change, while some region paths frame the mesh instead.

Even when valid bounds reach the viewport, `frame_bounds()` uses a fixed
isometric-like camera direction and a distance based only on the largest AABB
dimension. It does not fit against viewport aspect ratio and camera field of
view, and it clamps every extent to at least `1.0`. It resets the clipping range
afterward but has no separately tested policy for a point, line, extremely thin
bounds, or pathological scale.

### Test gap

Existing UI tests verify that a curve supplies exact bounds and that mesh
selection calls `frame_model()`. Existing headless viewport tests cover named
view direction and actor preservation, but there is no complete matrix proving
Frame Selected camera fit for transformed mesh, section group, region, preview
surface, BREP, degenerate bounds, and different viewport aspect ratios.

## FRAMING-003: project load frames before restored state is complete

### Current load sequence

For a mesh-backed project, `open_project()` currently performs these operations:

1. Decode the project and resolve `mesh_path`.
2. Call `load_model()`. That constructs the mesh at its initial/default
   transform and calls `_refresh_viewport(reset_camera=True)`, positioning the
   camera from those mesh bounds.
3. Apply the saved location, rotation, scale, and origin with
   `_restore_project_transform(... reset_camera=False)`.
4. Restore mesh visibility, planes/results, curves, surfaces, BREP records, and
   editable surface features.
5. Call `_refresh_viewport(reset_camera=False)` and return.

The final refresh updates actors/cache metrics but intentionally preserves the
camera produced in step 2. A project whose mesh was translated, rotated, or
scaled after import can therefore reopen with the camera aimed at the
pre-restore location. Restored visible geometry outside the initial mesh bounds
is never included in that initial fit.

For a project with `mesh_path: null`, `open_project()` restores project controls
and records and returns without issuing a deterministic post-restore frame
request. Such a file can contain curves or surface descriptors, but there is no
authoritative camera fit after their restoration.

The project format intentionally stores no camera, so correct post-restore
framing is required application behavior rather than a serialization concern.

### Reproduction characterizations for Task 77

The following cases should be captured as automated tests before changing the
camera implementation:

1. Save a project with a mesh translated far from its import position, reopen
   it, and assert that the camera focal point/fit uses the restored transformed
   bounds rather than the identity-load bounds.
2. Save a project with non-default rotation and scale plus visible curves or a
   visible surface preview extending beyond the mesh; assert the final fit
   contains all intended visible geometry.
3. Reopen a project whose mesh is hidden but whose generated geometry is
   visible; assert hidden mesh bounds do not control Frame All.
4. Reopen a meshless version 1 project containing visible restorable geometry;
   assert the scene is synchronized before a finite framing decision is made.
5. Verify that the ordinary refresh immediately after load does not perform a
   second accidental reset once the explicit post-restore camera request has
   completed.

## Task 77 expected behavior

Task 77 owns the implementation and tests. Its camera/scene architecture should
meet these observable outcomes:

### Frame All

- Compute one finite world-space union of the geometry that is currently
  eligible and visible in the scene snapshot.
- Include transformed mesh, visible curves/section results, regions, surface
  previews, and rebuilt/renderable BREP geometry according to an explicit,
  tested category policy.
- Exclude hidden objects and non-model decorations such as grid, world axes,
  view gizmos, origin/transform handles, and overlay labels. The world origin
  must not enter the bounds unless actual framed geometry warrants it.
- If no frameable geometry exists, leave the camera finite and deterministic
  and report/return a no-geometry result rather than reusing stale scene bounds.

### Frame Selected

- Resolve the selected object or expanded group to the same world-space bounds
  used by rendering, after all object transforms.
- Fit only that selection, not unrelated mesh/global bounds. A selected mesh
  must not be a special alias for Frame All.
- Use actual preview/BREP/region bounds when those are the rendered
  representation; do not approximate a BREP solely from source curves when
  actor geometry exists.
- Treat empty, missing, non-finite, point-like, line-like, and planar selections
  explicitly. An unavailable selection should not unexpectedly reframe an
  unrelated object.

### Camera controller

- Centralize bounds validation, padding, projection/aspect-aware fit, finite
  camera-vector fallbacks, and clipping-range updates in a tested camera
  controller rather than distributing category math through MainWindow.
- Support frame-bounds/all/selected, reset, and named orthographic/isometric
  views without mutating scene geometry.
- Produce finite camera position, focal point, view-up, scale/distance, and
  clipping values for degenerate and very large/small bounds.
- Preserve the user's camera during ordinary scene refresh. A camera changes
  only in response to an explicit camera request or the documented initial-load
  policy.

### Model and project opening

- Build/synchronize the renderable scene first, then issue the initial frame
  request against the actors/snapshot that actually exist.
- For project open, restore records, transforms, visibility, and rebuildable
  representations before determining visible bounds.
- Frame exactly once at the intentional end of that operation; later ordinary
  refreshes must preserve the result.

## Required verification boundary

Task 77 should add behavior-focused tests at three levels:

- pure camera math for finite/degenerate bounds, padding, aspect ratio, and
  clipping;
- scene-builder/actor synchronization tests proving visible and transformed
  category bounds; and
- headless VTK/application integration tests for Frame All, each selected
  category/group, model open, project open, and camera preservation on ordinary
  refresh.

Task 75 intentionally leaves `EmbeddedVTKViewport.frame_model()`,
`frame_bounds()`, project-load ordering, and the broad viewport argument surface
unchanged. Their presence after Task 75 is a documented migration boundary, not
acceptance of the regression.
