---

## Task 69: Surface Patch Preview From Prepared Curves

Purpose:
The app can now create, edit, project, rebuild, validate, and organize curves. The next step is to create better surface previews from prepared curves, especially region boundaries, projected guide curves, and rebuilt curves.

This task improves the surface workflow while staying preview-only.

Do not add BREP/STEP/IGES export.
Do not integrate pboyer/verb yet.
Do not add full NURBS surfaces yet.
Do not add automatic face recognition.
Do not add boolean/solid modeling.
Do not rewrite the existing surface collection.
Do not remove existing Fill Closed Curve or Loft Between Two Curves.
Do not add new dependencies.

Goal:
The user should be able to:

1. Select clean prepared curves.
2. Choose a surface preview type.
3. Generate a surface patch preview.
4. See diagnostics explaining quality problems.
5. Adjust source curves and regenerate.
6. Use this as the first practical scan-to-surface workflow.

---

## Current repo foundation to preserve

Existing:

* Manual curves are editable.
* Region boundaries can become editable curves.
* Projected curves exist.
* Rebuilt curves exist.
* Curve validation exists.
* Surface previews exist.
* Fill Closed Curve exists.
* Loft Between Two Curves exists.
* Surface opacity/wireframe controls exist.
* Surface source curve metadata exists.
* Scene browser supports curve grouping and surface grouping.

Current limitation:

* Single closed curve fill is a simple fan fill.
* Two-curve loft is available but limited.
* No four-boundary patch preview exists.
* No curve-network patch preview exists.
* No surface-from-region-boundary workflow exists beyond manually selecting curves.

---

## Part A — Add surface preview modes

Extend surface preview support to handle multiple preview modes:

Existing modes:

* closed_curve_fill
* two_curve_loft

New modes:

* boundary_patch
* four_curve_patch
* curve_network_patch

Definitions:

1. boundary_patch
   Input:

* one closed curve

Purpose:

* creates a better preview from one closed boundary curve than the current naive fan fill where practical

Behavior:

* use current fan fill as fallback
* compute best-fit plane
* project boundary to local 2D plane
* attempt simple polygon triangulation if feasible
* if triangulation is too risky or fails, fall back to fan fill
* report warning if fallback is used

Do not spend excessive time on perfect triangulation.
Do not add dependencies.
Concave curves may still be imperfect, but diagnostics must say so.

2. four_curve_patch
   Input:

* exactly four open or closed boundary/guide curves

Purpose:

* creates a Coons-style surface preview from four ordered boundary curves

Behavior:

* resample each curve to a common count
* infer/validate curve order if possible
* if order cannot be inferred reliably, use selection order
* build a Coons-style bilinear blended grid
* triangulate grid into preview mesh
* store diagnostics

This is a preview mesh, not a real NURBS surface.

3. curve_network_patch
   Input:

* three or more curves

Purpose:

* early preview of a surface patch from multiple guide curves

Behavior:

* for now, support a conservative case:

  * multiple roughly parallel guide curves
  * resample all to common count
  * stitch adjacent curves like loft strips
* if curves are not compatible:

  * return preview unavailable with clear reason

Do not attempt arbitrary network solving yet.

---

## Part B — Surface preview backend changes

Modify or extend:

src/surfaces/surface_preview.py

Add:

SurfacePreviewMode constants or equivalent:

* CLOSED_CURVE_FILL
* TWO_CURVE_LOFT
* BOUNDARY_PATCH
* FOUR_CURVE_PATCH
* CURVE_NETWORK_PATCH

Add helper functions:

1. build_boundary_patch_preview(surface, curve)

Return:

* SurfacePreviewBuildResult

Should:

* validate curve is closed
* clean points
* estimate planarity
* project to local plane
* attempt triangulation or fan fallback
* store diagnostics:

  * preview_mode
  * source_curve_count
  * input_point_count
  * planarity_error
  * triangulation_method
  * warning if fallback used

2. build_four_curve_patch_preview(surface, curves)

Return:

* SurfacePreviewBuildResult

Should:

* require exactly four curves
* clean/resample curves
* align endpoints where practical
* build a rectangular grid
* triangulate grid cells
* store diagnostics:

  * preview_mode
  * source_curve_count
  * grid_u_count
  * grid_v_count
  * average_corner_gap
  * max_corner_gap
  * seam_reversal_applied flags if used
  * warning if curve order is uncertain

