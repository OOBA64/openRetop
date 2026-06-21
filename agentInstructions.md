---

---

## Task 72 Rewrite: Manual Curve Workflow Rescue + Mesh-Conforming Loft Preview

Purpose:
The current manual curve workflow is not usable enough. In curve edit mode, camera movement is blocked or unreliable, clicks sometimes place random points, point editing is unclear, there are too many visible buttons/options, and the curve does not behave like a smooth ExModel-style guide curve.

Fix the user workflow before adding more primitives.

This task has two goals:

1. Make manual curve creation/editing feel controlled, simple, and smooth.
2. Add a mesh-conforming loft preview mode for open body-line curves so lofted surfaces can follow the scan body instead of floating/chording through space.

Do not add cylinder/cone/sphere fitting.
Do not add overbuild/trim yet.
Do not refactor MainWindow broadly.
Do not remove existing BREP functionality.
Do not remove region select.
Do not add pboyer/verb.
Do not make a full UI redesign.
Do not expose every advanced option by default.

---

## Core observed problems

Current user issues:

* In curve edit mode, camera orbit/pan/zoom is unreliable.
* Left click may place a random point when the user meant to rotate/select.
* User gets stuck in the camera position from when edit mode started.
* Too many curve buttons/options are visible.
* Most curve options should be automatic unless advanced mode is enabled.
* Hybrid curves are still sharp where they should be smooth.
* User must place too many points to trace a smooth body curve.
* BREP lofts made from open body-line curves do not conform to the scan/body surface.
* Loft surfaces still feel disconnected from the shape being reverse engineered.

Primary fix:
Separate navigation, curve creation, curve editing, and surface preview behavior into clear modes with safe defaults.

---

## Part A — Fix viewport navigation during curve modes

Camera movement must always work.

Rules:

* Right mouse drag: orbit camera.
* Middle mouse drag: pan camera.
* Mouse wheel: zoom.
* Shift + left drag: pan camera if supported.
* Alt + left drag: orbit camera if supported.
* Esc: cancel current placement/edit submode, not entire app.
* Left click should only place a curve point when the app is explicitly in Draw/Add Point mode.

Curve edit mode must not hijack all pointer input.

Required behavior:

* User can freely orbit/pan/zoom while creating a curve.
* User can freely orbit/pan/zoom while editing a curve.
* No point is placed unless:

  * Create Curve mode is active and Add Points is active, or
  * Add Point submode is active, or
  * Insert Point submode is active.
* Selecting/editing existing control points must not disable camera movement.
* Dragging a control point only starts when the cursor is actually over a control point.

Acceptance:

* Enter curve edit mode, orbit the camera with right mouse drag.
* Pan and zoom still work.
* Clicking empty space does not add a random point.
* Clicking/dragging a control point selects/moves that point.
* No accidental point placement while navigating.

---

## Part B — Replace current cluttered curve UI with simple/advanced workflow

The Manual RE panel should default to a small set of obvious actions.

Default visible controls:

Manual Curve:

* Create Curve
* Edit Selected Curve
* Finish Curve
* Cancel
* Undo Last Point
* Close / Open Curve
* Smoothness slider
* Fit to Mesh toggle
* Convert Selected Curve to Smooth Guide

Region Selection:

* Region Select
* Extract Boundary
* Create BREP Face From Region

Hide advanced point controls behind an "Advanced Curve Controls" collapsible section.

Advanced controls:

* Add Point
* Insert Point
* Delete Selected Point
* Set Point Smooth
* Set Point Corner
* Toggle Smooth/Corner
* Auto Detect Corners
* Clear Auto-Detected Corners
* Straighten Selected Span
* Smooth Selected Span
* Sample Count
* Corner Threshold
* Preserve Corners
* Curve Method dropdown

Default state:

* Curve Type: Smooth Guide
* Fit to Mesh: ON when mesh is loaded
* Auto corner detection: OFF during creation
* Preserve manually marked corners: ON
* Sample count: 128
* Smoothness: 4

Acceptance:

