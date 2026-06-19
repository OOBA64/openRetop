---

## Task 68: Surface-Ready Curve Preparation — Project, Rebuild, Validate

Purpose:
Region boundaries and manual curves now exist, but they are not yet reliable enough as surface inputs. Before adding real surface fitting, the app needs tools to project curves onto the mesh, rebuild/simplify them into cleaner control geometry, and validate whether selected curves are suitable for fill/loft/surface workflows.

This task is the bridge between:

* manual curves
* region boundary curves
* projected guide curves
* future surface patch generation

Do not add BREP/STEP/IGES export.
Do not integrate pboyer/verb yet.
Do not add full NURBS surfaces yet.
Do not add automatic face recognition.
Do not rewrite Region Select.
Do not rewrite Manual Curve Edit.
Do not replace existing Fill Closed Curve / Loft Between Two Curves.
Do not add new dependencies.

Current expected foundation:

* Manual curves are editable.
* Manual curve preview works.
* Snap to Mesh exists.
* Region Select exists.
* Region boundaries can be extracted into editable StoredCurves.
* Curves can already be selected, repaired, simplified, smoothed, filled, and lofted.
* Surface preview currently supports single closed curve fill and two-curve loft only.

Goal:
The user should be able to:

1. Select a manual curve, region boundary curve, or section curve.
2. Project it onto the mesh.
3. Rebuild it into cleaner control geometry.
4. Validate whether it is surface-ready.
5. Use the cleaned/projected curve for Fill Closed Curve or Loft Between Two Curves.
6. Preserve all source metadata so future surface tools know where the curve came from.

---

## Part A — Add curve projection backend

Create a focused module:

src/curves/projection.py

Purpose:
Project existing curves onto the loaded scan mesh without modifying the original curve.

Required dataclasses:

1. CurveProjectionResult
   Fields:

* projected_points: np.ndarray shape (N, 3)
* source_points: np.ndarray shape (N, 3)
* hit_mask: np.ndarray bool shape (N,)
* distances: np.ndarray shape (N,)
* triangle_indices: list[int | None]
* normals: list[list[float] | None]
* projected_count: int
* missed_count: int
* max_distance: float
* mean_distance: float
* warnings: list[str]

Required functions:

2. project_curve_points_to_mesh(
   points,
   mesh,
   *,
   max_search_distance=None,
   preserve_missed_points=True,
   ) -> CurveProjectionResult

Behavior:

* For each input point, find nearest point on mesh surface.
* Prefer VTK cell locator / closest point behavior if already available through VTK.
* If VTK closest-point APIs are not convenient, add a small focused nearest-triangle helper, but do not brute-force millions of triangles in Python for every interaction.
* Projection runs as an explicit command, not continuously every mouse move.
* If a point cannot be projected:

  * if preserve_missed_points=True, keep original point
  * mark hit_mask False
  * record warning
* Return projected_points with same count/order as source_points.
* Never return NaN/inf.
* Do not mutate source curve.
* Do not mutate mesh.

3. project_stored_curve_to_mesh(
   curve,
   mesh,
   *,
   curve_id,
   name,
   source_mesh_name,
   max_search_distance=None,
   ) -> StoredCurve

Behavior:

* Use curve.fitted_points or control_points as source points.
* Prefer editable control_points if available.
* Project points to mesh.
* Return a new StoredCurve.
* Metadata:

  * creation_type: "projected_curve"
  * source_curve_id
  * source_curve_name
  * source_curve_creation_type if available
  * source_mesh_name
  * projection_projected_count
  * projection_missed_count
  * projection_mean_distance
  * projection_max_distance
  * projection_warnings
  * control_points = projected points
  * curve_method copied from source or "catmull_rom"
  * sample_count copied from source
  * snap_to_mesh = True
  * snap_mode = "mesh"
* Preserve closed/open state.
* Keep projected curve editable through Manual Curve Edit mode.

Acceptance:

* Projection backend handles empty curves safely.
* Projection backend handles missing mesh safely.
* Projection result preserves point order.
* Projected curve stores useful metadata.
* Projected curve is a normal StoredCurve.

---

## Part B — Add Project Selected Curve to Mesh command

Add command:

Project Selected Curve to Mesh

Available in:

* Curves workbench
* Manual RE workbench if a curve is selected
* scene browser curve context menu, if low-risk

Behavior:

* Requires loaded mesh.
* Requires exactly one selected or active curve.
* Rejects no curve with:
  "Select one curve to project."
* Rejects no mesh with:
  "Load a mesh before projecting curves."
* Creates a new curve.
* Does not overwrite the source curve.
* Selects the new projected curve.
* Active curve = new projected curve.
* Adds it to CurveCollection.
* Refreshes viewport.
* Refreshes scene browser.
* Pushes undo command:
  "Project Curve to Mesh"
* Marks project dirty.

Naming:

* Projected Curve 1
* Projected Curve 2
  or:
* <source name> Projected

Use whichever is already easier, but avoid duplicate names.

Scene browser grouping:
Curves
Projected Curves
[V] Projected Curve 1 (projected)

Grouping priority:

1. Projected Curves
2. Region Boundaries
3. Manual Curves
4. Repaired/Processed Curves
5. Section Result groups
6. Unassigned

Acceptance:

* User can project selected curve onto mesh.
* Original curve remains unchanged.
* Projected curve appears under Projected Curves.
* Undo removes projected curve.
* Redo restores projected curve.
* Projected curve can be edited.

---

## Part C — Add curve rebuild backend

Create or extend focused curve utilities:

src/curves/rebuild.py

Purpose:
Reduce dense curves into cleaner control geometry for surface workflows.

Required dataclass:

CurveRebuildResult

* control_points: np.ndarray
* fitted_points: np.ndarray
* source_point_count: int
* target_control_point_count: int
* method: str
* is_closed: bool
* warnings: list[str]

Required functions:

1. rebuild_curve_by_arc_length(
   points,
   *,
   target_control_point_count,
   is_closed,
   curve_method="catmull_rom",
   sample_count=128,
   ) -> CurveRebuildResult

Behavior:

* Input can be dense polyline or fitted curve.
* Resample source points by arc length to target control point count.
* For closed curves, distribute points around loop without duplicating first point.
* For open curves, preserve first and last points.
* Rebuild fitted curve using existing manual_curve.sample_manual_curve().
* Clamp target_control_point_count:

  * open min 2
  * closed min 3
  * max 256
* Do not mutate original curve.
* Never return NaN/inf.

2. rebuild_stored_curve(
   curve,
   *,
   curve_id,
   name,
   target_control_point_count,
   curve_method,
   sample_count,
   ) -> StoredCurve

Metadata:

* creation_type: "rebuilt_curve"
* source_curve_id
* source_curve_name
* source_curve_creation_type if available
* rebuild_source_point_count
* rebuild_target_control_point_count
* rebuild_method
* control_points
* curve_method
* sample_count
* closed
* source metadata should be preserved under a clear prefix or copied where useful

Acceptance:

* Dense boundary curves can be reduced to fewer control points.
* Open curves preserve endpoints.
* Closed curves stay closed.
* Rebuilt curves remain editable.

---

## Part D — Add Rebuild Selected Curve command

Add command:

Rebuild Selected Curve

Available in:

* Curves workbench
* Manual RE workbench if curve selected
* scene browser curve context menu, if low-risk

UI controls:

* Target Control Points
* Curve Type:

  * Smooth Curve
  * Polyline
* Sample Count

Suggested defaults:

* Target Control Points: 16
* Curve Type: Smooth Curve
* Sample Count: 128

Behavior:

* Requires exactly one selected/active curve.
* Creates a new curve by default.
* Does not overwrite source curve.
* Selects new rebuilt curve.
* Pushes undo command:
  "Rebuild Curve"
* Marks project dirty.

Naming:

* Rebuilt Curve 1
  or:
* <source name> Rebuilt

Scene browser grouping:
Curves
Rebuilt Curves
[V] Rebuilt Curve 1 (rebuilt)

Grouping priority:

1. Projected Curves
2. Rebuilt Curves
3. Region Boundaries
4. Manual Curves
5. Repaired/Processed Curves
6. Section Result groups
7. Unassigned

Acceptance:

* User can reduce a high-density boundary to a smaller editable smooth curve.
* Original curve remains unchanged.
* Rebuilt curve can be edited and used in fill/loft.
* Undo/redo works.

---

## Part E — Add surface-readiness validation

Create module:

src/curves/validation.py

Purpose:
Report whether selected curves are suitable for fill/loft/surface preview.

Required dataclass:

CurveSurfaceReadiness

* curve_id: str
* curve_name: str
* point_count: int
* control_point_count: int | None
* is_closed: bool
* is_manual_like: bool
* is_projected: bool
* is_region_boundary: bool
* bounding_box_size: float
* perimeter_or_length: float
* endpoint_gap: float
* planarity_error: float | None
* mesh_projection_mean_distance: float | None
* mesh_projection_max_distance: float | None
* warnings: list[str]
* errors: list[str]

Required functions:

1. validate_curve_for_fill(curve) -> CurveSurfaceReadiness

Checks:

* must be closed
* must have at least 3 usable points
* must not be degenerate
* should report planarity error
* should warn if point count is extremely high
* should warn if endpoint gap is nonzero but within tolerance

2. validate_curves_for_loft(curves) -> list[CurveSurfaceReadiness]

Checks:

* exactly two curves preferred
* both must have at least 2 points
* warn if one closed and one open
* warn if point counts differ greatly
* warn if bounding boxes differ extremely
* warn if source metadata suggests different source regions/meshes

3. estimate_curve_planarity_error(points) -> float

Behavior:

* compute best-fit plane
* return max distance from points to plane
* handle invalid/degenerate curves safely

Do not prevent operations unless truly invalid.
Surface preview commands may still run with warnings.

Acceptance:

* Validation module can diagnose curve issues.
* Does not crash on empty/invalid curves.
* Does not mutate curves.

---

## Part F — Add Curve Surface Readiness UI

Curves workbench should display diagnostics for active/selected curve:

