---

## Task 44 Revised: Universal scene-browser chain selection and bulk object actions

Goal:
Every object/group shown in the scene browser should support meaningful chain selection and bulk actions.

Do not redo H hotkeys unless required.
Do not add new geometry features.
Do not add BREP export.
Do not redesign the UI shell.
Do not add dependencies.

Current status:

* H visibility toggle works globally.
* Curve group selection works.
* Curve multi-selection works.
* The remaining issue is that chain/group selection is not universal.
* Delete Selected currently operates too narrowly / one object at a time.

Requirements:

1. Define universal scene selection model

Add or formalize selected IDs for each object family:

* selected_mesh: bool, if practical
* selected_section_plane_ids: set[str]
* selected_section_result_ids: set[str]
* selected_curve_ids: set[str]
* selected_surface_ids: set[str]

If full model-wide multi-selection is too risky, add the minimum required state to support:

* multi-selected section planes
* multi-selected section results
* multi-selected curves
* multi-selected surfaces

Keep active IDs where they already exist:

* active_section_plane_id
* active_section_result_id
* active_curve_id
* active_surface_id

Active object = primary selected object.
Selected IDs = full chain/multi-selection.

2. Scene browser chain selection for every group

Every visible hierarchy node should have meaningful selection behavior.

Mesh:

* selecting Mesh selects the mesh.

Section Planes root:

* selects all section planes.

Individual Section Plane:

* selects that section plane.

Section Results root:

* selects all section results and, if practical, all child curves generated from them.

Individual Section Result:

* selects that section result.
* also selects all curves generated from that section result.

Curves root:

* selects all curves.

Curve group under section result:

* selects all child curves under that section result.

Individual Curve:

* selects that curve.

Surfaces root:

* selects all surfaces.

Individual Surface:

* selects that surface.

3. Scene browser Ctrl/Shift multi-selection

Preserve existing curve multi-selection.

Extend multi-selection to:

* section planes
* section results
* surfaces

Rules:

* Ctrl-click toggles item selection where practical.
* Shift-click range-selects where practical.
* Mixed-type selection is allowed only if safe.
* If mixed-type selection is too risky, support same-family multi-selection first and show clear status for unsupported mixed selections.

4. Selection visual feedback

Viewport should reflect selected objects where currently renderable:

* selected section planes visually distinct
* selected section result raw geometry visually distinct if visible
* selected curves visually distinct
* selected surfaces visually distinct
* selected mesh keeps existing bounding/highlight behavior

Scene browser should keep selected rows selected after refresh.

5. Bulk visibility actions should operate on full selection

Existing visibility commands should apply to all selected objects, not only active object.

Commands:

* Toggle Selected Visibility
* Hide Selected
* Isolate Selected
* Show All

Apply to:

* mesh
* selected section planes
* selected section results
* selected curves
* selected surfaces

Do not break existing H behavior.

6. Bulk delete selected

Delete Selected should delete all currently selected deletable objects in one action.

Supported deletes:

* selected section planes
* selected section results
* selected curves
* selected surfaces

Rules:

* deleting a section plane deletes its section results, curves, and dependent surfaces
* deleting a section result deletes its curves and dependent surfaces
* deleting a curve deletes dependent surfaces
* deleting a surface deletes only that surface
* deleting mesh should not be enabled yet unless safe; show "Mesh deletion is not implemented yet."

Deletion must:

* update scene browser
* update viewport
* clear invalid active IDs
* select a reasonable fallback object or clear selection
* mark project dirty
* not crash on empty selection

7. Context/right-click menu

Scene browser right-click menu should use the current selection.

Required actions:

* Rename, only when exactly one renameable object is selected
* Toggle Visibility
* Hide Selected
* Isolate Selected
* Show All
* Delete Selected
* Frame Selected

If multiple objects selected:

* Rename disabled/unavailable
* Delete Selected applies to all deletable selected objects

8. Rename behavior

Rename remains single-object only.

Renameable:

* mesh
* section plane
* section result
* curve
* surface

If multiple objects are selected and Rename is requested:

* show status: "Select one object to rename."

9. Surface creation compatibility

Create Surface From Selected Curves must still work.

Rules:

* if selected curves count == 1 closed curve, create fill preview
* if selected curves count == 2, create loft preview
* if selected curves count > 2, reject with clear status
* selection changes for other object types should not pollute selected_curve_ids unless intended

10. Tests

Add/update tests for:

* selecting Section Planes root selects all section planes
* selecting Section Results root selects all section results
* selecting one Section Result selects its child curves
* selecting Curves root selects all curves
* selecting Surfaces root selects all surfaces
* bulk hide selected section planes
* bulk hide selected surfaces
* bulk delete selected curves
* bulk delete selected surfaces
* deleting section result removes its curves and dependent surfaces
* deleting section plane removes its section results, curves, and dependent surfaces
* rename rejected for multi-selection
* Create Surface From Selected Curves still works with exactly two selected curves

Acceptance:

* app launches
* every scene-browser group has meaningful chain selection
* selected groups select their children
* bulk hide/show works
* bulk delete selected works
* curve surface workflow still works
* existing H hotkey behavior remains working
* pytest passes

Stop after this task.
