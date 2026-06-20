---

## Task 71: Region to Analytic BREP Surface — Plane Fit First

Purpose:
Region Select currently highlights/copies mesh information. That is not useful enough. The app now has a CAD kernel foundation, so Region Select must become a path to real CAD surfaces.

This task converts a selected mesh region into a real analytic BREP surface. Start with planar surface fitting. Do not attempt full automatic surfacing yet.

Primary workflow:
selected mesh region
→ fit best-fit analytic plane
→ project region boundary onto that plane
→ build real BREP planar face
→ export STEP

This turns Region Select into a real scan-to-CAD operation.

---

## Current repo foundation to preserve

Existing:

* Region Select exists.
* RegionSelection stores selected triangle indices.
* Region boundary extraction exists or should already exist from Task 67.
* BREP backend exists in cad_kernel.
* build_planar_face_from_curve() exists.
* STEP export exists.
* BrepSurfaceRecord / BrepSurfaceCollection exist.
* Surfaces workbench has CAD / BREP Output controls.

Use these systems.

Do not rewrite Region Select.
Do not rewrite the CAD kernel layer.
Do not remove preview surfaces.
Do not add another surface collection.
Do not add full NURBS fitting yet.
Do not add cylinder/cone/sphere yet unless plane is fully working.
Do not add new dependencies beyond CadQuery/OCP support already started.

---

## Part A — Add CadQuery to requirements

Update requirements.txt:

* add cadquery

Reason:
The app now has CAD/BREP features. A clean install must be able to use them.

If you want to keep CAD optional:

* make it clear in comments/docs
* but still provide an install path

Recommended:
requirements.txt:

* cadquery

or optional file:
requirements-cad.txt:

* cadquery

If using optional file, document:
python -m pip install -r requirements-cad.txt

Acceptance:

* clean environment can install CAD support
* app still degrades gracefully if CAD kernel is missing
* no import crash if cadquery is absent

---

## Part B — Add region primitive fitting module

Create:

src/regions/primitive_fit.py

Purpose:
Fit analytic primitives to selected region triangles.

Add dataclasses:

1. RegionPlaneFitResult

Fields:

* success: bool
* reason: str
* origin: np.ndarray
* normal: np.ndarray
* u_axis: np.ndarray
* v_axis: np.ndarray
* rms_error: float
* max_error: float
* sample_count: int
* triangle_count: int
* region_id: str
* region_name: str
* metadata: dict[str, object]

Add function:

fit_plane_to_region(
mesh: TriangleMeshData,
region: RegionSelection,
) -> RegionPlaneFitResult

Behavior:

* collect vertices from selected region triangles
* ignore invalid triangle indices
* deduplicate points by vertex index where possible
* compute best-fit plane using PCA/SVD
* origin = centroid
* normal = least-variance axis
* u_axis/v_axis = stable orthonormal plane basis
* compute signed distances from points to plane
* compute rms_error and max_error
* return failure if:

  * no mesh
  * no valid triangles
  * fewer than 3 usable non-collinear points
  * degenerate region
* do not mutate mesh
* do not mutate region

Tolerance:

* do not hard-fail slightly noisy scans
* store error metrics instead
* let user decide if fit is acceptable

Acceptance:

* planar triangle patch fits successfully
* noisy planar patch reports nonzero RMS/max error
* invalid region fails clearly
* degenerate region fails clearly

---

## Part C — Add region boundary projection to fitted plane

Add function:

project_region_boundary_to_plane(
boundary_points,
plane_fit: RegionPlaneFitResult,
*,
preserve_original_order=True,
) -> np.ndarray

Behavior:

* project each boundary point onto fitted plane
* preserve boundary ordering
* preserve closed/open state separately
* return Nx3 projected boundary points
* never return NaN/inf

Projection formula:
point_projected = point - dot(point - origin, normal) * normal

Also add:

region_plane_fit_error_summary(plane_fit) -> str

Examples:

* "Plane fit: RMS 0.018 mm, Max 0.064 mm"
* use app/model units generically if unit system is unknown

Acceptance:

* boundary points are flattened onto best-fit plane
* output point count equals input point count
* order is preserved

---

## Part D — Build BREP planar face from active region

Add command:

Create BREP Face From Selected Region

Available in:

* Manual RE workbench, under Region Selection
* Surfaces workbench, under CAD / BREP Output

Behavior:

1. Require loaded mesh.
2. Require active region.
3. Fit plane to active region.
4. Extract or reuse active region boundary curve.
5. Project boundary curve points onto fitted plane.
6. Build a closed CadCurveInput from projected boundary points.
7. Call build_planar_face_from_curve().
8. Create BrepSurfaceRecord.
9. Store runtime CAD object in BREP runtime cache.
10. Select created BREP surface.
11. Refresh scene browser.
12. Refresh viewport.
13. Mark project dirty.
14. Status:
    "Created BREP planar face from region: RMS <value>, Max <value>."

Failure behavior:

* no mesh:
  "Load a mesh before creating BREP from region."
* no active region:
  "Select a region first."
* boundary extraction fails:
  "Could not extract a closed boundary from selected region."
* CAD kernel unavailable:
  existing CAD kernel unavailable message
* CAD face fails:
  show CAD build result reason

Important:

* Do not create a mesh preview and call it BREP.
* The BREP object must come from the CAD kernel.
* The exported STEP must use the CAD object, not the preview mesh.

Acceptance:

* active planar region creates a BREP planar face
* created face exports to STEP
* invalid/non-boundary region fails clearly
* no crash

---

## Part E — Store region-to-BREP lineage metadata

BREP record metadata must include:

* brep_type = "planar_face"
* creation_type = "region_plane_fit_brep"
* source_region_id
* source_region_name
* source_region_triangle_count
* source_mesh_name
* boundary_curve_id if boundary curve was created/reused
* boundary_point_count
* plane_fit_origin
* plane_fit_normal
* plane_fit_u_axis
* plane_fit_v_axis
* plane_fit_rms_error
* plane_fit_max_error
* plane_fit_sample_count
* cad_build_method = "region_boundary_projected_to_best_fit_plane"
* backend
* warnings

If a boundary curve is auto-created:

* name it clearly:
  "<Region Name> Boundary"
* tag it as region_boundary
* select BREP surface after creation, not boundary curve

Acceptance:

* user can inspect how BREP was created
* future rebuild/export can reconstruct the BREP
* metadata survives project save/load

---

## Part F — Rebuild region BREP after project load

Existing BREP records may persist without raw CAD objects.

Extend Rebuild Selected BREP Surface to support:

creation_type == "region_plane_fit_brep"

Behavior:

* find source region if still present
* if source region missing but boundary curve exists:

  * rebuild from stored boundary curve and stored plane metadata
* if both missing:

  * fail clearly:
    "Cannot rebuild BREP: missing source region and boundary curve."
* rebuild CAD object
* update runtime cache
* status:
  "Rebuilt BREP planar face from region metadata."

Acceptance:

* saved project with region BREP loads safely
* user can rebuild BREP if source data exists
* no raw CAD object is serialized

---

## Part G — Viewport display for region-derived BREP

The viewport should visually distinguish:

* scan mesh
* selected region highlight
* preview surfaces
* real BREP surfaces

For region-derived BREP:

* use existing BREP display path if present
* if not present, create tessellated display from CAD object if easy
* fallback: display projected boundary and planar filled preview mesh, but label it as display preview only

Important:

* visual preview is not the exported object
* STEP export must use runtime CAD object

Suggested visual:

* BREP planar face: gold/amber translucent
* selected BREP: brighter gold/cyan edge
* source boundary curve: optional highlight

Acceptance:

* user can see the created BREP face
* it does not look identical to the original selected region
* selecting BREP surface updates diagnostics

---

## Part H — UI additions

Manual RE / Region Selection section:

* Create BREP Face From Region
* Export Selected BREP Surface to STEP, optional if not too cluttered

Surfaces / CAD-BREP Output section:

* Create BREP Face From Selected Region
* Create BREP Face From Closed Curve
* Create BREP Loft From Two Curves
* Rebuild Selected BREP Surface
* Export Selected BREP Surface to STEP

Diagnostics:

* Plane fit RMS
* Plane fit max error
* Region triangle count
* Boundary point count
* BREP source:

  * curve
  * region
  * loft
* CAD kernel status

Button enable/failure states:

* Create BREP Face From Region requires mesh and active region
* Export STEP requires selected BREP
* Face From Closed Curve requires one selected closed curve
* Loft requires two selected curves

Acceptance:

* region-to-BREP workflow is discoverable
* status messages are specific
* no confusing silent failures

---

## Part I — Scene browser

Under CAD / BREP Surfaces:

Examples:

* [V] Region Plane 1 (planar face)
* [V] BREP Face 1 (curve face)
* [V] BREP Loft 1 (loft)

Labels should distinguish source:

* region plane
* curve face
* loft

Do not show more than two tags.

Suggested labels:

* Region Plane 1 (region, planar)
* BREP Face 1 (curve, planar)
* BREP Loft 1 (loft)

Context actions:

* Select
* Rename
* Toggle Visibility
* Export STEP
* Rebuild BREP
* Delete

Acceptance:

* user can tell a region-derived CAD face apart from a curve-derived face
* BREP export is easy to find

---

## Part J — Tests

Add/update tests:

Region primitive fit:

* planar region fits successfully
* noisy planar region reports RMS/max error
* invalid triangle indices ignored
* empty region fails clearly
* degenerate/collinear region fails clearly
* normal is unit length
* u/v/normal are orthonormal

Boundary projection:

* boundary projects onto plane
* point count preserved
* no NaN/inf
* projected points have near-zero plane distance

Region-to-BREP command:

* fails with no mesh
* fails with no active region
* fails with invalid region
* succeeds on simple planar selected region if CAD kernel available
* creates BrepSurfaceRecord
* stores runtime CAD object
* metadata includes source_region_id
* metadata includes plane fit RMS/max
* selected BREP surface updates UI
* export STEP writes non-empty file if backend available

Rebuild:

* region-derived BREP rebuilds from active/source data
* missing source region fails clearly
* project save/load preserves BREP record metadata

Scene browser:

* region-derived BREP appears under CAD / BREP Surfaces
* label includes region/planar
* delete removes record and cache
* visibility toggle works

Regression:

* curve-derived BREP face still works
* BREP loft still works
* preview surfaces still work
* region select still works
* boundary extraction still works
* manual curves still work
* projected/rebuilt curves still work
* app launches without CAD kernel

Acceptance:

* pytest passes
* app launches
* selected planar region can become a real BREP face
* BREP face can export as STEP
* region select now produces actual CAD output
* no cylinder/cone/freeform yet

## Stop after this task.