* Type
* Source
* Point count
* Control point count
* Closed
* Endpoint gap
* Length/perimeter
* Planarity error
* Projection mean distance, if metadata exists
* Projection max distance, if metadata exists
* Surface readiness:

  * Ready for Fill
  * Ready for Loft
  * Warnings
  * Errors

Add buttons:

* Validate Selected Curve
* Validate Selected Curves for Loft

Behavior:

* If one curve selected:

  * show fill readiness
* If two curves selected:

  * show loft readiness
* If no curve:

  * status "Select curve(s) to validate."

Do not clutter the viewport.
Keep diagnostics in sidebar/Analysis panel.

Acceptance:

* User can tell why a curve fails fill/loft.
* User can tell whether a dense boundary should be rebuilt.
* Diagnostics update after projection/rebuild/edit.

---

## Part G — Improve Fill/Loft preflight messages

Before Fill Closed Curve:

* run validate_curve_for_fill()
* if hard errors:

  * do not create surface
  * show first hard error in status
* if warnings:

  * allow creation but store warnings in surface metadata

Before Loft Between Two Curves:

* run validate_curves_for_loft()
* if hard errors:

  * do not create surface
  * show first hard error in status
* if warnings:

  * allow creation but store warnings in surface metadata

Surface metadata:

* source_curve_validation_warnings
* source_curve_validation_errors
* source_curve_planarity_error if available
* source_curve_projection_distance if available

Do not rewrite existing surface preview algorithms in this task.

Acceptance:

* Fill/loft failures are more explainable.
* Surface context can show validation warnings.
* Existing valid fill/loft still works.

---

## Part H — Projected/Rebuilt curve metadata preservation

Every derived curve must clearly track lineage.

Projected curve metadata must include:

* creation_type = "projected_curve"
* source_curve_id
* source_curve_name
* source_curve_creation_type
* source_mesh_name
* projection stats
* control_points
* curve_method
* sample_count

Rebuilt curve metadata must include:

* creation_type = "rebuilt_curve"
* source_curve_id
* source_curve_name
* source_curve_creation_type
* rebuild_source_point_count
* rebuild_target_control_point_count
* rebuild_method
* control_points
* curve_method
* sample_count

If rebuilt from a projected curve:

* preserve source_mesh_name
* preserve projection stats under original keys or copied keys

If projected from a region boundary:

* preserve source_region_id
* preserve source_region_name
* preserve source_region_triangle_count

Acceptance:

* User can inspect curve origin.
* Future surface patch tools know curve lineage.
* Project save/load preserves metadata.

---

## Part I — Scene browser labels

Add labels:

Projected Curves:

* [V] Projected Curve 1 (projected)
* [V] Projected Curve 2 (projected, mesh)

Rebuilt Curves:

* [V] Rebuilt Curve 1 (rebuilt)
* [V] Rebuilt Curve 2 (rebuilt, smooth)

Boundary curves remain:

* [V] Region Boundary 1 (boundary, closed)

Do not show more than two tags.

Priority for tags:

1. projected
2. rebuilt
3. boundary
4. mesh
5. manual
6. smooth/polyline
7. closed/open
8. tiny

Acceptance:

* Derived curves are easy to find.
* User can distinguish projected/rebuilt/boundary/manual curves.

---

## Part J — Tests

Add/update tests for:

Projection backend:

* project empty curve returns safe result
* project curve to simple mesh returns same point count
* projected curve metadata contains projection stats
* missed points are preserved when enabled
* invalid mesh handled safely
* closed state preserved

Projection UI:

* Project Selected Curve to Mesh requires mesh
* Project Selected Curve to Mesh requires one curve
* command creates new StoredCurve
* original curve unchanged
* projected curve selected
* undo removes projected curve
* redo restores projected curve

Rebuild backend:

* rebuild open curve preserves endpoints
* rebuild closed curve remains closed
* rebuild dense curve reduces control point count
* target count clamps safely
* no NaN/inf output
* metadata includes source curve info

Rebuild UI:

* Rebuild Selected Curve requires one curve
* command creates new StoredCurve
* original curve unchanged
* rebuilt curve selected
* undo/redo works

Validation:

* fill validation rejects open curve
* fill validation accepts closed non-degenerate curve
* validation reports planarity error
* validation warns on very high point count
* loft validation warns on one-open/one-closed pair
* loft validation reports point-count mismatch
* invalid/empty curves do not crash

Fill/loft preflight:

* Fill Closed Curve reports validation error clearly
* Fill Closed Curve stores validation warnings
* Loft Between Two Curves stores validation warnings
* existing valid fill/loft still creates preview

Scene browser:

* Projected Curves group appears
* Rebuilt Curves group appears
* labels include projected/rebuilt tags
* visibility/delete/select works

Regression:

* manual curve creation/edit still works
* region select still works
* region boundary extraction still works
* surface fill/loft still works
* project save/load preserves projected/rebuilt metadata

Acceptance:

* pytest passes
* app launches
* mesh loading works
* user can project a curve to mesh
* user can rebuild a dense curve into fewer control points
* user can validate curve surface readiness
* fill/loft status messages become clearer
* no surface fitting yet
* no BREP/NURBS integration yet

## Stop after this task.