* Manual RE panel is no longer a wall of buttons.
* Common workflow is obvious.
* Advanced options still exist but are hidden unless needed.
* User does not need to understand every option to make a good curve.

---

## Part C — Add explicit tool submodes

Add a small internal manual-curve mode state machine.

Manual curve main modes:

* inactive
* drawing
* editing

Manual curve submodes:

* navigate
* add_point
* insert_point
* move_point
* select_point

Rules:

* Creating a new curve starts in drawing/add_point mode.
* Editing an existing curve starts in editing/select_point mode.
* After selecting a control point, dragging it moves only that point.
* Clicking empty space in edit mode does not add a point.
* Add Point must be explicitly enabled.
* Insert Point must be explicitly enabled.
* When Add Point or Insert Point is active, status text must clearly say so.
* Esc exits Add/Insert submode back to edit/select mode.
* Esc again exits edit mode.

Status examples:

* "Drawing curve: left-click to add points. Right-drag to orbit."
* "Editing curve: select or drag control points. Press Add Point to add points."
* "Add Point active: left-click to append point. Esc to return to edit mode."
* "Insert Point active: click curve segment to insert. Esc to return to edit mode."

Acceptance:

* No ambiguous click behavior.
* User always knows whether a click will place a point.
* Navigation always remains available.

---

## Part D — Make Smooth Guide the default curve type

Current Hybrid behavior is too corner-heavy.

Add or make primary:

MANUAL_CURVE_METHOD_SMOOTH_GUIDE = "smooth_guide"

Smooth Guide behavior:

* All points are smooth by default.
* Curve approximates the intended smooth path.
* It should not hard-kink unless a point is manually marked Corner.
* It should require fewer points than current Hybrid.
* It should work well for wheel arches, bumper contours, body lines, and fender edges.

Implementation:

* Do not auto-detect corners during initial drawing.
* Keep user control points fixed.
* Generate the visible fitted curve from a smoothed/fair curve path.
* Use centripetal Catmull-Rom or constrained smoothing as the first implementation.
* Apply smoothing to fitted/display curve, not to stored control point positions.
* Preserve endpoints for open curves.
* Preserve closure for closed curves.
* Preserve manual corners exactly.

Acceptance:

* User can trace a smooth wheel arch with 5–8 points.
* Curve is smooth without needing 30 points.
* Curve does not kink unless user marks a point as Corner.
* Existing Hybrid/Polyline options still work.

---

## Part E — Disable auto-corner detection during normal drawing

Auto corner detection is currently too aggressive for sparse scan tracing.

Change behavior:

* Auto corner detection is OFF by default.
* Auto corner detection does not run while placing points unless explicitly enabled.
* Auto Detect Corners is primarily a command the user can run after the curve is drawn.
* If auto detection marks points, store those as auto corners, not manual corners.

Metadata:

* point_type_source:

  * manual
  * auto
  * legacy
  * imported

Commands:

* Auto Detect Corners
* Clear Auto-Detected Corners

Rules:

* Clear Auto-Detected Corners must not remove manually set corners.
* User-set corners always override auto logic.

Acceptance:

* Smooth body curves are no longer accidentally segmented.
* Auto detection remains available for boxy/sharp shapes.
* User can repair auto-detected mistakes.

---

## Part F — Always show editable control cage for selected manual curves

When a manual curve is selected:

* show fitted curve
* show control polygon lightly
* show control points
* show corner/smooth point markers
* show selected point if applicable

When not editing:

* show the control cage lightly if the curve is selected.
* show a status hint: "Click Edit Selected Curve to modify control points."

When editing:

* show full control cage clearly.
* control point clicking must work.
* selected point type must update in the UI.

Visual rules:

* fitted curve: thick yellow/white
* control polygon: thin gray
* smooth points: small white/blue dots
* corner points: orange square/cube or orange marker
* selected point: cyan/larger

Acceptance:

* User can see why the curve is sharp/smooth.
* User can select points.
* Selected Point no longer stays "(none)" after clicking control points.
* Smooth/Corner buttons enable only when a control point is actually selected.