3. build_curve_network_patch_preview(surface, curves)

Return:

* SurfacePreviewBuildResult

Should:

* require at least three curves
* resample all curves to same point count
* stitch adjacent curves into strips
* store diagnostics:

  * preview_mode
  * source_curve_count
  * resampled_point_count
  * strip_count
  * average_pair_distance
  * max_pair_distance
  * warning if curve spacing varies heavily

Rules:

* never mutate source curves
* never crash on invalid curves
* return preview unavailable with reason instead of throwing
* keep mesh output as SurfacePreviewMesh
* keep existing build_surface_preview() public API if possible

Acceptance:

* one-curve fill still works
* two-curve loft still works
* four selected curves can generate preview patch
* compatible multi-curve network can generate stitched preview
* incompatible curves fail with clear reason

---

## Part C — Add surface creation commands

Add commands:

1. Create Boundary Patch From Curve
   Input:

* exactly one selected closed curve

Creates:

* SurfacePatch with surface_type="preview_boundary_patch"
* preview_mode="boundary_patch"

2. Create Four-Curve Patch
   Input:

* exactly four selected curves

Creates:

* SurfacePatch with surface_type="preview_four_curve_patch"
* preview_mode="four_curve_patch"

3. Create Curve Network Patch
   Input:

* three or more selected curves

Creates:

* SurfacePatch with surface_type="preview_curve_network_patch"
* preview_mode="curve_network_patch"

Keep existing:

* Fill Closed Curve
* Loft Between Two Curves

Do not remove old commands.
The new commands should be explicit, not hidden behind one overloaded button only.

Acceptance:

* commands are available from Surfaces workbench
* commands validate selection count
* commands create SurfacePatch objects
* surfaces appear in scene browser
* surface previews render in viewport
* undo/redo works with created surfaces

---

## Part D — Surfaces workbench UI

Update Surfaces workbench to expose clear surface workflows:

Primary buttons:

* Fill Closed Curve
* Loft Between Two Curves
* Create Boundary Patch
* Create Four-Curve Patch
* Create Curve Network Patch

Source tools:

* Select Source Curves
* Isolate Source Curves
* Show Source Curves
* Frame Source Curves

Diagnostics:

* Surface type
* Preview mode
* Source curve count
* Preview available
* Preview reason
* Warning
* Grid size, if available
* Planarity error, if available
* Average pair distance, if available
* Max pair distance, if available
* Raw metadata remains available but should not be the only readable diagnostics

Controls:

* Opacity
* Wireframe overlay
* Delete Surface
* Deselect

Disabled states:

* Create Boundary Patch disabled or fails gracefully unless one curve selected
* Create Four-Curve Patch disabled or fails gracefully unless four curves selected
* Create Curve Network Patch disabled or fails gracefully unless three or more curves selected

Acceptance:

* user can find new surface commands without top-menu hunting
* surface diagnostics are readable
* failed previews explain why

---

## Part E — Selection-order handling

Four-curve patches depend on curve order.

Implement simple selection-order support if already possible.

If current selection system does not preserve order:

* use scene browser order or curve collection order
* store warning:
  "Curve order inferred from scene order; inspect patch."

Add optional buttons later if needed:

* Move Source Curve Up
* Move Source Curve Down

Do not implement complex source-order editor in this task unless low-risk.

For now:

* create patch
* if twisted, diagnostics should tell user to reorder/select differently in future task

Acceptance:

* four-curve command works predictably enough for simple test cases
* uncertain ordering is documented in metadata warning
* no silent bad patch without warning

---

## Part F — Surface metadata lineage

Every surface created in this task must store:

* preview_mode
* source_curve_count
* source_curve_ids
* source_curve_names
* source_curve_creation_types
* source_curve_tags if available
* source_region_ids if curves came from regions
* source_mesh_names if available
* preview_available
* preview_reason
* preview_warning
* validation warnings/errors from source curves

For boundary patch:

* boundary_curve_id
* boundary_curve_name
* planarity_error
* triangulation_method

For four-curve patch:

* curve_order
* grid_u_count
* grid_v_count
* average_corner_gap
* max_corner_gap

For curve network patch:

* network_curve_count
* resampled_point_count
* strip_count
* average_pair_distance
* max_pair_distance

Acceptance:

* user can inspect where surface came from
* future export/fitting task can reuse metadata
* project save/load preserves metadata

---

## Part G — Surface preview quality safeguards

Add validation before creating surface preview:

For boundary patch:

* require one closed curve
* require at least 3 usable points
* warn if planarity error is high
* warn if point count is very high and curve should be rebuilt

For four-curve patch:

* require four curves
* require each curve has at least 2 usable points
* warn if endpoint gaps between curves are large
* warn if curves come from different source regions/meshes
* warn if one curve is closed and others are open

For curve network patch:

* require at least three curves
* require all curves have at least 2 usable points
* warn if curve spacing varies heavily
* warn if curve point counts differ heavily before resampling

Do not make warnings fatal unless geometry is impossible.
Fatal errors:

* no usable points
* too few curves
* degenerate source curve
* grid generation fails

Acceptance:

* invalid inputs fail cleanly
* questionable inputs generate warnings
* warnings are visible in surface context

---

## Part H — Better surface preview visuals

Surface preview should remain visually distinct but not overpower the mesh.

Requirements:

* selected surface uses existing selected color style
* unselected preview is darker/subtle
* wireframe overlay remains useful
* boundary/four-curve/network previews should show mesh grid/wireframe if enabled
* opacity should apply consistently
* surface updates when opacity/wireframe changes

Optional:

* show source curves highlighted while surface selected
* existing source curve highlighting should continue working

Acceptance:

* new patches are visually readable
* source curves remain understandable
* opacity/wireframe controls still work

---

## Part I — Scene browser labels

Surface labels should distinguish preview type:

Examples:

* [V] Fill Surface 1 (fill)
* [V] Loft Surface 1 (loft)
* [V] Boundary Patch 1 (boundary patch)
* [V] Four-Curve Patch 1 (4-curve patch)
* [V] Network Patch 1 (network patch)

Do not show more than two tags.

Surface group remains:
Surfaces
[V] Boundary Patch 1 (boundary patch)

Acceptance:

* user can identify surface preview type from scene browser
* visibility/delete/select still works

---

## Part J — Undo/redo

All new surface creation commands must be undoable.

Undo:

* removes created surface
* refreshes scene browser
* refreshes viewport
* restores selection fallback

Redo:

* restores surface
* refreshes scene browser
* refreshes viewport

Use existing created-surface undo pathway if present.

Acceptance:

* Create patch
* Undo removes it
* Redo restores it
* project dirty state updates correctly

---

## Part K — Tests

Add/update tests for:

Surface preview backend:

* boundary patch rejects open curve
* boundary patch accepts closed curve
* boundary patch returns preview mesh
* boundary patch stores planarity diagnostics
* four-curve patch rejects wrong curve count
* four-curve patch accepts simple rectangular four-curve input
* four-curve patch creates grid mesh
* curve network patch rejects fewer than three curves
* curve network patch accepts compatible parallel curves
* curve network patch creates strip mesh
* invalid curves do not crash
* warnings stored in result diagnostics

Surface creation commands:

* Create Boundary Patch requires one closed curve
* Create Boundary Patch creates SurfacePatch
* Create Four-Curve Patch requires four curves
* Create Four-Curve Patch creates SurfacePatch
* Create Curve Network Patch requires at least three curves
* Create Curve Network Patch creates SurfacePatch
* all commands store source_curve_ids
* all commands store preview_mode
* undo/redo works for each new surface type

UI/workbench:

* Surfaces workbench shows new buttons
* disabled/failure states are clear
* diagnostics update for selected surface
* opacity/wireframe controls still work

Scene browser:

* surface labels include fill/loft/boundary patch/4-curve patch/network patch tags
* selecting surface shows source curves
* delete surface works

Regression:

* existing Fill Closed Curve still works
* existing Loft Between Two Curves still works
* manual curve edit still works
* projected curves still work
* rebuilt curves still work
* region boundary curves still work
* project save/load still works

Acceptance:

* pytest passes
* app launches
* user can create boundary patch preview
* user can create four-curve patch preview
* user can create curve-network patch preview
* source curves remain selectable/highlightable
* no BREP/NURBS export yet
* no pboyer/verb integration yet

## Stop after this task.