---

## Part G — Add one-click repair for bad current curves

Add command:

Convert Selected Curve to Smooth Guide

Behavior:

* Takes selected manual curve.
* Keeps current control point positions.
* Sets all auto-detected corners to smooth.
* Keeps manually marked corners if metadata supports that distinction.
* Switches method to Smooth Guide.
* Uses Fit to Mesh if existing curve was mesh-snapped.
* Recomputes fitted curve.
* Creates undo step.
* Refreshes viewport.

Add command:

Reduce/Simplify Selected Guide Curve

Behavior:

* Reduces excessive control points while preserving shape.
* Keeps endpoints.
* Keeps manual corners.
* Uses tolerance based on model size.
* Creates a new simplified guide curve or updates with undo support.
* Does not destroy original unless user confirms.

Acceptance:

* User can fix a bad screenshot-style curve without redrawing.
* User can reduce point count.
* Curve becomes smoother with fewer hard breaks.

---

## Part H — Improve curve-on-mesh snapping during edit

When Fit to Mesh is ON:

* added points snap to mesh
* moved points re-project to mesh
* inserted points snap/project to mesh
* fitted curve may optionally be projected to mesh for preview

Do not make every sampled point snap by default unless using mesh-conforming curve mode.
Store:

* snap triangle indices
* snap normals
* projection distance
* source mesh name

Add option:

* Keep Curve On Mesh

Behavior:

* If enabled, after curve fit/smoothing, project sampled fitted curve to the mesh for display.
* Control points remain editable.
* This helps body-line curves stay visually on the scan.

Acceptance:

* Moved control points stay on body surface when Fit to Mesh is ON.
* Smooth fitted curve can visually lie on the scan surface.
* User can turn this off if it causes unwanted noise.

---

## Part I — Mesh-conforming loft preview for open body-line curves

Separate problem:
Open-curve BREP lofts between body lines may not conform to the scan body. A pure CAD loft interpolates between the curves in free space; it does not know it should follow the scanned body unless additional constraints/projection are applied.

Add a new preview/build mode:

Mesh-Conforming Loft Preview

Available for:

* two or more open curves
* curves on or near the mesh

Behavior:

1. Build normal loft sample grid between source curves.
2. For each sampled grid point, project it to nearest point on mesh.
3. Reject or warn if projection distance exceeds threshold.
4. Display the mesh-conforming preview as shaded surface.
5. Hide internal triangle edges by default.
6. Use this preview to evaluate whether source curves are good.
7. Do not call this a final BREP unless a real CAD fitting step is added.

UI:

* Create Mesh-Conforming Loft Preview
* Projection Distance Threshold
* Show Projection Error Heatmap, optional
* Convert Preview to Surface Fit, optional/future

Metadata:

* source_curve_ids
* source_mesh_name
* projection_mean_distance
* projection_max_distance
* failed_projection_count
* grid_u_count
* grid_v_count
* conforming_preview=True

Acceptance:

* Open body-line curves create a preview surface that follows the scan better than raw BREP loft.
* Projection distances are reported.
* Internal triangle edges are hidden by default.
* User understands this is a preview/conforming mesh surface, not a clean BREP yet.

---

## Part J — Keep BREP loft separate from mesh-conforming preview

Do not pretend a mesh-projected preview is a clean CAD loft.

Rules:

* BREP Loft:

  * clean CAD surface through source curves
  * may float/chord if source curves are open and body curvature is not constrained
  * exportable to STEP
* Mesh-Conforming Loft Preview:

  * projected onto scan mesh
  * visually conforms to body
  * useful for checking/guide surface
  * not automatically a STEP/BREP surface

Add status explanation:
"BREP loft is a CAD surface through the curves. Mesh-Conforming Preview projects the loft to the scan for visual/body-following evaluation."

Acceptance:

* User can choose between CAD loft and conforming preview.
* No false labeling.
* This directly addresses why open BREP lofts do not hug the body.

---

## Part K — Surface display fix: hide internal triangles by default

Generated surface previews currently look like triangulated retopology meshes.

Change default display:

* shaded smooth surface
* no internal triangle wireframe
* show only boundary edges
* optional sparse U/V isocurves
* wireframe/debug triangles hidden behind "Show Surface Tessellation"

Rules:

* BREP/preview surfaces should not show every triangle by default.
* Mesh-conforming preview should also hide internal triangles by default.
* Debug wireframe remains available.

Acceptance:

* Loft previews look like smooth surfaces instead of triangulated grids.
* User can still debug tessellation if needed.
* ExModel-like visual behavior is closer.

---

## Part L — Tests

Add/update tests:

Mode behavior:

* camera navigation events are not consumed by curve edit mode
* left click empty space in edit mode does not add point
* Add Point submode adds point
* Insert Point submode inserts point
* Esc exits submodes predictably
* edit mode preserves camera navigation

Smooth guide:

* new Smooth Guide curves default all points smooth
* sparse arch curve produces smooth sampled curve
* explicit corner remains sharp
* auto corner detection does not run unless commanded/enabled
* Convert Selected Curve to Smooth Guide clears auto-corners
* simplify guide curve reduces points while preserving endpoints/corners

Control cage:

* selected manual curve shows control points
* selected point type updates after click
* Set Smooth/Corner buttons enable when point selected
* non-edit selected curve still shows lightweight control cage

Snap/edit:

* moved point reprojects to mesh when Fit to Mesh ON
* added point snaps to mesh
* inserted point snaps to mesh
* Keep Curve On Mesh projects fitted curve for display

Mesh-conforming loft:

* open curves generate conforming preview
* grid points project to mesh
* projection distance metrics stored
* failed projection count reported
* preview does not create BREP record unless explicitly converted
* internal triangle edges hidden by default

Surface display:

* preview surfaces default to no triangle wireframe
* boundary edges still visible
* debug wireframe option works

Regression:

* manual curves still save/load
* old curves still load
* BREP face from curve still works
* editable BREP loft still works
* region select still works
* region-to-BREP planar face still works
* app launches without CAD kernel
* app launches with CAD kernel
* pytest passes

Acceptance:

* user can create/edit curves without losing camera control
* no random point placement during navigation/editing
* default curve workflow is simple and automated
* smooth body guide curves require far fewer points
* advanced controls are hidden unless needed
* mesh-conforming loft preview follows the scan body better than raw BREP loft
* surfaces no longer look like visible triangle grids by default

## Stop after this task.





---

## Future Refactor Phase — Tasks 78–80

Purpose:
After the manual curve, loft, overbuild, trim, and BREP workflow is functional, perform a full architecture cleanup. The current app has too much tool logic, UI logic, export logic, settings logic, and state coordination inside MainWindow. That must be split into clean, testable modules.

This refactor phase must not change user-visible behavior unless explicitly stated. The goal is separation, maintainability, and safer future development.

---

## Task 78: Application Architecture Refactor — Controllers, Commands, and Services

Goal:
Remove feature logic from MainWindow and move it into dedicated controllers/services.

Create structure:

src/app/controllers/

* selection_controller.py
* viewport_controller.py
* scene_controller.py
* curve_controller.py
* manual_curve_controller.py
* region_controller.py
* surface_controller.py
* brep_controller.py
* transform_controller.py

src/app/commands/

* command_context.py
* command_result.py
* curve_commands.py
* region_commands.py
* surface_commands.py
* brep_commands.py
* transform_commands.py
* export_commands.py

src/app/services/

* status_service.py
* dirty_state_service.py
* selection_service.py
* undo_service.py
* project_service.py
* viewport_refresh_service.py
* scene_browser_refresh_service.py

Rules:

* MainWindow should not directly implement feature behavior.
* MainWindow should own the shell, app lifecycle, and panel mounting only.
* Controllers coordinate tools.
* Commands perform discrete user actions.
* Services handle shared cross-cutting behavior.
* No feature regression.
* No UI redesign in this task.
* No new geometry features in this task.

MainWindow should retain:

* app startup
* menu/panel initialization
* top-level event wiring
* controller construction
* global shutdown/error handling

MainWindow should lose:

* BREP creation logic
* curve editing logic
* region extraction/fitting logic
* surface generation logic
* export logic
* detailed selection mutation logic
* direct project serialization logic where possible

Acceptance:

* MainWindow is substantially smaller.
* Existing commands still work.
* Undo/redo still works.
* Scene browser still updates.
* Viewport still updates.
* Tests pass.
* App launches.
* No user workflow is broken.

---

## Task 79: UI Refactor — Workbench Panels, Widgets, and Settings Separation

Goal:
Move all UI construction out of MainWindow into dedicated panels and reusable widgets.

Create structure:

src/app/panels/

* base_panel.py
* scene_panel.py
* transform_panel.py
* sections_panel.py
* curves_panel.py
* manual_re_panel.py
* region_panel.py
* surfaces_panel.py
* brep_panel.py
* analysis_panel.py

src/app/widgets/

* labeled_value.py
* numeric_entry.py
* color_picker_row.py
* command_button.py
* collapsible_section.py
* object_list_actions.py
* status_strip.py

src/app/bindings/

* ui_state.py
* panel_bindings.py
* command_bindings.py

Settings structure:

src/settings/

* settings_data.py
* settings_io.py
* settings_registry.py
* display_settings.py
* curve_settings.py
* region_settings.py
* surface_settings.py
* brep_settings.py
* export_settings.py

Rules:

* Panels build UI only.
* Panels do not contain geometry logic.
* Panels call controllers/commands.
* Settings UI must be separate from settings data.
* Preferences dialog must not own business logic.
* Reusable rows/widgets should replace repetitive label/button code.
* Workbench panels should be mountable independently.
* No behavior change unless required to preserve functionality.

Acceptance:

* MainWindow no longer contains thousands of lines of widget layout.
* Surface/BREP UI is in surfaces_panel.py / brep_panel.py.
* Manual curve UI is in manual_re_panel.py.
* Region UI is in region_panel.py.
* Preferences/settings code is split cleanly.
* Settings save/load still works.
* App launches.
* Tests pass.

---

## Task 80: Project IO, Export, and Dependency Boundary Refactor

Goal:
Separate all import/export, project persistence, CAD export, mesh export, and optional dependency handling into clean packages.

Create structure:

src/io/

* project_io.py
* project_schema.py
* project_migrations.py
* mesh_import.py
* mesh_export.py
* curve_io.py
* surface_io.py
* brep_io.py

src/export/

* export_registry.py
* step_exporter.py
* mesh_exporter.py
* curve_exporter.py
* diagnostic_exporter.py

src/dependencies/

* optional_dependencies.py
* cad_kernel_dependency.py
* vtk_dependency.py

src/cad_kernel/

* keep backend-specific CAD code isolated
* no app/UI imports inside cad_kernel
* no Tk imports inside cad_kernel

Rules:

* Export commands call export services.
* Project IO should not live inside MainWindow.
* CAD/BREP export should not be mixed with UI callbacks.
* Optional dependencies must be detected in one place.
* Missing optional dependency must never crash app startup.
* Project schema should support migration/versioning.
* STEP export must only export real CAD/BREP objects.
* Mesh export must not pretend to be BREP export.

Acceptance:

* Project save/load works.
* Existing projects load.
* STEP export works.
* Mesh import still works.
* Optional CAD kernel detection works.
* App launches without optional CAD packages.
* Export code is testable without UI.
* MainWindow does not directly write files except through services/commands.
* Tests pass.

---

## Refactor phase acceptance

After Tasks 78–80:

* MainWindow is mostly application shell.
* UI panels are separate.
* Settings are separated by domain.
* Export and project IO are separate.
* CAD kernel code remains isolated.
* Commands/controllers are testable.
* Geometry logic is outside UI files.
* No major user-visible regression.
* Future ExModel-style tools can be added without bloating MainWindow again.

---
